from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _load_module(name: str, script_name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / script_name)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bundle_module = _load_module(
    "materialize_pocketmd_lite_refinement_receipt_bundle",
    "materialize_pocketmd_lite_refinement_receipt_bundle.py",
)
rows_module = _load_module(
    "materialize_pocketmd_lite_topk_rows_from_receipt_bundle",
    "materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py",
)
intake_module = _load_module(
    "materialize_pocketmd_lite_operator_intake_from_rows",
    "materialize_pocketmd_lite_operator_intake_from_rows.py",
)
survival_module = _load_module(
    "materialize_pocketmd_lite_topk_survival_report",
    "materialize_pocketmd_lite_topk_survival_report.py",
)


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "execution_plan_ready": True,
                "candidate_slot_statuses": [
                    {
                        "slot_id": f"{case_id}_rank_{rank:02d}",
                        "case_id": case_id,
                        "top_k_rank": rank,
                        "candidate_id_placeholder": f"{case_id}_rank_{rank:02d}",
                        "source_family": "upstream_ranked_top_k_candidate_set",
                    }
                    for case_id in ("case_a", "case_b", "case_c")
                    for rank in (1, 2)
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _completed_receipt(bundle_row: dict[str, object]) -> dict[str, object]:
    receipt = copy.deepcopy(bundle_row["receipt_template_payload"])
    case_id = str(bundle_row["case_id"])
    rank = int(bundle_row["top_k_rank"])
    candidate_id = str(bundle_row["candidate_id_placeholder"])
    receipt.update(
        {
            "status": "complete",
            "candidate_id": candidate_id,
            "upstream_top_k_provenance_ref": (
                f"https://zenodo.org/records/7654321/files/"
                f"upstream-{case_id}-{candidate_id}.json#row"
            ),
            "upstream_top_k_source_checksum": _checksum(
                f"upstream:{case_id}:{candidate_id}"
            ),
            "pre_refinement_energy_proxy": -8.0 + rank,
            "post_refinement_energy_proxy": -8.5 + rank,
            "local_min_survived": True,
            "contact_persistence_rate": 0.8,
            "h_bond_persistence_rate": 0.7,
            "clash_count_before": 3,
            "clash_count_after": 1,
            "uncertainty_low": 0.1,
            "uncertainty_high": 0.3,
            "uncertainty_unit": "energy_proxy_delta",
            "provenance_ref": (
                f"https://zenodo.org/records/7654321/files/"
                f"refinement-{case_id}-{candidate_id}.json#row"
            ),
            "source_checksum": _checksum(f"refinement:{case_id}:{candidate_id}"),
            "operator_input_source": {
                "source_id": "pocketmd_lite_receipts_zenodo_7654321",
                "source_url": "https://zenodo.org/records/7654321",
                "source_license": "CC-BY-4.0",
                "source_artifact": (
                    f"https://zenodo.org/records/7654321/files/"
                    f"refinement-{case_id}-{candidate_id}.json"
                ),
                "source_artifact_sha256": _checksum(
                    f"artifact:{case_id}:{candidate_id}"
                ),
            },
        }
    )
    return receipt


def _materialize_bundle(tmp_path: Path) -> dict[str, object]:
    refinement_plan = tmp_path / "refinement_plan.json"
    bundle_out = tmp_path / "receipt_bundle.json"
    _write_plan(refinement_plan)
    return bundle_module.materialize_pocketmd_lite_refinement_receipt_bundle(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        out=bundle_out,
        receipt_root=Path("operator_receipts"),
        rows_out=tmp_path / "pocketmd_lite_topk_rows.json",
    )


def _write_completed_receipts(tmp_path: Path, bundle: dict[str, object]) -> None:
    for bundle_row in bundle["bundle_rows"]:
        receipt_path = tmp_path / str(bundle_row["receipt_ref"])
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(_completed_receipt(bundle_row), sort_keys=True),
            encoding="utf-8",
        )


def test_materializes_pocketmd_topk_rows_from_completed_receipt_bundle(
    tmp_path: Path,
) -> None:
    bundle = _materialize_bundle(tmp_path)
    _write_completed_receipts(tmp_path, bundle)
    receipt_bundle = tmp_path / "receipt_bundle.json"
    out_rows = tmp_path / "pocketmd_lite_topk_rows.json"
    out_report = tmp_path / "rows_report.json"

    report = rows_module.materialize_pocketmd_lite_topk_rows_from_receipt_bundle(
        repo_root=tmp_path,
        receipt_bundle=receipt_bundle,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "rows_materialized"
    assert report["contract_pass"] is True
    assert report["rows_materialized"] is True
    assert report["receipt_count"] == 6
    assert report["ready_receipt_count"] == 6
    assert report["incomplete_receipt_count"] == 0
    assert report["first_incomplete_receipt"] == {}
    assert report["receipt_completion_action_plan"] == []
    assert report["receipt_metric_family_count"] == 5
    assert report["receipt_metric_family_blocked_count"] == 0
    assert report["receipt_metric_family_missing_field_occurrence_count"] == 0
    assert {
        row["metric_family_id"]: row["status"]
        for row in report["receipt_metric_family_completion_plan"]
    } == {
        "local_min_survival": "ready",
        "contact_persistence": "ready",
        "h_bond_persistence": "ready",
        "clash_relief": "ready",
        "uncertainty": "ready",
    }
    assert report["unique_missing_required_fields"] == []
    assert report["total_missing_required_field_count"] == 0
    assert report["row_count"] == 6
    assert report["case_count"] == 3
    rows_payload = json.loads(out_rows.read_text(encoding="utf-8"))
    assert rows_payload["schema_version"] == "pocketmd-lite-topk-rows.v1"
    assert rows_payload["top_k_refinement_rows"][0]["top_k_rank"] == 1
    assert rows_payload["top_k_refinement_rows"][0]["local_min_survived"] is True
    assert rows_payload["top_k_refinement_rows"][0]["uncertainty_interval"] == {
        "high": 0.3,
        "low": 0.1,
        "unit": "energy_proxy_delta",
    }
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "rows_materialized"
    )

    intake = intake_module.build_pocketmd_lite_operator_intake_from_rows(
        rows_path=out_rows,
        repo_root=tmp_path,
        source_id="pocketmd_lite_receipts_zenodo_7654321",
        source_url="https://zenodo.org/records/7654321",
        source_license="CC-BY-4.0",
    )
    survival = survival_module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=tmp_path,
    )
    assert survival["status"] == "ready"
    assert survival["product_surface_ready"] is True


