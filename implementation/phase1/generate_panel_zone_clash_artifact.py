#!/usr/bin/env python3
"""Generate a panel-zone clash proxy artifact from the design-optimization dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


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


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


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


def _load_npz(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = np.load(path, allow_pickle=True)
    except Exception:
        return {}
    return {str(key): data[key] for key in data.files}


def _load_artifact(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _source_artifact_state(path: str, source_kind: str) -> dict[str, Any]:
    source_path = Path(path) if str(path).strip() else Path()
    present = bool(str(path).strip()) and source_path.exists()
    payload = _load_artifact(source_path) if present else {}
    source_provenance = payload.get("source_provenance", {}) if isinstance(payload.get("source_provenance"), dict) else {}
    contract_pass = bool(_safe_bool(payload.get("contract_pass", False)))
    payload_source_kind = str(
        payload.get("source_kind")
        or source_provenance.get("source_kind")
        or source_provenance.get("source_artifact_kind")
        or ""
    ).strip()
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    verification_tier = str(
        payload.get("verification_tier")
        or summary.get("verification_tier")
        or summary.get("upstream_verification_tier")
        or source_provenance.get("verification_tier")
        or summary.get("artifact_mode")
        or ""
    ).strip()
    source_kind_match = bool(not payload_source_kind or payload_source_kind == source_kind)
    return {
        "source_kind": source_kind,
        "path": str(source_path) if present else str(path or ""),
        "present": bool(present),
        "contract_pass": bool(contract_pass),
        "source_kind_match": bool(source_kind_match),
        "valid": bool(present and contract_pass and source_kind_match),
        "verification_tier": verification_tier,
        "payload_source_kind": payload_source_kind,
        "source_row_count": _safe_int(source_provenance.get("source_row_count", 0)),
        "valid_source_row_count": _safe_int(source_provenance.get("valid_source_row_count", 0)),
        "invalid_source_row_count": _safe_int(source_provenance.get("invalid_source_row_count", 0)),
        "candidate_member_count": _safe_int(source_provenance.get("candidate_member_count", 0)),
        "overlap_member_count": _safe_int(source_provenance.get("overlap_member_count", 0)),
        "candidate_scan_mode": str(source_provenance.get("candidate_scan_mode", "") or ""),
        "topology_capable_input": bool(_safe_bool(source_provenance.get("topology_capable_input", False))),
        "producer_backend": str(source_provenance.get("producer_backend", "") or ""),
        "topology_projected": bool(_safe_bool(source_provenance.get("topology_projected", False))),
        "solver_verified": bool(_safe_bool(source_provenance.get("solver_verified", False))),
        "instruction_sidecar_present": bool(_safe_bool(source_provenance.get("instruction_sidecar_present", False))),
        "instruction_sidecar_change_count": _safe_int(source_provenance.get("instruction_sidecar_change_count", 0)),
        "instruction_sidecar_candidate_overlap_mode": str(
            source_provenance.get("instruction_sidecar_candidate_overlap_mode", "") or ""
        ),
        "instruction_sidecar_overlap_row_count": _safe_int(source_provenance.get("instruction_sidecar_overlap_row_count", 0)),
        "instruction_sidecar_overlap_member_count": _safe_int(
            source_provenance.get("instruction_sidecar_overlap_member_count", 0)
        ),
        "instruction_sidecar_overlap_group_count": _safe_int(
            source_provenance.get("instruction_sidecar_overlap_group_count", 0)
        ),
        "instruction_sidecar_evidence_model": str(source_provenance.get("instruction_sidecar_evidence_model", "") or ""),
        "instruction_sidecar_rebar_delivery_mode": str(
            source_provenance.get("instruction_sidecar_rebar_delivery_mode", "") or ""
        ),
        "member_mapping_sidecar_present": bool(_safe_bool(source_provenance.get("member_mapping_sidecar_present", False))),
        "member_mapping_sidecar_path": str(source_provenance.get("member_mapping_sidecar_path", "") or ""),
        "member_mapping_sidecar_mode": str(source_provenance.get("member_mapping_sidecar_mode", "") or ""),
        "member_mapping_sidecar_row_count": _safe_int(source_provenance.get("member_mapping_sidecar_row_count", 0)),
        "member_mapping_sidecar_applied_row_count": _safe_int(
            source_provenance.get("member_mapping_sidecar_applied_row_count", 0)
        ),
        "member_mapping_sidecar_unmapped_source_member_count": _safe_int(
            source_provenance.get("member_mapping_sidecar_unmapped_source_member_count", 0)
        ),
        "source_bundle_mode": str(source_provenance.get("source_bundle_mode", "") or ""),
        "upstream_verification_tier": str(source_provenance.get("upstream_verification_tier", "") or ""),
        "source_input_path": str(source_provenance.get("source_input_path", "") or ""),
        "required_source_fields": list(source_provenance.get("required_source_fields", []) or []),
        "candidate_member_ids_head": list(source_provenance.get("candidate_member_ids_head", []) or [])[:16],
        "source_member_ids_head": list(source_provenance.get("source_member_ids_head", []) or [])[:16],
        "overlap_member_ids_head": list(source_provenance.get("overlap_member_ids_head", []) or [])[:16],
    }


def _sidecar_overlap_rank(mode: str) -> int:
    return {
        "none": 0,
        "section_signature": 1,
        "canonical_group_scope": 2,
        "group_id_direct": 3,
    }.get(str(mode or "").strip(), 0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument(
        "--design-optimization-npz",
        default="",
        help="Optional full design-optimization NPZ path; falls back to the report sibling when available.",
    )
    p.add_argument(
        "--panel-zone-joint-geometry-artifact",
        default="",
        help="Optional future 3D panel-zone joint geometry artifact path.",
    )
    p.add_argument(
        "--panel-zone-rebar-anchorage-artifact",
        default="",
        help="Optional future 3D panel-zone rebar anchorage artifact path.",
    )
    p.add_argument(
        "--panel-zone-clash-verification-artifact",
        default="",
        help="Optional future 3D panel-zone clash verification artifact path.",
    )
    p.add_argument("--out", default="implementation/phase1/panel_zone_clash_artifact.json")
    args = p.parse_args()

    dataset = _load_json(Path(args.design_optimization_dataset))
    summary = dataset.get("summary", {}) if isinstance(dataset.get("summary"), dict) else {}
    report_rows = dataset.get("rows_head", [])
    if not isinstance(report_rows, list):
        report_rows = []
    dataset_path = Path(args.design_optimization_dataset)
    npz_path = Path(args.design_optimization_npz) if str(args.design_optimization_npz).strip() else dataset_path.with_name("design_optimization_dataset.npz")
    npz = _load_npz(npz_path)
    full_constructability = np.asarray(npz.get("constructability_score", []), dtype=np.float64) if npz else np.asarray([], dtype=np.float64)
    full_anchorage = np.asarray(npz.get("anchorage_complexity", []), dtype=np.float64) if npz else np.asarray([], dtype=np.float64)
    full_detailing = np.asarray(npz.get("detailing_violation_ratio", []), dtype=np.float64) if npz else np.asarray([], dtype=np.float64)
    full_member_ids = np.asarray(npz.get("member_ids", []), dtype=object) if npz else np.asarray([], dtype=object)
    full_member_types = np.asarray(npz.get("member_types", []), dtype=object) if npz else np.asarray([], dtype=object)
    full_group_ids = np.asarray(npz.get("group_ids", []), dtype=object) if npz else np.asarray([], dtype=object)
    full_section_signatures = np.asarray(npz.get("section_signatures", []), dtype=object) if npz else np.asarray([], dtype=object)

    joint_geometry_source = _source_artifact_state(args.panel_zone_joint_geometry_artifact, "panel_zone_joint_geometry_3d")
    rebar_anchorage_source = _source_artifact_state(args.panel_zone_rebar_anchorage_artifact, "panel_zone_rebar_anchorage_3d")
    clash_verification_source = _source_artifact_state(args.panel_zone_clash_verification_artifact, "panel_zone_clash_verification_3d")
    source_artifacts = {
        "panel_zone_joint_geometry_3d": joint_geometry_source,
        "panel_zone_rebar_anchorage_3d": rebar_anchorage_source,
        "panel_zone_clash_verification_3d": clash_verification_source,
    }
    required_sources_complete = bool(all(src["valid"] for src in source_artifacts.values()))
    missing_required_sources = [name for name, src in source_artifacts.items() if not src["valid"]]
    source_valid_row_counts = {name: int(src["valid_source_row_count"]) for name, src in source_artifacts.items()}
    source_overlap_member_counts = {name: int(src["overlap_member_count"]) for name, src in source_artifacts.items()}
    source_candidate_scan_modes = {name: str(src["candidate_scan_mode"]) for name, src in source_artifacts.items()}
    source_input_paths = {name: str(src["source_input_path"]) for name, src in source_artifacts.items()}
    source_producer_backends = {name: str(src["producer_backend"]) for name, src in source_artifacts.items()}
    source_bundle_modes = {name: str(src["source_bundle_mode"]) for name, src in source_artifacts.items()}
    source_upstream_verification_tiers = {
        name: str(src["upstream_verification_tier"]) for name, src in source_artifacts.items()
    }
    source_instruction_sidecar_present = {name: bool(src["instruction_sidecar_present"]) for name, src in source_artifacts.items()}
    source_instruction_sidecar_change_counts = {name: int(src["instruction_sidecar_change_count"]) for name, src in source_artifacts.items()}
    source_instruction_sidecar_overlap_modes = {
        name: str(src["instruction_sidecar_candidate_overlap_mode"]) for name, src in source_artifacts.items()
    }
    source_instruction_sidecar_overlap_row_counts = {
        name: int(src["instruction_sidecar_overlap_row_count"]) for name, src in source_artifacts.items()
    }
    source_instruction_sidecar_overlap_member_counts = {
        name: int(src["instruction_sidecar_overlap_member_count"]) for name, src in source_artifacts.items()
    }
    source_instruction_sidecar_overlap_group_counts = {
        name: int(src["instruction_sidecar_overlap_group_count"]) for name, src in source_artifacts.items()
    }
    source_instruction_sidecar_evidence_models = {
        name: str(src["instruction_sidecar_evidence_model"]) for name, src in source_artifacts.items()
    }
    source_instruction_sidecar_rebar_delivery_modes = {
        name: str(src["instruction_sidecar_rebar_delivery_mode"]) for name, src in source_artifacts.items()
    }
    source_member_mapping_sidecar_present = {
        name: bool(src["member_mapping_sidecar_present"]) for name, src in source_artifacts.items()
    }
    source_member_mapping_sidecar_paths = {
        name: str(src["member_mapping_sidecar_path"]) for name, src in source_artifacts.items()
    }
    source_member_mapping_sidecar_modes = {
        name: str(src["member_mapping_sidecar_mode"]) for name, src in source_artifacts.items()
    }
    source_member_mapping_sidecar_row_counts = {
        name: int(src["member_mapping_sidecar_row_count"]) for name, src in source_artifacts.items()
    }
    source_member_mapping_sidecar_applied_row_counts = {
        name: int(src["member_mapping_sidecar_applied_row_count"]) for name, src in source_artifacts.items()
    }
    source_member_mapping_sidecar_unmapped_source_member_counts = {
        name: int(src["member_mapping_sidecar_unmapped_source_member_count"]) for name, src in source_artifacts.items()
    }
    validated_source_row_count_total = int(sum(src["valid_source_row_count"] for src in source_artifacts.values() if src["valid"]))
    validated_overlap_counts = [int(src["overlap_member_count"]) for src in source_artifacts.values() if src["valid"]]
    validated_source_overlap_member_count_min = int(min(validated_overlap_counts)) if validated_overlap_counts else 0
    instruction_sidecar_present = bool(any(source_instruction_sidecar_present.values()))
    instruction_sidecar_change_count = int(max(source_instruction_sidecar_change_counts.values(), default=0))
    instruction_sidecar_candidate_overlap_mode = max(
        (str(mode or "") for mode in source_instruction_sidecar_overlap_modes.values()),
        key=_sidecar_overlap_rank,
        default="",
    )
    instruction_sidecar_overlap_row_count = int(max(source_instruction_sidecar_overlap_row_counts.values(), default=0))
    instruction_sidecar_overlap_member_count = int(max(source_instruction_sidecar_overlap_member_counts.values(), default=0))
    instruction_sidecar_overlap_group_count = int(max(source_instruction_sidecar_overlap_group_counts.values(), default=0))
    instruction_sidecar_evidence_model = max(
        (str(mode or "") for mode in source_instruction_sidecar_evidence_models.values()),
        key=lambda value: (bool(value), value),
        default="",
    )
    instruction_sidecar_rebar_delivery_mode = max(
        (str(mode or "") for mode in source_instruction_sidecar_rebar_delivery_modes.values()),
        key=lambda value: (bool(value), value),
        default="",
    )
    member_mapping_sidecar_present = bool(any(source_member_mapping_sidecar_present.values()))
    member_mapping_sidecar_path = max(
        (str(path or "") for path in source_member_mapping_sidecar_paths.values()),
        key=lambda value: (bool(value), value),
        default="",
    )
    member_mapping_sidecar_mode = max(
        (str(mode or "") for mode in source_member_mapping_sidecar_modes.values()),
        key=lambda value: (bool(value), value),
        default="",
    )
    member_mapping_sidecar_row_count = int(max(source_member_mapping_sidecar_row_counts.values(), default=0))
    member_mapping_sidecar_applied_row_count = int(
        max(source_member_mapping_sidecar_applied_row_counts.values(), default=0)
    )
    member_mapping_sidecar_unmapped_source_member_count = int(
        max(source_member_mapping_sidecar_unmapped_source_member_counts.values(), default=0)
    )
    source_metadata_declared = bool(
        required_sources_complete
        and any(
            bool(src["producer_backend"]) or bool(src["topology_projected"]) or bool(src["solver_verified"])
            for src in source_artifacts.values()
        )
    )
    topology_projected_bridge_complete = bool(
        required_sources_complete and source_metadata_declared and all(bool(src["topology_projected"]) for src in source_artifacts.values())
    )
    solver_verified_bridge_complete = bool(
        required_sources_complete
        and (
            (not source_metadata_declared)
            or all(bool(src["solver_verified"]) for src in source_artifacts.values())
        )
    )

    rows_source = "npz_full" if full_constructability.size > 0 else "rows_head"
    if rows_source == "npz_full":
        iter_indices = range(int(full_constructability.shape[0]))
    else:
        iter_indices = range(len(report_rows))

    clash_rows: list[dict] = []
    for idx in iter_indices:
        row = report_rows[idx] if rows_source == "rows_head" and idx < len(report_rows) else {}
        if rows_source == "npz_full":
            constructability = float(full_constructability[idx]) if idx < int(full_constructability.shape[0]) else 0.0
            member_type = str(full_member_types[idx]).strip().lower() if idx < int(full_member_types.shape[0]) else ""
            if member_type not in {"beam", "column", "wall", "connection"}:
                continue
            if constructability >= 0.25:
                continue
            clash_rows.append(
                {
                    "member_id": str(full_member_ids[idx]) if idx < int(full_member_ids.shape[0]) else "",
                    "member_type": str(full_member_types[idx]) if idx < int(full_member_types.shape[0]) else "",
                    "group_id": str(full_group_ids[idx]) if idx < int(full_group_ids.shape[0]) else "",
                    "section_signature": str(full_section_signatures[idx]) if idx < int(full_section_signatures.shape[0]) else "",
                    "constructability_score": constructability,
                    "anchorage_complexity": float(full_anchorage[idx]) if idx < int(full_anchorage.shape[0]) else 0.0,
                    "detailing_violation_ratio": float(full_detailing[idx]) if idx < int(full_detailing.shape[0]) else 0.0,
                }
            )
            continue
        if not isinstance(row, dict):
            continue
        member_type = str(row.get("member_type", "") or "").strip().lower()
        if member_type not in {"beam", "column", "wall", "connection"}:
            continue
        if _safe_float(row.get("constructability_score", 0.0), 0.0) < 0.25:
            clash_rows.append(
                {
                    "member_id": str(row.get("member_id", row.get("group_id", "")) or ""),
                    "member_type": str(row.get("member_type", "") or ""),
                    "group_id": str(row.get("group_id", "") or ""),
                    "section_signature": str(row.get("section_signature", "") or ""),
                    "constructability_score": _safe_float(row.get("constructability_score", 0.0), 0.0),
                    "anchorage_complexity": _safe_float(row.get("anchorage_complexity", 0.0), 0.0),
                    "detailing_violation_ratio": _safe_float(row.get("detailing_violation_ratio", 0.0), 0.0),
                }
            )

    contract_pass = bool(_safe_bool(dataset.get("contract_pass", False)) and clash_rows)
    reason_code = "PASS" if contract_pass else ("ERR_INPUT" if not dataset else "ERR_NO_PANEL_ZONE_CLASH_ROWS")
    reason = (
        "panel-zone clash artifact upgraded with solver-verified 3D joint geometry, anchorage, and clash sources"
        if contract_pass and solver_verified_bridge_complete
        else "panel-zone clash artifact upgraded with MIDAS-topology-derived joint geometry, anchorage, and clash bridge sources"
        if contract_pass and topology_projected_bridge_complete
        else "panel-zone clash artifact upgraded with validated 3D source bridge"
        if contract_pass and required_sources_complete
        else "panel-zone clash artifact generated from low-constructability members"
        if contract_pass
        else (
            "design-optimization dataset did not expose low-constructability panel-zone candidates"
            if dataset and clash_rows == []
            else "required 3D panel-zone sources are missing or invalid"
        )
    )
    if contract_pass and solver_verified_bridge_complete:
        verification_tier = "true_3d_clash_and_anchorage_verified"
        verification_mode = "panel_zone_3d_clash_and_anchorage_verified"
        source_contract_mode = verification_tier
    elif contract_pass and topology_projected_bridge_complete:
        verification_tier = "topology_projected_3d_clash_and_anchorage_bridge"
        verification_mode = "topology_projected_midas_panel_bridge"
        source_contract_mode = verification_tier
    elif contract_pass and required_sources_complete:
        verification_tier = "validated_source_bridge_unclassified"
        verification_mode = "validated_source_bridge_unclassified"
        source_contract_mode = verification_tier
    else:
        verification_tier = "topology_capable_proxy_scan"
        verification_mode = "proxy_only"
        source_contract_mode = "topology_capable_proxy_scan" if rows_source == "npz_full" else "rows_head_proxy_scan"
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-clash-artifact",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_provenance": {
            "input_kind": rows_source,
            "input_dataset_report": str(args.design_optimization_dataset),
            "input_design_optimization_npz": str(npz_path),
            "topology_capable_input": bool(rows_source == "npz_full"),
            "required_sources_complete": bool(required_sources_complete),
            "true_3d_clash_verified": bool(contract_pass and solver_verified_bridge_complete),
            "true_3d_anchorage_verified": bool(contract_pass and solver_verified_bridge_complete),
            "topology_projected_bridge_complete": bool(contract_pass and topology_projected_bridge_complete),
            "solver_verified_bridge_complete": bool(contract_pass and solver_verified_bridge_complete),
            "verification_tier": verification_tier,
            "missing_required_sources": list(missing_required_sources),
            "source_valid_row_counts": source_valid_row_counts,
            "source_overlap_member_counts": source_overlap_member_counts,
            "source_candidate_scan_modes": source_candidate_scan_modes,
            "source_input_paths": source_input_paths,
            "source_producer_backends": source_producer_backends,
            "source_bundle_modes": source_bundle_modes,
            "source_upstream_verification_tiers": source_upstream_verification_tiers,
            "source_instruction_sidecar_present": source_instruction_sidecar_present,
            "source_instruction_sidecar_change_counts": source_instruction_sidecar_change_counts,
            "source_instruction_sidecar_overlap_modes": source_instruction_sidecar_overlap_modes,
            "source_instruction_sidecar_overlap_row_counts": source_instruction_sidecar_overlap_row_counts,
            "source_instruction_sidecar_overlap_member_counts": source_instruction_sidecar_overlap_member_counts,
            "source_instruction_sidecar_overlap_group_counts": source_instruction_sidecar_overlap_group_counts,
            "source_instruction_sidecar_evidence_models": source_instruction_sidecar_evidence_models,
            "source_instruction_sidecar_rebar_delivery_modes": source_instruction_sidecar_rebar_delivery_modes,
            "source_member_mapping_sidecar_present": source_member_mapping_sidecar_present,
            "source_member_mapping_sidecar_paths": source_member_mapping_sidecar_paths,
            "source_member_mapping_sidecar_modes": source_member_mapping_sidecar_modes,
            "source_member_mapping_sidecar_row_counts": source_member_mapping_sidecar_row_counts,
            "source_member_mapping_sidecar_applied_row_counts": source_member_mapping_sidecar_applied_row_counts,
            "source_member_mapping_sidecar_unmapped_source_member_counts": (
                source_member_mapping_sidecar_unmapped_source_member_counts
            ),
            "instruction_sidecar_present": bool(instruction_sidecar_present),
            "instruction_sidecar_change_count": int(instruction_sidecar_change_count),
            "instruction_sidecar_candidate_overlap_mode": instruction_sidecar_candidate_overlap_mode,
            "instruction_sidecar_overlap_row_count": int(instruction_sidecar_overlap_row_count),
            "instruction_sidecar_overlap_member_count": int(instruction_sidecar_overlap_member_count),
            "instruction_sidecar_overlap_group_count": int(instruction_sidecar_overlap_group_count),
            "instruction_sidecar_evidence_model": instruction_sidecar_evidence_model,
            "instruction_sidecar_rebar_delivery_mode": instruction_sidecar_rebar_delivery_mode,
            "member_mapping_sidecar_present": bool(member_mapping_sidecar_present),
            "member_mapping_sidecar_path": member_mapping_sidecar_path,
            "member_mapping_sidecar_mode": member_mapping_sidecar_mode,
            "member_mapping_sidecar_row_count": int(member_mapping_sidecar_row_count),
            "member_mapping_sidecar_applied_row_count": int(member_mapping_sidecar_applied_row_count),
            "member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_sidecar_unmapped_source_member_count
            ),
            "validated_source_row_count_total": int(validated_source_row_count_total),
            "validated_source_overlap_member_count_min": int(validated_source_overlap_member_count_min),
            "source_artifacts": source_artifacts,
        },
        "inputs": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "design_optimization_npz": str(npz_path),
            "panel_zone_joint_geometry_artifact": str(args.panel_zone_joint_geometry_artifact),
            "panel_zone_rebar_anchorage_artifact": str(args.panel_zone_rebar_anchorage_artifact),
            "panel_zone_clash_verification_artifact": str(args.panel_zone_clash_verification_artifact),
        },
        "summary": {
            "artifact_mode": "constructability_proxy_candidate_scan",
            "verification_mode": verification_mode,
            "verification_tier": verification_tier,
            "member_count": _safe_int(summary.get("member_count", 0)),
            "group_count": _safe_int(summary.get("group_count", 0)),
            "candidate_scan_mode": rows_source,
            "low_constructability_row_count": int(len(clash_rows)),
            "max_constructability_score": max((row["constructability_score"] for row in clash_rows), default=0.0),
            "max_anchorage_complexity": max((row["anchorage_complexity"] for row in clash_rows), default=0.0),
            "max_detailing_violation_ratio": max((row["detailing_violation_ratio"] for row in clash_rows), default=0.0),
            "candidate_member_count": int(len(clash_rows)),
            "candidate_member_ids_head": [row["member_id"] for row in clash_rows[:16]],
            "dataset_contract_pass": bool(_safe_bool(dataset.get("contract_pass", False))),
            "design_optimization_npz_path": str(npz_path),
            "source_contract_mode": source_contract_mode,
            "required_sources_complete": bool(required_sources_complete),
            "topology_projected_bridge_complete": bool(contract_pass and topology_projected_bridge_complete),
            "solver_verified_bridge_complete": bool(contract_pass and solver_verified_bridge_complete),
            "source_producer_backends": source_producer_backends,
            "source_bundle_modes": source_bundle_modes,
            "source_upstream_verification_tiers": source_upstream_verification_tiers,
            "instruction_sidecar_present": bool(instruction_sidecar_present),
            "instruction_sidecar_change_count": int(instruction_sidecar_change_count),
            "instruction_sidecar_candidate_overlap_mode": instruction_sidecar_candidate_overlap_mode,
            "instruction_sidecar_overlap_row_count": int(instruction_sidecar_overlap_row_count),
            "instruction_sidecar_overlap_member_count": int(instruction_sidecar_overlap_member_count),
            "instruction_sidecar_overlap_group_count": int(instruction_sidecar_overlap_group_count),
            "instruction_sidecar_evidence_model": instruction_sidecar_evidence_model,
            "instruction_sidecar_rebar_delivery_mode": instruction_sidecar_rebar_delivery_mode,
            "member_mapping_sidecar_present": bool(member_mapping_sidecar_present),
            "member_mapping_sidecar_mode": member_mapping_sidecar_mode,
            "member_mapping_sidecar_row_count": int(member_mapping_sidecar_row_count),
            "member_mapping_sidecar_applied_row_count": int(member_mapping_sidecar_applied_row_count),
            "member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_sidecar_unmapped_source_member_count
            ),
            "validated_source_row_count_total": int(validated_source_row_count_total),
            "validated_source_overlap_member_count_min": int(validated_source_overlap_member_count_min),
        },
        "artifacts": {
            "interference_row_count": int(len(clash_rows)),
            "interference_rows_head": clash_rows[:16],
        },
        "checks": {
            "dataset_contract_pass": bool(_safe_bool(dataset.get("contract_pass", False))),
            "clash_rows_present": bool(clash_rows),
            "full_dataset_scanned": bool(rows_source == "npz_full"),
            "topology_capable_input": bool(rows_source == "npz_full"),
            "required_sources_complete": bool(required_sources_complete),
            "true_3d_clash_verified": bool(contract_pass and solver_verified_bridge_complete),
            "true_3d_anchorage_verified": bool(contract_pass and solver_verified_bridge_complete),
            "topology_projected_bridge_complete": bool(contract_pass and topology_projected_bridge_complete),
            "solver_verified_bridge_complete": bool(contract_pass and solver_verified_bridge_complete),
            "proxy_only": bool(not (contract_pass and required_sources_complete)),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote panel-zone clash artifact: {out}")


if __name__ == "__main__":
    main()
