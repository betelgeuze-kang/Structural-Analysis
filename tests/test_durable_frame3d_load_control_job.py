from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from structural_analysis.api.frame3d_load_control import (
    advance_bounded_frame3d_load_control_model_ir,
    analyze_bounded_frame3d_load_control_model_ir,
    bounded_frame3d_load_control_resume_contract_hash,
    parse_bounded_frame3d_load_control_config,
    validate_bounded_frame3d_load_control_result_manifest,
)
from structural_analysis.api.nonlinear_frame import COROTATIONAL_PORTAL_PROFILE
from structural_analysis.engine_v2.contracts._canonical import canonical_json_bytes
from structural_analysis.execution.frame3d_load_control_validation import (
    FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    build_frame3d_load_control_validation_report,
    validate_frame3d_load_control_validation_report,
)
from structural_analysis.execution.frame3d_load_control_worker import (
    FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE,
    Frame3DLoadControlWorkerError,
    execute_frame3d_load_control_claim,
)
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import (
    ArtifactReference,
    DurableJobService,
    JobClaim,
    JobServiceError,
    build_job_completion_evidence,
)
from structural_analysis.execution.job_worker import (
    JobWorkerDispatchError,
    execute_job_claim,
)
from structural_analysis.model_ir import parse_model_ir_v2
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_SPARSE_MATRIX_BACKEND,
)


TENANT_TOKEN = "tenant-a-token-0123456789"
WORKER_TOKEN = "worker-token-0123456789"
TENANT_HEADERS = {
    "authorization": f"Bearer {TENANT_TOKEN}",
    "x-structural-tenant": "tenant-a",
}


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 9, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _frame3d_request(
    *,
    load_factors: tuple[float, ...] = (0.25, 0.5, 1.0),
) -> dict[str, Any]:
    model = json.loads(
        Path(
            "examples/bounded_frame3d_load_control_multimember.model-ir.v2.json"
        ).read_text(encoding="utf-8")
    )
    return {
        "schema_version": "structural-analysis-job-request.v2",
        "operation": "bounded_frame3d_load_control",
        "case_id": "durable-frame3d-load-control",
        "model": model,
        "config": {
            "schema_version": "bounded-frame3d-load-control-config.v1",
            "profile": "bounded_multimember_frame3d_load_control_model_ir_api.v1",
            "load_pattern_id": "LC_MULTI",
            "load_factors": list(load_factors),
            "solver_config": {
                "profile": (
                    "dense_elastic_corotational_timoshenko_"
                    "frame3d_load_control.v2"
                ),
                "residual_relative_tolerance": 1.0e-8,
                "residual_absolute_tolerance_kn": 1.0e-7,
                "increment_relative_tolerance": 1.0e-10,
                "increment_absolute_tolerance_m": 1.0e-12,
                "maximum_iterations": 20,
                "maximum_condition_number": 1.0e14,
                "linear_solver": "numpy_dense_solve",
                "equation_scaling": "centroid_diameter_force_moment_6dof.v1",
                "condition_number": "scaled_matrix_1_norm",
                "load_control": "strictly_increasing_positive_factors",
                "line_search": {
                    "policy": "strict_scaled_residual_decrease.v1",
                    "alphas": [1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125],
                },
                "regularization_allowed": False,
                "fallback_allowed": False,
            },
        },
        "result_contract": "bounded-frame3d-load-control-result.v1",
        "validator_id": FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    }


