"""Leased corotational RC execution with durable invocation reservations.

Each analysis and numerical verification reserves an API invocation. Source
replay costs are retained separately. Managed generation/guard and process-child
resource handling require the corresponding service/phase integration; this
worker does not infer those guarantees from ordinary leases.
"""

import base64
from contextlib import nullcontext
import hashlib
import time

from structural_analysis.api import rc_corotational_control as api
from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobClaim,
    JobServiceError,
    build_job_completion_evidence,
)
from structural_analysis.execution.rc_fiber_direct_control_worker import _LeaseKeeper
from structural_analysis.execution.rc_corotational_job_request import (
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)
from structural_analysis.execution.rc_corotational_job_contract import (
    RC_COROTATIONAL_JOB_VALIDATOR_ID,
    rc_corotational_chunk_binding,
    build_rc_corotational_job_receipt,
    build_rc_corotational_job_payload,
    validate_rc_corotational_job_checkpoint,
    validate_rc_corotational_job_result,
)


class RCCorotationalWorkerError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def execute_rc_corotational_control_claim(
    service, claim, *, worker_id, authorization_token, lease_seconds=300
):
    if type(service) is not DurableJobService or type(claim) is not JobClaim:
        raise RCCorotationalWorkerError("rc_corotational_worker_argument_invalid")
    if type(lease_seconds) is not int or not 5 <= lease_seconds <= 3600:
        raise RCCorotationalWorkerError("rc_corotational_worker_lease_invalid")
    # Older unmanaged services retain lease custody only. A managed service's
    # generation lock must span calls, publication and heartbeat cleanup.
    guard = (
        service.execution_guard()
        if hasattr(service, "execution_guard")
        else nullcontext()
    )
    with guard:
        return _execute(
            service,
            claim,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_seconds=lease_seconds,
        )


