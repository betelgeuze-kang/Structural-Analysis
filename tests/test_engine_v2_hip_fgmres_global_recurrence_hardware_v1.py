from __future__ import annotations

import ctypes
import math
from typing import Any

import numpy as np

from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_schedule_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (
    solve_record_byte_length_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    _fgmres_core,
    compile_fgmres_policy_v1,
)
from tests.test_engine_v2_hip_fgmres_initial_hardware_v2 import (
    _f64,
    _field_offsets,
    _i32,
    _open_native_execution,
)


def _lower_bidiagonal_csr(
    free_dof_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return a positive-diagonal operator that is not solved in five steps."""

    row_ptr = np.empty(free_dof_count + 1, dtype="<i4")
    row_ptr[0] = 0
    row_ptr[1:] = 2 * np.arange(1, free_dof_count + 1, dtype="<i4") - 1
    column_indices = np.empty(2 * free_dof_count - 1, dtype="<i4")
    values = np.empty(2 * free_dof_count - 1, dtype="<f8")
    column_indices[0] = 0
    values[0] = 1.0
    for row in range(1, free_dof_count):
        offset = 2 * row - 1
        column_indices[offset : offset + 2] = (row - 1, row)
        values[offset : offset + 2] = (0.5, 1.0)
    return row_ptr, column_indices, values


def _csr_matvec(
    row_ptr: np.ndarray,
    column_indices: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    result = np.empty(vector.size, dtype="<f8")
    for row in range(vector.size):
        start = int(row_ptr[row])
        end = int(row_ptr[row + 1])
        result[row] = np.dot(
            values[start:end],
            vector[column_indices[start:end]],
        )
    result[result == 0.0] = 0.0
    return result


def _dispatch_global_program(
    *,
    execution: Any,
    plan: Any,
    free_dof_count: int,
    nonzero_count: int,
    absolute_tolerance: float,
    relative_tolerance: float,
    authoritative_tolerance: float,
    stagnation_relative_tolerance: float,
    divergence_factor: float,
    device: dict[str, ctypes.c_void_p],
) -> dict[str, int]:
    """Submit the immutable host program without a live-state read or branch."""

    kernel = execution.kernel
    stream = execution.stream
    tree_stages: dict[str, int] = {}
    counts = {"control": 0, "vector": 0, "spmv": 0, "reduction": 0}

    for row in plan.launches:
        counts[row.submission_kind] += 1
        if row.submission_kind == "control":
            kernel.launch_control(
                stream,
                row.mode,
                row.expected_schedule_epoch,
                row.expected_restart,
                row.expected_column,
                -1 if row.row_index is None else row.row_index,
                -1 if row.pass_index is None else row.pass_index,
                free_dof_count,
                plan.restart_dimension,
                plan.max_iterations,
                plan.maximum_restart_count,
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
        elif row.submission_kind == "vector":
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
            assert row.submission_kind == "reduction"
            assert row.reduction_target is not None
            assert row.expected_reduction_epoch is not None
            assert row.value_count is not None
            assert row.logical_index is not None
            assert row.reduction_tree_id is not None
            stage = tree_stages.get(row.reduction_tree_id, 0)
            reduction_input = (
                device["reduction_ping"] if stage % 2 == 0 else device["reduction_pong"]
            )
            reduction_output = (
                device["reduction_pong"] if stage % 2 == 0 else device["reduction_ping"]
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
            tree_stages[row.reduction_tree_id] = stage + 1

    return counts


def test_native_gfx1030_global_recurrence_exhaustion_matches_cpu_oracle() -> None:
    """Run initial + all restart slots + guard with one terminal fence."""

    execution = _open_native_execution()
    free_dof_count = 513
    restart_dimension = 2
    max_iterations = 5
    absolute_tolerance = 0.0
    relative_tolerance = 1.0e-30
    authoritative_tolerance = 1.0e-30
    stagnation_relative_tolerance = 1.0e-8
    divergence_factor = 1.0e8
    plan = compile_hip_fgmres_global_schedule_plan_v1(
        free_dof_count,
        restart_dimension,
        max_iterations,
    )
    assert plan.maximum_restart_count == 3
    assert plan.reduction_stage_outputs == (2, 1)
    assert plan.final_guard_launch is not None
    assert len(plan.launches) == 298

    row_ptr, column_indices, values = _lower_bidiagonal_csr(free_dof_count)
    initial_solution = np.zeros(free_dof_count, dtype="<f8")
    rhs = np.ones(free_dof_count, dtype="<f8")
    inverse_diagonal = np.ones(free_dof_count, dtype="<f8")
    policy = compile_fgmres_policy_v1(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        stagnation_checkpoint_limit=2,
        stagnation_relative_tolerance=stagnation_relative_tolerance,
        divergence_factor=divergence_factor,
    )
    oracle = _fgmres_core(
        matvec=lambda vector: _csr_matvec(
            row_ptr,
            column_indices,
            values,
            vector,
        ),
        rhs=rhs,
        initial_solution=initial_solution,
        inverse_diagonal=inverse_diagonal,
        policy=policy,
        authoritative_tolerance=authoritative_tolerance,
    )
    assert oracle.status == "max_iterations"
    assert oracle.termination_code == "max_iterations_exhausted"
    assert oracle.iteration_count == 5
    assert oracle.restart_count == 3
    assert len(oracle.history) == 3

    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    dense_count = restart_dimension**2 + 5 * restart_dimension + 1
    record_bytes = solve_record_byte_length_v2(plan.maximum_restart_count)
    reduction_scratch_count = 2 * plan.reduction_stage_outputs[0]
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
        "reduction_ping": np.zeros(reduction_scratch_count, dtype="<f8"),
        "reduction_pong": np.zeros(reduction_scratch_count, dtype="<f8"),
        "control": np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1"),
        "record": np.zeros(record_bytes, dtype="u1"),
    }
    host_outputs = {
        "solution_x": np.empty_like(host_inputs["solution_x"]),
        "true_residual": np.empty_like(host_inputs["true_residual"]),
        "control": np.empty_like(host_inputs["control"]),
        "record": np.empty_like(host_inputs["record"]),
    }
    device: dict[str, ctypes.c_void_p] = {}
    download_count = 0
    fence_count = 0

    try:
        execution.open_stream()
        for name, host in host_inputs.items():
            device[name] = execution.allocate_and_upload(name, host)

        launch_counts = _dispatch_global_program(
            execution=execution,
            plan=plan,
            free_dof_count=free_dof_count,
            nonzero_count=values.size,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            authoritative_tolerance=authoritative_tolerance,
            stagnation_relative_tolerance=stagnation_relative_tolerance,
            divergence_factor=divergence_factor,
            device=device,
        )
        assert sum(launch_counts.values()) == len(plan.launches)
        assert launch_counts["control"] > 0
        assert launch_counts["vector"] > 0
        assert launch_counts["spmv"] > 0
        assert launch_counts["reduction"] > 0
        assert download_count == 0
        assert fence_count == 0
        assert execution.fence_observed is False
        assert execution.completion_acknowledged is False
        assert execution.kernel.pending_stream_count == 1

        for name, host in host_outputs.items():
            execution.enqueue_download(name, device[name], host)
            download_count += 1
        execution.observe_fence_and_acknowledge()
        fence_count += 1
        assert download_count == len(host_outputs)
        assert fence_count == 1
        assert execution.kernel.pending_stream_count == 0

        np.testing.assert_allclose(
            host_outputs["solution_x"],
            oracle.solution,
            rtol=2.0e-13,
            atol=2.0e-15,
        )
        np.testing.assert_allclose(
            host_outputs["true_residual"],
            oracle.residual,
            rtol=2.0e-13,
            atol=2.0e-15,
        )
        replayed_residual = rhs - _csr_matvec(
            row_ptr,
            column_indices,
            values,
            host_outputs["solution_x"],
        )
        np.testing.assert_allclose(
            host_outputs["true_residual"],
            replayed_residual,
            rtol=2.0e-15,
            atol=2.0e-15,
        )

        control_payload = host_outputs["control"].tobytes()
        record_payload = host_outputs["record"].tobytes()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        assert (
            _i32(control_payload, control_offsets, "phase")
            == control_abi["phase_codes"]["terminal"]
        )
        assert _i32(control_payload, control_offsets, "restart_index") == 3
        assert _i32(control_payload, control_offsets, "column_index") == 0
        assert _i32(control_payload, control_offsets, "schedule_epoch") == 237
        assert _i32(control_payload, control_offsets, "reduction_epoch") == 116
        for name in control_abi["transient_zero_fields"]:
            assert _i32(control_payload, control_offsets, name) == 0

        assert _i32(record_payload, record_offsets, "active") == 0
        assert (
            _i32(record_payload, record_offsets, "terminal_status")
            == record_abi["terminal_status_codes"]["max_iterations"]
        )
        assert (
            _i32(record_payload, record_offsets, "termination_code")
            == record_abi["termination_codes"]["max_iterations_exhausted"]
        )
        assert _i32(record_payload, record_offsets, "device_error_bits") == 0
        assert _i32(record_payload, record_offsets, "scheduled_iterations") == 5
        assert _i32(record_payload, record_offsets, "effective_iterations") == 5
        assert _i32(record_payload, record_offsets, "scheduled_restarts") == 3
        assert _i32(record_payload, record_offsets, "effective_restarts") == 3
        assert _i32(record_payload, record_offsets, "effective_arnoldi_dimension") == 1
        assert (
            _i32(record_payload, record_offsets, "operator_apply_count")
            == oracle.operator_apply_count
        )
        assert (
            _i32(record_payload, record_offsets, "preconditioner_apply_count")
            == oracle.preconditioner_apply_count
        )
        np.testing.assert_allclose(
            _f64(record_payload, record_offsets, "final_residual_l2"),
            math.sqrt(float(np.dot(oracle.residual, oracle.residual))),
            rtol=2.0e-13,
            atol=0.0,
        )
        np.testing.assert_allclose(
            _f64(record_payload, record_offsets, "final_residual_linf"),
            float(np.max(np.abs(oracle.residual))),
            rtol=2.0e-13,
            atol=0.0,
        )

        restart_offsets = _field_offsets(record_abi["restart_fields"])
        restart_header_bytes = int(record_abi["header_bytes"])
        restart_bytes = int(record_abi["restart_bytes"])
        for index, expected in enumerate(oracle.history):
            start = restart_header_bytes + index * restart_bytes
            payload = record_payload[start : start + restart_bytes]
            assert _i32(payload, restart_offsets, "restart_index") == index + 1
            assert (
                _i32(payload, restart_offsets, "start_iteration")
                == expected.start_iteration
            )
            assert (
                _i32(payload, restart_offsets, "end_iteration")
                == expected.end_iteration
            )
            assert (
                _i32(payload, restart_offsets, "arnoldi_step_count")
                == expected.arnoldi_step_count
            )
            assert (
                _i32(payload, restart_offsets, "reorthogonalization_count")
                == expected.reorthogonalization_count
            )
            assert (
                _i32(payload, restart_offsets, "termination_hint")
                == record_abi["restart_hint_codes"][expected.termination_hint]
            )
            np.testing.assert_allclose(
                _f64(payload, restart_offsets, "true_residual_l2"),
                expected.true_residual_l2,
                rtol=2.0e-13,
                atol=0.0,
            )
            np.testing.assert_allclose(
                _f64(payload, restart_offsets, "true_residual_linf"),
                expected.true_residual_linf,
                rtol=2.0e-13,
                atol=0.0,
            )
    finally:
        execution.close()


def test_native_gfx1030_global_recurrence_early_terminal_padding_is_no_op() -> None:
    """Keep the first-column terminal epochs across every remaining host row."""

    execution = _open_native_execution()
    free_dof_count = 513
    restart_dimension = 2
    max_iterations = 5
    absolute_tolerance = 0.0
    relative_tolerance = 1.0e-15
    authoritative_tolerance = 1.0e-15
    stagnation_relative_tolerance = 1.0e-8
    divergence_factor = 1.0e8
    plan = compile_hip_fgmres_global_schedule_plan_v1(
        free_dof_count,
        restart_dimension,
        max_iterations,
    )

    row_ptr = np.arange(free_dof_count + 1, dtype="<i4")
    column_indices = np.arange(free_dof_count, dtype="<i4")
    values = np.ones(free_dof_count, dtype="<f8")
    initial_solution = np.zeros(free_dof_count, dtype="<f8")
    rhs = np.ones(free_dof_count, dtype="<f8")
    inverse_diagonal = np.ones(free_dof_count, dtype="<f8")
    policy = compile_fgmres_policy_v1(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        stagnation_checkpoint_limit=2,
        stagnation_relative_tolerance=stagnation_relative_tolerance,
        divergence_factor=divergence_factor,
    )
    oracle = _fgmres_core(
        matvec=lambda vector: vector.copy(),
        rhs=rhs,
        initial_solution=initial_solution,
        inverse_diagonal=inverse_diagonal,
        policy=policy,
        authoritative_tolerance=authoritative_tolerance,
    )
    assert oracle.status == "converged"
    assert oracle.termination_code == "converged_happy_breakdown"
    assert oracle.iteration_count == 1
    assert oracle.restart_count == 1

    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    dense_count = restart_dimension**2 + 5 * restart_dimension + 1
    record_bytes = solve_record_byte_length_v2(plan.maximum_restart_count)
    reduction_scratch_count = 2 * plan.reduction_stage_outputs[0]
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
        "reduction_ping": np.zeros(reduction_scratch_count, dtype="<f8"),
        "reduction_pong": np.zeros(reduction_scratch_count, dtype="<f8"),
        "control": np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1"),
        "record": np.zeros(record_bytes, dtype="u1"),
    }
    host_outputs = {
        "solution_x": np.empty_like(host_inputs["solution_x"]),
        "true_residual": np.empty_like(host_inputs["true_residual"]),
        "control": np.empty_like(host_inputs["control"]),
        "record": np.empty_like(host_inputs["record"]),
    }
    device: dict[str, ctypes.c_void_p] = {}
    download_count = 0
    fence_count = 0

    try:
        execution.open_stream()
        for name, host in host_inputs.items():
            device[name] = execution.allocate_and_upload(name, host)

        launch_counts = _dispatch_global_program(
            execution=execution,
            plan=plan,
            free_dof_count=free_dof_count,
            nonzero_count=values.size,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            authoritative_tolerance=authoritative_tolerance,
            stagnation_relative_tolerance=stagnation_relative_tolerance,
            divergence_factor=divergence_factor,
            device=device,
        )
        assert sum(launch_counts.values()) == 298
        assert download_count == 0
        assert fence_count == 0
        assert execution.kernel.pending_stream_count == 1

        for name, host in host_outputs.items():
            execution.enqueue_download(name, device[name], host)
            download_count += 1
        execution.observe_fence_and_acknowledge()
        fence_count += 1
        assert download_count == len(host_outputs)
        assert fence_count == 1
        assert execution.kernel.pending_stream_count == 0

        np.testing.assert_array_equal(host_outputs["solution_x"], oracle.solution)
        np.testing.assert_array_equal(host_outputs["true_residual"], oracle.residual)
        control_payload = host_outputs["control"].tobytes()
        record_payload = host_outputs["record"].tobytes()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        assert (
            _i32(control_payload, control_offsets, "phase")
            == control_abi["phase_codes"]["terminal"]
        )
        assert _i32(control_payload, control_offsets, "restart_index") == 1
        assert _i32(control_payload, control_offsets, "column_index") == 0
        assert _i32(control_payload, control_offsets, "schedule_epoch") == 57
        assert _i32(control_payload, control_offsets, "reduction_epoch") == 28
        assert _i32(record_payload, record_offsets, "active") == 0
        assert (
            _i32(record_payload, record_offsets, "terminal_status")
            == record_abi["terminal_status_codes"]["converged"]
        )
        assert (
            _i32(record_payload, record_offsets, "termination_code")
            == record_abi["termination_codes"]["converged_happy_breakdown"]
        )
        assert _i32(record_payload, record_offsets, "device_error_bits") == 0
        assert _i32(record_payload, record_offsets, "effective_iterations") == 1
        assert _i32(record_payload, record_offsets, "effective_restarts") == 1
        assert (
            _i32(record_payload, record_offsets, "operator_apply_count")
            == oracle.operator_apply_count
        )
        assert (
            _i32(record_payload, record_offsets, "preconditioner_apply_count")
            == oracle.preconditioner_apply_count
        )
    finally:
        execution.close()
