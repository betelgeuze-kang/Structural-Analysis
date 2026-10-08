"""RC durable authorization and artifact bookkeeping; never execute a solver."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution import rc_fiber_job_contract as contract
from structural_analysis.execution import job_service as implementation
from structural_analysis.execution import job_http_api as http
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
    build_job_completion_evidence,
)

TENANT = "rc-tenant-authorization-0123456789"
OTHER = "rc-other-authorization-0123456789"
WORKER = "rc-worker-authorization-0123456789"
WORKER_B = "rc-worker-b-authorization-0123456789"
RESUME = "sha256:" + "a" * 64


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds=6):
        self.value += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("RC service test must not execute analysis or numerical validation")

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(api, "run_stateful_fiber_frame2d_control_path", forbidden)


def service(root, clock=None):
    return DurableJobService(
        root,
        tenant_tokens={"a": TENANT, "b": OTHER},
        worker_tokens={"worker-a": WORKER, "worker-b": WORKER_B},
        worker_tenants={"worker-a": {"a"}, "worker-b": {"a", "b"}},
        clock=clock,
    )


def request(maximum=6):
    return {
        "schema_version": contract.RC_FIBER_JOB_REQUEST_SCHEMA_VERSION,
        "operation": contract.RC_FIBER_JOB_OPERATION,
        "case_id": "rc-service-test",
        "model": json.loads(
            Path(
                "examples/public_rc_fiber_frame_l_frame_material_history.json"
            ).read_bytes()
        ),
        "config": BoundedRCFiberDirectControlRequest(
            7, (-0.0001, -0.0002, -0.0003)
        ).to_dict(),
        "source_revision": "b" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {
            "chunk_target_count": 1,
            "maximum_api_invocations": maximum,
        },
    }


def submit(s, payload=None, key="case"):
    return s.submit_job(
        tenant_id="a",
        authorization_token=TENANT,
        idempotency_key=key,
        request=request() if payload is None else payload,
    )


def claim(s, worker="worker-a"):
    found = s.claim_next(
        worker_id=worker,
        authorization_token=WORKER if worker == "worker-a" else WORKER_B,
        lease_seconds=5,
    )
    assert found is not None
    return found


def lease(c, worker="worker-a"):
    return {
        "worker_id": worker,
        "authorization_token": WORKER if worker == "worker-a" else WORKER_B,
        "lease_token": c.lease_token,
    }


def tenant():
    return {"tenant_id": "a", "authorization_token": TENANT}


def reserve(s, c, worker="worker-a"):
    return s.reserve_execution_attempt(c.job.job_id, **lease(c, worker))


def outcome(c, phase="analysis", raised=False):
    payload = json.loads(c.request_bytes)
    _, typed = contract.validate_rc_fiber_job_request(payload)
    return {
        "schema_version": "bounded-rc-fiber-job-invocation.v1",
        "phase": phase,
        "status": "raised" if raised else "returned",
        "job_request_hash": c.job.request.content_hash,
        "chunk_request_hash": replace(
            typed, targets_m=typed.targets_m[:1]
        ).request_hash,
        "completed_before": 0,
        "completed_after": 1,
        "restart_input_sha256": None,
        "timing": {"wall_ns": 12, "process_cpu_ns": 7},
        "api_result": {
            "status": "blocked",
            "metrics": {"control_work": {"unknown_solver_work_attempt_count": 0}},
        }
        if phase == "analysis" and not raised
        else None,
        "checkpoint_artifact_base64": None,
        "verification_report": {
            "contract_pass": False,
            "replay_control_work": {"unknown_solver_work_attempt_count": 0},
        }
        if phase == "verification" and not raised
        else None,
        "error": {"type": "SyntheticError", "code": "synthetic_failure"}
        if raised
        else None,
        "unavailable_execution_work": raised,
    }


def record(s, c, ordinal, value, worker="worker-a"):
    return s.record_rc_invocation_outcome(
        c.job.job_id, **lease(c, worker), ordinal=ordinal, outcome=value
    )


def evidence(s, job):
    return s.read_rc_invocation_evidence(job, **tenant())


def test_v3_submission_freezes_source_targets_and_global_api_budget(tmp_path):
    s = service(tmp_path)
    payload = request()
    j = submit(s, payload)
    assert j == submit(s, deepcopy(payload))
    payload["config"]["targets_m"][0] = -0.00005
    with pytest.raises(JobServiceError, match="idempotency_conflict"):
        submit(s, payload)
    c = claim(s)
    assert json.loads(c.request_bytes) == request()
    assert c.job.progress_total == 3
    assert s.read_execution_budget(j.job_id, **lease(c)) == {
        "maximum_attempts": 6,
        "reserved_attempts": 0,
        "remaining_attempts": 6,
    }
    assert s.worker_result_byte_limit(j.job_id, **lease(c)) == 576 * 1024 * 1024
    assert s.validate_integrity(j.job_id, **tenant())["contract_pass"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_api_invocations", 1),
        ("maximum_api_invocations", True),
        ("maximum_api_invocations", 4097),
        ("chunk_target_count", 0),
        ("chunk_target_count", 256),
    ],
)
def test_execution_configuration_fails_closed(tmp_path, field, value):
    payload = request()
    payload["execution_config"][field] = value
    with pytest.raises(JobServiceError):
        submit(service(tmp_path), payload)


def test_outcomes_are_immutable_content_addressed_and_reopenable(tmp_path):
    s = service(tmp_path)
    j = submit(s)
    c = claim(s)
    assert reserve(s, c) == 1
    value = outcome(c)
    record(s, c, 1, value)
    record(s, c, 1, deepcopy(value))  # Exact retry creates no second event.
    observed = s.get_job(j.job_id, **tenant())
    changed = deepcopy(value)
    changed["timing"]["wall_ns"] += 1
    with pytest.raises(JobServiceError, match="rc_invocation_outcome_conflict"):
        record(s, c, 1, changed)
    value["api_result"]["status"] = "changed-after-record"
    reopened = service(tmp_path)
    records = reopened.read_rc_invocation_outcomes(j.job_id, **lease(c))
    assert records == [{"ordinal": 1, "outcome": outcome(c)}]
    assert reopened.get_job(j.job_id, **tenant()).revision == observed.revision
    report = evidence(reopened, j.job_id)
    assert report["pending_ordinals"] == []
    assert "api_result" not in report["invocations"][0]
    assert report["invocations"][0]["content_hash"] == sha(canonical(outcome(c)))
    assert reopened.read_rc_invocation_artifact(
        j.job_id, **tenant(), ordinal=1
    ) == canonical(outcome(c))
    integrity = reopened.validate_integrity(j.job_id, **tenant())
    assert integrity["rc_invocation_artifact_hashes"] == {
        "1": sha(canonical(outcome(c)))
    }


@pytest.mark.parametrize("worker", ["worker-a", "worker-b"])
def test_crash_gap_cannot_be_filled_by_new_attempt_even_same_worker(tmp_path, worker):
    clock = Clock()
    s = service(tmp_path, clock)
    j = submit(s)
    first = claim(s)
    reserve(s, first)
    clock.advance()
    second = claim(s, worker)
    with pytest.raises(
        JobServiceError, match="rc_invocation_reservation_lease_mismatch"
    ):
        record(s, second, 1, outcome(second), worker)
    assert reserve(s, second, worker) == 2
    record(s, second, 2, outcome(second, raised=True), worker)
    report = evidence(s, j.job_id)
    assert report["pending_ordinals"] == [1]
    assert report["pending_execution_work"] == "unknown"
    assert report["execution_budget"] == {
        "maximum_attempts": 6,
        "reserved_attempts": 2,
        "remaining_attempts": 4,
    }
    assert report["invocations"][0]["unavailable_execution_work"] is True
    assert s.validate_integrity(j.job_id, **tenant())["contract_pass"]


def test_fail_resume_keeps_outcomes_gaps_and_exhausted_api_budget(tmp_path):
    s = service(tmp_path)
    j = submit(s, request(2))
    c = claim(s)
    reserve(s, c)
    record(s, c, 1, outcome(c, raised=True))
    reserve(s, c)
    s.fail_job(j.job_id, **lease(c), error_code="synthetic_failure", retriable=False)
    s.resume_failed_job(
        j.job_id,
        **tenant(),
        expected_request_hash=j.request.content_hash,
        expected_checkpoint_hash=None,
    )
    next_claim = claim(s)
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        reserve(s, next_claim)
    assert evidence(s, j.job_id)["pending_ordinals"] == [2]
    assert len(s.read_rc_invocation_outcomes(j.job_id, **lease(next_claim))) == 1


def test_cancel_and_expired_lease_cannot_publish_new_outcome(tmp_path):
    clock = Clock()
    s = service(tmp_path, clock)
    j = submit(s)
    c = claim(s)
    reserve(s, c)
    clock.advance()
    with pytest.raises(JobServiceError, match="lease_expired"):
        record(s, c, 1, outcome(c))
    recovered = claim(s)
    s.fail_job(
        j.job_id, **lease(recovered), error_code="synthetic_requeue", retriable=True
    )
    s.cancel_job(j.job_id, **tenant())
    with pytest.raises(JobServiceError, match="lease_state_invalid"):
        record(s, c, 1, outcome(c))
    assert evidence(s, j.job_id)["pending_ordinals"] == [1]
    assert evidence(s, j.job_id)["invocations"] == []


def test_expiry_during_blob_fsync_leaves_no_published_outcome(tmp_path, monkeypatch):
    clock = Clock()
    s = service(tmp_path, clock)
    j = submit(s)
    c = claim(s)
    reserve(s, c)
    put = s._put_blob

    def expiring(*args, **kwargs):
        ref = put(*args, **kwargs)
        clock.advance()
        return ref

    monkeypatch.setattr(s, "_put_blob", expiring)
    with pytest.raises(JobServiceError, match="lease_expired"):
        record(s, c, 1, outcome(c))
    assert evidence(s, j.job_id)["pending_ordinals"] == [1]
    assert (
        s.validate_integrity(j.job_id, **tenant())["rc_invocation_artifact_hashes"]
        == {}
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "phase",
        "status",
        "request",
        "suffix",
        "progress",
        "restart",
        "timing",
        "unknown",
        "duplicated_result",
        "base64",
    ],
)
def test_outcome_input_shape_and_phase_are_bound(tmp_path, mutation):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    reserve(s, c)
    value = outcome(c)
    if mutation == "phase":
        value["phase"] = "oracle"
    elif mutation == "status":
        value["status"] = "assumed"
    elif mutation == "request":
        value["job_request_hash"] = RESUME
    elif mutation == "suffix":
        value["chunk_request_hash"] = RESUME
    elif mutation == "progress":
        value["completed_after"] = 2
    elif mutation == "restart":
        value["restart_input_sha256"] = RESUME
    elif mutation == "timing":
        value["timing"]["wall_ns"] = True
    elif mutation == "unknown":
        value["unavailable_execution_work"] = 0
    elif mutation == "duplicated_result":
        value["phase"] = "verification"
    else:
        value["checkpoint_artifact_base64"] = "broken base64"
    with pytest.raises(JobServiceError, match="rc_invocation_contract_invalid"):
        record(s, c, 1, value)
    assert evidence(s, c.job.job_id)["pending_ordinals"] == [1]


@pytest.mark.parametrize("ordinal", [0, True, 2, -1])
def test_outcome_requires_an_existing_reserved_ordinal(tmp_path, ordinal):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    reserve(s, c)
    with pytest.raises(JobServiceError, match="rc_invocation_reservation_missing"):
        record(s, c, ordinal, outcome(c))


@pytest.mark.parametrize(
    "mutation", ["blob", "table", "delete", "budget", "reservation", "metadata_type"]
)
def test_integrity_verifies_outcome_blobs_table_events_and_budget(tmp_path, mutation):
    s = service(tmp_path)
    j = submit(s)
    c = claim(s)
    reserve(s, c)
    record(s, c, 1, outcome(c))
    if mutation == "blob":
        s._blob_path(sha(canonical(outcome(c)))).write_bytes(b"corrupted")
    else:
        with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
            if mutation == "table":
                db.execute(
                    "UPDATE job_rc_invocation_outcomes SET outcome_hash = ?", (RESUME,)
                )
            elif mutation == "delete":
                db.execute("DELETE FROM job_rc_invocation_outcomes")
            elif mutation == "budget":
                db.execute("UPDATE job_execution_budgets SET reserved_attempts = 0")
            elif mutation == "metadata_type":
                metadata = json.loads(
                    db.execute(
                        "SELECT metadata_json FROM job_rc_invocation_outcomes"
                    ).fetchone()[0]
                )
                metadata["unavailable_execution_work"] = 0
                db.execute(
                    "UPDATE job_rc_invocation_outcomes SET metadata_json = ?",
                    (canonical(metadata).decode(),),
                )
            else:
                db.execute(
                    "UPDATE job_rc_invocation_outcomes SET reservation_event_hash = ?",
                    (RESUME,),
                )
    with pytest.raises(JobServiceError, match="integrity_failed"):
        s.validate_integrity(j.job_id, **tenant())


def test_http_tenant_summary_and_raw_outcome_keep_authorization_and_unknowns(tmp_path):
    s = service(tmp_path)
    j = submit(s)
    c = claim(s)
    reserve(s, c)
    reserve(s, c)
    record(s, c, 1, outcome(c, raised=True))
    app = http.DurableJobHttpApi(s)
    path = f"/v1/jobs/{j.job_id}/rc-invocations"
    headers = {"X-Structural-Tenant": "a", "Authorization": f"Bearer {TENANT}"}
    summary = app.handle("GET", path, headers=headers)
    assert summary.status == 200 and json.loads(summary.body)["pending_ordinals"] == [2]
    raw = app.handle("GET", path + "/1", headers=headers)
    assert raw.status == 200 and raw.body == canonical(outcome(c, raised=True))
    assert app.handle("GET", path + "/2", headers=headers).status == 404
    assert (
        app.handle(
            "GET",
            path,
            headers={"X-Structural-Tenant": "b", "Authorization": f"Bearer {OTHER}"},
        ).status
        == 404
    )
    assert (
        app.handle(
            "GET",
            path,
            headers={"X-Structural-Tenant": "a", "Authorization": "Bearer incorrect"},
        ).status
        == 401
    )
    assert app.handle("POST", path, headers=headers).status == 405
    assert (
        app.handle("GET", f"/v1/jobs/{j.job_id}/result/1", headers=headers).status
        == 404
    )
    with pytest.raises(JobServiceError, match="worker_unauthorized"):
        s.read_rc_invocation_outcomes(
            j.job_id,
            worker_id="worker-a",
            authorization_token="incorrect",
            lease_token=c.lease_token,
        )


def test_submit_http_and_wsgi_keep_16mib_body_limit(tmp_path):
    s = service(tmp_path)
    app = http.DurableJobHttpApi(s)
    assert (
        app.handle("POST", "/v1/jobs", body=b" " * (16 * 1024 * 1024 + 1)).status == 413
    )
    statuses = []
    list(
        http.DurableJobWSGIApplication(s)(
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/v1/jobs",
                "CONTENT_LENGTH": str(16 * 1024 * 1024 + 1),
                "wsgi.input": BytesIO(),
            },
            lambda status, headers: statuses.append(status),
        )
    )
    assert statuses == ["413 Request Entity Too Large"]


def synthetic_pair(s, c, recorded_change=None):
    """Synthetic pure-contract seam isolates service binding from numerical checks."""
    a = outcome(c)
    a["api_result"] = {
        "result_hash": RESUME,
        "metrics": {
            "control_work": {"unknown_solver_work_attempt_count": 0, "known_work": 1}
        },
        "request": {"bound": True},
        "model": {"bound": True},
        "control": {"dof": 7},
        "path": {"path_hash": RESUME, "final_checkpoint": {"state_hash": RESUME}},
    }
    a["checkpoint_artifact_base64"] = base64.b64encode(b"synthetic-checkpoint").decode()
    v = outcome(c, "verification")
    v["verification_report"] = {
        "contract_pass": True,
        "artifact_contract_pass": True,
        "replay_control_work": {
            "unknown_solver_work_attempt_count": 0,
            "known_work": 1,
        },
        "response_reassembly_attempts": 1,
        "response_reassembly_verified_count": 1,
    }
    recorded_a, recorded_v = deepcopy(a), deepcopy(v)
    if recorded_change == "verification_flag_integer":
        recorded_v["verification_report"]["artifact_contract_pass"] = 1
    elif recorded_change == "verification_work_float":
        recorded_v["verification_report"]["replay_control_work"]["known_work"] = 1.0
    elif recorded_change == "analysis_work_float":
        recorded_a["api_result"]["metrics"]["control_work"]["known_work"] = 1.0
    reserve(s, c)
    record(s, c, 1, recorded_a)
    reserve(s, c)
    record(s, c, 2, recorded_v)
    receipt = {
        key: a[key]
        for key in [
            "job_request_hash",
            "chunk_request_hash",
            "completed_before",
            "completed_after",
            "restart_input_sha256",
        ]
    }
    receipt.update(
        {
            "analysis_ordinal": 1,
            "verification_ordinal": 2,
            "analysis_timing": a["timing"],
            "verification_timing": v["timing"],
            "analysis_metrics": a["api_result"]["metrics"],
            "verification_metrics": {
                key: v["verification_report"][key]
                for key in [
                    "replay_control_work",
                    "response_reassembly_attempts",
                    "response_reassembly_verified_count",
                ]
            },
            "validation_report": v["verification_report"],
            "result_hash": RESUME,
            "result_artifact_sha256": sha(canonical(a["api_result"])),
            "checkpoint_sha256": sha(b"synthetic-checkpoint"),
            "checkpoint_byte_length": len(b"synthetic-checkpoint"),
            "api_request": a["api_result"]["request"],
            "model_binding": a["api_result"]["model"],
            "control": a["api_result"]["control"],
            "path_hash": RESUME,
            "checkpoint_state_hash": RESUME,
        }
    )
    return receipt


@pytest.mark.parametrize(
    "changed",
    [
        "verification_flag_integer",
        "verification_work_float",
        "analysis_work_float",
        "analysis_timing_float",
        "verification_timing_float",
        "api_request_integer",
        "completed_after_float",
        "checkpoint_length_float",
    ],
)
def test_checkpoint_crossbindings_preserve_exact_json_types(
    tmp_path, monkeypatch, changed
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    receipt = synthetic_pair(s, c, recorded_change=changed)
    if changed == "analysis_work_float":
        # Bind the raw result hash exactly so the metric comparison itself is tested.
        stored = s.read_rc_invocation_outcomes(c.job.job_id, **lease(c))[0]["outcome"]
        receipt["result_artifact_sha256"] = sha(canonical(stored["api_result"]))
    elif changed.endswith("timing_float"):
        receipt[changed.removesuffix("_float")]["wall_ns"] = 12.0
    elif changed == "api_request_integer":
        receipt["api_request"]["bound"] = 1
    elif changed == "completed_after_float":
        receipt["completed_after"] = 1.0
    elif changed == "checkpoint_length_float":
        receipt["checkpoint_byte_length"] = float(receipt["checkpoint_byte_length"])
    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_checkpoint",
        lambda raw, **kwargs: json.loads(raw),
    )
    with pytest.raises(JobServiceError, match="rc_fiber_checkpoint_contract_invalid"):
        s.save_checkpoint(
            c.job.job_id,
            **lease(c),
            checkpoint_bytes=canonical(
                {"resume_contract_hash": RESUME, "receipts": [receipt]}
            ),
            checkpoint_media_type="application/json",
            progress_completed=1,
            progress_total=3,
            resume_contract_hash=RESUME,
        )
    assert s.get_job(c.job.job_id, **tenant()).checkpoint is None


@pytest.mark.parametrize(
    "changed",
    [
        None,
        "analysis_ordinal",
        "verification_ordinal",
        "job_request_hash",
        "chunk_request_hash",
        "result_hash",
        "path_hash",
        "checkpoint_state_hash",
        "analysis_timing",
        "validation_report",
        "checkpoint_sha256",
    ],
)
def test_checkpoint_requires_exact_recorded_outcomes_even_if_pure_receipt_attests_pass(
    tmp_path, monkeypatch, changed
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    receipt = synthetic_pair(s, c)
    if changed:
        receipt[changed] = (
            2
            if changed == "analysis_ordinal"
            else 1
            if changed == "verification_ordinal"
            else {}
            if changed in {"analysis_timing", "validation_report"}
            else sha(b"different")
        )
    checkpoint = {"resume_contract_hash": RESUME, "receipts": [receipt]}
    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_checkpoint",
        lambda raw, **kwargs: json.loads(raw),
    )

    def save():
        return s.save_checkpoint(
            c.job.job_id,
            **lease(c),
            checkpoint_bytes=canonical(checkpoint),
            checkpoint_media_type="application/json",
            progress_completed=1,
            progress_total=3,
            resume_contract_hash=RESUME,
        )

    if changed:
        with pytest.raises(
            JobServiceError, match="rc_fiber_checkpoint_contract_invalid"
        ):
            save()
        assert s.get_job(c.job.job_id, **tenant()).checkpoint is None
    else:
        saved = save()
        assert saved.status == "checkpointed" and saved.progress_completed == 1


def test_complete_and_result_read_use_rc_bound_and_exact_validation_report(
    tmp_path, monkeypatch
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    receipt = synthetic_pair(s, c)
    result = {
        "schema_version": "bounded-rc-fiber-job-result.v1",
        "receipts": [receipt],
        "synthetic_orchestration_only": True,
    }
    raw = canonical(result)
    report = {"contract_pass": True, "result_hash": sha(raw)}
    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_result",
        lambda value, **kwargs: deepcopy(report),
    )
    proof = build_job_completion_evidence(
        job_id=c.job.job_id,
        request_hash=c.job.request.content_hash,
        checkpoint_hash=None,
        result_bytes=raw,
        validation_report=report,
        validator_id=contract.RC_FIBER_JOB_VALIDATOR_ID,
    )
    forged = deepcopy(proof)
    forged["validation_report"]["unbound"] = True
    with pytest.raises(JobServiceError, match="rc_fiber_completion_report_mismatch"):
        s.complete_job(
            c.job.job_id,
            **lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=forged,
        )
    monkeypatch.setattr(implementation, "_MAX_RESULT_BYTES", 32)
    completed = s.complete_job(
        c.job.job_id,
        **lease(c),
        result_bytes=raw,
        result_media_type="application/json",
        evidence=proof,
    )
    assert completed.status == "succeeded"
    assert s.read_result(c.job.job_id, **tenant()) == raw
    assert s.validate_integrity(c.job.job_id, **tenant())["contract_pass"]
    assert (
        http.DurableJobHttpApi(s)
        .handle(
            "GET",
            f"/v1/jobs/{c.job.job_id}/result",
            headers={"X-Structural-Tenant": "a", "Authorization": f"Bearer {TENANT}"},
        )
        .body
        == raw
    )


@pytest.mark.parametrize("length", ["not-a-number", "-1", "1.5"])
def test_malformed_content_length_never_reads_larger_rc_completion_body(
    tmp_path, length
):
    class Unreadable:
        def read(self, *_args):
            pytest.fail("Rejected CONTENT_LENGTH must not trigger a stream read")

    states = []
    list(
        http.DurableJobWSGIApplication(service(tmp_path))(
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/v1/worker/jobs/job_" + "a" * 32 + "/complete",
                "CONTENT_LENGTH": length,
                "wsgi.input": Unreadable(),
            },
            lambda state, headers: states.append(state),
        )
    )
    assert states == ["413 Request Entity Too Large"]


@pytest.mark.parametrize(
    "phase,variant",
    [
        ("analysis", "absent"),
        ("analysis", "positive"),
        ("verification", "absent"),
        ("verification", "positive"),
        ("analysis", "raised"),
    ],
)
def test_unknown_execution_cannot_be_flattened_to_accounted(tmp_path, phase, variant):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    reserve(s, c)
    value = outcome(c, phase, raised=variant == "raised")
    if variant != "raised":
        metrics = (
            value["api_result"]["metrics"]
            if phase == "analysis"
            else value["verification_report"]
        )
        key = "control_work" if phase == "analysis" else "replay_control_work"
        metrics[key] = (
            None if variant == "absent" else {"unknown_solver_work_attempt_count": 1}
        )
    value["unavailable_execution_work"] = False
    with pytest.raises(JobServiceError, match="rc_invocation_contract_invalid"):
        record(s, c, 1, value)
    value["unavailable_execution_work"] = True
    record(s, c, 1, value)
    assert (
        evidence(s, c.job.job_id)["invocations"][0]["unavailable_execution_work"]
        is True
    )


def test_outcome_byte_limit_is_inclusive_and_does_not_publish_oversize(
    tmp_path, monkeypatch
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    reserve(s, c)
    value = outcome(c)
    maximum = len(canonical(value))
    monkeypatch.setattr(contract, "RC_FIBER_JOB_MAX_BYTES", maximum)
    record(s, c, 1, value)
    reserve(s, c)
    larger = deepcopy(value)
    larger["api_result"]["padding"] = "x"
    with pytest.raises(JobServiceError, match="artifact_size_out_of_bounds"):
        record(s, c, 2, larger)
    assert evidence(s, c.job.job_id)["pending_ordinals"] == [2]
    assert s.read_rc_invocation_artifact(
        c.job.job_id, **tenant(), ordinal=1
    ) == canonical(value)


def test_rc_checkpoint_limit_stays_separate_from_larger_result_limit(
    tmp_path, monkeypatch
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    monkeypatch.setattr(implementation, "_MAX_CHECKPOINT_BYTES", 8)
    with pytest.raises(JobServiceError, match="artifact_size_out_of_bounds"):
        s.save_checkpoint(
            c.job.job_id,
            **lease(c),
            checkpoint_bytes=b"123456789",
            checkpoint_media_type="application/json",
            progress_completed=1,
            progress_total=3,
            resume_contract_hash=RESUME,
        )
    assert s.get_job(c.job.job_id, **tenant()).checkpoint is None
    assert s.worker_result_byte_limit(c.job.job_id, **lease(c)) == 576 * 1024 * 1024


def test_posted_complete_envelope_limit_is_authenticated_and_operation_bound(
    tmp_path, monkeypatch
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    payload = {
        "worker_id": "worker-a",
        "lease_token": c.lease_token,
        "evidence": {},
        "result_base64": "e30=",
    }
    raw = canonical(payload)
    monkeypatch.setattr(http, "_MAX_HTTP_BODY", len(raw) - 1)
    monkeypatch.setattr(http, "_MAX_RC_COMPLETE_BODY", len(raw) + 1)
    app = http.DurableJobHttpApi(s)
    path = f"/v1/worker/jobs/{c.job.job_id}/complete"
    headers = {"Authorization": f"Bearer {WORKER}"}
    # RC reaches the unchanged evidence schema check: the larger envelope is accepted.
    accepted_transport = app.handle("POST", path, headers=headers, body=raw)
    assert (
        accepted_transport.status == 400
        and json.loads(accepted_transport.body)["error"]["code"] != "request_too_large"
    )
    assert (
        app.handle(
            "POST", path, headers={"Authorization": "Bearer incorrect"}, body=raw
        ).status
        == 401
    )
    monkeypatch.setattr(
        s, "worker_result_byte_limit", lambda *args, **kwargs: 64 * 1024 * 1024
    )
    assert app.handle("POST", path, headers=headers, body=raw).status == 413


def request_blob_inventory(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted((root / "blobs" / "sha256").rglob("*"))
        if path.is_file()
    }

# Admission/storage tests below use the existing synthetic pure-contract seam.
# They do not establish RC numerical correctness or a filesystem/database quota.
def admission_state_snapshot(s, root, job_id):
    with sqlite3.connect(root / "jobs.sqlite3") as connection:
        tables = {}
        for table in (
            "jobs",
            "job_events",
            "job_execution_budgets",
            "job_rc_invocation_outcomes",
        ):
            tables[table] = connection.execute(
                f"SELECT * FROM {table} WHERE job_id = ? ORDER BY rowid", (job_id,)
            ).fetchall()
    return {
        "job": s.get_job(job_id, **tenant()),
        "tables": tables,
        "invocations": evidence(s, job_id),
        "integrity": s.validate_integrity(job_id, **tenant()),
    }


def synthetic_admission_artifacts(s, c, monkeypatch, *, marker="admission"):
    receipt = synthetic_pair(s, c)
    checkpoint = canonical(
        {"resume_contract_hash": RESUME, "receipts": [receipt], "marker": marker}
    )
    result = {
        "schema_version": "bounded-rc-fiber-job-result.v1",
        "receipts": [receipt],
        "synthetic_orchestration_only": marker,
    }
    raw = canonical(result)
    report = {"contract_pass": True, "result_hash": sha(raw)}
    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_checkpoint",
        lambda raw, **kwargs: json.loads(raw),
    )
    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_result",
        lambda value, **kwargs: deepcopy(report),
    )
    proof = build_job_completion_evidence(
        job_id=c.job.job_id,
        request_hash=c.job.request.content_hash,
        checkpoint_hash=None,
        result_bytes=raw,
        validation_report=report,
        validator_id=contract.RC_FIBER_JOB_VALIDATOR_ID,
    )
    return checkpoint, result, raw, report, proof


@pytest.mark.parametrize("progress", [True, 1.0, 0, 3, 4])
def test_prewrite_checkpoint_progress_rejection_stores_no_blob(
    tmp_path, monkeypatch, progress
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    checkpoint, *_ = synthetic_admission_artifacts(s, c, monkeypatch)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match="checkpoint_progress_invalid"):
        s.save_checkpoint(
            c.job.job_id,
            **lease(c),
            checkpoint_bytes=checkpoint,
            checkpoint_media_type="application/json",
            progress_completed=progress,
            progress_total=3,
            resume_contract_hash=RESUME,
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize(
    "changed", ["analysis_ordinal", "analysis_timing", "result_hash"]
)
def test_prewrite_checkpoint_recorded_binding_rejection_stores_no_blob(
    tmp_path, monkeypatch, changed
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    checkpoint, *_ = synthetic_admission_artifacts(s, c, monkeypatch)
    value = json.loads(checkpoint)
    value["receipts"][0][changed] = (
        2
        if changed == "analysis_ordinal"
        else {}
        if changed == "analysis_timing"
        else sha(b"other")
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match="rc_fiber_checkpoint_contract_invalid"):
        s.save_checkpoint(
            c.job.job_id,
            **lease(c),
            checkpoint_bytes=canonical(value),
            checkpoint_media_type="application/json",
            progress_completed=1,
            progress_total=3,
            resume_contract_hash=RESUME,
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize(
    "changed",
    [
        "family",
        "job_id",
        "request_hash",
        "checkpoint_hash",
        "result_artifact_hash",
        "validator_id",
        "report",
        "recorded_pair",
    ],
)
def test_prewrite_completion_semantic_rejection_stores_no_blob(
    tmp_path, monkeypatch, changed
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    _, result, raw, _, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    if changed == "family":
        result["schema_version"] = "different-job-result.v1"
        raw = canonical(result)
        proof["result_artifact_hash"] = sha(raw)
        expected = "result_contract_mismatch"
    elif changed in {
        "job_id",
        "request_hash",
        "checkpoint_hash",
        "result_artifact_hash",
    }:
        proof[changed] = "job_" + "f" * 32 if changed == "job_id" else sha(b"other")
        expected = "completion_evidence_binding_mismatch"
    elif changed == "validator_id":
        proof["validator_id"] = "untrusted.validator"
        expected = "rc_fiber_completion_report_mismatch"
    elif changed == "report":
        proof["validation_report"]["unbound"] = True
        expected = "rc_fiber_completion_report_mismatch"
    else:
        result["receipts"][0]["analysis_ordinal"] = 2
        raw = canonical(result)
        proof["result_artifact_hash"] = sha(raw)
        expected = "rc_fiber_result_contract_invalid"
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match=expected):
        s.complete_job(
            c.job.job_id,
            **lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=proof,
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


def save_synthetic_checkpoint(s, c, raw, *, progress=1, resume=RESUME):
    return s.save_checkpoint(
        c.job.job_id,
        **lease(c),
        checkpoint_bytes=raw,
        checkpoint_media_type="application/json",
        progress_completed=progress,
        progress_total=3,
        resume_contract_hash=resume,
    )


def prepare_synthetic_prefix_pending(s, c, monkeypatch):
    checkpoint, result, raw, report, proof = synthetic_admission_artifacts(
        s, c, monkeypatch, marker="accepted-prefix"
    )
    saved = save_synthetic_checkpoint(s, c, checkpoint)
    assert saved.progress_completed == 1 and saved.status == "checkpointed"
    c = claim(s)
    assert reserve(s, c) == 3
    proof["checkpoint_hash"] = sha(checkpoint)
    next_checkpoint = json.loads(checkpoint)
    next_checkpoint["marker"] = "unpublished-next-prefix"
    return c, checkpoint, canonical(next_checkpoint), result, raw, report, proof


@pytest.mark.parametrize(
    "changed,expected",
    [
        ("unknown_job", "job_not_found"),
        ("worker_tenant", "worker_tenant_forbidden"),
        ("expired", "lease_expired"),
        ("wrong_token", "lease_unauthorized"),
        ("superseded", "lease_unauthorized"),
        ("total", "checkpoint_progress_invalid"),
        ("total_bool", "checkpoint_progress_invalid"),
        ("resume", "resume_contract_mismatch"),
        ("pure_contract", "rc_fiber_checkpoint_contract_invalid"),
        ("pure_resume", "rc_fiber_checkpoint_contract_invalid"),
    ],
)
def test_prewrite_checkpoint_lease_and_contract_rejection_preserves_storage(
    tmp_path, monkeypatch, changed, expected
):
    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    checkpoint, *_ = synthetic_admission_artifacts(s, c, monkeypatch, marker=changed)
    job_id = c.job.job_id
    args = dict(
        **lease(c),
        checkpoint_bytes=checkpoint,
        checkpoint_media_type="application/json",
        progress_completed=1,
        progress_total=3,
        resume_contract_hash=RESUME,
    )
    if changed == "unknown_job":
        job_id = "job_" + "e" * 32
    elif changed == "worker_tenant":
        s = DurableJobService(
            tmp_path,
            tenant_tokens={"a": TENANT, "b": OTHER},
            worker_tokens={"worker-a": WORKER, "worker-b": WORKER_B},
            worker_tenants={"worker-a": {"b"}, "worker-b": {"a", "b"}},
            clock=clock,
        )
    elif changed == "expired":
        clock.advance()
    elif changed == "wrong_token":
        args["lease_token"] = "wrong-but-well-formed-lease-token"
    elif changed == "superseded":
        clock.advance()
        successor = claim(service(tmp_path, clock), worker="worker-b")
        assert successor.lease_token != c.lease_token
    elif changed in {"total", "total_bool"}:
        args["progress_total"] = 4 if changed == "total" else True
    elif changed == "resume":
        save_synthetic_checkpoint(s, c, checkpoint)
        c = claim(s)
        args.update(lease(c))
        args["progress_completed"] = 2
        args["resume_contract_hash"] = sha(b"new resume contract")
        value = json.loads(checkpoint)
        value["marker"] = "rejected-resume-checkpoint"
        args["checkpoint_bytes"] = canonical(value)
    elif changed == "pure_contract":

        def reject(*args, **kwargs):
            raise ValueError("synthetic pure-contract rejection")

        monkeypatch.setattr(contract, "validate_rc_fiber_job_checkpoint", reject)
    elif changed == "pure_resume":
        value = json.loads(checkpoint)
        value["resume_contract_hash"] = sha(b"different validated resume")
        args["checkpoint_bytes"] = canonical(value)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match=expected):
        s.save_checkpoint(job_id, **args)
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize("operation", ["checkpoint", "completion"])
def test_prewrite_expiry_during_pure_validation_stores_no_blob(
    tmp_path, monkeypatch, operation
):
    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    c, _, checkpoint, _, raw, report, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    if operation == "checkpoint":

        def validate(value, **kwargs):
            clock.advance()
            return json.loads(value)

        monkeypatch.setattr(contract, "validate_rc_fiber_job_checkpoint", validate)

        def invoke():
            return save_synthetic_checkpoint(s, c, checkpoint, progress=2)
    else:

        def validate(value, **kwargs):
            clock.advance()
            return deepcopy(report)

        monkeypatch.setattr(contract, "validate_rc_fiber_job_result", validate)

        def invoke():
            return s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )

    with pytest.raises(JobServiceError, match="lease_expired"):
        invoke()
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs
    assert before["invocations"]["pending_ordinals"] == [3]


@pytest.mark.parametrize(
    "changed", ["pure_contract", "authority_pass", "authority_owner"]
)
def test_prewrite_completion_authority_and_pure_rejection_stores_no_blob(
    tmp_path, monkeypatch, changed
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    _, _, raw, _, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    if changed == "pure_contract":

        def reject(*args, **kwargs):
            raise ValueError("synthetic result contract rejection")

        monkeypatch.setattr(contract, "validate_rc_fiber_job_result", reject)
        expected = "rc_fiber_result_contract_invalid"
    else:
        proof[
            "contract_pass" if changed == "authority_pass" else "solver_truth_owner"
        ] = False if changed == "authority_pass" else "other_solver"
        expected = "job_schema_invalid"
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match=expected):
        s.complete_job(
            c.job.job_id,
            **lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=proof,
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize("race", ["expiry", "takeover"])
def test_prewrite_completion_rechecks_lease_after_initial_budget_gate(
    tmp_path, monkeypatch, race
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    _, _, raw, _, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    reached, resume = Event(), Event()
    initial_gate = s.worker_result_byte_limit

    def gated(*args, **kwargs):
        maximum = initial_gate(*args, **kwargs)
        reached.set()
        assert resume.wait(10), "early completion gate did not resume"
        return maximum

    monkeypatch.setattr(s, "worker_result_byte_limit", gated)

    def complete():
        try:
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
        except JobServiceError as exc:
            return exc.code
        pytest.fail("stale completion was accepted")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(complete)
        try:
            assert reached.wait(10), "completion did not reach initial lease gate"
            clock.advance()
            if race == "takeover":
                successor = claim(service(tmp_path, clock), worker="worker-b")
                assert successor.lease_token != c.lease_token
            before = admission_state_snapshot(s, tmp_path, c.job.job_id)
            blobs = request_blob_inventory(tmp_path)
        finally:
            resume.set()
        assert pending.result(timeout=10) == (
            "lease_expired" if race == "expiry" else "lease_unauthorized"
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize("expired_role", ["checkpoint", "result", "evidence"])
def test_prewrite_late_real_blob_fsync_expiry_preserves_prefix_and_unknown_work(
    tmp_path, monkeypatch, expired_role
):
    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    c, prefix, checkpoint, _, raw, _, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    written_roles = []
    put = s._put_blob

    def expiring(value, **kwargs):
        # The real content-addressed write, file fsync, rename, directory fsync
        # and reread finish before the clock moves. This is a late I/O boundary.
        ref = put(value, **kwargs)
        written_roles.append(kwargs["role"])
        if kwargs["role"] == expired_role:
            clock.advance()
        return ref

    monkeypatch.setattr(s, "_put_blob", expiring)
    with pytest.raises(JobServiceError, match="lease_expired"):
        if expired_role == "checkpoint":
            save_synthetic_checkpoint(s, c, checkpoint, progress=2)
        else:
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert s.read_checkpoint(c.job.job_id, **tenant()) == prefix
    assert written_roles == (
        ["checkpoint"]
        if expired_role == "checkpoint"
        else ["result"]
        if expired_role == "result"
        else ["result", "evidence"]
    )
    expected = (
        [checkpoint]
        if expired_role == "checkpoint"
        else [raw]
        if expired_role == "result"
        else [raw, canonical(proof)]
    )
    after = request_blob_inventory(tmp_path)
    assert sorted(
        value for path, value in after.items() if path not in blobs
    ) == sorted(expected)
    assert before["invocations"]["pending_ordinals"] == [3]
    assert before["job"].result is None and before["job"].evidence is None
    successor = claim(service(tmp_path, clock), worker="worker-b")
    assert successor.checkpoint_bytes == prefix
    assert successor.job.progress_completed == 1
    assert evidence(s, c.job.job_id)["pending_ordinals"] == [3]


@pytest.mark.parametrize("failing_role", ["checkpoint", "result", "evidence"])
def test_prewrite_admitted_fsync_failure_keeps_durable_state(
    tmp_path, monkeypatch, failing_role
):
    import errno

    s = service(tmp_path)
    submit(s)
    c = claim(s)
    c, prefix, checkpoint, _, raw, _, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    put = s._put_blob
    writes = []

    def fail_fsync(value, **kwargs):
        writes.append(kwargs["role"])
        if kwargs["role"] == failing_role:

            def no_space(*args):
                raise OSError(errno.ENOSPC, "synthetic full storage")

            with monkeypatch.context() as isolated:
                isolated.setattr(implementation.os, "fsync", no_space)
                return put(value, **kwargs)
        return put(value, **kwargs)

    monkeypatch.setattr(s, "_put_blob", fail_fsync)
    with pytest.raises(JobServiceError, match="artifact_write_failed"):
        if failing_role == "checkpoint":
            save_synthetic_checkpoint(s, c, checkpoint, progress=2)
        else:
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert s.read_checkpoint(c.job.job_id, **tenant()) == prefix
    after = request_blob_inventory(tmp_path)
    added = [value for path, value in after.items() if path not in blobs]
    assert added == ([raw] if failing_role == "evidence" else [])
    assert not list((tmp_path / "blobs").rglob(".job-blob-*"))
    assert writes == (
        ["checkpoint"]
        if failing_role == "checkpoint"
        else ["result"]
        if failing_role == "result"
        else ["result", "evidence"]
    )


@pytest.mark.parametrize("corrupt_role", ["checkpoint", "result", "evidence"])
def test_prewrite_admitted_existing_blob_corruption_is_not_repaired(
    tmp_path, monkeypatch, corrupt_role
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    c, prefix, checkpoint, _, raw, _, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    payload = (
        checkpoint
        if corrupt_role == "checkpoint"
        else raw
        if corrupt_role == "result"
        else canonical(proof)
    )
    path = s._blob_path(sha(payload))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"corrupted unreferenced synthetic artifact")
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match="artifact_integrity_failed"):
        if corrupt_role == "checkpoint":
            save_synthetic_checkpoint(s, c, checkpoint, progress=2)
        else:
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert s.read_checkpoint(c.job.job_id, **tenant()) == prefix
    assert path.read_bytes() == b"corrupted unreferenced synthetic artifact"
    after = request_blob_inventory(tmp_path)
    # Group admission verifies both existing candidates before the first write.
    assert after == blobs


def test_prewrite_accepted_artifacts_reopen_dedup_and_exact_retries(
    tmp_path, monkeypatch
):
    s = service(tmp_path)
    original_request = request()
    job = submit(s, original_request)
    c = claim(s)
    checkpoint, _, raw, _, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    saved = save_synthetic_checkpoint(s, c, checkpoint)
    reopened = service(tmp_path)
    assert reopened.read_checkpoint(job.job_id, **tenant()) == checkpoint
    assert submit(reopened, deepcopy(original_request)) == saved
    blobs = request_blob_inventory(tmp_path)
    assert submit(reopened, deepcopy(original_request)) == saved
    assert request_blob_inventory(tmp_path) == blobs
    c = claim(reopened)
    with pytest.raises(JobServiceError, match="checkpoint_progress_invalid"):
        save_synthetic_checkpoint(reopened, c, checkpoint)
    assert request_blob_inventory(tmp_path) == blobs
    proof["checkpoint_hash"] = sha(checkpoint)
    # Admitted duplicate contents exercise real _put_blob integrity/dedup.
    reopened._put_blob(
        raw,
        role="result",
        media_type="application/json",
        maximum_bytes=576 * 1024 * 1024,
    )
    reopened._put_blob(
        canonical(proof),
        role="evidence",
        media_type="application/json",
        maximum_bytes=1024 * 1024,
    )
    blobs = request_blob_inventory(tmp_path)
    completed = reopened.complete_job(
        job.job_id,
        **lease(c),
        result_bytes=raw,
        result_media_type="application/json",
        evidence=proof,
    )
    assert completed.status == "succeeded"
    assert request_blob_inventory(tmp_path) == blobs
    final = service(tmp_path)
    assert final.read_request(job.job_id, **tenant()) == canonical(original_request)
    assert final.read_checkpoint(job.job_id, **tenant()) == checkpoint
    assert final.read_result(job.job_id, **tenant()) == raw
    assert final.read_evidence(job.job_id, **tenant()) == canonical(proof)
    assert submit(final, deepcopy(original_request)) == completed
    stable = admission_state_snapshot(final, tmp_path, job.job_id)
    with pytest.raises(JobServiceError, match="lease_state_invalid"):
        final.complete_job(
            job.job_id,
            **lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=proof,
        )
    assert admission_state_snapshot(final, tmp_path, job.job_id) == stable
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize("operation", ["checkpoint", "completion"])
def test_prewrite_writer_lock_defers_takeover_and_preserves_committed_prefix(
    tmp_path, monkeypatch, operation
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    c, prefix, checkpoint, _, raw, report, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    validating, continue_validation, claimant_entered, claimant_finished = (
        Event(),
        Event(),
        Event(),
        Event(),
    )
    successor_service = service(tmp_path, clock)

    def hold_validation(value, **kwargs):
        validating.set()
        assert continue_validation.wait(10), "validation boundary did not resume"
        return json.loads(value) if operation == "checkpoint" else deepcopy(report)

    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_checkpoint"
        if operation == "checkpoint"
        else "validate_rc_fiber_job_result",
        hold_validation,
    )

    def publication():
        try:
            if operation == "checkpoint":
                save_synthetic_checkpoint(s, c, checkpoint, progress=2)
            else:
                s.complete_job(
                    c.job.job_id,
                    **lease(c),
                    result_bytes=raw,
                    result_media_type="application/json",
                    evidence=proof,
                )
        except JobServiceError as exc:
            return exc.code
        pytest.fail("expired publication committed")

    def takeover():
        claimant_entered.set()
        try:
            return claim(successor_service, worker="worker-b")
        finally:
            claimant_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempted = pool.submit(publication)
        successor = None
        try:
            assert validating.wait(10), "publication did not reach validation"
            clock.advance()
            successor = pool.submit(takeover)
            assert claimant_entered.wait(10), "takeover did not enter service"
            assert not claimant_finished.wait(0.1), (
                "writer takeover bypassed publication lock"
            )
            # A separate WAL reader observes only the prior committed projection.
            with sqlite3.connect(tmp_path / "jobs.sqlite3") as reader:
                row = reader.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (c.job.job_id,)
                ).fetchone()
            assert row == before["tables"]["jobs"][0]
        finally:
            continue_validation.set()
        assert attempted.result(timeout=10) == "lease_expired"
        assert successor is not None
        claimed = successor.result(timeout=10)
    assert claimed.checkpoint_bytes == prefix
    assert claimed.job.progress_completed == 1
    assert claimed.job.result is None and claimed.job.evidence is None
    assert request_blob_inventory(tmp_path) == blobs
    after = admission_state_snapshot(s, tmp_path, c.job.job_id)
    assert (
        after["tables"]["job_execution_budgets"]
        == before["tables"]["job_execution_budgets"]
    )
    assert (
        after["tables"]["job_rc_invocation_outcomes"]
        == before["tables"]["job_rc_invocation_outcomes"]
    )
    assert after["invocations"]["pending_ordinals"] == [3]
    assert after["invocations"]["pending_execution_work"] == "unknown"
    assert len(after["tables"]["job_events"]) == len(before["tables"]["job_events"]) + 2


@pytest.mark.parametrize("operation", ["checkpoint", "completion"])
def test_prewrite_validation_and_storage_use_frozen_mutable_inputs(
    tmp_path, monkeypatch, operation
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    checkpoint, _, raw, report, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    frozen_proof = canonical(proof)
    if operation == "checkpoint":
        buffer = bytearray(checkpoint)

        def mutate_caller(value, **kwargs):
            buffer[:] = b"changed caller checkpoint"
            return json.loads(value)

        monkeypatch.setattr(contract, "validate_rc_fiber_job_checkpoint", mutate_caller)
        saved = save_synthetic_checkpoint(s, c, buffer)
        assert saved.checkpoint.content_hash == sha(checkpoint)
        assert service(tmp_path).read_checkpoint(c.job.job_id, **tenant()) == checkpoint
    else:
        buffer = bytearray(raw)

        def mutate_caller(value, **kwargs):
            buffer[:] = b"changed caller result"
            proof["validation_report"]["mutated_after_snapshot"] = True
            return deepcopy(report)

        monkeypatch.setattr(contract, "validate_rc_fiber_job_result", mutate_caller)
        completed = s.complete_job(
            c.job.job_id,
            **lease(c),
            result_bytes=buffer,
            result_media_type="application/json",
            evidence=proof,
        )
        assert completed.result.content_hash == sha(raw)
        assert completed.evidence.content_hash == sha(frozen_proof)
        reopened = service(tmp_path)
        assert reopened.read_result(c.job.job_id, **tenant()) == raw
        assert reopened.read_evidence(c.job.job_id, **tenant()) == frozen_proof


@pytest.mark.parametrize("operation", ["checkpoint", "completion"])
def test_prewrite_real_fsync_writer_lock_blocks_heartbeat_and_takeover(
    tmp_path, monkeypatch, operation
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    c, prefix, checkpoint, _, raw, _, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    heartbeat_service, successor_service = (
        service(tmp_path, clock),
        service(tmp_path, clock),
    )
    synced, resume_writer = Event(), Event()
    heartbeat_entered, heartbeat_finished = Event(), Event()
    successor_entered, successor_finished = Event(), Event()
    sync_directory = s._fsync_directory

    def hold_synced_directory(path):
        # The real file fsync, atomic rename and directory fsync have completed.
        # The writer still holds BEGIN IMMEDIATE while two real writers compete.
        sync_directory(path)
        synced.set()
        assert resume_writer.wait(10), "fsync publication did not resume"

    monkeypatch.setattr(s, "_fsync_directory", hold_synced_directory)

    def publication():
        try:
            if operation == "checkpoint":
                save_synthetic_checkpoint(s, c, checkpoint, progress=2)
            else:
                s.complete_job(
                    c.job.job_id,
                    **lease(c),
                    result_bytes=raw,
                    result_media_type="application/json",
                    evidence=proof,
                )
        except JobServiceError as exc:
            return exc.code
        pytest.fail("publication crossed expired fsync lease")

    def heartbeat_attempt():
        heartbeat_entered.set()
        try:
            heartbeat_service.heartbeat(c.job.job_id, **lease(c), lease_seconds=5)
        except JobServiceError as exc:
            return exc.code
        finally:
            heartbeat_finished.set()
        pytest.fail("expired heartbeat renewed lease")

    def successor_attempt():
        successor_entered.set()
        try:
            return claim(successor_service, worker="worker-b")
        finally:
            successor_finished.set()

    with ThreadPoolExecutor(max_workers=3) as pool:
        attempted = pool.submit(publication)
        heartbeat = successor = None
        try:
            assert synced.wait(10), "publication did not reach actual directory fsync"
            clock.advance()
            heartbeat = pool.submit(heartbeat_attempt)
            successor = pool.submit(successor_attempt)
            assert heartbeat_entered.wait(10) and successor_entered.wait(10)
            assert not heartbeat_finished.wait(0.1), (
                "heartbeat bypassed fsync writer lock"
            )
            assert not successor_finished.wait(0.1), (
                "takeover bypassed fsync writer lock"
            )
            with sqlite3.connect(tmp_path / "jobs.sqlite3") as reader:
                row = reader.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (c.job.job_id,)
                ).fetchone()
            assert row == before["tables"]["jobs"][0]
        finally:
            resume_writer.set()
        assert attempted.result(timeout=10) == "lease_expired"
        assert heartbeat is not None and successor is not None
        assert heartbeat.result(timeout=10) in {"lease_expired", "lease_unauthorized"}
        claimed = successor.result(timeout=10)
    assert claimed.checkpoint_bytes == prefix
    assert claimed.job.progress_completed == 1
    assert claimed.job.result is None and claimed.job.evidence is None
    after = admission_state_snapshot(s, tmp_path, c.job.job_id)
    assert (
        after["tables"]["job_execution_budgets"]
        == before["tables"]["job_execution_budgets"]
    )
    assert (
        after["tables"]["job_rc_invocation_outcomes"]
        == before["tables"]["job_rc_invocation_outcomes"]
    )
    assert after["invocations"]["pending_ordinals"] == [3]
    assert after["invocations"]["pending_execution_work"] == "unknown"
    assert len(after["tables"]["job_events"]) == len(before["tables"]["job_events"]) + 2
    after_blobs = request_blob_inventory(tmp_path)
    added = [value for path, value in after_blobs.items() if path not in blobs]
    assert added == ([checkpoint] if operation == "checkpoint" else [raw])
    if operation == "completion":
        assert not s._blob_path(sha(canonical(proof))).exists()
