#!/usr/bin/env python3
"""Check whether current hinge-refresh source rows align with PEER SPD column benchmark scope."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase1-run-peer-spd-hinge-refresh-alignment"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "Current hinge-refresh source covers column and rebar-sensitive benchmark scope within the PEER SPD rebar envelope.",
    "ERR_BENCHMARK_INVALID": "PEER SPD hinge benchmark asset registry is missing or contains no benchmark-ready fixtures.",
    "ERR_REFRESH_SOURCE_INVALID": "Hinge-refresh source is missing or contains no refresh rows.",
    "ERR_COLUMN_REFRESH_MISSING": "Hinge-refresh source does not contain any column member refresh rows.",
    "ERR_REBAR_SENSITIVE_COLUMN_MISSING": "Hinge-refresh source contains column rows but none are rebar-sensitive.",
    "ERR_REBAR_RATIO_ENVELOPE_DISJOINT": "Current hinge-refresh source does not overlap the PEER SPD longitudinal rebar envelope.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _extract_refresh_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("hinge_refresh_rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _ratio_bounds(values: list[float]) -> tuple[float, float]:
    finite = [float(v) for v in values if isinstance(v, (int, float))]
    if not finite:
        return 0.0, 0.0
    return float(min(finite)), float(max(finite))


def _overlap_with_padding(
    benchmark_min: float,
    benchmark_max: float,
    refresh_min: float,
    refresh_max: float,
    *,
    pad_abs: float,
) -> bool:
    benchmark_lo = float(benchmark_min) - float(pad_abs)
    benchmark_hi = float(benchmark_max) + float(pad_abs)
    return max(float(refresh_min), benchmark_lo) <= min(float(refresh_max), benchmark_hi)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asset-registry",
        default="implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json",
    )
    parser.add_argument(
        "--hinge-refresh-source",
        default="implementation/phase1/pbd_hinge_refresh_source.json",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_refresh_alignment_report.json",
    )
    parser.add_argument("--min-column-refresh-count", type=int, default=1)
    parser.add_argument("--min-rebar-sensitive-column-count", type=int, default=1)
    parser.add_argument("--rebar-envelope-pad-abs", type=float, default=0.02)
    args = parser.parse_args()

    registry = _load_json(Path(args.asset_registry))
    registry_summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    registry_rows = [row for row in (registry.get("rows") or []) if isinstance(row, dict)]
    benchmark_rows = [row for row in registry_rows if _safe_bool(row.get("benchmark_ready"), False)]
    refresh_source = _load_json(Path(args.hinge_refresh_source))
    refresh_rows = _extract_refresh_rows(refresh_source)

    contract = {
        "min_column_refresh_count": int(args.min_column_refresh_count),
        "min_rebar_sensitive_column_count": int(args.min_rebar_sensitive_column_count),
        "rebar_envelope_pad_abs": float(args.rebar_envelope_pad_abs),
    }

    if not benchmark_rows:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_BENCHMARK_INVALID",
            "reason": REASONS["ERR_BENCHMARK_INVALID"],
            "inputs": {
                "asset_registry": str(args.asset_registry),
                "hinge_refresh_source": str(args.hinge_refresh_source),
                "out": str(args.out),
            },
            "contract": contract,
            "observed": {
                "benchmark_fixture_count": 0,
                "refresh_row_count": int(len(refresh_rows)),
                "refresh_column_row_count": 0,
                "refresh_rebar_sensitive_column_count": 0,
            },
            "rows_head": [],
        }
        _write_json(Path(args.out), payload)
        print(f"Wrote PEER SPD hinge refresh alignment report: {args.out}")
        raise SystemExit(1)

    if not refresh_rows:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_REFRESH_SOURCE_INVALID",
            "reason": REASONS["ERR_REFRESH_SOURCE_INVALID"],
            "inputs": {
                "asset_registry": str(args.asset_registry),
                "hinge_refresh_source": str(args.hinge_refresh_source),
                "out": str(args.out),
            },
            "contract": contract,
            "observed": {
                "benchmark_fixture_count": int(len(benchmark_rows)),
                "refresh_row_count": 0,
                "refresh_column_row_count": 0,
                "refresh_rebar_sensitive_column_count": 0,
            },
            "rows_head": [],
        }
        _write_json(Path(args.out), payload)
        print(f"Wrote PEER SPD hinge refresh alignment report: {args.out}")
        raise SystemExit(1)

    benchmark_fixtures = []
    for row in benchmark_rows:
        fixture_path = Path(str(row.get("fixture_path", "") or "").strip())
        fixture = _load_json(fixture_path) if fixture_path.exists() else {}
        specimen_summary = fixture.get("specimen_summary") if isinstance(fixture.get("specimen_summary"), dict) else {}
        targets = fixture.get("hinge_refresh_targets") if isinstance(fixture.get("hinge_refresh_targets"), dict) else {}
        benchmark_fixtures.append(
            {
                "seed_id": str(row.get("seed_id", "") or ""),
                "fixture_path": str(fixture_path),
                "holdout_split": str(row.get("holdout_split", "") or ""),
                "longitudinal_rebar_ratio": _safe_float(specimen_summary.get("longitudinal_rebar_ratio"), 0.0),
                "peak_abs_drift_ratio": _safe_float(
                    (fixture.get("hysteresis_summary") or {}).get("peak_abs_drift_ratio"), 0.0
                ),
                "rebar_sensitive_expected": _safe_bool(targets.get("rebar_sensitive_expected"), False),
            }
        )

    column_rows = [
        row for row in refresh_rows if str(row.get("member_type", "") or "").strip().lower() == "column"
    ]
    rebar_sensitive_column_rows = [row for row in column_rows if _safe_bool(row.get("rebar_sensitive"), False)]

    benchmark_rebar_values = [
        float(row["longitudinal_rebar_ratio"])
        for row in benchmark_fixtures
        if float(row["longitudinal_rebar_ratio"]) > 0.0
    ]
    benchmark_peak_drift_values = [
        float(row["peak_abs_drift_ratio"]) for row in benchmark_fixtures if float(row["peak_abs_drift_ratio"]) > 0.0
    ]
    refresh_before_values = [
        _safe_float(row.get("before_rebar_ratio"), 0.0)
        for row in column_rows
        if _safe_float(row.get("before_rebar_ratio"), 0.0) > 0.0
    ]
    refresh_after_values = [
        _safe_float(row.get("after_rebar_ratio"), 0.0)
        for row in column_rows
        if _safe_float(row.get("after_rebar_ratio"), 0.0) > 0.0
    ]
    refresh_combined_values = refresh_before_values + refresh_after_values

    benchmark_rebar_min, benchmark_rebar_max = _ratio_bounds(benchmark_rebar_values)
    benchmark_peak_drift_min, benchmark_peak_drift_max = _ratio_bounds(benchmark_peak_drift_values)
    refresh_rebar_min, refresh_rebar_max = _ratio_bounds(refresh_combined_values)
    rebar_envelope_overlap = _overlap_with_padding(
        benchmark_rebar_min,
        benchmark_rebar_max,
        refresh_rebar_min,
        refresh_rebar_max,
        pad_abs=float(args.rebar_envelope_pad_abs),
    )

    source_summary = refresh_source.get("summary") if isinstance(refresh_source.get("summary"), dict) else {}
    member_type_counts = Counter(str(row.get("member_type", "") or "").strip().lower() for row in refresh_rows)

    if len(column_rows) < int(args.min_column_refresh_count):
        reason_code = "ERR_COLUMN_REFRESH_MISSING"
    elif len(rebar_sensitive_column_rows) < int(args.min_rebar_sensitive_column_count):
        reason_code = "ERR_REBAR_SENSITIVE_COLUMN_MISSING"
    elif not rebar_envelope_overlap:
        reason_code = "ERR_REBAR_RATIO_ENVELOPE_DISJOINT"
    else:
        reason_code = "PASS"

    observed = {
        "benchmark_fixture_count": int(len(benchmark_fixtures)),
        "benchmark_holdout_count": int(registry_summary.get("holdout_count", 0) or 0),
        "benchmark_rebar_sensitive_count": int(
            sum(1 for row in benchmark_fixtures if bool(row.get("rebar_sensitive_expected")))
        ),
        "benchmark_longitudinal_rebar_ratio_min": float(benchmark_rebar_min),
        "benchmark_longitudinal_rebar_ratio_max": float(benchmark_rebar_max),
        "benchmark_peak_abs_drift_ratio_min": float(benchmark_peak_drift_min),
        "benchmark_peak_abs_drift_ratio_max": float(benchmark_peak_drift_max),
        "refresh_row_count": int(len(refresh_rows)),
        "refresh_column_row_count": int(len(column_rows)),
        "refresh_rebar_sensitive_column_count": int(len(rebar_sensitive_column_rows)),
        "refresh_before_rebar_ratio_min": float(_ratio_bounds(refresh_before_values)[0]),
        "refresh_before_rebar_ratio_max": float(_ratio_bounds(refresh_before_values)[1]),
        "refresh_after_rebar_ratio_min": float(_ratio_bounds(refresh_after_values)[0]),
        "refresh_after_rebar_ratio_max": float(_ratio_bounds(refresh_after_values)[1]),
        "refresh_combined_rebar_ratio_min": float(refresh_rebar_min),
        "refresh_combined_rebar_ratio_max": float(refresh_rebar_max),
        "rebar_envelope_overlap_with_padding": bool(rebar_envelope_overlap),
        "source_artifact_kind": str(source_summary.get("source_artifact_kind", "") or ""),
        "source_mode": str(source_summary.get("source_mode", "") or ""),
        "source_unique_member_count": int(source_summary.get("unique_member_count", 0) or 0),
        "source_member_type_counts": dict(member_type_counts),
    }

    row_head = [
        {
            "member_id": str(row.get("member_id", "") or ""),
            "group_id": str(row.get("group_id", "") or ""),
            "yield_rotation": _safe_float(row.get("yield_rotation"), 0.0),
            "ultimate_rotation": _safe_float(row.get("ultimate_rotation"), 0.0),
            "before_rebar_ratio": _safe_float(row.get("before_rebar_ratio"), 0.0),
            "after_rebar_ratio": _safe_float(row.get("after_rebar_ratio"), 0.0),
            "rebar_sensitive": _safe_bool(row.get("rebar_sensitive"), False),
            "action_family": str(row.get("action_family", "") or ""),
        }
        for row in column_rows[:5]
    ]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "inputs": {
            "asset_registry": str(args.asset_registry),
            "hinge_refresh_source": str(args.hinge_refresh_source),
            "out": str(args.out),
        },
        "contract": contract,
        "observed": observed,
        "benchmark_rows_head": benchmark_fixtures[:5],
        "rows_head": row_head,
    }
    _write_json(Path(args.out), payload)
    print(f"Wrote PEER SPD hinge refresh alignment report: {args.out}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
