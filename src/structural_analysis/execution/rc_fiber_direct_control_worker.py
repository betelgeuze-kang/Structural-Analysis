"""Durable fixed-chunk execution of the original experimental RC control API.

A reservation is one API invocation, not one Newton or target solve. Each chunk
replays its entire accepted prefix and receives a separate fresh numerical
verification before durable progress advances. Failed and abandoned invocations
remain evidence; they do not replace the last verified checkpoint.
"""

from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
from threading import Event, Thread
import time

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobClaim,
    JobServiceError,
    JobView,
    build_job_completion_evidence,
)
from structural_analysis.execution.rc_fiber_job_contract import (
    RC_FIBER_JOB_VALIDATOR_ID,
    build_rc_fiber_job_payload,
    build_rc_fiber_job_receipt,
    rc_fiber_job_canonical_bytes,
    rc_fiber_job_resume_contract_hash,
    validate_rc_fiber_job_checkpoint,
    validate_rc_fiber_job_request,
    validate_rc_fiber_job_result,
)


RC_FIBER_CHECKPOINT_MEDIA_TYPE = (
    "application/vnd.structural-analysis.rc-fiber-job-checkpoint+json"
)
RC_FIBER_RESULT_MEDIA_TYPE = (
    "application/vnd.structural-analysis.rc-fiber-job-result+json"
)


