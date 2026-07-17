from __future__ import annotations

import ctypes
from dataclasses import replace
from pathlib import Path
import struct
import sys

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_terminal_guard_plan_v1 as plan_module,
)
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_terminal_guard_rtc_v1 as rtc_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_context_v2 import (  # noqa: E402
    HIP_FGMRES_RTC_SOURCE_SHA256_V2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_terminal_guard_plan_v1 import (  # noqa: E402
    HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1,
    HipFgmresFixedRankCoarseTerminalGuardPlanV1Error,
    hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1,
    hip_fgmres_fixed_rank_coarse_terminal_guard_abi_payload_v1,
    hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1,
    hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_terminal_guard_rtc_v1 import (  # noqa: E402
    HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_IDENTITY_SCHEMA_VERSION_V1,
    HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1,
    HipRtcFgmresFixedRankCoarseTerminalGuardV1Error,
    _KERNEL_MINT,
    compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1,
    validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.backends.hip.context import (  # noqa: E402
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    load_hip_native_runtime,
)
from structural_analysis.engine_v2.backends.hip.transfer_audit_v1 import (  # noqa: E402
    _capture_bound_copy_audit_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (  # noqa: E402
    _compile_fixed_source,
    _load_hiprtc_api,
)


KERNEL_DIRECTORY = SRC_ROOT / "structural_analysis/engine_v2/assembly_backend/kernels"
RECURRENCE = KERNEL_DIRECTORY / "engine_v2_fgmres_v2.hip.cpp"
GUARD = (
    KERNEL_DIRECTORY / "engine_v2_fgmres_fixed_rank_coarse_terminal_guard_v1.hip.cpp"
)


class _Runtime:
    def __init__(self) -> None:
        self.launch_statuses: list[int | BaseException] = []
        self.launches: list[dict[str, object]] = []
        self.unload_status: int | BaseException = 0
        self.unloads = 0

    def launch(self, function: object, **keywords: object) -> int:
        parameters = keywords["parameters"]
        assert isinstance(parameters, ctypes.Array)
        argument_values = tuple(
            ctypes.cast(parameter, ctypes.POINTER(ctypes.c_void_p)).contents.value
            for parameter in parameters
        )
        self.launches.append(
            {
                "function": function,
                "argument_values": argument_values,
                **keywords,
            }
        )
        outcome = self.launch_statuses.pop(0) if self.launch_statuses else 0
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def unload(self, _module: object) -> int:
        self.unloads += 1
        if isinstance(self.unload_status, BaseException):
            raise self.unload_status
        return self.unload_status

    def error_string(self, status: int) -> str:
        return f"status={status}"


def _kernel(
    monkeypatch: pytest.MonkeyPatch,
    runtime: _Runtime | None = None,
) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
    monkeypatch.setattr(
        rtc_module,
        "validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1",
        lambda identity: identity,
    )
    return HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1(
        runtime=runtime or _Runtime(),  # type: ignore[arg-type]
        module=ctypes.c_void_p(1),
        function=ctypes.c_void_p(2),
        identity=None,  # type: ignore[arg-type]
        _mint=_KERNEL_MINT,
    )


def _launch(
    kernel: HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1,
    **updates: object,
) -> None:
    values: dict[str, object] = {
        "stream": 11,
        "maximum_restart_count": 4,
        "coarse_status": 0x100000,
        "control_state": 0x200000,
        "solve_record": 0x300000,
    }
    values.update(updates)
    kernel.launch_guard(**values)  # type: ignore[arg-type]


def test_source_contract_preserves_frozen_recurrence_and_device_only_guard() -> None:
    recurrence = RECURRENCE.read_bytes()
    guard = GUARD.read_bytes()
    source = hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1()
    components = hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1()

    assert components["recurrence"]["sha256"] == HIP_FGMRES_RTC_SOURCE_SHA256_V2
    assert components["recurrence"]["byte_length"] == len(recurrence)
    assert components["guard"]["byte_length"] == len(guard)
    assert components["combined"]["byte_length"] == len(source)
    assert source == recurrence + b"\n" + guard
    assert (
        guard.count(HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1.encode()) == 1
    )
    guard_text = guard.decode("utf-8")
    assert "engine_v2_terminal_failure_if_error_clear(" in guard_text
    assert "kCoarseGuardInactive = 1u << 31" in guard_text
    for forbidden in (
        "hipMalloc",
        "hipFree",
        "hipMemcpy",
        "hipStreamSynchronize",
        "cuda",
        "malloc(",
    ):
        assert forbidden not in guard_text


def test_guard_abi_is_deterministic_and_keeps_claims_bounded() -> None:
    first = hip_fgmres_fixed_rank_coarse_terminal_guard_abi_payload_v1()
    second = hip_fgmres_fixed_rank_coarse_terminal_guard_abi_payload_v1()

    assert first == second
    assert first is not second
    assert first["launch"] == {
        "grid": [1, 1, 1],
        "block": [1, 1, 1],
        "same_stream_after_typed_slot_apply": True,
        "arguments": [
            "coarse_status",
            "fgmres_control_state_v2",
            "solve_record",
        ],
    }
    assert first["status_mapping"]["inactive_bit_31"] == (
        "exact_value_no_op_mixed_bits_fail_closed"
    )
    assert first["status_mapping"]["first_device_error_wins"]
    boundary = first["claim_boundary"]
    assert boundary["device_direct_terminal_publication_implemented"]
    assert boundary["host_copy_count"] == 0
    assert boundary["host_branch_count"] == 0
    assert boundary["intermediate_synchronization_count"] == 0
    assert boundary["coarse_device_status_directly_terminal_bound"]
    assert boundary["live_recurrence_integration_performed"]
    assert boundary["actual_device_execution_performed"]
    assert not boundary["promotion_eligible"]
    assert not boundary["commercial_ready"]
    assert canonical_hash(first) == (
        hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1()
    )


def test_frozen_recurrence_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changed = tmp_path / RECURRENCE.name
    changed.write_bytes(RECURRENCE.read_bytes() + b"\n// drift\n")
    monkeypatch.setattr(plan_module, "_RECURRENCE_PATH", changed)

    with pytest.raises(HipFgmresFixedRankCoarseTerminalGuardPlanV1Error) as exc_info:
        hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1()
    assert exc_info.value.code == (
        "hip_fgmres_coarse_terminal_guard_recurrence_source_changed"
    )


@pytest.mark.parametrize("architecture", ("gfx1030", "gfx1100"))
def test_combined_guard_source_compiles_with_available_hiprtc(
    architecture: str,
) -> None:
    if not Path("/opt/rocm/lib/libhiprtc.so").exists():
        pytest.skip("libhiprtc is not installed")
    rtc = _load_hiprtc_api(None)
    code_object, compile_log = _compile_fixed_source(
        rtc,
        hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1(),
        (
            f"--offload-arch={architecture}",
            *HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1,
        ),
        program_name=GUARD.name,
    )
    assert code_object
    assert compile_log == ""


def test_launch_is_exact_one_by_one_and_requires_matching_parent_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)

    _launch(kernel)
    assert len(runtime.launches) == 1
    launch = runtime.launches[0]
    assert launch["function"].value == 2  # type: ignore[union-attr]
    assert (launch["grid_x"], launch["block_x"]) == (1, 1)
    assert launch["stream"].value == 11  # type: ignore[union-attr]
    assert launch["argument_values"] == (0x100000, 0x200000, 0x300000)
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 1
    assert kernel.lifetime_attempted_launch_count == 1
    assert kernel.lifetime_accepted_launch_count == 1
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as pending:
        kernel.close()
    assert pending.value.code == "hip_rtc_fgmres_coarse_terminal_guard_pending_work"
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as wrong:
        kernel.acknowledge_stream_fence(12)
    assert wrong.value.code == (
        "hip_rtc_fgmres_coarse_terminal_guard_fence_stream_invalid"
    )
    assert kernel.acknowledge_stream_fence(11) == 1
    kernel.close()
    assert kernel.closed
    assert runtime.unloads == 1


@pytest.mark.parametrize(
    "updates",
    (
        {"maximum_restart_count": True},
        {"maximum_restart_count": 0},
        {"coarse_status": 0x100002},
        {"control_state": 0x100000},
        {"solve_record": 0x200008},
        {"stream": 0},
    ),
)
def test_invalid_extent_alignment_alias_and_stream_fail_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)

    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as exc_info:
        _launch(kernel, **updates)
    assert exc_info.value.launch_disposition == "not_attempted"
    assert runtime.launches == []
    kernel.close()


def test_rejected_ambiguous_and_base_exception_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [7]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as rejected:
        _launch(kernel)
    assert rejected.value.launch_disposition == "rejected"
    assert not kernel.pending
    assert kernel.lifetime_attempted_launch_count == 1
    assert kernel.lifetime_accepted_launch_count == 0
    kernel.close()

    runtime = _Runtime()
    runtime.launch_statuses = [RuntimeError("native boundary")]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as ambiguous:
        _launch(kernel)
    assert ambiguous.value.launch_disposition == "ambiguous"
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 0
    assert kernel.acknowledge_stream_fence(11) == 0
    kernel.close()

    runtime = _Runtime()
    runtime.launch_statuses = [KeyboardInterrupt("native boundary")]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(KeyboardInterrupt, match="native boundary"):
        _launch(kernel)
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 0
    assert kernel.acknowledge_stream_fence(11) == 0
    kernel.close()


def test_stream_change_binding_mutation_and_unload_outcomes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    _launch(kernel)
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as changed:
        _launch(kernel, stream=12)
    assert changed.value.code == ("hip_rtc_fgmres_coarse_terminal_guard_stream_changed")
    assert kernel.acknowledge_stream_fence(11) == 1
    kernel._function = ctypes.c_void_p()
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as binding:
        _launch(kernel)
    assert binding.value.code == (
        "hip_rtc_fgmres_coarse_terminal_guard_binding_changed"
    )
    kernel._function = ctypes.c_void_p(2)
    runtime.unload_status = 7
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as unload:
        kernel.close()
    assert unload.value.code == ("hip_rtc_fgmres_coarse_terminal_guard_unload_failed")
    assert kernel.unload_disposition == "live"
    runtime.unload_status = 0
    kernel.close()
    assert kernel.closed and runtime.unloads == 2

    runtime = _Runtime()
    runtime.unload_status = RuntimeError("uncertain")
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error) as uncertain:
        kernel.close()
    assert uncertain.value.code == (
        "hip_rtc_fgmres_coarse_terminal_guard_unload_uncertain"
    )
    assert kernel.unload_disposition == "unload_outcome_uncertain"
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error):
        kernel.close()
    assert runtime.unloads == 1


