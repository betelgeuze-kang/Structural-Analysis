"""HIP-specific allocation and policy plan for a future FGMRES context.

The plan binds one exact sparse ``ExecutionPlanV2``, its independently
validated free-space overlay, and the shared fixed-restart FGMRES policy.  It
describes device buffer extents only: no allocation, transfer, kernel compile,
context lease, recurrence, or convergence observation is performed here.

Runtime-only lineage is intentionally not forged into this compile-time
artifact.  A future execution context must bind the exact latest free-space
apply and acquire an exclusive Krylov-primitive child lease when it opens.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    EXECUTION_PLAN_V2_CAPABILITY_PROFILE,
    EXECUTION_PLAN_V2_SCHEMA_VERSION,
    ExecutionPlanV2,
    ExecutionPlanV2Error,
    _detached_source_snapshot,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceError,
    FgmresPolicyV1,
    compile_fgmres_policy_v1,
    validate_fgmres_policy_v1,
)

from .free_space_plan import (
    HipFreeSpaceOperatorPlanV1,
    HipFreeSpaceOperatorPlanV1Error,
    compile_hip_free_space_operator_plan_v1,
    validate_hip_free_space_operator_plan_v1,
)


HIP_FGMRES_PLAN_V1_SCHEMA_VERSION = "structural-analysis-hip-fgmres-plan.v1"
HIP_FGMRES_PLAN_V1_CAPABILITY_PROFILE = (
    "phase0_hip_fixed_restart_fgmres_allocation_and_policy_plan"
)
HIP_FGMRES_REDUCTION_SEGMENT_SIZE = 512
HIP_FGMRES_MAX_RESTART_DIMENSION = 16
HIP_FGMRES_MAX_ITERATIONS = 4096
HIP_FGMRES_RECURRENCE_ABI_VERSION = 1
HIP_FGMRES_DGKS_ETA = 0.717
HIP_FGMRES_BREAKDOWN_EPSILON_MULTIPLIER = 64.0
HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES = 192
HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES = 72

_ZERO_HASH = "sha256:" + "0" * 64
_INT32_MAX = int(np.iinfo(np.int32).max)
_INT64_MAX = int(np.iinfo(np.int64).max)
_SOURCE_SOLVER_POLICY = "scipy_sparse_direct"
_BORROWED_NAMES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
    "reduced_state",
    "reduced_load",
    "reduced_direction",
    "jacobi_inverse",
)
_OWNED_NAMES = (
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "reduction_ping",
    "reduction_pong",
    "packed_dense_state",
    "solve_record",
)
_BUFFER_NAMES = _BORROWED_NAMES + _OWNED_NAMES
_PACKED_DENSE_OFFSETS = {
    "hessenberg": "offset=0,length=M*(M+1)",
    "givens_cos": "offset=M*(M+1),length=M",
    "givens_sin": "offset=M*(M+1)+M,length=M",
    "least_squares_rhs": "offset=M*(M+1)+2*M,length=M+1",
    "triangular_solution": "offset=M*(M+1)+3*M+1,length=M",
}
_SOLVE_RECORD_HEADER_I32_FIELDS = (
    "recurrence_abi_version",
    "active",
    "terminal_status",
    "termination_code",
    "device_error_bits",
    "scheduled_iterations",
    "effective_iterations",
    "scheduled_restarts",
    "effective_restarts",
    "effective_arnoldi_dimension",
    "happy_breakdown_count",
    "stagnation_checkpoint_count",
    "false_convergence_count",
    "operator_apply_count",
    "preconditioner_apply_count",
    "restart_dimension",
)
_SOLVE_RECORD_HEADER_F64_FIELDS = (
    "rhs_l2",
    "rhs_linf",
    "solver_tolerance_l2",
    "authoritative_tolerance_scaled_linf",
    "initial_residual_l2",
    "final_residual_l2",
    "final_residual_linf",
    "final_scaled_residual",
    "previous_checkpoint_residual_l2",
    "solution_update_l2",
    "solution_scale_l2",
    "estimated_residual_l2",
    "arnoldi_work_l2",
    "arnoldi_breakdown_threshold",
    "triangular_scale",
    "reserved_f64_0",
)
_SOLVE_RECORD_RESTART_I32_FIELDS = (
    "restart_index",
    "start_iteration",
    "end_iteration",
    "arnoldi_step_count",
    "reorthogonalization_count",
    "termination_hint",
    "flags",
    "reserved_i32_0",
)
_SOLVE_RECORD_RESTART_F64_FIELDS = (
    "estimated_residual_l2",
    "true_residual_l2",
    "true_residual_linf",
    "scaled_true_residual",
    "solution_update_l2",
)
_TERMINAL_STATUS_CODES = {
    "not_terminal": 0,
    "converged": 1,
    "max_iterations": 2,
    "stagnated": 3,
    "diverged": 4,
    "arnoldi_breakdown": 5,
    "numerical_failure": 6,
}
_TERMINATION_CODES = {
    "none": 0,
    "converged_initial_true_residual": 1,
    "converged_happy_breakdown": 2,
    "converged_true_residual": 3,
    "converged_restart_true_residual": 4,
    "max_iterations_exhausted": 10,
    "true_residual_stagnated": 20,
    "true_residual_diverged": 21,
    "arnoldi_triangular_factor_breakdown": 30,
    "arnoldi_invariant_subspace_breakdown": 31,
    "invalid_input_or_control": 40,
    "nonfinite_arithmetic": 41,
    "operator_application_failed": 42,
    "orthogonalization_failed": 43,
    "givens_rotation_failed": 44,
    "triangular_solve_failed": 45,
    "true_residual_replay_failed": 46,
    "restart_state_failed": 47,
}
_RESTART_HINT_CODES = {
    "none": 0,
    "restart_completed": 1,
    "converged_happy_breakdown": 2,
    "converged_true_residual": 3,
    "arnoldi_invariant_subspace_breakdown": 4,
    "arnoldi_triangular_factor_breakdown": 5,
}
_RESTART_FLAG_BITS = {
    "true_residual_replayed": 0,
    "solver_l2_passed": 1,
    "authoritative_linf_passed": 2,
    "happy_breakdown": 3,
    "invariant_breakdown": 4,
    "stagnation_plateau": 5,
    "tiny_update": 6,
    "divergence": 7,
}


def _field_layout(
    names: tuple[str, ...],
    *,
    dtype: Literal["i32", "f64"],
    start_offset: int,
) -> list[dict[str, Any]]:
    item_size = 4 if dtype == "i32" else 8
    return [
        {
            "name": name,
            "dtype": dtype,
            "offset_bytes": start_offset + index * item_size,
        }
        for index, name in enumerate(names)
    ]


def hip_fgmres_solve_record_abi_payload_v1() -> dict[str, Any]:
    """Return a fresh canonical description of the v1 solve-record ABI.

    The compile-time plan, HIPRTC module identity, host-side record decoder,
    and future live solver context must all hash this exact payload.  Returning
    fresh containers prevents a caller from mutating the module-owned ABI.
    """

    return {
        "recurrence_abi_version": HIP_FGMRES_RECURRENCE_ABI_VERSION,
        "byte_order": "little_endian",
        "header_bytes": HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES,
        "restart_bytes": HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES,
        "header_layout": "16*i32+16*f64",
        "restart_layout": "7*i32+4_byte_pad+5*f64",
        "header_fields": _field_layout(
            _SOLVE_RECORD_HEADER_I32_FIELDS,
            dtype="i32",
            start_offset=0,
        )
        + _field_layout(
            _SOLVE_RECORD_HEADER_F64_FIELDS,
            dtype="f64",
            start_offset=64,
        ),
        "restart_fields": _field_layout(
            _SOLVE_RECORD_RESTART_I32_FIELDS,
            dtype="i32",
            start_offset=0,
        )
        + _field_layout(
            _SOLVE_RECORD_RESTART_F64_FIELDS,
            dtype="f64",
            start_offset=32,
        ),
        "terminal_status_codes": dict(_TERMINAL_STATUS_CODES),
        "termination_codes": dict(_TERMINATION_CODES),
        "restart_hint_codes": dict(_RESTART_HINT_CODES),
        "restart_flag_bits": dict(_RESTART_FLAG_BITS),
    }


class HipFgmresPlanV1Error(ValueError):
    """Fail-closed FGMRES plan error with a stable code and JSON pointer."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresBufferPlanV1:
    """One borrowed device view or one future owned allocation extent."""

    name: str
    ownership: Literal["borrowed", "owned"]
    dtype: Literal["<f8", "<i4", "|u1"]
    shape: tuple[int, ...]
    element_count: int
    byte_length: int
    access: str
    source: str
    initialization: str
    extent_formula: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        payload["memory_space"] = "hip_device"
        return payload


