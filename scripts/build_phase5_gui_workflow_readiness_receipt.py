#!/usr/bin/env python3
"""Build a conservative Phase 5 GUI workflow readiness receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase5_gui_workflow_readiness_receipt.json"
APP_SURFACE = Path("src/App.tsx")
WORKFLOW_PANEL = Path("src/workbench/DeveloperPreviewWorkflowPanel.tsx")
WORKFLOW_MODEL = Path("src/workbench/developerPreviewWorkflow.ts")
WORKFLOW_STATE_MODEL = Path("src/workbench/developerPreviewWorkflowState.ts")
WORKFLOW_WORKER = Path("src/workbench/developerPreviewWorkflow.worker.ts")
TASK_BASED_UX_TEST = Path("tests/frontend/developer-preview-workflow.spec.ts")
TASK_BASED_UX_BROWSER_EXECUTION_RECEIPT = (
    PRODUCTIZATION / "phase5_task_based_ux_browser_execution_receipt.json"
)
TASK_BASED_UX_ENVIRONMENT_BLOCKER = "task_based_ux_browser_execution_environment_blocked"
PREVIEW_LOOPBACK_BIND_BLOCKER = "preview_server_loopback_bind_permission_blocked"
PREVIEW_LOOPBACK_BIND_REASON_CODE = "listen_eperm_127_0_0_1"
EVIDENCE_CONSOLE_SCOPE_STATUS = PRODUCTIZATION / "evidence_console_scope_status.json"
UX_OBSERVATION_REPORT = PRODUCTIZATION / "ux_new_user_observation_report.json"
UX_OBSERVATION_INTAKE = PRODUCTIZATION / "ux_new_user_observation_intake_packet.json"

WORKFLOW_STEPS = (
    {
        "id": "import",
        "label": "Import",
        "actual_gui_anchors": ("Import draft JSON", "Import review JSON"),
        "required_gui_contract_anchors": (
            "file and license/provenance review",
            "unit and coordinate-system review",
            "source-to-canonical mapping",
            "unsupported entity inventory",
        ),
        "required_capabilities": (
            "file and license/provenance review",
            "unit and coordinate-system review",
            "source-to-canonical mapping",
            "unsupported entity inventory",
        ),
    },
    {
        "id": "model_health",
        "label": "Model Health",
        "actual_gui_anchors": ("Model Health",),
        "required_gui_contract_anchors": (
            "disconnected component checks",
            "zero-length member checks",
            "duplicate node checks",
            "unstable DOF checks",
        ),
        "required_capabilities": (
            "disconnected component checks",
            "zero-length member checks",
            "duplicate node checks",
            "unstable DOF checks",
        ),
    },
    {
        "id": "analysis_setup",
        "label": "Analysis Setup",
        "actual_gui_anchors": ("Analysis Setup",),
        "required_gui_contract_anchors": (
            "analysis type selection",
            "load case and combination selection",
            "solver tolerance controls",
            "expected memory and runtime estimate",
        ),
        "required_capabilities": (
            "analysis type selection",
            "load case and combination selection",
            "solver tolerance controls",
            "expected memory and runtime estimate",
        ),
    },
    {
        "id": "run_monitor",
        "label": "Run & Monitor",
        "actual_gui_anchors": ("Run & Monitor",),
        "required_gui_contract_anchors": (
            "load-step progress",
            "residual and increment trace",
            "fallback and warning visibility",
            "explicit stop reason",
        ),
        "required_capabilities": (
            "load-step progress",
            "residual and increment trace",
            "fallback and warning visibility",
            "explicit stop reason",
        ),
    },
    {
        "id": "compare_report",
        "label": "Compare & Report",
        "actual_gui_anchors": ("Compare & Report",),
        "required_gui_contract_anchors": (
            "engine versus reference comparison",
            "story/member/mode traceability",
            "worst-error and residual reporting",
            "reproduction bundle export",
        ),
        "required_capabilities": (
            "engine versus reference comparison",
            "story/member/mode traceability",
            "worst-error and residual reporting",
            "reproduction bundle export",
        ),
    },
)

INPUTS = (
    APP_SURFACE,
    WORKFLOW_PANEL,
    WORKFLOW_MODEL,
    WORKFLOW_STATE_MODEL,
    WORKFLOW_WORKER,
    TASK_BASED_UX_TEST,
    TASK_BASED_UX_BROWSER_EXECUTION_RECEIPT,
    EVIDENCE_CONSOLE_SCOPE_STATUS,
    UX_OBSERVATION_REPORT,
    UX_OBSERVATION_INTAKE,
    Path("docs/templates/ux_new_user_observation.template.json"),
    Path("scripts/build_phase5_gui_workflow_readiness_receipt.py"),
    Path("scripts/run_phase5_task_based_ux_browser_smoke.py"),
    Path("scripts/build_ux_new_user_observation_report.py"),
    Path("scripts/build_ux_new_user_observation_intake_packet.py"),
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _read_text(repo_root: Path, path: Path) -> str:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return ""
    return resolved.read_text(encoding="utf-8", errors="replace")


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _preview_output_excerpt(browser_execution_receipt: dict[str, Any]) -> str:
    commands = browser_execution_receipt.get("commands")
    if not isinstance(commands, dict):
        return ""
    preview = commands.get("preview")
    if not isinstance(preview, dict):
        return ""
    return str(preview.get("output_excerpt", ""))


def _browser_execution_blocker_classification(
    browser_execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    reason_code = str(browser_execution_receipt.get("blocker_reason_code") or "")
    blocker = str(browser_execution_receipt.get("blocker") or "")
    if (
        blocker == PREVIEW_LOOPBACK_BIND_BLOCKER
        or reason_code == PREVIEW_LOOPBACK_BIND_REASON_CODE
    ):
        return {
            "blocker_category": "environment_loopback_bind_permission",
            "blocker_reason_code": PREVIEW_LOOPBACK_BIND_REASON_CODE,
            "environment_blocker": True,
            "blocker_evidence": {
                "syscall": "listen",
                "code": "EPERM",
                "address": "127.0.0.1",
                "port": 4173,
            },
        }
    normalized_output = _preview_output_excerpt(browser_execution_receipt).lower()
    if "listen" in normalized_output and "eperm" in normalized_output and "127.0.0.1" in normalized_output:
        return {
            "blocker_category": "environment_loopback_bind_permission",
            "blocker_reason_code": PREVIEW_LOOPBACK_BIND_REASON_CODE,
            "environment_blocker": True,
            "blocker_evidence": {
                "syscall": "listen",
                "code": "EPERM",
                "address": "127.0.0.1",
                "port": 4173,
            },
        }
    return {
        "blocker_category": str(
            browser_execution_receipt.get("blocker_category")
            or "browser_execution_failure"
        ),
        "blocker_reason_code": reason_code or "browser_execution_not_passed",
        "environment_blocker": bool(browser_execution_receipt.get("environment_blocker") is True),
        "blocker_evidence": (
            browser_execution_receipt.get("blocker_evidence")
            if isinstance(browser_execution_receipt.get("blocker_evidence"), dict)
            else {}
        ),
    }


def _workflow_step_ids(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("required_workflow_steps")
    if not isinstance(rows, list):
        summary = payload.get("summary")
        rows = summary.get("required_workflow_steps") if isinstance(summary, dict) else []
    ids: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("id"):
            ids.add(str(row["id"]))
    return ids


def _task_based_ux_test_contract(
    test_text: str,
    browser_execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    required_step_ids = {str(step["id"]) for step in WORKFLOW_STEPS}
    covered_step_ids = {
        str(step["id"])
        for step in WORKFLOW_STEPS
        if f'data-phase5-workflow-step="${step["id"]}"' in test_text
        or f"data-phase5-workflow-step=\"{step['id']}\"" in test_text
        or str(step["id"]) in test_text
    }
    required_labels = {str(step["label"]) for step in WORKFLOW_STEPS}
    covered_labels = {label for label in required_labels if label in test_text}
    blocks_promotion = bool(
        "without readiness promotion" in test_text
        and "Execution pass" in test_text
        and "0/5" in test_text
        and "UX observation" in test_text
        and "blocked" in test_text
    )
    shell_selector_present = 'data-phase5-gui-workflow-shell="true"' in test_text
    contract_pass = bool(
        test_text
        and required_step_ids.issubset(covered_step_ids)
        and required_labels.issubset(covered_labels)
        and shell_selector_present
        and blocks_promotion
    )
    browser_execution_receipt_attached = bool(browser_execution_receipt)
    browser_execution_passed = bool(browser_execution_receipt.get("contract_pass") is True)
    blocker_classification = _browser_execution_blocker_classification(browser_execution_receipt)
    environment_execution_blocker = (
        f"{TASK_BASED_UX_ENVIRONMENT_BLOCKER}:"
        f"{blocker_classification['blocker_reason_code']}"
        if browser_execution_receipt_attached
        and not browser_execution_passed
        and blocker_classification["environment_blocker"] is True
        else None
    )
    execution_blocker = (
        "task_based_ux_browser_execution_not_passed"
        if browser_execution_receipt_attached
        else "task_based_ux_browser_execution_receipt_missing"
    )
    return {
        "path": TASK_BASED_UX_TEST.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "required_step_ids": sorted(required_step_ids),
        "covered_step_ids": sorted(covered_step_ids),
        "missing_step_ids": sorted(required_step_ids.difference(covered_step_ids)),
        "covered_labels": sorted(covered_labels),
        "shell_selector_present": shell_selector_present,
        "blocks_readiness_promotion": blocks_promotion,
        "browser_execution_receipt": TASK_BASED_UX_BROWSER_EXECUTION_RECEIPT.as_posix(),
        "browser_execution_receipt_attached": browser_execution_receipt_attached,
        "browser_execution_status": browser_execution_receipt.get("status", "missing"),
        "browser_execution_passed": browser_execution_passed,
        "browser_execution_blocker": browser_execution_receipt.get("blocker"),
        "browser_execution_failed_phase": browser_execution_receipt.get("failed_phase"),
        "browser_execution_blocker_category": blocker_classification["blocker_category"],
        "browser_execution_blocker_reason_code": blocker_classification["blocker_reason_code"],
        "browser_execution_environment_blocker": blocker_classification["environment_blocker"],
        "browser_execution_blocker_evidence": blocker_classification["blocker_evidence"],
        "execution_blocker": execution_blocker,
        "execution_environment_blocker": environment_execution_blocker,
        "claim_boundary": (
            "The Playwright task smoke is a runnable test artifact. It does not prove "
            "the UX final gate until a browser execution receipt passes in an environment "
            "that can launch a browser and serve/open the app."
        ),
    }


def _route_case_run_state_contract(app_text: str, state_text: str) -> dict[str, Any]:
    required_app_anchors = {
        "imports_builder": "buildDeveloperPreviewWorkflowState",
        "renders_route_state": "data-phase5-route-state",
        "renders_route_id": "data-phase5-route-id",
        "renders_case_id": "data-phase5-case-id",
        "renders_run_id": "data-phase5-run-id",
        "renders_route_status": "data-phase5-route-status",
    }
    required_model_anchors = {
        "route_id": "routeId",
        "case_id": "caseId",
        "run_id": "runId",
        "route_case_run_boundary": "route/case/run-centered workflow state",
        "execution_boundary": "does not prove execution",
    }
    app_anchor_pass = {
        key: anchor in app_text for key, anchor in required_app_anchors.items()
    }
    model_anchor_pass = {
        key: anchor in state_text for key, anchor in required_model_anchors.items()
    }
    contract_pass = bool(
        state_text and all(app_anchor_pass.values()) and all(model_anchor_pass.values())
    )
    return {
        "path": WORKFLOW_STATE_MODEL.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "route_id": "developer-preview-local-workflow",
        "case_id": "open-benchmark-seed-corpus",
        "run_id": "execution-receipt-pending",
        "app_anchor_pass": app_anchor_pass,
        "model_anchor_pass": model_anchor_pass,
        "claim_boundary": (
            "The route/case/run model replaces ad hoc workflow display state for the "
            "Phase 5 shell only. It does not replace all ResourceMap loading and does "
            "not prove execution or UX readiness."
        ),
    }


def _status_vocabulary_contract(app_text: str, workflow_text: str, state_text: str) -> dict[str, Any]:
    allowed_statuses = ["ready", "blocked", "missing", "error"]
    required_app_anchors = {
        "renders_vocabulary": "data-phase5-status-vocabulary",
        "renders_status_tokens": "data-phase5-status-token",
    }
    required_model_anchors = {
        "exports_vocabulary": "DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY",
        "exports_normalizer": "normalizeDeveloperPreviewWorkflowStatus",
    }
    required_state_anchors = {
        "uses_normalizer": "normalizeDeveloperPreviewWorkflowStatus",
        "status_type": "DeveloperPreviewWorkflowStatus",
    }
    app_anchor_pass = {
        key: anchor in app_text for key, anchor in required_app_anchors.items()
    }
    model_anchor_pass = {
        key: anchor in workflow_text for key, anchor in required_model_anchors.items()
    }
    state_anchor_pass = {
        key: anchor in state_text for key, anchor in required_state_anchors.items()
    }
    status_presence = {
        status: status in app_text and status in workflow_text for status in allowed_statuses
    }
    contract_pass = bool(
        all(app_anchor_pass.values())
        and all(model_anchor_pass.values())
        and all(state_anchor_pass.values())
        and all(status_presence.values())
    )
    return {
        "path": WORKFLOW_MODEL.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "allowed_statuses": allowed_statuses,
        "status_presence": status_presence,
        "app_anchor_pass": app_anchor_pass,
        "model_anchor_pass": model_anchor_pass,
        "state_anchor_pass": state_anchor_pass,
        "claim_boundary": (
            "This contract proves that the Phase 5 workflow UI has a constrained "
            "ready/blocked/missing/error vocabulary and normalizer. It does not prove "
            "workflow execution, browser UX success, or Developer Preview RC readiness."
        ),
    }


def _value_kind_contract(app_text: str, workflow_text: str) -> dict[str, Any]:
    allowed_value_kinds = ["exact_value", "derived_proxy", "reference_value"]
    required_app_anchors = {
        "renders_legend": "data-phase5-value-kind-legend",
        "renders_value_kind": "data-phase5-value-kind",
        "renders_value_kind_tokens": "data-phase5-value-kind-token",
    }
    required_model_anchors = {
        "exports_value_kinds": "DEVELOPER_PREVIEW_WORKFLOW_VALUE_KINDS",
        "types_evidence_signal": "DeveloperPreviewWorkflowEvidenceSignal",
        "has_value_kind_field": "valueKind",
    }
    app_anchor_pass = {
        key: anchor in app_text for key, anchor in required_app_anchors.items()
    }
    model_anchor_pass = {
        key: anchor in workflow_text for key, anchor in required_model_anchors.items()
    }
    value_kind_presence = {
        value_kind: value_kind in app_text and value_kind in workflow_text
        for value_kind in allowed_value_kinds
    }
    contract_pass = bool(
        all(app_anchor_pass.values())
        and all(model_anchor_pass.values())
        and all(value_kind_presence.values())
    )
    return {
        "path": WORKFLOW_MODEL.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "allowed_value_kinds": allowed_value_kinds,
        "value_kind_presence": value_kind_presence,
        "app_anchor_pass": app_anchor_pass,
        "model_anchor_pass": model_anchor_pass,
        "claim_boundary": (
            "This contract proves that Phase 5 workflow evidence signals visibly "
            "distinguish exact values, derived proxies, and reference values. It does "
            "not prove that the underlying workflow was executed or that reference "
            "values are authoritative for every case."
        ),
    }


def _feature_module_contract(app_text: str, panel_text: str) -> dict[str, Any]:
    required_app_anchors = {
        "imports_panel": "DeveloperPreviewWorkflowPanel",
        "passes_route_state": "routeState={phase5RouteState}",
        "passes_steps": "steps={developerPreviewWorkflowSteps}",
    }
    required_panel_anchors = {
        "exports_panel": "export function DeveloperPreviewWorkflowPanel",
        "declares_props": "DeveloperPreviewWorkflowPanelProps",
        "renders_feature_module_anchor": "data-phase5-feature-module",
        "renders_workflow_shell": "data-phase5-gui-workflow-shell",
        "renders_workflow_steps": "data-phase5-workflow-step",
    }
    app_anchor_pass = {
        key: anchor in app_text for key, anchor in required_app_anchors.items()
    }
    panel_anchor_pass = {
        key: anchor in panel_text for key, anchor in required_panel_anchors.items()
    }
    contract_pass = bool(
        panel_text and all(app_anchor_pass.values()) and all(panel_anchor_pass.values())
    )
    return {
        "path": WORKFLOW_PANEL.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "app_anchor_pass": app_anchor_pass,
        "panel_anchor_pass": panel_anchor_pass,
        "claim_boundary": (
            "This contract proves that the Phase 5 workflow panel is separated into a "
            "feature module and wired from App.tsx. It does not prove task execution, "
            "UX success, or Developer Preview RC readiness."
        ),
    }


def _collapsible_provenance_contract(panel_text: str) -> dict[str, Any]:
    required_panel_anchors = {
        "uses_details": "<details",
        "uses_summary": "<summary",
        "renders_disclosure": "data-phase5-provenance-disclosure",
        "renders_summary_anchor": "data-phase5-provenance-summary",
        "renders_details_anchor": "data-phase5-provenance-details",
        "includes_advanced_provenance": "Advanced provenance",
        "includes_claim_boundary": "Claim boundary",
    }
    panel_anchor_pass = {
        key: anchor in panel_text for key, anchor in required_panel_anchors.items()
    }
    contract_pass = bool(panel_text and all(panel_anchor_pass.values()))
    return {
        "path": WORKFLOW_PANEL.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "panel_anchor_pass": panel_anchor_pass,
        "claim_boundary": (
            "This contract proves that advanced Phase 5 workflow provenance is available "
            "behind a collapsed disclosure. It does not prove source correctness, browser "
            "execution, UX success, or Developer Preview RC readiness."
        ),
    }


def _unified_selection_state_contract(panel_text: str, workflow_text: str) -> dict[str, Any]:
    selection_channels = ["3d", "table", "chart", "comparison_row"]
    required_panel_anchors = {
        "renders_selection_state": "data-phase5-selection-state",
        "renders_channel_vocabulary": "data-phase5-selection-channel-vocabulary",
        "renders_selection_channel": "data-phase5-selection-channel",
        "states_single_selection": "single selection state",
    }
    required_model_anchors = {
        "exports_channels": "DEVELOPER_PREVIEW_WORKFLOW_SELECTION_CHANNELS",
        "types_channel": "DeveloperPreviewWorkflowSelectionChannel",
    }
    panel_anchor_pass = {
        key: anchor in panel_text for key, anchor in required_panel_anchors.items()
    }
    model_anchor_pass = {
        key: anchor in workflow_text for key, anchor in required_model_anchors.items()
    }
    channel_presence = {
        channel: channel in panel_text and channel in workflow_text
        for channel in selection_channels
    }
    contract_pass = bool(
        all(panel_anchor_pass.values())
        and all(model_anchor_pass.values())
        and all(channel_presence.values())
    )
    return {
        "path": WORKFLOW_PANEL.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "selection_channels": selection_channels,
        "channel_presence": channel_presence,
        "panel_anchor_pass": panel_anchor_pass,
        "model_anchor_pass": model_anchor_pass,
        "claim_boundary": (
            "This contract proves that the Phase 5 workflow surface exposes a single "
            "selection-state vocabulary for 3D, table, chart, and comparison-row contexts. "
            "It does not prove live 3D picking, chart interaction, browser execution, or UX success."
        ),
    }


def _web_worker_boundary_contract(
    panel_text: str,
    workflow_text: str,
    worker_text: str,
) -> dict[str, Any]:
    worker_tasks = ["ifc_parse", "result_processing"]
    required_panel_anchors = {
        "renders_worker_boundary": "data-phase5-worker-boundary",
        "renders_worker_task_vocabulary": "data-phase5-worker-task-vocabulary",
        "renders_worker_task": "data-phase5-worker-task",
        "states_off_ui_thread": "off the UI thread",
    }
    required_model_anchors = {
        "exports_worker_tasks": "DEVELOPER_PREVIEW_WORKFLOW_WORKER_TASKS",
        "exports_worker_boundary": "DEVELOPER_PREVIEW_WORKFLOW_WORKER_BOUNDARY",
        "creates_worker": "new Worker",
        "uses_worker_entry": "developerPreviewWorkflow.worker.ts",
    }
    required_worker_anchors = {
        "has_message_handler": "onmessage",
        "posts_message": "postMessage",
        "processed_on_worker": "processedOn: 'web_worker'",
        "ifc_parse_task": "ifc_parse",
        "result_processing_task": "result_processing",
        "keeps_claim_boundary": "does not prove execution",
    }
    panel_anchor_pass = {
        key: anchor in panel_text for key, anchor in required_panel_anchors.items()
    }
    model_anchor_pass = {
        key: anchor in workflow_text for key, anchor in required_model_anchors.items()
    }
    worker_anchor_pass = {
        key: anchor in worker_text for key, anchor in required_worker_anchors.items()
    }
    task_presence = {
        task: task in panel_text and task in workflow_text and task in worker_text
        for task in worker_tasks
    }
    contract_pass = bool(
        all(panel_anchor_pass.values())
        and all(model_anchor_pass.values())
        and all(worker_anchor_pass.values())
        and all(task_presence.values())
    )
    return {
        "path": WORKFLOW_WORKER.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "worker_tasks": worker_tasks,
        "task_presence": task_presence,
        "panel_anchor_pass": panel_anchor_pass,
        "model_anchor_pass": model_anchor_pass,
        "worker_anchor_pass": worker_anchor_pass,
        "claim_boundary": (
            "This contract proves that the Phase 5 workflow source exposes a Web Worker "
            "boundary for large IFC parsing and result processing. It does not prove "
            "large-model execution, browser worker execution, task-based UX success, "
            "or Developer Preview RC readiness."
        ),
    }


def _evidence_console_absorption_contract(
    panel_text: str,
    workflow_text: str,
    evidence_console_scope: dict[str, Any],
) -> dict[str, Any]:
    expected_features = [
        "case_list",
        "source_provenance_inspector",
        "reference_vs_engine_comparison",
        "residual_audit",
        "worst_member_story",
        "reviewer_decision",
        "reproduce_bundle_export",
    ]
    required_panel_anchors = {
        "renders_absorption": "data-phase5-evidence-console-absorption",
        "renders_source": "data-phase5-evidence-console-source",
        "renders_feature_vocabulary": "data-phase5-evidence-console-feature-vocabulary",
        "renders_feature": "data-phase5-evidence-console-feature",
        "states_compare_report": "Compare & Report",
        "states_evidence_console": "Evidence Console",
    }
    required_model_anchors = {
        "exports_absorption": "DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION",
        "targets_compare_report": "compare_report",
        "references_source_receipt": EVIDENCE_CONSOLE_SCOPE_STATUS.as_posix(),
        "keeps_claim_boundary": "does not prove launch readiness",
    }
    panel_anchor_pass = {
        key: anchor in panel_text for key, anchor in required_panel_anchors.items()
    }
    model_anchor_pass = {
        key: anchor in workflow_text for key, anchor in required_model_anchors.items()
    }
    feature_rows = evidence_console_scope.get("feature_rows")
    feature_rows = feature_rows if isinstance(feature_rows, list) else []
    passed_features = sorted(
        str(row.get("check"))
        for row in feature_rows
        if isinstance(row, dict) and row.get("pass") is True and row.get("check")
    )
    feature_presence = {
        feature: (
            feature in workflow_text
            and feature in passed_features
        )
        for feature in expected_features
    }
    summary = evidence_console_scope.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    scope_contract_pass = bool(evidence_console_scope.get("scope_contract_pass") is True)
    launch_ready = bool(evidence_console_scope.get("launch_ready") is True)
    contract_pass = bool(
        all(panel_anchor_pass.values())
        and all(model_anchor_pass.values())
        and all(feature_presence.values())
        and scope_contract_pass
        and not launch_ready
    )
    return {
        "path": EVIDENCE_CONSOLE_SCOPE_STATUS.as_posix(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "workflow_step_id": "compare_report",
        "scope_contract_pass": scope_contract_pass,
        "launch_ready": launch_ready,
        "evidence_console_feature_count": int(
            summary.get("evidence_console_feature_count", 0) or 0
        ),
        "evidence_console_feature_pass_count": int(
            summary.get("evidence_console_feature_pass_count", 0) or 0
        ),
        "expected_features": expected_features,
        "passed_features": passed_features,
        "feature_presence": feature_presence,
        "panel_anchor_pass": panel_anchor_pass,
        "model_anchor_pass": model_anchor_pass,
        "external_blocker": "customer_shadow_completed_project_cases_ready"
        if not launch_ready
        else None,
        "claim_boundary": (
            "This contract proves that the Phase 5 Compare & Report source surface "
            "carries forward the current Evidence Console scope and references its "
            "scope-status receipt. It does not prove Evidence Console launch readiness, "
            "customer-shadow completion, browser task execution, human UX success, "
            "or Phase 5 closure."
        ),
    }


def _workflow_shell_step_rows(app_text: str, workflow_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    app_imports_model = "developerPreviewWorkflowSteps" in app_text
    app_renders_step_attribute = "data-phase5-workflow-step" in app_text
    app_renders_shell_attribute = "data-phase5-gui-workflow-shell" in app_text
    app_shell_wired = bool(app_imports_model and app_renders_step_attribute and app_renders_shell_attribute)
    for step in WORKFLOW_STEPS:
        anchors = (
            str(step["id"]),
            str(step["label"]),
            f"Phase5 workflow step: {step['label']}",
        )
        contract_anchors = tuple(str(anchor) for anchor in step["required_gui_contract_anchors"])
        present_anchors = [anchor for anchor in anchors if anchor in workflow_text]
        present_contract_anchors = [anchor for anchor in contract_anchors if anchor in workflow_text]
        label_present = str(step["label"]) in workflow_text
        contract_pass = bool(
            app_shell_wired
            and label_present
            and len(present_anchors) == len(anchors)
            and len(present_contract_anchors) == len(contract_anchors)
        )
        rows.append(
            {
                "id": step["id"],
                "label": step["label"],
                "status": "ready" if contract_pass else "missing",
                "contract_pass": contract_pass,
                "app_shell_wired": app_shell_wired,
                "label_present": label_present,
                "workflow_model_anchors": list(anchors),
                "present_workflow_model_anchors": present_anchors,
                "required_gui_contract_anchors": list(contract_anchors),
                "present_required_gui_contract_anchors": present_contract_anchors,
                "required_capabilities": list(step["required_capabilities"]),
                "claim_boundary": (
                    "The visible GUI shell proves only that the five-step workflow is "
                    "presented in the app source. It does not prove task execution, "
                    "human UX pass, or solver/benchmark correctness."
                ),
            }
        )
    return rows


def build_phase5_gui_workflow_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    app_text = _read_text(repo_root, APP_SURFACE)
    workflow_panel_text = _read_text(repo_root, WORKFLOW_PANEL)
    workflow_surface_text = f"{app_text}\n{workflow_panel_text}"
    workflow_text = _read_text(repo_root, WORKFLOW_MODEL)
    workflow_state_text = _read_text(repo_root, WORKFLOW_STATE_MODEL)
    workflow_worker_text = _read_text(repo_root, WORKFLOW_WORKER)
    task_test_text = _read_text(repo_root, TASK_BASED_UX_TEST)
    browser_execution_receipt = _load_json(
        repo_root,
        TASK_BASED_UX_BROWSER_EXECUTION_RECEIPT,
    )
    evidence_console_scope = _load_json(repo_root, EVIDENCE_CONSOLE_SCOPE_STATUS)
    observation = _load_json(repo_root, UX_OBSERVATION_REPORT)
    intake = _load_json(repo_root, UX_OBSERVATION_INTAKE)
    shell_rows = _workflow_shell_step_rows(workflow_surface_text, workflow_text)
    route_case_run_state = _route_case_run_state_contract(workflow_surface_text, workflow_state_text)
    status_vocabulary = _status_vocabulary_contract(
        workflow_surface_text,
        workflow_text,
        workflow_state_text,
    )
    value_kind_contract = _value_kind_contract(workflow_surface_text, workflow_text)
    feature_module = _feature_module_contract(app_text, workflow_panel_text)
    collapsible_provenance = _collapsible_provenance_contract(workflow_panel_text)
    unified_selection_state = _unified_selection_state_contract(
        workflow_panel_text,
        workflow_text,
    )
    web_worker_boundary = _web_worker_boundary_contract(
        workflow_panel_text,
        workflow_text,
        workflow_worker_text,
    )
    evidence_console_absorption = _evidence_console_absorption_contract(
        workflow_panel_text,
        workflow_text,
        evidence_console_scope,
    )
    task_based_ux_test = _task_based_ux_test_contract(task_test_text, browser_execution_receipt)
    required_step_ids = {str(step["id"]) for step in WORKFLOW_STEPS}
    observation_step_ids = _workflow_step_ids(observation)
    intake_step_ids = _workflow_step_ids(intake)
    shell_pass_ids = {str(row["id"]) for row in shell_rows if row["contract_pass"] is True}
    missing_shell_ids = sorted(required_step_ids.difference(shell_pass_ids))
    execution_pass_ids: set[str] = set()
    missing_execution_ids = sorted(required_step_ids.difference(execution_pass_ids))
    blockers = [
        *[f"gui_workflow_shell_step_not_proven:{step_id}" for step_id in missing_shell_ids],
        *[f"workflow_execution_step_not_proven:{step_id}" for step_id in missing_execution_ids],
    ]
    if observation.get("contract_pass") is not True:
        blockers.append("human_new_user_observation_not_passed")
    if task_based_ux_test["contract_pass"] is not True:
        blockers.append("task_based_ux_test_contract_not_ready")
    if route_case_run_state["contract_pass"] is not True:
        blockers.append("route_case_run_state_model_not_ready")
    if status_vocabulary["contract_pass"] is not True:
        blockers.append("status_vocabulary_contract_not_ready")
    if value_kind_contract["contract_pass"] is not True:
        blockers.append("value_kind_contract_not_ready")
    if feature_module["contract_pass"] is not True:
        blockers.append("workflow_feature_module_contract_not_ready")
    if collapsible_provenance["contract_pass"] is not True:
        blockers.append("collapsible_provenance_contract_not_ready")
    if unified_selection_state["contract_pass"] is not True:
        blockers.append("unified_selection_state_contract_not_ready")
    if web_worker_boundary["contract_pass"] is not True:
        blockers.append("web_worker_boundary_contract_not_ready")
    if evidence_console_absorption["contract_pass"] is not True:
        blockers.append("evidence_console_absorption_contract_not_ready")
    if task_based_ux_test["browser_execution_passed"] is not True:
        blockers.append(str(task_based_ux_test["execution_blocker"]))
        if task_based_ux_test["execution_environment_blocker"]:
            blockers.append(str(task_based_ux_test["execution_environment_blocker"]))
    if required_step_ids.difference(observation_step_ids):
        blockers.append("observation_required_workflow_steps_not_visible")
    if required_step_ids.difference(intake_step_ids):
        blockers.append("intake_required_workflow_steps_not_visible")
    contract_pass = bool(
        not blockers
        and len(shell_pass_ids) == len(required_step_ids)
        and len(execution_pass_ids) == len(required_step_ids)
        and observation.get("contract_pass") is True
    )
    return {
        "schema_version": "phase5-gui-workflow-readiness-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(INPUTS, repo_root=repo_root),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "phase5_closure_claim": contract_pass,
        "developer_preview_release_candidate_claim": contract_pass,
        "human_ux_observation_claim": bool(observation.get("contract_pass") is True),
        "app_surface": APP_SURFACE.as_posix(),
        "workflow_panel": WORKFLOW_PANEL.as_posix(),
        "workflow_model": WORKFLOW_MODEL.as_posix(),
        "workflow_worker": WORKFLOW_WORKER.as_posix(),
        "route_case_run_state_model": route_case_run_state,
        "status_vocabulary_contract": status_vocabulary,
        "value_kind_contract": value_kind_contract,
        "workflow_feature_module_contract": feature_module,
        "collapsible_provenance_contract": collapsible_provenance,
        "unified_selection_state_contract": unified_selection_state,
        "web_worker_boundary_contract": web_worker_boundary,
        "evidence_console_absorption_contract": evidence_console_absorption,
        "required_workflow_step_count": len(WORKFLOW_STEPS),
        "workflow_shell_step_pass_count": len(shell_pass_ids),
        "workflow_shell_steps": shell_rows,
        "missing_workflow_shell_steps": missing_shell_ids,
        "actual_gui_workflow_step_pass_count": len(shell_pass_ids),
        "actual_gui_workflow_step_partial_count": 0,
        "actual_gui_workflow_steps": shell_rows,
        "missing_actual_gui_workflow_steps": missing_shell_ids,
        "partial_actual_gui_workflow_steps": [],
        "execution_workflow_step_pass_count": len(execution_pass_ids),
        "missing_execution_workflow_steps": missing_execution_ids,
        "execution_receipt_count": 0,
        "task_based_ux_test": task_based_ux_test,
        "task_based_ux_browser_execution_receipt": browser_execution_receipt,
        "handoff_surface": {
            "observation_report": UX_OBSERVATION_REPORT.as_posix(),
            "observation_contract_pass": bool(observation.get("contract_pass") is True),
            "observation_required_workflow_step_count": len(observation_step_ids),
            "observation_missing_required_workflow_steps": sorted(
                required_step_ids.difference(observation_step_ids)
            ),
            "intake_packet": UX_OBSERVATION_INTAKE.as_posix(),
            "intake_required_workflow_step_count": len(intake_step_ids),
            "intake_missing_required_workflow_steps": sorted(
                required_step_ids.difference(intake_step_ids)
            ),
        },
        "required_workflow_steps": [
            {"id": str(step["id"]), "label": str(step["label"])}
            for step in WORKFLOW_STEPS
        ],
        "blockers": sorted(dict.fromkeys(blockers)),
        "owner_action": (
            "Attach execution receipts for the five-step GUI workflow and a passing "
            "human new-user observation record for that exact workflow before promoting "
            "Phase 5 or Developer Preview RC readiness."
        ),
        "summary_line": (
            "Phase 5 GUI workflow readiness: BLOCKED | shell="
            f"{len(shell_pass_ids)}/{len(WORKFLOW_STEPS)} | execution="
            f"{len(execution_pass_ids)}/{len(WORKFLOW_STEPS)} | observation_pass="
            f"{observation.get('contract_pass') is True} | task_test="
            f"{task_based_ux_test['status']} | route_state={route_case_run_state['status']} | "
            f"status_vocabulary={status_vocabulary['status']} | "
            f"value_kind={value_kind_contract['status']} | feature_module={feature_module['status']} | "
            f"provenance={collapsible_provenance['status']} | "
            f"selection_state={unified_selection_state['status']} | "
            f"web_worker={web_worker_boundary['status']} | "
            f"evidence_console_absorption={evidence_console_absorption['status']} | "
            f"browser_execution={task_based_ux_test['browser_execution_status']}"
        ),
        "claim_boundary": (
            "This receipt separates visible GUI workflow shell coverage from execution "
            "receipts, task-based browser smoke tests, UX observation templates, and "
            "owner handoff packets. A rendered five-step shell or a test artifact does "
            "not prove task execution, human new-user success, Phase 5 closure, or "
            "Developer Preview RC readiness."
        ),
    }


def write_phase5_gui_workflow_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase5_gui_workflow_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase5_gui_workflow_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase5_gui_workflow_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase5_gui_workflow_readiness_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase5_gui_workflow_readiness_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase5_gui_workflow_readiness_mismatch"
    return True, "phase5_gui_workflow_readiness_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase5_gui_workflow_readiness_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 5 GUI workflow readiness check: {message}")
        return 0 if ok else 1
    payload = write_phase5_gui_workflow_readiness_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
