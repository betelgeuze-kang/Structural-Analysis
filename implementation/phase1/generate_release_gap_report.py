#!/usr/bin/env python3
"""Generate release-based commercialization gap report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np

from implementation.phase1.chart_theme import (
    ACCENT,
    ACCENT_WARM,
    DANGER,
    MUTED,
    SUCCESS,
    WARNING,
    add_badge,
    add_figure_header,
    apply_analysis_axis_style,
    configure_analysis_chart_defaults,
    empty_state_figure,
    save_analysis_figure,
)
from implementation.phase1.panel_zone_external_validation import (
    build_panel_zone_external_validation_local_closure_surface,
    build_panel_zone_external_validation_provenance_surface,
    build_panel_zone_external_validation_required_evidence,
    build_panel_zone_external_validation_summary_line,
    normalize_panel_zone_external_validation_status_label,
    panel_zone_external_validation_artifact_closed,
)


FOUNDATION_KEYWORDS = {
    "foundation",
    "mat",
    "raft",
    "pile",
    "caisson",
    "pilecap",
    "pile_cap",
    "footing",
    "ground",
}
REQUIRED_PANEL_ZONE_SOURCES = (
    "panel_zone_joint_geometry_3d",
    "panel_zone_rebar_anchorage_3d",
    "panel_zone_clash_verification_3d",
)

CONSTITUTIVE_INTERACTION_NOTE = (
    "material and steel/composite constitutive gates are surfaced explicitly as shared summary lines across the "
    "release, committee, and external reports; closed supporting gates such as the load-combination engine remain "
    "visible as evidence when present."
)

DEFAULT_NATIVE_AUTHORING_WORKSPACE_SUMMARY = Path(
    "implementation/phase1/release/authoring/native_authoring_workspace_summary.json"
)
DEFAULT_NATIVE_AUTHORING_FAMILY_TRACKS = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_family_tracks.json"
)
DEFAULT_NATIVE_AUTHORING_RUNTIME_SUBMISSION_LANE = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_runtime_submission_lane.json"
)
DEFAULT_NATIVE_AUTHORING_RUNTIME_WRITEBACK_DEPTH_REPORT = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_runtime_writeback_depth_report.json"
)
DEFAULT_NATIVE_AUTHORING_LOCAL_RUNTIME_SCENARIO_DEPTH_REPORT = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_local_runtime_scenario_depth_report.json"
)
DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_local_variant_writeback_trace_report.json"
)
DEFAULT_NATIVE_AUTHORING_MULTI_PROJECT_RUNTIME_WRITEBACK_REPORT = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_multi_project_runtime_writeback_report.json"
)
DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json"
)
DEFAULT_NATIVE_AUTHORING_FAMILY_CORPUS_MANIFEST = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_family_corpus_manifest.json"
)
DEFAULT_NATIVE_AUTHORING_FAMILY_LOCAL_EVIDENCE_MANIFEST = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_family_local_evidence_manifest.json"
)
DEFAULT_NATIVE_AUTHORING_WRITEBACK_BREADTH_REPORT = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_writeback_breadth_report.json"
)
DEFAULT_NATIVE_AUTHORING_SOLVER_FAMILY_BREADTH_REPORT = Path(
    "implementation/phase1/release/authoring/portfolio/native_authoring_solver_family_breadth_report.json"
)
DEFAULT_PROJECT_REGISTRY_PORTFOLIO_WORKSPACE = Path(
    "implementation/phase1/release/project_registry_portfolio_workspace.json"
)
DEFAULT_PROJECT_REGISTRY_INDEX = Path(
    "implementation/phase1/release/project_registry_index.json"
)
DEFAULT_PROJECT_OPS_SERVICE_SNAPSHOT = Path(
    "implementation/phase1/release/project_ops_service_snapshot.json"
)
DEFAULT_MATERIAL_CONSTITUTIVE_GATE_REPORT = Path(
    "implementation/phase1/material_constitutive_gate_report.json"
)
DEFAULT_LOAD_COMBINATION_ENGINE_GATE_REPORT = Path(
    "implementation/phase1/load_combination_engine_gate_report.json"
)
DEFAULT_LOAD_COMBINATION_EDITOR_COMMERCIALIZATION_REPORT = Path(
    "implementation/phase1/release/authoring/load_combination_editor_commercialization_report.json"
)
DEFAULT_ADVANCED_SSI_REPORT = Path("implementation/phase1/advanced_ssi_report.json")
DEFAULT_WIND_WORKFLOW_REPORT = Path("implementation/phase1/wind_workflow_report.json")
DEFAULT_COMMERCIAL_WORKFLOW_BREADTH_REPORT = Path(
    "implementation/phase1/release/commercial_workflow_breadth_report.json"
)
DEFAULT_REFERENCE_REGRESSION_REPORT = Path(
    "implementation/phase1/release/reference_regression/reference_regression_report.json"
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_from_disk(path: str) -> dict:
    report_path = Path(path)
    if not report_path.is_absolute():
        candidate = REPO_ROOT / report_path
        if candidate.exists():
            report_path = candidate
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _pass(report: dict) -> bool:
    if "contract_pass" in report:
        return bool(report.get("contract_pass", False))
    if "all_pass" in report:
        return bool(report.get("all_pass", False))
    if "pass" in report:
        return bool(report.get("pass", False))
    return False


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                continue
    return None


def _first_bool(*values: Any) -> bool | None:
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "false"}:
            return text == "true"
    return None


def _normalize_native_authoring_status(value: Any) -> str:
    token = _status_slug(value, default="")
    if not token:
        return ""
    if token in {
        "pass",
        "passed",
        "ok",
        "success",
        "complete",
        "completed",
        "done",
        "green",
        "release_ready",
        "submission_ready",
        "runtime_ready",
        "writeback_ready",
        "registry_ready",
        "job_ready",
        "full_ready",
    }:
        return "ready"
    if token in {"narrowing", "partial", "partial_ready", "in_progress", "progress"}:
        return "narrowing"
    if token in {"check", "checked", "needs_review", "review"}:
        return "check"
    return token


def _native_authoring_ready_from_value(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _normalize_native_authoring_status(value)
    if normalized == "ready":
        return True
    if normalized:
        return False
    return None


def _normalize_native_authoring_status_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized_parts: list[str] = []
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ":" not in part:
            normalized_token = _normalize_native_authoring_status(part)
            normalized_parts.append(normalized_token or part.lower())
            continue
        family_id, status = part.split(":", 1)
        normalized_status = _normalize_native_authoring_status(status)
        normalized_parts.append(
            f"{family_id.strip()}:{normalized_status or str(status or '').strip().lower()}"
        )
    return ", ".join(normalized_parts)


def _derive_native_authoring_family_status_label(
    rows: list[dict[str, Any]],
    *,
    id_keys: tuple[str, ...],
    status_keys: tuple[str, ...],
    ready_keys: tuple[str, ...],
    fallback_status: str = "check",
    max_items: int = 6,
) -> str:
    labels: list[str] = []
    for row in rows:
        family_id = _first_text(*(row.get(key) for key in id_keys))
        if not family_id:
            continue
        status = ""
        for key in status_keys:
            normalized = _normalize_native_authoring_status(row.get(key))
            if normalized:
                status = normalized
                break
        if not status:
            ready = _first_bool(*(row.get(key) for key in ready_keys))
            if ready is None:
                for key in status_keys:
                    ready = _native_authoring_ready_from_value(row.get(key))
                    if ready is not None:
                        break
            if ready is True:
                status = "ready"
            elif ready is False:
                status = fallback_status
        labels.append(f"{family_id}:{status or fallback_status}")
    return _compact_label(labels, max_items=max_items)


def _count_native_authoring_ready_rows(
    rows: list[dict[str, Any]],
    *,
    status_keys: tuple[str, ...],
    ready_keys: tuple[str, ...],
) -> int:
    ready_count = 0
    for row in rows:
        ready = _first_bool(*(row.get(key) for key in ready_keys))
        if ready is None:
            for key in status_keys:
                ready = _native_authoring_ready_from_value(row.get(key))
                if ready is not None:
                    break
        if ready:
            ready_count += 1
    return ready_count


def _unique_sorted_tokens(values: list[str]) -> list[str]:
    return sorted({str(value or "").strip() for value in values if str(value or "").strip()})


def _authoring_section_family(section_id: Any) -> str:
    normalized = str(section_id or "").strip().lower()
    if not normalized:
        return "unknown"
    if normalized.startswith("steel") or "steel_" in normalized:
        return "steel"
    if (
        normalized.startswith("rc")
        or "concrete" in normalized
        or "wall" in normalized
        or "column" in normalized
    ):
        return "rc"
    if (
        normalized.startswith("cft")
        or normalized.startswith("src")
        or "composite" in normalized
    ):
        return "composite"
    if (
        normalized.startswith("deck")
        or "slab" in normalized
        or "plate" in normalized
    ):
        return "deck/floor"
    return "other"


def _compact_label(values: list[str], max_items: int = 5) -> str:
    normalized = _unique_sorted_tokens(values)
    if not normalized:
        return ""
    if len(normalized) <= max_items:
        return ", ".join(normalized)
    return f"{', '.join(normalized[:max_items])} +{len(normalized) - max_items}"


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _family_id(row: dict[str, Any]) -> str:
    return _first_text(
        row.get("family_id"),
        row.get("authoring_family_id"),
        row.get("submission_id"),
        row.get("project_id"),
    )


def _family_row_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        family_id = _family_id(row)
        if family_id:
            indexed[family_id] = row
    return indexed


def _max_int(*values: Any) -> int:
    parsed_values: list[int] = []
    for value in values:
        parsed = _first_int(value)
        if parsed is not None:
            parsed_values.append(parsed)
    return max(parsed_values, default=0)


def _derive_local_variant_writeback_trace_fallback_rows(
    *,
    portfolio_family_rows: list[dict[str, Any]],
    runtime_submission_rows: list[dict[str, Any]],
    runtime_writeback_depth_rows: list[dict[str, Any]],
    local_runtime_scenario_depth_rows: list[dict[str, Any]],
    solver_family_breadth_rows: list[dict[str, Any]],
    writeback_breadth_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    portfolio_by_family = _family_row_index(portfolio_family_rows)
    runtime_by_family = _family_row_index(runtime_submission_rows)
    runtime_writeback_by_family = _family_row_index(runtime_writeback_depth_rows)
    local_runtime_by_family = _family_row_index(local_runtime_scenario_depth_rows)
    solver_breadth_by_family = _family_row_index(solver_family_breadth_rows)
    writeback_breadth_by_family = _family_row_index(writeback_breadth_rows)
    family_ids = _unique_sorted_tokens(
        [
            *portfolio_by_family.keys(),
            *runtime_by_family.keys(),
            *runtime_writeback_by_family.keys(),
            *local_runtime_by_family.keys(),
            *solver_breadth_by_family.keys(),
            *writeback_breadth_by_family.keys(),
        ]
    )
    emitted_rows: list[dict[str, Any]] = []
    for family_id in family_ids:
        portfolio_row = portfolio_by_family.get(family_id, {})
        runtime_row = runtime_by_family.get(family_id, {})
        runtime_writeback_row = runtime_writeback_by_family.get(family_id, {})
        local_runtime_row = local_runtime_by_family.get(family_id, {})
        solver_breadth_row = solver_breadth_by_family.get(family_id, {})
        writeback_breadth_row = writeback_breadth_by_family.get(family_id, {})

        workspace_ready = bool(
            _first_bool(
                portfolio_row.get("workspace_ready"),
                portfolio_row.get("runtime_ready"),
                portfolio_row.get("solver_ready"),
                portfolio_row.get("ops_ready"),
                portfolio_row.get("contract_pass"),
            )
        )
        workspace_family_palette_count = _max_int(portfolio_row.get("palette_family_count"))
        workspace_section_palette_count = _max_int(portfolio_row.get("palette_section_count"))
        workspace_active_family_count = _max_int(portfolio_row.get("active_family_count"))
        member_type_count = _max_int(portfolio_row.get("member_type_count"))
        load_pattern_count = _max_int(portfolio_row.get("load_pattern_count"))
        workspace_variant_ready = bool(
            _first_bool(
                portfolio_row.get("workspace_variant_ready"),
                workspace_ready
                and workspace_family_palette_count >= 4
                and workspace_section_palette_count >= 4
                and workspace_active_family_count >= 2
                and member_type_count >= 2
                and load_pattern_count >= 4,
            )
        )

        solver_combo_count = _max_int(
            portfolio_row.get("solver_combo_count"),
            runtime_row.get("solver_combo_count"),
        )
        runtime_case_count = _max_int(
            portfolio_row.get("solver_load_case_count"),
            runtime_row.get("solver_load_case_count"),
        )
        mesh_request_count = _max_int(
            portfolio_row.get("solver_mesh_request_count"),
            runtime_row.get("solver_mesh_request_count"),
        )
        solver_ready = bool(
            _first_bool(
                runtime_row.get("runtime_ready"),
                portfolio_row.get("runtime_ready"),
                portfolio_row.get("solver_ready"),
                solver_breadth_row.get("broad_solver_family_ready"),
                writeback_breadth_row.get("broad_writeback_ready"),
            )
        )
        solver_combo_family_count = _max_int(
            portfolio_row.get("solver_combo_family_count"),
            runtime_row.get("solver_combo_family_count"),
            3 if solver_ready and solver_combo_count >= 12 and runtime_case_count >= 3 and mesh_request_count >= 2 else 0,
        )
        solver_variant_ready = bool(
            _first_bool(
                portfolio_row.get("solver_variant_ready"),
                solver_ready
                and solver_combo_count >= 12
                and runtime_case_count >= 3
                and mesh_request_count >= 2
                and solver_combo_family_count >= 3,
            )
        )

        runtime_writeback_full = bool(
            _first_bool(
                _status_slug(runtime_writeback_row.get("runtime_writeback_depth_status"), default="")
                == "full",
                runtime_writeback_row.get("signature_verified"),
            )
        )
        registry_ready = bool(
            _first_bool(
                portfolio_row.get("registry_ready"),
                runtime_row.get("writeback_ready"),
                runtime_writeback_full,
            )
        )
        signature_verified = bool(
            _first_bool(
                portfolio_row.get("signature_verified"),
                runtime_writeback_row.get("signature_verified"),
            )
        )
        package_bytes = _max_int(portfolio_row.get("package_bytes"))
        package_ready = bool(
            _first_bool(
                portfolio_row.get("package_ready"),
                package_bytes > 0,
            )
        )
        snapshot_count = _max_int(portfolio_row.get("snapshot_count"))
        approval_count = _max_int(portfolio_row.get("approval_count"))
        snapshot_ready = bool(
            _first_bool(
                runtime_writeback_row.get("snapshot_ready"),
                snapshot_count > 0,
            )
        )
        writeback_trace_ready = bool(
            _first_bool(
                portfolio_row.get("writeback_trace_ready"),
                registry_ready
                and signature_verified
                and approval_count > 0
                and snapshot_ready
                and package_ready,
            )
        )
        omitted_library_combination_count = _max_int(
            local_runtime_row.get("omitted_library_combination_count"),
        )
        partial_ready = any(
            (
                workspace_ready,
                workspace_variant_ready,
                solver_ready,
                solver_variant_ready,
                writeback_trace_ready,
                registry_ready,
                signature_verified,
                approval_count > 0,
                snapshot_ready,
                package_ready,
            )
        )
        depth_status = "deep" if (
            workspace_variant_ready and solver_variant_ready and writeback_trace_ready
        ) else "targeted" if partial_ready else "check"
        emitted_rows.append(
            {
                "family_id": family_id,
                "local_variant_writeback_trace_status": depth_status,
                "workspace_variant_ready": workspace_variant_ready,
                "solver_variant_ready": solver_variant_ready,
                "writeback_trace_ready": writeback_trace_ready,
                "workspace_active_family_count": workspace_active_family_count,
                "solver_combo_family_count": solver_combo_family_count,
                "signature_verified": signature_verified,
                "omitted_library_combination_count": omitted_library_combination_count,
            }
        )
    return emitted_rows


def _status_slug(value: Any, default: str = "holdout") -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return token or default


def _markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def _markdown_table_lines(rows: list[dict[str, Any]], limit: int = 20) -> list[str]:
    if not rows:
        return []
    header_keys: list[str] = []
    for row in rows:
        for key in row.keys():
            label = str(key or "").strip()
            if label and label not in header_keys:
                header_keys.append(label)
    if not header_keys:
        return []
    table_lines = [
        f"| {' | '.join(_markdown_cell(key) for key in header_keys)} |",
        f"| {' | '.join('---' for _ in header_keys)} |",
    ]
    for row in rows[:limit]:
        table_lines.append(
            f"| {' | '.join(_markdown_cell(row.get(key, '')) for key in header_keys)} |"
        )
    return table_lines


def _commercial_workflow_breadth_surface(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    artifact_links = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    rows = _dict_rows(report.get("rows"))
    construction_stage_ready = bool(_first_bool(summary.get("construction_stage_ready")) or False)
    rail_tunnel_ready = bool(_first_bool(summary.get("rail_tunnel_ready")) or False)
    design_redesign_loop_ready = bool(
        _first_bool(summary.get("design_redesign_loop_ready")) or False
    )
    construction_stage_history_snapshot_count = int(
        _first_int(summary.get("construction_stage_history_snapshot_count")) or 0
    )
    construction_stage_max_differential_shortening_mm = float(
        _finite(summary.get("construction_stage_max_differential_shortening_mm"))
    )
    rail_tunnel_serviceability_status = str(
        _first_text(summary.get("rail_tunnel_serviceability_status"), "unknown")
    )
    rail_tunnel_maintenance_priority = str(
        _first_text(summary.get("rail_tunnel_maintenance_priority"), "unknown")
    )
    rail_tunnel_recommended_action_count = int(
        _first_int(summary.get("rail_tunnel_recommended_action_count")) or 0
    )
    design_report_traceability_ratio = float(
        _finite(summary.get("design_report_traceability_ratio"))
    )
    design_report_ng_member_count = int(
        _first_int(summary.get("design_report_ng_member_count")) or 0
    )
    section_optimizer_suggestion_count = int(
        _first_int(summary.get("section_optimizer_suggestion_count")) or 0
    )
    section_optimizer_strengthen_count = int(
        _first_int(summary.get("section_optimizer_strengthen_count")) or 0
    )
    section_optimizer_reduce_count = int(
        _first_int(summary.get("section_optimizer_reduce_count")) or 0
    )
    governing_clause_count = int(_first_int(summary.get("governing_clause_count")) or 0)
    ready_surface_count = sum(
        [
            construction_stage_ready,
            rail_tunnel_ready,
            design_redesign_loop_ready,
        ]
    )
    total_surface_count = 3
    gap_status = (
        "closed"
        if ready_surface_count >= total_surface_count
        else "narrowing"
        if ready_surface_count > 0
        else "open"
    )
    summary_line = str(report.get("summary_line", "") or "").strip()
    pass_value = _first_bool(
        checks.get("pass"),
        report.get("contract_pass"),
        report.get("all_pass"),
        report.get("pass"),
    )
    surface_attached = bool(summary_line or summary or checks or artifact_links or rows)
    detail_label = (
        f"construction_stage_ready={construction_stage_ready}"
        f"(history_snapshots={construction_stage_history_snapshot_count},"
        f"max_diff_shortening_mm={construction_stage_max_differential_shortening_mm:.3f}) | "
        f"rail_tunnel_ready={rail_tunnel_ready}"
        f"(serviceability={rail_tunnel_serviceability_status},"
        f"maintenance_priority={rail_tunnel_maintenance_priority},"
        f"recommended_actions={rail_tunnel_recommended_action_count}) | "
        f"design_redesign_loop_ready={design_redesign_loop_ready}"
        f"(traceability_ratio={design_report_traceability_ratio:.3f},"
        f"ng_members={design_report_ng_member_count},"
        f"suggestions={section_optimizer_suggestion_count},"
        f"strengthen={section_optimizer_strengthen_count},"
        f"reduce={section_optimizer_reduce_count},"
        f"governing_clauses={governing_clause_count})"
    )
    return {
        "commercial_workflow_breadth_surface_attached": surface_attached,
        "commercial_workflow_breadth_summary_line": summary_line,
        "commercial_workflow_breadth_pass": bool(pass_value) if pass_value is not None else False,
        "commercial_workflow_breadth_report_path": str(report_path),
        "commercial_workflow_breadth_ready_surface_count": int(ready_surface_count),
        "commercial_workflow_breadth_total_surface_count": int(total_surface_count),
        "commercial_workflow_breadth_gap_status": gap_status,
        "commercial_workflow_breadth_detail_label": detail_label,
        "commercial_workflow_breadth_evidence": (
            f"pass={bool(pass_value) if pass_value is not None else False}, "
            f"ready_surfaces={ready_surface_count}/{total_surface_count}, "
            f"{detail_label}"
        ),
        "commercial_workflow_breadth_summary": {
            "construction_stage_ready": construction_stage_ready,
            "construction_stage_history_snapshot_count": construction_stage_history_snapshot_count,
            "construction_stage_max_differential_shortening_mm": construction_stage_max_differential_shortening_mm,
            "rail_tunnel_ready": rail_tunnel_ready,
            "rail_tunnel_serviceability_status": rail_tunnel_serviceability_status,
            "rail_tunnel_maintenance_priority": rail_tunnel_maintenance_priority,
            "rail_tunnel_recommended_action_count": rail_tunnel_recommended_action_count,
            "design_redesign_loop_ready": design_redesign_loop_ready,
            "design_report_traceability_ratio": design_report_traceability_ratio,
            "design_report_ng_member_count": design_report_ng_member_count,
            "section_optimizer_suggestion_count": section_optimizer_suggestion_count,
            "section_optimizer_strengthen_count": section_optimizer_strengthen_count,
            "section_optimizer_reduce_count": section_optimizer_reduce_count,
            "governing_clause_count": governing_clause_count,
        },
        "commercial_workflow_breadth_artifact_links": artifact_links,
        "commercial_workflow_breadth_rows": rows,
    }


def _normalize_advanced_holdout(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    holdout_id = str(normalized.get("id", "") or "").strip()
    ready = bool(normalized.get("ready", False))
    status = "closed" if ready else "open"
    mode = str(normalized.get("mode", "") or "").strip()
    reason = str(normalized.get("reason", "") or "").strip()
    title = str(normalized.get("title", normalized.get("id", "")) or "").strip()
    existing_status_label = str(normalized.get("status_label", "") or "").strip()
    existing_closure_label = str(normalized.get("closure_label", "") or "").strip()
    fallback_label = f"{status}_{_status_slug(mode or existing_status_label or title)}"
    status_label = existing_status_label or existing_closure_label or fallback_label
    closure_label = existing_closure_label or status_label
    why_it_remains = str(normalized.get("why_it_remains", "") or "").strip()
    if not why_it_remains:
        if ready:
            why_it_remains = (
                f"Closed in the current commercialization surface: {reason or f'{title} evidence is attached.'}"
            )
        else:
            why_it_remains = reason or (
                f"{title} remains open in the current commercialization surface."
            )
    exit_criteria = str(normalized.get("exit_criteria", "") or "").strip()
    if not exit_criteria:
        if ready:
            ready_mode = (
                mode
                or ("recomputed_member_local_hinge_state" if holdout_id == "pbd_dynamic_hinge_refresh" else "current_mode")
            )
            exit_criteria = (
                f"Keep `{ready_mode}` evidence attached and stable across release artifacts."
            )
        else:
            exit_criteria = (
                f"Attach deterministic `{mode or 'current_mode'}` evidence so this advanced holdout can close."
            )
    next_step = str(normalized.get("next_step", "") or "").strip()
    if not next_step:
        next_step = (
            "Monitor this closed holdout for regressions in the next release pass."
            if ready
            else "Generate the missing commercialization artifact and rerun the release gap report."
        )
    normalized.update(
        {
            "status": status,
            "status_label": status_label,
            "closure_label": closure_label,
            "why_it_remains": why_it_remains,
            "exit_criteria": exit_criteria,
            "next_step": next_step,
        }
    )
    return normalized


def _native_authoring_lane_surface(
    solver_session_report: dict[str, Any],
    ops_bundle_report: dict[str, Any],
    *,
    workspace_summary_report: dict[str, Any] | None = None,
    portfolio_report: dict[str, Any] | None = None,
    family_corpus_manifest_report: dict[str, Any] | None = None,
    family_local_evidence_manifest_report: dict[str, Any] | None = None,
    family_tracks_report: dict[str, Any] | None = None,
    runtime_submission_report: dict[str, Any] | None = None,
    runtime_writeback_depth_report: dict[str, Any] | None = None,
    local_runtime_scenario_depth_report: dict[str, Any] | None = None,
    local_variant_writeback_trace_report: dict[str, Any] | None = None,
    multi_project_runtime_writeback_report: dict[str, Any] | None = None,
    solver_family_breadth_report: dict[str, Any] | None = None,
    writeback_breadth_report: dict[str, Any] | None = None,
    project_ops_service_snapshot_report: dict[str, Any] | None = None,
    solver_session_path: Path,
    ops_bundle_path: Path,
    workspace_summary_path: Path | None = None,
    portfolio_path: Path | None = None,
    family_corpus_manifest_path: Path | None = None,
    family_local_evidence_manifest_path: Path | None = None,
    family_tracks_path: Path | None = None,
    runtime_submission_path: Path | None = None,
    runtime_writeback_depth_path: Path | None = None,
    local_runtime_scenario_depth_path: Path | None = None,
    local_variant_writeback_trace_path: Path | None = None,
    multi_project_runtime_writeback_path: Path | None = None,
    solver_family_breadth_path: Path | None = None,
    writeback_breadth_path: Path | None = None,
    project_ops_service_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    workspace_report = workspace_summary_report if isinstance(workspace_summary_report, dict) else {}
    portfolio_report = portfolio_report if isinstance(portfolio_report, dict) else {}
    native_authoring_family_corpus_manifest = (
        family_corpus_manifest_report if isinstance(family_corpus_manifest_report, dict) else {}
    )
    native_authoring_family_local_evidence_manifest = (
        family_local_evidence_manifest_report
        if isinstance(family_local_evidence_manifest_report, dict)
        else {}
    )
    family_tracks_report = family_tracks_report if isinstance(family_tracks_report, dict) else {}
    runtime_submission_report = (
        runtime_submission_report if isinstance(runtime_submission_report, dict) else {}
    )
    runtime_writeback_depth_report = (
        runtime_writeback_depth_report if isinstance(runtime_writeback_depth_report, dict) else {}
    )
    local_runtime_scenario_depth_report = (
        local_runtime_scenario_depth_report
        if isinstance(local_runtime_scenario_depth_report, dict)
        else {}
    )
    local_variant_writeback_trace_report = (
        local_variant_writeback_trace_report
        if isinstance(local_variant_writeback_trace_report, dict)
        else {}
    )
    multi_project_runtime_writeback_report = (
        multi_project_runtime_writeback_report
        if isinstance(multi_project_runtime_writeback_report, dict)
        else {}
    )
    solver_family_breadth_report = (
        solver_family_breadth_report if isinstance(solver_family_breadth_report, dict) else {}
    )
    writeback_breadth_report = writeback_breadth_report if isinstance(writeback_breadth_report, dict) else {}
    project_ops_service_snapshot_report = (
        project_ops_service_snapshot_report
        if isinstance(project_ops_service_snapshot_report, dict)
        else {}
    )
    workspace_summary_payload = (
        workspace_report.get("summary") if isinstance(workspace_report.get("summary"), dict) else {}
    )
    workspace_editor_controls = (
        workspace_report.get("editor_controls") if isinstance(workspace_report.get("editor_controls"), dict) else {}
    )
    solver_summary = (
        solver_session_report.get("summary") if isinstance(solver_session_report.get("summary"), dict) else {}
    )
    solver_authoring_summary = (
        solver_session_report.get("authoring_summary")
        if isinstance(solver_session_report.get("authoring_summary"), dict)
        else {}
    )
    solver_mesh_session = (
        solver_session_report.get("mesh_session") if isinstance(solver_session_report.get("mesh_session"), dict) else {}
    )
    load_combination_session = (
        solver_session_report.get("load_combination_session")
        if isinstance(solver_session_report.get("load_combination_session"), dict)
        else {}
    )
    runtime_summary = (
        load_combination_session.get("runtime_summary")
        if isinstance(load_combination_session.get("runtime_summary"), dict)
        else {}
    )
    solver_artifacts = (
        solver_session_report.get("artifacts") if isinstance(solver_session_report.get("artifacts"), dict) else {}
    )
    ops_summary = ops_bundle_report.get("summary") if isinstance(ops_bundle_report.get("summary"), dict) else {}
    ops_checks = ops_bundle_report.get("checks") if isinstance(ops_bundle_report.get("checks"), dict) else {}
    ops_inputs = ops_bundle_report.get("inputs") if isinstance(ops_bundle_report.get("inputs"), dict) else {}
    ops_artifacts = ops_bundle_report.get("artifacts") if isinstance(ops_bundle_report.get("artifacts"), dict) else {}
    batch_job_report_summary = (
        ops_bundle_report.get("batch_job_report_summary")
        if isinstance(ops_bundle_report.get("batch_job_report_summary"), dict)
        else {}
    )
    project_registry_summary = (
        ops_bundle_report.get("project_registry_summary")
        if isinstance(ops_bundle_report.get("project_registry_summary"), dict)
        else {}
    )
    portfolio_summary = (
        portfolio_report.get("summary") if isinstance(portfolio_report.get("summary"), dict) else {}
    )
    portfolio_scan = (
        portfolio_report.get("scan") if isinstance(portfolio_report.get("scan"), dict) else {}
    )
    portfolio_scan_summary = (
        portfolio_scan.get("summary") if isinstance(portfolio_scan.get("summary"), dict) else {}
    )
    portfolio_artifacts = (
        portfolio_report.get("artifacts") if isinstance(portfolio_report.get("artifacts"), dict) else {}
    )
    portfolio_family_rows = _dict_rows(portfolio_report.get("family_rows"))
    family_tracks_summary = (
        family_tracks_report.get("summary") if isinstance(family_tracks_report.get("summary"), dict) else {}
    )
    family_tracks_artifacts = (
        family_tracks_report.get("artifacts") if isinstance(family_tracks_report.get("artifacts"), dict) else {}
    )
    family_track_rows = _dict_rows(family_tracks_report.get("family_rows"))
    if not family_track_rows:
        family_track_rows = _dict_rows(family_tracks_report.get("tracks"))
    runtime_submission_summary = (
        runtime_submission_report.get("summary")
        if isinstance(runtime_submission_report.get("summary"), dict)
        else {}
    )
    runtime_submission_artifacts = (
        runtime_submission_report.get("artifacts")
        if isinstance(runtime_submission_report.get("artifacts"), dict)
        else {}
    )
    runtime_submission_rows = _dict_rows(runtime_submission_report.get("submission_rows"))
    if not runtime_submission_rows:
        runtime_submission_rows = _dict_rows(runtime_submission_report.get("family_rows"))
    if not runtime_submission_rows:
        runtime_submission_rows = _dict_rows(runtime_submission_report.get("rows"))
    runtime_writeback_depth_summary = (
        runtime_writeback_depth_report.get("summary")
        if isinstance(runtime_writeback_depth_report.get("summary"), dict)
        else {}
    )
    runtime_writeback_depth_artifacts = (
        runtime_writeback_depth_report.get("artifacts")
        if isinstance(runtime_writeback_depth_report.get("artifacts"), dict)
        else {}
    )
    runtime_writeback_depth_rows = _dict_rows(runtime_writeback_depth_report.get("family_rows"))
    local_runtime_scenario_depth_summary = (
        local_runtime_scenario_depth_report.get("summary")
        if isinstance(local_runtime_scenario_depth_report.get("summary"), dict)
        else {}
    )
    local_runtime_scenario_depth_artifacts = (
        local_runtime_scenario_depth_report.get("artifacts")
        if isinstance(local_runtime_scenario_depth_report.get("artifacts"), dict)
        else {}
    )
    local_runtime_scenario_depth_rows = _dict_rows(
        local_runtime_scenario_depth_report.get("family_rows")
    )
    local_variant_writeback_trace_summary = (
        local_variant_writeback_trace_report.get("summary")
        if isinstance(local_variant_writeback_trace_report.get("summary"), dict)
        else {}
    )
    if not local_variant_writeback_trace_summary:
        local_variant_writeback_trace_summary = (
            portfolio_report.get("local_variant_writeback_trace_summary")
            if isinstance(portfolio_report.get("local_variant_writeback_trace_summary"), dict)
            else {}
        )
    local_variant_writeback_trace_artifacts = (
        local_variant_writeback_trace_report.get("artifacts")
        if isinstance(local_variant_writeback_trace_report.get("artifacts"), dict)
        else {}
    )
    local_variant_writeback_trace_rows = _dict_rows(
        local_variant_writeback_trace_report.get("family_rows")
    )
    if not local_variant_writeback_trace_rows and portfolio_family_rows:
        local_variant_writeback_trace_rows = _derive_local_variant_writeback_trace_fallback_rows(
            portfolio_family_rows=portfolio_family_rows,
            runtime_submission_rows=runtime_submission_rows,
            runtime_writeback_depth_rows=runtime_writeback_depth_rows,
            local_runtime_scenario_depth_rows=local_runtime_scenario_depth_rows,
            solver_family_breadth_rows=[],
            writeback_breadth_rows=[],
        )
    multi_project_runtime_writeback_summary = (
        multi_project_runtime_writeback_report.get("summary")
        if isinstance(multi_project_runtime_writeback_report.get("summary"), dict)
        else {}
    )
    multi_project_runtime_writeback_artifacts = (
        multi_project_runtime_writeback_report.get("artifacts")
        if isinstance(multi_project_runtime_writeback_report.get("artifacts"), dict)
        else {}
    )
    multi_project_runtime_writeback_project_rows = _dict_rows(
        multi_project_runtime_writeback_report.get("project_rows")
    )
    multi_project_runtime_writeback_project_family_rows = _dict_rows(
        multi_project_runtime_writeback_report.get("project_family_rows")
    )
    solver_family_breadth_summary = (
        solver_family_breadth_report.get("summary")
        if isinstance(solver_family_breadth_report.get("summary"), dict)
        else {}
    )
    solver_family_breadth_artifacts = (
        solver_family_breadth_report.get("artifacts")
        if isinstance(solver_family_breadth_report.get("artifacts"), dict)
        else {}
    )
    solver_family_breadth_rows = _dict_rows(solver_family_breadth_report.get("family_rows"))
    writeback_breadth_summary = (
        writeback_breadth_report.get("summary")
        if isinstance(writeback_breadth_report.get("summary"), dict)
        else {}
    )
    writeback_breadth_artifacts = (
        writeback_breadth_report.get("artifacts")
        if isinstance(writeback_breadth_report.get("artifacts"), dict)
        else {}
    )
    writeback_breadth_rows = _dict_rows(writeback_breadth_report.get("family_rows"))
    project_ops_service_summary = (
        project_ops_service_snapshot_report.get("summary")
        if isinstance(project_ops_service_snapshot_report.get("summary"), dict)
        else {}
    )
    project_ops_service_artifacts = (
        project_ops_service_snapshot_report.get("artifacts")
        if isinstance(project_ops_service_snapshot_report.get("artifacts"), dict)
        else {}
    )
    project_ops_service_paths = (
        project_ops_service_snapshot_report.get("paths")
        if isinstance(project_ops_service_snapshot_report.get("paths"), dict)
        else {}
    )
    project_ops_service_projects = _dict_rows(project_ops_service_snapshot_report.get("project_rows"))
    project_ops_service_families = _dict_rows(project_ops_service_snapshot_report.get("family_rows"))
    project_ops_service_endpoints = _dict_rows(project_ops_service_snapshot_report.get("endpoint_rows"))

    section_palette = [
        str(value).strip()
        for value in (
            solver_session_report.get("authoring_controls", {}).get("section_palette", [])
            if isinstance(solver_session_report.get("authoring_controls"), dict)
            else []
        )
        if str(value or "").strip()
    ]
    if not section_palette:
        section_palette = [
            str(value).strip()
            for value in (workspace_editor_controls.get("section_palette") or [])
            if str(value or "").strip()
        ]
    active_section_counts = (
        solver_authoring_summary.get("section_usage_counts")
        if isinstance(solver_authoring_summary.get("section_usage_counts"), dict)
        else workspace_summary_payload.get("section_usage_counts")
        if isinstance(workspace_summary_payload.get("section_usage_counts"), dict)
        else {}
    )
    active_section_ids = [str(key).strip() for key in active_section_counts.keys() if str(key or "").strip()]
    palette_families = _unique_sorted_tokens([_authoring_section_family(section_id) for section_id in section_palette])
    active_families = _unique_sorted_tokens([_authoring_section_family(section_id) for section_id in active_section_ids])
    member_type_counts = (
        solver_authoring_summary.get("member_type_counts")
        if isinstance(solver_authoring_summary.get("member_type_counts"), dict)
        else workspace_summary_payload.get("member_type_counts")
        if isinstance(workspace_summary_payload.get("member_type_counts"), dict)
        else {}
    )
    member_types = _unique_sorted_tokens([str(key).strip() for key in member_type_counts.keys() if str(key or "").strip()])

    solver_summary_line = _first_text(solver_session_report.get("summary_line"))
    ops_summary_line = _first_text(ops_bundle_report.get("summary_line"))
    workspace_summary_line = _first_text(
        workspace_report.get("summary_line"),
        workspace_summary_payload.get("summary_line"),
        solver_authoring_summary.get("summary_line"),
    )
    solver_session_pass = bool(_pass(solver_session_report))
    solver_session_authoring_ready = bool(
        _first_bool(
            solver_summary.get("session_ready"),
            runtime_summary.get("authoring_ready"),
            solver_authoring_summary.get("native_authoring_ready"),
            solver_session_pass,
        )
    )
    ops_bundle_pass = bool(_pass(ops_bundle_report))
    ops_bundle_workspace_ready_pass = bool(ops_checks.get("workspace_summary_ready_pass", False))
    ops_bundle_signature_verified = bool(
        ops_checks.get("project_registry_signature_verified_pass", False)
    )
    native_authoring_lane_ready = bool(
        solver_session_pass
        and solver_session_authoring_ready
        and ops_bundle_pass
        and ops_bundle_workspace_ready_pass
        and ops_bundle_signature_verified
    )
    native_authoring_evidence_attached = any(
        (
            solver_session_pass,
            ops_bundle_pass,
            bool(solver_summary_line),
            bool(ops_summary_line),
            bool(solver_artifacts),
            bool(ops_artifacts),
        )
    )
    native_authoring_commercialization_status = "missing"
    if native_authoring_lane_ready:
        native_authoring_commercialization_status = "ready"
    elif native_authoring_evidence_attached:
        native_authoring_commercialization_status = "narrowing"

    solver_session_mesh_request_count = (
        _first_int(
            solver_summary.get("mesh_request_count"),
            solver_mesh_session.get("request_count"),
        )
        or 0
    )
    solver_session_total_estimated_cells = _first_int(
        solver_mesh_session.get("total_estimated_cells"),
    ) or 0
    solver_session_combo_count = _first_int(
        solver_summary.get("combo_count"),
        runtime_summary.get("combo_count"),
    ) or 0
    solver_session_load_case_count = _first_int(
        solver_summary.get("load_case_count"),
        runtime_summary.get("runtime_case_count"),
    ) or 0
    solver_session_loadcomb_line_count = _first_int(
        solver_summary.get("loadcomb_line_count"),
        load_combination_session.get("loadcomb_preview_line_count"),
    ) or 0
    ops_bundle_job_count = _first_int(
        ops_summary.get("job_count"),
        batch_job_report_summary.get("job_count"),
    ) or 0
    ops_bundle_snapshot_count = _first_int(
        ops_summary.get("snapshot_count"),
        batch_job_report_summary.get("snapshot_count"),
    ) or 0
    ops_bundle_registry_artifact_count = _first_int(
        ops_summary.get("registry_artifact_count"),
        project_registry_summary.get("artifact_count"),
    ) or 0
    ops_bundle_registry_approval_count = _first_int(
        ops_summary.get("registry_approval_count"),
        project_registry_summary.get("approval_count"),
    ) or 0
    ops_bundle_registry_package_bytes = _first_int(
        project_registry_summary.get("package_bytes"),
    ) or 0
    native_authoring_portfolio_attached = bool(portfolio_report)
    native_authoring_portfolio_project_count = _first_int(
        portfolio_summary.get("project_count"),
        len(portfolio_report.get("project_rows", [])) if isinstance(portfolio_report.get("project_rows"), list) else 0,
    ) or 0
    native_authoring_portfolio_complete_project_count = _first_int(
        portfolio_summary.get("complete_project_count"),
    ) or 0
    native_authoring_portfolio_signature_verified_count = _first_int(
        portfolio_summary.get("signature_verified_count"),
    ) or 0
    native_authoring_portfolio_package_reproducible_count = _first_int(
        portfolio_summary.get("package_reproducible_count"),
    ) or 0
    native_authoring_portfolio_unmatched_input_count = _first_int(
        portfolio_scan_summary.get("unmatched_input_count"),
    ) or 0
    native_authoring_portfolio_family_count = _first_int(
        portfolio_summary.get("family_count"),
        len(portfolio_family_rows),
    ) or 0
    native_authoring_portfolio_ready_family_count = _first_int(
        portfolio_summary.get("ready_family_count"),
        portfolio_summary.get("release_ready_family_count"),
        portfolio_summary.get("complete_family_count"),
        _count_native_authoring_ready_rows(
            portfolio_family_rows,
            status_keys=("commercialization_status", "reason_code"),
            ready_keys=("release_ready", "runtime_ready", "ops_ready", "contract_pass"),
        ),
    ) or 0
    native_authoring_portfolio_release_ready_family_count = _first_int(
        portfolio_summary.get("release_ready_family_count"),
        native_authoring_portfolio_ready_family_count,
    ) or 0
    native_authoring_portfolio_failed_family_count = max(
        native_authoring_portfolio_family_count - native_authoring_portfolio_ready_family_count,
        0,
    )
    native_authoring_portfolio_max_solver_combo_count = _first_int(
        portfolio_summary.get("max_solver_combo_count"),
        max(
            (
                _first_int(row.get("solver_combo_count"))
                or 0
                for row in portfolio_family_rows
            ),
            default=0,
        ),
        portfolio_summary.get("solver_combo_count"),
    ) or 0
    native_authoring_portfolio_max_solver_mesh_request_count = _first_int(
        portfolio_summary.get("max_solver_mesh_request_count"),
        max(
            (
                _first_int(row.get("solver_mesh_request_count"))
                or 0
                for row in portfolio_family_rows
            ),
            default=0,
        ),
        portfolio_summary.get("solver_mesh_request_count"),
    ) or 0
    native_authoring_portfolio_family_status_label = _first_text(
        _normalize_native_authoring_status_label(portfolio_summary.get("family_status_label")),
        _derive_native_authoring_family_status_label(
            portfolio_family_rows,
            id_keys=("family_id", "authoring_family_id", "project_id"),
            status_keys=("commercialization_status", "reason_code"),
            ready_keys=("release_ready", "runtime_ready", "ops_ready", "contract_pass"),
        ),
    )
    native_authoring_portfolio_summary_line = _first_text(
        portfolio_report.get("summary_line"),
    )
    native_authoring_family_corpus_summary = (
        native_authoring_family_corpus_manifest.get("summary")
        if isinstance(native_authoring_family_corpus_manifest.get("summary"), dict)
        else {}
    )
    native_authoring_family_corpus_attached = bool(native_authoring_family_corpus_manifest)
    native_authoring_family_corpus_summary_line = _first_text(
        native_authoring_family_corpus_manifest.get("summary_line"),
    )
    native_authoring_family_corpus_pass = _pass(native_authoring_family_corpus_manifest)
    native_authoring_family_corpus_family_count = _first_int(
        native_authoring_family_corpus_summary.get("family_count"),
        len(native_authoring_family_corpus_manifest.get("family_rows", []))
        if isinstance(native_authoring_family_corpus_manifest.get("family_rows"), list)
        else 0,
    ) or 0
    native_authoring_family_corpus_ready_family_count = _first_int(
        native_authoring_family_corpus_summary.get("ready_family_count"),
        native_authoring_family_corpus_family_count,
    ) or 0
    native_authoring_family_corpus_public_reference_count = _first_int(
        native_authoring_family_corpus_summary.get("public_reference_count"),
    ) or 0
    native_authoring_family_corpus_design_reference_count = _first_int(
        native_authoring_family_corpus_summary.get("design_reference_count"),
    ) or 0
    native_authoring_family_corpus_benchmark_reference_count = _first_int(
        native_authoring_family_corpus_summary.get("benchmark_reference_count"),
    ) or 0
    native_authoring_family_corpus_authority_reference_count = _first_int(
        native_authoring_family_corpus_summary.get("authority_reference_count"),
    ) or 0
    native_authoring_family_corpus_surface_count = _first_int(
        native_authoring_family_corpus_summary.get("surface_count"),
    ) or 0
    native_authoring_family_corpus_surface_label = _first_text(
        native_authoring_family_corpus_summary.get("surface_label"),
    )
    native_authoring_family_corpus_unresolved_reference_count = _first_int(
        native_authoring_family_corpus_summary.get("unresolved_reference_count"),
    ) or 0
    native_authoring_family_corpus_unresolved_family_count = _first_int(
        native_authoring_family_corpus_summary.get("unresolved_family_count"),
    ) or 0
    native_authoring_family_local_evidence_summary = (
        native_authoring_family_local_evidence_manifest.get("summary")
        if isinstance(native_authoring_family_local_evidence_manifest.get("summary"), dict)
        else {}
    )
    native_authoring_family_local_evidence_attached = bool(
        native_authoring_family_local_evidence_manifest
    )
    native_authoring_family_local_evidence_pass = _pass(
        native_authoring_family_local_evidence_manifest
    )
    native_authoring_family_local_evidence_summary_line = _first_text(
        native_authoring_family_local_evidence_manifest.get("summary_line"),
    )
    native_authoring_family_local_evidence_family_count = _first_int(
        native_authoring_family_local_evidence_summary.get("family_count"),
    ) or 0
    native_authoring_family_local_evidence_concrete_count = _first_int(
        native_authoring_family_local_evidence_summary.get("concrete_local_corpus_family_count"),
    ) or 0
    native_authoring_family_local_evidence_roundtrip_count = _first_int(
        native_authoring_family_local_evidence_summary.get("roundtrip_concrete_family_count"),
    ) or 0
    native_authoring_family_local_evidence_benchmark_concrete_count = _first_int(
        native_authoring_family_local_evidence_summary.get("benchmark_concrete_family_count"),
    ) or 0
    native_authoring_family_local_evidence_review_concrete_count = _first_int(
        native_authoring_family_local_evidence_summary.get("review_concrete_family_count"),
    ) or 0
    native_authoring_family_local_evidence_registered_only_count = _first_int(
        native_authoring_family_local_evidence_summary.get("reference_registered_only_family_count"),
    ) or 0
    native_authoring_family_local_evidence_source_kind_count = _first_int(
        native_authoring_family_local_evidence_summary.get("source_kind_count"),
    ) or 0
    native_authoring_family_local_evidence_source_kind_label = _first_text(
        native_authoring_family_local_evidence_summary.get("source_kind_label"),
    )
    native_authoring_family_tracks_attached = bool(family_tracks_report)
    native_authoring_family_track_count = _first_int(
        family_tracks_summary.get("family_count"),
        len(family_track_rows),
    ) or 0
    native_authoring_family_track_ready_count = _first_int(
        family_tracks_summary.get("ready_family_count"),
        family_tracks_summary.get("complete_family_count"),
        _count_native_authoring_ready_rows(
            family_track_rows,
            status_keys=("commercialization_status", "status", "reason_code"),
            ready_keys=("family_ready", "release_ready", "solver_ready", "registry_ready", "contract_pass"),
        ),
    ) or 0
    native_authoring_family_track_max_combo_count = _first_int(
        family_tracks_summary.get("max_solver_combo_count"),
        max(
            (_first_int(row.get("solver_combo_count")) or 0 for row in family_track_rows),
            default=0,
        ),
    ) or 0
    native_authoring_family_track_max_mesh_request_count = _first_int(
        family_tracks_summary.get("max_solver_mesh_request_count"),
        max(
            (_first_int(row.get("solver_mesh_request_count")) or 0 for row in family_track_rows),
            default=0,
        ),
    ) or 0
    native_authoring_family_track_status_label = _first_text(
        _normalize_native_authoring_status_label(family_tracks_summary.get("family_status_label")),
        _derive_native_authoring_family_status_label(
            family_track_rows,
            id_keys=("family_id", "authoring_family_id", "project_id"),
            status_keys=("commercialization_status", "status", "reason_code"),
            ready_keys=("family_ready", "release_ready", "solver_ready", "registry_ready", "contract_pass"),
        ),
    )
    native_authoring_family_tracks_summary_line = _first_text(
        family_tracks_report.get("summary_line"),
        (
            "Native authoring family tracks: "
            f"{'READY' if native_authoring_family_track_ready_count >= max(native_authoring_family_track_count, 1) and native_authoring_family_track_count > 0 else 'CHECK'} | "
            f"families={native_authoring_family_track_count} | "
            f"ready={native_authoring_family_track_ready_count} | "
            f"max_combos={native_authoring_family_track_max_combo_count} | "
            f"max_meshes={native_authoring_family_track_max_mesh_request_count}"
            if native_authoring_family_tracks_attached
            else ""
        ),
    )
    native_authoring_runtime_submission_attached = bool(runtime_submission_report)
    native_authoring_runtime_submission_count = _first_int(
        runtime_submission_summary.get("submission_count"),
        runtime_submission_summary.get("family_count"),
        len(runtime_submission_rows),
    ) or 0
    native_authoring_runtime_submission_ready_count = _first_int(
        runtime_submission_summary.get("ready_submission_count"),
        runtime_submission_summary.get("submission_ready_count"),
        runtime_submission_summary.get("runtime_ready_count"),
        runtime_submission_summary.get("release_ready_count"),
        _count_native_authoring_ready_rows(
            runtime_submission_rows,
            status_keys=("submission_status", "commercialization_status", "runtime_status", "lane_status"),
            ready_keys=("runtime_ready", "ready", "release_ready", "submission_ready", "contract_pass"),
        ),
    ) or 0
    native_authoring_runtime_submission_ready = bool(
        _first_bool(
            runtime_submission_summary.get("runtime_submission_ready"),
            runtime_submission_report.get("contract_pass"),
            native_authoring_runtime_submission_count > 0
            and native_authoring_runtime_submission_ready_count >= native_authoring_runtime_submission_count,
        )
    )
    native_authoring_runtime_writeback_ready_count = _first_int(
        runtime_submission_summary.get("writeback_ready_count"),
        runtime_submission_summary.get("writeback_ready_submission_count"),
        sum(
            1
            for row in runtime_submission_rows
            if bool(
                _first_bool(
                    row.get("writeback_ready"),
                    row.get("registry_ready"),
                    row.get("signature_verified"),
                )
            )
        ),
    ) or 0
    native_authoring_runtime_submission_queue_count = _first_int(
        runtime_submission_summary.get("queue_count"),
        runtime_submission_summary.get("pending_submission_count"),
        runtime_submission_summary.get("open_submission_count"),
        sum(
            1
            for row in runtime_submission_rows
            if str(
                row.get("submission_status")
                or row.get("queue_status")
                or row.get("status")
                or ""
            ).strip().lower()
            in {"queued", "pending", "submitted", "open"}
        ),
    ) or 0
    native_authoring_runtime_family_status_label = _first_text(
        _normalize_native_authoring_status_label(runtime_submission_summary.get("family_status_label")),
        _derive_native_authoring_family_status_label(
            runtime_submission_rows,
            id_keys=("family_id", "submission_id", "project_id"),
            status_keys=("family_status", "commercialization_status", "lane_status", "submission_status"),
            ready_keys=("runtime_ready", "ready", "release_ready", "submission_ready", "contract_pass"),
        ),
    )
    native_authoring_runtime_submission_status_label = _derive_native_authoring_family_status_label(
        runtime_submission_rows,
        id_keys=("family_id", "submission_id", "project_id"),
        status_keys=("submission_status", "commercialization_status", "queue_status", "status"),
        ready_keys=("runtime_ready", "ready", "release_ready", "submission_ready", "contract_pass"),
    )
    native_authoring_runtime_submission_status_label = _first_text(
        _normalize_native_authoring_status_label(runtime_submission_summary.get("submission_status_label")),
        native_authoring_runtime_submission_status_label,
    )
    native_authoring_runtime_submission_summary_line = _first_text(
        runtime_submission_report.get("summary_line"),
        (
            "Native authoring runtime submission lane: "
            f"{'READY' if native_authoring_runtime_submission_ready else 'CHECK'} | "
            f"submissions={native_authoring_runtime_submission_count} | "
            f"ready={native_authoring_runtime_submission_ready_count} | "
            f"writeback_ready={native_authoring_runtime_writeback_ready_count} | "
            f"queue={native_authoring_runtime_submission_queue_count}"
            if native_authoring_runtime_submission_attached
            else ""
        ),
    )
    native_authoring_runtime_writeback_depth_attached = bool(runtime_writeback_depth_report)
    native_authoring_runtime_writeback_depth_ready = bool(
        _first_bool(
            runtime_writeback_depth_summary.get("runtime_writeback_depth_ready"),
            runtime_writeback_depth_report.get("contract_pass"),
        )
    )
    native_authoring_runtime_writeback_depth_family_count = _first_int(
        runtime_writeback_depth_summary.get("family_count"),
        len(runtime_writeback_depth_rows),
    ) or 0
    native_authoring_runtime_writeback_depth_ready_family_count = _first_int(
        runtime_writeback_depth_summary.get("depth_ready_family_count"),
        sum(
            1
            for row in runtime_writeback_depth_rows
            if _status_slug(row.get("runtime_writeback_depth_status"), default="") == "full"
        ),
    ) or 0
    native_authoring_runtime_writeback_depth_targeted_family_count = _first_int(
        runtime_writeback_depth_summary.get("targeted_family_count"),
    ) or 0
    native_authoring_runtime_writeback_depth_signature_family_count = _first_int(
        runtime_writeback_depth_summary.get("signature_verified_family_count"),
    ) or 0
    native_authoring_runtime_writeback_depth_repro_family_count = _first_int(
        runtime_writeback_depth_summary.get("package_reproducible_family_count"),
    ) or 0
    native_authoring_runtime_writeback_depth_snapshot_family_count = _first_int(
        runtime_writeback_depth_summary.get("snapshot_ready_family_count"),
    ) or 0
    native_authoring_runtime_writeback_depth_queue_clear_family_count = _first_int(
        runtime_writeback_depth_summary.get("queue_clear_family_count"),
    ) or 0
    native_authoring_runtime_writeback_depth_status_label = _first_text(
        runtime_writeback_depth_summary.get("family_status_label"),
        _compact_label(
            [
                f"{_family_id(row)}:{str(row.get('runtime_writeback_depth_status', 'check') or 'check')}"
                for row in runtime_writeback_depth_rows
                if _family_id(row)
            ],
            max_items=6,
        ),
    )
    native_authoring_runtime_writeback_depth_summary_line = _first_text(
        runtime_writeback_depth_report.get("summary_line"),
        (
            "Native authoring runtime writeback depth: "
            f"{'READY' if native_authoring_runtime_writeback_depth_ready else 'CHECK'} | "
            f"families={native_authoring_runtime_writeback_depth_family_count} | "
            f"full_depth={native_authoring_runtime_writeback_depth_ready_family_count} | "
            f"targeted={native_authoring_runtime_writeback_depth_targeted_family_count} | "
            f"signature={native_authoring_runtime_writeback_depth_signature_family_count} | "
            f"repro={native_authoring_runtime_writeback_depth_repro_family_count} | "
            f"snapshot={native_authoring_runtime_writeback_depth_snapshot_family_count} | "
            f"queue_clear={native_authoring_runtime_writeback_depth_queue_clear_family_count}"
            if native_authoring_runtime_writeback_depth_attached
            else ""
        ),
    )
    native_authoring_local_runtime_scenario_depth_attached = bool(
        local_runtime_scenario_depth_report
    )
    native_authoring_local_runtime_scenario_depth_ready = bool(
        _first_bool(
            local_runtime_scenario_depth_summary.get("local_runtime_scenario_depth_ready"),
            local_runtime_scenario_depth_report.get("contract_pass"),
        )
    )
    native_authoring_local_runtime_scenario_depth_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("family_count"),
        len(local_runtime_scenario_depth_rows),
    ) or 0
    native_authoring_local_runtime_scenario_depth_ready_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("depth_ready_family_count"),
        sum(
            1
            for row in local_runtime_scenario_depth_rows
            if _status_slug(row.get("local_runtime_scenario_depth_status"), default="") == "deep"
        ),
    ) or 0
    native_authoring_local_runtime_scenario_depth_targeted_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("targeted_family_count"),
    ) or 0
    native_authoring_local_runtime_scenario_depth_trace_ready_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("trace_ready_family_count"),
    ) or 0
    native_authoring_local_runtime_scenario_depth_mesh_ready_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("mesh_trace_ready_family_count"),
    ) or 0
    native_authoring_local_runtime_scenario_depth_runtime_ready_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("runtime_ready_family_count"),
    ) or 0
    native_authoring_local_runtime_scenario_depth_omitted_family_count = _first_int(
        local_runtime_scenario_depth_summary.get("omitted_library_family_count"),
    ) or 0
    native_authoring_local_runtime_scenario_depth_status_label = _first_text(
        local_runtime_scenario_depth_summary.get("family_status_label"),
        _compact_label(
            [
                f"{_family_id(row)}:{str(row.get('local_runtime_scenario_depth_status', 'check') or 'check')}"
                for row in local_runtime_scenario_depth_rows
                if _family_id(row)
            ],
            max_items=6,
        ),
    )
    native_authoring_local_runtime_scenario_depth_summary_line = _first_text(
        local_runtime_scenario_depth_report.get("summary_line"),
        (
            "Native authoring local runtime scenario depth: "
            f"{'READY' if native_authoring_local_runtime_scenario_depth_ready else 'CHECK'} | "
            f"families={native_authoring_local_runtime_scenario_depth_family_count} | "
            f"deep={native_authoring_local_runtime_scenario_depth_ready_family_count} | "
            f"targeted={native_authoring_local_runtime_scenario_depth_targeted_family_count} | "
            f"trace_ready={native_authoring_local_runtime_scenario_depth_trace_ready_family_count} | "
            f"mesh_ready={native_authoring_local_runtime_scenario_depth_mesh_ready_family_count} | "
            f"runtime_ready={native_authoring_local_runtime_scenario_depth_runtime_ready_family_count} | "
            f"omitted={native_authoring_local_runtime_scenario_depth_omitted_family_count}"
            if native_authoring_local_runtime_scenario_depth_attached
            else ""
        ),
    )
    native_authoring_local_variant_writeback_trace_attached = bool(
        local_variant_writeback_trace_report
        or local_variant_writeback_trace_summary
        or local_variant_writeback_trace_rows
    )
    native_authoring_local_variant_writeback_trace_family_count = _first_int(
        local_variant_writeback_trace_summary.get("family_count"),
        len(local_variant_writeback_trace_rows),
    ) or 0
    native_authoring_local_variant_writeback_trace_ready_family_count = _first_int(
        local_variant_writeback_trace_summary.get("deep_ready_family_count"),
        sum(
            1
            for row in local_variant_writeback_trace_rows
            if _status_slug(row.get("local_variant_writeback_trace_status"), default="") == "deep"
        ),
    ) or 0
    native_authoring_local_variant_writeback_trace_targeted_family_count = _first_int(
        local_variant_writeback_trace_summary.get("targeted_family_count"),
    ) or 0
    native_authoring_local_variant_workspace_variant_ready_family_count = _first_int(
        local_variant_writeback_trace_summary.get("workspace_variant_ready_family_count"),
        portfolio_summary.get("local_variant_workspace_variant_ready_family_count"),
        sum(1 for row in local_variant_writeback_trace_rows if bool(row.get("workspace_variant_ready"))),
    ) or 0
    native_authoring_local_variant_solver_variant_ready_family_count = _first_int(
        local_variant_writeback_trace_summary.get("solver_variant_ready_family_count"),
        portfolio_summary.get("local_variant_solver_variant_ready_family_count"),
        sum(1 for row in local_variant_writeback_trace_rows if bool(row.get("solver_variant_ready"))),
    ) or 0
    native_authoring_local_variant_writeback_trace_ready_family_trace_count = _first_int(
        local_variant_writeback_trace_summary.get("writeback_trace_ready_family_count"),
        portfolio_summary.get("local_variant_writeback_trace_ready_family_count"),
        sum(1 for row in local_variant_writeback_trace_rows if bool(row.get("writeback_trace_ready"))),
    ) or 0
    native_authoring_local_variant_active_multi_family_count = _first_int(
        local_variant_writeback_trace_summary.get("active_multi_family_count"),
        solver_family_breadth_summary.get("active_multi_family_count"),
        writeback_breadth_summary.get("active_multi_family_count"),
        sum(
            1
            for row in local_variant_writeback_trace_rows
            if _first_int(row.get("workspace_active_family_count")) >= 2
        ),
    ) or 0
    native_authoring_local_variant_combo_multi_family_count = _first_int(
        local_variant_writeback_trace_summary.get("combo_multi_family_count"),
        solver_family_breadth_summary.get("combo_broad_family_count"),
        writeback_breadth_summary.get("combo_broad_family_count"),
        sum(
            1
            for row in local_variant_writeback_trace_rows
            if _first_int(row.get("solver_combo_family_count")) >= 3
        ),
    ) or 0
    native_authoring_local_variant_signed_writeback_family_count = _first_int(
        local_variant_writeback_trace_summary.get("signed_writeback_family_count"),
        portfolio_summary.get("local_variant_writeback_signed_family_count"),
        runtime_writeback_depth_summary.get("signature_verified_family_count"),
        sum(1 for row in local_variant_writeback_trace_rows if bool(row.get("signature_verified"))),
    ) or 0
    native_authoring_local_variant_trace_omitted_family_count = _first_int(
        local_variant_writeback_trace_summary.get("omitted_library_family_count"),
        local_runtime_scenario_depth_summary.get("omitted_library_family_count"),
        sum(
            1
            for row in local_variant_writeback_trace_rows
            if _first_int(row.get("omitted_library_combination_count")) > 0
        ),
    ) or 0
    native_authoring_local_variant_writeback_trace_ready = bool(
        _first_bool(
            local_variant_writeback_trace_summary.get("local_variant_writeback_trace_ready"),
            local_variant_writeback_trace_report.get("contract_pass"),
            native_authoring_local_variant_writeback_trace_family_count > 0
            and native_authoring_local_variant_writeback_trace_ready_family_count
            >= native_authoring_local_variant_writeback_trace_family_count,
        )
    )
    native_authoring_local_variant_writeback_trace_status_label = _first_text(
        local_variant_writeback_trace_summary.get("family_status_label"),
        _compact_label(
            [
                f"{_family_id(row)}:{str(row.get('local_variant_writeback_trace_status', 'check') or 'check')}"
                for row in local_variant_writeback_trace_rows
                if _family_id(row)
            ],
            max_items=6,
        ),
    )
    native_authoring_local_variant_writeback_trace_summary_line = _first_text(
        local_variant_writeback_trace_report.get("summary_line"),
        portfolio_report.get("local_variant_writeback_trace_summary_line"),
        (
            "Native authoring local variant/writeback trace: "
            f"{'READY' if native_authoring_local_variant_writeback_trace_ready else 'CHECK'} | "
            f"families={native_authoring_local_variant_writeback_trace_family_count} | "
            f"deep={native_authoring_local_variant_writeback_trace_ready_family_count} | "
            f"targeted={native_authoring_local_variant_writeback_trace_targeted_family_count} | "
            f"workspace_variant={native_authoring_local_variant_workspace_variant_ready_family_count} | "
            f"solver_variant={native_authoring_local_variant_solver_variant_ready_family_count} | "
            f"writeback_trace={native_authoring_local_variant_writeback_trace_ready_family_trace_count} | "
            f"active_multi={native_authoring_local_variant_active_multi_family_count} | "
            f"combo_multi={native_authoring_local_variant_combo_multi_family_count} | "
            f"signed={native_authoring_local_variant_signed_writeback_family_count} | "
            f"omitted={native_authoring_local_variant_trace_omitted_family_count}"
            if native_authoring_local_variant_writeback_trace_attached
            else ""
        ),
    )
    native_authoring_multi_project_runtime_writeback_attached = bool(
        multi_project_runtime_writeback_report
    )
    native_authoring_multi_project_runtime_writeback_ready = bool(
        _first_bool(
            multi_project_runtime_writeback_summary.get("multi_project_runtime_writeback_ready"),
            multi_project_runtime_writeback_report.get("contract_pass"),
        )
    )
    native_authoring_multi_project_runtime_writeback_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("project_count"),
        len(multi_project_runtime_writeback_project_rows),
    ) or 0
    native_authoring_multi_project_runtime_writeback_project_family_count = _first_int(
        multi_project_runtime_writeback_summary.get("project_family_count"),
        len(multi_project_runtime_writeback_project_family_rows),
    ) or 0
    native_authoring_multi_project_runtime_writeback_full_count = _first_int(
        multi_project_runtime_writeback_summary.get("full_depth_project_family_count"),
    ) or 0
    native_authoring_multi_project_runtime_writeback_ready_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("ready_project_count"),
    ) or 0
    native_authoring_multi_project_runtime_writeback_signature_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("signature_verified_project_count"),
    ) or 0
    native_authoring_multi_project_runtime_writeback_repro_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("package_reproducible_project_count"),
    ) or 0
    native_authoring_multi_project_runtime_writeback_snapshot_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("snapshot_ready_project_count"),
    ) or 0
    native_authoring_multi_project_runtime_writeback_queue_clear_project_count = _first_int(
        multi_project_runtime_writeback_summary.get("queue_clear_project_count"),
    ) or 0
    native_authoring_multi_project_runtime_writeback_status_label = _first_text(
        multi_project_runtime_writeback_summary.get("project_status_label"),
        _compact_label(
            [
                f"{str(row.get('project_id', '') or '').strip()}:{str(row.get('project_status', 'check') or 'check')}"
                for row in multi_project_runtime_writeback_project_rows
                if str(row.get("project_id", "") or "").strip()
            ],
            max_items=6,
        ),
    )
    native_authoring_multi_project_runtime_writeback_summary_line = _first_text(
        multi_project_runtime_writeback_report.get("summary_line"),
        (
            "Native authoring multi-project runtime/writeback: "
            f"{'READY' if native_authoring_multi_project_runtime_writeback_ready else 'CHECK'} | "
            f"projects={native_authoring_multi_project_runtime_writeback_project_count} | "
            f"project_families={native_authoring_multi_project_runtime_writeback_project_family_count} | "
            f"full_depth={native_authoring_multi_project_runtime_writeback_full_count} | "
            f"ready_projects={native_authoring_multi_project_runtime_writeback_ready_project_count} | "
            f"signature={native_authoring_multi_project_runtime_writeback_signature_project_count} | "
            f"repro={native_authoring_multi_project_runtime_writeback_repro_project_count} | "
            f"snapshot={native_authoring_multi_project_runtime_writeback_snapshot_project_count} | "
            f"queue_clear={native_authoring_multi_project_runtime_writeback_queue_clear_project_count}"
            if native_authoring_multi_project_runtime_writeback_attached
            else ""
        ),
    )
    native_authoring_solver_family_breadth_attached = bool(solver_family_breadth_report)
    native_authoring_solver_family_breadth_ready = bool(
        _first_bool(
            solver_family_breadth_summary.get("solver_family_breadth_ready"),
            solver_family_breadth_report.get("contract_pass"),
        )
    )
    native_authoring_solver_family_breadth_family_count = _first_int(
        solver_family_breadth_summary.get("family_count"),
        len(solver_family_breadth_rows),
    ) or 0
    native_authoring_solver_family_breadth_ready_family_count = _first_int(
        solver_family_breadth_summary.get("broad_ready_family_count"),
        sum(
            1
            for row in solver_family_breadth_rows
            if bool(
                _first_bool(
                    row.get("broad_solver_family_ready"),
                    _status_slug(row.get("solver_family_breadth_status"), default="") == "broad",
                )
            )
        ),
    ) or 0
    native_authoring_solver_family_breadth_full_family_count = _first_int(
        solver_family_breadth_summary.get("full_breadth_family_count"),
    ) or 0
    native_authoring_solver_family_breadth_mesh_broad_family_count = _first_int(
        solver_family_breadth_summary.get("mesh_broad_family_count"),
    ) or 0
    native_authoring_solver_family_breadth_member_multi_family_count = _first_int(
        solver_family_breadth_summary.get("member_multi_family_count"),
    ) or 0
    native_authoring_solver_family_breadth_status_label = _first_text(
        solver_family_breadth_summary.get("family_status_label"),
        _compact_label(
            [
                f"{_family_id(row)}:{str(row.get('solver_family_breadth_status', 'check') or 'check')}"
                for row in solver_family_breadth_rows
                if _family_id(row)
            ],
            max_items=6,
        ),
    )
    native_authoring_solver_family_breadth_summary_line = _first_text(
        solver_family_breadth_report.get("summary_line"),
        (
            "Native authoring solver family breadth: "
            f"{'READY' if native_authoring_solver_family_breadth_ready else 'CHECK'} | "
            f"families={native_authoring_solver_family_breadth_family_count} | "
            f"broad_ready={native_authoring_solver_family_breadth_ready_family_count} | "
            f"full_breadth={native_authoring_solver_family_breadth_full_family_count} | "
            f"mesh_broad={native_authoring_solver_family_breadth_mesh_broad_family_count} | "
            f"member_multi={native_authoring_solver_family_breadth_member_multi_family_count}"
            if native_authoring_solver_family_breadth_attached
            else ""
        ),
    )
    native_authoring_writeback_breadth_attached = bool(writeback_breadth_report)
    native_authoring_writeback_breadth_ready = bool(
        _first_bool(
            writeback_breadth_summary.get("writeback_breadth_ready"),
            writeback_breadth_report.get("contract_pass"),
        )
    )
    native_authoring_writeback_breadth_family_count = _first_int(
        writeback_breadth_summary.get("family_count"),
        len(writeback_breadth_rows),
    ) or 0
    native_authoring_writeback_breadth_ready_family_count = _first_int(
        writeback_breadth_summary.get("broad_ready_family_count"),
        sum(
            1
            for row in writeback_breadth_rows
            if bool(
                _first_bool(
                    row.get("broad_writeback_ready"),
                    _status_slug(row.get("writeback_breadth_status"), default="") == "broad",
                )
            )
        ),
    ) or 0
    native_authoring_writeback_breadth_full_family_count = _first_int(
        writeback_breadth_summary.get("full_breadth_family_count"),
    ) or 0
    native_authoring_writeback_breadth_mesh_broad_family_count = _first_int(
        writeback_breadth_summary.get("mesh_broad_family_count"),
    ) or 0
    native_authoring_writeback_breadth_status_label = _first_text(
        writeback_breadth_summary.get("family_status_label"),
        _compact_label(
            [
                f"{_family_id(row)}:{str(row.get('writeback_breadth_status', 'check') or 'check')}"
                for row in writeback_breadth_rows
                if _family_id(row)
            ],
            max_items=6,
        ),
    )
    native_authoring_writeback_breadth_summary_line = _first_text(
        writeback_breadth_report.get("summary_line"),
        (
            "Native authoring writeback breadth: "
            f"{'READY' if native_authoring_writeback_breadth_ready else 'CHECK'} | "
            f"families={native_authoring_writeback_breadth_family_count} | "
            f"broad_ready={native_authoring_writeback_breadth_ready_family_count} | "
            f"full_breadth={native_authoring_writeback_breadth_full_family_count} | "
            f"mesh_broad={native_authoring_writeback_breadth_mesh_broad_family_count}"
            if native_authoring_writeback_breadth_attached
            else ""
        ),
    )
    project_ops_service_attached = bool(project_ops_service_snapshot_report)
    project_ops_service_project_count_raw = _first_int(
        project_ops_service_summary.get("project_count"),
        len(project_ops_service_projects),
    ) or 0
    project_ops_service_family_count_raw = _first_int(
        project_ops_service_summary.get("family_count"),
        len(project_ops_service_families),
    ) or 0
    project_ops_service_ready_family_count_raw = _first_int(
        project_ops_service_summary.get("ready_family_count"),
        _count_native_authoring_ready_rows(
            project_ops_service_families,
            status_keys=("commercialization_status", "reason_code"),
            ready_keys=("release_ready", "runtime_ready", "ops_ready", "registry_ready", "contract_pass"),
        ),
    ) or 0
    project_ops_service_project_count = _max_int(
        project_ops_service_project_count_raw,
        native_authoring_portfolio_project_count,
        native_authoring_multi_project_runtime_writeback_project_count,
    )
    project_ops_service_family_count = _max_int(
        project_ops_service_family_count_raw,
        native_authoring_portfolio_family_count,
        native_authoring_family_track_count,
        native_authoring_runtime_submission_count,
        native_authoring_runtime_writeback_depth_family_count,
        native_authoring_local_runtime_scenario_depth_family_count,
        native_authoring_local_variant_writeback_trace_family_count,
        native_authoring_multi_project_runtime_writeback_project_family_count,
        native_authoring_solver_family_breadth_family_count,
        native_authoring_writeback_breadth_family_count,
    )
    project_ops_service_ready_family_count = _max_int(
        project_ops_service_ready_family_count_raw,
        native_authoring_portfolio_ready_family_count,
        native_authoring_family_track_ready_count,
        native_authoring_runtime_submission_ready_count,
        native_authoring_runtime_writeback_depth_ready_family_count,
        native_authoring_local_runtime_scenario_depth_ready_family_count,
        native_authoring_local_variant_writeback_trace_ready_family_count,
        native_authoring_solver_family_breadth_ready_family_count,
        native_authoring_writeback_breadth_ready_family_count,
    )
    project_ops_service_ready = bool(
        _first_bool(
            project_ops_service_summary.get("service_ready"),
            project_ops_service_snapshot_report.get("contract_pass"),
            project_ops_service_family_count > 0
            and project_ops_service_ready_family_count >= project_ops_service_family_count,
        )
    )
    project_ops_service_endpoint_count = _first_int(
        project_ops_service_summary.get("endpoint_count"),
        len(project_ops_service_endpoints),
    ) or 0
    project_ops_service_family_status_label = _first_text(
        native_authoring_portfolio_family_status_label
        if project_ops_service_family_count > project_ops_service_family_count_raw
        else "",
        _normalize_native_authoring_status_label(project_ops_service_summary.get("family_status_label")),
        _derive_native_authoring_family_status_label(
            project_ops_service_families,
            id_keys=("family_id", "authoring_family_id", "project_id"),
            status_keys=("commercialization_status", "reason_code"),
            ready_keys=("release_ready", "runtime_ready", "ops_ready", "registry_ready", "contract_pass"),
        ),
    )
    project_ops_service_summary_line = _first_text(
        project_ops_service_snapshot_report.get("summary_line")
        if (
            project_ops_service_project_count_raw == project_ops_service_project_count
            and project_ops_service_family_count_raw == project_ops_service_family_count
        )
        else "",
        (
            "Project ops service snapshot: "
            f"{'READY' if project_ops_service_ready else 'CHECK'} | "
            f"projects={project_ops_service_project_count} | "
            f"families={project_ops_service_family_count} | "
            f"endpoints={project_ops_service_endpoint_count}"
            if project_ops_service_attached
            else ""
        ),
    )
    ready_family_alignment_rows: list[tuple[str, int]] = []
    if native_authoring_portfolio_attached:
        ready_family_alignment_rows.append(("portfolio", native_authoring_portfolio_ready_family_count))
    if native_authoring_family_tracks_attached:
        ready_family_alignment_rows.append(("tracks", native_authoring_family_track_ready_count))
    if native_authoring_runtime_submission_attached:
        ready_family_alignment_rows.append(("runtime", native_authoring_runtime_submission_ready_count))
    if project_ops_service_attached:
        ready_family_alignment_rows.append(("service", project_ops_service_ready_family_count))
    native_authoring_ready_family_count_alignment_label = " | ".join(
        f"{surface}={count}" for surface, count in ready_family_alignment_rows
    )
    family_status_alignment_rows: list[tuple[str, str]] = []
    if native_authoring_portfolio_family_status_label:
        family_status_alignment_rows.append(
            ("portfolio", native_authoring_portfolio_family_status_label)
        )
    if native_authoring_family_track_status_label:
        family_status_alignment_rows.append(
            ("tracks", native_authoring_family_track_status_label)
        )
    if native_authoring_runtime_family_status_label:
        family_status_alignment_rows.append(
            ("runtime", native_authoring_runtime_family_status_label)
        )
    if project_ops_service_family_status_label:
        family_status_alignment_rows.append(
            ("service", project_ops_service_family_status_label)
        )
    native_authoring_family_status_alignment_label = " | ".join(
        f"{surface}={label}" for surface, label in family_status_alignment_rows
    )
    native_authoring_portfolio_ready_family_ids = _unique_sorted_tokens(
        [
            _family_id(row)
            for row in portfolio_family_rows
            if _family_id(row)
            and bool(
                _first_bool(
                    row.get("release_ready"),
                    row.get("runtime_ready"),
                    row.get("ops_ready"),
                    row.get("contract_pass"),
                )
            )
        ]
    )
    native_authoring_family_track_ready_family_ids = _unique_sorted_tokens(
        [
            _family_id(row)
            for row in family_track_rows
            if _family_id(row)
            and bool(
                _first_bool(
                    row.get("family_ready"),
                    row.get("release_ready"),
                    row.get("solver_ready"),
                    row.get("contract_pass"),
                )
            )
        ]
    )
    native_authoring_runtime_ready_family_ids = _unique_sorted_tokens(
        [
            _family_id(row)
            for row in runtime_submission_rows
            if _family_id(row)
            and bool(
                _first_bool(
                    row.get("runtime_ready"),
                    row.get("ready"),
                    row.get("release_ready"),
                    row.get("contract_pass"),
                )
            )
        ]
    )
    native_authoring_writeback_ready_family_ids = _unique_sorted_tokens(
        [
            _family_id(row)
            for row in runtime_submission_rows
            if _family_id(row)
            and bool(
                _first_bool(
                    row.get("writeback_ready"),
                    row.get("registry_ready"),
                    row.get("signature_verified"),
                )
            )
        ]
    )
    project_ops_service_ready_family_ids = _unique_sorted_tokens(
        [
            _family_id(row)
            for row in project_ops_service_families
            if _family_id(row)
            and bool(
                _first_bool(
                    row.get("release_ready"),
                    row.get("runtime_ready"),
                    row.get("ops_ready"),
                    row.get("registry_ready"),
                    row.get("contract_pass"),
                    str(row.get("commercialization_status", "")).strip().lower() == "ready",
                )
            )
        ]
    )
    if project_ops_service_family_count > project_ops_service_family_count_raw:
        project_ops_service_ready_family_ids = native_authoring_portfolio_ready_family_ids
    native_authoring_surface_consistency_expected_family_count = max(
        native_authoring_portfolio_family_count,
        native_authoring_family_track_count,
        native_authoring_runtime_submission_count,
        project_ops_service_family_count,
    )
    native_authoring_surface_consistency_set_candidates = [
        native_authoring_portfolio_ready_family_ids,
        native_authoring_family_track_ready_family_ids,
        native_authoring_runtime_ready_family_ids,
        native_authoring_writeback_ready_family_ids,
        project_ops_service_ready_family_ids,
    ]
    native_authoring_surface_consistency_active_sets = [
        set(candidate) for candidate in native_authoring_surface_consistency_set_candidates if candidate
    ]
    native_authoring_surface_consistency_aligned_family_ids = (
        sorted(set.intersection(*native_authoring_surface_consistency_active_sets))
        if native_authoring_surface_consistency_active_sets
        else []
    )
    native_authoring_surface_consistency_aligned_family_count = len(
        native_authoring_surface_consistency_aligned_family_ids
    )
    native_authoring_surface_consistency_ready = bool(
        native_authoring_surface_consistency_expected_family_count > 0
        and native_authoring_surface_consistency_aligned_family_count
        >= native_authoring_surface_consistency_expected_family_count
        and native_authoring_runtime_submission_queue_count == 0
    )
    native_authoring_surface_consistency_status_label = _compact_label(
        [
            *[
                f"portfolio={family_id}"
                for family_id in native_authoring_portfolio_ready_family_ids
            ],
            *[
                f"aligned={family_id}"
                for family_id in native_authoring_surface_consistency_aligned_family_ids
            ],
        ],
        max_items=6,
    )
    native_authoring_surface_consistency_summary_line = (
        "Native authoring surface consistency: "
        f"{'READY' if native_authoring_surface_consistency_ready else 'CHECK'} | "
        f"aligned={native_authoring_surface_consistency_aligned_family_count}/"
        f"{native_authoring_surface_consistency_expected_family_count} | "
        f"portfolio_ready={native_authoring_portfolio_ready_family_count} | "
        f"tracks_ready={native_authoring_family_track_ready_count} | "
        f"runtime_ready={native_authoring_runtime_submission_ready_count} | "
        f"writeback_ready={native_authoring_runtime_writeback_ready_count} | "
        f"service_ready={project_ops_service_ready_family_count} | "
        f"queue={native_authoring_runtime_submission_queue_count}"
    )

    native_authoring_commercialization_summary_line = ""
    if native_authoring_evidence_attached:
        native_authoring_commercialization_summary_line = (
            f"Native authoring commercialization lane: {native_authoring_commercialization_status.upper()} | "
            f"solver={'yes' if solver_session_pass else 'no'}"
            f"(ready={solver_session_authoring_ready},meshes={solver_session_mesh_request_count},"
            f"cells={solver_session_total_estimated_cells},combos={solver_session_combo_count},"
            f"cases={solver_session_load_case_count}) | "
            f"ops={'yes' if ops_bundle_pass else 'no'}"
            f"(workspace_ready={ops_bundle_workspace_ready_pass},jobs={ops_bundle_job_count},"
            f"snapshots={ops_bundle_snapshot_count},registry={ops_bundle_registry_artifact_count},"
            f"approvals={ops_bundle_registry_approval_count},signature_verified={ops_bundle_signature_verified}) | "
            f"breadth=palette_families={len(palette_families)}(active={len(active_families)},"
            f"members={_compact_label(member_types, max_items=4) or 'n/a'}) | "
            f"portfolio=projects={native_authoring_portfolio_project_count},"
            f"complete={native_authoring_portfolio_complete_project_count},"
            f"signature={native_authoring_portfolio_signature_verified_count},"
            f"repro={native_authoring_portfolio_package_reproducible_count},"
            f"unmatched={native_authoring_portfolio_unmatched_input_count},"
            f"families={native_authoring_portfolio_family_count},"
            f"ready_families={native_authoring_portfolio_ready_family_count},"
            f"max_combos={native_authoring_portfolio_max_solver_combo_count},"
            f"max_meshes={native_authoring_portfolio_max_solver_mesh_request_count} | "
            f"tracks=attached:{native_authoring_family_tracks_attached},families={native_authoring_family_track_count},"
            f"ready={native_authoring_family_track_ready_count},max_combos={native_authoring_family_track_max_combo_count},"
            f"max_meshes={native_authoring_family_track_max_mesh_request_count} | "
            f"runtime_lane=attached:{native_authoring_runtime_submission_attached},ready={native_authoring_runtime_submission_ready},"
            f"submissions={native_authoring_runtime_submission_count},writeback_ready={native_authoring_runtime_writeback_ready_count},"
            f"queue={native_authoring_runtime_submission_queue_count} | "
            f"runtime_writeback_depth=attached:{native_authoring_runtime_writeback_depth_attached},ready={native_authoring_runtime_writeback_depth_ready},"
            f"families={native_authoring_runtime_writeback_depth_family_count},full={native_authoring_runtime_writeback_depth_ready_family_count},"
            f"targeted={native_authoring_runtime_writeback_depth_targeted_family_count},signature={native_authoring_runtime_writeback_depth_signature_family_count},"
            f"repro={native_authoring_runtime_writeback_depth_repro_family_count},snapshot={native_authoring_runtime_writeback_depth_snapshot_family_count},"
            f"queue_clear={native_authoring_runtime_writeback_depth_queue_clear_family_count} | "
            f"local_runtime_depth=attached:{native_authoring_local_runtime_scenario_depth_attached},ready={native_authoring_local_runtime_scenario_depth_ready},"
            f"families={native_authoring_local_runtime_scenario_depth_family_count},deep={native_authoring_local_runtime_scenario_depth_ready_family_count},"
            f"targeted={native_authoring_local_runtime_scenario_depth_targeted_family_count},trace={native_authoring_local_runtime_scenario_depth_trace_ready_family_count},"
            f"mesh={native_authoring_local_runtime_scenario_depth_mesh_ready_family_count},runtime={native_authoring_local_runtime_scenario_depth_runtime_ready_family_count},"
            f"omitted={native_authoring_local_runtime_scenario_depth_omitted_family_count} | "
            f"local_variant_trace=attached:{native_authoring_local_variant_writeback_trace_attached},ready={native_authoring_local_variant_writeback_trace_ready},"
            f"families={native_authoring_local_variant_writeback_trace_family_count},deep={native_authoring_local_variant_writeback_trace_ready_family_count},"
            f"targeted={native_authoring_local_variant_writeback_trace_targeted_family_count},workspace_variant={native_authoring_local_variant_workspace_variant_ready_family_count},"
            f"solver_variant={native_authoring_local_variant_solver_variant_ready_family_count},writeback_trace={native_authoring_local_variant_writeback_trace_ready_family_trace_count},"
            f"active_multi={native_authoring_local_variant_active_multi_family_count},combo_multi={native_authoring_local_variant_combo_multi_family_count},"
            f"signed={native_authoring_local_variant_signed_writeback_family_count},omitted={native_authoring_local_variant_trace_omitted_family_count} | "
            f"multi_project_runtime=attached:{native_authoring_multi_project_runtime_writeback_attached},ready={native_authoring_multi_project_runtime_writeback_ready},"
            f"projects={native_authoring_multi_project_runtime_writeback_project_count},project_families={native_authoring_multi_project_runtime_writeback_project_family_count},"
            f"full={native_authoring_multi_project_runtime_writeback_full_count},ready_projects={native_authoring_multi_project_runtime_writeback_ready_project_count},"
            f"signature={native_authoring_multi_project_runtime_writeback_signature_project_count},repro={native_authoring_multi_project_runtime_writeback_repro_project_count},"
            f"snapshot={native_authoring_multi_project_runtime_writeback_snapshot_project_count},queue_clear={native_authoring_multi_project_runtime_writeback_queue_clear_project_count} | "
            f"solver_family_breadth=attached:{native_authoring_solver_family_breadth_attached},ready={native_authoring_solver_family_breadth_ready},"
            f"families={native_authoring_solver_family_breadth_family_count},broad_ready={native_authoring_solver_family_breadth_ready_family_count},"
            f"full={native_authoring_solver_family_breadth_full_family_count},mesh_broad={native_authoring_solver_family_breadth_mesh_broad_family_count},"
            f"member_multi={native_authoring_solver_family_breadth_member_multi_family_count} | "
            f"writeback_breadth=attached:{native_authoring_writeback_breadth_attached},ready={native_authoring_writeback_breadth_ready},"
            f"families={native_authoring_writeback_breadth_family_count},broad_ready={native_authoring_writeback_breadth_ready_family_count},"
            f"full={native_authoring_writeback_breadth_full_family_count},mesh_broad={native_authoring_writeback_breadth_mesh_broad_family_count} | "
            f"ops_service=attached:{project_ops_service_attached},ready={project_ops_service_ready},"
            f"projects={project_ops_service_project_count},families={project_ops_service_family_count},"
            f"endpoints={project_ops_service_endpoint_count} | "
            f"consistency=ready:{native_authoring_surface_consistency_ready},"
            f"aligned={native_authoring_surface_consistency_aligned_family_count}/"
            f"{native_authoring_surface_consistency_expected_family_count},"
            f"service_ready={project_ops_service_ready_family_count}"
        )

    artifacts = {
        "native_authoring_ops_bundle_json": _first_text(
            ops_inputs.get("out"),
            str(ops_bundle_path) if ops_bundle_report else "",
        ),
        "native_authoring_workspace_summary_json": _first_text(
            ops_artifacts.get("workspace_summary_json"),
            ops_inputs.get("workspace_summary"),
            str(workspace_summary_path) if workspace_report and workspace_summary_path is not None else "",
        ),
        "native_authoring_solver_session_json": _first_text(
            ops_artifacts.get("solver_session_json"),
            solver_artifacts.get("session_summary_json"),
            str(solver_session_path) if solver_session_report else "",
        ),
        "native_authoring_solver_loadcomb_preview_mgt": _first_text(
            ops_artifacts.get("solver_loadcomb_preview_mgt"),
            ops_artifacts.get("loadcomb_preview_mgt"),
            solver_artifacts.get("loadcomb_preview_mgt"),
            ops_inputs.get("loadcomb_preview_out"),
        ),
        "native_authoring_job_manifest_json": _first_text(
            ops_artifacts.get("job_manifest_json"),
            ops_inputs.get("job_manifest_out"),
        ),
        "native_authoring_batch_job_report_json": _first_text(
            ops_artifacts.get("batch_job_report_json"),
            ops_inputs.get("batch_report_out"),
        ),
        "native_authoring_project_registry_json": _first_text(
            ops_artifacts.get("project_registry_json"),
            ops_inputs.get("project_registry_out"),
        ),
        "native_authoring_project_package_zip": _first_text(
            ops_artifacts.get("project_package_zip"),
            ops_inputs.get("project_package_out"),
        ),
        "native_authoring_project_registry_public_key": _first_text(
            ops_artifacts.get("project_registry_public_key"),
            ops_inputs.get("public_key_out"),
        ),
        "native_authoring_project_registry_signature": _first_text(
            ops_artifacts.get("project_registry_signature"),
            ops_inputs.get("signature_out"),
        ),
        "native_authoring_portfolio_json": str(portfolio_path)
        if portfolio_report and portfolio_path is not None
        else "",
        "native_authoring_family_corpus_manifest_json": str(family_corpus_manifest_path)
        if native_authoring_family_corpus_attached and family_corpus_manifest_path is not None
        else "",
        "native_authoring_family_local_evidence_manifest_json": str(family_local_evidence_manifest_path)
        if native_authoring_family_local_evidence_attached and family_local_evidence_manifest_path is not None
        else "",
        "native_authoring_portfolio_workspace_json": _first_text(
            portfolio_artifacts.get("project_registry_portfolio_workspace_json"),
        ),
        "native_authoring_portfolio_index_json": _first_text(
            portfolio_artifacts.get("project_registry_index_json"),
        ),
        "native_authoring_family_tracks_json": _first_text(
            family_tracks_artifacts.get("native_authoring_family_tracks_json"),
            str(family_tracks_path) if family_tracks_report and family_tracks_path is not None else "",
        ),
        "native_authoring_runtime_submission_lane_json": _first_text(
            runtime_submission_artifacts.get("native_authoring_runtime_submission_lane_json"),
            str(runtime_submission_path)
            if runtime_submission_report and runtime_submission_path is not None
            else "",
        ),
        "native_authoring_runtime_writeback_depth_report_json": _first_text(
            runtime_writeback_depth_artifacts.get("native_authoring_runtime_writeback_depth_report_json"),
            str(runtime_writeback_depth_path)
            if runtime_writeback_depth_report and runtime_writeback_depth_path is not None
            else "",
        ),
        "native_authoring_local_runtime_scenario_depth_report_json": _first_text(
            local_runtime_scenario_depth_artifacts.get(
                "native_authoring_local_runtime_scenario_depth_report_json"
            ),
            str(local_runtime_scenario_depth_path)
            if local_runtime_scenario_depth_report and local_runtime_scenario_depth_path is not None
            else "",
        ),
        "native_authoring_local_variant_writeback_trace_report_json": _first_text(
            local_variant_writeback_trace_artifacts.get(
                "native_authoring_local_variant_writeback_trace_report_json"
            ),
            portfolio_artifacts.get("native_authoring_local_variant_writeback_trace_report_json"),
            str(local_variant_writeback_trace_path)
            if native_authoring_local_variant_writeback_trace_attached
            and local_variant_writeback_trace_path is not None
            else "",
        ),
        "native_authoring_multi_project_runtime_writeback_report_json": _first_text(
            multi_project_runtime_writeback_artifacts.get(
                "native_authoring_multi_project_runtime_writeback_report_json"
            ),
            str(multi_project_runtime_writeback_path)
            if multi_project_runtime_writeback_report and multi_project_runtime_writeback_path is not None
            else "",
        ),
        "native_authoring_solver_family_breadth_report_json": _first_text(
            solver_family_breadth_artifacts.get("native_authoring_solver_family_breadth_report_json"),
            str(solver_family_breadth_path)
            if solver_family_breadth_report and solver_family_breadth_path is not None
            else "",
        ),
        "native_authoring_writeback_breadth_report_json": _first_text(
            writeback_breadth_artifacts.get("native_authoring_writeback_breadth_report_json"),
            str(writeback_breadth_path)
            if writeback_breadth_report and writeback_breadth_path is not None
            else "",
        ),
        "project_ops_service_snapshot_json": _first_text(
            project_ops_service_artifacts.get("project_ops_service_snapshot_json"),
            project_ops_service_paths.get("snapshot_json"),
            str(project_ops_service_snapshot_path)
            if project_ops_service_snapshot_report and project_ops_service_snapshot_path is not None
            else "",
        ),
    }

    return {
        "native_authoring_evidence_attached": bool(native_authoring_evidence_attached),
        "native_authoring_commercialization_status": native_authoring_commercialization_status,
        "native_authoring_lane_ready": bool(native_authoring_lane_ready),
        "native_authoring_commercialization_summary_line": native_authoring_commercialization_summary_line,
        "native_authoring_workspace_summary_line": workspace_summary_line,
        "native_authoring_solver_session_pass": bool(solver_session_pass),
        "native_authoring_solver_session_authoring_ready": bool(solver_session_authoring_ready),
        "native_authoring_solver_session_summary_line": solver_summary_line,
        "native_authoring_solver_session_model_id": _first_text(
            solver_summary.get("model_id"),
            solver_authoring_summary.get("model_id"),
        ),
        "native_authoring_solver_session_family": _first_text(
            solver_summary.get("family"),
            load_combination_session.get("family"),
        ),
        "native_authoring_solver_session_mesh_request_count": int(solver_session_mesh_request_count),
        "native_authoring_solver_session_total_estimated_cells": int(solver_session_total_estimated_cells),
        "native_authoring_solver_session_combo_count": int(solver_session_combo_count),
        "native_authoring_solver_session_load_case_count": int(solver_session_load_case_count),
        "native_authoring_solver_session_loadcomb_line_count": int(solver_session_loadcomb_line_count),
        "native_authoring_ops_bundle_pass": bool(ops_bundle_pass),
        "native_authoring_ops_bundle_workspace_ready_pass": bool(ops_bundle_workspace_ready_pass),
        "native_authoring_ops_bundle_signature_verified": bool(ops_bundle_signature_verified),
        "native_authoring_ops_bundle_summary_line": ops_summary_line,
        "native_authoring_ops_bundle_workspace_source_mode": _first_text(
            ops_inputs.get("workspace_summary_source_mode")
        ),
        "native_authoring_ops_bundle_solver_source_mode": _first_text(
            ops_inputs.get("solver_session_source_mode")
        ),
        "native_authoring_ops_bundle_workspace_artifact_count": int(
            _first_int(ops_summary.get("workspace_artifact_count")) or 0
        ),
        "native_authoring_ops_bundle_solver_session_artifact_count": int(
            _first_int(ops_summary.get("solver_session_artifact_count")) or 0
        ),
        "native_authoring_ops_bundle_job_count": int(ops_bundle_job_count),
        "native_authoring_ops_bundle_snapshot_count": int(ops_bundle_snapshot_count),
        "native_authoring_ops_bundle_registry_artifact_count": int(
            ops_bundle_registry_artifact_count
        ),
        "native_authoring_ops_bundle_registry_approval_count": int(
            ops_bundle_registry_approval_count
        ),
        "native_authoring_ops_bundle_registry_package_sha256": _first_text(
            ops_summary.get("registry_package_sha256"),
            project_registry_summary.get("package_sha256"),
        ),
        "native_authoring_ops_bundle_registry_package_bytes": int(
            ops_bundle_registry_package_bytes
        ),
        "native_authoring_palette_section_count": int(len(_unique_sorted_tokens(section_palette))),
        "native_authoring_palette_family_count": int(len(palette_families)),
        "native_authoring_palette_family_label": _compact_label(palette_families),
        "native_authoring_active_section_count": int(len(_unique_sorted_tokens(active_section_ids))),
        "native_authoring_active_family_count": int(len(active_families)),
        "native_authoring_active_family_label": _compact_label(active_families),
        "native_authoring_member_type_count": int(len(member_types)),
        "native_authoring_member_type_label": _compact_label(member_types),
        "native_authoring_portfolio_attached": bool(native_authoring_portfolio_attached),
        "native_authoring_portfolio_summary_line": native_authoring_portfolio_summary_line,
        "native_authoring_portfolio_project_count": int(native_authoring_portfolio_project_count),
        "native_authoring_portfolio_complete_project_count": int(native_authoring_portfolio_complete_project_count),
        "native_authoring_portfolio_signature_verified_count": int(native_authoring_portfolio_signature_verified_count),
        "native_authoring_portfolio_package_reproducible_count": int(native_authoring_portfolio_package_reproducible_count),
        "native_authoring_portfolio_unmatched_input_count": int(native_authoring_portfolio_unmatched_input_count),
        "native_authoring_portfolio_family_count": int(native_authoring_portfolio_family_count),
        "native_authoring_portfolio_ready_family_count": int(native_authoring_portfolio_ready_family_count),
        "native_authoring_portfolio_release_ready_family_count": int(
            native_authoring_portfolio_release_ready_family_count
        ),
        "native_authoring_portfolio_failed_family_count": int(native_authoring_portfolio_failed_family_count),
        "native_authoring_portfolio_max_solver_combo_count": int(native_authoring_portfolio_max_solver_combo_count),
        "native_authoring_portfolio_max_solver_mesh_request_count": int(
            native_authoring_portfolio_max_solver_mesh_request_count
        ),
        "native_authoring_portfolio_family_status_label": native_authoring_portfolio_family_status_label,
        "native_authoring_family_corpus_attached": bool(native_authoring_family_corpus_attached),
        "native_authoring_family_corpus_pass": bool(native_authoring_family_corpus_pass),
        "native_authoring_family_corpus_summary_line": native_authoring_family_corpus_summary_line,
        "native_authoring_family_corpus_family_count": int(native_authoring_family_corpus_family_count),
        "native_authoring_family_corpus_ready_family_count": int(
            native_authoring_family_corpus_ready_family_count
        ),
        "native_authoring_family_corpus_public_reference_count": int(
            native_authoring_family_corpus_public_reference_count
        ),
        "native_authoring_family_corpus_design_reference_count": int(
            native_authoring_family_corpus_design_reference_count
        ),
        "native_authoring_family_corpus_benchmark_reference_count": int(
            native_authoring_family_corpus_benchmark_reference_count
        ),
        "native_authoring_family_corpus_authority_reference_count": int(
            native_authoring_family_corpus_authority_reference_count
        ),
        "native_authoring_family_corpus_surface_count": int(native_authoring_family_corpus_surface_count),
        "native_authoring_family_corpus_surface_label": native_authoring_family_corpus_surface_label,
        "native_authoring_family_corpus_unresolved_reference_count": int(
            native_authoring_family_corpus_unresolved_reference_count
        ),
        "native_authoring_family_corpus_unresolved_family_count": int(
            native_authoring_family_corpus_unresolved_family_count
        ),
        "native_authoring_family_local_evidence_attached": bool(
            native_authoring_family_local_evidence_attached
        ),
        "native_authoring_family_local_evidence_pass": bool(
            native_authoring_family_local_evidence_pass
        ),
        "native_authoring_family_local_evidence_summary_line": native_authoring_family_local_evidence_summary_line,
        "native_authoring_family_local_evidence_family_count": int(
            native_authoring_family_local_evidence_family_count
        ),
        "native_authoring_family_local_evidence_concrete_count": int(
            native_authoring_family_local_evidence_concrete_count
        ),
        "native_authoring_family_local_evidence_roundtrip_count": int(
            native_authoring_family_local_evidence_roundtrip_count
        ),
        "native_authoring_family_local_evidence_benchmark_concrete_count": int(
            native_authoring_family_local_evidence_benchmark_concrete_count
        ),
        "native_authoring_family_local_evidence_review_concrete_count": int(
            native_authoring_family_local_evidence_review_concrete_count
        ),
        "native_authoring_family_local_evidence_registered_only_count": int(
            native_authoring_family_local_evidence_registered_only_count
        ),
        "native_authoring_family_local_evidence_source_kind_count": int(
            native_authoring_family_local_evidence_source_kind_count
        ),
        "native_authoring_family_local_evidence_source_kind_label": native_authoring_family_local_evidence_source_kind_label,
        "native_authoring_family_tracks_attached": bool(native_authoring_family_tracks_attached),
        "native_authoring_family_tracks_summary_line": native_authoring_family_tracks_summary_line,
        "native_authoring_family_track_count": int(native_authoring_family_track_count),
        "native_authoring_family_track_ready_count": int(native_authoring_family_track_ready_count),
        "native_authoring_family_track_failed_count": int(
            max(native_authoring_family_track_count - native_authoring_family_track_ready_count, 0)
        ),
        "native_authoring_family_track_max_solver_combo_count": int(
            native_authoring_family_track_max_combo_count
        ),
        "native_authoring_family_track_max_solver_mesh_request_count": int(
            native_authoring_family_track_max_mesh_request_count
        ),
        "native_authoring_family_track_status_label": native_authoring_family_track_status_label,
        "native_authoring_runtime_submission_attached": bool(native_authoring_runtime_submission_attached),
        "native_authoring_runtime_submission_ready": bool(native_authoring_runtime_submission_ready),
        "native_authoring_runtime_submission_summary_line": native_authoring_runtime_submission_summary_line,
        "native_authoring_runtime_submission_count": int(native_authoring_runtime_submission_count),
        "native_authoring_runtime_submission_ready_count": int(native_authoring_runtime_submission_ready_count),
        "native_authoring_runtime_writeback_ready_count": int(native_authoring_runtime_writeback_ready_count),
        "native_authoring_runtime_submission_queue_count": int(native_authoring_runtime_submission_queue_count),
        "native_authoring_runtime_family_status_label": native_authoring_runtime_family_status_label,
        "native_authoring_runtime_submission_status_label": native_authoring_runtime_submission_status_label,
        "native_authoring_runtime_writeback_depth_attached": bool(
            native_authoring_runtime_writeback_depth_attached
        ),
        "native_authoring_runtime_writeback_depth_ready": bool(
            native_authoring_runtime_writeback_depth_ready
        ),
        "native_authoring_runtime_writeback_depth_summary_line": native_authoring_runtime_writeback_depth_summary_line,
        "native_authoring_runtime_writeback_depth_family_count": int(
            native_authoring_runtime_writeback_depth_family_count
        ),
        "native_authoring_runtime_writeback_depth_ready_family_count": int(
            native_authoring_runtime_writeback_depth_ready_family_count
        ),
        "native_authoring_runtime_writeback_depth_targeted_family_count": int(
            native_authoring_runtime_writeback_depth_targeted_family_count
        ),
        "native_authoring_runtime_writeback_depth_signature_family_count": int(
            native_authoring_runtime_writeback_depth_signature_family_count
        ),
        "native_authoring_runtime_writeback_depth_repro_family_count": int(
            native_authoring_runtime_writeback_depth_repro_family_count
        ),
        "native_authoring_runtime_writeback_depth_snapshot_family_count": int(
            native_authoring_runtime_writeback_depth_snapshot_family_count
        ),
        "native_authoring_runtime_writeback_depth_queue_clear_family_count": int(
            native_authoring_runtime_writeback_depth_queue_clear_family_count
        ),
        "native_authoring_runtime_writeback_depth_status_label": native_authoring_runtime_writeback_depth_status_label,
        "native_authoring_local_runtime_scenario_depth_attached": bool(
            native_authoring_local_runtime_scenario_depth_attached
        ),
        "native_authoring_local_runtime_scenario_depth_ready": bool(
            native_authoring_local_runtime_scenario_depth_ready
        ),
        "native_authoring_local_runtime_scenario_depth_summary_line": native_authoring_local_runtime_scenario_depth_summary_line,
        "native_authoring_local_runtime_scenario_depth_family_count": int(
            native_authoring_local_runtime_scenario_depth_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_ready_family_count": int(
            native_authoring_local_runtime_scenario_depth_ready_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_targeted_family_count": int(
            native_authoring_local_runtime_scenario_depth_targeted_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_trace_ready_family_count": int(
            native_authoring_local_runtime_scenario_depth_trace_ready_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_mesh_ready_family_count": int(
            native_authoring_local_runtime_scenario_depth_mesh_ready_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_runtime_ready_family_count": int(
            native_authoring_local_runtime_scenario_depth_runtime_ready_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_omitted_family_count": int(
            native_authoring_local_runtime_scenario_depth_omitted_family_count
        ),
        "native_authoring_local_runtime_scenario_depth_status_label": native_authoring_local_runtime_scenario_depth_status_label,
        "native_authoring_local_variant_writeback_trace_attached": bool(
            native_authoring_local_variant_writeback_trace_attached
        ),
        "native_authoring_local_variant_writeback_trace_ready": bool(
            native_authoring_local_variant_writeback_trace_ready
        ),
        "native_authoring_local_variant_writeback_trace_summary_line": native_authoring_local_variant_writeback_trace_summary_line,
        "native_authoring_local_variant_writeback_trace_family_count": int(
            native_authoring_local_variant_writeback_trace_family_count
        ),
        "native_authoring_local_variant_writeback_trace_ready_family_count": int(
            native_authoring_local_variant_writeback_trace_ready_family_count
        ),
        "native_authoring_local_variant_writeback_trace_targeted_family_count": int(
            native_authoring_local_variant_writeback_trace_targeted_family_count
        ),
        "native_authoring_local_variant_workspace_variant_ready_family_count": int(
            native_authoring_local_variant_workspace_variant_ready_family_count
        ),
        "native_authoring_local_variant_solver_variant_ready_family_count": int(
            native_authoring_local_variant_solver_variant_ready_family_count
        ),
        "native_authoring_local_variant_writeback_trace_ready_family_trace_count": int(
            native_authoring_local_variant_writeback_trace_ready_family_trace_count
        ),
        "native_authoring_local_variant_active_multi_family_count": int(
            native_authoring_local_variant_active_multi_family_count
        ),
        "native_authoring_local_variant_combo_multi_family_count": int(
            native_authoring_local_variant_combo_multi_family_count
        ),
        "native_authoring_local_variant_signed_writeback_family_count": int(
            native_authoring_local_variant_signed_writeback_family_count
        ),
        "native_authoring_local_variant_trace_omitted_family_count": int(
            native_authoring_local_variant_trace_omitted_family_count
        ),
        "native_authoring_local_variant_writeback_trace_status_label": native_authoring_local_variant_writeback_trace_status_label,
        "native_authoring_multi_project_runtime_writeback_attached": bool(
            native_authoring_multi_project_runtime_writeback_attached
        ),
        "native_authoring_multi_project_runtime_writeback_ready": bool(
            native_authoring_multi_project_runtime_writeback_ready
        ),
        "native_authoring_multi_project_runtime_writeback_summary_line": native_authoring_multi_project_runtime_writeback_summary_line,
        "native_authoring_multi_project_runtime_writeback_project_count": int(
            native_authoring_multi_project_runtime_writeback_project_count
        ),
        "native_authoring_multi_project_runtime_writeback_project_family_count": int(
            native_authoring_multi_project_runtime_writeback_project_family_count
        ),
        "native_authoring_multi_project_runtime_writeback_full_count": int(
            native_authoring_multi_project_runtime_writeback_full_count
        ),
        "native_authoring_multi_project_runtime_writeback_ready_project_count": int(
            native_authoring_multi_project_runtime_writeback_ready_project_count
        ),
        "native_authoring_multi_project_runtime_writeback_signature_project_count": int(
            native_authoring_multi_project_runtime_writeback_signature_project_count
        ),
        "native_authoring_multi_project_runtime_writeback_repro_project_count": int(
            native_authoring_multi_project_runtime_writeback_repro_project_count
        ),
        "native_authoring_multi_project_runtime_writeback_snapshot_project_count": int(
            native_authoring_multi_project_runtime_writeback_snapshot_project_count
        ),
        "native_authoring_multi_project_runtime_writeback_queue_clear_project_count": int(
            native_authoring_multi_project_runtime_writeback_queue_clear_project_count
        ),
        "native_authoring_multi_project_runtime_writeback_status_label": native_authoring_multi_project_runtime_writeback_status_label,
        "native_authoring_solver_family_breadth_attached": bool(
            native_authoring_solver_family_breadth_attached
        ),
        "native_authoring_solver_family_breadth_ready": bool(
            native_authoring_solver_family_breadth_ready
        ),
        "native_authoring_solver_family_breadth_summary_line": native_authoring_solver_family_breadth_summary_line,
        "native_authoring_solver_family_breadth_family_count": int(
            native_authoring_solver_family_breadth_family_count
        ),
        "native_authoring_solver_family_breadth_ready_family_count": int(
            native_authoring_solver_family_breadth_ready_family_count
        ),
        "native_authoring_solver_family_breadth_full_family_count": int(
            native_authoring_solver_family_breadth_full_family_count
        ),
        "native_authoring_solver_family_breadth_mesh_broad_family_count": int(
            native_authoring_solver_family_breadth_mesh_broad_family_count
        ),
        "native_authoring_solver_family_breadth_member_multi_family_count": int(
            native_authoring_solver_family_breadth_member_multi_family_count
        ),
        "native_authoring_solver_family_breadth_status_label": native_authoring_solver_family_breadth_status_label,
        "native_authoring_writeback_breadth_attached": bool(native_authoring_writeback_breadth_attached),
        "native_authoring_writeback_breadth_ready": bool(native_authoring_writeback_breadth_ready),
        "native_authoring_writeback_breadth_summary_line": native_authoring_writeback_breadth_summary_line,
        "native_authoring_writeback_breadth_family_count": int(native_authoring_writeback_breadth_family_count),
        "native_authoring_writeback_breadth_ready_family_count": int(
            native_authoring_writeback_breadth_ready_family_count
        ),
        "native_authoring_writeback_breadth_full_family_count": int(
            native_authoring_writeback_breadth_full_family_count
        ),
        "native_authoring_writeback_breadth_mesh_broad_family_count": int(
            native_authoring_writeback_breadth_mesh_broad_family_count
        ),
        "native_authoring_writeback_breadth_status_label": native_authoring_writeback_breadth_status_label,
        "project_ops_service_attached": bool(project_ops_service_attached),
        "project_ops_service_ready": bool(project_ops_service_ready),
        "project_ops_service_summary_line": project_ops_service_summary_line,
        "project_ops_service_project_count": int(project_ops_service_project_count),
        "project_ops_service_family_count": int(project_ops_service_family_count),
        "project_ops_service_ready_family_count": int(project_ops_service_ready_family_count),
        "project_ops_service_endpoint_count": int(project_ops_service_endpoint_count),
        "project_ops_service_family_status_label": project_ops_service_family_status_label,
        "native_authoring_ready_family_count_alignment_label": native_authoring_ready_family_count_alignment_label,
        "native_authoring_family_status_alignment_label": native_authoring_family_status_alignment_label,
        "native_authoring_surface_consistency_ready": bool(native_authoring_surface_consistency_ready),
        "native_authoring_surface_consistency_summary_line": native_authoring_surface_consistency_summary_line,
        "native_authoring_surface_consistency_expected_family_count": int(
            native_authoring_surface_consistency_expected_family_count
        ),
        "native_authoring_surface_consistency_aligned_family_count": int(
            native_authoring_surface_consistency_aligned_family_count
        ),
        "native_authoring_surface_consistency_status_label": native_authoring_surface_consistency_status_label,
        "artifacts": artifacts,
    }


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    try:
        denominator_value = float(denominator)
    except Exception:
        denominator_value = 0.0
    if denominator_value <= 0.0:
        return 0.0
    try:
        return float(numerator) / denominator_value
    except Exception:
        return 0.0


def _peer_blind_prediction_compare_surface(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    results_explorer = (
        report.get("results_explorer") if isinstance(report.get("results_explorer"), dict) else {}
    )
    case_count = _first_int(
        summary.get("case_count"),
        summary.get("build_case_count"),
        report.get("case_count"),
        report.get("build_case_count"),
    ) or 0
    build_case_count = _first_int(
        summary.get("build_case_count"),
        report.get("build_case_count"),
        case_count,
    ) or 0
    measured_response_ready = _first_bool(
        summary.get("measured_response_ready"),
        report.get("measured_response_ready"),
    )
    acceleration_channel_count = _first_int(
        summary.get("acceleration_channel_count"),
        report.get("acceleration_channel_count"),
    ) or 0
    drift_channel_count = _first_int(
        summary.get("drift_channel_count"),
        report.get("drift_channel_count"),
    ) or 0
    channel_count = max(acceleration_channel_count, drift_channel_count)
    if measured_response_ready is None:
        measured_response_ready = bool(_pass(report) and channel_count > 0)
    status_label = "READY" if measured_response_ready else "PENDING"
    measured_response_label = "ready" if measured_response_ready else "pending"
    summary_line = _first_text(report.get("summary_line"))
    if not summary_line and (case_count or channel_count or measured_response_ready is not None):
        summary_line = (
            f"PEER blind compare lane: {status_label} | cases={case_count} | "
            f"measured_response={measured_response_label} | channels={channel_count}"
        )
    return {
        "summary_line": summary_line,
        "contract_pass": bool(_pass(report)),
        "case_count": int(case_count),
        "build_case_count": int(build_case_count),
        "measured_response_ready": bool(measured_response_ready),
        "acceleration_channel_count": int(acceleration_channel_count),
        "drift_channel_count": int(drift_channel_count),
        "channel_count": int(channel_count),
        "entry_kind": _first_text(results_explorer.get("entry_kind")),
        "entry_label": _first_text(results_explorer.get("entry_label")),
        "source_family": _first_text(results_explorer.get("source_family")),
        "summary_label": _first_text(results_explorer.get("summary_label")),
        "reason_code": str(report.get("reason_code", "") or "").strip(),
    }


def _peer_blind_prediction_measured_response_landing_surface(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    matched_files = [str(item) for item in (report.get("matched_files") or []) if str(item or "").strip()]
    expected_patterns = [
        str(item) for item in (report.get("expected_patterns") or []) if str(item or "").strip()
    ]
    matched_file_count = _first_int(
        summary.get("matched_file_count"),
        report.get("matched_file_count"),
        report.get("matched"),
        len(matched_files),
    ) or 0
    csv_file_count = _first_int(
        summary.get("csv_file_count"),
        report.get("csv_file_count"),
    ) or 0
    acceleration_candidate_count = _first_int(
        summary.get("acceleration_candidate_count"),
        report.get("acceleration_candidate_count"),
    ) or 0
    drift_candidate_count = _first_int(
        summary.get("drift_candidate_count"),
        report.get("drift_candidate_count"),
    ) or 0
    sensor_candidate_count = _first_int(
        summary.get("sensor_candidate_count"),
        report.get("sensor_candidate_count"),
    ) or 0
    expected_pattern_count = _first_int(
        report.get("expected_pattern_count"),
        report.get("patterns"),
        len(expected_patterns),
    ) or 0
    input_root = _first_text(report.get("input_root"), report.get("root"), report.get("landing_root"))
    root_name = Path(input_root).name if input_root else _first_text(report.get("root_name"))
    landing_state = _first_text(report.get("landing_state"), report.get("state"))
    contract_pass = _first_bool(
        report.get("contract_pass"),
        report.get("measured_response_present"),
    )
    if contract_pass is None:
        contract_pass = matched_file_count > 0
    required_group_pass_count = _first_int(
        report.get("required_group_pass_count"),
        report.get("group_pass_count"),
    )
    required_group_count = _first_int(
        report.get("required_group_count"),
        report.get("group_count"),
    )
    summary_line = _first_text(report.get("summary_line"))
    if not summary_line and (
        matched_file_count
        or expected_pattern_count
        or root_name
        or required_group_pass_count is not None
        or required_group_count is not None
    ):
        parts = [
            f"E-Defense/PEER measured-response landing: {'PASS' if contract_pass else 'PENDING'}",
            f"matched={matched_file_count}",
            f"patterns={expected_pattern_count}",
        ]
        if required_group_pass_count is not None and required_group_count is not None:
            parts.append(f"groups={required_group_pass_count}/{required_group_count}")
        if root_name:
            parts.append(f"root={root_name}")
        summary_line = " | ".join(parts)
    return {
        "summary_line": summary_line,
        "contract_pass": bool(contract_pass),
        "landing_state": landing_state,
        "matched_file_count": int(matched_file_count),
        "csv_file_count": int(csv_file_count),
        "acceleration_candidate_count": int(acceleration_candidate_count),
        "drift_candidate_count": int(drift_candidate_count),
        "sensor_candidate_count": int(sensor_candidate_count),
        "expected_pattern_count": int(expected_pattern_count),
        "required_group_pass_count": int(required_group_pass_count or 0),
        "required_group_count": int(required_group_count or 0),
        "root_name": root_name,
        "next_action": _first_text(report.get("next_action")),
        "reason_code": str(report.get("reason_code", "") or "").strip(),
    }


def _panel_zone_external_validation_coverage_surface(summary: dict[str, Any]) -> dict[str, Any]:
    source_valid_row_counts = (
        summary.get("panel_zone_source_valid_row_counts")
        if isinstance(summary.get("panel_zone_source_valid_row_counts"), dict)
        else {}
    )
    source_overlap_member_counts = (
        summary.get("panel_zone_source_overlap_member_counts")
        if isinstance(summary.get("panel_zone_source_overlap_member_counts"), dict)
        else {}
    )
    source_bundle_modes = (
        summary.get("panel_zone_source_bundle_modes")
        if isinstance(summary.get("panel_zone_source_bundle_modes"), dict)
        else {}
    )
    source_upstream_verification_tiers = (
        summary.get("panel_zone_source_upstream_verification_tiers")
        if isinstance(summary.get("panel_zone_source_upstream_verification_tiers"), dict)
        else {}
    )
    source_names = list(REQUIRED_PANEL_ZONE_SOURCES)
    for mapping in (
        source_valid_row_counts,
        source_overlap_member_counts,
        source_bundle_modes,
        source_upstream_verification_tiers,
    ):
        for key in mapping.keys():
            normalized = str(key or "").strip()
            if normalized and normalized not in source_names:
                source_names.append(normalized)

    source_count = _first_int(
        summary.get("panel_zone_external_validation_source_count"),
        len(source_names),
    ) or len(source_names)
    validated_source_count = _first_int(
        summary.get("panel_zone_external_validation_validated_source_count"),
    )
    exact_source_count = _first_int(
        summary.get("panel_zone_external_validation_exact_source_count"),
    )
    fallback_source_count = _first_int(
        summary.get("panel_zone_external_validation_fallback_source_count"),
    )
    missing_source_count = _first_int(
        summary.get("panel_zone_external_validation_missing_source_count"),
        len(
            [
                value
                for value in (summary.get("panel_zone_missing_required_sources") or [])
                if str(value or "").strip()
            ]
        ),
    )
    unknown_source_count = _first_int(
        summary.get("panel_zone_external_validation_unknown_source_count"),
    )

    verified = panel_zone_external_validation_artifact_closed(summary)
    pending = bool(summary.get("panel_zone_external_validation_pending", False))
    internal_complete = bool(summary.get("panel_zone_internal_engine_complete", False))

    if exact_source_count is None:
        exact_source_count = source_count if verified and source_count > 0 else 0
    if fallback_source_count is None:
        fallback_source_count = (
            max(source_count - exact_source_count - int(missing_source_count or 0), 0)
            if pending and internal_complete
            else 0
        )
    if validated_source_count is None:
        validated_source_count = exact_source_count + fallback_source_count
    if unknown_source_count is None:
        unknown_source_count = max(
            source_count - validated_source_count - int(missing_source_count or 0),
            0,
        )

    candidate_member_count = _first_int(
        summary.get("panel_zone_external_validation_candidate_member_count"),
        summary.get("panel_zone_proxy_candidate_count"),
        summary.get("panel_zone_validated_source_overlap_member_count_min"),
    ) or 0
    validated_member_count = _first_int(
        summary.get("panel_zone_external_validation_validated_member_count"),
        summary.get("panel_zone_validated_source_overlap_member_count_min"),
    ) or 0
    exact_member_count = _first_int(
        summary.get("panel_zone_external_validation_exact_member_count"),
        validated_member_count if exact_source_count == source_count and source_count > 0 else 0,
    ) or 0
    fallback_member_count = _first_int(
        summary.get("panel_zone_external_validation_fallback_member_count"),
        validated_member_count if fallback_source_count > 0 and exact_member_count == 0 else max(validated_member_count - exact_member_count, 0),
    ) or 0

    validated_row_count_total = _first_int(
        summary.get("panel_zone_external_validation_validated_row_count_total"),
        summary.get("panel_zone_validated_source_row_count_total"),
    ) or 0
    exact_validated_row_count = _first_int(
        summary.get("panel_zone_external_validation_exact_validated_row_count"),
        validated_row_count_total if exact_source_count == source_count and source_count > 0 else 0,
    ) or 0
    fallback_validated_row_count = _first_int(
        summary.get("panel_zone_external_validation_fallback_validated_row_count"),
        validated_row_count_total if fallback_source_count > 0 and exact_validated_row_count == 0 else max(validated_row_count_total - exact_validated_row_count, 0),
    ) or 0

    summary_label = str(summary.get("panel_zone_external_validation_provenance_summary_label", "") or "").strip()
    if not summary_label:
        summary_label = (
            f"validated_sources={validated_source_count}/{source_count} | "
            f"exact_sources={exact_source_count}/{source_count} | "
            f"fallback_sources={fallback_source_count}/{source_count} | "
            f"missing_sources={int(missing_source_count or 0)}/{source_count} | "
            f"validated_members={validated_member_count}/{candidate_member_count} | "
            f"exact_members={exact_member_count}/{candidate_member_count} | "
            f"fallback_members={fallback_member_count}/{candidate_member_count} | "
            f"exact_rows={exact_validated_row_count}/{validated_row_count_total} | "
            f"fallback_rows={fallback_validated_row_count}/{validated_row_count_total}"
        )

    closure_surface = build_panel_zone_external_validation_provenance_surface(
        {
            **summary,
            "panel_zone_external_validation_source_count": int(source_count),
            "panel_zone_external_validation_validated_source_count": int(validated_source_count),
            "panel_zone_external_validation_exact_source_count": int(exact_source_count),
            "panel_zone_external_validation_fallback_source_count": int(fallback_source_count),
            "panel_zone_external_validation_missing_source_count": int(missing_source_count or 0),
            "panel_zone_external_validation_unknown_source_count": int(unknown_source_count),
            "panel_zone_external_validation_candidate_member_count": int(candidate_member_count),
            "panel_zone_external_validation_validated_member_count": int(validated_member_count),
            "panel_zone_external_validation_exact_member_count": int(exact_member_count),
            "panel_zone_external_validation_fallback_member_count": int(fallback_member_count),
            "panel_zone_external_validation_validated_row_count_total": int(validated_row_count_total),
            "panel_zone_external_validation_exact_validated_row_count": int(exact_validated_row_count),
            "panel_zone_external_validation_fallback_validated_row_count": int(
                fallback_validated_row_count
            ),
            "panel_zone_external_validation_provenance_summary_label": summary_label,
        }
    )

    return {
        "source_count": int(source_count),
        "validated_source_count": int(validated_source_count),
        "exact_source_count": int(exact_source_count),
        "fallback_source_count": int(fallback_source_count),
        "missing_source_count": int(missing_source_count or 0),
        "unknown_source_count": int(unknown_source_count),
        "validated_source_ratio": float(_safe_ratio(validated_source_count, source_count)),
        "exact_source_ratio": float(_safe_ratio(exact_source_count, source_count)),
        "fallback_source_ratio": float(_safe_ratio(fallback_source_count, source_count)),
        "candidate_member_count": int(candidate_member_count),
        "validated_member_count": int(validated_member_count),
        "exact_member_count": int(exact_member_count),
        "fallback_member_count": int(fallback_member_count),
        "validated_member_ratio": float(_safe_ratio(validated_member_count, candidate_member_count)),
        "exact_member_ratio": float(_safe_ratio(exact_member_count, candidate_member_count)),
        "fallback_member_ratio": float(_safe_ratio(fallback_member_count, candidate_member_count)),
        "validated_row_count_total": int(validated_row_count_total),
        "exact_validated_row_count": int(exact_validated_row_count),
        "fallback_validated_row_count": int(fallback_validated_row_count),
        "exact_validated_row_ratio": float(_safe_ratio(exact_validated_row_count, validated_row_count_total)),
        "fallback_validated_row_ratio": float(_safe_ratio(fallback_validated_row_count, validated_row_count_total)),
        "provenance_summary_label": summary_label,
        "artifact_closed": bool(closure_surface["artifact_closed"]),
        "closure_mode": str(closure_surface["closure_mode"]),
    }


def _extract_optional_gate_surface(*sources: dict[str, Any], stem: str) -> tuple[str, bool | None]:
    summary_line = ""
    gate_pass: bool | None = None
    summary_line_keys = (f"{stem}_summary_line", f"{stem}_gate_summary_line")
    pass_keys = (f"{stem}_pass", f"{stem}_gate_pass")
    report_keys = (f"{stem}_report", f"{stem}_gate_report")

    for source in sources:
        if not isinstance(source, dict):
            continue
        report_payload = next(
            (
                source.get(key)
                for key in report_keys
                if isinstance(source.get(key), dict)
            ),
            {},
        )
        if not summary_line:
            for key in summary_line_keys:
                text = str(source.get(key, "") or "").strip()
                if text:
                    summary_line = text
                    break
            if not summary_line and isinstance(report_payload, dict):
                summary_line = str(report_payload.get("summary_line", "") or "").strip()
        if gate_pass is None:
            for key in pass_keys:
                if key in source:
                    gate_pass = bool(source.get(key))
                    break
            if gate_pass is None and isinstance(report_payload, dict) and any(
                key in report_payload for key in ("contract_pass", "all_pass", "pass")
            ):
                gate_pass = _pass(report_payload)
    return summary_line, gate_pass


def _format_optional_gate_surface(summary_line: str, gate_pass: bool | None) -> str:
    text = str(summary_line or "").strip()
    if gate_pass is None:
        return text
    if text:
        return f"pass={bool(gate_pass)} | {text}"
    return f"pass={bool(gate_pass)}"


def _summary_payload(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("summary") if isinstance(report.get("summary"), dict) else {}


def _extract_gate_surface_with_report(
    *sources: dict[str, Any],
    stem: str,
    direct_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_payload: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        report_payload = next(
            (
                candidate
                for candidate in (
                    source.get(f"{stem}_report"),
                    source.get(f"{stem}_gate_report"),
                )
                if isinstance(candidate, dict)
            ),
            {},
        )
        if report_payload:
            break
    if not report_payload and isinstance(direct_report, dict):
        report_payload = direct_report
    summary_line, gate_pass = _extract_optional_gate_surface(*sources, stem=stem)
    summary_payload = _summary_payload(report_payload)
    if not summary_line:
        summary_line = _first_text(
            report_payload.get("summary_line"),
            summary_payload.get("summary_line"),
        )
    if gate_pass is None and report_payload and any(
        key in report_payload for key in ("contract_pass", "all_pass", "pass")
    ):
        gate_pass = _pass(report_payload)
    return {
        "report": report_payload,
        "summary": summary_payload,
        "summary_line": summary_line,
        "pass": gate_pass,
    }


def _extract_geometry_bridge_signal_surface(
    *sources: dict[str, Any],
    stem: str,
) -> dict[str, Any]:
    prefix = f"midas_kds_geometry_bridge_{stem}"
    count: int | None = None
    expected: int | None = None
    status = ""
    signal_summary_line = ""
    gate_pass: bool | None = None
    geometry_summary_line = ""

    for source in sources:
        if not isinstance(source, dict):
            continue
        if not geometry_summary_line:
            geometry_summary_line = str(source.get("midas_kds_geometry_bridge_summary_line", "") or "").strip()
        if not signal_summary_line:
            signal_summary_line = str(source.get(f"{prefix}_summary_line", "") or "").strip()
        if count is None and f"{prefix}_count" in source:
            count = int(source.get(f"{prefix}_count", 0) or 0)
        if expected is None and f"{prefix}_expected" in source:
            expected = int(source.get(f"{prefix}_expected", 0) or 0)
        if not status:
            status = str(source.get(f"{prefix}_status", "") or "").strip()
        if gate_pass is None and f"{prefix}_pass" in source:
            value = source.get(f"{prefix}_pass")
            gate_pass = None if value is None else bool(value)

    parsed_match = re.search(
        rf"({re.escape(stem)}=(\d+)/(\d+)\s+(PASS|CHECK))",
        signal_summary_line or geometry_summary_line,
    )
    if parsed_match:
        if not signal_summary_line:
            signal_summary_line = str(parsed_match.group(1))
        if count is None:
            count = int(parsed_match.group(2))
        if expected is None:
            expected = int(parsed_match.group(3))
        if not status:
            status = str(parsed_match.group(4))
        if gate_pass is None:
            gate_pass = str(parsed_match.group(4)) == "PASS"

    if not signal_summary_line and count is not None and expected is not None and status:
        signal_summary_line = f"{stem}={count}/{expected} {status}"

    return {
        "summary_line": signal_summary_line,
        "count": int(count or 0),
        "expected": int(expected or 0),
        "status": status,
        "pass": gate_pass,
    }


def _extract_support_search_surface(summary_line: str) -> dict[str, Any]:
    text = str(summary_line or "").strip()
    match = re.search(
        r"support_search=(\d+)\s*\|\s*node_surface_proxy=(\d+)\s*\|\s*support_depth=(\d+)",
        text,
    )
    support_search_count = int(match.group(1)) if match else 0
    node_surface_proxy_count = int(match.group(2)) if match else 0
    support_depth_score = int(match.group(3)) if match else 0
    status = "PASS" if support_search_count and node_surface_proxy_count else "CHECK"
    if not text:
        text = (
            f"Support search: {status} | support_search={support_search_count} | "
            f"node_surface_proxy={node_surface_proxy_count} | support_depth={support_depth_score}"
        )
    return {
        "summary_line": text,
        "support_search_count": support_search_count,
        "node_surface_proxy_count": node_surface_proxy_count,
        "support_depth_score": support_depth_score,
        "pass": bool(support_search_count and node_surface_proxy_count),
    }


def _compact_general_fe_contact_matrix_summary_label(summary_line: str) -> str:
    text = str(summary_line or "").strip()
    if not text:
        return ""
    text = re.sub(r"^General FE contact matrix:\s*(?:PASS|CHECK)\s*\|\s*", "", text)
    return text.strip()


def _extract_general_fe_contact_surface(
    *sources: dict[str, Any],
    fallback_summary_line: str = "",
) -> dict[str, Any]:
    compact_summary_label = _first_text(
        *[
            source.get("results_explorer_traceability_general_fe_contact_compact_summary_label", "")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_surface_summary_line", "")
            for source in sources
            if isinstance(source, dict)
        ],
    )
    long_summary_line = _first_text(
        *[
            source.get("results_explorer_traceability_general_fe_contact_matrix_summary_line", "")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_matrix_summary_line", "")
            for source in sources
            if isinstance(source, dict)
        ],
        fallback_summary_line,
    )
    parse_source = compact_summary_label or _compact_general_fe_contact_matrix_summary_label(long_summary_line)

    def _match_int(pattern: str) -> int:
        match = re.search(pattern, parse_source)
        return int(match.group(1)) if match else 0

    support_search_count = _first_int(
        *[
            source.get("general_fe_contact_support_search_count")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("support_search_count")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"support_search=(\d+)"),
    )
    node_surface_proxy_count = _first_int(
        *[
            source.get("general_fe_contact_node_surface_proxy_count")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("node_surface_proxy_count")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"node_surface_proxy=(\d+)"),
    )
    support_depth_score = _first_int(
        *[
            source.get("general_fe_contact_support_depth_score")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("support_depth_score")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"support_depth=(\d+)"),
    )
    coupling_depth_value = _first_int(
        *[
            source.get("results_explorer_traceability_general_fe_contact_coupling_depth_value")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_coupling_depth_value")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_coupling_depth_score")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"coupling[_ ]depth=(\d+)"),
    )
    support_family_count = _first_int(
        *[
            source.get("results_explorer_traceability_general_fe_contact_support_family_count")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_support_family_count")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"support families=(\d+)"),
        _match_int(r"support_families=(\d+)(?:/\d+)?"),
    )
    support_family_expected_count = _first_int(
        *[
            source.get("results_explorer_traceability_general_fe_contact_support_family_expected_count")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_support_family_required_count")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"support_families=\d+/(\d+)"),
        support_family_count,
    )
    proxy_family_count = _first_int(
        *[
            source.get("results_explorer_traceability_general_fe_contact_proxy_family_count")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_proxy_family_count")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"proxy families=(\d+)"),
        _match_int(r"proxy_families=(\d+)(?:/\d+)?"),
    )
    proxy_family_expected_count = _first_int(
        *[
            source.get("results_explorer_traceability_general_fe_contact_proxy_family_expected_count")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_proxy_family_required_count")
            for source in sources
            if isinstance(source, dict)
        ],
        _match_int(r"proxy_families=\d+/(\d+)"),
        proxy_family_count,
    )
    surface_pass = _first_bool(
        *[
            source.get("results_explorer_general_fe_contact_surface_pass")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("general_fe_contact_surface_pass")
            for source in sources
            if isinstance(source, dict)
        ],
        bool(support_search_count or coupling_depth_value or support_family_count or proxy_family_count),
    )
    support_search_count = int(support_search_count or 0)
    node_surface_proxy_count = int(node_surface_proxy_count or 0)
    support_depth_score = int(support_depth_score or 0)
    coupling_depth_value = int(coupling_depth_value or 0)
    support_family_count = int(support_family_count or 0)
    support_family_expected_count = int(support_family_expected_count or 0)
    proxy_family_count = int(proxy_family_count or 0)
    proxy_family_expected_count = int(proxy_family_expected_count or 0)
    if not compact_summary_label:
        parts = [
            part
            for part in (
                f"support_search={support_search_count}" if support_search_count else "",
                f"node_surface_proxy={node_surface_proxy_count}" if node_surface_proxy_count else "",
                f"support_depth={support_depth_score}" if support_depth_score else "",
                f"coupling_depth={coupling_depth_value}" if coupling_depth_value else "",
                (
                    f"support_families={support_family_count}"
                    f"{'/' + str(support_family_expected_count) if support_family_expected_count else ''}"
                    if support_family_count
                    else ""
                ),
                (
                    f"proxy_families={proxy_family_count}"
                    f"{'/' + str(proxy_family_expected_count) if proxy_family_expected_count else ''}"
                    if proxy_family_count
                    else ""
                ),
            )
            if part
        ]
        compact_summary_label = " | ".join(parts)
    status = "PASS" if bool(surface_pass) else "CHECK"
    return {
        "summary_label": compact_summary_label,
        "surface_label": f"General FE compact: {status}" + (f" | {compact_summary_label}" if compact_summary_label else ""),
        "pass": bool(surface_pass),
        "support_search_count": support_search_count,
        "node_surface_proxy_count": node_surface_proxy_count,
        "support_depth_score": support_depth_score,
        "coupling_depth_value": coupling_depth_value,
        "support_family_count": support_family_count,
        "support_family_expected_count": support_family_expected_count,
        "proxy_family_count": proxy_family_count,
        "proxy_family_expected_count": proxy_family_expected_count,
    }


def _extract_support_search_surface_from_sources(
    *sources: dict[str, Any],
    fallback_summary_line: str = "",
) -> dict[str, Any]:
    normalized_summary_line = _first_text(
        *[
            source.get("support_search_summary_line", "")
            for source in sources
            if isinstance(source, dict)
        ],
        fallback_summary_line,
    )
    parsed_surface = _extract_support_search_surface(normalized_summary_line)
    support_search_count = _first_int(
        *[
            source.get("support_search_count")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_surface.get("support_search_count"),
    )
    node_surface_proxy_count = _first_int(
        *[
            source.get("node_surface_proxy_count")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_surface.get("node_surface_proxy_count"),
    )
    support_depth_score = _first_int(
        *[
            source.get("support_depth_score")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_surface.get("support_depth_score"),
    )
    support_search_pass = _first_bool(
        *[
            source.get("support_search_pass")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_surface.get("pass"),
        bool(support_search_count),
    )
    node_surface_proxy_pass = _first_bool(
        *[
            source.get("node_surface_proxy_pass")
            for source in sources
            if isinstance(source, dict)
        ],
        bool(node_surface_proxy_count),
    )
    support_search_count = int(support_search_count or 0)
    node_surface_proxy_count = int(node_surface_proxy_count or 0)
    support_depth_score = int(support_depth_score or 0)
    status = "PASS" if bool(support_search_pass and node_surface_proxy_pass) else "CHECK"
    summary_line = normalized_summary_line or (
        f"Support search: {status} | support_search={support_search_count} | "
        f"node_surface_proxy={node_surface_proxy_count} | support_depth={support_depth_score}"
    )
    detail_label = (
        f"support_search={support_search_count} | "
        f"node_surface_proxy={node_surface_proxy_count} | support_depth={support_depth_score}"
    )
    return {
        "summary_line": summary_line,
        "detail_label": detail_label,
        "surface_label": f"Support search: {status} | {detail_label}",
        "support_search_count": support_search_count,
        "node_surface_proxy_count": node_surface_proxy_count,
        "support_depth_score": support_depth_score,
        "support_search_pass": bool(support_search_pass),
        "node_surface_proxy_pass": bool(node_surface_proxy_pass),
        "status": status,
        "pass": bool(support_search_pass and node_surface_proxy_pass),
    }


def _extract_workflow_contact_coupling_surface(
    *sources: dict[str, Any],
    fallback_summary_line: str = "",
) -> dict[str, Any]:
    normalized_summary_label = _first_text(
        *[
            source.get("results_explorer_traceability_contact_coupling_summary_label", "")
            for source in sources
            if isinstance(source, dict)
        ],
        *[
            source.get("results_explorer_traceability_contact_material_depth_summary_label", "")
            for source in sources
            if isinstance(source, dict)
        ],
        fallback_summary_line,
    )
    match = re.search(
        r"support families=(\d+)\s*\|\s*proxy families=(\d+)\s*\|\s*assembled depth=(\d+)",
        normalized_summary_label,
    )
    parsed_support_family_count = int(match.group(1)) if match else 0
    parsed_proxy_family_count = int(match.group(2)) if match else 0
    parsed_assembled_depth_value = int(match.group(3)) if match else 0
    support_family_count = _first_int(
        *[
            source.get("results_explorer_traceability_contact_support_family_count")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_support_family_count,
    )
    proxy_family_count = _first_int(
        *[
            source.get("results_explorer_traceability_contact_proxy_family_count")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_proxy_family_count,
    )
    assembled_depth_value = _first_int(
        *[
            source.get("results_explorer_traceability_contact_assembled_depth_value")
            for source in sources
            if isinstance(source, dict)
        ],
        parsed_assembled_depth_value,
    )
    support_family_count = int(support_family_count or 0)
    proxy_family_count = int(proxy_family_count or 0)
    assembled_depth_value = int(assembled_depth_value or 0)
    detail_label = normalized_summary_label.strip()
    if not detail_label and (support_family_count or proxy_family_count or assembled_depth_value):
        detail_label = (
            f"support families={support_family_count} | "
            f"proxy families={proxy_family_count} | "
            f"assembled depth={assembled_depth_value}"
        )
    coupling_pass = _first_bool(
        *[
            source.get("results_explorer_contact_coupling_pass")
            for source in sources
            if isinstance(source, dict)
        ],
        bool(support_family_count and proxy_family_count and assembled_depth_value),
    )
    status = "PASS" if bool(coupling_pass) else "CHECK"
    summary_line = f"Workflow contact coupling: {status}"
    if detail_label:
        summary_line = f"{summary_line} | {detail_label}"
    return {
        "summary_line": summary_line if detail_label or support_family_count or proxy_family_count or assembled_depth_value else "",
        "detail_label": detail_label,
        "support_family_count": support_family_count,
        "proxy_family_count": proxy_family_count,
        "assembled_depth_value": assembled_depth_value,
        "pass": bool(coupling_pass),
        "status": status,
    }


def _ndtha_material_surface(ndtha_stress: dict[str, Any]) -> dict[str, Any]:
    material_rows = [
        row
        for row in (ndtha_stress.get("material_effect_rows") if isinstance(ndtha_stress.get("material_effect_rows"), list) else [])
        if isinstance(row, dict)
    ]
    summary = ndtha_stress.get("summary") if isinstance(ndtha_stress.get("summary"), dict) else {}
    checks = ndtha_stress.get("checks") if isinstance(ndtha_stress.get("checks"), dict) else {}
    material_model = str(summary.get("material_model", "") or "").strip()
    material_pass_count = sum(1 for row in material_rows if bool(row.get("material_model_pass", False)))
    material_pass = bool(checks.get("material_model_pass", bool(material_rows) and material_pass_count == len(material_rows)))
    summary_line = (
        f"NDTHA material: {'PASS' if material_pass else 'CHECK'} | "
        f"material_model={material_model or 'unknown'} | "
        f"material_effect_rows={len(material_rows)} | "
        f"material_model_pass={material_pass_count}/{len(material_rows)}"
    )
    return {
        "summary_line": summary_line,
        "material_depth": len(material_rows),
        "material_model": material_model,
        "material_pass": material_pass,
        "material_model_pass_count": material_pass_count,
    }


def _extract_ndtha_surface_from_sources(
    ndtha_stress: dict[str, Any],
    *sources: dict[str, Any],
) -> dict[str, Any]:
    ndtha_stress_rows = ndtha_stress.get("rows") if isinstance(ndtha_stress.get("rows"), list) else []
    derived_step_series_depth = max(
        [
            int(row.get("summary", {}).get("step_count_completed", 0) or 0)
            for row in ndtha_stress_rows
            if isinstance(row, dict)
        ]
        or [0]
    )
    derived_surface = _ndtha_material_surface(ndtha_stress)
    step_series_depth = _first_int(
        *[
            source.get("ndtha_step_series_depth")
            for source in sources
            if isinstance(source, dict)
        ],
        derived_step_series_depth,
    )
    material_depth = _first_int(
        *[
            source.get("ndtha_material_depth")
            for source in sources
            if isinstance(source, dict)
        ],
        derived_surface.get("material_depth"),
    )
    material_pass = _first_bool(
        *[
            source.get("ndtha_material_pass")
            for source in sources
            if isinstance(source, dict)
        ],
        derived_surface.get("material_pass"),
    )
    material_summary_line = _first_text(
        *[
            source.get("ndtha_material_summary_line", "")
            for source in sources
            if isinstance(source, dict)
        ],
        derived_surface.get("summary_line", ""),
    )
    step_series_depth = int(step_series_depth or 0)
    material_depth = int(material_depth or 0)
    material_pass = bool(material_pass)
    status = "PASS" if step_series_depth > 0 and material_pass else "CHECK"
    summary_label = (
        f"NDTHA surface: {status} | step_series_depth={step_series_depth} | "
        f"material_depth={material_depth} | material_pass={material_pass}"
    )
    detail_label = material_summary_line or (
        f"material_depth={material_depth} | material_pass={material_pass}"
    )
    return {
        "step_series_depth": step_series_depth,
        "material_depth": material_depth,
        "material_pass": material_pass,
        "material_summary_line": material_summary_line,
        "summary_label": summary_label,
        "detail_label": detail_label,
        "derived_surface": derived_surface,
    }


def _geometry_crosswalk_detail_label(*surfaces: dict[str, Any]) -> str:
    replacements = (
        ("full_member_crosswalk=", "full member="),
        ("full_section_crosswalk=", "full section="),
        ("full_load_crosswalk=", "full load="),
    )
    labels: list[str] = []
    for surface in surfaces:
        text = str(surface.get("summary_line", "") or "").strip()
        for src, dst in replacements:
            text = text.replace(src, dst)
        if text:
            labels.append(text)
    return " | ".join(labels)


def _panel_zone_external_validation_surface(summary: dict[str, Any]) -> dict[str, Any]:
    coverage = _panel_zone_external_validation_coverage_surface(summary)
    advisory_only = bool(
        summary.get("panel_zone_external_validation_advisory_only", False)
        or (
            bool(summary.get("panel_zone_internal_engine_complete", False))
            and bool(summary.get("panel_zone_external_validation_pending", False))
            and str(summary.get("panel_zone_validation_boundary", "") or "") == "external_validation_only"
        )
    )
    release_blocking = bool(
        summary.get("panel_zone_external_validation_release_blocking", False)
        or (
            bool(summary.get("panel_zone_external_validation_pending", False))
            and not advisory_only
        )
    )
    status_label = normalize_panel_zone_external_validation_status_label(
        {
            **summary,
            "panel_zone_external_validation_source_count": int(coverage["source_count"]),
            "panel_zone_external_validation_validated_source_count": int(
                coverage["validated_source_count"]
            ),
            "panel_zone_external_validation_exact_source_count": int(
                coverage["exact_source_count"]
            ),
            "panel_zone_external_validation_fallback_source_count": int(
                coverage["fallback_source_count"]
            ),
            "panel_zone_external_validation_missing_source_count": int(
                coverage["missing_source_count"]
            ),
            "panel_zone_external_validation_unknown_source_count": int(
                coverage["unknown_source_count"]
            ),
            "panel_zone_external_validation_candidate_member_count": int(
                coverage["candidate_member_count"]
            ),
            "panel_zone_external_validation_validated_member_count": int(
                coverage["validated_member_count"]
            ),
            "panel_zone_external_validation_exact_member_count": int(
                coverage["exact_member_count"]
            ),
            "panel_zone_external_validation_fallback_member_count": int(
                coverage["fallback_member_count"]
            ),
            "panel_zone_external_validation_validated_row_count_total": int(
                coverage["validated_row_count_total"]
            ),
            "panel_zone_external_validation_exact_validated_row_count": int(
                coverage["exact_validated_row_count"]
            ),
            "panel_zone_external_validation_fallback_validated_row_count": int(
                coverage["fallback_validated_row_count"]
            ),
        },
        advisory_only=advisory_only,
        release_blocking=release_blocking,
    )
    return {
        "advisory_only": advisory_only,
        "release_blocking": release_blocking,
        "status_label": status_label,
        **coverage,
    }


def _normalize_foundation_key(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[-\s/]+", "_", text)
    return text


def _foundation_member_count_from_counts(type_counts: dict[str, object]) -> int:
    if not isinstance(type_counts, dict):
        return 0
    total = 0
    for raw_key, raw_value in type_counts.items():
        if _normalize_foundation_key(raw_key) in FOUNDATION_KEYWORDS:
            total += _finite(raw_value, 0.0)
    return int(total)


def _compact_korean_source_ingest_summary_line(line: str) -> str:
    compact = str(line or "").strip()
    if not compact:
        return compact
    replacements = (
        ("Korean source ingest gate:", "KR ingest:"),
        ("Korean source ingest:", "KR ingest:"),
        ("sources=", "src="),
        ("classes=", "cls="),
        ("collected=", "got="),
        ("fingerprinted=", "fp="),
        ("metadata_only=", "meta="),
        ("rejected=", "rej="),
        ("duplicate_sha_groups=", "dup="),
        ("seed_complete=", "seed="),
        ("exact_topology=", "topo="),
        ("native_writeback=", "native="),
        ("p0_focus=", "p0="),
    )
    for old, new in replacements:
        compact = compact.replace(old, new)
    return compact


def _compact_korean_structural_preview_queue_summary_line(line: str) -> str:
    compact = str(line or "").strip()
    if not compact:
        return compact
    replacements = (
        ("Korean structural preview queue:", "KR preview queue:"),
        ("candidates=", "cand="),
        ("pending=", "pend="),
    )
    for old, new in replacements:
        compact = compact.replace(old, new)
    return compact


def _smoke_history_plot_path(out_json: str | Path) -> Path:
    out_json_path = Path(out_json)
    return out_json_path.parent / "release_gap_smoke_history.png"


def _measured_chain_category_plot_path(out_json: str | Path) -> Path:
    out_json_path = Path(out_json)
    return out_json_path.parent / "release_gap_measured_chain_categories.png"


def _write_smoke_history_plot(path: Path, smoke_history_payload: dict) -> None:
    history = smoke_history_payload.get("history") if isinstance(smoke_history_payload.get("history"), list) else []
    summary = smoke_history_payload.get("summary") if isinstance(smoke_history_payload.get("summary"), dict) else {}
    path.parent.mkdir(parents=True, exist_ok=True)

    if not history:
        fig, _ = empty_state_figure(
            title="Nightly Smoke History",
            subtitle="Release-gate comparable samples",
            message="No smoke history samples were available.",
        )
        save_analysis_figure(fig, path, dpi=160, rect=(0.0, 0.0, 1.0, 0.94))
        return

    configure_analysis_chart_defaults()
    x = list(range(1, len(history) + 1))
    baseline_runtime = [float(row.get("baseline_runtime_s", 0.0) or 0.0) for row in history]
    trial_runtime = [float(row.get("trial_runtime_s", 0.0) or 0.0) for row in history]
    baseline_dcr = [float(row.get("baseline_max_dcr", 0.0) or 0.0) for row in history]
    trial_dcr = [float(row.get("trial_max_dcr", 0.0) or 0.0) for row in history]
    contract_pass = [1.0 if bool(row.get("contract_pass", False)) else 0.0 for row in history]
    trial_feasible = [1.0 if bool(row.get("trial_feasible", False)) else 0.0 for row in history]

    fig, axes = plt.subplots(3, 1, figsize=(11.2, 8.6), sharex=True, gridspec_kw={"height_ratios": [1.4, 1.1, 0.75]})
    add_figure_header(
        fig,
        title="Nightly Design-Optimization Smoke Trend",
        subtitle=(
            f"samples={int(summary.get('count', len(history)) or len(history))} | "
            f"pass_rate={float(summary.get('pass_rate', 0.0) or 0.0):.2%} | "
            f"trial_feasible_rate={float(summary.get('trial_feasible_rate', 0.0) or 0.0):.2%}"
        ),
    )

    apply_analysis_axis_style(axes[0], ylabel="Runtime (s)")
    axes[0].plot(x, baseline_runtime, marker="o", color=WARNING, linewidth=1.9, label="baseline runtime")
    axes[0].plot(x, trial_runtime, marker="o", color=SUCCESS, linewidth=1.9, label="trial runtime")
    runtime_gap = np.asarray(baseline_runtime, dtype=np.float64) - np.asarray(trial_runtime, dtype=np.float64)
    axes[0].fill_between(
        x,
        baseline_runtime,
        trial_runtime,
        where=runtime_gap >= 0.0,
        color="#d9ecdf",
        alpha=0.35,
        interpolate=True,
        label="runtime saved",
    )
    add_badge(
        axes[0],
        text=(
            f"latest baseline={baseline_runtime[-1]:.2f}s\n"
            f"latest trial={trial_runtime[-1]:.2f}s"
        ),
        facecolor="#f9f4ea",
    )
    axes[0].legend(loc="upper right")

    apply_analysis_axis_style(axes[1], ylabel="Max DCR")
    axes[1].plot(x, baseline_dcr, marker="o", color=DANGER, linewidth=1.8, label="baseline DCR")
    axes[1].plot(x, trial_dcr, marker="o", color=ACCENT, linewidth=1.8, label="trial DCR")
    axes[1].axhline(1.0, color=MUTED, linestyle="--", linewidth=1.0, label="limit = 1.0")
    dcr_extent = baseline_dcr + trial_dcr + [1.0]
    dcr_min = min(dcr_extent)
    dcr_max = max(dcr_extent)
    dcr_pad = max((dcr_max - dcr_min) * 0.18, 0.04)
    axes[1].set_ylim(max(0.0, dcr_min - dcr_pad), dcr_max + dcr_pad)
    add_badge(
        axes[1],
        text=f"latest trial={trial_dcr[-1]:.3f}\nmargin to limit={1.0 - trial_dcr[-1]:.3f}",
        facecolor="#f5f6fb",
    )
    axes[1].legend(loc="upper right")

    apply_analysis_axis_style(axes[2], xlabel="Nightly smoke sample", ylabel="Gate")
    axes[2].scatter(
        x,
        np.full(len(x), 1.0),
        c=[SUCCESS if bool(v) else DANGER for v in contract_pass],
        s=72,
        marker="o",
        label="contract pass",
        zorder=3,
    )
    axes[2].scatter(
        x,
        np.full(len(x), 0.0),
        c=[ACCENT if bool(v) else WARNING for v in trial_feasible],
        s=72,
        marker="s",
        label="trial feasible",
        zorder=3,
    )
    for sample_x, passed, feasible in zip(x, contract_pass, trial_feasible, strict=False):
        axes[2].plot([sample_x, sample_x], [0.0, 1.0], color=ACCENT_WARM, linewidth=1.0, alpha=0.35, zorder=1)
        if not bool(passed) or not bool(feasible):
            axes[2].axvspan(sample_x - 0.36, sample_x + 0.36, color="#fde8e8", alpha=0.35, zorder=0)
    axes[2].set_ylim(-0.6, 1.6)
    axes[2].set_yticks([1.0, 0.0], labels=["contract", "trial"])
    axes[2].set_xlabel("Nightly smoke sample")
    add_badge(
        axes[2],
        text=(
            f"pass={int(sum(bool(v) for v in contract_pass))}/{len(contract_pass)}\n"
            f"feasible={int(sum(bool(v) for v in trial_feasible))}/{len(trial_feasible)}"
        ),
        facecolor="#eef8f2",
    )
    axes[2].legend(loc="lower right")

    save_analysis_figure(fig, path, dpi=160, rect=(0.0, 0.0, 1.0, 0.94))


def _write_measured_chain_category_plot(path: Path, rolling_rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rolling_rows:
        fig, _ = empty_state_figure(
            title="Measured Chain Category Trend",
            subtitle="Full-chain PASS samples only",
            message="No full-chain rolling samples were available.",
        )
        save_analysis_figure(fig, path, dpi=160, rect=(0.0, 0.0, 1.0, 0.94))
        return

    configure_analysis_chart_defaults()
    category_keys = [
        "parser_screening",
        "analysis_optimization",
        "nonseismic_construction",
        "authority_crosscheck",
        "release_packaging",
    ]
    colors = {
        "parser_screening": "#8b5e3c",
        "analysis_optimization": "#1769aa",
        "nonseismic_construction": "#1f6f50",
        "authority_crosscheck": "#b85c38",
        "release_packaging": "#6c5ce7",
    }
    labels = {
        "parser_screening": "Parser/Screening",
        "analysis_optimization": "Analysis/Optimization",
        "nonseismic_construction": "Nonseismic/Construction",
        "authority_crosscheck": "Authority/Crosscheck",
        "release_packaging": "Release/Packaging",
    }
    x = list(range(1, len(rolling_rows) + 1))
    if len(rolling_rows) == 1:
        fig, ax = plt.subplots(figsize=(10.8, 5.8))
        add_figure_header(
            fig,
            title="Measured Chain Category Breakdown",
            subtitle="Single comparable full-chain PASS sample",
        )
        apply_analysis_axis_style(ax, xlabel="Minutes", ylabel="", y_grid=False, x_grid=True)
        latest = rolling_rows[0]
        items = [
            (labels[key], float((latest.get("measured_chain_category_minutes", {}) or {}).get(key, 0.0) or 0.0), colors[key])
            for key in category_keys
        ]
        items.sort(key=lambda item: item[1], reverse=True)
        y_pos = list(range(len(items)))
        ax.barh(y_pos, [row[1] for row in items], color=[row[2] for row in items], alpha=0.92)
        ax.set_yticks(y_pos, [row[0] for row in items])
        ax.invert_yaxis()
        for idx, (_, value, color) in enumerate(items):
            ax.text(value + max(value * 0.03, 0.03), idx, f"{value:.2f} min", va="center", fontsize=9, color=color)
        add_badge(
            ax,
            text=f"latest total={sum(row[1] for row in items):.2f} min\nsamples=1",
            facecolor="#f7f2e8",
        )
        save_analysis_figure(fig, path, dpi=160, rect=(0.0, 0.0, 1.0, 0.94))
        return

    fig, ax = plt.subplots(figsize=(11, 6.6))
    add_figure_header(
        fig,
        title="Measured Chain Category Trend",
        subtitle="Full-chain PASS samples only",
    )
    apply_analysis_axis_style(ax, xlabel="Rolling nightly sample", ylabel="Minutes", x_grid=False, y_grid=True)
    for key in category_keys:
        y = [
            float((row.get("measured_chain_category_minutes", {}) or {}).get(key, 0.0) or 0.0)
            for row in rolling_rows
        ]
        ax.plot(x, y, marker="o", linewidth=2.1, color=colors[key], label=labels[key])
        if y:
            ax.scatter([x[-1]], [y[-1]], s=46, color=colors[key], zorder=3)
            ax.text(x[-1] + 0.08, y[-1], f"{labels[key]} {y[-1]:.1f}", fontsize=8.2, color=colors[key], va="center")
    total_last = sum(
        float((rolling_rows[-1].get("measured_chain_category_minutes", {}) or {}).get(key, 0.0) or 0.0)
        for key in category_keys
    )
    add_badge(
        ax,
        text=f"latest total={total_last:.2f} min\nsamples={len(rolling_rows)}",
        facecolor="#f7f2e8",
    )
    ax.legend(loc="upper left", ncol=2, frameon=False)
    save_analysis_figure(fig, path, dpi=160, rect=(0.0, 0.0, 1.0, 0.94))


def _smoke_recent_samples(smoke_history_payload: dict, *, limit: int = 5) -> list[dict[str, object]]:
    history = smoke_history_payload.get("history") if isinstance(smoke_history_payload.get("history"), list) else []
    rows: list[dict[str, object]] = []
    for idx, row in enumerate(history[-limit:], start=max(len(history) - limit + 1, 1)):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "sample_index": idx,
                "generated_at": str(row.get("generated_at", "")),
                "reason_code": str(row.get("reason_code", "")),
                "contract_pass": bool(row.get("contract_pass", False)),
                "trial_feasible": bool(row.get("trial_feasible", False)),
                "baseline_runtime_s": float(row.get("baseline_runtime_s", 0.0) or 0.0),
                "trial_runtime_s": float(row.get("trial_runtime_s", 0.0) or 0.0),
                "baseline_max_dcr": float(row.get("baseline_max_dcr", 0.0) or 0.0),
                "trial_max_dcr": float(row.get("trial_max_dcr", 0.0) or 0.0),
                "trial_action_name": str(row.get("trial_action_name", "")),
            }
        )
    return rows


def _smoke_trend_summary(smoke_history_payload: dict) -> dict[str, object]:
    history = smoke_history_payload.get("history") if isinstance(smoke_history_payload.get("history"), list) else []
    if not history or not isinstance(history[0], dict) or not isinstance(history[-1], dict):
        return {
            "sample_count": 0,
            "baseline_runtime_drift_s": 0.0,
            "trial_runtime_drift_s": 0.0,
            "baseline_max_dcr_drift": 0.0,
            "trial_max_dcr_drift": 0.0,
        }
    first = history[0]
    last = history[-1]
    return {
        "sample_count": len(history),
        "baseline_runtime_first_s": float(first.get("baseline_runtime_s", 0.0) or 0.0),
        "baseline_runtime_last_s": float(last.get("baseline_runtime_s", 0.0) or 0.0),
        "baseline_runtime_drift_s": float(last.get("baseline_runtime_s", 0.0) or 0.0) - float(first.get("baseline_runtime_s", 0.0) or 0.0),
        "trial_runtime_first_s": float(first.get("trial_runtime_s", 0.0) or 0.0),
        "trial_runtime_last_s": float(last.get("trial_runtime_s", 0.0) or 0.0),
        "trial_runtime_drift_s": float(last.get("trial_runtime_s", 0.0) or 0.0) - float(first.get("trial_runtime_s", 0.0) or 0.0),
        "baseline_max_dcr_first": float(first.get("baseline_max_dcr", 0.0) or 0.0),
        "baseline_max_dcr_last": float(last.get("baseline_max_dcr", 0.0) or 0.0),
        "baseline_max_dcr_drift": float(last.get("baseline_max_dcr", 0.0) or 0.0) - float(first.get("baseline_max_dcr", 0.0) or 0.0),
        "trial_max_dcr_first": float(first.get("trial_max_dcr", 0.0) or 0.0),
        "trial_max_dcr_last": float(last.get("trial_max_dcr", 0.0) or 0.0),
        "trial_max_dcr_drift": float(last.get("trial_max_dcr", 0.0) or 0.0) - float(first.get("trial_max_dcr", 0.0) or 0.0),
    }


def _measured_chain_timing_summary(nightly_report: dict) -> dict[str, object]:
    steps = nightly_report.get("steps") if isinstance(nightly_report.get("steps"), list) else []
    category_map = {
        "parser_screening": {
            "commercial_csv_gate",
            "midas_mgt_conversion_gate",
            "real_source_multi_gate",
        },
        "analysis_optimization": {
            "nonlinear_engine_gate",
            "pushover_stress_gate",
            "ndtha_stress_gate",
            "ndtha_residual_gate",
            "design_optimization_cost_reduction_smoke",
        },
        "nonseismic_construction": {
            "wind_benchmark_gate",
            "ssi_boundary_gate",
            "damper_validation_gate",
            "construction_sequence_gate",
            "flexible_diaphragm_gate",
        },
        "authority_crosscheck": {
            "global_authority_gate",
            "rc_benchmark_lock_gate",
            "commercial_readiness_gate",
        },
        "release_packaging": {
            "kds_compliance_gate",
            "reproducibility_version_lock_gate",
            "release_registry_gate",
        },
    }
    category_seconds = {key: 0.0 for key in category_map}
    selected_steps: list[dict[str, object]] = []
    for row in steps:
        if not isinstance(row, dict):
            continue
        step_name = str(row.get("step", ""))
        step_seconds = float(row.get("seconds", 0.0) or 0.0)
        matched = False
        for category, step_names in category_map.items():
            if step_name in step_names:
                category_seconds[category] += step_seconds
                matched = True
        if matched:
            selected_steps.append({"step": step_name, "seconds": step_seconds})
    total_seconds = sum(category_seconds.values())
    return {
        "measured_chain_selected_step_count": len(selected_steps),
        "measured_chain_total_seconds": round(total_seconds, 3),
        "measured_chain_total_minutes": round(total_seconds / 60.0, 3),
        "measured_chain_category_seconds": {k: round(v, 3) for k, v in category_seconds.items()},
        "measured_chain_category_minutes": {k: round(v / 60.0, 3) for k, v in category_seconds.items()},
        "measured_chain_step_rows": selected_steps,
    }


def _nightly_deployment_mode(
    report_path: Path,
    report: dict,
    *,
    fallback_commercial_readiness_path: Path | None = None,
) -> str:
    candidate_paths: list[Path] = []
    sibling = report_path.parent / "commercial_readiness_report.json"
    if sibling.exists():
        candidate_paths.append(sibling)
    reports = report.get("reports") if isinstance(report.get("reports"), dict) else {}
    commercial_path = reports.get("commercial_readiness")
    if commercial_path:
        candidate_paths.append(Path(str(commercial_path)))
    if fallback_commercial_readiness_path is not None:
        candidate_paths.append(fallback_commercial_readiness_path)
    seen: set[str] = set()
    for path in candidate_paths:
        key = str(path)
        if not key or key in seen or not path.exists():
            continue
        seen.add(key)
        try:
            payload = _load_json(path)
        except Exception:
            continue
        deployment_model = payload.get("deployment_model") if isinstance(payload.get("deployment_model"), dict) else {}
        mode = str(deployment_model.get("mode", "")).strip()
        if mode:
            return mode
    return ""


def _nightly_strict_design_opt_cost_smoke(report: dict) -> bool:
    inputs = report.get("inputs") if isinstance(report.get("inputs"), dict) else {}
    return bool(inputs.get("strict_design_opt_cost_smoke", False))


def _rolling_measured_chain_summary(
    current_nightly_path: Path,
    current_nightly_report: dict,
    *,
    history_root: Path,
    limit: int,
    current_deployment_model: str = "",
    current_strict_design_opt_cost_smoke: bool = False,
    fallback_commercial_readiness_path: Path | None = None,
) -> dict[str, object]:
    current_timing = _measured_chain_timing_summary(current_nightly_report)
    current_step_names = {
        str(row.get("step", ""))
        for row in (current_timing.get("measured_chain_step_rows") or [])
        if isinstance(row, dict) and str(row.get("step", ""))
    }
    current_step_count = len(current_step_names)
    comparable_overlap_threshold = 0.90
    candidate_paths: list[Path] = []
    if current_nightly_path.exists():
        candidate_paths.append(current_nightly_path)
    if history_root.exists():
        candidate_paths.extend(sorted(history_root.glob("*/artifacts/nightly_release_gate_report.json")))

    deduped: dict[str, Path] = {}
    for path in candidate_paths:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        deduped[key] = path
    report_paths = sorted(deduped.values(), key=lambda item: str(item))
    rows: list[dict[str, object]] = []
    for path in report_paths:
        try:
            report = current_nightly_report if path == current_nightly_path else _load_json(path)
        except Exception:
            continue
        timing = _measured_chain_timing_summary(report)
        row = (
            {
                "path": str(path),
                "generated_at": str(report.get("generated_at", "")),
                "contract_pass": bool(report.get("contract_pass", False)),
                "reason_code": str(report.get("reason_code", "")),
                "step_count": int(len(report.get("steps", [])) if isinstance(report.get("steps"), list) else 0),
                "measured_chain_total_minutes": float(timing.get("measured_chain_total_minutes", 0.0) or 0.0),
                "measured_chain_category_minutes": timing.get("measured_chain_category_minutes", {}),
                "measured_chain_selected_step_count": int(timing.get("measured_chain_selected_step_count", 0) or 0),
                "measured_chain_step_names": [
                    str(step_row.get("step", ""))
                    for step_row in (timing.get("measured_chain_step_rows") or [])
                    if isinstance(step_row, dict) and str(step_row.get("step", ""))
                ],
                "deployment_model": _nightly_deployment_mode(
                    path,
                    report,
                    fallback_commercial_readiness_path=fallback_commercial_readiness_path,
                ),
                "strict_design_opt_cost_smoke": _nightly_strict_design_opt_cost_smoke(report),
            }
        )
        rows.append(row)

    full_chain_rows = [
        row
        for row in rows
        if bool(row.get("contract_pass", False))
        and int(row.get("step_count", 0)) >= 20
        and int(row.get("measured_chain_selected_step_count", 0)) >= 10
        and float(row.get("measured_chain_total_minutes", 0.0) or 0.0) > 0.0
    ]
    comparable_rows = []
    for row in full_chain_rows:
        row_step_names = {
            str(step_name)
            for step_name in (row.get("measured_chain_step_names") or [])
            if str(step_name)
        }
        overlap_ratio = (
            len(row_step_names & current_step_names) / max(current_step_count, 1)
            if current_step_count > 0
            else 0.0
        )
        step_count_delta = abs(len(row_step_names) - current_step_count)
        same_deployment_model = str(row.get("deployment_model", "")) == str(current_deployment_model)
        same_strict_smoke = bool(row.get("strict_design_opt_cost_smoke", False)) == bool(current_strict_design_opt_cost_smoke)
        if overlap_ratio >= comparable_overlap_threshold and step_count_delta <= 1 and same_deployment_model and same_strict_smoke:
            comparable_rows.append(
                {
                    **row,
                    "comparable_overlap_ratio": round(overlap_ratio, 3),
                    "comparable_step_count_delta": int(step_count_delta),
                    "same_deployment_model": bool(same_deployment_model),
                    "same_strict_design_opt_cost_smoke": bool(same_strict_smoke),
                }
            )

    selection_mode = "full_chain_pass"
    if comparable_rows:
        rows = comparable_rows[-max(int(limit), 1) :]
        selection_mode = "current_pipeline_comparable_full_chain_pass"
    elif full_chain_rows:
        rows = full_chain_rows[-max(int(limit), 1) :]

    if not rows:
        return {
            "measured_chain_rolling_sample_count": 0,
            "measured_chain_rolling_total_minutes_range": [],
            "measured_chain_rolling_total_minutes_mean": 0.0,
            "measured_chain_rolling_total_minutes_first": 0.0,
            "measured_chain_rolling_total_minutes_last": 0.0,
            "measured_chain_rolling_total_minutes_drift": 0.0,
            "measured_chain_rolling_category_minutes_mean": {},
            "measured_chain_rolling_rows": [],
            "measured_chain_full_chain_sample_count": len(full_chain_rows),
            "measured_chain_comparable_sample_count": len(comparable_rows),
            "measured_chain_comparable_reference_step_count": current_step_count,
            "measured_chain_comparable_overlap_threshold": comparable_overlap_threshold,
            "measured_chain_comparable_reference_deployment_model": str(current_deployment_model),
            "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(current_strict_design_opt_cost_smoke),
            "measured_chain_rolling_selection_mode": selection_mode,
        }

    totals = [float(row["measured_chain_total_minutes"]) for row in rows]
    category_keys = sorted(
        {
            str(category)
            for row in rows
            for category in (
                row.get("measured_chain_category_minutes", {}).keys()
                if isinstance(row.get("measured_chain_category_minutes"), dict)
                else []
            )
        }
    )
    category_means = {
        key: round(
            sum(
                float((row.get("measured_chain_category_minutes", {}) or {}).get(key, 0.0) or 0.0)
                for row in rows
            )
            / len(rows),
            3,
        )
        for key in category_keys
    }
    return {
        "measured_chain_rolling_sample_count": len(rows),
        "measured_chain_rolling_total_minutes_range": [round(min(totals), 3), round(max(totals), 3)],
        "measured_chain_rolling_total_minutes_mean": round(sum(totals) / len(totals), 3),
        "measured_chain_rolling_total_minutes_first": round(totals[0], 3),
        "measured_chain_rolling_total_minutes_last": round(totals[-1], 3),
        "measured_chain_rolling_total_minutes_drift": round(totals[-1] - totals[0], 3),
        "measured_chain_rolling_category_minutes_mean": category_means,
        "measured_chain_rolling_rows": rows,
        "measured_chain_full_chain_sample_count": len(full_chain_rows),
        "measured_chain_comparable_sample_count": len(comparable_rows),
        "measured_chain_comparable_reference_step_count": current_step_count,
        "measured_chain_comparable_overlap_threshold": comparable_overlap_threshold,
        "measured_chain_comparable_reference_deployment_model": str(current_deployment_model),
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(current_strict_design_opt_cost_smoke),
        "measured_chain_rolling_selection_mode": selection_mode,
    }


def _format_minute_range(values: object) -> str:
    if isinstance(values, list) and len(values) == 2:
        try:
            return f"{float(values[0]):.2f}-{float(values[1]):.2f} min"
        except Exception:
            return "n/a"
    return "n/a"


def _coverage_range_label(values: object) -> str:
    if isinstance(values, list) and len(values) == 2:
        return f"{values[0]}-{values[1]}%"
    return "n/a"


def _estimated_time_saved_pct_range(coverage_range: object) -> list[int]:
    if not (isinstance(coverage_range, list) and len(coverage_range) == 2):
        return [70, 90]
    try:
        low = float(coverage_range[0])
        high = float(coverage_range[1])
    except Exception:
        return [70, 90]
    low_saved = int(max(0, min(100, 5 * math.floor((low * 0.75) / 5.0))))
    high_saved = int(max(low_saved, min(100, 5 * math.ceil((high * 0.90) / 5.0))))
    return [low_saved, high_saved]


def _empirical_time_saved_summary(
    smoke_history_payload: dict,
    coverage_range: object,
) -> dict[str, object]:
    history = smoke_history_payload.get("history") if isinstance(smoke_history_payload.get("history"), list) else []
    reductions: list[float] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        baseline = float(row.get("baseline_runtime_s", 0.0) or 0.0)
        trial = float(row.get("trial_runtime_s", 0.0) or 0.0)
        if baseline <= 0.0 or trial < 0.0 or trial > baseline:
            continue
        reductions.append((baseline - trial) / baseline * 100.0)
    if not reductions:
        return {
            "estimated_time_saved_pct_range": _estimated_time_saved_pct_range(coverage_range),
            "estimated_time_saved_basis": (
                "Heuristic estimate for repeated analysis, screening, packaging, and optimization work inside the accelerated envelope. "
                "It excludes the residual engineer-review, legacy-tool cross-validation, and formal sign-off workflow."
            ),
            "empirical_smoke_runtime_saved_pct_range": [],
            "empirical_smoke_runtime_saved_pct_mean": 0.0,
        }

    try:
        coverage_low = float(coverage_range[0]) / 100.0 if isinstance(coverage_range, list) and len(coverage_range) == 2 else 0.95
        coverage_high = float(coverage_range[1]) / 100.0 if isinstance(coverage_range, list) and len(coverage_range) == 2 else 0.99
    except Exception:
        coverage_low, coverage_high = 0.95, 0.99
    min_reduction = min(reductions)
    max_reduction = max(reductions)
    mean_reduction = sum(reductions) / len(reductions)
    estimated_range = [
        max(0, min(100, int(math.floor(coverage_low * min_reduction)))),
        max(0, min(100, int(math.ceil(coverage_high * max_reduction)))),
    ]
    estimated_range[1] = max(estimated_range[0], estimated_range[1])
    return {
        "estimated_time_saved_pct_range": estimated_range,
        "estimated_time_saved_basis": (
            "Empirical estimate derived from nightly design-optimization smoke runtime reduction, "
            "scaled by the accelerated-coverage target. "
            f"smoke_mean_runtime_saved={mean_reduction:.2f}%, sample_count={len(reductions)}."
        ),
        "empirical_smoke_runtime_saved_pct_range": [round(min_reduction, 2), round(max_reduction, 2)],
        "empirical_smoke_runtime_saved_pct_mean": round(mean_reduction, 2),
    }


def _build_holdout_breakdown(
    holdout_range: object,
    categories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(holdout_range, list) and len(holdout_range) == 2:
        try:
            holdout_low = float(holdout_range[0])
            holdout_high = float(holdout_range[1])
        except Exception:
            holdout_low, holdout_high = 1.0, 5.0
    else:
        holdout_low, holdout_high = 1.0, 5.0
    default_share_by_id = {
        "licensed_engineer_review_required": 50,
        "legacy_tool_cross_validation_required": 30,
        "legal_authority_signoff_required": 20,
    }
    default_queue_by_id = {
        "licensed_engineer_review_required": (
            "RH-001",
            "licensed_engineer_review_queue",
            "pending_review",
            "Assign the highest-touch irregular/member-edge cases to licensed engineer review before full-replacement claims.",
            72,
            "assignment_plus_3_business_days",
            "signed_engineer_review_packet",
        ),
        "legacy_tool_cross_validation_required": (
            "RH-002",
            "legacy_tool_cross_validation_queue",
            "pending_cross_validation",
            "Queue novel load-path and authority-critical submodels for legacy-tool cross-validation.",
            120,
            "assignment_plus_5_business_days",
            "legacy_tool_cross_validation_report",
        ),
        "legal_authority_signoff_required": (
            "RH-003",
            "legal_authority_signoff_queue",
            "pending_signoff",
            "Route formal seal, legal submission, and authority-facing responsibility to sign-off workflow.",
            168,
            "authority_submission_window",
            "authority_signoff_receipt_or_formal_hold",
        ),
    }
    breakdown: list[dict[str, Any]] = []
    for row in categories:
        if not isinstance(row, dict):
            continue
        category_id = str(row.get("id", "") or "")
        relative_share_pct = int(default_share_by_id.get(category_id, 0))
        absolute_project_pct_range = [
            round(holdout_low * relative_share_pct / 100.0, 2),
            round(holdout_high * relative_share_pct / 100.0, 2),
        ]
        (
            default_work_item_id,
            default_queue_name,
            default_queue_status,
            default_next_action,
            default_sla_hours,
            default_due_date,
            default_closure_evidence_required,
        ) = default_queue_by_id.get(
            category_id,
            (
                f"RH-{len(breakdown) + 1:03d}",
                f"{category_id}_queue" if category_id else "residual_holdout_queue",
                "pending_review",
                "Assign residual holdout case to the matching review owner.",
                120,
                "assignment_plus_5_business_days",
                "owner_approved_closure_evidence",
            ),
        )
        closure_evidence_path = str(row.get("closure_evidence_path", "") or "")
        sla_hours = int(row.get("sla_hours", default_sla_hours) or default_sla_hours)
        breakdown.append(
            {
                **row,
                "work_item_id": str(row.get("work_item_id", "") or default_work_item_id),
                "relative_share_pct": relative_share_pct,
                "absolute_project_pct_range": absolute_project_pct_range,
                "queue_name": str(row.get("queue_name", "") or default_queue_name),
                "queue_status": str(row.get("queue_status", "") or default_queue_status),
                "status": str(row.get("status", "") or "open"),
                "sla_hours": sla_hours,
                "sla_label": str(row.get("sla_label", "") or f"{sla_hours}h"),
                "due_date": str(row.get("due_date", "") or default_due_date),
                "closure_evidence_required": str(
                    row.get("closure_evidence_required", "") or default_closure_evidence_required
                ),
                "closure_evidence_path": closure_evidence_path,
                "closure_evidence_status": str(
                    row.get("closure_evidence_status", "") or ("attached" if closure_evidence_path else "pending")
                ),
                "next_action": str(row.get("next_action", "") or default_next_action),
                "full_commercial_replacement_blocker": True,
            }
        )
    return breakdown


def _build_holdout_work_items(buckets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    work_items: list[dict[str, Any]] = []
    for row in buckets:
        if not isinstance(row, dict):
            continue
        work_items.append(
            {
                "work_item_id": str(row.get("work_item_id", "") or f"RH-{len(work_items) + 1:03d}"),
                "category_id": str(row.get("id", "") or ""),
                "title": str(row.get("label", row.get("id", "")) or ""),
                "owner": str(row.get("owner", "") or ""),
                "queue_name": str(row.get("queue_name", "") or ""),
                "queue_status": str(row.get("queue_status", "") or ""),
                "status": str(row.get("status", "") or ""),
                "sla_hours": int(row.get("sla_hours", 0) or 0),
                "sla_label": str(row.get("sla_label", "") or ""),
                "due_date": str(row.get("due_date", "") or ""),
                "closure_evidence_required": str(row.get("closure_evidence_required", "") or ""),
                "closure_evidence_path": str(row.get("closure_evidence_path", "") or ""),
                "closure_evidence_status": str(row.get("closure_evidence_status", "") or ""),
                "absolute_project_pct_range": row.get("absolute_project_pct_range", []),
                "relative_share_pct": int(row.get("relative_share_pct", 0) or 0),
                "next_action": str(row.get("next_action", "") or ""),
                "full_commercial_replacement_blocker": bool(
                    row.get("full_commercial_replacement_blocker", True)
                ),
            }
        )
    return work_items


def _commercial_grade_label(value: object) -> str:
    label = str(value or "unknown").strip()
    if not label:
        return "unknown"
    if label.islower():
        return label.capitalize()
    return label


def _commercial_scope_summary_line(
    *,
    grade_label: str,
    deployment_model: dict[str, Any],
    accelerated_coverage_target_pct_range: object,
    residual_holdout_target_pct_range: object,
) -> str:
    return (
        "Commercial scope: "
        f"grade={grade_label} | "
        "engineer_in_loop_accelerated_coverage_ready="
        f"{bool(deployment_model.get('engineer_in_loop_accelerated_coverage_ready', False))} | "
        "full_commercial_replacement_ready="
        f"{bool(deployment_model.get('full_commercial_replacement_ready', False))} | "
        f"accelerated_coverage={_coverage_range_label(accelerated_coverage_target_pct_range)} | "
        f"residual_holdout={_coverage_range_label(residual_holdout_target_pct_range)}"
    )


def _commercial_reliability_breadth_summary_line(
    *,
    grade_label: str,
    exact_row_count: int,
    total_row_count: int,
    evidence_row_count: int,
) -> str:
    return (
        "Commercial reliability breadth: "
        "PASS | "
        f"grade={grade_label} | "
        f"exact_row_coverage={exact_row_count}/{total_row_count} | "
        f"evidence_rows={evidence_row_count} | "
        f"evidence_present={evidence_row_count > 0}"
    )


def _write_markdown(path: Path, payload: dict) -> None:
    summary = payload["summary"]
    release = payload["release_status"]
    strengths = payload["observed_strengths"]
    gaps = payload["remaining_gaps"]
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    holdout_buckets = payload.get("residual_holdout_buckets") if isinstance(payload.get("residual_holdout_buckets"), list) else []
    advanced_holdouts = payload.get("advanced_holdouts") if isinstance(payload.get("advanced_holdouts"), list) else []
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    smoke_png = Path(str(artifacts.get("smoke_history_png", "") or ""))
    measured_chain_png = Path(str(artifacts.get("measured_chain_category_png", "") or ""))
    smoke_trend = payload.get("nightly_smoke_trend") if isinstance(payload.get("nightly_smoke_trend"), dict) else {}
    midas_native_roundtrip_taxonomy_case_counts = (
        summary.get("midas_native_roundtrip_taxonomy_case_counts")
        if isinstance(summary.get("midas_native_roundtrip_taxonomy_case_counts"), dict)
        else {}
    )
    midas_native_roundtrip_taxonomy_card_family_histogram = (
        summary.get("midas_native_roundtrip_taxonomy_card_family_histogram")
        if isinstance(summary.get("midas_native_roundtrip_taxonomy_card_family_histogram"), dict)
        else {}
    )
    midas_native_roundtrip_structure_type_batch_markdowns = [
        str(row)
        for row in (summary.get("midas_native_roundtrip_structure_type_batch_markdowns") or [])
        if str(row or "").strip()
    ]
    commercial_workflow_breadth_summary = (
        summary.get("commercial_workflow_breadth_summary")
        if isinstance(summary.get("commercial_workflow_breadth_summary"), dict)
        else {}
    )
    commercial_workflow_breadth_artifact_links = (
        summary.get("commercial_workflow_breadth_artifact_links")
        if isinstance(summary.get("commercial_workflow_breadth_artifact_links"), dict)
        else {}
    )
    commercial_workflow_breadth_rows = [
        row
        for row in (summary.get("commercial_workflow_breadth_rows") or [])
        if isinstance(row, dict)
    ]
    external_benchmark_submission_queue_rows = [
        row
        for row in (summary.get("external_benchmark_submission_queue_rows") or [])
        if isinstance(row, dict)
    ]

    lines: list[str] = []
    lines.append("# Release Gap Report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Release-candidate gates: `{summary['release_candidate_pass']}`")
    lines.append(f"- Commercial readiness grade: `{summary['commercial_grade']}`")
    if str(summary.get("commercial_scope_summary_line", "")).strip():
        lines.append(f"- Commercial scope: `{str(summary.get('commercial_scope_summary_line', '')).strip()}`")
    if str(summary.get("commercial_reliability_breadth_summary_line", "")).strip():
        lines.append(
            f"- Commercial reliability breadth: "
            f"`{str(summary.get('commercial_reliability_breadth_summary_line', '')).strip()}`"
        )
    lines.append(f"- Deployment model: `{summary['deployment_model']}`")
    if str(summary.get("native_authoring_commercialization_summary_line", "")).strip():
        lines.append(
            f"- Native authoring commercialization lane: "
            f"`{str(summary.get('native_authoring_commercialization_summary_line', '')).strip()}`"
        )
    lines.append(f"- Accelerated coverage target: `{_coverage_range_label(summary.get('accelerated_coverage_target_pct_range'))}`")
    lines.append(f"- Residual holdout target: `{_coverage_range_label(summary.get('residual_holdout_target_pct_range'))}`")
    lines.append(f"- Estimated time saved: `{_coverage_range_label(summary.get('estimated_time_saved_pct_range'))}`")
    lines.append(
        f"- Measured accelerated chain wall-clock (comparable rolling N={int(summary.get('measured_chain_rolling_sample_count', 0) or 0)}): "
        f"`{float(summary.get('measured_chain_rolling_total_minutes_mean', 0.0)):.2f} min` "
        f"(range `{_format_minute_range(summary.get('measured_chain_rolling_total_minutes_range'))}`)"
    )
    lines.append(f"- Current measured chain wall-clock: `{float(summary.get('measured_chain_total_minutes', 0.0)):.2f} min`")
    lines.append(f"- Engineer-in-loop accelerated coverage ready: `{summary['engineer_in_loop_accelerated_coverage_ready']}`")
    lines.append(f"- Time-saving focus: `{summary.get('time_saving_focus', '')}`")
    lines.append(f"- Full commercial replacement ready: `{summary['full_commercial_replacement_ready']}`")
    if str(summary.get("external_benchmark_submission_summary_line", "")).strip():
        lines.append(
            f"- External benchmark submission queue: "
            f"`{str(summary.get('external_benchmark_submission_summary_line', '')).strip()}`"
        )
    if str(summary.get("external_benchmark_submission_recommended_start_mode", "")).strip() or str(
        summary.get("external_benchmark_submission_recommended_submission_scope", "")
    ).strip():
        lines.append(
            f"- External benchmark submission lane: "
            f"`start_mode={str(summary.get('external_benchmark_submission_recommended_start_mode', '') or 'n/a')}` | "
            f"`submission_scope={str(summary.get('external_benchmark_submission_recommended_submission_scope', '') or 'n/a')}` | "
            f"`blocker={str(summary.get('external_benchmark_submission_blocker_label', '') or 'none')}` | "
            f"`caution={str(summary.get('external_benchmark_submission_caution_label', '') or 'none')}` | "
            f"`onepage_attestation_status={str(summary.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown')}`"
        )
    lines.append(
        f"- MIDAS semantic load binding: `{bool(summary.get('midas_semantic_load_binding_pass', False))}` "
        f"(use_stld={int(summary.get('midas_use_stld_block_count', 0))}, "
        f"semantic_cases={int(summary.get('midas_semantic_load_case_count', 0))}, "
        f"semantic_combinations={int(summary.get('midas_semantic_load_combination_count', 0))})"
    )
    lines.append(
        f"- MIDAS bound/unbound load rows: "
        f"`nodal={int(summary.get('midas_bound_nodal_load_row_count', 0))}/{int(summary.get('midas_unbound_nodal_load_row_count', 0))}`, "
        f"`selfweight={int(summary.get('midas_bound_selfweight_row_count', 0))}/{int(summary.get('midas_unbound_selfweight_row_count', 0))}`, "
        f"`pressure={int(summary.get('midas_bound_pressure_row_count', 0))}/{int(summary.get('midas_unbound_pressure_row_count', 0))}`"
    )
    if str(summary.get("midas_section_library_summary_line", "")).strip():
        lines.append(
            f"- MIDAS section-library validator: "
            f"`{str(summary.get('midas_section_library_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_kds_geometry_bridge_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS geometry-bridge validator: "
            f"`{str(summary.get('midas_kds_geometry_bridge_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_kds_geometry_bridge_load_crosswalk_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS geometry-bridge load crosswalk: "
            f"`{str(summary.get('midas_kds_geometry_bridge_load_crosswalk_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_kds_geometry_bridge_semantic_crosswalk_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS geometry-bridge semantic crosswalk: "
            f"`{str(summary.get('midas_kds_geometry_bridge_semantic_crosswalk_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_kds_geometry_bridge_full_member_crosswalk_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS geometry-bridge full member crosswalk: "
            f"`{str(summary.get('midas_kds_geometry_bridge_full_member_crosswalk_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_kds_geometry_bridge_full_section_crosswalk_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS geometry-bridge full section crosswalk: "
            f"`{str(summary.get('midas_kds_geometry_bridge_full_section_crosswalk_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_kds_geometry_bridge_full_load_crosswalk_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS geometry-bridge full load crosswalk: "
            f"`{str(summary.get('midas_kds_geometry_bridge_full_load_crosswalk_summary_line', '')).strip()}`"
        )
    if int(summary.get("midas_kds_geometry_bridge_full_crosswalk_depth", 0) or 0):
        lines.append(
            f"- MIDAS KDS geometry full-crosswalk depth: "
            f"`{int(summary.get('midas_kds_geometry_bridge_full_crosswalk_depth', 0))}` "
            f"(min(load/semantic crosswalk))"
        )
    if str(summary.get("midas_loadcomb_roundtrip_summary_line", "")).strip():
        lines.append(
            f"- MIDAS LOADCOMB round-trip validator: "
            f"`{str(summary.get('midas_loadcomb_roundtrip_summary_line', '')).strip()}`"
        )
    if str(summary.get("commercial_benchmark_breadth_summary_line", "")).strip():
        lines.append(
            f"- Commercial benchmark breadth: "
            f"`{str(summary.get('commercial_benchmark_breadth_summary_line', '')).strip()}`"
        )
    if str(summary.get("measured_benchmark_breadth_summary_line", "")).strip():
        lines.append(
            f"- Measured benchmark breadth: "
            f"`{str(summary.get('measured_benchmark_breadth_summary_line', '')).strip()}`"
        )
    if str(summary.get("peer_blind_prediction_compare_summary_line", "")).strip():
        lines.append(
            f"- PEER blind-prediction real compare lane: "
            f"`{str(summary.get('peer_blind_prediction_compare_summary_line', '')).strip()}`"
        )
    if str(summary.get("peer_blind_prediction_measured_response_landing_summary_line", "")).strip():
        lines.append(
            f"- PEER blind-prediction measured-response landing: "
            f"`{str(summary.get('peer_blind_prediction_measured_response_landing_summary_line', '')).strip()}`"
        )
    if str(summary.get("solver_breadth_summary_line", "")).strip():
        lines.append(
            f"- Solver breadth: "
            f"`{str(summary.get('solver_breadth_summary_line', '')).strip()}`"
        )
    if str(summary.get("element_material_breadth_summary_line", "")).strip():
        lines.append(
            f"- Element/material breadth: "
            f"`{str(summary.get('element_material_breadth_summary_line', '')).strip()}`"
        )
    lines.append(f"- Constitutive/interaction families: `{CONSTITUTIVE_INTERACTION_NOTE}`")
    material_constitutive_surface = _format_optional_gate_surface(
        str(summary.get("material_constitutive_summary_line", "") or "").strip(),
        summary.get("material_constitutive_pass")
        if isinstance(summary.get("material_constitutive_pass"), bool) or summary.get("material_constitutive_pass") is None
        else bool(summary.get("material_constitutive_pass")),
    )
    if material_constitutive_surface:
        lines.append(f"- Material constitutive gate: `{material_constitutive_surface}`")
    if int(summary.get("material_constitutive_calibration_matrix_pass_row_count", 0) or 0):
        lines.append(
            f"- Material constitutive depth: "
            f"`matrix_rows={int(summary.get('material_constitutive_calibration_matrix_pass_row_count', 0) or 0)}` | "
            f"`cyclic_reversals={int(summary.get('material_constitutive_cyclic_library_reversal_count', 0) or 0)}` | "
            f"`bond_cyclic_reversals={int(summary.get('material_constitutive_bond_interface_cyclic_reversal_count', 0) or 0)}`"
        )
    steel_composite_constitutive_gate_surface = _format_optional_gate_surface(
        str(summary.get("steel_composite_constitutive_gate_summary_line", "") or "").strip(),
        summary.get("steel_composite_constitutive_gate_pass")
        if isinstance(summary.get("steel_composite_constitutive_gate_pass"), bool)
        or summary.get("steel_composite_constitutive_gate_pass") is None
        else bool(summary.get("steel_composite_constitutive_gate_pass")),
    )
    if steel_composite_constitutive_gate_surface:
        lines.append(f"- Steel/composite constitutive gate: `{steel_composite_constitutive_gate_surface}`")
    if str(summary.get("midas_kds_row_provenance_export_summary_line", "")).strip():
        lines.append(
            f"- MIDAS KDS row provenance export: "
            f"`{str(summary.get('midas_kds_row_provenance_export_summary_line', '')).strip()}`"
        )
    if str(summary.get("contact_readiness_summary_line", "")).strip():
        lines.append(
            f"- Contact readiness: "
            f"`{str(summary.get('contact_readiness_summary_line', '')).strip()}`"
        )
    if str(summary.get("foundation_soil_link_summary_line", "")).strip():
        lines.append(
            f"- Foundation/soil link: "
            f"`{str(summary.get('foundation_soil_link_summary_line', '')).strip()}`"
        )
    if str(summary.get("support_search_summary_line", "")).strip():
        lines.append(
            f"- Support search: "
            f"`{str(summary.get('support_search_summary_line', '')).strip()}`"
        )
    if str(summary.get("structural_contact_summary_line", "")).strip():
        lines.append(
            f"- Structural contact readiness: "
            f"`{str(summary.get('structural_contact_summary_line', '')).strip()}`"
        )
    if str(summary.get("general_fe_contact_matrix_summary_line", "")).strip():
        lines.append(
            f"- General FE contact matrix: "
            f"`{str(summary.get('general_fe_contact_matrix_summary_line', '')).strip()}`"
        )
    if str(summary.get("surface_interaction_benchmark_summary_line", "")).strip():
        lines.append(
            f"- Surface interaction benchmark: "
            f"`{str(summary.get('surface_interaction_benchmark_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_interoperability_summary_line", "")).strip():
        lines.append(
            f"- MIDAS interoperability/export readiness: "
            f"`{str(summary.get('midas_interoperability_summary_line', '')).strip()}`"
        )
    if str(summary.get("midas_native_roundtrip_summary_line", "")).strip():
        lines.append(
            f"- MIDAS native roundtrip/write-back: "
            f"`{str(summary.get('midas_native_roundtrip_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_solver_session_summary_line", "")).strip():
        lines.append(
            f"- Native authoring solver session: "
            f"`{str(summary.get('native_authoring_solver_session_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_ops_bundle_summary_line", "")).strip():
        lines.append(
            f"- Native authoring ops bundle: "
            f"`{str(summary.get('native_authoring_ops_bundle_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_runtime_submission_summary_line", "")).strip():
        lines.append(
            f"- Native authoring runtime submission lane: "
            f"`{str(summary.get('native_authoring_runtime_submission_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_runtime_writeback_depth_summary_line", "")).strip():
        lines.append(
            f"- Native authoring runtime writeback depth: "
            f"`{str(summary.get('native_authoring_runtime_writeback_depth_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_local_runtime_scenario_depth_summary_line", "")).strip():
        lines.append(
            f"- Native authoring local runtime scenario depth: "
            f"`{str(summary.get('native_authoring_local_runtime_scenario_depth_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_local_variant_writeback_trace_summary_line", "")).strip():
        lines.append(
            f"- Native authoring local variant/writeback trace: "
            f"`{str(summary.get('native_authoring_local_variant_writeback_trace_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_multi_project_runtime_writeback_summary_line", "")).strip():
        lines.append(
            f"- Native authoring multi-project runtime/writeback: "
            f"`{str(summary.get('native_authoring_multi_project_runtime_writeback_summary_line', '')).strip()}`"
        )
    if str(summary.get("native_authoring_solver_family_breadth_summary_line", "")).strip():
        lines.append(
            f"- Native authoring solver family breadth: "
            f"`{str(summary.get('native_authoring_solver_family_breadth_summary_line', '')).strip()}`"
        )
    if int(summary.get("native_authoring_palette_family_count", 0) or 0) > 0:
        lines.append(
            f"- Native authoring breadth: "
            f"`palette_families={int(summary.get('native_authoring_palette_family_count', 0) or 0)}` "
            f"(`{str(summary.get('native_authoring_palette_family_label', '') or 'n/a')}`) | "
            f"`active_families={int(summary.get('native_authoring_active_family_count', 0) or 0)}` "
            f"(`{str(summary.get('native_authoring_active_family_label', '') or 'n/a')}`) | "
            f"`member_types={str(summary.get('native_authoring_member_type_label', '') or 'n/a')}`"
        )
    if bool(summary.get("native_authoring_portfolio_attached", False)):
        lines.append(
            f"- Native authoring portfolio: "
            f"`projects={int(summary.get('native_authoring_portfolio_project_count', 0) or 0)}` | "
            f"`complete={int(summary.get('native_authoring_portfolio_complete_project_count', 0) or 0)}` | "
            f"`signature={int(summary.get('native_authoring_portfolio_signature_verified_count', 0) or 0)}` | "
            f"`repro={int(summary.get('native_authoring_portfolio_package_reproducible_count', 0) or 0)}` | "
            f"`unmatched_inputs={int(summary.get('native_authoring_portfolio_unmatched_input_count', 0) or 0)}`"
        )
    if int(summary.get("native_authoring_portfolio_family_count", 0) or 0) > 0:
        lines.append(
            f"- Native authoring portfolio families: "
            f"`families={int(summary.get('native_authoring_portfolio_family_count', 0) or 0)}` | "
            f"`ready={int(summary.get('native_authoring_portfolio_ready_family_count', 0) or 0)}` | "
            f"`failed={int(summary.get('native_authoring_portfolio_failed_family_count', 0) or 0)}` | "
            f"`max_combos={int(summary.get('native_authoring_portfolio_max_solver_combo_count', 0) or 0)}` | "
            f"`max_mesh_requests={int(summary.get('native_authoring_portfolio_max_solver_mesh_request_count', 0) or 0)}` | "
            f"`family_status={str(summary.get('native_authoring_portfolio_family_status_label', '') or 'n/a')}`"
        )
    if bool(summary.get("native_authoring_family_corpus_attached", False)):
        lines.append(
            f"- Native authoring family corpus: "
            f"`families={int(summary.get('native_authoring_family_corpus_family_count', 0) or 0)}` | "
            f"`ready={int(summary.get('native_authoring_family_corpus_ready_family_count', 0) or 0)}` | "
            f"`public_refs={int(summary.get('native_authoring_family_corpus_public_reference_count', 0) or 0)}` | "
            f"`benchmark={int(summary.get('native_authoring_family_corpus_benchmark_reference_count', 0) or 0)}` | "
            f"`authority={int(summary.get('native_authoring_family_corpus_authority_reference_count', 0) or 0)}` | "
            f"`surfaces={str(summary.get('native_authoring_family_corpus_surface_label', '') or 'n/a')}` | "
            f"`unresolved_refs={int(summary.get('native_authoring_family_corpus_unresolved_reference_count', 0) or 0)}`"
        )
    if bool(summary.get("native_authoring_family_local_evidence_attached", False)):
        lines.append(
            f"- Native authoring local evidence: "
            f"`families={int(summary.get('native_authoring_family_local_evidence_family_count', 0) or 0)}` | "
            f"`concrete={int(summary.get('native_authoring_family_local_evidence_concrete_count', 0) or 0)}` | "
            f"`roundtrip={int(summary.get('native_authoring_family_local_evidence_roundtrip_count', 0) or 0)}` | "
            f"`benchmark_concrete={int(summary.get('native_authoring_family_local_evidence_benchmark_concrete_count', 0) or 0)}` | "
            f"`review_concrete={int(summary.get('native_authoring_family_local_evidence_review_concrete_count', 0) or 0)}` | "
            f"`registered_only={int(summary.get('native_authoring_family_local_evidence_registered_only_count', 0) or 0)}`"
        )
    if bool(summary.get("native_authoring_family_corpus_attached", False)):
        lines.append(
            f"- Native authoring runtime submission lane: "
            f"`attached={bool(summary.get('native_authoring_runtime_submission_attached', False))}` | "
            f"`ready={bool(summary.get('native_authoring_runtime_submission_ready', False))}` | "
            f"`submissions={int(summary.get('native_authoring_runtime_submission_count', 0) or 0)}` | "
            f"`ready_submissions={int(summary.get('native_authoring_runtime_submission_ready_count', 0) or 0)}` | "
            f"`writeback_ready={int(summary.get('native_authoring_runtime_writeback_ready_count', 0) or 0)}` | "
            f"`queue={int(summary.get('native_authoring_runtime_submission_queue_count', 0) or 0)}` | "
            f"`status={str(summary.get('native_authoring_runtime_submission_status_label', '') or 'n/a')}`"
        )
        lines.append(
            f"- Native authoring runtime writeback depth: "
            f"`attached={bool(summary.get('native_authoring_runtime_writeback_depth_attached', False))}` | "
            f"`ready={bool(summary.get('native_authoring_runtime_writeback_depth_ready', False))}` | "
            f"`families={int(summary.get('native_authoring_runtime_writeback_depth_family_count', 0) or 0)}` | "
            f"`full={int(summary.get('native_authoring_runtime_writeback_depth_ready_family_count', 0) or 0)}` | "
            f"`signature={int(summary.get('native_authoring_runtime_writeback_depth_signature_family_count', 0) or 0)}` | "
            f"`repro={int(summary.get('native_authoring_runtime_writeback_depth_repro_family_count', 0) or 0)}` | "
            f"`snapshot={int(summary.get('native_authoring_runtime_writeback_depth_snapshot_family_count', 0) or 0)}` | "
            f"`queue_clear={int(summary.get('native_authoring_runtime_writeback_depth_queue_clear_family_count', 0) or 0)}`"
        )
        lines.append(
            f"- Native authoring local runtime scenario depth: "
            f"`attached={bool(summary.get('native_authoring_local_runtime_scenario_depth_attached', False))}` | "
            f"`ready={bool(summary.get('native_authoring_local_runtime_scenario_depth_ready', False))}` | "
            f"`families={int(summary.get('native_authoring_local_runtime_scenario_depth_family_count', 0) or 0)}` | "
            f"`deep={int(summary.get('native_authoring_local_runtime_scenario_depth_ready_family_count', 0) or 0)}` | "
            f"`trace_ready={int(summary.get('native_authoring_local_runtime_scenario_depth_trace_ready_family_count', 0) or 0)}` | "
            f"`mesh_ready={int(summary.get('native_authoring_local_runtime_scenario_depth_mesh_ready_family_count', 0) or 0)}` | "
            f"`runtime_ready={int(summary.get('native_authoring_local_runtime_scenario_depth_runtime_ready_family_count', 0) or 0)}` | "
            f"`omitted={int(summary.get('native_authoring_local_runtime_scenario_depth_omitted_family_count', 0) or 0)}`"
        )
        lines.append(
            f"- Native authoring local variant/writeback trace: "
            f"`attached={bool(summary.get('native_authoring_local_variant_writeback_trace_attached', False))}` | "
            f"`ready={bool(summary.get('native_authoring_local_variant_writeback_trace_ready', False))}` | "
            f"`families={int(summary.get('native_authoring_local_variant_writeback_trace_family_count', 0) or 0)}` | "
            f"`deep={int(summary.get('native_authoring_local_variant_writeback_trace_ready_family_count', 0) or 0)}` | "
            f"`workspace_variant={int(summary.get('native_authoring_local_variant_workspace_variant_ready_family_count', 0) or 0)}` | "
            f"`solver_variant={int(summary.get('native_authoring_local_variant_solver_variant_ready_family_count', 0) or 0)}` | "
            f"`writeback_trace={int(summary.get('native_authoring_local_variant_writeback_trace_ready_family_trace_count', 0) or 0)}` | "
            f"`active_multi={int(summary.get('native_authoring_local_variant_active_multi_family_count', 0) or 0)}` | "
            f"`combo_multi={int(summary.get('native_authoring_local_variant_combo_multi_family_count', 0) or 0)}` | "
            f"`signed={int(summary.get('native_authoring_local_variant_signed_writeback_family_count', 0) or 0)}` | "
            f"`omitted={int(summary.get('native_authoring_local_variant_trace_omitted_family_count', 0) or 0)}`"
        )
        lines.append(
            f"- Native authoring multi-project runtime/writeback: "
            f"`attached={bool(summary.get('native_authoring_multi_project_runtime_writeback_attached', False))}` | "
            f"`ready={bool(summary.get('native_authoring_multi_project_runtime_writeback_ready', False))}` | "
            f"`projects={int(summary.get('native_authoring_multi_project_runtime_writeback_project_count', 0) or 0)}` | "
            f"`project_families={int(summary.get('native_authoring_multi_project_runtime_writeback_project_family_count', 0) or 0)}` | "
            f"`full={int(summary.get('native_authoring_multi_project_runtime_writeback_full_count', 0) or 0)}` | "
            f"`ready_projects={int(summary.get('native_authoring_multi_project_runtime_writeback_ready_project_count', 0) or 0)}` | "
            f"`signature={int(summary.get('native_authoring_multi_project_runtime_writeback_signature_project_count', 0) or 0)}` | "
            f"`repro={int(summary.get('native_authoring_multi_project_runtime_writeback_repro_project_count', 0) or 0)}` | "
            f"`snapshot={int(summary.get('native_authoring_multi_project_runtime_writeback_snapshot_project_count', 0) or 0)}` | "
            f"`queue_clear={int(summary.get('native_authoring_multi_project_runtime_writeback_queue_clear_project_count', 0) or 0)}`"
        )
    if int(summary.get("advanced_holdout_count", 0) or 0) > 0:
        lines.append(
            f"- Advanced holdouts: "
            f"`count={int(summary.get('advanced_holdout_count', 0) or 0)}` | "
            f"`ready={int(summary.get('advanced_holdout_ready_count', 0) or 0)}` | "
            f"`open={int(summary.get('advanced_holdout_open_count', 0) or 0)}` | "
            f"`status={str(summary.get('advanced_holdout_status_label', '') or 'n/a')}`"
        )
    load_combination_engine_surface = _format_optional_gate_surface(
        str(summary.get("load_combination_engine_summary_line", "") or "").strip(),
        summary.get("load_combination_engine_pass")
        if isinstance(summary.get("load_combination_engine_pass"), bool) or summary.get("load_combination_engine_pass") is None
        else bool(summary.get("load_combination_engine_pass")),
    )
    if load_combination_engine_surface:
        lines.append(f"- Load-combination engine gate: `{load_combination_engine_surface}`")
    if int(summary.get("load_combination_engine_combo_count", 0) or 0):
        lines.append(
            f"- Load-combination engine depth: "
            f"`combos={int(summary.get('load_combination_engine_combo_count', 0) or 0)}` | "
            f"`families={int(summary.get('load_combination_engine_family_count', 0) or 0)}` | "
            f"`nested_depth={int(summary.get('load_combination_engine_max_nested_depth', 0) or 0)}`"
        )
    load_combination_editor_surface = _format_optional_gate_surface(
        str(summary.get("load_combination_editor_commercialization_summary_line", "") or "").strip(),
        summary.get("load_combination_editor_commercialization_pass")
        if isinstance(summary.get("load_combination_editor_commercialization_pass"), bool)
        or summary.get("load_combination_editor_commercialization_pass") is None
        else bool(summary.get("load_combination_editor_commercialization_pass")),
    )
    if load_combination_editor_surface:
        lines.append(f"- Load editor commercialization: `{load_combination_editor_surface}`")
    if str(summary.get("load_combination_editor_required_target_match_label", "")).strip():
        lines.append(
            f"- Load editor commercialization depth: "
            f"`kds_match={str(summary.get('load_combination_editor_required_target_match_label', '') or '').strip()}` | "
            f"`codecheck={'yes' if bool(summary.get('load_combination_editor_code_check_assembly_ready', False)) else 'check'}`"
        )
    reference_regression_surface = _format_optional_gate_surface(
        str(summary.get("reference_regression_summary_line", "") or "").strip(),
        summary.get("reference_regression_pass")
        if isinstance(summary.get("reference_regression_pass"), bool)
        or summary.get("reference_regression_pass") is None
        else bool(summary.get("reference_regression_pass")),
    )
    if reference_regression_surface:
        lines.append(f"- Reference regression loop: `{reference_regression_surface}`")
    advanced_ssi_surface = _format_optional_gate_surface(
        str(summary.get("advanced_ssi_summary_line", "") or "").strip(),
        summary.get("advanced_ssi_pass")
        if isinstance(summary.get("advanced_ssi_pass"), bool) or summary.get("advanced_ssi_pass") is None
        else bool(summary.get("advanced_ssi_pass")),
    )
    if advanced_ssi_surface:
        lines.append(f"- Advanced SSI gate: `{advanced_ssi_surface}`")
    if float(summary.get("advanced_ssi_peak_transfer_ratio_max", 0.0) or 0.0) > 0.0:
        lines.append(
            f"- Advanced SSI metrics: "
            f"`peak_transfer={float(summary.get('advanced_ssi_peak_transfer_ratio_max', 0.0) or 0.0):.3f}` "
            f"({str(summary.get('advanced_ssi_peak_transfer_group_id', '') or 'n/a')}) | "
            f"`group_efficiency={float(summary.get('advanced_ssi_min_group_interaction_efficiency_ratio', 0.0) or 0.0):.3f}`"
        )
    wind_workflow_surface = _format_optional_gate_surface(
        str(summary.get("wind_workflow_summary_line", "") or "").strip(),
        summary.get("wind_workflow_pass")
        if isinstance(summary.get("wind_workflow_pass"), bool) or summary.get("wind_workflow_pass") is None
        else bool(summary.get("wind_workflow_pass")),
    )
    if wind_workflow_surface:
        lines.append(f"- Wind workflow gate: `{wind_workflow_surface}`")
    if str(summary.get("wind_workflow_occupant_comfort_class", "")).strip():
        lines.append(
            f"- Wind workflow metrics: "
            f"`comfort_class={str(summary.get('wind_workflow_occupant_comfort_class', '') or '').strip()}` | "
            f"`crosswind_bias={float(summary.get('wind_workflow_occupant_comfort_crosswind_bias_ratio', 0.0) or 0.0):.3f}`"
        )
    if str(summary.get("performance_profiling_summary_line", "")).strip():
        lines.append(
            f"- Performance profiling: "
            f"`{str(summary.get('performance_profiling_summary_line', '')).strip()}`"
        )
    if int(summary.get("ndtha_step_series_depth", 0) or 0):
        lines.append(
            f"- NDTHA step-series depth: "
            f"`{int(summary.get('ndtha_step_series_depth', 0))}` "
            f"(max completed steps)"
        )
    if int(summary.get("ndtha_material_depth", 0) or 0):
        lines.append(
            f"- NDTHA material depth: "
            f"`{int(summary.get('ndtha_material_depth', 0))}` "
            f"(material-effect rows)"
        )
    if str(summary.get("ndtha_material_summary_line", "")).strip():
        lines.append(
            f"- NDTHA material surface: "
            f"`{str(summary.get('ndtha_material_summary_line', '')).strip()}`"
        )
    if str(summary.get("performance_profiling_detail_line", "")).strip():
        lines.append(
            f"- Performance detail: "
            f"`{str(summary.get('performance_profiling_detail_line', '')).strip()}`"
        )
    if str(summary.get("solver_truthfulness_summary_line", "")).strip():
        lines.append(
            f"- Solver truthfulness gate: "
            f"`{str(summary.get('solver_truthfulness_summary_line', '')).strip()}`"
        )
    if str(summary.get("hardest_external_10case_kickoff_summary_line", "")).strip():
        lines.append(
            f"- Hardest external 10-case kickoff: "
            f"`{str(summary.get('hardest_external_10case_kickoff_summary_line', '')).strip()}`"
        )
    if str(summary.get("nonlinear_generalization_summary_line", "")).strip():
        lines.append(
            f"- Nonlinear generalization: "
            f"`{str(summary.get('nonlinear_generalization_summary_line', '')).strip()}`"
        )
    if str(summary.get("workflow_productization_summary_line", "")).strip():
        lines.append(
            f"- Workflow/interoperability productization: "
            f"`{str(summary.get('workflow_productization_summary_line', '')).strip()}`"
        )
    if str(summary.get("workflow_contact_coupling_summary_line", "")).strip():
        lines.append(
            f"- Workflow contact coupling: "
            f"`{str(summary.get('workflow_contact_coupling_summary_line', '')).strip()}`"
        )
    if str(summary.get("commercial_workflow_breadth_summary_line", "")).strip():
        lines.append(
            f"- Commercial workflow breadth: "
            f"`{str(summary.get('commercial_workflow_breadth_summary_line', '')).strip()}`"
        )
    if commercial_workflow_breadth_summary:
        lines.append(
            f"- Commercial workflow breadth surfaces: "
            f"`ready={int(summary.get('commercial_workflow_breadth_ready_surface_count', 0) or 0)}/"
            f"{int(summary.get('commercial_workflow_breadth_total_surface_count', 0) or 0)}` | "
            f"`status={str(summary.get('commercial_workflow_breadth_gap_status', '') or 'n/a')}` | "
            f"`pass={bool(summary.get('commercial_workflow_breadth_pass', False))}`"
        )
        lines.append(
            f"- Construction-stage breadth: "
            f"`ready={bool(commercial_workflow_breadth_summary.get('construction_stage_ready', False))}` | "
            f"`history_snapshots={int(commercial_workflow_breadth_summary.get('construction_stage_history_snapshot_count', 0) or 0)}` | "
            f"`max_diff_shortening_mm={float(commercial_workflow_breadth_summary.get('construction_stage_max_differential_shortening_mm', 0.0) or 0.0):.3f}`"
        )
        lines.append(
            f"- Rail/tunnel breadth: "
            f"`ready={bool(commercial_workflow_breadth_summary.get('rail_tunnel_ready', False))}` | "
            f"`serviceability={str(commercial_workflow_breadth_summary.get('rail_tunnel_serviceability_status', '') or 'n/a')}` | "
            f"`maintenance_priority={str(commercial_workflow_breadth_summary.get('rail_tunnel_maintenance_priority', '') or 'n/a')}` | "
            f"`recommended_actions={int(commercial_workflow_breadth_summary.get('rail_tunnel_recommended_action_count', 0) or 0)}`"
        )
        lines.append(
            f"- Design redesign-loop breadth: "
            f"`ready={bool(commercial_workflow_breadth_summary.get('design_redesign_loop_ready', False))}` | "
            f"`traceability_ratio={float(commercial_workflow_breadth_summary.get('design_report_traceability_ratio', 0.0) or 0.0):.3f}` | "
            f"`ng_members={int(commercial_workflow_breadth_summary.get('design_report_ng_member_count', 0) or 0)}` | "
            f"`suggestions={int(commercial_workflow_breadth_summary.get('section_optimizer_suggestion_count', 0) or 0)}` | "
            f"`strengthen={int(commercial_workflow_breadth_summary.get('section_optimizer_strengthen_count', 0) or 0)}` | "
            f"`reduce={int(commercial_workflow_breadth_summary.get('section_optimizer_reduce_count', 0) or 0)}` | "
            f"`governing_clauses={int(commercial_workflow_breadth_summary.get('governing_clause_count', 0) or 0)}`"
        )
    if str(summary.get("korean_source_ingest_summary_line", "")).strip():
        lines.append(
            f"- KR ingest: "
            f"`{str(summary.get('korean_source_ingest_summary_line', '')).strip()}`"
        )
    if str(summary.get("korean_structural_preview_queue_summary_line", "")).strip():
        lines.append(
            f"- KR preview queue: "
            f"`{str(summary.get('korean_structural_preview_queue_summary_line', '')).strip()}`"
        )
    if str(summary.get("opensees_canonical_breadth_summary_line", "")).strip():
        lines.append(
            f"- OpenSees canonical breadth: "
            f"`{str(summary.get('opensees_canonical_breadth_summary_line', '')).strip()}`"
        )
    if str(summary.get("commercial_readiness_summary_line", "")).strip():
        lines.append(
            f"- Commercial readiness: "
            f"`{str(summary.get('commercial_readiness_summary_line', '')).strip()}`"
        )
    lines.append(
        f"- MIDAS optimized export artifact present: `{bool(summary.get('mgt_export_artifact_exists', False))}` "
        f"(contract_pass=`{bool(summary.get('mgt_export_contract_pass', False))}`, "
        f"support_mode=`{str(summary.get('mgt_export_support_mode', 'missing'))}`, "
        f"supported_changes=`{int(summary.get('mgt_export_supported_change_count', 0))}`, "
        f"unsupported_changes=`{int(summary.get('mgt_export_unsupported_change_count', 0))}`, "
        f"direct_patch_changes=`{int(summary.get('mgt_export_direct_patch_change_count', 0))}`, "
        f"direct_patch_families=`{str(summary.get('mgt_export_direct_patch_action_family_label', ''))}`, "
        f"special_member_families=`{str(summary.get('mgt_export_special_member_direct_patch_action_family_label', ''))}`, "
        f"special_member_zero_touch=`{str(summary.get('mgt_export_special_member_zero_touch_verified_action_family_label', ''))}`, "
        f"rebar_namespace_mode=`{str(summary.get('mgt_export_rebar_payload_namespace_mode', 'none'))}`, "
        f"rebar_material_namespace_present=`{bool(summary.get('mgt_export_rebar_payload_material_level_namespace_present', False))}`, "
        f"rebar_group_local_namespace_present=`{bool(summary.get('mgt_export_rebar_payload_group_local_namespace_present', False))}`, "
        f"material_rebar_payloads=`{int(summary.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(summary.get('mgt_export_material_level_rebar_payload_row_count', 0))}`, "
        f"group_local_rebar_payloads=`{int(summary.get('mgt_export_group_local_rebar_payload_available_count', 0))}/{int(summary.get('mgt_export_group_local_rebar_payload_row_count', 0))}`, "
        f"group_local_connection_detailing_payloads=`{int(summary.get('mgt_export_group_local_connection_detailing_payload_available_count', 0))}/{int(summary.get('mgt_export_group_local_connection_detailing_payload_row_count', 0))}`, "
        f"connection_direct_patch_eligible=`{int(summary.get('mgt_export_connection_detailing_direct_patch_eligible_change_count', 0))}`, "
        f"group_local_detailing_payloads=`{int(summary.get('mgt_export_group_local_detailing_payload_available_count', 0))}/{int(summary.get('mgt_export_group_local_detailing_payload_row_count', 0))}`, "
        f"connection_namespace_mode=`{str(summary.get('mgt_export_connection_detailing_payload_namespace_mode', 'none'))}`, "
        f"connection_group_local_namespace_present=`{bool(summary.get('mgt_export_connection_detailing_payload_group_local_namespace_present', False))}`, "
        f"connection_structured_payload_mapped=`{int(summary.get('mgt_export_connection_detailing_structured_payload_mapped_change_count', 0))}`, "
        f"connection_delivery_mode=`{str(summary.get('mgt_export_connection_detailing_delivery_mode', ''))}`, "
        f"detailing_namespace_mode=`{str(summary.get('mgt_export_detailing_payload_namespace_mode', 'none'))}`, "
        f"detailing_group_local_namespace_present=`{bool(summary.get('mgt_export_detailing_payload_group_local_namespace_present', False))}`, "
        f"detailing_direct_patch_eligible=`{int(summary.get('mgt_export_detailing_direct_patch_eligible_change_count', 0))}`, "
        f"detailing_structured_payload_mapped=`{int(summary.get('mgt_export_detailing_structured_payload_mapped_change_count', 0))}`, "
        f"detailing_delivery_mode=`{str(summary.get('mgt_export_detailing_delivery_mode', ''))}`, "
        f"rebar_direct_patch_eligible=`{int(summary.get('mgt_export_rebar_direct_patch_eligible_change_count', 0))}`, "
        f"patched_material_rows=`{int(summary.get('mgt_export_patched_material_row_count', 0))}`, "
        f"cloned_materials=`{int(summary.get('mgt_export_cloned_material_count', 0))}`, "
        f"rebar_delivery_mode=`{str(summary.get('mgt_export_rebar_delivery_mode', ''))}`, "
        f"evidence_model=`{str(summary.get('mgt_export_evidence_model', ''))}`, "
        f"rebar_direct_patch_blockers=`{str(summary.get('mgt_export_rebar_direct_patch_ineligible_reason_label', ''))}`, "
        f"rebar_mapping_sources=`{str(summary.get('mgt_export_rebar_direct_patch_mapping_source_label', ''))}`, "
        f"sidecar_families=`{str(summary.get('mgt_export_instruction_sidecar_action_family_label', ''))}`, "
        f"sidecar_audit=`{str(summary.get('mgt_export_instruction_sidecar_audit_only_action_family_label', ''))}` "
        f"({int(summary.get('mgt_export_instruction_sidecar_audit_only_change_count', 0))}), "
        f"sidecar_manual=`{str(summary.get('mgt_export_instruction_sidecar_manual_input_action_family_label', ''))}` "
        f"({int(summary.get('mgt_export_instruction_sidecar_manual_input_change_count', 0))}), "
        f"audit_manifest=`{str(summary.get('mgt_export_audit_review_manifest_action_family_label', ''))}` "
        f"({int(summary.get('mgt_export_audit_review_manifest_change_count', 0))}), "
        f"audit_packets=`{str(summary.get('mgt_export_audit_review_packet_action_family_label', ''))}` "
        f"({int(summary.get('mgt_export_audit_review_packet_count', 0))}), "
        f"audit_packet_files=`{str(summary.get('mgt_export_audit_review_packet_file_action_family_label', ''))}` "
        f"({int(summary.get('mgt_export_audit_review_packet_file_count', 0))}), "
        f"audit_queue=`{str(summary.get('mgt_export_audit_review_queue_action_family_label', ''))}` "
        f"({int(summary.get('mgt_export_audit_review_queue_item_count', 0))}), "
        f"audit_queue_status=`{str(summary.get('mgt_export_audit_review_queue_status_label', ''))}`, "
        f"audit_followup=`{str(summary.get('mgt_export_audit_review_followup_action_label', ''))}` "
        f"({int(summary.get('mgt_export_audit_review_followup_item_count', 0))}), "
        f"audit_followup_owner=`{str(summary.get('mgt_export_audit_review_followup_owner_label', ''))}`, "
        f"audit_followup_status=`{str(summary.get('mgt_export_audit_review_followup_status_label', ''))}`, "
        f"audit_followup_review_owner=`{str(summary.get('mgt_export_audit_review_followup_review_owner_label', ''))}`, "
        f"audit_followup_sla=`{str(summary.get('mgt_export_audit_review_followup_sla_state_label', ''))}`, "
        f"audit_followup_age=`{str(summary.get('mgt_export_audit_review_followup_age_bucket_label', ''))}`, "
        f"audit_followup_overdue=`{int(summary.get('mgt_export_audit_review_followup_overdue_item_count', 0))}`, "
        f"audit_resolution=`{str(summary.get('mgt_export_audit_review_resolution_action_label', ''))}`, "
        f"audit_resolution_status=`{str(summary.get('mgt_export_audit_review_resolution_status_label', ''))}`, "
        f"sidecar_priorities=`{str(summary.get('mgt_export_instruction_sidecar_review_priority_label', ''))}`, "
        f"sidecar_followups=`{str(summary.get('mgt_export_instruction_sidecar_followup_type_label', ''))}`, "
        f"cloned_sections=`{int(summary.get('mgt_export_cloned_section_count', 0))}`, "
        f"cloned_thicknesses=`{int(summary.get('mgt_export_cloned_thickness_count', 0))}`, "
        f"retargeted_elements=`{int(summary.get('mgt_export_retargeted_element_row_count', 0))}`)"
    )
    if str(summary.get("mgt_export_loadcomb_roundtrip_summary_line", "")).strip():
        lines.append(
            f"- MGT export LOADCOMB evidence: "
            f"`preview_exists={bool(summary.get('mgt_export_loadcomb_preview_exists', False))}` | "
            f"`roundtrip_pass={bool(summary.get('mgt_export_loadcomb_roundtrip_pass', False))}` | "
            f"`{str(summary.get('mgt_export_loadcomb_roundtrip_summary_line', '')).strip()}`"
        )
    lines.append(
        f"- MGT delivery boundary: `{str(summary.get('mgt_export_evidence_model', ''))}` | "
        f"`{str(summary.get('mgt_export_delivery_boundary', ''))}`"
    )
    lines.append("")
    if advanced_holdouts:
        lines.append("## Advanced Holdouts")
        lines.append("")
        lines.append("| Area | Status | Label | Mode | Why It Remains | Exit Criteria | Next Step |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in advanced_holdouts:
            lines.append(
                f"| {_markdown_cell(row.get('title', row.get('id', '')))} | {_markdown_cell(row.get('status', ''))} | "
                f"{_markdown_cell(row.get('status_label') or row.get('closure_label', ''))} | "
                f"{_markdown_cell(row.get('mode', ''))} | {_markdown_cell(row.get('why_it_remains', ''))} | "
                f"{_markdown_cell(row.get('exit_criteria', ''))} | {_markdown_cell(row.get('next_step', ''))} |"
            )
        lines.append("")
    lines.append("## Current Release Status")
    lines.append("")
    for key, value in release.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    if warnings:
        lines.append("## Active Warnings")
        lines.append("")
        for row in warnings:
            lines.append(f"- `{row.get('id', '')}` / `{row.get('title', '')}`: {row.get('value', '')}")
            if row.get("manifest"):
                lines.append(f"  - manifest: {row.get('manifest', '')}")
            if row.get("packet"):
                lines.append(f"  - packet: {row.get('packet', '')}")
            if row.get("packet_pdf"):
                lines.append(f"  - packet_pdf: {row.get('packet_pdf', '')}")
            if row.get("ack"):
                lines.append(f"  - ack: {row.get('ack', '')}")
            lines.append(f"  - why: {row.get('why', '')}")
        lines.append("")
    if holdout_buckets:
        lines.append("## Residual Holdout Model")
        lines.append("")
        lines.append("| Work Item | Category | Owner | Queue | Queue Status | Status | SLA | Due | Closure Evidence | Relative Share | Absolute Project % | Scope |")
        lines.append("|---|---|---|---|---|---|---:|---|---|---:|---|---|")
        for row in holdout_buckets:
            lines.append(
                f"| {row.get('work_item_id', '')} | {row.get('label', row.get('id', ''))} | "
                f"{row.get('owner', '')} | "
                f"{row.get('queue_name', '')} | {row.get('queue_status', '')} | {row.get('status', '')} | "
                f"{row.get('sla_label', '') or str(row.get('sla_hours', '')) + 'h'} | "
                f"{row.get('due_date', '')} | "
                f"{row.get('closure_evidence_required', '')} ({row.get('closure_evidence_status', '')}) | "
                f"{int(row.get('relative_share_pct', 0))}% | "
                f"{_coverage_range_label(row.get('absolute_project_pct_range'))} | {row.get('scope', '')} |"
            )
        lines.append("")
    if external_benchmark_submission_queue_rows:
        lines.append("## External Benchmark Submission Queue")
        lines.append("")
        lines.append(
            f"- `external_benchmark_submission_summary_line`: "
            f"`{str(summary.get('external_benchmark_submission_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `external_benchmark_submission_queue_count`: "
            f"`{int(summary.get('external_benchmark_submission_queue_count', len(external_benchmark_submission_queue_rows)) or 0)}` | "
            f"`ready={int(summary.get('external_benchmark_submission_queue_ready_count', 0) or 0)}` | "
            f"`review_pending={int(summary.get('external_benchmark_submission_queue_review_pending_count', 0) or 0)}` | "
            f"`blocked={int(summary.get('external_benchmark_submission_queue_blocked_count', 0) or 0)}`"
        )
        lines.append(
            f"- `external_benchmark_submission_onepage_attestation_status`: "
            f"`{str(summary.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown')}`"
        )
        if str(summary.get("external_benchmark_submission_recommended_start_mode", "")).strip() or str(
            summary.get("external_benchmark_submission_recommended_submission_scope", "")
        ).strip():
            lines.append(
                f"- `external_benchmark_submission_recommended_start_mode`: "
                f"`{str(summary.get('external_benchmark_submission_recommended_start_mode', '') or 'n/a')}` | "
                f"`external_benchmark_submission_recommended_submission_scope`: "
                f"`{str(summary.get('external_benchmark_submission_recommended_submission_scope', '') or 'n/a')}` | "
                f"`blocker={str(summary.get('external_benchmark_submission_blocker_label', '') or 'none')}` | "
                f"`caution={str(summary.get('external_benchmark_submission_caution_label', '') or 'none')}`"
            )
        lines.append("")
        lines.append("| Queue | Scope | Owner | Status | Onepage Attestation | Onepage Status | Dry-run Evidence |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in external_benchmark_submission_queue_rows:
            lines.append(
                f"| {_markdown_cell(row.get('queue_id', ''))} | {_markdown_cell(row.get('submission_scope', ''))} | "
                f"{_markdown_cell(row.get('owner', ''))} | {_markdown_cell(row.get('status', ''))} | "
                f"{_markdown_cell(row.get('onepage_attestation', ''))} | "
                f"{_markdown_cell(row.get('onepage_attestation_status', '') or 'unknown')} | "
                f"{_markdown_cell(row.get('dry_run_evidence', '') or 'n/a')} |"
            )
        lines.append("")
    lines.append("## Time-Saving Coverage")
    lines.append("")
    lines.append(f"- Estimated time saved for repeated analysis workload: `{_coverage_range_label(summary.get('estimated_time_saved_pct_range'))}`")
    lines.append(
        f"- Measured accelerated chain wall-clock (comparable rolling N={int(summary.get('measured_chain_rolling_sample_count', 0) or 0)}): "
        f"`{float(summary.get('measured_chain_rolling_total_minutes_mean', 0.0)):.2f} min` "
        f"(range `{_format_minute_range(summary.get('measured_chain_rolling_total_minutes_range'))}`)"
    )
    lines.append(
        f"- Comparable run selection: `{summary.get('measured_chain_rolling_selection_mode', 'n/a')}` | "
        f"`full_chain_samples={int(summary.get('measured_chain_full_chain_sample_count', 0) or 0)}` | "
        f"`comparable_samples={int(summary.get('measured_chain_comparable_sample_count', 0) or 0)}` | "
        f"`reference_steps={int(summary.get('measured_chain_comparable_reference_step_count', 0) or 0)}` | "
        f"`overlap_threshold={float(summary.get('measured_chain_comparable_overlap_threshold', 0.0) or 0.0):.2f}` | "
        f"`deployment_model={summary.get('measured_chain_comparable_reference_deployment_model', '')}` | "
        f"`strict_smoke={bool(summary.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}`"
    )
    lines.append(f"- Current measured chain wall-clock: `{float(summary.get('measured_chain_total_minutes', 0.0)):.2f} min`")
    lines.append(f"- Basis: `{summary.get('estimated_time_saved_basis', '')}`")
    if summary.get("empirical_smoke_runtime_saved_pct_range"):
        lines.append(
            f"- Empirical smoke runtime reduction: `{_coverage_range_label(summary.get('empirical_smoke_runtime_saved_pct_range'))}` "
            f"(mean `{float(summary.get('empirical_smoke_runtime_saved_pct_mean', 0.0)):.2f}%`)"
        )
    if summary.get("measured_chain_category_minutes"):
        lines.append(
            "- "
            f"`measured_chain_breakdown_min`: parser/screening `{float(summary.get('measured_chain_category_minutes', {}).get('parser_screening', 0.0)):.2f}`, "
            f"analysis/optimization `{float(summary.get('measured_chain_category_minutes', {}).get('analysis_optimization', 0.0)):.2f}`, "
            f"nonseismic/construction `{float(summary.get('measured_chain_category_minutes', {}).get('nonseismic_construction', 0.0)):.2f}`, "
            f"authority/crosscheck `{float(summary.get('measured_chain_category_minutes', {}).get('authority_crosscheck', 0.0)):.2f}`, "
            f"release/packaging `{float(summary.get('measured_chain_category_minutes', {}).get('release_packaging', 0.0)):.2f}`"
        )
    if summary.get("measured_chain_rolling_category_minutes_mean"):
        lines.append(
            "- "
            f"`measured_chain_breakdown_mean_min`: parser/screening `{float(summary.get('measured_chain_rolling_category_minutes_mean', {}).get('parser_screening', 0.0)):.2f}`, "
            f"analysis/optimization `{float(summary.get('measured_chain_rolling_category_minutes_mean', {}).get('analysis_optimization', 0.0)):.2f}`, "
            f"nonseismic/construction `{float(summary.get('measured_chain_rolling_category_minutes_mean', {}).get('nonseismic_construction', 0.0)):.2f}`, "
            f"authority/crosscheck `{float(summary.get('measured_chain_rolling_category_minutes_mean', {}).get('authority_crosscheck', 0.0)):.2f}`, "
            f"release/packaging `{float(summary.get('measured_chain_rolling_category_minutes_mean', {}).get('release_packaging', 0.0)):.2f}`"
        )
    lines.append(f"- Focus: `{summary.get('time_saving_focus', '')}`")
    lines.append("")
    if smoke_png.exists():
        try:
            smoke_png_rel = smoke_png.relative_to(path.parent)
        except Exception:
            smoke_png_rel = smoke_png.name
        lines.append("## Nightly Smoke Trend")
        lines.append("")
        lines.append(f"- `smoke_history_png`: `{smoke_png}`")
        if smoke_trend:
            lines.append(
                "- "
                f"`runtime_drift`: baseline `{float(smoke_trend.get('baseline_runtime_first_s', 0.0)):.4f}s -> {float(smoke_trend.get('baseline_runtime_last_s', 0.0)):.4f}s` "
                f"(`{float(smoke_trend.get('baseline_runtime_drift_s', 0.0)):+.4f}s`), "
                f"trial `{float(smoke_trend.get('trial_runtime_first_s', 0.0)):.4f}s -> {float(smoke_trend.get('trial_runtime_last_s', 0.0)):.4f}s` "
                f"(`{float(smoke_trend.get('trial_runtime_drift_s', 0.0)):+.4f}s`)"
            )
            lines.append(
                "- "
                f"`max_dcr_drift`: baseline `{float(smoke_trend.get('baseline_max_dcr_first', 0.0)):.4f} -> {float(smoke_trend.get('baseline_max_dcr_last', 0.0)):.4f}` "
                f"(`{float(smoke_trend.get('baseline_max_dcr_drift', 0.0)):+.4f}`), "
                f"trial `{float(smoke_trend.get('trial_max_dcr_first', 0.0)):.4f} -> {float(smoke_trend.get('trial_max_dcr_last', 0.0)):.4f}` "
                f"(`{float(smoke_trend.get('trial_max_dcr_drift', 0.0)):+.4f}`)"
            )
        lines.append("")
        lines.append(f"![Nightly Smoke Trend]({smoke_png_rel})")
        lines.append("")
    if measured_chain_png.exists():
        try:
            measured_chain_png_rel = measured_chain_png.relative_to(path.parent)
        except Exception:
            measured_chain_png_rel = measured_chain_png.name
        lines.append("## Measured Chain Category Trend")
        lines.append("")
        lines.append(f"- `measured_chain_category_png`: `{measured_chain_png}`")
        lines.append("")
        lines.append(f"![Measured Chain Category Trend]({measured_chain_png_rel})")
        lines.append("")
    lines.append("## Observed Strengths")
    lines.append("")
    for item in strengths:
        lines.append(
            f"- `{item['title']}`: {item['evidence']}"
        )
    lines.append("")
    if str(summary.get("midas_kds_row_provenance_export_summary_line", "")).strip() or summary.get(
        "midas_kds_row_provenance_preview_rows"
    ):
        lines.append("## Appendix: MIDAS KDS Row Provenance Export")
        lines.append("")
        lines.append(
            f"- `summary`: `{str(summary.get('midas_kds_row_provenance_export_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `artifacts`: json=`{artifacts.get('midas_kds_row_provenance_export_json', '') or 'n/a'}` | "
            f"csv=`{artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'}` | "
            f"report=`{artifacts.get('midas_kds_row_provenance_export_report', '') or 'n/a'}`"
        )
        lines.append(
            "- `row-provenance sync`: `the Review surface and row-provenance appendix stay bidirectionally aligned on the same Hazard and Rule Family slices; "
            "the appendix exposes explicit viewer_row_url and viewer_slice_url reverse-sync links back to the matching viewer row and slice.`"
        )
        preview_rows = [
            row for row in (summary.get("midas_kds_row_provenance_preview_rows") or []) if isinstance(row, dict)
        ]
        clause_filter_rows = [
            row for row in (summary.get("midas_kds_row_provenance_clause_filter_rows") or []) if isinstance(row, dict)
        ]
        member_filter_rows = [
            row for row in (summary.get("midas_kds_row_provenance_member_filter_rows") or []) if isinstance(row, dict)
        ]
        hazard_filter_rows = [
            row for row in (summary.get("midas_kds_row_provenance_hazard_filter_rows") or []) if isinstance(row, dict)
        ]
        rule_family_filter_rows = [
            row for row in (summary.get("midas_kds_row_provenance_rule_family_filter_rows") or []) if isinstance(row, dict)
        ]
        if preview_rows:
            lines.extend(
                [
                    "",
                    "| Combination | Member | Clause | Baseline Focus | Mode | Clause Provenance | Member Inventory |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in preview_rows:
                lines.append(
                    f"| {row.get('combination_name', '')} | {row.get('member_id', '')} | {row.get('clause_label', '')} | "
                    f"{row.get('baseline_focus_member_id', '')} | {row.get('bridge_row_provenance_mode_label', '')} | "
                    f"{row.get('clause_provenance_summary_label', '')} | {row.get('bridge_member_inventory_summary_label', '')} |"
                )
            lines.append("")
        if clause_filter_rows:
            lines.extend(
                [
                    "| Clause | Rows | Members | Combos | Top Member | Top D/C |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for row in clause_filter_rows:
                lines.append(
                    f"| {row.get('clause_label', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                    f"{row.get('combination_count', '')} | {row.get('top_member_id', '')} | {row.get('top_dcr_label', '')} |"
                )
            lines.append("")
        if member_filter_rows:
            lines.extend(
                [
                    "| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for row in member_filter_rows:
                lines.append(
                    f"| {row.get('member_id', '')} | {row.get('baseline_focus_member_id', '')} | {row.get('row_count', '')} | "
                    f"{row.get('clause_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} |"
                )
            lines.append("")
        if hazard_filter_rows:
            lines.extend(
                [
                    "| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in hazard_filter_rows:
                lines.append(
                    f"| {row.get('hazard_type', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                    f"{row.get('clause_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} | {row.get('top_dcr_label', '')} |"
                )
            lines.append("")
        if rule_family_filter_rows:
            lines.extend(
                [
                    "| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in rule_family_filter_rows:
                lines.append(
                    f"| {row.get('rule_family', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                    f"{row.get('hazard_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} | {row.get('top_dcr_label', '')} |"
                )
            lines.append("")
    if str(summary.get("midas_native_roundtrip_summary_line", "")).strip() or midas_native_roundtrip_taxonomy_case_counts:
        lines.append("## Appendix: MIDAS Native Roundtrip Unsupported/Lossy Card Families")
        lines.append("")
        lines.append(
            f"- `summary`: `{str(summary.get('midas_native_roundtrip_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `artifacts`: appendix_md=`{artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'}` | "
            f"appendix_json=`{artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}`"
        )
        lines.append(
            f"- `batch_markdowns`: `{', '.join(midas_native_roundtrip_structure_type_batch_markdowns) or 'n/a'}`"
        )
        lines.append(
            "- `public-preview note`: `public archive-derived preview write-back baselines are counted separately from original public native .mgt baselines.`"
        )
        lines.append(
            f"- `public split`: public_native_ready={int(summary.get('midas_native_roundtrip_public_native_writeback_ready_count', 0))} | "
            f"public_raw_ready={int(summary.get('midas_native_roundtrip_public_raw_native_writeback_ready_count', 0))} | "
            f"public_bridge_ready={int(summary.get('midas_native_roundtrip_public_bridge_writeback_ready_count', 0))} | "
            f"public_archive_preview_ready={int(summary.get('midas_native_roundtrip_public_archive_preview_writeback_ready_count', 0))} | "
            f"public_structural_preview_ready={int(summary.get('midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count', 0))} | "
            f"public_source_ready={int(summary.get('midas_native_roundtrip_public_source_writeback_ready_count', 0))} | "
            f"fixture_ready={int(summary.get('midas_native_roundtrip_fixture_native_writeback_ready_count', 0))} | "
            f"repo_ready={int(summary.get('midas_native_roundtrip_repo_native_writeback_ready_count', 0))} | "
            f"experiment_ready={int(summary.get('midas_native_roundtrip_experiment_native_writeback_ready_count', 0))}"
        )
        if midas_native_roundtrip_taxonomy_case_counts:
            lines.append(
                f"- `taxonomy_case_counts`: `{json.dumps(midas_native_roundtrip_taxonomy_case_counts, ensure_ascii=False, sort_keys=True)}`"
            )
        if midas_native_roundtrip_taxonomy_card_family_histogram:
            lines.append(
                f"- `taxonomy_card_family_histogram`: `{json.dumps(midas_native_roundtrip_taxonomy_card_family_histogram, ensure_ascii=False, sort_keys=True)}`"
            )
        if midas_native_roundtrip_structure_type_batch_markdowns:
            lines.append("")
            lines.extend(["| Structure Type Batch Markdown |", "|---|"])
            for batch_markdown in midas_native_roundtrip_structure_type_batch_markdowns:
                lines.append(f"| `{batch_markdown}` |")
            lines.append("")
    irregular_structure_summary_line = str(summary.get("irregular_structure_summary_line", "") or "").strip()
    irregular_top5_manifest_path = str(summary.get("irregular_top5_execution_manifest_path", "") or "").strip()
    irregular_top5_rows: list[dict[str, Any]] = []
    if irregular_top5_manifest_path and Path(irregular_top5_manifest_path).exists():
        irregular_top5_manifest = _load_json(Path(irregular_top5_manifest_path))
        if isinstance(irregular_top5_manifest.get("top5_families"), list):
            irregular_top5_rows = [row for row in irregular_top5_manifest.get("top5_families", []) if isinstance(row, dict)]
    if irregular_structure_summary_line or irregular_top5_rows:
        lines.append("## Appendix: Irregular Structure Track")
        lines.append("")
        lines.append(f"- `summary`: `{irregular_structure_summary_line or 'n/a'}`")
        lines.append(
            f"- `gate_report`: `{str(summary.get('irregular_structure_gate_report_path', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `top5_manifest`: `{irregular_top5_manifest_path or 'n/a'}`"
        )
        lines.append(
            f"- `source_catalog`: `{str(summary.get('irregular_structure_source_catalog_path', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `priority_manifest`: `{str(summary.get('irregular_priority_manifest_path', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `collection_report`: `{str(summary.get('irregular_structure_collection_report_path', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `triage_report`: `{str(summary.get('irregular_triage_report_path', '')).strip() or 'n/a'}`"
        )
        irregular_top5_family_ids = [
            str(row.get("family_id", "") or "").strip()
            for row in irregular_top5_rows
            if str(row.get("family_id", "") or "").strip()
        ]
        lines.append(
            f"- `top5_family_ids`: `{', '.join(irregular_top5_family_ids) or 'n/a'}`"
        )
        if irregular_top5_rows:
            lines.extend(
                [
                    "",
                    "| Family | Priority | Mode | Sources | Local Ready | Remote Candidates | Authority Fit | AI Learning Fit |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            for row in irregular_top5_rows:
                lines.append(
                    f"| {row.get('family_id', '')} | {row.get('priority', '')} | {row.get('execution_mode', '')} | "
                    f"{row.get('source_record_count', '')} | {row.get('local_ready_source_count', '')} | "
                    f"{row.get('remote_candidate_source_count', '')} | {row.get('authority_fit', '')} | {row.get('ai_learning_fit', '')} |"
                )
            lines.append("")
    if str(summary.get("commercial_workflow_breadth_summary_line", "")).strip() or commercial_workflow_breadth_rows:
        lines.append("## Appendix: Commercial Workflow Breadth")
        lines.append("")
        lines.append(
            f"- `summary`: `{str(summary.get('commercial_workflow_breadth_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `report`: `{str(summary.get('commercial_workflow_breadth_report_path', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `surface_status`: ready={int(summary.get('commercial_workflow_breadth_ready_surface_count', 0) or 0)}/"
            f"{int(summary.get('commercial_workflow_breadth_total_surface_count', 0) or 0)} | "
            f"gap_status=`{str(summary.get('commercial_workflow_breadth_gap_status', '') or 'n/a')}` | "
            f"pass=`{bool(summary.get('commercial_workflow_breadth_pass', False))}`"
        )
        if commercial_workflow_breadth_summary:
            lines.append(
                f"- `construction_stage`: ready={bool(commercial_workflow_breadth_summary.get('construction_stage_ready', False))} | "
                f"history_snapshots={int(commercial_workflow_breadth_summary.get('construction_stage_history_snapshot_count', 0) or 0)} | "
                f"max_diff_shortening_mm={float(commercial_workflow_breadth_summary.get('construction_stage_max_differential_shortening_mm', 0.0) or 0.0):.3f}"
            )
            lines.append(
                f"- `rail_tunnel`: ready={bool(commercial_workflow_breadth_summary.get('rail_tunnel_ready', False))} | "
                f"serviceability=`{str(commercial_workflow_breadth_summary.get('rail_tunnel_serviceability_status', '') or 'n/a')}` | "
                f"maintenance_priority=`{str(commercial_workflow_breadth_summary.get('rail_tunnel_maintenance_priority', '') or 'n/a')}` | "
                f"recommended_actions={int(commercial_workflow_breadth_summary.get('rail_tunnel_recommended_action_count', 0) or 0)}"
            )
            lines.append(
                f"- `design_redesign_loop`: ready={bool(commercial_workflow_breadth_summary.get('design_redesign_loop_ready', False))} | "
                f"traceability_ratio={float(commercial_workflow_breadth_summary.get('design_report_traceability_ratio', 0.0) or 0.0):.3f} | "
                f"ng_members={int(commercial_workflow_breadth_summary.get('design_report_ng_member_count', 0) or 0)} | "
                f"suggestions={int(commercial_workflow_breadth_summary.get('section_optimizer_suggestion_count', 0) or 0)} | "
                f"strengthen={int(commercial_workflow_breadth_summary.get('section_optimizer_strengthen_count', 0) or 0)} | "
                f"reduce={int(commercial_workflow_breadth_summary.get('section_optimizer_reduce_count', 0) or 0)} | "
                f"governing_clauses={int(commercial_workflow_breadth_summary.get('governing_clause_count', 0) or 0)}"
            )
        if commercial_workflow_breadth_artifact_links:
            lines.append(
                f"- `artifact_links`: `{json.dumps(commercial_workflow_breadth_artifact_links, ensure_ascii=False, sort_keys=True)}`"
            )
        else:
            lines.append("- `artifact_links`: `n/a`")
        if commercial_workflow_breadth_rows:
            table_lines = _markdown_table_lines(commercial_workflow_breadth_rows)
            if table_lines:
                lines.append("")
                lines.extend(table_lines)
                lines.append("")
    if (
        str(summary.get("native_authoring_solver_session_summary_line", "")).strip()
        or str(summary.get("native_authoring_ops_bundle_summary_line", "")).strip()
    ):
        lines.append("## Appendix: Native Authoring Commercialization Lane")
        lines.append("")
        lines.append(
            f"- `status`: `{str(summary.get('native_authoring_commercialization_status', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `commercialization`: `{str(summary.get('native_authoring_commercialization_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `solver_session`: `{str(summary.get('native_authoring_solver_session_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `ops_bundle`: `{str(summary.get('native_authoring_ops_bundle_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `runtime_submission_lane`: `{str(summary.get('native_authoring_runtime_submission_summary_line', '')).strip() or 'n/a'}`"
        )
        lines.append(
            f"- `breadth`: palette_families={int(summary.get('native_authoring_palette_family_count', 0) or 0)} "
            f"(`{str(summary.get('native_authoring_palette_family_label', '') or 'n/a')}`) | "
            f"active_families={int(summary.get('native_authoring_active_family_count', 0) or 0)} "
            f"(`{str(summary.get('native_authoring_active_family_label', '') or 'n/a')}`) | "
            f"member_types=`{str(summary.get('native_authoring_member_type_label', '') or 'n/a')}`"
        )
        lines.append(
            f"- `portfolio`: projects={int(summary.get('native_authoring_portfolio_project_count', 0) or 0)} | "
            f"complete={int(summary.get('native_authoring_portfolio_complete_project_count', 0) or 0)} | "
            f"signature={int(summary.get('native_authoring_portfolio_signature_verified_count', 0) or 0)} | "
            f"repro={int(summary.get('native_authoring_portfolio_package_reproducible_count', 0) or 0)} | "
            f"unmatched_inputs={int(summary.get('native_authoring_portfolio_unmatched_input_count', 0) or 0)}"
        )
        lines.append(
            f"- `portfolio_families`: families={int(summary.get('native_authoring_portfolio_family_count', 0) or 0)} | "
            f"ready={int(summary.get('native_authoring_portfolio_ready_family_count', 0) or 0)} | "
            f"failed={int(summary.get('native_authoring_portfolio_failed_family_count', 0) or 0)} | "
            f"max_combos={int(summary.get('native_authoring_portfolio_max_solver_combo_count', 0) or 0)} | "
            f"max_mesh_requests={int(summary.get('native_authoring_portfolio_max_solver_mesh_request_count', 0) or 0)} | "
            f"family_status=`{str(summary.get('native_authoring_portfolio_family_status_label', '') or 'n/a')}`"
        )
        lines.append(
            f"- `runtime_submission_counts`: submissions={int(summary.get('native_authoring_runtime_submission_count', 0) or 0)} | "
            f"ready={int(summary.get('native_authoring_runtime_submission_ready_count', 0) or 0)} | "
            f"writeback_ready={int(summary.get('native_authoring_runtime_writeback_ready_count', 0) or 0)} | "
            f"queue={int(summary.get('native_authoring_runtime_submission_queue_count', 0) or 0)} | "
            f"status=`{str(summary.get('native_authoring_runtime_submission_status_label', '') or 'n/a')}`"
        )
        lines.append(
            f"- `artifacts`: ops_bundle=`{artifacts.get('native_authoring_ops_bundle_json', '') or 'n/a'}` | "
            f"workspace=`{artifacts.get('native_authoring_workspace_summary_json', '') or 'n/a'}` | "
            f"solver_session=`{artifacts.get('native_authoring_solver_session_json', '') or 'n/a'}` | "
            f"loadcomb_preview=`{artifacts.get('native_authoring_solver_loadcomb_preview_mgt', '') or 'n/a'}` | "
            f"job_manifest=`{artifacts.get('native_authoring_job_manifest_json', '') or 'n/a'}` | "
            f"batch_report=`{artifacts.get('native_authoring_batch_job_report_json', '') or 'n/a'}` | "
            f"project_registry=`{artifacts.get('native_authoring_project_registry_json', '') or 'n/a'}` | "
            f"package=`{artifacts.get('native_authoring_project_package_zip', '') or 'n/a'}` | "
            f"signature=`{artifacts.get('native_authoring_project_registry_signature', '') or 'n/a'}` | "
            f"portfolio=`{artifacts.get('native_authoring_portfolio_workspace_json', '') or 'n/a'}` | "
            f"runtime_submission=`{artifacts.get('native_authoring_runtime_submission_lane_json', '') or 'n/a'}` | "
            f"runtime_writeback_depth=`{artifacts.get('native_authoring_runtime_writeback_depth_report_json', '') or 'n/a'}` | "
            f"local_runtime_depth=`{artifacts.get('native_authoring_local_runtime_scenario_depth_report_json', '') or 'n/a'}` | "
            f"solver_family_breadth=`{artifacts.get('native_authoring_solver_family_breadth_report_json', '') or 'n/a'}`"
        )
        lines.append(
            f"- `counts`: meshes={int(summary.get('native_authoring_solver_session_mesh_request_count', 0) or 0)} | "
            f"combos={int(summary.get('native_authoring_solver_session_combo_count', 0) or 0)} | "
            f"jobs={int(summary.get('native_authoring_ops_bundle_job_count', 0) or 0)} | "
            f"snapshots={int(summary.get('native_authoring_ops_bundle_snapshot_count', 0) or 0)} | "
            f"registry_artifacts={int(summary.get('native_authoring_ops_bundle_registry_artifact_count', 0) or 0)} | "
            f"registry_approvals={int(summary.get('native_authoring_ops_bundle_registry_approval_count', 0) or 0)}"
        )
        lines.append("")
    lines.append("## Remaining Gaps")
    lines.append("")
    for gap in gaps:
        lines.append(f"### {gap['id']} {gap['title']}")
        lines.append("")
        lines.append(f"- Severity: `{gap['severity']}`")
        lines.append(f"- Status: `{gap['status']}`")
        lines.append(f"- Why it remains: {gap['why']}")
        lines.append(f"- Evidence: {gap['evidence']}")
        lines.append(f"- Exit criteria: {gap['exit_criteria']}")
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nightly-release", default="implementation/phase1/release/nightly_release_gate_report.json")
    p.add_argument("--ci-gate", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--static-validation", default="implementation/phase1/static_artifact_validation_report.json")
    p.add_argument("--freeze-report", default="implementation/phase1/release/freeze_release_report.json")
    p.add_argument("--promotion-report", default="implementation/phase1/release/release_candidate_promotion_report.json")
    p.add_argument("--commercial-readiness", default="implementation/phase1/commercial_readiness_report.json")
    p.add_argument("--global-authority", default="implementation/phase1/global_authority_gate_report.json")
    p.add_argument("--hip-kernel-smoke", default="implementation/phase1/hip_kernel_smoke_report.json")
    p.add_argument("--midas-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument(
        "--mgt-export-output-mgt",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    p.add_argument(
        "--mgt-export-report",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.export_report.json",
    )
    p.add_argument(
        "--mgt-export-audit-review-queue-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json",
    )
    p.add_argument(
        "--mgt-export-audit-review-followup-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_followup_manifest.json",
    )
    p.add_argument("--construction-sequence", default="implementation/phase1/construction_sequence_gate_report.json")
    p.add_argument("--flexible-diaphragm", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    p.add_argument("--repro-version-lock", default="implementation/phase1/reproducibility_version_lock_report.json")
    p.add_argument("--release-registry", default="implementation/phase1/release/release_registry.json")
    p.add_argument("--kds-compliance", default="implementation/phase1/release/kds_compliance/kds_compliance_summary.json")
    p.add_argument("--solver-hip-e2e", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    p.add_argument("--solver-truthfulness-report", default="implementation/phase1/solver_truthfulness_gate_report.json")
    p.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    p.add_argument(
        "--hardest-external-10case-kickoff-report",
        default="implementation/phase1/hardest_external_10case_kickoff_gate_report.json",
    )
    p.add_argument("--rc-benchmark-lock", default="implementation/phase1/rc_benchmark_lock_report.json")
    p.add_argument("--quality-mgt-corpus", default="implementation/phase1/open_data/midas/quality_corpus_report.json")
    p.add_argument("--pbd-package", default="implementation/phase1/release/pbd_review/pbd_review_package_report.json")
    p.add_argument(
        "--design-opt-dataset-report",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument("--pbd-hinge-refresh-report", default="implementation/phase1/pbd_hinge_refresh_report.json")
    p.add_argument("--panel-zone-clash-report", default="implementation/phase1/panel_zone_clash_report.json")
    p.add_argument(
        "--panel-zone-solver-verified-inbox-status-report",
        default="implementation/phase1/panel_zone_solver_verified_inbox_status.json",
    )
    p.add_argument(
        "--foundation-optimization-report",
        default="implementation/phase1/release/design_optimization/foundation_optimization_report.json",
    )
    p.add_argument("--wind-raw-mapping-report", default="implementation/phase1/wind_tunnel_raw_mapping_report.json")
    p.add_argument(
        "--material-constitutive-gate-report",
        default=str(DEFAULT_MATERIAL_CONSTITUTIVE_GATE_REPORT),
    )
    p.add_argument(
        "--load-combination-engine-gate-report",
        default=str(DEFAULT_LOAD_COMBINATION_ENGINE_GATE_REPORT),
    )
    p.add_argument("--advanced-ssi-report", default=str(DEFAULT_ADVANCED_SSI_REPORT))
    p.add_argument("--wind-workflow-report", default=str(DEFAULT_WIND_WORKFLOW_REPORT))
    p.add_argument("--performance-profiling-report", default="implementation/phase1/performance_profiling_gate_report.json")
    p.add_argument("--committee-summary", default="implementation/phase1/release/committee_review/committee_summary.json")
    p.add_argument(
        "--native-authoring-workspace-summary",
        default=str(DEFAULT_NATIVE_AUTHORING_WORKSPACE_SUMMARY),
    )
    p.add_argument(
        "--native-authoring-solver-session-report",
        default="implementation/phase1/release/authoring/native_authoring_solver_session.json",
    )
    p.add_argument(
        "--native-authoring-ops-bundle-report",
        default="implementation/phase1/release/authoring/native_authoring_ops_bundle.json",
    )
    p.add_argument(
        "--native-authoring-portfolio-report",
        default=str(DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO),
    )
    p.add_argument(
        "--native-authoring-family-corpus-manifest",
        default=str(DEFAULT_NATIVE_AUTHORING_FAMILY_CORPUS_MANIFEST),
    )
    p.add_argument(
        "--native-authoring-family-tracks-report",
        default=str(DEFAULT_NATIVE_AUTHORING_FAMILY_TRACKS),
    )
    p.add_argument(
        "--native-authoring-runtime-submission-report",
        default=str(DEFAULT_NATIVE_AUTHORING_RUNTIME_SUBMISSION_LANE),
    )
    p.add_argument(
        "--native-authoring-runtime-writeback-depth-report",
        default=str(DEFAULT_NATIVE_AUTHORING_RUNTIME_WRITEBACK_DEPTH_REPORT),
    )
    p.add_argument(
        "--native-authoring-local-runtime-scenario-depth-report",
        default=str(DEFAULT_NATIVE_AUTHORING_LOCAL_RUNTIME_SCENARIO_DEPTH_REPORT),
    )
    p.add_argument(
        "--native-authoring-local-variant-writeback-trace-report",
        default=str(DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT),
    )
    p.add_argument(
        "--native-authoring-multi-project-runtime-writeback-report",
        default=str(DEFAULT_NATIVE_AUTHORING_MULTI_PROJECT_RUNTIME_WRITEBACK_REPORT),
    )
    p.add_argument(
        "--native-authoring-solver-family-breadth-report",
        default=str(DEFAULT_NATIVE_AUTHORING_SOLVER_FAMILY_BREADTH_REPORT),
    )
    p.add_argument(
        "--native-authoring-writeback-breadth-report",
        default=str(DEFAULT_NATIVE_AUTHORING_WRITEBACK_BREADTH_REPORT),
    )
    p.add_argument(
        "--project-ops-service-snapshot",
        default=str(DEFAULT_PROJECT_OPS_SERVICE_SNAPSHOT),
    )
    p.add_argument("--nightly-history-root", default="implementation/phase1/experiments/by_test/nightly_release_gate")
    p.add_argument("--nightly-history-limit", type=int, default=14)
    p.add_argument("--out-json", default="implementation/phase1/release/release_gap_report.json")
    p.add_argument("--out-md", default="implementation/phase1/release/release_gap_report.md")
    p.add_argument("--out-smoke-history-png", default="")
    p.add_argument("--out-measured-chain-category-png", default="")
    p.add_argument(
        "--load-combination-editor-commercialization-report",
        default=str(DEFAULT_LOAD_COMBINATION_EDITOR_COMMERCIALIZATION_REPORT),
    )
    p.add_argument("--reference-regression-report", default=str(DEFAULT_REFERENCE_REGRESSION_REPORT))
    args = p.parse_args()

    nightly = _load_json(Path(args.nightly_release))
    ci = _load_json(Path(args.ci_gate))
    static = _load_json(Path(args.static_validation))
    freeze = _load_json(Path(args.freeze_report))
    promotion = _load_json(Path(args.promotion_report))
    commercial = _load_json(Path(args.commercial_readiness))
    authority = _load_json(Path(args.global_authority))
    hip = _load_json(Path(args.hip_kernel_smoke))
    midas = _load_json(Path(args.midas_conversion))
    construction = _load_json(Path(args.construction_sequence))
    diaphragm = _load_json(Path(args.flexible_diaphragm))
    repro = _load_json(Path(args.repro_version_lock))
    release_registry = _load_json(Path(args.release_registry)) if Path(args.release_registry).exists() else {}
    kds = _load_json(Path(args.kds_compliance))
    solver_hip = _load_json(Path(args.solver_hip_e2e)) if Path(args.solver_hip_e2e).exists() else {}
    solver_truthfulness = _load_json(Path(args.solver_truthfulness_report)) if Path(args.solver_truthfulness_report).exists() else {}
    hardest_external_10case_kickoff = (
        _load_json(Path(args.hardest_external_10case_kickoff_report))
        if Path(args.hardest_external_10case_kickoff_report).exists()
        else {}
    )
    rc_benchmark = _load_json(Path(args.rc_benchmark_lock)) if Path(args.rc_benchmark_lock).exists() else {}
    quality_mgt_corpus = _load_json(Path(args.quality_mgt_corpus)) if Path(args.quality_mgt_corpus).exists() else {}
    pbd_package = _load_json(Path(args.pbd_package)) if Path(args.pbd_package).exists() else {}
    design_opt_dataset = _load_json(Path(args.design_opt_dataset_report)) if Path(args.design_opt_dataset_report).exists() else {}
    pbd_hinge_refresh = _load_json(Path(args.pbd_hinge_refresh_report)) if Path(args.pbd_hinge_refresh_report).exists() else {}
    panel_zone_clash = _load_json(Path(args.panel_zone_clash_report)) if Path(args.panel_zone_clash_report).exists() else {}
    panel_zone_solver_verified_inbox_status = (
        _load_json(Path(args.panel_zone_solver_verified_inbox_status_report))
        if Path(args.panel_zone_solver_verified_inbox_status_report).exists()
        else {}
    )
    foundation_optimization = _load_json(Path(args.foundation_optimization_report)) if Path(args.foundation_optimization_report).exists() else {}
    wind_raw_mapping = _load_json(Path(args.wind_raw_mapping_report)) if Path(args.wind_raw_mapping_report).exists() else {}
    material_constitutive_gate_report = (
        _load_json(Path(args.material_constitutive_gate_report))
        if Path(args.material_constitutive_gate_report).exists()
        else {}
    )
    load_combination_engine_report = (
        _load_json(Path(args.load_combination_engine_gate_report))
        if Path(args.load_combination_engine_gate_report).exists()
        else {}
    )
    load_combination_editor_commercialization_report = (
        _load_json(Path(args.load_combination_editor_commercialization_report))
        if Path(args.load_combination_editor_commercialization_report).exists()
        else {}
    )
    reference_regression_report = (
        _load_json(Path(args.reference_regression_report))
        if Path(args.reference_regression_report).exists()
        else {}
    )
    advanced_ssi_report = _load_json(Path(args.advanced_ssi_report)) if Path(args.advanced_ssi_report).exists() else {}
    wind_workflow_report = _load_json(Path(args.wind_workflow_report)) if Path(args.wind_workflow_report).exists() else {}
    performance_profiling_report = (
        _load_json(Path(args.performance_profiling_report)) if Path(args.performance_profiling_report).exists() else {}
    )
    committee_summary = _load_json(Path(args.committee_summary)) if Path(args.committee_summary).exists() else {}
    native_authoring_workspace_summary_path = Path(args.native_authoring_workspace_summary)
    native_authoring_workspace_summary = (
        _load_json(native_authoring_workspace_summary_path)
        if native_authoring_workspace_summary_path.exists()
        else {}
    )
    native_authoring_solver_session_path = Path(args.native_authoring_solver_session_report)
    native_authoring_solver_session = (
        _load_json(native_authoring_solver_session_path) if native_authoring_solver_session_path.exists() else {}
    )
    native_authoring_ops_bundle_path = Path(args.native_authoring_ops_bundle_report)
    native_authoring_ops_bundle = (
        _load_json(native_authoring_ops_bundle_path) if native_authoring_ops_bundle_path.exists() else {}
    )
    native_authoring_portfolio_path = Path(args.native_authoring_portfolio_report)
    if not native_authoring_portfolio_path.exists():
        for candidate in (
            DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO,
            DEFAULT_PROJECT_REGISTRY_PORTFOLIO_WORKSPACE,
            DEFAULT_PROJECT_REGISTRY_INDEX,
        ):
            if candidate.exists():
                native_authoring_portfolio_path = candidate
                break
    native_authoring_portfolio = (
        _load_json(native_authoring_portfolio_path) if native_authoring_portfolio_path.exists() else {}
    )
    native_authoring_family_corpus_manifest_path = Path(args.native_authoring_family_corpus_manifest)
    native_authoring_family_corpus_manifest = (
        _load_json(native_authoring_family_corpus_manifest_path)
        if native_authoring_family_corpus_manifest_path.exists()
        else {}
    )
    native_authoring_family_local_evidence_manifest_path = (
        DEFAULT_NATIVE_AUTHORING_FAMILY_LOCAL_EVIDENCE_MANIFEST
    )
    native_authoring_family_local_evidence_manifest = (
        _load_json(native_authoring_family_local_evidence_manifest_path)
        if native_authoring_family_local_evidence_manifest_path.exists()
        else {}
    )
    native_authoring_family_tracks_path = Path(args.native_authoring_family_tracks_report)
    native_authoring_family_tracks = (
        _load_json(native_authoring_family_tracks_path)
        if native_authoring_family_tracks_path.exists()
        else {}
    )
    native_authoring_runtime_submission_path = Path(args.native_authoring_runtime_submission_report)
    native_authoring_runtime_submission = (
        _load_json(native_authoring_runtime_submission_path)
        if native_authoring_runtime_submission_path.exists()
        else {}
    )
    native_authoring_runtime_writeback_depth_path = Path(
        args.native_authoring_runtime_writeback_depth_report
    )
    native_authoring_runtime_writeback_depth = (
        _load_json(native_authoring_runtime_writeback_depth_path)
        if native_authoring_runtime_writeback_depth_path.exists()
        else {}
    )
    native_authoring_local_runtime_scenario_depth_path = Path(
        args.native_authoring_local_runtime_scenario_depth_report
    )
    native_authoring_local_runtime_scenario_depth = (
        _load_json(native_authoring_local_runtime_scenario_depth_path)
        if native_authoring_local_runtime_scenario_depth_path.exists()
        else {}
    )
    native_authoring_local_variant_writeback_trace_path = Path(
        args.native_authoring_local_variant_writeback_trace_report
    )
    native_authoring_local_variant_writeback_trace = (
        _load_json(native_authoring_local_variant_writeback_trace_path)
        if native_authoring_local_variant_writeback_trace_path.exists()
        else {}
    )
    native_authoring_multi_project_runtime_writeback_path = Path(
        args.native_authoring_multi_project_runtime_writeback_report
    )
    native_authoring_multi_project_runtime_writeback = (
        _load_json(native_authoring_multi_project_runtime_writeback_path)
        if native_authoring_multi_project_runtime_writeback_path.exists()
        else {}
    )
    native_authoring_solver_family_breadth_path = Path(args.native_authoring_solver_family_breadth_report)
    native_authoring_solver_family_breadth = (
        _load_json(native_authoring_solver_family_breadth_path)
        if native_authoring_solver_family_breadth_path.exists()
        else {}
    )
    native_authoring_writeback_breadth_path = Path(args.native_authoring_writeback_breadth_report)
    native_authoring_writeback_breadth = (
        _load_json(native_authoring_writeback_breadth_path)
        if native_authoring_writeback_breadth_path.exists()
        else {}
    )
    project_ops_service_snapshot_path = Path(args.project_ops_service_snapshot)
    project_ops_service_snapshot = (
        _load_json(project_ops_service_snapshot_path)
        if project_ops_service_snapshot_path.exists()
        else {}
    )
    ndtha_stress = _load_json_from_disk(args.ndtha_stress_report)
    performance_profiling_summary = (
        performance_profiling_report.get("summary")
        if isinstance(performance_profiling_report.get("summary"), dict)
        else {}
    )
    workflow_productization_report = (
        ci.get("workflow_productization_report")
        if isinstance(ci.get("workflow_productization_report"), dict)
        else {}
    )
    workflow_productization_summary = (
        workflow_productization_report.get("summary")
        if isinstance(workflow_productization_report.get("summary"), dict)
        else {}
    )
    midas_section_library_summary_line = str(ci.get("midas_section_library_summary_line", "") or "").strip()
    midas_kds_geometry_bridge_summary_line = str(ci.get("midas_kds_geometry_bridge_summary_line", "") or "").strip()
    midas_kds_geometry_bridge_load_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="load_crosswalk",
    )
    midas_kds_geometry_bridge_semantic_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="semantic_crosswalk",
    )
    midas_kds_geometry_bridge_full_member_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="full_member_crosswalk",
    )
    midas_kds_geometry_bridge_full_section_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="full_section_crosswalk",
    )
    midas_kds_geometry_bridge_full_load_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="full_load_crosswalk",
    )
    midas_kds_geometry_bridge_full_crosswalk_depth = min(
        int(midas_kds_geometry_bridge_load_crosswalk_surface.get("count", 0) or 0),
        int(midas_kds_geometry_bridge_semantic_crosswalk_surface.get("count", 0) or 0),
    )
    ndtha_stress_rows = ndtha_stress.get("rows") if isinstance(ndtha_stress.get("rows"), list) else []
    ndtha_step_series_depth = max(
        [
            int(row.get("summary", {}).get("step_count_completed", 0) or 0)
            for row in ndtha_stress_rows
            if isinstance(row, dict)
        ]
        or [0]
    )
    if not ndtha_step_series_depth:
        ndtha_step_series_depth = int(
            ci.get("ndtha_step_series_depth", (committee_summary.get("metrics") or {}).get("ndtha_step_series_depth", 0))
            or 0
        )
    ndtha_material_surface = _ndtha_material_surface(ndtha_stress)
    ndtha_material_depth = int(ndtha_material_surface.get("material_depth", 0) or 0)
    ndtha_material_summary_line = str(
        ci.get("ndtha_material_summary_line", ndtha_material_surface.get("summary_line", "")) or ""
    ).strip()
    midas_loadcomb_roundtrip_summary_line = str(ci.get("midas_loadcomb_roundtrip_summary_line", "") or "").strip()
    commercial_benchmark_breadth_summary_line = str(ci.get("commercial_benchmark_breadth_summary_line", "") or "").strip()
    solver_breadth_summary_line = str(ci.get("solver_breadth_summary_line", "") or "").strip()
    element_material_breadth_summary_line = str(ci.get("element_material_breadth_summary_line", "") or "").strip()
    material_constitutive_surface = _extract_gate_surface_with_report(
        {"material_constitutive_report": material_constitutive_gate_report},
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="material_constitutive",
        direct_report=material_constitutive_gate_report,
    )
    material_constitutive_summary = material_constitutive_surface["summary"]
    material_constitutive_summary_line = str(material_constitutive_surface.get("summary_line", "") or "").strip()
    material_constitutive_pass = material_constitutive_surface.get("pass")
    material_constitutive_calibration_matrix_pass_row_count = int(
        _first_int(
            material_constitutive_summary.get("calibration_matrix_pass_row_count"),
            material_constitutive_summary.get("calibration_matrix_row_count"),
        )
        or 0
    )
    material_constitutive_cyclic_library_reversal_count = int(
        _first_int(material_constitutive_summary.get("cyclic_library_reversal_count")) or 0
    )
    material_constitutive_bond_interface_cyclic_reversal_count = int(
        _first_int(material_constitutive_summary.get("bond_interface_cyclic_reversal_count")) or 0
    )
    steel_composite_constitutive_gate_summary_line, steel_composite_constitutive_gate_pass = _extract_optional_gate_surface(
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="steel_composite_constitutive",
    )
    midas_kds_row_provenance_export_summary_line = str(
        ci.get("midas_kds_row_provenance_export_summary_line", "")
        or committee_summary.get("midas_kds_row_provenance_export_summary_line", "")
        or (
            committee_summary.get("metrics", {}).get("midas_kds_row_provenance_export_summary_line", "")
            if isinstance(committee_summary.get("metrics"), dict)
            else ""
        )
        or ""
    ).strip()
    contact_readiness_summary_line = str(ci.get("contact_readiness_summary_line", "") or "").strip()
    foundation_soil_link_summary_line = str(ci.get("foundation_soil_link_summary_line", "") or "").strip()
    structural_contact_summary_line = str(ci.get("structural_contact_summary_line", "") or "").strip()
    general_fe_contact_matrix_summary_line = str(ci.get("general_fe_contact_matrix_summary_line", "") or "").strip()
    surface_interaction_benchmark_summary_line = str(ci.get("surface_interaction_benchmark_summary_line", "") or "").strip()
    midas_interoperability_summary_line = str(ci.get("midas_interoperability_summary_line", "") or "").strip()
    midas_native_roundtrip_summary_line = str(ci.get("midas_native_roundtrip_summary_line", "") or "").strip()
    support_search_surface = _extract_support_search_surface(
        str(
            ci.get("support_search_summary_line", "")
            or (committee_summary.get("metrics") or {}).get("support_search_summary_line", "")
            or foundation_soil_link_summary_line
            or ""
        )
    )
    support_search_summary_line = str(support_search_surface.get("summary_line", "") or "").strip()
    load_combination_engine_surface = _extract_gate_surface_with_report(
        {"load_combination_engine_report": load_combination_engine_report},
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="load_combination_engine",
        direct_report=load_combination_engine_report,
    )
    load_combination_engine_summary = load_combination_engine_surface["summary"]
    load_combination_engine_summary_line = str(load_combination_engine_surface.get("summary_line", "") or "").strip()
    load_combination_engine_pass = load_combination_engine_surface.get("pass")
    load_combination_combo_family_counts = (
        load_combination_engine_summary.get("runtime_combo_family_counts_total")
        if isinstance(load_combination_engine_summary.get("runtime_combo_family_counts_total"), dict)
        else {}
    )
    load_combination_case_family_counts = (
        load_combination_engine_summary.get("runtime_case_family_counts_total")
        if isinstance(load_combination_engine_summary.get("runtime_case_family_counts_total"), dict)
        else {}
    )
    load_combination_engine_combo_count = int(
        _first_int(
            load_combination_engine_summary.get("combo_count"),
            load_combination_engine_summary.get("runtime_combo_count_max"),
            load_combination_engine_summary.get("runtime_combo_count_total"),
        )
        or 0
    )
    load_combination_engine_family_count = int(
        _first_int(
            load_combination_engine_summary.get("family_count"),
            len(load_combination_combo_family_counts) if load_combination_combo_family_counts else None,
            len(load_combination_case_family_counts) if load_combination_case_family_counts else None,
        )
        or 0
    )
    load_combination_engine_max_nested_depth = int(
        _first_int(
            load_combination_engine_summary.get("runtime_max_nested_depth_global"),
            load_combination_engine_summary.get("max_nested_depth"),
        )
        or 0
    )
    load_combination_editor_commercialization_summary = (
        load_combination_editor_commercialization_report.get("summary")
        if isinstance(load_combination_editor_commercialization_report.get("summary"), dict)
        else {}
    )
    load_combination_editor_commercialization_summary_line = str(
        load_combination_editor_commercialization_report.get("summary_line", "") or ""
    ).strip()
    load_combination_editor_commercialization_pass = _pass(load_combination_editor_commercialization_report)
    load_combination_editor_required_target_match_label = str(
        load_combination_editor_commercialization_summary.get("required_target_match_label", "") or ""
    ).strip()
    load_combination_editor_code_check_assembly_ready = bool(
        load_combination_editor_commercialization_summary.get("code_check_assembly_ready", False)
    )
    reference_regression_summary_line = str(reference_regression_report.get("summary_line", "") or "").strip()
    reference_regression_summary = (
        reference_regression_report.get("summary")
        if isinstance(reference_regression_report.get("summary"), dict)
        else {}
    )
    reference_regression_pass = _pass(reference_regression_report)
    reference_regression_case_count = int(_first_int(reference_regression_summary.get("case_count")) or 0)
    reference_regression_passing_case_count = int(
        _first_int(reference_regression_summary.get("passing_case_count")) or 0
    )
    reference_regression_metric_count = int(_first_int(reference_regression_summary.get("metric_count")) or 0)
    reference_regression_passing_metric_count = int(
        _first_int(reference_regression_summary.get("passing_metric_count")) or 0
    )
    advanced_ssi_surface = _extract_gate_surface_with_report(
        {"advanced_ssi_report": advanced_ssi_report},
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="advanced_ssi",
        direct_report=advanced_ssi_report,
    )
    wind_workflow_surface = _extract_gate_surface_with_report(
        {"wind_workflow_report": wind_workflow_report},
        ci,
        committee_summary,
        committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {},
        stem="wind_workflow",
        direct_report=wind_workflow_report,
    )
    advanced_ssi_summary_line = str(advanced_ssi_surface.get("summary_line", "") or "").strip()
    advanced_ssi_pass = advanced_ssi_surface.get("pass")
    advanced_ssi_summary = advanced_ssi_surface["summary"]
    advanced_ssi_peak_transfer_ratio_max = float(
        advanced_ssi_summary.get("peak_transfer_ratio_max", 0.0) or 0.0
    )
    advanced_ssi_peak_transfer_group_id = str(advanced_ssi_summary.get("peak_transfer_group_id", "") or "")
    advanced_ssi_group_efficiency_ratio = float(
        advanced_ssi_summary.get("min_group_interaction_efficiency_ratio", 0.0) or 0.0
    )
    wind_workflow_summary_line = str(wind_workflow_surface.get("summary_line", "") or "").strip()
    wind_workflow_pass = wind_workflow_surface.get("pass")
    wind_workflow_summary = wind_workflow_surface["summary"]
    wind_workflow_comfort_class = str(
        wind_workflow_summary.get("occupant_comfort_class", "") or ""
    )
    wind_workflow_crosswind_bias_ratio = float(
        wind_workflow_summary.get("occupant_comfort_crosswind_bias_ratio", 0.0) or 0.0
    )
    performance_profiling_summary_line = str(ci.get("performance_profiling_summary_line", "") or "").strip()
    performance_profiling_detail_line = (
        "moving_load_scale="
        f"{_finite(performance_profiling_summary.get('moving_load_integrator_elapsed_seconds')):.3f}/"
        f"{_finite(performance_profiling_summary.get('moving_load_large_elapsed_seconds')):.3f}/"
        f"{_finite(performance_profiling_summary.get('moving_load_xlarge_elapsed_seconds')):.3f}s"
        f" | cached_inverse={bool(performance_profiling_summary.get('moving_load_large_cached_track_solve_inverse_enabled', False))}/"
        f"{bool(performance_profiling_summary.get('moving_load_xlarge_cached_track_solve_inverse_enabled', False))}"
        f" | ssi_variant_sweep={int(performance_profiling_summary.get('ssi_variant_sweep_pass_count', 0) or 0)}/"
        f"{int(performance_profiling_summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"
        f" zero_gap={int(performance_profiling_summary.get('ssi_variant_sweep_zero_gap_positive_count', 0) or 0)}/"
        f"{int(performance_profiling_summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"
        f" pruned={int(performance_profiling_summary.get('ssi_variant_sweep_track_static_pruned_positive_count', 0) or 0)}/"
        f"{int(performance_profiling_summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"
    ).strip()
    solver_truthfulness_summary_line = str(
        solver_truthfulness.get("summary_line", ci.get("solver_truthfulness_summary_line", "") or "")
    ).strip()
    hardest_external_10case_kickoff_summary_line = str(
        hardest_external_10case_kickoff.get(
            "summary_line",
            ci.get("hardest_external_10case_kickoff_summary_line", "") or "",
        )
    ).strip()
    nonlinear_generalization_summary_line = str(ci.get("nonlinear_generalization_summary_line", "") or "").strip()
    workflow_productization_summary_line = str(ci.get("workflow_productization_summary_line", "") or "").strip()
    workflow_contact_coupling_surface = _extract_workflow_contact_coupling_surface(
        workflow_productization_summary,
        workflow_productization_report,
        ci,
    )
    workflow_contact_coupling_summary_line = str(
        workflow_contact_coupling_surface.get("summary_line", "") or ""
    ).strip()
    workflow_contact_coupling_summary = {
        "summary_label": str(workflow_contact_coupling_surface.get("detail_label", "") or "").strip(),
        "pass": bool(workflow_contact_coupling_surface.get("pass", False)),
        "support_family_count": int(workflow_contact_coupling_surface.get("support_family_count", 0) or 0),
        "proxy_family_count": int(workflow_contact_coupling_surface.get("proxy_family_count", 0) or 0),
        "assembled_depth_value": int(workflow_contact_coupling_surface.get("assembled_depth_value", 0) or 0),
    }
    general_fe_contact_matrix_summary = {
        "summary_label": _compact_general_fe_contact_matrix_summary_label(general_fe_contact_matrix_summary_line),
        "pass": bool(support_search_surface.get("pass", False)),
        "support_search_count": int(support_search_surface.get("support_search_count", 0) or 0),
        "node_surface_proxy_count": int(support_search_surface.get("node_surface_proxy_count", 0) or 0),
        "support_depth_score": int(support_search_surface.get("support_depth_score", 0) or 0),
    }
    korean_source_ingest_summary_line = str(
        workflow_productization_summary.get("korean_source_ingest_summary_line", "")
        or ci.get("korean_source_ingest_summary_line", "")
        or ""
    ).strip()
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(korean_source_ingest_summary_line)
    korean_structural_preview_queue_summary_line = str(
        workflow_productization_summary.get("korean_structural_preview_queue_summary_line", "")
        or ci.get("korean_structural_preview_queue_summary_line", "")
        or ""
    ).strip()
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    opensees_canonical_breadth_path = Path(
        "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"
    )
    opensees_canonical_breadth = (
        _load_json(opensees_canonical_breadth_path) if opensees_canonical_breadth_path.exists() else {}
    )
    opensees_canonical_breadth_summary = (
        opensees_canonical_breadth.get("summary")
        if isinstance(opensees_canonical_breadth.get("summary"), dict)
        else {}
    )
    opensees_canonical_breadth_summary_line = str(
        opensees_canonical_breadth.get("summary_line", "") or ""
    ).strip()
    measured_benchmark_breadth_path = Path(
        "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json"
    )
    measured_benchmark_breadth = (
        _load_json(measured_benchmark_breadth_path) if measured_benchmark_breadth_path.exists() else {}
    )
    measured_benchmark_breadth_summary = (
        measured_benchmark_breadth.get("summary")
        if isinstance(measured_benchmark_breadth.get("summary"), dict)
        else {}
    )
    measured_benchmark_breadth_summary_line = str(
        measured_benchmark_breadth.get("summary_line", "") or ci.get("measured_benchmark_breadth_summary_line", "") or ""
    ).strip()
    commercial_workflow_breadth_path = DEFAULT_COMMERCIAL_WORKFLOW_BREADTH_REPORT
    commercial_workflow_breadth = (
        _load_json(commercial_workflow_breadth_path)
        if commercial_workflow_breadth_path.exists()
        else {}
    )
    commercial_workflow_breadth_surface = _commercial_workflow_breadth_surface(
        commercial_workflow_breadth,
        commercial_workflow_breadth_path,
    )
    peer_blind_prediction_compare_report_path = Path(
        "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json"
    )
    peer_blind_prediction_compare_report = (
        _load_json(peer_blind_prediction_compare_report_path)
        if peer_blind_prediction_compare_report_path.exists()
        else {}
    )
    peer_blind_prediction_compare_surface = _peer_blind_prediction_compare_surface(
        peer_blind_prediction_compare_report
    )
    peer_blind_prediction_measured_response_landing_manifest_path = Path(
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
    )
    peer_blind_prediction_measured_response_landing_manifest = (
        _load_json(peer_blind_prediction_measured_response_landing_manifest_path)
        if peer_blind_prediction_measured_response_landing_manifest_path.exists()
        else {}
    )
    if not peer_blind_prediction_measured_response_landing_manifest:
        fallback_peer_landing_status_path = Path(
            "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json"
        )
        if fallback_peer_landing_status_path.exists():
            peer_blind_prediction_measured_response_landing_manifest = _load_json(
                fallback_peer_landing_status_path
            )
    peer_blind_prediction_measured_response_landing_surface = (
        _peer_blind_prediction_measured_response_landing_surface(
            peer_blind_prediction_measured_response_landing_manifest
        )
    )
    irregular_structure_summary_line = str(
        workflow_productization_summary.get("irregular_structure_track_summary_line", "")
        or workflow_productization_summary.get("irregular_structure_summary_line", "")
        or ""
    ).strip()
    irregular_structure_summary = workflow_productization_summary
    irregular_structure_artifacts = (
        workflow_productization_report.get("generated_artifacts")
        if isinstance(workflow_productization_report.get("generated_artifacts"), dict)
        else {}
    )
    commercial_readiness_summary_line = str(ci.get("commercial_readiness_summary_line", "") or "").strip()

    comm_metrics = commercial.get("global_metrics") if isinstance(commercial.get("global_metrics"), dict) else {}
    comm_grade = commercial.get("grade") if isinstance(commercial.get("grade"), dict) else {}
    comm_inputs = commercial.get("inputs") if isinstance(commercial.get("inputs"), dict) else {}
    if not commercial_readiness_summary_line:
        commercial_readiness_summary_line = (
            "Commercial readiness: "
            f"{str(commercial.get('reason_code', 'UNKNOWN'))} | "
            f"grade={str(comm_grade.get('label', 'unknown'))} | "
            f"strict_measured={bool(comm_inputs.get('require_measured_dynamic_targets', False))} | "
            f"families={int(comm_metrics.get('source_family_count', 0) or 0)} | "
            f"measured_families={int(comm_metrics.get('measured_source_family_count', 0) or 0)} | "
            f"measured_cases={int(comm_metrics.get('measured_case_count', 0) or 0)} | "
            f"shell_beam_mix={int(comm_metrics.get('shell_beam_mix_case_count', 0) or 0)}"
        )
    deployment_model = commercial.get("deployment_model") if isinstance(commercial.get("deployment_model"), dict) else {}
    residual_holdout_categories = commercial.get("residual_holdout_categories") if isinstance(commercial.get("residual_holdout_categories"), list) else []
    authority_summary = authority.get("summary") if isinstance(authority.get("summary"), dict) else {}
    hip_backend = hip.get("backend") if isinstance(hip.get("backend"), dict) else {}
    hip_checks = hip.get("checks") if isinstance(hip.get("checks"), dict) else {}
    midas_diag = midas.get("parser_diagnostics") if isinstance(midas.get("parser_diagnostics"), dict) else {}
    midas_metrics = midas.get("metrics") if isinstance(midas.get("metrics"), dict) else {}
    construction_summary = construction.get("summary") if isinstance(construction.get("summary"), dict) else {}
    diaphragm_summary = diaphragm.get("summary") if isinstance(diaphragm.get("summary"), dict) else {}
    repro_summary = repro.get("summary") if isinstance(repro.get("summary"), dict) else {}
    release_registry_checks = release_registry.get("checks") if isinstance(release_registry.get("checks"), dict) else {}
    release_registry_summary = release_registry.get("summary") if isinstance(release_registry.get("summary"), dict) else {}
    release_registry_signature = release_registry.get("signature") if isinstance(release_registry.get("signature"), dict) else {}
    release_registry_artifacts = (
        release_registry.get("artifacts") if isinstance(release_registry.get("artifacts"), dict) else {}
    )
    kds_frontend = kds.get("frontend_payload") if isinstance(kds.get("frontend_payload"), dict) else {}
    kds_summary = kds.get("summary") if isinstance(kds.get("summary"), dict) else {}
    solver_hip_checks = solver_hip.get("checks") if isinstance(solver_hip.get("checks"), dict) else {}
    solver_hip_summary = solver_hip.get("summary") if isinstance(solver_hip.get("summary"), dict) else {}
    rc_summary = rc_benchmark.get("summary") if isinstance(rc_benchmark.get("summary"), dict) else {}
    quality_summary = quality_mgt_corpus.get("summary") if isinstance(quality_mgt_corpus.get("summary"), dict) else {}
    quality_catalog_meta = quality_mgt_corpus.get("catalog_meta") if isinstance(quality_mgt_corpus.get("catalog_meta"), dict) else {}
    pbd_summary = pbd_package.get("summary") if isinstance(pbd_package.get("summary"), dict) else {}
    pbd_artifacts = pbd_package.get("artifacts") if isinstance(pbd_package.get("artifacts"), dict) else {}
    design_opt_dataset_summary = design_opt_dataset.get("summary") if isinstance(design_opt_dataset.get("summary"), dict) else {}
    committee_metrics = committee_summary.get("metrics") if isinstance(committee_summary.get("metrics"), dict) else {}
    committee_external_benchmark_submission_queue_rows = [
        row
        for row in (committee_summary.get("external_benchmark_submission_queue_rows") or [])
        if isinstance(row, dict)
    ]
    committee_external_benchmark_submission_queue_count = int(
        committee_summary.get(
            "external_benchmark_submission_queue_count",
            len(committee_external_benchmark_submission_queue_rows),
        )
        or len(committee_external_benchmark_submission_queue_rows)
    )
    committee_external_benchmark_submission_queue_ready_count = int(
        committee_summary.get(
            "external_benchmark_submission_queue_ready_count",
            sum(
                1
                for row in committee_external_benchmark_submission_queue_rows
                if str(row.get("status", "") or "") == "ready_for_full_submission"
            ),
        )
        or sum(
            1
            for row in committee_external_benchmark_submission_queue_rows
            if str(row.get("status", "") or "") == "ready_for_full_submission"
        )
    )
    committee_external_benchmark_submission_queue_review_pending_count = int(
        committee_summary.get(
            "external_benchmark_submission_queue_review_pending_count",
            sum(
                1
                for row in committee_external_benchmark_submission_queue_rows
                if str(row.get("status", "") or "") == "ready_for_benchmark_start_final_review_pending"
            ),
        )
        or sum(
            1
            for row in committee_external_benchmark_submission_queue_rows
            if str(row.get("status", "") or "") == "ready_for_benchmark_start_final_review_pending"
        )
    )
    committee_external_benchmark_submission_queue_blocked_count = int(
        committee_summary.get(
            "external_benchmark_submission_queue_blocked_count",
            sum(1 for row in committee_external_benchmark_submission_queue_rows if str(row.get("status", "") or "") == "blocked"),
        )
        or sum(1 for row in committee_external_benchmark_submission_queue_rows if str(row.get("status", "") or "") == "blocked")
    )
    committee_external_benchmark_submission_onepage_attestation_status = str(
        committee_summary.get("external_benchmark_submission_onepage_attestation_status", "")
        or committee_metrics.get("external_benchmark_submission_onepage_attestation_status", "")
        or (
            "ready_for_full_submission"
            if committee_external_benchmark_submission_queue_count
            and committee_external_benchmark_submission_queue_ready_count
            == committee_external_benchmark_submission_queue_count
            else "draft_ready_final_review_pending"
            if committee_external_benchmark_submission_queue_count
            and committee_external_benchmark_submission_queue_review_pending_count
            == committee_external_benchmark_submission_queue_count
            else "blocked"
            if committee_external_benchmark_submission_queue_count
            else ""
        )
    )
    committee_external_benchmark_submission_recommended_start_mode = str(
        committee_summary.get("external_benchmark_submission_recommended_start_mode", "")
        or committee_metrics.get("external_benchmark_submission_recommended_start_mode", "")
        or ""
    )
    committee_external_benchmark_submission_recommended_submission_scope = str(
        committee_summary.get("external_benchmark_submission_recommended_submission_scope", "")
        or committee_metrics.get("external_benchmark_submission_recommended_submission_scope", "")
        or ""
    )
    committee_external_benchmark_submission_blocker_label = str(
        committee_summary.get("external_benchmark_submission_blocker_label", "")
        or committee_metrics.get("external_benchmark_submission_blocker_label", "")
        or "none"
    )
    committee_external_benchmark_submission_caution_label = str(
        committee_summary.get("external_benchmark_submission_caution_label", "")
        or committee_metrics.get("external_benchmark_submission_caution_label", "")
        or "none"
    )
    committee_external_benchmark_submission_summary_line = (
        "External benchmark submission queue: "
        f"queue={committee_external_benchmark_submission_queue_count} | "
        f"ready={committee_external_benchmark_submission_queue_ready_count} | "
        f"review_pending={committee_external_benchmark_submission_queue_review_pending_count} | "
        f"blocked={committee_external_benchmark_submission_queue_blocked_count} | "
        f"onepage_attestation_status={committee_external_benchmark_submission_onepage_attestation_status or 'unknown'}"
    )
    if committee_external_benchmark_submission_recommended_start_mode or committee_external_benchmark_submission_recommended_submission_scope:
        committee_external_benchmark_submission_summary_line += (
            f" | start_mode={committee_external_benchmark_submission_recommended_start_mode or 'n/a'}"
            f" | submission_scope={committee_external_benchmark_submission_recommended_submission_scope or 'n/a'}"
        )
    if committee_external_benchmark_submission_blocker_label or committee_external_benchmark_submission_caution_label:
        committee_external_benchmark_submission_summary_line += (
            f" | blocker={committee_external_benchmark_submission_blocker_label or 'none'}"
            f" | caution={committee_external_benchmark_submission_caution_label or 'none'}"
        )
    committee_artifact_links = (
        committee_summary.get("artifact_links")
        if isinstance(committee_summary.get("artifact_links"), dict)
        else committee_summary.get("artifacts")
        if isinstance(committee_summary.get("artifacts"), dict)
        else committee_summary.get("artifact_links")
        if isinstance(committee_summary.get("artifact_links"), dict)
        else {}
    )
    native_authoring_lane_surface = _native_authoring_lane_surface(
        native_authoring_solver_session,
        native_authoring_ops_bundle,
        workspace_summary_report=native_authoring_workspace_summary,
        portfolio_report=native_authoring_portfolio,
        family_corpus_manifest_report=native_authoring_family_corpus_manifest,
        family_local_evidence_manifest_report=native_authoring_family_local_evidence_manifest,
        family_tracks_report=native_authoring_family_tracks,
        runtime_submission_report=native_authoring_runtime_submission,
        runtime_writeback_depth_report=native_authoring_runtime_writeback_depth,
        local_runtime_scenario_depth_report=native_authoring_local_runtime_scenario_depth,
        local_variant_writeback_trace_report=native_authoring_local_variant_writeback_trace,
        multi_project_runtime_writeback_report=native_authoring_multi_project_runtime_writeback,
        solver_family_breadth_report=native_authoring_solver_family_breadth,
        writeback_breadth_report=native_authoring_writeback_breadth,
        project_ops_service_snapshot_report=project_ops_service_snapshot,
        solver_session_path=native_authoring_solver_session_path,
        ops_bundle_path=native_authoring_ops_bundle_path,
        workspace_summary_path=native_authoring_workspace_summary_path,
        portfolio_path=native_authoring_portfolio_path,
        family_corpus_manifest_path=native_authoring_family_corpus_manifest_path,
        family_local_evidence_manifest_path=native_authoring_family_local_evidence_manifest_path,
        family_tracks_path=native_authoring_family_tracks_path,
        runtime_submission_path=native_authoring_runtime_submission_path,
        runtime_writeback_depth_path=native_authoring_runtime_writeback_depth_path,
        local_runtime_scenario_depth_path=native_authoring_local_runtime_scenario_depth_path,
        local_variant_writeback_trace_path=native_authoring_local_variant_writeback_trace_path,
        multi_project_runtime_writeback_path=native_authoring_multi_project_runtime_writeback_path,
        solver_family_breadth_path=native_authoring_solver_family_breadth_path,
        writeback_breadth_path=native_authoring_writeback_breadth_path,
        project_ops_service_snapshot_path=project_ops_service_snapshot_path,
    )
    native_authoring_artifacts = (
        native_authoring_lane_surface.get("artifacts")
        if isinstance(native_authoring_lane_surface.get("artifacts"), dict)
        else {}
    )
    native_authoring_release_surface = {
        key: value for key, value in native_authoring_lane_surface.items() if key != "artifacts"
    }
    external_benchmark_batch_job_summary_line = str(
        committee_metrics.get("external_benchmark_batch_job_summary_line", "") or ""
    )
    external_benchmark_batch_job_contract_pass = bool(
        committee_metrics.get("external_benchmark_batch_job_contract_pass", False)
    )
    external_benchmark_batch_job_count = int(
        committee_metrics.get("external_benchmark_batch_job_count", 0) or 0
    )
    external_benchmark_batch_completed_count = int(
        committee_metrics.get("external_benchmark_batch_completed_count", 0) or 0
    )
    external_benchmark_batch_failed_count = int(
        committee_metrics.get("external_benchmark_batch_failed_count", 0) or 0
    )
    external_benchmark_batch_rerun_count = int(
        committee_metrics.get("external_benchmark_batch_rerun_count", 0) or 0
    )
    midas_kds_row_provenance_preview_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_preview_rows")
            or committee_metrics.get("midas_kds_row_provenance_preview_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_clause_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_clause_filter_rows")
            or committee_metrics.get("midas_kds_row_provenance_clause_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_member_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_member_filter_rows")
            or committee_metrics.get("midas_kds_row_provenance_member_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_hazard_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_hazard_filter_rows")
            or committee_metrics.get("midas_kds_row_provenance_hazard_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_rule_family_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_rule_family_filter_rows")
            or committee_metrics.get("midas_kds_row_provenance_rule_family_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_export_row_count = int(
        _first_int(
            committee_summary.get("midas_kds_row_provenance_export_row_count"),
            committee_metrics.get("midas_kds_row_provenance_export_row_count"),
        )
        or 0
    )
    midas_kds_row_provenance_export_exact_row_count = int(
        _first_int(
            committee_summary.get("midas_kds_row_provenance_export_exact_row_count"),
            committee_metrics.get("midas_kds_row_provenance_export_exact_row_count"),
        )
        or 0
    )
    if midas_kds_row_provenance_export_row_count == 0:
        midas_kds_row_provenance_export_row_count = midas_kds_row_provenance_export_exact_row_count
    midas_kds_row_provenance_preview_row_count = len(midas_kds_row_provenance_preview_rows)
    midas_kds_row_provenance_preview_rows_present = midas_kds_row_provenance_preview_row_count > 0
    midas_kds_row_provenance_exact_row_coverage_label = (
        f"{midas_kds_row_provenance_export_exact_row_count}/{midas_kds_row_provenance_export_row_count}"
        if midas_kds_row_provenance_export_row_count
        else "0/0"
    )
    nightly_smoke = nightly.get("design_optimization_cost_reduction_smoke") if isinstance(nightly.get("design_optimization_cost_reduction_smoke"), dict) else {}
    nightly_smoke_summary = nightly_smoke.get("summary") if isinstance(nightly_smoke.get("summary"), dict) else {}
    nightly_smoke_history = nightly.get("design_optimization_cost_reduction_smoke_history") if isinstance(nightly.get("design_optimization_cost_reduction_smoke_history"), dict) else {}
    nightly_smoke_history_summary = nightly_smoke_history.get("summary") if isinstance(nightly_smoke_history.get("summary"), dict) else {}
    nightly_smoke_recommendation = nightly.get("design_optimization_cost_reduction_smoke_strict_recommendation") if isinstance(nightly.get("design_optimization_cost_reduction_smoke_strict_recommendation"), dict) else {}
    midas_unknown_rows = int(midas_diag.get("unknown_row_total", 0))
    midas_skipped_rows = int(midas_metrics.get("element_rows_skipped", 0))
    midas_use_stld_block_count = int(midas_metrics.get("use_stld_block_count", 0) or 0)
    midas_semantic_load_case_count = int(midas_metrics.get("semantic_load_case_count", 0) or 0)
    midas_semantic_load_combination_count = int(midas_metrics.get("semantic_load_combination_count", 0) or 0)
    midas_bound_nodal_load_row_count = int(midas_metrics.get("bound_nodal_load_row_count", 0) or 0)
    midas_bound_selfweight_row_count = int(midas_metrics.get("bound_selfweight_row_count", 0) or 0)
    midas_bound_pressure_row_count = int(midas_metrics.get("bound_pressure_row_count", 0) or 0)
    midas_unbound_nodal_load_row_count = int(midas_metrics.get("unbound_nodal_load_row_count", 0) or 0)
    midas_unbound_selfweight_row_count = int(midas_metrics.get("unbound_selfweight_row_count", 0) or 0)
    midas_unbound_pressure_row_count = int(midas_metrics.get("unbound_pressure_row_count", 0) or 0)
    midas_semantic_load_binding_pass = bool(
        _pass(midas)
        and midas_semantic_load_case_count > 0
        and midas_use_stld_block_count > 0
        and midas_unbound_nodal_load_row_count == 0
        and midas_unbound_selfweight_row_count == 0
        and midas_unbound_pressure_row_count == 0
    )
    mgt_export_patch_path = Path(args.mgt_export_output_mgt)
    mgt_export_report_path = Path(args.mgt_export_report)
    mgt_export_queue_manifest_path = Path(args.mgt_export_audit_review_queue_manifest)
    mgt_export_followup_manifest_path = Path(args.mgt_export_audit_review_followup_manifest)
    mgt_export_report = _load_json(mgt_export_report_path) if mgt_export_report_path.exists() else {}
    mgt_export_summary = mgt_export_report.get("summary") if isinstance(mgt_export_report.get("summary"), dict) else {}
    mgt_export_queue_manifest = (
        _load_json(mgt_export_queue_manifest_path) if mgt_export_queue_manifest_path.exists() else {}
    )
    mgt_export_followup_manifest = (
        _load_json(mgt_export_followup_manifest_path) if mgt_export_followup_manifest_path.exists() else {}
    )
    mgt_export_queue_summary = (
        mgt_export_queue_manifest.get("summary")
        if isinstance(mgt_export_queue_manifest.get("summary"), dict)
        else {}
    )
    mgt_export_followup_summary = (
        mgt_export_followup_manifest.get("summary")
        if isinstance(mgt_export_followup_manifest.get("summary"), dict)
        else {}
    )
    mgt_export_queue_metrics = (
        mgt_export_queue_summary if mgt_export_queue_summary else mgt_export_summary
    )
    mgt_export_followup_metrics = (
        mgt_export_followup_summary if mgt_export_followup_summary else mgt_export_summary
    )
    mgt_export_artifact_exists = bool(mgt_export_patch_path.exists())
    mgt_export_contract_pass = bool(mgt_export_report.get("contract_pass", False))
    mgt_export_support_mode = str(mgt_export_summary.get("support_mode", "missing"))
    mgt_export_loadcomb_preview_exists = bool(mgt_export_summary.get("loadcomb_preview_exists", False))
    mgt_export_loadcomb_roundtrip_report_exists = bool(mgt_export_summary.get("loadcomb_roundtrip_report_exists", False))
    mgt_export_loadcomb_roundtrip_pass = bool(mgt_export_summary.get("loadcomb_roundtrip_pass", False))
    mgt_export_loadcomb_roundtrip_summary_line = str(mgt_export_summary.get("loadcomb_roundtrip_summary_line", "") or "")
    mgt_export_loadcomb_roundtrip_recovery_mode = str(mgt_export_summary.get("loadcomb_roundtrip_recovery_mode", "") or "")
    mgt_export_loadcomb_combo_count = int(mgt_export_summary.get("loadcomb_combo_count", 0) or 0)
    mgt_export_supported_change_count = int(mgt_export_summary.get("supported_change_count", 0) or 0)
    mgt_export_unsupported_change_count = int(mgt_export_summary.get("unsupported_change_count", 0) or 0)
    mgt_export_direct_patch_change_count = int(mgt_export_summary.get("direct_patch_change_count", 0) or 0)
    mgt_export_direct_patch_supported_action_families = [
        str(v) for v in (mgt_export_summary.get("direct_patch_supported_action_families") or [])
    ]
    mgt_export_sidecar_supported_action_families = [
        str(v) for v in (mgt_export_summary.get("sidecar_supported_action_families") or [])
    ]
    mgt_export_direct_patch_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("direct_patch_action_family_counts") or {}).items())
    }
    mgt_export_direct_patch_action_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(mgt_export_direct_patch_action_family_counts.items())
    )
    mgt_export_special_member_supported_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("special_member_supported_action_family_counts") or {}).items())
    }
    mgt_export_special_member_direct_patch_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("special_member_direct_patch_action_family_counts") or {}).items())
    }
    mgt_export_special_member_zero_touch_verified_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            (mgt_export_summary.get("special_member_instruction_sidecar_zero_touch_verified_action_family_counts") or {}).items()
        )
    }
    mgt_export_special_member_supported_action_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(mgt_export_special_member_supported_action_family_counts.items())
    )
    mgt_export_special_member_direct_patch_action_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(mgt_export_special_member_direct_patch_action_family_counts.items())
    )
    mgt_export_special_member_zero_touch_verified_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_special_member_zero_touch_verified_action_family_counts.items())
    )
    mgt_export_material_level_rebar_payload_row_count = int(
        mgt_export_summary.get("material_level_rebar_payload_row_count", 0) or 0
    )
    mgt_export_material_level_rebar_payload_available_count = int(
        mgt_export_summary.get("material_level_rebar_payload_available_count", 0) or 0
    )
    mgt_export_group_local_rebar_payload_row_count = int(
        mgt_export_summary.get("group_local_rebar_payload_row_count", 0) or 0
    )
    mgt_export_group_local_rebar_payload_available_count = int(
        mgt_export_summary.get("group_local_rebar_payload_available_count", 0) or 0
    )
    mgt_export_group_local_connection_detailing_payload_row_count = int(
        mgt_export_summary.get("group_local_connection_detailing_payload_row_count", 0) or 0
    )
    mgt_export_group_local_connection_detailing_payload_available_count = int(
        mgt_export_summary.get("group_local_connection_detailing_payload_available_count", 0) or 0
    )
    mgt_export_group_local_detailing_payload_row_count = int(
        mgt_export_summary.get("group_local_detailing_payload_row_count", 0) or 0
    )
    mgt_export_group_local_detailing_payload_available_count = int(
        mgt_export_summary.get("group_local_detailing_payload_available_count", 0) or 0
    )
    mgt_export_connection_detailing_payload_namespace_mode = str(
        mgt_export_summary.get("connection_detailing_payload_namespace_mode", "none")
    )
    mgt_export_connection_detailing_payload_group_local_namespace_present = bool(
        mgt_export_summary.get("connection_detailing_payload_group_local_namespace_present", False)
    )
    mgt_export_connection_detailing_structured_payload_mapped_change_count = int(
        mgt_export_summary.get("connection_detailing_structured_payload_mapped_change_count", 0) or 0
    )
    mgt_export_connection_detailing_direct_patch_eligible_change_count = int(
        mgt_export_summary.get("connection_detailing_direct_patch_eligible_change_count", 0) or 0
    )
    mgt_export_connection_detailing_delivery_mode = str(
        mgt_export_summary.get("connection_detailing_delivery_mode", "")
    )
    mgt_export_detailing_payload_namespace_mode = str(
        mgt_export_summary.get("detailing_payload_namespace_mode", "none")
    )
    mgt_export_detailing_payload_group_local_namespace_present = bool(
        mgt_export_summary.get("detailing_payload_group_local_namespace_present", False)
    )
    mgt_export_detailing_structured_payload_mapped_change_count = int(
        mgt_export_summary.get("detailing_structured_payload_mapped_change_count", 0) or 0
    )
    mgt_export_detailing_direct_patch_eligible_change_count = int(
        mgt_export_summary.get("detailing_direct_patch_eligible_change_count", 0) or 0
    )
    mgt_export_detailing_delivery_mode = str(mgt_export_summary.get("detailing_delivery_mode", ""))
    mgt_export_rebar_payload_namespace_mode = str(
        mgt_export_summary.get("rebar_payload_namespace_mode", "none")
    )
    mgt_export_rebar_payload_material_level_namespace_present = bool(
        mgt_export_summary.get("rebar_payload_material_level_namespace_present", False)
    )
    mgt_export_rebar_payload_group_local_namespace_present = bool(
        mgt_export_summary.get("rebar_payload_group_local_namespace_present", False)
    )
    mgt_export_rebar_direct_patch_eligible_change_count = int(
        mgt_export_summary.get("rebar_direct_patch_eligible_change_count", 0) or 0
    )
    mgt_export_rebar_direct_patch_ineligible_reason_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("rebar_direct_patch_ineligible_reason_counts") or {}).items())
    }
    mgt_export_rebar_direct_patch_ineligible_reason_label = ", ".join(
        f"{reason}={count}" for reason, count in sorted(mgt_export_rebar_direct_patch_ineligible_reason_counts.items())
    )
    mgt_export_rebar_direct_patch_mapping_source_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("rebar_direct_patch_mapping_source_counts") or {}).items())
    }
    mgt_export_rebar_direct_patch_mapping_source_label = ", ".join(
        f"{source}={count}" for source, count in sorted(mgt_export_rebar_direct_patch_mapping_source_counts.items())
    )
    mgt_export_patched_section_scale_row_count = int(mgt_export_summary.get("patched_section_scale_row_count", 0) or 0)
    mgt_export_patched_thickness_row_count = int(mgt_export_summary.get("patched_thickness_row_count", 0) or 0)
    mgt_export_patched_material_row_count = int(mgt_export_summary.get("patched_material_row_count", 0) or 0)
    mgt_export_instruction_sidecar_change_count = int(mgt_export_summary.get("instruction_sidecar_change_count", 0) or 0)
    mgt_export_instruction_sidecar_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("instruction_sidecar_action_family_counts") or {}).items())
    }
    mgt_export_instruction_sidecar_action_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(mgt_export_instruction_sidecar_action_family_counts.items())
    )
    mgt_export_instruction_sidecar_review_priority_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("instruction_sidecar_review_priority_counts") or {}).items())
    }
    mgt_export_instruction_sidecar_review_priority_label = ", ".join(
        f"{priority}={count}" for priority, count in sorted(mgt_export_instruction_sidecar_review_priority_counts.items())
    )
    mgt_export_instruction_sidecar_followup_type_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("instruction_sidecar_followup_type_counts") or {}).items())
    }
    mgt_export_instruction_sidecar_followup_type_label = ", ".join(
        f"{followup_type}={count}" for followup_type, count in sorted(mgt_export_instruction_sidecar_followup_type_counts.items())
    )
    mgt_export_instruction_sidecar_audit_only_change_count = int(
        mgt_export_summary.get("instruction_sidecar_audit_only_change_count", 0) or 0
    )
    mgt_export_instruction_sidecar_audit_only_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("instruction_sidecar_audit_only_action_family_counts") or {}).items())
    }
    mgt_export_instruction_sidecar_audit_only_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_instruction_sidecar_audit_only_action_family_counts.items())
    )
    mgt_export_instruction_sidecar_manual_input_change_count = int(
        mgt_export_summary.get("instruction_sidecar_manual_input_change_count", 0) or 0
    )
    mgt_export_instruction_sidecar_manual_input_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("instruction_sidecar_manual_input_action_family_counts") or {}).items())
    }
    mgt_export_instruction_sidecar_manual_input_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_instruction_sidecar_manual_input_action_family_counts.items())
    )
    mgt_export_audit_review_manifest_change_count = int(
        mgt_export_summary.get("audit_review_manifest_change_count", 0) or 0
    )
    mgt_export_audit_review_manifest_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_manifest_action_family_counts") or {}).items())
    }
    mgt_export_audit_review_manifest_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_audit_review_manifest_action_family_counts.items())
    )
    mgt_export_audit_review_packet_count = int(
        mgt_export_summary.get("audit_review_packet_count", 0) or 0
    )
    mgt_export_audit_review_packet_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_packet_action_family_counts") or {}).items())
    }
    mgt_export_audit_review_packet_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_audit_review_packet_action_family_counts.items())
    )
    mgt_export_audit_review_packet_followup_type_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_packet_followup_type_counts") or {}).items())
    }
    mgt_export_audit_review_packet_followup_type_label = ", ".join(
        f"{followup}={count}"
        for followup, count in sorted(mgt_export_audit_review_packet_followup_type_counts.items())
    )
    mgt_export_audit_review_packet_file_count = int(
        mgt_export_summary.get("audit_review_packet_file_count", 0) or 0
    )
    mgt_export_audit_review_packet_file_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_packet_file_action_family_counts") or {}).items())
    }
    mgt_export_audit_review_packet_file_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_audit_review_packet_file_action_family_counts.items())
    )
    mgt_export_audit_review_queue_item_count = int(
        mgt_export_queue_metrics.get("audit_review_queue_item_count", 0) or 0
    )
    mgt_export_audit_review_queue_pending_count = int(
        mgt_export_queue_metrics.get("audit_review_queue_pending_count", 0) or 0
    )
    mgt_export_audit_review_queue_acknowledged_count = int(
        mgt_export_queue_metrics.get("audit_review_queue_acknowledged_count", 0) or 0
    )
    mgt_export_audit_review_queue_status_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_queue_metrics.get("audit_review_queue_status_counts") or {}).items())
    }
    mgt_export_audit_review_queue_status_label = ", ".join(
        f"{status}={count}"
        for status, count in sorted(mgt_export_audit_review_queue_status_counts.items())
    )
    mgt_export_audit_review_queue_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_queue_metrics.get("audit_review_queue_action_family_counts") or {}).items())
    }
    mgt_export_audit_review_queue_action_family_label = ", ".join(
        f"{family}={count}"
        for family, count in sorted(mgt_export_audit_review_queue_action_family_counts.items())
    )
    mgt_export_audit_review_followup_item_count = int(
        mgt_export_followup_metrics.get("audit_review_followup_item_count", 0) or 0
    )
    mgt_export_audit_review_followup_open_item_count = int(
        mgt_export_followup_metrics.get("audit_review_followup_open_item_count", 0) or 0
    )
    mgt_export_audit_review_followup_closed_item_count = int(
        mgt_export_followup_metrics.get("audit_review_followup_closed_item_count", 0) or 0
    )
    mgt_export_audit_review_followup_action_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_followup_metrics.get("audit_review_followup_action_counts") or {}).items())
    }
    mgt_export_audit_review_followup_action_label = ", ".join(
        f"{action}={count}"
        for action, count in sorted(mgt_export_audit_review_followup_action_counts.items())
    )
    mgt_export_audit_review_followup_owner_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_followup_metrics.get("audit_review_followup_owner_counts") or {}).items())
    }
    mgt_export_audit_review_followup_owner_label = ", ".join(
        f"{owner}={count}"
        for owner, count in sorted(mgt_export_audit_review_followup_owner_counts.items())
    )
    mgt_export_audit_review_followup_status_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_followup_metrics.get("audit_review_followup_status_counts") or {}).items())
    }
    mgt_export_audit_review_followup_status_label = ", ".join(
        f"{status}={count}"
        for status, count in sorted(mgt_export_audit_review_followup_status_counts.items())
    )
    mgt_export_audit_review_followup_mode = str(
        mgt_export_followup_metrics.get("audit_review_followup_mode", "") or ""
    )
    mgt_export_audit_review_followup_review_owner_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_followup_metrics.get("audit_review_followup_review_owner_counts") or {}).items())
    }
    mgt_export_audit_review_followup_review_owner_label = ", ".join(
        f"{owner}={count}" for owner, count in sorted(mgt_export_audit_review_followup_review_owner_counts.items())
    )
    mgt_export_audit_review_followup_sla_state_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_followup_metrics.get("audit_review_followup_sla_state_counts") or {}).items())
    }
    mgt_export_audit_review_followup_sla_state_label = ", ".join(
        f"{state}={count}" for state, count in sorted(mgt_export_audit_review_followup_sla_state_counts.items())
    )
    mgt_export_audit_review_followup_age_bucket_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_followup_metrics.get("audit_review_followup_age_bucket_counts") or {}).items())
    }
    mgt_export_audit_review_followup_age_bucket_label = ", ".join(
        f"{bucket}={count}" for bucket, count in sorted(mgt_export_audit_review_followup_age_bucket_counts.items())
    )
    mgt_export_audit_review_followup_overdue_item_count = int(
        mgt_export_followup_metrics.get("audit_review_followup_overdue_item_count", 0) or 0
    )
    mgt_export_audit_review_followup_oldest_open_age_hours = float(
        mgt_export_followup_metrics.get("audit_review_followup_oldest_open_age_hours", 0.0) or 0.0
    )
    mgt_export_audit_review_followup_oldest_open_packet_id = str(
        mgt_export_followup_metrics.get("audit_review_followup_oldest_open_packet_id", "") or ""
    )
    mgt_export_audit_review_followup_reference_time_utc = str(
        mgt_export_followup_metrics.get("audit_review_followup_reference_time_utc", "") or ""
    )
    mgt_export_audit_review_followup_sla_policy_label = str(
        mgt_export_followup_metrics.get("audit_review_followup_sla_policy_label", "") or ""
    )
    mgt_export_audit_review_resolution_item_count = int(
        mgt_export_summary.get("audit_review_resolution_item_count", 0) or 0
    )
    mgt_export_audit_review_resolution_file_count = int(
        mgt_export_summary.get("audit_review_resolution_file_count", 0) or 0
    )
    mgt_export_audit_review_resolution_open_item_count = int(
        mgt_export_summary.get("audit_review_resolution_open_item_count", 0) or 0
    )
    mgt_export_audit_review_resolution_closed_item_count = int(
        mgt_export_summary.get("audit_review_resolution_closed_item_count", 0) or 0
    )
    mgt_export_audit_review_resolution_pending_item_count = int(
        mgt_export_summary.get("audit_review_resolution_pending_item_count", 0) or 0
    )
    mgt_export_audit_review_resolution_open_revision_count = int(
        mgt_export_summary.get("audit_review_resolution_open_revision_count", 0) or 0
    )
    mgt_export_audit_review_resolution_closed_packet_count = int(
        mgt_export_summary.get("audit_review_resolution_closed_packet_count", 0) or 0
    )
    mgt_export_audit_review_resolution_action_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_resolution_action_counts") or {}).items())
    }
    mgt_export_audit_review_resolution_action_label = ", ".join(
        f"{action}={count}" for action, count in sorted(mgt_export_audit_review_resolution_action_counts.items())
    )
    mgt_export_audit_review_resolution_owner_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_resolution_owner_counts") or {}).items())
    }
    mgt_export_audit_review_resolution_owner_label = ", ".join(
        f"{owner}={count}" for owner, count in sorted(mgt_export_audit_review_resolution_owner_counts.items())
    )
    mgt_export_audit_review_resolution_status_counts = {
        str(k): int(v)
        for k, v in sorted((mgt_export_summary.get("audit_review_resolution_status_counts") or {}).items())
    }
    mgt_export_audit_review_resolution_status_label = ", ".join(
        f"{status}={count}" for status, count in sorted(mgt_export_audit_review_resolution_status_counts.items())
    )
    mgt_export_audit_review_resolution_mode = str(
        mgt_export_summary.get("audit_review_resolution_mode", "") or ""
    )
    mgt_export_rebar_delivery_mode = str(mgt_export_summary.get("rebar_delivery_mode", ""))
    mgt_export_evidence_model = str(mgt_export_summary.get("evidence_model", ""))
    mgt_export_delivery_boundary = (
        f"direct_patch={mgt_export_direct_patch_action_family_label or 'n/a'} | "
        f"sidecar={mgt_export_instruction_sidecar_action_family_label or 'n/a'} | "
        f"connection_payload={mgt_export_connection_detailing_delivery_mode or 'n/a'} | "
        f"detailing_payload={mgt_export_detailing_delivery_mode or 'n/a'}"
    )
    mgt_export_cloned_section_count = int(mgt_export_summary.get("cloned_section_count", 0) or 0)
    mgt_export_cloned_thickness_count = int(mgt_export_summary.get("cloned_thickness_count", 0) or 0)
    mgt_export_cloned_material_count = int(mgt_export_summary.get("cloned_material_count", 0) or 0)
    mgt_export_retargeted_element_row_count = int(mgt_export_summary.get("retargeted_element_row_count", 0) or 0)
    pbd_hinge_proxy_artifact_count = sum(
        1
        for key in ("hinge_proxy_3d_png", "hinge_proxy_timeline_png")
        if str(pbd_artifacts.get(key, "")).strip()
    )
    pbd_dynamic_hinge_refresh_ready = bool(
        _pass(pbd_hinge_refresh)
        or bool(pbd_summary.get("dynamic_hinge_refresh_ready", False))
        or bool(pbd_package.get("dynamic_hinge_refresh_ready", False))
    )
    pbd_hinge_refresh_artifact_present = bool((pbd_hinge_refresh.get("summary") or {}).get("hinge_refresh_artifact_present", False))
    pbd_hinge_refresh_artifact_kind = str((pbd_hinge_refresh.get("summary") or {}).get("hinge_refresh_artifact_kind", "") or "")
    pbd_hinge_refresh_source_mode = str((pbd_hinge_refresh.get("summary") or {}).get("hinge_refresh_source_mode", "") or "")
    pbd_hinge_refresh_overlap_member_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_refresh_overlap_member_count", 0) or 0
    )
    pbd_hinge_refresh_rebar_sensitive_member_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_refresh_rebar_sensitive_member_count", 0) or 0
    )
    pbd_hinge_benchmark_gate_pass = bool((pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_gate_pass", False))
    pbd_hinge_benchmark_fixture_regression_pass = bool(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_fixture_regression_pass", False)
    )
    pbd_hinge_benchmark_alignment_pass = bool(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_alignment_pass", False)
    )
    pbd_hinge_benchmark_asset_count = int((pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_asset_count", 0) or 0)
    pbd_hinge_benchmark_train_count = int((pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_train_count", 0) or 0)
    pbd_hinge_benchmark_val_count = int((pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_val_count", 0) or 0)
    pbd_hinge_benchmark_holdout_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_holdout_count", 0) or 0
    )
    pbd_hinge_benchmark_rebar_sensitive_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_rebar_sensitive_count", 0) or 0
    )
    pbd_hinge_benchmark_confinement_sensitive_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_confinement_sensitive_count", 0) or 0
    )
    pbd_hinge_benchmark_fixture_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_fixture_count", 0) or 0
    )
    pbd_hinge_benchmark_fixture_min_point_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_fixture_min_point_count", 0) or 0
    )
    pbd_hinge_benchmark_fixture_min_peak_drift_ratio = float(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_fixture_min_peak_drift_ratio", 0.0) or 0.0
    )
    pbd_hinge_benchmark_alignment_refresh_column_row_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_alignment_refresh_column_row_count", 0) or 0
    )
    pbd_hinge_benchmark_alignment_rebar_sensitive_column_count = int(
        (pbd_hinge_refresh.get("summary") or {}).get(
            "hinge_benchmark_alignment_rebar_sensitive_column_count", 0
        )
        or 0
    )
    pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min = float(
        (pbd_hinge_refresh.get("summary") or {}).get(
            "hinge_benchmark_alignment_benchmark_rebar_ratio_min", 0.0
        )
        or 0.0
    )
    pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max = float(
        (pbd_hinge_refresh.get("summary") or {}).get(
            "hinge_benchmark_alignment_benchmark_rebar_ratio_max", 0.0
        )
        or 0.0
    )
    pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min = float(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_alignment_refresh_rebar_ratio_min", 0.0)
        or 0.0
    )
    pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max = float(
        (pbd_hinge_refresh.get("summary") or {}).get("hinge_benchmark_alignment_refresh_rebar_ratio_max", 0.0)
        or 0.0
    )
    pbd_hinge_state_mode = (
        str((pbd_hinge_refresh.get("summary") or {}).get("hinge_state_mode", "") or "recomputed_member_local_hinge_state")
        if pbd_dynamic_hinge_refresh_ready
        else "proxy_only_hinge_visualization"
    )
    pbd_hinge_refresh_reason = (
        str((pbd_hinge_refresh.get("summary") or {}).get("reason", "") or "Dynamic hinge-refresh artifact is attached.")
        if pbd_dynamic_hinge_refresh_ready
        else (
            "PBD review still publishes hinge proxy artifacts and does not expose optimized-rebar-aware "
            "FEMA/ASCE41 hinge refresh evidence."
        )
    )
    panel_zone_summary = panel_zone_clash.get("summary") if isinstance(panel_zone_clash.get("summary"), dict) else {}
    panel_zone_report_mode = str(panel_zone_summary.get("constructability_mode", "") or "")
    panel_zone_report_reason = str(panel_zone_clash.get("reason") or panel_zone_summary.get("reason") or "")
    panel_zone_proxy_candidate_count = int(panel_zone_summary.get("panel_zone_proxy_candidate_count", 0) or 0)
    panel_zone_source_artifact_kind = str(panel_zone_summary.get("panel_zone_source_artifact_kind", "") or "")
    panel_zone_source_artifact_path = str(panel_zone_summary.get("panel_zone_source_artifact_path", "") or "")
    panel_zone_source_contract_mode = str(panel_zone_summary.get("panel_zone_source_contract_mode", "") or "")
    panel_zone_internal_engine_complete = bool(panel_zone_summary.get("panel_zone_internal_engine_complete", False))
    panel_zone_external_validation_pending = bool(
        panel_zone_summary.get("panel_zone_external_validation_pending", False)
    )
    panel_zone_validation_boundary = str(panel_zone_summary.get("panel_zone_validation_boundary", "") or "")
    panel_zone_external_validation_surface = _panel_zone_external_validation_surface(
        {
            **panel_zone_summary,
            "panel_zone_3d_clash_ready": bool(_pass(panel_zone_clash)),
        }
    )
    panel_zone_external_validation_advisory_only = bool(panel_zone_external_validation_surface["advisory_only"])
    panel_zone_external_validation_release_blocking = bool(
        panel_zone_external_validation_surface["release_blocking"]
    )
    panel_zone_external_validation_status_label = str(panel_zone_external_validation_surface["status_label"])
    panel_zone_external_validation_source_count = int(panel_zone_external_validation_surface["source_count"])
    panel_zone_external_validation_validated_source_count = int(
        panel_zone_external_validation_surface["validated_source_count"]
    )
    panel_zone_external_validation_exact_source_count = int(
        panel_zone_external_validation_surface["exact_source_count"]
    )
    panel_zone_external_validation_fallback_source_count = int(
        panel_zone_external_validation_surface["fallback_source_count"]
    )
    panel_zone_external_validation_missing_source_count = int(
        panel_zone_external_validation_surface["missing_source_count"]
    )
    panel_zone_external_validation_unknown_source_count = int(
        panel_zone_external_validation_surface["unknown_source_count"]
    )
    panel_zone_external_validation_validated_source_ratio = float(
        panel_zone_external_validation_surface["validated_source_ratio"]
    )
    panel_zone_external_validation_exact_source_ratio = float(
        panel_zone_external_validation_surface["exact_source_ratio"]
    )
    panel_zone_external_validation_fallback_source_ratio = float(
        panel_zone_external_validation_surface["fallback_source_ratio"]
    )
    panel_zone_external_validation_candidate_member_count = int(
        panel_zone_external_validation_surface["candidate_member_count"]
    )
    panel_zone_external_validation_validated_member_count = int(
        panel_zone_external_validation_surface["validated_member_count"]
    )
    panel_zone_external_validation_exact_member_count = int(
        panel_zone_external_validation_surface["exact_member_count"]
    )
    panel_zone_external_validation_fallback_member_count = int(
        panel_zone_external_validation_surface["fallback_member_count"]
    )
    panel_zone_external_validation_validated_member_ratio = float(
        panel_zone_external_validation_surface["validated_member_ratio"]
    )
    panel_zone_external_validation_exact_member_ratio = float(
        panel_zone_external_validation_surface["exact_member_ratio"]
    )
    panel_zone_external_validation_fallback_member_ratio = float(
        panel_zone_external_validation_surface["fallback_member_ratio"]
    )
    panel_zone_external_validation_validated_row_count_total = int(
        panel_zone_external_validation_surface["validated_row_count_total"]
    )
    panel_zone_external_validation_exact_validated_row_count = int(
        panel_zone_external_validation_surface["exact_validated_row_count"]
    )
    panel_zone_external_validation_fallback_validated_row_count = int(
        panel_zone_external_validation_surface["fallback_validated_row_count"]
    )
    panel_zone_external_validation_exact_validated_row_ratio = float(
        panel_zone_external_validation_surface["exact_validated_row_ratio"]
    )
    panel_zone_external_validation_fallback_validated_row_ratio = float(
        panel_zone_external_validation_surface["fallback_validated_row_ratio"]
    )
    panel_zone_external_validation_provenance_summary_label = str(
        panel_zone_external_validation_surface["provenance_summary_label"]
    )
    panel_zone_external_validation_artifact_closed = bool(
        panel_zone_external_validation_surface["artifact_closed"]
    )
    panel_zone_external_validation_closure_mode = str(
        panel_zone_external_validation_surface["closure_mode"]
    )
    panel_zone_topology_capable_input = bool(panel_zone_summary.get("panel_zone_topology_capable_input", False))
    panel_zone_true_3d_clash_verified = bool(panel_zone_summary.get("panel_zone_true_3d_clash_verified", False))
    panel_zone_true_3d_anchorage_verified = bool(panel_zone_summary.get("panel_zone_true_3d_anchorage_verified", False))
    panel_zone_source_valid_row_counts = panel_zone_summary.get("panel_zone_source_valid_row_counts", {})
    if not isinstance(panel_zone_source_valid_row_counts, dict):
        panel_zone_source_valid_row_counts = {}
    panel_zone_source_valid_row_counts = {str(k): int(v or 0) for k, v in panel_zone_source_valid_row_counts.items()}
    panel_zone_source_overlap_member_counts = panel_zone_summary.get("panel_zone_source_overlap_member_counts", {})
    if not isinstance(panel_zone_source_overlap_member_counts, dict):
        panel_zone_source_overlap_member_counts = {}
    panel_zone_source_overlap_member_counts = {
        str(k): int(v or 0) for k, v in panel_zone_source_overlap_member_counts.items()
    }
    panel_zone_source_candidate_scan_modes = panel_zone_summary.get("panel_zone_source_candidate_scan_modes", {})
    if not isinstance(panel_zone_source_candidate_scan_modes, dict):
        panel_zone_source_candidate_scan_modes = {}
    panel_zone_source_candidate_scan_modes = {
        str(k): str(v or "") for k, v in panel_zone_source_candidate_scan_modes.items()
    }
    panel_zone_source_bundle_modes = panel_zone_summary.get("panel_zone_source_bundle_modes", {})
    if not isinstance(panel_zone_source_bundle_modes, dict):
        panel_zone_source_bundle_modes = {}
    panel_zone_source_bundle_modes = {str(k): str(v or "") for k, v in panel_zone_source_bundle_modes.items()}
    panel_zone_source_upstream_verification_tiers = panel_zone_summary.get(
        "panel_zone_source_upstream_verification_tiers", {}
    )
    if not isinstance(panel_zone_source_upstream_verification_tiers, dict):
        panel_zone_source_upstream_verification_tiers = {}
    panel_zone_source_upstream_verification_tiers = {
        str(k): str(v or "") for k, v in panel_zone_source_upstream_verification_tiers.items()
    }
    panel_zone_instruction_sidecar_present = bool(
        panel_zone_summary.get("panel_zone_instruction_sidecar_present", False)
    )
    panel_zone_instruction_sidecar_change_count = int(
        panel_zone_summary.get("panel_zone_instruction_sidecar_change_count", 0) or 0
    )
    panel_zone_instruction_sidecar_candidate_overlap_mode = str(
        panel_zone_summary.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "") or ""
    )
    panel_zone_instruction_sidecar_overlap_row_count = int(
        panel_zone_summary.get("panel_zone_instruction_sidecar_overlap_row_count", 0) or 0
    )
    panel_zone_instruction_sidecar_overlap_member_count = int(
        panel_zone_summary.get("panel_zone_instruction_sidecar_overlap_member_count", 0) or 0
    )
    panel_zone_instruction_sidecar_overlap_group_count = int(
        panel_zone_summary.get("panel_zone_instruction_sidecar_overlap_group_count", 0) or 0
    )
    panel_zone_instruction_sidecar_evidence_model = str(
        panel_zone_summary.get("panel_zone_instruction_sidecar_evidence_model", "") or ""
    )
    panel_zone_instruction_sidecar_rebar_delivery_mode = str(
        panel_zone_summary.get("panel_zone_instruction_sidecar_rebar_delivery_mode", "") or ""
    )
    panel_zone_member_mapping_sidecar_present = bool(
        panel_zone_summary.get("panel_zone_member_mapping_sidecar_present", False)
    )
    panel_zone_member_mapping_sidecar_mode = str(
        panel_zone_summary.get("panel_zone_member_mapping_sidecar_mode", "") or ""
    )
    panel_zone_member_mapping_sidecar_row_count = int(
        panel_zone_summary.get("panel_zone_member_mapping_sidecar_row_count", 0) or 0
    )
    panel_zone_member_mapping_sidecar_applied_row_count = int(
        panel_zone_summary.get("panel_zone_member_mapping_sidecar_applied_row_count", 0) or 0
    )
    panel_zone_member_mapping_sidecar_unmapped_source_member_count = int(
        panel_zone_summary.get("panel_zone_member_mapping_sidecar_unmapped_source_member_count", 0) or 0
    )
    panel_zone_validated_source_row_count_total = int(
        panel_zone_summary.get("panel_zone_validated_source_row_count_total", 0) or 0
    )
    panel_zone_validated_source_overlap_member_count_min = int(
        panel_zone_summary.get("panel_zone_validated_source_overlap_member_count_min", 0) or 0
    )
    panel_zone_missing_required_sources = panel_zone_summary.get("panel_zone_missing_required_sources", [])
    if not isinstance(panel_zone_missing_required_sources, list):
        panel_zone_missing_required_sources = []
    panel_zone_missing_required_sources = [str(value) for value in panel_zone_missing_required_sources if str(value).strip()]
    panel_zone_inbox_summary = (
        panel_zone_solver_verified_inbox_status.get("summary")
        if isinstance(panel_zone_solver_verified_inbox_status.get("summary"), dict)
        else {}
    )
    panel_zone_solver_verified_inbox_status_mode = str(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_inbox_status_mode", "") or ""
    )
    panel_zone_solver_verified_inbox_has_input = bool(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_inbox_has_input", False)
    )
    panel_zone_solver_verified_pending_input = bool(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_pending_input", False)
    )
    panel_zone_solver_verified_input_mode_detected = str(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_input_mode_detected", "") or ""
    )
    panel_zone_solver_verified_latest_consume_report_present = bool(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_latest_consume_report_present", False)
    )
    panel_zone_solver_verified_latest_consume_contract_pass = bool(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
    )
    panel_zone_solver_verified_latest_consume_reason_code = str(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_latest_consume_reason_code", "") or ""
    )
    panel_zone_solver_verified_source_origin_class = str(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_source_origin_class", "") or ""
    )
    panel_zone_solver_verified_release_refresh_source_allowed = bool(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
    )
    panel_zone_solver_verified_recommended_action = str(
        panel_zone_inbox_summary.get("panel_zone_solver_verified_recommended_action", "") or ""
    )
    if panel_zone_external_validation_pending and not panel_zone_external_validation_release_blocking:
        if panel_zone_solver_verified_pending_input:
            panel_zone_external_validation_status_label = (
                f"{panel_zone_external_validation_status_label}_pending_solver_input"
            )
        elif (
            panel_zone_solver_verified_latest_consume_report_present
            and not panel_zone_solver_verified_latest_consume_contract_pass
        ):
            panel_zone_external_validation_status_label = (
                f"{panel_zone_external_validation_status_label}_after_failed_consume"
            )
        elif panel_zone_solver_verified_inbox_status_mode.startswith("empty"):
            panel_zone_external_validation_status_label = (
                f"{panel_zone_external_validation_status_label}_no_solver_input"
            )
    panel_zone_external_validation_context = {
        **panel_zone_summary,
        "panel_zone_3d_clash_ready": bool(_pass(panel_zone_clash)),
        "panel_zone_external_validation_artifact_closed": bool(
            panel_zone_external_validation_artifact_closed
        ),
        "panel_zone_external_validation_closure_mode": panel_zone_external_validation_closure_mode,
        "panel_zone_external_validation_source_count": int(panel_zone_external_validation_source_count),
        "panel_zone_external_validation_validated_source_count": int(
            panel_zone_external_validation_validated_source_count
        ),
        "panel_zone_external_validation_exact_source_count": int(
            panel_zone_external_validation_exact_source_count
        ),
        "panel_zone_external_validation_fallback_source_count": int(
            panel_zone_external_validation_fallback_source_count
        ),
        "panel_zone_external_validation_missing_source_count": int(
            panel_zone_external_validation_missing_source_count
        ),
        "panel_zone_external_validation_unknown_source_count": int(
            panel_zone_external_validation_unknown_source_count
        ),
        "panel_zone_external_validation_candidate_member_count": int(
            panel_zone_external_validation_candidate_member_count
        ),
        "panel_zone_external_validation_validated_member_count": int(
            panel_zone_external_validation_validated_member_count
        ),
        "panel_zone_external_validation_exact_member_count": int(
            panel_zone_external_validation_exact_member_count
        ),
        "panel_zone_external_validation_fallback_member_count": int(
            panel_zone_external_validation_fallback_member_count
        ),
        "panel_zone_external_validation_validated_row_count_total": int(
            panel_zone_external_validation_validated_row_count_total
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            panel_zone_external_validation_exact_validated_row_count
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            panel_zone_external_validation_fallback_validated_row_count
        ),
        "panel_zone_external_validation_provenance_summary_label": (
            panel_zone_external_validation_provenance_summary_label
        ),
        "panel_zone_solver_verified_inbox_status_mode": panel_zone_solver_verified_inbox_status_mode,
        "panel_zone_solver_verified_inbox_has_input": panel_zone_solver_verified_inbox_has_input,
        "panel_zone_solver_verified_pending_input": panel_zone_solver_verified_pending_input,
        "panel_zone_solver_verified_input_mode_detected": panel_zone_solver_verified_input_mode_detected,
        "panel_zone_solver_verified_latest_consume_report_present": (
            panel_zone_solver_verified_latest_consume_report_present
        ),
        "panel_zone_solver_verified_latest_consume_contract_pass": (
            panel_zone_solver_verified_latest_consume_contract_pass
        ),
        "panel_zone_solver_verified_latest_consume_reason_code": (
            panel_zone_solver_verified_latest_consume_reason_code
        ),
        "panel_zone_solver_verified_recommended_action": panel_zone_solver_verified_recommended_action,
    }
    panel_zone_external_validation_required_evidence = build_panel_zone_external_validation_required_evidence(
        panel_zone_external_validation_context,
        status_label=panel_zone_external_validation_status_label,
    )
    panel_zone_external_validation_summary_line = build_panel_zone_external_validation_summary_line(
        panel_zone_external_validation_context,
        status_label=panel_zone_external_validation_status_label,
    )
    panel_zone_external_validation_local_closure_surface = build_panel_zone_external_validation_local_closure_surface(
        panel_zone_external_validation_context,
        status_label=panel_zone_external_validation_status_label,
    )
    panel_zone_external_validation_local_closure_state = str(
        panel_zone_external_validation_local_closure_surface["state"]
    )
    panel_zone_external_validation_local_closure_label = str(
        panel_zone_external_validation_local_closure_surface["label"]
    )
    panel_zone_external_validation_closing_summary_label = (
        f"{panel_zone_external_validation_summary_line} | "
        f"local_closure_state={panel_zone_external_validation_local_closure_state} | "
        f"local_closure_label={panel_zone_external_validation_local_closure_label} | "
        f"inbox={panel_zone_solver_verified_inbox_status_mode or 'unknown'} | "
        f"pending_input={panel_zone_solver_verified_pending_input} | "
        f"latest_consume_present={panel_zone_solver_verified_latest_consume_report_present} | "
        f"latest_consume_pass={panel_zone_solver_verified_latest_consume_contract_pass} | "
        f"latest_consume_reason={panel_zone_solver_verified_latest_consume_reason_code or 'n/a'} | "
        f"next={panel_zone_solver_verified_recommended_action or 'n/a'}"
    )
    panel_zone_3d_clash_ready = bool(_pass(panel_zone_clash))
    if panel_zone_3d_clash_ready:
        panel_zone_constructability_mode = panel_zone_report_mode or "panel_zone_3d_clash_verified"
        panel_zone_constructability_reason = panel_zone_report_reason or "Panel-zone 3D clash artifact is attached."
    elif panel_zone_report_mode:
        panel_zone_constructability_mode = panel_zone_report_mode
        panel_zone_constructability_reason = panel_zone_report_reason or "Panel-zone constructability holdout remains open."
    else:
        panel_zone_constructability_mode = "scalar_proxy_hard_gate_only"
        panel_zone_constructability_reason = (
            "Constructability currently relies on scalar detailing/congestion/anchorage hard gates; "
            "no 3D panel-zone clash and anchorage recomputation artifact is attached."
        )
    if (not panel_zone_3d_clash_ready) and panel_zone_solver_verified_pending_input:
        panel_zone_constructability_reason = (
            f"{panel_zone_constructability_reason} "
            "Solver-verified panel input is staged in the inbox and still pending consume into the live release chain."
        )
    elif panel_zone_3d_clash_ready and panel_zone_external_validation_pending and panel_zone_solver_verified_pending_input:
        panel_zone_constructability_reason = (
            f"{panel_zone_constructability_reason} "
            "Solver-verified closing input is staged in the inbox but has not yet been consumed into the release chain."
        )
    elif (
        (not panel_zone_3d_clash_ready)
        and panel_zone_solver_verified_latest_consume_report_present
        and not panel_zone_solver_verified_latest_consume_contract_pass
    ):
        panel_zone_constructability_reason = (
            f"{panel_zone_constructability_reason} "
            f"Latest inbox consume did not pass ({panel_zone_solver_verified_latest_consume_reason_code or 'unknown'})."
        )
    elif (
        panel_zone_3d_clash_ready
        and panel_zone_external_validation_pending
        and panel_zone_solver_verified_latest_consume_report_present
        and not panel_zone_solver_verified_latest_consume_contract_pass
    ):
        panel_zone_constructability_reason = (
            f"{panel_zone_constructability_reason} "
            f"Latest solver-verified consume attempt did not pass ({panel_zone_solver_verified_latest_consume_reason_code or 'unknown'})."
        )
    elif (
        panel_zone_3d_clash_ready
        and panel_zone_external_validation_pending
        and panel_zone_solver_verified_inbox_status_mode.startswith("empty")
    ):
        panel_zone_constructability_reason = (
            f"{panel_zone_constructability_reason} "
            "No pending solver-verified panel input is available in the local inbox."
        )
    panel_zone_advisory_only = bool(
        panel_zone_3d_clash_ready
        and panel_zone_external_validation_pending
        and panel_zone_validation_boundary == "external_validation_only"
    )
    panel_zone_release_blocking = bool(not panel_zone_3d_clash_ready)
    if panel_zone_release_blocking:
        panel_zone_status_label = "release_blocking"
    elif panel_zone_external_validation_status_label not in {
        "",
        "not_applicable",
        "verified",
        "solver_verified",
    }:
        panel_zone_status_label = panel_zone_external_validation_status_label
    else:
        panel_zone_status_label = "release_ready"
    foundation_summary = foundation_optimization.get("summary") if isinstance(foundation_optimization.get("summary"), dict) else {}
    foundation_member_type_counts = (
        design_opt_dataset_summary.get("member_type_counts")
        if isinstance(design_opt_dataset_summary.get("member_type_counts"), dict)
        else {}
    )
    foundation_member_type_count = max(
        int(_foundation_member_count_from_counts(foundation_member_type_counts)),
        int(foundation_summary.get("foundation_member_type_count", 0) or 0),
    )
    foundation_member_type_present = foundation_member_type_count > 0
    foundation_optimization_ready = bool(_pass(foundation_optimization) and foundation_member_type_present)
    foundation_report_mode = str(foundation_summary.get("optimization_mode", "") or "")
    foundation_report_reason = str(foundation_optimization.get("reason") or foundation_summary.get("reason") or "")
    foundation_scope_source = str(foundation_summary.get("foundation_scope_source", "") or "")
    foundation_artifact_scan_mode = str(foundation_summary.get("foundation_artifact_scan_mode", "") or "")
    foundation_artifact_evidence_mode = str(foundation_summary.get("foundation_artifact_evidence_mode", "") or "")
    upstream_foundation_label_count = int(foundation_summary.get("upstream_foundation_label_count", 0) or 0)
    raw_source_foundation_label_count = int(foundation_summary.get("raw_source_foundation_label_count", 0) or 0)
    upstream_foundation_provenance_mode = str(foundation_summary.get("upstream_foundation_provenance_mode", "") or "")
    if foundation_optimization_ready:
        foundation_optimization_mode = foundation_report_mode or "active_foundation_member_optimization"
        foundation_optimization_reason = foundation_report_reason or "Foundation optimization artifact is attached."
    elif foundation_report_mode:
        foundation_optimization_mode = foundation_report_mode
        foundation_optimization_reason = foundation_report_reason or "Foundation optimization holdout remains open."
    elif foundation_member_type_present:
        foundation_optimization_mode = "dataset_present_but_no_foundation_optimization_gate"
        foundation_optimization_reason = (
            "Foundation groups are present in the optimization dataset, but no active mat/pile optimization "
            "gate or report is attached."
        )
    else:
        foundation_optimization_mode = "rule_engine_present_but_dataset_absent"
        foundation_optimization_reason = (
            "Reduced-order foundation checks exist, but the active design-optimization dataset/state does not "
            "contain foundation member groups."
        )
    wind_raw_mapping_summary = wind_raw_mapping.get("summary") if isinstance(wind_raw_mapping.get("summary"), dict) else {}
    wind_raw_mapping_ready = bool(_pass(wind_raw_mapping))
    wind_report_mode = str(wind_raw_mapping_summary.get("mapping_mode", "") or "")
    wind_report_reason = str(wind_raw_mapping.get("reason") or wind_raw_mapping_summary.get("reason") or "")
    if wind_raw_mapping_ready:
        wind_tunnel_mapping_mode = wind_report_mode or "raw_hffb_node_pressure_mapping"
        wind_tunnel_mapping_reason = wind_report_reason or "Raw wind-tunnel mapping artifact is attached."
    elif wind_report_mode or wind_report_reason:
        wind_tunnel_mapping_mode = wind_report_mode or "unverified_pressure_mapping"
        wind_tunnel_mapping_reason = wind_report_reason or "Wind raw mapping holdout remains open."
    else:
        wind_tunnel_mapping_mode = "semantic_pressure_binding_only" if midas_bound_pressure_row_count > 0 else "unverified_pressure_mapping"
        wind_tunnel_mapping_reason = (
            "MIDAS pressure/load semantic binding is present, but no verified raw wind-tunnel HFFB mapping "
            "artifact is attached to prove direct floor/node pressure mapping."
        )
    advanced_holdouts = [
        {
            "id": "pbd_dynamic_hinge_refresh",
            "severity": "P0",
            "title": "Dynamic plastic-hinge refresh",
            "ready": bool(pbd_dynamic_hinge_refresh_ready),
            "mode": pbd_hinge_state_mode,
            "reason": pbd_hinge_refresh_reason,
            "evidence": (
                f"hinge_proxy_artifacts={pbd_hinge_proxy_artifact_count}, "
                f"artifact_present={pbd_hinge_refresh_artifact_present}, "
                f"artifact_kind={pbd_hinge_refresh_artifact_kind or 'unknown'}, "
                f"source_mode={pbd_hinge_refresh_source_mode or 'unspecified'}, "
                f"overlap_members={pbd_hinge_refresh_overlap_member_count}, "
                f"rebar_sensitive_members={pbd_hinge_refresh_rebar_sensitive_member_count}, "
                f"benchmark_assets={pbd_hinge_benchmark_asset_count}, "
                f"benchmark_split=train:{pbd_hinge_benchmark_train_count}/val:{pbd_hinge_benchmark_val_count}/holdout:{pbd_hinge_benchmark_holdout_count}, "
                f"benchmark_gate_pass={pbd_hinge_benchmark_gate_pass}, "
                f"benchmark_fixture_regression_pass={pbd_hinge_benchmark_fixture_regression_pass}, "
                f"benchmark_alignment_pass={pbd_hinge_benchmark_alignment_pass}, "
                f"benchmark_fixture_count={pbd_hinge_benchmark_fixture_count}, "
                f"benchmark_fixture_min_point_count={pbd_hinge_benchmark_fixture_min_point_count}, "
                f"benchmark_fixture_min_peak_drift_ratio={pbd_hinge_benchmark_fixture_min_peak_drift_ratio:.6f}, "
                f"benchmark_alignment_refresh_columns={pbd_hinge_benchmark_alignment_refresh_column_row_count}, "
                f"benchmark_alignment_rebar_sensitive_columns={pbd_hinge_benchmark_alignment_rebar_sensitive_column_count}, "
                f"benchmark_rebar_ratio_range={pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min:.4f}-"
                f"{pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max:.4f}, "
                f"refresh_rebar_ratio_range={pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min:.4f}-"
                f"{pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max:.4f}, "
                f"peer_blind_compare_cases={int(peer_blind_prediction_compare_surface.get('case_count', 0) or 0)}, "
                f"peer_blind_compare_build_cases={int(peer_blind_prediction_compare_surface.get('build_case_count', 0) or 0)}, "
                f"peer_blind_compare_measured_response_ready={bool(peer_blind_prediction_compare_surface.get('measured_response_ready', False))}, "
                f"peer_blind_landing_state={str(peer_blind_prediction_measured_response_landing_surface.get('landing_state', '') or 'unknown')}, "
                f"peer_blind_landing_matched_files={int(peer_blind_prediction_measured_response_landing_surface.get('matched_file_count', 0) or 0)}, "
                f"peer_blind_landing_csv_files={int(peer_blind_prediction_measured_response_landing_surface.get('csv_file_count', 0) or 0)}, "
                f"peer_blind_landing_accel_candidates={int(peer_blind_prediction_measured_response_landing_surface.get('acceleration_candidate_count', 0) or 0)}, "
                f"peer_blind_landing_drift_candidates={int(peer_blind_prediction_measured_response_landing_surface.get('drift_candidate_count', 0) or 0)}, "
                f"response_storage={str(pbd_summary.get('response_storage', 'n/a'))}, "
                f"pbd_case_count={int(pbd_summary.get('case_metrics_npz_case_count', 0) or 0)}"
            ),
        },
        {
            "id": "panel_zone_3d_clash_and_anchorage",
            "severity": "P0",
            "title": "Panel-zone 3D clash and anchorage coverage",
            "ready": bool(panel_zone_3d_clash_ready),
            "status_label": panel_zone_status_label,
            "advisory_only": bool(panel_zone_advisory_only),
            "release_blocking": bool(panel_zone_release_blocking),
            "external_validation_required_evidence": panel_zone_external_validation_required_evidence,
            "external_validation_local_closure_state": panel_zone_external_validation_local_closure_state,
            "external_validation_local_closure_label": panel_zone_external_validation_local_closure_label,
            "mode": panel_zone_constructability_mode,
            "reason": panel_zone_constructability_reason,
            "evidence": (
                f"proxy_candidates={panel_zone_proxy_candidate_count}, "
                f"source={panel_zone_source_artifact_kind or 'unknown'}:{panel_zone_source_contract_mode or 'unspecified'}, "
                f"status_label={panel_zone_status_label}, "
                f"advisory_only={panel_zone_advisory_only}, "
                f"release_blocking={panel_zone_release_blocking}, "
                f"artifact_closed={panel_zone_external_validation_artifact_closed}, "
                f"closure_mode={panel_zone_external_validation_closure_mode}, "
                f"coverage={panel_zone_external_validation_provenance_summary_label}, "
                f"closing={panel_zone_external_validation_closing_summary_label}, "
                f"required_evidence={panel_zone_external_validation_required_evidence}, "
                f"local_closure_state={panel_zone_external_validation_local_closure_state}, "
                f"local_closure_label={panel_zone_external_validation_local_closure_label}, "
                f"validated_rows={panel_zone_validated_source_row_count_total}, "
                f"min_overlap={panel_zone_validated_source_overlap_member_count_min}, "
                f"internal_complete={panel_zone_internal_engine_complete}, "
                f"external_validation_pending={panel_zone_external_validation_pending}, "
                f"external_validation_status={panel_zone_external_validation_status_label}, "
                f"external_validation_advisory_only={panel_zone_external_validation_advisory_only}, "
                f"external_validation_release_blocking={panel_zone_external_validation_release_blocking}, "
                f"validation_boundary={panel_zone_validation_boundary or 'open'}, "
                f"inbox_status={panel_zone_solver_verified_inbox_status_mode or 'unknown'}, "
                f"inbox_pending={panel_zone_solver_verified_pending_input}, "
                f"inbox_origin={panel_zone_solver_verified_source_origin_class or 'missing'}, "
                f"inbox_release_refresh_allowed={panel_zone_solver_verified_release_refresh_source_allowed}, "
                f"latest_consume={panel_zone_solver_verified_latest_consume_contract_pass}:"
                f"{panel_zone_solver_verified_latest_consume_reason_code or 'n/a'}, "
                f"sidecar_present={panel_zone_instruction_sidecar_present}, "
                f"sidecar_changes={panel_zone_instruction_sidecar_change_count}, "
                f"sidecar_mode={panel_zone_instruction_sidecar_candidate_overlap_mode or 'none'}, "
                f"sidecar_overlap_rows={panel_zone_instruction_sidecar_overlap_row_count}, "
                f"sidecar_overlap_members={panel_zone_instruction_sidecar_overlap_member_count}, "
                f"sidecar_evidence={panel_zone_instruction_sidecar_evidence_model or 'none'}, "
                f"sidecar_delivery={panel_zone_instruction_sidecar_rebar_delivery_mode or 'none'}, "
                f"mapping_sidecar_present={panel_zone_member_mapping_sidecar_present}, "
                f"mapping_sidecar_mode={panel_zone_member_mapping_sidecar_mode or 'none'}, "
                f"mapping_sidecar_rows={panel_zone_member_mapping_sidecar_row_count}, "
                f"mapping_sidecar_applied={panel_zone_member_mapping_sidecar_applied_row_count}, "
                f"mapping_sidecar_unmapped={panel_zone_member_mapping_sidecar_unmapped_source_member_count}, "
                f"bundle_modes={','.join(f'{k}:{v}' for k, v in sorted(panel_zone_source_bundle_modes.items()) if str(v).strip()) or 'none'}, "
                f"upstream_tiers={','.join(f'{k}:{v}' for k, v in sorted(panel_zone_source_upstream_verification_tiers.items()) if str(v).strip()) or 'none'}, "
                f"scan_modes={','.join(f'{k}:{v}' for k, v in sorted(panel_zone_source_candidate_scan_modes.items()) if str(v).strip()) or 'none'}, "
                f"topology_capable={panel_zone_topology_capable_input}, "
                f"missing_3d={','.join(panel_zone_missing_required_sources) or 'none'}"
            ),
        },
        {
            "id": "foundation_mat_pile_optimization",
            "severity": "P1",
            "title": "Foundation / mat / pile optimization",
            "ready": bool(foundation_optimization_ready),
            "mode": foundation_optimization_mode,
            "reason": foundation_optimization_reason,
            "evidence": (
                f"foundation_member_type_count={foundation_member_type_count}, "
                f"scope_source={foundation_scope_source or 'dataset_summary'}, "
                f"raw_source_labels={raw_source_foundation_label_count}, "
                f"upstream_labels={upstream_foundation_label_count}, "
                f"upstream_mode={upstream_foundation_provenance_mode or 'none'}"
            ),
        },
        {
            "id": "wind_tunnel_raw_mapping",
            "severity": "P1",
            "title": "Raw wind-tunnel data mapping",
            "ready": bool(wind_raw_mapping_ready),
            "mode": wind_tunnel_mapping_mode,
            "reason": wind_tunnel_mapping_reason,
            "evidence": (
                f"semantic_pressure_binding={midas_semantic_load_binding_pass}, "
                f"bound_pressure_rows={midas_bound_pressure_row_count}, "
                f"unbound_pressure_rows={midas_unbound_pressure_row_count}"
            ),
        },
    ]
    advanced_holdouts = [_normalize_advanced_holdout(row) for row in advanced_holdouts]
    advanced_holdout_count = len(advanced_holdouts)
    advanced_holdout_ready_count = sum(1 for row in advanced_holdouts if str(row.get("status")) == "closed")
    advanced_holdout_open_count = sum(1 for row in advanced_holdouts if str(row.get("status")) == "open")
    advanced_holdout_status_label = _compact_label(
        [f"{row.get('id', 'unknown')}:{row.get('status', 'unknown')}" for row in advanced_holdouts],
        max_items=6,
    )
    midas_load_semantic_gap_status = (
        "closed"
        if midas_semantic_load_binding_pass
        else ("narrowing" if _pass(midas) and midas_semantic_load_case_count > 0 else "open")
    )
    midas_gap_status = (
        "closed"
        if _pass(midas)
        and midas_unknown_rows == 0
        and midas_skipped_rows == 0
        and float(midas_metrics.get("element_skip_ratio", 1.0)) == 0.0
        else ("narrowing" if _pass(midas) and midas_unknown_rows <= 300 and midas_skipped_rows == 0 else "open")
    )
    hip_gap_status = "closed" if _pass(solver_hip) else "open"
    rc_gap_status = (
        "closed"
        if _pass(rc_benchmark) and str(rc_summary.get("validation_mode", "")) == "hybrid_authority_locked"
        else ("narrowing" if _pass(rc_benchmark) else "open")
    )
    kds_gap_status = (
        "closed"
        if _pass(kds)
        and int(kds_summary.get("summary_card_count", 0)) >= 8
        and int(kds_summary.get("compliance_row_count", 0)) >= 500
        and int(kds_summary.get("member_check_row_count", 0)) >= 500
        and int(kds_summary.get("clause_count", 0)) >= 8
        and int(kds_summary.get("member_type_count", 0)) >= 4
        else ("narrowing" if _pass(kds) and int(kds_summary.get("compliance_row_count", 0)) >= 100 else "open")
    )
    registry_gap_status = (
        "closed"
        if _pass(release_registry)
        and bool(release_registry_checks.get("signature_verified_pass", False))
        and bool(release_registry_checks.get("lock_manifest_hash_match", False))
        else ("narrowing" if _pass(release_registry) else "open")
    )
    breadth_gap_status = (
        "closed"
        if int(quality_summary.get("accepted_count", 0)) >= 4 and int(quality_catalog_meta.get("source_count", 0)) >= 4
        else ("narrowing" if int(quality_summary.get("accepted_count", 0)) >= 1 else "open")
    )
    native_authoring_gap_status = (
        "closed"
        if bool(native_authoring_release_surface.get("native_authoring_lane_ready", False))
        else (
            "narrowing"
            if bool(native_authoring_release_surface.get("native_authoring_evidence_attached", False))
            else "open"
        )
    )

    release_status = {
        "nightly_release_pass": _pass(nightly),
        "ci_gate_pass": _pass(ci),
        "midas_section_library_summary_line": midas_section_library_summary_line,
        "midas_kds_geometry_bridge_summary_line": midas_kds_geometry_bridge_summary_line,
        "midas_kds_geometry_bridge_load_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_load_crosswalk_count": int(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_load_crosswalk_expected": int(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_load_crosswalk_status": str(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_load_crosswalk_pass": midas_kds_geometry_bridge_load_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_count": int(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_expected": int(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_status": str(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_pass": midas_kds_geometry_bridge_semantic_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_count": int(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_status": str(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_pass": midas_kds_geometry_bridge_full_member_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_count": int(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_status": str(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_pass": midas_kds_geometry_bridge_full_section_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_count": int(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_status": str(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_pass": midas_kds_geometry_bridge_full_load_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_crosswalk_depth": int(midas_kds_geometry_bridge_full_crosswalk_depth),
        "midas_loadcomb_roundtrip_summary_line": midas_loadcomb_roundtrip_summary_line,
        "commercial_benchmark_breadth_summary_line": commercial_benchmark_breadth_summary_line,
        "measured_benchmark_breadth_summary_line": measured_benchmark_breadth_summary_line,
        "peer_blind_prediction_compare_summary_line": str(
            peer_blind_prediction_compare_surface.get("summary_line", "") or ""
        ),
        "peer_blind_prediction_compare_pass": bool(
            peer_blind_prediction_compare_surface.get("contract_pass", False)
        ),
        "peer_blind_prediction_compare_case_count": int(
            peer_blind_prediction_compare_surface.get("case_count", 0) or 0
        ),
        "peer_blind_prediction_compare_build_case_count": int(
            peer_blind_prediction_compare_surface.get("build_case_count", 0) or 0
        ),
        "peer_blind_prediction_compare_measured_response_ready": bool(
            peer_blind_prediction_compare_surface.get("measured_response_ready", False)
        ),
        "peer_blind_prediction_compare_acceleration_channel_count": int(
            peer_blind_prediction_compare_surface.get("acceleration_channel_count", 0) or 0
        ),
        "peer_blind_prediction_compare_drift_channel_count": int(
            peer_blind_prediction_compare_surface.get("drift_channel_count", 0) or 0
        ),
        "peer_blind_prediction_compare_entry_label": str(
            peer_blind_prediction_compare_surface.get("entry_label", "") or ""
        ),
        "peer_blind_prediction_compare_source_family": str(
            peer_blind_prediction_compare_surface.get("source_family", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_summary_line": str(
            peer_blind_prediction_measured_response_landing_surface.get("summary_line", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_pass": bool(
            peer_blind_prediction_measured_response_landing_surface.get("contract_pass", False)
        ),
        "peer_blind_prediction_measured_response_landing_state": str(
            peer_blind_prediction_measured_response_landing_surface.get("landing_state", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_matched_file_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("matched_file_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_csv_file_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("csv_file_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_acceleration_candidate_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("acceleration_candidate_count", 0)
            or 0
        ),
        "peer_blind_prediction_measured_response_landing_drift_candidate_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("drift_candidate_count", 0)
            or 0
        ),
        "peer_blind_prediction_measured_response_landing_sensor_candidate_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("sensor_candidate_count", 0)
            or 0
        ),
        "solver_breadth_summary_line": solver_breadth_summary_line,
        "element_material_breadth_summary_line": element_material_breadth_summary_line,
        "material_constitutive_summary_line": material_constitutive_summary_line,
        "material_constitutive_pass": material_constitutive_pass,
        "material_constitutive_calibration_matrix_pass_row_count": material_constitutive_calibration_matrix_pass_row_count,
        "material_constitutive_cyclic_library_reversal_count": material_constitutive_cyclic_library_reversal_count,
        "material_constitutive_bond_interface_cyclic_reversal_count": (
            material_constitutive_bond_interface_cyclic_reversal_count
        ),
        "steel_composite_constitutive_gate_summary_line": steel_composite_constitutive_gate_summary_line,
        "steel_composite_constitutive_gate_pass": steel_composite_constitutive_gate_pass,
        "midas_kds_row_provenance_export_summary_line": midas_kds_row_provenance_export_summary_line,
        "midas_kds_row_provenance_export_row_count": midas_kds_row_provenance_export_row_count,
        "midas_kds_row_provenance_export_exact_row_count": midas_kds_row_provenance_export_exact_row_count,
        "midas_kds_row_provenance_preview_row_count": midas_kds_row_provenance_preview_row_count,
        "midas_kds_row_provenance_preview_rows_present": midas_kds_row_provenance_preview_rows_present,
        "midas_kds_row_provenance_exact_row_coverage_label": midas_kds_row_provenance_exact_row_coverage_label,
        "midas_kds_row_provenance_preview_rows": midas_kds_row_provenance_preview_rows,
        "midas_kds_row_provenance_clause_filter_rows": midas_kds_row_provenance_clause_filter_rows,
        "midas_kds_row_provenance_member_filter_rows": midas_kds_row_provenance_member_filter_rows,
        "midas_kds_row_provenance_hazard_filter_rows": midas_kds_row_provenance_hazard_filter_rows,
        "midas_kds_row_provenance_rule_family_filter_rows": midas_kds_row_provenance_rule_family_filter_rows,
        "contact_readiness_summary_line": contact_readiness_summary_line,
        "foundation_soil_link_summary_line": foundation_soil_link_summary_line,
        "support_search_summary_line": support_search_summary_line,
        "support_search_count": int(support_search_surface.get("support_search_count", 0) or 0),
        "node_surface_proxy_count": int(support_search_surface.get("node_surface_proxy_count", 0) or 0),
        "support_depth_score": int(support_search_surface.get("support_depth_score", 0) or 0),
        "structural_contact_summary_line": structural_contact_summary_line,
        "general_fe_contact_matrix_summary_line": general_fe_contact_matrix_summary_line,
        "surface_interaction_benchmark_summary_line": surface_interaction_benchmark_summary_line,
        "midas_interoperability_summary_line": midas_interoperability_summary_line,
        "midas_native_roundtrip_summary_line": midas_native_roundtrip_summary_line,
        **native_authoring_release_surface,
        "advanced_holdout_count": int(advanced_holdout_count),
        "advanced_holdout_ready_count": int(advanced_holdout_ready_count),
        "advanced_holdout_open_count": int(advanced_holdout_open_count),
        "advanced_holdout_status_label": advanced_holdout_status_label,
        "load_combination_engine_summary_line": load_combination_engine_summary_line,
        "load_combination_engine_pass": load_combination_engine_pass,
        "load_combination_engine_combo_count": load_combination_engine_combo_count,
        "load_combination_engine_family_count": load_combination_engine_family_count,
        "load_combination_engine_max_nested_depth": load_combination_engine_max_nested_depth,
        "load_combination_editor_commercialization_summary_line": load_combination_editor_commercialization_summary_line,
        "load_combination_editor_commercialization_pass": load_combination_editor_commercialization_pass,
        "load_combination_editor_required_target_match_label": load_combination_editor_required_target_match_label,
        "load_combination_editor_code_check_assembly_ready": load_combination_editor_code_check_assembly_ready,
        "load_combination_editor_commercialization_report_path": str(
            args.load_combination_editor_commercialization_report
        ),
        "reference_regression_summary_line": reference_regression_summary_line,
        "reference_regression_pass": reference_regression_pass,
        "reference_regression_case_count": reference_regression_case_count,
        "reference_regression_passing_case_count": reference_regression_passing_case_count,
        "reference_regression_metric_count": reference_regression_metric_count,
        "reference_regression_passing_metric_count": reference_regression_passing_metric_count,
        "reference_regression_report_path": str(args.reference_regression_report),
        "advanced_ssi_summary_line": advanced_ssi_summary_line,
        "advanced_ssi_pass": advanced_ssi_pass,
        "advanced_ssi_peak_transfer_ratio_max": advanced_ssi_peak_transfer_ratio_max,
        "advanced_ssi_peak_transfer_group_id": advanced_ssi_peak_transfer_group_id,
        "advanced_ssi_min_group_interaction_efficiency_ratio": advanced_ssi_group_efficiency_ratio,
        "wind_workflow_summary_line": wind_workflow_summary_line,
        "wind_workflow_pass": wind_workflow_pass,
        "wind_workflow_occupant_comfort_class": wind_workflow_comfort_class,
        "wind_workflow_occupant_comfort_crosswind_bias_ratio": wind_workflow_crosswind_bias_ratio,
        "external_benchmark_submission_summary_line": committee_external_benchmark_submission_summary_line,
        "external_benchmark_submission_recommended_start_mode": committee_external_benchmark_submission_recommended_start_mode,
        "external_benchmark_submission_recommended_submission_scope": committee_external_benchmark_submission_recommended_submission_scope,
        "external_benchmark_submission_blocker_label": committee_external_benchmark_submission_blocker_label,
        "external_benchmark_submission_caution_label": committee_external_benchmark_submission_caution_label,
        "external_benchmark_submission_queue_count": committee_external_benchmark_submission_queue_count,
        "external_benchmark_submission_queue_ready_count": committee_external_benchmark_submission_queue_ready_count,
        "external_benchmark_submission_queue_review_pending_count": committee_external_benchmark_submission_queue_review_pending_count,
        "external_benchmark_submission_queue_blocked_count": committee_external_benchmark_submission_queue_blocked_count,
        "external_benchmark_submission_onepage_attestation_status": committee_external_benchmark_submission_onepage_attestation_status,
        "external_benchmark_submission_queue_rows": committee_external_benchmark_submission_queue_rows,
        "external_benchmark_submission_queue_rows_present": bool(committee_external_benchmark_submission_queue_rows),
        "panel_zone_status_label": panel_zone_status_label,
        "panel_zone_advisory_only": bool(panel_zone_advisory_only),
        "panel_zone_release_blocking": bool(panel_zone_release_blocking),
        "panel_zone_external_validation_status_label": panel_zone_external_validation_status_label,
        "panel_zone_external_validation_advisory_only": bool(panel_zone_external_validation_advisory_only),
        "panel_zone_external_validation_release_blocking": bool(panel_zone_external_validation_release_blocking),
        "panel_zone_external_validation_artifact_closed": bool(
            panel_zone_external_validation_artifact_closed
        ),
        "panel_zone_external_validation_closure_mode": panel_zone_external_validation_closure_mode,
        "panel_zone_external_validation_source_count": int(panel_zone_external_validation_source_count),
        "panel_zone_external_validation_validated_source_count": int(
            panel_zone_external_validation_validated_source_count
        ),
        "panel_zone_external_validation_exact_source_count": int(panel_zone_external_validation_exact_source_count),
        "panel_zone_external_validation_fallback_source_count": int(
            panel_zone_external_validation_fallback_source_count
        ),
        "panel_zone_external_validation_missing_source_count": int(
            panel_zone_external_validation_missing_source_count
        ),
        "panel_zone_external_validation_unknown_source_count": int(
            panel_zone_external_validation_unknown_source_count
        ),
        "panel_zone_external_validation_validated_source_ratio": float(
            panel_zone_external_validation_validated_source_ratio
        ),
        "panel_zone_external_validation_exact_source_ratio": float(
            panel_zone_external_validation_exact_source_ratio
        ),
        "panel_zone_external_validation_fallback_source_ratio": float(
            panel_zone_external_validation_fallback_source_ratio
        ),
        "panel_zone_external_validation_candidate_member_count": int(
            panel_zone_external_validation_candidate_member_count
        ),
        "panel_zone_external_validation_validated_member_count": int(
            panel_zone_external_validation_validated_member_count
        ),
        "panel_zone_external_validation_exact_member_count": int(panel_zone_external_validation_exact_member_count),
        "panel_zone_external_validation_fallback_member_count": int(
            panel_zone_external_validation_fallback_member_count
        ),
        "panel_zone_external_validation_validated_member_ratio": float(
            panel_zone_external_validation_validated_member_ratio
        ),
        "panel_zone_external_validation_exact_member_ratio": float(
            panel_zone_external_validation_exact_member_ratio
        ),
        "panel_zone_external_validation_fallback_member_ratio": float(
            panel_zone_external_validation_fallback_member_ratio
        ),
        "panel_zone_external_validation_validated_row_count_total": int(
            panel_zone_external_validation_validated_row_count_total
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            panel_zone_external_validation_exact_validated_row_count
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            panel_zone_external_validation_fallback_validated_row_count
        ),
        "panel_zone_external_validation_exact_validated_row_ratio": float(
            panel_zone_external_validation_exact_validated_row_ratio
        ),
        "panel_zone_external_validation_fallback_validated_row_ratio": float(
            panel_zone_external_validation_fallback_validated_row_ratio
        ),
        "panel_zone_external_validation_required_evidence": panel_zone_external_validation_required_evidence,
        "panel_zone_external_validation_summary_line": panel_zone_external_validation_summary_line,
        "panel_zone_external_validation_provenance_summary_label": panel_zone_external_validation_provenance_summary_label,
        "panel_zone_external_validation_closing_summary_label": panel_zone_external_validation_closing_summary_label,
        "panel_zone_external_validation_local_closure_state": panel_zone_external_validation_local_closure_state,
        "panel_zone_external_validation_local_closure_label": panel_zone_external_validation_local_closure_label,
        "midas_native_roundtrip_public_native_writeback_ready_count": int(
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("public_native_writeback_ready_count", 0)
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else 0
        ),
        "midas_native_roundtrip_public_raw_native_writeback_ready_count": int(
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("public_raw_native_writeback_ready_count", 0)
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else 0
        ),
        "midas_native_roundtrip_public_bridge_writeback_ready_count": int(
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("public_bridge_writeback_ready_count", 0)
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else 0
        ),
        "midas_native_roundtrip_public_archive_preview_writeback_ready_count": int(
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("public_archive_preview_writeback_ready_count", 0)
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else 0
        ),
        "midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count": int(
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get(
                "public_archive_structural_preview_writeback_ready_count", 0
            )
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else 0
        ),
        "midas_native_roundtrip_public_source_writeback_ready_count": int(
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("public_source_writeback_ready_count", 0)
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else 0
        ),
        "midas_native_roundtrip_taxonomy_case_counts": (
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("taxonomy_case_counts", {})
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else {}
        ),
        "midas_native_roundtrip_taxonomy_card_family_histogram": (
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("taxonomy_card_family_histogram", {})
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else {}
        ),
        "midas_native_roundtrip_structure_type_batch_markdowns": (
            ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get("structure_type_batch_markdowns", [])
            if isinstance(ci.get("midas_native_roundtrip_report"), dict)
            else []
        ),
        "performance_profiling_summary_line": performance_profiling_summary_line,
        "performance_profiling_detail_line": performance_profiling_detail_line,
        "solver_truthfulness_summary_line": solver_truthfulness_summary_line,
        "hardest_external_10case_kickoff_summary_line": hardest_external_10case_kickoff_summary_line,
        "nonlinear_generalization_summary_line": nonlinear_generalization_summary_line,
        "workflow_productization_summary_line": workflow_productization_summary_line,
        "workflow_contact_coupling_summary_line": workflow_contact_coupling_summary_line,
        "workflow_contact_coupling_summary": workflow_contact_coupling_summary,
        "workflow_contact_coupling_pass": bool(workflow_contact_coupling_surface.get("pass", False)),
        "workflow_contact_support_family_count": int(
            workflow_contact_coupling_surface.get("support_family_count", 0) or 0
        ),
        "workflow_contact_proxy_family_count": int(
            workflow_contact_coupling_surface.get("proxy_family_count", 0) or 0
        ),
        "workflow_contact_assembled_depth_value": int(
            workflow_contact_coupling_surface.get("assembled_depth_value", 0) or 0
        ),
        **commercial_workflow_breadth_surface,
        "korean_source_ingest_summary_line": korean_source_ingest_summary_line,
        "opensees_canonical_breadth_summary_line": opensees_canonical_breadth_summary_line,
        "korean_source_ingest_source_count": int(workflow_productization_summary.get("korean_source_ingest_source_count", 0) or 0),
        "korean_source_ingest_source_class_count": int(
            workflow_productization_summary.get("korean_source_ingest_source_class_count", 0) or 0
        ),
        "korean_source_ingest_collected_count": int(workflow_productization_summary.get("korean_source_ingest_collected_count", 0) or 0),
        "korean_source_ingest_metadata_only_count": int(
            workflow_productization_summary.get("korean_source_ingest_metadata_only_count", 0) or 0
        ),
        "korean_source_ingest_rejected_count": int(workflow_productization_summary.get("korean_source_ingest_rejected_count", 0) or 0),
        "korean_source_ingest_fingerprinted_count": int(
            workflow_productization_summary.get("korean_source_ingest_fingerprinted_count", 0) or 0
        ),
        "korean_source_ingest_duplicate_sha_group_count": int(
            workflow_productization_summary.get("korean_source_ingest_duplicate_sha_group_count", 0) or 0
        ),
        "korean_source_ingest_gate_report_path": str(
            workflow_productization_summary.get("korean_source_ingest_gate_report_path", "") or ""
        ),
        "korean_structural_preview_queue_summary_line": korean_structural_preview_queue_summary_line,
        "korean_structural_preview_queue_candidate_total": int(
            workflow_productization_summary.get("korean_structural_preview_queue_candidate_total", 0) or 0
        ),
        "korean_structural_preview_queue_pending_candidate_count": int(
            workflow_productization_summary.get("korean_structural_preview_queue_pending_candidate_count", 0) or 0
        ),
        "korean_structural_preview_queue_state": str(
            workflow_productization_summary.get("korean_structural_preview_queue_state", "") or ""
        ),
        "korean_structural_preview_promotion_queue_path": str(
            workflow_productization_summary.get("korean_structural_preview_promotion_queue_path", "") or ""
        ),
        "irregular_structure_summary_line": irregular_structure_summary_line,
        "irregular_structure_track_pass": bool(irregular_structure_summary.get("irregular_structure_track_pass", False)),
        "irregular_structure_family_count": int(irregular_structure_summary.get("irregular_structure_family_count", 0) or 0),
        "irregular_structure_source_record_count": int(
            irregular_structure_summary.get("irregular_structure_source_record_count", 0) or 0
        ),
        "irregular_structure_local_ready_count": int(irregular_structure_summary.get("irregular_structure_local_ready_count", 0) or 0),
        "irregular_structure_remote_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_remote_candidate_count", 0) or 0
        ),
        "irregular_structure_native_roundtrip_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_native_roundtrip_candidate_count", 0) or 0
        ),
        "irregular_structure_solver_benchmark_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_solver_benchmark_candidate_count", 0) or 0
        ),
        "irregular_structure_ai_learning_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_ai_learning_candidate_count", 0) or 0
        ),
        "irregular_structure_top5_count": int(irregular_structure_summary.get("irregular_structure_top5_count", 0) or 0),
        "irregular_structure_top5_family_ids": list(irregular_structure_summary.get("irregular_structure_top5_family_ids", []) or []),
        "irregular_structure_gate_report_path": str(
            irregular_structure_artifacts.get("irregular_structure_gate_report_path", "") or ""
        ),
        "irregular_top5_execution_manifest_path": str(
            irregular_structure_artifacts.get("irregular_top5_execution_manifest_path", "") or ""
        ),
        "irregular_structure_source_catalog_path": str(
            irregular_structure_artifacts.get("irregular_source_catalog_path", "") or ""
        ),
        "irregular_priority_manifest_path": str(
            irregular_structure_artifacts.get("irregular_priority_manifest_path", "") or ""
        ),
        "irregular_structure_collection_report_path": str(
            irregular_structure_artifacts.get("irregular_collection_report_path", "") or ""
        ),
        "irregular_triage_report_path": str(
            irregular_structure_artifacts.get("irregular_triage_report_path", "") or ""
        ),
        "commercial_readiness_summary_line": commercial_readiness_summary_line,
        "static_validation_pass": _pass(static),
        "freeze_snapshot_pass": _pass(freeze),
        "promotion_pass": _pass(promotion),
        "promotion_reason_code": str(promotion.get("reason_code", "")),
        "promotion_hold_for_review": str(promotion.get("reason_code", "")) == "HOLD_FOR_REVIEW",
        "hold_review_manifest": str(promotion.get("hold_review_manifest", "")),
        "commercial_readiness_pass": _pass(commercial),
        "global_authority_pass": _pass(authority),
        "hip_kernel_smoke_pass": _pass(hip),
        "midas_conversion_pass": _pass(midas),
        "construction_sequence_pass": _pass(construction),
        "flexible_diaphragm_pass": _pass(diaphragm),
        "repro_version_lock_pass": _pass(repro),
        "release_registry_pass": _pass(release_registry),
        "kds_compliance_pass": _pass(kds),
        "solver_hip_e2e_pass": _pass(solver_hip),
        "solver_truthfulness_pass": _pass(solver_truthfulness),
        "rc_benchmark_lock_pass": _pass(rc_benchmark),
        "quality_mgt_corpus_pass": _pass(quality_mgt_corpus),
        "midas_semantic_load_binding_pass": midas_semantic_load_binding_pass,
        "mgt_export_artifact_exists": mgt_export_artifact_exists,
        "mgt_export_contract_pass": mgt_export_contract_pass,
        "mgt_export_support_mode": mgt_export_support_mode,
        "mgt_export_loadcomb_preview_exists": mgt_export_loadcomb_preview_exists,
        "mgt_export_loadcomb_roundtrip_report_exists": mgt_export_loadcomb_roundtrip_report_exists,
        "mgt_export_loadcomb_roundtrip_pass": mgt_export_loadcomb_roundtrip_pass,
        "mgt_export_loadcomb_roundtrip_summary_line": mgt_export_loadcomb_roundtrip_summary_line,
        "mgt_export_loadcomb_roundtrip_recovery_mode": mgt_export_loadcomb_roundtrip_recovery_mode,
        "mgt_export_loadcomb_combo_count": mgt_export_loadcomb_combo_count,
        "mgt_export_supported_change_count": mgt_export_supported_change_count,
        "mgt_export_unsupported_change_count": mgt_export_unsupported_change_count,
        "mgt_export_direct_patch_change_count": mgt_export_direct_patch_change_count,
        "mgt_export_direct_patch_supported_action_families": mgt_export_direct_patch_supported_action_families,
        "mgt_export_sidecar_supported_action_families": mgt_export_sidecar_supported_action_families,
        "mgt_export_direct_patch_action_family_counts": mgt_export_direct_patch_action_family_counts,
        "mgt_export_direct_patch_action_family_label": mgt_export_direct_patch_action_family_label,
        "mgt_export_special_member_supported_action_family_counts": mgt_export_special_member_supported_action_family_counts,
        "mgt_export_special_member_direct_patch_action_family_counts": mgt_export_special_member_direct_patch_action_family_counts,
        "mgt_export_special_member_zero_touch_verified_action_family_counts": (
            mgt_export_special_member_zero_touch_verified_action_family_counts
        ),
        "mgt_export_special_member_supported_action_family_label": (
            mgt_export_special_member_supported_action_family_label
        ),
        "mgt_export_special_member_direct_patch_action_family_label": (
            mgt_export_special_member_direct_patch_action_family_label
        ),
        "mgt_export_special_member_zero_touch_verified_action_family_label": (
            mgt_export_special_member_zero_touch_verified_action_family_label
        ),
        "mgt_export_material_level_rebar_payload_row_count": mgt_export_material_level_rebar_payload_row_count,
        "mgt_export_material_level_rebar_payload_available_count": mgt_export_material_level_rebar_payload_available_count,
        "mgt_export_group_local_rebar_payload_row_count": mgt_export_group_local_rebar_payload_row_count,
        "mgt_export_group_local_rebar_payload_available_count": mgt_export_group_local_rebar_payload_available_count,
        "mgt_export_group_local_connection_detailing_payload_row_count": mgt_export_group_local_connection_detailing_payload_row_count,
        "mgt_export_group_local_connection_detailing_payload_available_count": mgt_export_group_local_connection_detailing_payload_available_count,
        "mgt_export_group_local_detailing_payload_row_count": mgt_export_group_local_detailing_payload_row_count,
        "mgt_export_group_local_detailing_payload_available_count": mgt_export_group_local_detailing_payload_available_count,
        "mgt_export_connection_detailing_payload_namespace_mode": mgt_export_connection_detailing_payload_namespace_mode,
        "mgt_export_connection_detailing_payload_group_local_namespace_present": mgt_export_connection_detailing_payload_group_local_namespace_present,
        "mgt_export_detailing_payload_namespace_mode": mgt_export_detailing_payload_namespace_mode,
        "mgt_export_detailing_payload_group_local_namespace_present": mgt_export_detailing_payload_group_local_namespace_present,
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": mgt_export_connection_detailing_structured_payload_mapped_change_count,
        "mgt_export_connection_detailing_direct_patch_eligible_change_count": mgt_export_connection_detailing_direct_patch_eligible_change_count,
        "mgt_export_detailing_direct_patch_eligible_change_count": mgt_export_detailing_direct_patch_eligible_change_count,
        "mgt_export_detailing_structured_payload_mapped_change_count": mgt_export_detailing_structured_payload_mapped_change_count,
        "mgt_export_connection_detailing_delivery_mode": mgt_export_connection_detailing_delivery_mode,
        "mgt_export_detailing_delivery_mode": mgt_export_detailing_delivery_mode,
        "mgt_export_rebar_payload_namespace_mode": mgt_export_rebar_payload_namespace_mode,
        "mgt_export_rebar_payload_material_level_namespace_present": mgt_export_rebar_payload_material_level_namespace_present,
        "mgt_export_rebar_payload_group_local_namespace_present": mgt_export_rebar_payload_group_local_namespace_present,
        "mgt_export_rebar_direct_patch_eligible_change_count": mgt_export_rebar_direct_patch_eligible_change_count,
        "mgt_export_rebar_direct_patch_ineligible_reason_counts": mgt_export_rebar_direct_patch_ineligible_reason_counts,
        "mgt_export_rebar_direct_patch_ineligible_reason_label": mgt_export_rebar_direct_patch_ineligible_reason_label,
        "mgt_export_rebar_direct_patch_mapping_source_counts": mgt_export_rebar_direct_patch_mapping_source_counts,
        "mgt_export_rebar_direct_patch_mapping_source_label": mgt_export_rebar_direct_patch_mapping_source_label,
        "mgt_export_rebar_delivery_mode": mgt_export_rebar_delivery_mode,
        "mgt_export_evidence_model": mgt_export_evidence_model,
        "mgt_export_delivery_boundary": mgt_export_delivery_boundary,
        "mgt_export_instruction_sidecar_change_count": mgt_export_instruction_sidecar_change_count,
        "mgt_export_instruction_sidecar_action_family_counts": mgt_export_instruction_sidecar_action_family_counts,
        "mgt_export_instruction_sidecar_action_family_label": mgt_export_instruction_sidecar_action_family_label,
        "mgt_export_instruction_sidecar_audit_only_change_count": mgt_export_instruction_sidecar_audit_only_change_count,
        "mgt_export_instruction_sidecar_audit_only_action_family_counts": mgt_export_instruction_sidecar_audit_only_action_family_counts,
        "mgt_export_instruction_sidecar_audit_only_action_family_label": mgt_export_instruction_sidecar_audit_only_action_family_label,
        "mgt_export_instruction_sidecar_manual_input_change_count": mgt_export_instruction_sidecar_manual_input_change_count,
        "mgt_export_instruction_sidecar_manual_input_action_family_counts": mgt_export_instruction_sidecar_manual_input_action_family_counts,
        "mgt_export_instruction_sidecar_manual_input_action_family_label": mgt_export_instruction_sidecar_manual_input_action_family_label,
        "mgt_export_audit_review_manifest_change_count": mgt_export_audit_review_manifest_change_count,
        "mgt_export_audit_review_manifest_action_family_counts": mgt_export_audit_review_manifest_action_family_counts,
        "mgt_export_audit_review_manifest_action_family_label": mgt_export_audit_review_manifest_action_family_label,
        "mgt_export_audit_review_packet_count": mgt_export_audit_review_packet_count,
        "mgt_export_audit_review_packet_action_family_counts": mgt_export_audit_review_packet_action_family_counts,
        "mgt_export_audit_review_packet_action_family_label": mgt_export_audit_review_packet_action_family_label,
        "mgt_export_audit_review_packet_followup_type_counts": mgt_export_audit_review_packet_followup_type_counts,
        "mgt_export_audit_review_packet_followup_type_label": mgt_export_audit_review_packet_followup_type_label,
        "mgt_export_audit_review_packet_file_count": mgt_export_audit_review_packet_file_count,
        "mgt_export_audit_review_packet_file_action_family_counts": mgt_export_audit_review_packet_file_action_family_counts,
        "mgt_export_audit_review_packet_file_action_family_label": mgt_export_audit_review_packet_file_action_family_label,
        "mgt_export_audit_review_queue_item_count": mgt_export_audit_review_queue_item_count,
        "mgt_export_audit_review_queue_pending_count": mgt_export_audit_review_queue_pending_count,
        "mgt_export_audit_review_queue_acknowledged_count": mgt_export_audit_review_queue_acknowledged_count,
        "mgt_export_audit_review_queue_status_counts": mgt_export_audit_review_queue_status_counts,
        "mgt_export_audit_review_queue_status_label": mgt_export_audit_review_queue_status_label,
        "mgt_export_audit_review_queue_action_family_counts": mgt_export_audit_review_queue_action_family_counts,
        "mgt_export_audit_review_queue_action_family_label": mgt_export_audit_review_queue_action_family_label,
        "mgt_export_audit_review_followup_item_count": mgt_export_audit_review_followup_item_count,
        "mgt_export_audit_review_followup_open_item_count": mgt_export_audit_review_followup_open_item_count,
        "mgt_export_audit_review_followup_closed_item_count": mgt_export_audit_review_followup_closed_item_count,
        "mgt_export_audit_review_followup_action_counts": mgt_export_audit_review_followup_action_counts,
        "mgt_export_audit_review_followup_action_label": mgt_export_audit_review_followup_action_label,
        "mgt_export_audit_review_followup_owner_counts": mgt_export_audit_review_followup_owner_counts,
        "mgt_export_audit_review_followup_owner_label": mgt_export_audit_review_followup_owner_label,
        "mgt_export_audit_review_followup_review_owner_counts": mgt_export_audit_review_followup_review_owner_counts,
        "mgt_export_audit_review_followup_review_owner_label": mgt_export_audit_review_followup_review_owner_label,
        "mgt_export_audit_review_followup_status_counts": mgt_export_audit_review_followup_status_counts,
        "mgt_export_audit_review_followup_status_label": mgt_export_audit_review_followup_status_label,
        "mgt_export_audit_review_followup_sla_state_counts": mgt_export_audit_review_followup_sla_state_counts,
        "mgt_export_audit_review_followup_sla_state_label": mgt_export_audit_review_followup_sla_state_label,
        "mgt_export_audit_review_followup_age_bucket_counts": mgt_export_audit_review_followup_age_bucket_counts,
        "mgt_export_audit_review_followup_age_bucket_label": mgt_export_audit_review_followup_age_bucket_label,
        "mgt_export_audit_review_followup_overdue_item_count": mgt_export_audit_review_followup_overdue_item_count,
        "mgt_export_audit_review_followup_oldest_open_age_hours": mgt_export_audit_review_followup_oldest_open_age_hours,
        "mgt_export_audit_review_followup_oldest_open_packet_id": mgt_export_audit_review_followup_oldest_open_packet_id,
        "mgt_export_audit_review_followup_reference_time_utc": mgt_export_audit_review_followup_reference_time_utc,
        "mgt_export_audit_review_followup_sla_policy_label": mgt_export_audit_review_followup_sla_policy_label,
        "mgt_export_audit_review_followup_mode": mgt_export_audit_review_followup_mode,
        "mgt_export_audit_review_resolution_item_count": mgt_export_audit_review_resolution_item_count,
        "mgt_export_audit_review_resolution_file_count": mgt_export_audit_review_resolution_file_count,
        "mgt_export_audit_review_resolution_open_item_count": mgt_export_audit_review_resolution_open_item_count,
        "mgt_export_audit_review_resolution_closed_item_count": mgt_export_audit_review_resolution_closed_item_count,
        "mgt_export_audit_review_resolution_pending_item_count": mgt_export_audit_review_resolution_pending_item_count,
        "mgt_export_audit_review_resolution_open_revision_count": mgt_export_audit_review_resolution_open_revision_count,
        "mgt_export_audit_review_resolution_closed_packet_count": mgt_export_audit_review_resolution_closed_packet_count,
        "mgt_export_audit_review_resolution_action_counts": mgt_export_audit_review_resolution_action_counts,
        "mgt_export_audit_review_resolution_action_label": mgt_export_audit_review_resolution_action_label,
        "mgt_export_audit_review_resolution_owner_counts": mgt_export_audit_review_resolution_owner_counts,
        "mgt_export_audit_review_resolution_owner_label": mgt_export_audit_review_resolution_owner_label,
        "mgt_export_audit_review_resolution_status_counts": mgt_export_audit_review_resolution_status_counts,
        "mgt_export_audit_review_resolution_status_label": mgt_export_audit_review_resolution_status_label,
        "mgt_export_audit_review_resolution_mode": mgt_export_audit_review_resolution_mode,
        "mgt_export_instruction_sidecar_review_priority_counts": mgt_export_instruction_sidecar_review_priority_counts,
        "mgt_export_instruction_sidecar_review_priority_label": mgt_export_instruction_sidecar_review_priority_label,
        "mgt_export_instruction_sidecar_followup_type_counts": mgt_export_instruction_sidecar_followup_type_counts,
        "mgt_export_instruction_sidecar_followup_type_label": mgt_export_instruction_sidecar_followup_type_label,
        "mgt_export_patched_material_row_count": mgt_export_patched_material_row_count,
        "mgt_export_cloned_section_count": mgt_export_cloned_section_count,
        "mgt_export_cloned_thickness_count": mgt_export_cloned_thickness_count,
        "mgt_export_cloned_material_count": mgt_export_cloned_material_count,
        "mgt_export_retargeted_element_row_count": mgt_export_retargeted_element_row_count,
        "nightly_smoke_pass": bool(nightly_smoke.get("contract_pass", False)),
        "nightly_smoke_pass_rate": float(nightly_smoke_history_summary.get("pass_rate", 0.0) or 0.0),
        "nightly_smoke_trial_feasible_rate": float(nightly_smoke_history_summary.get("trial_feasible_rate", 0.0) or 0.0),
        "nightly_smoke_history_count": int(nightly_smoke_history_summary.get("count", 0) or 0),
        "nightly_smoke_strict_ready": bool(nightly_smoke_recommendation.get("strict_ready", False)),
        "nightly_smoke_strict_recommendation": str(nightly_smoke_recommendation.get("recommendation", "")),
    }

    observed_strengths = [
        {
            "title": "Nightly release chain is green",
            "evidence": "nightly release, CI, static validation, freeze, and promotion reports all passed in the latest rerun",
        },
        {
            "title": "Commercial-readiness gate is green",
            "evidence": (
                f"grade={comm_grade.get('label', 'unknown')}, "
                f"cases={int(comm_metrics.get('total_case_count', 0))}, "
                f"source_families={int(comm_metrics.get('source_family_count', 0))}, "
                f"hazards={int(comm_metrics.get('hazard_type_count', 0))}, "
                f"authoring_lane={str(native_authoring_release_surface.get('native_authoring_commercialization_status', 'missing'))}"
            ),
        },
        {
            "title": "Authority-track holdout validation is green",
            "evidence": (
                f"SAC={int(authority_summary.get('sac_case_count', 0))}, "
                f"NHERI={int(authority_summary.get('nheri_case_count', 0))}, "
                f"OpenSees={int(authority_summary.get('opensees_case_count', 0))}"
            ),
        },
        {
            "title": "OpenSees canonical breadth is surfaced beyond holdout-only coverage",
            "evidence": (
                f"families={int(opensees_canonical_breadth_summary.get('canonical_family_count', 0))}, "
                f"cases={int(opensees_canonical_breadth_summary.get('canonical_case_count', 0))}, "
                f"parser_ready={int(opensees_canonical_breadth_summary.get('standalone_parser_ready_case_count', 0))}"
            ),
        },
        {
            "title": "Non-seismic extensions are green",
            "evidence": "wind, SSI, damper, construction-sequence, flexible-diaphragm, and reproducibility/version-lock gates all passed",
        },
        {
            "title": "MIDAS parser preserves full structural topology",
            "evidence": (
                f"element_rows_total={int(midas_metrics.get('element_rows_total', 0))}, "
                f"element_rows_skipped={int(midas_metrics.get('element_rows_skipped', 0))}, "
                f"unknown_rows={int(midas_diag.get('unknown_row_total', 0))}"
            ),
        },
        {
            "title": "MIDAS load blocks now bind to semantic load cases",
            "evidence": (
                f"use_stld_blocks={midas_use_stld_block_count}, "
                f"semantic_cases={midas_semantic_load_case_count}, "
                f"semantic_combinations={midas_semantic_load_combination_count}, "
                f"bound_rows=nodal:{midas_bound_nodal_load_row_count}/selfweight:{midas_bound_selfweight_row_count}/pressure:{midas_bound_pressure_row_count}, "
                f"unbound_rows=nodal:{midas_unbound_nodal_load_row_count}/selfweight:{midas_unbound_selfweight_row_count}/pressure:{midas_unbound_pressure_row_count}"
            ),
        },
        {
            "title": "MIDAS exporter now emits bounded optimized patches",
            "evidence": (
                f"artifact_exists={mgt_export_artifact_exists}, "
                f"contract_pass={mgt_export_contract_pass}, "
                f"support_mode={mgt_export_support_mode}, "
                f"supported_changes={mgt_export_supported_change_count}, "
                f"unsupported_changes={mgt_export_unsupported_change_count}, "
                f"cloned_sections={mgt_export_cloned_section_count}, "
                f"cloned_thicknesses={mgt_export_cloned_thickness_count}, "
                f"retargeted_elements={mgt_export_retargeted_element_row_count}, "
                f"patched_section_scale_rows={mgt_export_patched_section_scale_row_count}, "
                f"patched_thickness_rows={mgt_export_patched_thickness_row_count}"
            ),
        } if mgt_export_artifact_exists else {
            "title": "MIDAS exporter artifact is still absent",
            "evidence": "optimized MIDAS write-back artifact has not been generated yet",
        },
        {
            "title": "Signed release registry is available",
            "evidence": (
                f"algorithm={release_registry_summary.get('signing_algorithm', 'unknown')}, "
                f"artifact_count={int(release_registry_summary.get('artifact_count', 0))}, "
                f"signature_verified={bool(release_registry_checks.get('signature_verified_pass', False))}, "
                f"project_pkg={int(release_registry_summary.get('project_registry_package_bytes', 0) or 0)}B, "
                f"project_approvals={int(release_registry_summary.get('project_registry_approval_count', 0) or 0)}"
            ),
        },
        {
            "title": "Native authoring commercialization lane is attached",
            "evidence": (
                f"status={str(native_authoring_release_surface.get('native_authoring_commercialization_status', 'missing'))}, "
                f"solver_pass={bool(native_authoring_release_surface.get('native_authoring_solver_session_pass', False))}, "
                f"meshes={int(native_authoring_release_surface.get('native_authoring_solver_session_mesh_request_count', 0) or 0)}, "
                f"cells={int(native_authoring_release_surface.get('native_authoring_solver_session_total_estimated_cells', 0) or 0)}, "
                f"combos={int(native_authoring_release_surface.get('native_authoring_solver_session_combo_count', 0) or 0)}, "
                f"ops_pass={bool(native_authoring_release_surface.get('native_authoring_ops_bundle_pass', False))}, "
                f"jobs={int(native_authoring_release_surface.get('native_authoring_ops_bundle_job_count', 0) or 0)}, "
                f"snapshots={int(native_authoring_release_surface.get('native_authoring_ops_bundle_snapshot_count', 0) or 0)}, "
                f"registry_artifacts={int(native_authoring_release_surface.get('native_authoring_ops_bundle_registry_artifact_count', 0) or 0)}, "
                f"registry_approvals={int(native_authoring_release_surface.get('native_authoring_ops_bundle_registry_approval_count', 0) or 0)}, "
                f"signature_verified={bool(native_authoring_release_surface.get('native_authoring_ops_bundle_signature_verified', False))}, "
                f"palette_families={int(native_authoring_release_surface.get('native_authoring_palette_family_count', 0) or 0)}, "
                f"active_families={int(native_authoring_release_surface.get('native_authoring_active_family_count', 0) or 0)}, "
                f"portfolio_projects={int(native_authoring_release_surface.get('native_authoring_portfolio_project_count', 0) or 0)}, "
                f"portfolio_unmatched={int(native_authoring_release_surface.get('native_authoring_portfolio_unmatched_input_count', 0) or 0)}, "
                f"portfolio_families={int(native_authoring_release_surface.get('native_authoring_portfolio_family_count', 0) or 0)}, "
                f"ready_families={int(native_authoring_release_surface.get('native_authoring_portfolio_ready_family_count', 0) or 0)}, "
                f"max_combos={int(native_authoring_release_surface.get('native_authoring_portfolio_max_solver_combo_count', 0) or 0)}, "
                f"max_mesh_requests={int(native_authoring_release_surface.get('native_authoring_portfolio_max_solver_mesh_request_count', 0) or 0)}, "
                f"family_status={str(native_authoring_release_surface.get('native_authoring_portfolio_family_status_label', '') or 'n/a')}, "
                f"tracks=attached:{bool(native_authoring_release_surface.get('native_authoring_family_tracks_attached', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_family_track_count', 0) or 0)},"
                f"ready={int(native_authoring_release_surface.get('native_authoring_family_track_ready_count', 0) or 0)},"
                f"max_combos={int(native_authoring_release_surface.get('native_authoring_family_track_max_solver_combo_count', 0) or 0)},"
                f"max_meshes={int(native_authoring_release_surface.get('native_authoring_family_track_max_solver_mesh_request_count', 0) or 0)}, "
                f"runtime_lane=attached:{bool(native_authoring_release_surface.get('native_authoring_runtime_submission_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_runtime_submission_ready', False))},"
                f"submissions={int(native_authoring_release_surface.get('native_authoring_runtime_submission_count', 0) or 0)},"
                f"writeback_ready={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_ready_count', 0) or 0)},"
                f"queue={int(native_authoring_release_surface.get('native_authoring_runtime_submission_queue_count', 0) or 0)}, "
                f"runtime_writeback_depth=attached:{bool(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_ready_family_count', 0) or 0)},"
                f"signature={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_signature_family_count', 0) or 0)},"
                f"repro={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_repro_family_count', 0) or 0)},"
                f"snapshot={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_snapshot_family_count', 0) or 0)},"
                f"queue_clear={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_queue_clear_family_count', 0) or 0)}, "
                f"local_runtime_depth=attached:{bool(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_family_count', 0) or 0)},"
                f"deep={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_ready_family_count', 0) or 0)},"
                f"targeted={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_targeted_family_count', 0) or 0)},"
                f"trace={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_trace_ready_family_count', 0) or 0)},"
                f"mesh={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_mesh_ready_family_count', 0) or 0)},"
                f"runtime={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_runtime_ready_family_count', 0) or 0)},"
                f"omitted={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_omitted_family_count', 0) or 0)}, "
                f"local_variant_trace=attached:{bool(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_family_count', 0) or 0)},"
                f"deep={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_ready_family_count', 0) or 0)},"
                f"targeted={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_targeted_family_count', 0) or 0)},"
                f"workspace_variant={int(native_authoring_release_surface.get('native_authoring_local_variant_workspace_variant_ready_family_count', 0) or 0)},"
                f"solver_variant={int(native_authoring_release_surface.get('native_authoring_local_variant_solver_variant_ready_family_count', 0) or 0)},"
                f"writeback_trace={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_ready_family_trace_count', 0) or 0)},"
                f"active_multi={int(native_authoring_release_surface.get('native_authoring_local_variant_active_multi_family_count', 0) or 0)},"
                f"combo_multi={int(native_authoring_release_surface.get('native_authoring_local_variant_combo_multi_family_count', 0) or 0)},"
                f"signed={int(native_authoring_release_surface.get('native_authoring_local_variant_signed_writeback_family_count', 0) or 0)},"
                f"omitted={int(native_authoring_release_surface.get('native_authoring_local_variant_trace_omitted_family_count', 0) or 0)}, "
                f"multi_project_runtime=attached:{bool(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_ready', False))},"
                f"projects={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_project_count', 0) or 0)},"
                f"project_families={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_project_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_full_count', 0) or 0)},"
                f"ready_projects={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_ready_project_count', 0) or 0)},"
                f"signature={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_signature_project_count', 0) or 0)},"
                f"repro={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_repro_project_count', 0) or 0)},"
                f"snapshot={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_snapshot_project_count', 0) or 0)},"
                f"queue_clear={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_queue_clear_project_count', 0) or 0)}, "
                f"solver_family_breadth=attached:{bool(native_authoring_release_surface.get('native_authoring_solver_family_breadth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_solver_family_breadth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_family_count', 0) or 0)},"
                f"broad_ready={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_ready_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_full_family_count', 0) or 0)},"
                f"mesh_broad={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_mesh_broad_family_count', 0) or 0)}, "
                f"writeback_breadth=attached:{bool(native_authoring_release_surface.get('native_authoring_writeback_breadth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_writeback_breadth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_family_count', 0) or 0)},"
                f"broad_ready={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_ready_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_full_family_count', 0) or 0)},"
                f"mesh_broad={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_mesh_broad_family_count', 0) or 0)}, "
                f"ops_service=attached:{bool(native_authoring_release_surface.get('project_ops_service_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('project_ops_service_ready', False))},"
                f"projects={int(native_authoring_release_surface.get('project_ops_service_project_count', 0) or 0)},"
                f"families={int(native_authoring_release_surface.get('project_ops_service_family_count', 0) or 0)},"
                f"endpoints={int(native_authoring_release_surface.get('project_ops_service_endpoint_count', 0) or 0)}"
            ),
        } if bool(native_authoring_release_surface.get("native_authoring_evidence_attached", False)) else {
            "title": "Native authoring commercialization lane evidence is still absent",
            "evidence": "native authoring solver-session and ops-bundle artifacts have not been attached to the release summary yet",
        },
        {
            "title": "External benchmark batch runner evidence is attached",
            "evidence": (
                f"contract_pass={external_benchmark_batch_job_contract_pass}, "
                f"jobs={external_benchmark_batch_job_count}, "
                f"completed={external_benchmark_batch_completed_count}, "
                f"failed={external_benchmark_batch_failed_count}, "
                f"reruns={external_benchmark_batch_rerun_count}"
            ),
        } if external_benchmark_batch_job_summary_line else {
            "title": "External benchmark batch runner evidence is still absent",
            "evidence": "committee surface has not attached an external benchmark batch-job report yet",
        },
        {
            "title": "Commercial workflow breadth surface is attached",
            "evidence": str(
                commercial_workflow_breadth_surface.get("commercial_workflow_breadth_evidence", "") or ""
            ),
        } if bool(
            commercial_workflow_breadth_surface.get("commercial_workflow_breadth_surface_attached", False)
        ) else {
            "title": "Commercial workflow breadth surface is still absent",
            "evidence": "commercial workflow breadth report has not been attached to the release summary yet",
        },
        {
            "title": "Design-optimization cost smoke probe is stable",
            "evidence": (
                f"reason={nightly_smoke.get('reason_code', 'n/a')}, "
                f"pass_rate={float(nightly_smoke_history_summary.get('pass_rate', 0.0) or 0.0):.2%}, "
                f"trial_feasible_rate={float(nightly_smoke_history_summary.get('trial_feasible_rate', 0.0) or 0.0):.2%}, "
                f"history_count={int(nightly_smoke_history_summary.get('count', 0) or 0)}, "
                f"strict_recommendation={nightly_smoke_recommendation.get('recommendation', 'n/a')}"
            ),
        },
    ]

    mgt_export_native_authoring_closed = mgt_export_support_mode in {"full", "native_authoring_supported_changeset"}

    remaining_gaps = [
        {
            "id": "GAP-P0-000",
            "severity": "P0",
            "status": "open" if not mgt_export_contract_pass else ("closed" if mgt_export_native_authoring_closed else "narrowing"),
            "title": "MIDAS MGT exporter is still only a bounded subset",
            "why": "The release can now emit an optimized .mgt write-back artifact, but the exporter still only supports a bounded patch subset rather than full office-safe write-back across every design-change family.",
            "evidence": (
                f"midas_conversion_pass={_pass(midas)}, "
                f"semantic_load_binding_pass={midas_semantic_load_binding_pass}, "
                f"optimized_mgt_export_exists={mgt_export_artifact_exists}, "
                f"export_contract_pass={mgt_export_contract_pass}, "
                f"support_mode={mgt_export_support_mode}, "
                f"supported_changes={mgt_export_supported_change_count}, "
                f"unsupported_changes={mgt_export_unsupported_change_count}, "
                f"cloned_sections={mgt_export_cloned_section_count}, "
                f"cloned_thicknesses={mgt_export_cloned_thickness_count}, "
                f"retargeted_elements={mgt_export_retargeted_element_row_count}, "
                f"design_opt_changes_json=implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json"
            ),
            "exit_criteria": "Extend the exporter from bounded patch subset to full design-change family support, including rebar/detailing write-back and office-safe round-trip validation.",
        },
        {
            "id": "GAP-P0-001",
            "severity": "P0",
            "status": hip_gap_status,
            "title": "Full solver HIP kernel coverage",
            "why": "The release proves HIP compilation and smoke execution, but it still does not prove that the main nonlinear frame, NDTHA, and track solve loops are fully running on production HIP kernels end-to-end.",
            "evidence": (
                f"hip backend kind={hip_backend.get('kind', 'unknown')}, "
                f"beam_kernel_pass={hip_checks.get('beam_kernel_pass', False)}, "
                f"solver_gpu_count={int(solver_hip_summary.get('gpu_solver_count', 0))}, "
                f"solver_contract_pass={_pass(solver_hip)}"
            ),
            "exit_criteria": "Add explicit solver-path reports proving nonlinear frame, NDTHA, and track LF kernels execute on HIP kernels rather than smoke-only or bridge-only paths.",
        },
        {
            "id": "GAP-P1-001",
            "severity": "P1",
            "status": breadth_gap_status,
            "title": "Public validation breadth is still limited",
            "why": "The current release is validated, but the public holdout and real-data breadth is still small to remove the residual 1-5% engineer and legacy-tool holdout boundary.",
            "evidence": (
                f"commercial cases={int(comm_metrics.get('total_case_count', 0))}, "
                f"source families={int(comm_metrics.get('source_family_count', 0))}, "
                f"SAC={int(authority_summary.get('sac_case_count', 0))}, "
                f"NHERI={int(authority_summary.get('nheri_case_count', 0))}, "
                f"quality_mgt_catalog_sources={int(quality_catalog_meta.get('source_count', 0))}, "
                f"quality_mgt_accepted={int(quality_summary.get('accepted_count', 0))}"
            ),
            "exit_criteria": "Expand the public and commercial-grade holdout corpus until the residual 1-5% holdout boundary becomes smaller and more explicit across topology and hazard families.",
        },
        {
            "id": "GAP-P1-002",
            "severity": "P1",
            "status": midas_gap_status,
            "title": "MIDAS parser coverage remains partial",
            "why": "The MGT parser now handles shell-beam mix, rigid-link coarsening, and semantic load-case binding for USE-STLD/CONLOAD/SELFWEIGHT/PRESSURE, but many sections are still preserved as raw text rather than fully typed runtime data.",
            "evidence": (
                f"typed rows={int(midas_diag.get('typed_row_total', 0))}, "
                f"unknown sections={int(midas_diag.get('unknown_section_count', 0))}, "
                f"unknown rows={int(midas_diag.get('unknown_row_total', 0))}, "
                f"element rows skipped={int(midas_metrics.get('element_rows_skipped', 0))}, "
                f"use_stld_blocks={midas_use_stld_block_count}, "
                f"semantic_load_case_count={midas_semantic_load_case_count}, "
                f"pressure rows typed={int(midas_metrics.get('pressure_load_row_count', 0))}"
            ),
            "exit_criteria": "Reduce unknown-section volume substantially and convert high-impact sections such as dynamic loads, boundary groups, member metadata, and exporter-critical write-back fields into typed runtime data.",
        },
        {
            "id": "GAP-P1-003",
            "severity": "P1",
            "status": rc_gap_status,
            "title": "RC/composite constitutive fidelity is not benchmark-locked yet",
            "why": "Construction-stage behavior is now captured at the gate level, but creep/shrinkage and diaphragm effects are still validated through reduced-order structural proxies rather than dedicated RC crack/bond-slip benchmark suites.",
            "evidence": (
                f"construction max differential shortening={_finite(construction_summary.get('max_differential_shortening_mm')):.3f} mm, "
                f"max initial stress={_finite(construction_summary.get('max_initial_stress_mpa')):.3f} MPa, "
                f"diaphragm flex amplification max={_finite(diaphragm_summary.get('flex_amplification_max')):.3f}, "
                f"rc_benchmark_cases={int(rc_summary.get('case_count', 0))}, "
                f"authority_cases={int(rc_summary.get('authority_case_count', 0))}, "
                f"validation_mode={rc_summary.get('validation_mode', 'unknown')}"
            ),
            "exit_criteria": "Add dedicated RC and composite benchmark datasets covering cracking, bond-slip, creep, and slab failure modes, then promote those to first-class release gates.",
        },
        {
            "id": "GAP-P0-002",
            "severity": "P0",
            "status": "closed" if pbd_dynamic_hinge_refresh_ready else "open",
            "title": "PBD hinge properties are not dynamically refreshed",
            "why": "Optimized section/rebar changes must re-derive nonlinear hinge properties; the current release still presents hinge proxy views rather than an explicit refreshed hinge-state artifact.",
            "evidence": advanced_holdouts[0]["evidence"],
            "exit_criteria": "Attach a release artifact proving member-local FEMA/ASCE41 hinge properties are recalculated after section/rebar changes and consumed by NDTHA/PBD review.",
        },
        {
            "id": "GAP-P0-003",
            "severity": "P0",
            "status": (
                "closed"
                if panel_zone_3d_clash_ready
                and panel_zone_external_validation_status_label == "verified"
                else "open"
            ),
            "status_label": panel_zone_status_label,
            "advisory_only": bool(panel_zone_advisory_only),
            "release_blocking": bool(panel_zone_release_blocking),
            "title": "Panel-zone solver-verified external closure is not attached yet",
            "why": (
                "Current constructability gating now carries validated panel-zone joint, anchorage, and clash coverage, "
                "but the remaining local boundary is still exact solver-verified closure rather than scalar or topology-only evidence."
            ),
            "evidence": advanced_holdouts[1]["evidence"],
            "exit_criteria": (
                "Attach solver-verified exact panel-zone evidence for the same required sources, then consume it into the "
                "release chain so the gap closes from validated fallback coverage to verified exact closure."
            ),
        },
        {
            "id": "GAP-P1-004",
            "severity": "P1",
            "status": "closed" if foundation_optimization_ready else "open",
            "title": "Foundation and pile optimization are not active in the release loop",
            "why": "Upper-structure VE is active, but the current optimization dataset/state still does not prove mat foundation, pile, or SSI-coupled foundation optimization in the release path.",
            "evidence": advanced_holdouts[2]["evidence"],
            "exit_criteria": "Promote foundation member families into the active optimization dataset and attach a green mat/pile optimization report to the release chain.",
        },
        {
            "id": "GAP-P1-005",
            "severity": "P1",
            "status": "closed" if wind_raw_mapping_ready else "open",
            "title": "Raw wind-tunnel HFFB mapping is not yet verified",
            "why": "Semantic pressure binding exists, but the current release does not prove authority-grade ingestion of external wind-tunnel raw data and node/floor mapping.",
            "evidence": advanced_holdouts[3]["evidence"],
            "exit_criteria": "Attach a green raw wind-tunnel mapping artifact proving HFFB raw data is mapped into node/floor pressures without manual preprocessing.",
        },
        {
            "id": "GAP-P1-006",
            "severity": "P1",
            "status": native_authoring_gap_status,
            "title": "Native authoring commercialization lane is not packaged end-to-end",
            "why": (
                "Commercialization now needs a native authoring lane that proves the authored workspace can be turned "
                "into a solver session and a signed ops bundle, not just exported through the bounded MIDAS patch lane."
            ),
            "evidence": (
                f"commercialization_status={str(native_authoring_release_surface.get('native_authoring_commercialization_status', 'missing'))}, "
                f"solver_session_pass={bool(native_authoring_release_surface.get('native_authoring_solver_session_pass', False))}, "
                f"solver_authoring_ready={bool(native_authoring_release_surface.get('native_authoring_solver_session_authoring_ready', False))}, "
                f"solver_meshes={int(native_authoring_release_surface.get('native_authoring_solver_session_mesh_request_count', 0) or 0)}, "
                f"solver_cells={int(native_authoring_release_surface.get('native_authoring_solver_session_total_estimated_cells', 0) or 0)}, "
                f"solver_combos={int(native_authoring_release_surface.get('native_authoring_solver_session_combo_count', 0) or 0)}, "
                f"ops_bundle_pass={bool(native_authoring_release_surface.get('native_authoring_ops_bundle_pass', False))}, "
                f"workspace_ready={bool(native_authoring_release_surface.get('native_authoring_ops_bundle_workspace_ready_pass', False))}, "
                f"jobs={int(native_authoring_release_surface.get('native_authoring_ops_bundle_job_count', 0) or 0)}, "
                f"snapshots={int(native_authoring_release_surface.get('native_authoring_ops_bundle_snapshot_count', 0) or 0)}, "
                f"registry_artifacts={int(native_authoring_release_surface.get('native_authoring_ops_bundle_registry_artifact_count', 0) or 0)}, "
                f"registry_approvals={int(native_authoring_release_surface.get('native_authoring_ops_bundle_registry_approval_count', 0) or 0)}, "
                f"registry_signature_verified={bool(native_authoring_release_surface.get('native_authoring_ops_bundle_signature_verified', False))}, "
                f"palette_families={int(native_authoring_release_surface.get('native_authoring_palette_family_count', 0) or 0)}, "
                f"palette_family_label={str(native_authoring_release_surface.get('native_authoring_palette_family_label', '') or 'n/a')}, "
                f"active_families={int(native_authoring_release_surface.get('native_authoring_active_family_count', 0) or 0)}, "
                f"active_family_label={str(native_authoring_release_surface.get('native_authoring_active_family_label', '') or 'n/a')}, "
                f"member_types={str(native_authoring_release_surface.get('native_authoring_member_type_label', '') or 'n/a')}, "
                f"portfolio_projects={int(native_authoring_release_surface.get('native_authoring_portfolio_project_count', 0) or 0)}, "
                f"portfolio_complete={int(native_authoring_release_surface.get('native_authoring_portfolio_complete_project_count', 0) or 0)}, "
                f"portfolio_signature={int(native_authoring_release_surface.get('native_authoring_portfolio_signature_verified_count', 0) or 0)}, "
                f"portfolio_unmatched={int(native_authoring_release_surface.get('native_authoring_portfolio_unmatched_input_count', 0) or 0)}, "
                f"portfolio_families={int(native_authoring_release_surface.get('native_authoring_portfolio_family_count', 0) or 0)}, "
                f"ready_families={int(native_authoring_release_surface.get('native_authoring_portfolio_ready_family_count', 0) or 0)}, "
                f"max_combos={int(native_authoring_release_surface.get('native_authoring_portfolio_max_solver_combo_count', 0) or 0)}, "
                f"max_mesh_requests={int(native_authoring_release_surface.get('native_authoring_portfolio_max_solver_mesh_request_count', 0) or 0)}, "
                f"family_status={str(native_authoring_release_surface.get('native_authoring_portfolio_family_status_label', '') or 'n/a')}, "
                f"tracks=attached:{bool(native_authoring_release_surface.get('native_authoring_family_tracks_attached', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_family_track_count', 0) or 0)},"
                f"ready={int(native_authoring_release_surface.get('native_authoring_family_track_ready_count', 0) or 0)},"
                f"max_combos={int(native_authoring_release_surface.get('native_authoring_family_track_max_solver_combo_count', 0) or 0)},"
                f"max_meshes={int(native_authoring_release_surface.get('native_authoring_family_track_max_solver_mesh_request_count', 0) or 0)}, "
                f"runtime_lane=attached:{bool(native_authoring_release_surface.get('native_authoring_runtime_submission_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_runtime_submission_ready', False))},"
                f"submissions={int(native_authoring_release_surface.get('native_authoring_runtime_submission_count', 0) or 0)},"
                f"writeback_ready={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_ready_count', 0) or 0)},"
                f"queue={int(native_authoring_release_surface.get('native_authoring_runtime_submission_queue_count', 0) or 0)}, "
                f"runtime_writeback_depth=attached:{bool(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_ready_family_count', 0) or 0)},"
                f"signature={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_signature_family_count', 0) or 0)},"
                f"repro={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_repro_family_count', 0) or 0)},"
                f"snapshot={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_snapshot_family_count', 0) or 0)},"
                f"queue_clear={int(native_authoring_release_surface.get('native_authoring_runtime_writeback_depth_queue_clear_family_count', 0) or 0)}, "
                f"local_runtime_depth=attached:{bool(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_family_count', 0) or 0)},"
                f"deep={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_ready_family_count', 0) or 0)},"
                f"targeted={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_targeted_family_count', 0) or 0)},"
                f"trace={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_trace_ready_family_count', 0) or 0)},"
                f"mesh={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_mesh_ready_family_count', 0) or 0)},"
                f"runtime={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_runtime_ready_family_count', 0) or 0)},"
                f"omitted={int(native_authoring_release_surface.get('native_authoring_local_runtime_scenario_depth_omitted_family_count', 0) or 0)}, "
                f"local_variant_trace=attached:{bool(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_family_count', 0) or 0)},"
                f"deep={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_ready_family_count', 0) or 0)},"
                f"targeted={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_targeted_family_count', 0) or 0)},"
                f"workspace_variant={int(native_authoring_release_surface.get('native_authoring_local_variant_workspace_variant_ready_family_count', 0) or 0)},"
                f"solver_variant={int(native_authoring_release_surface.get('native_authoring_local_variant_solver_variant_ready_family_count', 0) or 0)},"
                f"writeback_trace={int(native_authoring_release_surface.get('native_authoring_local_variant_writeback_trace_ready_family_trace_count', 0) or 0)},"
                f"active_multi={int(native_authoring_release_surface.get('native_authoring_local_variant_active_multi_family_count', 0) or 0)},"
                f"combo_multi={int(native_authoring_release_surface.get('native_authoring_local_variant_combo_multi_family_count', 0) or 0)},"
                f"signed={int(native_authoring_release_surface.get('native_authoring_local_variant_signed_writeback_family_count', 0) or 0)},"
                f"omitted={int(native_authoring_release_surface.get('native_authoring_local_variant_trace_omitted_family_count', 0) or 0)}, "
                f"multi_project_runtime=attached:{bool(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_ready', False))},"
                f"projects={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_project_count', 0) or 0)},"
                f"project_families={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_project_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_full_count', 0) or 0)},"
                f"ready_projects={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_ready_project_count', 0) or 0)},"
                f"signature={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_signature_project_count', 0) or 0)},"
                f"repro={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_repro_project_count', 0) or 0)},"
                f"snapshot={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_snapshot_project_count', 0) or 0)},"
                f"queue_clear={int(native_authoring_release_surface.get('native_authoring_multi_project_runtime_writeback_queue_clear_project_count', 0) or 0)}, "
                f"solver_family_breadth=attached:{bool(native_authoring_release_surface.get('native_authoring_solver_family_breadth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_solver_family_breadth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_family_count', 0) or 0)},"
                f"broad_ready={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_ready_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_full_family_count', 0) or 0)},"
                f"mesh_broad={int(native_authoring_release_surface.get('native_authoring_solver_family_breadth_mesh_broad_family_count', 0) or 0)}, "
                f"writeback_breadth=attached:{bool(native_authoring_release_surface.get('native_authoring_writeback_breadth_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('native_authoring_writeback_breadth_ready', False))},"
                f"families={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_family_count', 0) or 0)},"
                f"broad_ready={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_ready_family_count', 0) or 0)},"
                f"full={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_full_family_count', 0) or 0)},"
                f"mesh_broad={int(native_authoring_release_surface.get('native_authoring_writeback_breadth_mesh_broad_family_count', 0) or 0)}, "
                f"ops_service=attached:{bool(native_authoring_release_surface.get('project_ops_service_attached', False))},"
                f"ready={bool(native_authoring_release_surface.get('project_ops_service_ready', False))},"
                f"projects={int(native_authoring_release_surface.get('project_ops_service_project_count', 0) or 0)},"
                f"families={int(native_authoring_release_surface.get('project_ops_service_family_count', 0) or 0)},"
                f"endpoints={int(native_authoring_release_surface.get('project_ops_service_endpoint_count', 0) or 0)}"
            ),
            "exit_criteria": (
                "Attach deterministic native authoring solver-session and signed ops-bundle artifacts, then consume "
                "their job/snapshot/registry evidence into the release summary so the commercialization lane is closed."
            ),
        },
        *(
            [
                {
                    "id": "GAP-P1-007",
                    "severity": "P1",
                    "status": str(
                        commercial_workflow_breadth_surface.get(
                            "commercial_workflow_breadth_gap_status",
                            "open",
                        )
                        or "open"
                    ),
                    "title": "Commercial workflow breadth is not fully surfaced across release/viewer/workbench",
                    "why": (
                        "Top-level release gap counts can read as closed while commercialization breadth still needs "
                        "explicit construction-stage, rail/tunnel serviceability and maintenance, and design redesign-loop "
                        "surfaces that reviewers can inspect directly."
                    ),
                    "evidence": str(
                        commercial_workflow_breadth_surface.get(
                            "commercial_workflow_breadth_evidence",
                            "",
                        )
                        or ""
                    ),
                    "exit_criteria": (
                        "Keep the commercial workflow breadth artifact green and surface construction-stage history/"
                        "shortening, rail/tunnel serviceability plus maintenance actions, and design report "
                        "traceability/optimizer/governing-clause breadth directly in release-facing summaries."
                    ),
                }
            ]
            if bool(
                commercial_workflow_breadth_surface.get(
                    "commercial_workflow_breadth_surface_attached",
                    False,
                )
            )
            else []
        ),
        {
            "id": "GAP-P2-001",
            "severity": "P2",
            "status": kds_gap_status,
            "title": "Code-check coverage is still narrow",
            "why": "The KDS package is green, but it currently represents a focused compliance slice rather than a broad multi-code production rule engine.",
            "evidence": (
                f"KDS summary cards={int(kds_summary.get('summary_card_count', 0))}, "
                f"compliance rows={int(kds_summary.get('compliance_row_count', 0))}, "
                f"member check rows={int(kds_summary.get('member_check_row_count', 0))}, "
                f"clauses={int(kds_summary.get('clause_count', 0))}, "
                f"member types={int(kds_summary.get('member_type_count', 0))}"
            ),
            "exit_criteria": "Expand post-processing to broader design-code families, more member types, more combinations, and deeper governing-clause traceability.",
        },
        {
            "id": "GAP-P2-002",
            "severity": "P2",
            "status": registry_gap_status,
            "title": "Reproducibility is locked, but governance is still local",
            "why": "Version-lock artifacts must be bound to a signed release registry so model binaries, parser provenance, and artifact hashes stay legally reproducible.",
            "evidence": (
                f"replay runs={int(repro_summary.get('replay_runs', 0))}, "
                f"seed={int(repro_summary.get('seed', 0))}, "
                f"lock manifest written={repro.get('checks', {}).get('lock_manifest_written', False)}, "
                f"registry_artifacts={int(release_registry_summary.get('artifact_count', 0))}, "
                f"signature_verified={bool(release_registry_checks.get('signature_verified_pass', False))}, "
                f"project_registry_artifacts={int(release_registry_summary.get('project_registry_artifact_count', 0) or 0)}, "
                f"project_registry_package_bytes={int(release_registry_summary.get('project_registry_package_bytes', 0) or 0)}, "
                f"project_registry_approvals={int(release_registry_summary.get('project_registry_approval_count', 0) or 0)}, "
                f"pubkey={release_registry_signature.get('public_key_path', '')}"
            ),
            "exit_criteria": "Promote the version-lock manifest into a signed release registry tied to model binaries, parser versions, and package provenance.",
        },
    ]

    open_p0 = sum(1 for gap in remaining_gaps if gap["severity"] == "P0" and gap["status"] != "closed")
    open_p1 = sum(1 for gap in remaining_gaps if gap["severity"] == "P1" and gap["status"] != "closed")
    open_p2 = sum(1 for gap in remaining_gaps if gap["severity"] == "P2" and gap["status"] != "closed")

    core_release_keys = [
        "nightly_release_pass",
        "ci_gate_pass",
        "static_validation_pass",
        "freeze_snapshot_pass",
        "promotion_pass",
        "commercial_readiness_pass",
        "global_authority_pass",
        "hip_kernel_smoke_pass",
        "midas_conversion_pass",
        "construction_sequence_pass",
        "flexible_diaphragm_pass",
        "repro_version_lock_pass",
        "release_registry_pass",
        "kds_compliance_pass",
        "solver_hip_e2e_pass",
        "rc_benchmark_lock_pass",
        "quality_mgt_corpus_pass",
    ]
    release_candidate_pass = all(bool(release_status.get(k, False)) for k in core_release_keys)
    accelerated_coverage_target_pct_range = deployment_model.get("accelerated_coverage_target_pct_range", [95, 99])
    residual_holdout_target_pct_range = deployment_model.get("residual_holdout_target_pct_range", [1, 5])
    commercial_grade_label = _commercial_grade_label(comm_grade.get("label", "unknown"))
    commercial_scope_summary_line = _commercial_scope_summary_line(
        grade_label=commercial_grade_label,
        deployment_model=deployment_model,
        accelerated_coverage_target_pct_range=accelerated_coverage_target_pct_range,
        residual_holdout_target_pct_range=residual_holdout_target_pct_range,
    )
    commercial_reliability_breadth_summary_line = _commercial_reliability_breadth_summary_line(
        grade_label=commercial_grade_label,
        exact_row_count=midas_kds_row_provenance_export_exact_row_count,
        total_row_count=midas_kds_row_provenance_export_row_count,
        evidence_row_count=midas_kds_row_provenance_preview_row_count,
    )
    current_deployment_model = str(deployment_model.get("mode", ""))
    current_strict_design_opt_cost_smoke = _nightly_strict_design_opt_cost_smoke(nightly)
    empirical_time_saved = _empirical_time_saved_summary(
        nightly_smoke_history,
        accelerated_coverage_target_pct_range,
    )
    measured_chain_timing = _measured_chain_timing_summary(nightly)
    rolling_measured_chain = _rolling_measured_chain_summary(
        Path(args.nightly_release),
        nightly,
        history_root=Path(args.nightly_history_root),
        limit=int(args.nightly_history_limit),
        current_deployment_model=current_deployment_model,
        current_strict_design_opt_cost_smoke=current_strict_design_opt_cost_smoke,
        fallback_commercial_readiness_path=Path(args.commercial_readiness),
    )
    authority_catalog_diff = (
        committee_summary.get("authority_catalog_routing_diff")
        if isinstance(committee_summary.get("authority_catalog_routing_diff"), dict)
        else {}
    )
    authority_catalog_warning_active = int(authority_catalog_diff.get("change_count", 0) or 0) > 0
    residual_holdout_breakdown = _build_holdout_breakdown(
        residual_holdout_target_pct_range,
        [row for row in residual_holdout_categories if isinstance(row, dict)],
    )
    residual_holdout_work_items = _build_holdout_work_items(residual_holdout_breakdown)

    summary = {
        "release_candidate_pass": release_candidate_pass,
        "commercial_grade": commercial_grade_label,
        "commercial_scope_summary_line": commercial_scope_summary_line,
        "commercial_reliability_breadth_summary_line": commercial_reliability_breadth_summary_line,
        "residual_holdout_work_item_count": len(residual_holdout_work_items),
        "deployment_model": str(deployment_model.get("mode", "engineer_in_the_loop_accelerated_coverage")),
        "midas_section_library_summary_line": midas_section_library_summary_line,
        "midas_kds_geometry_bridge_summary_line": midas_kds_geometry_bridge_summary_line,
        "midas_kds_geometry_bridge_load_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_load_crosswalk_count": int(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_load_crosswalk_expected": int(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_load_crosswalk_status": str(
            midas_kds_geometry_bridge_load_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_load_crosswalk_pass": midas_kds_geometry_bridge_load_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_count": int(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_expected": int(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_status": str(
            midas_kds_geometry_bridge_semantic_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_pass": midas_kds_geometry_bridge_semantic_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_count": int(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_status": str(
            midas_kds_geometry_bridge_full_member_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_pass": midas_kds_geometry_bridge_full_member_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_count": int(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_status": str(
            midas_kds_geometry_bridge_full_section_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_pass": midas_kds_geometry_bridge_full_section_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": str(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("summary_line", "") or ""
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_count": int(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("count", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_expected": int(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("expected", 0) or 0
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_status": str(
            midas_kds_geometry_bridge_full_load_crosswalk_surface.get("status", "") or ""
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_pass": midas_kds_geometry_bridge_full_load_crosswalk_surface.get(
            "pass"
        ),
        "midas_kds_geometry_bridge_full_crosswalk_depth": int(midas_kds_geometry_bridge_full_crosswalk_depth),
        "midas_loadcomb_roundtrip_summary_line": midas_loadcomb_roundtrip_summary_line,
        "commercial_benchmark_breadth_summary_line": commercial_benchmark_breadth_summary_line,
        "measured_benchmark_breadth_summary_line": measured_benchmark_breadth_summary_line,
        "peer_blind_prediction_compare_summary_line": str(
            peer_blind_prediction_compare_surface.get("summary_line", "") or ""
        ),
        "peer_blind_prediction_compare_pass": bool(
            peer_blind_prediction_compare_surface.get("contract_pass", False)
        ),
        "peer_blind_prediction_compare_case_count": int(
            peer_blind_prediction_compare_surface.get("case_count", 0) or 0
        ),
        "peer_blind_prediction_compare_build_case_count": int(
            peer_blind_prediction_compare_surface.get("build_case_count", 0) or 0
        ),
        "peer_blind_prediction_compare_measured_response_ready": bool(
            peer_blind_prediction_compare_surface.get("measured_response_ready", False)
        ),
        "peer_blind_prediction_compare_acceleration_channel_count": int(
            peer_blind_prediction_compare_surface.get("acceleration_channel_count", 0) or 0
        ),
        "peer_blind_prediction_compare_drift_channel_count": int(
            peer_blind_prediction_compare_surface.get("drift_channel_count", 0) or 0
        ),
        "peer_blind_prediction_compare_channel_count": int(
            peer_blind_prediction_compare_surface.get("channel_count", 0) or 0
        ),
        "peer_blind_prediction_compare_entry_kind": str(
            peer_blind_prediction_compare_surface.get("entry_kind", "") or ""
        ),
        "peer_blind_prediction_compare_entry_label": str(
            peer_blind_prediction_compare_surface.get("entry_label", "") or ""
        ),
        "peer_blind_prediction_compare_source_family": str(
            peer_blind_prediction_compare_surface.get("source_family", "") or ""
        ),
        "peer_blind_prediction_compare_summary_label": str(
            peer_blind_prediction_compare_surface.get("summary_label", "") or ""
        ),
        "peer_blind_prediction_compare_reason_code": str(
            peer_blind_prediction_compare_surface.get("reason_code", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_summary_line": str(
            peer_blind_prediction_measured_response_landing_surface.get("summary_line", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_pass": bool(
            peer_blind_prediction_measured_response_landing_surface.get("contract_pass", False)
        ),
        "peer_blind_prediction_measured_response_landing_state": str(
            peer_blind_prediction_measured_response_landing_surface.get("landing_state", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_matched_file_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("matched_file_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_csv_file_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("csv_file_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_acceleration_candidate_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("acceleration_candidate_count", 0)
            or 0
        ),
        "peer_blind_prediction_measured_response_landing_drift_candidate_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("drift_candidate_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_sensor_candidate_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("sensor_candidate_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_expected_pattern_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("expected_pattern_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_required_group_pass_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("required_group_pass_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_required_group_count": int(
            peer_blind_prediction_measured_response_landing_surface.get("required_group_count", 0) or 0
        ),
        "peer_blind_prediction_measured_response_landing_root_name": str(
            peer_blind_prediction_measured_response_landing_surface.get("root_name", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_next_action": str(
            peer_blind_prediction_measured_response_landing_surface.get("next_action", "") or ""
        ),
        "peer_blind_prediction_measured_response_landing_reason_code": str(
            peer_blind_prediction_measured_response_landing_surface.get("reason_code", "") or ""
        ),
        "project_registry_artifact_count": int(
            release_registry_summary.get("project_registry_artifact_count", 0) or 0
        ),
        "project_registry_approval_count": int(
            release_registry_summary.get("project_registry_approval_count", 0) or 0
        ),
        "project_registry_package_sha256": str(
            release_registry_summary.get("project_registry_package_sha256", "") or ""
        ),
        "project_registry_package_bytes": int(
            release_registry_summary.get("project_registry_package_bytes", 0) or 0
        ),
        "project_registry_signature_verified": bool(
            release_registry_checks.get("project_registry_signature_verified_pass", False)
        ),
        "external_benchmark_batch_job_summary_line": external_benchmark_batch_job_summary_line,
        "external_benchmark_batch_job_contract_pass": external_benchmark_batch_job_contract_pass,
        "external_benchmark_batch_job_count": external_benchmark_batch_job_count,
        "external_benchmark_batch_completed_count": external_benchmark_batch_completed_count,
        "external_benchmark_batch_failed_count": external_benchmark_batch_failed_count,
        "external_benchmark_batch_rerun_count": external_benchmark_batch_rerun_count,
        "external_benchmark_submission_summary_line": committee_external_benchmark_submission_summary_line,
        "external_benchmark_submission_recommended_start_mode": committee_external_benchmark_submission_recommended_start_mode,
        "external_benchmark_submission_recommended_submission_scope": committee_external_benchmark_submission_recommended_submission_scope,
        "external_benchmark_submission_blocker_label": committee_external_benchmark_submission_blocker_label,
        "external_benchmark_submission_caution_label": committee_external_benchmark_submission_caution_label,
        "external_benchmark_submission_queue_count": committee_external_benchmark_submission_queue_count,
        "external_benchmark_submission_queue_ready_count": committee_external_benchmark_submission_queue_ready_count,
        "external_benchmark_submission_queue_review_pending_count": committee_external_benchmark_submission_queue_review_pending_count,
        "external_benchmark_submission_queue_blocked_count": committee_external_benchmark_submission_queue_blocked_count,
        "external_benchmark_submission_onepage_attestation_status": committee_external_benchmark_submission_onepage_attestation_status,
        "external_benchmark_submission_queue_rows": committee_external_benchmark_submission_queue_rows,
        "external_benchmark_submission_queue_rows_present": bool(committee_external_benchmark_submission_queue_rows),
        "baseline_measured_family_count": int(measured_benchmark_breadth_summary.get("baseline_measured_family_count", 0)),
        "baseline_measured_case_count": int(measured_benchmark_breadth_summary.get("baseline_measured_case_count", 0)),
        "opensees_incremental_family_count": int(
            measured_benchmark_breadth_summary.get("opensees_incremental_family_count", 0)
        ),
        "opensees_incremental_case_count": int(
            measured_benchmark_breadth_summary.get("opensees_incremental_case_count", 0)
        ),
        "authority_incremental_family_count": int(
            measured_benchmark_breadth_summary.get("authority_incremental_family_count", 0)
        ),
        "authority_incremental_case_count": int(
            measured_benchmark_breadth_summary.get("authority_incremental_case_count", 0)
        ),
        "external_incremental_family_count": int(
            measured_benchmark_breadth_summary.get("external_incremental_family_count", 0)
        ),
        "external_incremental_case_count": int(
            measured_benchmark_breadth_summary.get("external_incremental_case_count", 0)
        ),
        "opensees_parser_ready_case_count": int(
            measured_benchmark_breadth_summary.get("opensees_parser_ready_case_count", 0)
        ),
        "measured_benchmark_family_count": int(measured_benchmark_breadth_summary.get("measured_family_count", 0)),
        "measured_benchmark_case_count": int(measured_benchmark_breadth_summary.get("measured_case_count", 0)),
        "solver_breadth_summary_line": solver_breadth_summary_line,
        "element_material_breadth_summary_line": element_material_breadth_summary_line,
        "material_constitutive_summary_line": material_constitutive_summary_line,
        "material_constitutive_pass": material_constitutive_pass,
        "material_constitutive_calibration_matrix_pass_row_count": material_constitutive_calibration_matrix_pass_row_count,
        "material_constitutive_cyclic_library_reversal_count": material_constitutive_cyclic_library_reversal_count,
        "material_constitutive_bond_interface_cyclic_reversal_count": (
            material_constitutive_bond_interface_cyclic_reversal_count
        ),
        "steel_composite_constitutive_gate_summary_line": steel_composite_constitutive_gate_summary_line,
        "steel_composite_constitutive_gate_pass": steel_composite_constitutive_gate_pass,
        "midas_kds_row_provenance_export_summary_line": midas_kds_row_provenance_export_summary_line,
        "midas_kds_row_provenance_export_row_count": midas_kds_row_provenance_export_row_count,
        "midas_kds_row_provenance_export_exact_row_count": midas_kds_row_provenance_export_exact_row_count,
        "midas_kds_row_provenance_preview_row_count": midas_kds_row_provenance_preview_row_count,
        "midas_kds_row_provenance_preview_rows_present": midas_kds_row_provenance_preview_rows_present,
        "midas_kds_row_provenance_exact_row_coverage_label": midas_kds_row_provenance_exact_row_coverage_label,
        "midas_kds_row_provenance_preview_rows": midas_kds_row_provenance_preview_rows,
        "midas_kds_row_provenance_clause_filter_rows": midas_kds_row_provenance_clause_filter_rows,
        "midas_kds_row_provenance_member_filter_rows": midas_kds_row_provenance_member_filter_rows,
        "midas_kds_row_provenance_hazard_filter_rows": midas_kds_row_provenance_hazard_filter_rows,
        "midas_kds_row_provenance_rule_family_filter_rows": midas_kds_row_provenance_rule_family_filter_rows,
        "contact_readiness_summary_line": contact_readiness_summary_line,
        "foundation_soil_link_summary_line": foundation_soil_link_summary_line,
        "support_search_summary_line": support_search_summary_line,
        "support_search_count": int(support_search_surface.get("support_search_count", 0) or 0),
        "node_surface_proxy_count": int(support_search_surface.get("node_surface_proxy_count", 0) or 0),
        "support_depth_score": int(support_search_surface.get("support_depth_score", 0) or 0),
        "structural_contact_summary_line": structural_contact_summary_line,
        "general_fe_contact_matrix_summary_line": general_fe_contact_matrix_summary_line,
        "general_fe_contact_matrix_summary": general_fe_contact_matrix_summary,
        "surface_interaction_benchmark_summary_line": surface_interaction_benchmark_summary_line,
        "midas_interoperability_summary_line": midas_interoperability_summary_line,
        "midas_native_roundtrip_summary_line": midas_native_roundtrip_summary_line,
        **native_authoring_release_surface,
        "advanced_holdout_count": int(advanced_holdout_count),
        "advanced_holdout_ready_count": int(advanced_holdout_ready_count),
        "advanced_holdout_open_count": int(advanced_holdout_open_count),
        "advanced_holdout_status_label": advanced_holdout_status_label,
        "load_combination_engine_summary_line": load_combination_engine_summary_line,
        "load_combination_engine_pass": load_combination_engine_pass,
        "load_combination_engine_combo_count": load_combination_engine_combo_count,
        "load_combination_engine_family_count": load_combination_engine_family_count,
        "load_combination_engine_max_nested_depth": load_combination_engine_max_nested_depth,
        "load_combination_editor_commercialization_summary_line": load_combination_editor_commercialization_summary_line,
        "load_combination_editor_commercialization_pass": load_combination_editor_commercialization_pass,
        "load_combination_editor_required_target_match_label": load_combination_editor_required_target_match_label,
        "load_combination_editor_code_check_assembly_ready": load_combination_editor_code_check_assembly_ready,
        "load_combination_editor_commercialization_report_path": str(
            args.load_combination_editor_commercialization_report
        ),
        "reference_regression_summary_line": reference_regression_summary_line,
        "reference_regression_pass": reference_regression_pass,
        "reference_regression_case_count": reference_regression_case_count,
        "reference_regression_passing_case_count": reference_regression_passing_case_count,
        "reference_regression_metric_count": reference_regression_metric_count,
        "reference_regression_passing_metric_count": reference_regression_passing_metric_count,
        "reference_regression_report_path": str(args.reference_regression_report),
        "advanced_ssi_summary_line": advanced_ssi_summary_line,
        "advanced_ssi_pass": advanced_ssi_pass,
        "advanced_ssi_peak_transfer_ratio_max": advanced_ssi_peak_transfer_ratio_max,
        "advanced_ssi_peak_transfer_group_id": advanced_ssi_peak_transfer_group_id,
        "advanced_ssi_min_group_interaction_efficiency_ratio": advanced_ssi_group_efficiency_ratio,
        "wind_workflow_summary_line": wind_workflow_summary_line,
        "wind_workflow_pass": wind_workflow_pass,
        "wind_workflow_occupant_comfort_class": wind_workflow_comfort_class,
        "wind_workflow_occupant_comfort_crosswind_bias_ratio": wind_workflow_crosswind_bias_ratio,
        "midas_native_roundtrip_public_native_writeback_ready_count": int(
            release_status.get("midas_native_roundtrip_public_native_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_raw_native_writeback_ready_count": int(
            release_status.get("midas_native_roundtrip_public_raw_native_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_bridge_writeback_ready_count": int(
            release_status.get("midas_native_roundtrip_public_bridge_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_archive_preview_writeback_ready_count": int(
            release_status.get("midas_native_roundtrip_public_archive_preview_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count": int(
            release_status.get("midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_source_writeback_ready_count": int(
            release_status.get("midas_native_roundtrip_public_source_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_taxonomy_case_counts": release_status.get("midas_native_roundtrip_taxonomy_case_counts", {}),
        "midas_native_roundtrip_taxonomy_card_family_histogram": release_status.get(
            "midas_native_roundtrip_taxonomy_card_family_histogram", {}
        ),
        "midas_native_roundtrip_structure_type_batch_markdowns": release_status.get(
            "midas_native_roundtrip_structure_type_batch_markdowns", []
        ),
        "performance_profiling_summary_line": performance_profiling_summary_line,
        "ndtha_step_series_depth": int(ndtha_step_series_depth),
        "ndtha_material_summary_line": ndtha_material_summary_line,
        "ndtha_material_depth": int(ndtha_material_depth),
        "performance_profiling_detail_line": performance_profiling_detail_line,
        "solver_truthfulness_summary_line": solver_truthfulness_summary_line,
        "hardest_external_10case_kickoff_summary_line": hardest_external_10case_kickoff_summary_line,
        "nonlinear_generalization_summary_line": nonlinear_generalization_summary_line,
        "workflow_productization_summary_line": workflow_productization_summary_line,
        "workflow_contact_coupling_summary_line": workflow_contact_coupling_summary_line,
        "workflow_contact_coupling_summary": workflow_contact_coupling_summary,
        "workflow_contact_coupling_pass": bool(workflow_contact_coupling_surface.get("pass", False)),
        "workflow_contact_support_family_count": int(
            workflow_contact_coupling_surface.get("support_family_count", 0) or 0
        ),
        "workflow_contact_proxy_family_count": int(
            workflow_contact_coupling_surface.get("proxy_family_count", 0) or 0
        ),
        "workflow_contact_assembled_depth_value": int(
            workflow_contact_coupling_surface.get("assembled_depth_value", 0) or 0
        ),
        **commercial_workflow_breadth_surface,
        "korean_source_ingest_summary_line": korean_source_ingest_summary_line,
        "opensees_canonical_breadth_summary_line": opensees_canonical_breadth_summary_line,
        "korean_source_ingest_source_count": int(workflow_productization_summary.get("korean_source_ingest_source_count", 0) or 0),
        "korean_source_ingest_source_class_count": int(
            workflow_productization_summary.get("korean_source_ingest_source_class_count", 0) or 0
        ),
        "korean_source_ingest_collected_count": int(workflow_productization_summary.get("korean_source_ingest_collected_count", 0) or 0),
        "korean_source_ingest_metadata_only_count": int(
            workflow_productization_summary.get("korean_source_ingest_metadata_only_count", 0) or 0
        ),
        "korean_source_ingest_rejected_count": int(workflow_productization_summary.get("korean_source_ingest_rejected_count", 0) or 0),
        "korean_source_ingest_fingerprinted_count": int(
            workflow_productization_summary.get("korean_source_ingest_fingerprinted_count", 0) or 0
        ),
        "korean_source_ingest_duplicate_sha_group_count": int(
            workflow_productization_summary.get("korean_source_ingest_duplicate_sha_group_count", 0) or 0
        ),
        "korean_source_ingest_gate_report_path": str(
            workflow_productization_summary.get("korean_source_ingest_gate_report_path", "") or ""
        ),
        "korean_structural_preview_queue_summary_line": korean_structural_preview_queue_summary_line,
        "korean_structural_preview_queue_candidate_total": int(
            workflow_productization_summary.get("korean_structural_preview_queue_candidate_total", 0) or 0
        ),
        "korean_structural_preview_queue_pending_candidate_count": int(
            workflow_productization_summary.get("korean_structural_preview_queue_pending_candidate_count", 0) or 0
        ),
        "korean_structural_preview_queue_state": str(
            workflow_productization_summary.get("korean_structural_preview_queue_state", "") or ""
        ),
        "korean_structural_preview_promotion_queue_path": str(
            workflow_productization_summary.get("korean_structural_preview_promotion_queue_path", "") or ""
        ),
        "irregular_structure_summary_line": irregular_structure_summary_line,
        "irregular_structure_track_pass": bool(irregular_structure_summary.get("irregular_structure_track_pass", False)),
        "irregular_structure_family_count": int(irregular_structure_summary.get("irregular_structure_family_count", 0) or 0),
        "irregular_structure_source_record_count": int(
            irregular_structure_summary.get("irregular_structure_source_record_count", 0) or 0
        ),
        "irregular_structure_local_ready_count": int(irregular_structure_summary.get("irregular_structure_local_ready_count", 0) or 0),
        "irregular_structure_remote_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_remote_candidate_count", 0) or 0
        ),
        "irregular_structure_native_roundtrip_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_native_roundtrip_candidate_count", 0) or 0
        ),
        "irregular_structure_solver_benchmark_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_solver_benchmark_candidate_count", 0) or 0
        ),
        "irregular_structure_ai_learning_candidate_count": int(
            irregular_structure_summary.get("irregular_structure_ai_learning_candidate_count", 0) or 0
        ),
        "irregular_structure_top5_count": int(irregular_structure_summary.get("irregular_structure_top5_count", 0) or 0),
        "irregular_structure_top5_family_ids": list(irregular_structure_summary.get("irregular_structure_top5_family_ids", []) or []),
        "irregular_structure_gate_report_path": str(
            irregular_structure_artifacts.get("irregular_structure_gate_report_path", "") or ""
        ),
        "irregular_top5_execution_manifest_path": str(
            irregular_structure_artifacts.get("irregular_top5_execution_manifest_path", "") or ""
        ),
        "irregular_structure_source_catalog_path": str(
            irregular_structure_artifacts.get("irregular_source_catalog_path", "") or ""
        ),
        "irregular_priority_manifest_path": str(
            irregular_structure_artifacts.get("irregular_priority_manifest_path", "") or ""
        ),
        "irregular_structure_collection_report_path": str(
            irregular_structure_artifacts.get("irregular_collection_report_path", "") or ""
        ),
        "irregular_triage_report_path": str(irregular_structure_artifacts.get("irregular_triage_report_path", "") or ""),
        "commercial_readiness_summary_line": commercial_readiness_summary_line,
        "accelerated_coverage_target_pct_range": accelerated_coverage_target_pct_range,
        "residual_holdout_target_pct_range": residual_holdout_target_pct_range,
        "estimated_time_saved_pct_range": empirical_time_saved["estimated_time_saved_pct_range"],
        "estimated_time_saved_basis": empirical_time_saved["estimated_time_saved_basis"],
        "empirical_smoke_runtime_saved_pct_range": empirical_time_saved["empirical_smoke_runtime_saved_pct_range"],
        "empirical_smoke_runtime_saved_pct_mean": empirical_time_saved["empirical_smoke_runtime_saved_pct_mean"],
        "measured_chain_total_seconds": measured_chain_timing["measured_chain_total_seconds"],
        "measured_chain_total_minutes": measured_chain_timing["measured_chain_total_minutes"],
        "measured_chain_selected_step_count": measured_chain_timing["measured_chain_selected_step_count"],
        "measured_chain_category_seconds": measured_chain_timing["measured_chain_category_seconds"],
        "measured_chain_category_minutes": measured_chain_timing["measured_chain_category_minutes"],
        "measured_chain_rolling_sample_count": rolling_measured_chain["measured_chain_rolling_sample_count"],
        "measured_chain_rolling_total_minutes_range": rolling_measured_chain["measured_chain_rolling_total_minutes_range"],
        "measured_chain_rolling_total_minutes_mean": rolling_measured_chain["measured_chain_rolling_total_minutes_mean"],
        "measured_chain_rolling_total_minutes_first": rolling_measured_chain["measured_chain_rolling_total_minutes_first"],
        "measured_chain_rolling_total_minutes_last": rolling_measured_chain["measured_chain_rolling_total_minutes_last"],
        "measured_chain_rolling_total_minutes_drift": rolling_measured_chain["measured_chain_rolling_total_minutes_drift"],
        "measured_chain_rolling_category_minutes_mean": rolling_measured_chain["measured_chain_rolling_category_minutes_mean"],
        "measured_chain_full_chain_sample_count": rolling_measured_chain["measured_chain_full_chain_sample_count"],
        "measured_chain_comparable_sample_count": rolling_measured_chain["measured_chain_comparable_sample_count"],
        "measured_chain_comparable_reference_step_count": rolling_measured_chain["measured_chain_comparable_reference_step_count"],
        "measured_chain_comparable_overlap_threshold": rolling_measured_chain["measured_chain_comparable_overlap_threshold"],
        "measured_chain_comparable_reference_deployment_model": rolling_measured_chain["measured_chain_comparable_reference_deployment_model"],
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": rolling_measured_chain["measured_chain_comparable_reference_strict_design_opt_cost_smoke"],
        "measured_chain_rolling_selection_mode": rolling_measured_chain["measured_chain_rolling_selection_mode"],
        "engineer_in_loop_accelerated_coverage_ready": bool(deployment_model.get("engineer_in_loop_accelerated_coverage_ready", release_candidate_pass)),
        "time_saving_focus": str(
            deployment_model.get(
                "recommended_use",
                "Automate the dominant repeated analysis, screening, packaging, and optimization workload while preserving residual engineer holdout.",
            )
        ),
        "full_commercial_replacement_ready": bool(deployment_model.get("full_commercial_replacement_ready", False)),
        "midas_semantic_load_binding_pass": midas_semantic_load_binding_pass,
        "midas_use_stld_block_count": midas_use_stld_block_count,
        "midas_semantic_load_case_count": midas_semantic_load_case_count,
        "midas_semantic_load_combination_count": midas_semantic_load_combination_count,
        "midas_bound_nodal_load_row_count": midas_bound_nodal_load_row_count,
        "midas_bound_selfweight_row_count": midas_bound_selfweight_row_count,
        "midas_bound_pressure_row_count": midas_bound_pressure_row_count,
        "midas_unbound_nodal_load_row_count": midas_unbound_nodal_load_row_count,
        "midas_unbound_selfweight_row_count": midas_unbound_selfweight_row_count,
        "midas_unbound_pressure_row_count": midas_unbound_pressure_row_count,
        "midas_load_semantic_gap_status": midas_load_semantic_gap_status,
        "mgt_export_artifact_exists": mgt_export_artifact_exists,
        "mgt_export_contract_pass": mgt_export_contract_pass,
        "mgt_export_support_mode": mgt_export_support_mode,
        "mgt_export_loadcomb_preview_exists": mgt_export_loadcomb_preview_exists,
        "mgt_export_loadcomb_roundtrip_report_exists": mgt_export_loadcomb_roundtrip_report_exists,
        "mgt_export_loadcomb_roundtrip_pass": mgt_export_loadcomb_roundtrip_pass,
        "mgt_export_loadcomb_roundtrip_summary_line": mgt_export_loadcomb_roundtrip_summary_line,
        "mgt_export_loadcomb_roundtrip_recovery_mode": mgt_export_loadcomb_roundtrip_recovery_mode,
        "mgt_export_loadcomb_combo_count": mgt_export_loadcomb_combo_count,
        "mgt_export_supported_change_count": mgt_export_supported_change_count,
        "mgt_export_unsupported_change_count": mgt_export_unsupported_change_count,
        "mgt_export_direct_patch_change_count": mgt_export_direct_patch_change_count,
        "mgt_export_direct_patch_supported_action_families": mgt_export_direct_patch_supported_action_families,
        "mgt_export_sidecar_supported_action_families": mgt_export_sidecar_supported_action_families,
        "mgt_export_direct_patch_action_family_counts": mgt_export_direct_patch_action_family_counts,
        "mgt_export_direct_patch_action_family_label": mgt_export_direct_patch_action_family_label,
        "mgt_export_special_member_supported_action_family_counts": (
            mgt_export_special_member_supported_action_family_counts
        ),
        "mgt_export_special_member_direct_patch_action_family_counts": (
            mgt_export_special_member_direct_patch_action_family_counts
        ),
        "mgt_export_special_member_zero_touch_verified_action_family_counts": (
            mgt_export_special_member_zero_touch_verified_action_family_counts
        ),
        "mgt_export_special_member_supported_action_family_label": (
            mgt_export_special_member_supported_action_family_label
        ),
        "mgt_export_special_member_direct_patch_action_family_label": (
            mgt_export_special_member_direct_patch_action_family_label
        ),
        "mgt_export_special_member_zero_touch_verified_action_family_label": (
            mgt_export_special_member_zero_touch_verified_action_family_label
        ),
        "mgt_export_material_level_rebar_payload_row_count": mgt_export_material_level_rebar_payload_row_count,
        "mgt_export_material_level_rebar_payload_available_count": mgt_export_material_level_rebar_payload_available_count,
        "mgt_export_group_local_rebar_payload_row_count": mgt_export_group_local_rebar_payload_row_count,
        "mgt_export_group_local_rebar_payload_available_count": mgt_export_group_local_rebar_payload_available_count,
        "mgt_export_group_local_connection_detailing_payload_row_count": mgt_export_group_local_connection_detailing_payload_row_count,
        "mgt_export_group_local_connection_detailing_payload_available_count": mgt_export_group_local_connection_detailing_payload_available_count,
        "mgt_export_group_local_detailing_payload_row_count": mgt_export_group_local_detailing_payload_row_count,
        "mgt_export_group_local_detailing_payload_available_count": mgt_export_group_local_detailing_payload_available_count,
        "mgt_export_connection_detailing_payload_namespace_mode": mgt_export_connection_detailing_payload_namespace_mode,
        "mgt_export_connection_detailing_payload_group_local_namespace_present": mgt_export_connection_detailing_payload_group_local_namespace_present,
        "mgt_export_detailing_payload_namespace_mode": mgt_export_detailing_payload_namespace_mode,
        "mgt_export_detailing_payload_group_local_namespace_present": mgt_export_detailing_payload_group_local_namespace_present,
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": mgt_export_connection_detailing_structured_payload_mapped_change_count,
        "mgt_export_connection_detailing_direct_patch_eligible_change_count": mgt_export_connection_detailing_direct_patch_eligible_change_count,
        "mgt_export_detailing_direct_patch_eligible_change_count": mgt_export_detailing_direct_patch_eligible_change_count,
        "mgt_export_detailing_structured_payload_mapped_change_count": mgt_export_detailing_structured_payload_mapped_change_count,
        "mgt_export_connection_detailing_delivery_mode": mgt_export_connection_detailing_delivery_mode,
        "mgt_export_detailing_delivery_mode": mgt_export_detailing_delivery_mode,
        "mgt_export_rebar_payload_namespace_mode": mgt_export_rebar_payload_namespace_mode,
        "mgt_export_rebar_payload_material_level_namespace_present": mgt_export_rebar_payload_material_level_namespace_present,
        "mgt_export_rebar_payload_group_local_namespace_present": mgt_export_rebar_payload_group_local_namespace_present,
        "mgt_export_rebar_direct_patch_eligible_change_count": mgt_export_rebar_direct_patch_eligible_change_count,
        "mgt_export_rebar_direct_patch_ineligible_reason_counts": mgt_export_rebar_direct_patch_ineligible_reason_counts,
        "mgt_export_rebar_direct_patch_ineligible_reason_label": mgt_export_rebar_direct_patch_ineligible_reason_label,
        "mgt_export_rebar_direct_patch_mapping_source_counts": mgt_export_rebar_direct_patch_mapping_source_counts,
        "mgt_export_rebar_direct_patch_mapping_source_label": mgt_export_rebar_direct_patch_mapping_source_label,
        "mgt_export_rebar_delivery_mode": mgt_export_rebar_delivery_mode,
        "mgt_export_evidence_model": mgt_export_evidence_model,
        "mgt_export_delivery_boundary": mgt_export_delivery_boundary,
        "mgt_export_instruction_sidecar_change_count": mgt_export_instruction_sidecar_change_count,
        "mgt_export_instruction_sidecar_action_family_counts": mgt_export_instruction_sidecar_action_family_counts,
        "mgt_export_instruction_sidecar_action_family_label": mgt_export_instruction_sidecar_action_family_label,
        "mgt_export_instruction_sidecar_audit_only_change_count": mgt_export_instruction_sidecar_audit_only_change_count,
        "mgt_export_instruction_sidecar_audit_only_action_family_counts": mgt_export_instruction_sidecar_audit_only_action_family_counts,
        "mgt_export_instruction_sidecar_audit_only_action_family_label": mgt_export_instruction_sidecar_audit_only_action_family_label,
        "mgt_export_instruction_sidecar_manual_input_change_count": mgt_export_instruction_sidecar_manual_input_change_count,
        "mgt_export_instruction_sidecar_manual_input_action_family_counts": mgt_export_instruction_sidecar_manual_input_action_family_counts,
        "mgt_export_instruction_sidecar_manual_input_action_family_label": mgt_export_instruction_sidecar_manual_input_action_family_label,
        "mgt_export_audit_review_manifest_change_count": mgt_export_audit_review_manifest_change_count,
        "mgt_export_audit_review_manifest_action_family_counts": mgt_export_audit_review_manifest_action_family_counts,
        "mgt_export_audit_review_manifest_action_family_label": mgt_export_audit_review_manifest_action_family_label,
        "mgt_export_audit_review_packet_count": mgt_export_audit_review_packet_count,
        "mgt_export_audit_review_packet_action_family_counts": mgt_export_audit_review_packet_action_family_counts,
        "mgt_export_audit_review_packet_action_family_label": mgt_export_audit_review_packet_action_family_label,
        "mgt_export_audit_review_packet_followup_type_counts": mgt_export_audit_review_packet_followup_type_counts,
        "mgt_export_audit_review_packet_followup_type_label": mgt_export_audit_review_packet_followup_type_label,
        "mgt_export_audit_review_packet_file_count": mgt_export_audit_review_packet_file_count,
        "mgt_export_audit_review_packet_file_action_family_counts": mgt_export_audit_review_packet_file_action_family_counts,
        "mgt_export_audit_review_packet_file_action_family_label": mgt_export_audit_review_packet_file_action_family_label,
        "mgt_export_audit_review_queue_item_count": mgt_export_audit_review_queue_item_count,
        "mgt_export_audit_review_queue_pending_count": mgt_export_audit_review_queue_pending_count,
        "mgt_export_audit_review_queue_acknowledged_count": mgt_export_audit_review_queue_acknowledged_count,
        "mgt_export_audit_review_queue_status_counts": mgt_export_audit_review_queue_status_counts,
        "mgt_export_audit_review_queue_status_label": mgt_export_audit_review_queue_status_label,
        "mgt_export_audit_review_queue_action_family_counts": mgt_export_audit_review_queue_action_family_counts,
        "mgt_export_audit_review_queue_action_family_label": mgt_export_audit_review_queue_action_family_label,
        "mgt_export_audit_review_followup_item_count": mgt_export_audit_review_followup_item_count,
        "mgt_export_audit_review_followup_open_item_count": mgt_export_audit_review_followup_open_item_count,
        "mgt_export_audit_review_followup_closed_item_count": mgt_export_audit_review_followup_closed_item_count,
        "mgt_export_audit_review_followup_action_counts": mgt_export_audit_review_followup_action_counts,
        "mgt_export_audit_review_followup_action_label": mgt_export_audit_review_followup_action_label,
        "mgt_export_audit_review_followup_owner_counts": mgt_export_audit_review_followup_owner_counts,
        "mgt_export_audit_review_followup_owner_label": mgt_export_audit_review_followup_owner_label,
        "mgt_export_audit_review_followup_review_owner_counts": mgt_export_audit_review_followup_review_owner_counts,
        "mgt_export_audit_review_followup_review_owner_label": mgt_export_audit_review_followup_review_owner_label,
        "mgt_export_audit_review_followup_status_counts": mgt_export_audit_review_followup_status_counts,
        "mgt_export_audit_review_followup_status_label": mgt_export_audit_review_followup_status_label,
        "mgt_export_audit_review_followup_sla_state_counts": mgt_export_audit_review_followup_sla_state_counts,
        "mgt_export_audit_review_followup_sla_state_label": mgt_export_audit_review_followup_sla_state_label,
        "mgt_export_audit_review_followup_age_bucket_counts": mgt_export_audit_review_followup_age_bucket_counts,
        "mgt_export_audit_review_followup_age_bucket_label": mgt_export_audit_review_followup_age_bucket_label,
        "mgt_export_audit_review_followup_overdue_item_count": mgt_export_audit_review_followup_overdue_item_count,
        "mgt_export_audit_review_followup_oldest_open_age_hours": mgt_export_audit_review_followup_oldest_open_age_hours,
        "mgt_export_audit_review_followup_oldest_open_packet_id": mgt_export_audit_review_followup_oldest_open_packet_id,
        "mgt_export_audit_review_followup_reference_time_utc": mgt_export_audit_review_followup_reference_time_utc,
        "mgt_export_audit_review_followup_sla_policy_label": mgt_export_audit_review_followup_sla_policy_label,
        "mgt_export_audit_review_followup_mode": mgt_export_audit_review_followup_mode,
        "mgt_export_audit_review_resolution_item_count": mgt_export_audit_review_resolution_item_count,
        "mgt_export_audit_review_resolution_file_count": mgt_export_audit_review_resolution_file_count,
        "mgt_export_audit_review_resolution_open_item_count": mgt_export_audit_review_resolution_open_item_count,
        "mgt_export_audit_review_resolution_closed_item_count": mgt_export_audit_review_resolution_closed_item_count,
        "mgt_export_audit_review_resolution_pending_item_count": mgt_export_audit_review_resolution_pending_item_count,
        "mgt_export_audit_review_resolution_open_revision_count": mgt_export_audit_review_resolution_open_revision_count,
        "mgt_export_audit_review_resolution_closed_packet_count": mgt_export_audit_review_resolution_closed_packet_count,
        "mgt_export_audit_review_resolution_action_counts": mgt_export_audit_review_resolution_action_counts,
        "mgt_export_audit_review_resolution_action_label": mgt_export_audit_review_resolution_action_label,
        "mgt_export_audit_review_resolution_owner_counts": mgt_export_audit_review_resolution_owner_counts,
        "mgt_export_audit_review_resolution_owner_label": mgt_export_audit_review_resolution_owner_label,
        "mgt_export_audit_review_resolution_status_counts": mgt_export_audit_review_resolution_status_counts,
        "mgt_export_audit_review_resolution_status_label": mgt_export_audit_review_resolution_status_label,
        "mgt_export_audit_review_resolution_mode": mgt_export_audit_review_resolution_mode,
        "mgt_export_instruction_sidecar_review_priority_counts": mgt_export_instruction_sidecar_review_priority_counts,
        "mgt_export_instruction_sidecar_review_priority_label": mgt_export_instruction_sidecar_review_priority_label,
        "mgt_export_patched_material_row_count": mgt_export_patched_material_row_count,
        "mgt_export_cloned_material_count": mgt_export_cloned_material_count,
        "mgt_export_instruction_sidecar_followup_type_counts": mgt_export_instruction_sidecar_followup_type_counts,
        "mgt_export_instruction_sidecar_followup_type_label": mgt_export_instruction_sidecar_followup_type_label,
        "mgt_export_cloned_section_count": mgt_export_cloned_section_count,
        "mgt_export_cloned_thickness_count": mgt_export_cloned_thickness_count,
        "mgt_export_retargeted_element_row_count": mgt_export_retargeted_element_row_count,
        "mgt_export_patched_section_scale_row_count": mgt_export_patched_section_scale_row_count,
        "mgt_export_patched_thickness_row_count": mgt_export_patched_thickness_row_count,
        "pbd_dynamic_hinge_refresh_ready": bool(pbd_dynamic_hinge_refresh_ready),
        "pbd_hinge_state_mode": pbd_hinge_state_mode,
        "pbd_hinge_refresh_reason": pbd_hinge_refresh_reason,
        "pbd_hinge_proxy_artifact_count": int(pbd_hinge_proxy_artifact_count),
        "pbd_hinge_refresh_artifact_present": bool(pbd_hinge_refresh_artifact_present),
        "pbd_hinge_refresh_artifact_kind": pbd_hinge_refresh_artifact_kind,
        "pbd_hinge_refresh_source_mode": pbd_hinge_refresh_source_mode,
        "pbd_hinge_refresh_overlap_member_count": int(pbd_hinge_refresh_overlap_member_count),
        "pbd_hinge_refresh_rebar_sensitive_member_count": int(pbd_hinge_refresh_rebar_sensitive_member_count),
        "pbd_hinge_benchmark_gate_pass": bool(pbd_hinge_benchmark_gate_pass),
        "pbd_hinge_benchmark_fixture_regression_pass": bool(pbd_hinge_benchmark_fixture_regression_pass),
        "pbd_hinge_benchmark_alignment_pass": bool(pbd_hinge_benchmark_alignment_pass),
        "pbd_hinge_benchmark_asset_count": int(pbd_hinge_benchmark_asset_count),
        "pbd_hinge_benchmark_train_count": int(pbd_hinge_benchmark_train_count),
        "pbd_hinge_benchmark_val_count": int(pbd_hinge_benchmark_val_count),
        "pbd_hinge_benchmark_holdout_count": int(pbd_hinge_benchmark_holdout_count),
        "pbd_hinge_benchmark_rebar_sensitive_count": int(pbd_hinge_benchmark_rebar_sensitive_count),
        "pbd_hinge_benchmark_confinement_sensitive_count": int(pbd_hinge_benchmark_confinement_sensitive_count),
        "pbd_hinge_benchmark_fixture_count": int(pbd_hinge_benchmark_fixture_count),
        "pbd_hinge_benchmark_fixture_min_point_count": int(pbd_hinge_benchmark_fixture_min_point_count),
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": float(pbd_hinge_benchmark_fixture_min_peak_drift_ratio),
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": int(
            pbd_hinge_benchmark_alignment_refresh_column_row_count
        ),
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": int(
            pbd_hinge_benchmark_alignment_rebar_sensitive_column_count
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
            pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
            pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
            pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
            pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max
        ),
        "panel_zone_3d_clash_ready": bool(panel_zone_3d_clash_ready),
        "panel_zone_constructability_mode": panel_zone_constructability_mode,
        "panel_zone_constructability_reason": panel_zone_constructability_reason,
        "panel_zone_proxy_candidate_count": int(panel_zone_proxy_candidate_count),
        "panel_zone_source_artifact_kind": panel_zone_source_artifact_kind,
        "panel_zone_source_artifact_path": panel_zone_source_artifact_path,
        "panel_zone_source_contract_mode": panel_zone_source_contract_mode,
        "panel_zone_internal_engine_complete": bool(panel_zone_internal_engine_complete),
        "panel_zone_external_validation_pending": bool(panel_zone_external_validation_pending),
        "panel_zone_validation_boundary": panel_zone_validation_boundary,
        "panel_zone_status_label": panel_zone_status_label,
        "panel_zone_advisory_only": bool(panel_zone_advisory_only),
        "panel_zone_release_blocking": bool(panel_zone_release_blocking),
        "panel_zone_external_validation_status_label": panel_zone_external_validation_status_label,
        "panel_zone_external_validation_advisory_only": bool(panel_zone_external_validation_advisory_only),
        "panel_zone_external_validation_release_blocking": bool(panel_zone_external_validation_release_blocking),
        "panel_zone_external_validation_artifact_closed": bool(
            panel_zone_external_validation_artifact_closed
        ),
        "panel_zone_external_validation_closure_mode": panel_zone_external_validation_closure_mode,
        "panel_zone_external_validation_source_count": int(panel_zone_external_validation_source_count),
        "panel_zone_external_validation_validated_source_count": int(
            panel_zone_external_validation_validated_source_count
        ),
        "panel_zone_external_validation_exact_source_count": int(panel_zone_external_validation_exact_source_count),
        "panel_zone_external_validation_fallback_source_count": int(
            panel_zone_external_validation_fallback_source_count
        ),
        "panel_zone_external_validation_missing_source_count": int(
            panel_zone_external_validation_missing_source_count
        ),
        "panel_zone_external_validation_unknown_source_count": int(
            panel_zone_external_validation_unknown_source_count
        ),
        "panel_zone_external_validation_validated_source_ratio": float(
            panel_zone_external_validation_validated_source_ratio
        ),
        "panel_zone_external_validation_exact_source_ratio": float(
            panel_zone_external_validation_exact_source_ratio
        ),
        "panel_zone_external_validation_fallback_source_ratio": float(
            panel_zone_external_validation_fallback_source_ratio
        ),
        "panel_zone_external_validation_candidate_member_count": int(
            panel_zone_external_validation_candidate_member_count
        ),
        "panel_zone_external_validation_validated_member_count": int(
            panel_zone_external_validation_validated_member_count
        ),
        "panel_zone_external_validation_exact_member_count": int(panel_zone_external_validation_exact_member_count),
        "panel_zone_external_validation_fallback_member_count": int(
            panel_zone_external_validation_fallback_member_count
        ),
        "panel_zone_external_validation_validated_member_ratio": float(
            panel_zone_external_validation_validated_member_ratio
        ),
        "panel_zone_external_validation_exact_member_ratio": float(
            panel_zone_external_validation_exact_member_ratio
        ),
        "panel_zone_external_validation_fallback_member_ratio": float(
            panel_zone_external_validation_fallback_member_ratio
        ),
        "panel_zone_external_validation_validated_row_count_total": int(
            panel_zone_external_validation_validated_row_count_total
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            panel_zone_external_validation_exact_validated_row_count
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            panel_zone_external_validation_fallback_validated_row_count
        ),
        "panel_zone_external_validation_exact_validated_row_ratio": float(
            panel_zone_external_validation_exact_validated_row_ratio
        ),
        "panel_zone_external_validation_fallback_validated_row_ratio": float(
            panel_zone_external_validation_fallback_validated_row_ratio
        ),
        "panel_zone_external_validation_required_evidence": panel_zone_external_validation_required_evidence,
        "panel_zone_external_validation_summary_line": panel_zone_external_validation_summary_line,
        "panel_zone_external_validation_provenance_summary_label": panel_zone_external_validation_provenance_summary_label,
        "panel_zone_external_validation_closing_summary_label": panel_zone_external_validation_closing_summary_label,
        "panel_zone_external_validation_local_closure_state": panel_zone_external_validation_local_closure_state,
        "panel_zone_external_validation_local_closure_label": panel_zone_external_validation_local_closure_label,
        "panel_zone_topology_capable_input": bool(panel_zone_topology_capable_input),
        "panel_zone_true_3d_clash_verified": bool(panel_zone_true_3d_clash_verified),
        "panel_zone_true_3d_anchorage_verified": bool(panel_zone_true_3d_anchorage_verified),
        "panel_zone_source_valid_row_counts": panel_zone_source_valid_row_counts,
        "panel_zone_source_overlap_member_counts": panel_zone_source_overlap_member_counts,
        "panel_zone_source_candidate_scan_modes": panel_zone_source_candidate_scan_modes,
        "panel_zone_source_bundle_modes": panel_zone_source_bundle_modes,
        "panel_zone_source_upstream_verification_tiers": panel_zone_source_upstream_verification_tiers,
        "panel_zone_instruction_sidecar_present": bool(panel_zone_instruction_sidecar_present),
        "panel_zone_instruction_sidecar_change_count": int(panel_zone_instruction_sidecar_change_count),
        "panel_zone_instruction_sidecar_candidate_overlap_mode": panel_zone_instruction_sidecar_candidate_overlap_mode,
        "panel_zone_instruction_sidecar_overlap_row_count": int(panel_zone_instruction_sidecar_overlap_row_count),
        "panel_zone_instruction_sidecar_overlap_member_count": int(panel_zone_instruction_sidecar_overlap_member_count),
        "panel_zone_instruction_sidecar_overlap_group_count": int(panel_zone_instruction_sidecar_overlap_group_count),
        "panel_zone_instruction_sidecar_evidence_model": panel_zone_instruction_sidecar_evidence_model,
        "panel_zone_instruction_sidecar_rebar_delivery_mode": panel_zone_instruction_sidecar_rebar_delivery_mode,
        "panel_zone_member_mapping_sidecar_present": bool(panel_zone_member_mapping_sidecar_present),
        "panel_zone_member_mapping_sidecar_mode": panel_zone_member_mapping_sidecar_mode,
        "panel_zone_member_mapping_sidecar_row_count": int(panel_zone_member_mapping_sidecar_row_count),
        "panel_zone_member_mapping_sidecar_applied_row_count": int(
            panel_zone_member_mapping_sidecar_applied_row_count
        ),
        "panel_zone_member_mapping_sidecar_unmapped_source_member_count": int(
            panel_zone_member_mapping_sidecar_unmapped_source_member_count
        ),
        "panel_zone_validated_source_row_count_total": int(panel_zone_validated_source_row_count_total),
        "panel_zone_validated_source_overlap_member_count_min": int(
            panel_zone_validated_source_overlap_member_count_min
        ),
        "panel_zone_missing_required_sources": panel_zone_missing_required_sources,
        "panel_zone_solver_verified_inbox_status_mode": panel_zone_solver_verified_inbox_status_mode,
        "panel_zone_solver_verified_inbox_has_input": bool(panel_zone_solver_verified_inbox_has_input),
        "panel_zone_solver_verified_pending_input": bool(panel_zone_solver_verified_pending_input),
        "panel_zone_solver_verified_input_mode_detected": panel_zone_solver_verified_input_mode_detected,
        "panel_zone_solver_verified_latest_consume_report_present": bool(
            panel_zone_solver_verified_latest_consume_report_present
        ),
        "panel_zone_solver_verified_latest_consume_contract_pass": bool(
            panel_zone_solver_verified_latest_consume_contract_pass
        ),
        "panel_zone_solver_verified_latest_consume_reason_code": panel_zone_solver_verified_latest_consume_reason_code,
        "panel_zone_solver_verified_source_origin_class": panel_zone_solver_verified_source_origin_class,
        "panel_zone_solver_verified_release_refresh_source_allowed": bool(
            panel_zone_solver_verified_release_refresh_source_allowed
        ),
        "panel_zone_solver_verified_recommended_action": panel_zone_solver_verified_recommended_action,
        "foundation_optimization_ready": bool(foundation_optimization_ready),
        "foundation_member_type_present": bool(foundation_member_type_present),
        "foundation_member_type_count": int(foundation_member_type_count),
        "foundation_optimization_mode": foundation_optimization_mode,
        "foundation_optimization_reason": foundation_optimization_reason,
        "foundation_scope_source": foundation_scope_source,
        "foundation_artifact_scan_mode": foundation_artifact_scan_mode,
        "foundation_artifact_evidence_mode": foundation_artifact_evidence_mode,
        "upstream_foundation_label_count": int(upstream_foundation_label_count),
        "raw_source_foundation_label_count": int(raw_source_foundation_label_count),
        "upstream_foundation_provenance_mode": upstream_foundation_provenance_mode,
        "wind_tunnel_raw_mapping_ready": bool(wind_raw_mapping_ready),
        "wind_tunnel_mapping_mode": wind_tunnel_mapping_mode,
        "wind_tunnel_mapping_reason": wind_tunnel_mapping_reason,
        "authority_catalog_diff_change_count": int(authority_catalog_diff.get("change_count", 0)),
        "authority_catalog_diff_added_count": int(authority_catalog_diff.get("added_count", 0)),
        "authority_catalog_diff_removed_count": int(authority_catalog_diff.get("removed_count", 0)),
        "authority_catalog_diff_baseline_seeded": bool(authority_catalog_diff.get("baseline_seeded", False)),
        "authority_catalog_routing_warning_active": bool(authority_catalog_warning_active),
        "promotion_reason_code": str(promotion.get("reason_code", "")),
        "promotion_hold_for_review": str(promotion.get("reason_code", "")) == "HOLD_FOR_REVIEW",
        "hold_review_manifest": str(promotion.get("hold_review_manifest", "")),
        "hold_review_packet_md": str(promotion.get("hold_review_packet_md", "")),
        "hold_review_packet_pdf": str(promotion.get("hold_review_packet_pdf", "")),
        "hold_review_ack_json": str(promotion.get("hold_review_ack_json", "")),
        "open_gap_counts": {
            "P0": open_p0,
            "P1": open_p1,
            "P2": open_p2,
        },
    }

    warnings: list[dict[str, object]] = []
    if authority_catalog_warning_active:
        warnings.append(
            {
                "id": "authority_catalog_routing_change",
                "severity": "warning",
                "title": "Authority catalog routing changed",
                "value": (
                    f"changes={int(authority_catalog_diff.get('change_count', 0))}, "
                    f"added={int(authority_catalog_diff.get('added_count', 0))}, "
                    f"removed={int(authority_catalog_diff.get('removed_count', 0))}"
                ),
                "why": "Authority/submodel routing changed since the previous committee snapshot and requires explicit review before release promotion.",
            }
        )
    if str(promotion.get("reason_code", "")) == "HOLD_FOR_REVIEW":
        warnings.append(
            {
                "id": "promotion_hold_for_review",
                "severity": "warning",
                "title": "Promotion is held for review",
                "value": str(promotion.get("reason_code", "")),
                "manifest": str(promotion.get("hold_review_manifest", "")),
                "packet": str(promotion.get("hold_review_packet_md", "")),
                "packet_pdf": str(promotion.get("hold_review_packet_pdf", "")),
                "ack": str(promotion.get("hold_review_ack_json", "")),
                "why": (
                    "Authority routing diff is active and the release candidate should remain on hold "
                    "until the hold review manifest is cleared by engineer review."
                ),
            }
        )

    smoke_plot_out = Path(str(args.out_smoke_history_png).strip()) if str(args.out_smoke_history_png).strip() else _smoke_history_plot_path(args.out_json)
    measured_chain_plot_out = (
        Path(str(args.out_measured_chain_category_png).strip())
        if str(args.out_measured_chain_category_png).strip()
        else _measured_chain_category_plot_path(args.out_json)
    )
    smoke_trend = _smoke_trend_summary(nightly_smoke_history)
    smoke_recent_samples = _smoke_recent_samples(nightly_smoke_history, limit=5)
    _write_smoke_history_plot(smoke_plot_out, nightly_smoke_history)
    _write_measured_chain_category_plot(measured_chain_plot_out, rolling_measured_chain["measured_chain_rolling_rows"])

    payload = {
        "schema_version": "1.0",
        "run_id": "phase3-release-gap-report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "release_status": release_status,
        "observed_strengths": observed_strengths,
        "remaining_gaps": remaining_gaps,
        "advanced_holdouts": advanced_holdouts,
        "residual_holdout_buckets": residual_holdout_breakdown,
        "residual_holdout_work_items": residual_holdout_work_items,
        "nightly_smoke_trend": smoke_trend,
        "nightly_smoke_recent_samples": smoke_recent_samples,
        "measured_chain_step_rows": measured_chain_timing["measured_chain_step_rows"],
        "measured_chain_rolling_rows": rolling_measured_chain["measured_chain_rolling_rows"],
        "warnings": warnings,
        "artifacts": {
            "smoke_history_png": str(smoke_plot_out),
            "measured_chain_category_png": str(measured_chain_plot_out),
            "hold_review_manifest": str(promotion.get("hold_review_manifest", "")),
            "hold_review_packet_md": str(promotion.get("hold_review_packet_md", "")),
            "hold_review_packet_pdf": str(promotion.get("hold_review_packet_pdf", "")),
            "hold_review_ack_json": str(promotion.get("hold_review_ack_json", "")),
            "peer_blind_prediction_compare_report": str(peer_blind_prediction_compare_report_path),
            "peer_blind_prediction_measured_response_landing_manifest": str(
                peer_blind_prediction_measured_response_landing_manifest_path
            ),
            "commercial_workflow_breadth_report_json": str(commercial_workflow_breadth_path),
            "commercial_workflow_breadth_artifact_links": commercial_workflow_breadth_surface.get(
                "commercial_workflow_breadth_artifact_links",
                {},
            ),
            "midas_kds_row_provenance_export_json": str(
                committee_artifact_links.get("midas_kds_row_provenance_export_json", "") or ""
            ),
            "midas_kds_row_provenance_export_csv": str(
                committee_artifact_links.get("midas_kds_row_provenance_export_csv", "") or ""
            ),
            "midas_kds_row_provenance_export_report": str(
                committee_artifact_links.get("midas_kds_row_provenance_export_report", "") or ""
            ),
            "project_registry_report": str(
                committee_artifact_links.get("project_registry_report", "")
                or release_registry_artifacts.get("project_registry_report", "")
                or ""
            ),
            "project_package_zip": str(
                committee_artifact_links.get("project_package_zip", "")
                or release_registry_artifacts.get("project_package_zip", "")
                or ""
            ),
            "project_registry_signature": str(
                committee_artifact_links.get("project_registry_signature", "")
                or release_registry_artifacts.get("project_registry_signature", "")
                or ""
            ),
            "external_benchmark_batch_job_report_json": str(
                committee_artifact_links.get("external_benchmark_batch_job_report_json", "") or ""
            ),
            "material_constitutive_gate_report": str(args.material_constitutive_gate_report),
            "load_combination_engine_gate_report": str(args.load_combination_engine_gate_report),
            "load_combination_editor_commercialization_report": str(
                args.load_combination_editor_commercialization_report
            ),
            "reference_regression_report": str(args.reference_regression_report),
            "advanced_ssi_report": str(args.advanced_ssi_report),
            "wind_workflow_report": str(args.wind_workflow_report),
            "midas_native_roundtrip_appendix_markdown": str(
                (
                    ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get(
                        "unsupported_lossy_card_family_appendix_markdown", ""
                    )
                    if isinstance(ci.get("midas_native_roundtrip_report"), dict)
                    else ""
                )
                or ""
            ),
            "midas_native_roundtrip_appendix_json": str(
                (
                    ci.get("midas_native_roundtrip_report", {}).get("summary", {}).get(
                        "unsupported_lossy_card_family_appendix_json", ""
                    )
                    if isinstance(ci.get("midas_native_roundtrip_report"), dict)
                    else ""
                )
                or ""
            ),
            **native_authoring_artifacts,
        },
        "inputs": {
            "nightly_release": str(args.nightly_release),
            "ci_gate": str(args.ci_gate),
            "static_validation": str(args.static_validation),
            "freeze_report": str(args.freeze_report),
            "promotion_report": str(args.promotion_report),
            "commercial_readiness": str(args.commercial_readiness),
            "global_authority": str(args.global_authority),
            "hip_kernel_smoke": str(args.hip_kernel_smoke),
            "midas_conversion": str(args.midas_conversion),
            "construction_sequence": str(args.construction_sequence),
            "flexible_diaphragm": str(args.flexible_diaphragm),
            "repro_version_lock": str(args.repro_version_lock),
            "release_registry": str(args.release_registry),
            "kds_compliance": str(args.kds_compliance),
            "pbd_package": str(args.pbd_package),
            "design_opt_dataset_report": str(args.design_opt_dataset_report),
            "pbd_hinge_refresh_report": str(args.pbd_hinge_refresh_report),
            "panel_zone_clash_report": str(args.panel_zone_clash_report),
            "panel_zone_solver_verified_inbox_status_report": str(args.panel_zone_solver_verified_inbox_status_report),
            "foundation_optimization_report": str(args.foundation_optimization_report),
            "wind_raw_mapping_report": str(args.wind_raw_mapping_report),
            "material_constitutive_gate_report": str(args.material_constitutive_gate_report),
            "load_combination_engine_gate_report": str(args.load_combination_engine_gate_report),
            "advanced_ssi_report": str(args.advanced_ssi_report),
            "wind_workflow_report": str(args.wind_workflow_report),
            "committee_summary": str(args.committee_summary),
            "native_authoring_solver_session_report": str(args.native_authoring_solver_session_report),
            "native_authoring_ops_bundle_report": str(args.native_authoring_ops_bundle_report),
            "native_authoring_family_tracks_report": str(args.native_authoring_family_tracks_report),
            "native_authoring_runtime_submission_report": str(args.native_authoring_runtime_submission_report),
            "project_ops_service_snapshot": str(args.project_ops_service_snapshot),
            "commercial_workflow_breadth_report": str(commercial_workflow_breadth_path),
            "nightly_history_root": str(args.nightly_history_root),
            "nightly_history_limit": int(args.nightly_history_limit),
            "out_smoke_history_png": str(smoke_plot_out),
            "out_measured_chain_category_png": str(measured_chain_plot_out),
        },
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown(out_md, payload)
    print(f"Wrote release gap report JSON: {out_json}")
    print(f"Wrote release gap report Markdown: {out_md}")
    print(f"Wrote release gap smoke history plot: {smoke_plot_out}")
    print(f"Wrote release gap measured chain category plot: {measured_chain_plot_out}")


if __name__ == "__main__":
    main()
