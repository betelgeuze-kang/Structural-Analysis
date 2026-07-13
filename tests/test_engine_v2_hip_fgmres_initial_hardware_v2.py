from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from typing import Any, NoReturn

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (  # noqa: E402
    HipRtcFgmresV2Error,
    compile_hip_rtc_fgmres_v2_kernel,
    first_column_candidate_preparation_launches_v2,
    first_column_candidate_residual_launches_v2,
    first_column_candidate_scale_metrics_launches_v2,
    first_column_checkpoint_transaction_launches_v2,
    first_column_completion_launches_v2,
    first_column_predecessor_validation_launch_v2,
    first_column_reduction_launches_v2,
    initial_reduction_launches_v2,
    reduction_stage_output_counts_v2,
    solve_record_byte_length_v2,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    HipNativeRuntimeError,
    load_hip_native_runtime,
    probe_hip_capability,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (  # noqa: E402
    prepare_fgmres_gpu_tree_first_column_candidate_residual_v2,
    prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2,
    prepare_fgmres_gpu_tree_first_column_candidate_v2,
    prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2,
    replay_fgmres_gpu_tree_first_arnoldi_column_v2,
    replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2,
    replay_fgmres_gpu_tree_initial_v2,
)


_ARCH_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")
_HIP_MEMCPY_HOST_TO_DEVICE = 1
_HIP_MEMCPY_DEVICE_TO_HOST = 2
_TOOLCHAIN_UNAVAILABLE_CODES = frozenset(
    {
        "hip_rtc_library_not_found",
        "hip_rtc_library_load_failed",
    }
)


def _local_architectures() -> tuple[str, ...]:
    executable = shutil.which("rocm_agent_enumerator")
    if executable is None:
        for candidate in (
            Path("/opt/rocm/bin/rocm_agent_enumerator"),
            Path("/opt/rocm-6.0.2/bin/rocm_agent_enumerator"),
        ):
            if candidate.is_file() and candidate.stat().st_mode & 0o111:
                executable = str(candidate)
                break
    if executable is None:
        return ()
    try:
        completed = subprocess.run(
            [executable],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode != 0:
        return ()
    return tuple(
        target
        for target in (token.strip().lower() for token in completed.stdout.split())
        if target != "gfx000" and _ARCH_PATTERN.fullmatch(target)
    )


def _skip(message: str) -> NoReturn:
    pytest.skip(f"{message} No CPU fallback was used.")


def _bind(runtime: Any, symbol: str, argtypes: list[Any]) -> Any:
    return runtime.bind(symbol, argtypes, ctypes.c_int)


def _require_hip_success(runtime: Any, status: int, operation: str) -> None:
    assert status == 0, f"{operation} failed: {runtime.hip_error_string(status)}"


def _field_offsets(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row["name"]): int(row["offset_bytes"]) for row in rows}


def _i32(payload: bytes, offsets: dict[str, int], name: str) -> int:
    return int(struct.unpack_from("<i", payload, offsets[name])[0])


def _f64(payload: bytes, offsets: dict[str, int], name: str) -> float:
    return float(struct.unpack_from("<d", payload, offsets[name])[0])


def _store_i32(
    payload: np.ndarray,
    offsets: dict[str, int],
    name: str,
    value: int,
) -> None:
    struct.pack_into("<i", payload, offsets[name], value)


def _store_f64(
    payload: np.ndarray,
    offsets: dict[str, int],
    name: str,
    value: float,
) -> None:
    struct.pack_into("<d", payload, offsets[name], value)


def _assert_close(actual: float, expected: float) -> None:
    np.testing.assert_allclose(actual, expected, rtol=2.0e-15, atol=0.0)


@dataclass(frozen=True, slots=True)
class _NativeHipApi:
    runtime: Any
    hip_malloc: Any
    hip_free: Any
    hip_memcpy_async: Any
    stream_create: Any
    stream_synchronize: Any
    stream_destroy: Any


@dataclass(slots=True)
class _NativeExecution:
    api: _NativeHipApi
    kernel: Any
    stream: ctypes.c_void_p = field(default_factory=ctypes.c_void_p)
    allocations: list[ctypes.c_void_p] = field(default_factory=list)
    fence_observed: bool = False
    completion_acknowledged: bool = False

    def open_stream(self) -> None:
        _require_hip_success(
            self.api.runtime,
            int(self.api.stream_create(ctypes.byref(self.stream))),
            "hipStreamCreate",
        )
        assert self.stream.value is not None

    def allocate_and_upload(
        self,
        name: str,
        host: np.ndarray,
    ) -> ctypes.c_void_p:
        pointer = ctypes.c_void_p()
        _require_hip_success(
            self.api.runtime,
            int(self.api.hip_malloc(ctypes.byref(pointer), host.nbytes)),
            f"hipMalloc({name})",
        )
        assert pointer.value is not None
        self.allocations.append(pointer)
        _require_hip_success(
            self.api.runtime,
            int(
                self.api.hip_memcpy_async(
                    pointer,
                    ctypes.c_void_p(host.ctypes.data),
                    host.nbytes,
                    _HIP_MEMCPY_HOST_TO_DEVICE,
                    self.stream,
                )
            ),
            f"hipMemcpyAsync(H2D {name})",
        )
        return pointer

    def enqueue_download(
        self,
        name: str,
        device_pointer: ctypes.c_void_p,
        host: np.ndarray,
    ) -> None:
        _require_hip_success(
            self.api.runtime,
            int(
                self.api.hip_memcpy_async(
                    ctypes.c_void_p(host.ctypes.data),
                    device_pointer,
                    host.nbytes,
                    _HIP_MEMCPY_DEVICE_TO_HOST,
                    self.stream,
                )
            ),
            f"hipMemcpyAsync(D2H {name})",
        )

    def observe_fence_and_acknowledge(self) -> None:
        _require_hip_success(
            self.api.runtime,
            int(self.api.stream_synchronize(self.stream)),
            "hipStreamSynchronize(result fence)",
        )
        self.fence_observed = True
        self.kernel.acknowledge_stream_completion(self.stream)
        self.completion_acknowledged = True

    def close(self) -> None:
        cleanup_errors: list[str] = []
        runtime = self.api.runtime
        if self.kernel.pending_stream_count:
            if self.stream.value is not None and not self.fence_observed:
                status = int(self.api.stream_synchronize(self.stream))
                if status == 0:
                    self.fence_observed = True
                else:
                    cleanup_errors.append(
                        "hipStreamSynchronize(cleanup fence): "
                        f"{runtime.hip_error_string(status)}"
                    )
            if self.fence_observed and not self.completion_acknowledged:
                try:
                    self.kernel.acknowledge_stream_completion(self.stream)
                    self.completion_acknowledged = True
                except Exception as exc:
                    cleanup_errors.append(
                        f"acknowledge_stream_completion: {type(exc).__name__}: {exc}"
                    )
        for pointer in reversed(self.allocations):
            status = int(self.api.hip_free(pointer))
            if status != 0:
                cleanup_errors.append(f"hipFree: {runtime.hip_error_string(status)}")
        if self.stream.value is not None:
            status = int(self.api.stream_destroy(self.stream))
            if status != 0:
                cleanup_errors.append(
                    f"hipStreamDestroy: {runtime.hip_error_string(status)}"
                )
        try:
            self.kernel.close()
        except Exception as exc:
            cleanup_errors.append(f"kernel.close: {type(exc).__name__}: {exc}")
        if cleanup_errors:
            pytest.fail(
                "Native FGMRES v2 cleanup failed: " + "; ".join(cleanup_errors),
                pytrace=False,
            )


def _open_native_execution() -> _NativeExecution:
    architectures = _local_architectures()
    if not architectures or architectures[0] != "gfx1030":
        _skip("The primary real HIP agent is not gfx1030.")

    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert capability.fallback_used is False
        _skip(f"Native HIP device 0 is unavailable: {capability.status_code}.")

    try:
        runtime = load_hip_native_runtime()
        hip_set_device = _bind(runtime, "hipSetDevice", [ctypes.c_int])
        hip_malloc = _bind(
            runtime,
            "hipMalloc",
            [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t],
        )
        hip_free = _bind(runtime, "hipFree", [ctypes.c_void_p])
        hip_memcpy_async = _bind(
            runtime,
            "hipMemcpyAsync",
            [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_int,
                ctypes.c_void_p,
            ],
        )
        stream_create = _bind(
            runtime,
            "hipStreamCreate",
            [ctypes.POINTER(ctypes.c_void_p)],
        )
        stream_synchronize = _bind(
            runtime,
            "hipStreamSynchronize",
            [ctypes.c_void_p],
        )
        stream_destroy = _bind(
            runtime,
            "hipStreamDestroy",
            [ctypes.c_void_p],
        )
    except HipNativeRuntimeError as exc:
        _skip(f"The native HIP execution surface is unavailable: {exc.code}.")

    set_device_status = int(hip_set_device(0))
    if set_device_status != 0:
        _skip(
            "HIP device 0 could not be selected: "
            f"{runtime.hip_error_string(set_device_status)}."
        )

    try:
        kernel = compile_hip_rtc_fgmres_v2_kernel(runtime, "gfx1030")
    except HipRtcFgmresV2Error as exc:
        if exc.code in _TOOLCHAIN_UNAVAILABLE_CODES:
            _skip(f"The native HIPRTC toolchain is unavailable: {exc.code}.")
        raise

    return _NativeExecution(
        api=_NativeHipApi(
            runtime=runtime,
            hip_malloc=hip_malloc,
            hip_free=hip_free,
            hip_memcpy_async=hip_memcpy_async,
            stream_create=stream_create,
            stream_synchronize=stream_synchronize,
            stream_destroy=stream_destroy,
        ),
        kernel=kernel,
    )


def test_native_gfx1030_fgmres_v2_initial_schedule_matches_gpu_tree_oracle() -> None:
    execution = _open_native_execution()
    kernel = execution.kernel

    free_dof_count = 513
    restart_dimension = 4
    max_iterations = 0
    maximum_restart_count = 0
    absolute_tolerance = 0.0
    relative_tolerance = 1.0e-12
    authoritative_tolerance = 1.0e-12
    stagnation_relative_tolerance = 1.0e-8
    divergence_factor = 1.0e8

    indices = np.arange(free_dof_count, dtype="<i4")
    row_ptr = np.arange(free_dof_count + 1, dtype="<i4")
    column_indices = indices.copy()
    values = np.ascontiguousarray(
        1.0 + (indices.astype("<f8") % 5.0) * 0.25,
        dtype="<f8",
    )
    initial_solution = np.ascontiguousarray(
        ((indices.astype("<f8") % 7.0) - 3.0) * 0.125,
        dtype="<f8",
    )
    rhs = np.ascontiguousarray(
        ((indices.astype("<f8") % 11.0) - 5.0) * 0.5 + 0.25,
        dtype="<f8",
    )
    oracle = replay_fgmres_gpu_tree_initial_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        rhs=rhs,
        initial_solution=initial_solution,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        authoritative_tolerance=authoritative_tolerance,
        max_iterations=max_iterations,
    )
    assert oracle.terminal_status == "max_iterations"
    assert oracle.termination_code == "max_iterations_exhausted"
    assert reduction_stage_output_counts_v2(free_dof_count) == (2, 1)

    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    control_modes = control_abi["control_mode_codes"]
    vector_modes = control_abi["vector_mode_codes"]
    vector_gates = control_abi["vector_gate_codes"]
    spmv_modes = control_abi["spmv_mode_codes"]
    reduction_rows = initial_reduction_launches_v2(free_dof_count)
    stage_count = len(oracle.rhs_l2.stage_output_counts)
    assert len(reduction_rows) == 4 * stage_count == 8
    assert [row.expected_reduction_epoch for row in reduction_rows] == list(range(8))

    record_bytes = solve_record_byte_length_v2(maximum_restart_count)
    host_inputs: dict[str, np.ndarray] = {
        "row_ptr": row_ptr,
        "column_indices": column_indices,
        "values": values,
        "reduced_state": initial_solution,
        "reduced_load": rhs,
        "inverse_diagonal": np.ones(free_dof_count, dtype="<f8"),
        "solution_x": np.zeros(free_dof_count, dtype="<f8"),
        "true_residual": np.zeros(free_dof_count, dtype="<f8"),
        "work_w": np.zeros(free_dof_count, dtype="<f8"),
        "basis_v": np.zeros(free_dof_count, dtype="<f8"),
        "basis_z": np.zeros(free_dof_count, dtype="<f8"),
        "dense": np.zeros(1, dtype="<f8"),
        "reduction_ping": np.zeros(4, dtype="<f8"),
        "reduction_pong": np.zeros(4, dtype="<f8"),
        "control": np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1"),
        "record": np.zeros(record_bytes, dtype="u1"),
    }
    host_outputs: dict[str, np.ndarray] = {
        "solution_x": np.empty(free_dof_count, dtype="<f8"),
        "work_w": np.empty(free_dof_count, dtype="<f8"),
        "true_residual": np.empty(free_dof_count, dtype="<f8"),
        "control": np.empty(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1"),
        "record": np.empty(record_bytes, dtype="u1"),
    }

    device: dict[str, ctypes.c_void_p] = {}
    try:
        execution.open_stream()
        stream = execution.stream

        for name, host in host_inputs.items():
            device[name] = execution.allocate_and_upload(name, host)

        def launch_control(mode: int, schedule_epoch: int) -> None:
            kernel.launch_control(
                stream,
                mode,
                schedule_epoch,
                -1,
                -1,
                -1,
                -1,
                free_dof_count,
                restart_dimension,
                max_iterations,
                maximum_restart_count,
                2,
                absolute_tolerance,
                relative_tolerance,
                authoritative_tolerance,
                stagnation_relative_tolerance,
                divergence_factor,
                device["dense"],
                device["control"],
                device["record"],
            )

        def launch_reductions(rows: tuple[Any, ...]) -> None:
            metric_stages: dict[str, int] = {}
            for row in rows:
                stage = metric_stages.get(row.metric, 0)
                if stage % 2 == 0:
                    reduction_input = device["reduction_ping"]
                    reduction_output = device["reduction_pong"]
                else:
                    reduction_input = device["reduction_pong"]
                    reduction_output = device["reduction_ping"]
                kernel.launch_reduction(
                    stream,
                    row.reduction_mode,
                    row.reduction_target,
                    row.expected_schedule_epoch,
                    -1,
                    -1,
                    row.expected_reduction_epoch,
                    row.value_count,
                    0,
                    device["reduced_load"],
                    device["solution_x"],
                    device["true_residual"],
                    device["work_w"],
                    device["basis_v"],
                    reduction_input,
                    reduction_output,
                    device["control"],
                    device["record"],
                )
                metric_stages[row.metric] = stage + 1

        launch_control(control_modes["INIT"], 0)
        kernel.launch_vector(
            stream,
            vector_modes["COPY_INITIAL_X"],
            vector_gates["ACTIVE"],
            1,
            -1,
            -1,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        launch_reductions(reduction_rows[: 2 * stage_count])
        launch_control(control_modes["BIND_RHS"], 2 + 2 * stage_count)
        kernel.launch_csr_spmv_indexed(
            stream,
            spmv_modes["INITIAL"],
            3 + 2 * stage_count,
            -1,
            -1,
            free_dof_count,
            free_dof_count,
            0,
            device["row_ptr"],
            device["column_indices"],
            device["values"],
            device["solution_x"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["control"],
            device["record"],
        )
        launch_control(control_modes["OPERATOR_ACCEPT"], 4 + 2 * stage_count)
        kernel.launch_vector(
            stream,
            vector_modes["FORM_INITIAL_RESIDUAL"],
            vector_gates["ACTIVE"],
            5 + 2 * stage_count,
            -1,
            -1,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        launch_reductions(reduction_rows[2 * stage_count :])
        launch_control(control_modes["INITIAL_GATE"], 6 + 4 * stage_count)

        assert kernel.pending_stream_count == 1
        for name, host in host_outputs.items():
            execution.enqueue_download(name, device[name], host)
        execution.observe_fence_and_acknowledge()
        assert kernel.pending_stream_count == 0

        np.testing.assert_array_equal(host_outputs["solution_x"], oracle.solution_x)
        np.testing.assert_array_equal(host_outputs["work_w"], oracle.operator_value)
        np.testing.assert_array_equal(
            host_outputs["true_residual"], oracle.true_residual
        )

        control_payload = host_outputs["control"].tobytes()
        record_payload = host_outputs["record"].tobytes()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])

        assert _i32(control_payload, control_offsets, "control_abi_version") == 2
        assert (
            _i32(control_payload, control_offsets, "phase")
            == control_abi["phase_codes"]["terminal"]
        )
        assert _i32(control_payload, control_offsets, "free_dof_count") == 513
        assert _i32(control_payload, control_offsets, "restart_dimension") == 4
        assert _i32(control_payload, control_offsets, "max_iterations") == 0
        assert _i32(control_payload, control_offsets, "maximum_restart_count") == 0
        assert _i32(control_payload, control_offsets, "restart_index") == 0
        assert _i32(control_payload, control_offsets, "column_index") == -1
        assert _i32(control_payload, control_offsets, "reduction_epoch") == 8
        assert _i32(control_payload, control_offsets, "reduction_valid_mask") == 0
        assert _i32(control_payload, control_offsets, "failure_origin") == 0
        assert _i32(control_payload, control_offsets, "schedule_epoch") == 15
        for name in control_abi["transient_zero_fields"]:
            assert _i32(control_payload, control_offsets, name) == 0
        assert _f64(control_payload, control_offsets, "candidate_l2") == 0.0
        assert _f64(control_payload, control_offsets, "candidate_linf") == 0.0

        status_codes = record_abi["terminal_status_codes"]
        termination_codes = record_abi["termination_codes"]
        assert _i32(record_payload, record_offsets, "recurrence_abi_version") == 2
        assert _i32(record_payload, record_offsets, "active") == 0
        assert (
            _i32(record_payload, record_offsets, "terminal_status")
            == status_codes[oracle.terminal_status]
        )
        assert (
            _i32(record_payload, record_offsets, "termination_code")
            == termination_codes[oracle.termination_code]
        )
        assert _i32(record_payload, record_offsets, "device_error_bits") == 0
        assert _i32(record_payload, record_offsets, "scheduled_iterations") == 0
        assert _i32(record_payload, record_offsets, "effective_iterations") == 0
        assert _i32(record_payload, record_offsets, "scheduled_restarts") == 0
        assert _i32(record_payload, record_offsets, "effective_restarts") == 0
        assert _i32(record_payload, record_offsets, "effective_arnoldi_dimension") == 0
        assert (
            _i32(record_payload, record_offsets, "operator_apply_count")
            == oracle.operator_apply_count
            == 1
        )
        assert _i32(record_payload, record_offsets, "preconditioner_apply_count") == 0
        assert _i32(record_payload, record_offsets, "restart_dimension") == 4

        _assert_close(
            _f64(record_payload, record_offsets, "rhs_l2"),
            oracle.rhs_l2.value,
        )
        _assert_close(
            _f64(record_payload, record_offsets, "rhs_linf"),
            oracle.rhs_linf.value,
        )
        _assert_close(
            _f64(record_payload, record_offsets, "solver_tolerance_l2"),
            oracle.solver_tolerance_l2,
        )
        assert (
            _f64(
                record_payload,
                record_offsets,
                "authoritative_tolerance_scaled_linf",
            )
            == authoritative_tolerance
        )
        for name in (
            "initial_residual_l2",
            "final_residual_l2",
            "previous_checkpoint_residual_l2",
            "estimated_residual_l2",
        ):
            _assert_close(
                _f64(record_payload, record_offsets, name),
                oracle.residual_l2.value,
            )
        _assert_close(
            _f64(record_payload, record_offsets, "final_residual_linf"),
            oracle.residual_linf.value,
        )
        _assert_close(
            _f64(record_payload, record_offsets, "final_scaled_residual"),
            oracle.scaled_residual_linf,
        )
    finally:
        execution.close()


@pytest.mark.parametrize(
    "column_case",
    (
        "signed_dot_dgks",
        "orthogonal_no_dgks",
        "happy_breakdown",
        "triangular_breakdown",
        "cycle_end_candidate",
        "malformed_final_handoff_next_restart",
        "malformed_final_handoff_operator_count",
    ),
)
def test_native_gfx1030_first_column_checkpoint_transaction_matches_oracle(
    column_case: str,
) -> None:
    execution = _open_native_execution()
    kernel = execution.kernel

    free_dof_count = 513
    restart_dimension = (
        1
        if column_case
        in {
            "cycle_end_candidate",
            "malformed_final_handoff_next_restart",
            "malformed_final_handoff_operator_count",
        }
        else 4
    )
    max_iterations = restart_dimension
    maximum_restart_count = 1
    absolute_tolerance = 0.0
    relative_tolerance = 1.0e-15
    authoritative_tolerance = 1.0e-15
    stagnation_relative_tolerance = 1.0e-8
    divergence_factor = 1.0e8

    initial_solution = np.zeros(free_dof_count, dtype="<f8")
    if column_case == "signed_dot_dgks":
        # 256 independent [[1,-2],[-2,1]] blocks plus one trailing [1].
        # The diagonal is positive, while the all-ones residual has a
        # strictly negative first dot and triggers the second DGKS pass.
        row_ptr = np.empty(free_dof_count + 1, dtype="<i4")
        row_ptr[:free_dof_count] = 2 * np.arange(free_dof_count, dtype="<i4")
        row_ptr[free_dof_count] = 2 * (free_dof_count - 1) + 1
        nonzero_count = int(row_ptr[-1])
        column_indices = np.empty(nonzero_count, dtype="<i4")
        values = np.empty(nonzero_count, dtype="<f8")
        for first_row in range(0, free_dof_count - 1, 2):
            first = 2 * first_row
            column_indices[first : first + 4] = (
                first_row,
                first_row + 1,
                first_row,
                first_row + 1,
            )
            values[first : first + 4] = (1.0, -2.0, -2.0, 1.0)
        column_indices[-1] = free_dof_count - 1
        values[-1] = 1.0
        rhs = np.ones(free_dof_count, dtype="<f8")
    elif column_case == "orthogonal_no_dgks":
        # A positive diagonal plus A[1,0]=100 sends v0=e0 predominantly into
        # the orthogonal direction e1.  The first-pass norm remains above the
        # strict 0.717 threshold, so DGKS must stay in the Arnoldi phase.
        row_ptr = np.arange(free_dof_count + 1, dtype="<i4")
        row_ptr[2:] += 1
        nonzero_count = int(row_ptr[-1])
        column_indices = np.arange(free_dof_count, dtype="<i4")
        column_indices = np.insert(column_indices, 1, 0).astype("<i4", copy=False)
        values = np.ones(nonzero_count, dtype="<f8")
        values[1] = 100.0
        rhs = np.zeros(free_dof_count, dtype="<f8")
        rhs[0] = 1.0
    elif column_case == "happy_breakdown":
        # A=I and v0=e0 produces an exact invariant subspace after the first
        # projection.  The fixed second pass is active, H_NEXT is exact zero,
        # V1 must be canonical +0, and Givens must request a candidate check.
        row_ptr = np.arange(free_dof_count + 1, dtype="<i4")
        column_indices = np.arange(free_dof_count, dtype="<i4")
        values = np.ones(free_dof_count, dtype="<f8")
        nonzero_count = free_dof_count
        rhs = np.zeros(free_dof_count, dtype="<f8")
        rhs[0] = 1.0
    elif column_case == "triangular_breakdown":
        # Singular positive-diagonal [[1,-1],[-1,1]] blocks annihilate the
        # all-ones V0.  The trailing diagonal remains positive but receives a
        # zero residual entry, so both Givens and the triangular pivot are 0.
        row_ptr = np.empty(free_dof_count + 1, dtype="<i4")
        row_ptr[:free_dof_count] = 2 * np.arange(free_dof_count, dtype="<i4")
        row_ptr[free_dof_count] = 2 * (free_dof_count - 1) + 1
        nonzero_count = int(row_ptr[-1])
        column_indices = np.empty(nonzero_count, dtype="<i4")
        values = np.empty(nonzero_count, dtype="<f8")
        for first_row in range(0, free_dof_count - 1, 2):
            first = 2 * first_row
            column_indices[first : first + 4] = (
                first_row,
                first_row + 1,
                first_row,
                first_row + 1,
            )
            values[first : first + 4] = (1.0, -1.0, -1.0, 1.0)
        column_indices[-1] = free_dof_count - 1
        values[-1] = 1.0
        rhs = np.ones(free_dof_count, dtype="<f8")
        rhs[-1] = 0.0
    else:
        # The same noninvariant orthogonal-dominant operator becomes an
        # unconditional cycle-end candidate when M=1.  This exercises the
        # active candidate SpMV/residual/dual-metric path without relying on
        # happy or invariant breakdown.
        row_ptr = np.arange(free_dof_count + 1, dtype="<i4")
        row_ptr[2:] += 1
        nonzero_count = int(row_ptr[-1])
        column_indices = np.arange(free_dof_count, dtype="<i4")
        column_indices = np.insert(column_indices, 1, 0).astype("<i4", copy=False)
        values = np.ones(nonzero_count, dtype="<f8")
        values[1] = 100.0
        rhs = np.zeros(free_dof_count, dtype="<f8")
        rhs[0] = 1.0
    inverse_diagonal = np.ones(free_dof_count, dtype="<f8")
    initial_oracle = replay_fgmres_gpu_tree_initial_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        rhs=rhs,
        initial_solution=initial_solution,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        authoritative_tolerance=authoritative_tolerance,
        max_iterations=max_iterations,
    )
    assert initial_oracle.terminal_status == "not_terminal"
    basis_v0 = np.ascontiguousarray(
        initial_oracle.true_residual / initial_oracle.residual_l2.value,
        dtype="<f8",
    )
    column_oracle = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=inverse_diagonal,
    )
    completion_oracle = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=inverse_diagonal,
        cycle_beta=initial_oracle.residual_l2.value,
        solver_tolerance_l2=initial_oracle.solver_tolerance_l2,
        cycle_width=restart_dimension,
    )
    preparation_oracle = prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=completion_oracle,
        committed_solution=initial_solution,
    )
    candidate_residual_oracle = (
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=preparation_oracle,
            row_ptr=row_ptr,
            column_indices=column_indices,
            values=values,
            reduced_load=rhs,
        )
    )
    candidate_scale_oracle = (
        prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
            candidate_residual=candidate_residual_oracle,
            solver_tolerance_l2=initial_oracle.solver_tolerance_l2,
            authoritative_tolerance=authoritative_tolerance,
            rhs_linf=initial_oracle.rhs_linf.value,
            initial_residual_l2=initial_oracle.residual_l2.value,
            divergence_factor=divergence_factor,
            committed_solution=initial_solution,
        )
    )
    checkpoint_oracle = prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2(
        candidate_scale_metrics=candidate_scale_oracle,
        solver_tolerance_l2=initial_oracle.solver_tolerance_l2,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=initial_oracle.rhs_linf.value,
        initial_residual_l2=initial_oracle.residual_l2.value,
        divergence_factor=divergence_factor,
        committed_solution=initial_solution,
        committed_true_residual=initial_oracle.true_residual,
        previous_checkpoint_l2=initial_oracle.residual_l2.value,
        previous_solution_scale_l2=0.0,
        previous_stagnation_checkpoint_count=0,
        previous_false_convergence_count=0,
        previous_happy_breakdown_count=0,
        stagnation_relative_tolerance=stagnation_relative_tolerance,
        stagnation_checkpoint_limit=2,
        max_iterations=max_iterations,
        restart_dimension=restart_dimension,
    )
    if column_case == "signed_dot_dgks":
        assert column_oracle.h00_first_coefficient < 0.0
        assert column_oracle.dgks_second_pass is True
    elif column_case == "orthogonal_no_dgks":
        assert column_oracle.h00_first_coefficient == 1.0
        assert column_oracle.dgks_second_pass is False
    elif column_case == "happy_breakdown":
        assert column_oracle.h00_first_coefficient == 1.0
        assert column_oracle.dgks_second_pass is True
        assert completion_oracle.h_next_invariant_breakdown is True
        assert completion_oracle.candidate_reason_bits == 3
        assert preparation_oracle.candidate_vector_valid is True
    else:
        if column_case == "triangular_breakdown":
            assert completion_oracle.rotated_h00 == 0.0
            assert completion_oracle.candidate_required is True
            assert preparation_oracle.triangular_breakdown is True
            assert preparation_oracle.invariant_breakdown is True
        else:
            assert column_case in {
                "cycle_end_candidate",
                "malformed_final_handoff_next_restart",
                "malformed_final_handoff_operator_count",
            }
            assert column_oracle.dgks_second_pass is False
            assert completion_oracle.invariant_breakdown is False
            assert completion_oracle.candidate_reason_bits == 4
            assert preparation_oracle.candidate_vector_valid is True

    assert candidate_residual_oracle.candidate_replay_valid == (
        preparation_oracle.candidate_vector_valid
    )
    assert candidate_scale_oracle.candidate_scale_required == (
        column_case
        in {
            "cycle_end_candidate",
            "malformed_final_handoff_next_restart",
            "malformed_final_handoff_operator_count",
        }
    )

    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    control_offsets = _field_offsets(control_abi["fields"])
    control_modes = control_abi["control_mode_codes"]
    vector_modes = control_abi["vector_mode_codes"]
    vector_gates = control_abi["vector_gate_codes"]
    spmv_modes = control_abi["spmv_mode_codes"]
    initial_rows = initial_reduction_launches_v2(free_dof_count)
    column_rows = first_column_reduction_launches_v2(free_dof_count)
    completion_rows = first_column_completion_launches_v2(free_dof_count)
    preparation_rows = first_column_candidate_preparation_launches_v2(free_dof_count)
    candidate_residual_rows = first_column_candidate_residual_launches_v2(
        free_dof_count,
        restart_dimension,
    )
    candidate_scale_rows = first_column_candidate_scale_metrics_launches_v2(
        free_dof_count
    )
    predecessor_validation_row = first_column_predecessor_validation_launch_v2(
        free_dof_count
    )
    checkpoint_rows = first_column_checkpoint_transaction_launches_v2(
        free_dof_count,
        restart_dimension,
    )
    stage_outputs = reduction_stage_output_counts_v2(free_dof_count)
    stage_count = len(stage_outputs)
    assert stage_count == 2
    assert len(initial_rows) == 8
    assert len(column_rows) == 6
    assert len(completion_rows) == 8
    assert len(preparation_rows) == stage_count + 3 == 5
    assert len(candidate_residual_rows) == 2 * stage_count + 3 == 7
    assert len(candidate_scale_rows) == 2 * stage_count == 4
    assert len(checkpoint_rows) == 4

    dense_count = restart_dimension * restart_dimension + 5 * restart_dimension + 1
    record_bytes = solve_record_byte_length_v2(maximum_restart_count)
    host_inputs: dict[str, np.ndarray] = {
        "row_ptr": row_ptr,
        "column_indices": column_indices,
        "values": values,
        "reduced_state": initial_solution,
        "reduced_load": rhs,
        "inverse_diagonal": inverse_diagonal,
        "solution_x": np.zeros(free_dof_count, dtype="<f8"),
        "true_residual": np.zeros(free_dof_count, dtype="<f8"),
        "work_w": np.zeros(free_dof_count, dtype="<f8"),
        "basis_v": np.zeros(
            (restart_dimension + 1) * free_dof_count,
            dtype="<f8",
        ),
        "basis_z": np.zeros(restart_dimension * free_dof_count, dtype="<f8"),
        "dense": np.zeros(dense_count, dtype="<f8"),
        "reduction_ping": np.zeros(4, dtype="<f8"),
        "reduction_pong": np.zeros(4, dtype="<f8"),
        "control": np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1"),
        "record": np.zeros(record_bytes, dtype="u1"),
    }
    candidate_scratch_poison = np.full(free_dof_count, np.nan, dtype="<f8")
    host_inputs["basis_v"][
        restart_dimension * free_dof_count : (restart_dimension + 1) * free_dof_count
    ] = candidate_scratch_poison
    host_outputs: dict[str, np.ndarray] = {
        "solution_x": np.empty_like(host_inputs["solution_x"]),
        "true_residual": np.empty_like(host_inputs["true_residual"]),
        "basis_v": np.empty_like(host_inputs["basis_v"]),
        "basis_z": np.empty_like(host_inputs["basis_z"]),
        "work_w": np.empty_like(host_inputs["work_w"]),
        "dense": np.empty_like(host_inputs["dense"]),
        "control": np.empty_like(host_inputs["control"]),
        "record": np.empty_like(host_inputs["record"]),
    }

    device: dict[str, ctypes.c_void_p] = {}
    try:
        execution.open_stream()
        stream = execution.stream
        for name, host in host_inputs.items():
            device[name] = execution.allocate_and_upload(name, host)

        def launch_control(
            mode: int,
            schedule_epoch: int,
            expected_restart: int = -1,
            expected_column: int = -1,
            row_index: int = -1,
            pass_index: int = -1,
        ) -> None:
            kernel.launch_control(
                stream,
                mode,
                schedule_epoch,
                expected_restart,
                expected_column,
                row_index,
                pass_index,
                free_dof_count,
                restart_dimension,
                max_iterations,
                maximum_restart_count,
                2,
                absolute_tolerance,
                relative_tolerance,
                authoritative_tolerance,
                stagnation_relative_tolerance,
                divergence_factor,
                device["dense"],
                device["control"],
                device["record"],
            )

        def launch_reductions(rows: tuple[Any, ...]) -> None:
            metric_stages: dict[str, int] = {}
            for row in rows:
                stage = metric_stages.get(row.metric, 0)
                if stage % 2 == 0:
                    reduction_input = device["reduction_ping"]
                    reduction_output = device["reduction_pong"]
                else:
                    reduction_input = device["reduction_pong"]
                    reduction_output = device["reduction_ping"]
                kernel.launch_reduction(
                    stream,
                    row.reduction_mode,
                    row.reduction_target,
                    row.expected_schedule_epoch,
                    getattr(row, "expected_restart", -1),
                    getattr(row, "expected_column", -1),
                    row.expected_reduction_epoch,
                    row.value_count,
                    getattr(row, "logical_index", 0),
                    device["reduced_load"],
                    device["solution_x"],
                    device["true_residual"],
                    device["work_w"],
                    device["basis_v"],
                    reduction_input,
                    reduction_output,
                    device["control"],
                    device["record"],
                )
                metric_stages[row.metric] = stage + 1

        launch_control(control_modes["INIT"], 0)
        kernel.launch_vector(
            stream,
            vector_modes["COPY_INITIAL_X"],
            vector_gates["ACTIVE"],
            1,
            -1,
            -1,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        launch_reductions(initial_rows[: 2 * stage_count])
        launch_control(control_modes["BIND_RHS"], 2 + 2 * stage_count)
        kernel.launch_csr_spmv_indexed(
            stream,
            spmv_modes["INITIAL"],
            3 + 2 * stage_count,
            -1,
            -1,
            free_dof_count,
            nonzero_count,
            0,
            device["row_ptr"],
            device["column_indices"],
            device["values"],
            device["solution_x"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["control"],
            device["record"],
        )
        launch_control(control_modes["OPERATOR_ACCEPT"], 4 + 2 * stage_count)
        kernel.launch_vector(
            stream,
            vector_modes["FORM_INITIAL_RESIDUAL"],
            vector_gates["ACTIVE"],
            5 + 2 * stage_count,
            -1,
            -1,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        launch_reductions(initial_rows[2 * stage_count :])
        launch_control(control_modes["INITIAL_GATE"], 6 + 4 * stage_count)

        boundary = 7 + 4 * stage_count
        launch_control(control_modes["RESTART_BEGIN"], boundary, 1, -1)
        kernel.launch_vector(
            stream,
            vector_modes["NORMALIZE_V0"],
            vector_gates["ACTIVE"],
            boundary + 1,
            1,
            0,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        kernel.launch_vector(
            stream,
            vector_modes["APPLY_JACOBI_INDEXED"],
            vector_gates["ACTIVE"],
            boundary + 2,
            1,
            0,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        launch_control(control_modes["PRECONDITION_ACCEPT"], boundary + 3, 1, 0)
        kernel.launch_csr_spmv_indexed(
            stream,
            spmv_modes["ARNOLDI"],
            boundary + 4,
            1,
            0,
            free_dof_count,
            nonzero_count,
            0,
            device["row_ptr"],
            device["column_indices"],
            device["values"],
            device["solution_x"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["control"],
            device["record"],
        )
        launch_control(control_modes["OPERATOR_ACCEPT"], boundary + 5, 1, 0)
        launch_reductions(column_rows[:stage_count])
        launch_reductions(column_rows[stage_count : 2 * stage_count])
        launch_control(control_modes["DOT_ACCEPT"], 13 + 6 * stage_count, 1, 0, 0, 0)
        kernel.launch_vector(
            stream,
            vector_modes["MGS_SUBTRACT_INDEXED"],
            vector_gates["ACTIVE"],
            14 + 6 * stage_count,
            1,
            0,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )
        launch_reductions(column_rows[2 * stage_count :])
        launch_control(
            control_modes["DGKS_DECIDE"],
            15 + 7 * stage_count,
            1,
            0,
            -1,
            0,
        )

        completion_metric_stages: dict[str, int] = {}
        handoff_corruption: np.ndarray | None = None
        for row in (
            *completion_rows,
            *preparation_rows,
            *candidate_residual_rows,
            *candidate_scale_rows,
            predecessor_validation_row,
            *checkpoint_rows,
        ):
            if row.submission_kind == "reduction":
                assert row.reduction_target is not None
                assert row.expected_reduction_epoch is not None
                assert row.value_count is not None
                assert row.logical_index is not None
                stage = completion_metric_stages.get(row.name, 0)
                reduction_input = (
                    device["reduction_ping"]
                    if stage % 2 == 0
                    else device["reduction_pong"]
                )
                reduction_output = (
                    device["reduction_pong"]
                    if stage % 2 == 0
                    else device["reduction_ping"]
                )
                kernel.launch_reduction(
                    stream,
                    row.mode,
                    row.reduction_target,
                    row.expected_schedule_epoch,
                    row.expected_restart,
                    row.expected_column,
                    row.expected_reduction_epoch,
                    row.value_count,
                    row.logical_index,
                    device["reduced_load"],
                    device["solution_x"],
                    device["true_residual"],
                    device["work_w"],
                    device["basis_v"],
                    reduction_input,
                    reduction_output,
                    device["control"],
                    device["record"],
                )
                completion_metric_stages[row.name] = stage + 1
            elif row.submission_kind == "control":
                assert row.row_index is not None
                assert row.pass_index is not None
                if column_case.startswith("malformed_final_handoff_") and (
                    row.name == "CHECKPOINT_FINALIZE_COLUMN0"
                ):
                    if column_case == "malformed_final_handoff_next_restart":
                        corruption_role = "control"
                        corruption_field = "next_expected_restart"
                        corruption_value = maximum_restart_count
                    else:
                        assert column_case == "malformed_final_handoff_operator_count"
                        corruption_role = "record"
                        corruption_field = "operator_apply_count"
                        corruption_value = (
                            candidate_scale_oracle.operator_apply_count + 1
                        )
                    corruption_offsets = (
                        control_offsets
                        if corruption_role == "control"
                        else _field_offsets(record_abi["header_fields"])
                    )
                    handoff_corruption = np.asarray([corruption_value], dtype="<i4")
                    corrupt_destination = ctypes.c_void_p(
                        device[corruption_role].value
                        + corruption_offsets[corruption_field]
                    )
                    _require_hip_success(
                        execution.api.runtime,
                        int(
                            execution.api.hip_memcpy_async(
                                corrupt_destination,
                                ctypes.c_void_p(handoff_corruption.ctypes.data),
                                handoff_corruption.nbytes,
                                _HIP_MEMCPY_HOST_TO_DEVICE,
                                stream,
                            )
                        ),
                        "hipMemcpyAsync(H2D malformed final handoff)",
                    )
                launch_control(
                    row.mode,
                    row.expected_schedule_epoch,
                    row.expected_restart,
                    row.expected_column,
                    row.row_index,
                    row.pass_index,
                )
            elif row.submission_kind == "spmv":
                assert row.logical_index is not None
                kernel.launch_csr_spmv_indexed(
                    stream,
                    row.mode,
                    row.expected_schedule_epoch,
                    row.expected_restart,
                    row.expected_column,
                    free_dof_count,
                    nonzero_count,
                    row.logical_index,
                    device["row_ptr"],
                    device["column_indices"],
                    device["values"],
                    device["solution_x"],
                    device["work_w"],
                    device["basis_v"],
                    device["basis_z"],
                    device["control"],
                    device["record"],
                )
            else:
                assert row.submission_kind == "vector"
                assert row.vector_gate is not None
                assert row.logical_index is not None
                kernel.launch_vector(
                    stream,
                    row.mode,
                    row.vector_gate,
                    row.expected_schedule_epoch,
                    row.expected_restart,
                    row.expected_column,
                    free_dof_count,
                    row.logical_index,
                    device["reduced_state"],
                    device["reduced_load"],
                    device["inverse_diagonal"],
                    device["solution_x"],
                    device["true_residual"],
                    device["work_w"],
                    device["basis_v"],
                    device["basis_z"],
                    device["dense"],
                    device["control"],
                    device["record"],
                )
                if (
                    column_case
                    in {
                        "cycle_end_candidate",
                        "malformed_final_handoff_next_restart",
                        "malformed_final_handoff_operator_count",
                    }
                    and row.name == "PREFLIGHT_COMMIT_SOURCE_COLUMN0"
                ):
                    sealed_preflight_control = np.empty_like(host_inputs["control"])
                    execution.enqueue_download(
                        "sealed_preflight_control",
                        device["control"],
                        sealed_preflight_control,
                    )
                    execution.observe_fence_and_acknowledge()
                    sealed_payload = sealed_preflight_control.tobytes()
                    assert (
                        _i32(
                            sealed_payload,
                            control_offsets,
                            "predecessor_validation_state",
                        )
                        == control_abi["predecessor_validation_state_codes"][
                            "commit_preflighted"
                        ]
                    )
                    assert (
                        _i32(
                            sealed_payload,
                            control_offsets,
                            "predecessor_mask_snapshot",
                        )
                        == 7936
                    )
                    assert (
                        _i32(
                            sealed_payload,
                            control_offsets,
                            "predecessor_reduction_epoch_snapshot",
                        )
                        == 14 * stage_count
                    )
                    assert (
                        _i32(sealed_payload, control_offsets, "schedule_epoch")
                        == row.expected_schedule_epoch
                    )

        assert kernel.pending_stream_count == 1
        for name, host in host_outputs.items():
            execution.enqueue_download(name, device[name], host)
        execution.observe_fence_and_acknowledge()
        assert kernel.pending_stream_count == 0

        if column_case.startswith("malformed_final_handoff_"):
            assert handoff_corruption is not None
            control_payload = host_outputs["control"].tobytes()
            record_payload = host_outputs["record"].tobytes()
            record_offsets = _field_offsets(record_abi["header_fields"])
            assert (
                _i32(control_payload, control_offsets, "phase")
                == control_abi["phase_codes"]["failed"]
            )
            assert _i32(control_payload, control_offsets, "failure_origin") == 1
            assert _i32(record_payload, record_offsets, "active") == 0
            assert _i32(record_payload, record_offsets, "terminal_status") == 6
            assert _i32(record_payload, record_offsets, "termination_code") == 47
            assert _i32(record_payload, record_offsets, "device_error_bits") == 1
            assert _f64(record_payload, record_offsets, "final_residual_l2") == (
                initial_oracle.residual_l2.value
            )
            assert _f64(record_payload, record_offsets, "final_residual_linf") == (
                initial_oracle.residual_linf.value
            )
            assert _f64(record_payload, record_offsets, "final_scaled_residual") == (
                initial_oracle.scaled_residual_linf
            )
            assert _f64(record_payload, record_offsets, "solution_update_l2") == 0.0
            assert (
                _f64(
                    record_payload,
                    record_offsets,
                    "previous_checkpoint_residual_l2",
                )
                == initial_oracle.residual_l2.value
            )
            restart_payload = record_payload[
                record_abi["header_bytes"] : record_abi["header_bytes"]
                + record_abi["restart_bytes"]
            ]
            assert restart_payload == bytes(record_abi["restart_bytes"])
            return

        np.testing.assert_array_equal(
            host_outputs["basis_v"][:free_dof_count],
            column_oracle.basis_v0,
        )
        np.testing.assert_array_equal(
            host_outputs["basis_z"][:free_dof_count],
            column_oracle.jacobi_z0,
        )
        if not (
            restart_dimension == 1 and candidate_residual_oracle.candidate_replay_valid
        ):
            np.testing.assert_array_equal(
                host_outputs["basis_v"][free_dof_count : 2 * free_dof_count],
                completion_oracle.basis_v1,
            )
        if completion_oracle.h_next_invariant_breakdown and restart_dimension != 1:
            assert not np.any(
                np.signbit(host_outputs["basis_v"][free_dof_count : 2 * free_dof_count])
            )
        candidate_scratch = host_outputs["basis_v"][
            restart_dimension * free_dof_count : (restart_dimension + 1)
            * free_dof_count
        ]
        if candidate_residual_oracle.candidate_replay_valid:
            np.testing.assert_array_equal(
                candidate_scratch,
                candidate_residual_oracle.candidate_true_residual,
            )
        else:
            np.testing.assert_array_equal(
                candidate_scratch.view("<u8"),
                candidate_scratch_poison.view("<u8"),
            )
        np.testing.assert_array_equal(
            host_outputs["work_w"],
            (
                preparation_oracle.trial_x
                if preparation_oracle.candidate_vector_valid
                else column_oracle.work_after_final
            ),
        )
        np.testing.assert_array_equal(
            host_outputs["solution_x"], checkpoint_oracle.solution_x
        )
        np.testing.assert_array_equal(
            host_outputs["true_residual"], checkpoint_oracle.true_residual
        )
        dense = host_outputs["dense"]
        cosine0_offset = restart_dimension * (restart_dimension + 1)
        sine0_offset = cosine0_offset + restart_dimension
        g0_offset = sine0_offset + restart_dimension
        y0_offset = g0_offset + restart_dimension + 1
        assert dense[0] == completion_oracle.rotated_h00
        assert dense[1] == completion_oracle.rotated_h10
        assert dense[cosine0_offset] == completion_oracle.cosine0
        assert dense[sine0_offset] == completion_oracle.sine0
        assert dense[g0_offset] == completion_oracle.g0
        assert dense[g0_offset + 1] == completion_oracle.g1
        if preparation_oracle.candidate_vector_valid:
            assert dense[y0_offset] == preparation_oracle.y0
        elif preparation_oracle.triangular_breakdown:
            assert dense[y0_offset] == 0.0
            assert not np.signbit(dense[y0_offset])
        else:
            assert dense[y0_offset] == column_oracle.h00_second_coefficient

        control_payload = host_outputs["control"].tobytes()
        record_payload = host_outputs["record"].tobytes()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        assert (
            _i32(control_payload, control_offsets, "phase")
            == control_abi["phase_codes"][checkpoint_oracle.phase_after_finalize]
        )
        assert _i32(control_payload, control_offsets, "restart_index") == 1
        assert _i32(control_payload, control_offsets, "next_expected_restart") == 2
        assert (
            _i32(control_payload, control_offsets, "column_index")
            == checkpoint_oracle.column_index_after_finalize
        )
        assert _i32(control_payload, control_offsets, "cycle_start_iteration") == 0
        assert (
            _i32(control_payload, control_offsets, "cycle_width") == restart_dimension
        )
        assert _i32(control_payload, control_offsets, "arnoldi_step_count") == 1
        assert (
            _i32(control_payload, control_offsets, "reorthogonalization_count")
            == completion_oracle.reorthogonalization_count
        )
        assert _i32(control_payload, control_offsets, "dgks_reorth_required") == 0
        assert _i32(control_payload, control_offsets, "invariant_breakdown") == 0
        assert _i32(control_payload, control_offsets, "candidate_required") == 0
        assert _i32(control_payload, control_offsets, "candidate_reason_bits") == 0
        assert _i32(control_payload, control_offsets, "triangular_breakdown") == 0
        assert _i32(control_payload, control_offsets, "commit_required") == 0
        assert _i32(control_payload, control_offsets, "continuation_required") == 0
        assert _i32(control_payload, control_offsets, "pending_terminal_status") == 0
        assert _i32(control_payload, control_offsets, "pending_termination_code") == 0
        assert _i32(control_payload, control_offsets, "pending_restart_hint") == 0
        assert _i32(control_payload, control_offsets, "pending_restart_flags") == 0
        assert _i32(control_payload, control_offsets, "reduction_valid_mask") == 0
        assert (
            _i32(control_payload, control_offsets, "predecessor_validation_state")
            == control_abi["predecessor_validation_state_codes"]["empty"]
        )
        assert _i32(control_payload, control_offsets, "predecessor_mask_snapshot") == 0
        assert (
            _i32(
                control_payload,
                control_offsets,
                "predecessor_reduction_epoch_snapshot",
            )
            == 0
        )
        assert (
            _i32(control_payload, control_offsets, "reduction_epoch")
            == 14 * stage_count
        )
        assert (
            _i32(control_payload, control_offsets, "schedule_epoch")
            == 29 + 14 * stage_count
        )
        expected_cycle_beta = (
            checkpoint_oracle.final_residual_l2
            if checkpoint_oracle.continuation_kind == "between_restarts"
            else initial_oracle.residual_l2.value
        )
        assert (
            _f64(control_payload, control_offsets, "cycle_beta") == expected_cycle_beta
        )
        assert _f64(control_payload, control_offsets, "dot_coefficient") == 0.0
        assert _f64(control_payload, control_offsets, "work_before_l2") == (
            column_oracle.work_before_l2.value
        )
        assert _f64(control_payload, control_offsets, "after_first_l2") == 0.0
        assert _f64(control_payload, control_offsets, "h_next_l2") == 0.0
        assert _f64(control_payload, control_offsets, "candidate_l2") == 0.0
        assert _f64(control_payload, control_offsets, "candidate_linf") == 0.0
        assert _f64(control_payload, control_offsets, "solution_update_l2") == 0.0
        assert _f64(control_payload, control_offsets, "trial_x_l2") == 0.0
        assert _f64(control_payload, control_offsets, "committed_x_l2") == 0.0
        assert _f64(control_payload, control_offsets, "x_scale_l2") == 0.0

        assert _i32(record_payload, record_offsets, "active") == int(
            checkpoint_oracle.active_after_finalize
        )
        assert (
            _i32(record_payload, record_offsets, "terminal_status")
            == checkpoint_oracle.terminal_status_code
        )
        assert (
            _i32(record_payload, record_offsets, "termination_code")
            == checkpoint_oracle.termination_code_value
        )
        assert _i32(record_payload, record_offsets, "device_error_bits") == 0
        assert checkpoint_oracle.final_guard_handoff_required == (
            column_case == "cycle_end_candidate"
        )
        if checkpoint_oracle.final_guard_handoff_required:
            assert checkpoint_oracle.pending_terminal_status == "max_iterations"
            assert checkpoint_oracle.pending_termination_code == (
                "max_iterations_exhausted"
            )
            assert checkpoint_oracle.terminal_status == "not_terminal"
            assert checkpoint_oracle.termination_code == "none"
        assert _i32(record_payload, record_offsets, "effective_restarts") == 1
        assert (
            _i32(record_payload, record_offsets, "effective_iterations")
            == completion_oracle.effective_iterations
        )
        assert (
            _i32(record_payload, record_offsets, "effective_arnoldi_dimension")
            == completion_oracle.effective_arnoldi_dimension
        )
        assert (
            _i32(record_payload, record_offsets, "operator_apply_count")
            == candidate_scale_oracle.operator_apply_count
        )
        assert (
            _i32(record_payload, record_offsets, "preconditioner_apply_count")
            == completion_oracle.preconditioner_apply_count
        )
        assert (
            _i32(record_payload, record_offsets, "happy_breakdown_count")
            == checkpoint_oracle.happy_breakdown_count
        )
        assert (
            _i32(record_payload, record_offsets, "stagnation_checkpoint_count")
            == checkpoint_oracle.stagnation_checkpoint_count
        )
        assert (
            _i32(record_payload, record_offsets, "false_convergence_count")
            == checkpoint_oracle.false_convergence_count
        )
        assert _f64(record_payload, record_offsets, "final_residual_l2") == (
            checkpoint_oracle.final_residual_l2
        )
        assert _f64(record_payload, record_offsets, "final_residual_linf") == (
            checkpoint_oracle.final_residual_linf
        )
        assert _f64(record_payload, record_offsets, "final_scaled_residual") == (
            checkpoint_oracle.final_scaled_residual
        )
        assert (
            _f64(
                record_payload,
                record_offsets,
                "previous_checkpoint_residual_l2",
            )
            == checkpoint_oracle.previous_checkpoint_l2
        )
        expected_header_update = (
            preparation_oracle.solution_update_l2.value
            if checkpoint_oracle.commit_required
            and preparation_oracle.solution_update_l2 is not None
            else 0.0
        )
        assert (
            _f64(record_payload, record_offsets, "solution_update_l2")
            == expected_header_update
        )
        assert _f64(record_payload, record_offsets, "solution_scale_l2") == (
            checkpoint_oracle.solution_scale_l2
        )
        assert (
            _f64(record_payload, record_offsets, "estimated_residual_l2")
            == completion_oracle.estimated_residual_l2
        )
        assert (
            _f64(record_payload, record_offsets, "arnoldi_work_l2")
            == column_oracle.work_before_l2.value
        )
        assert (
            _f64(record_payload, record_offsets, "arnoldi_breakdown_threshold")
            == completion_oracle.h_next_breakdown_threshold
        )
        assert _f64(record_payload, record_offsets, "triangular_scale") == (
            preparation_oracle.triangular_scale
            if preparation_oracle.triangular_scale is not None
            else 0.0
        )
        restart_payload = record_payload[
            record_abi["header_bytes"] : record_abi["header_bytes"]
            + record_abi["restart_bytes"]
        ]
        restart_offsets = _field_offsets(record_abi["restart_fields"])
        if checkpoint_oracle.restart_record is None:
            assert restart_payload == bytes(record_abi["restart_bytes"])
        else:
            expected_row = checkpoint_oracle.restart_record
            assert _i32(restart_payload, restart_offsets, "restart_index") == 1
            assert (
                _i32(restart_payload, restart_offsets, "start_iteration")
                == expected_row.start_iteration
            )
            assert (
                _i32(restart_payload, restart_offsets, "end_iteration")
                == expected_row.end_iteration
            )
            assert (
                _i32(restart_payload, restart_offsets, "arnoldi_step_count")
                == expected_row.arnoldi_step_count
            )
            assert (
                _i32(
                    restart_payload,
                    restart_offsets,
                    "reorthogonalization_count",
                )
                == expected_row.reorthogonalization_count
            )
            assert (
                _i32(restart_payload, restart_offsets, "termination_hint")
                == expected_row.termination_hint_code
            )
            assert _i32(restart_payload, restart_offsets, "flags") == expected_row.flags
            _assert_close(
                _f64(restart_payload, restart_offsets, "estimated_residual_l2"),
                expected_row.estimated_residual_l2,
            )
            _assert_close(
                _f64(restart_payload, restart_offsets, "true_residual_l2"),
                expected_row.true_residual_l2,
            )
            _assert_close(
                _f64(restart_payload, restart_offsets, "true_residual_linf"),
                expected_row.true_residual_linf,
            )
            _assert_close(
                _f64(restart_payload, restart_offsets, "scaled_true_residual"),
                expected_row.scaled_true_residual,
            )
            _assert_close(
                _f64(restart_payload, restart_offsets, "solution_update_l2"),
                expected_row.solution_update_l2,
            )
    finally:
        execution.close()


@pytest.mark.parametrize(
    "checkpoint_case",
    (
        "early_false_convergence",
        "unhappy_invariant",
        "strict_divergence",
        "stagnation_limit",
        "x_scale_overflow",
        "invalid_commit_sources",
        "duplicate_preflight",
        "skip_preflight",
    ),
)
def test_native_gfx1030_synthetic_checkpoint_boundary_priority_and_failure(
    checkpoint_case: str,
) -> None:
    execution = _open_native_execution()
    kernel = execution.kernel
    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    control_offsets = _field_offsets(control_abi["fields"])
    record_offsets = _field_offsets(record_abi["header_fields"])
    restart_offsets = _field_offsets(record_abi["restart_fields"])
    phase_codes = control_abi["phase_codes"]

    free_dof_count = 513
    stage_count = len(reduction_stage_output_counts_v2(free_dof_count))
    assert stage_count == 2
    planned = checkpoint_case in {
        "strict_divergence",
        "stagnation_limit",
        "x_scale_overflow",
        "invalid_commit_sources",
        "duplicate_preflight",
        "skip_preflight",
    }
    restart_dimension = 1 if planned else 4
    max_iterations = 2 if planned else 4
    maximum_restart_count = (
        max_iterations + restart_dimension - 1
    ) // restart_dimension
    cycle_width = 1 if planned else restart_dimension
    candidate_reason_bits = {
        "early_false_convergence": 1,
        "unhappy_invariant": 2,
        "strict_divergence": 4,
        "stagnation_limit": 4,
        "x_scale_overflow": 4,
        "invalid_commit_sources": 4,
        "duplicate_preflight": 4,
        "skip_preflight": 4,
    }[checkpoint_case]
    invariant_breakdown = int(checkpoint_case == "unhappy_invariant")
    candidate_l2 = {
        "early_false_convergence": 2.0,
        "unhappy_invariant": 2.0,
        "strict_divergence": float(np.nextafter(2.0, np.inf)),
        "stagnation_limit": 1.5,
        "x_scale_overflow": 1.5,
        "invalid_commit_sources": float(np.nextafter(2.0, np.inf)),
        "duplicate_preflight": float(np.nextafter(2.0, np.inf)),
        "skip_preflight": float(np.nextafter(2.0, np.inf)),
    }[checkpoint_case]
    scale_path = checkpoint_case in {"stagnation_limit", "x_scale_overflow"}
    reduction_valid_mask = 7936 if scale_path else 1792
    trial_x_l2 = (
        np.finfo(np.float64).max if checkpoint_case == "x_scale_overflow" else 1.0
    )
    committed_x_l2 = trial_x_l2
    solution_update_l2 = (
        np.ldexp(2.0, -26) if checkpoint_case == "stagnation_limit" else 0.5
    )
    prior_stagnation = int(checkpoint_case == "stagnation_limit")

    committed_solution = (
        np.arange(free_dof_count, dtype="<f8") * np.float64(0.125) - 17.0
    )
    committed_residual = 31.0 - np.arange(free_dof_count, dtype="<f8") * np.float64(
        0.0625
    )
    trial_solution = np.full(free_dof_count, 2.0, dtype="<f8")
    candidate_residual = np.full(free_dof_count, 3.0, dtype="<f8")
    if checkpoint_case == "early_false_convergence":
        trial_solution[-1] = np.nan
        candidate_residual[-1] = np.inf
    elif checkpoint_case == "invalid_commit_sources":
        trial_solution[-1] = np.nan
        candidate_residual[-2] = -np.inf
    basis_v = np.zeros((restart_dimension + 1) * free_dof_count, dtype="<f8")
    basis_v[
        restart_dimension * free_dof_count : (restart_dimension + 1) * free_dof_count
    ] = candidate_residual
    basis_z = np.zeros(restart_dimension * free_dof_count, dtype="<f8")
    dense = np.zeros(
        restart_dimension * restart_dimension + 5 * restart_dimension + 1,
        dtype="<f8",
    )
    control = np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1")
    record = np.zeros(
        solve_record_byte_length_v2(maximum_restart_count),
        dtype="u1",
    )

    for name, value in {
        "control_abi_version": 2,
        "phase": phase_codes["candidate"],
        "free_dof_count": free_dof_count,
        "restart_dimension": restart_dimension,
        "max_iterations": max_iterations,
        "maximum_restart_count": maximum_restart_count,
        "restart_index": 1,
        "cycle_start_iteration": 0,
        "cycle_width": cycle_width,
        "column_index": 0,
        "arnoldi_step_count": 1,
        "reorthogonalization_count": 0,
        "dgks_reorth_required": 0,
        "invariant_breakdown": invariant_breakdown,
        "candidate_required": 1,
        "candidate_reason_bits": candidate_reason_bits,
        "triangular_breakdown": 0,
        "commit_required": 0,
        "continuation_required": 0,
        "pending_terminal_status": 0,
        "pending_termination_code": 0,
        "pending_restart_hint": 0,
        "pending_restart_flags": 0,
        "stagnation_checkpoint_limit": 2,
        "reduction_epoch": 14 * stage_count,
        "reduction_valid_mask": reduction_valid_mask,
        "failure_origin": 0,
        "next_expected_restart": 2,
        "schedule_epoch": 26 + 14 * stage_count,
    }.items():
        _store_i32(control, control_offsets, name, value)
    for name, value in {
        "absolute_tolerance": 0.0,
        "relative_tolerance": 1.0e-12,
        "authoritative_tolerance": 1.0,
        "stagnation_relative_tolerance": 0.1,
        "divergence_factor": 2.0,
        "cycle_beta": 1.0,
        "candidate_l2": candidate_l2,
        "candidate_linf": candidate_l2,
        "solution_update_l2": solution_update_l2,
        "committed_x_l2": committed_x_l2,
        "trial_x_l2": trial_x_l2,
        "x_scale_l2": 0.0,
    }.items():
        _store_f64(control, control_offsets, name, value)

    committed_l2 = float(np.sqrt(free_dof_count))
    for name, value in {
        "recurrence_abi_version": 2,
        "active": 1,
        "terminal_status": 0,
        "termination_code": 0,
        "device_error_bits": 0,
        "scheduled_iterations": max_iterations,
        "effective_iterations": 1,
        "scheduled_restarts": maximum_restart_count,
        "effective_restarts": 1,
        "effective_arnoldi_dimension": 1,
        "happy_breakdown_count": 0,
        "stagnation_checkpoint_count": prior_stagnation,
        "false_convergence_count": 0,
        "operator_apply_count": 3,
        "preconditioner_apply_count": 1,
        "restart_dimension": restart_dimension,
    }.items():
        _store_i32(record, record_offsets, name, value)
    for name, value in {
        "rhs_l2": 1.0,
        "rhs_linf": 1.0,
        "solver_tolerance_l2": 1.0,
        "authoritative_tolerance_scaled_linf": 1.0,
        "initial_residual_l2": 1.0,
        "final_residual_l2": committed_l2,
        "final_residual_linf": 1.0,
        "final_scaled_residual": 1.0,
        "previous_checkpoint_residual_l2": 1.0,
        "solution_update_l2": 0.0,
        "solution_scale_l2": 0.0,
        "estimated_residual_l2": 0.5,
        "arnoldi_work_l2": 1.0,
        "arnoldi_breakdown_threshold": 0.0,
        "triangular_scale": 1.0,
    }.items():
        _store_f64(record, record_offsets, name, value)

    host_inputs = {
        "reduced_state": np.zeros(free_dof_count, dtype="<f8"),
        "reduced_load": np.zeros(free_dof_count, dtype="<f8"),
        "inverse_diagonal": np.ones(free_dof_count, dtype="<f8"),
        "solution_x": committed_solution,
        "true_residual": committed_residual,
        "work_w": trial_solution,
        "basis_v": basis_v,
        "basis_z": basis_z,
        "dense": dense,
        "control": control,
        "record": record,
    }
    host_outputs = {
        "solution_x": np.empty_like(committed_solution),
        "true_residual": np.empty_like(committed_residual),
        "control": np.empty_like(control),
        "record": np.empty_like(record),
    }
    device: dict[str, ctypes.c_void_p] = {}
    try:
        execution.open_stream()
        stream = execution.stream
        for name, host in host_inputs.items():
            device[name] = execution.allocate_and_upload(name, host)
        rows = first_column_checkpoint_transaction_launches_v2(
            free_dof_count,
            restart_dimension,
        )
        for row in rows:
            preflight_row = row.name == "PREFLIGHT_COMMIT_SOURCE_COLUMN0"
            if checkpoint_case == "skip_preflight" and preflight_row:
                continue
            repetitions = (
                2 if checkpoint_case == "duplicate_preflight" and preflight_row else 1
            )
            for _ in range(repetitions):
                if row.submission_kind == "control":
                    assert row.row_index == -1
                    assert row.pass_index == -1
                    kernel.launch_control(
                        stream,
                        row.mode,
                        row.expected_schedule_epoch,
                        row.expected_restart,
                        row.expected_column,
                        row.row_index,
                        row.pass_index,
                        free_dof_count,
                        restart_dimension,
                        max_iterations,
                        maximum_restart_count,
                        2,
                        0.0,
                        1.0e-12,
                        1.0,
                        0.1,
                        2.0,
                        device["dense"],
                        device["control"],
                        device["record"],
                    )
                else:
                    assert row.submission_kind == "vector"
                    assert row.vector_gate is not None
                    assert row.logical_index == restart_dimension
                    kernel.launch_vector(
                        stream,
                        row.mode,
                        row.vector_gate,
                        row.expected_schedule_epoch,
                        row.expected_restart,
                        row.expected_column,
                        free_dof_count,
                        row.logical_index,
                        device["reduced_state"],
                        device["reduced_load"],
                        device["inverse_diagonal"],
                        device["solution_x"],
                        device["true_residual"],
                        device["work_w"],
                        device["basis_v"],
                        device["basis_z"],
                        device["dense"],
                        device["control"],
                        device["record"],
                    )
                    if checkpoint_case == "strict_divergence" and preflight_row:
                        legacy_preflight_control = np.empty_like(host_inputs["control"])
                        execution.enqueue_download(
                            "legacy_preflight_control",
                            device["control"],
                            legacy_preflight_control,
                        )
                        execution.observe_fence_and_acknowledge()
                        legacy_payload = legacy_preflight_control.tobytes()
                        assert (
                            _i32(
                                legacy_payload,
                                control_offsets,
                                "predecessor_validation_state",
                            )
                            == control_abi["predecessor_validation_state_codes"][
                                "commit_preflighted"
                            ]
                        )
                        assert (
                            _i32(
                                legacy_payload,
                                control_offsets,
                                "predecessor_mask_snapshot",
                            )
                            == 0
                        )
                        assert (
                            _i32(
                                legacy_payload,
                                control_offsets,
                                "predecessor_reduction_epoch_snapshot",
                            )
                            == 0
                        )
                        assert (
                            _i32(
                                legacy_payload,
                                control_offsets,
                                "schedule_epoch",
                            )
                            == row.expected_schedule_epoch
                        )
        for name, host in host_outputs.items():
            execution.enqueue_download(name, device[name], host)
        execution.observe_fence_and_acknowledge()

        control_payload = host_outputs["control"].tobytes()
        record_payload = host_outputs["record"].tobytes()
        failure = checkpoint_case in {
            "x_scale_overflow",
            "invalid_commit_sources",
            "duplicate_preflight",
            "skip_preflight",
        }
        committed = checkpoint_case in {
            "unhappy_invariant",
            "strict_divergence",
            "stagnation_limit",
        }
        np.testing.assert_array_equal(
            host_outputs["solution_x"],
            trial_solution if committed else committed_solution,
        )
        np.testing.assert_array_equal(
            host_outputs["true_residual"],
            candidate_residual if committed else committed_residual,
        )
        if checkpoint_case in {
            "early_false_convergence",
            "invalid_commit_sources",
            "duplicate_preflight",
            "skip_preflight",
        }:
            assert host_outputs["solution_x"].tobytes() == (
                committed_solution.tobytes()
            )
            assert host_outputs["true_residual"].tobytes() == (
                committed_residual.tobytes()
            )
        expected_status_code = {
            "early_false_convergence": 0,
            "unhappy_invariant": 5,
            "strict_divergence": 4,
            "stagnation_limit": 3,
            "x_scale_overflow": 6,
            "invalid_commit_sources": 6,
            "duplicate_preflight": 6,
            "skip_preflight": 6,
        }[checkpoint_case]
        expected_termination_code = {
            "early_false_convergence": 0,
            "unhappy_invariant": 31,
            "strict_divergence": 21,
            "stagnation_limit": 20,
            "x_scale_overflow": 47,
            "invalid_commit_sources": 47,
            "duplicate_preflight": 40,
            "skip_preflight": 40,
        }[checkpoint_case]
        assert (
            _i32(record_payload, record_offsets, "terminal_status")
            == expected_status_code
        )
        assert (
            _i32(record_payload, record_offsets, "termination_code")
            == expected_termination_code
        )
        assert _i32(record_payload, record_offsets, "active") == int(
            checkpoint_case == "early_false_convergence"
        )
        expected_error_bits = {
            "x_scale_overflow": 8,
            "invalid_commit_sources": 4,
            "duplicate_preflight": 1,
            "skip_preflight": 1,
        }.get(checkpoint_case, 0)
        assert (
            _i32(record_payload, record_offsets, "device_error_bits")
            == expected_error_bits
        )
        vector_failure = checkpoint_case in {
            "invalid_commit_sources",
            "duplicate_preflight",
            "skip_preflight",
        }
        assert _i32(control_payload, control_offsets, "failure_origin") == (
            2 if vector_failure else int(failure)
        )
        assert _i32(control_payload, control_offsets, "schedule_epoch") == (
            27 + 14 * stage_count if failure else 29 + 14 * stage_count
        )
        assert _i32(control_payload, control_offsets, "phase") == (
            phase_codes["failed"]
            if failure
            else (
                phase_codes["arnoldi"]
                if checkpoint_case == "early_false_convergence"
                else phase_codes["terminal"]
            )
        )
        if not failure:
            assert (
                _i32(
                    control_payload,
                    control_offsets,
                    "predecessor_validation_state",
                )
                == control_abi["predecessor_validation_state_codes"]["empty"]
            )
            assert (
                _i32(
                    control_payload,
                    control_offsets,
                    "predecessor_mask_snapshot",
                )
                == 0
            )
            assert (
                _i32(
                    control_payload,
                    control_offsets,
                    "predecessor_reduction_epoch_snapshot",
                )
                == 0
            )
        assert _i32(record_payload, record_offsets, "false_convergence_count") == int(
            checkpoint_case == "early_false_convergence"
        )
        assert _i32(
            record_payload,
            record_offsets,
            "stagnation_checkpoint_count",
        ) == (2 if checkpoint_case == "stagnation_limit" else 0)
        restart_payload = record_payload[
            record_abi["header_bytes"] : record_abi["header_bytes"]
            + record_abi["restart_bytes"]
        ]
        expected_row_flags = {
            "early_false_convergence": 0,
            "unhappy_invariant": 17,
            "strict_divergence": 129,
            "stagnation_limit": 97,
            "x_scale_overflow": 0,
            "invalid_commit_sources": 0,
            "duplicate_preflight": 0,
            "skip_preflight": 0,
        }[checkpoint_case]
        if committed:
            assert _i32(restart_payload, restart_offsets, "restart_index") == 1
            assert _i32(restart_payload, restart_offsets, "flags") == (
                expected_row_flags
            )
        else:
            assert restart_payload == bytes(record_abi["restart_bytes"])
    finally:
        execution.close()


def test_native_gfx1030_duplicate_reduction_epoch_fails_without_hang() -> None:
    execution = _open_native_execution()
    kernel = execution.kernel
    free_dof_count = 513
    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    interface_abi = hip_fgmres_recurrence_kernel_abi_payload_v2()
    control_modes = control_abi["control_mode_codes"]
    vector_modes = control_abi["vector_mode_codes"]
    vector_gates = control_abi["vector_gate_codes"]
    first_stage = initial_reduction_launches_v2(free_dof_count)[0]
    assert first_stage.metric == "rhs_l2"
    assert first_stage.expected_schedule_epoch == 2
    assert first_stage.expected_reduction_epoch == 0
    assert first_stage.value_count == 513
    assert first_stage.output_count == 2
    assert first_stage.final_stage is False
    assert first_stage.reduction_target == control_abi["reduction_target_codes"]["NONE"]

    record_bytes = solve_record_byte_length_v2(0)
    indices = np.arange(free_dof_count, dtype="<f8")
    host_inputs: dict[str, np.ndarray] = {
        "reduced_state": np.ascontiguousarray(
            (indices % 7.0 - 3.0) * 0.125,
            dtype="<f8",
        ),
        "reduced_load": np.ascontiguousarray(
            (indices % 11.0 - 5.0) * 0.5 + 0.25,
            dtype="<f8",
        ),
        "inverse_diagonal": np.ones(free_dof_count, dtype="<f8"),
        "solution_x": np.zeros(free_dof_count, dtype="<f8"),
        "true_residual": np.zeros(free_dof_count, dtype="<f8"),
        "work_w": np.zeros(free_dof_count, dtype="<f8"),
        "basis_v": np.zeros(free_dof_count, dtype="<f8"),
        "basis_z": np.zeros(free_dof_count, dtype="<f8"),
        "dense": np.zeros(1, dtype="<f8"),
        "reduction_input": np.zeros(4, dtype="<f8"),
        "reduction_output": np.zeros(4, dtype="<f8"),
        "control": np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1"),
        "record": np.zeros(record_bytes, dtype="u1"),
    }
    host_control = np.empty(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1")
    host_record = np.empty(record_bytes, dtype="u1")
    device: dict[str, ctypes.c_void_p] = {}
    try:
        execution.open_stream()
        stream = execution.stream
        for name, host in host_inputs.items():
            device[name] = execution.allocate_and_upload(name, host)

        kernel.launch_control(
            stream,
            control_modes["INIT"],
            0,
            -1,
            -1,
            -1,
            -1,
            free_dof_count,
            4,
            0,
            0,
            2,
            0.0,
            1.0e-12,
            1.0e-12,
            1.0e-8,
            1.0e8,
            device["dense"],
            device["control"],
            device["record"],
        )
        kernel.launch_vector(
            stream,
            vector_modes["COPY_INITIAL_X"],
            vector_gates["ACTIVE"],
            1,
            -1,
            -1,
            free_dof_count,
            0,
            device["reduced_state"],
            device["reduced_load"],
            device["inverse_diagonal"],
            device["solution_x"],
            device["true_residual"],
            device["work_w"],
            device["basis_v"],
            device["basis_z"],
            device["dense"],
            device["control"],
            device["record"],
        )

        def launch_first_stage() -> None:
            kernel.launch_reduction(
                stream,
                first_stage.reduction_mode,
                first_stage.reduction_target,
                first_stage.expected_schedule_epoch,
                -1,
                -1,
                first_stage.expected_reduction_epoch,
                first_stage.value_count,
                0,
                device["reduced_load"],
                device["solution_x"],
                device["true_residual"],
                device["work_w"],
                device["basis_v"],
                device["reduction_input"],
                device["reduction_output"],
                device["control"],
                device["record"],
            )

        launch_first_stage()
        launch_first_stage()
        assert kernel.pending_stream_count == 1
        execution.enqueue_download("control", device["control"], host_control)
        execution.enqueue_download("record", device["record"], host_record)
        execution.observe_fence_and_acknowledge()
        assert kernel.pending_stream_count == 0

        control_payload = host_control.tobytes()
        record_payload = host_record.tobytes()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        assert _i32(record_payload, record_offsets, "active") == 0
        assert (
            _i32(
                record_payload,
                record_offsets,
                "terminal_status",
            )
            == record_abi["terminal_status_codes"]["numerical_failure"]
        )
        assert (
            _i32(
                record_payload,
                record_offsets,
                "termination_code",
            )
            == record_abi["termination_codes"]["invalid_input_or_control"]
        )
        assert (
            _i32(
                record_payload,
                record_offsets,
                "device_error_bits",
            )
            == interface_abi["device_error_masks"]["invalid_control_or_geometry"]
        )
        assert (
            _i32(control_payload, control_offsets, "phase")
            == control_abi["phase_codes"]["failed"]
        )
        assert (
            _i32(
                control_payload,
                control_offsets,
                "failure_origin",
            )
            == control_abi["failure_origin_codes"]["reduction"]
        )
        assert _i32(control_payload, control_offsets, "schedule_epoch") == 3
        assert _i32(control_payload, control_offsets, "reduction_epoch") == 1
    finally:
        execution.close()
