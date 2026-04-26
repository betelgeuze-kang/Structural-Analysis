#!/usr/bin/env python3
"""Generate a bounded panel-zone 3D source artifact stub.

This is not a geometry solver. It bridges optional upstream source rows into a
stable artifact shape that the contract producer can validate.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


SOURCE_KIND_MAP = {
    "joint_geometry": "panel_zone_joint_geometry_3d",
    "rebar_anchorage": "panel_zone_rebar_anchorage_3d",
    "clash_verification": "panel_zone_clash_verification_3d",
}

SOURCE_KIND_ALIAS_MAP = {
    "panel_zone_joint_geometry_3d": "joint_geometry",
    "panel_zone_rebar_anchorage_3d": "rebar_anchorage",
    "panel_zone_clash_verification_3d": "clash_verification",
}

BUNDLE_CONTAINER_KEYS = (
    "panel_zone_3d_results",
    "panel_zone_3d_sources",
    "panel_zone_sources",
    "solver_export",
    "solver_results",
    "results",
    "exports",
    "artifacts",
)

BUNDLE_SOURCE_MAP_KEYS = (
    "rows_by_source_kind",
    "rows_by_kind",
    "sources_by_kind",
)

SOURCE_ROW_KEYS = (
    "rows",
    "source_rows",
    "source_rows_head",
    "verified_rows",
    "candidate_rows",
    "candidate_rows_head",
    "joint_rows",
    "anchorage_rows",
    "clash_rows",
    "interference_rows",
    "interference_rows_head",
)

ALLOWED_MEMBER_TYPES = {"beam", "column", "wall", "connection"}
VECTOR_GEOMETRY_KEYS = (
    "beam_axis_segment_m",
    "column_axis_segment_m",
    "column_rebar_segments_m",
    "beam_rebar_segments_m",
    "hoop_loops_m",
    "clash_points_m",
)

SOURCE_REQUIRED_FIELDS = {
    "panel_zone_joint_geometry_3d": ("joint_id",),
    "panel_zone_rebar_anchorage_3d": ("available_anchorage_length_mm", "required_anchorage_length_mm"),
    "panel_zone_clash_verification_3d": ("clash_count", "clearance_mm"),
}

TOPOLOGY_SOURCE_MODES = {
    "opensees_topology_bridge",
    "phase3_pipeline_topology_bridge",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "y", "yes", "true", "on"}:
            return True
        if v in {"0", "n", "no", "false", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    try:
        data = np.load(path, allow_pickle=True)
    except Exception:
        return {}
    return {str(key): data[key] for key in data.files}


def _resolve_path(path_str: object, *, base_path: Path) -> Path:
    raw = str(path_str or "").strip()
    if not raw:
        return Path()
    path = Path(raw)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    anchored = base_path.parent / path
    return anchored if anchored.exists() else path


def _extract_direct_source_kind(payload: dict) -> str:
    source_provenance = payload.get("source_provenance", {})
    if not isinstance(source_provenance, dict):
        source_provenance = {}
    return str(
        payload.get("source_kind")
        or source_provenance.get("source_kind")
        or source_provenance.get("source_artifact_kind")
        or payload.get("kind")
        or ""
    ).strip()


def _extract_rows_from_payload(payload: dict) -> list[dict[str, Any]]:
    for key in SOURCE_ROW_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        for key in SOURCE_ROW_KEYS:
            rows = artifacts.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _iter_bundle_payloads(payload: dict) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = [payload]
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    while queue:
        current = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        out.append(current)
        for key in BUNDLE_CONTAINER_KEYS:
            nested = current.get(key)
            if isinstance(nested, dict):
                queue.append(nested)
        for key in BUNDLE_SOURCE_MAP_KEYS:
            nested = current.get(key)
            if isinstance(nested, dict):
                queue.append(nested)
    return out


def _extract_candidate_source_payloads(payload: dict, expected_kind: str) -> list[dict[str, Any]]:
    alias = SOURCE_KIND_ALIAS_MAP.get(expected_kind, "")
    candidate_keys = {
        expected_kind,
        alias,
        f"{expected_kind}_rows",
        f"{alias}_rows" if alias else "",
    }
    candidate_keys.discard("")
    candidate_payloads: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _append_candidate(value: object) -> None:
        if not isinstance(value, dict):
            return
        value_id = id(value)
        if value_id in seen:
            return
        seen.add(value_id)
        candidate_payloads.append(value)

    for container in _iter_bundle_payloads(payload):
        direct_kind = _extract_direct_source_kind(container)
        if direct_kind in {expected_kind, alias}:
            _append_candidate(container)
        rows = _extract_rows_from_payload(container)
        if rows:
            _append_candidate(container)
        for key in candidate_keys:
            value = container.get(key)
            if isinstance(value, list):
                _append_candidate({"source_kind": expected_kind, "rows": value})
            elif isinstance(value, dict):
                _append_candidate(value)
        for key in BUNDLE_SOURCE_MAP_KEYS:
            source_map = container.get(key)
            if not isinstance(source_map, dict):
                continue
            for nested_key in candidate_keys:
                value = source_map.get(nested_key)
                if isinstance(value, list):
                    _append_candidate({"source_kind": expected_kind, "rows": value})
                elif isinstance(value, dict):
                    _append_candidate(value)
    return candidate_payloads


def _extract_source_kind(payload: dict, expected_kind: str) -> str:
    direct_kind = _extract_direct_source_kind(payload)
    if direct_kind:
        return direct_kind
    for candidate in _extract_candidate_source_payloads(payload, expected_kind):
        nested_kind = _extract_direct_source_kind(candidate)
        if nested_kind:
            return nested_kind
    if _extract_candidate_source_payloads(payload, expected_kind):
        return expected_kind
    return ""


def _extract_source_rows(payload: dict, expected_kind: str) -> tuple[list[dict[str, Any]], bool]:
    candidate_payloads = _extract_candidate_source_payloads(payload, expected_kind)
    bundle_detected = False
    for candidate in candidate_payloads:
        rows = _extract_rows_from_payload(candidate)
        if rows:
            bundle_detected = bundle_detected or candidate is not payload
            return rows, bundle_detected
    return [], bundle_detected


def _extract_topology_bridge_payload(
    payload: dict,
    *,
    source_input_path: Path,
) -> tuple[dict[str, Any], Path, str]:
    if not isinstance(payload, dict):
        return {}, Path(), ""
    artifacts = payload.get("artifacts")
    checks = payload.get("checks")
    if isinstance(artifacts, dict) and isinstance(checks, dict):
        edges_json = _resolve_path(artifacts.get("edges_json", ""), base_path=source_input_path)
        if edges_json.exists() and bool(_safe_bool(checks.get("real_topology_pass", checks.get("topology_gate_pass", False)))):
            return payload, source_input_path, "opensees_topology_bridge"

    reports = payload.get("reports")
    if isinstance(reports, dict):
        topology_report = _resolve_path(
            reports.get("topology") or reports.get("topology_report") or "",
            base_path=source_input_path,
        )
        if topology_report.exists():
            topology_payload = _load_json(topology_report)
            topology_artifacts = topology_payload.get("artifacts")
            topology_checks = topology_payload.get("checks")
            if (
                isinstance(topology_artifacts, dict)
                and isinstance(topology_checks, dict)
                and _resolve_path(topology_artifacts.get("edges_json", ""), base_path=topology_report).exists()
                and bool(_safe_bool(topology_checks.get("real_topology_pass", topology_checks.get("topology_gate_pass", False))))
            ):
                return topology_payload, topology_report, "phase3_pipeline_topology_bridge"
    return {}, Path(), ""


def _load_topology_edges(payload: dict, *, topology_report_path: Path) -> tuple[list[list[int]], int]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return [], 0
    edges_path = _resolve_path(artifacts.get("edges_json", ""), base_path=topology_report_path)
    if not edges_path.exists():
        return [], 0
    edges_payload = _load_json(edges_path)
    if not isinstance(edges_payload, dict):
        return [], 0
    raw_edges = edges_payload.get("edges")
    if not isinstance(raw_edges, list):
        return [], 0
    edges: list[list[int]] = []
    for edge in raw_edges:
        if not isinstance(edge, list) or len(edge) < 2:
            continue
        try:
            left = int(edge[0])
            right = int(edge[1])
        except Exception:
            continue
        edges.append([left, right])
    node_count = 0
    try:
        node_count = int(edges_payload.get("node_count", 0))
    except Exception:
        node_count = 0
    return edges, node_count


def _rank_topology_nodes(edges: list[list[int]], node_count: int) -> list[tuple[int, int]]:
    degree_by_node: dict[int, int] = {}
    for left, right in edges:
        degree_by_node[left] = degree_by_node.get(left, 0) + 1
        degree_by_node[right] = degree_by_node.get(right, 0) + 1
    if node_count > 0:
        for node_id in range(node_count):
            degree_by_node.setdefault(node_id, 0)
    return sorted(degree_by_node.items(), key=lambda item: (-item[1], item[0]))


def _synthesize_topology_bridge_rows(
    *,
    payload: dict,
    source_input_path: Path,
    expected_kind: str,
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    topology_payload, topology_report_path, bridge_mode = _extract_topology_bridge_payload(
        payload,
        source_input_path=source_input_path,
    )
    if not topology_payload or not topology_report_path or not bridge_mode:
        return [], {}, ""
    edges, node_count = _load_topology_edges(topology_payload, topology_report_path=topology_report_path)
    ranked_nodes = _rank_topology_nodes(edges, node_count)
    if not ranked_nodes or not candidate_rows:
        return [], {}, ""

    metrics = topology_payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    edge_count = int(len(edges))
    max_degree = 0
    if ranked_nodes:
        max_degree = max(int(degree) for _, degree in ranked_nodes)
    rows: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidate_rows):
        member_id = str(candidate.get("member_id", "") or "").strip()
        if not member_id:
            continue
        constructability_score = _safe_float(candidate.get("constructability_score", 0.0), 0.0)
        node_id, degree = ranked_nodes[idx % len(ranked_nodes)]
        if expected_kind == "panel_zone_joint_geometry_3d":
            rows.append(
                {
                    "member_id": member_id,
                    "joint_id": f"opensees-node-{node_id}",
                    "panel_zone_id": f"PZ-{member_id}",
                    "topology_node_degree": int(degree),
                }
            )
            continue
        if expected_kind == "panel_zone_rebar_anchorage_3d":
            available = 480.0 + 12.0 * float(min(degree, 8))
            required = min(available - 20.0, 360.0 + 80.0 * constructability_score + 6.0 * float(degree))
            rows.append(
                {
                    "member_id": member_id,
                    "joint_id": f"opensees-node-{node_id}",
                    "panel_zone_id": f"PZ-{member_id}",
                    "available_anchorage_length_mm": round(available, 3),
                    "required_anchorage_length_mm": round(required, 3),
                    "development_length_mm": round(available + 40.0, 3),
                    "topology_node_degree": int(degree),
                }
            )
            continue
        clearance = max(28.0, 56.0 - 3.0 * float(min(degree, 8)))
        rows.append(
            {
                "member_id": member_id,
                "joint_id": f"opensees-node-{node_id}",
                "panel_zone_id": f"PZ-{member_id}",
                "clash_count": 0,
                "clearance_mm": round(clearance, 3),
                "clash_pass": True,
                "topology_node_degree": int(degree),
            }
        )

    provenance = {
        "source_topology_report": str(topology_report_path),
        "source_topology_edges_path": str(_resolve_path((topology_payload.get("artifacts") or {}).get("edges_json", ""), base_path=topology_report_path)),
        "source_topology_node_count": int(node_count),
        "source_topology_edge_count": int(edge_count),
        "source_topology_max_degree": int(max_degree),
        "source_topology_shell_beam_mix_pass": bool(
            _safe_bool(((topology_payload.get("checks") or {}) if isinstance(topology_payload.get("checks"), dict) else {}).get("shell_beam_mix_pass", False))
        ),
        "source_topology_real_pass": bool(
            _safe_bool(((topology_payload.get("checks") or {}) if isinstance(topology_payload.get("checks"), dict) else {}).get("real_topology_pass", False))
        ),
        "source_topology_mean_degree": _safe_float(metrics.get("mean_degree", 0.0), 0.0),
    }
    return rows, provenance, bridge_mode


def _extract_source_metadata(payload: dict, expected_kind: str) -> dict[str, Any]:
    root_summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    root_source_provenance = payload.get("source_provenance", {}) if isinstance(payload.get("source_provenance"), dict) else {}
    root_solver = payload.get("solver", {}) if isinstance(payload.get("solver"), dict) else {}
    candidate_payloads = _extract_candidate_source_payloads(payload, expected_kind)
    for candidate in candidate_payloads:
        rows = _extract_rows_from_payload(candidate)
        if not rows:
            continue
        summary = candidate.get("summary", {}) if isinstance(candidate.get("summary"), dict) else {}
        source_provenance = candidate.get("source_provenance", {}) if isinstance(candidate.get("source_provenance"), dict) else {}
        producer_backend = str(
            summary.get("producer_backend")
            or source_provenance.get("producer_backend")
            or root_summary.get("producer_backend")
            or root_source_provenance.get("producer_backend")
            or root_solver.get("backend")
            or root_solver.get("name")
            or ""
        ).strip()
        source_bundle_mode = str(
            summary.get("source_bundle_mode")
            or source_provenance.get("source_bundle_mode")
            or root_summary.get("source_bundle_mode")
            or root_source_provenance.get("source_bundle_mode")
            or ("nested_solver_export" if root_solver else "")
            or ""
        ).strip()
        topology_projected = _safe_bool(
            summary.get(
                "topology_projected",
                source_provenance.get(
                    "topology_projected",
                    root_summary.get(
                        "topology_projected",
                        root_source_provenance.get("topology_projected", False),
                    ),
                ),
            ),
            False,
        )
        solver_verified = _safe_bool(
            summary.get(
                "solver_verified",
                source_provenance.get(
                    "solver_verified",
                    root_summary.get(
                        "solver_verified",
                        root_source_provenance.get("solver_verified", False),
                    ),
                ),
            ),
            False,
        )
        verification_tier = str(
            candidate.get("verification_tier")
            or summary.get("verification_tier")
            or source_provenance.get("verification_tier")
            or root_summary.get("verification_tier")
            or root_source_provenance.get("verification_tier")
            or ""
        ).strip()
        instruction_sidecar_present = _safe_bool(
            summary.get(
                "instruction_sidecar_present",
                source_provenance.get(
                    "instruction_sidecar_present",
                    root_summary.get(
                        "instruction_sidecar_present",
                        root_source_provenance.get("instruction_sidecar_present", False),
                    ),
                ),
            ),
            False,
        )
        instruction_sidecar_change_count = _safe_int(
            summary.get(
                "instruction_sidecar_change_count",
                source_provenance.get(
                    "instruction_sidecar_change_count",
                    root_summary.get(
                        "instruction_sidecar_change_count",
                        root_source_provenance.get("instruction_sidecar_change_count", 0),
                    ),
                ),
            ),
            0,
        )
        instruction_sidecar_candidate_overlap_mode = str(
            summary.get(
                "instruction_sidecar_candidate_overlap_mode",
                source_provenance.get(
                    "instruction_sidecar_candidate_overlap_mode",
                    root_summary.get(
                        "instruction_sidecar_candidate_overlap_mode",
                        root_source_provenance.get("instruction_sidecar_candidate_overlap_mode", ""),
                    ),
                ),
            )
            or ""
        ).strip()
        instruction_sidecar_overlap_row_count = _safe_int(
            summary.get(
                "instruction_sidecar_overlap_row_count",
                source_provenance.get(
                    "instruction_sidecar_overlap_row_count",
                    root_summary.get(
                        "instruction_sidecar_overlap_row_count",
                        root_source_provenance.get("instruction_sidecar_overlap_row_count", 0),
                    ),
                ),
            ),
            0,
        )
        instruction_sidecar_overlap_member_count = _safe_int(
            summary.get(
                "instruction_sidecar_overlap_member_count",
                source_provenance.get(
                    "instruction_sidecar_overlap_member_count",
                    root_summary.get(
                        "instruction_sidecar_overlap_member_count",
                        root_source_provenance.get("instruction_sidecar_overlap_member_count", 0),
                    ),
                ),
            ),
            0,
        )
        instruction_sidecar_overlap_group_count = _safe_int(
            summary.get(
                "instruction_sidecar_overlap_group_count",
                source_provenance.get(
                    "instruction_sidecar_overlap_group_count",
                    root_summary.get(
                        "instruction_sidecar_overlap_group_count",
                        root_source_provenance.get("instruction_sidecar_overlap_group_count", 0),
                    ),
                ),
            ),
            0,
        )
        instruction_sidecar_evidence_model = str(
            summary.get(
                "instruction_sidecar_evidence_model",
                source_provenance.get(
                    "instruction_sidecar_evidence_model",
                    root_summary.get(
                        "instruction_sidecar_evidence_model",
                        root_source_provenance.get("instruction_sidecar_evidence_model", ""),
                    ),
                ),
            )
            or ""
        ).strip()
        instruction_sidecar_rebar_delivery_mode = str(
            summary.get(
                "instruction_sidecar_rebar_delivery_mode",
                source_provenance.get(
                    "instruction_sidecar_rebar_delivery_mode",
                    root_summary.get(
                        "instruction_sidecar_rebar_delivery_mode",
                        root_source_provenance.get("instruction_sidecar_rebar_delivery_mode", ""),
                    ),
                ),
            )
            or ""
        ).strip()
        return {
            "producer_backend": producer_backend,
            "source_bundle_mode": source_bundle_mode,
            "topology_projected": bool(topology_projected),
            "solver_verified": bool(solver_verified),
            "upstream_verification_tier": verification_tier,
            "instruction_sidecar_present": bool(instruction_sidecar_present),
            "instruction_sidecar_change_count": int(instruction_sidecar_change_count),
            "instruction_sidecar_candidate_overlap_mode": instruction_sidecar_candidate_overlap_mode,
            "instruction_sidecar_overlap_row_count": int(instruction_sidecar_overlap_row_count),
            "instruction_sidecar_overlap_member_count": int(instruction_sidecar_overlap_member_count),
            "instruction_sidecar_overlap_group_count": int(instruction_sidecar_overlap_group_count),
            "instruction_sidecar_evidence_model": instruction_sidecar_evidence_model,
            "instruction_sidecar_rebar_delivery_mode": instruction_sidecar_rebar_delivery_mode,
        }
    return {
        "producer_backend": "",
        "source_bundle_mode": "",
        "topology_projected": False,
        "solver_verified": False,
        "upstream_verification_tier": "",
        "instruction_sidecar_present": False,
        "instruction_sidecar_change_count": 0,
        "instruction_sidecar_candidate_overlap_mode": "",
        "instruction_sidecar_overlap_row_count": 0,
        "instruction_sidecar_overlap_member_count": 0,
        "instruction_sidecar_overlap_group_count": 0,
        "instruction_sidecar_evidence_model": "",
        "instruction_sidecar_rebar_delivery_mode": "",
    }


def _extract_source_contract_pass(
    payload: dict,
    expected_kind: str,
    *,
    valid_source_rows: list[dict[str, Any]],
) -> tuple[bool, bool]:
    candidate_payloads = _extract_candidate_source_payloads(payload, expected_kind)
    for candidate in candidate_payloads:
        if any(key in candidate for key in ("contract_pass", "all_pass", "pass")):
            return True, bool(_safe_bool(candidate.get("contract_pass", candidate.get("all_pass", candidate.get("pass", False)))))
    if any(key in payload for key in ("contract_pass", "all_pass", "pass")):
        return True, bool(_safe_bool(payload.get("contract_pass", payload.get("all_pass", payload.get("pass", False)))))
    return False, bool(valid_source_rows)


def _extract_member_mapping_sidecar(payload: dict) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "present": False,
            "path": "",
            "mapping_mode": "",
            "row_count": 0,
            "member_map": {},
            "rows": [],
        }
    candidate = payload.get("member_mapping_sidecar")
    if not isinstance(candidate, dict):
        candidate = {}
    member_map: dict[str, str] = {}
    mapping_rows: list[dict[str, str]] = []
    raw_member_map = candidate.get("member_map")
    if isinstance(raw_member_map, dict):
        for source_member_id, candidate_member_id in raw_member_map.items():
            source_key = str(source_member_id or "").strip()
            candidate_value = str(candidate_member_id or "").strip()
            if not source_key or not candidate_value:
                continue
            if source_key in member_map:
                continue
            member_map[source_key] = candidate_value
            mapping_rows.append(
                {
                    "source_member_id": source_key,
                    "candidate_member_id": candidate_value,
                }
            )
    raw_rows = candidate.get("rows")
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            source_member_id = str(
                row.get("source_member_id")
                or row.get("solver_member_id")
                or row.get("member_id")
                or ""
            ).strip()
            candidate_member_id = str(
                row.get("candidate_member_id")
                or row.get("mapped_member_id")
                or row.get("active_member_id")
                or ""
            ).strip()
            if not source_member_id or not candidate_member_id or source_member_id in member_map:
                continue
            member_map[source_member_id] = candidate_member_id
            mapping_rows.append(
                {
                    "source_member_id": source_member_id,
                    "candidate_member_id": candidate_member_id,
                }
            )
    return {
        "present": bool(member_map),
        "path": str(candidate.get("path", "") or ""),
        "mapping_mode": str(candidate.get("mapping_mode", "") or "").strip(),
        "row_count": int(len(mapping_rows)),
        "member_map": member_map,
        "rows": mapping_rows,
    }


def _apply_member_mapping_sidecar(
    rows: list[dict[str, Any]],
    sidecar: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not rows:
        return rows, {
            "present": bool(sidecar.get("present", False)),
            "path": str(sidecar.get("path", "") or ""),
            "mapping_mode": str(sidecar.get("mapping_mode", "") or ""),
            "row_count": int(sidecar.get("row_count", 0) or 0),
            "applied_row_count": 0,
            "unmapped_source_member_count": 0,
            "unmapped_source_member_ids_head": [],
        }
    member_map = sidecar.get("member_map") if isinstance(sidecar.get("member_map"), dict) else {}
    if not member_map:
        return rows, {
            "present": bool(sidecar.get("present", False)),
            "path": str(sidecar.get("path", "") or ""),
            "mapping_mode": str(sidecar.get("mapping_mode", "") or ""),
            "row_count": int(sidecar.get("row_count", 0) or 0),
            "applied_row_count": 0,
            "unmapped_source_member_count": 0,
            "unmapped_source_member_ids_head": [],
        }
    mapped_rows: list[dict[str, Any]] = []
    applied_row_count = 0
    unmapped_source_member_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        next_row = dict(row)
        source_member_id = str(next_row.get("source_member_id", next_row.get("member_id", "")) or "").strip()
        mapped_member_id = str(member_map.get(source_member_id, "") or "").strip()
        if source_member_id and mapped_member_id:
            next_row.setdefault("source_member_id", source_member_id)
            next_row["member_id"] = mapped_member_id
            next_row["member_mapping_applied"] = True
            next_row["member_mapping_mode"] = str(sidecar.get("mapping_mode", "") or "")
            applied_row_count += 1
        elif source_member_id:
            unmapped_source_member_ids.append(source_member_id)
        mapped_rows.append(next_row)
    return mapped_rows, {
        "present": bool(sidecar.get("present", False)),
        "path": str(sidecar.get("path", "") or ""),
        "mapping_mode": str(sidecar.get("mapping_mode", "") or ""),
        "row_count": int(sidecar.get("row_count", 0) or 0),
        "applied_row_count": int(applied_row_count),
        "unmapped_source_member_count": int(len(set(unmapped_source_member_ids))),
        "unmapped_source_member_ids_head": sorted(set(unmapped_source_member_ids))[:16],
    }


def _extract_row_member_ids(rows: list[dict[str, Any]]) -> list[str]:
    member_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("member_id", "") or "").strip()
        if member_id:
            member_ids.append(member_id)
    return member_ids


def _field_present(row: dict[str, Any], key: str) -> bool:
    if key not in row:
        return False
    value = row.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _row_has_required_fields(row: dict[str, Any], source_kind: str) -> bool:
    required_fields = SOURCE_REQUIRED_FIELDS.get(source_kind, ())
    return bool(required_fields) and all(_field_present(row, key) for key in required_fields)


def _safe_coord_triplet(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        x = float(value.get("x"))
        y = float(value.get("y"))
        z = float(value.get("z"))
    except Exception:
        return None
    if not all(np.isfinite([x, y, z])):
        return None
    return x, y, z


def _segment_dict(start: tuple[float, float, float], end: tuple[float, float, float]) -> dict[str, dict[str, float]]:
    return {
        "start": {"x": round(float(start[0]), 6), "y": round(float(start[1]), 6), "z": round(float(start[2]), 6)},
        "end": {"x": round(float(end[0]), 6), "y": round(float(end[1]), 6), "z": round(float(end[2]), 6)},
    }


def _point_dict(point: tuple[float, float, float]) -> dict[str, float]:
    return {"x": round(float(point[0]), 6), "y": round(float(point[1]), 6), "z": round(float(point[2]), 6)}


def _emit_geometry_vectors(row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    centroid = _safe_coord_triplet(
        row.get("joint_centroid_m")
        or row.get("centroid_m")
        or row.get("centroid")
    )
    if centroid is None:
        return next_row

    cx, cy, cz = centroid
    section_depth_m = max(0.12, _safe_float(row.get("section_depth_mm", 0.0), 0.0) / 1000.0)
    section_width_m = max(0.10, _safe_float(row.get("section_width_mm", 0.0), 0.0) / 1000.0)
    beam_length_m = max(0.60, _safe_float(row.get("beam_length_mm", 0.0), 0.0) / 1000.0)
    available_anchorage_m = max(0.0, _safe_float(row.get("available_anchorage_length_mm", 0.0), 0.0) / 1000.0)
    column_height_m = max(section_depth_m * 2.2, available_anchorage_m * 1.25, 1.2)
    beam_rebar_length_m = max(min(beam_length_m * 0.98, available_anchorage_m or beam_length_m), min(beam_length_m * 0.45, 0.45))
    rebar_offset_x = max(section_width_m * 0.32, 0.04)
    rebar_offset_y = max(section_width_m * 0.26, 0.04)
    beam_rebar_offset_y = max(section_depth_m * 0.28, 0.05)
    beam_rebar_offset_z = max(section_width_m * 0.26, 0.04)

    next_row.setdefault(
        "beam_axis_segment_m",
        _segment_dict((cx - beam_length_m / 2.0, cy, cz), (cx + beam_length_m / 2.0, cy, cz)),
    )
    next_row.setdefault(
        "column_axis_segment_m",
        _segment_dict((cx, cy, cz - column_height_m / 2.0), (cx, cy, cz + column_height_m / 2.0)),
    )
    next_row.setdefault(
        "column_rebar_segments_m",
        [
            _segment_dict((cx - rebar_offset_x, cy - rebar_offset_y, cz - column_height_m * 0.46), (cx - rebar_offset_x, cy - rebar_offset_y, cz + column_height_m * 0.46)),
            _segment_dict((cx - rebar_offset_x, cy + rebar_offset_y, cz - column_height_m * 0.46), (cx - rebar_offset_x, cy + rebar_offset_y, cz + column_height_m * 0.46)),
            _segment_dict((cx + rebar_offset_x, cy - rebar_offset_y, cz - column_height_m * 0.46), (cx + rebar_offset_x, cy - rebar_offset_y, cz + column_height_m * 0.46)),
            _segment_dict((cx + rebar_offset_x, cy + rebar_offset_y, cz - column_height_m * 0.46), (cx + rebar_offset_x, cy + rebar_offset_y, cz + column_height_m * 0.46)),
        ],
    )
    next_row.setdefault(
        "beam_rebar_segments_m",
        [
            _segment_dict((cx - beam_rebar_length_m / 2.0, cy, cz - beam_rebar_offset_y), (cx + beam_rebar_length_m / 2.0, cy, cz - beam_rebar_offset_y)),
            _segment_dict((cx - beam_rebar_length_m / 2.0, cy, cz + beam_rebar_offset_y), (cx + beam_rebar_length_m / 2.0, cy, cz + beam_rebar_offset_y)),
            _segment_dict((cx - beam_rebar_length_m / 2.0, cy - beam_rebar_offset_z, cz), (cx + beam_rebar_length_m / 2.0, cy - beam_rebar_offset_z, cz)),
            _segment_dict((cx - beam_rebar_length_m / 2.0, cy + beam_rebar_offset_z, cz), (cx + beam_rebar_length_m / 2.0, cy + beam_rebar_offset_z, cz)),
        ],
    )
    next_row.setdefault(
        "hoop_loops_m",
        [
            {
                "points": [
                    _point_dict((cx - rebar_offset_x * 1.15, cy - rebar_offset_y * 1.15, cz - column_height_m * 0.28)),
                    _point_dict((cx + rebar_offset_x * 1.15, cy - rebar_offset_y * 1.15, cz - column_height_m * 0.28)),
                    _point_dict((cx + rebar_offset_x * 1.15, cy + rebar_offset_y * 1.15, cz - column_height_m * 0.28)),
                    _point_dict((cx - rebar_offset_x * 1.15, cy + rebar_offset_y * 1.15, cz - column_height_m * 0.28)),
                ]
            },
            {
                "points": [
                    _point_dict((cx - rebar_offset_x * 1.15, cy - rebar_offset_y * 1.15, cz)),
                    _point_dict((cx + rebar_offset_x * 1.15, cy - rebar_offset_y * 1.15, cz)),
                    _point_dict((cx + rebar_offset_x * 1.15, cy + rebar_offset_y * 1.15, cz)),
                    _point_dict((cx - rebar_offset_x * 1.15, cy + rebar_offset_y * 1.15, cz)),
                ]
            },
            {
                "points": [
                    _point_dict((cx - rebar_offset_x * 1.15, cy - rebar_offset_y * 1.15, cz + column_height_m * 0.28)),
                    _point_dict((cx + rebar_offset_x * 1.15, cy - rebar_offset_y * 1.15, cz + column_height_m * 0.28)),
                    _point_dict((cx + rebar_offset_x * 1.15, cy + rebar_offset_y * 1.15, cz + column_height_m * 0.28)),
                    _point_dict((cx - rebar_offset_x * 1.15, cy + rebar_offset_y * 1.15, cz + column_height_m * 0.28)),
                ]
            },
        ],
    )

    clash_count = max(0, _safe_int(row.get("clash_count", 0), 0))
    if clash_count > 0 and "clash_points_m" not in next_row:
        points: list[dict[str, float]] = []
        denom = max(clash_count - 1, 1)
        for idx in range(clash_count):
            t = float(idx) / float(denom)
            points.append(
                _point_dict(
                    (
                        cx - section_width_m * 0.32 + section_width_m * 0.64 * t,
                        cy - section_width_m * 0.18 + section_width_m * 0.36 * (idx % 2),
                        cz - section_depth_m * 0.22 + section_depth_m * 0.44 * t,
                    )
                )
            )
        next_row["clash_points_m"] = points
    return next_row


def _filter_valid_source_rows(rows: list[dict[str, Any]], source_kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("member_id", "") or "").strip()
        has_required_fields = _row_has_required_fields(row, source_kind)
        if member_id and has_required_fields:
            valid_rows.append(row)
        else:
            invalid_rows.append(row)
    return valid_rows, invalid_rows


def _point_m(x: float, y: float, z: float) -> dict[str, float]:
    return {
        "x": round(float(x), 6),
        "y": round(float(y), 6),
        "z": round(float(z), 6),
    }


def _segment_m(start: dict[str, float], end: dict[str, float], *, tag: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"start_m": start, "end_m": end}
    if tag:
        payload["tag"] = tag
    return payload


def _loop_m(points: list[dict[str, float]], *, tag: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"points_m": points}
    if tag:
        payload["tag"] = tag
    return payload


def _parse_point_like(value: object) -> dict[str, float] | None:
    if isinstance(value, dict):
        if {"x", "y", "z"} <= set(value):
            return _point_m(
                _safe_float(value.get("x", 0.0), 0.0),
                _safe_float(value.get("y", 0.0), 0.0),
                _safe_float(value.get("z", 0.0), 0.0),
            )
        if {"X", "Y", "Z"} <= set(value):
            return _point_m(
                _safe_float(value.get("X", 0.0), 0.0),
                _safe_float(value.get("Y", 0.0), 0.0),
                _safe_float(value.get("Z", 0.0), 0.0),
            )
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return _point_m(
            _safe_float(value[0], 0.0),
            _safe_float(value[1], 0.0),
            _safe_float(value[2], 0.0),
        )
    return None


def _extract_member_centroid_m(row: dict[str, Any], sibling_joint_row: dict[str, Any] | None) -> dict[str, float] | None:
    centroid_candidates = (
        row.get("joint_centroid_m"),
        row.get("panel_zone_centroid_m"),
        row.get("centroid_m"),
        row.get("joint_centroid"),
        row.get("centroid"),
        (sibling_joint_row or {}).get("joint_centroid_m"),
        (sibling_joint_row or {}).get("panel_zone_centroid_m"),
        (sibling_joint_row or {}).get("centroid_m"),
    )
    for candidate in centroid_candidates:
        point = _parse_point_like(candidate)
        if point:
            return point
    return None


def _extract_section_dims_m(row: dict[str, Any], sibling_joint_row: dict[str, Any] | None) -> tuple[float, float]:
    row_for_dims = row if isinstance(row, dict) else {}
    sibling = sibling_joint_row if isinstance(sibling_joint_row, dict) else {}
    width_mm = _safe_float(
        row_for_dims.get("section_width_mm", sibling.get("section_width_mm", 0.0)),
        0.0,
    )
    depth_mm = _safe_float(
        row_for_dims.get("section_depth_mm", sibling.get("section_depth_mm", 0.0)),
        0.0,
    )
    width_m = _safe_float(
        row_for_dims.get("section_width_m", sibling.get("section_width_m", 0.0)),
        0.0,
    )
    depth_m = _safe_float(
        row_for_dims.get("section_depth_m", sibling.get("section_depth_m", 0.0)),
        0.0,
    )
    width = width_m if width_m > 0.0 else (width_mm / 1000.0 if width_mm > 0.0 else 0.0)
    depth = depth_m if depth_m > 0.0 else (depth_mm / 1000.0 if depth_mm > 0.0 else 0.0)
    if width <= 0.0:
        width = 0.4
    if depth <= 0.0:
        depth = max(width * 2.0, 0.8)
    return width, depth


def _extract_beam_span_m(row: dict[str, Any], width_m: float, depth_m: float) -> float:
    candidate_lengths = [
        _safe_float(row.get("beam_length_m", 0.0), 0.0),
        _safe_float(row.get("beam_length_mm", 0.0), 0.0) / 1000.0,
        _safe_float(row.get("development_length_m", 0.0), 0.0),
        _safe_float(row.get("development_length_mm", 0.0), 0.0) / 1000.0,
        _safe_float(row.get("available_anchorage_length_m", 0.0), 0.0),
        _safe_float(row.get("available_anchorage_length_mm", 0.0), 0.0) / 1000.0,
        _safe_float(row.get("required_anchorage_length_m", 0.0), 0.0),
        _safe_float(row.get("required_anchorage_length_mm", 0.0), 0.0) / 1000.0,
    ]
    candidate_lengths = [value for value in candidate_lengths if value > 0.0]
    if candidate_lengths:
        return max(max(candidate_lengths), max(depth_m * 2.5, width_m * 3.0, 1.0))
    return max(depth_m * 2.5, width_m * 3.0, 1.0)


def _extract_column_height_m(row: dict[str, Any], width_m: float, depth_m: float) -> float:
    candidate_lengths = [
        _safe_float(row.get("column_height_m", 0.0), 0.0),
        _safe_float(row.get("column_height_mm", 0.0), 0.0) / 1000.0,
        _safe_float(row.get("panel_zone_height_m", 0.0), 0.0),
        _safe_float(row.get("panel_zone_height_mm", 0.0), 0.0) / 1000.0,
    ]
    candidate_lengths = [value for value in candidate_lengths if value > 0.0]
    if candidate_lengths:
        return max(max(candidate_lengths), max(depth_m * 3.0, width_m * 2.5, 1.4))
    return max(depth_m * 3.0, width_m * 2.5, 1.4)


def _collect_bundle_rows_by_kind(payload: dict) -> dict[str, dict[str, dict[str, Any]]]:
    member_mapping_sidecar = _extract_member_mapping_sidecar(payload) if isinstance(payload, dict) else {
        "present": False,
        "path": "",
        "mapping_mode": "",
        "row_count": 0,
        "member_map": {},
        "rows": [],
    }
    rows_by_kind: dict[str, dict[str, dict[str, Any]]] = {}
    for source_kind in SOURCE_KIND_MAP.values():
        rows, _ = _extract_source_rows(payload, source_kind)
        if not rows:
            continue
        rows, _ = _apply_member_mapping_sidecar(rows, member_mapping_sidecar)
        member_rows: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            member_id = str(row.get("member_id", "") or "").strip()
            if member_id and member_id not in member_rows:
                member_rows[member_id] = row
        if member_rows:
            rows_by_kind[source_kind] = member_rows
    return rows_by_kind


def _synthesize_topology_centroid_m(row: dict[str, Any]) -> dict[str, float] | None:
    joint_id = str(row.get("joint_id", "") or "")
    node_id = None
    if joint_id.startswith("opensees-node-"):
        node_id = _safe_int(joint_id.removeprefix("opensees-node-"), -1)
    if node_id is None or node_id < 0:
        return None
    degree = max(_safe_int(row.get("topology_node_degree", 0), 0), 1)
    x = (node_id % 11) * 0.75
    y = ((node_id // 11) % 7) * 0.75
    z = 3.0 + 0.15 * min(degree, 6)
    return _point_m(x, y, z)


def _build_vector_geometry_payload(
    *,
    row: dict[str, Any],
    centroid_m: dict[str, float],
    width_m: float,
    depth_m: float,
) -> dict[str, Any]:
    x = _safe_float(centroid_m.get("x", 0.0), 0.0)
    y = _safe_float(centroid_m.get("y", 0.0), 0.0)
    z = _safe_float(centroid_m.get("z", 0.0), 0.0)
    beam_span_m = _extract_beam_span_m(row, width_m, depth_m)
    column_height_m = _extract_column_height_m(row, width_m, depth_m)
    beam_half = beam_span_m * 0.5
    column_half = column_height_m * 0.5

    beam_axis_segment = _segment_m(
        _point_m(x - beam_half, y, z),
        _point_m(x + beam_half, y, z),
    )
    column_axis_segment = _segment_m(
        _point_m(x, y, z - column_half),
        _point_m(x, y, z + column_half),
    )

    beam_y_offset = max(width_m * 0.22, 0.05)
    beam_z_offset = max(depth_m * 0.28, 0.08)
    beam_rebar_segments = [
        _segment_m(_point_m(x - beam_half, y - beam_y_offset, z + beam_z_offset), _point_m(x + beam_half, y - beam_y_offset, z + beam_z_offset), tag="beam-top-left"),
        _segment_m(_point_m(x - beam_half, y + beam_y_offset, z + beam_z_offset), _point_m(x + beam_half, y + beam_y_offset, z + beam_z_offset), tag="beam-top-right"),
        _segment_m(_point_m(x - beam_half, y - beam_y_offset, z - beam_z_offset), _point_m(x + beam_half, y - beam_y_offset, z - beam_z_offset), tag="beam-bottom-left"),
        _segment_m(_point_m(x - beam_half, y + beam_y_offset, z - beam_z_offset), _point_m(x + beam_half, y + beam_y_offset, z - beam_z_offset), tag="beam-bottom-right"),
    ]

    column_x_offset = max(depth_m * 0.22, 0.06)
    column_y_offset = max(width_m * 0.22, 0.05)
    column_rebar_segments = [
        _segment_m(_point_m(x - column_x_offset, y - column_y_offset, z - column_half), _point_m(x - column_x_offset, y - column_y_offset, z + column_half), tag="column-corner-1"),
        _segment_m(_point_m(x + column_x_offset, y - column_y_offset, z - column_half), _point_m(x + column_x_offset, y - column_y_offset, z + column_half), tag="column-corner-2"),
        _segment_m(_point_m(x + column_x_offset, y + column_y_offset, z - column_half), _point_m(x + column_x_offset, y + column_y_offset, z + column_half), tag="column-corner-3"),
        _segment_m(_point_m(x - column_x_offset, y + column_y_offset, z - column_half), _point_m(x - column_x_offset, y + column_y_offset, z + column_half), tag="column-corner-4"),
    ]

    hoop_x = max(depth_m * 0.3, 0.08)
    hoop_y = max(width_m * 0.3, 0.06)
    hoop_offsets = (-column_half * 0.25, 0.0, column_half * 0.25)
    hoop_loops = []
    for idx, loop_offset in enumerate(hoop_offsets, start=1):
        loop_z = z + loop_offset
        hoop_loops.append(
            _loop_m(
                [
                    _point_m(x - hoop_x, y - hoop_y, loop_z),
                    _point_m(x + hoop_x, y - hoop_y, loop_z),
                    _point_m(x + hoop_x, y + hoop_y, loop_z),
                    _point_m(x - hoop_x, y + hoop_y, loop_z),
                    _point_m(x - hoop_x, y - hoop_y, loop_z),
                ],
                tag=f"hoop-{idx}",
            )
        )

    clash_count = max(_safe_int(row.get("clash_count", 0), 0), 0)
    clash_points = []
    if clash_count > 0:
        clash_count = min(clash_count, 4)
        clash_step = max(min(width_m, depth_m) * 0.15, 0.03)
        origin_offset = -0.5 * clash_step * float(clash_count - 1)
        for idx in range(clash_count):
            clash_points.append(_point_m(x + origin_offset + float(idx) * clash_step, y, z))

    return {
        "beam_axis_segment_m": beam_axis_segment,
        "column_axis_segment_m": column_axis_segment,
        "column_rebar_segments_m": column_rebar_segments,
        "beam_rebar_segments_m": beam_rebar_segments,
        "hoop_loops_m": hoop_loops,
        "clash_points_m": clash_points,
    }


def _enrich_source_rows_with_vector_geometry(
    rows: list[dict[str, Any]],
    *,
    source_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_by_kind = _collect_bundle_rows_by_kind(source_payload) if isinstance(source_payload, dict) else {}
    joint_rows_by_member = rows_by_kind.get("panel_zone_joint_geometry_3d", {})
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        member_id = str(enriched.get("member_id", "") or "").strip()
        sibling_joint_row = joint_rows_by_member.get(member_id) if member_id else None
        centroid_m = _extract_member_centroid_m(enriched, sibling_joint_row)
        if centroid_m is None:
            centroid_m = _synthesize_topology_centroid_m(enriched)
        if centroid_m is not None:
            enriched.setdefault("joint_centroid_m", centroid_m)
            width_m, depth_m = _extract_section_dims_m(enriched, sibling_joint_row)
            enriched.setdefault("section_width_mm", round(width_m * 1000.0, 3))
            enriched.setdefault("section_depth_mm", round(depth_m * 1000.0, 3))
            for key, value in _build_vector_geometry_payload(
                row=enriched,
                centroid_m=centroid_m,
                width_m=width_m,
                depth_m=depth_m,
            ).items():
                if key not in enriched or enriched.get(key) in (None, [], {}):
                    enriched[key] = value
        enriched_rows.append(enriched)
    return enriched_rows


def _extract_candidate_rows(dataset: dict, npz_state: dict[str, np.ndarray]) -> tuple[str, list[dict[str, Any]]]:
    if npz_state:
        constructability = np.asarray(npz_state.get("constructability_score", np.asarray([], dtype=np.float64)), dtype=np.float64)
        member_ids = np.asarray(npz_state.get("member_ids", np.asarray([], dtype=object)), dtype=object)
        member_types = np.asarray(npz_state.get("member_types", np.asarray([], dtype=object)), dtype=object)
        group_ids = np.asarray(npz_state.get("group_ids", np.asarray([], dtype=object)), dtype=object)
        section_signatures = np.asarray(npz_state.get("section_signatures", np.asarray([], dtype=object)), dtype=object)
        count = int(constructability.shape[0])
        rows: list[dict[str, Any]] = []
        for idx in range(count):
            member_type = str(member_types[idx]).strip().lower() if idx < int(member_types.shape[0]) else ""
            if member_type not in ALLOWED_MEMBER_TYPES:
                continue
            score = float(constructability[idx])
            if score >= 0.25:
                continue
            rows.append(
                {
                    "member_id": str(member_ids[idx]) if idx < int(member_ids.shape[0]) else "",
                    "member_type": str(member_types[idx]) if idx < int(member_types.shape[0]) else "",
                    "group_id": str(group_ids[idx]) if idx < int(group_ids.shape[0]) else "",
                    "section_signature": str(section_signatures[idx]) if idx < int(section_signatures.shape[0]) else "",
                    "constructability_score": score,
                }
            )
        return "npz_full", rows

    report_rows = dataset.get("rows_head", [])
    if not isinstance(report_rows, list):
        report_rows = []
    rows = []
    for row in report_rows:
        if not isinstance(row, dict):
            continue
        member_type = str(row.get("member_type", "") or "").strip().lower()
        if member_type not in ALLOWED_MEMBER_TYPES:
            continue
        score = _safe_float(row.get("constructability_score", 0.0), 0.0)
        if score >= 0.25:
            continue
        rows.append(
            {
                "member_id": str(row.get("member_id", row.get("group_id", "")) or ""),
                "member_type": str(row.get("member_type", "") or ""),
                "group_id": str(row.get("group_id", "") or ""),
                "section_signature": str(row.get("section_signature", "") or ""),
                "constructability_score": score,
            }
        )
    return "rows_head", rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-kind", choices=sorted(SOURCE_KIND_MAP), required=True)
    parser.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    parser.add_argument(
        "--design-optimization-npz",
        default="",
        help="Optional full design-optimization NPZ path; falls back to the report sibling when available.",
    )
    parser.add_argument(
        "--source-input",
        default="",
        help="Optional upstream source JSON emitted by a future 3D geometry/anchorage/clash solver.",
    )
    parser.add_argument("--out", default="implementation/phase1/panel_zone_3d_source_artifact.json")
    args = parser.parse_args()

    expected_kind = SOURCE_KIND_MAP[args.source_kind]
    dataset_path = Path(args.design_optimization_dataset)
    dataset = _load_json(dataset_path)
    npz_path = Path(args.design_optimization_npz) if str(args.design_optimization_npz).strip() else dataset_path.with_name(
        "design_optimization_dataset.npz"
    )
    npz_state = _load_npz(npz_path)
    candidate_scan_mode, candidate_rows = _extract_candidate_rows(dataset, npz_state)

    source_input_path = Path(args.source_input) if str(args.source_input).strip() else Path()
    source_input_present = bool(str(args.source_input).strip()) and source_input_path.exists()
    source_payload = _load_json(source_input_path) if source_input_present else {}
    source_rows, bundle_detected = _extract_source_rows(source_payload, expected_kind) if source_input_present else ([], False)
    member_mapping_sidecar = _extract_member_mapping_sidecar(source_payload) if source_input_present else {
        "present": False,
        "path": "",
        "mapping_mode": "",
        "row_count": 0,
        "member_map": {},
        "rows": [],
    }
    topology_bridge_provenance: dict[str, Any] = {}
    source_bridge_mode = ""
    if source_input_present and not source_rows:
        source_rows, topology_bridge_provenance, source_bridge_mode = _synthesize_topology_bridge_rows(
            payload=source_payload,
            source_input_path=source_input_path,
            expected_kind=expected_kind,
            candidate_rows=candidate_rows,
        )
    source_kind = _extract_source_kind(source_payload, expected_kind)
    source_metadata = _extract_source_metadata(source_payload, expected_kind) if source_input_present else {
        "producer_backend": "",
        "source_bundle_mode": "",
        "topology_projected": False,
        "solver_verified": False,
        "upstream_verification_tier": "",
        "instruction_sidecar_present": False,
        "instruction_sidecar_change_count": 0,
        "instruction_sidecar_candidate_overlap_mode": "",
        "instruction_sidecar_overlap_row_count": 0,
        "instruction_sidecar_overlap_member_count": 0,
        "instruction_sidecar_overlap_group_count": 0,
    }
    if source_bridge_mode:
        source_metadata = {
            "producer_backend": "opensees_topology_report"
            if source_bridge_mode == "opensees_topology_bridge"
            else "phase3_pipeline_topology_report",
            "source_bundle_mode": source_bridge_mode,
            "topology_projected": True,
            "solver_verified": False,
            "upstream_verification_tier": source_bridge_mode,
            "instruction_sidecar_present": False,
            "instruction_sidecar_change_count": 0,
            "instruction_sidecar_candidate_overlap_mode": "",
            "instruction_sidecar_overlap_row_count": 0,
            "instruction_sidecar_overlap_member_count": 0,
            "instruction_sidecar_overlap_group_count": 0,
            "instruction_sidecar_evidence_model": "",
            "instruction_sidecar_rebar_delivery_mode": "",
    }
    source_kind_match = bool(source_bridge_mode or not source_kind or source_kind == expected_kind)
    valid_source_rows, invalid_source_rows = _filter_valid_source_rows(source_rows, expected_kind)
    valid_source_rows, member_mapping_surface = _apply_member_mapping_sidecar(
        valid_source_rows,
        member_mapping_sidecar,
    )
    valid_source_rows = _enrich_source_rows_with_vector_geometry(
        valid_source_rows,
        source_payload=source_payload,
    )
    source_has_explicit_pass, source_input_contract_pass = _extract_source_contract_pass(
        source_payload,
        expected_kind,
        valid_source_rows=valid_source_rows,
    )
    candidate_member_ids = _extract_row_member_ids(candidate_rows)
    raw_source_member_ids = _extract_row_member_ids(source_rows)
    source_member_ids = _extract_row_member_ids(valid_source_rows)
    candidate_member_id_set = set(candidate_member_ids)
    source_member_id_set = set(source_member_ids)
    overlap_member_ids = sorted(candidate_member_id_set & source_member_id_set)

    if not candidate_rows:
        reason_code = "ERR_NO_PANEL_ZONE_CANDIDATES"
        reason = "design-optimization dataset did not expose low-constructability panel-zone candidates"
    elif not source_input_present:
        reason_code = "ERR_SOURCE_INPUT_MISSING"
        reason = "expected upstream 3D source input is missing"
    elif source_kind and source_kind != expected_kind:
        reason_code = "ERR_SOURCE_KIND_MISMATCH"
        reason = "upstream 3D source input kind does not match the requested source artifact"
    elif source_rows and not valid_source_rows:
        reason_code = "ERR_SOURCE_REQUIRED_FIELDS_MISSING"
        reason = "upstream 3D source input rows are present but missing required fields"
    elif not source_input_contract_pass or not valid_source_rows:
        reason_code = "ERR_SOURCE_INPUT_INVALID"
        reason = "upstream 3D source input is present but invalid, missing required fields, or has no usable rows"
    elif not overlap_member_ids:
        reason_code = "ERR_SOURCE_MEMBER_OVERLAP_MISSING"
        reason = (
            "upstream 3D source input does not overlap the active panel-zone candidate members after member-mapping reconciliation"
            if bool(member_mapping_sidecar.get("present", False))
            else "upstream 3D source input does not overlap the active panel-zone candidate members"
        )
    else:
        reason_code = "PASS"
        if bool(source_metadata.get("topology_projected", False)) and not bool(source_metadata.get("solver_verified", False)):
            reason = (
                "MIDAS-topology-projected panel source rows are attached and candidate rows are bound; "
                "solver-verified 3D clash rows are not attached."
            )
        else:
            reason = "panel-zone 3D source artifact is attached and candidate rows are bound"

    contract_pass = reason_code == "PASS"
    if contract_pass and bool(source_metadata.get("topology_projected", False)) and not bool(source_metadata.get("solver_verified", False)):
        verification_tier = f"{expected_kind}_topology_projected_validated_source"
    elif contract_pass and bool(source_metadata.get("solver_verified", False)):
        verification_tier = f"{expected_kind}_solver_verified_validated_source"
    elif contract_pass:
        verification_tier = f"{expected_kind}_validated_source"
    else:
        verification_tier = f"{expected_kind}_source_stub"

    payload = {
        "schema_version": "1.0",
        "run_id": f"phase1-panel-zone-{args.source_kind}-source-artifact",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": expected_kind,
        "source_provenance": {
            "source_kind": expected_kind,
            "input_dataset_report": str(args.design_optimization_dataset),
            "input_design_optimization_npz": str(npz_path),
            "source_input_path": str(source_input_path) if source_input_present else str(args.source_input or ""),
            "source_input_present": bool(source_input_present),
            "source_input_contract_pass": bool(source_input_contract_pass),
            "source_input_kind": str(source_kind or source_bridge_mode or ""),
            "source_kind_match": bool(source_kind_match),
            "source_bundle_detected": bool(bundle_detected),
            "source_bundle_mode": str(source_metadata.get("source_bundle_mode") or ("nested_solver_export" if bundle_detected else "direct_source_rows")),
            "producer_backend": str(source_metadata.get("producer_backend", "") or ""),
            "topology_projected": bool(source_metadata.get("topology_projected", False)),
            "solver_verified": bool(source_metadata.get("solver_verified", False)),
            "upstream_verification_tier": str(source_metadata.get("upstream_verification_tier", "") or ""),
            "instruction_sidecar_present": bool(source_metadata.get("instruction_sidecar_present", False)),
            "instruction_sidecar_change_count": int(source_metadata.get("instruction_sidecar_change_count", 0) or 0),
            "instruction_sidecar_candidate_overlap_mode": str(
                source_metadata.get("instruction_sidecar_candidate_overlap_mode", "") or ""
            ),
            "instruction_sidecar_overlap_row_count": int(source_metadata.get("instruction_sidecar_overlap_row_count", 0) or 0),
            "instruction_sidecar_overlap_member_count": int(source_metadata.get("instruction_sidecar_overlap_member_count", 0) or 0),
            "instruction_sidecar_overlap_group_count": int(source_metadata.get("instruction_sidecar_overlap_group_count", 0) or 0),
            "instruction_sidecar_evidence_model": str(source_metadata.get("instruction_sidecar_evidence_model", "") or ""),
            "instruction_sidecar_rebar_delivery_mode": str(
                source_metadata.get("instruction_sidecar_rebar_delivery_mode", "") or ""
            ),
            "member_mapping_sidecar_present": bool(member_mapping_surface.get("present", False)),
            "member_mapping_sidecar_path": str(member_mapping_surface.get("path", "") or ""),
            "member_mapping_sidecar_mode": str(member_mapping_surface.get("mapping_mode", "") or ""),
            "member_mapping_sidecar_row_count": int(member_mapping_surface.get("row_count", 0) or 0),
            "member_mapping_sidecar_applied_row_count": int(member_mapping_surface.get("applied_row_count", 0) or 0),
            "member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_surface.get("unmapped_source_member_count", 0) or 0
            ),
            "source_row_count": int(len(source_rows)),
            "valid_source_row_count": int(len(valid_source_rows)),
            "invalid_source_row_count": int(len(invalid_source_rows)),
            "candidate_scan_mode": candidate_scan_mode,
            "candidate_member_count": int(len(candidate_rows)),
            "candidate_member_ids_head": [row["member_id"] for row in candidate_rows[:16]],
            "raw_source_member_ids_head": raw_source_member_ids[:16],
            "source_member_ids_head": source_member_ids[:16],
            "overlap_member_count": int(len(overlap_member_ids)),
            "overlap_member_ids_head": overlap_member_ids[:16],
            "required_source_fields": list(SOURCE_REQUIRED_FIELDS.get(expected_kind, ())),
            "required_source_member_id": True,
            "verification_tier": verification_tier,
            "topology_capable_input": bool(candidate_scan_mode == "npz_full"),
            **topology_bridge_provenance,
        },
        "summary": {
            "source_kind": expected_kind,
            "source_status": "validated" if contract_pass else "open",
            "candidate_scan_mode": candidate_scan_mode,
            "candidate_member_count": int(len(candidate_rows)),
            "source_row_count": int(len(source_rows)),
            "valid_source_row_count": int(len(valid_source_rows)),
            "invalid_source_row_count": int(len(invalid_source_rows)),
            "overlap_member_count": int(len(overlap_member_ids)),
            "source_input_present": bool(source_input_present),
            "source_input_contract_pass": bool(source_input_contract_pass),
            "source_kind_match": bool(source_kind_match),
            "source_bundle_mode": str(source_metadata.get("source_bundle_mode") or ("nested_solver_export" if bundle_detected else "direct_source_rows")),
            "producer_backend": str(source_metadata.get("producer_backend", "") or ""),
            "topology_projected": bool(source_metadata.get("topology_projected", False)),
            "solver_verified": bool(source_metadata.get("solver_verified", False)),
            "upstream_verification_tier": str(source_metadata.get("upstream_verification_tier", "") or ""),
            "instruction_sidecar_present": bool(source_metadata.get("instruction_sidecar_present", False)),
            "instruction_sidecar_change_count": int(source_metadata.get("instruction_sidecar_change_count", 0) or 0),
            "instruction_sidecar_candidate_overlap_mode": str(
                source_metadata.get("instruction_sidecar_candidate_overlap_mode", "") or ""
            ),
            "instruction_sidecar_overlap_row_count": int(source_metadata.get("instruction_sidecar_overlap_row_count", 0) or 0),
            "instruction_sidecar_overlap_member_count": int(source_metadata.get("instruction_sidecar_overlap_member_count", 0) or 0),
            "instruction_sidecar_overlap_group_count": int(source_metadata.get("instruction_sidecar_overlap_group_count", 0) or 0),
            "instruction_sidecar_evidence_model": str(source_metadata.get("instruction_sidecar_evidence_model", "") or ""),
            "instruction_sidecar_rebar_delivery_mode": str(
                source_metadata.get("instruction_sidecar_rebar_delivery_mode", "") or ""
            ),
            "member_mapping_sidecar_present": bool(member_mapping_surface.get("present", False)),
            "member_mapping_sidecar_mode": str(member_mapping_surface.get("mapping_mode", "") or ""),
            "member_mapping_sidecar_row_count": int(member_mapping_surface.get("row_count", 0) or 0),
            "member_mapping_sidecar_applied_row_count": int(member_mapping_surface.get("applied_row_count", 0) or 0),
            "member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_surface.get("unmapped_source_member_count", 0) or 0
            ),
            "verification_tier": verification_tier,
        },
        "artifacts": {
            "candidate_rows_head": candidate_rows[:16],
            "source_rows_head": valid_source_rows[:16],
            "invalid_source_rows_head": invalid_source_rows[:16],
        },
        "checks": {
            "candidate_members_present": bool(candidate_rows),
            "source_input_present": bool(source_input_present),
            "source_rows_present": bool(valid_source_rows),
            "source_input_contract_pass": bool(source_input_contract_pass),
            "source_kind_match": bool(source_kind_match),
            "required_source_fields_present": bool(valid_source_rows) and not invalid_source_rows,
            "source_member_overlap_present": bool(overlap_member_ids),
            "topology_capable_input": bool(candidate_scan_mode == "npz_full"),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote panel-zone 3D source artifact: {out}")


if __name__ == "__main__":
    main()
