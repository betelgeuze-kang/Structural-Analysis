"""Real tiny RC continuation plus explicit synthetic worker-failure contracts.

The shared fixture performs four analysis calls and four mandatory fresh-source
verifications. Prefix replay makes those eight API invocations eighteen core
target calls. Transport failure tests reuse those retained bytes; their stubs
are not numerical nonconvergence or independent physical evidence.
"""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import Event

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.execution import job_worker as dispatcher
from structural_analysis.execution import rc_fiber_direct_control_worker as worker
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import DurableJobService, JobServiceError


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
TARGETS = (-1.0e-6, -2.0e-6, -1.5e-6)
TENANT_AUTH = {
    "tenant_id": "tenant",
    "authorization_token": "rc-durable-tenant-token-0123456789",
}
WORKER_AUTH = {
    "worker_id": "worker",
    "authorization_token": "rc-durable-worker-token-0123456789",
}


def _bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def _service(directory, clock=None):
    return DurableJobService(
        directory,
        tenant_tokens={"tenant": TENANT_AUTH["authorization_token"]},
        worker_tokens={"worker": WORKER_AUTH["authorization_token"]},
        worker_tenants={"worker": {"tenant"}},
        clock=clock or Clock(),
    )


def _request(*, chunk_size=1, maximum_invocations=16):
    return {
        "schema_version": "structural-analysis-job-request.v3",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "tiny-rc-reversal",
        "model": json.loads(MODEL.read_bytes()),
        "config": BoundedRCFiberDirectControlRequest(
            7, TARGETS, allow_reversals=True, maximum_reversals=1
        ).to_dict(),
        # A caller declaration; this fixture does not attest a Git revision.
        "source_revision": "a" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {
            "chunk_target_count": chunk_size,
            "maximum_api_invocations": maximum_invocations,
        },
    }


def _submit(service, request=None):
    return service.submit_job(
        **TENANT_AUTH, idempotency_key="tiny-rc", request=request or _request()
    )


def _claim(service):
    claim = service.claim_next(**WORKER_AUTH, lease_seconds=300)
    assert claim is not None
    return claim


def _run(service, claim, **kwargs):
    return worker.execute_rc_fiber_direct_control_claim(
        service, claim, **WORKER_AUTH, **kwargs
    )


def _credentials(claim):
    return WORKER_AUTH | {"lease_token": claim.lease_token}


def _evidence(service, job_id, **auth):
    envelope = service.read_rc_invocation_evidence(job_id, **auth)
    assert envelope["execution_budget_unit"] == "reserved_api_invocations"
    records = []
    for reference in envelope["invocations"]:
        raw = service.read_rc_invocation_artifact(
            job_id, **auth, ordinal=reference["ordinal"]
        )
        assert len(raw) == reference["byte_length"]
        assert _sha(raw) == reference["content_hash"]
        records.append({"ordinal": reference["ordinal"], "outcome": json.loads(raw)})
    return envelope | {"records": records}


def _native(payload):
    return base64.b64decode(
        payload["terminal_checkpoint_artifact_base64"], validate=True
    )


def _forbid_numerics(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("this transport regression must not enter the RC solver")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )


