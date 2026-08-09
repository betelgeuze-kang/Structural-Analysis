"""Trusted durable worker for bounded multi-member Frame3D load control."""

from __future__ import annotations

import hashlib
import json
from typing import Any, NoReturn

from structural_analysis.api.frame3d_load_control import (
    BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION,
    BoundedFrame3DLoadControlError,
    advance_bounded_frame3d_load_control_model_ir,
    analyze_bounded_frame3d_load_control_model_ir,
    bounded_frame3d_load_control_resume_contract_hash,
    parse_bounded_frame3d_load_control_config,
    validate_bounded_frame3d_load_control_result_manifest,
)
from structural_analysis.execution.frame3d_load_control_validation import (
    FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    build_frame3d_load_control_validation_report,
)
from structural_analysis.execution.job_service import (
    JOB_REQUEST_V2_SCHEMA_VERSION,
    DurableJobService,
    JobClaim,
    JobView,
    build_job_completion_evidence,
)
from structural_analysis.model_ir import ModelIRValidationError, parse_model_ir_v2


FRAME3D_LOAD_CONTROL_OPERATION = "bounded_frame3d_load_control"
FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE = (
    "application/vnd.structural-analysis.frame3d-load-control-checkpoint+json"
)
FRAME3D_LOAD_CONTROL_RESULT_MEDIA_TYPE = (
    "application/vnd.structural-analysis.result+json"
)


