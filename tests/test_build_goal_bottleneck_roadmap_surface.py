from __future__ import annotations

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

    phase_2 = rows["phase_2_public_benchmark_harness"]
    assert phase_2["state"] == "blocked"
    assert phase_2["bottleneck"] == "public_benchmark_source_of_truth_not_ready"
    assert phase_2["first_blocker"] == "casf_pdbbind_source_material_not_attached"
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
    assert phase_3["summary"]["phase3_exit_gate_status"] == "blocked"
    assert phase_3["summary"]["phase3_failed_criterion_count"] == 4
    assert phase_3["summary"]["phase3_failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
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
    assert "fill_gpcr_hard_decoy_operator_intake_packet" in phase_3["next_actions"]

    phase_4 = rows["phase_4_pocketmd_lite"]
    assert phase_4["state"] == "blocked"
    assert phase_4["bottleneck"] == "pocketmd_lite_science_product_surface_locked"
    assert phase_4["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert phase_4["linked_routes"] == [
        "/product/pocketmd-lite",
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
    assert phase_4["summary"]["operator_intake_required_slot_count"] == 1
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
