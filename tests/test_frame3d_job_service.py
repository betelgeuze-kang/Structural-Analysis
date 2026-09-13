"""Durable 3D orchestration tests without solver execution or physical claims."""

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from structural_analysis.api import frame3d_direct_control as api
from structural_analysis.api.frame3d_direct_control import (
    BoundedFrame3DDirectControlConfig,
)
from structural_analysis.api.frame3d_direct_control_request import (
    bounded_frame3d_direct_control_request_payload,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    StatefulCorotationalFrame3DDisplacementControlConfig,
)
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
    validate_job_view,
)
from structural_analysis.execution.job_http_api import DurableJobHttpApi


ROOT = Path(__file__).resolve().parents[1]
TENANT_TOKEN = "frame3d-tenant-token-0123456789"
OTHER_TENANT_TOKEN = "frame3d-other-tenant-token-0123456789"
WORKER_TOKEN = "frame3d-worker-token-0123456789"
OTHER_WORKER_TOKEN = "frame3d-other-worker-token-0123456789"
OUTSIDE_WORKER_TOKEN = "frame3d-outside-worker-token-0123456789"
SOURCE_REVISION = "a" * 40
RESUME_HASH = "sha256:" + "b" * 64


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def forbid_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("service orchestration test must not run a physical analysis")

    monkeypatch.setattr(
        api, "analyze_bounded_frame3d_direct_control_model_ir", forbidden
    )
    monkeypatch.setattr(
        api, "run_stateful_corotational_frame3d_displacement_control_path", forbidden
    )


def _service(root, clock=None):
    return DurableJobService(
        root,
        tenant_tokens={"tenant-a": TENANT_TOKEN, "tenant-b": OTHER_TENANT_TOKEN},
        worker_tokens={
            "worker-a": WORKER_TOKEN,
            "worker-b": OTHER_WORKER_TOKEN,
            "worker-c": OUTSIDE_WORKER_TOKEN,
        },
        worker_tenants={
            "worker-a": {"tenant-a"},
            "worker-b": {"tenant-a"},
            "worker-c": {"tenant-b"},
        },
        clock=clock,
    )


def _request(maximum_attempts=4):
    config = BoundedFrame3DDirectControlConfig(
        "N2",
        "UX",
        (0.001, 0.002, 0.003, 0.004),
        StatefulCorotationalFrame3DDisplacementControlConfig(
            maximum_path_solve_attempts=maximum_attempts
        ),
    )
    return {
        "schema_version": "structural-analysis-job-request.v2",
        "operation": "bounded_frame3d_direct_control",
        "case_id": "durable-bounded-frame3d",
        "model": json.loads(
            (
                ROOT
                / "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
            ).read_bytes()
        ),
        "config": bounded_frame3d_direct_control_request_payload(config),
        "source_revision": SOURCE_REVISION,
        "result_contract": "bounded-frame3d-job-result.v1",
    }


def _legacy_request():
    return {
        "schema_version": "structural-analysis-job-request.v1",
        "operation": "nonlinear_frame",
        "case_id": "legacy-checkpoint-service-fixture",
        "model": json.loads(
            (ROOT / "examples/public_corotational_rc_portal.json").read_bytes()
        ),
        "config": {
            "profile": "corotational_one_bay_portal.v1",
            "load_steps": 4,
            "residual_tolerance": 1e-10,
            "increment_tolerance_m": 1e-12,
            "maximum_iterations": 40,
            "matrix_backend": "scipy_sparse_spsolve_cpu",
            "control_mode": "load_control",
        },
        "result_contract": "unified-nonlinear-frame-result.v1",
    }


def _submit(service, request=None, *, key="frame3d-run"):
    return service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key=key,
        request=_request() if request is None else request,
    )


def _claim(service):
    claim = service.claim_next(
        worker_id="worker-a", authorization_token=WORKER_TOKEN, lease_seconds=5
    )
    assert claim is not None
    return claim


def _lease(claim):
    return {
        "worker_id": "worker-a",
        "authorization_token": WORKER_TOKEN,
        "lease_token": claim.lease_token,
    }


