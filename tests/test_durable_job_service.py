from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
import sqlite3
from pathlib import Path

import pytest

from structural_analysis.execution import job_service as job_service_module

from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    COROTATIONAL_PORTAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    analyze_nonlinear_frame_model_ir,
    nonlinear_frame_model_ir_resume_contract_hash,
    validate_nonlinear_frame_manifest,
)
from structural_analysis.execution.job_http_api import (
    DurableJobHttpApi,
    DurableJobWSGIApplication,
)
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
    build_job_completion_evidence,
    validate_job_view,
)
from structural_analysis.execution.nonlinear_frame_worker import (
    execute_nonlinear_frame_claim,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model_ir import parse_model_ir_v2
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_SPARSE_MATRIX_BACKEND,
)


TENANT_A_TOKEN = "tenant-a-token-0123456789"
TENANT_B_TOKEN = "tenant-b-token-0123456789"
WORKER_TOKEN = "worker-token-0123456789"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 22, 5, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _model_payload() -> dict:
    return json.loads(
        Path("examples/public_corotational_rc_portal.json").read_text(encoding="utf-8")
    )


def _request(*, load_steps: int = 4) -> dict:
    return {
        "schema_version": "structural-analysis-job-request.v1",
        "operation": "nonlinear_frame",
        "case_id": "durable-portal",
        "model": _model_payload(),
        "config": {
            "profile": COROTATIONAL_PORTAL_PROFILE,
            "load_steps": load_steps,
            "residual_tolerance": 1.0e-10,
            "increment_tolerance_m": 1.0e-12,
            "maximum_iterations": 40,
            "matrix_backend": VECTOR_SPARSE_MATRIX_BACKEND,
            "control_mode": "load_control",
        },
        "result_contract": "unified-nonlinear-frame-result.v1",
    }


def _model_ir_request(*, load_steps: int = 2) -> dict:
    model = json.loads(
        Path("examples/bounded_planar_frame_alpha.model-ir.v2.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "schema_version": "structural-analysis-job-request.v1",
        "operation": "nonlinear_frame",
        "case_id": "durable-bounded-planar-model-ir",
        "model": model,
        "config": {
            "profile": COROTATIONAL_GENERAL_PROFILE,
            "load_steps": load_steps,
            "residual_tolerance": 1.0e-9,
            "increment_tolerance_m": 1.0e-12,
            "maximum_iterations": 60,
            "matrix_backend": VECTOR_SPARSE_MATRIX_BACKEND,
            "control_mode": "load_control",
        },
        "result_contract": "unified-nonlinear-frame-result.v1",
    }


def _service(root: Path, *, clock: MutableClock | None = None) -> DurableJobService:
    return DurableJobService(
        root,
        tenant_tokens={
            "tenant-a": TENANT_A_TOKEN,
            "tenant-b": TENANT_B_TOKEN,
        },
        worker_tokens={"worker-a": WORKER_TOKEN},
        worker_tenants={"worker-a": {"tenant-a"}},
        clock=clock,
    )


def _submit(service: DurableJobService, *, key: str = "portal-run-1"):
    return service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        idempotency_key=key,
        request=_request(),
    )


def _claim(service: DurableJobService):
    claim = service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
    assert claim is not None
    return claim


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_submission_is_idempotent_request_bound_and_tenant_isolated(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "jobs")
    first = _submit(service)
    second = _submit(service)

    assert first.job_id == second.job_id
    assert first.revision == second.revision == 0
    assert first.status == "queued"
    assert validate_job_view(first)["job_id"] == first.job_id

    changed = _request(load_steps=5)
    with pytest.raises(JobServiceError, match="idempotency_conflict"):
        service.submit_job(
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
            idempotency_key="portal-run-1",
            request=changed,
        )
    with pytest.raises(JobServiceError, match="job_not_found"):
        service.get_job(
            first.job_id,
            tenant_id="tenant-b",
            authorization_token=TENANT_B_TOKEN,
        )
    with pytest.raises(JobServiceError, match="tenant_unauthorized"):
        service.get_job(
            first.job_id,
            tenant_id="tenant-a",
            authorization_token="wrong-token-that-is-long",
        )


def test_worker_lease_expires_requeues_and_rejects_stale_token(tmp_path: Path) -> None:
    clock = MutableClock()
    service = _service(tmp_path / "jobs", clock=clock)
    submitted = _submit(service)
    stale = service.claim_next(
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_seconds=5,
    )
    assert stale is not None and stale.job.status == "running"
    clock.advance(5)

    with pytest.raises(JobServiceError, match="lease_expired"):
        service.heartbeat(
            submitted.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=stale.lease_token,
        )

    recovered = _claim(service)
    assert recovered.job.status == "running"
    assert recovered.job.attempt == 2
    assert recovered.checkpoint_bytes is None
    with pytest.raises(JobServiceError, match="lease_unauthorized"):
        service.fail_job(
            submitted.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=stale.lease_token,
            error_code="stale_worker",
        )
    failed = service.fail_job(
        submitted.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=recovered.lease_token,
        error_code="bounded_worker_failure",
    )
    assert failed.status == "failed"
    report = service.validate_integrity(
        submitted.job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
    )
    assert report["contract_pass"] is True
    assert report["event_count"] == 5


