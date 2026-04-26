from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _default_results_card(member_type: object) -> str:
    normalized = _normalize_text(member_type).lower()
    if normalized in {"beam", "column", "brace", "wall", "slab"}:
        return "envelope"
    return "envelope"


def _build_event_handoff(event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in event_rows if isinstance(row, dict)]
    if not rows:
        return {
            "member_id": "",
            "load_case": "",
            "row_ref": "",
            "viewer_row_url": "",
            "viewer_slice_url": "",
            "overlay_row_id": "",
            "results_card": "envelope",
            "results_series_index": 0,
            "results_companion": "checks",
            "results_detail_block": "chart",
            "codecheck_companion": "summary",
            "codecheck_detail_block": "row-provenance",
            "codecheck_appendix_block": "",
            "overlay_focus": "",
            "overlay_member_id": "",
            "overlay_group_id": "",
            "overlay_group_index": "",
            "overlay_action_name": "",
            "overlay_story_band": "",
            "overlay_zone_label": "",
            "overlay_selected_event_index": "",
        }

    representative = sorted(
        rows,
        key=lambda row: (
            -_safe_float(row.get("projected_cost_delta")),
            -_safe_float(row.get("max_dcr")),
            _normalize_text(row.get("group_id")),
        ),
    )[0]
    results_card = _normalize_text(
        representative.get("recommended_results_card") or representative.get("results_card")
    ).lower() or _default_results_card(representative.get("member_type"))
    results_series_index = _safe_int(
        representative.get("recommended_results_series_index")
        if representative.get("recommended_results_series_index") not in (None, "")
        else 0,
        0,
    )
    return {
        "member_id": _normalize_text(
            representative.get("member_id")
            or representative.get("baseline_focus_member_id")
            or representative.get("case_id")
        ),
        "load_case": _normalize_text(
            representative.get("combination_name") or representative.get("load_case")
        ),
        "row_ref": _normalize_text(
            representative.get("viewer_row_ref") or representative.get("row_ref")
        ),
        "viewer_row_url": _normalize_text(representative.get("viewer_row_url")),
        "viewer_slice_url": _normalize_text(representative.get("viewer_slice_url")),
        "overlay_row_id": _normalize_text(
            representative.get("viewer_overlay_row_id") or representative.get("overlay_row_id")
        ),
        "results_card": results_card,
        "results_series_index": results_series_index,
        "results_companion": "checks",
        "results_detail_block": "chart",
        "codecheck_companion": "summary",
        "codecheck_detail_block": "row-provenance",
        "codecheck_appendix_block": "",
        "overlay_focus": "member",
        "overlay_member_id": _normalize_text(
            representative.get("member_id") or representative.get("baseline_focus_member_id")
        ),
        "overlay_group_id": _normalize_text(representative.get("group_id")),
        "overlay_group_index": _normalize_text(representative.get("group_index")),
        "overlay_action_name": _normalize_text(representative.get("action_name")),
        "overlay_story_band": _normalize_text(representative.get("story_band")),
        "overlay_zone_label": _normalize_text(representative.get("zone_label")),
        "overlay_selected_event_index": _normalize_text(representative.get("selected_event_index")),
    }


def build_demo_payload() -> dict[str, Any]:
    history = [
        {"iter": 0, "cost": 1.000, "dcr": 1.160, "penalty": 0.420, "modified": 0, "event_label": "baseline"},
        {"iter": 1, "cost": 0.948, "dcr": 1.080, "penalty": 0.388, "modified": 3, "event_label": "beam section down x2, detailing down x1"},
        {"iter": 2, "cost": 0.902, "dcr": 1.020, "penalty": 0.364, "modified": 5, "event_label": "wall thickness down x2"},
        {"iter": 3, "cost": 0.861, "dcr": 0.991, "penalty": 0.339, "modified": 7, "event_label": "rebar down x1, slab thickness down x1"},
        {"iter": 4, "cost": 0.842, "dcr": 0.978, "penalty": 0.326, "modified": 8, "event_label": "connection detailing down x1"},
    ]
    return {
        "schema_version": "0.1.0",
        "viewer_family": "optimization_history_viewer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "demo_fallback",
        "source_artifacts": {},
        "summary": {
            "title": "Optimization Convergence History",
            "status_label": "Demo fallback",
            "status_tone": "warning",
            "source_label": "embedded demo series",
            "iteration_count": len(history) - 1,
            "iteration_budget": len(history) - 1,
            "accepted_count": len(history) - 1,
            "changed_group_count": history[-1]["modified"],
            "baseline_cost_proxy": history[0]["cost"],
            "final_cost_proxy": history[-1]["cost"],
            "cost_reduction_proxy": history[0]["cost"] - history[-1]["cost"],
            "baseline_max_dcr": history[0]["dcr"],
            "final_max_dcr": history[-1]["dcr"],
            "baseline_penalty": history[0]["penalty"],
            "final_penalty": history[-1]["penalty"],
            "modified_total": history[-1]["modified"],
            "objective_profile": "demo",
            "budget_mode": "demo",
            "solver_backend_static": "demo",
            "solver_backend_ndtha": "demo",
        },
        "charts": {
            "cost": {"title": "Normalized Cost Proxy", "value_format": "number3"},
            "dcr": {"title": "Max D/C Ratio (Constraint < 1.0)", "value_format": "number3", "threshold": 1.0},
            "penalty": {"title": "Constructability Penalty Proxy", "value_format": "number3"},
            "modified": {"title": "Cumulative Modified Groups", "value_format": "integer"},
        },
        "history": history,
    }


