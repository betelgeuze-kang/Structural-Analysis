#!/usr/bin/env python3
"""Suggest bounded section/detailing updates from code-check evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.design_optimization_env import ACTION_FAMILY_BY_NAME
except ImportError:  # pragma: no cover - script execution fallback
    from design_optimization_env import ACTION_FAMILY_BY_NAME


REASONS = {
    "PASS": "section optimization suggestions generated",
    "ERR_INPUT": "invalid section optimizer input",
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


def _accepted_action_lookup(design_optimization_report: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(design_optimization_report, dict):
        return lookup
    for row in design_optimization_report.get("accepted_head") or []:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("member_id") or row.get("baseline_focus_member_id") or "").strip()
        if not member_id:
            continue
        lookup.setdefault(member_id, []).append(row)
    return lookup


def _group_change_lookup(change_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for row in change_rows:
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        lookup.setdefault(group_id, []).append(row)
    return lookup


def _member_governing_rows(code_check_report: dict[str, Any]) -> list[dict[str, Any]]:
    member_check_rows = code_check_report.get("member_check_rows")
    if not isinstance(member_check_rows, list):
        raise ValueError("code check report missing member_check_rows")
    summary_rows = code_check_report.get("rows")
    summary_by_member = {
        str(row.get("member_id", "")).strip(): row
        for row in (summary_rows if isinstance(summary_rows, list) else [])
        if isinstance(row, dict) and str(row.get("member_id", "")).strip()
    }
    governing_by_member: dict[str, dict[str, Any]] = {}
    for row in member_check_rows:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("member_id", "")).strip()
        if not member_id:
            continue
        dcr = _safe_float(row.get("dcr"), 0.0)
        if not math.isfinite(dcr):
            continue
        existing = governing_by_member.get(member_id)
        if existing is None or dcr >= _safe_float(existing.get("dcr"), -math.inf):
            governing_by_member[member_id] = dict(row)
    out: list[dict[str, Any]] = []
    for member_id, governing in governing_by_member.items():
        summary_row = summary_by_member.get(member_id, {})
        out.append(
            {
                "member_id": member_id,
                "case_id": str(governing.get("case_id", summary_row.get("case_id", "")) or ""),
                "member_type": str(governing.get("member_type", summary_row.get("member_type", "generic_frame")) or "generic_frame"),
                "hazard_type": str(governing.get("hazard_type", summary_row.get("hazard_type", "")) or ""),
                "topology_type": str(governing.get("topology_type", summary_row.get("topology_type", "")) or ""),
                "governing_component": str(governing.get("component", summary_row.get("governing_component", "")) or ""),
                "governing_clause": str(governing.get("clause", "") or ""),
                "governing_combination": str(governing.get("combination", summary_row.get("governing_combination", "")) or ""),
                "max_dcr": float(_safe_float(summary_row.get("max_dcr"), governing.get("dcr"))),
                "governing_dcr": float(dcr),
            }
        )
    out.sort(key=lambda row: float(row["max_dcr"]), reverse=True)
    return out


def _direction(max_dcr: float, *, strengthen_trigger_dcr: float, reduce_trigger_dcr: float) -> str:
    if float(max_dcr) > float(strengthen_trigger_dcr):
        return "strengthen"
    if float(max_dcr) < float(reduce_trigger_dcr):
        return "reduce"
    return "hold"


def _default_action_name(
    *,
    member_type: str,
    governing_component: str,
    governing_clause: str,
    direction: str,
) -> str:
    member = str(member_type).strip().lower()
    component = str(governing_component).strip().lower()
    clause = str(governing_clause).strip().lower()
    if direction == "strengthen":
        if member == "beam":
            return "rebar_up" if "shear" in component or "shear" in clause else "beam_section_up"
        if member == "column":
            return "perimeter_frame_up"
        if member == "wall":
            return "core_wall_up" if "boundary" in component or "drift" in component or "-be-" in clause else "wall_thickness_up"
        if member == "slab":
            return "slab_thickness_up" if "punch" in component or "punch" in clause else "rebar_up"
        if member == "foundation":
            return "pile_count_increase" if "bear" in component or "bear" in clause else "foundation_mat_thickness_up"
        if member == "connection":
            return "connection_detailing_up"
        return "rebar_up"
    if member == "beam":
        return "beam_section_down"
    if member == "column":
        return "perimeter_frame_down"
    if member == "wall":
        return "core_wall_down" if "boundary" in component or "drift" in component or "-be-" in clause else "wall_thickness_down"
    if member == "slab":
        return "slab_thickness_down"
    if member == "foundation":
        return "foundation_mat_thickness_down"
    if member == "connection":
        return "connection_detailing_down"
    return "rebar_down"


def _rationale(direction: str, governing_component: str, governing_clause: str) -> str:
    component = str(governing_component).strip().lower()
    clause = str(governing_clause).strip().lower()
    if direction == "strengthen":
        if "drift" in component:
            return "increase lateral stiffness to pull drift below the design target"
        if "boundary" in component or "-be-" in clause:
            return "increase wall boundary capacity to reduce governing compression demand"
        if "punch" in component or "punch" in clause:
            return "increase slab punching perimeter or thickness to recover punching margin"
        if "slip" in component or "rot" in component:
            return "tighten connection detailing to reduce slip and rotational demand"
        if "shear" in component or "shear" in clause:
            return "increase shear reinforcement/detailing to recover governing shear margin"
        return "increase section or reinforcement so the governing clause returns below the target DCR"
    return "harvest overstrength while preserving a practical DCR buffer and simplifying the package"


def _aligned_action_name(
    *,
    member_id: str,
    direction: str,
    fallback_action_name: str,
    accepted_lookup: dict[str, list[dict[str, Any]]],
) -> tuple[str, bool, str]:
    desired_suffix = "_up" if direction == "strengthen" else "_down"
    for row in accepted_lookup.get(member_id, []):
        action_name = str(row.get("action_name", "") or "").strip()
        if not action_name:
            continue
        if direction == "strengthen" and (
            action_name.endswith(desired_suffix) or action_name in {"anchorage_reinforce", "splice_reinforce", "pile_count_increase"}
        ):
            return action_name, True, str(row.get("viewer_row_url", "") or "")
        if direction == "reduce" and (
            action_name.endswith(desired_suffix) or action_name in {"anchorage_simplify", "splice_simplify", "pile_count_decrease"}
        ):
            return action_name, True, str(row.get("viewer_row_url", "") or "")
    return fallback_action_name, False, ""


def generate_section_suggestions(
    *,
    code_check_report: dict[str, Any],
    design_optimization_report: dict[str, Any] | None = None,
    design_change_rows: list[dict[str, Any]] | None = None,
    strengthen_trigger_dcr: float = 1.0,
    reduce_trigger_dcr: float = 0.65,
    target_dcr: float = 0.95,
    max_suggestions: int = 50,
) -> dict[str, Any]:
    governing_rows = _member_governing_rows(code_check_report)
    accepted_lookup = _accepted_action_lookup(design_optimization_report)
    change_lookup = _group_change_lookup(list(design_change_rows or []))
    suggestions: list[dict[str, Any]] = []

    for row in governing_rows:
        max_dcr = float(_safe_float(row.get("max_dcr"), 0.0))
        direction = _direction(
            max_dcr,
            strengthen_trigger_dcr=float(strengthen_trigger_dcr),
            reduce_trigger_dcr=float(reduce_trigger_dcr),
        )
        if direction == "hold":
            continue
        fallback_action_name = _default_action_name(
            member_type=str(row.get("member_type", "")),
            governing_component=str(row.get("governing_component", "")),
            governing_clause=str(row.get("governing_clause", "")),
            direction=direction,
        )
        action_name, design_opt_aligned, viewer_row_url = _aligned_action_name(
            member_id=str(row.get("member_id", "")),
            direction=direction,
            fallback_action_name=fallback_action_name,
            accepted_lookup=accepted_lookup,
        )
        action_family = ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        if direction == "strengthen":
            required_capacity_scale = max(max_dcr / max(float(target_dcr), 1.0e-9), 1.02)
            required_capacity_scale = min(required_capacity_scale, 1.40)
            estimated_max_dcr_after = max_dcr / required_capacity_scale
            priority = (max_dcr - float(target_dcr)) * 100.0 + 10.0
        else:
            utilization_ratio = max(max_dcr / max(float(reduce_trigger_dcr), 1.0e-9), 0.1)
            required_capacity_scale = max(utilization_ratio, 0.75)
            estimated_max_dcr_after = max_dcr / required_capacity_scale
            priority = (float(reduce_trigger_dcr) - max_dcr) * 50.0 + 2.5
        related_change_count = sum(
            len(rows)
            for group_id, rows in change_lookup.items()
            if str(row.get("member_id", "")) and str(row.get("member_id", "")) in group_id
        )
        suggestions.append(
            {
                "member_id": str(row.get("member_id", "")),
                "case_id": str(row.get("case_id", "")),
                "member_type": str(row.get("member_type", "")),
                "hazard_type": str(row.get("hazard_type", "")),
                "topology_type": str(row.get("topology_type", "")),
                "governing_component": str(row.get("governing_component", "")),
                "governing_clause": str(row.get("governing_clause", "")),
                "governing_combination": str(row.get("governing_combination", "")),
                "current_max_dcr": float(max_dcr),
                "direction": direction,
                "action_name": action_name,
                "action_family": action_family,
                "required_capacity_scale": float(required_capacity_scale),
                "estimated_max_dcr_after": float(estimated_max_dcr_after),
                "priority_score": float(priority),
                "rationale": _rationale(direction, str(row.get("governing_component", "")), str(row.get("governing_clause", ""))),
                "design_optimization_aligned": bool(design_opt_aligned),
                "design_optimization_viewer_row_url": viewer_row_url,
                "related_change_row_count": int(related_change_count),
            }
        )

    suggestions.sort(
        key=lambda row: (
            0 if str(row.get("direction", "")) == "strengthen" else 1,
            -float(row.get("priority_score", 0.0)),
            -float(row.get("current_max_dcr", 0.0)),
        )
    )
    suggestions = suggestions[: max(int(max_suggestions), 0)]

    over_limit_members = sum(1 for row in governing_rows if float(_safe_float(row.get("max_dcr"), 0.0)) > float(strengthen_trigger_dcr))
    covered_over_limit_members = sum(
        1
        for row in suggestions
        if str(row.get("direction", "")) == "strengthen"
    )
    action_family_counts: dict[str, int] = {}
    for row in suggestions:
        action_family = str(row.get("action_family", "") or "")
        action_family_counts[action_family] = int(action_family_counts.get(action_family, 0)) + 1

    checks = {
        "governing_clause_traceability_pass": bool(all(str(row.get("governing_clause", "")).strip() for row in suggestions)),
        "action_family_supported_pass": bool(all(str(row.get("action_name", "")) in ACTION_FAMILY_BY_NAME for row in suggestions)),
        "over_limit_covered_pass": bool(over_limit_members == 0 or covered_over_limit_members >= over_limit_members),
        "suggestion_table_present_pass": bool(len(governing_rows) == 0 or len(suggestions) > 0),
    }
    contract_pass = bool(all(checks.values()))
    summary = {
        "governing_member_count": int(len(governing_rows)),
        "suggestion_count": int(len(suggestions)),
        "strengthen_count": int(sum(1 for row in suggestions if str(row.get("direction", "")) == "strengthen")),
        "reduce_count": int(sum(1 for row in suggestions if str(row.get("direction", "")) == "reduce")),
        "design_optimization_aligned_count": int(sum(1 for row in suggestions if bool(row.get("design_optimization_aligned", False)))),
        "governing_clause_count": int(len({str(row.get("governing_clause", "")) for row in governing_rows if str(row.get("governing_clause", "")).strip()})),
        "over_limit_member_count": int(over_limit_members),
        "overdesigned_member_count": int(sum(1 for row in governing_rows if float(_safe_float(row.get("max_dcr"), 0.0)) < float(reduce_trigger_dcr))),
        "max_dcr": float(max((float(_safe_float(row.get("max_dcr"), 0.0)) for row in governing_rows), default=0.0)),
        "suggestion_action_family_counts": dict(sorted(action_family_counts.items())),
    }
    summary_line = (
        f"Section optimizer: {'PASS' if contract_pass else 'CHECK'} | "
        f"suggestions={summary['suggestion_count']}(strengthen={summary['strengthen_count']},reduce={summary['reduce_count']},aligned={summary['design_optimization_aligned_count']}) | "
        f"members={summary['governing_member_count']} | "
        f"max_dcr={summary['max_dcr']:.3f} | "
        f"clauses={summary['governing_clause_count']} | "
        "families="
        + ",".join(f"{key}={value}" for key, value in summary["suggestion_action_family_counts"].items())
    )
    return {
        "schema_version": "1.0",
        "report_family": "section_optimizer",
        "run_id": "phase1-section-optimizer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "strengthen_trigger_dcr": float(strengthen_trigger_dcr),
            "reduce_trigger_dcr": float(reduce_trigger_dcr),
            "target_dcr": float(target_dcr),
            "max_suggestions": int(max_suggestions),
            "design_optimization_report_present": bool(isinstance(design_optimization_report, dict)),
            "design_change_row_count": int(len(design_change_rows or [])),
        },
        "summary": summary,
        "checks": checks,
        "governing_rows": governing_rows,
        "suggestion_rows": suggestions,
        "summary_line": summary_line,
        "contract_pass": bool(contract_pass),
        "reason_code": "PASS",
        "reason": REASONS["PASS"],
    }


def write_section_optimizer_artifacts(
    payload: dict[str, Any],
    *,
    out_json: Path,
    out_csv: Path | None = None,
) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if out_csv is None:
        return
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = payload.get("suggestion_rows")
    if not isinstance(rows, list):
        rows = []
    fieldnames = [
        "member_id",
        "case_id",
        "member_type",
        "governing_component",
        "governing_clause",
        "current_max_dcr",
        "direction",
        "action_name",
        "action_family",
        "required_capacity_scale",
        "estimated_max_dcr_after",
        "priority_score",
        "design_optimization_aligned",
        "related_change_row_count",
        "rationale",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if isinstance(row, dict):
                writer.writerow({key: row.get(key, "") for key in fieldnames})


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
    parser.add_argument("--strengthen-trigger-dcr", type=float, default=1.0)
    parser.add_argument("--reduce-trigger-dcr", type=float, default=0.65)
    parser.add_argument("--target-dcr", type=float, default=0.95)
    parser.add_argument("--max-suggestions", type=int, default=50)
    parser.add_argument("--out", default="implementation/phase1/release/design_reports/section_optimizer_report.json")
    parser.add_argument("--csv-out", default="")
    args = parser.parse_args()

    out_json = Path(args.out)
    out_csv = Path(args.csv_out) if str(args.csv_out).strip() else out_json.with_suffix(".csv")
    try:
        payload = generate_section_suggestions(
            code_check_report=_load_json(Path(args.code_check_report)),
            design_optimization_report=(
                _load_json(Path(args.design_optimization_report))
                if Path(args.design_optimization_report).exists()
                else None
            ),
            design_change_rows=_load_csv_rows(Path(args.design_changes_csv) if Path(args.design_changes_csv).exists() else None),
            strengthen_trigger_dcr=float(args.strengthen_trigger_dcr),
            reduce_trigger_dcr=float(args.reduce_trigger_dcr),
            target_dcr=float(args.target_dcr),
            max_suggestions=int(args.max_suggestions),
        )
    except Exception as exc:
        payload = {
            "schema_version": "1.0",
            "report_family": "section_optimizer",
            "run_id": "phase1-section-optimizer",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "code_check_report": str(args.code_check_report),
                "design_optimization_report": str(args.design_optimization_report),
                "design_changes_csv": str(args.design_changes_csv),
            },
            "summary": {},
            "checks": {},
            "governing_rows": [],
            "suggestion_rows": [],
            "summary_line": "Section optimizer: CHECK | invalid input",
            "contract_pass": False,
            "reason_code": "ERR_INPUT",
            "reason": f"{REASONS['ERR_INPUT']}: {exc}",
        }
    write_section_optimizer_artifacts(payload, out_json=out_json, out_csv=out_csv)
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