def test_exact_checkpoint_resume_survives_service_restart_and_matches_full_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "jobs"
    service = _service(root)
    submitted = _submit(service)
    partial = execute_nonlinear_frame_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        checkpoint_step_budget=2,
    )
    assert partial.status == "checkpointed"
    assert partial.progress_completed == 2
    assert partial.can_resume is True
    assert partial.checkpoint is not None
    checkpoint_hash = partial.checkpoint.content_hash

    # A fresh service process reopens the same WAL database and immutable blobs.
    service = _service(root)
    resumed_claim = _claim(service)
    assert resumed_claim.checkpoint_bytes is not None
    assert resumed_claim.job.checkpoint is not None
    assert resumed_claim.job.checkpoint.content_hash == checkpoint_hash
    final = execute_nonlinear_frame_claim(
        service,
        resumed_claim,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
    )
    assert final.status == "succeeded"
    assert final.progress_completed == final.progress_total == 4
    assert final.result is not None and final.evidence is not None
    assert final.can_resume is False
    assert validate_job_view(final)["status"] == "succeeded"

    resumed_payload = json.loads(
        service.read_result(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )
    )
    validate_nonlinear_frame_manifest(resumed_payload)
    evidence = json.loads(
        service.read_evidence(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )
    )
    assert evidence["job_id"] == submitted.job_id
    assert evidence["request_hash"] == final.request.content_hash
    assert evidence["checkpoint_hash"] == checkpoint_hash
    assert evidence["result_artifact_hash"] == final.result.content_hash
    assert evidence["contract_pass"] is True

    model = load_neutral_json_bytes(_canonical_bytes(_model_payload()))
    direct = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(
            profile=COROTATIONAL_PORTAL_PROFILE,
            load_steps=4,
            residual_tolerance=1.0e-10,
            increment_tolerance_m=1.0e-12,
            maximum_iterations=40,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    ).to_dict()
    for key in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
        "convergence_history",
        "engineering_result_ir",
    ):
        assert resumed_payload[key] == direct[key]
    assert (
        resumed_payload["checkpoint"]["chain_hash"]
        == direct["checkpoint"]["chain_hash"]
    )
    assert (
        resumed_payload["checkpoint"]["terminal_state_hash"]
        == direct["checkpoint"]["terminal_state_hash"]
    )
    assert resumed_payload["metrics"]["replayed_prefix_step_count"] == 2
    assert resumed_payload["metrics"]["newly_solved_step_count"] == 2
    assert (
        service.validate_integrity(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )["contract_pass"]
        is True
    )


def test_model_ir_checkpoint_resume_preserves_source_and_execution_plan_bindings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "jobs"
    request = _model_ir_request()
    document = parse_model_ir_v2(request["model"])
    service = _service(root)
    submitted = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        idempotency_key="bounded-planar-model-ir-run-1",
        request=request,
    )

    partial = execute_nonlinear_frame_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        checkpoint_step_budget=1,
    )
    assert partial.status == "checkpointed"
    assert partial.progress_completed == 1
    assert partial.checkpoint is not None
    expected_resume_hash = nonlinear_frame_model_ir_resume_contract_hash(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            residual_tolerance=1.0e-9,
            increment_tolerance_m=1.0e-12,
            maximum_iterations=60,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )
    assert partial.resume_contract_hash == expected_resume_hash

    service = _service(root)
    final = execute_nonlinear_frame_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
    )
    assert final.status == "succeeded"
    assert final.progress_completed == final.progress_total == 2

    resumed = json.loads(
        service.read_result(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )
    )
    validate_nonlinear_frame_manifest(resumed)
    source = resumed["contract_bindings"]["source_model_ir_adapter"]
    plan = resumed["contract_bindings"]["bounded_planar_execution_plan"]
    assert resumed["input_checksum"] == document.content_hash
    assert source["model_ir_content_hash"] == document.content_hash
    assert plan["model_ir_content_hash"] == document.content_hash
    assert source["adapter_hash"] == plan["model_ir_adapter_hash"]

    direct = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=2,
            residual_tolerance=1.0e-9,
            increment_tolerance_m=1.0e-12,
            maximum_iterations=60,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    ).to_dict()
    for key in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
        "convergence_history",
        "engineering_result_ir",
        "contract_bindings",
    ):
        assert resumed[key] == direct[key]
    assert resumed["checkpoint"]["chain_hash"] == direct["checkpoint"]["chain_hash"]
    assert resumed["metrics"]["replayed_prefix_step_count"] == 1
    assert resumed["metrics"]["newly_solved_step_count"] == 1
    assert (
        service.validate_integrity(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )["contract_pass"]
        is True
    )