def _v1_request() -> dict[str, Any]:
    model = json.loads(
        Path("examples/public_corotational_rc_portal.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "schema_version": "structural-analysis-job-request.v1",
        "operation": "nonlinear_frame",
        "case_id": "dispatcher-v1",
        "model": model,
        "config": {
            "profile": COROTATIONAL_PORTAL_PROFILE,
            "load_steps": 2,
            "residual_tolerance": 1.0e-10,
            "increment_tolerance_m": 1.0e-12,
            "maximum_iterations": 40,
            "matrix_backend": VECTOR_SPARSE_MATRIX_BACKEND,
            "control_mode": "load_control",
        },
        "result_contract": "unified-nonlinear-frame-result.v1",
    }


def _service(
    root: Path,
    *,
    clock: MutableClock | None = None,
) -> DurableJobService:
    return DurableJobService(
        root,
        tenant_tokens={"tenant-a": TENANT_TOKEN},
        worker_tokens={"worker-a": WORKER_TOKEN},
        worker_tenants={"worker-a": {"tenant-a"}},
        clock=clock,
    )


def _claim(service: DurableJobService) -> JobClaim:
    claim = service.claim_next(
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
    )
    assert claim is not None
    return claim


@pytest.fixture(scope="module")
def terminal_reference() -> dict[str, Any]:
    request = _frame3d_request()
    request_bytes = canonical_json_bytes(request)
    document = parse_model_ir_v2(request["model"])
    config = parse_bounded_frame3d_load_control_config(request["config"])
    result = analyze_bounded_frame3d_load_control_model_ir(document, config)
    result_bytes = result.manifest_bytes()
    checkpoint_bytes = result.checkpoint_artifact_bytes()
    report = build_frame3d_load_control_validation_report(
        result=result,
        result_bytes=result_bytes,
        document=document,
        config=config,
        checkpoint_artifact_bytes=checkpoint_bytes,
        job_request_artifact_bytes=request_bytes,
        resume_checkpoint_artifact_bytes=None,
        resume_completed_prefix_count=0,
        validator_id=FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    )
    partial = advance_bounded_frame3d_load_control_model_ir(
        document,
        config,
        maximum_new_steps=2,
    )
    partial_checkpoint_bytes = partial.checkpoint_artifact_bytes()
    resumed_result = analyze_bounded_frame3d_load_control_model_ir(
        document,
        config,
        restart_checkpoint_artifact=partial_checkpoint_bytes,
    )
    resumed_result_bytes = resumed_result.manifest_bytes()
    resumed_report = build_frame3d_load_control_validation_report(
        result=resumed_result,
        result_bytes=resumed_result_bytes,
        document=document,
        config=config,
        checkpoint_artifact_bytes=resumed_result.checkpoint_artifact_bytes(),
        job_request_artifact_bytes=request_bytes,
        resume_checkpoint_artifact_bytes=partial_checkpoint_bytes,
        resume_completed_prefix_count=2,
        validator_id=FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    )
    return {
        "request": request,
        "request_bytes": request_bytes,
        "document": document,
        "config": config,
        "result": result,
        "result_bytes": result_bytes,
        "checkpoint_bytes": checkpoint_bytes,
        "report": report,
        "partial": partial,
        "resumed_result": resumed_result,
        "resumed_result_bytes": resumed_result_bytes,
        "resumed_report": resumed_report,
    }


def test_partial_restart_publishes_exact_terminal_pair_and_http_contract(
    tmp_path: Path,
    terminal_reference: dict[str, Any],
) -> None:
    root = tmp_path / "jobs"
    service = _service(root)
    api = DurableJobHttpApi(service)
    submit_response = api.handle(
        "POST",
        "/v1/jobs",
        headers={**TENANT_HEADERS, "idempotency-key": "frame3d-resume"},
        body=terminal_reference["request_bytes"],
    )
    assert submit_response.status == 202
    job_id = json.loads(submit_response.body)["job_id"]

    partial = execute_job_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        checkpoint_step_budget=2,
    )
    assert partial.status == "checkpointed"
    assert (partial.progress_completed, partial.progress_total) == (2, 3)
    assert partial.result is None and partial.evidence is None
    assert partial.checkpoint is not None
    partial_checkpoint_sha256 = partial.checkpoint.content_hash

    checkpoint_status = api.handle(
        "GET",
        f"/v1/jobs/{job_id}",
        headers=TENANT_HEADERS,
    )
    assert checkpoint_status.status == 200
    checkpoint_view = json.loads(checkpoint_status.body)
    assert checkpoint_view["status"] == "checkpointed"
    assert checkpoint_view["checkpoint"]["content_hash"] == partial_checkpoint_sha256

    fresh_service = _service(root)
    resumed_claim = _claim(fresh_service)
    assert resumed_claim.checkpoint_bytes is not None
    assert _sha256(resumed_claim.checkpoint_bytes) == partial_checkpoint_sha256
    completed = execute_job_claim(
        fresh_service,
        resumed_claim,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
    )
    assert completed.status == "succeeded"
    assert (completed.progress_completed, completed.progress_total) == (3, 3)
    assert completed.checkpoint is not None
    assert completed.checkpoint.content_hash == partial_checkpoint_sha256
    assert completed.result is not None and completed.evidence is not None

    result_bytes = fresh_service.read_result(
        job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
    )
    evidence_bytes = fresh_service.read_evidence(
        job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
    )
    assert completed.result.content_hash == _sha256(result_bytes)
    assert completed.evidence.content_hash == _sha256(evidence_bytes)
    result = json.loads(result_bytes)
    evidence = json.loads(evidence_bytes)
    report = evidence["validation_report"]
    validate_frame3d_load_control_validation_report(report)
    assert result_bytes == terminal_reference["resumed_result_bytes"]

    assert evidence["request_hash"] == completed.request.content_hash
    assert evidence["checkpoint_hash"] == partial_checkpoint_sha256
    assert evidence["result_artifact_hash"] == completed.result.content_hash
    assert report["job_request_artifact_sha256"] == completed.request.content_hash
    assert report["resume_checkpoint_artifact_sha256"] == partial_checkpoint_sha256
    assert report["result_artifact_sha256"] == completed.result.content_hash
    assert report["result_hash"] == result["result_hash"]
    assert report["result_hash"] != report["result_artifact_sha256"]
    assert report["resume_completed_prefix_count"] == 2
    assert report["accepted_suffix_step_count"] == 1
    assert report["completed_prefix_count"] == 3
    assert report["remaining_load_factor_count"] == 0
    assert report["fallback_count"] == report["regularization_count"] == 0
    assert report["external_vv_level"] == 0
    assert report["workbench_execution"] is False
    assert report["public_product_promotion"] is False
    assert report["release_eligible"] is False

    terminal_checkpoint_bytes = canonical_json_bytes(
        result["checkpoint_artifact"]
    ) + b"\n"
    assert report["terminal_checkpoint_artifact_sha256"] == _sha256(
        terminal_checkpoint_bytes
    )
    assert (
        report["terminal_checkpoint_artifact_hash"]
        == result["checkpoint_artifact"]["artifact_hash"]
    )
    validate_bounded_frame3d_load_control_result_manifest(
        result_bytes,
        document=terminal_reference["document"],
        config=terminal_reference["config"],
        checkpoint_artifact_bytes=terminal_checkpoint_bytes,
    )

    uninterrupted = terminal_reference["result"].to_dict()
    for field in (
        "node_displacements",
        "support_reactions",
        "member_recovery",
        "full_node_equilibrium",
        "checkpoint_artifact",
    ):
        assert result[field] == uninterrupted[field]
    assert result["result_hash"] != uninterrupted["result_hash"]
    assert result["metrics"]["accepted_step_count"] == 1
    assert uninterrupted["metrics"]["accepted_step_count"] == 3

    terminal_api = DurableJobHttpApi(fresh_service)
    status_response = terminal_api.handle(
        "GET",
        f"/v1/jobs/{job_id}",
        headers=TENANT_HEADERS,
    )
    result_response = terminal_api.handle(
        "GET",
        f"/v1/jobs/{job_id}/result",
        headers=TENANT_HEADERS,
    )
    evidence_response = terminal_api.handle(
        "GET",
        f"/v1/jobs/{job_id}/evidence",
        headers=TENANT_HEADERS,
    )
    assert status_response.status == result_response.status == evidence_response.status == 200
    assert json.loads(status_response.body)["status"] == "succeeded"
    assert result_response.body == result_bytes
    assert evidence_response.body == evidence_bytes
    assert result_response.headers["content-type"] == (
        "application/vnd.structural-analysis.result+json"
    )
    assert evidence_response.headers["content-type"] == "application/json"
    assert fresh_service.validate_integrity(
        job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
    )["contract_pass"] is True


