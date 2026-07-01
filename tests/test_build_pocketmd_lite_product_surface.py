from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_pocketmd_lite_product_surface.py"
PM_REPORT_PATH = REPO_ROOT / "scripts" / "report_pm_release_gate.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_pocketmd_lite_product_surface", SCRIPT_PATH)
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


def test_pocketmd_lite_contract_keeps_broad_md_and_fep_locked() -> None:
    artifacts = module.build_pocketmd_lite_artifacts(repo_root=REPO_ROOT)
    contract = artifacts["contract"]
    survival = artifacts["topk_survival_report"]
    api = artifacts["readonly_api"]
    handoff = artifacts["delivery_handoff"]
    operator_template = artifacts["operator_template"]
    operator = artifacts["operator_intake_packet"]
    surface = artifacts["surface"]

    assert contract["schema_version"] == "pocketmd-lite-contract.v1"
    assert contract["contract_pass"] is True
    assert contract["product_surface_ready"] is False
    assert contract["scope"] == "top_k_lite_refinement_only"
    assert contract["top_k_policy"]["requires_upstream_ranked_candidates"] is True
    assert {
        "local_min_survival_rate",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_relief_rate",
        "uncertainty_width_median",
    } == {row["metric_id"] for row in contract["reported_metrics"]}
    assert "free_energy_perturbation_claim" in contract["blocked_claims"]
    assert "broad_all_atom_md_claim" in contract["blocked_claims"]
    assert contract["operator_intake_schema"]["source_checksum_policy"] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert contract["materializer"] == {
        "schema_version": "pocketmd-lite-topk-survival-materialization.v1",
        "script": "scripts/materialize_pocketmd_lite_topk_survival_report.py",
        "status": "ready_for_operator_intake",
        "input_contract": (
            "implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json"
        ),
        "required_intake_key": "cases",
        "outputs": {
            "topk_survival_report": (
                "implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_topk_survival_report.json"
            ),
            "science_product_surface": (
                "implementation/phase1/release_evidence/surface/"
                "pocketmd_lite_science_product_surface.json"
            ),
        },
        "operator_template": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_template.json"
        ),
        "raw_row_importer": {
            "script": "scripts/materialize_pocketmd_lite_operator_intake_from_rows.py",
            "status": "ready_for_raw_operator_rows",
            "supported_source_formats": ["csv", "tsv", "json", "jsonl", "ndjson"],
            "default_row_path_candidates": [
                "implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json",
                "implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.jsonl",
                "implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.ndjson",
                "implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.csv",
                "implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.tsv",
            ],
            "auto_detecting_actual_closure_command": (
                "python3 scripts/materialize_science_actual_closure_from_rows.py "
                "--fail-blocked"
            ),
            "required_output_key": "cases",
            "output_intake": "<operator-pocketmd-lite-intake.json>",
            "emits_operator_input_source_receipt": True,
            "top_k_row_quality_minimums": {
                "min_candidate_count_per_case": 2,
                "min_real_refinement_case_count": 3,
                "min_top_k_rank_coverage_per_case": 2,
                "min_total_top_k_candidate_count": 6,
            },
            "operator_input_source_receipt_policy": {
                "required_mode": "raw_top_k_refinement_rows",
                "source_artifact_sha256_policy": (
                    "sha256:<64 lowercase or uppercase hex characters>"
                ),
                "required_operator_input_source_fields": [
                    "mode",
                    "source_artifact",
                    "source_artifact_sha256",
                    "source_id",
                    "source_url",
                    "source_license",
                ],
            },
            "command": (
                "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
                "--rows <operator-pocketmd-lite-refinement-rows.csv|tsv|json|jsonl|ndjson> "
                "--out <operator-pocketmd-lite-intake.json> "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
        },
        "command": (
            "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
            "--intake <operator-pocketmd-lite-intake.json> "
            "--contract implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_contract.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_survival_report.json "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json "
            "--fail-blocked"
        ),
    }

    assert survival["schema_version"] == "pocketmd-lite-topk-survival-report.v1"
    assert survival["contract_pass"] is False
    assert survival["summary_line"] == (
        "PocketMD Lite top-k survival report: LOCKED | "
        "first_blocked_target=top_k_refinement_operator_intake | blockers=6"
    )
    assert survival["first_blocker"] == "pocketmd_lite_topk_candidate_rows_missing"
    assert survival["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert survival["root_cause_tags"] == ["operator_refinement_rows_required"]
    assert survival["real_refinement_case_count"] == 0
    assert survival["summary"]["local_min_survival_rate"] is None
    assert survival["blockers"] == [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
        "pocketmd_lite_contact_persistence_rows_missing",
        "pocketmd_lite_h_bond_persistence_rows_missing",
        "pocketmd_lite_clash_relief_rows_missing",
        "pocketmd_lite_uncertainty_rows_missing",
    ]
    assert "uncertainty_width_median" in survival["required_metrics"]
    assert "source_checksum" in survival["required_case_fields"]
    assert survival["materializer"]["status"] == "ready_for_operator_intake"
    assert survival["phase4_exit_gate"]["status"] == "blocked"
    assert survival["phase4_exit_gate"]["failed_criterion_count"] == 8
    assert survival["phase4_exit_gate"]["failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert survival["operator_input_source_receipt"]["status"] == "blocked"
    assert survival["operator_input_source_receipt"]["contract_pass"] is False
    assert survival["operator_input_source_receipt"]["blockers"] == [
        "operator_input_source_receipt_required"
    ]
    assert "operator_input_source_receipt_required" not in survival["blockers"]
    assert survival["operator_intake_route"] == "/product/pocketmd-lite/operator-intake"
    assert survival["operator_intake_packet"] == {
        "route": "/product/pocketmd-lite/operator-intake",
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_intake_packet.json"
        ),
        "markdown_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_intake_packet.md"
        ),
        "template_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_template.json"
        ),
        "status": "ready_for_operator_input",
        "required_slot_count": 1,
        "gate_unblock_plan_count": 1,
        "minimum_refinement_case_count": 3,
        "minimum_top_k_candidate_count": 6,
        "minimum_candidate_count_per_case": 2,
        "minimum_top_k_rank_coverage_per_case": 2,
        "top_k_row_quality_minimums": {
            "min_candidate_count_per_case": 2,
            "min_real_refinement_case_count": 3,
            "min_top_k_rank_coverage_per_case": 2,
            "min_total_top_k_candidate_count": 6,
        },
        "first_blocker": "pocketmd_lite_topk_candidate_rows_missing",
        "first_blocked_target": "top_k_refinement_operator_intake",
        "root_cause_tags": ["operator_refinement_rows_required"],
        "first_operator_evidence_gap": survival["first_operator_evidence_gap"],
    }
    assert survival["operator_gate_unblock_plan"][0]["slot_id"] == (
        "top_k_refinement_rows"
    )
    assert survival["operator_gate_unblock_plan"][0]["minimum_evidence"][
        "required_case_fields"
    ] == survival["required_case_fields"]
    assert survival["operator_handoff_summary"]["first_blocker"] == (
        "pocketmd_lite_topk_candidate_rows_missing"
    )
    assert survival["operator_handoff_summary"]["materialization_command"] == survival[
        "materializer"
    ]["command"]
    assert survival["next_actions"][:2] == [
        "materialize_pocketmd_lite_operator_intake_from_rows",
        "fill_pocketmd_lite_operator_intake_packet",
    ]

    assert api["schema_version"] == "pocketmd-lite-readonly-api.v1"
    assert api["contract_pass"] is True
    assert api["read_model_ready"] is True
    assert api["route"] == "/product/pocketmd-lite"
    assert api["read_model"] == {
        "route": "/product/pocketmd-lite",
        "alternate_routes": [
            "/product/pocketmd-lite/operator-intake",
            "/product/pocketmd-lite/handoff",
            "/product/capabilities",
        ],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_readonly_api.json"
        ),
        "mutation_allowed": False,
    }
    assert api["mutation_allowed"] is False
    assert {row["method"] for row in api["endpoints"]} == {"GET"}
    assert "get_pocketmd_lite_delivery_handoff" in {
        row["endpoint_id"] for row in api["endpoints"]
    }
    assert "write_operator_evidence" in api["forbidden_operations"]
    assert "get_pocketmd_lite_operator_template" in {
        row["endpoint_id"] for row in api["endpoints"]
    }

    assert handoff["schema_version"] == "pocketmd-lite-delivery-handoff.v1"
    assert handoff["contract_pass"] is True
    assert handoff["read_model_ready"] is True
    assert handoff["route"] == "/product/pocketmd-lite/handoff"
    assert handoff["read_model"] == {
        "route": "/product/pocketmd-lite/handoff",
        "alternate_routes": [
            "/product/pocketmd-lite",
            "/product/pocketmd-lite/operator-intake",
            "/product/capabilities",
        ],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_delivery_handoff.json"
        ),
        "mutation_allowed": False,
    }
    assert handoff["evidence_artifacts"]["operator_intake_packet"].endswith(
        "pocketmd_lite_operator_intake_packet.json"
    )
    assert handoff["phase4_exit_gate_reference"] == {
        "source_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_survival_report.json"
        ),
        "json_pointer": "/phase4_exit_gate",
        "required_status": "ready",
        "required_criteria": [
            "top_k_refinement_rows_present",
            "top_k_refinement_case_coverage",
            "local_min_survival_materialized",
            "contact_persistence_materialized",
            "h_bond_persistence_materialized",
            "clash_relief_materialized",
            "uncertainty_summary_materialized",
            "report_blockers_resolved",
            "broad_all_atom_fep_claims_locked",
        ],
    }
    assert handoff["operator_intake_reference"]["required_slot_id"] == (
        "top_k_refinement_rows"
    )
    assert handoff["operator_intake_reference"]["route"] == (
        "/product/pocketmd-lite/operator-intake"
    )
    assert handoff["operator_intake_reference"]["template_artifact"].endswith(
        "pocketmd_lite_operator_template.json"
    )
    assert "topk_survival_report.real_refinement_case_count >= 3" in handoff[
        "acceptance_criteria"
    ]
    assert "topk_survival_report.top_k_candidate_count >= 6" in handoff[
        "acceptance_criteria"
    ]
    assert "topk_survival_report.top_k_row_quality.contract_pass == true" in handoff[
        "acceptance_criteria"
    ]
    assert "topk_survival_report.phase4_exit_gate.status == ready" in handoff[
        "acceptance_criteria"
    ]

    assert operator["schema_version"] == "pocketmd-lite-operator-intake-packet.v1"
    assert operator["status"] == "ready_for_operator_input"
    assert operator["contract_pass"] is True
    assert operator["read_model_ready"] is True
    assert operator["route"] == "/product/pocketmd-lite/operator-intake"
    assert operator["read_model"] == {
        "route": "/product/pocketmd-lite/operator-intake",
        "alternate_routes": [
            "/product/pocketmd-lite",
            "/product/pocketmd-lite/handoff",
            "/product/capabilities",
        ],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_intake_packet.json"
        ),
        "mutation_allowed": False,
    }
    assert operator["mutation_allowed"] is False
    assert operator["owner_input_required"] is True
    assert operator["product_surface_ready"] is False
    assert operator["broad_all_atom_md_claim_safe"] is False
    assert operator["broad_fep_claim_safe"] is False
    assert operator["required_slot_count"] == 1
    assert operator["input_slots"][0]["slot_id"] == "top_k_refinement_rows"
    assert operator["input_slots"][0]["template_artifact"].endswith(
        "pocketmd_lite_operator_template.json"
    )
    assert operator["gate_unblock_plan_count"] == 1
    assert operator["minimum_refinement_case_count"] == 3
    assert operator["minimum_top_k_candidate_count"] == 6
    assert operator["minimum_candidate_count_per_case"] == 2
    assert operator["minimum_top_k_rank_coverage_per_case"] == 2
    assert operator["top_k_row_quality_minimums"] == {
        "min_candidate_count_per_case": 2,
        "min_real_refinement_case_count": 3,
        "min_top_k_rank_coverage_per_case": 2,
        "min_total_top_k_candidate_count": 6,
    }
    gate_plan = operator["gate_unblock_plan"][0]
    assert gate_plan["slot_id"] == "top_k_refinement_rows"
    assert gate_plan["unblocks_phase4_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
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
    assert gate_plan["minimum_evidence"]["real_refinement_case_count"] == 3
    assert gate_plan["minimum_evidence"]["top_k_candidate_count"] == 6
    assert gate_plan["minimum_evidence"]["candidate_count_per_case"] == 2
    assert gate_plan["minimum_evidence"]["top_k_rank_coverage_per_case"] == 2
    assert gate_plan["minimum_evidence"]["required_rank_span_per_case"] == [1, 2]
    assert gate_plan["minimum_evidence"]["top_k_row_quality_minimums"] == {
        "min_candidate_count_per_case": 2,
        "min_real_refinement_case_count": 3,
        "min_top_k_rank_coverage_per_case": 2,
        "min_total_top_k_candidate_count": 6,
    }
    assert gate_plan["minimum_evidence"]["source_checksum_policy"] == {
        "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
        "required_receipt_field": "source_checksum",
    }
    assert gate_plan["materialization_steps"] == [
        "materialize_pocketmd_lite_operator_intake_from_rows",
        "materialize_pocketmd_lite_topk_survival_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert operator["current_surface_status"]["first_blocked_target"] == (
        "top_k_refinement_operator_intake"
    )
    assert operator["materialization_sequence"][0]["step_id"] == (
        "materialize_pocketmd_lite_operator_intake_from_rows"
    )
    assert operator["materialization_sequence"][1]["step_id"] == (
        "fill_pocketmd_lite_operator_intake_packet"
    )
    assert operator["next_actions"][:2] == [
        "materialize_pocketmd_lite_operator_intake_from_rows",
        "fill_pocketmd_lite_operator_intake_packet",
    ]
    assert operator["acceptance_criteria"][-1].startswith("broad_all_atom_md_claim")
    assert operator_template["schema_version"] == "pocketmd-lite-operator-template.v1"
    assert operator_template["status"] == "operator_template_seed"
    assert operator_template["operator_values_filled"] is False
    assert operator_template["template"]["cases"][0]["case_id"] == (
        "pocketmd_lite_case_001"
    )

    assert surface["schema_version"] == "pocketmd-lite-science-product-surface.v1"
    assert surface["surface_id"] == "pocketmd_lite_science_product_surface"
    assert surface["surface_kind"] == "science_product_surface"
    assert surface["science_surface_family"] == "pocketmd_lite"
    assert surface["contract_pass"] is False
    assert surface["locked"] is True
    assert surface["claim_locked"] is True
    assert surface["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert surface["first_blocker"] == "pocketmd_lite_topk_candidate_rows_missing"
    assert surface["root_cause_tags"] == ["operator_refinement_rows_required"]
    assert surface["blockers"] == [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
        "pocketmd_lite_contact_persistence_rows_missing",
        "pocketmd_lite_h_bond_persistence_rows_missing",
        "pocketmd_lite_clash_relief_rows_missing",
        "pocketmd_lite_uncertainty_rows_missing",
        "pocketmd_lite_broad_all_atom_fep_claim_locked",
    ]
    assert surface["operator_intake_route"] == "/product/pocketmd-lite/operator-intake"
    assert surface["operator_intake_required_slot_count"] == 1
    assert surface["operator_evidence_gap_count"] == 1
    assert surface["first_operator_evidence_gap"]["slot_id"] == (
        "top_k_refinement_rows"
    )
    assert surface["first_operator_evidence_gap"]["blocked_phase4_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert surface["first_operator_evidence_gap"]["preserves_phase4_criteria"] == [
        "broad_all_atom_fep_claims_locked"
    ]
    assert surface["operator_handoff_summary"] == {
        "route": "/product/pocketmd-lite/operator-intake",
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_intake_packet.json"
        ),
        "template_artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_operator_template.json"
        ),
        "first_blocker": "pocketmd_lite_topk_candidate_rows_missing",
        "first_blocked_target": "top_k_refinement_operator_intake",
        "first_next_action": "attach top-k candidate refinement rows",
        "required_slot_count": 1,
        "blocked_operator_slot_count": 1,
        "minimum_evidence": {
            "real_refinement_case_count": 3,
            "top_k_candidate_count": 6,
            "candidate_count_per_case": 2,
            "top_k_rank_coverage_per_case": 2,
            "required_rank_span_per_case": [1, 2],
            "top_k_row_quality_minimums": {
                "min_candidate_count_per_case": 2,
                "min_real_refinement_case_count": 3,
                "min_top_k_rank_coverage_per_case": 2,
                "min_total_top_k_candidate_count": 6,
            },
            "candidate_scope": "upstream_ranked_top_k_candidates_only",
            "required_case_fields": [
                "case_id",
                "source_family",
                "top_k_rank",
                "candidate_id",
                "pre_refinement_energy_proxy",
                "post_refinement_energy_proxy",
                "local_min_survived",
                "contact_persistence_rate",
                "h_bond_persistence_rate",
                "clash_count_before",
                "clash_count_after",
                "uncertainty_interval",
                "provenance_ref",
                "source_checksum",
            ],
            "receipt_fields": [
                "provenance_ref",
                "source_checksum",
                "operator_input_source.source_artifact",
                "operator_input_source.source_artifact_sha256",
                "operator_input_source.source_id",
                "operator_input_source.source_url",
                "operator_input_source.source_license",
            ],
            "source_checksum_policy": {
                "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
                "required_receipt_field": "source_checksum",
            },
            "operator_input_source_receipt_policy": {
                "required_mode": "raw_top_k_refinement_rows",
                "source_artifact_sha256_policy": (
                    "sha256:<64 lowercase or uppercase hex characters>"
                ),
                "required_operator_input_source_fields": [
                    "mode",
                    "source_artifact",
                    "source_artifact_sha256",
                    "source_id",
                    "source_url",
                    "source_license",
                ],
            },
            "raw_row_supported_formats": ["csv", "tsv", "json", "jsonl", "ndjson"],
        },
        "materialization_steps": [
            "materialize_pocketmd_lite_operator_intake_from_rows",
            "materialize_pocketmd_lite_topk_survival_report",
            "refresh_product_capabilities_surface",
            "refresh_goal_bottleneck_roadmap_surface",
        ],
        "raw_row_import_command": (
            "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
            "--rows <operator-pocketmd-lite-refinement-rows.csv|tsv|json|jsonl|ndjson> "
            "--out <operator-pocketmd-lite-intake.json> "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license>"
        ),
        "materialization_command": (
            "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
            "--intake <operator-pocketmd-lite-intake.json> "
            "--contract implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_contract.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_survival_report.json "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json "
            "--fail-blocked"
        ),
        "validation_command": (
            "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
            "--intake <operator-pocketmd-lite-intake.json> "
            "--contract implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_contract.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_topk_survival_report.json "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json "
            "--fail-blocked"
        ),
    }
    assert surface["phase4_exit_gate"]["status"] == "blocked"
    assert surface["phase4_exit_gate"]["failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    assert surface["operator_input_source_receipt"] == survival[
        "operator_input_source_receipt"
    ]
    assert surface["readiness_summary"]["phase4_exit_gate_status"] == "blocked"
    assert surface["readiness_summary"]["phase4_failed_criterion_count"] == 8
    assert surface["readiness_summary"]["operator_input_source_receipt_status"] == (
        "blocked"
    )
    assert (
        surface["readiness_summary"]["operator_input_source_receipt_contract_pass"]
        is False
    )
    assert surface["goal_roadmap_linkage"] == {
        "phase": "Phase 4",
        "roadmap_item": "PocketMD Lite science product surface",
        "bottleneck": "pocketmd_lite_science_product_surface_locked",
        "next_goal_actions": [
            "materialize_pocketmd_lite_operator_intake_from_rows",
            "fill_pocketmd_lite_operator_intake_packet",
            "run_pocketmd_lite_topk_survival_materializer",
            "publish_pocketmd_lite_readonly_api",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_action_board",
        ],
    }
    assert "Broad all-atom MD, FEP" in surface["claim_boundary"]


