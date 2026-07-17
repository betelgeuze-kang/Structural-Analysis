from __future__ import annotations

import ctypes
from dataclasses import replace
from pathlib import Path
import sys
import threading

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_slot_rtc_v1 as rtc_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_plan_v1 import (  # noqa: E402
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_rtc_v1 import (  # noqa: E402
    HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_ABI_VERSION_V1,
    HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_IDENTITY_SCHEMA_VERSION_V1,
    HipRtcFgmresFixedRankCoarseSlotKernelV1,
    HipRtcFgmresFixedRankCoarseSlotV1Error,
    _KERNEL_MINT,
    compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1,
    validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    load_hip_native_runtime,
)


class _Runtime:
    def __init__(self) -> None:
        self.launch_statuses: list[int | BaseException] = []
        self.launches: list[dict[str, object]] = []
        self.unload_status: int | BaseException = 0
        self.unloads = 0

    def launch(self, function: object, **keywords: object) -> int:
        self.launches.append({"function": function, **keywords})
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
) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
    monkeypatch.setattr(
        rtc_module,
        "validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1",
        lambda identity: identity,
    )
    functions = {
        symbol: ctypes.c_void_p(index + 2)
        for index, symbol in enumerate(
            HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1
        )
    }
    return HipRtcFgmresFixedRankCoarseSlotKernelV1(
        runtime=runtime or _Runtime(),  # type: ignore[arg-type]
        module=ctypes.c_void_p(1),
        functions=functions,
        identity=None,  # type: ignore[arg-type]
        _mint=_KERNEL_MINT,
    )


def _launch(
    kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1,
    **updates: object,
) -> int:
    values: dict[str, object] = {
        "stream": 11,
        "expected_schedule_epoch": 7,
        "expected_restart": 1,
        "expected_column": 1,
        "maximum_restart_count": 4,
        "free_dof_count": 513,
        "retained_rank": 2,
        "restart_dimension": 4,
        "logical_index": 1,
        "jacobi_inverse": 0x100000,
        "basis_v": 0x200000,
        "preconditioned_basis_z": 0x300000,
        "coarse_physical_basis_z": 0x400000,
        "coarse_operator_basis_az": 0x500000,
        "coarse_cholesky_l": 0x600000,
        "coarse_rhs": 0x700000,
        "coarse_coefficients": 0x800000,
        "coarse_status": 0x900000,
        "control_state": 0xA00000,
        "solve_record": 0xB00000,
    }
    values.update(updates)
    return kernel.launch_slot(**values)  # type: ignore[arg-type]


def test_slot_enqueues_exact_four_geometries_and_requires_matching_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)

    assert _launch(kernel) == 4
    assert tuple((row["grid_x"], row["block_x"]) for row in runtime.launches) == (
        (1, 1),
        (2, 256),
        (1, 1),
        (3, 256),
    )
    assert tuple(row["function"].value for row in runtime.launches) == (2, 3, 4, 5)  # type: ignore[union-attr]
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 4
    assert kernel.lifetime_attempted_launch_count == 4
    assert kernel.lifetime_accepted_launch_count == 4
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as close_error:
        kernel.close()
    assert close_error.value.code == "hip_rtc_fgmres_coarse_slot_pending_work"
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as wrong_fence:
        kernel.acknowledge_stream_fence(12)
    assert wrong_fence.value.code == "hip_rtc_fgmres_coarse_slot_fence_stream_invalid"
    assert kernel.acknowledge_stream_fence(11) == 4
    kernel.close()
    assert kernel.closed
    assert kernel.unload_disposition == "terminal"
    assert runtime.unloads == 1


@pytest.mark.parametrize(
    ("updates", "expected_code"),
    (
        (
            {"coarse_rhs": 0x800000},
            "hip_rtc_fgmres_coarse_slot_pointer_contract_invalid",
        ),
        (
            {"basis_v": 0x100008},
            "hip_rtc_fgmres_coarse_slot_pointer_contract_invalid",
        ),
        (
            {"jacobi_inverse": 0x100004},
            "hip_rtc_fgmres_coarse_slot_pointer_contract_invalid",
        ),
        (
            {"expected_schedule_epoch": True},
            "hip_rtc_fgmres_coarse_slot_launch_contract_invalid",
        ),
        (
            {"expected_column": 2},
            "hip_rtc_fgmres_coarse_slot_coordinate_invalid",
        ),
        (
            {"expected_restart": 5},
            "hip_rtc_fgmres_coarse_slot_coordinate_invalid",
        ),
    ),
)
def test_alias_alignment_and_coordinate_fail_before_native_launch(
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
    expected_code: str,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)

    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as exc_info:
        _launch(kernel, **updates)
    assert exc_info.value.code == expected_code
    assert exc_info.value.launch_disposition == "not_attempted"
    assert runtime.launches == []
    kernel.close()


