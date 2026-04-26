from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_freeze_release_snapshot_carries_accelerated_coverage(tmp_path: Path) -> None:
    source_dir = tmp_path / "phase1"
    release_dir = source_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        source_dir / "commercial_readiness_report.json",
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
            "inputs": {"forbid_toy_cases": True},
        },
    )
    _write_json(
        source_dir / "real_source_multi_gate_report.json",
        {"contract_pass": True, "checks": {"all_real_source_pass": True, "all_toy_free_pass": True}},
    )
    _write_json(
        source_dir / "nonlinear_frame_engine_report.json",
        {
            "contract_pass": True,
            "checks": {
                "rust_backend_used_pass": True,
                "all_cases_converged": True,
                "drift_p95_pass": True,
                "base_shear_p95_pass": True,
                "top_disp_p95_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "nonlinear_pushover_stress_report.json",
        {
            "contract_pass": True,
            "checks": {
                "all_cases_converged": True,
                "plasticity_triggered_all_cases": True,
                "collapse_path_pass": True,
                "min_plastic_story_count_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "nonlinear_ndtha_stress_report.json",
        {
            "contract_pass": True,
            "checks": {
                "all_cases_converged": True,
                "pdelta_enabled_pass": True,
                "dynamic_reversal_pass": True,
                "rust_backend_used_pass": True,
                "plasticity_triggered_all_cases": True,
                "min_plastic_story_count_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "phase3_megastructure_pipeline_report.json",
        {"contract_pass": True, "checks": {"shell_beam_mix_pass": True, "gpu_strict_pass": True, "real_source_verified": True}},
    )
    _write_json(source_dir / "opensees_topology_report.json", {"contract_pass": True, "checks": {"shell_beam_mix_pass": True}})
    _write_json(source_dir / "scaleout_io_profile_report.json", {"contract_pass": True, "checks": {"gpu_strict_pass": True}})
    _write_json(
        release_dir / "release_registry.json",
        {
            "contract_pass": True,
            "checks": {"signature_verified_pass": True},
            "summary": {
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                "authority_catalog_diff_change_count": 1,
                "authority_catalog_routing_warning_active": True,
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
                "pbd_dynamic_hinge_refresh_ready": True,
                "pbd_hinge_state_mode": "computed_member_local_hinge_refresh",
                "pbd_hinge_refresh_reason": "dynamic hinge refresh attached",
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
                "panel_zone_constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
                "panel_zone_constructability_reason": "3d panel-zone clash artifact attached",
                "panel_zone_proxy_candidate_count": 1,
                "panel_zone_source_artifact_kind": "design_optimization_dataset_npz",
                "panel_zone_source_artifact_path": "implementation/phase1/panel_zone_clash_artifact.json",
                "panel_zone_source_contract_mode": "true_3d_clash_and_anchorage_verified",
                "panel_zone_source_valid_row_counts": {"panel_zone_joint_geometry_3d": 1},
                "panel_zone_source_overlap_member_counts": {"panel_zone_joint_geometry_3d": 1},
                "panel_zone_source_candidate_scan_modes": {"panel_zone_joint_geometry_3d": "npz_full"},
                "panel_zone_validated_source_row_count_total": 3,
                "panel_zone_validated_source_overlap_member_count_min": 1,
                "foundation_optimization_ready": True,
                "foundation_member_type_present": True,
                "foundation_member_type_count": 7,
                "foundation_optimization_mode": "active_foundation_member_optimization",
                "foundation_optimization_reason": "foundation optimization artifact attached",
                "foundation_scope_source": "dataset_summary",
                "foundation_artifact_scan_mode": "npz_full",
                "upstream_foundation_label_count": 5,
                "raw_source_foundation_label_count": 3,
                "upstream_foundation_provenance_mode": "dataset_scope_only",
                "wind_tunnel_raw_mapping_ready": True,
                "wind_tunnel_mapping_mode": "raw_hffb_node_pressure_mapping",
                "wind_tunnel_mapping_reason": "raw wind tunnel mapping artifact attached",
            },
            "registry_body": {
                "accelerated_coverage_provenance": {
                    "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                    "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                    "comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                    "comparable_reference_strict_design_opt_cost_smoke": True,
                    "authority_catalog_diff_change_count": 1,
                    "authority_catalog_routing_warning_active": True,
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
        },
    )

    out = release_dir / "freeze_release_report.json"
    latest = release_dir / "phase3_nightly_latest.json"
    cmd = [
        sys.executable,
        "implementation/phase1/freeze_release_snapshot.py",
        "--source-dir",
        str(source_dir),
        "--release-dir",
        str(release_dir),
        "--artifact-files",
        "commercial_readiness_report.json,release/release_registry.json",
        "--latest-pointer",
        str(latest),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert report["measured_chain_comparable_reference_strict_design_opt_cost_smoke"] is True
    assert report["authority_catalog_diff_change_count"] == 1
    assert report["authority_catalog_routing_warning_active"] is True
    assert report["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert report["mgt_export_rebar_delivery_mode"] == "structured_sidecar_only"
    assert report["mgt_export_connection_detailing_direct_patch_eligible_change_count"] == 2
    assert report["mgt_export_detailing_direct_patch_eligible_change_count"] == 1
    assert report["mgt_export_group_local_rebar_payload_available_count"] == 0
    assert report["mgt_export_patched_material_row_count"] == 0
    assert report["mgt_export_cloned_material_count"] == 0
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
    assert report["mgt_export_delivery_boundary"] == (
        "direct_patch=beam_section=1, slab_thickness=2, wall_thickness=5 | "
        "sidecar=connection_detailing=3, detailing=4, rebar=5 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert report["mgt_export_evidence_model"] == "direct_patch_plus_structured_sidecar"
    assert report["pbd_dynamic_hinge_refresh_ready"] is True
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
    assert report["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert report["panel_zone_validated_source_row_count_total"] == 3
    assert report["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert report["foundation_optimization_ready"] is True
    assert report["foundation_scope_source"] == "dataset_summary"
    assert report["raw_source_foundation_label_count"] == 3
    assert report["wind_tunnel_raw_mapping_ready"] is True

    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_payload["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert latest_payload["measured_chain_comparable_reference_strict_design_opt_cost_smoke"] is True
    assert latest_payload["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert latest_payload["mgt_export_rebar_delivery_mode"] == "structured_sidecar_only"
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
    assert latest_payload["pbd_dynamic_hinge_refresh_ready"] is True
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
    assert latest_payload["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert latest_payload["panel_zone_validated_source_row_count_total"] == 3
    assert latest_payload["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert latest_payload["foundation_optimization_ready"] is True
    assert latest_payload["foundation_scope_source"] == "dataset_summary"
    assert latest_payload["raw_source_foundation_label_count"] == 3
    assert latest_payload["wind_tunnel_raw_mapping_ready"] is True
    manifest = json.loads((Path(latest_payload["path"]) / "snapshot_manifest.json").read_text(encoding="utf-8"))
    assert manifest["accelerated_coverage"]["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert manifest["accelerated_coverage"]["authority_catalog_diff_change_count"] == 1
    assert manifest["accelerated_coverage"]["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert manifest["accelerated_coverage"]["mgt_export_group_local_rebar_payload_available_count"] == 0
    assert manifest["accelerated_coverage"]["mgt_export_patched_material_row_count"] == 0
    assert manifest["accelerated_coverage"]["mgt_export_cloned_material_count"] == 0
    assert manifest["accelerated_coverage"]["mgt_export_audit_review_followup_item_count"] == 2
    assert manifest["accelerated_coverage"]["mgt_export_audit_review_followup_action_label"] == "close_packet=1, wait_for_review=1"
    assert manifest["accelerated_coverage"]["mgt_export_audit_review_followup_owner_label"] == "licensed_engineer=1, none=1"
    assert manifest["accelerated_coverage"]["mgt_export_audit_review_followup_status_label"] == "approved=1, pending_review=1"
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_template_item_count"] == 2
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert manifest["accelerated_coverage"]["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert manifest["accelerated_coverage"]["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert manifest["accelerated_coverage"]["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert manifest["accelerated_coverage"]["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_runner_apply_live"] is False
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_runner_live_applied"] is False
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert manifest["accelerated_coverage"]["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert manifest["accelerated_coverage"]["pbd_resolved_ndtha_report"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json"
    assert manifest["accelerated_coverage"]["pbd_resolved_ndtha_response_npz"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz"
    assert manifest["accelerated_coverage"]["pbd_ndtha_response_fallback_used"] is True
    assert manifest["accelerated_coverage"]["pbd_ndtha_response_coverage_count"] == 7
    assert manifest["accelerated_coverage"]["pbd_response_source_label"] == (
        "resolved_report=implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json | "
        "response_npz=implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz | "
        "fallback_used=True | coverage=7"
    )
    assert manifest["pbd_response_source"]["resolved_ndtha_report"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json"
    assert manifest["pbd_response_source"]["fallback_used"] is True
    assert manifest["accelerated_coverage"]["mgt_export_delivery_boundary"] == (
        "direct_patch=beam_section=1, slab_thickness=2, wall_thickness=5 | "
        "sidecar=connection_detailing=3, detailing=4, rebar=5 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert manifest["accelerated_coverage"]["pbd_dynamic_hinge_refresh_ready"] is True
    assert manifest["accelerated_coverage"]["pbd_hinge_refresh_artifact_present"] is True
    assert manifest["accelerated_coverage"]["pbd_hinge_refresh_overlap_member_count"] == 3
    assert manifest["accelerated_coverage"]["pbd_hinge_refresh_rebar_sensitive_member_count"] == 3
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_gate_pass"] is True
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_fixture_regression_pass"] is True
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_alignment_pass"] is True
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_asset_count"] == 5
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_train_count"] == 2
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_val_count"] == 2
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_holdout_count"] == 1
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_rebar_sensitive_count"] == 1
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_confinement_sensitive_count"] == 1
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_fixture_count"] == 5
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_fixture_min_point_count"] == 449
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert manifest["accelerated_coverage"]["pbd_hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert manifest["accelerated_coverage"]["panel_zone_3d_clash_ready"] is True
    assert manifest["accelerated_coverage"]["panel_zone_internal_engine_complete"] is True
    assert manifest["accelerated_coverage"]["panel_zone_external_validation_pending"] is True
    assert manifest["accelerated_coverage"]["panel_zone_validation_boundary"] == "external_validation_only"
    assert manifest["accelerated_coverage"]["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert manifest["accelerated_coverage"]["panel_zone_validated_source_row_count_total"] == 3
    assert manifest["accelerated_coverage"]["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert manifest["accelerated_coverage"]["foundation_optimization_ready"] is True
    assert manifest["accelerated_coverage"]["foundation_scope_source"] == "dataset_summary"
    assert manifest["accelerated_coverage"]["raw_source_foundation_label_count"] == 3
    assert manifest["accelerated_coverage"]["wind_tunnel_raw_mapping_ready"] is True


def test_freeze_release_snapshot_manifest_includes_new_nightly_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "phase1"
    release_dir = source_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        source_dir / "commercial_readiness_report.json",
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
            "inputs": {"forbid_toy_cases": True},
        },
    )
    _write_json(
        source_dir / "real_source_multi_gate_report.json",
        {"contract_pass": True, "checks": {"all_real_source_pass": True, "all_toy_free_pass": True}},
    )
    _write_json(
        source_dir / "nonlinear_frame_engine_report.json",
        {
            "contract_pass": True,
            "checks": {
                "rust_backend_used_pass": True,
                "all_cases_converged": True,
                "drift_p95_pass": True,
                "base_shear_p95_pass": True,
                "top_disp_p95_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "nonlinear_pushover_stress_report.json",
        {
            "contract_pass": True,
            "checks": {
                "all_cases_converged": True,
                "plasticity_triggered_all_cases": True,
                "collapse_path_pass": True,
                "min_plastic_story_count_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "nonlinear_ndtha_stress_report.json",
        {
            "contract_pass": True,
            "checks": {
                "all_cases_converged": True,
                "pdelta_enabled_pass": True,
                "dynamic_reversal_pass": True,
                "rust_backend_used_pass": True,
                "plasticity_triggered_all_cases": True,
                "min_plastic_story_count_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "phase3_megastructure_pipeline_report.json",
        {"contract_pass": True, "checks": {"shell_beam_mix_pass": True, "gpu_strict_pass": True, "real_source_verified": True}},
    )
    _write_json(source_dir / "opensees_topology_report.json", {"contract_pass": True, "checks": {"shell_beam_mix_pass": True}})
    _write_json(source_dir / "scaleout_io_profile_report.json", {"contract_pass": True, "checks": {"gpu_strict_pass": True}})
    _write_json(
        release_dir / "release_registry.json",
        {
            "contract_pass": True,
            "checks": {"signature_verified_pass": True},
            "summary": {"deployment_model": "engineer_in_the_loop_accelerated_coverage"},
            "registry_body": {"accelerated_coverage_provenance": {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}},
        },
    )

    _write_json(source_dir / "pbd_hinge_refresh_report.json", {"contract_pass": True})
    _write_json(source_dir / "panel_zone_clash_report.json", {"contract_pass": True})
    _write_json(source_dir / "wind_tunnel_raw_mapping_report.json", {"contract_pass": True})
    _write_json(release_dir / "release_gap_report.json", {"contract_pass": True, "reason_code": "COVERED"})
    (release_dir / "release_gap_report.md").write_text("# gap report\n", encoding="utf-8")
    (release_dir / "release_gap_smoke_history.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (release_dir / "release_gap_measured_chain_categories.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    _write_json(release_dir / "design_optimization" / "foundation_optimization_report.json", {"contract_pass": True})
    _write_json(release_dir / "committee_review" / "committee_review_package_report.json", {"contract_pass": True})
    _write_json(release_dir / "committee_review" / "committee_summary.json", {"contract_pass": True})
    _write_json(release_dir / "committee_review" / "authority_catalog_routing_diff.json", {"change_count": 0})
    (release_dir / "signing").mkdir(parents=True, exist_ok=True)
    (release_dir / "signing" / "release_registry_ed25519.pub.pem").write_text("pubkey\n", encoding="utf-8")
    (release_dir / "signing" / "release_registry.signature.b64").write_text("sig\n", encoding="utf-8")
    _write_json(source_dir / "ci_gate_report.json", {"all_pass": True})
    _write_json(source_dir / "static_artifact_validation_report.json", {"pass": True})
    _write_json(source_dir / "ci_artifact_manifest.json", {"contract_pass": True})

    out = release_dir / "freeze_release_report.json"
    latest = release_dir / "phase3_nightly_latest.json"
    artifact_files = ",".join(
        [
            "pbd_hinge_refresh_report.json",
            "panel_zone_clash_report.json",
            "wind_tunnel_raw_mapping_report.json",
            "release/release_gap_report.json",
            "release/release_gap_report.md",
            "release/release_gap_smoke_history.png",
            "release/release_gap_measured_chain_categories.png",
            "release/design_optimization/foundation_optimization_report.json",
        ]
    )
    cmd = [
        sys.executable,
        "implementation/phase1/freeze_release_snapshot.py",
        "--source-dir",
        str(source_dir),
        "--release-dir",
        str(release_dir),
        "--artifact-files",
        artifact_files,
        "--latest-pointer",
        str(latest),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    manifest = json.loads((Path(latest_payload["path"]) / "snapshot_manifest.json").read_text(encoding="utf-8"))
    manifest_files = {row["file"] for row in manifest["files"]}
    assert "pbd_hinge_refresh_report.json" in manifest_files
    assert "panel_zone_clash_report.json" in manifest_files
    assert "wind_tunnel_raw_mapping_report.json" in manifest_files
    assert "release/release_gap_report.json" in manifest_files
    assert "release/release_gap_report.md" in manifest_files
    assert "release/release_gap_smoke_history.png" in manifest_files
    assert "release/release_gap_measured_chain_categories.png" in manifest_files
    assert "release/design_optimization/foundation_optimization_report.json" in manifest_files
