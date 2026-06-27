#!/usr/bin/env python3
"""Regularized assembled-tangent direction-solve helpers (F2f).

F2e established that, with the real per-element service tangent, the assembled
free-space tangent is consistent with the physical residual (parity pass) but is
singular / rank-deficient for direct factorization. This module sweeps a principled
regularization, solves the (regularized) direction, and quantifies how small a
regularization is needed to obtain a factorable, descent-yielding direction, for
comparison against the production lambda ~= 515.

Helpers are fail-closed and never promote G1.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from scipy.sparse import csc_matrix, eye as sparse_eye
from scipy.sparse.linalg import MatrixRankWarning, spsolve


ResidualFn = Callable[[np.ndarray], np.ndarray]

REGULARIZATION_MODES = ("none", "scalar_shift", "relative_diagonal_shift")
DEFAULT_REGULARIZATION_MODE = "none"
PRODUCTION_LAMBDA = 515.4025311317521

# A candidate whose direction collapses onto the (negative) residual / damped
# identity solve (cosine above this threshold) has lost its Newton content.
GRADIENT_COLLAPSE_COSINE = 0.98

PASS = "PASS"
ERR_UNREGULARIZED_TANGENT_SINGULAR = "ERR_UNREGULARIZED_TANGENT_SINGULAR"
ERR_REGULARIZATION_SWEEP_NO_FACTORABLE_CANDIDATE = "ERR_REGULARIZATION_SWEEP_NO_FACTORABLE_CANDIDATE"
ERR_REGULARIZED_SOLVE_FAILED = "ERR_REGULARIZED_SOLVE_FAILED"
ERR_REGULARIZED_DIRECTION_NAN = "ERR_REGULARIZED_DIRECTION_NAN"
ERR_LINE_SEARCH_NO_DESCENT = "ERR_LINE_SEARCH_NO_DESCENT"
ERR_REGULARIZATION_TOO_LARGE = "ERR_REGULARIZATION_TOO_LARGE"
ERR_PARITY_REQUIRED_BUT_FAILED = "ERR_PARITY_REQUIRED_BUT_FAILED"


def _inf_norm(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.max(np.abs(x))) if x.size else 0.0


def _safe_cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 1.0e-300 or nb <= 1.0e-300:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def regularize_matrix(k_free: Any, mode: str, mu: float) -> tuple[Any, float, str]:
    """Return (K_reg, effective_absolute_shift, scale_source) for a regularization."""
    if mode not in REGULARIZATION_MODES:
        raise ValueError(f"unknown regularization mode {mode!r}; expected {REGULARIZATION_MODES}")
    n = k_free.shape[0]
    if mode == "none" or mu == 0.0:
        return k_free, 0.0, "none"
    if mode == "scalar_shift":
        shift = float(mu)
        return (k_free + shift * sparse_eye(n, format="csr")), shift, "absolute"
    # relative_diagonal_shift: mu * median(|diag nonzero|)
    diag = np.abs(np.asarray(k_free.diagonal(), dtype=np.float64))
    nz = diag[diag > 0.0]
    scale = float(np.median(nz)) if nz.size else 1.0
    shift = float(mu) * scale
    return (k_free + shift * sparse_eye(n, format="csr")), shift, f"relative_median_diag={scale:.6e}"


def solve_regularized_direction(
    k_free: Any,
    residual_fn: ResidualFn,
    x0: np.ndarray,
    *,
    mode: str,
    mu: float,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Sparse-direct solve of (K + reg) p = -R(x0); fail-closed with reason codes."""
    import warnings

    x0 = np.asarray(x0, dtype=np.float64)
    r0 = np.asarray(residual_fn(x0), dtype=np.float64)
    b = -r0
    k_reg, eff_shift, scale_source = regularize_matrix(k_free, mode, mu)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            p = np.asarray(spsolve(csc_matrix(k_reg), b), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        return None, {"mode": mode, "mu": float(mu), "effective_shift": eff_shift,
                      "scale_source": scale_source, "factorization_pass": False,
                      "reason_code": ERR_REGULARIZED_SOLVE_FAILED, "detail": str(exc)[:160]}
    if not bool(np.all(np.isfinite(p))):
        return None, {"mode": mode, "mu": float(mu), "effective_shift": eff_shift,
                      "scale_source": scale_source, "factorization_pass": True,
                      "reason_code": ERR_REGULARIZED_DIRECTION_NAN}
    cosine_with_neg_residual = _safe_cosine(p, b)
    return p, {"mode": mode, "mu": float(mu), "effective_shift": eff_shift,
               "scale_source": scale_source, "factorization_pass": True,
               "reason_code": PASS, "cosine_with_neg_residual": cosine_with_neg_residual}