@pytest.fixture(scope="module")
def actual_runs():
    """One shared actual fixture, with optional explicit retained-byte reuse."""
    retained = os.environ.get("STRUCTURAL_RC_DURABLE_WORKER_RETAINED")
    if retained:
        original_directory = Path(retained)
        summary = json.loads((original_directory / "fixture.json").read_bytes())
        assert summary["model_sha256"] == _sha(MODEL.read_bytes())
        assert summary["original_api_calls"] == 4
        assert summary["fresh_verification_calls"] == 4
        assert summary["core_target_calls"] == 18
        # A service constructor may initialize SQLite metadata. Open only a
        # fresh copy so subsequent regressions never write into retained proof.
        directory = (
            Path(tempfile.mkdtemp(prefix="structural-rc-worker-reuse-")) / "copy"
        )
        shutil.copytree(original_directory, directory)
        print(
            f"Reusing original RC worker artifacts without numerical calls: {original_directory}; working copy: {directory}"
        )
        return directory, summary

    directory = Path(tempfile.mkdtemp(prefix="structural-rc-durable-worker-"))
    print(f"Original RC durable-worker development artifacts: {directory}", flush=True)
    (directory / "model.json").write_bytes(MODEL.read_bytes())
    counts = {
        "original_api_calls": 0,
        "fresh_verification_calls": 0,
        "core_target_calls": 0,
    }
    numerical_calls = []
    original_analyze = api.analyze_bounded_rc_fiber_direct_control
    original_verify = api.validate_bounded_rc_fiber_direct_control_artifacts
    original_step = paths.solve_stateful_fiber_frame2d_displacement_control_step
    phase = "analysis"
    current_chunk = None
    chunk_rows = []

    def observed_step(*args, **kwargs):
        counts["core_target_calls"] += 1
        numerical_calls.append(
            {"phase": phase, "target_m": kwargs["target_control_displacement_m"]}
        )
        return original_step(*args, **kwargs)

    def observed_analyze(*args, **kwargs):
        if phase == "analysis":
            counts["original_api_calls"] += 1
        value = original_analyze(*args, **kwargs)
        if phase == "analysis":
            raw = value.result_artifact_bytes()
            (current_chunk / "api-result.json").write_bytes(raw)
            (current_chunk / "native-checkpoint.json").write_bytes(
                value.checkpoint_artifact_bytes()
            )
        return value

    def observed_verify(*args, **kwargs):
        nonlocal phase
        counts["fresh_verification_calls"] += 1
        phase = "verification"
        try:
            value = original_verify(*args, **kwargs)
            (current_chunk / "verification.json").write_bytes(_bytes(value.to_dict()))
            return value
        finally:
            phase = "analysis"

    summary = {"model_sha256": _sha(MODEL.read_bytes()), "chunks": chunk_rows}
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                api, "analyze_bounded_rc_fiber_direct_control", observed_analyze
            )
            patch.setattr(
                api,
                "validate_bounded_rc_fiber_direct_control_artifacts",
                observed_verify,
            )
            patch.setattr(
                paths,
                "solve_stateful_fiber_frame2d_displacement_control_step",
                observed_step,
            )
            for name, chunk_size, claim_count in (("full", 3, 1), ("split", 1, 3)):
                store = directory / f"{name}-store"
                service = _service(store)
                request = _request(chunk_size=chunk_size)
                job = _submit(service, request)
                summary[name] = {"job_id": job.job_id, "request": request}
                for index in range(claim_count):
                    service = _service(store)
                    claim = _claim(service)
                    current_chunk = directory / f"{name}-chunk-{index + 1}"
                    current_chunk.mkdir()
                    (current_chunk / "request.json").write_bytes(claim.request_bytes)
                    if claim.checkpoint_bytes is not None:
                        (current_chunk / "input-job-checkpoint.json").write_bytes(
                            claim.checkpoint_bytes
                        )
                    job = dispatcher.execute_job_claim(service, claim, **WORKER_AUTH)
                    (current_chunk / "job.json").write_bytes(_bytes(job.to_dict()))
                    chunk_rows.append(
                        {
                            "name": name,
                            "index": index,
                            "status": job.status,
                            "directory": current_chunk.name,
                        }
                    )
                    if index + 1 < claim_count:
                        assert job.status == "checkpointed"
                        assert job.progress_completed == index + 1
                        assert job.lease_expires_at is None
                        if index == 0:
                            shutil.copytree(store, directory / "prefix-store")
                    else:
                        assert job.status == "succeeded"
                        (directory / f"{name}-result.json").write_bytes(
                            service.read_result(job.job_id, **TENANT_AUTH)
                        )
                    assert service.validate_integrity(job.job_id, **TENANT_AUTH)[
                        "contract_pass"
                    ]
        assert counts == {
            "original_api_calls": 4,
            "fresh_verification_calls": 4,
            "core_target_calls": 18,
        }
        return directory, summary | counts
    finally:
        summary.update(counts)
        summary["numerical_calls"] = numerical_calls
        summary["scope"] = (
            "development correctness; instrumentation/storage included; not performance or independent physical validation"
        )
        (directory / "fixture.json").write_bytes(_bytes(summary))


