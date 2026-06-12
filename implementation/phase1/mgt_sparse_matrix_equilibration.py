#!/usr/bin/env python3
"""Symmetric diagonal scaling for ill-conditioned coupled equilibrium tangents."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.sparse import diags


def symmetric_sqrt_diagonal_scaling(
    k_ff: Any,
    rhs: np.ndarray,
    *,
    diag_floor: float = 1.0,
    diag_cap_percentile: float = 99.5,
) -> tuple[Any, np.ndarray, np.ndarray, dict[str, Any]]:
    """Return D K D, D rhs, and per-row scale with 1/sqrt(|diag|) clamped."""
    csr = k_ff.tocsr()
    rhs_np = np.asarray(rhs, dtype=np.float64).reshape(-1)
    diag = np.asarray(np.abs(csr.diagonal()), dtype=np.float64)
    if diag.size == 0:
        return csr, rhs_np, np.ones(0, dtype=np.float64), {
            "equilibration": "symmetric_sqrt_diagonal",
            "applied": False,
        }
    positive = diag[diag > 0.0]
    cap = float(np.percentile(positive, float(diag_cap_percentile))) if positive.size else float(diag_floor)
    cap = max(cap, float(diag_floor))
    diag_clamped = np.clip(diag, float(diag_floor), cap)
    scale = 1.0 / np.sqrt(diag_clamped)
    d_op = diags(scale, format="csr")
    k_scaled = (d_op @ csr @ d_op).tocsr()
    rhs_scaled = scale * rhs_np
    return k_scaled, rhs_scaled, scale, {
        "equilibration": "symmetric_sqrt_diagonal",
        "applied": True,
        "diag_floor": float(diag_floor),
        "diag_cap_percentile": float(diag_cap_percentile),
        "diag_cap": cap,
        "diag_abs_min": float(np.min(diag)) if diag.size else 0.0,
        "diag_abs_max": float(np.max(diag)) if diag.size else 0.0,
        "diag_abs_mean": float(np.mean(diag)) if diag.size else 0.0,
        "scaled_diag_abs_max": float(np.max(np.abs(k_scaled.diagonal()))) if k_scaled.nnz else 0.0,
    }


def unscale_solution(solution_scaled: np.ndarray, scale: np.ndarray) -> np.ndarray:
    scaled = np.asarray(solution_scaled, dtype=np.float64).reshape(-1)
    if scale.size != scaled.size:
        return scaled
    return scale * scaled
