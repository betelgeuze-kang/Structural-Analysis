#!/usr/bin/env python3
"""Null-space mode audit helpers (F2g-alt).

Pure helpers to map a near-null eigenvector of the assembled free-space tangent to
node / DOF-type structure and classify the mechanism. Audit only: never modifies the
solver and never promotes G1.
"""

from __future__ import annotations

from typing import Any

import numpy as np


DOF_TYPES = ("UX", "UY", "UZ", "RX", "RY", "RZ")

CLASS_DRILLING = "drilling_rotation_like"
CLASS_UNRESTRAINED_ROTATION = "unrestrained_rotation"
CLASS_TRANSLATION = "translation_mechanism_like"
CLASS_DISTRIBUTED = "mixed_or_distributed"


def dof_type_for(global_dof: int, dof_per_node: int) -> str:
    return DOF_TYPES[int(global_dof) % int(dof_per_node)] if dof_per_node else "UNKNOWN"


def scan_diagonal(diag: np.ndarray, *, floor: float = 1.0e-8) -> dict[str, Any]:
    diag = np.abs(np.asarray(diag, dtype=np.float64))
    return {
        "diag_min_abs": float(np.min(diag)) if diag.size else 0.0,
        "diag_max_abs": float(np.max(diag)) if diag.size else 0.0,
        "zero_diag_count": int(np.count_nonzero(diag == 0.0)),
        "tiny_diag_count": int(np.count_nonzero(diag < floor)),
        "tiny_diag_floor": float(floor),
    }


def map_mode_to_dofs(
    z: np.ndarray,
    free: np.ndarray,
    node_id: np.ndarray,
    dof_per_node: int,
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Map a free-space mode vector to dominant DOF types and nodes (by energy z^2)."""
    z = np.asarray(z, dtype=np.float64)
    free = np.asarray(free, dtype=np.int64)
    node_id = np.asarray(node_id, dtype=np.int64)
    total = float(np.dot(z, z)) or 1.0
    type_energy: dict[str, float] = {t: 0.0 for t in DOF_TYPES}
    for i, gdof in enumerate(free.tolist()):
        t = dof_type_for(gdof, dof_per_node)
        type_energy[t] += float(z[i] * z[i])
    dominant_dof_types = {t: (e / total) for t, e in type_energy.items() if e > 0.0}
    order = np.argsort(-np.abs(z))[: max(1, int(top))]
    dominant_nodes = []
    for i in order.tolist():
        gdof = int(free[i])
        node_index = gdof // int(dof_per_node)
        dominant_nodes.append({
            "free_dof_index": int(free[i]),
            "node_id": int(node_id[node_index]) if 0 <= node_index < node_id.size else None,
            "dof": dof_type_for(gdof, dof_per_node),
            "amplitude": float(z[i]),
        })
    return {"dominant_dof_types": dominant_dof_types, "dominant_nodes": dominant_nodes}


def classify_mode(dominant_dof_types: dict[str, float]) -> str:
    d = {t: float(dominant_dof_types.get(t, 0.0)) for t in DOF_TYPES}
    rot = d["RX"] + d["RY"] + d["RZ"]
    trans = d["UX"] + d["UY"] + d["UZ"]
    if d["RZ"] >= 0.5:
        return CLASS_DRILLING
    if rot >= 0.6:
        return CLASS_UNRESTRAINED_ROTATION
    if trans >= 0.6:
        return CLASS_TRANSLATION
    return CLASS_DISTRIBUTED


def aggregate_pinning_candidates(mode_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Propose (not apply) pinning candidate sets from the audited near-null modes."""
    type_counts: dict[str, int] = {}
    for row in mode_rows:
        ddt = row.get("dominant_dof_types", {})
        if not ddt:
            continue
        top_type = max(ddt, key=lambda k: ddt[k])
        type_counts[top_type] = type_counts.get(top_type, 0) + 1
    candidates = []
    for dof_type, count in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        candidates.append({
            "strategy": f"pin_dominant_{dof_type}_modes",
            "target_dof_type": dof_type,
            "candidate_count": int(count),
            "claim_boundary": "candidate_only_not_applied",
        })
    return candidates
