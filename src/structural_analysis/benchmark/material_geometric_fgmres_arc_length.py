"""Engine v2 CPU FGMRES integration for the bounded material-geometric path.

The physical residual, accepted material parent, current-chord tangent, and
transactional arc-length loop come from ``material_geometric_truss_arc_length``.
This module replaces only the default dense tangent solve with a dedicated
ExecutionPlan/EquationScaling binding and Engine v2 CPU FGMRES.  The reduced
operator has exactly two equations, so this is integration evidence rather
than a production-scale sparse or preconditioned nonlinear solver claim.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any

import numpy as np

from structural_analysis.benchmark.material_geometric_truss import (
    StatefulTwoBarTrussProblem,
)
from structural_analysis.benchmark.material_geometric_truss_arc_length import (
    MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
    MATERIAL_GEOMETRIC_ARC_LENGTH_TANGENT_ACTION,
    MaterialGeometricArcLengthResult,
    MaterialGeometricArcLengthStepProblem,
    build_material_geometric_source_problem_contract_hash,
    stateful_material_geometric_arc_length_continuation,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.equation_scaling import (
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    create_execution_plan,
)
from structural_analysis.engine_v2.cpu_fgmres_tangent import (
    CPU_FGMRES_TANGENT_SOLVE_PROFILE,
    solve_cpu_fgmres_tangent_system,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    VectorArcLengthTangentSolve,
)


MATERIAL_GEOMETRIC_FGMRES_ARC_LENGTH_SCHEMA_VERSION = (
    "phase2-material-geometric-cpu-fgmres-arc-length.v1"
)
MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE = (
    "material-geometric-two-bar-engine-v2-cpu-fgmres-state-tangent.v1"
)
MATERIAL_GEOMETRIC_FGMRES_SOLVE_RECEIPT_SCHEMA_VERSION = (
    "material-geometric-two-bar-cpu-fgmres-state-tangent-solve.v1"
)
MATERIAL_GEOMETRIC_FGMRES_CLAIM_BOUNDARY = (
    "This receipt verifies every predictor and Schur-corrector tangent solve "
    "in one bounded, state-updated material-geometric two-bar arc-length path "
    "through a dedicated Engine v2 ExecutionPlan, EquationScaling, exact "
    "two-equation reduced CSR operator, and deterministic CPU FGMRES. It does "
    "not establish a general 2D/3D truss, frame or shell adapter, production-"
    "scale sparsity or preconditioner effectiveness, finite-strain behavior, "
    "ROCm/HIP parity, durable checkpoints, external validation, full-building "
    "equilibrium, or G1 closure."
)

_NODE_COUNT = 3
_DOF_PER_NODE = 6
_DOF_COUNT = _NODE_COUNT * _DOF_PER_NODE
_FREE_DOFS = np.asarray([6, 7], dtype="<i4")
_MAX_ITERATIONS = 4
_RESTART_LENGTH = 2
_RELATIVE_TOLERANCE = 1.0e-13
_ABSOLUTE_TOLERANCE = 1.0e-14
_EXPLICIT_RESIDUAL_TOLERANCE_N = 1.0e-6
_KN_TO_N = 1_000.0


def _binding_hash(label: str, source_hash: str) -> str:
    return canonical_hash(
        {
            "profile": MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE,
            "label": label,
            "source_problem_contract_hash": source_hash,
        }
    )


def _global_csr_pattern() -> tuple[np.ndarray, np.ndarray]:
    free = {int(value) for value in _FREE_DOFS}
    row_ptr = [0]
    columns: list[int] = []
    for row in range(_DOF_COUNT):
        if row in free:
            columns.extend(int(value) for value in _FREE_DOFS)
        else:
            columns.append(row)
        row_ptr.append(len(columns))
    return (
        np.asarray(row_ptr, dtype="<i8"),
        np.asarray(columns, dtype="<i4"),
    )


def _build_binding(problem: StatefulTwoBarTrussProblem) -> dict[str, Any]:
    source_hash = build_material_geometric_source_problem_contract_hash(problem)
    constrained_dofs = np.asarray(
        [index for index in range(_DOF_COUNT) if index not in set(_FREE_DOFS)],
        dtype="<i4",
    )
    global_to_free = np.full(_DOF_COUNT, -1, dtype="<i4")
    global_to_free[_FREE_DOFS] = np.arange(_FREE_DOFS.size, dtype="<i4")
    row_ptr, column_indices = _global_csr_pattern()
    left_dofs = np.arange(0, 6, dtype="<i4")
    apex_dofs = np.arange(6, 12, dtype="<i4")
    right_dofs = np.arange(12, 18, dtype="<i4")
    plan = create_execution_plan(
        model_ir_content_hash=source_hash,
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_binding_hash("numeric-buffers", source_hash),
        solver_entity_mapping_hash=_binding_hash("entity-mapping", source_hash),
        solver_artifact_hash=_binding_hash("solver-artifact", source_hash),
        load_pattern_id="MATERIAL_GEOMETRIC_TWO_BAR_ARC_LENGTH",
        operator_id="material-geometric-two-bar-current-state-tangent",
        operator_version="material-geometric-two-bar-current-state-tangent.v1",
        operator_hash=_binding_hash("operator", source_hash),
        node_ids=("LEFT_SUPPORT", "APEX", "RIGHT_SUPPORT"),
        element_ids=("left-bar", "right-bar"),
        node_dof_indices=np.arange(_DOF_COUNT, dtype="<i4").reshape(
            _NODE_COUNT,
            _DOF_PER_NODE,
        ),
        global_to_free=global_to_free,
        element_global_dofs=np.asarray(
            [
                np.concatenate((left_dofs, apex_dofs)),
                np.concatenate((apex_dofs, right_dofs)),
            ],
            dtype="<i4",
        ),
        constrained_dofs=constrained_dofs,
        free_dofs=_FREE_DOFS,
        csr_row_ptr=row_ptr,
        csr_column_indices=column_indices,
    )
    coordinates = np.asarray(
        [
            [-problem.half_span_m, 0.0, 0.0],
            [0.0, problem.rise_m, 0.0],
            [problem.half_span_m, 0.0, 0.0],
        ],
        dtype="<f8",
    )
    reference_equation_load = np.zeros(_DOF_COUNT, dtype="<f8")
    reference_equation_load[_FREE_DOFS] = _KN_TO_N * problem.reference_load_kn()
    scaling = create_equation_scaling(
        execution_plan=plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_equation_load,
    )
    bound_plan = bind_equation_scaling_to_execution_plan(
        plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_equation_load,
    )
    return {
        "plan": bound_plan,
        "scaling": scaling,
        "coordinates": coordinates,
        "reference_equation_load": reference_equation_load,
        "source_problem_contract_hash": source_hash,
    }


def _global_csr_values(
    binding: dict[str, Any],
    tangent_kn_per_m: np.ndarray,
) -> np.ndarray:
    plan = binding["plan"]
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    values = np.zeros(columns.size, dtype="<f8")
    free_index = {int(global_dof): index for index, global_dof in enumerate(_FREE_DOFS)}
    for row in range(plan.dof_count):
        for position in range(int(row_ptr[row]), int(row_ptr[row + 1])):
            column = int(columns[position])
            if row in free_index:
                values[position] = (
                    _KN_TO_N * tangent_kn_per_m[free_index[row], free_index[column]]
                )
            else:
                values[position] = 1.0 if row == column else 0.0
    return values


def _finite_two_vector(values: Any, *, name: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite two-vector") from exc
    if vector.shape != (2,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite two-vector")
    return np.ascontiguousarray(vector, dtype=np.float64)


@dataclass(frozen=True)
class MaterialGeometricCPUFGMRESStateTangentSolver:
    """Dedicated two-equation Engine v2 binding for the physical state tangent."""

    binding: dict[str, Any]
    profile: str
    contract_hash: str

    def solve_at_state(
        self,
        problem: MaterialGeometricArcLengthStepProblem,
        free_displacements_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        load_factor: float,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve:
        if not isinstance(problem, MaterialGeometricArcLengthStepProblem):
            raise TypeError("FGMRES solver received an incompatible problem")
        state = _finite_two_vector(
            free_displacements_m,
            name="free_displacements_m",
        )
        right_hand_side = _finite_two_vector(
            right_hand_side_kn,
            name="right_hand_side_kn",
        )
        normalized_load_factor = float(load_factor)
        if not math.isfinite(normalized_load_factor):
            raise ValueError("load_factor must be finite")
        identity = np.eye(2, dtype=np.float64)
        tangent = np.column_stack(
            [
                problem.consistent_state_tangent_action_kn_per_m(
                    state,
                    normalized_load_factor,
                    identity[:, column],
                )
                for column in range(2)
            ]
        )
        solve = solve_cpu_fgmres_tangent_system(
            execution_plan=self.binding["plan"],
            scaling=self.binding["scaling"],
            node_coordinates_m=self.binding["coordinates"],
            reference_equation_load_si=self.binding["reference_equation_load"],
            global_csr_values_si=_global_csr_values(self.binding, tangent),
            right_hand_side_free=_KN_TO_N * right_hand_side,
            solution_artifact_uri=(
                "artifact://material-geometric-cpu-fgmres-arc-length/"
                f"{solve_id}/solution_free.f64le"
            ),
            max_iterations=_MAX_ITERATIONS,
            restart_length=_RESTART_LENGTH,
            relative_tolerance_scaled_l2=_RELATIVE_TOLERANCE,
            absolute_tolerance_scaled_l2=_ABSOLUTE_TOLERANCE,
            explicit_residual_tolerance=_EXPLICIT_RESIDUAL_TOLERANCE_N,
        )
        receipt = {
            "schema_version": (MATERIAL_GEOMETRIC_FGMRES_SOLVE_RECEIPT_SCHEMA_VERSION),
            "contract_pass": solve.contract_pass,
            "solve_id": solve_id,
            "accepted_material_parent_state_hash": (problem.accepted_state.state_hash),
            "local_displacements_m": state.tolist(),
            "local_load_factor": normalized_load_factor,
            "tangent_action": MATERIAL_GEOMETRIC_ARC_LENGTH_TANGENT_ACTION,
            "tangent_kn_per_m": tangent.tolist(),
            "matrix_binding": "exact_two_equation_reduced_csr_si_converted",
            "physical_to_engine_force_scale_n_per_kn": _KN_TO_N,
            "execution_plan_hash": self.binding["plan"].plan_hash,
            "scaling_hash": self.binding["scaling"].scaling_hash,
            "engine_v2_tangent_solve": solve.to_manifest(),
        }
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=solve.contract_pass,
            terminal_reason=solve.terminal_reason,
            solution_free=tuple(float(value) for value in solve.solution_free),
            receipt=receipt,
        )


def create_material_geometric_cpu_fgmres_state_tangent_solver(
    problem: StatefulTwoBarTrussProblem,
) -> MaterialGeometricCPUFGMRESStateTangentSolver:
    """Create the dedicated deterministic ExecutionPlan and solver identity."""

    binding = _build_binding(problem)
    contract_hash = canonical_hash(
        {
            "profile": MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE,
            "source_problem_contract_hash": binding["source_problem_contract_hash"],
            "execution_plan_hash": binding["plan"].plan_hash,
            "scaling_hash": binding["scaling"].scaling_hash,
            "operator_mode": VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
            "tangent_action": MATERIAL_GEOMETRIC_ARC_LENGTH_TANGENT_ACTION,
            "free_equation_count": 2,
            "reduced_csr_nnz": 4,
            "max_iterations": _MAX_ITERATIONS,
            "restart_length": _RESTART_LENGTH,
            "relative_tolerance_scaled_l2": _RELATIVE_TOLERANCE,
            "absolute_tolerance_scaled_l2": _ABSOLUTE_TOLERANCE,
            "explicit_residual_tolerance_n": _EXPLICIT_RESIDUAL_TOLERANCE_N,
            "preconditioner_profile": "identity_right_preconditioner.v1",
        }
    )
    return MaterialGeometricCPUFGMRESStateTangentSolver(
        binding=binding,
        profile=MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE,
        contract_hash=contract_hash,
    )


def _tangent_solve_rows(
    result: MaterialGeometricArcLengthResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for physical_attempt in result.attempts:
        for attempt in physical_attempt.vector_result.attempts:
            predictor = attempt.get("predictor_tangent_solve")
            if isinstance(predictor, dict):
                rows.append(predictor)
            for history_row in attempt.get("corrector_history", []):
                metadata = history_row.get("tangent_solve_metadata") or {}
                for key in (
                    "residual_solve",
                    "reference_load_solve",
                    "load_linearization_solve",
                ):
                    row = metadata.get(key)
                    if isinstance(row, dict):
                        rows.append(row)
    return rows


def _accepted_states(result: MaterialGeometricArcLengthResult):
    return [result.initial_state] + [
        attempt.accepted_state for attempt in result.attempts if attempt.committed
    ]


def _maximum_material_state_error(
    left: MaterialGeometricArcLengthResult,
    right: MaterialGeometricArcLengthResult,
) -> float:
    fields = (
        "plastic_strain",
        "backstress_mpa",
        "accumulated_plastic_strain",
        "dissipated_energy_density_mj_per_m3",
    )
    errors = [
        abs(float(getattr(left_state, field)) - float(getattr(right_state, field)))
        for left_state, right_state in zip(
            left.final_state.material_states,
            right.final_state.material_states,
            strict=True,
        )
        for field in fields
    ]
    return max(errors, default=0.0)


@lru_cache(maxsize=1)
def _build_material_geometric_cpu_fgmres_arc_length_benchmark_cached() -> dict[
    str, Any
]:
    problem = StatefulTwoBarTrussProblem()
    solver = create_material_geometric_cpu_fgmres_state_tangent_solver(problem)
    first = stateful_material_geometric_arc_length_continuation(
        problem,
        state_tangent_solver=solver,
    )
    repeated = stateful_material_geometric_arc_length_continuation(
        problem,
        state_tangent_solver=solver,
    )
    restart_boundary = next(
        checkpoint
        for checkpoint in first.checkpoints
        if checkpoint.last_attempt_outcome == "rolled_back"
    )
    restarted = stateful_material_geometric_arc_length_continuation(
        problem,
        checkpoint=restart_boundary,
        state_tangent_solver=solver,
    )
    dense_reference = stateful_material_geometric_arc_length_continuation(problem)

    first_states = _accepted_states(first)
    dense_states = _accepted_states(dense_reference)
    same_state_count = len(first_states) == len(dense_states)
    if same_state_count:
        displacement_error = max(
            abs(left_value - right_value)
            for left_state, right_state in zip(first_states, dense_states, strict=True)
            for left_value, right_value in zip(
                left_state.apex_displacements_m,
                right_state.apex_displacements_m,
                strict=True,
            )
        )
        load_factor_error = max(
            abs(left_state.load_factor - right_state.load_factor)
            for left_state, right_state in zip(first_states, dense_states, strict=True)
        )
    else:
        displacement_error = math.inf
        load_factor_error = math.inf
    material_state_error = _maximum_material_state_error(first, dense_reference)
    dense_reference_gate = bool(
        dense_reference.status == "ready"
        and same_state_count
        and displacement_error <= 1.0e-10
        and load_factor_error <= 1.0e-10
        and material_state_error <= 1.0e-9
    )

    rows = _tangent_solve_rows(first)
    engine_receipts = [row["receipt"]["engine_v2_tangent_solve"] for row in rows]
    maximum_tangent_residual = max(
        (float(row["explicit_residual_inf_norm_kn"]) for row in rows),
        default=math.inf,
    )
    maximum_iteration_count = max(
        (int(receipt["solver"]["iteration_count"]) for receipt in engine_receipts),
        default=0,
    )
    maximum_matvec_count = max(
        (int(receipt["solver"]["matvec_count"]) for receipt in engine_receipts),
        default=0,
    )
    every_tangent_solve_gate = bool(
        rows
        and len(rows) == first.metrics["tangent_solve_count"]
        and all(row["profile"] == solver.profile for row in rows)
        and all(row["contract_hash"] == solver.contract_hash for row in rows)
        and all(receipt["contract_pass"] is True for receipt in engine_receipts)
        and all(
            receipt["profile"] == CPU_FGMRES_TANGENT_SOLVE_PROFILE
            for receipt in engine_receipts
        )
        and maximum_tangent_residual
        <= MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG.tangent_solve_residual_tolerance_kn
    )
    plan = solver.binding["plan"]
    row_ptr = plan.array("csr_row_ptr")
    reduced_nnz = sum(
        int(row_ptr[int(global_dof) + 1]) - int(row_ptr[int(global_dof)])
        for global_dof in plan.array("free_dofs")
    )
    binding_gate = bool(
        int(plan.array("free_dofs").size) == 2
        and int(plan.array("csr_column_indices").size) == 20
        and reduced_nnz == 4
        and all(receipt["solver"]["free_count"] == 2 for receipt in engine_receipts)
        and all(
            receipt["source"]["execution_plan_hash"] == plan.plan_hash
            for receipt in engine_receipts
        )
        and all(
            receipt["source"]["scaling_hash"] == solver.binding["scaling"].scaling_hash
            for receipt in engine_receipts
        )
    )
    deterministic_replay_exact = first.to_dict() == repeated.to_dict()
    checkpoint_restart_exact = restarted.final_checkpoint == first.final_checkpoint
    contract_pass = bool(
        first.status == "ready"
        and first.metrics["contract_pass"] is True
        and first.metrics["tangent_solver_profile"] == solver.profile
        and first.metrics["tangent_solver_contract_hash"] == solver.contract_hash
        and first.metrics["fallback_count"] == 0
        and first.metrics["regularization_count"] == 0
        and every_tangent_solve_gate
        and binding_gate
        and deterministic_replay_exact
        and checkpoint_restart_exact
        and dense_reference_gate
    )
    return {
        "schema_version": (MATERIAL_GEOMETRIC_FGMRES_ARC_LENGTH_SCHEMA_VERSION),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": "stateful_material_geometric_two_bar_cpu_fgmres_arc_length",
        "analysis_type": (
            "stateful_material_geometric_vector_arc_length_cpu_fgmres_"
            "tangent_integration"
        ),
        "state_tangent_solver_profile": solver.profile,
        "state_tangent_solver_contract_hash": solver.contract_hash,
        "execution_plan_hash": plan.plan_hash,
        "equation_scaling_hash": solver.binding["scaling"].scaling_hash,
        "reduced_equation_count": 2,
        "reduced_csr_nnz": reduced_nnz,
        "solver_result": first.to_dict(),
        "verification": {
            "engine_v2_cpu_fgmres_every_tangent_solve": (every_tangent_solve_gate),
            "execution_plan_equation_scaling_binding_passed": binding_gate,
            "deterministic_replay_exact": deterministic_replay_exact,
            "checkpoint_restart_exact": checkpoint_restart_exact,
            "restart_boundary_outcome": restart_boundary.last_attempt_outcome,
            "dense_reference_path_gate_passed": dense_reference_gate,
            "same_dense_reference_accepted_state_count": same_state_count,
            "maximum_dense_reference_displacement_absolute_error_m": (
                displacement_error
            ),
            "maximum_dense_reference_load_factor_absolute_error": (load_factor_error),
            "maximum_dense_reference_material_state_absolute_error": (
                material_state_error
            ),
            "tangent_solve_count": len(rows),
            "maximum_tangent_solve_explicit_residual_inf_norm_kn": (
                maximum_tangent_residual
            ),
            "maximum_tangent_solve_iteration_count": maximum_iteration_count,
            "maximum_tangent_solve_matvec_count": maximum_matvec_count,
            "accepted_step_count": first.metrics["accepted_step_count"],
            "rejected_step_count": first.metrics["rejected_step_count"],
            "descending_load_branch_observed": first.metrics[
                "descending_load_branch_observed"
            ],
            "fallback_count": first.metrics["fallback_count"],
            "regularization_count": first.metrics["regularization_count"],
        },
        "verification_hierarchy": {
            "level_1_analytic_and_dense_reference": contract_pass,
            "level_2_external_code_to_code": False,
            "level_3_published_benchmark": False,
            "level_4_experimental": False,
            "level_5_customer_shadow": False,
        },
        "claims": {
            "bounded_material_geometric_arc_length_cpu_fgmres": contract_pass,
            "engine_v2_cpu_fgmres_every_tangent_solve": (every_tangent_solve_gate),
            "execution_plan_equation_scaling_bound": binding_gate,
            "dense_reference_path_equivalence": dense_reference_gate,
            "deterministic_checkpoint_restart": checkpoint_restart_exact,
            "general_2d_3d_truss_frame_shell": False,
            "production_scale_sparse_preconditioner": False,
            "finite_strain_constitutive_behavior": False,
            "production_rocm_hip_nonlinear_parity": False,
            "durable_serialized_checkpoint": False,
            "external_validation": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "general_truss_frame_shell_material_geometric_adapter_missing",
            "two_equation_reduced_csr_does_not_prove_production_scale_sparsity",
            "production_preconditioner_effectiveness_not_verified",
            "finite_strain_constitutive_model_not_implemented",
            "production_rocm_hip_nonlinear_parity_not_verified",
            "checkpoint_is_in_memory_not_a_durable_artifact",
            "external_code_to_code_and_experimental_receipts_missing",
            "full_building_material_geometric_equilibrium_not_demonstrated",
            "g1_closure_not_claimed",
        ],
        "claim_boundary": MATERIAL_GEOMETRIC_FGMRES_CLAIM_BOUNDARY,
    }


def build_material_geometric_cpu_fgmres_arc_length_benchmark() -> dict[str, Any]:
    """Return an isolated copy of the deterministic integration receipt."""

    return deepcopy(_build_material_geometric_cpu_fgmres_arc_length_benchmark_cached())


__all__ = [
    "MATERIAL_GEOMETRIC_FGMRES_ARC_LENGTH_SCHEMA_VERSION",
    "MATERIAL_GEOMETRIC_FGMRES_CLAIM_BOUNDARY",
    "MATERIAL_GEOMETRIC_FGMRES_SOLVE_RECEIPT_SCHEMA_VERSION",
    "MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE",
    "MaterialGeometricCPUFGMRESStateTangentSolver",
    "build_material_geometric_cpu_fgmres_arc_length_benchmark",
    "create_material_geometric_cpu_fgmres_state_tangent_solver",
]
