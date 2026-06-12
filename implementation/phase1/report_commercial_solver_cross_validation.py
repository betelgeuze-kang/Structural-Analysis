#!/usr/bin/env python3
"""HF vs LF commercial export cross-validation report (E-P2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "commercial-solver-cross-validation.v1"
DEFAULT_METRICS = (
    "drift_ratio_pct",
    "base_shear_kN",
    "mode_shape_mac",
    "buckling_factor",
    "equilibrium_residual",
    "top_displacement_m",
    "axial_force_kN",
)
DEFAULT_REL_TOL = {
    "drift_ratio_pct": 0.12,
    "base_shear_kN": 0.10,
    "mode_shape_mac": 0.05,
    "buckling_factor": 0.12,
    "equilibrium_residual": 0.05,
    "top_displacement_m": 0.12,
    "axial_force_kN": 0.10,
}
# Failures within this fraction above tolerance are tracked as marginal (engineer review, not hard block).
MARGINAL_TOLERANCE_FRACTION = 0.05


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    hf: float
    lf: float
    abs_delta: float
    rel_error: float
    tolerance: float
    ok: bool
    marginal_only: bool = False


def _rel_error(hf: float, lf: float, *, metric: str = "") -> float:
    delta = abs(hf - lf)
    if metric == "equilibrium_residual":
        return delta
    if abs(hf) < 1e-9 or abs(lf) < 1e-9:
        return delta
    denom = max(abs(hf), abs(lf), 1e-9)
    return delta / denom


def _case_metrics(case: dict[str, Any]) -> dict[str, dict[str, float]]:
    metrics = case.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return metrics
    hf = case.get("hf_metrics") if isinstance(case.get("hf_metrics"), dict) else {}
    lf = case.get("lf_metrics") if isinstance(case.get("lf_metrics"), dict) else {}
    if not hf and not lf:
        return {}
    keys = set(hf.keys()) | set(lf.keys())
    return {key: {"hf": float(hf.get(key, 0.0)), "lf": float(lf.get(key, 0.0))} for key in keys}


def compare_case_metrics(
    case: dict[str, Any],
    *,
    rel_tol: dict[str, float] | None = None,
) -> list[MetricDelta]:
    tolerances = {**DEFAULT_REL_TOL, **(rel_tol or {})}
    rows: list[MetricDelta] = []
    metrics = _case_metrics(case)
    for metric, pair in metrics.items():
        if not isinstance(pair, dict):
            continue
        if "hf" not in pair or "lf" not in pair:
            continue
        hf = float(pair["hf"])
        lf = float(pair["lf"])
        tol = float(tolerances.get(metric, 0.15))
        rel = _rel_error(hf, lf, metric=metric)
        ok = rel <= tol
        marginal_only = not ok and rel <= tol * (1.0 + MARGINAL_TOLERANCE_FRACTION)
        rows.append(
            MetricDelta(
                metric=metric,
                hf=hf,
                lf=lf,
                abs_delta=abs(hf - lf),
                rel_error=rel,
                tolerance=tol,
                ok=ok,
                marginal_only=marginal_only,
            )
        )
    return rows


def _metric_failure_rows(case_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hard: list[dict[str, Any]] = []
    marginal: list[dict[str, Any]] = []
    for case in case_rows:
        case_id = case.get("case_id")
        for metric in case.get("metrics") or []:
            if not isinstance(metric, dict) or metric.get("ok") or metric.get("marginal_only"):
                continue
            tol = float(metric.get("tolerance") or 0.0)
            rel = float(metric.get("rel_error") or 0.0)
            row = {
                "case_id": case_id,
                "metric": metric.get("metric"),
                "rel_error": rel,
                "tolerance": tol,
            }
            if tol > 0.0 and rel <= tol * (1.0 + MARGINAL_TOLERANCE_FRACTION):
                marginal.append(row)
            else:
                hard.append(row)
    return hard, marginal


def summarize_modal_buckling(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Minimal modal/buckling ingest summary from commercial benchmark cases."""
    mode_mac_hf: list[float] = []
    buckling_hf: list[float] = []
    for case in cases:
        metrics = _case_metrics(case)
        mac = metrics.get("mode_shape_mac")
        buck = metrics.get("buckling_factor")
        if isinstance(mac, dict) and "hf" in mac:
            mode_mac_hf.append(float(mac["hf"]))
        if isinstance(buck, dict) and "hf" in buck:
            buckling_hf.append(float(buck["hf"]))
    return {
        "case_count": len(cases),
        "mode_shape_mac_hf_min": min(mode_mac_hf) if mode_mac_hf else None,
        "mode_shape_mac_hf_mean": round(sum(mode_mac_hf) / len(mode_mac_hf), 4) if mode_mac_hf else None,
        "buckling_factor_hf_min": min(buckling_hf) if buckling_hf else None,
        "buckling_factor_hf_mean": round(sum(buckling_hf) / len(buckling_hf), 3) if buckling_hf else None,
        "note": (
            "Ingested from commercial exports; this artifact records benchmark tolerances, "
            "while native eigen/buckling solve evidence is emitted separately."
        ),
    }