def _execute(service, claim, *, worker_id, authorization_token, lease_seconds):
    job_id = claim.job.job_id
    credentials = dict(
        worker_id=worker_id,
        authorization_token=authorization_token,
        lease_token=claim.lease_token,
    )

    def fail_active(code):
        try:
            service.fail_job(job_id, **credentials, error_code=code, retriable=False)
        except JobServiceError:
            pass  # A stale lease cannot mutate its replacement.

    try:
        current = service.heartbeat(job_id, **credentials, lease_seconds=lease_seconds)
        if any(
            getattr(current, name) != getattr(claim.job, name)
            for name in (
                "request",
                "checkpoint",
                "progress_completed",
                "progress_total",
                "resume_contract_hash",
                "attempt",
            )
        ):
            raise RCCorotationalWorkerError("rc_corotational_claim_projection_changed")
        with _LeaseKeeper(service, job_id, credentials, lease_seconds) as lease:
            typed = validate_rc_corotational_job_request(claim.request_bytes)
            if (
                typed.request_bytes != claim.request_bytes
                or typed.request_hash != current.request.content_hash
                or len(claim.request_bytes) != current.request.byte_length
                or current.progress_total != typed.progress_total
            ):
                raise RCCorotationalWorkerError(
                    "rc_corotational_request_binding_changed"
                )
            request = typed.to_dict()
            budget = service.read_execution_budget(job_id, **credentials)
            receipts, restart = [], None
            if current.checkpoint is not None:
                if (
                    type(claim.checkpoint_bytes) is not bytes
                    or len(claim.checkpoint_bytes) != current.checkpoint.byte_length
                    or "sha256:" + hashlib.sha256(claim.checkpoint_bytes).hexdigest()
                    != current.checkpoint.content_hash
                ):
                    raise RCCorotationalWorkerError(
                        "rc_corotational_checkpoint_binding_changed"
                    )
                prior = validate_rc_corotational_job_checkpoint(
                    claim.checkpoint_bytes,
                    request=request,
                    progress_completed=current.progress_completed,
                    resume_contract_hash=typed.resume_contract_hash,
                    execution_budget=budget,
                )["payload"]
                receipts = list(prior["receipts"])
                restart = base64.b64decode(
                    prior["terminal_checkpoint_artifact_base64"], validate=True
                )
            elif current.progress_completed != 0:
                raise RCCorotationalWorkerError(
                    "rc_corotational_progress_without_checkpoint"
                )
            planned = dict(
                rc_corotational_chunk_binding(
                    request, current.progress_completed, restart
                )
            )
            binding = dict(
                planned, schema_version="bounded-rc-corotational-job-invocation.v1"
            )
            binding["completed_after"] = binding.pop("planned_after")

            def invoke(phase, call):
                lease.check()
                ordinal = service.reserve_execution_attempt(job_id, **credentials)
                outcome = dict(
                    binding,
                    phase=phase,
                    status="raised",
                    api_result=None,
                    checkpoint_artifact_base64=None,
                    verification_report=None,
                    error=None,
                    unavailable_execution_work=True,
                )
                wall, cpu = time.perf_counter_ns(), time.process_time_ns()
                try:
                    value, fields = call()
                except Exception as error:
                    outcome["timing"] = dict(
                        wall_ns=time.perf_counter_ns() - wall,
                        process_cpu_ns=time.process_time_ns() - cpu,
                    )
                    outcome["error"] = {"type": type(error).__name__}
                    if isinstance(error, api.RCCorotationalControlExecutionError):
                        outcome["error"]["work"] = error.work
                    service.record_rc_invocation_outcome(
                        job_id, **credentials, ordinal=ordinal, outcome=outcome
                    )
                    raise
                outcome.update(fields)
                outcome["status"] = "returned"
                outcome["timing"] = dict(
                    wall_ns=time.perf_counter_ns() - wall,
                    process_cpu_ns=time.process_time_ns() - cpu,
                )
                service.record_rc_invocation_outcome(
                    job_id, **credentials, ordinal=ordinal, outcome=outcome
                )
                lease.check()
                return value, outcome, ordinal

            def analyze():
                result = api.analyze_rc_corotational_control(
                    typed.model, typed.targets_m, restart=restart, **typed.api_kwargs()
                )
                payload = strict_json_object_bytes(
                    result.result_bytes, maximum_bytes=api.MAX_BYTES
                )
                return result, {
                    "api_result": payload,
                    "checkpoint_artifact_base64": None
                    if result.continuation_bytes is None
                    else base64.b64encode(result.continuation_bytes).decode(),
                    "unavailable_execution_work": payload["work"][
                        "unavailable_execution_work"
                    ],
                }

            artifacts, analysis, analysis_ordinal = invoke("analysis", analyze)

            def verify():
                report = api.validate_rc_corotational_control_artifacts(
                    typed.model,
                    typed.targets_m,
                    result=artifacts.result_bytes,
                    continuation=artifacts.continuation_bytes,
                    restart=restart,
                    **typed.api_kwargs(),
                )
                return report, {
                    "verification_report": report,
                    "unavailable_execution_work": report["replay_work"][
                        "unavailable_execution_work"
                    ],
                }

            report, verified, verification_ordinal = invoke("verification", verify)
            payload = analysis["api_result"]
            if (
                report["artifact_contract_pass"] is not True
                or report["fresh_source_execution_invoked"] is not True
                or report["solver_replay_performed"] is not True
                or payload["status"] not in ("paused", "ready")
            ):
                raise RCCorotationalWorkerError("rc_corotational_chunk_not_verified")
            receipts.append(
                build_rc_corotational_job_receipt(
                    request,
                    completed_before=current.progress_completed,
                    analysis_ordinal=analysis_ordinal,
                    verification_ordinal=verification_ordinal,
                    analysis_outcome=analysis,
                    verification_outcome=verified,
                )
            )
            budget = service.read_execution_budget(job_id, **credentials)
            complete = payload["contract_pass"] is True
            job_payload = build_rc_corotational_job_payload(
                request,
                receipts=receipts,
                execution_budget=budget,
                terminal_checkpoint=artifacts.continuation_bytes,
                api_result=payload if complete else None,
                complete=complete,
            )
            lease.check()
            if complete:
                pure_report = validate_rc_corotational_job_result(
                    job_payload,
                    request=request,
                    execution_budget=budget,
                    checkpoint=claim.checkpoint_bytes,
                )
                raw = rc_corotational_job_canonical_bytes(job_payload)
                evidence = build_job_completion_evidence(
                    job_id=job_id,
                    request_hash=current.request.content_hash,
                    checkpoint_hash=current.checkpoint.content_hash
                    if current.checkpoint
                    else None,
                    result_bytes=raw,
                    validation_report=pure_report,
                    validator_id=RC_COROTATIONAL_JOB_VALIDATOR_ID,
                )
                return service.complete_job(
                    job_id,
                    **credentials,
                    result_bytes=raw,
                    result_media_type="application/vnd.structural-analysis.rc-corotational-job-result+json",
                    evidence=evidence,
                )
            return service.save_checkpoint(
                job_id,
                **credentials,
                checkpoint_bytes=rc_corotational_job_canonical_bytes(job_payload),
                checkpoint_media_type="application/vnd.structural-analysis.rc-corotational-job-checkpoint+json",
                progress_completed=payload["total_control_attempts"],
                progress_total=typed.progress_total,
                resume_contract_hash=typed.resume_contract_hash,
            )
    except (JobServiceError, RCCorotationalWorkerError) as error:
        fail_active(error.code)
        raise
    except Exception:
        fail_active("rc_corotational_execution_failed")
        raise
