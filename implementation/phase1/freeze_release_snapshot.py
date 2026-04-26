#!/usr/bin/env python3
"""Freeze nightly release snapshot artifacts into immutable bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_files(text: str) -> list[str]:
    out: list[str] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if tok:
            out.append(tok)
    if not out:
        raise ValueError("at least one artifact file is required")
    return out


def _parse_optional_files(text: str) -> list[str]:
    out: list[str] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if tok:
            out.append(tok)
    return out


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_gate_ok(path: Path) -> bool:
    payload = _load_json(path)
    if "all_pass" in payload:
        return bool(payload.get("all_pass", False))
    if "contract_pass" in payload:
        return bool(payload.get("contract_pass", False))
    if "pass" in payload:
        return bool(payload.get("pass", False))
    return True


def _bool(d: dict, path: tuple[str, ...]) -> bool:
    cur: object = d
    for key in path:
        if not isinstance(cur, dict):
            return False
        cur = cur.get(key)
    return bool(cur)


def _release_policy_checks(source_dir: Path) -> dict:
    cr = _load_json(source_dir / "commercial_readiness_report.json")
    rs = _load_json(source_dir / "real_source_multi_gate_report.json")
    ne = _load_json(source_dir / "nonlinear_frame_engine_report.json")
    ps = _load_json(source_dir / "nonlinear_pushover_stress_report.json")
    nd = _load_json(source_dir / "nonlinear_ndtha_stress_report.json")
    p3 = _load_json(source_dir / "phase3_megastructure_pipeline_report.json")
    topo = _load_json(source_dir / "opensees_topology_report.json")
    sio = _load_json(source_dir / "scaleout_io_profile_report.json")
    registry = _load_json(source_dir / "release/release_registry.json")

    checks = {
        "commercial_readiness_pass": bool(cr.get("contract_pass", False)),
        "commercial_readiness_real_source_pass": _bool(cr, ("checks", "real_source_pass")),
        "commercial_readiness_gpu_strict_pass": _bool(cr, ("checks", "gpu_strict_pass")),
        "forbid_toy_cases_enforced": _bool(cr, ("inputs", "forbid_toy_cases")),
        "real_source_multi_pass": bool(rs.get("contract_pass", False)),
        "real_source_multi_all_real_source_pass": _bool(rs, ("checks", "all_real_source_pass")),
        "real_source_multi_all_toy_free_pass": _bool(rs, ("checks", "all_toy_free_pass")),
        "nonlinear_engine_pass": bool(ne.get("contract_pass", False)),
        "nonlinear_engine_rust_backend_pass": _bool(ne, ("checks", "rust_backend_used_pass")),
        "nonlinear_engine_convergence_pass": _bool(ne, ("checks", "all_cases_converged")),
        "nonlinear_engine_drift_p95_pass": _bool(ne, ("checks", "drift_p95_pass")),
        "nonlinear_engine_base_p95_pass": _bool(ne, ("checks", "base_shear_p95_pass")),
        "nonlinear_engine_top_p95_pass": _bool(ne, ("checks", "top_disp_p95_pass")),
        "pushover_stress_pass": bool(ps.get("contract_pass", False)),
        "pushover_convergence_pass": _bool(ps, ("checks", "all_cases_converged")),
        "pushover_plasticity_pass": _bool(ps, ("checks", "plasticity_triggered_all_cases")),
        "pushover_collapse_path_pass": _bool(ps, ("checks", "collapse_path_pass")),
        "pushover_min_plastic_pass": _bool(ps, ("checks", "min_plastic_story_count_pass")),
        "ndtha_stress_pass": bool(nd.get("contract_pass", False)),
        "ndtha_convergence_pass": _bool(nd, ("checks", "all_cases_converged")),
        "ndtha_pdelta_pass": _bool(nd, ("checks", "pdelta_enabled_pass")),
        "ndtha_dynamic_reversal_pass": _bool(nd, ("checks", "dynamic_reversal_pass")),
        "ndtha_rust_backend_pass": _bool(nd, ("checks", "rust_backend_used_pass")),
        "ndtha_plasticity_pass": _bool(nd, ("checks", "plasticity_triggered_all_cases")),
        "ndtha_min_plastic_pass": _bool(nd, ("checks", "min_plastic_story_count_pass")),
        "phase3_shell_beam_mix_pass": _bool(p3, ("checks", "shell_beam_mix_pass")),
        "phase3_gpu_strict_pass": _bool(p3, ("checks", "gpu_strict_pass")),
        "phase3_real_source_verified": _bool(p3, ("checks", "real_source_verified")),
        "topology_shell_beam_mix_pass": _bool(topo, ("checks", "shell_beam_mix_pass")),
        "scaleout_io_gpu_strict_pass": _bool(sio, ("checks", "gpu_strict_pass")),
        "release_registry_pass": bool(registry.get("contract_pass", False)),
        "release_registry_signature_pass": _bool(registry, ("checks", "signature_verified_pass")),
    }
    checks["policy_pass"] = all(bool(v) for v in checks.values())
    return checks


def _registry_accelerated_coverage_summary(source_dir: Path) -> dict:
    registry = _load_json(source_dir / "release/release_registry.json")
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
        "panel_zone_validation_boundary": str(
            summary.get("panel_zone_validation_boundary") or accel.get("panel_zone_validation_boundary") or ""
        ),
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source-dir", default="implementation/phase1")
    p.add_argument("--release-dir", default="implementation/phase1/release")
    p.add_argument("--snapshot-prefix", default="phase3_nightly_hardening")
    p.add_argument(
        "--artifact-files",
        default=(
            "phase3_megastructure_pipeline_report.json,"
            "opensees_topology_report.json,"
            "partitioned_scaleout_report.json,"
            "sync_stress_gate_report.json,"
            "noise_convergence_gate_report.json,"
            "commercial_csv_gate_report.json,"
            "commercial_readiness_report.json,"
            "real_source_multi_gate_report.json,"
            "nonlinear_frame_engine_report.json,"
            "nonlinear_pushover_stress_report.json,"
            "nonlinear_ndtha_stress_report.json,"
            "nightly_10m_repro_report.json,"
            "scaleout_io_profile_report.json,"
            "pbd_hinge_refresh_report.json,"
            "panel_zone_clash_artifact.json,"
            "panel_zone_clash_report.json,"
            "wind_tunnel_raw_mapping.json,"
            "wind_tunnel_raw_mapping_report.json,"
            "release/release_registry.json,"
            "release/release_gap_report.json,"
            "release/release_gap_report.md,"
            "release/release_gap_smoke_history.png,"
            "release/release_gap_measured_chain_categories.png,"
            "release/design_optimization/foundation_optimization_artifact.json,"
            "release/design_optimization/foundation_optimization_report.json,"
            "release/committee_review/committee_review_package_report.json,"
            "release/committee_review/committee_summary.json,"
            "release/committee_review/authority_catalog_routing_diff.json,"
            "release/signing/release_registry_ed25519.pub.pem,"
            "release/signing/release_registry.signature.b64,"
            "ci_gate_report.json,"
            "static_artifact_validation_report.json,"
            "ci_artifact_manifest.json"
        ),
    )
    p.add_argument(
        "--optional-artifact-files",
        default=(
            "panel_zone_joint_geometry_3d.json,"
            "panel_zone_rebar_anchorage_3d.json,"
            "panel_zone_clash_verification_3d.json,"
            "panel_zone_joint_geometry_3d_contract.json,"
            "panel_zone_rebar_anchorage_3d_contract.json,"
            "panel_zone_clash_verification_3d_contract.json"
        ),
        help="Optional artifacts to include in the manifest when present; missing files are recorded but do not fail the snapshot.",
    )
    p.add_argument("--require-green-json", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--enforce-release-policy", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--latest-pointer", default="implementation/phase1/release/phase3_nightly_latest.json")
    p.add_argument("--out", default="")
    args = p.parse_args()

    source_dir = Path(args.source_dir).resolve()
    release_dir = Path(args.release_dir).resolve()
    release_dir.mkdir(parents=True, exist_ok=True)

    files = _parse_files(args.artifact_files)
    optional_files = _parse_optional_files(args.optional_artifact_files)
    release_policy = _release_policy_checks(source_dir)
    accelerated_coverage = _registry_accelerated_coverage_summary(source_dir)
    if bool(args.enforce_release_policy) and not bool(release_policy.get("policy_pass", False)):
        raise SystemExit(f"release policy check failed: {release_policy}")

    ts = datetime.now(timezone.utc)
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    snapshot_name = f"{args.snapshot_prefix}_{stamp}"
    snapshot_dir = release_dir / snapshot_name
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    manifest_files: list[dict] = []
    copied_paths: list[Path] = []
    for rel in files:
        src = source_dir / rel
        if not src.exists():
            raise SystemExit(f"missing artifact: {src}")
        if bool(args.require_green_json) and src.suffix.lower() == ".json":
            if not _json_gate_ok(src):
                raise SystemExit(f"artifact gate is not green: {src}")
        dst = snapshot_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_paths.append(dst)
        manifest_files.append(
            {
                "file": rel,
                "present": True,
                "optional": False,
                "bytes": int(dst.stat().st_size),
                "sha256": _sha256(dst),
            }
        )

    optional_manifest_files: list[dict] = []
    for rel in optional_files:
        src = source_dir / rel
        if src.exists():
            json_gate_pass = True
            if src.suffix.lower() == ".json":
                json_gate_pass = bool(_json_gate_ok(src))
            dst = snapshot_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied_paths.append(dst)
            optional_manifest_files.append(
                {
                    "file": rel,
                    "present": True,
                    "optional": True,
                    "bytes": int(dst.stat().st_size),
                    "sha256": _sha256(dst),
                    "json_gate_pass": bool(json_gate_pass),
                }
            )
        else:
            optional_manifest_files.append(
                {
                    "file": rel,
                    "present": False,
                    "optional": True,
                    "bytes": 0,
                    "sha256": "",
                    "missing": True,
                    "json_gate_pass": False,
                }
            )

    snapshot_manifest = {
        "schema_version": "1.0",
        "run_id": "phase3-nightly-release-snapshot",
        "generated_at": ts.isoformat(),
        "snapshot": snapshot_name,
        "source_dir": str(source_dir),
        "release_policy": release_policy,
        "accelerated_coverage": accelerated_coverage,
        "pbd_response_source": {
            "resolved_ndtha_report": str(accelerated_coverage.get("pbd_resolved_ndtha_report", "") or ""),
            "resolved_ndtha_response_npz": str(accelerated_coverage.get("pbd_resolved_ndtha_response_npz", "") or ""),
            "fallback_used": bool(accelerated_coverage.get("pbd_ndtha_response_fallback_used", False)),
            "coverage_count": int(accelerated_coverage.get("pbd_ndtha_response_coverage_count", 0) or 0),
            "label": str(accelerated_coverage.get("pbd_response_source_label", "") or ""),
        },
        "release_policy_sha256": hashlib.sha256(
            json.dumps(release_policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "files": manifest_files,
        "optional_files": optional_manifest_files,
    }
    (snapshot_dir / "snapshot_manifest.json").write_text(json.dumps(snapshot_manifest, indent=2), encoding="utf-8")

    tar_path = release_dir / f"{snapshot_name}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(snapshot_dir, arcname=snapshot_name)

    latest_pointer = {
        "snapshot": snapshot_name,
        "path": str(snapshot_dir),
        "tarball": str(tar_path),
        "generated_at": ts.isoformat(),
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
    Path(args.latest_pointer).write_text(json.dumps(latest_pointer, indent=2), encoding="utf-8")

    out_path = Path(args.out) if str(args.out).strip() else (snapshot_dir / "freeze_release_report.json")
    out_payload = {
        "schema_version": "1.0",
        "run_id": "phase3-freeze-release-snapshot",
        "generated_at": ts.isoformat(),
        "snapshot": snapshot_name,
        "snapshot_dir": str(snapshot_dir),
        "tarball": str(tar_path),
        "latest_pointer": str(Path(args.latest_pointer)),
        "artifact_count": len(copied_paths),
        "release_policy": release_policy,
        "accelerated_coverage": accelerated_coverage,
        "pbd_response_source": {
            "resolved_ndtha_report": str(accelerated_coverage.get("pbd_resolved_ndtha_report", "") or ""),
            "resolved_ndtha_response_npz": str(accelerated_coverage.get("pbd_resolved_ndtha_response_npz", "") or ""),
            "fallback_used": bool(accelerated_coverage.get("pbd_ndtha_response_fallback_used", False)),
            "coverage_count": int(accelerated_coverage.get("pbd_ndtha_response_coverage_count", 0) or 0),
            "label": str(accelerated_coverage.get("pbd_response_source_label", "") or ""),
        },
        "release_policy_sha256": snapshot_manifest["release_policy_sha256"],
        "summary": accelerated_coverage,
        **accelerated_coverage,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "release snapshot frozen",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    print(f"Wrote freeze release report: {out_path}")


if __name__ == "__main__":
    main()
