"""CPU FGMRES tangent-solve bridge for vector arc-length correctors."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.benchmark.coupled_shallow_arch_arc_length import (
    CoupledShallowArchArcLengthProblem,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan import (
    create_execution_plan,
)
from structural_analysis.engine_v2.cpu_fgmres_tangent import (
    CPU_FGMRES_TANGENT_SOLVE_PROFILE,
    solve_cpu_fgmres_tangent_system,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthTangentSolve,
)


ARC_LENGTH_FGMRES_BRIDGE_SCHEMA_VERSION = (
    "phase2-arc-length-cpu-fgmres-tangent-bridge.v1"
)
ARC_LENGTH_FGMRES_BRIDGE_CLAIM_BOUNDARY = (
    "This receipt verifies deterministic CPU FGMRES tangent solves and Schur "
    "equivalence to one dense augmented arc-length correction on three analytic "
    "two-DOF states. It does not run the complete continuation loop through the "
    "Engine v2 adapter, assemble a frame/shell residual, prove a production sparse "
    "nonlinear backend, establish ROCm/HIP parity, close full-building G1, or "
    "provide release-readiness evidence."
)
ARC_LENGTH_CPU_FGMRES_VECTOR_TANGENT_SOLVER_PROFILE = (
    "vector_arc_length_schur_engine_v2_cpu_fgmres.v1"
)


@dataclass(frozen=True)
class ArcLengthCPUFGMRESTangentSolver:
    """Benchmark binding from dense vector tangents to Engine v2 FGMRES."""

    binding: dict[str, Any]
    profile: str
    contract_hash: str

    def solve(
        self,
        tangent_kn_per_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve:
        solve = _fgmres_solve(
            binding=self.binding,
            tangent=tangent_kn_per_m,
            right_hand_side=right_hand_side_kn,
            artifact_id=solve_id,
        )
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=solve.contract_pass,
            terminal_reason=solve.terminal_reason,
            solution_free=tuple(float(value) for value in solve.solution_free),
            receipt=solve.to_manifest(),
        )


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _build_binding() -> dict[str, Any]:
    dof_count = 12
    free_dofs = np.asarray([6, 7], dtype="<i4")
    constrained_dofs = np.asarray(
        [0, 1, 2, 3, 4, 5, 8, 9, 10, 11],
        dtype="<i4",
    )
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free_dofs] = np.arange(free_dofs.size, dtype="<i4")
    base = create_execution_plan(
        model_ir_content_hash=_hash("a"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("b"),
        solver_entity_mapping_hash=_hash("c"),
        solver_artifact_hash=_hash("d"),
        load_pattern_id="ARC_LENGTH_TANGENT_BRIDGE",
        operator_id="coupled-shallow-arch-consistent-tangent",
        operator_version="coupled-shallow-arch-consistent-tangent.v1",
        operator_hash=_hash("e"),
        node_ids=("FIXED", "FREE"),
        element_ids=("ANALYTIC_COUPLING",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained_dofs,
        free_dofs=free_dofs,
        csr_row_ptr=np.arange(
            0,
            dof_count * dof_count + 1,
            dof_count,
            dtype="<i8",
        ),
        csr_column_indices=np.tile(
            np.arange(dof_count, dtype="<i4"),
            dof_count,
        ),
    )
    coordinates = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        dtype="<f8",
    )
    reference_equation_load = np.zeros(dof_count, dtype="<f8")
    reference_equation_load[free_dofs] = np.asarray([1.0, 1.0])
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_equation_load,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_equation_load,
    )
    return {
        "plan": plan,
        "scaling": scaling,
        "coordinates": coordinates,
        "reference_equation_load": reference_equation_load,
        "free_dofs": free_dofs,
    }


def create_arc_length_cpu_fgmres_tangent_solver() -> (
    ArcLengthCPUFGMRESTangentSolver
):
    """Create the fixed analytic benchmark binding and its contract hash."""

    binding = _build_binding()
    plan = binding["plan"]
    scaling = binding["scaling"]
    contract_hash = canonical_hash(
        {
            "profile": ARC_LENGTH_CPU_FGMRES_VECTOR_TANGENT_SOLVER_PROFILE,
            "execution_plan_hash": plan.plan_hash,
            "scaling_hash": scaling.scaling_hash,
            "free_dofs": binding["free_dofs"].tolist(),
            "max_iterations": 4,
            "restart_length": 2,
            "relative_tolerance_scaled_l2": 1.0e-13,
            "absolute_tolerance_scaled_l2": 1.0e-14,
            "explicit_residual_tolerance": 1.0e-12,
            "preconditioner_profile": "identity_right_preconditioner.v1",
        }
    )
    return ArcLengthCPUFGMRESTangentSolver(
        binding=binding,
        profile=ARC_LENGTH_CPU_FGMRES_VECTOR_TANGENT_SOLVER_PROFILE,
        contract_hash=contract_hash,
    )


def _embed_tangent(binding: dict[str, Any], tangent: np.ndarray) -> np.ndarray:
    plan = binding["plan"]
    free_dofs = binding["free_dofs"]
    values = np.zeros(plan.array("csr_column_indices").size, dtype="<f8")
    for row, global_row in enumerate(free_dofs):
        for column, global_column in enumerate(free_dofs):
            values[
                int(global_row) * plan.dof_count + int(global_column)
            ] = tangent[row, column]
    return values


def _fgmres_solve(
    *,
    binding: dict[str, Any],
    tangent: np.ndarray,
    right_hand_side: np.ndarray,
    artifact_id: str,
):
    return solve_cpu_fgmres_tangent_system(
        execution_plan=binding["plan"],
        scaling=binding["scaling"],
        node_coordinates_m=binding["coordinates"],
        reference_equation_load_si=binding["reference_equation_load"],
        global_csr_values_si=_embed_tangent(binding, tangent),
        right_hand_side_free=right_hand_side,
        solution_artifact_uri=(
            f"artifact://arc-length-fgmres-bridge/{artifact_id}/"
            "solution_free.f64le"
        ),
        max_iterations=4,
        restart_length=2,
        relative_tolerance_scaled_l2=1.0e-13,
        absolute_tolerance_scaled_l2=1.0e-14,
        explicit_residual_tolerance=1.0e-12,
    )


def _bridge_row(
    *,
    problem: CoupledShallowArchArcLengthProblem,
    binding: dict[str, Any],
    state_id: str,
    primary_displacement_m: float,
) -> dict[str, Any]:
    accepted_displacements = np.asarray(
        [
            primary_displacement_m,
            problem.coupling_ratio * primary_displacement_m,
        ],
        dtype="<f8",
    )
    accepted_load_factor = problem.arch.internal_force_kn(
        primary_displacement_m
    )
    delta_displacements = np.asarray([0.012, -0.004], dtype="<f8")
    delta_load_factor = 0.5
    trial_displacements = accepted_displacements + delta_displacements
    trial_load_factor = accepted_load_factor + delta_load_factor
    reference_load = problem.reference_load_kn()
    residual = (
        problem.internal_force_kn(trial_displacements)
        - trial_load_factor * reference_load
    )
    tangent = problem.consistent_tangent_kn_per_m(trial_displacements)
    load_metric_scale_m = 0.002
    exact_increment_norm = math.sqrt(
        float(np.dot(delta_displacements, delta_displacements))
        + (load_metric_scale_m * delta_load_factor) ** 2
    )
    arc_length_m = 0.93 * exact_increment_norm
    constraint_residual = float(
        np.dot(delta_displacements, delta_displacements)
        + (load_metric_scale_m * delta_load_factor) ** 2
        - arc_length_m**2
    )
    constraint_displacement = 2.0 * delta_displacements
    constraint_load = 2.0 * load_metric_scale_m**2 * delta_load_factor

    residual_solve = _fgmres_solve(
        binding=binding,
        tangent=tangent,
        right_hand_side=-residual,
        artifact_id=f"{state_id}-residual",
    )
    load_solve = _fgmres_solve(
        binding=binding,
        tangent=tangent,
        right_hand_side=reference_load,
        artifact_id=f"{state_id}-reference-load",
    )
    residual_direction = residual_solve.solution_free
    load_direction = load_solve.solution_free
    schur_denominator = float(
        np.dot(constraint_displacement, load_direction) + constraint_load
    )
    schur_load_correction = float(
        (
            -constraint_residual
            - np.dot(constraint_displacement, residual_direction)
        )
        / schur_denominator
    )
    schur_displacement_correction = (
        residual_direction + load_direction * schur_load_correction
    )
    augmented = np.empty((3, 3), dtype="<f8")
    augmented[:2, :2] = tangent
    augmented[:2, 2] = -reference_load
    augmented[2, :2] = constraint_displacement
    augmented[2, 2] = constraint_load
    direct_correction = np.linalg.solve(
        augmented,
        -np.concatenate((residual, np.asarray([constraint_residual]))),
    )
    schur_correction = np.concatenate(
        (
            schur_displacement_correction,
            np.asarray([schur_load_correction]),
        )
    )
    correction_absolute_error = float(
        np.linalg.norm(schur_correction - direct_correction, ord=np.inf)
    )
    augmented_linear_residual = augmented @ schur_correction + np.concatenate(
        (residual, np.asarray([constraint_residual]))
    )
    augmented_linear_residual_inf = float(
        np.linalg.norm(augmented_linear_residual, ord=np.inf)
    )
    direct_residual_solution_error = float(
        np.linalg.norm(
            residual_direction - np.linalg.solve(tangent, -residual),
            ord=np.inf,
        )
    )
    direct_load_solution_error = float(
        np.linalg.norm(
            load_direction - np.linalg.solve(tangent, reference_load),
            ord=np.inf,
        )
    )
    contract_pass = bool(
        residual_solve.contract_pass
        and load_solve.contract_pass
        and correction_absolute_error <= 1.0e-12
        and augmented_linear_residual_inf <= 1.0e-12
        and direct_residual_solution_error <= 1.0e-12
        and direct_load_solution_error <= 1.0e-12
    )
    return {
        "state_id": state_id,
        "accepted_free_displacements_m": accepted_displacements.tolist(),
        "accepted_load_factor": accepted_load_factor,
        "trial_free_displacements_m": trial_displacements.tolist(),
        "trial_load_factor": trial_load_factor,
        "consistent_tangent_kn_per_m": tangent.tolist(),
        "consistent_tangent_determinant": float(np.linalg.det(tangent)),
        "residual_kn": residual.tolist(),
        "constraint_residual_m2": constraint_residual,
        "constraint_displacement_gradient_m": (
            constraint_displacement.tolist()
        ),
        "constraint_load_factor_gradient_m2": constraint_load,
        "schur_denominator": schur_denominator,
        "schur_correction": schur_correction.tolist(),
        "direct_augmented_correction": direct_correction.tolist(),
        "maximum_correction_absolute_error": correction_absolute_error,
        "augmented_linear_residual_inf_norm": augmented_linear_residual_inf,
        "residual_tangent_solve_direct_absolute_error": (
            direct_residual_solution_error
        ),
        "reference_load_tangent_solve_direct_absolute_error": (
            direct_load_solution_error
        ),
        "residual_tangent_solve": residual_solve.to_manifest(),
        "reference_load_tangent_solve": load_solve.to_manifest(),
        "contract_pass": contract_pass,
    }


def build_arc_length_cpu_fgmres_tangent_bridge_seed() -> dict[str, Any]:
    """Build pre-limit, descending, and rehardening tangent bridge evidence."""

    problem = CoupledShallowArchArcLengthProblem()
    binding = _build_binding()
    rows = [
        _bridge_row(
            problem=problem,
            binding=binding,
            state_id=state_id,
            primary_displacement_m=displacement,
        )
        for state_id, displacement in (
            ("pre_limit_positive_tangent", 0.03),
            ("descending_negative_tangent", 0.20),
            ("rehardening_positive_tangent", 0.44),
        )
    ]
    replay_rows = [
        _bridge_row(
            problem=problem,
            binding=binding,
            state_id=state_id,
            primary_displacement_m=displacement,
        )
        for state_id, displacement in (
            ("pre_limit_positive_tangent", 0.03),
            ("descending_negative_tangent", 0.20),
            ("rehardening_positive_tangent", 0.44),
        )
    ]
    deterministic_replay_exact = rows == replay_rows
    all_tangent_solves_ready = all(
        row[solve_name]["contract_pass"] is True
        for row in rows
        for solve_name in (
            "residual_tangent_solve",
            "reference_load_tangent_solve",
        )
    )
    determinant_sign_coverage = bool(
        rows[0]["consistent_tangent_determinant"] > 0.0
        and rows[1]["consistent_tangent_determinant"] < 0.0
        and rows[2]["consistent_tangent_determinant"] > 0.0
    )
    schur_equivalence_pass = bool(
        all(row["contract_pass"] is True for row in rows)
        and max(row["maximum_correction_absolute_error"] for row in rows)
        <= 1.0e-12
        and max(row["augmented_linear_residual_inf_norm"] for row in rows)
        <= 1.0e-12
    )
    contract_pass = bool(
        all_tangent_solves_ready
        and determinant_sign_coverage
        and schur_equivalence_pass
        and deterministic_replay_exact
    )
    return {
        "schema_version": ARC_LENGTH_FGMRES_BRIDGE_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": "coupled_shallow_arch_cpu_fgmres_tangent_bridge",
        "analysis_type": "arc_length_schur_tangent_solve_bridge",
        "linear_solver_profile": CPU_FGMRES_TANGENT_SOLVE_PROFILE,
        "state_rows": rows,
        "verification": {
            "all_tangent_solves_ready": all_tangent_solves_ready,
            "positive_negative_positive_determinant_coverage": (
                determinant_sign_coverage
            ),
            "schur_augmented_correction_equivalence": schur_equivalence_pass,
            "deterministic_replay_exact": deterministic_replay_exact,
            "maximum_correction_absolute_error": max(
                row["maximum_correction_absolute_error"] for row in rows
            ),
            "maximum_augmented_linear_residual_inf_norm": max(
                row["augmented_linear_residual_inf_norm"] for row in rows
            ),
            "maximum_tangent_solve_explicit_residual_inf_norm": max(
                row[solve_name]["explicit_residual"]["inf_norm"]
                for row in rows
                for solve_name in (
                    "residual_tangent_solve",
                    "reference_load_tangent_solve",
                )
            ),
            "tangent_solve_count": 2 * len(rows),
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "claims": {
            "engine_v2_cpu_fgmres_tangent_bridge": contract_pass,
            "schur_augmented_increment_equivalence": schur_equivalence_pass,
            "indefinite_tangent_solve": bool(
                all_tangent_solves_ready
                and rows[1]["consistent_tangent_determinant"] < 0.0
            ),
            "complete_arc_length_backend_integration": False,
            "frame_shell_residual_assembly": False,
            "production_sparse_nonlinear_backend": False,
            "production_rocm_hip_parity": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "complete_continuation_loop_not_using_engine_v2_tangent_adapter",
            "frame_shell_residual_assembly_not_connected",
            "production_sparse_nonlinear_backend_not_verified",
            "production_rocm_hip_parity_not_verified",
            "g1_full_load_full_mesh_not_closed",
        ],
        "claim_boundary": ARC_LENGTH_FGMRES_BRIDGE_CLAIM_BOUNDARY,
    }


__all__ = [
    "ARC_LENGTH_CPU_FGMRES_VECTOR_TANGENT_SOLVER_PROFILE",
    "ARC_LENGTH_FGMRES_BRIDGE_CLAIM_BOUNDARY",
    "ARC_LENGTH_FGMRES_BRIDGE_SCHEMA_VERSION",
    "ArcLengthCPUFGMRESTangentSolver",
    "build_arc_length_cpu_fgmres_tangent_bridge_seed",
    "create_arc_length_cpu_fgmres_tangent_solver",
]