def _budget(service, claim):
    return service.read_execution_budget(claim.job.job_id, **_lease(claim))


def _reserve(service, claim):
    return service.reserve_execution_attempt(claim.job.job_id, **_lease(claim))


def _integrity(service, job_id):
    return service.validate_integrity(
        job_id, tenant_id="tenant-a", authorization_token=TENANT_TOKEN
    )


def _save(service, claim, completed, **options):
    # Opaque bytes belong only to the existing trusted-worker v1 service seam.
    return service.save_checkpoint(
        claim.job.job_id,
        **_lease(claim),
        checkpoint_bytes=f"synthetic-orchestration-checkpoint-{completed}".encode(),
        checkpoint_media_type="application/octet-stream",
        progress_completed=completed,
        progress_total=4,
        resume_contract_hash=RESUME_HASH,
        **options,
    )


@pytest.mark.parametrize("source", (SOURCE_REVISION, "sha256:" + "c" * 64))
def test_v2_submission_is_idempotent_source_bound_and_keeps_v1_view(source, tmp_path):
    service = _service(tmp_path / "jobs")
    payload = _request()
    payload["source_revision"] = source
    frozen = deepcopy(payload)
    first = _submit(service, payload)
    assert first == _submit(service, deepcopy(payload))
    assert first.status == "queued"
    assert first.progress_completed == 0 and first.progress_total == 4
    view = validate_job_view(first)
    assert view["schema_version"] == "structural-analysis-job-view.v1"
    assert view["solver_truth_owner"] == "structural_analysis_core"
    payload["config"]["control_targets"][0] = 999
    claim = _claim(service)
    assert json.loads(claim.request_bytes) == frozen
    assert _budget(service, claim) == {
        "maximum_attempts": 4,
        "reserved_attempts": 0,
        "remaining_attempts": 4,
    }
    assert _integrity(service, first.job_id)["contract_pass"] is True


@pytest.mark.parametrize("changed", ("source", "budget", "targets", "model"))
def test_v2_idempotency_cannot_replace_any_immutable_input(changed, tmp_path):
    service = _service(tmp_path / "jobs")
    original = _request()
    first = _submit(service, original)
    replacement = deepcopy(original)
    if changed == "source":
        replacement["source_revision"] = "d" * 40
    elif changed == "budget":
        replacement["config"]["solver_config"]["maximum_path_solve_attempts"] += 1
    elif changed == "targets":
        replacement["config"]["control_targets"][0] = 0.0009
    else:
        replacement["model"]["model_id"] += "-different"
    with pytest.raises(JobServiceError, match="idempotency_conflict"):
        _submit(service, replacement)
    assert _submit(service, original).request == first.request


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-source",
        "unknown-top",
        "wrong-version",
        "wrong-operation",
        "wrong-result",
        "source-short",
        "source-uppercase",
        "source-bool",
        "case-empty",
        "model-not-object",
        "model-invalid",
        "config-unknown",
        "config-schema",
        "config-target-bool",
        "config-target-nonfinite",
        "config-budget-bool",
        "config-budget-float",
        "config-budget-zero",
        "config-budget-over-bound",
        "config-policy-without-id",
        "config-policy-unknown",
    ),
)
def test_invalid_v2_schema_or_typed_config_never_creates_a_claim(mutation, tmp_path):
    service = _service(tmp_path / "jobs")
    payload = _request()
    config = payload["config"]
    if mutation == "missing-source":
        payload.pop("source_revision")
    elif mutation == "unknown-top":
        payload["execution_budget"] = 999
    elif mutation == "wrong-version":
        payload["schema_version"] = "structural-analysis-job-request.v1"
    elif mutation == "wrong-operation":
        payload["operation"] = "nonlinear_frame"
    elif mutation == "wrong-result":
        payload["result_contract"] = "bounded-frame3d-direct-control-result.v2"
    elif mutation == "source-short":
        payload["source_revision"] = "a" * 39
    elif mutation == "source-uppercase":
        payload["source_revision"] = "A" * 40
    elif mutation == "source-bool":
        payload["source_revision"] = True
    elif mutation == "case-empty":
        payload["case_id"] = ""
    elif mutation == "model-not-object":
        payload["model"] = []
    elif mutation == "model-invalid":
        payload["model"] = {"schema_version": "structural-analysis-model-ir.v2"}
    elif mutation == "config-unknown":
        config["opaque"] = True
    elif mutation == "config-schema":
        config["schema_version"] = "bounded-frame3d-direct-control-request.v0"
    elif mutation == "config-target-bool":
        config["control_targets"][0] = True
    elif mutation == "config-target-nonfinite":
        config["control_targets"][0] = float("inf")
    elif mutation.startswith("config-budget-"):
        config["solver_config"]["maximum_path_solve_attempts"] = {
            "config-budget-bool": True,
            "config-budget-float": 4.0,
            "config-budget-zero": 0,
            "config-budget-over-bound": 65537,
        }[mutation]
    else:
        config["solver_config"]["frame_config"]["factorization_policy"] = (
            {} if mutation == "config-policy-without-id" else {"policy_id": "opaque"}
        )
    with pytest.raises(JobServiceError):
        _submit(service, payload)
    assert (
        service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
        is None
    )


