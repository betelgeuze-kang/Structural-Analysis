#!/usr/bin/env python3
"""Build the Developer Preview Release Candidate status receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "developer_preview_rc_status.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

PHASE1_CORE_API = PRODUCTIZATION / "phase1_core_api_contract_summary.json"
DEVELOPER_PREVIEW_READINESS = PRODUCTIZATION / "developer_preview_readiness.json"
DATASET_LICENSE_MANIFEST = PRODUCTIZATION / "developer_preview_dataset_license_manifest.json"
GAP_LEDGER_EVIDENCE_AUDIT = PRODUCTIZATION / "gap_ledger_evidence_audit.json"
PHASE3_FACTORY_SUMMARY = PRODUCTIZATION / "phase3_benchmark_factory_seed_summary.json"
PHASE3_FACTORY_SCORECARD = PRODUCTIZATION / "phase3_benchmark_factory_seed_scorecard.json"
PHASE3_ACQUISITION_PLAN = PRODUCTIZATION / "phase3_benchmark_acquisition_plan.json"
PHASE3_REPRO_BUNDLE = PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
PHASE3_CLEAN_CHECKOUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
PHASE3_GIT_CLEAN_CLONE = PRODUCTIZATION / "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
PHASE3_RELEASE_CONTROL_CLEANUP_PLAN = PRODUCTIZATION / "phase3_release_control_cleanup_plan.json"
PHASE6_LINUX_WINDOWS_PARITY_STATUS = PRODUCTIZATION / "phase6_linux_windows_parity_status.json"
PHASE6_SILENT_IMPORT_LOSS_STATUS = PRODUCTIZATION / "phase6_silent_import_loss_status.json"
PHASE6_BENCHMARK_SCALE_STATUS = PRODUCTIZATION / "phase6_benchmark_scale_status.json"
PHASE6_UX_OBSERVATION_STATUS = PRODUCTIZATION / "phase6_ux_observation_status.json"
PHASE6_CLEAN_CHECKOUT_STATUS = PRODUCTIZATION / "phase6_clean_checkout_status.json"
PHASE3_IFC_IMPORT_HEALTH = PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
PHASE3_IFC_CLEAN_ACQUISITION = PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"
PHASE3_IFC_DIRTY_ACQUISITION = PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
PHASE3_IFC_SOURCE_LICENSE = PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
PHASE3_IFC_QUERY_GUI = PRODUCTIZATION / "phase3_ifc_query_gui_readiness_receipt.json"
PHASE3_MEDIUM_MODEL_SCORECARD = PRODUCTIZATION / "phase3_medium_model_scorecard_readiness_receipt.json"
PHASE3_LARGE_MODEL_RUNNER = PRODUCTIZATION / "phase3_large_model_runner_readiness_receipt.json"
PHASE4_IMPORT_TEMPLATE = PRODUCTIZATION / "phase4_commercial_comparison_import_template.json"
PHASE4_CROSS_SOLVER_READINESS = PRODUCTIZATION / "phase4_commercial_cross_solver_readiness_receipt.json"
PHASE5_GUI_WORKFLOW = PRODUCTIZATION / "phase5_gui_workflow_readiness_receipt.json"
EVIDENCE_CONSOLE_SCOPE = PRODUCTIZATION / "evidence_console_scope_status.json"
UX_OBSERVATION = PRODUCTIZATION / "ux_new_user_observation_report.json"
UX_OBSERVATION_INTAKE = PRODUCTIZATION / "ux_new_user_observation_intake_packet.json"

SCHEMA_VERSION = "developer-preview-rc-status.v1"
TASK_BASED_UX_ENVIRONMENT_BLOCKER = "task_based_ux_browser_execution_environment_blocked"
PREVIEW_LOOPBACK_BIND_REASON_CODE = "listen_eperm_127_0_0_1"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_text(repo_root: Path, path: Path) -> str:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return ""
    return resolved.read_text(encoding="utf-8", errors="replace")


def _contract_ready(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status", "")).lower()
    return bool(payload.get("contract_pass") is True or status in {"ready", "pass"})


def _row(
    *,
    item: str,
    status: str,
    contract_pass: bool,
    evidence: str,
    blockers: list[str] | None = None,
    notes: list[str] | None = None,
    blocker_grouping_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "item": item,
        "status": status,
        "contract_pass": bool(contract_pass),
        "evidence": evidence,
        "blockers": blockers or [],
        "notes": notes or [],
    }
    if blocker_grouping_metadata:
        row["blocker_grouping_metadata"] = blocker_grouping_metadata
    return row


def _pyproject_package_ready(repo_root: Path) -> bool:
    pyproject = _read_text(repo_root, Path("pyproject.toml"))
    setup_cfg = _read_text(repo_root, Path("setup.cfg"))
    return bool(
        '[tool.setuptools.packages.find]\nwhere = ["src"]' in pyproject
        and 'include = ["structural_analysis*"]' in pyproject
        and "packages = find:" in setup_cfg
        and "where = src" in setup_cfg
        and "structural-analysis =" in pyproject
        and "structural-analysis-benchmark =" in pyproject
    )


def _cli_entry_ready(repo_root: Path, entry_name: str, target: str) -> bool:
    pyproject = _read_text(repo_root, Path("pyproject.toml"))
    setup_cfg = _read_text(repo_root, Path("setup.cfg"))
    return bool(
        f'{entry_name} = "{target}"' in pyproject
        and f"{entry_name} = {target}" in setup_cfg
    )


def _scorecard_convergence_history_ready(score_rows: list[Any]) -> bool:
    if not score_rows:
        return False
    for row in score_rows:
        if not isinstance(row, dict):
            return False
        history = row.get("convergence_history")
        if not isinstance(history, list) or not history:
            return False
        for entry in history:
            if not isinstance(entry, dict):
                return False
            if "residual_norm" not in entry or "relative_increment" not in entry:
                return False
    return True


def _acquisition_blockers_for_lanes(acquisition_plan: dict[str, Any], lanes: set[str]) -> list[str]:
    rows = acquisition_plan.get("rows")
    rows = rows if isinstance(rows, list) else []
    blockers: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_lanes = {str(lane) for lane in row.get("lanes", [])}
        if not lanes.intersection(row_lanes):
            continue
        blockers.extend(str(blocker) for blocker in row.get("blockers", []) if str(blocker))
    return sorted(dict.fromkeys(blockers))


def _blocker_counts(blockers: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for blocker in blockers:
        key = str(blocker).split(":", 1)[0]
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _filter_blocker_grouping_metadata(
    grouping: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    if not grouping:
        return {}
    blocker_set = set(blockers)
    groups: dict[str, dict[str, Any]] = {}
    classified: set[str] = set()
    source_groups = grouping.get("groups")
    source_groups = source_groups if isinstance(source_groups, dict) else {}
    for group_name, group in source_groups.items():
        if not isinstance(group, dict):
            continue
        grouped = [
            str(blocker)
            for blocker in group.get("blockers", [])
            if str(blocker) in blocker_set
        ]
        classified.update(grouped)
        groups[str(group_name)] = {
            **group,
            "blocker_count": len(grouped),
            "blockers": grouped,
        }
    unassigned_blockers = [blocker for blocker in blockers if blocker not in classified]
    return {
        "schema_version": str(grouping.get("schema_version", "")),
        "grouping_policy": str(grouping.get("grouping_policy", "")),
        "blocker_count": len(blockers),
        "unassigned_blocker_count": len(unassigned_blockers),
        "unassigned_blockers": unassigned_blockers,
        "groups": groups,
    }


def _task_based_ux_environment_classification(
    task_based_ux_test: dict[str, Any],
    browser_execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    reason_code = str(
        task_based_ux_test.get("browser_execution_blocker_reason_code")
        or browser_execution_receipt.get("blocker_reason_code")
        or ""
    )
    environment_blocker = bool(
        task_based_ux_test.get("browser_execution_environment_blocker") is True
        or browser_execution_receipt.get("environment_blocker") is True
    )
    commands = _as_dict(browser_execution_receipt.get("commands"))
    preview = _as_dict(commands.get("preview"))
    preview_output = str(preview.get("output_excerpt", "")).lower()
    if (
        reason_code == PREVIEW_LOOPBACK_BIND_REASON_CODE
        or ("listen" in preview_output and "eperm" in preview_output and "127.0.0.1" in preview_output)
    ):
        reason_code = PREVIEW_LOOPBACK_BIND_REASON_CODE
        environment_blocker = True
    detail = (
        f"{TASK_BASED_UX_ENVIRONMENT_BLOCKER}:{reason_code}"
        if environment_blocker and reason_code
        else ""
    )
    return {
        "environment_blocker": environment_blocker,
        "reason_code": reason_code,
        "blocker": detail,
    }


def _gap_ledger_closure_requirement_visibility(
    gap_ledger_audit: dict[str, Any],
) -> dict[str, Any]:
    ledgers: dict[str, dict[str, Any]] = {}
    total_failed_ids: list[str] = []
    total_requirement_count = 0
    total_pass_count = 0
    total_fail_count = 0
    total_nonclosed_failed_rows = 0
    rows = [
        row for row in _as_list(gap_ledger_audit.get("row_outcomes")) if isinstance(row, dict)
    ]
    for ledger_name in ("commercial_solver", "ai_engine"):
        ledger_rows = [row for row in rows if str(row.get("ledger", "")) == ledger_name]
        nonclosed_rows = [row for row in ledger_rows if row.get("closed") is not True]
        failed_ids = sorted(
            f"{str(row.get('id', ''))}:{str(requirement_id)}"
            for row in nonclosed_rows
            for requirement_id in _as_list(row.get("closure_requirement_failed_ids"))
            if str(row.get("id", "")) and str(requirement_id)
        )
        requirement_count = sum(_as_int(row.get("closure_requirement_count")) for row in ledger_rows)
        pass_count = sum(_as_int(row.get("closure_requirement_pass_count")) for row in ledger_rows)
        fail_count = sum(_as_int(row.get("closure_requirement_fail_count")) for row in ledger_rows)
        nonclosed_failed_rows = sum(
            1
            for row in nonclosed_rows
            if _as_int(row.get("closure_requirement_fail_count")) > 0
        )
        total_requirement_count += requirement_count
        total_pass_count += pass_count
        total_fail_count += fail_count
        total_nonclosed_failed_rows += nonclosed_failed_rows
        total_failed_ids.extend(failed_ids)
        ledgers[ledger_name] = {
            "row_count": len(ledger_rows),
            "nonclosed_row_count": len(nonclosed_rows),
            "closure_requirement_count": requirement_count,
            "closure_requirement_pass_count": pass_count,
            "closure_requirement_fail_count": fail_count,
            "nonclosed_rows_with_failed_closure_requirements_count": nonclosed_failed_rows,
            "nonclosed_failed_closure_requirement_ids": failed_ids,
        }
    return {
        "source": "gap_ledger_evidence_audit.row_outcomes",
        "source_status": str(gap_ledger_audit.get("status", "missing")),
        "source_contract_pass": bool(gap_ledger_audit.get("contract_pass") is True),
        "source_full_gap_ledger_ready": bool(gap_ledger_audit.get("full_gap_ledger_ready") is True),
        "closure_requirement_count": total_requirement_count,
        "closure_requirement_pass_count": total_pass_count,
        "closure_requirement_fail_count": total_fail_count,
        "nonclosed_rows_with_failed_closure_requirements_count": total_nonclosed_failed_rows,
        "nonclosed_failed_closure_requirement_ids": sorted(dict.fromkeys(total_failed_ids)),
        "ledgers": ledgers,
        "claim_boundary": (
            "This is a visibility summary for existing gap-ledger closure requirements. "
            "It does not add Developer Preview blockers, close G1/G6/G7, create external "
            "receipts, or promote commercial readiness."
        ),
    }


def build_developer_preview_rc_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    phase1_core = _load_json(repo_root, PHASE1_CORE_API)
    preview = _load_json(repo_root, DEVELOPER_PREVIEW_READINESS)
    dataset_manifest = _load_json(repo_root, DATASET_LICENSE_MANIFEST)
    gap_ledger_audit = _load_json(repo_root, GAP_LEDGER_EVIDENCE_AUDIT)
    factory_summary = _load_json(repo_root, PHASE3_FACTORY_SUMMARY)
    factory_scorecard = _load_json(repo_root, PHASE3_FACTORY_SCORECARD)
    acquisition_plan = _load_json(repo_root, PHASE3_ACQUISITION_PLAN)
    repro_bundle = _load_json(repo_root, PHASE3_REPRO_BUNDLE)
    clean_checkout = _load_json(repo_root, PHASE3_CLEAN_CHECKOUT)
    git_clean_clone = _load_json(repo_root, PHASE3_GIT_CLEAN_CLONE)
    release_control_cleanup_plan = _load_json(repo_root, PHASE3_RELEASE_CONTROL_CLEANUP_PLAN)
    linux_windows_parity = _load_json(repo_root, PHASE6_LINUX_WINDOWS_PARITY_STATUS)
    silent_import_loss = _load_json(repo_root, PHASE6_SILENT_IMPORT_LOSS_STATUS)
    benchmark_scale = _load_json(repo_root, PHASE6_BENCHMARK_SCALE_STATUS)
    ux_observation_status = _load_json(repo_root, PHASE6_UX_OBSERVATION_STATUS)
    clean_checkout_status = _load_json(repo_root, PHASE6_CLEAN_CHECKOUT_STATUS)
    ifc_import = _load_json(repo_root, PHASE3_IFC_IMPORT_HEALTH)
    ifc_clean_acquisition = _load_json(repo_root, PHASE3_IFC_CLEAN_ACQUISITION)
    ifc_dirty_acquisition = _load_json(repo_root, PHASE3_IFC_DIRTY_ACQUISITION)
    ifc_source_license = _load_json(repo_root, PHASE3_IFC_SOURCE_LICENSE)
    ifc_query_gui = _load_json(repo_root, PHASE3_IFC_QUERY_GUI)
    medium_model_scorecard = _load_json(repo_root, PHASE3_MEDIUM_MODEL_SCORECARD)
    large_model_runner = _load_json(repo_root, PHASE3_LARGE_MODEL_RUNNER)
    import_template = _load_json(repo_root, PHASE4_IMPORT_TEMPLATE)
    cross_solver_readiness = _load_json(repo_root, PHASE4_CROSS_SOLVER_READINESS)
    phase5_gui_workflow = _load_json(repo_root, PHASE5_GUI_WORKFLOW)
    evidence_console = _load_json(repo_root, EVIDENCE_CONSOLE_SCOPE)
    ux_observation = _load_json(repo_root, UX_OBSERVATION)
    ux_intake = _load_json(repo_root, UX_OBSERVATION_INTAKE)

    package_ready = _pyproject_package_ready(repo_root)
    analysis_cli_ready = _cli_entry_ready(
        repo_root,
        "structural-analysis",
        "structural_analysis.api.cli:main",
    )
    benchmark_cli_ready = _cli_entry_ready(
        repo_root,
        "structural-analysis-benchmark",
        "structural_analysis.benchmark.cli:main",
    )
    package_runner = factory_summary.get("package_benchmark_runner")
    package_runner = package_runner if isinstance(package_runner, dict) else {}
    scorecard_ready = bool(
        factory_summary.get("contract_pass") is True
        and factory_summary.get("case_count") == factory_summary.get("pass_count")
        and int(factory_summary.get("case_count", 0) or 0) >= 20
    )
    scope_contract_pass = bool(evidence_console.get("scope_contract_pass") is True)
    acquisition_command = acquisition_plan.get("sample_acquisition_command")
    acquisition_command = acquisition_command if isinstance(acquisition_command, dict) else {}
    acquisition_command_ready = bool(acquisition_command.get("contract_pass") is True)
    dataset_ready = _contract_ready(dataset_manifest)
    repro_ready = _contract_ready(repro_bundle)
    clean_checkout_ready = _contract_ready(clean_checkout)
    git_clean_clone_ready = _contract_ready(git_clean_clone)
    ux_ready = bool(ux_observation_status.get("contract_pass") is True)

    deliverables = [
        _row(
            item="installable_python_package",
            status="ready" if package_ready and _contract_ready(phase1_core) else "blocked",
            contract_pass=package_ready and _contract_ready(phase1_core),
            evidence="pyproject.toml; setup.cfg; phase1_core_api_contract_summary.json",
            blockers=[] if package_ready else ["package_metadata_or_entry_points_missing"],
        ),
        _row(
            item="structural_analysis_cli",
            status="ready" if analysis_cli_ready and _contract_ready(phase1_core) else "blocked",
            contract_pass=analysis_cli_ready and _contract_ready(phase1_core),
            evidence="pyproject.toml; setup.cfg; phase1_core_api_contract_summary.json",
        ),
        _row(
            item="local_web_gui_surface",
            status="ready" if scope_contract_pass else "blocked",
            contract_pass=scope_contract_pass,
            evidence=str(EVIDENCE_CONSOLE_SCOPE),
            blockers=[]
            if scope_contract_pass
            else ["evidence_console_scope_contract_not_passed"],
            notes=[
                "Commercial/customer-shadow launch prerequisite is visible but not "
                "treated as a Developer Preview RC deliverable blocker."
            ],
        ),
        _row(
            item="sample_acquisition_command",
            status="ready" if acquisition_command_ready else "blocked",
            contract_pass=acquisition_command_ready,
            evidence=str(PHASE3_ACQUISITION_PLAN),
            blockers=[]
            if acquisition_command_ready
            else ["sample_acquisition_command_surface_not_ready"],
            notes=[
                "This deliverable checks the no-download acquisition policy command "
                "surface only; Phase 3 corpus acquisition blockers remain final-gate "
                "or benchmark blockers."
            ],
        ),
        _row(
            item="benchmark_runner",
            status="ready"
            if benchmark_cli_ready and package_runner.get("contract_pass") is True
            else "blocked",
            contract_pass=benchmark_cli_ready and package_runner.get("contract_pass") is True,
            evidence=str(PHASE3_FACTORY_SUMMARY),
            blockers=[]
            if benchmark_cli_ready and package_runner.get("contract_pass") is True
            else ["package_benchmark_runner_not_ready"],
        ),
        _row(
            item="benchmark_scorecard",
            status="ready" if scorecard_ready else "blocked",
            contract_pass=scorecard_ready,
            evidence=f"{PHASE3_FACTORY_SUMMARY}; {PHASE3_FACTORY_SCORECARD}",
            blockers=[] if scorecard_ready else ["generated_seed_scorecard_not_all_pass"],
        ),
        _row(
            item="known_limitations",
            status="ready",
            contract_pass=True,
            evidence=f"{DEVELOPER_PREVIEW_READINESS}; {PHASE3_ACQUISITION_PLAN}",
            notes=[
                "Known limitations are generated from active Developer Preview blockers "
                "and Phase 3 acquisition blockers."
            ],
        ),
        _row(
            item="reproducibility_bundle",
            status="ready" if repro_ready else "blocked",
            contract_pass=repro_ready,
            evidence=str(PHASE3_REPRO_BUNDLE),
            blockers=[] if repro_ready else ["reproducibility_bundle_not_ready"],
        ),
        _row(
            item="dataset_license_manifest",
            status="ready" if dataset_ready else "blocked",
            contract_pass=dataset_ready,
            evidence=str(DATASET_LICENSE_MANIFEST),
            blockers=list(dataset_manifest.get("blockers", [])),
        ),
        _row(
            item="commercial_comparison_import_template",
            status="ready" if _contract_ready(import_template) else "blocked",
            contract_pass=_contract_ready(import_template),
            evidence=str(PHASE4_IMPORT_TEMPLATE),
        ),
    ]

    remaining_targets = factory_summary.get("remaining_quantity_targets")
    remaining_targets = remaining_targets if isinstance(remaining_targets, dict) else {}
    analytic_current = int(remaining_targets.get("analytic_component_cases_current", 0) or 0)
    analytic_required = int(remaining_targets.get("analytic_component_cases_required", 20) or 20)
    medium_current = int(remaining_targets.get("medium_structural_models_current", 0) or 0)
    medium_required = int(remaining_targets.get("medium_structural_models_required", 5) or 5)
    large_current = int(remaining_targets.get("large_structural_models_current", 0) or 0)
    large_required = int(remaining_targets.get("large_structural_models_required", 2) or 2)
    ifc_current = int(remaining_targets.get("ifc_clean_dirty_import_cases_current", 0) or 0)
    ifc_required = int(remaining_targets.get("ifc_clean_dirty_import_cases_required", 10) or 10)
    medium_acquisition_blockers = _acquisition_blockers_for_lanes(
        acquisition_plan,
        {"opensees-medium"},
    )
    medium_scorecard_blockers = [
        str(blocker) for blocker in medium_model_scorecard.get("blockers", []) if str(blocker)
    ]
    benchmark_medium_gate = (
        benchmark_scale.get("medium_gate")
        if isinstance(benchmark_scale.get("medium_gate"), dict)
        else {}
    )
    benchmark_medium_blocker_grouping = (
        benchmark_medium_gate.get("blocker_grouping_metadata")
        if isinstance(benchmark_medium_gate.get("blocker_grouping_metadata"), dict)
        else {}
    )
    benchmark_medium_blockers = [
        str(blocker) for blocker in benchmark_medium_gate.get("blockers", []) if str(blocker)
    ]
    large_acquisition_blockers = _acquisition_blockers_for_lanes(
        acquisition_plan,
        {"opensees-megatall", "large-model-performance"},
    )
    large_runner_blockers = [
        str(blocker) for blocker in large_model_runner.get("blockers", []) if str(blocker)
    ]
    benchmark_large_gate = (
        benchmark_scale.get("large_gate")
        if isinstance(benchmark_scale.get("large_gate"), dict)
        else {}
    )
    benchmark_large_blocker_grouping = (
        benchmark_large_gate.get("blocker_grouping_metadata")
        if isinstance(benchmark_large_gate.get("blocker_grouping_metadata"), dict)
        else {}
    )
    benchmark_large_blockers = [
        str(blocker) for blocker in benchmark_large_gate.get("blockers", []) if str(blocker)
    ]
    analytic_component_ready = bool(
        scorecard_ready
        and analytic_current >= analytic_required
    )
    medium_ready = bool(benchmark_medium_gate.get("contract_pass") is True)
    large_ready = bool(benchmark_large_gate.get("contract_pass") is True)
    ifc_ready = bool(silent_import_loss.get("contract_pass") is True)
    score_rows = factory_scorecard.get("rows")
    score_rows = score_rows if isinstance(score_rows, list) else []
    residual_metrics_ready = bool(
        score_rows
        and all(
            isinstance(row, dict)
            and isinstance(row.get("metrics"), dict)
            and row["metrics"].get("residual_formula") == "F_internal_minus_F_external"
            for row in score_rows
        )
    )
    convergence_history_ready = _scorecard_convergence_history_ready(score_rows)
    unsupported_ready = bool(_contract_ready(phase1_core) and _contract_ready(import_template))
    git_clean_clone_blockers = [
        str(blocker) for blocker in git_clean_clone.get("blockers", []) if str(blocker)
    ]
    required_git_clean_clone_inputs = [
        str(path) for path in git_clean_clone.get("required_git_clean_clone_inputs", []) if str(path)
    ]
    expected_scorecard = (
        repro_bundle.get("expected_scorecard")
        if isinstance(repro_bundle.get("expected_scorecard"), dict)
        else {}
    )
    stable_artifact_checksums = (
        repro_bundle.get("stable_artifact_checksums")
        if isinstance(repro_bundle.get("stable_artifact_checksums"), dict)
        else {}
    )
    clean_checkout_blockers = []
    if not clean_checkout_ready:
        clean_checkout_blockers.append("clean_checkout_reproduction_not_passed")
    if not git_clean_clone_ready:
        clean_checkout_blockers.append("git_clean_clone_reproduction_not_passed")
        clean_checkout_blockers.extend(git_clean_clone_blockers[:8])
    phase6_clean_checkout_ready = bool(clean_checkout_status.get("contract_pass") is True)
    phase6_clean_checkout_blockers = [
        str(blocker) for blocker in clean_checkout_status.get("blockers", []) if str(blocker)
    ]
    phase6_clean_checkout_blocker_grouping = (
        clean_checkout_status.get("blocker_grouping_metadata")
        if isinstance(clean_checkout_status.get("blocker_grouping_metadata"), dict)
        else {}
    )
    phase5_task_based_ux_test = _as_dict(phase5_gui_workflow.get("task_based_ux_test"))
    phase5_task_based_ux_browser_execution_receipt = _as_dict(
        phase5_gui_workflow.get("task_based_ux_browser_execution_receipt")
    )
    phase5_task_based_ux_environment = _task_based_ux_environment_classification(
        phase5_task_based_ux_test,
        phase5_task_based_ux_browser_execution_receipt,
    )
    if phase5_task_based_ux_environment["reason_code"]:
        phase5_task_based_ux_test = {
            **phase5_task_based_ux_test,
            "browser_execution_environment_blocker": bool(
                phase5_task_based_ux_environment["environment_blocker"]
            ),
            "browser_execution_blocker_reason_code": str(
                phase5_task_based_ux_environment["reason_code"]
            ),
            "execution_environment_blocker": str(phase5_task_based_ux_environment["blocker"]),
        }
    phase5_gui_workflow_blockers = list(phase5_gui_workflow.get("blockers", []))
    if (
        phase5_task_based_ux_environment["blocker"]
        and phase5_task_based_ux_environment["blocker"] not in phase5_gui_workflow_blockers
    ):
        phase5_gui_workflow_blockers.append(str(phase5_task_based_ux_environment["blocker"]))
    ux_status_blockers = list(ux_observation_status.get("blockers", []))
    if (
        phase5_task_based_ux_environment["blocker"]
        and phase5_task_based_ux_environment["blocker"] not in ux_status_blockers
    ):
        ux_status_blockers.append(str(phase5_task_based_ux_environment["blocker"]))
    ux_status_blocker_grouping = (
        ux_observation_status.get("blocker_grouping_metadata")
        if isinstance(ux_observation_status.get("blocker_grouping_metadata"), dict)
        else {}
    )
    linux_windows_receipt_blockers = [
        str(blocker)
        for blocker in linux_windows_parity.get("blocked_by", [])
        if str(blocker)
    ]
    linux_windows_gate_blockers = [
        blocker
        for blocker in linux_windows_receipt_blockers
        if blocker != "git_clean_clone_reproduction_not_passed"
    ]
    if not linux_windows_gate_blockers and linux_windows_parity.get("contract_pass") is not True:
        linux_windows_gate_blockers = ["linux_windows_parity_receipts_missing"]
    linux_windows_blocker_grouping = (
        linux_windows_parity.get("blocker_grouping_metadata")
        if isinstance(linux_windows_parity.get("blocker_grouping_metadata"), dict)
        else {}
    )
    linux_windows_gate_blocker_grouping = _filter_blocker_grouping_metadata(
        linux_windows_blocker_grouping,
        linux_windows_gate_blockers,
    )

    final_gates = [
        _row(
            item="analytic_component_benchmark_all_pass",
            status="ready" if analytic_component_ready else "blocked",
            contract_pass=analytic_component_ready,
            evidence=str(PHASE3_FACTORY_SUMMARY),
        ),
        _row(
            item="selected_medium_models_pass_or_approved_review",
            status="ready" if medium_ready else "blocked",
            contract_pass=medium_ready,
            evidence=(
                f"{PHASE3_FACTORY_SUMMARY}; {PHASE3_ACQUISITION_PLAN}; "
                f"{PHASE3_MEDIUM_MODEL_SCORECARD}; {PHASE6_BENCHMARK_SCALE_STATUS}"
            ),
            blockers=[]
            if medium_ready
            else list(
                dict.fromkeys(
                    [
                        f"medium_structural_models_current_below_required:{medium_current}/{medium_required}",
                        *medium_acquisition_blockers,
                        *medium_scorecard_blockers,
                        *benchmark_medium_blockers,
                    ]
                )
            ),
            blocker_grouping_metadata=benchmark_medium_blocker_grouping,
            notes=[
                "Requires passing or pre-approved REVIEW evidence for selected medium "
                "OpenSees/reference models. Local topology/parser evidence does not "
                "count as medium-model benchmark pass evidence."
            ],
        ),
        _row(
            item="large_models_crash_oom_free",
            status="ready" if large_ready else "blocked",
            contract_pass=large_ready,
            evidence=(
                f"{PHASE3_FACTORY_SUMMARY}; {PHASE3_ACQUISITION_PLAN}; "
                f"{PHASE3_LARGE_MODEL_RUNNER}; {PHASE6_BENCHMARK_SCALE_STATUS}"
            ),
            blockers=[]
            if large_ready
            else list(
                dict.fromkeys(
                    [
                        f"large_structural_models_current_below_required:{large_current}/{large_required}",
                        *large_acquisition_blockers,
                        *large_runner_blockers,
                        *benchmark_large_blockers,
                    ]
                )
            ),
            blocker_grouping_metadata=benchmark_large_blocker_grouping,
            notes=[
                "Requires acquired large-model sources, runner/nightly lane evidence, "
                "and crash/OOM-free execution receipts. Policy-only acquisition rows "
                "do not satisfy this final gate."
            ],
        ),
        _row(
            item="silent_import_loss_zero",
            status="ready" if ifc_ready else "blocked",
            contract_pass=ifc_ready,
            evidence=(
                f"{PHASE3_IFC_IMPORT_HEALTH}; {PHASE3_IFC_CLEAN_ACQUISITION}; "
                f"{PHASE3_IFC_DIRTY_ACQUISITION}; {PHASE3_IFC_SOURCE_LICENSE}; "
                f"{PHASE6_SILENT_IMPORT_LOSS_STATUS}"
            ),
            blockers=list(silent_import_loss.get("blockers", [])),
            notes=[
                "Requires acquired/checksummed clean and dirty IFC files, license "
                "review, and executed import-health plus negative/import-hardening "
                "contracts. Source identity or expected contracts alone do not prove "
                "silent import loss is zero."
            ],
        ),
        _row(
            item="residual_and_convergence_history_present",
            status="ready" if residual_metrics_ready and convergence_history_ready else "blocked",
            contract_pass=residual_metrics_ready and convergence_history_ready,
            evidence=f"{PHASE3_FACTORY_SCORECARD}; {PHASE1_CORE_API}",
            blockers=[]
            if residual_metrics_ready and convergence_history_ready
            else ["benchmark_scorecard_convergence_history_not_retained_per_case"],
            notes=[
                "Generated scorecard rows must retain residual formula and non-empty "
                "per-case convergence history with residual and increment fields."
            ],
        ),
        _row(
            item="unsupported_features_explicitly_blocked",
            status="ready" if unsupported_ready else "blocked",
            contract_pass=unsupported_ready,
            evidence=f"{PHASE1_CORE_API}; {PHASE4_IMPORT_TEMPLATE}",
        ),
        _row(
            item="linux_windows_reproducibility_confirmed",
            status="blocked",
            contract_pass=False,
            evidence=(
                f"{PHASE3_REPRO_BUNDLE}; {PHASE3_GIT_CLEAN_CLONE}; "
                f"{PHASE6_LINUX_WINDOWS_PARITY_STATUS}"
            ),
            blockers=linux_windows_gate_blockers,
            blocker_grouping_metadata=linux_windows_gate_blocker_grouping,
            notes=[
                "Requires independent Linux and Windows receipts that replay the "
                "same seed benchmark commands and compare stable output checksums. "
                "Git clean-clone blockers are tracked under "
                "benchmark_results_clean_checkout_regenerated so this gate remains "
                "scoped to missing Linux/Windows parity evidence."
            ],
        ),
        _row(
            item="new_user_core_workflow_observation_passed",
            status="ready" if ux_ready else "blocked",
            contract_pass=ux_ready,
            evidence=f"{UX_OBSERVATION}; {UX_OBSERVATION_INTAKE}; {PHASE6_UX_OBSERVATION_STATUS}",
            blockers=ux_status_blockers,
            blocker_grouping_metadata=ux_status_blocker_grouping,
            notes=[
                "This gate requires a passing human new-user observation report. "
                "The intake packet is an owner handoff checklist only, automated "
                "browser/task evidence does not replace human observation, and visible "
                "workflow shell coverage does not satisfy the gate by itself."
            ],
        ),
        _row(
            item="benchmark_results_clean_checkout_regenerated",
            status="ready" if phase6_clean_checkout_ready else "blocked",
            contract_pass=phase6_clean_checkout_ready,
            evidence=(
                f"{PHASE3_CLEAN_CHECKOUT}; {PHASE3_GIT_CLEAN_CLONE}; "
                f"{PHASE3_RELEASE_CONTROL_CLEANUP_PLAN}; {PHASE6_CLEAN_CHECKOUT_STATUS}"
            ),
            blockers=phase6_clean_checkout_blockers or clean_checkout_blockers,
            blocker_grouping_metadata=phase6_clean_checkout_blocker_grouping,
            notes=[
                "Local isolated worktree-copy replay and git clean-clone replay are "
                "separate evidence. This gate requires both to pass and cannot be "
                "closed until every required git-clean-clone input is tracked and "
                "committed in the replayed source state. The Phase 6 status receipt "
                "keeps local replay, real git clone replay, and cleanup handoff "
                "separate."
            ],
        ),
    ]

    deliverable_blockers = [
        f"deliverable_blocked:{row['item']}"
        for row in deliverables
        if row["contract_pass"] is not True
    ]
    final_gate_blockers = [
        f"final_gate_blocked:{row['item']}"
        for row in final_gates
        if row["contract_pass"] is not True
    ]
    future_commercial_gates = [
        "30_run_ci_streak",
        "customer_shadow",
        "product_license",
        "license_server_operation",
        "commercial_sla",
        "external_approval_receipts",
        "remote_github_sync",
    ]
    rc_ready = bool(not deliverable_blockers and not final_gate_blockers)
    preview_gap_visibility = preview.get("gap_ledger_closure_requirement_visibility")
    gap_ledger_closure_requirement_visibility = (
        preview_gap_visibility
        if isinstance(preview_gap_visibility, dict) and preview_gap_visibility
        else _gap_ledger_closure_requirement_visibility(gap_ledger_audit)
    )
    known_limitations = {
        "developer_preview_blocker_count": int(preview.get("blocker_count", 0) or 0),
        "developer_preview_blockers": list(preview.get("blockers", []))[:20],
        "gap_ledger_closure_requirement_visibility": gap_ledger_closure_requirement_visibility,
        "phase3_acquisition_blockers": list(acquisition_plan.get("blockers", []))[:20],
        "dataset_license_blockers": list(dataset_manifest.get("blockers", [])),
        "dataset_license_external_corpus_blockers": list(
            (
                dataset_manifest.get("phase3_external_corpus_readiness")
                if isinstance(dataset_manifest.get("phase3_external_corpus_readiness"), dict)
                else {}
            ).get("blockers", [])
        ),
        "ux_new_user_observation_handoff": {
            "ux_observation_status_receipt": str(PHASE6_UX_OBSERVATION_STATUS),
            "ux_observation_status": str(ux_observation_status.get("status", "missing")),
            "ux_observation_contract_pass": bool(ux_observation_status.get("contract_pass") is True),
            "observation_report": str(UX_OBSERVATION),
            "intake_packet": str(UX_OBSERVATION_INTAKE),
            "human_observation_gate": (
                ux_observation_status.get("human_observation_gate")
                if isinstance(ux_observation_status.get("human_observation_gate"), dict)
                else {}
            ),
            "intake_packet_gate": (
                ux_observation_status.get("intake_packet_gate")
                if isinstance(ux_observation_status.get("intake_packet_gate"), dict)
                else {}
            ),
            "phase5_workflow_gate": (
                ux_observation_status.get("phase5_workflow_gate")
                if isinstance(ux_observation_status.get("phase5_workflow_gate"), dict)
                else {}
            ),
            "phase6_ux_status_blockers": ux_status_blockers,
            "phase6_ux_blocker_grouping": ux_status_blocker_grouping,
            "owner_action": str(ux_observation.get("summary", {}).get("owner_action", "")),
            "report_blockers": list(ux_observation.get("blockers", [])),
            "required_workflow_steps": list(
                (
                    ux_observation.get("summary")
                    if isinstance(ux_observation.get("summary"), dict)
                    else {}
                ).get("required_workflow_steps", ux_observation.get("required_workflow_steps", []))
            ),
            "workflow_step_pass_count": int(
                (
                    ux_observation.get("summary")
                    if isinstance(ux_observation.get("summary"), dict)
                    else {}
                ).get("workflow_step_pass_count", 0)
                or 0
            ),
            "required_workflow_step_count": int(
                (
                    ux_observation.get("summary")
                    if isinstance(ux_observation.get("summary"), dict)
                    else {}
                ).get("required_workflow_step_count", 0)
                or 0
            ),
            "missing_workflow_steps": list(
                (
                    ux_observation.get("summary")
                    if isinstance(ux_observation.get("summary"), dict)
                    else {}
                ).get("missing_workflow_steps", [])
            ),
            "not_passed_workflow_steps": list(
                (
                    ux_observation.get("summary")
                    if isinstance(ux_observation.get("summary"), dict)
                    else {}
                ).get("not_passed_workflow_steps", [])
            ),
            "intake_field_pass_count": int(
                (ux_intake.get("summary") if isinstance(ux_intake.get("summary"), dict) else {}).get(
                    "field_pass_count",
                    0,
                )
                or 0
            ),
            "intake_field_count": int(
                (ux_intake.get("summary") if isinstance(ux_intake.get("summary"), dict) else {}).get(
                    "field_count",
                    0,
                )
                or 0
            ),
            "validation_commands": list(
                dict.fromkeys(
                    [
                        *[
                            str(command)
                            for command in ux_observation.get("validation_commands", [])
                            if str(command)
                        ],
                        *[
                            str(command)
                            for command in ux_intake.get("validation_commands", [])
                            if str(command)
                        ],
                    ]
                )
            ),
            "claim_boundary": (
                "Human new-user observation remains required. Intake evidence is only "
                "a handoff checklist, automated browser/task tests do not replace the "
                "human observation, and visible workflow shell coverage cannot close "
                "the RC UX final gate."
            ),
        },
        "benchmark_quantity_handoff": {
            "source": str(PHASE3_FACTORY_SUMMARY),
            "acquisition_plan": str(PHASE3_ACQUISITION_PLAN),
            "benchmark_scale_status_receipt": str(PHASE6_BENCHMARK_SCALE_STATUS),
            "benchmark_scale_status": str(benchmark_scale.get("status", "missing")),
            "benchmark_scale_contract_pass": bool(benchmark_scale.get("contract_pass") is True),
            "benchmark_scale_blocker_grouping": (
                benchmark_scale.get("blocker_grouping_metadata")
                if isinstance(benchmark_scale.get("blocker_grouping_metadata"), dict)
                else {}
            ),
            "targets": {
                "analytic_component": {
                    "current": analytic_current,
                    "required": analytic_required,
                    "remaining": max(analytic_required - analytic_current, 0),
                    "contract_pass": analytic_component_ready,
                },
                "medium_structural_models": {
                    "current": medium_current,
                    "required": medium_required,
                    "remaining": max(medium_required - medium_current, 0),
                    "contract_pass": medium_ready,
                    "acquisition_blockers": medium_acquisition_blockers,
                    "scorecard_blockers": medium_scorecard_blockers,
                    "scorecard_readiness_receipt": str(PHASE3_MEDIUM_MODEL_SCORECARD),
                    "benchmark_scale_gate": benchmark_medium_gate,
                },
                "large_structural_models": {
                    "current": large_current,
                    "required": large_required,
                    "remaining": max(large_required - large_current, 0),
                    "contract_pass": large_ready,
                    "acquisition_blockers": large_acquisition_blockers,
                    "runner_blockers": large_runner_blockers,
                    "runner_readiness_receipt": str(PHASE3_LARGE_MODEL_RUNNER),
                    "benchmark_scale_gate": benchmark_large_gate,
                },
                "ifc_clean_dirty_import_cases": {
                    "current": ifc_current,
                    "required": ifc_required,
                    "remaining": max(ifc_required - ifc_current, 0),
                    "contract_pass": ifc_ready,
                },
            },
            "owner_action": (
                "Attach/acquire licensed medium and large reference models, ingest "
                "reference outputs, run normalized benchmark scorecards, and record "
                "approved REVIEW rows only where the final-gate policy allows review."
            ),
            "claim_boundary": (
                "This handoff records quantity gaps and acquisition blockers only. It "
                "does not create medium/large benchmark evidence or close full Phase 3."
            ),
        },
        "medium_model_scorecard_handoff": {
            "scorecard_readiness_receipt": str(PHASE3_MEDIUM_MODEL_SCORECARD),
            "benchmark_scale_status_receipt": str(PHASE6_BENCHMARK_SCALE_STATUS),
            "benchmark_scale_status": str(benchmark_scale.get("status", "missing")),
            "benchmark_scale_contract_pass": bool(benchmark_scale.get("contract_pass") is True),
            "benchmark_scale_gate": benchmark_medium_gate,
            "benchmark_scale_blocker_grouping": benchmark_medium_blocker_grouping,
            "required_medium_model_count": int(
                medium_model_scorecard.get("required_medium_model_count", 5) or 5
            ),
            "current_medium_model_scorecard_count": int(
                medium_model_scorecard.get("current_medium_model_scorecard_count", 0) or 0
            ),
            "pass_or_approved_review_count": int(
                medium_model_scorecard.get("pass_or_approved_review_count", 0) or 0
            ),
            "local_candidate_artifact_count": int(
                medium_model_scorecard.get("local_candidate_artifact_count", 0) or 0
            ),
            "local_topology_contract_pass": bool(
                medium_model_scorecard.get("local_topology_contract_pass") is True
            ),
            "required_evidence_count": int(medium_model_scorecard.get("required_evidence_count", 0) or 0),
            "required_evidence_pass_count": int(
                medium_model_scorecard.get("required_evidence_pass_count", 0) or 0
            ),
            "runner_command_ready": bool(
                medium_model_scorecard.get("runner_command_ready") is True
            ),
            "runner_command_template": str(
                medium_model_scorecard.get("runner_command_template") or ""
            ),
            "resource_envelope": (
                medium_model_scorecard.get("resource_envelope")
                if isinstance(medium_model_scorecard.get("resource_envelope"), dict)
                else {}
            ),
            "blockers": medium_scorecard_blockers,
            "local_parser_boundary": (
                medium_model_scorecard.get("local_parser_boundary")
                if isinstance(medium_model_scorecard.get("local_parser_boundary"), dict)
                else {}
            ),
            "scorecard_receipt_template": (
                medium_model_scorecard.get("scorecard_receipt_template")
                if isinstance(medium_model_scorecard.get("scorecard_receipt_template"), dict)
                else {}
            ),
            "owner_action": str(medium_model_scorecard.get("owner_action", "")),
            "claim_boundary": str(medium_model_scorecard.get("claim_boundary", "")),
        },
        "large_model_runner_handoff": {
            "runner_readiness_receipt": str(PHASE3_LARGE_MODEL_RUNNER),
            "benchmark_scale_status_receipt": str(PHASE6_BENCHMARK_SCALE_STATUS),
            "benchmark_scale_status": str(benchmark_scale.get("status", "missing")),
            "benchmark_scale_contract_pass": bool(benchmark_scale.get("contract_pass") is True),
            "benchmark_scale_gate": benchmark_large_gate,
            "benchmark_scale_blocker_grouping": benchmark_large_blocker_grouping,
            "required_large_model_count": int(large_model_runner.get("required_large_model_count", 2) or 2),
            "current_large_model_execution_receipt_count": int(
                large_model_runner.get("current_large_model_execution_receipt_count", 0) or 0
            ),
            "crash_oom_free_execution_count": int(
                large_model_runner.get("crash_oom_free_execution_count", 0) or 0
            ),
            "scorecard_or_review_count": int(large_model_runner.get("scorecard_or_review_count", 0) or 0),
            "required_evidence_count": int(large_model_runner.get("required_evidence_count", 0) or 0),
            "required_evidence_pass_count": int(large_model_runner.get("required_evidence_pass_count", 0) or 0),
            "blockers": large_runner_blockers,
            "runner_command_ready": bool(large_model_runner.get("runner_command_ready") is True),
            "runner_command_template": str(large_model_runner.get("runner_command_template", "")),
            "resource_envelope": (
                large_model_runner.get("resource_envelope")
                if isinstance(large_model_runner.get("resource_envelope"), dict)
                else {}
            ),
            "runner_receipt_template": (
                large_model_runner.get("runner_receipt_template")
                if isinstance(large_model_runner.get("runner_receipt_template"), dict)
                else {}
            ),
            "owner_action": str(large_model_runner.get("owner_action", "")),
            "claim_boundary": str(large_model_runner.get("claim_boundary", "")),
        },
        "ifc_import_handoff": {
            "silent_import_loss_status_receipt": str(PHASE6_SILENT_IMPORT_LOSS_STATUS),
            "silent_import_loss_status": str(silent_import_loss.get("status", "missing")),
            "silent_import_loss_contract_pass": bool(
                silent_import_loss.get("contract_pass") is True
            ),
            "import_health_receipt": str(PHASE3_IFC_IMPORT_HEALTH),
            "clean_acquisition_receipt": str(PHASE3_IFC_CLEAN_ACQUISITION),
            "dirty_acquisition_receipt": str(PHASE3_IFC_DIRTY_ACQUISITION),
            "source_license_receipt": str(PHASE3_IFC_SOURCE_LICENSE),
            "clean_selected_file_count": int(ifc_clean_acquisition.get("selected_file_count", 0) or 0),
            "clean_expected_contract_count": int(
                ifc_clean_acquisition.get("expected_import_health_contract_count", 0) or 0
            ),
            "clean_execution_count": int(
                ifc_clean_acquisition.get("import_health_execution_count", 0) or 0
            ),
            "dirty_selected_file_count": int(ifc_dirty_acquisition.get("selected_file_count", 0) or 0),
            "dirty_expected_contract_count": int(
                ifc_dirty_acquisition.get("expected_negative_import_contract_count", 0) or 0
            ),
            "dirty_execution_count": int(
                ifc_dirty_acquisition.get("dirty_import_execution_count", 0) or 0
            ),
            "import_health_execution_count": int(
                ifc_import.get("import_health_execution_count", 0) or 0
            ),
            "import_health_contract_pass_count": int(
                ifc_import.get("import_health_contract_pass_count", 0) or 0
            ),
            "selected_import_case_count": int(
                silent_import_loss.get("selected_import_case_count", 0) or 0
            ),
            "required_ifc_import_case_count": int(
                silent_import_loss.get("required_ifc_import_case_count", 0) or 0
            ),
            "evidence_requirements": (
                silent_import_loss.get("evidence_requirements")
                if isinstance(silent_import_loss.get("evidence_requirements"), dict)
                else {}
            ),
            "source_license_blockers": list(ifc_source_license.get("blockers", [])),
            "import_health_blockers": list(ifc_import.get("blockers", [])),
            "clean_acquisition_blockers": list(ifc_clean_acquisition.get("blockers", [])),
            "dirty_acquisition_blockers": list(ifc_dirty_acquisition.get("blockers", [])),
            "silent_import_loss_blockers": list(silent_import_loss.get("blockers", [])),
            "silent_import_loss_direct_blockers": list(
                silent_import_loss.get("direct_blockers", silent_import_loss.get("blockers", []))
            ),
            "silent_import_loss_spillover_blockers": list(
                silent_import_loss.get("spillover_blockers", [])
            ),
            "silent_import_loss_all_blockers": list(
                silent_import_loss.get("all_blockers", silent_import_loss.get("blockers", []))
            ),
            "silent_import_loss_blocker_grouping": (
                silent_import_loss.get("blocker_grouping_metadata")
                if isinstance(silent_import_loss.get("blocker_grouping_metadata"), dict)
                else {}
            ),
            "owner_action": (
                str(silent_import_loss.get("owner_action", ""))
                or "Acquire the selected clean/dirty IFC files after license review, attach "
                "source SHA256 values, execute the import-health and negative/import-hardening "
                "contracts, and keep unsupported entities explicit."
            ),
            "claim_boundary": (
                str(silent_import_loss.get("claim_boundary", ""))
                or "IFC import-health handoff prevents silent-data-loss claims from being "
                "promoted without executed evidence. It is not solver accuracy evidence "
                "and does not close full Phase 3."
            ),
        },
        "ifc_query_gui_handoff": {
            "query_gui_readiness_receipt": str(PHASE3_IFC_QUERY_GUI),
            "required_task_source_count": int(ifc_query_gui.get("required_task_source_count", 1) or 1),
            "current_task_source_count": int(ifc_query_gui.get("current_task_source_count", 0) or 0),
            "task_manifest_count": int(ifc_query_gui.get("task_manifest_count", 0) or 0),
            "expected_answer_count": int(ifc_query_gui.get("expected_answer_count", 0) or 0),
            "gui_task_execution_count": int(ifc_query_gui.get("gui_task_execution_count", 0) or 0),
            "workflow_step_count": int(ifc_query_gui.get("workflow_step_count", 0) or 0),
            "workflow_step_pass_count": int(ifc_query_gui.get("workflow_step_pass_count", 0) or 0),
            "missing_workflow_steps": list(ifc_query_gui.get("missing_workflow_steps", [])),
            "required_evidence_count": int(ifc_query_gui.get("required_evidence_count", 0) or 0),
            "required_evidence_pass_count": int(ifc_query_gui.get("required_evidence_pass_count", 0) or 0),
            "blockers": list(ifc_query_gui.get("blockers", [])),
            "task_execution_receipt_template": (
                ifc_query_gui.get("task_execution_receipt_template")
                if isinstance(ifc_query_gui.get("task_execution_receipt_template"), dict)
                else {}
            ),
            "owner_action": str(ifc_query_gui.get("owner_action", "")),
            "claim_boundary": str(ifc_query_gui.get("claim_boundary", "")),
        },
        "phase5_gui_workflow_handoff": {
            "gui_workflow_readiness_receipt": str(PHASE5_GUI_WORKFLOW),
            "required_workflow_step_count": int(
                phase5_gui_workflow.get("required_workflow_step_count", 0) or 0
            ),
            "workflow_shell_step_pass_count": int(
                phase5_gui_workflow.get("workflow_shell_step_pass_count", 0) or 0
            ),
            "actual_gui_workflow_step_pass_count": int(
                phase5_gui_workflow.get("actual_gui_workflow_step_pass_count", 0) or 0
            ),
            "actual_gui_workflow_step_partial_count": int(
                phase5_gui_workflow.get("actual_gui_workflow_step_partial_count", 0) or 0
            ),
            "execution_workflow_step_pass_count": int(
                phase5_gui_workflow.get("execution_workflow_step_pass_count", 0) or 0
            ),
            "missing_actual_gui_workflow_steps": list(
                phase5_gui_workflow.get("missing_actual_gui_workflow_steps", [])
            ),
            "missing_execution_workflow_steps": list(
                phase5_gui_workflow.get("missing_execution_workflow_steps", [])
            ),
            "partial_actual_gui_workflow_steps": list(
                phase5_gui_workflow.get("partial_actual_gui_workflow_steps", [])
            ),
            "handoff_surface": (
                phase5_gui_workflow.get("handoff_surface")
                if isinstance(phase5_gui_workflow.get("handoff_surface"), dict)
                else {}
            ),
            "task_based_ux_test": phase5_task_based_ux_test,
            "task_based_ux_browser_execution_receipt": phase5_task_based_ux_browser_execution_receipt,
            "route_case_run_state_model": (
                phase5_gui_workflow.get("route_case_run_state_model")
                if isinstance(phase5_gui_workflow.get("route_case_run_state_model"), dict)
                else {}
            ),
            "blockers": phase5_gui_workflow_blockers,
            "owner_action": str(phase5_gui_workflow.get("owner_action", "")),
            "claim_boundary": str(phase5_gui_workflow.get("claim_boundary", "")),
        },
        "commercial_cross_solver_handoff": {
            "cross_solver_readiness_receipt": str(PHASE4_CROSS_SOLVER_READINESS),
            "required_reference_solver_count": int(
                cross_solver_readiness.get("required_reference_solver_count", 2) or 2
            ),
            "current_reference_solver_count": int(
                cross_solver_readiness.get("current_reference_solver_count", 0) or 0
            ),
            "operator_package_attached": bool(cross_solver_readiness.get("operator_package_attached") is True),
            "operator_permission_attached": bool(
                cross_solver_readiness.get("operator_permission_attached") is True
            ),
            "operator_checksum_count": int(cross_solver_readiness.get("operator_checksum_count", 0) or 0),
            "operator_trace_rows_available": bool(
                cross_solver_readiness.get("operator_trace_rows_available") is True
            ),
            "required_evidence_count": int(cross_solver_readiness.get("required_evidence_count", 0) or 0),
            "required_evidence_pass_count": int(
                cross_solver_readiness.get("required_evidence_pass_count", 0) or 0
            ),
            "blockers": list(cross_solver_readiness.get("blockers", [])),
            "readiness_inputs": (
                cross_solver_readiness.get("readiness_inputs")
                if isinstance(cross_solver_readiness.get("readiness_inputs"), dict)
                else {}
            ),
            "operator_package_template": (
                cross_solver_readiness.get("operator_package_template")
                if isinstance(cross_solver_readiness.get("operator_package_template"), dict)
                else {}
            ),
            "owner_action": str(cross_solver_readiness.get("owner_action", "")),
            "claim_boundary": str(cross_solver_readiness.get("claim_boundary", "")),
        },
        "linux_windows_reproducibility_handoff": {
            "parity_status_receipt": str(PHASE6_LINUX_WINDOWS_PARITY_STATUS),
            "parity_status": str(linux_windows_parity.get("status", "missing")),
            "parity_contract_pass": bool(linux_windows_parity.get("contract_pass") is True),
            "reproducibility_bundle": str(PHASE3_REPRO_BUNDLE),
            "git_clean_clone_receipt": str(PHASE3_GIT_CLEAN_CLONE),
            "required_platforms": list(
                linux_windows_parity.get("required_platforms", ["linux", "windows"])
            ),
            "current_platform_receipts": list(
                linux_windows_parity.get("current_platform_receipts", [])
            ),
            "missing_platform_receipts": list(
                linux_windows_parity.get("missing_platform_receipts", ["linux", "windows"])
            ),
            "platform_receipt_schema": str(
                linux_windows_parity.get(
                    "platform_receipt_schema",
                    "phase6-linux-windows-platform-replay-receipt.v1",
                )
            ),
            "platform_receipt_template": {
                **(
                    linux_windows_parity.get("platform_receipt_template")
                    if isinstance(linux_windows_parity.get("platform_receipt_template"), dict)
                    else {}
                )
            },
            "required_commands": list(linux_windows_parity.get("required_commands", [])),
            "comparison_requirements": list(
                linux_windows_parity.get("comparison_requirements", [])
            ),
            "expected_stable_artifact_checksums": (
                linux_windows_parity.get("expected_stable_artifact_checksums")
                if isinstance(linux_windows_parity.get("expected_stable_artifact_checksums"), dict)
                else stable_artifact_checksums
            ),
            "expected_scorecard": (
                linux_windows_parity.get("expected_scorecard")
                if isinstance(linux_windows_parity.get("expected_scorecard"), dict)
                else expected_scorecard
            ),
            "parity_comparison_contract": (
                linux_windows_parity.get("parity_comparison_contract")
                if isinstance(linux_windows_parity.get("parity_comparison_contract"), dict)
                else {}
            ),
            "blocked_by": list(
                linux_windows_parity.get("blocked_by", ["linux_windows_parity_receipts_missing"])
            ),
            "parity_blocker_grouping": linux_windows_blocker_grouping,
            "parity_gate_blocker_grouping": linux_windows_gate_blocker_grouping,
            "clean_clone_blockers_tracked_elsewhere": list(git_clean_clone_blockers[:8]),
            "owner_action": str(
                linux_windows_parity.get(
                    "owner_action",
                    "Run the seed benchmark replay on Linux and Windows from the same "
                    "tracked source state, attach platform receipts with stable checksums, "
                    "and compare scorecard identity before promoting parity.",
                )
            ),
            "claim_boundary": str(
                linux_windows_parity.get(
                    "claim_boundary",
                    "This handoff defines the Linux/Windows parity evidence required for "
                    "the RC gate. It does not prove parity and does not replace the separate "
                    "git clean-clone reproduction gate.",
                )
            ),
        },
        "clean_checkout_reproduction_handoff": {
            "clean_checkout_status_receipt": str(PHASE6_CLEAN_CHECKOUT_STATUS),
            "clean_checkout_status": str(clean_checkout_status.get("status", "missing")),
            "clean_checkout_status_contract_pass": bool(clean_checkout_status.get("contract_pass") is True),
            "local_clean_checkout_gate": (
                clean_checkout_status.get("local_clean_checkout_gate")
                if isinstance(clean_checkout_status.get("local_clean_checkout_gate"), dict)
                else {}
            ),
            "git_clean_clone_gate": (
                clean_checkout_status.get("git_clean_clone_gate")
                if isinstance(clean_checkout_status.get("git_clean_clone_gate"), dict)
                else {}
            ),
            "release_control_cleanup_gate": (
                clean_checkout_status.get("release_control_cleanup_gate")
                if isinstance(clean_checkout_status.get("release_control_cleanup_gate"), dict)
                else {}
            ),
            "phase6_clean_checkout_blockers": list(clean_checkout_status.get("blockers", [])),
            "phase6_clean_checkout_blocker_grouping": phase6_clean_checkout_blocker_grouping,
            "clean_checkout_receipt": str(PHASE3_CLEAN_CHECKOUT),
            "git_clean_clone_receipt": str(PHASE3_GIT_CLEAN_CLONE),
            "release_control_cleanup_plan": str(PHASE3_RELEASE_CONTROL_CLEANUP_PLAN),
            "reproducibility_bundle": str(PHASE3_REPRO_BUNDLE),
            "local_clean_checkout": {
                "status": str(clean_checkout.get("status", "missing")),
                "contract_pass": clean_checkout_ready,
                "executed": bool(clean_checkout.get("clean_checkout_executed") is True),
                "claim_boundary": str(clean_checkout.get("claim_boundary", "")),
            },
            "git_clean_clone": {
                "status": str(git_clean_clone.get("status", "missing")),
                "contract_pass": git_clean_clone_ready,
                "executed": bool(git_clean_clone.get("git_clean_clone_executed") is True),
                "required_input_count": len(required_git_clean_clone_inputs),
                "blocker_count": len(git_clean_clone_blockers),
                "blocker_counts": _blocker_counts(git_clean_clone_blockers),
                "blockers": git_clean_clone_blockers,
                "claim_boundary": str(git_clean_clone.get("claim_boundary", "")),
            },
            "release_control_cleanup": {
                "status": str(release_control_cleanup_plan.get("status", "missing")),
                "contract_pass": bool(release_control_cleanup_plan.get("contract_pass") is True),
                "human_git_action_required": bool(
                    release_control_cleanup_plan.get("human_git_action_required") is True
                ),
                "candidate_release_control_commit_set_count": int(
                    release_control_cleanup_plan.get(
                        "candidate_release_control_commit_set_count",
                        0,
                    )
                    or 0
                ),
                "recommended_action_counts": (
                    release_control_cleanup_plan.get("recommended_action_counts")
                    if isinstance(
                        release_control_cleanup_plan.get("recommended_action_counts"),
                        dict,
                    )
                    else {}
                ),
                "human_handoff_next_action": (
                    release_control_cleanup_plan.get("human_handoff", {}).get("next_action")
                    if isinstance(release_control_cleanup_plan.get("human_handoff"), dict)
                    else ""
                ),
                "next_verification_commands": list(
                    release_control_cleanup_plan.get("next_verification_commands", [])
                ),
                "claim_boundary": str(release_control_cleanup_plan.get("claim_boundary", "")),
            },
            "required_commands": [
                "python3 scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
                "python3 scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
                "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
            ],
            "owner_action": (
                "Review and commit or intentionally remove every required git-clean-clone "
                "input change, ensure the missing required path is tracked or removed from "
                "the contract, then rerun the git clean-clone reproduction receipt."
            ),
            "claim_boundary": (
                "This handoff records why clean-checkout RC promotion is blocked. It does "
                "not commit changes, prove Linux/Windows parity, or close full Phase 3."
            ),
        },
        "final_gate_blockers": final_gate_blockers,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("pyproject.toml"),
                Path("setup.cfg"),
                PHASE1_CORE_API,
                DEVELOPER_PREVIEW_READINESS,
                DATASET_LICENSE_MANIFEST,
                GAP_LEDGER_EVIDENCE_AUDIT,
                PHASE3_FACTORY_SUMMARY,
                PHASE3_FACTORY_SCORECARD,
                PHASE3_ACQUISITION_PLAN,
                PHASE3_REPRO_BUNDLE,
                PHASE3_CLEAN_CHECKOUT,
                PHASE3_GIT_CLEAN_CLONE,
                PHASE3_RELEASE_CONTROL_CLEANUP_PLAN,
                PHASE6_LINUX_WINDOWS_PARITY_STATUS,
                PHASE6_SILENT_IMPORT_LOSS_STATUS,
                PHASE6_BENCHMARK_SCALE_STATUS,
                PHASE6_UX_OBSERVATION_STATUS,
                PHASE6_CLEAN_CHECKOUT_STATUS,
                PHASE3_IFC_IMPORT_HEALTH,
                PHASE3_IFC_CLEAN_ACQUISITION,
                PHASE3_IFC_DIRTY_ACQUISITION,
                PHASE3_IFC_SOURCE_LICENSE,
                PHASE5_GUI_WORKFLOW,
                PHASE4_IMPORT_TEMPLATE,
                EVIDENCE_CONSOLE_SCOPE,
                UX_OBSERVATION,
                UX_OBSERVATION_INTAKE,
            ],
            reused_evidence=True,
            reuse_policy="rc_status_aggregates_existing_phase1_phase3_phase4_preview_receipts",
            repo_root=repo_root,
        ),
        "status": "ready" if rc_ready else "blocked",
        "contract_pass": rc_ready,
        "developer_preview_release_candidate_ready": rc_ready,
        "developer_preview_release_candidate_claim": rc_ready,
        "developer_preview_ready": bool(preview.get("developer_preview_ready") is True),
        "deliverable_count": len(deliverables),
        "deliverable_pass_count": sum(1 for row in deliverables if row["contract_pass"] is True),
        "final_gate_count": len(final_gates),
        "final_gate_pass_count": sum(1 for row in final_gates if row["contract_pass"] is True),
        "deliverables": deliverables,
        "final_gates": final_gates,
        "known_limitations": known_limitations,
        "future_commercial_gates": future_commercial_gates,
        "blockers": [*deliverable_blockers, *final_gate_blockers],
        "claim_boundary": (
            "This receipt aggregates Developer Preview RC deliverables and final gates "
            "from existing evidence only. It does not close Commercial Release, full "
            "Phase 3 corpus, G1 full nonlinear full-mesh/material Newton, Linux/Windows "
            "parity, external benchmark, customer shadow, license, SLA, or external "
            "approval gates. Remote GitHub sync/push approval remains a release-publication "
            "handoff, while clean-checkout reproducibility is tracked separately."
        ),
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value, (*path, key))
            for key, value in payload.items()
            if key not in {"generated_at"}
            and not (path == () and key == "source_commit_sha")
        }
    if isinstance(payload, list):
        return [_strip_volatile(item, path) for item in payload]
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    known_limitations = _as_dict(payload.get("known_limitations"))
    closure_visibility = _as_dict(
        known_limitations.get("gap_ledger_closure_requirement_visibility")
    )
    failed_requirement_ids = [
        str(item)
        for item in _as_list(closure_visibility.get("nonclosed_failed_closure_requirement_ids"))
        if str(item)
    ]
    lines = [
        "# Developer Preview RC Status",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `developer_preview_release_candidate_ready`: "
        f"`{payload['developer_preview_release_candidate_ready']}`",
        f"- `deliverables`: `{payload['deliverable_pass_count']}/{payload['deliverable_count']}`",
        f"- `final_gates`: `{payload['final_gate_pass_count']}/{payload['final_gate_count']}`",
        "",
        "## Deliverables",
        "",
        "| Item | Status | Pass |",
        "|---|---|---|",
    ]
    for row in payload["deliverables"]:
        lines.append(f"| `{row['item']}` | `{row['status']}` | `{row['contract_pass']}` |")
    lines.extend(["", "## Final Gates", "", "| Item | Status | Pass |", "|---|---|---|"])
    for row in payload["final_gates"]:
        lines.append(f"| `{row['item']}` | `{row['status']}` | `{row['contract_pass']}` |")
    lines.extend(
        [
            "",
            "## Known Limitation Closure Requirements",
            "",
            f"- `source_status`: `{closure_visibility.get('source_status', 'missing')}`",
            f"- `source_full_gap_ledger_ready`: `{closure_visibility.get('source_full_gap_ledger_ready', False)}`",
            f"- `closure_requirements`: `{closure_visibility.get('closure_requirement_pass_count', 0)}/"
            f"{closure_visibility.get('closure_requirement_count', 0)}`",
            f"- `failed_closure_requirements`: `{closure_visibility.get('closure_requirement_fail_count', 0)}`",
            f"- `nonclosed_rows_with_failed_closure_requirements`: "
            f"`{closure_visibility.get('nonclosed_rows_with_failed_closure_requirements_count', 0)}`",
        ]
    )
    if failed_requirement_ids:
        lines.extend(["", "Failed requirement IDs:"])
        lines.extend(f"- `{item}`" for item in failed_requirement_ids)
    if closure_visibility.get("claim_boundary"):
        lines.extend(["", str(closure_visibility.get("claim_boundary"))])
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def check_developer_preview_rc_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    out_md_path: Path = DEFAULT_OUT_MD,
) -> tuple[bool, str]:
    resolved_out = out_path if out_path.is_absolute() else repo_root / out_path
    resolved_md = out_md_path if out_md_path.is_absolute() else repo_root / out_md_path
    if not resolved_out.exists():
        return False, f"developer_preview_rc_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved_out.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"developer_preview_rc_status_unreadable:{exc.__class__.__name__}"
    expected = build_developer_preview_rc_status(repo_root=repo_root)
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "developer_preview_rc_status_mismatch"
    if not resolved_md.exists():
        return False, f"developer_preview_rc_status_report_missing:{out_md_path.as_posix()}"
    if resolved_md.read_text(encoding="utf-8") != _markdown(expected):
        return False, "developer_preview_rc_status_report_mismatch"
    return True, "developer_preview_rc_status_consistent"


def write_developer_preview_rc_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    out_md_path: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_developer_preview_rc_status(repo_root=repo_root)
    resolved_out = out_path if out_path.is_absolute() else repo_root / out_path
    resolved_md = out_md_path if out_md_path.is_absolute() else repo_root / out_md_path
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_developer_preview_rc_status(
            repo_root=ROOT,
            out_path=args.out,
            out_md_path=args.out_md,
        )
        if not ok:
            print(f"Developer Preview RC status check FAILED: {message}", file=sys.stderr)
            return 2
        print(f"Developer Preview RC status check: {message}")
        return 0
    payload = write_developer_preview_rc_status(
        repo_root=ROOT,
        out_path=args.out,
        out_md_path=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Developer Preview RC status: "
            f"{payload['status']} | deliverables="
            f"{payload['deliverable_pass_count']}/{payload['deliverable_count']} | "
            f"final_gates={payload['final_gate_pass_count']}/{payload['final_gate_count']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
