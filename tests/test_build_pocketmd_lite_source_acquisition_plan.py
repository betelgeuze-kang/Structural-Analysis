from __future__ import annotations

import importlib.util
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
        "detected_row_artifact_count": 0,
        "minimum_rows_by_case_count": 3,
        "operator_rows_ready": False,
        "phase4_refinement_receipt_plan_status": "operator_receipts_required",
        "phase4_refinement_receipt_role_count": 4,
        "raw_row_artifact_detected": False,
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
    assert payload["commands"]["build_refinement_execution_plan"].startswith(
        "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py"
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
        "row_artifact_detected_unvalidated"
    )
    assert payload["raw_row_candidate_status"]["detected_row_artifact_count"] == 1
    assert payload["raw_row_candidate_status"]["first_detected_path"] == str(rows_out)
    assert payload["summary"]["raw_row_artifact_detected"] is True
    assert payload["summary"]["detected_row_artifact_count"] == 1
    assert payload["summary"]["operator_rows_ready"] is True
    assert payload["refinement_execution_plan"]["operator_rows_ready"] is True
    assert payload["blockers"] == [
        "pocketmd_lite_topk_rows_detected_but_not_materialized",
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
    assert payload["phase4_refinement_receipt_plan"]["receipt_role_count"] == 4
    assert payload["refinement_execution_plan"]["execution_plan_ready"] is True
    assert "# PocketMD Lite Source Acquisition Plan" in markdown
    assert "pocketmd_lite_refinement_execution_plan.json" in markdown
    assert "pocketmd_lite_topk_rows_template.csv" in markdown
    assert "`pocketmd_lite_case_001` | 2 | `1,2`" in markdown
    assert "## Phase 4 Receipt Roles" in markdown
    assert "upstream_top_k_candidate_scope_receipt" in markdown
    assert "uncertainty_interval_receipt" in markdown
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in markdown