def _build_event_rows(
    report_payload: dict[str, Any],
    accepted_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    inputs = report_payload.get("inputs") if isinstance(report_payload.get("inputs"), dict) else {}
    accepted_rows = accepted_payload.get("accepted_candidate_explain_rows")
    if not isinstance(accepted_rows, list):
        return []

    selected_rows = [row for row in accepted_rows if isinstance(row, dict) and bool(row.get("selected_in_final_loop", False))]
    selected_rows = [row for row in selected_rows if int(row.get("selected_event_index", 0) or 0) > 0]
    if not selected_rows:
        return []

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(selected_rows, key=lambda item: (int(item.get("selected_event_index", 0) or 0), str(item.get("group_id", "")))):
        grouped[int(row.get("selected_event_index", 0) or 0)].append(row)

    baseline_cost = _safe_float(summary.get("baseline_cost_proxy"))
    final_cost = _safe_float(summary.get("final_cost_proxy"), baseline_cost)
    baseline_dcr = _safe_float(summary.get("baseline_max_dcr"))
    final_dcr = _safe_float(summary.get("final_max_dcr"), baseline_dcr)
    baseline_penalty = _safe_float(summary.get("baseline_constructability_avg"))
    final_penalty = _safe_float(summary.get("final_constructability_avg"), baseline_penalty)

    cost_target = max(0.0, baseline_cost - final_cost)
    cost_projection_total = sum(
        max(0.0, _safe_float(row.get("projected_cost_delta")))
        for rows in grouped.values()
        for row in rows
    )
    cost_scale = (cost_target / cost_projection_total) if cost_projection_total > 1.0e-9 else 0.0

    penalty_target = max(0.0, baseline_penalty - final_penalty)
    penalty_projection_total = sum(
        max(0.0, _safe_float(row.get("constructability_gain")))
        for rows in grouped.values()
        for row in rows
    )
    penalty_scale = (penalty_target / penalty_projection_total) if penalty_projection_total > 1.0e-9 else 0.0

    rows: list[dict[str, Any]] = [
        {
            "iter": 0,
            "cost": baseline_cost,
            "dcr": baseline_dcr,
            "penalty": baseline_penalty,
            "modified": 0,
            "selected_count": 0,
            "event_label": "baseline repaired input",
            "event_note": "baseline before accepted final-loop changes",
            "handoff": _build_event_handoff([]),
        }
    ]

    cumulative_cost_projection = 0.0
    cumulative_penalty_projection = 0.0
    cumulative_unique_groups = 0
    cumulative_selected_rows = 0
    seen_groups: set[str] = set()
    running_dcr = baseline_dcr

    for event_index in sorted(grouped):
        event_rows = grouped[event_index]
        event_groups = {str(row.get("group_id", "") or "") for row in event_rows if str(row.get("group_id", "") or "")}
        new_groups = event_groups - seen_groups
        seen_groups.update(event_groups)
        cumulative_unique_groups += len(new_groups)
        cumulative_selected_rows += len(event_rows)

        cumulative_cost_projection += sum(max(0.0, _safe_float(row.get("projected_cost_delta"))) for row in event_rows)
        cumulative_penalty_projection += sum(max(0.0, _safe_float(row.get("constructability_gain"))) for row in event_rows)
        running_dcr = max(running_dcr, max((_safe_float(row.get("max_dcr")) for row in event_rows), default=running_dcr))

        family_counts = Counter(str(row.get("action_name", "") or "unknown") for row in event_rows)
        top_families = ", ".join(f"{name} x{count}" for name, count in sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))[:4])

        rows.append(
            {
                "iter": int(event_index),
                "cost": baseline_cost - (cumulative_cost_projection * cost_scale),
                "dcr": running_dcr,
                "penalty": baseline_penalty - (cumulative_penalty_projection * penalty_scale),
                "modified": cumulative_unique_groups,
                "selected_count": cumulative_selected_rows,
                "event_label": top_families or f"accepted batch {event_index}",
                "event_note": (
                    f"event {event_index}: +{len(new_groups)} new groups, "
                    f"+{len(event_rows)} selected rows, "
                    f"projected cost delta={sum(_safe_float(row.get('projected_cost_delta')) for row in event_rows):.3f}"
                ),
                "handoff": _build_event_handoff(event_rows),
            }
        )

    rows[-1]["cost"] = final_cost
    rows[-1]["dcr"] = final_dcr
    rows[-1]["penalty"] = final_penalty
    rows[-1]["modified"] = int(summary.get("changed_group_count", rows[-1]["modified"]) or rows[-1]["modified"])

    title = "Optimization Convergence History"
    status_label = "Feasible repaired slice" if bool(report_payload.get("contract_pass", False)) else str(report_payload.get("reason_code", "artifact loaded") or "artifact loaded")
    source_label = "cost reduction report + accepted candidate explain"

    return {
        "schema_version": "0.1.0",
        "viewer_family": "optimization_history_viewer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "report_plus_accepted_rows",
        "source_artifacts": {
            "report": str(inputs.get("out_json", "")) if inputs else "",
            "accepted_candidate_explain": str(inputs.get("accepted_candidate_explain_json_out", "")) if inputs else "",
            "reverse_sync": str(inputs.get("reverse_sync_json_out", "")) if inputs else "",
        },
        "summary": {
            "title": title,
            "status_label": status_label,
            "status_tone": "ok" if bool(report_payload.get("contract_pass", False)) else "warning",
            "source_label": source_label,
            "iteration_count": len(rows) - 1,
            "iteration_budget": int(inputs.get("effective_max_iterations", inputs.get("max_iterations", len(rows) - 1)) or len(rows) - 1),
            "accepted_count": int(summary.get("accepted_count", 0) or 0),
            "changed_group_count": int(summary.get("changed_group_count", 0) or 0),
            "baseline_cost_proxy": baseline_cost,
            "final_cost_proxy": final_cost,
            "cost_reduction_proxy": baseline_cost - final_cost,
            "baseline_max_dcr": baseline_dcr,
            "final_max_dcr": final_dcr,
            "baseline_penalty": baseline_penalty,
            "final_penalty": final_penalty,
            "modified_total": int(summary.get("changed_group_count", rows[-1]["modified"]) or rows[-1]["modified"]),
            "objective_profile": str(summary.get("objective_profile", "") or ""),
            "budget_mode": str(summary.get("budget_mode", "") or ""),
            "solver_backend_static": str(summary.get("solver_backend_static", "") or ""),
            "solver_backend_ndtha": str(summary.get("solver_backend_ndtha", "") or ""),
        },
        "charts": {
            "cost": {"title": "Cost Proxy", "value_format": "number1"},
            "dcr": {"title": "Max D/C Ratio", "value_format": "number3", "threshold": 1.0},
            "penalty": {"title": "Constructability Penalty Proxy", "value_format": "number3"},
            "modified": {"title": "Cumulative Modified Groups", "value_format": "integer"},
        },
        "history": rows,
    }


