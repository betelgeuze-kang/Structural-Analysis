from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_buildingsmart_ifc_acquisition_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_buildingsmart_ifc_acquisition_receipt_authors_expected_import_contracts() -> None:
    payload = module.build_phase3_buildingsmart_ifc_acquisition_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-buildingsmart-ifc-acquisition-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["selected_file_count"] == 2
    assert payload["source_file_acquired_count"] == 0
    assert payload["source_checksum_attached_count"] == 0
    assert payload["expected_import_health_contract_count"] == 2
    assert payload["import_health_execution_count"] == 0
    assert payload["ready_source_count"] == 0
    assert payload["redistribution_allowed_source_count"] == 0
    assert payload["commercial_use_allowed_source_count"] == 0
    assert "source_sha256_missing" in payload["blockers"]
    assert "import_health_execution_missing" in payload["blockers"]
    assert "phase3_ifc_import_case_count_below_minimum" in payload["blockers"]
    assert "does not download or bundle IFC files" in payload["claim_boundary"]

    requirement = payload["phase3_ifc_import_case_requirement"]
    assert requirement["minimum_clean_dirty_import_case_count"] == 10
    assert requirement["selected_clean_import_contract_count"] == 2
    assert requirement["selected_dirty_import_contract_count"] == 0
    assert requirement["selected_total_import_contract_count"] == 2
    assert requirement["remaining_import_contract_count"] == 8
    assert requirement["quantity_credit_ready_count"] == 0
    assert requirement["status"] == "blocked"
    assert requirement["blocker"] == "phase3_ifc_import_case_count_below_minimum"
    assert "no dirty/negative IFC contracts" in requirement["claim_boundary"]

    rows = {row["case_id"]: row for row in payload["selected_files"]}
    building = rows["buildingsmart_pcert_building_structural"]
    assert building["filename"] == "Building-Structural.ifc"
    assert building["source_url"].endswith("/Building-Structural.ifc")
    assert building["source_sha256"] == ""
    assert building["source_checksum_status"] == "pending_until_operator_acquisition"
    assert building["acquisition_command"][:2] == ["python3", "-c"]
    assert "urlretrieve" in building["acquisition_command"][2]
    assert "parents=True" in building["acquisition_command"][2]
    assert building["acquisition_command"][3] == building["source_url"]
    assert building["acquisition_command"][4] == building["local_path"]
    assert building["verification_command_after_acquisition"][2].endswith("structural_analysis.api.cli")
    assert "--out" in building["verification_command_after_acquisition"]
    assert "--result-out" not in building["verification_command_after_acquisition"]
    assert building["expected_import_health_contract"]["expected_status"] == "blocked"
    assert building["expected_import_health_contract"]["text_scan_only"] is True
    assert "ifc_geometry_not_canonicalized" in building["expected_import_health_contract"]["required_blocked_fields"]
    assert building["expected_import_health_contract"]["phase3_quantity_credit_claim"] is False

    bridge = rows["buildingsmart_pcert_infra_bridge"]
    assert bridge["filename"] == "Infra-Bridge.ifc"
    assert bridge["source_url"].endswith("/Infra-Bridge.ifc")
    assert bridge["expected_import_health_contract"]["source_format"] == "ifc_step"
    assert "IFCMEMBER" in bridge["expected_import_health_contract"]["expected_structural_classes_present"]


def test_buildingsmart_ifc_acquisition_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_buildingsmart_ifc_acquisition_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_buildingsmart_ifc_acquisition_receipt_missing:")


def test_buildingsmart_ifc_acquisition_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    module.write_phase3_buildingsmart_ifc_acquisition_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["status"] = "ready"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_buildingsmart_ifc_acquisition_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_buildingsmart_ifc_acquisition_receipt_mismatch"
