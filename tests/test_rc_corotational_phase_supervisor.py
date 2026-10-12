"""Pure corotational transport contracts; no process, source or numerical proof."""

from copy import deepcopy
import json
import signal

import pytest

from structural_analysis.execution import rc_corotational_phase_supervisor as supervisor
from structural_analysis.execution import rc_fiber_phase_supervisor as common
from structural_analysis.execution.rc_corotational_job_request import (
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_phase_policy import (
    RCCorotationalPhasePolicy,
    decode_rc_corotational_phase_policy,
)
from tests.test_rc_corotational_phase_policy import request


@pytest.fixture(autouse=True)
def forbid_process_numerical_and_source_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail(
            "pure transport test invoked process, numerical API or source fingerprint"
        )

    source_hashes = {name: "sha256:" + "a" * 64 for name in supervisor._SOURCE_FILES}
    monkeypatch.setattr(supervisor, "_source_hashes", lambda: dict(source_hashes))
    monkeypatch.setattr(common, "_source_hashes", forbidden)
    monkeypatch.setattr(common, "_supervise", forbidden)
    monkeypatch.setattr(common.subprocess, "Popen", forbidden)
    monkeypatch.setattr(common.os, "sched_getaffinity", lambda _pid: {0})
    for module, names in (
        (
            "structural_analysis.api.rc_corotational_control",
            (
                "analyze_rc_corotational_control",
                "validate_rc_corotational_control_artifacts",
                "solve_stateful_corotational_fiber_frame2d_load_step",
                "run_corotational_control_subdivision",
                "_source_identity",
            ),
        ),
        (
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision",
            (
                "solve_stateful_corotational_fiber_frame2d_displacement_control_step",
                "_source_identity",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(f"{module}.{name}", forbidden)


def expected(*, phase="analysis", before=0, lower_policy=False):
    payload = request()
    if lower_policy:
        payload["execution_config"]["phase_execution_policy"].update(
            analysis_timeout_ms=1,
            verification_timeout_ms=1,
            termination_grace_ms=1,
        )
    policy = decode_rc_corotational_phase_policy(
        payload["execution_config"]["phase_execution_policy"]
    )
    raw = rc_corotational_job_canonical_bytes(payload)
    restart = None if before == 0 else b"synthetic-native-restart"
    result = b"synthetic-original-result" if phase == "verification" else None
    native = b"synthetic-original-native" if phase == "verification" else None
    planned = before + payload["execution_config"]["attempt_limit_per_call"]
    metadata = supervisor._input_metadata(
        phase, raw, before, planned, restart, result, native, policy
    )
    return metadata, (raw, restart, result, native), policy


def reply(original, *, error_type=None, work=None):
    phase = original["identity"]["phase"]
    segments = (
        b"synthetic-result" if phase == "analysis" and error_type is None else None,
        b"synthetic-native" if phase == "analysis" and error_type is None else None,
        common._json({"contract_pass": False})
        if phase == "verification" and error_type is None
        else None,
        None if work is None else common._json(work),
    )
    metadata = {
        "schema_version": supervisor._SCHEMA,
        "identity": deepcopy(original["identity"]),
        "policy": deepcopy(original["policy"]),
        "segment_hashes": [common._hash(value) for value in segments],
        "status": "returned" if error_type is None else "raised",
        "error_type": error_type,
        "timing": {"wall_ns": 800, "process_cpu_ns": 100},
        "measurement": {
            "wall_started_ns": 1200,
            "wall_finished_ns": 2000,
            "cpu_started_ns": 100,
            "cpu_finished_ns": 200,
        },
    }
    return metadata, segments


def frame(metadata, segments):
    return b"".join(supervisor._frame_parts(metadata, segments))


def checked_reply(metadata, segments, original):
    return supervisor._check_reply(metadata, segments, original, 1000, 3000)


@pytest.mark.parametrize("phase", ["analysis", "verification"])
@pytest.mark.parametrize("piece_size", [1, 7, 65536])
def test_incremental_binary_frames_preserve_whole_request_and_exact_segments(
    phase, piece_size
):
    metadata, segments, _policy = expected(phase=phase, before=2)
    receiver = supervisor._FrameReceiver("input", phase)
    wire = frame(metadata, segments)
    for offset in range(0, len(wire), piece_size):
        receiver.feed(wire[offset : offset + piece_size])
    decoded, recovered = receiver.value()
    assert decoded == metadata and recovered == segments
    assert decoded["identity"]["completed_before"] == 2
    assert decoded["identity"]["planned_after"] == 3
    assert decoded["identity"]["restart_input_sha256"] == common._hash(segments[1])
    assert decoded["identity"]["source_hashes"] == {
        name: "sha256:" + "a" * 64 for name in supervisor._SOURCE_FILES
    }
    assert (
        json.loads(recovered[0])["config"]["targets_m"]
        == request()["config"]["targets_m"]
    )


@pytest.mark.parametrize("phase", ["analysis", "verification"])
def test_returned_reply_frame_and_measured_clocks_are_transport_only(phase):
    original, _segments, _policy = expected(phase=phase)
    metadata, segments = reply(original)
    receiver = supervisor._FrameReceiver("output", phase)
    receiver.feed(frame(metadata, segments))
    decoded, recovered = receiver.value()
    checked = checked_reply(decoded, recovered, original)
    assert checked.status == "returned"
    assert checked.timing == {"wall_ns": 800, "process_cpu_ns": 100}
    if phase == "analysis":
        assert checked.raw_result == b"synthetic-result"
        assert checked.native_checkpoint == b"synthetic-native"
    else:
        assert checked.verification_report == {"contract_pass": False}


def test_header_caps_are_exact_and_rejected_before_segment_allocation():
    mib = 1024 * 1024
    assert (
        supervisor._REQUEST_MAX_BYTES,
        supervisor._NATIVE_MAX_BYTES,
        supervisor._RESULT_MAX_BYTES,
        supervisor._REPORT_MAX_BYTES,
        supervisor._FRAME_SEGMENTS_MAX_BYTES,
    ) == (16 * mib, 16 * mib, 64 * mib, 64 * mib, 112 * mib)
    assert (common._NATIVE_MAX_BYTES, common._RESULT_MAX_BYTES) == (8 * mib, 512 * mib)
    caps = (16 * mib, 16 * mib, 64 * mib, 16 * mib)
    receiver = supervisor._FrameReceiver("input", "verification")
    receiver.feed(common._HEADER.pack(supervisor._MAGIC, 1, *caps))
    assert receiver.lengths == caps
    assert all(not value for value in receiver.buffers)
    for direction, phase, baseline, limits in (
        (
            "input",
            "verification",
            [1, 0, 1, 0],
            [16 * mib, 16 * mib, 64 * mib, 16 * mib],
        ),
        ("output", "pending", [0, 0, 0, 0], [64 * mib, 16 * mib, 64 * mib, 64 * mib]),
    ):
        for index, limit in enumerate(limits):
            oversized = list(baseline)
            oversized[index] = limit + 1
            receiver = supervisor._FrameReceiver(direction, phase)
            with pytest.raises(ValueError, match="bounds"):
                receiver.feed(common._HEADER.pack(supervisor._MAGIC, 1, *oversized))
            assert all(not value for value in receiver.buffers)
    receiver = supervisor._FrameReceiver("output", "pending")
    with pytest.raises(ValueError, match="bounds"):
        receiver.feed(
            common._HEADER.pack(supervisor._MAGIC, 1, 64 * mib, 0, 64 * mib, 0)
        )
    for metadata_size in (0, supervisor._METADATA_MAX_BYTES + 1):
        with pytest.raises(ValueError, match="bounds"):
            supervisor._FrameReceiver("input", "analysis").feed(
                common._HEADER.pack(supervisor._MAGIC, metadata_size, 1, 0, 0, 0)
            )


@pytest.mark.parametrize(
    "direction,phase,lengths",
    [
        ("input", "analysis", (0, 0, 0, 0)),
        ("input", "analysis", (1, 0, 1, 0)),
        ("input", "analysis", (1, 0, 0, 1)),
        ("input", "verification", (1, 0, 0, 0)),
        ("output", "analysis", (0, 0, 1, 0)),
        ("output", "verification", (1, 0, 0, 0)),
        ("output", "verification", (0, 1, 1, 0)),
        ("output", "analysis", (1, 0, 0, 1)),
    ],
)
def test_declared_input_and_output_segment_roles_fail_closed(direction, phase, lengths):
    with pytest.raises(ValueError):
        supervisor._FrameReceiver(direction, phase).feed(
            common._HEADER.pack(supervisor._MAGIC, 1, *lengths)
        )


def test_emitter_enforces_directional_caps_and_exact_bytes(monkeypatch):
    original, segments, _policy = expected()
    for invalid in (
        (b"a",),
        (b"", None, None, None),
        (bytearray(b"a"), None, None, None),
        (segments[0], None, b"result", None),
    ):
        with pytest.raises(ValueError):
            supervisor._frame_parts(original, invalid)
    monkeypatch.setattr(supervisor, "_NATIVE_MAX_BYTES", 8)
    with pytest.raises(ValueError, match="bounds"):
        supervisor._frame_parts(original, (segments[0], b"n" * 9, None, None))


def test_old_namespace_corruption_truncation_and_noncanonical_metadata_rejected():
    original, segments, _policy = expected()
    wire = frame(original, segments)
    with pytest.raises(ValueError):
        supervisor._FrameReceiver("input", "analysis").feed(
            common._HEADER.pack(common._MAGIC, 1, 1, 0, 0, 0)
        )
    for size in (1, common._HEADER.size - 1, len(wire) - 1):
        receiver = supervisor._FrameReceiver("input", "analysis")
        receiver.feed(wire[:size])
        with pytest.raises(ValueError, match="truncated"):
            receiver.value()
    receiver = supervisor._FrameReceiver("input", "analysis")
    receiver.feed(wire)
    with pytest.raises(ValueError, match="trailing"):
        receiver.feed(b"x")
    receiver = supervisor._FrameReceiver("input", "analysis")
    receiver.feed(wire[:-1] + bytes([wire[-1] ^ 1]))
    with pytest.raises(ValueError, match="hash mismatch"):
        receiver.value()
    for invalid in (
        b'{"segment_hashes":[],"segment_hashes":[]}',
        b'{"a":NaN}',
        b' {"segment_hashes":[]}',
    ):
        receiver = supervisor._FrameReceiver("output", "pending")
        receiver.feed(
            common._HEADER.pack(supervisor._MAGIC, len(invalid), 0, 0, 0, 0) + invalid
        )
        with pytest.raises(ValueError):
            receiver.value()


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_request_hash", "sha256:" + "b" * 64),
        ("chunk_request_hash", "sha256:" + "b" * 64),
        ("completed_before", False),
        ("completed_before", 0.0),
        ("planned_after", True),
        ("planned_after", 1.0),
        ("source_revision", "c" * 40),
        ("source_hashes", {"api": "sha256:" + "b" * 64}),
        ("restart_input_sha256", "sha256:" + "b" * 64),
        ("analysis_result_sha256", "sha256:" + "b" * 64),
    ],
)
def test_reply_identity_values_and_exact_numeric_types_bind_to_parent(field, value):
    original, _segments, _policy = expected()
    metadata, segments = reply(original)
    metadata["identity"][field] = value
    with pytest.raises(ValueError):
        checked_reply(metadata, segments, original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("analysis_timeout_ms", True),
        ("analysis_timeout_ms", 1.0),
        ("verification_timeout_ms", True),
        ("termination_grace_ms", True),
        ("analysis_timeout_ms", 2),
        ("schema_version", "bounded-rc-fiber-phase-execution-policy.v1"),
    ],
)
def test_reply_policy_exact_integer_types_and_namespace_are_not_python_value_equality(
    field, value
):
    original, _segments, _policy = expected(lower_policy=True)
    metadata, segments = reply(original)
    metadata["policy"][field] = value
    with pytest.raises(ValueError):
        checked_reply(metadata, segments, original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("wall_started_ns", True),
        ("wall_started_ns", 999),
        ("wall_finished_ns", 3001),
        ("wall_finished_ns", 1100),
        ("cpu_started_ns", -1),
        ("cpu_finished_ns", 99),
        ("cpu_finished_ns", 2**63),
    ],
)
def test_reply_measured_clock_fields_reject_invalid_or_out_of_window_counts(
    field, value
):
    original, _segments, _policy = expected()
    metadata, segments = reply(original)
    metadata["measurement"][field] = value
    with pytest.raises(ValueError):
        checked_reply(metadata, segments, original)