def build_payload(
    report_payload: dict[str, Any] | None,
    accepted_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(report_payload, dict) and isinstance(accepted_payload, dict):
        built = _build_event_rows(report_payload, accepted_payload)
        if built:
            return built
    return build_demo_payload()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate optimization history viewer payload from optimization artifacts.")
    parser.add_argument(
        "--report",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_report.json",
        help="Path to the design optimization cost reduction report JSON.",
    )
    parser.add_argument(
        "--accepted",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_accepted_candidate_explain.json",
        help="Path to the accepted candidate explain JSON.",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/release/visualization/optimization_history_viewer.json",
        help="Output payload path.",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    accepted_path = Path(args.accepted)
    out_path = Path(args.out)

    report_payload = _load_json(report_path) if report_path.exists() else None
    accepted_payload = _load_json(accepted_path) if accepted_path.exists() else None
    payload = build_payload(report_payload, accepted_payload)

    source_artifacts = payload.get("source_artifacts") if isinstance(payload.get("source_artifacts"), dict) else {}
    source_artifacts["report"] = str(report_path)
    source_artifacts["accepted_candidate_explain"] = str(accepted_path)
    reverse_sync_artifact = ""
    if isinstance(report_payload, dict):
        inputs = report_payload.get("inputs") if isinstance(report_payload.get("inputs"), dict) else {}
        reverse_sync_artifact = str(inputs.get("reverse_sync_json_out", "") or "")
    if reverse_sync_artifact:
        source_artifacts["reverse_sync"] = reverse_sync_artifact
    payload["source_artifacts"] = source_artifacts

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote optimization history payload: {out_path}")
    print(f"  source_mode: {payload.get('source_mode')}")
    print(f"  iterations: {payload.get('summary', {}).get('iteration_count')}")


if __name__ == "__main__":
    main()