def _prefix(actual_runs, tmp_path, clock=None):
    directory, summary = actual_runs
    shutil.copytree(directory / "prefix-store", tmp_path / "service")
    service = _service(tmp_path / "service", clock)
    claim = _claim(service)
    assert claim.job.job_id == summary["split"]["job_id"]
    assert claim.job.progress_completed == 1
    return service, claim


def _saved_call(actual_runs, *, chunk=2):
    directory, _summary = actual_runs
    source = directory / f"split-chunk-{chunk}"
    result = api.BoundedRCFiberDirectControlResult(
        (source / "api-result.json").read_bytes(),
        (source / "native-checkpoint.json").read_bytes(),
    )
    report = api.BoundedRCFiberDirectControlValidationReport(
        (source / "verification.json").read_bytes()
    )
    return result, report


def _stub_saved_calls(actual_runs, monkeypatch, claim, *, report_mutation=None):
    """Replay saved return values at the API boundary, with no new numerical work."""
    result, report = _saved_call(actual_runs)
    calls = []
    expected_restart = _native(json.loads(claim.checkpoint_bytes))

    def analyze(_model, targets, **kwargs):
        assert targets == (TARGETS[1],)
        assert kwargs["restart"] == expected_restart
        calls.append("analysis")
        return result

    def verify(_model, targets, **kwargs):
        assert targets == (TARGETS[1],)
        assert kwargs["restart"] == expected_restart
        assert kwargs["result"] == result.result_artifact_bytes()
        assert kwargs["checkpoint"] == result.checkpoint_artifact_bytes()
        calls.append("verification")
        payload = report.to_dict()
        if report_mutation is not None:
            report_mutation(payload)
        return api.BoundedRCFiberDirectControlValidationReport(_bytes(payload))

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", analyze)
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", verify
    )
    _forbid_numerics(monkeypatch)
    return calls


def test_real_reopened_chunks_preserve_exact_cumulative_response_and_checkpoint(
    actual_runs,
):
    directory, summary = actual_runs
    full = json.loads((directory / "full-result.json").read_bytes())
    split = json.loads((directory / "split-result.json").read_bytes())
    assert _native(full) == _native(split)
    full_api = json.loads((directory / "full-chunk-1/api-result.json").read_bytes())
    split_api = json.loads((directory / "split-chunk-3/api-result.json").read_bytes())
    for field in (
        "response_history",
        "terminal_response",
        "checkpoint",
        "model",
        "claims",
    ):
        assert _bytes(full_api[field]) == _bytes(split_api[field])
    assert len(full_api["response_history"]) == len(TARGETS)
    # Request/restart and per-invocation work remain distinct, not hidden in a
    # misleading claim of equality of whole API result bytes.
    assert full_api["request"] != split_api["request"]
    assert summary["original_api_calls"] == summary["fresh_verification_calls"] == 4
    assert summary["core_target_calls"] == 18


def test_actual_reserved_invocations_retain_analysis_and_fresh_verification(
    actual_runs,
):
    directory, summary = actual_runs
    for name, invocation_count in (("full", 2), ("split", 6)):
        service = _service(directory / f"{name}-store")
        job_id = summary[name]["job_id"]
        evidence = _evidence(service, job_id, **TENANT_AUTH)
        assert len(evidence["records"]) == invocation_count
        assert evidence["pending_ordinals"] == []
        assert [row["ordinal"] for row in evidence["records"]] == list(
            range(1, invocation_count + 1)
        )
        for index, record in enumerate(evidence["records"]):
            outcome = record["outcome"]
            assert outcome["phase"] == (
                "analysis" if index % 2 == 0 else "verification"
            )
            assert outcome["status"] == "returned"
            assert outcome["unavailable_execution_work"] is False
            assert all(
                type(value) is int and value >= 0
                for value in outcome["timing"].values()
            )
            if outcome["phase"] == "analysis":
                assert outcome["api_result"]["status"] == "ready"
                assert outcome["checkpoint_artifact_base64"] is not None
                assert outcome["verification_report"] is None
            else:
                report = outcome["verification_report"]
                assert report["fresh_source_execution_invoked"] is True
                assert report["solver_replay_performed"] is True
                assert report["artifact_contract_pass"] is True
                assert outcome["api_result"] is None


