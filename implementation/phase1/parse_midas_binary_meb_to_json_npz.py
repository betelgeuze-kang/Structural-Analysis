#!/usr/bin/env python3
"""Partial decoder for MIDAS binary .meb/.mmbx/.mcb containers.

Current scope:
- inspect MBDG/DB-like binary layout
- extract table-directory inventory rows
- infer in-file payload spans from low-24-bit metadata candidates
- derive heuristic XY preview candidates from xVPNT payload blocks when available

This does not claim full topology reconstruction yet, but it produces reusable
inventory artifacts that can be surfaced in viewer/catalog flows.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import struct

import numpy as np


REASONS = {
    "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY": "binary meb directory inventory and heuristic geometry preview extracted",
    "PASS_TABLE_DIRECTORY_ONLY": "binary meb directory inventory extracted but no stable geometry preview was inferred",
    "ERR_MISSING_INPUT": "input meb file is missing",
    "ERR_UNRECOGNIZED_LAYOUT": "binary meb layout is not recognized by the current decoder",
}

STRUCTURAL_TOKEN_PRIORITY = [
    "__DBMS_DATA__",
    "GUID",
    "UNIT",
    "NODE",
    "ELEM",
    "MATL",
    "SECT",
    "THIK",
    "PLAN",
    "STOR",
    "FGRP",
    "DSEC",
    "MDUL",
    "GRND",
    "MBTP",
    "MEMB",
    "PONT",
    "CURV",
    "xUNIT",
    "xMATL",
    "xSECT",
    "xTHIK",
    "xPLAN",
    "xSTOR",
    "xFGRP",
    "xDSEC",
    "xMDUL",
    "xGRND",
    "xMBTP",
    "xMEMB",
]
TABLE_PATTERN = re.compile(rb"((?:x[A-Z0-9]{3,4})|(?:[A-Z][A-Z0-9]{3}))\x00")
MCVL_TABLE_PATTERN = re.compile(r"(?:x[A-Z0-9_]{3}|[A-Z][A-Z0-9_]{3})")


def _unique_preserve(rows: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row in seen:
            continue
        seen.add(row)
        out.append(row)
    return out


def _safe_ascii_words(data: bytes, *, limit: int = 24) -> list[str]:
    words = [
        token.decode("ascii", errors="ignore")
        for token in re.findall(rb"[ -~]{4,40}", data)
    ]
    return _unique_preserve(words)[:limit]


def _inspect_meb(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    magic_bytes = data[:4]
    magic_ascii = magic_bytes.decode("ascii", errors="ignore")
    ascii_tokens = [
        token.decode("ascii", errors="ignore")
        for token in re.findall(rb"[A-Za-z_][A-Za-z0-9_]{3,15}", data)
    ]
    filtered_tokens = _unique_preserve(
        [
            token
            for token in ascii_tokens
            if (
                token == "__DBMS_DATA__"
                or token == "GUID"
                or (token.startswith("x") and token[1:].isupper())
                or token.isupper()
            )
        ]
    )
    structural_tokens = [token for token in filtered_tokens if token in STRUCTURAL_TOKEN_PRIORITY]
    layout_family = "UNKNOWN"
    scaffold_ready = False
    if magic_ascii == "MBDG" and "__DBMS_DATA__" in filtered_tokens:
        layout_family = "MBDG_DB_CONTAINER"
        scaffold_ready = len(structural_tokens) >= 4
    elif magic_ascii == "MCVL":
        layout_family = "MCVL_TABLE_CONTAINER"
        scaffold_ready = True
    return {
        "input_path": str(path),
        "size_bytes": int(len(data)),
        "magic_ascii": magic_ascii,
        "magic_hex": magic_bytes.hex(),
        "layout_family": layout_family,
        "dbms_marker_present": "__DBMS_DATA__" in filtered_tokens,
        "table_token_rows": filtered_tokens[:64],
        "structural_token_rows": structural_tokens,
        "scaffold_ready": scaffold_ready,
    }


def _iter_table_entries(data: bytes) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for match in TABLE_PATTERN.finditer(data):
        pos = int(match.start())
        if pos + 20 > len(data):
            continue
        chunk = data[pos : pos + 20]
        table_name = chunk[:8].split(b"\0", 1)[0].decode("ascii", errors="ignore")
        if not (
            table_name.startswith("x")
            or (len(table_name) == 4 and table_name[:1].isalpha() and table_name.upper() == table_name)
        ):
            continue
        word1, word2, word3 = struct.unpack("<III", chunk[8:20])
        rows.append(
            {
                "table_name": table_name,
                "directory_position": pos,
                "entry_bytes_hex": chunk.hex(),
                "metadata_words_hex": [hex(word1), hex(word2), hex(word3)],
                "metadata_words_uint32": [int(word1), int(word2), int(word3)],
                "candidate_low24_data_position": int(word1 & 0x00FFFFFF),
                "directory_sentinel": table_name in {"x500", "x700"},
            }
        )

    rows.sort(key=lambda row: int(row["directory_position"]))
    block_index = -1
    previous_position: int | None = None
    for row in rows:
        position = int(row["directory_position"])
        if previous_position is None or position - previous_position > 40:
            block_index += 1
        row["directory_block_index"] = block_index
        previous_position = position
    return rows


def _iter_mcvl_table_entries(data: bytes) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if len(data) < 40:
        return rows
    directory_start = struct.unpack_from("<I", data, 12)[0]
    if directory_start <= 0 or directory_start >= len(data):
        directory_start = 20
    position = int(directory_start)
    while position + 20 <= len(data):
        token_bytes = data[position : position + 4]
        token = token_bytes.decode("ascii", errors="ignore")
        if not MCVL_TABLE_PATTERN.fullmatch(token):
            break
        word0, word1, word2, word3 = struct.unpack_from("<IIII", data, position + 4)
        rows.append(
            {
                "table_name": token,
                "directory_position": int(position),
                "entry_bytes_hex": data[position : position + 20].hex(),
                "metadata_words_hex": [hex(word0), hex(word1), hex(word2), hex(word3)],
                "metadata_words_uint32": [int(word0), int(word1), int(word2), int(word3)],
                "candidate_low24_data_position": int(len(data) + 1),
                "directory_sentinel": False,
                "mcvl_hint_word0": int(word0),
                "mcvl_hint_range_start": int(word1),
                "mcvl_hint_range_end": int(word2),
                "mcvl_hint_word3": int(word3),
            }
        )
        position += 20
    for index, row in enumerate(rows):
        row["directory_block_index"] = 0
        row["mcvl_directory_index"] = index
    return rows


def _plausible_f64_rows(data: bytes, *, limit: int = 128) -> list[dict[str, object]]:
    count = len(data) // 8
    if count <= 0:
        return []
    doubles = struct.unpack("<" + "d" * count, data[: count * 8])
    rows: list[dict[str, object]] = []
    for index, value in enumerate(doubles):
        if not math.isfinite(value):
            continue
        if abs(value) <= 1e-3 or abs(value) >= 1e3:
            continue
        rows.append(
            {
                "byte_offset": int(index * 8),
                "value": round(float(value), 6),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _extract_xy_preview(data: bytes) -> dict[str, object]:
    count = len(data) // 8
    if count < 4:
        return {
            "mode": "heuristic_xy_segment_preview",
            "ready": False,
            "candidate_segments_xy": [],
            "candidate_points_xy": [],
            "candidate_segment_count": 0,
            "candidate_point_count": 0,
            "bounds": {},
            "note": "xVPNT payload did not expose enough plausible coordinate quads",
        }
    doubles = struct.unpack("<" + "d" * count, data[: count * 8])
    segments: list[dict[str, object]] = []
    seen_segments: set[tuple[float, float, float, float]] = set()
    for index in range(len(doubles) - 3):
        quad = doubles[index : index + 4]
        if all(math.isfinite(value) and 1e-3 < abs(value) < 1e3 for value in quad):
            rounded = tuple(round(float(value), 6) for value in quad)
            if rounded not in seen_segments:
                seen_segments.add(rounded)
                segments.append(
                    {
                        "byte_offset": int(index * 8),
                        "x1": rounded[0],
                        "y1": rounded[1],
                        "x2": rounded[2],
                        "y2": rounded[3],
                    }
                )

    points: list[list[float]] = []
    seen_points: set[tuple[float, float]] = set()
    for row in segments:
        for point in ((float(row["x1"]), float(row["y1"])), (float(row["x2"]), float(row["y2"]))):
            rounded = (round(point[0], 6), round(point[1], 6))
            if rounded in seen_points:
                continue
            seen_points.add(rounded)
            points.append([rounded[0], rounded[1]])

    bounds: dict[str, float] = {}
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bounds = {
            "min_x": round(min(xs), 6),
            "max_x": round(max(xs), 6),
            "min_y": round(min(ys), 6),
            "max_y": round(max(ys), 6),
        }

    return {
        "mode": "heuristic_xy_segment_preview",
        "ready": bool(segments),
        "candidate_segments_xy": segments,
        "candidate_points_xy": points,
        "candidate_segment_count": int(len(segments)),
        "candidate_point_count": int(len(points)),
        "bounds": bounds,
        "note": "xVPNT payload에서 연속 double quad를 xy segment 후보로 추출한 heuristic preview입니다.",
    }


def _extract_embedded_ascii_block(data: bytes, marker: str, *, next_markers: list[str]) -> str:
    marker_bytes = marker.encode("ascii")
    start = data.find(marker_bytes)
    if start < 0:
        return ""
    end = len(data)
    for next_marker in next_markers:
        next_bytes = next_marker.encode("ascii")
        next_pos = data.find(next_bytes, start + len(marker_bytes))
        if next_pos > start:
            end = min(end, next_pos)
    generic_next = re.search(rb"(?:\r?\n)\*[A-Z_][A-Z0-9_]*", data[start + len(marker_bytes) :])
    if generic_next is not None:
        next_pos = start + len(marker_bytes) + int(generic_next.start())
        if next_pos > start:
            end = min(end, next_pos)
    block = data[start:end].decode("latin-1", errors="ignore")
    return block.replace("\r", "")


def _extract_embedded_ascii_block_near_positions(
    data: bytes,
    marker: str,
    *,
    next_markers: list[str],
    anchor_positions: list[int],
    lookbehind_bytes: int = 4096,
    lookahead_bytes: int = 160000,
) -> tuple[str, dict[str, int]]:
    marker_bytes = marker.encode("ascii")
    if not anchor_positions:
        return "", {}
    for anchor in sorted({max(0, int(position)) for position in anchor_positions}):
        window_start = max(0, anchor - max(0, int(lookbehind_bytes)))
        window_end = min(len(data), anchor + max(4096, int(lookahead_bytes)))
        if window_end <= window_start:
            continue
        window = data[window_start:window_end]
        local_pos = window.find(marker_bytes)
        if local_pos < 0:
            continue
        block = _extract_embedded_ascii_block(window[local_pos:], marker, next_markers=next_markers)
        if block:
            return block, {
                "anchor_directory_position": int(anchor),
                "window_start_byte": int(window_start + local_pos),
                "window_end_byte": int(window_end),
            }
    return "", {}


def _parse_ascii_numeric_row(line: str) -> list[float]:
    cleaned = line.strip().replace("\x00", "")
    if not cleaned or cleaned.startswith("*"):
        return []
    values: list[float] = []
    for token in cleaned.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            return []
    return values


def _project_xyz_geometry(
    candidate_points_xyz: list[list[float]],
    candidate_segments_xyz: list[tuple[list[float], list[float]]],
) -> dict[str, object]:
    if not candidate_points_xyz:
        return {}

    xs = [float(point[0]) for point in candidate_points_xyz]
    ys = [float(point[1]) for point in candidate_points_xyz]
    zs = [float(point[2]) for point in candidate_points_xyz]
    projection_options = [
        ("XY", xs, ys, 0, 1),
        ("XZ", xs, zs, 0, 2),
        ("YZ", ys, zs, 1, 2),
    ]
    projection_label, proj_x, proj_y, axis_a, axis_b = max(
        projection_options,
        key=lambda row: (max(row[1]) - min(row[1])) * (max(row[2]) - min(row[2])),
    )
    candidate_points_xy = [[round(float(point[axis_a]), 6), round(float(point[axis_b]), 6)] for point in candidate_points_xyz]
    bounds = {
        "min_x": round(min(proj_x), 6),
        "max_x": round(max(proj_x), 6),
        "min_y": round(min(proj_y), 6),
        "max_y": round(max(proj_y), 6),
    }

    candidate_segments_xy: list[dict[str, float]] = []
    seen_segments: set[tuple[float, float, float, float]] = set()
    for start_xyz, end_xyz in candidate_segments_xyz:
        x1 = round(float(start_xyz[axis_a]), 6)
        y1 = round(float(start_xyz[axis_b]), 6)
        x2 = round(float(end_xyz[axis_a]), 6)
        y2 = round(float(end_xyz[axis_b]), 6)
        if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
            continue
        segment_key = (x1, y1, x2, y2)
        reverse_key = (x2, y2, x1, y1)
        if segment_key in seen_segments or reverse_key in seen_segments:
            continue
        seen_segments.add(segment_key)
        candidate_segments_xy.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    axis_spans = {
        "X": round(max(xs) - min(xs), 6),
        "Y": round(max(ys) - min(ys), 6),
        "Z": round(max(zs) - min(zs), 6),
    }
    return {
        "projection_label": projection_label,
        "candidate_points_xy": candidate_points_xy,
        "candidate_segments_xy": candidate_segments_xy,
        "bounds": bounds,
        "axis_spans": axis_spans,
    }


def _build_table_local_ascii_preview(
    point_block: str,
    member_add_block: str,
    *,
    source_table: str,
    anchor_table_names: list[str],
    search_context: dict[str, int] | None = None,
) -> dict[str, object]:
    search_context = search_context or {}
    points_by_id: dict[int, list[float]] = {}
    for line in point_block.splitlines()[1:]:
        values = _parse_ascii_numeric_row(line)
        if len(values) < 5:
            continue
        point_id = int(values[0])
        x = float(values[2])
        y = float(values[3])
        z = float(values[4])
        if not all(math.isfinite(value) for value in (x, y, z)):
            continue
        if max(abs(x), abs(y), abs(z)) > 1e6:
            continue
        points_by_id[point_id] = [round(x, 6), round(y, 6), round(z, 6)]

    if len(points_by_id) < 4:
        return {}

    candidate_segments_xyz: list[tuple[list[float], list[float]]] = []
    resolved_member_path_samples: list[list[int]] = []
    participating_point_ids: set[int] = set()
    topology_edges: set[tuple[int, int]] = set()
    member_path_count = 0
    resolved_member_path_count = 0
    member_reference_count = 0
    resolved_member_reference_count = 0
    if member_add_block:
        lines = [line for line in member_add_block.splitlines()[1:] if line.strip()]
        index = 0
        while index < len(lines):
            header_values = _parse_ascii_numeric_row(lines[index])
            index += 1
            if len(header_values) < 2:
                continue
            node_count = max(0, int(header_values[1]))
            if node_count < 2 or index >= len(lines):
                continue
            node_values = _parse_ascii_numeric_row(lines[index])
            index += 1
            node_ids = [int(value) for value in node_values[:node_count]]
            if len(node_ids) < 2:
                continue
            member_path_count += 1
            member_reference_count += len(node_ids)
            resolved_points = [points_by_id.get(node_id) for node_id in node_ids]
            resolved_pairs = [
                (node_id, point)
                for node_id, point in zip(node_ids, resolved_points)
                if isinstance(point, list)
            ]
            resolved_points = [point for _, point in resolved_pairs]
            if len(resolved_points) < 2:
                continue
            resolved_member_path_count += 1
            resolved_member_reference_count += len(resolved_points)
            resolved_node_ids = [node_id for node_id, _ in resolved_pairs]
            participating_point_ids.update(resolved_node_ids)
            if len(resolved_member_path_samples) < 5:
                resolved_member_path_samples.append([int(node_id) for node_id in resolved_node_ids])
            for (start_id, start_xyz), (end_id, end_xyz) in zip(resolved_pairs[:-1], resolved_pairs[1:]):
                candidate_segments_xyz.append((start_xyz, end_xyz))
                edge = tuple(sorted((int(start_id), int(end_id))))
                if edge[0] != edge[1]:
                    topology_edges.add(edge)

    candidate_points_xyz = [points_by_id[key] for key in sorted(points_by_id.keys())]
    projected = _project_xyz_geometry(candidate_points_xyz, candidate_segments_xyz)
    if not projected:
        return {}

    graph_neighbors: dict[int, set[int]] = {point_id: set() for point_id in participating_point_ids}
    for start_id, end_id in topology_edges:
        graph_neighbors.setdefault(int(start_id), set()).add(int(end_id))
        graph_neighbors.setdefault(int(end_id), set()).add(int(start_id))
    graph_visited: set[int] = set()
    component_count = 0
    for point_id in sorted(graph_neighbors.keys()):
        if point_id in graph_visited:
            continue
        component_count += 1
        stack = [point_id]
        while stack:
            current = stack.pop()
            if current in graph_visited:
                continue
            graph_visited.add(current)
            stack.extend(sorted(graph_neighbors.get(current, set()) - graph_visited))
    degree_by_point = {point_id: len(graph_neighbors.get(point_id, set())) for point_id in graph_neighbors}
    dangling_point_count = int(sum(1 for degree in degree_by_point.values() if degree == 1))
    junction_point_count = int(sum(1 for degree in degree_by_point.values() if degree >= 3))
    isolated_preview_point_count = int(len(points_by_id) - len(participating_point_ids))
    missing_member_path_count = int(max(0, member_path_count - resolved_member_path_count))
    missing_member_reference_count = int(max(0, member_reference_count - resolved_member_reference_count))
    payload_exact_topology_ready = bool(
        member_path_count > 0
        and resolved_member_path_count == member_path_count
        and member_reference_count > 0
        and resolved_member_reference_count == member_reference_count
    )
    topology_preview_ready = bool(
        member_path_count > 0
        and resolved_member_path_count == member_path_count
        and member_reference_count > 0
        and resolved_member_reference_count == member_reference_count
        and len(topology_edges) >= 3
        and len(participating_point_ids) >= 4
        and isolated_preview_point_count == 0
    )
    exact_topology_candidate = bool(
        payload_exact_topology_ready
        and topology_preview_ready
        and missing_member_path_count == 0
        and missing_member_reference_count == 0
    )
    exact_topology_promoted = False
    payload_exactness_label = (
        "payload-exact member-add topology preview"
        if payload_exact_topology_ready
        else "table-local preview"
    )
    topology_readiness_label = (
        "payload-exact member-add topology preview"
        if topology_preview_ready
        else "table-local preview"
    )

    note = (
        "embedded ASCII *POINT"
        + ("/*MEMBER_ADD" if candidate_segments_xyz else "")
        + " 블록을 이용해 만든 table-local unverified preview입니다. "
        + "member topology는 explicit consecutive path만 사용하고, implied loop closure는 추가하지 않았습니다."
    )
    if payload_exact_topology_ready:
        note += " embedded payload 내부의 *POINT/*MEMBER_ADD reference는 exact하게 해석됐지만, full-file verified topology를 주장하지는 않습니다."
    if topology_preview_ready:
        note += " 모든 member-add path reference가 point set에 해석돼 payload-exact member-add preview candidate로 승격 가능합니다."
    if exact_topology_candidate:
        note += " payload 내부 기준으로는 exact recovered topology candidate evidence도 함께 확보됐습니다."
    if search_context:
        note = (
            "PONT/CURV/MEMB directory_position 주변 window에서 찾은 "
            + note
        )

    preview = {
        "mode": "table_local_ascii_preview",
        "ready": False,
        "candidate_segments_xy": projected.get("candidate_segments_xy", []),
        "candidate_points_xy": projected.get("candidate_points_xy", []),
        "candidate_points_xyz": candidate_points_xyz,
        "candidate_segment_count": int(len(projected.get("candidate_segments_xy", []))),
        "candidate_point_count": int(len(projected.get("candidate_points_xy", []))),
        "bounds": projected.get("bounds", {}) if isinstance(projected.get("bounds"), dict) else {},
        "source_table": source_table,
        "projection_label": str(projected.get("projection_label", "") or ""),
        "anchor_table_names": anchor_table_names,
        "member_path_count": int(member_path_count),
        "resolved_member_path_count": int(resolved_member_path_count),
        "member_path_resolution_rate": round(
            float(resolved_member_path_count) / float(member_path_count),
            3,
        )
        if member_path_count
        else 0.0,
        "member_reference_count": int(member_reference_count),
        "resolved_member_reference_count": int(resolved_member_reference_count),
        "missing_member_path_count": int(missing_member_path_count),
        "missing_member_reference_count": int(missing_member_reference_count),
        "member_reference_resolution_rate": round(
            float(resolved_member_reference_count) / float(member_reference_count),
            3,
        )
        if member_reference_count
        else 0.0,
        "payload_exact_topology_ready": payload_exact_topology_ready,
        "payload_exactness_label": payload_exactness_label,
        "topology_grounding_label": "explicit_member_add_paths" if topology_edges else "point_cloud_only",
        "topology_preview_ready": topology_preview_ready,
        "topology_readiness_label": topology_readiness_label,
        "exact_topology_candidate": exact_topology_candidate,
        "exact_topology_promoted": exact_topology_promoted,
        "topology_node_count": int(len(participating_point_ids)),
        "topology_edge_count": int(len(topology_edges)),
        "topology_component_count": int(component_count),
        "dangling_point_count": int(dangling_point_count),
        "junction_point_count": int(junction_point_count),
        "isolated_preview_point_count": int(isolated_preview_point_count),
        "resolved_member_path_samples": resolved_member_path_samples,
        "axis_spans": projected.get("axis_spans", {}) if isinstance(projected.get("axis_spans"), dict) else {},
        "note": note,
    }
    if search_context:
        preview.update(search_context)
    return preview


def _extract_table_local_ascii_preview(data: bytes, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    anchor_positions = sorted(
        {
            int(row.get("directory_position", 0) or 0)
            for row in (rows or [])
            if str(row.get("table_name", "") or "") in {"PONT", "CURV", "MEMB"}
        }
    )
    for anchor in anchor_positions:
        point_block, search_context = _extract_embedded_ascii_block_near_positions(
            data,
            "*POINT",
            next_markers=["*CURVE", "*MEMBER_ADD", "*MEMBER"],
            anchor_positions=[anchor],
        )
        if not point_block:
            continue
        member_add_block, member_search_context = _extract_embedded_ascii_block_near_positions(
            data,
            "*MEMBER_ADD",
            next_markers=["*ENDDATA", "*LOAD", "*BOUND", "*MASS"],
            anchor_positions=[anchor],
        )
        if member_search_context:
            search_context.update(
                {
                    "member_window_start_byte": int(member_search_context.get("window_start_byte", 0)),
                    "member_window_end_byte": int(member_search_context.get("window_end_byte", 0)),
                }
            )
        preview = _build_table_local_ascii_preview(
            point_block,
            member_add_block,
            source_table="ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD",
            anchor_table_names=["PONT", "CURV", "MEMB", "*POINT", *([] if not member_add_block else ["*MEMBER_ADD"])],
            search_context=search_context,
        )
        if preview:
            return preview

    point_block = _extract_embedded_ascii_block(
        data,
        "*POINT",
        next_markers=["*CURVE", "*MEMBER_ADD", "*MEMBER"],
    )
    if not point_block:
        return {}

    member_add_block = _extract_embedded_ascii_block(
        data,
        "*MEMBER_ADD",
        next_markers=["*ENDDATA", "*LOAD", "*BOUND", "*MASS"],
    )
    return _build_table_local_ascii_preview(
        point_block,
        member_add_block,
        source_table="ASCII:*POINT/*MEMBER_ADD",
        anchor_table_names=["*POINT", *([] if not member_add_block else ["*MEMBER_ADD"])],
    )


def _extract_raw_xyz_preview(
    data: bytes,
    *,
    scan_bytes: int = 250_000,
    max_abs: float = 500.0,
    cluster_gap_bytes: int = 1024,
    min_cluster_points: int = 12,
    min_axis_span: float = 20.0,
    note_prefix: str = "Raw double scan",
) -> dict[str, object]:
    limit = min(len(data), max(256, int(scan_bytes)))
    candidate_rows: list[tuple[int, tuple[float, float, float]]] = []
    seen_points: set[tuple[float, float, float]] = set()
    for offset in range(0, max(0, limit - 24), 8):
        values = struct.unpack("<ddd", data[offset : offset + 24])
        if not all(math.isfinite(value) for value in values):
            continue
        if max(abs(value) for value in values) > max_abs:
            continue
        if sum(abs(value) > 1e-5 for value in values) < 2:
            continue
        point = tuple(round(float(value), 6) for value in values)
        if point in seen_points:
            continue
        seen_points.add(point)
        candidate_rows.append((offset, point))

    if not candidate_rows:
        return {
            "mode": "heuristic_xyz_point_scan",
            "ready": False,
            "candidate_segments_xy": [],
            "candidate_points_xy": [],
            "candidate_segment_count": 0,
            "candidate_point_count": 0,
            "bounds": {},
            "source_table": "raw_f64_xyz_scan",
            "projection_label": "",
            "note": f"{note_prefix}에서 안정적인 xyz 후보를 찾지 못했습니다.",
        }

    clusters: list[list[tuple[int, tuple[float, float, float]]]] = []
    current: list[tuple[int, tuple[float, float, float]]] = []
    for row in candidate_rows:
        if not current or row[0] - current[-1][0] <= cluster_gap_bytes:
            current.append(row)
        else:
            clusters.append(current)
            current = [row]
    if current:
        clusters.append(current)

    def _cluster_score(cluster: list[tuple[int, tuple[float, float, float]]]) -> float:
        xs = [row[1][0] for row in cluster]
        ys = [row[1][1] for row in cluster]
        zs = [row[1][2] for row in cluster]
        spans = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        return float(len(cluster)) * max(spans)

    best_cluster = max(clusters, key=_cluster_score)
    points_xyz = [row[1] for row in best_cluster]
    if len(points_xyz) < min_cluster_points:
        return {
            "mode": "heuristic_xyz_point_scan",
            "ready": False,
            "candidate_segments_xy": [],
            "candidate_points_xy": [],
            "candidate_segment_count": 0,
            "candidate_point_count": 0,
            "bounds": {},
            "source_table": "raw_f64_xyz_scan",
            "projection_label": "",
            "note": f"{note_prefix} 후보는 있었지만 안정적인 cluster 크기에 못 미쳤습니다.",
        }

    xs = [point[0] for point in points_xyz]
    ys = [point[1] for point in points_xyz]
    zs = [point[2] for point in points_xyz]
    cluster_spans = (
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    )
    if max(cluster_spans) < min_axis_span:
        return {
            "mode": "heuristic_xyz_point_scan",
            "ready": False,
            "candidate_segments_xy": [],
            "candidate_points_xy": [],
            "candidate_segment_count": 0,
            "candidate_point_count": 0,
            "bounds": {},
            "source_table": "raw_f64_xyz_scan",
            "projection_label": "",
            "note": f"{note_prefix} candidate cluster가 있었지만 span이 너무 작아 preview로 쓰지 않았습니다.",
        }
    projection_options = [
        ("XY", xs, ys),
        ("XZ", xs, zs),
        ("YZ", ys, zs),
    ]
    projection_label, proj_x, proj_y = max(
        projection_options,
        key=lambda row: (max(row[1]) - min(row[1])) * (max(row[2]) - min(row[2])),
    )
    points_xy = [[round(x, 6), round(y, 6)] for x, y in zip(proj_x, proj_y)]
    bounds = {
        "min_x": round(min(proj_x), 6),
        "max_x": round(max(proj_x), 6),
        "min_y": round(min(proj_y), 6),
        "max_y": round(max(proj_y), 6),
    }
    return {
        "mode": "heuristic_xyz_point_scan",
        "ready": False,
        "candidate_segments_xy": [],
        "candidate_points_xy": points_xy,
        "candidate_segment_count": 0,
        "candidate_point_count": int(len(points_xy)),
        "bounds": bounds,
        "source_table": "raw_f64_xyz_scan",
        "projection_label": projection_label,
        "note": f"{note_prefix}에서 가장 밀집된 xyz cluster를 {projection_label} 평면으로 투영한 unverified preview입니다.",
    }


def _extract_sparse_window_xyz_preview(
    data: bytes,
    *,
    window_bytes: int = 32768,
    step_bytes: int = 8192,
    max_abs: float = 500.0,
    cluster_gap_bytes: int = 512,
    min_cluster_points: int = 4,
    min_axis_span: float = 0.1,
    max_axis_span: float = 5.0,
    note_prefix: str = "Payload-local window scan",
) -> dict[str, object]:
    if len(data) < 24:
        return {}
    window_bytes = max(4096, int(window_bytes))
    step_bytes = max(1024, int(step_bytes))
    best_preview: dict[str, object] = {}
    best_score = -1.0
    max_start = max(0, len(data) - window_bytes)
    for start in range(0, max_start + step_bytes, step_bytes):
        end = min(len(data), start + window_bytes)
        candidate_rows: list[tuple[int, tuple[float, float, float]]] = []
        seen_points: set[tuple[float, float, float]] = set()
        for offset in range(start, max(start, end - 24), 8):
            values = struct.unpack("<ddd", data[offset : offset + 24])
            if not all(math.isfinite(value) for value in values):
                continue
            if max(abs(value) for value in values) > max_abs:
                continue
            if sum(abs(value) > 1e-5 for value in values) < 2:
                continue
            point = tuple(round(float(value), 6) for value in values)
            if point in seen_points:
                continue
            seen_points.add(point)
            candidate_rows.append((offset, point))
        if len(candidate_rows) < min_cluster_points:
            continue

        clusters: list[list[tuple[int, tuple[float, float, float]]]] = []
        current: list[tuple[int, tuple[float, float, float]]] = []
        for row in candidate_rows:
            if not current or row[0] - current[-1][0] <= cluster_gap_bytes:
                current.append(row)
            else:
                clusters.append(current)
                current = [row]
        if current:
            clusters.append(current)
        if not clusters:
            continue

        best_cluster = max(clusters, key=len)
        points_xyz = [row[1] for row in best_cluster]
        if len(points_xyz) < min_cluster_points:
            continue
        xs = [point[0] for point in points_xyz]
        ys = [point[1] for point in points_xyz]
        zs = [point[2] for point in points_xyz]
        axis_spans = {
            "X": max(xs) - min(xs),
            "Y": max(ys) - min(ys),
            "Z": max(zs) - min(zs),
        }
        max_span = max(axis_spans.values(), default=0.0)
        if max_span < min_axis_span or max_span > max_axis_span:
            continue

        projection_options = [
            ("XY", xs, ys),
            ("XZ", xs, zs),
            ("YZ", ys, zs),
        ]
        projection_label, proj_x, proj_y = max(
            projection_options,
            key=lambda row: (max(row[1]) - min(row[1])) * (max(row[2]) - min(row[2])),
        )
        points_xy = [[round(x, 6), round(y, 6)] for x, y in zip(proj_x, proj_y)]
        area_score = (max(proj_x) - min(proj_x)) * (max(proj_y) - min(proj_y))
        preview_score = float(len(points_xy)) * float(area_score)
        if preview_score <= best_score:
            continue

        best_score = preview_score
        best_preview = {
            "mode": "sparse_local_xyz_point_scan",
            "ready": False,
            "candidate_segments_xy": [],
            "candidate_points_xy": points_xy,
            "candidate_points_xyz": [[round(v, 6) for v in point] for point in points_xyz],
            "candidate_segment_count": 0,
            "candidate_point_count": int(len(points_xy)),
            "bounds": {
                "min_x": round(min(proj_x), 6),
                "max_x": round(max(proj_x), 6),
                "min_y": round(min(proj_y), 6),
                "max_y": round(max(proj_y), 6),
            },
            "source_table": "windowed_f64_xyz_scan",
            "projection_label": projection_label,
            "window_start_byte": int(start),
            "window_end_byte": int(end),
            "cluster_start_byte": int(best_cluster[0][0]),
            "cluster_end_byte": int(best_cluster[-1][0] + 24),
            "axis_spans": {key: round(float(value), 6) for key, value in axis_spans.items()},
            "note": (
                f"{note_prefix}에서 가장 조밀한 local xyz cluster를 {projection_label} 평면으로 투영한 "
                "unverified sparse preview입니다."
            ),
        }
    return best_preview


def _extract_mcvl_node_hint_preview(
    data: bytes,
    rows: list[dict[str, object]],
    *,
    stride_bytes: int = 32,
    max_abs: float = 500.0,
    min_scalar_count: int = 9,
    min_point_count: int = 4,
    min_axis_span: float = 20.0,
) -> dict[str, object]:
    node_row = next((row for row in rows if str(row.get("table_name", "") or "") == "NODE"), None)
    elem_row = next((row for row in rows if str(row.get("table_name", "") or "") == "ELEM"), None)
    if not isinstance(node_row, dict):
        return {}

    scalar_rows = _scan_mcvl_node_scalar_rows(
        data,
        node_row,
        stride_bytes=stride_bytes,
        max_abs=max_abs,
    )
    if len(scalar_rows) < min_scalar_count:
        return {}

    range_start = int(node_row.get("mcvl_hint_range_start", 0) or 0)
    range_end = int(node_row.get("mcvl_hint_range_end", 0) or 0)

    def _build_candidate(phase: int) -> dict[str, object]:
        candidate_points_xyz: list[list[float]] = []
        candidate_point_sources: list[list[dict[str, object]]] = []
        selected_phase_record_windows: list[list[int]] = []
        selected_phase_lane_sequences: list[list[int]] = []
        for index in range(phase, len(scalar_rows) - 2, 3):
            triplet = scalar_rows[index : index + 3]
            if len(triplet) < 3:
                continue
            point_xyz = [float(triplet[0]["value"]), float(triplet[1]["value"]), float(triplet[2]["value"])]
            candidate_points_xyz.append([round(value, 6) for value in point_xyz])
            candidate_point_sources.append([dict(item) for item in triplet])
            selected_phase_record_windows.append([int(item["record_index"]) for item in triplet])
            selected_phase_lane_sequences.append([int(item["value_index"]) for item in triplet])

        if len(candidate_points_xyz) < min_point_count:
            return {}

        candidate_segments_xyz = [
            (list(candidate_points_xyz[index]), list(candidate_points_xyz[index + 1]))
            for index in range(len(candidate_points_xyz) - 1)
        ]
        projected = _project_xyz_geometry(candidate_points_xyz, candidate_segments_xyz)
        axis_spans = projected.get("axis_spans", {}) if isinstance(projected.get("axis_spans"), dict) else {}
        bounds = projected.get("bounds", {}) if isinstance(projected.get("bounds"), dict) else {}
        area_score = (
            float(bounds.get("max_x", 0.0) or 0.0) - float(bounds.get("min_x", 0.0) or 0.0)
        ) * (
            float(bounds.get("max_y", 0.0) or 0.0) - float(bounds.get("min_y", 0.0) or 0.0)
        )
        return {
            "phase": int(phase),
            "points_xyz": candidate_points_xyz,
            "segments_xyz": candidate_segments_xyz,
            "point_sources": candidate_point_sources,
            "projection_label": str(projected.get("projection_label", "") or ""),
            "projected_points_xy": projected.get("candidate_points_xy", []),
            "projected_segments_xy": projected.get("candidate_segments_xy", []),
            "bounds": bounds,
            "axis_spans": {key: round(float(value), 6) for key, value in axis_spans.items()},
            "score": round(float(area_score) * len(candidate_points_xyz), 6),
            "selected_phase_record_windows": selected_phase_record_windows,
            "selected_phase_lane_sequences": selected_phase_lane_sequences,
        }

    candidates = [_build_candidate(phase) for phase in range(3)]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return {}
    phase_scoreboard = [
        {
            "phase": int(candidate.get("phase", 0) or 0),
            "point_count": int(len(candidate.get("points_xyz", []))),
            "segment_count": int(len(candidate.get("segments_xyz", []))),
            "projection_label": str(candidate.get("projection_label", "") or ""),
            "score": round(float(candidate.get("score", 0.0) or 0.0), 6),
        }
        for candidate in candidates
    ]
    best = max(candidates, key=lambda item: (float(item.get("score", 0.0)), len(item.get("points_xyz", []))))
    axis_spans = best.get("axis_spans", {}) if isinstance(best.get("axis_spans"), dict) else {}
    if max((float(value) for value in axis_spans.values()), default=0.0) < min_axis_span:
        return {}

    projected_points_xy = best.get("projected_points_xy", [])
    projected_segments_xy = best.get("projected_segments_xy", [])
    bounds = best.get("bounds", {}) if isinstance(best.get("bounds"), dict) else {}

    elem_start = int(elem_row.get("mcvl_hint_range_start", 0) or 0) if isinstance(elem_row, dict) else 0
    elem_end = int(elem_row.get("mcvl_hint_range_end", 0) or 0) if isinstance(elem_row, dict) else 0
    return {
        "mode": "mcvl_node_hint_preview",
        "ready": False,
        "candidate_segments_xy": projected_segments_xy,
        "candidate_points_xy": projected_points_xy,
        "candidate_points_xyz": best.get("points_xyz", []),
        "candidate_segments_xyz": best.get("segments_xyz", []),
        "candidate_point_sources": best.get("point_sources", []),
        "candidate_segment_count": int(len(projected_segments_xy)),
        "candidate_point_count": int(len(projected_points_xy)),
        "candidate_scalar_count": int(len(scalar_rows)),
        "bounds": bounds,
        "source_table": "NODE/ELEM hinted ranges",
        "projection_label": str(best.get("projection_label", "") or ""),
        "hint_stride_bytes": int(stride_bytes),
        "hint_grouping_phase": int(best.get("phase", 0) or 0),
        "hint_node_range": [int(range_start), int(range_end)],
        "hint_elem_range": [int(elem_start), int(elem_end)] if elem_start or elem_end else [],
        "axis_spans": axis_spans,
        "phase_scoreboard": phase_scoreboard,
        "selected_phase_record_windows": best.get("selected_phase_record_windows", []),
        "selected_phase_lane_sequences": best.get("selected_phase_lane_sequences", []),
        "topology_grounding_label": "record_order_polyline",
        "topology_node_count": int(len(best.get("points_xyz", []))),
        "topology_edge_count": int(len(best.get("segments_xyz", []))),
        "note": (
            "MCVL NODE hinted range에서 추출한 sparse scalar를 triplet으로 묶고, "
            "record-order polyline으로 연결한 "
            f"{str(best.get('projection_label', '') or 'XY')} 평면 unverified hint preview입니다. "
            "실제 member connectivity는 아직 복구하지 않았습니다."
        ),
    }


def _scan_mcvl_node_scalar_rows(
    data: bytes,
    node_row: dict[str, object] | None,
    *,
    stride_bytes: int = 32,
    max_abs: float = 500.0,
) -> list[dict[str, object]]:
    if not isinstance(node_row, dict):
        return []
    range_start = int(node_row.get("mcvl_hint_range_start", 0) or 0)
    range_end = int(node_row.get("mcvl_hint_range_end", 0) or 0)
    if range_end <= range_start or range_start <= 0:
        return []

    scalar_rows: list[dict[str, object]] = []
    for record_index in range(range_start, range_end):
        offset = int(record_index * stride_bytes)
        if offset + stride_bytes > len(data):
            break
        chunk = data[offset : offset + stride_bytes]
        doubles = struct.unpack("<dddd", chunk)
        for value_index, value in enumerate(doubles):
            if not math.isfinite(value):
                continue
            if abs(value) <= 1e-6 or abs(value) > max_abs:
                continue
            scalar_rows.append(
                {
                    "record_index": int(record_index),
                    "byte_offset": int(offset),
                    "value_index": int(value_index),
                    "value": round(float(value), 6),
                }
            )
    return scalar_rows


def _extract_mcvl_record_topology_preview(
    data: bytes,
    rows: list[dict[str, object]],
    *,
    stride_bytes: int = 32,
    max_abs: float = 500.0,
    min_point_count: int = 4,
    min_edge_count: int = 3,
) -> dict[str, object]:
    node_row = next((row for row in rows if str(row.get("table_name", "") or "") == "NODE"), None)
    elem_row = next((row for row in rows if str(row.get("table_name", "") or "") == "ELEM"), None)
    if not isinstance(node_row, dict) or not isinstance(elem_row, dict):
        return {}

    node_start = int(node_row.get("mcvl_hint_range_start", 0) or 0)
    node_end = int(node_row.get("mcvl_hint_range_end", 0) or 0)
    elem_start = int(elem_row.get("mcvl_hint_range_start", 0) or 0)
    elem_end = int(elem_row.get("mcvl_hint_range_end", 0) or 0)
    if node_end <= node_start or elem_end <= elem_start or node_start <= 0 or elem_start <= 0:
        return {}

    node_points_by_record: dict[int, list[float]] = {}
    node_source_slots_by_record: dict[int, list[int]] = {}
    for record_index in range(node_start, node_end):
        offset = int(record_index * stride_bytes)
        if offset + stride_bytes > len(data):
            break
        doubles = struct.unpack("<dddd", data[offset : offset + stride_bytes])
        leading_xyz = [float(value) for value in doubles[:3]]
        if not all(math.isfinite(value) and abs(value) <= max_abs for value in leading_xyz):
            continue
        trailing_value = float(doubles[3])
        if not math.isfinite(trailing_value) or abs(trailing_value) > max_abs:
            continue
        node_points_by_record[int(record_index)] = [round(value, 6) for value in leading_xyz]
        node_source_slots_by_record[int(record_index)] = [0, 1, 2]

    if len(node_points_by_record) < min_point_count:
        return {}

    topology_edges: set[tuple[int, int]] = set()
    member_record_count = 0
    resolved_member_record_count = 0
    resolved_reference_count = 0
    member_reference_count = 0
    element_path_samples: list[list[int]] = []
    active_elem_reference_slots: dict[int, int] = {}
    for record_index in range(elem_start, elem_end):
        offset = int(record_index * stride_bytes)
        if offset + stride_bytes > len(data):
            break
        values = struct.unpack("<IIIIIIII", data[offset : offset + stride_bytes])
        path_refs: list[int] = []
        path_slots: list[int] = []
        seen_refs: set[int] = set()
        for slot_index, value in enumerate(values):
            if not (node_start <= int(value) < node_end):
                continue
            member_reference_count += 1
            if int(value) in node_points_by_record:
                resolved_reference_count += 1
            if int(value) in seen_refs:
                continue
            seen_refs.add(int(value))
            if int(value) not in node_points_by_record:
                continue
            path_refs.append(int(value))
            path_slots.append(int(slot_index))
        if len(path_refs) < 2:
            continue
        member_record_count += 1
        resolved_member_record_count += 1
        if len(element_path_samples) < 6:
            element_path_samples.append(list(path_refs))
        for slot in path_slots:
            active_elem_reference_slots[int(slot)] = active_elem_reference_slots.get(int(slot), 0) + 1
        for start_id, end_id in zip(path_refs[:-1], path_refs[1:]):
            if start_id == end_id:
                continue
            topology_edges.add(tuple(sorted((int(start_id), int(end_id)))))

    if len(topology_edges) < min_edge_count:
        return {}

    participating_ids = sorted({point_id for edge in topology_edges for point_id in edge})
    candidate_points_xyz = [node_points_by_record[point_id] for point_id in participating_ids]
    id_to_xyz = {point_id: node_points_by_record[point_id] for point_id in participating_ids}
    candidate_segments_xyz = [
        (list(id_to_xyz[start_id]), list(id_to_xyz[end_id]))
        for start_id, end_id in sorted(topology_edges)
    ]
    projected = _project_xyz_geometry(candidate_points_xyz, candidate_segments_xyz)
    if not projected:
        return {}

    return {
        "mode": "mcvl_record_topology_preview",
        "ready": False,
        "candidate_segments_xy": projected.get("candidate_segments_xy", []),
        "candidate_points_xy": projected.get("candidate_points_xy", []),
        "candidate_points_xyz": candidate_points_xyz,
        "candidate_segments_xyz": candidate_segments_xyz,
        "candidate_segment_count": int(len(projected.get("candidate_segments_xy", []))),
        "candidate_point_count": int(len(projected.get("candidate_points_xy", []))),
        "candidate_node_record_count": int(len(node_points_by_record)),
        "candidate_elem_record_count": int(member_record_count),
        "resolved_member_record_count": int(resolved_member_record_count),
        "member_reference_count": int(member_reference_count),
        "resolved_member_reference_count": int(resolved_reference_count),
        "resolved_member_reference_rate": round(
            float(resolved_reference_count) / float(member_reference_count),
            3,
        )
        if member_reference_count
        else 0.0,
        "candidate_node_record_ids": participating_ids,
        "candidate_node_source_slots": [
            {
                "record_index": int(record_index),
                "slots": node_source_slots_by_record.get(int(record_index), []),
            }
            for record_index in participating_ids[:12]
        ],
        "candidate_elem_reference_slots": [
            {"slot": int(slot), "hit_count": int(hit_count)}
            for slot, hit_count in sorted(active_elem_reference_slots.items(), key=lambda item: (-item[1], item[0]))
        ],
        "candidate_elem_path_samples": element_path_samples,
        "bounds": projected.get("bounds", {}) if isinstance(projected.get("bounds"), dict) else {},
        "source_table": "NODE/ELEM decoded records",
        "projection_label": str(projected.get("projection_label", "") or ""),
        "hint_stride_bytes": int(stride_bytes),
        "hint_node_range": [int(node_start), int(node_end)],
        "hint_elem_range": [int(elem_start), int(elem_end)],
        "axis_spans": projected.get("axis_spans", {}) if isinstance(projected.get("axis_spans"), dict) else {},
        "topology_grounding_label": "record_local_node_elem_paths",
        "topology_preview_ready": True,
        "topology_readiness_label": "record-grounded NODE/ELEM topology preview",
        "exact_topology_candidate": True,
        "exact_topology_promoted": False,
        "topology_node_count": int(len(participating_ids)),
        "topology_edge_count": int(len(topology_edges)),
        "note": (
            "MCVL NODE record-local xyz candidate와 ELEM uint reference를 직접 연결한 "
            f"{str(projected.get('projection_label', '') or 'XY')} 평면 topology-grounded preview입니다. "
            "ELEM path semantics 전체를 복원했다고 주장하지는 않지만, record-local reference connectivity는 hint preview보다 직접적입니다."
        ),
    }


def _summarize_mcvl_node_record_probe(
    data: bytes,
    node_row: dict[str, object] | None,
    *,
    stride_bytes: int = 32,
    max_abs: float = 500.0,
) -> dict[str, object]:
    if not isinstance(node_row, dict):
        return {}
    range_start = int(node_row.get("mcvl_hint_range_start", 0) or 0)
    range_end = int(node_row.get("mcvl_hint_range_end", 0) or 0)
    if range_end <= range_start or range_start <= 0:
        return {}

    counts = {
        "records_with_0_values": 0,
        "records_with_1_value": 0,
        "records_with_2_values": 0,
        "records_with_3plus_values": 0,
    }
    example_rows: list[dict[str, object]] = []
    for record_index in range(range_start, range_end):
        offset = int(record_index * stride_bytes)
        if offset + stride_bytes > len(data):
            break
        values = struct.unpack("<dddd", data[offset : offset + stride_bytes])
        plausible = [round(float(value), 6) for value in values if math.isfinite(value) and abs(value) > 1e-6 and abs(value) < max_abs]
        plausible_count = len(plausible)
        if plausible_count <= 0:
            counts["records_with_0_values"] += 1
        elif plausible_count == 1:
            counts["records_with_1_value"] += 1
        elif plausible_count == 2:
            counts["records_with_2_values"] += 1
        else:
            counts["records_with_3plus_values"] += 1
        if plausible_count >= 2 and len(example_rows) < 6:
            example_rows.append(
                {
                    "record_index": int(record_index),
                    "plausible_count": int(plausible_count),
                    "values": plausible[:4],
                }
            )

    note = (
        "NODE hinted range records mostly expose sparse scalar slots. "
        "Record-local exact xyz decode is not justified yet."
    )
    if counts["records_with_3plus_values"] > 0:
        note = (
            "Some NODE hinted records expose 3+ plausible doubles. "
            "Record-local xyz decode may be feasible as the next exact-decode step."
        )
    return {
        "record_range": [int(range_start), int(range_end)],
        "stride_bytes": int(stride_bytes),
        **counts,
        "example_multi_value_rows": example_rows,
        "note": note,
    }


def _summarize_mcvl_node_reassembly_probe(
    data: bytes,
    node_row: dict[str, object] | None,
    *,
    stride_bytes: int = 32,
    max_abs: float = 500.0,
) -> dict[str, object]:
    scalar_rows = _scan_mcvl_node_scalar_rows(
        data,
        node_row,
        stride_bytes=stride_bytes,
        max_abs=max_abs,
    )
    if len(scalar_rows) < 3:
        return {}

    phase_rows: list[dict[str, object]] = []
    for phase in range(3):
        candidate_count = 0
        cross_record_count = 0
        duplicate_record_count = 0
        unique_lane_sequences: dict[tuple[int, ...], int] = {}
        unique_record_spans: dict[tuple[int, ...], int] = {}
        first_candidate: dict[str, object] | None = None

        for index in range(phase, len(scalar_rows) - 2, 3):
            triplet = scalar_rows[index : index + 3]
            if len(triplet) < 3:
                continue
            candidate_count += 1
            record_window = tuple(int(item["record_index"]) for item in triplet)
            lane_sequence = tuple(int(item["value_index"]) for item in triplet)
            unique_record_spans[record_window] = unique_record_spans.get(record_window, 0) + 1
            unique_lane_sequences[lane_sequence] = unique_lane_sequences.get(lane_sequence, 0) + 1
            if len(set(record_window)) >= 2:
                cross_record_count += 1
            if len(set(record_window)) < 3:
                duplicate_record_count += 1
            if first_candidate is None:
                first_candidate = {
                    "record_window": [int(value) for value in record_window],
                    "lane_sequence": [int(value) for value in lane_sequence],
                    "values": [round(float(item["value"]), 6) for item in triplet],
                }

        if candidate_count <= 0:
            continue
        dominant_lane_sequence, dominant_lane_count = max(
            unique_lane_sequences.items(),
            key=lambda item: (int(item[1]), item[0]),
        )
        dominant_record_window, dominant_record_count = max(
            unique_record_spans.items(),
            key=lambda item: (int(item[1]), item[0]),
        )
        phase_rows.append(
            {
                "phase": int(phase),
                "candidate_triplet_count": int(candidate_count),
                "cross_record_triplet_count": int(cross_record_count),
                "duplicate_record_triplet_count": int(duplicate_record_count),
                "dominant_lane_sequence": [int(value) for value in dominant_lane_sequence],
                "dominant_lane_sequence_count": int(dominant_lane_count),
                "dominant_record_window": [int(value) for value in dominant_record_window],
                "dominant_record_window_count": int(dominant_record_count),
                "first_candidate": first_candidate or {},
            }
        )

    if not phase_rows:
        return {}

    best_phase = max(
        phase_rows,
        key=lambda row: (
            int(row.get("cross_record_triplet_count", 0) or 0),
            int(row.get("candidate_triplet_count", 0) or 0),
            -int(row.get("phase", 0) or 0),
        ),
    )
    candidate_triplet_count = int(best_phase.get("candidate_triplet_count", 0) or 0)
    cross_record_triplet_count = int(best_phase.get("cross_record_triplet_count", 0) or 0)
    cross_record_ratio = round(
        float(cross_record_triplet_count) / float(candidate_triplet_count),
        3,
    ) if candidate_triplet_count else 0.0
    hypothesis_ready = candidate_triplet_count >= 4 and cross_record_triplet_count >= 3
    note = (
        "Cross-record NODE xyz reassembly candidates are visible in the hinted scalar stream, "
        "but this is still probe-level evidence rather than exact xyz recovery."
        if hypothesis_ready
        else "Only sparse cross-record triplet evidence is visible so far; exact NODE xyz recovery is still underdetermined."
    )
    return {
        "records_scanned": int(len({int(row["record_index"]) for row in scalar_rows})),
        "scalar_sample_count": int(len(scalar_rows)),
        "phase_rows": phase_rows,
        "best_phase": int(best_phase.get("phase", 0) or 0),
        "candidate_triplet_count": candidate_triplet_count,
        "cross_record_triplet_count": cross_record_triplet_count,
        "cross_record_triplet_ratio": cross_record_ratio,
        "duplicate_record_triplet_count": int(best_phase.get("duplicate_record_triplet_count", 0) or 0),
        "best_record_window": (
            (best_phase.get("first_candidate", {}) if isinstance(best_phase.get("first_candidate"), dict) else {}).get("record_window", [])
            or best_phase.get("dominant_record_window", [])
        ),
        "best_lane_sequence": (
            (best_phase.get("first_candidate", {}) if isinstance(best_phase.get("first_candidate"), dict) else {}).get("lane_sequence", [])
            or best_phase.get("dominant_lane_sequence", [])
        ),
        "first_candidate": best_phase.get("first_candidate", {}),
        "supports_cross_record_xyz_hypothesis": hypothesis_ready,
        "note": note,
    }


def _summarize_mcvl_scalar_lane_probe(
    data: bytes,
    row: dict[str, object] | None,
    *,
    stride_bytes: int = 32,
    max_abs: float = 500.0,
    small_uint_max: int = 100000,
    sample_limit: int = 8,
) -> dict[str, object]:
    if not isinstance(row, dict):
        return {}
    range_start = int(row.get("mcvl_hint_range_start", 0) or 0)
    range_end = int(row.get("mcvl_hint_range_end", 0) or 0)
    if range_end <= range_start or range_start <= 0:
        return {}

    scalar_lane_counts = [0] * 4
    scalar_lane_patterns: dict[tuple[int, ...], int] = {}
    companion_small_uint_slot_hits: list[list[int]] = [[0] * 8 for _ in range(4)]
    sample_scalar_records: list[dict[str, object]] = []
    records_scanned = 0
    active_scalar_record_count = 0
    single_scalar_record_count = 0
    multi_scalar_record_count = 0

    for record_index in range(range_start, range_end):
        offset = int(record_index * stride_bytes)
        if offset + stride_bytes > len(data):
            break
        values_f64 = struct.unpack("<dddd", data[offset : offset + stride_bytes])
        values_u32 = struct.unpack("<IIIIIIII", data[offset : offset + stride_bytes])
        records_scanned += 1

        active_lanes: list[int] = []
        scalar_values: list[float] = []
        for lane_index, value in enumerate(values_f64):
            if not math.isfinite(value):
                continue
            if abs(value) <= 1e-6 or abs(value) >= max_abs:
                continue
            scalar_lane_counts[lane_index] += 1
            active_lanes.append(int(lane_index))
            scalar_values.append(round(float(value), 6))

        if not active_lanes:
            continue

        active_scalar_record_count += 1
        scalar_lane_patterns[tuple(active_lanes)] = scalar_lane_patterns.get(tuple(active_lanes), 0) + 1
        if len(active_lanes) == 1:
            single_scalar_record_count += 1
        else:
            multi_scalar_record_count += 1

        for lane_index in active_lanes:
            lane_slots = {lane_index * 2, lane_index * 2 + 1}
            for slot_index, value in enumerate(values_u32):
                if slot_index in lane_slots:
                    continue
                if 0 < int(value) < small_uint_max:
                    companion_small_uint_slot_hits[lane_index][slot_index] += 1

        if len(sample_scalar_records) < sample_limit:
            sample_scalar_records.append(
                {
                    "record_index": int(record_index),
                    "active_lanes": [int(value) for value in active_lanes],
                    "scalar_values": scalar_values,
                    "companion_small_uints": [
                        {"slot": int(slot_index), "value_uint32": int(value)}
                        for slot_index, value in enumerate(values_u32)
                        if 0 < int(value) < small_uint_max
                    ],
                }
            )

    dominant_lane_patterns = [
        {
            "lanes": [int(value) for value in lane_pattern],
            "record_count": int(record_count),
        }
        for lane_pattern, record_count in sorted(
            scalar_lane_patterns.items(),
            key=lambda item: (-int(item[1]), len(item[0]), item[0]),
        )[: sample_limit]
    ]
    likely_scalar_lane_indices = [
        int(lane_index)
        for lane_index, hit_count in enumerate(scalar_lane_counts)
        if hit_count > 0
    ]
    companion_probe = [
        {
            "lane": int(lane_index),
            "slot_hits": [int(value) for value in slot_hits],
        }
        for lane_index, slot_hits in enumerate(companion_small_uint_slot_hits)
    ]
    note = (
        "MCVL hinted range was scanned as 4x float64 lanes per 32-byte record to expose sparse scalar placement. "
        "This is structural evidence only, not a verified NODE xyz decode."
    )
    if active_scalar_record_count > 0:
        note += " Active scalar lanes rotate across the 32-byte record and frequently co-occur with small uint fragments in neighboring slots."

    likely_scalar_anchor_slots: list[dict[str, object]] = []
    for lane_index, slot_hits in enumerate(companion_small_uint_slot_hits):
        total_hits = int(sum(slot_hits))
        ranked_slots = [
            {"slot": int(slot_index), "hit_count": int(hit_count)}
            for slot_index, hit_count in sorted(
                enumerate(slot_hits),
                key=lambda item: (-int(item[1]), int(item[0])),
            )
            if int(hit_count) > 0
        ]
        if not ranked_slots:
            continue
        dominant_hit_count = int(ranked_slots[0]["hit_count"])
        likely_scalar_anchor_slots.append(
            {
                "lane": int(lane_index),
                "total_hits": total_hits,
                "dominant_slots": ranked_slots[:3],
                "dominant_slot_confidence": round(float(dominant_hit_count) / float(total_hits), 3) if total_hits else 0.0,
            }
        )

    return {
        "table_name": str(row.get("table_name", "") or ""),
        "record_range": [int(range_start), int(range_end)],
        "stride_bytes": int(stride_bytes),
        "records_scanned": int(records_scanned),
        "active_scalar_record_count": int(active_scalar_record_count),
        "single_scalar_record_count": int(single_scalar_record_count),
        "multi_scalar_record_count": int(multi_scalar_record_count),
        "scalar_lane_counts": [int(value) for value in scalar_lane_counts],
        "likely_scalar_lane_indices": likely_scalar_lane_indices,
        "dominant_scalar_lane_patterns": dominant_lane_patterns,
        "companion_small_uint_slot_hits": companion_probe,
        "likely_scalar_anchor_slots": likely_scalar_anchor_slots,
        "sample_scalar_records": sample_scalar_records,
        "note": note,
    }


def _summarize_mcvl_node_xyz_slot_recovery_probe(
    hint_preview: dict[str, object] | None,
    scalar_probe: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(hint_preview, dict) or not hint_preview.get("candidate_points_xyz"):
        return {}

    record_windows = hint_preview.get("selected_phase_record_windows", [])
    lane_sequences = hint_preview.get("selected_phase_lane_sequences", [])
    point_sources = hint_preview.get("candidate_point_sources", [])
    if not isinstance(record_windows, list) or not isinstance(lane_sequences, list):
        return {}

    anchor_by_lane: dict[int, dict[str, object]] = {}
    if isinstance(scalar_probe, dict):
        for item in scalar_probe.get("likely_scalar_anchor_slots", []):
            if not isinstance(item, dict):
                continue
            lane = int(item.get("lane", -1) or -1)
            if lane < 0:
                continue
            anchor_by_lane[lane] = item

    tuple_count = min(len(record_windows), len(lane_sequences))
    if tuple_count <= 0:
        return {}

    tuple_samples: list[dict[str, object]] = []
    unique_lane_counts: list[int] = []
    record_spans: list[int] = []
    strong_tuple_count = 0
    partial_tuple_count = 0
    three_lane_tuple_count = 0
    repeated_lane_tuple_count = 0
    tight_window_tuple_count = 0
    anchor_supported_tuple_count = 0

    for index in range(tuple_count):
        record_window = record_windows[index]
        lane_sequence = lane_sequences[index]
        if not isinstance(record_window, list) or not isinstance(lane_sequence, list):
            continue
        if not record_window or not lane_sequence:
            continue
        normalized_window = [int(value) for value in record_window]
        normalized_lanes = [int(value) for value in lane_sequence]
        unique_lanes = sorted(set(normalized_lanes))
        unique_lane_count = len(unique_lanes)
        record_span = max(normalized_window) - min(normalized_window)
        unique_lane_counts.append(unique_lane_count)
        record_spans.append(int(record_span))

        if unique_lane_count >= 3:
            three_lane_tuple_count += 1
        if unique_lane_count < len(normalized_lanes):
            repeated_lane_tuple_count += 1
        if record_span <= 3:
            tight_window_tuple_count += 1

        anchor_supported_lanes = 0
        anchor_summary: list[dict[str, object]] = []
        for lane in unique_lanes:
            anchor_item = anchor_by_lane.get(int(lane))
            dominant_slots = []
            dominant_confidence = 0.0
            if isinstance(anchor_item, dict):
                dominant_slots = [
                    {
                        "slot": int(slot_item.get("slot", 0) or 0),
                        "hit_count": int(slot_item.get("hit_count", 0) or 0),
                    }
                    for slot_item in anchor_item.get("dominant_slots", [])[:2]
                    if isinstance(slot_item, dict)
                ]
                dominant_confidence = float(anchor_item.get("dominant_slot_confidence", 0.0) or 0.0)
                anchor_supported_lanes += 1
            anchor_summary.append(
                {
                    "lane": int(lane),
                    "dominant_slots": dominant_slots,
                    "dominant_slot_confidence": round(dominant_confidence, 3),
                }
            )

        if anchor_supported_lanes >= 3:
            anchor_supported_tuple_count += 1

        quality_label = "weak_candidate"
        if unique_lane_count >= 3:
            quality_label = "strong_candidate"
            strong_tuple_count += 1
        elif unique_lane_count == 2:
            quality_label = "partial_candidate"
            partial_tuple_count += 1

        value_triplet = []
        if index < len(point_sources) and isinstance(point_sources[index], list):
            value_triplet = [
                {
                    "record_index": int(item.get("record_index", 0) or 0),
                    "lane": int(item.get("value_index", 0) or 0),
                    "value": round(float(item.get("value", 0.0) or 0.0), 6),
                }
                for item in point_sources[index]
                if isinstance(item, dict)
            ]

        tuple_samples.append(
            {
                "tuple_index": int(index),
                "record_window": normalized_window,
                "lane_sequence": normalized_lanes,
                "unique_lane_count": int(unique_lane_count),
                "record_span": int(record_span),
                "anchor_supported_lane_count": int(anchor_supported_lanes),
                "quality_label": quality_label,
                "anchor_slots": anchor_summary,
                "value_triplet": value_triplet,
            }
        )

    stable_anchor_lane_count = sum(
        1
        for anchor_item in anchor_by_lane.values()
        if float(anchor_item.get("dominant_slot_confidence", 0.0) or 0.0) >= 0.6
    )
    if strong_tuple_count >= max(3, tuple_count - 1):
        recovery_evidence_label = "partial_repeatable_slot_recovery"
    elif strong_tuple_count >= 2:
        recovery_evidence_label = "weak_repeatable_slot_recovery"
    else:
        recovery_evidence_label = "insufficient_slot_recovery"

    return {
        "assembler_label": "phase_triplet_plus_lane_anchor_probe",
        "candidate_xyz_tuple_count": int(tuple_count),
        "strong_xyz_tuple_count": int(strong_tuple_count),
        "partial_xyz_tuple_count": int(partial_tuple_count),
        "three_lane_tuple_count": int(three_lane_tuple_count),
        "repeated_lane_tuple_count": int(repeated_lane_tuple_count),
        "tight_window_tuple_count": int(tight_window_tuple_count),
        "anchor_supported_tuple_count": int(anchor_supported_tuple_count),
        "stable_anchor_lane_count": int(stable_anchor_lane_count),
        "candidate_record_span_min": int(min(record_spans)) if record_spans else 0,
        "candidate_record_span_max": int(max(record_spans)) if record_spans else 0,
        "candidate_record_span_avg": round(sum(record_spans) / len(record_spans), 3) if record_spans else 0.0,
        "candidate_unique_lane_count_min": int(min(unique_lane_counts)) if unique_lane_counts else 0,
        "candidate_unique_lane_count_max": int(max(unique_lane_counts)) if unique_lane_counts else 0,
        "lane_anchor_support_map": [
            {
                "lane": int(item.get("lane", 0) or 0),
                "total_hits": int(item.get("total_hits", 0) or 0),
                "dominant_slots": [
                    {
                        "slot": int(slot_item.get("slot", 0) or 0),
                        "hit_count": int(slot_item.get("hit_count", 0) or 0),
                    }
                    for slot_item in item.get("dominant_slots", [])[:3]
                    if isinstance(slot_item, dict)
                ],
                "dominant_slot_confidence": round(float(item.get("dominant_slot_confidence", 0.0) or 0.0), 3),
            }
            for item in sorted(anchor_by_lane.values(), key=lambda row: int(row.get("lane", 0) or 0))
        ],
        "tuple_samples": tuple_samples[:6],
        "recovery_evidence_label": recovery_evidence_label,
        "exact_xyz_recovery_ready": False,
        "note": (
            "NODE hinted range에서 phase-triplet 후보를 다시 읽어보면, "
            f"{int(strong_tuple_count)}/{int(tuple_count)} tuple이 3-lane coverage를 보입니다. "
            "이건 hint-guided preview보다 강한 parser-side evidence지만, "
            "record-local exact xyz decode를 정당화할 정도는 아직 아닙니다."
        ),
    }


def _summarize_mcvl_u32_layout_probe(
    data: bytes,
    row: dict[str, object] | None,
    *,
    stride_bytes: int = 32,
    small_uint_max: int = 100000,
    sample_limit: int = 8,
    reference_ranges: dict[str, tuple[int, int]] | None = None,
) -> dict[str, object]:
    if not isinstance(row, dict):
        return {}
    range_start = int(row.get("mcvl_hint_range_start", 0) or 0)
    range_end = int(row.get("mcvl_hint_range_end", 0) or 0)
    if range_end <= range_start or range_start <= 0:
        return {}

    full_record_counter: dict[str, int] = {}
    small_uint_slot_counts = [0] * 8
    nonzero_slot_counts = [0] * 8
    small_uint_slot_min = [None] * 8
    small_uint_slot_max = [None] * 8
    small_uint_slot_unique: list[set[int]] = [set() for _ in range(8)]
    small_uint_slot_ordered_values: list[list[int]] = [[] for _ in range(8)]
    record_small_uint_patterns: dict[tuple[int, ...], int] = {}
    adjacent_slot_pair_diffs: dict[tuple[int, int], list[int]] = {
        (slot_index, slot_index + 1): []
        for slot_index in range(7)
    }
    reference_slot_hits: dict[str, list[int]] = {
        key: [0] * 8
        for key in (reference_ranges or {})
    }
    fill_byte_counter: Counter[int] = Counter()
    nonzero_fill_byte_counter: Counter[int] = Counter()
    sample_small_uint_records: list[dict[str, object]] = []
    records_scanned = 0
    active_small_uint_record_count = 0
    zero_record_count = 0
    constant_fill_record_count = 0
    nonzero_constant_fill_record_count = 0
    space_fill_record_count = 0
    nonfill_nonzero_record_count = 0

    for record_index in range(range_start, range_end):
        offset = int(record_index * stride_bytes)
        if offset + stride_bytes > len(data):
            break
        chunk = data[offset : offset + stride_bytes]
        values = struct.unpack("<IIIIIIII", chunk)
        records_scanned += 1
        full_record_counter[chunk.hex()] = full_record_counter.get(chunk.hex(), 0) + 1
        if not any(chunk):
            zero_record_count += 1
        if len(set(chunk)) == 1:
            fill_byte = int(chunk[0])
            constant_fill_record_count += 1
            fill_byte_counter[fill_byte] += 1
            if fill_byte != 0:
                nonzero_constant_fill_record_count += 1
                nonzero_fill_byte_counter[fill_byte] += 1
            if fill_byte == 0x20:
                space_fill_record_count += 1
        elif any(chunk):
            nonfill_nonzero_record_count += 1
        small_uint_values: list[dict[str, int]] = []
        present_slots: list[int] = []
        for slot_index, value in enumerate(values):
            if value != 0:
                nonzero_slot_counts[slot_index] += 1
            if 0 < value < small_uint_max:
                small_uint_slot_counts[slot_index] += 1
                small_uint_slot_unique[slot_index].add(int(value))
                small_uint_slot_ordered_values[slot_index].append(int(value))
                present_slots.append(int(slot_index))
                if small_uint_slot_min[slot_index] is None or value < int(small_uint_slot_min[slot_index]):
                    small_uint_slot_min[slot_index] = int(value)
                if small_uint_slot_max[slot_index] is None or value > int(small_uint_slot_max[slot_index]):
                    small_uint_slot_max[slot_index] = int(value)
                small_uint_values.append({"slot": int(slot_index), "value_uint32": int(value)})
            for range_label, range_pair in (reference_ranges or {}).items():
                ref_start, ref_end = range_pair
                if int(ref_start) <= int(value) <= int(ref_end):
                    reference_slot_hits[range_label][slot_index] += 1
        if present_slots:
            pattern_key = tuple(present_slots)
            record_small_uint_patterns[pattern_key] = record_small_uint_patterns.get(pattern_key, 0) + 1
        for slot_index in range(7):
            left = int(values[slot_index])
            right = int(values[slot_index + 1])
            if 0 < left < small_uint_max and 0 < right < small_uint_max:
                adjacent_slot_pair_diffs[(slot_index, slot_index + 1)].append(int(right - left))
        if small_uint_values:
            active_small_uint_record_count += 1
            if len(sample_small_uint_records) < sample_limit:
                sample_small_uint_records.append(
                    {
                        "record_index": int(record_index),
                        "values": small_uint_values,
                    }
                )

    if records_scanned <= 0:
        return {}

    dominant_record_hex = ""
    dominant_record_count = 0
    if full_record_counter:
        dominant_record_hex, dominant_record_count = max(full_record_counter.items(), key=lambda item: item[1])
    dominant_record_ratio = round(float(dominant_record_count) / float(records_scanned), 3) if records_scanned else 0.0
    dominant_fill_byte = None
    dominant_fill_byte_count = 0
    if fill_byte_counter:
        dominant_fill_byte, dominant_fill_byte_count = max(fill_byte_counter.items(), key=lambda item: item[1])
    dominant_nonzero_fill_byte = None
    dominant_nonzero_fill_byte_count = 0
    if nonzero_fill_byte_counter:
        dominant_nonzero_fill_byte, dominant_nonzero_fill_byte_count = max(nonzero_fill_byte_counter.items(), key=lambda item: item[1])

    note = (
        "MCVL hinted range was scanned as 8x uint32 fields per 32-byte record to expose field-layout evidence."
    )
    if dominant_record_ratio >= 0.9:
        note += " Most records share the same raw uint32 layout, so this range still looks more like constant-filled scaffolding than decoded payload."
    elif active_small_uint_record_count > 0:
        note += " Sparse small uint32 values are present, which may be useful as the next offset/layout probe."
    if space_fill_record_count > 0:
        note += " A subset of records are 0x20-filled, which looks more like padding or text-aligned filler than resolved member references at this stride."

    likely_identifier_slots = [
        int(slot_index)
        for slot_index, unique_values in enumerate(small_uint_slot_unique)
        if len(unique_values) >= 3 and small_uint_slot_counts[slot_index] >= 3
    ]
    slot_pattern_probe = [
        {
            "slots": [int(value) for value in slot_pattern],
            "record_count": int(record_count),
        }
        for slot_pattern, record_count in sorted(
            record_small_uint_patterns.items(),
            key=lambda item: (-int(item[1]), len(item[0]), item[0]),
        )[: sample_limit + 4]
    ]

    slot_progression_probe: list[dict[str, object]] = []
    likely_counter_slots: list[int] = []
    for slot_index, ordered_values in enumerate(small_uint_slot_ordered_values):
        if len(ordered_values) < 2:
            slot_progression_probe.append(
                {
                    "slot": int(slot_index),
                    "observation_count": int(len(ordered_values)),
                    "transition_count": 0,
                    "increasing_transition_count": 0,
                    "decreasing_transition_count": 0,
                    "repeated_transition_count": 0,
                    "small_positive_step_count": 0,
                    "nondecreasing_ratio": 0.0,
                    "small_positive_step_ratio": 0.0,
                    "sample_ordered_values": [int(value) for value in ordered_values[: sample_limit + 4]],
                }
            )
            continue
        diffs = [int(next_value - current_value) for current_value, next_value in zip(ordered_values, ordered_values[1:])]
        increasing_transition_count = sum(1 for value in diffs if value > 0)
        decreasing_transition_count = sum(1 for value in diffs if value < 0)
        repeated_transition_count = sum(1 for value in diffs if value == 0)
        small_positive_step_count = sum(1 for value in diffs if 0 < value <= 8)
        transition_count = len(diffs)
        nondecreasing_ratio = (
            round(float(increasing_transition_count + repeated_transition_count) / float(transition_count), 3)
            if transition_count
            else 0.0
        )
        small_positive_step_ratio = (
            round(float(small_positive_step_count) / float(transition_count), 3)
            if transition_count
            else 0.0
        )
        if transition_count >= 4 and nondecreasing_ratio >= 0.8 and small_positive_step_count >= 2:
            likely_counter_slots.append(int(slot_index))
        slot_progression_probe.append(
            {
                "slot": int(slot_index),
                "observation_count": int(len(ordered_values)),
                "transition_count": int(transition_count),
                "increasing_transition_count": int(increasing_transition_count),
                "decreasing_transition_count": int(decreasing_transition_count),
                "repeated_transition_count": int(repeated_transition_count),
                "small_positive_step_count": int(small_positive_step_count),
                "nondecreasing_ratio": float(nondecreasing_ratio),
                "small_positive_step_ratio": float(small_positive_step_ratio),
                "sample_ordered_values": [int(value) for value in ordered_values[: sample_limit + 4]],
            }
        )

    adjacent_slot_pair_probe: list[dict[str, object]] = []
    likely_packed_identifier_pairs: list[list[int]] = []
    for pair_key, pair_diffs in adjacent_slot_pair_diffs.items():
        pair_counter = Counter(pair_diffs)
        pair_transition_count = len(pair_diffs)
        dominant_delta = 0
        dominant_delta_count = 0
        if pair_counter:
            dominant_delta, dominant_delta_count = max(pair_counter.items(), key=lambda item: item[1])
        near_equal_step_count = sum(1 for value in pair_diffs if abs(int(value)) <= 1)
        near_equal_step_ratio = (
            round(float(near_equal_step_count) / float(pair_transition_count), 3)
            if pair_transition_count
            else 0.0
        )
        dominant_delta_ratio = (
            round(float(dominant_delta_count) / float(pair_transition_count), 3)
            if pair_transition_count
            else 0.0
        )
        if pair_transition_count >= 4 and near_equal_step_ratio >= 0.5:
            likely_packed_identifier_pairs.append([int(pair_key[0]), int(pair_key[1])])
        adjacent_slot_pair_probe.append(
            {
                "pair": [int(pair_key[0]), int(pair_key[1])],
                "cooccurrence_count": int(pair_transition_count),
                "near_equal_step_count": int(near_equal_step_count),
                "near_equal_step_ratio": float(near_equal_step_ratio),
                "dominant_delta": int(dominant_delta),
                "dominant_delta_count": int(dominant_delta_count),
                "dominant_delta_ratio": float(dominant_delta_ratio),
                "common_deltas": [
                    {"delta": int(delta), "count": int(count)}
                    for delta, count in pair_counter.most_common(6)
                ],
            }
        )

    layout_state_label = "mixed_sparse_uint_fields"
    if dominant_record_ratio >= 0.6:
        layout_state_label = "constant_fill_dominant"
    elif likely_identifier_slots:
        layout_state_label = "sparse_identifier_candidate"

    return {
        "table_name": str(row.get("table_name", "") or ""),
        "record_range": [int(range_start), int(range_end)],
        "stride_bytes": int(stride_bytes),
        "records_scanned": int(records_scanned),
        "active_small_uint_record_count": int(active_small_uint_record_count),
        "zero_record_count": int(zero_record_count),
        "constant_fill_record_count": int(constant_fill_record_count),
        "nonzero_constant_fill_record_count": int(nonzero_constant_fill_record_count),
        "space_fill_record_count": int(space_fill_record_count),
        "nonfill_nonzero_record_count": int(nonfill_nonzero_record_count),
        "small_uint_slot_counts": [int(value) for value in small_uint_slot_counts],
        "nonzero_slot_counts": [int(value) for value in nonzero_slot_counts],
        "small_uint_slot_minmax": [
            {
                "slot": int(slot_index),
                "min": (None if small_uint_slot_min[slot_index] is None else int(small_uint_slot_min[slot_index])),
                "max": (None if small_uint_slot_max[slot_index] is None else int(small_uint_slot_max[slot_index])),
                "unique_count": int(len(small_uint_slot_unique[slot_index])),
            }
            for slot_index in range(8)
        ],
        "slot_pattern_probe": slot_pattern_probe,
        "likely_identifier_slots": likely_identifier_slots,
        "likely_counter_slots": likely_counter_slots,
        "adjacent_slot_pair_probe": adjacent_slot_pair_probe,
        "likely_packed_identifier_pairs": likely_packed_identifier_pairs,
        "reference_slot_hits": {
            str(range_label): [int(value) for value in slot_counts]
            for range_label, slot_counts in reference_slot_hits.items()
        },
        "slot_progression_probe": slot_progression_probe,
        "dominant_record_hex": dominant_record_hex,
        "dominant_record_count": int(dominant_record_count),
        "dominant_record_ratio": float(dominant_record_ratio),
        "dominant_fill_byte_hex": ("" if dominant_fill_byte is None else f"0x{int(dominant_fill_byte):02x}"),
        "dominant_fill_byte_ascii": ("" if dominant_fill_byte is None or int(dominant_fill_byte) < 32 or int(dominant_fill_byte) > 126 else chr(int(dominant_fill_byte))),
        "dominant_fill_byte_count": int(dominant_fill_byte_count),
        "dominant_nonzero_fill_byte_hex": (
            "" if dominant_nonzero_fill_byte is None else f"0x{int(dominant_nonzero_fill_byte):02x}"
        ),
        "dominant_nonzero_fill_byte_ascii": (
            ""
            if dominant_nonzero_fill_byte is None or int(dominant_nonzero_fill_byte) < 32 or int(dominant_nonzero_fill_byte) > 126
            else chr(int(dominant_nonzero_fill_byte))
        ),
        "dominant_nonzero_fill_byte_count": int(dominant_nonzero_fill_byte_count),
        "layout_state_label": layout_state_label,
        "sample_small_uint_records": sample_small_uint_records,
        "note": note,
    }


def _build_directory_blocks(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    buckets: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        buckets.setdefault(int(row.get("directory_block_index", 0) or 0), []).append(row)
    out: list[dict[str, object]] = []
    for block_index in sorted(buckets.keys()):
        items = buckets[block_index]
        out.append(
            {
                "directory_block_index": block_index,
                "entry_count": len(items),
                "token_label": ", ".join(str(item.get("table_name", "")) for item in items),
                "directory_position_start": int(items[0].get("directory_position", 0) or 0),
                "directory_position_end": int(items[-1].get("directory_position", 0) or 0),
            }
        )
    return out


def _summarize_inventory(data: bytes, rows: list[dict[str, object]], *, sample_bytes: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    file_size = len(data)
    valid_positions = sorted(
        {
            int(row["candidate_low24_data_position"])
            for row in rows
            if not bool(row.get("directory_sentinel", False)) and int(row["candidate_low24_data_position"]) < file_size
        }
    )
    next_by_position = {
        valid_positions[index]: (valid_positions[index + 1] if index + 1 < len(valid_positions) else file_size)
        for index in range(len(valid_positions))
    }

    table_rows: list[dict[str, object]] = []
    geometry_preview: dict[str, object] = {
        "mode": "heuristic_xy_segment_preview",
        "ready": False,
        "candidate_segments_xy": [],
        "candidate_points_xy": [],
        "candidate_segment_count": 0,
        "candidate_point_count": 0,
        "bounds": {},
        "source_table": "",
        "note": "no heuristic geometry preview extracted",
    }

    for row in rows:
        candidate = int(row.get("candidate_low24_data_position", 0) or 0)
        sentinel = bool(row.get("directory_sentinel", False))
        in_file = bool(candidate < file_size and not sentinel)
        next_position = next_by_position.get(candidate, file_size) if in_file else file_size
        inferred_span = max(0, int(next_position - candidate)) if in_file else 0
        payload_probe_cap = max(inferred_span, 4096) if in_file else 0
        payload_probe_span = min(file_size - candidate, sample_bytes, payload_probe_cap) if in_file else 0
        payload = data[candidate : candidate + payload_probe_span] if payload_probe_span > 0 else b""
        payload_ascii = _safe_ascii_words(payload)
        plausible_rows = _plausible_f64_rows(payload)

        item = dict(row)
        item.update(
            {
                "data_position_in_file": in_file,
                "inferred_payload_span_bytes": int(inferred_span),
                "payload_probe_span_bytes": int(payload_probe_span),
                "payload_ascii_rows": payload_ascii,
                "payload_plausible_f64_rows": plausible_rows,
                "payload_head_hex": payload[:96].hex(),
                "unresolved_reason": "directory sentinel row"
                if sentinel
                else ("candidate low24 offset falls outside file" if not in_file else ""),
            }
        )
        if str(item.get("table_name", "")) in {"xVPNT", "PONT"} and payload:
            preview = _extract_xy_preview(payload)
            preview["source_table"] = str(item.get("table_name", ""))
            item["geometry_preview"] = preview
            if bool(preview.get("ready", False)):
                geometry_preview = preview
        table_rows.append(item)

    summary = {
        "table_entry_count": int(len(rows)),
        "directory_block_count": int(len({int(row.get('directory_block_index', 0) or 0) for row in rows})),
        "in_file_payload_table_count": int(sum(1 for row in table_rows if bool(row.get("data_position_in_file", False)))),
        "directory_sentinel_count": int(sum(1 for row in table_rows if bool(row.get("directory_sentinel", False)))),
        "unresolved_table_count": int(sum(1 for row in table_rows if str(row.get("unresolved_reason", "")))),
        "geometry_preview_ready": bool(geometry_preview.get("ready", False)),
        "topology_preview_ready": bool(geometry_preview.get("topology_preview_ready", False)),
        "geometry_preview_segment_count": int(geometry_preview.get("candidate_segment_count", 0) or 0),
        "geometry_preview_point_count": int(geometry_preview.get("candidate_point_count", 0) or 0),
        "geometry_preview_source_table": str(geometry_preview.get("source_table", "") or ""),
    }
    if not bool(geometry_preview.get("ready", False)):
        ascii_preview = _extract_table_local_ascii_preview(data, rows)
        local_preview = _extract_sparse_window_xyz_preview(
            data,
            window_bytes=min(max(sample_bytes * 4, 16384), 65536),
            step_bytes=max(4096, sample_bytes // 2),
            max_abs=500.0,
            cluster_gap_bytes=512,
            min_cluster_points=4,
            min_axis_span=0.1,
            note_prefix="MBDG payload-local window scan",
        )
        raw_preview = _extract_raw_xyz_preview(
            data,
            scan_bytes=min(max(sample_bytes * 8, 65536), 250_000),
            max_abs=500.0,
            cluster_gap_bytes=1024,
            min_cluster_points=6,
            min_axis_span=20.0,
            note_prefix="MBDG raw double scan",
        )
        if ascii_preview.get("candidate_points_xy"):
            geometry_preview = ascii_preview
        elif local_preview.get("candidate_points_xy"):
            geometry_preview = local_preview
        if not ascii_preview.get("candidate_points_xy") and raw_preview.get("candidate_points_xy") and int(raw_preview.get("candidate_point_count", 0) or 0) >= int(
            geometry_preview.get("candidate_point_count", 0) or 0
        ) + 2:
            geometry_preview = raw_preview
        if geometry_preview.get("candidate_points_xy"):
            summary["geometry_preview_point_count"] = int(geometry_preview.get("candidate_point_count", 0) or 0)
            summary["geometry_preview_segment_count"] = int(geometry_preview.get("candidate_segment_count", 0) or 0)
            summary["geometry_preview_source_table"] = str(geometry_preview.get("source_table", "") or "")
            summary["topology_preview_ready"] = bool(geometry_preview.get("topology_preview_ready", False))
        if geometry_preview.get("mode") == "table_local_ascii_preview":
            summary["table_local_preview_probe"] = {
                "candidate_point_count": int(geometry_preview.get("candidate_point_count", 0) or 0),
                "candidate_segment_count": int(geometry_preview.get("candidate_segment_count", 0) or 0),
                "projection_label": str(geometry_preview.get("projection_label", "") or ""),
                "source_table": str(geometry_preview.get("source_table", "") or ""),
                "anchor_table_names": geometry_preview.get("anchor_table_names", []),
                "topology_grounding_label": str(geometry_preview.get("topology_grounding_label", "") or ""),
                "member_path_count": int(geometry_preview.get("member_path_count", 0) or 0),
                "resolved_member_path_count": int(geometry_preview.get("resolved_member_path_count", 0) or 0),
                "missing_member_path_count": int(geometry_preview.get("missing_member_path_count", 0) or 0),
                "member_path_resolution_rate": float(geometry_preview.get("member_path_resolution_rate", 0.0) or 0.0),
                "member_reference_count": int(geometry_preview.get("member_reference_count", 0) or 0),
                "resolved_member_reference_count": int(geometry_preview.get("resolved_member_reference_count", 0) or 0),
                "missing_member_reference_count": int(geometry_preview.get("missing_member_reference_count", 0) or 0),
                "member_reference_resolution_rate": float(geometry_preview.get("member_reference_resolution_rate", 0.0) or 0.0),
                "payload_exact_topology_ready": bool(geometry_preview.get("payload_exact_topology_ready", False)),
                "payload_exactness_label": str(geometry_preview.get("payload_exactness_label", "") or ""),
                "topology_preview_ready": bool(geometry_preview.get("topology_preview_ready", False)),
                "topology_readiness_label": str(geometry_preview.get("topology_readiness_label", "") or ""),
                "topology_node_count": int(geometry_preview.get("topology_node_count", 0) or 0),
                "topology_edge_count": int(geometry_preview.get("topology_edge_count", 0) or 0),
                "topology_component_count": int(geometry_preview.get("topology_component_count", 0) or 0),
                "dangling_point_count": int(geometry_preview.get("dangling_point_count", 0) or 0),
                "junction_point_count": int(geometry_preview.get("junction_point_count", 0) or 0),
                "isolated_preview_point_count": int(geometry_preview.get("isolated_preview_point_count", 0) or 0),
                "resolved_member_path_samples": geometry_preview.get("resolved_member_path_samples", []),
                "anchor_directory_position": int(geometry_preview.get("anchor_directory_position", 0) or 0),
                "window_start_byte": int(geometry_preview.get("window_start_byte", 0) or 0),
                "window_end_byte": int(geometry_preview.get("window_end_byte", 0) or 0),
            }
    summary["geometry_preview_mode"] = str(geometry_preview.get("mode", "") or "")
    return table_rows, {"geometry_preview": geometry_preview, "summary": summary}


def _write_npz(path: Path, table_rows: list[dict[str, object]], geometry_preview: dict[str, object]) -> None:
    table_names = np.asarray([str(row.get("table_name", "")) for row in table_rows], dtype=str)
    directory_positions = np.asarray([int(row.get("directory_position", 0) or 0) for row in table_rows], dtype=np.int64)
    candidate_low24 = np.asarray([int(row.get("candidate_low24_data_position", 0) or 0) for row in table_rows], dtype=np.int64)
    data_position_in_file = np.asarray([bool(row.get("data_position_in_file", False)) for row in table_rows], dtype=bool)
    inferred_payload_span = np.asarray([int(row.get("inferred_payload_span_bytes", 0) or 0) for row in table_rows], dtype=np.int64)
    directory_block_index = np.asarray([int(row.get("directory_block_index", 0) or 0) for row in table_rows], dtype=np.int64)
    segment_rows = geometry_preview.get("candidate_segments_xy") or []
    point_rows = geometry_preview.get("candidate_points_xy") or []
    segment_array = np.asarray(
        [[float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])] for row in segment_rows],
        dtype=np.float64,
    ).reshape((-1, 4)) if segment_rows else np.zeros((0, 4), dtype=np.float64)
    point_array = np.asarray(point_rows, dtype=np.float64).reshape((-1, 2)) if point_rows else np.zeros((0, 2), dtype=np.float64)
    np.savez(
        path,
        table_name=table_names,
        directory_position=directory_positions,
        candidate_low24_data_position=candidate_low24,
        data_position_in_file=data_position_in_file,
        inferred_payload_span_bytes=inferred_payload_span,
        directory_block_index=directory_block_index,
        preview_segments_xy=segment_array,
        preview_points_xy=point_array,
    )


def _summarize_mcvl_inventory(data: bytes, rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    exact_preview = _extract_mcvl_record_topology_preview(data, rows)
    hint_preview = _extract_mcvl_node_hint_preview(data, rows)
    raw_preview = _extract_raw_xyz_preview(
        data,
        scan_bytes=250_000,
        max_abs=500.0,
        cluster_gap_bytes=1024,
        min_cluster_points=12,
        min_axis_span=20.0,
        note_prefix="MCVL raw double scan",
    )
    selected_preview = exact_preview if exact_preview.get("candidate_points_xy") else (hint_preview if hint_preview.get("candidate_points_xy") else raw_preview)
    table_rows: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item.update(
            {
                "data_position_in_file": False,
                "inferred_payload_span_bytes": 0,
                "payload_probe_span_bytes": 0,
                "payload_ascii_rows": [],
                "payload_plausible_f64_rows": [],
                "payload_head_hex": "",
                "unresolved_reason": "mcvl table directory extracted but payload offsets are not decoded yet",
            }
        )
        table_rows.append(item)
    geometry_preview: dict[str, object] = {
        "mode": str(selected_preview.get("mode", "") or "heuristic_xyz_point_scan"),
        "ready": False,
        "candidate_segments_xy": selected_preview.get("candidate_segments_xy", []),
        "candidate_points_xy": selected_preview.get("candidate_points_xy", []),
        "candidate_points_xyz": selected_preview.get("candidate_points_xyz", []),
        "candidate_segments_xyz": selected_preview.get("candidate_segments_xyz", []),
        "candidate_point_sources": selected_preview.get("candidate_point_sources", []),
        "candidate_segment_count": int(selected_preview.get("candidate_segment_count", 0) or 0),
        "candidate_point_count": int(selected_preview.get("candidate_point_count", 0) or 0),
        "candidate_scalar_count": int(selected_preview.get("candidate_scalar_count", 0) or 0),
        "bounds": selected_preview.get("bounds", {}) if isinstance(selected_preview.get("bounds"), dict) else {},
        "source_table": str(selected_preview.get("source_table", "") or ""),
        "projection_label": str(selected_preview.get("projection_label", "") or ""),
        "hint_stride_bytes": int(selected_preview.get("hint_stride_bytes", 0) or 0),
        "hint_grouping_phase": int(selected_preview.get("hint_grouping_phase", 0) or 0),
        "hint_node_range": selected_preview.get("hint_node_range", []),
        "hint_elem_range": selected_preview.get("hint_elem_range", []),
        "topology_grounding_label": str(selected_preview.get("topology_grounding_label", "") or ""),
        "topology_preview_ready": bool(selected_preview.get("topology_preview_ready", False)),
        "topology_readiness_label": str(selected_preview.get("topology_readiness_label", "") or ""),
        "exact_topology_candidate": bool(selected_preview.get("exact_topology_candidate", False)),
        "exact_topology_promoted": bool(selected_preview.get("exact_topology_promoted", False)),
        "topology_node_count": int(selected_preview.get("topology_node_count", 0) or 0),
        "topology_edge_count": int(selected_preview.get("topology_edge_count", 0) or 0),
        "axis_spans": selected_preview.get("axis_spans", {}) if isinstance(selected_preview.get("axis_spans"), dict) else {},
        "note": str(
            selected_preview.get("note", "")
            or "MCVL table directory는 추출됐지만 payload offset mapping이 아직 없어 geometry preview는 만들지 못했습니다."
        ),
    }
    if selected_preview.get("candidate_node_record_count") is not None:
        geometry_preview["candidate_node_record_count"] = int(selected_preview.get("candidate_node_record_count", 0) or 0)
        geometry_preview["candidate_elem_record_count"] = int(selected_preview.get("candidate_elem_record_count", 0) or 0)
        geometry_preview["resolved_member_record_count"] = int(selected_preview.get("resolved_member_record_count", 0) or 0)
        geometry_preview["member_reference_count"] = int(selected_preview.get("member_reference_count", 0) or 0)
        geometry_preview["resolved_member_reference_count"] = int(selected_preview.get("resolved_member_reference_count", 0) or 0)
        geometry_preview["resolved_member_reference_rate"] = float(selected_preview.get("resolved_member_reference_rate", 0.0) or 0.0)
        geometry_preview["candidate_node_record_ids"] = selected_preview.get("candidate_node_record_ids", [])
        geometry_preview["candidate_node_source_slots"] = selected_preview.get("candidate_node_source_slots", [])
        geometry_preview["candidate_elem_reference_slots"] = selected_preview.get("candidate_elem_reference_slots", [])
        geometry_preview["candidate_elem_path_samples"] = selected_preview.get("candidate_elem_path_samples", [])
    summary = {
        "table_entry_count": int(len(rows)),
        "directory_block_count": 1 if rows else 0,
        "in_file_payload_table_count": 0,
        "directory_sentinel_count": 0,
        "unresolved_table_count": int(len(rows)),
        "geometry_preview_ready": False,
        "geometry_preview_segment_count": int(selected_preview.get("candidate_segment_count", 0) or 0),
        "geometry_preview_point_count": int(selected_preview.get("candidate_point_count", 0) or 0),
        "geometry_preview_source_table": str(selected_preview.get("source_table", "") or ""),
        "geometry_preview_mode": str(selected_preview.get("mode", "") or ""),
    }
    node_row = next((row for row in rows if str(row.get("table_name", "") or "") == "NODE"), None)
    elem_row = next((row for row in rows if str(row.get("table_name", "") or "") == "ELEM"), None)
    if isinstance(node_row, dict) or isinstance(elem_row, dict):
        node_range = (
            int(node_row.get("mcvl_hint_range_start", 0) or 0),
            int(node_row.get("mcvl_hint_range_end", 0) or 0),
        ) if isinstance(node_row, dict) else (0, 0)
        elem_range = (
            int(elem_row.get("mcvl_hint_range_start", 0) or 0),
            int(elem_row.get("mcvl_hint_range_end", 0) or 0),
        ) if isinstance(elem_row, dict) else (0, 0)
        def _probe_row(row: dict[str, object] | None) -> dict[str, object]:
            if not isinstance(row, dict):
                return {}
            start = int(row.get("mcvl_hint_range_start", 0) or 0)
            end = int(row.get("mcvl_hint_range_end", 0) or 0)
            return {
                "table_name": str(row.get("table_name", "") or ""),
                "range_start": start,
                "range_end": end,
                "record_count_hint": max(0, end - start),
                "word3_hint": int(row.get("mcvl_hint_word3", 0) or 0),
                "directory_position": int(row.get("directory_position", 0) or 0),
            }

        summary["mcvl_node_elem_probe"] = {
            "layout_family": "MCVL_TABLE_CONTAINER",
            "node": _probe_row(node_row),
            "elem": _probe_row(elem_row),
            "likely_stride_bytes": 32,
            "note": "NODE/ELEM token rows are present. Decode the hinted MCVL ranges into actual node coordinates and member connectivity.",
        }
        summary["mcvl_node_record_probe"] = _summarize_mcvl_node_record_probe(data, node_row, stride_bytes=32, max_abs=500.0)
        summary["mcvl_node_reassembly_probe"] = _summarize_mcvl_node_reassembly_probe(
            data,
            node_row,
            stride_bytes=32,
            max_abs=500.0,
        )
        summary["mcvl_node_scalar_lane_probe"] = _summarize_mcvl_scalar_lane_probe(
            data,
            node_row,
            stride_bytes=32,
            max_abs=500.0,
            small_uint_max=100000,
        )
        summary["mcvl_node_uint_layout_probe"] = _summarize_mcvl_u32_layout_probe(
            data,
            node_row,
            stride_bytes=32,
            reference_ranges={"node_range": node_range, "elem_range": elem_range},
        )
        summary["mcvl_elem_uint_layout_probe"] = _summarize_mcvl_u32_layout_probe(
            data,
            elem_row,
            stride_bytes=32,
            reference_ranges={"node_range": node_range, "elem_range": elem_range},
        )
    if hint_preview:
        summary["mcvl_hint_preview_probe"] = {
            "candidate_scalar_count": int(hint_preview.get("candidate_scalar_count", 0) or 0),
            "candidate_point_count": int(hint_preview.get("candidate_point_count", 0) or 0),
            "candidate_segment_count": int(hint_preview.get("candidate_segment_count", 0) or 0),
            "projection_label": str(hint_preview.get("projection_label", "") or ""),
            "hint_grouping_phase": int(hint_preview.get("hint_grouping_phase", 0) or 0),
            "source_table": str(hint_preview.get("source_table", "") or ""),
            "topology_grounding_label": str(hint_preview.get("topology_grounding_label", "") or ""),
            "phase_scoreboard": hint_preview.get("phase_scoreboard", []),
            "selected_phase_record_windows": hint_preview.get("selected_phase_record_windows", []),
            "selected_phase_lane_sequences": hint_preview.get("selected_phase_lane_sequences", []),
        }
        slot_recovery_probe = _summarize_mcvl_node_xyz_slot_recovery_probe(
            hint_preview,
            summary.get("mcvl_node_scalar_lane_probe", {}),
        )
        if slot_recovery_probe:
            summary["mcvl_node_xyz_slot_recovery_probe"] = slot_recovery_probe
            geometry_preview["node_xyz_recovery_label"] = str(slot_recovery_probe.get("recovery_evidence_label", "") or "")
            geometry_preview["node_xyz_recovery_ready"] = bool(slot_recovery_probe.get("exact_xyz_recovery_ready", False))
            geometry_preview["node_xyz_strong_tuple_count"] = int(slot_recovery_probe.get("strong_xyz_tuple_count", 0) or 0)
            geometry_preview["node_xyz_tuple_count"] = int(slot_recovery_probe.get("candidate_xyz_tuple_count", 0) or 0)
    if exact_preview:
        summary["mcvl_exact_topology_probe"] = {
            "candidate_point_count": int(exact_preview.get("candidate_point_count", 0) or 0),
            "candidate_segment_count": int(exact_preview.get("candidate_segment_count", 0) or 0),
            "projection_label": str(exact_preview.get("projection_label", "") or ""),
            "source_table": str(exact_preview.get("source_table", "") or ""),
            "topology_grounding_label": str(exact_preview.get("topology_grounding_label", "") or ""),
            "candidate_node_record_count": int(exact_preview.get("candidate_node_record_count", 0) or 0),
            "candidate_elem_record_count": int(exact_preview.get("candidate_elem_record_count", 0) or 0),
            "resolved_member_reference_rate": float(exact_preview.get("resolved_member_reference_rate", 0.0) or 0.0),
            "candidate_elem_reference_slots": exact_preview.get("candidate_elem_reference_slots", []),
            "exact_topology_candidate": bool(exact_preview.get("exact_topology_candidate", False)),
            "exact_topology_promoted": bool(exact_preview.get("exact_topology_promoted", False)),
        }
    return table_rows, {"geometry_preview": geometry_preview, "summary": summary}


def decode_meb_inventory(meb_path: Path, *, sample_bytes: int = 32768) -> tuple[dict[str, object], dict[str, object]]:
    probe = _inspect_meb(meb_path)
    if not bool(probe.get("scaffold_ready", False)):
        report_payload = {
            "schema_version": "1.0",
            "input": {"meb": str(meb_path)},
            "probe": probe,
            "contract_pass": False,
            "reason_code": "ERR_UNRECOGNIZED_LAYOUT",
            "reason": REASONS["ERR_UNRECOGNIZED_LAYOUT"],
        }
        return {}, report_payload

    data = meb_path.read_bytes()
    layout_family = str(probe.get("layout_family", "") or "")
    if layout_family == "MCVL_TABLE_CONTAINER":
        directory_rows = _iter_mcvl_table_entries(data)
        inventory_rows, extracted = _summarize_mcvl_inventory(data, directory_rows)
    else:
        directory_rows = _iter_table_entries(data)
        inventory_rows, extracted = _summarize_inventory(data, directory_rows, sample_bytes=max(256, int(sample_bytes)))
    geometry_preview = extracted["geometry_preview"]
    summary = extracted["summary"]
    directory_blocks = _build_directory_blocks(directory_rows)
    reason_code = (
        "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY"
        if bool(summary.get("geometry_preview_ready", False))
        else "PASS_TABLE_DIRECTORY_ONLY"
    )
    unique_table_names: list[str] = []
    for row in inventory_rows:
        table_name = str(row.get("table_name", "") or "")
        if not table_name or table_name in unique_table_names:
            continue
        unique_table_names.append(table_name)
        if len(unique_table_names) >= 24:
            break
    summary.update(
        {
            "layout_family": layout_family,
            "reason_code": reason_code,
            "source_member_name": meb_path.name,
            "table_names": unique_table_names,
            "geometry_preview_mode": str(geometry_preview.get("mode", "") or summary.get("geometry_preview_mode", "") or ""),
        }
    )

    inventory_payload = {
        "schema_version": "1.0",
        "input": {"meb": str(meb_path)},
        "probe": probe,
        "directory_blocks": directory_blocks,
        "table_inventory_rows": inventory_rows,
        "geometry_preview": geometry_preview,
        "summary": summary,
    }
    report_payload = dict(inventory_payload)
    report_payload.update(
        {
            "checks": {
                "magic_mbdg": str(probe.get("magic_ascii", "")) == "MBDG",
                "dbms_marker_present": bool(probe.get("dbms_marker_present", False)),
                "table_directory_nonzero": bool(directory_rows),
                "geometry_preview_ready": bool(summary.get("geometry_preview_ready", False)),
            },
            "next_step": {
                "recommended_decoder": "midas_binary_mcb_table_decoder" if layout_family == "MCVL_TABLE_CONTAINER" else "midas_binary_meb_table_decoder",
                "recommended_outputs": ["json", "npz", "preview_svg"],
                "notes": (
                    "Use decoded MCVL table directory inventory as a bridge until full NODE/ELEM payload mapping is implemented."
                    if layout_family == "MCVL_TABLE_CONTAINER"
                    else "Use decoded table inventory and xVPNT heuristic preview as a bridge until full xMEMB/xSEGM topology decoding is implemented."
                ),
            },
            "contract_pass": True,
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
    )
    return inventory_payload, report_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meb", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--npz-out", default=None)
    parser.add_argument("--sample-bytes", type=int, default=32768)
    args = parser.parse_args()

    meb_path = Path(args.meb)
    report_out = Path(args.report_out)
    json_out = Path(args.json_out) if args.json_out else None
    npz_out = Path(args.npz_out) if args.npz_out else None
    for path in [report_out, json_out, npz_out]:
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    if not meb_path.exists():
        payload = {
            "schema_version": "1.0",
            "contract_pass": False,
            "reason_code": "ERR_MISSING_INPUT",
            "reason": REASONS["ERR_MISSING_INPUT"],
        }
        report_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1)

    inventory_payload, report_payload = decode_meb_inventory(meb_path, sample_bytes=max(256, int(args.sample_bytes)))
    if not bool(report_payload.get("contract_pass", False)):
        report_out.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1)

    if json_out is not None:
        json_out.write_text(json.dumps(inventory_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote MIDAS binary meb inventory json: {json_out}")
    if npz_out is not None:
        _write_npz(npz_out, inventory_payload.get("table_inventory_rows", []), inventory_payload.get("geometry_preview", {}))
        print(f"Wrote MIDAS binary meb inventory npz: {npz_out}")
    report_out.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote MIDAS binary meb inventory report: {report_out}")


if __name__ == "__main__":
    main()