def test_failed_checkpoint_resume_requires_exact_optimistic_hashes(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "jobs")
    submitted = _submit(service)
    partial = execute_nonlinear_frame_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        checkpoint_step_budget=1,
    )
    retry_claim = _claim(service)
    failed = service.fail_job(
        submitted.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=retry_claim.lease_token,
        error_code="simulated_worker_crash",
    )
    assert failed.status == "failed" and failed.can_resume is True
    assert partial.checkpoint is not None

    with pytest.raises(JobServiceError, match="resume_optimistic_binding_mismatch"):
        service.resume_failed_job(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
            expected_request_hash="sha256:" + "0" * 64,
            expected_checkpoint_hash=partial.checkpoint.content_hash,
        )
    resumed = service.resume_failed_job(
        submitted.job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        expected_request_hash=submitted.request.content_hash,
        expected_checkpoint_hash=partial.checkpoint.content_hash,
    )
    assert resumed.status == "checkpointed"
    assert resumed.can_resume is True


def test_completion_rejects_unbound_evidence_and_blob_tamper(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    service = _service(root)
    submitted = _submit(service)
    claim = _claim(service)
    result = {
        "schema_version": "unified-nonlinear-frame-result.v1",
        "result_hash": "sha256:" + "1" * 64,
    }
    result_bytes = _canonical_bytes(result)
    evidence = build_job_completion_evidence(
        job_id=submitted.job_id,
        request_hash=submitted.request.content_hash,
        checkpoint_hash=None,
        result_bytes=result_bytes,
        validation_report={"contract_pass": True},
        validator_id="test.core.validator",
    )
    evidence["request_hash"] = "sha256:" + "2" * 64
    with pytest.raises(JobServiceError, match="completion_evidence_binding_mismatch"):
        service.complete_job(
            submitted.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
            result_bytes=result_bytes,
            result_media_type="application/json",
            evidence=evidence,
        )

    # Complete a real run, then alter the exact content-addressed result bytes.
    service.fail_job(
        submitted.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=claim.lease_token,
        error_code="unbound_evidence_rejected",
        retriable=True,
    )
    final = execute_nonlinear_frame_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
    )
    assert final.result is not None
    digest = final.result.content_hash.removeprefix("sha256:")
    blob = root / "blobs" / "sha256" / digest[:2] / digest
    blob.write_bytes(b"tampered")
    with pytest.raises(JobServiceError, match="artifact_integrity_failed"):
        service.read_result(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )
    with pytest.raises(JobServiceError, match="artifact_integrity_failed"):
        service.validate_integrity(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_A_TOKEN,
        )


def test_http_api_is_authenticated_tenant_scoped_and_lease_secret_free(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "jobs")
    api = DurableJobHttpApi(service)
    body = _canonical_bytes(_request())
    headers = {
        "Authorization": f"Bearer {TENANT_A_TOKEN}",
        "X-Structural-Tenant": "tenant-a",
        "Idempotency-Key": "http-portal-1",
    }
    submitted = api.handle("POST", "/v1/jobs", headers=headers, body=body)
    assert submitted.status == 202
    payload = json.loads(submitted.body)
    job_id = payload["job_id"]
    assert payload["status"] == "queued"
    assert "lease_token" not in submitted.body.decode("utf-8")

    fetched = api.handle("GET", f"/v1/jobs/{job_id}", headers=headers)
    assert fetched.status == 200
    assert validate_job_view(json.loads(fetched.body))["job_id"] == job_id
    wrong_tenant = api.handle(
        "GET",
        f"/v1/jobs/{job_id}",
        headers={
            "Authorization": f"Bearer {TENANT_B_TOKEN}",
            "X-Structural-Tenant": "tenant-b",
        },
    )
    assert wrong_tenant.status == 404
    unauthenticated = api.handle(
        "GET",
        f"/v1/jobs/{job_id}",
        headers={"X-Structural-Tenant": "tenant-a"},
    )
    assert unauthenticated.status == 401
    assert TENANT_A_TOKEN.encode() not in unauthenticated.body

    malformed_worker = api.handle(
        "POST",
        "/v1/worker/claims",
        headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
        body=_canonical_bytes(
            {"worker_id": "worker-a", "lease_seconds": "not-an-integer"}
        ),
    )
    assert malformed_worker.status == 400
    assert json.loads(malformed_worker.body)["error"]["code"] == "request_field_invalid"


