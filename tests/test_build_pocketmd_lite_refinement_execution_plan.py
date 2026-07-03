from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_pocketmd_lite_refinement_execution_plan.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_pocketmd_lite_refinement_execution_plan",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _source_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "minimum_rows_by_case": [
                    {
                        "case_id": "case_a",
                        "minimum_candidate_rows": 2,
                        "required_top_k_rank_prefix": [1, 2],
                    },
                    {
                        "case_id": "case_b",
                        "minimum_candidate_rows": 2,
                        "required_top_k_rank_prefix": [1, 2],
                    },
                    {
                        "case_id": "case_c",
                        "minimum_candidate_rows": 2,
                        "required_top_k_rank_prefix": [1, 2],
                    },
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _survival_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_pass": False,
                "blockers": [
                    "pocketmd_lite_topk_candidate_rows_missing",
                    "pocketmd_lite_local_min_survival_rows_missing",
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_refinement_execution_plan_enumerates_candidate_slots(
    tmp_path: Path,
) -> None:
    source_plan = tmp_path / "source_plan.json"
    survival_report = tmp_path / "survival_report.json"
    rows_out = tmp_path / "pocketmd_lite_topk_rows.json"
    operator_intake = tmp_path / "pocketmd_lite_operator_intake.json"
    _source_plan(source_plan)
    _survival_report(survival_report)

    payload = module.build_pocketmd_lite_refinement_execution_plan(
        repo_root=tmp_path,
        source_acquisition_plan_path=source_plan,
        survival_report_path=survival_report,
        rows_out=rows_out,
        operator_intake_out=operator_intake,
    )

    assert payload["schema_version"] == "pocketmd-lite-refinement-execution-plan.v1"
    assert payload["status"] == "operator_refinement_rows_required"
    assert payload["contract_pass"] is True
    assert payload["execution_plan_ready"] is True
    assert payload["operator_rows_ready"] is False
    assert payload["survival_report_ready"] is False
    assert payload["actual_closure_ready"] is False
    assert payload["required_case_count"] == 3
    assert payload["required_candidate_slot_count"] == 6
    assert payload["blockers"] == [
        "pocketmd_lite_topk_rows_not_detected",
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
    ]
    assert payload["summary"] == {
        "blocker_count": 3,
        "operator_rows_ready": False,
        "required_candidate_slot_count": 6,
        "required_case_count": 3,
        "survival_report_blocker_count": 2,
        "survival_report_ready": False,
    }
    assert payload["candidate_slots"][0]["case_id"] == "case_a"
    assert payload["candidate_slots"][0]["top_k_rank"] == 1
    assert payload["candidate_slots"][0]["status"] == "operator_row_required"
    assert "upstream_top_k_provenance_ref" in payload["candidate_slots"][0][
        "required_receipt_fields"
    ]
    assert "contact_persistence_rate" in payload["candidate_slots"][0][
        "required_metric_fields"
    ]
    assert payload["raw_row_candidate_status"]["detected_row_artifact_count"] == 0
    assert payload["supported_row_formats"] == ["csv", "tsv", "json", "jsonl", "ndjson"]
    assert payload["expected_rows_artifact"] == str(rows_out)
    assert payload["expected_operator_intake_artifact"] == str(operator_intake)
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in payload[
        "operator_commands"
    ]["import_rows"]
    assert "does not run refinement" in payload["claim_boundary"]


def test_refinement_execution_plan_cli_writes_artifact(tmp_path: Path) -> None:
    source_plan = tmp_path / "source_plan.json"
    survival_report = tmp_path / "survival_report.json"
    rows_out = tmp_path / "pocketmd_lite_topk_rows.json"
    operator_intake = tmp_path / "pocketmd_lite_operator_intake.json"
    out = tmp_path / "pocketmd_lite_refinement_execution_plan.json"
    _source_plan(source_plan)
    _survival_report(survival_report)

    assert module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--source-acquisition-plan",
            str(source_plan),
            "--survival-report",
            str(survival_report),
            "--rows-out",
            str(rows_out),
            "--operator-intake-out",
            str(operator_intake),
            "--out",
            str(out),
        ]
    ) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["required_candidate_slot_count"] == 6
    assert payload["summary"]["blocker_count"] == 3
