from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_buildingsmart_dirty_ifc_acquisition_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_dirty_ifc_acquisition_receipt_authors_negative_contracts_without_credit() -> None:
    payload = module.build_phase3_buildingsmart_dirty_ifc_acquisition_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-buildingsmart-dirty-ifc-acquisition-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["selected_file_count"] == 8
    assert payload["source_file_acquired_count"] == 0
    assert payload["source_checksum_attached_count"] == 0
    assert payload["expected_negative_import_contract_count"] == 8
    assert payload["dirty_import_execution_count"] == 0
    assert payload["ready_source_count"] == 0
    assert payload["redistribution_allowed_source_count"] == 0
    assert payload["commercial_use_allowed_source_count"] == 0
    assert "per_file_license_review_pending" in payload["blockers"]
    assert "dirty_import_execution_missing" in payload["blockers"]
    assert "silent_data_loss_negative_gate_not_executed" in payload["blockers"]
    assert "does not download or bundle IFC files" in payload["claim_boundary"]

    requirement = payload["phase3_ifc_import_case_requirement"]
    assert requirement["minimum_clean_dirty_import_case_count"] == 10
    assert requirement["selected_dirty_import_contract_count"] == 8
    assert requirement["quantity_credit_ready_count"] == 0
    assert requirement["status"] == "blocked"
    assert requirement["blocker"] == "dirty_ifc_import_execution_missing"

    rows = {row["case_id"]: row for row in payload["selected_files"]}
    assert set(rows) == {
        "buildingsmart_community_clinic_architectural",
        "buildingsmart_community_clinic_electrical",
        "buildingsmart_community_clinic_hvac",
        "buildingsmart_community_clinic_plumbing",
        "buildingsmart_community_clinic_structural",
        "buildingsmart_community_duplex_architectural",
        "buildingsmart_community_duplex_electrical",
        "buildingsmart_community_duplex_mep",
    }
    clinic = rows["buildingsmart_community_clinic_structural"]
    assert clinic["filename"] == "Clinic_Structural.ifc"
    assert clinic["source_url"].endswith("/Medical-Dental%20Clinic/Clinic_Structural.ifc")
    assert clinic["source_sha256"] == ""
    assert clinic["source_checksum_status"] == "pending_until_operator_acquisition"
    assert clinic["acquisition_command"][:2] == ["python3", "-c"]
    assert "urlretrieve" in clinic["acquisition_command"][2]
    assert "parents=True" in clinic["acquisition_command"][2]
    assert clinic["acquisition_command"][3] == clinic["source_url"]
    assert clinic["acquisition_command"][4] == clinic["local_path"]
    assert clinic["verification_command_after_acquisition"][2].endswith("structural_analysis.api.cli")
    assert "--out" in clinic["verification_command_after_acquisition"]
    assert "--result-out" not in clinic["verification_command_after_acquisition"]
    contract = clinic["expected_negative_import_contract"]
    assert contract["expected_status"] == "blocked"
    assert contract["text_scan_only"] is True
    assert contract["phase3_quantity_credit_claim"] is False
    assert "ifc_geometry_not_canonicalized" in contract["required_blocked_fields"]


def test_dirty_ifc_acquisition_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_buildingsmart_dirty_ifc_acquisition_receipt_missing:")


def test_dirty_ifc_acquisition_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    module.write_phase3_buildingsmart_dirty_ifc_acquisition_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["status"] = "ready"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_buildingsmart_dirty_ifc_acquisition_receipt_mismatch"