@pytest.mark.parametrize("failure_index", (0, 1, 2, 3))
def test_rejected_launch_keeps_exact_partial_acceptance_until_fence(
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [0] * failure_index + [7]
    kernel = _kernel(monkeypatch, runtime)

    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as exc_info:
        _launch(kernel)
    error = exc_info.value
    assert error.code == "hip_rtc_fgmres_coarse_slot_kernel_launch_failed"
    assert error.launch_disposition == "rejected"
    assert error.attempted_launch_count == failure_index + 1
    assert error.accepted_launch_count == failure_index
    assert kernel.pending == (failure_index > 0)
    assert kernel.pending_accepted_launch_count == failure_index
    if failure_index:
        assert kernel.acknowledge_stream_fence(11) == failure_index
    kernel.close()


def test_ambiguous_exception_and_base_exception_prearm_stream_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [0, RuntimeError("native boundary")]
    kernel = _kernel(monkeypatch, runtime)

    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as ambiguous:
        _launch(kernel)
    assert ambiguous.value.launch_disposition == "ambiguous"
    assert ambiguous.value.attempted_launch_count == 2
    assert ambiguous.value.accepted_launch_count == 1
    assert kernel.pending
    assert kernel.acknowledge_stream_fence(11) == 1
    kernel.close()

    runtime = _Runtime()
    runtime.launch_statuses = [KeyboardInterrupt("native boundary")]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(KeyboardInterrupt, match="native boundary"):
        _launch(kernel)
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 0
    assert kernel.lifetime_attempted_launch_count == 1
    assert kernel.acknowledge_stream_fence(11) == 0
    kernel.close()


def test_stream_change_and_binding_mutation_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    assert _launch(kernel) == 4

    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as stream_error:
        _launch(kernel, stream=12)
    assert stream_error.value.code == "hip_rtc_fgmres_coarse_slot_stream_changed"
    assert len(runtime.launches) == 4
    assert kernel.acknowledge_stream_fence(11) == 4

    first_symbol = HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1[0]
    kernel._functions[first_symbol] = ctypes.c_void_p()
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as binding_error:
        _launch(kernel)
    assert binding_error.value.code == "hip_rtc_fgmres_coarse_slot_binding_changed"
    assert len(runtime.launches) == 4
    kernel.close()


def test_unload_rejection_retries_but_exception_is_terminally_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.unload_status = 7
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as rejected:
        kernel.close()
    assert rejected.value.code == "hip_rtc_fgmres_coarse_slot_module_unload_failed"
    assert kernel.unload_disposition == "live"
    runtime.unload_status = 0
    kernel.close()
    assert kernel.closed and runtime.unloads == 2

    runtime = _Runtime()
    runtime.unload_status = RuntimeError("native unload boundary")
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as uncertain:
        kernel.close()
    assert uncertain.value.code == "hip_rtc_fgmres_coarse_slot_module_unload_uncertain"
    assert kernel.unload_disposition == "unload_outcome_uncertain"
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as retry:
        kernel.close()
    assert retry.value.code == "hip_rtc_fgmres_coarse_slot_module_unload_uncertain"
    assert runtime.unloads == 1


def test_compile_handoffs_cover_return_boundary_and_direct_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)

    def fake_compile_impl(
        _loaded_runtime: object,
        _architecture: str,
        _hiprtc_library: object,
        *,
        _handoff: object,
    ) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
        _handoff.publish(kernel)  # type: ignore[attr-defined]
        return kernel

    monkeypatch.setattr(rtc_module, "_compile_impl", fake_compile_impl)
    handoff = rtc_module._HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1()

    def interrupted_compiler(*args: object) -> object:
        compiled = compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1(*args)
        assert compiled is kernel
        raise KeyboardInterrupt("after compiler return")

    with pytest.raises(KeyboardInterrupt, match="after compiler return"):
        rtc_module._compile_fixed_rank_coarse_slot_with_handoff_v1(
            interrupted_compiler,
            handoff,
            object(),
            "gfx1030",
            None,
        )
    assert handoff.kernel is kernel
    assert not kernel.closed and runtime.unloads == 0
    kernel.close()

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
        raise KeyboardInterrupt("after kernel publication")

    monkeypatch.setattr(rtc_module, "_compile_impl", interrupted_compile_impl)
    with pytest.raises(KeyboardInterrupt, match="after kernel publication"):
        compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1(
            object(),
            "gfx1030",
        )
    assert kernel.closed and runtime.unloads == 1


