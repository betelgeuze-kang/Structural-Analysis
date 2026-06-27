#!/usr/bin/env python3
"""Opt-in physical-consistent global Newton operator (probe-stage helper).

This module adds an *opt-in* physical-consistent global Newton operator next to
the existing (default) normalized frame/geometric corrector. It does NOT replace
the default solver path and does NOT promote any G1 gate.

Two operator modes are defined:

  GLOBAL_NEWTON_OPERATOR_CURRENT  = "current_normalized_frame_geometric"
      The existing corrector named by the D audit: service-material reduced frame
      tangent + geometric delta + solver-only lambda damping. It is NOT dR/du and
      is retained only as a regression baseline.

  GLOBAL_NEWTON_OPERATOR_PHYSICAL = "physical_consistent_frame_shell_material_geometric"
      A matrix-free linearization of the *physical* residual
      R(u, lambda) = F_int(u) - lambda * F_ext, i.e. the directional derivative
      J_phys(u) . v = d/dalpha R(u + alpha v)|_{alpha=0}. Because it is taken
      directly from the physical residual, it uses NO solver-only lambda damping
      and NO service-material reduction.

The default is always GLOBAL_NEWTON_OPERATOR_CURRENT.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np


GLOBAL_NEWTON_OPERATOR_CURRENT = "current_normalized_frame_geometric"
GLOBAL_NEWTON_OPERATOR_PHYSICAL = "physical_consistent_frame_shell_material_geometric"
DEFAULT_GLOBAL_NEWTON_OPERATOR = GLOBAL_NEWTON_OPERATOR_CURRENT
GLOBAL_NEWTON_OPERATORS = (
    GLOBAL_NEWTON_OPERATOR_CURRENT,
    GLOBAL_NEWTON_OPERATOR_PHYSICAL,
)

# Default central-difference step for the matrix-free directional derivative.
DEFAULT_JVP_EPS = 1.0e-6
# Parity tolerances for "JVP resolves the physical-residual directional derivative".
DEFAULT_JVP_RELATIVE_TOLERANCE = 1.0e-4
DEFAULT_JVP_ABSOLUTE_TOLERANCE_N = 1.0e-2

ResidualFn = Callable[[np.ndarray], np.ndarray]


def normalize_global_newton_operator(value: str | None) -> str:
    """Return a valid operator mode, defaulting to the current normalized path."""
    if value is None:
        return DEFAULT_GLOBAL_NEWTON_OPERATOR
    text = str(value).strip()
    if text not in GLOBAL_NEWTON_OPERATORS:
        raise ValueError(
            f"unknown global_newton_operator {value!r}; "
            f"expected one of {GLOBAL_NEWTON_OPERATORS}"
        )
    return text


def operator_uses_solver_normalization_lambda(mode: str) -> bool:
    """True only for the current normalized corrector (lambda damping injected).

    The physical-consistent operator never injects a solver-only lambda damping
    because it is the directional derivative of the physical residual.
    """
    return normalize_global_newton_operator(mode) == GLOBAL_NEWTON_OPERATOR_CURRENT


def physical_consistent_jvp(
    residual_fn: ResidualFn,
    u: np.ndarray,
    v: np.ndarray,
    *,
    eps: float = DEFAULT_JVP_EPS,
) -> np.ndarray:
    """Matrix-free directional derivative of the physical residual.

    Returns J_phys(u) . v approximated by a central difference of ``residual_fn``:

        (R(u + eps * v) - R(u - eps * v)) / (2 * eps)

    No lambda damping and no service-material reduction are applied: the operator
    is exactly the linearization of whatever physical residual ``residual_fn``
    evaluates.
    """
    u = np.asarray(u, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    if u.shape != v.shape:
        raise ValueError(f"u shape {u.shape} != v shape {v.shape}")
    step = float(eps)
    if step <= 0.0:
        raise ValueError("eps must be positive")
    r_plus = np.asarray(residual_fn(u + step * v), dtype=np.float64)
    r_minus = np.asarray(residual_fn(u - step * v), dtype=np.float64)
    return (r_plus - r_minus) / (2.0 * step)


def jvp_parity_report(
    residual_fn: ResidualFn,
    u: np.ndarray,
    v: np.ndarray,
    *,
    eps: float = DEFAULT_JVP_EPS,
    reference_eps: float | None = None,
    relative_tolerance: float = DEFAULT_JVP_RELATIVE_TOLERANCE,
    absolute_tolerance_n: float = DEFAULT_JVP_ABSOLUTE_TOLERANCE_N,
) -> dict[str, Any]:
    """Verify the matrix-free JVP resolves the physical-residual derivative.

    Compares the central-difference JVP at ``eps`` against an independent
    central-difference estimate at ``reference_eps`` (a different step). For a
    well-resolved linearization of a smooth physical residual the two estimates
    agree to O(eps^2); large disagreement flags noise- or nonlinearity-dominated
    sampling rather than a faithful operator.
    """
    if reference_eps is None:
        reference_eps = eps * 10.0
    jvp = physical_consistent_jvp(residual_fn, u, v, eps=eps)
    jvp_ref = physical_consistent_jvp(residual_fn, u, v, eps=reference_eps)
    diff = jvp - jvp_ref
    max_abs = float(np.max(np.abs(diff))) if diff.size else 0.0
    denom = max(
        float(np.max(np.abs(jvp))) if jvp.size else 0.0,
        float(np.max(np.abs(jvp_ref))) if jvp_ref.size else 0.0,
        1.0,
    )
    max_rel = max_abs / denom
    passed = bool(max_rel <= relative_tolerance and max_abs <= absolute_tolerance_n)
    return {
        "finite_difference_eps": float(eps),
        "reference_finite_difference_eps": float(reference_eps),
        "jvp_inf_n": float(np.max(np.abs(jvp))) if jvp.size else 0.0,
        "reference_jvp_inf_n": float(np.max(np.abs(jvp_ref))) if jvp_ref.size else 0.0,
        "max_relative_error": float(max_rel),
        "max_absolute_error_n": float(max_abs),
        "relative_tolerance": float(relative_tolerance),
        "absolute_tolerance_n": float(absolute_tolerance_n),
        "pass": passed,
    }


def jvp_parity_against_reference(
    jvp: np.ndarray,
    reference_action: np.ndarray,
    *,
    relative_tolerance: float = DEFAULT_JVP_RELATIVE_TOLERANCE,
    absolute_tolerance_n: float = DEFAULT_JVP_ABSOLUTE_TOLERANCE_N,
) -> dict[str, Any]:
    """Compare a JVP against a known analytic operator action (e.g. A . v)."""
    jvp = np.asarray(jvp, dtype=np.float64)
    reference_action = np.asarray(reference_action, dtype=np.float64)
    diff = jvp - reference_action
    max_abs = float(np.max(np.abs(diff))) if diff.size else 0.0
    denom = max(float(np.max(np.abs(reference_action))) if reference_action.size else 0.0, 1.0)
    max_rel = max_abs / denom
    passed = bool(max_rel <= relative_tolerance and max_abs <= absolute_tolerance_n)
    return {
        "max_relative_error": float(max_rel),
        "max_absolute_error_n": float(max_abs),
        "relative_tolerance": float(relative_tolerance),
        "absolute_tolerance_n": float(absolute_tolerance_n),
        "pass": passed,
    }
