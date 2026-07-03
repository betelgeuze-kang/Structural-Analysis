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
        "minimum_rows_by_case_count": 3,
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
    assert "# PocketMD Lite Source Acquisition Plan" in markdown
    assert "`pocketmd_lite_case_001` | 2 | `1,2`" in markdown
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in markdown