@pytest.mark.parametrize(
    "field",
    (
        "artifact_contract_pass",
        "contract_pass",
        "physical_path_complete",
        "fresh_source_execution_invoked",
        "solver_replay_performed",
    ),
)
def test_mandatory_verification_rejection_preserves_prefix(
    actual_runs, tmp_path, monkeypatch, field
):
    service, claim = _prefix(actual_runs, tmp_path)
    calls = _stub_saved_calls(
        actual_runs,
        monkeypatch,
        claim,
        report_mutation=lambda value: value.update({field: False}),
    )
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError,
        match="rc_fiber_worker_verification_failed",
    ):
        _run(service, claim)
    assert calls == ["analysis", "verification"]
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed"
    assert failed.progress_completed == 1
    assert failed.checkpoint == claim.job.checkpoint
    assert failed.result is failed.evidence is None
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    assert len(evidence["records"]) == 4
    assert evidence["records"][-1]["outcome"]["verification_report"][field] is False


@pytest.mark.parametrize(
    "field", ("request_bytes", "checkpoint_bytes", "progress_completed", "attempt")
)
def test_forged_claim_fails_before_reserving_or_calling_api(
    actual_runs, tmp_path, monkeypatch, field
):
    service, claim = _prefix(actual_runs, tmp_path)
    _forbid_numerics(monkeypatch)
    if field.endswith("bytes"):
        forged = replace(claim, **{field: getattr(claim, field) + b" "})
    else:
        forged = replace(
            claim, job=replace(claim.job, **{field: getattr(claim.job, field) + 1})
        )
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError, match="rc_fiber_worker_contract_invalid"
    ):
        _run(service, forged)
    evidence = _evidence(service, claim.job.job_id, **TENANT_AUTH)
    assert len(evidence["records"]) == 2
    assert evidence["pending_ordinals"] == []


@pytest.mark.parametrize("budget", (True, 0, 256, 2))
def test_dispatch_budget_cannot_change_immutable_chunk(
    actual_runs, tmp_path, monkeypatch, budget
):
    service, claim = _prefix(actual_runs, tmp_path)
    _forbid_numerics(monkeypatch)
    with pytest.raises(worker.RCFiberDirectControlWorkerError):
        _run(service, claim, checkpoint_target_budget=budget)
    evidence = _evidence(service, claim.job.job_id, **TENANT_AUTH)
    assert len(evidence["records"]) == 2
    assert evidence["pending_ordinals"] == []


def test_recorded_exception_retains_unknown_work_and_last_checkpoint(
    actual_runs, tmp_path, monkeypatch
):
    service, claim = _prefix(actual_runs, tmp_path)
    _forbid_numerics(monkeypatch)

    def interrupted(*_args, **_kwargs):
        assert (
            service.read_execution_budget(claim.job.job_id, **_credentials(claim))[
                "reserved_attempts"
            ]
            == 3
        )
        raise RuntimeError(
            "synthetic API-boundary failure; not a numerical observation"
        )

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", interrupted)
    with pytest.raises(RuntimeError, match="synthetic API-boundary"):
        _run(service, claim)
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed"
    assert failed.checkpoint == claim.job.checkpoint
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    outcome = evidence["records"][-1]["outcome"]
    assert outcome["status"] == "raised"
    assert outcome["error"]["type"] == "RuntimeError"
    assert outcome["unavailable_execution_work"] is True
    assert evidence["pending_ordinals"] == []