@dataclass(frozen=True, slots=True)
class HipFgmresPlanV1:
    """Immutable compile-time contract for a future device FGMRES child."""

    schema_version: str
    capability_profile: str
    plan_id: str
    plan_hash: str
    memory_layout_hash: str

    source_execution_plan_schema_version: str
    source_execution_plan_capability_profile: str
    source_execution_plan_id: str
    source_execution_plan_hash: str
    source_operator_version: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_symbolic_reuse_hash: str
    source_partition_hash: str
    source_model_ir_content_hash: str
    source_solver_artifact_hash: str
    source_load_pattern_id: str
    source_residual_tolerance: float

    source_free_space_schema_version: str
    source_free_space_capability_profile: str
    source_free_space_plan_id: str
    source_free_space_plan_hash: str
    source_free_space_view_hash: str
    jacobi_diagonal_data_hash: str
    jacobi_inverse_data_hash: str

    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    reduction_partial_count: int
    maximum_restart_count: int
    packed_dense_scalar_count: int

    policy: FgmresPolicyV1
    buffers: tuple[HipFgmresBufferPlanV1, ...]
    borrowed_device_byte_span: int
    owned_device_byte_length: int

    _source_execution_plan: ExecutionPlanV2 = dataclass_field(
        repr=False,
        compare=False,
    )
    _source_free_space_plan: HipFreeSpaceOperatorPlanV1 = dataclass_field(
        repr=False,
        compare=False,
    )

    @property
    def restart_dimension(self) -> int:
        return self.policy.restart_dimension

    @property
    def max_iterations(self) -> int:
        return self.policy.max_iterations

    def buffer(self, name: str) -> HipFgmresBufferPlanV1:
        for row in self.buffers:
            if row.name == name:
                return row
        raise KeyError(f"Unknown HIP FGMRES plan buffer: {name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "plan_id": self.plan_id,
            "source_contract": {
                "execution_plan_schema_version": (
                    self.source_execution_plan_schema_version
                ),
                "execution_plan_capability_profile": (
                    self.source_execution_plan_capability_profile
                ),
                "execution_plan_id": self.source_execution_plan_id,
                "execution_plan_hash": self.source_execution_plan_hash,
                "operator_version": self.source_operator_version,
                "operator_hash": self.source_operator_hash,
                "numeric_snapshot_hash": self.source_numeric_snapshot_hash,
                "symbolic_reuse_hash": self.source_symbolic_reuse_hash,
                "partition_hash": self.source_partition_hash,
                "model_ir_content_hash": self.source_model_ir_content_hash,
                "solver_artifact_hash": self.source_solver_artifact_hash,
                "load_pattern_id": self.source_load_pattern_id,
                "authoritative_residual_tolerance": (self.source_residual_tolerance),
                "source_solver_policy": _SOURCE_SOLVER_POLICY,
                "source_solver_policy_overridden": False,
            },
            "free_space_contract": {
                "schema_version": self.source_free_space_schema_version,
                "capability_profile": self.source_free_space_capability_profile,
                "plan_id": self.source_free_space_plan_id,
                "plan_hash": self.source_free_space_plan_hash,
                "free_space_view_hash": self.source_free_space_view_hash,
                "jacobi_diagonal_data_hash": self.jacobi_diagonal_data_hash,
                "jacobi_inverse_data_hash": self.jacobi_inverse_data_hash,
            },
            "policy": self.policy.to_dict(),
            "dimensions": {
                "global_dof_count": self.global_dof_count,
                "free_dof_count": self.free_dof_count,
                "reduced_csr_nnz": self.reduced_csr_nnz,
                "restart_dimension": self.restart_dimension,
                "max_iterations": self.max_iterations,
                "maximum_restart_count": self.maximum_restart_count,
                "reduction_segment_size": HIP_FGMRES_REDUCTION_SEGMENT_SIZE,
                "reduction_partial_count": self.reduction_partial_count,
                "packed_dense_scalar_count": self.packed_dense_scalar_count,
            },
            "algorithm_contract": {
                "recurrence_abi_version": HIP_FGMRES_RECURRENCE_ABI_VERSION,
                "method": "fixed_restart_right_preconditioned_fgmres",
                "scalar_type": "fp64",
                "residual_equation": "r=b-Ax",
                "orthogonalization": "dgks_conditional_two_pass_mgs",
                "dgks_reorthogonalization_eta": HIP_FGMRES_DGKS_ETA,
                "arnoldi_breakdown_epsilon_multiplier": (
                    HIP_FGMRES_BREAKDOWN_EPSILON_MULTIPLIER
                ),
                "arnoldi_breakdown_test": ("h_next_le_64_eps_times_l2_of_A_z_j"),
                "givens_breakdown_test": (
                    "hypot_upper_lower_le_64_eps_times_max_abs_upper_lower"
                ),
                "least_squares_update": "incremental_givens_qr",
                "hessenberg_layout": "column_major_(M+1)_by_M",
                "triangular_backsolve": (
                    "scale_relative_upper_triangular_no_lstsq_or_pinv"
                ),
                "preconditioner": "positive_unshifted_jacobi_right",
                "initial_residual_replay": "always_explicit_b_minus_A_x0",
                "internal_convergence_test": (
                    "l2_le_max_atol_rtol_times_rhs_l2_no_unit_floor"
                ),
                "true_residual_checkpoint": "each_restart_and_final",
                "candidate_true_residual_trigger": (
                    "estimated_l2_pass_or_suspected_arnoldi_breakdown"
                ),
                "estimated_residual_authoritative": False,
                "convergence_requires_both_true_residual_gates": True,
                "authoritative_load_scale": "max_1_rhs_linf",
                "comparisons_are_inclusive": True,
                "authoritative_final_test": (
                    "scaled_true_residual_linf_le_execution_plan_tolerance"
                ),
                "triangular_pivot_floor": (
                    "64_eps_times_max_abs_upper_factor_no_unit_floor"
                ),
                "stagnation_checkpoint_rule": (
                    "consecutive_plateau_and_sqrt_eps_scaled_tiny_update"
                ),
                "divergence_checkpoint_rule": (
                    "true_l2_gt_factor_times_max_initial_l2_float64_tiny"
                ),
                "restart_dimension_fixed_for_plan": True,
                "global_iteration_cap_crosses_restart_boundaries": True,
                "dense_lstsq_or_pinv_fallback_allowed": False,
                "diagonal_shift_or_clamp_allowed": False,
                "silent_solver_fallback_allowed": False,
            },
            "runtime_lineage_requirements": {
                "compile_time_apply_receipt_bound": False,
                "compile_time_primitive_receipt_bound": False,
                "context_open_must_bind_exact_latest_free_space_apply": True,
                "context_open_must_acquire_exclusive_primitive_child": True,
                "context_open_must_bind_exact_live_primitive_context": True,
                "reduced_buffers_must_resolve_through_primitive_source_apply": True,
                "same_runtime_device_and_stream_required": True,
            },
            "memory_plan": {
                "buffer_order": list(_BUFFER_NAMES),
                "borrowed_buffer_count": len(_BORROWED_NAMES),
                "owned_buffer_count": len(_OWNED_NAMES),
                "borrowed_device_byte_span": self.borrowed_device_byte_span,
                "owned_device_byte_length": self.owned_device_byte_length,
                "additional_peak_device_bytes_planned": (self.owned_device_byte_length),
                "basis_storage_formula": "8*((M+1)*F+M*F)",
                "reduction_storage_formula": "8*(2*P+2*P)",
                "packed_dense_storage_formula": "8*(M*M+5*M+1)",
                "solve_record_storage_formula": "192+72*R",
                "solve_record_header_bytes": (HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES),
                "solve_record_restart_bytes": (HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES),
                "solve_record_restart_layout": "7*i32+4_byte_pad+5*f64",
                "solve_record_header_layout": "16*i32+16*f64",
                "scalar_byte_order": "little_endian",
                "packed_dense_offsets": dict(_PACKED_DENSE_OFFSETS),
                "solve_record_header_fields": _field_layout(
                    _SOLVE_RECORD_HEADER_I32_FIELDS,
                    dtype="i32",
                    start_offset=0,
                )
                + _field_layout(
                    _SOLVE_RECORD_HEADER_F64_FIELDS,
                    dtype="f64",
                    start_offset=64,
                ),
                "solve_record_restart_fields": _field_layout(
                    _SOLVE_RECORD_RESTART_I32_FIELDS,
                    dtype="i32",
                    start_offset=0,
                )
                + _field_layout(
                    _SOLVE_RECORD_RESTART_F64_FIELDS,
                    dtype="f64",
                    start_offset=32,
                ),
                "terminal_status_codes": dict(_TERMINAL_STATUS_CODES),
                "termination_codes": dict(_TERMINATION_CODES),
                "restart_hint_codes": dict(_RESTART_HINT_CODES),
                "restart_flag_bits": dict(_RESTART_FLAG_BITS),
                "buffers": [row.to_dict() for row in self.buffers],
                "memory_layout_hash": self.memory_layout_hash,
            },
            "claim_boundary": {
                "compile_time_plan_only": True,
                "hip_specific_layout": True,
                "device_buffer_layout_planned": True,
                "positive_jacobi_source_preflight_passed": True,
                "execution_performed": False,
                "device_allocation_performed": False,
                "runtime_receipt_lineage_bound": False,
                "fgmres_runtime_ready": False,
                "iteration_host_copy_zero_proven": False,
                "spd_proven": False,
                "pcg_ready": False,
                "fallback_used": False,
                "end_to_end_O_N_proven": False,
                "speedup_proven": False,
                "promotion_eligible": False,
                "commercial_ready": False,
                "schema_only_validation_authoritative": False,
                "python_semantic_replay_required": True,
            },
            "plan_hash": self.plan_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def compile_hip_fgmres_plan_v1(
    source_plan: ExecutionPlanV2,
    source_free_space_plan: HipFreeSpaceOperatorPlanV1,
    policy: FgmresPolicyV1 | None = None,
) -> HipFgmresPlanV1:
    """Compile an immutable FGMRES allocation plan without runtime work."""

    _validate_source_pair(source_plan, source_free_space_plan)
    try:
        checked_policy = (
            compile_fgmres_policy_v1()
            if policy is None
            else validate_fgmres_policy_v1(policy)
        )
    except CpuFgmresReferenceError as exc:
        raise HipFgmresPlanV1Error(
            "hip_fgmres_policy_invalid",
            f"/policy{exc.path if exc.path != '/' else ''}",
            f"{exc.code}: {exc.message}",
        ) from exc

    source_witness = _snapshot_execution_plan(source_plan)
    overlay_witness = compile_hip_free_space_operator_plan_v1(source_witness)
    if overlay_witness.plan_hash != source_free_space_plan.plan_hash:
        _fail(
            "hip_fgmres_free_space_plan_mismatch",
            "/free_space_contract/plan_hash",
        )
    policy_witness = replace(checked_policy)
    jacobi_diagonal_hash, jacobi_inverse_hash = _jacobi_hashes(source_witness)

    free_dof_count = overlay_witness.free_dof_count
    reduced_csr_nnz = overlay_witness.reduced_csr_nnz
    restart_dimension = policy_witness.restart_dimension
    partial_count = max(
        1,
        (free_dof_count + HIP_FGMRES_REDUCTION_SEGMENT_SIZE - 1)
        // HIP_FGMRES_REDUCTION_SEGMENT_SIZE,
    )
    maximum_restart_count = (
        0
        if policy_witness.max_iterations == 0
        else (policy_witness.max_iterations + restart_dimension - 1)
        // restart_dimension
    )
    packed_dense_count = (
        restart_dimension * restart_dimension + 5 * restart_dimension + 1
    )
    buffers = _compile_buffer_plan(
        free_dof_count,
        reduced_csr_nnz,
        restart_dimension,
        partial_count,
        policy_witness.max_iterations,
    )
    borrowed_bytes = sum(
        row.byte_length for row in buffers if row.ownership == "borrowed"
    )
    owned_bytes = sum(row.byte_length for row in buffers if row.ownership == "owned")
    if borrowed_bytes > _INT64_MAX or owned_bytes > _INT64_MAX:
        _fail(
            "hip_fgmres_device_extent_capacity_exceeded",
            "/memory_plan",
        )

    artifact = HipFgmresPlanV1(
        schema_version=HIP_FGMRES_PLAN_V1_SCHEMA_VERSION,
        capability_profile=HIP_FGMRES_PLAN_V1_CAPABILITY_PROFILE,
        plan_id="HipFgmresPlan:" + "0" * 24,
        plan_hash=_ZERO_HASH,
        memory_layout_hash=_ZERO_HASH,
        source_execution_plan_schema_version=source_witness.schema_version,
        source_execution_plan_capability_profile=source_witness.capability_profile,
        source_execution_plan_id=source_witness.plan_id,
        source_execution_plan_hash=source_witness.plan_hash,
        source_operator_version=source_witness.operator_version,
        source_operator_hash=source_witness.operator_hash,
        source_numeric_snapshot_hash=source_witness.numeric_snapshot_hash,
        source_symbolic_reuse_hash=source_witness.symbolic_reuse_hash,
        source_partition_hash=source_witness.partition_hash,
        source_model_ir_content_hash=source_witness.model_ir_content_hash,
        source_solver_artifact_hash=source_witness.solver_artifact_hash,
        source_load_pattern_id=source_witness.load_pattern_id,
        source_residual_tolerance=source_witness.residual_tolerance,
        source_free_space_schema_version=overlay_witness.schema_version,
        source_free_space_capability_profile=overlay_witness.capability_profile,
        source_free_space_plan_id=overlay_witness.plan_id,
        source_free_space_plan_hash=overlay_witness.plan_hash,
        source_free_space_view_hash=overlay_witness.free_space_view_hash,
        jacobi_diagonal_data_hash=jacobi_diagonal_hash,
        jacobi_inverse_data_hash=jacobi_inverse_hash,
        global_dof_count=source_witness.dof_count,
        free_dof_count=free_dof_count,
        reduced_csr_nnz=reduced_csr_nnz,
        reduction_partial_count=partial_count,
        maximum_restart_count=maximum_restart_count,
        packed_dense_scalar_count=packed_dense_count,
        policy=policy_witness,
        buffers=buffers,
        borrowed_device_byte_span=borrowed_bytes,
        owned_device_byte_length=owned_bytes,
        _source_execution_plan=source_witness,
        _source_free_space_plan=overlay_witness,
    )
    artifact = replace(
        artifact,
        memory_layout_hash=_memory_layout_hash(artifact),
    )
    artifact = replace(artifact, plan_id=_plan_id(artifact))
    artifact = replace(artifact, plan_hash=_plan_hash(artifact))
    validate_hip_fgmres_plan_v1(
        artifact,
        expected_execution_plan=source_plan,
        expected_free_space_plan=source_free_space_plan,
    )
    return artifact


def validate_hip_fgmres_plan_v1(
    artifact: HipFgmresPlanV1,
    *,
    expected_execution_plan: ExecutionPlanV2 | None = None,
    expected_free_space_plan: HipFreeSpaceOperatorPlanV1 | None = None,
) -> None:
    """Validate source replay, policy, exact extents, and canonical hashes."""

    if type(artifact) is not HipFgmresPlanV1:
        _raise(
            "hip_fgmres_plan_type_invalid",
            "/",
            "Expected an exact HipFgmresPlanV1 instance.",
        )
    if (
        type(artifact.policy) is not FgmresPolicyV1
        or type(artifact.buffers) is not tuple
        or any(type(row) is not HipFgmresBufferPlanV1 for row in artifact.buffers)
        or type(artifact._source_execution_plan) is not ExecutionPlanV2
        or type(artifact._source_free_space_plan) is not HipFreeSpaceOperatorPlanV1
    ):
        _fail("hip_fgmres_plan_container_invalid", "/")

    try:
        validate_fgmres_policy_v1(artifact.policy)
    except CpuFgmresReferenceError as exc:
        raise HipFgmresPlanV1Error(
            "hip_fgmres_policy_invalid",
            f"/policy{exc.path if exc.path != '/' else ''}",
            f"{exc.code}: {exc.message}",
        ) from exc

    try:
        manifest = artifact.to_dict()
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HipFgmresPlanV1Error(
            "hip_fgmres_plan_manifest_invalid",
            "/",
            f"Cannot build FGMRES plan manifest: {exc}",
        ) from exc
    errors = sorted(
        _schema_validator().iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipFgmresPlanV1Error(
            "hip_fgmres_plan_schema_invalid",
            path,
            error.message,
        )

    if artifact.schema_version != HIP_FGMRES_PLAN_V1_SCHEMA_VERSION:
        _fail("hip_fgmres_plan_schema_mismatch", "/schema_version")
    if artifact.capability_profile != HIP_FGMRES_PLAN_V1_CAPABILITY_PROFILE:
        _fail("hip_fgmres_plan_profile_mismatch", "/capability_profile")
    _validate_exact_scalar_types(artifact)

    source = artifact._source_execution_plan
    overlay = artifact._source_free_space_plan
    _validate_source_pair(source, overlay)
    _validate_source_bindings(artifact, source, overlay)

    if expected_execution_plan is not None:
        if type(expected_execution_plan) is not ExecutionPlanV2:
            _fail(
                "hip_fgmres_expected_execution_plan_invalid",
                "/source_contract",
            )
        _validate_execution_source(expected_execution_plan)
        if expected_execution_plan.plan_hash != source.plan_hash:
            _fail(
                "hip_fgmres_expected_execution_plan_mismatch",
                "/source_contract/execution_plan_hash",
            )
        _validate_source_bindings(artifact, expected_execution_plan, overlay)
    if expected_free_space_plan is not None:
        if type(expected_free_space_plan) is not HipFreeSpaceOperatorPlanV1:
            _fail(
                "hip_fgmres_expected_free_space_plan_invalid",
                "/free_space_contract",
            )
        execution_for_overlay = (
            source if expected_execution_plan is None else expected_execution_plan
        )
        _validate_source_pair(execution_for_overlay, expected_free_space_plan)
        if expected_free_space_plan.plan_hash != overlay.plan_hash:
            _fail(
                "hip_fgmres_expected_free_space_plan_mismatch",
                "/free_space_contract/plan_hash",
            )

    f = overlay.free_dof_count
    z = overlay.reduced_csr_nnz
    m = artifact.policy.restart_dimension
    p = max(
        1,
        (f + HIP_FGMRES_REDUCTION_SEGMENT_SIZE - 1)
        // HIP_FGMRES_REDUCTION_SEGMENT_SIZE,
    )
    expected_dimensions = {
        "global_dof_count": source.dof_count,
        "free_dof_count": f,
        "reduced_csr_nnz": z,
        "reduction_partial_count": p,
        "maximum_restart_count": (
            0
            if artifact.policy.max_iterations == 0
            else (artifact.policy.max_iterations + m - 1) // m
        ),
        "packed_dense_scalar_count": m * m + 5 * m + 1,
    }
    for name, expected in expected_dimensions.items():
        if getattr(artifact, name) != expected:
            _fail("hip_fgmres_dimension_mismatch", f"/dimensions/{name}")

    expected_diagonal_hash, expected_inverse_hash = _jacobi_hashes(source)
    if artifact.jacobi_diagonal_data_hash != expected_diagonal_hash:
        _fail(
            "hip_fgmres_jacobi_diagonal_hash_mismatch",
            "/free_space_contract/jacobi_diagonal_data_hash",
        )
    if artifact.jacobi_inverse_data_hash != expected_inverse_hash:
        _fail(
            "hip_fgmres_jacobi_inverse_hash_mismatch",
            "/free_space_contract/jacobi_inverse_data_hash",
        )
    if artifact.source_residual_tolerance != source.residual_tolerance:
        _fail(
            "hip_fgmres_authoritative_tolerance_mismatch",
            "/source_contract/authoritative_residual_tolerance",
        )
    expected_buffers = _compile_buffer_plan(
        f,
        z,
        m,
        p,
        artifact.policy.max_iterations,
    )
    if artifact.buffers != expected_buffers:
        _fail("hip_fgmres_buffer_plan_mismatch", "/memory_plan/buffers")
    if tuple(row.name for row in artifact.buffers) != _BUFFER_NAMES:
        _fail("hip_fgmres_buffer_order_invalid", "/memory_plan/buffers")
    borrowed_bytes = sum(
        row.byte_length for row in expected_buffers if row.ownership == "borrowed"
    )
    owned_bytes = sum(
        row.byte_length for row in expected_buffers if row.ownership == "owned"
    )
    if artifact.borrowed_device_byte_span != borrowed_bytes:
        _fail(
            "hip_fgmres_borrowed_byte_span_mismatch",
            "/memory_plan/borrowed_device_byte_span",
        )
    if artifact.owned_device_byte_length != owned_bytes:
        _fail(
            "hip_fgmres_owned_byte_length_mismatch",
            "/memory_plan/owned_device_byte_length",
        )
    if artifact.memory_layout_hash != _memory_layout_hash(artifact):
        _fail(
            "hip_fgmres_memory_layout_hash_mismatch",
            "/memory_plan/memory_layout_hash",
        )
    if artifact.plan_id != _plan_id(artifact):
        _fail("hip_fgmres_plan_id_mismatch", "/plan_id")
    if artifact.plan_hash != _plan_hash(artifact):
        _fail("hip_fgmres_plan_hash_mismatch", "/plan_hash")


def _compile_buffer_plan(
    free_dof_count: int,
    reduced_csr_nnz: int,
    restart_dimension: int,
    reduction_partial_count: int,
    max_iterations: int,
) -> tuple[HipFgmresBufferPlanV1, ...]:
    f = free_dof_count
    z = reduced_csr_nnz
    m = restart_dimension
    p = reduction_partial_count
    specifications = (
        (
            "reduced_csr_row_ptr",
            "borrowed",
            "<i4",
            (f + 1,),
            "read_only",
            "free_space_symbolic",
            "parent_owned_no_transfer",
            "F+1",
        ),
        (
            "reduced_csr_column_indices",
            "borrowed",
            "<i4",
            (z,),
            "read_only",
            "free_space_symbolic",
            "parent_owned_no_transfer",
            "Z",
        ),
        (
            "reduced_csr_values",
            "borrowed",
            "<f8",
            (z,),
            "read_only",
            "free_space_numeric",
            "parent_owned_no_transfer",
            "Z",
        ),
        (
            "reduced_state",
            "borrowed",
            "<f8",
            (f,),
            "read_only",
            "free_space_reduced_state",
            "parent_owned_no_transfer",
            "F",
        ),
        (
            "reduced_load",
            "borrowed",
            "<f8",
            (f,),
            "read_only",
            "free_space_reduced_load",
            "parent_owned_no_transfer",
            "F",
        ),
        (
            "reduced_direction",
            "borrowed",
            "<f8",
            (f,),
            "read_only",
            "latest_free_space_apply",
            "parent_owned_no_transfer",
            "F",
        ),
        (
            "jacobi_inverse",
            "borrowed",
            "<f8",
            (f,),
            "read_only_after_prepare",
            "krylov_primitives",
            "parent_owned_no_transfer",
            "F",
        ),
        (
            "solution_x",
            "owned",
            "<f8",
            (f,),
            "read_write",
            "fgmres_context",
            "same_stream_copy_from_reduced_state",
            "F",
        ),
        (
            "true_residual",
            "owned",
            "<f8",
            (f,),
            "read_write",
            "fgmres_context",
            "same_stream_copy_from_reduced_direction",
            "F",
        ),
        (
            "work_w",
            "owned",
            "<f8",
            (f,),
            "read_write",
            "fgmres_context",
            "device_only",
            "F",
        ),
        (
            "basis_v",
            "owned",
            "<f8",
            (m + 1, f),
            "read_write",
            "fgmres_context",
            "device_only",
            "(M+1)*F",
        ),
        (
            "preconditioned_basis_z",
            "owned",
            "<f8",
            (m, f),
            "read_write",
            "fgmres_context",
            "device_only",
            "M*F",
        ),
        (
            "reduction_ping",
            "owned",
            "<f8",
            (2 * p,),
            "read_write",
            "fgmres_context",
            "device_only",
            "2*P",
        ),
        (
            "reduction_pong",
            "owned",
            "<f8",
            (2 * p,),
            "read_write",
            "fgmres_context",
            "device_only",
            "2*P",
        ),
        (
            "packed_dense_state",
            "owned",
            "<f8",
            (m * m + 5 * m + 1,),
            "read_write",
            "fgmres_context",
            "device_only",
            "M*M+5*M+1",
        ),
        (
            "solve_record",
            "owned",
            "|u1",
            (
                HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES
                + HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES
                * (0 if max_iterations == 0 else (max_iterations + m - 1) // m),
            ),
            "read_write",
            "fgmres_context",
            "async_h2d_zero_once_before_enqueue",
            "192+72*R",
        ),
    )
    rows: list[HipFgmresBufferPlanV1] = []
    for (
        name,
        ownership,
        dtype,
        shape,
        access,
        source,
        initialization,
        formula,
    ) in specifications:
        count = int(np.prod(shape, dtype=np.int64))
        item_size = 8 if dtype == "<f8" else 4 if dtype == "<i4" else 1
        rows.append(
            HipFgmresBufferPlanV1(
                name=name,
                ownership=ownership,
                dtype=dtype,
                shape=shape,
                element_count=count,
                byte_length=count * item_size,
                access=access,
                source=source,
                initialization=initialization,
                extent_formula=formula,
            )
        )
    return tuple(rows)


def _validate_execution_source(source: ExecutionPlanV2) -> None:
    if type(source) is not ExecutionPlanV2:
        _raise(
            "hip_fgmres_source_execution_plan_invalid",
            "/source_contract",
            "Source must be an exact ExecutionPlanV2.",
        )
    try:
        validate_execution_plan_v2(source, expected_buffers=source._source_buffers)
    except (AttributeError, ExecutionPlanV2Error) as exc:
        raise HipFgmresPlanV1Error(
            "hip_fgmres_source_execution_plan_invalid",
            getattr(exc, "path", "/source_contract"),
            f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', str(exc))}",
        ) from exc
    if source.schema_version != EXECUTION_PLAN_V2_SCHEMA_VERSION:
        _fail(
            "hip_fgmres_source_execution_schema_mismatch",
            "/source_contract/execution_plan_schema_version",
        )
    if source.capability_profile != EXECUTION_PLAN_V2_CAPABILITY_PROFILE:
        _fail(
            "hip_fgmres_source_execution_profile_mismatch",
            "/source_contract/execution_plan_capability_profile",
        )


def _validate_source_pair(
    source: ExecutionPlanV2,
    overlay: HipFreeSpaceOperatorPlanV1,
) -> None:
    _validate_execution_source(source)
    if type(overlay) is not HipFreeSpaceOperatorPlanV1:
        _fail(
            "hip_fgmres_source_free_space_plan_invalid",
            "/free_space_contract",
        )
    try:
        validate_hip_free_space_operator_plan_v1(
            overlay,
            expected_execution_plan=source,
        )
    except (AttributeError, HipFreeSpaceOperatorPlanV1Error) as exc:
        raise HipFgmresPlanV1Error(
            "hip_fgmres_source_free_space_plan_invalid",
            getattr(exc, "path", "/free_space_contract"),
            f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', str(exc))}",
        ) from exc


def _snapshot_execution_plan(source: ExecutionPlanV2) -> ExecutionPlanV2:
    source_buffers = _detached_source_snapshot(source._source_buffers)
    source_buffers = replace(
        source_buffers,
        descriptors=tuple(replace(row) for row in source_buffers.descriptors),
    )
    witness = replace(
        source,
        descriptors=tuple(replace(row) for row in source.descriptors),
        _arrays=tuple(list(source._arrays)),
        _source_buffers=source_buffers,
    )
    _validate_execution_source(witness)
    return witness


def _validate_source_bindings(
    artifact: HipFgmresPlanV1,
    source: ExecutionPlanV2,
    overlay: HipFreeSpaceOperatorPlanV1,
) -> None:
    bindings = (
        (
            artifact.source_execution_plan_schema_version,
            source.schema_version,
            "/source_contract/execution_plan_schema_version",
        ),
        (
            artifact.source_execution_plan_capability_profile,
            source.capability_profile,
            "/source_contract/execution_plan_capability_profile",
        ),
        (
            artifact.source_execution_plan_id,
            source.plan_id,
            "/source_contract/execution_plan_id",
        ),
        (
            artifact.source_execution_plan_hash,
            source.plan_hash,
            "/source_contract/execution_plan_hash",
        ),
        (
            artifact.source_operator_version,
            source.operator_version,
            "/source_contract/operator_version",
        ),
        (
            artifact.source_operator_hash,
            source.operator_hash,
            "/source_contract/operator_hash",
        ),
        (
            artifact.source_numeric_snapshot_hash,
            source.numeric_snapshot_hash,
            "/source_contract/numeric_snapshot_hash",
        ),
        (
            artifact.source_symbolic_reuse_hash,
            source.symbolic_reuse_hash,
            "/source_contract/symbolic_reuse_hash",
        ),
        (
            artifact.source_partition_hash,
            source.partition_hash,
            "/source_contract/partition_hash",
        ),
        (
            artifact.source_model_ir_content_hash,
            source.model_ir_content_hash,
            "/source_contract/model_ir_content_hash",
        ),
        (
            artifact.source_solver_artifact_hash,
            source.solver_artifact_hash,
            "/source_contract/solver_artifact_hash",
        ),
        (
            artifact.source_load_pattern_id,
            source.load_pattern_id,
            "/source_contract/load_pattern_id",
        ),
        (
            artifact.source_residual_tolerance,
            source.residual_tolerance,
            "/source_contract/authoritative_residual_tolerance",
        ),
        (
            artifact.source_free_space_schema_version,
            overlay.schema_version,
            "/free_space_contract/schema_version",
        ),
        (
            artifact.source_free_space_capability_profile,
            overlay.capability_profile,
            "/free_space_contract/capability_profile",
        ),
        (
            artifact.source_free_space_plan_id,
            overlay.plan_id,
            "/free_space_contract/plan_id",
        ),
        (
            artifact.source_free_space_plan_hash,
            overlay.plan_hash,
            "/free_space_contract/plan_hash",
        ),
        (
            artifact.source_free_space_view_hash,
            overlay.free_space_view_hash,
            "/free_space_contract/free_space_view_hash",
        ),
    )
    for actual, expected, path in bindings:
        if actual != expected:
            _fail("hip_fgmres_source_binding_mismatch", path)


def _jacobi_hashes(source: ExecutionPlanV2) -> tuple[str, str]:
    row_ptr = source.array("reduced_csr_row_ptr")
    columns = source.array("reduced_csr_column_indices")
    values = source.array("reduced_stiffness_csr_values")
    free_count = int(source.array("free_dofs").size)
    diagonal = np.empty(free_count, dtype="<f8")
    for row in range(free_count):
        begin = int(row_ptr[row])
        end = int(row_ptr[row + 1])
        positions = np.flatnonzero(columns[begin:end] == row)
        if positions.size != 1:
            _fail(
                "hip_fgmres_jacobi_diagonal_structure_invalid",
                "/free_space_contract/jacobi_diagonal_data_hash",
            )
        value = float(values[begin + int(positions[0])])
        if not np.isfinite(value) or value <= 0.0:
            _fail(
                "hip_fgmres_positive_jacobi_unavailable",
                "/free_space_contract/jacobi_diagonal_data_hash",
            )
        diagonal[row] = value
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        inverse = 1.0 / diagonal
    if not np.isfinite(inverse).all() or np.any(inverse <= 0.0):
        _fail(
            "hip_fgmres_positive_jacobi_inverse_unavailable",
            "/free_space_contract/jacobi_inverse_data_hash",
        )
    inverse = np.ascontiguousarray(inverse, dtype="<f8")
    return array_data_hash(diagonal), array_data_hash(inverse)


def _jacobi_diagonal_hash(source: ExecutionPlanV2) -> str:
    return _jacobi_hashes(source)[0]


def _validate_exact_scalar_types(artifact: HipFgmresPlanV1) -> None:
    positive_ints = (
        "global_dof_count",
        "free_dof_count",
        "reduced_csr_nnz",
        "reduction_partial_count",
        "packed_dense_scalar_count",
        "borrowed_device_byte_span",
        "owned_device_byte_length",
    )
    for name in positive_ints:
        value = getattr(artifact, name)
        if type(value) is not int or value <= 0 or value > _INT64_MAX:
            _fail("hip_fgmres_scalar_type_invalid", f"/dimensions/{name}")
    if (
        type(artifact.maximum_restart_count) is not int
        or artifact.maximum_restart_count < 0
        or artifact.maximum_restart_count > HIP_FGMRES_MAX_ITERATIONS
    ):
        _fail(
            "hip_fgmres_scalar_type_invalid",
            "/dimensions/maximum_restart_count",
        )
    for name in (
        "schema_version",
        "capability_profile",
        "plan_id",
        "plan_hash",
        "memory_layout_hash",
        "source_execution_plan_schema_version",
        "source_execution_plan_capability_profile",
        "source_execution_plan_id",
        "source_execution_plan_hash",
        "source_operator_version",
        "source_operator_hash",
        "source_numeric_snapshot_hash",
        "source_symbolic_reuse_hash",
        "source_partition_hash",
        "source_model_ir_content_hash",
        "source_solver_artifact_hash",
        "source_load_pattern_id",
        "source_free_space_schema_version",
        "source_free_space_capability_profile",
        "source_free_space_plan_id",
        "source_free_space_plan_hash",
        "source_free_space_view_hash",
        "jacobi_diagonal_data_hash",
        "jacobi_inverse_data_hash",
    ):
        if type(getattr(artifact, name)) is not str:
            _fail("hip_fgmres_scalar_type_invalid", f"/{name}")
    if (
        type(artifact.source_residual_tolerance) is not float
        or not math.isfinite(artifact.source_residual_tolerance)
        or artifact.source_residual_tolerance <= 0.0
    ):
        _fail(
            "hip_fgmres_scalar_type_invalid",
            "/source_contract/authoritative_residual_tolerance",
        )


def _memory_layout_hash(artifact: HipFgmresPlanV1) -> str:
    memory_plan = artifact.to_dict()["memory_plan"]
    memory_plan.pop("memory_layout_hash")
    return canonical_hash(
        {
            "recurrence_abi_version": HIP_FGMRES_RECURRENCE_ABI_VERSION,
            "memory_plan": memory_plan,
        }
    )


def _plan_id(artifact: HipFgmresPlanV1) -> str:
    digest = canonical_hash(
        {
            "source_execution_plan_hash": artifact.source_execution_plan_hash,
            "source_free_space_plan_hash": artifact.source_free_space_plan_hash,
            "policy_hash": artifact.policy.policy_hash,
            "memory_layout_hash": artifact.memory_layout_hash,
        }
    )
    return "HipFgmresPlan:" + digest.removeprefix("sha256:")[:24]


def _plan_hash(artifact: HipFgmresPlanV1) -> str:
    payload = artifact.to_dict()
    payload.pop("plan_hash")
    return canonical_hash(payload)


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "hip_fgmres_plan_v1.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresPlanV1Error(code, path, message or code)


def _raise(code: str, path: str, message: str) -> None:
    raise HipFgmresPlanV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_MAX_ITERATIONS",
    "HIP_FGMRES_MAX_RESTART_DIMENSION",
    "HIP_FGMRES_PLAN_V1_CAPABILITY_PROFILE",
    "HIP_FGMRES_PLAN_V1_SCHEMA_VERSION",
    "HIP_FGMRES_RECURRENCE_ABI_VERSION",
    "HIP_FGMRES_REDUCTION_SEGMENT_SIZE",
    "HipFgmresBufferPlanV1",
    "HipFgmresPlanV1",
    "HipFgmresPlanV1Error",
    "compile_hip_fgmres_plan_v1",
    "hip_fgmres_solve_record_abi_payload_v1",
    "validate_hip_fgmres_plan_v1",
]