def test_service_blocks_generic_partial_validator_and_bool_alias_evidence(
    tmp_path: Path,
    terminal_reference: dict[str, Any],
) -> None:
    service = _service(tmp_path / "jobs")
    submitted = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="direct-completion-negative",
        request=terminal_reference["request"],
    )
    claim = _claim(service)

    def complete(result_bytes: bytes, report: dict[str, Any], validator_id: str) -> None:
        evidence = build_job_completion_evidence(
            job_id=submitted.job_id,
            request_hash=claim.job.request.content_hash,
            checkpoint_hash=None,
            result_bytes=result_bytes,
            validation_report=report,
            validator_id=validator_id,
        )
        service.complete_job(
            submitted.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
            result_bytes=result_bytes,
            result_media_type="application/vnd.structural-analysis.result+json",
            evidence=evidence,
        )

    with pytest.raises(JobServiceError):
        complete(
            terminal_reference["result_bytes"],
            {"contract_pass": True},
            FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
        )

    wrong_validator_report = terminal_reference["report"].to_dict()
    wrong_validator_report["validator_id"] = "wrong.validator"
    with pytest.raises(JobServiceError):
        complete(
            terminal_reference["result_bytes"],
            wrong_validator_report,
            "wrong.validator",
        )

    bool_alias_report = terminal_reference["report"].to_dict()
    bool_alias_report["total_load_factor_count"] = True
    with pytest.raises(JobServiceError):
        complete(
            terminal_reference["result_bytes"],
            bool_alias_report,
            FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
        )

    partial_bytes = terminal_reference["partial"].manifest_bytes()
    with pytest.raises(JobServiceError, match="frame3d_completion_schedule_mismatch"):
        complete(
            partial_bytes,
            terminal_reference["report"].to_dict(),
            FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
        )


