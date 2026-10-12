"""Separate bounded binary transport for whole-history corotational phases.

Linux process ownership, group teardown and reaping reuse the existing private
supervision loop. Transport identity and caps are independent: request/native
16 MiB each, API/report 64 MiB each, at most 112 MiB of binary input segments.
These are transport caps, not RSS limits. No credentials enter the child. The
direct child inherits an optional managed guard and arms PDEATHSIG before imports.
"""

from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import time

from structural_analysis.execution import rc_fiber_phase_supervisor as common
from structural_analysis.execution.rc_corotational_phase_policy import (
    RCCorotationalPhasePolicy,
)

_MIB = 1024 * 1024
_REQUEST_MAX_BYTES = 16 * _MIB
_NATIVE_MAX_BYTES = 16 * _MIB
_RESULT_MAX_BYTES = 64 * _MIB
_REPORT_MAX_BYTES = 64 * _MIB
_FRAME_SEGMENTS_MAX_BYTES = 112 * _MIB
_METADATA_MAX_BYTES = 64 * 1024
_MAGIC = b"SA-RC-CORO-1\x00\x00\x00\x00"
_SCHEMA = "bounded-rc-corotational-phase-transport.v1"
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_FILES = {
    "supervisor": "execution/rc_corotational_phase_supervisor.py",
    "shared_supervision": "execution/rc_fiber_phase_supervisor.py",
    "bootstrap": "execution/_rc_fiber_phase_bootstrap.py",
    "api": "api/rc_corotational_control.py",
    "request_decoder": "execution/rc_corotational_job_request.py",
    "durable_contract": "execution/rc_corotational_job_contract.py",
    "phase_policy": "execution/rc_corotational_phase_policy.py",
}


def _source_hashes():
    package = _SOURCE_ROOT / "structural_analysis"
    return {
        name: common._hash((package / path).read_bytes())
        for name, path in _SOURCE_FILES.items()
    }


def _child_argv(expected_parent_pid):
    return [
        sys.executable,
        "-I",
        str(common._BOOTSTRAP_PATH),
        str(expected_parent_pid),
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
            or any(value > cap for value, cap in zip(lengths, caps, strict=True))
            or sum(lengths) > _FRAME_SEGMENTS_MAX_BYTES
        ):
            raise ValueError("corotational frame header/byte bounds invalid")
        if self.direction == "input":
            if not lengths[0] or (self.phase == "analysis" and any(lengths[2:])):
                raise ValueError("corotational input roles invalid")
            if self.phase == "verification" and not lengths[2]:
                raise ValueError("corotational verification needs original result")
        elif (
            (self.phase == "analysis" and lengths[2])
            or (self.phase == "verification" and (lengths[0] or lengths[1]))
            or (lengths[3] and any(lengths[:3]))
        ):
            raise ValueError("corotational output roles invalid")
        self.metadata_length, self.lengths = metadata_length, tuple(lengths)


def _frame_parts(metadata, segments):
    if len(segments) != 4:
        raise ValueError("corotational transport requires four binary segments")
    raw = common._json(metadata)
    lengths = tuple(0 if value is None else len(value) for value in segments)
    if (
        not 1 <= len(raw) <= _METADATA_MAX_BYTES
        or sum(lengths) > _FRAME_SEGMENTS_MAX_BYTES
        or any(
            value is not None and (type(value) is not bytes or not value)
            for value in segments
        )
    ):
        raise ValueError("corotational transport frame exceeds bounds")
    header = common._HEADER.pack(_MAGIC, len(raw), *lengths)
    receiver = _FrameReceiver(
        "output" if "status" in metadata else "input", metadata["identity"]["phase"]
    )
    receiver.header = bytearray(header)
    receiver._header_ready()
    return (header, raw, *(v for v in segments if v is not None))