def test_crash_reservation_stays_unknown_and_exhaustion_cannot_retry_api(
    tmp_path, monkeypatch
):
    clock = Clock()
    service = _service(tmp_path / "service", clock)
    job = _submit(service, _request(maximum_invocations=2))
    claim = _claim(service)
    calls = []
    _forbid_numerics(monkeypatch)

    def crash(*_args, **_kwargs):
        calls.append(True)
        assert (
            service.read_execution_budget(job.job_id, **_credentials(claim))[
                "reserved_attempts"
            ]
            == 1
        )
        raise KeyboardInterrupt("synthetic process death after reservation")

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", crash)
    with pytest.raises(KeyboardInterrupt):
        _run(service, claim)
    evidence = _evidence(service, job.job_id, **TENANT_AUTH)
    assert evidence["records"] == []
    assert evidence["pending_ordinals"] == [1]
    clock.advance(301)
    restarted = _service(tmp_path / "service", clock)
    retry = _claim(restarted)
    assert retry.job.attempt == 2
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError,
        match="execution_attempt_budget_exhausted",
    ):
        _run(restarted, retry)
    assert len(calls) == 1
    final = restarted.get_job(job.job_id, **TENANT_AUTH)
    assert final.status == "failed"
    assert final.result is final.checkpoint is None
    assert _evidence(restarted, job.job_id, **TENANT_AUTH)["pending_ordinals"] == [1]


def test_stale_claim_does_not_mutate_replacement_lease(
    actual_runs, tmp_path, monkeypatch
):
    service, stale = _prefix(actual_runs, tmp_path)
    service.fail_job(
        stale.job.job_id,
        **_credentials(stale),
        error_code="synthetic_retriable",
        retriable=True,
    )
    current = _claim(service)
    _forbid_numerics(monkeypatch)
    with pytest.raises(JobServiceError, match="lease_unauthorized"):
        _run(service, stale)
    job = service.get_job(stale.job.job_id, **TENANT_AUTH)
    assert job.status == "running"
    assert job.revision == current.job.revision
    assert (
        service.read_execution_budget(job.job_id, **_credentials(current))[
            "reserved_attempts"
        ]
        == 2
    )


def test_cancel_between_chunks_never_enters_next_api(
    actual_runs, tmp_path, monkeypatch
):
    directory, summary = actual_runs
    shutil.copytree(directory / "prefix-store", tmp_path / "service")
    service = _service(tmp_path / "service")
    job_id = summary["split"]["job_id"]
    _forbid_numerics(monkeypatch)
    cancelled = service.cancel_job(job_id, **TENANT_AUTH)
    assert cancelled.status == "cancelled"
    assert cancelled.progress_completed == 1
    assert cancelled.checkpoint is not None
    assert service.claim_next(**WORKER_AUTH, lease_seconds=300) is None
    assert len(_evidence(service, job_id, **TENANT_AUTH)["records"]) == 2


def test_running_cancellation_is_rejected_without_losing_lease(actual_runs, tmp_path):
    service, claim = _prefix(actual_runs, tmp_path)
    with pytest.raises(JobServiceError, match="cancel_state_invalid"):
        service.cancel_job(claim.job.job_id, **TENANT_AUTH)
    assert (
        service.read_execution_budget(claim.job.job_id, **_credentials(claim))[
            "reserved_attempts"
        ]
        == 2
    )