def test_wsgi_composition_root_submits_without_default_credentials(
    tmp_path: Path,
) -> None:
    application = DurableJobWSGIApplication(_service(tmp_path / "jobs"))
    body = _canonical_bytes(_request())
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    response = b"".join(
        application(
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/v1/jobs",
                "CONTENT_LENGTH": str(len(body)),
                "CONTENT_TYPE": "application/json",
                "HTTP_AUTHORIZATION": f"Bearer {TENANT_A_TOKEN}",
                "HTTP_X_STRUCTURAL_TENANT": "tenant-a",
                "HTTP_IDEMPOTENCY_KEY": "wsgi-portal-1",
                "wsgi.input": BytesIO(body),
            },
            start_response,
        )
    )
    assert captured["status"] == "202 Accepted"
    assert json.loads(response)["status"] == "queued"
    assert TENANT_A_TOKEN.encode() not in response


def test_checkpoint_hash_is_byte_exact_and_not_a_path_reference(tmp_path: Path) -> None:
    service = _service(tmp_path / "jobs")
    _submit(service)
    partial = execute_nonlinear_frame_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        checkpoint_step_budget=2,
    )
    assert partial.checkpoint is not None
    claim = _claim(service)
    assert claim.checkpoint_bytes is not None
    observed = "sha256:" + hashlib.sha256(claim.checkpoint_bytes).hexdigest()
    assert observed == partial.checkpoint.content_hash
    assert "path" not in partial.checkpoint.to_dict()


def test_service_rejects_a_symlink_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("platform runner does not allow unprivileged directory symlinks")
    with pytest.raises(JobServiceError, match="service_root_symlink_rejected"):
        _service(link)


class _ConnectionClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.value += seconds


class _ConnectionProbe:
    def __init__(self, failure=None, *, stage="PRAGMA journal_mode = WAL", mode="wal"):
        self.failure = failure
        self.stage = stage
        self.mode = mode
        self.statements = []
        self.closed = False

    def execute(self, statement):
        self.statements.append(statement)
        if statement == self.stage and self.failure is not None:
            raise self.failure
        return self

    def fetchone(self):
        return (self.mode,)

    def close(self):
        assert not self.closed
        self.closed = True


def _bare_connection_service(tmp_path):
    service = object.__new__(DurableJobService)
    service._execution_authority = None
    service._execution_binding = None
    service._db_path = tmp_path / "jobs.sqlite3"
    return service


def _sqlite_failure(message, code=None):
    failure = sqlite3.OperationalError(message)
    if code is not None:
        failure.sqlite_errorcode = code
    return failure


@pytest.mark.parametrize("code", [None, 5, 5 | (2 << 8)])
def test_connection_retries_only_busy_and_closes_each_failed_connection(
    tmp_path,
    monkeypatch,
    code,
):
    service = _bare_connection_service(tmp_path)
    clock = _ConnectionClock()
    probes = [
        _ConnectionProbe(_sqlite_failure("database is locked", code)),
        _ConnectionProbe(_sqlite_failure("database is locked", code)),
        _ConnectionProbe(),
    ]
    calls = []

    def connect(path, **kwargs):
        if calls:
            assert probes[len(calls) - 1].closed
        calls.append(kwargs)
        return probes[len(calls) - 1]

    monkeypatch.setattr(job_service_module.sqlite3, "connect", connect)
    monkeypatch.setattr(job_service_module, "monotonic", clock.monotonic, raising=False)
    monkeypatch.setattr(job_service_module, "sleep", clock.sleep, raising=False)
    connection = service._connect()
    assert connection is probes[-1]
    assert [probe.closed for probe in probes] == [True, True, False]
    assert len(clock.sleeps) == 2
    assert all(call == {"timeout": 0.0, "isolation_level": None} for call in calls)
    assert connection.row_factory is sqlite3.Row
    assert connection.statements == [
        "PRAGMA foreign_keys = ON",
        "PRAGMA journal_mode = WAL",
        "PRAGMA synchronous = FULL",
        "PRAGMA busy_timeout = 30000",
    ]
    connection.close()


def test_connection_busy_retries_share_one_monotonic_thirty_second_deadline(
    tmp_path,
    monkeypatch,
):
    clock = _ConnectionClock()
    probes = []

    def connect(path, **kwargs):
        assert clock.value < 30.0
        assert kwargs["timeout"] == 0.0
        if probes:
            assert probes[-1].closed
        probe = _ConnectionProbe(_sqlite_failure("database is locked"))
        probes.append(probe)
        return probe

    monkeypatch.setattr(job_service_module.sqlite3, "connect", connect)
    monkeypatch.setattr(job_service_module, "monotonic", clock.monotonic, raising=False)
    monkeypatch.setattr(job_service_module, "sleep", clock.sleep, raising=False)
    with pytest.raises(JobServiceError, match="job_database_open_failed"):
        _bare_connection_service(tmp_path)._connect()
    assert clock.value == pytest.approx(30.0)
    assert 2 < len(probes) < 1000
    assert all(probe.closed for probe in probes)
    assert max(clock.sleeps) <= 0.05


