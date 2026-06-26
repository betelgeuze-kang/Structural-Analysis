from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase5_gui_workflow_readiness_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase5_gui_workflow_readiness_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase5_gui_workflow_readiness_blocks_without_execution_or_human_observation() -> None:
    payload = module.build_phase5_gui_workflow_readiness_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase5-gui-workflow-readiness-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase5_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["human_ux_observation_claim"] is False
    assert payload["workflow_panel"] == "src/workbench/DeveloperPreviewWorkflowPanel.tsx"
    assert payload["workflow_worker"] == "src/workbench/developerPreviewWorkflow.worker.ts"
    assert payload["required_workflow_step_count"] == 5
    assert payload["workflow_shell_step_pass_count"] == 5
    assert payload["actual_gui_workflow_step_pass_count"] == 5
    assert payload["actual_gui_workflow_step_partial_count"] == 0
    assert payload["execution_workflow_step_pass_count"] == 0
    assert payload["execution_receipt_count"] == 0
    assert payload["task_based_ux_test"]["status"] == "ready"
    assert payload["task_based_ux_test"]["contract_pass"] is True
    assert payload["task_based_ux_test"]["path"] == "tests/frontend/developer-preview-workflow.spec.ts"
    assert payload["task_based_ux_test"]["browser_execution_receipt"] == (
        "implementation/phase1/release_evidence/productization/"
        "phase5_task_based_ux_browser_execution_receipt.json"
    )
    assert payload["task_based_ux_test"]["browser_execution_receipt_attached"] is True
    assert payload["task_based_ux_test"]["browser_execution_status"] == "blocked"
    assert payload["task_based_ux_test"]["browser_execution_passed"] is False
    assert payload["task_based_ux_test"]["browser_execution_blocker"] == (
        "preview_server_loopback_bind_permission_blocked"
    )
    assert payload["task_based_ux_test"]["browser_execution_failed_phase"] == "preview_server_start"
    assert payload["task_based_ux_test"]["browser_execution_environment_blocker"] is True
    assert payload["task_based_ux_test"]["browser_execution_blocker_reason_code"] == (
        "listen_eperm_127_0_0_1"
    )
    assert payload["task_based_ux_test"]["execution_environment_blocker"] == (
        "task_based_ux_browser_execution_environment_blocked:listen_eperm_127_0_0_1"
    )
    assert payload["task_based_ux_test"]["missing_step_ids"] == []
    assert payload["task_based_ux_test"]["blocks_readiness_promotion"] is True
    assert payload["task_based_ux_browser_execution_receipt"]["status"] == "blocked"
    assert payload["task_based_ux_browser_execution_receipt"]["contract_pass"] is False
    assert payload["task_based_ux_browser_execution_receipt"]["failed_phase"] == "preview_server_start"
    assert payload["task_based_ux_browser_execution_receipt"]["blocker"] == (
        "preview_server_loopback_bind_permission_blocked"
    )
    assert payload["task_based_ux_browser_execution_receipt"]["browser_execution_passed"] is False
    assert payload["task_based_ux_browser_execution_receipt"]["executed_workflow_steps"] == []
    assert payload["task_based_ux_browser_execution_receipt"]["blocked_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert payload["route_case_run_state_model"]["status"] == "ready"
    assert payload["route_case_run_state_model"]["contract_pass"] is True
    assert payload["route_case_run_state_model"]["route_id"] == "developer-preview-local-workflow"
    assert payload["route_case_run_state_model"]["case_id"] == "open-benchmark-seed-corpus"
    assert payload["route_case_run_state_model"]["run_id"] == "execution-receipt-pending"
    assert payload["route_case_run_state_model"]["app_anchor_pass"] == {
        "imports_builder": True,
        "renders_case_id": True,
        "renders_route_id": True,
        "renders_route_state": True,
        "renders_route_status": True,
        "renders_run_id": True,
    }
    assert payload["status_vocabulary_contract"]["status"] == "ready"
    assert payload["status_vocabulary_contract"]["contract_pass"] is True
    assert payload["status_vocabulary_contract"]["allowed_statuses"] == [
        "ready",
        "blocked",
        "missing",
        "error",
    ]
    assert payload["status_vocabulary_contract"]["status_presence"] == {
        "ready": True,
        "blocked": True,
        "missing": True,
        "error": True,
    }
    assert all(payload["status_vocabulary_contract"]["app_anchor_pass"].values())
    assert all(payload["status_vocabulary_contract"]["model_anchor_pass"].values())
    assert all(payload["status_vocabulary_contract"]["state_anchor_pass"].values())
    assert payload["value_kind_contract"]["status"] == "ready"
    assert payload["value_kind_contract"]["contract_pass"] is True
    assert payload["value_kind_contract"]["allowed_value_kinds"] == [
        "exact_value",
        "derived_proxy",
        "reference_value",
    ]
    assert payload["value_kind_contract"]["value_kind_presence"] == {
        "exact_value": True,
        "derived_proxy": True,
        "reference_value": True,
    }
    assert all(payload["value_kind_contract"]["app_anchor_pass"].values())
    assert all(payload["value_kind_contract"]["model_anchor_pass"].values())
    assert payload["workflow_feature_module_contract"]["status"] == "ready"
    assert payload["workflow_feature_module_contract"]["contract_pass"] is True
    assert all(payload["workflow_feature_module_contract"]["app_anchor_pass"].values())
    assert all(payload["workflow_feature_module_contract"]["panel_anchor_pass"].values())
    assert payload["collapsible_provenance_contract"]["status"] == "ready"
    assert payload["collapsible_provenance_contract"]["contract_pass"] is True
    assert all(payload["collapsible_provenance_contract"]["panel_anchor_pass"].values())
    assert payload["unified_selection_state_contract"]["status"] == "ready"
    assert payload["unified_selection_state_contract"]["contract_pass"] is True
    assert payload["unified_selection_state_contract"]["selection_channels"] == [
        "3d",
        "table",
        "chart",
        "comparison_row",
    ]
    assert payload["unified_selection_state_contract"]["channel_presence"] == {
        "3d": True,
        "table": True,
        "chart": True,
        "comparison_row": True,
    }
    assert all(payload["unified_selection_state_contract"]["panel_anchor_pass"].values())
    assert all(payload["unified_selection_state_contract"]["model_anchor_pass"].values())
    assert payload["web_worker_boundary_contract"]["status"] == "ready"
    assert payload["web_worker_boundary_contract"]["contract_pass"] is True
    assert payload["web_worker_boundary_contract"]["worker_tasks"] == [
        "ifc_parse",
        "result_processing",
    ]
    assert payload["web_worker_boundary_contract"]["task_presence"] == {
        "ifc_parse": True,
        "result_processing": True,
    }
    assert all(payload["web_worker_boundary_contract"]["panel_anchor_pass"].values())
    assert all(payload["web_worker_boundary_contract"]["model_anchor_pass"].values())
    assert all(payload["web_worker_boundary_contract"]["worker_anchor_pass"].values())
    assert payload["evidence_console_absorption_contract"]["status"] == "ready"
    assert payload["evidence_console_absorption_contract"]["contract_pass"] is True
    assert payload["evidence_console_absorption_contract"]["workflow_step_id"] == "compare_report"
    assert payload["evidence_console_absorption_contract"]["scope_contract_pass"] is True
    assert payload["evidence_console_absorption_contract"]["launch_ready"] is False
    assert payload["evidence_console_absorption_contract"]["external_blocker"] == (
        "customer_shadow_completed_project_cases_ready"
    )
    assert payload["evidence_console_absorption_contract"]["evidence_console_feature_count"] == 7
    assert payload["evidence_console_absorption_contract"]["evidence_console_feature_pass_count"] == 7
    assert payload["evidence_console_absorption_contract"]["expected_features"] == [
        "case_list",
        "source_provenance_inspector",
        "reference_vs_engine_comparison",
        "residual_audit",
        "worst_member_story",
        "reviewer_decision",
        "reproduce_bundle_export",
    ]
    assert payload["evidence_console_absorption_contract"]["feature_presence"] == {
        "case_list": True,
        "source_provenance_inspector": True,
        "reference_vs_engine_comparison": True,
        "residual_audit": True,
        "worst_member_story": True,
        "reviewer_decision": True,
        "reproduce_bundle_export": True,
    }
    assert all(payload["evidence_console_absorption_contract"]["panel_anchor_pass"].values())
    assert all(payload["evidence_console_absorption_contract"]["model_anchor_pass"].values())
    assert payload["partial_actual_gui_workflow_steps"] == []
    assert payload["missing_actual_gui_workflow_steps"] == []
    assert payload["missing_execution_workflow_steps"] == [
        "analysis_setup",
        "compare_report",
        "import",
        "model_health",
        "run_monitor",
    ]
    assert payload["required_workflow_steps"] == [
        {"id": "import", "label": "Import"},
        {"id": "model_health", "label": "Model Health"},
        {"id": "analysis_setup", "label": "Analysis Setup"},
        {"id": "run_monitor", "label": "Run & Monitor"},
        {"id": "compare_report", "label": "Compare & Report"},
    ]
    rows = {row["id"]: row for row in payload["actual_gui_workflow_steps"]}
    assert rows["import"]["status"] == "ready"
    assert rows["import"]["app_shell_wired"] is True
    assert rows["import"]["present_workflow_model_anchors"] == [
        "import",
        "Import",
        "Phase5 workflow step: Import",
    ]
    assert rows["model_health"]["status"] == "ready"
    assert "workflow_execution_step_not_proven:import" in payload["blockers"]
    assert "workflow_execution_step_not_proven:model_health" in payload["blockers"]
    assert "task_based_ux_browser_execution_receipt_missing" not in payload["blockers"]
    assert "task_based_ux_browser_execution_not_passed" in payload["blockers"]
    assert (
        "task_based_ux_browser_execution_environment_blocked:listen_eperm_127_0_0_1"
        in payload["blockers"]
    )
    assert "status_vocabulary_contract_not_ready" not in payload["blockers"]
    assert "value_kind_contract_not_ready" not in payload["blockers"]
    assert "workflow_feature_module_contract_not_ready" not in payload["blockers"]
    assert "collapsible_provenance_contract_not_ready" not in payload["blockers"]
    assert "unified_selection_state_contract_not_ready" not in payload["blockers"]
    assert "web_worker_boundary_contract_not_ready" not in payload["blockers"]
    assert "evidence_console_absorption_contract_not_ready" not in payload["blockers"]
    assert "human_new_user_observation_not_passed" in payload["blockers"]
    assert payload["handoff_surface"]["observation_required_workflow_step_count"] == 5
    assert payload["handoff_surface"]["intake_required_workflow_step_count"] == 5
    assert payload["handoff_surface"]["observation_contract_pass"] is False
    assert "task-based browser smoke tests" in payload["claim_boundary"]


def test_phase5_gui_workflow_readiness_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase5_gui_workflow_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase5_gui_workflow_readiness_missing:")


def test_phase5_gui_workflow_readiness_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "phase5-gui-workflow.json"
    module.write_phase5_gui_workflow_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase5_gui_workflow_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase5_gui_workflow_readiness_mismatch"