def build_cross_validation_report(
    payload: dict[str, Any],
    *,
    rel_tol: dict[str, float] | None = None,
) -> dict[str, Any]:
    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    if not cases and isinstance(payload.get("public_benchmark_cases"), list):
        cases = list(payload["public_benchmark_cases"])

    case_rows: list[dict[str, Any]] = []
    failing_metrics = 0
    compared_metrics = 0
    for case in cases:
        deltas = compare_case_metrics(case, rel_tol=rel_tol)
        compared_metrics += len(deltas)
        failing_metrics += sum(1 for row in deltas if not row.ok and not row.marginal_only)
        case_rows.append(
            {
                "case_id": case.get("case_id"),
                "split": case.get("split"),
                "topology_type": case.get("topology_type"),
                "hazard_type": case.get("hazard_type"),
                "metrics": [
                    {
                        "metric": row.metric,
                        "hf": row.hf,
                        "lf": row.lf,
                        "rel_error": round(row.rel_error, 4),
                        "tolerance": row.tolerance,
                        "ok": row.ok,
                        "marginal_only": row.marginal_only,
                    }
                    for row in deltas
                ],
                "ok": all(row.ok or row.marginal_only for row in deltas) if deltas else False,
            }
        )

    ok_cases = sum(1 for row in case_rows if row.get("ok"))
    hard_failures, marginal_failures = _metric_failure_rows(case_rows)
    marginal_accepted = [
        {
            "case_id": case.get("case_id"),
            "metric": metric.get("metric"),
            "rel_error": metric.get("rel_error"),
            "tolerance": metric.get("tolerance"),
        }
        for case in case_rows
        for metric in (case.get("metrics") or [])
        if isinstance(metric, dict) and metric.get("marginal_only")
    ]
    if case_rows and ok_cases == len(case_rows):
        status = "pass" if not marginal_accepted else "pass_with_marginal_metrics"
    elif hard_failures:
        status = "partial" if ok_cases else "fail"
    else:
        status = "partial" if ok_cases else "fail"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim": "Commercial HF/LF export agreement check; not independent solver certification.",
        "source": payload.get("source") if isinstance(payload.get("source"), dict) else {},
        "case_count": len(case_rows),
        "cases_passed": ok_cases,
        "metric_comparisons": compared_metrics,
        "metric_failures": failing_metrics,
        "metric_failures_hard": len(hard_failures),
        "metric_failures_marginal": len(marginal_failures),
        "metric_marginal_accepted": len(marginal_accepted),
        "hard_failure_cases": hard_failures,
        "marginal_failure_cases": marginal_failures,
        "marginal_accepted_metrics": marginal_accepted,
        "marginal_tolerance_fraction": MARGINAL_TOLERANCE_FRACTION,
        "modal_buckling_summary": summarize_modal_buckling(cases),
        "cases": case_rows,
        "tolerances": {**DEFAULT_REL_TOL, **(rel_tol or {})},
    }


def load_cases_payload(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