@pytest.mark.parametrize(
    "stage", ["connect", "PRAGMA journal_mode = WAL", "PRAGMA synchronous = FULL"]
)
@pytest.mark.parametrize(
    "message,code",
    [
        ("database table is locked", None),
        ("database is locked", 6),
        ("disk I/O error", 10),
        ("attempt to write a readonly database", 8),
    ],
)
def test_connection_non_busy_errors_fail_once_and_close(
    tmp_path, monkeypatch, stage, message, code
):
    failure = _sqlite_failure(message, code)
    probe = _ConnectionProbe(failure, stage=stage)
    calls = []

    def connect(path, **kwargs):
        calls.append(kwargs)
        if stage == "connect":
            raise failure
        return probe

    monkeypatch.setattr(job_service_module.sqlite3, "connect", connect)
    monkeypatch.setattr(
        job_service_module,
        "sleep",
        lambda _: pytest.fail("non-BUSY retried"),
        raising=False,
    )
    with pytest.raises(JobServiceError, match="job_database_open_failed"):
        _bare_connection_service(tmp_path)._connect()
    assert len(calls) == 1
    assert probe.closed is (stage != "connect")


def test_connection_rejects_an_unavailable_wal_mode_without_fallback(
    tmp_path, monkeypatch
):
    probe = _ConnectionProbe(mode="delete")
    monkeypatch.setattr(
        job_service_module.sqlite3, "connect", lambda *args, **kwargs: probe
    )
    monkeypatch.setattr(
        job_service_module,
        "sleep",
        lambda _: pytest.fail("WAL fallback retried"),
        raising=False,
    )
    with pytest.raises(JobServiceError, match="job_database_open_failed"):
        _bare_connection_service(tmp_path)._connect()
    assert probe.closed
    assert "PRAGMA synchronous = FULL" not in probe.statements


def test_constructor_retries_real_wal_conversion_after_reader_releases_lock(
    tmp_path, monkeypatch
):
    root = tmp_path / "jobs"
    root.mkdir()
    reader = sqlite3.connect(root / "jobs.sqlite3", isolation_level=None)
    reader.execute("CREATE TABLE retained (value INTEGER)")
    reader.execute("INSERT INTO retained VALUES (7)")
    reader.execute("BEGIN")
    assert reader.execute("SELECT value FROM retained").fetchone() == (7,)
    retried = Event()
    real_sleep = job_service_module.sleep

    def observed_retry(seconds):
        retried.set()
        real_sleep(seconds)

    monkeypatch.setattr(job_service_module, "sleep", observed_retry)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service, root)
        try:
            assert retried.wait(5), "WAL conversion did not retry the held reader lock"
        finally:
            reader.rollback()
            reader.close()
        service = future.result(timeout=5)
    connection = service._connect()
    try:
        assert connection.execute("SELECT value FROM retained").fetchone()[0] == 7
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.isolation_level is None
    finally:
        connection.close()


def test_simultaneous_constructors_submit_once_and_claim_once(tmp_path):
    count = 4
    barrier = Barrier(count, timeout=10)
    root = tmp_path / "jobs"

    def submit_and_claim(_):
        barrier.wait()
        service = _service(root)
        barrier.wait()
        submitted = _submit(service, key="simultaneous")
        barrier.wait()
        claim = service.claim_next(
            worker_id="worker-a", authorization_token=WORKER_TOKEN
        )
        return submitted, claim

    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(submit_and_claim, range(count)))
    assert len({job.job_id for job, _ in results}) == 1
    claims = [claim for _, claim in results if claim is not None]
    assert len(claims) == 1
    assert claims[0].job.attempt == 1
    service = _service(root)
    integrity = service.validate_integrity(
        claims[0].job.job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
    )
    assert integrity["contract_pass"] is True
    assert integrity["event_count"] == 2
    assert integrity["job_status"] == "running"


