from __future__ import annotations

import ctypes

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_schedule_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (
    solve_record_byte_length_v2,
)
from tests.test_engine_v2_hip_fgmres_initial_hardware_v2 import (
    _field_offsets,
    _i32,
    _open_native_execution,
    _store_f64,
    _store_i32,
)


FREE_DOF_COUNT = 513
RESTART_DIMENSION = 2
MAX_ITERATIONS = 4
MAXIMUM_RESTART_COUNT = 2
STAGNATION_CHECKPOINT_LIMIT = 2
ABSOLUTE_TOLERANCE = 0.0
RELATIVE_TOLERANCE = 1.0e-12
AUTHORITATIVE_TOLERANCE = 1.0e-12
STAGNATION_RELATIVE_TOLERANCE = 1.0e-8
DIVERGENCE_FACTOR = 1.0e8


def _final_guard_prestate(*, malformed: bool) -> tuple[np.ndarray, np.ndarray]:
    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    control_offsets = _field_offsets(control_abi["fields"])
    record_offsets = _field_offsets(record_abi["header_fields"])
    restart_offsets = _field_offsets(record_abi["restart_fields"])

    control = np.zeros(HIP_FGMRES_CONTROL_STATE_BYTES_V2, dtype="u1")
    record = np.zeros(solve_record_byte_length_v2(MAXIMUM_RESTART_COUNT), dtype="u1")

    control_i32 = {
        "control_abi_version": 2,
        "phase": control_abi["phase_codes"]["arnoldi"],
        "free_dof_count": FREE_DOF_COUNT,
        "restart_dimension": RESTART_DIMENSION,
        "max_iterations": MAX_ITERATIONS,
        "maximum_restart_count": MAXIMUM_RESTART_COUNT,
        "restart_index": MAXIMUM_RESTART_COUNT,
        "cycle_start_iteration": 2,
        "cycle_width": RESTART_DIMENSION,
        "column_index": RESTART_DIMENSION - 1,
        "arnoldi_step_count": RESTART_DIMENSION,
        "reorthogonalization_count": 0,
        "dgks_reorth_required": 0,
        "invariant_breakdown": 0,
        "candidate_required": 0,
        "candidate_reason_bits": 0,
        "triangular_breakdown": 0,
        "commit_required": 0,
        "continuation_required": 0,
        "pending_terminal_status": 0,
        "pending_termination_code": 0,
        "pending_restart_hint": 0,
        "pending_restart_flags": 0,
        "stagnation_checkpoint_limit": STAGNATION_CHECKPOINT_LIMIT,
        "reduction_epoch": 96,
        "reduction_valid_mask": 0,
        "failure_origin": control_abi["failure_origin_codes"]["none"],
        "next_expected_restart": MAXIMUM_RESTART_COUNT + 1,
        "schedule_epoch": 195,
        "predecessor_validation_state": 0,
        "predecessor_mask_snapshot": 0,
        "predecessor_reduction_epoch_snapshot": 0,
    }
    for name, value in control_i32.items():
        _store_i32(control, control_offsets, name, value)

    control_f64 = {
        "absolute_tolerance": ABSOLUTE_TOLERANCE,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "authoritative_tolerance": AUTHORITATIVE_TOLERANCE,
        "stagnation_relative_tolerance": STAGNATION_RELATIVE_TOLERANCE,
        "divergence_factor": DIVERGENCE_FACTOR,
        "cycle_beta": 0.25,
    }
    for name, value in control_f64.items():
        _store_f64(control, control_offsets, name, value)

    record_i32 = {
        "recurrence_abi_version": 2,
        "active": 1,
        "terminal_status": record_abi["terminal_status_codes"]["not_terminal"],
        "termination_code": record_abi["termination_codes"]["none"],
        "device_error_bits": 0,
        "scheduled_iterations": MAX_ITERATIONS,
        "effective_iterations": MAX_ITERATIONS,
        "scheduled_restarts": MAXIMUM_RESTART_COUNT,
        "effective_restarts": MAXIMUM_RESTART_COUNT,
        "effective_arnoldi_dimension": RESTART_DIMENSION,
        "happy_breakdown_count": 0,
        "stagnation_checkpoint_count": 0,
        "false_convergence_count": 0,
        "operator_apply_count": 8 if malformed else 7,
        "preconditioner_apply_count": MAX_ITERATIONS,
        "restart_dimension": RESTART_DIMENSION,
    }
    for name, value in record_i32.items():
        _store_i32(record, record_offsets, name, value)

    final_metrics = {
        "final_residual_l2": 0.25,
        "final_residual_linf": 0.125,
        "final_scaled_residual": 0.5,
        "solution_update_l2": 0.03125,
        "estimated_residual_l2": 0.375,
    }
    for name, value in final_metrics.items():
        _store_f64(record, record_offsets, name, value)

    restart_base = int(record_abi["header_bytes"]) + (MAXIMUM_RESTART_COUNT - 1) * int(
        record_abi["restart_bytes"]
    )
    final_restart = record[
        restart_base : restart_base + int(record_abi["restart_bytes"])
    ]
    restart_i32 = {
        "restart_index": MAXIMUM_RESTART_COUNT,
        "start_iteration": 2,
        "end_iteration": MAX_ITERATIONS,
        "arnoldi_step_count": RESTART_DIMENSION,
        "reorthogonalization_count": 0,
        "termination_hint": record_abi["restart_hint_codes"]["restart_completed"],
        "flags": 1 << record_abi["restart_flag_bits"]["true_residual_replayed"],
        "reserved_i32_0": 0,
    }
    for name, value in restart_i32.items():
        _store_i32(final_restart, restart_offsets, name, value)
    restart_f64 = {
        "estimated_residual_l2": final_metrics["estimated_residual_l2"],
        "true_residual_l2": final_metrics["final_residual_l2"],
        "true_residual_linf": final_metrics["final_residual_linf"],
        "scaled_true_residual": final_metrics["final_scaled_residual"],
        "solution_update_l2": final_metrics["solution_update_l2"],
    }
    for name, value in restart_f64.items():
        _store_f64(final_restart, restart_offsets, name, value)

    return control, record


