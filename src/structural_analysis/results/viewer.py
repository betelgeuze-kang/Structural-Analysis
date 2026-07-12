"""Viewer payload builder sourced only from authoritative solver results."""

from __future__ import annotations

from typing import Any

import numpy as np

REACTION_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
VIEWER_SCHEMA_VERSION = "structural-analysis-viewer-payload.v2"


def build_linear_static_viewer_payload(
    *,
    node_ids: tuple[str, ...],
    node_coordinates: tuple[tuple[float, float, float], ...],
    dof_labels: tuple[str, ...],
    displacements: np.ndarray,
    reactions: np.ndarray,
    equilibrium_residuals: np.ndarray,
    member_forces: list[dict[str, Any]],
    solver_path_id: str,
) -> dict[str, Any]:
    """Project one authoritative solution into the versioned viewer envelope.

    ``reaction`` contains constrained-DOF support reactions only. Free-DOF
    numerical imbalance is exposed separately as ``equilibrium_residual`` so it
    cannot be mistaken for a physical support reaction.
    """

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
                "equilibrium_residual": {
                    REACTION_LABELS[offset]: float(
                        equilibrium_residuals[base + offset]
                    )
                    for offset in range(width)
                },
            }
        )
    return {
        "schema_version": VIEWER_SCHEMA_VERSION,
        "source": "authoritative_solver_result",
        "solver_path_id": solver_path_id,
        "analysis_fidelity": "cpu_reference_linear_fea",
        "reaction_definition": "constrained_dof_internal_minus_external_force",
        "equilibrium_residual_definition": (
            "free_dof_internal_minus_external_force; constrained entries are zero"
        ),
        "nodes": nodes,
        "elements": member_forces,
    }
