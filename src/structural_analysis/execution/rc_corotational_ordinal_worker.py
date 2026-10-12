"""Managed ordinal worker and bounded child transport.

The existing shared-generation guard and job permit span launch through reaping
and publication. API entries and production/verification solver ceilings are
separate, nonrefundable reservations. Verification replays only the attached
trusted suffix. No self-hash confers execution or restart authority.
"""

from __future__ import annotations

import base64
from pathlib import Path
import sys
import time

from structural_analysis.execution import rc_fiber_phase_supervisor as common
from structural_analysis.execution.rc_corotational_phase_supervisor import (
    validate_corotational_phase_host,
)
from structural_analysis.execution.rc_corotational_phase_policy import (
    decode_rc_corotational_phase_policy,
)

_MIB = 1024 * 1024
_REQUEST_MAX_BYTES = 16 * _MIB
_NATIVE_MAX_BYTES = 16 * _MIB
_RESULT_MAX_BYTES = 64 * _MIB
_REPORT_MAX_BYTES = 64 * _MIB
_FRAME_SEGMENTS_MAX_BYTES = 112 * _MIB
_METADATA_MAX_BYTES = 64 * 1024
_MAGIC = b"SA-RC-ORDL-1\x00\x00\x00\x00"
_SCHEMA = "bounded-rc-ordinal-phase-transport.v1"
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_FILES = {
    "worker": "execution/rc_corotational_ordinal_worker.py",
    "supervision": "execution/rc_fiber_phase_supervisor.py",
    "bootstrap": "execution/_rc_fiber_phase_bootstrap.py",
    "api": "api/rc_corotational_ordinal_control.py",
    "request": "execution/rc_corotational_ordinal_job_request.py",
    "contract": "execution/rc_corotational_ordinal_job_contract.py",
    "driver": "assembly/stateful_corotational_fiber_frame2d_ordinal_driver.py",
}


def _source_hashes():
    return {
        name: common._hash((_SOURCE_ROOT / "structural_analysis" / path).read_bytes())
        for name, path in _SOURCE_FILES.items()
    }


def _child_argv(parent_pid):
    return [
        sys.executable,
        "-I",
        str(common._BOOTSTRAP_PATH),
        str(parent_pid),
        str(_SOURCE_ROOT),
        str(Path(__file__).resolve()),
        common._json(common._dependency_paths()).decode(),
    ]


class _FrameReceiver(common._FrameReceiver):
    def _header_ready(self):
        magic, metadata_length, *lengths = common._HEADER.unpack(self.header)
        caps = (
            (
                _REQUEST_MAX_BYTES,
                _NATIVE_MAX_BYTES,
                _RESULT_MAX_BYTES,
                _NATIVE_MAX_BYTES,
            )
            if self.direction == "input"
            else (
                _RESULT_MAX_BYTES,
                _NATIVE_MAX_BYTES,
                _REPORT_MAX_BYTES,
                _REPORT_MAX_BYTES,
            )
        )
        if (
            magic != _MAGIC
            or not 1 <= metadata_length <= _METADATA_MAX_BYTES
            or any(v > cap for v, cap in zip(lengths, caps, strict=True))
            or sum(lengths) > _FRAME_SEGMENTS_MAX_BYTES
        ):
            raise ValueError("ordinal frame bounds invalid")
        if self.direction == "input":
            if not lengths[0] or (self.phase == "analysis" and any(lengths[2:])):
                raise ValueError("ordinal input roles invalid")
            if self.phase == "verification" and (not lengths[2] or not lengths[3]):
                raise ValueError("ordinal verification requires original artifacts")
        elif (
            lengths[3]
            or (self.phase == "analysis" and lengths[2])
            or (self.phase == "verification" and any(lengths[:2]))
        ):
            raise ValueError("ordinal output roles invalid")
        self.metadata_length, self.lengths = metadata_length, tuple(lengths)


def _frame_parts(metadata, segments):
    if len(segments) != 4 or any(
        v is not None and (type(v) is not bytes or not v) for v in segments
    ):
        raise ValueError("ordinal frame requires four immutable segment roles")
    raw = common._json(metadata)
    lengths = tuple(0 if v is None else len(v) for v in segments)
    header = common._HEADER.pack(_MAGIC, len(raw), *lengths)
    check = _FrameReceiver(
        "output" if "status" in metadata else "input", metadata["identity"]["phase"]
    )
    check.header = bytearray(header)
    check._header_ready()
    return (header, raw, *(v for v in segments if v is not None))


