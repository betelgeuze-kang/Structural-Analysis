from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_ifc_source_license_receipt.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_ifc_source_license_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase3_ifc_source_license_receipt_keeps_claim_boundary_blocked() -> None:
    payload = module.build_phase3_ifc_source_license_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-ifc-source-license-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["source_count"] == 3
    assert payload["source_url_verified_count"] == 3
    assert payload["ready_source_count"] == 0
    assert payload["source_file_acquired_count"] == 10
    assert payload["source_checksum_attached_count"] == 10
    assert payload["import_health_execution_count"] == 10
    assert payload["import_health_contract_pass_count"] == 10
    assert payload["visible_entity_accounting_case_count"] == 10
    assert payload["silent_import_loss_gate_pass_count"] == 10
    assert payload["quantity_credit_ready_count"] == 0
    assert payload["source_license_review_pass_count"] == 0
    assert payload["source_license_review_blocker_count"] == 3
    assert payload["redistribution_allowed_source_count"] == 0
    assert payload["commercial_use_allowed_source_count"] == 0
    assert "selected_file_checksums_missing" not in payload["blockers"]
    assert "import_health_execution_missing" not in payload["blockers"]
    assert "dirty_import_execution_missing" not in payload["blockers"]
    assert "query_expected_answers_missing" in payload["blockers"]
    assert "phase3_ifc_import_case_count_below_minimum" not in payload["blockers"]
    assert "phase3_ifc_import_case_quantity_credit_missing" in payload["blockers"]
    assert "silent_import_loss_gate_not_executed" not in payload["blockers"]
    assert "silent_import_loss_gate_not_implemented" not in payload["blockers"]
    assert "download or bundle" in payload["claim_boundary"]
    assert "close Phase 3" in payload["claim_boundary"]

    requirement = payload["phase3_ifc_import_case_requirement"]
    assert requirement["minimum_clean_dirty_import_case_count"] == 10
    assert requirement["selected_clean_import_contract_count"] == 2
    assert requirement["selected_dirty_import_contract_count"] == 8
    assert requirement["selected_total_import_contract_count"] == 10
    assert requirement["remaining_import_contract_count"] == 0
    assert requirement["quantity_credit_ready_count"] == 0
    assert requirement["import_health_execution_receipt_path"].endswith(
        "phase3_ifc_import_health_execution_receipt.json"
    )
    assert requirement["status"] == "blocked"
    assert requirement["blocker"] == "phase3_ifc_import_case_quantity_credit_missing"
    assert "eight dirty/import-hardening community contracts" in requirement["claim_boundary"]

    sources = {row["source_id"]: row for row in payload["sources"]}
    pcert = sources["buildingsmart_pcert_sample_scene"]
    assert pcert["lanes"] == ["buildingsmart-clean-ifc"]
    assert pcert["source_url"] == "https://github.com/buildingSMART/Sample-Test-Files"
    assert pcert["declared_license"] == "CC-BY-4.0"
    assert pcert["acquisition_receipt_path"].endswith("phase3_buildingsmart_ifc_acquisition_receipt.json")
    assert pcert["redistribution_allowed"] is False
    assert pcert["commercial_use_allowed"] is False
    assert pcert["ready_for_phase3_quantity_credit"] is False
    assert pcert["checksum_status"] == "selected_file_checksums_attached_from_local_private_corpus"
    assert pcert["source_file_acquired_count"] == 2
    assert pcert["source_checksum_attached_count"] == 2
    assert pcert["import_health_execution_count"] == 2
    assert pcert["import_health_contract_pass_count"] == 2
    assert pcert["silent_import_loss_gate_pass_count"] == 2
    assert pcert["expected_output_status"] == "import_health_contracts_executed_and_passed_pending_license_review"
    assert pcert["blockers"] == ["product_legal_license_review_pending"]
    assert "silent_import_loss_gate_not_executed" not in pcert["blockers"]
    assert "silent_import_loss_gate_not_implemented" not in pcert["blockers"]
    assert "Building-Structural.ifc" in pcert["candidate_files"]
    assert "Infra-Bridge.ifc" in pcert["candidate_files"]

    community = sources["buildingsmart_community_dirty_samples"]
    assert community["lanes"] == ["buildingsmart-dirty-ifc"]
    assert community["source_url"] == "https://github.com/buildingsmart-community/Community-Sample-Test-Files"
    assert "dirty_file_selection_pending" not in community["blockers"]
    assert "dirty_import_execution_missing" not in community["blockers"]
    assert community["blockers"] == ["per_file_license_review_pending"]
    assert community["expected_output_status"] == "import_health_contracts_executed_and_passed_pending_license_review"
    assert community["acquisition_receipt_path"].endswith(
        "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
    )
    assert len(community["candidate_files"]) == 8
    assert "Clinic_Structural.ifc" in community["candidate_files"]
    assert community["checksum_status"] == "selected_file_checksums_attached_from_local_private_corpus"
    assert community["source_file_acquired_count"] == 8
    assert community["source_checksum_attached_count"] == 8
    assert community["import_health_execution_count"] == 8
    assert community["import_health_contract_pass_count"] == 8
    assert community["silent_import_loss_gate_pass_count"] == 8

    ifc_bench = sources["ifc_bench_v2_arxiv_query_tasks"]
    assert ifc_bench["lanes"] == ["ifc-query-and-gui"]
    assert ifc_bench["source_url"] == "https://arxiv.org/abs/2605.01698"
    assert ifc_bench["source_doi"] == "https://doi.org/10.48550/arXiv.2605.01698"
    assert "dataset_repository_url_missing" in ifc_bench["blockers"]
    assert "query_expected_answers_missing" in ifc_bench["blockers"]


def test_phase3_ifc_source_license_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_ifc_source_license_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_ifc_source_license_receipt_missing:")


def test_phase3_ifc_source_license_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    module.write_phase3_ifc_source_license_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["status"] = "ready"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_ifc_source_license_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_ifc_source_license_receipt_mismatch"
