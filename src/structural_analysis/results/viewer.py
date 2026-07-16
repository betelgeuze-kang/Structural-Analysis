"""Viewer payload builder sourced only from authoritative solver results."""

from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import numpy as np

REACTION_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
DISPLACEMENT_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
VIEWER_SCHEMA_VERSION = "structural-analysis-viewer-payload.v2"
VIEWER_MODEL_IDENTITY_POLICY = "source_bytes_and_detached_canonical_model_v1"
VIEWER_SCHEMA_RESOURCE = "viewer_payload.schema.json"
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ViewerPayloadValidationError(ValueError):
    """Fail-closed Viewer payload contract violation."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


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
    payload = {
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
    return validate_linear_static_viewer_payload(
        payload,
        require_bound_identity=False,
    )


def bind_viewer_model_identity(
    payload: Mapping[str, Any],
    *,
    source_input_checksum: str,
    canonical_model_checksum: str,
) -> dict[str, Any]:
    """Return a Viewer payload bound to source bytes and analysis semantics.

    ``source_input_checksum`` identifies the imported file bytes. The canonical
    checksum identifies the detached, source-path-independent model envelope
    actually supplied to analysis. Neither value is a solver-validation or
    signed-authenticity claim.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("Viewer payload must be a mapping.")
    unbound = dict(payload)
    validate_linear_static_viewer_payload(
        unbound,
        require_bound_identity=False,
    )
    if "model_identity" in unbound:
        raise ViewerPayloadValidationError(
            "viewer_model_identity_already_bound",
            "/model_identity",
            "Viewer payload already contains model identity.",
        )
    _require_hash(source_input_checksum, "source_input_checksum")
    _require_hash(canonical_model_checksum, "canonical_model_checksum")

    unbound["model_identity"] = {
        "identity_policy": VIEWER_MODEL_IDENTITY_POLICY,
        "source_input_checksum": source_input_checksum,
        "canonical_model_checksum": canonical_model_checksum,
        "analysis_input_snapshot": "detached_canonical_model_v1",
    }
    return validate_linear_static_viewer_payload(unbound)


def validate_linear_static_viewer_payload(
    payload: Mapping[str, Any],
    *,
    require_bound_identity: bool = True,
) -> dict[str, Any]:
    """Validate JSON shape, finite numerics, IDs, and topology references."""

    if type(payload) is not dict:
        raise ViewerPayloadValidationError(
            "viewer_payload_type_invalid",
            "/",
            "Viewer payload must use an exact dictionary.",
        )
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        raise ViewerPayloadValidationError(
            "viewer_payload_schema_invalid",
            path or "/",
            error.message,
        )

    identity = payload.get("model_identity")
    if require_bound_identity and identity is None:
        raise ViewerPayloadValidationError(
            "viewer_model_identity_missing",
            "/model_identity",
            "Public Viewer payload requires bound model identity.",
        )
    if identity is not None:
        _validate_identity(identity)

    node_rows = payload["nodes"]
    node_ids: list[str] = []
    for index, row in enumerate(node_rows):
        node_id = row["id"]
        node_ids.append(node_id)
        _validate_number_sequence(row["coordinates"], f"/nodes/{index}/coordinates")
        _validate_vector(
            row["displacement"],
            DISPLACEMENT_LABELS,
            f"/nodes/{index}/displacement",
        )
        _validate_vector(
            row["reaction"],
            REACTION_LABELS,
            f"/nodes/{index}/reaction",
        )
        _validate_vector(
            row["equilibrium_residual"],
            REACTION_LABELS,
            f"/nodes/{index}/equilibrium_residual",
        )
    if len(set(node_ids)) != len(node_ids):
        raise ViewerPayloadValidationError(
            "viewer_node_id_duplicate",
            "/nodes",
            "Viewer node IDs must be unique.",
        )

    node_id_set = set(node_ids)
    element_ids: list[str] = []
    for index, row in enumerate(payload["elements"]):
        element_ids.append(row["id"])
        element_nodes = row["nodes"]
        if element_nodes[0] == element_nodes[1]:
            raise ViewerPayloadValidationError(
                "viewer_element_connectivity_degenerate",
                f"/elements/{index}/nodes",
                "Viewer element endpoints must be distinct.",
            )
        unknown_nodes = [value for value in element_nodes if value not in node_id_set]
        if unknown_nodes:
            raise ViewerPayloadValidationError(
                "viewer_element_node_missing",
                f"/elements/{index}/nodes",
                f"Viewer element references unknown nodes: {unknown_nodes}.",
            )
        _validate_vector_values(
            row["local_end_forces"],
            f"/elements/{index}/local_end_forces",
        )
        for field_name in ("axial_force", "elongation"):
            if field_name in row:
                _require_finite_number(
                    row[field_name],
                    f"/elements/{index}/{field_name}",
                )
    if len(set(element_ids)) != len(element_ids):
        raise ViewerPayloadValidationError(
            "viewer_element_id_duplicate",
            "/elements",
            "Viewer element IDs must be unique.",
        )
    return dict(payload)


def _validate_identity(identity: Any) -> None:
    if type(identity) is not dict:
        raise ViewerPayloadValidationError(
            "viewer_model_identity_type_invalid",
            "/model_identity",
            "Model identity must use an exact dictionary.",
        )
    if identity["identity_policy"] != VIEWER_MODEL_IDENTITY_POLICY:
        raise ViewerPayloadValidationError(
            "viewer_model_identity_policy_invalid",
            "/model_identity/identity_policy",
            "Unknown Viewer model identity policy.",
        )
    _require_hash(identity["source_input_checksum"], "source_input_checksum")
    _require_hash(identity["canonical_model_checksum"], "canonical_model_checksum")


def _validate_number_sequence(values: Any, path: str) -> None:
    if type(values) is not list:
        raise ViewerPayloadValidationError(
            "viewer_numeric_sequence_invalid",
            path,
            "Expected an exact numeric list.",
        )
    for index, value in enumerate(values):
        _require_finite_number(value, f"{path}/{index}")


def _validate_vector(values: Any, labels: tuple[str, ...], path: str) -> None:
    if type(values) is not dict or tuple(values) != labels:
        raise ViewerPayloadValidationError(
            "viewer_vector_layout_invalid",
            path,
            f"Expected exact ordered components {list(labels)}.",
        )
    _validate_vector_values(values, path)


def _validate_vector_values(values: Mapping[str, Any], path: str) -> None:
    for label, value in values.items():
        _require_finite_number(value, f"{path}/{label}")


def _require_finite_number(value: Any, path: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ViewerPayloadValidationError(
            "viewer_numeric_value_invalid",
            path,
            "Viewer numerical values must be exact finite JSON numbers.",
        )
    return float(value)


def _require_hash(value: Any, label: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        raise ViewerPayloadValidationError(
            "viewer_checksum_invalid",
            f"/model_identity/{label}",
            f"{label} must be sha256:<64 lowercase hex>.",
        )
    return value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / VIEWER_SCHEMA_RESOURCE
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
