"""Verified scalar arc-length path for the exact two-bar shallow arch."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from structural_analysis.benchmark.geometric_nonlinear import TwoBarShallowArch
from structural_analysis.solvers.nonlinear.arc_length import (
    ScalarArcLengthConfig,
    scalar_arc_length_continuation,
)


SHALLOW_ARCH_ARC_LENGTH_SCHEMA_VERSION = (
    "phase2-shallow-arch-arc-length-benchmark.v1"
)
SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY = (
    "This receipt verifies one scalar spherical arc-length implementation on the "
    "exact symmetric two-bar shallow arch. It crosses the first limit point and "
    "follows descending, negative-load, and rehardening branches with consistent "
    "tangent, exact rollback, and checkpoint restart. It is not a multi-DOF frame "
    "or shell solver, a Lee-frame benchmark, material-geometric coupling, published "
    "or experimental validation, HIP parity, or release evidence."
)


@dataclass(frozen=True)
class ShallowArchArcLengthProblem:
    case_id: str = "two_bar_shallow_arch_scalar_arc_length"
    arch: TwoBarShallowArch = field(default_factory=TwoBarShallowArch)

    def initial_displacement_m(self) -> float:
        return 0.0

    def initial_load_kn(self) -> float:
        return 0.0

    def internal_force_kn(self, displacement_m: float) -> float:
        return self.arch.internal_force_kn(displacement_m)

    def consistent_tangent_kn_per_m(self, displacement_m: float) -> float:
        return self.arch.consistent_tangent_kn_per_m(displacement_m)


def _tangent_finite_difference_row(
    problem: ShallowArchArcLengthProblem,
    displacement_m: float,
) -> dict[str, Any]:
    step_m = 1.0e-7 * max(1.0, abs(displacement_m))
    finite_difference = (
        problem.internal_force_kn(displacement_m + step_m)
        - problem.internal_force_kn(displacement_m - step_m)
    ) / (2.0 * step_m)
    analytic = problem.consistent_tangent_kn_per_m(displacement_m)
    absolute_error = abs(finite_difference - analytic)
    allowed_error = max(1.0e-5, 1.0e-7 * abs(analytic))
    return {
        "displacement_m": displacement_m,
        "finite_difference_step_m": step_m,
        "consistent_tangent_kn_per_m": analytic,
        "finite_difference_tangent_kn_per_m": finite_difference,
        "absolute_error_kn_per_m": absolute_error,
        "allowed_error_kn_per_m": allowed_error,
        "contract_pass": absolute_error <= allowed_error,
    }


def _first_local_maximum(loads: list[float]) -> int | None:
    for index in range(1, len(loads) - 1):
        if loads[index] > loads[index - 1] and loads[index] > loads[index + 1]:
            return index
    return None


def build_shallow_arch_arc_length_benchmark_seed(
    *,
    config: ScalarArcLengthConfig | None = None,
) -> dict[str, Any]:
    """Build deterministic path, rollback, tangent, and restart evidence."""

    problem = ShallowArchArcLengthProblem()
    solver_config = config or ScalarArcLengthConfig(failed_step_reduction=0.25)
    first = scalar_arc_length_continuation(problem, config=solver_config)
    second = scalar_arc_length_continuation(problem, config=solver_config)
    first_payload = first.to_dict()
    deterministic_replay_exact = first_payload == second.to_dict()
    restart_checkpoint = first.checkpoints[len(first.checkpoints) // 2]
    restarted = scalar_arc_length_continuation(
        problem,
        config=solver_config,
        resume_from=restart_checkpoint,
    )
    restart_exact = restarted.final_checkpoint == first.final_checkpoint

    exact_limit_displacement, exact_limit_load = problem.arch.first_limit_point()
    checkpoints = list(first.checkpoints)
    below = max(
        (
            row
            for row in checkpoints
            if row.displacement_m < exact_limit_displacement
        ),
        key=lambda row: row.displacement_m,
    )
    above = min(
        (
            row
            for row in checkpoints
            if row.displacement_m > exact_limit_displacement
        ),
        key=lambda row: row.displacement_m,
    )
    loads = [row.load_kn for row in checkpoints]
    first_local_maximum_index = _first_local_maximum(loads)
    first_local_maximum_load = (
        loads[first_local_maximum_index]
        if first_local_maximum_index is not None
        else math.nan
    )
    first_limit_load_relative_error = abs(
        first_local_maximum_load - exact_limit_load
    ) / exact_limit_load
    tangent_sample_displacements = (
        0.03,
        0.07,
        exact_limit_displacement,
        0.20,
        0.32,
        0.44,
    )
    tangent_rows = [
        _tangent_finite_difference_row(problem, displacement)
        for displacement in tangent_sample_displacements
    ]
    rejected_attempts = [
        row for row in first.attempts if row["accepted"] is False
    ]
    rollback_evidence_pass = bool(
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
        and path_metrics["consistent_tangent_sign_change_observed"] is True
        and path_metrics["descending_load_branch_observed"] is True
        and path_metrics["negative_load_branch_observed"] is True
        and path_metrics["rehardening_branch_observed"] is True
        and path_metrics["fallback_count"] == 0
        and path_metrics["regularization_count"] == 0
    )
    limit_point_gate_pass = bool(
        below.displacement_m < exact_limit_displacement < above.displacement_m
        and first_local_maximum_index is not None
        and first_limit_load_relative_error <= 0.01
    )
    tangent_gate_pass = bool(
        tangent_rows and all(row["contract_pass"] for row in tangent_rows)
    )
    contract_pass = bool(
        path_gate_pass
        and limit_point_gate_pass
        and tangent_gate_pass
        and rollback_evidence_pass
        and restart_exact
        and deterministic_replay_exact
    )
    return {
        "schema_version": SHALLOW_ARCH_ARC_LENGTH_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": problem.case_id,
        "analysis_type": "scalar_spherical_arc_length_continuation",
        "truth_basis": "exact_two_bar_corotational_truss_equilibrium",
        "solver_result": first_payload,
        "verification": {
            "path_gate_passed": path_gate_pass,
            "limit_point_gate_passed": limit_point_gate_pass,
            "tangent_finite_difference_gate_passed": tangent_gate_pass,
            "rollback_evidence_passed": rollback_evidence_pass,
            "checkpoint_restart_exact": restart_exact,
            "deterministic_replay_exact": deterministic_replay_exact,
            "restart_checkpoint_state_hash": restart_checkpoint.state_hash,
            "final_checkpoint_state_hash": first.final_checkpoint.state_hash,
            "restarted_final_checkpoint_state_hash": (
                restarted.final_checkpoint.state_hash
            ),
        },
        "exact_first_limit_point": {
            "displacement_m": exact_limit_displacement,
            "load_kn": exact_limit_load,
        },
        "computed_first_limit_bracket": {
            "below_step_index": below.step_index,
            "below_displacement_m": below.displacement_m,
            "below_load_kn": below.load_kn,
            "above_step_index": above.step_index,
            "above_displacement_m": above.displacement_m,
            "above_load_kn": above.load_kn,
            "first_local_maximum_step_index": first_local_maximum_index,
            "first_local_maximum_load_kn": first_local_maximum_load,
            "first_limit_load_relative_error": first_limit_load_relative_error,
            "relative_tolerance": 0.01,
            "contract_pass": limit_point_gate_pass,
        },
        "consistent_tangent_finite_difference_rows": tangent_rows,
        "claims": {
            "scalar_arc_length_path_following": contract_pass,
            "shallow_arch_limit_point_crossing": contract_pass,
            "failed_step_rollback": rollback_evidence_pass,
            "checkpoint_restart": restart_exact,
            "multi_dof_frame_shell_arc_length": False,
            "lee_frame_snapthrough": False,
            "material_geometric_coupling": False,
            "production_rocm_hip_parity": False,
            "geometric_nonlinear_benchmark_breadth": False,
        },
        "blockers_remaining": [
            "multi_dof_frame_shell_arc_length_not_implemented",
            "lee_frame_snapthrough_not_implemented",
            "continuum_cantilever_large_rotation_not_implemented",
            "material_geometric_coupling_not_verified",
            "published_or_experimental_validation_not_attached",
            "production_rocm_hip_parity_not_verified",
        ],
        "claim_boundary": SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    }


__all__ = [
    "SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY",
    "SHALLOW_ARCH_ARC_LENGTH_SCHEMA_VERSION",
    "ShallowArchArcLengthProblem",
    "build_shallow_arch_arc_length_benchmark_seed",
]
