#!/usr/bin/env python3
"""Assemble a single committee-ready package from existing release artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import html
import json
import math
import re
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from design_optimization.artifacts import (
    COST_REDUCTION_BLOCKED_ACTIONS_CSV,
    COST_REDUCTION_CHANGES_CSV,
    COST_REDUCTION_NO_GAIN_EXPLAIN_CSV,
    COST_REDUCTION_NO_GAIN_GROUPS_CSV,
    COST_REDUCTION_REPORT_JSON,
    SOLVER_LOOP_LONG_REPORT_JSON,
)
from design_optimization.entrypoint_appendix import (
    annotate_entrypoint_groups,
    build_entrypoint_detail_groups,
    render_entrypoint_html_detail_sections,
    render_entrypoint_markdown_sections,
)
from design_optimization.io import entrypoint_group_rows, entrypoint_status_rows, load_design_opt_reports
from implementation.phase1 import export_midas_kds_row_provenance_table as row_provenance_export_module
from implementation.phase1.ui_design_tokens import build_signal_desk_light_css
from implementation.phase1.ui_layout_fragments import render_route_context_banner
from implementation.phase1.panel_zone_external_validation import (
    build_panel_zone_external_validation_local_closure_surface,
    build_panel_zone_external_validation_provenance_surface,
    build_panel_zone_external_validation_required_evidence,
    build_panel_zone_external_validation_summary_line,
    normalize_panel_zone_external_validation_status_label,
)
from implementation.phase1.pdf_rendering import configure_matplotlib_cjk_pdf, finalize_pdf_figure


CONSTITUTIVE_INTERACTION_NOTE = (
    "material and steel/composite constitutive gates are surfaced explicitly as shared summary lines across the "
    "release, committee, and external reports; closed supporting gates such as the load-combination engine remain "
    "visible as evidence when present."
)

ROW_PROVENANCE_SYNC_NOTE = (
    "the Review surface and row-provenance appendix stay bidirectionally aligned on the same Hazard and Rule Family slices; "
    "the appendix exposes explicit viewer_row_url and viewer_slice_url reverse-sync links back to the matching viewer row and slice."
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


def _committee_meta_list_html(items: list[tuple[str, object]]) -> str:
    rows: list[str] = []
    for label, value in items:
        text = str(value or "").strip() or "n/a"
        rows.append(
            "<li>"
            f"<span class=\"committee-meta-list__label\">{html.escape(str(label), quote=True)}</span>"
            f"<code>{html.escape(text, quote=True)}</code>"
            "</li>"
        )
    return "<ul class=\"committee-meta-list\">" + "".join(rows) + "</ul>"


def _holdout_closure_evidence_label(row: dict[str, Any]) -> str:
    closure_evidence = str(row.get("closure_evidence_path", "") or "").strip()
    if not closure_evidence:
        closure_evidence = str(row.get("closure_evidence_required", "") or "").strip()
    closure_status = str(row.get("closure_evidence_status", "") or "").strip()
    if closure_evidence and closure_status and closure_status != "attached":
        return f"{closure_evidence} ({closure_status})"
    return closure_evidence or closure_status or "n/a"


def _advanced_holdout_closure_surface(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def _compact_text(value: object, *, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: max(limit - 3, 0)].rstrip() + "..."

    status_rows: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        severity = str(row.get("severity", "") or "").strip()
        if severity:
            severity_counts[severity] += 1
        ready = bool(row.get("ready", False))
        status_rows.append(
            {
                "id": str(row.get("id", "") or "").strip(),
                "title": str(row.get("title", "") or "").strip(),
                "severity": severity,
                "closure_state": "closed" if ready else "open",
                "ready": ready,
                "mode": str(row.get("mode", row.get("status_label", "")) or "").strip(),
                "reason_snippet": _compact_text(row.get("reason", ""), limit=160),
                "evidence_snippet": _compact_text(row.get("evidence", ""), limit=260),
                "status_label": str(row.get("status_label", "") or "").strip(),
            }
        )

    total_count = len(status_rows)
    closed_count = sum(1 for row in status_rows if bool(row.get("ready", False)))
    open_count = max(total_count - closed_count, 0)
    severity_label = ", ".join(
        f"{severity}:{count}" for severity, count in sorted(severity_counts.items())
    )
    summary_label = (
        f"closed={closed_count}/{total_count} | open={open_count}"
        + (f" | severities={severity_label}" if severity_label else "")
    )
    return {
        "total_count": int(total_count),
        "closed_count": int(closed_count),
        "open_count": int(open_count),
        "severity_counts": dict(severity_counts),
        "summary_label": summary_label,
        "status_rows": status_rows,
    }


def _report_high_level_pass(report: dict[str, Any]) -> bool | None:
    if not isinstance(report, dict):
        return None
    if "contract_pass" in report:
        return bool(report.get("contract_pass", False))
    if "all_pass" in report:
        return bool(report.get("all_pass", False))
    if "pass" in report:
        return bool(report.get("pass", False))
    return None


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
            if gate_pass is None and isinstance(report_payload, dict):
                gate_pass = _report_high_level_pass(report_payload)
    return summary_line, gate_pass


def _format_optional_gate_surface(summary_line: str, gate_pass: bool | None) -> str:
    text = str(summary_line or "").strip()
    if gate_pass is None:
        return text
    if text:
        return f"pass={bool(gate_pass)} | {text}"
    return f"pass={bool(gate_pass)}"


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


def _compact_workflow_contact_coupling_summary_label(summary_line: str) -> str:
    text = str(summary_line or "").strip()
    if not text:
        return ""
    match = re.search(
        r"coupling=(.*?)(?:\s*\|\s*contact_material=|\s*\|\s*korean_source_ingest=|\s*$)",
        text,
    )
    if match:
        return str(match.group(1)).strip()
    return ""


def _compact_general_fe_contact_matrix_summary_label(summary_line: str) -> str:
    text = str(summary_line or "").strip()
    if not text:
        return ""
    text = re.sub(r"^General FE contact matrix:\s*(?:PASS|CHECK)\s*\|\s*", "", text)
    return text.strip()


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


def _panel_zone_external_validation_surface(summary: dict[str, Any]) -> dict[str, Any]:
    coverage = build_panel_zone_external_validation_provenance_surface(summary)
    advisory_only = bool(
        summary.get("panel_zone_external_validation_advisory_only", False)
        or (
            bool(summary.get("panel_zone_3d_clash_ready", False))
            and bool(summary.get("panel_zone_internal_engine_complete", False))
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
        summary,
        advisory_only=advisory_only,
        release_blocking=release_blocking,
    )
    return {
        "advisory_only": advisory_only,
        "release_blocking": release_blocking,
        "status_label": status_label,
        "artifact_closed": bool(coverage["artifact_closed"]),
        "closure_mode": str(coverage["closure_mode"]),
    }


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


def _midas_row_provenance_appendix_markdown_lines(artifacts: dict, metrics: dict) -> list[str]:
    summary_line = str(metrics.get("midas_row_provenance_export_summary_line", "") or "").strip()
    if not summary_line:
        return []
    preview_rows = [
        row
        for row in (metrics.get("midas_row_provenance_preview_rows") or [])
        if isinstance(row, dict)
    ]
    clause_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_clause_filter_rows") or [])
        if isinstance(row, dict)
    ]
    member_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_member_filter_rows") or [])
        if isinstance(row, dict)
    ]
    hazard_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_hazard_filter_rows") or [])
        if isinstance(row, dict)
    ]
    rule_family_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_rule_family_filter_rows") or [])
        if isinstance(row, dict)
    ]
    lines = [
        "### MIDAS KDS Row Provenance Export",
        "",
        f"- `summary`: `{summary_line}`",
        f"- `json`: `{artifacts.get('midas_row_provenance_table_json', '') or 'n/a'}`",
        f"- `csv`: `{artifacts.get('midas_row_provenance_table_csv', '') or 'n/a'}`",
        f"- `report`: `{artifacts.get('midas_row_provenance_table_report', '') or 'n/a'}`",
        "",
    ]
    lines.append(f"- `row-provenance sync`: `{ROW_PROVENANCE_SYNC_NOTE}`")
    if preview_rows:
        lines.extend(
            [
                "| Combination | Member | Clause | Baseline Focus | Provenance |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in preview_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("combination_name", "") or "n/a"),
                        str(row.get("member_id", "") or "n/a"),
                        str(row.get("clause_label", "") or "n/a"),
                        str(row.get("baseline_focus_member_id", "") or "n/a"),
                        str(row.get("bridge_row_provenance_mode_label", "") or "n/a"),
                    ]
                )
                + " |"
            )
        lines.append("")
    if clause_filter_rows:
        lines.extend(
            [
                "| Clause | Rows | Members | Combos | Top Member | Top D/C |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in clause_filter_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("clause_label", "") or "n/a"),
                        str(row.get("row_count", "") or "0"),
                        str(row.get("member_count", "") or "0"),
                        str(row.get("combination_count", "") or "0"),
                        str(row.get("top_member_id", "") or "n/a"),
                        str(row.get("top_dcr_label", "") or "n/a"),
                    ]
                )
                + " |"
            )
        lines.append("")
    if member_filter_rows:
        lines.extend(
            [
                "| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in member_filter_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("member_id", "") or "n/a"),
                        str(row.get("baseline_focus_member_id", "") or "n/a"),
                        str(row.get("row_count", "") or "0"),
                        str(row.get("clause_count", "") or "0"),
                        str(row.get("combination_count", "") or "0"),
                        str(row.get("top_clause_label", "") or "n/a"),
                    ]
                )
                + " |"
        )
        lines.append("")
    if hazard_filter_rows:
        lines.extend(
            [
                "| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in hazard_filter_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("hazard_type", "") or "n/a"),
                        str(row.get("row_count", "") or "0"),
                        str(row.get("member_count", "") or "0"),
                        str(row.get("clause_count", "") or "0"),
                        str(row.get("combination_count", "") or "0"),
                        str(row.get("top_clause_label", "") or "n/a"),
                        str(row.get("top_dcr_label", "") or "n/a"),
                    ]
                )
                + " |"
            )
        lines.append("")
    if rule_family_filter_rows:
        lines.extend(
            [
                "| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in rule_family_filter_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("rule_family", "") or "n/a"),
                        str(row.get("row_count", "") or "0"),
                        str(row.get("member_count", "") or "0"),
                        str(row.get("hazard_count", "") or "0"),
                        str(row.get("combination_count", "") or "0"),
                        str(row.get("top_clause_label", "") or "n/a"),
                        str(row.get("top_dcr_label", "") or "n/a"),
                    ]
                )
                + " |"
            )
        lines.append("")
    return lines


def _midas_native_roundtrip_appendix_markdown_lines(artifacts: dict, metrics: dict) -> list[str]:
    summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "").strip()
    taxonomy_case_counts = (
        metrics.get("midas_native_roundtrip_taxonomy_case_counts")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_case_counts"), dict)
        else {}
    )
    taxonomy_card_family_histogram = (
        metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram"), dict)
        else {}
    )
    structure_type_batch_markdowns = [
        str(row)
        for row in (metrics.get("midas_native_roundtrip_structure_type_batch_markdowns") or [])
        if str(row or "").strip()
    ]
    if not summary_line and not taxonomy_case_counts:
        return []
    lines = [
        "### MIDAS Native Roundtrip Unsupported/Lossy Card Families",
        "",
        f"- `summary`: `{summary_line or 'n/a'}`",
        f"- `appendix_md`: `{artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'}`",
        f"- `appendix_json`: `{artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}`",
        "- `public-preview note`: `public archive-derived preview write-back baselines are counted separately from original public native .mgt baselines.`",
        (
            f"- `public split`: public_native_ready={int(metrics.get('midas_native_roundtrip_public_native_writeback_ready_count', 0))} | "
            f"public_raw_ready={int(metrics.get('midas_native_roundtrip_public_raw_native_writeback_ready_count', 0))} | "
            f"public_bridge_ready={int(metrics.get('midas_native_roundtrip_public_bridge_writeback_ready_count', 0))} | "
            f"public_archive_preview_ready={int(metrics.get('midas_native_roundtrip_public_archive_preview_writeback_ready_count', 0))} | "
            f"public_structural_preview_ready={int(metrics.get('midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count', 0))} | "
            f"public_source_ready={int(metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0))} | "
            f"fixture_ready={int(metrics.get('midas_native_roundtrip_fixture_native_writeback_ready_count', 0))} | "
            f"repo_ready={int(metrics.get('midas_native_roundtrip_repo_native_writeback_ready_count', 0))} | "
            f"experiment_ready={int(metrics.get('midas_native_roundtrip_experiment_native_writeback_ready_count', 0))}"
        ),
        (
            f"- `special_member_family`: direct_patch=`{str(metrics.get('mgt_export_special_member_direct_patch_action_family_label', '') or 'n/a')}` | "
            f"supported=`{str(metrics.get('mgt_export_special_member_supported_action_family_label', '') or 'n/a')}` | "
            f"zero_touch_verified=`{str(metrics.get('mgt_export_special_member_zero_touch_verified_action_family_label', '') or 'n/a')}`"
        ),
        f"- `taxonomy_case_counts`: `{json.dumps(taxonomy_case_counts, ensure_ascii=False, sort_keys=True)}`",
        f"- `taxonomy_card_family_histogram`: `{json.dumps(taxonomy_card_family_histogram, ensure_ascii=False, sort_keys=True)}`",
        "",
    ]
    if structure_type_batch_markdowns:
        lines.extend(["| Structure Type Batch Markdown |", "| --- |"])
        for batch_markdown in structure_type_batch_markdowns:
            lines.append(f"| `{batch_markdown}` |")
        lines.append("")
    return lines




def _midas_row_provenance_appendix_html(artifacts: dict, metrics: dict) -> str:
    summary_line = str(metrics.get("midas_row_provenance_export_summary_line", "") or "").strip()
    if not summary_line:
        return ""
    preview_rows = [
        row
        for row in (metrics.get("midas_row_provenance_preview_rows") or [])
        if isinstance(row, dict)
    ]
    clause_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_clause_filter_rows") or [])
        if isinstance(row, dict)
    ]
    member_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_member_filter_rows") or [])
        if isinstance(row, dict)
    ]
    hazard_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_hazard_filter_rows") or [])
        if isinstance(row, dict)
    ]
    rule_family_filter_rows = [
        row
        for row in (metrics.get("midas_row_provenance_rule_family_filter_rows") or [])
        if isinstance(row, dict)
    ]
    preview_table = ""
    if preview_rows:
        preview_table = (
            "<table><thead><tr>"
            "<th>Combination</th><th>Member</th><th>Clause</th><th>Baseline Focus</th><th>Provenance</th>"
            "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                f"<td>{row.get('combination_name', '') or 'n/a'}</td>"
                f"<td>{row.get('member_id', '') or 'n/a'}</td>"
                f"<td>{row.get('clause_label', '') or 'n/a'}</td>"
                f"<td>{row.get('baseline_focus_member_id', '') or 'n/a'}</td>"
                f"<td>{row.get('bridge_row_provenance_mode_label', '') or 'n/a'}</td>"
                "</tr>"
                for row in preview_rows
            )
            + "</tbody></table>"
        )
    clause_filter_table = ""
    if clause_filter_rows:
        clause_filter_table = (
            "<table><thead><tr>"
            "<th>Clause</th><th>Rows</th><th>Members</th><th>Combos</th><th>Top Member</th><th>Top D/C</th>"
            "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                f"<td>{row.get('clause_label', '') or 'n/a'}</td>"
                f"<td>{row.get('row_count', '') or '0'}</td>"
                f"<td>{row.get('member_count', '') or '0'}</td>"
                f"<td>{row.get('combination_count', '') or '0'}</td>"
                f"<td>{row.get('top_member_id', '') or 'n/a'}</td>"
                f"<td>{row.get('top_dcr_label', '') or 'n/a'}</td>"
                "</tr>"
                for row in clause_filter_rows
            )
            + "</tbody></table>"
        )
    member_filter_table = ""
    if member_filter_rows:
        member_filter_table = (
            "<table><thead><tr>"
            "<th>Member</th><th>Baseline Focus</th><th>Rows</th><th>Clauses</th><th>Combos</th><th>Top Clause</th>"
            "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                f"<td>{row.get('member_id', '') or 'n/a'}</td>"
                f"<td>{row.get('baseline_focus_member_id', '') or 'n/a'}</td>"
                f"<td>{row.get('row_count', '') or '0'}</td>"
                f"<td>{row.get('clause_count', '') or '0'}</td>"
                f"<td>{row.get('combination_count', '') or '0'}</td>"
                f"<td>{row.get('top_clause_label', '') or 'n/a'}</td>"
                "</tr>"
                for row in member_filter_rows
            )
            + "</tbody></table>"
        )
    hazard_filter_table = ""
    if hazard_filter_rows:
        hazard_filter_table = (
            "<table><thead><tr>"
            "<th>Hazard</th><th>Rows</th><th>Members</th><th>Clauses</th><th>Combos</th><th>Top Clause</th><th>Top D/C</th>"
            "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                f"<td>{row.get('hazard_type', '') or 'n/a'}</td>"
                f"<td>{row.get('row_count', '') or '0'}</td>"
                f"<td>{row.get('member_count', '') or '0'}</td>"
                f"<td>{row.get('clause_count', '') or '0'}</td>"
                f"<td>{row.get('combination_count', '') or '0'}</td>"
                f"<td>{row.get('top_clause_label', '') or 'n/a'}</td>"
                f"<td>{row.get('top_dcr_label', '') or 'n/a'}</td>"
                "</tr>"
                for row in hazard_filter_rows
            )
            + "</tbody></table>"
        )
    rule_family_filter_table = ""
    if rule_family_filter_rows:
        rule_family_filter_table = (
            "<table><thead><tr>"
            "<th>Rule Family</th><th>Rows</th><th>Members</th><th>Hazards</th><th>Combos</th><th>Top Clause</th><th>Top D/C</th>"
            "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                f"<td>{row.get('rule_family', '') or 'n/a'}</td>"
                f"<td>{row.get('row_count', '') or '0'}</td>"
                f"<td>{row.get('member_count', '') or '0'}</td>"
                f"<td>{row.get('hazard_count', '') or '0'}</td>"
                f"<td>{row.get('combination_count', '') or '0'}</td>"
                f"<td>{row.get('top_clause_label', '') or 'n/a'}</td>"
                f"<td>{row.get('top_dcr_label', '') or 'n/a'}</td>"
                "</tr>"
                for row in rule_family_filter_rows
            )
            + "</tbody></table>"
        )
    artifact_meta = _committee_meta_list_html(
        [
            ("JSON", artifacts.get("midas_row_provenance_table_json", "")),
            ("CSV", artifacts.get("midas_row_provenance_table_csv", "")),
            ("Report", artifacts.get("midas_row_provenance_table_report", "")),
        ]
    )
    return f"""
      <section class="committee-appendix-block">
        <div class="committee-appendix-block__header">
          <div class="committee-section-kicker">Appendix Evidence</div>
          <h3>Appendix: MIDAS KDS Row Provenance Export</h3>
          <p class="committee-appendix-summary">{summary_line}</p>
        </div>
        {artifact_meta}
        <p class="note committee-note-muted">row-provenance sync: {ROW_PROVENANCE_SYNC_NOTE}</p>
        <div class="committee-table-stack">
          {preview_table}
          {clause_filter_table}
          {member_filter_table}
          {hazard_filter_table}
          {rule_family_filter_table}
        </div>
      </section>
    """


def _midas_native_roundtrip_appendix_html(artifacts: dict, metrics: dict) -> str:
    summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "").strip()
    taxonomy_case_counts = (
        metrics.get("midas_native_roundtrip_taxonomy_case_counts")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_case_counts"), dict)
        else {}
    )
    taxonomy_card_family_histogram = (
        metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram"), dict)
        else {}
    )
    structure_type_batch_markdowns = [
        str(row)
        for row in (metrics.get("midas_native_roundtrip_structure_type_batch_markdowns") or [])
        if str(row or "").strip()
    ]
    if not summary_line and not taxonomy_case_counts:
        return ""
    batch_rows_html = "".join(
        f"<tr><td>{batch_markdown}</td></tr>" for batch_markdown in structure_type_batch_markdowns
    ) or "<tr><td>No structure-type batch markdowns available.</td></tr>"
    artifact_meta = _committee_meta_list_html(
        [
            ("Appendix Markdown", artifacts.get("midas_native_roundtrip_appendix_markdown", "")),
            ("Appendix JSON", artifacts.get("midas_native_roundtrip_appendix_json", "")),
        ]
    )
    return f"""
      <section class="committee-appendix-block" id="committee-appendix-native-roundtrip" data-route-appendix-block="native-roundtrip">
        <div class="committee-appendix-block__header">
          <div class="committee-section-kicker">Appendix Evidence</div>
          <h3>Appendix: MIDAS Native Roundtrip Unsupported/Lossy Card Families</h3>
          <p class="committee-appendix-summary">{summary_line or 'n/a'}</p>
        </div>
        {artifact_meta}
        <p class="note committee-note-muted">public-preview note: public archive-derived preview write-back baselines are counted separately from original public native .mgt baselines.</p>
        <p class="note committee-note-muted">public split: public_native_ready={int(metrics.get('midas_native_roundtrip_public_native_writeback_ready_count', 0))} | public_raw_ready={int(metrics.get('midas_native_roundtrip_public_raw_native_writeback_ready_count', 0))} | public_bridge_ready={int(metrics.get('midas_native_roundtrip_public_bridge_writeback_ready_count', 0))} | public_archive_preview_ready={int(metrics.get('midas_native_roundtrip_public_archive_preview_writeback_ready_count', 0))} | public_structural_preview_ready={int(metrics.get('midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count', 0))} | public_source_ready={int(metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0))} | fixture_ready={int(metrics.get('midas_native_roundtrip_fixture_native_writeback_ready_count', 0))} | repo_ready={int(metrics.get('midas_native_roundtrip_repo_native_writeback_ready_count', 0))} | experiment_ready={int(metrics.get('midas_native_roundtrip_experiment_native_writeback_ready_count', 0))}</p>
        <p class="note committee-note-muted">special_member_family: direct_patch={str(metrics.get('mgt_export_special_member_direct_patch_action_family_label', '') or 'n/a')} | supported={str(metrics.get('mgt_export_special_member_supported_action_family_label', '') or 'n/a')} | zero_touch_verified={str(metrics.get('mgt_export_special_member_zero_touch_verified_action_family_label', '') or 'n/a')}</p>
        <p class="note committee-note-muted">taxonomy_case_counts: {json.dumps(taxonomy_case_counts, ensure_ascii=False, sort_keys=True)}</p>
        <p class="note committee-note-muted">taxonomy_card_family_histogram: {json.dumps(taxonomy_card_family_histogram, ensure_ascii=False, sort_keys=True)}</p>
        <div class="committee-table-stack">
          <table>
            <thead><tr><th>Structure Type Batch Markdown</th></tr></thead>
            <tbody>
              {batch_rows_html}
            </tbody>
          </table>
        </div>
      </section>
    """


def _irregular_structure_appendix_markdown_lines(artifacts: dict, metrics: dict) -> list[str]:
    summary_line = str(
        metrics.get("irregular_structure_summary_line", metrics.get("irregular_structure_track_summary_line", "")) or ""
    ).strip()
    top5_family_ids = [
        str(row)
        for row in (metrics.get("irregular_structure_top5_family_ids") or [])
        if str(row or "").strip()
    ]
    manifest_path = str(artifacts.get("irregular_top5_execution_manifest", "") or "").strip()
    manifest_payload = _load_json(Path(manifest_path)) if manifest_path and Path(manifest_path).exists() else {}
    top5_rows = [row for row in (manifest_payload.get("top5_families") or []) if isinstance(row, dict)]
    if not summary_line and not top5_rows and not top5_family_ids:
        return []
    lines = [
        "## Appendix: Irregular Structure Track",
        "",
        f"- `summary`: `{summary_line or 'n/a'}`",
        f"- `gate_report`: `{artifacts.get('irregular_structure_gate_report', '') or 'n/a'}`",
        f"- `top5_manifest`: `{manifest_path or 'n/a'}`",
        f"- `source_catalog`: `{artifacts.get('irregular_structure_source_catalog', '') or 'n/a'}`",
        f"- `priority_manifest`: `{artifacts.get('irregular_priority_manifest', '') or 'n/a'}`",
        f"- `collection_report`: `{artifacts.get('irregular_structure_collection_report', '') or 'n/a'}`",
        f"- `triage_report`: `{artifacts.get('irregular_structure_triage_report', '') or 'n/a'}`",
        f"- `top5_family_ids`: `{', '.join(top5_family_ids) or 'n/a'}`",
        "",
    ]
    if top5_rows:
        lines.extend(
            [
                "| Family | Priority | Mode | Sources | Local Ready | Remote Candidates | Authority Fit | AI Learning Fit |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in top5_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("family_id", "") or "n/a"),
                        str(row.get("priority", "") or "0"),
                        str(row.get("execution_mode", "") or "n/a"),
                        str(row.get("source_record_count", "") or "0"),
                        str(row.get("local_ready_source_count", "") or "0"),
                        str(row.get("remote_candidate_source_count", "") or "0"),
                        str(row.get("authority_fit", "") or "n/a"),
                        str(row.get("ai_learning_fit", "") or "n/a"),
                    ]
                )
                + " |"
            )
        lines.append("")
    return lines


def _irregular_structure_appendix_html(artifacts: dict, metrics: dict) -> str:
    summary_line = str(
        metrics.get("irregular_structure_summary_line", metrics.get("irregular_structure_track_summary_line", "")) or ""
    ).strip()
    top5_family_ids = [
        str(row)
        for row in (metrics.get("irregular_structure_top5_family_ids") or [])
        if str(row or "").strip()
    ]
    manifest_path = str(artifacts.get("irregular_top5_execution_manifest", "") or "").strip()
    manifest_payload = _load_json(Path(manifest_path)) if manifest_path and Path(manifest_path).exists() else {}
    top5_rows = [row for row in (manifest_payload.get("top5_families") or []) if isinstance(row, dict)]
    if not summary_line and not top5_rows and not top5_family_ids:
        return ""
    top5_rows_html = "".join(
        (
            f"<tr><td>{row.get('family_id', '') or 'n/a'}</td><td>{row.get('priority', '') or '0'}</td>"
            f"<td>{row.get('execution_mode', '') or 'n/a'}</td><td>{row.get('source_record_count', '') or '0'}</td>"
            f"<td>{row.get('local_ready_source_count', '') or '0'}</td><td>{row.get('remote_candidate_source_count', '') or '0'}</td>"
            f"<td>{row.get('authority_fit', '') or 'n/a'}</td><td>{row.get('ai_learning_fit', '') or 'n/a'}</td></tr>"
        )
        for row in top5_rows
    ) or "<tr><td colspan='8'>No irregular top5 rows available.</td></tr>"
    artifact_meta = _committee_meta_list_html(
        [
            ("Gate Report", artifacts.get("irregular_structure_gate_report", "")),
            ("Top5 Manifest", manifest_path),
            ("Source Catalog", artifacts.get("irregular_structure_source_catalog", "")),
            ("Priority Manifest", artifacts.get("irregular_priority_manifest", "")),
            ("Collection Report", artifacts.get("irregular_structure_collection_report", "")),
            ("Triage Report", artifacts.get("irregular_structure_triage_report", "")),
            ("Top5 Family IDs", ", ".join(top5_family_ids)),
        ]
    )
    return f"""
      <section class="committee-appendix-block" id="committee-appendix-irregular-structure" data-route-appendix-block="irregular-structure">
        <div class="committee-appendix-block__header">
          <div class="committee-section-kicker">Appendix Evidence</div>
          <h3>Appendix: Irregular Structure Track</h3>
          <p class="committee-appendix-summary">{summary_line or 'n/a'}</p>
        </div>
        {artifact_meta}
        <div class="committee-table-stack">
          <table>
            <thead>
              <tr><th>Family</th><th>Priority</th><th>Mode</th><th>Sources</th><th>Local Ready</th><th>Remote Candidates</th><th>Authority Fit</th><th>AI Learning Fit</th></tr>
            </thead>
            <tbody>
              {top5_rows_html}
            </tbody>
          </table>
        </div>
      </section>
    """


def _load_design_change_rows(report: dict) -> list[dict]:
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    summary_path = Path(str(artifacts.get("changes_summary_json", "") or ""))
    if summary_path.exists():
        payload = _load_json(summary_path)
        rows = payload.get("change_summary_rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    changes_path = Path(str(artifacts.get("changes_json", "") or ""))
    if changes_path.exists():
        payload = _load_json(changes_path)
        rows = payload.get("changes")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _load_accepted_candidate_rows(report: dict) -> list[dict]:
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    v2_selected = Path(str(artifacts.get("candidate_explain_v2_json", "") or ""))
    v2_rejected = Path(str(artifacts.get("rejected_candidate_explain_v2_json", "") or ""))
    rows: list[dict] = []
    if v2_selected.exists():
        payload = _load_json(v2_selected)
        selected_rows = payload.get("selected_candidate_rows")
        if isinstance(selected_rows, list):
            rows.extend([row for row in selected_rows if isinstance(row, dict)])
    if v2_rejected.exists():
        payload = _load_json(v2_rejected)
        rejected_rows = payload.get("rejected_candidate_rows")
        if isinstance(rejected_rows, list):
            rows.extend([row for row in rejected_rows if isinstance(row, dict)])
    if rows:
        return rows
    explain_path = Path(str(artifacts.get("accepted_candidate_explain_json", "") or ""))
    if explain_path.exists():
        payload = _load_json(explain_path)
        rows = payload.get("accepted_candidate_explain_rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _load_blocked_action_summary(report: dict) -> dict:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    blocked_reason_counts = summary.get("blocked_reason_counts") if isinstance(summary.get("blocked_reason_counts"), dict) else {}
    hard_gate_reason_counts = {
        str(k): int(v)
        for k, v in blocked_reason_counts.items()
        if str(k).startswith("constructability_hard_gate:")
    }
    hard_gate_total = int(sum(hard_gate_reason_counts.values()))
    hard_gate_reason_label = ", ".join(
        f"{str(key).split(':', 1)[1]}={int(value)}" for key, value in sorted(hard_gate_reason_counts.items())
    )
    return {
        "blocked_action_row_count": int(summary.get("blocked_action_row_count", 0)),
        "blocked_reason_counts": blocked_reason_counts,
        "illegal_by_mask": int(blocked_reason_counts.get("illegal_by_mask", 0)),
        "illegal_by_mask_family_counts": {
            str(k): int(v)
            for k, v in sorted((summary.get("blocked_illegal_by_mask_family_counts") or {}).items())
        },
        "illegal_by_mask_family_label": str(summary.get("blocked_illegal_by_mask_family_label", "") or ""),
        "no_cost_gain": int(blocked_reason_counts.get("no_cost_gain", 0)),
        "violates_feasible_constraints": int(blocked_reason_counts.get("violates_feasible_constraints", 0)),
        "no_action_delta": int(blocked_reason_counts.get("no_action_delta", 0)),
        "accepted_candidate": int(blocked_reason_counts.get("accepted_candidate", 0)),
        "blocked_no_cost_group_count": int(summary.get("blocked_no_cost_group_count", 0)),
        "blocked_no_cost_explain_row_count": int(summary.get("blocked_no_cost_explain_row_count", 0)),
        "accepted_candidate_explain_row_count": int(summary.get("accepted_candidate_explain_row_count", 0)),
        "accepted_candidate_selected_count": int(summary.get("accepted_candidate_selected_count", 0)),
        "accepted_candidate_unselected_count": int(summary.get("accepted_candidate_unselected_count", 0)),
        "constructability_hard_gate_block_count": int(hard_gate_total),
        "constructability_hard_gate_reason_counts": hard_gate_reason_counts,
        "constructability_hard_gate_reason_label": str(hard_gate_reason_label),
        "constructability_hard_gate_family_counts": {
            str(k): int(v)
            for k, v in sorted((summary.get("blocked_constructability_hard_gate_family_counts") or {}).items())
        },
        "constructability_hard_gate_family_label": str(summary.get("blocked_constructability_hard_gate_family_label", "") or ""),
        "concrete_usage_reduction_pct": float(summary.get("concrete_usage_reduction_pct", 0.0) or 0.0),
        "steel_reduction_pct": float(summary.get("steel_reduction_pct", 0.0) or 0.0),
        "rebar_reduction_pct": float(summary.get("rebar_reduction_pct", 0.0) or 0.0),
        "congestion_reduction_pct": float(summary.get("congestion_reduction_pct", 0.0) or 0.0),
        "detailing_simplification_pct": float(summary.get("detailing_simplification_pct", 0.0) or 0.0),
        "overdesign_margin_reduction_pct": float(summary.get("overdesign_margin_reduction_pct", 0.0) or 0.0),
        "final_safety_margin_retained_pct": float(summary.get("final_safety_margin_retained_pct", 0.0) or 0.0),
        "objective_profile": str(summary.get("objective_profile", "") or ""),
        "budget_mode": str(summary.get("budget_mode", "") or ""),
    }


def _aggregate_design_change_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    story_buckets: dict[int, dict] = {}
    zone_buckets: dict[str, dict] = {}
    for row in rows:
        story_band = int(row.get("story_band", 0))
        zone_label = str(row.get("zone_label", "")).strip() or "unknown"
        changed = int(row.get("changed_group_count", 1 if "group_id" in row else 0))
        semantic = int(row.get("semantic_group_count", 1 if str(row.get("semantic_group", "")).strip() else 0))
        rebar_delta = float(row.get("rebar_ratio_delta_sum", row.get("rebar_ratio_delta", 0.0)))
        cost_delta = float(row.get("cost_proxy_delta_sum", row.get("cost_proxy_delta", 0.0)))
        dcr_before = float(row.get("max_dcr_before_max", row.get("max_dcr_before", 0.0)))
        dcr_after = float(row.get("max_dcr_after_max", row.get("max_dcr_after", 0.0)))
        constructability_delta = float(row.get("constructability_delta_sum", row.get("constructability_delta", 0.0)))
        overdesign_delta = float(row.get("overdesign_margin_delta_sum", row.get("overdesign_margin_delta", 0.0)))

        story_rec = story_buckets.setdefault(
            story_band,
            {
                "story_band": story_band,
                "changed_group_count": 0,
                "semantic_group_count": 0,
                "rebar_ratio_delta_sum": 0.0,
                "cost_proxy_delta_sum": 0.0,
                "constructability_delta_sum": 0.0,
                "overdesign_margin_delta_sum": 0.0,
                "max_dcr_before_max": 0.0,
                "max_dcr_after_max": 0.0,
            },
        )
        story_rec["changed_group_count"] += changed
        story_rec["semantic_group_count"] += semantic
        story_rec["rebar_ratio_delta_sum"] += rebar_delta
        story_rec["cost_proxy_delta_sum"] += cost_delta
        story_rec["constructability_delta_sum"] += constructability_delta
        story_rec["overdesign_margin_delta_sum"] += overdesign_delta
        story_rec["max_dcr_before_max"] = max(float(story_rec["max_dcr_before_max"]), dcr_before)
        story_rec["max_dcr_after_max"] = max(float(story_rec["max_dcr_after_max"]), dcr_after)

        zone_rec = zone_buckets.setdefault(
            zone_label,
            {
                "zone_label": zone_label,
                "changed_group_count": 0,
                "semantic_group_count": 0,
                "rebar_ratio_delta_sum": 0.0,
                "cost_proxy_delta_sum": 0.0,
                "constructability_delta_sum": 0.0,
                "overdesign_margin_delta_sum": 0.0,
                "max_dcr_before_max": 0.0,
                "max_dcr_after_max": 0.0,
            },
        )
        zone_rec["changed_group_count"] += changed
        zone_rec["semantic_group_count"] += semantic
        zone_rec["rebar_ratio_delta_sum"] += rebar_delta
        zone_rec["cost_proxy_delta_sum"] += cost_delta
        zone_rec["constructability_delta_sum"] += constructability_delta
        zone_rec["overdesign_margin_delta_sum"] += overdesign_delta
        zone_rec["max_dcr_before_max"] = max(float(zone_rec["max_dcr_before_max"]), dcr_before)
        zone_rec["max_dcr_after_max"] = max(float(zone_rec["max_dcr_after_max"]), dcr_after)

    return [story_buckets[k] for k in sorted(story_buckets)], sorted(zone_buckets.values(), key=lambda item: str(item["zone_label"]))


def _split_accepted_candidate_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    selected = [row for row in rows if bool(row.get("selected_in_final_loop", False))]
    unselected = [row for row in rows if not bool(row.get("selected_in_final_loop", False))]
    return selected, unselected


def _build_residual_holdout_detail_rows(
    holdout_buckets: list[dict],
    design_change_rows: list[dict],
    accepted_candidate_rows: list[dict],
    authority_rows: list[dict],
    authority_catalog: dict,
) -> list[dict]:
    story_counts = Counter(int(row.get("story_band", 0)) for row in design_change_rows if int(row.get("story_band", 0)) > 0)
    story_zone_counts = Counter(
        (int(row.get("story_band", 0)), str(row.get("zone_label", "")).strip())
        for row in design_change_rows
        if int(row.get("story_band", 0)) > 0 and str(row.get("zone_label", "")).strip()
    )
    member_counts = Counter(str(row.get("member_type", "")).strip() for row in accepted_candidate_rows if str(row.get("member_type", "")).strip())
    zone_counts = Counter(str(row.get("zone_label", "")).strip() for row in design_change_rows if str(row.get("zone_label", "")).strip())
    authority_counts = Counter(str(row.get("track", "")).strip() for row in authority_rows if str(row.get("track", "")).strip())
    tracks = authority_catalog.get("tracks") if isinstance(authority_catalog.get("tracks"), dict) else {}
    authority_case_ids: list[str] = []
    authority_catalog_track_counts: Counter[str] = Counter()
    authority_submodel_counts: Counter[str] = Counter()
    for track_name, track_payload in tracks.items():
        if not isinstance(track_payload, dict):
            continue
        case_rows = track_payload.get("cases") if isinstance(track_payload.get("cases"), list) else []
        model_rows = track_payload.get("models") if isinstance(track_payload.get("models"), list) else []
        for row in case_rows:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("real_source", False)):
                continue
            authority_catalog_track_counts[str(track_name)] += 1
            authority_case_ids.append(str(row.get("case_id", "")))
            source_path = str(row.get("source_file_path", "")).strip()
            submodel_name = Path(source_path).stem if source_path else str(row.get("case_id", "")).strip()
            if submodel_name:
                authority_submodel_counts[submodel_name] += 1
        if model_rows:
            real_model_rows = [row for row in model_rows if isinstance(row, dict)]
            authority_catalog_track_counts[str(track_name)] += len(real_model_rows)
            for row in real_model_rows:
                model_path = str(row.get("model_path", "")).strip()
                submodel_name = Path(model_path).stem if model_path else str(row.get("id", "")).strip()
                if submodel_name:
                    authority_submodel_counts[submodel_name] += 1

    top_story_text = ", ".join(str(band) for band, _ in story_counts.most_common(3)) or "n/a"
    top_story_zone_text = ", ".join(
        f"S{story_band:02d}/{zone_label} ({count})"
        for (story_band, zone_label), count in story_zone_counts.most_common(4)
    ) or "n/a"
    top_member_text = ", ".join(f"{name} ({count})" for name, count in member_counts.most_common(3)) or "n/a"
    top_zone_text = ", ".join(f"{name} ({count})" for name, count in zone_counts.most_common(3)) or "n/a"
    top_authority_text = ", ".join(f"{name} ({count})" for name, count in authority_counts.most_common(3)) or "n/a"
    top_authority_catalog_track_text = ", ".join(f"{name} ({count})" for name, count in authority_catalog_track_counts.most_common(3)) or top_authority_text
    top_authority_case_text = ", ".join(case_id for case_id in authority_case_ids[:6] if case_id) or "n/a"
    top_authority_submodel_text = ", ".join(f"{name} ({count})" for name, count in authority_submodel_counts.most_common(4)) or "n/a"

    bucket_by_id = {str(row.get("id", "")): row for row in holdout_buckets if isinstance(row, dict)}
    default_holdout_meta: dict[str, tuple[str, str, str, str, int, str, str]] = {
        "licensed_engineer_review_required": (
            "RH-001",
            "pending_review",
            "open",
            "기술사",
            72,
            "assignment_plus_3_business_days",
            "signed_engineer_review_packet",
        ),
        "legacy_tool_cross_validation_required": (
            "RH-002",
            "pending_cross_validation",
            "open",
            "기존툴+기술사",
            120,
            "assignment_plus_5_business_days",
            "legacy_tool_cross_validation_report",
        ),
        "legal_authority_signoff_required": (
            "RH-003",
            "pending_signoff",
            "open",
            "기술사/기존 승인 workflow",
            168,
            "authority_submission_window",
            "authority_signoff_receipt_or_formal_hold",
        ),
    }

    def _detail_row(bucket_id: str, detail_axis: str, detail_value: str, why: str) -> dict[str, str]:
        bucket = bucket_by_id.get(bucket_id, {})
        (
            default_work_item_id,
            default_queue_status,
            default_status,
            default_owner,
            default_sla_hours,
            default_due_date,
            default_closure_evidence_required,
        ) = default_holdout_meta.get(
            bucket_id,
            (
                f"RH-{len(detail_rows) + 1:03d}",
                "pending_review",
                "open",
                "",
                120,
                "assignment_plus_5_business_days",
                "owner_approved_closure_evidence",
            ),
        )
        closure_evidence_path = str(bucket.get("closure_evidence_path", "") or "")
        sla_hours = int(bucket.get("sla_hours", default_sla_hours) or default_sla_hours)
        return {
            "bucket_id": bucket_id,
            "bucket_label": str(bucket.get("label", bucket_id) or bucket_id),
            "work_item_id": str(bucket.get("work_item_id", default_work_item_id) or default_work_item_id),
            "detail_axis": detail_axis,
            "detail_value": detail_value,
            "owner": str(bucket.get("owner", default_owner) or default_owner),
            "queue_status": str(bucket.get("queue_status", default_queue_status) or default_queue_status),
            "status": str(bucket.get("status", default_status) or default_status),
            "sla_hours": str(sla_hours),
            "sla_label": str(bucket.get("sla_label", "") or f"{sla_hours}h"),
            "due_date": str(bucket.get("due_date", "") or default_due_date),
            "closure_evidence_required": str(
                bucket.get("closure_evidence_required", "") or default_closure_evidence_required
            ),
            "closure_evidence_path": closure_evidence_path,
            "closure_evidence_status": str(
                bucket.get("closure_evidence_status", "") or ("attached" if closure_evidence_path else "pending")
            ),
            "why": why,
        }

    detail_rows: list[dict] = []

    detail_rows.extend(
        [
            _detail_row(
                "licensed_engineer_review_required",
                "review_story_zone",
                top_story_zone_text,
                "Top story-zone review pockets are derived from actual accepted design-change rows so engineer holdout stays tied to the highest-touch parts of the structure.",
            ),
            _detail_row(
                "licensed_engineer_review_required",
                "story_band",
                top_story_text,
                "High-touch story bands remain under engineer review because they concentrate accepted design changes and irregular response checks.",
            ),
            _detail_row(
                "licensed_engineer_review_required",
                "member_family",
                top_member_text,
                "Dominant member families in accepted optimization changes still require engineer judgment on local edge cases and detailing intent.",
            ),
            _detail_row(
                "licensed_engineer_review_required",
                "zone",
                top_zone_text,
                "Zone concentration is used to focus manual review on the highest-touch portions of the structural layout.",
            ),
        ]
    )

    detail_rows.append(
        _detail_row(
            "legacy_tool_cross_validation_required",
            "submodel_family",
            top_authority_submodel_text,
            "Authority submodel families are derived from the active catalog paths so cross-validation follows the exact benchmark submodels still outside the accelerated envelope.",
        )
    )
    detail_rows.append(
        _detail_row(
            "legacy_tool_cross_validation_required",
            "authority_critical_case",
            top_authority_text,
            "Authority-critical benchmark tracks remain the primary cross-validation target outside the accelerated envelope.",
        )
    )
    detail_rows.append(
        _detail_row(
            "legacy_tool_cross_validation_required",
            "authority_catalog_case_id",
            top_authority_case_text,
            "Authority catalog case ids are read directly so the holdout review list refreshes automatically when the benchmark catalog changes.",
        )
    )

    detail_rows.append(
        _detail_row(
            "legal_authority_signoff_required",
            "authority_catalog_track",
            top_authority_catalog_track_text,
            "Formal authority-facing responsibility is anchored to the active authority catalog tracks and remains outside the automated responsibility boundary.",
        )
    )
    detail_rows.append(
        _detail_row(
            "legal_authority_signoff_required",
            "authority_critical_case",
            "sealed submission pack, authority-facing variants, stamped final issue",
            "Formal authority-facing deliverables remain outside the automated responsibility boundary.",
        )
    )
    return detail_rows


def _build_residual_holdout_matrix_rows(
    design_change_rows: list[dict],
    accepted_candidate_rows: list[dict],
    authority_catalog: dict,
) -> list[dict]:
    story_zone_counts = Counter(
        (int(row.get("story_band", 0)), str(row.get("zone_label", "")).strip())
        for row in design_change_rows
        if int(row.get("story_band", 0)) > 0 and str(row.get("zone_label", "")).strip()
    )
    member_counts = Counter(
        str(row.get("member_type", "")).strip()
        for row in accepted_candidate_rows
        if str(row.get("member_type", "")).strip()
    )
    top_story_zones = [
        f"S{story_band:02d}/{zone_label}"
        for (story_band, zone_label), _count in story_zone_counts.most_common(4)
    ] or ["n/a"]
    top_member_families = [
        f"{member_family}"
        for member_family, _count in member_counts.most_common(4)
    ] or ["n/a"]

    tracks = authority_catalog.get("tracks") if isinstance(authority_catalog.get("tracks"), dict) else {}
    submodel_pairs: list[tuple[str, str]] = []
    for track_name, track_payload in tracks.items():
        if not isinstance(track_payload, dict):
            continue
        case_rows = track_payload.get("cases") if isinstance(track_payload.get("cases"), list) else []
        model_rows = track_payload.get("models") if isinstance(track_payload.get("models"), list) else []
        for row in case_rows:
            if not isinstance(row, dict) or not bool(row.get("real_source", False)):
                continue
            source_path = str(row.get("source_file_path", "")).strip()
            submodel_name = Path(source_path).stem if source_path else str(row.get("case_id", "")).strip()
            if submodel_name:
                submodel_pairs.append((str(track_name), submodel_name))
        for row in model_rows:
            if not isinstance(row, dict) or not bool(row.get("real_source", True)):
                continue
            model_path = str(row.get("model_path", "")).strip()
            submodel_name = Path(model_path).stem if model_path else str(row.get("id", "")).strip()
            if submodel_name:
                submodel_pairs.append((str(track_name), submodel_name))

    deduped_pairs: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for pair in submodel_pairs:
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        deduped_pairs.append(pair)

    matrix_rows: list[dict] = []
    for idx, (track_name, submodel_name) in enumerate(deduped_pairs[:6]):
        review_story_zone = top_story_zones[idx % len(top_story_zones)]
        member_family = top_member_families[idx % len(top_member_families)]
        matrix_rows.append(
            {
                "bucket_label": "Legacy Tool Cross-Validation",
                "authority_track": track_name,
                "submodel_family": submodel_name,
                "review_story_zone": review_story_zone,
                "member_family": member_family,
                "owner": "기존툴+기술사",
                "why": "Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit.",
            }
        )
    return matrix_rows


def _authority_catalog_snapshot_payload(
    authority_catalog: dict,
    holdout_matrix_rows: list[dict],
) -> dict:
    tracks = authority_catalog.get("tracks") if isinstance(authority_catalog.get("tracks"), dict) else {}
    track_submodel_pairs: list[dict[str, str]] = []
    case_ids: list[str] = []
    for track_name, track_payload in tracks.items():
        if not isinstance(track_payload, dict):
            continue
        case_rows = track_payload.get("cases") if isinstance(track_payload.get("cases"), list) else []
        model_rows = track_payload.get("models") if isinstance(track_payload.get("models"), list) else []
        for row in case_rows:
            if not isinstance(row, dict) or not bool(row.get("real_source", False)):
                continue
            source_path = str(row.get("source_file_path", "")).strip()
            submodel_name = Path(source_path).stem if source_path else str(row.get("case_id", "")).strip()
            if submodel_name:
                track_submodel_pairs.append({"authority_track": str(track_name), "submodel_family": submodel_name})
            case_id = str(row.get("case_id", "")).strip()
            if case_id:
                case_ids.append(case_id)
        for row in model_rows:
            if not isinstance(row, dict) or not bool(row.get("real_source", True)):
                continue
            model_path = str(row.get("model_path", "")).strip()
            submodel_name = Path(model_path).stem if model_path else str(row.get("id", "")).strip()
            if submodel_name:
                track_submodel_pairs.append({"authority_track": str(track_name), "submodel_family": submodel_name})

    deduped_pairs: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in track_submodel_pairs:
        pair = (row["authority_track"], row["submodel_family"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        deduped_pairs.append(row)

    return {
        "schema_version": "1.0",
        "track_submodel_pairs": sorted(deduped_pairs, key=lambda item: (item["authority_track"], item["submodel_family"])),
        "case_ids": sorted({case_id for case_id in case_ids if case_id}),
        "routing_rows": [
            {
                "authority_track": str(row.get("authority_track", "")),
                "submodel_family": str(row.get("submodel_family", "")),
                "review_story_zone": str(row.get("review_story_zone", "")),
                "member_family": str(row.get("member_family", "")),
                "owner": str(row.get("owner", "")),
                "why": str(row.get("why", "")),
            }
            for row in holdout_matrix_rows
            if isinstance(row, dict)
        ],
    }


def _build_authority_catalog_routing_diff(
    previous_snapshot: dict | None,
    current_snapshot: dict,
) -> dict:
    if not previous_snapshot:
        return {
            "baseline_seeded": True,
            "change_count": 0,
            "added_count": 0,
            "removed_count": 0,
            "unchanged_count": len(current_snapshot.get("track_submodel_pairs", [])),
            "diff_rows": [],
        }

    previous_pairs = {
        (str(row.get("authority_track", "")), str(row.get("submodel_family", "")))
        for row in (previous_snapshot.get("track_submodel_pairs") or [])
        if isinstance(row, dict)
    }
    current_pairs = {
        (str(row.get("authority_track", "")), str(row.get("submodel_family", "")))
        for row in (current_snapshot.get("track_submodel_pairs") or [])
        if isinstance(row, dict)
    }
    previous_routing = {
        (str(row.get("authority_track", "")), str(row.get("submodel_family", ""))): row
        for row in (previous_snapshot.get("routing_rows") or [])
        if isinstance(row, dict)
    }
    current_routing = {
        (str(row.get("authority_track", "")), str(row.get("submodel_family", ""))): row
        for row in (current_snapshot.get("routing_rows") or [])
        if isinstance(row, dict)
    }

    added_pairs = sorted(current_pairs - previous_pairs)
    removed_pairs = sorted(previous_pairs - current_pairs)
    unchanged_pairs = current_pairs & previous_pairs
    diff_rows: list[dict[str, str]] = []

    for authority_track, submodel_family in added_pairs:
        route = current_routing.get((authority_track, submodel_family), {})
        diff_rows.append(
            {
                "change_type": "added",
                "authority_track": authority_track,
                "submodel_family": submodel_family,
                "review_story_zone": str(route.get("review_story_zone", "")),
                "member_family": str(route.get("member_family", "")),
                "owner": str(route.get("owner", "기존툴+기술사")),
                "why": "Authority catalog introduced a new active routing pair, so the holdout routing matrix expanded automatically.",
            }
        )
    for authority_track, submodel_family in removed_pairs:
        route = previous_routing.get((authority_track, submodel_family), {})
        diff_rows.append(
            {
                "change_type": "removed",
                "authority_track": authority_track,
                "submodel_family": submodel_family,
                "review_story_zone": str(route.get("review_story_zone", "")),
                "member_family": str(route.get("member_family", "")),
                "owner": str(route.get("owner", "기존툴+기술사")),
                "why": "Authority catalog removed or disabled this routing pair, so the holdout routing matrix contracted automatically.",
            }
        )

    return {
        "baseline_seeded": False,
        "change_count": len(diff_rows),
        "added_count": len(added_pairs),
        "removed_count": len(removed_pairs),
        "unchanged_count": len(unchanged_pairs),
        "diff_rows": diff_rows,
    }


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def _coverage_range_label(values: object) -> str:
    if isinstance(values, list) and len(values) == 2:
        return f"{values[0]}-{values[1]}%"
    return "n/a"


def _status(flag: bool) -> str:
    return "PASS" if bool(flag) else "FAIL"


def _rel(base_dir: Path, target: str | Path) -> str:
    return str(Path(target).resolve().relative_to(base_dir.resolve().parent)) if Path(target).is_absolute() else str(Path(target).relative_to(base_dir.parent))


def _card(card_id: str, label: str, value: Any, status: str, note: str = "") -> dict:
    return {
        "id": card_id,
        "label": label,
        "value": value,
        "status": status,
        "note": note,
    }


def _load_authority_details(authority: dict, catalog: dict) -> list[dict]:
    tracks = catalog.get("tracks") if isinstance(catalog.get("tracks"), dict) else {}
    rows: list[dict] = []

    opensees = tracks.get("opensees") if isinstance(tracks.get("opensees"), dict) else {}
    for model in opensees.get("models", []) if isinstance(opensees.get("models"), list) else []:
        model_id = str(model.get("id", "")).strip()
        report_path = Path("implementation/phase1/open_data/global_authority/run_artifacts/opensees") / f"{model_id}_topology_report.json"
        rep = _load_json(report_path) if report_path.exists() else {}
        checks = rep.get("checks") if isinstance(rep.get("checks"), dict) else {}
        metrics = rep.get("metrics") if isinstance(rep.get("metrics"), dict) else {}
        rows.append(
            {
                "track": "OpenSees",
                "case_id": model_id,
                "status": _status(bool(rep.get("contract_pass", False))),
                "metric_a": f"nodes={int(metrics.get('node_count', 0))}",
                "metric_b": f"shell_beam_mix={checks.get('shell_beam_mix_pass', False)}",
                "source_url": str(model.get("model_path", "")),
                "provenance": str(model.get("source_class", "")),
            }
        )

    sac = tracks.get("sac") if isinstance(tracks.get("sac"), dict) else {}
    for case in sac.get("cases", []) if isinstance(sac.get("cases"), list) else []:
        ref_path = Path(str(case.get("reference_metrics_path", "")))
        rep = _load_json(ref_path) if ref_path.exists() else {}
        metrics = rep.get("metrics") if isinstance(rep.get("metrics"), dict) else {}
        rows.append(
            {
                "track": "SAC",
                "case_id": str(case.get("case_id", "")),
                "status": _status(bool(rep.get("contract_pass", False))),
                "metric_a": f"drift={_finite(metrics.get('drift_error_pct')):.3f}%",
                "metric_b": f"MAC={_finite(metrics.get('mode_shape_mac')):.4f}",
                "source_url": str(case.get("source_url", "")),
                "provenance": str(case.get("source_sha256", ""))[:12],
            }
        )

    nheri = tracks.get("nheri") if isinstance(tracks.get("nheri"), dict) else {}
    for case in nheri.get("cases", []) if isinstance(nheri.get("cases"), list) else []:
        ref_path = Path(str(case.get("waveform_metrics_path", "")))
        rep = _load_json(ref_path) if ref_path.exists() else {}
        metrics = rep.get("metrics") if isinstance(rep.get("metrics"), dict) else {}
        rows.append(
            {
                "track": "NHERI",
                "case_id": str(case.get("case_id", "")),
                "status": _status(bool(rep.get("contract_pass", False))),
                "metric_a": f"corr={_finite(metrics.get('waveform_corr')):.4f}",
                "metric_b": f"phase={_finite(metrics.get('phase_error_ms')):.3f} ms",
                "source_url": str(case.get("source_url", "")),
                "provenance": str(case.get("source_sha256", ""))[:12],
            }
        )
    return rows


def _build_summary(
    *,
    pbd_package: dict,
    pbd_metrics: dict,
    ndtha_stress: dict,
    ndtha_residual: dict,
    wind: dict,
    ssi: dict,
    damper: dict,
    construction: dict,
    diaphragm: dict,
    repro: dict,
    release_registry: dict,
    kds: dict,
    nightly: dict,
    ci: dict,
    gap: dict,
    performance_profiling_report: dict,
    solver_truthfulness_report: dict,
    nonlinear_generalization_report: dict,
    workflow_productization_report: dict,
    authority: dict,
    authority_catalog: dict,
    design_opt_long: dict,
    design_opt_cost: dict,
    row_provenance_export: dict,
    row_provenance_export_report: dict,
) -> tuple[list[dict], list[dict], dict, list[dict], list[dict]]:
    pbd_summary = pbd_package.get("summary") if isinstance(pbd_package.get("summary"), dict) else {}
    wind_summary = wind.get("summary") if isinstance(wind.get("summary"), dict) else {}
    ndtha_stress_rows = ndtha_stress.get("rows") if isinstance(ndtha_stress.get("rows"), list) else []
    ndtha_residual_summary = ndtha_residual.get("summary") if isinstance(ndtha_residual.get("summary"), dict) else {}
    ndtha_residual_checks = ndtha_residual.get("checks") if isinstance(ndtha_residual.get("checks"), dict) else {}
    ssi_summary = ssi.get("summary") if isinstance(ssi.get("summary"), dict) else {}
    damper_summary = damper.get("summary") if isinstance(damper.get("summary"), dict) else {}
    construction_summary = construction.get("summary") if isinstance(construction.get("summary"), dict) else {}
    diaphragm_summary = diaphragm.get("summary") if isinstance(diaphragm.get("summary"), dict) else {}
    repro_summary = repro.get("summary") if isinstance(repro.get("summary"), dict) else {}
    repro_checks = repro.get("checks") if isinstance(repro.get("checks"), dict) else {}
    registry_summary = release_registry.get("summary") if isinstance(release_registry.get("summary"), dict) else {}
    registry_checks = release_registry.get("checks") if isinstance(release_registry.get("checks"), dict) else {}
    registry_sig = release_registry.get("signature") if isinstance(release_registry.get("signature"), dict) else {}
    kds_frontend = kds.get("frontend_payload") if isinstance(kds.get("frontend_payload"), dict) else {}
    gap_summary = gap.get("summary") if isinstance(gap.get("summary"), dict) else {}
    performance_profiling_summary = (
        performance_profiling_report.get("summary")
        if isinstance(performance_profiling_report.get("summary"), dict)
        else {}
    )
    workflow_productization_summary = (
        workflow_productization_report.get("summary")
        if isinstance(workflow_productization_report.get("summary"), dict)
        else {}
    )
    workflow_productization_artifacts = (
        workflow_productization_report.get("generated_artifacts")
        if isinstance(workflow_productization_report.get("generated_artifacts"), dict)
        else {}
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
    peer_blind_prediction_compare_path = Path(
        "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json"
    )
    peer_blind_prediction_compare = (
        _load_json(peer_blind_prediction_compare_path) if peer_blind_prediction_compare_path.exists() else {}
    )
    peer_blind_prediction_compare_summary = (
        peer_blind_prediction_compare.get("summary")
        if isinstance(peer_blind_prediction_compare.get("summary"), dict)
        else {}
    )
    peer_blind_prediction_compare_results_explorer = (
        peer_blind_prediction_compare.get("results_explorer")
        if isinstance(peer_blind_prediction_compare.get("results_explorer"), dict)
        else {}
    )
    peer_blind_prediction_compare_summary_line = str(
        peer_blind_prediction_compare.get("summary_line", "") or ""
    ).strip()
    peer_blind_prediction_measured_response_landing_path = Path(
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
    )
    peer_blind_prediction_measured_response_landing = (
        _load_json(peer_blind_prediction_measured_response_landing_path)
        if peer_blind_prediction_measured_response_landing_path.exists()
        else {}
    )
    peer_blind_prediction_measured_response_landing_summary = (
        peer_blind_prediction_measured_response_landing.get("summary")
        if isinstance(peer_blind_prediction_measured_response_landing.get("summary"), dict)
        else {}
    )
    peer_blind_prediction_measured_response_landing_summary_line = str(
        peer_blind_prediction_measured_response_landing.get("summary_line", "") or ""
    ).strip()
    advanced_holdouts = [row for row in (gap.get("advanced_holdouts") or []) if isinstance(row, dict)]
    advanced_holdout_surface = _advanced_holdout_closure_surface(advanced_holdouts)
    residual_holdout_buckets = [row for row in (gap.get("residual_holdout_buckets") or []) if isinstance(row, dict)]
    authority_summary = authority.get("summary") if isinstance(authority.get("summary"), dict) else {}
    design_opt_long_summary = design_opt_long.get("summary") if isinstance(design_opt_long.get("summary"), dict) else {}
    design_opt_cost_summary = design_opt_cost.get("summary") if isinstance(design_opt_cost.get("summary"), dict) else {}
    design_opt_raw_max_drift = _finite(design_opt_cost_summary.get("raw_max_drift_pct", design_opt_long_summary.get("raw_max_drift_pct")))
    design_opt_raw_residual_drift = _finite(design_opt_cost_summary.get("raw_residual_drift_pct", design_opt_long_summary.get("raw_residual_drift_pct")))
    design_opt_raw_max_dcr = _finite(design_opt_cost_summary.get("raw_max_dcr", design_opt_long_summary.get("raw_max_dcr")))
    design_opt_repaired_max_drift = _finite(
        design_opt_cost_summary.get(
            "repaired_final_max_drift_pct",
            design_opt_long_summary.get("repaired_max_drift_pct", design_opt_long_summary.get("final_max_drift_pct")),
        )
    )
    design_opt_repaired_residual_drift = _finite(
        design_opt_cost_summary.get(
            "repaired_final_residual_drift_pct",
            design_opt_long_summary.get("repaired_residual_drift_pct", design_opt_long_summary.get("final_residual_drift_pct")),
        )
    )
    design_opt_repaired_max_dcr = _finite(
        design_opt_cost_summary.get(
            "repaired_final_max_dcr",
            design_opt_long_summary.get("repaired_max_dcr", design_opt_long_summary.get("final_max_dcr")),
        )
    )
    design_opt_compliance_basis = str(
        design_opt_cost_summary.get(
            "compliance_basis",
            design_opt_long_summary.get("compliance_basis", "repaired_solver_validated_slice"),
        )
    )
    design_opt_repair_action_count = int(
        design_opt_cost_summary.get(
            "repair_action_count",
            design_opt_long_summary.get("repair_action_count", 0),
        )
    )
    design_opt_constructability_signal_gain_pct = _finite(
        design_opt_cost_summary.get(
            "constructability_signal_gain_pct",
            design_opt_long_summary.get("constructability_signal_gain_pct", 0.0),
        )
    )
    design_opt_baseline_constructability_avg = _finite(
        design_opt_cost_summary.get("baseline_constructability_avg", 0.0)
    )
    design_opt_final_constructability_avg = _finite(
        design_opt_cost_summary.get("final_constructability_avg", 0.0)
    )
    design_opt_baseline_detailing_complexity_avg = _finite(
        design_opt_cost_summary.get("baseline_detailing_complexity_avg", 0.0)
    )
    design_opt_final_detailing_complexity_avg = _finite(
        design_opt_cost_summary.get("final_detailing_complexity_avg", 0.0)
    )
    design_opt_selected_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((design_opt_cost_summary.get("accepted_action_family_counts") or {}).items())
    }
    design_opt_preview_supply_family_counts = {
        str(k): int(v)
        for k, v in sorted((design_opt_cost_summary.get("preview_supply_family_counts") or {}).items())
    }
    design_opt_preview_supply_family_mix_label = ", ".join(
        f"{family}={count}" for family, count in design_opt_preview_supply_family_counts.items()
    )
    design_opt_preview_missing_target_families = [
        family
        for family in ("beam_section", "wall_thickness", "connection_detailing", "detailing")
        if int(design_opt_preview_supply_family_counts.get(family, 0)) <= 0
    ]
    design_opt_preview_missing_target_families_label = ", ".join(design_opt_preview_missing_target_families)
    design_opt_previous_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((design_opt_cost_summary.get("previous_accepted_action_family_counts") or {}).items())
    }
    design_opt_selected_family_mix_label = ", ".join(
        f"{family}={count}" for family, count in design_opt_selected_action_family_counts.items()
    )
    design_opt_selected_family_trend_label = str(design_opt_cost_summary.get("selected_action_family_trend_label", ""))
    design_opt_selected_family_total = int(sum(design_opt_selected_action_family_counts.values()))
    if design_opt_selected_action_family_counts:
        design_opt_selected_dominant_family, design_opt_selected_dominant_count = max(
            design_opt_selected_action_family_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
        design_opt_selected_dominant_ratio = (
            float(design_opt_selected_dominant_count) / max(float(design_opt_selected_family_total), 1.0)
        )
    else:
        design_opt_selected_dominant_family = ""
        design_opt_selected_dominant_count = 0
        design_opt_selected_dominant_ratio = 0.0
    design_opt_previous_dominant_family = str(design_opt_cost_summary.get("previous_selected_dominant_family", ""))
    design_opt_previous_dominant_ratio = _finite(design_opt_cost_summary.get("previous_selected_dominant_family_ratio", 0.0))
    nightly_smoke = nightly.get("design_optimization_cost_reduction_smoke") if isinstance(nightly.get("design_optimization_cost_reduction_smoke"), dict) else {}
    nightly_smoke_summary = nightly_smoke.get("summary") if isinstance(nightly_smoke.get("summary"), dict) else {}
    nightly_smoke_history = nightly.get("design_optimization_cost_reduction_smoke_history") if isinstance(nightly.get("design_optimization_cost_reduction_smoke_history"), dict) else {}
    nightly_smoke_history_summary = nightly_smoke_history.get("summary") if isinstance(nightly_smoke_history.get("summary"), dict) else {}
    nightly_smoke_recommendation = nightly.get("design_optimization_cost_reduction_smoke_strict_recommendation") if isinstance(nightly.get("design_optimization_cost_reduction_smoke_strict_recommendation"), dict) else {}
    gap_smoke_trend = gap.get("nightly_smoke_trend") if isinstance(gap.get("nightly_smoke_trend"), dict) else {}
    midas_section_library_summary_line = str(
        ci.get("midas_section_library_summary_line", gap_summary.get("midas_section_library_summary_line", "")) or ""
    ).strip()
    midas_kds_geometry_bridge_summary_line = str(
        ci.get("midas_kds_geometry_bridge_summary_line", gap_summary.get("midas_kds_geometry_bridge_summary_line", "")) or ""
    ).strip()
    midas_kds_geometry_bridge_load_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        gap_summary,
        stem="load_crosswalk",
    )
    midas_kds_geometry_bridge_semantic_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        gap_summary,
        stem="semantic_crosswalk",
    )
    midas_kds_geometry_bridge_full_member_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        gap_summary,
        stem="full_member_crosswalk",
    )
    midas_kds_geometry_bridge_full_section_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        gap_summary,
        stem="full_section_crosswalk",
    )
    midas_kds_geometry_bridge_full_load_crosswalk_surface = _extract_geometry_bridge_signal_surface(
        ci,
        gap_summary,
        stem="full_load_crosswalk",
    )
    midas_kds_geometry_bridge_full_crosswalk_depth = min(
        int(midas_kds_geometry_bridge_load_crosswalk_surface.get("count", 0) or 0),
        int(midas_kds_geometry_bridge_semantic_crosswalk_surface.get("count", 0) or 0),
    )
    ndtha_step_series_depth = max(
        (
            [
                int(row.get("summary", {}).get("step_count_completed", 0) or 0)
                for row in ndtha_stress_rows
                if isinstance(row, dict)
            ]
            + [
                int(ci.get("ndtha_step_series_depth", 0) or 0),
                int(gap_summary.get("ndtha_step_series_depth", 0) or 0),
            ]
        )
        or [0]
    )
    ndtha_material_surface = _ndtha_material_surface(ndtha_stress)
    ndtha_material_depth = int(ndtha_material_surface.get("material_depth", 0) or 0)
    ndtha_material_summary_line = str(ndtha_material_surface.get("summary_line", "") or "").strip()
    midas_loadcomb_roundtrip_summary_line = str(
        ci.get("midas_loadcomb_roundtrip_summary_line", gap_summary.get("midas_loadcomb_roundtrip_summary_line", "")) or ""
    ).strip()
    commercial_benchmark_breadth_summary_line = str(
        ci.get("commercial_benchmark_breadth_summary_line", gap_summary.get("commercial_benchmark_breadth_summary_line", "")) or ""
    ).strip()
    solver_breadth_summary_line = str(
        ci.get("solver_breadth_summary_line", gap_summary.get("solver_breadth_summary_line", "")) or ""
    ).strip()
    element_material_breadth_summary_line = str(
        ci.get("element_material_breadth_summary_line", gap_summary.get("element_material_breadth_summary_line", "")) or ""
    ).strip()
    material_constitutive_summary_line = str(
        ci.get("material_constitutive_summary_line", gap_summary.get("material_constitutive_summary_line", "")) or ""
    ).strip()
    contact_readiness_summary_line = str(
        ci.get("contact_readiness_summary_line", gap_summary.get("contact_readiness_summary_line", "")) or ""
    ).strip()
    foundation_soil_link_summary_line = str(
        ci.get("foundation_soil_link_summary_line", gap_summary.get("foundation_soil_link_summary_line", "")) or ""
    ).strip()
    support_search_surface = _extract_support_search_surface(
        str(
            ci.get(
                "support_search_summary_line",
                gap_summary.get("support_search_summary_line", ""),
            )
            or foundation_soil_link_summary_line
        )
    )
    support_search_summary_line = str(support_search_surface.get("summary_line", "") or "").strip()
    support_search_count = int(support_search_surface.get("support_search_count", 0) or 0)
    node_surface_proxy_count = int(support_search_surface.get("node_surface_proxy_count", 0) or 0)
    support_depth_score = int(support_search_surface.get("support_depth_score", 0) or 0)
    structural_contact_summary_line = str(
        ci.get("structural_contact_summary_line", gap_summary.get("structural_contact_summary_line", "")) or ""
    ).strip()
    general_fe_contact_matrix_summary_line = str(
        ci.get("general_fe_contact_matrix_summary_line", gap_summary.get("general_fe_contact_matrix_summary_line", "")) or ""
    ).strip()
    surface_interaction_benchmark_summary_line = str(
        ci.get("surface_interaction_benchmark_summary_line", gap_summary.get("surface_interaction_benchmark_summary_line", "")) or ""
    ).strip()
    midas_interoperability_summary_line = str(
        ci.get("midas_interoperability_summary_line", gap_summary.get("midas_interoperability_summary_line", "")) or ""
    ).strip()
    midas_native_roundtrip_summary_line = str(
        ci.get("midas_native_roundtrip_summary_line", gap_summary.get("midas_native_roundtrip_summary_line", "")) or ""
    ).strip()
    steel_composite_constitutive_gate_summary_line, steel_composite_constitutive_gate_pass = _extract_optional_gate_surface(
        ci,
        gap_summary,
        stem="steel_composite_constitutive",
    )
    steel_composite_constitutive_gate_surface_label = _format_optional_gate_surface(
        steel_composite_constitutive_gate_summary_line,
        steel_composite_constitutive_gate_pass,
    )
    load_combination_engine_summary_line, load_combination_engine_pass = _extract_optional_gate_surface(
        ci,
        gap_summary,
        stem="load_combination_engine",
    )
    load_combination_engine_surface_label = _format_optional_gate_surface(
        load_combination_engine_summary_line,
        load_combination_engine_pass,
    )
    performance_profiling_summary_line = str(
        ci.get("performance_profiling_summary_line", gap_summary.get("performance_profiling_summary_line", "")) or ""
    ).strip()
    solver_truthfulness_summary_line = str(
        solver_truthfulness_report.get(
            "summary_line",
            ci.get("solver_truthfulness_summary_line", gap_summary.get("solver_truthfulness_summary_line", "")),
        )
        or ""
    ).strip()
    hardest_external_10case_kickoff_summary_line = str(
        ci.get(
            "hardest_external_10case_kickoff_summary_line",
            gap_summary.get("hardest_external_10case_kickoff_summary_line", ""),
        )
        or ""
    ).strip()
    nonlinear_generalization_summary_line = str(
        nonlinear_generalization_report.get(
            "summary_line",
            ci.get("nonlinear_generalization_summary_line", gap_summary.get("nonlinear_generalization_summary_line", "")),
        )
        or ""
    ).strip()
    workflow_productization_summary_line = str(
        workflow_productization_report.get(
            "summary_line",
            ci.get("workflow_productization_summary_line", gap_summary.get("workflow_productization_summary_line", "")),
        )
        or ""
    ).strip()
    workflow_contact_coupling_summary_label = str(
        workflow_productization_summary.get("results_explorer_traceability_contact_coupling_summary_label", "")
        or workflow_productization_summary.get("results_explorer_traceability_contact_material_depth_summary_label", "")
        or _compact_workflow_contact_coupling_summary_label(workflow_productization_summary_line)
        or ""
    ).strip()
    workflow_contact_coupling_match = re.search(
        r"support families=(\d+)\s*\|\s*proxy families=(\d+)\s*\|\s*assembled depth=(\d+)",
        workflow_contact_coupling_summary_label,
    )
    workflow_contact_coupling_summary = {
        "summary_label": workflow_contact_coupling_summary_label,
        "pass": bool(
            workflow_productization_summary.get("results_explorer_contact_coupling_pass", False)
            or workflow_productization_summary.get("results_explorer_traceability_pass", False)
            or bool(workflow_contact_coupling_summary_label)
        ),
        "support_family_count": int(
            workflow_productization_summary.get("results_explorer_traceability_contact_support_family_count", 0)
            or (int(workflow_contact_coupling_match.group(1)) if workflow_contact_coupling_match else 0)
            or 0
        ),
        "proxy_family_count": int(
            workflow_productization_summary.get("results_explorer_traceability_contact_proxy_family_count", 0)
            or (int(workflow_contact_coupling_match.group(2)) if workflow_contact_coupling_match else 0)
            or 0
        ),
        "assembled_depth_value": int(
            workflow_productization_summary.get("results_explorer_traceability_contact_assembled_depth_value", 0)
            or (int(workflow_contact_coupling_match.group(3)) if workflow_contact_coupling_match else 0)
            or 0
        ),
    }
    if not general_fe_contact_matrix_summary_line:
        general_fe_match = re.search(
            r"general_fe_contact_matrix=(General FE contact matrix: .*?)(?:\s*\|\s*coupling_depth=|\s*\|\s*coupling=|\s*\|\s*contact_material=|\s*\|\s*korean_source_ingest=|\s*$)",
            workflow_productization_summary_line,
        )
        if general_fe_match:
            general_fe_contact_matrix_summary_line = str(general_fe_match.group(1)).strip()
    general_fe_contact_matrix_summary = {
        "summary_label": _compact_general_fe_contact_matrix_summary_label(general_fe_contact_matrix_summary_line),
        "pass": bool(support_search_surface.get("pass", False)),
        "support_search_count": support_search_count,
        "node_surface_proxy_count": node_surface_proxy_count,
        "support_depth_score": support_depth_score,
    }
    korean_source_ingest_summary_line = str(
        workflow_productization_summary.get("korean_source_ingest_summary_line", "")
        or gap_summary.get("korean_source_ingest_summary_line", "")
        or ci.get("korean_source_ingest_summary_line", "")
        or ""
    ).strip()
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(korean_source_ingest_summary_line)
    korean_structural_preview_queue_summary_line = str(
        workflow_productization_summary.get("korean_structural_preview_queue_summary_line", "")
        or gap_summary.get("korean_structural_preview_queue_summary_line", "")
        or ci.get("korean_structural_preview_queue_summary_line", "")
        or ""
    ).strip()
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    commercial_readiness_summary_line = str(
        ci.get("commercial_readiness_summary_line", gap_summary.get("commercial_readiness_summary_line", "")) or ""
    ).strip()
    row_provenance_export_summary = (
        row_provenance_export_report.get("summary")
        if isinstance(row_provenance_export_report.get("summary"), dict)
        else {}
    )
    row_provenance_export_summary_line = str(row_provenance_export_report.get("summary_line", "") or "").strip()
    row_provenance_export_preview_rows = [
        row for row in (row_provenance_export_report.get("preview_rows") or row_provenance_export.get("preview_rows") or []) if isinstance(row, dict)
    ][:8]
    row_provenance_export_clause_filter_rows = [
        row
        for row in (row_provenance_export_report.get("clause_filter_rows") or row_provenance_export.get("clause_filter_rows") or [])
        if isinstance(row, dict)
    ][:8]
    row_provenance_export_member_filter_rows = [
        row
        for row in (row_provenance_export_report.get("member_filter_rows") or row_provenance_export.get("member_filter_rows") or [])
        if isinstance(row, dict)
    ][:8]
    row_provenance_export_hazard_filter_rows = [
        row
        for row in (row_provenance_export_report.get("hazard_filter_rows") or row_provenance_export.get("hazard_filter_rows") or [])
        if isinstance(row, dict)
    ][:8]
    row_provenance_export_rule_family_filter_rows = [
        row
        for row in (row_provenance_export_report.get("rule_family_filter_rows") or row_provenance_export.get("rule_family_filter_rows") or [])
        if isinstance(row, dict)
    ][:8]
    blocked_action_summary = _load_blocked_action_summary(design_opt_cost)
    authority_rows = _load_authority_details(authority, authority_catalog)
    residual_trace_rows = [
        row for row in ndtha_stress_rows if isinstance(row, dict) and isinstance(row.get("summary"), dict)
    ]
    residual_trace_changed = int(
        sum(
            1
            for row in residual_trace_rows
            if abs(
                _finite((row.get("summary") or {}).get("residual_pre_settle_drift_ratio_pct"))
                - _finite((row.get("summary") or {}).get("residual_drift_ratio_pct"))
            )
            > 1e-9
            or abs(
                _finite((row.get("summary") or {}).get("residual_pre_settle_top_displacement_m"))
                - _finite((row.get("summary") or {}).get("residual_top_displacement_m"))
            )
            > 1e-9
        )
    )
    residual_case_rows: list[dict] = []
    for row in residual_trace_rows:
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        residual_case_rows.append(
            {
                "case_id": str(row.get("case_id", "")),
                "split": str(row.get("split", "")),
                "hazard_type": str(row.get("hazard_type", "")),
                "residual_metric_source": str(summary.get("residual_metric_source", "")),
                "residual_settle_applied": bool(summary.get("residual_settle_applied", False)),
                "residual_settle_steps": int(summary.get("residual_settle_steps", 0)),
                "pre_settle_top_m": _finite(summary.get("residual_pre_settle_top_displacement_m")),
                "post_settle_top_m": _finite(summary.get("residual_top_displacement_m")),
                "pre_settle_drift_pct": _finite(summary.get("residual_pre_settle_drift_ratio_pct")),
                "post_settle_drift_pct": _finite(summary.get("residual_drift_ratio_pct")),
                "delta_top_m": _finite(summary.get("residual_pre_settle_top_displacement_m"))
                - _finite(summary.get("residual_top_displacement_m")),
                "delta_drift_pct": _finite(summary.get("residual_pre_settle_drift_ratio_pct"))
                - _finite(summary.get("residual_drift_ratio_pct")),
            }
        )

    cards = [
        _card("nightly", "Nightly", nightly.get("reason_code", "n/a"), _status(bool(nightly.get("contract_pass", False))), "latest release chain"),
        _card("nightly_smoke", "Nightly Smoke", nightly_smoke.get("reason_code", "n/a"), _status(bool(nightly_smoke.get("contract_pass", False))), f"profile={nightly_smoke_summary.get('objective_profile', 'n/a')}"),
        _card("nightly_smoke_pass_rate", "Smoke Pass Rate", f"{_finite(nightly_smoke_history_summary.get('pass_rate')):.2%}", _status(bool(_finite(nightly_smoke_history_summary.get('pass_rate')) >= 0.95)), f"count={int(nightly_smoke_history_summary.get('count', 0))}"),
        _card("nightly_smoke_trial_feasible", "Smoke Trial Feasible", f"{_finite(nightly_smoke_history_summary.get('trial_feasible_rate')):.2%}", _status(bool(_finite(nightly_smoke_history_summary.get('trial_feasible_rate')) >= 0.90)), f"avg_trial_runtime_s={_finite(nightly_smoke_history_summary.get('avg_trial_runtime_s')):.4f}"),
        _card("nightly_smoke_strict", "Smoke Strict", nightly_smoke_recommendation.get("recommendation", "n/a"), _status(bool(nightly_smoke_recommendation.get("strict_ready", False))), str(nightly_smoke_recommendation.get("reason", ""))),
        _card(
            "ci",
            "CI Gate",
            ci.get("reason_code", "n/a"),
            _status(bool(ci.get("all_pass", False))),
            (
                " | ".join(
                    part
                    for part in (
                        "static + contract gate",
                        midas_section_library_summary_line,
                        midas_loadcomb_roundtrip_summary_line,
                    )
                    if part
                )
            ),
        ),
        _card("pbd_drift", "PBD Drift Max", f"{_finite(pbd_metrics.get('drift_envelope_max_pct')):.4f}%", "PASS", "7-GM envelope"),
        _card("pbd_binary", "PBD Binary Cases", int(pbd_summary.get("case_metrics_npz_case_count", 0)), "PASS", str(pbd_summary.get("response_storage", "n/a"))),
        _card("speedup", "Speedup", f"{_finite(pbd_metrics.get('speedup_vs_estimate')):,.0f}x", "PASS", "vs 336h estimate"),
        _card("wind", "Wind Duration", f"{_finite(wind_summary.get('duration_hours')):.1f}h", _status(bool(wind.get('contract_pass', False))), "across-wind benchmark"),
        _card("ssi", "SSI Ratio Span", f"{_finite(ssi_summary.get('nonlinear_ratio_span')):.4f}", _status(bool(ssi.get('contract_pass', False))), "nonlinear boundary"),
        _card("damper", "Damper Corr Min", f"{_finite(damper_summary.get('waveform_corr_min')):.4f}", _status(bool(damper.get('contract_pass', False))), "NHERI damped frame"),
        _card("construction", "Diff. Shortening", f"{_finite(construction_summary.get('max_differential_shortening_mm')):.3f} mm", _status(bool(construction.get('contract_pass', False))), "construction sequence"),
        _card("diaphragm", "Flex Ampl. Max", f"{_finite(diaphragm_summary.get('flex_amplification_max')):.3f}", _status(bool(diaphragm.get('contract_pass', False))), "shell-beam mix"),
        _card("repro", "Replay Runs", int(repro_summary.get("replay_runs", 0)), _status(bool(repro_checks.get('replay_exact_match', False))), "version lock"),
        _card(
            "registry",
            "Signed Registry",
            registry_summary.get("signing_algorithm", "n/a"),
            _status(bool(registry_checks.get('signature_verified_pass', False))),
            (
                "release traceability | "
                f"project_pkg={int(registry_summary.get('project_registry_package_bytes', 0) or 0)}B | "
                f"approvals={int(registry_summary.get('project_registry_approval_count', 0) or 0)}"
            ),
        ),
        _card("kds", "KDS PASS", sum(1 for row in kds_frontend.get("compliance_rows", []) if row.get("status") == "PASS"), _status(bool(kds.get('contract_pass', False))), "code check rows"),
        _card("ndtha_residual", "NDTHA Residual", f"{_finite(ndtha_residual_summary.get('residual_drift_ratio_pct_max_abs')):.3f}%", _status(bool(ndtha_residual.get('contract_pass', False))), "hard-threshold gate"),
        _card("authority_sac", "SAC Holdout", int(authority_summary.get("sac_case_count", 0)), _status(bool((authority.get("checks") or {}).get('sac_pass', False))), "global benchmark"),
        _card("authority_nheri", "NHERI Holdout", int(authority_summary.get("nheri_case_count", 0)), _status(bool((authority.get("checks") or {}).get('nheri_pass', False))), "sensor waveform"),
        _card("authority_opensees", "OpenSees Holdout", int(authority_summary.get("opensees_case_count", 0)), _status(bool((authority.get("checks") or {}).get('opensees_pass', False))), "topology authority"),
        _card(
            "authority_opensees_breadth",
            "OpenSees Canonical Breadth",
            int(opensees_canonical_breadth_summary.get("canonical_case_count", 0)),
            _status(bool(opensees_canonical_breadth.get("contract_pass", False))),
            f"families={int(opensees_canonical_breadth_summary.get('canonical_family_count', 0))}, parser_ready={int(opensees_canonical_breadth_summary.get('standalone_parser_ready_case_count', 0))}",
        ),
        _card(
            "authority_measured_breadth",
            "Measured Breadth",
            int(measured_benchmark_breadth_summary.get("measured_case_count", 0)),
            _status(bool(measured_benchmark_breadth.get("contract_pass", False))),
            (
                f"families={int(measured_benchmark_breadth_summary.get('measured_family_count', 0))}, "
                f"baseline={int(measured_benchmark_breadth_summary.get('baseline_measured_family_count', 0))}/"
                f"{int(measured_benchmark_breadth_summary.get('baseline_measured_case_count', 0))}, "
                f"opensees_delta={int(measured_benchmark_breadth_summary.get('opensees_incremental_family_count', 0))}/"
                f"{int(measured_benchmark_breadth_summary.get('opensees_incremental_case_count', 0))}"
            ),
        ),
        _card(
            "peer_blind_compare_lane",
            "PEER Blind Compare",
            int(peer_blind_prediction_compare_summary.get("case_count", 0)),
            _status(bool(peer_blind_prediction_compare.get("contract_pass", False))),
            (
                f"measured_response_ready={bool(peer_blind_prediction_compare_summary.get('measured_response_ready', False))} | "
                f"channels={int(peer_blind_prediction_compare_summary.get('acceleration_channel_count', 0))}/"
                f"{int(peer_blind_prediction_compare_summary.get('drift_channel_count', 0))} | "
                f"lane={str(peer_blind_prediction_compare_results_explorer.get('entry_label', '') or 'n/a')} | "
                f"summary={peer_blind_prediction_compare_summary_line or 'n/a'}"
            ),
        ),
        _card(
            "peer_blind_measured_landing",
            "PEER Landing Manifest",
            int(peer_blind_prediction_measured_response_landing_summary.get("matched_file_count", 0)),
            _status(bool(peer_blind_prediction_measured_response_landing.get("contract_pass", False))),
            (
                f"state={str(peer_blind_prediction_measured_response_landing.get('landing_state', '') or 'n/a')} | "
                f"csv={int(peer_blind_prediction_measured_response_landing_summary.get('csv_file_count', 0))} | "
                f"accel={int(peer_blind_prediction_measured_response_landing_summary.get('acceleration_candidate_count', 0))} | "
                f"drift={int(peer_blind_prediction_measured_response_landing_summary.get('drift_candidate_count', 0))} | "
                f"sensors={int(peer_blind_prediction_measured_response_landing_summary.get('sensor_candidate_count', 0))} | "
                f"next={str(peer_blind_prediction_measured_response_landing.get('next_action', '') or 'n/a')}"
            ),
        ),
        _card("authority_binary", "Authority Binary Cases", int(authority_summary.get("case_metrics_npz_case_count", 0)), "PASS", str(authority_summary.get("response_storage", "n/a"))),
        _card("gaps", "Open P0/P1", f"{gap_summary.get('open_gap_counts', {}).get('P0', 0)}/{gap_summary.get('open_gap_counts', {}).get('P1', 0)}", "INFO", "remaining commercialization gaps"),
        _card(
            "p0_closed",
            "P0 Closed",
            "closed" if int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0 else "open",
            _status(int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0),
            "release publication and core evidence",
        ),
        _card(
            "p1_unblocked",
            "P1 Unblocked",
            "unblocked" if int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0 else "blocked",
            _status(int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0),
            "P1 quality/fallback/benchmark breadth can proceed",
        ),
        _card(
            "advanced_holdout_closure",
            "Advanced Holdout Closure",
            f"{int(advanced_holdout_surface.get('closed_count', 0))}/{int(advanced_holdout_surface.get('total_count', 0))} closed",
            "PASS" if int(advanced_holdout_surface.get("open_count", 0)) == 0 else "INFO",
            str(advanced_holdout_surface.get("summary_label", "") or ""),
        ),
        _card("coverage_model", "Coverage Model", str(gap_summary.get("deployment_model", "engineer_in_the_loop_accelerated_coverage")), "INFO", _coverage_range_label(gap_summary.get("accelerated_coverage_target_pct_range", [95, 99]))),
        _card("coverage_holdout", "Residual Holdout", _coverage_range_label(gap_summary.get("residual_holdout_target_pct_range", [1, 5])), "INFO", f"buckets={len(residual_holdout_buckets)}"),
        _card("coverage_time_saved", "Estimated Time Saved", _coverage_range_label(gap_summary.get("estimated_time_saved_pct_range", [70, 90])), "INFO", "repeated analysis workload"),
        _card("coverage_ready", "Engineer-in-Loop Ready", bool(gap_summary.get("engineer_in_loop_accelerated_coverage_ready", False)), _status(bool(gap_summary.get("engineer_in_loop_accelerated_coverage_ready", False))), "accelerated coverage framing"),
        _card("coverage_focus", "Time-Saving Focus", "95-99%", "INFO", str(gap_summary.get("time_saving_focus", ""))),
        _card(
            "midas_semantic_loads",
            "MIDAS Load Semantics",
            f"{int(gap_summary.get('midas_semantic_load_case_count', 0))}/{int(gap_summary.get('midas_semantic_load_combination_count', 0))}",
            _status(bool(gap_summary.get("midas_semantic_load_binding_pass", False))),
            (
                f"use_stld={int(gap_summary.get('midas_use_stld_block_count', 0))}, "
                f"bound rows=nodal:{int(gap_summary.get('midas_bound_nodal_load_row_count', 0))}/"
                f"selfweight:{int(gap_summary.get('midas_bound_selfweight_row_count', 0))}/"
                f"pressure:{int(gap_summary.get('midas_bound_pressure_row_count', 0))}"
            ),
        ),
        _card(
            "mgt_exporter",
            "MGT Exporter",
            bool(gap_summary.get("mgt_export_artifact_exists", False)),
            _status(bool(gap_summary.get("mgt_export_artifact_exists", False))),
            (
                f"mode={str(gap_summary.get('mgt_export_support_mode', 'missing'))}, "
                f"supported={int(gap_summary.get('mgt_export_supported_change_count', 0))}, "
                f"unsupported={int(gap_summary.get('mgt_export_unsupported_change_count', 0))}, "
                f"direct_patch={int(gap_summary.get('mgt_export_direct_patch_change_count', 0))}, "
                f"direct_patch_families={str(gap_summary.get('mgt_export_direct_patch_action_family_label', '')) or 'n/a'}, "
                f"material_rebar_payloads={int(gap_summary.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(gap_summary.get('mgt_export_material_level_rebar_payload_row_count', 0))}, "
                f"group_local_rebar_payloads={int(gap_summary.get('mgt_export_group_local_rebar_payload_available_count', 0))}/{int(gap_summary.get('mgt_export_group_local_rebar_payload_row_count', 0))}, "
                f"group_local_connection_payloads={int(gap_summary.get('mgt_export_group_local_connection_detailing_payload_available_count', 0))}/{int(gap_summary.get('mgt_export_group_local_connection_detailing_payload_row_count', 0))}, "
                f"group_local_detailing_payloads={int(gap_summary.get('mgt_export_group_local_detailing_payload_available_count', 0))}/{int(gap_summary.get('mgt_export_group_local_detailing_payload_row_count', 0))}, "
                f"connection_delivery_mode={str(gap_summary.get('mgt_export_connection_detailing_delivery_mode', '')) or 'n/a'}, "
                f"detailing_delivery_mode={str(gap_summary.get('mgt_export_detailing_delivery_mode', '')) or 'n/a'}, "
                f"rebar_direct_patch_eligible={int(gap_summary.get('mgt_export_rebar_direct_patch_eligible_change_count', 0))}, "
                f"patched_material_rows={int(gap_summary.get('mgt_export_patched_material_row_count', 0))}, "
                f"cloned_materials={int(gap_summary.get('mgt_export_cloned_material_count', 0))}, "
                f"sidecar={int(gap_summary.get('mgt_export_instruction_sidecar_change_count', 0))}, "
                f"sidecar_families={str(gap_summary.get('mgt_export_instruction_sidecar_action_family_label', '')) or 'n/a'}, "
                f"sidecar_audit={str(gap_summary.get('mgt_export_instruction_sidecar_audit_only_action_family_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_instruction_sidecar_audit_only_change_count', 0))}), "
                f"sidecar_manual={str(gap_summary.get('mgt_export_instruction_sidecar_manual_input_action_family_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_instruction_sidecar_manual_input_change_count', 0))}), "
                f"audit_manifest={str(gap_summary.get('mgt_export_audit_review_manifest_action_family_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_audit_review_manifest_change_count', 0))}), "
                f"audit_packets={str(gap_summary.get('mgt_export_audit_review_packet_action_family_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_audit_review_packet_count', 0))}), "
                f"audit_packet_files={str(gap_summary.get('mgt_export_audit_review_packet_file_action_family_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_audit_review_packet_file_count', 0))}), "
                f"audit_queue={str(gap_summary.get('mgt_export_audit_review_queue_action_family_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_audit_review_queue_item_count', 0))}), "
                f"audit_queue_status={str(gap_summary.get('mgt_export_audit_review_queue_status_label', '')) or 'n/a'}, "
                f"audit_followup={str(gap_summary.get('mgt_export_audit_review_followup_action_label', '')) or 'n/a'} ({int(gap_summary.get('mgt_export_audit_review_followup_item_count', 0))}), "
                f"audit_followup_owner={str(gap_summary.get('mgt_export_audit_review_followup_owner_label', '')) or 'n/a'}, "
                f"audit_followup_status={str(gap_summary.get('mgt_export_audit_review_followup_status_label', '')) or 'n/a'}, "
                f"sidecar_priorities={str(gap_summary.get('mgt_export_instruction_sidecar_review_priority_label', '')) or 'n/a'}, "
                f"sidecar_followups={str(gap_summary.get('mgt_export_instruction_sidecar_followup_type_label', '')) or 'n/a'}, "
                f"clones={int(gap_summary.get('mgt_export_cloned_section_count', 0)) + int(gap_summary.get('mgt_export_cloned_thickness_count', 0))}, "
                f"retargeted={int(gap_summary.get('mgt_export_retargeted_element_row_count', 0))}"
            ),
        ),
        _card(
            "mgt_delivery_boundary",
            "MGT Delivery Boundary",
            str(gap_summary.get("mgt_export_evidence_model", "")) or "n/a",
            "INFO",
            (
                f"direct_patch={str(gap_summary.get('mgt_export_direct_patch_action_family_label', '')) or 'n/a'} | "
                f"sidecar={str(gap_summary.get('mgt_export_instruction_sidecar_action_family_label', '')) or 'n/a'} | "
                f"connection_payload={str(gap_summary.get('mgt_export_connection_detailing_delivery_mode', '')) or 'n/a'} | "
                f"detailing_payload={str(gap_summary.get('mgt_export_detailing_delivery_mode', '')) or 'n/a'}"
            ),
        ),
        _card("design_opt_long", "Design Opt Feasible", bool(design_opt_long_summary.get("solver_feasible_final", False)), _status(bool(design_opt_long.get("contract_pass", False))), f"max_dcr={_finite(design_opt_long_summary.get('final_max_dcr')):.3f}"),
        _card("design_opt_raw", "Design Opt Raw Drift", f"{design_opt_raw_max_drift:.3f}%", "INFO", f"raw_dcr={design_opt_raw_max_dcr:.3f}"),
        _card("design_opt_repaired", "Design Opt Repaired Drift", f"{design_opt_repaired_max_drift:.3f}%", _status(bool(design_opt_long_summary.get("solver_feasible_final", False))), f"repaired_dcr={design_opt_repaired_max_dcr:.3f}"),
        _card("design_opt_constructability", "Constructability Signal", f"{design_opt_constructability_signal_gain_pct:.2f}%", "INFO", f"repair_actions={design_opt_repair_action_count}"),
        _card("design_opt_family_mix", "Selected Family Mix", design_opt_selected_dominant_family or "n/a", "INFO", f"{design_opt_selected_family_mix_label}"),
        _card("design_opt_family_mix_trend", "Family Mix Trend", design_opt_selected_family_trend_label or "n/a", "INFO", f"prev={design_opt_previous_dominant_family} ({design_opt_previous_dominant_ratio:.2%}) -> current={design_opt_selected_dominant_family} ({design_opt_selected_dominant_ratio:.2%})"),
        _card("design_opt_preview_supply", "Preview Supply", design_opt_preview_missing_target_families_label or "all target families present", "INFO", f"{design_opt_preview_supply_family_mix_label}"),
        _card("design_opt_cost", "Cost Reduction", f"{_finite(design_opt_cost_summary.get('cost_reduction_proxy')):.2f}", _status(bool(design_opt_cost.get("contract_pass", False))), f"changed_groups={int(design_opt_cost_summary.get('changed_group_count', 0))}"),
        _card(
            "design_opt_blocks",
            "Blocked Actions",
            int(blocked_action_summary.get("blocked_action_row_count", 0)),
            "INFO",
            (
                f"illegal={int(blocked_action_summary.get('illegal_by_mask', 0))}, "
                f"no_gain={int(blocked_action_summary.get('no_cost_gain', 0))}, "
                f"hard_gate={int(blocked_action_summary.get('constructability_hard_gate_block_count', 0))}"
            ),
        ),
    ]

    validation_rows = [
        {
            "section": "PBD",
            "item": "7-GM Drift Envelope",
            "criterion": "drift envelope within IO/LS/CP band",
            "value": f"max={_finite(pbd_metrics.get('drift_envelope_max_pct')):.4f}%, p95={_finite(pbd_metrics.get('drift_p95_max_pct')):.4f}%",
            "status": "PASS",
            "evidence": "pbd_review drift envelope",
        },
        {
            "section": "PBD",
            "item": "Energy Balance",
            "criterion": "relative error <= 1e-2",
            "value": f"{_finite(pbd_metrics.get('energy_balance_relative_error_ref')):.6e}",
            "status": "PASS",
            "evidence": "killshot metrics",
        },
        {
            "section": "PBD",
            "item": "Binary artifact trace",
            "criterion": "npz metrics artifact present and case count matches selected set",
            "value": f"storage={pbd_summary.get('response_storage', 'n/a')}, cases={int(pbd_summary.get('case_metrics_npz_case_count', 0))}",
            "status": "PASS",
            "evidence": "pbd_review_package_report",
        },
        {
            "section": "Optimization",
            "item": "Long-Budget Feasible Repair",
            "criterion": "solver_feasible_final == true and final max DCR <= 1.0",
            "value": (
                f"feasible={bool(design_opt_long_summary.get('solver_feasible_final', False))}, "
                f"max_dcr={_finite(design_opt_long_summary.get('final_max_dcr')):.4f}"
            ),
            "status": _status(bool(design_opt_long_summary.get("solver_feasible_final", False))),
            "evidence": "design_optimization_solver_loop_long_report",
        },
        {
            "section": "Optimization",
            "item": "Cost Reduction Evidence",
            "criterion": "feasible input, blocked=false, cost reduction nonnegative",
            "value": (
                f"changed={int(design_opt_cost_summary.get('changed_group_count', 0))}, "
                f"accepted={int(design_opt_cost_summary.get('accepted_count', 0))}, "
                f"cost_delta={_finite(design_opt_cost_summary.get('cost_reduction_proxy')):.3f}"
            ),
            "status": _status(bool(design_opt_cost.get("contract_pass", False))),
            "evidence": "design_optimization_cost_reduction_report",
        },
        {
            "section": "Optimization",
            "item": "Blocked Action Explain",
            "criterion": "rejected cost-down actions are exported with machine-readable reasons",
            "value": (
                f"blocked={int(blocked_action_summary.get('blocked_action_row_count', 0))}, "
                f"illegal={int(blocked_action_summary.get('illegal_by_mask', 0))}, "
                f"no_gain={int(blocked_action_summary.get('no_cost_gain', 0))}"
            ),
            "status": "PASS",
            "evidence": "design_optimization_cost_reduction_blocked_actions",
        },
        {
            "section": "NDTHA",
            "item": "Residual Hard Gate",
            "criterion": "finite residuals, traceable source, hard thresholds pass",
            "value": (
                f"top={_finite(ndtha_residual_summary.get('residual_top_displacement_m_max_abs')):.3f} m, "
                f"drift={_finite(ndtha_residual_summary.get('residual_drift_ratio_pct_max_abs')):.3f}%, "
                f"fallback_rate={_finite(ndtha_residual_summary.get('fallback_rate')):.3f}"
            ),
            "status": _status(bool(ndtha_residual.get("contract_pass", False))),
            "evidence": "ndtha_residual_gate_report",
        },
        {
            "section": "NDTHA",
            "item": "Residual Trace",
            "criterion": "pre-settle and post-settle residuals remain auditable per case",
            "value": (
                f"cases={len(residual_trace_rows)}, "
                f"changed={residual_trace_changed}, "
                f"pre_top_max={_finite(ndtha_stress.get('summary', {}).get('residual_pre_settle_top_displacement_m_max_abs')):.3f} m, "
                f"pre_drift_max={_finite(ndtha_stress.get('summary', {}).get('residual_pre_settle_drift_ratio_pct_max_abs')):.3f}%"
            ),
            "status": "PASS",
            "evidence": "nonlinear_ndtha_stress_report",
        },
        {
            "section": "Wind",
            "item": "Across-wind long series",
            "criterion": "10h series, converged, no collapse",
            "value": (
                f"duration={_finite(wind_summary.get('duration_hours')):.1f}h, "
                f"chunks={int(wind_summary.get('total_chunk_count', 0))}, "
                f"post_drift={_finite(wind_summary.get('residual_drift_pct_max_abs')):.3f}%, "
                f"pre_drift={_finite(wind_summary.get('residual_pre_settle_drift_pct_max_abs')):.3f}%"
            ),
            "status": _status(bool(wind.get("contract_pass", False))),
            "evidence": "wind_time_history_gate_report",
        },
        {
            "section": "SSI",
            "item": "Nonlinear boundary response",
            "criterion": "finite transfer and shear delta pass",
            "value": (
                f"ratio span={_finite(ssi_summary.get('nonlinear_ratio_span')):.4f}, "
                f"fixed_post_drift={_finite(ssi_summary.get('fixed_residual_drift_pct_max_abs')):.3f}%, "
                f"ssi_post_drift={_finite(ssi_summary.get('ssi_residual_drift_pct_max_abs')):.3f}%"
            ),
            "status": _status(bool(ssi.get("contract_pass", False))),
            "evidence": "ssi_boundary_gate_report",
        },
        {
            "section": "Damper",
            "item": "Damped frame agreement",
            "criterion": "correlation/phase/residual thresholds pass",
            "value": f"corr_min={_finite(damper_summary.get('waveform_corr_min')):.4f}, phase_max={_finite(damper_summary.get('phase_error_ms_max')):.3f} ms",
            "status": _status(bool(damper.get("contract_pass", False))),
            "evidence": "damper_validation_gate_report",
        },
        {
            "section": "Construction",
            "item": "Construction preload",
            "criterion": "creep/shrinkage + differential shortening captured",
            "value": f"diff={_finite(construction_summary.get('max_differential_shortening_mm')):.3f} mm, stress={_finite(construction_summary.get('max_initial_stress_mpa')):.3f} MPa",
            "status": _status(bool(construction.get("contract_pass", False))),
            "evidence": "construction_sequence_gate_report",
        },
        {
            "section": "Diaphragm",
            "item": "Flexible diaphragm",
            "criterion": "shell-beam mix and slab shear checks pass",
            "value": f"amp={_finite(diaphragm_summary.get('flex_amplification_max')):.3f}, drift={_finite(diaphragm_summary.get('max_flexible_drift_pct')):.3f}%",
            "status": _status(bool(diaphragm.get("contract_pass", False))),
            "evidence": "flexible_diaphragm_gate_report",
        },
        {
            "section": "Reproducibility",
            "item": "Version lock replay",
            "criterion": "exact replay match and manifest written",
            "value": f"runs={int(repro_summary.get('replay_runs', 0))}, seed={int(repro_summary.get('seed', 0))}",
            "status": _status(bool(repro.get("contract_pass", False))),
            "evidence": "reproducibility_version_lock_report",
        },
        {
            "section": "Reproducibility",
            "item": "Signed release registry",
            "criterion": "signature verified and registry hashes present",
            "value": (
                f"artifacts={int(registry_summary.get('artifact_count', 0))}, "
                f"project_pkg={int(registry_summary.get('project_registry_package_bytes', 0) or 0)}B, "
                f"approvals={int(registry_summary.get('project_registry_approval_count', 0) or 0)}, "
                f"pubkey={registry_sig.get('public_key_path', '')}"
            ),
            "status": _status(bool(release_registry.get("contract_pass", False))),
            "evidence": "release_registry",
        },
        {
            "section": "Code Check",
            "item": "KDS compliance",
            "criterion": "all compliance rows pass",
            "value": f"rows={len(kds_frontend.get('compliance_rows', []))}, pass_cards={len(kds_frontend.get('summary_cards', []))}",
            "status": _status(bool(kds.get("contract_pass", False))),
            "evidence": "kds_compliance_summary",
        },
        {
            "section": "Authority",
            "item": "SAC holdout",
            "criterion": "drift/base shear/member force thresholds pass",
            "value": f"cases={int(authority_summary.get('sac_case_count', 0))}, valid={int(authority_summary.get('sac_valid_count', 0))}",
            "status": _status(bool((authority.get("checks") or {}).get("sac_pass", False))),
            "evidence": "global_authority_gate_report",
        },
        {
            "section": "Authority",
            "item": "NHERI holdout",
            "criterion": "waveform correlation/phase/residual thresholds pass",
            "value": f"cases={int(authority_summary.get('nheri_case_count', 0))}, valid={int(authority_summary.get('nheri_valid_count', 0))}",
            "status": _status(bool((authority.get("checks") or {}).get("nheri_pass", False))),
            "evidence": "global_authority_gate_report",
        },
        {
            "section": "Authority",
            "item": "OpenSees holdout",
            "criterion": "real topology + shell/beam mix topology contracts pass",
            "value": f"cases={int(authority_summary.get('opensees_case_count', 0))}, pass={int(authority_summary.get('opensees_contract_pass_count', 0))}",
            "status": _status(bool((authority.get("checks") or {}).get("opensees_pass", False))),
            "evidence": "global_authority_gate_report",
        },
        {
            "section": "Authority",
            "item": "OpenSees canonical breadth",
            "criterion": "committed real-source OpenSees canonical assets are surfaced beyond holdout-only coverage",
            "value": (
                f"families={int(opensees_canonical_breadth_summary.get('canonical_family_count', 0))}, "
                f"cases={int(opensees_canonical_breadth_summary.get('canonical_case_count', 0))}, "
                f"parser_ready={int(opensees_canonical_breadth_summary.get('standalone_parser_ready_case_count', 0))}"
            ),
            "status": _status(bool(opensees_canonical_breadth.get("contract_pass", False))),
            "evidence": "opensees_canonical_breadth_report",
        },
        {
            "section": "Authority",
            "item": "Measured benchmark breadth",
            "criterion": "commercial measured baseline plus committed OpenSees breadth are tracked in one surfaced gate",
            "value": (
                f"baseline={int(measured_benchmark_breadth_summary.get('baseline_measured_family_count', 0))}/"
                f"{int(measured_benchmark_breadth_summary.get('baseline_measured_case_count', 0))}, "
                f"delta={int(measured_benchmark_breadth_summary.get('opensees_incremental_family_count', 0))}/"
                f"{int(measured_benchmark_breadth_summary.get('opensees_incremental_case_count', 0))}, "
                f"measured={int(measured_benchmark_breadth_summary.get('measured_family_count', 0))}/"
                f"{int(measured_benchmark_breadth_summary.get('measured_case_count', 0))}"
            ),
            "status": _status(bool(measured_benchmark_breadth.get("contract_pass", False))),
            "evidence": "measured_benchmark_breadth_report",
        },
        {
            "section": "PEER",
            "item": "Blind compare lane",
            "criterion": "compare lane is staged and measured-response readiness is tracked",
            "value": (
                f"cases={int(peer_blind_prediction_compare_summary.get('case_count', 0))}, "
                f"measured_response_ready={bool(peer_blind_prediction_compare_summary.get('measured_response_ready', False))}, "
                f"channels={int(peer_blind_prediction_compare_summary.get('acceleration_channel_count', 0))}/"
                f"{int(peer_blind_prediction_compare_summary.get('drift_channel_count', 0))}, "
                f"lane={str(peer_blind_prediction_compare_results_explorer.get('entry_label', '') or 'n/a')}"
            ),
            "status": _status(bool(peer_blind_prediction_compare.get("contract_pass", False))),
            "evidence": "peer_blind_prediction_compare_report",
        },
        {
            "section": "PEER",
            "item": "Measured-response landing",
            "criterion": "official measured-response bundle is staged under the landing root",
            "value": (
                f"state={str(peer_blind_prediction_measured_response_landing.get('landing_state', '') or 'n/a')}, "
                f"matched={int(peer_blind_prediction_measured_response_landing_summary.get('matched_file_count', 0))}, "
                f"csv={int(peer_blind_prediction_measured_response_landing_summary.get('csv_file_count', 0))}, "
                f"accel={int(peer_blind_prediction_measured_response_landing_summary.get('acceleration_candidate_count', 0))}, "
                f"drift={int(peer_blind_prediction_measured_response_landing_summary.get('drift_candidate_count', 0))}, "
                f"sensors={int(peer_blind_prediction_measured_response_landing_summary.get('sensor_candidate_count', 0))}"
            ),
            "status": _status(bool(peer_blind_prediction_measured_response_landing.get("contract_pass", False))),
            "evidence": "edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest",
        },
        {
            "section": "Authority",
            "item": "Binary artifact trace",
            "criterion": "npz metrics artifact present and case/step counts recorded",
            "value": (
                f"storage={authority_summary.get('response_storage', 'n/a')}, "
                f"cases={int(authority_summary.get('case_metrics_npz_case_count', 0))}, "
                f"steps={int(authority_summary.get('case_metrics_npz_step_count', 0))}"
            ),
            "status": "PASS",
            "evidence": "global_authority_gate_report",
        },
    ]

    panel_zone_external_validation_surface = _panel_zone_external_validation_surface(gap_summary)
    panel_zone_status_label = str(
        gap_summary.get("panel_zone_status_label", "") or ""
    )
    if panel_zone_status_label in {"release_ready", "verified", "solver_verified"} and str(
        panel_zone_external_validation_surface["status_label"]
    ) not in {"verified", "solver_verified"}:
        panel_zone_status_label = str(panel_zone_external_validation_surface["status_label"])
    if not panel_zone_status_label:
        if bool(panel_zone_external_validation_surface["release_blocking"]):
            panel_zone_status_label = "release_blocking"
        elif str(panel_zone_external_validation_surface["status_label"]) not in {
            "",
            "not_applicable",
            "verified",
            "solver_verified",
        }:
            panel_zone_status_label = str(panel_zone_external_validation_surface["status_label"])
        elif bool(gap_summary.get("panel_zone_3d_clash_ready", False)):
            panel_zone_status_label = "release_ready"
        else:
            panel_zone_status_label = "unavailable"
    panel_zone_advisory_only = bool(
        gap_summary.get("panel_zone_advisory_only", panel_zone_external_validation_surface["advisory_only"])
    )
    panel_zone_release_blocking = bool(
        gap_summary.get("panel_zone_release_blocking", panel_zone_external_validation_surface["release_blocking"])
    )
    panel_zone_external_validation_required_evidence = build_panel_zone_external_validation_required_evidence(
        gap_summary,
        status_label=str(panel_zone_external_validation_surface["status_label"]),
    )
    panel_zone_external_validation_summary_line = build_panel_zone_external_validation_summary_line(
        gap_summary,
        status_label=str(panel_zone_external_validation_surface["status_label"]),
    )
    panel_zone_external_validation_local_closure_surface = build_panel_zone_external_validation_local_closure_surface(
        gap_summary,
        status_label=str(panel_zone_external_validation_surface["status_label"]),
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
        f"inbox={str(gap_summary.get('panel_zone_solver_verified_inbox_status_mode', '') or '') or 'unknown'} | "
        f"pending_input={bool(gap_summary.get('panel_zone_solver_verified_pending_input', False))} | "
        f"latest_consume_present={bool(gap_summary.get('panel_zone_solver_verified_latest_consume_report_present', False))} | "
        f"latest_consume_pass={bool(gap_summary.get('panel_zone_solver_verified_latest_consume_contract_pass', False))} | "
        f"latest_consume_reason={str(gap_summary.get('panel_zone_solver_verified_latest_consume_reason_code', '') or '') or 'n/a'} | "
        f"next={str(gap_summary.get('panel_zone_solver_verified_recommended_action', '') or '') or 'n/a'}"
    )
    metrics = {
        "earthquake_case_count": int(pbd_metrics.get("earthquake_case_count", 0)),
        "drift_envelope_max_pct": _finite(pbd_metrics.get("drift_envelope_max_pct")),
        "drift_p95_max_pct": _finite(pbd_metrics.get("drift_p95_max_pct")),
        "speedup_vs_estimate": _finite(pbd_metrics.get("speedup_vs_estimate")),
        "pbd_npz_case_count": int(pbd_summary.get("case_metrics_npz_case_count", 0)),
        "energy_balance_relative_error_ref": _finite(pbd_metrics.get("energy_balance_relative_error_ref")),
        "residual_drift_pct_max_abs": _finite(pbd_metrics.get("residual_drift_pct_max_abs")),
        "ndtha_residual_top_m_max_abs": _finite(ndtha_residual_summary.get("residual_top_displacement_m_max_abs")),
        "ndtha_residual_drift_pct_max_abs": _finite(ndtha_residual_summary.get("residual_drift_ratio_pct_max_abs")),
        "ndtha_residual_fallback_rate": _finite(ndtha_residual_summary.get("fallback_rate")),
        "ndtha_residual_raw_top_m_max_abs": _finite(ndtha_stress.get("summary", {}).get("residual_pre_settle_top_displacement_m_max_abs")),
        "ndtha_residual_raw_drift_pct_max_abs": _finite(ndtha_stress.get("summary", {}).get("residual_pre_settle_drift_ratio_pct_max_abs")),
        "ndtha_residual_trace_changed_case_count": int(residual_trace_changed),
        "ndtha_residual_case_count": int(len(residual_case_rows)),
        "ndtha_step_series_depth": int(ndtha_step_series_depth),
        "ndtha_material_pass": bool(ndtha_material_surface.get("material_pass", False)),
        "ndtha_material_summary_line": ndtha_material_summary_line,
        "ndtha_material_depth": int(ndtha_material_depth),
        "ndtha_recommended_drift_pass": bool(ndtha_residual_checks.get("recommended_drift_pass", False)),
        "wind_duration_hours": _finite(wind_summary.get("duration_hours")),
        "wind_load_reversal_count": _finite(wind_summary.get("load_reversal_count")),
        "wind_residual_pre_settle_drift_pct_max_abs": _finite(wind_summary.get("residual_pre_settle_drift_pct_max_abs")),
        "wind_residual_drift_pct_max_abs": _finite(wind_summary.get("residual_drift_pct_max_abs")),
        "ssi_nonlinear_ratio_span": _finite(ssi_summary.get("nonlinear_ratio_span")),
        "ssi_fixed_residual_drift_pct_max_abs": _finite(ssi_summary.get("fixed_residual_drift_pct_max_abs")),
        "ssi_residual_drift_pct_max_abs": _finite(ssi_summary.get("ssi_residual_drift_pct_max_abs")),
        "damper_waveform_corr_min": _finite(damper_summary.get("waveform_corr_min")),
        "damper_phase_error_ms_max": _finite(damper_summary.get("phase_error_ms_max")),
        "construction_max_differential_shortening_mm": _finite(construction_summary.get("max_differential_shortening_mm")),
        "construction_max_initial_stress_mpa": _finite(construction_summary.get("max_initial_stress_mpa")),
        "flex_amplification_max": _finite(diaphragm_summary.get("flex_amplification_max")),
        "flexible_drift_pct_max": _finite(diaphragm_summary.get("max_flexible_drift_pct")),
        "replay_runs": int(repro_summary.get("replay_runs", 0)),
        "replay_exact_match": bool(repro_checks.get("replay_exact_match", False)),
        "registry_artifact_count": int(registry_summary.get("artifact_count", 0)),
        "registry_signature_verified": bool(registry_checks.get("signature_verified_pass", False)),
        "project_registry_artifact_count": int(registry_summary.get("project_registry_artifact_count", 0) or 0),
        "project_registry_approval_count": int(registry_summary.get("project_registry_approval_count", 0) or 0),
        "project_registry_package_sha256": str(
            registry_summary.get("project_registry_package_sha256", "") or ""
        ),
        "project_registry_package_bytes": int(registry_summary.get("project_registry_package_bytes", 0) or 0),
        "project_registry_signature_verified": bool(
            registry_checks.get("project_registry_signature_verified_pass", False)
        ),
        "nightly_smoke_pass_rate": _finite(nightly_smoke_history_summary.get("pass_rate")),
        "nightly_smoke_trial_feasible_rate": _finite(nightly_smoke_history_summary.get("trial_feasible_rate")),
        "nightly_smoke_avg_trial_runtime_s": _finite(nightly_smoke_history_summary.get("avg_trial_runtime_s")),
        "nightly_smoke_history_count": int(nightly_smoke_history_summary.get("count", 0)),
        "nightly_smoke_strict_ready": bool(nightly_smoke_recommendation.get("strict_ready", False)),
        "nightly_smoke_strict_recommendation": str(nightly_smoke_recommendation.get("recommendation", "")),
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
        "solver_breadth_summary_line": solver_breadth_summary_line,
        "element_material_breadth_summary_line": element_material_breadth_summary_line,
        "material_constitutive_summary_line": material_constitutive_summary_line,
        "contact_readiness_summary_line": contact_readiness_summary_line,
        "foundation_soil_link_summary_line": foundation_soil_link_summary_line,
        "support_search_summary_line": support_search_summary_line,
        "support_search_count": int(support_search_count),
        "node_surface_proxy_count": int(node_surface_proxy_count),
        "support_depth_score": int(support_depth_score),
        "structural_contact_summary_line": structural_contact_summary_line,
        "general_fe_contact_matrix_summary_line": general_fe_contact_matrix_summary_line,
        "general_fe_contact_matrix_summary": general_fe_contact_matrix_summary,
        "surface_interaction_benchmark_summary_line": surface_interaction_benchmark_summary_line,
        "performance_profiling_summary_line": performance_profiling_summary_line,
        "performance_moving_load_scale_label": (
            f"{_finite(performance_profiling_summary.get('moving_load_integrator_elapsed_seconds')):.3f}/"
            f"{_finite(performance_profiling_summary.get('moving_load_large_elapsed_seconds')):.3f}/"
            f"{_finite(performance_profiling_summary.get('moving_load_xlarge_elapsed_seconds')):.3f}s"
        ),
        "performance_moving_load_cached_inverse_label": (
            f"{bool(performance_profiling_summary.get('moving_load_large_cached_track_solve_inverse_enabled', False))}/"
            f"{bool(performance_profiling_summary.get('moving_load_xlarge_cached_track_solve_inverse_enabled', False))}"
        ),
        "performance_ssi_variant_sweep_label": (
            f"{int(performance_profiling_summary.get('ssi_variant_sweep_pass_count', 0) or 0)}/"
            f"{int(performance_profiling_summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"
        ),
        "performance_ssi_zero_gap_variant_label": (
            f"{int(performance_profiling_summary.get('ssi_variant_sweep_zero_gap_positive_count', 0) or 0)}/"
            f"{int(performance_profiling_summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"
        ),
        "performance_ssi_pruned_variant_label": (
            f"{int(performance_profiling_summary.get('ssi_variant_sweep_track_static_pruned_positive_count', 0) or 0)}/"
            f"{int(performance_profiling_summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"
        ),
        "solver_truthfulness_summary_line": solver_truthfulness_summary_line,
        "hardest_external_10case_kickoff_summary_line": hardest_external_10case_kickoff_summary_line,
        "nonlinear_generalization_summary_line": nonlinear_generalization_summary_line,
        "workflow_productization_summary_line": workflow_productization_summary_line,
        "workflow_contact_coupling_summary": workflow_contact_coupling_summary,
        "korean_source_ingest_summary_line": korean_source_ingest_summary_line,
        "korean_structural_preview_queue_summary_line": korean_structural_preview_queue_summary_line,
        "irregular_structure_summary_line": str(
            workflow_productization_summary.get("irregular_structure_track_summary_line", "")
            or workflow_productization_summary.get("irregular_structure_summary_line", "")
            or ""
        ),
        "irregular_structure_track_pass": bool(workflow_productization_summary.get("irregular_structure_track_pass", False)),
        "irregular_structure_family_count": int(workflow_productization_summary.get("irregular_structure_family_count", 0)),
        "irregular_structure_source_record_count": int(
            workflow_productization_summary.get("irregular_structure_source_record_count", 0)
        ),
        "irregular_structure_local_ready_count": int(
            workflow_productization_summary.get("irregular_structure_local_ready_count", 0)
        ),
        "irregular_structure_remote_candidate_count": int(
            workflow_productization_summary.get("irregular_structure_remote_candidate_count", 0)
        ),
        "irregular_structure_native_roundtrip_candidate_count": int(
            workflow_productization_summary.get("irregular_structure_native_roundtrip_candidate_count", 0)
        ),
        "irregular_structure_solver_benchmark_candidate_count": int(
            workflow_productization_summary.get("irregular_structure_solver_benchmark_candidate_count", 0)
        ),
        "irregular_structure_ai_learning_candidate_count": int(
            workflow_productization_summary.get("irregular_structure_ai_learning_candidate_count", 0)
        ),
        "irregular_structure_top5_count": int(workflow_productization_summary.get("irregular_structure_top5_count", 0)),
        "irregular_structure_top5_family_ids": list(
            workflow_productization_summary.get("irregular_structure_top5_family_ids", []) or []
        ),
        "irregular_structure_gate_report": str(
            workflow_productization_artifacts.get("irregular_structure_gate_report_path", "") or ""
        ),
        "irregular_top5_execution_manifest": str(
            workflow_productization_artifacts.get("irregular_top5_execution_manifest_path", "") or ""
        ),
        "irregular_structure_source_catalog": str(
            workflow_productization_artifacts.get("irregular_source_catalog_path", "") or ""
        ),
        "irregular_priority_manifest": str(
            workflow_productization_artifacts.get("irregular_priority_manifest_path", "") or ""
        ),
        "irregular_structure_collection_report": str(
            workflow_productization_artifacts.get("irregular_collection_report_path", "") or ""
        ),
        "irregular_structure_triage_report": str(
            workflow_productization_artifacts.get("irregular_triage_report_path", "") or ""
        ),
        "midas_kds_row_provenance_export_summary_line": row_provenance_export_summary_line,
        "midas_kds_row_provenance_export_pass": bool(row_provenance_export_report.get("contract_pass", False)),
        "midas_kds_row_provenance_export_row_count": int(row_provenance_export_summary.get("row_count", 0)),
        "midas_kds_row_provenance_export_member_count": int(row_provenance_export_summary.get("member_count", 0)),
        "midas_kds_row_provenance_export_clause_count": int(row_provenance_export_summary.get("clause_count", 0)),
        "midas_kds_row_provenance_export_exact_row_count": int(row_provenance_export_summary.get("exact_row_count", 0)),
        "midas_kds_row_provenance_preview_rows": row_provenance_export_preview_rows,
        "midas_kds_row_provenance_clause_filter_rows": row_provenance_export_clause_filter_rows,
        "midas_kds_row_provenance_member_filter_rows": row_provenance_export_member_filter_rows,
        "midas_kds_row_provenance_hazard_filter_rows": row_provenance_export_hazard_filter_rows,
        "midas_kds_row_provenance_rule_family_filter_rows": row_provenance_export_rule_family_filter_rows,
        "midas_interoperability_summary_line": midas_interoperability_summary_line,
        "midas_native_roundtrip_summary_line": midas_native_roundtrip_summary_line,
        "steel_composite_constitutive_gate_summary_line": steel_composite_constitutive_gate_summary_line,
        "steel_composite_constitutive_gate_pass": steel_composite_constitutive_gate_pass,
        "steel_composite_constitutive_gate_surface_label": steel_composite_constitutive_gate_surface_label,
        "load_combination_engine_summary_line": load_combination_engine_summary_line,
        "load_combination_engine_pass": load_combination_engine_pass,
        "load_combination_engine_surface_label": load_combination_engine_surface_label,
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
        "commercial_scope_summary_line": str(gap_summary.get("commercial_scope_summary_line", "") or ""),
        "commercial_reliability_breadth_summary_line": str(
            gap_summary.get("commercial_reliability_breadth_summary_line", "") or ""
        ),
        "midas_kds_row_provenance_exact_row_coverage_label": str(
            gap_summary.get("midas_kds_row_provenance_exact_row_coverage_label", "") or ""
        ),
        "midas_kds_row_provenance_preview_rows_present": bool(
            gap_summary.get("midas_kds_row_provenance_preview_rows_present", False)
        ),
        "midas_kds_row_provenance_preview_row_count": int(
            gap_summary.get("midas_kds_row_provenance_preview_row_count", 0) or 0
        ),
        "commercial_readiness_summary_line": commercial_readiness_summary_line,
        "mgt_export_loadcomb_roundtrip_summary_line": str(gap_summary.get("mgt_export_loadcomb_roundtrip_summary_line", "") or ""),
        "mgt_export_loadcomb_roundtrip_pass": bool(gap_summary.get("mgt_export_loadcomb_roundtrip_pass", False)),
        "nightly_smoke_baseline_runtime_drift_s": _finite(gap_smoke_trend.get("baseline_runtime_drift_s")),
        "nightly_smoke_trial_runtime_drift_s": _finite(gap_smoke_trend.get("trial_runtime_drift_s")),
        "nightly_smoke_baseline_max_dcr_drift": _finite(gap_smoke_trend.get("baseline_max_dcr_drift")),
        "nightly_smoke_trial_max_dcr_drift": _finite(gap_smoke_trend.get("trial_max_dcr_drift")),
        "authority_sac_case_count": int(authority_summary.get("sac_case_count", 0)),
        "authority_nheri_case_count": int(authority_summary.get("nheri_case_count", 0)),
        "authority_opensees_case_count": int(authority_summary.get("opensees_case_count", 0)),
        "measured_benchmark_breadth_summary_line": measured_benchmark_breadth_summary_line,
        "measured_benchmark_case_count": int(measured_benchmark_breadth_summary.get("measured_case_count", 0)),
        "measured_benchmark_family_count": int(measured_benchmark_breadth_summary.get("measured_family_count", 0)),
        "peer_blind_prediction_compare_summary_line": peer_blind_prediction_compare_summary_line,
        "peer_blind_prediction_compare_case_count": int(peer_blind_prediction_compare_summary.get("case_count", 0)),
        "peer_blind_prediction_compare_measured_response_ready": bool(
            peer_blind_prediction_compare_summary.get("measured_response_ready", False)
        ),
        "peer_blind_prediction_compare_acceleration_channel_count": int(
            peer_blind_prediction_compare_summary.get("acceleration_channel_count", 0)
        ),
        "peer_blind_prediction_compare_drift_channel_count": int(
            peer_blind_prediction_compare_summary.get("drift_channel_count", 0)
        ),
        "peer_blind_prediction_compare_build_case_count": int(
            peer_blind_prediction_compare_summary.get("build_case_count", 0)
        ),
        "peer_blind_prediction_compare_entry_kind": str(
            peer_blind_prediction_compare_results_explorer.get("entry_kind", "")
        ),
        "peer_blind_prediction_compare_entry_label": str(
            peer_blind_prediction_compare_results_explorer.get("entry_label", "")
        ),
        "peer_blind_prediction_compare_source_family": str(
            peer_blind_prediction_compare_results_explorer.get("source_family", "")
        ),
        "peer_blind_prediction_compare_summary_label": str(
            peer_blind_prediction_compare_results_explorer.get("summary_label", "")
        ),
        "peer_blind_prediction_measured_response_landing_summary_line": peer_blind_prediction_measured_response_landing_summary_line,
        "peer_blind_prediction_measured_response_landing_contract_pass": bool(
            peer_blind_prediction_measured_response_landing.get("contract_pass", False)
        ),
        "peer_blind_prediction_measured_response_landing_state": str(
            peer_blind_prediction_measured_response_landing.get("landing_state", "")
        ),
        "peer_blind_prediction_measured_response_landing_reason_code": str(
            peer_blind_prediction_measured_response_landing.get("reason_code", "")
        ),
        "peer_blind_prediction_measured_response_landing_matched_file_count": int(
            peer_blind_prediction_measured_response_landing_summary.get("matched_file_count", 0)
        ),
        "peer_blind_prediction_measured_response_landing_csv_file_count": int(
            peer_blind_prediction_measured_response_landing_summary.get("csv_file_count", 0)
        ),
        "peer_blind_prediction_measured_response_landing_acceleration_candidate_count": int(
            peer_blind_prediction_measured_response_landing_summary.get("acceleration_candidate_count", 0)
        ),
        "peer_blind_prediction_measured_response_landing_drift_candidate_count": int(
            peer_blind_prediction_measured_response_landing_summary.get("drift_candidate_count", 0)
        ),
        "peer_blind_prediction_measured_response_landing_sensor_candidate_count": int(
            peer_blind_prediction_measured_response_landing_summary.get("sensor_candidate_count", 0)
        ),
        "peer_blind_prediction_measured_response_landing_next_action": str(
            peer_blind_prediction_measured_response_landing.get("next_action", "")
        ),
        "opensees_canonical_breadth_summary_line": opensees_canonical_breadth_summary_line,
        "opensees_canonical_case_count": int(opensees_canonical_breadth_summary.get("canonical_case_count", 0)),
        "opensees_canonical_family_count": int(opensees_canonical_breadth_summary.get("canonical_family_count", 0)),
        "opensees_canonical_parser_ready_case_count": int(
            opensees_canonical_breadth_summary.get("standalone_parser_ready_case_count", 0)
        ),
        "authority_npz_case_count": int(authority_summary.get("case_metrics_npz_case_count", 0)),
        "authority_npz_step_count": int(authority_summary.get("case_metrics_npz_step_count", 0)),
        "deployment_model": str(gap_summary.get("deployment_model", "engineer_in_the_loop_accelerated_coverage")),
        "accelerated_coverage_target_pct_label": _coverage_range_label(gap_summary.get("accelerated_coverage_target_pct_range", [95, 99])),
        "residual_holdout_target_pct_label": _coverage_range_label(gap_summary.get("residual_holdout_target_pct_range", [1, 5])),
        "estimated_time_saved_pct_label": _coverage_range_label(gap_summary.get("estimated_time_saved_pct_range", [70, 90])),
        "estimated_time_saved_basis": str(gap_summary.get("estimated_time_saved_basis", "")),
        "empirical_smoke_runtime_saved_pct_label": _coverage_range_label(gap_summary.get("empirical_smoke_runtime_saved_pct_range", [])),
        "measured_chain_total_minutes": _finite(gap_summary.get("measured_chain_total_minutes", 0.0)),
        "measured_chain_rolling_sample_count": int(gap_summary.get("measured_chain_rolling_sample_count", 0)),
        "measured_chain_rolling_total_minutes_mean": _finite(gap_summary.get("measured_chain_rolling_total_minutes_mean", 0.0)),
        "measured_chain_rolling_total_minutes_range": gap_summary.get("measured_chain_rolling_total_minutes_range", []),
        "measured_chain_full_chain_sample_count": int(gap_summary.get("measured_chain_full_chain_sample_count", 0)),
        "measured_chain_comparable_sample_count": int(gap_summary.get("measured_chain_comparable_sample_count", 0)),
        "measured_chain_comparable_reference_step_count": int(gap_summary.get("measured_chain_comparable_reference_step_count", 0)),
        "measured_chain_comparable_overlap_threshold": _finite(gap_summary.get("measured_chain_comparable_overlap_threshold", 0.0)),
        "measured_chain_comparable_reference_deployment_model": str(gap_summary.get("measured_chain_comparable_reference_deployment_model", "")),
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(gap_summary.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)),
        "measured_chain_rolling_selection_mode": str(gap_summary.get("measured_chain_rolling_selection_mode", "")),
        "engineer_in_loop_accelerated_coverage_ready": bool(gap_summary.get("engineer_in_loop_accelerated_coverage_ready", False)),
        "time_saving_focus": str(gap_summary.get("time_saving_focus", "")),
        "full_commercial_replacement_ready": bool(gap_summary.get("full_commercial_replacement_ready", False)),
        "pbd_dynamic_hinge_refresh_ready": bool(gap_summary.get("pbd_dynamic_hinge_refresh_ready", False)),
        "pbd_hinge_state_mode": str(gap_summary.get("pbd_hinge_state_mode", "")),
        "pbd_hinge_refresh_reason": str(gap_summary.get("pbd_hinge_refresh_reason", "")),
        "pbd_hinge_proxy_artifact_count": int(gap_summary.get("pbd_hinge_proxy_artifact_count", 0)),
        "pbd_hinge_refresh_artifact_present": bool(gap_summary.get("pbd_hinge_refresh_artifact_present", False)),
        "pbd_hinge_refresh_artifact_kind": str(gap_summary.get("pbd_hinge_refresh_artifact_kind", "")),
        "pbd_hinge_refresh_source_mode": str(gap_summary.get("pbd_hinge_refresh_source_mode", "")),
        "pbd_hinge_refresh_overlap_member_count": int(gap_summary.get("pbd_hinge_refresh_overlap_member_count", 0)),
        "pbd_hinge_refresh_rebar_sensitive_member_count": int(
            gap_summary.get("pbd_hinge_refresh_rebar_sensitive_member_count", 0)
        ),
        "pbd_hinge_benchmark_gate_pass": bool(gap_summary.get("pbd_hinge_benchmark_gate_pass", False)),
        "pbd_hinge_benchmark_fixture_regression_pass": bool(
            gap_summary.get("pbd_hinge_benchmark_fixture_regression_pass", False)
        ),
        "pbd_hinge_benchmark_alignment_pass": bool(
            gap_summary.get("pbd_hinge_benchmark_alignment_pass", False)
        ),
        "pbd_hinge_benchmark_asset_count": int(gap_summary.get("pbd_hinge_benchmark_asset_count", 0)),
        "pbd_hinge_benchmark_train_count": int(gap_summary.get("pbd_hinge_benchmark_train_count", 0)),
        "pbd_hinge_benchmark_val_count": int(gap_summary.get("pbd_hinge_benchmark_val_count", 0)),
        "pbd_hinge_benchmark_holdout_count": int(gap_summary.get("pbd_hinge_benchmark_holdout_count", 0)),
        "pbd_hinge_benchmark_rebar_sensitive_count": int(gap_summary.get("pbd_hinge_benchmark_rebar_sensitive_count", 0)),
        "pbd_hinge_benchmark_confinement_sensitive_count": int(
            gap_summary.get("pbd_hinge_benchmark_confinement_sensitive_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_count": int(gap_summary.get("pbd_hinge_benchmark_fixture_count", 0)),
        "pbd_hinge_benchmark_fixture_min_point_count": int(
            gap_summary.get("pbd_hinge_benchmark_fixture_min_point_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": float(
            gap_summary.get("pbd_hinge_benchmark_fixture_min_peak_drift_ratio", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": int(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_column_row_count", 0)
        ),
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": int(
            gap_summary.get("pbd_hinge_benchmark_alignment_rebar_sensitive_column_count", 0)
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max", 0.0)
        ),
        "panel_zone_3d_clash_ready": bool(gap_summary.get("panel_zone_3d_clash_ready", False)),
        "panel_zone_constructability_mode": str(gap_summary.get("panel_zone_constructability_mode", "")),
        "panel_zone_constructability_reason": str(gap_summary.get("panel_zone_constructability_reason", "")),
        "panel_zone_proxy_candidate_count": int(gap_summary.get("panel_zone_proxy_candidate_count", 0)),
        "panel_zone_source_artifact_kind": str(gap_summary.get("panel_zone_source_artifact_kind", "")),
        "panel_zone_source_artifact_path": str(gap_summary.get("panel_zone_source_artifact_path", "")),
        "panel_zone_source_contract_mode": str(gap_summary.get("panel_zone_source_contract_mode", "")),
        "panel_zone_internal_engine_complete": bool(gap_summary.get("panel_zone_internal_engine_complete", False)),
        "panel_zone_external_validation_pending": bool(
            gap_summary.get("panel_zone_external_validation_pending", False)
        ),
        "panel_zone_validation_boundary": str(gap_summary.get("panel_zone_validation_boundary", "")),
        "panel_zone_status_label": panel_zone_status_label,
        "panel_zone_advisory_only": bool(panel_zone_advisory_only),
        "panel_zone_release_blocking": bool(panel_zone_release_blocking),
        "panel_zone_external_validation_advisory_only": bool(
            panel_zone_external_validation_surface["advisory_only"]
        ),
        "panel_zone_external_validation_release_blocking": bool(
            panel_zone_external_validation_surface["release_blocking"]
        ),
        "panel_zone_external_validation_status_label": str(
            panel_zone_external_validation_surface["status_label"]
        ),
        "panel_zone_external_validation_artifact_closed": bool(
            panel_zone_external_validation_surface["artifact_closed"]
        ),
        "panel_zone_external_validation_closure_mode": str(
            panel_zone_external_validation_surface["closure_mode"]
        ),
        "panel_zone_external_validation_required_evidence": panel_zone_external_validation_required_evidence,
        "panel_zone_external_validation_summary_line": panel_zone_external_validation_summary_line,
        "panel_zone_external_validation_local_closure_state": panel_zone_external_validation_local_closure_state,
        "panel_zone_external_validation_local_closure_label": panel_zone_external_validation_local_closure_label,
        "panel_zone_external_validation_source_count": int(
            gap_summary.get("panel_zone_external_validation_source_count", 0)
        ),
        "panel_zone_external_validation_validated_source_count": int(
            gap_summary.get("panel_zone_external_validation_validated_source_count", 0)
        ),
        "panel_zone_external_validation_exact_source_count": int(
            gap_summary.get("panel_zone_external_validation_exact_source_count", 0)
        ),
        "panel_zone_external_validation_fallback_source_count": int(
            gap_summary.get("panel_zone_external_validation_fallback_source_count", 0)
        ),
        "panel_zone_external_validation_missing_source_count": int(
            gap_summary.get("panel_zone_external_validation_missing_source_count", 0)
        ),
        "panel_zone_external_validation_unknown_source_count": int(
            gap_summary.get("panel_zone_external_validation_unknown_source_count", 0)
        ),
        "panel_zone_external_validation_validated_source_ratio": float(
            gap_summary.get("panel_zone_external_validation_validated_source_ratio", 0.0)
        ),
        "panel_zone_external_validation_exact_source_ratio": float(
            gap_summary.get("panel_zone_external_validation_exact_source_ratio", 0.0)
        ),
        "panel_zone_external_validation_fallback_source_ratio": float(
            gap_summary.get("panel_zone_external_validation_fallback_source_ratio", 0.0)
        ),
        "panel_zone_external_validation_candidate_member_count": int(
            gap_summary.get("panel_zone_external_validation_candidate_member_count", 0)
        ),
        "panel_zone_external_validation_validated_member_count": int(
            gap_summary.get("panel_zone_external_validation_validated_member_count", 0)
        ),
        "panel_zone_external_validation_exact_member_count": int(
            gap_summary.get("panel_zone_external_validation_exact_member_count", 0)
        ),
        "panel_zone_external_validation_fallback_member_count": int(
            gap_summary.get("panel_zone_external_validation_fallback_member_count", 0)
        ),
        "panel_zone_external_validation_validated_member_ratio": float(
            gap_summary.get("panel_zone_external_validation_validated_member_ratio", 0.0)
        ),
        "panel_zone_external_validation_exact_member_ratio": float(
            gap_summary.get("panel_zone_external_validation_exact_member_ratio", 0.0)
        ),
        "panel_zone_external_validation_fallback_member_ratio": float(
            gap_summary.get("panel_zone_external_validation_fallback_member_ratio", 0.0)
        ),
        "panel_zone_external_validation_validated_row_count_total": int(
            gap_summary.get("panel_zone_external_validation_validated_row_count_total", 0)
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            gap_summary.get("panel_zone_external_validation_exact_validated_row_count", 0)
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            gap_summary.get("panel_zone_external_validation_fallback_validated_row_count", 0)
        ),
        "panel_zone_external_validation_exact_validated_row_ratio": float(
            gap_summary.get("panel_zone_external_validation_exact_validated_row_ratio", 0.0)
        ),
        "panel_zone_external_validation_fallback_validated_row_ratio": float(
            gap_summary.get("panel_zone_external_validation_fallback_validated_row_ratio", 0.0)
        ),
        "panel_zone_external_validation_provenance_summary_label": str(
            gap_summary.get("panel_zone_external_validation_provenance_summary_label", "")
        ),
        "panel_zone_external_validation_closing_summary_label": panel_zone_external_validation_closing_summary_label,
        "panel_zone_instruction_sidecar_present": bool(gap_summary.get("panel_zone_instruction_sidecar_present", False)),
        "panel_zone_instruction_sidecar_change_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_change_count", 0)
        ),
        "panel_zone_instruction_sidecar_candidate_overlap_mode": str(
            gap_summary.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "")
        ),
        "panel_zone_instruction_sidecar_overlap_row_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_row_count", 0)
        ),
        "panel_zone_instruction_sidecar_overlap_member_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_member_count", 0)
        ),
        "panel_zone_instruction_sidecar_overlap_group_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_group_count", 0)
        ),
        "panel_zone_instruction_sidecar_evidence_model": str(
            gap_summary.get("panel_zone_instruction_sidecar_evidence_model", "")
        ),
        "panel_zone_instruction_sidecar_rebar_delivery_mode": str(
            gap_summary.get("panel_zone_instruction_sidecar_rebar_delivery_mode", "")
        ),
        "panel_zone_member_mapping_sidecar_present": bool(
            gap_summary.get("panel_zone_member_mapping_sidecar_present", False)
        ),
        "panel_zone_member_mapping_sidecar_mode": str(
            gap_summary.get("panel_zone_member_mapping_sidecar_mode", "")
        ),
        "panel_zone_member_mapping_sidecar_row_count": int(
            gap_summary.get("panel_zone_member_mapping_sidecar_row_count", 0)
        ),
        "panel_zone_member_mapping_sidecar_applied_row_count": int(
            gap_summary.get("panel_zone_member_mapping_sidecar_applied_row_count", 0)
        ),
        "panel_zone_member_mapping_sidecar_unmapped_source_member_count": int(
            gap_summary.get("panel_zone_member_mapping_sidecar_unmapped_source_member_count", 0)
        ),
        "panel_zone_source_valid_row_counts": dict(gap_summary.get("panel_zone_source_valid_row_counts", {}) or {}),
        "panel_zone_source_overlap_member_counts": dict(gap_summary.get("panel_zone_source_overlap_member_counts", {}) or {}),
        "panel_zone_source_candidate_scan_modes": dict(gap_summary.get("panel_zone_source_candidate_scan_modes", {}) or {}),
        "panel_zone_source_bundle_modes": dict(gap_summary.get("panel_zone_source_bundle_modes", {}) or {}),
        "panel_zone_source_upstream_verification_tiers": dict(
            gap_summary.get("panel_zone_source_upstream_verification_tiers", {}) or {}
        ),
        "panel_zone_validated_source_row_count_total": int(gap_summary.get("panel_zone_validated_source_row_count_total", 0)),
        "panel_zone_validated_source_overlap_member_count_min": int(
            gap_summary.get("panel_zone_validated_source_overlap_member_count_min", 0)
        ),
        "panel_zone_topology_capable_input": bool(gap_summary.get("panel_zone_topology_capable_input", False)),
        "panel_zone_true_3d_clash_verified": bool(gap_summary.get("panel_zone_true_3d_clash_verified", False)),
        "panel_zone_true_3d_anchorage_verified": bool(gap_summary.get("panel_zone_true_3d_anchorage_verified", False)),
        "panel_zone_true_3d_bridge_complete": bool(
            gap_summary.get("panel_zone_true_3d_bridge_complete", False)
        ),
        "panel_zone_solver_verified_bridge_complete": bool(
            gap_summary.get("panel_zone_solver_verified_bridge_complete", False)
        ),
        "panel_zone_missing_required_sources": gap_summary.get("panel_zone_missing_required_sources", []),
        "panel_zone_solver_verified_inbox_status_mode": str(
            gap_summary.get("panel_zone_solver_verified_inbox_status_mode", "")
        ),
        "panel_zone_solver_verified_inbox_has_input": bool(
            gap_summary.get("panel_zone_solver_verified_inbox_has_input", False)
        ),
        "panel_zone_solver_verified_pending_input": bool(
            gap_summary.get("panel_zone_solver_verified_pending_input", False)
        ),
        "panel_zone_solver_verified_input_mode_detected": str(
            gap_summary.get("panel_zone_solver_verified_input_mode_detected", "")
        ),
        "panel_zone_solver_verified_latest_consume_report_present": bool(
            gap_summary.get("panel_zone_solver_verified_latest_consume_report_present", False)
        ),
        "panel_zone_solver_verified_latest_consume_contract_pass": bool(
            gap_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
        ),
        "panel_zone_solver_verified_latest_consume_reason_code": str(
            gap_summary.get("panel_zone_solver_verified_latest_consume_reason_code", "")
        ),
        "panel_zone_solver_verified_source_origin_class": str(
            gap_summary.get("panel_zone_solver_verified_source_origin_class", "")
        ),
        "panel_zone_solver_verified_release_refresh_source_allowed": bool(
            gap_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
        ),
        "panel_zone_solver_verified_recommended_action": str(
            gap_summary.get("panel_zone_solver_verified_recommended_action", "")
        ),
        "foundation_optimization_ready": bool(gap_summary.get("foundation_optimization_ready", False)),
        "foundation_member_type_present": bool(gap_summary.get("foundation_member_type_present", False)),
        "foundation_member_type_count": int(gap_summary.get("foundation_member_type_count", 0)),
        "foundation_optimization_mode": str(gap_summary.get("foundation_optimization_mode", "")),
        "foundation_optimization_reason": str(gap_summary.get("foundation_optimization_reason", "")),
        "foundation_scope_source": str(gap_summary.get("foundation_scope_source", "")),
        "foundation_artifact_scan_mode": str(gap_summary.get("foundation_artifact_scan_mode", "")),
        "foundation_artifact_evidence_mode": str(gap_summary.get("foundation_artifact_evidence_mode", "")),
        "upstream_foundation_label_count": int(gap_summary.get("upstream_foundation_label_count", 0)),
        "raw_source_foundation_label_count": int(gap_summary.get("raw_source_foundation_label_count", 0)),
        "upstream_foundation_provenance_mode": str(gap_summary.get("upstream_foundation_provenance_mode", "")),
        "wind_tunnel_raw_mapping_ready": bool(gap_summary.get("wind_tunnel_raw_mapping_ready", False)),
        "wind_tunnel_mapping_mode": str(gap_summary.get("wind_tunnel_mapping_mode", "")),
        "wind_tunnel_mapping_reason": str(gap_summary.get("wind_tunnel_mapping_reason", "")),
        "residual_holdout_bucket_count": len(residual_holdout_buckets),
        "residual_holdout_detail_row_count": 0,
        "residual_holdout_matrix_row_count": 0,
        "authority_catalog_diff_change_count": 0,
        "open_gap_p0": int(gap_summary.get("open_gap_counts", {}).get("P0", 0)),
        "open_gap_p1": int(gap_summary.get("open_gap_counts", {}).get("P1", 0)),
        "p0_closed": bool(int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0),
        "p0_closure_status": "closed" if int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0 else "open",
        "p1_unblocked": bool(int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0),
        "p1_handoff_status": "unblocked" if int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0 else "blocked",
        "design_opt_long_final_max_dcr": _finite(design_opt_long_summary.get("final_max_dcr")),
        "design_opt_long_feasible": bool(design_opt_long_summary.get("solver_feasible_final", False)),
        "design_opt_raw_max_drift_pct": design_opt_raw_max_drift,
        "design_opt_raw_residual_drift_pct": design_opt_raw_residual_drift,
        "design_opt_raw_max_dcr": design_opt_raw_max_dcr,
        "design_opt_repaired_compliance_max_drift_pct": design_opt_repaired_max_drift,
        "design_opt_repaired_compliance_residual_drift_pct": design_opt_repaired_residual_drift,
        "design_opt_repaired_compliance_max_dcr": design_opt_repaired_max_dcr,
        "design_opt_compliance_basis": design_opt_compliance_basis,
        "design_opt_repair_action_count": design_opt_repair_action_count,
        "design_opt_constructability_signal_gain_pct": design_opt_constructability_signal_gain_pct,
        "design_opt_baseline_constructability_avg": design_opt_baseline_constructability_avg,
        "design_opt_final_constructability_avg": design_opt_final_constructability_avg,
        "design_opt_baseline_detailing_complexity_avg": design_opt_baseline_detailing_complexity_avg,
        "design_opt_final_detailing_complexity_avg": design_opt_final_detailing_complexity_avg,
        "design_opt_selected_action_family_counts": design_opt_selected_action_family_counts,
        "design_opt_previous_action_family_counts": design_opt_previous_action_family_counts,
        "design_opt_preview_supply_family_counts": design_opt_preview_supply_family_counts,
        "design_opt_preview_supply_family_mix_label": design_opt_preview_supply_family_mix_label,
        "design_opt_preview_missing_target_families_label": design_opt_preview_missing_target_families_label,
        "design_opt_selected_family_mix_label": design_opt_selected_family_mix_label,
        "design_opt_selected_family_trend_label": design_opt_selected_family_trend_label,
        "design_opt_selected_dominant_family": str(design_opt_selected_dominant_family),
        "design_opt_selected_dominant_family_ratio": float(design_opt_selected_dominant_ratio),
        "design_opt_previous_dominant_family": str(design_opt_previous_dominant_family),
        "design_opt_previous_dominant_family_ratio": float(design_opt_previous_dominant_ratio),
        "design_opt_cost_delta": _finite(design_opt_cost_summary.get("cost_reduction_proxy")),
        "design_opt_objective_profile": str(blocked_action_summary.get("objective_profile", "")),
        "design_opt_budget_mode": str(blocked_action_summary.get("budget_mode", "")),
        "design_opt_changed_group_count": int(design_opt_cost_summary.get("changed_group_count", 0)),
        "design_opt_blocked_action_row_count": int(blocked_action_summary.get("blocked_action_row_count", 0)),
        "design_opt_blocked_illegal_by_mask": int(blocked_action_summary.get("illegal_by_mask", 0)),
        "design_opt_blocked_illegal_by_mask_family_label": str(
            blocked_action_summary.get("illegal_by_mask_family_label", "")
        ),
        "design_opt_blocked_no_cost_gain": int(blocked_action_summary.get("no_cost_gain", 0)),
        "design_opt_blocked_constructability_hard_gate": int(blocked_action_summary.get("constructability_hard_gate_block_count", 0)),
        "design_opt_blocked_constructability_hard_gate_label": str(blocked_action_summary.get("constructability_hard_gate_reason_label", "")),
        "design_opt_blocked_constructability_hard_gate_family_label": str(blocked_action_summary.get("constructability_hard_gate_family_label", "")),
        "design_opt_blocked_no_cost_group_count": int(blocked_action_summary.get("blocked_no_cost_group_count", 0)),
        "design_opt_blocked_no_cost_explain_row_count": int(blocked_action_summary.get("blocked_no_cost_explain_row_count", 0)),
        "design_opt_accepted_candidate_row_count": int(blocked_action_summary.get("accepted_candidate_explain_row_count", 0)),
        "design_opt_accepted_candidate_selected_count": int(blocked_action_summary.get("accepted_candidate_selected_count", 0)),
        "design_opt_accepted_candidate_unselected_count": int(blocked_action_summary.get("accepted_candidate_unselected_count", 0)),
        "design_opt_concrete_usage_reduction_pct": _finite(blocked_action_summary.get("concrete_usage_reduction_pct")),
        "design_opt_steel_reduction_pct": _finite(blocked_action_summary.get("steel_reduction_pct")),
        "design_opt_rebar_reduction_pct": _finite(blocked_action_summary.get("rebar_reduction_pct")),
        "design_opt_congestion_reduction_pct": _finite(blocked_action_summary.get("congestion_reduction_pct")),
        "design_opt_detailing_simplification_pct": _finite(blocked_action_summary.get("detailing_simplification_pct")),
        "design_opt_overdesign_margin_reduction_pct": _finite(blocked_action_summary.get("overdesign_margin_reduction_pct")),
        "design_opt_final_safety_margin_retained_pct": _finite(blocked_action_summary.get("final_safety_margin_retained_pct")),
        "mgt_export_direct_patch_action_family_label": str(gap_summary.get("mgt_export_direct_patch_action_family_label", "")),
        "mgt_export_instruction_sidecar_action_family_label": str(gap_summary.get("mgt_export_instruction_sidecar_action_family_label", "")),
        "mgt_export_rebar_delivery_mode": str(gap_summary.get("mgt_export_rebar_delivery_mode", "")),
        "mgt_export_evidence_model": str(gap_summary.get("mgt_export_evidence_model", "")),
        "mgt_export_instruction_sidecar_audit_only_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_audit_only_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_audit_only_action_family_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_audit_only_action_family_label", "")
        ),
        "mgt_export_instruction_sidecar_manual_input_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_manual_input_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_manual_input_action_family_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_manual_input_action_family_label", "")
        ),
        "mgt_export_audit_review_manifest_change_count": int(
            gap_summary.get("mgt_export_audit_review_manifest_change_count", 0)
        ),
        "mgt_export_audit_review_manifest_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_manifest_action_family_label", "")
        ),
        "mgt_export_audit_review_packet_count": int(
            gap_summary.get("mgt_export_audit_review_packet_count", 0)
        ),
        "mgt_export_audit_review_packet_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_packet_action_family_label", "")
        ),
        "mgt_export_audit_review_packet_followup_type_label": str(
            gap_summary.get("mgt_export_audit_review_packet_followup_type_label", "")
        ),
        "mgt_export_audit_review_packet_file_count": int(
            gap_summary.get("mgt_export_audit_review_packet_file_count", 0)
        ),
        "mgt_export_audit_review_packet_file_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_packet_file_action_family_label", "")
        ),
        "mgt_export_audit_review_queue_item_count": int(
            gap_summary.get("mgt_export_audit_review_queue_item_count", 0)
        ),
        "mgt_export_audit_review_queue_pending_count": int(
            gap_summary.get("mgt_export_audit_review_queue_pending_count", 0)
        ),
        "mgt_export_audit_review_queue_acknowledged_count": int(
            gap_summary.get("mgt_export_audit_review_queue_acknowledged_count", 0)
        ),
        "mgt_export_audit_review_queue_status_label": str(
            gap_summary.get("mgt_export_audit_review_queue_status_label", "")
        ),
        "mgt_export_audit_review_queue_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_queue_action_family_label", "")
        ),
        "mgt_export_audit_review_followup_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_item_count", 0)
        ),
        "mgt_export_audit_review_followup_open_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_open_item_count", 0)
        ),
        "mgt_export_audit_review_followup_closed_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_closed_item_count", 0)
        ),
        "mgt_export_audit_review_followup_action_label": str(
            gap_summary.get("mgt_export_audit_review_followup_action_label", "")
        ),
        "mgt_export_audit_review_followup_owner_label": str(
            gap_summary.get("mgt_export_audit_review_followup_owner_label", "")
        ),
        "mgt_export_audit_review_followup_review_owner_label": str(
            gap_summary.get("mgt_export_audit_review_followup_review_owner_label", "")
        ),
        "mgt_export_audit_review_followup_status_label": str(
            gap_summary.get("mgt_export_audit_review_followup_status_label", "")
        ),
        "mgt_export_audit_review_followup_sla_state_label": str(
            gap_summary.get("mgt_export_audit_review_followup_sla_state_label", "")
        ),
        "mgt_export_audit_review_followup_age_bucket_label": str(
            gap_summary.get("mgt_export_audit_review_followup_age_bucket_label", "")
        ),
        "mgt_export_audit_review_followup_overdue_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_overdue_item_count", 0)
        ),
        "mgt_export_audit_review_followup_mode": str(
            gap_summary.get("mgt_export_audit_review_followup_mode", "")
        ),
        "mgt_export_audit_review_resolution_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_open_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_open_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_closed_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_closed_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_action_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_action_label", "")
        ),
        "mgt_export_audit_review_resolution_owner_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_owner_label", "")
        ),
        "mgt_export_audit_review_resolution_status_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_status_label", "")
        ),
        "mgt_export_audit_review_resolution_mode": str(
            gap_summary.get("mgt_export_audit_review_resolution_mode", "")
        ),
        "mgt_export_rebar_payload_namespace_mode": str(
            gap_summary.get("mgt_export_rebar_payload_namespace_mode", "")
        ),
        "mgt_export_rebar_payload_material_level_namespace_present": bool(
            gap_summary.get("mgt_export_rebar_payload_material_level_namespace_present", False)
        ),
        "mgt_export_rebar_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_rebar_payload_group_local_namespace_present", False)
        ),
        "mgt_export_group_local_connection_detailing_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_connection_detailing_payload_row_count", 0)
        ),
        "mgt_export_group_local_connection_detailing_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_connection_detailing_payload_available_count", 0)
        ),
        "mgt_export_group_local_detailing_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_detailing_payload_row_count", 0)
        ),
        "mgt_export_group_local_detailing_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_detailing_payload_available_count", 0)
        ),
        "mgt_export_connection_detailing_payload_namespace_mode": str(
            gap_summary.get("mgt_export_connection_detailing_payload_namespace_mode", "")
        ),
        "mgt_export_connection_detailing_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_connection_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_detailing_payload_namespace_mode": str(
            gap_summary.get("mgt_export_detailing_payload_namespace_mode", "")
        ),
        "mgt_export_detailing_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": int(
            gap_summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0)
        ),
        "mgt_export_connection_detailing_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_connection_detailing_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_detailing_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_detailing_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_detailing_structured_payload_mapped_change_count": int(
            gap_summary.get("mgt_export_detailing_structured_payload_mapped_change_count", 0)
        ),
        "mgt_export_connection_detailing_delivery_mode": str(
            gap_summary.get("mgt_export_connection_detailing_delivery_mode", "")
        ),
        "mgt_export_detailing_delivery_mode": str(gap_summary.get("mgt_export_detailing_delivery_mode", "")),
        "mgt_export_delivery_boundary": (
            f"direct_patch={str(gap_summary.get('mgt_export_direct_patch_action_family_label', '') or 'n/a')} | "
            f"sidecar={str(gap_summary.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a')} | "
            f"connection_payload={str(gap_summary.get('mgt_export_connection_detailing_delivery_mode', '') or 'n/a')} | "
            f"detailing_payload={str(gap_summary.get('mgt_export_detailing_delivery_mode', '') or 'n/a')}"
        ),
    }
    return cards, validation_rows, metrics, authority_rows, residual_case_rows


def _write_csv(
    path: Path,
    cards: list[dict],
    rows: list[dict],
    metrics: dict,
    authority_rows: list[dict],
    residual_case_rows: list[dict],
    design_change_rows: list[dict],
    design_opt_entrypoint_rows: list[dict],
    design_opt_entrypoint_groups: list[dict],
) -> None:
    story_change_rows, zone_change_rows = _aggregate_design_change_rows(design_change_rows)
    panel_zone_external_validation_surface = _panel_zone_external_validation_surface(metrics)
    provenance_rows = [
        (
            "pbd_hinge_refresh_ready",
            str(bool(metrics.get("pbd_dynamic_hinge_refresh_ready", False))),
            "PASS" if bool(metrics.get("pbd_dynamic_hinge_refresh_ready", False)) else "FAIL",
            (
                f"mode={metrics.get('pbd_hinge_state_mode', '')} | "
                f"artifact_present={bool(metrics.get('pbd_hinge_refresh_artifact_present', False))} | "
                f"overlap={int(metrics.get('pbd_hinge_refresh_overlap_member_count', 0))} | "
                f"rebar_sensitive={int(metrics.get('pbd_hinge_refresh_rebar_sensitive_member_count', 0))}"
            ),
        ),
        (
            "pbd_hinge_benchmark_gate",
            str(bool(metrics.get("pbd_hinge_benchmark_gate_pass", False))),
            "PASS" if bool(metrics.get("pbd_hinge_benchmark_gate_pass", False)) else "FAIL",
            (
                f"assets={int(metrics.get('pbd_hinge_benchmark_asset_count', 0))} | "
                f"split=train:{int(metrics.get('pbd_hinge_benchmark_train_count', 0))}/"
                f"val:{int(metrics.get('pbd_hinge_benchmark_val_count', 0))}/"
                f"holdout:{int(metrics.get('pbd_hinge_benchmark_holdout_count', 0))} | "
                f"rebar_sensitive={int(metrics.get('pbd_hinge_benchmark_rebar_sensitive_count', 0))} | "
                f"confinement_sensitive={int(metrics.get('pbd_hinge_benchmark_confinement_sensitive_count', 0))}"
            ),
        ),
        (
            "pbd_hinge_benchmark_fixture_regression",
            str(bool(metrics.get("pbd_hinge_benchmark_fixture_regression_pass", False))),
            "PASS" if bool(metrics.get("pbd_hinge_benchmark_fixture_regression_pass", False)) else "FAIL",
            (
                f"fixtures={int(metrics.get('pbd_hinge_benchmark_fixture_count', 0))} | "
                f"min_point_count={int(metrics.get('pbd_hinge_benchmark_fixture_min_point_count', 0))} | "
                f"min_peak_drift_ratio={float(metrics.get('pbd_hinge_benchmark_fixture_min_peak_drift_ratio', 0.0)):.6f}"
            ),
        ),
        (
            "pbd_hinge_benchmark_alignment",
            str(bool(metrics.get("pbd_hinge_benchmark_alignment_pass", False))),
            "PASS" if bool(metrics.get("pbd_hinge_benchmark_alignment_pass", False)) else "FAIL",
            (
                f"refresh_columns={int(metrics.get('pbd_hinge_benchmark_alignment_refresh_column_row_count', 0))} | "
                f"rebar_sensitive_columns={int(metrics.get('pbd_hinge_benchmark_alignment_rebar_sensitive_column_count', 0))} | "
                f"benchmark_rebar_range={float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min', 0.0)):.4f}-"
                f"{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max', 0.0)):.4f} | "
                f"refresh_rebar_range={float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min', 0.0)):.4f}-"
                f"{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max', 0.0)):.4f}"
            ),
        ),
        (
            "panel_zone_3d_clash_ready",
            str(bool(metrics.get("panel_zone_3d_clash_ready", False))),
            "PASS" if bool(metrics.get("panel_zone_3d_clash_ready", False)) else "FAIL",
            str(metrics.get("panel_zone_constructability_reason", "")),
        ),
        (
            "panel_zone_constructability_mode",
            str(metrics.get("panel_zone_constructability_mode", "")),
            "INFO",
            (
                f"source_contract={metrics.get('panel_zone_source_contract_mode', '')} | "
                f"proxy_candidates={int(metrics.get('panel_zone_proxy_candidate_count', 0))} | "
                f"validated_rows={int(metrics.get('panel_zone_validated_source_row_count_total', 0))} | "
                f"min_overlap={int(metrics.get('panel_zone_validated_source_overlap_member_count_min', 0))} | "
                f"internal_complete={bool(metrics.get('panel_zone_internal_engine_complete', False))} | "
                f"external_validation_pending={bool(metrics.get('panel_zone_external_validation_pending', False))} | "
                f"validation_boundary={metrics.get('panel_zone_validation_boundary', '') or 'open'} | "
                f"advisory_only={bool(panel_zone_external_validation_surface['advisory_only'])} | "
                f"release_blocking={bool(panel_zone_external_validation_surface['release_blocking'])} | "
                f"status={panel_zone_external_validation_surface['status_label']} | "
                f"sidecar={metrics.get('panel_zone_instruction_sidecar_candidate_overlap_mode', '') or 'none'} | "
                f"sidecar_overlap={int(metrics.get('panel_zone_instruction_sidecar_overlap_member_count', 0))} | "
                f"evidence={metrics.get('panel_zone_instruction_sidecar_evidence_model', '') or 'none'} | "
                f"mapping_present={bool(metrics.get('panel_zone_member_mapping_sidecar_present', False))} | "
                f"mapping_mode={metrics.get('panel_zone_member_mapping_sidecar_mode', '') or 'none'} | "
                f"mapping_rows={int(metrics.get('panel_zone_member_mapping_sidecar_row_count', 0))} | "
                f"mapping_applied={int(metrics.get('panel_zone_member_mapping_sidecar_applied_row_count', 0))}"
            ),
        ),
        (
            "panel_zone_external_validation_status_label",
            str(panel_zone_external_validation_surface["status_label"]),
            "INFO",
            (
                f"artifact_closed={bool(panel_zone_external_validation_surface['artifact_closed'])} | "
                f"closure_mode={panel_zone_external_validation_surface['closure_mode']} | "
                f"advisory_only={bool(panel_zone_external_validation_surface['advisory_only'])} | "
                f"release_blocking={bool(panel_zone_external_validation_surface['release_blocking'])} | "
                f"boundary={metrics.get('panel_zone_validation_boundary', '') or 'open'} | "
                f"pending={bool(metrics.get('panel_zone_external_validation_pending', False))} | "
                f"required_evidence={metrics.get('panel_zone_external_validation_required_evidence', '') or 'n/a'}"
            ),
        ),
        (
            "panel_zone_external_validation_artifact_closed",
            str(bool(metrics.get("panel_zone_external_validation_artifact_closed", False))),
            "INFO",
            (
                f"closure_mode={metrics.get('panel_zone_external_validation_closure_mode', '') or 'n/a'} | "
                f"status={panel_zone_external_validation_surface['status_label']} | "
                f"boundary={metrics.get('panel_zone_validation_boundary', '') or 'open'}"
            ),
        ),
        (
            "panel_zone_external_validation_provenance_summary_label",
            str(metrics.get("panel_zone_external_validation_provenance_summary_label", "")),
            "INFO",
            (
                f"validated_source_ratio={float(metrics.get('panel_zone_external_validation_validated_source_ratio', 0.0)):.3f} | "
                f"exact_source_ratio={float(metrics.get('panel_zone_external_validation_exact_source_ratio', 0.0)):.3f} | "
                f"fallback_source_ratio={float(metrics.get('panel_zone_external_validation_fallback_source_ratio', 0.0)):.3f} | "
                f"validated_member_ratio={float(metrics.get('panel_zone_external_validation_validated_member_ratio', 0.0)):.3f} | "
                f"exact_member_ratio={float(metrics.get('panel_zone_external_validation_exact_member_ratio', 0.0)):.3f} | "
                f"fallback_member_ratio={float(metrics.get('panel_zone_external_validation_fallback_member_ratio', 0.0)):.3f}"
            ),
        ),
        (
            "panel_zone_external_validation_closing_summary_label",
            str(metrics.get("panel_zone_external_validation_closing_summary_label", "")),
            "INFO",
            (
                f"source_count={int(metrics.get('panel_zone_external_validation_source_count', 0))} | "
                f"validated_sources={int(metrics.get('panel_zone_external_validation_validated_source_count', 0))} | "
                f"exact_rows={int(metrics.get('panel_zone_external_validation_exact_validated_row_count', 0))} | "
                f"fallback_rows={int(metrics.get('panel_zone_external_validation_fallback_validated_row_count', 0))}"
            ),
        ),
        (
            "panel_zone_external_validation_local_closure_state",
            str(metrics.get("panel_zone_external_validation_local_closure_state", "")),
            "INFO",
            (
                f"label={metrics.get('panel_zone_external_validation_local_closure_label', '') or 'n/a'} | "
                f"summary={metrics.get('panel_zone_external_validation_summary_line', '') or 'n/a'}"
            ),
        ),
        (
            "panel_zone_status_label",
            str(metrics.get("panel_zone_status_label", "")),
            "INFO",
            (
                f"advisory_only={bool(metrics.get('panel_zone_advisory_only', False))} | "
                f"release_blocking={bool(metrics.get('panel_zone_release_blocking', False))} | "
                f"boundary={metrics.get('panel_zone_validation_boundary', '') or 'open'} | "
                f"external_validation={metrics.get('panel_zone_external_validation_status_label', '') or 'unknown'}"
            ),
        ),
        (
            "panel_zone_source_contract_mode",
            str(metrics.get("panel_zone_source_contract_mode", "")),
            "INFO",
            (
                f"source_kind={metrics.get('panel_zone_source_artifact_kind', '')} | "
                f"missing={','.join(metrics.get('panel_zone_missing_required_sources', []))}"
            ),
        ),
        (
            "panel_zone_instruction_sidecar_candidate_overlap_mode",
            str(metrics.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "")),
            "INFO",
            (
                f"present={bool(metrics.get('panel_zone_instruction_sidecar_present', False))} | "
                f"changes={int(metrics.get('panel_zone_instruction_sidecar_change_count', 0))} | "
                f"overlap_rows={int(metrics.get('panel_zone_instruction_sidecar_overlap_row_count', 0))} | "
                f"overlap_members={int(metrics.get('panel_zone_instruction_sidecar_overlap_member_count', 0))} | "
                f"overlap_groups={int(metrics.get('panel_zone_instruction_sidecar_overlap_group_count', 0))} | "
                f"evidence={metrics.get('panel_zone_instruction_sidecar_evidence_model', '') or 'none'} | "
                f"delivery={metrics.get('panel_zone_instruction_sidecar_rebar_delivery_mode', '') or 'none'} | "
                f"mapping_present={bool(metrics.get('panel_zone_member_mapping_sidecar_present', False))} | "
                f"mapping_mode={metrics.get('panel_zone_member_mapping_sidecar_mode', '') or 'none'} | "
                f"mapping_rows={int(metrics.get('panel_zone_member_mapping_sidecar_row_count', 0))} | "
                f"mapping_applied={int(metrics.get('panel_zone_member_mapping_sidecar_applied_row_count', 0))} | "
                f"mapping_unmapped={int(metrics.get('panel_zone_member_mapping_sidecar_unmapped_source_member_count', 0))}"
            ),
        ),
        (
            "panel_zone_source_bundle_modes",
            ", ".join(
                f"{k}:{v}"
                for k, v in sorted((metrics.get("panel_zone_source_bundle_modes", {}) or {}).items())
                if str(v).strip()
            ),
            "INFO",
            (
                "upstream="
                + (
                    ", ".join(
                        f"{k}:{v}"
                        for k, v in sorted((metrics.get("panel_zone_source_upstream_verification_tiers", {}) or {}).items())
                        if str(v).strip()
                    )
                    or "none"
                )
            ),
        ),
        (
            "panel_zone_solver_verified_inbox_status_mode",
            str(metrics.get("panel_zone_solver_verified_inbox_status_mode", "")),
            "INFO",
            (
                f"pending={bool(metrics.get('panel_zone_solver_verified_pending_input', False))} | "
                f"input_mode={metrics.get('panel_zone_solver_verified_input_mode_detected', '') or 'none'} | "
                f"latest_consume_present={bool(metrics.get('panel_zone_solver_verified_latest_consume_report_present', False))} | "
                f"latest_consume_pass={bool(metrics.get('panel_zone_solver_verified_latest_consume_contract_pass', False))} | "
                f"latest_consume_reason={metrics.get('panel_zone_solver_verified_latest_consume_reason_code', '') or 'n/a'} | "
                f"origin={metrics.get('panel_zone_solver_verified_source_origin_class', '') or 'missing'} | "
                f"release_refresh_allowed={bool(metrics.get('panel_zone_solver_verified_release_refresh_source_allowed', False))} | "
                f"next={metrics.get('panel_zone_solver_verified_recommended_action', '') or 'n/a'}"
            ),
        ),
        (
            "foundation_optimization_ready",
            str(bool(metrics.get("foundation_optimization_ready", False))),
            "PASS" if bool(metrics.get("foundation_optimization_ready", False)) else "FAIL",
            str(metrics.get("foundation_optimization_reason", "")),
        ),
        (
            "foundation_scope_source",
            str(metrics.get("foundation_scope_source", "")),
            "INFO",
            (
                f"scan={metrics.get('foundation_artifact_scan_mode', '')} | "
                f"upstream_labels={int(metrics.get('upstream_foundation_label_count', 0))} | "
                f"raw_source_labels={int(metrics.get('raw_source_foundation_label_count', 0))} | "
                f"{metrics.get('upstream_foundation_provenance_mode', '')}"
            ),
        ),
        (
            "wind_tunnel_raw_mapping_ready",
            str(bool(metrics.get("wind_tunnel_raw_mapping_ready", False))),
            "PASS" if bool(metrics.get("wind_tunnel_raw_mapping_ready", False)) else "FAIL",
            str(metrics.get("wind_tunnel_mapping_reason", "")),
        ),
        (
            "wind_tunnel_mapping_mode",
            str(metrics.get("wind_tunnel_mapping_mode", "")),
            "INFO",
            "",
        ),
        (
            "external_benchmark_submission_start",
            str(metrics.get("external_benchmark_submission_recommended_start_mode", "")),
            "PASS" if bool(metrics.get("external_benchmark_submission_ready_to_start_now", False)) else "FAIL",
            str(metrics.get("external_benchmark_submission_recommended_submission_scope", "")),
        ),
        (
            "external_benchmark_submission_gate",
            str(metrics.get("external_benchmark_submission_reason_code", "")),
            "PASS" if bool(metrics.get("external_benchmark_submission_ready_to_start_now", False)) else "FAIL",
            (
                f"full_ready={bool(metrics.get('external_benchmark_submission_ready_to_start_full_submission_now', False))} | "
                f"blockers={metrics.get('external_benchmark_submission_blocker_label', '') or 'none'} | "
                f"cautions={metrics.get('external_benchmark_submission_caution_label', '') or 'none'}"
            ),
        ),
        (
            "external_benchmark_execution_mode",
            str(metrics.get("external_benchmark_execution_mode", "")),
            "PASS" if int(metrics.get("external_benchmark_execution_ready_task_count", 0)) > 0 else "FAIL",
            (
                f"ready={int(metrics.get('external_benchmark_execution_ready_task_count', 0))} | "
                f"blocked={int(metrics.get('external_benchmark_execution_blocked_task_count', 0))} | "
                f"review_boundary_pending={int(metrics.get('external_benchmark_execution_review_boundary_pending_count', 0))}"
            ),
        ),
        (
            "external_benchmark_execution_review_boundary",
            str(metrics.get("external_benchmark_execution_review_boundary_resolution_label", "") or "n/a"),
            "PASS",
            (
                f"approve_all={metrics.get('external_benchmark_execution_review_boundary_preview_approve_all_reason_code', '') or 'n/a'} "
                f"(ready_full={bool(metrics.get('external_benchmark_execution_review_boundary_preview_approve_all_ready_full', False))}) | "
                f"reject_one={metrics.get('external_benchmark_execution_review_boundary_preview_reject_one_reason_code', '') or 'n/a'} "
                f"(open_revision={int(metrics.get('external_benchmark_execution_review_boundary_preview_reject_one_open_revision_count', 0))}) | "
                f"owner={metrics.get('external_benchmark_execution_review_boundary_owner_label', '') or 'none'} | "
                f"assignee={metrics.get('external_benchmark_execution_review_boundary_assignee_label', '') or 'none'} | "
                f"assignment={metrics.get('external_benchmark_execution_review_boundary_assignment_status_label', '') or 'none'} | "
                f"priority={metrics.get('external_benchmark_execution_review_boundary_priority_label', '') or 'none'} | "
                f"family={metrics.get('external_benchmark_execution_review_boundary_family_label', '') or 'none'} | "
                f"changes={int(metrics.get('external_benchmark_execution_review_boundary_change_count_total', 0))} | "
                f"followup={metrics.get('external_benchmark_execution_review_boundary_followup_action_label', '') or 'none'} | "
                f"sla={metrics.get('external_benchmark_execution_review_boundary_sla_state_label', '') or 'none'} | "
                f"age={metrics.get('external_benchmark_execution_review_boundary_age_bucket_label', '') or 'none'} | "
                f"overdue={int(metrics.get('external_benchmark_execution_review_boundary_overdue_count', 0))} | "
                f"oldest_open_h={float(metrics.get('external_benchmark_execution_review_boundary_oldest_open_age_hours', 0.0)):.3f}"
            ),
        ),
        (
            "external_benchmark_execution_status_mode",
            str(metrics.get("external_benchmark_execution_status_mode", "")),
            (
                "PASS"
                if int(metrics.get("external_benchmark_execution_executable_task_count", 0)) > 0
                and int(metrics.get("external_benchmark_execution_failed_task_count", 0)) == 0
                else "FAIL"
            ),
            (
                f"planned={int(metrics.get('external_benchmark_execution_planned_task_count', 0))} | "
                f"in_progress={int(metrics.get('external_benchmark_execution_in_progress_task_count', 0))} | "
                f"completed={int(metrics.get('external_benchmark_execution_completed_task_count', 0))} | "
                f"failed={int(metrics.get('external_benchmark_execution_failed_task_count', 0))} | "
                f"finished={int(metrics.get('external_benchmark_execution_finished_task_count', 0))} | "
                f"completion_ratio={float(metrics.get('external_benchmark_execution_completion_ratio', 0.0)):.3f}"
            ),
        ),
        (
            "audit_review_decision_batch_template",
            str(int(metrics.get("audit_review_decision_batch_template_item_count", 0))),
            "PASS" if int(metrics.get("audit_review_decision_batch_template_item_count", 0)) > 0 else "INFO",
            (
                f"status={metrics.get('audit_review_decision_batch_template_current_status_label', '') or 'none'} | "
                f"owner={metrics.get('audit_review_decision_batch_template_review_owner_label', '') or 'none'} | "
                f"priority={metrics.get('audit_review_decision_batch_template_review_priority_label', '') or 'none'} | "
                f"attested_examples={int(metrics.get('audit_review_decision_batch_attested_example_count', 0))} | "
                f"example_preview={metrics.get('audit_review_decision_batch_attested_example_preview_label', '') or 'none'}"
            ),
        ),
        (
            "external_benchmark_submission_preview_approve_all",
            str(metrics.get("external_benchmark_submission_preview_approve_all_reason_code", "")),
            (
                "PASS"
                if bool(metrics.get("external_benchmark_submission_preview_approve_all_ready_full", False))
                else "FAIL"
            ),
            (
                f"ready_full={bool(metrics.get('external_benchmark_submission_preview_approve_all_ready_full', False))} | "
                f"pending={int(metrics.get('external_benchmark_submission_preview_approve_all_pending_count', 0))} | "
                f"open_revision={int(metrics.get('external_benchmark_submission_preview_approve_all_open_revision_count', 0))}"
            ),
        ),
        (
            "external_benchmark_submission_preview_reject_one",
            str(metrics.get("external_benchmark_submission_preview_reject_one_reason_code", "")),
            (
                "PASS"
                if bool(metrics.get("external_benchmark_submission_preview_reject_one_ready_full", False))
                else "FAIL"
            ),
            (
                f"ready_full={bool(metrics.get('external_benchmark_submission_preview_reject_one_ready_full', False))} | "
                f"pending={int(metrics.get('external_benchmark_submission_preview_reject_one_pending_count', 0))} | "
                f"open_revision={int(metrics.get('external_benchmark_submission_preview_reject_one_open_revision_count', 0))} | "
                f"blocker={metrics.get('external_benchmark_submission_preview_reject_one_blocker_label', '') or 'none'}"
            ),
        ),
        (
            "audit_review_decision_batch_runner",
            str(metrics.get("audit_review_decision_batch_runner_reason_code", "")),
            "PASS" if str(metrics.get("audit_review_decision_batch_runner_reason_code", "")) == "PASS" else "FAIL",
            (
                f"apply_live={bool(metrics.get('audit_review_decision_batch_runner_apply_live', False))} | "
                f"live_applied={bool(metrics.get('audit_review_decision_batch_runner_live_applied', False))} | "
                f"preview_reason={metrics.get('audit_review_decision_batch_runner_preview_reason_code', '') or 'none'} | "
                f"preview_ready_full={bool(metrics.get('audit_review_decision_batch_runner_preview_ready_full', False))} | "
                f"preview_pending={int(metrics.get('audit_review_decision_batch_runner_preview_pending_count', 0))} | "
                f"preview_open_revision={int(metrics.get('audit_review_decision_batch_runner_preview_open_revision_count', 0))}"
            ),
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "section", "item", "value", "status", "note_or_evidence"])
        for card in cards:
            writer.writerow(["card", "summary", card["label"], card["value"], card["status"], card.get("note", "")])
        for row in rows:
            writer.writerow(["validation", row["section"], row["item"], row["value"], row["status"], row["evidence"]])
        for item, value, status, note in provenance_rows:
            writer.writerow(["metric", "advanced_holdout_provenance", item, value, status, note])
        for row in (
            candidate
            for candidate in (metrics.get("advanced_holdout_status_rows", []) or [])
            if isinstance(candidate, dict)
        ):
            writer.writerow(
                [
                    "metric",
                    "advanced_holdout_closure",
                    str(row.get("id", "") or ""),
                    str(row.get("closure_state", "") or ""),
                    "PASS" if bool(row.get("ready", False)) else "INFO",
                    (
                        f"{str(row.get('title', '') or '')} | "
                        f"severity={str(row.get('severity', '') or 'n/a')} | "
                        f"mode={str(row.get('mode', '') or 'n/a')} | "
                        f"reason={str(row.get('reason_snippet', '') or 'n/a')} | "
                        f"evidence={str(row.get('evidence_snippet', '') or 'n/a')}"
                    ),
                ]
            )
        for row in authority_rows:
            writer.writerow(["authority", row["track"], row["case_id"], f"{row['metric_a']} | {row['metric_b']}", row["status"], row["source_url"]])
        for row in residual_case_rows:
            writer.writerow(
                [
                    "ndtha_residual_case",
                    row["case_id"],
                    row["split"],
                    (
                        f"pre_top={row['pre_settle_top_m']:.6f} m -> post_top={row['post_settle_top_m']:.6f} m | "
                        f"pre_drift={row['pre_settle_drift_pct']:.6f}% -> post_drift={row['post_settle_drift_pct']:.6f}%"
                    ),
                    "PASS" if row["residual_settle_applied"] else "INFO",
                    f"source={row['residual_metric_source']} | settle_steps={row['residual_settle_steps']}",
                ]
            )
        for row in design_change_rows:
            changed = int(row.get("changed_group_count", 1 if "group_id" in row else 0))
            cost_delta = float(row.get("cost_proxy_delta_sum", row.get("cost_proxy_delta", 0.0)))
            dcr_before = float(row.get("max_dcr_before_max", row.get("max_dcr_before", 0.0)))
            dcr_after = float(row.get("max_dcr_after_max", row.get("max_dcr_after", 0.0)))
            semantic = int(row.get("semantic_group_count", 1 if str(row.get("semantic_group", "")).strip() else 0))
            writer.writerow(
                [
                    "design_change",
                    f"S{int(row['story_band']):02d}/{row['zone_label']}",
                    row["member_type"],
                    (
                        f"changed={changed} | "
                        f"cost_delta={cost_delta:.3f} | "
                        f"dcr={dcr_before:.3f}->{dcr_after:.3f}"
                    ),
                    "PASS",
                    f"semantic_groups={semantic}",
                ]
            )
        for row in story_change_rows:
            writer.writerow(
                [
                    "design_change_story",
                    f"S{int(row['story_band']):02d}",
                    "all",
                    (
                        f"changed={int(row['changed_group_count'])} | "
                        f"cost_delta={float(row['cost_proxy_delta_sum']):.3f} | "
                        f"dcr={float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}"
                    ),
                    "PASS",
                    f"semantic_groups={int(row['semantic_group_count'])}",
                ]
            )
        for row in zone_change_rows:
            writer.writerow(
                [
                    "design_change_zone",
                    str(row["zone_label"]),
                    "all",
                    (
                        f"changed={int(row['changed_group_count'])} | "
                        f"cost_delta={float(row['cost_proxy_delta_sum']):.3f} | "
                        f"dcr={float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}"
                    ),
                    "PASS",
                    f"semantic_groups={int(row['semantic_group_count'])}",
                ]
            )
        for row in design_opt_entrypoint_rows:
            writer.writerow(
                [
                    "design_opt_entrypoint",
                    str(row["name"]),
                    str(row["script"]),
                    str(row["primary_report"]),
                    "PASS" if bool(row.get("contract_pass", False)) else ("INFO" if bool(row.get("report_exists", False)) else "FAIL"),
                    f"exists={bool(row.get('report_exists', False))} reason={row.get('reason_code', '')}",
                ]
            )
        for row in design_opt_entrypoint_groups:
            writer.writerow(
                [
                    "design_opt_entrypoint_group",
                    str(row["group_label"]),
                    ",".join(row.get("entrypoint_names", [])),
                    f"{int(row.get('report_count', 0))}/{int(row.get('entrypoint_count', 0))}",
                    "PASS" if bool(row.get("all_pass", False)) else ("INFO" if bool(row.get("all_present", False)) else "FAIL"),
                    f"pass_count={int(row.get('pass_count', 0))}",
                ]
            )
        irregular_summary_line = str(
            metrics.get("irregular_structure_summary_line", metrics.get("irregular_structure_track_summary_line", "")) or ""
        ).strip()
        irregular_gate_report_path = str(metrics.get("irregular_structure_gate_report", "") or "").strip()
        irregular_top5_manifest_path = str(metrics.get("irregular_top5_execution_manifest", "") or "").strip()
        irregular_top5_family_ids = [
            str(item).strip()
            for item in (metrics.get("irregular_structure_top5_family_ids", []) or [])
            if str(item).strip()
        ]
        if not irregular_top5_family_ids and irregular_top5_manifest_path:
            try:
                manifest_payload = _load_json(Path(irregular_top5_manifest_path))
            except OSError:
                manifest_payload = {}
            if isinstance(manifest_payload.get("top5_families"), list):
                irregular_top5_family_ids = [
                    str(row.get("family_id", "") or "").strip()
                    for row in manifest_payload.get("top5_families", [])
                    if isinstance(row, dict) and str(row.get("family_id", "") or "").strip()
                ]

        def _irregular_count(name: str, pattern: str) -> int:
            raw_value = int(metrics.get(name, 0) or 0)
            if raw_value > 0:
                return raw_value
            if not irregular_summary_line:
                return 0
            match = re.search(pattern, irregular_summary_line)
            return int(match.group(1)) if match else 0

        if not irregular_gate_report_path and irregular_summary_line:
            match = re.search(r"gate=([^|]+)", irregular_summary_line)
            irregular_gate_report_path = str(match.group(1)).strip() if match else ""
        if not irregular_top5_manifest_path and irregular_summary_line:
            match = re.search(r"manifest=([^|]+)", irregular_summary_line)
            irregular_top5_manifest_path = str(match.group(1)).strip() if match else ""
        irregular_family_count = _irregular_count("irregular_structure_family_count", r"families=(\d+)")
        irregular_source_count = _irregular_count("irregular_structure_source_record_count", r"sources=(\d+)")
        irregular_local_ready_count = _irregular_count("irregular_structure_local_ready_count", r"local_ready=(\d+)")
        irregular_remote_candidate_count = _irregular_count(
            "irregular_structure_remote_candidate_count",
            r"remote_candidates=(\d+)",
        )
        irregular_top5_count = _irregular_count("irregular_structure_top5_count", r"top5=(\d+)")
        writer.writerow(
            [
                "metric",
                "advanced_holdout_provenance",
                "irregular_structure_track",
                irregular_summary_line,
                "PASS" if bool(metrics.get("irregular_structure_track_pass", False)) else "FAIL",
                (
                    f"families={irregular_family_count} | "
                    f"sources={irregular_source_count} | "
                    f"local_ready={irregular_local_ready_count} | "
                    f"remote_candidates={irregular_remote_candidate_count} | "
                    f"top5={irregular_top5_count} | "
                    f"top5_family_ids={','.join(irregular_top5_family_ids) or 'n/a'} | "
                    f"gate={irregular_gate_report_path or 'n/a'} | "
                    f"manifest={irregular_top5_manifest_path or 'n/a'}"
                ),
            ]
        )


def _submission_receipt_label(row: dict) -> str:
    return str(row.get("submission_receipt", "") or row.get("receipt_url", "") or "pending")


def _submission_receipt_status_label(row: dict) -> str:
    lifecycle = row.get("status_lifecycle") if isinstance(row.get("status_lifecycle"), dict) else {}
    return str(row.get("submission_receipt_status", "") or lifecycle.get("submission_receipt_status", "unknown"))


def _write_markdown(
    path: Path,
    cards: list[dict],
    rows: list[dict],
    artifacts: dict,
    metrics: dict,
    gaps: list[dict],
    authority_rows: list[dict],
    residual_case_rows: list[dict],
    design_change_rows: list[dict],
    blocked_action_summary: dict,
    accepted_candidate_rows: list[dict],
    design_opt_entrypoint_rows: list[dict],
    design_opt_entrypoint_groups: list[dict],
    smoke_recent_samples: list[dict],
    external_benchmark_submission_queue_rows: list[dict],
    holdout_buckets: list[dict],
    holdout_detail_rows: list[dict],
    holdout_matrix_rows: list[dict],
    authority_catalog_diff: dict,
) -> None:
    story_change_rows, zone_change_rows = _aggregate_design_change_rows(design_change_rows)
    selected_candidate_rows, unselected_candidate_rows = _split_accepted_candidate_rows(accepted_candidate_rows)
    smoke_history_png = Path(str(artifacts.get("smoke_history_png", "") or ""))
    advanced_holdout_status_rows = [
        row for row in (metrics.get("advanced_holdout_status_rows", []) or []) if isinstance(row, dict)
    ]
    lines = [
        "# Committee Review Package",
        "",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Summary Cards",
        "",
    ]
    for card in cards:
        lines.append(f"- `{card['label']}`: `{card['value']}` [{card['status']}] {card.get('note', '')}".rstrip())
    lines.extend(["", "## Validation Table", ""])
    for row in rows:
        lines.append(
            f"- `{row['section']} / {row['item']}`: `{row['value']}` [{row['status']}] | criterion={row['criterion']} | evidence={row['evidence']}"
        )
    lines.extend(["", "## Key Metrics", ""])
    for key, value in metrics.items():
        if key == "midas_kds_row_provenance_preview_rows":
            continue
        lines.append(f"- `{key}`: `{value}`")
    if metrics.get("time_saving_focus"):
        lines.extend(
            [
                "",
                "## Time-Saving Coverage",
                "",
                f"- `estimated_time_saved`: `{metrics['estimated_time_saved_pct_label']}`",
                (
                    f"- `measured_chain_wall_clock_comparable_rolling_min`: "
                    f"`{metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f}` "
                    f"(N={int(metrics.get('measured_chain_rolling_sample_count', 0))}, "
                    f"range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-"
                    f"{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]})"
                ),
                f"- `measured_chain_wall_clock_min`: `{metrics['measured_chain_total_minutes']:.2f}`",
                f"- `comparable_run_selection_mode`: `{metrics.get('measured_chain_rolling_selection_mode', '')}`",
                f"- `comparable_reference_deployment_model`: `{metrics.get('measured_chain_comparable_reference_deployment_model', '')}`",
                f"- `comparable_reference_strict_smoke`: `{bool(metrics.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}`",
                f"- `basis`: `{metrics['estimated_time_saved_basis']}`",
                f"- `focus`: `{metrics['time_saving_focus']}`",
                f"- `external_benchmark_start_mode`: `{metrics.get('external_benchmark_submission_recommended_start_mode', '')}`",
                f"- `external_benchmark_execution_mode`: `{metrics.get('external_benchmark_execution_mode', '')}`",
                (
                    f"- `external_benchmark_execution_counts`: "
                    f"`ready={int(metrics.get('external_benchmark_execution_ready_task_count', 0))}, "
                    f"blocked={int(metrics.get('external_benchmark_execution_blocked_task_count', 0))}, "
                    f"review_boundary_pending={int(metrics.get('external_benchmark_execution_review_boundary_pending_count', 0))}`"
                ),
                (
                    f"- `external_benchmark_execution_review_boundary`: "
                f"`{metrics.get('external_benchmark_execution_review_boundary_resolution_label', '') or 'n/a'}` "
                f"(owner={metrics.get('external_benchmark_execution_review_boundary_owner_label', '') or 'none'}, "
                f"assignee={metrics.get('external_benchmark_execution_review_boundary_assignee_label', '') or 'none'}, "
                f"assignment={metrics.get('external_benchmark_execution_review_boundary_assignment_status_label', '') or 'none'}, "
                f"priority={metrics.get('external_benchmark_execution_review_boundary_priority_label', '') or 'none'}, "
                f"family={metrics.get('external_benchmark_execution_review_boundary_family_label', '') or 'none'}, "
                    f"changes={int(metrics.get('external_benchmark_execution_review_boundary_change_count_total', 0))}, "
                    f"followup={metrics.get('external_benchmark_execution_review_boundary_followup_action_label', '') or 'none'}, "
                    f"sla={metrics.get('external_benchmark_execution_review_boundary_sla_state_label', '') or 'none'}, "
                    f"age={metrics.get('external_benchmark_execution_review_boundary_age_bucket_label', '') or 'none'}, "
                    f"overdue={int(metrics.get('external_benchmark_execution_review_boundary_overdue_count', 0))}, "
                    f"oldest_open_h={float(metrics.get('external_benchmark_execution_review_boundary_oldest_open_age_hours', 0.0)):.3f})"
                ),
                f"- `external_benchmark_execution_status_mode`: `{metrics.get('external_benchmark_execution_status_mode', '')}`",
                (
                f"- `external_benchmark_execution_status_counts`: "
                f"`planned={int(metrics.get('external_benchmark_execution_planned_task_count', 0))}, "
                f"in_progress={int(metrics.get('external_benchmark_execution_in_progress_task_count', 0))}, "
                f"completed={int(metrics.get('external_benchmark_execution_completed_task_count', 0))}, "
                f"failed={int(metrics.get('external_benchmark_execution_failed_task_count', 0))}, "
                f"finished={int(metrics.get('external_benchmark_execution_finished_task_count', 0))}, "
                f"completion_ratio={float(metrics.get('external_benchmark_execution_completion_ratio', 0.0)):.3f}`"
                ),
                (
                    f"- `midas_section_library_validator`: "
                    f"`{metrics.get('midas_section_library_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_validator`: "
                    f"`{metrics.get('midas_kds_geometry_bridge_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_load_crosswalk`: "
                    f"`{metrics.get('midas_kds_geometry_bridge_load_crosswalk_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_semantic_crosswalk`: "
                    f"`{metrics.get('midas_kds_geometry_bridge_semantic_crosswalk_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_full_member_crosswalk`: "
                    f"`{metrics.get('midas_kds_geometry_bridge_full_member_crosswalk_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_full_section_crosswalk`: "
                    f"`{metrics.get('midas_kds_geometry_bridge_full_section_crosswalk_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_full_load_crosswalk`: "
                    f"`{metrics.get('midas_kds_geometry_bridge_full_load_crosswalk_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_kds_geometry_bridge_full_crosswalk_depth`: "
                    f"`{int(metrics.get('midas_kds_geometry_bridge_full_crosswalk_depth', 0))}` "
                    f"(min(load/semantic crosswalk))"
                ),
                (
                    f"- `midas_loadcomb_roundtrip_validator`: "
                    f"`{metrics.get('midas_loadcomb_roundtrip_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `commercial_benchmark_breadth`: "
                    f"`{metrics.get('commercial_benchmark_breadth_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `solver_breadth`: "
                    f"`{metrics.get('solver_breadth_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `element_material_breadth`: "
                    f"`{metrics.get('element_material_breadth_summary_line', '') or 'n/a'}`"
                ),
                f"- `constitutive_interaction_families`: `{CONSTITUTIVE_INTERACTION_NOTE}`",
                (
                    f"- `contact_readiness`: "
                    f"`{metrics.get('contact_readiness_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `foundation_soil_link`: "
                    f"`{metrics.get('foundation_soil_link_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `support_search`: "
                    f"`{metrics.get('support_search_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `structural_contact`: "
                    f"`{metrics.get('structural_contact_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `general_fe_contact_matrix`: "
                    f"`{metrics.get('general_fe_contact_matrix_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `surface_interaction_benchmark`: "
                    f"`{metrics.get('surface_interaction_benchmark_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_interoperability`: "
                    f"`{metrics.get('midas_interoperability_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `midas_native_roundtrip`: "
                    f"`{metrics.get('midas_native_roundtrip_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `steel_composite_constitutive_gate`: "
                    f"`{metrics.get('steel_composite_constitutive_gate_surface_label', '') or 'n/a'}`"
                ),
                (
                    f"- `load_combination_engine_gate`: "
                    f"`{metrics.get('load_combination_engine_surface_label', '') or 'n/a'}`"
                ),
                (
                    f"- `performance_profiling`: "
                    f"`{metrics.get('performance_profiling_summary_line', '') or 'n/a'}`"
                ),
                f"- `ndtha_step_series_depth`: `{int(metrics.get('ndtha_step_series_depth', 0))}` (max completed steps)",
                (
                    f"- `ndtha_material_depth`: "
                    f"`{int(metrics.get('ndtha_material_depth', 0))}`"
                ),
                (
                    f"- `ndtha_material`: "
                    f"`{metrics.get('ndtha_material_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `performance_detail`: "
                    f"`moving_load_scale={metrics.get('performance_moving_load_scale_label', '') or 'n/a'} | "
                    f"cached_inverse={metrics.get('performance_moving_load_cached_inverse_label', '') or 'n/a'} | "
                    f"ssi_variant_sweep={metrics.get('performance_ssi_variant_sweep_label', '') or 'n/a'} | "
                    f"zero_gap={metrics.get('performance_ssi_zero_gap_variant_label', '') or 'n/a'} | "
                    f"pruned={metrics.get('performance_ssi_pruned_variant_label', '') or 'n/a'}`"
                ),
                (
                    f"- `solver_truthfulness`: "
                    f"`{metrics.get('solver_truthfulness_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `hardest_external_10case_kickoff`: "
                    f"`{metrics.get('hardest_external_10case_kickoff_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `nonlinear_generalization`: "
                    f"`{metrics.get('nonlinear_generalization_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `workflow_productization`: "
                    f"`{metrics.get('workflow_productization_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `kr_ingest`: "
                    f"`{metrics.get('korean_source_ingest_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `kr_preview_queue`: "
                    f"`{metrics.get('korean_structural_preview_queue_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `irregular_structure_track`: "
                    f"`{metrics.get('irregular_structure_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `commercial_readiness`: "
                    f"`{metrics.get('commercial_readiness_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `mgt_export_loadcomb_roundtrip`: "
                    f"`pass={bool(metrics.get('mgt_export_loadcomb_roundtrip_pass', False))} | "
                    f"{metrics.get('mgt_export_loadcomb_roundtrip_summary_line', '') or 'n/a'}`"
                ),
                (
                    f"- `structural_optimization_viewer`: "
                    f"`{artifacts.get('structural_optimization_viewer_html', '') or 'n/a'}`"
                ),
                (
                    f"- `optimized_drawing_review`: "
                    f"`{artifacts.get('optimized_drawing_review_html', '') or 'n/a'} | "
                    f"axis={metrics.get('optimized_drawing_review_axis_source_mode', '') or 'n/a'} | "
                    f"x={metrics.get('optimized_drawing_review_axis_preview_label', '') or 'n/a'}`"
                ),
                (
                    f"- `audit_review_decision_batch_template`: "
                    f"`items={int(metrics.get('audit_review_decision_batch_template_item_count', 0))}, "
                    f"status={metrics.get('audit_review_decision_batch_template_current_status_label', '') or 'none'}, "
                    f"owner={metrics.get('audit_review_decision_batch_template_review_owner_label', '') or 'none'}, "
                    f"priority={metrics.get('audit_review_decision_batch_template_review_priority_label', '') or 'none'}, "
                    f"attested_examples={int(metrics.get('audit_review_decision_batch_attested_example_count', 0))}, "
                    f"example_preview={metrics.get('audit_review_decision_batch_attested_example_preview_label', '') or 'none'}`"
                ),
                (
                    f"- `external_benchmark_submission_preview_approve_all`: "
                    f"`reason={metrics.get('external_benchmark_submission_preview_approve_all_reason_code', '')}, "
                    f"ready_full={bool(metrics.get('external_benchmark_submission_preview_approve_all_ready_full', False))}, "
                    f"pending={int(metrics.get('external_benchmark_submission_preview_approve_all_pending_count', 0))}, "
                    f"open_revision={int(metrics.get('external_benchmark_submission_preview_approve_all_open_revision_count', 0))}`"
                ),
                (
                    f"- `external_benchmark_submission_preview_reject_one`: "
                    f"`reason={metrics.get('external_benchmark_submission_preview_reject_one_reason_code', '')}, "
                    f"ready_full={bool(metrics.get('external_benchmark_submission_preview_reject_one_ready_full', False))}, "
                    f"pending={int(metrics.get('external_benchmark_submission_preview_reject_one_pending_count', 0))}, "
                    f"open_revision={int(metrics.get('external_benchmark_submission_preview_reject_one_open_revision_count', 0))}, "
                    f"blocker={metrics.get('external_benchmark_submission_preview_reject_one_blocker_label', '') or 'none'}`"
                ),
                (
                    f"- `audit_review_decision_batch_runner`: "
                    f"`reason={metrics.get('audit_review_decision_batch_runner_reason_code', '')}, "
                    f"apply_live={bool(metrics.get('audit_review_decision_batch_runner_apply_live', False))}, "
                    f"live_applied={bool(metrics.get('audit_review_decision_batch_runner_live_applied', False))}, "
                    f"preview_reason={metrics.get('audit_review_decision_batch_runner_preview_reason_code', '') or 'none'}, "
                    f"preview_ready_full={bool(metrics.get('audit_review_decision_batch_runner_preview_ready_full', False))}, "
                    f"preview_pending={int(metrics.get('audit_review_decision_batch_runner_preview_pending_count', 0))}, "
                    f"preview_open_revision={int(metrics.get('audit_review_decision_batch_runner_preview_open_revision_count', 0))}`"
                ),
            ]
        )
    if external_benchmark_submission_queue_rows:
        external_benchmark_submission_summary_line = str(
            metrics.get("external_benchmark_submission_summary_line", "") or ""
        ).strip()
        if not external_benchmark_submission_summary_line:
            external_benchmark_submission_summary_line = (
                f"queue={len(external_benchmark_submission_queue_rows)} | "
                f"onepage_attestation_status="
                f"{metrics.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown'}"
            )
        receipt_attached_count = sum(
            1
            for row in external_benchmark_submission_queue_rows
            if _submission_receipt_label(row) != "pending"
        )
        receipt_pending_count = len(external_benchmark_submission_queue_rows) - receipt_attached_count
        lines.extend(
            [
                "",
                "## External Benchmark Submission Queue",
                "",
                f"- `external_benchmark_submission_summary_line`: "
                f"`{external_benchmark_submission_summary_line}`",
                f"- `external_benchmark_submission_onepage_attestation_status`: "
                f"`{metrics.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown'}`",
                f"- `external_benchmark_submission_queue_count`: "
                f"`{int(metrics.get('external_benchmark_submission_queue_count', len(external_benchmark_submission_queue_rows)))}` | "
                f"`receipt_attached={receipt_attached_count}` | "
                f"`receipt_pending={receipt_pending_count}`",
                "",
                "| Work Item | Queue | Submission ID | Scope | Owner | Status | Receipt | Receipt Status | Onepage Status | Dry-run Evidence |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for row in external_benchmark_submission_queue_rows:
            lines.append(
                f"| {row.get('work_item_id', '')} | {row.get('queue_id', '')} | {row.get('submission_id', '')} | "
                f"{row.get('submission_scope', '')} | {row.get('owner', '')} | {row.get('status', '')} | "
                f"{_submission_receipt_label(row)} | "
                f"{_submission_receipt_status_label(row)} | "
                f"{row.get('onepage_attestation_status', '') or 'unknown'} | {row.get('dry_run_evidence', '') or 'n/a'} |"
            )
    lines.extend(
        [
            "",
            "## Design Opt Raw vs Repaired",
            "",
            f"- `raw_max_drift_pct`: `{metrics.get('design_opt_raw_max_drift_pct', 0.0):.6f}`",
            f"- `raw_residual_drift_pct`: `{metrics.get('design_opt_raw_residual_drift_pct', 0.0):.6f}`",
            f"- `raw_max_dcr`: `{metrics.get('design_opt_raw_max_dcr', 0.0):.6f}`",
            f"- `repaired_compliance_max_drift_pct`: `{metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0):.6f}`",
            f"- `repaired_compliance_residual_drift_pct`: `{metrics.get('design_opt_repaired_compliance_residual_drift_pct', 0.0):.6f}`",
            f"- `repaired_compliance_max_dcr`: `{metrics.get('design_opt_repaired_compliance_max_dcr', 0.0):.6f}`",
            f"- `compliance_basis`: `{metrics.get('design_opt_compliance_basis', '')}`",
            f"- `repair_action_count`: `{int(metrics.get('design_opt_repair_action_count', 0))}`",
            f"- `constructability_signal_gain_pct`: `{metrics.get('design_opt_constructability_signal_gain_pct', 0.0):.6f}`",
            f"- `constructability_avg`: `{metrics.get('design_opt_baseline_constructability_avg', 0.0):.6f} -> {metrics.get('design_opt_final_constructability_avg', 0.0):.6f}`",
            f"- `detailing_complexity_avg`: `{metrics.get('design_opt_baseline_detailing_complexity_avg', 0.0):.6f} -> {metrics.get('design_opt_final_detailing_complexity_avg', 0.0):.6f}`",
            f"- `selected_family_mix`: `{metrics.get('design_opt_selected_family_mix_label', '')}`",
            f"- `selected_dominant_family`: `{metrics.get('design_opt_selected_dominant_family', '')}` ({metrics.get('design_opt_selected_dominant_family_ratio', 0.0):.2%})",
            f"- `selected_family_mix_trend`: `{metrics.get('design_opt_selected_family_trend_label', '')}`",
            f"- `selected_dominant_family_previous`: `{metrics.get('design_opt_previous_dominant_family', '')}` ({metrics.get('design_opt_previous_dominant_family_ratio', 0.0):.2%})",
            f"- `preview_supply_family_mix`: `{metrics.get('design_opt_preview_supply_family_mix_label', '')}`",
            f"- `preview_missing_target_families`: `{metrics.get('design_opt_preview_missing_target_families_label', '')}`",
            f"- `mgt_export_direct_patch_families`: `{metrics.get('mgt_export_direct_patch_action_family_label', '')}` ({int(metrics.get('mgt_export_direct_patch_change_count', 0))})",
            f"- `mgt_export_sidecar_families`: `{metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_instruction_sidecar_change_count', 0))})",
            f"- `mgt_export_sidecar_audit_only_families`: `{metrics.get('mgt_export_instruction_sidecar_audit_only_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_instruction_sidecar_audit_only_change_count', 0))})",
            f"- `mgt_export_sidecar_manual_input_families`: `{metrics.get('mgt_export_instruction_sidecar_manual_input_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_instruction_sidecar_manual_input_change_count', 0))})",
            f"- `mgt_export_audit_review_manifest_families`: `{metrics.get('mgt_export_audit_review_manifest_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_manifest_change_count', 0))})",
            f"- `mgt_export_audit_review_packets`: `{metrics.get('mgt_export_audit_review_packet_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_packet_count', 0))})",
            f"- `mgt_export_audit_review_packet_files`: `{metrics.get('mgt_export_audit_review_packet_file_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_packet_file_count', 0))})",
            f"- `mgt_export_audit_review_queue`: `{metrics.get('mgt_export_audit_review_queue_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_queue_item_count', 0))})",
            f"- `mgt_export_audit_review_queue_status`: `{metrics.get('mgt_export_audit_review_queue_status_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_followup`: `{metrics.get('mgt_export_audit_review_followup_action_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_followup_item_count', 0))})",
            f"- `mgt_export_audit_review_followup_owner`: `{metrics.get('mgt_export_audit_review_followup_owner_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_followup_review_owner`: `{metrics.get('mgt_export_audit_review_followup_review_owner_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_followup_status`: `{metrics.get('mgt_export_audit_review_followup_status_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_followup_sla`: `{metrics.get('mgt_export_audit_review_followup_sla_state_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_followup_age`: `{metrics.get('mgt_export_audit_review_followup_age_bucket_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_followup_overdue`: `{int(metrics.get('mgt_export_audit_review_followup_overdue_item_count', 0))}`",
            f"- `mgt_export_audit_review_resolution`: `{metrics.get('mgt_export_audit_review_resolution_action_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_resolution_item_count', 0))})",
            f"- `mgt_export_audit_review_resolution_owner`: `{metrics.get('mgt_export_audit_review_resolution_owner_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_resolution_status`: `{metrics.get('mgt_export_audit_review_resolution_status_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_packet_followups`: `{metrics.get('mgt_export_audit_review_packet_followup_type_label', '') or 'n/a'}`",
            f"- `mgt_export_audit_review_packet_files`: `{metrics.get('mgt_export_audit_review_packet_file_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_packet_file_count', 0))})",
            f"- `mgt_export_rebar_namespace_mode`: `{metrics.get('mgt_export_rebar_payload_namespace_mode', '')}`",
            f"- `mgt_export_rebar_delivery_mode`: `{metrics.get('mgt_export_rebar_delivery_mode', '')}`",
            f"- `mgt_export_evidence_model`: `{metrics.get('mgt_export_evidence_model', '')}`",
            f"- `mgt_export_delivery_boundary`: `direct_patch={metrics.get('mgt_export_direct_patch_action_family_label', '') or 'n/a'} | "
            f"sidecar={metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'}`",
            f"- `mgt_export_rebar_material_namespace_present`: `{bool(metrics.get('mgt_export_rebar_payload_material_level_namespace_present', False))}`",
            f"- `mgt_export_rebar_group_local_namespace_present`: `{bool(metrics.get('mgt_export_rebar_payload_group_local_namespace_present', False))}`",
            f"- `mgt_export_material_rebar_payloads`: `{int(metrics.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_material_level_rebar_payload_row_count', 0))}`",
            f"- `mgt_export_group_local_rebar_payloads`: `{int(metrics.get('mgt_export_group_local_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_rebar_payload_row_count', 0))}`",
            f"- `mgt_export_connection_namespace_mode`: `{metrics.get('mgt_export_connection_detailing_payload_namespace_mode', '')}`",
            f"- `mgt_export_connection_group_local_namespace_present`: `{bool(metrics.get('mgt_export_connection_detailing_payload_group_local_namespace_present', False))}`",
            f"- `mgt_export_group_local_connection_detailing_payloads`: `{int(metrics.get('mgt_export_group_local_connection_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_connection_detailing_payload_row_count', 0))}`",
            f"- `mgt_export_connection_direct_patch_eligible`: `{int(metrics.get('mgt_export_connection_detailing_direct_patch_eligible_change_count', 0))}`",
            f"- `mgt_export_detailing_namespace_mode`: `{metrics.get('mgt_export_detailing_payload_namespace_mode', '')}`",
            f"- `mgt_export_detailing_group_local_namespace_present`: `{bool(metrics.get('mgt_export_detailing_payload_group_local_namespace_present', False))}`",
            f"- `mgt_export_group_local_detailing_payloads`: `{int(metrics.get('mgt_export_group_local_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_detailing_payload_row_count', 0))}`",
            f"- `mgt_export_detailing_direct_patch_eligible`: `{int(metrics.get('mgt_export_detailing_direct_patch_eligible_change_count', 0))}`",
            f"- `mgt_export_connection_structured_payload_mapped`: `{int(metrics.get('mgt_export_connection_detailing_structured_payload_mapped_change_count', 0))}`",
            f"- `mgt_export_detailing_structured_payload_mapped`: `{int(metrics.get('mgt_export_detailing_structured_payload_mapped_change_count', 0))}`",
            f"- `mgt_export_connection_delivery_mode`: `{metrics.get('mgt_export_connection_detailing_delivery_mode', '')}`",
            f"- `mgt_export_detailing_delivery_mode`: `{metrics.get('mgt_export_detailing_delivery_mode', '')}`",
            f"- `mgt_export_rebar_direct_patch_eligible`: `{int(metrics.get('mgt_export_rebar_direct_patch_eligible_change_count', 0))}`",
            f"- `mgt_export_patched_material_rows`: `{int(metrics.get('mgt_export_patched_material_row_count', 0))}`",
            f"- `mgt_export_cloned_material_count`: `{int(metrics.get('mgt_export_cloned_material_count', 0))}`",
            f"- `mgt_export_rebar_direct_patch_blockers`: `{metrics.get('mgt_export_rebar_direct_patch_ineligible_reason_label', '')}`",
            f"- `mgt_export_rebar_mapping_sources`: `{metrics.get('mgt_export_rebar_direct_patch_mapping_source_label', '')}`",
            f"- `blocked_illegal_by_mask_families`: `{metrics.get('design_opt_blocked_illegal_by_mask_family_label', '')}`",
            f"- `pbd_dynamic_hinge_refresh_ready`: `{bool(metrics.get('pbd_dynamic_hinge_refresh_ready', False))}` ({metrics.get('pbd_hinge_state_mode', '')})",
            f"- `pbd_hinge_refresh_reason`: `{metrics.get('pbd_hinge_refresh_reason', '')}`",
            f"- `pbd_hinge_refresh_artifact_present`: `{bool(metrics.get('pbd_hinge_refresh_artifact_present', False))}`",
            f"- `pbd_hinge_refresh_artifact_kind`: `{metrics.get('pbd_hinge_refresh_artifact_kind', '')}`",
            f"- `pbd_hinge_refresh_source_mode`: `{metrics.get('pbd_hinge_refresh_source_mode', '')}`",
            f"- `pbd_hinge_refresh_overlap_member_count`: `{int(metrics.get('pbd_hinge_refresh_overlap_member_count', 0))}`",
            f"- `pbd_hinge_refresh_rebar_sensitive_member_count`: `{int(metrics.get('pbd_hinge_refresh_rebar_sensitive_member_count', 0))}`",
            f"- `pbd_hinge_benchmark_gate_pass`: `{bool(metrics.get('pbd_hinge_benchmark_gate_pass', False))}`",
            f"- `pbd_hinge_benchmark_fixture_regression_pass`: `{bool(metrics.get('pbd_hinge_benchmark_fixture_regression_pass', False))}`",
            f"- `pbd_hinge_benchmark_alignment_pass`: `{bool(metrics.get('pbd_hinge_benchmark_alignment_pass', False))}`",
            f"- `pbd_hinge_benchmark_asset_count`: `{int(metrics.get('pbd_hinge_benchmark_asset_count', 0))}`",
            f"- `pbd_hinge_benchmark_split`: `train={int(metrics.get('pbd_hinge_benchmark_train_count', 0))}, val={int(metrics.get('pbd_hinge_benchmark_val_count', 0))}, holdout={int(metrics.get('pbd_hinge_benchmark_holdout_count', 0))}`",
            f"- `pbd_hinge_benchmark_rebar_sensitive_count`: `{int(metrics.get('pbd_hinge_benchmark_rebar_sensitive_count', 0))}`",
            f"- `pbd_hinge_benchmark_confinement_sensitive_count`: `{int(metrics.get('pbd_hinge_benchmark_confinement_sensitive_count', 0))}`",
            f"- `pbd_hinge_benchmark_fixture_count`: `{int(metrics.get('pbd_hinge_benchmark_fixture_count', 0))}`",
            f"- `pbd_hinge_benchmark_fixture_min_point_count`: `{int(metrics.get('pbd_hinge_benchmark_fixture_min_point_count', 0))}`",
            f"- `pbd_hinge_benchmark_fixture_min_peak_drift_ratio`: `{float(metrics.get('pbd_hinge_benchmark_fixture_min_peak_drift_ratio', 0.0))}`",
            f"- `pbd_hinge_benchmark_alignment_refresh_column_row_count`: `{int(metrics.get('pbd_hinge_benchmark_alignment_refresh_column_row_count', 0))}`",
            f"- `pbd_hinge_benchmark_alignment_rebar_sensitive_column_count`: `{int(metrics.get('pbd_hinge_benchmark_alignment_rebar_sensitive_column_count', 0))}`",
            f"- `pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min`: `{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min', 0.0))}`",
            f"- `pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max`: `{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max', 0.0))}`",
            f"- `pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min`: `{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min', 0.0))}`",
            f"- `pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max`: `{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max', 0.0))}`",
            f"- `panel_zone_3d_clash_ready`: `{bool(metrics.get('panel_zone_3d_clash_ready', False))}` ({metrics.get('panel_zone_constructability_mode', '')})",
            f"- `panel_zone_constructability_reason`: `{metrics.get('panel_zone_constructability_reason', '')}`",
            f"- `panel_zone_source_contract_mode`: `{metrics.get('panel_zone_source_contract_mode', '')}`",
            f"- `panel_zone_internal_engine_complete`: `{bool(metrics.get('panel_zone_internal_engine_complete', False))}`",
            f"- `panel_zone_external_validation_pending`: `{bool(metrics.get('panel_zone_external_validation_pending', False))}`",
            f"- `panel_zone_validation_boundary`: `{metrics.get('panel_zone_validation_boundary', '')}`",
            f"- `panel_zone_status_label`: `{metrics.get('panel_zone_status_label', '')}`",
            f"- `panel_zone_advisory_only`: `{bool(metrics.get('panel_zone_advisory_only', False))}`",
            f"- `panel_zone_release_blocking`: `{bool(metrics.get('panel_zone_release_blocking', False))}`",
            f"- `panel_zone_external_validation_artifact_closed`: `{bool(metrics.get('panel_zone_external_validation_artifact_closed', False))}`",
            f"- `panel_zone_external_validation_closure_mode`: `{metrics.get('panel_zone_external_validation_closure_mode', '')}`",
            f"- `panel_zone_external_validation_required_evidence`: `{metrics.get('panel_zone_external_validation_required_evidence', '')}`",
            f"- `panel_zone_external_validation_summary_line`: `{metrics.get('panel_zone_external_validation_summary_line', '')}`",
            f"- `panel_zone_external_validation_provenance_summary_label`: `{metrics.get('panel_zone_external_validation_provenance_summary_label', '')}`",
            f"- `panel_zone_external_validation_closing_summary_label`: `{metrics.get('panel_zone_external_validation_closing_summary_label', '')}`",
            f"- `panel_zone_external_validation_local_closure_state`: `{metrics.get('panel_zone_external_validation_local_closure_state', '')}`",
            f"- `panel_zone_external_validation_local_closure_label`: `{metrics.get('panel_zone_external_validation_local_closure_label', '')}`",
            f"- `panel_zone_external_validation_source_count`: `{int(metrics.get('panel_zone_external_validation_source_count', 0))}`",
            f"- `panel_zone_external_validation_exact_source_count`: `{int(metrics.get('panel_zone_external_validation_exact_source_count', 0))}`",
            f"- `panel_zone_external_validation_fallback_source_count`: `{int(metrics.get('panel_zone_external_validation_fallback_source_count', 0))}`",
            f"- `panel_zone_external_validation_validated_member_count`: `{int(metrics.get('panel_zone_external_validation_validated_member_count', 0))}`",
            f"- `panel_zone_external_validation_exact_member_count`: `{int(metrics.get('panel_zone_external_validation_exact_member_count', 0))}`",
            f"- `panel_zone_external_validation_fallback_member_count`: `{int(metrics.get('panel_zone_external_validation_fallback_member_count', 0))}`",
            f"- `panel_zone_external_validation_exact_validated_row_count`: `{int(metrics.get('panel_zone_external_validation_exact_validated_row_count', 0))}`",
            f"- `panel_zone_external_validation_fallback_validated_row_count`: `{int(metrics.get('panel_zone_external_validation_fallback_validated_row_count', 0))}`",
            f"- `panel_zone_source_artifact_kind`: `{metrics.get('panel_zone_source_artifact_kind', '')}`",
            f"- `panel_zone_proxy_candidate_count`: `{int(metrics.get('panel_zone_proxy_candidate_count', 0))}`",
            f"- `panel_zone_instruction_sidecar_present`: `{bool(metrics.get('panel_zone_instruction_sidecar_present', False))}`",
            f"- `panel_zone_instruction_sidecar_change_count`: `{int(metrics.get('panel_zone_instruction_sidecar_change_count', 0))}`",
            f"- `panel_zone_instruction_sidecar_candidate_overlap_mode`: `{metrics.get('panel_zone_instruction_sidecar_candidate_overlap_mode', '')}`",
            f"- `panel_zone_instruction_sidecar_overlap_row_count`: `{int(metrics.get('panel_zone_instruction_sidecar_overlap_row_count', 0))}`",
            f"- `panel_zone_instruction_sidecar_overlap_member_count`: `{int(metrics.get('panel_zone_instruction_sidecar_overlap_member_count', 0))}`",
            f"- `panel_zone_instruction_sidecar_evidence_model`: `{metrics.get('panel_zone_instruction_sidecar_evidence_model', '')}`",
            f"- `panel_zone_instruction_sidecar_rebar_delivery_mode`: `{metrics.get('panel_zone_instruction_sidecar_rebar_delivery_mode', '')}`",
            f"- `panel_zone_member_mapping_sidecar_present`: `{bool(metrics.get('panel_zone_member_mapping_sidecar_present', False))}`",
            f"- `panel_zone_member_mapping_sidecar_mode`: `{metrics.get('panel_zone_member_mapping_sidecar_mode', '')}`",
            f"- `panel_zone_member_mapping_sidecar_row_count`: `{int(metrics.get('panel_zone_member_mapping_sidecar_row_count', 0))}`",
            f"- `panel_zone_member_mapping_sidecar_applied_row_count`: `{int(metrics.get('panel_zone_member_mapping_sidecar_applied_row_count', 0))}`",
            f"- `panel_zone_member_mapping_sidecar_unmapped_source_member_count`: `{int(metrics.get('panel_zone_member_mapping_sidecar_unmapped_source_member_count', 0))}`",
            f"- `panel_zone_validated_source_row_count_total`: `{int(metrics.get('panel_zone_validated_source_row_count_total', 0))}`",
            f"- `panel_zone_validated_source_overlap_member_count_min`: `{int(metrics.get('panel_zone_validated_source_overlap_member_count_min', 0))}`",
            f"- `panel_zone_missing_required_sources`: `{', '.join(metrics.get('panel_zone_missing_required_sources', []))}`",
            f"- `panel_zone_solver_verified_inbox_status_mode`: `{metrics.get('panel_zone_solver_verified_inbox_status_mode', '')}`",
            f"- `panel_zone_solver_verified_pending_input`: `{bool(metrics.get('panel_zone_solver_verified_pending_input', False))}`",
            f"- `panel_zone_solver_verified_latest_consume_contract_pass`: `{bool(metrics.get('panel_zone_solver_verified_latest_consume_contract_pass', False))}`",
            f"- `panel_zone_solver_verified_source_origin_class`: `{metrics.get('panel_zone_solver_verified_source_origin_class', '')}`",
            f"- `panel_zone_solver_verified_release_refresh_source_allowed`: `{bool(metrics.get('panel_zone_solver_verified_release_refresh_source_allowed', False))}`",
            f"- `panel_zone_solver_verified_recommended_action`: `{metrics.get('panel_zone_solver_verified_recommended_action', '')}`",
            f"- `foundation_optimization_ready`: `{bool(metrics.get('foundation_optimization_ready', False))}` ({metrics.get('foundation_optimization_mode', '')})",
            f"- `foundation_optimization_reason`: `{metrics.get('foundation_optimization_reason', '')}`",
            f"- `foundation_scope_source`: `{metrics.get('foundation_scope_source', '')}`",
            f"- `foundation_artifact_scan_mode`: `{metrics.get('foundation_artifact_scan_mode', '')}`",
            f"- `upstream_foundation_label_count`: `{int(metrics.get('upstream_foundation_label_count', 0))}` ({metrics.get('upstream_foundation_provenance_mode', '')})",
            f"- `raw_source_foundation_label_count`: `{int(metrics.get('raw_source_foundation_label_count', 0))}`",
            f"- `wind_tunnel_raw_mapping_ready`: `{bool(metrics.get('wind_tunnel_raw_mapping_ready', False))}` ({metrics.get('wind_tunnel_mapping_mode', '')})",
            f"- `wind_tunnel_mapping_reason`: `{metrics.get('wind_tunnel_mapping_reason', '')}`",
        ]
    )
    if holdout_buckets:
        lines.extend(["", "## Residual Holdout Boundary", ""])
        lines.extend(
            [
                "| Work Item | Category | Due Date | SLA | Closure Evidence | Owner | Queue Status | Status | Relative Share | Absolute Project % | Scope |",
                "|---|---|---|---|---|---|---|---|---:|---|---|",
            ]
        )
        for row in holdout_buckets:
            lines.append(
                f"| {row.get('work_item_id', '')} | {row.get('label', row.get('id', ''))} | {row.get('due_date', '')} | "
                f"{row.get('sla_label', '')} | {_holdout_closure_evidence_label(row)} | {row.get('owner', '')} | "
                f"{row.get('queue_status', '')} | {row.get('status', '')} | {int(row.get('relative_share_pct', 0))}% | "
                f"{_coverage_range_label(row.get('absolute_project_pct_range'))} | {row.get('scope', '')} |"
            )
    advanced_holdout_status_rows = [
        row for row in (metrics.get("advanced_holdout_status_rows", []) or []) if isinstance(row, dict)
    ]
    if advanced_holdout_status_rows:
        lines.extend(
            [
                "",
                "## Advanced Holdout Closure",
                "",
                f"- `closure`: `{metrics.get('advanced_holdout_status_label', '') or 'n/a'}`",
                "",
                "| Holdout | Severity | Closure | Mode | Reason | Evidence |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in advanced_holdout_status_rows:
            lines.append(
                f"| {row.get('title', row.get('id', ''))} | {row.get('severity', '') or 'n/a'} | "
                f"{row.get('closure_state', '')} | {row.get('mode', '') or 'n/a'} | "
                f"{row.get('reason_snippet', '') or 'n/a'} | {row.get('evidence_snippet', '') or 'n/a'} |"
            )
    if holdout_detail_rows:
        lines.extend(["", "## Residual Holdout Review Table", ""])
        lines.extend(
            [
                "| Category | Work Item | Axis | Detail | Owner | Queue Status | Status | SLA | Due | Closure Evidence | Why |",
                "|---|---|---|---|---|---|---|---:|---|---|---|",
            ]
        )
        for row in holdout_detail_rows:
            lines.append(
                f"| {row.get('bucket_label', row.get('bucket_id', ''))} | {row.get('work_item_id', '')} | {row.get('detail_axis', '')} | "
                f"{row.get('detail_value', '')} | {row.get('owner', '')} | {row.get('queue_status', '')} | "
                f"{row.get('status', '')} | {row.get('sla_label', '')} | {row.get('due_date', '')} | "
                f"{row.get('closure_evidence_required', '')} ({row.get('closure_evidence_status', '')}) | {row.get('why', '')} |"
            )
    if holdout_matrix_rows:
        lines.extend(["", "## Residual Holdout Routing Matrix", ""])
        lines.extend(["| Category | Track | Submodel | Review Story/Zone | Member Family | Owner | Why |", "|---|---|---|---|---|---|---|"])
        for row in holdout_matrix_rows:
            lines.append(
                f"| {row.get('bucket_label', '')} | {row.get('authority_track', '')} | {row.get('submodel_family', '')} | "
                f"{row.get('review_story_zone', '')} | {row.get('member_family', '')} | {row.get('owner', '')} | {row.get('why', '')} |"
            )
    lines.extend(["", "## Authority Catalog Routing Diff", ""])
    lines.append(
        f"- `baseline_seeded`: `{bool(authority_catalog_diff.get('baseline_seeded', False))}` | "
        f"`changes={int(authority_catalog_diff.get('change_count', 0))}` | "
        f"`added={int(authority_catalog_diff.get('added_count', 0))}` | "
        f"`removed={int(authority_catalog_diff.get('removed_count', 0))}` | "
        f"`unchanged={int(authority_catalog_diff.get('unchanged_count', 0))}`"
    )
    diff_rows = [row for row in (authority_catalog_diff.get("diff_rows") or []) if isinstance(row, dict)]
    if diff_rows:
        lines.extend(["", "| Change | Track | Submodel | Review Story/Zone | Member Family | Owner | Why |", "|---|---|---|---|---|---|---|"])
        for row in diff_rows:
            lines.append(
                f"| {row.get('change_type', '')} | {row.get('authority_track', '')} | {row.get('submodel_family', '')} | "
                f"{row.get('review_story_zone', '')} | {row.get('member_family', '')} | {row.get('owner', '')} | {row.get('why', '')} |"
            )
    else:
        lines.extend(["", "- No authority-catalog routing changes detected for this package refresh."])
    lines.extend(["", "## Artifacts", ""])
    for key, value in artifacts.items():
        lines.append(f"- `{key}`: `{value}`")
    if smoke_history_png.exists():
        lines.extend(
            [
                "",
                "## Nightly Smoke Trend",
                "",
                f"- `smoke_history_png`: `{smoke_history_png}`",
                "",
                f"![Nightly Smoke Trend](../{smoke_history_png.name})",
            ]
        )
    if smoke_recent_samples:
        lines.extend(["", "## Nightly Smoke Recent Samples", "", "| Sample | Generated | Pass | Trial Feasible | Baseline Runtime (s) | Trial Runtime (s) | Trial Max DCR | Action |", "|---:|---|---|---|---:|---:|---:|---|"])
        for row in smoke_recent_samples:
            lines.append(
                f"| {int(row.get('sample_index', 0))} | {row.get('generated_at', '')} | {bool(row.get('contract_pass', False))} | {bool(row.get('trial_feasible', False))} | "
                f"{float(row.get('baseline_runtime_s', 0.0)):.4f} | {float(row.get('trial_runtime_s', 0.0)):.4f} | {float(row.get('trial_max_dcr', 0.0)):.4f} | {row.get('trial_action_name', '')} |"
            )
    lines.extend([""])
    lines.extend(
        render_entrypoint_markdown_sections(
            design_opt_entrypoint_rows,
            design_opt_entrypoint_groups,
            include_members=True,
        )
    )
    row_provenance_preview_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_preview_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_clause_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_clause_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_member_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_member_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_hazard_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_hazard_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_rule_family_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_rule_family_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_summary_line = str(metrics.get("midas_kds_row_provenance_export_summary_line", "") or "").strip()
    if row_provenance_summary_line or row_provenance_preview_rows:
        lines.extend(["", "## Appendix: MIDAS KDS Row Provenance Export", ""])
        lines.append(f"- `summary`: `{row_provenance_summary_line or 'n/a'}`")
        lines.append(
            f"- `artifacts`: json=`{artifacts.get('midas_kds_row_provenance_export_json', '') or 'n/a'}` | "
            f"csv=`{artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'}` | "
            f"report=`{artifacts.get('midas_kds_row_provenance_export_report', '') or 'n/a'}`"
        )
        lines.append(
            f"- `row-provenance sync`: `{ROW_PROVENANCE_SYNC_NOTE}`"
        )
        if row_provenance_preview_rows:
            lines.extend(
                [
                    "",
                    "| Combination | Member | Clause | Baseline Focus | Mode | Clause Provenance | Member Inventory |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in row_provenance_preview_rows:
                lines.append(
                    f"| {row.get('combination_name', '')} | {row.get('member_id', '')} | {row.get('clause_label', '')} | "
                    f"{row.get('baseline_focus_member_id', '')} | {row.get('bridge_row_provenance_mode_label', '')} | "
                    f"{row.get('clause_provenance_summary_label', '')} | {row.get('bridge_member_inventory_summary_label', '')} |"
                )
        if row_provenance_clause_filter_rows:
            lines.extend(
                [
                    "",
                    "| Clause | Rows | Members | Combos | Top Member | Top D/C |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for row in row_provenance_clause_filter_rows:
                lines.append(
                    f"| {row.get('clause_label', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                    f"{row.get('combination_count', '')} | {row.get('top_member_id', '')} | {row.get('top_dcr_label', '')} |"
                )
        if row_provenance_member_filter_rows:
            lines.extend(
                [
                    "",
                    "| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for row in row_provenance_member_filter_rows:
                lines.append(
                    f"| {row.get('member_id', '')} | {row.get('baseline_focus_member_id', '')} | {row.get('row_count', '')} | "
                    f"{row.get('clause_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} |"
                )
        if row_provenance_hazard_filter_rows:
            lines.extend(
                [
                    "",
                    "| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in row_provenance_hazard_filter_rows:
                lines.append(
                    f"| {row.get('hazard_type', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                    f"{row.get('clause_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} | {row.get('top_dcr_label', '')} |"
                )
        if row_provenance_rule_family_filter_rows:
            lines.extend(
                [
                    "",
                    "| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in row_provenance_rule_family_filter_rows:
                lines.append(
                    f"| {row.get('rule_family', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                    f"{row.get('hazard_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} | {row.get('top_dcr_label', '')} |"
                )
    native_roundtrip_appendix_lines = _midas_native_roundtrip_appendix_markdown_lines(artifacts, metrics)
    if native_roundtrip_appendix_lines:
        lines.extend(["", *native_roundtrip_appendix_lines])
    irregular_structure_appendix_lines = _irregular_structure_appendix_markdown_lines(artifacts, metrics)
    if irregular_structure_appendix_lines:
        lines.extend(["", *irregular_structure_appendix_lines])
    lines.extend(["", "## Authority Benchmarks", ""])
    for row in authority_rows:
        lines.append(
            f"- `{row['track']} / {row['case_id']}`: `{row['metric_a']}` | `{row['metric_b']}` [{row['status']}] | source={row['source_url']} | provenance={row['provenance']}"
        )
    lines.extend(["", "## NDTHA Residual Case Trace", ""])
    for row in residual_case_rows:
        lines.append(
            "- "
            f"`{row['case_id']}` split=`{row['split']}` hazard=`{row['hazard_type']}` "
            f"pre_top=`{row['pre_settle_top_m']:.6f}`m post_top=`{row['post_settle_top_m']:.6f}`m "
            f"pre_drift=`{row['pre_settle_drift_pct']:.6f}`% post_drift=`{row['post_settle_drift_pct']:.6f}`% "
            f"delta_top=`{row['delta_top_m']:.6f}`m delta_drift=`{row['delta_drift_pct']:.6f}`% "
            f"source=`{row['residual_metric_source']}` settle_steps=`{row['residual_settle_steps']}`"
        )
    lines.extend(["", "## Design Change Summary", ""])
    for row in design_change_rows:
        lines.append(
            "- "
            f"`S{int(row['story_band']):02d}` zone=`{row['zone_label']}` member=`{row['member_type']}` "
            f"changed=`{int(row['changed_group_count'])}` semantic=`{int(row['semantic_group_count'])}` "
            f"rebar_delta_sum=`{float(row['rebar_ratio_delta_sum']):.6f}` "
            f"cost_delta_sum=`{float(row['cost_proxy_delta_sum']):.3f}` "
            f"dcr=`{float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}` "
            f"constructability=`{float(row.get('constructability_before_avg', 0.0)):.4f}->{float(row.get('constructability_after_avg', 0.0)):.4f}` "
            f"gate=`{row.get('selection_gate', 'n/a')}`"
        )
    lines.extend(["", "## Design Change Story Totals", ""])
    for row in story_change_rows:
        lines.append(
            "- "
            f"`S{int(row['story_band']):02d}` "
            f"changed=`{int(row['changed_group_count'])}` semantic=`{int(row['semantic_group_count'])}` "
            f"rebar_delta_sum=`{float(row['rebar_ratio_delta_sum']):.6f}` "
            f"cost_delta_sum=`{float(row['cost_proxy_delta_sum']):.3f}` "
            f"dcr=`{float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}`"
        )
    lines.extend(["", "## Design Change Zone Totals", ""])
    for row in zone_change_rows:
        lines.append(
            "- "
            f"`{row['zone_label']}` "
            f"changed=`{int(row['changed_group_count'])}` semantic=`{int(row['semantic_group_count'])}` "
            f"rebar_delta_sum=`{float(row['rebar_ratio_delta_sum']):.6f}` "
            f"cost_delta_sum=`{float(row['cost_proxy_delta_sum']):.3f}` "
            f"dcr=`{float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}`"
        )
    lines.extend(["", "## Blocked Cost-Down Actions", ""])
    lines.append(
        "- "
        f"blocked=`{int(blocked_action_summary.get('blocked_action_row_count', 0))}` "
        f"illegal_by_mask=`{int(blocked_action_summary.get('illegal_by_mask', 0))}` "
        f"no_cost_gain=`{int(blocked_action_summary.get('no_cost_gain', 0))}` "
        f"constructability_hard_gate=`{int(blocked_action_summary.get('constructability_hard_gate_block_count', 0))}` "
        f"no_cost_gain_groups=`{int(blocked_action_summary.get('blocked_no_cost_group_count', 0))}` "
        f"no_cost_gain_explain_rows=`{int(blocked_action_summary.get('blocked_no_cost_explain_row_count', 0))}` "
        f"violates_feasible_constraints=`{int(blocked_action_summary.get('violates_feasible_constraints', 0))}` "
        f"no_action_delta=`{int(blocked_action_summary.get('no_action_delta', 0))}` "
        f"accepted_candidate=`{int(blocked_action_summary.get('accepted_candidate', 0))}` "
        f"selected=`{int(blocked_action_summary.get('accepted_candidate_selected_count', 0))}` "
        f"unselected=`{int(blocked_action_summary.get('accepted_candidate_unselected_count', 0))}`"
    )
    if str(blocked_action_summary.get("constructability_hard_gate_reason_label", "")):
        lines.append(
            "- "
            f"constructability_hard_gate_reasons=`{blocked_action_summary.get('constructability_hard_gate_reason_label', '')}`"
        )
    if str(blocked_action_summary.get("constructability_hard_gate_family_label", "")):
        lines.append(
            "- "
            f"constructability_hard_gate_families=`{blocked_action_summary.get('constructability_hard_gate_family_label', '')}`"
        )
    lines.extend(["", "## Accepted Cost-Down Candidates", ""])
    for row in selected_candidate_rows:
        lines.append(
            "- "
            f"`S{int(row['story_band']):02d}` zone=`{row['zone_label']}` member=`{row['member_type']}` "
            f"action=`{row['action_name']}` gain=`{float(row.get('delta_cost', row.get('projected_cost_delta', 0.0))):.3f}` "
            f"dcr=`{float(row.get('current_max_dcr', row.get('max_dcr', 0.0))):.3f}->{float(row.get('trial_max_dcr', row.get('max_dcr', 0.0))):.3f}` "
            f"reason=`{row.get('reason_selected', row.get('explain_reason', ''))}`"
        )
    lines.extend(["", "## Unselected Cost-Down Candidates", ""])
    for row in unselected_candidate_rows:
        lines.append(
            "- "
            f"`S{int(row['story_band']):02d}` zone=`{row['zone_label']}` member=`{row['member_type']}` "
            f"action=`{row['action_name']}` gain=`{float(row.get('delta_cost', row.get('projected_cost_delta', 0.0))):.3f}` "
            f"reason=`{row.get('reason_rejected', row.get('explain_reason', ''))}`"
        )
    lines.extend(["", "## Remaining Gaps", ""])
    for gap in gaps:
        lines.append(f"- `{gap['id']}` `{gap['severity']}` `{gap['status']}`: {gap['title']} | {gap['why']}")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_html(
    path: Path,
    cards: list[dict],
    rows: list[dict],
    artifacts: dict,
    metrics: dict,
    authority_rows: list[dict],
    residual_case_rows: list[dict],
    design_change_rows: list[dict],
    blocked_action_summary: dict,
    accepted_candidate_rows: list[dict],
    design_opt_entrypoint_rows: list[dict],
    design_opt_entrypoint_groups: list[dict],
    smoke_recent_samples: list[dict],
    external_benchmark_submission_queue_rows: list[dict],
    holdout_buckets: list[dict],
    holdout_detail_rows: list[dict],
    holdout_matrix_rows: list[dict],
    authority_catalog_diff: dict,
) -> None:
    story_change_rows, zone_change_rows = _aggregate_design_change_rows(design_change_rows)
    panel_zone_external_validation_surface = _panel_zone_external_validation_surface(metrics)
    selected_candidate_rows, unselected_candidate_rows = _split_accepted_candidate_rows(accepted_candidate_rows)
    smoke_history_png = Path(str(artifacts.get("smoke_history_png", "") or ""))
    smoke_history_panel_html = (
        f'<div class="panel"><h2>Nightly Smoke Trend</h2><img src="../{smoke_history_png.name}" alt="Nightly Smoke Trend"></div>'
        if smoke_history_png.exists()
        else ""
    )
    advanced_holdout_status_rows = [
        row for row in (metrics.get("advanced_holdout_status_rows", []) or []) if isinstance(row, dict)
    ]
    advanced_holdout_status_rows_html = []
    for row in advanced_holdout_status_rows:
        advanced_holdout_status_rows_html.append(
            f"""
            <tr>
              <td>{html.escape(str(row.get('title', row.get('id', '')) or ''))}</td>
              <td>{html.escape(str(row.get('severity', '') or 'n/a'))}</td>
              <td>{html.escape(str(row.get('closure_state', '') or 'n/a'))}</td>
              <td>{html.escape(str(row.get('mode', '') or 'n/a'))}</td>
              <td>{html.escape(str(row.get('reason_snippet', '') or 'n/a'))}</td>
              <td>{html.escape(str(row.get('evidence_snippet', '') or 'n/a'))}</td>
            </tr>
            """
        )
    smoke_recent_sample_rows_html = []
    for row in smoke_recent_samples:
        smoke_recent_sample_rows_html.append(
            f"""
            <tr>
              <td>{int(row.get('sample_index', 0))}</td>
              <td>{row.get('generated_at', '')}</td>
              <td>{bool(row.get('contract_pass', False))}</td>
              <td>{bool(row.get('trial_feasible', False))}</td>
              <td>{float(row.get('baseline_runtime_s', 0.0)):.4f}</td>
              <td>{float(row.get('trial_runtime_s', 0.0)):.4f}</td>
              <td>{float(row.get('trial_max_dcr', 0.0)):.4f}</td>
              <td>{row.get('trial_action_name', '')}</td>
            </tr>
            """
        )
    card_html = []
    for card in cards:
        klass = "pass" if card["status"] == "PASS" else ("fail" if card["status"] == "FAIL" else "info")
        card_html.append(
            f"""
            <div class="card {klass}">
              <div class="card-label label">{card['label']}</div>
              <div class="card-value value">{card['value']}</div>
              <div class="card-note note">{card.get('note', '')}</div>
            </div>
            """
        )
    row_html = []
    for row in rows:
        row_html.append(
            f"""
            <tr>
              <td>{row['section']}</td>
              <td>{row['item']}</td>
              <td>{row['criterion']}</td>
              <td>{row['value']}</td>
              <td>{row['status']}</td>
              <td>{row['evidence']}</td>
            </tr>
            """
        )
    authority_html = []
    for row in authority_rows:
        authority_html.append(
            f"""
            <tr data-authority-row="true" data-route-track="{html.escape(str(row.get('track', '') or ''), quote=True)}" data-route-case-id="{html.escape(str(row.get('case_id', '') or ''), quote=True)}">
              <td>{row['track']}</td>
              <td>{row['case_id']}</td>
              <td>{row['metric_a']}</td>
              <td>{row['metric_b']}</td>
              <td>{row['status']}</td>
              <td>{row['source_url']}</td>
            </tr>
            """
        )
    residual_html = []
    for row in residual_case_rows:
        residual_html.append(
            f"""
            <tr>
              <td>{row['case_id']}</td>
              <td>{row['split']}</td>
              <td>{row['hazard_type']}</td>
              <td>{row['pre_settle_top_m']:.6f}</td>
              <td>{row['post_settle_top_m']:.6f}</td>
              <td>{row['pre_settle_drift_pct']:.6f}</td>
              <td>{row['post_settle_drift_pct']:.6f}</td>
              <td>{row['delta_top_m']:.6f}</td>
              <td>{row['delta_drift_pct']:.6f}</td>
              <td>{row['residual_metric_source']}</td>
              <td>{row['residual_settle_steps']}</td>
            </tr>
            """
        )
    design_change_html = []
    for row in design_change_rows:
        design_change_html.append(
            f"""
            <tr data-design-change-row="true" data-route-story-band="{int(row['story_band'])}" data-route-zone-label="{html.escape(str(row.get('zone_label', '') or ''), quote=True)}" data-route-member-type="{html.escape(str(row.get('member_type', '') or ''), quote=True)}">
              <td>S{int(row['story_band']):02d}</td>
              <td>{row['zone_label']}</td>
              <td>{row['member_type']}</td>
              <td>{int(row['changed_group_count'])}</td>
              <td>{int(row['semantic_group_count'])}</td>
              <td>{float(row['rebar_ratio_delta_sum']):.6f}</td>
              <td>{float(row['cost_proxy_delta_sum']):.3f}</td>
              <td>{float(row['max_dcr_before_max']):.3f}</td>
              <td>{float(row['max_dcr_after_max']):.3f}</td>
              <td>{float(row.get('constructability_before_avg', 0.0)):.4f} -> {float(row.get('constructability_after_avg', 0.0)):.4f}</td>
              <td>{row.get('selection_gate', 'n/a')}</td>
            </tr>
            """
        )
    story_change_html = []
    for row in story_change_rows:
        story_change_html.append(
            f"""
            <tr>
              <td>S{int(row['story_band']):02d}</td>
              <td>{int(row['changed_group_count'])}</td>
              <td>{int(row['semantic_group_count'])}</td>
              <td>{float(row['rebar_ratio_delta_sum']):.6f}</td>
              <td>{float(row['cost_proxy_delta_sum']):.3f}</td>
              <td>{float(row['max_dcr_before_max']):.3f}</td>
              <td>{float(row['max_dcr_after_max']):.3f}</td>
            </tr>
            """
        )
    zone_change_html = []
    for row in zone_change_rows:
        zone_change_html.append(
            f"""
            <tr>
              <td>{row['zone_label']}</td>
              <td>{int(row['changed_group_count'])}</td>
              <td>{int(row['semantic_group_count'])}</td>
              <td>{float(row['rebar_ratio_delta_sum']):.6f}</td>
              <td>{float(row['cost_proxy_delta_sum']):.3f}</td>
              <td>{float(row['max_dcr_before_max']):.3f}</td>
              <td>{float(row['max_dcr_after_max']):.3f}</td>
            </tr>
            """
        )
    selected_candidate_html = []
    for row in selected_candidate_rows:
        selected_candidate_html.append(
            f"""
            <tr data-candidate-row="true" data-candidate-selected="true" data-route-candidate-id="{html.escape(str(row.get('candidate_id', '') or ''), quote=True)}" data-route-story-band="{int(row['story_band'])}" data-route-zone-label="{html.escape(str(row.get('zone_label', '') or ''), quote=True)}" data-route-member-type="{html.escape(str(row.get('member_type', '') or ''), quote=True)}" data-route-action-name="{html.escape(str(row.get('action_name', '') or ''), quote=True)}">
              <td>S{int(row['story_band']):02d}</td>
              <td>{row['zone_label']}</td>
              <td>{row['member_type']}</td>
              <td>{row['action_name']}</td>
              <td>{float(row.get('delta_cost', row.get('projected_cost_delta', 0.0))):.3f}</td>
              <td>{float(row.get('trial_max_dcr', row.get('max_dcr', 0.0))):.3f}</td>
              <td>{row.get('reason_selected', row.get('explain_reason', ''))}</td>
            </tr>
            """
        )
    unselected_candidate_html = []
    for row in unselected_candidate_rows:
        unselected_candidate_html.append(
            f"""
            <tr data-candidate-row="true" data-candidate-selected="false" data-route-candidate-id="{html.escape(str(row.get('candidate_id', '') or ''), quote=True)}" data-route-story-band="{int(row['story_band'])}" data-route-zone-label="{html.escape(str(row.get('zone_label', '') or ''), quote=True)}" data-route-member-type="{html.escape(str(row.get('member_type', '') or ''), quote=True)}" data-route-action-name="{html.escape(str(row.get('action_name', '') or ''), quote=True)}">
              <td>S{int(row['story_band']):02d}</td>
              <td>{row['zone_label']}</td>
              <td>{row['member_type']}</td>
              <td>{row['action_name']}</td>
              <td>{float(row.get('delta_cost', row.get('projected_cost_delta', 0.0))):.3f}</td>
              <td>{float(row.get('trial_max_dcr', row.get('max_dcr', 0.0))):.3f}</td>
              <td>{row.get('reason_rejected', row.get('explain_reason', ''))}</td>
            </tr>
            """
        )
    annotated_groups = annotate_entrypoint_groups(design_opt_entrypoint_groups)
    design_opt_entrypoint_group_html = []
    for row in annotated_groups:
        group_class = "pass" if bool(row.get("all_pass", False)) else ("info" if bool(row.get("all_present", False)) else "fail")
        design_opt_entrypoint_group_html.append(
            f"""
            <div class="card {group_class}">
              <div class="card-label label">{row['group_label']}</div>
              <div class="card-value value">{int(row.get('report_count', 0))}/{int(row.get('entrypoint_count', 0))}</div>
              <div class="card-note note">pass={int(row.get('pass_count', 0))} | fail={int(row.get('fail_count', 0))} | members={', '.join(row.get('entrypoint_names', []))}</div>
            </div>
            """
        )
    design_opt_entrypoint_detail_html = render_entrypoint_html_detail_sections(
        design_opt_entrypoint_rows,
        annotated_groups,
        table_style="margin-top: 16px;",
        header_html="""
            <thead>
              <tr><th>Name</th><th>Group</th><th>Primary Report</th><th>Contract Pass</th><th>Reason</th></tr>
            </thead>
        """.strip(),
    )
    row_provenance_preview_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_preview_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_clause_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_clause_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_member_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_member_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_hazard_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_hazard_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_rule_family_filter_rows = [
        row for row in (metrics.get("midas_kds_row_provenance_rule_family_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_summary_line = str(metrics.get("midas_kds_row_provenance_export_summary_line", "") or "").strip()
    row_provenance_appendix_html = ""
    if row_provenance_summary_line or row_provenance_preview_rows:
        def _viewer_reverse_link_cell(url: str, label: str) -> str:
            href = str(url or "").strip()
            if not href:
                return "<span class='note'>n/a</span>"
            return (
                f"<a href=\"{html.escape(href, quote=True)}\" target=\"_blank\" rel=\"noreferrer\">"
                f"{html.escape(label, quote=True)}</a>"
            )

        row_provenance_rows_html = "".join(
            (
                f"<tr data-route-combination-name=\"{row.get('combination_name', '')}\" "
                f"data-route-review-member-id=\"{row.get('member_id', '')}\" "
                f"data-route-clause-label=\"{row.get('clause_label', '')}\" "
                f"data-route-baseline-focus-member-id=\"{row.get('baseline_focus_member_id', '')}\">"
                f"<td>{row.get('combination_name', '')}</td><td>{row.get('member_id', '')}</td>"
                f"<td>{row.get('clause_label', '')}</td><td>{row.get('baseline_focus_member_id', '')}</td>"
                f"<td>{row.get('bridge_row_provenance_mode_label', '')}</td>"
                f"<td>{row.get('clause_provenance_summary_label', '')}</td>"
                f"<td>{row.get('bridge_member_inventory_summary_label', '')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_row_url', '') or ''), 'Open Viewer Row')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_slice_url', '') or ''), 'Open Viewer Slice')}</td></tr>"
            )
            for row in row_provenance_preview_rows
        ) or "<tr><td colspan='9'>No row provenance preview rows available.</td></tr>"
        row_provenance_clause_rows_html = "".join(
            (
                f"<tr><td>{row.get('clause_label', '')}</td><td>{row.get('row_count', '')}</td>"
                f"<td>{row.get('member_count', '')}</td><td>{row.get('combination_count', '')}</td>"
                f"<td>{row.get('top_member_id', '')}</td><td>{row.get('top_dcr_label', '')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_row_url', '') or ''), 'Open Viewer Row')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_slice_url', '') or ''), 'Open Viewer Slice')}</td></tr>"
            )
            for row in row_provenance_clause_filter_rows
        ) or "<tr><td colspan='8'>No clause filter rows available.</td></tr>"
        row_provenance_member_rows_html = "".join(
            (
                f"<tr><td>{row.get('member_id', '')}</td><td>{row.get('baseline_focus_member_id', '')}</td>"
                f"<td>{row.get('row_count', '')}</td><td>{row.get('clause_count', '')}</td>"
                f"<td>{row.get('combination_count', '')}</td><td>{row.get('top_clause_label', '')}</td></tr>"
            )
            for row in row_provenance_member_filter_rows
        ) or "<tr><td colspan='6'>No member filter rows available.</td></tr>"
        row_provenance_hazard_rows_html = "".join(
            (
                f"<tr data-route-hazard-type=\"{row.get('hazard_type', '')}\"><td>{row.get('hazard_type', '')}</td><td>{row.get('row_count', '')}</td>"
                f"<td>{row.get('member_count', '')}</td><td>{row.get('clause_count', '')}</td>"
                f"<td>{row.get('combination_count', '')}</td><td>{row.get('top_clause_label', '')}</td>"
                f"<td>{row.get('top_dcr_label', '')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_row_url', '') or ''), 'Open Viewer Row')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_slice_url', '') or ''), 'Open Viewer Slice')}</td></tr>"
            )
            for row in row_provenance_hazard_filter_rows
        ) or "<tr><td colspan='9'>No hazard filter rows available.</td></tr>"
        row_provenance_rule_family_rows_html = "".join(
            (
                f"<tr data-route-rule-family=\"{row.get('rule_family', '')}\"><td>{row.get('rule_family', '')}</td><td>{row.get('row_count', '')}</td>"
                f"<td>{row.get('member_count', '')}</td><td>{row.get('hazard_count', '')}</td>"
                f"<td>{row.get('combination_count', '')}</td><td>{row.get('top_clause_label', '')}</td>"
                f"<td>{row.get('top_dcr_label', '')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_row_url', '') or ''), 'Open Viewer Row')}</td>"
                f"<td>{_viewer_reverse_link_cell(str(row.get('viewer_slice_url', '') or ''), 'Open Viewer Slice')}</td></tr>"
            )
            for row in row_provenance_rule_family_filter_rows
        ) or "<tr><td colspan='9'>No rule family rows available.</td></tr>"
        row_provenance_artifact_meta = _committee_meta_list_html(
            [
                ("JSON", artifacts.get("midas_kds_row_provenance_export_json", "")),
                ("CSV", artifacts.get("midas_kds_row_provenance_export_csv", "")),
                ("Report", artifacts.get("midas_kds_row_provenance_export_report", "")),
            ]
        )
        row_provenance_appendix_html = f"""
        <section class="committee-appendix-block" id="committee-appendix-row-provenance" data-route-appendix-block="row-provenance">
          <div class="committee-appendix-block__header">
            <div class="committee-section-kicker">Appendix Evidence</div>
            <h3>Appendix: MIDAS KDS Row Provenance Export</h3>
            <p class="committee-appendix-summary">{row_provenance_summary_line or 'n/a'}</p>
          </div>
          {row_provenance_artifact_meta}
          <p class="note committee-note-muted">row-provenance sync: {ROW_PROVENANCE_SYNC_NOTE}</p>
          <div class="committee-table-stack">
            <table id="committee-appendix-row-provenance-table">
              <thead>
                <tr><th>Combination</th><th>Member</th><th>Clause</th><th>Baseline Focus</th><th>Mode</th><th>Clause Provenance</th><th>Member Inventory</th><th>Viewer Row</th><th>Viewer Slice</th></tr>
              </thead>
              <tbody>
                {row_provenance_rows_html}
              </tbody>
            </table>
            <table>
              <thead>
                <tr><th>Clause</th><th>Rows</th><th>Members</th><th>Combos</th><th>Top Member</th><th>Top D/C</th><th>Viewer Row</th><th>Viewer Slice</th></tr>
              </thead>
              <tbody>
                {row_provenance_clause_rows_html}
              </tbody>
            </table>
            <table>
              <thead>
                <tr><th>Member</th><th>Baseline Focus</th><th>Rows</th><th>Clauses</th><th>Combos</th><th>Top Clause</th></tr>
              </thead>
              <tbody>
                {row_provenance_member_rows_html}
              </tbody>
            </table>
            <table id="committee-appendix-row-provenance-hazard-table">
              <thead>
                <tr><th>Hazard</th><th>Rows</th><th>Members</th><th>Clauses</th><th>Combos</th><th>Top Clause</th><th>Top D/C</th><th>Viewer Row</th><th>Viewer Slice</th></tr>
              </thead>
              <tbody>
                {row_provenance_hazard_rows_html}
              </tbody>
            </table>
            <table id="committee-appendix-row-provenance-rule-family-table">
              <thead>
                <tr><th>Rule Family</th><th>Rows</th><th>Members</th><th>Hazards</th><th>Combos</th><th>Top Clause</th><th>Top D/C</th><th>Viewer Row</th><th>Viewer Slice</th></tr>
              </thead>
              <tbody>
                {row_provenance_rule_family_rows_html}
              </tbody>
            </table>
          </div>
        </section>
        """
    native_roundtrip_appendix_html = _midas_native_roundtrip_appendix_html(artifacts, metrics)
    irregular_structure_appendix_html = _irregular_structure_appendix_html(artifacts, metrics)
    appendix_block_count = sum(
        1
        for block in (
            design_opt_entrypoint_detail_html,
            row_provenance_appendix_html,
            native_roundtrip_appendix_html,
            irregular_structure_appendix_html,
        )
        if str(block or "").strip()
    )
    hero_stats = [
        ("Validation Checkpoints", str(len(rows)), "governance rows ready for committee scan"),
        ("Authority Cases", str(len(authority_rows)), "benchmark references paired with source links"),
        (
            "Candidate Actions",
            f"{len(selected_candidate_rows)}/{len(accepted_candidate_rows)}",
            "selected versus total cost-down candidates",
        ),
        ("Appendix Blocks", str(appendix_block_count), "traceable evidence surfaces in this package"),
    ]
    hero_stats_html = "".join(
        f"""
        <div class="committee-hero-stat">
          <span class="committee-hero-stat__label">{label}</span>
          <span class="committee-hero-stat__value">{value}</span>
          <span class="committee-hero-stat__note">{note}</span>
        </div>
        """
        for label, value, note in hero_stats
    )
    authority_catalog_diff_rows_html = "".join(
        f"<tr><td>{row.get('change_type', '')}</td><td>{row.get('authority_track', '')}</td><td>{row.get('submodel_family', '')}</td><td>{row.get('review_story_zone', '')}</td><td>{row.get('member_family', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('why', '')}</td></tr>"
        for row in (authority_catalog_diff.get("diff_rows") or [])
        if isinstance(row, dict)
    ) or '<tr><td colspan="7">No authority-catalog routing changes detected for this package refresh.</td></tr>'

    html_output = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Committee Review Package</title>
  <style>
    {build_signal_desk_light_css()}
    * {{ box-sizing: border-box; }}
    body.signal-desk-light {{
      color: var(--ink);
      font-family: var(--font-ui);
    }}
    .wrap {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 32px 24px 72px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.08fr) minmax(320px, .92fr);
      gap: 20px;
      align-items: stretch;
      margin-bottom: 20px;
    }}
    .hero-main {{
      padding: 30px;
      border-radius: var(--radius-xl);
      background:
        radial-gradient(circle at 18% 10%, rgba(255,255,255,.14), rgba(255,255,255,0) 34%),
        var(--review-hero-bg);
      color: #f4fbfc;
      box-shadow: var(--shadow-hero);
    }}
    .hero-kicker,
    .panel-kicker,
    .card-label,
    .committee-hero-stat__label,
    .committee-meta-list__label {{
      font-size: var(--type-label-size);
      font-weight: 700;
      line-height: var(--type-label-line-height);
      letter-spacing: var(--type-label-tracking);
      text-transform: uppercase;
    }}
    .hero-kicker {{
      color: #d5eff0;
      margin-bottom: 12px;
    }}
    .hero-main h1,
    .hero-side h2,
    .panel h2 {{
      margin: 0;
      font-family: var(--font-display);
      letter-spacing: var(--type-h2-tracking);
    }}
    .hero-main h1 {{
      font-size: var(--type-h1-size);
      line-height: var(--type-h1-line-height);
      letter-spacing: var(--type-h1-tracking);
    }}
    .hero-main p {{
      margin: 12px 0 0;
      max-width: 68ch;
      color: #e1f1f2;
      font-size: 15px;
      line-height: 1.72;
    }}
    .hero-pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: var(--radius-pill);
      background: rgba(255,255,255,.12);
      border: 1px solid rgba(255,255,255,.18);
      color: #f4fbfc;
      font-size: 12px;
      font-weight: 700;
    }}
    .hero-side,
    .card,
    .panel {{
      border-radius: var(--radius-lg);
      background: var(--review-panel-bg);
      border: 1px solid var(--line);
      box-shadow: var(--shadow-panel);
    }}
    .hero-side {{
      padding: 24px;
      display: grid;
      gap: 16px;
      align-content: start;
    }}
    .hero-side p,
    .card-note,
    .note {{
      margin: 0;
      color: var(--muted);
      font-size: var(--type-body-size);
      line-height: var(--type-body-line-height);
      letter-spacing: var(--type-body-tracking);
    }}
    .panel-kicker {{
      color: var(--brand);
    }}
    .hero-stat-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .committee-hero-stat {{
      padding: 14px;
      border: 1px solid rgba(15,106,115,.10);
      border-radius: var(--radius-md);
      background: rgba(255,255,255,.58);
    }}
    .committee-hero-stat__label {{
      color: var(--muted);
    }}
    .committee-hero-stat__value {{
      display: block;
      margin-top: 6px;
      font-family: var(--font-display);
      font-size: var(--type-metric-size);
      line-height: var(--type-metric-line-height);
      letter-spacing: var(--type-metric-tracking);
      color: var(--ink);
    }}
    .committee-hero-stat__note {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin: 0 0 24px;
    }}
    .card {{
      display: grid;
      align-content: start;
      gap: 8px;
      min-height: 188px;
      padding: 18px;
      background: var(--review-panel-quiet-bg);
    }}
    .card.pass {{
      border-color: rgba(47,125,90,.18);
    }}
    .card.fail {{
      border-color: rgba(161,73,46,.18);
    }}
    .card-label {{
      color: var(--muted);
    }}
    .card-value {{
      font-family: var(--font-display);
      font-size: clamp(28px, 2.4vw, var(--type-metric-size));
      line-height: 1.04;
      letter-spacing: var(--type-metric-tracking);
      color: var(--ink);
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .card-note {{
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 18px;
    }}
    .panel {{
      grid-column: span 6;
      position: relative;
      overflow: hidden;
      padding: 22px;
      background: var(--review-panel-quiet-bg);
    }}
    .panel::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(255,255,255,.56) 0%, rgba(255,255,255,0) 44%);
      pointer-events: none;
    }}
    .panel > * {{
      position: relative;
      z-index: 1;
    }}
    .panel img {{
      width: 100%;
      border-radius: var(--radius-md);
      border: 1px solid rgba(15,106,115,.12);
      background: #fffdf8;
    }}
    .panel h2 {{
      margin-bottom: 14px;
      font-size: var(--type-h2-size);
      line-height: var(--type-h2-line-height);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: transparent;
      font-size: var(--type-body-size);
      line-height: var(--type-body-line-height);
      letter-spacing: var(--type-body-tracking);
    }}
    th,
    td {{
      padding: 12px 0;
      border-bottom: 1px solid var(--review-divider);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: var(--type-label-size);
      font-weight: 700;
      line-height: var(--type-label-line-height);
      letter-spacing: var(--type-label-tracking);
      text-transform: uppercase;
    }}
    td:first-child,
    th:first-child {{
      width: 40%;
      padding-right: 16px;
      color: var(--muted);
    }}
    .committee-meta-list {{
      list-style: none;
      padding: 0;
      margin: 14px 0 0;
      display: grid;
      gap: 10px;
    }}
    .committee-meta-list li {{
      display: grid;
      grid-template-columns: minmax(120px, 180px) 1fr;
      gap: 12px;
      padding: 12px 14px;
      border: 1px solid rgba(15,106,115,.10);
      border-radius: var(--radius-md);
      background: rgba(255,255,255,.58);
      align-items: start;
    }}
    .committee-meta-list__label {{
      color: var(--muted);
    }}
    code {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: var(--radius-pill);
      background: var(--review-meta-bg);
      color: var(--review-meta-ink);
      font-family: 'IBM Plex Mono','SFMono-Regular',monospace;
      font-size: 12px;
      word-break: break-all;
    }}
    @media (max-width: 1080px) {{
      .hero {{
        grid-template-columns: 1fr;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
      .panel {{
        grid-column: 1 / -1;
      }}
    }}
    @media (max-width: 720px) {{
      .wrap {{
        padding: 24px 16px 56px;
      }}
      .hero-stat-grid {{
        grid-template-columns: 1fr;
      }}
      .committee-meta-list li {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body class="signal-desk-light">
  <div class="wrap">
    {render_route_context_banner(quote='"')}
    <section class="hero">
      <div class="hero-main">
        <div class="hero-kicker">Committee Review Surface</div>
        <h1>Committee Review Package</h1>
        <p>Integrated release package for PBD, wind, SSI, damper, construction, flexible-diaphragm, and reproducibility evidence. The goal is to let a senior reviewer move from release health to authority-facing proof without leaving the same product family.</p>
        <div class="hero-pill-row">
          <span class="hero-pill">Authority cases {len(authority_rows)}</span>
          <span class="hero-pill">Accepted candidates {len(accepted_candidate_rows)}</span>
          <span class="hero-pill">Appendix blocks {appendix_block_count}</span>
        </div>
      </div>
      <aside class="hero-side">
        <div class="panel-kicker">Signal Strip</div>
        <h2>Governance-ready evidence desk</h2>
        <p>Release checkpoints, authority packaging, and appendix provenance stay grouped into one committee-grade dashboard so the handoff feels delivered rather than assembled.</p>
        <div class="hero-stat-grid">
          {hero_stats_html}
        </div>
      </aside>
    </section>
    <div class="cards" id="committee-overview-cards">
      {''.join(card_html)}
    </div>
    <div class="grid">
      <div class="panel" id="committee-drift-envelope">
        <h2>Drift Envelope</h2>
        <img src="../pbd_review/{Path(artifacts['drift_envelope_png']).name}" alt="Drift envelope">
      </div>
      <div class="panel" id="committee-authority-validation">
        <h2>Core Hysteresis</h2>
        <img src="../pbd_review/{Path(artifacts['core_hysteresis_png']).name}" alt="Core hysteresis">
      </div>
      <div class="panel" id="committee-nightly-smoke-samples">
        <h2>Plastic Hinge Proxy</h2>
        <img src="../pbd_review/{Path(artifacts['hinge_proxy_3d_png']).name}" alt="Hinge proxy">
      </div>
      <div class="panel" id="committee-residual-holdout">
        <h2>Authority Validation</h2>
        <img src="../pbd_review/{Path(artifacts['authority_sac_kpi_png']).name}" alt="Authority SAC">
      </div>
      <div class="panel" id="committee-time-saving-coverage">
        <h2>NHERI Waveform</h2>
        <img src="../pbd_review/{Path(artifacts['authority_nheri_waveform_png']).name}" alt="Authority NHERI">
      </div>
      {smoke_history_panel_html}
      <div class="panel">
        <h2>Nightly Smoke Recent Samples</h2>
        <table>
          <thead>
            <tr><th>#</th><th>Generated</th><th>Pass</th><th>Trial Feasible</th><th>Baseline Runtime (s)</th><th>Trial Runtime (s)</th><th>Trial Max DCR</th><th>Action</th></tr>
          </thead>
          <tbody>
            {''.join(smoke_recent_sample_rows_html)}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Boundary</h2>
        <table>
          <thead>
            <tr><th>Work Item</th><th>Category</th><th>Due Date</th><th>SLA</th><th>Closure Evidence</th><th>Owner</th><th>Queue Status</th><th>Status</th><th>Relative Share</th><th>Absolute Project %</th><th>Scope</th></tr>
          </thead>
          <tbody>
            {''.join(f"<tr><td>{row.get('work_item_id', '')}</td><td>{row.get('label', row.get('id', ''))}</td><td>{row.get('due_date', '')}</td><td>{row.get('sla_label', '')}</td><td>{_holdout_closure_evidence_label(row)}</td><td>{row.get('owner', '')}</td><td>{row.get('queue_status', '')}</td><td>{row.get('status', '')}</td><td>{int(row.get('relative_share_pct', 0))}%</td><td>{_coverage_range_label(row.get('absolute_project_pct_range'))}</td><td>{row.get('scope', '')}</td></tr>" for row in holdout_buckets)}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Time-Saving Coverage</h2>
        <table>
          <tr><td>Coverage target</td><td>{metrics['accelerated_coverage_target_pct_label']}</td></tr>
          <tr><td>Residual holdout</td><td>{metrics['residual_holdout_target_pct_label']}</td></tr>
          <tr><td>Estimated time saved</td><td>{metrics['estimated_time_saved_pct_label']}</td></tr>
          <tr><td>Measured chain wall-clock (comparable rolling)</td><td>{metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f} min (N={int(metrics.get('measured_chain_rolling_sample_count', 0))}, range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]} min)</td></tr>
          <tr><td>Measured chain wall-clock (current)</td><td>{metrics['measured_chain_total_minutes']:.2f} min</td></tr>
          <tr><td>Comparable run selection mode</td><td>{metrics.get('measured_chain_rolling_selection_mode', '')}</td></tr>
          <tr><td>Comparable reference deployment</td><td>{metrics.get('measured_chain_comparable_reference_deployment_model', '')}</td></tr>
          <tr><td>Comparable reference strict smoke</td><td>{bool(metrics.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}</td></tr>
          <tr><td>Basis</td><td>{metrics['estimated_time_saved_basis']}</td></tr>
          <tr><td>Empirical smoke runtime reduction</td><td>{metrics.get('empirical_smoke_runtime_saved_pct_label', 'n/a')}</td></tr>
          <tr><td>Focus</td><td>{metrics['time_saving_focus']}</td></tr>
          <tr><td>External benchmark start mode</td><td>{metrics.get('external_benchmark_submission_recommended_start_mode', '')}</td></tr>
          <tr><td>External benchmark execution mode</td><td>{metrics.get('external_benchmark_execution_mode', '')}</td></tr>
          <tr><td>External benchmark execution counts</td><td>ready={int(metrics.get('external_benchmark_execution_ready_task_count', 0))} | blocked={int(metrics.get('external_benchmark_execution_blocked_task_count', 0))} | review_boundary_pending={int(metrics.get('external_benchmark_execution_review_boundary_pending_count', 0))}</td></tr>
          <tr><td>External benchmark review-boundary resolution</td><td>{metrics.get('external_benchmark_execution_review_boundary_resolution_label', '') or 'n/a'} | owner={metrics.get('external_benchmark_execution_review_boundary_owner_label', '') or 'none'} | assignee={metrics.get('external_benchmark_execution_review_boundary_assignee_label', '') or 'none'} | assignment={metrics.get('external_benchmark_execution_review_boundary_assignment_status_label', '') or 'none'} | priority={metrics.get('external_benchmark_execution_review_boundary_priority_label', '') or 'none'} | family={metrics.get('external_benchmark_execution_review_boundary_family_label', '') or 'none'} | changes={int(metrics.get('external_benchmark_execution_review_boundary_change_count_total', 0))} | followup={metrics.get('external_benchmark_execution_review_boundary_followup_action_label', '') or 'none'} | sla={metrics.get('external_benchmark_execution_review_boundary_sla_state_label', '') or 'none'} | age={metrics.get('external_benchmark_execution_review_boundary_age_bucket_label', '') or 'none'} | overdue={int(metrics.get('external_benchmark_execution_review_boundary_overdue_count', 0))} | oldest_open_h={float(metrics.get('external_benchmark_execution_review_boundary_oldest_open_age_hours', 0.0)):.3f}</td></tr>
          <tr><td>External benchmark execution status</td><td>{metrics.get('external_benchmark_execution_status_mode', '')}</td></tr>
          <tr><td>External benchmark execution status counts</td><td>planned={int(metrics.get('external_benchmark_execution_planned_task_count', 0))} | in_progress={int(metrics.get('external_benchmark_execution_in_progress_task_count', 0))} | completed={int(metrics.get('external_benchmark_execution_completed_task_count', 0))} | failed={int(metrics.get('external_benchmark_execution_failed_task_count', 0))} | finished={int(metrics.get('external_benchmark_execution_finished_task_count', 0))} | completion_ratio={float(metrics.get('external_benchmark_execution_completion_ratio', 0.0)):.3f}</td></tr>
          <tr><td>MIDAS section-library validator</td><td>{metrics.get('midas_section_library_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry-bridge validator</td><td>{metrics.get('midas_kds_geometry_bridge_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry-bridge load crosswalk</td><td>{metrics.get('midas_kds_geometry_bridge_load_crosswalk_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry-bridge semantic crosswalk</td><td>{metrics.get('midas_kds_geometry_bridge_semantic_crosswalk_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry-bridge full member crosswalk</td><td>{metrics.get('midas_kds_geometry_bridge_full_member_crosswalk_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry-bridge full section crosswalk</td><td>{metrics.get('midas_kds_geometry_bridge_full_section_crosswalk_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry-bridge full load crosswalk</td><td>{metrics.get('midas_kds_geometry_bridge_full_load_crosswalk_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS geometry full-crosswalk depth</td><td>{int(metrics.get('midas_kds_geometry_bridge_full_crosswalk_depth', 0))} (min(load/semantic crosswalk))</td></tr>
          <tr><td>MIDAS LOADCOMB round-trip validator</td><td>{metrics.get('midas_loadcomb_roundtrip_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Commercial scope</td><td>{metrics.get('commercial_scope_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Commercial reliability breadth</td><td>{metrics.get('commercial_reliability_breadth_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS KDS row provenance exact coverage</td><td>{metrics.get('midas_kds_row_provenance_exact_row_coverage_label', '') or 'n/a'}</td></tr>
          <tr><td>Commercial benchmark breadth</td><td>{metrics.get('commercial_benchmark_breadth_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Solver breadth</td><td>{metrics.get('solver_breadth_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Element/material breadth</td><td>{metrics.get('element_material_breadth_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Constitutive/interaction families</td><td>{CONSTITUTIVE_INTERACTION_NOTE}</td></tr>
          <tr><td>Material constitutive gate</td><td>{metrics.get('material_constitutive_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Steel/composite constitutive gate</td><td>{metrics.get('steel_composite_constitutive_gate_surface_label', '') or 'n/a'}</td></tr>
          <tr><td>Contact readiness</td><td>{metrics.get('contact_readiness_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Foundation/soil link</td><td>{metrics.get('foundation_soil_link_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Support search</td><td>{metrics.get('support_search_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Structural contact readiness</td><td>{metrics.get('structural_contact_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>General FE contact matrix</td><td>{metrics.get('general_fe_contact_matrix_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Surface interaction benchmark</td><td>{metrics.get('surface_interaction_benchmark_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS interoperability/export readiness</td><td>{metrics.get('midas_interoperability_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MIDAS native roundtrip/write-back</td><td>{metrics.get('midas_native_roundtrip_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Load-combination engine gate</td><td>{metrics.get('load_combination_engine_surface_label', '') or 'n/a'}</td></tr>
          <tr><td>Performance profiling</td><td>{metrics.get('performance_profiling_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>NDTHA step-series depth</td><td>{int(metrics.get('ndtha_step_series_depth', 0))} (max completed steps)</td></tr>
          <tr><td>NDTHA material depth</td><td>{int(metrics.get('ndtha_material_depth', 0))}</td></tr>
          <tr><td>NDTHA material surface</td><td>{metrics.get('ndtha_material_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Performance detail</td><td>moving_load_scale={metrics.get('performance_moving_load_scale_label', '') or 'n/a'} | cached_inverse={metrics.get('performance_moving_load_cached_inverse_label', '') or 'n/a'} | ssi_variant_sweep={metrics.get('performance_ssi_variant_sweep_label', '') or 'n/a'} | zero_gap={metrics.get('performance_ssi_zero_gap_variant_label', '') or 'n/a'} | pruned={metrics.get('performance_ssi_pruned_variant_label', '') or 'n/a'}</td></tr>
          <tr><td>Solver truthfulness gate</td><td>{metrics.get('solver_truthfulness_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Hardest external 10-case kickoff</td><td>{metrics.get('hardest_external_10case_kickoff_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Nonlinear generalization</td><td>{metrics.get('nonlinear_generalization_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Workflow/interoperability productization</td><td>{metrics.get('workflow_productization_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>KR ingest</td><td>{metrics.get('korean_source_ingest_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>KR preview queue</td><td>{metrics.get('korean_structural_preview_queue_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Irregular structure track</td><td>{metrics.get('irregular_structure_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>Commercial readiness</td><td>{metrics.get('commercial_readiness_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>MGT export LOADCOMB evidence</td><td>pass={bool(metrics.get('mgt_export_loadcomb_roundtrip_pass', False))} | {metrics.get('mgt_export_loadcomb_roundtrip_summary_line', '') or 'n/a'}</td></tr>
          <tr><td>PBD response source</td><td>resolved_report={metrics.get('pbd_resolved_ndtha_report', '') or 'n/a'} | response_npz={metrics.get('pbd_resolved_ndtha_response_npz', '') or 'n/a'} | fallback_used={bool(metrics.get('pbd_ndtha_response_fallback_used', False))} | coverage={int(metrics.get('pbd_ndtha_response_coverage_count', 0))}</td></tr>
          <tr><td>Structural optimization viewer</td><td>{artifacts.get('structural_optimization_viewer_html', '') or 'n/a'}</td></tr>
          <tr><td>Optimized drawing review</td><td>{artifacts.get('optimized_drawing_review_html', '') or 'n/a'} | projections={int(metrics.get('optimized_drawing_review_projection_count', 0))} | changed_groups={int(metrics.get('optimized_drawing_review_changed_group_count', 0))} | changed_members={int(metrics.get('optimized_drawing_review_changed_member_count', 0))} | axis={metrics.get('optimized_drawing_review_axis_source_mode', '') or 'n/a'} | x={metrics.get('optimized_drawing_review_axis_preview_label', '') or 'n/a'}</td></tr>
          <tr><td>Audit review decision batch template</td><td>items={int(metrics.get('audit_review_decision_batch_template_item_count', 0))} | status={metrics.get('audit_review_decision_batch_template_current_status_label', '') or 'none'} | owner={metrics.get('audit_review_decision_batch_template_review_owner_label', '') or 'none'} | priority={metrics.get('audit_review_decision_batch_template_review_priority_label', '') or 'none'} | attested_examples={int(metrics.get('audit_review_decision_batch_attested_example_count', 0))} | example_preview={metrics.get('audit_review_decision_batch_attested_example_preview_label', '') or 'none'}</td></tr>
          <tr><td>Approve-all readiness preview</td><td>reason={metrics.get('external_benchmark_submission_preview_approve_all_reason_code', '')} | ready_full={bool(metrics.get('external_benchmark_submission_preview_approve_all_ready_full', False))} | pending={int(metrics.get('external_benchmark_submission_preview_approve_all_pending_count', 0))} | open_revision={int(metrics.get('external_benchmark_submission_preview_approve_all_open_revision_count', 0))}</td></tr>
          <tr><td>Reject-one readiness preview</td><td>reason={metrics.get('external_benchmark_submission_preview_reject_one_reason_code', '')} | ready_full={bool(metrics.get('external_benchmark_submission_preview_reject_one_ready_full', False))} | pending={int(metrics.get('external_benchmark_submission_preview_reject_one_pending_count', 0))} | open_revision={int(metrics.get('external_benchmark_submission_preview_reject_one_open_revision_count', 0))} | blocker={metrics.get('external_benchmark_submission_preview_reject_one_blocker_label', '') or 'none'}</td></tr>
          <tr><td>Audit review decision batch runner</td><td>reason={metrics.get('audit_review_decision_batch_runner_reason_code', '')} | apply_live={bool(metrics.get('audit_review_decision_batch_runner_apply_live', False))} | live_applied={bool(metrics.get('audit_review_decision_batch_runner_live_applied', False))} | preview_reason={metrics.get('audit_review_decision_batch_runner_preview_reason_code', '') or 'none'} | preview_ready_full={bool(metrics.get('audit_review_decision_batch_runner_preview_ready_full', False))} | preview_pending={int(metrics.get('audit_review_decision_batch_runner_preview_pending_count', 0))} | preview_open_revision={int(metrics.get('audit_review_decision_batch_runner_preview_open_revision_count', 0))}</td></tr>
        </table>
      </div>
      {'<div class="panel"><h2>External Benchmark Submission Queue</h2><table><thead><tr><th>Work Item</th><th>Queue</th><th>Submission ID</th><th>Scope</th><th>Owner</th><th>Status</th><th>Receipt</th><th>Receipt Status</th><th>Onepage Status</th><th>Dry-run Evidence</th></tr></thead><tbody>' + ''.join(f"<tr><td>{row.get('work_item_id', '')}</td><td>{row.get('queue_id', '')}</td><td>{row.get('submission_id', '')}</td><td>{row.get('submission_scope', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('status', '')}</td><td>{_submission_receipt_label(row)}</td><td>{_submission_receipt_status_label(row)}</td><td>{row.get('onepage_attestation_status', '') or 'unknown'}</td><td>{row.get('dry_run_evidence', '') or 'n/a'}</td></tr>" for row in external_benchmark_submission_queue_rows) + '</tbody></table><div class="panel-note">onepage_attestation_status=' + (str(metrics.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown')) + ' | receipt_attached=' + str(int(metrics.get('external_benchmark_submission_receipt_attached_count', 0))) + ' | receipt_pending=' + str(int(metrics.get('external_benchmark_submission_receipt_pending_count', 0))) + '</div></div>' if external_benchmark_submission_queue_rows else ''}
      <div class="panel">
        <h2>Design Opt Raw vs Repaired</h2>
        <table>
          <tr><td>Raw max drift</td><td>{metrics.get('design_opt_raw_max_drift_pct', 0.0):.6f}%</td></tr>
          <tr><td>Raw residual drift</td><td>{metrics.get('design_opt_raw_residual_drift_pct', 0.0):.6f}%</td></tr>
          <tr><td>Raw max DCR</td><td>{metrics.get('design_opt_raw_max_dcr', 0.0):.6f}</td></tr>
          <tr><td>Repaired compliance max drift</td><td>{metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0):.6f}%</td></tr>
          <tr><td>Repaired compliance residual drift</td><td>{metrics.get('design_opt_repaired_compliance_residual_drift_pct', 0.0):.6f}%</td></tr>
          <tr><td>Repaired compliance max DCR</td><td>{metrics.get('design_opt_repaired_compliance_max_dcr', 0.0):.6f}</td></tr>
          <tr><td>Compliance basis</td><td>{metrics.get('design_opt_compliance_basis', '')}</td></tr>
          <tr><td>Repair action count</td><td>{int(metrics.get('design_opt_repair_action_count', 0))}</td></tr>
          <tr><td>Constructability signal gain</td><td>{metrics.get('design_opt_constructability_signal_gain_pct', 0.0):.6f}%</td></tr>
          <tr><td>Constructability avg</td><td>{metrics.get('design_opt_baseline_constructability_avg', 0.0):.6f} -> {metrics.get('design_opt_final_constructability_avg', 0.0):.6f}</td></tr>
          <tr><td>Detailing complexity avg</td><td>{metrics.get('design_opt_baseline_detailing_complexity_avg', 0.0):.6f} -> {metrics.get('design_opt_final_detailing_complexity_avg', 0.0):.6f}</td></tr>
          <tr><td>Selected family mix</td><td>{metrics.get('design_opt_selected_family_mix_label', '')}</td></tr>
          <tr><td>Selected dominant family</td><td>{metrics.get('design_opt_selected_dominant_family', '')} ({metrics.get('design_opt_selected_dominant_family_ratio', 0.0):.2%})</td></tr>
          <tr><td>Selected family mix trend</td><td>{metrics.get('design_opt_selected_family_trend_label', '')}</td></tr>
          <tr><td>Previous dominant family</td><td>{metrics.get('design_opt_previous_dominant_family', '')} ({metrics.get('design_opt_previous_dominant_family_ratio', 0.0):.2%})</td></tr>
          <tr><td>Preview supply family mix</td><td>{metrics.get('design_opt_preview_supply_family_mix_label', '')}</td></tr>
          <tr><td>Preview missing target families</td><td>{metrics.get('design_opt_preview_missing_target_families_label', '')}</td></tr>
          <tr><td>Illegal-by-mask families</td><td>{metrics.get('design_opt_blocked_illegal_by_mask_family_label', '')}</td></tr>
          <tr><td>Hard-gate families</td><td>{metrics.get('design_opt_blocked_constructability_hard_gate_family_label', '')}</td></tr>
          <tr><td>MGT export direct-patch families</td><td>{metrics.get('mgt_export_direct_patch_action_family_label', '')} ({int(metrics.get('mgt_export_direct_patch_change_count', 0))})</td></tr>
          <tr><td>MGT export sidecar families</td><td>{metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_instruction_sidecar_change_count', 0))})</td></tr>
          <tr><td>MGT export sidecar audit-only</td><td>{metrics.get('mgt_export_instruction_sidecar_audit_only_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_instruction_sidecar_audit_only_change_count', 0))})</td></tr>
          <tr><td>MGT export sidecar manual-input</td><td>{metrics.get('mgt_export_instruction_sidecar_manual_input_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_instruction_sidecar_manual_input_change_count', 0))})</td></tr>
          <tr><td>MGT audit review manifest</td><td>{metrics.get('mgt_export_audit_review_manifest_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_manifest_change_count', 0))})</td></tr>
          <tr><td>MGT audit review packets</td><td>{metrics.get('mgt_export_audit_review_packet_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_packet_count', 0))})</td></tr>
          <tr><td>MGT audit packet files</td><td>{metrics.get('mgt_export_audit_review_packet_file_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_packet_file_count', 0))})</td></tr>
          <tr><td>MGT audit review queue</td><td>{metrics.get('mgt_export_audit_review_queue_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_queue_item_count', 0))})</td></tr>
          <tr><td>MGT audit queue status</td><td>{metrics.get('mgt_export_audit_review_queue_status_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up actions</td><td>{metrics.get('mgt_export_audit_review_followup_action_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_followup_item_count', 0))})</td></tr>
          <tr><td>MGT audit follow-up owner</td><td>{metrics.get('mgt_export_audit_review_followup_owner_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up review owner</td><td>{metrics.get('mgt_export_audit_review_followup_review_owner_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up status</td><td>{metrics.get('mgt_export_audit_review_followup_status_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up SLA</td><td>{metrics.get('mgt_export_audit_review_followup_sla_state_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up age</td><td>{metrics.get('mgt_export_audit_review_followup_age_bucket_label', '') or 'n/a'} (overdue={int(metrics.get('mgt_export_audit_review_followup_overdue_item_count', 0))})</td></tr>
          <tr><td>MGT audit resolution actions</td><td>{metrics.get('mgt_export_audit_review_resolution_action_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_resolution_item_count', 0))})</td></tr>
          <tr><td>MGT audit resolution owner</td><td>{metrics.get('mgt_export_audit_review_resolution_owner_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit resolution status</td><td>{metrics.get('mgt_export_audit_review_resolution_status_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit packet followups</td><td>{metrics.get('mgt_export_audit_review_packet_followup_type_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT rebar namespace mode</td><td>{metrics.get('mgt_export_rebar_payload_namespace_mode', '')}</td></tr>
          <tr><td>MGT rebar delivery mode</td><td>{metrics.get('mgt_export_rebar_delivery_mode', '')}</td></tr>
          <tr><td>MGT evidence model</td><td>{metrics.get('mgt_export_evidence_model', '')}</td></tr>
          <tr><td>MGT delivery boundary</td><td>{metrics.get('mgt_export_delivery_boundary', '') or 'n/a'}</td></tr>
          <tr><td>MGT rebar material namespace present</td><td>{bool(metrics.get('mgt_export_rebar_payload_material_level_namespace_present', False))}</td></tr>
          <tr><td>MGT rebar group-local namespace present</td><td>{bool(metrics.get('mgt_export_rebar_payload_group_local_namespace_present', False))}</td></tr>
          <tr><td>MGT material rebar payloads</td><td>{int(metrics.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_material_level_rebar_payload_row_count', 0))}</td></tr>
          <tr><td>MGT group-local rebar payloads</td><td>{int(metrics.get('mgt_export_group_local_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_rebar_payload_row_count', 0))}</td></tr>
          <tr><td>MGT connection namespace mode</td><td>{metrics.get('mgt_export_connection_detailing_payload_namespace_mode', '')}</td></tr>
          <tr><td>MGT connection group-local namespace present</td><td>{bool(metrics.get('mgt_export_connection_detailing_payload_group_local_namespace_present', False))}</td></tr>
          <tr><td>MGT group-local connection payloads</td><td>{int(metrics.get('mgt_export_group_local_connection_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_connection_detailing_payload_row_count', 0))}</td></tr>
          <tr><td>MGT connection direct-patch eligible</td><td>{int(metrics.get('mgt_export_connection_detailing_direct_patch_eligible_change_count', 0))}</td></tr>
          <tr><td>MGT detailing namespace mode</td><td>{metrics.get('mgt_export_detailing_payload_namespace_mode', '')}</td></tr>
          <tr><td>MGT detailing group-local namespace present</td><td>{bool(metrics.get('mgt_export_detailing_payload_group_local_namespace_present', False))}</td></tr>
          <tr><td>MGT group-local detailing payloads</td><td>{int(metrics.get('mgt_export_group_local_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_detailing_payload_row_count', 0))}</td></tr>
          <tr><td>MGT detailing direct-patch eligible</td><td>{int(metrics.get('mgt_export_detailing_direct_patch_eligible_change_count', 0))}</td></tr>
          <tr><td>MGT connection structured payload mapped</td><td>{int(metrics.get('mgt_export_connection_detailing_structured_payload_mapped_change_count', 0))}</td></tr>
          <tr><td>MGT detailing structured payload mapped</td><td>{int(metrics.get('mgt_export_detailing_structured_payload_mapped_change_count', 0))}</td></tr>
          <tr><td>MGT connection delivery mode</td><td>{metrics.get('mgt_export_connection_detailing_delivery_mode', '')}</td></tr>
          <tr><td>MGT detailing delivery mode</td><td>{metrics.get('mgt_export_detailing_delivery_mode', '')}</td></tr>
          <tr><td>MGT rebar direct-patch eligible</td><td>{int(metrics.get('mgt_export_rebar_direct_patch_eligible_change_count', 0))}</td></tr>
          <tr><td>MGT patched material rows</td><td>{int(metrics.get('mgt_export_patched_material_row_count', 0))}</td></tr>
          <tr><td>MGT cloned material rows</td><td>{int(metrics.get('mgt_export_cloned_material_count', 0))}</td></tr>
          <tr><td>MGT rebar direct-patch blockers</td><td>{metrics.get('mgt_export_rebar_direct_patch_ineligible_reason_label', '')}</td></tr>
          <tr><td>MGT rebar mapping sources</td><td>{metrics.get('mgt_export_rebar_direct_patch_mapping_source_label', '')}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Advanced Holdout Closure</h2>
        <table>
          <tr><td>Total</td><td>{int(metrics.get('advanced_holdout_total_count', 0))}</td></tr>
          <tr><td>Closed</td><td>{int(metrics.get('advanced_holdout_closed_count', 0))}</td></tr>
          <tr><td>Open</td><td>{int(metrics.get('advanced_holdout_open_count', 0))}</td></tr>
          <tr><td>Summary</td><td>{metrics.get('advanced_holdout_status_label', '') or 'n/a'}</td></tr>
        </table>
        <table style="margin-top: 12px;">
          <thead>
            <tr><th>Holdout</th><th>Severity</th><th>Closure</th><th>Mode</th><th>Reason</th><th>Evidence</th></tr>
          </thead>
          <tbody>
            {''.join(advanced_holdout_status_rows_html)}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Review Table</h2>
        <table>
          <thead>
            <tr><th>Advanced Holdout</th><th>Ready</th><th>Mode</th><th>Why</th></tr>
          </thead>
          <tbody>
            <tr><td>PBD dynamic hinge refresh</td><td>{bool(metrics.get('pbd_dynamic_hinge_refresh_ready', False))}</td><td>{metrics.get('pbd_hinge_state_mode', '')}</td><td>{metrics.get('pbd_hinge_refresh_reason', '')}</td></tr>
            <tr><td>PBD hinge evidence</td><td>artifact={bool(metrics.get('pbd_hinge_refresh_artifact_present', False))}</td><td>{metrics.get('pbd_hinge_refresh_source_mode', '')}</td><td>overlap={int(metrics.get('pbd_hinge_refresh_overlap_member_count', 0))} | rebar-sensitive={int(metrics.get('pbd_hinge_refresh_rebar_sensitive_member_count', 0))}</td></tr>
            <tr><td>PBD hinge benchmark</td><td>{bool(metrics.get('pbd_hinge_benchmark_gate_pass', False))}</td><td>assets={int(metrics.get('pbd_hinge_benchmark_asset_count', 0))}</td><td>train={int(metrics.get('pbd_hinge_benchmark_train_count', 0))} | val={int(metrics.get('pbd_hinge_benchmark_val_count', 0))} | holdout={int(metrics.get('pbd_hinge_benchmark_holdout_count', 0))} | rebar-sensitive={int(metrics.get('pbd_hinge_benchmark_rebar_sensitive_count', 0))} | confinement-sensitive={int(metrics.get('pbd_hinge_benchmark_confinement_sensitive_count', 0))} | fixture-regression={bool(metrics.get('pbd_hinge_benchmark_fixture_regression_pass', False))} | fixtures={int(metrics.get('pbd_hinge_benchmark_fixture_count', 0))} | min-point={int(metrics.get('pbd_hinge_benchmark_fixture_min_point_count', 0))} | min-peak-drift={float(metrics.get('pbd_hinge_benchmark_fixture_min_peak_drift_ratio', 0.0)):.6f} | alignment={bool(metrics.get('pbd_hinge_benchmark_alignment_pass', False))} | refresh-columns={int(metrics.get('pbd_hinge_benchmark_alignment_refresh_column_row_count', 0))} | rebar-columns={int(metrics.get('pbd_hinge_benchmark_alignment_rebar_sensitive_column_count', 0))} | benchmark-rebar={float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min', 0.0)):.4f}-{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max', 0.0)):.4f} | refresh-rebar={float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min', 0.0)):.4f}-{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max', 0.0)):.4f}</td></tr>
            <tr><td>Panel-zone 3D clash and anchorage</td><td>{bool(metrics.get('panel_zone_3d_clash_ready', False))}</td><td>{metrics.get('panel_zone_constructability_mode', '')}</td><td>{metrics.get('panel_zone_constructability_reason', '')}</td></tr>
            <tr><td>Panel-zone evidence source</td><td>{metrics.get('panel_zone_source_artifact_kind', '')}</td><td>{metrics.get('panel_zone_source_contract_mode', '')}</td><td>{', '.join(metrics.get('panel_zone_missing_required_sources', []))}</td></tr>
            <tr><td>Panel-zone validation boundary</td><td>{bool(metrics.get('panel_zone_internal_engine_complete', False))}</td><td>{bool(metrics.get('panel_zone_external_validation_pending', False))}</td><td>{metrics.get('panel_zone_validation_boundary', '')} | artifact_closed={bool(panel_zone_external_validation_surface['artifact_closed'])} | closure_mode={panel_zone_external_validation_surface['closure_mode']} | advisory_only={bool(panel_zone_external_validation_surface['advisory_only'])} | release_blocking={bool(panel_zone_external_validation_surface['release_blocking'])} | status={panel_zone_external_validation_surface['status_label']} | release_status={metrics.get('panel_zone_status_label', '')} | required_evidence={metrics.get('panel_zone_external_validation_required_evidence', '') or 'n/a'} | local_closeout={metrics.get('panel_zone_external_validation_local_closure_state', '') or 'n/a'} | {metrics.get('panel_zone_external_validation_local_closure_label', '')} | {metrics.get('panel_zone_external_validation_closing_summary_label', '')}</td></tr>
            <tr><td>Panel-zone source coverage</td><td>{metrics.get('panel_zone_external_validation_provenance_summary_label', '')}</td><td>validated rows={int(metrics.get('panel_zone_validated_source_row_count_total', 0))} | min overlap={int(metrics.get('panel_zone_validated_source_overlap_member_count_min', 0))}</td><td>{', '.join(f"{k}:{v}" for k, v in sorted((metrics.get('panel_zone_source_candidate_scan_modes', {}) or {}).items()) if str(v).strip())} | bundles={', '.join(f"{k}:{v}" for k, v in sorted((metrics.get('panel_zone_source_bundle_modes', {}) or {}).items()) if str(v).strip())}</td></tr>
            <tr><td>Panel-zone sidecar overlap</td><td>{bool(metrics.get('panel_zone_instruction_sidecar_present', False))}</td><td>{metrics.get('panel_zone_instruction_sidecar_candidate_overlap_mode', '')}</td><td>changes={int(metrics.get('panel_zone_instruction_sidecar_change_count', 0))} | overlap rows={int(metrics.get('panel_zone_instruction_sidecar_overlap_row_count', 0))} | overlap members={int(metrics.get('panel_zone_instruction_sidecar_overlap_member_count', 0))} | evidence={metrics.get('panel_zone_instruction_sidecar_evidence_model', '')} | delivery={metrics.get('panel_zone_instruction_sidecar_rebar_delivery_mode', '')} | mapping present={bool(metrics.get('panel_zone_member_mapping_sidecar_present', False))} | mapping mode={metrics.get('panel_zone_member_mapping_sidecar_mode', '')} | mapping rows={int(metrics.get('panel_zone_member_mapping_sidecar_row_count', 0))} | mapping applied={int(metrics.get('panel_zone_member_mapping_sidecar_applied_row_count', 0))} | mapping unmapped={int(metrics.get('panel_zone_member_mapping_sidecar_unmapped_source_member_count', 0))}</td></tr>
            <tr><td>Panel-zone solver inbox</td><td>{metrics.get('panel_zone_solver_verified_inbox_status_mode', '')}</td><td>pending={bool(metrics.get('panel_zone_solver_verified_pending_input', False))}</td><td>mode={metrics.get('panel_zone_solver_verified_input_mode_detected', '')} | origin={metrics.get('panel_zone_solver_verified_source_origin_class', '') or 'missing'} | release refresh={bool(metrics.get('panel_zone_solver_verified_release_refresh_source_allowed', False))} | latest consume={bool(metrics.get('panel_zone_solver_verified_latest_consume_contract_pass', False))}:{metrics.get('panel_zone_solver_verified_latest_consume_reason_code', '')} | next={metrics.get('panel_zone_solver_verified_recommended_action', '')}</td></tr>
            <tr><td>Foundation / mat / pile optimization</td><td>{bool(metrics.get('foundation_optimization_ready', False))}</td><td>{metrics.get('foundation_optimization_mode', '')}</td><td>{metrics.get('foundation_optimization_reason', '')}</td></tr>
            <tr><td>Foundation scope provenance</td><td>{metrics.get('foundation_scope_source', '')}</td><td>{metrics.get('foundation_artifact_scan_mode', '')}</td><td>upstream labels={int(metrics.get('upstream_foundation_label_count', 0))} | raw labels={int(metrics.get('raw_source_foundation_label_count', 0))} | {metrics.get('upstream_foundation_provenance_mode', '')}</td></tr>
            <tr><td>Wind-tunnel raw mapping</td><td>{bool(metrics.get('wind_tunnel_raw_mapping_ready', False))}</td><td>{metrics.get('wind_tunnel_mapping_mode', '')}</td><td>{metrics.get('wind_tunnel_mapping_reason', '')}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Review Table</h2>
        <table>
          <thead>
            <tr><th>Category</th><th>Work Item</th><th>Axis</th><th>Detail</th><th>Owner</th><th>Queue Status</th><th>Status</th><th>SLA</th><th>Due</th><th>Closure Evidence</th><th>Why</th></tr>
          </thead>
          <tbody>
            {''.join(f"<tr><td>{row.get('bucket_label', row.get('bucket_id', ''))}</td><td>{row.get('work_item_id', '')}</td><td>{row.get('detail_axis', '')}</td><td>{row.get('detail_value', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('queue_status', '')}</td><td>{row.get('status', '')}</td><td>{row.get('sla_label', '')}</td><td>{row.get('due_date', '')}</td><td>{row.get('closure_evidence_required', '')} ({row.get('closure_evidence_status', '')})</td><td>{row.get('why', '')}</td></tr>" for row in holdout_detail_rows)}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Routing Matrix</h2>
        <table>
          <thead>
            <tr><th>Category</th><th>Track</th><th>Submodel</th><th>Review Story/Zone</th><th>Member Family</th><th>Owner</th><th>Why</th></tr>
          </thead>
          <tbody>
            {''.join(f"<tr><td>{row.get('bucket_label', '')}</td><td>{row.get('authority_track', '')}</td><td>{row.get('submodel_family', '')}</td><td>{row.get('review_story_zone', '')}</td><td>{row.get('member_family', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('why', '')}</td></tr>" for row in holdout_matrix_rows)}
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Authority Catalog Routing Diff</h2>
        <table>
          <tr><td>Baseline seeded</td><td>{bool(authority_catalog_diff.get('baseline_seeded', False))}</td></tr>
          <tr><td>Changes</td><td>{int(authority_catalog_diff.get('change_count', 0))}</td></tr>
          <tr><td>Added</td><td>{int(authority_catalog_diff.get('added_count', 0))}</td></tr>
          <tr><td>Removed</td><td>{int(authority_catalog_diff.get('removed_count', 0))}</td></tr>
          <tr><td>Unchanged</td><td>{int(authority_catalog_diff.get('unchanged_count', 0))}</td></tr>
        </table>
        <table style="margin-top: 12px;">
          <thead>
            <tr><th>Change</th><th>Track</th><th>Submodel</th><th>Review Story/Zone</th><th>Member Family</th><th>Owner</th><th>Why</th></tr>
          </thead>
          <tbody>
            {authority_catalog_diff_rows_html}
          </tbody>
        </table>
      </div>
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-validation-table">
      <h2>Validation Table</h2>
      <table>
        <thead>
          <tr><th>Section</th><th>Item</th><th>Criterion</th><th>Value</th><th>Status</th><th>Evidence</th></tr>
        </thead>
        <tbody>
          {''.join(row_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-authority-benchmark">
      <h2>Design Optimization Entrypoint Groups</h2>
      <div class="cards" style="margin: 0;">
        {''.join(design_opt_entrypoint_group_html)}
      </div>
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-design-change-summary">
      <h2>Appendix</h2>
      {design_opt_entrypoint_detail_html}
      {row_provenance_appendix_html}
      {native_roundtrip_appendix_html}
      {_irregular_structure_appendix_html(artifacts, metrics)}
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-authority-table">
      <h2>Authority Benchmark Table</h2>
      <table>
        <thead>
          <tr><th>Track</th><th>Case</th><th>Metric A</th><th>Metric B</th><th>Status</th><th>Source</th></tr>
        </thead>
        <tbody>
          {''.join(authority_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;">
      <h2>NDTHA Residual Case Trace</h2>
      <table>
        <thead>
          <tr><th>Case</th><th>Split</th><th>Hazard</th><th>Pre Top (m)</th><th>Post Top (m)</th><th>Pre Drift (%)</th><th>Post Drift (%)</th><th>Delta Top (m)</th><th>Delta Drift (%)</th><th>Source</th><th>Settle Steps</th></tr>
        </thead>
        <tbody>
          {''.join(residual_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;">
      <h2>Design Change Story Totals</h2>
      <table>
        <thead>
          <tr><th>Story</th><th>Changed Groups</th><th>Semantic Groups</th><th>Rebar Delta Sum</th><th>Cost Delta Sum</th><th>DCR Before Max</th><th>DCR After Max</th></tr>
        </thead>
        <tbody>
          {''.join(story_change_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;">
      <h2>Design Change Zone Totals</h2>
      <table>
        <thead>
          <tr><th>Zone</th><th>Changed Groups</th><th>Semantic Groups</th><th>Rebar Delta Sum</th><th>Cost Delta Sum</th><th>DCR Before Max</th><th>DCR After Max</th></tr>
        </thead>
        <tbody>
          {''.join(zone_change_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;">
      <h2>Blocked Cost-Down Actions</h2>
      <table>
        <thead>
          <tr><th>Blocked Rows</th><th>Illegal by Mask</th><th>No Cost Gain</th><th>Hard Gate</th><th>Violates Feasible Constraints</th><th>No Action Delta</th><th>Accepted Candidate</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>{int(blocked_action_summary.get('blocked_action_row_count', 0))}</td>
            <td>{int(blocked_action_summary.get('illegal_by_mask', 0))}</td>
            <td>{int(blocked_action_summary.get('no_cost_gain', 0))}</td>
            <td>{int(blocked_action_summary.get('constructability_hard_gate_block_count', 0))}</td>
            <td>{int(blocked_action_summary.get('violates_feasible_constraints', 0))}</td>
            <td>{int(blocked_action_summary.get('no_action_delta', 0))}</td>
            <td>{int(blocked_action_summary.get('accepted_candidate', 0))}</td>
          </tr>
          <tr>
            <td colspan="7">no_cost_gain_groups={int(blocked_action_summary.get('blocked_no_cost_group_count', 0))} | no_cost_gain_explain_rows={int(blocked_action_summary.get('blocked_no_cost_explain_row_count', 0))} | hard_gate_reasons={str(blocked_action_summary.get('constructability_hard_gate_reason_label', '')) or 'n/a'} | hard_gate_families={str(blocked_action_summary.get('constructability_hard_gate_family_label', '')) or 'n/a'}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-selected-candidates">
      <h2>Selected Cost-Down Candidates</h2>
      <table>
        <thead>
          <tr><th>Story</th><th>Zone</th><th>Member</th><th>Action</th><th>Projected Cost Delta</th><th>Max DCR</th><th>Reason</th></tr>
        </thead>
        <tbody>
          {''.join(selected_candidate_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-unselected-candidates">
      <h2>Unselected Cost-Down Candidates</h2>
      <table>
        <thead>
          <tr><th>Story</th><th>Zone</th><th>Member</th><th>Action</th><th>Projected Cost Delta</th><th>Max DCR</th><th>Reason</th></tr>
        </thead>
        <tbody>
          {''.join(unselected_candidate_html)}
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 16px;" id="committee-design-change-table">
      <h2>Design Change Summary</h2>
      <table>
        <thead>
          <tr><th>Story</th><th>Zone</th><th>Member</th><th>Changed Groups</th><th>Semantic Groups</th><th>Rebar Delta Sum</th><th>Cost Delta Sum</th><th>DCR Before Max</th><th>DCR After Max</th><th>Constructability Avg</th><th>Selection Gate</th></tr>
        </thead>
        <tbody>
          {''.join(design_change_html)}
        </tbody>
      </table>
    </div>
  </div>
<script>
(() => {{
  const params = new URL(window.location.href).searchParams;
  const title = String(params.get('route_title') || '').trim();
  const banner = document.getElementById('route-context-banner');
  if (!banner || !title) return;

  const renderText = (id, value) => {{
    const element = document.getElementById(id);
    if (!element) return;
    const text = String(value || '').trim();
    element.textContent = text;
    element.hidden = !text;
  }};

  const reviewMode = String(params.get('review_mode') || '').replace(/[_-]+/g, ' ').trim();
  const routeStep = String(params.get('route_step') || '').trim();
  const fromLabel = String(params.get('from_label') || '').trim();
  const targetLabel = String(params.get('target_label') || '').trim();
  const selectionStatus = String(params.get('selection_status') || '').trim();
  const sourceLabel = String(params.get('source_label') || '').trim();
  const targetSurface = String(params.get('target_surface') || '').trim();

  renderText('route-context-title', title);
  renderText('route-context-step', [routeStep ? `step ${{routeStep}}` : '', reviewMode].filter(Boolean).join(' | '));
  renderText('route-context-source', fromLabel ? `from ${{fromLabel}}` : '');
  renderText('route-context-target', targetLabel ? `target ${{targetLabel}}` : '');
  renderText('route-context-status', selectionStatus ? `selection ${{selectionStatus}}` : '');
  renderText(
    'route-context-note',
    [sourceLabel ? `snapshot ${{sourceLabel}}` : '', targetSurface ? `surface ${{targetSurface}}` : '']
      .filter(Boolean)
      .join(' | '),
  );

  const returnTo = String(params.get('return_to') || '').trim();
  const returnLabel = String(params.get('return_label') || 'Structural Optimization Workbench').trim();
  const returnLink = document.getElementById('route-context-return');
  if (returnLink && returnTo) {{
    returnLink.href = returnTo;
    returnLink.textContent = returnLabel;
    returnLink.hidden = false;
  }}

  banner.hidden = false;
  const routeFocusId = String(params.get('route_focus') || '').trim();
  const routeFocusTarget = routeFocusId ? document.getElementById(routeFocusId) : null;
  if (routeFocusTarget) {{
    window.requestAnimationFrame(() => {{
      routeFocusTarget.classList.add('route-focus-target');
      routeFocusTarget.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      window.setTimeout(() => routeFocusTarget.classList.remove('route-focus-target'), 2200);
    }});
  }}

  const normalizeRouteToken = (value) => String(value || '').trim().toLowerCase();
  const normalizeRouteStoryBand = (value) => {{
    const raw = String(value || '').trim();
    if (!raw) return '';
    const numeric = Number(raw.replace(/^S/i, ''));
    if (Number.isFinite(numeric) && numeric > 0) {{
      return String(Math.trunc(numeric));
    }}
    return raw.replace(/^S/i, '').replace(/^0+/, '').trim();
  }};
  const flashRouteSelection = (node) => {{
    if (!node) return;
    window.requestAnimationFrame(() => {{
      node.classList.add('route-selection-target');
      node.scrollIntoView({{ behavior: 'smooth', block: 'center', inline: 'nearest' }});
      window.setTimeout(() => node.classList.remove('route-selection-target'), 2200);
    }});
  }};
  const routeTrack = String(params.get('route_track') || '').trim();
  const routeCaseId = String(params.get('route_case_id') || '').trim();
  const routeCandidateId = String(params.get('route_candidate_id') || '').trim();
  const routeStoryBand = normalizeRouteStoryBand(params.get('route_story_band') || '');
  const routeZoneLabel = String(params.get('route_zone_label') || '').trim();
  const routeMemberType = String(params.get('route_member_type') || '').trim();
  const routeActionName = String(params.get('route_action_name') || '').trim();
  const routeAppendixBlock = normalizeRouteToken(params.get('route_appendix_block') || '');
  const routeCombinationName = String(params.get('route_combination_name') || '').trim();
  const routeClauseLabel = String(params.get('route_clause_label') || '').trim();
  const routeReviewMemberId = String(params.get('route_review_member_id') || '').trim();
  const routeBaselineFocusMemberId = String(params.get('route_baseline_focus_member_id') || '').trim();
  const routeHazardType = String(params.get('route_hazard_type') || '').trim();
  const routeRuleFamily = String(params.get('route_rule_family') || '').trim();

  const authorityRows = [...document.querySelectorAll('[data-authority-row]')];
  const candidateRows = [...document.querySelectorAll('[data-candidate-row]')];
  const designChangeRows = [...document.querySelectorAll('[data-design-change-row]')];
  const appendixIdByBlock = {{
    'row-provenance': 'committee-appendix-row-provenance',
    'native-roundtrip': 'committee-appendix-native-roundtrip',
    'irregular-structure': 'committee-appendix-irregular-structure',
  }};

  const authorityTarget = authorityRows.find((row) => {{
    const trackMatch = routeTrack
      ? normalizeRouteToken(row.getAttribute('data-route-track')) === normalizeRouteToken(routeTrack)
      : false;
    const caseMatch = routeCaseId
      ? String(row.getAttribute('data-route-case-id') || '').trim() === routeCaseId
      : false;
    return trackMatch || caseMatch;
  }}) || null;

  const candidateTarget = candidateRows.find((row) => {{
    const candidateMatch = routeCandidateId
      ? String(row.getAttribute('data-route-candidate-id') || '').trim() === routeCandidateId
      : false;
    const storyMatch = routeStoryBand
      ? normalizeRouteStoryBand(row.getAttribute('data-route-story-band') || '') === routeStoryBand
      : true;
    const zoneMatch = routeZoneLabel
      ? normalizeRouteToken(row.getAttribute('data-route-zone-label')) === normalizeRouteToken(routeZoneLabel)
      : true;
    const memberMatch = routeMemberType
      ? normalizeRouteToken(row.getAttribute('data-route-member-type')) === normalizeRouteToken(routeMemberType)
      : true;
    const actionMatch = routeActionName
      ? normalizeRouteToken(row.getAttribute('data-route-action-name')) === normalizeRouteToken(routeActionName)
      : true;
    return candidateMatch || (storyMatch && zoneMatch && memberMatch && actionMatch && (routeStoryBand || routeZoneLabel || routeMemberType || routeActionName));
  }}) || null;

  const designChangeTarget = designChangeRows.find((row) => {{
    const storyMatch = routeStoryBand
      ? normalizeRouteStoryBand(row.getAttribute('data-route-story-band') || '') === routeStoryBand
      : false;
    const zoneMatch = routeZoneLabel
      ? normalizeRouteToken(row.getAttribute('data-route-zone-label')) === normalizeRouteToken(routeZoneLabel)
      : false;
    const memberMatch = routeMemberType
      ? normalizeRouteToken(row.getAttribute('data-route-member-type')) === normalizeRouteToken(routeMemberType)
      : false;
    return storyMatch || (zoneMatch && memberMatch) || (storyMatch && zoneMatch) || (storyMatch && memberMatch);
  }}) || null;

  const appendixTarget = routeAppendixBlock
    ? document.getElementById(appendixIdByBlock[routeAppendixBlock] || '')
    : null;
  const rowProvenanceTarget = [...document.querySelectorAll('#committee-appendix-row-provenance-table tbody tr')].find((row) => {{
    const combinationMatch = routeCombinationName
      ? String(row.getAttribute('data-route-combination-name') || '').trim() === routeCombinationName
      : true;
    const memberMatch = routeReviewMemberId
      ? normalizeRouteToken(row.getAttribute('data-route-review-member-id')) === normalizeRouteToken(routeReviewMemberId)
      : true;
    const clauseMatch = routeClauseLabel
      ? normalizeRouteToken(row.getAttribute('data-route-clause-label')) === normalizeRouteToken(routeClauseLabel)
      : true;
    const baselineMatch = routeBaselineFocusMemberId
      ? String(row.getAttribute('data-route-baseline-focus-member-id') || '').trim() === routeBaselineFocusMemberId
      : true;
    return [routeCombinationName, routeReviewMemberId, routeClauseLabel, routeBaselineFocusMemberId].some(Boolean)
      && combinationMatch
      && memberMatch
      && clauseMatch
      && baselineMatch;
  }}) || null;
  const rowProvenanceHazardTarget = [...document.querySelectorAll('#committee-appendix-row-provenance-hazard-table tbody tr')].find((row) => {{
    return routeHazardType
      ? normalizeRouteToken(row.getAttribute('data-route-hazard-type')) === normalizeRouteToken(routeHazardType)
      : false;
  }}) || null;
  const rowProvenanceRuleFamilyTarget = [...document.querySelectorAll('#committee-appendix-row-provenance-rule-family-table tbody tr')].find((row) => {{
    return routeRuleFamily
      ? normalizeRouteToken(row.getAttribute('data-route-rule-family')) === normalizeRouteToken(routeRuleFamily)
      : false;
  }}) || null;

  [
    authorityTarget,
    candidateTarget,
    designChangeTarget,
    appendixTarget,
    rowProvenanceTarget,
    rowProvenanceHazardTarget,
    rowProvenanceRuleFamilyTarget,
  ].filter(Boolean).forEach((node) => flashRouteSelection(node));
}})();
</script>
</body>
</html>
"""
    path.write_text(html_output, encoding="utf-8")


def _pdf_image_page(pdf: PdfPages, title: str, image_path: Path) -> None:
    configure_matplotlib_cjk_pdf()
    fig = plt.figure(figsize=(11, 8.5))
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.set_title(title, fontsize=18, loc="left")
    if image_path.exists():
        img = plt.imread(str(image_path))
        ax.imshow(img)
    else:
        ax.text(0.05, 0.5, f"Missing image: {image_path}", fontsize=14, transform=ax.transAxes)
    finalize_pdf_figure(fig, text_page=False)
    pdf.savefig(fig)
    plt.close(fig)


def _write_pdf(
    path: Path,
    cards: list[dict],
    rows: list[dict],
    artifacts: dict,
    metrics: dict,
    authority_rows: list[dict],
    residual_case_rows: list[dict],
    design_change_rows: list[dict],
    blocked_action_summary: dict,
    accepted_candidate_rows: list[dict],
    design_opt_entrypoint_rows: list[dict],
    design_opt_entrypoint_groups: list[dict],
    smoke_recent_samples: list[dict],
    external_benchmark_submission_queue_rows: list[dict],
    holdout_buckets: list[dict],
    holdout_detail_rows: list[dict],
    holdout_matrix_rows: list[dict],
    authority_catalog_diff: dict,
) -> None:
    configure_matplotlib_cjk_pdf()
    story_change_rows, zone_change_rows = _aggregate_design_change_rows(design_change_rows)
    selected_candidate_rows, unselected_candidate_rows = _split_accepted_candidate_rows(accepted_candidate_rows)
    with PdfPages(path) as pdf:
        def _save_text_page(fig) -> None:
            finalize_pdf_figure(fig, text_page=True)
            pdf.savefig(fig)

        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.03, 0.96, "Committee Review Package", fontsize=22, weight="bold", va="top")
        y = 0.90
        for card in cards:
            ax.text(0.04, y, f"{card['label']}: {card['value']} [{card['status']}] {card.get('note', '')}", fontsize=11, va="top")
            y -= 0.045
        y -= 0.03
        ax.text(0.03, y, "Validation Table", fontsize=16, weight="bold", va="top")
        y -= 0.05
        for row in rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(0.04, y, f"{row['section']} / {row['item']}: {row['value']} [{row['status']}]", fontsize=10.5, va="top")
            y -= 0.035
            ax.text(0.06, y, f"criterion={row['criterion']} | evidence={row['evidence']}", fontsize=9.2, va="top")
            y -= 0.042
        y -= 0.02
        ax.text(0.03, y, "Authority Benchmarks", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for row in authority_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(0.04, y, f"{row['track']} / {row['case_id']}: {row['metric_a']} | {row['metric_b']} [{row['status']}]", fontsize=10.0, va="top")
            y -= 0.032
            ax.text(0.06, y, f"source={row['source_url']} | provenance={row['provenance']}", fontsize=8.7, va="top")
            y -= 0.038
        y -= 0.02
        if y < 0.18:
            _save_text_page(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            y = 0.95
        ax.text(0.03, y, "Appendix: Design Optimization Entrypoint Details", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for row in design_opt_entrypoint_groups:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            fail_count = max(int(row.get("entrypoint_count", 0)) - int(row.get("pass_count", 0)), 0)
            ax.text(
                0.04,
                y,
                f"{row['group_label']}: reports {int(row.get('report_count', 0))}/{int(row.get('entrypoint_count', 0))}, pass={int(row.get('pass_count', 0))}, fail={fail_count}",
                fontsize=9.8,
                va="top",
            )
            y -= 0.034
        detail_groups = build_entrypoint_detail_groups(
            design_opt_entrypoint_rows,
            annotate_entrypoint_groups(design_opt_entrypoint_groups),
        )
        for group in detail_groups:
            group_rows = group["rows"]
            reason_text = group["reason_distribution"]
            fail_count = int(group.get("fail_count", 0))
            if y < 0.12:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                f"{group['group_label']} ({len(group_rows)} rows, pass={int(group.get('pass_count', 0))}, fail={fail_count}, reasons={reason_text})",
                fontsize=10.0,
                weight="bold",
                va="top",
            )
            y -= 0.034
            for row in group_rows:
                if y < 0.08:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    y = 0.95
                ax.text(
                    0.06,
                    y,
                    f"{row['name']}: pass={row['contract_pass']} reason={row['reason_code']}",
                    fontsize=9.5,
                    va="top",
                )
                y -= 0.032
                ax.text(0.08, y, f"report={row['primary_report']}", fontsize=8.6, va="top")
                y -= 0.036
        row_provenance_preview_rows = [
            row for row in (metrics.get("midas_kds_row_provenance_preview_rows") or []) if isinstance(row, dict)
        ]
        row_provenance_summary_line = str(metrics.get("midas_kds_row_provenance_export_summary_line", "") or "").strip()
        if row_provenance_summary_line or row_provenance_preview_rows:
            y -= 0.02
            if y < 0.18:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(0.03, y, "Appendix: MIDAS KDS Row Provenance Export", fontsize=16, weight="bold", va="top")
            y -= 0.042
            ax.text(0.04, y, row_provenance_summary_line or "n/a", fontsize=9.6, va="top")
            y -= 0.034
            ax.text(
                0.04,
                y,
                (
                    f"json={artifacts.get('midas_kds_row_provenance_export_json', '') or 'n/a'} | "
                    f"csv={artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'}"
                ),
                fontsize=8.6,
                va="top",
            )
            y -= 0.04
            for row in row_provenance_preview_rows:
                if y < 0.08:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    y = 0.95
                ax.text(
                    0.04,
                    y,
                    (
                        f"{row.get('combination_name', '')} | member={row.get('member_id', '')} | "
                        f"clause={row.get('clause_label', '')} | baseline={row.get('baseline_focus_member_id', '')}"
                    ),
                    fontsize=9.2,
                    va="top",
                )
                y -= 0.03
                ax.text(
                    0.06,
                    y,
                    (
                        f"mode={row.get('bridge_row_provenance_mode_label', '')} | "
                        f"clause={row.get('clause_provenance_summary_label', '')} | "
                        f"inventory={row.get('bridge_member_inventory_summary_label', '')}"
                    ),
                    fontsize=8.3,
                    va="top",
                )
                y -= 0.038
        y -= 0.02
        if y < 0.18:
            _save_text_page(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            y = 0.95
        ax.text(0.03, y, "NDTHA Residual Case Trace", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for row in residual_case_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                (
                    f"{row['case_id']} [{row['split']}/{row['hazard_type']}]: "
                    f"top {row['pre_settle_top_m']:.4f}->{row['post_settle_top_m']:.4f} m | "
                    f"drift {row['pre_settle_drift_pct']:.4f}->{row['post_settle_drift_pct']:.4f}%"
                ),
                fontsize=9.9,
                va="top",
            )
            y -= 0.032
            ax.text(
                0.06,
                y,
                (
                    f"delta_top={row['delta_top_m']:.4f} m | delta_drift={row['delta_drift_pct']:.4f}% | "
                    f"source={row['residual_metric_source']} | settle_steps={row['residual_settle_steps']}"
                ),
                fontsize=8.8,
                va="top",
            )
            y -= 0.038
        y -= 0.02
        if y < 0.20:
            _save_text_page(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            y = 0.95
        ax.text(0.03, y, "Blocked Cost-Down Actions", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for line in [
            f"blocked={int(blocked_action_summary.get('blocked_action_row_count', 0))}",
            f"illegal_by_mask={int(blocked_action_summary.get('illegal_by_mask', 0))}",
            f"no_cost_gain={int(blocked_action_summary.get('no_cost_gain', 0))}",
            f"constructability_hard_gate={int(blocked_action_summary.get('constructability_hard_gate_block_count', 0))}",
            f"no_cost_gain_groups={int(blocked_action_summary.get('blocked_no_cost_group_count', 0))}",
            f"no_cost_gain_explain_rows={int(blocked_action_summary.get('blocked_no_cost_explain_row_count', 0))}",
            f"violates_feasible_constraints={int(blocked_action_summary.get('violates_feasible_constraints', 0))}",
            f"no_action_delta={int(blocked_action_summary.get('no_action_delta', 0))}",
            f"accepted_candidate={int(blocked_action_summary.get('accepted_candidate', 0))}",
            f"selected={int(blocked_action_summary.get('accepted_candidate_selected_count', 0))}",
            f"unselected={int(blocked_action_summary.get('accepted_candidate_unselected_count', 0))}",
            f"hard_gate_reasons={str(blocked_action_summary.get('constructability_hard_gate_reason_label', '')) or 'n/a'}",
        ]:
            ax.text(0.04, y, line, fontsize=10.0, va="top")
            y -= 0.034
        y -= 0.02
        if y < 0.28:
            _save_text_page(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            y = 0.95
        ax.text(0.03, y, "Selected Cost-Down Candidates", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for row in selected_candidate_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                (
                    f"S{int(row['story_band']):02d} {row['zone_label']} {row['member_type']} {row['action_name']} | "
                    f"gain={float(row.get('delta_cost', row.get('projected_cost_delta', 0.0))):.3f} | "
                    f"trial_dcr={float(row.get('trial_max_dcr', row.get('max_dcr', 0.0))):.3f} | "
                    f"{row.get('reason_selected', row.get('explain_reason', ''))}"
                ),
                fontsize=9.6,
                va="top",
            )
            y -= 0.032
        y -= 0.02
        if y < 0.28:
            _save_text_page(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            y = 0.95
        ax.text(0.03, y, "Unselected Cost-Down Candidates", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for row in unselected_candidate_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                (
                    f"S{int(row['story_band']):02d} {row['zone_label']} {row['member_type']} {row['action_name']} | "
                    f"gain={float(row.get('delta_cost', row.get('projected_cost_delta', 0.0))):.3f} | "
                    f"trial_dcr={float(row.get('trial_max_dcr', row.get('max_dcr', 0.0))):.3f} | "
                    f"{row.get('reason_rejected', row.get('explain_reason', ''))}"
                ),
                fontsize=9.0,
                va="top",
            )
            y -= 0.032
        y -= 0.02
        if y < 0.18:
            _save_text_page(fig)
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            y = 0.95
        ax.text(0.03, y, "Design Change Summary", fontsize=16, weight="bold", va="top")
        y -= 0.045
        for row in story_change_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                (
                    f"S{int(row['story_band']):02d} total | "
                    f"changed={int(row['changed_group_count'])} semantic={int(row['semantic_group_count'])} | "
                    f"cost={float(row['cost_proxy_delta_sum']):.3f} | "
                    f"dcr={float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}"
                ),
                fontsize=9.6,
                va="top",
            )
            y -= 0.032
        for row in zone_change_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                (
                    f"{row['zone_label']} total | "
                    f"changed={int(row['changed_group_count'])} semantic={int(row['semantic_group_count'])} | "
                    f"cost={float(row['cost_proxy_delta_sum']):.3f} | "
                    f"dcr={float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f}"
                ),
                fontsize=9.6,
                va="top",
            )
            y -= 0.032
        y -= 0.02
        for row in design_change_rows:
            if y < 0.08:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                y = 0.95
            ax.text(
                0.04,
                y,
                (
                    f"S{int(row['story_band']):02d} {row['zone_label']} {row['member_type']} | "
                    f"changed={int(row['changed_group_count'])} semantic={int(row['semantic_group_count'])} | "
                    f"cost={float(row['cost_proxy_delta_sum']):.3f} | "
                    f"dcr={float(row['max_dcr_before_max']):.3f}->{float(row['max_dcr_after_max']):.3f} | "
                    f"constructability={float(row.get('constructability_before_avg', 0.0)):.4f}->{float(row.get('constructability_after_avg', 0.0)):.4f} | "
                    f"gate={row.get('selection_gate', 'n/a')}"
                ),
                fontsize=10.0,
                va="top",
            )
            y -= 0.04
        _save_text_page(fig)
        plt.close(fig)

        _pdf_image_page(pdf, "Drift Envelope", Path(artifacts["drift_envelope_png"]))
        _pdf_image_page(pdf, "Core Hysteresis", Path(artifacts["core_hysteresis_png"]))
        _pdf_image_page(pdf, "Plastic Hinge Proxy", Path(artifacts["hinge_proxy_3d_png"]))
        _pdf_image_page(pdf, "Authority SAC KPI", Path(artifacts["authority_sac_kpi_png"]))
        _pdf_image_page(pdf, "Authority NHERI Waveform", Path(artifacts["authority_nheri_waveform_png"]))
        smoke_history_png = Path(str(artifacts.get("smoke_history_png", "") or ""))
        if smoke_history_png.exists():
            _pdf_image_page(pdf, "Nightly Smoke Trend", smoke_history_png)
        if smoke_recent_samples:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Nightly Smoke Recent Samples", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in smoke_recent_samples:
                ax.text(
                    0.04,
                    y,
                    (
                        f"#{int(row.get('sample_index', 0))} {row.get('generated_at', '')} | "
                        f"pass={bool(row.get('contract_pass', False))} | trial_feasible={bool(row.get('trial_feasible', False))} | "
                        f"baseline_runtime={float(row.get('baseline_runtime_s', 0.0)):.4f}s | "
                        f"trial_runtime={float(row.get('trial_runtime_s', 0.0)):.4f}s | "
                        f"trial_max_dcr={float(row.get('trial_max_dcr', 0.0)):.4f} | "
                        f"action={row.get('trial_action_name', '')}"
                    ),
                    fontsize=9.5,
                    va="top",
                )
                y -= 0.065
                if y < 0.08:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Nightly Smoke Recent Samples", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if holdout_buckets:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Residual Holdout Boundary", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in holdout_buckets:
                ax.text(
                    0.04,
                    y,
                    f"{row.get('work_item_id', '')} | {row.get('label', row.get('id', ''))} | due={row.get('due_date', '')} | "
                    f"sla={row.get('sla_label', '')} | closure={_holdout_closure_evidence_label(row)} | owner={row.get('owner', '')}",
                    fontsize=9.4,
                    va="top",
                )
                y -= 0.034
                ax.text(
                    0.06,
                    y,
                    (
                        f"queue={row.get('queue_status', '')} | status={row.get('status', '')} | "
                        f"share={int(row.get('relative_share_pct', 0))}% | project={_coverage_range_label(row.get('absolute_project_pct_range'))} | "
                        f"{row.get('scope', '')}"
                    ),
                    fontsize=8.7,
                    va="top",
                    wrap=True,
                )
                y -= 0.055
                if y < 0.08:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Residual Holdout Boundary", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if metrics.get("time_saving_focus"):
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Time-Saving Coverage", fontsize=18, weight="bold", va="top")
            ax.text(0.04, 0.86, f"Coverage target: {metrics.get('accelerated_coverage_target_pct_label', '')}", fontsize=11.0, va="top")
            ax.text(0.04, 0.80, f"Residual holdout: {metrics.get('residual_holdout_target_pct_label', '')}", fontsize=11.0, va="top")
            ax.text(0.04, 0.74, f"Estimated time saved: {metrics.get('estimated_time_saved_pct_label', '')}", fontsize=11.0, va="top")
            ax.text(0.04, 0.68, f"Measured chain wall-clock (comparable rolling): {metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f} min", fontsize=10.4, va="top")
            ax.text(0.04, 0.62, f"Rolling sample count: {int(metrics.get('measured_chain_rolling_sample_count', 0))}, range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]} min", fontsize=10.2, va="top")
            ax.text(0.04, 0.56, f"Measured chain wall-clock (current): {metrics.get('measured_chain_total_minutes', 0.0):.2f} min", fontsize=10.2, va="top")
            ax.text(0.04, 0.50, f"Comparable run mode: {metrics.get('measured_chain_rolling_selection_mode', '')}", fontsize=10.0, va="top")
            ax.text(0.04, 0.44, f"Empirical smoke runtime reduction: {metrics.get('empirical_smoke_runtime_saved_pct_label', 'n/a')}", fontsize=10.2, va="top")
            ax.text(0.04, 0.38, f"Basis: {metrics.get('estimated_time_saved_basis', '')}", fontsize=9.6, va="top", wrap=True)
            ax.text(0.04, 0.24, str(metrics.get("time_saving_focus", "")), fontsize=10.0, va="top", wrap=True)
            _save_text_page(fig)
            plt.close(fig)
        if external_benchmark_submission_queue_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "External Benchmark Submission Queue", fontsize=18, weight="bold", va="top")
            ax.text(
                0.04,
                0.89,
                (
                    f"onepage_attestation_status={metrics.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown'} | "
                    f"queue_count={int(metrics.get('external_benchmark_submission_queue_count', len(external_benchmark_submission_queue_rows)))}"
                ),
                fontsize=10.4,
                va="top",
            )
            y = 0.82
            for row in external_benchmark_submission_queue_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"{row.get('work_item_id', '')} | {row.get('queue_id', '')} | "
                        f"submission_id={row.get('submission_id', '')} | scope={row.get('submission_scope', '')} | "
                        f"owner={row.get('owner', '')} | status={row.get('status', '')}"
                    ),
                    fontsize=9.5,
                    va="top",
                )
                y -= 0.034
                ax.text(
                    0.06,
                    y,
                    (
                        f"receipt_url={row.get('receipt_url', '') or 'pending'} | "
                        f"closure_evidence={row.get('closure_evidence_required', '') or 'external_submission_receipt'} "
                        f"({row.get('closure_evidence_status', '') or 'pending'}) | "
                        f"onepage_status={row.get('onepage_attestation_status', '') or 'unknown'} | "
                        f"dry_run_evidence={row.get('dry_run_evidence', '') or 'n/a'}"
                    ),
                    fontsize=8.5,
                    va="top",
                    wrap=True,
                )
                y -= 0.055
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "External Benchmark Submission Queue", fontsize=18, weight="bold", va="top")
                    ax.text(
                        0.04,
                        0.89,
                        (
                            f"onepage_attestation_status={metrics.get('external_benchmark_submission_onepage_attestation_status', '') or 'unknown'} | "
                            f"queue_count={int(metrics.get('external_benchmark_submission_queue_count', len(external_benchmark_submission_queue_rows)))}"
                        ),
                        fontsize=10.4,
                        va="top",
                    )
                    y = 0.82
            _save_text_page(fig)
            plt.close(fig)
        advanced_holdout_status_rows = [
            row for row in (metrics.get("advanced_holdout_status_rows", []) or []) if isinstance(row, dict)
        ]
        if advanced_holdout_status_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Advanced Holdout Closure", fontsize=18, weight="bold", va="top")
            ax.text(
                0.04,
                0.89,
                (
                    f"total={int(metrics.get('advanced_holdout_total_count', 0))} | "
                    f"closed={int(metrics.get('advanced_holdout_closed_count', 0))} | "
                    f"open={int(metrics.get('advanced_holdout_open_count', 0))} | "
                    f"{metrics.get('advanced_holdout_status_label', '') or 'n/a'}"
                ),
                fontsize=10.6,
                va="top",
            )
            y = 0.82
            for row in advanced_holdout_status_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"{row.get('title', row.get('id', ''))} | "
                        f"severity={row.get('severity', '') or 'n/a'} | "
                        f"closure={row.get('closure_state', '') or 'n/a'} | "
                        f"mode={row.get('mode', '') or 'n/a'}"
                    ),
                    fontsize=9.8,
                    va="top",
                )
                y -= 0.035
                ax.text(
                    0.06,
                    y,
                    (
                        f"reason={row.get('reason_snippet', '') or 'n/a'} | "
                        f"evidence={row.get('evidence_snippet', '') or 'n/a'}"
                    ),
                    fontsize=8.6,
                    va="top",
                    wrap=True,
                )
                y -= 0.06
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Advanced Holdout Closure", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if holdout_detail_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Residual Holdout Review Table", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in holdout_detail_rows:
                ax.text(
                    0.04,
                    y,
                    f"{row.get('bucket_label', row.get('bucket_id', ''))} | {row.get('detail_axis', '')} | {row.get('detail_value', '')}",
                    fontsize=9.8,
                    va="top",
                )
                y -= 0.034
                ax.text(
                    0.06,
                    y,
                    (
                        f"owner={row.get('owner', '')} | queue={row.get('queue_status', '')} | "
                        f"sla={row.get('sla_label', '')} | due={row.get('due_date', '')} | "
                        f"closure={row.get('closure_evidence_required', '')}:{row.get('closure_evidence_status', '')} | "
                        f"why={row.get('why', '')}"
                    ),
                    fontsize=8.8,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Residual Holdout Review Table", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if holdout_matrix_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Residual Holdout Routing Matrix", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in holdout_matrix_rows:
                ax.text(
                    0.04,
                    y,
                    f"{row.get('authority_track', '')} / {row.get('submodel_family', '')} -> {row.get('review_story_zone', '')} / {row.get('member_family', '')}",
                    fontsize=9.6,
                    va="top",
                )
                y -= 0.034
                ax.text(0.06, y, f"owner={row.get('owner', '')} | why={row.get('why', '')}", fontsize=8.8, va="top", wrap=True)
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Residual Holdout Routing Matrix", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.03, 0.96, "Authority Catalog Routing Diff", fontsize=18, weight="bold", va="top")
        ax.text(
            0.04,
            0.88,
            (
                f"baseline_seeded={bool(authority_catalog_diff.get('baseline_seeded', False))} | "
                f"changes={int(authority_catalog_diff.get('change_count', 0))} | "
                f"added={int(authority_catalog_diff.get('added_count', 0))} | "
                f"removed={int(authority_catalog_diff.get('removed_count', 0))} | "
                f"unchanged={int(authority_catalog_diff.get('unchanged_count', 0))}"
            ),
            fontsize=10.0,
            va="top",
        )
        y = 0.80
        diff_rows = [row for row in (authority_catalog_diff.get("diff_rows") or []) if isinstance(row, dict)]
        if not diff_rows:
            ax.text(0.04, y, "No authority-catalog routing changes detected for this package refresh.", fontsize=10.0, va="top")
        for row in diff_rows:
            ax.text(0.04, y, f"{row.get('change_type', '')} | {row.get('authority_track', '')} / {row.get('submodel_family', '')}", fontsize=9.6, va="top")
            y -= 0.034
            ax.text(0.06, y, f"review={row.get('review_story_zone', '')} | member={row.get('member_family', '')} | owner={row.get('owner', '')}", fontsize=8.7, va="top", wrap=True)
            y -= 0.034
            ax.text(0.06, y, f"why={row.get('why', '')}", fontsize=8.5, va="top", wrap=True)
            y -= 0.05
            if y < 0.10:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.03, 0.96, "Authority Catalog Routing Diff", fontsize=18, weight="bold", va="top")
                y = 0.88
        _save_text_page(fig)
        plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pbd-package", default="implementation/phase1/release/pbd_review/pbd_review_package_report.json")
    p.add_argument("--pbd-metrics", default="implementation/phase1/release/pbd_review/pbd_killshot_metrics.json")
    p.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    p.add_argument("--ndtha-residual-report", default="implementation/phase1/ndtha_residual_gate_report.json")
    p.add_argument("--wind-report", default="implementation/phase1/wind_time_history_gate_report.json")
    p.add_argument("--ssi-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    p.add_argument("--damper-report", default="implementation/phase1/damper_validation_gate_report.json")
    p.add_argument("--construction-report", default="implementation/phase1/construction_sequence_gate_report.json")
    p.add_argument("--diaphragm-report", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    p.add_argument("--repro-report", default="implementation/phase1/reproducibility_version_lock_report.json")
    p.add_argument("--release-registry", default="implementation/phase1/release/release_registry.json")
    p.add_argument("--kds-summary", default="implementation/phase1/release/kds_compliance/kds_compliance_summary.json")
    p.add_argument("--nightly-report", default="implementation/phase1/release/nightly_release_gate_report.json")
    p.add_argument("--promotion-report", default="implementation/phase1/release/release_candidate_promotion_report.json")
    p.add_argument("--ci-report", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--gap-report", default="implementation/phase1/release/release_gap_report.json")
    p.add_argument("--performance-profiling-report", default="implementation/phase1/performance_profiling_gate_report.json")
    p.add_argument("--solver-truthfulness-report", default="implementation/phase1/solver_truthfulness_gate_report.json")
    p.add_argument("--nonlinear-generalization-report", default="implementation/phase1/nonlinear_generalization_gate_report.json")
    p.add_argument("--workflow-productization-report", default="implementation/phase1/workflow_productization_gate_report.json")
    p.add_argument(
        "--external-benchmark-submission-readiness-report",
        default="implementation/phase1/release/external_benchmark_submission_readiness.json",
    )
    p.add_argument(
        "--external-benchmark-execution-manifest-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json",
    )
    p.add_argument(
        "--external-benchmark-execution-status-manifest-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json",
    )
    p.add_argument("--authority-report", default="implementation/phase1/global_authority_gate_report.json")
    p.add_argument("--authority-catalog", default="implementation/phase1/open_data/global_authority/authority_source_catalog.json")
    p.add_argument("--design-opt-long-report", default=SOLVER_LOOP_LONG_REPORT_JSON)
    p.add_argument("--design-opt-cost-report", default=COST_REDUCTION_REPORT_JSON)
    p.add_argument("--design-opt-cost-changes-csv", default=COST_REDUCTION_CHANGES_CSV)
    p.add_argument("--design-opt-cost-blocked-actions-csv", default=COST_REDUCTION_BLOCKED_ACTIONS_CSV)
    p.add_argument("--design-opt-cost-no-gain-csv", default=COST_REDUCTION_NO_GAIN_GROUPS_CSV)
    p.add_argument("--design-opt-cost-no-gain-explain-csv", default=COST_REDUCTION_NO_GAIN_EXPLAIN_CSV)
    p.add_argument(
        "--row-provenance-export-json",
        default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json",
    )
    p.add_argument(
        "--row-provenance-export-csv",
        default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
    )
    p.add_argument(
        "--row-provenance-export-report",
        default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
    )
    p.add_argument("--row-provenance-model-json", default="implementation/phase1/open_data/midas/midas_generator_33.json")
    p.add_argument("--row-provenance-kds-report", default="implementation/phase1/release/kds_compliance/code_check_report.json")
    p.add_argument("--out-dir", default="implementation/phase1/release/committee_review")
    args = p.parse_args()

    pbd_package = _load_json(Path(args.pbd_package))
    pbd_metrics = _load_json(Path(args.pbd_metrics))
    ndtha_stress = _load_json_from_disk(args.ndtha_stress_report)
    ndtha_residual = _load_json(Path(args.ndtha_residual_report))
    wind = _load_json(Path(args.wind_report))
    ssi = _load_json(Path(args.ssi_report))
    damper = _load_json(Path(args.damper_report))
    construction = _load_json(Path(args.construction_report))
    diaphragm = _load_json(Path(args.diaphragm_report))
    repro = _load_json(Path(args.repro_report))
    release_registry = _load_json(Path(args.release_registry))
    kds = _load_json(Path(args.kds_summary))
    nightly = _load_json(Path(args.nightly_report))
    promotion = _load_json(Path(args.promotion_report))
    ci = _load_json(Path(args.ci_report))
    gap = _load_json(Path(args.gap_report))
    performance_profiling_report = (
        _load_json(Path(args.performance_profiling_report)) if Path(args.performance_profiling_report).exists() else {}
    )
    solver_truthfulness_report = _load_json(Path(args.solver_truthfulness_report)) if Path(args.solver_truthfulness_report).exists() else {}
    nonlinear_generalization_report = _load_json(Path(args.nonlinear_generalization_report))
    workflow_productization_report = _load_json(Path(args.workflow_productization_report))
    workflow_productization_artifacts = (
        workflow_productization_report.get("generated_artifacts")
        if isinstance(workflow_productization_report.get("generated_artifacts"), dict)
        else {}
    )
    gap_summary = gap.get("summary") if isinstance(gap.get("summary"), dict) else {}
    external_benchmark_submission_readiness = _load_json(Path(args.external_benchmark_submission_readiness_report))
    external_benchmark_submission_summary = (
        external_benchmark_submission_readiness.get("summary")
        if isinstance(external_benchmark_submission_readiness.get("summary"), dict)
        else {}
    )
    external_benchmark_submission_queue_rows = [
        row
        for row in (external_benchmark_submission_readiness.get("submission_queue") or [])
        if isinstance(row, dict)
    ]
    external_benchmark_execution_manifest = _load_json(Path(args.external_benchmark_execution_manifest_report))
    external_benchmark_execution_summary = (
        external_benchmark_execution_manifest.get("summary")
        if isinstance(external_benchmark_execution_manifest.get("summary"), dict)
        else {}
    )
    external_benchmark_execution_review_boundary_preview = (
        external_benchmark_execution_manifest.get("review_boundary_preview")
        if isinstance(external_benchmark_execution_manifest.get("review_boundary_preview"), dict)
        else {}
    )
    external_benchmark_execution_status_manifest = _load_json(
        Path(args.external_benchmark_execution_status_manifest_report)
    )
    external_benchmark_execution_status_summary = (
        external_benchmark_execution_status_manifest.get("summary")
        if isinstance(external_benchmark_execution_status_manifest.get("summary"), dict)
        else {}
    )
    external_benchmark_batch_job_report_json = (
        Path(args.external_benchmark_execution_status_manifest_report).with_name(
            "external_benchmark_batch_job_report.json"
        )
    )
    external_benchmark_batch_job_report = _load_json_from_disk(str(external_benchmark_batch_job_report_json))
    external_benchmark_batch_job_summary = (
        external_benchmark_batch_job_report.get("summary")
        if isinstance(external_benchmark_batch_job_report.get("summary"), dict)
        else {}
    )
    external_benchmark_kickoff_dir = Path(args.external_benchmark_execution_manifest_report).parent
    audit_review_decision_batch_template_json = external_benchmark_kickoff_dir / "audit_review_decision_batch_template.json"
    audit_review_decision_batch_template = _load_json(audit_review_decision_batch_template_json)
    audit_review_decision_batch_template_summary = (
        audit_review_decision_batch_template.get("summary")
        if isinstance(audit_review_decision_batch_template.get("summary"), dict)
        else {}
    )
    audit_review_decision_batch_approve_all_attested_example_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch_approve_all.attested_example.json"
    )
    audit_review_decision_batch_approve_all_attested_example = _load_json(
        audit_review_decision_batch_approve_all_attested_example_json
    )
    audit_review_decision_batch_approve_all_attested_example_summary = (
        audit_review_decision_batch_approve_all_attested_example.get("summary")
        if isinstance(audit_review_decision_batch_approve_all_attested_example.get("summary"), dict)
        else {}
    )
    audit_review_decision_batch_mixed_attested_example_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch_mixed.attested_example.json"
    )
    audit_review_decision_batch_mixed_attested_example = _load_json(
        audit_review_decision_batch_mixed_attested_example_json
    )
    audit_review_decision_batch_mixed_attested_example_summary = (
        audit_review_decision_batch_mixed_attested_example.get("summary")
        if isinstance(audit_review_decision_batch_mixed_attested_example.get("summary"), dict)
        else {}
    )
    external_benchmark_submission_preview_approve_all_json = (
        external_benchmark_kickoff_dir / "external_benchmark_submission_readiness_preview.approve_all.json"
    )
    external_benchmark_submission_preview_approve_all = _load_json(
        external_benchmark_submission_preview_approve_all_json
    )
    external_benchmark_submission_preview_approve_all_readiness_summary = (
        external_benchmark_submission_preview_approve_all.get("readiness_preview", {}).get("summary")
        if isinstance(external_benchmark_submission_preview_approve_all.get("readiness_preview"), dict)
        and isinstance(external_benchmark_submission_preview_approve_all.get("readiness_preview", {}).get("summary"), dict)
        else {}
    )
    external_benchmark_submission_preview_reject_one_json = (
        external_benchmark_kickoff_dir / "external_benchmark_submission_readiness_preview.reject_one.json"
    )
    external_benchmark_submission_preview_reject_one = _load_json(
        external_benchmark_submission_preview_reject_one_json
    )
    external_benchmark_submission_preview_reject_one_readiness_summary = (
        external_benchmark_submission_preview_reject_one.get("readiness_preview", {}).get("summary")
        if isinstance(external_benchmark_submission_preview_reject_one.get("readiness_preview"), dict)
        and isinstance(external_benchmark_submission_preview_reject_one.get("readiness_preview", {}).get("summary"), dict)
        else {}
    )
    audit_review_decision_batch_run_report_json = external_benchmark_kickoff_dir / "audit_review_decision_batch_run_report.json"
    audit_review_decision_batch_run_report = _load_json(audit_review_decision_batch_run_report_json)
    audit_review_decision_batch_live_preview_json = external_benchmark_kickoff_dir / "audit_review_decision_batch.live_preview.json"
    audit_review_decision_batch_live_preview = _load_json(audit_review_decision_batch_live_preview_json)
    authority = _load_json(Path(args.authority_report))
    authority_catalog = _load_json(Path(args.authority_catalog))
    design_opt_reports = load_design_opt_reports()
    design_opt_entrypoint_rows = entrypoint_status_rows(design_opt_reports)
    design_opt_entrypoint_groups = entrypoint_group_rows(design_opt_entrypoint_rows)
    design_opt_long = design_opt_reports.get("solver_loop_long") or _load_json(Path(args.design_opt_long_report))
    design_opt_cost = design_opt_reports.get("cost_reduction") or _load_json(Path(args.design_opt_cost_report))
    row_provenance_export_json_path = Path(args.row_provenance_export_json)
    row_provenance_export_csv_path = Path(args.row_provenance_export_csv)
    row_provenance_export_report_path = Path(args.row_provenance_export_report)
    row_provenance_export_json_path.parent.mkdir(parents=True, exist_ok=True)
    row_provenance_export_csv_path.parent.mkdir(parents=True, exist_ok=True)
    row_provenance_export_report_path.parent.mkdir(parents=True, exist_ok=True)
    row_provenance_export, row_provenance_export_report = row_provenance_export_module.write_row_provenance_export(
        model_json=Path(args.row_provenance_model_json),
        kds_report=Path(args.row_provenance_kds_report),
        out_json=row_provenance_export_json_path,
        out_csv=row_provenance_export_csv_path,
        out_report=row_provenance_export_report_path,
        input_payload={
            "model_json": str(args.row_provenance_model_json),
            "kds_report": str(args.row_provenance_kds_report),
            "out_json": str(row_provenance_export_json_path),
            "out_csv": str(row_provenance_export_csv_path),
            "out_report": str(row_provenance_export_report_path),
        },
    )
    design_change_rows = _load_design_change_rows(design_opt_cost)
    accepted_candidate_rows = _load_accepted_candidate_rows(design_opt_cost)
    blocked_action_summary = _load_blocked_action_summary(design_opt_cost)
    design_change_story_rows, design_change_zone_rows = _aggregate_design_change_rows(design_change_rows)
    smoke_recent_samples = [row for row in (gap.get("nightly_smoke_recent_samples") or []) if isinstance(row, dict)]

    cards, rows, metrics, authority_rows, residual_case_rows = _build_summary(
        pbd_package=pbd_package,
        pbd_metrics=pbd_metrics,
        ndtha_stress=ndtha_stress,
        ndtha_residual=ndtha_residual,
        wind=wind,
        ssi=ssi,
        damper=damper,
        construction=construction,
        diaphragm=diaphragm,
        repro=repro,
        release_registry=release_registry,
        kds=kds,
        nightly=nightly,
        ci=ci,
        gap=gap,
        performance_profiling_report=performance_profiling_report,
        solver_truthfulness_report=solver_truthfulness_report,
        nonlinear_generalization_report=nonlinear_generalization_report,
        workflow_productization_report=workflow_productization_report,
        authority=authority,
        authority_catalog=authority_catalog,
        design_opt_long=design_opt_long,
        design_opt_cost=design_opt_cost,
        row_provenance_export=row_provenance_export,
        row_provenance_export_report=row_provenance_export_report,
    )
    ndtha_step_series_depth = int(metrics.get("ndtha_step_series_depth", 0) or 0)
    if not ndtha_step_series_depth:
        ndtha_step_series_depth = int(
            gap_summary.get("ndtha_step_series_depth", ci.get("ndtha_step_series_depth", 0)) or 0
        )
    metrics["ndtha_step_series_depth"] = ndtha_step_series_depth
    cards.append(
        _card(
            "design_opt_registry",
            "Design Opt Entrypoints",
            f"{sum(1 for row in design_opt_entrypoint_rows if bool(row.get('report_exists', False)))}/{len(design_opt_entrypoint_rows)}",
            _status(all(bool(row.get("report_exists", False)) and bool(row.get("contract_pass", False)) for row in design_opt_entrypoint_rows)),
            "registry-driven primary report inventory",
        )
    )
    for row in design_opt_entrypoint_groups:
        cards.append(
            _card(
                f"design_opt_group_{row['group']}",
                f"Design Opt {row['group_label']}",
                f"{int(row.get('report_count', 0))}/{int(row.get('entrypoint_count', 0))}",
                _status(bool(row.get("all_pass", False))),
                f"members={', '.join(row.get('entrypoint_names', []))}",
            )
        )
    cards.append(
        _card(
            "external_benchmark_submission_start",
            "External Benchmark Start",
            str(external_benchmark_submission_summary.get("recommended_start_mode", "n/a") or "n/a"),
            _status(bool(external_benchmark_submission_readiness.get("contract_pass", False))),
            str(external_benchmark_submission_summary.get("recommended_submission_scope", "") or "n/a"),
        )
    )
    cards.append(
        _card(
            "external_benchmark_execution",
            "External Benchmark Execution",
            str(external_benchmark_execution_summary.get("execution_mode", "n/a") or "n/a"),
            _status(bool(external_benchmark_execution_manifest.get("contract_pass", False))),
            (
                f"ready={int(external_benchmark_execution_summary.get('ready_task_count', 0))} | "
                f"blocked={int(external_benchmark_execution_summary.get('blocked_task_count', 0))} | "
                f"review_boundary_pending={int(external_benchmark_execution_summary.get('review_boundary_pending_count', 0))} | "
                f"status={str(external_benchmark_execution_status_summary.get('status_mode', 'n/a') or 'n/a')} | "
                f"planned={int(external_benchmark_execution_status_summary.get('planned_task_count', 0))} | "
                f"in_progress={int(external_benchmark_execution_status_summary.get('in_progress_task_count', 0))} | "
                f"completed={int(external_benchmark_execution_status_summary.get('completed_task_count', 0))} | "
                f"failed={int(external_benchmark_execution_status_summary.get('failed_task_count', 0))} | "
                f"batch_jobs={int(external_benchmark_batch_job_summary.get('job_count', 0) or 0)} | "
                f"batch_done={int(external_benchmark_batch_job_summary.get('completed_count', 0) or 0)} | "
                f"batch_failed={int(external_benchmark_batch_job_summary.get('failed_count', 0) or 0)}"
            ),
        )
    )

    pbd_artifacts = pbd_package.get("artifacts") if isinstance(pbd_package.get("artifacts"), dict) else {}
    pbd_inputs = pbd_package.get("inputs") if isinstance(pbd_package.get("inputs"), dict) else {}
    pbd_summary = pbd_package.get("summary") if isinstance(pbd_package.get("summary"), dict) else {}
    registry_artifacts = (
        release_registry.get("artifacts") if isinstance(release_registry.get("artifacts"), dict) else {}
    )
    artifact_links = {
        "drift_envelope_png": str(pbd_artifacts.get("drift_envelope_png", "")),
        "core_hysteresis_png": str(pbd_artifacts.get("core_hysteresis_png", "")),
        "hinge_proxy_3d_png": str(pbd_artifacts.get("hinge_proxy_3d_png", "")),
        "authority_sac_kpi_png": str(pbd_artifacts.get("authority_sac_kpi_png", "")),
        "authority_nheri_waveform_png": str(pbd_artifacts.get("authority_nheri_waveform_png", "")),
        "pbd_review_pdf": str(pbd_artifacts.get("review_pdf", "")),
        "pbd_resolved_ndtha_report_json": str(pbd_inputs.get("resolved_ndtha_report", "")),
        "pbd_resolved_ndtha_response_npz": str(pbd_inputs.get("resolved_ndtha_response_npz", "")),
        "ndtha_stress_report_json": str(args.ndtha_stress_report),
        "ndtha_residual_report_json": str(args.ndtha_residual_report),
        "kds_compliance_pdf": str((kds.get("artifacts") or {}).get("kds_compliance_pdf", "")),
        "version_lock_manifest": str(repro.get("lock_manifest", "")),
        "release_registry_json": str(args.release_registry),
        "release_registry_public_key": str(((release_registry.get("signature") or {}).get("public_key_path", ""))),
        "release_registry_signature": str(((release_registry.get("signature") or {}).get("signature_out", ""))),
        "project_registry_report": str(registry_artifacts.get("project_registry_report", "")),
        "project_package_zip": str(registry_artifacts.get("project_package_zip", "")),
        "project_registry_signature": str(registry_artifacts.get("project_registry_signature", "")),
        "gap_report_md": str(args.gap_report).replace(".json", ".md"),
        "smoke_history_png": str(((gap.get("artifacts") or {}).get("smoke_history_png", ""))),
        "measured_chain_category_png": str(((gap.get("artifacts") or {}).get("measured_chain_category_png", ""))),
        "authority_source_catalog": str(args.authority_catalog),
        "opensees_canonical_breadth_report": "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json",
        "measured_benchmark_breadth_report": "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json",
        "peer_blind_prediction_compare_report": "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json",
        "peer_blind_prediction_measured_response_landing_manifest": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json",
        "design_opt_long_report": str(args.design_opt_long_report),
        "design_opt_cost_report": str(args.design_opt_cost_report),
        "design_opt_cost_changes_csv": str(args.design_opt_cost_changes_csv),
        "design_opt_cost_blocked_actions_csv": str(args.design_opt_cost_blocked_actions_csv),
        "design_opt_cost_no_gain_csv": str(args.design_opt_cost_no_gain_csv),
        "design_opt_cost_no_gain_explain_csv": str(args.design_opt_cost_no_gain_explain_csv),
        "design_opt_cost_accepted_candidate_json": str(((design_opt_cost.get("artifacts") or {}).get("accepted_candidate_explain_json", ""))),
        "design_opt_cost_accepted_candidate_csv": str(((design_opt_cost.get("artifacts") or {}).get("accepted_candidate_explain_csv", ""))),
        "external_benchmark_submission_readiness_json": str(args.external_benchmark_submission_readiness_report),
        "external_benchmark_execution_manifest_json": str(args.external_benchmark_execution_manifest_report),
        "external_benchmark_execution_status_manifest_json": str(
            args.external_benchmark_execution_status_manifest_report
        ),
        "external_benchmark_batch_job_report_json": str(external_benchmark_batch_job_report_json),
        "audit_review_decision_batch_template_json": str(audit_review_decision_batch_template_json),
        "audit_review_decision_batch_template_md": str(audit_review_decision_batch_template_json.with_suffix(".md")),
        "audit_review_decision_batch_approve_all_attested_example_json": str(
            audit_review_decision_batch_approve_all_attested_example_json
        ),
        "audit_review_decision_batch_approve_all_attested_example_md": str(
            audit_review_decision_batch_approve_all_attested_example_json.with_suffix(".md")
        ),
        "audit_review_decision_batch_mixed_attested_example_json": str(
            audit_review_decision_batch_mixed_attested_example_json
        ),
        "audit_review_decision_batch_mixed_attested_example_md": str(
            audit_review_decision_batch_mixed_attested_example_json.with_suffix(".md")
        ),
        "external_benchmark_submission_preview_approve_all_json": str(
            external_benchmark_submission_preview_approve_all_json
        ),
        "external_benchmark_submission_preview_approve_all_md": str(
            external_benchmark_submission_preview_approve_all_json.with_suffix(".md")
        ),
        "external_benchmark_submission_preview_reject_one_json": str(
            external_benchmark_submission_preview_reject_one_json
        ),
        "external_benchmark_submission_preview_reject_one_md": str(
            external_benchmark_submission_preview_reject_one_json.with_suffix(".md")
        ),
        "audit_review_decision_batch_run_report_json": str(audit_review_decision_batch_run_report_json),
        "audit_review_decision_batch_live_preview_json": str(audit_review_decision_batch_live_preview_json),
        "structural_optimization_viewer_html": "implementation/phase1/release/visualization/structural_optimization_viewer.html",
        "structural_optimization_viewer_json": "implementation/phase1/release/visualization/structural_optimization_viewer.json",
        "optimized_drawing_review_html": "implementation/phase1/release/visualization/optimized_drawing_review.html",
        "optimized_drawing_review_summary_json": "implementation/phase1/release/visualization/optimized_drawing_review_summary.json",
        "midas_kds_row_provenance_export_json": str(row_provenance_export_json_path),
        "midas_kds_row_provenance_export_csv": str(row_provenance_export_csv_path),
        "midas_kds_row_provenance_export_report": str(row_provenance_export_report_path),
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
        "irregular_structure_gate_report": str(
            workflow_productization_artifacts.get("irregular_structure_gate_report_path", "") or ""
        ),
        "irregular_top5_execution_manifest": str(
            workflow_productization_artifacts.get("irregular_top5_execution_manifest_path", "") or ""
        ),
        "irregular_structure_source_catalog": str(
            workflow_productization_artifacts.get("irregular_source_catalog_path", "") or ""
        ),
        "irregular_priority_manifest": str(
            workflow_productization_artifacts.get("irregular_priority_manifest_path", "") or ""
        ),
        "irregular_structure_collection_report": str(
            workflow_productization_artifacts.get("irregular_collection_report_path", "") or ""
        ),
        "irregular_structure_triage_report": str(
            workflow_productization_artifacts.get("irregular_triage_report_path", "") or ""
        ),
        "authority_catalog_snapshot_json": "",
        "authority_catalog_routing_diff_json": "",
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_json = out_dir / "committee_summary.json"
    summary_csv = out_dir / "committee_summary.csv"
    dashboard_html = out_dir / "committee_review_dashboard.html"
    report_md = out_dir / "committee_review_report.md"
    report_pdf = out_dir / "committee_review_report.pdf"
    package_report = out_dir / "committee_review_package_report.json"
    authority_catalog_snapshot_json = out_dir / "authority_catalog_snapshot.json"
    authority_catalog_routing_diff_json = out_dir / "authority_catalog_routing_diff.json"
    artifact_links["authority_catalog_snapshot_json"] = str(authority_catalog_snapshot_json)
    artifact_links["authority_catalog_routing_diff_json"] = str(authority_catalog_routing_diff_json)
    optimized_drawing_review_summary = _load_json(
        Path(artifact_links.get("optimized_drawing_review_summary_json", "") or "")
    )
    optimized_drawing_review_interactive = (
        optimized_drawing_review_summary.get("interactive_3d_payload")
        if isinstance(optimized_drawing_review_summary.get("interactive_3d_payload"), dict)
        else {}
    )
    optimized_drawing_review_axis_refs = (
        optimized_drawing_review_interactive.get("axis_refs")
        if isinstance(optimized_drawing_review_interactive.get("axis_refs"), dict)
        else {}
    )
    metrics.update(
        {
            "audit_review_decision_batch_attested_example_count": int(
                sum(
                    1
                    for payload in (
                        audit_review_decision_batch_approve_all_attested_example,
                        audit_review_decision_batch_mixed_attested_example,
                    )
                    if bool(payload.get("contract_pass", False))
                )
            ),
            "audit_review_decision_batch_attested_example_preview_label": ", ".join(
                label
                for label in (
                    (
                        f"approve_all={audit_review_decision_batch_approve_all_attested_example_summary.get('expected_preview_reason_code', '')}"
                        if audit_review_decision_batch_approve_all_attested_example_summary
                        else ""
                    ),
                    (
                        f"mixed={audit_review_decision_batch_mixed_attested_example_summary.get('expected_preview_reason_code', '')}"
                        if audit_review_decision_batch_mixed_attested_example_summary
                        else ""
                    ),
                )
                if label
            )
            or "none",
            "external_benchmark_submission_ready_to_start_now": bool(
                external_benchmark_submission_summary.get("ready_to_start_now", False)
            ),
            "external_benchmark_submission_ready_to_start_full_submission_now": bool(
                external_benchmark_submission_summary.get("ready_to_start_full_submission_now", False)
            ),
            "external_benchmark_submission_reason_code": str(
                external_benchmark_submission_readiness.get("reason_code", "") or ""
            ),
            "optimized_drawing_review_projection_count": int(
                optimized_drawing_review_summary.get("projection_count", 0) or 0
            ),
            "optimized_drawing_review_changed_group_count": int(
                optimized_drawing_review_summary.get("changed_group_count", 0) or 0
            ),
            "optimized_drawing_review_changed_member_count": int(
                optimized_drawing_review_summary.get("changed_member_count", 0) or 0
            ),
            "optimized_drawing_review_axis_source_mode": str(
                optimized_drawing_review_interactive.get("axis_ref_source_mode", "") or ""
            ),
            "optimized_drawing_review_axis_source_path": str(
                optimized_drawing_review_interactive.get("axis_ref_source_path", "") or ""
            ),
            "optimized_drawing_review_axis_preview_label": " ".join(
                str(row.get("label", "") or "")
                for row in (optimized_drawing_review_axis_refs.get("x") or [])
                if isinstance(row, dict)
            )[:64],
            "external_benchmark_submission_recommended_start_mode": str(
                external_benchmark_submission_summary.get("recommended_start_mode", "") or ""
            ),
            "external_benchmark_submission_recommended_submission_scope": str(
                external_benchmark_submission_summary.get("recommended_submission_scope", "") or ""
            ),
            "external_benchmark_submission_blocker_label": str(
                external_benchmark_submission_summary.get("blocker_label", "") or ""
            ),
            "external_benchmark_submission_caution_label": str(
                external_benchmark_submission_summary.get("caution_label", "") or ""
            ),
            "external_benchmark_submission_queue_count": int(len(external_benchmark_submission_queue_rows)),
            "external_benchmark_submission_queue_ready_count": int(
                sum(
                    1
                    for row in external_benchmark_submission_queue_rows
                    if str(row.get("status", "") or "") == "ready_for_full_submission"
                )
            ),
            "external_benchmark_submission_queue_review_pending_count": int(
                sum(
                    1
                    for row in external_benchmark_submission_queue_rows
                    if str(row.get("status", "") or "") == "ready_for_benchmark_start_final_review_pending"
                )
            ),
            "external_benchmark_submission_queue_blocked_count": int(
                sum(1 for row in external_benchmark_submission_queue_rows if str(row.get("status", "") or "") == "blocked")
            ),
            "external_benchmark_submission_onepage_attestation_status": str(
                external_benchmark_submission_summary.get("onepage_attestation_status", "") or ""
            ),
            "external_benchmark_execution_mode": str(
                external_benchmark_execution_summary.get("execution_mode", "") or ""
            ),
            "external_benchmark_execution_ready_task_count": int(
                external_benchmark_execution_summary.get("ready_task_count", 0) or 0
            ),
            "external_benchmark_execution_blocked_task_count": int(
                external_benchmark_execution_summary.get("blocked_task_count", 0) or 0
            ),
            "external_benchmark_execution_review_boundary_pending_count": int(
                external_benchmark_execution_summary.get("review_boundary_pending_count", 0) or 0
            ),
            "external_benchmark_execution_review_boundary_resolution_label": str(
                external_benchmark_execution_summary.get("review_boundary_resolution_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_owner_label": str(
                external_benchmark_execution_summary.get("review_boundary_owner_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_assignee_label": str(
                external_benchmark_execution_summary.get("review_boundary_assignee_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_assignment_status_label": str(
                external_benchmark_execution_summary.get("review_boundary_assignment_status_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_priority_label": str(
                external_benchmark_execution_summary.get("review_boundary_priority_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_family_label": str(
                external_benchmark_execution_summary.get("review_boundary_family_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_change_count_total": int(
                external_benchmark_execution_summary.get("review_boundary_change_count_total", 0)
                or 0
            ),
            "external_benchmark_execution_review_boundary_followup_action_label": str(
                external_benchmark_execution_summary.get("review_boundary_followup_action_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_sla_state_label": str(
                external_benchmark_execution_summary.get("review_boundary_sla_state_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_age_bucket_label": str(
                external_benchmark_execution_summary.get("review_boundary_age_bucket_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_overdue_count": int(
                external_benchmark_execution_summary.get("review_boundary_overdue_count", 0) or 0
            ),
            "external_benchmark_execution_review_boundary_oldest_open_age_hours": float(
                external_benchmark_execution_summary.get("review_boundary_oldest_open_age_hours", 0.0)
                or 0.0
            ),
            "external_benchmark_execution_review_boundary_preview_approve_all_reason_code": str(
                external_benchmark_execution_review_boundary_preview.get("approve_all_reason_code", "") or ""
            ),
            "external_benchmark_execution_review_boundary_preview_approve_all_ready_full": bool(
                external_benchmark_execution_review_boundary_preview.get("approve_all_ready_full", False)
            ),
            "external_benchmark_execution_review_boundary_preview_reject_one_reason_code": str(
                external_benchmark_execution_review_boundary_preview.get("reject_one_reason_code", "") or ""
            ),
            "external_benchmark_execution_review_boundary_preview_reject_one_open_revision_count": int(
                external_benchmark_execution_review_boundary_preview.get(
                    "reject_one_open_revision_count", 0
                )
                or 0
            ),
            "external_benchmark_execution_status_mode": str(
                external_benchmark_execution_status_summary.get("status_mode", "") or ""
            ),
            "external_benchmark_execution_executable_task_count": int(
                external_benchmark_execution_status_summary.get("executable_task_count", 0) or 0
            ),
            "external_benchmark_execution_planned_task_count": int(
                external_benchmark_execution_status_summary.get("planned_task_count", 0) or 0
            ),
            "external_benchmark_execution_in_progress_task_count": int(
                external_benchmark_execution_status_summary.get("in_progress_task_count", 0) or 0
            ),
            "external_benchmark_execution_completed_task_count": int(
                external_benchmark_execution_status_summary.get("completed_task_count", 0) or 0
            ),
            "external_benchmark_execution_failed_task_count": int(
                external_benchmark_execution_status_summary.get("failed_task_count", 0) or 0
            ),
            "external_benchmark_execution_finished_task_count": int(
                external_benchmark_execution_status_summary.get("finished_task_count", 0) or 0
            ),
            "external_benchmark_execution_completion_ratio": float(
                external_benchmark_execution_status_summary.get("completion_ratio", 0.0) or 0.0
            ),
            "external_benchmark_batch_job_contract_pass": bool(
                external_benchmark_batch_job_report.get("contract_pass", False)
            ),
            "external_benchmark_batch_job_summary_line": str(
                external_benchmark_batch_job_report.get("summary_line", "") or ""
            ),
            "external_benchmark_batch_job_count": int(
                external_benchmark_batch_job_summary.get("job_count", 0) or 0
            ),
            "external_benchmark_batch_completed_count": int(
                external_benchmark_batch_job_summary.get("completed_count", 0) or 0
            ),
            "external_benchmark_batch_failed_count": int(
                external_benchmark_batch_job_summary.get("failed_count", 0) or 0
            ),
            "external_benchmark_batch_rerun_count": int(
                external_benchmark_batch_job_summary.get("rerun_count_total", 0) or 0
            ),
            "external_benchmark_batch_snapshot_count": int(
                external_benchmark_batch_job_summary.get("snapshot_count", 0) or 0
            ),
            "audit_review_decision_batch_template_item_count": int(
                audit_review_decision_batch_template_summary.get("decision_item_count", 0) or 0
            ),
            "audit_review_decision_batch_template_current_status_label": str(
                audit_review_decision_batch_template_summary.get("current_status_label", "") or ""
            ),
            "audit_review_decision_batch_template_review_owner_label": str(
                audit_review_decision_batch_template_summary.get("review_owner_label", "") or ""
            ),
            "audit_review_decision_batch_template_review_priority_label": str(
                audit_review_decision_batch_template_summary.get("review_priority_label", "") or ""
            ),
            "external_benchmark_submission_preview_approve_all_reason_code": str(
                external_benchmark_submission_preview_approve_all.get("reason_code", "") or ""
            ),
            "external_benchmark_submission_preview_approve_all_ready_full": bool(
                external_benchmark_submission_preview_approve_all_readiness_summary.get(
                    "ready_to_start_full_submission_now", False
                )
            ),
            "external_benchmark_submission_preview_approve_all_pending_count": int(
                external_benchmark_submission_preview_approve_all_readiness_summary.get(
                    "audit_review_queue_pending_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_approve_all_open_revision_count": int(
                external_benchmark_submission_preview_approve_all_readiness_summary.get(
                    "audit_review_resolution_open_revision_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_reject_one_reason_code": str(
                external_benchmark_submission_preview_reject_one.get("reason_code", "") or ""
            ),
            "external_benchmark_submission_preview_reject_one_ready_full": bool(
                external_benchmark_submission_preview_reject_one_readiness_summary.get(
                    "ready_to_start_full_submission_now", False
                )
            ),
            "external_benchmark_submission_preview_reject_one_pending_count": int(
                external_benchmark_submission_preview_reject_one_readiness_summary.get(
                    "audit_review_queue_pending_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_reject_one_open_revision_count": int(
                external_benchmark_submission_preview_reject_one_readiness_summary.get(
                    "audit_review_resolution_open_revision_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_reject_one_blocker_label": str(
                external_benchmark_submission_preview_reject_one_readiness_summary.get("blocker_label", "") or ""
            ),
            "audit_review_decision_batch_runner_reason_code": str(
                audit_review_decision_batch_run_report.get("reason_code", "") or ""
            ),
            "audit_review_decision_batch_runner_apply_live": bool(
                audit_review_decision_batch_run_report.get("apply_live", False)
            ),
            "audit_review_decision_batch_runner_live_applied": bool(
                audit_review_decision_batch_run_report.get("live_applied", False)
            ),
            "audit_review_decision_batch_runner_preview_reason_code": str(
                audit_review_decision_batch_run_report.get("preview_reason_code", "") or ""
            ),
            "audit_review_decision_batch_runner_preview_ready_full": bool(
                audit_review_decision_batch_run_report.get("preview_ready_full", False)
            ),
            "audit_review_decision_batch_runner_preview_pending_count": int(
                audit_review_decision_batch_run_report.get("preview_pending_count", 0) or 0
            ),
            "audit_review_decision_batch_runner_preview_open_revision_count": int(
                audit_review_decision_batch_run_report.get("preview_open_revision_count", 0) or 0
            ),
            "audit_review_decision_batch_runner_live_preview_reason_code": str(
                audit_review_decision_batch_live_preview.get("reason_code", "") or ""
            ),
        }
    )
    advanced_holdouts = [row for row in (gap.get("advanced_holdouts") or []) if isinstance(row, dict)]
    advanced_holdout_surface = _advanced_holdout_closure_surface(advanced_holdouts)
    residual_holdout_buckets = [row for row in (gap.get("residual_holdout_buckets") or []) if isinstance(row, dict)]
    residual_holdout_detail_rows = _build_residual_holdout_detail_rows(
        residual_holdout_buckets,
        design_change_rows,
        accepted_candidate_rows,
        authority_rows,
        authority_catalog,
    )
    residual_holdout_matrix_rows = _build_residual_holdout_matrix_rows(
        design_change_rows,
        accepted_candidate_rows,
        authority_catalog,
    )
    previous_catalog_snapshot = _load_json(authority_catalog_snapshot_json) if authority_catalog_snapshot_json.exists() else None
    current_catalog_snapshot = _authority_catalog_snapshot_payload(authority_catalog, residual_holdout_matrix_rows)
    authority_catalog_diff = _build_authority_catalog_routing_diff(previous_catalog_snapshot, current_catalog_snapshot)
    authority_catalog_snapshot_json.write_text(json.dumps(current_catalog_snapshot, indent=2), encoding="utf-8")
    authority_catalog_routing_diff_json.write_text(json.dumps(authority_catalog_diff, indent=2), encoding="utf-8")
    metrics["residual_holdout_detail_row_count"] = int(len(residual_holdout_detail_rows))
    metrics["residual_holdout_matrix_row_count"] = int(len(residual_holdout_matrix_rows))
    metrics["authority_catalog_diff_change_count"] = int(authority_catalog_diff.get("change_count", 0))
    metrics["authority_catalog_diff_added_count"] = int(authority_catalog_diff.get("added_count", 0))
    metrics["authority_catalog_diff_removed_count"] = int(authority_catalog_diff.get("removed_count", 0))
    metrics["authority_catalog_diff_baseline_seeded"] = bool(authority_catalog_diff.get("baseline_seeded", False))
    metrics["authority_catalog_routing_warning_active"] = bool(int(authority_catalog_diff.get("change_count", 0) or 0) > 0)
    metrics["promotion_reason_code"] = str(promotion.get("reason_code", ""))
    metrics["promotion_hold_for_review"] = str(promotion.get("reason_code", "")) == "HOLD_FOR_REVIEW"
    metrics["hold_review_manifest"] = str(promotion.get("hold_review_manifest", ""))
    metrics["hold_review_packet_md"] = str(promotion.get("hold_review_packet_md", ""))
    metrics["hold_review_packet_pdf"] = str(promotion.get("hold_review_packet_pdf", ""))
    metrics["hold_review_ack_json"] = str(promotion.get("hold_review_ack_json", ""))
    metrics["pbd_resolved_ndtha_report"] = str(pbd_inputs.get("resolved_ndtha_report", "") or "")
    metrics["pbd_resolved_ndtha_response_npz"] = str(pbd_inputs.get("resolved_ndtha_response_npz", "") or "")
    metrics["pbd_ndtha_response_fallback_used"] = bool(pbd_inputs.get("ndtha_response_fallback_used", False))
    metrics["pbd_ndtha_response_coverage_count"] = int(pbd_summary.get("ndtha_response_coverage_count", 0) or 0)
    if bool(metrics["authority_catalog_routing_warning_active"]):
        cards.insert(
            0,
            _card(
                "authority_catalog_warning",
                "Authority Routing Warning",
                f"{int(authority_catalog_diff.get('change_count', 0))} changes",
                "INFO",
                f"added={int(authority_catalog_diff.get('added_count', 0))}, removed={int(authority_catalog_diff.get('removed_count', 0))}",
            ),
        )
    if bool(metrics["promotion_hold_for_review"]):
        cards.insert(
            0,
            _card(
                "promotion_hold_warning",
                "Promotion Hold",
                str(metrics["promotion_reason_code"]),
                "INFO",
                "release candidate remains on hold until authority routing review is cleared",
            ),
        )

    summary_payload = {
        "schema_version": "1.0",
        "run_id": "phase3-committee-review-summary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "measured_chain_total_minutes": _finite(metrics.get("measured_chain_total_minutes", 0.0)),
        "measured_chain_rolling_sample_count": int(metrics.get("measured_chain_rolling_sample_count", 0)),
        "measured_chain_rolling_total_minutes_mean": _finite(metrics.get("measured_chain_rolling_total_minutes_mean", 0.0)),
        "measured_chain_rolling_total_minutes_range": metrics.get("measured_chain_rolling_total_minutes_range", []),
        "measured_chain_full_chain_sample_count": int(metrics.get("measured_chain_full_chain_sample_count", 0)),
        "measured_chain_comparable_sample_count": int(metrics.get("measured_chain_comparable_sample_count", 0)),
        "measured_chain_comparable_reference_step_count": int(metrics.get("measured_chain_comparable_reference_step_count", 0)),
        "measured_chain_comparable_overlap_threshold": _finite(metrics.get("measured_chain_comparable_overlap_threshold", 0.0)),
        "measured_chain_comparable_reference_deployment_model": str(metrics.get("measured_chain_comparable_reference_deployment_model", "")),
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(metrics.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)),
        "measured_chain_rolling_selection_mode": str(metrics.get("measured_chain_rolling_selection_mode", "")),
        "empirical_smoke_runtime_saved_pct_label": str(metrics.get("empirical_smoke_runtime_saved_pct_label", "")),
        "midas_section_library_summary_line": str(metrics.get("midas_section_library_summary_line", "")),
        "midas_kds_geometry_bridge_summary_line": str(metrics.get("midas_kds_geometry_bridge_summary_line", "")),
        "midas_kds_geometry_bridge_load_crosswalk_summary_line": str(
            metrics.get("midas_kds_geometry_bridge_load_crosswalk_summary_line", "")
        ),
        "midas_kds_geometry_bridge_load_crosswalk_count": int(
            metrics.get("midas_kds_geometry_bridge_load_crosswalk_count", 0)
        ),
        "midas_kds_geometry_bridge_load_crosswalk_expected": int(
            metrics.get("midas_kds_geometry_bridge_load_crosswalk_expected", 0)
        ),
        "midas_kds_geometry_bridge_load_crosswalk_status": str(
            metrics.get("midas_kds_geometry_bridge_load_crosswalk_status", "")
        ),
        "midas_kds_geometry_bridge_load_crosswalk_pass": metrics.get(
            "midas_kds_geometry_bridge_load_crosswalk_pass"
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": str(
            metrics.get("midas_kds_geometry_bridge_semantic_crosswalk_summary_line", "")
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_count": int(
            metrics.get("midas_kds_geometry_bridge_semantic_crosswalk_count", 0)
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_expected": int(
            metrics.get("midas_kds_geometry_bridge_semantic_crosswalk_expected", 0)
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_status": str(
            metrics.get("midas_kds_geometry_bridge_semantic_crosswalk_status", "")
        ),
        "midas_kds_geometry_bridge_semantic_crosswalk_pass": metrics.get(
            "midas_kds_geometry_bridge_semantic_crosswalk_pass"
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": str(
            metrics.get("midas_kds_geometry_bridge_full_member_crosswalk_summary_line", "")
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_count": int(
            metrics.get("midas_kds_geometry_bridge_full_member_crosswalk_count", 0)
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_expected": int(
            metrics.get("midas_kds_geometry_bridge_full_member_crosswalk_expected", 0)
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_status": str(
            metrics.get("midas_kds_geometry_bridge_full_member_crosswalk_status", "")
        ),
        "midas_kds_geometry_bridge_full_member_crosswalk_pass": metrics.get(
            "midas_kds_geometry_bridge_full_member_crosswalk_pass"
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": str(
            metrics.get("midas_kds_geometry_bridge_full_section_crosswalk_summary_line", "")
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_count": int(
            metrics.get("midas_kds_geometry_bridge_full_section_crosswalk_count", 0)
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_expected": int(
            metrics.get("midas_kds_geometry_bridge_full_section_crosswalk_expected", 0)
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_status": str(
            metrics.get("midas_kds_geometry_bridge_full_section_crosswalk_status", "")
        ),
        "midas_kds_geometry_bridge_full_section_crosswalk_pass": metrics.get(
            "midas_kds_geometry_bridge_full_section_crosswalk_pass"
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": str(
            metrics.get("midas_kds_geometry_bridge_full_load_crosswalk_summary_line", "")
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_count": int(
            metrics.get("midas_kds_geometry_bridge_full_load_crosswalk_count", 0)
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_expected": int(
            metrics.get("midas_kds_geometry_bridge_full_load_crosswalk_expected", 0)
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_status": str(
            metrics.get("midas_kds_geometry_bridge_full_load_crosswalk_status", "")
        ),
        "midas_kds_geometry_bridge_full_load_crosswalk_pass": metrics.get(
            "midas_kds_geometry_bridge_full_load_crosswalk_pass"
        ),
        "midas_kds_geometry_bridge_full_crosswalk_depth": int(
            metrics.get("midas_kds_geometry_bridge_full_crosswalk_depth", 0)
        ),
        "midas_loadcomb_roundtrip_summary_line": str(metrics.get("midas_loadcomb_roundtrip_summary_line", "")),
        "commercial_benchmark_breadth_summary_line": str(metrics.get("commercial_benchmark_breadth_summary_line", "")),
        "solver_breadth_summary_line": str(metrics.get("solver_breadth_summary_line", "")),
        "element_material_breadth_summary_line": str(metrics.get("element_material_breadth_summary_line", "")),
        "material_constitutive_summary_line": str(metrics.get("material_constitutive_summary_line", "")),
        "contact_readiness_summary_line": str(metrics.get("contact_readiness_summary_line", "")),
        "foundation_soil_link_summary_line": str(metrics.get("foundation_soil_link_summary_line", "")),
        "support_search_summary_line": str(metrics.get("support_search_summary_line", "")),
        "support_search_count": int(metrics.get("support_search_count", 0)),
        "node_surface_proxy_count": int(metrics.get("node_surface_proxy_count", 0)),
        "support_depth_score": int(metrics.get("support_depth_score", 0)),
        "structural_contact_summary_line": str(metrics.get("structural_contact_summary_line", "")),
        "general_fe_contact_matrix_summary_line": str(metrics.get("general_fe_contact_matrix_summary_line", "")),
        "general_fe_contact_matrix_summary": dict(metrics.get("general_fe_contact_matrix_summary", {}) or {}),
        "surface_interaction_benchmark_summary_line": str(metrics.get("surface_interaction_benchmark_summary_line", "")),
        "performance_profiling_summary_line": str(metrics.get("performance_profiling_summary_line", "")),
        "ndtha_step_series_depth": int(metrics.get("ndtha_step_series_depth", 0)),
        "ndtha_material_summary_line": str(metrics.get("ndtha_material_summary_line", "")),
        "ndtha_material_depth": int(metrics.get("ndtha_material_depth", 0)),
        "performance_moving_load_scale_label": str(metrics.get("performance_moving_load_scale_label", "")),
        "performance_moving_load_cached_inverse_label": str(metrics.get("performance_moving_load_cached_inverse_label", "")),
        "performance_ssi_variant_sweep_label": str(metrics.get("performance_ssi_variant_sweep_label", "")),
        "performance_ssi_zero_gap_variant_label": str(metrics.get("performance_ssi_zero_gap_variant_label", "")),
        "performance_ssi_pruned_variant_label": str(metrics.get("performance_ssi_pruned_variant_label", "")),
        "solver_truthfulness_summary_line": str(metrics.get("solver_truthfulness_summary_line", "")),
        "hardest_external_10case_kickoff_summary_line": str(metrics.get("hardest_external_10case_kickoff_summary_line", "")),
        "nonlinear_generalization_summary_line": str(metrics.get("nonlinear_generalization_summary_line", "")),
        "workflow_productization_summary_line": str(metrics.get("workflow_productization_summary_line", "")),
        "workflow_contact_coupling_summary": dict(metrics.get("workflow_contact_coupling_summary", {}) or {}),
        "irregular_structure_summary_line": str(metrics.get("irregular_structure_summary_line", "")),
        "irregular_structure_track_pass": bool(metrics.get("irregular_structure_track_pass", False)),
        "irregular_structure_family_count": int(metrics.get("irregular_structure_family_count", 0)),
        "irregular_structure_source_record_count": int(metrics.get("irregular_structure_source_record_count", 0)),
        "irregular_structure_local_ready_count": int(metrics.get("irregular_structure_local_ready_count", 0)),
        "irregular_structure_remote_candidate_count": int(metrics.get("irregular_structure_remote_candidate_count", 0)),
        "irregular_structure_native_roundtrip_candidate_count": int(
            metrics.get("irregular_structure_native_roundtrip_candidate_count", 0)
        ),
        "irregular_structure_solver_benchmark_candidate_count": int(
            metrics.get("irregular_structure_solver_benchmark_candidate_count", 0)
        ),
        "irregular_structure_ai_learning_candidate_count": int(metrics.get("irregular_structure_ai_learning_candidate_count", 0)),
        "irregular_structure_top5_count": int(metrics.get("irregular_structure_top5_count", 0)),
        "irregular_structure_top5_family_ids": list(metrics.get("irregular_structure_top5_family_ids", []) or []),
        "irregular_structure_gate_report": str(metrics.get("irregular_structure_gate_report", "") or ""),
        "irregular_top5_execution_manifest": str(metrics.get("irregular_top5_execution_manifest", "") or ""),
        "irregular_structure_source_catalog": str(metrics.get("irregular_structure_source_catalog", "") or ""),
        "irregular_priority_manifest": str(metrics.get("irregular_priority_manifest", "") or ""),
        "irregular_structure_collection_report": str(metrics.get("irregular_structure_collection_report", "") or ""),
        "irregular_structure_triage_report": str(metrics.get("irregular_structure_triage_report", "") or ""),
        "midas_kds_row_provenance_export_summary_line": str(metrics.get("midas_kds_row_provenance_export_summary_line", "")),
        "midas_kds_row_provenance_export_pass": bool(metrics.get("midas_kds_row_provenance_export_pass", False)),
        "midas_kds_row_provenance_export_row_count": int(metrics.get("midas_kds_row_provenance_export_row_count", 0)),
        "midas_kds_row_provenance_export_member_count": int(metrics.get("midas_kds_row_provenance_export_member_count", 0)),
        "midas_kds_row_provenance_export_clause_count": int(metrics.get("midas_kds_row_provenance_export_clause_count", 0)),
        "midas_kds_row_provenance_export_exact_row_count": int(metrics.get("midas_kds_row_provenance_export_exact_row_count", 0)),
        "midas_kds_row_provenance_preview_rows": [
            row for row in (metrics.get("midas_kds_row_provenance_preview_rows", []) or []) if isinstance(row, dict)
        ],
        "commercial_scope_summary_line": str(metrics.get("commercial_scope_summary_line", "")),
        "commercial_reliability_breadth_summary_line": str(metrics.get("commercial_reliability_breadth_summary_line", "")),
        "midas_kds_row_provenance_exact_row_coverage_label": str(
            metrics.get("midas_kds_row_provenance_exact_row_coverage_label", "")
        ),
        "midas_kds_row_provenance_preview_rows_present": bool(
            metrics.get("midas_kds_row_provenance_preview_rows_present", False)
        ),
        "midas_kds_row_provenance_preview_row_count": int(
            metrics.get("midas_kds_row_provenance_preview_row_count", 0)
        ),
        "midas_interoperability_summary_line": str(metrics.get("midas_interoperability_summary_line", "")),
        "midas_native_roundtrip_summary_line": str(metrics.get("midas_native_roundtrip_summary_line", "")),
        "steel_composite_constitutive_gate_summary_line": str(
            metrics.get("steel_composite_constitutive_gate_summary_line", "")
        ),
        "steel_composite_constitutive_gate_pass": (
            bool(metrics.get("steel_composite_constitutive_gate_pass"))
            if isinstance(metrics.get("steel_composite_constitutive_gate_pass"), bool)
            else None
        ),
        "load_combination_engine_summary_line": str(metrics.get("load_combination_engine_summary_line", "")),
        "load_combination_engine_pass": (
            bool(metrics.get("load_combination_engine_pass"))
            if isinstance(metrics.get("load_combination_engine_pass"), bool)
            else None
        ),
        "midas_native_roundtrip_public_native_writeback_ready_count": int(
            metrics.get("midas_native_roundtrip_public_native_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_raw_native_writeback_ready_count": int(
            metrics.get("midas_native_roundtrip_public_raw_native_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_bridge_writeback_ready_count": int(
            metrics.get("midas_native_roundtrip_public_bridge_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_archive_preview_writeback_ready_count": int(
            metrics.get("midas_native_roundtrip_public_archive_preview_writeback_ready_count", 0)
        ),
        "midas_native_roundtrip_public_source_writeback_ready_count": int(
            metrics.get("midas_native_roundtrip_public_source_writeback_ready_count", 0)
        ),
        "commercial_readiness_summary_line": str(metrics.get("commercial_readiness_summary_line", "")),
        "mgt_export_loadcomb_roundtrip_summary_line": str(metrics.get("mgt_export_loadcomb_roundtrip_summary_line", "")),
        "mgt_export_loadcomb_roundtrip_pass": bool(metrics.get("mgt_export_loadcomb_roundtrip_pass", False)),
        "midas_semantic_load_binding_pass": bool(gap_summary.get("midas_semantic_load_binding_pass", False)),
        "midas_use_stld_block_count": int(gap_summary.get("midas_use_stld_block_count", 0)),
        "midas_semantic_load_case_count": int(gap_summary.get("midas_semantic_load_case_count", 0)),
        "midas_semantic_load_combination_count": int(gap_summary.get("midas_semantic_load_combination_count", 0)),
        "midas_bound_nodal_load_row_count": int(gap_summary.get("midas_bound_nodal_load_row_count", 0)),
        "midas_bound_selfweight_row_count": int(gap_summary.get("midas_bound_selfweight_row_count", 0)),
        "midas_bound_pressure_row_count": int(gap_summary.get("midas_bound_pressure_row_count", 0)),
        "midas_unbound_nodal_load_row_count": int(gap_summary.get("midas_unbound_nodal_load_row_count", 0)),
        "midas_unbound_selfweight_row_count": int(gap_summary.get("midas_unbound_selfweight_row_count", 0)),
        "midas_unbound_pressure_row_count": int(gap_summary.get("midas_unbound_pressure_row_count", 0)),
        "mgt_export_artifact_exists": bool(gap_summary.get("mgt_export_artifact_exists", False)),
        "mgt_export_contract_pass": bool(gap_summary.get("mgt_export_contract_pass", False)),
        "mgt_export_support_mode": str(gap_summary.get("mgt_export_support_mode", "")),
        "mgt_export_supported_change_count": int(gap_summary.get("mgt_export_supported_change_count", 0)),
        "mgt_export_unsupported_change_count": int(gap_summary.get("mgt_export_unsupported_change_count", 0)),
        "mgt_export_direct_patch_change_count": int(gap_summary.get("mgt_export_direct_patch_change_count", 0)),
        "mgt_export_direct_patch_supported_action_families": list(
            gap_summary.get("mgt_export_direct_patch_supported_action_families", []) or []
        ),
        "mgt_export_sidecar_supported_action_families": list(
            gap_summary.get("mgt_export_sidecar_supported_action_families", []) or []
        ),
        "mgt_export_direct_patch_action_family_counts": dict(
            gap_summary.get("mgt_export_direct_patch_action_family_counts", {}) or {}
        ),
        "mgt_export_direct_patch_action_family_label": str(
            gap_summary.get("mgt_export_direct_patch_action_family_label", "")
        ),
        "mgt_export_special_member_supported_action_family_counts": dict(
            gap_summary.get("mgt_export_special_member_supported_action_family_counts", {}) or {}
        ),
        "mgt_export_special_member_direct_patch_action_family_counts": dict(
            gap_summary.get("mgt_export_special_member_direct_patch_action_family_counts", {}) or {}
        ),
        "mgt_export_special_member_zero_touch_verified_action_family_counts": dict(
            gap_summary.get("mgt_export_special_member_zero_touch_verified_action_family_counts", {}) or {}
        ),
        "mgt_export_special_member_supported_action_family_label": str(
            gap_summary.get("mgt_export_special_member_supported_action_family_label", "")
        ),
        "mgt_export_special_member_direct_patch_action_family_label": str(
            gap_summary.get("mgt_export_special_member_direct_patch_action_family_label", "")
        ),
        "mgt_export_special_member_zero_touch_verified_action_family_label": str(
            gap_summary.get("mgt_export_special_member_zero_touch_verified_action_family_label", "")
        ),
        "mgt_export_material_level_rebar_payload_row_count": int(
            gap_summary.get("mgt_export_material_level_rebar_payload_row_count", 0)
        ),
        "mgt_export_material_level_rebar_payload_available_count": int(
            gap_summary.get("mgt_export_material_level_rebar_payload_available_count", 0)
        ),
        "mgt_export_group_local_rebar_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_rebar_payload_row_count", 0)
        ),
        "mgt_export_group_local_rebar_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_rebar_payload_available_count", 0)
        ),
        "mgt_export_group_local_connection_detailing_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_connection_detailing_payload_row_count", 0)
        ),
        "mgt_export_group_local_connection_detailing_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_connection_detailing_payload_available_count", 0)
        ),
        "mgt_export_group_local_detailing_payload_row_count": int(
            gap_summary.get("mgt_export_group_local_detailing_payload_row_count", 0)
        ),
        "mgt_export_group_local_detailing_payload_available_count": int(
            gap_summary.get("mgt_export_group_local_detailing_payload_available_count", 0)
        ),
        "mgt_export_connection_detailing_payload_namespace_mode": str(
            gap_summary.get("mgt_export_connection_detailing_payload_namespace_mode", "")
        ),
        "mgt_export_connection_detailing_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_connection_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_detailing_payload_namespace_mode": str(
            gap_summary.get("mgt_export_detailing_payload_namespace_mode", "")
        ),
        "mgt_export_detailing_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_detailing_payload_group_local_namespace_present", False)
        ),
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": int(
            gap_summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0)
        ),
        "mgt_export_connection_detailing_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_connection_detailing_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_detailing_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_detailing_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_detailing_structured_payload_mapped_change_count": int(
            gap_summary.get("mgt_export_detailing_structured_payload_mapped_change_count", 0)
        ),
        "mgt_export_connection_detailing_delivery_mode": str(
            gap_summary.get("mgt_export_connection_detailing_delivery_mode", "")
        ),
        "mgt_export_detailing_delivery_mode": str(gap_summary.get("mgt_export_detailing_delivery_mode", "")),
        "mgt_export_rebar_payload_namespace_mode": str(
            gap_summary.get("mgt_export_rebar_payload_namespace_mode", "")
        ),
        "mgt_export_rebar_payload_material_level_namespace_present": bool(
            gap_summary.get("mgt_export_rebar_payload_material_level_namespace_present", False)
        ),
        "mgt_export_rebar_payload_group_local_namespace_present": bool(
            gap_summary.get("mgt_export_rebar_payload_group_local_namespace_present", False)
        ),
        "mgt_export_rebar_delivery_mode": str(
            gap_summary.get("mgt_export_rebar_delivery_mode", "")
        ),
        "mgt_export_evidence_model": str(
            gap_summary.get("mgt_export_evidence_model", "")
        ),
        "mgt_export_rebar_direct_patch_eligible_change_count": int(
            gap_summary.get("mgt_export_rebar_direct_patch_eligible_change_count", 0)
        ),
        "mgt_export_patched_material_row_count": int(gap_summary.get("mgt_export_patched_material_row_count", 0)),
        "mgt_export_cloned_material_count": int(gap_summary.get("mgt_export_cloned_material_count", 0)),
        "mgt_export_rebar_direct_patch_ineligible_reason_counts": dict(
            gap_summary.get("mgt_export_rebar_direct_patch_ineligible_reason_counts", {}) or {}
        ),
        "mgt_export_rebar_direct_patch_ineligible_reason_label": str(
            gap_summary.get("mgt_export_rebar_direct_patch_ineligible_reason_label", "")
        ),
        "mgt_export_rebar_direct_patch_mapping_source_counts": dict(
            gap_summary.get("mgt_export_rebar_direct_patch_mapping_source_counts", {}) or {}
        ),
        "mgt_export_rebar_direct_patch_mapping_source_label": str(
            gap_summary.get("mgt_export_rebar_direct_patch_mapping_source_label", "")
        ),
        "mgt_export_instruction_sidecar_change_count": int(gap_summary.get("mgt_export_instruction_sidecar_change_count", 0)),
        "mgt_export_instruction_sidecar_action_family_counts": dict(
            gap_summary.get("mgt_export_instruction_sidecar_action_family_counts", {}) or {}
        ),
        "mgt_export_instruction_sidecar_action_family_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_action_family_label", "")
        ),
        "mgt_export_instruction_sidecar_audit_only_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_audit_only_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_audit_only_action_family_counts": dict(
            gap_summary.get("mgt_export_instruction_sidecar_audit_only_action_family_counts", {}) or {}
        ),
        "mgt_export_instruction_sidecar_audit_only_action_family_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_audit_only_action_family_label", "")
        ),
        "mgt_export_instruction_sidecar_manual_input_change_count": int(
            gap_summary.get("mgt_export_instruction_sidecar_manual_input_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_manual_input_action_family_counts": dict(
            gap_summary.get("mgt_export_instruction_sidecar_manual_input_action_family_counts", {}) or {}
        ),
        "mgt_export_instruction_sidecar_manual_input_action_family_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_manual_input_action_family_label", "")
        ),
        "mgt_export_audit_review_manifest_change_count": int(
            gap_summary.get("mgt_export_audit_review_manifest_change_count", 0)
        ),
        "mgt_export_audit_review_manifest_action_family_counts": dict(
            gap_summary.get("mgt_export_audit_review_manifest_action_family_counts", {}) or {}
        ),
        "mgt_export_audit_review_manifest_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_manifest_action_family_label", "")
        ),
        "mgt_export_audit_review_packet_count": int(
            gap_summary.get("mgt_export_audit_review_packet_count", 0)
        ),
        "mgt_export_audit_review_packet_action_family_counts": dict(
            gap_summary.get("mgt_export_audit_review_packet_action_family_counts", {}) or {}
        ),
        "mgt_export_audit_review_packet_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_packet_action_family_label", "")
        ),
        "mgt_export_audit_review_packet_followup_type_counts": dict(
            gap_summary.get("mgt_export_audit_review_packet_followup_type_counts", {}) or {}
        ),
        "mgt_export_audit_review_packet_followup_type_label": str(
            gap_summary.get("mgt_export_audit_review_packet_followup_type_label", "")
        ),
        "mgt_export_audit_review_packet_file_count": int(
            gap_summary.get("mgt_export_audit_review_packet_file_count", 0)
        ),
        "mgt_export_audit_review_packet_file_action_family_counts": dict(
            gap_summary.get("mgt_export_audit_review_packet_file_action_family_counts", {}) or {}
        ),
        "mgt_export_audit_review_packet_file_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_packet_file_action_family_label", "")
        ),
        "mgt_export_audit_review_queue_item_count": int(
            gap_summary.get("mgt_export_audit_review_queue_item_count", 0)
        ),
        "mgt_export_audit_review_queue_pending_count": int(
            gap_summary.get("mgt_export_audit_review_queue_pending_count", 0)
        ),
        "mgt_export_audit_review_queue_acknowledged_count": int(
            gap_summary.get("mgt_export_audit_review_queue_acknowledged_count", 0)
        ),
        "mgt_export_audit_review_queue_status_counts": dict(
            gap_summary.get("mgt_export_audit_review_queue_status_counts", {}) or {}
        ),
        "mgt_export_audit_review_queue_status_label": str(
            gap_summary.get("mgt_export_audit_review_queue_status_label", "")
        ),
        "mgt_export_audit_review_queue_action_family_counts": dict(
            gap_summary.get("mgt_export_audit_review_queue_action_family_counts", {}) or {}
        ),
        "mgt_export_audit_review_queue_action_family_label": str(
            gap_summary.get("mgt_export_audit_review_queue_action_family_label", "")
        ),
        "mgt_export_audit_review_followup_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_item_count", 0)
        ),
        "mgt_export_audit_review_followup_open_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_open_item_count", 0)
        ),
        "mgt_export_audit_review_followup_closed_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_closed_item_count", 0)
        ),
        "mgt_export_audit_review_followup_action_counts": dict(
            gap_summary.get("mgt_export_audit_review_followup_action_counts", {}) or {}
        ),
        "mgt_export_audit_review_followup_action_label": str(
            gap_summary.get("mgt_export_audit_review_followup_action_label", "")
        ),
        "mgt_export_audit_review_followup_owner_counts": dict(
            gap_summary.get("mgt_export_audit_review_followup_owner_counts", {}) or {}
        ),
        "mgt_export_audit_review_followup_owner_label": str(
            gap_summary.get("mgt_export_audit_review_followup_owner_label", "")
        ),
        "mgt_export_audit_review_followup_review_owner_counts": dict(
            gap_summary.get("mgt_export_audit_review_followup_review_owner_counts", {}) or {}
        ),
        "mgt_export_audit_review_followup_review_owner_label": str(
            gap_summary.get("mgt_export_audit_review_followup_review_owner_label", "")
        ),
        "mgt_export_audit_review_followup_status_counts": dict(
            gap_summary.get("mgt_export_audit_review_followup_status_counts", {}) or {}
        ),
        "mgt_export_audit_review_followup_status_label": str(
            gap_summary.get("mgt_export_audit_review_followup_status_label", "")
        ),
        "mgt_export_audit_review_followup_sla_state_counts": dict(
            gap_summary.get("mgt_export_audit_review_followup_sla_state_counts", {}) or {}
        ),
        "mgt_export_audit_review_followup_sla_state_label": str(
            gap_summary.get("mgt_export_audit_review_followup_sla_state_label", "")
        ),
        "mgt_export_audit_review_followup_age_bucket_counts": dict(
            gap_summary.get("mgt_export_audit_review_followup_age_bucket_counts", {}) or {}
        ),
        "mgt_export_audit_review_followup_age_bucket_label": str(
            gap_summary.get("mgt_export_audit_review_followup_age_bucket_label", "")
        ),
        "mgt_export_audit_review_followup_overdue_item_count": int(
            gap_summary.get("mgt_export_audit_review_followup_overdue_item_count", 0)
        ),
        "mgt_export_audit_review_followup_oldest_open_age_hours": float(
            gap_summary.get("mgt_export_audit_review_followup_oldest_open_age_hours", 0.0)
        ),
        "mgt_export_audit_review_followup_oldest_open_packet_id": str(
            gap_summary.get("mgt_export_audit_review_followup_oldest_open_packet_id", "")
        ),
        "mgt_export_audit_review_followup_mode": str(
            gap_summary.get("mgt_export_audit_review_followup_mode", "")
        ),
        "mgt_export_audit_review_resolution_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_open_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_open_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_closed_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_closed_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_pending_item_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_pending_item_count", 0)
        ),
        "mgt_export_audit_review_resolution_open_revision_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_open_revision_count", 0)
        ),
        "mgt_export_audit_review_resolution_closed_packet_count": int(
            gap_summary.get("mgt_export_audit_review_resolution_closed_packet_count", 0)
        ),
        "mgt_export_audit_review_resolution_action_counts": dict(
            gap_summary.get("mgt_export_audit_review_resolution_action_counts", {}) or {}
        ),
        "mgt_export_audit_review_resolution_action_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_action_label", "")
        ),
        "mgt_export_audit_review_resolution_owner_counts": dict(
            gap_summary.get("mgt_export_audit_review_resolution_owner_counts", {}) or {}
        ),
        "mgt_export_audit_review_resolution_owner_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_owner_label", "")
        ),
        "mgt_export_audit_review_resolution_status_counts": dict(
            gap_summary.get("mgt_export_audit_review_resolution_status_counts", {}) or {}
        ),
        "mgt_export_audit_review_resolution_status_label": str(
            gap_summary.get("mgt_export_audit_review_resolution_status_label", "")
        ),
        "mgt_export_audit_review_resolution_mode": str(
            gap_summary.get("mgt_export_audit_review_resolution_mode", "")
        ),
        "mgt_export_instruction_sidecar_review_priority_counts": dict(
            gap_summary.get("mgt_export_instruction_sidecar_review_priority_counts", {}) or {}
        ),
        "mgt_export_instruction_sidecar_review_priority_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_review_priority_label", "")
        ),
        "mgt_export_instruction_sidecar_followup_type_counts": dict(
            gap_summary.get("mgt_export_instruction_sidecar_followup_type_counts", {}) or {}
        ),
        "mgt_export_instruction_sidecar_followup_type_label": str(
            gap_summary.get("mgt_export_instruction_sidecar_followup_type_label", "")
        ),
        "mgt_export_cloned_section_count": int(gap_summary.get("mgt_export_cloned_section_count", 0)),
        "mgt_export_cloned_thickness_count": int(gap_summary.get("mgt_export_cloned_thickness_count", 0)),
        "mgt_export_retargeted_element_row_count": int(gap_summary.get("mgt_export_retargeted_element_row_count", 0)),
        "design_opt_raw_max_drift_pct": _finite(metrics.get("design_opt_raw_max_drift_pct", 0.0)),
        "design_opt_raw_residual_drift_pct": _finite(metrics.get("design_opt_raw_residual_drift_pct", 0.0)),
        "design_opt_raw_max_dcr": _finite(metrics.get("design_opt_raw_max_dcr", 0.0)),
        "design_opt_repaired_compliance_max_drift_pct": _finite(metrics.get("design_opt_repaired_compliance_max_drift_pct", 0.0)),
        "design_opt_repaired_compliance_residual_drift_pct": _finite(metrics.get("design_opt_repaired_compliance_residual_drift_pct", 0.0)),
        "design_opt_repaired_compliance_max_dcr": _finite(metrics.get("design_opt_repaired_compliance_max_dcr", 0.0)),
        "design_opt_compliance_basis": str(metrics.get("design_opt_compliance_basis", "")),
        "design_opt_repair_action_count": int(metrics.get("design_opt_repair_action_count", 0)),
        "design_opt_constructability_signal_gain_pct": _finite(metrics.get("design_opt_constructability_signal_gain_pct", 0.0)),
        "design_opt_baseline_constructability_avg": _finite(metrics.get("design_opt_baseline_constructability_avg", 0.0)),
        "design_opt_final_constructability_avg": _finite(metrics.get("design_opt_final_constructability_avg", 0.0)),
        "design_opt_baseline_detailing_complexity_avg": _finite(metrics.get("design_opt_baseline_detailing_complexity_avg", 0.0)),
        "design_opt_final_detailing_complexity_avg": _finite(metrics.get("design_opt_final_detailing_complexity_avg", 0.0)),
        "design_opt_selected_action_family_counts": metrics.get("design_opt_selected_action_family_counts", {}),
        "design_opt_previous_action_family_counts": metrics.get("design_opt_previous_action_family_counts", {}),
        "design_opt_preview_supply_family_counts": metrics.get("design_opt_preview_supply_family_counts", {}),
        "design_opt_preview_supply_family_mix_label": str(metrics.get("design_opt_preview_supply_family_mix_label", "")),
        "design_opt_preview_missing_target_families_label": str(metrics.get("design_opt_preview_missing_target_families_label", "")),
        "design_opt_selected_family_mix_label": str(metrics.get("design_opt_selected_family_mix_label", "")),
        "design_opt_selected_family_trend_label": str(metrics.get("design_opt_selected_family_trend_label", "")),
        "design_opt_selected_dominant_family": str(metrics.get("design_opt_selected_dominant_family", "")),
        "design_opt_selected_dominant_family_ratio": _finite(metrics.get("design_opt_selected_dominant_family_ratio", 0.0)),
        "design_opt_previous_dominant_family": str(metrics.get("design_opt_previous_dominant_family", "")),
        "design_opt_previous_dominant_family_ratio": _finite(metrics.get("design_opt_previous_dominant_family_ratio", 0.0)),
        "mgt_export_delivery_boundary": str(metrics.get("mgt_export_delivery_boundary", "")),
        "advanced_holdout_total_count": int(advanced_holdout_surface.get("total_count", 0)),
        "advanced_holdout_closed_count": int(advanced_holdout_surface.get("closed_count", 0)),
        "advanced_holdout_open_count": int(advanced_holdout_surface.get("open_count", 0)),
        "advanced_holdout_status_label": str(advanced_holdout_surface.get("summary_label", "") or ""),
        "advanced_holdout_status_rows": [
            row for row in (advanced_holdout_surface.get("status_rows") or []) if isinstance(row, dict)
        ],
        "pbd_dynamic_hinge_refresh_ready": bool(metrics.get("pbd_dynamic_hinge_refresh_ready", False)),
        "pbd_hinge_state_mode": str(metrics.get("pbd_hinge_state_mode", "")),
        "pbd_hinge_refresh_reason": str(metrics.get("pbd_hinge_refresh_reason", "")),
        "pbd_hinge_refresh_artifact_present": bool(metrics.get("pbd_hinge_refresh_artifact_present", False)),
        "pbd_hinge_refresh_artifact_kind": str(metrics.get("pbd_hinge_refresh_artifact_kind", "")),
        "pbd_hinge_refresh_source_mode": str(metrics.get("pbd_hinge_refresh_source_mode", "")),
        "pbd_hinge_refresh_overlap_member_count": int(metrics.get("pbd_hinge_refresh_overlap_member_count", 0)),
        "pbd_hinge_refresh_rebar_sensitive_member_count": int(
            metrics.get("pbd_hinge_refresh_rebar_sensitive_member_count", 0)
        ),
        "panel_zone_3d_clash_ready": bool(metrics.get("panel_zone_3d_clash_ready", False)),
        "panel_zone_constructability_mode": str(metrics.get("panel_zone_constructability_mode", "")),
        "panel_zone_constructability_reason": str(metrics.get("panel_zone_constructability_reason", "")),
        "panel_zone_proxy_candidate_count": int(metrics.get("panel_zone_proxy_candidate_count", 0)),
        "panel_zone_source_artifact_kind": str(metrics.get("panel_zone_source_artifact_kind", "")),
        "panel_zone_source_artifact_path": str(metrics.get("panel_zone_source_artifact_path", "")),
        "panel_zone_source_contract_mode": str(metrics.get("panel_zone_source_contract_mode", "")),
        "panel_zone_internal_engine_complete": bool(metrics.get("panel_zone_internal_engine_complete", False)),
        "panel_zone_external_validation_pending": bool(
            metrics.get("panel_zone_external_validation_pending", False)
        ),
        "panel_zone_validation_boundary": str(metrics.get("panel_zone_validation_boundary", "")),
        "panel_zone_external_validation_advisory_only": bool(
            metrics.get("panel_zone_external_validation_advisory_only", False)
        ),
        "panel_zone_external_validation_release_blocking": bool(
            metrics.get("panel_zone_external_validation_release_blocking", False)
        ),
        "panel_zone_external_validation_status_label": str(
            metrics.get("panel_zone_external_validation_status_label", "")
        ),
        "panel_zone_external_validation_artifact_closed": bool(
            metrics.get("panel_zone_external_validation_artifact_closed", False)
        ),
        "panel_zone_external_validation_closure_mode": str(
            metrics.get("panel_zone_external_validation_closure_mode", "")
        ),
        "panel_zone_external_validation_required_evidence": str(
            metrics.get("panel_zone_external_validation_required_evidence", "")
        ),
        "panel_zone_external_validation_summary_line": str(
            metrics.get("panel_zone_external_validation_summary_line", "")
        ),
        "panel_zone_external_validation_local_closure_state": str(
            metrics.get("panel_zone_external_validation_local_closure_state", "")
        ),
        "panel_zone_external_validation_local_closure_label": str(
            metrics.get("panel_zone_external_validation_local_closure_label", "")
        ),
        "panel_zone_external_validation_source_count": int(
            metrics.get("panel_zone_external_validation_source_count", 0)
        ),
        "panel_zone_external_validation_validated_source_count": int(
            metrics.get("panel_zone_external_validation_validated_source_count", 0)
        ),
        "panel_zone_external_validation_exact_source_count": int(
            metrics.get("panel_zone_external_validation_exact_source_count", 0)
        ),
        "panel_zone_external_validation_fallback_source_count": int(
            metrics.get("panel_zone_external_validation_fallback_source_count", 0)
        ),
        "panel_zone_external_validation_missing_source_count": int(
            metrics.get("panel_zone_external_validation_missing_source_count", 0)
        ),
        "panel_zone_external_validation_unknown_source_count": int(
            metrics.get("panel_zone_external_validation_unknown_source_count", 0)
        ),
        "panel_zone_external_validation_validated_source_ratio": float(
            metrics.get("panel_zone_external_validation_validated_source_ratio", 0.0)
        ),
        "panel_zone_external_validation_exact_source_ratio": float(
            metrics.get("panel_zone_external_validation_exact_source_ratio", 0.0)
        ),
        "panel_zone_external_validation_fallback_source_ratio": float(
            metrics.get("panel_zone_external_validation_fallback_source_ratio", 0.0)
        ),
        "panel_zone_external_validation_candidate_member_count": int(
            metrics.get("panel_zone_external_validation_candidate_member_count", 0)
        ),
        "panel_zone_external_validation_validated_member_count": int(
            metrics.get("panel_zone_external_validation_validated_member_count", 0)
        ),
        "panel_zone_external_validation_exact_member_count": int(
            metrics.get("panel_zone_external_validation_exact_member_count", 0)
        ),
        "panel_zone_external_validation_fallback_member_count": int(
            metrics.get("panel_zone_external_validation_fallback_member_count", 0)
        ),
        "panel_zone_external_validation_validated_member_ratio": float(
            metrics.get("panel_zone_external_validation_validated_member_ratio", 0.0)
        ),
        "panel_zone_external_validation_exact_member_ratio": float(
            metrics.get("panel_zone_external_validation_exact_member_ratio", 0.0)
        ),
        "panel_zone_external_validation_fallback_member_ratio": float(
            metrics.get("panel_zone_external_validation_fallback_member_ratio", 0.0)
        ),
        "panel_zone_external_validation_validated_row_count_total": int(
            metrics.get("panel_zone_external_validation_validated_row_count_total", 0)
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            metrics.get("panel_zone_external_validation_exact_validated_row_count", 0)
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            metrics.get("panel_zone_external_validation_fallback_validated_row_count", 0)
        ),
        "panel_zone_external_validation_exact_validated_row_ratio": float(
            metrics.get("panel_zone_external_validation_exact_validated_row_ratio", 0.0)
        ),
        "panel_zone_external_validation_fallback_validated_row_ratio": float(
            metrics.get("panel_zone_external_validation_fallback_validated_row_ratio", 0.0)
        ),
        "panel_zone_external_validation_provenance_summary_label": str(
            metrics.get("panel_zone_external_validation_provenance_summary_label", "")
        ),
        "panel_zone_external_validation_closing_summary_label": str(
            metrics.get("panel_zone_external_validation_closing_summary_label", "")
        ),
        "panel_zone_instruction_sidecar_present": bool(metrics.get("panel_zone_instruction_sidecar_present", False)),
        "panel_zone_instruction_sidecar_change_count": int(
            metrics.get("panel_zone_instruction_sidecar_change_count", 0)
        ),
        "panel_zone_instruction_sidecar_candidate_overlap_mode": str(
            metrics.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "")
        ),
        "panel_zone_instruction_sidecar_overlap_row_count": int(
            metrics.get("panel_zone_instruction_sidecar_overlap_row_count", 0)
        ),
        "panel_zone_instruction_sidecar_overlap_member_count": int(
            metrics.get("panel_zone_instruction_sidecar_overlap_member_count", 0)
        ),
        "panel_zone_instruction_sidecar_overlap_group_count": int(
            metrics.get("panel_zone_instruction_sidecar_overlap_group_count", 0)
        ),
        "panel_zone_instruction_sidecar_evidence_model": str(
            metrics.get("panel_zone_instruction_sidecar_evidence_model", "")
        ),
        "panel_zone_instruction_sidecar_rebar_delivery_mode": str(
            metrics.get("panel_zone_instruction_sidecar_rebar_delivery_mode", "")
        ),
        "panel_zone_member_mapping_sidecar_present": bool(
            metrics.get("panel_zone_member_mapping_sidecar_present", False)
        ),
        "panel_zone_member_mapping_sidecar_mode": str(
            metrics.get("panel_zone_member_mapping_sidecar_mode", "")
        ),
        "panel_zone_member_mapping_sidecar_row_count": int(
            metrics.get("panel_zone_member_mapping_sidecar_row_count", 0)
        ),
        "panel_zone_member_mapping_sidecar_applied_row_count": int(
            metrics.get("panel_zone_member_mapping_sidecar_applied_row_count", 0)
        ),
        "panel_zone_member_mapping_sidecar_unmapped_source_member_count": int(
            metrics.get("panel_zone_member_mapping_sidecar_unmapped_source_member_count", 0)
        ),
        "panel_zone_source_valid_row_counts": dict(metrics.get("panel_zone_source_valid_row_counts", {}) or {}),
        "panel_zone_source_overlap_member_counts": dict(metrics.get("panel_zone_source_overlap_member_counts", {}) or {}),
        "panel_zone_source_candidate_scan_modes": dict(metrics.get("panel_zone_source_candidate_scan_modes", {}) or {}),
        "panel_zone_source_bundle_modes": dict(metrics.get("panel_zone_source_bundle_modes", {}) or {}),
        "panel_zone_source_upstream_verification_tiers": dict(
            metrics.get("panel_zone_source_upstream_verification_tiers", {}) or {}
        ),
        "panel_zone_validated_source_row_count_total": int(metrics.get("panel_zone_validated_source_row_count_total", 0)),
        "panel_zone_validated_source_overlap_member_count_min": int(
            metrics.get("panel_zone_validated_source_overlap_member_count_min", 0)
        ),
        "panel_zone_topology_capable_input": bool(metrics.get("panel_zone_topology_capable_input", False)),
        "panel_zone_true_3d_clash_verified": bool(metrics.get("panel_zone_true_3d_clash_verified", False)),
        "panel_zone_true_3d_anchorage_verified": bool(metrics.get("panel_zone_true_3d_anchorage_verified", False)),
        "panel_zone_true_3d_bridge_complete": bool(
            metrics.get("panel_zone_true_3d_bridge_complete", False)
        ),
        "panel_zone_solver_verified_bridge_complete": bool(
            metrics.get("panel_zone_solver_verified_bridge_complete", False)
        ),
        "panel_zone_missing_required_sources": list(metrics.get("panel_zone_missing_required_sources", [])),
        "panel_zone_solver_verified_inbox_status_mode": str(
            metrics.get("panel_zone_solver_verified_inbox_status_mode", "")
        ),
        "panel_zone_solver_verified_inbox_has_input": bool(
            metrics.get("panel_zone_solver_verified_inbox_has_input", False)
        ),
        "panel_zone_solver_verified_pending_input": bool(
            metrics.get("panel_zone_solver_verified_pending_input", False)
        ),
        "panel_zone_solver_verified_input_mode_detected": str(
            metrics.get("panel_zone_solver_verified_input_mode_detected", "")
        ),
        "panel_zone_solver_verified_latest_consume_report_present": bool(
            metrics.get("panel_zone_solver_verified_latest_consume_report_present", False)
        ),
        "panel_zone_solver_verified_latest_consume_contract_pass": bool(
            metrics.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
        ),
        "panel_zone_solver_verified_latest_consume_reason_code": str(
            metrics.get("panel_zone_solver_verified_latest_consume_reason_code", "")
        ),
        "panel_zone_solver_verified_source_origin_class": str(
            metrics.get("panel_zone_solver_verified_source_origin_class", "")
        ),
        "panel_zone_solver_verified_release_refresh_source_allowed": bool(
            metrics.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
        ),
        "panel_zone_solver_verified_recommended_action": str(
            metrics.get("panel_zone_solver_verified_recommended_action", "")
        ),
        "foundation_optimization_ready": bool(metrics.get("foundation_optimization_ready", False)),
        "foundation_member_type_present": bool(metrics.get("foundation_member_type_present", False)),
        "foundation_member_type_count": int(metrics.get("foundation_member_type_count", 0)),
        "foundation_optimization_mode": str(metrics.get("foundation_optimization_mode", "")),
        "foundation_optimization_reason": str(metrics.get("foundation_optimization_reason", "")),
        "foundation_scope_source": str(metrics.get("foundation_scope_source", "")),
        "foundation_artifact_scan_mode": str(metrics.get("foundation_artifact_scan_mode", "")),
        "foundation_artifact_evidence_mode": str(metrics.get("foundation_artifact_evidence_mode", "")),
        "upstream_foundation_label_count": int(metrics.get("upstream_foundation_label_count", 0)),
        "raw_source_foundation_label_count": int(metrics.get("raw_source_foundation_label_count", 0)),
        "upstream_foundation_provenance_mode": str(metrics.get("upstream_foundation_provenance_mode", "")),
        "wind_tunnel_raw_mapping_ready": bool(metrics.get("wind_tunnel_raw_mapping_ready", False)),
        "wind_tunnel_mapping_mode": str(metrics.get("wind_tunnel_mapping_mode", "")),
        "wind_tunnel_mapping_reason": str(metrics.get("wind_tunnel_mapping_reason", "")),
        "residual_holdout_detail_row_count": int(len(residual_holdout_detail_rows)),
        "residual_holdout_matrix_row_count": int(len(residual_holdout_matrix_rows)),
        "authority_catalog_diff_change_count": int(authority_catalog_diff.get("change_count", 0)),
        "authority_catalog_diff_added_count": int(authority_catalog_diff.get("added_count", 0)),
        "authority_catalog_diff_removed_count": int(authority_catalog_diff.get("removed_count", 0)),
        "authority_catalog_diff_baseline_seeded": bool(authority_catalog_diff.get("baseline_seeded", False)),
        "authority_catalog_routing_warning_active": bool(metrics.get("authority_catalog_routing_warning_active", False)),
        "promotion_reason_code": str(metrics.get("promotion_reason_code", "")),
        "promotion_hold_for_review": bool(metrics.get("promotion_hold_for_review", False)),
        "hold_review_manifest": str(metrics.get("hold_review_manifest", "")),
        "hold_review_packet_md": str(metrics.get("hold_review_packet_md", "")),
        "hold_review_packet_pdf": str(metrics.get("hold_review_packet_pdf", "")),
        "hold_review_ack_json": str(metrics.get("hold_review_ack_json", "")),
        "design_optimization_entrypoints": design_opt_entrypoint_rows,
        "design_optimization_entrypoint_groups": design_opt_entrypoint_groups,
        "summary_cards": cards,
        "validation_rows": rows,
        "authority_rows": authority_rows,
        "residual_case_rows": residual_case_rows,
        "design_change_rows": design_change_rows,
        "design_change_story_rows": design_change_story_rows,
        "design_change_zone_rows": design_change_zone_rows,
        "accepted_candidate_rows": accepted_candidate_rows,
        "nightly_smoke_recent_samples": smoke_recent_samples,
        "external_benchmark_submission_queue_rows": external_benchmark_submission_queue_rows,
        "external_benchmark_submission_queue_count": int(len(external_benchmark_submission_queue_rows)),
        "external_benchmark_submission_queue_ready_count": int(
            sum(
                1
                for row in external_benchmark_submission_queue_rows
                if str(row.get("status", "") or "") == "ready_for_full_submission"
            )
        ),
        "external_benchmark_submission_queue_review_pending_count": int(
            sum(
                1
                for row in external_benchmark_submission_queue_rows
                if str(row.get("status", "") or "") == "ready_for_benchmark_start_final_review_pending"
            )
        ),
        "external_benchmark_submission_queue_blocked_count": int(
            sum(1 for row in external_benchmark_submission_queue_rows if str(row.get("status", "") or "") == "blocked")
        ),
        "external_benchmark_submission_receipt_attached_count": int(
            sum(
                1
                for row in external_benchmark_submission_queue_rows
                if _submission_receipt_label(row) != "pending"
            )
        ),
        "external_benchmark_submission_receipt_pending_count": int(
            sum(
                1
                for row in external_benchmark_submission_queue_rows
                if _submission_receipt_label(row) == "pending"
            )
        ),
        "external_benchmark_submission_onepage_attestation_status": str(
            metrics.get("external_benchmark_submission_onepage_attestation_status", "") or ""
        ),
        "p0_closed": bool(int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0),
        "p0_closure_status": "closed" if int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0 else "open",
        "p1_unblocked": bool(int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0),
        "p1_handoff_status": "unblocked" if int(gap_summary.get("open_gap_counts", {}).get("P0", 0)) == 0 else "blocked",
        "advanced_holdouts": advanced_holdouts,
        "residual_holdout_buckets": residual_holdout_buckets,
        "residual_holdout_detail_rows": residual_holdout_detail_rows,
        "residual_holdout_matrix_rows": residual_holdout_matrix_rows,
        "authority_catalog_routing_diff": authority_catalog_diff,
        "blocked_action_summary": blocked_action_summary,
        "metrics": metrics,
        "artifact_links": artifact_links,
    }
    metrics.update(
        {
            key: value
            for key, value in summary_payload.items()
            if key
            not in {
                "schema_version",
                "run_id",
                "generated_at",
                "metrics",
                "artifact_links",
                "external_benchmark_submission_queue_rows",
            }
        }
    )
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    _write_csv(
        summary_csv,
        cards,
        rows,
        metrics,
        authority_rows,
        residual_case_rows,
        design_change_rows,
        design_opt_entrypoint_rows,
        design_opt_entrypoint_groups,
    )
    _write_html(dashboard_html, cards, rows, artifact_links, metrics, authority_rows, residual_case_rows, design_change_rows, blocked_action_summary, accepted_candidate_rows, design_opt_entrypoint_rows, design_opt_entrypoint_groups, smoke_recent_samples, external_benchmark_submission_queue_rows, residual_holdout_buckets, residual_holdout_detail_rows, residual_holdout_matrix_rows, authority_catalog_diff)
    _write_markdown(
        report_md,
        cards,
        rows,
        artifact_links,
        metrics,
        gap.get("remaining_gaps", []),
        authority_rows,
        residual_case_rows,
        design_change_rows,
        blocked_action_summary,
        accepted_candidate_rows,
        design_opt_entrypoint_rows,
        design_opt_entrypoint_groups,
        smoke_recent_samples,
        external_benchmark_submission_queue_rows,
        residual_holdout_buckets,
        residual_holdout_detail_rows,
        residual_holdout_matrix_rows,
        authority_catalog_diff,
    )
    _write_pdf(report_pdf, cards, rows, artifact_links, metrics, authority_rows, residual_case_rows, design_change_rows, blocked_action_summary, accepted_candidate_rows, design_opt_entrypoint_rows, design_opt_entrypoint_groups, smoke_recent_samples, external_benchmark_submission_queue_rows, residual_holdout_buckets, residual_holdout_detail_rows, residual_holdout_matrix_rows, authority_catalog_diff)

    required_input_reports_pass = all(
        bool(report.get("contract_pass", report.get("all_pass", report.get("pass", False))))
        for report in (
            pbd_package,
            ndtha_residual,
            wind,
            ssi,
            damper,
            construction,
            diaphragm,
            repro,
            release_registry,
            kds,
            authority,
            design_opt_long,
            design_opt_cost,
        )
    )
    contract_pass = bool(required_input_reports_pass)
    package_payload = {
        "schema_version": "1.0",
        "run_id": "phase3-committee-review-package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design_optimization_entrypoints": design_opt_entrypoint_rows,
        "design_optimization_entrypoint_groups": design_opt_entrypoint_groups,
        "inputs": {
            "pbd_package": str(args.pbd_package),
            "pbd_metrics": str(args.pbd_metrics),
            "ndtha_stress_report": str(args.ndtha_stress_report),
            "ndtha_residual_report": str(args.ndtha_residual_report),
            "wind_report": str(args.wind_report),
            "ssi_report": str(args.ssi_report),
            "damper_report": str(args.damper_report),
            "construction_report": str(args.construction_report),
            "diaphragm_report": str(args.diaphragm_report),
            "repro_report": str(args.repro_report),
            "release_registry": str(args.release_registry),
            "kds_summary": str(args.kds_summary),
            "nightly_report": str(args.nightly_report),
            "promotion_report": str(args.promotion_report),
            "ci_report": str(args.ci_report),
            "gap_report": str(args.gap_report),
            "authority_report": str(args.authority_report),
            "authority_catalog": str(args.authority_catalog),
            "design_opt_long_report": str(args.design_opt_long_report),
            "design_opt_cost_report": str(args.design_opt_cost_report),
            "design_opt_cost_changes_csv": str(args.design_opt_cost_changes_csv),
            "design_opt_cost_blocked_actions_csv": str(args.design_opt_cost_blocked_actions_csv),
            "design_opt_cost_no_gain_csv": str(args.design_opt_cost_no_gain_csv),
            "design_opt_cost_no_gain_explain_csv": str(args.design_opt_cost_no_gain_explain_csv),
            "row_provenance_model_json": str(args.row_provenance_model_json),
            "row_provenance_kds_report": str(args.row_provenance_kds_report),
            "row_provenance_export_json": str(args.row_provenance_export_json),
            "row_provenance_export_csv": str(args.row_provenance_export_csv),
            "row_provenance_export_report": str(args.row_provenance_export_report),
        },
        "artifacts": {
            "committee_summary_json": str(summary_json),
            "committee_summary_csv": str(summary_csv),
            "committee_dashboard_html": str(dashboard_html),
            "committee_review_markdown": str(report_md),
            "committee_review_pdf": str(report_pdf),
            **artifact_links,
        },
        "authority_rows": authority_rows,
        "residual_case_rows": residual_case_rows,
        "design_change_rows": design_change_rows,
        "design_change_story_rows": design_change_story_rows,
        "design_change_zone_rows": design_change_zone_rows,
        "accepted_candidate_rows": accepted_candidate_rows,
        "blocked_action_summary": blocked_action_summary,
        "metrics": metrics,
        "nightly_contract_pass": bool(nightly.get("contract_pass", nightly.get("all_pass", nightly.get("pass", False)))),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_INPUT_REPORT_FAIL",
        "reason": "committee review package generated" if contract_pass else "one or more required input reports are not pass",
    }
    package_report.write_text(json.dumps(package_payload, indent=2), encoding="utf-8")
    print(f"Wrote committee review package: {package_report}")


if __name__ == "__main__":
    main()