class Frame3DLoadControlWorkerError(ValueError):
    """Stable fail-closed durable Frame3D worker error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def execute_frame3d_load_control_claim(
    service: DurableJobService,
    claim: JobClaim,
    *,
    worker_id: str,
    authorization_token: str,
    checkpoint_step_budget: int | None = None,
) -> JobView:
    """Advance one exact v2 claim or atomically publish its terminal artifacts."""

    if type(service) is not DurableJobService or type(claim) is not JobClaim:
        _fail("worker_argument_invalid", "Exact service and claim types are required.")
    if claim.job.status != "running":
        _fail("worker_claim_not_running", "The supplied claim is not active.")
    if checkpoint_step_budget is not None and (
        type(checkpoint_step_budget) is not int
        or not 1 <= checkpoint_step_budget <= 64
    ):
        _fail(
            "worker_checkpoint_budget_invalid",
            "checkpoint_step_budget must be an integer in [1, 64].",
        )
    request_hash = _sha256(claim.request_bytes)
    if request_hash != claim.job.request.content_hash:
        _fail("worker_request_integrity_failed", "Request bytes changed after claim.")
    request = _request_object(claim.request_bytes)
    if request["validator_id"] != FRAME3D_LOAD_CONTROL_VALIDATOR_ID:
        _fail(
            "worker_validator_identity_mismatch",
            "Request validator identity is not the durable Frame3D validator.",
        )
    try:
        document = parse_model_ir_v2(request["model"], require_analysis_ready=True)
        config = parse_bounded_frame3d_load_control_config(request["config"])
    except (BoundedFrame3DLoadControlError, ModelIRValidationError, TypeError, ValueError) as error:
        raise Frame3DLoadControlWorkerError(
            "worker_request_payload_invalid",
            "ModelIR or config failed the bounded public API contract.",
        ) from error

    expected_total = len(config.load_factors)
    if claim.job.progress_total != expected_total:
        _fail(
            "worker_progress_contract_mismatch",
            "Persisted progress total differs from the exact load schedule.",
        )
    if (claim.checkpoint_bytes is None) != (claim.job.checkpoint is None):
        _fail(
            "worker_checkpoint_reference_mismatch",
            "Checkpoint bytes and persisted reference disagree.",
        )
    if (claim.job.progress_completed == 0) != (claim.checkpoint_bytes is None):
        _fail(
            "worker_checkpoint_progress_mismatch",
            "Durable prefix progress and checkpoint availability disagree.",
        )
    if claim.checkpoint_bytes is not None:
        assert claim.job.checkpoint is not None
        if _sha256(claim.checkpoint_bytes) != claim.job.checkpoint.content_hash:
            _fail(
                "worker_checkpoint_integrity_failed",
                "Checkpoint bytes changed after claim.",
            )

    expected_resume_hash = bounded_frame3d_load_control_resume_contract_hash(
        document,
        config,
    )
    if (
        claim.checkpoint_bytes is None
        and claim.job.resume_contract_hash is not None
    ) or (
        claim.checkpoint_bytes is not None
        and claim.job.resume_contract_hash != expected_resume_hash
    ):
        _fail(
            "worker_resume_contract_mismatch",
            "Checkpoint belongs to a different model, config, or load schedule.",
        )
    remaining = expected_total - claim.job.progress_completed
    if remaining <= 0:
        _fail(
            "worker_progress_terminal_invalid",
            "A complete load schedule must not be leased for more execution.",
        )

    if checkpoint_step_budget is not None and checkpoint_step_budget < remaining:
        try:
            partial = advance_bounded_frame3d_load_control_model_ir(
                document,
                config,
                maximum_new_steps=checkpoint_step_budget,
                restart_checkpoint_artifact=claim.checkpoint_bytes,
            )
            checkpoint_bytes = partial.checkpoint_artifact_bytes()
            validate_bounded_frame3d_load_control_result_manifest(
                partial.manifest_bytes(),
                document=document,
                config=config,
                checkpoint_artifact_bytes=checkpoint_bytes,
            )
        except (BoundedFrame3DLoadControlError, TypeError, ValueError) as error:
            raise Frame3DLoadControlWorkerError(
                "worker_checkpoint_advance_failed",
                "The bounded public API rejected partial checkpoint advancement.",
            ) from error
        completed = partial.metrics["completed_prefix_count"]
        result_remaining = partial.metrics["remaining_load_factor_count"]
        if (
            type(completed) is not int
            or completed != claim.job.progress_completed + checkpoint_step_budget
            or partial.metrics["accepted_step_count"] != checkpoint_step_budget
            or type(result_remaining) is not int
            or result_remaining != expected_total - completed
            or result_remaining <= 0
            or partial.checkpoint_artifact["resume_contract_hash"]
            != expected_resume_hash
        ):
            _fail(
                "worker_checkpoint_progress_mismatch",
                "Partial result progress differs from the durable schedule prefix.",
            )
        return service.save_checkpoint(
            claim.job.job_id,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_token=claim.lease_token,
            checkpoint_bytes=checkpoint_bytes,
            checkpoint_media_type=FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE,
            progress_completed=completed,
            progress_total=expected_total,
            resume_contract_hash=expected_resume_hash,
        )

    try:
        result = analyze_bounded_frame3d_load_control_model_ir(
            document,
            config,
            restart_checkpoint_artifact=claim.checkpoint_bytes,
        )
        result_bytes = result.manifest_bytes()
        terminal_checkpoint_bytes = result.checkpoint_artifact_bytes()
        report = build_frame3d_load_control_validation_report(
            result=result,
            result_bytes=result_bytes,
            document=document,
            config=config,
            checkpoint_artifact_bytes=terminal_checkpoint_bytes,
            job_request_artifact_bytes=claim.request_bytes,
            resume_checkpoint_artifact_bytes=claim.checkpoint_bytes,
            resume_completed_prefix_count=claim.job.progress_completed,
            validator_id=FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
        )
    except (BoundedFrame3DLoadControlError, TypeError, ValueError) as error:
        raise Frame3DLoadControlWorkerError(
            "worker_terminal_validation_failed",
            "Terminal result failed persisted bounded replay validation.",
        ) from error
    if (
        result.schema_version != BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION
        or result.metrics["completed_prefix_count"] != expected_total
        or result.metrics["remaining_load_factor_count"] != 0
        or result.metrics["accepted_step_count"] != remaining
        or result.metrics["final_load_factor"] != config.load_factors[-1]
    ):
        _fail(
            "worker_terminal_progress_mismatch",
            "Terminal result did not complete the exact remaining schedule suffix.",
        )
    evidence = build_job_completion_evidence(
        job_id=claim.job.job_id,
        request_hash=claim.job.request.content_hash,
        checkpoint_hash=(
            claim.job.checkpoint.content_hash if claim.job.checkpoint else None
        ),
        result_bytes=result_bytes,
        validation_report=report.to_dict(),
        validator_id=FRAME3D_LOAD_CONTROL_VALIDATOR_ID,
    )
    return service.complete_job(
        claim.job.job_id,
        worker_id=worker_id,
        authorization_token=authorization_token,
        lease_token=claim.lease_token,
        result_bytes=result_bytes,
        result_media_type=FRAME3D_LOAD_CONTROL_RESULT_MEDIA_TYPE,
        evidence=evidence,
    )


def _request_object(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise Frame3DLoadControlWorkerError(
            "worker_request_json_invalid",
            "Request is not finite duplicate-free UTF-8 JSON.",
        ) from error
    expected_keys = {
        "schema_version",
        "operation",
        "case_id",
        "model",
        "config",
        "result_contract",
        "validator_id",
    }
    if (
        type(value) is not dict
        or set(value) != expected_keys
        or value.get("schema_version") != JOB_REQUEST_V2_SCHEMA_VERSION
        or value.get("operation") != FRAME3D_LOAD_CONTROL_OPERATION
        or value.get("result_contract")
        != BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION
        or value.get("validator_id") != FRAME3D_LOAD_CONTROL_VALIDATOR_ID
        or type(value.get("model")) is not dict
        or type(value.get("config")) is not dict
        or _canonical_json_bytes(value) != payload
    ):
        _fail(
            "worker_request_contract_invalid",
            "Request does not implement the exact canonical Frame3D v2 contract.",
        )
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise Frame3DLoadControlWorkerError(
            "worker_json_canonicalization_failed",
            "Job content is not finite canonical JSON.",
        ) from error


def _object_without_duplicate_keys(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant: {value}")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fail(code: str, detail: str) -> NoReturn:
    raise Frame3DLoadControlWorkerError(code, detail)


__all__ = [
    "FRAME3D_LOAD_CONTROL_CHECKPOINT_MEDIA_TYPE",
    "FRAME3D_LOAD_CONTROL_OPERATION",
    "FRAME3D_LOAD_CONTROL_RESULT_MEDIA_TYPE",
    "Frame3DLoadControlWorkerError",
    "execute_frame3d_load_control_claim",
]
