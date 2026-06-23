from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase6_silent_import_loss_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase6_silent_import_loss_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase6_silent_import_loss_status_blocks_without_ifc_execution() -> None:
    payload = module.build_phase6_silent_import_loss_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase6-silent-import-loss-status.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["required_ifc_import_case_count"] == 10
    assert payload["clean_selected_file_count"] == 2
    assert payload["dirty_selected_file_count"] == 8
    assert payload["selected_import_case_count"] == 10
    assert payload["import_health_execution_count"] == 0
    assert payload["import_health_contract_pass_count"] == 0
    assert payload["evidence_requirements"]["clean_dirty_import_case_count"] == {
        "current": 10,
        "required": 10,
        "contract_pass": True,
    }
    assert payload["evidence_requirements"]["source_files_acquired"] is False
    assert payload["evidence_requirements"]["selected_file_checksums_ready"] is False
    assert payload["evidence_requirements"]["product_license_review_ready"] is False
    assert payload["evidence_requirements"]["import_health_execution_ready"] is False
    assert payload["evidence_requirements"]["silent_data_loss_negative_gate_executed"] is False
    assert payload["readiness_inputs"]["import_health_receipt"].endswith(
        "phase3_ifc_import_health_execution_receipt.json"
    )
    assert "source_file_not_acquired" in payload["blockers"]
    assert "source_sha256_missing" in payload["blockers"]
    assert "selected_file_checksums_missing" in payload["blockers"]
    assert "product_legal_license_review_pending" in payload["blockers"]
    assert "silent_data_loss_negative_gate_not_executed" in payload["blockers"]
    assert "silent_import_loss_gate_not_executed" in payload["blockers"]
    assert "silent_import_loss_gate_not_implemented" not in payload["blockers"]
    assert "ifc_import_health_execution_count_below_required:0/10" in payload["blockers"]
    grouping = payload["blocker_grouping_metadata"]
    assert grouping["schema_version"] == "phase6-silent-import-loss-blocker-groups.v1"
    assert grouping["unassigned_blockers"] == []
    groups = grouping["groups"]
    assert groups["source_acquisition"]["display_name"] == "source/acquisition"
    assert groups["source_acquisition"]["scope"] == "direct_silent_import_loss"
    assert "source_file_not_acquired" in groups["source_acquisition"]["blockers"]
    assert "source_sha256_missing" in groups["checksum"]["blockers"]
    assert "selected_file_checksums_missing" in groups["checksum"]["blockers"]
    assert "product_legal_license_review_pending" in groups["license_legal"]["blockers"]
    assert "import_health_execution_missing" in groups["import_execution"]["blockers"]
    assert (
        "ifc_import_health_execution_count_below_required:0/10"
        in groups["import_execution"]["blockers"]
    )
    assert (
        "silent_data_loss_negative_gate_not_executed"
        in groups["silent_loss_gate"]["blockers"]
    )
    assert "silent_import_loss_gate_not_executed" in groups["silent_loss_gate"]["blockers"]
    assert groups["query_gui_spillover"]["scope"] == "spillover_not_direct_silent_import_loss"
    assert groups["query_gui_spillover"]["blockers"] == [
        "dataset_repository_url_missing",
        "gui_task_runner_not_implemented",
        "query_expected_answers_missing",
        "query_task_file_checksums_missing",
    ]
    assert "not direct silent-import-loss closure blockers" in grouping["claim_boundary"]
    assert "regenerate the Phase 3 import-health execution receipt" in payload["owner_action"]
    assert "regenerate and check this Phase 6 silent-import-loss status" in payload["owner_action"]
    assert payload["owner_action"].endswith("then refresh the RC final gate.")
    assert "expected contracts" not in payload["claim_boundary"]
    assert "does not download or bundle IFC files" in payload["claim_boundary"]


def test_phase6_silent_import_loss_status_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase6_silent_import_loss_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase6_silent_import_loss_status_missing:")


def test_phase6_silent_import_loss_status_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "silent-import-loss.json"
    module.write_phase6_silent_import_loss_status(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase6_silent_import_loss_status(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase6_silent_import_loss_status_mismatch"
