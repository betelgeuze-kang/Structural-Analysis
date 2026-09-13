"""Real bounded 3D worker continuation; transport mutations reuse solver receipts."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.api import frame3d_direct_control as api
from structural_analysis.api.frame3d_direct_control_request import (
    bounded_frame3d_direct_control_request_payload,
)
from structural_analysis.assembly import (
    stateful_corotational_frame3d_displacement_control as control,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.execution import frame3d_direct_control_worker as worker
from structural_analysis.execution import frame3d_job_contract as contract
from structural_analysis.execution import job_worker as dispatcher
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
    build_job_completion_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = (
    ROOT / "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
)
TENANT_TOKEN = "frame3d-tenant-token-0123456789"
WORKER_TOKEN = "frame3d-worker-token-0123456789"
SOURCE_REVISION = "a" * 40  # Caller declaration, not a source attestation.
WORKER_AUTH = {"worker_id": "worker", "authorization_token": WORKER_TOKEN}
TENANT_AUTH = {"tenant_id": "tenant", "authorization_token": TENANT_TOKEN}


def _bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _request(targets=(0.003, 0.006), *, cyclic=False, maximum_attempts=4096):
    config = api.BoundedFrame3DDirectControlConfig(
        "N2",
        "UX",
        tuple(targets),
        control.StatefulCorotationalFrame3DDisplacementControlConfig(
            allow_direction_reversal=cyclic,
            maximum_direction_reversals=2 if cyclic else 0,
            maximum_path_solve_attempts=maximum_attempts,
        ),
    )
    return {
        "schema_version": "structural-analysis-job-request.v2",
        "operation": "bounded_frame3d_direct_control",
        "case_id": "durable-axial-cyclic" if cyclic else "durable-axial-monotonic",
        "model": json.loads(MODEL_PATH.read_bytes()),
        "config": bounded_frame3d_direct_control_request_payload(config),
        "source_revision": SOURCE_REVISION,
        "result_contract": "bounded-frame3d-job-result.v1",
    }


def _service(path):
    return DurableJobService(
        path,
        tenant_tokens={"tenant": TENANT_TOKEN},
        worker_tokens={"worker": WORKER_TOKEN},
        worker_tenants={"worker": {"tenant"}},
        clock=lambda: datetime(2026, 9, 8, tzinfo=timezone.utc),
    )


def _submit(service, request, key):
    return service.submit_job(**TENANT_AUTH, idempotency_key=key, request=request)


def _claim(service):
    claim = service.claim_next(**WORKER_AUTH, lease_seconds=300)
    assert claim is not None
    return claim


def _run(service, claim, *, budget=None):
    return worker.execute_frame3d_direct_control_claim(
        service, claim, **WORKER_AUTH, checkpoint_target_budget=budget
    )


def _result(service, job):
    return json.loads(service.read_result(job.job_id, **TENANT_AUTH))


def _terminal_bytes(wrapper):
    return base64.b64decode(
        wrapper["terminal_checkpoint_artifact_base64"], validate=True
    )


def _rehash(wrapper, field):
    wrapper[field] = canonical_hash({k: v for k, v in wrapper.items() if k != field})
    return wrapper


def _forbid_solve(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid durable transport must fail before a numerical attempt")

    monkeypatch.setattr(
        control,
        "solve_stateful_corotational_frame3d_displacement_control_step",
        forbidden,
    )


@pytest.fixture(scope="module")
def actual_runs(tmp_path_factory):
    """Two complete paths and their split equivalents: ten real target attempts."""
    workspace = tmp_path_factory.mktemp("frame3d-durable-real")
    records = {}
    attempts = []
    real_step = control.solve_stateful_corotational_frame3d_displacement_control_step

    def counted(*args, **kwargs):
        attempts.append(kwargs["target_control_coordinate"])
        return real_step(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            control,
            "solve_stateful_corotational_frame3d_displacement_control_step",
            counted,
        )
        for name, targets, prefix_count in (
            ("monotonic", (0.003, 0.006), 1),
            ("cyclic", (0.003, 0.006, 0.001), 2),
        ):
            request = _request(targets, cyclic=name == "cyclic")
            path = workspace / name
            service = _service(path)
            first_attempt = len(attempts)
            submitted = _submit(service, request, "full")
            full = dispatcher.execute_job_claim(service, _claim(service), **WORKER_AUTH)
            assert full.job_id == submitted.job_id
            assert full.status == "succeeded"
            full_payload = _result(service, full)

            split = _submit(service, request, "split")
            prefix_claim = _claim(service)
            partial = _run(service, prefix_claim, budget=prefix_count)
            assert partial.job_id == split.job_id
            assert partial.status == "checkpointed"
            assert partial.progress_completed == prefix_count
            assert partial.progress_total == len(targets)
            assert partial.lease_expires_at is None

            # Reconstruct the service from disk; only persisted request/checkpoint
            # bytes, credentials and a fresh claim carry the continuation.
            restarted = _service(path)
            resume_claim = _claim(restarted)
            assert resume_claim.job.attempt == 2
            assert resume_claim.request_bytes == prefix_claim.request_bytes
            assert resume_claim.checkpoint_bytes is not None
            prefix_bytes = resume_claim.checkpoint_bytes
            resumed = _run(restarted, resume_claim)
            assert resumed.status == "succeeded"
            resumed_payload = _result(restarted, resumed)
            records[name] = {
                "service": restarted,
                "request": request,
                "targets": targets,
                "prefix_count": prefix_count,
                "prefix_bytes": prefix_bytes,
                "full": full,
                "full_payload": full_payload,
                "resumed": resumed,
                "resumed_payload": resumed_payload,
                "attempts": tuple(attempts[first_attempt:]),
            }
    assert len(attempts) == 10
    return records


@pytest.mark.parametrize("name", ("monotonic", "cyclic"))
def test_real_service_restart_preserves_exact_terminal_checkpoint(actual_runs, name):
    record = actual_runs[name]
    full, resumed = record["full_payload"], record["resumed_payload"]
    assert _terminal_bytes(full) == _terminal_bytes(resumed)
    for payload in (full, resumed):
        assert payload["schema_version"] == "bounded-frame3d-job-result.v1"
        assert payload["completed_target_count"] == len(record["targets"])
        assert payload["total_target_count"] == len(record["targets"])
        assert payload["control_targets"] == list(record["targets"])
        assert len(payload["receipts"]) == len(record["targets"])
        for index, (receipt, target) in enumerate(
            zip(payload["receipts"], record["targets"], strict=True), start=1
        ):
            assert receipt["target_index"] == index
            assert receipt["authored_target"] == target
            assert receipt["reserved_attempt_ordinals"] == [index]
            assert receipt["api_result"]["control"]["control_targets"] == [target]
            assert receipt["api_result"]["metrics"]["requested_target_count"] == 1
        assert (
            contract.validate_frame3d_job_result(payload, request=record["request"])[
                "contract_pass"
            ]
            is True
        )
    assert record["attempts"] == record["targets"] * 2
    assert record["full"].attempt == 1
    assert record["resumed"].attempt == 2
    for job in (record["full"], record["resumed"]):
        report = record["service"].validate_integrity(job.job_id, **TENANT_AUTH)
        assert report["contract_pass"] is True


def test_multi_target_partial_claim_retains_both_committed_receipts(actual_runs):
    record = actual_runs["cyclic"]
    prefix = contract.validate_frame3d_job_checkpoint(
        record["prefix_bytes"], request=record["request"], progress_completed=2
    )
    assert prefix["completed_target_count"] == 2
    assert len(prefix["receipts"]) == 2
    assert prefix["control_targets"] == list(record["targets"])
    assert prefix["execution_budget"]["reserved_attempts"] == 2
    assert _terminal_bytes(prefix) != _terminal_bytes(record["full_payload"])


def test_checkpoint_and_result_validation_return_detached_snapshots(actual_runs):
    record = actual_runs["monotonic"]
    original = json.loads(record["prefix_bytes"])
    validated = contract.validate_frame3d_job_checkpoint(
        original, request=record["request"]
    )
    validated["control_targets"][0] = 999.0
    validated["receipts"].clear()
    assert original == json.loads(record["prefix_bytes"])
    result = record["full_payload"]
    before = deepcopy(result)
    contract.validate_frame3d_job_result(result, request=record["request"])
    assert result == before


def _lease_saved_prefix(path, record):
    """Reuse an actual source-bound prefix to test transport without another solve.

    Reservations deliberately precede attaching its already validated receipts;
    they are conservative budget charges, not new numerical observations.
    """
    service = _service(path)
    submitted = _submit(service, record["request"], "reused-prefix")
    claim = _claim(service)
    prefix = json.loads(record["prefix_bytes"])
    for _ in range(prefix["execution_budget"]["reserved_attempts"]):
        service.reserve_execution_attempt(
            submitted.job_id, **WORKER_AUTH, lease_token=claim.lease_token
        )
    saved = service.save_checkpoint(
        submitted.job_id,
        **WORKER_AUTH,
        lease_token=claim.lease_token,
        checkpoint_bytes=record["prefix_bytes"],
        checkpoint_media_type="application/json",
        progress_completed=prefix["completed_target_count"],
        progress_total=prefix["total_target_count"],
        resume_contract_hash=prefix["resume_contract_hash"],
    )
    assert saved.status == "checkpointed"
    return service, _claim(service)


@pytest.mark.parametrize(
    "mutation", ("cursor", "raw_checkpoint", "authority", "targets")
)
def test_rehashed_checkpoint_contradictions_fail_before_solver(
    actual_runs, tmp_path, monkeypatch, mutation
):
    record = actual_runs["monotonic"]
    service, claim = _lease_saved_prefix(tmp_path / mutation, record)
    payload = json.loads(claim.checkpoint_bytes)
    if mutation == "cursor":
        payload["completed_target_count"] += 1
    elif mutation == "raw_checkpoint":
        payload["terminal_checkpoint_artifact_base64"] = base64.b64encode(
            b"{}"
        ).decode()
    elif mutation == "authority":
        payload["authority"]["design_authority"] = True
    else:
        # Alter an as-yet unexecuted authored target; the prefix must still bind
        # the entire immutable requested schedule.
        payload["control_targets"][-1] += 0.001
    raw = _bytes(_rehash(payload, "checkpoint_hash"))
    _forbid_solve(monkeypatch)
    with pytest.raises(ValueError):
        contract.validate_frame3d_job_checkpoint(raw, request=record["request"])

    # Even a self-consistent replacement reference must not replace the live
    # durable projection. The direct validator above also checks its semantics.
    forged = replace(
        claim,
        checkpoint_bytes=raw,
        job=replace(
            claim.job,
            checkpoint=replace(
                claim.job.checkpoint,
                content_hash=_hash_bytes(raw),
                byte_length=len(raw),
            ),
        ),
    )
    with pytest.raises(
        worker.Frame3DDirectControlWorkerError, match="frame3d_worker_contract_invalid"
    ):
        _run(service, forged)
    current = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert current.status != "succeeded"
    assert current.progress_completed == record["prefix_count"]


@pytest.mark.parametrize(
    "mutation", ("cursor", "raw_checkpoint", "authority", "targets")
)
def test_rehashed_terminal_result_contradictions_are_rejected(
    actual_runs, monkeypatch, mutation
):
    record = actual_runs["monotonic"]
    payload = deepcopy(record["full_payload"])
    if mutation == "cursor":
        payload["completed_target_count"] -= 1
    elif mutation == "raw_checkpoint":
        payload["terminal_checkpoint_artifact_base64"] = base64.b64encode(
            b"{}"
        ).decode()
    elif mutation == "authority":
        payload["authority"]["design_authority"] = True
    else:
        payload["control_targets"][-1] += 0.001
    _rehash(payload, "result_hash")
    _forbid_solve(monkeypatch)
    with pytest.raises(ValueError):
        contract.validate_frame3d_job_result(payload, request=record["request"])


@pytest.mark.parametrize("mutation", ("missing", "previous_chain", "accepted_step"))
def test_cyclic_receipt_chain_proof_is_required_after_rehashing(
    actual_runs, monkeypatch, mutation
):
    record = actual_runs["cyclic"]
    payload = json.loads(record["prefix_bytes"])
    receipt = payload["receipts"][1]
    if mutation == "missing":
        receipt["target_chain_proof"] = None
    elif mutation == "previous_chain":
        receipt["target_chain_proof"]["preimage"]["previous_chain_hash"] = (
            "sha256:" + "0" * 64
        )
    else:
        receipt["target_chain_proof"]["preimage"]["accepted_step_hashes"][0] = (
            "sha256:" + "0" * 64
        )
    _rehash(receipt, "receipt_hash")
    _rehash(payload, "checkpoint_hash")
    _forbid_solve(monkeypatch)
    with pytest.raises(ValueError, match="cyclic|target-chain"):
        contract.validate_frame3d_job_checkpoint(payload, request=record["request"])


def test_published_http_result_and_evidence_are_exact_worker_artifacts(actual_runs):
    record = actual_runs["cyclic"]
    service, job = record["service"], record["resumed"]
    http = DurableJobHttpApi(service)
    headers = {
        "Authorization": f"Bearer {TENANT_TOKEN}",
        "X-Structural-Tenant": "tenant",
    }
    result = http.handle("GET", f"/v1/jobs/{job.job_id}/result", headers=headers)
    evidence = http.handle("GET", f"/v1/jobs/{job.job_id}/evidence", headers=headers)
    assert result.status == evidence.status == 200
    assert result.body == service.read_result(job.job_id, **TENANT_AUTH)
    assert evidence.body == service.read_evidence(job.job_id, **TENANT_AUTH)
    assert json.loads(result.body) == record["resumed_payload"]
    proof = json.loads(evidence.body)
    assert proof["contract_pass"] is True
    assert proof["job_id"] == job.job_id
    assert proof["request_hash"] == job.request.content_hash
    assert proof["result_artifact_hash"] == _hash_bytes(result.body)
    assert b"lease_token" not in result.body + evidence.body
    assert WORKER_TOKEN.encode() not in result.body + evidence.body


@pytest.mark.parametrize("mutation", ("budget_float", "authority_bool"))
def test_completion_rejects_recomputed_report_numeric_type_aliases(
    actual_runs, tmp_path, monkeypatch, mutation
):
    record = actual_runs["monotonic"]
    service = _service(tmp_path / mutation)
    submitted = _submit(service, record["request"], "completion-report-alias")
    claim = _claim(service)
    result = record["full_payload"]
    for _ in range(result["execution_budget"]["reserved_attempts"]):
        service.reserve_execution_attempt(
            submitted.job_id, **WORKER_AUTH, lease_token=claim.lease_token
        )
    budget = service.read_execution_budget(
        submitted.job_id, **WORKER_AUTH, lease_token=claim.lease_token
    )
    report = contract.validate_frame3d_job_result(
        result, request=record["request"], execution_budget=budget
    )
    if mutation == "budget_float":
        report["execution_budget"]["maximum_attempts"] = float(
            report["execution_budget"]["maximum_attempts"]
        )
    else:
        assert report["authority"]["external_vv_level"] == 0
        report["authority"]["external_vv_level"] = False
    result_bytes = _bytes(result)
    evidence = build_job_completion_evidence(
        job_id=submitted.job_id,
        request_hash=submitted.request.content_hash,
        checkpoint_hash=None,
        result_bytes=result_bytes,
        validation_report=report,
        validator_id=contract.FRAME3D_JOB_VALIDATOR_ID,
    )
    assert evidence["contract_pass"] is True
    _forbid_solve(monkeypatch)
    with pytest.raises(JobServiceError, match="frame3d_completion_report_mismatch"):
        service.complete_job(
            submitted.job_id,
            **WORKER_AUTH,
            lease_token=claim.lease_token,
            result_bytes=result_bytes,
            result_media_type="application/json",
            evidence=evidence,
        )
    current = service.get_job(submitted.job_id, **TENANT_AUTH)
    assert current.status == "running"
    assert current.result is None and current.evidence is None


def test_one_global_attempt_cannot_finish_two_targets_through_retry(
    tmp_path, monkeypatch
):
    path = tmp_path / "one-global-attempt"
    request = _request(maximum_attempts=1)
    service = _service(path)
    submitted = _submit(service, request, "one-attempt")
    attempts = []
    real_step = control.solve_stateful_corotational_frame3d_displacement_control_step

    def counted(*args, **kwargs):
        attempts.append(kwargs["target_control_coordinate"])
        return real_step(*args, **kwargs)

    monkeypatch.setattr(
        control,
        "solve_stateful_corotational_frame3d_displacement_control_step",
        counted,
    )
    prefix = _run(service, _claim(service), budget=1)
    assert prefix.status == "checkpointed"
    assert prefix.progress_completed == 1
    assert attempts == [request["config"]["control_targets"][0]]
    assert prefix.checkpoint is not None
    safe_hash = prefix.checkpoint.content_hash
    restarted = _service(path)
    claim = _claim(restarted)
    safe_bytes = claim.checkpoint_bytes
    assert safe_bytes is not None
    assert restarted.read_execution_budget(
        submitted.job_id, **WORKER_AUTH, lease_token=claim.lease_token
    ) == {"maximum_attempts": 1, "reserved_attempts": 1, "remaining_attempts": 0}
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        _run(restarted, claim)
    failed = restarted.get_job(submitted.job_id, **TENANT_AUTH)
    assert failed.status == "failed"
    assert failed.progress_completed == 1
    assert failed.checkpoint.content_hash == safe_hash
    assert failed.error_code == "execution_attempt_budget_exhausted"
    assert failed.result is None and failed.evidence is None

    resumed = restarted.resume_failed_job(
        submitted.job_id,
        **TENANT_AUTH,
        expected_request_hash=submitted.request.content_hash,
        expected_checkpoint_hash=safe_hash,
    )
    assert resumed.status == "checkpointed"
    final_claim = _claim(restarted)
    assert final_claim.checkpoint_bytes == safe_bytes
    assert final_claim.job.attempt == 3
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        _run(restarted, final_claim)
    assert len(attempts) == 1
    final = restarted.get_job(submitted.job_id, **TENANT_AUTH)
    assert final.status == "failed" and final.progress_completed == 1
    assert final.checkpoint.content_hash == safe_hash
    assert restarted.validate_integrity(submitted.job_id, **TENANT_AUTH)[
        "contract_pass"
    ]


def test_stale_claim_is_rejected_before_api_entry(actual_runs, tmp_path, monkeypatch):
    service, stale = _lease_saved_prefix(tmp_path / "stale", actual_runs["monotonic"])
    service.fail_job(
        stale.job.job_id,
        **WORKER_AUTH,
        lease_token=stale.lease_token,
        error_code="synthetic_retriable_transport_failure",
        retriable=True,
    )
    current = _claim(service)
    api_calls = []

    def forbidden(*args, **kwargs):
        api_calls.append(True)
        pytest.fail("stale claim must fail before API entry")

    monkeypatch.setattr(
        worker, "analyze_bounded_frame3d_direct_control_model_ir", forbidden
    )
    _forbid_solve(monkeypatch)
    with pytest.raises(JobServiceError, match="lease_unauthorized"):
        _run(service, stale)
    assert not api_calls
    still_running = service.get_job(stale.job.job_id, **TENANT_AUTH)
    assert still_running.status == "running"
    assert still_running.revision == current.job.revision
    assert (
        service.read_execution_budget(
            current.job.job_id, **WORKER_AUTH, lease_token=current.lease_token
        )["reserved_attempts"]
        == 1
    )


def test_synthetic_blocked_api_result_preserves_last_safe_checkpoint(
    actual_runs, tmp_path, monkeypatch
):
    """Worker persistence only; this stub is not physical nonconvergence evidence."""
    record = actual_runs["monotonic"]
    service, claim = _lease_saved_prefix(tmp_path / "blocked-result", record)
    saved_bytes = claim.checkpoint_bytes
    saved_hash = claim.job.checkpoint.content_hash
    receipt = record["full_payload"]["receipts"][-1]
    ready = api.BoundedFrame3DDirectControlResult(
        **receipt["api_result"],
        _checkpoint_artifact_bytes=base64.b64decode(
            receipt["checkpoint_artifact_base64"], validate=True
        ),
    )
    blocked = replace(
        ready,
        status="blocked",
        contract_pass=False,
        terminal_reason_code="synthetic_worker_persistence_blocked",
    )
    calls = []

    def blocked_api(document, config, **kwargs):
        calls.append(config.control_targets)
        assert kwargs["restart_checkpoint_artifact"] == _terminal_bytes(
            json.loads(saved_bytes)
        )
        kwargs["before_solve_attempt"]()
        return blocked

    monkeypatch.setattr(
        worker, "analyze_bounded_frame3d_direct_control_model_ir", blocked_api
    )

    def blocked_validation(result):
        assert result is blocked
        return {"contract_pass": False}

    # Isolate the already-validated-blocked-result branch; neither stub is
    # presented as a real solver or core-validator observation.
    monkeypatch.setattr(
        worker, "validate_bounded_frame3d_direct_control_result", blocked_validation
    )
    _forbid_solve(monkeypatch)
    with pytest.raises(
        worker.Frame3DDirectControlWorkerError, match="frame3d_worker_target_blocked"
    ):
        _run(service, claim)
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed"
    assert failed.error_code == "frame3d_worker_target_blocked"
    assert failed.progress_completed == 1
    assert failed.checkpoint.content_hash == saved_hash
    assert failed.result is None and failed.evidence is None
    assert calls == [(record["targets"][-1],)]
    service.resume_failed_job(
        failed.job_id,
        **TENANT_AUTH,
        expected_request_hash=failed.request.content_hash,
        expected_checkpoint_hash=saved_hash,
    )
    retry = _claim(service)
    assert retry.checkpoint_bytes == saved_bytes
    assert (
        service.read_execution_budget(
            failed.job_id, **WORKER_AUTH, lease_token=retry.lease_token
        )["reserved_attempts"]
        == 2
    )
    assert service.validate_integrity(failed.job_id, **TENANT_AUTH)["contract_pass"]