def test_direct_compile_interruption_closes_published_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)

    def interrupted_compile_impl(
        _loaded_runtime: object,
        _architecture: str,
        _hiprtc_library: object,
        *,
        _handoff: object,
    ) -> object:
        _handoff.publish(kernel)  # type: ignore[attr-defined]
        raise KeyboardInterrupt("after publication")

    monkeypatch.setattr(rtc_module, "_compile_impl", interrupted_compile_impl)
    with pytest.raises(KeyboardInterrupt, match="after publication"):
        compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1(
            object(),
            "gfx1030",
        )
    assert kernel.closed
    assert runtime.unloads == 1


@pytest.mark.skipif(not Path("/dev/kfd").exists(), reason="no local AMD KFD device")
def test_actual_local_gfx1030_compile_load_bind_identity_and_close() -> None:
    runtime = load_hip_native_runtime()
    kernel = compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1(
        runtime,
        "gfx1030",
    )
    identity = kernel.identity
    assert identity.schema_version == (
        HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_IDENTITY_SCHEMA_VERSION_V1
    )
    assert identity.architecture == "gfx1030"
    assert identity.symbol == HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1
    assert identity.code_object_byte_length > 0
    assert identity.to_dict()["identity_hash"] == identity.identity_hash
    validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1(identity)
    with pytest.raises(HipRtcFgmresFixedRankCoarseTerminalGuardV1Error):
        validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1(
            replace(identity, compile_options=())
        )
    kernel.close()
    assert kernel.closed