def test_default_budget_comes_from_existing_typed_solver_config(tmp_path):
    service = _service(tmp_path / "jobs")
    payload = _request()
    payload["config"].pop("solver_config")
    _submit(service, payload)
    claim = _claim(service)
    assert _budget(service, claim) == {
        "maximum_attempts": 4096,
        "reserved_attempts": 0,
        "remaining_attempts": 4096,
    }


def test_inprocess_http_submits_and_reports_v2_jobs_without_cross_tenant_access(
    tmp_path,
):
    service = _service(tmp_path / "jobs")
    http = DurableJobHttpApi(service)
    headers = {
        "Authorization": f"Bearer {TENANT_TOKEN}",
        "X-Structural-Tenant": "tenant-a",
        "Idempotency-Key": "frame3d-http-request",
    }
    body = json.dumps(_request(), allow_nan=False).encode()
    submitted = http.handle("POST", "/v1/jobs", headers=headers, body=body)
    assert submitted.status == 202, submitted.body
    view = validate_job_view(json.loads(submitted.body))
    assert view["status"] == "queued"
    assert view["progress"]["total_steps"] == 4
    repeated = http.handle("POST", "/v1/jobs", headers=headers, body=body)
    assert repeated.status == 202
    assert json.loads(repeated.body)["job_id"] == view["job_id"]
    route = f"/v1/jobs/{view['job_id']}"
    status = http.handle("GET", route, headers=headers)
    assert status.status == 200
    assert validate_job_view(json.loads(status.body)) == view
    isolated = http.handle(
        "GET",
        route,
        headers={
            "Authorization": f"Bearer {OTHER_TENANT_TOKEN}",
            "X-Structural-Tenant": "tenant-b",
        },
    )
    assert isolated.status == 404
    unauthenticated = http.handle(
        "GET", route, headers={"X-Structural-Tenant": "tenant-a"}
    )
    assert unauthenticated.status == 401
    for response in (submitted, status, isolated, unauthenticated):
        assert b"lease_token" not in response.body
        assert TENANT_TOKEN.encode() not in response.body


@pytest.mark.parametrize(
    "operation", ("reserve_execution_attempt", "heartbeat", "fail_job")
)
def test_lease_expiring_while_waiting_for_transaction_cannot_mutate_job(
    operation, tmp_path, monkeypatch
):
    clock = Clock()
    service = _service(tmp_path / "jobs", clock)
    _submit(service)
    claim = _claim(service)
    transaction = service._transaction

    @contextmanager
    def delayed_transaction():
        clock.advance(5)
        with transaction() as connection:
            yield connection

    monkeypatch.setattr(service, "_transaction", delayed_transaction)
    options = {"error_code": "test_delayed_failure"} if operation == "fail_job" else {}
    with pytest.raises(JobServiceError, match="lease_expired"):
        getattr(service, operation)(claim.job.job_id, **_lease(claim), **options)
    monkeypatch.setattr(service, "_transaction", transaction)
    current = service.get_job(
        claim.job.job_id, tenant_id="tenant-a", authorization_token=TENANT_TOKEN
    )
    assert current.revision == claim.job.revision
    assert current.lease_expires_at == claim.job.lease_expires_at
    active = _claim(service)
    assert active.job.attempt == 2
    assert _budget(service, active)["reserved_attempts"] == 0