def _expected_poststate(
    control: np.ndarray,
    record: np.ndarray,
    *,
    malformed: bool,
) -> tuple[np.ndarray, np.ndarray]:
    control_abi = hip_fgmres_control_state_abi_payload_v2()
    record_abi = hip_fgmres_solve_record_abi_payload_v2()
    control_offsets = _field_offsets(control_abi["fields"])
    record_offsets = _field_offsets(record_abi["header_fields"])
    expected_control = control.copy()
    expected_record = record.copy()

    _store_i32(expected_record, record_offsets, "active", 0)
    if malformed:
        _store_i32(
            expected_control,
            control_offsets,
            "phase",
            control_abi["phase_codes"]["failed"],
        )
        _store_i32(
            expected_control,
            control_offsets,
            "failure_origin",
            control_abi["failure_origin_codes"]["control"],
        )
        _store_i32(
            expected_control,
            control_offsets,
            "pending_terminal_status",
            record_abi["terminal_status_codes"]["numerical_failure"],
        )
        _store_i32(
            expected_control,
            control_offsets,
            "pending_termination_code",
            record_abi["termination_codes"]["restart_state_failed"],
        )
        _store_i32(
            expected_record,
            record_offsets,
            "terminal_status",
            record_abi["terminal_status_codes"]["numerical_failure"],
        )
        _store_i32(
            expected_record,
            record_offsets,
            "termination_code",
            record_abi["termination_codes"]["restart_state_failed"],
        )
        _store_i32(expected_record, record_offsets, "device_error_bits", 1)
    else:
        _store_i32(
            expected_control,
            control_offsets,
            "phase",
            control_abi["phase_codes"]["terminal"],
        )
        _store_i32(expected_control, control_offsets, "schedule_epoch", 196)
        _store_i32(
            expected_record,
            record_offsets,
            "terminal_status",
            record_abi["terminal_status_codes"]["max_iterations"],
        )
        _store_i32(
            expected_record,
            record_offsets,
            "termination_code",
            record_abi["termination_codes"]["max_iterations_exhausted"],
        )
    return expected_control, expected_record


