"""Trusted worker adapter from durable jobs to the bounded nonlinear API."""

from __future__ import annotations

import hashlib
import json
from typing import Any, NoReturn, cast

from structural_analysis.api.nonlinear_frame import (
    NonlinearFrameConfig,
    NonlinearFrameProfile,
    advance_nonlinear_frame_checkpoint,
    advance_nonlinear_frame_model_ir_checkpoint,
    analyze_nonlinear_frame,
    analyze_nonlinear_frame_model_ir,
    nonlinear_frame_model_ir_resume_contract_hash,
    nonlinear_frame_resume_contract_hash,
    validate_nonlinear_frame_result,
)
from structural_analysis.execution.job_service import (
    JOB_REQUEST_SCHEMA_VERSION,
    DurableJobService,
    JobClaim,
    JobView,
    build_job_completion_evidence,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model_ir import MODEL_IR_V2_SCHEMA_VERSION, parse_model_ir_v2


CHECKPOINT_MEDIA_TYPE = "application/vnd.structural-analysis.checkpoint+json"
RESULT_MEDIA_TYPE = "application/vnd.structural-analysis.result+json"
NONLINEAR_FRAME_VALIDATOR_ID = (
    "structural_analysis.api.nonlinear_frame.validate_nonlinear_frame_result"
)


class NonlinearFrameWorkerError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def execute_nonlinear_frame_claim(
    service: DurableJobService,
    claim: JobClaim,
    *,
    worker_id: str,
    authorization_token: str,
    checkpoint_step_budget: int | None = None,
) -> JobView:
    """Advance or complete one exact worker claim.

    When ``checkpoint_step_budget`` is smaller than the remaining path, this
    invocation commits a partial checkpoint and returns ``checkpointed``.
    Otherwise it runs the public API to its configured terminal target,
    validates the result, and atomically publishes result plus evidence.
    """

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
    request_hash = "sha256:" + hashlib.sha256(claim.request_bytes).hexdigest()
    if request_hash != claim.job.request.content_hash:
        _fail("worker_request_integrity_failed", "Request bytes changed after claim.")
    request = _request_object(claim.request_bytes)
    model_payload = request["model"]
    is_model_ir = model_payload.get("schema_version") == MODEL_IR_V2_SCHEMA_VERSION
    if is_model_ir:
        model_ir = parse_model_ir_v2(model_payload)
        model = None
    else:
        model_ir = None
        model = load_neutral_json_bytes(
            _canonical_json_bytes(model_payload),
            source_path=f"job://{claim.job.job_id}/canonical-model.json",
        )
    config = _config(request["config"])
    expected_total = config.load_steps
    if claim.job.progress_total != expected_total:
        _fail(
            "worker_progress_contract_mismatch",
            "Persisted total steps differ from the immutable solver configuration.",
        )
    if (claim.checkpoint_bytes is None) != (claim.job.checkpoint is None):
        _fail(
            "worker_checkpoint_reference_mismatch",
            "Checkpoint bytes and the persisted reference disagree.",
        )
    if model_ir is not None:
        expected_resume_hash = nonlinear_frame_model_ir_resume_contract_hash(
            model_ir, config
        )
    else:
        assert model is not None
        expected_resume_hash = nonlinear_frame_resume_contract_hash(model, config)
    if (
        claim.job.resume_contract_hash is not None
        and claim.job.resume_contract_hash != expected_resume_hash
    ):
        _fail(
            "worker_resume_contract_mismatch",
            "The checkpoint belongs to a different model/compiler/control path.",
        )
    remaining = expected_total - claim.job.progress_completed
    if remaining <= 0:
        _fail(
            "worker_progress_terminal_invalid",
            "A completed control path must not be leased for more execution.",
        )

    if checkpoint_step_budget is not None and checkpoint_step_budget < remaining:
        if model_ir is not None:
            advance = advance_nonlinear_frame_model_ir_checkpoint(
                model_ir,
                config,
                maximum_new_steps=checkpoint_step_budget,
                restart_checkpoint_chain=claim.checkpoint_bytes,
            )
        else:
            assert model is not None
            advance = advance_nonlinear_frame_checkpoint(
                model,
                config,
                maximum_new_steps=checkpoint_step_budget,
                restart_checkpoint_chain=claim.checkpoint_bytes,
            )
        expected_completed = claim.job.progress_completed + checkpoint_step_budget
        if (
            advance.completed_steps != expected_completed
            or advance.total_steps != expected_total
            or advance.resume_contract_hash != expected_resume_hash
        ):
            _fail(
                "worker_checkpoint_progress_mismatch",
                "Solver checkpoint progress differs from the durable job projection.",
            )
        return service.save_checkpoint(
            claim.job.job_id,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_token=claim.lease_token,
            checkpoint_bytes=advance.checkpoint_bytes,
            checkpoint_media_type=CHECKPOINT_MEDIA_TYPE,
            progress_completed=advance.completed_steps,
            progress_total=advance.total_steps,
            resume_contract_hash=advance.resume_contract_hash,
        )

    if model_ir is not None:
        result = analyze_nonlinear_frame_model_ir(
            model_ir,
            config,
            restart_checkpoint_chain=claim.checkpoint_bytes,
        )
    else:
        assert model is not None
        result = analyze_nonlinear_frame(
            model,
            config,
            restart_checkpoint_chain=claim.checkpoint_bytes,
        )
    report = validate_nonlinear_frame_result(result)
    if not report.contract_pass:
        service.fail_job(
            claim.job.job_id,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_token=claim.lease_token,
            error_code="nonlinear_frame_contract_blocked",
            retriable=False,
        )
        _fail(
            "worker_result_contract_blocked",
            "The core result validator did not authorize publication.",
        )
    result_bytes = _canonical_json_bytes(result.to_dict())
    evidence = build_job_completion_evidence(
        job_id=claim.job.job_id,
        request_hash=claim.job.request.content_hash,
        checkpoint_hash=(
            claim.job.checkpoint.content_hash if claim.job.checkpoint else None
        ),
        result_bytes=result_bytes,
        validation_report=report.to_dict(),
        validator_id=NONLINEAR_FRAME_VALIDATOR_ID,
    )
    return service.complete_job(
        claim.job.job_id,
        worker_id=worker_id,
        authorization_token=authorization_token,
        lease_token=claim.lease_token,
        result_bytes=result_bytes,
        result_media_type=RESULT_MEDIA_TYPE,
        evidence=evidence,
    )


def _request_object(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NonlinearFrameWorkerError(
            "worker_request_json_invalid", "Request is not valid UTF-8 JSON."
        ) from exc
    if (
        type(value) is not dict
        or value.get("schema_version") != JOB_REQUEST_SCHEMA_VERSION
        or value.get("operation") != "nonlinear_frame"
        or type(value.get("model")) is not dict
        or type(value.get("config")) is not dict
    ):
        _fail(
            "worker_request_contract_invalid",
            "Request does not implement the nonlinear-frame job contract.",
        )
    return value


def _config(payload: Any) -> NonlinearFrameConfig:
    if type(payload) is not dict:
        _fail("worker_config_invalid", "Job config must be an object.")
    expected_keys = {
        "profile",
        "load_steps",
        "residual_tolerance",
        "increment_tolerance_m",
        "maximum_iterations",
        "matrix_backend",
        "control_mode",
    }
    if set(payload) != expected_keys or payload.get("control_mode") != "load_control":
        _fail(
            "worker_config_invalid",
            "The v1 durable worker accepts only the exact load-control configuration.",
        )
    try:
        return NonlinearFrameConfig(
            profile=cast(NonlinearFrameProfile, payload["profile"]),
            load_steps=payload["load_steps"],
            residual_tolerance=payload["residual_tolerance"],
            increment_tolerance_m=payload["increment_tolerance_m"],
            maximum_iterations=payload["maximum_iterations"],
            matrix_backend=payload["matrix_backend"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NonlinearFrameWorkerError(
            "worker_config_invalid", "Job config failed the public API contract."
        ) from exc


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise NonlinearFrameWorkerError(
            "worker_json_canonicalization_failed",
            "Job content is not finite canonical JSON.",
        ) from exc


def _fail(code: str, detail: str) -> NoReturn:
    raise NonlinearFrameWorkerError(code, detail)


__all__ = [
    "CHECKPOINT_MEDIA_TYPE",
    "NONLINEAR_FRAME_VALIDATOR_ID",
    "RESULT_MEDIA_TYPE",
    "NonlinearFrameWorkerError",
    "execute_nonlinear_frame_claim",
]