def test_synthetic_blocked_suffix_is_still_verified_and_preserves_prefix(
    actual_runs, tmp_path, monkeypatch
):
    """A worker branch test; the fabricated failure is not physical evidence."""
    service, claim = _prefix(actual_runs, tmp_path)
    ready, _report = _saved_call(actual_runs)
    payload = ready.to_dict()
    payload.update(status="blocked", contract_pass=False)
    payload["result_hash"] = _sha(
        _bytes({key: value for key, value in payload.items() if key != "result_hash"})
    )
    blocked = api.BoundedRCFiberDirectControlResult(
        _bytes(payload), ready.checkpoint_artifact_bytes()
    )
    calls = []

    def analyze(*_args, **_kwargs):
        assert (
            service.read_execution_budget(claim.job.job_id, **_credentials(claim))[
                "reserved_attempts"
            ]
            == 3
        )
        calls.append("analysis")
        return blocked

    def verify(*_args, **kwargs):
        assert kwargs["result"] == blocked.result_artifact_bytes()
        assert kwargs["checkpoint"] == blocked.checkpoint_artifact_bytes()
        assert (
            service.read_execution_budget(claim.job.job_id, **_credentials(claim))[
                "reserved_attempts"
            ]
            == 4
        )
        calls.append("verification")
        report = _report.to_dict()
        report.update(
            contract_pass=False,
            physical_path_complete=False,
            verified_result_hash=blocked.result_hash,
        )
        return api.BoundedRCFiberDirectControlValidationReport(_bytes(report))

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", analyze)
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", verify
    )
    _forbid_numerics(monkeypatch)
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError, match="rc_fiber_worker_chunk_blocked"
    ):
        _run(service, claim)
    assert calls == ["analysis", "verification"]
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed"
    assert failed.progress_completed == 1
    assert failed.checkpoint == claim.job.checkpoint
    assert failed.result is failed.evidence is None
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    assert evidence["execution_budget"]["reserved_attempts"] == 4
    assert evidence["pending_ordinals"] == []
    assert evidence["records"][-2]["outcome"]["api_result"]["status"] == "blocked"
    assert (
        evidence["records"][-1]["outcome"]["verification_report"][
            "artifact_contract_pass"
        ]
        is True
    )


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_lease_expiry_after_computation_cannot_publish_or_erase_prefix(
    actual_runs, tmp_path, monkeypatch, phase
):
    clock = Clock()
    service, claim = _prefix(actual_runs, tmp_path, clock)
    calls = _stub_saved_calls(actual_runs, monkeypatch, claim)
    name = (
        "analyze_bounded_rc_fiber_direct_control"
        if phase == "analysis"
        else "validate_bounded_rc_fiber_direct_control_artifacts"
    )
    original = getattr(api, name)

    def expires_after_return(*args, **kwargs):
        value = original(*args, **kwargs)
        clock.advance(301)
        return value

    monkeypatch.setattr(api, name, expires_after_return)
    with pytest.raises(JobServiceError, match="lease_expired"):
        _run(service, claim)
    assert calls == (
        ["analysis"] if phase == "analysis" else ["analysis", "verification"]
    )
    evidence = _evidence(service, claim.job.job_id, **TENANT_AUTH)
    # Unrecordable completion remains unknown instead of becoming zero work.
    assert evidence["pending_ordinals"] == [3 if phase == "analysis" else 4]
    current = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert current.checkpoint == claim.job.checkpoint
    assert current.progress_completed == 1
    assert current.result is current.evidence is None
    successor = _claim(service)
    assert successor.job.attempt == claim.job.attempt + 1
    assert successor.checkpoint_bytes == claim.checkpoint_bytes


def test_lease_keeper_renews_while_api_is_in_flight(actual_runs, tmp_path, monkeypatch):
    service, claim = _prefix(actual_runs, tmp_path)
    calls = _stub_saved_calls(actual_runs, monkeypatch, claim)
    entered, renewed = Event(), Event()
    original_analyze = api.analyze_bounded_rc_fiber_direct_control
    original_heartbeat = service.heartbeat
    original_keeper_run = worker._LeaseKeeper._run

    def heartbeat(*args, **kwargs):
        value = original_heartbeat(*args, **kwargs)
        if entered.is_set():
            renewed.set()
        return value

    def prompt_keeper_run(self):
        # Accelerate only the wait schedule. The original keeper still performs
        # the real authenticated service heartbeat on its background thread.
        assert entered.wait(5)
        original_wait = self.stopped.wait
        first = True

        def first_tick(timeout):
            nonlocal first
            if first:
                first = False
                return False
            return original_wait(timeout)

        monkeypatch.setattr(self.stopped, "wait", first_tick)
        original_keeper_run(self)

    def analysis_waiting_for_renewal(*args, **kwargs):
        entered.set()
        assert renewed.wait(5), "no heartbeat while the API boundary was occupied"
        return original_analyze(*args, **kwargs)

    monkeypatch.setattr(service, "heartbeat", heartbeat)
    monkeypatch.setattr(worker._LeaseKeeper, "_run", prompt_keeper_run)
    monkeypatch.setattr(
        api, "analyze_bounded_rc_fiber_direct_control", analysis_waiting_for_renewal
    )
    advanced = _run(service, claim)
    assert calls == ["analysis", "verification"]
    assert renewed.is_set()
    assert advanced.status == "checkpointed" and advanced.progress_completed == 2
    assert advanced.lease_expires_at is None