def test_pocketmd_topk_rows_from_receipt_bundle_blocks_missing_receipts(
    tmp_path: Path,
) -> None:
    _materialize_bundle(tmp_path)
    out_rows = tmp_path / "pocketmd_lite_topk_rows.json"
    out_report = tmp_path / "rows_report.json"

    report = rows_module.materialize_pocketmd_lite_topk_rows_from_receipt_bundle(
        repo_root=tmp_path,
        receipt_bundle=tmp_path / "receipt_bundle.json",
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "operator_receipts_completion_required"
    assert report["contract_pass"] is False
    assert report["rows_materialized"] is False
    assert report["receipt_count"] == 6
    assert report["ready_receipt_count"] == 0
    assert report["incomplete_receipt_count"] == 6
    assert len(report["receipt_completion_action_plan"]) == 6
    assert "receipt_file_missing" in "\n".join(report["blockers"])
    assert not out_rows.exists()
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "operator_receipts_completion_required"
    )


def test_pocketmd_topk_rows_from_receipt_bundle_reports_incomplete_templates(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    receipt_bundle = tmp_path / "receipt_bundle.json"
    _write_plan(refinement_plan)
    bundle_module.materialize_pocketmd_lite_refinement_receipt_bundle(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        out=receipt_bundle,
        receipt_root=Path("operator_receipts"),
        rows_out=tmp_path / "pocketmd_lite_topk_rows.json",
        write_template_files=True,
    )
    out_rows = tmp_path / "pocketmd_lite_topk_rows.json"
    out_report = tmp_path / "rows_report.json"

    report = rows_module.materialize_pocketmd_lite_topk_rows_from_receipt_bundle(
        repo_root=tmp_path,
        receipt_bundle=receipt_bundle,
        out_rows=out_rows,
        out_report=out_report,
    )

    blockers_text = "\n".join(report["blockers"])
    assert report["status"] == "operator_receipts_completion_required"
    assert report["receipt_count"] == 6
    assert report["ready_receipt_count"] == 0
    assert report["incomplete_receipt_count"] == 6
    assert "receipt_not_complete" in blockers_text
    assert "receipt_file_missing" not in blockers_text
    assert "operator_input_source" not in blockers_text
    assert "row_normalization_failed" not in blockers_text
    first_status = report["row_statuses"][0]
    first_action = report["receipt_completion_action_plan"][0]
    assert report["first_incomplete_receipt"] == first_action
    assert first_action["receipt_ref"].endswith("case_a/rank_01_refinement_receipt.json")
    assert first_action["completion_missing_required_field_count"] == 18
    assert first_action["operator_completion_action"] == (
        "fill_completion_missing_required_fields_and_set_status_complete"
    )
    assert report["receipt_metric_family_count"] == 5
    assert report["receipt_metric_family_blocked_count"] == 5
    assert report["receipt_metric_family_missing_field_occurrence_count"] == 54
    metric_family_plan = {
        row["metric_family_id"]: row
        for row in report["receipt_metric_family_completion_plan"]
    }
    assert metric_family_plan["local_min_survival"][
        "blocked_receipt_count"
    ] == 6
    assert metric_family_plan["local_min_survival"][
        "missing_field_occurrence_count"
    ] == 18
    assert metric_family_plan["local_min_survival"][
        "first_blocked_receipt"
    ]["missing_receipt_fields"] == [
        "pre_refinement_energy_proxy",
        "post_refinement_energy_proxy",
        "local_min_survived",
    ]
    assert metric_family_plan["contact_persistence"][
        "missing_field_occurrence_count"
    ] == 6
    assert metric_family_plan["h_bond_persistence"][
        "missing_field_occurrence_count"
    ] == 6
    assert metric_family_plan["clash_relief"][
        "missing_field_occurrence_count"
    ] == 12
    assert metric_family_plan["uncertainty"][
        "missing_field_occurrence_count"
    ] == 12
    assert report["unique_missing_required_field_count"] == 18
    assert report["total_missing_required_field_count"] == 108
    assert first_status["receipt_complete"] is False
    assert first_status["completion_required_field_count"] == 23
    assert first_status["completion_filled_required_field_count"] == 5
    assert first_status["completion_missing_required_field_count"] == 18
    assert first_status["operator_completion_action"] == (
        "fill_completion_missing_required_fields_and_set_status_complete"
    )
    assert first_status["completion_missing_required_fields"] == [
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
        "provenance_ref",
        "source_checksum",
        "operator_input_source.source_id",
        "operator_input_source.source_url",
        "operator_input_source.source_license",
        "operator_input_source.source_artifact",
        "operator_input_source.source_artifact_sha256",
    ]
    assert not out_rows.exists()