def test_claim_lease_starts_after_lock_wait_and_blob_read(
    tmp_path, monkeypatch
):
    clock = Clock()
    service = _service(tmp_path / "jobs", clock)
    _submit(service)
    transaction = service._transaction
    read_blob = service._read_blob

    @contextmanager
    def delayed_transaction():
        clock.advance(5)
        with transaction() as connection:
            yield connection

    def delayed_read(*args, **kwargs):
        raw = read_blob(*args, **kwargs)
        clock.advance(7)
        return raw

    monkeypatch.setattr(service, "_transaction", delayed_transaction)
    monkeypatch.setattr(service, "_read_blob", delayed_read)
    claim = _claim(service)
    monkeypatch.setattr(service, "_transaction", transaction)
    monkeypatch.setattr(service, "_read_blob", read_blob)
    expires = datetime.fromisoformat(claim.job.lease_expires_at.replace("Z", "+00:00"))
    assert expires == clock.value + timedelta(seconds=5)
    assert service.heartbeat(claim.job.job_id, **_lease(claim)).status == "running"
    assert _reserve(service, claim) == 1


def test_mutable_checkpoint_buffer_cannot_change_bytes_between_storage_and_validation(
    tmp_path, monkeypatch
):
    from structural_analysis.execution import frame3d_job_contract as contract

    service = _service(tmp_path / "jobs", Clock())
    submitted = _submit(service)
    claim = _claim(service)
    assert _reserve(service, claim) == 1
    initial = b"synthetic-service-checkpoint-initial"
    buffer = bytearray(initial)
    stored = service._put_blob
    validated = []

    def mutate_after_store(payload, **kwargs):
        reference = stored(payload, **kwargs)
        if kwargs["role"] == "checkpoint":
            buffer[:] = b"mutated-after-persistence"
        return reference

    def validate_synthetic_snapshot(
        payload, *, request, progress_completed, execution_budget
    ):
        # Deliberate orchestration-only stub: these bytes are no physical artifact.
        assert type(payload) is bytes
        assert payload == initial
        assert request == json.loads(claim.request_bytes)
        assert progress_completed == 1
        assert execution_budget["reserved_attempts"] == 1
        validated.append(payload)
        return {"resume_contract_hash": RESUME_HASH, "receipts": [{"synthetic": True}]}

    monkeypatch.setattr(service, "_put_blob", mutate_after_store)
    monkeypatch.setattr(
        contract, "validate_frame3d_job_checkpoint", validate_synthetic_snapshot
    )
    saved = service.save_checkpoint(
        submitted.job_id,
        **_lease(claim),
        checkpoint_bytes=buffer,
        checkpoint_media_type="application/octet-stream",
        progress_completed=1,
        progress_total=4,
        resume_contract_hash=RESUME_HASH,
    )
    assert saved.status == "checkpointed"
    assert bytes(buffer) != initial
    assert validated == [initial]
    resumed = _claim(service)
    assert resumed.checkpoint_bytes == initial
    assert resumed.job.checkpoint == saved.checkpoint


