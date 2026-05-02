#!/usr/bin/env python3
"""Generate a panel-zone 3D clash and anchorage-recompute readiness report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.panel_zone_external_validation import (  # noqa: E402
    build_panel_zone_external_validation_local_closure_surface,
    build_panel_zone_external_validation_provenance_surface,
    build_panel_zone_external_validation_required_evidence,
    build_panel_zone_external_validation_summary_line,
)


REASONS = {
    "PASS": "3D panel-zone clash and anchorage recompute artifact is attached",
    "ERR_INPUT": "required input artifacts are missing or invalid",
    "ERR_NO_PANEL_ZONE_CLASH_ARTIFACT": "no 3D panel-zone clash or anchorage-recompute artifact is attached",
    "ERR_PROXY_ONLY": "member-local panel-zone proxy artifact is attached, but 3D clash verification is still missing",
    "ERR_MISSING_REQUIRED_SOURCES": "panel-zone 3D bridge producer is attached, but required 3D source artifacts are missing or invalid",
    "ERR_TOPOLOGY_PROJECTED_ONLY": "MIDAS-topology-projected panel-zone bridge is attached, but solver-verified 3D rebar clash evidence is still missing",
}

REQUIRED_PANEL_ZONE_SOURCES = (
    "panel_zone_joint_geometry_3d",
    "panel_zone_rebar_anchorage_3d",
    "panel_zone_clash_verification_3d",
)
EXACT_PROVENANCE_MARKERS = (
    "solver_verified",
    "true_3d",
    "direct_solver_export",
    "reviewer_verified_exact",
    "manual_verified_exact",
    "exact",
)
FALLBACK_PROVENANCE_MARKERS = (
    "topology_projected",
    "topology_projection",
    "projection",
    "proxy",
    "heuristic",
    "fallback",
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


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    try:
        denominator_value = float(denominator)
    except Exception:
        denominator_value = 0.0
    if denominator_value <= 0.0:
        return 0.0
    try:
        return float(numerator) / denominator_value
    except Exception:
        return 0.0


def _matches_any_marker(*values: object, markers: tuple[str, ...]) -> bool:
    normalized = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    if not normalized:
        return False
    return any(marker in normalized for marker in markers)


def _panel_zone_external_validation_coverage(
    *,
    source_valid_row_counts: dict[str, int],
    source_overlap_member_counts: dict[str, int],
    source_candidate_scan_modes: dict[str, str],
    source_producer_backends: dict[str, str],
    source_bundle_modes: dict[str, str],
    source_upstream_verification_tiers: dict[str, str],
    source_artifacts: dict[str, dict],
    missing_required_sources: list[str],
    proxy_candidate_count: int,
    validated_source_row_count_total: int,
    validated_source_overlap_member_count_min: int,
    verified_artifact: bool,
    required_sources_complete: bool,
    topology_projected_bridge_complete: bool,
    solver_verified_bridge_complete: bool,
) -> dict[str, object]:
    source_names: list[str] = list(REQUIRED_PANEL_ZONE_SOURCES)
    for mapping in (
        source_valid_row_counts,
        source_overlap_member_counts,
        source_candidate_scan_modes,
        source_producer_backends,
        source_bundle_modes,
        source_upstream_verification_tiers,
        source_artifacts,
    ):
        for key in mapping.keys():
            normalized = str(key or "").strip()
            if normalized and normalized not in source_names:
                source_names.append(normalized)
    for key in missing_required_sources:
        normalized = str(key or "").strip()
        if normalized and normalized not in source_names:
            source_names.append(normalized)

    classified_rows: list[dict[str, object]] = []
    for source_name in source_names:
        artifact_meta = source_artifacts.get(source_name, {})
        if not isinstance(artifact_meta, dict):
            artifact_meta = {}
        required_source = source_name in REQUIRED_PANEL_ZONE_SOURCES
        valid_row_count = _safe_int(
            source_valid_row_counts.get(
                source_name,
                artifact_meta.get("valid_source_row_count", artifact_meta.get("source_row_count", 0)),
            ),
            0,
        )
        overlap_member_count = _safe_int(
            source_overlap_member_counts.get(source_name, artifact_meta.get("overlap_member_count", 0)),
            0,
        )
        candidate_member_count = _safe_int(artifact_meta.get("candidate_member_count", 0), 0)
        bundle_mode = str(source_bundle_modes.get(source_name, artifact_meta.get("bundle_mode", "")) or "").strip()
        producer_backend = str(
            source_producer_backends.get(source_name, artifact_meta.get("producer_backend", "")) or ""
        ).strip()
        upstream_tier = str(
            source_upstream_verification_tiers.get(source_name, artifact_meta.get("verification_tier", "")) or ""
        ).strip()
        aggregate_required_source_present = bool(
            required_source
            and source_name not in missing_required_sources
            and (
                verified_artifact
                or solver_verified_bridge_complete
                or topology_projected_bridge_complete
                or required_sources_complete
            )
        )
        present = bool(
            _safe_bool(artifact_meta.get("present", False))
            or valid_row_count > 0
            or overlap_member_count > 0
            or bundle_mode
            or producer_backend
            or upstream_tier
            or aggregate_required_source_present
        )
        valid = bool(
            _safe_bool(artifact_meta.get("valid", aggregate_required_source_present or present))
            and source_name not in missing_required_sources
        )
        provenance_mode = "unknown"
        if source_name in missing_required_sources or (not valid and not present):
            provenance_mode = "missing"
        elif verified_artifact or solver_verified_bridge_complete or _matches_any_marker(
            bundle_mode,
            producer_backend,
            upstream_tier,
            markers=EXACT_PROVENANCE_MARKERS,
        ):
            provenance_mode = "exact"
        elif topology_projected_bridge_complete or required_sources_complete or _matches_any_marker(
            bundle_mode,
            producer_backend,
            upstream_tier,
            source_candidate_scan_modes.get(source_name, ""),
            markers=FALLBACK_PROVENANCE_MARKERS,
        ):
            provenance_mode = "fallback"
        classified_rows.append(
            {
                "source_name": source_name,
                "provenance_mode": provenance_mode,
                "valid_row_count": valid_row_count,
                "overlap_member_count": overlap_member_count,
                "candidate_member_count": candidate_member_count,
                "present": present,
                "valid": valid,
            }
        )

    total_source_count = len(classified_rows)
    exact_rows = [row for row in classified_rows if row["provenance_mode"] == "exact"]
    fallback_rows = [row for row in classified_rows if row["provenance_mode"] == "fallback"]
    missing_rows = [row for row in classified_rows if row["provenance_mode"] == "missing"]
    unknown_rows = [row for row in classified_rows if row["provenance_mode"] == "unknown"]
    validated_rows = [row for row in classified_rows if row["provenance_mode"] in {"exact", "fallback"}]

    exact_source_count = len(exact_rows)
    fallback_source_count = len(fallback_rows)
    missing_source_count = len(missing_rows)
    unknown_source_count = len(unknown_rows)
    validated_source_count = len(validated_rows)

    exact_validated_row_count = sum(int(row["valid_row_count"]) for row in exact_rows)
    fallback_validated_row_count = sum(int(row["valid_row_count"]) for row in fallback_rows)
    unknown_validated_row_count = sum(int(row["valid_row_count"]) for row in unknown_rows)
    total_validated_row_count = max(
        int(validated_source_row_count_total),
        exact_validated_row_count + fallback_validated_row_count + unknown_validated_row_count,
    )
    unattributed_validated_row_count = max(
        total_validated_row_count - exact_validated_row_count - fallback_validated_row_count - unknown_validated_row_count,
        0,
    )
    if unattributed_validated_row_count > 0:
        if exact_source_count > 0 and fallback_source_count == 0:
            exact_validated_row_count += unattributed_validated_row_count
            unattributed_validated_row_count = 0
        elif fallback_source_count > 0 and exact_source_count == 0:
            fallback_validated_row_count += unattributed_validated_row_count
            unattributed_validated_row_count = 0

    candidate_member_count_total = max(
        int(proxy_candidate_count),
        int(validated_source_overlap_member_count_min),
        max((int(row["candidate_member_count"]) for row in classified_rows), default=0),
        max((int(row["overlap_member_count"]) for row in classified_rows), default=0),
    )

    def _minimum_overlap(rows: list[dict[str, object]], fallback_value: int = 0) -> int:
        overlaps = [int(row["overlap_member_count"]) for row in rows if int(row["overlap_member_count"]) > 0]
        if overlaps:
            return min(overlaps)
        return int(fallback_value)

    exact_member_count = _minimum_overlap(
        exact_rows,
        validated_source_overlap_member_count_min if exact_source_count == total_source_count and total_source_count > 0 else 0,
    )
    fallback_member_count = _minimum_overlap(
        fallback_rows,
        validated_source_overlap_member_count_min if fallback_source_count == total_source_count and total_source_count > 0 else 0,
    )
    validated_member_count = max(int(validated_source_overlap_member_count_min), exact_member_count, fallback_member_count)

    summary_label = (
        f"validated_sources={validated_source_count}/{total_source_count} | "
        f"exact_sources={exact_source_count}/{total_source_count} | "
        f"fallback_sources={fallback_source_count}/{total_source_count} | "
        f"missing_sources={missing_source_count}/{total_source_count} | "
        f"validated_members={validated_member_count}/{candidate_member_count_total} | "
        f"exact_members={exact_member_count}/{candidate_member_count_total} | "
        f"fallback_members={fallback_member_count}/{candidate_member_count_total} | "
        f"exact_rows={exact_validated_row_count}/{total_validated_row_count} | "
        f"fallback_rows={fallback_validated_row_count}/{total_validated_row_count}"
    )
    if unattributed_validated_row_count > 0:
        summary_label = (
            f"{summary_label} | "
            f"unattributed_rows={unattributed_validated_row_count}/{total_validated_row_count}"
        )

    return {
        "source_count": int(total_source_count),
        "validated_source_count": int(validated_source_count),
        "exact_source_count": int(exact_source_count),
        "fallback_source_count": int(fallback_source_count),
        "missing_source_count": int(missing_source_count),
        "unknown_source_count": int(unknown_source_count),
        "validated_source_ratio": float(_safe_ratio(validated_source_count, total_source_count)),
        "exact_source_ratio": float(_safe_ratio(exact_source_count, total_source_count)),
        "fallback_source_ratio": float(_safe_ratio(fallback_source_count, total_source_count)),
        "candidate_member_count": int(candidate_member_count_total),
        "validated_member_count": int(validated_member_count),
        "exact_member_count": int(exact_member_count),
        "fallback_member_count": int(fallback_member_count),
        "validated_member_ratio": float(_safe_ratio(validated_member_count, candidate_member_count_total)),
        "exact_member_ratio": float(_safe_ratio(exact_member_count, candidate_member_count_total)),
        "fallback_member_ratio": float(_safe_ratio(fallback_member_count, candidate_member_count_total)),
        "validated_row_count_total": int(total_validated_row_count),
        "exact_validated_row_count": int(exact_validated_row_count),
        "fallback_validated_row_count": int(fallback_validated_row_count),
        "unknown_validated_row_count": int(unknown_validated_row_count),
        "unattributed_validated_row_count": int(unattributed_validated_row_count),
        "exact_validated_row_ratio": float(_safe_ratio(exact_validated_row_count, total_validated_row_count)),
        "fallback_validated_row_ratio": float(_safe_ratio(fallback_validated_row_count, total_validated_row_count)),
        "unattributed_validated_row_ratio": float(
            _safe_ratio(unattributed_validated_row_count, total_validated_row_count)
        ),
        "summary_label": summary_label,
    }


def _row_stat(values: list[dict], key: str) -> float:
    if not values:
        return 0.0
    numeric = []
    for row in values:
        if not isinstance(row, dict):
            continue
        try:
            numeric.append(float(row.get(key, 0.0)))
        except Exception:
            numeric.append(0.0)
    return max(numeric) if numeric else 0.0


def _is_3d_verified_mode(mode: str) -> bool:
    normalized = mode.strip().lower()
    return normalized in {
        "panel_zone_3d_clash_and_anchorage_verified",
        "3d_verified",
        "three_d_verified",
    }


def _external_validation_status_label(
    *,
    verified_artifact: bool,
    exact_source_count: int,
    fallback_source_count: int,
    missing_source_count: int,
    advisory_only: bool,
    release_blocking: bool,
) -> str:
    if verified_artifact:
        return "verified"
    if advisory_only and fallback_source_count > 0 and exact_source_count == 0:
        return "validated_fallback_only_gap"
    if advisory_only and exact_source_count > 0 and fallback_source_count > 0:
        return "mixed_exact_fallback_gap"
    if advisory_only and missing_source_count > 0:
        return "validated_source_gap"
    if release_blocking:
        return "release_blocking"
    if advisory_only:
        return "measured_external_validation_gap"
    return "not_applicable"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument(
        "--pbd-review-package",
        default="implementation/phase1/release/pbd_review/pbd_review_package_report.json",
    )
    p.add_argument(
        "--panel-zone-clash-artifact",
        default="implementation/phase1/panel_zone_clash_artifact.json",
        help="Optional 3D panel-zone clash evidence JSON/CSV path",
    )
    p.add_argument(
        "--solver-verified-inbox-status",
        default="implementation/phase1/panel_zone_solver_verified_inbox_status.json",
        help="Optional solver-verified panel-zone inbox status JSON path",
    )
    p.add_argument("--out", default="implementation/phase1/panel_zone_clash_report.json")
    args = p.parse_args()

    dataset = _load_json(Path(args.design_optimization_dataset))
    pbd = _load_json(Path(args.pbd_review_package))
    rows = dataset.get("rows_head", [])
    if not isinstance(rows, list):
        rows = []

    outlier_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            if float(row.get("constructability_score", 0.0)) < 0.25:
                outlier_count += 1
        except Exception:
            pass

    clash_artifact_path_raw = str(args.panel_zone_clash_artifact).strip()
    clash_artifact_path = Path(clash_artifact_path_raw) if clash_artifact_path_raw else None
    clash_artifact = _load_json(clash_artifact_path) if clash_artifact_path is not None else {}
    solver_verified_inbox_status_path_raw = str(args.solver_verified_inbox_status).strip()
    solver_verified_inbox_status_path = (
        Path(solver_verified_inbox_status_path_raw) if solver_verified_inbox_status_path_raw else None
    )
    solver_verified_inbox_status = (
        _load_json(solver_verified_inbox_status_path) if solver_verified_inbox_status_path is not None else {}
    )
    artifact_present = bool(clash_artifact_path is not None and clash_artifact_path.exists())
    artifact_contract = bool(_safe_bool(clash_artifact.get("contract_pass", False)))
    artifact_source_provenance = (
        clash_artifact.get("source_provenance", {}) if isinstance(clash_artifact.get("source_provenance"), dict) else {}
    )
    artifact_summary = clash_artifact.get("summary", {}) if isinstance(clash_artifact.get("summary"), dict) else {}
    artifact_inputs = clash_artifact.get("inputs", {}) if isinstance(clash_artifact.get("inputs"), dict) else {}
    inbox_summary = (
        solver_verified_inbox_status.get("summary")
        if isinstance(solver_verified_inbox_status.get("summary"), dict)
        else {}
    )
    solver_verified_inbox_status_mode = str(
        inbox_summary.get("panel_zone_solver_verified_inbox_status_mode", "") or ""
    )
    solver_verified_inbox_has_input = bool(
        inbox_summary.get("panel_zone_solver_verified_inbox_has_input", False)
    )
    solver_verified_pending_input = bool(
        inbox_summary.get("panel_zone_solver_verified_pending_input", False)
    )
    solver_verified_input_mode_detected = str(
        inbox_summary.get("panel_zone_solver_verified_input_mode_detected", "") or ""
    )
    solver_verified_latest_consume_report_present = bool(
        inbox_summary.get("panel_zone_solver_verified_latest_consume_report_present", False)
    )
    solver_verified_latest_consume_contract_pass = bool(
        inbox_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
    )
    solver_verified_latest_consume_reason_code = str(
        inbox_summary.get("panel_zone_solver_verified_latest_consume_reason_code", "") or ""
    )
    solver_verified_source_origin_class = str(
        inbox_summary.get("panel_zone_solver_verified_source_origin_class", "") or ""
    )
    solver_verified_release_refresh_source_allowed = bool(
        inbox_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
    )
    solver_verified_recommended_action = str(
        inbox_summary.get("panel_zone_solver_verified_recommended_action", "") or ""
    )
    artifact_dataset_path = str(artifact_inputs.get("design_optimization_dataset", "") or "").strip()
    artifact_npz_path = str(artifact_inputs.get("design_optimization_npz", "") or "").strip()
    if artifact_npz_path:
        artifact_source_kind = "design_optimization_dataset_npz"
        artifact_source_path = artifact_npz_path
    elif artifact_dataset_path:
        artifact_source_kind = "design_optimization_dataset_report"
        artifact_source_path = artifact_dataset_path
    else:
        artifact_source_kind = "unknown"
        artifact_source_path = ""
    artifact_mode = str(
        artifact_summary.get("verification_mode")
        or artifact_summary.get("constructability_mode")
        or artifact_summary.get("artifact_mode")
        or ""
    ).strip()
    clash_row_count = 0
    if isinstance(clash_artifact.get("artifacts"), dict):
        clash_row_count = _safe_int(clash_artifact.get("artifacts", {}).get("interference_row_count", 0))
    if not clash_row_count:
        clash_row_count = _safe_int(artifact_summary.get("interference_count", 0))
    proxy_candidate_count = _safe_int(artifact_summary.get("low_constructability_row_count", 0))
    if not proxy_candidate_count:
        proxy_candidate_count = _safe_int(artifact_summary.get("candidate_member_count", 0))
    constructability_low_outlier_count = max(int(outlier_count), int(proxy_candidate_count))
    source_contract_mode = str(
        artifact_summary.get("source_contract_mode")
        or artifact_source_provenance.get("source_contract_mode")
        or ("topology_capable_proxy_scan" if artifact_source_provenance.get("topology_capable_input") else "rows_head_proxy_scan")
    )
    missing_required_sources = artifact_source_provenance.get("missing_required_sources", [])
    if not isinstance(missing_required_sources, list):
        missing_required_sources = []
    topology_capable_input = bool(artifact_source_provenance.get("topology_capable_input", False))
    true_3d_clash_verified = bool(artifact_source_provenance.get("true_3d_clash_verified", False))
    true_3d_anchorage_verified = bool(artifact_source_provenance.get("true_3d_anchorage_verified", False))
    required_sources_complete = bool(artifact_source_provenance.get("required_sources_complete", False))
    source_valid_row_counts = artifact_source_provenance.get("source_valid_row_counts", {})
    if not isinstance(source_valid_row_counts, dict):
        source_valid_row_counts = {}
    source_valid_row_counts = {str(k): _safe_int(v, 0) for k, v in source_valid_row_counts.items()}
    source_overlap_member_counts = artifact_source_provenance.get("source_overlap_member_counts", {})
    if not isinstance(source_overlap_member_counts, dict):
        source_overlap_member_counts = {}
    source_overlap_member_counts = {str(k): _safe_int(v, 0) for k, v in source_overlap_member_counts.items()}
    source_candidate_scan_modes = artifact_source_provenance.get("source_candidate_scan_modes", {})
    if not isinstance(source_candidate_scan_modes, dict):
        source_candidate_scan_modes = {}
    source_candidate_scan_modes = {str(k): str(v or "") for k, v in source_candidate_scan_modes.items()}
    source_producer_backends = artifact_source_provenance.get("source_producer_backends", {})
    if not isinstance(source_producer_backends, dict):
        source_producer_backends = {}
    source_producer_backends = {str(k): str(v or "") for k, v in source_producer_backends.items()}
    source_bundle_modes = artifact_source_provenance.get("source_bundle_modes", {})
    if not isinstance(source_bundle_modes, dict):
        source_bundle_modes = {}
    source_bundle_modes = {str(k): str(v or "") for k, v in source_bundle_modes.items()}
    source_upstream_verification_tiers = artifact_source_provenance.get("source_upstream_verification_tiers", {})
    if not isinstance(source_upstream_verification_tiers, dict):
        source_upstream_verification_tiers = {}
    source_upstream_verification_tiers = {str(k): str(v or "") for k, v in source_upstream_verification_tiers.items()}
    source_artifacts = artifact_source_provenance.get("source_artifacts", {})
    if not isinstance(source_artifacts, dict):
        source_artifacts = {}
    source_artifacts = {
        str(k): v for k, v in source_artifacts.items() if isinstance(v, dict)
    }
    validated_source_row_count_total = _safe_int(artifact_source_provenance.get("validated_source_row_count_total", 0))
    validated_source_overlap_member_count_min = _safe_int(
        artifact_source_provenance.get("validated_source_overlap_member_count_min", 0)
    )
    instruction_sidecar_present = bool(_safe_bool(artifact_source_provenance.get("instruction_sidecar_present", False)))
    instruction_sidecar_change_count = _safe_int(artifact_source_provenance.get("instruction_sidecar_change_count", 0))
    instruction_sidecar_candidate_overlap_mode = str(
        artifact_source_provenance.get("instruction_sidecar_candidate_overlap_mode", "") or ""
    ).strip()
    instruction_sidecar_overlap_row_count = _safe_int(
        artifact_source_provenance.get("instruction_sidecar_overlap_row_count", 0)
    )
    instruction_sidecar_overlap_member_count = _safe_int(
        artifact_source_provenance.get("instruction_sidecar_overlap_member_count", 0)
    )
    instruction_sidecar_overlap_group_count = _safe_int(
        artifact_source_provenance.get("instruction_sidecar_overlap_group_count", 0)
    )
    instruction_sidecar_evidence_model = str(
        artifact_source_provenance.get("instruction_sidecar_evidence_model", "") or ""
    ).strip()
    instruction_sidecar_rebar_delivery_mode = str(
        artifact_source_provenance.get("instruction_sidecar_rebar_delivery_mode", "") or ""
    ).strip()
    member_mapping_sidecar_present = bool(
        _safe_bool(artifact_source_provenance.get("member_mapping_sidecar_present", False))
    )
    member_mapping_sidecar_mode = str(
        artifact_source_provenance.get("member_mapping_sidecar_mode", "") or ""
    ).strip()
    member_mapping_sidecar_row_count = _safe_int(
        artifact_source_provenance.get("member_mapping_sidecar_row_count", 0)
    )
    member_mapping_sidecar_applied_row_count = _safe_int(
        artifact_source_provenance.get("member_mapping_sidecar_applied_row_count", 0)
    )
    member_mapping_sidecar_unmapped_source_member_count = _safe_int(
        artifact_source_provenance.get("member_mapping_sidecar_unmapped_source_member_count", 0)
    )
    topology_projected_bridge_complete = bool(artifact_source_provenance.get("topology_projected_bridge_complete", False))
    solver_verified_bridge_complete = bool(artifact_source_provenance.get("solver_verified_bridge_complete", False))
    verified_tier = str(
        artifact_source_provenance.get("verification_tier")
        or artifact_summary.get("verification_tier")
        or ""
    ).strip()

    verified_artifact = bool(
        artifact_present
        and artifact_contract
        and (
            _is_3d_verified_mode(artifact_mode)
            or verified_tier == "true_3d_clash_and_anchorage_verified"
            or (required_sources_complete and solver_verified_bridge_complete and true_3d_clash_verified and true_3d_anchorage_verified)
        )
    )
    topology_projected_artifact = bool(
        artifact_present
        and artifact_contract
        and not verified_artifact
        and required_sources_complete
        and topology_projected_bridge_complete
    )
    internal_engine_complete = bool(
        topology_projected_artifact
        and validated_source_row_count_total > 0
        and validated_source_overlap_member_count_min > 0
    )
    proxy_artifact = bool(
        artifact_present
        and not topology_projected_artifact
        and not verified_artifact
        and (
            clash_row_count > 0
            or proxy_candidate_count > 0
            or "proxy" in artifact_mode.lower()
        )
    )
    contract_pass = bool(verified_artifact or internal_engine_complete)
    external_validation_pending = bool(internal_engine_complete and not verified_artifact)
    external_validation_advisory_only = bool(external_validation_pending and contract_pass)
    external_validation_release_blocking = bool(external_validation_pending and not contract_pass)
    external_validation_coverage = _panel_zone_external_validation_coverage(
        source_valid_row_counts=source_valid_row_counts,
        source_overlap_member_counts=source_overlap_member_counts,
        source_candidate_scan_modes=source_candidate_scan_modes,
        source_producer_backends=source_producer_backends,
        source_bundle_modes=source_bundle_modes,
        source_upstream_verification_tiers=source_upstream_verification_tiers,
        source_artifacts=source_artifacts,
        missing_required_sources=missing_required_sources,
        proxy_candidate_count=proxy_candidate_count,
        validated_source_row_count_total=validated_source_row_count_total,
        validated_source_overlap_member_count_min=validated_source_overlap_member_count_min,
        verified_artifact=verified_artifact,
        required_sources_complete=required_sources_complete,
        topology_projected_bridge_complete=topology_projected_bridge_complete,
        solver_verified_bridge_complete=solver_verified_bridge_complete,
    )
    external_validation_status_label = _external_validation_status_label(
        verified_artifact=verified_artifact,
        exact_source_count=int(external_validation_coverage["exact_source_count"]),
        fallback_source_count=int(external_validation_coverage["fallback_source_count"]),
        missing_source_count=int(external_validation_coverage["missing_source_count"]),
        advisory_only=external_validation_advisory_only,
        release_blocking=external_validation_release_blocking,
    )
    validation_boundary = (
        "external_validation_only"
        if external_validation_pending
        else "solver_verified"
        if verified_artifact
        else "open"
    )
    source_bridge_complete = bool(required_sources_complete and true_3d_clash_verified and true_3d_anchorage_verified)
    external_validation_summary_context = {
        "panel_zone_validation_boundary": validation_boundary,
        "panel_zone_external_validation_pending": external_validation_pending,
        "panel_zone_external_validation_status_label": external_validation_status_label,
        "panel_zone_external_validation_artifact_closed": bool(verified_artifact),
        "panel_zone_internal_engine_complete": internal_engine_complete,
        "panel_zone_3d_clash_ready": bool(verified_artifact),
        "panel_zone_true_3d_clash_verified": true_3d_clash_verified,
        "panel_zone_true_3d_anchorage_verified": true_3d_anchorage_verified,
        "panel_zone_true_3d_bridge_complete": source_bridge_complete,
        "panel_zone_solver_verified_bridge_complete": solver_verified_bridge_complete,
        "panel_zone_external_validation_source_count": int(external_validation_coverage["source_count"]),
        "panel_zone_external_validation_validated_source_count": int(
            external_validation_coverage["validated_source_count"]
        ),
        "panel_zone_external_validation_exact_source_count": int(
            external_validation_coverage["exact_source_count"]
        ),
        "panel_zone_external_validation_fallback_source_count": int(
            external_validation_coverage["fallback_source_count"]
        ),
        "panel_zone_external_validation_missing_source_count": int(
            external_validation_coverage["missing_source_count"]
        ),
        "panel_zone_external_validation_unknown_source_count": int(
            external_validation_coverage["unknown_source_count"]
        ),
        "panel_zone_external_validation_candidate_member_count": int(
            external_validation_coverage["candidate_member_count"]
        ),
        "panel_zone_external_validation_validated_member_count": int(
            external_validation_coverage["validated_member_count"]
        ),
        "panel_zone_external_validation_exact_member_count": int(
            external_validation_coverage["exact_member_count"]
        ),
        "panel_zone_external_validation_fallback_member_count": int(
            external_validation_coverage["fallback_member_count"]
        ),
        "panel_zone_external_validation_validated_row_count_total": int(
            external_validation_coverage["validated_row_count_total"]
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            external_validation_coverage["exact_validated_row_count"]
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            external_validation_coverage["fallback_validated_row_count"]
        ),
        "panel_zone_external_validation_provenance_summary_label": str(
            external_validation_coverage["summary_label"]
        ),
        "panel_zone_solver_verified_inbox_status_mode": solver_verified_inbox_status_mode,
        "panel_zone_solver_verified_inbox_has_input": solver_verified_inbox_has_input,
        "panel_zone_solver_verified_pending_input": solver_verified_pending_input,
        "panel_zone_solver_verified_input_mode_detected": solver_verified_input_mode_detected,
        "panel_zone_solver_verified_latest_consume_report_present": solver_verified_latest_consume_report_present,
        "panel_zone_solver_verified_latest_consume_contract_pass": solver_verified_latest_consume_contract_pass,
        "panel_zone_solver_verified_latest_consume_reason_code": solver_verified_latest_consume_reason_code,
        "panel_zone_solver_verified_recommended_action": solver_verified_recommended_action,
    }
    external_validation_closure_surface = build_panel_zone_external_validation_provenance_surface(
        external_validation_summary_context
    )
    external_validation_closure_mode = str(
        external_validation_closure_surface.get("closure_mode", "") or ""
    ).strip()
    external_validation_required_evidence = build_panel_zone_external_validation_required_evidence(
        external_validation_summary_context,
        status_label=external_validation_status_label,
    )
    external_validation_summary_line = build_panel_zone_external_validation_summary_line(
        external_validation_summary_context,
        status_label=external_validation_status_label,
    )
    external_validation_local_closure_surface = build_panel_zone_external_validation_local_closure_surface(
        external_validation_summary_context,
        status_label=external_validation_status_label,
    )
    external_validation_local_closure_state = str(
        external_validation_local_closure_surface.get("state", "") or ""
    ).strip()
    external_validation_local_closure_label = str(
        external_validation_local_closure_surface.get("label", "") or ""
    ).strip()
    external_validation_closing_summary_label = (
        f"status={external_validation_status_label} | "
        f"validated_sources={int(external_validation_coverage['validated_source_count'])}/{int(external_validation_coverage['source_count'])} | "
        f"exact_sources={int(external_validation_coverage['exact_source_count'])}/{int(external_validation_coverage['source_count'])} | "
        f"fallback_sources={int(external_validation_coverage['fallback_source_count'])}/{int(external_validation_coverage['source_count'])} | "
        f"validated_members={int(external_validation_coverage['validated_member_count'])}/{int(external_validation_coverage['candidate_member_count'])} | "
        f"exact_rows={int(external_validation_coverage['exact_validated_row_count'])}/{int(external_validation_coverage['validated_row_count_total'])} | "
        f"fallback_rows={int(external_validation_coverage['fallback_validated_row_count'])}/{int(external_validation_coverage['validated_row_count_total'])} | "
        f"local_closure_state={external_validation_local_closure_state} | "
        f"local_closure_label={external_validation_local_closure_label} | "
        f"inbox={solver_verified_inbox_status_mode or 'unknown'} | "
        f"pending_input={solver_verified_pending_input} | "
        f"latest_consume_present={solver_verified_latest_consume_report_present} | "
        f"latest_consume_pass={solver_verified_latest_consume_contract_pass} | "
        f"latest_consume_reason={solver_verified_latest_consume_reason_code or 'n/a'} | "
        f"next={solver_verified_recommended_action or 'n/a'}"
    )

    if not dataset and not isinstance(dataset.get("summary"), dict):
        reason_code = "ERR_INPUT"
        reason = "design-optimization dataset report is missing or invalid"
        mode = "input_missing"
    elif verified_artifact:
        reason_code = "PASS"
        reason = "3D panel-zone clash and anchorage recomputation artifacts are attached"
        mode = "panel_zone_3d_clash_and_anchorage_verified"
    elif internal_engine_complete:
        reason_code = "PASS"
        reason = (
            "Internal engine completed panel-zone joint geometry, anchorage, and clash recomputation with "
            "validated member overlap; external verification now serves as an optional audit boundary."
        )
        mode = "internal_engine_panel_zone_3d_clash_and_anchorage_complete"
    elif artifact_present and missing_required_sources:
        reason_code = "ERR_MISSING_REQUIRED_SOURCES"
        reason = (
            "panel-zone bridge producer is attached, but required 3D source artifacts are missing or invalid: "
            + ", ".join(missing_required_sources)
        )
        mode = "panel_zone_3d_bridge_missing_required_sources"
    elif topology_projected_artifact:
        reason_code = "ERR_TOPOLOGY_PROJECTED_ONLY"
        if instruction_sidecar_present and instruction_sidecar_candidate_overlap_mode == "none":
            reason = (
                "MIDAS-topology-derived joint/anchorage/clash bridge is attached, and an optimization instruction "
                "sidecar is present, but it does not overlap the active panel-zone candidates and solver-verified "
                "3D rebar clash evidence is still not attached."
            )
        elif instruction_sidecar_present:
            evidence_tokens = [
                token
                for token in (
                    instruction_sidecar_evidence_model,
                    instruction_sidecar_rebar_delivery_mode,
                )
                if token
            ]
            evidence_tail = f" using {'/'.join(evidence_tokens)} evidence" if evidence_tokens else ""
            reason = (
                "MIDAS-topology-derived joint/anchorage/clash bridge is attached with validated member overlap, "
                f"and an optimization instruction sidecar overlaps the active panel-zone candidates via "
                f"{instruction_sidecar_candidate_overlap_mode}{evidence_tail}, but solver-verified 3D rebar clash evidence is "
                "still not attached."
            )
        else:
            reason = (
                "MIDAS-topology-derived joint/anchorage/clash bridge is attached with validated member overlap, "
                "but solver-verified 3D rebar clash evidence is still not attached."
            )
        mode = "topology_projected_midas_panel_bridge"
    elif proxy_artifact:
        artifact_reason = str(clash_artifact.get("reason") or "").strip()
        reason_code = "ERR_PROXY_ONLY"
        reason = (
            "Member-local panel-zone proxy evidence is attached, but no 3D clash/anchorage recomputation artifact is attached."
            if not artifact_reason or clash_artifact.get("reason_code") == "PASS"
            else artifact_reason
        )
        mode = "proxy_artifact_attached_but_not_3d_verified"
    elif outlier_count > 0:
        reason_code = "ERR_NO_PANEL_ZONE_CLASH_ARTIFACT"
        reason = "constructability metrics require anchor-clash/anchorage recomputation evidence but none is attached"
        mode = "scalar_proxy_hard_gate_only"
    else:
        reason_code = "ERR_NO_PANEL_ZONE_CLASH_ARTIFACT"
        reason = "No 3D panel-zone clash artifact is attached."
        mode = "scalar_proxy_hard_gate_only"

    design_summary = dataset.get("summary", {})
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-clash-readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "pbd_review_package": str(args.pbd_review_package),
            "panel_zone_clash_artifact": str(args.panel_zone_clash_artifact),
            "solver_verified_inbox_status": str(args.solver_verified_inbox_status),
        },
        "summary": {
            "constructability_mode": mode,
            "sample_member_count": _safe_int(len(rows)),
            "constructability_low_outlier_count": int(constructability_low_outlier_count),
            "max_constructability_score": _row_stat(rows, "constructability_score"),
            "max_anchorage_complexity": _row_stat(rows, "anchorage_complexity"),
            "max_detailing_violation_ratio": _row_stat(rows, "detailing_violation_ratio"),
            "design_opt_constructability_avg": _safe_float(design_summary.get("constructability_score", design_summary.get("constructability_avg"))),
            "design_opt_detailing_complexity_avg": _safe_float(design_summary.get("detailing_complexity_score", design_summary.get("detailing_complexity_avg"))),
            "hinge_proxy_artifact_present": bool(bool(pbd)),
            "panel_zone_clash_report_attached": bool(artifact_present),
            "panel_zone_clash_row_count": int(clash_row_count),
            "panel_zone_proxy_candidate_count": int(proxy_candidate_count),
            "panel_zone_source_artifact_kind": artifact_source_kind,
            "panel_zone_source_artifact_path": artifact_source_path,
            "panel_zone_source_contract_mode": source_contract_mode,
            "panel_zone_missing_required_sources": missing_required_sources,
            "panel_zone_topology_capable_input": topology_capable_input,
            "panel_zone_true_3d_clash_verified": true_3d_clash_verified,
            "panel_zone_true_3d_anchorage_verified": true_3d_anchorage_verified,
            "panel_zone_required_sources_complete": required_sources_complete,
            "panel_zone_true_3d_bridge_complete": source_bridge_complete,
            "panel_zone_topology_projected_bridge_complete": topology_projected_bridge_complete,
            "panel_zone_solver_verified_bridge_complete": solver_verified_bridge_complete,
            "panel_zone_internal_engine_complete": internal_engine_complete,
            "panel_zone_external_validation_pending": external_validation_pending,
            "panel_zone_external_validation_advisory_only": external_validation_advisory_only,
            "panel_zone_external_validation_release_blocking": external_validation_release_blocking,
            "panel_zone_external_validation_status_label": external_validation_status_label,
            "panel_zone_external_validation_artifact_closed": bool(verified_artifact),
            "panel_zone_external_validation_closure_mode": external_validation_closure_mode,
            "panel_zone_external_validation_source_count": int(external_validation_coverage["source_count"]),
            "panel_zone_external_validation_validated_source_count": int(
                external_validation_coverage["validated_source_count"]
            ),
            "panel_zone_external_validation_exact_source_count": int(external_validation_coverage["exact_source_count"]),
            "panel_zone_external_validation_fallback_source_count": int(
                external_validation_coverage["fallback_source_count"]
            ),
            "panel_zone_external_validation_missing_source_count": int(
                external_validation_coverage["missing_source_count"]
            ),
            "panel_zone_external_validation_unknown_source_count": int(
                external_validation_coverage["unknown_source_count"]
            ),
            "panel_zone_external_validation_validated_source_ratio": float(
                external_validation_coverage["validated_source_ratio"]
            ),
            "panel_zone_external_validation_exact_source_ratio": float(
                external_validation_coverage["exact_source_ratio"]
            ),
            "panel_zone_external_validation_fallback_source_ratio": float(
                external_validation_coverage["fallback_source_ratio"]
            ),
            "panel_zone_external_validation_candidate_member_count": int(
                external_validation_coverage["candidate_member_count"]
            ),
            "panel_zone_external_validation_validated_member_count": int(
                external_validation_coverage["validated_member_count"]
            ),
            "panel_zone_external_validation_exact_member_count": int(
                external_validation_coverage["exact_member_count"]
            ),
            "panel_zone_external_validation_fallback_member_count": int(
                external_validation_coverage["fallback_member_count"]
            ),
            "panel_zone_external_validation_validated_member_ratio": float(
                external_validation_coverage["validated_member_ratio"]
            ),
            "panel_zone_external_validation_exact_member_ratio": float(
                external_validation_coverage["exact_member_ratio"]
            ),
            "panel_zone_external_validation_fallback_member_ratio": float(
                external_validation_coverage["fallback_member_ratio"]
            ),
            "panel_zone_external_validation_validated_row_count_total": int(
                external_validation_coverage["validated_row_count_total"]
            ),
            "panel_zone_external_validation_exact_validated_row_count": int(
                external_validation_coverage["exact_validated_row_count"]
            ),
            "panel_zone_external_validation_fallback_validated_row_count": int(
                external_validation_coverage["fallback_validated_row_count"]
            ),
            "panel_zone_external_validation_unattributed_validated_row_count": int(
                external_validation_coverage["unattributed_validated_row_count"]
            ),
            "panel_zone_external_validation_exact_validated_row_ratio": float(
                external_validation_coverage["exact_validated_row_ratio"]
            ),
            "panel_zone_external_validation_fallback_validated_row_ratio": float(
                external_validation_coverage["fallback_validated_row_ratio"]
            ),
            "panel_zone_external_validation_unattributed_validated_row_ratio": float(
                external_validation_coverage["unattributed_validated_row_ratio"]
            ),
            "panel_zone_external_validation_required_evidence": external_validation_required_evidence,
            "panel_zone_external_validation_summary_line": external_validation_summary_line,
            "panel_zone_external_validation_local_closure_state": external_validation_local_closure_state,
            "panel_zone_external_validation_local_closure_label": external_validation_local_closure_label,
            "panel_zone_external_validation_closing_summary_label": external_validation_closing_summary_label,
            "panel_zone_solver_verified_inbox_status_mode": solver_verified_inbox_status_mode,
            "panel_zone_solver_verified_inbox_has_input": solver_verified_inbox_has_input,
            "panel_zone_solver_verified_pending_input": solver_verified_pending_input,
            "panel_zone_solver_verified_input_mode_detected": solver_verified_input_mode_detected,
            "panel_zone_solver_verified_latest_consume_report_present": solver_verified_latest_consume_report_present,
            "panel_zone_solver_verified_latest_consume_contract_pass": solver_verified_latest_consume_contract_pass,
            "panel_zone_solver_verified_latest_consume_reason_code": solver_verified_latest_consume_reason_code,
            "panel_zone_solver_verified_source_origin_class": solver_verified_source_origin_class,
            "panel_zone_solver_verified_release_refresh_source_allowed": solver_verified_release_refresh_source_allowed,
            "panel_zone_solver_verified_recommended_action": solver_verified_recommended_action,
            "panel_zone_external_validation_provenance_summary_label": str(
                external_validation_coverage["summary_label"]
            ),
            "panel_zone_validation_boundary": validation_boundary,
            "panel_zone_source_valid_row_counts": source_valid_row_counts,
            "panel_zone_source_overlap_member_counts": source_overlap_member_counts,
            "panel_zone_source_candidate_scan_modes": source_candidate_scan_modes,
            "panel_zone_source_producer_backends": source_producer_backends,
            "panel_zone_source_bundle_modes": source_bundle_modes,
            "panel_zone_source_upstream_verification_tiers": source_upstream_verification_tiers,
            "panel_zone_instruction_sidecar_present": bool(instruction_sidecar_present),
            "panel_zone_instruction_sidecar_change_count": int(instruction_sidecar_change_count),
            "panel_zone_instruction_sidecar_candidate_overlap_mode": instruction_sidecar_candidate_overlap_mode,
            "panel_zone_instruction_sidecar_overlap_row_count": int(instruction_sidecar_overlap_row_count),
            "panel_zone_instruction_sidecar_overlap_member_count": int(instruction_sidecar_overlap_member_count),
            "panel_zone_instruction_sidecar_overlap_group_count": int(instruction_sidecar_overlap_group_count),
            "panel_zone_instruction_sidecar_evidence_model": instruction_sidecar_evidence_model,
            "panel_zone_instruction_sidecar_rebar_delivery_mode": instruction_sidecar_rebar_delivery_mode,
            "panel_zone_member_mapping_sidecar_present": bool(member_mapping_sidecar_present),
            "panel_zone_member_mapping_sidecar_mode": member_mapping_sidecar_mode,
            "panel_zone_member_mapping_sidecar_row_count": int(member_mapping_sidecar_row_count),
            "panel_zone_member_mapping_sidecar_applied_row_count": int(
                member_mapping_sidecar_applied_row_count
            ),
            "panel_zone_member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_sidecar_unmapped_source_member_count
            ),
            "panel_zone_validated_source_row_count_total": int(validated_source_row_count_total),
            "panel_zone_validated_source_overlap_member_count_min": int(validated_source_overlap_member_count_min),
            "pbd_contract_pass": _safe_bool(pbd.get("contract_pass", False)),
            "dataset_contract_pass": _safe_bool(dataset.get("contract_pass", False)),
        },
        "checks": {
            "constructability_proxy_only": bool(mode == "scalar_proxy_hard_gate_only"),
            "panel_zone_clash_artifact_present": bool(artifact_present),
            "panel_zone_clash_artifact_contract_pass": bool(artifact_contract),
            "panel_zone_clash_artifact_3d_verified": bool(verified_artifact),
            "panel_zone_clash_artifact_source_detected": bool(artifact_source_path),
            "panel_zone_topology_capable_input": bool(topology_capable_input),
            "panel_zone_true_3d_clash_verified": bool(true_3d_clash_verified),
            "panel_zone_true_3d_anchorage_verified": bool(true_3d_anchorage_verified),
            "panel_zone_required_sources_complete": bool(required_sources_complete),
            "panel_zone_true_3d_bridge_complete": bool(source_bridge_complete),
            "panel_zone_topology_projected_bridge_complete": bool(topology_projected_bridge_complete),
            "panel_zone_solver_verified_bridge_complete": bool(solver_verified_bridge_complete),
            "panel_zone_internal_engine_complete": bool(internal_engine_complete),
            "panel_zone_external_validation_pending": bool(external_validation_pending),
            "panel_zone_external_validation_advisory_only": bool(external_validation_advisory_only),
            "panel_zone_external_validation_release_blocking": bool(external_validation_release_blocking),
            "panel_zone_missing_required_sources": bool(missing_required_sources),
            "panel_zone_topology_projected_artifact_present": bool(topology_projected_artifact),
            "panel_zone_proxy_artifact_present": bool(proxy_artifact),
            "dataset_contract_pass": bool(_safe_bool(dataset.get("contract_pass", False))),
            "pbd_contract_pass": bool(_safe_bool(pbd.get("contract_pass", False))),
        },
        "artifact_meta": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "pbd_review_package": str(args.pbd_review_package),
            "panel_zone_clash_artifact": str(args.panel_zone_clash_artifact) or "",
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote panel-zone clash report: {out}")


if __name__ == "__main__":
    main()