def test_v2_checkpoint_survives_expired_lease_reclaim_and_rejects_stale_token(
    tmp_path: Path,
    terminal_reference: dict[str, Any],
) -> None:
    clock = MutableClock()
    root = tmp_path / "jobs"
    service = _service(root, clock=clock)
    submitted = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="expired-frame3d-checkpoint",
        request=terminal_reference["request"],
    )
    initial_claim = _claim(service)
    checkpoint_bytes = terminal_reference["partial"].checkpoint_artifact_bytes()
    checkpointed = service.save_checkpoint(
        submitted.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=initial_claim.lease_token,
        checkpoint_bytes=checkpoint_bytes,
        checkpoint_media_type=FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE,
        progress_completed=2,
        progress_total=3,
        resume_contract_hash=bounded_frame3d_load_control_resume_contract_hash(
            terminal_reference["document"],
            terminal_reference["config"],
        ),
    )
    assert checkpointed.checkpoint is not None
    checkpoint_sha256 = checkpointed.checkpoint.content_hash

    expired_claim = service.claim_next(
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_seconds=5,
    )
    assert expired_claim is not None
    clock.advance(6)
    fresh_service = _service(root, clock=clock)
    reclaimed = fresh_service.claim_next(
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_seconds=5,
    )
    assert reclaimed is not None
    assert reclaimed.job.progress_completed == 2
    assert reclaimed.job.progress_total == 3
    assert reclaimed.job.checkpoint is not None
    assert reclaimed.job.checkpoint.content_hash == checkpoint_sha256
    assert reclaimed.checkpoint_bytes == checkpoint_bytes

    with pytest.raises(JobServiceError, match="lease_unauthorized"):
        service.heartbeat(
            submitted.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=expired_claim.lease_token,
        )


