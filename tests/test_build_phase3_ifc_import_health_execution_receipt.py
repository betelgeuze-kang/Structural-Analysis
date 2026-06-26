from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_ifc_import_health_execution_receipt.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_ifc_import_health_execution_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_ifc_import_health_execution_blocks_until_local_files_exist() -> None:
    payload = module.build_phase3_ifc_import_health_execution_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-ifc-import-health-execution-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["candidate_case_count"] == 10
    assert payload["minimum_clean_dirty_import_case_count"] == 10
    assert payload["source_file_acquired_count"] == 0
    assert payload["source_checksum_attached_count"] == 0
    assert payload["import_health_execution_count"] == 0
    assert payload["import_health_contract_pass_count"] == 0
    assert payload["visible_entity_accounting_case_count"] == 0
    assert payload["silent_import_loss_gate_pass_count"] == 0
    assert payload["silent_import_loss_gate"]["status"] == "blocked"
    assert payload["silent_import_loss_gate"]["contract_pass"] is False
    assert payload["silent_import_loss_gate"]["silent_import_loss_zero"] is False
    assert payload["silent_import_loss_gate"]["required_case_count"] == 10
    assert payload["silent_import_loss_gate"]["candidate_case_count"] == 10
    assert "silent_import_loss_gate_not_executed" in payload["silent_import_loss_gate"]["blockers"]
    assert payload["quantity_credit_ready_count"] == 0
    assert "source_file_not_acquired" in payload["blockers"]
    assert "source_sha256_missing" in payload["blockers"]
    assert "import_health_execution_missing" in payload["blockers"]
    assert "does not download files" in payload["claim_boundary"]
    assert {row["lane_kind"] for row in payload["case_receipts"]} == {"clean", "dirty"}
    assert all(row["quantity_credit_ready"] is False for row in payload["case_receipts"])
    assert all(row["silent_import_loss_gate"]["contract_pass"] is False for row in payload["case_receipts"])


def test_ifc_import_health_case_receipt_executes_expected_blocked_contract(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private_corpus/phase3/test/model.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#1=IFCBEAM('b1',$,'B1',$,$,$,$,$);",
                "ENDSEC;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    row = {
        "case_id": "test_ifc_case",
        "lane_kind": "clean",
        "filename": "model.ifc",
        "source_url": "https://example.invalid/model.ifc",
        "local_path": ifc_path.relative_to(tmp_path).as_posix(),
        "selected_benchmark_lanes": ["buildingsmart-clean-ifc"],
        "truth_class": "geometry_and_import_truth",
        "contract": {
            "expected_status": "blocked",
            "required_warning_fragments": ["IFC adapter is STEP text scan only"],
            "required_blocked_fields": ["ifc_geometry_not_canonicalized"],
        },
    }

    receipt = module._case_receipt(tmp_path, row, execute=True)

    assert receipt["status"] == "blocked"
    assert receipt["source_file_acquired"] is True
    assert receipt["source_sha256"].startswith("sha256:")
    assert receipt["import_health_executed"] is True
    assert receipt["import_health_contract_pass"] is True
    assert receipt["silent_import_loss_gate"]["status"] == "pass"
    assert receipt["silent_import_loss_gate"]["contract_pass"] is True
    assert receipt["silent_import_loss_gate"]["silent_import_loss_zero"] is True
    assert receipt["silent_import_loss_gate"]["visible_entity_accounting"] is True
    assert receipt["silent_import_loss_gate"]["record_count"] == 1
    assert receipt["silent_import_loss_gate"]["parsed_record_count"] == 1
    assert receipt["silent_import_loss_gate"]["structural_entity_count"] == 1
    assert receipt["silent_import_loss_gate"]["unsupported_feature_count"] > 0
    assert receipt["silent_import_loss_gate"]["warning_count"] > 0
    assert receipt["silent_import_loss_gate"]["blockers"] == []
    assert receipt["quantity_credit_ready"] is False
    assert receipt["blockers"] == []
    assert receipt["execution"]["return_code"] == 2
    assert receipt["execution"]["result_exists"] is True
    assert receipt["execution"]["report_exists"] is True
    assert receipt["execution"]["report"]["status"] == "blocked"
    assert receipt["execution"]["result"]["status"] == "blocked"
    assert receipt["execution"]["result"]["metrics"]["record_count"] == 1
    assert receipt["execution"]["result"]["metrics"]["entity_counts"]["IFCBEAM"] == 1


def test_ifc_import_health_execution_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_ifc_import_health_execution_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_ifc_import_health_execution_receipt_missing:")


def test_ifc_import_health_execution_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    module.write_phase3_ifc_import_health_execution_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["status"] = "ready"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_ifc_import_health_execution_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_ifc_import_health_execution_receipt_mismatch"
