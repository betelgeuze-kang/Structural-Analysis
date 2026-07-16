"""Viewer payload builder sourced only from authoritative solver results."""

from __future__ import annotations

import re
from typing import Any, Mapping

import numpy as np

REACTION_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
VIEWER_SCHEMA_VERSION = "structural-analysis-viewer-payload.v2"
VIEWER_MODEL_IDENTITY_POLICY = "source_bytes_and_detached_canonical_model_v1"
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


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

    Model identity is bound later at the public analysis boundary, where the
    exact source-byte checksum and detached canonical snapshot checksum are both
    available. Direct solver payloads therefore remain explicitly unbound until
    :func:`bind_viewer_model_identity` succeeds.
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


def bind_viewer_model_identity(
    payload: Mapping[str, Any],
    *,
    source_input_checksum: str,
    canonical_model_checksum: str,
) -> dict[str, Any]:
    """Return a viewer payload bound to both source bytes and analysis semantics.

    ``source_input_checksum`` identifies the imported file bytes. The canonical
    checksum identifies the detached, source-path-independent model envelope
    actually supplied to analysis. Neither value is a solver-validation or
    signed-authenticity claim.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("Viewer payload must be a mapping.")
    if payload.get("schema_version") != VIEWER_SCHEMA_VERSION:
        raise ValueError("Viewer model identity requires the supported payload schema.")
    if "model_identity" in payload:
        raise ValueError("Viewer payload already contains model identity.")
    _require_hash(source_input_checksum, "source_input_checksum")
    _require_hash(canonical_model_checksum, "canonical_model_checksum")

    bound = dict(payload)
    bound["model_identity"] = {
        "identity_policy": VIEWER_MODEL_IDENTITY_POLICY,
        "source_input_checksum": source_input_checksum,
        "canonical_model_checksum": canonical_model_checksum,
        "analysis_input_snapshot": "detached_canonical_model_v1",
    }
    return bound


def _require_hash(value: Any, label: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>.")
    return value
