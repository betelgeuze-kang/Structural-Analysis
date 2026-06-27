#!/usr/bin/env python3
"""Non-promoting physical-residual line-search preview (F1-stage helper).

Builds a Newton direction from the *physical* residual using the opt-in
physical-consistent operator (matrix-free JVP from E), then runs a backtracking
line-search on the physical residual R(u, lambda) = F_int(u) - lambda * F_ext.

This is a preview/diagnostic. It does NOT change the default solver path and does
NOT promote any G1 gate. It exists to check whether the physical-consistent
operator beats the D-audit "tiny-alpha stall" on a representative physical system
before any real-model (F2) work.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from scipy.sparse.linalg import LinearOperator, gmres

from g1_global_newton_operator import (
    DEFAULT_JVP_EPS,
    physical_consistent_jvp,
)


ResidualFn = Callable[[np.ndarray], np.ndarray]

# The D audit found descent only for alpha <= ~1.25e-4 and ~1.9% reduction/pass.
D_TINY_ALPHA_THRESHOLD = 1.25e-4
D_RESIDUAL_REDUCTION_BASELINE = 0.019
D_AUDIT_MAX_PREDICTED_ACTUAL_RATIO = 830000.0

DEFAULT_ALPHAS = (
    1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.015625, 0.0078125,
    0.00390625, 0.001953125, 0.0009765625, 0.00048828125,
    0.000244140625, 0.0001220703125,
)


def _inf_norm(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.max(np.abs(x))) if x.size else 0.0


def _is_finite(x: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(x, dtype=np.float64))))


def solve_physical_newton_direction(
    residual_fn: ResidualFn,
    u: np.ndarray,
    *,
    mode: str = "matrix_free_gmres",
    eps: float = DEFAULT_JVP_EPS,
    gmres_tol: float = 1.0e-8,
    gmres_maxiter: int = 500,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Solve J_phys(u) p = -R(u) using the matrix-free physical JVP.

    ``mode='representative_direct'`` densely assembles J from JVPs (only suitable
    for small representative systems) and solves directly. ``mode='matrix_free_gmres'``
    wraps the JVP in a scipy LinearOperator and runs GMRES.
    """
    u = np.asarray(u, dtype=np.float64)
    r0 = np.asarray(residual_fn(u), dtype=np.float64)
    n = int(u.size)
    if not _is_finite(r0):
        return None, {"mode": mode, "converged": False, "reason_code": "nan_residual_at_base_state"}

    def jvp(v: np.ndarray) -> np.ndarray:
        return physical_consistent_jvp(residual_fn, u, v, eps=eps)

    if mode == "representative_direct":
        jac = np.empty((n, n), dtype=np.float64)
        basis = np.eye(n, dtype=np.float64)
        for i in range(n):
            jac[:, i] = jvp(basis[:, i])
        try:
            p = np.linalg.solve(jac, -r0)
            converged = _is_finite(p)
            reason = "ok" if converged else "non_finite_direction"
        except np.linalg.LinAlgError as exc:
            return None, {"mode": mode, "converged": False, "reason_code": f"linalg_error:{exc}"}
        return (p if converged else None), {
            "mode": mode,
            "converged": bool(converged),
            "reason_code": reason,
            "jacobian_assembled_dense": True,
        }

    # matrix-free GMRES
    operator = LinearOperator((n, n), matvec=jvp, dtype=np.float64)
    try:
        p, info = gmres(operator, -r0, rtol=gmres_tol, maxiter=gmres_maxiter)
    except TypeError:
        # older scipy uses `tol` instead of `rtol`
        p, info = gmres(operator, -r0, tol=gmres_tol, maxiter=gmres_maxiter)
    converged = bool(info == 0 and _is_finite(p))
    if info > 0:
        reason = "gmres_not_converged_maxiter"
    elif info < 0:
        reason = "gmres_illegal_input_or_breakdown"
    elif not _is_finite(p):
        reason = "non_finite_direction"
    else:
        reason = "ok"
    return (p if converged else None), {
        "mode": mode,
        "converged": converged,
        "reason_code": reason,
        "gmres_info": int(info),
        "gmres_maxiter": int(gmres_maxiter),
    }