def _input_metadata(
    phase, request_bytes, before, planned_after, restart, result, checkpoint, policy
):
    from structural_analysis.execution.rc_corotational_job_request import (
        validate_rc_corotational_job_request,
    )
    from structural_analysis.execution.rc_corotational_job_contract import (
        rc_corotational_chunk_binding,
    )

    typed = validate_rc_corotational_job_request(request_bytes)
    if typed.execution_config.phase_execution_policy is None or common._json(
        typed.execution_config.phase_execution_policy.to_dict()
    ) != common._json(policy.to_dict()):
        raise ValueError("corotational authored isolation policy differs")
    binding = rc_corotational_chunk_binding(typed, before, restart)
    if binding["planned_after"] != planned_after:
        raise ValueError("corotational planned control attempt span differs")
    identity = {
        "phase": phase,
        **binding,
        "source_revision": typed.source_revision,
        "analysis_result_sha256": common._hash(result),
        "analysis_checkpoint_sha256": common._hash(checkpoint),
        "source_hashes": _source_hashes(),
    }
    return {
        "schema_version": _SCHEMA,
        "identity": identity,
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
        or metadata.get("schema_version") != _SCHEMA
        or common._json(metadata["policy"]) != common._json(expected["policy"])
        or common._json(metadata["identity"]) != common._json(expected["identity"])
    ):
        raise ValueError("corotational reply namespace/policy differs")
    work = segments[3]
    if (work is not None) != (
        metadata.get("error_type") == "RCCorotationalControlExecutionError"
    ):
        raise ValueError("corotational partial-work exception binding differs")
    if work is not None:
        from structural_analysis.execution.rc_corotational_job_contract import _work

        parsed = common._strict_object(work)
        _work(parsed)
        if parsed["unavailable_execution_work"] is not True:
            raise ValueError("corotational raised work must remain unavailable")
    # Reuse only generic clock/status/exit-role validation. The original frame
    # namespace/hash and corotational exception work were checked above; no old
    # RC artifact or material-law interpretation is used by this private bridge.
    projected = dict(metadata, schema_version=common._SCHEMA)
    projected.pop("policy")
    projected_expected = dict(expected, schema_version=common._SCHEMA)
    reply = common._check_reply(
        projected, (*segments[:3], None), projected_expected, started_ns, received_ns
    )
    return common.RCFiberPhaseReply(
        reply.status,
        reply._timing_bytes,
        reply.raw_result,
        reply.native_checkpoint,
        reply._verification_bytes,
        reply.error_type,
        work,
        b"{}",
    )


def validate_corotational_phase_host(policy, *, authority_fd=None, job_guard_fd=None):
    if sys.platform != "linux" or type(policy) is not RCCorotationalPhasePolicy:
        raise common.RCFiberPhaseError(
            "rc_corotational_worker_analysis_unsupported",
            "Linux and exact authored policy required",
        )
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise common.RCFiberPhaseError(
            "rc_corotational_worker_analysis_unsupported",
            "default SIGCHLD and exclusive child-wait ownership required",
        )
    if authority_fd is not None and authority_fd == job_guard_fd:
        raise common.RCFiberPhaseError(
            "rc_corotational_worker_analysis_job_guard_invalid",
            "distinct execution guards required",
        )
    for guard_name, guard_fd in (
        ("authority", authority_fd),
        ("job_guard", job_guard_fd),
    ):
        if guard_fd is None:
            continue
        try:
            if type(guard_fd) is not int or not 3 <= guard_fd <= 2**31 - 1:
                raise ValueError("invalid execution guard descriptor")
            os.fstat(guard_fd)
        except (ValueError, OSError) as error:
            raise common.RCFiberPhaseError(
                "rc_corotational_worker_analysis_" + guard_name + "_invalid",
                "execution guard descriptor unavailable",
            ) from error


def run_rc_corotational_phase(
    *,
    phase,
    request_bytes,
    completed_before,
    completed_after,
    restart,
    result=None,
    checkpoint=None,
    policy,
    lease_check,
    authority_fd=None,
    job_guard_fd=None,
):
    started_ns = time.perf_counter_ns()
    validate_corotational_phase_host(
        policy, authority_fd=authority_fd, job_guard_fd=job_guard_fd
    )
    if (
        type(phase) is not str
        or phase not in ("analysis", "verification")
        or not callable(lease_check)
    ):
        raise ValueError("invalid corotational phase/check callback")
    timeout = (
        policy.analysis_timeout_ms
        if phase == "analysis"
        else policy.verification_timeout_ms
    )
    deadline = started_ns + timeout * 1_000_000
    values = (request_bytes, restart, result, checkpoint)
    caps = (_REQUEST_MAX_BYTES, _NATIVE_MAX_BYTES, _RESULT_MAX_BYTES, _NATIVE_MAX_BYTES)
    code = f"rc_corotational_worker_{phase}_"
    if (
        request_bytes is None
        or any(
            v is not None and (type(v) is not bytes or not 1 <= len(v) <= cap)
            for v, cap in zip(values, caps, strict=True)
        )
        or (phase == "analysis" and (result is not None or checkpoint is not None))
        or (phase == "verification" and result is None)
    ):
        raise common.RCFiberPhaseError(
            code + "unsupported", "immutable corotational artifact bounds/roles invalid"
        )
    try:
        expected = _input_metadata(
            phase,
            request_bytes,
            completed_before,
            completed_after,
            restart,
            result,
            checkpoint,
            policy,
        )
        parts = _frame_parts(expected, values)
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError) as error:
        raise common.RCFiberPhaseError(
            code + "unsupported", "corotational input/policy binding invalid"
        ) from error

    def check_lease():
        try:
            lease_check()
        except Exception as error:
            # The common loop attaches its observed cleanup to phase errors.
            # Keep that custody for this transport without changing the legacy
            # transport's original stale-lease exception behavior.
            raise common.RCFiberPhaseError(
                code + "lease_lost", "parent lease check failed"
            ) from error

    return common._supervise(
        phase,
        parts,
        expected,
        started_ns,
        deadline,
        policy.termination_grace_ms,
        check_lease,
        authority_fd,
        backend=common._PhaseBackend(
            "rc_corotational_worker_", _FrameReceiver, _child_argv, _check_reply
        ),
        job_guard_fd=job_guard_fd,
    )


