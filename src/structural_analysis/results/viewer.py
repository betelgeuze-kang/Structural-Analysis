"""Viewer payload builder sourced only from authoritative solver results."""

from __future__ import annotations

from typing import Any

import numpy as np

REACTION_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")


def build_linear_static_viewer_payload(
    *,
    node_ids: tuple[str, ...],
    node_coordinates: tuple[tuple[float, float, float], ...],
    dof_labels: tuple[str, ...],
    displacements: np.ndarray,
    reactions: np.ndarray,
    member_forces: list[dict[str, Any]],
    solver_path_id: str,
) -> dict[str, Any]:
    width = len(dof_labels)
    nodes = []
    for index, node_id in enumerate(node_ids):
        base = width * index
        nodes.append(
            {
                "id": node_id,
                "coordinates": list(node_coordinates[index]),
                "displacement": {
                    label: float(displacements[base + offset])
                    for offset, label in enumerate(dof_labels)
                },
                "reaction": {
                    REACTION_LABELS[offset]: float(reactions[base + offset])
                    for offset in range(width)
                },
            }
        )
    return {
        "schema_version": "structural-analysis-viewer-payload.v1",
        "source": "authoritative_solver_result",
        "solver_path_id": solver_path_id,
        "analysis_fidelity": "cpu_reference_linear_fea",
        "nodes": nodes,
        "elements": member_forces,
    }
