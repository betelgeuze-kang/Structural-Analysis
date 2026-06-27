#!/usr/bin/env python3
"""Component-wise operator reconciliation audit helpers (F2c).

Pure numeric helpers to decompose and compare the physical residual directional
derivative (J_phys . v) against the assembled tangent action (K . v) component by
component, and to rank which component drives the decorrelation found in F2b-ii-a.

These helpers are an audit only: they never modify the solver and never promote G1.
"""

from __future__ import annotations

from typing import Any

import numpy as np


CLASSIFY_CONSISTENT = "consistent"
CLASSIFY_SCALE_FACTOR = "scale_factor"
CLASSIFY_DECORRELATED = "decorrelated_not_scale_factor"

ERR_COMPONENT_SHAPE_MISMATCH = "ERR_COMPONENT_SHAPE_MISMATCH"


def safe_cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity that returns 0.0 when either vector is (near) zero."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1.0e-300 or nb <= 1.0e-300:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def classify_mismatch(
    kv: np.ndarray,
    jv: np.ndarray,
    *,
    parity_rel_tol: float = 1.0e-3,
    alignment_cosine: float = 0.99,
) -> str:
    """Classify K.v vs J.v as consistent, scale-only, or decorrelated."""
    kv = np.asarray(kv, dtype=np.float64)
    jv = np.asarray(jv, dtype=np.float64)
    nk = float(np.linalg.norm(kv))
    nj = float(np.linalg.norm(jv))
    if nk <= 1.0e-300 and nj <= 1.0e-300:
        return CLASSIFY_CONSISTENT
    cos = safe_cosine(kv, jv)
    abs_cos = abs(cos)
    norm_ratio = nk / nj if nj > 0.0 else float("inf")
    if abs_cos >= 1.0 - parity_rel_tol and abs(norm_ratio - 1.0) <= parity_rel_tol:
        return CLASSIFY_CONSISTENT
    if abs_cos >= alignment_cosine:
        return CLASSIFY_SCALE_FACTOR
    return CLASSIFY_DECORRELATED


def component_rows(
    component_actions: dict[str, np.ndarray],
    reference: np.ndarray,
    *,
    expected_shape: tuple[int, ...] | None = None,
) -> list[dict[str, Any]]:
    """Build per-component comparison rows against a reference action vector.

    Raises ValueError tagged with ERR_COMPONENT_SHAPE_MISMATCH if a component
    action does not match the reference shape.
    """
    reference = np.asarray(reference, dtype=np.float64)
    ref_norm = float(np.linalg.norm(reference))
    rows: list[dict[str, Any]] = []
    for name, action in component_actions.items():
        if action is None:
            rows.append({"component": name, "present": False, "norm": 0.0,
                         "cosine_with_reference": 0.0, "contribution_ratio": 0.0})
            continue
        action = np.asarray(action, dtype=np.float64)
        if expected_shape is not None and action.shape != tuple(expected_shape):
            raise ValueError(f"{ERR_COMPONENT_SHAPE_MISMATCH}:{name}:{action.shape}!={expected_shape}")
        if reference.size and action.shape != reference.shape:
            raise ValueError(f"{ERR_COMPONENT_SHAPE_MISMATCH}:{name}:{action.shape}!={reference.shape}")
        norm = float(np.linalg.norm(action))
        rows.append({
            "component": name,
            "present": True,
            "norm": norm,
            "inf_norm": float(np.max(np.abs(action))) if action.size else 0.0,
            "cosine_with_reference": safe_cosine(action, reference),
            "contribution_ratio": (norm / ref_norm) if ref_norm > 0.0 else 0.0,
            "sign_alignment": float(np.dot(action, reference)),
        })
    return rows


def rank_suspects(rows: list[dict[str, Any]], *, parity_pass: bool) -> list[dict[str, Any]]:
    """Rank components most responsible for the decorrelation.

    A component is a strong suspect when it carries a large share of the reference
    norm (it dominates J_phys) while the assembled tangent fails to reproduce it.
    When parity passes there are no suspects.
    """
    if parity_pass:
        return []
    present = [r for r in rows if r.get("present")]
    ranked = sorted(present, key=lambda r: float(r.get("contribution_ratio") or 0.0), reverse=True)
    suspects: list[dict[str, Any]] = []
    for i, row in enumerate(ranked):
        if float(row.get("contribution_ratio") or 0.0) <= 0.0:
            continue
        suspects.append({
            "component": row["component"],
            "contribution_ratio": float(row["contribution_ratio"]),
            "cosine_with_reference": float(row["cosine_with_reference"]),
            "reason": (
                "dominates the physical residual directional derivative; "
                "assembled tangent does not reproduce this component's magnitude/direction"
            ),
            "priority": i + 1,
        })
    return suspects