def test_worker_rejects_cross_schedule_and_tampered_checkpoint_wrapper(
    tmp_path: Path,
    terminal_reference: dict[str, Any],
) -> None:
    checkpoint_bytes = terminal_reference["partial"].checkpoint_artifact_bytes()
    checkpoint_ref = ArtifactReference(
        role="checkpoint",
        content_hash=_sha256(checkpoint_bytes),
        byte_length=len(checkpoint_bytes),
        media_type=FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE,
    )

    cross_request = _frame3d_request(load_factors=(0.2, 0.5, 1.0))
    cross_service = _service(tmp_path / "cross")
    cross_service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="cross-schedule",
        request=cross_request,
    )
    cross_claim = _claim(cross_service)
    cross_document = parse_model_ir_v2(cross_request["model"])
    cross_config = parse_bounded_frame3d_load_control_config(cross_request["config"])
    fake_cross_claim = JobClaim(
        job=replace(
            cross_claim.job,
            progress_completed=2,
            checkpoint=checkpoint_ref,
            resume_contract_hash=bounded_frame3d_load_control_resume_contract_hash(
                cross_document,
                cross_config,
            ),
        ),
        lease_token=cross_claim.lease_token,
        request_bytes=cross_claim.request_bytes,
        checkpoint_bytes=checkpoint_bytes,
    )
    with pytest.raises(Frame3DLoadControlWorkerError, match="worker_terminal_validation_failed"):
        execute_frame3d_load_control_claim(
            cross_service,
            fake_cross_claim,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
        )

    tampered_payload = json.loads(checkpoint_bytes)
    tampered_payload["artifact_hash"] = "sha256:" + "0" * 64
    tampered_bytes = canonical_json_bytes(tampered_payload) + b"\n"
    tampered_ref = replace(
        checkpoint_ref,
        content_hash=_sha256(tampered_bytes),
        byte_length=len(tampered_bytes),
    )
    same_request = terminal_reference["request"]
    same_service = _service(tmp_path / "tampered")
    same_service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="tampered-checkpoint",
        request=same_request,
    )
    same_claim = _claim(same_service)
    fake_tampered_claim = JobClaim(
        job=replace(
            same_claim.job,
            progress_completed=2,
            checkpoint=tampered_ref,
            resume_contract_hash=bounded_frame3d_load_control_resume_contract_hash(
                terminal_reference["document"],
                terminal_reference["config"],
            ),
        ),
        lease_token=same_claim.lease_token,
        request_bytes=same_claim.request_bytes,
        checkpoint_bytes=tampered_bytes,
    )
    with pytest.raises(Frame3DLoadControlWorkerError, match="worker_terminal_validation_failed"):
        execute_frame3d_load_control_claim(
            same_service,
            fake_tampered_claim,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
        )

    direct_service = _service(tmp_path / "tampered-direct-completion")
    direct_job = direct_service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="tampered-direct-completion",
        request=same_request,
    )
    direct_claim = _claim(direct_service)
    resume_contract_hash = bounded_frame3d_load_control_resume_contract_hash(
        terminal_reference["document"],
        terminal_reference["config"],
    )
    direct_service.save_checkpoint(
        direct_job.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=direct_claim.lease_token,
        checkpoint_bytes=tampered_bytes,
        checkpoint_media_type=FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE,
        progress_completed=2,
        progress_total=3,
        resume_contract_hash=resume_contract_hash,
    )
    terminal_claim = _claim(direct_service)
    assert terminal_claim.job.checkpoint is not None
    forged_report = terminal_reference["resumed_report"].to_dict()
    forged_report["resume_checkpoint_artifact_sha256"] = (
        terminal_claim.job.checkpoint.content_hash
    )
    resumed_result_bytes = terminal_reference["resumed_result_bytes"]
    forged_evidence = build_job_completion_evidence(
        job_id=direct_job.job_id,
        request_hash=terminal_claim.job.request.content_hash,
        checkpoint_hash=terminal_claim.job.checkpoint.content_hash,
        result_bytes=resumed_result_bytes,
        validation_report=forged_report,
        validator_id=FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    )
    with pytest.raises(
        JobServiceError,
        match="frame3d_completion_resume_checkpoint_binding_mismatch",
    ):
        direct_service.complete_job(
            direct_job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=terminal_claim.lease_token,
            result_bytes=resumed_result_bytes,
            result_media_type="application/vnd.structural-analysis.result+json",
            evidence=forged_evidence,
        )