class RCFiberDirectControlWorkerError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _hash(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class _LeaseKeeper:
    """Renew independently of long numerical calls without pretending to cancel them."""

    def __init__(self, service, job_id, credentials, lease_seconds):
        self.service = service
        self.job_id = job_id
        self.credentials = credentials
        self.lease_seconds = lease_seconds
        self.stopped = Event()
        self.failure = None
        self.thread = Thread(target=self._run, name="rc-fiber-job-lease", daemon=True)

    def _run(self):
        while not self.stopped.wait(min(30.0, self.lease_seconds / 3.0)):
            try:
                self.service.heartbeat(
                    self.job_id,
                    **self.credentials,
                    lease_seconds=self.lease_seconds,
                )
            except Exception as error:
                self.failure = error
                return

    def check(self):
        if self.failure is not None:
            raise JobServiceError(
                "rc_fiber_worker_lease_renewal_failed",
                "/lease",
                "The worker could not renew its lease; computed work cannot publish.",
            ) from self.failure

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.stopped.set()
        self.thread.join()


def execute_rc_fiber_direct_control_claim(
    service: DurableJobService,
    claim: JobClaim,
    *,
    worker_id: str,
    authorization_token: str,
    checkpoint_target_budget: int | None = None,
    lease_seconds: int = 300,
) -> JobView:
    """Run one immutable chunk per lease, then release or publish completion.

    The optional dispatcher budget must equal the authored chunk size. Cancellation
    is between chunks. A lost lease cannot interrupt an in-flight solver, but it
    prevents publishing into a replacement lease. Each outcome records API plus
    artifact-extraction wall/process time; durable storage/transport costs are
    separate and are not represented as solver time.
    """
    if type(service) is not DurableJobService or type(claim) is not JobClaim:
        raise RCFiberDirectControlWorkerError(
            "rc_fiber_worker_argument_invalid", "exact service/claim types required"
        )
    if checkpoint_target_budget is not None and (
        type(checkpoint_target_budget) is not int
        or not 1 <= checkpoint_target_budget <= 255
    ):
        raise RCFiberDirectControlWorkerError(
            "rc_fiber_worker_target_budget_invalid",
            "target budget must be an integer in [1, 255]",
        )
    if type(lease_seconds) is not int or not 5 <= lease_seconds <= 3600:
        raise RCFiberDirectControlWorkerError(
            "rc_fiber_worker_lease_duration_invalid",
            "lease_seconds must be an integer in [5, 3600]",
        )
    credentials = {
        "worker_id": worker_id,
        "authorization_token": authorization_token,
        "lease_token": claim.lease_token,
    }
    job_id = claim.job.job_id

    def fail_if_active(code):
        try:
            service.fail_job(job_id, **credentials, error_code=code, retriable=False)
        except JobServiceError:
            pass  # A stale lease must never mutate its replacement.

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
            raise ValueError("claim projection differs from the live leased job")
        with _LeaseKeeper(service, job_id, credentials, lease_seconds) as lease:
            if (
                type(claim.request_bytes) is not bytes
                or len(claim.request_bytes) != current.request.byte_length
                or _hash(claim.request_bytes) != current.request.content_hash
            ):
                raise ValueError("claim request bytes differ from their reference")
            request = strict_json_object_bytes(
                claim.request_bytes, maximum_bytes=16 * 1024 * 1024
            )
            if rc_fiber_job_canonical_bytes(request) != claim.request_bytes:
                raise ValueError("immutable request is not canonical JSON")
            model, config = validate_rc_fiber_job_request(request)
            chunk_size = request["execution_config"]["chunk_target_count"]
            if checkpoint_target_budget not in (None, chunk_size):
                raise ValueError("dispatcher target budget changes the authored chunks")
            total, completed = len(config.targets_m), current.progress_completed
            resume_hash = rc_fiber_job_resume_contract_hash(request)
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
                raise ValueError("claim target/checkpoint/resume contract mismatch")
            budget = service.read_execution_budget(job_id, **credentials)
            receipts, restart = [], None
            if claim.checkpoint_bytes is not None:
                if (
                    type(claim.checkpoint_bytes) is not bytes
                    or len(claim.checkpoint_bytes) != current.checkpoint.byte_length
                    or _hash(claim.checkpoint_bytes) != current.checkpoint.content_hash
                    or current.resume_contract_hash != resume_hash
                ):
                    raise ValueError(
                        "claim checkpoint bytes differ from their reference"
                    )
                prefix = validate_rc_fiber_job_checkpoint(
                    claim.checkpoint_bytes,
                    request=request,
                    progress_completed=completed,
                    execution_budget=budget,
                )
                receipts = prefix["receipts"]
                restart = base64.b64decode(
                    prefix["terminal_checkpoint_artifact_base64"], validate=True
                )
            if budget["remaining_attempts"] < 2:
                raise RCFiberDirectControlWorkerError(
                    "execution_attempt_budget_exhausted",
                    "A chunk requires separate analysis and verification reservations.",
                )
            stop = min(total, completed + chunk_size)
            chunk = replace(config, targets_m=config.targets_m[completed:stop])
            binding = {
                "schema_version": "bounded-rc-fiber-job-invocation.v1",
                "job_request_hash": current.request.content_hash,
                "chunk_request_hash": chunk.request_hash,
                "completed_before": completed,
                "completed_after": stop,
                "restart_input_sha256": None if restart is None else _hash(restart),
            }

            def invoke(phase, call):
                lease.check()
                ordinal = service.reserve_execution_attempt(job_id, **credentials)
                outcome = binding | {
                    "phase": phase,
                    "status": "raised",
                    "api_result": None,
                    "checkpoint_artifact_base64": None,
                    "verification_report": None,
                    "error": None,
                    "unavailable_execution_work": True,
                }
                wall, cpu = time.perf_counter_ns(), time.process_time_ns()
                try:
                    value, fields = call()
                except Exception as error:
                    outcome["timing"] = {
                        "wall_ns": time.perf_counter_ns() - wall,
                        "process_cpu_ns": time.process_time_ns() - cpu,
                    }
                    outcome["error"] = {"type": type(error).__name__}
                    if isinstance(error, api.BoundedRCFiberDirectControlArtifactError):
                        outcome["error"]["report"] = error.to_dict()
                    service.record_rc_invocation_outcome(
                        job_id, **credentials, ordinal=ordinal, outcome=outcome
                    )
                    raise
                outcome.update(fields)
                outcome["status"] = "returned"
                outcome["timing"] = {
                    "wall_ns": time.perf_counter_ns() - wall,
                    "process_cpu_ns": time.process_time_ns() - cpu,
                }
                service.record_rc_invocation_outcome(
                    job_id, **credentials, ordinal=ordinal, outcome=outcome
                )
                lease.check()
                return value, outcome, ordinal

            def analyze():
                result = api.analyze_bounded_rc_fiber_direct_control(
                    model, chunk.targets_m, restart=restart, **chunk.api_kwargs()
                )
                payload = result.to_dict()
                raw = result.result_artifact_bytes()
                checkpoint = (
                    result.checkpoint_artifact_bytes()
                    if payload["checkpoint"] is not None
                    else None
                )
                return (result, payload, raw, checkpoint), {
                    "api_result": payload,
                    "checkpoint_artifact_base64": (
                        base64.b64encode(checkpoint).decode("ascii")
                        if checkpoint is not None
                        else None
                    ),
                    "unavailable_execution_work": (
                        payload["metrics"].get("unavailable_execution_work", False)
                        or payload["metrics"].get("control_work") is None
                        or (payload["metrics"].get("control_work") or {}).get(
                            "unknown_solver_work_attempt_count", 0
                        )
                        > 0
                    ),
                }

            (result, api_payload, raw, checkpoint), analysis, analysis_ordinal = invoke(
                "analysis", analyze
            )

            def verify():
                report = api.validate_bounded_rc_fiber_direct_control_artifacts(
                    model,
                    chunk.targets_m,
                    result=raw,
                    checkpoint=checkpoint,
                    restart=restart,
                    **chunk.api_kwargs(),
                ).to_dict()
                return report, {
                    "verification_report": report,
                    "unavailable_execution_work": (
                        report["unavailable_execution_work"]
                        or (report.get("replay_control_work") or {}).get(
                            "unknown_solver_work_attempt_count", 0
                        )
                        > 0
                    ),
                }

            verification, verified, verification_ordinal = invoke(
                "verification", verify
            )
            if (
                api_payload["status"] != "ready"
                or api_payload["contract_pass"] is not True
            ):
                raise RCFiberDirectControlWorkerError(
                    "rc_fiber_worker_chunk_blocked",
                    "The authored chunk did not complete; its attempted work is retained.",
                )
            if any(
                verification.get(key) is not True
                for key in (
                    "artifact_contract_pass",
                    "contract_pass",
                    "physical_path_complete",
                    "fresh_source_execution_invoked",
                    "solver_replay_performed",
                )
            ):
                raise RCFiberDirectControlWorkerError(
                    "rc_fiber_worker_verification_failed",
                    "Fresh complete source verification did not pass.",
                )
            receipts.append(
                build_rc_fiber_job_receipt(
                    request,
                    completed_before=completed,
                    result=result,
                    verification_report=verification,
                    restart_checkpoint=restart,
                    analysis_ordinal=analysis_ordinal,
                    verification_ordinal=verification_ordinal,
                    analysis_timing=analysis["timing"],
                    verification_timing=verified["timing"],
                )
            )
            budget = service.read_execution_budget(job_id, **credentials)
            terminal = stop == total
            payload = build_rc_fiber_job_payload(
                request,
                receipts=receipts,
                execution_budget=budget,
                terminal_checkpoint=checkpoint,
                api_result=api_payload if terminal else None,
                complete=terminal,
            )
            lease.check()
            if terminal:
                report = validate_rc_fiber_job_result(
                    payload,
                    request=request,
                    execution_budget=budget,
                    checkpoint=claim.checkpoint_bytes,
                )
                result_bytes = rc_fiber_job_canonical_bytes(payload)
                evidence = build_job_completion_evidence(
                    job_id=job_id,
                    request_hash=current.request.content_hash,
                    checkpoint_hash=(
                        current.checkpoint.content_hash if current.checkpoint else None
                    ),
                    result_bytes=result_bytes,
                    validation_report=report,
                    validator_id=RC_FIBER_JOB_VALIDATOR_ID,
                )
                lease.check()
                return service.complete_job(
                    job_id,
                    **credentials,
                    result_bytes=result_bytes,
                    result_media_type=RC_FIBER_RESULT_MEDIA_TYPE,
                    evidence=evidence,
                )
            return service.save_checkpoint(
                job_id,
                **credentials,
                checkpoint_bytes=rc_fiber_job_canonical_bytes(payload),
                checkpoint_media_type=RC_FIBER_CHECKPOINT_MEDIA_TYPE,
                progress_completed=stop,
                progress_total=total,
                resume_contract_hash=resume_hash,
                release_lease=True,
            )
    except (JobServiceError, RCFiberDirectControlWorkerError) as error:
        fail_if_active(error.code)
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        fail_if_active("rc_fiber_worker_contract_invalid")
        raise RCFiberDirectControlWorkerError(
            "rc_fiber_worker_contract_invalid",
            "The RC job execution contract is invalid.",
        ) from error
    except Exception:
        fail_if_active("rc_fiber_worker_execution_failed")
        raise


__all__ = ["RCFiberDirectControlWorkerError", "execute_rc_fiber_direct_control_claim"]
