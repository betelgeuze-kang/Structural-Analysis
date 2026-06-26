from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_ifc_query_gui_readiness_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_ifc_query_gui_readiness_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_ifc_query_gui_readiness_blocks_without_task_evidence() -> None:
    payload = module.build_phase3_ifc_query_gui_readiness_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-ifc-query-gui-readiness-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["fem_numerical_accuracy_claim"] is False
    assert payload["query_gui_task_claim"] is False
    assert payload["required_task_source_count"] == 1
    assert payload["current_task_source_count"] == 0
    assert payload["task_manifest_count"] == 0
    assert payload["expected_answer_count"] == 0
    assert payload["gui_task_execution_count"] == 0
    assert payload["workflow_step_count"] == 5
    assert payload["workflow_step_pass_count"] == 0
    assert payload["required_evidence_pass_count"] == 0
    assert payload["required_evidence_count"] == len(payload["required_evidence"])
    assert payload["missing_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert "dataset_repository_url_missing" in payload["blockers"]
    assert "query_task_manifest_missing" in payload["blockers"]
    assert "query_expected_answers_missing" in payload["blockers"]
    assert "gui_task_runner_not_implemented" in payload["blockers"]
    assert "gui_workflow_coverage_missing" in payload["blockers"]
    assert "ifc_query_gui_task_execution_missing" in payload["blockers"]
    assert payload["task_execution_receipt_template"]["schema_version"] == (
        "phase3-ifc-query-gui-task-execution-receipt.v1"
    )
    assert payload["task_execution_receipt_template"]["contract_pass"] is False
    assert "not FEM numerical accuracy evidence" in payload["claim_boundary"]


def test_ifc_query_gui_readiness_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_ifc_query_gui_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_ifc_query_gui_readiness_missing:")


def test_ifc_query_gui_readiness_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "ifc-query-gui.json"
    module.write_phase3_ifc_query_gui_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_ifc_query_gui_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_ifc_query_gui_readiness_mismatch"
