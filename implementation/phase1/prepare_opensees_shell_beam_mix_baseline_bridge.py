#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np

from parse_opensees_to_csr import _as_int, _iter_statements, _parse_model, _tokenize


REASONS = {
    "PASS": "opensees text baseline bridge passed",
    "ERR_FILE_MISSING": "input opensees model missing",
    "ERR_PARSE_FAIL": "no coordinated opensees elements could be bridged",
}

ALLOWED_EXPR_GLOBALS = {
    **{name: getattr(math, name) for name in dir(math) if not name.startswith("_")},
    "abs": abs,
    "min": min,
    "max": max,
    "pow": pow,
}
VARIABLE_TOKEN_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _round_point(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return (round(float(point[0]), 6), round(float(point[1]), 6), round(float(point[2]), 6))


def _cluster_levels(values: list[float], tol: float = 1.0e-6) -> list[float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return [0.0]
    clustered = [ordered[0]]
    for value in ordered[1:]:
        if abs(value - clustered[-1]) <= tol:
            clustered[-1] = (clustered[-1] + value) * 0.5
        else:
            clustered.append(value)
    return clustered


def _resolve_scalar(token: str, variables: dict[str, float]) -> float | None:
    raw = str(token or "").strip()
    if not raw:
        return None
    if raw.startswith("$") and " " not in raw and raw[1:] in variables:
        return variables.get(raw[1:])
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        raw = inner[4:].strip() if inner.lower().startswith("expr") else inner
    missing_variable = False

    def _replace_variable(match: re.Match[str]) -> str:
        nonlocal missing_variable
        name = match.group(1)
        value = variables.get(name)
        if value is None:
            missing_variable = True
            return "None"
        return repr(float(value))

    substituted = VARIABLE_TOKEN_RE.sub(_replace_variable, raw)
    if missing_variable:
        return None
    try:
        return float(substituted)
    except Exception:
        try:
            return float(eval(substituted, {"__builtins__": {}}, ALLOWED_EXPR_GLOBALS))
        except Exception:
            return None


def _consume_scalar_token(tokens: list[str], start_index: int) -> tuple[str, int]:
    if start_index >= len(tokens):
        return "", start_index
    parts = [str(tokens[start_index])]
    bracket_balance = parts[0].count("[") - parts[0].count("]")
    next_index = start_index + 1
    while bracket_balance > 0 and next_index < len(tokens):
        token = str(tokens[next_index])
        parts.append(token)
        bracket_balance += token.count("[") - token.count("]")
        next_index += 1
    return " ".join(parts), next_index


def _parse_coordinate_nodes(path: Path) -> tuple[dict[int, tuple[float, float, float]], dict[str, float], int]:
    variables: dict[str, float] = {}
    nodes: dict[int, tuple[float, float, float]] = {}
    resolved_node_count = 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    for stmt in _iter_statements(text):
        toks = _tokenize(stmt)
        if not toks:
            continue
        head = toks[0].lower()
        if head in {"set", "variable"} and len(toks) >= 3:
            value_token, _ = _consume_scalar_token(toks, 2)
            value = _resolve_scalar(value_token, variables)
            if value is not None:
                variables[str(toks[1])] = float(value)
            continue
        if head not in {"node", "ops.node"} or len(toks) < 4:
            continue
        node_id = _as_int(toks[1])
        x_token, next_index = _consume_scalar_token(toks, 2)
        y_token, next_index = _consume_scalar_token(toks, next_index)
        x_value = _resolve_scalar(x_token, variables)
        y_value = _resolve_scalar(y_token, variables)
        if node_id is None or x_value is None or y_value is None:
            continue
        z_token, _ = _consume_scalar_token(toks, next_index)
        z_value = _resolve_scalar(z_token, variables) if z_token else None
        if z_value is None:
            coords = (float(x_value), 0.0, float(y_value))
        else:
            coords = (float(x_value), float(y_value), float(z_value))
        nodes[int(node_id)] = _round_point(coords)
        resolved_node_count += 1
    return nodes, variables, resolved_node_count


def _story_band_for_z(z_value: float, levels: list[float]) -> int:
    if not levels:
        return 1
    closest_index = min(range(len(levels)), key=lambda idx: abs(float(levels[idx]) - float(z_value)))
    return int(closest_index + 1)


def _element_class(etype: str, coords: list[tuple[float, float, float]]) -> tuple[str, str]:
    token = str(etype or "").lower()
    if len(coords) >= 3 or any(marker in token for marker in ("shell", "quad", "mitc", "asdshell")):
        xs = [point[0] for point in coords]
        ys = [point[1] for point in coords]
        zs = [point[2] for point in coords]
        xy_span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0e-6)
        z_span = max(zs) - min(zs)
        if z_span > max(0.5, xy_span * 0.32):
            return ("wall", "PLATE")
        return ("slab", "PLATE")

    if len(coords) >= 2:
        start = coords[0]
        end = coords[1]
        dx = float(end[0] - start[0])
        dy = float(end[1] - start[1])
        dz = float(end[2] - start[2])
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        vertical_ratio = abs(dz) / length if length > 1.0e-9 else 0.0
        if vertical_ratio >= 0.78:
            return ("column", "COLUMN")
        if "truss" in token or "brace" in token:
            return ("beam_brace", "BEAM")
        return ("beam", "BEAM")

    return ("other", "OTHER")


def _member_type_for_family(family: str) -> str:
    token = str(family or "").lower()
    if "beam" in token:
        return "beam"
    if "column" in token:
        return "column"
    if "wall" in token:
        return "wall"
    if "slab" in token:
        return "slab"
    return "other"


def _zone_label_for_coords(
    coords: list[tuple[float, float, float]],
    *,
    family: str,
    centroid_xy: tuple[float, float],
    max_radius: float,
) -> str:
    member_type = _member_type_for_family(family)
    if member_type == "slab":
        return "intermediate"
    radii = [
        math.hypot(float(point[0]) - float(centroid_xy[0]), float(point[1]) - float(centroid_xy[1]))
        for point in coords
    ]
    mean_radius = sum(radii) / max(1, len(radii))
    if max_radius <= 1.0e-9:
        return "core"
    if mean_radius <= max_radius * 0.42:
        return "core"
    if mean_radius <= max_radius * 0.72:
        return "intermediate"
    return "perimeter"


def _type_label(histogram: Counter[str]) -> str:
    return ", ".join(
        f"{key}={int(value)}"
        for key, value in sorted(histogram.items(), key=lambda item: (-int(item[1]), str(item[0]).lower()))
    ) or "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge OpenSees shell-beam mix text model into baseline 3D viewer geometry.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--opensees-model", required=True)
    parser.add_argument("--model-json-out", required=True)
    parser.add_argument("--npz-out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args()

    source_id = str(args.source_id).strip() or "unknown_source"
    model_path = Path(args.opensees_model)
    model_json_out = Path(args.model_json_out)
    npz_out = Path(args.npz_out)
    report_out = Path(args.report_out)

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "report_type": "opensees_text_baseline_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "inputs": {
            "opensees_model": str(model_path),
            "model_json_out": str(model_json_out),
            "npz_out": str(npz_out),
            "report_out": str(report_out),
        },
    }

    if not model_path.exists():
        report.update({"contract_pass": False, "reason_code": "ERR_FILE_MISSING"})
        _write_json(report_out, report)
        return 1

    nodes_raw, elements_raw, parse_counters = _parse_model(model_path)
    coord_nodes, variable_map, resolved_node_count = _parse_coordinate_nodes(model_path)

    if not coord_nodes:
        report.update(
            {
                "contract_pass": False,
                "reason_code": "ERR_PARSE_FAIL",
                "parse_counters": parse_counters,
                "summary": {
                    "coordinated_node_count": 0,
                    "resolved_node_count": int(resolved_node_count),
                    "variable_count": int(len(variable_map)),
                    "kept_element_count": 0,
                },
            }
        )
        _write_json(report_out, report)
        return 1

    xs = [point[0] for point in coord_nodes.values()]
    ys = [point[1] for point in coord_nodes.values()]
    zs = [point[2] for point in coord_nodes.values()]
    centroid_xy = (sum(xs) / len(xs), sum(ys) / len(ys))
    max_radius = max(
        (
            math.hypot(float(point[0]) - float(centroid_xy[0]), float(point[1]) - float(centroid_xy[1]))
            for point in coord_nodes.values()
        ),
        default=0.0,
    )
    story_levels = _cluster_levels(zs)

    model_elements: list[dict[str, Any]] = []
    element_type_histogram: Counter[str] = Counter()
    element_class_histogram: Counter[str] = Counter()
    member_ids: list[str] = []
    member_types: list[str] = []
    group_ids: list[str] = []
    group_index_per_member: list[int] = []
    story_band_index: list[int] = []
    zone_labels: list[str] = []

    group_index_lookup: dict[str, int] = {}
    unique_group_ids: list[str] = []
    member_type_per_group: list[str] = []
    zone_label_per_group: list[str] = []
    story_band_per_group: list[int] = []

    for etype, element_id, node_ids in elements_raw:
        coords = [coord_nodes[int(node_id)] for node_id in node_ids if int(node_id) in coord_nodes]
        if len(coords) < 2:
            continue
        family, type_label = _element_class(str(etype), coords)
        member_type = _member_type_for_family(family)
        centroid_z = sum(point[2] for point in coords) / len(coords)
        story_band = _story_band_for_z(centroid_z, story_levels)
        zone_label = _zone_label_for_coords(
            coords,
            family=family,
            centroid_xy=centroid_xy,
            max_radius=max_radius,
        )
        group_id = f"S{int(story_band):02d}:{zone_label}:{family}"
        if group_id not in group_index_lookup:
            group_index_lookup[group_id] = len(unique_group_ids)
            unique_group_ids.append(group_id)
            member_type_per_group.append(member_type)
            zone_label_per_group.append(zone_label)
            story_band_per_group.append(int(story_band))
        group_index = int(group_index_lookup[group_id])
        element_type_histogram[str(etype)] += 1
        element_class_histogram[member_type] += 1
        model_elements.append(
            {
                "id": str(int(element_id)),
                "type": type_label,
                "family": family,
                "node_ids": [int(node_id) for node_id in node_ids if int(node_id) in coord_nodes],
                "element_id": int(element_id),
                "source_element_type": str(etype),
                "story_band": int(story_band),
                "zone_label": zone_label,
                "group_id": group_id,
                "group_index": group_index,
            }
        )
        member_ids.append(str(int(element_id)))
        member_types.append(member_type)
        group_ids.append(group_id)
        group_index_per_member.append(group_index)
        story_band_index.append(int(story_band))
        zone_labels.append(zone_label)

    if not model_elements:
        report.update(
            {
                "contract_pass": False,
                "reason_code": "ERR_PARSE_FAIL",
                "parse_counters": parse_counters,
                "summary": {
                    "coordinated_node_count": int(len(coord_nodes)),
                    "resolved_node_count": int(resolved_node_count),
                    "variable_count": int(len(variable_map)),
                    "kept_element_count": 0,
                },
            }
        )
        _write_json(report_out, report)
        return 1

    model_nodes = [
        {"id": int(node_id), "x": float(point[0]), "y": float(point[1]), "z": float(point[2])}
        for node_id, point in sorted(coord_nodes.items(), key=lambda item: int(item[0]))
    ]
    model_elements.sort(key=lambda row: int(row.get("element_id", 0) or 0))

    source_profile_label = 'shell-beam mix' if int(element_class_histogram.get('slab', 0) or 0) > 0 else 'frame-brace mix'

    model_payload = {
        "schema_version": "1.0",
        "model_kind": "opensees_text_baseline",
        "topology_metrics": {
            "node_count": int(len(model_nodes)),
            "element_count": int(len(model_elements)),
            "story_band_count": int(len(story_levels)),
            "element_type_histogram": dict(element_type_histogram),
            "element_class_histogram": dict(element_class_histogram),
        },
        "model": {
            "nodes": model_nodes,
            "elements": model_elements,
        },
    }
    _write_json(model_json_out, model_payload)

    npz_out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        npz_out,
        member_ids=np.asarray(member_ids, dtype=str),
        member_types=np.asarray(member_types, dtype=str),
        group_ids=np.asarray(group_ids, dtype=str),
        group_index_per_member=np.asarray(group_index_per_member, dtype=np.int32),
        member_type_per_group=np.asarray(member_type_per_group, dtype=str),
        zone_label_per_group=np.asarray(zone_label_per_group, dtype=str),
        story_band_per_group=np.asarray(story_band_per_group, dtype=np.int32),
        story_band_index=np.asarray(story_band_index, dtype=np.int32),
        zone_labels=np.asarray(zone_labels, dtype=str),
        unique_group_ids=np.asarray(unique_group_ids, dtype=str),
    )

    report.update(
        {
            "source_provenance": {"source_class": "opensees_text", "source_path": str(model_path)},
            "parse_counters": parse_counters,
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "viewer_ready": True,
                "accepted_object_count": int(len(model_elements)),
                "node_count": int(len(model_nodes)),
                "element_count": int(len(model_elements)),
                "resolved_node_count": int(resolved_node_count),
                "variable_count": int(len(variable_map)),
                "story_band_count": int(len(story_levels)),
                "family_assumption": "opensees_text_orientation_classification",
                "source_profile_label": source_profile_label,
                "accepted_type_label": _type_label(element_type_histogram),
                "element_class_label": _type_label(element_class_histogram),
                "max_radius": round(float(max_radius), 3),
                "bbox_label": (
                    f"x={round(min(xs), 3)}..{round(max(xs), 3)} | "
                    f"y={round(min(ys), 3)}..{round(max(ys), 3)} | "
                    f"z={round(min(zs), 3)}..{round(max(zs), 3)}"
                ),
            },
            "artifacts": {
                "model_json": str(model_json_out),
                "dataset_npz": str(npz_out),
            },
        }
    )
    _write_json(report_out, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
