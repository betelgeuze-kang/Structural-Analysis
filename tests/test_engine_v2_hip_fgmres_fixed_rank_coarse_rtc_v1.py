from __future__ import annotations

import ctypes
from dataclasses import replace
from pathlib import Path
import sys
import threading

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_rtc_v1 as rtc_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_plan_v1 import (  # noqa: E402
    HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_rtc_v1 import (  # noqa: E402
    HIP_RTC_FGMRES_FIXED_RANK_COARSE_ABI_VERSION_V1,
    HIP_RTC_FGMRES_FIXED_RANK_COARSE_IDENTITY_SCHEMA_VERSION_V1,
    HipRtcFgmresFixedRankCoarseKernelV1,
    HipRtcFgmresFixedRankCoarseV1Error,
    _KERNEL_MINT,
    _fixed_source,
    compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1,
    validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    load_hip_native_runtime,
)
from structural_analysis.engine_v2.backends.hip.context import (  # noqa: E402
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip.transfer_audit_v1 import (  # noqa: E402
    _capture_bound_copy_audit_v1,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.operators.sparse_linear_static import (  # noqa: E402
    solve_sparse_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (  # noqa: E402
    apply_cpu_fgmres_fixed_rank_coarse_v1,
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

KERNEL = Path(
    "src/structural_analysis/engine_v2/assembly_backend/kernels/"
    "engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp"
)
FIXTURE = Path("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")


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


def _kernel(monkeypatch: pytest.MonkeyPatch, runtime: _Runtime | None = None):
    monkeypatch.setattr(
        rtc_module,
        "validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1",
        lambda identity: identity,
    )
    functions = {
        symbol: ctypes.c_void_p(index + 2)
        for index, symbol in enumerate(HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1)
    }
    return HipRtcFgmresFixedRankCoarseKernelV1(
        runtime=runtime or _Runtime(),  # type: ignore[arg-type]
        module=ctypes.c_void_p(1),
        functions=functions,
        identity=None,  # type: ignore[arg-type]
        _mint=_KERNEL_MINT,
    )


def _launch(kernel: HipRtcFgmresFixedRankCoarseKernelV1, **updates: object) -> int:
    values: dict[str, object] = {
        "stream": 11,
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
    }
    values.update(updates)
    return kernel.launch_application(**values)  # type: ignore[arg-type]


def test_fixed_source_contains_exact_four_symbols_and_no_runtime_calls() -> None:
    source = _fixed_source()
    assert source == KERNEL.read_bytes()
    for symbol in HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1:
        assert source.count(symbol.encode()) == 1
    for forbidden in (b"hipMalloc", b"hipMemcpy", b"hipStreamSynchronize"):
        assert forbidden not in source
    assert b"__shared__ unsigned int shared_gate;" in source
    assert b"shared_gate = *coarse_status;" in source
    assert b"if (shared_gate != 0u)" in source
    assert b"static_cast<unsigned int>(free_dof_count)" in source


def test_kernel_enqueues_exact_four_geometries_and_requires_fence(
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
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 4
    assert kernel.lifetime_attempted_launch_count == 4
    assert kernel.lifetime_accepted_launch_count == 4
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as exc_info:
        kernel.close()
    assert exc_info.value.code == "hip_rtc_fgmres_coarse_pending_work"
    assert kernel.acknowledge_stream_fence(11) == 4
    assert not kernel.pending
    kernel.close()
    assert runtime.unloads == 1
    assert kernel.closed


def test_alias_and_invalid_geometry_reject_before_native_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as alias:
        _launch(kernel, coarse_rhs=0x800000)
    assert alias.value.code == "hip_rtc_fgmres_coarse_alias_invalid"
    assert alias.value.launch_disposition == "not_attempted"
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as boolean:
        _launch(kernel, retained_rank=True)
    assert boolean.value.code == "hip_rtc_fgmres_coarse_launch_contract_invalid"
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error):
        _launch(kernel, logical_index=4)
    assert runtime.launches == []
    kernel.close()


@pytest.mark.parametrize(
    ("updates", "expected_code"),
    (
        ({"basis_v": 0x100008}, "hip_rtc_fgmres_coarse_alias_invalid"),
        (
            {"jacobi_inverse": 0x100004},
            "hip_rtc_fgmres_coarse_launch_contract_invalid",
        ),
        (
            {"jacobi_inverse": rtc_module._UINTPTR_MAX - 7},
            "hip_rtc_fgmres_coarse_launch_contract_invalid",
        ),
    ),
)
def test_interior_overlap_alignment_and_uintptr_overflow_fail_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
    expected_code: str,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as exc_info:
        _launch(kernel, **updates)
    assert exc_info.value.code == expected_code
    assert exc_info.value.launch_disposition == "not_attempted"
    assert runtime.launches == []
    kernel.close()


@pytest.mark.parametrize("failure_index", (0, 1, 2, 3))
def test_rejected_launch_preserves_exact_partial_acceptance_until_fence(
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [0] * failure_index + [7]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as exc_info:
        _launch(kernel)
    error = exc_info.value
    assert error.code == "hip_rtc_fgmres_coarse_kernel_launch_failed"
    assert error.launch_disposition == "rejected"
    assert error.attempted_launch_count == failure_index + 1
    assert error.accepted_launch_count == failure_index
    assert kernel.pending == (failure_index > 0)
    assert kernel.pending_accepted_launch_count == failure_index
    if failure_index:
        assert kernel.acknowledge_stream_fence(11) == failure_index
    kernel.close()


def test_ambiguous_native_exception_poison_requires_matching_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [0, RuntimeError("native boundary")]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as exc_info:
        _launch(kernel)
    assert exc_info.value.launch_disposition == "ambiguous"
    assert exc_info.value.attempted_launch_count == 2
    assert exc_info.value.accepted_launch_count == 1
    assert kernel.pending
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as wrong_fence:
        kernel.acknowledge_stream_fence(12)
    assert wrong_fence.value.code == "hip_rtc_fgmres_coarse_fence_stream_invalid"
    assert kernel.acknowledge_stream_fence(11) == 1
    kernel.close()


def test_base_exception_prearms_uncertain_work_until_matching_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [KeyboardInterrupt()]
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(KeyboardInterrupt):
        _launch(kernel)
    assert kernel.pending
    assert kernel.pending_accepted_launch_count == 0
    assert kernel.lifetime_attempted_launch_count == 1
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as close_error:
        kernel.close()
    assert close_error.value.code == "hip_rtc_fgmres_coarse_pending_work"
    assert kernel.acknowledge_stream_fence(11) == 0
    kernel.close()


def test_unload_exception_is_uncertain_and_never_double_unloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.unload_status = RuntimeError("native unload boundary")
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as first:
        kernel.close()
    assert first.value.code == "hip_rtc_fgmres_coarse_module_unload_uncertain"
    assert kernel.unload_disposition == "unload_outcome_uncertain"
    assert runtime.unloads == 1
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as retry:
        kernel.close()
    assert retry.value.code == "hip_rtc_fgmres_coarse_module_unload_uncertain"
    assert runtime.unloads == 1


def test_rejected_unload_remains_safely_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    runtime.unload_status = 7
    kernel = _kernel(monkeypatch, runtime)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as rejected:
        kernel.close()
    assert rejected.value.code == "hip_rtc_fgmres_coarse_module_unload_failed"
    assert kernel.unload_disposition == "live"
    runtime.unload_status = 0
    kernel.close()
    assert runtime.unloads == 2
    assert kernel.closed
    assert kernel.unload_disposition == "terminal"


def test_stream_change_and_binding_mutation_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    _launch(kernel)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as stream_error:
        _launch(kernel, stream=12)
    assert stream_error.value.code == "hip_rtc_fgmres_coarse_stream_changed"
    assert len(runtime.launches) == 4
    kernel.acknowledge_stream_fence(11)
    kernel._functions[HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1[0]] = (
        ctypes.c_void_p()
    )
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error) as binding_error:
        _launch(kernel)
    assert binding_error.value.code == "hip_rtc_fgmres_coarse_binding_changed"
    kernel.close()


def test_concurrent_same_stream_applications_are_serialized(
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
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert results == [4, 4]
    assert len(runtime.launches) == 8
    assert kernel.acknowledge_stream_fence(11) == 8
    kernel.close()


def test_native_callback_reentrant_module_operation_fails_without_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ReentrantRuntime(_Runtime):
        def __init__(self) -> None:
            super().__init__()
            self.kernel: HipRtcFgmresFixedRankCoarseKernelV1 | None = None
            self.reentrant_error: HipRtcFgmresFixedRankCoarseV1Error | None = None

        def launch(self, function: object, **keywords: object) -> int:
            if self.reentrant_error is None:
                assert self.kernel is not None
                try:
                    self.kernel.close()
                except HipRtcFgmresFixedRankCoarseV1Error as exc:
                    self.reentrant_error = exc
            return super().launch(function, **keywords)

    runtime = _ReentrantRuntime()
    kernel = _kernel(monkeypatch, runtime)
    runtime.kernel = kernel
    assert _launch(kernel) == 4
    assert runtime.reentrant_error is not None
    assert runtime.reentrant_error.code == "hip_rtc_fgmres_coarse_reentrant_operation"
    assert runtime.reentrant_error.launch_disposition == "not_attempted"
    assert kernel.acknowledge_stream_fence(11) == 4
    kernel.close()


@pytest.mark.skipif(not Path("/dev/kfd").exists(), reason="no local AMD KFD device")
def test_actual_local_gfx1030_compile_load_bind_identity_and_close() -> None:
    runtime = load_hip_native_runtime()
    kernel = compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1(runtime, "gfx1030")
    identity = kernel.identity
    assert (
        identity.schema_version
        == HIP_RTC_FGMRES_FIXED_RANK_COARSE_IDENTITY_SCHEMA_VERSION_V1
    )
    assert identity.abi_version == HIP_RTC_FGMRES_FIXED_RANK_COARSE_ABI_VERSION_V1
    assert identity.architecture == "gfx1030"
    assert identity.kernel_symbols == HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1
    assert identity.code_object_byte_length > 0
    assert identity.to_dict()["identity_hash"] == identity.identity_hash
    validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(identity)
    with pytest.raises(HipRtcFgmresFixedRankCoarseV1Error):
        validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(
            replace(identity, code_object_byte_length=True)
        )
    kernel.close()
    assert kernel.closed


@pytest.mark.skipif(not Path("/dev/kfd").exists(), reason="no local AMD KFD device")
def test_actual_local_gfx1030_four_launch_application_matches_cpu_exactly() -> None:
    model = load_model_ir_v2(FIXTURE)
    buffers = pack_solver_model_buffers(model, load_pattern_id="LC_WEAK")
    execution = compile_execution_plan_v2(buffers)
    free = execution.array("free_dofs")
    direct = solve_sparse_execution_plan_v2(execution)
    mode = immutable_array(
        direct.displacements_si.reshape(-1)[free],
        dtype="<f8",
    )
    axis = np.zeros_like(mode)
    axis[0] = 1.0
    coarse = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        execution,
        np.column_stack((mode, axis)),
        rank_cap=2,
    )
    f = coarse.free_dof_count
    k = coarse.retained_rank
    m = 4
    logical_index = 1
    residual = np.ascontiguousarray(np.linspace(-0.75, 1.25, f), dtype="<f8")
    expected = apply_cpu_fgmres_fixed_rank_coarse_v1(coarse, residual)
    basis_v = np.zeros((m + 1, f), dtype="<f8")
    basis_v[logical_index] = residual
    basis_z = np.zeros((m, f), dtype="<f8")
    host_arrays = {
        "jacobi_inverse": np.ascontiguousarray(
            coarse.inverse_sqrt_diagonal**2,
            dtype="<f8",
        ),
        "basis_v": basis_v,
        "preconditioned_basis_z": basis_z,
        "coarse_physical_basis_z": coarse.physical_basis_z,
        "coarse_operator_basis_az": coarse.operator_basis_az,
        "coarse_cholesky_l": coarse.coarse_cholesky_l,
        "coarse_rhs": np.zeros(k, dtype="<f8"),
        "coarse_coefficients": np.zeros(k, dtype="<f8"),
        "coarse_status": np.zeros(1, dtype="<u4"),
    }
    loaded = load_hip_native_runtime()
    runtime = _BoundHipContextRuntime(loaded)
    runtime.set_device(0)
    stream = runtime.create_stream()
    pointers: dict[str, object] = {}
    kernel = None
    try:
        for name, array in host_arrays.items():
            pointers[name] = runtime.malloc(int(array.nbytes))
        upload_names = (
            "jacobi_inverse",
            "basis_v",
            "coarse_physical_basis_z",
            "coarse_operator_basis_az",
            "coarse_cholesky_l",
        )
        for name in upload_names:
            runtime.copy_h2d_async(pointers[name], host_arrays[name], stream)
        runtime.synchronize(stream)
        before_application = _capture_bound_copy_audit_v1(runtime).snapshot
        kernel = compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1(
            loaded,
            "gfx1030",
        )
        accepted = kernel.launch_application(
            stream=stream,
            free_dof_count=f,
            retained_rank=k,
            restart_dimension=m,
            logical_index=logical_index,
            **pointers,
        )
        runtime.synchronize(stream)
        assert kernel.acknowledge_stream_fence(stream) == 4
        after_application = _capture_bound_copy_audit_v1(runtime).snapshot
        assert accepted == 4
        assert (
            after_application.h2d_async.attempt_count
            - before_application.h2d_async.attempt_count
            == 0
        )
        assert (
            after_application.d2h_async.attempt_count
            - before_application.d2h_async.attempt_count
            == 0
        )
        assert (
            after_application.d2h_blocking.attempt_count
            - before_application.d2h_blocking.attempt_count
            == 0
        )
        runtime.copy_d2h(
            basis_z,
            pointers["preconditioned_basis_z"],
        )
        runtime.copy_d2h(
            host_arrays["coarse_status"],
            pointers["coarse_status"],
        )
        assert int(host_arrays["coarse_status"][0]) == 0
        np.testing.assert_array_equal(basis_z[logical_index], expected)
    finally:
        if kernel is not None:
            if kernel.pending:
                runtime.synchronize(stream)
                kernel.acknowledge_stream_fence(stream)
            kernel.close()
        for pointer in reversed(tuple(pointers.values())):
            runtime.free(pointer)
        runtime.destroy_stream(stream)
