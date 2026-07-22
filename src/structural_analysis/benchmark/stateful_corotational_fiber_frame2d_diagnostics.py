"""Same-parent diagnostics for the stateful corotational fiber-frame assembly."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)


def finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
    epsilon_m: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    """Check every free-equation column from one immutable accepted state."""

    epsilon = float(epsilon_m)
    tolerance = float(relative_tolerance)
    if not math.isfinite(epsilon) or epsilon <= 0.0:
        raise ValueError("epsilon_m must be finite and positive")
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("relative_tolerance must be finite and positive")
    try:
        free = np.asarray(trial_free_coordinates_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("trial_free_coordinates_m has invalid values") from exc
    equation_count = len(problem.free_global_dofs)
    if free.shape != (equation_count,) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")

    parent_bytes = accepted_checkpoint.canonical_bytes()
    base = assemble_stateful_corotational_fiber_frame2d(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=free,
    )
    finite_difference = np.empty_like(base.jacobian_kn_per_m)
    parent_hashes = [base.parent_checkpoint_hash]
    response_parent_hashes = [
        row.response.parent_state_hash for row in base.member_assemblies
    ]
    for column in range(equation_count):
        perturbation = np.zeros_like(free)
        perturbation[column] = epsilon
        forward = assemble_stateful_corotational_fiber_frame2d(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free + perturbation,
        )
        backward = assemble_stateful_corotational_fiber_frame2d(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free - perturbation,
        )
        finite_difference[:, column] = (forward.residual_kn - backward.residual_kn) / (
            2.0 * epsilon
        )
        for assembly in (forward, backward):
            parent_hashes.append(assembly.parent_checkpoint_hash)
            response_parent_hashes.extend(
                row.response.parent_state_hash for row in assembly.member_assemblies
            )

    error = finite_difference - base.jacobian_kn_per_m
    absolute_error = float(np.linalg.norm(error, ord=np.inf))
    scale = max(
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(np.linalg.norm(base.jacobian_kn_per_m, ord=np.inf)),
        1.0,
    )
    relative_error = absolute_error / scale
    symmetry_error = float(
        np.linalg.norm(
            base.jacobian_kn_per_m - base.jacobian_kn_per_m.T,
            ord=np.inf,
        )
    )
    decomposition_error = float(
        np.linalg.norm(
            base.consistent_tangent_global
            - base.material_tangent_global
            - base.geometric_tangent_global,
            ord=np.inf,
        )
    )
    member_parent_hashes = tuple(
        state.state_hash for state in accepted_checkpoint.element_states
    )
    expected_response_parent_hashes = member_parent_hashes * (1 + 2 * equation_count)
    same_parent = bool(
        all(value == accepted_checkpoint.state_hash for value in parent_hashes)
        and tuple(response_parent_hashes) == expected_response_parent_hashes
        and accepted_checkpoint.canonical_bytes() == parent_bytes
    )
    material_tangent_norm = float(
        np.linalg.norm(base.material_tangent_global, ord=np.inf)
    )
    geometric_tangent_norm = float(
        np.linalg.norm(base.geometric_tangent_global, ord=np.inf)
    )
    yielded_member_count = sum(
        int(row.response.yielded_integration_point_count > 0)
        for row in base.member_assemblies
    )
    damaged_member_count = sum(
        int(row.response.damaged_integration_point_count > 0)
        for row in base.member_assemblies
    )
    return {
        "parent_checkpoint_hash": accepted_checkpoint.state_hash,
        "parent_epoch": accepted_checkpoint.epoch,
        "same_committed_parent_checkpoint": same_parent,
        "equation_count": equation_count,
        "finite_difference_epsilon_m": epsilon,
        "analytic_jacobian_kn_per_m": base.jacobian_kn_per_m.tolist(),
        "finite_difference_jacobian_kn_per_m": finite_difference.tolist(),
        "absolute_inf_error_kn_per_m": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": tolerance,
        "tangent_symmetry_error_kn_per_m": symmetry_error,
        "tangent_decomposition_error_kn_per_m": decomposition_error,
        "material_tangent_inf_norm_kn_per_m": material_tangent_norm,
        "geometric_tangent_inf_norm_kn_per_m": geometric_tangent_norm,
        "material_and_geometric_terms_active": bool(
            material_tangent_norm > 0.0 and geometric_tangent_norm > 0.0
        ),
        "yielded_member_count": yielded_member_count,
        "damaged_member_count": damaged_member_count,
        "pass": bool(
            relative_error <= tolerance
            and symmetry_error <= 1.0e-9
            and decomposition_error <= 1.0e-8
            and same_parent
        ),
    }


__all__ = [
    "finite_difference_stateful_corotational_fiber_frame2d_tangent_check",
]