def physical_residual_backtracking_line_search(
    residual_fn: ResidualFn,
    u: np.ndarray,
    p: np.ndarray,
    *,
    jvp_action: np.ndarray | None = None,
    alphas: tuple[float, ...] = DEFAULT_ALPHAS,
    eps: float = DEFAULT_JVP_EPS,
    sufficient_reduction: float = 0.0,
) -> dict[str, Any]:
    """Backtracking line-search on the physical residual inf-norm.

    For each alpha records the predicted change (alpha * J.p) versus the actual
    physical residual change, and the predicted/actual mismatch ratio. Accepts
    the largest alpha that reduces the residual by more than ``sufficient_reduction``.
    """
    u = np.asarray(u, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    r0 = np.asarray(residual_fn(u), dtype=np.float64)
    if not _is_finite(r0) or not _is_finite(p):
        return {
            "status": "fail_closed_nan",
            "reason_code": "nan_residual_or_direction",
            "accepted_alpha": None,
            "residual_before_n": _inf_norm(r0) if _is_finite(r0) else None,
            "residual_after_n": None,
            "residual_reduction_ratio": None,
            "alpha_rows": [],
        }
    r0_norm = _inf_norm(r0)
    if jvp_action is None:
        jvp_action = physical_consistent_jvp(residual_fn, u, p, eps=eps)
    jvp_action = np.asarray(jvp_action, dtype=np.float64)

    rows: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for alpha in alphas:
        r_alpha = np.asarray(residual_fn(u + alpha * p), dtype=np.float64)
        if not _is_finite(r_alpha):
            rows.append({"alpha": float(alpha), "residual_inf_n": None, "finite": False})
            continue
        r_alpha_norm = _inf_norm(r_alpha)
        predicted_delta = alpha * jvp_action
        actual_delta = r_alpha - r0
        pred_norm = _inf_norm(predicted_delta)
        act_norm = _inf_norm(actual_delta)
        mismatch_ratio = pred_norm / max(act_norm, 1.0e-30)
        reduction_ratio = (r0_norm - r_alpha_norm) / max(r0_norm, 1.0e-30)
        is_descent = bool(r_alpha_norm < r0_norm - sufficient_reduction * r0_norm)
        row = {
            "alpha": float(alpha),
            "residual_inf_n": float(r_alpha_norm),
            "residual_reduction_ratio": float(reduction_ratio),
            "predicted_delta_inf_n": float(pred_norm),
            "actual_delta_inf_n": float(act_norm),
            "predicted_over_actual_mismatch_ratio": float(mismatch_ratio),
            "is_descent": is_descent,
            "finite": True,
        }
        rows.append(row)
        if is_descent and (best is None or alpha > best["alpha"]):
            best = row

    if best is None:
        return {
            "status": "no_descent_found",
            "reason_code": "no_alpha_reduced_physical_residual",
            "accepted_alpha": None,
            "residual_before_n": float(r0_norm),
            "residual_after_n": None,
            "residual_reduction_ratio": 0.0,
            "alpha_rows": rows,
        }
    return {
        "status": "ready",
        "reason_code": "ok",
        "accepted_alpha": float(best["alpha"]),
        "residual_before_n": float(r0_norm),
        "residual_after_n": float(best["residual_inf_n"]),
        "residual_reduction_ratio": float(best["residual_reduction_ratio"]),
        "accepted_predicted_over_actual_mismatch_ratio": float(
            best["predicted_over_actual_mismatch_ratio"]
        ),
        "beats_d_tiny_alpha_threshold": bool(best["alpha"] > D_TINY_ALPHA_THRESHOLD),
        "beats_d_residual_reduction_baseline": bool(
            best["residual_reduction_ratio"] > D_RESIDUAL_REDUCTION_BASELINE
        ),
        "alpha_rows": rows,
    }
