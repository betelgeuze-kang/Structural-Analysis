"""Thin MIDAS MGT adapter for the canonical Developer Preview model."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re
from typing import Any

from structural_analysis.io.neutral.loader import checksum_for_path
from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)
from structural_analysis.units.schema import CoordinateSystem, UnitSystem

KNOWN_MGT_SECTIONS = {
    "ROOT",
    "UNIT",
    "NODE",
    "ELEMENT",
    "MATERIAL",
    "SECTION",
    "CONSTRAINT",
    "SUPPORT",
    "STLDCASE",
    "LOADCASE",
    "LOADCOMB",
    "USE-STLD",
    "CONLOAD",
    "SELFWEIGHT",
    "PRESSURE",
    "NODALMASS",
    "ELASTICLINK",
    "OFFSET",
    "THICKNESS",
    "STORY-ECCEN",
    "DGN-SECT",
    "DGN-MATL",
    "GROUP",
    "VERSION",
}
UNSUPPORTED_STRUCTURAL_SECTIONS = {
    "ELASTICLINK": "mgt_elastic_link_unsupported",
    "OFFSET": "mgt_beam_offset_unsupported",
    "THICKNESS": "mgt_thickness_unsupported",
    "STORY-ECCEN": "mgt_story_eccentricity_unsupported",
}
_RANGE_BY_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*by\s*(\d+)\s*$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*$", re.IGNORECASE)


def load_midas_mgt(path: Path) -> CanonicalModel:
    sections, line_count = _parse_sections(path)
    nodes_by_id = _parse_nodes(sections.get("NODE", []))
    element_rows = sections.get("ELEMENT", [])
    elements, element_diag = _parse_elements(element_rows, set(nodes_by_id))
    materials = _parse_materials(sections.get("MATERIAL", []))
    section_rows = _parse_section_rows(sections.get("SECTION", []))
    supports = _parse_supports(
        sections.get("CONSTRAINT", []) + sections.get("SUPPORT", []),
        set(nodes_by_id),
    )
    static_load_cases = _parse_static_load_cases(sections.get("STLDCASE", []))
    nodal_loads = _parse_nodal_loads(sections.get("CONLOAD", []), set(nodes_by_id))

    unsupported_features: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not nodes_by_id:
        unsupported_features.append(
            {
                "kind": "mgt_nodes_missing",
                "detail": "No parseable *NODE rows were found.",
            }
        )
    if element_rows and element_diag["skipped_count"]:
        unsupported_features.append(
            {
                "kind": "mgt_element_rows_skipped",
                "detail": "Some *ELEMENT rows could not be mapped without loss.",
                "skipped_count": element_diag["skipped_count"],
                "skip_reason_count": element_diag["skip_reason_count"],
                "unresolved_head": element_diag["unresolved_head"],
            }
        )
    if not elements:
        unsupported_features.append(
            {
                "kind": "mgt_elements_missing",
                "detail": "No parseable *ELEMENT rows were found.",
            }
        )
    for section_name, unsupported_kind in sorted(UNSUPPORTED_STRUCTURAL_SECTIONS.items()):
        row_count = len(sections.get(section_name, []))
        if row_count:
            unsupported_features.append(
                {
                    "kind": unsupported_kind,
                    "detail": (
                        f"*{section_name} rows are preserved in metadata only by "
                        "this thin MGT adapter."
                    ),
                    "row_count": row_count,
                }
            )
    unknown_sections = sorted(key for key in sections if key not in KNOWN_MGT_SECTIONS)
    if unknown_sections:
        warnings.append(
            "MGT sections preserved only as metadata, not canonical analysis inputs: "
            + ",".join(unknown_sections[:12])
            + ("..." if len(unknown_sections) > 12 else "")
        )

    units = _parse_units(sections.get("UNIT", []))
    if not sections.get("UNIT"):
        warnings.append("MGT *UNIT block missing; units defaulted to unknown.")
    elif units.length == "unknown" or units.force == "unknown":
        warnings.append("MGT *UNIT block could not be normalized completely.")
    element_count_by_type = Counter(str(row.get("type", "other")) for row in elements)
    loads = [
        {"kind": "static_load_case", **row}
        for row in static_load_cases
    ] + nodal_loads
    return CanonicalModel(
        schema_version=CANONICAL_MODEL_SCHEMA_VERSION,
        source_path=str(path),
        source_format="midas_mgt",
        input_checksum=checksum_for_path(path),
        units=units,
        coordinate_system=CoordinateSystem(axis_order=("X", "Y", "Z"), up_axis="Z"),
        nodes=[
            {"id": str(node_id), "coordinates": list(coords)}
            for node_id, coords in sorted(nodes_by_id.items())
        ],
        elements=elements,
        materials=materials,
        sections=section_rows,
        loads=loads,
        supports=supports,
        unsupported_features=unsupported_features,
        warnings=warnings,
        metadata={
            "adapter": "structural_analysis.io.midas.load_midas_mgt",
            "adapter_scope": (
                "topology/model-health import only; deterministic solver closure "
                "and MGT load assembly remain outside this adapter"
            ),
            "line_count": line_count,
            "section_counts": {key: len(value) for key, value in sorted(sections.items())},
            "unknown_sections": unknown_sections,
            "unsupported_structural_sections": {
                key: len(sections.get(key, []))
                for key in sorted(UNSUPPORTED_STRUCTURAL_SECTIONS)
                if sections.get(key)
            },
            "element_parse_diagnostics": element_diag,
            "load_summary": {
                "static_load_case_count": len(static_load_cases),
                "nodal_load_count": len(nodal_loads),
            },
            "element_type_counts": dict(sorted(element_count_by_type.items())),
        },
    )


def _clean_line(line: str) -> str:
    raw = str(line).rstrip()
    stripped = raw.lstrip()
    if not stripped or stripped.startswith("#") or stripped.startswith("$"):
        return ""
    if ";" in raw:
        raw = raw.split(";", 1)[0]
    return raw.strip()


def _parse_sections(path: Path) -> tuple[dict[str, list[str]], int]:
    sections: dict[str, list[str]] = defaultdict(list)
    current = "ROOT"
    line_count = 0
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line_count += 1
        line = _clean_line(raw)
        if not line:
            continue
        if line.startswith("*"):
            header = line[1:].strip()
            current = header.split(",", 1)[0].strip().upper() or "ROOT"
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return dict(sections), line_count


def _split_csv_like(value: str) -> list[str]:
    return [token.strip() for token in str(value).split(",") if token.strip()]


def _as_int(token: str) -> int | None:
    try:
        value = float(str(token).strip())
    except ValueError:
        return None
    if abs(value - int(value)) <= 1.0e-9:
        return int(value)
    return None


def _as_float(token: str) -> float | None:
    try:
        return float(str(token).strip())
    except ValueError:
        return None


def _parse_units(rows: list[str]) -> UnitSystem:
    tokens = _split_csv_like(rows[0]) if rows else []
    force = _normalize_force_unit(tokens[0] if len(tokens) >= 1 else "unknown")
    length = _normalize_length_unit(tokens[1] if len(tokens) >= 2 else "unknown")
    return UnitSystem(length=length, force=force)


def _normalize_force_unit(value: str) -> str:
    upper = str(value).strip().upper()
    if upper == "KN":
        return "kN"
    if upper == "MN":
        return "MN"
    if upper in {"N", "LBF", "KIP"}:
        return {"N": "N", "LBF": "lbf", "KIP": "kip"}[upper]
    return "unknown"


def _normalize_length_unit(value: str) -> str:
    upper = str(value).strip().upper()
    if upper in {"M", "MM", "CM", "FT", "IN"}:
        return upper.lower()
    return "unknown"


def _parse_nodes(rows: list[str]) -> dict[int, tuple[float, float, float]]:
    nodes: dict[int, tuple[float, float, float]] = {}
    for row in rows:
        tokens = _split_csv_like(row)
        if len(tokens) < 4:
            continue
        node_id = _as_int(tokens[0])
        coords = [_as_float(token) for token in tokens[1:4]]
        if node_id is None or any(value is None for value in coords):
            continue
        nodes[int(node_id)] = (float(coords[0]), float(coords[1]), float(coords[2]))
    return nodes


def _element_arity_hint(element_type: str) -> int | None:
    key = str(element_type).strip().upper()
    if any(marker in key for marker in ("PLATE", "SHELL", "WALL", "QUAD")):
        return 4
    if "TRI" in key:
        return 3
    if any(marker in key for marker in ("SOLID", "BRICK", "HEX")):
        return 8
    if any(marker in key for marker in ("BEAM", "TRUSS", "FRAME", "COLUMN", "LINK", "COMPTR")):
        return 2
    return None


def _canonical_element_type(element_type: str) -> str:
    key = str(element_type).strip().upper()
    if any(marker in key for marker in ("PLATE", "SHELL", "WALL", "QUAD", "TRI")):
        return "shell"
    if any(marker in key for marker in ("BEAM", "TRUSS", "FRAME", "COLUMN", "LINK", "COMPTR")):
        return "frame"
    if any(marker in key for marker in ("SOLID", "BRICK", "HEX")):
        return "solid"
    return "other"


def _parse_elements(
    rows: list[str],
    node_ids: set[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    skip_reason_count: Counter[str] = Counter()
    unresolved_head: list[dict[str, Any]] = []
    for row in rows:
        tokens = _split_csv_like(row)
        if len(tokens) < 6:
            _record_skip(skip_reason_count, unresolved_head, row, "too_short")
            continue
        element_id = _as_int(tokens[0])
        if element_id is None:
            _record_skip(skip_reason_count, unresolved_head, row, "bad_id")
            continue
        source_type = str(tokens[1]).strip().upper()
        arity = _element_arity_hint(source_type)
        if arity is None:
            _record_skip(
                skip_reason_count,
                unresolved_head,
                row,
                f"unsupported_type:{source_type}",
                element_id=element_id,
                source_type=source_type,
            )
            continue

        connectivity: list[str] = []
        reason = ""
        minimum_nodes = 3 if arity >= 3 else 2
        for index in range(arity):
            token_index = 4 + index
            if token_index >= len(tokens):
                reason = "missing_node_slot"
                break
            node_id = _as_int(tokens[token_index])
            if node_id is None:
                reason = "bad_node_slot"
                break
            if node_id == 0:
                if arity >= 3 and len(connectivity) >= minimum_nodes:
                    break
                reason = "zero_before_min_nodes"
                break
            if node_id not in node_ids:
                reason = "unknown_node_ref"
                break
            node_key = str(node_id)
            if node_key not in connectivity:
                connectivity.append(node_key)
        if len(connectivity) < minimum_nodes:
            _record_skip(
                skip_reason_count,
                unresolved_head,
                row,
                f"{reason or 'insufficient_node_count'}:{source_type}",
                element_id=element_id,
                source_type=source_type,
            )
            continue

        material_id = _as_int(tokens[2])
        section_id = _as_int(tokens[3])
        element: dict[str, Any] = {
            "id": str(element_id),
            "type": _canonical_element_type(source_type),
            "source_type": source_type,
            "nodes": connectivity,
            "material": str(material_id) if material_id is not None else "",
            "section": str(section_id) if section_id is not None else "",
        }
        if element["type"] == "frame":
            angle = _as_float(tokens[6]) if len(tokens) >= 7 else None
            element["local_axis_angle_deg"] = float(angle) if angle is not None else 0.0
        if element["type"] == "shell":
            lcaxis = _as_int(tokens[10]) if len(tokens) >= 11 else None
            element["lcaxis_code"] = int(lcaxis) if lcaxis is not None else 0
        elements.append(element)
    return elements, {
        "row_count": len(rows),
        "parsed_count": len(elements),
        "skipped_count": int(sum(skip_reason_count.values())),
        "skip_reason_count": {key: int(value) for key, value in sorted(skip_reason_count.items())},
        "unresolved_head": unresolved_head,
    }


def _record_skip(
    skip_reason_count: Counter[str],
    unresolved_head: list[dict[str, Any]],
    raw: str,
    reason: str,
    *,
    element_id: int | None = None,
    source_type: str = "",
) -> None:
    skip_reason_count[reason] += 1
    if len(unresolved_head) >= 32:
        return
    row: dict[str, Any] = {"reason": reason, "raw": raw}
    if element_id is not None:
        row["id"] = str(element_id)
    if source_type:
        row["source_type"] = source_type
    unresolved_head.append(row)


def _parse_materials(rows: list[str]) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for row in rows:
        tokens = _split_csv_like(row)
        if not tokens:
            continue
        material_id = _as_int(tokens[0])
        if material_id is None:
            continue
        materials.append(
            {
                "id": str(material_id),
                "type": str(tokens[1]).strip().lower() if len(tokens) >= 2 else "",
                "source_type": str(tokens[1]).strip().upper() if len(tokens) >= 2 else "",
                "raw_tokens": tokens[2:],
            }
        )
    return materials


def _parse_section_rows(rows: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for row in rows:
        tokens = _split_csv_like(row)
        if not tokens:
            continue
        section_id = _as_int(tokens[0])
        if section_id is None:
            continue
        sections.append(
            {
                "id": str(section_id),
                "name": str(tokens[1]).strip() if len(tokens) >= 2 else "",
                "raw_tokens": tokens[2:],
            }
        )
    return sections


def _parse_supports(rows: list[str], node_ids: set[int]) -> list[dict[str, Any]]:
    supports: list[dict[str, Any]] = []
    for row in rows:
        tokens = _split_csv_like(row)
        if not tokens:
            continue
        for node_id in _expand_node_expr(tokens[0]):
            if node_id in node_ids:
                supports.append(
                    {
                        "id": f"SUPPORT:{node_id}",
                        "node": str(node_id),
                        "source": "midas_mgt_constraint",
                        "raw": row,
                    }
                )
    return supports


def _parse_static_load_cases(rows: list[str]) -> list[dict[str, Any]]:
    load_cases: list[dict[str, Any]] = []
    for row in rows:
        tokens = _split_csv_like(row)
        if not tokens:
            continue
        load_cases.append(
            {
                "name": str(tokens[0]).strip(),
                "type": str(tokens[1]).strip() if len(tokens) >= 2 else "",
                "raw": row,
            }
        )
    return load_cases


def _parse_nodal_loads(rows: list[str], node_ids: set[int]) -> list[dict[str, Any]]:
    loads: list[dict[str, Any]] = []
    for row in rows:
        tokens = _split_csv_like(row)
        if len(tokens) < 7:
            continue
        target_nodes = [str(node_id) for node_id in _expand_node_expr(tokens[0]) if node_id in node_ids]
        values = [_as_float(token) for token in tokens[1:7]]
        if not target_nodes or any(value is None for value in values):
            continue
        loads.append(
            {
                "kind": "nodal_load",
                "nodes": target_nodes,
                "fx": float(values[0]),
                "fy": float(values[1]),
                "fz": float(values[2]),
                "mx": float(values[3]),
                "my": float(values[4]),
                "mz": float(values[5]),
                "raw": row,
            }
        )
    return loads


def _expand_node_expr(expr: str) -> list[int]:
    node_ids: list[int] = []
    for token in str(expr).replace(",", " ").split():
        node_ids.extend(_extract_node_span(token))
    return node_ids


def _extract_node_span(token: str) -> list[int]:
    match = _RANGE_BY_RE.match(token)
    if match:
        start, end, step = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if step <= 0:
            return []
        if start <= end:
            return list(range(start, end + 1, step))
        return list(range(start, end - 1, -step))
    match = _RANGE_RE.match(token)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end:
            return list(range(start, end + 1))
        return list(range(start, end - 1, -1))
    value = _as_int(token)
    return [int(value)] if value is not None else []