def test_terminal_schedule_may_close_below_full_load_without_hardcoding_one(
    tmp_path: Path,
) -> None:
    request = _frame3d_request(load_factors=(0.25, 0.5, 0.8))
    service = _service(tmp_path / "jobs")
    submitted = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="terminal-factor-point-eight",
        request=request,
    )
    completed = execute_job_claim(
        service,
        _claim(service),
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
    )
    assert completed.status == "succeeded"
    result = json.loads(
        service.read_result(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_TOKEN,
        )
    )
    evidence = json.loads(
        service.read_evidence(
            submitted.job_id,
            tenant_id="tenant-a",
            authorization_token=TENANT_TOKEN,
        )
    )
    assert result["load_factors"] == [0.25, 0.5, 0.8]
    assert result["metrics"]["final_load_factor"] == 0.8
    assert result["checkpoint_artifact"]["checkpoint"]["load_factor"] == 0.8
    assert evidence["validation_report"]["final_load_factor"] == 0.8


def test_generic_dispatcher_accepts_only_exact_v1_and_v2_pairs(tmp_path: Path) -> None:
    v1_service = _service(tmp_path / "v1")
    v1_service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="dispatch-v1",
        request=_v1_request(),
    )
    v1_claim = _claim(v1_service)
    with patch(
        "structural_analysis.execution.job_worker.execute_nonlinear_frame_claim",
        return_value=v1_claim.job,
    ) as execute_v1:
        assert (
            execute_job_claim(
                v1_service,
                v1_claim,
                worker_id="worker-a",
                authorization_token=WORKER_TOKEN,
            )
            == v1_claim.job
        )
    execute_v1.assert_called_once()

    unsupported = json.loads(v1_claim.request_bytes)
    unsupported["operation"] = "not_allowlisted"
    unsupported_bytes = canonical_json_bytes(unsupported)
    unsupported_claim = JobClaim(
        job=replace(
            v1_claim.job,
            request=replace(
                v1_claim.job.request,
                content_hash=_sha256(unsupported_bytes),
                byte_length=len(unsupported_bytes),
            ),
        ),
        lease_token=v1_claim.lease_token,
        request_bytes=unsupported_bytes,
        checkpoint_bytes=None,
    )
    with pytest.raises(JobWorkerDispatchError, match="identity_unsupported"):
        execute_job_claim(
            v1_service,
            unsupported_claim,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
        )

    v2_service = _service(tmp_path / "v2-validator")
    v2_service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_TOKEN,
        idempotency_key="dispatch-v2-validator",
        request=_frame3d_request(),
    )
    v2_claim = _claim(v2_service)
    wrong_validator = json.loads(v2_claim.request_bytes)
    wrong_validator["validator_id"] = "wrong.validator"
    wrong_validator_bytes = canonical_json_bytes(wrong_validator)
    wrong_validator_claim = JobClaim(
        job=replace(
            v2_claim.job,
            request=replace(
                v2_claim.job.request,
                content_hash=_sha256(wrong_validator_bytes),
                byte_length=len(wrong_validator_bytes),
            ),
        ),
        lease_token=v2_claim.lease_token,
        request_bytes=wrong_validator_bytes,
        checkpoint_bytes=None,
    )
    with pytest.raises(Frame3DLoadControlWorkerError, match="request_contract_invalid"):
        execute_job_claim(
            v2_service,
            wrong_validator_claim,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
        )
