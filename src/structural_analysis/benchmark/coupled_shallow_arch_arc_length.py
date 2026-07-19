"""Coupled two-DOF verification seed for vector spherical arc length."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from structural_analysis.benchmark.geometric_nonlinear import TwoBarShallowArch
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthConfig,
    vector_arc_length_continuation,
)


COUPLED_SHALLOW_ARCH_ARC_LENGTH_SCHEMA_VERSION = (
    "phase2-coupled-shallow-arch-vector-arc-length.v1"
)
COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY = (
    "This receipt verifies the dense vector spherical arc-length kernel on one "
    "analytic coupled two-DOF shallow-arch potential. It does not verify a frame "
    "or shell element formulation, the Lee frame, material-geometric coupling, "
    "published or experimental validation, a sparse backend, ROCm/HIP parity, "
    "full-building equilibrium, or G1 closure."
)
COUPLED_SHALLOW_ARCH_VECTOR_ARC_LENGTH_CONFIG = VectorArcLengthConfig(
    failed_step_reduction=0.25,
    maximum_corrector_iterations=5,
)


@dataclass(frozen=True)
class CoupledShallowArchArcLengthProblem:
    """Two-DOF conservative potential with an exact scalar reduction."""

    case_id: str = "coupled_two_dof_shallow_arch_vector_arc_length"
    arch: TwoBarShallowArch = field(default_factory=TwoBarShallowArch)
    coupling_ratio: float = 0.35
    coupling_stiffness_kn_per_m: float = 400.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(2, dtype=float)

    def initial_load_factor(self) -> float:
        return 0.0

    def reference_load_kn(self) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=float)

    def _coupling_extension_m(self, free_displacements_m: np.ndarray) -> float:
        primary, coupled = free_displacements_m
        return float(coupled - self.coupling_ratio * primary)

    def internal_force_kn(self, free_displacements_m: np.ndarray) -> np.ndarray:
        primary = float(free_displacements_m[0])
        coupling_extension = self._coupling_extension_m(free_displacements_m)
        coupling_force = self.coupling_stiffness_kn_per_m * coupling_extension
        return np.asarray(
            [
                self.arch.internal_force_kn(primary)
                - self.coupling_ratio * coupling_force,
                coupling_force,
            ],
            dtype=float,
        )

    def consistent_tangent_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray:
        primary = float(free_displacements_m[0])
        coupling = self.coupling_ratio
        stiffness = self.coupling_stiffness_kn_per_m
        return np.asarray(
            [
                [
                    self.arch.consistent_tangent_kn_per_m(primary)
                    + stiffness * coupling**2,
                    -stiffness * coupling,
                ],
                [-stiffness * coupling, stiffness],
            ],
            dtype=float,
        )

    def strain_energy_kn_m(self, free_displacements_m: np.ndarray) -> float:
        primary = float(free_displacements_m[0])
        coupling_extension = self._coupling_extension_m(free_displacements_m)
        return float(
            self.arch.strain_energy_kn_m(primary)
            + 0.5
            * self.coupling_stiffness_kn_per_m
            * coupling_extension**2
        )


def _first_local_maximum(values: list[float]) -> int | None:
    for index in range(1, len(values) - 1):
        if values[index] > values[index - 1] and values[index] > values[index + 1]:
            return index
    return None


def _finite_difference_row(
    problem: CoupledShallowArchArcLengthProblem,
    primary_displacement_m: float,
) -> dict[str, Any]:
    displacement = np.asarray(
        [
            primary_displacement_m,
            problem.coupling_ratio * primary_displacement_m + 0.003,
        ],
        dtype=float,
    )
    step_m = 3.0e-6
    identity = np.eye(2, dtype=float)
    tangent_fd = np.column_stack(
        [
            (
                problem.internal_force_kn(displacement + step_m * identity[:, column])
                - problem.internal_force_kn(
                    displacement - step_m * identity[:, column]
                )
            )
            / (2.0 * step_m)
            for column in range(2)
        ]
    )
    energy_gradient_fd = np.asarray(
        [
            (
                problem.strain_energy_kn_m(
                    displacement + step_m * identity[:, column]
                )
                - problem.strain_energy_kn_m(
                    displacement - step_m * identity[:, column]
                )
            )
            / (2.0 * step_m)
            for column in range(2)
        ],
        dtype=float,
    )
    tangent = problem.consistent_tangent_kn_per_m(displacement)
    internal_force = problem.internal_force_kn(displacement)
    tangent_absolute_error = float(np.max(np.abs(tangent_fd - tangent)))
    energy_gradient_absolute_error = float(
        np.max(np.abs(energy_gradient_fd - internal_force))
    )
    symmetry_absolute_error = float(np.max(np.abs(tangent - tangent.T)))
    tangent_allowed_error = 1.0e-6
    energy_allowed_error = 1.0e-7
    return {
        "free_displacements_m": displacement.tolist(),
        "finite_difference_step_m": step_m,
        "consistent_tangent_kn_per_m": tangent.tolist(),
        "finite_difference_tangent_kn_per_m": tangent_fd.tolist(),
        "internal_force_kn": internal_force.tolist(),
        "finite_difference_energy_gradient_kn": energy_gradient_fd.tolist(),
        "maximum_tangent_absolute_error_kn_per_m": tangent_absolute_error,
        "maximum_energy_gradient_absolute_error_kn": (
            energy_gradient_absolute_error
        ),
        "tangent_symmetry_absolute_error_kn_per_m": symmetry_absolute_error,
        "tangent_allowed_error_kn_per_m": tangent_allowed_error,
        "energy_gradient_allowed_error_kn": energy_allowed_error,
        "contract_pass": bool(
            tangent_absolute_error <= tangent_allowed_error
            and energy_gradient_absolute_error <= energy_allowed_error
            and symmetry_absolute_error == 0.0
        ),
    }


def build_coupled_shallow_arch_vector_arc_length_benchmark_seed(
    *,
    config: VectorArcLengthConfig | None = None,
) -> dict[str, Any]:
    """Build deterministic coupled path, tangent, rollback, and restart evidence."""

    problem = CoupledShallowArchArcLengthProblem()
    solver_config = config or COUPLED_SHALLOW_ARCH_VECTOR_ARC_LENGTH_CONFIG
    first = vector_arc_length_continuation(problem, config=solver_config)
    second = vector_arc_length_continuation(problem, config=solver_config)
    deterministic_replay_exact = first.to_dict() == second.to_dict()
    restart_checkpoint = first.checkpoints[len(first.checkpoints) // 2]
    restarted = vector_arc_length_continuation(
        problem,
        config=solver_config,
        resume_from=restart_checkpoint,
    )
    checkpoint_restart_exact = restarted.final_checkpoint == first.final_checkpoint

    exact_limit_displacement, exact_limit_load = problem.arch.first_limit_point()
    checkpoints = list(first.checkpoints)
    load_factors = [row.load_factor for row in checkpoints]
    below = max(
        (
            row
            for row in checkpoints
            if row.free_displacements_m[0] < exact_limit_displacement
        ),
        key=lambda row: row.free_displacements_m[0],
    )
    above = min(
        (
            row
            for row in checkpoints
            if row.free_displacements_m[0] > exact_limit_displacement
        ),
        key=lambda row: row.free_displacements_m[0],
    )
    local_maximum_index = _first_local_maximum(load_factors)
    local_maximum_load = (
        load_factors[local_maximum_index]
        if local_maximum_index is not None
        else math.nan
    )
    limit_load_relative_error = abs(
        local_maximum_load - exact_limit_load
    ) / exact_limit_load

    coupling_relation_errors = [
        abs(
            row.free_displacements_m[1]
            - problem.coupling_ratio * row.free_displacements_m[0]
        )
        for row in checkpoints
    ]
    reduced_equilibrium_errors = [
        abs(
            row.load_factor
            - problem.arch.internal_force_kn(row.free_displacements_m[0])
        )
        for row in checkpoints
    ]
    finite_difference_rows = [
        _finite_difference_row(problem, displacement)
        for displacement in (
            0.03,
            0.07,
            exact_limit_displacement,
            0.20,
            0.32,
            0.44,
        )
    ]
    rejected_attempts = [
        row for row in first.attempts if row["accepted"] is False
    ]
    rollback_gate_pass = bool(
        rejected_attempts
        and all(
            row["rollback_exact"] is True
            and row["accepted_state_hash_before"]
            == row["accepted_state_hash_after"]
            for row in rejected_attempts
        )
    )
    path_metrics = first.metrics
    path_gate_pass = bool(
        first.status == "ready"
        and path_metrics["contract_pass"] is True
        and path_metrics["equation_count"] == 2
        and path_metrics["descending_load_branch_observed"] is True
        and path_metrics["negative_load_factor_observed"] is True
        and path_metrics["rehardening_load_branch_observed"] is True
        and path_metrics["fallback_count"] == 0
        and path_metrics["regularization_count"] == 0
    )
    exact_reduction_gate_pass = bool(
        max(coupling_relation_errors) <= 1.0e-12
        and max(reduced_equilibrium_errors) <= solver_config.residual_tolerance_kn
    )
    limit_point_gate_pass = bool(
        below.free_displacements_m[0]
        < exact_limit_displacement
        < above.free_displacements_m[0]
        and local_maximum_index is not None
        and limit_load_relative_error <= 0.01
    )
    finite_difference_gate_pass = bool(
        finite_difference_rows
        and all(row["contract_pass"] for row in finite_difference_rows)
    )
    contract_pass = bool(
        path_gate_pass
        and exact_reduction_gate_pass
        and limit_point_gate_pass
        and finite_difference_gate_pass
        and rollback_gate_pass
        and checkpoint_restart_exact
        and deterministic_replay_exact
    )
    return {
        "schema_version": COUPLED_SHALLOW_ARCH_ARC_LENGTH_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": problem.case_id,
        "analysis_type": "dense_vector_spherical_arc_length_continuation",
        "truth_basis": "analytic_coupled_two_dof_conservative_potential",
        "problem_definition": {
            "equation_count": 2,
            "coupling_ratio": problem.coupling_ratio,
            "coupling_stiffness_kn_per_m": problem.coupling_stiffness_kn_per_m,
            "reference_load_kn": problem.reference_load_kn().tolist(),
            "exact_reduction": (
                "u1=coupling_ratio*u0; load_factor=shallow_arch_force(u0)"
            ),
        },
        "solver_result": first.to_dict(),
        "verification": {
            "path_gate_passed": path_gate_pass,
            "exact_scalar_reduction_gate_passed": exact_reduction_gate_pass,
            "limit_point_gate_passed": limit_point_gate_pass,
            "tangent_energy_finite_difference_gate_passed": (
                finite_difference_gate_pass
            ),
            "rollback_evidence_passed": rollback_gate_pass,
            "checkpoint_restart_exact": checkpoint_restart_exact,
            "deterministic_replay_exact": deterministic_replay_exact,
            "path_contract_hash": first.path_contract_hash,
            "restart_checkpoint_state_hash": restart_checkpoint.state_hash,
            "final_checkpoint_state_hash": first.final_checkpoint.state_hash,
            "restarted_final_checkpoint_state_hash": (
                restarted.final_checkpoint.state_hash
            ),
        },
        "exact_reduction_errors": {
            "maximum_coupling_relation_absolute_error_m": max(
                coupling_relation_errors
            ),
            "maximum_reduced_equilibrium_absolute_error_kn": max(
                reduced_equilibrium_errors
            ),
            "contract_pass": exact_reduction_gate_pass,
        },
        "exact_first_limit_point": {
            "primary_displacement_m": exact_limit_displacement,
            "coupled_displacement_m": (
                problem.coupling_ratio * exact_limit_displacement
            ),
            "load_factor": exact_limit_load,
        },
        "computed_first_limit_bracket": {
            "below_step_index": below.step_index,
            "below_primary_displacement_m": below.free_displacements_m[0],
            "below_load_factor": below.load_factor,
            "above_step_index": above.step_index,
            "above_primary_displacement_m": above.free_displacements_m[0],
            "above_load_factor": above.load_factor,
            "first_local_maximum_step_index": local_maximum_index,
            "first_local_maximum_load_factor": local_maximum_load,
            "first_limit_load_relative_error": limit_load_relative_error,
            "relative_tolerance": 0.01,
            "contract_pass": limit_point_gate_pass,
        },
        "finite_difference_rows": finite_difference_rows,
        "claims": {
            "dense_multi_dof_vector_arc_length": contract_pass,
            "coupled_two_dof_limit_point_crossing": contract_pass,
            "consistent_vector_tangent": finite_difference_gate_pass,
            "failed_step_rollback": rollback_gate_pass,
            "checkpoint_restart": checkpoint_restart_exact,
            "general_frame_shell_arc_length": False,
            "lee_frame_snapthrough": False,
            "material_geometric_coupling": False,
            "published_or_experimental_validation": False,
            "production_sparse_backend": False,
            "production_rocm_hip_parity": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "frame_shell_element_formulation_not_connected",
            "lee_frame_snapthrough_not_implemented",
            "material_geometric_coupling_not_verified",
            "published_or_experimental_validation_not_attached",
            "production_sparse_backend_not_implemented",
            "production_rocm_hip_parity_not_verified",
            "g1_full_load_full_mesh_not_closed",
        ],
        "claim_boundary": COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    }


__all__ = [
    "COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY",
    "COUPLED_SHALLOW_ARCH_ARC_LENGTH_SCHEMA_VERSION",
    "COUPLED_SHALLOW_ARCH_VECTOR_ARC_LENGTH_CONFIG",
    "CoupledShallowArchArcLengthProblem",
    "build_coupled_shallow_arch_vector_arc_length_benchmark_seed",
]