def _input_metadata(phase, request_bytes, restart, result, checkpoint, grant, policy):
    from structural_analysis.execution.rc_corotational_ordinal_job_request import (
        validate_rc_corotational_ordinal_job_request,
    )
    from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
        _grant,
        ordinal_chunk_hash,
    )

    typed = validate_rc_corotational_ordinal_job_request(request_bytes)
    _grant(grant, typed)
    role = "production" if phase == "analysis" else "verification"
    if (
        grant["phase"] != role
        or typed.execution_config.phase_execution_policy.to_dict() != policy.to_dict()
        or common._hash(restart) != grant["native_input_sha256"]
    ):
        raise ValueError("ordinal source/policy/granted input differs")
    return {
        "schema_version": _SCHEMA,
        "identity": {
            "phase": phase,
            "job_request_hash": typed.request_hash,
            "chunk_request_hash": ordinal_chunk_hash(typed, grant),
            "source_revision": typed.source_revision,
            "context_hash": typed.context_hash,
            "grant": grant,
            "analysis_result_sha256": common._hash(result),
            "analysis_checkpoint_sha256": common._hash(checkpoint),
            "source_hashes": _source_hashes(),
        },
        "policy": policy.to_dict(),
        "segment_hashes": [
            common._hash(v) for v in (request_bytes, restart, result, checkpoint)
        ],
    }


def _check_reply(metadata, segments, expected, started_ns, received_ns):
    if (
        set(metadata)
        != {
            "schema_version",
            "identity",
            "policy",
            "segment_hashes",
            "status",
            "timing",
            "measurement",
            "error_type",
        }
        or metadata["schema_version"] != _SCHEMA
        or common._json(metadata["policy"]) != common._json(expected["policy"])
        or segments[3] is not None
    ):
        raise ValueError("ordinal reply namespace/policy differs")
    projected = dict(metadata, schema_version=common._SCHEMA)
    projected.pop("policy")
    return common._check_reply(
        projected,
        segments,
        dict(expected, schema_version=common._SCHEMA),
        started_ns,
        received_ns,
    )


def run_ordinal_phase(
    *,
    phase,
    request_bytes,
    restart,
    grant,
    policy,
    lease_check,
    authority_fd,
    job_guard_fd,
    result=None,
    checkpoint=None,
):
    started = time.perf_counter_ns()
    validate_corotational_phase_host(
        policy, authority_fd=authority_fd, job_guard_fd=job_guard_fd
    )
    if authority_fd is None or job_guard_fd is None:
        raise common.RCFiberPhaseError(
            "rc_ordinal_worker_guard_required",
            "Managed distinct lifetime descriptors required",
        )
    if phase not in ("production", "verification") or not callable(lease_check):
        raise ValueError("ordinal phase invalid")
    transport = "analysis" if phase == "production" else phase
    if (phase == "production" and (result is not None or checkpoint is not None)) or (
        phase == "verification" and (result is None or checkpoint is None)
    ):
        raise ValueError("ordinal phase artifacts invalid")
    expected = _input_metadata(
        transport, request_bytes, restart, result, checkpoint, grant, policy
    )
    parts = _frame_parts(expected, (request_bytes, restart, result, checkpoint))
    timeout = (
        policy.analysis_timeout_ms
        if phase == "production"
        else policy.verification_timeout_ms
    )

    def check():
        try:
            lease_check()
        except Exception as exc:
            raise common.RCFiberPhaseError(
                "rc_ordinal_worker_" + transport + "_lease_lost", "Lease lost"
            ) from exc

    return common._supervise(
        transport,
        parts,
        expected,
        started,
        started + timeout * 1_000_000,
        policy.termination_grace_ms,
        check,
        authority_fd,
        backend=common._PhaseBackend(
            "rc_ordinal_worker_", _FrameReceiver, _child_argv, _check_reply
        ),
        job_guard_fd=job_guard_fd,
    )