@pytest.mark.parametrize("malformed", (False, True), ids=("valid", "malformed"))
def test_native_gfx1030_final_guard_active_fallthrough_is_exact_and_fail_closed(
    malformed: bool,
) -> None:
    plan = compile_hip_fgmres_global_schedule_plan_v1(
        FREE_DOF_COUNT,
        RESTART_DIMENSION,
        MAX_ITERATIONS,
    )
    guard = plan.final_guard_launch
    assert plan.maximum_restart_count == MAXIMUM_RESTART_COUNT
    assert plan.reduction_stage_outputs == (2, 1)
    assert plan.initial_schedule_end == 15
    assert plan.restart_schedule_stride == 90
    assert plan.restart_reduction_stride == 44
    assert plan.final_schedule_epoch == 195
    assert plan.final_reduction_epoch == 96
    assert plan.schedule_end_epoch == 196
    assert guard is not None
    assert (
        guard.expected_schedule_epoch,
        guard.expected_reduction_epoch,
        guard.expected_restart,
        guard.expected_column,
    ) == (195, 96, MAXIMUM_RESTART_COUNT, RESTART_DIMENSION - 1)

    interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    guard_contract = interface["global_fixed_recurrence_schedule"][
        "final_guard_contract"
    ]
    assert guard_contract["active_valid_behavior"] == (
        "claim_one_schedule_epoch_and_publish_max_iterations"
    )
    assert guard_contract["active_malformed_behavior"] == "fail_closed_code_47"

    control, record = _final_guard_prestate(malformed=malformed)
    expected_control, expected_record = _expected_poststate(
        control,
        record,
        malformed=malformed,
    )
    numeric_poison = {
        # FINAL_GUARD receives only this one-byte nonnumeric-capacity pointer.
        # Any dense access would violate the contract and cross its allocation.
        "dense": np.array([0xA5], dtype="u1"),
        "solution_x": np.array([11.25, -7.5], dtype="<f8"),
        "true_residual": np.array([-13.5, 17.75], dtype="<f8"),
        "basis_v": np.array([19.0, -23.0], dtype="<f8"),
        "basis_z": np.array([-29.0, 31.0], dtype="<f8"),
        "csr_row_ptr": np.array([37, -41], dtype="<i4"),
        "csr_column_indices": np.array([-43, 47], dtype="<i4"),
        "csr_values": np.array([53.5, -59.25], dtype="<f8"),
    }
    poison_bytes = {name: value.tobytes() for name, value in numeric_poison.items()}
    execution = _open_native_execution()
    device: dict[str, ctypes.c_void_p] = {}
    outputs: dict[str, np.ndarray] = {}
    try:
        execution.open_stream()
        for name, host in {
            **numeric_poison,
            "control": control,
            "record": record,
        }.items():
            device[name] = execution.allocate_and_upload(name, host)
            outputs[name] = np.empty_like(host)

        execution.kernel.launch_control(
            execution.stream,
            guard.mode,
            guard.expected_schedule_epoch,
            guard.expected_restart,
            guard.expected_column,
            -1,
            -1,
            FREE_DOF_COUNT,
            RESTART_DIMENSION,
            MAX_ITERATIONS,
            MAXIMUM_RESTART_COUNT,
            STAGNATION_CHECKPOINT_LIMIT,
            ABSOLUTE_TOLERANCE,
            RELATIVE_TOLERANCE,
            AUTHORITATIVE_TOLERANCE,
            STAGNATION_RELATIVE_TOLERANCE,
            DIVERGENCE_FACTOR,
            device["dense"],
            device["control"],
            device["record"],
        )

        for name, host in outputs.items():
            execution.enqueue_download(name, device[name], host)
        execution.observe_fence_and_acknowledge()

        assert outputs["control"].tobytes() == expected_control.tobytes()
        assert outputs["record"].tobytes() == expected_record.tobytes()
        for name, before in poison_bytes.items():
            assert outputs[name].tobytes() == before

        control_offsets = _field_offsets(
            hip_fgmres_control_state_abi_payload_v2()["fields"]
        )
        actual_control = outputs["control"].tobytes()
        assert _i32(actual_control, control_offsets, "reduction_epoch") == 96
        assert _i32(actual_control, control_offsets, "schedule_epoch") == (
            195 if malformed else 196
        )
        assert execution.kernel.pending_stream_count == 0
    finally:
        execution.close()