def _read_input_frame():
    # Header caps apply immediately; declared phase/segment roles are checked
    # after canonical metadata is available, before any numerical invocation.
    receiver = _FrameReceiver("input", "pending")
    while raw := sys.stdin.buffer.read1(common._IO_CHUNK_BYTES):
        receiver.feed(raw)
    return receiver.value()


def _execute_child(metadata, segments):
    from structural_analysis.execution.rc_corotational_phase_policy import (
        decode_rc_corotational_phase_policy,
    )
    from structural_analysis.execution.rc_corotational_job_request import (
        validate_rc_corotational_job_request,
    )
    from structural_analysis.api import rc_corotational_control as api

    if (
        set(metadata) != {"schema_version", "identity", "policy", "segment_hashes"}
        or metadata["schema_version"] != _SCHEMA
    ):
        raise ValueError("corotational child metadata shape differs")
    identity = metadata["identity"]
    phase = identity.get("phase")
    if phase not in ("analysis", "verification"):
        raise ValueError("corotational child phase differs")
    policy = decode_rc_corotational_phase_policy(metadata["policy"])
    request_bytes, restart, result, checkpoint = segments
    expected = _input_metadata(
        phase,
        request_bytes,
        identity["completed_before"],
        identity["planned_after"],
        restart,
        result,
        checkpoint,
        policy,
    )
    if (
        common._json(metadata) != common._json(expected)
        or (phase == "analysis" and (result is not None or checkpoint is not None))
        or (phase == "verification" and result is None)
    ):
        raise ValueError("corotational child original source/input identity differs")
    typed = validate_rc_corotational_job_request(request_bytes)
    wall_started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
    status, error_type, output = "returned", None, (None, None, None, None)
    try:
        if phase == "analysis":
            value = api.analyze_rc_corotational_control(
                typed.model, typed.targets_m, restart=restart, **typed.api_kwargs()
            )
            output = (value.result_bytes, value.continuation_bytes, None, None)
        else:
            value = api.validate_rc_corotational_control_artifacts(
                typed.model,
                typed.targets_m,
                result=result,
                continuation=checkpoint,
                restart=restart,
                **typed.api_kwargs(),
            )
            output = (None, None, common._json(value), None)
    except Exception as error:
        status, error_type = "raised", type(error).__name__
        if isinstance(error, api.RCCorotationalControlExecutionError):
            output = (None, None, None, common._json(error.work))
    wall_finished, cpu_finished = time.perf_counter_ns(), time.process_time_ns()
    reply = {
        "schema_version": _SCHEMA,
        "identity": identity,
        "policy": policy.to_dict(),
        "status": status,
        "error_type": error_type,
        "timing": {
            "wall_ns": wall_finished - wall_started,
            "process_cpu_ns": cpu_finished - cpu_started,
        },
        "measurement": {
            "wall_started_ns": wall_started,
            "wall_finished_ns": wall_finished,
            "cpu_started_ns": cpu_started,
            "cpu_finished_ns": cpu_finished,
        },
        "segment_hashes": [common._hash(v) for v in output],
    }
    return reply, output


def _child_main():
    metadata, segments = _read_input_frame()
    reply, output = _execute_child(metadata, segments)
    for part in _frame_parts(reply, output):
        sys.stdout.buffer.write(part)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    _child_main()