def _execute_child(metadata, segments):
    # Include admission/export in the measured API scope; bootstrap/import CPU
    # remains outside this clock and is never manufactured as measured work.
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    if (
        set(metadata) != {"schema_version", "identity", "policy", "segment_hashes"}
        or metadata["schema_version"] != _SCHEMA
    ):
        raise ValueError("ordinal child metadata invalid")
    phase = metadata["identity"]["phase"]
    if phase not in ("analysis", "verification"):
        raise ValueError("ordinal child role invalid")
    policy = decode_rc_corotational_phase_policy(metadata["policy"])
    request, restart, result, checkpoint = segments
    grant = metadata["identity"]["grant"]
    expected = _input_metadata(
        phase, request, restart, result, checkpoint, grant, policy
    )
    if common._json(expected) != common._json(metadata):
        raise ValueError("ordinal child source/grant/original hashes differ")
    status, error_type, output = "returned", None, (None, None, None, None)
    try:
        from structural_analysis.api.rc_corotational_ordinal_control import (
            analyze_ordinal_job,
            verify_ordinal_job,
        )

        if phase == "analysis":
            value = analyze_ordinal_job(
                request, restart, grant["ceiling"], grant["record_limit"]
            )
            output = (value.result_bytes, value.continuation_bytes, None, None)
        else:
            output = (
                None,
                None,
                verify_ordinal_job(
                    request,
                    restart,
                    result,
                    checkpoint,
                    grant["ceiling"],
                    grant["record_limit"],
                ),
                None,
            )
    except Exception as error:
        status, error_type = "raised", type(error).__name__
    endwall, endcpu = time.perf_counter_ns(), time.process_time_ns()
    return {
        "schema_version": _SCHEMA,
        "identity": metadata["identity"],
        "policy": policy.to_dict(),
        "status": status,
        "error_type": error_type,
        "timing": {"wall_ns": endwall - wall, "process_cpu_ns": endcpu - cpu},
        "measurement": {
            "wall_started_ns": wall,
            "wall_finished_ns": endwall,
            "cpu_started_ns": cpu,
            "cpu_finished_ns": endcpu,
        },
        "segment_hashes": [common._hash(v) for v in output],
    }, output


def _child_main():
    receiver = _FrameReceiver("input", "pending")
    while raw := sys.stdin.buffer.read1(common._IO_CHUNK_BYTES):
        receiver.feed(raw)
    reply, output = _execute_child(*receiver.value())
    for part in _frame_parts(reply, output):
        sys.stdout.buffer.write(part)
    sys.stdout.buffer.flush()


class RCOrdinalWorkerError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def execute_rc_corotational_ordinal_claim(
    service, claim, *, worker_id, authorization_token, lease_seconds=300
):
    from structural_analysis.execution.job_service import DurableJobService, JobClaim

    if (
        type(service) is not DurableJobService
        or type(claim) is not JobClaim
        or type(lease_seconds) is not int
        or not 5 <= lease_seconds <= 3600
    ):
        raise RCOrdinalWorkerError("rc_ordinal_worker_argument_invalid")
    with service.execution_guard() as authority_fd:
        if authority_fd is None:
            raise RCOrdinalWorkerError("rc_ordinal_worker_managed_owner_required")
        with service.job_execution_permit(
            claim.job.job_id,
            expected_request_hash=claim.job.request.content_hash,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_token=claim.lease_token,
        ) as job_guard_fd:
            return _execute(
                service,
                claim,
                worker_id=worker_id,
                authorization_token=authorization_token,
                lease_seconds=lease_seconds,
                authority_fd=authority_fd,
                job_guard_fd=job_guard_fd,
            )


