from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_product_capabilities_surface.py"
PM_REPORT_PATH = REPO_ROOT / "scripts" / "report_pm_release_gate.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_product_capabilities_surface", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

pm_spec = importlib.util.spec_from_file_location("report_pm_release_gate", PM_REPORT_PATH)
assert pm_spec is not None
pm_report = importlib.util.module_from_spec(pm_spec)
assert pm_spec.loader is not None
sys.modules[pm_spec.name] = pm_report
pm_spec.loader.exec_module(pm_report)


def _capability_by_id(surface: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = surface["capability_rows"]
    assert isinstance(rows, list)
    return {
        str(row["capability_id"]): row
        for row in rows
        if isinstance(row, dict) and "capability_id" in row
    }


def test_product_capabilities_surface_exposes_science_and_benchmark_rows() -> None:
    surface = module.build_product_capabilities_surface(repo_root=REPO_ROOT)
    rows = _capability_by_id(surface)

    assert surface["schema_version"] == "product-capabilities-surface.v1"
    assert surface["surface_id"] == "product_capabilities_surface"
    assert surface["surface_kind"] == "product_capabilities_surface"
    assert surface["status"] == "ready"
    assert surface["reason_code"] == "PASS"
    assert surface["contract_pass"] is True
    assert surface["locked"] is False
    assert surface["claim_locked"] is False
    assert surface["blockers"] == []
    assert surface["read_model"] == {
        "route": "/product/capabilities",
        "artifact": "implementation/phase1/release_evidence/surface/product_capabilities_surface.json",
        "mutation_allowed": False,
    }

    assert {
        "structural_solver_restricted_alpha_surface",
        "public_benchmark_harness",
        "h_bond_backmap_evidence",
        "gpcr_hard_decoy_evidence",
        "pocketmd_lite_top_k_refinement",
    } <= set(rows)

    public_benchmark = rows["public_benchmark_harness"]
    assert public_benchmark["state"] == "blocked"
    assert public_benchmark["summary"]["read_model_ready"] is True
    assert public_benchmark["summary"]["source_of_truth_route"] == (
        "/product/public-benchmark"
    )
    assert public_benchmark["summary"]["public_benchmark_ready"] is False
    assert public_benchmark["summary"]["operator_intake_route"] == (
        "/product/public-benchmark/operator-intake"
    )
    assert public_benchmark["summary"]["operator_intake_packet_status"] == (
        "ready_for_operator_input"
    )
    assert public_benchmark["summary"]["operator_intake_required_slot_count"] == 4
    assert public_benchmark["summary"]["gate_unblock_plan_count"] == 4
    assert public_benchmark["summary"]["operator_evidence_gap_count"] == 4
    assert public_benchmark["summary"]["first_operator_evidence_gap"]["slot_id"] == (
        "casf_pdbbind_subset_intake"
    )
    assert public_benchmark["summary"]["first_operator_evidence_gap"][
        "blocked_tier_beta_criteria"
    ] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert public_benchmark["summary"]["minimum_subset_case_count"] == 12
    assert public_benchmark["summary"]["tier_beta_gate_status"] == "blocked"
    assert public_benchmark["summary"]["tier_beta_failed_criterion_count"] == 7
    assert [
        row["criterion_id"]
        for row in public_benchmark["summary"]["tier_beta_gate_criteria"]
    ] == [
        "casf_pdbbind_subset_materialized",
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "dud_e_lit_pcba_enrichment_ready",
        "vina_gnina_comparison_ready",
        "external_receipts_attached",
    ]
    assert {
        row["slot_id"]: row["status"]
        for row in public_benchmark["summary"]["operator_intake_slots"]
    } == {
        "casf_pdbbind_subset_intake": "operator_input_required",
        "pose_coordinate_intake": "operator_input_required",
        "dud_e_lit_pcba_enrichment_intake": "operator_input_required",
        "vina_gnina_comparison_intake": "operator_input_required",
    }
    gate_plan = {
        row["slot_id"]: row
        for row in public_benchmark["summary"]["gate_unblock_plan"]
    }
    assert gate_plan["casf_pdbbind_subset_intake"][
        "unblocks_tier_beta_criteria"
    ] == [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ]
    assert gate_plan["casf_pdbbind_subset_intake"]["minimum_evidence"][
        "case_count"
    ] == 12
    assert gate_plan["dud_e_lit_pcba_enrichment_intake"][
        "materialization_steps"
    ] == ["materialize_enrichment_scorecard"]
    gap_register = {
        row["slot_id"]: row
        for row in public_benchmark["summary"]["operator_evidence_gap_register"]
    }
    assert gap_register["pose_coordinate_intake"]["blocked_tier_beta_criteria"] == [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
    ]
    assert gap_register["casf_pdbbind_subset_intake"]["first_next_action"] == (
        "attach at least 12 local CASF/PDBBind case descriptors"
    )
    assert public_benchmark["summary"]["symmetry_rmsd_scorecard_summary"] == {
        "status": "ready",
        "dry_run_case_count": 1,
        "real_benchmark_case_count": 0,
        "dry_run_pose_success": True,
    }
    assert (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_operator_intake_packet.json"
        in public_benchmark["evidence_artifacts"]
    )
    assert "attach_dud_e_lit_pcba_enrichment_intake" in public_benchmark["next_actions"]
    assert "attach_vina_gnina_comparison_intake" in public_benchmark["next_actions"]
    assert "fill_public_benchmark_operator_intake_packet" in public_benchmark["next_actions"]

    h_bond = rows["h_bond_backmap_evidence"]
    assert h_bond["state"] == "blocked"
    assert h_bond["summary"]["operator_intake_packet_status"] == (
        "ready_for_operator_input"
    )
    assert h_bond["summary"]["operator_intake_required_slot_count"] == 3
    assert h_bond["summary"]["claim_locked"] is True
    assert h_bond["summary"]["first_blocked_target"] == (
        "operator_attached_h_bond_backmap_cases"
    )
    assert h_bond["summary"]["root_cause_tags"] == [
        "operator_receipts_required",
        "operator_handoff_required",
    ]
    assert (
        "implementation/phase1/release_evidence/productization/"
        "h_bond_backmap_operator_intake_packet.json"
        in h_bond["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "h_bond_backmap_operator_intake_packet.md"
        in h_bond["evidence_artifacts"]
    )
    assert "fill_h_bond_backmap_operator_intake_packet" in h_bond["next_actions"]
    assert "attach_h_bond_backmap_operator_receipts" in h_bond["next_actions"]

    pocketmd = rows["pocketmd_lite_top_k_refinement"]
    assert pocketmd["state"] == "blocked"
    assert pocketmd["summary"]["product_surface_ready"] is False
    assert pocketmd["summary"]["operator_intake_packet_status"] == (
        "ready_for_operator_input"
    )
    assert pocketmd["summary"]["operator_intake_route"] == (
        "/product/pocketmd-lite/operator-intake"
    )
    assert pocketmd["summary"]["operator_intake_required_slot_count"] == 1
    assert pocketmd["summary"]["gate_unblock_plan_count"] == 1
    assert pocketmd["summary"]["minimum_refinement_case_count"] == 1
    assert pocketmd["summary"]["minimum_top_k_candidate_count"] == 1
    assert pocketmd["summary"]["phase4_exit_gate_status"] == "blocked"
    assert pocketmd["summary"]["phase4_failed_criterion_count"] == 7
    assert pocketmd["summary"]["phase4_failed_criteria"] == [
        "top_k_refinement_rows_present",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert [
        row["criterion_id"] for row in pocketmd["summary"]["phase4_exit_gate_criteria"]
    ] == [
        "top_k_refinement_rows_present",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
        "broad_all_atom_fep_claims_locked",
    ]
    assert {
        row["slot_id"]: row["status"]
        for row in pocketmd["summary"]["operator_intake_slots"]
    } == {"top_k_refinement_rows": "operator_input_required"}
    gate_plan = pocketmd["summary"]["gate_unblock_plan"][0]
    assert gate_plan["slot_id"] == "top_k_refinement_rows"
    assert gate_plan["unblocks_phase4_criteria"] == [
        "top_k_refinement_rows_present",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert gate_plan["preserves_phase4_criteria"] == [
        "broad_all_atom_fep_claims_locked"
    ]
    assert gate_plan["minimum_evidence"]["candidate_scope"] == (
        "upstream_ranked_top_k_candidates_only"
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_readonly_api.json"
        in pocketmd["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_delivery_handoff.json"
        in pocketmd["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_operator_intake_packet.json"
        in pocketmd["evidence_artifacts"]
    )
    assert pocketmd["summary"]["readonly_api_status"] == "ready_for_seed_artifacts"
    assert pocketmd["summary"]["readonly_api_route"] == "/product/pocketmd-lite"
    assert pocketmd["summary"]["readonly_api_endpoint_count"] == 6
    assert pocketmd["summary"]["handoff_status"] == (
        "handoff_ready_operator_evidence_required"
    )
    assert pocketmd["summary"]["handoff_route"] == "/product/pocketmd-lite/handoff"
    assert pocketmd["summary"]["handoff_acceptance_criteria_count"] == 6
    assert pocketmd["summary"]["handoff_phase4_exit_gate_required_status"] == "ready"
    assert "fill_pocketmd_lite_operator_intake_packet" in pocketmd["next_actions"]
    assert "run_pocketmd_lite_topk_survival_materializer" in pocketmd["next_actions"]

    gpcr = rows["gpcr_hard_decoy_evidence"]
    assert gpcr["state"] == "blocked"
    assert gpcr["summary"]["product_report_route"] == "/product/gpcr-hard-decoy-suite-report"
    assert gpcr["summary"]["broad_gpcr_family_claim_safe"] is False
    assert gpcr["summary"]["operator_intake_route"] == (
        "/product/gpcr-hard-decoy-suite-report/operator-intake"
    )
    assert gpcr["summary"]["operator_intake_packet_status"] == "ready_for_operator_input"
    assert gpcr["summary"]["operator_intake_required_slot_count"] == 3
    assert gpcr["summary"]["gate_unblock_plan_count"] == 3
    assert gpcr["summary"]["minimum_target_count"] == 3
    assert gpcr["summary"]["minimum_metric_field_count_per_target"] == 4
    assert gpcr["summary"]["phase3_exit_gate_status"] == "blocked"
    assert gpcr["summary"]["phase3_failed_criterion_count"] == 4
    assert gpcr["summary"]["phase3_failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert [
        row["criterion_id"] for row in gpcr["summary"]["phase3_exit_gate_criteria"]
    ] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert gpcr["summary"]["phase3_exit_gate_criteria"][0][
        "current_by_target"
    ] == {"DRD2": None, "HTR2A": None, "OPRM1": None}
    assert {
        row["target_id"]: row["status"]
        for row in gpcr["summary"]["operator_target_slots"]
    } == {
        "DRD2": "operator_input_required",
        "HTR2A": "operator_input_required",
        "OPRM1": "operator_input_required",
    }
    gate_plan = {row["target_id"]: row for row in gpcr["summary"]["gate_unblock_plan"]}
    assert gate_plan["DRD2"]["slot_id"] == "drd2_hard_decoy_metrics"
    assert gate_plan["DRD2"]["unblocks_phase3_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert gate_plan["DRD2"]["minimum_evidence"]["thresholds"][
        "top20_hit_rate"
    ] == ">=0.2"
    assert gate_plan["DRD2"]["materialization_steps"] == [
        "materialize_gpcr_hard_decoy_suite_report",
        "refresh_gpcr_hard_decoy_product_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert (
        "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json"
        in gpcr["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json"
        in gpcr["evidence_artifacts"]
    )
    assert "fill_gpcr_hard_decoy_operator_intake_packet" in gpcr["next_actions"]


def test_product_capabilities_surface_cli_writes_pm_visible_ready_surface(
    tmp_path: Path,
) -> None:
    out = tmp_path / "surface" / "product_capabilities_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["input_checksums"][
        "scripts/build_product_capabilities_surface.py"
    ].startswith("sha256:")
    assert payload["surface_id"] == "product_capabilities_surface"

    rows = pm_report._evidence_surface_rows(out.parent)
    assert rows == [
        {
            "surface_id": "product_capabilities_surface",
            "path": str(out),
            "present": True,
            "contract_pass": True,
            "status": "ready",
            "reason_code": "PASS",
            "blocker_count": 0,
            "locked": False,
            "missing": False,
            "summary_line": payload["summary_line"],
            "first_blocked_target": "",
            "root_cause_tags": [],
        }
    ]