def test_connection_busy_during_open_retries_without_a_connection_to_close(
    tmp_path, monkeypatch
):
    clock = _ConnectionClock()
    probe = _ConnectionProbe()
    calls = []

    def connect(path, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise _sqlite_failure("database is locked", 5)
        return probe

    monkeypatch.setattr(job_service_module.sqlite3, "connect", connect)
    monkeypatch.setattr(job_service_module, "monotonic", clock.monotonic)
    monkeypatch.setattr(job_service_module, "sleep", clock.sleep)
    connection = _bare_connection_service(tmp_path)._connect()
    assert connection is probe
    assert len(calls) == 2
    assert len(clock.sleeps) == 1
    assert not probe.closed
    connection.close()


def test_connection_setup_cannot_extend_deadline_and_closes_before_failure(
    tmp_path, monkeypatch
):
    clock = _ConnectionClock()
    probe = _ConnectionProbe()
    execute = probe.execute

    def slow_setup(statement):
        if statement == "PRAGMA synchronous = FULL":
            clock.value = 30.0
        return execute(statement)

    probe.execute = slow_setup
    monkeypatch.setattr(
        job_service_module.sqlite3, "connect", lambda *args, **kwargs: probe
    )
    monkeypatch.setattr(job_service_module, "monotonic", clock.monotonic)
    monkeypatch.setattr(
        job_service_module, "sleep", lambda _: pytest.fail("expired deadline waited")
    )
    with pytest.raises(JobServiceError, match="job_database_open_failed"):
        _bare_connection_service(tmp_path)._connect()
    assert probe.closed
    assert "PRAGMA busy_timeout = 30000" not in probe.statements


def test_connection_unexpected_setup_exception_closes_without_retry(
    tmp_path, monkeypatch
):
    probe = _ConnectionProbe(RuntimeError("setup interrupted"))
    monkeypatch.setattr(
        job_service_module.sqlite3, "connect", lambda *args, **kwargs: probe
    )
    monkeypatch.setattr(
        job_service_module, "sleep", lambda _: pytest.fail("unexpected error retried")
    )
    with pytest.raises(RuntimeError, match="setup interrupted"):
        _bare_connection_service(tmp_path)._connect()
    assert probe.closed


def test_same_database_instances_serialize_real_writer_and_heartbeat(
    tmp_path, monkeypatch
):
    """A busy SQLite BEGIN is real; only the test shortens its busy wait."""
    clock = MutableClock()
    writer = _service(tmp_path / "jobs", clock=clock)
    renewer = _service(tmp_path / "jobs" / ".", clock=clock)
    job = _submit(writer)
    claim = _claim(writer)
    started, finished = Event(), Event()
    open_connection = renewer._open_configured_connection

    def short_busy_connection():
        connection = open_connection()
        connection.execute("PRAGMA busy_timeout=25")
        return connection

    monkeypatch.setattr(renewer, "_open_configured_connection", short_busy_connection)

    def heartbeat():
        started.set()
        try:
            return renewer.heartbeat(
                job.job_id,
                worker_id="worker-a",
                authorization_token=WORKER_TOKEN,
                lease_token=claim.lease_token,
            )
        finally:
            finished.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with writer._transaction() as connection:
            connection.execute(
                "UPDATE jobs SET updated_at=updated_at WHERE job_id=?", (job.job_id,)
            )
            future = pool.submit(heartbeat)
            assert started.wait(5)
            early = finished.wait(0.2)
        # Both threads are reaped even on the baseline failure.
        result = future.result(timeout=5)
    assert not early, "heartbeat bypassed the same-database writer coordination"
    assert result.status == "running" and result.revision == claim.job.revision + 1
    connection = writer._connect()
    try:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    finally:
        connection.close()


def test_claim_lease_is_minted_after_long_immutable_request_check(
    tmp_path, monkeypatch
):
    clock = MutableClock()
    service = _service(tmp_path / "jobs", clock=clock)
    job = _submit(service)
    read_blob = service._read_blob
    delayed = False

    def long_request_check(content_hash, *args, **kwargs):
        nonlocal delayed
        result = read_blob(content_hash, *args, **kwargs)
        if content_hash == job.request.content_hash and not delayed:
            delayed = True
            clock.advance(65)
        return result

    monkeypatch.setattr(service, "_read_blob", long_request_check)
    claim = service.claim_next(
        worker_id="worker-a", authorization_token=WORKER_TOKEN, lease_seconds=60
    )
    assert claim is not None and delayed
    expiry = datetime.fromisoformat(claim.job.lease_expires_at.replace("Z", "+00:00"))
    assert expiry == clock.value + timedelta(seconds=60)
    assert (
        service.heartbeat(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
        ).status
        == "running"
    )


def test_waiting_heartbeat_checks_expiration_after_writer_commits(tmp_path):
    clock = MutableClock()
    writer = _service(tmp_path / "jobs", clock=clock)
    renewer = _service(tmp_path / "jobs", clock=clock)
    job = _submit(writer)
    claim = writer.claim_next(
        worker_id="worker-a", authorization_token=WORKER_TOKEN, lease_seconds=5
    )
    started = Event()

    def heartbeat():
        started.set()
        return renewer.heartbeat(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with writer._transaction() as connection:
            connection.execute("UPDATE jobs SET updated_at=updated_at")
            future = pool.submit(heartbeat)
            assert started.wait(5)
            clock.advance(5)
        with pytest.raises(JobServiceError, match="lease_expired"):
            future.result(timeout=5)
    assert (
        writer.get_job(
            job.job_id, tenant_id="tenant-a", authorization_token=TENANT_A_TOKEN
        ).revision
        == claim.job.revision
    )


def test_waiting_heartbeat_rejects_replaced_lease_token(tmp_path, monkeypatch):
    clock = MutableClock()
    claimer = _service(tmp_path / "jobs", clock=clock)
    renewer = _service(tmp_path / "jobs", clock=clock)
    job = _submit(claimer)
    old_claim = claimer.claim_next(
        worker_id="worker-a", authorization_token=WORKER_TOKEN, lease_seconds=5
    )
    clock.advance(5)
    checking, release, heartbeat_started = Event(), Event(), Event()
    read_blob = claimer._read_blob

    def paused_request_check(content_hash, *args, **kwargs):
        value = read_blob(content_hash, *args, **kwargs)
        if content_hash == job.request.content_hash and not checking.is_set():
            checking.set()
            assert release.wait(5)
        return value

    monkeypatch.setattr(claimer, "_read_blob", paused_request_check)

    def heartbeat():
        heartbeat_started.set()
        return renewer.heartbeat(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=old_claim.lease_token,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        new_claim_future = pool.submit(_claim, claimer)
        try:
            assert checking.wait(5)
            heartbeat_future = pool.submit(heartbeat)
            assert heartbeat_started.wait(5)
        finally:
            release.set()
        new_claim = new_claim_future.result(timeout=5)
        with pytest.raises(JobServiceError, match="lease_unauthorized"):
            heartbeat_future.result(timeout=5)
    assert new_claim.lease_token != old_claim.lease_token
    assert new_claim.job.attempt == 2
    assert (
        claimer.heartbeat(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=new_claim.lease_token,
        ).status
        == "running"
    )


def test_different_database_writer_does_not_block_heartbeat(tmp_path):
    busy = _service(tmp_path / "busy")
    independent = _service(tmp_path / "independent")
    _submit(busy)
    job = _submit(independent)
    claim = _claim(independent)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with busy._transaction() as connection:
            connection.execute("UPDATE jobs SET updated_at=updated_at")
            result = pool.submit(
                independent.heartbeat,
                job.job_id,
                worker_id="worker-a",
                authorization_token=WORKER_TOKEN,
                lease_token=claim.lease_token,
            ).result(timeout=5)
    assert result.status == "running"


def test_constructor_schema_and_policy_wait_for_same_database_writer(
    tmp_path, monkeypatch
):
    root = tmp_path / "jobs"
    writer = _service(root)
    _submit(writer)
    started, initializing = Event(), Event()
    initialize = DurableJobService._initialize_database_unlocked

    def observed_initialize(service):
        initializing.set()
        return initialize(service)

    monkeypatch.setattr(
        DurableJobService, "_initialize_database_unlocked", observed_initialize
    )

    def reopen():
        started.set()
        return DurableJobService(
            root,
            tenant_tokens={"tenant-a": TENANT_A_TOKEN},
            worker_tokens={"worker-a": WORKER_TOKEN},
            max_blob_payload_bytes=1024 * 1024,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with writer._transaction() as connection:
            connection.execute("UPDATE jobs SET updated_at=updated_at")
            future = pool.submit(reopen)
            assert started.wait(5)
            entered_early = initializing.wait(0.2)
        reopened = future.result(timeout=5)
    assert not entered_early and initializing.is_set()
    with reopened._connect() as connection:
        assert (
            connection.execute(
                "SELECT maximum_bytes FROM job_blob_payload_policy"
            ).fetchone()[0]
            == 1024 * 1024
        )


def test_writer_rollback_releases_same_database_mutex(tmp_path):
    writer = _service(tmp_path / "jobs")
    renewer = _service(tmp_path / "jobs")
    job = _submit(writer)
    claim = _claim(writer)
    with pytest.raises(RuntimeError, match="interrupt transaction"):
        with writer._transaction() as connection:
            connection.execute("UPDATE jobs SET progress_completed=99")
            raise RuntimeError("interrupt transaction")
    result = renewer.heartbeat(
        job.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=claim.lease_token,
    )
    assert result.status == "running" and result.progress_completed == 0


def test_waiting_fenced_writer_and_activation_keep_one_lock_order(
    tmp_path, monkeypatch
):
    from structural_analysis.execution.job_execution_authority import (
        ExecutionAuthorityError,
        JobExecutionAuthority,
    )
    from tests.test_rc_real_process_lifecycle import request

    root = tmp_path / "managed"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    writer = DurableJobService(
        root,
        tenant_tokens={"tenant-a": TENANT_A_TOKEN},
        worker_tokens={"worker-a": WORKER_TOKEN},
        execution_authority=authority,
        execution_binding=binding,
    )
    renewer = _service(root)
    job = writer.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        idempotency_key="managed",
        request=request(),
    )
    claim = _claim(writer)
    waiting_fenced, activating = Event(), Event()
    database_writer = job_service_module._database_writer

    def observed_writer(database):
        if database == renewer._db_path:
            waiting_fenced.set()
        return database_writer(database)

    monkeypatch.setattr(job_service_module, "_database_writer", observed_writer)

    def activate():
        activating.set()
        return authority.activate(binding, tmp_path / "restored")

    with ThreadPoolExecutor(max_workers=2) as pool:
        with writer._transaction() as connection:
            connection.execute("UPDATE jobs SET updated_at=updated_at")
            waiting_fenced.clear()
            future = pool.submit(
                renewer.heartbeat,
                job.job_id,
                worker_id="worker-a",
                authorization_token=WORKER_TOKEN,
                lease_token=claim.lease_token,
            )
            assert waiting_fenced.wait(5)
            activation = pool.submit(activate)
            assert activating.wait(5)
            # Authority activation is deliberately nonblocking and fail-closed.
            with pytest.raises(ExecutionAuthorityError, match="authority busy"):
                activation.result(timeout=5)
        assert future.result(timeout=5).status == "running"
    assert authority.activate(binding, tmp_path / "restored").generation == 2
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        renewer.heartbeat(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
        )


def test_current_ordinal_resume_rejects_recorded_source_checkpoint_without_numerics(
    monkeypatch,
):
    """A historical codec override does not grant a new-source worker resume."""
    import base64

    from structural_analysis.assembly import (
        stateful_corotational_fiber_frame2d_ordinal_driver as driver,
        stateful_corotational_fiber_frame2d_ordinal_history as history,
    )
    from structural_analysis.execution.rc_corotational_job_request import (
        rc_corotational_job_canonical_bytes,
    )
    from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
        ORDINAL_JOB_CHECKPOINT_SCHEMA_VERSION,
        ordinal_resume_binding,
    )
    from structural_analysis.execution.rc_corotational_ordinal_job_request import (
        validate_rc_corotational_ordinal_job_request,
    )
    from tests.test_rc_corotational_ordinal_job_request import ordinal_request

    # This is a virgin structural fixture, not an original job/owner checkpoint.
    old_source = "sha256:" + "f" * 64
    authored = ordinal_request()
    current = validate_rc_corotational_ordinal_job_request(authored)
    recorded = validate_rc_corotational_ordinal_job_request(
        authored, recorded_source_identity=old_source
    )
    assert current.request_bytes == recorded.request_bytes
    assert current.execution_source_identity != recorded.execution_source_identity
    problem, plan, config = recorded.prepare()

    def forbidden(*_args, **_kwargs):
        pytest.fail("source-only admission must not assemble, solve, run or launch")

    for module in (driver, history):
        monkeypatch.setattr(module, "assemble_scheduled_frame", forbidden)
        monkeypatch.setattr(module, "solve_scheduled_control_step", forbidden)
    monkeypatch.setattr(driver, "run_ordinal_history", forbidden)
    monkeypatch.setattr(driver, "_source_identity", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    native = driver.OrdinalContinuation(
        recorded.context_hash,
        old_source,
        plan.hash,
        history.initial_mechanical_checkpoint(problem, recorded.context_hash),
    )
    raw = driver.dump_ordinal_continuation(
        problem,
        plan,
        native,
        maximum_solver_attempts=recorded.config.maximum_solver_attempts,
        maximum_subdivision_depth=recorded.config.maximum_subdivision_depth,
        config=config,
        recorded_source_identity=old_source,
    )
    checkpoint = {
        "schema_version": ORDINAL_JOB_CHECKPOINT_SCHEMA_VERSION,
        "request_hash": recorded.request_hash,
        "context_hash": recorded.context_hash,
        "resume_contract_hash": recorded.resume_contract_hash,
        "progress_completed": 0,
        "terminal_checkpoint_artifact_base64": base64.b64encode(raw).decode("ascii"),
    }
    checkpoint["checkpoint_hash"] = (
        "sha256:"
        + hashlib.sha256(rc_corotational_job_canonical_bytes(checkpoint)).hexdigest()
    )
    historical = ordinal_resume_binding(recorded, checkpoint)
    assert historical["completed_before"] == 0
    assert historical["native_continuation_bytes"] == raw
    assert historical["requires_solver"] is True
    # The same production binding function used before the owned grant/child
    # must reject this otherwise canonical prefix against the current request.
    with pytest.raises(
        ValueError, match="ordinal attached checkpoint identity differs"
    ):
        ordinal_resume_binding(current, checkpoint)