def test_actual_compact_receipts_do_not_duplicate_cumulative_api_history(actual_runs):
    directory, summary = actual_runs
    total_core = 0
    for name, reserved in (("full", 2), ("split", 6)):
        payload = json.loads((directory / f"{name}-result.json").read_bytes())
        assert payload["execution_budget_unit"] == "reserved_api_invocations"
        assert payload["execution_budget"]["reserved_attempts"] == reserved
        assert payload["completed_target_count"] == 3
        assert payload["api_result"] == json.loads(
            (
                directory / f"{name}-chunk-{1 if name == 'full' else 3}/api-result.json"
            ).read_bytes()
        )
        assert all(
            "api_result" not in row and "response_history" not in row
            for row in payload["receipts"]
        )
        for receipt in payload["receipts"]:
            analysis = receipt["analysis_metrics"]["control_work"][
                "attempted_step_count"
            ]
            verification = receipt["verification_metrics"]["replay_control_work"][
                "attempted_step_count"
            ]
            assert analysis == verification == receipt["completed_after"]
            total_core += analysis + verification
        service = _service(directory / f"{name}-store")
        evidence = _evidence(service, summary[name]["job_id"], **TENANT_AUTH)
        assert evidence["execution_budget"]["reserved_attempts"] == reserved
    assert total_core == summary["core_target_calls"] == 18
    for chunk in (2, 3):
        checkpoint = json.loads(
            (directory / f"split-chunk-{chunk}/input-job-checkpoint.json").read_bytes()
        )
        assert "api_result" not in checkpoint
        assert all("api_result" not in receipt for receipt in checkpoint["receipts"])


