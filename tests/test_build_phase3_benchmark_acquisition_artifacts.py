from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_benchmark_acquisition_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_benchmark_acquisition_artifacts", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase3_benchmark_acquisition_plan_blocks_without_sources_or_licenses() -> None:
    payload = module.build_phase3_benchmark_acquisition_artifact(repo_root=REPO_ROOT)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["non_seed_lane_count"] == 7
    assert payload["non_seed_source_count"] == 6
    assert payload["ready_source_count"] == 0
    assert payload["local_candidate_source_count"] == 1
    assert payload["topology_receipt_source_count"] == 4
    assert payload["source_license_receipt_source_count"] == 4
    assert payload["all_non_seed_lanes_have_acquisition_policy"] is True
    assert payload["all_non_seed_sources_have_license_checksum_and_expected_outputs"] is False
    assert payload["lanes"] == [
        "buildingsmart-clean-ifc",
        "buildingsmart-dirty-ifc",
        "commercial-cross-solver",
        "ifc-query-and-gui",
        "large-model-performance",
        "opensees-medium",
        "opensees-megatall",
    ]
    assert "license_review_pending" in payload["blockers"]
    assert "checksum_missing" in payload["blockers"]
    assert "phase3_ifc_import_case_count_below_minimum" not in payload["blockers"]
    assert "phase3_ifc_import_case_quantity_credit_missing" in payload["blockers"]
    assert "operator_reference_outputs_missing" in payload["blockers"]
    assert "operator_reference_package_missing" in payload["blockers"]
    assert "operator_reference_ingest_validator_blocked" in payload["blockers"]
    assert "cross_solver_mapping_expectations_missing" not in payload["blockers"]
    assert "opensees_medium_scorecard_execution_missing" in payload["blockers"]
    assert "phase3_scorecard_runner_not_implemented" not in payload["blockers"]
    assert "close Phase 3" in payload["claim_boundary"]

    ifc_requirement = payload["ifc_import_case_requirement"]
    assert ifc_requirement["minimum_clean_dirty_import_case_count"] == 10
    assert ifc_requirement["selected_clean_import_contract_count"] == 2
    assert ifc_requirement["selected_dirty_import_contract_count"] == 8
    assert ifc_requirement["selected_total_import_contract_count"] == 10
    assert ifc_requirement["remaining_import_contract_count"] == 0
    assert ifc_requirement["quantity_credit_ready_count"] == 0
    assert ifc_requirement["import_health_execution_receipt_path"].endswith(
        "phase3_ifc_import_health_execution_receipt.json"
    )
    assert ifc_requirement["status"] == "blocked"
    assert ifc_requirement["blocker"] == "phase3_ifc_import_case_quantity_credit_missing"
    assert "eight dirty/negative expected block contracts" in ifc_requirement["claim_boundary"]

    rows_by_source = {row["source_id"]: row for row in payload["rows"]}
    opensees_medium = rows_by_source["opensees_scbf16b_medium_candidate"]
    assert opensees_medium["lanes"] == ["opensees-medium"]
    assert opensees_medium["source_kind"] == "local_opensees_candidate_source_url_unverified"
    assert opensees_medium["source_url_or_doi"] == "local_candidate_source_url_unverified:SCBF16B"
    assert opensees_medium["license_status"] == "blocked_no_authoritative_license_source_attached"
    assert opensees_medium["checksum_status"] == "local_candidate_checksum_attached_source_url_unverified"
    assert "opensees_medium_scorecard_execution_missing" in opensees_medium["blockers"]
    assert "authoritative source URL" in opensees_medium["claim_boundary"]
    assert "redistribution rights" in opensees_medium["claim_boundary"]
    assert "OpenSees medium scorecard execution" in opensees_medium["claim_boundary"]
    assert len(opensees_medium["local_candidate_artifacts"]) == 2
    assert opensees_medium["local_candidate_artifacts"][0]["case_id"] == "SCBF16B_shell_beam_mix"
    assert opensees_medium["local_candidate_artifacts"][0]["sha256"] == (
        "ceb64448b2a04afd19f57a6652aac4859760c511fd3bb447c41991f7c415bcdc"
    )
    assert opensees_medium["existing_receipts"][0]["path"] == "implementation/phase1/opensees_topology_report.json"
    assert opensees_medium["existing_receipts"][0]["contract_pass"] is True
    assert "Topology parser evidence only" in opensees_medium["existing_receipts"][0]["claim_boundary"]
    assert opensees_medium["source_license_receipt_path"].endswith(
        "phase3_opensees_medium_source_license_receipt.json"
    )
    assert rows_by_source["opensees_megatall_model_2_large"]["lanes"] == [
        "opensees-megatall",
        "large-model-performance",
    ]
    clean_ifc = rows_by_source["buildingsmart_clean_ifc_samples"]
    assert clean_ifc["source_url_or_doi"].startswith(
        "https://github.com/buildingSMART/Sample-Test-Files/tree/main/"
    )
    assert clean_ifc["license_status"] == "declared_cc_by_4_0_product_legal_review_pending"
    assert clean_ifc["expected_output_status"] == "authored_import_health_contracts_pending_execution"
    assert "source_url_verification_pending" not in clean_ifc["blockers"]
    assert "import_expected_outputs_missing" not in clean_ifc["blockers"]
    assert "import_health_execution_missing" in clean_ifc["blockers"]
    assert clean_ifc["existing_receipts"][0]["path"].endswith(
        "phase3_buildingsmart_ifc_acquisition_receipt.json"
    )
    assert clean_ifc["existing_receipts"][0]["expected_import_health_contract_count"] == 2
    assert clean_ifc["source_license_receipt_path"].endswith("phase3_ifc_source_license_receipt.json")
    dirty_ifc = rows_by_source["buildingsmart_dirty_ifc_samples"]
    assert dirty_ifc["source_url_or_doi"] == "https://github.com/buildingsmart-community/Community-Sample-Test-Files"
    assert "dirty_file_selection_pending" not in dirty_ifc["blockers"]
    assert "dirty_import_execution_missing" in dirty_ifc["blockers"]
    assert dirty_ifc["expected_output_status"] == "authored_negative_import_contracts_pending_execution"
    assert dirty_ifc["existing_receipts"][0]["path"].endswith(
        "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
    )
    assert dirty_ifc["existing_receipts"][0]["expected_negative_import_contract_count"] == 8
    assert dirty_ifc["source_license_receipt_path"].endswith("phase3_ifc_source_license_receipt.json")
    ifc_query = rows_by_source["ifc_query_and_gui_public_corpus"]
    assert ifc_query["source_url_or_doi"] == "https://doi.org/10.48550/arXiv.2605.01698"
    assert "dataset_repository_url_missing" in ifc_query["blockers"]
    assert "source_url_verification_pending" not in ifc_query["blockers"]
    assert ifc_query["source_license_receipt_path"].endswith("phase3_ifc_source_license_receipt.json")
    commercial = rows_by_source["commercial_cross_solver_operator_imports"]
    assert commercial["truth_class"] == "comparison_reference"
    assert commercial["expected_output_status"] == (
        "authored_import_template_and_operator_contract_pending_reference_outputs"
    )
    assert "operator_reference_package_missing" in commercial["blockers"]
    assert "operator_reference_ingest_validator_blocked" in commercial["blockers"]
    assert "operator_reference_outputs_missing" in commercial["blockers"]
    assert "cross_solver_mapping_expectations_missing" not in commercial["blockers"]
    assert commercial["existing_receipts"][0]["path"].endswith(
        "phase4_commercial_comparison_import_template.json"
    )
    assert commercial["existing_receipts"][0]["contract_pass"] is True
    assert commercial["existing_receipts"][1]["path"].endswith(
        "phase4_commercial_operator_reference_contract.json"
    )
    assert commercial["existing_receipts"][1]["contract_pass"] is False
    assert commercial["existing_receipts"][1]["required_reference_solver_count"] == 2
    assert commercial["existing_receipts"][1]["current_reference_solver_count"] == 0
    assert commercial["existing_receipts"][2]["path"].endswith(
        "phase4_commercial_operator_reference_ingest_validator.json"
    )
    assert commercial["existing_receipts"][2]["contract_pass"] is False
    assert "Operator package shape" in commercial["existing_receipts"][2]["validation_scope"]
    for row in payload["rows"]:
        assert row["ready_for_phase3_quantity_credit"] is False
        assert row["redistribution_allowed"] is False
        assert row["commercial_use_allowed"] is False
        if row["source_id"] == "opensees_scbf16b_medium_candidate":
            assert row["checksum_status"] == "local_candidate_checksum_attached_source_url_unverified"
        else:
            assert row["checksum_status"].startswith("missing")
        if row["source_id"] == "buildingsmart_clean_ifc_samples":
            assert row["expected_output_status"] == "authored_import_health_contracts_pending_execution"
        elif row["source_id"] == "buildingsmart_dirty_ifc_samples":
            assert row["expected_output_status"] == "authored_negative_import_contracts_pending_execution"
        elif row["source_id"] == "commercial_cross_solver_operator_imports":
            assert row["expected_output_status"] == (
                "authored_import_template_and_operator_contract_pending_reference_outputs"
            )
        else:
            assert row["expected_output_status"].startswith("missing")
        assert row["blockers"]


def test_phase3_benchmark_acquisition_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_benchmark_acquisition_artifact(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_benchmark_acquisition_missing:")


def test_phase3_benchmark_acquisition_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "acquisition.json"
    module.write_phase3_benchmark_acquisition_artifact(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["status"] = "ready"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_benchmark_acquisition_artifact(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_benchmark_acquisition_mismatch"
