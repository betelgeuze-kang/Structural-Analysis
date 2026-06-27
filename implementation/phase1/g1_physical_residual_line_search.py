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

PRECONDITIONER_MODES = (
    "none", "jacobi_diag", "absolute_jacobi_diag", "damped_jacobi_diag",
)
DEFAULT_PRECONDITIONER = "none"
DEFAULT_PRECONDITIONER_FLOOR = 1.0e-8
DEFAULT_PRECONDITIONER_DAMPING_RATIO = 1.0e-3


def build_jacobi_preconditioner(
    diag: np.ndarray,
    mode: str = DEFAULT_PRECONDITIONER,
    *,
    floor: float = DEFAULT_PRECONDITIONER_FLOOR,
    damping_ratio: float = DEFAULT_PRECONDITIONER_DAMPING_RATIO,
) -> tuple[Callable[[np.ndarray], np.ndarray] | None, dict[str, Any]]:
    """Build a free-space diagonal (Jacobi) preconditioner M^-1 from a diagonal.

    Modes:
      - ``none``                : no preconditioner (returns None);
      - ``jacobi_diag``         : 1/diag, preserving sign (floored magnitude);
      - ``absolute_jacobi_diag``: 1/max(|diag|, floor);
      - ``damped_jacobi_diag``  : 1/(max(|diag|, floor) + damping_ratio*max|diag|).
    """
    if mode not in PRECONDITIONER_MODES:
        raise ValueError(f"unknown preconditioner mode {mode!r}; expected {PRECONDITIONER_MODES}")
    diag = np.asarray(diag, dtype=np.float64)
    n = int(diag.size)
    abs_diag = np.abs(diag)
    max_abs = float(np.max(abs_diag)) if n else 1.0
    min_abs = float(np.min(abs_diag)) if n else 0.0
    tiny = int(np.count_nonzero(abs_diag < floor))
    meta = {
        "mode": mode,
        "applied_in_free_space": True,
        "diag_min_abs": min_abs,
        "diag_max_abs": max_abs,
        "diag_floor": float(floor),
        "tiny_diag_count": tiny,
    }
    if mode == "none":
        return None, meta

    if mode == "jacobi_diag":
        floored_mag = np.maximum(abs_diag, floor)
        sign = np.where(diag >= 0.0, 1.0, -1.0)
        minv_vec = sign / floored_mag
    elif mode == "absolute_jacobi_diag":
        minv_vec = 1.0 / np.maximum(abs_diag, floor)
    else:  # damped_jacobi_diag
        meta["damping_ratio"] = float(damping_ratio)
        minv_vec = 1.0 / (np.maximum(abs_diag, floor) + damping_ratio * max_abs)

    if not bool(np.all(np.isfinite(minv_vec))):
        meta["reason_code"] = "nonfinite_preconditioner"
        return None, meta

    def minv(r: np.ndarray) -> np.ndarray:
        r = np.asarray(r, dtype=np.float64)
        if r.shape != minv_vec.shape:
            raise ValueError(
                f"preconditioner expects free-space vector of shape {minv_vec.shape}, "
                f"got {r.shape}"
            )
        return minv_vec * r

    return minv, meta



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
    gmres_atol: float = 1.0e-10,
    gmres_maxiter: int = 500,
    preconditioner_minv: Callable[[np.ndarray], np.ndarray] | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Solve J_phys(u) p = -R(u) using the matrix-free physical JVP.

    ``mode='representative_direct'`` densely assembles J from JVPs (only suitable
    for small representative systems) and solves directly. ``mode='matrix_free_gmres'``
    wraps the JVP in a scipy LinearOperator and runs GMRES, optionally with a
    free-space preconditioner ``preconditioner_minv`` (a callable M^-1 . r).
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
            "preconditioned": False,
            "residual_norm_before": float(_inf_norm(r0)),
            "residual_norm_after": float(_inf_norm(jac @ p + r0)) if converged else None,
        }

    # matrix-free GMRES
    iter_count = {"n": 0}

    def _count(_x):  # scipy callback (per-iteration)
        iter_count["n"] += 1

    operator = LinearOperator((n, n), matvec=jvp, dtype=np.float64)
    precond = (
        LinearOperator((n, n), matvec=preconditioner_minv, dtype=np.float64)
        if preconditioner_minv is not None
        else None
    )
    try:
        p, info = gmres(
            operator, -r0, rtol=gmres_tol, atol=gmres_atol,
            maxiter=gmres_maxiter, M=precond, callback=_count, callback_type="legacy",
        )
    except TypeError:
        try:
            p, info = gmres(
                operator, -r0, tol=gmres_tol, atol=gmres_atol,
                maxiter=gmres_maxiter, M=precond, callback=_count, callback_type="legacy",
            )
        except TypeError:
            # very old scipy: no callback_type support; drop iteration counting
            p, info = gmres(
                operator, -r0, tol=gmres_tol, maxiter=gmres_maxiter, M=precond,
            )
    converged = bool(info == 0 and _is_finite(p))
    if info > 0:
        reason = "gmres_not_converged_maxiter"
    elif info < 0:
        reason = "gmres_illegal_input_or_breakdown"
    elif not _is_finite(p):
        reason = "non_finite_direction"
    else:
        reason = "ok"
    residual_after = float(_inf_norm(jvp(p) + r0)) if _is_finite(p) else None
    return (p if converged else None), {
        "mode": mode,
        "converged": converged,
        "reason_code": reason,
        "gmres_info": int(info),
        "gmres_maxiter": int(gmres_maxiter),
        "iterations": int(iter_count["n"]),
        "preconditioned": bool(precond is not None),
        "residual_norm_before": float(_inf_norm(r0)),
        "residual_norm_after": residual_after,
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
