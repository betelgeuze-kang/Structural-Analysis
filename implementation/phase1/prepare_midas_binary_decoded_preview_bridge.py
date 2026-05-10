#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _point_key(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (round(float(x), 6), round(float(y), 6), round(float(z), 6))


def _segment_rows(preview: dict[str, Any]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for row in (preview.get("candidate_segments_xy") or []):
        if not isinstance(row, dict):
            continue
        try:
            rows.append(
                {
                    "x1": float(row.get("x1", 0.0)),
                    "y1": float(row.get("y1", 0.0)),
                    "x2": float(row.get("x2", 0.0)),
                    "y2": float(row.get("y2", 0.0)),
                }
            )
        except (TypeError, ValueError):
            continue
    return rows


def _point_rows(preview: dict[str, Any]) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for row in (preview.get("candidate_points_xy") or []):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            rows.append((float(row[0]), float(row[1])))
        except (TypeError, ValueError):
            continue
    return rows


def _point_scan_edges(points_xy: list[tuple[float, float]]) -> list[dict[str, float]]:
    unique_points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for x, y in points_xy:
        key = (round(float(x), 6), round(float(y), 6))
        if key in seen:
            continue
        seen.add(key)
        unique_points.append((float(x), float(y)))
    if len(unique_points) < 2:
        return []

    remaining = list(range(len(unique_points)))
    start = min(remaining, key=lambda idx: (unique_points[idx][0] + unique_points[idx][1], unique_points[idx][0], unique_points[idx][1]))
    order = [start]
    remaining.remove(start)
    while remaining:
        current = order[-1]
        cx, cy = unique_points[current]
        next_idx = min(
            remaining,
            key=lambda idx: ((unique_points[idx][0] - cx) ** 2 + (unique_points[idx][1] - cy) ** 2, unique_points[idx][0], unique_points[idx][1]),
        )
        order.append(next_idx)
        remaining.remove(next_idx)

    edges: list[dict[str, float]] = []
    for a, b in zip(order[:-1], order[1:]):
        x1, y1 = unique_points[a]
        x2, y2 = unique_points[b]
        if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
            continue
        edges.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return edges


def _preview_surface_fields(
    preview_state_label: str,
    *,
    topology_preview_ready: bool = False,
    topology_readiness_label: str = "",
    payload_exact_topology_ready: bool = False,
    exact_topology_candidate: bool = False,
    exact_topology_promoted: bool = False,
) -> dict[str, str]:
    state = str(preview_state_label or "")
    if state == "verified preview":
        return {
            "preview_surface_bucket": "verified-preview",
            "preview_surface_status_label": "viewer-ready verified preview 3d bridge",
            "preview_surface_status_tone": "ok",
            "preview_readiness_stage_label": "viewer-ready verified preview",
        }
    if state == "unverified hint preview":
        return {
            "preview_surface_bucket": "hint-preview",
            "preview_surface_status_label": "hint-guided preview-derived 3d candidate",
            "preview_surface_status_tone": "warn",
            "preview_readiness_stage_label": "hint preview candidate",
        }
    if state == "unverified table-local preview":
        if exact_topology_promoted:
            return {
                "preview_surface_bucket": "table-local-preview",
                "preview_surface_status_label": "exact recovered topology-derived 3d candidate",
                "preview_surface_status_tone": "warn",
                "preview_readiness_stage_label": "exact recovered topology promoted",
            }
        if exact_topology_candidate:
            return {
                "preview_surface_bucket": "table-local-preview",
                "preview_surface_status_label": "exact recovered topology-derived 3d candidate",
                "preview_surface_status_tone": "warn",
                "preview_readiness_stage_label": "exact recovered topology candidate",
            }
        if payload_exact_topology_ready or str(topology_readiness_label or "").startswith("payload-exact"):
            return {
                "preview_surface_bucket": "table-local-preview",
                "preview_surface_status_label": "payload-exact member-add preview-derived 3d candidate",
                "preview_surface_status_tone": "warn",
                "preview_readiness_stage_label": "payload-exact member-add preview candidate",
            }
        if topology_preview_ready or str(topology_readiness_label or "").startswith("topology-grounded"):
            return {
                "preview_surface_bucket": "table-local-preview",
                "preview_surface_status_label": "topology-grounded preview-derived 3d candidate",
                "preview_surface_status_tone": "warn",
                "preview_readiness_stage_label": "topology-grounded preview candidate",
            }
        return {
            "preview_surface_bucket": "table-local-preview",
            "preview_surface_status_label": "table-local preview-derived 3d candidate",
            "preview_surface_status_tone": "warn",
            "preview_readiness_stage_label": "table-local preview candidate",
        }
    if state == "unverified raw preview":
        return {
            "preview_surface_bucket": "raw-preview",
            "preview_surface_status_label": "raw preview-derived 3d candidate",
            "preview_surface_status_tone": "warn",
            "preview_readiness_stage_label": "raw preview candidate",
        }
    return {
        "preview_surface_bucket": "heuristic-preview",
        "preview_surface_status_label": "decoded heuristic preview 3d candidate",
        "preview_surface_status_tone": "warn",
        "preview_readiness_stage_label": "heuristic preview candidate",
    }


def _is_table_local_preview_mode(preview_mode: str) -> bool:
    mode = str(preview_mode or "").strip().lower()
    return (
        mode.startswith("table_local")
        or mode.startswith("table-local")
        or "table_local" in mode
        or "table-local" in mode
        or mode.startswith("payload_relative")
    )


def _resolve_preview_state_label(preview_mode: str, *, geometry_preview_ready: bool) -> str:
    if geometry_preview_ready:
        return "verified preview"
    if preview_mode == "mcvl_node_hint_preview":
        return "unverified hint preview"
    if _is_table_local_preview_mode(preview_mode):
        return "unverified table-local preview"
    if preview_mode == "heuristic_xyz_point_scan":
        return "unverified raw preview"
    return "unverified heuristic preview"


def _resolve_bridge_labels(preview_mode: str, *, segment_count: int, point_chain_count: int) -> tuple[str, str, str]:
    if segment_count > 0:
        if _is_table_local_preview_mode(preview_mode):
            return (
                "table_local_segment_preview",
                "table_local_preview",
                f"table_segment={segment_count}",
            )
        return (
            "segment_preview",
            "beam_preview",
            f"heuristic_segment={segment_count}",
        )
    if preview_mode == "mcvl_node_hint_preview":
        return (
            "point_scan_chain",
            "mcvl_hint_preview",
            f"hint_point_link={point_chain_count}",
        )
    if _is_table_local_preview_mode(preview_mode):
        return (
            "table_local_point_chain",
            "table_local_preview",
            f"table_point_link={point_chain_count}",
        )
    return (
        "point_scan_chain",
        "point_scan_preview",
        f"heuristic_point_link={point_chain_count}",
    )


def _resolve_preview_basis(preview_mode: str, source_table: str) -> str:
    mode = str(preview_mode or "").strip().lower()
    source = str(source_table or "").strip()
    if mode == "mcvl_node_hint_preview":
        return "mcvl_node_elem_hint"
    if _is_table_local_preview_mode(mode):
        if source.startswith("ASCII:*POINT"):
            return "embedded_ascii_point_member"
        return "table_local_payload"
    if "raw" in mode or "point_scan" in mode or "xyz_point_scan" in mode:
        return "raw_xyz_scan"
    if source:
        return "table_directory_heuristic"
    return "heuristic_preview"


def _preview_signal_candidates(
    preview: dict[str, Any] | None,
    preview_summary: dict[str, Any] | None,
    report_summary: dict[str, Any] | None,
) -> list[tuple[str, dict[str, Any]]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    if isinstance(preview, dict):
        candidates.append(("geometry_preview", preview))
    if isinstance(preview_summary, dict):
        candidates.append(("inventory_summary", preview_summary))
        probe = preview_summary.get("table_local_preview_probe")
        if isinstance(probe, dict):
            candidates.append(("inventory_summary.table_local_preview_probe", probe))
        probe = preview_summary.get("mcvl_exact_topology_probe")
        if isinstance(probe, dict):
            candidates.append(("inventory_summary.mcvl_exact_topology_probe", probe))
    if isinstance(report_summary, dict):
        candidates.append(("inventory_report_summary", report_summary))
        probe = report_summary.get("table_local_preview_probe")
        if isinstance(probe, dict):
            candidates.append(("inventory_report_summary.table_local_preview_probe", probe))
        probe = report_summary.get("mcvl_exact_topology_probe")
        if isinstance(probe, dict):
            candidates.append(("inventory_report_summary.mcvl_exact_topology_probe", probe))
    return candidates


def _resolve_preview_exactness_fields(
    preview_state_label: str,
    topology_fields: dict[str, Any],
) -> dict[str, str]:
    field_sources = topology_fields.get("topology_signal_field_sources")
    source_map = field_sources if isinstance(field_sources, dict) else {}
    exact_promoted = bool(topology_fields.get("exact_topology_promoted", False))
    exact_candidate = bool(topology_fields.get("exact_topology_candidate", False))
    topology_ready = bool(topology_fields.get("topology_preview_ready", False))
    payload_exact_ready = bool(topology_fields.get("payload_exact_topology_ready", False))
    topology_grounding_label = str(topology_fields.get("topology_grounding_label", "") or "")

    if exact_promoted:
        return {
            "preview_exactness_tier": "exact-topology-promoted",
            "preview_exactness_label": "exact topology promoted",
            "preview_exactness_signal_source": str(source_map.get("exact_topology_promoted", "unknown") or "unknown"),
        }
    if exact_candidate:
        return {
            "preview_exactness_tier": "exact-topology-candidate",
            "preview_exactness_label": "exact topology candidate",
            "preview_exactness_signal_source": str(source_map.get("exact_topology_candidate", "unknown") or "unknown"),
        }
    if payload_exact_ready:
        return {
            "preview_exactness_tier": "payload-exact-topology",
            "preview_exactness_label": "payload-exact member-add preview",
            "preview_exactness_signal_source": str(source_map.get("payload_exact_topology_ready", "unknown") or "unknown"),
        }
    if topology_ready:
        return {
            "preview_exactness_tier": "topology-grounded",
            "preview_exactness_label": "topology-grounded preview",
            "preview_exactness_signal_source": str(source_map.get("topology_preview_ready", "unknown") or "unknown"),
        }
    if topology_grounding_label:
        return {
            "preview_exactness_tier": "topology-signal",
            "preview_exactness_label": "topology signal only",
            "preview_exactness_signal_source": str(source_map.get("topology_grounding_label", "unknown") or "unknown"),
        }
    state = str(preview_state_label or "")
    if state == "verified preview":
        return {
            "preview_exactness_tier": "verified-geometry",
            "preview_exactness_label": "verified geometry preview",
            "preview_exactness_signal_source": "geometry_preview_ready",
        }
    if state == "unverified hint preview":
        return {
            "preview_exactness_tier": "hint-preview",
            "preview_exactness_label": "hint-guided preview",
            "preview_exactness_signal_source": "geometry_preview.mode",
        }
    if state == "unverified table-local preview":
        return {
            "preview_exactness_tier": "table-local-preview",
            "preview_exactness_label": "table-local preview",
            "preview_exactness_signal_source": "geometry_preview.mode",
        }
    if state == "unverified raw preview":
        return {
            "preview_exactness_tier": "raw-preview",
            "preview_exactness_label": "raw preview",
            "preview_exactness_signal_source": "geometry_preview.mode",
        }
    return {
        "preview_exactness_tier": "heuristic-preview",
        "preview_exactness_label": "heuristic preview",
        "preview_exactness_signal_source": "bridge-default",
    }


def _preview_topology_fields(
    preview: dict[str, Any] | None,
    preview_summary: dict[str, Any] | None = None,
    report_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = preview if isinstance(preview, dict) else {}
    candidates = _preview_signal_candidates(payload, preview_summary, report_summary)
    fields: dict[str, Any] = {}
    source_map: dict[str, str] = {}
    scalar_keys = (
        "topology_grounding_label",
        "topology_node_count",
        "topology_edge_count",
        "topology_component_count",
        "dangling_point_count",
        "junction_point_count",
        "isolated_preview_point_count",
        "member_path_count",
        "resolved_member_path_count",
        "member_path_resolution_rate",
        "member_reference_count",
        "resolved_member_reference_count",
        "member_reference_resolution_rate",
        "missing_node_id_count",
        "missing_member_path_count",
        "missing_member_reference_count",
        "payload_exact_topology_ready",
        "topology_preview_ready",
        "topology_readiness_label",
        "exact_topology_candidate",
        "exact_topology_promoted",
    )
    bool_keys = {
        "payload_exact_topology_ready",
        "topology_preview_ready",
        "exact_topology_candidate",
        "exact_topology_promoted",
    }
    float_keys = {
        "member_path_resolution_rate",
        "member_reference_resolution_rate",
    }
    for key in scalar_keys:
        if key in bool_keys:
            seen = False
            for label, candidate in candidates:
                if key not in candidate:
                    continue
                seen = True
                if bool(candidate.get(key, False)):
                    fields[key] = True
                    source_map[key] = label
                    break
                if key not in source_map:
                    source_map[key] = label
            if seen and key not in fields:
                fields[key] = False
            continue

        best_value: Any | None = None
        best_source = ""
        for label, candidate in candidates:
            value = candidate.get(key)
            if value is None or value == "" or value == []:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_value = float(value)
                if best_value is None or numeric_value > float(best_value):
                    best_value = float(value) if key in float_keys else int(value)
                    best_source = label
                continue
            if best_value is None:
                best_value = value
                best_source = label
        if best_value is None:
            continue
        fields[key] = best_value
        if best_source:
            source_map[key] = best_source
    samples = payload.get("resolved_member_path_samples")
    if not (isinstance(samples, list) and samples):
        for label, candidate in candidates:
            samples = candidate.get("resolved_member_path_samples")
            if isinstance(samples, list) and samples:
                source_map["resolved_member_path_samples"] = label
                break
    if isinstance(samples, list) and samples:
        fields["resolved_member_path_samples"] = samples
    if source_map:
        fields["topology_signal_field_sources"] = source_map
    return fields


def _topology_graph_payload(
    preview: dict[str, Any],
    topology_fields: dict[str, Any],
) -> dict[str, Any]:
    if not bool(topology_fields.get("exact_topology_candidate", False)):
        return {}
    if int(topology_fields.get("missing_member_path_count", 0) or 0) != 0:
        return {}
    if int(topology_fields.get("missing_member_reference_count", 0) or 0) != 0:
        return {}

    raw_nodes = preview.get("topology_nodes_xyz")
    raw_edges = preview.get("topology_edges_node_ids")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return {}

    nodes: dict[int, tuple[float, float, float]] = {}
    for row in raw_nodes:
        if not isinstance(row, dict):
            continue
        try:
            node_id = int(row.get("id", 0))
            coord = (
                float(row.get("x", 0.0)),
                float(row.get("y", 0.0)),
                float(row.get("z", 0.0)),
            )
        except (TypeError, ValueError):
            continue
        if node_id <= 0:
            continue
        nodes[node_id] = coord

    edges: set[tuple[int, int]] = set()
    missing_refs = 0
    for row in raw_edges:
        if not isinstance(row, dict):
            continue
        try:
            start_id = int(row.get("start", 0))
            end_id = int(row.get("end", 0))
        except (TypeError, ValueError):
            continue
        if start_id == end_id:
            continue
        if start_id not in nodes or end_id not in nodes:
            missing_refs += 1
            continue
        edges.add((min(start_id, end_id), max(start_id, end_id)))

    expected_node_count = int(topology_fields.get("topology_node_count", 0) or 0)
    expected_edge_count = int(topology_fields.get("topology_edge_count", 0) or 0)
    graph_matches_topology = (
        expected_node_count > 0
        and expected_edge_count > 0
        and len(nodes) == expected_node_count
        and len(edges) == expected_edge_count
        and missing_refs == 0
    )
    if not graph_matches_topology:
        return {}

    return {
        "nodes": nodes,
        "edges": sorted(edges),
        "graph_matches_topology": True,
    }


def _make_npz_payload(
    npz_out: Path,
    nodes: dict[int, tuple[float, float, float]],
    elements: list[dict[str, Any]],
    edges: list[tuple[int, int]],
) -> dict[str, int]:
    node_ids = sorted(nodes.keys())
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    node_xyz = np.asarray([nodes[node_id] for node_id in node_ids], dtype=np.float64)

    edge_index = np.zeros((2, len(edges) * 2), dtype=np.int64)
    for index, (node_a, node_b) in enumerate(edges):
        ia = node_index[int(node_a)]
        ib = node_index[int(node_b)]
        edge_index[:, 2 * index] = np.asarray([ia, ib], dtype=np.int64)
        edge_index[:, 2 * index + 1] = np.asarray([ib, ia], dtype=np.int64)

    elem_ids = np.asarray([int(row["id"]) for row in elements], dtype=np.int64)
    elem_conn_ptr = [0]
    elem_conn_idx: list[int] = []
    for row in elements:
        for node_id in row.get("node_ids", []):
            elem_conn_idx.append(int(node_index[int(node_id)]))
        elem_conn_ptr.append(len(elem_conn_idx))

    member_ids = np.asarray([str(row["id"]) for row in elements], dtype=str)
    story_band_index = np.zeros((len(elements),), dtype=np.int64)

    npz_out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        npz_out,
        node_id=np.asarray(node_ids, dtype=np.int64),
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_ids,
        elem_type_code=np.ones((len(elements),), dtype=np.int32),
        elem_section_id=np.full((len(elements),), -1, dtype=np.int64),
        elem_material_id=np.full((len(elements),), -1, dtype=np.int64),
        elem_conn_ptr=np.asarray(elem_conn_ptr, dtype=np.int64),
        elem_conn_idx=np.asarray(elem_conn_idx, dtype=np.int64),
        member_ids=member_ids,
        story_band_index=story_band_index,
    )
    return {
        "node_count": int(len(node_ids)),
        "edge_count_directed": int(edge_index.shape[1]),
        "element_count": int(len(elements)),
        "member_id_count": int(member_ids.size),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge decoded MEB preview geometry into a baseline 3D viewer payload.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--decoded-inventory-json", required=True)
    parser.add_argument("--decoded-inventory-report", required=True)
    parser.add_argument("--refresh-report", required=True)
    parser.add_argument("--model-json-out", required=True)
    parser.add_argument("--npz-out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args()

    source_id = str(args.source_id).strip() or "unknown_source"
    inventory_json_path = Path(args.decoded_inventory_json)
    inventory_report_path = Path(args.decoded_inventory_report)
    refresh_report_path = Path(args.refresh_report)
    model_json_out = Path(args.model_json_out)
    npz_out = Path(args.npz_out)
    report_out = Path(args.report_out)

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "report_type": "midas_binary_decoded_preview_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "inputs": {
            "decoded_inventory_json": str(inventory_json_path),
            "decoded_inventory_report": str(inventory_report_path),
            "refresh_report": str(refresh_report_path),
            "model_json_out": str(model_json_out),
            "npz_out": str(npz_out),
            "report_out": str(report_out),
        },
    }

    if not inventory_json_path.exists():
        report.update({"contract_pass": False, "reason_code": "ERR_INVENTORY_JSON_MISSING"})
        _write_json(report_out, report)
        return 1
    if not inventory_report_path.exists():
        report.update({"contract_pass": False, "reason_code": "ERR_INVENTORY_REPORT_MISSING"})
        _write_json(report_out, report)
        return 1

    inventory_payload = json.loads(inventory_json_path.read_text(encoding="utf-8"))
    inventory_report = json.loads(inventory_report_path.read_text(encoding="utf-8"))
    refresh_report = (
        json.loads(refresh_report_path.read_text(encoding="utf-8"))
        if refresh_report_path.exists()
        else {}
    )

    preview = inventory_payload.get("geometry_preview") if isinstance(inventory_payload.get("geometry_preview"), dict) else {}
    preview_summary = inventory_payload.get("summary") if isinstance(inventory_payload.get("summary"), dict) else {}
    report_summary = inventory_report.get("summary") if isinstance(inventory_report.get("summary"), dict) else {}
    segment_rows = _segment_rows(preview)
    preview_mode = str(preview.get("mode", "") or report_summary.get("geometry_preview_mode", "") or "")
    source_table = str(preview.get("source_table", "") or report_summary.get("geometry_preview_source_table", ""))
    projection_label = str(preview.get("projection_label", "") or "")
    anchor_table_names = [str(item) for item in (preview.get("anchor_table_names") or []) if str(item)]
    preview_state_label = _resolve_preview_state_label(
        preview_mode,
        geometry_preview_ready=bool(report_summary.get("geometry_preview_ready", False)),
    )
    bridge_mode, family_assumption, accepted_type_label = _resolve_bridge_labels(
        preview_mode,
        segment_count=len(segment_rows),
        point_chain_count=len(segment_rows),
    )
    preview_basis = _resolve_preview_basis(preview_mode, source_table)
    if not segment_rows:
        point_rows = _point_rows(preview)
        segment_rows = _point_scan_edges(point_rows)
        bridge_mode, family_assumption, accepted_type_label = _resolve_bridge_labels(
            preview_mode,
            segment_count=0,
            point_chain_count=len(segment_rows),
        )
    if not segment_rows:
        report.update({"contract_pass": False, "reason_code": "ERR_NO_PREVIEW_SEGMENTS"})
        _write_json(report_out, report)
        return 1
    preview_topology_fields = _preview_topology_fields(preview, preview_summary, report_summary)
    topology_graph = _topology_graph_payload(preview, preview_topology_fields)
    if topology_graph:
        preview_topology_fields["exact_topology_promoted"] = True
        preview_topology_fields["topology_node_count"] = len(topology_graph["nodes"])
        preview_topology_fields["topology_edge_count"] = len(topology_graph["edges"])
        source_map = preview_topology_fields.get("topology_signal_field_sources")
        if not isinstance(source_map, dict):
            source_map = {}
        source_map["exact_topology_promoted"] = "bridge.topology_graph_payload"
        preview_topology_fields["topology_signal_field_sources"] = source_map

    preview_exactness_fields = _resolve_preview_exactness_fields(preview_state_label, preview_topology_fields)
    surface_fields = _preview_surface_fields(
        preview_state_label,
        payload_exact_topology_ready=bool(preview_topology_fields.get("payload_exact_topology_ready", False)),
        topology_preview_ready=bool(preview_topology_fields.get("topology_preview_ready", False)),
        topology_readiness_label=str(preview_topology_fields.get("topology_readiness_label", "") or ""),
        exact_topology_candidate=bool(preview_topology_fields.get("exact_topology_candidate", False)),
        exact_topology_promoted=bool(preview_topology_fields.get("exact_topology_promoted", False)),
    )
    if topology_graph:
        bridge_mode = "payload_exact_topology_graph"
        family_assumption = "payload_exact_topology"
        accepted_type_label = f"exact_topology_edge={len(topology_graph['edges'])}"

    nodes: dict[int, tuple[float, float, float]] = {}
    node_lookup: dict[tuple[float, float, float], int] = {}
    elements: list[dict[str, Any]] = []
    edges: list[tuple[int, int]] = []
    node_id = 1

    bbox_min = [float("inf"), float("inf"), float("inf")]
    bbox_max = [float("-inf"), float("-inf"), float("-inf")]

    if topology_graph:
        nodes = dict(topology_graph["nodes"])
        for coord in nodes.values():
            for axis in range(3):
                bbox_min[axis] = min(bbox_min[axis], float(coord[axis]))
                bbox_max[axis] = max(bbox_max[axis], float(coord[axis]))
        for element_id, (start_id, end_id) in enumerate(topology_graph["edges"], start=1):
            edges.append((int(start_id), int(end_id)))
            elements.append(
                {
                    "id": int(element_id),
                    "type": "BEAM",
                    "family": family_assumption,
                    "node_ids": [int(start_id), int(end_id)],
                    "section_id": -1,
                    "material_id": -1,
                    "source_table": str(preview.get("source_table", "") or report_summary.get("geometry_preview_source_table", "")),
                    "preview_mode": str(preview.get("mode", "") or "heuristic_xy_segment_preview"),
                    "bridge_mode": bridge_mode,
                }
            )
    else:
        for element_id, row in enumerate(segment_rows, start=1):
            point_keys = [
                _point_key(row["x1"], row["y1"], 0.0),
                _point_key(row["x2"], row["y2"], 0.0),
            ]
            node_ids: list[int] = []
            for key in point_keys:
                for axis in range(3):
                    bbox_min[axis] = min(bbox_min[axis], key[axis])
                    bbox_max[axis] = max(bbox_max[axis], key[axis])
                if key not in node_lookup:
                    node_lookup[key] = node_id
                    nodes[node_id] = key
                    node_id += 1
                node_ids.append(node_lookup[key])
            if node_ids[0] == node_ids[1]:
                continue
            edge = (min(node_ids[0], node_ids[1]), max(node_ids[0], node_ids[1]))
            edges.append(edge)
            elements.append(
                {
                    "id": int(element_id),
                    "type": "BEAM",
                    "family": family_assumption,
                    "node_ids": node_ids,
                    "section_id": -1,
                    "material_id": -1,
                    "source_table": str(preview.get("source_table", "") or report_summary.get("geometry_preview_source_table", "")),
                    "preview_mode": str(preview.get("mode", "") or "heuristic_xy_segment_preview"),
                    "bridge_mode": bridge_mode,
                }
            )

    if not elements:
        report.update({"contract_pass": False, "reason_code": "ERR_NO_VIEWABLE_SEGMENTS"})
        _write_json(report_out, report)
        return 1

    edge_rows = sorted(set(edges))
    model_payload = {
        "schema_version": "1.0",
        "source_provenance": {
            "source_family": "midas_binary_decoded_preview_bridge",
            "source_id": source_id,
            "path": str(inventory_json_path),
        },
        "model": {
            "nodes": [
                {"id": int(current_id), "x": float(coord[0]), "y": float(coord[1]), "z": float(coord[2])}
                for current_id, coord in sorted(nodes.items())
            ],
            "elements": elements,
            "materials": [],
            "sections": [],
            "loads": {},
            "metadata": {
                "bridge_family": "decoded_preview_baseline",
                "family_assumption": family_assumption,
                "accepted_type_label": accepted_type_label,
                "selected_member_name": str(refresh_report.get("selected_member_name", "") or ""),
                "preview_state_label": preview_state_label,
                "preview_mode": str(preview.get("mode", "") or "heuristic_xy_segment_preview"),
                "preview_basis": preview_basis,
                "preview_projection_label": projection_label,
                "preview_anchor_table_names": anchor_table_names,
                "bridge_mode": bridge_mode,
                "source_table": source_table,
                **preview_topology_fields,
                **preview_exactness_fields,
                **surface_fields,
            },
        },
        "topology_metrics": {
            "node_count": int(len(nodes)),
            "element_count": int(len(elements)),
            "edge_count_undirected": int(len(edge_rows)),
            "beam_element_count": int(len(elements)),
            "shell_element_count": 0,
        },
    }
    _write_json(model_json_out, model_payload)
    npz_summary = _make_npz_payload(npz_out, nodes, elements, edge_rows)

    report.update(
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "preview_segment_count": int(len(elements)),
                "preview_point_count": int(len(nodes)),
                "viewer_ready": True,
                "family_assumption": family_assumption,
                "preview_state_label": preview_state_label,
                "preview_mode": str(preview.get("mode", "") or "heuristic_xy_segment_preview"),
                "preview_basis": preview_basis,
                "preview_projection_label": projection_label,
                "preview_anchor_table_names": anchor_table_names,
                "bridge_mode": bridge_mode,
                "source_table": source_table,
                **preview_topology_fields,
                **preview_exactness_fields,
                **surface_fields,
                "selected_member_name": str(refresh_report.get("selected_member_name", "") or ""),
                "reason_code": str(refresh_report.get("selected_reason_code", "") or inventory_report.get("reason_code", "") or "PASS"),
                "accepted_type_label": accepted_type_label,
                "bbox_min": [round(value, 4) for value in bbox_min],
                "bbox_max": [round(value, 4) for value in bbox_max],
                **npz_summary,
                "decoded_geometry_preview_point_count": int(
                    preview_summary.get("geometry_preview_point_count", report_summary.get("geometry_preview_point_count", 0)) or 0
                ),
                "decoded_geometry_preview_segment_count": int(
                    preview_summary.get("geometry_preview_segment_count", report_summary.get("geometry_preview_segment_count", 0)) or 0
                ),
            },
            "artifacts": {
                "decoded_inventory_json": str(inventory_json_path),
                "decoded_inventory_report": str(inventory_report_path),
                "refresh_report": str(refresh_report_path),
                "model_json": str(model_json_out),
                "dataset_npz": str(npz_out),
            },
        }
    )
    _write_json(report_out, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
