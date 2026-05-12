#!/usr/bin/env python3
"""Build release-safe proxy structural graphs from private-corpus IFC files."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any


DEFAULT_PRIVATE_MANIFEST = Path("private_corpus/real_drawings/private_real_drawing_corpus_manifest.json")
DEFAULT_REDACTED_MANIFEST = Path("tmp/real_drawing_private_corpus/redacted_manifest.json")
DEFAULT_OUT_DIR = Path("tmp/real_drawing_private_corpus/ifc_adapter")
ADAPTER_SCHEMA_VERSION = "real-drawing-ifc-structural-proxy-graph.v1"
ADAPTER_MODE = "entity_proxy_graph"
SOLVER_GRAPH_SCHEMA_VERSION = "real-drawing-ifc-solver-graph-draft.v1"
AGGREGATE_RELATIONSHIP = "aggregates_decomposition"
CONTAINED_RELATIONSHIP = "contained_in_spatial_structure"

STRUCTURAL_ENTITY_TYPES = {
    "IFCBEAM",
    "IFCCOLUMN",
    "IFCSLAB",
    "IFCWALL",
    "IFCWALLSTANDARDCASE",
    "IFCMEMBER",
    "IFCPLATE",
    "IFCFOOTING",
    "IFCPILE",
}
MATERIAL_SECTION_SOURCE_TYPES = {
    "IFCMATERIALLAYER",
    "IFCMATERIALLAYERSET",
    "IFCMATERIALLAYERSETUSAGE",
    "IFCMATERIALPROFILE",
    "IFCMATERIALPROFILESET",
    "IFCMATERIALPROFILESETUSAGE",
    "IFCMATERIALCONSTITUENT",
    "IFCMATERIALCONSTITUENTSET",
}
LOAD_GROUP_ENTITY_TYPES = {"IFCLOADGROUP", "IFCSTRUCTURALLOADGROUP"}
LOAD_RELATIONSHIP_ENTITY_TYPES = {"IFCRELCONNECTSSTRUCTURALACTIVITY", "IFCRELASSIGNSTOGROUP"}
SPATIAL_ENTITY_TYPES = {"IFCBUILDINGSTOREY"}
COUNTED_ENTITY_TYPES = STRUCTURAL_ENTITY_TYPES | SPATIAL_ENTITY_TYPES
ENTITY_RE = re.compile(r"^\s*#(?P<id>\d+)\s*=\s*(?P<type>[A-Z0-9_]+)\s*\((?P<args>.*)\)\s*;\s*$", re.I | re.S)
REF_RE = re.compile(r"#(\d+)")
NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_report_stem(file_id: str, file_name: str) -> str:
    stem = str(file_id or "").strip() or Path(file_name).stem
    chars = [ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in stem]
    return "".join(chars).strip("._") or "ifc_model"


def _manifest_ifc_rows(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("project_id", "") or "")
        for file_row in project.get("files", []):
            if not isinstance(file_row, dict):
                continue
            if str(file_row.get("file_type", "") or "").lower() != ".ifc":
                continue
            if file_row.get("model_optimization_candidate") is not True:
                continue
            file_id = str(file_row.get("file_id", "") or "")
            rows[(project_id, file_id)] = {"project": project, "file": file_row}
    return rows


def _records(path: Path) -> list[str]:
    records: list[str] = []
    current: list[str] = []
    in_data = False
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            stripped = line.strip()
            upper = stripped.upper()
            if upper == "DATA;":
                in_data = True
                continue
            if upper == "ENDSEC;" and in_data:
                break
            if not in_data:
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


def _split_step_args(text: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            buf.append(ch)
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                buf.append(text[i + 1])
                i += 2
                continue
            in_string = not in_string
        elif not in_string and ch == "(":
            depth += 1
            buf.append(ch)
        elif not in_string and ch == ")":
            depth = max(depth - 1, 0)
            buf.append(ch)
        elif not in_string and ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    args.append("".join(buf).strip())
    return args


def _record_args(record: str) -> tuple[str, str, list[str]] | None:
    match = ENTITY_RE.match(record)
    if not match:
        return None
    entity_id = f"#{match.group('id')}"
    entity_type = match.group("type").upper()
    return entity_id, entity_type, _split_step_args(match.group("args"))


def _entity_label(entity_type: str, _args: list[str], entity_id: str) -> str:
    return f"{entity_type}:{entity_id}"


def _first_ref(text: str) -> str | None:
    refs = REF_RE.findall(text or "")
    return f"#{refs[0]}" if refs else None


def _refs(text: str) -> list[str]:
    return [f"#{ref}" for ref in REF_RE.findall(text or "")]


def _step_label(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned in {"", "$", "*"}:
        return ""
    if cleaned.startswith("'") and cleaned.endswith("'") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].replace("''", "'")
    if cleaned.startswith(".") and cleaned.endswith(".") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1]
    return cleaned


def _is_section_source_type(entity_type: str) -> bool:
    return entity_type in MATERIAL_SECTION_SOURCE_TYPES or entity_type.endswith("PROFILEDEF")


def _is_load_group_type(entity_type: str) -> bool:
    return entity_type in LOAD_GROUP_ENTITY_TYPES or entity_type.endswith("LOADGROUP")


def _is_structural_load_type(entity_type: str) -> bool:
    return entity_type.startswith("IFCSTRUCTURALLOAD") and not _is_load_group_type(entity_type)


def _is_structural_action_type(entity_type: str) -> bool:
    return entity_type.startswith("IFCSTRUCTURAL") and "ACTION" in entity_type


def _is_load_related_type(entity_type: str) -> bool:
    return (
        _is_load_group_type(entity_type)
        or _is_structural_load_type(entity_type)
        or _is_structural_action_type(entity_type)
    )


def _is_load_case_group(args: list[str]) -> bool:
    return any("LOAD_CASE" in str(arg).upper() or "LOADCASE" in str(arg).upper() for arg in args)


def _ref_closure(
    root: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
    memo: dict[str, set[str]],
    *,
    max_nodes: int = 800,
) -> set[str]:
    if not root:
        return set()
    if root in memo:
        return memo[root]
    seen: set[str] = set()
    stack = [root]
    while stack and len(seen) < max_nodes:
        entity_id = stack.pop()
        if entity_id in seen:
            continue
        seen.add(entity_id)
        row = record_by_id.get(entity_id)
        if row is None:
            continue
        _entity_type, args = row
        for arg in args:
            for ref in _refs(arg):
                if ref not in seen:
                    stack.append(ref)
    memo[root] = seen
    return seen


def _relationship_group_id(entity_type: str, entity_id: str) -> str:
    return f"relationship:{entity_type}:{entity_id}"


def _append_unique_edge(
    edges: list[dict[str, str]],
    seen_edges: set[tuple[str, str, str]],
    *,
    source: str,
    target: str,
    relationship: str,
) -> bool:
    if not source or not target or source == target:
        return False
    key = (source, target, relationship)
    if key in seen_edges:
        return False
    seen_edges.add(key)
    edges.append({"source": source, "target": target, "relationship": relationship})
    return True


def _number_tuple(text: str, *, dimensions: int = 3) -> list[float] | None:
    values = [float(value) for value in NUMBER_RE.findall(text or "")]
    if not values:
        return None
    while len(values) < dimensions:
        values.append(0.0)
    return values[:dimensions]


def _first_number(text: str) -> float | None:
    match = NUMBER_RE.search(text or "")
    return float(match.group(0)) if match else None


def _vector_add(left: list[float], right: list[float]) -> list[float]:
    return [left[0] + right[0], left[1] + right[1], left[2] + right[2]]


def _dot(left: list[float], right: list[float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _normalize(vector: list[float], fallback: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-9:
        return fallback[:]
    return [value / length for value in vector]


def _basis_vector(basis: list[list[float]], vector: list[float]) -> list[float]:
    return [
        basis[0][0] * vector[0] + basis[1][0] * vector[1] + basis[2][0] * vector[2],
        basis[0][1] * vector[0] + basis[1][1] * vector[1] + basis[2][1] * vector[2],
        basis[0][2] * vector[0] + basis[1][2] * vector[1] + basis[2][2] * vector[2],
    ]


def _combine_transform(
    parent: tuple[list[float], list[list[float]]],
    local: tuple[list[float], list[list[float]]],
) -> tuple[list[float], list[list[float]]]:
    parent_origin, parent_basis = parent
    local_origin, local_basis = local
    origin = _vector_add(parent_origin, _basis_vector(parent_basis, local_origin))
    basis = [_basis_vector(parent_basis, axis) for axis in local_basis]
    return origin, basis


def _identity_transform() -> tuple[list[float], list[list[float]]]:
    return [0.0, 0.0, 0.0], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


BODY_MEMBER_EXTENT_SOURCES = {
    "ifc_body_advanced_brep_bounds_world",
    "ifc_body_brep_bounds_world",
    "ifc_body_extrusion_depth_world",
    "ifc_body_boolean_operand_extent_world",
    "ifc_mapped_body_advanced_brep_bounds_world",
    "ifc_mapped_body_brep_bounds_world",
    "ifc_mapped_body_extrusion_depth_world",
    "ifc_mapped_body_boolean_operand_extent_world",
}


def _direction_from_ref(
    direction_id: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
    fallback: list[float],
) -> list[float]:
    row = record_by_id.get(direction_id or "")
    if row is None or row[0] != "IFCDIRECTION" or not row[1]:
        return fallback[:]
    return _normalize(_number_tuple(row[1][0], dimensions=3) or fallback, fallback)


def _cartesian_transformation_operator_transform(
    operator_id: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
) -> tuple[list[float], list[list[float]]] | None:
    row = record_by_id.get(operator_id or "")
    if row is None or not row[0].startswith("IFCCARTESIANTRANSFORMATIONOPERATOR"):
        return None
    entity_type, args = row
    if len(args) <= 2:
        return None
    scale1 = _first_number(args[3]) if len(args) > 3 else None
    scale1 = 1.0 if scale1 is None else scale1
    scale2 = scale1
    scale3 = scale1
    if "NONUNIFORM" in entity_type:
        scale2 = _first_number(args[5]) if len(args) > 5 else None
        scale3 = _first_number(args[6]) if len(args) > 6 else None
        scale2 = scale1 if scale2 is None else scale2
        scale3 = scale1 if scale3 is None else scale3

    origin = _cartesian_point(_first_ref(args[2]), record_by_id) or [0.0, 0.0, 0.0]
    x_axis = _direction_from_ref(_first_ref(args[0]), record_by_id, [1.0, 0.0, 0.0])
    y_axis = _direction_from_ref(_first_ref(args[1]), record_by_id, [0.0, 1.0, 0.0])
    if "2D" in entity_type:
        z_axis = [0.0, 0.0, 1.0]
    else:
        z_axis = _direction_from_ref(_first_ref(args[4]) if len(args) > 4 else None, record_by_id, _cross(x_axis, y_axis))
    z_axis = _normalize(z_axis, [0.0, 0.0, 1.0])
    x_axis = _normalize([x_axis[index] - z_axis[index] * _dot(x_axis, z_axis) for index in range(3)], [1.0, 0.0, 0.0])
    y_axis = _normalize(_cross(z_axis, x_axis), [0.0, 1.0, 0.0])
    x_axis = _normalize(_cross(y_axis, z_axis), [1.0, 0.0, 0.0])
    return origin, [
        [value * scale1 for value in x_axis],
        [value * scale2 for value in y_axis],
        [value * scale3 for value in z_axis],
    ]


def _axis_placement_transform(
    placement_id: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
) -> tuple[list[float], list[list[float]]] | None:
    if not placement_id:
        return _identity_transform()
    row = record_by_id.get(placement_id)
    if row is None:
        return None
    entity_type, args = row
    if entity_type not in {"IFCAXIS2PLACEMENT3D", "IFCAXIS2PLACEMENT2D"} or not args:
        return None
    location_id = _first_ref(args[0])
    location_row = record_by_id.get(location_id or "")
    if location_row is None or location_row[0] != "IFCCARTESIANPOINT":
        return None
    origin = _number_tuple(location_row[1][0] if location_row[1] else "", dimensions=3)
    if origin is None:
        return None

    if entity_type == "IFCAXIS2PLACEMENT2D":
        ref_dir_id = _first_ref(args[1]) if len(args) > 1 else None
        ref_dir_row = record_by_id.get(ref_dir_id or "")
        x_axis = _number_tuple(ref_dir_row[1][0], dimensions=3) if ref_dir_row and ref_dir_row[0] == "IFCDIRECTION" else None
        x_axis = _normalize(x_axis or [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        z_axis = [0.0, 0.0, 1.0]
        y_axis = _normalize(_cross(z_axis, x_axis), [0.0, 1.0, 0.0])
        x_axis = _normalize(_cross(y_axis, z_axis), [1.0, 0.0, 0.0])
        return origin, [x_axis, y_axis, z_axis]

    axis_id = _first_ref(args[1]) if len(args) > 1 else None
    ref_direction_id = _first_ref(args[2]) if len(args) > 2 else None
    axis_row = record_by_id.get(axis_id or "")
    ref_direction_row = record_by_id.get(ref_direction_id or "")
    z_axis = (
        _number_tuple(axis_row[1][0], dimensions=3)
        if axis_row and axis_row[0] == "IFCDIRECTION" and axis_row[1]
        else None
    )
    x_axis = (
        _number_tuple(ref_direction_row[1][0], dimensions=3)
        if ref_direction_row and ref_direction_row[0] == "IFCDIRECTION" and ref_direction_row[1]
        else None
    )
    z_axis = _normalize(z_axis or [0.0, 0.0, 1.0], [0.0, 0.0, 1.0])
    x_axis = _normalize(x_axis or [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    x_axis = _normalize([x_axis[index] - z_axis[index] * _dot(x_axis, z_axis) for index in range(3)], [1.0, 0.0, 0.0])
    y_axis = _normalize(_cross(z_axis, x_axis), [0.0, 1.0, 0.0])
    x_axis = _normalize(_cross(y_axis, z_axis), [1.0, 0.0, 0.0])
    return origin, [x_axis, y_axis, z_axis]


def _local_placement_transform(
    placement_id: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
    memo: dict[str, tuple[list[float], list[list[float]]] | None],
    visiting: set[str],
) -> tuple[list[float], list[list[float]]] | None:
    if not placement_id:
        return _identity_transform()
    if placement_id in memo:
        return memo[placement_id]
    if placement_id in visiting:
        memo[placement_id] = None
        return None
    row = record_by_id.get(placement_id)
    if row is None or row[0] != "IFCLOCALPLACEMENT":
        memo[placement_id] = None
        return None
    visiting.add(placement_id)
    args = row[1]
    parent_id = _first_ref(args[0]) if args else None
    relative_id = _first_ref(args[1]) if len(args) > 1 else None
    parent_transform = _local_placement_transform(parent_id, record_by_id, memo, visiting)
    relative_transform = _axis_placement_transform(relative_id, record_by_id)
    visiting.discard(placement_id)
    if parent_transform is None or relative_transform is None:
        memo[placement_id] = None
        return None
    transform = _combine_transform(parent_transform, relative_transform)
    memo[placement_id] = transform
    return transform


def _round_point(point: list[float]) -> list[float]:
    return [round(value, 6) for value in point]


def _transform_point(
    transform: tuple[list[float], list[list[float]]],
    point: list[float],
) -> list[float]:
    origin, basis = transform
    return _round_point(_vector_add(origin, _basis_vector(basis, point)))


def _placement_bounds(points: list[list[float]]) -> dict[str, list[float]]:
    if not points:
        return {"min": [], "max": []}
    return {
        "min": _round_point([min(point[index] for point in points) for index in range(3)]),
        "max": _round_point([max(point[index] for point in points) for index in range(3)]),
    }


def _node_xyz(node: dict[str, Any]) -> list[float] | None:
    try:
        return [float(node["x"]), float(node["y"]), float(node["z"])]
    except Exception:
        return None


def _axis_marker_direction(ifc_entity_type: str) -> list[float]:
    entity_type = str(ifc_entity_type or "").upper()
    if entity_type in {"IFCCOLUMN", "IFCPILE"}:
        return [0.0, 0.0, 1.0]
    if entity_type in {"IFCWALL", "IFCWALLSTANDARDCASE"}:
        return [0.0, 1.0, 0.0]
    return [1.0, 0.0, 0.0]


def _axis_marker_length(points: list[list[float]]) -> float:
    if len(points) < 2:
        return 1.0
    bounds = _placement_bounds(points)
    min_point = bounds.get("min") or [0.0, 0.0, 0.0]
    max_point = bounds.get("max") or [0.0, 0.0, 0.0]
    diagonal = math.sqrt(sum((float(max_point[index]) - float(min_point[index])) ** 2 for index in range(3)))
    if diagonal <= 1e-9:
        return 1.0
    return round(max(0.5, min(6.0, diagonal * 0.015)), 6)


def _cartesian_point(
    point_id: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
) -> list[float] | None:
    row = record_by_id.get(point_id or "")
    if row is None or row[0] != "IFCCARTESIANPOINT" or not row[1]:
        return None
    return _number_tuple(row[1][0], dimensions=3)


def _axis_polyline_world_points(
    item_id: str,
    record_by_id: dict[str, tuple[str, list[str]]],
    product_transform: tuple[list[float], list[list[float]]],
) -> list[list[float]]:
    item = record_by_id.get(item_id)
    if item is None or item[0] != "IFCPOLYLINE" or not item[1]:
        return []
    points = [
        _cartesian_point(point_id, record_by_id)
        for point_id in _refs(item[1][0])
    ]
    world_points = [_transform_point(product_transform, point) for point in points if point is not None]
    return world_points if len(world_points) >= 2 else []


def _extruded_body_world_points(
    item_id: str,
    record_by_id: dict[str, tuple[str, list[str]]],
    product_transform: tuple[list[float], list[list[float]]],
) -> list[list[float]]:
    item = record_by_id.get(item_id)
    if item is None or item[0] != "IFCEXTRUDEDAREASOLID" or len(item[1]) <= 3:
        return []
    position_transform = _axis_placement_transform(_first_ref(item[1][1]), record_by_id)
    combined_transform = _combine_transform(product_transform, position_transform or _identity_transform())
    direction_row = record_by_id.get(_first_ref(item[1][2]) or "")
    direction = (
        _number_tuple(direction_row[1][0], dimensions=3)
        if direction_row is not None and direction_row[0] == "IFCDIRECTION" and direction_row[1]
        else [0.0, 0.0, 1.0]
    )
    depth = _first_number(item[1][3])
    if depth is None or abs(depth) <= 1e-9:
        return []
    local_direction = _normalize(direction, [0.0, 0.0, 1.0])
    end = _transform_point(combined_transform, [local_direction[index] * depth for index in range(3)])
    return [_transform_point(combined_transform, [0.0, 0.0, 0.0]), end]


def _cartesian_points_reachable_from_item(
    item_id: str,
    record_by_id: dict[str, tuple[str, list[str]]],
    *,
    visited_items: set[str] | None = None,
) -> list[list[float]]:
    visited = visited_items if visited_items is not None else set()
    if item_id in visited:
        return []
    visited.add(item_id)
    row = record_by_id.get(item_id)
    if row is None:
        return []
    entity_type, args = row
    if entity_type == "IFCCARTESIANPOINT":
        point = _cartesian_point(item_id, record_by_id)
        return [point] if point is not None else []
    points: list[list[float]] = []
    for ref_id in _refs(" ".join(args)):
        points.extend(
            _cartesian_points_reachable_from_item(
                ref_id,
                record_by_id,
                visited_items=visited,
            )
        )
    return points


def _extent_points_from_world_points(points: list[list[float]]) -> list[list[float]]:
    if len(points) < 2:
        return []
    mins = [min(point[index] for point in points) for index in range(3)]
    maxs = [max(point[index] for point in points) for index in range(3)]
    spans = [maxs[index] - mins[index] for index in range(3)]
    max_span = max(spans)
    if max_span <= 1e-9:
        return []
    axis_index = spans.index(max_span)
    center = [(mins[index] + maxs[index]) / 2.0 for index in range(3)]
    start = center[:]
    end = center[:]
    start[axis_index] = mins[axis_index]
    end[axis_index] = maxs[axis_index]
    return [_round_point(start), _round_point(end)]


def _brep_body_world_points(
    item_id: str,
    record_by_id: dict[str, tuple[str, list[str]]],
    product_transform: tuple[list[float], list[list[float]]],
) -> list[list[float]]:
    local_points = _cartesian_points_reachable_from_item(item_id, record_by_id)
    world_points = [_transform_point(product_transform, point) for point in local_points]
    return _extent_points_from_world_points(world_points)


def _body_item_world_extent(
    item_id: str,
    record_by_id: dict[str, tuple[str, list[str]]],
    product_transform: tuple[list[float], list[list[float]]],
    *,
    visited_items: set[str] | None = None,
) -> tuple[str, list[list[float]]]:
    visited = visited_items if visited_items is not None else set()
    if item_id in visited:
        return "", []
    visited.add(item_id)
    item = record_by_id.get(item_id)
    if item is None:
        return "", []
    entity_type, args = item
    if entity_type == "IFCEXTRUDEDAREASOLID":
        points = _extruded_body_world_points(item_id, record_by_id, product_transform)
        return ("ifc_body_extrusion_depth_world", points) if points else ("", [])
    if entity_type == "IFCFACETEDBREP":
        points = _brep_body_world_points(item_id, record_by_id, product_transform)
        return ("ifc_body_brep_bounds_world", points) if points else ("", [])
    if entity_type == "IFCADVANCEDBREP":
        points = _brep_body_world_points(item_id, record_by_id, product_transform)
        return ("ifc_body_advanced_brep_bounds_world", points) if points else ("", [])
    if entity_type == "IFCMAPPEDITEM" and len(args) > 1:
        source, points = _mapped_item_world_extent(
            item_id,
            record_by_id,
            product_transform,
            visited_items=visited,
        )
        return source, points
    if entity_type in {"IFCBOOLEANCLIPPINGRESULT", "IFCBOOLEANRESULT"}:
        for operand_id in _refs(" ".join(args[1:])):
            source, points = _body_item_world_extent(
                operand_id,
                record_by_id,
                product_transform,
                visited_items=visited,
            )
            if points:
                return "ifc_body_boolean_operand_extent_world", points
    return "", []


def _mapped_item_world_extent(
    item_id: str,
    record_by_id: dict[str, tuple[str, list[str]]],
    product_transform: tuple[list[float], list[list[float]]],
    *,
    visited_items: set[str] | None = None,
) -> tuple[str, list[list[float]]]:
    item = record_by_id.get(item_id)
    if item is None or item[0] != "IFCMAPPEDITEM" or len(item[1]) <= 1:
        return "", []
    representation_map = record_by_id.get(_first_ref(item[1][0]) or "")
    if representation_map is None or representation_map[0] != "IFCREPRESENTATIONMAP" or len(representation_map[1]) <= 1:
        return "", []
    mapped_representation = record_by_id.get(_first_ref(representation_map[1][1]) or "")
    if mapped_representation is None or mapped_representation[0] != "IFCSHAPEREPRESENTATION" or len(mapped_representation[1]) <= 3:
        return "", []
    origin_transform = _axis_placement_transform(_first_ref(representation_map[1][0]), record_by_id) or _identity_transform()
    target_transform = _cartesian_transformation_operator_transform(_first_ref(item[1][1]), record_by_id) or _identity_transform()
    mapped_transform = _combine_transform(_combine_transform(product_transform, target_transform), origin_transform)
    for mapped_item_id in _refs(mapped_representation[1][3]):
        source, points = _body_item_world_extent(
            mapped_item_id,
            record_by_id,
            mapped_transform,
            visited_items=visited_items,
        )
        if points:
            mapped_source = source.replace("ifc_body_", "ifc_mapped_body_", 1)
            return mapped_source, points
    return "", []


def _member_extent_from_representations(
    *,
    product_shape_id: str | None,
    record_by_id: dict[str, tuple[str, list[str]]],
    product_transform: tuple[list[float], list[list[float]]],
) -> tuple[str, list[list[float]]]:
    product_shape = record_by_id.get(product_shape_id or "")
    if product_shape is None or product_shape[0] != "IFCPRODUCTDEFINITIONSHAPE" or len(product_shape[1]) <= 2:
        return "", []

    best_body_points: list[list[float]] = []
    best_body_source = ""
    for representation_id in _refs(product_shape[1][2]):
        representation = record_by_id.get(representation_id)
        if representation is None or representation[0] != "IFCSHAPEREPRESENTATION" or len(representation[1]) <= 3:
            continue
        representation_identifier = _step_label(representation[1][1]).upper()
        representation_type = _step_label(representation[1][2]).upper()
        item_ids = _refs(representation[1][3])
        if representation_identifier == "AXIS" or "CURVE" in representation_type:
            for item_id in item_ids:
                axis_points = _axis_polyline_world_points(item_id, record_by_id, product_transform)
                if axis_points:
                    return "ifc_axis_polyline_world", axis_points
        if representation_identifier == "BODY" and not best_body_points:
            for item_id in item_ids:
                body_source, body_points = _body_item_world_extent(item_id, record_by_id, product_transform)
                if body_points:
                    best_body_source = body_source
                    best_body_points = body_points
                    break
    if best_body_points:
        return best_body_source or "ifc_body_extrusion_depth_world", best_body_points
    return "", []


def _family_for_ifc_entity_type(ifc_entity_type: str) -> str:
    entity_type = str(ifc_entity_type or "").upper()
    if entity_type in {"IFCCOLUMN", "IFCPILE"}:
        return "vertical_member"
    if entity_type in {"IFCBEAM", "IFCMEMBER"}:
        return "linear_member"
    if entity_type in {"IFCSLAB", "IFCPLATE", "IFCFOOTING"}:
        return "surface_member"
    if entity_type in {"IFCWALL", "IFCWALLSTANDARDCASE"}:
        return "wall_member"
    return "structural_member"


def _solver_artifact_receipt(
    *,
    graph: dict[str, Any],
    model_node_count: int,
    element_count: int,
    source_structural_node_count: int,
    member_extent_element_count: int,
    axis_polyline_element_count: int,
    body_extrusion_element_count: int,
    placement_marker_fallback_count: int,
    placement_marker_fallback_reason_counts: Counter[str],
    geometry_scope: str,
    json_path: Path,
    npz_path: Path,
) -> dict[str, Any]:
    receipts = graph.get("evidence_receipts") if isinstance(graph.get("evidence_receipts"), dict) else {}
    basis_receipt_ids = [
        "ifc_local_placement_coordinate_extraction_receipt",
        "ifc_representation_shape_axis_receipt",
        "ifc_material_section_binding_receipt",
    ]
    attached_basis = [
        receipt_id
        for receipt_id in basis_receipt_ids
        if bool(receipts.get(receipt_id, {}).get("contract_pass", False))
    ]
    load_receipt = receipts.get("ifc_load_case_extraction_or_engineer_signed_zero_load_receipt", {})
    load_pass = bool(load_receipt.get("contract_pass", False))
    contract_pass = (
        len(attached_basis) == len(basis_receipt_ids)
        and model_node_count > 0
        and element_count > 0
    )
    open_dependencies: list[str] = []
    if not load_pass:
        open_dependencies.append("ifc_load_case_extraction_or_engineer_signed_zero_load_receipt")
    open_dependencies.append("viewer_sidecar_rebuild_receipt")
    return {
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS_IFC_SOLVER_GRAPH_JSON_NPZ_DRAFT_EMITTED"
            if contract_pass
            else "ERR_IFC_SOLVER_GRAPH_JSON_NPZ_DRAFT_INCOMPLETE"
        ),
        "artifact_scope": "release_safe_solver_graph_draft_from_ifc_placement_shape_material_receipts",
        "geometry_scope": geometry_scope,
        "solver_exact": False,
        "commercial_claim_blocked": True,
        "json_path": str(json_path),
        "npz_path": str(npz_path),
        "model_node_count": model_node_count,
        "element_count": element_count,
        "member_extent_element_count": member_extent_element_count,
        "axis_polyline_element_count": axis_polyline_element_count,
        "body_extrusion_element_count": body_extrusion_element_count,
        "placement_marker_fallback_count": placement_marker_fallback_count,
        "placement_marker_fallback_reason_counts": dict(sorted(placement_marker_fallback_reason_counts.items())),
        "placement_marker_fallback_source_shape_missing_count": int(
            placement_marker_fallback_reason_counts.get("source_ifc_product_shape_missing", 0)
        ),
        "placement_marker_fallback_unresolved_count": int(
            placement_marker_fallback_count
            - placement_marker_fallback_reason_counts.get("source_ifc_product_shape_missing", 0)
        ),
        "member_extent_coverage_ratio": (
            round(member_extent_element_count / element_count, 4)
            if element_count > 0
            else 0.0
        ),
        "source_structural_node_count": source_structural_node_count,
        "structural_entity_count": int(graph.get("metrics", {}).get("structural_entity_count", 0) or 0),
        "basis_receipts_attached": attached_basis,
        "open_dependencies": open_dependencies,
        "zero_load_substitution_requires_engineer_signature": bool(
            load_receipt.get("zero_load_substitution_requires_engineer_signature", False)
        ),
    }


def _write_solver_graph_artifacts(
    *,
    graph: dict[str, Any],
    json_path: Path,
    npz_path: Path,
) -> dict[str, Any]:
    import numpy as np

    source_nodes = [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        and node.get("proxy_node_kind") == "structural_element"
        and _node_xyz(node) is not None
    ]
    points = [_node_xyz(node) for node in source_nodes]
    clean_points = [point for point in points if point is not None]
    marker_length = _axis_marker_length(clean_points)
    model_nodes: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    node_index_by_id: dict[str, int] = {}
    element_node_indices: list[list[int]] = []
    member_extent_element_count = 0
    axis_polyline_element_count = 0
    body_extrusion_element_count = 0
    placement_marker_fallback_count = 0
    placement_marker_fallback_reason_counts: Counter[str] = Counter()

    for source_node in source_nodes:
        origin = _node_xyz(source_node)
        if origin is None:
            continue
        source_ifc_id = str(source_node.get("id") or "")
        entity_type = str(source_node.get("ifc_entity_type") or "")
        base_id = source_ifc_id.lstrip("#") or str(len(elements) + 1)
        extent_points = [
            point
            for point in (source_node.get("member_axis_world_points") or [])
            if isinstance(point, list) and len(point) >= 3
        ]
        extent_source = str(source_node.get("member_extent_source") or "")
        if len(extent_points) >= 2:
            segment_points = [_round_point([float(point[0]), float(point[1]), float(point[2])]) for point in extent_points]
            geometry_scope = extent_source
            member_extent_element_count += 1
            if extent_source == "ifc_axis_polyline_world":
                axis_polyline_element_count += 1
            elif extent_source in BODY_MEMBER_EXTENT_SOURCES:
                body_extrusion_element_count += 1
        else:
            direction = _axis_marker_direction(entity_type)
            end = _round_point(
                [
                    origin[index] + direction[index] * marker_length
                    for index in range(3)
                ]
            )
            segment_points = [origin, end]
            geometry_scope = "placement_origin_axis_marker_not_member_extents"
            placement_marker_fallback_count += 1
            fallback_reason = str(
                source_node.get("member_extent_missing_reason")
                or "member_extent_geometry_unresolved"
            )
            placement_marker_fallback_reason_counts[fallback_reason] += 1

        node_ids: list[str] = []
        node_indices: list[int] = []
        for point_index, point in enumerate(segment_points, start=1):
            node_id = f"ifc:{base_id}:n{point_index}"
            node = {
                "id": node_id,
                "x": point[0],
                "y": point[1],
                "z": point[2],
                "source_ifc_id": source_ifc_id,
            }
            node_index_by_id[node_id] = len(model_nodes)
            node_indices.append(len(model_nodes))
            node_ids.append(node_id)
            model_nodes.append(node)
        element = {
            "id": f"ifc:{base_id}",
            "node_ids": node_ids,
            "ifc_entity_id": source_ifc_id,
            "ifc_entity_type": entity_type,
            "family": _family_for_ifc_entity_type(entity_type),
            "geometry_scope": geometry_scope,
        }
        if geometry_scope == "placement_origin_axis_marker_not_member_extents":
            element["geometry_fallback_reason"] = fallback_reason
        if source_node.get("material_binding_source"):
            element["material_binding_source"] = source_node.get("material_binding_source")
        if source_node.get("section_source"):
            element["section_source"] = source_node.get("section_source")
        elements.append(element)
        element_node_indices.append([node_indices[0], node_indices[-1]])

    model_geometry_scope = (
        "ifc_axis_or_body_member_extents"
        if elements and placement_marker_fallback_count == 0
        else "ifc_axis_or_body_member_extents_with_placement_marker_fallback"
        if member_extent_element_count > 0
        else "placement_origin_axis_marker_not_member_extents"
    )

    receipt = _solver_artifact_receipt(
        graph=graph,
        model_node_count=len(model_nodes),
        element_count=len(elements),
        source_structural_node_count=len(source_nodes),
        member_extent_element_count=member_extent_element_count,
        axis_polyline_element_count=axis_polyline_element_count,
        body_extrusion_element_count=body_extrusion_element_count,
        placement_marker_fallback_count=placement_marker_fallback_count,
        placement_marker_fallback_reason_counts=placement_marker_fallback_reason_counts,
        geometry_scope=model_geometry_scope,
        json_path=json_path,
        npz_path=npz_path,
    )
    payload = {
        "schema_version": SOLVER_GRAPH_SCHEMA_VERSION,
        "generated_at": graph.get("generated_at"),
        "contract_pass": bool(receipt.get("contract_pass", False)),
        "reason_code": receipt.get("reason_code"),
        "source": graph.get("source", {}),
        "adapter_mode": ADAPTER_MODE,
        "solver_exact": False,
        "commercial_claim_blocked": True,
        "model": {
            "units": {"length": "ifc_model_units_unscaled"},
            "geometry_scope": model_geometry_scope,
            "nodes": model_nodes,
            "elements": elements,
        },
        "metrics": {
            "model_node_count": len(model_nodes),
            "element_count": len(elements),
            "source_structural_node_count": len(source_nodes),
            "member_extent_element_count": member_extent_element_count,
            "axis_polyline_element_count": axis_polyline_element_count,
            "body_extrusion_element_count": body_extrusion_element_count,
            "placement_marker_fallback_count": placement_marker_fallback_count,
            "placement_marker_fallback_reason_counts": dict(sorted(placement_marker_fallback_reason_counts.items())),
            "placement_marker_fallback_source_shape_missing_count": int(
                placement_marker_fallback_reason_counts.get("source_ifc_product_shape_missing", 0)
            ),
            "placement_marker_fallback_unresolved_count": int(
                placement_marker_fallback_count
                - placement_marker_fallback_reason_counts.get("source_ifc_product_shape_missing", 0)
            ),
            "member_extent_coverage_ratio": (
                round(member_extent_element_count / len(elements), 4)
                if elements
                else 0.0
            ),
            "axis_marker_length": marker_length,
        },
        "evidence_receipts": {"solver_graph_json_npz_receipt": receipt},
        "limitations": [
            "IFC Axis polylines, Body extrusion depths, mapped bodies, boolean first operands, or BREP point-bound extents are preferred when available; placement-origin axis markers are only fallback geometry.",
            "Member extents, meshing, boundary conditions, and loads are not asserted as solver-exact.",
        ],
    }
    _write_json(json_path, payload)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    node_ids = [str(node["id"]) for node in model_nodes]
    element_ids = [str(element["id"]) for element in elements]
    np.savez_compressed(
        npz_path,
        node_ids=np.asarray(node_ids, dtype=str),
        node_xyz=np.asarray(
            [[float(node["x"]), float(node["y"]), float(node["z"])] for node in model_nodes],
            dtype=np.float64,
        ).reshape((-1, 3)),
        element_ids=np.asarray(element_ids, dtype=str),
        element_node_indices=np.asarray(element_node_indices, dtype=np.int64).reshape((-1, 2)),
        element_family=np.asarray([str(element["family"]) for element in elements], dtype=str),
        source_ifc_ids=np.asarray([str(element["ifc_entity_id"]) for element in elements], dtype=str),
    )
    return receipt


def _placement_receipt(
    *,
    structural_entity_count: int,
    structural_placement_count: int,
    node_placement_count: int,
    points: list[list[float]],
) -> dict[str, Any]:
    coverage = round(structural_placement_count / structural_entity_count, 4) if structural_entity_count > 0 else 0.0
    contract_pass = structural_entity_count > 0 and structural_placement_count > 0
    return {
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS_IFC_LOCAL_PLACEMENT_COORDINATES_EXTRACTED"
            if contract_pass
            else "ERR_IFC_LOCAL_PLACEMENT_COORDINATES_MISSING"
        ),
        "coordinate_scope": "release_safe_product_origin",
        "coordinate_units": "ifc_model_units_unscaled",
        "placement_coordinate_node_count": node_placement_count,
        "placement_coordinate_structural_count": structural_placement_count,
        "structural_entity_count": structural_entity_count,
        "placement_coverage_ratio": coverage,
        "placement_bounds": _placement_bounds(points),
    }


def _representation_receipt(
    *,
    structural_entity_count: int,
    shape_product_count: int,
    body_representation_count: int,
    axis_representation_count: int,
    representation_counts: Counter[str],
    representation_type_counts: Counter[str],
    geometry_item_counts: Counter[str],
) -> dict[str, Any]:
    coverage = round(shape_product_count / structural_entity_count, 4) if structural_entity_count > 0 else 0.0
    body_coverage = round(body_representation_count / structural_entity_count, 4) if structural_entity_count > 0 else 0.0
    axis_coverage = round(axis_representation_count / structural_entity_count, 4) if structural_entity_count > 0 else 0.0
    contract_pass = structural_entity_count > 0 and coverage >= 0.95 and body_representation_count > 0
    return {
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS_IFC_REPRESENTATION_SHAPE_AXIS_EXTRACTED"
            if contract_pass
            else "ERR_IFC_REPRESENTATION_SHAPE_AXIS_INCOMPLETE"
        ),
        "representation_scope": "release_safe_shape_axis_inventory",
        "structural_entity_count": structural_entity_count,
        "shape_product_structural_count": shape_product_count,
        "body_representation_structural_count": body_representation_count,
        "axis_representation_structural_count": axis_representation_count,
        "shape_product_coverage_ratio": coverage,
        "body_representation_coverage_ratio": body_coverage,
        "axis_representation_coverage_ratio": axis_coverage,
        "missing_shape_product_count": max(0, structural_entity_count - shape_product_count),
        "representation_identifier_counts": dict(sorted(representation_counts.items())),
        "representation_type_counts": dict(sorted(representation_type_counts.items())),
        "geometry_item_type_counts": dict(sorted(geometry_item_counts.items())),
    }


def _material_section_receipt(
    *,
    structural_entity_count: int,
    material_association_count: int,
    material_bound_structural_count: int,
    material_direct_structural_count: int,
    material_type_structural_count: int,
    section_source_structural_count: int,
    material_root_type_counts: Counter[str],
    material_entity_type_counts: Counter[str],
    section_source_type_counts: Counter[str],
) -> dict[str, Any]:
    material_coverage = (
        round(material_bound_structural_count / structural_entity_count, 4)
        if structural_entity_count > 0
        else 0.0
    )
    section_coverage = (
        round(section_source_structural_count / structural_entity_count, 4)
        if structural_entity_count > 0
        else 0.0
    )
    material_threshold = 0.95
    section_threshold = 0.9
    contract_pass = (
        structural_entity_count > 0
        and material_association_count > 0
        and material_coverage >= material_threshold
        and section_coverage >= section_threshold
    )
    return {
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS_IFC_MATERIAL_SECTION_BINDINGS_EXTRACTED"
            if contract_pass
            else "ERR_IFC_MATERIAL_SECTION_BINDINGS_INCOMPLETE"
        ),
        "binding_scope": "release_safe_material_association_and_section_source_inventory",
        "structural_entity_count": structural_entity_count,
        "material_association_count": material_association_count,
        "material_bound_structural_count": material_bound_structural_count,
        "material_direct_structural_count": material_direct_structural_count,
        "material_type_structural_count": material_type_structural_count,
        "section_source_structural_count": section_source_structural_count,
        "material_binding_coverage_ratio": material_coverage,
        "section_source_coverage_ratio": section_coverage,
        "material_binding_coverage_threshold": material_threshold,
        "section_source_coverage_threshold": section_threshold,
        "missing_material_binding_count": max(0, structural_entity_count - material_bound_structural_count),
        "missing_section_source_count": max(0, structural_entity_count - section_source_structural_count),
        "material_root_type_counts": dict(sorted(material_root_type_counts.items())),
        "material_entity_type_counts": dict(sorted(material_entity_type_counts.items())),
        "section_source_type_counts": dict(sorted(section_source_type_counts.items())),
    }


def _load_case_receipt(
    *,
    structural_entity_count: int,
    load_related_counts: Counter[str],
    load_group_count: int,
    load_case_count: int,
    structural_load_count: int,
    structural_action_count: int,
    connected_structural_action_count: int,
    load_group_assignment_count: int,
) -> dict[str, Any]:
    load_related_record_count = sum(load_related_counts.values())
    contract_pass = (
        load_case_count > 0
        or structural_load_count > 0
        or structural_action_count > 0
        or connected_structural_action_count > 0
    )
    return {
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS_IFC_LOAD_CASES_EXTRACTED"
            if contract_pass
            else "ERR_IFC_LOAD_CASES_MISSING_ENGINEER_ZERO_LOAD_SIGNATURE_REQUIRED"
        ),
        "load_scope": "release_safe_ifc_structural_load_inventory",
        "structural_entity_count": structural_entity_count,
        "load_related_record_count": load_related_record_count,
        "load_group_count": load_group_count,
        "load_case_group_count": load_case_count,
        "structural_load_count": structural_load_count,
        "structural_action_count": structural_action_count,
        "connected_structural_action_count": connected_structural_action_count,
        "load_group_assignment_count": load_group_assignment_count,
        "load_related_entity_type_counts": dict(sorted(load_related_counts.items())),
        "engineer_zero_load_signature_attached": False,
        "zero_load_substitution_requires_engineer_signature": not contract_pass,
        "zero_load_attestation_scope": "not_attested" if not contract_pass else "not_required_loads_extracted",
    }


def parse_ifc_proxy_graph(path: Path) -> dict[str, Any]:
    entity_counts: Counter[str] = Counter()
    nodes: dict[str, dict[str, Any]] = {}
    records = _records(path)
    parsed_records: list[tuple[str, str, list[str]]] = []
    record_by_id: dict[str, tuple[str, list[str]]] = {}

    for record in records:
        parsed = _record_args(record)
        if parsed is None:
            continue
        entity_id, entity_type, args = parsed
        parsed_records.append(parsed)
        record_by_id[entity_id] = (entity_type, args)
        entity_counts[entity_type] += 1
        if entity_type in COUNTED_ENTITY_TYPES:
            nodes[entity_id] = {
                "id": entity_id,
                "ifc_entity_type": entity_type,
                "label": _entity_label(entity_type, args, entity_id),
                "proxy_node_kind": "storey" if entity_type in SPATIAL_ENTITY_TYPES else "structural_element",
            }

    structural_entity_count = sum(entity_counts[entity_type] for entity_type in STRUCTURAL_ENTITY_TYPES)
    storey_count = entity_counts["IFCBUILDINGSTOREY"]
    placement_memo: dict[str, tuple[list[float], list[list[float]]] | None] = {}
    placement_points: dict[str, list[float]] = {}
    placement_transforms: dict[str, tuple[list[float], list[list[float]]]] = {}
    for entity_id, entity_type, args in parsed_records:
        if entity_id not in nodes or len(args) <= 5:
            continue
        placement_id = _first_ref(args[5])
        transform = _local_placement_transform(placement_id, record_by_id, placement_memo, set())
        if transform is None:
            continue
        origin, _basis = transform
        point = _round_point(origin)
        placement_points[entity_id] = point
        placement_transforms[entity_id] = transform
        nodes[entity_id].update(
            {
                "x": point[0],
                "y": point[1],
                "z": point[2],
                "placement_source": "IFCLOCALPLACEMENT",
            }
        )
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    aggregate_group_candidates: list[tuple[str, list[str]]] = []

    for entity_id, entity_type, args in parsed_records:
        if len(args) < 6:
            continue
        if entity_type == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
            related_ids = [f"#{ref}" for ref in REF_RE.findall(args[4])]
            container_ids = [f"#{ref}" for ref in REF_RE.findall(args[5])]
            for source in related_ids:
                for target in container_ids:
                    if source in nodes and target in nodes:
                        _append_unique_edge(
                            edges,
                            seen_edges,
                            source=source,
                            target=target,
                            relationship=CONTAINED_RELATIONSHIP,
                        )
        elif entity_type == "IFCRELAGGREGATES":
            parent_ids = [f"#{ref}" for ref in REF_RE.findall(args[4])]
            child_ids = [f"#{ref}" for ref in REF_RE.findall(args[5])]
            counted_children = [child_id for child_id in child_ids if child_id in nodes]
            counted_parents = [parent_id for parent_id in parent_ids if parent_id in nodes]
            for source in counted_children:
                for target in counted_parents:
                    _append_unique_edge(
                        edges,
                        seen_edges,
                        source=source,
                        target=target,
                        relationship=AGGREGATE_RELATIONSHIP,
                    )
            if counted_children and not counted_parents:
                aggregate_group_candidates.append((entity_id, counted_children))

    direct_edge_count = len(edges)
    if structural_entity_count > 0 and direct_edge_count < structural_entity_count:
        for entity_id, counted_children in aggregate_group_candidates:
            group_id = _relationship_group_id("IFCRELAGGREGATES", entity_id)
            nodes[group_id] = {
                "id": group_id,
                "ifc_entity_type": "IFCRELAGGREGATES",
                "label": f"IFCRELAGGREGATES:{entity_id}",
                "proxy_node_kind": "relationship_group",
                "relationship": AGGREGATE_RELATIONSHIP,
            }
            child_points = [placement_points[source] for source in counted_children if source in placement_points]
            if child_points:
                centroid = _round_point(
                    [
                        sum(point[index] for point in child_points) / len(child_points)
                        for index in range(3)
                    ]
                )
                placement_points[group_id] = centroid
                nodes[group_id].update(
                    {
                        "x": centroid[0],
                        "y": centroid[1],
                        "z": centroid[2],
                        "placement_source": "child_placement_centroid",
                    }
                )
            for source in counted_children:
                _append_unique_edge(
                    edges,
                    seen_edges,
                    source=source,
                    target=group_id,
                    relationship=AGGREGATE_RELATIONSHIP,
                )

    relationship_counts = Counter(edge["relationship"] for edge in edges)
    relationship_group_node_count = sum(
        1 for node in nodes.values() if node.get("proxy_node_kind") == "relationship_group"
    )
    relationship_extraction_modes = []
    if direct_edge_count > 0:
        relationship_extraction_modes.append("direct_counted_entity_edges")
    if relationship_group_node_count > 0:
        relationship_extraction_modes.append("release_safe_aggregate_group_edges")
    structural_placement_count = sum(
        1
        for entity_id, point in placement_points.items()
        if point and nodes.get(entity_id, {}).get("proxy_node_kind") == "structural_element"
    )
    placement_receipt = _placement_receipt(
        structural_entity_count=int(structural_entity_count),
        structural_placement_count=structural_placement_count,
        node_placement_count=len(placement_points),
        points=list(placement_points.values()),
    )
    representation_counts: Counter[str] = Counter()
    representation_type_counts: Counter[str] = Counter()
    geometry_item_counts: Counter[str] = Counter()
    shape_product_ids: set[str] = set()
    body_representation_ids: set[str] = set()
    axis_representation_ids: set[str] = set()
    member_extent_ids: set[str] = set()
    axis_polyline_extent_ids: set[str] = set()
    body_extrusion_extent_ids: set[str] = set()
    for entity_id, entity_type, args in parsed_records:
        if entity_type not in STRUCTURAL_ENTITY_TYPES or len(args) <= 6:
            continue
        product_shape_id = _first_ref(args[6])
        product_shape = record_by_id.get(product_shape_id or "")
        if product_shape is None or product_shape[0] != "IFCPRODUCTDEFINITIONSHAPE" or len(product_shape[1]) <= 2:
            node = nodes.get(entity_id)
            if node is not None:
                node["member_extent_missing_reason"] = "source_ifc_product_shape_missing"
            continue
        shape_product_ids.add(entity_id)
        has_body = False
        has_axis = False
        for representation_id in _refs(product_shape[1][2]):
            representation = record_by_id.get(representation_id)
            if representation is None or representation[0] != "IFCSHAPEREPRESENTATION" or len(representation[1]) <= 3:
                continue
            representation_identifier = _step_label(representation[1][1]) or "UNSPECIFIED"
            representation_type = _step_label(representation[1][2]) or "UNSPECIFIED"
            representation_counts[representation_identifier] += 1
            representation_type_counts[representation_type] += 1
            if representation_identifier.upper() == "BODY":
                has_body = True
            if representation_identifier.upper() == "AXIS" or "CURVE" in representation_type.upper():
                has_axis = True
            for item_id in _refs(representation[1][3]):
                item = record_by_id.get(item_id)
                if item is not None:
                    geometry_item_counts[item[0]] += 1
        if has_body:
            body_representation_ids.add(entity_id)
        if has_axis:
            axis_representation_ids.add(entity_id)
        product_transform = placement_transforms.get(entity_id) or _identity_transform()
        extent_source, extent_points = _member_extent_from_representations(
            product_shape_id=product_shape_id,
            record_by_id=record_by_id,
            product_transform=product_transform,
        )
        if extent_points:
            member_extent_ids.add(entity_id)
            if extent_source == "ifc_axis_polyline_world":
                axis_polyline_extent_ids.add(entity_id)
            elif extent_source in BODY_MEMBER_EXTENT_SOURCES:
                body_extrusion_extent_ids.add(entity_id)
            nodes[entity_id]["member_axis_world_points"] = extent_points
            nodes[entity_id]["member_extent_source"] = extent_source
        else:
            nodes[entity_id]["member_extent_missing_reason"] = "member_extent_geometry_unresolved"
    representation_receipt = _representation_receipt(
        structural_entity_count=int(structural_entity_count),
        shape_product_count=len(shape_product_ids),
        body_representation_count=len(body_representation_ids),
        axis_representation_count=len(axis_representation_ids),
        representation_counts=representation_counts,
        representation_type_counts=representation_type_counts,
        geometry_item_counts=geometry_item_counts,
    )
    structural_ids = {
        entity_id
        for entity_id, entity_type, _args in parsed_records
        if entity_type in STRUCTURAL_ENTITY_TYPES
    }
    type_to_structural_ids: dict[str, set[str]] = {}
    for _entity_id, entity_type, args in parsed_records:
        if entity_type != "IFCRELDEFINESBYTYPE" or len(args) <= 5:
            continue
        type_id = _first_ref(args[5])
        related_structural_ids = {ref for ref in _refs(args[4]) if ref in structural_ids}
        if type_id and related_structural_ids:
            type_to_structural_ids.setdefault(type_id, set()).update(related_structural_ids)

    closure_memo: dict[str, set[str]] = {}
    material_sources_by_id: dict[str, set[str]] = {}
    section_sources_by_id: dict[str, set[str]] = {}
    material_root_type_counts: Counter[str] = Counter()
    material_entity_type_refs: dict[str, set[str]] = {}
    section_source_type_refs: dict[str, set[str]] = {}
    material_association_count = 0

    def add_source(target: str, source: str, source_map: dict[str, set[str]]) -> None:
        if target in structural_ids:
            source_map.setdefault(target, set()).add(source)

    def add_type_ref(entity_type: str, entity_id: str, groups: dict[str, set[str]]) -> None:
        groups.setdefault(entity_type, set()).add(entity_id)

    for _entity_id, entity_type, args in parsed_records:
        if entity_type != "IFCRELASSOCIATESMATERIAL" or len(args) <= 5:
            continue
        material_association_count += 1
        related_ids = _refs(args[4])
        direct_targets = {ref for ref in related_ids if ref in structural_ids}
        typed_targets: set[str] = set()
        for related_id in related_ids:
            typed_targets.update(type_to_structural_ids.get(related_id, set()))
        for target in direct_targets:
            add_source(target, "direct", material_sources_by_id)
        for target in typed_targets:
            add_source(target, "type", material_sources_by_id)

        material_root_id = _first_ref(args[5])
        material_root = record_by_id.get(material_root_id or "")
        if material_root is not None:
            material_root_type_counts[material_root[0]] += 1
        material_graph_ids = _ref_closure(material_root_id, record_by_id, closure_memo)
        has_section_source = False
        for ref in material_graph_ids:
            material_row = record_by_id.get(ref)
            if material_row is None:
                continue
            ref_type = material_row[0]
            if ref_type.startswith("IFCMATERIAL"):
                add_type_ref(ref_type, ref, material_entity_type_refs)
            if _is_section_source_type(ref_type):
                has_section_source = True
                add_type_ref(ref_type, ref, section_source_type_refs)
        if has_section_source:
            for target in direct_targets | typed_targets:
                add_source(target, "material_definition", section_sources_by_id)

    for entity_id, entity_type, args in parsed_records:
        if entity_type not in STRUCTURAL_ENTITY_TYPES or len(args) <= 6:
            continue
        product_shape_id = _first_ref(args[6])
        for ref in _ref_closure(product_shape_id, record_by_id, closure_memo):
            shape_row = record_by_id.get(ref)
            if shape_row is None:
                continue
            ref_type = shape_row[0]
            if ref_type.endswith("PROFILEDEF"):
                add_source(entity_id, "shape_profile", section_sources_by_id)
                add_type_ref(ref_type, ref, section_source_type_refs)

    for entity_id, sources in material_sources_by_id.items():
        node = nodes.get(entity_id)
        if node is not None:
            node["material_binding_source"] = "+".join(sorted(sources))
    for entity_id, sources in section_sources_by_id.items():
        node = nodes.get(entity_id)
        if node is not None:
            node["section_source"] = "+".join(sorted(sources))

    material_entity_type_counts = Counter(
        {entity_type: len(refs) for entity_type, refs in material_entity_type_refs.items()}
    )
    section_source_type_counts = Counter(
        {entity_type: len(refs) for entity_type, refs in section_source_type_refs.items()}
    )
    material_section_receipt = _material_section_receipt(
        structural_entity_count=int(structural_entity_count),
        material_association_count=material_association_count,
        material_bound_structural_count=len(material_sources_by_id),
        material_direct_structural_count=sum(1 for sources in material_sources_by_id.values() if "direct" in sources),
        material_type_structural_count=sum(1 for sources in material_sources_by_id.values() if "type" in sources),
        section_source_structural_count=len(section_sources_by_id),
        material_root_type_counts=material_root_type_counts,
        material_entity_type_counts=material_entity_type_counts,
        section_source_type_counts=section_source_type_counts,
    )
    load_related_counts: Counter[str] = Counter()
    load_group_ids: set[str] = set()
    load_case_ids: set[str] = set()
    structural_load_ids: set[str] = set()
    structural_action_ids: set[str] = set()
    for entity_id, entity_type, args in parsed_records:
        if _is_load_related_type(entity_type):
            load_related_counts[entity_type] += 1
        if _is_load_group_type(entity_type):
            load_group_ids.add(entity_id)
            if _is_load_case_group(args):
                load_case_ids.add(entity_id)
        if _is_structural_load_type(entity_type):
            structural_load_ids.add(entity_id)
        if _is_structural_action_type(entity_type):
            structural_action_ids.add(entity_id)

    connected_structural_action_ids: set[str] = set()
    load_group_assignment_count = 0
    for _entity_id, entity_type, args in parsed_records:
        if entity_type not in LOAD_RELATIONSHIP_ENTITY_TYPES:
            continue
        refs = {ref for arg in args for ref in _refs(arg)}
        if entity_type == "IFCRELCONNECTSSTRUCTURALACTIVITY":
            if refs & structural_ids:
                connected_structural_action_ids.update(refs & structural_action_ids)
            if refs & structural_action_ids:
                load_related_counts[entity_type] += 1
        if refs & load_group_ids and (refs & structural_action_ids or refs & structural_load_ids):
            load_group_assignment_count += 1
            load_related_counts[entity_type] += 1

    load_case_receipt = _load_case_receipt(
        structural_entity_count=int(structural_entity_count),
        load_related_counts=load_related_counts,
        load_group_count=len(load_group_ids),
        load_case_count=len(load_case_ids),
        structural_load_count=len(structural_load_ids),
        structural_action_count=len(structural_action_ids),
        connected_structural_action_count=len(connected_structural_action_ids),
        load_group_assignment_count=load_group_assignment_count,
    )
    return {
        "adapter_mode": ADAPTER_MODE,
        "entity_counts": {entity_type: int(entity_counts[entity_type]) for entity_type in sorted(COUNTED_ENTITY_TYPES)},
        "metrics": {
            "record_count": len(records),
            "proxy_node_count": len(nodes),
            "proxy_edge_count": len(edges),
            "direct_relationship_edge_count": direct_edge_count,
            "relationship_group_node_count": relationship_group_node_count,
            "placement_coordinate_node_count": len(placement_points),
            "placement_coordinate_structural_count": structural_placement_count,
            "placement_coverage_ratio": placement_receipt["placement_coverage_ratio"],
            "shape_product_structural_count": len(shape_product_ids),
            "body_representation_structural_count": len(body_representation_ids),
            "axis_representation_structural_count": len(axis_representation_ids),
            "axis_polyline_extent_structural_count": len(axis_polyline_extent_ids),
            "body_extrusion_extent_structural_count": len(body_extrusion_extent_ids),
            "member_extent_structural_count": len(member_extent_ids),
            "member_extent_coverage_ratio": (
                round(len(member_extent_ids) / structural_entity_count, 4)
                if structural_entity_count > 0
                else 0.0
            ),
            "shape_product_coverage_ratio": representation_receipt["shape_product_coverage_ratio"],
            "material_bound_structural_count": len(material_sources_by_id),
            "material_binding_coverage_ratio": material_section_receipt["material_binding_coverage_ratio"],
            "section_source_structural_count": len(section_sources_by_id),
            "section_source_coverage_ratio": material_section_receipt["section_source_coverage_ratio"],
            "load_related_record_count": load_case_receipt["load_related_record_count"],
            "load_case_group_count": len(load_case_ids),
            "structural_load_count": len(structural_load_ids),
            "structural_action_count": len(structural_action_ids),
            "structural_entity_count": int(structural_entity_count),
            "storey_count": int(storey_count),
        },
        "evidence_receipts": {
            "ifc_local_placement_coordinate_extraction_receipt": placement_receipt,
            "ifc_representation_shape_axis_receipt": representation_receipt,
            "ifc_material_section_binding_receipt": material_section_receipt,
            "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt": load_case_receipt,
        },
        "proxy_relationship_counts": dict(sorted(relationship_counts.items())),
        "relationship_extraction_modes": relationship_extraction_modes,
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def _release_safe_source(project: dict[str, Any], file_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": str(project.get("project_id", "") or ""),
        "project_title": str(project.get("project_title", "") or ""),
        "source_family": str(project.get("source_family", "") or ""),
        "file_id": str(file_row.get("file_id", "") or ""),
        "file_name": str(file_row.get("file_name", "") or ""),
        "file_type": str(file_row.get("file_type", "") or ""),
        "role": str(file_row.get("role", "") or ""),
        "bytes": int(file_row.get("bytes", 0) or 0),
        "sha256": str(file_row.get("sha256", "") or ""),
        "source_url": str(file_row.get("source_url", "") or ""),
        "raw_redistribution_allowed": bool(file_row.get("raw_redistribution_allowed", False)),
        "release_surface_allowed": bool(file_row.get("release_surface_allowed", False)),
    }


def convert_ifc_corpus(
    *,
    private_manifest_path: Path,
    redacted_manifest_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    private_rows = _manifest_ifc_rows(_load_json(private_manifest_path))
    redacted_rows = _manifest_ifc_rows(_load_json(redacted_manifest_path))
    reports: list[dict[str, Any]] = []
    errors: list[str] = []

    for key, redacted_entry in sorted(redacted_rows.items()):
        private_entry = private_rows.get(key)
        project = redacted_entry["project"]
        file_row = redacted_entry["file"]
        file_id = str(file_row.get("file_id", "") or "")
        file_name = str(file_row.get("file_name", "") or "")
        stem = _safe_report_stem(file_id, file_name)
        report_path = out_dir / f"{stem}.report.json"
        graph_path = out_dir / f"{stem}.graph.json"
        solver_graph_path = out_dir / f"{stem}.solver_graph.json"
        solver_npz_path = out_dir / f"{stem}.solver_graph.npz"
        source = _release_safe_source(project, file_row)
        if not private_entry:
            report = {
                "schema_version": ADAPTER_SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "contract_pass": False,
                "reason_code": "ERR_PRIVATE_MANIFEST_ROW_MISSING",
                "adapter_mode": ADAPTER_MODE,
                "source": source,
            }
            errors.append(f"{source['project_id']}/{source['file_id']}: private manifest row missing")
        else:
            private_file_row = private_entry["file"]
            raw_path = Path(str(private_file_row.get("private_path", "") or ""))
            if not raw_path.exists():
                report = {
                    "schema_version": ADAPTER_SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "contract_pass": False,
                    "reason_code": "ERR_PRIVATE_IFC_FILE_MISSING",
                    "adapter_mode": ADAPTER_MODE,
                    "source": source,
                }
                errors.append(f"{source['project_id']}/{source['file_id']}: private IFC file missing")
            else:
                graph = {
                    "schema_version": ADAPTER_SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": source,
                    **parse_ifc_proxy_graph(raw_path),
                }
                solver_receipt = _write_solver_graph_artifacts(
                    graph=graph,
                    json_path=solver_graph_path,
                    npz_path=solver_npz_path,
                )
                graph.setdefault("evidence_receipts", {})["solver_graph_json_npz_receipt"] = solver_receipt
                graph["solver_graph_artifacts"] = {
                    "solver_graph_json": str(solver_graph_path),
                    "solver_graph_npz": str(solver_npz_path),
                }
                _write_json(graph_path, graph)
                metrics = graph["metrics"]
                report = {
                    "schema_version": ADAPTER_SCHEMA_VERSION,
                    "generated_at": graph["generated_at"],
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "adapter_mode": ADAPTER_MODE,
                    "source": source,
                    "graph_json": str(graph_path),
                    "solver_graph_json": str(solver_graph_path),
                    "solver_graph_npz": str(solver_npz_path),
                    "metrics": metrics,
                    "entity_counts": graph["entity_counts"],
                    "evidence_receipts": graph.get("evidence_receipts", {}),
                    "solver_exact": False,
                    "optimization_readiness": "ifc_proxy_graph_ready",
                    "readiness_note": (
                        "Entity-count proxy graph only; exact member geometry, material/section binding, "
                        "load extraction, and solver-native connectivity are not asserted."
                    ),
                }
        _write_json(report_path, report)
        reports.append({**report, "report_json": str(report_path)})

    ready_reports = [report for report in reports if report.get("contract_pass") is True]
    summary = {
        "ifc_candidate_count": len(reports),
        "ifc_proxy_graph_ready_count": len(ready_reports),
        "failed_count": len(reports) - len(ready_reports),
        "adapter_mode": ADAPTER_MODE,
        "solver_exact": False,
        "proxy_node_count_total": sum(int(report.get("metrics", {}).get("proxy_node_count", 0) or 0) for report in ready_reports),
        "proxy_edge_count_total": sum(int(report.get("metrics", {}).get("proxy_edge_count", 0) or 0) for report in ready_reports),
        "structural_entity_count_total": sum(
            int(report.get("metrics", {}).get("structural_entity_count", 0) or 0) for report in ready_reports
        ),
        "local_placement_receipt_count": sum(
            1
            for report in ready_reports
            if bool(
                report.get("evidence_receipts", {})
                .get("ifc_local_placement_coordinate_extraction_receipt", {})
                .get("contract_pass", False)
            )
        ),
        "shape_axis_receipt_count": sum(
            1
            for report in ready_reports
            if bool(
                report.get("evidence_receipts", {})
                .get("ifc_representation_shape_axis_receipt", {})
                .get("contract_pass", False)
            )
        ),
        "material_section_receipt_count": sum(
            1
            for report in ready_reports
            if bool(
                report.get("evidence_receipts", {})
                .get("ifc_material_section_binding_receipt", {})
                .get("contract_pass", False)
            )
        ),
        "solver_graph_json_npz_receipt_count": sum(
            1
            for report in ready_reports
            if bool(
                report.get("evidence_receipts", {})
                .get("solver_graph_json_npz_receipt", {})
                .get("contract_pass", False)
            )
        ),
        "solver_graph_model_node_count_total": sum(
            int(
                report.get("evidence_receipts", {})
                .get("solver_graph_json_npz_receipt", {})
                .get("model_node_count", 0)
                or 0
            )
            for report in ready_reports
        ),
        "solver_graph_element_count_total": sum(
            int(
                report.get("evidence_receipts", {})
                .get("solver_graph_json_npz_receipt", {})
                .get("element_count", 0)
                or 0
            )
            for report in ready_reports
        ),
        "load_case_receipt_count": sum(
            1
            for report in ready_reports
            if bool(
                report.get("evidence_receipts", {})
                .get("ifc_load_case_extraction_or_engineer_signed_zero_load_receipt", {})
                .get("contract_pass", False)
            )
        ),
        "zero_load_signature_required_count": sum(
            1
            for report in ready_reports
            if bool(
                report.get("evidence_receipts", {})
                .get("ifc_load_case_extraction_or_engineer_signed_zero_load_receipt", {})
                .get("zero_load_substitution_requires_engineer_signature", False)
            )
        ),
    }
    manifest = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not errors,
        "reason_code": "PASS" if not errors else "ERR_IFC_PROXY_GRAPH_CONVERSION",
        "source_redacted_manifest": str(redacted_manifest_path),
        "private_manifest_used": True,
        "output_dir": str(out_dir),
        "summary": summary,
        "reports": [
            {
                "project_id": report["source"]["project_id"],
                "file_id": report["source"]["file_id"],
                "file_name": report["source"]["file_name"],
                "contract_pass": bool(report.get("contract_pass", False)),
                "reason_code": str(report.get("reason_code", "") or ""),
                "report_json": report["report_json"],
                "graph_json": str(report.get("graph_json", "") or ""),
                "solver_graph_json": str(report.get("solver_graph_json", "") or ""),
                "solver_graph_npz": str(report.get("solver_graph_npz", "") or ""),
                "adapter_mode": ADAPTER_MODE,
                "solver_exact": False,
                "metrics": report.get("metrics", {}),
            }
            for report in reports
        ],
        "errors": errors,
    }
    _write_json(out_dir / "ifc_adapter_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-manifest", type=Path, default=DEFAULT_PRIVATE_MANIFEST)
    parser.add_argument("--redacted-manifest", type=Path, default=DEFAULT_REDACTED_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest = convert_ifc_corpus(
        private_manifest_path=args.private_manifest,
        redacted_manifest_path=args.redacted_manifest,
        out_dir=args.out_dir,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = manifest["summary"]
        print(
            "IFC private corpus adapter: "
            f"{manifest['reason_code']} | candidates={summary['ifc_candidate_count']} | "
            f"proxy_ready={summary['ifc_proxy_graph_ready_count']} | "
            f"structural_entities={summary['structural_entity_count_total']}"
        )
    return 0 if manifest["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