def test_pocketmd_lite_cli_writes_pm_visible_surface(tmp_path: Path) -> None:
    contract_out = tmp_path / "pocketmd_lite_contract.json"
    survival_out = tmp_path / "pocketmd_lite_topk_survival_report.json"
    api_out = tmp_path / "pocketmd_lite_readonly_api.json"
    handoff_out = tmp_path / "pocketmd_lite_delivery_handoff.json"
    operator_out = tmp_path / "pocketmd_lite_operator_intake_packet.json"
    operator_md_out = tmp_path / "pocketmd_lite_operator_intake_packet.md"
    operator_template_out = tmp_path / "pocketmd_lite_operator_template.json"
    surface_out = tmp_path / "surface" / "pocketmd_lite_science_product_surface.json"

    assert (
        module.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--contract-out",
                str(contract_out),
                "--survival-report-out",
                str(survival_out),
                "--readonly-api-out",
                str(api_out),
                "--handoff-out",
                str(handoff_out),
                "--operator-intake-out",
                str(operator_out),
                "--operator-intake-md-out",
                str(operator_md_out),
                "--operator-template-out",
                str(operator_template_out),
                "--surface-out",
                str(surface_out),
            ]
        )
        == 0
    )

    for path in (
        contract_out,
        survival_out,
        api_out,
        handoff_out,
        operator_out,
        operator_template_out,
        surface_out,
    ):
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["source_commit_sha"]
        assert payload["input_checksums"][
            "scripts/build_pocketmd_lite_product_surface.py"
        ].startswith("sha256:")
        assert payload["input_checksums"][
            "scripts/materialize_pocketmd_lite_topk_survival_report.py"
        ].startswith("sha256:")
        assert payload["input_checksums"][
            "scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"
        ].startswith("sha256:")
    assert "# PocketMD Lite Operator Intake Packet" in operator_md_out.read_text(
        encoding="utf-8"
    )
    survival_payload = json.loads(survival_out.read_text(encoding="utf-8"))
    surface_payload = json.loads(surface_out.read_text(encoding="utf-8"))
    assert survival_payload["operator_input_source_receipt"]["blockers"] == [
        "operator_input_source_receipt_required"
    ]
    assert surface_payload["operator_input_source_receipt"] == survival_payload[
        "operator_input_source_receipt"
    ]

    rows = pm_report._evidence_surface_rows(surface_out.parent)
    assert rows == [
        {
            "surface_id": "pocketmd_lite_science_product_surface",
            "path": str(surface_out),
            "present": True,
            "contract_pass": False,
            "status": "locked",
            "reason_code": "ERR_POCKETMD_LITE_PRODUCT_SURFACE_LOCKED",
            "blocker_count": 7,
            "locked": True,
            "missing": True,
            "summary_line": (
                "PocketMD Lite science product surface: LOCKED | "
                "top-k refinement operator rows required"
            ),
            "first_blocked_target": "top_k_refinement_operator_intake",
            "root_cause_tags": ["operator_refinement_rows_required"],
            "blocked_criteria": [
                "top_k_refinement_rows_present",
                "top_k_refinement_case_coverage",
                "local_min_survival_materialized",
                "contact_persistence_materialized",
                "h_bond_persistence_materialized",
                "clash_relief_materialized",
                "uncertainty_summary_materialized",
                "report_blockers_resolved",
            ],
        }
    ]
