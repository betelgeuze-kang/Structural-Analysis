#!/usr/bin/env python3
"""Generate a signed release registry anchored to version-lock artifacts."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

try:
    from implementation.phase1.project_registry_service import build_project_registry
except ImportError:  # pragma: no cover - script execution fallback
    from project_registry_service import build_project_registry


REASONS = {
    "PASS": "signed release registry generated",
    "ERR_INPUT": "invalid or missing registry input",
    "ERR_SOURCE_GATE": "one or more source reports are not green",
    "ERR_SIGNATURE": "registry signing or verification failed",
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _json_green(payload: dict) -> bool:
    if "all_pass" in payload:
        return bool(payload.get("all_pass", False))
    if "contract_pass" in payload:
        return bool(payload.get("contract_pass", False))
    if "pass" in payload:
        return bool(payload.get("pass", False))
    return False


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _openssl(args: list[str]) -> None:
    proc = subprocess.run(args, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "openssl failed").strip())


def _ensure_keypair(private_key: Path, public_key: Path) -> bool:
    generated = False
    if not private_key.exists():
        private_key.parent.mkdir(parents=True, exist_ok=True)
        _openssl(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)])
        generated = True
    if generated or not public_key.exists():
        public_key.parent.mkdir(parents=True, exist_ok=True)
        _openssl(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)])
    return generated


def _artifact_entry(label: str, path: Path, payload: dict | None = None) -> dict:
    entry = {
        "label": label,
        "path": str(path),
        "sha256": _sha256_file(path),
        "bytes": int(path.stat().st_size),
    }
    if isinstance(payload, dict):
        if "reason_code" in payload:
            entry["reason_code"] = str(payload.get("reason_code", ""))
        if "contract_pass" in payload:
            entry["contract_pass"] = bool(payload.get("contract_pass", False))
    return entry


def _optional_artifact_entry(label: str, path: Path | None) -> tuple[dict | None, dict]:
    if path is None or not path.exists():
        return None, {}
    payload: dict | None = None
    try:
        if path.suffix.lower() == ".json":
            loaded = _load_json(path)
            payload = loaded if isinstance(loaded, dict) else None
    except Exception:
        payload = None
    return _artifact_entry(label, path, payload), (payload or {})


def _project_registry_audit_payload(*, artifact_entries: list[dict], generated_at: str) -> dict:
    rows = []
    for index, entry in enumerate(artifact_entries, start=1):
        path = Path(str(entry.get("path", "") or ""))
        rows.append(
            {
                "event_id": f"release-registry-artifact-{index:03d}",
                "actor": "generate_signed_release_registry",
                "action": "packaged_artifact",
                "status": "completed",
                "artifact_label": path.name,
                "timestamp": generated_at,
                "note": str(entry.get("label", "")),
            }
        )
    return {"audit_log": rows}


def _project_registry_approval_payload(*, generated_at: str) -> dict:
    return {
        "approvals": [
            {
                "gate_id": "release_registry_source_gate",
                "approver": "generate_signed_release_registry",
                "status": "approved",
                "decided_at": generated_at,
                "comment": "all release source gates passed",
            },
            {
                "gate_id": "release_registry_signature_gate",
                "approver": "generate_signed_release_registry",
                "status": "approved",
                "decided_at": generated_at,
                "comment": "release registry signature verified",
            },
        ]
    }


def _mgt_export_provenance_from_gap(gap_summary: dict) -> dict:
    direct_patch_label = str(gap_summary.get("mgt_export_direct_patch_action_family_label", "") or "")
    sidecar_label = str(gap_summary.get("mgt_export_instruction_sidecar_action_family_label", "") or "")
    sidecar_audit_label = str(gap_summary.get("mgt_export_instruction_sidecar_audit_only_action_family_label", "") or "")
    sidecar_manual_label = str(gap_summary.get("mgt_export_instruction_sidecar_manual_input_action_family_label", "") or "")
    rebar_delivery_mode = "structured_sidecar_only"
    if bool(gap_summary.get("mgt_export_rebar_direct_patch_eligible_change_count", 0)):
        rebar_delivery_mode = "direct_patch_eligible"
    elif bool(gap_summary.get("mgt_export_group_local_rebar_payload_row_count", 0)):
        rebar_delivery_mode = "group_local_payload_present_but_unmapped"
    return {
        "mgt_export_support_mode": str(gap_summary.get("mgt_export_support_mode", "")),
        "mgt_export_direct_patch_change_count": int(gap_summary.get("mgt_export_direct_patch_change_count", 0) or 0),
        "mgt_export_direct_patch_action_family_label": direct_patch_label,
        "mgt_export_instruction_sidecar_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_change_count", 0) or 0
        ),
        "mgt_export_instruction_sidecar_action_family_label": sidecar_label,
        "mgt_export_instruction_sidecar_audit_only_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_audit_only_change_count", 0) or 0
        ),
        "mgt_export_instruction_sidecar_audit_only_action_family_label": sidecar_audit_label,
        "mgt_export_instruction_sidecar_manual_input_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_manual_input_change_count", 0) or 0
        ),
        "mgt_export_instruction_sidecar_manual_input_action_family_label": sidecar_manual_label,
        "mgt_export_audit_review_manifest_change_count": int(
            gap_summary.get("mgt_export_audit_review_manifest_change_count", 0) or 0
        ),
        "mgt_export_audit_review_manifest_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_manifest_action_family_label", "") or ""
        ),
        "mgt_export_audit_review_packet_count": int(
            gap_summary.get("mgt_export_audit_review_packet_count", 0) or 0
        ),
        "mgt_export_audit_review_packet_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_packet_action_family_label", "") or ""
        ),
        "mgt_export_audit_review_packet_followup_type_label": str(
            gap_summary.get("mgt_export_audit_review_packet_followup_type_label", "") or ""
        ),
        "mgt_export_audit_review_packet_file_count": int(
            gap_summary.get("mgt_export_audit_review_packet_file_count", 0) or 0
        ),
        "mgt_export_audit_review_packet_file_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_packet_file_action_family_label", "") or ""
        ),
        "mgt_export_audit_review_queue_item_count": int(
            gap_summary.get("mgt_export_audit_review_queue_item_count", 0) or 0
        ),
        "mgt_export_audit_review_queue_pending_count": int(
            gap_summary.get("mgt_export_audit_review_queue_pending_count", 0) or 0
        ),
        "mgt_export_audit_review_queue_acknowledged_count": int(
            gap_summary.get("mgt_export_audit_review_queue_acknowledged_count", 0) or 0
        ),
        "mgt_export_audit_review_queue_status_label": str(
            gap_summary.get("mgt_export_audit_review_queue_status_label", "") or ""
        ),
        "mgt_export_audit_review_queue_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_queue_action_family_label", "") or ""
        ),
        "mgt_export_audit_review_followup_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_item_count", 0) or 0
        ),
        "mgt_export_audit_review_followup_open_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_open_item_count", 0) or 0
        ),
        "mgt_export_audit_review_followup_closed_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_closed_item_count", 0) or 0
        ),
        "mgt_export_audit_review_followup_action_label": str(
            gap_summary.get("mgt_export_audit_review_followup_action_label", "") or ""
        ),
        "mgt_export_audit_review_followup_owner_label": str(
            gap_summary.get("mgt_export_audit_review_followup_owner_label", "") or ""
        ),
        "mgt_export_audit_review_followup_review_owner_label": str(
            gap_summary.get("mgt_export_audit_review_followup_review_owner_label", "") or ""
        ),
        "mgt_export_audit_review_followup_status_label": str(
            gap_summary.get("mgt_export_audit_review_followup_status_label", "") or ""
        ),
        "mgt_export_audit_review_followup_sla_state_label": str(
            gap_summary.get("mgt_export_audit_review_followup_sla_state_label", "") or ""
        ),
        "mgt_export_audit_review_followup_age_bucket_label": str(
            gap_summary.get("mgt_export_audit_review_followup_age_bucket_label", "") or ""
        ),
        "mgt_export_audit_review_followup_overdue_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_overdue_item_count", 0) or 0
        ),
        "mgt_export_audit_review_followup_oldest_open_age_hours": float(
            gap_summary.get("mgt_export_audit_review_followup_oldest_open_age_hours", 0.0) or 0.0
        ),
        "mgt_export_audit_review_followup_oldest_open_packet_id": str(
            gap_summary.get("mgt_export_audit_review_followup_oldest_open_packet_id", "") or ""
        ),
        "mgt_export_audit_review_followup_mode": str(
            gap_summary.get("mgt_export_audit_review_followup_mode", "") or ""
        ),
        "mgt_export_audit_review_resolution_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_item_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_file_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_file_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_open_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_open_item_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_closed_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_closed_item_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_pending_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_pending_item_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_open_revision_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_open_revision_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_closed_packet_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_closed_packet_count", 0) or 0
        ),
        "mgt_export_audit_review_resolution_action_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_action_label", "") or ""
        ),
        "mgt_export_audit_review_resolution_owner_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_owner_label", "") or ""
        ),
        "mgt_export_audit_review_resolution_status_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_status_label", "") or ""
        ),
        "mgt_export_audit_review_resolution_mode": str(
            gap_summary.get("mgt_export_audit_review_resolution_mode", "") or ""
        ),
        "mgt_export_rebar_payload_namespace_mode": str(
            gap_summary.get("mgt_export_rebar_payload_namespace_mode", "")
        ),
        "mgt_export_rebar_payload_material_level_namespace_present": bool(
            gap_summary.get("mgt_export_rebar_payload_material_level_namespace_present", False)
        ),
        "mgt_export_rebar_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_rebar_payload_group_local_namespace_present", False)
        ),
        "mgt_export_group_local_rebar_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_rebar_payload_row_count", 0) or 0
        ),
        "mgt_export_group_local_rebar_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_rebar_payload_available_count", 0) or 0
        ),
        "mgt_export_group_local_connection_detailing_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_connection_detailing_payload_row_count", 0) or 0
        ),
        "mgt_export_group_local_connection_detailing_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_connection_detailing_payload_available_count", 0) or 0
        ),
        "mgt_export_group_local_detailing_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_detailing_payload_row_count", 0) or 0
        ),
        "mgt_export_group_local_detailing_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_detailing_payload_available_count", 0) or 0
        ),
        "mgt_export_connection_detailing_payload_namespace_mode": str(
            gap_summary.get("mgt_export_connection_detailing_payload_namespace_mode", "")
        ),
        "mgt_export_connection_detailing_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_connection_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_detailing_payload_namespace_mode": str(
            gap_summary.get("mgt_export_detailing_payload_namespace_mode", "")
        ),
        "mgt_export_detailing_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": int(
            gap_summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0) or 0
        ),
        "mgt_export_connection_detailing_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_connection_detailing_direct_patch_eligible_change_count", 0) or 0
        ),
        "mgt_export_detailing_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_detailing_direct_patch_eligible_change_count", 0) or 0
        ),
        "mgt_export_detailing_structured_payload_mapped_change_count": int(
            gap_summary.get("mgt_export_detailing_structured_payload_mapped_change_count", 0) or 0
        ),
        "mgt_export_connection_detailing_delivery_mode": str(
            gap_summary.get("mgt_export_connection_detailing_delivery_mode", "")
        ),
        "mgt_export_detailing_delivery_mode": str(gap_summary.get("mgt_export_detailing_delivery_mode", "")),
        "mgt_export_rebar_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_rebar_direct_patch_eligible_change_count", 0) or 0
        ),
        "mgt_export_patched_material_row_count": int(gap_summary.get("mgt_export_patched_material_row_count", 0) or 0),
        "mgt_export_cloned_material_count": int(gap_summary.get("mgt_export_cloned_material_count", 0) or 0),
        "mgt_export_rebar_direct_patch_ineligible_reason_label": str(
            gap_summary.get("mgt_export_rebar_direct_patch_ineligible_reason_label", "")
        ),
        "mgt_export_rebar_direct_patch_mapping_source_label": str(
            gap_summary.get("mgt_export_rebar_direct_patch_mapping_source_label", "")
        ),
        "mgt_export_rebar_delivery_mode": rebar_delivery_mode,
        "mgt_export_delivery_boundary": (
            f"direct_patch={direct_patch_label or 'n/a'} | "
            f"sidecar={sidecar_label or 'n/a'} | "
            f"connection_payload={str(gap_summary.get('mgt_export_connection_detailing_delivery_mode', '') or 'n/a')} | "
            f"detailing_payload={str(gap_summary.get('mgt_export_detailing_delivery_mode', '') or 'n/a')}"
        ),
        "mgt_export_evidence_model": str(
            gap_summary.get("mgt_export_evidence_model", "")
            or (
                "direct_patch_plus_structured_sidecar"
                if int(gap_summary.get("mgt_export_instruction_sidecar_change_count", 0) or 0) > 0
                else "direct_patch_only"
            )
        ),
    }


def _advanced_holdout_provenance_from_gap(gap_summary: dict) -> dict:
    return {
        "pbd_dynamic_hinge_refresh_ready": bool(gap_summary.get("pbd_dynamic_hinge_refresh_ready", False)),
        "pbd_hinge_state_mode": str(gap_summary.get("pbd_hinge_state_mode", "") or ""),
        "pbd_hinge_refresh_reason": str(gap_summary.get("pbd_hinge_refresh_reason", "") or ""),
        "pbd_hinge_refresh_artifact_present": bool(gap_summary.get("pbd_hinge_refresh_artifact_present", False)),
        "pbd_hinge_refresh_artifact_kind": str(gap_summary.get("pbd_hinge_refresh_artifact_kind", "") or ""),
        "pbd_hinge_refresh_source_mode": str(gap_summary.get("pbd_hinge_refresh_source_mode", "") or ""),
        "pbd_hinge_refresh_overlap_member_count": int(gap_summary.get("pbd_hinge_refresh_overlap_member_count", 0) or 0),
        "pbd_hinge_refresh_rebar_sensitive_member_count": int(
            gap_summary.get("pbd_hinge_refresh_rebar_sensitive_member_count", 0) or 0
        ),
        "pbd_hinge_benchmark_gate_pass": bool(gap_summary.get("pbd_hinge_benchmark_gate_pass", False)),
        "pbd_hinge_benchmark_fixture_regression_pass": bool(
            gap_summary.get("pbd_hinge_benchmark_fixture_regression_pass", False)
        ),
        "pbd_hinge_benchmark_alignment_pass": bool(gap_summary.get("pbd_hinge_benchmark_alignment_pass", False)),
        "pbd_hinge_benchmark_asset_count": int(gap_summary.get("pbd_hinge_benchmark_asset_count", 0) or 0),
        "pbd_hinge_benchmark_train_count": int(gap_summary.get("pbd_hinge_benchmark_train_count", 0) or 0),
        "pbd_hinge_benchmark_val_count": int(gap_summary.get("pbd_hinge_benchmark_val_count", 0) or 0),
        "pbd_hinge_benchmark_holdout_count": int(gap_summary.get("pbd_hinge_benchmark_holdout_count", 0) or 0),
        "pbd_hinge_benchmark_rebar_sensitive_count": int(
            gap_summary.get("pbd_hinge_benchmark_rebar_sensitive_count", 0) or 0
        ),
        "pbd_hinge_benchmark_confinement_sensitive_count": int(
            gap_summary.get("pbd_hinge_benchmark_confinement_sensitive_count", 0) or 0
        ),
        "pbd_hinge_benchmark_fixture_count": int(gap_summary.get("pbd_hinge_benchmark_fixture_count", 0) or 0),
        "pbd_hinge_benchmark_fixture_min_point_count": int(
            gap_summary.get("pbd_hinge_benchmark_fixture_min_point_count", 0) or 0
        ),
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": float(
            gap_summary.get("pbd_hinge_benchmark_fixture_min_peak_drift_ratio", 0.0) or 0.0
        ),
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": int(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_column_row_count", 0) or 0
        ),
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": int(
            gap_summary.get("pbd_hinge_benchmark_alignment_rebar_sensitive_column_count", 0) or 0
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min", 0.0) or 0.0
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max", 0.0) or 0.0
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min", 0.0) or 0.0
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max", 0.0) or 0.0
        ),
        "panel_zone_3d_clash_ready": bool(gap_summary.get("panel_zone_3d_clash_ready", False)),
        "panel_zone_constructability_mode": str(gap_summary.get("panel_zone_constructability_mode", "") or ""),
        "panel_zone_constructability_reason": str(gap_summary.get("panel_zone_constructability_reason", "") or ""),
        "panel_zone_proxy_candidate_count": int(gap_summary.get("panel_zone_proxy_candidate_count", 0) or 0),
        "panel_zone_source_artifact_kind": str(gap_summary.get("panel_zone_source_artifact_kind", "") or ""),
        "panel_zone_source_artifact_path": str(gap_summary.get("panel_zone_source_artifact_path", "") or ""),
        "panel_zone_source_contract_mode": str(gap_summary.get("panel_zone_source_contract_mode", "") or ""),
        "panel_zone_internal_engine_complete": bool(gap_summary.get("panel_zone_internal_engine_complete", False)),
        "panel_zone_external_validation_pending": bool(
            gap_summary.get("panel_zone_external_validation_pending", False)
        ),
        "panel_zone_validation_boundary": str(gap_summary.get("panel_zone_validation_boundary", "") or ""),
        "panel_zone_instruction_sidecar_present": bool(gap_summary.get("panel_zone_instruction_sidecar_present", False)),
        "panel_zone_instruction_sidecar_change_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_change_count", 0) or 0
        ),
        "panel_zone_instruction_sidecar_candidate_overlap_mode": str(
            gap_summary.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "") or ""
        ),
        "panel_zone_instruction_sidecar_overlap_row_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_row_count", 0) or 0
        ),
        "panel_zone_instruction_sidecar_overlap_member_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_member_count", 0) or 0
        ),
        "panel_zone_instruction_sidecar_overlap_group_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_group_count", 0) or 0
        ),
        "panel_zone_instruction_sidecar_evidence_model": str(
            gap_summary.get("panel_zone_instruction_sidecar_evidence_model", "") or ""
        ),
        "panel_zone_instruction_sidecar_rebar_delivery_mode": str(
            gap_summary.get("panel_zone_instruction_sidecar_rebar_delivery_mode", "") or ""
        ),
        "panel_zone_source_valid_row_counts": dict(gap_summary.get("panel_zone_source_valid_row_counts", {}) or {}),
        "panel_zone_source_overlap_member_counts": dict(
            gap_summary.get("panel_zone_source_overlap_member_counts", {}) or {}
        ),
        "panel_zone_source_candidate_scan_modes": dict(
            gap_summary.get("panel_zone_source_candidate_scan_modes", {}) or {}
        ),
        "panel_zone_source_bundle_modes": dict(gap_summary.get("panel_zone_source_bundle_modes", {}) or {}),
        "panel_zone_source_upstream_verification_tiers": dict(
            gap_summary.get("panel_zone_source_upstream_verification_tiers", {}) or {}
        ),
        "panel_zone_validated_source_row_count_total": int(
            gap_summary.get("panel_zone_validated_source_row_count_total", 0) or 0
        ),
        "panel_zone_validated_source_overlap_member_count_min": int(
            gap_summary.get("panel_zone_validated_source_overlap_member_count_min", 0) or 0
        ),
        "panel_zone_missing_required_sources": list(gap_summary.get("panel_zone_missing_required_sources", []) or []),
        "panel_zone_solver_verified_inbox_status_mode": str(
            gap_summary.get("panel_zone_solver_verified_inbox_status_mode", "") or ""
        ),
        "panel_zone_solver_verified_inbox_has_input": bool(
            gap_summary.get("panel_zone_solver_verified_inbox_has_input", False)
        ),
        "panel_zone_solver_verified_pending_input": bool(
            gap_summary.get("panel_zone_solver_verified_pending_input", False)
        ),
        "panel_zone_solver_verified_input_mode_detected": str(
            gap_summary.get("panel_zone_solver_verified_input_mode_detected", "") or ""
        ),
        "panel_zone_solver_verified_latest_consume_report_present": bool(
            gap_summary.get("panel_zone_solver_verified_latest_consume_report_present", False)
        ),
        "panel_zone_solver_verified_latest_consume_contract_pass": bool(
            gap_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
        ),
        "panel_zone_solver_verified_latest_consume_reason_code": str(
            gap_summary.get("panel_zone_solver_verified_latest_consume_reason_code", "") or ""
        ),
        "panel_zone_solver_verified_source_origin_class": str(
            gap_summary.get("panel_zone_solver_verified_source_origin_class", "") or ""
        ),
        "panel_zone_solver_verified_release_refresh_source_allowed": bool(
            gap_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
        ),
        "panel_zone_solver_verified_recommended_action": str(
            gap_summary.get("panel_zone_solver_verified_recommended_action", "") or ""
        ),
        "panel_zone_topology_capable_input": bool(gap_summary.get("panel_zone_topology_capable_input", False)),
        "panel_zone_true_3d_clash_verified": bool(gap_summary.get("panel_zone_true_3d_clash_verified", False)),
        "panel_zone_true_3d_anchorage_verified": bool(gap_summary.get("panel_zone_true_3d_anchorage_verified", False)),
        "foundation_optimization_ready": bool(gap_summary.get("foundation_optimization_ready", False)),
        "foundation_member_type_present": bool(gap_summary.get("foundation_member_type_present", False)),
        "foundation_member_type_count": int(gap_summary.get("foundation_member_type_count", 0) or 0),
        "foundation_optimization_mode": str(gap_summary.get("foundation_optimization_mode", "") or ""),
        "foundation_optimization_reason": str(gap_summary.get("foundation_optimization_reason", "") or ""),
        "foundation_scope_source": str(gap_summary.get("foundation_scope_source", "") or ""),
        "foundation_artifact_scan_mode": str(gap_summary.get("foundation_artifact_scan_mode", "") or ""),
        "foundation_artifact_evidence_mode": str(gap_summary.get("foundation_artifact_evidence_mode", "") or ""),
        "upstream_foundation_label_count": int(gap_summary.get("upstream_foundation_label_count", 0) or 0),
        "raw_source_foundation_label_count": int(gap_summary.get("raw_source_foundation_label_count", 0) or 0),
        "upstream_foundation_provenance_mode": str(gap_summary.get("upstream_foundation_provenance_mode", "") or ""),
        "wind_tunnel_raw_mapping_ready": bool(gap_summary.get("wind_tunnel_raw_mapping_ready", False)),
        "wind_tunnel_mapping_mode": str(gap_summary.get("wind_tunnel_mapping_mode", "") or ""),
        "wind_tunnel_mapping_reason": str(gap_summary.get("wind_tunnel_mapping_reason", "") or ""),
    }


def _advanced_holdout_closure_surface_from_gap_report(gap_report: dict) -> dict:
    rows = [
        row
        for row in (gap_report.get("advanced_holdouts") or [])
        if isinstance(row, dict)
    ]

    def _compact_text(value: object, *, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: max(limit - 3, 0)].rstrip() + "..."

    status_rows = []
    severity_counts: dict[str, int] = {}
    for row in rows:
        severity = str(row.get("severity", "") or "")
        if severity:
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        ready = bool(row.get("ready", False))
        status_rows.append(
            {
                "id": str(row.get("id", "") or ""),
                "title": str(row.get("title", "") or ""),
                "severity": severity,
                "closure_state": "closed" if ready else "open",
                "ready": ready,
                "mode": str(row.get("mode", row.get("status_label", "")) or ""),
                "reason_snippet": _compact_text(row.get("reason", ""), limit=160),
                "evidence_snippet": _compact_text(row.get("evidence", ""), limit=280),
            }
        )

    closed_count = sum(1 for row in status_rows if bool(row.get("ready", False)))
    total_count = len(status_rows)
    open_count = max(total_count - closed_count, 0)
    severity_label = ", ".join(
        f"{severity}:{count}" for severity, count in sorted(severity_counts.items())
    )
    summary_line = (
        f"closed={closed_count}/{total_count} | open={open_count}"
        + (f" | severities={severity_label}" if severity_label else "")
    )
    return {
        "advanced_holdout_total_count": int(total_count),
        "advanced_holdout_closed_count": int(closed_count),
        "advanced_holdout_open_count": int(open_count),
        "advanced_holdout_closure_summary_line": summary_line,
        "advanced_holdout_status_rows": status_rows,
    }


def _external_benchmark_execution_provenance_from_committee_summary(committee_summary: dict) -> dict:
    metrics = committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {}
    pbd_resolved_ndtha_report = str(metrics.get("pbd_resolved_ndtha_report", "") or "")
    pbd_resolved_ndtha_response_npz = str(metrics.get("pbd_resolved_ndtha_response_npz", "") or "")
    pbd_ndtha_response_fallback_used = bool(metrics.get("pbd_ndtha_response_fallback_used", False))
    pbd_ndtha_response_coverage_count = int(metrics.get("pbd_ndtha_response_coverage_count", 0) or 0)
    return {
        "pbd_resolved_ndtha_report": pbd_resolved_ndtha_report,
        "pbd_resolved_ndtha_response_npz": pbd_resolved_ndtha_response_npz,
        "pbd_ndtha_response_fallback_used": pbd_ndtha_response_fallback_used,
        "pbd_ndtha_response_coverage_count": pbd_ndtha_response_coverage_count,
        "pbd_response_source_label": (
            f"resolved_report={pbd_resolved_ndtha_report or 'n/a'} | "
            f"response_npz={pbd_resolved_ndtha_response_npz or 'n/a'} | "
            f"fallback_used={pbd_ndtha_response_fallback_used} | "
            f"coverage={pbd_ndtha_response_coverage_count}"
        ),
        "audit_review_decision_batch_template_item_count": int(
            metrics.get("audit_review_decision_batch_template_item_count", 0) or 0
        ),
        "audit_review_decision_batch_template_current_status_label": str(
            metrics.get("audit_review_decision_batch_template_current_status_label", "") or ""
        ),
        "audit_review_decision_batch_template_review_owner_label": str(
            metrics.get("audit_review_decision_batch_template_review_owner_label", "") or ""
        ),
        "audit_review_decision_batch_template_review_priority_label": str(
            metrics.get("audit_review_decision_batch_template_review_priority_label", "") or ""
        ),
        "audit_review_decision_batch_attested_example_count": int(
            metrics.get("audit_review_decision_batch_attested_example_count", 0) or 0
        ),
        "audit_review_decision_batch_attested_example_preview_label": str(
            metrics.get("audit_review_decision_batch_attested_example_preview_label", "") or ""
        ),
        "external_benchmark_submission_preview_approve_all_reason_code": str(
            metrics.get("external_benchmark_submission_preview_approve_all_reason_code", "") or ""
        ),
        "external_benchmark_submission_preview_approve_all_ready_full": bool(
            metrics.get("external_benchmark_submission_preview_approve_all_ready_full", False)
        ),
        "external_benchmark_submission_preview_approve_all_pending_count": int(
            metrics.get("external_benchmark_submission_preview_approve_all_pending_count", 0) or 0
        ),
        "external_benchmark_submission_preview_approve_all_open_revision_count": int(
            metrics.get("external_benchmark_submission_preview_approve_all_open_revision_count", 0) or 0
        ),
        "external_benchmark_submission_preview_reject_one_reason_code": str(
            metrics.get("external_benchmark_submission_preview_reject_one_reason_code", "") or ""
        ),
        "external_benchmark_submission_preview_reject_one_ready_full": bool(
            metrics.get("external_benchmark_submission_preview_reject_one_ready_full", False)
        ),
        "external_benchmark_submission_preview_reject_one_pending_count": int(
            metrics.get("external_benchmark_submission_preview_reject_one_pending_count", 0) or 0
        ),
        "external_benchmark_submission_preview_reject_one_open_revision_count": int(
            metrics.get("external_benchmark_submission_preview_reject_one_open_revision_count", 0) or 0
        ),
        "external_benchmark_submission_preview_reject_one_blocker_label": str(
            metrics.get("external_benchmark_submission_preview_reject_one_blocker_label", "") or ""
        ),
        "audit_review_decision_batch_runner_reason_code": str(
            metrics.get("audit_review_decision_batch_runner_reason_code", "") or ""
        ),
        "audit_review_decision_batch_runner_apply_live": bool(
            metrics.get("audit_review_decision_batch_runner_apply_live", False)
        ),
        "audit_review_decision_batch_runner_live_applied": bool(
            metrics.get("audit_review_decision_batch_runner_live_applied", False)
        ),
        "audit_review_decision_batch_runner_preview_reason_code": str(
            metrics.get("audit_review_decision_batch_runner_preview_reason_code", "") or ""
        ),
        "audit_review_decision_batch_runner_preview_ready_full": bool(
            metrics.get("audit_review_decision_batch_runner_preview_ready_full", False)
        ),
        "audit_review_decision_batch_runner_preview_pending_count": int(
            metrics.get("audit_review_decision_batch_runner_preview_pending_count", 0) or 0
        ),
        "audit_review_decision_batch_runner_preview_open_revision_count": int(
            metrics.get("audit_review_decision_batch_runner_preview_open_revision_count", 0) or 0
        ),
        "audit_review_decision_batch_runner_live_preview_reason_code": str(
            metrics.get("audit_review_decision_batch_runner_live_preview_reason_code", "") or ""
        ),
        "external_benchmark_execution_mode": str(metrics.get("external_benchmark_execution_mode", "") or ""),
        "external_benchmark_execution_ready_task_count": int(
            metrics.get("external_benchmark_execution_ready_task_count", 0) or 0
        ),
        "external_benchmark_execution_blocked_task_count": int(
            metrics.get("external_benchmark_execution_blocked_task_count", 0) or 0
        ),
        "external_benchmark_execution_review_boundary_pending_count": int(
            metrics.get("external_benchmark_execution_review_boundary_pending_count", 0) or 0
        ),
        "external_benchmark_execution_review_boundary_resolution_label": str(
            metrics.get("external_benchmark_execution_review_boundary_resolution_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_owner_label": str(
            metrics.get("external_benchmark_execution_review_boundary_owner_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_assignee_label": str(
            metrics.get("external_benchmark_execution_review_boundary_assignee_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_assignment_status_label": str(
            metrics.get("external_benchmark_execution_review_boundary_assignment_status_label", "")
            or ""
        ),
        "external_benchmark_execution_review_boundary_priority_label": str(
            metrics.get("external_benchmark_execution_review_boundary_priority_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_family_label": str(
            metrics.get("external_benchmark_execution_review_boundary_family_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_change_count_total": int(
            metrics.get("external_benchmark_execution_review_boundary_change_count_total", 0) or 0
        ),
        "external_benchmark_execution_review_boundary_followup_action_label": str(
            metrics.get("external_benchmark_execution_review_boundary_followup_action_label", "")
            or ""
        ),
        "external_benchmark_execution_review_boundary_sla_state_label": str(
            metrics.get("external_benchmark_execution_review_boundary_sla_state_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_age_bucket_label": str(
            metrics.get("external_benchmark_execution_review_boundary_age_bucket_label", "") or ""
        ),
        "external_benchmark_execution_review_boundary_overdue_count": int(
            metrics.get("external_benchmark_execution_review_boundary_overdue_count", 0) or 0
        ),
        "external_benchmark_execution_review_boundary_oldest_open_age_hours": float(
            metrics.get("external_benchmark_execution_review_boundary_oldest_open_age_hours", 0.0)
            or 0.0
        ),
        "external_benchmark_execution_review_boundary_preview_approve_all_reason_code": str(
            metrics.get("external_benchmark_execution_review_boundary_preview_approve_all_reason_code", "")
            or ""
        ),
        "external_benchmark_execution_review_boundary_preview_approve_all_ready_full": bool(
            metrics.get("external_benchmark_execution_review_boundary_preview_approve_all_ready_full", False)
        ),
        "external_benchmark_execution_review_boundary_preview_reject_one_reason_code": str(
            metrics.get("external_benchmark_execution_review_boundary_preview_reject_one_reason_code", "")
            or ""
        ),
        "external_benchmark_execution_review_boundary_preview_reject_one_open_revision_count": int(
            metrics.get(
                "external_benchmark_execution_review_boundary_preview_reject_one_open_revision_count",
                0,
            )
            or 0
        ),
        "external_benchmark_execution_status_mode": str(
            metrics.get("external_benchmark_execution_status_mode", "") or ""
        ),
        "external_benchmark_execution_executable_task_count": int(
            metrics.get("external_benchmark_execution_executable_task_count", 0) or 0
        ),
        "external_benchmark_execution_planned_task_count": int(
            metrics.get("external_benchmark_execution_planned_task_count", 0) or 0
        ),
        "external_benchmark_execution_in_progress_task_count": int(
            metrics.get("external_benchmark_execution_in_progress_task_count", 0) or 0
        ),
        "external_benchmark_execution_completed_task_count": int(
            metrics.get("external_benchmark_execution_completed_task_count", 0) or 0
        ),
        "external_benchmark_execution_failed_task_count": int(
            metrics.get("external_benchmark_execution_failed_task_count", 0) or 0
        ),
        "external_benchmark_execution_finished_task_count": int(
            metrics.get("external_benchmark_execution_finished_task_count", 0) or 0
        ),
        "external_benchmark_execution_completion_ratio": float(
            metrics.get("external_benchmark_execution_completion_ratio", 0.0) or 0.0
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repro-report", default="implementation/phase1/reproducibility_version_lock_report.json")
    p.add_argument("--lock-manifest", default="implementation/phase1/release/version_lock_manifest.json")
    p.add_argument("--kds-summary", default="implementation/phase1/release/kds_compliance/kds_compliance_summary.json")
    p.add_argument("--midas-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--solver-hip-e2e", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    p.add_argument("--committee-package", default="implementation/phase1/release/committee_review/committee_review_package_report.json")
    p.add_argument("--committee-summary", default="implementation/phase1/release/committee_review/committee_summary.json")
    p.add_argument("--gap-report", default="implementation/phase1/release/release_gap_report.json")
    p.add_argument("--external-benchmark-submission-readiness", default="")
    p.add_argument("--external-benchmark-kickoff-package", default="")
    p.add_argument("--external-benchmark-kickoff-markdown", default="")
    p.add_argument("--external-benchmark-execution-manifest", default="")
    p.add_argument("--external-benchmark-execution-manifest-markdown", default="")
    p.add_argument("--external-benchmark-execution-status", default="")
    p.add_argument("--external-benchmark-execution-status-markdown", default="")
    p.add_argument("--case-onepage-attestation-index", default="")
    p.add_argument("--case-onepage-attestation-index-markdown", default="")
    p.add_argument("--audit-review-decision-batch-template", default="")
    p.add_argument("--audit-review-decision-batch-template-markdown", default="")
    p.add_argument("--approve-all-submission-readiness-preview", default="")
    p.add_argument("--approve-all-submission-readiness-preview-markdown", default="")
    p.add_argument("--exact-topology-structural-preview-promotion-queue", default="")
    p.add_argument("--exact-topology-structural-preview-promotion-queue-markdown", default="")
    p.add_argument("--ci-report", default="")
    p.add_argument("--parser-script", default="implementation/phase1/parse_midas_mgt_to_json_npz.py")
    p.add_argument("--private-key-out", default="implementation/phase1/release/signing/release_registry_ed25519.pem")
    p.add_argument("--public-key-out", default="implementation/phase1/release/signing/release_registry_ed25519.pub.pem")
    p.add_argument("--signature-out", default="implementation/phase1/release/signing/release_registry.signature.b64")
    p.add_argument("--project-private-key-out", default="")
    p.add_argument("--project-public-key-out", default="")
    p.add_argument("--project-signature-out", default="")
    p.add_argument("--project-package-out", default="")
    p.add_argument("--project-registry-out", default="")
    p.add_argument("--out", default="implementation/phase1/release/release_registry.json")
    p.add_argument(
        "--generated-at",
        default="",
        help="Optional fixed ISO timestamp for reproducible release registry/package generation.",
    )
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        repro_path = Path(args.repro_report)
        lock_path = Path(args.lock_manifest)
        kds_path = Path(args.kds_summary)
        midas_path = Path(args.midas_conversion)
        solver_path = Path(args.solver_hip_e2e)
        committee_path = Path(args.committee_package) if str(args.committee_package).strip() else None
        committee_summary_path = Path(args.committee_summary) if str(args.committee_summary).strip() else None
        gap_report_path = Path(args.gap_report) if str(args.gap_report).strip() else None
        external_artifact_paths = [
            ("external_benchmark_submission_readiness", Path(args.external_benchmark_submission_readiness) if str(args.external_benchmark_submission_readiness).strip() else None),
            ("external_benchmark_kickoff_package", Path(args.external_benchmark_kickoff_package) if str(args.external_benchmark_kickoff_package).strip() else None),
            ("external_benchmark_kickoff_markdown", Path(args.external_benchmark_kickoff_markdown) if str(args.external_benchmark_kickoff_markdown).strip() else None),
            ("external_benchmark_execution_manifest", Path(args.external_benchmark_execution_manifest) if str(args.external_benchmark_execution_manifest).strip() else None),
            ("external_benchmark_execution_manifest_markdown", Path(args.external_benchmark_execution_manifest_markdown) if str(args.external_benchmark_execution_manifest_markdown).strip() else None),
            ("external_benchmark_execution_status", Path(args.external_benchmark_execution_status) if str(args.external_benchmark_execution_status).strip() else None),
            ("external_benchmark_execution_status_markdown", Path(args.external_benchmark_execution_status_markdown) if str(args.external_benchmark_execution_status_markdown).strip() else None),
            ("case_onepage_attestation_index", Path(args.case_onepage_attestation_index) if str(args.case_onepage_attestation_index).strip() else None),
            ("case_onepage_attestation_index_markdown", Path(args.case_onepage_attestation_index_markdown) if str(args.case_onepage_attestation_index_markdown).strip() else None),
            ("audit_review_decision_batch_template", Path(args.audit_review_decision_batch_template) if str(args.audit_review_decision_batch_template).strip() else None),
            ("audit_review_decision_batch_template_markdown", Path(args.audit_review_decision_batch_template_markdown) if str(args.audit_review_decision_batch_template_markdown).strip() else None),
            ("approve_all_submission_readiness_preview", Path(args.approve_all_submission_readiness_preview) if str(args.approve_all_submission_readiness_preview).strip() else None),
            ("approve_all_submission_readiness_preview_markdown", Path(args.approve_all_submission_readiness_preview_markdown) if str(args.approve_all_submission_readiness_preview_markdown).strip() else None),
            ("exact_topology_structural_preview_promotion_queue", Path(args.exact_topology_structural_preview_promotion_queue) if str(args.exact_topology_structural_preview_promotion_queue).strip() else None),
            ("exact_topology_structural_preview_promotion_queue_markdown", Path(args.exact_topology_structural_preview_promotion_queue_markdown) if str(args.exact_topology_structural_preview_promotion_queue_markdown).strip() else None),
        ]
        parser_script = Path(args.parser_script)
        ci_path = Path(args.ci_report) if str(args.ci_report).strip() else None
        private_key = Path(args.private_key_out)
        public_key = Path(args.public_key_out)
        signature_out = Path(args.signature_out)

        required_paths = [repro_path, lock_path, kds_path, midas_path, solver_path, parser_script]
        if ci_path is not None:
            required_paths.append(ci_path)
        missing = [str(pth) for pth in required_paths if not pth.exists()]
        if missing:
            raise FileNotFoundError(",".join(missing))

        repro = _load_json(repro_path)
        lock_manifest = _load_json(lock_path)
        kds = _load_json(kds_path)
        midas = _load_json(midas_path)
        solver = _load_json(solver_path)
        committee = _load_json(committee_path) if committee_path is not None and committee_path.exists() else {}
        committee_summary = (
            _load_json(committee_summary_path)
            if committee_summary_path is not None and committee_summary_path.exists()
            else {}
        )
        gap_report = _load_json(gap_report_path) if gap_report_path is not None and gap_report_path.exists() else {}
        ci = _load_json(ci_path) if ci_path is not None else {}
        gap_summary = gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {}
        gap_release_status = gap_report.get("release_status") if isinstance(gap_report.get("release_status"), dict) else {}
        gap_context = {**gap_release_status, **gap_summary}

        source_reports = {
            "repro_report": repro,
            "kds_summary": kds,
            "midas_conversion": midas,
            "solver_hip_e2e": solver,
        }
        if ci_path is not None:
            source_reports["ci_report"] = ci
        green_reports_pass = bool(all(_json_green(payload) for payload in source_reports.values()))
        if not green_reports_pass:
            raise RuntimeError("ERR_SOURCE_GATE")

        key_generated = _ensure_keypair(private_key, public_key)

        artifact_entries = [
            _artifact_entry("repro_report", repro_path, repro),
            _artifact_entry("lock_manifest", lock_path, lock_manifest),
            _artifact_entry("kds_summary", kds_path, kds),
            _artifact_entry("midas_conversion", midas_path, midas),
            _artifact_entry("solver_hip_e2e", solver_path, solver),
            _artifact_entry("parser_script", parser_script, None),
        ]
        if committee_path is not None and committee_path.exists():
            artifact_entries.append(_artifact_entry("committee_package", committee_path, committee))
        if committee_summary_path is not None and committee_summary_path.exists():
            artifact_entries.append(_artifact_entry("committee_summary", committee_summary_path, committee_summary))
        if gap_report_path is not None and gap_report_path.exists():
            artifact_entries.append(_artifact_entry("release_gap_report", gap_report_path, gap_report))
        if ci_path is not None:
            artifact_entries.append(_artifact_entry("ci_report", ci_path, ci))
        external_benchmark_asset_payloads: dict[str, dict] = {}
        for label, path in external_artifact_paths:
            entry, payload = _optional_artifact_entry(label, path)
            if entry is not None:
                artifact_entries.append(entry)
                external_benchmark_asset_payloads[label] = payload
        external_benchmark_asset_entries = [
            {
                "label": str(row.get("label", "") or ""),
                "path": str(row.get("path", "") or ""),
                "sha256": str(row.get("sha256", "") or ""),
                "bytes": int(row.get("bytes", 0) or 0),
            }
            for row in artifact_entries
            if str(row.get("label", "") or "").startswith(
                (
                    "external_benchmark_",
                    "case_onepage_",
                    "audit_review_decision_batch_",
                    "approve_all_submission_",
                    "exact_topology_",
                )
            )
        ]

        mgt_export_provenance = _mgt_export_provenance_from_gap(gap_context)
        advanced_holdout_provenance = _advanced_holdout_provenance_from_gap(gap_context)
        advanced_holdout_closure_surface = _advanced_holdout_closure_surface_from_gap_report(gap_report)
        external_benchmark_execution_provenance = _external_benchmark_execution_provenance_from_committee_summary(
            committee_summary
        )

        generated_at = str(args.generated_at).strip() or datetime.now(timezone.utc).isoformat()

        registry_body = {
            "schema_version": "1.0",
            "registry_id": "phase1-signed-release-registry",
            "generated_at": generated_at,
            "provenance": {
                "lock_manifest_path": str(lock_path),
                "lock_manifest_sha256": _sha256_file(lock_path),
                "seed": int(lock_manifest.get("seed", 0)),
                "replay_runs": int(lock_manifest.get("replay_runs", 0)),
                "replay_digest": str(lock_manifest.get("replay_digest", "")),
            },
            "input_hashes": dict(lock_manifest.get("input_hashes") or {}),
            "model_hashes": dict(lock_manifest.get("model_hashes") or {}),
            "artifacts": artifact_entries,
            "parser_provenance": {
                "parser_script": str(parser_script),
                "parser_script_sha256": _sha256_file(parser_script),
                "mgt_source_path": str((midas.get("source_provenance") or {}).get("path", "")),
                "mgt_source_sha256": str((midas.get("source_provenance") or {}).get("sha256", "")),
                "element_rows_total": int((midas.get("metrics") or {}).get("element_rows_total", 0)),
                "element_rows_skipped": int((midas.get("metrics") or {}).get("element_rows_skipped", 0)),
                "unknown_row_total": int((midas.get("metrics") or {}).get("unknown_row_total", 0)),
            },
            "package_provenance": {
                "kds_summary_path": str(kds_path),
                "kds_pdf_path": str((kds.get("artifacts") or {}).get("kds_compliance_pdf", "")),
                "committee_package_path": str(committee_path) if committee_path is not None else "",
                "committee_pdf_path": str((committee.get("artifacts") or {}).get("committee_review_pdf", "")),
                "committee_summary_path": str(committee_summary_path) if committee_summary_path is not None else "",
                "release_gap_report_path": str(gap_report_path) if gap_report_path is not None else "",
                "pbd_response_source": {
                    "resolved_ndtha_report": str(
                        external_benchmark_execution_provenance.get("pbd_resolved_ndtha_report", "") or ""
                    ),
                    "resolved_ndtha_response_npz": str(
                        external_benchmark_execution_provenance.get("pbd_resolved_ndtha_response_npz", "") or ""
                    ),
                    "fallback_used": bool(
                        external_benchmark_execution_provenance.get("pbd_ndtha_response_fallback_used", False)
                    ),
                    "coverage_count": int(
                        external_benchmark_execution_provenance.get("pbd_ndtha_response_coverage_count", 0) or 0
                    ),
                    "label": str(external_benchmark_execution_provenance.get("pbd_response_source_label", "") or ""),
                },
                "external_benchmark_release_assets": external_benchmark_asset_entries,
            },
            "accelerated_coverage_provenance": {
                "deployment_model": str(gap_context.get("deployment_model", "")),
                "measured_chain_rolling_selection_mode": str(gap_context.get("measured_chain_rolling_selection_mode", "")),
                "comparable_reference_deployment_model": str(gap_context.get("measured_chain_comparable_reference_deployment_model", "")),
                "comparable_reference_strict_design_opt_cost_smoke": bool(
                    gap_context.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)
                ),
                "authority_catalog_diff_change_count": int(committee_summary.get("authority_catalog_diff_change_count", 0)),
                "authority_catalog_routing_warning_active": bool(
                    committee_summary.get("authority_catalog_routing_warning_active", False)
                ),
                **external_benchmark_execution_provenance,
                **mgt_export_provenance,
                **advanced_holdout_provenance,
                **advanced_holdout_closure_surface,
                "external_benchmark_release_asset_count": int(len(external_benchmark_asset_entries)),
                "external_benchmark_release_asset_labels": [
                    str(row.get("label", "") or "") for row in external_benchmark_asset_entries
                ],
                "external_benchmark_submission_queue_count": int(
                    (
                        external_benchmark_asset_payloads.get("external_benchmark_submission_readiness", {})
                        .get("summary", {})
                        .get("submission_queue_count", 0)
                    )
                    or 0
                ),
                "external_benchmark_onepage_attestation_status": str(
                    (
                        external_benchmark_asset_payloads.get("external_benchmark_submission_readiness", {})
                        .get("summary", {})
                        .get("onepage_attestation_status", "")
                    )
                    or ""
                ),
            },
        }

        canonical = _canonical_bytes(registry_body)
        body_sha256 = hashlib.sha256(canonical).hexdigest()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            body_path = tmpdir_path / "registry_body.json"
            sig_bin = tmpdir_path / "registry_body.sig"
            body_path.write_bytes(canonical)
            _openssl(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    str(private_key),
                    "-in",
                    str(body_path),
                    "-out",
                    str(sig_bin),
                ]
            )
            _openssl(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-sigfile",
                    str(sig_bin),
                    "-in",
                    str(body_path),
                    "-rawin",
                ]
            )
            signature_bytes = sig_bin.read_bytes()

        signature_b64 = base64.b64encode(signature_bytes).decode("ascii")
        signature_out.parent.mkdir(parents=True, exist_ok=True)
        signature_out.write_text(signature_b64 + "\n", encoding="utf-8")

        checks = {
            "green_reports_pass": bool(green_reports_pass),
            "lock_manifest_hash_match": bool(
                str((repro.get("lock_manifest") or "")).strip() == str(lock_path)
                and str((lock_manifest.get("replay_digest") or "")).strip() != ""
            ),
            "artifact_hashes_present_pass": bool(len(artifact_entries) >= 6),
            "public_key_written_pass": bool(public_key.exists()),
            "signature_generated_pass": bool(len(signature_bytes) > 0),
            "signature_verified_pass": True,
        }
        contract_pass = bool(all(checks.values()))
        reason_code = "PASS" if contract_pass else "ERR_SIGNATURE"

        project_registry_payload: dict = {}
        project_registry_out = Path(str(args.project_registry_out).strip() or str(out.with_name("project_registry.json")))
        project_package_out = Path(str(args.project_package_out).strip() or str(out.with_name("project_package.zip")))
        project_signature_out = Path(
            str(args.project_signature_out).strip()
            or str(signature_out.with_name("project_registry.signature.b64"))
        )
        project_private_key = Path(str(args.project_private_key_out).strip() or str(private_key))
        project_public_key = Path(str(args.project_public_key_out).strip() or str(public_key))

        if contract_pass:
            project_artifact_entries = list(artifact_entries)
            project_artifact_entries.extend(
                [
                    _artifact_entry("release_registry_public_key", public_key, None),
                    _artifact_entry("release_registry_signature", signature_out, None),
                ]
            )
            project_registry_payload = build_project_registry(
                project_id="phase1-release",
                project_name="Phase1 Structural AI Release Package",
                artifact_paths=[Path(str(row["path"])) for row in project_artifact_entries],
                audit_payload=_project_registry_audit_payload(
                    artifact_entries=project_artifact_entries,
                    generated_at=generated_at,
                ),
                approval_payload=_project_registry_approval_payload(generated_at=generated_at),
                private_key_out=project_private_key,
                public_key_out=project_public_key,
                signature_out=project_signature_out,
                package_out=project_package_out,
                out=project_registry_out,
                generated_at=generated_at,
            )
            artifact_entries.extend(
                [
                    _artifact_entry("project_registry_report", project_registry_out, project_registry_payload),
                    _artifact_entry("project_package_zip", project_package_out, None),
                    _artifact_entry("project_registry_signature", project_signature_out, None),
                ]
            )
            project_registry_checks = (
                project_registry_payload.get("checks")
                if isinstance(project_registry_payload.get("checks"), dict)
                else {}
            )
            project_registry_summary = (
                project_registry_payload.get("summary")
                if isinstance(project_registry_payload.get("summary"), dict)
                else {}
            )
            checks["project_registry_package_pass"] = bool(project_registry_payload.get("contract_pass", False))
            checks["project_registry_signature_verified_pass"] = bool(
                project_registry_checks.get("signature_verified_pass", False)
            )
            contract_pass = bool(all(checks.values()))
            reason_code = "PASS" if contract_pass else "ERR_SIGNATURE"
        else:
            project_registry_summary = {}

        report = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-signed-release-registry",
            "generated_at": generated_at,
            "inputs": {
                "repro_report": str(repro_path),
                "lock_manifest": str(lock_path),
                "kds_summary": str(kds_path),
                "midas_conversion": str(midas_path),
                "solver_hip_e2e": str(solver_path),
                "committee_package": str(committee_path) if committee_path is not None else "",
                "committee_summary": str(committee_summary_path) if committee_summary_path is not None else "",
                "gap_report": str(gap_report_path) if gap_report_path is not None else "",
                "external_benchmark_artifacts": {
                    label: str(path) if path is not None else "" for label, path in external_artifact_paths
                },
                "ci_report": str(ci_path) if ci_path is not None else "",
                "parser_script": str(parser_script),
                "public_key_out": str(public_key),
                "signature_out": str(signature_out),
                "project_private_key_out": str(project_private_key),
                "project_public_key_out": str(project_public_key),
                "project_signature_out": str(project_signature_out),
                "project_package_out": str(project_package_out),
                "project_registry_out": str(project_registry_out),
                "out": str(out),
            },
            "checks": checks,
            "summary": {
                "artifact_count": int(len(artifact_entries)),
                "model_hash_count": int(len(lock_manifest.get("model_hashes") or {})),
                "input_hash_count": int(len(lock_manifest.get("input_hashes") or {})),
                "key_generated_this_run": bool(key_generated),
                "signing_algorithm": "ed25519",
                "registry_body_sha256": body_sha256,
                "deployment_model": str(gap_context.get("deployment_model", "")),
                "measured_chain_rolling_selection_mode": str(gap_context.get("measured_chain_rolling_selection_mode", "")),
                "measured_chain_comparable_reference_deployment_model": str(
                    gap_context.get("measured_chain_comparable_reference_deployment_model", "")
                ),
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(
                    gap_context.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)
                ),
                "authority_catalog_diff_change_count": int(committee_summary.get("authority_catalog_diff_change_count", 0)),
                "authority_catalog_routing_warning_active": bool(
                    committee_summary.get("authority_catalog_routing_warning_active", False)
                ),
                "project_registry_artifact_count": int(project_registry_summary.get("artifact_count", 0) or 0),
                "project_registry_approval_count": int(project_registry_summary.get("approval_count", 0) or 0),
                "project_registry_package_sha256": str(project_registry_summary.get("package_sha256", "") or ""),
                "project_registry_package_bytes": int(project_registry_summary.get("package_bytes", 0) or 0),
                "external_benchmark_release_asset_count": int(len(external_benchmark_asset_entries)),
                "external_benchmark_release_asset_labels": [
                    str(row.get("label", "") or "") for row in external_benchmark_asset_entries
                ],
                "external_benchmark_submission_queue_count": int(
                    (
                        external_benchmark_asset_payloads.get("external_benchmark_submission_readiness", {})
                        .get("summary", {})
                        .get("submission_queue_count", 0)
                    )
                    or 0
                ),
                "external_benchmark_onepage_attestation_status": str(
                    (
                        external_benchmark_asset_payloads.get("external_benchmark_submission_readiness", {})
                        .get("summary", {})
                        .get("onepage_attestation_status", "")
                    )
                    or ""
                ),
                **external_benchmark_execution_provenance,
                **mgt_export_provenance,
                **advanced_holdout_provenance,
                "advanced_holdout_total_count": int(
                    advanced_holdout_closure_surface.get("advanced_holdout_total_count", 0) or 0
                ),
                "advanced_holdout_closed_count": int(
                    advanced_holdout_closure_surface.get("advanced_holdout_closed_count", 0) or 0
                ),
                "advanced_holdout_open_count": int(
                    advanced_holdout_closure_surface.get("advanced_holdout_open_count", 0) or 0
                ),
                "advanced_holdout_closure_summary_line": str(
                    advanced_holdout_closure_surface.get("advanced_holdout_closure_summary_line", "") or ""
                ),
            },
            "registry_body": registry_body,
            "signature": {
                "algorithm": "ed25519",
                "public_key_path": str(public_key),
                "signature_b64": signature_b64,
                "signature_out": str(signature_out),
                "canonical_body_sha256": body_sha256,
            },
            "artifacts": {
                "project_registry_report": str(project_registry_out),
                "project_package_zip": str(project_package_out),
                "project_registry_signature": str(project_signature_out),
            },
            "project_registry_report": project_registry_payload,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote signed release registry: {out}")
        if not contract_pass:
            raise SystemExit(1)
    except FileNotFoundError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-signed-release-registry",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INPUT",
            "reason": f"{REASONS['ERR_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote signed release registry: {out}")
        raise SystemExit(1)
    except RuntimeError as exc:
        code = "ERR_SIGNATURE"
        if str(exc) == "ERR_SOURCE_GATE":
            code = "ERR_SOURCE_GATE"
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-signed-release-registry",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": code,
            "reason": REASONS[code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote signed release registry: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
