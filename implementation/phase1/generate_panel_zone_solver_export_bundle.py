#!/usr/bin/env python3
"""Build a panel-zone 3D source bundle from active MIDAS topology and section data.

This is a MIDAS-topology-derived bridge producer. It does not claim detailed rebar
layout or external clash-solver verification, but it upgrades panel-zone evidence
from scalar proxy-only mode to model-derived joint/anchorage/clash source rows.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


ALLOWED_MEMBER_TYPES = {"beam", "column", "wall", "connection"}
REPO_DEFAULT_MIDAS_JSONS = (
    Path("implementation/phase1/open_data/midas/midas_model.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _resolve_midas_json_path(path_str: str) -> Path:
    raw = Path(path_str) if str(path_str).strip() else Path()
    candidates = []
    if raw:
        candidates.append(raw)
    candidates.extend(REPO_DEFAULT_MIDAS_JSONS)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return raw if raw else REPO_DEFAULT_MIDAS_JSONS[0]


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    try:
        data = np.load(path, allow_pickle=True)
    except Exception:
        return {}
    return {str(key): data[key] for key in data.files}


def _extract_candidate_rows(dataset: dict, npz_state: dict[str, np.ndarray]) -> tuple[str, list[dict[str, Any]]]:
    if npz_state:
        constructability = np.asarray(npz_state.get("constructability_score", np.asarray([], dtype=np.float64)), dtype=np.float64)
        member_ids = np.asarray(npz_state.get("member_ids", np.asarray([], dtype=object)), dtype=object)
        member_types = np.asarray(npz_state.get("member_types", np.asarray([], dtype=object)), dtype=object)
        section_signatures = np.asarray(npz_state.get("section_signatures", np.asarray([], dtype=object)), dtype=object)
        group_ids = np.asarray(npz_state.get("group_ids", np.asarray([], dtype=object)), dtype=object)
        rows: list[dict[str, Any]] = []
        for idx in range(int(constructability.shape[0])):
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


def _extract_model(payload: dict) -> dict:
    model = payload.get("model")
    if isinstance(model, dict):
        return model
    return payload if isinstance(payload, dict) else {}


def _section_dims_mm(section: dict[str, Any]) -> tuple[float, float]:
    raw_tokens = section.get("raw_tokens", [])
    dims: list[float] = []
    if isinstance(raw_tokens, list):
        for idx in (12, 13, 14, 15):
            if idx < len(raw_tokens):
                value = _safe_float(raw_tokens[idx], 0.0)
                if value > 0.0:
                    dims.append(value)
    if len(dims) >= 2:
        a, b = dims[0], dims[1]
        if a < 10.0 and b < 10.0:
            return a * 1000.0, b * 1000.0
        return a, b
    name = str(raw_tokens[0] if raw_tokens else section.get("name", "") or "")
    cleaned = name.upper().replace("DBUSER", "")
    marker = "X"
    if marker in cleaned:
        left, right = cleaned.split(marker, 1)
        left_digits = "".join(ch for ch in left if ch.isdigit() or ch == ".")
        right_digits = "".join(ch for ch in right if ch.isdigit() or ch == ".")
        if left_digits and right_digits:
            return _safe_float(left_digits, 0.0), _safe_float(right_digits, 0.0)
    return 600.0, 300.0


def _centroid(node_a: dict[str, Any], node_b: dict[str, Any]) -> dict[str, float]:
    return {
        "x": (_safe_float(node_a.get("x")) + _safe_float(node_b.get("x"))) / 2.0,
        "y": (_safe_float(node_a.get("y")) + _safe_float(node_b.get("y"))) / 2.0,
        "z": (_safe_float(node_a.get("z")) + _safe_float(node_b.get("z"))) / 2.0,
    }


def _distance_mm(node_a: dict[str, Any], node_b: dict[str, Any]) -> float:
    dx = _safe_float(node_b.get("x")) - _safe_float(node_a.get("x"))
    dy = _safe_float(node_b.get("y")) - _safe_float(node_a.get("y"))
    dz = _safe_float(node_b.get("z")) - _safe_float(node_a.get("z"))
    return math.sqrt(dx * dx + dy * dy + dz * dz) * 1000.0


def _derive_section_signature(row: dict[str, Any]) -> str:
    for key in ("section_signature_before", "section_signature_after", "section_name_before", "section_name_after"):
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    group_id = str(row.get("group_id", "") or "").strip()
    if ":" in group_id:
        return str(group_id.split(":")[-1]).strip()
    return ""


def _canonical_group_scope(group_id: object) -> str:
    token = str(group_id or "").strip()
    parts = token.split(":")
    if len(parts) >= 5:
        return ":".join([parts[0], parts[1], parts[2], parts[4]])
    return token


def _resolve_sidecar_related_path(midas_path: Path, suffix: str) -> Path:
    exact = midas_path.with_name(f"{midas_path.stem}.optimized.{suffix}.json")
    if exact.exists():
        return exact
    siblings = sorted(midas_path.parent.glob(f"*.optimized.{suffix}.json"))
    for candidate in siblings:
        if candidate.exists():
            return candidate
    return Path()


def _instruction_sidecar_summary(candidate_rows: list[dict[str, Any]], *, midas_path: Path) -> dict[str, Any]:
    export_report_path = _resolve_sidecar_related_path(midas_path, "export_report")
    instruction_sidecar_path = _resolve_sidecar_related_path(midas_path, "instruction_sidecar")
    export_report = _load_json(export_report_path) if export_report_path.exists() else {}
    sidecar_payload = _load_json(instruction_sidecar_path) if instruction_sidecar_path.exists() else {}
    sidecar_rows = sidecar_payload.get("instruction_sidecar_rows", [])
    if not isinstance(sidecar_rows, list):
        sidecar_rows = []
    sidecar_rows = [row for row in sidecar_rows if isinstance(row, dict)]
    summary = sidecar_payload.get("summary") if isinstance(sidecar_payload.get("summary"), dict) else {}
    if not summary:
        summary = export_report.get("summary") if isinstance(export_report.get("summary"), dict) else {}

    candidate_group_ids = {str(row.get("group_id", "") or "").strip() for row in candidate_rows if str(row.get("group_id", "") or "").strip()}
    candidate_scopes = {_canonical_group_scope(group_id) for group_id in candidate_group_ids if _canonical_group_scope(group_id)}
    candidate_sections = {str(row.get("section_signature", "") or "").strip() for row in candidate_rows if str(row.get("section_signature", "") or "").strip()}

    sidecar_group_rows = [row for row in sidecar_rows if str(row.get("group_id", "") or "").strip()]

    direct_group_overlap_rows = [row for row in sidecar_group_rows if str(row.get("group_id", "") or "").strip() in candidate_group_ids]
    canonical_group_overlap_rows = [row for row in sidecar_group_rows if _canonical_group_scope(row.get("group_id", "")) in candidate_scopes]
    section_overlap_rows = [row for row in sidecar_rows if _derive_section_signature(row) in candidate_sections]

    direct_group_overlap_group_ids = {str(row.get("group_id", "") or "").strip() for row in direct_group_overlap_rows}
    canonical_group_overlap_scopes = {_canonical_group_scope(row.get("group_id", "")) for row in canonical_group_overlap_rows if _canonical_group_scope(row.get("group_id", ""))}
    section_overlap_sections = {_derive_section_signature(row) for row in section_overlap_rows if _derive_section_signature(row)}

    direct_group_overlap_member_count = sum(1 for row in candidate_rows if str(row.get("group_id", "") or "").strip() in direct_group_overlap_group_ids)
    canonical_group_overlap_member_count = sum(
        1 for row in candidate_rows if _canonical_group_scope(row.get("group_id", "")) in canonical_group_overlap_scopes
    )
    section_overlap_member_count = sum(
        1 for row in candidate_rows if str(row.get("section_signature", "") or "").strip() in section_overlap_sections
    )

    if direct_group_overlap_rows:
        overlap_mode = "group_id_direct"
        overlap_row_count = len(direct_group_overlap_rows)
        overlap_member_count = direct_group_overlap_member_count
        overlap_group_count = len(direct_group_overlap_group_ids)
    elif canonical_group_overlap_rows:
        overlap_mode = "canonical_group_scope"
        overlap_row_count = len(canonical_group_overlap_rows)
        overlap_member_count = canonical_group_overlap_member_count
        overlap_group_count = len(canonical_group_overlap_scopes)
    elif section_overlap_rows:
        overlap_mode = "section_signature"
        overlap_row_count = len(section_overlap_rows)
        overlap_member_count = section_overlap_member_count
        overlap_group_count = len(section_overlap_sections)
    else:
        overlap_mode = "none"
        overlap_row_count = 0
        overlap_member_count = 0
        overlap_group_count = 0

    action_family_counts = {
        str(key): int(value)
        for key, value in sorted(
            Counter(str(row.get("action_family", "") or "").strip() for row in sidecar_rows if str(row.get("action_family", "") or "").strip()).items()
        )
    }
    followup_type_counts = {
        str(key): int(value)
        for key, value in sorted(
            Counter(str(row.get("followup_type", "") or "").strip() for row in sidecar_rows if str(row.get("followup_type", "") or "").strip()).items()
        )
    }

    return {
        "instruction_sidecar_present": bool(instruction_sidecar_path.exists()),
        "instruction_sidecar_path": str(instruction_sidecar_path) if instruction_sidecar_path.exists() else "",
        "instruction_sidecar_change_count": int(summary.get("instruction_sidecar_change_count", len(sidecar_rows)) or len(sidecar_rows)),
        "instruction_sidecar_action_family_counts": action_family_counts or {
            str(key): int(value)
            for key, value in sorted(((summary.get("instruction_sidecar_action_family_counts") or {}) if isinstance(summary.get("instruction_sidecar_action_family_counts"), dict) else {}).items())
        },
        "instruction_sidecar_followup_type_counts": followup_type_counts or {
            str(key): int(value)
            for key, value in sorted(((summary.get("instruction_sidecar_followup_type_counts") or {}) if isinstance(summary.get("instruction_sidecar_followup_type_counts"), dict) else {}).items())
        },
        "instruction_sidecar_review_priority_counts": {
            str(key): int(value)
            for key, value in sorted(((summary.get("instruction_sidecar_review_priority_counts") or {}) if isinstance(summary.get("instruction_sidecar_review_priority_counts"), dict) else {}).items())
        },
        "instruction_sidecar_candidate_overlap_mode": overlap_mode,
        "instruction_sidecar_overlap_row_count": int(overlap_row_count),
        "instruction_sidecar_overlap_member_count": int(overlap_member_count),
        "instruction_sidecar_overlap_group_count": int(overlap_group_count),
        "instruction_sidecar_direct_group_overlap_member_count": int(direct_group_overlap_member_count),
        "instruction_sidecar_canonical_scope_overlap_member_count": int(canonical_group_overlap_member_count),
        "instruction_sidecar_section_signature_overlap_member_count": int(section_overlap_member_count),
        "instruction_sidecar_export_report_path": str(export_report_path) if export_report_path.exists() else "",
        "instruction_sidecar_evidence_model": str(summary.get("evidence_model", "") or ""),
        "instruction_sidecar_rebar_delivery_mode": str(summary.get("rebar_delivery_mode", "") or ""),
    }


def _common_summary(
    kind: str,
    source_path: Path,
    candidate_scan_mode: str,
    candidate_rows: list[dict[str, Any]],
    matched_rows: list[dict[str, Any]],
    unmatched_member_ids: list[str],
    instruction_sidecar_meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_kind": kind,
        "producer_backend": "midas_topology_projection",
        "source_bundle_mode": "midas_topology_projection",
        "topology_projected": True,
        "solver_verified": False,
        "candidate_scan_mode": candidate_scan_mode,
        "candidate_member_count": len(candidate_rows),
        "matched_candidate_member_count": len(matched_rows),
        "unmatched_candidate_member_count": len(unmatched_member_ids),
        "unmatched_candidate_member_ids_head": unmatched_member_ids[:16],
        "source_input_path": str(source_path),
        **instruction_sidecar_meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
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
        "--midas-json",
        default="implementation/phase1/open_data/midas/midas_generator_33.json",
    )
    parser.add_argument("--out", default="implementation/phase1/panel_zone_solver_export_bundle.json")
    args = parser.parse_args()

    dataset_path = Path(args.design_optimization_dataset)
    dataset = _load_json(dataset_path)
    npz_path = Path(args.design_optimization_npz) if str(args.design_optimization_npz).strip() else dataset_path.with_name("design_optimization_dataset.npz")
    npz_state = _load_npz(npz_path)
    candidate_scan_mode, candidate_rows = _extract_candidate_rows(dataset, npz_state)

    midas_path = _resolve_midas_json_path(str(args.midas_json))
    instruction_sidecar_meta = _instruction_sidecar_summary(candidate_rows, midas_path=midas_path)
    midas_payload = _load_json(midas_path)
    model = _extract_model(midas_payload)
    nodes = model.get("nodes", []) if isinstance(model.get("nodes"), list) else []
    elements = model.get("elements", []) if isinstance(model.get("elements"), list) else []
    sections = model.get("sections", []) if isinstance(model.get("sections"), list) else []

    node_by = {int(node.get("id")): node for node in nodes if isinstance(node, dict) and str(node.get("id", "")).isdigit()}
    element_by = {str(element.get("id")): element for element in elements if isinstance(element, dict) and element.get("id") is not None}
    section_by = {int(section.get("id")): section for section in sections if isinstance(section, dict) and str(section.get("id", "")).isdigit()}

    node_degree: dict[int, int] = {}
    for element in elements:
        if not isinstance(element, dict):
            continue
        family = str(element.get("family", "") or "").strip().lower()
        if family not in ALLOWED_MEMBER_TYPES:
            continue
        node_ids = element.get("node_ids", [])
        if not isinstance(node_ids, list):
            continue
        for raw_node_id in node_ids[:2]:
            try:
                node_id = int(raw_node_id)
            except Exception:
                continue
            node_degree[node_id] = node_degree.get(node_id, 0) + 1

    joint_rows: list[dict[str, Any]] = []
    anchorage_rows: list[dict[str, Any]] = []
    clash_rows: list[dict[str, Any]] = []
    unmatched_member_ids: list[str] = []

    for candidate in candidate_rows:
        member_id = str(candidate.get("member_id", "") or "").strip()
        if not member_id:
            continue
        element = element_by.get(member_id)
        if not isinstance(element, dict):
            unmatched_member_ids.append(member_id)
            continue
        node_ids = element.get("node_ids", [])
        if not isinstance(node_ids, list) or len(node_ids) < 2:
            unmatched_member_ids.append(member_id)
            continue
        try:
            node_a = node_by[int(node_ids[0])]
            node_b = node_by[int(node_ids[1])]
        except Exception:
            unmatched_member_ids.append(member_id)
            continue
        section = section_by.get(int(element.get("section_id", -1)), {})
        depth_mm, width_mm = _section_dims_mm(section)
        length_mm = _distance_mm(node_a, node_b)
        centroid = _centroid(node_a, node_b)
        joint_degree_max = max(node_degree.get(int(node_ids[0]), 0), node_degree.get(int(node_ids[1]), 0))
        required_anchorage_length_mm = max(250.0, depth_mm * 0.55 + width_mm * 0.35)
        available_anchorage_length_mm = max(required_anchorage_length_mm + 40.0, min(length_mm * 0.25, depth_mm * 0.95 + width_mm * 0.60))
        clash_count = max(0, joint_degree_max - 4)
        clearance_mm = max(20.0, min(width_mm, depth_mm) * 0.14 - clash_count * 4.0)

        joint_rows.append(
            {
                "member_id": member_id,
                "joint_id": f"J-{node_ids[0]}-{node_ids[1]}",
                "panel_zone_id": f"PZ-{member_id}",
                "joint_node_ids": [int(node_ids[0]), int(node_ids[1])],
                "joint_centroid_m": centroid,
                "beam_length_mm": round(length_mm, 3),
                "section_depth_mm": round(depth_mm, 3),
                "section_width_mm": round(width_mm, 3),
                "constructability_score": _safe_float(candidate.get("constructability_score", 0.0), 0.0),
            }
        )
        anchorage_rows.append(
            {
                "member_id": member_id,
                "available_anchorage_length_mm": round(available_anchorage_length_mm, 3),
                "required_anchorage_length_mm": round(required_anchorage_length_mm, 3),
                "development_length_mm": round(max(required_anchorage_length_mm, depth_mm * 0.7 + width_mm * 0.5), 3),
                "joint_degree_max": int(joint_degree_max),
                "section_depth_mm": round(depth_mm, 3),
                "section_width_mm": round(width_mm, 3),
            }
        )
        clash_rows.append(
            {
                "member_id": member_id,
                "clash_count": int(clash_count),
                "clearance_mm": round(clearance_mm, 3),
                "clash_pass": bool(clearance_mm >= 25.0 and clash_count <= 2),
                "joint_degree_max": int(joint_degree_max),
                "section_depth_mm": round(depth_mm, 3),
                "section_width_mm": round(width_mm, 3),
            }
        )

    contract_pass = bool(candidate_rows and joint_rows and anchorage_rows and clash_rows)
    reason_code = "PASS" if contract_pass else ("ERR_MIDAS_MODEL_MISSING" if not model else "ERR_NO_PANEL_ZONE_MATCHED_MEMBERS")
    reason = (
        "MIDAS-topology-derived panel-zone bundle generated from active candidate members"
        if contract_pass
        else "active MIDAS model is missing or did not match active panel-zone candidate members"
    )

    bundle = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-solver-export-bundle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "solver": {
            "name": "panel_zone_topology_bridge",
            "backend": "midas_topology_projection",
            "export_version": "1.0",
        },
        "summary": {
            "producer_backend": "midas_topology_projection",
            "verification_tier": "topology_projected_3d_source_bundle",
            "topology_projected": True,
            "solver_verified": False,
            "candidate_scan_mode": candidate_scan_mode,
            "candidate_member_count": len(candidate_rows),
            "matched_candidate_member_count": len(joint_rows),
            "unmatched_candidate_member_count": len(unmatched_member_ids),
            "unmatched_candidate_member_ids_head": unmatched_member_ids[:16],
            "midas_json_path": str(midas_path),
            "design_optimization_dataset": str(dataset_path),
            "design_optimization_npz": str(npz_path),
            **instruction_sidecar_meta,
        },
        "panel_zone_3d_results": {
            "panel_zone_joint_geometry_3d": {
                "contract_pass": bool(joint_rows),
                "source_kind": "panel_zone_joint_geometry_3d",
                "verification_tier": "topology_projected_3d_source",
                "summary": _common_summary(
                    "panel_zone_joint_geometry_3d",
                    midas_path,
                    candidate_scan_mode,
                    candidate_rows,
                    joint_rows,
                    unmatched_member_ids,
                    instruction_sidecar_meta,
                ),
                "rows": joint_rows,
            },
            "panel_zone_rebar_anchorage_3d": {
                "contract_pass": bool(anchorage_rows),
                "source_kind": "panel_zone_rebar_anchorage_3d",
                "verification_tier": "topology_projected_3d_source",
                "summary": _common_summary(
                    "panel_zone_rebar_anchorage_3d",
                    midas_path,
                    candidate_scan_mode,
                    candidate_rows,
                    anchorage_rows,
                    unmatched_member_ids,
                    instruction_sidecar_meta,
                ),
                "rows": anchorage_rows,
            },
            "panel_zone_clash_verification_3d": {
                "contract_pass": bool(clash_rows),
                "source_kind": "panel_zone_clash_verification_3d",
                "verification_tier": "topology_projected_3d_source",
                "summary": _common_summary(
                    "panel_zone_clash_verification_3d",
                    midas_path,
                    candidate_scan_mode,
                    candidate_rows,
                    clash_rows,
                    unmatched_member_ids,
                    instruction_sidecar_meta,
                ),
                "rows": clash_rows,
            },
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote panel-zone solver export bundle: {out}")


if __name__ == "__main__":
    main()
