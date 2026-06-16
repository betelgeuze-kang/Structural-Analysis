#!/usr/bin/env python3
"""Build PM core-engine family p95 accuracy evidence from benchmark comparison rows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_COMMERCIAL_READINESS = Path("implementation/phase1/commercial_readiness_report.strict_breadth.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/core_family_p95_accuracy_report.json")

METRIC_SPECS = {
    "drift_ratio_pct": "drift_error_pct",
    "base_shear_kN": "base_shear_error_pct",
    "buckling_factor": "buckling_factor_error_pct",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _p95(values: list[float]) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    idx = max(0, min(len(clean) - 1, math.ceil(0.95 * len(clean)) - 1))
    return float(clean[idx])


def _source_family(row: dict[str, Any]) -> str:
    provenance = row.get("source_provenance") if isinstance(row.get("source_provenance"), dict) else {}
    families = provenance.get("source_families")
    if isinstance(families, list) and families:
        return ",".join(str(item) for item in families)
    return str(row.get("model_id", row.get("family", "")))


def _metric_error_pct(entry: dict[str, Any]) -> float | None:
    try:
        hf = float(entry.get("hf"))
        pred = float(entry.get("topk_pred"))
    except Exception:
        return None
    if not math.isfinite(hf) or not math.isfinite(pred) or abs(hf) <= 1e-12:
        return None
    return float(abs(pred - hf) / abs(hf) * 100.0)


def build_report(*, commercial_readiness_path: Path, max_p95_error_pct: float) -> dict[str, Any]:
    commercial = _load_json(commercial_readiness_path)
    model_rows = commercial.get("model_rows") if isinstance(commercial.get("model_rows"), list) else []
    rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    comparison_reports: dict[str, str] = {}
    blockers: list[str] = []

    for model_row in model_rows:
        if not isinstance(model_row, dict):
            continue
        model_id = str(model_row.get("model_id", ""))
        family = _source_family(model_row)
        reports = model_row.get("reports") if isinstance(model_row.get("reports"), dict) else {}
        comparison_path = Path(str(reports.get("comparison", "")))
        if model_id:
            comparison_reports[model_id] = str(comparison_path)
        comparison = _load_json(comparison_path)
        comparison_rows = comparison.get("rows") if isinstance(comparison.get("rows"), list) else []
        family_metric_values: list[float] = []

        for source_metric, output_metric in METRIC_SPECS.items():
            values: list[float] = []
            for comparison_row in comparison_rows:
                if not isinstance(comparison_row, dict):
                    continue
                metrics = comparison_row.get("metrics") if isinstance(comparison_row.get("metrics"), dict) else {}
                metric_entry = metrics.get(source_metric)
                if not isinstance(metric_entry, dict):
                    continue
                value = _metric_error_pct(metric_entry)
                if value is not None:
                    values.append(value)
            metric_p95 = _p95(values)
            if metric_p95 is None:
                rows.append(
                    {
                        "model_id": model_id,
                        "family": family,
                        "metric": output_metric,
                        "sample_count": 0,
                        "p95_error_pct": None,
                        "max_error_pct": None,
                        "threshold_pct": max_p95_error_pct,
                        "status": "fail",
                    }
                )
                continue
            family_metric_values.append(metric_p95)
            rows.append(
                {
                    "model_id": model_id,
                    "family": family,
                    "metric": output_metric,
                    "sample_count": len(values),
                    "p95_error_pct": metric_p95,
                    "max_error_pct": float(max(values)),
                    "threshold_pct": max_p95_error_pct,
                    "status": "pass" if metric_p95 <= max_p95_error_pct else "fail",
                }
            )

        family_max = max(family_metric_values) if family_metric_values else math.inf
        family_rows.append(
            {
                "model_id": model_id,
                "family": family,
                "comparison_report": str(comparison_path),
                "metric_count": len(family_metric_values),
                "max_family_p95_error_pct": None if not math.isfinite(family_max) else float(family_max),
                "threshold_pct": max_p95_error_pct,
                "status": "pass" if family_metric_values and family_max <= max_p95_error_pct else "fail",
            }
        )

    finite_p95 = [float(row["p95_error_pct"]) for row in rows if isinstance(row.get("p95_error_pct"), (int, float))]
    max_family_values = [
        float(row["max_family_p95_error_pct"])
        for row in family_rows
        if isinstance(row.get("max_family_p95_error_pct"), (int, float))
    ]
    checks = {
        "commercial_readiness_contract_pass": _reason_pass(commercial),
        "comparison_reports_present": bool(model_rows) and all(Path(path).exists() for path in comparison_reports.values()),
        "finite_error_rows": bool(finite_p95),
        "family_rows_present": bool(family_rows),
        "family_p95_error_limited_pass": bool(max_family_values and max(max_family_values) <= max_p95_error_pct),
        "noise_robustness_metrics_excluded": True,
    }
    blockers = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": "core-family-p95-accuracy-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_CORE_FAMILY_P95_FAIL",
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "family_count": len(family_rows),
            "metric_row_count": len(rows),
            "max_family_p95_error_pct": max(max_family_values) if max_family_values else None,
            "max_p95_error_pct_limit": max_p95_error_pct,
            "max_metric_p95_error_pct": max(finite_p95) if finite_p95 else None,
        },
        "rows": rows,
        "family_rows": family_rows,
        "artifacts": {
            "commercial_readiness": str(commercial_readiness_path),
            "comparison_reports": comparison_reports,
        },
        "claim_boundary": (
            "Core family p95 is computed from benchmark HF-vs-topk comparison rows for primary accuracy "
            "metrics. High-noise robustness p95 metrics are intentionally excluded from this core accuracy gate."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument("--max-p95-error-pct", type=float, default=5.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        commercial_readiness_path=args.commercial_readiness,
        max_p95_error_pct=float(args.max_p95_error_pct),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_blocked and not payload["contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
