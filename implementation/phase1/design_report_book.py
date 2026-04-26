#!/usr/bin/env python3
"""Assemble a traceable design report book from code-check and optimization artifacts."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.external_design_sheet_diff import build_external_design_sheet_diff
    from implementation.phase1.section_optimizer import generate_section_suggestions
except ImportError:  # pragma: no cover - script execution fallback
    from external_design_sheet_diff import build_external_design_sheet_diff
    from section_optimizer import generate_section_suggestions


REASONS = {
    "PASS": "design report book generated",
    "ERR_INPUT": "invalid design report book input",
}


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected json object: {path}")
    return payload


def _load_csv_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _aggregate_clause_rows(member_check_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_clause: dict[str, dict[str, Any]] = {}
    for row in member_check_rows:
        clause = str(row.get("clause", "") or "").strip()
        if not clause:
            continue
        rec = by_clause.setdefault(
            clause,
            {
                "clause": clause,
                "member_count": 0,
                "ng_count": 0,
                "max_dcr": 0.0,
                "governing_member_id": "",
                "member_type_mix": set(),
                "rule_family_mix": set(),
            },
        )
        dcr = _safe_float(row.get("dcr"), 0.0)
        rec["member_count"] = int(rec["member_count"]) + 1
        if dcr > 1.0:
            rec["ng_count"] = int(rec["ng_count"]) + 1
        if dcr >= float(rec["max_dcr"]):
            rec["max_dcr"] = float(dcr)
            rec["governing_member_id"] = str(row.get("member_id", "") or "")
        rec["member_type_mix"].add(str(row.get("member_type", "") or ""))
        rec["rule_family_mix"].add(str(row.get("rule_family", "") or ""))
    out: list[dict[str, Any]] = []
    for rec in by_clause.values():
        out.append(
            {
                "clause": str(rec["clause"]),
                "member_count": int(rec["member_count"]),
                "ng_count": int(rec["ng_count"]),
                "max_dcr": float(rec["max_dcr"]),
                "governing_member_id": str(rec["governing_member_id"]),
                "member_type_mix": ",".join(sorted(item for item in rec["member_type_mix"] if item)),
                "rule_family_mix": ",".join(sorted(item for item in rec["rule_family_mix"] if item)),
            }
        )
    out.sort(key=lambda row: (float(row["max_dcr"]), int(row["ng_count"]), int(row["member_count"])), reverse=True)
    return out


def _aggregate_ng_rows(member_check_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in member_check_rows:
        dcr = _safe_float(row.get("dcr"), 0.0)
        if dcr <= 1.0:
            continue
        key = (
            str(row.get("combination", "") or ""),
            str(row.get("member_type", "") or ""),
            str(row.get("clause", "") or ""),
        )
        rec = grouped.setdefault(
            key,
            {
                "combination": key[0],
                "member_type": key[1],
                "clause": key[2],
                "ng_count": 0,
                "max_dcr": 0.0,
                "member_ids": set(),
            },
        )
        rec["ng_count"] = int(rec["ng_count"]) + 1
        rec["max_dcr"] = max(float(rec["max_dcr"]), float(dcr))
        rec["member_ids"].add(str(row.get("member_id", "") or ""))
    out: list[dict[str, Any]] = []
    for rec in grouped.values():
        out.append(
            {
                "combination": str(rec["combination"]),
                "member_type": str(rec["member_type"]),
                "clause": str(rec["clause"]),
                "ng_count": int(rec["ng_count"]),
                "max_dcr": float(rec["max_dcr"]),
                "member_ids": ",".join(sorted(item for item in rec["member_ids"] if item)[:6]),
            }
        )
    out.sort(key=lambda row: (int(row["ng_count"]), float(row["max_dcr"])), reverse=True)
    return out


def _aggregate_member_family_rows(member_check_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in member_check_rows:
        member_type = str(row.get("member_type", "generic_frame") or "generic_frame")
        rec = grouped.setdefault(
            member_type,
            {
                "member_type": member_type,
                "max_dcr": 0.0,
                "governing_clause": "",
                "governing_member_id": "",
            },
        )
        dcr = _safe_float(row.get("dcr"), 0.0)
        if dcr >= float(rec["max_dcr"]):
            rec["max_dcr"] = float(dcr)
            rec["governing_clause"] = str(row.get("clause", "") or "")
            rec["governing_member_id"] = str(row.get("member_id", "") or "")
    out = [dict(rec) for rec in grouped.values()]
    out.sort(key=lambda row: float(row["max_dcr"]), reverse=True)
    return out


def _optimization_change_rows(
    design_optimization_report: dict[str, Any] | None,
    design_change_rows: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(design_optimization_report, dict):
        for row in design_optimization_report.get("accepted_head") or []:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "member_id": str(row.get("member_id") or row.get("baseline_focus_member_id") or ""),
                    "member_type": str(row.get("member_type", "") or ""),
                    "action_name": str(row.get("action_name", "") or ""),
                    "action_family": str(row.get("action_family", "") or ""),
                    "governing_clause": str(row.get("governing_clause_label", "") or ""),
                    "projected_cost_delta": float(_safe_float(row.get("projected_cost_delta"), 0.0)),
                    "max_dcr": float(_safe_float(row.get("max_dcr"), 0.0)),
                    "viewer_row_url": str(row.get("viewer_row_url", "") or ""),
                }
            )
    if not out and design_change_rows:
        for row in design_change_rows:
            out.append(
                {
                    "member_id": "",
                    "member_type": str(row.get("member_type", "") or ""),
                    "action_name": str(row.get("action_name", "") or ""),
                    "action_family": str(row.get("action_family", "") or ""),
                    "governing_clause": str(row.get("governing_clause", "") or ""),
                    "projected_cost_delta": float(_safe_float(row.get("cost_proxy_delta"), 0.0)),
                    "max_dcr": float(_safe_float(row.get("max_dcr_after"), 0.0)),
                    "viewer_row_url": "",
                }
            )
    out.sort(key=lambda row: abs(float(row["projected_cost_delta"])), reverse=True)
    return out[:limit]


def build_design_report_book(
    *,
    code_check_report: dict[str, Any],
    design_optimization_report: dict[str, Any] | None = None,
    design_change_rows: list[dict[str, Any]] | None = None,
    section_optimizer_report: dict[str, Any] | None = None,
    external_design_sheet_diff_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    member_check_rows_raw = code_check_report.get("member_check_rows")
    if not isinstance(member_check_rows_raw, list):
        raise ValueError("code check report missing member_check_rows")
    member_check_rows = [row for row in member_check_rows_raw if isinstance(row, dict)]
    summary = code_check_report.get("summary")
    code_summary = summary if isinstance(summary, dict) else {}
    governing_rows = code_check_report.get("rows")
    governing_member_rows = [row for row in governing_rows if isinstance(row, dict)] if isinstance(governing_rows, list) else []
    clause_rows = _aggregate_clause_rows(member_check_rows)
    ng_group_rows = _aggregate_ng_rows(member_check_rows)
    member_family_rows = _aggregate_member_family_rows(member_check_rows)
    optimizer_payload = (
        section_optimizer_report
        if isinstance(section_optimizer_report, dict)
        else generate_section_suggestions(
            code_check_report=code_check_report,
            design_optimization_report=design_optimization_report,
            design_change_rows=list(design_change_rows or []),
        )
    )
    suggestion_rows = optimizer_payload.get("suggestion_rows")
    suggestions = [row for row in suggestion_rows if isinstance(row, dict)] if isinstance(suggestion_rows, list) else []
    optimization_head_rows = _optimization_change_rows(design_optimization_report, list(design_change_rows or []))
    external_diff_summary = (
        external_design_sheet_diff_report.get("summary")
        if isinstance((external_design_sheet_diff_report or {}).get("summary"), dict)
        else {}
    )
    external_diff_rows_raw = (
        external_design_sheet_diff_report.get("changed_rows")
        if isinstance((external_design_sheet_diff_report or {}).get("changed_rows"), list)
        else []
    )
    external_diff_rows = [row for row in external_diff_rows_raw if isinstance(row, dict)]

    traceable_rows = sum(1 for row in member_check_rows if str(row.get("clause", "")).strip())
    traceability_ratio = traceable_rows / max(len(member_check_rows), 1)
    ng_member_count = sum(1 for row in governing_member_rows if float(_safe_float(row.get("max_dcr"), 0.0)) > 1.0)
    design_summary = (
        design_optimization_report.get("summary")
        if isinstance((design_optimization_report or {}).get("summary"), dict)
        else {}
    )
    checks = {
        "governing_clause_traceability_pass": bool(traceability_ratio >= 0.999999),
        "dcr_table_present_pass": bool(len(member_check_rows) > 0),
        "governing_clause_table_present_pass": bool(len(clause_rows) > 0),
        "ng_grouping_present_pass": bool(len(ng_group_rows) > 0 or ng_member_count == 0),
        "section_suggestion_link_pass": bool(len(suggestions) > 0 or len(governing_member_rows) == 0),
        "external_sheet_diff_traceability_pass": bool(
            not isinstance(external_design_sheet_diff_report, dict)
            or (
                bool(external_diff_summary.get("key_field"))
                and int(external_diff_summary.get("shared_column_count", 0) or 0) > 0
            )
        ),
    }
    contract_pass = bool(all(checks.values()))
    report_summary = {
        "member_count": int(code_summary.get("member_count", len({str(row.get('member_id', '')).strip() for row in member_check_rows if str(row.get('member_id', '')).strip()}))),
        "member_check_row_count": int(code_summary.get("member_check_row_count", len(member_check_rows))),
        "clause_count": int(code_summary.get("clause_count", len(clause_rows))),
        "member_family_count": int(len(member_family_rows)),
        "max_dcr": float(_safe_float(code_summary.get("max_dcr"), max((_safe_float(row.get("dcr"), 0.0) for row in member_check_rows), default=0.0))),
        "governing_member_id": str(code_summary.get("governing_member_id", member_family_rows[0]["governing_member_id"] if member_family_rows else "")),
        "governing_clause": str(clause_rows[0]["clause"] if clause_rows else ""),
        "governing_clause_traceability_ratio": float(traceability_ratio),
        "ng_member_count": int(ng_member_count),
        "ng_group_count": int(len(ng_group_rows)),
        "suggestion_count": int(len(suggestions)),
        "optimization_change_row_count": int(len(optimization_head_rows)),
        "optimization_accepted_count": int(_safe_float(design_summary.get("accepted_count"), len(optimization_head_rows))),
        "optimization_cost_reduction_proxy": float(_safe_float(design_summary.get("cost_reduction_proxy"), 0.0)),
        "optimization_final_max_dcr": float(_safe_float(design_summary.get("final_max_dcr"), 0.0)),
        "external_sheet_diff_changed_row_count": int(external_diff_summary.get("changed_row_count", 0) or 0),
        "external_sheet_diff_added_row_count": int(external_diff_summary.get("added_row_count", 0) or 0),
        "external_sheet_diff_removed_row_count": int(external_diff_summary.get("removed_row_count", 0) or 0),
        "external_sheet_diff_key_field": str(external_diff_summary.get("key_field", "") or ""),
        "external_sheet_diff_max_numeric_delta": float(_safe_float(external_diff_summary.get("max_numeric_delta"), 0.0)),
        "design_contract_pass": bool(code_check_report.get("contract_pass", False)),
        "section_optimizer_contract_pass": bool(optimizer_payload.get("contract_pass", False)),
    }
    summary_line = (
        f"Design report book: {'PASS' if contract_pass else 'CHECK'} | "
        f"members={report_summary['member_count']} | "
        f"checks={report_summary['member_check_row_count']} | "
        f"max_dcr={report_summary['max_dcr']:.3f} | "
        f"trace={report_summary['governing_clause_traceability_ratio'] * 100.0:.1f}% | "
        f"ng={report_summary['ng_member_count']} | "
        f"suggestions={report_summary['suggestion_count']} | "
        f"opt_changes={report_summary['optimization_change_row_count']} | "
        f"sheet_diff={report_summary['external_sheet_diff_changed_row_count']}"
    )
    return {
        "schema_version": "1.0",
        "report_family": "design_report_book",
        "run_id": "phase1-design-report-book",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_report_present": bool(isinstance(design_optimization_report, dict)),
            "design_change_row_count": int(len(design_change_rows or [])),
            "external_design_sheet_diff_report_present": bool(isinstance(external_design_sheet_diff_report, dict)),
        },
        "summary": report_summary,
        "checks": checks,
        "governing_clause_rows": clause_rows[:100],
        "ng_group_rows": ng_group_rows[:100],
        "member_family_rows": member_family_rows,
        "dcr_table_head": sorted(member_check_rows, key=lambda row: float(_safe_float(row.get("dcr"), 0.0)), reverse=True)[:200],
        "section_suggestion_rows": suggestions[:100],
        "optimization_change_rows": optimization_head_rows,
        "external_sheet_diff_rows": external_diff_rows[:50],
        "summary_line": summary_line,
        "contract_pass": bool(contract_pass),
        "reason_code": "PASS",
        "reason": REASONS["PASS"],
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    clause_rows = payload.get("governing_clause_rows") if isinstance(payload.get("governing_clause_rows"), list) else []
    ng_rows = payload.get("ng_group_rows") if isinstance(payload.get("ng_group_rows"), list) else []
    family_rows = payload.get("member_family_rows") if isinstance(payload.get("member_family_rows"), list) else []
    suggestion_rows = payload.get("section_suggestion_rows") if isinstance(payload.get("section_suggestion_rows"), list) else []
    optimization_rows = payload.get("optimization_change_rows") if isinstance(payload.get("optimization_change_rows"), list) else []
    external_sheet_diff_rows = payload.get("external_sheet_diff_rows") if isinstance(payload.get("external_sheet_diff_rows"), list) else []
    lines = [
        "# Design Report Book",
        "",
        f"- Generated at (UTC): `{payload.get('generated_at', '')}`",
        f"- Summary: `{payload.get('summary_line', '')}`",
        "",
        "## Summary",
        "",
        f"- Members: `{summary.get('member_count', 0)}`",
        f"- Member checks: `{summary.get('member_check_row_count', 0)}`",
        f"- Governing max DCR: `{float(_safe_float(summary.get('max_dcr'), 0.0)):.4f}`",
        f"- Governing clause traceability: `{float(_safe_float(summary.get('governing_clause_traceability_ratio'), 0.0)) * 100.0:.1f}%`",
        f"- NG members: `{summary.get('ng_member_count', 0)}`",
        f"- Suggestions: `{summary.get('suggestion_count', 0)}`",
        f"- External sheet diff rows: `{summary.get('external_sheet_diff_changed_row_count', 0)}`",
        "",
        "## Governing Clause Table",
        "",
        "| Clause | Members | NG | Max DCR | Governing Member |",
        "|---|---:|---:|---:|---|",
    ]
    for row in clause_rows[:20]:
        if isinstance(row, dict):
            lines.append(
                f"| {row.get('clause','')} | {int(row.get('member_count',0))} | {int(row.get('ng_count',0))} | {float(_safe_float(row.get('max_dcr'),0.0)):.4f} | {row.get('governing_member_id','')} |"
            )
    lines.extend(["", "## NG Grouping", "", "| Combination | Member Type | Clause | NG | Max DCR |", "|---|---|---|---:|---:|"])
    for row in ng_rows[:20]:
        if isinstance(row, dict):
            lines.append(
                f"| {row.get('combination','')} | {row.get('member_type','')} | {row.get('clause','')} | {int(row.get('ng_count',0))} | {float(_safe_float(row.get('max_dcr'),0.0)):.4f} |"
            )
    lines.extend(["", "## Member Family Envelope", "", "| Member Type | Max DCR | Governing Clause | Governing Member |", "|---|---:|---|---|"])
    for row in family_rows[:20]:
        if isinstance(row, dict):
            lines.append(
                f"| {row.get('member_type','')} | {float(_safe_float(row.get('max_dcr'),0.0)):.4f} | {row.get('governing_clause','')} | {row.get('governing_member_id','')} |"
            )
    lines.extend(["", "## Section Suggestions", "", "| Member | Type | Direction | Action | Clause | Current DCR | Estimated After |", "|---|---|---|---|---|---:|---:|"])
    for row in suggestion_rows[:20]:
        if isinstance(row, dict):
            lines.append(
                f"| {row.get('member_id','')} | {row.get('member_type','')} | {row.get('direction','')} | {row.get('action_name','')} | {row.get('governing_clause','')} | {float(_safe_float(row.get('current_max_dcr'),0.0)):.4f} | {float(_safe_float(row.get('estimated_max_dcr_after'),0.0)):.4f} |"
            )
    if optimization_rows:
        lines.extend(["", "## Optimization Linkage", "", "| Member | Type | Action | Clause | Cost Delta | Max DCR |", "|---|---|---|---|---:|---:|"])
        for row in optimization_rows[:20]:
            if isinstance(row, dict):
                lines.append(
                    f"| {row.get('member_id','')} | {row.get('member_type','')} | {row.get('action_name','')} | {row.get('governing_clause','')} | {float(_safe_float(row.get('projected_cost_delta'),0.0)):.4f} | {float(_safe_float(row.get('max_dcr'),0.0)):.4f} |"
                )
    if external_sheet_diff_rows:
        lines.extend(["", "## External Sheet Diff", "", "| Row Key | Changed Columns | Max Numeric Delta |", "|---|---|---:|"])
        for row in external_sheet_diff_rows[:20]:
            if isinstance(row, dict):
                changed_columns = ",".join(str(item) for item in (row.get("changed_columns") or []) if str(item).strip())
                lines.append(
                    f"| {row.get('row_key','')} | {changed_columns} | {float(_safe_float(row.get('max_numeric_delta'),0.0)):.4f} |"
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_design_report_book_artifacts(
    payload: dict[str, Any],
    *,
    out_json: Path,
    out_md: Path | None = None,
) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if out_md is not None:
        _write_markdown(out_md, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-check-report", default="implementation/phase1/release/kds_compliance/code_check_report.json")
    parser.add_argument(
        "--design-optimization-report",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_report.json",
    )
    parser.add_argument(
        "--design-changes-csv",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.csv",
    )
    parser.add_argument("--section-optimizer-report", default="")
    parser.add_argument("--external-design-sheet-diff-report", default="")
    parser.add_argument("--external-design-sheet-baseline", default="")
    parser.add_argument("--external-design-sheet-revised", default="")
    parser.add_argument("--out", default="implementation/phase1/release/design_reports/design_report_book.json")
    parser.add_argument("--md-out", default="")
    args = parser.parse_args()

    out_json = Path(args.out)
    out_md = Path(args.md_out) if str(args.md_out).strip() else out_json.with_suffix(".md")
    try:
        payload = build_design_report_book(
            code_check_report=_load_json(Path(args.code_check_report)),
            design_optimization_report=(
                _load_json(Path(args.design_optimization_report))
                if Path(args.design_optimization_report).exists()
                else None
            ),
            design_change_rows=_load_csv_rows(Path(args.design_changes_csv) if Path(args.design_changes_csv).exists() else None),
            section_optimizer_report=(
                _load_json(Path(args.section_optimizer_report))
                if str(args.section_optimizer_report).strip() and Path(args.section_optimizer_report).exists()
                else None
            ),
            external_design_sheet_diff_report=(
                _load_json(Path(args.external_design_sheet_diff_report))
                if str(args.external_design_sheet_diff_report).strip() and Path(args.external_design_sheet_diff_report).exists()
                else build_external_design_sheet_diff(
                    baseline_path=Path(args.external_design_sheet_baseline),
                    revised_path=Path(args.external_design_sheet_revised),
                )
                if str(args.external_design_sheet_baseline).strip()
                and str(args.external_design_sheet_revised).strip()
                and Path(args.external_design_sheet_baseline).exists()
                and Path(args.external_design_sheet_revised).exists()
                else None
            ),
        )
    except Exception as exc:
        payload = {
            "schema_version": "1.0",
            "report_family": "design_report_book",
            "run_id": "phase1-design-report-book",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "code_check_report": str(args.code_check_report),
                "design_optimization_report": str(args.design_optimization_report),
                "design_changes_csv": str(args.design_changes_csv),
                "section_optimizer_report": str(args.section_optimizer_report),
                "external_design_sheet_diff_report": str(args.external_design_sheet_diff_report),
            },
            "summary": {},
            "checks": {},
            "governing_clause_rows": [],
            "ng_group_rows": [],
            "member_family_rows": [],
            "dcr_table_head": [],
            "section_suggestion_rows": [],
            "optimization_change_rows": [],
            "external_sheet_diff_rows": [],
            "summary_line": "Design report book: CHECK | invalid input",
            "contract_pass": False,
            "reason_code": "ERR_INPUT",
            "reason": f"{REASONS['ERR_INPUT']}: {exc}",
        }
    write_design_report_book_artifacts(payload, out_json=out_json, out_md=out_md)
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