@pytest.mark.parametrize(
    "operation", ("reserve_execution_attempt", "read_execution_budget")
)
@pytest.mark.parametrize(
    "credentials,code",
    (
        (
            {"authorization_token": "wrong-worker-token-0123456789"},
            "worker_unauthorized",
        ),
        (
            {"worker_id": "worker-b", "authorization_token": OTHER_WORKER_TOKEN},
            "lease_unauthorized",
        ),
        (
            {"worker_id": "worker-c", "authorization_token": OUTSIDE_WORKER_TOKEN},
            "worker_tenant_forbidden",
        ),
        ({"lease_token": "stale-lease-token-0123456789"}, "lease_unauthorized"),
    ),
)
def test_budget_access_requires_worker_scope_and_current_lease(
    operation, credentials, code, tmp_path
):
    service = _service(tmp_path / "jobs")
    _submit(service)
    claim = _claim(service)
    before = service.get_job(
        claim.job.job_id, tenant_id="tenant-a", authorization_token=TENANT_TOKEN
    )
    with pytest.raises(JobServiceError, match=code):
        getattr(service, operation)(
            claim.job.job_id, **{**_lease(claim), **credentials}
        )
    assert _budget(service, claim)["reserved_attempts"] == 0
    after = service.get_job(
        claim.job.job_id, tenant_id="tenant-a", authorization_token=TENANT_TOKEN
    )
    assert after.revision == before.revision
    assert _reserve(service, claim) == 1


def test_expired_and_superseded_lease_cannot_reserve_or_read_budget(tmp_path):
    clock = Clock()
    service = _service(tmp_path / "jobs", clock)
    _submit(service)
    stale = _claim(service)
    clock.advance(5)
    for operation in (service.reserve_execution_attempt, service.read_execution_budget):
        with pytest.raises(JobServiceError, match="lease_expired"):
            operation(stale.job.job_id, **_lease(stale))
    active = _claim(service)
    assert active.job.attempt == 2
    for operation in (service.reserve_execution_attempt, service.read_execution_budget):
        with pytest.raises(JobServiceError, match="lease_unauthorized"):
            operation(stale.job.job_id, **_lease(stale))
    assert _budget(service, active)["reserved_attempts"] == 0
    assert _reserve(service, active) == 1


def test_reservations_survive_restart_expiry_requeue_and_explicit_failed_resume(
    tmp_path,
):
    clock = Clock()
    root = tmp_path / "jobs"
    service = _service(root, clock)
    submitted = _submit(service)
    first = _claim(service)
    assert _reserve(service, first) == 1
    # Deliberately reserve without invoking a solver: crash-before-call still costs one.
    service = _service(root, clock)
    assert _budget(service, first)["reserved_attempts"] == 1
    service.fail_job(
        first.job.job_id, **_lease(first), error_code="test_retry", retriable=True
    )
    second = _claim(service)
    assert second.job.attempt == 2
    assert _reserve(service, second) == 2
    clock.advance(5)
    third = _claim(service)
    assert third.job.attempt == 3
    assert _reserve(service, third) == 3
    failed = service.fail_job(
        third.job.job_id, **_lease(third), error_code="test_terminal"
    )
    assert failed.status == "failed"
    with pytest.raises(JobServiceError, match="resume_optimistic_binding_mismatch"):
        service.resume_failed_job(
            failed.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_TOKEN,
            expected_request_hash="sha256:" + "f" * 64,
            expected_checkpoint_hash=None,
        )
    service = _service(root, clock)
    service.resume_failed_job(
        failed.job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        expected_request_hash=submitted.request.content_hash,
        expected_checkpoint_hash=None,
    )
    fourth = _claim(service)
    assert fourth.job.attempt == 4
    assert _reserve(service, fourth) == 4
    assert _budget(service, fourth) == {
        "maximum_attempts": 4,
        "reserved_attempts": 4,
        "remaining_attempts": 0,
    }
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        _reserve(service, fourth)
    service.fail_job(
        fourth.job.job_id,
        **_lease(fourth),
        error_code="test_retry_at_cap",
        retriable=True,
    )
    service = _service(root, clock)
    fifth = _claim(service)
    assert fifth.job.attempt == 5
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        _reserve(service, fifth)
    assert _budget(service, fifth)["reserved_attempts"] == 4
    assert _integrity(service, submitted.job_id)["contract_pass"] is True


