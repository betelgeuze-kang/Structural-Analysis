"""Loader for the first neutral canonical JSON model format."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


def checksum_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def load_neutral_json(path: Path) -> CanonicalModel:
    raw = path.read_bytes()
    return load_neutral_json_bytes(raw, source_path=str(path))


def load_neutral_json_bytes(
    raw: bytes | bytearray | memoryview,
    *,
    source_path: str = "memory://neutral-model.json",
) -> CanonicalModel:
    """Load one immutable in-memory neutral model for a durable worker request."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise ValueError("Neutral canonical model input must be bytes-like.")
    encoded = bytes(raw)
    if not encoded or len(encoded) > 16 * 1024 * 1024:
        raise ValueError("Neutral canonical model input exceeds the bounded byte profile.")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Neutral canonical model must be valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Neutral canonical model must be a JSON object.")

    return _load_neutral_payload(
        payload,
        source_path=source_path,
        input_checksum=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    )


def _load_neutral_payload(
    payload: dict[str, Any], *, source_path: str, input_checksum: str
) -> CanonicalModel:

    schema_version = str(
        payload.get("schema_version", CANONICAL_MODEL_SCHEMA_VERSION)
    )
    if schema_version != CANONICAL_MODEL_SCHEMA_VERSION:
        raise ValueError(f"Unsupported canonical model schema: {schema_version}")

    units_payload = _object(payload, "units")
    coordinate_payload = _object(payload, "coordinate_system")
    units = UnitSystem(
        length=str(units_payload.get("length", "")),
        force=str(units_payload.get("force", "")),
    )
    coordinate_system = CoordinateSystem(
        axis_order=tuple(coordinate_payload.get("axis_order", [])),
        up_axis=str(coordinate_payload.get("up_axis", "")),
    )

    warnings = _validate_topology(payload)
    return CanonicalModel(
        schema_version=schema_version,
        source_path=source_path,
        source_format="neutral_json",
        input_checksum=input_checksum,
        units=units,
        coordinate_system=coordinate_system,
        nodes=_list(payload, "nodes"),
        elements=_list(payload, "elements"),
        materials=_list(payload, "materials"),
        sections=_list(payload, "sections"),
        loads=_list(payload, "loads"),
        supports=_list(payload, "supports"),
        unsupported_features=_list(payload, "unsupported_features"),
        warnings=warnings + [str(item) for item in payload.get("warnings", [])],
        metadata=_object(payload, "metadata", required=False),
    )


def _object(payload: dict[str, Any], key: str, required: bool = True) -> dict[str, Any]:
    value = payload.get(key)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object.")
    return value


def _list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array.")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{key} must contain JSON objects.")
    return value


def _validate_topology(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    node_ids = set()
    for node in _list(payload, "nodes"):
        node_id = node.get("id")
        coords = node.get("coordinates")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("Each node must carry a non-empty string id.")
        if node_id in node_ids:
            raise ValueError(f"Duplicate node id: {node_id}")
        if not isinstance(coords, list) or len(coords) != 3:
            raise ValueError(f"Node {node_id} coordinates must contain three values.")
        node_ids.add(node_id)

    for element in _list(payload, "elements"):
        element_id = element.get("id")
        connectivity = element.get("nodes")
        if not isinstance(element_id, str) or not element_id:
            raise ValueError("Each element must carry a non-empty string id.")
        if not isinstance(connectivity, list) or len(connectivity) < 2:
            raise ValueError(f"Element {element_id} must reference at least two nodes.")
        missing = [node_id for node_id in connectivity if node_id not in node_ids]
        if missing:
            raise ValueError(f"Element {element_id} references missing nodes: {missing}")

    if not node_ids:
        warnings.append("Canonical model has no nodes.")
    return warnings