def _execute(
    service,
    claim,
    *,
    worker_id,
    authorization_token,
    lease_seconds,
    authority_fd,
    job_guard_fd,
):
    from structural_analysis.execution.job_service import (
        JobServiceError,
        build_job_completion_evidence,
    )
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        _LeaseKeeper,
    )
    from structural_analysis.execution.rc_corotational_ordinal_job_request import (
        validate_rc_corotational_ordinal_job_request,
    )
    from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
        ORDINAL_JOB_VALIDATOR_ID,
        ORDINAL_INVOCATION_SCHEMA_VERSION,
        ordinal_resume_binding,
        ordinal_chunk_hash,
        validate_ordinal_job_checkpoint,
        build_ordinal_job_receipt,
        build_ordinal_job_payload,
        validate_ordinal_job_result,
    )

    job_id = claim.job.job_id
    credentials = dict(
        worker_id=worker_id,
        authorization_token=authorization_token,
        lease_token=claim.lease_token,
    )
    try:
        current = service.heartbeat(job_id, **credentials, lease_seconds=lease_seconds)
        if any(
            getattr(current, n) != getattr(claim.job, n)
            for n in (
                "request",
                "checkpoint",
                "progress_completed",
                "progress_total",
                "resume_contract_hash",
                "attempt",
            )
        ):
            raise RCOrdinalWorkerError("rc_ordinal_claim_projection_changed")
        with _LeaseKeeper(
            service, job_id, credentials, lease_seconds, initial_lease=current
        ) as lease:
            typed = validate_rc_corotational_ordinal_job_request(claim.request_bytes)
            if (
                typed.request_hash != current.request.content_hash
                or typed.progress_total != current.progress_total
            ):
                raise RCOrdinalWorkerError("rc_ordinal_request_binding_changed")
            policy = typed.execution_config.phase_execution_policy
            validate_corotational_phase_host(
                policy, authority_fd=authority_fd, job_guard_fd=job_guard_fd
            )
            budget = service.read_execution_budget(job_id, **credentials)
            credits = service.read_ordinal_solver_budget(job_id, **credentials)
            receipts = []
            if current.checkpoint is not None:
                if (
                    type(claim.checkpoint_bytes) is not bytes
                    or common._hash(claim.checkpoint_bytes)
                    != current.checkpoint.content_hash
                    or len(claim.checkpoint_bytes) != current.checkpoint.byte_length
                ):
                    raise RCOrdinalWorkerError("rc_ordinal_checkpoint_binding_changed")
                prior = validate_ordinal_job_checkpoint(
                    claim.checkpoint_bytes,
                    request=typed,
                    progress_completed=current.progress_completed,
                    resume_contract_hash=typed.resume_contract_hash,
                    execution_budget=budget,
                    solver_credit_budget=credits,
                )["payload"]
                receipts = list(prior["receipts"])
            elif current.progress_completed != 0:
                raise RCOrdinalWorkerError("rc_ordinal_progress_without_checkpoint")
            binding = ordinal_resume_binding(typed, claim.checkpoint_bytes)
            restart = binding["native_continuation_bytes"]
            before = binding["completed_before"]
            record_limit = min(
                typed.execution_config.record_limit_per_call,
                typed.progress_total - before,
            )
            if record_limit < 1 or budget["remaining_attempts"] < 2:
                raise RCOrdinalWorkerError("rc_ordinal_api_budget_exhausted")
            native_remaining = typed.config.maximum_solver_attempts
            if restart is not None:
                from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
                    _native,
                )

                native_remaining -= _native(typed, restart).solver_invocations
            ceiling = (
                min(
                    typed.execution_config.attempt_limit_per_call,
                    credits["production"]["remaining"],
                    credits["verification"]["remaining"],
                    native_remaining,
                )
                if binding["requires_solver"]
                else 0
            )
            if binding["requires_solver"] and ceiling < 1:
                raise RCOrdinalWorkerError("rc_ordinal_solver_budget_exhausted")
            prior_hash = current.checkpoint.content_hash if current.checkpoint else None

            def invoke(phase, result=None, checkpoint=None):
                lease.check()
                ordinal = service.reserve_execution_attempt(job_id, **credentials)
                grant = service.reserve_ordinal_solver_credits(
                    job_id,
                    **credentials,
                    phase=phase,
                    api_ordinal=ordinal,
                    ceiling=ceiling,
                    expected_checkpoint_hash=prior_hash,
                    native_input_sha256=binding["native_input_sha256"],
                    record_limit=record_limit,
                )
                start, cpustart = time.perf_counter_ns(), time.process_time_ns()
                reply, error = None, None
                try:
                    reply = run_ordinal_phase(
                        phase=phase,
                        request_bytes=claim.request_bytes,
                        restart=restart,
                        result=result,
                        checkpoint=checkpoint,
                        grant=grant,
                        policy=policy,
                        lease_check=lease.check,
                        authority_fd=authority_fd,
                        job_guard_fd=job_guard_fd,
                    )
                    if reply.status == "raised":
                        error = RCOrdinalWorkerError("rc_ordinal_child_raised")
                except Exception as exc:
                    error = exc
                wall, parentcpu = (
                    time.perf_counter_ns() - start,
                    time.process_time_ns() - cpustart,
                )
                successful = (
                    reply is not None and reply.status == "returned" and error is None
                )
                api_result = (
                    common._strict_object(reply.raw_result)
                    if successful and phase == "production"
                    else None
                )
                report = (
                    reply.verification_report
                    if successful and phase == "verification"
                    else None
                )
                outcome = dict(
                    schema_version=ORDINAL_INVOCATION_SCHEMA_VERSION,
                    phase=phase,
                    status="returned" if successful else "raised",
                    job_request_hash=typed.request_hash,
                    context_hash=typed.context_hash,
                    chunk_request_hash=ordinal_chunk_hash(typed, grant),
                    completed_before=before,
                    completed_after=(api_result or report)["completed_after"]
                    if successful
                    else before,
                    restart_input_sha256=binding["native_input_sha256"],
                    timing=reply.timing
                    if reply is not None
                    else {"wall_ns": wall, "process_cpu_ns": parentcpu},
                    api_result=api_result,
                    checkpoint_artifact_base64=base64.b64encode(
                        reply.native_checkpoint
                    ).decode("ascii")
                    if successful and phase == "production"
                    else None,
                    verification_report=report,
                    error=None
                    if successful
                    else {
                        "type": reply.error_type
                        if reply is not None
                        else type(error).__name__,
                        "code": getattr(error, "code", "rc_ordinal_phase_unaccounted"),
                    },
                    unavailable_execution_work=not successful,
                    grant=grant,
                    credits_used=(api_result or report)["credits_used"]
                    if successful
                    else None,
                    phase_supervision={
                        "phase": phase,
                        "policy": policy.to_dict(),
                        "status": reply.status if reply is not None else "unaccounted",
                        "supervisor": reply.supervisor_timing
                        if reply is not None
                        else {"scope": "parent failure; child CPU unavailable"},
                        "parent_wall_ns": wall,
                        "parent_process_cpu_ns": parentcpu,
                        "cleanup": getattr(error, "cleanup", {})
                        if error is not None
                        else {},
                    },
                )
                service.record_rc_invocation_outcome(
                    job_id, **credentials, ordinal=ordinal, outcome=outcome
                )
                if not successful:
                    raise error
                return ordinal, outcome, reply

            pordinal, production, artifacts = invoke("production")
            vordinal, verification, _reply = invoke(
                "verification", artifacts.raw_result, artifacts.native_checkpoint
            )
            native_status = production["api_result"]["status"]
            if native_status in ("blocked", "budget_exhausted"):
                # Both original phase observations and nonrefundable grants
                # are recorded. A matching failed suffix is diagnostic data,
                # rather than an accepted checkpoint or successful receipt.
                raise RCOrdinalWorkerError("rc_ordinal_native_" + native_status)
            receipts.append(
                build_ordinal_job_receipt(
                    typed,
                    production_ordinal=pordinal,
                    verification_ordinal=vordinal,
                    production_outcome=production,
                    verification_outcome=verification,
                )
            )
            budget = service.read_execution_budget(job_id, **credentials)
            credits = service.read_ordinal_solver_budget(job_id, **credentials)
            complete = production["api_result"]["status"] == "complete"
            payload = build_ordinal_job_payload(
                typed,
                receipts=receipts,
                execution_budget=budget,
                solver_credit_budget=credits,
                terminal_checkpoint=artifacts.native_checkpoint,
                api_result=production["api_result"],
                complete=complete,
            )
            raw = common._json(payload)
            lease.check()
            if complete:
                validation = validate_ordinal_job_result(
                    payload,
                    request=typed,
                    execution_budget=budget,
                    solver_credit_budget=credits,
                    checkpoint=claim.checkpoint_bytes,
                )
                evidence = build_job_completion_evidence(
                    job_id=job_id,
                    request_hash=typed.request_hash,
                    checkpoint_hash=prior_hash,
                    result_bytes=raw,
                    validator_id=ORDINAL_JOB_VALIDATOR_ID,
                    validation_report=validation,
                )
                return service.complete_job(
                    job_id,
                    **credentials,
                    result_bytes=raw,
                    result_media_type="application/json",
                    evidence=evidence,
                    expected_checkpoint_hash=prior_hash,
                )
            return service.save_checkpoint(
                job_id,
                **credentials,
                checkpoint_bytes=raw,
                checkpoint_media_type="application/json",
                progress_completed=payload["progress_completed"],
                progress_total=typed.progress_total,
                resume_contract_hash=typed.resume_contract_hash,
                expected_checkpoint_hash=prior_hash,
            )
    except Exception as error:
        try:
            service.fail_job(
                job_id,
                **credentials,
                error_code=getattr(error, "code", "rc_ordinal_worker_failed"),
                retriable=False,
            )
        except JobServiceError:
            pass
        raise


if __name__ == "__main__":
    _child_main()