def test_reply_clock_derived_deltas_and_possible_child_cpu_bound():
    original, _segments, _policy = expected()
    for field, value in (
        ("wall_ns", True),
        ("wall_ns", 799),
        ("process_cpu_ns", 101),
        ("process_cpu_ns", -1),
    ):
        metadata, segments = reply(original)
        metadata["timing"][field] = value
        with pytest.raises(ValueError):
            checked_reply(metadata, segments, original)
    metadata, segments = reply(original)
    metadata["measurement"].update(cpu_started_ns=0, cpu_finished_ns=1_000_801)
    metadata["timing"]["process_cpu_ns"] = 1_000_801
    with pytest.raises(ValueError, match="CPU clocks"):
        checked_reply(metadata, segments, original)


def test_reply_exact_top_fields_namespaces_and_phase_roles():
    original, _segments, _policy = expected()
    metadata, segments = reply(original)
    for invalid in (
        dict(metadata, schema_version=common._SCHEMA),
        dict(metadata, extra=True),
    ):
        with pytest.raises(ValueError):
            checked_reply(invalid, segments, original)
    for field in ("policy", "measurement", "identity"):
        invalid = deepcopy(metadata)
        del invalid[field]
        with pytest.raises(ValueError):
            checked_reply(invalid, segments, original)
    with pytest.raises(ValueError):
        checked_reply(metadata, (None, None, b"{}", None), original)
    original, _segments, _policy = expected(phase="verification")
    metadata, segments = reply(original)
    with pytest.raises(ValueError):
        checked_reply(metadata, (b"raw", None, segments[2], None), original)


