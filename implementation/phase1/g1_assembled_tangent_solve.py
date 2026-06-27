#!/usr/bin/env python3
"""Assembled free-space tangent direction solves (F2b-ii-a helper).

F2b-i found that diagonal (Jacobi) preconditioning cannot fix the extreme
stiffness-contrast ill-conditioning of the real MGT model. This module adds
assembled-tangent-based direction solves:

  - ``sparse_direct_spsolve`` / ``sparse_direct_splu`` : solve K_free p = -R(x0)
    directly (a modified/quasi-Newton step when K_free approximates dR/du);
  - ``gmres_ilu`` : matrix-free physical JVP operator preconditioned by an
    incomplete-LU factorization of the assembled free-space tangent.

It also verifies that the assembled tangent is consistent with the physical
residual operator (``K_free @ v`` vs the matrix-free JVP and a finite difference).
Everything is fail-closed with explicit reason codes; nothing here promotes G1.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import LinearOperator, gmres, spilu, splu, spsolve

from g1_global_newton_operator import DEFAULT_JVP_EPS, physical_consistent_jvp


ResidualFn = Callable[[np.ndarray], np.ndarray]

DIRECTION_SOLVERS = (
    "gmres_matrix_free",
    "gmres_ilu",
    "sparse_direct_spsolve",
    "sparse_direct_splu",
)
DEFAULT_DIRECTION_SOLVER = "gmres_matrix_free"

# reason codes
PASS = "PASS"
ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH = "ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH"
ERR_ASSEMBLED_TANGENT_PARITY_FAILED = "ERR_ASSEMBLED_TANGENT_PARITY_FAILED"
ERR_SPARSE_DIRECT_FACTOR_FAILED = "ERR_SPARSE_DIRECT_FACTOR_FAILED"
ERR_SPARSE_DIRECT_SOLVE_FAILED = "ERR_SPARSE_DIRECT_SOLVE_FAILED"
ERR_ILU_FACTOR_FAILED = "ERR_ILU_FACTOR_FAILED"
ERR_ILU_GMRES_NOT_CONVERGED = "ERR_ILU_GMRES_NOT_CONVERGED"
ERR_DIRECTION_SOLVE_BLOCKED = "ERR_DIRECTION_SOLVE_BLOCKED"


def _inf_norm(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.max(np.abs(x))) if x.size else 0.0


def _is_finite(x: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(x, dtype=np.float64))))


def assembled_tangent_parity(
    k_free: Any,
    residual_fn: ResidualFn,
    x0: np.ndarray,
    *,
    eps: float = DEFAULT_JVP_EPS,
    probes: int = 3,
    relative_tolerance: float = 1.0e-3,
    seed: int = 0,
) -> dict[str, Any]:
    """Check K_free @ v against the matrix-free physical JVP for random probes.

    A relatively loose tolerance is used: the assembled tangent is allowed to be
    an approximation of dR/du (it is used as a quasi-Newton operator / ILU
    preconditioner), but a gross mismatch is flagged.
    """
    x0 = np.asarray(x0, dtype=np.float64)
    n = int(x0.size)
    rng = np.random.default_rng(seed)
    max_rel = 0.0
    max_abs = 0.0
    for _ in range(max(1, probes)):
        v = rng.standard_normal(n)
        v = v / max(float(np.linalg.norm(v)), 1.0e-30)
        kv = np.asarray(k_free @ v, dtype=np.float64)
        jv = physical_consistent_jvp(residual_fn, x0, v, eps=eps)
        diff = kv - jv
        abs_err = _inf_norm(diff)
        denom = max(_inf_norm(kv), _inf_norm(jv), 1.0)
        max_abs = max(max_abs, abs_err)
        max_rel = max(max_rel, abs_err / denom)
    return {
        "attempted": True,
        "pass": bool(max_rel <= relative_tolerance),
        "max_relative_error": float(max_rel),
        "max_absolute_error": float(max_abs),
        "relative_tolerance": float(relative_tolerance),
        "probes": int(max(1, probes)),
    }


def solve_direction_assembled(
    k_free: Any,
    residual_fn: ResidualFn,
    x0: np.ndarray,
    *,
    solver: str = DEFAULT_DIRECTION_SOLVER,
    eps: float = DEFAULT_JVP_EPS,
    ilu_drop_tol: float = 1.0e-4,
    ilu_fill_factor: float = 10.0,
    gmres_maxiter: int = 400,
    gmres_rtol: float = 1.0e-6,
    gmres_atol: float = 1.0e-10,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Solve for a Newton-ish direction using the assembled free-space tangent."""
    if solver not in DIRECTION_SOLVERS:
        raise ValueError(f"unknown direction solver {solver!r}; expected {DIRECTION_SOLVERS}")
    x0 = np.asarray(x0, dtype=np.float64)
    n = int(x0.size)
    r0 = np.asarray(residual_fn(x0), dtype=np.float64)
    if not _is_finite(r0):
        return None, {"solver": solver, "status": "blocked", "reason_code": "nan_residual_at_base_state"}
    b = -r0

    if k_free.shape != (n, n):
        return None, {
            "solver": solver, "status": "blocked",
            "reason_code": ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH,
            "tangent_shape": list(k_free.shape), "expected_shape": [n, n],
        }

    def _linear_residual_after(p: np.ndarray) -> float:
        return _inf_norm(np.asarray(k_free @ p, dtype=np.float64) - b)

    if solver == "sparse_direct_spsolve":
        try:
            import warnings

            from scipy.sparse.linalg import MatrixRankWarning

            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                p = np.asarray(spsolve(csc_matrix(k_free), b), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            return None, {"solver": solver, "status": "blocked",
                          "reason_code": ERR_SPARSE_DIRECT_SOLVE_FAILED, "detail": str(exc)[:200]}
        if not _is_finite(p):
            return None, {"solver": solver, "status": "blocked",
                          "reason_code": ERR_SPARSE_DIRECT_SOLVE_FAILED, "detail": "non_finite_solution"}
        return p, {"solver": solver, "status": "ready", "reason_code": PASS,
                   "residual_norm_before": _inf_norm(r0),
                   "residual_norm_after_linear_solve": _linear_residual_after(p)}

    if solver == "sparse_direct_splu":
        try:
            lu = splu(csc_matrix(k_free))
        except Exception as exc:  # noqa: BLE001
            return None, {"solver": solver, "status": "blocked",
                          "reason_code": ERR_SPARSE_DIRECT_FACTOR_FAILED, "detail": str(exc)[:200]}
        try:
            p = np.asarray(lu.solve(b), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            return None, {"solver": solver, "status": "blocked",
                          "reason_code": ERR_SPARSE_DIRECT_SOLVE_FAILED, "detail": str(exc)[:200]}
        if not _is_finite(p):
            return None, {"solver": solver, "status": "blocked",
                          "reason_code": ERR_SPARSE_DIRECT_SOLVE_FAILED, "detail": "non_finite_solution"}
        return p, {"solver": solver, "status": "ready", "reason_code": PASS,
                   "residual_norm_before": _inf_norm(r0),
                   "residual_norm_after_linear_solve": _linear_residual_after(p)}

    if solver == "gmres_matrix_free":
        operator = LinearOperator((n, n), matvec=lambda v: physical_consistent_jvp(residual_fn, x0, v, eps=eps), dtype=np.float64)
        precond = None
    else:  # gmres_ilu
        try:
            ilu = spilu(csc_matrix(k_free), drop_tol=ilu_drop_tol, fill_factor=ilu_fill_factor)
        except Exception as exc:  # noqa: BLE001
            return None, {"solver": solver, "status": "blocked",
                          "reason_code": ERR_ILU_FACTOR_FAILED, "detail": str(exc)[:200]}
        operator = LinearOperator((n, n), matvec=lambda v: physical_consistent_jvp(residual_fn, x0, v, eps=eps), dtype=np.float64)
        precond = LinearOperator((n, n), matvec=ilu.solve, dtype=np.float64)

    iters = {"n": 0}

    def _cb(_x):
        iters["n"] += 1

    try:
        p, info = gmres(operator, b, rtol=gmres_rtol, atol=gmres_atol,
                        maxiter=gmres_maxiter, M=precond, callback=_cb, callback_type="legacy")
    except TypeError:
        p, info = gmres(operator, b, tol=gmres_rtol, maxiter=gmres_maxiter, M=precond)
    converged = bool(info == 0 and _is_finite(p))
    residual_after = _inf_norm(np.asarray(operator @ p, dtype=np.float64) - b) if _is_finite(p) else None
    if not converged:
        reason = (
            ERR_ILU_GMRES_NOT_CONVERGED if solver == "gmres_ilu"
            else ERR_DIRECTION_SOLVE_BLOCKED
        )
        return None, {"solver": solver, "status": "blocked", "reason_code": reason,
                      "gmres_info": int(info), "iterations": int(iters["n"]),
                      "preconditioned": bool(precond is not None),
                      "residual_norm_before": _inf_norm(r0), "residual_norm_after": residual_after}
    return p, {"solver": solver, "status": "ready", "reason_code": PASS,
               "gmres_info": int(info), "iterations": int(iters["n"]),
               "preconditioned": bool(precond is not None),
               "residual_norm_before": _inf_norm(r0), "residual_norm_after": residual_after}