def test_native_callback_reentry_fails_without_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ReentrantRuntime(_Runtime):
        def __init__(self) -> None:
            super().__init__()
            self.kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1 | None = None
            self.reentrant_error: HipRtcFgmresFixedRankCoarseSlotV1Error | None = None

        def launch(self, function: object, **keywords: object) -> int:
            if self.reentrant_error is None:
                assert self.kernel is not None
                try:
                    self.kernel.close()
                except HipRtcFgmresFixedRankCoarseSlotV1Error as exc:
                    self.reentrant_error = exc
            return super().launch(function, **keywords)

    runtime = _ReentrantRuntime()
    kernel = _kernel(monkeypatch, runtime)
    runtime.kernel = kernel
    assert _launch(kernel) == 4
    assert runtime.reentrant_error is not None
    assert (
        runtime.reentrant_error.code == "hip_rtc_fgmres_coarse_slot_reentrant_operation"
    )
    assert kernel.acknowledge_stream_fence(11) == 4
    kernel.close()


def test_concurrent_same_stream_slots_are_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BlockingRuntime(_Runtime):
        def __init__(self) -> None:
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()
            self.second_native_call = threading.Event()
            self._call_count = 0
            self._call_count_lock = threading.Lock()

        def launch(self, function: object, **keywords: object) -> int:
            with self._call_count_lock:
                ordinal = self._call_count
                self._call_count += 1
            if ordinal == 0:
                self.entered.set()
                assert self.release.wait(timeout=5.0)
            else:
                self.second_native_call.set()
            return super().launch(function, **keywords)

    runtime = _BlockingRuntime()
    kernel = _kernel(monkeypatch, runtime)
    second_attempted = threading.Event()
    results: list[int] = []
    errors: list[BaseException] = []

    def invoke(*, second: bool) -> None:
        if second:
            second_attempted.set()
        try:
            results.append(_launch(kernel))
        except BaseException as exc:  # pragma: no cover - assertion captures details
            errors.append(exc)

    first = threading.Thread(target=invoke, kwargs={"second": False})
    second = threading.Thread(target=invoke, kwargs={"second": True})
    first.start()
    assert runtime.entered.wait(timeout=5.0)
    second.start()
    assert second_attempted.wait(timeout=5.0)
    assert not runtime.second_native_call.wait(timeout=0.1)
    runtime.release.set()
    first.join(timeout=5.0)
    second.join(timeout=5.0)
    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert sorted(results) == [4, 4]
    assert len(runtime.launches) == 8
    assert kernel.acknowledge_stream_fence(11) == 8
    kernel.close()


@pytest.mark.skipif(not Path("/dev/kfd").exists(), reason="no local AMD KFD device")
def test_actual_local_gfx1030_compile_load_bind_identity_and_close() -> None:
    runtime = load_hip_native_runtime()
    kernel = compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1(
        runtime,
        "gfx1030",
    )
    identity = kernel.identity
    assert (
        identity.schema_version
        == HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_IDENTITY_SCHEMA_VERSION_V1
    )
    assert identity.abi_version == HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_ABI_VERSION_V1
    assert identity.architecture == "gfx1030"
    assert (
        identity.kernel_symbols == HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1
    )
    assert identity.code_object_byte_length > 0
    assert identity.to_dict()["identity_hash"] == identity.identity_hash
    validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(identity)
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error):
        validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(
            replace(identity, compile_options=())
        )
    kernel.close()
    assert kernel.closed
