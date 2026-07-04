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

spec = importlib.util.spec_from_file_location(
    "build_goal_bottleneck_roadmap_surface",
    SCRIPT_PATH,
)
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
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "goal_bottleneck_roadmap_surface.json"
        ),
        "mutation_allowed": False,
    }
    assert surface["source_of_truth_gap_summary"] == {
        "candidate_count": 5,
        "fix_count": 2,
        "fixed_count": 2,
        "no_op_count": 0,
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
    assert classification["accuracy_parity_scorecard"]["classification"] == "fix"
    assert classification["accuracy_parity_scorecard"]["freshness_label"] == (
        "accuracy_parity_scorecard"
    )
    assert "science_scorecard_overall_pass_field" in classification[
        "accuracy_parity_scorecard"
    ]["validation_basis"]
    assert classification["goal_operator_action_board"]["classification"] == (
        "aggregator-review"
    )
    assert classification["goal_operator_action_board"]["freshness_label"] == ""
    assert "not_closure_evidence_without_owner_receipts" in classification[
        "goal_operator_action_board"
    ]["validation_basis"]
    assert surface["source_of_truth_gap_evidence_matrix_count"] == 5
    evidence_matrix = {
        row["candidate"]: row
        for row in surface["source_of_truth_gap_evidence_matrix"]
    }
    assert set(evidence_matrix) == set(classification)
    assert evidence_matrix["accuracy_parity_scorecard"] == {
        "candidate": "accuracy_parity_scorecard",
        "classification": "fix",
        "contract_pass": True,
        "current_repo_paths": [
            "implementation/phase1/real_accuracy_validation_report.json"
        ],
        "failed_live_checks": [],
        "freshness_label": "accuracy_parity_scorecard",
        "freshness_policy": "direct_leaf_row",
        "operator_action": (
            "keep_accuracy_parity_scorecard_as_direct_freshness_leaf"
        ),
        "science_scorecard_priority_review": True,
        "source_tracking_mode": "direct_freshness_leaf",
        "source_tracking_verified": True,
        "status": "classified",
    }
    assert evidence_matrix["goal_operator_action_board"]["classification"] == (
        "aggregator-review"
    )
    assert evidence_matrix["goal_operator_action_board"][
        "source_tracking_mode"
    ] == "aggregator_upstream_source_tracking"
    assert evidence_matrix["goal_operator_action_board"][
        "source_tracking_verified"
    ] is True

    kpis = surface["release_decision_kpis"]
    pm_report = json.loads(
        (
            REPO_ROOT
            / "implementation/phase1/release_evidence/productization/"
            / "pm_release_gate_report.json"
        ).read_text(encoding="utf-8")
    )
    decision = pm_report["release_decision"]
    assert kpis == {
        key: decision[key]
        for key in (
            "release_allowed",
            "blocked_release_count",
            "first_blocker",
            "operator_action_count",
            "approval_token_count",
            "stale_artifact_count",
            "evidence_surface_count",
            "missing_evidence_surface_count",
            "locked_evidence_surface_count",
            "public_benchmark_ready",
        )
    }
    assert kpis["blocked_release_count"] == len(pm_report["full_release_blockers"])
    assert kpis["first_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert kpis["evidence_surface_count"] == 8
    assert kpis["locked_evidence_surface_count"] == 0
    assert kpis["missing_evidence_surface_count"] == 0
    assert surface["science_evidence_surface_bottlenecks"] == [
        "public_benchmark_vina_gnina_actual_rows_required",
        "pocketmd_lite_topk_actual_rows_required",
    ]
    science_status = surface["science_evidence_surface_status"]
    assert science_status["status"] == "operator_evidence_required"
    assert science_status["contract_pass"] is False
    assert science_status["missing_row_inputs"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]
    science_progress = science_status["completion_progress"]
    assert science_progress["complete_component_ids"] == [
        "gpcr_hard_decoy_actual_closure"
    ]
    assert science_progress["blocked_component_ids"] == [
        "public_benchmark_phase2_actual_closure",
        "pocketmd_lite_topk_actual_closure",
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

    release_area_handoffs = {
        row["blocker_id"]: row
        for row in briefing["release_area_owner_handoffs"]
    }
    assert set(release_area_handoffs) == set(pm_report["release_area_blockers"])
    required_release_area_handoffs = {
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
        "ux::human_new_user_observation_missing_or_failed",
        "ux::human_new_user_30min_sample_evidence_missing",
        "security::license_status_not_configured",
    }
    assert required_release_area_handoffs.issubset(release_area_handoffs)
    assert kpis["blocked_release_count"] >= len(required_release_area_handoffs)
    assert briefing["release_area_blocker_count"] == len(release_area_handoffs)
    assert briefing["release_area_owner_handoff_count"] == len(release_area_handoffs)

    ci_handoff = release_area_handoffs[
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    ]
    assert ci_handoff["owner"] == "release_ci_owner"
    assert ci_handoff["handoff_state"] == "external_owner_input_ready"
    assert ci_handoff["external_input_required"] is True
    assert ci_handoff["evidence_state"] == "self_hosted_runner_offline"
    assert "Bring at least one GitHub Actions self-hosted runner online" in ci_handoff[
        "owner_action"
    ]
    assert (
        "rerun the workflow" in ci_handoff["owner_action"]
        or "Open a pull request for this branch" in ci_handoff["owner_action"]
    )
    assert "collect 30 additional consecutive successful" in ci_handoff[
        "owner_action"
    ]
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
    assert human_ux["human_observation_blocker_count"] == 12
    assert human_ux["owner_intake_contract_pass"] is False
    assert human_ux["owner_intake_reason_code"] == (
        "ERR_UX_NEW_USER_OBSERVATION_OWNER_INPUT_REQUIRED"
    )
    assert human_ux["owner_intake_current_blocker_count"] == 12
    assert human_ux["missing_field_count"] == 14
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
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert briefing["primary_roadmap_phase_id"] == "phase_1_goal_release_cockpit"
    assert briefing["blocked_science_or_beta_phase_count"] == 2
    assert briefing["blocked_science_or_beta_phases"] == [
        {
            "phase_id": "phase_2_public_benchmark_actual_closure",
            "roadmap_item": "Public benchmark Phase 2 actual closure",
            "bottleneck": "public_benchmark_vina_gnina_actual_rows_required",
            "first_blocker": (
                "public_benchmark_phase2_actual_closure::"
                "vina_gnina_comparison_adapter::vina_gnina_rows_not_provided"
            ),
            "first_blocked_target": "public_benchmark_phase2_actual_closure",
        },
        {
            "phase_id": "phase_4_pocketmd_lite_topk_actual_closure",
            "roadmap_item": "PocketMD Lite top-k actual closure",
            "bottleneck": "pocketmd_lite_topk_actual_rows_required",
            "first_blocker": (
                "pocketmd_lite_topk_actual_closure::pocketmd_rows_not_provided"
            ),
            "first_blocked_target": "pocketmd_lite_topk_actual_closure",
        },
    ]
    assert briefing["next_owner_handoff_count"] == 2
    assert briefing["first_operator_handoff"]["slot_id"] == "vina_gnina_rows"
    assert briefing["first_operator_handoff"][
        "actual_evidence_audit_status"
    ] == "engine_input_manifest_required"
    assert briefing["next_owner_handoff_slot_count"] == 2
    assert briefing["first_operator_handoff_slot"]["slot_id"] == "vina_gnina_rows"
    assert briefing["first_operator_handoff_slot"][
        "blocked_criteria"
    ] == ["vina_gnina_comparison_ready"]
    assert briefing["claim_boundaries"] == [
        "do_not_claim_limited_commercial_release_until_release_allowed_true",
        "do_not_replace_human_ux_observation_with_templates_or_automation",
        "do_not_claim_science_actual_closure_until_operator_rows_pass",
    ]
    assert surface["operator_evidence_handoff_count"] == 2
    handoffs = {
        row["slot_id"]: row for row in surface["operator_evidence_handoff_queue"]
    }
    assert sorted(handoffs) == ["pocketmd_rows", "vina_gnina_rows"]
    assert handoffs["vina_gnina_rows"]["queue_priority"] == 1
    assert handoffs["vina_gnina_rows"]["template_artifact"].endswith(
        "public_benchmark_vina_gnina_rows_template.csv"
    )
    assert handoffs["vina_gnina_rows"]["first_next_action"] == (
        "complete_vina_gnina_input_manifest_required_values"
    )
    assert handoffs["vina_gnina_rows"]["command_key"] == (
        "build_input_manifest_template_preflight"
    )
    assert (
        "build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"
        in handoffs["vina_gnina_rows"]["materialization_command"]
    )
    assert handoffs["vina_gnina_rows"]["first_unblock_action"][
        "action_source"
    ] == "first_operator_blocker_family"
    assert handoffs["vina_gnina_rows"]["first_unblock_action"][
        "first_missing_item"
    ]["field"] == "prepared_receptor_checksum"
    assert handoffs["vina_gnina_rows"][
        "runtime_blocker_family_action_count"
    ] == 7
    assert [
        row["family_id"]
        for row in handoffs["vina_gnina_rows"]["runtime_blocker_family_actions"]
    ] == [
        "manifest_required_values",
        "official_source_files",
        "prepared_input_files",
        "input_and_engine_receipt_refs",
        "engine_runtime",
        "engine_run_slots",
        "adapter_rows",
    ]
    assert handoffs["vina_gnina_rows"][
        "actual_evidence_audit_status"
    ] == "engine_input_manifest_required"
    assert handoffs["vina_gnina_rows"][
        "actual_evidence_blocked_component_count"
    ] == 6
    assert "engine_input_manifest" in handoffs["vina_gnina_rows"][
        "actual_evidence_remaining_evidence"
    ]
    assert handoffs["pocketmd_rows"]["queue_priority"] == 2
    assert handoffs["pocketmd_rows"]["template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert handoffs["pocketmd_rows"]["first_next_action"] == (
        "fill_completion_missing_required_fields_and_set_status_complete"
    )
    assert handoffs["pocketmd_rows"]["command_key"] == "rerun_rows_materialization"
    assert (
        "materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py"
        in handoffs["pocketmd_rows"]["materialization_command"]
    )
    assert handoffs["pocketmd_rows"]["first_unblock_action"][
        "action_source"
    ] == "first_incomplete_receipt"
    assert handoffs["pocketmd_rows"]["first_unblock_action"][
        "receipt_ref"
    ].endswith("pocketmd_lite_case_001/rank_01_refinement_receipt.json")
    assert "upstream_top_k_provenance_ref" in handoffs["pocketmd_rows"][
        "first_unblock_action"
    ]["missing_receipt_fields"]
    assert handoffs["pocketmd_rows"]["first_metric_family_action"][
        "metric_family_id"
    ] == "local_min_survival"
    assert handoffs["pocketmd_rows"]["first_metric_family_action"][
        "phase4_criterion_id"
    ] == "local_min_survival_materialized"
    assert handoffs["pocketmd_rows"]["first_metric_family_action"][
        "first_blocked_receipt"
    ]["receipt_ref"].endswith(
        "pocketmd_lite_case_001/rank_01_refinement_receipt.json"
    )
    assert handoffs["pocketmd_rows"][
        "refinement_receipt_completion_action_count"
    ] == 6
    assert handoffs["pocketmd_rows"][
        "refinement_metric_family_action_count"
    ] == 5
    assert [
        row["metric_family_id"]
        for row in handoffs["pocketmd_rows"]["refinement_metric_family_actions"]
    ] == [
        "local_min_survival",
        "contact_persistence",
        "h_bond_persistence",
        "clash_relief",
        "uncertainty",
    ]
    assert handoffs["pocketmd_rows"][
        "actual_evidence_audit_status"
    ] == "operator_topk_rows_required"
    assert handoffs["pocketmd_rows"]["actual_evidence_blocked_component_count"] == 4
    assert "bounded_top_k_row_slots" in handoffs["pocketmd_rows"][
        "actual_evidence_remaining_evidence"
    ]
    assert surface["operator_evidence_handoff_slot_count"] == 2
    slots = {
        row["slot_id"]: row for row in surface["operator_evidence_handoff_slot_queue"]
    }
    assert sorted(slots) == ["pocketmd_rows", "vina_gnina_rows"]
    assert slots["vina_gnina_rows"]["first_next_action"] == (
        "complete_vina_gnina_input_manifest_required_values"
    )
    assert slots["vina_gnina_rows"]["command_key"] == (
        "build_input_manifest_template_preflight"
    )
    assert slots["vina_gnina_rows"]["runtime_blocker_family_action_count"] == 7
    assert slots["pocketmd_rows"]["first_next_action"] == (
        "fill_completion_missing_required_fields_and_set_status_complete"
    )
    assert slots["pocketmd_rows"]["command_key"] == "rerun_rows_materialization"
    assert slots["pocketmd_rows"]["refinement_metric_family_action_count"] == 5
    assert slots["pocketmd_rows"]["blocked_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]


def test_goal_bottleneck_surface_exposes_active_thread_goal_audit() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)

    audit = surface["active_thread_goal_objective_audit"]
    assert audit["scope_policy"] == "current_thread_goal_objective_only"
    assert audit["status"] == "operator_evidence_required"
    assert audit["actual_closure_ready"] is False
    assert audit["priority_count"] == 4
    assert audit["complete_priority_count"] == 2
    assert audit["blocked_priority_count"] == 2
    assert audit["complete_priority_ids"] == [
        "priority_1_source_of_truth_gap_classification",
        "priority_3_gpcr_hard_decoy_actual_closure",
    ]
    assert audit["blocked_priority_ids"] == [
        "priority_2_public_benchmark_phase2_actual_closure",
        "priority_4_pocketmd_lite_topk_refinement",
    ]
    assert audit["operator_row_inputs_required"] == [
        "vina_gnina_rows",
        "pocketmd_rows",
    ]

    rows = {row["priority_id"]: row for row in audit["priority_rows"]}
    source = rows["priority_1_source_of_truth_gap_classification"]
    assert source["state"] == "complete"
    assert source["pass"] is True
    assert source["current"]["candidate_count"] == 5
    assert source["current"]["fix_count"] == 2
    assert source["current"]["aggregator_review_count"] == 3
    assert source["current"]["accuracy_parity_scorecard_classification"] == "fix"
    assert source["current"][
        "accuracy_parity_scorecard_science_scorecard_priority_review"
    ] is True

    public = rows["priority_2_public_benchmark_phase2_actual_closure"]
    assert public["state"] == "blocked"
    assert public["current"]["requirement_count"] == 5
    assert public["current"]["requirement_pass_count"] == 4
    assert public["current"]["completion_audit_status"] == "blocked"
    assert public["current"]["completion_requirement_count"] == 6
    assert public["current"]["completion_requirement_pass_count"] == 4
    assert public["current"]["completion_blocker_count"] == 2
    assert public["current"]["completion_blocked_requirement_ids"] == [
        "vina_gnina_comparison_ready",
        "public_benchmark_source_actuality_ready",
    ]
    assert public["current"]["source_actuality_scope"] == "provided_row_inputs_only"
    assert public["current"]["source_actuality_scope_complete"] is False
    assert public["current"]["source_actuality_missing_row_inputs"] == [
        "vina_gnina_rows"
    ]
    assert public["current"]["missing_row_inputs"] == ["vina_gnina_rows"]
    assert public["current"]["input_manifest_detected"] is True
    assert public["current"]["input_manifest_syntax_ready"] is True
    assert public["current"]["input_manifest_verification_status"] == (
        "syntactic_manifest_detected_but_case_inputs_unverified"
    )
    assert public["current"]["verified_case_input_count"] == 0
    assert public["current"]["template_completion_blocked_case_count"] == 12
    assert public["current"]["missing_engine_ids"] == ["vina", "gnina"]
    assert "public_benchmark_vina_gnina_case_input_files_or_receipts_unverified" in (
        public["blockers"]
    )
    assert "vina_gnina_rows_not_provided" in public["blockers"]
    assert (
        "public_benchmark_source_actuality_ready::"
        "source_actuality_scope_incomplete:vina_gnina_rows"
    ) in public["blockers"]

    gpcr = rows["priority_3_gpcr_hard_decoy_actual_closure"]
    assert gpcr["state"] == "complete"
    assert gpcr["current"]["requirement_pass_count"] == 5
    assert gpcr["current"]["target_pass_count"] == 3
    assert gpcr["current"]["criteria"]["ranking_pr_auc_ci_low_min"][
        "required"
    ] == ">=0.45"
    assert gpcr["current"]["criteria"]["top20_hit_rate_min"][
        "current_by_target"
    ] == {"DRD2": 0.6, "HTR2A": 0.6, "OPRM1": 0.6}
    assert gpcr["current"]["criteria"]["decoys_above_positive_count_max"][
        "current_by_target"
    ] == {"DRD2": 0, "HTR2A": 0, "OPRM1": 0}
    assert gpcr["current"]["criteria"]["no_positive_out_anchored_by_top_decoys"][
        "current_by_target"
    ] == {"DRD2": False, "HTR2A": False, "OPRM1": False}

    pocketmd = rows["priority_4_pocketmd_lite_topk_refinement"]
    assert pocketmd["state"] == "blocked"
    assert pocketmd["current"]["requirement_count"] == 9
    assert pocketmd["current"]["requirement_pass_count"] == 1
    assert pocketmd["current"]["survival_completion_audit_status"] == "blocked"
    assert pocketmd["current"]["survival_completion_requirement_count"] == 10
    assert pocketmd["current"]["survival_completion_requirement_pass_count"] == 1
    assert pocketmd["current"]["survival_completion_blocker_count"] == 14
    assert pocketmd["current"]["survival_completion_blocked_requirement_ids"] == [
        "operator_input_source_receipt_pass",
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert pocketmd["current"]["ready_requirement_count"] == 2
    assert pocketmd["current"]["missing_row_inputs"] == ["pocketmd_rows"]
    assert pocketmd["current"]["missing_candidate_slot_count"] == 6
    assert pocketmd["current"]["receipt_metric_family_blocked_count"] == 5
    assert pocketmd["current"][
        "receipt_metric_family_missing_field_occurrence_count"
    ] == 54
    assert pocketmd["current"]["operator_blocker_family_count"] == 8
    assert pocketmd["current"]["operator_blocker_family_blocked_count"] == 8
    assert pocketmd["current"]["operator_blocker_family_missing_item_count"] == 89
    assert pocketmd["current"]["ready_receipt_count"] == 0
    assert pocketmd["current"]["incomplete_receipt_count"] == 6
    assert "pocketmd_lite_local_min_survival_rows_missing" in pocketmd["blockers"]
    assert (
        "operator_input_source_receipt_pass::operator_input_source_receipt_required"
        in pocketmd["blockers"]
    )


def test_goal_bottleneck_surface_uses_science_closure_aggregate_not_raw_rows(
    monkeypatch,
) -> None:
    original_load_json = module._load_json
    loaded_paths: list[str] = []

    def tracking_load_json(repo_root: Path, path: Path) -> dict[str, object]:
        loaded_paths.append(path.as_posix())
        return original_load_json(repo_root, path)

    monkeypatch.setattr(module, "_load_json", tracking_load_json)

    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)
    forbidden_path_fragments = (
        "gpcr_hard_decoy_rows",
        "public_benchmark_vina_gnina_rows",
        "pocketmd_lite_topk_rows",
        "md3bead",
    )

    assert hasattr(module, "_science_actual_closure_rows")
    assert module.DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF.as_posix() in (
        loaded_paths
    )
    assert module.DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT.as_posix() in loaded_paths
    assert module.DEFAULT_PUBLIC_BENCHMARK_PHASE2_ROW_AUDIT.as_posix() in loaded_paths
    assert module.DEFAULT_POCKETMD_TOPK_SURVIVAL_REPORT.as_posix() in loaded_paths
    assert not any(
        fragment in path.lower()
        for path in loaded_paths
        for fragment in forbidden_path_fragments
    )
    rows = _row_by_phase(surface)
    assert rows["phase_3_gpcr_hard_decoy_actual_closure"]["state"] == "ready"
    assert rows["phase_4_pocketmd_lite_topk_actual_closure"]["state"] == "blocked"


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


def test_goal_bottleneck_roadmap_surface_links_structural_release_bottleneck() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)
    rows = _row_by_phase(surface)

    assert set(rows) == {
        "phase_0_source_of_truth_hardening",
        "phase_1_goal_release_cockpit",
        "phase_2_public_benchmark_actual_closure",
        "phase_3_gpcr_hard_decoy_actual_closure",
        "phase_4_pocketmd_lite_topk_actual_closure",
    }
    assert rows["phase_0_source_of_truth_hardening"]["state"] == "ready"
    phase_1 = rows["phase_1_goal_release_cockpit"]
    assert phase_1["state"] == "blocked"
    assert phase_1["bottleneck"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert phase_1["first_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    kpis = surface["release_decision_kpis"]
    assert phase_1["summary"] == {
        "release_allowed": kpis["release_allowed"],
        "blocked_release_count": kpis["blocked_release_count"],
        "operator_action_count": kpis["operator_action_count"],
        "approval_token_count": kpis["approval_token_count"],
        "action_register_contract_pass": False,
        "product_capability_count": 1,
        "blocked_capability_count": 0,
    }
    assert phase_1["next_actions"] == ["work_release_decision_operator_actions"]
    phase_2 = rows["phase_2_public_benchmark_actual_closure"]
    assert phase_2["state"] == "blocked"
    assert phase_2["bottleneck"] == (
        "public_benchmark_vina_gnina_actual_rows_required"
    )
    assert phase_2["summary"]["missing_row_inputs"] == ["vina_gnina_rows"]
    assert phase_2["summary"]["actual_evidence_audit_status"] == (
        "engine_input_manifest_required"
    )
    assert phase_2["summary"]["operator_evidence_gap_register"][0]["slot_id"] == (
        "vina_gnina_rows"
    )
    phase2_gate = phase_2["summary"]["component_gate_summary"]
    assert phase2_gate["phase2_exit_gate_status"] == "blocked"
    assert phase2_gate["phase2_ready"] is False
    assert phase2_gate["phase2_failed_criteria"] == ["vina_gnina_comparison_ready"]
    assert phase2_gate["phase2_requirement_summary"] == {
        "blocked_component_count": 1,
        "blocked_component_ids": ["vina_gnina_comparison_adapter"],
        "materialized_component_count": 4,
        "missing_row_input_count": 1,
        "missing_row_inputs": ["vina_gnina_rows"],
        "operator_evidence_required_count": 1,
        "phase2_ready": False,
        "ready_component_count": 4,
        "required_component_count": 5,
    }
    phase2_requirements = {
        row["component_id"]: row
        for row in phase2_gate["phase2_requirements"]
    }
    assert phase2_requirements["casf_pdbbind_pose_success_harness"][
        "requirement"
    ] == "CASF/PDBBind pose-success harness"
    assert phase2_requirements["casf_pdbbind_pose_success_harness"]["ready"] is True
    assert phase2_requirements["casf_pdbbind_pose_success_harness"]["pass"] is True
    assert phase2_requirements["symmetry_aware_ligand_rmsd"][
        "requirement"
    ] == "Symmetry-aware ligand RMSD scorecard"
    assert phase2_requirements["symmetry_aware_ligand_rmsd"]["ready"] is True
    assert phase2_requirements["symmetry_aware_ligand_rmsd"]["pass"] is True
    assert phase2_requirements["posebusters_style_pose_validity"][
        "requirement"
    ] == "PoseBusters-style pose validity packet"
    assert phase2_requirements["posebusters_style_pose_validity"]["ready"] is True
    assert phase2_requirements["posebusters_style_pose_validity"]["pass"] is True
    assert phase2_requirements["dud_e_or_lit_pcba_enrichment"][
        "requirement"
    ] == "DUD-E or LIT-PCBA enrichment scorecard"
    assert phase2_requirements["dud_e_or_lit_pcba_enrichment"]["ready"] is True
    assert phase2_requirements["dud_e_or_lit_pcba_enrichment"]["pass"] is True
    vina_requirement = phase2_requirements["vina_gnina_comparison_adapter"]
    assert vina_requirement["requirement"] == "Vina/GNINA comparison adapter"
    assert vina_requirement["ready"] is False
    assert vina_requirement["pass"] is False
    assert vina_requirement["operator_evidence_required"] is True
    assert vina_requirement["row_input_status"] == {"vina_gnina_rows": "missing"}
    assert vina_requirement["blockers"] == ["vina_gnina_rows_not_provided"]
    phase2_row_inputs = {
        row["row_input_id"]: row
        for row in phase2_gate["phase2_row_closure_matrix"]
    }
    assert phase2_row_inputs["subset_rows"]["status"] == "provided"
    assert phase2_row_inputs["pose_rows"]["status"] == "provided"
    assert phase2_row_inputs["enrichment_rows"]["status"] == "provided"
    assert phase2_row_inputs["vina_gnina_rows"]["status"] == "missing"
    assert phase2_row_inputs["vina_gnina_rows"]["operator_blockers_if_missing"] == [
        "vina_gnina_comparison_adapter::vina_gnina_rows_not_provided"
    ]
    phase_3 = rows["phase_3_gpcr_hard_decoy_actual_closure"]
    assert phase_3["state"] == "ready"
    assert phase_3["summary"]["actual_closure_ready"] is True
    assert phase_3["summary"]["requirement_pass_count"] == 5
    phase3_gate = phase_3["summary"]["phase3_exit_gate"]
    assert phase3_gate["phase3_exit_gate_status"] == "ready"
    assert phase3_gate["phase3_failed_criteria"] == []
    phase3_criteria = {
        row["criterion_id"]: row
        for row in phase3_gate["phase3_exit_gate_criteria"]
    }
    assert phase3_criteria["ranking_pr_auc_ci_low_min"] == {
        "blockers": [],
        "criterion_id": "ranking_pr_auc_ci_low_min",
        "current_by_target": {"DRD2": 1.0, "HTR2A": 1.0, "OPRM1": 1.0},
        "failed_targets": [],
        "pass": True,
        "required": ">=0.45",
    }
    assert phase3_criteria["top20_hit_rate_min"] == {
        "blockers": [],
        "criterion_id": "top20_hit_rate_min",
        "current_by_target": {"DRD2": 0.6, "HTR2A": 0.6, "OPRM1": 0.6},
        "failed_targets": [],
        "pass": True,
        "required": ">=0.2",
    }
    assert phase3_criteria["decoys_above_positive_count_max"] == {
        "blockers": [],
        "criterion_id": "decoys_above_positive_count_max",
        "current_by_target": {"DRD2": 0, "HTR2A": 0, "OPRM1": 0},
        "failed_targets": [],
        "pass": True,
        "required": "<=0",
    }
    assert phase3_criteria["no_positive_out_anchored_by_top_decoys"] == {
        "blockers": [],
        "criterion_id": "no_positive_out_anchored_by_top_decoys",
        "current_by_target": {"DRD2": False, "HTR2A": False, "OPRM1": False},
        "failed_targets": [],
        "pass": True,
        "required": False,
    }
    assert phase_3["summary"]["component_gate_summary"]["rows_path"].endswith(
        "gpcr_hard_decoy_rows.json"
    )
    assert phase_3["summary"]["component_gate_summary"]["target_pass_count"] == 3
    phase_4 = rows["phase_4_pocketmd_lite_topk_actual_closure"]
    assert phase_4["state"] == "blocked"
    assert phase_4["bottleneck"] == "pocketmd_lite_topk_actual_rows_required"
    assert phase_4["summary"]["missing_row_inputs"] == ["pocketmd_rows"]
    assert phase_4["summary"]["actual_evidence_audit_status"] == (
        "operator_topk_rows_required"
    )
    assert phase_4["summary"]["operator_evidence_gap_register"][0]["slot_id"] == (
        "pocketmd_rows"
    )
    phase4_gate = phase_4["summary"]["phase4_exit_gate"]
    assert phase4_gate["phase4_exit_gate_status"] == "blocked"
    assert phase4_gate["phase4_operator_status"] == "operator_topk_rows_required"
    assert phase4_gate["phase4_ready"] is False
    assert phase4_gate["phase4_failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert phase4_gate["phase4_requirement_summary"] == {
        "actual_closure_ready": False,
        "blocked_requirement_count": 7,
        "blocked_requirement_ids": [
            "top_k_refinement_rows_present",
            "top_k_refinement_case_coverage",
            "local_min_survival_reported",
            "contact_persistence_reported",
            "h_bond_persistence_reported",
            "clash_relief_reported",
            "uncertainty_reported",
        ],
        "phase4_actual_evidence_audit_status": "operator_topk_rows_required",
        "phase4_actual_evidence_blocked_component_count": 4,
        "phase4_actual_evidence_missing_metric_count": 5,
        "phase4_missing_candidate_slot_count": 6,
        "ready_requirement_count": 2,
        "remaining_blockers": [
            "pocketmd_lite_topk_rows_not_acquired",
            "pocketmd_lite_topk_candidate_rows_missing",
            "pocketmd_lite_local_min_survival_rows_missing",
            "pocketmd_lite_contact_persistence_rows_missing",
            "pocketmd_lite_h_bond_persistence_rows_missing",
            "pocketmd_lite_clash_relief_rows_missing",
            "pocketmd_lite_uncertainty_rows_missing",
            "pocketmd_lite_topk_rows_not_provided",
        ],
        "remaining_operator_action": (
            "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
            "productization/pocketmd_lite_topk_rows.json"
        ),
        "remaining_row_inputs": ["pocketmd_rows"],
        "requirement_count": 9,
    }
    phase4_criteria = {
        row["criterion_id"]: row
        for row in phase4_gate["phase4_exit_gate_criteria"]
    }
    assert list(phase4_criteria) == phase4_gate["phase4_failed_criteria"]
    assert phase4_criteria["top_k_refinement_rows_present"]["current"] == {
        "required_candidate_slot_count": 6,
        "row_artifact_detected": False,
        "validated_row_count": 0,
    }
    assert phase4_criteria["top_k_refinement_case_coverage"]["required"] == {
        "coverage_ready": True,
        "min_real_refinement_case_count": 3,
        "min_total_top_k_candidate_count": 6,
    }
    expected_phase4_metrics = {
        "local_min_survival_materialized": (
            "local_min_survival_reported",
            "local_min_survival_rate",
            "pocketmd_lite_local_min_survival_rows_missing",
        ),
        "contact_persistence_materialized": (
            "contact_persistence_reported",
            "contact_persistence_rate_median",
            "pocketmd_lite_contact_persistence_rows_missing",
        ),
        "h_bond_persistence_materialized": (
            "h_bond_persistence_reported",
            "h_bond_persistence_rate_median",
            "pocketmd_lite_h_bond_persistence_rows_missing",
        ),
        "clash_relief_materialized": (
            "clash_relief_reported",
            "clash_relief_rate",
            "pocketmd_lite_clash_relief_rows_missing",
        ),
        "uncertainty_summary_materialized": (
            "uncertainty_reported",
            "uncertainty_width_median",
            "pocketmd_lite_uncertainty_rows_missing",
        ),
    }
    for criterion_id, (requirement_id, summary_field, blocker) in (
        expected_phase4_metrics.items()
    ):
        metric = phase4_criteria[criterion_id]
        assert metric["requirement_id"] == requirement_id
        assert metric["summary_field"] == summary_field
        assert metric["current"]["summary_value"] is None
        assert metric["current"]["survival_report_contract_pass"] is False
        assert metric["pass"] is False
        assert blocker in metric["blockers"]
    assert phase4_criteria["report_blockers_resolved"]["receipt_roles"] == [
        "lite_refinement_run_receipt",
        "interaction_persistence_receipt",
        "uncertainty_interval_receipt",
    ]
    phase4_requirements = {
        row["requirement_id"]: row
        for row in phase4_gate["phase4_requirements"]
    }
    assert len(phase4_requirements) == 9
    assert phase4_requirements["bounded_top_k_scope_contract"]["pass"] is True
    assert phase4_requirements["broad_all_atom_fep_claims_locked"]["pass"] is True
    assert phase4_requirements["local_min_survival_reported"]["blocker_id"] == (
        "pocketmd_lite_local_min_survival_rows_missing"
    )
    assert phase4_gate["phase4_candidate_slot_summary"] == {
        "candidate_slot_count": 6,
        "missing_candidate_slot_count": 6,
        "missing_candidate_slot_ids": [
            "pocketmd_lite_case_001_rank_1",
            "pocketmd_lite_case_001_rank_2",
            "pocketmd_lite_case_002_rank_1",
            "pocketmd_lite_case_002_rank_2",
            "pocketmd_lite_case_003_rank_1",
            "pocketmd_lite_case_003_rank_2",
        ],
    }
    assert surface["primary_roadmap_bottleneck"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert surface["primary_roadmap_phase_id"] == "phase_1_goal_release_cockpit"


def test_goal_bottleneck_roadmap_surface_cli_writes_payload(tmp_path: Path) -> None:
    out = tmp_path / "productization" / "goal_bottleneck_roadmap_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "goal-bottleneck-roadmap-surface.v1"
    assert payload["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert payload["summary_line"].startswith("Goal bottleneck roadmap surface: READY")