def test_running_checkpoint_keeps_same_lease_and_commits_incremental_progress(tmp_path):
    service = _service(tmp_path / "jobs")
    _submit(service, _legacy_request())
    claim = _claim(service)
    first = _save(service, claim, 1, release_lease=False)
    assert first.status == "running" and first.progress_completed == 1
    assert first.lease_expires_at == claim.job.lease_expires_at
    assert first.checkpoint is not None
    assert first.can_resume is False
    assert validate_job_view(first)["status"] == "running"
    renewed = service.heartbeat(first.job_id, **_lease(claim), lease_seconds=60)
    assert renewed.status == "running"
    second = _save(service, claim, 2, release_lease=False)
    assert second.status == "running" and second.progress_completed == 2
    assert second.checkpoint.content_hash != first.checkpoint.content_hash
    with pytest.raises(JobServiceError, match="checkpoint_progress_invalid"):
        _save(service, claim, 2, release_lease=False)
    final_partial = _save(service, claim, 3)
    assert final_partial.status == "checkpointed"
    assert final_partial.can_resume is True
    assert final_partial.lease_expires_at is None
    with pytest.raises(JobServiceError, match="lease_state_invalid"):
        service.heartbeat(first.job_id, **_lease(claim))
    resumed = _claim(service)
    assert resumed.checkpoint_bytes == b"synthetic-orchestration-checkpoint-3"
    assert resumed.job.progress_completed == 3
    assert _integrity(service, first.job_id)["contract_pass"] is True


@pytest.mark.parametrize("release", (None, 0, 1, "false"))
def test_checkpoint_release_lease_flag_requires_exact_boolean(release, tmp_path):
    service = _service(tmp_path / "jobs")
    _submit(service, _legacy_request())
    claim = _claim(service)
    with pytest.raises(JobServiceError, match="checkpoint_lease_policy_invalid"):
        _save(service, claim, 1, release_lease=release)
    current = service.get_job(
        claim.job.job_id, tenant_id="tenant-a", authorization_token=TENANT_TOKEN
    )
    assert current.status == "running" and current.progress_completed == 0


@pytest.mark.parametrize(
    "operation", ("reserve_execution_attempt", "read_execution_budget")
)
def test_execution_reservation_api_rejects_legacy_v1_jobs(operation, tmp_path):
    service = _service(tmp_path / "jobs")
    _submit(service, _legacy_request())
    claim = _claim(service)
    with pytest.raises(JobServiceError, match="execution_budget_operation_unsupported"):
        getattr(service, operation)(claim.job.job_id, **_lease(claim))
    assert _integrity(service, claim.job.job_id)["contract_pass"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "reset-count",
        "increase-cap",
        "decrease-cap",
        "missing-row",
        "invalid-count",
        "invalid-cap",
    ),
)
def test_integrity_rejects_budget_projection_changed_without_reservation_events(
    mutation, tmp_path
):
    service = _service(tmp_path / "jobs")
    submitted = _submit(service)
    claim = _claim(service)
    assert _reserve(service, claim) == 1
    assert _integrity(service, submitted.job_id)["contract_pass"] is True
    sql, values = {
        "reset-count": (
            "UPDATE job_execution_budgets SET reserved_attempts = ? WHERE job_id = ?",
            (0, submitted.job_id),
        ),
        "increase-cap": (
            "UPDATE job_execution_budgets SET maximum_attempts = ? WHERE job_id = ?",
            ("5", submitted.job_id),
        ),
        "decrease-cap": (
            "UPDATE job_execution_budgets SET maximum_attempts = ? WHERE job_id = ?",
            ("3", submitted.job_id),
        ),
        "missing-row": (
            "DELETE FROM job_execution_budgets WHERE job_id = ?",
            (submitted.job_id,),
        ),
        "invalid-count": (
            "UPDATE job_execution_budgets SET reserved_attempts = ? WHERE job_id = ?",
            (5, submitted.job_id),
        ),
        "invalid-cap": (
            "UPDATE job_execution_budgets SET maximum_attempts = ? WHERE job_id = ?",
            ("4.0", submitted.job_id),
        ),
    }[mutation]
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.execute(sql, values)
    with pytest.raises(JobServiceError, match="execution_budget_integrity_failed"):
        _budget(service, claim)
    with pytest.raises(JobServiceError, match="execution_budget_integrity_failed"):
        _reserve(service, claim)
    with pytest.raises(JobServiceError, match="execution_budget_integrity_failed"):
        _integrity(service, submitted.job_id)
