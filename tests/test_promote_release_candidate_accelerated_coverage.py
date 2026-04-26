from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _green_report() -> dict:
    return {"contract_pass": True, "reason_code": "PASS"}


def test_promote_release_candidate_carries_accelerated_coverage(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    snapshot_dir = release_dir / "phase3_nightly_hardening_20260315T000000Z"
    (snapshot_dir / "release").mkdir(parents=True, exist_ok=True)

    for rel in [
        "ci_gate_report.json",
        "phase3_megastructure_pipeline_report.json",
        "static_artifact_validation_report.json",
        "commercial_readiness_report.json",
        "real_source_multi_gate_report.json",
        "nonlinear_frame_engine_report.json",
        "nonlinear_pushover_stress_report.json",
        "nonlinear_ndtha_stress_report.json",
        "nightly_10m_repro_report.json",
    ]:
        _write_json(snapshot_dir / rel, _green_report())

    _write_json(
        snapshot_dir / "snapshot_manifest.json",
        {"release_policy": {"policy_pass": True}},
    )
    _write_json(
        snapshot_dir / "release" / "release_registry.json",
        {
            "summary": {
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                "authority_catalog_diff_change_count": 0,
                "authority_catalog_routing_warning_active": False,
                "pbd_resolved_ndtha_report": "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json",
                "pbd_resolved_ndtha_response_npz": "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz",
                "pbd_ndtha_response_fallback_used": True,
                "pbd_ndtha_response_coverage_count": 7,
                "mgt_export_support_mode": "bounded_patch_subset",
                "mgt_export_direct_patch_change_count": 7,
                "mgt_export_direct_patch_action_family_label": "beam_section=1, slab_thickness=2, wall_thickness=5",
                "mgt_export_instruction_sidecar_change_count": 12,
                "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=3, detailing=4, rebar=5",
                "mgt_export_rebar_payload_namespace_mode": "material_level_only",
                "mgt_export_rebar_payload_material_level_namespace_present": True,
                "mgt_export_rebar_payload_group_local_namespace_present": False,
                "mgt_export_group_local_rebar_payload_available_count": 0,
                "mgt_export_group_local_rebar_payload_row_count": 0,
                "mgt_export_rebar_direct_patch_eligible_change_count": 0,
                "mgt_export_patched_material_row_count": 0,
                "mgt_export_cloned_material_count": 0,
                "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=2, mixed_material_scope=4",
                "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=5, direct_group_id=1",
                "mgt_export_rebar_delivery_mode": "structured_sidecar_only",
                "mgt_export_connection_detailing_direct_patch_eligible_change_count": 2,
                "mgt_export_detailing_direct_patch_eligible_change_count": 1,
                "mgt_export_connection_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                "mgt_export_detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
                "mgt_export_evidence_model": "direct_patch_plus_structured_sidecar",
                "mgt_export_audit_review_followup_item_count": 2,
                "mgt_export_audit_review_followup_open_item_count": 1,
                "mgt_export_audit_review_followup_closed_item_count": 1,
                "mgt_export_audit_review_followup_action_label": "close_packet=1, wait_for_review=1",
                "mgt_export_audit_review_followup_owner_label": "licensed_engineer=1, none=1",
                "mgt_export_audit_review_followup_status_label": "approved=1, pending_review=1",
                "mgt_export_audit_review_followup_mode": "queue_status_projected_followup_actions",
                "audit_review_decision_batch_template_item_count": 2,
                "audit_review_decision_batch_template_current_status_label": "pending_review=2",
                "audit_review_decision_batch_template_review_owner_label": "licensed_engineer=2",
                "audit_review_decision_batch_template_review_priority_label": "high=1, medium=1",
                "external_benchmark_submission_preview_approve_all_reason_code": "PASS_START_NOW_FULL",
                "external_benchmark_submission_preview_approve_all_ready_full": True,
                "external_benchmark_submission_preview_approve_all_pending_count": 0,
                "external_benchmark_submission_preview_approve_all_open_revision_count": 0,
                "external_benchmark_submission_preview_reject_one_reason_code": "ERR_ARCHITECTURE_BLOCKERS",
                "external_benchmark_submission_preview_reject_one_ready_full": False,
                "external_benchmark_submission_preview_reject_one_pending_count": 0,
                "external_benchmark_submission_preview_reject_one_open_revision_count": 1,
                "external_benchmark_submission_preview_reject_one_blocker_label": "audit_review_resolution_has_open_revisions",
                "audit_review_decision_batch_runner_reason_code": "PASS",
                "audit_review_decision_batch_runner_apply_live": False,
                "audit_review_decision_batch_runner_live_applied": False,
                "audit_review_decision_batch_runner_preview_reason_code": "PASS_START_NOW_FULL",
                "audit_review_decision_batch_runner_preview_ready_full": True,
                "audit_review_decision_batch_runner_preview_pending_count": 0,
                "audit_review_decision_batch_runner_preview_open_revision_count": 0,
                "audit_review_decision_batch_runner_live_preview_reason_code": "PASS_START_NOW_FULL",
                "pbd_hinge_refresh_artifact_present": True,
                "pbd_hinge_refresh_artifact_kind": "hinge_refresh_source_json",
                "pbd_hinge_refresh_source_mode": "rebar_sensitive_member_local_refresh",
                "pbd_hinge_refresh_overlap_member_count": 3,
                "pbd_hinge_refresh_rebar_sensitive_member_count": 3,
                "pbd_hinge_benchmark_gate_pass": True,
                "pbd_hinge_benchmark_fixture_regression_pass": True,
                "pbd_hinge_benchmark_alignment_pass": True,
                "pbd_hinge_benchmark_asset_count": 5,
                "pbd_hinge_benchmark_train_count": 2,
                "pbd_hinge_benchmark_val_count": 2,
                "pbd_hinge_benchmark_holdout_count": 1,
                "pbd_hinge_benchmark_rebar_sensitive_count": 1,
                "pbd_hinge_benchmark_confinement_sensitive_count": 1,
                "pbd_hinge_benchmark_fixture_count": 5,
                "pbd_hinge_benchmark_fixture_min_point_count": 449,
                "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": 0.03662513089005235,
                "pbd_hinge_benchmark_alignment_refresh_column_row_count": 5,
                "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": 5,
                "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": 0.0127,
                "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": 0.0603,
                "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": 0.064,
                "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": 0.074,
                "panel_zone_3d_clash_ready": True,
                "panel_zone_internal_engine_complete": True,
                "panel_zone_external_validation_pending": True,
                "panel_zone_validation_boundary": "external_validation_only",
                "panel_zone_source_contract_mode": "true_3d_clash_and_anchorage_verified",
                "panel_zone_validated_source_row_count_total": 3,
                "panel_zone_validated_source_overlap_member_count_min": 1,
                "foundation_scope_source": "dataset_summary",
                "raw_source_foundation_label_count": 3,
            }
        },
    )

    nightly_pointer = release_dir / "phase3_nightly_latest.json"
    _write_json(
        nightly_pointer,
        {
            "snapshot": snapshot_dir.name,
            "path": str(snapshot_dir),
        },
    )
    pr_ci = tmp_path / "ci_gate_report.json"
    _write_json(pr_ci, {"all_pass": True, "reason_code": "PASS"})

    out = release_dir / "release_candidate_promotion_report.json"
    latest_rc = release_dir / "release_candidate_latest.json"
    hold_manifest = release_dir / "hold_review_manifest.json"
    hold_packet = release_dir / "hold_review_packet.md"
    hold_packet_pdf = release_dir / "hold_review_packet.pdf"
    hold_ack = release_dir / "hold_review_ack.json"
    cmd = [
        sys.executable,
        "implementation/phase1/promote_release_candidate.py",
        "--release-dir",
        str(release_dir),
        "--nightly-pointer",
        str(nightly_pointer),
        "--pr-ci",
        str(pr_ci),
        "--out",
        str(out),
        "--latest-rc-pointer",
        str(latest_rc),
        "--hold-review-manifest",
        str(hold_manifest),
        "--hold-review-packet-md",
        str(hold_packet),
        "--hold-review-packet-pdf",
        str(hold_packet_pdf),
        "--hold-review-ack-json",
        str(hold_ack),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert report["measured_chain_rolling_selection_mode"] == "current_pipeline_comparable_full_chain_pass"
    assert report["measured_chain_comparable_reference_strict_design_opt_cost_smoke"] is True
    assert report["authority_catalog_diff_change_count"] == 0
    assert report["authority_catalog_routing_warning_active"] is False
    assert report["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert report["mgt_export_rebar_delivery_mode"] == "structured_sidecar_only"
    assert report["mgt_export_connection_detailing_direct_patch_eligible_change_count"] == 2
    assert report["mgt_export_detailing_direct_patch_eligible_change_count"] == 1
    assert report["mgt_export_group_local_rebar_payload_available_count"] == 0
    assert report["mgt_export_patched_material_row_count"] == 0
    assert report["mgt_export_cloned_material_count"] == 0
    assert report["mgt_export_audit_review_followup_item_count"] == 2
    assert report["mgt_export_audit_review_followup_action_label"] == "close_packet=1, wait_for_review=1"
    assert report["mgt_export_audit_review_followup_owner_label"] == "licensed_engineer=1, none=1"
    assert report["mgt_export_audit_review_followup_status_label"] == "approved=1, pending_review=1"
    assert report["audit_review_decision_batch_template_item_count"] == 2
    assert report["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert report["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert report["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert report["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert report["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert report["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert report["audit_review_decision_batch_runner_apply_live"] is False
    assert report["audit_review_decision_batch_runner_live_applied"] is False
    assert report["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert report["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert report["pbd_resolved_ndtha_report"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json"
    assert report["pbd_resolved_ndtha_response_npz"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz"
    assert report["pbd_ndtha_response_fallback_used"] is True
    assert report["pbd_ndtha_response_coverage_count"] == 7
    assert report["pbd_response_source_label"] == (
        "resolved_report=implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json | "
        "response_npz=implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz | "
        "fallback_used=True | coverage=7"
    )
    assert report["pbd_response_source"]["resolved_ndtha_report"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json"
    assert report["pbd_response_source"]["fallback_used"] is True
    assert report["mgt_export_delivery_boundary"] == (
        "direct_patch=beam_section=1, slab_thickness=2, wall_thickness=5 | "
        "sidecar=connection_detailing=3, detailing=4, rebar=5 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert report["pbd_hinge_refresh_artifact_present"] is True
    assert report["pbd_hinge_refresh_overlap_member_count"] == 3
    assert report["pbd_hinge_refresh_rebar_sensitive_member_count"] == 3
    assert report["pbd_hinge_benchmark_gate_pass"] is True
    assert report["pbd_hinge_benchmark_fixture_regression_pass"] is True
    assert report["pbd_hinge_benchmark_alignment_pass"] is True
    assert report["pbd_hinge_benchmark_asset_count"] == 5
    assert report["pbd_hinge_benchmark_train_count"] == 2
    assert report["pbd_hinge_benchmark_val_count"] == 2
    assert report["pbd_hinge_benchmark_holdout_count"] == 1
    assert report["pbd_hinge_benchmark_rebar_sensitive_count"] == 1
    assert report["pbd_hinge_benchmark_confinement_sensitive_count"] == 1
    assert report["pbd_hinge_benchmark_fixture_count"] == 5
    assert report["pbd_hinge_benchmark_fixture_min_point_count"] == 449
    assert report["pbd_hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert report["pbd_hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert report["panel_zone_3d_clash_ready"] is True
    assert report["panel_zone_internal_engine_complete"] is True
    assert report["panel_zone_external_validation_pending"] is True
    assert report["panel_zone_validation_boundary"] == "external_validation_only"
    assert report["panel_zone_validation_advisory_only"] is True
    assert report["panel_zone_validation_advisory_label"] == "panel_zone_external_validation_only_boundary"
    assert report["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert report["panel_zone_validated_source_row_count_total"] == 3
    assert report["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert report["foundation_scope_source"] == "dataset_summary"
    assert report["raw_source_foundation_label_count"] == 3
    latest_payload = json.loads(latest_rc.read_text(encoding="utf-8"))
    assert latest_payload["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert latest_payload["measured_chain_comparable_reference_strict_design_opt_cost_smoke"] is True
    assert latest_payload["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert latest_payload["mgt_export_connection_detailing_direct_patch_eligible_change_count"] == 2
    assert latest_payload["mgt_export_detailing_direct_patch_eligible_change_count"] == 1
    assert latest_payload["mgt_export_group_local_rebar_payload_available_count"] == 0
    assert latest_payload["mgt_export_patched_material_row_count"] == 0
    assert latest_payload["mgt_export_cloned_material_count"] == 0
    assert latest_payload["audit_review_decision_batch_template_item_count"] == 2
    assert latest_payload["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert latest_payload["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert latest_payload["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert latest_payload["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert latest_payload["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert latest_payload["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert latest_payload["audit_review_decision_batch_runner_apply_live"] is False
    assert latest_payload["audit_review_decision_batch_runner_live_applied"] is False
    assert latest_payload["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert latest_payload["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert latest_payload["mgt_export_delivery_boundary"] == (
        "direct_patch=beam_section=1, slab_thickness=2, wall_thickness=5 | "
        "sidecar=connection_detailing=3, detailing=4, rebar=5 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert latest_payload["pbd_hinge_refresh_artifact_present"] is True
    assert latest_payload["pbd_hinge_refresh_overlap_member_count"] == 3
    assert latest_payload["pbd_hinge_refresh_rebar_sensitive_member_count"] == 3
    assert latest_payload["pbd_hinge_benchmark_gate_pass"] is True
    assert latest_payload["pbd_hinge_benchmark_fixture_regression_pass"] is True
    assert latest_payload["pbd_hinge_benchmark_alignment_pass"] is True
    assert latest_payload["pbd_hinge_benchmark_asset_count"] == 5
    assert latest_payload["pbd_hinge_benchmark_train_count"] == 2
    assert latest_payload["pbd_hinge_benchmark_val_count"] == 2
    assert latest_payload["pbd_hinge_benchmark_holdout_count"] == 1
    assert latest_payload["pbd_hinge_benchmark_rebar_sensitive_count"] == 1
    assert latest_payload["pbd_hinge_benchmark_confinement_sensitive_count"] == 1
    assert latest_payload["pbd_hinge_benchmark_fixture_count"] == 5
    assert latest_payload["pbd_hinge_benchmark_fixture_min_point_count"] == 449
    assert latest_payload["pbd_hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert latest_payload["pbd_hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert latest_payload["panel_zone_3d_clash_ready"] is True
    assert latest_payload["panel_zone_internal_engine_complete"] is True
    assert latest_payload["panel_zone_external_validation_pending"] is True
    assert latest_payload["panel_zone_validation_boundary"] == "external_validation_only"
    assert latest_payload["panel_zone_validation_advisory_only"] is True
    assert latest_payload["panel_zone_validation_advisory_label"] == "panel_zone_external_validation_only_boundary"
    assert latest_payload["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert latest_payload["panel_zone_validated_source_row_count_total"] == 3
    assert latest_payload["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert latest_payload["foundation_scope_source"] == "dataset_summary"
    assert latest_payload["raw_source_foundation_label_count"] == 3
    manifest_payload = json.loads(hold_manifest.read_text(encoding="utf-8"))
    assert manifest_payload["review_required"] is False
    assert manifest_payload["authority_catalog_diff_change_count"] == 0
    ack_payload = json.loads(hold_ack.read_text(encoding="utf-8"))
    assert ack_payload["ack_required"] is False
    assert ack_payload["hold_clearance"]["status"] == "clear_not_required"
    assert ack_payload["licensed_engineer_signoff"]["status"] == "not_required"
    assert len(ack_payload["clearance_evidence"]["evidence_hash_sha256"]) == 64
    assert hold_packet.exists()
    assert hold_packet_pdf.exists()


def test_promote_release_candidate_holds_for_authority_diff(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    snapshot_dir = release_dir / "phase3_nightly_hardening_20260315T000000Z"
    (snapshot_dir / "release").mkdir(parents=True, exist_ok=True)

    for rel in [
        "ci_gate_report.json",
        "phase3_megastructure_pipeline_report.json",
        "static_artifact_validation_report.json",
        "commercial_readiness_report.json",
        "real_source_multi_gate_report.json",
        "nonlinear_frame_engine_report.json",
        "nonlinear_pushover_stress_report.json",
        "nonlinear_ndtha_stress_report.json",
        "nightly_10m_repro_report.json",
    ]:
        _write_json(snapshot_dir / rel, _green_report())

    _write_json(snapshot_dir / "snapshot_manifest.json", {"release_policy": {"policy_pass": True}})
    _write_json(
        snapshot_dir / "release" / "release_registry.json",
        {
            "summary": {
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                "authority_catalog_diff_change_count": 3,
                "authority_catalog_routing_warning_active": True,
                "mgt_export_support_mode": "bounded_patch_subset",
                "mgt_export_direct_patch_change_count": 7,
                "mgt_export_direct_patch_action_family_label": "beam_section=1, slab_thickness=2, wall_thickness=5",
                "mgt_export_instruction_sidecar_change_count": 12,
                "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=3, detailing=4, rebar=5",
                "mgt_export_rebar_payload_namespace_mode": "material_level_only",
                "mgt_export_rebar_payload_material_level_namespace_present": True,
                "mgt_export_rebar_payload_group_local_namespace_present": False,
                "mgt_export_group_local_rebar_payload_row_count": 0,
                "mgt_export_rebar_direct_patch_eligible_change_count": 0,
                "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=2, mixed_material_scope=4",
                "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=5, direct_group_id=1",
                "mgt_export_rebar_delivery_mode": "structured_sidecar_only",
                "mgt_export_connection_detailing_direct_patch_eligible_change_count": 2,
                "mgt_export_detailing_direct_patch_eligible_change_count": 1,
                "mgt_export_connection_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                "mgt_export_detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
                "mgt_export_evidence_model": "direct_patch_plus_structured_sidecar",
            }
        },
    )

    nightly_pointer = release_dir / "phase3_nightly_latest.json"
    _write_json(nightly_pointer, {"snapshot": snapshot_dir.name, "path": str(snapshot_dir)})
    pr_ci = tmp_path / "ci_gate_report.json"
    _write_json(pr_ci, {"all_pass": True, "reason_code": "PASS"})

    out = release_dir / "release_candidate_promotion_report.json"
    latest_rc = release_dir / "release_candidate_latest.json"
    hold_manifest = release_dir / "hold_review_manifest.json"
    hold_packet = release_dir / "hold_review_packet.md"
    hold_packet_pdf = release_dir / "hold_review_packet.pdf"
    hold_ack = release_dir / "hold_review_ack.json"
    cmd = [
        sys.executable,
        "implementation/phase1/promote_release_candidate.py",
        "--release-dir",
        str(release_dir),
        "--nightly-pointer",
        str(nightly_pointer),
        "--pr-ci",
        str(pr_ci),
        "--out",
        str(out),
        "--latest-rc-pointer",
        str(latest_rc),
        "--hold-review-manifest",
        str(hold_manifest),
        "--hold-review-packet-md",
        str(hold_packet),
        "--hold-review-packet-pdf",
        str(hold_packet_pdf),
        "--hold-review-ack-json",
        str(hold_ack),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] == "HOLD_FOR_REVIEW"
    assert report["checks"]["authority_hold_for_review"] is True
    assert report["authority_catalog_diff_change_count"] == 3
    assert not latest_rc.exists()
    manifest_payload = json.loads(hold_manifest.read_text(encoding="utf-8"))
    assert manifest_payload["review_required"] is True
    assert manifest_payload["reason_code"] == "HOLD_FOR_REVIEW"
    assert manifest_payload["authority_catalog_diff_change_count"] == 3
    assert manifest_payload["authority_catalog_routing_diff"]["source"] == "accelerated_coverage_summary_fallback"
    ack_payload = json.loads(hold_ack.read_text(encoding="utf-8"))
    assert ack_payload["ack_required"] is True
    assert ack_payload["engineer_ack"]["status"] == "pending_review"
    assert ack_payload["licensed_engineer_signoff"]["status"] == "pending_signoff"
    assert ack_payload["clearance_evidence"]["status"] == "pending_evidence_review"
    assert hold_packet.exists()
    assert hold_packet_pdf.exists()


def test_promote_release_candidate_repromotes_after_hold_is_cleared(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    snapshot_dir = release_dir / "phase3_nightly_hardening_20260315T000000Z"
    (snapshot_dir / "release").mkdir(parents=True, exist_ok=True)

    for rel in [
        "ci_gate_report.json",
        "phase3_megastructure_pipeline_report.json",
        "static_artifact_validation_report.json",
        "commercial_readiness_report.json",
        "real_source_multi_gate_report.json",
        "nonlinear_frame_engine_report.json",
        "nonlinear_pushover_stress_report.json",
        "nonlinear_ndtha_stress_report.json",
        "nightly_10m_repro_report.json",
    ]:
        _write_json(snapshot_dir / rel, _green_report())

    _write_json(snapshot_dir / "snapshot_manifest.json", {"release_policy": {"policy_pass": True}})
    registry_path = snapshot_dir / "release" / "release_registry.json"
    _write_json(
        registry_path,
        {
            "summary": {
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                "authority_catalog_diff_change_count": 2,
                "authority_catalog_routing_warning_active": True,
                "mgt_export_support_mode": "bounded_patch_subset",
                "mgt_export_direct_patch_change_count": 7,
                "mgt_export_instruction_sidecar_change_count": 12,
                "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=3, detailing=4, rebar=5",
                "mgt_export_rebar_payload_namespace_mode": "material_level_only",
                "mgt_export_rebar_payload_material_level_namespace_present": True,
                "mgt_export_rebar_payload_group_local_namespace_present": False,
                "mgt_export_group_local_rebar_payload_row_count": 0,
                "mgt_export_rebar_direct_patch_eligible_change_count": 0,
                "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=2, mixed_material_scope=4",
                "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=5, direct_group_id=1",
                "mgt_export_rebar_delivery_mode": "structured_sidecar_only",
                "mgt_export_connection_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                "mgt_export_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                "mgt_export_evidence_model": "direct_patch_plus_structured_sidecar",
            }
        },
    )

    nightly_pointer = release_dir / "phase3_nightly_latest.json"
    _write_json(nightly_pointer, {"snapshot": snapshot_dir.name, "path": str(snapshot_dir)})
    pr_ci = tmp_path / "ci_gate_report.json"
    _write_json(pr_ci, {"all_pass": True, "reason_code": "PASS"})

    out = release_dir / "release_candidate_promotion_report.json"
    latest_rc = release_dir / "release_candidate_latest.json"
    hold_manifest = release_dir / "hold_review_manifest.json"
    hold_packet = release_dir / "hold_review_packet.md"
    hold_packet_pdf = release_dir / "hold_review_packet.pdf"
    hold_ack = release_dir / "hold_review_ack.json"
    base_cmd = [
        sys.executable,
        "implementation/phase1/promote_release_candidate.py",
        "--release-dir",
        str(release_dir),
        "--nightly-pointer",
        str(nightly_pointer),
        "--pr-ci",
        str(pr_ci),
        "--out",
        str(out),
        "--latest-rc-pointer",
        str(latest_rc),
        "--hold-review-manifest",
        str(hold_manifest),
        "--hold-review-packet-md",
        str(hold_packet),
        "--hold-review-packet-pdf",
        str(hold_packet_pdf),
        "--hold-review-ack-json",
        str(hold_ack),
    ]

    first = subprocess.run(base_cmd, check=False, capture_output=True, text=True)
    assert first.returncode != 0
    first_report = json.loads(out.read_text(encoding="utf-8"))
    assert first_report["reason_code"] == "HOLD_FOR_REVIEW"
    first_manifest = json.loads(hold_manifest.read_text(encoding="utf-8"))
    assert first_manifest["review_required"] is True
    assert hold_packet.exists()
    assert "Review status: `review_required`" in hold_packet.read_text(encoding="utf-8")
    first_ack = json.loads(hold_ack.read_text(encoding="utf-8"))
    assert first_ack["ack_required"] is True
    assert first_ack["engineer_ack"]["status"] == "pending_review"
    assert not latest_rc.exists()

    _write_json(
        registry_path,
        {
            "summary": {
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                "authority_catalog_diff_change_count": 0,
                "authority_catalog_routing_warning_active": False,
            }
        },
    )

    second = subprocess.run(base_cmd, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    second_report = json.loads(out.read_text(encoding="utf-8"))
    assert second_report["reason_code"] == "PASS"
    second_manifest = json.loads(hold_manifest.read_text(encoding="utf-8"))
    assert second_manifest["review_required"] is False
    assert second_manifest["review_status"] == "clear"
    assert second_manifest["recommended_next_step"] == "promotion_may_proceed"
    second_ack = json.loads(hold_ack.read_text(encoding="utf-8"))
    assert second_ack["ack_required"] is False
    assert second_ack["hold_clearance"]["status"] == "clear_ready_for_record"
    assert second_ack["clearance_evidence"]["status"] == "ready_for_clearance_record"
    packet_text = hold_packet.read_text(encoding="utf-8")
    assert "Review status: `clear`" in packet_text
    assert latest_rc.exists()
    assert hold_packet_pdf.exists()
    latest_payload = json.loads(latest_rc.read_text(encoding="utf-8"))
    assert latest_payload["hold_review_packet_md"].endswith("hold_review_packet.md")
    assert latest_payload["hold_review_packet_pdf"].endswith("hold_review_packet.pdf")
    assert latest_payload["hold_review_ack_json"].endswith("hold_review_ack.json")


def test_promote_release_candidate_uses_row_level_authority_diff_in_packet(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    snapshot_dir = release_dir / "phase3_nightly_hardening_20260315T000000Z"
    (snapshot_dir / "release" / "committee_review").mkdir(parents=True, exist_ok=True)

    for rel in [
        "ci_gate_report.json",
        "phase3_megastructure_pipeline_report.json",
        "static_artifact_validation_report.json",
        "commercial_readiness_report.json",
        "real_source_multi_gate_report.json",
        "nonlinear_frame_engine_report.json",
        "nonlinear_pushover_stress_report.json",
        "nonlinear_ndtha_stress_report.json",
        "nightly_10m_repro_report.json",
    ]:
        _write_json(snapshot_dir / rel, _green_report())

    _write_json(snapshot_dir / "snapshot_manifest.json", {"release_policy": {"policy_pass": True}})
    _write_json(
        snapshot_dir / "release" / "release_registry.json",
        {
            "summary": {
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                "authority_catalog_diff_change_count": 2,
                "authority_catalog_routing_warning_active": True,
            }
        },
    )
    _write_json(
        snapshot_dir / "release" / "committee_review" / "committee_summary.json",
        {
            "residual_holdout_matrix_rows": [
                {
                    "authority_track": "sac",
                    "submodel_family": "SCBF16B",
                    "review_story_zone": "S02/perimeter",
                    "member_family": "beam",
                    "owner": "legacy_solver",
                    "why": "reference row",
                }
            ]
        },
    )
    _write_json(
        snapshot_dir / "release" / "committee_review" / "authority_catalog_routing_diff.json",
        {
            "change_count": 2,
            "added_count": 1,
            "removed_count": 1,
            "unchanged_count": 0,
            "baseline_seeded": False,
            "diff_rows": [
                {
                    "change_type": "added",
                    "authority_track": "sac",
                    "submodel_family": "SCBF16B",
                    "review_story_zone": "S02/perimeter",
                    "member_family": "beam",
                    "owner": "legacy_solver",
                    "why": "benchmark row-level diff",
                }
            ],
        },
    )

    nightly_pointer = release_dir / "phase3_nightly_latest.json"
    _write_json(nightly_pointer, {"snapshot": snapshot_dir.name, "path": str(snapshot_dir)})
    pr_ci = tmp_path / "ci_gate_report.json"
    _write_json(pr_ci, {"all_pass": True, "reason_code": "PASS"})

    out = release_dir / "release_candidate_promotion_report.json"
    hold_manifest = release_dir / "hold_review_manifest.json"
    hold_packet = release_dir / "hold_review_packet.md"
    hold_packet_pdf = release_dir / "hold_review_packet.pdf"
    hold_ack = release_dir / "hold_review_ack.json"
    cmd = [
        sys.executable,
        "implementation/phase1/promote_release_candidate.py",
        "--release-dir",
        str(release_dir),
        "--nightly-pointer",
        str(nightly_pointer),
        "--pr-ci",
        str(pr_ci),
        "--out",
        str(out),
        "--hold-review-manifest",
        str(hold_manifest),
        "--hold-review-packet-md",
        str(hold_packet),
        "--hold-review-packet-pdf",
        str(hold_packet_pdf),
        "--hold-review-ack-json",
        str(hold_ack),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    manifest_payload = json.loads(hold_manifest.read_text(encoding="utf-8"))
    assert manifest_payload["authority_catalog_routing_diff"]["diff_rows"][0]["submodel_family"] == "SCBF16B"
    assert manifest_payload["review_packet_rows"][0]["row_type"] == "authority_catalog_diff"
    assert manifest_payload["review_packet_rows"][0]["change_type"] == "added"
    packet_text = hold_packet.read_text(encoding="utf-8")
    assert "SCBF16B" in packet_text
    assert "benchmark row-level diff" in packet_text
    assert hold_packet_pdf.exists()
