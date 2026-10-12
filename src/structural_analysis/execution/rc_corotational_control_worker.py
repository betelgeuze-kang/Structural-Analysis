"""Leased corotational RC execution with durable invocation reservations.

Each analysis and numerical verification reserves an API invocation. Source
replay costs are retained separately. Opted-in v7 phases use isolated supervised
children and retain their measured reply or unaccounted cleanup failure. The
managed generation guard, when present, spans child cleanup and publication.
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
from structural_analysis.execution import (
    rc_corotational_phase_supervisor as phase_runner,
)
from structural_analysis.execution.rc_fiber_phase_supervisor import RCFiberPhaseError
from structural_analysis.execution.rc_corotational_job_request import (
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)
from structural_analysis.execution.rc_corotational_job_contract import (
    RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION,
    ISOLATED_RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION,
    RC_COROTATIONAL_PHASE_SUPERVISION_SCHEMA_VERSION,
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
    with guard as authority_fd:
        return _execute(
            service,
            claim,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_seconds=lease_seconds,
            authority_fd=authority_fd,
        )


def _execute(
    service, claim, *, worker_id, authorization_token, lease_seconds, authority_fd
):
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
        with _LeaseKeeper(
            service, job_id, credentials, lease_seconds, initial_lease=current
        ) as lease:
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
            phase_policy = typed.execution_config.phase_execution_policy
            if phase_policy is not None:
                phase_runner.validate_corotational_phase_host(
                    phase_policy, authority_fd=authority_fd
                )
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
                planned,
                schema_version=(
                    ISOLATED_RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION
                    if phase_policy is not None
                    else RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION
                ),
            )
            binding["completed_after"] = binding.pop("planned_after")
            phase_replies = {}

            def supervision(phase, reply, wall_ns, error=None):
                return {
                    "schema_version": RC_COROTATIONAL_PHASE_SUPERVISION_SCHEMA_VERSION,
                    "phase": phase,
                    "job_request_hash": typed.request_hash,
                    "chunk_request_hash": planned["chunk_request_hash"],
                    "completed_before": planned["completed_before"],
                    "planned_after": planned["planned_after"],
                    "restart_input_sha256": planned["restart_input_sha256"],
                    "policy": phase_policy.to_dict(),
                    "status": reply.status if reply is not None else "unaccounted",
                    "supervisor": reply.supervisor_timing
                    if reply is not None
                    else {
                        "wall_ns": wall_ns,
                        "scope": "parent phase failure; child CPU unavailable",
                    },
                    "cleanup": error.cleanup
                    if isinstance(error, RCFiberPhaseError)
                    else {},
                }

            def isolated(phase, *, result=None, checkpoint=None):
                reply = phase_runner.run_rc_corotational_phase(
                    phase=phase,
                    request_bytes=claim.request_bytes,
                    completed_before=current.progress_completed,
                    completed_after=planned["planned_after"],
                    restart=restart,
                    result=result,
                    checkpoint=checkpoint,
                    policy=phase_policy,
                    lease_check=lease.check,
                    authority_fd=authority_fd,
                )
                phase_replies[phase] = reply
                if reply.status == "raised":
                    raise RCCorotationalWorkerError(
                        f"rc_corotational_worker_{phase}_raised"
                    )
                return reply

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
                    wall_ns = time.perf_counter_ns() - wall
                    reply = phase_replies.get(phase)
                    # A measured raised child is distinct from a missing,
                    # malformed or rejected return. The latter never invents
                    # CPU time and cannot become an accepted receipt.
                    measured_error = (
                        reply
                        if reply is not None and reply.status == "raised"
                        else None
                    )
                    outcome["timing"] = (
                        measured_error.timing
                        if measured_error is not None
                        else dict(
                            wall_ns=wall_ns,
                            process_cpu_ns=None
                            if phase_policy is not None
                            else time.process_time_ns() - cpu,
                        )
                    )
                    outcome["error"] = {"type": type(error).__name__}
                    if isinstance(error, api.RCCorotationalControlExecutionError):
                        outcome["error"]["work"] = error.work
                    if phase_policy is not None:
                        outcome["phase_supervision"] = supervision(
                            phase, measured_error, wall_ns, error
                        )
                        if measured_error is not None:
                            outcome["error"] = {"type": measured_error.error_type}
                            if measured_error.artifact_error_report is not None:
                                outcome["error"]["work"] = (
                                    measured_error.artifact_error_report
                                )
                        if isinstance(error, RCFiberPhaseError):
                            outcome["error"]["code"] = error.code
                    service.record_rc_invocation_outcome(
                        job_id, **credentials, ordinal=ordinal, outcome=outcome
                    )
                    raise
                outcome.update(fields)
                outcome["status"] = "returned"
                reply = phase_replies.get(phase)
                outcome["timing"] = (
                    reply.timing
                    if phase_policy is not None
                    else dict(
                        wall_ns=time.perf_counter_ns() - wall,
                        process_cpu_ns=time.process_time_ns() - cpu,
                    )
                )
                if phase_policy is not None:
                    outcome["phase_supervision"] = supervision(phase, reply, 0)
                service.record_rc_invocation_outcome(
                    job_id, **credentials, ordinal=ordinal, outcome=outcome
                )
                lease.check()
                return value, outcome, ordinal

            def analyze():
                result = (
                    api.RCCorotationalControlArtifacts(
                        (reply := isolated("analysis")).raw_result,
                        reply.native_checkpoint,
                    )
                    if phase_policy is not None
                    else api.analyze_rc_corotational_control(
                        typed.model,
                        typed.targets_m,
                        restart=restart,
                        **typed.api_kwargs(),
                    )
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
                report = (
                    isolated(
                        "verification",
                        result=artifacts.result_bytes,
                        checkpoint=artifacts.continuation_bytes,
                    ).verification_report
                    if phase_policy is not None
                    else api.validate_rc_corotational_control_artifacts(
                        typed.model,
                        typed.targets_m,
                        result=artifacts.result_bytes,
                        continuation=artifacts.continuation_bytes,
                        restart=restart,
                        **typed.api_kwargs(),
                    )
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
    except (JobServiceError, RCCorotationalWorkerError, RCFiberPhaseError) as error:
        fail_active(error.code)
        raise
    except Exception:
        fail_active("rc_corotational_execution_failed")
        raise
