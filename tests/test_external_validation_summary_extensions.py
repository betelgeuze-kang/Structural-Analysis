from pathlib import Path
import json
import subprocess
import sys

from implementation.phase1.prepare_external_validation_submission import (
    _build_bundle,
    _write_external_benchmark_case_onepages,
    _write_summary_html,
    _write_summary_markdown,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "foundation_realish"


def _summary() -> dict:
    return {
        "bundle_id": "unit-test",
        "generated_at": "2026-03-15T00:00:00+00:00",
        "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
        "authority_catalog_diff_change_count": 2,
        "authority_catalog_diff_added_count": 1,
        "authority_catalog_diff_removed_count": 1,
        "authority_catalog_routing_warning_active": True,
        "promotion_reason_code": "PASS",
        "promotion_hold_for_review": False,
        "hold_review_manifest": "implementation/phase1/release/hold_review_manifest.json",
        "hold_review_packet_md": "implementation/phase1/release/hold_review_packet.md",
        "hold_review_packet_pdf": "implementation/phase1/release/hold_review_packet.pdf",
        "hold_review_ack_json": "implementation/phase1/release/hold_review_ack.json",
        "design_optimization_entrypoints": [],
        "design_optimization_entrypoint_groups": [],
        "checks": {
            "nightly_release": "PASS",
            "ci_gate": "PASS",
            "static_validation": "PASS",
            "freeze_release": "PASS",
            "promotion": "PASS",
            "signed_release_registry": "PASS",
            "registry_signature_verified": "PASS",
            "solver_hip_e2e": "PASS",
            "rc_benchmark_lock": "PASS",
            "ndtha_residual_gate": "PASS",
            "committee_review_package": "PASS",
        },
        "metrics": {
            "midas_section_library_summary_line": "MIDAS section-library: ok | 182/183 used | 183 templates | source=midas_parser_derived",
            "material_constitutive_summary_line": "Material constitutive gate: PASS | concrete_damage=yes(matrix=14/14,max=1.000) | cyclic_degradation=yes(matrix=14/14,residual_max=1.914%) | bond_interface=yes(matrix=15/15,bond_max=0.980) | matrix=43/43 | groups=concrete_damage=14/14,cyclic_degradation=14/14,bond_interface=15/15 | coverage=cd[t=3,h=2,s=2],cyc[t=2,h=2,store=2],bond[t=3,h=2,s=2]",
            "surface_interaction_benchmark_summary_line": "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4",
            "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
            "korean_source_ingest_summary_line": (
                "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | seed=4 | topo=1 | native=1 | p0=3"
            ),
            "measured_benchmark_breadth_summary_line": (
                "Measured benchmark breadth: PASS | baseline=2/51 | opensees_delta=6/7 | authority_delta=2/6 | external_delta=10/10 | measured_families=20 | measured_cases=74 | parser_ready=3"
            ),
            "opensees_canonical_breadth_summary_line": (
                "OpenSees canonical breadth: PASS | families=6 | cases=7 | parser_ready=3 | "
                "origins=designsafe_publication=1,github_public=2,global_authority=2,public_lab_download=2"
            ),
            "korean_structural_preview_queue_summary_line": "KR preview queue: PASS | cand=4 | pend=1 | state=open",
            "irregular_structure_summary_line": "Irregular structure track: PASS | families=20 | sources=28 | local_ready=11 | remote_candidates=17 | collected=16 | native_roundtrip_candidates=16 | solver_candidates=11 | ai_candidates=28 | top5=5",
            "irregular_structure_track_summary_line": "Irregular structure track: PASS | families=20 | sources=28 | local_ready=11 | remote_candidates=17 | collected=16 | native_roundtrip_candidates=16 | solver_candidates=11 | ai_candidates=28 | top5=5",
            "irregular_structure_track_pass": True,
            "irregular_structure_family_count": 20,
            "irregular_structure_source_record_count": 28,
            "irregular_structure_local_ready_count": 11,
            "irregular_structure_remote_candidate_count": 17,
            "irregular_structure_collected_count": 16,
            "irregular_structure_native_roundtrip_candidate_count": 16,
            "irregular_structure_solver_benchmark_candidate_count": 11,
            "irregular_structure_ai_learning_candidate_count": 28,
            "irregular_structure_top5_count": 5,
            "irregular_structure_top5_local_ready_count": 1,
            "irregular_structure_top5_remote_needed_count": 4,
            "irregular_structure_top5_family_ids": [
                "transfer_podium_tower",
                "soft_story_podium_tower",
                "torsionally_eccentric_core_tower",
                "setback_tower",
                "reentrant_corner_tower",
            ],
            "irregular_benchmark_execution_summary_line": "Irregular benchmark execution: PASS | ready=1 | blocked=4 | task_count=5 | top5_local_ready=1 | top5_remote_needed=4",
            "irregular_benchmark_execution_ready_task_count": 1,
            "irregular_benchmark_execution_blocked_task_count": 4,
            "irregular_benchmark_execution_task_count": 5,
            "midas_kds_row_provenance_preview_rows": [
                {
                    "combination_name": "gLCB1",
                    "member_id": "C-TST-003",
                    "clause_label": "KDS-MOMENT-Y-001",
                    "baseline_focus_member_id": "27441",
                    "bridge_row_provenance_mode_label": "exact row-level provenance",
                    "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                    "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column",
                },
                {
                    "combination_name": "gLCB1",
                    "member_id": "C-TRN-005",
                    "clause_label": "KDS-MOMENT-Y-001",
                    "baseline_focus_member_id": "27441",
                    "bridge_row_provenance_mode_label": "exact row-level provenance",
                    "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                    "bridge_member_inventory_summary_label": "review=C-TRN-005 | case=C-TRN-005 | baseline=27441 | member_types=column",
                },
            ],
            "midas_kds_row_provenance_clause_filter_rows": [
                {
                    "clause_label": "KDS-MOMENT-Y-001",
                    "row_count": 12,
                    "member_count": 12,
                    "combination_count": 6,
                    "top_member_id": "C-TST-003",
                    "top_dcr_label": "1.216",
                }
            ],
            "midas_kds_row_provenance_member_filter_rows": [
                {
                    "member_id": "C-TST-003",
                    "baseline_focus_member_id": "27441",
                    "row_count": 12,
                    "clause_count": 1,
                    "combination_count": 6,
                    "top_clause_label": "KDS-MOMENT-Y-001",
                }
            ],
            "midas_kds_row_provenance_hazard_filter_rows": [
                {
                    "hazard_type": "seismic",
                    "row_count": 12,
                    "member_count": 12,
                    "clause_count": 1,
                    "combination_count": 6,
                    "top_clause_label": "KDS-MOMENT-Y-001",
                    "top_dcr_label": "1.216",
                }
            ],
            "midas_kds_row_provenance_rule_family_filter_rows": [
                {
                    "rule_family": "strength",
                    "row_count": 12,
                    "member_count": 12,
                    "hazard_count": 1,
                    "combination_count": 6,
                    "top_clause_label": "KDS-MOMENT-Y-001",
                    "top_dcr_label": "1.216",
                }
            ],
            "nightly_smoke_reason_code": "PASS",
            "nightly_smoke_pass_rate": 1.0,
            "nightly_smoke_trial_feasible_rate": 1.0,
            "nightly_smoke_avg_trial_runtime_s": 0.05,
            "nightly_smoke_history_count": 5,
            "nightly_smoke_strict_recommendation": "candidate_for_strict_enable",
            "commercial_grade": "Commercial",
            "deployment_model": "engineer_in_the_loop_accelerated_coverage",
            "accelerated_coverage_target_pct_label": "95-99%",
            "residual_holdout_target_pct_label": "1-5%",
            "estimated_time_saved_pct_label": "90-96%",
            "measured_chain_rolling_total_minutes_mean": 5.06,
            "measured_chain_rolling_sample_count": 7,
            "measured_chain_rolling_total_minutes_range": [4.95, 5.24],
            "measured_chain_total_minutes": 5.24,
            "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
            "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
            "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
            "empirical_smoke_runtime_saved_pct_label": "95.38-96.24%",
            "estimated_time_saved_basis": "empirical_smoke_runtime_reduction x coverage target",
            "engineer_in_loop_accelerated_coverage_ready": True,
            "time_saving_focus": "Automate repetitive heavy-lift analysis and packaging.",
            "full_commercial_replacement_ready": False,
            "external_benchmark_submission_ready_to_start_now": True,
            "external_benchmark_submission_ready_to_start_full_submission_now": False,
            "external_benchmark_submission_reason_code": "PASS_START_NOW_LIMITED",
            "external_benchmark_submission_recommended_start_mode": "start_now_limited_external_benchmark",
            "external_benchmark_submission_recommended_submission_scope": "component_and_system_performance_benchmark_with_review_boundary",
            "external_benchmark_submission_blocker_label": "",
            "external_benchmark_submission_caution_label": "panel_zone_external_validation_only_boundary, audit_review_queue_pending=1",
            "external_benchmark_execution_mode": "limited",
            "external_benchmark_execution_ready_task_count": 10,
            "external_benchmark_execution_blocked_task_count": 2,
            "external_benchmark_execution_review_boundary_pending_count": 2,
            "external_benchmark_execution_review_boundary_resolution_label": "approve_all=PASS_START_NOW_FULL/ready_full=yes; reject_one=ERR_ARCHITECTURE_BLOCKERS/open_revision=1",
            "external_benchmark_execution_review_boundary_owner_label": "licensed_engineer=2",
            "external_benchmark_execution_review_boundary_assignee_label": "unassigned=2",
            "external_benchmark_execution_review_boundary_assignment_status_label": "unassigned=2",
            "external_benchmark_execution_review_boundary_priority_label": "high=1, medium=1",
            "external_benchmark_execution_review_boundary_family_label": "connection_detailing=1, detailing=1",
            "external_benchmark_execution_review_boundary_change_count_total": 11,
            "external_benchmark_execution_review_boundary_followup_action_label": "wait_for_review=2",
            "external_benchmark_execution_review_boundary_sla_state_label": "within_sla=2",
            "external_benchmark_execution_review_boundary_age_bucket_label": "lt_24h=2",
            "external_benchmark_execution_review_boundary_overdue_count": 0,
            "external_benchmark_execution_review_boundary_oldest_open_age_hours": 5.5,
            "external_benchmark_execution_status_mode": "planned_only",
            "external_benchmark_execution_executable_task_count": 10,
            "external_benchmark_execution_planned_task_count": 10,
            "external_benchmark_execution_in_progress_task_count": 0,
            "external_benchmark_execution_completed_task_count": 0,
            "external_benchmark_execution_failed_task_count": 0,
            "external_benchmark_execution_finished_task_count": 0,
            "external_benchmark_execution_completion_ratio": 0.0,
            "audit_review_decision_batch_template_item_count": 2,
            "audit_review_decision_batch_template_current_status_label": "pending_review=2",
            "audit_review_decision_batch_template_review_owner_label": "licensed_engineer=2",
            "audit_review_decision_batch_template_review_priority_label": "high=1, medium=1",
            "audit_review_decision_batch_attested_example_count": 2,
            "audit_review_decision_batch_attested_example_preview_label": "approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS",
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
            "pbd_dynamic_hinge_refresh_ready": False,
            "pbd_hinge_state_mode": "proxy_only_hinge_visualization",
            "pbd_hinge_refresh_reason": "PBD review still publishes hinge proxy artifacts.",
            "pbd_hinge_refresh_artifact_present": True,
            "pbd_hinge_refresh_artifact_kind": "hinge_refresh_source_json",
            "pbd_hinge_refresh_source_mode": "proxy_only_dataset_heuristic",
            "pbd_hinge_refresh_overlap_member_count": 0,
            "pbd_hinge_refresh_rebar_sensitive_member_count": 0,
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
            "panel_zone_3d_clash_ready": False,
            "panel_zone_constructability_mode": "scalar_proxy_hard_gate_only",
            "panel_zone_constructability_reason": "No 3D panel-zone clash artifact is attached.",
            "panel_zone_proxy_candidate_count": 45,
            "panel_zone_source_artifact_kind": "design_optimization_dataset_npz",
            "panel_zone_source_contract_mode": "topology_capable_proxy_scan",
            "panel_zone_instruction_sidecar_present": True,
            "panel_zone_instruction_sidecar_change_count": 17,
            "panel_zone_instruction_sidecar_candidate_overlap_mode": "section_signature",
            "panel_zone_instruction_sidecar_overlap_row_count": 4,
            "panel_zone_instruction_sidecar_overlap_member_count": 11,
            "panel_zone_instruction_sidecar_overlap_group_count": 3,
            "panel_zone_instruction_sidecar_evidence_model": "direct_patch_plus_structured_sidecar",
            "panel_zone_instruction_sidecar_rebar_delivery_mode": "structured_sidecar_only",
            "panel_zone_source_valid_row_counts": {
                "panel_zone_joint_geometry_3d": 2,
                "panel_zone_rebar_anchorage_3d": 1,
                "panel_zone_clash_verification_3d": 2,
            },
            "panel_zone_source_overlap_member_counts": {
                "panel_zone_joint_geometry_3d": 1,
                "panel_zone_rebar_anchorage_3d": 1,
                "panel_zone_clash_verification_3d": 1,
            },
            "panel_zone_source_candidate_scan_modes": {
                "panel_zone_joint_geometry_3d": "npz_full",
                "panel_zone_rebar_anchorage_3d": "npz_full",
                "panel_zone_clash_verification_3d": "npz_full",
            },
            "panel_zone_source_bundle_modes": {
                "panel_zone_joint_geometry_3d": "nested_solver_export",
                "panel_zone_rebar_anchorage_3d": "nested_solver_export",
                "panel_zone_clash_verification_3d": "nested_solver_export",
            },
            "panel_zone_source_upstream_verification_tiers": {
                "panel_zone_joint_geometry_3d": "panel_zone_joint_geometry_3d_topology_projected_validated_source",
                "panel_zone_rebar_anchorage_3d": "panel_zone_rebar_anchorage_3d_topology_projected_validated_source",
                "panel_zone_clash_verification_3d": "panel_zone_clash_verification_3d_topology_projected_validated_source",
            },
            "panel_zone_validated_source_row_count_total": 5,
            "panel_zone_validated_source_overlap_member_count_min": 1,
            "panel_zone_missing_required_sources": [
                "panel_zone_joint_geometry_3d",
                "panel_zone_rebar_anchorage_3d",
                "panel_zone_clash_verification_3d",
            ],
            "panel_zone_solver_verified_inbox_status_mode": "pending_raw_triplet",
            "panel_zone_solver_verified_inbox_has_input": True,
            "panel_zone_solver_verified_pending_input": True,
            "panel_zone_solver_verified_input_mode_detected": "raw_triplet",
            "panel_zone_solver_verified_latest_consume_report_present": True,
            "panel_zone_solver_verified_latest_consume_contract_pass": False,
            "panel_zone_solver_verified_latest_consume_reason_code": "ERR_HANDOFF_FAILED",
            "panel_zone_solver_verified_source_origin_class": "fixture_sample",
            "panel_zone_solver_verified_release_refresh_source_allowed": False,
            "panel_zone_solver_verified_recommended_action": "consume_pending_input",
            "foundation_optimization_ready": False,
            "foundation_member_type_present": False,
            "foundation_member_type_count": 0,
            "foundation_optimization_mode": "rule_engine_present_but_dataset_absent",
            "foundation_optimization_reason": "Active design-optimization dataset has no foundation groups.",
            "foundation_scope_source": "artifact_empty_scan",
            "foundation_artifact_scan_mode": "npz_full_empty",
            "upstream_foundation_label_count": 3,
            "upstream_foundation_provenance_mode": "parsed_model_labels_present",
            "wind_tunnel_raw_mapping_ready": False,
            "wind_tunnel_mapping_mode": "semantic_pressure_binding_only",
            "wind_tunnel_mapping_reason": "No verified raw wind-tunnel mapping artifact is attached.",
            "promotion_reason_code": "PASS",
            "promotion_hold_for_review": False,
            "hold_review_manifest": "implementation/phase1/release/hold_review_manifest.json",
            "hold_review_packet_md": "implementation/phase1/release/hold_review_packet.md",
            "hold_review_packet_pdf": "implementation/phase1/release/hold_review_packet.pdf",
            "hold_review_ack_json": "implementation/phase1/release/hold_review_ack.json",
            "open_gap_p0": 0,
            "open_gap_p1": 1,
            "open_gap_p2": 2,
            "midas_element_rows_total": 100,
            "midas_element_rows_skipped": 0,
            "midas_unknown_row_total": 0,
            "midas_semantic_load_binding_pass": True,
            "midas_use_stld_block_count": 2,
            "midas_semantic_load_case_count": 6,
            "midas_semantic_load_combination_count": 8,
            "midas_bound_nodal_load_row_count": 12,
            "midas_bound_selfweight_row_count": 1,
            "midas_bound_pressure_row_count": 7278,
            "midas_unbound_nodal_load_row_count": 0,
            "midas_unbound_selfweight_row_count": 0,
            "midas_unbound_pressure_row_count": 0,
            "mgt_export_artifact_exists": True,
            "mgt_export_contract_pass": True,
            "mgt_export_support_mode": "bounded_patch_subset",
            "mgt_export_supported_change_count": 2,
            "mgt_export_unsupported_change_count": 5,
            "mgt_export_direct_patch_change_count": 2,
            "mgt_export_direct_patch_action_family_counts": {
                "beam_section": 1,
                "wall_thickness": 1,
            },
            "mgt_export_direct_patch_action_family_label": "beam_section=1, wall_thickness=1",
            "mgt_export_rebar_payload_namespace_mode": "material_level_only",
            "mgt_export_rebar_delivery_mode": "structured_sidecar_only",
            "mgt_export_evidence_model": "direct_patch_plus_structured_sidecar",
            "mgt_export_rebar_payload_material_level_namespace_present": True,
            "mgt_export_rebar_payload_group_local_namespace_present": False,
            "mgt_export_material_level_rebar_payload_row_count": 5,
            "mgt_export_material_level_rebar_payload_available_count": 0,
            "mgt_export_group_local_rebar_payload_row_count": 0,
            "mgt_export_rebar_direct_patch_eligible_change_count": 0,
            "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=1, mixed_material_scope=2",
            "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=1, direct_group_id=2",
            "mgt_export_instruction_sidecar_change_count": 3,
            "mgt_export_instruction_sidecar_action_family_counts": {
                "connection_detailing": 2,
                "detailing": 1,
            },
            "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=2, detailing=1",
            "mgt_export_instruction_sidecar_audit_only_change_count": 2,
            "mgt_export_instruction_sidecar_audit_only_action_family_counts": {
                "connection_detailing": 2,
            },
            "mgt_export_instruction_sidecar_audit_only_action_family_label": "connection_detailing=2",
            "mgt_export_instruction_sidecar_manual_input_change_count": 1,
            "mgt_export_instruction_sidecar_manual_input_action_family_counts": {
                "detailing": 1,
            },
            "mgt_export_instruction_sidecar_manual_input_action_family_label": "detailing=1",
            "mgt_export_audit_review_manifest_change_count": 2,
            "mgt_export_audit_review_manifest_action_family_counts": {
                "connection_detailing": 2,
            },
            "mgt_export_audit_review_manifest_action_family_label": "connection_detailing=2",
            "mgt_export_audit_review_packet_count": 1,
            "mgt_export_audit_review_packet_action_family_counts": {
                "connection_detailing": 1,
            },
            "mgt_export_audit_review_packet_action_family_label": "connection_detailing=1",
            "mgt_export_audit_review_packet_followup_type_counts": {
                "connection_detailing_audit_after_material_patch": 1,
            },
            "mgt_export_audit_review_packet_followup_type_label": "connection_detailing_audit_after_material_patch=1",
            "mgt_export_audit_review_packet_file_count": 1,
            "mgt_export_audit_review_packet_file_action_family_counts": {
                "connection_detailing": 1,
            },
            "mgt_export_audit_review_packet_file_action_family_label": "connection_detailing=1",
            "mgt_export_audit_review_queue_item_count": 1,
            "mgt_export_audit_review_queue_pending_count": 1,
            "mgt_export_audit_review_queue_acknowledged_count": 0,
            "mgt_export_audit_review_queue_status_counts": {
                "pending_review": 1,
            },
            "mgt_export_audit_review_queue_status_label": "pending_review=1",
            "mgt_export_audit_review_queue_action_family_counts": {
                "connection_detailing": 1,
            },
            "mgt_export_audit_review_queue_action_family_label": "connection_detailing=1",
            "mgt_export_audit_review_followup_item_count": 1,
            "mgt_export_audit_review_followup_open_item_count": 1,
            "mgt_export_audit_review_followup_closed_item_count": 0,
            "mgt_export_audit_review_followup_action_counts": {
                "wait_for_review": 1,
            },
            "mgt_export_audit_review_followup_action_label": "wait_for_review=1",
            "mgt_export_audit_review_followup_owner_counts": {
                "licensed_engineer": 1,
            },
            "mgt_export_audit_review_followup_owner_label": "licensed_engineer=1",
            "mgt_export_audit_review_followup_status_counts": {
                "pending_review": 1,
            },
            "mgt_export_audit_review_followup_status_label": "pending_review=1",
            "mgt_export_audit_review_followup_mode": "queue_status_projected_followup_actions",
            "kds_compliance_rows": 10,
            "kds_member_check_rows": 10,
            "kds_clause_count": 12,
            "ndtha_residual_top_m_max_abs": 0.01,
            "ndtha_residual_drift_pct_max_abs": 0.1,
            "ndtha_residual_fallback_rate": 0.0,
            "registry_artifact_count": 100,
            "design_opt_long_feasible": True,
            "design_opt_long_final_max_dcr": 0.93,
            "design_opt_baseline_constructability_avg": 0.2864,
            "design_opt_final_constructability_avg": 0.2848,
            "design_opt_baseline_detailing_complexity_avg": 0.3575,
            "design_opt_final_detailing_complexity_avg": 0.3564,
            "design_opt_selected_family_mix_label": "beam_section=3, detailing=8, rebar=4, slab_thickness=3",
            "design_opt_selected_dominant_family": "detailing",
            "design_opt_selected_dominant_family_ratio": 0.44,
            "design_opt_selected_family_trend_label": "beam_section=+1, detailing=-2, rebar=-2, slab_thickness=-1",
            "design_opt_previous_dominant_family": "detailing",
            "design_opt_previous_dominant_family_ratio": 0.50,
            "design_opt_preview_supply_family_mix_label": "beam_section=8, detailing=104, rebar=120, slab_thickness=96",
            "design_opt_preview_missing_target_families_label": "wall_thickness, connection_detailing",
            "design_opt_cost_delta": 500.0,
            "design_opt_changed_group_count": 5,
            "design_opt_blocked_action_row_count": 0,
            "design_opt_blocked_illegal_by_mask": 0,
            "design_opt_blocked_illegal_by_mask_family_label": "connection_detailing=3, perimeter_frame=2",
            "design_opt_blocked_no_cost_gain": 0,
            "design_opt_blocked_constructability_hard_gate": 6,
            "design_opt_blocked_constructability_hard_gate_label": "detailing_not_improved_enough=4, congestion_above_hard_limit=2",
            "design_opt_blocked_no_cost_group_count": 0,
            "design_opt_blocked_no_cost_explain_row_count": 0,
            "design_opt_entrypoint_report_count": 7,
            "design_opt_entrypoint_pass_count": 7,
        },
        "midas_kds_row_provenance_preview_rows": [
            {
                "combination_name": "gLCB1",
                "member_id": "C-TST-003",
                "clause_label": "KDS-MOMENT-Y-001",
                "baseline_focus_member_id": "27441",
                "bridge_row_provenance_mode_label": "exact row-level provenance",
                "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column",
            },
            {
                "combination_name": "gLCB1",
                "member_id": "C-TRN-005",
                "clause_label": "KDS-MOMENT-Y-001",
                "baseline_focus_member_id": "27441",
                "bridge_row_provenance_mode_label": "exact row-level provenance",
                "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                "bridge_member_inventory_summary_label": "review=C-TRN-005 | case=C-TRN-005 | baseline=27441 | member_types=column",
            },
        ],
        "derived": {
            "frame_case_count": 1,
            "frame_drift_error_pct_p95": 1.0,
            "frame_top_disp_error_pct_p95": 1.0,
            "wind_case_count": 1,
            "wind_max_drift_pct": 1.0,
            "wind_residual_drift_pct": 0.1,
            "ssi_case_count": 1,
            "ssi_nonlinear_ratio_span": 0.1,
            "ssi_residual_drift_pct": 0.1,
            "design_opt_change_rows": 5,
            "design_opt_long_final_max_dcr": 0.93,
            "design_opt_cost_delta": 500.0,
        },
        "artifacts": {
            "nightly_smoke_history_png": "implementation/phase1/release/release_gap_smoke_history.png",
            "measured_chain_category_png": "implementation/phase1/release/release_gap_measured_chain_category.png",
            "midas_kds_row_provenance_export_json": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json",
            "midas_kds_row_provenance_export_csv": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
            "midas_kds_row_provenance_export_report": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
            "irregular_structure_gate_report_json": "implementation/phase1/irregular_structure_collection_gate_report.json",
            "irregular_structure_source_catalog_json": "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
            "irregular_structure_triage_report_json": "implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
            "irregular_structure_collection_report_json": "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
            "irregular_top5_execution_manifest_json": "implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
            "irregular_benchmark_execution_manifest_json": "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json",
        },
        "korean_native_roundtrip_representative_rows": [
            {
                "structure_type": "housing",
                "source_id": "lh_bucheon_yeokgok_a1_housing_native_baseline",
                "title": "LH Bucheon Yeokgok A1 housing native baseline",
                "lane_label": "public native",
                "structural_system": "wall_frame_housing",
                "receipt_md": "implementation/phase1/release/midas_native_roundtrip/lh_bucheon_yeokgok_a1_housing_native_baseline.diff_receipt.md",
                "receipt_json": "implementation/phase1/release/midas_native_roundtrip/lh_bucheon_yeokgok_a1_housing_native_baseline.diff_receipt.json",
                "type_batch_markdown": "implementation/phase1/release/midas_native_roundtrip/housing.diff_batch.md",
            },
            {
                "structure_type": "public_facility",
                "source_id": "ifc_public_award_structure__structural_preview_candidate",
                "title": "IFC public award structure",
                "lane_label": "public structural preview",
                "structural_system": "ifc_structural_subset",
                "receipt_md": "implementation/phase1/release/midas_native_roundtrip/ifc_public_award_structure.structural_preview_promotion_receipt.md",
                "receipt_json": "implementation/phase1/release/midas_native_roundtrip/ifc_public_award_structure.structural_preview_promotion_receipt.json",
                "type_batch_markdown": "implementation/phase1/release/midas_native_roundtrip/public_facility.diff_batch.md",
            },
        ],
        "residual_holdout_buckets": [
            {"label": "Licensed Engineer Review", "owner": "PE", "relative_share_pct": 50, "absolute_project_pct_range": [0.5, 2.5], "scope": "critical review"}
        ],
        "residual_holdout_detail_rows": [
            {"bucket_label": "Licensed Engineer Review", "detail_axis": "review_story_zone", "detail_value": "S02/perimeter", "owner": "PE", "why": "critical"}
        ],
        "residual_holdout_matrix_rows": [
            {
                "bucket_label": "Legacy Tool Cross-Validation",
                "authority_track": "sac",
                "submodel_family": "SCBF16B",
                "review_story_zone": "S02/perimeter",
                "member_family": "beam",
                "owner": "Legacy solver",
                "why": "benchmark holdout",
            }
        ],
        "nightly_smoke_recent_samples": [
            {"sample_index": 1, "generated_at": "2026-03-15T00:00:00+00:00", "contract_pass": True, "trial_feasible": True, "baseline_runtime_s": 1.2, "trial_runtime_s": 0.05, "trial_max_dcr": 0.93, "trial_action_name": "rebar_down"}
        ],
        "nightly_smoke_trend": {
            "baseline_runtime_first_s": 1.20,
            "baseline_runtime_last_s": 1.25,
            "baseline_runtime_drift_s": 0.05,
            "trial_runtime_first_s": 0.05,
            "trial_runtime_last_s": 0.06,
            "trial_runtime_drift_s": 0.01,
            "baseline_max_dcr_first": 0.93,
            "baseline_max_dcr_last": 0.93,
            "baseline_max_dcr_drift": 0.0,
            "trial_max_dcr_first": 0.93,
            "trial_max_dcr_last": 0.93,
            "trial_max_dcr_drift": 0.0,
        },
        "authority_catalog_routing_diff": {
            "baseline_seeded": False,
            "change_count": 2,
            "added_count": 1,
            "removed_count": 1,
            "unchanged_count": 0,
            "diff_rows": [
                {
                    "change_type": "added",
                    "authority_track": "sac",
                    "submodel_family": "SCBF16B",
                    "review_story_zone": "S02/perimeter",
                    "member_family": "beam",
                    "owner": "Legacy solver",
                    "why": "benchmark holdout",
                }
            ],
        },
        "irregular_top5_families": [
            {
                "priority": 1,
                "family_id": "transfer_podium_tower",
                "execution_mode": "remote_needed",
                "local_ready_source_count": 0,
                "remote_candidate_source_count": 4,
                "recommended_kpi_or_validation_angle": "transfer floor load path + torsion response",
                "source_ids": ["pub-a", "pub-b"],
            },
            {
                "priority": 2,
                "family_id": "soft_story_podium_tower",
                "execution_mode": "remote_needed",
                "local_ready_source_count": 0,
                "remote_candidate_source_count": 3,
                "recommended_kpi_or_validation_angle": "soft-story drift amplification",
                "source_ids": ["pub-c"],
            },
            {
                "priority": 3,
                "family_id": "torsionally_eccentric_core_tower",
                "execution_mode": "ready_local_now",
                "local_ready_source_count": 1,
                "remote_candidate_source_count": 2,
                "recommended_kpi_or_validation_angle": "torsion-dominant response",
                "source_ids": ["pub-d", "pub-e"],
            },
            {
                "priority": 4,
                "family_id": "setback_tower",
                "execution_mode": "remote_needed",
                "local_ready_source_count": 0,
                "remote_candidate_source_count": 2,
                "recommended_kpi_or_validation_angle": "load redistribution at setbacks",
                "source_ids": ["pub-f"],
            },
            {
                "priority": 5,
                "family_id": "reentrant_corner_tower",
                "execution_mode": "remote_needed",
                "local_ready_source_count": 0,
                "remote_candidate_source_count": 2,
                "recommended_kpi_or_validation_angle": "stress concentration and torsion coupling",
                "source_ids": ["pub-g"],
            },
        ],
        "irregular_benchmark_execution_ready_tasks": [
            {
                "task_id": "irregular::torsionally_eccentric_core_tower",
                "case_id": "torsionally_eccentric_core_tower",
                "execution_status": "ready",
                "source_origin_class": "public_native_or_preview",
                "input_path": "implementation/phase1/open_data/irregular/torsionally_eccentric_core_tower.mgt",
                "kpi_receipt_path": "implementation/phase1/release/external_benchmark_kickoff/irregular/torsionally_eccentric_core_tower/kpi_receipt.json",
            }
        ],
        "irregular_benchmark_execution_blocked_tasks": [
            {
                "task_id": "irregular::soft_story_podium_tower",
                "case_id": "soft_story_podium_tower",
                "execution_status": "blocked_by_review",
                "source_origin_class": "remote_candidate",
                "input_path": "implementation/phase1/open_data/irregular/soft_story_podium_tower.mgt",
                "kpi_receipt_path": "implementation/phase1/release/external_benchmark_kickoff/irregular/soft_story_podium_tower/kpi_receipt.json",
            }
        ],
    }


def test_write_external_benchmark_case_onepages_inherits_native_roundtrip_appendix(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "metrics": {
            "midas_native_roundtrip_summary_line": "MIDAS native roundtrip: PASS | corpus=51 | native_text=22 | public_native=4 | public_raw_native=3 | public_bridge_native=1 | public_preview_native=7 | fixture_native=4 | repo_native=3 | experiment_native=3 | archives=7 | ready=21 | public_ready=12 | public_native_ready=4 | public_raw_ready=3 | public_bridge_ready=1 | public_preview_ready=7 | fixture_ready=4 | repo_ready=2 | experiment_ready=3 | receipts=21/21 | topology=21/21 | load=21/21 | loadcomb=21/21 exact | types=8 | taxonomy=exact:20,canonical:1,lossy:0,unsupported:0,manual:1 | pending_review=2",
            "midas_native_roundtrip_writeback_diff_summary_line": "MIDAS native write-back diff receipts: PASS | ready=21 | receipts=21/21 | topology=21/21 | load=21/21 | loadcomb=21/21 exact | types=8 | taxonomy=exact:20,canonical:1,lossy:0,unsupported:0,manual:1 | pending_review=2",
            "midas_native_roundtrip_taxonomy_case_counts": {"preserved_exact": 4, "canonical_rewrite": 1},
            "midas_native_roundtrip_taxonomy_card_family_histogram": {"supported_action_families": {"beam_section": 1}},
            "midas_native_roundtrip_structure_type_batch_markdowns": [
                "implementation/phase1/release/midas_native_roundtrip/stair.diff_batch.md"
            ],
            "midas_native_roundtrip_corpus_case_count": 51,
            "midas_native_roundtrip_native_text_case_count": 22,
            "midas_native_roundtrip_public_native_text_case_count": 4,
            "midas_native_roundtrip_public_raw_native_text_case_count": 3,
            "midas_native_roundtrip_public_bridge_text_case_count": 1,
            "midas_native_roundtrip_public_archive_preview_text_case_count": 7,
            "midas_native_roundtrip_fixture_native_text_case_count": 4,
            "midas_native_roundtrip_repo_native_text_case_count": 3,
            "midas_native_roundtrip_experiment_native_text_case_count": 3,
            "midas_native_roundtrip_archive_case_count": 7,
            "midas_native_roundtrip_native_writeback_ready_count": 21,
            "midas_native_roundtrip_public_native_writeback_ready_count": 4,
            "midas_native_roundtrip_public_raw_native_writeback_ready_count": 3,
            "midas_native_roundtrip_public_bridge_writeback_ready_count": 1,
            "midas_native_roundtrip_public_archive_preview_writeback_ready_count": 7,
            "midas_native_roundtrip_public_source_writeback_ready_count": 12,
            "midas_native_roundtrip_fixture_native_writeback_ready_count": 4,
            "midas_native_roundtrip_repo_native_writeback_ready_count": 2,
            "midas_native_roundtrip_experiment_native_writeback_ready_count": 3,
            "midas_native_roundtrip_structure_type_count": 8,
            "midas_native_roundtrip_structure_type_batch_count": 8,
            "midas_native_roundtrip_receipt_count": 21,
            "midas_native_roundtrip_receipt_pass_count": 21,
            "midas_native_roundtrip_pending_review_total": 2,
            "midas_native_roundtrip_taxonomy_case_counts": {"preserved_exact": 20, "canonical_rewrite": 1, "lossy_rewrite": 0, "unsupported_card": 0, "manual_review_required": 1, "parser_drop_suspected": 1},
            "midas_native_roundtrip_taxonomy_card_family_histogram": {
                "supported_action_families": {
                    "beam_section": 1,
                    "connection_detailing": 12,
                    "detailing": 10,
                    "perimeter_frame": 1,
                    "rebar": 5,
                    "slab_thickness": 2,
                    "wall_thickness": 5,
                },
                "direct_patch_action_families": {
                    "beam_section": 1,
                    "connection_detailing": 6,
                    "detailing": 5,
                    "perimeter_frame": 1,
                    "rebar": 5,
                    "slab_thickness": 2,
                    "wall_thickness": 5,
                },
                "audit_only_action_families": {"connection_detailing": 6, "detailing": 5},
                "audit_manifest_action_families": {"connection_detailing": 6, "detailing": 5},
                "unsupported_reason_counts": {},
            },
        },
        "artifacts": {
            "midas_native_roundtrip_appendix_markdown": "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
            "midas_native_roundtrip_appendix_json": "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
            "midas_native_roundtrip_receipts_report_json": "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
            "midas_kds_row_provenance_export_report": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
            "midas_kds_row_provenance_export_csv": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
            "irregular_benchmark_execution_manifest_json": "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json",
            "irregular_benchmark_receipt_index_json": "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_receipts/receipt_index.json",
        },
        "irregular_benchmark_execution_ready_tasks": [
            {
                "task_id": "irregular::torsionally_eccentric_core_tower",
                "case_id": "torsionally_eccentric_core_tower",
                "case_label": "Torsionally Eccentric Core Tower",
                "execution_status": "ready",
                "benchmark_readiness_tier": "proxy",
                "benchmark_receipt_json": "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_receipts/torsionally_eccentric_core_tower.benchmark_receipt.json",
                "benchmark_receipt_md": "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_receipts/torsionally_eccentric_core_tower.benchmark_receipt.md",
            }
        ],
        "external_benchmark_case_onepage_rows": [
            {
                "task_id": "hardest::sample_case",
                "case_id": "sample_case",
                "case_label": "Sample Case",
                "benchmark_family": "native_roundtrip",
                "hazard_family": "none",
                "topology_family": "stair",
                "load_path_family": "identity_writeback",
                "source_origin_class": "official_external_benchmark_fullcase",
                "execution_status": "completed",
                "kpi_receipt_path": "implementation/phase1/release/external_benchmark_kickoff/runs/sample/benchmark_task_kpi_receipt.json",
                "case_bundle_zip_path": "implementation/phase1/release/external_benchmark_kickoff/runs/sample/signed_case_bundle.zip",
                "kpi_rows": [{"label": "case_count", "value": 1, "source": "primary.summary.case_count"}],
            }
        ],
        "korean_native_roundtrip_representative_rows": [
            {
                "structure_type": "public_facility",
                "source_id": "ifc_public_award_structure__structural_preview_candidate",
                "title": "IFC public award structure",
                "lane_label": "public structural preview",
                "structural_system": "ifc_structural_subset",
                "receipt_md": "implementation/phase1/release/midas_native_roundtrip/ifc_public_award_structure.structural_preview_promotion_receipt.md",
                "receipt_json": "implementation/phase1/release/midas_native_roundtrip/ifc_public_award_structure.structural_preview_promotion_receipt.json",
                "type_batch_markdown": "implementation/phase1/release/midas_native_roundtrip/public_facility.diff_batch.md",
            }
        ],
    }

    _write_external_benchmark_case_onepages(bundle_dir, summary, summary["artifacts"])
    rows = summary["external_benchmark_case_onepage_rows"]

    assert len(rows) == 1
    case_row = rows[0]
    md_path = bundle_dir / case_row["case_onepage_md"]
    html_path = bundle_dir / case_row["case_onepage_html"]
    json_path = bundle_dir / case_row["case_onepage_json"]
    assert json_path.exists()
    assert md_path.exists()
    assert html_path.exists()
    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_payload["case_id"] == "sample_case"
    assert json_payload["cover_sheet_title"] == "Reviewer / Authority Cover Sheet"
    assert json_payload["irregular_benchmark_receipt_count"] == 1
    assert json_payload["irregular_benchmark_receipt_index_json"].endswith("receipt_index.json")
    assert json_payload["irregular_benchmark_receipt_rows"][0]["benchmark_receipt_json"].endswith(
        "torsionally_eccentric_core_tower.benchmark_receipt.json"
    )
    assert json_payload["cover_sheet_fields"][0]["label"] == "Prepared for"
    assert any(field["label"] == "Irregular benchmark receipts" for field in json_payload["cover_sheet_fields"])
    assert "pending real reviewer/authority attestation" in json_payload["cover_sheet_disclaimer"]
    assert json_payload["cover_sheet_slots"]["reviewer_name_slot"].startswith("PENDING_REAL_REVIEWER_NAME")
    assert json_payload["cover_sheet_slots"]["reviewer_role_or_license_slot"].startswith("PENDING_REAL_REVIEWER_ROLE_OR_LICENSE")
    assert json_payload["cover_sheet_slots"]["reviewer_signature_slot"].startswith("PENDING_REAL_REVIEWER_SIGNATURE")
    assert json_payload["cover_sheet_slots"]["receipt_id_slot"].startswith("PENDING_REAL_AUTHORITY_RECEIPT_ID")
    assert json_payload["cover_sheet_slots"]["receipt_issued_at_slot"].startswith("PENDING_REAL_AUTHORITY_RECEIPT_ISSUED_AT")
    assert json_payload["cover_sheet_slots"]["authority_receipt_slot"].startswith("PENDING_REAL_AUTHORITY_RECEIPT")
    assert json_payload["cover_sheet_slots"]["approval_signature_slot"].startswith("PENDING_REAL_APPROVAL_SIGNATURE")
    assert any(field["label"] == "Reviewer signature" for field in json_payload["cover_sheet_fields"])
    assert any(field["label"] == "Receipt issued at" for field in json_payload["cover_sheet_fields"])
    assert "unsupported_lossy_card_family_appendix.md" in json_payload["native_roundtrip_appendix_markdown"]
    assert "Reviewer / Authority Cover Sheet" in md_path.read_text(encoding="utf-8")
    assert "Auto-generated from the execution status manifest and KPI receipt." in md_path.read_text(encoding="utf-8")
    assert "Reviewer signature" in md_path.read_text(encoding="utf-8")
    assert "PENDING_REAL_REVIEWER_SIGNATURE_FILL_CASE_ATTESTATION_MANIFEST" in md_path.read_text(encoding="utf-8")
    assert "Receipt issued at" in md_path.read_text(encoding="utf-8")
    assert "pending real reviewer/authority attestation" in md_path.read_text(encoding="utf-8")
    assert "Authority routing" in md_path.read_text(encoding="utf-8")
    index_md = bundle_dir / "external_benchmark_case_onepages" / "index.md"
    index_html = bundle_dir / "external_benchmark_case_onepages" / "index.html"
    assert "KR Public Structural Preview Representatives" in index_md.read_text(encoding="utf-8")
    assert "ifc_public_award_structure__structural_preview_candidate" in index_md.read_text(encoding="utf-8")
    assert "KR Public Structural Preview Representatives" in index_html.read_text(encoding="utf-8")
    assert "Attestation workflow" in md_path.read_text(encoding="utf-8")
    assert "## Shared Appendices" in md_path.read_text(encoding="utf-8")
    assert "## Irregular Benchmark Receipts" in md_path.read_text(encoding="utf-8")
    assert "torsionally_eccentric_core_tower.benchmark_receipt.json" in md_path.read_text(encoding="utf-8")
    assert "receipt_index.json" in md_path.read_text(encoding="utf-8")
    assert "native roundtrip appendix markdown" in md_path.read_text(encoding="utf-8")
    assert "Reviewer / Authority Cover Sheet" in html_path.read_text(encoding="utf-8")
    assert "Auto-generated from the execution status manifest and KPI receipt." in html_path.read_text(encoding="utf-8")
    assert "Reviewer role / license" in html_path.read_text(encoding="utf-8")
    assert "PENDING_REAL_AUTHORITY_RECEIPT_FILL_CASE_ATTESTATION_MANIFEST" in html_path.read_text(encoding="utf-8")
    assert "pending real reviewer/authority attestation" in html_path.read_text(encoding="utf-8")
    assert "Irregular Benchmark Receipts" in html_path.read_text(encoding="utf-8")
    assert "torsionally_eccentric_core_tower.benchmark_receipt.md" in html_path.read_text(encoding="utf-8")
    assert "native roundtrip appendix markdown" in html_path.read_text(encoding="utf-8")
    assert "row provenance report" in md_path.read_text(encoding="utf-8")
    assert "row provenance csv" in html_path.read_text(encoding="utf-8")


def _run_foundation_realish_fixture(tmp_path: Path) -> dict:
    dataset_out = tmp_path / "design_optimization_dataset_report.json"
    npz_out = tmp_path / "design_optimization_dataset.npz"
    artifact_out = tmp_path / "foundation_optimization_artifact.json"
    report_out = tmp_path / "foundation_optimization_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(FIXTURE_DIR / "foundation_small_model.json"),
            "--code-check",
            str(FIXTURE_DIR / "foundation_small_code_check.json"),
            "--pbd-review",
            str(FIXTURE_DIR / "foundation_small_pbd.json"),
            "--ndtha-residual",
            str(FIXTURE_DIR / "foundation_small_ndtha.json"),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(dataset_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    dataset = json.loads(dataset_out.read_text(encoding="utf-8"))
    foundation_rows = [row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert foundation_rows
    first = foundation_rows[0]

    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    changes.write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "group_id": str(first.get("group_id", "")),
                        "member_type": str(first.get("member_type", "")),
                        "semantic_group": str(first.get("semantic_group", "")),
                        "action_name": "mat_down",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    blocked.write_text(json.dumps({"blocked_rows": []}, ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--design-optimization-npz",
            str(npz_out),
            "--midas-model",
            str(FIXTURE_DIR / "foundation_small_model.json"),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--foundation-optimization-artifact",
            str(artifact_out),
            "--out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return {
        "dataset": dataset,
        "artifact": json.loads(artifact_out.read_text(encoding="utf-8")),
        "report": json.loads(report_out.read_text(encoding="utf-8")),
    }


def test_external_markdown_includes_matrix_and_chain_plot(tmp_path: Path) -> None:
    path = tmp_path / "summary.md"
    _write_summary_markdown(path, _summary())
    text = path.read_text(encoding="utf-8")
    assert "Measured Chain Category Trend" in text
    assert "Active Warnings" in text
    assert "Residual Holdout Routing Matrix" in text
    assert "comparable_reference_deployment_model" in text
    assert "SCBF16B" in text
    assert "design_opt_constructability_avg" in text
    assert "0.2864 -> 0.2848" in text
    assert "design_opt_selected_family_mix" in text
    assert "beam_section=3, detailing=8, rebar=4, slab_thickness=3" in text
    assert "design_opt_selected_family_mix_trend" in text
    assert "beam_section=+1, detailing=-2, rebar=-2, slab_thickness=-1" in text
    assert "design_opt_preview_missing_target_families" in text
    assert "wall_thickness, connection_detailing" in text
    assert "midas_semantic_load_binding_pass" in text
    assert "mgt_export_artifact_exists" in text
    assert "mgt_export_contract_pass" in text
    assert "mgt_export_support_mode" in text
    assert "bounded_patch_subset" in text
    assert "mgt_export_direct_patch_change_count" in text
    assert "mgt_export_direct_patch_action_family_label" in text
    assert "beam_section=1, wall_thickness=1" in text
    assert "mgt_export_rebar_payload_namespace_mode" in text
    assert "material_level_only" in text
    assert "mgt_export_rebar_delivery_mode" in text
    assert "structured_sidecar_only" in text
    assert "mgt_export_evidence_model" in text
    assert "direct_patch_plus_structured_sidecar" in text
    assert "mgt_export_delivery_boundary" in text
    assert "direct_patch=beam_section=1, wall_thickness=1" in text
    assert "sidecar=connection_detailing=2, detailing=1" in text
    assert "mgt_export_rebar_payload_material_level_namespace_present" in text
    assert "True" in text
    assert "mgt_export_rebar_payload_group_local_namespace_present" in text
    assert "False" in text
    assert "mgt_export_material_level_rebar_payloads" in text
    assert "0/5" in text
    assert "mgt_export_rebar_direct_patch_eligible_change_count" in text
    assert "mgt_export_rebar_direct_patch_ineligible_reason_label" in text
    assert "material_payload_missing=1, mixed_material_scope=2" in text
    assert "mgt_export_rebar_direct_patch_mapping_source_label" in text
    assert "alt_slab_wall_group_id=1, direct_group_id=2" in text
    assert "mgt_export_instruction_sidecar_action_family_label" in text
    assert "connection_detailing=2, detailing=1" in text
    assert "mgt_export_instruction_sidecar_audit_only_action_family_label" in text
    assert "connection_detailing=2" in text
    assert "mgt_export_instruction_sidecar_manual_input_action_family_label" in text
    assert "detailing=1" in text
    assert "mgt_export_audit_review_manifest_action_family_label" in text
    assert "mgt_export_audit_review_packet_action_family_label" in text
    assert "mgt_export_audit_review_packet_file_action_family_label" in text
    assert "mgt_export_audit_review_queue_action_family_label" in text
    assert "mgt_export_audit_review_queue_status_label" in text
    assert "mgt_export_audit_review_followup_action_label" in text
    assert "mgt_export_audit_review_followup_owner_label" in text
    assert "mgt_export_audit_review_followup_status_label" in text
    assert "connection_detailing=1" in text
    assert "Advanced Holdouts" in text
    assert "pbd_dynamic_hinge_refresh_ready" in text
    assert "pbd_hinge_refresh_artifact_present" in text
    assert "pbd_hinge_refresh_overlap_member_count" in text
    assert "pbd_hinge_benchmark_gate_pass" in text
    assert "pbd_hinge_benchmark_fixture_regression_pass" in text
    assert "pbd_hinge_benchmark_alignment_pass" in text
    assert "pbd_hinge_benchmark_asset_count" in text
    assert "pbd_hinge_benchmark_fixture_count" in text
    assert "train=2, val=2, holdout=1" in text
    assert "panel_zone_3d_clash_ready" in text
    assert "foundation_optimization_ready" in text
    assert "wind_tunnel_raw_mapping_ready" in text
    assert "panel_zone_source_contract_mode" in text
    assert "panel_zone_instruction_sidecar_candidate_overlap_mode" in text
    assert "section_signature" in text
    assert "panel_zone_instruction_sidecar_evidence_model" in text
    assert "direct_patch_plus_structured_sidecar" in text
    assert "topology_capable_proxy_scan" in text
    assert "panel_zone_proxy_candidate_count" in text
    assert "45" in text
    assert "panel_zone_validated_source_row_count_total" in text
    assert "panel_zone_validated_source_overlap_member_count_min" in text
    assert "panel_zone_missing_required_sources" in text
    assert "panel_zone_joint_geometry_3d" in text
    assert "panel_zone_solver_verified_inbox_status_mode" in text
    assert "panel_zone_solver_verified_source_origin_class" in text
    assert "panel_zone_solver_verified_release_refresh_source_allowed" in text
    assert "consume_pending_input" in text
    assert "foundation_scope_source" in text
    assert "artifact_empty_scan" in text
    assert "upstream_foundation_label_count" in text
    assert "parsed_model_labels_present" in text
    assert "design_opt_blocked_constructability_hard_gate" in text
    assert "detailing_not_improved_enough=4" in text
    assert "design_opt_blocked_illegal_by_mask_family_label" in text
    assert "connection_detailing=3, perimeter_frame=2" in text
    assert "external_benchmark_submission_ready_to_start_now" in text
    assert "external_benchmark_submission_reason_code" in text
    assert "PASS_START_NOW_LIMITED" in text
    assert "external_benchmark_submission_recommended_start_mode" in text
    assert "start_now_limited_external_benchmark" in text
    assert "external_benchmark_submission_recommended_submission_scope" in text
    assert "component_and_system_performance_benchmark_with_review_boundary" in text
    assert "external_benchmark_submission_caution_label" in text
    assert "audit_review_queue_pending=1" in text
    assert "external_benchmark_execution_mode" in text
    assert "external_benchmark_execution_ready_task_count" in text
    assert "external_benchmark_execution_blocked_task_count" in text
    assert "external_benchmark_execution_review_boundary_pending_count" in text
    assert "external_benchmark_execution_review_boundary_resolution_label" in text
    assert "external_benchmark_execution_review_boundary_owner_label" in text
    assert "external_benchmark_execution_review_boundary_change_count_total" in text
    assert "external_benchmark_execution_status_mode" in text
    assert "external_benchmark_execution_planned_task_count" in text
    assert "external_benchmark_execution_completion_ratio" in text
    assert "audit_review_decision_batch_template_item_count" in text
    assert "pending_review=2" in text
    assert "audit_review_decision_batch_attested_example_count" in text
    assert "approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS" in text
    assert "external_benchmark_submission_preview_approve_all_reason_code" in text
    assert "PASS_START_NOW_FULL" in text
    assert "external_benchmark_submission_preview_reject_one_reason_code" in text
    assert "audit_review_resolution_has_open_revisions" in text
    assert "audit_review_decision_batch_runner_reason_code" in text
    assert "midas_section_library_validator" in text
    assert "## MIDAS Section Library" in text
    assert "embedded metadata validated" in text
    assert "validator_line" in text
    assert "## Constitutive / Interaction Coverage" in text
    assert "Constitutive / Interaction Coverage" in text
    assert "expanded constitutive/interaction families" in text
    assert "material_constitutive" in text
    assert "surface_interaction" in text
    assert "## Appendix: MIDAS KDS Row Provenance Export" in text
    assert "row-provenance sync" in text
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in text
    assert "viewer_row_url" in text
    assert "viewer_slice_url" in text
    assert "midas_kds_row_provenance_table.csv" in text
    assert "KDS-MOMENT-Y-001" in text
    assert "exact row-level provenance" in text
    assert "nightly / release gap / committee dashboard / external validation onepage all consume the same validator line" in text
    assert "MIDAS section-library: ok | 182/183 used | 183 templates | source=midas_parser_derived" in text
    assert "PASS" in text


def test_external_html_includes_matrix_and_chain_plot(tmp_path: Path) -> None:
    path = tmp_path / "summary.html"
    _write_summary_html(path, _summary())
    text = path.read_text(encoding="utf-8")
    assert "MGT Delivery Boundary" in text
    assert "Measured Chain Category Trend" in text
    assert "Active Warnings" in text
    assert "Residual Holdout Routing Matrix" in text
    assert "Comparable reference deployment" in text
    assert "release_gap_measured_chain_category.png" in text
    assert "Design-opt constructability avg" in text
    assert "0.2864 -> 0.2848" in text
    assert "Design-opt selected family mix" in text
    assert "beam_section=3, detailing=8, rebar=4, slab_thickness=3" in text
    assert "Design-opt selected family mix trend" in text
    assert "beam_section=+1, detailing=-2, rebar=-2, slab_thickness=-1" in text
    assert "Design-opt preview missing target families" in text
    assert "wall_thickness, connection_detailing" in text
    assert "MIDAS semantic load binding" in text
    assert "MGT export instruction sidecar families" in text
    assert "connection_detailing=2, detailing=1" in text
    assert "MGT audit review packets" in text
    assert "MGT audit packet files" in text
    assert "MGT audit review queue" in text
    assert "MGT audit queue status" in text
    assert "connection_detailing=1" in text
    assert "MGT export artifact exists" in text
    assert "MGT export contract pass" in text
    assert "MGT export support mode" in text
    assert "bounded_patch_subset" in text
    assert "MGT export direct-patch changes" in text
    assert "MGT export direct-patch families" in text
    assert "beam_section=1, wall_thickness=1" in text
    assert "MGT rebar namespace mode" in text
    assert "material_level_only" in text
    assert "MGT rebar delivery mode" in text
    assert "structured_sidecar_only" in text
    assert "MGT evidence model" in text
    assert "direct_patch_plus_structured_sidecar" in text
    assert "MGT delivery boundary" in text
    assert "direct_patch=beam_section=1, wall_thickness=1" in text
    assert "sidecar=connection_detailing=2, detailing=1" in text
    assert "MGT detailing direct-patch eligible" in text
    assert "Advanced Holdouts" in text
    assert "proxy_only_hinge_visualization" in text
    assert "PBD hinge benchmark" in text
    assert "assets=5" in text
    assert "train=2 | val=2 | holdout=1" in text
    assert "alignment=True" in text
    assert "refresh-columns=5" in text
    assert "scalar_proxy_hard_gate_only" in text
    assert "Panel-zone evidence source" in text
    assert "Panel-zone source coverage" in text
    assert "validated rows=5 | min overlap=1" in text
    assert "nested_solver_export" in text
    assert "topology_capable_proxy_scan" in text
    assert "direct_patch_plus_structured_sidecar" in text
    assert "structured_sidecar_only" in text
    assert "Panel-zone missing 3D sources" in text
    assert "panel_zone_clash_verification_3d" in text
    assert "Panel-zone solver inbox" in text
    assert "pending_raw_triplet" in text
    assert "origin=fixture_sample" in text
    assert "consume_pending_input" in text
    assert "External benchmark execution mode" in text
    assert "External benchmark execution ready tasks" in text
    assert "External benchmark execution blocked tasks" in text
    assert "External benchmark execution review-boundary pending" in text
    assert "assignee=unassigned=2 | assignment=unassigned=2" in text
    assert "PBD response source" in text
    assert "fallback_used=False | coverage=0" in text
    assert "Audit review decision batch template" in text
    assert "items=2 | status=pending_review=2 | owner=licensed_engineer=2 | priority=high=1, medium=1" in text
    assert "Approve-all readiness preview" in text
    assert "reason=PASS_START_NOW_FULL | ready_full=True | pending=0 | open_revision=0" in text
    assert "Reject-one readiness preview" in text
    assert "reason=ERR_ARCHITECTURE_BLOCKERS | ready_full=False | pending=0 | open_revision=1 | blocker=audit_review_resolution_has_open_revisions" in text
    assert "Audit review decision batch runner" in text
    assert "reason=PASS | apply_live=False | live_applied=False | preview_reason=PASS_START_NOW_FULL | preview_ready_full=True | preview_pending=0 | preview_open_revision=0" in text
    assert ">limited<" in text
    assert "rule_engine_present_but_dataset_absent" in text
    assert "Foundation scope provenance" in text
    assert "artifact_empty_scan" in text
    assert "parsed_model_labels_present" in text
    assert "semantic_pressure_binding_only" in text
    assert "Structured sidecar families" in text
    assert "MGT rebar material namespace present" in text
    assert "MGT rebar group-local namespace present" in text
    assert "MGT material rebar payloads" in text
    assert "MGT rebar direct-patch eligible" in text
    assert "MGT rebar direct-patch blockers" in text
    assert "material_payload_missing=1, mixed_material_scope=2" in text
    assert "MGT rebar mapping sources" in text
    assert "alt_slab_wall_group_id=1, direct_group_id=2" in text
    assert "0/5" in text
    assert "Illegal-by-mask families" in text
    assert "connection_detailing=3, perimeter_frame=2" in text
    assert "Blocked constructability hard-gate" in text
    assert "detailing_not_improved_enough=4" in text
    assert "External benchmark start mode" in text
    assert "start_now_limited_external_benchmark" in text
    assert "External benchmark scope" in text
    assert "component_and_system_performance_benchmark_with_review_boundary" in text
    assert "External benchmark reason" in text
    assert "PASS_START_NOW_LIMITED" in text
    assert "External benchmark cautions" in text
    assert "audit_review_queue_pending=1" in text
    assert "MIDAS Section Library" in text
    assert "embedded metadata validated" in text
    assert "static + contract gate" in text
    assert "Constitutive / Interaction Coverage" in text
    assert "expanded constitutive/interaction families" in text
    assert "Material constitutive gate: PASS" in text
    assert "Surface interaction benchmark: PASS" in text
    assert "Appendix: MIDAS KDS Row Provenance Export" in text
    assert "row-provenance sync" in text
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in text
    assert "viewer_row_url" in text
    assert "viewer_slice_url" in text
    assert "midas_kds_row_provenance_table.csv" in text
    assert "KDS-MOMENT-Y-001" in text
    assert "nightly, release gap, committee dashboard, and this external-validation onepage all consume the same validator line" in text
    assert "MIDAS section-library validator" in text
    assert "MIDAS section-library: ok | 182/183 used | 183 templates | source=midas_parser_derived" in text


def test_external_markdown_and_html_include_row_provenance_appendix(tmp_path: Path) -> None:
    summary = _summary()
    summary["metrics"]["midas_kds_row_provenance_export_summary_line"] = (
        "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144"
    )
    summary["metrics"]["midas_kds_row_provenance_preview_rows"] = [
        {
            "combination_name": "gLCB1",
            "member_id": "C-TST-003",
            "clause_label": "KDS-MOMENT-Y-001",
            "baseline_focus_member_id": "27441",
            "bridge_row_provenance_mode_label": "exact row-level provenance",
            "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
            "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column",
        }
    ]
    summary["metrics"]["midas_kds_row_provenance_clause_filter_rows"] = [
        {
            "clause_label": "KDS-MOMENT-Y-001",
            "row_count": 12,
            "member_count": 12,
            "combination_count": 6,
            "top_member_id": "C-TST-003",
            "top_dcr_label": "1.216",
        }
    ]
    summary["metrics"]["midas_kds_row_provenance_member_filter_rows"] = [
        {
            "member_id": "C-TST-003",
            "baseline_focus_member_id": "27441",
            "row_count": 12,
            "clause_count": 1,
            "combination_count": 6,
            "top_clause_label": "KDS-MOMENT-Y-001",
        }
    ]
    summary["metrics"]["midas_kds_row_provenance_hazard_filter_rows"] = [
        {
            "hazard_type": "seismic",
            "row_count": 12,
            "member_count": 12,
            "clause_count": 1,
            "combination_count": 6,
            "top_clause_label": "KDS-MOMENT-Y-001",
            "top_dcr_label": "1.216",
        }
    ]
    summary["metrics"]["midas_kds_row_provenance_rule_family_filter_rows"] = [
        {
            "rule_family": "strength",
            "row_count": 12,
            "member_count": 12,
            "hazard_count": 1,
            "combination_count": 6,
            "top_clause_label": "KDS-MOMENT-Y-001",
            "top_dcr_label": "1.216",
        }
    ]
    summary["artifacts"]["midas_kds_row_provenance_export_json"] = (
        "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json"
    )
    summary["artifacts"]["midas_kds_row_provenance_export_csv"] = (
        "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv"
    )
    summary["artifacts"]["midas_kds_row_provenance_export_report"] = (
        "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json"
    )
    md_path = tmp_path / "summary.md"
    html_path = tmp_path / "summary.html"
    _write_summary_markdown(md_path, summary)
    _write_summary_html(html_path, summary)
    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "## Constitutive / Interaction Coverage" in markdown
    assert "expanded constitutive/interaction families" in markdown
    assert "## Appendix: MIDAS KDS Row Provenance Export" in markdown
    assert "row-provenance sync" in markdown
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in markdown
    assert "viewer_row_url" in markdown
    assert "viewer_slice_url" in markdown
    assert "midas_kds_row_provenance_table.csv" in markdown
    assert "KDS-MOMENT-Y-001" in markdown
    assert "| Clause | Rows | Members | Combos | Top Member | Top D/C |" in markdown
    assert "| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |" in markdown
    assert "| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |" in markdown
    assert "| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |" in markdown
    assert "Constitutive / Interaction Coverage" in html
    assert "expanded constitutive/interaction families" in html
    assert "Appendix: MIDAS KDS Row Provenance Export" in html
    assert "row-provenance sync" in html
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in html
    assert "viewer_row_url" in html
    assert "viewer_slice_url" in html
    assert "midas_kds_row_provenance_table.csv" in html
    assert "KDS-MOMENT-Y-001" in html
    assert "Top D/C" in html
    assert "Top Clause" in html


def test_external_markdown_and_html_surface_foundation_realish_provenance(tmp_path: Path) -> None:
    fixture = _run_foundation_realish_fixture(tmp_path)
    report = fixture["report"]
    dataset = fixture["dataset"]
    summary = _summary()
    summary["metrics"]["foundation_optimization_ready"] = report["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    summary["metrics"]["foundation_optimization_mode"] = report["summary"]["optimization_mode"]
    summary["metrics"]["foundation_optimization_reason"] = report["summary"]["foundation_scope_source"]
    summary["metrics"]["foundation_scope_source"] = report["summary"]["foundation_scope_source"]
    summary["metrics"]["foundation_artifact_scan_mode"] = report["summary"].get("foundation_artifact_scan_mode", "npz_full")
    summary["metrics"]["upstream_foundation_label_count"] = int(dataset["summary"]["member_type_counts"]["foundation"])
    summary["metrics"]["upstream_foundation_provenance_mode"] = "dataset_summary_fixture"
    md_path = tmp_path / "summary.md"
    html_path = tmp_path / "summary.html"
    _write_summary_markdown(md_path, summary)
    _write_summary_html(html_path, summary)
    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "foundation_optimization_ready" in markdown
    assert "active_foundation_member_optimization" in markdown
    assert "foundation_scope_source" in markdown
    assert "dataset_summary" in markdown
    assert "upstream_foundation_label_count" in markdown
    assert "2" in markdown
    assert "Foundation optimization" in html
    assert "active_foundation_member_optimization" in html
    assert "Foundation scope provenance" in html
    assert "dataset_summary" in html
    assert "upstream_foundation_label_count" in markdown


def test_external_markdown_and_html_include_promotion_hold(tmp_path: Path) -> None:
    summary = _summary()
    summary["promotion_reason_code"] = "HOLD_FOR_REVIEW"
    summary["promotion_hold_for_review"] = True
    summary["checks"]["promotion"] = "FAIL"
    summary["metrics"]["promotion_reason_code"] = "HOLD_FOR_REVIEW"
    summary["metrics"]["promotion_hold_for_review"] = True
    md_path = tmp_path / "summary.md"
    html_path = tmp_path / "summary.html"
    _write_summary_markdown(md_path, summary)
    _write_summary_html(html_path, summary)
    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "Active Promotion Hold" in markdown
    assert "hold_review_manifest" in markdown
    assert "hold_review_packet_md" in markdown
    assert "hold_review_packet_pdf" in markdown
    assert "hold_review_ack_json" in markdown
    assert "HOLD_FOR_REVIEW" in markdown
    assert "Promotion Hold" in html
    assert "hold_review_manifest.json" in html
    assert "hold_review_packet.md" in html
    assert "hold_review_packet.pdf" in html
    assert "hold_review_ack.json" in html


def test_external_markdown_and_html_include_native_roundtrip_appendix(tmp_path: Path) -> None:
    summary = _summary()

    gate_json = tmp_path / "midas_native_roundtrip_gate_report.json"
    receipts_json = tmp_path / "midas_native_writeback_diff_receipts_report.json"
    appendix_md = tmp_path / "unsupported_lossy_card_family_appendix.md"
    appendix_json = tmp_path / "unsupported_lossy_card_family_appendix.json"
    bridge_batch_md = tmp_path / "bridge.diff_batch.md"
    building_batch_md = tmp_path / "building.diff_batch.md"
    bridge_receipt_md = tmp_path / "bridge_case_01.diff_receipt.md"
    bridge_receipt_json = tmp_path / "bridge_case_01.diff_receipt.json"

    for path, payload in [
        (gate_json, {"summary": {"corpus_case_count": 6}}),
        (
            receipts_json,
            {
                "summary": {
                    "ready_case_count": 2,
                    "receipt_count": 2,
                    "receipt_pass_count": 2,
                    "topology_stable_case_count": 2,
                    "load_contract_stable_case_count": 2,
                    "loadcomb_exact_case_count": 2,
                    "pending_review_total": 1,
                    "structure_type_batch_count": 2,
                    "taxonomy_case_counts": {
                        "preserved_exact": 1,
                        "canonical_rewrite": 1,
                        "lossy_rewrite": 0,
                        "unsupported_card": 0,
                        "manual_review_required": 0,
                        "parser_drop_suspected": 0,
                    },
                    "taxonomy_card_family_histogram": {
                        "supported_action_families": {"beam_section": 1},
                        "direct_patch_action_families": {"beam_section": 1},
                        "audit_only_action_families": {},
                        "audit_manifest_action_families": {},
                        "unsupported_reason_counts": {},
                    },
                },
                "receipt_rows": [
                    {
                        "case_id": "bridge_case_01",
                        "structure_type": "bridge",
                        "writeback_mode": "native",
                        "contract_pass": True,
                        "summary_line": "bridge_case_01 | pass",
                        "receipt_json": str(bridge_receipt_json),
                        "receipt_md": str(bridge_receipt_md),
                        "topology_stability_pass": True,
                        "load_contract_stability_pass": True,
                        "loadcomb_exact_roundtrip_pass": True,
                        "unknown_rows_zero_pass": True,
                        "review_pending_count": 0,
                        "taxonomy": {"preserved_exact": 1},
                    },
                    {
                        "case_id": "building_case_02",
                        "structure_type": "building",
                        "writeback_mode": "archive_preview",
                        "contract_pass": True,
                        "summary_line": "building_case_02 | pass",
                        "receipt_json": str(tmp_path / "building_case_02.diff_receipt.json"),
                        "receipt_md": str(tmp_path / "building_case_02.diff_receipt.md"),
                        "topology_stability_pass": True,
                        "load_contract_stability_pass": True,
                        "loadcomb_exact_roundtrip_pass": True,
                        "unknown_rows_zero_pass": True,
                        "review_pending_count": 1,
                        "taxonomy": {"canonical_rewrite": 1},
                    },
                ],
                "structure_type_batches": [
                    {
                        "structure_type": "bridge",
                        "ready_case_count": 1,
                        "receipt_pass_count": 1,
                        "topology_stable_case_count": 1,
                        "load_contract_stable_case_count": 1,
                        "loadcomb_exact_case_count": 1,
                        "pending_review_total": 0,
                        "taxonomy_case_counts": {"preserved_exact": 1},
                        "taxonomy_card_family_histogram": {"supported_action_families": {"beam_section": 1}},
                        "writeback_modes": {"native": 1},
                        "case_ids": ["bridge_case_01"],
                        "batch_markdown": str(bridge_batch_md),
                    },
                    {
                        "structure_type": "building",
                        "ready_case_count": 1,
                        "receipt_pass_count": 1,
                        "topology_stable_case_count": 1,
                        "load_contract_stable_case_count": 1,
                        "loadcomb_exact_case_count": 1,
                        "pending_review_total": 1,
                        "taxonomy_case_counts": {"canonical_rewrite": 1},
                        "taxonomy_card_family_histogram": {"supported_action_families": {"beam_section": 1}},
                        "writeback_modes": {"archive_preview": 1},
                        "case_ids": ["building_case_02"],
                        "batch_markdown": str(building_batch_md),
                    },
                ],
                "unsupported_lossy_card_family_appendix_markdown": str(appendix_md),
                "unsupported_lossy_card_family_appendix_json": str(appendix_json),
            },
        ),
    ]:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for path in [appendix_md, appendix_json, bridge_batch_md, building_batch_md, bridge_receipt_md, bridge_receipt_json]:
        path.write_text(path.name, encoding="utf-8")
    (tmp_path / "building_case_02.diff_receipt.json").write_text("{}", encoding="utf-8")
    (tmp_path / "building_case_02.diff_receipt.md").write_text("building_case_02", encoding="utf-8")

    summary["metrics"].update(
        {
            "midas_native_roundtrip_summary_line": "MIDAS native roundtrip: PASS | corpus=6 | native_text=2 | public_native=1 | public_preview_native=1 | fixture_native=1 | repo_native=1 | experiment_native=0 | archives=1 | ready=2 | public_ready=2 | public_native_ready=1 | public_preview_ready=1 | fixture_ready=1 | repo_ready=0 | experiment_ready=0 | receipts=2/2 | topology=2/2 | load=2/2 | loadcomb=2/2 exact | types=2 | taxonomy=exact:1,canonical:1,lossy:0,unsupported:0,manual:0 | pending_review=1",
            "midas_native_roundtrip_writeback_diff_summary_line": "MIDAS native write-back diff receipts: PASS | ready=2 | receipts=2/2 | topology=2/2 | load=2/2 | loadcomb=2/2 exact | types=2 | taxonomy=exact:1,canonical:1,lossy:0,unsupported:0,manual:0 | pending_review=1",
            "midas_native_roundtrip_corpus_case_count": 6,
            "midas_native_roundtrip_native_text_case_count": 2,
            "midas_native_roundtrip_public_native_text_case_count": 1,
            "midas_native_roundtrip_public_archive_preview_text_case_count": 1,
            "midas_native_roundtrip_fixture_native_text_case_count": 1,
            "midas_native_roundtrip_repo_native_text_case_count": 1,
            "midas_native_roundtrip_archive_case_count": 1,
            "midas_native_roundtrip_native_writeback_ready_count": 2,
            "midas_native_roundtrip_public_native_writeback_ready_count": 1,
            "midas_native_roundtrip_public_archive_preview_writeback_ready_count": 1,
            "midas_native_roundtrip_public_source_writeback_ready_count": 2,
            "midas_native_roundtrip_fixture_native_writeback_ready_count": 1,
            "midas_native_roundtrip_repo_native_writeback_ready_count": 1,
            "midas_native_roundtrip_experiment_native_writeback_ready_count": 0,
            "midas_native_roundtrip_structure_type_count": 2,
            "midas_native_roundtrip_receipt_count": 2,
            "midas_native_roundtrip_receipt_pass_count": 2,
            "midas_native_roundtrip_topology_stable_case_count": 2,
            "midas_native_roundtrip_load_contract_stable_case_count": 2,
            "midas_native_roundtrip_loadcomb_exact_case_count": 2,
            "midas_native_roundtrip_pending_review_total": 1,
            "midas_native_roundtrip_structure_type_batch_count": 2,
            "midas_native_roundtrip_taxonomy_case_counts": {
                "preserved_exact": 1,
                "canonical_rewrite": 1,
                "lossy_rewrite": 0,
                "unsupported_card": 0,
                "manual_review_required": 0,
                "parser_drop_suspected": 0,
            },
            "midas_native_roundtrip_taxonomy_card_family_histogram": {
                "supported_action_families": {"beam_section": 1},
                "direct_patch_action_families": {"beam_section": 1},
                "audit_only_action_families": {},
                "audit_manifest_action_families": {},
                "unsupported_reason_counts": {},
            },
            "midas_native_roundtrip_receipt_rows": [
                {
                    "case_id": "bridge_case_01",
                    "structure_type": "bridge",
                    "writeback_mode": "native",
                    "contract_pass": True,
                    "summary_line": "bridge_case_01 | pass",
                    "receipt_json": str(bridge_receipt_json),
                    "receipt_md": str(bridge_receipt_md),
                    "review_pending_count": 0,
                },
                {
                    "case_id": "building_case_02",
                    "structure_type": "building",
                    "writeback_mode": "archive_preview",
                    "contract_pass": True,
                    "summary_line": "building_case_02 | pass",
                    "receipt_json": str(tmp_path / "building_case_02.diff_receipt.json"),
                    "receipt_md": str(tmp_path / "building_case_02.diff_receipt.md"),
                    "review_pending_count": 1,
                },
            ],
            "midas_native_roundtrip_structure_type_batches": [
                {
                    "structure_type": "bridge",
                    "ready_case_count": 1,
                    "receipt_pass_count": 1,
                    "topology_stable_case_count": 1,
                    "load_contract_stable_case_count": 1,
                    "loadcomb_exact_case_count": 1,
                    "pending_review_total": 0,
                    "batch_markdown": str(bridge_batch_md),
                },
                {
                    "structure_type": "building",
                    "ready_case_count": 1,
                    "receipt_pass_count": 1,
                    "topology_stable_case_count": 1,
                    "load_contract_stable_case_count": 1,
                    "loadcomb_exact_case_count": 1,
                    "pending_review_total": 1,
                    "batch_markdown": str(building_batch_md),
                },
            ],
            "midas_native_roundtrip_structure_type_batch_markdowns": [
                str(bridge_batch_md),
                str(building_batch_md),
            ],
        }
    )
    summary["artifacts"].update(
        {
            "midas_native_roundtrip_gate_report_json": str(gate_json),
            "midas_native_roundtrip_receipts_report_json": str(receipts_json),
            "midas_native_roundtrip_appendix_markdown": str(appendix_md),
            "midas_native_roundtrip_appendix_json": str(appendix_json),
        }
    )
    irregular_receipt_dir = tmp_path / "irregular_benchmark_receipts"
    irregular_receipt_dir.mkdir(parents=True, exist_ok=True)
    irregular_receipt_index = irregular_receipt_dir / "receipt_index.json"
    irregular_receipt_json = irregular_receipt_dir / "torsionally_eccentric_core_tower.benchmark_receipt.json"
    irregular_receipt_md = irregular_receipt_dir / "torsionally_eccentric_core_tower.benchmark_receipt.md"
    irregular_receipt_index.write_text("{}", encoding="utf-8")
    irregular_receipt_json.write_text("{}", encoding="utf-8")
    irregular_receipt_md.write_text("# receipt", encoding="utf-8")
    summary["artifacts"]["irregular_benchmark_receipt_index_json"] = str(irregular_receipt_index)
    summary["irregular_benchmark_execution_ready_tasks"][0]["benchmark_receipt_json"] = str(irregular_receipt_json)
    summary["irregular_benchmark_execution_ready_tasks"][0]["benchmark_receipt_md"] = str(irregular_receipt_md)
    summary["irregular_canonical_promotion_queue_rows"] = [
        {
            "family_id": "transfer_podium_tower",
            "source_id": "transfer_podium_tower_proxy_local",
            "status": "source_hunt_pending",
            "promotion_path": "collect official benchmark-native package",
            "native_support": "native MEB support via midas_multifamily_building_meb_local",
            "blocker": "Canonical benchmark model has not been collected yet.",
        }
    ]
    summary["checks"]["promotion"] = "PASS"

    md_path = tmp_path / "summary.md"
    html_path = tmp_path / "summary.html"
    _write_summary_markdown(md_path, summary)
    _write_summary_html(html_path, summary)
    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "MIDAS Native Roundtrip / Write-Back" in markdown
    assert "MIDAS native roundtrip: PASS" in markdown
    assert "MIDAS Native Roundtrip / Write-Back Taxonomy" in markdown
    assert "bridge_case_01" in markdown
    assert str(appendix_md) in markdown
    assert "KR Source / Preview" in markdown
    assert "kr_ingest_summary" in markdown
    assert "measured_benchmark_breadth" in markdown
    assert "kr_preview_queue_summary" in markdown
    assert "KR ingest" in markdown
    assert "Measured benchmark breadth" in markdown
    assert "measured_cases=74" in markdown
    assert "OpenSees canonical breadth" in markdown
    assert "KR Representative Type Batches" in markdown
    assert "Public Structural Preview Lane" in markdown
    assert "Public Native Lane" in markdown
    assert "lh_bucheon_yeokgok_a1_housing_native_baseline" in markdown
    assert "ifc_public_award_structure__structural_preview_candidate" in markdown
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in markdown
    assert "Irregular Structure Track" in markdown
    assert "Irregular benchmark execution: PASS" in markdown
    assert "irregular_benchmark_execution_manifest.json" in markdown
    assert "irregular benchmark receipt index" in markdown
    assert "torsionally_eccentric_core_tower.benchmark_receipt.json" in markdown
    assert "special_member_family" in markdown
    assert "kr_promotion_queue" in markdown
    assert "Bridged To Canonical Promotion Queue" not in markdown
    assert "collect official benchmark-native package" not in markdown
    assert "transfer_podium_tower" not in markdown
    assert "Transfer Podium Hunt" not in markdown
    assert "reference_pdf_recursive_hunt" not in markdown
    assert "author_whitelist_scan" not in markdown
    assert "MIDAS Native Roundtrip / Write-Back" in html
    assert "MIDAS native write-back diff receipts: PASS" in html
    assert "bridge_case_01" in html
    assert str(appendix_json) in html
    assert "KR Source / Preview" in html
    assert "KR ingest" in html
    assert "Measured benchmark breadth" in html
    assert "measured_cases=74" in html
    assert "OpenSees canonical breadth" in html
    assert "Public Structural Preview Lane" in html
    assert "Public Native Lane" in html
    assert "LH Bucheon Yeokgok A1 housing native baseline" in html
    assert "IFC public award structure" in html
    assert "KR preview queue" in html
    assert "KR ingest" in html
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in html
    assert "Irregular Structure Track" in html
    assert "irregular_benchmark_execution_manifest.json" in html
    assert "irregular benchmark receipt index" in html
    assert "torsionally_eccentric_core_tower.benchmark_receipt.md" in html
    assert "special_member_family" in html
    assert "kr_promotion_queue" in html
    assert "Canonical promotion queue" in html
    assert "collect official benchmark-native package" not in html
    assert "transfer_podium_tower" not in html
    assert "Transfer Podium Hunt" not in html
    assert "reference_pdf_recursive_hunt" not in html
    assert "author_whitelist_scan" not in html


def test_write_summary_markdown_and_html_include_irregular_structure_track(tmp_path: Path) -> None:
    summary = _summary()
    summary["artifacts"].update(
        {
            "midas_native_roundtrip_appendix_markdown": "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
            "midas_native_roundtrip_appendix_json": "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
            "midas_native_roundtrip_receipts_report_json": "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
        }
    )
    irregular_receipt_dir = tmp_path / "irregular_benchmark_receipts"
    irregular_receipt_dir.mkdir(parents=True, exist_ok=True)
    irregular_receipt_index = irregular_receipt_dir / "receipt_index.json"
    irregular_receipt_json = irregular_receipt_dir / "torsionally_eccentric_core_tower.benchmark_receipt.json"
    irregular_receipt_md = irregular_receipt_dir / "torsionally_eccentric_core_tower.benchmark_receipt.md"
    irregular_receipt_index.write_text("{}", encoding="utf-8")
    irregular_receipt_json.write_text("{}", encoding="utf-8")
    irregular_receipt_md.write_text("# receipt", encoding="utf-8")
    summary["artifacts"]["irregular_benchmark_receipt_index_json"] = str(irregular_receipt_index)
    summary["irregular_benchmark_execution_ready_tasks"][0]["benchmark_receipt_json"] = str(irregular_receipt_json)
    summary["irregular_benchmark_execution_ready_tasks"][0]["benchmark_receipt_md"] = str(irregular_receipt_md)
    summary["irregular_canonical_promotion_queue_rows"] = [
        {
            "family_id": "transfer_podium_tower",
            "source_id": "transfer_podium_tower_proxy_local",
            "status": "source_hunt_pending",
            "promotion_path": "collect official benchmark-native package",
            "native_support": "native MEB support via midas_multifamily_building_meb_local",
            "blocker": "Canonical benchmark model has not been collected yet.",
        }
    ]
    md_path = tmp_path / "summary.md"
    html_path = tmp_path / "summary.html"

    _write_summary_markdown(md_path, summary)
    _write_summary_html(html_path, summary)

    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "Irregular Structure Track" in markdown
    assert "Irregular benchmark execution: PASS | ready=1 | blocked=4 | task_count=5 | top5_local_ready=1 | top5_remote_needed=4" in markdown
    assert "torsionally_eccentric_core_tower" in markdown
    assert "irregular_structure_collection_gate_report.json" not in markdown
    assert "irregular benchmark receipt index" in markdown
    assert "torsionally_eccentric_core_tower.benchmark_receipt.json" in markdown
    assert "Bridged To Canonical Promotion Queue" not in markdown
    assert "transfer_podium_tower_proxy_local" not in markdown
    assert "collect official benchmark-native package" not in markdown
    assert "transfer_podium_tower" not in markdown
    assert "reference_pdf_recursive_hunt" not in markdown
    assert "author_whitelist_scan" not in markdown
    assert "Irregular Structure Track" in html
    assert "Irregular benchmark execution: PASS | ready=1 | blocked=4 | task_count=5 | top5_local_ready=1 | top5_remote_needed=4" in html
    assert "torsionally_eccentric_core_tower" in html
    assert "irregular_structure_collection_gate_report.json" not in html
    assert "irregular benchmark receipt index" in html
    assert "torsionally_eccentric_core_tower.benchmark_receipt.md" in html
    assert "Canonical promotion queue" in html
    assert "transfer_podium_tower_proxy_local" not in html
    assert "collect official benchmark-native package" not in html
    assert "transfer_podium_tower" not in html
    assert "reference_pdf_recursive_hunt" not in html
    assert "author_whitelist_scan" not in html


def test_build_bundle_keeps_root_summary_files(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    summary = _summary()
    irregular_artifact_paths = {
        "irregular_structure_gate_report_json": tmp_path / "irregular_structure_collection_gate_report.json",
        "irregular_structure_source_catalog_json": tmp_path / "irregular_structure_source_catalog.json",
        "irregular_structure_triage_report_json": tmp_path / "irregular_structure_triage_report.json",
        "irregular_structure_collection_report_json": tmp_path / "irregular_structure_collection_report.json",
        "irregular_top5_execution_manifest_json": tmp_path / "irregular_top5_execution_manifest.json",
        "irregular_benchmark_execution_manifest_json": tmp_path / "irregular_benchmark_execution_manifest.json",
        "irregular_benchmark_receipt_index_json": tmp_path / "irregular_benchmark_receipts" / "receipt_index.json",
        "irregular_benchmark_receipt_json": tmp_path / "irregular_benchmark_receipts" / "torsionally_eccentric_core_tower.benchmark_receipt.json",
        "irregular_benchmark_receipt_md": tmp_path / "irregular_benchmark_receipts" / "torsionally_eccentric_core_tower.benchmark_receipt.md",
    }
    for path in irregular_artifact_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "# receipt\n", encoding="utf-8")
    summary["artifacts"].update(
        {
            "midas_native_roundtrip_appendix_markdown": "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
            "midas_native_roundtrip_appendix_json": "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
            "midas_native_roundtrip_receipts_report_json": "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
            **{key: str(path) for key, path in irregular_artifact_paths.items()},
        }
    )
    summary["external_benchmark_case_onepage_rows"] = [
        {
            "task_id": "hardest::peer_tbi_tall_building_ndtha",
            "case_id": "peer_tbi_tall_building_ndtha",
            "case_label": "PEER TBI Tall Building NDTHA",
            "benchmark_family": "highrise_ndtha",
            "hazard_family": "seismic",
            "topology_family": "tall_building_core_outrigger",
            "load_path_family": "ndtha_multi_record",
            "source_origin_class": "official_external_benchmark_fullcase",
            "execution_status": "ready",
            "kpi_receipt_path": "implementation/phase1/release/external_benchmark_kickoff/runs/hardest_peer_tbi_tall_building_ndtha/benchmark_task_kpi_receipt.json",
            "case_bundle_zip_path": "implementation/phase1/release/external_benchmark_kickoff/runs/hardest_peer_tbi_tall_building_ndtha/signed_case_bundle.zip",
            "kpi_rows": [
                {"label": "case_count", "value": 3, "source": "primary.summary.case_count"},
                {"label": "solver_hip_variants", "value": 20, "source": "supporting.solver_hip.summary.solver_count"},
            ],
        }
    ]
    summary["irregular_benchmark_execution_ready_tasks"] = [
        {
            "task_id": "irregular::torsionally_eccentric_core_tower",
            "case_id": "torsionally_eccentric_core_tower",
            "case_label": "Torsionally Eccentric Core Tower",
            "execution_status": "ready",
            "benchmark_readiness_tier": "proxy",
            "benchmark_receipt_json": str(irregular_artifact_paths["irregular_benchmark_receipt_json"]),
            "benchmark_receipt_md": str(irregular_artifact_paths["irregular_benchmark_receipt_md"]),
        }
    ]

    bundle_dir, bundle_zip, summary_json, summary_md, summary_html, summary_pdf, removed = _build_bundle(
        release_dir=release_dir,
        bundle_name="external_validation_submission_unit",
        artifacts=[str(artifact)] + [str(path) for path in irregular_artifact_paths.values()],
        summary=summary,
        prune_old=False,
        prune_prefix="external_validation_submission_",
    )

    assert removed == []
    assert bundle_dir.exists()
    assert bundle_zip.exists()
    assert summary_json.exists()
    assert summary_md.exists()
    assert summary_html.exists()
    assert summary_pdf.exists()
    summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
    case_row = summary_payload["external_benchmark_case_onepage_rows"][0]
    case_dir = bundle_dir / "external_benchmark_case_onepages"
    case_md = bundle_dir / case_row["case_onepage_md"]
    case_html = bundle_dir / case_row["case_onepage_html"]
    case_pdf = bundle_dir / case_row["case_onepage_pdf"]
    index_md = case_dir / "index.md"
    index_html = case_dir / "index.html"
    index_pdf = case_dir / "index.pdf"
    case_json = bundle_dir / case_row["case_onepage_json"]
    readme = bundle_dir / "README.txt"
    assert case_md.exists()
    assert case_html.exists()
    assert case_pdf.exists()
    assert index_md.exists()
    assert index_html.exists()
    assert index_pdf.exists()
    assert case_json.exists()
    assert readme.exists()
    case_json_payload = json.loads(case_json.read_text(encoding="utf-8"))
    assert case_json_payload["cover_sheet_title"] == "Reviewer / Authority Cover Sheet"
    assert case_json_payload["irregular_benchmark_receipt_count"] == 1
    assert case_json_payload["irregular_benchmark_receipt_rows"][0]["benchmark_receipt_md"].endswith(
        "torsionally_eccentric_core_tower.benchmark_receipt.md"
    )
    assert case_json_payload["cover_sheet_fields"][0]["label"] == "Prepared for"
    assert "pending real reviewer/authority attestation" in case_json_payload["cover_sheet_disclaimer"]
    assert case_json_payload["cover_sheet_slots"]["reviewer_name_slot"].startswith("PENDING_REAL_REVIEWER_NAME")
    assert case_json_payload["cover_sheet_slots"]["reviewer_signature_slot"].startswith("PENDING_REAL_REVIEWER_SIGNATURE")
    assert case_json_payload["cover_sheet_slots"]["receipt_id_slot"].startswith("PENDING_REAL_AUTHORITY_RECEIPT_ID")
    assert case_json_payload["cover_sheet_slots"]["receipt_issued_at_slot"].startswith("PENDING_REAL_AUTHORITY_RECEIPT_ISSUED_AT")
    assert "Reviewer / Authority Cover Sheet" in case_md.read_text(encoding="utf-8")
    assert "Auto-generated from the execution status manifest and KPI receipt." in case_md.read_text(encoding="utf-8")
    assert "ready_now=True" in case_md.read_text(encoding="utf-8")
    assert "Reviewer signature" in case_md.read_text(encoding="utf-8")
    assert "Receipt id" in case_md.read_text(encoding="utf-8")
    assert "pending real reviewer/authority attestation" in case_md.read_text(encoding="utf-8")
    assert "Attestation workflow" in case_md.read_text(encoding="utf-8")
    assert "## Shared Appendices" in case_md.read_text(encoding="utf-8")
    assert "## Irregular Benchmark Receipts" in case_md.read_text(encoding="utf-8")
    assert "torsionally_eccentric_core_tower.benchmark_receipt.json" in case_md.read_text(encoding="utf-8")
    assert "row provenance report" in case_md.read_text(encoding="utf-8")
    assert (bundle_dir / "artifacts" / "absolute_artifacts" / "torsionally_eccentric_core_tower.benchmark_receipt.json").exists()
    assert (bundle_dir / "artifacts" / "absolute_artifacts" / "torsionally_eccentric_core_tower.benchmark_receipt.md").exists()
    assert "reviewer / authority cover sheet" in readme.read_text(encoding="utf-8").lower()
    assert "reviewer / authority cover sheet" in index_md.read_text(encoding="utf-8").lower()
    index_md_text = index_md.read_text(encoding="utf-8")
    index_html_text = index_html.read_text(encoding="utf-8")
    assert "shared native roundtrip appendix" in index_md_text
    assert "shared row provenance report" in index_md_text
    assert "Native Authoring Coverage" in case_md.read_text(encoding="utf-8")
    assert "kr_promotion_queue" in case_md.read_text(encoding="utf-8")
    assert "Irregular Receipts" in index_md_text
    assert "torsionally_eccentric_core_tower.benchmark_receipt.json" in index_md_text
    assert "shared native roundtrip appendix" in index_html_text
    assert "shared row provenance report" in index_html_text
    assert "Transfer Podium Hunt" not in index_md_text
    assert "transfer_podium_source_hunt_ledger.md" not in index_md_text
    assert "Transfer Podium Hunt" not in index_html_text
    assert "transfer_podium_source_hunt_ledger.md" not in index_html_text
    assert "Irregular Receipts" in index_html_text
    assert "torsionally_eccentric_core_tower.benchmark_receipt.md" in index_html_text
    assert "Irregular Structure Track" in summary_md.read_text(encoding="utf-8")
    assert "Irregular Structure Track" in summary_html.read_text(encoding="utf-8")
    assert "irregular_structure_collection_gate_report.json" not in summary_md.read_text(encoding="utf-8")
    assert "irregular_structure_collection_gate_report.json" not in summary_html.read_text(encoding="utf-8")
    scrubbed_names = {
        "irregular_structure_collection_gate_report.json",
        "irregular_structure_source_catalog.json",
        "irregular_structure_triage_report.json",
        "irregular_structure_collection_report.json",
        "irregular_top5_execution_manifest.json",
    }
    kept_names = {
        "irregular_benchmark_execution_manifest.json",
        "receipt_index.json",
        "torsionally_eccentric_core_tower.benchmark_receipt.json",
        "torsionally_eccentric_core_tower.benchmark_receipt.md",
    }
    for path in irregular_artifact_paths.values():
        copied = bundle_dir / "artifacts" / "absolute_artifacts" / path.name
        if path.name in scrubbed_names:
            assert not copied.exists()
        elif path.name in kept_names:
            assert copied.exists()
    assert "PEER TBI Tall Building NDTHA" in case_html.read_text(encoding="utf-8")
    assert "Reviewer / Authority Cover Sheet" in case_html.read_text(encoding="utf-8")
    assert "Reviewer role / license" in case_html.read_text(encoding="utf-8")
    assert "PENDING_REAL_APPROVAL_SIGNATURE_FILL_CASE_ATTESTATION_MANIFEST" in case_html.read_text(encoding="utf-8")
    assert "pending real reviewer/authority attestation" in case_html.read_text(encoding="utf-8")
    assert "Appendix: External Benchmark Case Onepages" in summary_md.read_text(encoding="utf-8")
    assert "External benchmark case onepages" in summary_html.read_text(encoding="utf-8")
