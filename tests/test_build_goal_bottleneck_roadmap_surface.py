from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_goal_bottleneck_roadmap_surface.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_goal_bottleneck_roadmap_surface", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _row_by_phase(surface: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = surface["roadmap_rows"]
    assert isinstance(rows, list)
    return {
        str(row["phase_id"]): row
        for row in rows
        if isinstance(row, dict) and "phase_id" in row
    }


def test_goal_bottleneck_roadmap_surface_exposes_goal_release_kpis() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)

    assert surface["schema_version"] == "goal-bottleneck-roadmap-surface.v1"
    assert surface["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert surface["contract_pass"] is True
    assert surface["read_model_ready"] is True
    assert surface["route"] == "/goal/bottleneck"
    assert surface["read_model"] == {
        "route": "/goal/bottleneck",
        "alternate_routes": ["/goal/roadmap"],
        "artifact": "implementation/phase1/release_evidence/productization/goal_bottleneck_roadmap_surface.json",
        "mutation_allowed": False,
    }
    assert surface["source_of_truth_gap_summary"] == {
        "candidate_count": 5,
        "fixed_count": 2,
        "aggregator_review_count": 3,
    }
    classification = {
        row["candidate"]: row
        for row in surface["source_of_truth_gap_classification"]
    }
    assert set(classification) == {
        "accuracy_parity_scorecard",
        "product_production_ai_checkpoint_readiness",
        "goal_readiness_rollup",
        "product_goal_completion_audit",
        "goal_operator_action_board",
    }
    assert classification["accuracy_parity_scorecard"]["classification"] == "fixed"
    assert classification["accuracy_parity_scorecard"]["freshness_label"] == (
        "accuracy_parity_scorecard"
    )
    assert classification["goal_operator_action_board"]["classification"] == (
        "aggregator-review"
    )
    assert classification["goal_operator_action_board"]["freshness_label"] == ""

    kpis = surface["release_decision_kpis"]
    assert kpis == {
        "approval_token_count": 8,
        "blocked_release_count": 9,
        "broad_gpcr_family_claim_safe": False,
        "evidence_surface_count": 12,
        "first_blocker": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "locked_evidence_surface_count": 3,
        "missing_evidence_surface_count": 0,
        "operator_action_count": 17,
        "pocketmd_lite_product_surface_ready": False,
        "public_benchmark_ready": False,
        "release_allowed": False,
        "stale_artifact_count": 0,
    }
    assert surface["science_evidence_surface_bottlenecks"] == [
        "h_bond_evidence_surface_locked",
        "broad_gpcr_family_claim_locked",
        "pocketmd_lite_science_product_surface_locked",
    ]
    assert surface["non_expert_release_briefing_ready"] is True
    briefing = surface["non_expert_release_briefing"]
    assert briefing["audience"] == "non_expert_pm_operator"
    assert briefing["release_allowed"] is False
    assert briefing["primary_release_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert briefing["refresh_required_operator_action_count"] == 0
    assert briefing["refresh_required_operator_actions"] == []
    assert briefing["release_area_blocker_count"] == 9
    assert briefing["release_area_owner_handoff_count"] == 9
    release_area_handoffs = {
        row["blocker_id"]: row
        for row in briefing["release_area_owner_handoffs"]
    }
    assert set(release_area_handoffs) == {
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
        "ux::human_new_user_observation_missing_or_failed",
        "ux::human_new_user_30min_sample_evidence_missing",
        "security::license_status_not_configured",
        "evidence_freshness::p1_benchmark_breadth_status::input_dependency_newer_than_artifact",
        "github_sync::github_sync_preflight::remote_mutation_approval_required",
        "github_sync::github_sync_remote_sync_pending",
        "github_sync::github_sync_preflight_not_synced",
    }
    ci_handoff = release_area_handoffs[
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    ]
    assert ci_handoff["owner"] == "release_ci_owner"
    assert ci_handoff["handoff_state"] == "external_owner_input_ready"
    assert ci_handoff["external_input_required"] is True
    assert ci_handoff["evidence_state"] == "missing_tracked_ci_streak_evidence"
    assert ci_handoff["acceptance_criteria_count"] == 4
    assert "ci_streak_intake_packet" in ci_handoff["evidence_artifact_keys"]
    ux_handoff = release_area_handoffs[
        "ux::human_new_user_observation_missing_or_failed"
    ]
    assert ux_handoff["owner"] == "ux_research_owner"
    assert ux_handoff["evidence_state"] == "missing_human_new_user_observation"
    assert "ux_new_user_observation_intake_packet" in ux_handoff[
        "evidence_artifact_keys"
    ]
    security_handoff = release_area_handoffs[
        "security::license_status_not_configured"
    ]
    assert security_handoff["owner"] == "product_legal_owner"
    assert security_handoff["evidence_state"] == "not_configured"
    github_handoff = release_area_handoffs[
        "github_sync::github_sync_preflight_not_synced"
    ]
    assert github_handoff["owner"] == "release_owner"
    assert github_handoff["evidence_state"] == "approval_required"
    assert github_handoff["handoff_state"] == "external_owner_input_ready"
    assert briefing["human_ux_blockers"] == [
        "ux::human_new_user_observation_missing_or_failed",
        "ux::human_new_user_30min_sample_evidence_missing",
    ]
    assert briefing["human_ux_owner_action"] == (
        "attach a passing human new-user observation record before claiming "
        "the UX release-area gate"
    )
    human_ux = briefing["human_ux_release_gate"]
    assert human_ux["status"] == "blocked"
    assert human_ux["release_area_blockers"] == briefing["human_ux_blockers"]
    assert human_ux["human_observation_contract_pass"] is False
    assert human_ux["human_observation_reason_code"] == (
        "ERR_UX_NEW_USER_OBSERVATION_REQUIRED"
    )
    assert human_ux["human_observation_blocker_count"] == 11
    assert human_ux["owner_intake_contract_pass"] is False
    assert human_ux["owner_intake_reason_code"] == (
        "ERR_UX_NEW_USER_OBSERVATION_OWNER_INPUT_REQUIRED"
    )
    assert human_ux["owner_intake_current_blocker_count"] == 11
    assert human_ux["missing_field_count"] == 13
    assert human_ux["workflow_step_pass_count"] == 0
    assert human_ux["required_workflow_step_count"] == 5
    assert human_ux["missing_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert human_ux["max_completion_minutes"] == 30
    assert "Automated rehearsal or templates do not close it" in human_ux[
        "plain_status"
    ]
    assert human_ux["evidence_artifacts"] == {
        "observation_report": (
            "implementation/phase1/release_evidence/productization/"
            "ux_new_user_observation_report.json"
        ),
        "owner_intake_packet": (
            "implementation/phase1/release_evidence/productization/"
            "ux_new_user_observation_intake_packet.json"
        ),
        "observation_source": (
            "implementation/phase1/release_evidence/productization/"
            "ux_new_user_observation.json"
        ),
        "template": "docs/templates/ux_new_user_observation.template.json",
    }
    assert any(
        "build_ux_new_user_observation_report.py" in command
        for command in human_ux["validation_commands"]
    )
    assert human_ux["claim_boundary"] == (
        "This report validates a human new-user observation record. Automated "
        "browser rehearsal evidence does not satisfy the PM UX release-area "
        "gate by itself."
    )
    assert briefing["primary_roadmap_bottleneck"] == (
        "public_benchmark_source_of_truth_not_ready"
    )
    assert briefing["blocked_science_or_beta_phase_count"] == 3
    assert [
        row["phase_id"] for row in briefing["blocked_science_or_beta_phases"]
    ] == [
        "phase_2_public_benchmark_harness",
        "phase_3_gpcr_hard_decoy_closure",
        "phase_4_pocketmd_lite",
    ]
    assert briefing["next_owner_handoff_count"] == 3
    assert briefing["first_operator_handoff"]["phase_id"] == (
        "phase_2_public_benchmark_harness"
    )
    assert briefing["claim_boundaries"] == [
        "do_not_claim_limited_commercial_release_until_release_allowed_true",
        "do_not_claim_tier_beta_until_public_benchmark_ready_true",
        "do_not_claim_broad_gpcr_until_broad_gpcr_family_claim_safe_true",
        "do_not_claim_pocketmd_lite_ready_until_product_surface_ready_true",
        "do_not_replace_human_ux_observation_with_templates_or_automation",
    ]
    assert surface["operator_evidence_handoff_scope"] == (
        "first_blocked_operator_gap_per_blocked_phase"
    )
    assert surface["operator_evidence_handoff_count"] == 3
    assert surface["first_operator_evidence_handoff"]["phase_id"] == (
        "phase_2_public_benchmark_harness"
    )
    assert surface["first_operator_evidence_handoff"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert surface["first_operator_evidence_handoff"]["first_blocker"] == (
        "casf_pdbbind_source_material_not_attached"
    )
    assert [
        row["phase_id"] for row in surface["operator_evidence_handoff_queue"]
    ] == [
        "phase_2_public_benchmark_harness",
        "phase_3_gpcr_hard_decoy_closure",
        "phase_4_pocketmd_lite",
    ]


def test_goal_bottleneck_roadmap_surface_promotes_stale_refresh_operator_action(
    monkeypatch,
) -> None:
    original_load_json = module._load_json
    pm_report = original_load_json(REPO_ROOT, module.DEFAULT_PM_REPORT)
    action_register = original_load_json(REPO_ROOT, module.DEFAULT_ACTION_REGISTER)

    stale_pm_report = copy.deepcopy(pm_report)
    decision = stale_pm_report["release_decision"]
    decision["stale_artifact_count"] = 2
    decision["operator_action_count"] = int(decision["operator_action_count"]) + 1
    decision["operator_actions"] = [
        {
            "action_id": "refresh_release_evidence_freshness",
            "status": "refresh_required",
            "reason": (
                "release_evidence_freshness_report has stale or incomplete "
                "source-of-truth blockers"
            ),
            "artifact": "release_evidence_freshness_report",
        },
        *decision["operator_actions"],
    ]

    stale_action_register = copy.deepcopy(action_register)
    stale_action_register["release_decision_operator_actions"] = [
        row
        for row in stale_action_register["release_decision_operator_actions"]
        if row["action_id"] != "refresh_release_evidence_freshness"
    ]

    def fake_load_json(repo_root: Path, path: Path) -> dict[str, object]:
        if path == module.DEFAULT_PM_REPORT:
            return copy.deepcopy(stale_pm_report)
        if path == module.DEFAULT_ACTION_REGISTER:
            return copy.deepcopy(stale_action_register)
        return original_load_json(repo_root, path)

    monkeypatch.setattr(module, "_load_json", fake_load_json)

    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)

    assert surface["release_decision_kpis"]["stale_artifact_count"] == 2
    assert "refresh_stale_goal_artifacts" in surface["next_actions"]
    actions = {
        row["action_id"]: row
        for row in surface["release_decision_operator_actions"]
    }
    refresh_action = actions["refresh_release_evidence_freshness"]
    assert refresh_action["status"] == "refresh_required"
    assert refresh_action["artifact"] == "release_evidence_freshness_report"
    briefing = surface["non_expert_release_briefing"]
    assert briefing["refresh_required_operator_action_count"] == 1
    assert briefing["refresh_required_operator_actions"] == [refresh_action]


def test_goal_bottleneck_roadmap_surface_links_phase_bottlenecks() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)
    rows = _row_by_phase(surface)

    assert rows["phase_0_source_of_truth_hardening"]["state"] == "ready"
    assert rows["phase_0_source_of_truth_hardening"]["summary"][
        "classification_rows"
    ][0] == {
        "candidate": "accuracy_parity_scorecard",
        "classification": "fixed",
        "freshness_policy": "direct_leaf_row",
        "freshness_label": "accuracy_parity_scorecard",
    }
    assert rows["phase_1_goal_release_cockpit"]["state"] == "ready"
    assert rows["phase_1_goal_release_cockpit"]["first_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    phase_1_summary = rows["phase_1_goal_release_cockpit"]["summary"]
    science_rows = {
        row["surface_family"]: row
        for row in phase_1_summary["science_evidence_surface_status_rows"]
    }
    assert set(science_rows) == {"h_bond", "gpcr", "pocketmd_lite"}
    assert phase_1_summary["first_locked_science_evidence_surface"][
        "surface_family"
    ] == "h_bond"
    assert science_rows["h_bond"] == {
        "bottleneck": "h_bond_evidence_surface_locked",
        "capability_blocker_count": 2,
        "capability_id": "h_bond_backmap_evidence",
        "capability_state": "blocked",
        "evidence_artifact_count": 3,
        "first_blocked_target": "operator_attached_h_bond_backmap_cases",
        "first_next_action": "fill_h_bond_backmap_operator_intake_packet",
        "locked": True,
        "locked_count": 1,
        "operator_intake_packet_status": "ready_for_operator_input",
        "operator_intake_required_slot_count": 3,
        "present": True,
        "root_cause_tags": [
            "operator_receipts_required",
            "operator_handoff_required",
        ],
        "status": "locked",
        "surface_count": 1,
        "surface_family": "h_bond",
        "surface_ids": ["h_bond_backmap_evidence_surface"],
    }
    assert science_rows["gpcr"]["bottleneck"] == "broad_gpcr_family_claim_locked"
    assert science_rows["gpcr"]["first_blocked_target"] == "DRD2"
    assert science_rows["gpcr"]["root_cause_tags"] == ["operator_values_required"]
    assert science_rows["gpcr"]["first_next_action"] == (
        "fill_gpcr_hard_decoy_operator_intake_packet"
    )
    assert science_rows["gpcr"]["operator_intake_required_slot_count"] == 3

    phase_2 = rows["phase_2_public_benchmark_harness"]
    assert phase_2["state"] == "blocked"
    assert phase_2["bottleneck"] == "public_benchmark_source_of_truth_not_ready"
    assert phase_2["first_blocker"] == "casf_pdbbind_source_material_not_attached"
    assert phase_2["first_blocked_target"] == "casf_pdbbind_subset_intake"
    assert phase_2["root_cause_tags"] == [
        "operator_source_material_required",
        "operator_receipts_required",
    ]
    assert phase_2["linked_routes"] == [
        "/product/public-benchmark",
        "/product/public-benchmark/operator-intake",
        "/product/capabilities",
    ]
    assert phase_2["summary"]["read_model_ready"] is True
    assert phase_2["summary"]["source_of_truth_route"] == "/product/public-benchmark"
    assert phase_2["summary"]["operator_intake_route"] == (
        "/product/public-benchmark/operator-intake"
    )
    assert phase_2["summary"]["gate_unblock_plan_count"] == 4
    assert phase_2["summary"]["operator_evidence_gap_count"] == 4
    assert phase_2["summary"]["first_operator_evidence_gap"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert phase_2["summary"]["first_operator_evidence_gap"][
        "blocked_tier_beta_criteria"
    ] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert phase_2["summary"]["minimum_subset_case_count"] == 12
    assert phase_2["summary"]["tier_beta_gate_status"] == "blocked"
    assert phase_2["summary"]["tier_beta_failed_criterion_count"] == 7
    assert phase_2["summary"]["tier_beta_failed_criteria"] == [
        "casf_pdbbind_subset_materialized",
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "dud_e_lit_pcba_enrichment_ready",
        "vina_gnina_comparison_ready",
        "external_receipts_attached",
    ]
    assert phase_2["blocked_criteria_count"] == 7
    assert phase_2["blocked_criteria"] == phase_2["summary"][
        "tier_beta_failed_criteria"
    ]
    assert [
        row["criterion_id"] for row in phase_2["summary"]["tier_beta_gate_criteria"]
    ] == [
        "casf_pdbbind_subset_materialized",
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "dud_e_lit_pcba_enrichment_ready",
        "vina_gnina_comparison_ready",
        "external_receipts_attached",
    ]
    assert all(
        row["pass"] is False for row in phase_2["summary"]["tier_beta_gate_criteria"]
    )
    assert {
        row["slot_id"]: row["status"]
        for row in phase_2["summary"]["operator_intake_slots"]
    } == {
        "casf_pdbbind_subset_intake": "operator_input_required",
        "pose_coordinate_intake": "operator_input_required",
        "dud_e_lit_pcba_enrichment_intake": "operator_input_required",
        "vina_gnina_comparison_intake": "operator_input_required",
    }
    gate_plan = {
        row["slot_id"]: row
        for row in phase_2["summary"]["gate_unblock_plan"]
    }
    assert gate_plan["casf_pdbbind_subset_intake"][
        "unblocks_tier_beta_criteria"
    ] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert gate_plan["pose_coordinate_intake"]["materialization_steps"] == [
        "materialize_pose_validity_input",
        "materialize_posebusters_validity_packet",
        "materialize_symmetry_rmsd_scorecard",
    ]
    gap_register = {
        row["slot_id"]: row
        for row in phase_2["summary"]["operator_evidence_gap_register"]
    }
    assert gap_register["pose_coordinate_intake"]["blocked_tier_beta_criteria"] == [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
    ]
    assert gap_register["casf_pdbbind_subset_intake"]["first_next_action"] == (
        "attach at least 12 local CASF/PDBBind case descriptors"
    )
    assert phase_2["summary"]["pose_validity_packet_summary"]["real_benchmark_case_count"] == 0
    assert phase_2["summary"]["symmetry_rmsd_scorecard_summary"] == {
        "status": "ready",
        "dry_run_case_count": 1,
        "real_benchmark_case_count": 0,
        "dry_run_pose_success": True,
    }
    assert phase_2["summary"]["vina_gnina_comparison_adapter_summary"][
        "real_comparison_case_count"
    ] == 0
    assert "attach_dud_e_lit_pcba_enrichment_intake" in phase_2["next_actions"]
    assert "attach_vina_gnina_comparison_intake" in phase_2["next_actions"]

    phase_3 = rows["phase_3_gpcr_hard_decoy_closure"]
    assert phase_3["state"] == "blocked"
    assert phase_3["bottleneck"] == "broad_gpcr_family_claim_locked"
    assert phase_3["first_blocker"] == "DRD2:ranking_pr_auc_ci_low_required"
    assert phase_3["first_blocked_target"] == "DRD2"
    assert phase_3["root_cause_tags"] == ["operator_values_required"]
    assert phase_3["linked_routes"] == [
        "/product/gpcr-hard-decoy-suite-report",
        "/product/gpcr-hard-decoy-suite-report/operator-intake",
        "/product/capabilities",
    ]
    assert (
        "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json"
        in phase_3["evidence_artifacts"]
    )
    assert phase_3["summary"]["operator_intake_packet_status"] == "ready_for_operator_input"
    assert phase_3["summary"]["product_report_route"] == (
        "/product/gpcr-hard-decoy-suite-report"
    )
    assert phase_3["summary"]["operator_intake_route"] == (
        "/product/gpcr-hard-decoy-suite-report/operator-intake"
    )
    assert phase_3["summary"]["operator_intake_required_slot_count"] == 3
    assert phase_3["summary"]["gate_unblock_plan_count"] == 3
    assert phase_3["summary"]["minimum_target_count"] == 3
    assert phase_3["summary"]["minimum_metric_field_count_per_target"] == 4
    assert phase_3["summary"]["operator_evidence_gap_count"] == 3
    assert phase_3["summary"]["first_operator_evidence_gap"]["slot_id"] == (
        "drd2_hard_decoy_metrics"
    )
    assert phase_3["summary"]["first_operator_evidence_gap"]["target_id"] == "DRD2"
    assert phase_3["summary"]["first_operator_evidence_gap"][
        "blocked_phase3_criteria"
    ] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert phase_3["summary"]["first_operator_evidence_gap"][
        "first_next_action"
    ] == "fill DRD2 hard-decoy metrics in the GPCR operator intake packet"
    assert phase_3["summary"]["phase3_exit_gate_status"] == "blocked"
    assert phase_3["summary"]["phase3_failed_criterion_count"] == 4
    assert phase_3["summary"]["phase3_failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert phase_3["blocked_criteria_count"] == 4
    assert phase_3["blocked_criteria"] == phase_3["summary"][
        "phase3_failed_criteria"
    ]
    assert [
        row["criterion_id"] for row in phase_3["summary"]["phase3_exit_gate_criteria"]
    ] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert phase_3["summary"]["phase3_exit_gate_criteria"][0][
        "current_by_target"
    ] == {"DRD2": None, "HTR2A": None, "OPRM1": None}
    assert phase_3["summary"]["phase3_exit_gate_criteria"][0][
        "failed_targets"
    ] == ["DRD2", "HTR2A", "OPRM1"]
    assert {
        row["target_id"]: row["status"]
        for row in phase_3["summary"]["operator_target_slots"]
    } == {
        "DRD2": "operator_input_required",
        "HTR2A": "operator_input_required",
        "OPRM1": "operator_input_required",
    }
    assert {
        row["target_id"]: row["phase3_blocked"]
        for row in phase_3["summary"]["operator_evidence_gap_register"]
    } == {"DRD2": True, "HTR2A": True, "OPRM1": True}
    gate_plan = {row["target_id"]: row for row in phase_3["summary"]["gate_unblock_plan"]}
    assert gate_plan["DRD2"]["slot_id"] == "drd2_hard_decoy_metrics"
    assert gate_plan["DRD2"]["status"] == "operator_input_required"
    assert gate_plan["DRD2"]["unblocks_phase3_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert gate_plan["DRD2"]["minimum_evidence"]["thresholds"][
        "decoys_above_positive_count"
    ] == "<=0"
    assert gate_plan["DRD2"]["materialization_steps"] == [
        "materialize_gpcr_hard_decoy_suite_report",
        "refresh_gpcr_hard_decoy_product_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert "fill_gpcr_hard_decoy_operator_intake_packet" in phase_3["next_actions"]

    phase_4 = rows["phase_4_pocketmd_lite"]
    assert phase_4["state"] == "blocked"
    assert phase_4["bottleneck"] == "pocketmd_lite_science_product_surface_locked"
    assert phase_4["first_blocker"] == "pocketmd_lite_topk_candidate_rows_missing"
    assert phase_4["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert phase_4["linked_routes"] == [
        "/product/pocketmd-lite",
        "/product/pocketmd-lite/operator-intake",
        "/product/pocketmd-lite/handoff",
        "/product/capabilities",
    ]
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_operator_intake_packet.json"
        in phase_4["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_readonly_api.json"
        in phase_4["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_delivery_handoff.json"
        in phase_4["evidence_artifacts"]
    )
    assert phase_4["summary"]["readonly_api_status"] == "ready_for_seed_artifacts"
    assert phase_4["summary"]["readonly_api_route"] == "/product/pocketmd-lite"
    assert phase_4["summary"]["readonly_api_endpoint_count"] == 6
    assert phase_4["summary"]["handoff_status"] == (
        "handoff_ready_operator_evidence_required"
    )
    assert phase_4["summary"]["handoff_route"] == "/product/pocketmd-lite/handoff"
    assert phase_4["summary"]["handoff_acceptance_criteria_count"] == 6
    assert phase_4["summary"]["handoff_phase4_exit_gate_required_status"] == "ready"
    assert phase_4["summary"]["operator_intake_packet_status"] == (
        "ready_for_operator_input"
    )
    assert phase_4["summary"]["operator_intake_route"] == (
        "/product/pocketmd-lite/operator-intake"
    )
    assert phase_4["summary"]["operator_intake_required_slot_count"] == 1
    assert phase_4["summary"]["gate_unblock_plan_count"] == 1
    assert phase_4["summary"]["minimum_refinement_case_count"] == 1
    assert phase_4["summary"]["minimum_top_k_candidate_count"] == 1
    assert phase_4["summary"]["operator_intake_slots"] == [
        {
            "required": True,
            "required_case_field_count": 14,
            "slot_id": "top_k_refinement_rows",
            "status": "operator_input_required",
        }
    ]
    assert phase_4["summary"]["operator_evidence_gap_count"] == 1
    assert phase_4["summary"]["first_operator_evidence_gap"]["slot_id"] == (
        "top_k_refinement_rows"
    )
    assert phase_4["summary"]["first_operator_evidence_gap"][
        "blocked_phase4_criteria"
    ] == [
        "top_k_refinement_rows_present",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert phase_4["summary"]["first_operator_evidence_gap"][
        "first_next_action"
    ] == "attach top-k candidate refinement rows"
    assert phase_4["summary"]["phase4_exit_gate_status"] == "blocked"
    assert phase_4["summary"]["phase4_failed_criterion_count"] == 7
    assert phase_4["summary"]["phase4_failed_criteria"] == [
        "top_k_refinement_rows_present",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert phase_4["blocked_criteria_count"] == 7
    assert phase_4["blocked_criteria"] == phase_4["summary"][
        "phase4_failed_criteria"
    ]
    gate_plan = phase_4["summary"]["gate_unblock_plan"][0]
    assert gate_plan["slot_id"] == "top_k_refinement_rows"
    assert gate_plan["status"] == "operator_input_required"
    assert gate_plan["unblocks_phase4_criteria"] == [
        "top_k_refinement_rows_present",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert gate_plan["materialization_steps"] == [
        "materialize_pocketmd_lite_topk_survival_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert "fill_pocketmd_lite_operator_intake_packet" in phase_4["next_actions"]
    assert "regenerate_goal_bottleneck_action_board" in phase_4["next_actions"]

    assert surface["primary_roadmap_bottleneck"] == "public_benchmark_source_of_truth_not_ready"
    assert surface["primary_roadmap_phase_id"] == "phase_2_public_benchmark_harness"


def test_goal_bottleneck_roadmap_surface_cli_writes_payload(tmp_path: Path) -> None:
    out = tmp_path / "productization" / "goal_bottleneck_roadmap_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["input_checksums"][
        "scripts/build_goal_bottleneck_roadmap_surface.py"
    ].startswith("sha256:")
    assert payload["reused_evidence"] is True
    assert payload["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert payload["primary_next_actions"][0] == "fill_public_benchmark_operator_intake_packet"