def test_actual_http_artifacts_match_original_result_and_invocation_bytes(actual_runs):
    directory, summary = actual_runs
    service = _service(directory / "split-store")
    job_id = summary["split"]["job_id"]
    http = DurableJobHttpApi(service)
    headers = {
        "Authorization": f"Bearer {TENANT_AUTH['authorization_token']}",
        "X-Structural-Tenant": "tenant",
    }
    for role, raw in (
        ("result", (directory / "split-result.json").read_bytes()),
        ("evidence", service.read_evidence(job_id, **TENANT_AUTH)),
    ):
        response = http.handle("GET", f"/v1/jobs/{job_id}/{role}", headers=headers)
        assert response.status == 200
        assert response.body == raw
    manifest = http.handle("GET", f"/v1/jobs/{job_id}/rc-invocations", headers=headers)
    assert manifest.status == 200
    evidence = json.loads(manifest.body)
    assert len(evidence["invocations"]) == 6
    for reference in evidence["invocations"]:
        response = http.handle(
            "GET",
            f"/v1/jobs/{job_id}/rc-invocations/{reference['ordinal']}",
            headers=headers,
        )
        assert response.status == 200
        assert _sha(response.body) == reference["content_hash"]
        assert len(response.body) == reference["byte_length"]
        assert response.body == service.read_rc_invocation_artifact(
            job_id, **TENANT_AUTH, ordinal=reference["ordinal"]
        )


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_typed_export_exception_retains_original_execution_metrics(
    actual_runs, tmp_path, monkeypatch, phase
):
    service, claim = _prefix(actual_runs, tmp_path)
    _stub_saved_calls(actual_runs, monkeypatch, claim)
    result, _report = _saved_call(actual_runs)
    export_error = api.BoundedRCFiberDirectControlArtifactError(
        "synthetic artifact export failure after accounted execution", result.to_dict()
    )

    def raised(*_args, **_kwargs):
        raise export_error

    name = (
        "analyze_bounded_rc_fiber_direct_control"
        if phase == "analysis"
        else "validate_bounded_rc_fiber_direct_control_artifacts"
    )
    monkeypatch.setattr(api, name, raised)
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError, match="rc_fiber_worker_contract_invalid"
    ):
        _run(service, claim)
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.checkpoint == claim.job.checkpoint
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    outcome = evidence["records"][-1]["outcome"]
    assert outcome["phase"] == phase and outcome["status"] == "raised"
    assert outcome["error"]["type"] == "BoundedRCFiberDirectControlArtifactError"
    assert outcome["error"]["report"] == export_error.to_dict()
    assert (
        outcome["error"]["report"]["execution_metrics"] == result.to_dict()["metrics"]
    )
    assert outcome["error"]["report"]["computed_path_status"] == "ready"
    assert outcome["error"]["report"]["state_or_restart_export_available"] is False
    assert outcome["unavailable_execution_work"] is True
    assert evidence["pending_ordinals"] == []


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_returned_unknown_work_is_recorded_and_cannot_publish(
    actual_runs, tmp_path, monkeypatch, phase
):
    service, claim = _prefix(actual_runs, tmp_path)
    result, report = _saved_call(actual_runs)
    payload, validation = result.to_dict(), report.to_dict()
    if phase == "analysis":
        payload["metrics"]["control_work"]["unknown_solver_work_attempt_count"] = 1
        payload["result_hash"] = _sha(
            _bytes(
                {key: value for key, value in payload.items() if key != "result_hash"}
            )
        )
        validation["verified_result_hash"] = payload["result_hash"]
    else:
        validation["replay_control_work"]["unknown_solver_work_attempt_count"] = 1
    unknown_result = api.BoundedRCFiberDirectControlResult(
        _bytes(payload), result.checkpoint_artifact_bytes()
    )
    monkeypatch.setattr(
        api,
        "analyze_bounded_rc_fiber_direct_control",
        lambda *_args, **_kwargs: unknown_result,
    )
    monkeypatch.setattr(
        api,
        "validate_bounded_rc_fiber_direct_control_artifacts",
        lambda *_args, **_kwargs: api.BoundedRCFiberDirectControlValidationReport(
            _bytes(validation)
        ),
    )
    _forbid_numerics(monkeypatch)
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError, match="rc_fiber_worker_contract_invalid"
    ):
        _run(service, claim)
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.checkpoint == claim.job.checkpoint
    assert failed.result is failed.evidence is None
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    assert (
        evidence["records"][-2 if phase == "analysis" else -1]["outcome"][
            "unavailable_execution_work"
        ]
        is True
    )
    assert evidence["pending_ordinals"] == []


def test_abandoned_reservation_survives_successful_retry_as_unknown_gap(
    actual_runs, tmp_path, monkeypatch
):
    clock = Clock()
    service, claim = _prefix(actual_runs, tmp_path, clock)
    _forbid_numerics(monkeypatch)

    def crash(*_args, **_kwargs):
        raise KeyboardInterrupt("synthetic crash after the third reservation")

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", crash)
    with pytest.raises(KeyboardInterrupt):
        _run(service, claim)
    clock.advance(301)
    current = _claim(service)
    _stub_saved_calls(actual_runs, monkeypatch, current)
    resumed = _run(service, current)
    assert resumed.status == "checkpointed" and resumed.progress_completed == 2
    evidence = _evidence(service, resumed.job_id, **TENANT_AUTH)
    assert evidence["pending_ordinals"] == [3]
    assert evidence["pending_execution_work"] == "unknown"
    assert evidence["execution_budget"]["reserved_attempts"] == 5
    assert [record["ordinal"] for record in evidence["records"]] == [1, 2, 4, 5]
    successor = _claim(service)
    checkpoint = json.loads(successor.checkpoint_bytes)
    assert checkpoint["receipts"][-1]["analysis_ordinal"] == 4
    assert checkpoint["receipts"][-1]["verification_ordinal"] == 5
    assert service.validate_integrity(resumed.job_id, **TENANT_AUTH)["contract_pass"]
