#!/usr/bin/env python3
"""Diagonal stiffness scale audit for coupled frame-shell-spring operators."""

from __future__ import annotations

from typing import Any

import numpy as np


def audit_coupled_stiffness_diagonals(
    *,
    components: dict[str, Any],
    free_global_dofs: np.ndarray,
    imbalance_ratio_threshold: float = 1.0e8,
) -> dict[str, Any]:
    """Summarize free-DOF diagonal scales per coupled stiffness component."""
    free = np.asarray(free_global_dofs, dtype=np.int64).reshape(-1)
    per_component: dict[str, Any] = {}
    mins: list[float] = []
    maxs: list[float] = []
    for name, matrix in components.items():
        if matrix is None:
            continue
        diag_global = np.asarray(matrix.diagonal(), dtype=np.float64)
        if free.size == 0 or diag_global.size == 0:
            per_component[name] = {"free_diag_count": 0}
            continue
        diag = np.abs(diag_global[free])
        nonzero = diag[diag > 0.0]
        if nonzero.size == 0:
            per_component[name] = {
                "free_diag_count": int(diag.size),
                "nonzero_diag_count": 0,
            }
            continue
        comp_min = float(np.min(nonzero))
        comp_max = float(np.max(nonzero))
        mins.append(comp_min)
        maxs.append(comp_max)
        per_component[name] = {
            "free_diag_count": int(diag.size),
            "nonzero_diag_count": int(nonzero.size),
            "diag_abs_min": comp_min,
            "diag_abs_max": comp_max,
            "diag_abs_mean": float(np.mean(nonzero)),
            "diag_abs_median": float(np.median(nonzero)),
            "unit": "N_per_m_or_Nm_per_rad",
        }
    cross_min = min(mins) if mins else 0.0
    cross_max = max(maxs) if maxs else 0.0
    cross_ratio = cross_max / max(cross_min, 1.0e-30)
    return {
        "per_component": per_component,
        "cross_component_diag_max_ratio": float(cross_ratio),
        "unit_consistency_warning": bool(cross_ratio > float(imbalance_ratio_threshold)),
        "imbalance_ratio_threshold": float(imbalance_ratio_threshold),
        "claim_boundary": (
            "Diagonal audit only; it does not prove unit conversion correctness but flags "
            "solver-hostile stiffness scale separation across coupled components."
        ),
    }
