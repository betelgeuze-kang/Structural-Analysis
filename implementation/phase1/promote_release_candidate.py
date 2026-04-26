#!/usr/bin/env python3
"""Promote latest nightly snapshot to release-candidate on dual-green policy.

Policy:
- latest nightly snapshot exists
- nightly ci/pipeline/static reports are green
- current PR ci report is green
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from implementation.phase1.pdf_rendering import configure_matplotlib_cjk_pdf, finalize_pdf_figure


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_green(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path}"
    data = _load_json(path)
    if "all_pass" in data:
        ok = bool(data.get("all_pass", False))
    elif "contract_pass" in data:
        ok = bool(data.get("contract_pass", False))
    elif "pass" in data:
        ok = bool(data.get("pass", False))
    else:
        ok = False
    reason = str(data.get("reason_code", "UNKNOWN"))
    return ok, reason


def _registry_accelerated_coverage_summary(snapshot_dir: Path) -> dict:
    registry_path = snapshot_dir / "release" / "release_registry.json"
    if not registry_path.exists():
        return {
            "deployment_model": "",
            "measured_chain_rolling_selection_mode": "",
            "measured_chain_comparable_reference_deployment_model": "",
            "measured_chain_comparable_reference_strict_design_opt_cost_smoke": False,
            "authority_catalog_diff_change_count": 0,
            "authority_catalog_routing_warning_active": False,
            "pbd_resolved_ndtha_report": "",
            "pbd_resolved_ndtha_response_npz": "",
            "pbd_ndtha_response_fallback_used": False,
            "pbd_ndtha_response_coverage_count": 0,
            "pbd_hinge_benchmark_gate_pass": False,
            "pbd_hinge_benchmark_fixture_regression_pass": False,
            "pbd_hinge_benchmark_alignment_pass": False,
            "pbd_hinge_benchmark_asset_count": 0,
            "pbd_hinge_benchmark_train_count": 0,
            "pbd_hinge_benchmark_val_count": 0,
            "pbd_hinge_benchmark_holdout_count": 0,
            "pbd_hinge_benchmark_rebar_sensitive_count": 0,
            "pbd_hinge_benchmark_confinement_sensitive_count": 0,
            "pbd_hinge_benchmark_fixture_count": 0,
            "pbd_hinge_benchmark_fixture_min_point_count": 0,
            "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": 0.0,
            "pbd_hinge_benchmark_alignment_refresh_column_row_count": 0,
            "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": 0,
            "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": 0.0,
            "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": 0.0,
            "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": 0.0,
            "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": 0.0,
        }
    registry = _load_json(registry_path)
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    body = registry.get("registry_body") if isinstance(registry.get("registry_body"), dict) else {}
    accel = body.get("accelerated_coverage_provenance") if isinstance(body.get("accelerated_coverage_provenance"), dict) else {}
    direct_patch_label = str(
        summary.get("mgt_export_direct_patch_action_family_label")
        or accel.get("mgt_export_direct_patch_action_family_label")
        or ""
    )
    sidecar_label = str(
        summary.get("mgt_export_instruction_sidecar_action_family_label")
        or accel.get("mgt_export_instruction_sidecar_action_family_label")
        or ""
    )
    delivery_boundary = str(
        summary.get("mgt_export_delivery_boundary")
        or accel.get("mgt_export_delivery_boundary")
        or (
            f"direct_patch={direct_patch_label or 'n/a'} | "
            f"sidecar={sidecar_label or 'n/a'} | "
            f"connection_payload={str(summary.get('mgt_export_connection_detailing_delivery_mode') or accel.get('mgt_export_connection_detailing_delivery_mode') or 'n/a')} | "
            f"detailing_payload={str(summary.get('mgt_export_detailing_delivery_mode') or accel.get('mgt_export_detailing_delivery_mode') or 'n/a')}"
            if direct_patch_label or sidecar_label
            else ""
        )
    )
    panel_zone_validation_boundary = str(
        summary.get("panel_zone_validation_boundary") or accel.get("panel_zone_validation_boundary") or ""
    )
    panel_zone_validation_advisory_only = bool(
        summary.get("panel_zone_validation_advisory_only")
        if "panel_zone_validation_advisory_only" in summary
        else accel.get("panel_zone_validation_advisory_only", panel_zone_validation_boundary == "external_validation_only")
    )
    panel_zone_validation_advisory_label = str(
        summary.get("panel_zone_validation_advisory_label")
        or accel.get("panel_zone_validation_advisory_label")
        or ("panel_zone_external_validation_only_boundary" if panel_zone_validation_advisory_only else "none")
    )

    return {
        "deployment_model": str(summary.get("deployment_model") or accel.get("deployment_model") or ""),
        "measured_chain_rolling_selection_mode": str(
            summary.get("measured_chain_rolling_selection_mode")
            or accel.get("measured_chain_rolling_selection_mode")
            or ""
        ),
        "measured_chain_comparable_reference_deployment_model": str(
            summary.get("measured_chain_comparable_reference_deployment_model")
            or accel.get("comparable_reference_deployment_model")
            or ""
        ),
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(
            summary.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke")
            if "measured_chain_comparable_reference_strict_design_opt_cost_smoke" in summary
            else accel.get("comparable_reference_strict_design_opt_cost_smoke", False)
        ),
        "authority_catalog_diff_change_count": int(
            summary.get("authority_catalog_diff_change_count")
            if "authority_catalog_diff_change_count" in summary
            else accel.get("authority_catalog_diff_change_count", 0)
        ),
        "authority_catalog_routing_warning_active": bool(
            summary.get("authority_catalog_routing_warning_active")
            if "authority_catalog_routing_warning_active" in summary
            else accel.get("authority_catalog_routing_warning_active", False)
        ),
        "mgt_export_support_mode": str(summary.get("mgt_export_support_mode") or accel.get("mgt_export_support_mode") or ""),
        "mgt_export_direct_patch_change_count": int(
            summary.get("mgt_export_direct_patch_change_count")
            if "mgt_export_direct_patch_change_count" in summary
            else accel.get("mgt_export_direct_patch_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_change_count": int(
            summary.get("mgt_export_instruction_sidecar_change_count")
            if "mgt_export_instruction_sidecar_change_count" in summary
            else accel.get("mgt_export_instruction_sidecar_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_action_family_label": str(
            summary.get("mgt_export_instruction_sidecar_action_family_label")
            or accel.get("mgt_export_instruction_sidecar_action_family_label")
            or ""
        ),
        "mgt_export_instruction_sidecar_audit_only_change_count": int(
            summary.get("mgt_export_instruction_sidecar_audit_only_change_count")
            if "mgt_export_instruction_sidecar_audit_only_change_count" in summary
            else accel.get("mgt_export_instruction_sidecar_audit_only_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_audit_only_action_family_label": str(
            summary.get("mgt_export_instruction_sidecar_audit_only_action_family_label")
            or accel.get("mgt_export_instruction_sidecar_audit_only_action_family_label")
            or ""
        ),
        "mgt_export_instruction_sidecar_manual_input_change_count": int(
            summary.get("mgt_export_instruction_sidecar_manual_input_change_count")
            if "mgt_export_instruction_sidecar_manual_input_change_count" in summary
            else accel.get("mgt_export_instruction_sidecar_manual_input_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_manual_input_action_family_label": str(
            summary.get("mgt_export_instruction_sidecar_manual_input_action_family_label")
            or accel.get("mgt_export_instruction_sidecar_manual_input_action_family_label")
            or ""
        ),
        "mgt_export_audit_review_manifest_change_count": int(
            summary.get("mgt_export_audit_review_manifest_change_count")
            if "mgt_export_audit_review_manifest_change_count" in summary
            else accel.get("mgt_export_audit_review_manifest_change_count", 0)
        ),
        "mgt_export_audit_review_manifest_action_family_label": str(
            summary.get("mgt_export_audit_review_manifest_action_family_label")
            or accel.get("mgt_export_audit_review_manifest_action_family_label")
            or ""
        ),
        "mgt_export_audit_review_packet_count": int(
            summary.get("mgt_export_audit_review_packet_count")
            if "mgt_export_audit_review_packet_count" in summary
            else accel.get("mgt_export_audit_review_packet_count", 0)
        ),
        "mgt_export_audit_review_packet_action_family_label": str(
            summary.get("mgt_export_audit_review_packet_action_family_label")
            or accel.get("mgt_export_audit_review_packet_action_family_label")
            or ""
        ),
        "mgt_export_audit_review_packet_followup_type_label": str(
            summary.get("mgt_export_audit_review_packet_followup_type_label")
            or accel.get("mgt_export_audit_review_packet_followup_type_label")
            or ""
        ),
        "mgt_export_audit_review_packet_file_count": int(
            summary.get("mgt_export_audit_review_packet_file_count")
            if "mgt_export_audit_review_packet_file_count" in summary
            else accel.get("mgt_export_audit_review_packet_file_count", 0)
            or 0
        ),
        "mgt_export_audit_review_packet_file_action_family_label": str(
            summary.get("mgt_export_audit_review_packet_file_action_family_label")
            or accel.get("mgt_export_audit_review_packet_file_action_family_label")
            or ""
        ),
        "mgt_export_audit_review_queue_item_count": int(
            summary.get("mgt_export_audit_review_queue_item_count")
            if "mgt_export_audit_review_queue_item_count" in summary
            else accel.get("mgt_export_audit_review_queue_item_count", 0)
            or 0
        ),
        "mgt_export_audit_review_queue_pending_count": int(
            summary.get("mgt_export_audit_review_queue_pending_count")
            if "mgt_export_audit_review_queue_pending_count" in summary
            else accel.get("mgt_export_audit_review_queue_pending_count", 0)
            or 0
        ),
        "mgt_export_audit_review_queue_acknowledged_count": int(
            summary.get("mgt_export_audit_review_queue_acknowledged_count")
            if "mgt_export_audit_review_queue_acknowledged_count" in summary
            else accel.get("mgt_export_audit_review_queue_acknowledged_count", 0)
            or 0
        ),
        "mgt_export_audit_review_queue_status_label": str(
            summary.get("mgt_export_audit_review_queue_status_label")
            or accel.get("mgt_export_audit_review_queue_status_label")
            or ""
        ),
        "mgt_export_audit_review_queue_action_family_label": str(
            summary.get("mgt_export_audit_review_queue_action_family_label")
            or accel.get("mgt_export_audit_review_queue_action_family_label")
            or ""
        ),
        "mgt_export_audit_review_followup_item_count": int(
            summary.get("mgt_export_audit_review_followup_item_count")
            if "mgt_export_audit_review_followup_item_count" in summary
            else accel.get("mgt_export_audit_review_followup_item_count", 0)
            or 0
        ),
        "mgt_export_audit_review_followup_open_item_count": int(
            summary.get("mgt_export_audit_review_followup_open_item_count")
            if "mgt_export_audit_review_followup_open_item_count" in summary
            else accel.get("mgt_export_audit_review_followup_open_item_count", 0)
            or 0
        ),
        "mgt_export_audit_review_followup_closed_item_count": int(
            summary.get("mgt_export_audit_review_followup_closed_item_count")
            if "mgt_export_audit_review_followup_closed_item_count" in summary
            else accel.get("mgt_export_audit_review_followup_closed_item_count", 0)
            or 0
        ),
        "mgt_export_audit_review_followup_action_label": str(
            summary.get("mgt_export_audit_review_followup_action_label")
            or accel.get("mgt_export_audit_review_followup_action_label")
            or ""
        ),
        "mgt_export_audit_review_followup_owner_label": str(
            summary.get("mgt_export_audit_review_followup_owner_label")
            or accel.get("mgt_export_audit_review_followup_owner_label")
            or ""
        ),
        "mgt_export_audit_review_followup_review_owner_label": str(
            summary.get("mgt_export_audit_review_followup_review_owner_label")
            or accel.get("mgt_export_audit_review_followup_review_owner_label")
            or ""
        ),
        "mgt_export_audit_review_followup_status_label": str(
            summary.get("mgt_export_audit_review_followup_status_label")
            or accel.get("mgt_export_audit_review_followup_status_label")
            or ""
        ),
        "mgt_export_audit_review_followup_sla_state_label": str(
            summary.get("mgt_export_audit_review_followup_sla_state_label")
            or accel.get("mgt_export_audit_review_followup_sla_state_label")
            or ""
        ),
        "mgt_export_audit_review_followup_age_bucket_label": str(
            summary.get("mgt_export_audit_review_followup_age_bucket_label")
            or accel.get("mgt_export_audit_review_followup_age_bucket_label")
            or ""
        ),
        "mgt_export_audit_review_followup_overdue_item_count": int(
            summary.get("mgt_export_audit_review_followup_overdue_item_count")
            if "mgt_export_audit_review_followup_overdue_item_count" in summary
            else accel.get("mgt_export_audit_review_followup_overdue_item_count", 0)
            or 0
        ),
        "mgt_export_audit_review_followup_mode": str(
            summary.get("mgt_export_audit_review_followup_mode")
            or accel.get("mgt_export_audit_review_followup_mode")
            or ""
        ),
        "mgt_export_audit_review_resolution_item_count": int(
            summary.get("mgt_export_audit_review_resolution_item_count")
            if "mgt_export_audit_review_resolution_item_count" in summary
            else accel.get("mgt_export_audit_review_resolution_item_count", 0)
            or 0
        ),
        "mgt_export_audit_review_resolution_action_label": str(
            summary.get("mgt_export_audit_review_resolution_action_label")
            or accel.get("mgt_export_audit_review_resolution_action_label")
            or ""
        ),
        "mgt_export_audit_review_resolution_owner_label": str(
            summary.get("mgt_export_audit_review_resolution_owner_label")
            or accel.get("mgt_export_audit_review_resolution_owner_label")
            or ""
        ),
        "mgt_export_audit_review_resolution_status_label": str(
            summary.get("mgt_export_audit_review_resolution_status_label")
            or accel.get("mgt_export_audit_review_resolution_status_label")
            or ""
        ),
        "mgt_export_audit_review_resolution_mode": str(
            summary.get("mgt_export_audit_review_resolution_mode")
            or accel.get("mgt_export_audit_review_resolution_mode")
            or ""
        ),
        "audit_review_decision_batch_template_item_count": int(
            summary.get("audit_review_decision_batch_template_item_count")
            if "audit_review_decision_batch_template_item_count" in summary
            else accel.get("audit_review_decision_batch_template_item_count", 0)
            or 0
        ),
        "audit_review_decision_batch_template_current_status_label": str(
            summary.get("audit_review_decision_batch_template_current_status_label")
            or accel.get("audit_review_decision_batch_template_current_status_label")
            or ""
        ),
        "audit_review_decision_batch_template_review_owner_label": str(
            summary.get("audit_review_decision_batch_template_review_owner_label")
            or accel.get("audit_review_decision_batch_template_review_owner_label")
            or ""
        ),
        "audit_review_decision_batch_template_review_priority_label": str(
            summary.get("audit_review_decision_batch_template_review_priority_label")
            or accel.get("audit_review_decision_batch_template_review_priority_label")
            or ""
        ),
        "audit_review_decision_batch_attested_example_count": int(
            summary.get("audit_review_decision_batch_attested_example_count")
            if "audit_review_decision_batch_attested_example_count" in summary
            else accel.get("audit_review_decision_batch_attested_example_count", 0)
            or 0
        ),
        "audit_review_decision_batch_attested_example_preview_label": str(
            summary.get("audit_review_decision_batch_attested_example_preview_label")
            or accel.get("audit_review_decision_batch_attested_example_preview_label")
            or ""
        ),
        "external_benchmark_submission_preview_approve_all_reason_code": str(
            summary.get("external_benchmark_submission_preview_approve_all_reason_code")
            or accel.get("external_benchmark_submission_preview_approve_all_reason_code")
            or ""
        ),
        "external_benchmark_submission_preview_approve_all_ready_full": bool(
            summary.get("external_benchmark_submission_preview_approve_all_ready_full")
            if "external_benchmark_submission_preview_approve_all_ready_full" in summary
            else accel.get("external_benchmark_submission_preview_approve_all_ready_full", False)
        ),
        "external_benchmark_submission_preview_approve_all_pending_count": int(
            summary.get("external_benchmark_submission_preview_approve_all_pending_count")
            if "external_benchmark_submission_preview_approve_all_pending_count" in summary
            else accel.get("external_benchmark_submission_preview_approve_all_pending_count", 0)
            or 0
        ),
        "external_benchmark_submission_preview_approve_all_open_revision_count": int(
            summary.get("external_benchmark_submission_preview_approve_all_open_revision_count")
            if "external_benchmark_submission_preview_approve_all_open_revision_count" in summary
            else accel.get("external_benchmark_submission_preview_approve_all_open_revision_count", 0)
            or 0
        ),
        "external_benchmark_submission_preview_reject_one_reason_code": str(
            summary.get("external_benchmark_submission_preview_reject_one_reason_code")
            or accel.get("external_benchmark_submission_preview_reject_one_reason_code")
            or ""
        ),
        "external_benchmark_submission_preview_reject_one_ready_full": bool(
            summary.get("external_benchmark_submission_preview_reject_one_ready_full")
            if "external_benchmark_submission_preview_reject_one_ready_full" in summary
            else accel.get("external_benchmark_submission_preview_reject_one_ready_full", False)
        ),
        "external_benchmark_submission_preview_reject_one_pending_count": int(
            summary.get("external_benchmark_submission_preview_reject_one_pending_count")
            if "external_benchmark_submission_preview_reject_one_pending_count" in summary
            else accel.get("external_benchmark_submission_preview_reject_one_pending_count", 0)
            or 0
        ),
        "external_benchmark_submission_preview_reject_one_open_revision_count": int(
            summary.get("external_benchmark_submission_preview_reject_one_open_revision_count")
            if "external_benchmark_submission_preview_reject_one_open_revision_count" in summary
            else accel.get("external_benchmark_submission_preview_reject_one_open_revision_count", 0)
            or 0
        ),
        "external_benchmark_submission_preview_reject_one_blocker_label": str(
            summary.get("external_benchmark_submission_preview_reject_one_blocker_label")
            or accel.get("external_benchmark_submission_preview_reject_one_blocker_label")
            or ""
        ),
        "audit_review_decision_batch_runner_reason_code": str(
            summary.get("audit_review_decision_batch_runner_reason_code")
            or accel.get("audit_review_decision_batch_runner_reason_code")
            or ""
        ),
        "audit_review_decision_batch_runner_apply_live": bool(
            summary.get("audit_review_decision_batch_runner_apply_live")
            if "audit_review_decision_batch_runner_apply_live" in summary
            else accel.get("audit_review_decision_batch_runner_apply_live", False)
        ),
        "audit_review_decision_batch_runner_live_applied": bool(
            summary.get("audit_review_decision_batch_runner_live_applied")
            if "audit_review_decision_batch_runner_live_applied" in summary
            else accel.get("audit_review_decision_batch_runner_live_applied", False)
        ),
        "audit_review_decision_batch_runner_preview_reason_code": str(
            summary.get("audit_review_decision_batch_runner_preview_reason_code")
            or accel.get("audit_review_decision_batch_runner_preview_reason_code")
            or ""
        ),
        "audit_review_decision_batch_runner_preview_ready_full": bool(
            summary.get("audit_review_decision_batch_runner_preview_ready_full")
            if "audit_review_decision_batch_runner_preview_ready_full" in summary
            else accel.get("audit_review_decision_batch_runner_preview_ready_full", False)
        ),
        "audit_review_decision_batch_runner_preview_pending_count": int(
            summary.get("audit_review_decision_batch_runner_preview_pending_count")
            if "audit_review_decision_batch_runner_preview_pending_count" in summary
            else accel.get("audit_review_decision_batch_runner_preview_pending_count", 0)
            or 0
        ),
        "audit_review_decision_batch_runner_preview_open_revision_count": int(
            summary.get("audit_review_decision_batch_runner_preview_open_revision_count")
            if "audit_review_decision_batch_runner_preview_open_revision_count" in summary
            else accel.get("audit_review_decision_batch_runner_preview_open_revision_count", 0)
            or 0
        ),
        "audit_review_decision_batch_runner_live_preview_reason_code": str(
            summary.get("audit_review_decision_batch_runner_live_preview_reason_code")
            or accel.get("audit_review_decision_batch_runner_live_preview_reason_code")
            or ""
        ),
        "mgt_export_rebar_payload_namespace_mode": str(
            summary.get("mgt_export_rebar_payload_namespace_mode")
            or accel.get("mgt_export_rebar_payload_namespace_mode")
            or ""
        ),
        "mgt_export_rebar_payload_material_level_namespace_present": bool(
            summary.get("mgt_export_rebar_payload_material_level_namespace_present")
            if "mgt_export_rebar_payload_material_level_namespace_present" in summary
            else accel.get("mgt_export_rebar_payload_material_level_namespace_present", False)
        ),
        "mgt_export_rebar_payload_group_local_namespace_present": bool(
            summary.get("mgt_export_rebar_payload_group_local_namespace_present")
            if "mgt_export_rebar_payload_group_local_namespace_present" in summary
            else accel.get("mgt_export_rebar_payload_group_local_namespace_present", False)
        ),
        "mgt_export_group_local_rebar_payload_row_count": int(
            summary.get("mgt_export_group_local_rebar_payload_row_count")
            if "mgt_export_group_local_rebar_payload_row_count" in summary
            else accel.get("mgt_export_group_local_rebar_payload_row_count", 0)
        ),
        "mgt_export_group_local_rebar_payload_available_count": int(
            summary.get("mgt_export_group_local_rebar_payload_available_count")
            if "mgt_export_group_local_rebar_payload_available_count" in summary
            else accel.get("mgt_export_group_local_rebar_payload_available_count", 0)
        ),
        "mgt_export_group_local_connection_detailing_payload_row_count": int(
            summary.get("mgt_export_group_local_connection_detailing_payload_row_count")
            if "mgt_export_group_local_connection_detailing_payload_row_count" in summary
            else accel.get("mgt_export_group_local_connection_detailing_payload_row_count", 0)
        ),
        "mgt_export_group_local_connection_detailing_payload_available_count": int(
            summary.get("mgt_export_group_local_connection_detailing_payload_available_count")
            if "mgt_export_group_local_connection_detailing_payload_available_count" in summary
            else accel.get("mgt_export_group_local_connection_detailing_payload_available_count", 0)
        ),
        "mgt_export_group_local_detailing_payload_row_count": int(
            summary.get("mgt_export_group_local_detailing_payload_row_count")
            if "mgt_export_group_local_detailing_payload_row_count" in summary
            else accel.get("mgt_export_group_local_detailing_payload_row_count", 0)
        ),
        "mgt_export_group_local_detailing_payload_available_count": int(
            summary.get("mgt_export_group_local_detailing_payload_available_count")
            if "mgt_export_group_local_detailing_payload_available_count" in summary
            else accel.get("mgt_export_group_local_detailing_payload_available_count", 0)
        ),
        "mgt_export_connection_detailing_payload_namespace_mode": str(
            summary.get("mgt_export_connection_detailing_payload_namespace_mode")
            or accel.get("mgt_export_connection_detailing_payload_namespace_mode")
            or ""
        ),
        "mgt_export_connection_detailing_payload_group_local_namespace_present": bool(
            summary.get("mgt_export_connection_detailing_payload_group_local_namespace_present")
            if "mgt_export_connection_detailing_payload_group_local_namespace_present" in summary
            else accel.get("mgt_export_connection_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_detailing_payload_namespace_mode": str(
            summary.get("mgt_export_detailing_payload_namespace_mode")
            or accel.get("mgt_export_detailing_payload_namespace_mode")
            or ""
        ),
        "mgt_export_detailing_payload_group_local_namespace_present": bool(
            summary.get("mgt_export_detailing_payload_group_local_namespace_present")
            if "mgt_export_detailing_payload_group_local_namespace_present" in summary
            else accel.get("mgt_export_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": int(
            summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count")
            if "mgt_export_connection_detailing_structured_payload_mapped_change_count" in summary
            else accel.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0)
        ),
        "mgt_export_connection_detailing_direct_patch_eligible_change_count": int(
            summary.get("mgt_export_connection_detailing_direct_patch_eligible_change_count")
            if "mgt_export_connection_detailing_direct_patch_eligible_change_count" in summary
            else accel.get("mgt_export_connection_detailing_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_detailing_structured_payload_mapped_change_count": int(
            summary.get("mgt_export_detailing_structured_payload_mapped_change_count")
            if "mgt_export_detailing_structured_payload_mapped_change_count" in summary
            else accel.get("mgt_export_detailing_structured_payload_mapped_change_count", 0)
        ),
        "mgt_export_detailing_direct_patch_eligible_change_count": int(
            summary.get("mgt_export_detailing_direct_patch_eligible_change_count")
            if "mgt_export_detailing_direct_patch_eligible_change_count" in summary
            else accel.get("mgt_export_detailing_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_connection_detailing_delivery_mode": str(
            summary.get("mgt_export_connection_detailing_delivery_mode")
            or accel.get("mgt_export_connection_detailing_delivery_mode")
            or ""
        ),
        "mgt_export_detailing_delivery_mode": str(
            summary.get("mgt_export_detailing_delivery_mode")
            or accel.get("mgt_export_detailing_delivery_mode")
            or ""
        ),
        "mgt_export_rebar_direct_patch_eligible_change_count": int(
            summary.get("mgt_export_rebar_direct_patch_eligible_change_count")
            if "mgt_export_rebar_direct_patch_eligible_change_count" in summary
            else accel.get("mgt_export_rebar_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_patched_material_row_count": int(
            summary.get("mgt_export_patched_material_row_count")
            if "mgt_export_patched_material_row_count" in summary
            else accel.get("mgt_export_patched_material_row_count", 0)
        ),
        "mgt_export_cloned_material_count": int(
            summary.get("mgt_export_cloned_material_count")
            if "mgt_export_cloned_material_count" in summary
            else accel.get("mgt_export_cloned_material_count", 0)
        ),
        "mgt_export_rebar_direct_patch_ineligible_reason_label": str(
            summary.get("mgt_export_rebar_direct_patch_ineligible_reason_label")
            or accel.get("mgt_export_rebar_direct_patch_ineligible_reason_label")
            or ""
        ),
        "mgt_export_rebar_direct_patch_mapping_source_label": str(
            summary.get("mgt_export_rebar_direct_patch_mapping_source_label")
            or accel.get("mgt_export_rebar_direct_patch_mapping_source_label")
            or ""
        ),
        "mgt_export_rebar_delivery_mode": str(
            summary.get("mgt_export_rebar_delivery_mode")
            or accel.get("mgt_export_rebar_delivery_mode")
            or ""
        ),
        "mgt_export_delivery_boundary": delivery_boundary,
        "mgt_export_evidence_model": str(
            summary.get("mgt_export_evidence_model")
            or accel.get("mgt_export_evidence_model")
            or ""
        ),
        "pbd_dynamic_hinge_refresh_ready": bool(
            summary.get("pbd_dynamic_hinge_refresh_ready")
            if "pbd_dynamic_hinge_refresh_ready" in summary
            else accel.get("pbd_dynamic_hinge_refresh_ready", False)
        ),
        "pbd_hinge_state_mode": str(summary.get("pbd_hinge_state_mode") or accel.get("pbd_hinge_state_mode") or ""),
        "pbd_hinge_refresh_reason": str(summary.get("pbd_hinge_refresh_reason") or accel.get("pbd_hinge_refresh_reason") or ""),
        "pbd_hinge_refresh_artifact_present": bool(
            summary.get("pbd_hinge_refresh_artifact_present")
            if "pbd_hinge_refresh_artifact_present" in summary
            else accel.get("pbd_hinge_refresh_artifact_present", False)
        ),
        "pbd_hinge_refresh_artifact_kind": str(
            summary.get("pbd_hinge_refresh_artifact_kind") or accel.get("pbd_hinge_refresh_artifact_kind") or ""
        ),
        "pbd_hinge_refresh_source_mode": str(
            summary.get("pbd_hinge_refresh_source_mode") or accel.get("pbd_hinge_refresh_source_mode") or ""
        ),
        "pbd_hinge_refresh_overlap_member_count": int(
            summary.get("pbd_hinge_refresh_overlap_member_count")
            if "pbd_hinge_refresh_overlap_member_count" in summary
            else accel.get("pbd_hinge_refresh_overlap_member_count", 0)
        ),
        "pbd_hinge_refresh_rebar_sensitive_member_count": int(
            summary.get("pbd_hinge_refresh_rebar_sensitive_member_count")
            if "pbd_hinge_refresh_rebar_sensitive_member_count" in summary
            else accel.get("pbd_hinge_refresh_rebar_sensitive_member_count", 0)
        ),
        "pbd_hinge_benchmark_gate_pass": bool(
            summary.get("pbd_hinge_benchmark_gate_pass")
            if "pbd_hinge_benchmark_gate_pass" in summary
            else accel.get("pbd_hinge_benchmark_gate_pass", False)
        ),
        "pbd_hinge_benchmark_fixture_regression_pass": bool(
            summary.get("pbd_hinge_benchmark_fixture_regression_pass")
            if "pbd_hinge_benchmark_fixture_regression_pass" in summary
            else accel.get("pbd_hinge_benchmark_fixture_regression_pass", False)
        ),
        "pbd_hinge_benchmark_alignment_pass": bool(
            summary.get("pbd_hinge_benchmark_alignment_pass")
            if "pbd_hinge_benchmark_alignment_pass" in summary
            else accel.get("pbd_hinge_benchmark_alignment_pass", False)
        ),
        "pbd_hinge_benchmark_asset_count": int(
            summary.get("pbd_hinge_benchmark_asset_count")
            if "pbd_hinge_benchmark_asset_count" in summary
            else accel.get("pbd_hinge_benchmark_asset_count", 0)
        ),
        "pbd_hinge_benchmark_train_count": int(
            summary.get("pbd_hinge_benchmark_train_count")
            if "pbd_hinge_benchmark_train_count" in summary
            else accel.get("pbd_hinge_benchmark_train_count", 0)
        ),
        "pbd_hinge_benchmark_val_count": int(
            summary.get("pbd_hinge_benchmark_val_count")
            if "pbd_hinge_benchmark_val_count" in summary
            else accel.get("pbd_hinge_benchmark_val_count", 0)
        ),
        "pbd_hinge_benchmark_holdout_count": int(
            summary.get("pbd_hinge_benchmark_holdout_count")
            if "pbd_hinge_benchmark_holdout_count" in summary
            else accel.get("pbd_hinge_benchmark_holdout_count", 0)
        ),
        "pbd_hinge_benchmark_rebar_sensitive_count": int(
            summary.get("pbd_hinge_benchmark_rebar_sensitive_count")
            if "pbd_hinge_benchmark_rebar_sensitive_count" in summary
            else accel.get("pbd_hinge_benchmark_rebar_sensitive_count", 0)
        ),
        "pbd_hinge_benchmark_confinement_sensitive_count": int(
            summary.get("pbd_hinge_benchmark_confinement_sensitive_count")
            if "pbd_hinge_benchmark_confinement_sensitive_count" in summary
            else accel.get("pbd_hinge_benchmark_confinement_sensitive_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_count": int(
            summary.get("pbd_hinge_benchmark_fixture_count")
            if "pbd_hinge_benchmark_fixture_count" in summary
            else accel.get("pbd_hinge_benchmark_fixture_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_min_point_count": int(
            summary.get("pbd_hinge_benchmark_fixture_min_point_count")
            if "pbd_hinge_benchmark_fixture_min_point_count" in summary
            else accel.get("pbd_hinge_benchmark_fixture_min_point_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": float(
            summary.get("pbd_hinge_benchmark_fixture_min_peak_drift_ratio")
            if "pbd_hinge_benchmark_fixture_min_peak_drift_ratio" in summary
            else accel.get("pbd_hinge_benchmark_fixture_min_peak_drift_ratio", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": int(
            summary.get("pbd_hinge_benchmark_alignment_refresh_column_row_count")
            if "pbd_hinge_benchmark_alignment_refresh_column_row_count" in summary
            else accel.get("pbd_hinge_benchmark_alignment_refresh_column_row_count", 0)
        ),
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": int(
            summary.get("pbd_hinge_benchmark_alignment_rebar_sensitive_column_count")
            if "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count" in summary
            else accel.get("pbd_hinge_benchmark_alignment_rebar_sensitive_column_count", 0)
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
            summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min")
            if "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min" in summary
            else accel.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
            summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max")
            if "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max" in summary
            else accel.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
            summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min")
            if "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min" in summary
            else accel.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
            summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max")
            if "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max" in summary
            else accel.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max", 0.0)
        ),
        "pbd_resolved_ndtha_report": str(
            summary.get("pbd_resolved_ndtha_report") or accel.get("pbd_resolved_ndtha_report") or ""
        ),
        "pbd_resolved_ndtha_response_npz": str(
            summary.get("pbd_resolved_ndtha_response_npz")
            or accel.get("pbd_resolved_ndtha_response_npz")
            or ""
        ),
        "pbd_ndtha_response_fallback_used": bool(
            summary.get("pbd_ndtha_response_fallback_used")
            if "pbd_ndtha_response_fallback_used" in summary
            else accel.get("pbd_ndtha_response_fallback_used", False)
        ),
        "pbd_ndtha_response_coverage_count": int(
            summary.get("pbd_ndtha_response_coverage_count")
            if "pbd_ndtha_response_coverage_count" in summary
            else accel.get("pbd_ndtha_response_coverage_count", 0)
        ),
        "pbd_response_source_label": str(
            summary.get("pbd_response_source_label")
            or accel.get("pbd_response_source_label")
            or (
                f"resolved_report={str(summary.get('pbd_resolved_ndtha_report') or accel.get('pbd_resolved_ndtha_report') or 'n/a')} | "
                f"response_npz={str(summary.get('pbd_resolved_ndtha_response_npz') or accel.get('pbd_resolved_ndtha_response_npz') or 'n/a')} | "
                f"fallback_used={bool(summary.get('pbd_ndtha_response_fallback_used') if 'pbd_ndtha_response_fallback_used' in summary else accel.get('pbd_ndtha_response_fallback_used', False))} | "
                f"coverage={int(summary.get('pbd_ndtha_response_coverage_count') if 'pbd_ndtha_response_coverage_count' in summary else accel.get('pbd_ndtha_response_coverage_count', 0) or 0)}"
            )
        ),
        "panel_zone_3d_clash_ready": bool(
            summary.get("panel_zone_3d_clash_ready")
            if "panel_zone_3d_clash_ready" in summary
            else accel.get("panel_zone_3d_clash_ready", False)
        ),
        "panel_zone_constructability_mode": str(
            summary.get("panel_zone_constructability_mode") or accel.get("panel_zone_constructability_mode") or ""
        ),
        "panel_zone_constructability_reason": str(
            summary.get("panel_zone_constructability_reason") or accel.get("panel_zone_constructability_reason") or ""
        ),
        "panel_zone_proxy_candidate_count": int(
            summary.get("panel_zone_proxy_candidate_count")
            if "panel_zone_proxy_candidate_count" in summary
            else accel.get("panel_zone_proxy_candidate_count", 0)
        ),
        "panel_zone_source_artifact_kind": str(
            summary.get("panel_zone_source_artifact_kind") or accel.get("panel_zone_source_artifact_kind") or ""
        ),
        "panel_zone_source_artifact_path": str(
            summary.get("panel_zone_source_artifact_path") or accel.get("panel_zone_source_artifact_path") or ""
        ),
        "panel_zone_source_contract_mode": str(
            summary.get("panel_zone_source_contract_mode") or accel.get("panel_zone_source_contract_mode") or ""
        ),
        "panel_zone_internal_engine_complete": bool(
            summary.get("panel_zone_internal_engine_complete")
            if "panel_zone_internal_engine_complete" in summary
            else accel.get("panel_zone_internal_engine_complete", False)
        ),
        "panel_zone_external_validation_pending": bool(
            summary.get("panel_zone_external_validation_pending")
            if "panel_zone_external_validation_pending" in summary
            else accel.get("panel_zone_external_validation_pending", False)
        ),
        "panel_zone_validation_boundary": panel_zone_validation_boundary,
        "panel_zone_validation_advisory_only": panel_zone_validation_advisory_only,
        "panel_zone_validation_advisory_label": panel_zone_validation_advisory_label,
        "panel_zone_source_valid_row_counts": dict(
            summary.get("panel_zone_source_valid_row_counts")
            if "panel_zone_source_valid_row_counts" in summary
            else accel.get("panel_zone_source_valid_row_counts", {})
            or {}
        ),
        "panel_zone_source_overlap_member_counts": dict(
            summary.get("panel_zone_source_overlap_member_counts")
            if "panel_zone_source_overlap_member_counts" in summary
            else accel.get("panel_zone_source_overlap_member_counts", {})
            or {}
        ),
        "panel_zone_source_candidate_scan_modes": dict(
            summary.get("panel_zone_source_candidate_scan_modes")
            if "panel_zone_source_candidate_scan_modes" in summary
            else accel.get("panel_zone_source_candidate_scan_modes", {})
            or {}
        ),
        "panel_zone_validated_source_row_count_total": int(
            summary.get("panel_zone_validated_source_row_count_total")
            if "panel_zone_validated_source_row_count_total" in summary
            else accel.get("panel_zone_validated_source_row_count_total", 0)
        ),
        "panel_zone_validated_source_overlap_member_count_min": int(
            summary.get("panel_zone_validated_source_overlap_member_count_min")
            if "panel_zone_validated_source_overlap_member_count_min" in summary
            else accel.get("panel_zone_validated_source_overlap_member_count_min", 0)
        ),
        "foundation_optimization_ready": bool(
            summary.get("foundation_optimization_ready")
            if "foundation_optimization_ready" in summary
            else accel.get("foundation_optimization_ready", False)
        ),
        "foundation_member_type_present": bool(
            summary.get("foundation_member_type_present")
            if "foundation_member_type_present" in summary
            else accel.get("foundation_member_type_present", False)
        ),
        "foundation_member_type_count": int(
            summary.get("foundation_member_type_count")
            if "foundation_member_type_count" in summary
            else accel.get("foundation_member_type_count", 0)
        ),
        "foundation_optimization_mode": str(
            summary.get("foundation_optimization_mode") or accel.get("foundation_optimization_mode") or ""
        ),
        "foundation_optimization_reason": str(
            summary.get("foundation_optimization_reason") or accel.get("foundation_optimization_reason") or ""
        ),
        "foundation_scope_source": str(summary.get("foundation_scope_source") or accel.get("foundation_scope_source") or ""),
        "foundation_artifact_scan_mode": str(
            summary.get("foundation_artifact_scan_mode") or accel.get("foundation_artifact_scan_mode") or ""
        ),
        "upstream_foundation_label_count": int(
            summary.get("upstream_foundation_label_count")
            if "upstream_foundation_label_count" in summary
            else accel.get("upstream_foundation_label_count", 0)
        ),
        "raw_source_foundation_label_count": int(
            summary.get("raw_source_foundation_label_count")
            if "raw_source_foundation_label_count" in summary
            else accel.get("raw_source_foundation_label_count", 0)
        ),
        "upstream_foundation_provenance_mode": str(
            summary.get("upstream_foundation_provenance_mode") or accel.get("upstream_foundation_provenance_mode") or ""
        ),
        "wind_tunnel_raw_mapping_ready": bool(
            summary.get("wind_tunnel_raw_mapping_ready")
            if "wind_tunnel_raw_mapping_ready" in summary
            else accel.get("wind_tunnel_raw_mapping_ready", False)
        ),
        "wind_tunnel_mapping_mode": str(summary.get("wind_tunnel_mapping_mode") or accel.get("wind_tunnel_mapping_mode") or ""),
        "wind_tunnel_mapping_reason": str(
            summary.get("wind_tunnel_mapping_reason") or accel.get("wind_tunnel_mapping_reason") or ""
        ),
    }


def _load_committee_hold_context(snapshot_dir: Path, release_dir: Path) -> tuple[dict, dict]:
    snapshot_summary = snapshot_dir / "release" / "committee_review" / "committee_summary.json"
    live_summary = release_dir / "committee_review" / "committee_summary.json"
    summary_path = snapshot_summary if snapshot_summary.exists() else live_summary
    summary = _load_json(summary_path) if summary_path.exists() else {}
    diff = summary.get("authority_catalog_routing_diff") if isinstance(summary.get("authority_catalog_routing_diff"), dict) else {}
    if not diff:
        snapshot_diff = snapshot_dir / "release" / "committee_review" / "authority_catalog_routing_diff.json"
        live_diff = release_dir / "committee_review" / "authority_catalog_routing_diff.json"
        diff_path = snapshot_diff if snapshot_diff.exists() else live_diff
        diff = _load_json(diff_path) if diff_path.exists() else {}
    return summary, diff


def _effective_authority_catalog_diff(authority_catalog_diff: dict, accelerated_coverage: dict) -> dict:
    if authority_catalog_diff:
        return authority_catalog_diff
    change_count = int(accelerated_coverage.get("authority_catalog_diff_change_count", 0) or 0)
    if change_count <= 0:
        return {}
    return {
        "baseline_seeded": bool(accelerated_coverage.get("authority_catalog_routing_warning_active", False)),
        "change_count": change_count,
        "added_count": 0,
        "removed_count": 0,
        "unchanged_count": 0,
        "diff_rows": [],
        "source": "accelerated_coverage_summary_fallback",
    }


def _review_checklist(review_required: bool) -> list[str]:
    if not review_required:
        return [
            "Authority routing diff is clear for the current snapshot.",
            "Release candidate promotion may proceed under the current engineer-in-loop model.",
        ]
    return [
        "Review changed authority routing rows and confirm the affected submodel/story-zone scope.",
        "Run legacy-tool cross-validation for changed authority-track rows before release promotion.",
        "Record engineer sign-off against the hold review packet and clear the hold before repromotion.",
    ]


def _review_packet_rows(authority_catalog_diff: dict, residual_holdout_matrix_rows: list[dict]) -> list[dict]:
    diff_rows = [row for row in (authority_catalog_diff.get("diff_rows") or []) if isinstance(row, dict)]
    if diff_rows:
        return [
            {
                "row_type": "authority_catalog_diff",
                "review_priority": "high",
                "change_type": str(row.get("change_type", "")),
                "authority_track": str(row.get("authority_track", "")),
                "submodel_family": str(row.get("submodel_family", "")),
                "review_story_zone": str(row.get("review_story_zone", "")),
                "member_family": str(row.get("member_family", "")),
                "owner": str(row.get("owner", "")),
                "why": str(row.get("why", "")),
            }
            for row in diff_rows
        ]
    if residual_holdout_matrix_rows:
        return [
            {
                "row_type": "holdout_routing_reference",
                "review_priority": "reference",
                "change_type": "none",
                "authority_track": str(row.get("authority_track", "")),
                "submodel_family": str(row.get("submodel_family", "")),
                "review_story_zone": str(row.get("review_story_zone", "")),
                "member_family": str(row.get("member_family", "")),
                "owner": str(row.get("owner", "")),
                "why": str(row.get("why", "")),
            }
            for row in residual_holdout_matrix_rows[:12]
            if isinstance(row, dict)
        ]
    return [
        {
            "row_type": "summary_fallback",
            "review_priority": "summary",
            "change_type": "unknown",
            "authority_track": "",
            "submodel_family": "",
            "review_story_zone": "",
            "member_family": "",
            "owner": "licensed_engineer",
            "why": "Authority diff count is reported, but no row-level routing diff was available in the current snapshot.",
        }
    ]


def _write_hold_review_packet_markdown(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [row for row in (payload.get("review_packet_rows") or []) if isinstance(row, dict)]
    checklist = [row for row in (payload.get("review_checklist") or []) if isinstance(row, str)]
    signoff = payload.get("licensed_engineer_signoff") if isinstance(payload.get("licensed_engineer_signoff"), dict) else {}
    evidence = payload.get("clearance_evidence") if isinstance(payload.get("clearance_evidence"), dict) else {}
    lines = [
        "# Hold Review Packet",
        "",
        f"- Generated at: `{payload.get('generated_at', '')}`",
        f"- Source snapshot: `{payload.get('source_snapshot', '')}`",
        f"- Review status: `{payload.get('review_status', '')}`",
        f"- Recommended next step: `{payload.get('recommended_next_step', '')}`",
        f"- Promotion report: `{payload.get('promotion_report', '')}`",
        f"- Hold review manifest: `{payload.get('manifest_path', '')}`",
        f"- Hold review packet pdf: `{payload.get('hold_review_packet_pdf', '')}`",
        f"- Hold review ack: `{payload.get('hold_review_ack_json', '')}`",
        "",
        "## Review Scope",
        "",
        f"- `authority_catalog_diff_change_count`: `{payload.get('authority_catalog_diff_change_count', 0)}`",
        f"- `authority_catalog_diff_added_count`: `{payload.get('authority_catalog_diff_added_count', 0)}`",
        f"- `authority_catalog_diff_removed_count`: `{payload.get('authority_catalog_diff_removed_count', 0)}`",
        f"- `residual_holdout_matrix_row_count`: `{payload.get('residual_holdout_matrix_row_count', 0)}`",
        "",
        "## Engineer Sign-Off And Clearance Evidence",
        "",
        f"- `licensed_engineer_signoff.status`: `{signoff.get('status', '')}`",
        f"- `licensed_engineer_signoff.signer_name`: `{signoff.get('signer_name', '')}`",
        f"- `licensed_engineer_signoff.signer_license_id`: `{signoff.get('signer_license_id', '')}`",
        f"- `licensed_engineer_signoff.signed_at`: `{signoff.get('signed_at', '')}`",
        f"- `licensed_engineer_signoff.signature_reference`: `{signoff.get('signature_reference', '')}`",
        f"- `clearance_evidence.status`: `{evidence.get('status', '')}`",
        f"- `clearance_evidence.evidence_hash_sha256`: `{evidence.get('evidence_hash_sha256', '')}`",
        "",
        "## Review Checklist",
        "",
    ]
    for item in checklist:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Review Packet Rows",
            "",
            "| Type | Priority | Change | Track | Submodel | Story/Zone | Member | Owner | Why |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('row_type', '')} | {row.get('review_priority', '')} | {row.get('change_type', '')} | "
            f"{row.get('authority_track', '')} | {row.get('submodel_family', '')} | {row.get('review_story_zone', '')} | "
            f"{row.get('member_family', '')} | {row.get('owner', '')} | {row.get('why', '')} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_hold_review_packet_pdf(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    configure_matplotlib_cjk_pdf()
    rows = [row for row in (payload.get("review_packet_rows") or []) if isinstance(row, dict)]
    checklist = [row for row in (payload.get("review_checklist") or []) if isinstance(row, str)]
    signoff = payload.get("licensed_engineer_signoff") if isinstance(payload.get("licensed_engineer_signoff"), dict) else {}
    evidence = payload.get("clearance_evidence") if isinstance(payload.get("clearance_evidence"), dict) else {}
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.03, 0.96, "Hold Review Packet", fontsize=20, weight="bold", va="top")
        y = 0.90
        header_rows = [
            ("Generated", payload.get("generated_at", "")),
            ("Source snapshot", payload.get("source_snapshot", "")),
            ("Review status", payload.get("review_status", "")),
            ("Recommended next step", payload.get("recommended_next_step", "")),
            ("Promotion report", payload.get("promotion_report", "")),
            ("Hold review manifest", payload.get("manifest_path", "")),
            ("Hold review ack", payload.get("hold_review_ack_json", "")),
            ("Packet PDF", payload.get("hold_review_packet_pdf", "")),
            ("Authority diff count", str(payload.get("authority_catalog_diff_change_count", 0))),
            ("Residual matrix rows", str(payload.get("residual_holdout_matrix_row_count", 0))),
            ("Signoff status", str(signoff.get("status", ""))),
            ("Evidence hash", str(evidence.get("evidence_hash_sha256", ""))),
        ]
        for key, value in header_rows:
            ax.text(0.04, y, f"{key}", fontsize=10.5, color="#6c5b4d", va="top")
            ax.text(0.33, y, str(value), fontsize=10.7, color="#1f1a16", va="top", wrap=True)
            y -= 0.055
        finalize_pdf_figure(fig, text_page=True)
        pdf.savefig(fig)
        plt.close(fig)

        if checklist:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Review Checklist", fontsize=18, weight="bold", va="top")
            y = 0.88
            for item in checklist:
                ax.text(0.05, y, f"- {item}", fontsize=10.5, va="top", wrap=True)
                y -= 0.08
                if y < 0.10:
                    finalize_pdf_figure(fig, text_page=True)
                    pdf.savefig(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Review Checklist", fontsize=18, weight="bold", va="top")
                    y = 0.88
            finalize_pdf_figure(fig, text_page=True)
            pdf.savefig(fig)
            plt.close(fig)

        if rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Review Packet Rows", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"{row.get('row_type', '')} | priority={row.get('review_priority', '')} | change={row.get('change_type', '')} | "
                        f"track={row.get('authority_track', '')} | submodel={row.get('submodel_family', '')} | "
                        f"story/zone={row.get('review_story_zone', '')} | member={row.get('member_family', '')}"
                    ),
                    fontsize=9.4,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                ax.text(0.06, y, f"owner={row.get('owner', '')} | why={row.get('why', '')}", fontsize=8.8, va="top", wrap=True)
                y -= 0.07
                if y < 0.10:
                    finalize_pdf_figure(fig, text_page=True)
                    pdf.savefig(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Review Packet Rows", fontsize=18, weight="bold", va="top")
                    y = 0.90
            finalize_pdf_figure(fig, text_page=True)
            pdf.savefig(fig)
            plt.close(fig)


def _clearance_evidence_hash(authority_catalog_diff: dict, review_packet_rows: list[dict], residual_holdout_matrix_rows: list[dict]) -> str:
    payload = {
        "authority_catalog_routing_diff": authority_catalog_diff,
        "review_packet_rows": review_packet_rows,
        "residual_holdout_matrix_rows": residual_holdout_matrix_rows,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _build_hold_review_ack(
    *,
    now_iso: str,
    snapshot_name: str,
    snapshot_dir: Path,
    promotion_report: Path,
    hold_review_manifest_path: Path,
    hold_review_packet_md_path: Path,
    hold_review_packet_pdf_path: Path,
    hold_review_ack_path: Path,
    review_required: bool,
    reason_code: str,
    effective_authority_catalog_diff: dict,
    review_packet_rows: list[dict],
    residual_holdout_matrix_rows: list[dict],
) -> dict:
    prior = _load_json(hold_review_ack_path) if hold_review_ack_path.exists() else {}
    prior_events = [row for row in (prior.get("events") or []) if isinstance(row, dict)]
    prior_engineer_ack = prior.get("engineer_ack") if isinstance(prior.get("engineer_ack"), dict) else {}
    prior_clearance = prior.get("hold_clearance") if isinstance(prior.get("hold_clearance"), dict) else {}
    prior_signoff = prior.get("licensed_engineer_signoff") if isinstance(prior.get("licensed_engineer_signoff"), dict) else {}
    prior_evidence = prior.get("clearance_evidence") if isinstance(prior.get("clearance_evidence"), dict) else {}
    event_type = "hold_detected" if review_required else "hold_clear_or_not_required"
    event = {
        "timestamp": now_iso,
        "event": event_type,
        "reason_code": reason_code,
        "authority_catalog_diff_change_count": int(effective_authority_catalog_diff.get("change_count", 0)),
    }
    events = prior_events + [event]
    if review_required:
        engineer_ack = {
            "status": str(prior_engineer_ack.get("status", "pending_review")),
            "acknowledged_by": str(prior_engineer_ack.get("acknowledged_by", "")),
            "acknowledged_at": str(prior_engineer_ack.get("acknowledged_at", "")),
            "notes": str(prior_engineer_ack.get("notes", "")),
        }
        hold_clearance = {
            "status": str(prior_clearance.get("status", "pending_clearance")),
            "cleared_by": str(prior_clearance.get("cleared_by", "")),
            "cleared_at": str(prior_clearance.get("cleared_at", "")),
            "basis": str(prior_clearance.get("basis", "")),
        }
        licensed_engineer_signoff = {
            "status": str(prior_signoff.get("status", "pending_signoff")),
            "signer_name": str(prior_signoff.get("signer_name", "")),
            "signer_license_id": str(prior_signoff.get("signer_license_id", "")),
            "signed_at": str(prior_signoff.get("signed_at", "")),
            "signature_reference": str(prior_signoff.get("signature_reference", "")),
            "notes": str(prior_signoff.get("notes", "")),
        }
    else:
        prior_pending_clearance = str(prior_clearance.get("status", "")) in {"pending_clearance", "clear_ready_for_record"}
        engineer_ack = {
            "status": "not_required" if not prior_engineer_ack else str(prior_engineer_ack.get("status", "not_required")),
            "acknowledged_by": str(prior_engineer_ack.get("acknowledged_by", "")),
            "acknowledged_at": str(prior_engineer_ack.get("acknowledged_at", "")),
            "notes": str(prior_engineer_ack.get("notes", "")),
        }
        hold_clearance = {
            "status": (
                "clear_ready_for_record"
                if prior_pending_clearance
                else ("clear_not_required" if not prior_clearance else str(prior_clearance.get("status", "clear_not_required")))
            ),
            "cleared_by": str(prior_clearance.get("cleared_by", "")),
            "cleared_at": str(prior_clearance.get("cleared_at", "")),
            "basis": str(prior_clearance.get("basis", "")),
        }
        licensed_engineer_signoff = {
            "status": "not_required" if not prior_signoff else str(prior_signoff.get("status", "not_required")),
            "signer_name": str(prior_signoff.get("signer_name", "")),
            "signer_license_id": str(prior_signoff.get("signer_license_id", "")),
            "signed_at": str(prior_signoff.get("signed_at", "")),
            "signature_reference": str(prior_signoff.get("signature_reference", "")),
            "notes": str(prior_signoff.get("notes", "")),
        }
    evidence_hash = _clearance_evidence_hash(
        effective_authority_catalog_diff,
        review_packet_rows,
        residual_holdout_matrix_rows,
    )
    clearance_evidence = {
        "status": (
            "pending_evidence_review"
            if review_required
            else (
                "ready_for_clearance_record"
                if hold_clearance.get("status") == "clear_ready_for_record"
                else "not_required"
            )
        ),
        "evidence_hash_sha256": evidence_hash,
        "evidence_basis": "canonical_json(authority_catalog_routing_diff, review_packet_rows, residual_holdout_matrix_rows)",
        "evidence_source_paths": [
            str(hold_review_manifest_path),
            str(hold_review_packet_md_path),
            str(hold_review_packet_pdf_path),
        ],
        "review_notes": str(prior_evidence.get("review_notes", "")),
    }
    return {
        "schema_version": "1.0",
        "run_id": "phase3-hold-review-ack",
        "generated_at": now_iso,
        "source_snapshot": snapshot_name,
        "source_snapshot_dir": str(snapshot_dir),
        "promotion_report": str(promotion_report),
        "hold_review_manifest": str(hold_review_manifest_path),
        "hold_review_packet_md": str(hold_review_packet_md_path),
        "hold_review_packet_pdf": str(hold_review_packet_pdf_path),
        "hold_review_ack_json": str(hold_review_ack_path),
        "ack_required": bool(review_required),
        "reason_code": reason_code,
        "review_row_count": int(len(review_packet_rows)),
        "authority_catalog_diff_change_count": int(effective_authority_catalog_diff.get("change_count", 0)),
        "engineer_ack": engineer_ack,
        "licensed_engineer_signoff": licensed_engineer_signoff,
        "hold_clearance": hold_clearance,
        "clearance_evidence": clearance_evidence,
        "events": events,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--release-dir", default="implementation/phase1/release")
    p.add_argument("--nightly-pointer", default="implementation/phase1/release/phase3_nightly_latest.json")
    p.add_argument("--pr-ci", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--out", default="implementation/phase1/release/release_candidate_promotion_report.json")
    p.add_argument("--latest-rc-pointer", default="implementation/phase1/release/release_candidate_latest.json")
    p.add_argument("--hold-review-manifest", default="implementation/phase1/release/hold_review_manifest.json")
    p.add_argument("--hold-review-packet-md", default="implementation/phase1/release/hold_review_packet.md")
    p.add_argument("--hold-review-packet-pdf", default="implementation/phase1/release/hold_review_packet.pdf")
    p.add_argument("--hold-review-ack-json", default="implementation/phase1/release/hold_review_ack.json")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    release_dir = Path(args.release_dir).resolve()
    release_dir.mkdir(parents=True, exist_ok=True)

    nightly_ptr = Path(args.nightly_pointer)
    if not nightly_ptr.exists():
        raise SystemExit(f"nightly pointer missing: {nightly_ptr}")
    nightly = _load_json(nightly_ptr)
    snapshot_dir = Path(str(nightly.get("path", "")))
    snapshot_name = str(nightly.get("snapshot", ""))
    if not snapshot_name or not snapshot_dir.exists():
        raise SystemExit("invalid nightly pointer (snapshot/path)")

    nightly_ci = snapshot_dir / "ci_gate_report.json"
    nightly_pipeline = snapshot_dir / "phase3_megastructure_pipeline_report.json"
    nightly_validator = snapshot_dir / "static_artifact_validation_report.json"
    nightly_commercial_readiness = snapshot_dir / "commercial_readiness_report.json"
    nightly_real_source_multi = snapshot_dir / "real_source_multi_gate_report.json"
    nightly_nonlinear_engine = snapshot_dir / "nonlinear_frame_engine_report.json"
    nightly_pushover_stress = snapshot_dir / "nonlinear_pushover_stress_report.json"
    nightly_ndtha_stress = snapshot_dir / "nonlinear_ndtha_stress_report.json"
    nightly_10m_repro = snapshot_dir / "nightly_10m_repro_report.json"
    snapshot_manifest = snapshot_dir / "snapshot_manifest.json"
    pr_ci = Path(args.pr_ci)

    nightly_ci_ok, nightly_ci_reason = _report_green(nightly_ci)
    nightly_pipeline_ok, nightly_pipeline_reason = _report_green(nightly_pipeline)
    nightly_validator_ok, nightly_validator_reason = _report_green(nightly_validator)
    nightly_commercial_readiness_ok, nightly_commercial_readiness_reason = _report_green(nightly_commercial_readiness)
    nightly_real_source_multi_ok, nightly_real_source_multi_reason = _report_green(nightly_real_source_multi)
    nightly_nonlinear_engine_ok, nightly_nonlinear_engine_reason = _report_green(nightly_nonlinear_engine)
    nightly_pushover_stress_ok, nightly_pushover_stress_reason = _report_green(nightly_pushover_stress)
    nightly_ndtha_stress_ok, nightly_ndtha_stress_reason = _report_green(nightly_ndtha_stress)
    nightly_10m_repro_ok, nightly_10m_repro_reason = _report_green(nightly_10m_repro)
    accelerated_coverage = _registry_accelerated_coverage_summary(snapshot_dir)
    committee_summary, authority_catalog_diff = _load_committee_hold_context(snapshot_dir, release_dir)
    manifest_ok = False
    manifest_reason = "missing snapshot_manifest"
    if snapshot_manifest.exists():
        manifest = _load_json(snapshot_manifest)
        policy = manifest.get("release_policy") if isinstance(manifest.get("release_policy"), dict) else {}
        manifest_ok = bool(policy.get("policy_pass", False))
        manifest_reason = "PASS" if manifest_ok else "release_policy.policy_pass=false"
    pr_ci_ok, pr_ci_reason = _report_green(pr_ci)

    dual_green = bool(
        nightly_ci_ok
        and nightly_pipeline_ok
        and nightly_validator_ok
        and nightly_commercial_readiness_ok
        and nightly_real_source_multi_ok
        and nightly_nonlinear_engine_ok
        and nightly_pushover_stress_ok
        and nightly_ndtha_stress_ok
        and nightly_10m_repro_ok
        and manifest_ok
        and pr_ci_ok
    )
    authority_hold_for_review = bool(int(accelerated_coverage.get("authority_catalog_diff_change_count", 0) or 0) > 0)
    hold_review_manifest_path = Path(args.hold_review_manifest)
    hold_review_packet_md_path = Path(args.hold_review_packet_md)
    hold_review_packet_pdf_path = Path(args.hold_review_packet_pdf)
    hold_review_ack_path = Path(args.hold_review_ack_json)

    candidate_id = f"rc_{now.strftime('%Y%m%dT%H%M%SZ')}"
    contract_pass = bool(dual_green and not authority_hold_for_review)
    if contract_pass:
        reason_code = "PASS"
        reason = "nightly and pr gates are green"
    elif authority_hold_for_review:
        reason_code = "HOLD_FOR_REVIEW"
        reason = "authority routing diff requires explicit review before promotion"
    else:
        reason_code = "ERR_PROMOTION_GATE"
        reason = "dual-green policy failed"

    report = {
        "schema_version": "1.0",
        "run_id": "phase3-promote-release-candidate",
        "generated_at": now.isoformat(),
        "candidate_id": candidate_id,
        "source_snapshot": snapshot_name,
        "source_snapshot_dir": str(snapshot_dir),
        "checks": {
            "nightly_ci_green": bool(nightly_ci_ok),
            "nightly_pipeline_green": bool(nightly_pipeline_ok),
            "nightly_validator_green": bool(nightly_validator_ok),
            "nightly_commercial_readiness_green": bool(nightly_commercial_readiness_ok),
            "nightly_real_source_multi_green": bool(nightly_real_source_multi_ok),
            "nightly_nonlinear_engine_green": bool(nightly_nonlinear_engine_ok),
            "nightly_pushover_stress_green": bool(nightly_pushover_stress_ok),
            "nightly_ndtha_stress_green": bool(nightly_ndtha_stress_ok),
            "nightly_10m_repro_green": bool(nightly_10m_repro_ok),
            "snapshot_release_policy_green": bool(manifest_ok),
            "pr_ci_green": bool(pr_ci_ok),
            "dual_green_policy": bool(dual_green),
            "authority_hold_for_review": bool(authority_hold_for_review),
        },
        "pbd_response_source": {
            "resolved_ndtha_report": str(accelerated_coverage.get("pbd_resolved_ndtha_report", "") or ""),
            "resolved_ndtha_response_npz": str(accelerated_coverage.get("pbd_resolved_ndtha_response_npz", "") or ""),
            "fallback_used": bool(accelerated_coverage.get("pbd_ndtha_response_fallback_used", False)),
            "coverage_count": int(accelerated_coverage.get("pbd_ndtha_response_coverage_count", 0) or 0),
            "label": str(accelerated_coverage.get("pbd_response_source_label", "") or ""),
        },
        "summary": accelerated_coverage,
        **accelerated_coverage,
        "hold_review_manifest": str(hold_review_manifest_path),
        "hold_review_packet_md": str(hold_review_packet_md_path),
        "hold_review_packet_pdf": str(hold_review_packet_pdf_path),
        "hold_review_ack_json": str(hold_review_ack_path),
        "reasons": {
            "nightly_ci_reason": nightly_ci_reason,
            "nightly_pipeline_reason": nightly_pipeline_reason,
            "nightly_validator_reason": nightly_validator_reason,
            "nightly_commercial_readiness_reason": nightly_commercial_readiness_reason,
            "nightly_real_source_multi_reason": nightly_real_source_multi_reason,
            "nightly_nonlinear_engine_reason": nightly_nonlinear_engine_reason,
            "nightly_pushover_stress_reason": nightly_pushover_stress_reason,
            "nightly_ndtha_stress_reason": nightly_ndtha_stress_reason,
            "nightly_10m_repro_reason": nightly_10m_repro_reason,
            "snapshot_release_policy_reason": manifest_reason,
            "pr_ci_reason": pr_ci_reason,
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    effective_authority_catalog_diff = _effective_authority_catalog_diff(authority_catalog_diff, accelerated_coverage)
    residual_holdout_matrix_rows = [
        row for row in (committee_summary.get("residual_holdout_matrix_rows") or []) if isinstance(row, dict)
    ]
    review_packet_rows = _review_packet_rows(effective_authority_catalog_diff, residual_holdout_matrix_rows)
    hold_manifest = {
        "schema_version": "1.0",
        "run_id": "phase3-hold-review-manifest",
        "packet_type": "engineer_hold_review",
        "generated_at": now.isoformat(),
        "source_snapshot": snapshot_name,
        "source_snapshot_dir": str(snapshot_dir),
        "promotion_report": str(out_path),
        "manifest_path": str(hold_review_manifest_path),
        "hold_review_packet_md": str(hold_review_packet_md_path),
        "hold_review_packet_pdf": str(hold_review_packet_pdf_path),
        "hold_review_ack_json": str(hold_review_ack_path),
        "review_required": bool(authority_hold_for_review),
        "review_status": "review_required" if authority_hold_for_review else "clear",
        "review_owner": "licensed_engineer",
        "recommended_next_step": "hold_release_candidate" if authority_hold_for_review else "promotion_may_proceed",
        "reason_code": reason_code,
        "reason": reason,
        "pbd_response_source": {
            "resolved_ndtha_report": str(accelerated_coverage.get("pbd_resolved_ndtha_report", "") or ""),
            "resolved_ndtha_response_npz": str(accelerated_coverage.get("pbd_resolved_ndtha_response_npz", "") or ""),
            "fallback_used": bool(accelerated_coverage.get("pbd_ndtha_response_fallback_used", False)),
            "coverage_count": int(accelerated_coverage.get("pbd_ndtha_response_coverage_count", 0) or 0),
            "label": str(accelerated_coverage.get("pbd_response_source_label", "") or ""),
        },
        "summary": accelerated_coverage,
        "authority_catalog_routing_diff": effective_authority_catalog_diff,
        "authority_catalog_diff_change_count": int(effective_authority_catalog_diff.get("change_count", 0)),
        "authority_catalog_diff_added_count": int(effective_authority_catalog_diff.get("added_count", 0)),
        "authority_catalog_diff_removed_count": int(effective_authority_catalog_diff.get("removed_count", 0)),
        "authority_catalog_diff_baseline_seeded": bool(effective_authority_catalog_diff.get("baseline_seeded", False)),
        "committee_summary_path": str((snapshot_dir / "release" / "committee_review" / "committee_summary.json")),
        "review_checklist": _review_checklist(bool(authority_hold_for_review)),
        "review_rows": [row for row in (effective_authority_catalog_diff.get("diff_rows") or []) if isinstance(row, dict)],
        "review_packet_rows": review_packet_rows,
        "residual_holdout_matrix_row_count": int(len(residual_holdout_matrix_rows)),
        "residual_holdout_matrix_rows": residual_holdout_matrix_rows,
    }
    hold_review_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    hold_review_manifest_path.write_text(json.dumps(hold_manifest, indent=2), encoding="utf-8")
    _write_hold_review_packet_markdown(hold_review_packet_md_path, hold_manifest)
    hold_review_ack = _build_hold_review_ack(
        now_iso=now.isoformat(),
        snapshot_name=snapshot_name,
        snapshot_dir=snapshot_dir,
        promotion_report=out_path,
        hold_review_manifest_path=hold_review_manifest_path,
        hold_review_packet_md_path=hold_review_packet_md_path,
        hold_review_packet_pdf_path=hold_review_packet_pdf_path,
        hold_review_ack_path=hold_review_ack_path,
        review_required=bool(authority_hold_for_review),
        reason_code=reason_code,
        effective_authority_catalog_diff=effective_authority_catalog_diff,
        review_packet_rows=review_packet_rows,
        residual_holdout_matrix_rows=residual_holdout_matrix_rows,
    )
    hold_review_ack_path.parent.mkdir(parents=True, exist_ok=True)
    hold_review_ack_path.write_text(json.dumps(hold_review_ack, indent=2), encoding="utf-8")
    hold_review_packet_payload = {
        **hold_manifest,
        "licensed_engineer_signoff": hold_review_ack.get("licensed_engineer_signoff", {}),
        "clearance_evidence": hold_review_ack.get("clearance_evidence", {}),
    }
    _write_hold_review_packet_markdown(hold_review_packet_md_path, hold_review_packet_payload)
    _write_hold_review_packet_pdf(hold_review_packet_pdf_path, hold_review_packet_payload)

    latest_rc_path = Path(args.latest_rc_pointer)
    if contract_pass:
        latest_rc = {
            "candidate_id": candidate_id,
            "source_snapshot": snapshot_name,
            "source_snapshot_dir": str(snapshot_dir),
            "promotion_report": str(out_path),
            "hold_review_manifest": str(hold_review_manifest_path),
            "hold_review_packet_md": str(hold_review_packet_md_path),
            "hold_review_packet_pdf": str(hold_review_packet_pdf_path),
            "hold_review_ack_json": str(hold_review_ack_path),
            "generated_at": now.isoformat(),
            "pbd_response_source": {
                "resolved_ndtha_report": str(accelerated_coverage.get("pbd_resolved_ndtha_report", "") or ""),
                "resolved_ndtha_response_npz": str(accelerated_coverage.get("pbd_resolved_ndtha_response_npz", "") or ""),
                "fallback_used": bool(accelerated_coverage.get("pbd_ndtha_response_fallback_used", False)),
                "coverage_count": int(accelerated_coverage.get("pbd_ndtha_response_coverage_count", 0) or 0),
                "label": str(accelerated_coverage.get("pbd_response_source_label", "") or ""),
            },
            "summary": accelerated_coverage,
            **accelerated_coverage,
        }
        latest_rc_path.write_text(json.dumps(latest_rc, indent=2), encoding="utf-8")
    elif latest_rc_path.exists():
        latest_rc_path.unlink()

    print(f"Wrote release candidate promotion report: {out_path}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