def test_partial_work_exception_keeps_unknown_work_and_has_own_exception_namespace():
    original, _segments, _policy = expected()
    work = {
        "preload_solver_calls": 1,
        "restart_replay_solver_calls": 0,
        "control_solver_calls": 0,
        "unavailable_execution_work": True,
    }
    metadata, segments = reply(
        original, error_type="RCCorotationalControlExecutionError", work=work
    )
    checked = checked_reply(metadata, segments, original)
    assert (
        checked.status == "raised"
        and checked.error_type == "RCCorotationalControlExecutionError"
    )
    assert checked.artifact_error_report == work
    with pytest.raises(ValueError):
        checked_reply(metadata, (None, None, None, None), original)
    for changed in (
        dict(work, unavailable_execution_work=False),
        dict(work, control_solver_calls=True),
        dict(work, extra=1),
    ):
        metadata, segments = reply(
            original, error_type="RCCorotationalControlExecutionError", work=changed
        )
        with pytest.raises(ValueError):
            checked_reply(metadata, segments, original)
    metadata, segments = reply(original, error_type="ValueError", work=work)
    with pytest.raises(ValueError):
        checked_reply(metadata, segments, original)
    metadata, segments = reply(
        original, error_type="BoundedRCFiberDirectControlArtifactError"
    )
    with pytest.raises(ValueError):
        checked_reply(metadata, segments, original)


