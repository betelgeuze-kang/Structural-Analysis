"""Fresh-process execution of an opted-in Linux RC numerical phase.

The parent keeps credentials, leases, durable reservations and publication. The
child reconstructs the exact canonical request and native restart and performs
one analysis or mandatory fresh verification. A complete measured reply alone
can become an accounted invocation. Cutoff, EOF, corrupt/late IPC and unsuccessful
cleanup are errors with no invented CPU time or numerical reply.

Raw binary segments retain existing request (16 MiB), result (512 MiB), native
restart (8 MiB) and RC durable report (576 MiB) byte bounds; there is no base64
artifact duplication. Incremental pipe draining prevents join-before-read
deadlock. These are logical transport bounds, not an RSS/disk quota. A deadline
covers launch/import/request reconstruction/API/export/IPC. Process creation and
uninterruptible kernel teardown can exceed it; observed direct-child reaping is
required, and a bounded failed cleanup is explicit. The parent must retain
exclusive child-wait ownership and default SIGCHLD handling; unsupported/native
auto-reaping or competing reapers cannot establish a successful exit. Group termination plus Linux
PDEATHSIG protects a direct child and ordinary same-group processes, not arbitrary
escaped descendants, a whole job, or cumulative retry costs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import selectors
import signal
import struct
import subprocess
import sys
import time
from typing import Callable


_MIB = 1024 * 1024
_REQUEST_MAX_BYTES = 16 * _MIB
_RESULT_MAX_BYTES = 512 * _MIB
_NATIVE_MAX_BYTES = 8 * _MIB
_REPORT_MAX_BYTES = 576 * _MIB
_METADATA_MAX_BYTES = 64 * 1024
_FRAME_SEGMENTS_MAX_BYTES = 576 * _MIB
_STDERR_MAX_BYTES = 64 * 1024
_IO_CHUNK_BYTES = 64 * 1024
_POLL_SECONDS = 0.02
_MAGIC = b"SA-RC-PHASE-1\x00\x00\x00"
_HEADER = struct.Struct("!16sIQQQQ")
_SCHEMA = "bounded-rc-fiber-phase-transport.v1"
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_BOOTSTRAP_PATH = Path(__file__).with_name("_rc_fiber_phase_bootstrap.py").resolve()
_SOURCE_FILES = {
    "supervisor": "execution/rc_fiber_phase_supervisor.py",
    "bootstrap": "execution/_rc_fiber_phase_bootstrap.py",
    "api": "api/rc_fiber_frame_direct_control.py",
    "request_decoder": "api/rc_fiber_frame_direct_control_request.py",
    "durable_contract": "execution/rc_fiber_job_contract.py",
    "phase_policy": "execution/rc_fiber_phase_policy.py",
}


def _json(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash(raw: bytes | None) -> str | None:
    return None if raw is None else "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_object(raw: bytes) -> dict:
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError("duplicate transport JSON key")
            value[key] = item
        return value

    def constant(_value):
        raise ValueError("non-finite transport JSON number")

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant
        )
        if type(value) is not dict or _json(value) != raw:
            raise ValueError("transport object must use exact canonical JSON")
        return value
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ValueError("invalid canonical phase JSON object") from error


class RCFiberPhaseError(ValueError):
    """Unaccounted phase failure; cleanup diagnostics never imply solver work."""

    def __init__(self, code: str, detail: str, *, cleanup: dict | None = None):
        self.code = code
        self.detail = detail
        self._cleanup_bytes = _json(cleanup or {})
        super().__init__(f"{code}: {detail}")

    @property
    def cleanup(self) -> dict:
        return json.loads(self._cleanup_bytes)


@dataclass(frozen=True)
class RCFiberPhaseReply:
    status: str
    _timing_bytes: bytes
    raw_result: bytes | None
    native_checkpoint: bytes | None
    _verification_bytes: bytes | None
    error_type: str | None
    _artifact_error_bytes: bytes | None
    _supervisor_bytes: bytes

    @property
    def timing(self) -> dict:
        return json.loads(self._timing_bytes)

    @property
    def verification_report(self) -> dict | None:
        return (
            None
            if self._verification_bytes is None
            else json.loads(self._verification_bytes)
        )

    @property
    def artifact_error_report(self) -> dict | None:
        return (
            None
            if self._artifact_error_bytes is None
            else json.loads(self._artifact_error_bytes)
        )

    @property
    def supervisor_timing(self) -> dict:
        return json.loads(self._supervisor_bytes)


def _source_hashes() -> dict:
    package = _SOURCE_ROOT / "structural_analysis"
    return {
        name: _hash((package / relative).read_bytes())
        for name, relative in _SOURCE_FILES.items()
    }


def _dependency_paths() -> list[str]:
    # The current worker runtime may use packages installed in its user site.
    # Add only origins of known numerical/schema dependencies after bootstrap;
    # do not execute user .pth/sitecustomize or inherit arbitrary PYTHONPATH.
    roots = set()
    for name in ("numpy", "jsonschema", "scipy"):
        spec = importlib.util.find_spec(name)
        if spec is not None and spec.origin is not None:
            origin = Path(spec.origin).resolve(strict=True)
            roots.add(
                str(
                    origin.parent.parent
                    if spec.submodule_search_locations is not None
                    else origin.parent
                )
            )
    return sorted(roots)


def _child_argv(expected_parent_pid: int) -> list[str]:
    """Private seam for real subprocess tests; no public entry/environment override."""
    return [
        sys.executable,
        "-I",
        str(_BOOTSTRAP_PATH),
        str(expected_parent_pid),
        str(_SOURCE_ROOT),
        str(Path(__file__).resolve()),
        _json(_dependency_paths()).decode("utf-8"),
    ]


def _child_environment() -> dict[str, str]:
    # Never inherit authentication, loader injection, PYTHONPATH or user config.
    result = {"PATH": "/usr/bin:/bin"}
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        value = os.environ.get(name)
        if (
            value is not None
            and len(value) <= 4
            and value.isascii()
            and value.isdigit()
        ):
            if 1 <= int(value) <= 1024:
                result[name] = value
    return result


def _frame_parts(metadata: dict, segments: tuple[bytes | None, ...]):
    if len(segments) != 4:
        raise ValueError("phase transport requires exactly four binary segments")
    raw = _json(metadata)
    lengths = tuple(0 if value is None else len(value) for value in segments)
    if len(raw) > _METADATA_MAX_BYTES or sum(lengths) > _FRAME_SEGMENTS_MAX_BYTES:
        raise ValueError("phase transport frame exceeds its explicit byte bound")
    if any(
        value is not None and (type(value) is not bytes or not value)
        for value in segments
    ):
        raise ValueError("phase transport segments must be nonempty immutable bytes")
    return (
        _HEADER.pack(_MAGIC, len(raw), *lengths),
        raw,
        *(value for value in segments if value is not None),
    )


class _FrameReceiver:
    """Incremental parser: reject lengths before allocating/draining artifacts."""

    def __init__(self, direction: str, phase: str):
        self.direction, self.phase = direction, phase
        self.header = bytearray()
        self.metadata = bytearray()
        self.lengths = None
        self.metadata_length = None
        self.buffers = [bytearray() for _ in range(4)]
        self.digests = [hashlib.sha256() for _ in range(4)]
        self.segment = 0
        self.complete = False

    def _header_ready(self):
        magic, metadata_length, *lengths = _HEADER.unpack(self.header)
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
            or any(value > limit for value, limit in zip(lengths, caps, strict=True))
            or sum(lengths) > _FRAME_SEGMENTS_MAX_BYTES
        ):
            raise ValueError("phase frame header/declared byte lengths invalid")
        if self.direction == "input":
            if not lengths[0] or (self.phase == "analysis" and any(lengths[2:])):
                raise ValueError("phase input segment roles invalid")
            if self.phase == "verification" and not lengths[2]:
                raise ValueError("verification requires original analysis bytes")
        elif (
            (self.phase == "analysis" and lengths[2])
            or (self.phase == "verification" and (lengths[0] or lengths[1]))
            or (lengths[3] and any(lengths[:3]))
        ):
            raise ValueError("phase output segment roles invalid")
        self.metadata_length, self.lengths = metadata_length, tuple(lengths)

    def feed(self, raw: bytes):
        view, offset = memoryview(raw), 0
        if self.complete and raw:
            raise ValueError("trailing phase transport bytes")
        while offset < len(view):
            if len(self.header) < _HEADER.size:
                count = min(_HEADER.size - len(self.header), len(view) - offset)
                self.header.extend(view[offset : offset + count])
                offset += count
                if len(self.header) == _HEADER.size:
                    self._header_ready()
            elif len(self.metadata) < self.metadata_length:
                count = min(
                    self.metadata_length - len(self.metadata), len(view) - offset
                )
                self.metadata.extend(view[offset : offset + count])
                offset += count
            else:
                while (
                    self.segment < 4
                    and len(self.buffers[self.segment]) == self.lengths[self.segment]
                ):
                    self.segment += 1
                if self.segment == 4:
                    self.complete = True
                    raise ValueError("trailing phase transport bytes")
                count = min(
                    self.lengths[self.segment] - len(self.buffers[self.segment]),
                    len(view) - offset,
                )
                chunk = view[offset : offset + count]
                self.buffers[self.segment].extend(chunk)
                self.digests[self.segment].update(chunk)
                offset += count
        if (
            self.lengths is not None
            and len(self.metadata) == self.metadata_length
            and all(
                len(value) == length
                for value, length in zip(self.buffers, self.lengths, strict=True)
            )
        ):
            self.complete = True

    def value(self):
        if not self.complete:
            raise ValueError("truncated phase transport frame")
        metadata = _strict_object(bytes(self.metadata))
        segments = tuple(
            bytes(value) if length else None
            for value, length in zip(self.buffers, self.lengths, strict=True)
        )
        hashes = [
            None if not length else "sha256:" + digest.hexdigest()
            for digest, length in zip(self.digests, self.lengths, strict=True)
        ]
        if metadata.get("segment_hashes") != hashes:
            raise ValueError("phase binary segment hash mismatch")
        return metadata, segments


def _input_metadata(
    phase,
    request_bytes,
    completed_before,
    completed_after,
    restart,
    result,
    checkpoint,
    policy,
):
    request = _strict_object(request_bytes)
    config, execution = request.get("config"), request.get("execution_config")
    if (
        request.get("operation") != "bounded_rc_fiber_direct_control"
        or type(config) is not dict
        or type(execution) is not dict
        or type(config.get("targets_m")) is not list
        or type(execution.get("chunk_target_count")) is not int
    ):
        raise ValueError("phase requires original canonical RC durable request")
    total, size = len(config["targets_m"]), execution["chunk_target_count"]
    if (
        type(completed_before) is not int
        or type(completed_after) is not int
        or not 1 <= size <= 255
        or not 0 <= completed_before < total
        or completed_before % size
        or completed_after != min(total, completed_before + size)
        or (completed_before == 0) != (restart is None)
    ):
        raise ValueError("phase range/restart differs from the authored fixed chunk")
    if request["execution_config"].get("phase_execution_policy") != policy.to_dict():
        raise ValueError("phase policy differs from the immutable authored request")
    chunk = dict(
        config, targets_m=config["targets_m"][completed_before:completed_after]
    )
    identity = {
        "phase": phase,
        "job_request_hash": _hash(request_bytes),
        "chunk_request_hash": _hash(_json(chunk)),
        "source_revision": request.get("source_revision"),
        "completed_before": completed_before,
        "completed_after": completed_after,
        "restart_input_sha256": _hash(restart),
        "analysis_result_sha256": _hash(result),
        "analysis_checkpoint_sha256": _hash(checkpoint),
        "source_hashes": _source_hashes(),
    }
    return {
        "schema_version": _SCHEMA,
        "identity": identity,
        "policy": policy.to_dict(),
        "segment_hashes": [
            _hash(value) for value in (request_bytes, restart, result, checkpoint)
        ],
    }


def _check_reply(metadata, segments, expected, started_ns, received_ns):
    if (
        set(metadata)
        != {
            "schema_version",
            "identity",
            "segment_hashes",
            "status",
            "timing",
            "measurement",
            "error_type",
        }
        or metadata["schema_version"] != _SCHEMA
        or metadata["identity"] != expected["identity"]
        or metadata["status"] not in ("returned", "raised")
    ):
        raise ValueError("phase reply identity/status/source mismatch")
    timing, measurement = metadata["timing"], metadata["measurement"]
    if (
        type(timing) is not dict
        or set(timing) != {"wall_ns", "process_cpu_ns"}
        or any(
            type(value) is not int or not 0 <= value < 2**63
            for value in timing.values()
        )
        or type(measurement) is not dict
        or set(measurement)
        != {"wall_started_ns", "wall_finished_ns", "cpu_started_ns", "cpu_finished_ns"}
        or any(
            type(value) is not int or not 0 <= value < 2**63
            for value in measurement.values()
        )
        or not started_ns
        <= measurement["wall_started_ns"]
        <= measurement["wall_finished_ns"]
        <= received_ns
        or measurement["cpu_finished_ns"] < measurement["cpu_started_ns"]
        or timing["wall_ns"]
        != measurement["wall_finished_ns"] - measurement["wall_started_ns"]
        or timing["process_cpu_ns"]
        != measurement["cpu_finished_ns"] - measurement["cpu_started_ns"]
    ):
        raise ValueError("phase reply measured API/export clocks invalid")
    cpu_slots = max(1, len(os.sched_getaffinity(0)))
    if (
        timing["process_cpu_ns"] > timing["wall_ns"] * cpu_slots + 1_000_000
        or measurement["cpu_finished_ns"]
        > (received_ns - started_ns) * cpu_slots + 1_000_000
    ):
        raise ValueError("phase reply CPU clocks exceed possible child execution scope")
    raw, native, verification, artifact_error = segments
    phase, status = expected["identity"]["phase"], metadata["status"]
    error_type = metadata["error_type"]
    if status == "returned":
        if error_type is not None or artifact_error is not None:
            raise ValueError("returned phase contains raised exception fields")
        if phase == "analysis":
            if raw is None or verification is not None:
                raise ValueError("returned analysis artifact segments invalid")
        elif verification is None or raw is not None or native is not None:
            raise ValueError("returned verification report segments invalid")
    elif (
        raw is not None
        or native is not None
        or verification is not None
        or type(error_type) is not str
        or not 1 <= len(error_type) <= 128
        or not error_type.isidentifier()
        or (
            (artifact_error is not None)
            != (error_type == "BoundedRCFiberDirectControlArtifactError")
        )
    ):
        raise ValueError("raised phase exception/report segments invalid")
    for report in (verification, artifact_error):
        if report is not None:
            _strict_object(report)
    if artifact_error is not None:
        # Preserve the exact public typed report, including its false claims;
        # malformed structured exceptions remain unaccounted transport failure.
        from structural_analysis.api.rc_fiber_frame_direct_control import (
            BoundedRCFiberDirectControlArtifactError,
        )

        report = _strict_object(artifact_error)
        try:
            restored = BoundedRCFiberDirectControlArtifactError(
                report["failure"],
                {
                    "model": report["model"],
                    "request": report["request"],
                    "status": report["computed_path_status"],
                    "metrics": report["execution_metrics"],
                },
            ).to_dict()
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise ValueError("typed phase artifact-error report invalid") from error
        if _json(restored) != _json(report):
            raise ValueError(
                "typed phase artifact-error report differs from its public contract"
            )
    return RCFiberPhaseReply(
        status,
        _json(timing),
        raw,
        native,
        verification,
        error_type,
        artifact_error,
        b"{}",
    )


def _signal_group(process, sig, diagnostics):
    try:
        os.killpg(process.pid, sig)
        diagnostics["signals_sent"].append(signal.Signals(sig).name)
    except ProcessLookupError:
        pass
    except OSError as error:
        diagnostics["signal_errors"].append(
            {"signal": signal.Signals(sig).name, "errno": error.errno}
        )


def _observe_exit(process):
    """Observe without reaping: an owned zombie still pins its numeric PID/PGID."""
    return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)


def _observed_returncode(observed):
    if observed.si_code == os.CLD_EXITED:
        return observed.si_status
    if observed.si_code in (os.CLD_KILLED, os.CLD_DUMPED):
        return -observed.si_status
    raise ValueError("phase child wait observation is not an exited child")


def _reap_observed(process, observed):
    expected = _observed_returncode(observed)
    # Popen.wait masks ECHILD as exit0. Require our own exact waitpid receipt,
    # including for a successful observed exit; never manufacture owned reaping.
    waited, status = os.waitpid(process.pid, os.WNOHANG)
    if waited != process.pid:
        raise ChildProcessError("phase child final wait did not return the owned PID")
    returned = os.waitstatus_to_exitcode(status)
    process.returncode = returned
    if returned != expected:
        raise ChildProcessError(
            "phase child wait status changed or reaping ownership was lost"
        )
    process._rc_phase_owned_reaped_returncode = expected
    return returned


def _stop_process(process, grace_ms):
    started = time.perf_counter_ns()
    diagnostics = {
        "pid": process.pid,
        "signals_sent": [],
        "signal_errors": [],
        "direct_child_reaped": False,
        "returncode": None,
        "ownership_lost": False,
    }
    # A completed normal path can hit its deadline just after our own explicit
    # wait. It has already signalled the owned group; never signal a recycled ID.
    marker = getattr(process, "_rc_phase_owned_reaped_returncode", None)
    if marker is not None and process.returncode == marker:
        diagnostics.update(
            {
                "direct_child_reaped": True,
                "returncode": marker,
                "group_signal_after_reap_avoided": True,
                "cleanup_wall_ns": time.perf_counter_ns() - started,
            }
        )
        return diagnostics
    try:
        _observe_exit(process)  # ECHILD refuses group signalling after ownership loss.
        _signal_group(process, signal.SIGTERM, diagnostics)
        term_until = time.perf_counter_ns() + grace_ms * 1_000_000
        observed = _observe_exit(process)
        while observed is None and time.perf_counter_ns() < term_until:
            time.sleep(
                min(_POLL_SECONDS, max(0, (term_until - time.perf_counter_ns()) / 1e9))
            )
            observed = _observe_exit(process)
        # Retain the direct child's PID, including when already exited, until
        # this final signal to its ordinary process group has been attempted.
        _signal_group(process, signal.SIGKILL, diagnostics)
        kill_until = time.perf_counter_ns() + grace_ms * 1_000_000
        observed = _observe_exit(process)
        while observed is None and time.perf_counter_ns() < kill_until:
            time.sleep(
                min(_POLL_SECONDS, max(0, (kill_until - time.perf_counter_ns()) / 1e9))
            )
            observed = _observe_exit(process)
        if observed is not None:
            diagnostics["observed_returncode"] = _observed_returncode(observed)
            diagnostics["returncode"] = _reap_observed(process, observed)
            diagnostics["direct_child_reaped"] = True
    except ChildProcessError:
        diagnostics["ownership_lost"] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        diagnostics["wait_error"] = {
            "type": type(error).__name__,
            "errno": getattr(error, "errno", None),
        }
    diagnostics["cleanup_wall_ns"] = time.perf_counter_ns() - started
    return diagnostics


def _supervise(phase, parts, expected, started_ns, deadline_ns, grace_ms, lease_check):
    code = f"rc_fiber_worker_{phase}_"
    process = None
    receiver = _FrameReceiver("output", phase)
    stderr_tail = bytearray()
    stderr_total = 0
    selector = None
    endpoints = []
    closed = set()
    part_index = part_offset = 0
    received_ns = None
    lease_failure = None

    def check_lease():
        nonlocal lease_failure
        try:
            lease_check()
        except BaseException as error:
            lease_failure = error
            raise

    try:
        selector = selectors.DefaultSelector()
        check_lease()
        if time.perf_counter_ns() >= deadline_ns:
            raise RCFiberPhaseError(
                code + "timeout", "phase deadline passed before launch"
            )
        process = subprocess.Popen(
            _child_argv(os.getpid()),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_child_environment(),
            cwd="/tmp",
            start_new_session=True,
            close_fds=True,
        )
        # Track all owned endpoints before setup can fail for any one of them.
        endpoints.extend((process.stdin, process.stdout, process.stderr))
        for stream, events, role in (
            (process.stdin, selectors.EVENT_WRITE, "stdin"),
            (process.stdout, selectors.EVENT_READ, "stdout"),
            (process.stderr, selectors.EVENT_READ, "stderr"),
        ):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, events, role)
        while True:
            check_lease()
            now = time.perf_counter_ns()
            if now >= deadline_ns:
                raise RCFiberPhaseError(
                    code + "timeout", "numerical phase exceeded its authored deadline"
                )
            observed = _observe_exit(process)
            if observed is not None and {"stdin", "stdout", "stderr"} <= closed:
                if _observed_returncode(observed) != 0:
                    raise ValueError(
                        "numerical child exited without a successful complete transport"
                    )
                metadata, segments = receiver.value()
                reply = _check_reply(
                    metadata,
                    segments,
                    expected,
                    started_ns,
                    received_ns if received_ns is not None else now,
                )
                check_lease()
                if time.perf_counter_ns() >= deadline_ns:
                    raise RCFiberPhaseError(
                        code + "timeout",
                        "complete phase reply arrived after its deadline",
                    )
                total = {
                    "wall_ns": time.perf_counter_ns() - started_ns,
                    "child_pid": process.pid,
                    "child_returncode": _observed_returncode(observed),
                    "direct_child_reaped": True,
                    "stderr_byte_count": stderr_total,
                    "stderr_retained_bytes": len(stderr_tail),
                    "stderr_truncated": stderr_total > len(stderr_tail),
                    "scope": "parent launch/request/import/API/export/IPC/reap; contains child API scope",
                }
                # End an ordinary lingering same-group process without attributing it to API time.
                cleanup = {
                    "pid": process.pid,
                    "signals_sent": [],
                    "signal_errors": [],
                    "direct_child_reaped": False,
                    "direct_child_exit_observed": True,
                    "returncode": _observed_returncode(observed),
                }
                _signal_group(process, signal.SIGKILL, cleanup)
                if cleanup["signal_errors"]:
                    raise RCFiberPhaseError(
                        code + "cleanup_failed",
                        "completed child's group cleanup was not confirmed",
                        cleanup=cleanup,
                    )
                _reap_observed(process, observed)
                total["wall_ns"] = time.perf_counter_ns() - started_ns
                if time.perf_counter_ns() >= deadline_ns:
                    raise RCFiberPhaseError(
                        code + "timeout", "phase cleanup completed after its deadline"
                    )
                return RCFiberPhaseReply(
                    reply.status,
                    reply._timing_bytes,
                    reply.raw_result,
                    reply.native_checkpoint,
                    reply._verification_bytes,
                    reply.error_type,
                    reply._artifact_error_bytes,
                    _json(total),
                )
            wait = min(_POLL_SECONDS, max(0, (deadline_ns - now) / 1e9))
            for key, _events in selector.select(wait):
                stream, role = key.fileobj, key.data
                if role == "stdin":
                    while part_index < len(parts) and part_offset == len(
                        parts[part_index]
                    ):
                        part_index += 1
                        part_offset = 0
                    if part_index == len(parts):
                        selector.unregister(stream)
                        stream.close()
                        closed.add("stdin")
                        continue
                    try:
                        count = os.write(
                            stream.fileno(),
                            memoryview(parts[part_index])[
                                part_offset : part_offset + _IO_CHUNK_BYTES
                            ],
                        )
                        part_offset += count
                    except BrokenPipeError as error:
                        raise ValueError(
                            "child closed input before consuming its original frame"
                        ) from error
                    except BlockingIOError:
                        continue
                else:
                    try:
                        raw = os.read(stream.fileno(), _IO_CHUNK_BYTES)
                    except BlockingIOError:
                        continue
                    if not raw:
                        selector.unregister(stream)
                        stream.close()
                        closed.add(role)
                    elif role == "stdout":
                        receiver.feed(raw)
                        if receiver.complete:
                            received_ns = time.perf_counter_ns()
                    else:
                        stderr_total += len(raw)
                        stderr_tail.extend(raw)
                        if len(stderr_tail) > _STDERR_MAX_BYTES:
                            del stderr_tail[:-_STDERR_MAX_BYTES]
    except BaseException as error:
        cleanup = {} if process is None else _stop_process(process, grace_ms)
        if isinstance(error, RCFiberPhaseError) and error.cleanup:
            cleanup["prior_cleanup"] = error.cleanup
        if process is not None:
            cleanup.update(
                {
                    "stderr_byte_count": stderr_total,
                    "stderr_retained_bytes": len(stderr_tail),
                    "stderr_truncated": stderr_total > len(stderr_tail),
                }
            )
        if process is not None and (
            not cleanup["direct_child_reaped"]
            or cleanup["signal_errors"]
            or cleanup.get("ownership_lost")
            or cleanup.get("wait_error")
        ):
            raise RCFiberPhaseError(
                code + "cleanup_failed",
                "direct-child cleanup was not confirmed",
                cleanup=cleanup,
            ) from error
        if isinstance(error, RCFiberPhaseError):
            raise RCFiberPhaseError(
                error.code, error.detail, cleanup=cleanup
            ) from error
        if error is lease_failure:
            raise
        if not isinstance(
            error,
            (
                ValueError,
                TypeError,
                KeyError,
                RecursionError,
                OverflowError,
                OSError,
                subprocess.SubprocessError,
            ),
        ):
            raise  # Includes the original stale lease/keeper error after cleanup.
        raise RCFiberPhaseError(
            code + "transport_invalid", "phase transport/launch failed", cleanup=cleanup
        ) from error
    finally:
        if selector is not None:
            selector.close()
        for stream in endpoints:
            if not stream.closed:
                stream.close()


def run_rc_fiber_phase(
    *,
    phase: str,
    request_bytes: bytes,
    completed_before: int,
    completed_after: int,
    restart: bytes | None,
    result: bytes | None = None,
    checkpoint: bytes | None = None,
    policy,
    lease_check: Callable[[], None],
) -> RCFiberPhaseReply:
    """Execute one authored phase; incomplete work never yields a measured reply."""
    started_ns = time.perf_counter_ns()
    from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy

    if phase not in ("analysis", "verification") or type(phase) is not str:
        raise RCFiberPhaseError(
            "rc_fiber_worker_analysis_unsupported", "unknown numerical phase"
        )
    code = f"rc_fiber_worker_{phase}_"
    if (
        sys.platform != "linux"
        or type(policy) is not RCFiberPhasePolicy
        or not callable(lease_check)
    ):
        raise RCFiberPhaseError(
            code + "unsupported",
            "exact authored policy and Linux phase support required",
        )
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise RCFiberPhaseError(
            code + "unsupported",
            "phase execution requires default SIGCHLD and exclusive child-wait ownership",
        )
    timeout_ms = (
        policy.analysis_timeout_ms
        if phase == "analysis"
        else policy.verification_timeout_ms
    )
    deadline_ns = started_ns + timeout_ms * 1_000_000
    values = (request_bytes, restart, result, checkpoint)
    caps = (_REQUEST_MAX_BYTES, _NATIVE_MAX_BYTES, _RESULT_MAX_BYTES, _NATIVE_MAX_BYTES)
    if (
        request_bytes is None
        or any(
            value is not None
            and (type(value) is not bytes or not 1 <= len(value) <= cap)
            for value, cap in zip(values, caps, strict=True)
        )
        or (phase == "analysis" and (result is not None or checkpoint is not None))
        or (phase == "verification" and result is None)
    ):
        raise RCFiberPhaseError(
            code + "unsupported", "phase immutable artifact byte bounds/roles invalid"
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
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise RCFiberPhaseError(
            code + "transport_invalid", "original request/phase/source binding invalid"
        ) from error
    return _supervise(
        phase,
        parts,
        expected,
        started_ns,
        deadline_ns,
        policy.termination_grace_ms,
        lease_check,
    )


def _read_input_frame():
    # The input phase is only available in metadata; permissive header roles are
    # tightened by the complete identity before solver import/invocation.
    receiver = _FrameReceiver("input", "verification")
    # A verification header normally requires result; the child accepts either
    # role until its original identity is decoded.
    receiver.phase = "input-unbound"
    while True:
        raw = sys.stdin.buffer.read(_IO_CHUNK_BYTES)
        if not raw:
            break
        receiver.feed(raw)
    return receiver.value()


def _write_frame(stream, metadata, segments):
    metadata = dict(metadata, segment_hashes=[_hash(value) for value in segments])
    for part in _frame_parts(metadata, segments):
        view = memoryview(part)
        offset = 0
        while offset < len(view):
            count = stream.write(view[offset : offset + _IO_CHUNK_BYTES])
            if not count:
                raise ValueError(
                    "phase output stream stopped before its complete frame"
                )
            offset += count
    stream.flush()


def _execute_child(metadata, segments):
    if set(metadata) != {"schema_version", "identity", "policy", "segment_hashes"}:
        raise ValueError("phase child input envelope has unknown fields")
    from structural_analysis.execution.rc_fiber_phase_policy import (
        decode_rc_fiber_phase_policy,
    )

    identity = metadata["identity"]
    if type(identity) is not dict or identity.get("phase") not in (
        "analysis",
        "verification",
    ):
        raise ValueError("phase child input identity invalid")
    policy = decode_rc_fiber_phase_policy(metadata["policy"])
    request_bytes, restart, raw_result, native = segments
    expected = _input_metadata(
        identity["phase"],
        request_bytes,
        identity["completed_before"],
        identity["completed_after"],
        restart,
        raw_result,
        native,
        policy,
    )
    if metadata != expected:
        raise ValueError("phase child original input/source identity mismatch")
    from dataclasses import replace
    from structural_analysis.api import rc_fiber_frame_direct_control as api
    from structural_analysis.execution.rc_fiber_job_contract import (
        validate_rc_fiber_job_request,
    )

    request = _strict_object(request_bytes)
    model, config = validate_rc_fiber_job_request(request)
    chunk = replace(
        config,
        targets_m=config.targets_m[
            identity["completed_before"] : identity["completed_after"]
        ],
    )
    if chunk.request_hash != identity["chunk_request_hash"]:
        raise ValueError("phase child reconstructed chunk hash differs")
    kwargs = chunk.api_kwargs()
    kwargs["restart"] = restart
    kwargs["reuse_line_search_assembly"] = request["execution_config"].get(
        "reuse_line_search_assembly", False
    )
    wall_started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
    status, error_type = "returned", None
    output = (None, None, None, None)
    try:
        if identity["phase"] == "analysis":
            value = api.analyze_bounded_rc_fiber_direct_control(
                model, chunk.targets_m, **kwargs
            )
            payload = value.to_dict()
            raw = value.result_artifact_bytes()
            checkpoint = (
                value.checkpoint_artifact_bytes()
                if payload["checkpoint"] is not None
                else None
            )
            output = (raw, checkpoint, None, None)
        else:
            report = api.validate_bounded_rc_fiber_direct_control_artifacts(
                model, chunk.targets_m, result=raw_result, checkpoint=native, **kwargs
            ).to_dict()
            output = (None, None, _json(report), None)
    except Exception as error:
        status, error_type = "raised", type(error).__name__
        report = (
            _json(error.to_dict())
            if isinstance(error, api.BoundedRCFiberDirectControlArtifactError)
            else None
        )
        output = (None, None, None, report)
    cpu_finished, wall_finished = time.process_time_ns(), time.perf_counter_ns()
    reply = {
        "schema_version": _SCHEMA,
        "identity": identity,
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
    }
    return reply, output


def _child_main():
    # Keep protocol stdout isolated from Python and native solver stdout. The
    # duplicate pipe endpoint is owned here and never handed to the solver.
    reply_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    with os.fdopen(reply_fd, "wb", buffering=0) as stream:
        metadata, segments = _read_input_frame()
        reply, output = _execute_child(metadata, segments)
        _write_frame(stream, reply, output)


if __name__ == "__main__":
    _child_main()
