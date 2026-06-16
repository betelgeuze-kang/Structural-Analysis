#!/usr/bin/env python3
"""Hard-threshold gate for NDTHA residual metrics.

Separates solver execution from residual acceptance so CI can enforce stable
post-processed residual metrics without modifying the core NDTHA contract.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "ndtha residual gate passed",
    "ERR_INVALID_INPUT": "invalid ndtha residual gate input",
    "ERR_NDTHA_REPORT": "ndtha report missing required fields",
    "ERR_RESIDUAL_TRACE": "ndtha residual traceability fields invalid",
    "ERR_SOLVER_CONTROL_TRACE": "ndtha solver-control traceability fields invalid",
    "ERR_SOLVER_CONTROL_LIMIT": "ndtha solver-control hard threshold violated",
    "ERR_RESIDUAL_HARD_LIMIT": "ndtha residual hard threshold violated",
    "ERR_RESIDUAL_RECOMMENDED_LIMIT": "ndtha recommended residual release threshold violated",
    "ERR_CORRECTED_STATE_RECOMPUTE": "ndtha corrected-state recompute evidence is missing or failed",
}


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "ndtha_stress",
        "max_residual_top_displacement_m",
        "max_residual_drift_ratio_pct",
        "recommended_residual_top_displacement_m",
        "recommended_residual_drift_ratio_pct",
        "max_fallback_rate",
        "out",
    ],
    "properties": {
        "ndtha_stress": {"type": "string", "minLength": 1},
        "max_residual_top_displacement_m": {"type": "number", "exclusiveMinimum": 0.0},
        "max_residual_drift_ratio_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "recommended_residual_top_displacement_m": {"type": "number", "exclusiveMinimum": 0.0},
        "recommended_residual_drift_ratio_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "max_fallback_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "strict_recommended_residual_hard_fail": {"type": "boolean"},
        "require_corrected_state_recompute": {"type": "boolean"},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(x: Any, default: float = math.nan) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    return v if math.isfinite(v) else default


def _int_or_default(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return int(default)


def _case_solver_control_metrics(row: dict[str, Any]) -> dict[str, Any]:
    row_summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    solver_control = row_summary.get("solver_control") if isinstance(row_summary.get("solver_control"), dict) else {}
    if solver_control:
        next_run = solver_control.get("next_run_control") if isinstance(solver_control.get("next_run_control"), dict) else {}
        dt_scale_min = _finite(next_run.get("recommended_dt_scale_min"))
        event_count = int(solver_control.get("event_count", 0))
        cutback_step_count = int(solver_control.get("cutback_recommended_step_count", 0))
        nonconverged_step_count = int(solver_control.get("nonconverged_step_count", 0))
        event_sequence_pass = bool(solver_control.get("event_sequence_pass", nonconverged_step_count == 0))
        trace_pass = bool(
            isinstance(solver_control.get("event_history_available"), bool)
            and math.isfinite(dt_scale_min)
            and 0.0 < float(dt_scale_min) <= 1.0
            and event_count >= 0
            and cutback_step_count >= 0
            and nonconverged_step_count >= 0
        )
        return {
            "trace_source": "solver_control_summary",
            "trace_pass": trace_pass,
            "event_count": event_count,
            "cutback_step_count": cutback_step_count,
            "cutback_case": bool(cutback_step_count > 0),
            "nonconverged_step_count": nonconverged_step_count,
            "recommended_dt_scale_min": float(dt_scale_min) if math.isfinite(dt_scale_min) else math.nan,
            "event_sequence_pass": bool(event_sequence_pass and nonconverged_step_count == 0),
        }

    steps_head = row.get("steps_head") if isinstance(row.get("steps_head"), list) else []
    event_rows = [step for step in steps_head if isinstance(step, dict) and str(step.get("solver_event", "")).strip()]
    event_count = len(event_rows)
    cutback_step_count = sum(
        1
        for step in steps_head
        if isinstance(step, dict) and _finite(step.get("recommended_dt_scale"), default=1.0) < 0.999999
    )
    nonconverged_step_count = sum(
        1
        for step in steps_head
        if isinstance(step, dict) and (not bool(step.get("converged", False)) or str(step.get("status", "")).upper() in {"FAIL", "COLLAPSED"})
    )
    dt_candidates = [
        _finite(step.get("recommended_dt_scale"))
        for step in steps_head
        if isinstance(step, dict)
    ]
    finite_dt = [float(v) for v in dt_candidates if math.isfinite(v)]
    dt_scale_min = min(finite_dt, default=1.0)
    trace_pass = bool(steps_head and math.isfinite(dt_scale_min) and 0.0 < float(dt_scale_min) <= 1.0)
    return {
        "trace_source": "steps_head_fallback" if steps_head else "missing",
        "trace_pass": trace_pass,
        "event_count": int(event_count),
        "cutback_step_count": int(cutback_step_count),
        "cutback_case": bool(cutback_step_count > 0),
        "nonconverged_step_count": int(nonconverged_step_count),
        "recommended_dt_scale_min": float(dt_scale_min) if math.isfinite(dt_scale_min) else math.nan,
        "event_sequence_pass": bool(trace_pass and nonconverged_step_count == 0),
    }


def _case_corrected_state_recompute_metrics(row_summary: dict[str, Any]) -> dict[str, Any]:
    recompute = row_summary.get("corrected_state_recompute")
    if not isinstance(recompute, dict):
        recompute = row_summary.get("gnn_corrected_state_recompute")
    if not isinstance(recompute, dict):
        return {
            "present": False,
            "pass": False,
            "source": "missing",
            "residual_top_displacement_m": math.nan,
            "residual_drift_ratio_pct": math.nan,
        }

    top = _finite(recompute.get("residual_top_displacement_m"))
    drift = _finite(recompute.get("residual_drift_ratio_pct"))
    pass_value = recompute.get("contract_pass", recompute.get("pass", False))
    return {
        "present": True,
        "pass": bool(pass_value),
        "source": str(recompute.get("source", "corrected_state_recompute") or "corrected_state_recompute"),
        "residual_top_displacement_m": float(top) if math.isfinite(top) else math.nan,
        "residual_drift_ratio_pct": float(drift) if math.isfinite(drift) else math.nan,
    }


def run_ndtha_residual_gate(
    *,
    ndtha_report: dict[str, Any],
    max_residual_top_displacement_m: float,
    max_residual_drift_ratio_pct: float,
    recommended_residual_top_displacement_m: float,
    recommended_residual_drift_ratio_pct: float,
    max_fallback_rate: float,
    strict_recommended_residual_hard_fail: bool = False,
    require_corrected_state_recompute: bool = False,
) -> dict[str, Any]:
    rows = ndtha_report.get("rows")
    summary = ndtha_report.get("summary") if isinstance(ndtha_report.get("summary"), dict) else {}
    checks = ndtha_report.get("checks") if isinstance(ndtha_report.get("checks"), dict) else {}

    if not isinstance(rows, list) or not rows:
        return {
            "contract_pass": False,
            "reason_code": "ERR_NDTHA_REPORT",
            "reason": REASONS["ERR_NDTHA_REPORT"],
            "checks": {"rows_present_pass": False},
            "summary": {},
            "rows": [],
        }

    gate_rows: list[dict[str, Any]] = []
    allowed_sources = {"solver_raw", "history_tail", "collapse_state"}
    trace_ok_all = True
    residual_ok_all = True
    finite_ok_all = True
    recommended_top_exceed: list[str] = []
    recommended_drift_exceed: list[str] = []
    fallback_case_ids: list[str] = []
    source_counts: dict[str, int] = {}
    residual_top_values: list[float] = []
    residual_drift_values: list[float] = []
    raw_top_values: list[float] = []
    raw_drift_values: list[float] = []
    solver_control_trace_ok_all = True
    solver_control_sequence_ok_all = True
    solver_control_event_count_total = 0
    solver_control_cutback_case_ids: list[str] = []
    solver_control_nonconverged_step_total = 0
    solver_control_recommended_dt_scale_min = 1.0
    solver_control_trace_source_counts: dict[str, int] = {}
    corrected_state_recompute_present_all = True
    corrected_state_recompute_pass_all = True

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id", f"case-{idx}"))
        row_summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        case_checks = row.get("checks") if isinstance(row.get("checks"), dict) else {}
        residual_top = _finite(row_summary.get("residual_top_displacement_m"))
        residual_drift = _finite(row_summary.get("residual_drift_ratio_pct"))
        raw_top = _finite(row_summary.get("raw_residual_top_displacement_m"))
        raw_drift = _finite(row_summary.get("raw_residual_drift_ratio_pct"))
        source = str(row_summary.get("residual_metric_source", "")).strip()
        fallback_used = bool(row_summary.get("residual_metric_fallback_used", False))
        collapsed = bool(case_checks.get("collapsed", False))

        finite_ok = bool(math.isfinite(residual_top) and math.isfinite(residual_drift))
        trace_ok = bool(source in allowed_sources and isinstance(fallback_used, bool))
        hard_top_ok = bool(finite_ok and abs(residual_top) <= float(max_residual_top_displacement_m))
        hard_drift_ok = bool(finite_ok and abs(residual_drift) <= float(max_residual_drift_ratio_pct))
        hard_ok = bool(hard_top_ok and hard_drift_ok)
        if collapsed and source not in {"collapse_state", "solver_raw"}:
            trace_ok = False

        recommended_top_ok = bool(finite_ok and abs(residual_top) <= float(recommended_residual_top_displacement_m))
        recommended_drift_ok = bool(finite_ok and abs(residual_drift) <= float(recommended_residual_drift_ratio_pct))
        normalized = {
            "hard_top_ratio": float(abs(residual_top) / float(max_residual_top_displacement_m))
            if finite_ok and max_residual_top_displacement_m > 0.0
            else math.inf,
            "hard_drift_ratio": float(abs(residual_drift) / float(max_residual_drift_ratio_pct))
            if finite_ok and max_residual_drift_ratio_pct > 0.0
            else math.inf,
            "recommended_top_ratio": float(abs(residual_top) / float(recommended_residual_top_displacement_m))
            if finite_ok and recommended_residual_top_displacement_m > 0.0
            else math.inf,
            "recommended_drift_ratio": float(abs(residual_drift) / float(recommended_residual_drift_ratio_pct))
            if finite_ok and recommended_residual_drift_ratio_pct > 0.0
            else math.inf,
        }
        normalized["hard_max_ratio"] = float(max(normalized["hard_top_ratio"], normalized["hard_drift_ratio"]))
        normalized["recommended_max_ratio"] = float(
            max(normalized["recommended_top_ratio"], normalized["recommended_drift_ratio"])
        )

        finite_ok_all = bool(finite_ok_all and finite_ok)
        trace_ok_all = bool(trace_ok_all and trace_ok)
        residual_ok_all = bool(residual_ok_all and hard_ok)

        if fallback_used:
            fallback_case_ids.append(case_id)
        if not recommended_top_ok:
            recommended_top_exceed.append(case_id)
        if not recommended_drift_ok:
            recommended_drift_exceed.append(case_id)

        source_counts[source] = int(source_counts.get(source, 0) + 1)
        if math.isfinite(residual_top):
            residual_top_values.append(abs(residual_top))
        if math.isfinite(residual_drift):
            residual_drift_values.append(abs(residual_drift))
        if math.isfinite(raw_top):
            raw_top_values.append(abs(raw_top))
        if math.isfinite(raw_drift):
            raw_drift_values.append(abs(raw_drift))

        solver_control_metrics = _case_solver_control_metrics(row)
        solver_control_trace_ok_all = bool(solver_control_trace_ok_all and solver_control_metrics["trace_pass"])
        solver_control_sequence_ok_all = bool(
            solver_control_sequence_ok_all and solver_control_metrics["event_sequence_pass"]
        )
        solver_control_event_count_total += int(solver_control_metrics["event_count"])
        solver_control_nonconverged_step_total += int(solver_control_metrics["nonconverged_step_count"])
        solver_control_trace_source = str(solver_control_metrics["trace_source"])
        solver_control_trace_source_counts[solver_control_trace_source] = int(
            solver_control_trace_source_counts.get(solver_control_trace_source, 0) + 1
        )
        dt_scale_min = _finite(solver_control_metrics.get("recommended_dt_scale_min"))
        if math.isfinite(dt_scale_min):
            solver_control_recommended_dt_scale_min = min(
                float(solver_control_recommended_dt_scale_min),
                float(dt_scale_min),
            )
        if bool(solver_control_metrics["cutback_case"]):
            solver_control_cutback_case_ids.append(case_id)
        corrected_state_metrics = _case_corrected_state_recompute_metrics(row_summary)
        corrected_state_recompute_present_all = bool(
            corrected_state_recompute_present_all and corrected_state_metrics["present"]
        )
        corrected_state_recompute_pass_all = bool(
            corrected_state_recompute_pass_all and corrected_state_metrics["pass"]
        )

        gate_rows.append(
            {
                "case_id": case_id,
                "collapsed": bool(collapsed),
                "residual_top_displacement_m": float(residual_top) if math.isfinite(residual_top) else math.inf,
                "residual_drift_ratio_pct": float(residual_drift) if math.isfinite(residual_drift) else math.inf,
                "raw_residual_top_displacement_m": float(raw_top) if math.isfinite(raw_top) else math.inf,
                "raw_residual_drift_ratio_pct": float(raw_drift) if math.isfinite(raw_drift) else math.inf,
                "residual_metric_source": source,
                "residual_metric_fallback_used": bool(fallback_used),
                "normalized_residual": normalized,
                "corrected_state_recompute": corrected_state_metrics,
                "solver_control_trace_source": solver_control_trace_source,
                "solver_control_event_count": int(solver_control_metrics["event_count"]),
                "solver_control_cutback_step_count": int(solver_control_metrics["cutback_step_count"]),
                "solver_control_nonconverged_step_count": int(solver_control_metrics["nonconverged_step_count"]),
                "solver_control_recommended_dt_scale_min": float(dt_scale_min) if math.isfinite(dt_scale_min) else math.inf,
                "checks": {
                    "finite_pass": bool(finite_ok),
                    "trace_pass": bool(trace_ok),
                    "hard_top_pass": bool(hard_top_ok),
                    "hard_drift_pass": bool(hard_drift_ok),
                    "hard_pass": bool(hard_ok),
                    "recommended_top_pass": bool(recommended_top_ok),
                    "recommended_drift_pass": bool(recommended_drift_ok),
                    "recommended_residual_pass": bool(recommended_top_ok and recommended_drift_ok),
                    "corrected_state_recompute_present": bool(corrected_state_metrics["present"]),
                    "corrected_state_recompute_pass": bool(corrected_state_metrics["pass"]),
                    "solver_control_trace_pass": bool(solver_control_metrics["trace_pass"]),
                    "solver_control_event_sequence_pass": bool(solver_control_metrics["event_sequence_pass"]),
                },
            }
        )

    case_count = len(gate_rows)
    fallback_rate = float(len(fallback_case_ids) / max(1, case_count))
    source_ratios = {
        key: float(value / max(1, case_count))
        for key, value in sorted(source_counts.items())
    }
    solver_raw_ratio = float(source_counts.get("solver_raw", 0) / max(1, case_count))
    ndtha_solver_control_trace = bool(checks.get("solver_control_history_pass", False))
    ndtha_solver_control_event_total = _int_or_default(summary.get("solver_control_event_count_total"), default=-1)
    ndtha_solver_control_nonconverged_total = _int_or_default(summary.get("solver_control_nonconverged_step_total"), default=-1)
    ndtha_solver_control_cutback_case_ids = summary.get("solver_control_cutback_case_ids")
    ndtha_solver_control_dt_scale_min = _finite(summary.get("solver_control_recommended_dt_scale_min"))
    solver_control_rollup_pass = bool(
        ndtha_solver_control_trace
        and ndtha_solver_control_event_total == int(solver_control_event_count_total)
        and ndtha_solver_control_nonconverged_total == int(solver_control_nonconverged_step_total)
        and isinstance(ndtha_solver_control_cutback_case_ids, list)
        and sorted(str(v) for v in ndtha_solver_control_cutback_case_ids) == sorted(solver_control_cutback_case_ids)
        and math.isfinite(ndtha_solver_control_dt_scale_min)
        and abs(float(ndtha_solver_control_dt_scale_min) - float(solver_control_recommended_dt_scale_min)) <= 1e-9
    )
    gate_checks = {
        "case_count_pass": bool(case_count >= 1),
        "ndtha_contract_pass": bool(ndtha_report.get("contract_pass", False)),
        "ndtha_no_collapse_pass": bool(checks.get("no_collapse_detected", False)),
        "summary_residual_finite_pass": bool(finite_ok_all),
        "residual_metric_trace_pass": bool(trace_ok_all),
        "residual_top_hard_pass": bool(residual_ok_all and all(r["checks"]["hard_top_pass"] for r in gate_rows)),
        "residual_drift_hard_pass": bool(residual_ok_all and all(r["checks"]["hard_drift_pass"] for r in gate_rows)),
        "fallback_rate_pass": bool(fallback_rate <= float(max_fallback_rate)),
        "recommended_top_pass": bool(len(recommended_top_exceed) == 0),
        "recommended_drift_pass": bool(len(recommended_drift_exceed) == 0),
        "recommended_residual_pass": bool(len(recommended_top_exceed) == 0 and len(recommended_drift_exceed) == 0),
        "strict_recommended_residual_hard_fail_enabled": bool(strict_recommended_residual_hard_fail),
        "strict_recommended_residual_pass": bool(
            (not strict_recommended_residual_hard_fail)
            or (len(recommended_top_exceed) == 0 and len(recommended_drift_exceed) == 0)
        ),
        "corrected_state_recompute_required": bool(require_corrected_state_recompute),
        "corrected_state_recompute_present_pass": bool(
            (not require_corrected_state_recompute) or corrected_state_recompute_present_all
        ),
        "corrected_state_recompute_pass": bool(
            (not require_corrected_state_recompute)
            or (corrected_state_recompute_present_all and corrected_state_recompute_pass_all)
        ),
        "solver_control_trace_pass": bool(solver_control_trace_ok_all and ndtha_solver_control_trace),
        "solver_control_rollup_pass": bool(solver_control_rollup_pass),
        "solver_control_event_sequence_pass": bool(solver_control_sequence_ok_all and solver_control_nonconverged_step_total == 0),
    }
    contract_pass = bool(
        gate_checks["case_count_pass"]
        and gate_checks["ndtha_contract_pass"]
        and gate_checks["ndtha_no_collapse_pass"]
        and gate_checks["summary_residual_finite_pass"]
        and gate_checks["residual_metric_trace_pass"]
        and gate_checks["residual_top_hard_pass"]
        and gate_checks["residual_drift_hard_pass"]
        and gate_checks["fallback_rate_pass"]
        and gate_checks["strict_recommended_residual_pass"]
        and gate_checks["corrected_state_recompute_pass"]
        and gate_checks["solver_control_trace_pass"]
        and gate_checks["solver_control_rollup_pass"]
        and gate_checks["solver_control_event_sequence_pass"]
    )

    if not gate_checks["case_count_pass"] or not gate_checks["ndtha_contract_pass"]:
        reason_code = "ERR_NDTHA_REPORT"
    elif not gate_checks["summary_residual_finite_pass"] or not gate_checks["residual_metric_trace_pass"]:
        reason_code = "ERR_RESIDUAL_TRACE"
    elif not gate_checks["solver_control_trace_pass"] or not gate_checks["solver_control_rollup_pass"]:
        reason_code = "ERR_SOLVER_CONTROL_TRACE"
    elif not gate_checks["solver_control_event_sequence_pass"]:
        reason_code = "ERR_SOLVER_CONTROL_LIMIT"
    elif not gate_checks["strict_recommended_residual_pass"]:
        reason_code = "ERR_RESIDUAL_RECOMMENDED_LIMIT"
    elif not gate_checks["corrected_state_recompute_pass"]:
        reason_code = "ERR_CORRECTED_STATE_RECOMPUTE"
    elif not contract_pass:
        reason_code = "ERR_RESIDUAL_HARD_LIMIT"
    else:
        reason_code = "PASS"

    return {
        "schema_version": "1.0",
        "run_id": "phase3-ndtha-residual-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": gate_checks,
        "summary": {
            "case_count": int(case_count),
            "residual_top_displacement_m_max_abs": max(residual_top_values) if residual_top_values else 0.0,
            "residual_drift_ratio_pct_max_abs": max(residual_drift_values) if residual_drift_values else 0.0,
            "raw_residual_top_displacement_m_max_abs": max(raw_top_values) if raw_top_values else 0.0,
            "raw_residual_drift_ratio_pct_max_abs": max(raw_drift_values) if raw_drift_values else 0.0,
            "fallback_case_count": int(len(fallback_case_ids)),
            "fallback_rate": float(fallback_rate),
            "fallback_case_ids": fallback_case_ids,
            "residual_metric_source_counts": source_counts,
            "residual_metric_source_ratios": source_ratios,
            "solver_raw_case_count": int(source_counts.get("solver_raw", 0)),
            "solver_raw_ratio": float(solver_raw_ratio),
            "recommended_top_exceed_case_ids": recommended_top_exceed,
            "recommended_drift_exceed_case_ids": recommended_drift_exceed,
            "strict_recommended_residual_hard_fail": bool(strict_recommended_residual_hard_fail),
            "corrected_state_recompute_required": bool(require_corrected_state_recompute),
            "corrected_state_recompute_present_count": int(
                sum(1 for row in gate_rows if row["checks"]["corrected_state_recompute_present"])
            ),
            "corrected_state_recompute_pass_count": int(
                sum(1 for row in gate_rows if row["checks"]["corrected_state_recompute_pass"])
            ),
            "solver_control_event_count_total": int(solver_control_event_count_total),
            "solver_control_nonconverged_step_total": int(solver_control_nonconverged_step_total),
            "solver_control_cutback_case_ids": solver_control_cutback_case_ids,
            "solver_control_recommended_dt_scale_min": float(solver_control_recommended_dt_scale_min),
            "solver_control_trace_source_counts": solver_control_trace_source_counts,
            "summary_line": (
                "NDTHA residual gate: "
                f"{'PASS' if contract_pass else 'CHECK'} | "
                f"cases={case_count} | "
                f"fallback_rate={fallback_rate:.3f} | "
                f"solver_raw_ratio={solver_raw_ratio:.3f} | "
                f"solver_control=events={solver_control_event_count_total},"
                f"nonconverged={solver_control_nonconverged_step_total},"
                f"cutback_cases={len(solver_control_cutback_case_ids)},"
                f"dt_scale_min={solver_control_recommended_dt_scale_min:.3f}"
            ),
        },
        "rows": gate_rows,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ndtha-stress", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    p.add_argument("--max-residual-top-displacement-m", type=float, default=5.0)
    p.add_argument("--max-residual-drift-ratio-pct", type=float, default=10.0)
    p.add_argument("--recommended-residual-top-displacement-m", type=float, default=1.0)
    p.add_argument("--recommended-residual-drift-ratio-pct", type=float, default=2.0)
    p.add_argument("--max-fallback-rate", type=float, default=1.0)
    p.add_argument("--strict-recommended-residual-hard-fail", action="store_true")
    p.add_argument("--require-corrected-state-recompute", action="store_true")
    p.add_argument("--out", default="implementation/phase1/ndtha_residual_gate_report.json")
    args = p.parse_args()

    input_payload = {
        "ndtha_stress": str(args.ndtha_stress),
        "max_residual_top_displacement_m": float(args.max_residual_top_displacement_m),
        "max_residual_drift_ratio_pct": float(args.max_residual_drift_ratio_pct),
        "recommended_residual_top_displacement_m": float(args.recommended_residual_top_displacement_m),
        "recommended_residual_drift_ratio_pct": float(args.recommended_residual_drift_ratio_pct),
        "max_fallback_rate": float(args.max_fallback_rate),
        "strict_recommended_residual_hard_fail": bool(args.strict_recommended_residual_hard_fail),
        "require_corrected_state_recompute": bool(args.require_corrected_state_recompute),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_ndtha_residual_gate")
        ndtha_report = _load_json(Path(args.ndtha_stress))
        report = run_ndtha_residual_gate(
            ndtha_report=ndtha_report,
            max_residual_top_displacement_m=float(args.max_residual_top_displacement_m),
            max_residual_drift_ratio_pct=float(args.max_residual_drift_ratio_pct),
            recommended_residual_top_displacement_m=float(args.recommended_residual_top_displacement_m),
            recommended_residual_drift_ratio_pct=float(args.recommended_residual_drift_ratio_pct),
            max_fallback_rate=float(args.max_fallback_rate),
            strict_recommended_residual_hard_fail=bool(args.strict_recommended_residual_hard_fail),
            require_corrected_state_recompute=bool(args.require_corrected_state_recompute),
        )
    except (ValueError, FileNotFoundError, InputContractError, json.JSONDecodeError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-ndtha-residual-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": {"input_valid": False},
            "summary": {},
            "rows": [],
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote NDTHA residual gate report: {out}")
        raise SystemExit(1)

    report["inputs"] = input_payload
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote NDTHA residual gate report: {out}")
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
