from __future__ import annotations

import importlib.util
import csv
import hashlib
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_pocketmd_lite_source_acquisition_plan.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_pocketmd_lite_source_acquisition_plan",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_valid_rows(path: Path) -> None:
    fieldnames = [
        "case_id",
        "source_family",
        "top_k_rank",
        "candidate_id",
        "upstream_top_k_provenance_ref",
        "upstream_top_k_source_checksum",
        "pre_refinement_energy_proxy",
        "post_refinement_energy_proxy",
        "local_min_survived",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_count_before",
        "clash_count_after",
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
        "provenance_ref",
        "source_checksum",
    ]
    rows = []
    for case_index in range(1, 4):
        case_id = f"pocketmd_lite_case_{case_index:03d}"
        for rank in (1, 2):
            candidate_id = f"{case_id}_candidate_{rank:02d}"
            rows.append(
                {
                    "case_id": case_id,
                    "source_family": "upstream_ranked_top_k_candidate_set",
                    "top_k_rank": rank,
                    "candidate_id": candidate_id,
                    "upstream_top_k_provenance_ref": (
                        f"https://pocketmd-data.org/topk/{case_id}/{candidate_id}.json#row"
                    ),
                    "upstream_top_k_source_checksum": _checksum(
                        f"upstream:{case_id}:{candidate_id}"
                    ),
                    "pre_refinement_energy_proxy": -8.0 + rank,
                    "post_refinement_energy_proxy": -8.4 + rank,
                    "local_min_survived": "true",
                    "contact_persistence_rate": 0.8,
                    "h_bond_persistence_rate": 0.7,
                    "clash_count_before": 3,
                    "clash_count_after": 1,
                    "uncertainty_low": 0.1,
                    "uncertainty_high": 0.3,
                    "uncertainty_unit": "energy_proxy_delta",
                    "provenance_ref": (
                        f"https://pocketmd-data.org/refinement/{case_id}/{candidate_id}.json#row"
                    ),
                    "source_checksum": _checksum(f"refinement:{case_id}:{candidate_id}"),
                }
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_pocketmd_lite_source_acquisition_plan_exposes_topk_row_contract() -> None:
    payload = module.build_pocketmd_lite_source_acquisition_plan(
        repo_root=REPO_ROOT,
    )
    receipt_plan = payload["phase4_refinement_receipt_plan"]
    execution_plan = payload["refinement_execution_plan"]
    receipt_roles = {
        row["receipt_role_id"]: row for row in receipt_plan["receipt_roles"]
    }

    assert payload["schema_version"] == "pocketmd-lite-source-acquisition-plan.v1"
    assert payload["status"] == "operator_acquisition_required"
    assert payload["contract_pass"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["source_scope"] == "bounded_top_k_lite_refinement_rows"
    assert payload["supported_source_formats"] == ["csv", "tsv", "json", "jsonl", "ndjson"]
    assert payload["top_k_row_quality_minimums"] == {
        "min_candidate_count_per_case": 2,
        "min_real_refinement_case_count": 3,
        "min_top_k_rank_coverage_per_case": 2,
        "min_total_top_k_candidate_count": 6,
    }
    assert payload["phase4_refinement_receipt_promotion_policy"] == {
        "broad_all_atom_or_fep_claims_unlocked": False,
        "lite_refinement_metric_receipts_required": True,
        "operator_attached_rows_required": True,
        "operator_input_source_receipt_required": True,
        "per_row_sha256_receipt_required": True,
        "summary_only_metrics_promote_to_phase4": False,
        "synthetic_fixture_rows_promote_to_phase4": False,
        "upstream_top_k_scope_receipts_required": True,
    }
    assert receipt_plan["plan_id"] == "pocketmd_lite_phase4_refinement_receipt_plan"
    assert receipt_plan["status"] == "operator_receipts_required"
    assert receipt_plan["receipt_role_count"] == 4
    assert receipt_plan["covered_phase4_criterion_count"] == 8
    assert receipt_plan["preserved_phase4_criteria"] == [
        "broad_all_atom_fep_claims_locked"
    ]
    assert set(receipt_roles) == {
        "upstream_top_k_candidate_scope_receipt",
        "lite_refinement_run_receipt",
        "interaction_persistence_receipt",
        "uncertainty_interval_receipt",
    }
    assert receipt_roles["upstream_top_k_candidate_scope_receipt"][
        "closes_phase4_criteria"
    ] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
    ]
    assert "upstream_top_k_source_checksum" in receipt_roles[
        "upstream_top_k_candidate_scope_receipt"
    ]["required_fields"]
    assert receipt_roles["lite_refinement_run_receipt"][
        "closes_phase4_criteria"
    ] == ["local_min_survival_materialized", "report_blockers_resolved"]
    assert "contact_persistence_materialized" in receipt_roles[
        "interaction_persistence_receipt"
    ]["closes_phase4_criteria"]
    assert receipt_roles["uncertainty_interval_receipt"][
        "required_quality_gates"
    ] == [
        "uncertainty_interval_has_finite_low_and_high",
        "uncertainty_high_is_not_below_low",
        "uncertainty_unit_is_nonblank",
        "uncertainty_rows_share_the_bounded_top_k_candidate_scope",
    ]
    assert execution_plan == {
        "actual_closure_ready": False,
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_refinement_execution_plan.json"
        ),
        "claim_boundary": (
            "The execution plan enumerates the bounded top-k case/rank slots "
            "operator rows must fill. It does not synthesize rows or promote "
            "PocketMD Lite closure without the survival materializer."
        ),
        "command": (
            "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py "
            "--out implementation/phase1/release_evidence/productization/"
            "pocketmd_lite_refinement_execution_plan.json"
        ),
        "execution_plan_ready": True,
        "operator_rows_ready": False,
        "required_candidate_slot_count": 6,
        "required_case_count": 3,
        "schema_version": "pocketmd-lite-refinement-execution-plan.v1",
        "status": "operator_refinement_rows_required",
        "survival_report_ready": False,
    }
    assert payload["operator_next_actions"] == payload[
        "operator_acquisition_checklist"
    ]
    assert payload["operator_next_actions"][:3] == [
        "review_phase4_refinement_receipt_plan",
        "build_pocketmd_lite_refinement_execution_plan",
        "build_pocketmd_lite_topk_rows_template_preflight",
    ]
    assert payload["operator_next_actions"][-2:] == [
        "run_pocketmd_lite_raw_row_importer_and_survival_materializer",
        "refresh_science_actual_closure_from_rows",
    ]
    assert payload["minimum_rows_by_case"] == [
        {
            "case_id": "pocketmd_lite_case_001",
            "minimum_candidate_rows": 2,
            "required_top_k_rank_prefix": [1, 2],
            "candidate_scope": "upstream_ranked_top_k_candidates_only",
        },
        {
            "case_id": "pocketmd_lite_case_002",
            "minimum_candidate_rows": 2,
            "required_top_k_rank_prefix": [1, 2],
            "candidate_scope": "upstream_ranked_top_k_candidates_only",
        },
        {
            "case_id": "pocketmd_lite_case_003",
            "minimum_candidate_rows": 2,
            "required_top_k_rank_prefix": [1, 2],
            "candidate_scope": "upstream_ranked_top_k_candidates_only",
        },
    ]

    row_contract = payload["row_artifact_contract"]
    assert row_contract["default_output"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    )
    assert row_contract["template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert row_contract["template_preflight_artifact"].endswith(
        "pocketmd_lite_topk_rows_template_preflight.json"
    )
    assert row_contract["template_preflight_markdown_artifact"].endswith(
        "pocketmd_lite_topk_rows_template_preflight.md"
    )
    assert "build_pocketmd_lite_topk_rows_template_preflight.py" in row_contract[
        "template_preflight_command"
    ]
    assert row_contract["template_usage_policy"] == (
        "The template enumerates required columns and minimum case/rank slots only. "
        "Operators must replace placeholder blanks with real top-k refinement rows "
        "and receipts before writing rows to the default output."
    )
    assert row_contract["operator_intake_output"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_operator_intake.json"
    )
    assert row_contract["required_case_count"] == 3
    assert row_contract["required_total_candidate_rows"] == 6
    assert row_contract["required_candidate_rows_per_case"] == 2
    assert row_contract["required_top_k_rank_coverage_per_case"] == 2
    assert row_contract["required_flat_row_fields"] == [
        "case_id",
        "source_family",
        "top_k_rank",
        "candidate_id",
        "upstream_top_k_provenance_ref",
        "upstream_top_k_source_checksum",
        "pre_refinement_energy_proxy",
        "post_refinement_energy_proxy",
        "local_min_survived",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_count_before",
        "clash_count_after",
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
        "provenance_ref",
        "source_checksum",
    ]
    assert payload["raw_row_candidate_status"]["status"] == "row_artifact_missing"
    assert payload["raw_row_candidate_status"]["detected_row_artifact_count"] == 0
    assert row_contract["raw_row_candidate_status"] == payload[
        "raw_row_candidate_status"
    ]
    assert row_contract["source_receipt_requirements"]["mode"] == (
        "raw_top_k_refinement_rows"
    )
    assert row_contract["row_value_contract"]["top_k_survival_scope_policy"].startswith(
        "PocketMD Lite refinement rows are bounded to upstream top-k candidates only"
    )
    row_action = payload["pocketmd_rows_operator_action"]
    assert row_action["row_input_id"] == "pocketmd_rows"
    assert row_action["status"] == "missing"
    assert row_action["operator_action"] == (
        "attach_pocketmd_rows_at_implementation/phase1/release_evidence/"
        "productization/pocketmd_lite_topk_rows.json"
    )
    assert row_action["default_row_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    )
    assert row_action["template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert row_action["required_case_count"] == 3
    assert row_action["required_candidate_slot_count"] == 6
    assert row_action["required_total_candidate_rows"] == 6
    assert row_action["operator_blockers_if_missing"] == [
        "pocketmd_lite_topk_rows_not_acquired"
    ]
    assert row_action["required_receipt_roles"] == [
        "upstream_top_k_candidate_scope_receipt",
        "lite_refinement_run_receipt",
        "interaction_persistence_receipt",
        "uncertainty_interval_receipt",
    ]
    assert payload["phase4_candidate_slot_matrix_count"] == 6
    assert payload["phase4_missing_candidate_slot_count"] == 6
    slot_matrix = {
        row["slot_id"]: row for row in payload["phase4_candidate_slot_matrix"]
    }
    first_slot = slot_matrix["pocketmd_lite_case_001_rank_1"]
    assert first_slot["status"] == "missing"
    assert first_slot["required_receipt_roles"] == [
        "upstream_top_k_candidate_scope_receipt",
        "lite_refinement_run_receipt",
        "interaction_persistence_receipt",
        "uncertainty_interval_receipt",
    ]
    assert "contact_persistence_rate" in first_slot["required_metric_fields"]
    assert "uncertainty_summary_materialized" in first_slot[
        "closes_phase4_criteria"
    ]
    assert payload["phase4_metric_closure_matrix_count"] == 8
    assert payload["template_preflight_summary"]["status"] == (
        "operator_rows_completion_required"
    )
    assert payload["template_preflight_summary"]["role_receipt_plan_count"] == 24
    assert payload["template_preflight_summary"]["role_receipt_blocked_count"] == 24
    assert payload["template_preflight_summary"][
        "operator_input_source_receipt_requirement_count"
    ] == 5
    assert payload["template_preflight_summary"][
        "operator_input_source_receipt_blocked_count"
    ] == 5
    assert payload["template_preflight_summary"]["first_blocked_role_receipt"][
        "role_id"
    ] == "upstream_top_k_candidate_scope_receipt"
    metric_matrix = {
        row["criterion_id"]: row for row in payload["phase4_metric_closure_matrix"]
    }
    assert metric_matrix["local_min_survival_materialized"]["metric_id"] == (
        "local_min_survival_rate"
    )
    assert metric_matrix["contact_persistence_materialized"][
        "required_row_fields"
    ] == ["contact_persistence_rate"]
    assert metric_matrix["h_bond_persistence_materialized"]["metric_id"] == (
        "h_bond_persistence_rate"
    )
    assert metric_matrix["clash_relief_materialized"]["required_row_fields"] == [
        "clash_count_before",
        "clash_count_after",
    ]
    assert metric_matrix["uncertainty_summary_materialized"][
        "required_row_fields"
    ] == ["uncertainty_low", "uncertainty_high", "uncertainty_unit"]
    preflight_action = row_action["row_preflight_action_packet"]
    assert preflight_action["status"] == "row_artifact_missing"
    assert preflight_action["expected_rows_artifact"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert preflight_action["template_preflight_artifact"].endswith(
        "pocketmd_lite_topk_rows_template_preflight.json"
    )
    assert "build_pocketmd_lite_topk_rows_template_preflight.py" in preflight_action[
        "build_template_preflight_command"
    ]
    assert preflight_action["supported_candidate_paths"] == [
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json",
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.jsonl",
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.ndjson",
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.csv",
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.tsv",
    ]
    assert preflight_action["detected_row_artifact_count"] == 0
    assert preflight_action["validated_row_count"] == 0
    assert preflight_action["covered_required_slot_count"] == 0
    assert preflight_action["required_candidate_slot_count"] == 6
    assert len(preflight_action["missing_required_slots"]) == 6
    assert preflight_action["blocker"] == "pocketmd_lite_topk_rows_not_acquired"
    assert preflight_action["template_preflight_summary"][
        "role_receipt_blocked_count"
    ] == 24
    assert preflight_action["template_preflight_summary"][
        "operator_input_source_receipt_blocked_count"
    ] == 5
    assert preflight_action["template_safety_policy"] == {
        "broad_all_atom_or_fep_claims_remain_locked": True,
        "operator_rows_must_be_real_top_k_refinement_outputs": True,
        "placeholder_or_fixture_rows_do_not_promote": True,
        "preflight_does_not_run_refinement": True,
        "template_is_not_evidence": True,
    }
    top_k_action = row_action["top_k_rows_action_packet"]
    assert top_k_action["status"] == "operator_rows_required"
    assert top_k_action["template_artifact"].endswith(
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert top_k_action["template_preflight_artifact"].endswith(
        "pocketmd_lite_topk_rows_template_preflight.json"
    )
    assert top_k_action["expected_rows_artifact"].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert top_k_action["review_template_command"] == row_action["commands"][
        "review_row_template"
    ]
    assert top_k_action["build_template_preflight_command"] == row_action[
        "commands"
    ]["build_row_template_preflight"]
    assert top_k_action["import_rows_command"] == row_action["commands"][
        "import_rows"
    ]
    assert top_k_action["materialize_survival_command"] == row_action["commands"][
        "materialize_survival"
    ]
    assert top_k_action["verify_science_actual_closure_command"] == row_action[
        "commands"
    ]["science_actual_closure"]
    pocketmd_rows_arg = (
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    )
    assert pocketmd_rows_arg in top_k_action["verify_science_actual_closure_command"]
    assert "--source-id <source-id>" in top_k_action[
        "verify_science_actual_closure_command"
    ]
    assert "operator_input_source.source_artifact_sha256" in top_k_action[
        "operator_must_fill_or_verify"
    ]
    assert "uncertainty_interval_receipt" in top_k_action[
        "required_receipt_roles"
    ]
    assert top_k_action["role_receipt_plan_summary"][
        "role_receipt_blocked_count"
    ] == 24
    assert top_k_action["role_receipt_plan_summary"]["first_blocked_role_receipt"][
        "role_id"
    ] == "upstream_top_k_candidate_scope_receipt"
    assert top_k_action["operator_input_source_receipt_plan_summary"][
        "blocked_count"
    ] == 5
    assert top_k_action["operator_input_source_receipt_plan_summary"][
        "first_blocked_receipt"
    ]["field"] == "source_id"
    assert top_k_action["phase4_metric_receipt_action_count"] == 8
    metric_receipt_actions = {
        row["criterion_id"]: row
        for row in top_k_action["phase4_metric_receipt_actions"]
    }
    assert metric_receipt_actions["local_min_survival_materialized"][
        "receipt_roles"
    ] == ["lite_refinement_run_receipt"]
    assert metric_receipt_actions["contact_persistence_materialized"][
        "receipt_roles"
    ] == ["interaction_persistence_receipt"]
    assert metric_receipt_actions["uncertainty_summary_materialized"][
        "required_row_fields"
    ] == ["uncertainty_low", "uncertainty_high", "uncertainty_unit"]
    assert "lite_refinement_metric_receipts_not_attached" in metric_receipt_actions[
        "report_blockers_resolved"
    ]["blockers"]
    assert top_k_action["template_safety_policy"] == {
        "broad_all_atom_or_fep_claims_remain_locked": True,
        "expected_rows_must_be_operator_reviewed": True,
        "placeholder_or_fixture_rows_do_not_promote": True,
        "summary_only_metrics_do_not_promote": True,
        "template_is_not_evidence": True,
    }
    assert "uncertainty_summary_materialized" in row_action[
        "closes_phase4_criteria"
    ]
    assert payload["missing_row_input_actions"] == [row_action]
    assert payload["missing_row_input_action_count"] == 1

    assert payload["metric_receipt_contract"] == [
        {
            "metric_id": "local_min_survival_rate",
            "required_row_fields": ["local_min_survived"],
            "required_value_policy": "boolean per top-k candidate",
        },
        {
            "metric_id": "contact_persistence_rate",
            "required_row_fields": ["contact_persistence_rate"],
            "required_value_policy": "finite fraction from 0.0 to 1.0",
        },
        {
            "metric_id": "h_bond_persistence_rate",
            "required_row_fields": ["h_bond_persistence_rate"],
            "required_value_policy": "finite fraction from 0.0 to 1.0",
        },
        {
            "metric_id": "clash_relief_rate",
            "required_row_fields": ["clash_count_before", "clash_count_after"],
            "required_value_policy": "non-negative integer clash counts",
        },
        {
            "metric_id": "uncertainty_width_median",
            "required_row_fields": [
                "uncertainty_low",
                "uncertainty_high",
                "uncertainty_unit",
            ],
            "required_value_policy": (
                "finite interval with high >= low and nonblank unit"
            ),
        },
    ]
    assert payload["summary"] == {
        "actual_closure_ready": False,
        "blocker_count": 3,
        "covered_required_slot_count": 0,
        "detected_row_artifact_count": 0,
        "missing_row_input_action_count": 1,
        "minimum_rows_by_case_count": 3,
        "operator_rows_ready": False,
        "phase4_candidate_slot_matrix_count": 6,
        "phase4_metric_closure_matrix_count": 8,
        "phase4_missing_candidate_slot_count": 6,
        "phase4_refinement_receipt_plan_status": "operator_receipts_required",
        "phase4_refinement_receipt_role_count": 4,
        "template_preflight_status": "operator_rows_completion_required",
        "template_preflight_role_receipt_plan_count": 24,
        "template_preflight_role_receipt_blocked_count": 24,
        "template_preflight_operator_input_source_receipt_requirement_count": 5,
        "template_preflight_operator_input_source_receipt_blocked_count": 5,
        "raw_row_artifact_detected": False,
        "raw_row_candidate_status": "row_artifact_missing",
        "validated_row_count": 0,
        "covered_phase4_criterion_count": 8,
        "refinement_execution_plan_ready": True,
        "refinement_execution_plan_status": "operator_refinement_rows_required",
        "required_candidate_slot_count": 6,
        "required_candidate_rows_per_case": 2,
        "required_case_count": 3,
        "required_total_candidate_rows": 6,
    }
    assert payload["blockers"] == [
        "pocketmd_lite_topk_rows_not_acquired",
        "upstream_top_k_candidate_receipts_not_attached",
        "lite_refinement_metric_receipts_not_attached",
    ]
    assert payload["commands"]["import_rows"].startswith(
        "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"
    )
    assert payload["commands"]["science_actual_closure"] == (
        "python3 scripts/materialize_science_actual_closure_from_rows.py "
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json --source-id <source-id> "
        "--source-url <source-url> --source-license <license> --fail-blocked"
    )
    assert payload["commands"]["build_refinement_execution_plan"].startswith(
        "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py"
    )
    assert payload["commands"]["build_row_template_preflight"].startswith(
        "python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py"
    )
    assert payload["commands"]["review_row_template"] == (
        "sed -n '1,20p' "
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows_template.csv"
    )


def test_pocketmd_lite_source_acquisition_plan_detects_dropzone_rows(
    tmp_path: Path,
) -> None:
    rows_out = tmp_path / "pocketmd_lite_topk_rows.json"
    rows_out.write_text("[]\n", encoding="utf-8")

    payload = module.build_pocketmd_lite_source_acquisition_plan(
        repo_root=tmp_path,
        rows_out=rows_out,
    )

    assert payload["raw_row_candidate_status"]["status"] == (
        "row_artifact_detected_empty"
    )
    assert payload["raw_row_candidate_status"]["detected_row_artifact_count"] == 1
    assert payload["raw_row_candidate_status"]["first_detected_path"] == str(rows_out)
    assert payload["summary"]["raw_row_artifact_detected"] is True
    assert payload["summary"]["detected_row_artifact_count"] == 1
    assert payload["summary"]["operator_rows_ready"] is False
    assert payload["refinement_execution_plan"]["operator_rows_ready"] is False
    assert payload["missing_row_input_action_count"] == 1
    assert payload["missing_row_input_actions"][0]["operator_blockers_if_missing"] == [
        "pocketmd_lite_topk_rows_empty"
    ]
    assert payload["blockers"] == [
        "pocketmd_lite_topk_rows_empty",
        "upstream_top_k_candidate_receipts_not_attached",
        "lite_refinement_metric_receipts_not_attached",
    ]


def test_pocketmd_lite_source_acquisition_plan_validates_slot_coverage(
    tmp_path: Path,
) -> None:
    rows_out = tmp_path / "pocketmd_lite_topk_rows.csv"
    _write_valid_rows(rows_out)

    payload = module.build_pocketmd_lite_source_acquisition_plan(
        repo_root=tmp_path,
        rows_out=rows_out,
    )

    assert payload["raw_row_candidate_status"]["status"] == (
        "row_artifact_detected_validated"
    )
    assert payload["raw_row_candidate_status"]["selected_row_count"] == 6
    assert payload["raw_row_candidate_status"]["validated_row_count"] == 6
    assert payload["raw_row_candidate_status"]["validated_case_count"] == 3
    assert payload["raw_row_candidate_status"]["covered_required_slot_count"] == 6
    assert payload["raw_row_candidate_status"]["missing_required_slots"] == []
    assert payload["raw_row_candidate_status"]["coverage_ready"] is True
    assert payload["summary"]["operator_rows_ready"] is True
    assert payload["summary"]["raw_row_candidate_status"] == (
        "row_artifact_detected_validated"
    )
    assert payload["summary"]["validated_row_count"] == 6
    assert payload["summary"]["covered_required_slot_count"] == 6
    assert payload["phase4_missing_candidate_slot_count"] == 0
    assert all(
        row["status"] == "provided"
        for row in payload["phase4_candidate_slot_matrix"]
    )
    assert payload["missing_row_input_actions"] == []
    assert payload["missing_row_input_action_count"] == 0
    assert payload["pocketmd_rows_operator_action"]["status"] == "provided"
    assert payload["blockers"] == [
        "upstream_top_k_candidate_receipts_not_attached",
        "lite_refinement_metric_receipts_not_attached",
    ]


def test_pocketmd_lite_source_acquisition_plan_cli_writes_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "pocketmd_lite_source_acquisition_plan.json"
    out_md = tmp_path / "pocketmd_lite_source_acquisition_plan.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert payload["actual_closure_ready"] is False
    assert payload["summary"]["required_total_candidate_rows"] == 6
    assert payload["summary"]["required_candidate_slot_count"] == 6
    assert payload["summary"]["phase4_candidate_slot_matrix_count"] == 6
    assert payload["summary"]["phase4_metric_closure_matrix_count"] == 8
    assert payload["phase4_refinement_receipt_plan"]["receipt_role_count"] == 4
    assert payload["refinement_execution_plan"]["execution_plan_ready"] is True
    assert "# PocketMD Lite Source Acquisition Plan" in markdown
    assert "pocketmd_lite_refinement_execution_plan.json" in markdown
    assert "pocketmd_lite_topk_rows_template.csv" in markdown
    assert "pocketmd_lite_topk_rows_template_preflight.json" in markdown
    assert "build_pocketmd_lite_topk_rows_template_preflight.py" in markdown
    assert "## Operator Next Actions" in markdown
    assert "| 1 | `review_phase4_refinement_receipt_plan` |" in markdown
    assert "| 11 | `refresh_science_actual_closure_from_rows` |" in markdown
    assert "## Phase 4 Candidate Slot Matrix" in markdown
    assert "pocketmd_lite_case_001_rank_1" in markdown
    assert "## Phase 4 Metric Closure Matrix" in markdown
    assert "local_min_survival_materialized" in markdown
    assert "uncertainty_width_median" in markdown
    assert "## Missing Row Input Actions" in markdown
    assert "attach_pocketmd_rows_at_" in markdown
    assert "### PocketMD Row Preflight Action" in markdown
    assert "pocketmd_lite_topk_rows.tsv" in markdown
    assert "`preflight_does_not_run_refinement`: `True`" in markdown
    assert "### PocketMD Top-k Rows Action" in markdown
    assert "`phase4_metric_receipt_action_count`: `8`" in markdown
    assert "#### PocketMD Phase 4 Receipt Closure Actions" in markdown
    assert "local_min_survival_materialized" in markdown
    assert "interaction_persistence_receipt" in markdown
    assert "`template_is_not_evidence`: `True`" in markdown
    assert "`placeholder_or_fixture_rows_do_not_promote`: `True`" in markdown
    assert "operator_input_source.source_artifact_sha256" in markdown
    assert "verify_science_actual_closure_command" in markdown
    assert (
        "--pocketmd-rows implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    ) in markdown
    assert "--source-license <license>" in markdown
    assert "`pocketmd_lite_case_001` | 2 | `1,2`" in markdown
    assert "## Phase 4 Receipt Roles" in markdown
    assert "upstream_top_k_candidate_scope_receipt" in markdown
    assert "uncertainty_interval_receipt" in markdown
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in markdown
