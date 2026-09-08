"""Durable target-at-a-time execution of the existing Frame3D candidate API."""

from __future__ import annotations

from dataclasses import replace
import hashlib

from structural_analysis.api.frame3d_direct_control import (
    analyze_bounded_frame3d_direct_control_model_ir,
    validate_bounded_frame3d_direct_control_result,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.execution.frame3d_job_contract import (
    FRAME3D_JOB_VALIDATOR_ID,
    build_frame3d_job_payload,
    build_frame3d_job_receipt,
    frame3d_job_canonical_bytes,
    frame3d_job_checkpoint_artifact,
    frame3d_job_resume_contract_hash,
    validate_frame3d_job_checkpoint,
    validate_frame3d_job_request,
    validate_frame3d_job_result,
)
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobClaim,
    JobServiceError,
    JobView,
    build_job_completion_evidence,
)


FRAME3D_CHECKPOINT_MEDIA_TYPE = (
    "application/vnd.structural-analysis.frame3d-job-checkpoint+json"
)
FRAME3D_RESULT_MEDIA_TYPE = (
    "application/vnd.structural-analysis.frame3d-job-result+json"
)


class Frame3DDirectControlWorkerError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def execute_frame3d_direct_control_claim(
    service: DurableJobService,
    claim: JobClaim,
    *,
    worker_id: str,
    authorization_token: str,
    checkpoint_target_budget: int | None = None,
    lease_seconds: int = 300,
) -> JobView:
    """Execute up to the requested authored-target budget under one lease.

    Every ready nonterminal target is durably committed. Intermediate saves
    retain the lease; the requested partial boundary returns it. Each actual
    adaptive solve attempt renews the lease and consumes one immutable global
    reservation. A blocked interior cutback never replaces the last durable
    requested-target checkpoint. No running-solver cancellation is implied.
    """
    if type(service) is not DurableJobService or type(claim) is not JobClaim:
        raise Frame3DDirectControlWorkerError(
            "frame3d_worker_argument_invalid", "exact service/claim types required"
        )
    if checkpoint_target_budget is not None and (
        type(checkpoint_target_budget) is not int
        or not 1 <= checkpoint_target_budget <= 4096
    ):
        raise Frame3DDirectControlWorkerError(
            "frame3d_worker_target_budget_invalid",
            "target budget must be an integer in [1, 4096]",
        )
    if type(lease_seconds) is not int or not 5 <= lease_seconds <= 3600:
        raise Frame3DDirectControlWorkerError(
            "frame3d_worker_lease_duration_invalid",
            "lease_seconds must be an integer in [5, 3600]",
        )
    credentials = {
        "worker_id": worker_id,
        "authorization_token": authorization_token,
        "lease_token": claim.lease_token,
    }

    def fail_if_active(code: str) -> None:
        try:
            service.fail_job(
                claim.job.job_id, **credentials, error_code=code, retriable=False
            )
        except JobServiceError:
            # An expired/replaced lease must never mutate the replacement job.
            pass

    try:
        current = service.heartbeat(
            claim.job.job_id, **credentials, lease_seconds=lease_seconds
        )
        if (
            current.request != claim.job.request
            or current.checkpoint != claim.job.checkpoint
            or current.progress_completed != claim.job.progress_completed
            or current.progress_total != claim.job.progress_total
            or current.resume_contract_hash != claim.job.resume_contract_hash
        ):
            raise ValueError("claim projection differs from the live leased job")
        if (
            type(claim.request_bytes) is not bytes
            or len(claim.request_bytes) != current.request.byte_length
            or "sha256:" + hashlib.sha256(claim.request_bytes).hexdigest()
            != current.request.content_hash
        ):
            raise ValueError(
                "claim request bytes differ from their exact artifact reference"
            )
        request = strict_json_object_bytes(
            claim.request_bytes, maximum_bytes=16 * 1024 * 1024
        )
        if frame3d_job_canonical_bytes(request) != claim.request_bytes:
            raise ValueError(
                "claim request bytes are not the canonical immutable request"
            )
        document, config = validate_frame3d_job_request(request)
        total = len(config.control_targets)
        completed = current.progress_completed
        resume_hash = frame3d_job_resume_contract_hash(request)
        if (
            current.progress_total != total
            or not 0 <= completed < total
            or (current.checkpoint is None) != (claim.checkpoint_bytes is None)
            or (current.checkpoint is None and completed != 0)
            or (
                current.resume_contract_hash is not None
                and current.resume_contract_hash != resume_hash
            )
        ):
            raise ValueError(
                "claim target progress/checkpoint/resume contract mismatch"
            )
        budget = service.read_execution_budget(current.job_id, **credentials)
        receipts = []
        restart = None
        persisted_checkpoint = claim.checkpoint_bytes
        if persisted_checkpoint is not None:
            if (
                type(persisted_checkpoint) is not bytes
                or len(persisted_checkpoint) != current.checkpoint.byte_length
                or "sha256:" + hashlib.sha256(persisted_checkpoint).hexdigest()
                != current.checkpoint.content_hash
                or current.resume_contract_hash != resume_hash
            ):
                raise ValueError(
                    "claim checkpoint bytes differ from their exact artifact reference"
                )
            prefix = validate_frame3d_job_checkpoint(
                persisted_checkpoint,
                request=request,
                progress_completed=completed,
                execution_budget=budget,
            )
            receipts = prefix["receipts"]
            restart = frame3d_job_checkpoint_artifact(prefix)
        stop = (
            total
            if checkpoint_target_budget is None
            else min(total, completed + checkpoint_target_budget)
        )
        for index in range(completed + 1, stop + 1):
            reservations: list[int] = []

            def before_solve_attempt() -> None:
                service.heartbeat(
                    current.job_id, **credentials, lease_seconds=lease_seconds
                )
                ordinal = service.reserve_execution_attempt(
                    current.job_id, **credentials
                )
                reservations.append(ordinal)

            target_config = replace(
                config, control_targets=(config.control_targets[index - 1],)
            )
            result = analyze_bounded_frame3d_direct_control_model_ir(
                document,
                target_config,
                restart_checkpoint_artifact=restart,
                before_solve_attempt=before_solve_attempt,
            )
            validate_bounded_frame3d_direct_control_result(result)
            if result.status != "ready" or result.contract_pass is not True:
                raise Frame3DDirectControlWorkerError(
                    "frame3d_worker_target_blocked",
                    result.terminal_reason_code or "target did not commit exactly",
                )
            receipts.append(
                build_frame3d_job_receipt(
                    request,
                    target_index=index,
                    result=result,
                    restart_checkpoint=restart,
                    reserved_attempt_ordinals=reservations,
                )
            )
            budget = service.read_execution_budget(current.job_id, **credentials)
            terminal = index == total
            payload = build_frame3d_job_payload(
                request,
                receipts=receipts,
                execution_budget=budget,
                complete=terminal,
            )
            if terminal:
                report = validate_frame3d_job_result(
                    payload,
                    request=request,
                    execution_budget=budget,
                    checkpoint=persisted_checkpoint,
                )
                result_bytes = frame3d_job_canonical_bytes(payload)
                evidence = build_job_completion_evidence(
                    job_id=current.job_id,
                    request_hash=current.request.content_hash,
                    checkpoint_hash=current.checkpoint.content_hash
                    if current.checkpoint
                    else None,
                    result_bytes=result_bytes,
                    validation_report=report,
                    validator_id=FRAME3D_JOB_VALIDATOR_ID,
                )
                return service.complete_job(
                    current.job_id,
                    **credentials,
                    result_bytes=result_bytes,
                    result_media_type=FRAME3D_RESULT_MEDIA_TYPE,
                    evidence=evidence,
                )
            validate_frame3d_job_checkpoint(
                payload,
                request=request,
                progress_completed=index,
                execution_budget=budget,
            )
            checkpoint_bytes = frame3d_job_canonical_bytes(payload)
            current = service.save_checkpoint(
                current.job_id,
                **credentials,
                checkpoint_bytes=checkpoint_bytes,
                checkpoint_media_type=FRAME3D_CHECKPOINT_MEDIA_TYPE,
                progress_completed=index,
                progress_total=total,
                resume_contract_hash=resume_hash,
                release_lease=index == stop,
            )
            persisted_checkpoint = checkpoint_bytes
            restart = result.checkpoint_artifact_bytes()
            if index == stop:
                return current
        raise ValueError(
            "bounded Frame3D worker made no target progress"
        )  # pragma: no cover
    except JobServiceError as error:
        fail_if_active(error.code)
        raise
    except Frame3DDirectControlWorkerError as error:
        fail_if_active(error.code)
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        fail_if_active("frame3d_worker_contract_invalid")
        raise Frame3DDirectControlWorkerError(
            "frame3d_worker_contract_invalid", str(error)
        ) from error
    except Exception:
        fail_if_active("frame3d_worker_execution_failed")
        raise


__all__ = ["Frame3DDirectControlWorkerError", "execute_frame3d_direct_control_claim"]