def test_original_policy_restart_and_planned_span_reject_before_numerical_child():
    original, segments, policy = expected(before=2)
    with pytest.raises(ValueError):
        supervisor._input_metadata(
            "analysis",
            segments[0],
            2,
            3,
            segments[1],
            None,
            None,
            RCCorotationalPhasePolicy(1, 1, 1),
        )
    with pytest.raises(ValueError):
        supervisor._input_metadata(
            "analysis", segments[0], 2, 4, segments[1], None, None, policy
        )
    for field, value in (
        ("job_request_hash", "sha256:" + "b" * 64),
        ("completed_before", False),
        ("source_hashes", {"api": "sha256:" + "b" * 64}),
    ):
        altered = deepcopy(original)
        altered["identity"][field] = value
        with pytest.raises(ValueError):
            supervisor._execute_child(altered, segments)
    payload = json.loads(segments[0])
    payload["schema_version"] = "structural-analysis-job-request.v6"
    del payload["execution_config"]["phase_execution_policy"]
    with pytest.raises(ValueError):
        supervisor._input_metadata(
            "analysis",
            rc_corotational_job_canonical_bytes(payload),
            0,
            1,
            None,
            None,
            None,
            policy,
        )


def test_public_host_preflight_and_private_backend_routing_without_process_launch(
    monkeypatch,
):
    original, segments, policy = expected()
    monkeypatch.setattr(supervisor.sys, "platform", "linux")
    monkeypatch.setattr(supervisor.signal, "getsignal", lambda _signal: signal.SIG_DFL)
    observed = []

    def capture(*args, **kwargs):
        observed.append((args, kwargs))
        return "synthetic-supervisor-boundary"

    monkeypatch.setattr(common, "_supervise", capture)
    result = supervisor.run_rc_corotational_phase(
        phase="analysis",
        request_bytes=segments[0],
        completed_before=0,
        completed_after=1,
        restart=None,
        policy=policy,
        lease_check=lambda: None,
    )
    assert result == "synthetic-supervisor-boundary"
    args, kwargs = observed[0]
    assert args[2] == original
    assert args[4] - args[3] == policy.analysis_timeout_ms * 1_000_000
    assert args[5] == policy.termination_grace_ms
    backend = kwargs["backend"]
    assert backend.code_prefix == "rc_corotational_worker_"
    assert backend.receiver is supervisor._FrameReceiver
    assert backend.check_reply is supervisor._check_reply
    count = len(observed)
    with pytest.raises(ValueError):
        supervisor.run_rc_corotational_phase(
            phase="unknown",
            request_bytes=segments[0],
            completed_before=0,
            completed_after=1,
            restart=None,
            policy=policy,
            lease_check=lambda: None,
        )
    monkeypatch.setattr(supervisor.sys, "platform", "unsupported")
    with pytest.raises(common.RCFiberPhaseError):
        supervisor.validate_corotational_phase_host(policy)
    monkeypatch.setattr(supervisor.sys, "platform", "linux")
    for bad in (None, False):
        with pytest.raises(common.RCFiberPhaseError):
            supervisor.validate_corotational_phase_host(bad)
    monkeypatch.setattr(supervisor.signal, "getsignal", lambda _signal: signal.SIG_IGN)
    with pytest.raises(common.RCFiberPhaseError):
        supervisor.validate_corotational_phase_host(policy)
    monkeypatch.setattr(supervisor.signal, "getsignal", lambda _signal: signal.SIG_DFL)
    for bad in (False, -1, 2, 2**31):
        with pytest.raises(common.RCFiberPhaseError):
            supervisor.validate_corotational_phase_host(policy, authority_fd=bad)
    assert len(observed) == count
