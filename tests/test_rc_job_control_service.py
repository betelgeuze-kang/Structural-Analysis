"""Control linearization and durable custody using synthetic invocation artifacts."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from structural_analysis.execution import job_service as implementation
from structural_analysis.execution.job_service import JobServiceError, JobView
from . import test_rc_fiber_job_service as seams
from .test_rc_fiber_job_service import no_solver as no_solver


def command(s, job, action, **changes):
    view = s.get_rc_control(job.job_id, **seams.tenant())
    return {
        "schema_version": "rc-job-control-request.v1",
        "control_id": "rc-control-" + str(uuid4()),
        "action": action,
        "expected_request_hash": view["job"]["request_hash"],
        "expected_checkpoint_hash": view["job"]["checkpoint_hash"],
        "expected_control_revision": view["control_revision"],
        "expected_attempt": view["job"]["attempt"],
        **changes,
    }


def post(s, job, action):
    return s.submit_rc_control(job.job_id, command(s, job, action), **seams.tenant())


def current(s, job):
    return s.get_rc_control(job.job_id, **seams.tenant())


def reserve(s, c, phase="analysis", analysis=None):
    return s.reserve_rc_execution_attempt(
        c.job.job_id,
        **seams.lease(c),
        phase=phase,
        chunk_request_hash=seams.outcome(c)["chunk_request_hash"],
        analysis_ordinal=analysis,
    )


def test_hold_resume_keeps_old_view_and_skips_held_queue(tmp_path):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    old = job.to_dict()
    paused = post(s, job, "pause")["view"]
    assert paused["state"] == "paused" and paused["job"]["status"] == "queued"
    assert s.claim_next(worker_id="worker-a", authorization_token=seams.WORKER) is None
    other = seams.submit(s, key="next-job")
    assert seams.claim(s).job.job_id == other.job_id
    assert set(s.get_job(job.job_id, **seams.tenant()).to_dict()) == set(old)
    resumed = post(s, job, "resume")["view"]
    assert resumed["state"] == "available"
    assert seams.claim(s).job.job_id == job.job_id
    assert current(s, job)["control_revision"] == 2
    assert s.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]


def test_retry_receipt_is_original_but_view_is_current(tmp_path):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    pause = command(s, job, "pause")
    accepted = s.submit_rc_control(job.job_id, pause, **seams.tenant())
    post(s, job, "resume")
    replay = s.submit_rc_control(job.job_id, pause, **seams.tenant())
    assert (
        replay["accepted_control_revision"]
        == accepted["accepted_control_revision"]
        == 1
    )
    assert replay["control_id"] == pause["control_id"]
    assert replay["view"]["control_revision"] == 2
    assert replay["view"]["last_command"]["action"] == "resume"
    with pytest.raises(JobServiceError, match="rc_control_id_conflict"):
        s.submit_rc_control(job.job_id, pause | {"action": "cancel"}, **seams.tenant())


def test_heartbeat_does_not_invalidate_control_cas_but_attempt_does(tmp_path):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    stale = command(s, job, "pause")
    c = seams.claim(s)
    with pytest.raises(JobServiceError, match="rc_control_source_conflict"):
        s.submit_rc_control(job.job_id, stale, **seams.tenant())
    pending = command(s, job, "pause")
    s.heartbeat(job.job_id, **seams.lease(c))
    assert (
        s.submit_rc_control(job.job_id, pending, **seams.tenant())["view"]["state"]
        == "pause_pending"
    )


@pytest.mark.parametrize(
    "action,expected", [("pause", "queued"), ("cancel", "cancelled")]
)
def test_control_before_analysis_commits_without_reservation(
    tmp_path, action, expected
):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    assert post(s, job, action)["view"]["state"] == action + "_pending"
    s.heartbeat(job.job_id, **seams.lease(c))
    stopped = reserve(s, c)
    assert isinstance(stopped, JobView) and stopped.status == expected
    assert current(s, job)["last_command"]["boundary"] == "before_analysis"
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 0
    assert s.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]


@pytest.mark.parametrize("legacy", [False, True])
def test_analysis_first_allows_only_mandatory_verification(tmp_path, legacy):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    a = seams.reserve(s, c) if legacy else reserve(s, c)
    post(s, job, "pause")
    seams.record(s, c, a, seams.outcome(c))
    v = seams.reserve(s, c) if legacy else reserve(s, c, "verification", a)
    assert v == 2
    seams.record(s, c, v, seams.outcome(c, "verification"))
    if legacy:
        with pytest.raises(JobServiceError, match="rc_control_boundary_stop"):
            seams.reserve(s, c)
    else:
        with pytest.raises(
            JobServiceError, match="rc_control_verification_binding_invalid"
        ):
            reserve(s, c, "verification", a)
        assert reserve(s, c).status == "queued"
    assert current(s, job)["state"] == "paused"
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 2


def test_phase_reservation_rejects_wrong_chunk_or_phase(tmp_path):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    a = reserve(s, c)
    with pytest.raises(
        JobServiceError, match="rc_invocation_reservation_phase_mismatch"
    ):
        seams.record(s, c, a, seams.outcome(c, "verification"))
    seams.record(s, c, a, seams.outcome(c))
    with pytest.raises(
        JobServiceError, match="rc_control_verification_binding_invalid"
    ):
        s.reserve_rc_execution_attempt(
            job.job_id,
            **seams.lease(c),
            phase="verification",
            chunk_request_hash="sha256:" + "f" * 64,
            analysis_ordinal=a,
        )


def test_pause_upgrades_to_cancel_and_legacy_routes_cannot_override(tmp_path):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    post(s, job, "pause")
    with pytest.raises(JobServiceError, match="rc_control_state_conflict"):
        post(s, job, "resume")
    post(s, job, "cancel")
    with pytest.raises(JobServiceError, match="rc_control_state_conflict"):
        post(s, job, "pause")
    for invoke in (
        lambda: s.cancel_job(job.job_id, **seams.tenant()),
        lambda: s.resume_failed_job(
            job.job_id,
            **seams.tenant(),
            expected_request_hash=job.request.content_hash,
            expected_checkpoint_hash=None,
        ),
    ):
        with pytest.raises(JobServiceError, match="rc_control_route_required"):
            invoke()
    assert reserve(s, c).status == "cancelled"
    assert current(s, job)["control_revision"] == 2


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_expiry_applies_control_preserves_unknown_spend(tmp_path, action):
    clock = seams.Clock()
    s = seams.service(tmp_path, clock)
    job = seams.submit(s)
    c = seams.claim(s)
    assert reserve(s, c) == 1
    post(s, job, action)
    clock.advance()
    assert s.claim_next(worker_id="worker-a", authorization_token=seams.WORKER) is None
    view = current(s, job)
    assert view["last_command"]["boundary"] == "lease_expired"
    assert view["state"] == ("paused" if action == "pause" else "terminal")
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 1
    assert s.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]


def test_actual_failure_remains_failure_and_explicit_retry_clears_hold(tmp_path):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    post(s, job, "pause")
    failed = s.fail_job(
        job.job_id, **seams.lease(c), error_code="synthetic_failure", retriable=True
    )
    assert failed.status == "failed" and failed.error_code == "synthetic_failure"
    assert current(s, job)["last_command"]["disposition"] == "failed"
    s.resume_failed_job(
        job.job_id,
        **seams.tenant(),
        expected_request_hash=job.request.content_hash,
        expected_checkpoint_hash=None,
    )
    assert current(s, job)["state"] == "available"


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_checkpoint_publication_applies_control_atomically(
    tmp_path, monkeypatch, action
):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    checkpoint, *_ = seams.synthetic_admission_artifacts(s, c, monkeypatch)
    post(s, job, action)
    saved = seams.save_synthetic_checkpoint(s, c, checkpoint)
    assert saved.status == ("checkpointed" if action == "pause" else "cancelled")
    assert saved.checkpoint.content_hash == seams.sha(checkpoint)
    assert current(s, job)["last_command"]["boundary"] == "verified_checkpoint"
    assert s.claim_next(worker_id="worker-a", authorization_token=seams.WORKER) is None
    assert s.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_final_publication_linearizes_prior_control_without_fake_prefix(
    tmp_path, monkeypatch, action
):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    _, _, raw, _, proof = seams.synthetic_admission_artifacts(s, c, monkeypatch)
    post(s, job, action)
    result = s.complete_job(
        job.job_id,
        **seams.lease(c),
        result_bytes=raw,
        result_media_type="application/json",
        evidence=proof,
    )
    assert result.status == ("succeeded" if action == "pause" else "cancelled")
    assert result.checkpoint is None
    assert (result.result is not None) is (action == "pause")
    assert result.progress_completed == (3 if action == "pause" else 0)
    assert current(s, job)["last_command"]["boundary"] == "verified_final"
    with pytest.raises(JobServiceError, match="rc_control_state_conflict"):
        post(s, job, "cancel")
    assert s.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]


def test_completion_first_makes_waiting_cancel_conflict(tmp_path, monkeypatch):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    _, _, raw, _, proof = seams.synthetic_admission_artifacts(s, c, monkeypatch)
    cancel = command(s, job, "cancel")
    entered, release = Event(), Event()
    original = s._put_blob

    def held(*args, **kwargs):
        if kwargs.get("role") == "result":
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(s, "_put_blob", held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        done = pool.submit(
            s.complete_job,
            job.job_id,
            **seams.lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=proof,
        )
        assert entered.wait(5)
        waiting = pool.submit(s.submit_rc_control, job.job_id, cancel, **seams.tenant())
        release.set()
        assert done.result(5).status == "succeeded"
        with pytest.raises(JobServiceError, match="rc_control_state_conflict"):
            waiting.result(5)
    assert current(s, job)["control_revision"] == 0


def test_control_get_does_not_compile_or_hydrate_numerical_artifacts(
    tmp_path, monkeypatch
):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    post(s, job, "pause")

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Control GET must not validate numerical payloads or compile models"
        )

    monkeypatch.setattr(implementation, "_rc_fiber_request", forbidden)
    monkeypatch.setattr(s, "_validate_integrity_snapshot", forbidden)
    monkeypatch.setattr(s, "_checkpoint_for_row", forbidden)
    assert current(s, job)["state"] == "paused"


@pytest.mark.parametrize("version", ["v3", "v6", "v7"])
@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_both_workers_unwind_pending_boundary_without_failure_or_numerics(
    tmp_path, monkeypatch, version, action
):
    from . import test_rc_corotational_job_contract as pure
    from structural_analysis.execution.job_worker import execute_job_claim
    from structural_analysis.api import rc_corotational_control as coro
    from structural_analysis.execution import rc_corotational_phase_supervisor
    from structural_analysis.execution import rc_fiber_phase_supervisor

    def forbidden(*args, **kwargs):
        pytest.fail("Pending control before analysis cannot enter a numerical phase")

    monkeypatch.setattr(coro, "analyze_rc_corotational_control", forbidden)
    monkeypatch.setattr(coro, "validate_rc_corotational_control_artifacts", forbidden)
    monkeypatch.setattr(
        rc_corotational_phase_supervisor, "run_rc_corotational_phase", forbidden
    )
    monkeypatch.setattr(rc_fiber_phase_supervisor, "run_rc_fiber_phase", forbidden)
    s = seams.service(tmp_path)
    payload = (
        seams.request()
        if version == "v3"
        else pure.request()
        if version == "v6"
        else pure.isolated_request()
    )
    job = seams.submit(s, payload)
    c = seams.claim(s)
    post(s, job, action)
    stopped = execute_job_claim(
        s, c, worker_id="worker-a", authorization_token=seams.WORKER
    )
    assert stopped.status == ("queued" if action == "pause" else "cancelled")
    assert stopped.error_code == (None if action == "pause" else "cancelled_by_tenant")
    assert current(s, job)["last_command"]["boundary"] == "before_analysis"
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 0


@pytest.mark.parametrize("winner", ["control", "analysis"])
def test_atomic_analysis_reservation_and_control_race(tmp_path, monkeypatch, winner):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    pause = command(s, job, "pause")
    entered, release = Event(), Event()
    original = s._transition
    event = (
        "rc_control_requested" if winner == "control" else "execution_attempt_reserved"
    )

    def held(*args, **kwargs):
        row = original(*args, **kwargs)
        if kwargs["event_type"] == event:
            entered.set()
            assert release.wait(5)
        return row

    monkeypatch.setattr(s, "_transition", held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        if winner == "control":
            first = pool.submit(
                s.submit_rc_control, job.job_id, pause, **seams.tenant()
            )
            assert entered.wait(5)
            second = pool.submit(reserve, s, c)
        else:
            first = pool.submit(reserve, s, c)
            assert entered.wait(5)
            second = pool.submit(
                s.submit_rc_control, job.job_id, pause, **seams.tenant()
            )
        release.set()
        a, b = first.result(5), second.result(5)
    if winner == "control":
        assert a["view"]["state"] == "pause_pending"
        assert isinstance(b, JobView) and b.status == "queued"
        assert (
            seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 0
        )
    else:
        assert a == 1 and b["view"]["state"] == "pause_pending"
        seams.record(s, c, 1, seams.outcome(c))
        with pytest.raises(JobServiceError, match="rc_control_verification_required"):
            reserve(s, c)
        assert reserve(s, c, "verification", 1) == 2


def test_checkpoint_hold_is_atomic_against_competing_claim(tmp_path, monkeypatch):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    checkpoint, *_ = seams.synthetic_admission_artifacts(s, c, monkeypatch)
    post(s, job, "pause")
    entered, release = Event(), Event()
    original = s._transition

    def held(*args, **kwargs):
        row = original(*args, **kwargs)
        if kwargs["event_type"] == "checkpoint_committed":
            entered.set()
            assert release.wait(5)
        return row

    monkeypatch.setattr(s, "_transition", held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(seams.save_synthetic_checkpoint, s, c, checkpoint)
        assert entered.wait(5)
        waiting = pool.submit(
            s.claim_next, worker_id="worker-b", authorization_token=seams.WORKER_B
        )
        release.set()
        assert publication.result(5).status == "checkpointed"
        assert waiting.result(5) is None
    assert current(s, job)["state"] == "paused"


def test_final_cancel_preserves_prior_checkpoint_and_unknown_ordinal(
    tmp_path, monkeypatch
):
    s = seams.service(tmp_path)
    job = seams.submit(s)
    c = seams.claim(s)
    c, checkpoint, _, _, raw, _, proof = seams.prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    before = seams.request_blob_inventory(tmp_path)
    post(s, job, "cancel")
    cancelled = s.complete_job(
        job.job_id,
        **seams.lease(c),
        result_bytes=raw,
        result_media_type="application/json",
        evidence=proof,
    )
    assert cancelled.checkpoint.content_hash == seams.sha(checkpoint)
    assert (
        cancelled.progress_completed == 1
        and cancelled.result is None
        and cancelled.evidence is None
    )
    assert seams.request_blob_inventory(tmp_path) == before
    records = seams.evidence(s, job.job_id)
    assert records["execution_budget"]["reserved_attempts"] == 3
    assert records["pending_ordinals"] == [3]


def test_expiry_during_final_validation_does_not_resolve_verified_final(
    tmp_path, monkeypatch
):
    clock = seams.Clock()
    s = seams.service(tmp_path, clock)
    job = seams.submit(s)
    c = seams.claim(s)
    _, _, raw, report, proof = seams.synthetic_admission_artifacts(s, c, monkeypatch)
    post(s, job, "cancel")

    def expires(*args, **kwargs):
        clock.advance()
        return report

    monkeypatch.setattr(seams.contract, "validate_rc_fiber_job_result", expires)
    with pytest.raises(JobServiceError, match="lease_expired"):
        s.complete_job(
            job.job_id,
            **seams.lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=proof,
        )
    assert current(s, job)["state"] == "cancel_pending"
    assert s.claim_next(worker_id="worker-a", authorization_token=seams.WORKER) is None
    assert current(s, job)["last_command"]["boundary"] == "lease_expired"


@pytest.mark.parametrize("action", ["pause", "cancel"])
@pytest.mark.parametrize("request_during", ["analysis", "verification"])
def test_running_coro_worker_keeps_mandatory_verification_with_pending_intent(
    tmp_path, monkeypatch, action, request_during
):
    from . import test_rc_corotational_job_contract as pure
    from structural_analysis.execution.job_worker import execute_job_claim
    from structural_analysis.api import rc_corotational_control as api

    payload = pure.request()
    analysis, verification, native = pure.pair(payload)
    s = seams.service(tmp_path)
    job = seams.submit(s, payload)
    c = seams.claim(s)
    calls = []

    def intent(phase):
        calls.append(phase)
        if request_during == phase:
            assert post(s, job, action)["view"]["state"] == action + "_pending"
            # Pending intent is not lease loss, including during verification.
            assert s.heartbeat(job.job_id, **seams.lease(c)).status == "running"

    def analyze(*args, **kwargs):
        intent("analysis")
        return api.RCCorotationalControlArtifacts(
            seams.canonical(analysis["api_result"]), native
        )

    def verify(*args, **kwargs):
        intent("verification")
        return verification["verification_report"]

    monkeypatch.setattr(api, "analyze_rc_corotational_control", analyze)
    monkeypatch.setattr(api, "validate_rc_corotational_control_artifacts", verify)
    saved = execute_job_claim(
        s, c, worker_id="worker-a", authorization_token=seams.WORKER
    )
    assert calls == ["analysis", "verification"]
    assert saved.status == ("checkpointed" if action == "pause" else "cancelled")
    assert saved.progress_completed == 1 and saved.checkpoint is not None
    assert current(s, job)["last_command"]["boundary"] == "verified_checkpoint"
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 2
    assert s.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]


@pytest.mark.parametrize("legacy", [False, True])
def test_expiry_during_control_validation_cannot_apply_worker_boundary(
    tmp_path, monkeypatch, legacy
):
    clock = seams.Clock()
    s = seams.service(tmp_path, clock)
    job = seams.submit(s)
    c = seams.claim(s)
    post(s, job, "pause")
    original = s._rc_control_snapshot

    def expires(*args, **kwargs):
        result = original(*args, **kwargs)
        clock.advance()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(s, "_rc_control_snapshot", expires)
        with pytest.raises(JobServiceError, match="lease_expired"):
            seams.reserve(s, c) if legacy else reserve(s, c)
    assert current(s, job)["state"] == "pause_pending"
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 0
    assert s.claim_next(worker_id="worker-a", authorization_token=seams.WORKER) is None
    assert current(s, job)["last_command"]["boundary"] == "lease_expired"


@pytest.mark.parametrize("pause", [False, True])
def test_fixed_worker_pending_boundary_precedes_two_invocation_budget_gate(
    tmp_path, pause
):
    from structural_analysis.execution.job_worker import execute_job_claim
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        RCFiberDirectControlWorkerError,
    )

    s = seams.service(tmp_path)
    job = seams.submit(s, seams.request(maximum=2))
    first = seams.claim(s)
    assert seams.reserve(s, first) == 1  # Lost outcome is retained as unknown spend.
    s.fail_job(job.job_id, **seams.lease(first), error_code="synthetic_failure")
    s.resume_failed_job(
        job.job_id,
        **seams.tenant(),
        expected_request_hash=job.request.content_hash,
        expected_checkpoint_hash=None,
    )
    c = seams.claim(s)
    if pause:
        post(s, job, "pause")
        stopped = execute_job_claim(
            s, c, worker_id="worker-a", authorization_token=seams.WORKER
        )
        assert stopped.status == "queued" and stopped.error_code is None
        assert current(s, job)["state"] == "paused"
    else:
        with pytest.raises(
            RCFiberDirectControlWorkerError, match="execution_attempt_budget_exhausted"
        ) as caught:
            execute_job_claim(
                s, c, worker_id="worker-a", authorization_token=seams.WORKER
            )
        assert isinstance(caught.value.__cause__, JobServiceError)
        assert caught.value.__cause__.code == caught.value.code
        assert s.get_job(job.job_id, **seams.tenant()).status == "failed"
    assert seams.evidence(s, job.job_id)["execution_budget"]["reserved_attempts"] == 1
    assert seams.evidence(s, job.job_id)["pending_ordinals"] == [1]
