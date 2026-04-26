#!/usr/bin/env python3
"""Validate diversified official TPU raw HFFB benchmark assets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


RUN_ID = "phase1-run-tpu-hffb-benchmark-gate"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "Official TPU raw HFFB benchmark assets cover isolated and interference high-rise cases for diversified mapping validation.",
    "ERR_REGISTRY_MISSING": "Wind benchmark asset registry is missing or invalid.",
    "ERR_TPU_ASSET_COUNT": "Insufficient official TPU materialized assets are available.",
    "ERR_SOURCE_REAL": "One or more TPU assets are not marked as real official sources.",
    "ERR_MAPPING_ELIGIBILITY": "One or more TPU assets are not eligible for raw HFFB mapping validation.",
    "ERR_TIME_AXIS": "One or more TPU assets is missing a usable time axis or sample interval.",
    "ERR_SIGNAL_COLUMNS": "One or more TPU assets is missing signal columns.",
    "ERR_ISOLATED_CASE_MISSING": "No isolated TPU high-rise benchmark asset is present.",
    "ERR_INTERFERENCE_CASE_MISSING": "No interference TPU high-rise benchmark asset is present.",
    "ERR_BLOCKER_VISIBILITY": "Non-time-history TPU assets must expose why they are blocked from the long-duration wind gate.",
}


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        out = float(value)
        if math.isfinite(out):
            return out
    return None


def _selected_tpu_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = registry.get("benchmark_ready_assets")
    if not isinstance(rows, list):
        return []
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not bool(row.get("real_source", False)):
            continue
        if str(row.get("source_origin_class", "")).strip() != "official_external_benchmark":
            continue
        if not str(row.get("benchmark_seed_id", "")).startswith("tpu_hffb_"):
            continue
        if not str(row.get("data_path", "")).lower().endswith(".csv"):
            continue
        selected.append(row)
    return selected


def _summary_numbers(rows: list[dict[str, Any]], key: str) -> tuple[float | None, float | None]:
    values = [_safe_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    if not clean:
        return None, None
    return min(clean), max(clean)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-registry", default="implementation/phase1/open_data/wind/wind_benchmark_asset_registry.json")
    parser.add_argument("--min-asset-count", type=int, default=2)
    parser.add_argument("--out", default="implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json")
    args = parser.parse_args()

    registry_path = Path(args.asset_registry)
    registry = _load_json(registry_path)
    registry_exists = isinstance(registry, dict)
    rows = _selected_tpu_rows(registry or {})

    isolated_count = int(sum(1 for row in rows if str(row.get("case_role", "")).strip() == "baseline_isolated_highrise"))
    interference_count = int(sum(1 for row in rows if str(row.get("case_role", "")).strip() == "neighbor_interference_highrise"))
    real_source_pass = bool(rows) and all(bool(row.get("real_source", False)) for row in rows)
    mapping_eligibility_pass = bool(rows) and all(bool(row.get("raw_hffb_mapping_eligible", False)) for row in rows)
    time_axis_pass = bool(rows) and all(_safe_float(row.get("dt_s")) not in {None, 0.0} for row in rows)
    signal_columns_pass = bool(rows) and all(int(row.get("signal_column_count", 0) or 0) > 0 for row in rows)
    isolated_case_pass = bool(isolated_count > 0)
    interference_case_pass = bool(interference_count > 0)
    blocker_visibility_pass = bool(rows) and all(
        bool(row.get("wind_time_history_gate_eligible", False))
        or bool(str(row.get("wind_time_history_gate_blocker", "")).strip())
        for row in rows
    )
    asset_count_pass = bool(len(rows) >= max(int(args.min_asset_count), 1))

    checks = {
        "registry_present": bool(registry_exists),
        "tpu_asset_count_pass": asset_count_pass,
        "source_real_pass": real_source_pass,
        "raw_hffb_mapping_eligible_pass": mapping_eligibility_pass,
        "time_axis_present_pass": time_axis_pass,
        "signal_columns_present_pass": signal_columns_pass,
        "isolated_case_present_pass": isolated_case_pass,
        "interference_case_present_pass": interference_case_pass,
        "wind_time_history_blocker_visible_pass": blocker_visibility_pass,
    }

    reason_code = "PASS"
    for candidate in (
        "ERR_REGISTRY_MISSING",
        "ERR_TPU_ASSET_COUNT",
        "ERR_SOURCE_REAL",
        "ERR_MAPPING_ELIGIBILITY",
        "ERR_TIME_AXIS",
        "ERR_SIGNAL_COLUMNS",
        "ERR_ISOLATED_CASE_MISSING",
        "ERR_INTERFERENCE_CASE_MISSING",
        "ERR_BLOCKER_VISIBILITY",
    ):
        if candidate == "ERR_REGISTRY_MISSING" and not checks["registry_present"]:
            reason_code = candidate
            break
        if candidate == "ERR_TPU_ASSET_COUNT" and not checks["tpu_asset_count_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_SOURCE_REAL" and not checks["source_real_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_MAPPING_ELIGIBILITY" and not checks["raw_hffb_mapping_eligible_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_TIME_AXIS" and not checks["time_axis_present_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_SIGNAL_COLUMNS" and not checks["signal_columns_present_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_ISOLATED_CASE_MISSING" and not checks["isolated_case_present_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_INTERFERENCE_CASE_MISSING" and not checks["interference_case_present_pass"]:
            reason_code = candidate
            break
        if candidate == "ERR_BLOCKER_VISIBILITY" and not checks["wind_time_history_blocker_visible_pass"]:
            reason_code = candidate
            break

    duration_min, duration_max = _summary_numbers(rows, "duration_hours")
    dt_min, dt_max = _summary_numbers(rows, "dt_s")
    signal_min, signal_max = _summary_numbers(rows, "signal_column_count")
    contract_pass = bool(all(checks.values()))

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "asset_registry": str(registry_path),
            "min_asset_count": int(args.min_asset_count),
            "out": str(args.out),
        },
        "checks": checks,
        "artifacts": {
            "asset_registry": str(registry_path),
            "report_json": str(args.out),
        },
        "summary": {
            "benchmark_scope": "raw_hffb_mapping_diversification_only",
            "selected_asset_count": int(len(rows)),
            "isolated_case_count": isolated_count,
            "interference_case_count": interference_count,
            "raw_hffb_mapping_eligible_count": int(sum(1 for row in rows if bool(row.get("raw_hffb_mapping_eligible", False)))),
            "wind_time_history_gate_eligible_count": int(sum(1 for row in rows if bool(row.get("wind_time_history_gate_eligible", False)))),
            "signal_column_count_min": 0 if signal_min is None else int(signal_min),
            "signal_column_count_max": 0 if signal_max is None else int(signal_max),
            "dt_s_min": dt_min,
            "dt_s_max": dt_max,
            "duration_hours_min": duration_min,
            "duration_hours_max": duration_max,
            "holdout_splits": sorted({str(row.get("holdout_split", "")).strip() for row in rows if str(row.get("holdout_split", "")).strip()}),
            "case_roles": sorted({str(row.get("case_role", "")).strip() for row in rows if str(row.get("case_role", "")).strip()}),
        },
        "rows": [
            {
                "benchmark_seed_id": str(row.get("benchmark_seed_id", "")),
                "source_name": str(row.get("source_name", "")),
                "source_url": str(row.get("source_url", "")),
                "case_role": str(row.get("case_role", "")),
                "holdout_split": str(row.get("holdout_split", "")),
                "data_path": str(row.get("data_path", "")),
                "row_count": int(row.get("row_count", 0) or 0),
                "signal_column_count": int(row.get("signal_column_count", 0) or 0),
                "dt_s": _safe_float(row.get("dt_s")),
                "duration_hours": _safe_float(row.get("duration_hours")),
                "raw_hffb_mapping_eligible": bool(row.get("raw_hffb_mapping_eligible", False)),
                "wind_time_history_gate_eligible": bool(row.get("wind_time_history_gate_eligible", False)),
                "wind_time_history_gate_blocker": str(row.get("wind_time_history_gate_blocker", "")),
            }
            for row in rows
        ],
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote TPU HFFB benchmark gate report: {args.out}")


if __name__ == "__main__":
    main()