@pytest.mark.skipif(not Path("/dev/kfd").exists(), reason="no local AMD KFD device")
def test_actual_local_guard_publishes_coarse_failure_without_iteration_copy() -> None:
    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    control_offsets = {
        field["name"]: int(field["offset_bytes"]) for field in control_abi["fields"]
    }
    record_offsets = {
        field["name"]: int(field["offset_bytes"])
        for field in record_abi["header_fields"]
    }
    control = np.zeros(int(control_abi["byte_length"]), dtype="u1")
    record = np.zeros(
        int(record_abi["header_bytes"] + record_abi["restart_bytes"]),
        dtype="u1",
    )
    coarse_status = np.array([1 << 1], dtype="<u4")
    struct.pack_into(
        "<i",
        control,
        control_offsets["control_abi_version"],
        2,
    )
    struct.pack_into("<i", control, control_offsets["commit_required"], 1)
    struct.pack_into("<i", control, control_offsets["continuation_required"], 1)
    struct.pack_into(
        "<i",
        record,
        record_offsets["recurrence_abi_version"],
        2,
    )
    struct.pack_into("<i", record, record_offsets["active"], 1)

    loaded = load_hip_native_runtime()
    runtime = _BoundHipContextRuntime(loaded)
    runtime.set_device(0)
    stream = runtime.create_stream()
    pointers: dict[str, object] = {}
    kernel = None
    try:
        for name, host in (
            ("coarse_status", coarse_status),
            ("control_state", control),
            ("solve_record", record),
        ):
            pointers[name] = runtime.malloc(int(host.nbytes))
            runtime.copy_h2d_async(pointers[name], host, stream)
        runtime.synchronize(stream)
        kernel = compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1(
            loaded,
            "gfx1030",
        )
        before = _capture_bound_copy_audit_v1(runtime).snapshot
        kernel.launch_guard(
            stream=stream,
            maximum_restart_count=1,
            **pointers,
        )
        runtime.synchronize(stream)
        assert kernel.acknowledge_stream_fence(stream) == 1
        after = _capture_bound_copy_audit_v1(runtime).snapshot
        assert after.h2d_async.attempt_count == before.h2d_async.attempt_count
        assert after.d2h_async.attempt_count == before.d2h_async.attempt_count
        assert after.d2h_blocking.attempt_count == before.d2h_blocking.attempt_count

        runtime.copy_d2h(control, pointers["control_state"])
        runtime.copy_d2h(record, pointers["solve_record"])
        assert struct.unpack_from("<i", record, record_offsets["active"])[0] == 0
        assert (
            struct.unpack_from("<i", record, record_offsets["terminal_status"])[0] == 6
        )
        assert (
            struct.unpack_from("<i", record, record_offsets["termination_code"])[0]
            == 43
        )
        assert (
            struct.unpack_from("<i", record, record_offsets["device_error_bits"])[0]
            == 4
        )
        assert struct.unpack_from("<i", control, control_offsets["phase"])[0] == 10
        assert (
            struct.unpack_from("<i", control, control_offsets["failure_origin"])[0] == 2
        )
        assert (
            struct.unpack_from("<i", control, control_offsets["commit_required"])[0]
            == 0
        )
        assert (
            struct.unpack_from("<i", control, control_offsets["continuation_required"])[
                0
            ]
            == 0
        )
    finally:
        if kernel is not None:
            if kernel.pending:
                runtime.synchronize(stream)
                kernel.acknowledge_stream_fence(stream)
            kernel.close()
        for pointer in reversed(tuple(pointers.values())):
            runtime.free(pointer)
        runtime.destroy_stream(stream)
