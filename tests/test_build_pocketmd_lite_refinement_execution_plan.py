from __future__ import annotations

import importlib.util
import csv
import hashlib
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


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _valid_rows(path: Path) -> None:
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
    for case_id in ("case_a", "case_b", "case_c"):
        for rank in (1, 2):
            candidate_id = f"{case_id}_rank_{rank:02d}"
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
                    "post_refinement_energy_proxy": -8.5 + rank,
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
        "pocketmd_lite_topk_rows_not_acquired",
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
    ]
    assert payload["summary"] == {
        "blocker_count": 3,
        "covered_required_slot_count": 0,
        "missing_candidate_slot_count": 6,
        "operator_rows_ready": False,
        "provided_candidate_slot_count": 0,
        "raw_row_candidate_status": "row_artifact_missing",
        "required_candidate_slot_count": 6,
        "required_case_count": 3,
        "survival_report_blocker_count": 2,
        "survival_report_ready": False,
        "validated_row_count": 0,
    }
    assert payload["candidate_slots"][0]["case_id"] == "case_a"
    assert payload["candidate_slots"][0]["top_k_rank"] == 1
    assert payload["candidate_slots"][0]["status"] == "operator_row_required"
    assert payload["candidate_slots"][0]["candidate_id_placeholder"] == "case_a_rank_01"
    assert payload["candidate_slots"][0]["source_family"] == (
        "upstream_ranked_top_k_candidate_set"
    )
    assert "upstream_top_k_provenance_ref" in payload["candidate_slots"][0][
        "required_receipt_fields"
    ]
    assert "contact_persistence_rate" in payload["candidate_slots"][0][
        "required_metric_fields"
    ]
    assert payload["raw_row_candidate_status"]["detected_row_artifact_count"] == 0
    assert payload["raw_row_candidate_status"]["status"] == "row_artifact_missing"
    assert payload["supported_row_formats"] == ["csv", "tsv", "json", "jsonl", "ndjson"]
    assert payload["required_case_fields"] == [
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
        "uncertainty_interval",
        "provenance_ref",
        "source_checksum",
    ]
    assert payload["required_flat_row_fields"] == [
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
    assert "uncertainty_interval" not in payload["candidate_slots"][0][
        "required_row_fields"
    ]
    assert payload["candidate_slots"][0]["required_metric_fields"][-3:] == [
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
    ]
    assert payload["candidate_slot_statuses"][0]["slot_id"] == "case_a_rank_01"
    assert payload["candidate_slot_statuses"][0]["status"] == "row_slot_missing"
    assert payload["candidate_slot_statuses"][0]["missing"] is True
    assert payload["candidate_slot_statuses"][0]["provided"] is False
    assert payload["candidate_slot_statuses"][0]["operator_action"] == (
        "attach_pocketmd_topk_row_for_case_a_rank_01"
    )
    assert payload["candidate_slot_statuses"][0]["required_metric_fields"][-3:] == [
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
    ]
    assert payload["top_k_slot_status_summary"] == {
        "case_top_k_rank_prefixes": {},
        "covered_required_slot_count": 0,
        "first_missing_candidate_slot": {
            "case_id": "case_a",
            "operator_action": "attach_pocketmd_topk_row_for_case_a_rank_01",
            "slot_id": "case_a_rank_01",
            "top_k_rank": 1,
        },
        "missing_candidate_slot_count": 6,
        "missing_candidate_slots": [
            {
                "case_id": "case_a",
                "operator_action": "attach_pocketmd_topk_row_for_case_a_rank_01",
                "slot_id": "case_a_rank_01",
                "top_k_rank": 1,
            },
            {
                "case_id": "case_a",
                "operator_action": "attach_pocketmd_topk_row_for_case_a_rank_02",
                "slot_id": "case_a_rank_02",
                "top_k_rank": 2,
            },
            {
                "case_id": "case_b",
                "operator_action": "attach_pocketmd_topk_row_for_case_b_rank_01",
                "slot_id": "case_b_rank_01",
                "top_k_rank": 1,
            },
            {
                "case_id": "case_b",
                "operator_action": "attach_pocketmd_topk_row_for_case_b_rank_02",
                "slot_id": "case_b_rank_02",
                "top_k_rank": 2,
            },
            {
                "case_id": "case_c",
                "operator_action": "attach_pocketmd_topk_row_for_case_c_rank_01",
                "slot_id": "case_c_rank_01",
                "top_k_rank": 1,
            },
            {
                "case_id": "case_c",
                "operator_action": "attach_pocketmd_topk_row_for_case_c_rank_02",
                "slot_id": "case_c_rank_02",
                "top_k_rank": 2,
            },
        ],
        "operator_rows_ready": False,
        "provided_candidate_slot_count": 0,
        "provided_candidate_slots": [],
        "raw_row_candidate_status": "row_artifact_missing",
        "required_candidate_slot_count": 6,
        "selected_path": "",
        "validated_row_count": 0,
    }
    assert payload["expected_rows_artifact"] == str(rows_out)
    assert payload["expected_operator_intake_artifact"] == str(operator_intake)
    unblock = payload["operator_unblock_packet"]
    assert unblock["status"] == "operator_refinement_rows_required"
    assert unblock["row_template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows_template.csv"
    )
    assert unblock["expected_rows_artifact"] == str(rows_out)
    assert unblock["expected_operator_intake_artifact"] == str(operator_intake)
    assert unblock["required_candidate_slot_count"] == 6
    assert unblock["provided_candidate_slot_count"] == 0
    assert unblock["missing_candidate_slot_count"] == 6
    assert unblock["first_missing_candidate_slot"]["slot_id"] == "case_a_rank_01"
    assert unblock["operator_sequence"][:2] == [
        "preflight_pocketmd_lite_topk_rows_template",
        "fill_pocketmd_lite_topk_rows_from_template",
    ]
    assert unblock["row_template_preflight_artifact"].endswith(
        "pocketmd_lite_topk_rows_template_preflight.json"
    )
    assert "build_pocketmd_lite_topk_rows_template_preflight.py" in unblock[
        "commands"
    ]["build_row_template_preflight"]
    assert "materialize_pocketmd_lite_operator_intake_from_rows.py" in payload[
        "operator_commands"
    ]["import_rows"]
    assert "does not run refinement" in payload["claim_boundary"]


def test_refinement_execution_plan_marks_valid_rows_ready(
    tmp_path: Path,
) -> None:
    source_plan = tmp_path / "source_plan.json"
    survival_report = tmp_path / "survival_report.json"
    rows_out = tmp_path / "pocketmd_lite_topk_rows.csv"
    operator_intake = tmp_path / "pocketmd_lite_operator_intake.json"
    _source_plan(source_plan)
    _survival_report(survival_report)
    _valid_rows(rows_out)

    payload = module.build_pocketmd_lite_refinement_execution_plan(
        repo_root=tmp_path,
        source_acquisition_plan_path=source_plan,
        survival_report_path=survival_report,
        rows_out=rows_out,
        operator_intake_out=operator_intake,
    )

    assert payload["operator_rows_ready"] is True
    assert payload["raw_row_candidate_status"]["status"] == (
        "row_artifact_detected_validated"
    )
    assert payload["raw_row_candidate_status"]["validated_row_count"] == 6
    assert payload["raw_row_candidate_status"]["covered_required_slot_count"] == 6
    assert payload["raw_row_candidate_status"]["missing_required_slots"] == []
    assert payload["summary"]["operator_rows_ready"] is True
    assert payload["summary"]["validated_row_count"] == 6
    assert payload["summary"]["covered_required_slot_count"] == 6
    assert payload["summary"]["provided_candidate_slot_count"] == 6
    assert payload["summary"]["missing_candidate_slot_count"] == 0
    assert payload["candidate_slot_statuses"][0]["status"] == "row_slot_provided"
    assert payload["candidate_slot_statuses"][0]["missing"] is False
    assert payload["candidate_slot_statuses"][0]["provided"] is True
    assert payload["candidate_slot_statuses"][0]["operator_action"] == (
        "review_validated_pocketmd_topk_row_for_case_a_rank_01"
    )
    assert payload["top_k_slot_status_summary"]["operator_rows_ready"] is True
    assert payload["top_k_slot_status_summary"]["provided_candidate_slot_count"] == 6
    assert payload["top_k_slot_status_summary"]["missing_candidate_slot_count"] == 0
    assert payload["top_k_slot_status_summary"]["missing_candidate_slots"] == []
    assert payload["top_k_slot_status_summary"]["first_missing_candidate_slot"] == {}
    assert payload["operator_unblock_packet"]["status"] == (
        "operator_refinement_rows_ready"
    )
    assert payload["operator_unblock_packet"]["provided_candidate_slot_count"] == 6
    assert payload["operator_unblock_packet"]["missing_candidate_slot_count"] == 0
    assert payload["blockers"] == [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
    ]


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
    assert payload["top_k_slot_status_summary"]["missing_candidate_slot_count"] == 6
