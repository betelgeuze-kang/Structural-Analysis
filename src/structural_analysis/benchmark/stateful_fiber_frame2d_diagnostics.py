"""Same-parent diagnostics for the bounded stateful fiber-frame assembly."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    assemble_stateful_fiber_frame2d,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)


def finite_difference_stateful_fiber_frame2d_tangent_check(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
    epsilon_m: float = 1.0e-8,
    relative_tolerance: float = 5.0e-6,
) -> dict[str, Any]:
    """Check every free-equation column from one immutable checkpoint."""

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
    if free.shape != (len(problem.free_global_dofs),) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")
    parent_bytes = accepted_checkpoint.canonical_bytes()
    base = assemble_stateful_fiber_frame2d(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=free,
    )
    finite_difference = np.empty_like(base.jacobian_kn_per_m)
    parent_hashes = [base.parent_checkpoint_hash]
    for column in range(free.size):
        direction = np.zeros_like(free)
        direction[column] = epsilon
        forward = assemble_stateful_fiber_frame2d(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free + direction,
        )
        backward = assemble_stateful_fiber_frame2d(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free - direction,
        )
        finite_difference[:, column] = (forward.residual_kn - backward.residual_kn) / (
            2.0 * epsilon
        )
        parent_hashes.extend(
            (forward.parent_checkpoint_hash, backward.parent_checkpoint_hash)
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
    same_parent = bool(
        all(value == accepted_checkpoint.state_hash for value in parent_hashes)
        and accepted_checkpoint.canonical_bytes() == parent_bytes
    )
    return {
        "parent_checkpoint_hash": accepted_checkpoint.state_hash,
        "parent_epoch": accepted_checkpoint.epoch,
        "same_committed_parent_checkpoint": same_parent,
        "finite_difference_epsilon_m": epsilon,
        "analytic_jacobian_kn_per_m": base.jacobian_kn_per_m.tolist(),
        "finite_difference_jacobian_kn_per_m": finite_difference.tolist(),
        "absolute_inf_error_kn_per_m": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": tolerance,
        "tangent_symmetry_error": symmetry_error,
        "pass": bool(
            relative_error <= tolerance and symmetry_error <= 1.0e-9 and same_parent
        ),
    }


__all__ = ["finite_difference_stateful_fiber_frame2d_tangent_check"]
