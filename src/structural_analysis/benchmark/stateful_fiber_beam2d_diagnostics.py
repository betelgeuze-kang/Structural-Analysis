"""Non-authoritative diagnostics for the stateful 2D fiber beam kernel."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from structural_analysis.elements.stateful_fiber_beam2d import (
    StatefulFiberBeam2D,
    StatefulFiberBeam2DState,
)


def _positive(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be positive")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be positive") from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _local_vector(values: Any, *, name: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite six-vector")
    return np.array(vector, dtype=np.float64, copy=True, order="C")


def finite_difference_stateful_fiber_beam2d_tangent_check(
    element: StatefulFiberBeam2D,
    committed_state: StatefulFiberBeam2DState,
    *,
    local_displacements: Any | None = None,
    displacement_epsilon_m: float = 1.0e-8,
    rotation_epsilon_rad: float = 1.0e-8,
    relative_tolerance: float = 3.0e-6,
) -> dict[str, Any]:
    """Compare all six tangent columns from one immutable element parent."""

    local = _local_vector(
        (
            element.uniform_generalized_strain_displacements(-3.0e-4, 6.0e-3)
            if local_displacements is None
            else local_displacements
        ),
        name="local_displacements",
    )
    displacement_step = _positive(
        displacement_epsilon_m,
        name="displacement_epsilon_m",
    )
    rotation_step = _positive(
        rotation_epsilon_rad,
        name="rotation_epsilon_rad",
    )
    tolerance = _positive(relative_tolerance, name="relative_tolerance")
    steps = np.asarray(
        [
            displacement_step,
            displacement_step,
            rotation_step,
            displacement_step,
            displacement_step,
            rotation_step,
        ],
        dtype=np.float64,
    )
    parent_bytes = committed_state.canonical_bytes()
    center = element.integrate(local, committed_state)
    difference = np.empty((6, 6), dtype=np.float64)
    parent_hashes = [center.parent_state_hash]
    for column, step in enumerate(steps):
        direction = np.zeros(6, dtype=np.float64)
        direction[column] = step
        forward = element.integrate(local + direction, committed_state)
        backward = element.integrate(local - direction, committed_state)
        difference[:, column] = (
            forward.internal_force_local - backward.internal_force_local
        ) / (2.0 * step)
        parent_hashes.extend((forward.parent_state_hash, backward.parent_state_hash))
    error = difference - center.consistent_tangent_local
    absolute_error = float(np.linalg.norm(error, ord=np.inf))
    scale = max(
        float(np.linalg.norm(difference, ord=np.inf)),
        float(np.linalg.norm(center.consistent_tangent_local, ord=np.inf)),
        1.0,
    )
    relative_error = absolute_error / scale
    symmetry_error = float(
        np.linalg.norm(
            center.consistent_tangent_local - center.consistent_tangent_local.T,
            ord=np.inf,
        )
    )
    same_parent = bool(
        all(value == committed_state.state_hash for value in parent_hashes)
        and committed_state.canonical_bytes() == parent_bytes
    )
    return {
        "local_displacements": local.tolist(),
        "analytic_consistent_tangent": (center.consistent_tangent_local.tolist()),
        "finite_difference_tangent": difference.tolist(),
        "absolute_inf_error": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": tolerance,
        "tangent_symmetry_error": symmetry_error,
        "same_committed_parent_state": same_parent,
        "pass": bool(
            relative_error <= tolerance and symmetry_error <= 1.0e-10 and same_parent
        ),
    }


def diagnose_stateful_fiber_beam2d_history(
    element: StatefulFiberBeam2D,
    local_displacement_path: Iterable[Any],
    *,
    initial_state: StatefulFiberBeam2DState | None = None,
) -> dict[str, Any]:
    """Run cyclic diagnostic history with explicit non-product acceptance.

    This helper exists only for bounded benchmark evidence. Product commits
    must pass residual, increment, ancestry, and rollback gates in an assembly
    checkpoint layer.
    """

    path = tuple(
        _local_vector(row, name="local_displacement_path row")
        for row in local_displacement_path
    )
    if not path:
        raise ValueError("local_displacement_path must be non-empty")
    state = initial_state or element.initial_state()
    element.validate_state(state)
    previous_curvature = float(
        np.mean(
            [
                section_state.curvature_z_per_m
                for section_state in state.integration_point_states
            ]
        )
    )
    previous_sign = 0
    reversal_count = 0
    rows: list[dict[str, Any]] = []
    energy_values = [element.dissipated_energy_mj(state)]
    for step_index, local in enumerate(path, start=1):
        parent = state
        response = element.integrate(local, parent)
        curvature = float(np.mean(response.generalized_strains[:, 1]))
        increment = curvature - previous_curvature
        sign = 1 if increment > 0.0 else -1 if increment < 0.0 else 0
        if sign != 0 and previous_sign != 0 and sign != previous_sign:
            reversal_count += 1
        if sign != 0:
            previous_sign = sign
        state = response.state
        energy_values.append(response.dissipated_energy_mj)
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                "accepted_state_hash": state.state_hash,
                "mean_curvature_z_per_m": curvature,
                "curvature_increment_sign": sign,
                **response.to_summary_dict(),
            }
        )
        previous_curvature = curvature
    energy_monotonic = all(
        following + 1.0e-15 >= current
        for current, following in zip(energy_values, energy_values[1:])
    )
    return {
        "diagnostic_only": True,
        "authoritative_commit_path": False,
        "element_contract_hash": element.contract_hash,
        "step_count": len(rows),
        "curvature_reversal_count": reversal_count,
        "yielded_step_count": sum(
            int(row["yielded_integration_point_count"] > 0) for row in rows
        ),
        "concrete_damage_step_count": sum(
            int(row["damaged_integration_point_count"] > 0) for row in rows
        ),
        "dissipated_energy_nonnegative_monotonic": energy_monotonic,
        "final_dissipated_energy_mj": energy_values[-1],
        "final_state": state.to_dict(),
        "history": rows,
    }


__all__ = [
    "diagnose_stateful_fiber_beam2d_history",
    "finite_difference_stateful_fiber_beam2d_tangent_check",
]
