#!/usr/bin/env python3
"""Build explicit PM runtime and memory budget evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/runtime_memory_release_budget_report.json")
DEFAULT_NIGHTLY_10M = Path("implementation/phase1/release_evidence/productization/nightly_10m_repro_report.json")
DEFAULT_NIGHTLY_HISTORY_ROOT = Path("implementation/phase1/release")
DEFAULT_WORKSTATION_BUDGET = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_NDTHA_LONG_PROFILE = Path("implementation/phase1/ndtha_long_profile_report.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("rows")
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _p95(values: list[float]) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    idx = max(0, min(len(clean) - 1, math.ceil(0.95 * len(clean)) - 1))
    return clean[idx]


def _status_row(budget_id: str, title: str, actual: float | None, limit: float, unit: str, sample_count: int) -> dict[str, Any]:
    passed = bool(actual is not None and math.isfinite(actual) and actual <= limit)
    return {
        "budget_id": budget_id,
        "title": title,
        "actual": actual,
        "limit": limit,
        "unit": unit,
        "sample_count": sample_count,
        "status": "pass" if passed else "fail",
    }


def _collect_nightly_history(root: Path) -> list[dict[str, Any]]:
    reports = [_load_json(path) for path in sorted(root.glob("phase3_nightly_hardening_*/nightly_10m_repro_report.json"))]
    return [payload for payload in reports if payload]


def _oom_signature_count(payloads: list[dict[str, Any]]) -> int:
    count = 0
    needles = ("out of memory", "oom", "cuda out of memory", "hip out of memory")
    for payload in payloads:
        for row in _rows(payload):
            text = f"{row.get('stderr_tail', '')}\n{row.get('stdout_tail', '')}".lower()
            if any(needle in text for needle in needles):
                count += 1
    return count


def build_report(
    *,
    nightly_10m_path: Path,
    nightly_history_root: Path,
    workstation_budget_path: Path,
    ndtha_long_profile_path: Path,
    nightly_10m_latency_budget_ms: float,
    nightly_10m_command_budget_seconds: float,
    ndtha_runtime_budget_seconds: float,
) -> dict[str, Any]:
    nightly = _load_json(nightly_10m_path)
    history = _collect_nightly_history(nightly_history_root)
    workstation = _load_json(workstation_budget_path)
    ndtha = _load_json(ndtha_long_profile_path)
    nightly_payloads = [payload for payload in [nightly, *history] if payload]

    latency_values = [
        _as_float(_summary(payload).get("latency_10m_mean_ms"), float("nan"))
        for payload in nightly_payloads
        if "latency_10m_mean_ms" in _summary(payload)
    ]
    command_seconds = [
        _as_float(row.get("seconds"), float("nan"))
        for payload in nightly_payloads
        for row in _rows(payload)
        if "seconds" in row
    ]
    working_set_values = [
        _as_float(_summary(payload).get("working_set_10m_mean_mb"), float("nan"))
        for payload in nightly_payloads
        if "working_set_10m_mean_mb" in _summary(payload)
    ]
    ndtha_elapsed = [
        _as_float(row.get("elapsed_wall_s"), float("nan"))
        for row in _rows(ndtha)
        if "elapsed_wall_s" in row
    ]
    workstation_budget = workstation.get("performance_budget") if isinstance(workstation.get("performance_budget"), dict) else {}
    viewer_ready_ms = _as_float(workstation_budget.get("viewer_ready_ms"), float("nan"))
    viewer_ready_limit = _as_float(workstation_budget.get("viewer_max_ready_ms"), 60000.0)
    memory_budget = workstation_budget.get("memory_budget_gib") if isinstance(workstation_budget.get("memory_budget_gib"), dict) else {}
    available_memory_mb = _as_float(memory_budget.get("available_total_gib"), 0.0) * 1024.0

    runtime_rows = [
        _status_row(
            "nightly_10m_latency_p95",
            "P95 of historical 10M nightly latency means",
            _p95(latency_values),
            nightly_10m_latency_budget_ms,
            "ms",
            len(latency_values),
        ),
        _status_row(
            "nightly_10m_command_seconds_p95",
            "P95 of historical nightly 10M gate command wall time",
            _p95(command_seconds),
            nightly_10m_command_budget_seconds,
            "s",
            len(command_seconds),
        ),
        _status_row(
            "ndtha_long_profile_elapsed_p95",
            "P95 of NDTHA long-profile run elapsed wall time",
            _p95(ndtha_elapsed),
            ndtha_runtime_budget_seconds,
            "s",
            len(ndtha_elapsed),
        ),
        _status_row(
            "workstation_viewer_ready_ms",
            "Workstation viewer ready time",
            viewer_ready_ms if math.isfinite(viewer_ready_ms) else None,
            viewer_ready_limit,
            "ms",
            1 if math.isfinite(viewer_ready_ms) else 0,
        ),
    ]
    runtime_fail_count = sum(1 for row in runtime_rows if row["status"] != "pass")
    runtime_exceed_rate = runtime_fail_count / len(runtime_rows) if runtime_rows else 1.0

    oom_count = _oom_signature_count([*nightly_payloads, ndtha])
    memory_rows = [
        {
            "budget_id": "oom_signature_count",
            "title": "OOM signature count in release runtime rows",
            "actual": oom_count,
            "limit": 0,
            "unit": "count",
            "sample_count": sum(len(_rows(payload)) for payload in [*nightly_payloads, ndtha]),
            "status": "pass" if oom_count == 0 else "fail",
        },
        _status_row(
            "nightly_10m_working_set_p95",
            "P95 of historical 10M nightly working-set means",
            _p95(working_set_values),
            available_memory_mb if available_memory_mb > 0 else 0.0,
            "MiB",
            len(working_set_values),
        ),
        {
            "budget_id": "peak_memory_budget_report_present",
            "title": "Workstation peak memory budget is present",
            "actual": 1 if memory_budget else 0,
            "limit": 1,
            "unit": "boolean",
            "sample_count": 1,
            "status": "pass" if memory_budget else "fail",
        },
        {
            "budget_id": "ndtha_peak_vram_report_present",
            "title": "NDTHA peak VRAM report is present",
            "actual": _summary(ndtha).get("peak_vram_mb_mean"),
            "limit": _summary(ndtha).get("peak_vram_mb_mean"),
            "unit": "MiB",
            "sample_count": len(ndtha_elapsed),
            "status": "pass" if "peak_vram_mb_mean" in _summary(ndtha) else "fail",
        },
    ]
    memory_fail_count = sum(1 for row in memory_rows if row["status"] != "pass")
    checks = {
        "runtime_budget_rows_present": bool(runtime_rows),
        "p95_runtime_budget_exceed_rate_pass": runtime_exceed_rate <= 0.05,
        "oom_zero_pass": oom_count == 0,
        "peak_memory_budget_report_present": bool(memory_budget),
        "memory_budget_rows_pass": memory_fail_count == 0,
    }
    blockers = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": "runtime-memory-release-budget-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "p95_runtime_budget_exceed_rate": runtime_exceed_rate,
            "runtime_budget_row_count": len(runtime_rows),
            "runtime_budget_fail_count": runtime_fail_count,
            "oom_count": oom_count,
            "memory_budget_row_count": len(memory_rows),
            "memory_budget_fail_count": memory_fail_count,
            "nightly_history_report_count": len(history),
        },
        "runtime_budget_rows": runtime_rows,
        "memory_budget_rows": memory_rows,
        "artifacts": {
            "nightly_10m_repro": str(nightly_10m_path),
            "nightly_history_root": str(nightly_history_root),
            "workstation_budget": str(workstation_budget_path),
            "ndtha_long_profile": str(ndtha_long_profile_path),
        },
        "claim_boundary": (
            "This report turns existing release runtime evidence into explicit PM budget rows. It is not a "
            "customer-device benchmark and does not replace broader performance qualification."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nightly-10m", type=Path, default=DEFAULT_NIGHTLY_10M)
    parser.add_argument("--nightly-history-root", type=Path, default=DEFAULT_NIGHTLY_HISTORY_ROOT)
    parser.add_argument("--workstation-budget", type=Path, default=DEFAULT_WORKSTATION_BUDGET)
    parser.add_argument("--ndtha-long-profile", type=Path, default=DEFAULT_NDTHA_LONG_PROFILE)
    parser.add_argument("--nightly-10m-latency-budget-ms", type=float, default=6000.0)
    parser.add_argument("--nightly-10m-command-budget-seconds", type=float, default=180.0)
    parser.add_argument("--ndtha-runtime-budget-seconds", type=float, default=180.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        nightly_10m_path=args.nightly_10m,
        nightly_history_root=args.nightly_history_root,
        workstation_budget_path=args.workstation_budget,
        ndtha_long_profile_path=args.ndtha_long_profile,
        nightly_10m_latency_budget_ms=args.nightly_10m_latency_budget_ms,
        nightly_10m_command_budget_seconds=args.nightly_10m_command_budget_seconds,
        ndtha_runtime_budget_seconds=args.ndtha_runtime_budget_seconds,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["reason_code"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
