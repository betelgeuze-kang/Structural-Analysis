"""Thin IFC STEP adapter for Developer Preview import health checks."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any

from structural_analysis.io.neutral.loader import checksum_for_path
from structural_analysis.model.schema import CANONICAL_MODEL_SCHEMA_VERSION, CanonicalModel
from structural_analysis.units.schema import CoordinateSystem, UnitSystem

STRUCTURAL_ENTITY_TYPES = {
    "IFCBEAM": "frame",
    "IFCCOLUMN": "frame",
    "IFCMEMBER": "frame",
    "IFCSLAB": "shell",
    "IFCPLATE": "shell",
    "IFCWALL": "shell",
    "IFCWALLSTANDARDCASE": "shell",
    "IFCFOOTING": "foundation",
    "IFCPILE": "foundation",
}
STOREY_ENTITY_TYPES = {"IFCBUILDINGSTOREY"}
MATERIAL_ENTITY_PREFIXES = (
    "IFCMATERIAL",
)
SECTION_ENTITY_SUFFIXES = (
    "PROFILEDEF",
    "PROFILESET",
    "LAYERSET",
    "CONSTITUENTSET",
)
LOAD_GROUP_ENTITY_TYPES = {"IFCLOADGROUP", "IFCSTRUCTURALLOADGROUP"}
LOAD_RELATIONSHIP_ENTITY_TYPES = {
    "IFCRELCONNECTSSTRUCTURALACTIVITY",
    "IFCRELASSIGNSTOGROUP",
}
ENTITY_RE = re.compile(
    r"^\s*#(?P<id>\d+)\s*=\s*(?P<type>[A-Z0-9_]+)\s*\((?P<args>.*)\)\s*;\s*$",
    re.IGNORECASE | re.DOTALL,
)


def load_ifc_step(path: Path) -> CanonicalModel:
    records = _records(path)
    parsed_records = [record for record in (_record_args(item) for item in records) if record]
    entity_counts = Counter(entity_type for _entity_id, entity_type, _args in parsed_records)

    structural_elements: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    loads: list[dict[str, Any]] = []
    storeys: list[dict[str, Any]] = []

    for entity_id, entity_type, args in parsed_records:
        if entity_type in STRUCTURAL_ENTITY_TYPES:
            structural_elements.append(
                {
                    "id": entity_id,
                    "type": STRUCTURAL_ENTITY_TYPES[entity_type],
                    "source_type": entity_type,
                    "name": _label_from_args(args, fallback=entity_id),
                    "nodes": [],
                    "material": "",
                    "section": "",
                }
            )
            continue
        if entity_type in STOREY_ENTITY_TYPES:
            storeys.append(
                {
                    "id": entity_id,
                    "source_type": entity_type,
                    "name": _label_from_args(args, fallback=entity_id),
                }
            )
            continue
        if _is_material_entity(entity_type):
            materials.append(
                {
                    "id": entity_id,
                    "type": entity_type.lower(),
                    "source_type": entity_type,
                    "name": _label_from_args(args, fallback=entity_id),
                }
            )
            continue
        if _is_section_entity(entity_type):
            sections.append(
                {
                    "id": entity_id,
                    "source_type": entity_type,
                    "name": _label_from_args(args, fallback=entity_id),
                }
            )
            continue
        if _is_load_related_entity(entity_type):
            loads.append(
                {
                    "id": entity_id,
                    "kind": _load_kind(entity_type),
                    "source_type": entity_type,
                    "name": _label_from_args(args, fallback=entity_id),
                }
            )

    unsupported_features = _unsupported_features(
        record_count=len(records),
        structural_count=len(structural_elements),
        material_count=len(materials),
        section_count=len(sections),
        load_count=len(loads),
    )
    warnings = [
        "IFC adapter is STEP text scan only; exact placements, representation geometry, "
        "materials, sections, and loads require later adapter receipts."
    ]
    if not any(entity_type.startswith("IFCSIUNIT") for entity_type in entity_counts):
        warnings.append("No normalized IFC unit assignment was extracted; units are unknown.")

    return CanonicalModel(
        schema_version=CANONICAL_MODEL_SCHEMA_VERSION,
        source_path=str(path),
        source_format="ifc_step",
        input_checksum=checksum_for_path(path),
        units=UnitSystem(length="unknown", force="unknown"),
        coordinate_system=CoordinateSystem(axis_order=("X", "Y", "Z"), up_axis="Z"),
        nodes=[],
        elements=structural_elements,
        materials=materials,
        sections=sections,
        loads=loads,
        supports=[],
        unsupported_features=unsupported_features,
        warnings=warnings,
        metadata={
            "adapter": "structural_analysis.io.ifc.load_ifc_step",
            "adapter_scope": (
                "IFC entity scan only; exact topology, placement coordinates, "
                "geometry, material/section binding, and load evidence remain blocked"
            ),
            "record_count": len(records),
            "parsed_record_count": len(parsed_records),
            "entity_counts": {key: int(value) for key, value in sorted(entity_counts.items())},
            "storeys": storeys,
            "structural_entity_count": len(structural_elements),
            "material_entity_count": len(materials),
            "section_entity_count": len(sections),
            "load_related_entity_count": len(loads),
            "text_scan_only": True,
        },
    )


def _records(path: Path) -> list[str]:
    records: list[str] = []
    current: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if current:
            current.append(stripped)
        elif stripped.startswith("#"):
            current.append(stripped)
        else:
            continue
        if stripped.endswith(";"):
            records.append(" ".join(current))
            current = []
    return records


def _record_args(record: str) -> tuple[str, str, list[str]] | None:
    match = ENTITY_RE.match(record)
    if not match:
        return None
    return f"#{match.group('id')}", match.group("type").upper(), _split_step_args(match.group("args"))


def _split_step_args(text: str) -> list[str]:
    args: list[str] = []
    buffer: list[str] = []
    depth = 0
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            buffer.append(char)
            if in_string and index + 1 < len(text) and text[index + 1] == "'":
                buffer.append(text[index + 1])
                index += 2
                continue
            in_string = not in_string
        elif not in_string and char == "(":
            depth += 1
            buffer.append(char)
        elif not in_string and char == ")":
            depth = max(depth - 1, 0)
            buffer.append(char)
        elif not in_string and char == "," and depth == 0:
            args.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
        index += 1
    args.append("".join(buffer).strip())
    return args


def _label_from_args(args: list[str], *, fallback: str) -> str:
    for candidate_index in (2, 0, 1):
        if candidate_index >= len(args):
            continue
        label = _step_label(args[candidate_index])
        if label:
            return label
    return fallback


def _step_label(value: str) -> str:
    text = str(value or "").strip()
    if not text or text in {"$", "*"}:
        return ""
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text.startswith(".") and text.endswith(".") and len(text) >= 2:
        return text[1:-1]
    if text.startswith("#"):
        return ""
    return text


def _is_material_entity(entity_type: str) -> bool:
    return any(entity_type.startswith(prefix) for prefix in MATERIAL_ENTITY_PREFIXES)


def _is_section_entity(entity_type: str) -> bool:
    return any(entity_type.endswith(suffix) for suffix in SECTION_ENTITY_SUFFIXES)


def _is_load_related_entity(entity_type: str) -> bool:
    return (
        entity_type in LOAD_GROUP_ENTITY_TYPES
        or entity_type in LOAD_RELATIONSHIP_ENTITY_TYPES
        or (entity_type.startswith("IFCSTRUCTURALLOAD") and entity_type not in LOAD_GROUP_ENTITY_TYPES)
        or (entity_type.startswith("IFCSTRUCTURAL") and "ACTION" in entity_type)
    )


def _load_kind(entity_type: str) -> str:
    if entity_type in LOAD_GROUP_ENTITY_TYPES:
        return "ifc_load_group"
    if entity_type in LOAD_RELATIONSHIP_ENTITY_TYPES:
        return "ifc_load_relationship"
    if entity_type.startswith("IFCSTRUCTURALLOAD"):
        return "ifc_structural_load"
    if "ACTION" in entity_type:
        return "ifc_structural_action"
    return "ifc_load_related"


def _unsupported_features(
    *,
    record_count: int,
    structural_count: int,
    material_count: int,
    section_count: int,
    load_count: int,
) -> list[dict[str, Any]]:
    unsupported: list[dict[str, Any]] = []
    if record_count == 0:
        unsupported.append(
            {
                "kind": "ifc_step_records_missing",
                "detail": "No STEP entity records were found in the IFC file.",
            }
        )
    if structural_count == 0:
        unsupported.append(
            {
                "kind": "ifc_structural_entities_missing",
                "detail": "No supported IFC structural product entities were found.",
            }
        )
    else:
        unsupported.append(
            {
                "kind": "ifc_geometry_not_canonicalized",
                "detail": (
                    "Structural IFC entities were counted, but exact placement and "
                    "representation geometry are not canonicalized by this thin adapter."
                ),
                "structural_entity_count": structural_count,
            }
        )
    if material_count == 0:
        unsupported.append(
            {
                "kind": "ifc_material_binding_missing",
                "detail": "No IFC material entities were extracted for canonical material binding.",
            }
        )
    if section_count == 0:
        unsupported.append(
            {
                "kind": "ifc_section_binding_missing",
                "detail": "No IFC profile/layer/section entities were extracted.",
            }
        )
    if load_count == 0:
        unsupported.append(
            {
                "kind": "ifc_load_model_missing",
                "detail": (
                    "No IFC structural load/action/load-group entities were extracted; "
                    "analysis claims require load evidence or engineer-signed zero-load evidence."
                ),
            }
        )
    return unsupported
