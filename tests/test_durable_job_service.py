from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_PORTAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
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
        Path("examples/public_corotational_rc_portal.json").read_text(
            encoding="utf-8"
        )
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
    claim = service.claim_next(
        worker_id="worker-a", authorization_token=WORKER_TOKEN
    )
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
    ):
        assert resumed_payload[key] == direct[key]
    assert resumed_payload["checkpoint"]["chain_hash"] == direct["checkpoint"][
        "chain_hash"
    ]
    assert resumed_payload["checkpoint"]["terminal_state_hash"] == direct[
        "checkpoint"
    ]["terminal_state_hash"]
    assert resumed_payload["metrics"]["replayed_prefix_step_count"] == 2
    assert resumed_payload["metrics"]["newly_solved_step_count"] == 2
    assert service.validate_integrity(
        submitted.job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
    )["contract_pass"] is True


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
