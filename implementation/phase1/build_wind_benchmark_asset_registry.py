#!/usr/bin/env python3
"""Build a local registry of available wind benchmark assets and probes."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


RUN_ID = "phase1-build-wind-benchmark-asset-registry"
SCHEMA_VERSION = "1.0"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _discover_source_manifests(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*.json"):
        name = path.name
        if not (name.endswith(".manifest.json") or name.endswith(".source_manifest.json")):
            continue
        if name.endswith(".fetch_manifest.json") or name.endswith(".prepare_report.json") or name.endswith(".convert_report.json"):
            continue
        paths.append(path)
    return sorted(paths)


def _asset_row_from_manifest(path: Path) -> dict[str, Any] | None:
    manifest = _load_json(path)
    data_path = str(manifest.get("data_path", "") or "")
    if not data_path:
        return None
    csv_profile = manifest.get("csv_profile") if isinstance(manifest.get("csv_profile"), dict) else {}
    csv_path = Path(data_path)
    if data_path.lower().endswith(".csv") and csv_path.exists():
        if not csv_profile:
            csv_profile = _profile_csv(csv_path)
    signal_columns = csv_profile.get("signal_columns", [])
    data_path_lower = data_path.lower()
    asset_type = "csv_manifest" if data_path_lower.endswith(".csv") else "raw_manifest"
    fieldnames = csv_profile.get("fieldnames", []) if isinstance(csv_profile.get("fieldnames"), list) else []
    has_time_column = "time_s" in fieldnames
    has_across_wind_force_column = "across_wind_force_kN" in fieldnames
    dt_s = manifest.get("dt_s", csv_profile.get("dt_s"))
    duration_hours = manifest.get("duration_hours", csv_profile.get("duration_hours"))
    raw_hffb_mapping_eligible = bool(
        str(manifest.get("source_origin_class", "") or "") == "official_external_benchmark"
        and int(len(signal_columns)) > 0
    )
    wind_gate_ready = bool(
        data_path_lower.endswith(".csv")
        and has_time_column
        and has_across_wind_force_column
        and isinstance(duration_hours, (int, float))
        and math.isfinite(float(duration_hours))
        and float(duration_hours) >= 10.0
    )
    blocker = ""
    if not wind_gate_ready:
        if not has_time_column:
            blocker = "missing_time_s_column"
        elif not has_across_wind_force_column:
            blocker = "missing_across_wind_force_kN_column"
        elif not isinstance(duration_hours, (int, float)) or not math.isfinite(float(duration_hours)):
            blocker = "duration_unknown"
        elif float(duration_hours) < 10.0:
            blocker = "duration_below_10h"
    return {
        "asset_type": asset_type,
        "path": str(path),
        "source_name": str(manifest.get("source_name", "") or ""),
        "source_url": str(manifest.get("source_url", "") or ""),
        "real_source": bool(manifest.get("real_source", False)),
        "source_origin_class": str(manifest.get("source_origin_class", "") or ""),
        "benchmark_seed_id": str(manifest.get("benchmark_seed_id", "") or ""),
        "case_id": str(manifest.get("case_id", "") or ""),
        "case_role": str(manifest.get("case_role", "") or ""),
        "holdout_split": str(manifest.get("holdout_split", "") or ""),
        "contract_pass": bool(manifest.get("contract_pass", False)),
        "reason_code": str(manifest.get("reason_code", "") or ""),
        "data_path": data_path,
        "row_count": int(csv_profile.get("row_count", 0) or 0),
        "signal_column_count": int(len(signal_columns)) if isinstance(signal_columns, list) else 0,
        "fieldnames_head": fieldnames[:10],
        "dt_s": None if not isinstance(dt_s, (int, float)) or not math.isfinite(float(dt_s)) else float(dt_s),
        "duration_hours": None if not isinstance(duration_hours, (int, float)) or not math.isfinite(float(duration_hours)) else float(duration_hours),
        "raw_hffb_mapping_eligible": raw_hffb_mapping_eligible,
        "wind_time_history_gate_eligible": wind_gate_ready,
        "wind_time_history_gate_blocker": blocker,
        "sha256": str(manifest.get("sha256", "") or ""),
    }


def _profile_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or []) if str(name or "").strip()]
        rows = list(reader)
    time_candidates = [name for name in fieldnames if name.lower() in {"time", "time_s", "t", "time_sec"}]
    signal_candidates = [
        name
        for name in fieldnames
        if any(token in name.lower() for token in ("pressure", "cp", "force", "load", "signal_"))
        and name.lower() not in {"time", "time_s", "t", "time_sec"}
    ]
    dt_s = None
    duration_hours = None
    if time_candidates and rows:
        times = []
        for row in rows:
            try:
                times.append(float(row.get(time_candidates[0], "")))
            except Exception:
                continue
        if len(times) >= 2:
            diffs = [times[idx + 1] - times[idx] for idx in range(len(times) - 1)]
            positive = [diff for diff in diffs if math.isfinite(diff) and diff > 0.0]
            if positive:
                dt_s = min(positive)
            duration_hours = max(0.0, (times[-1] - times[0]) / 3600.0)
    return {
        "row_count": int(len(rows)),
        "fieldnames": fieldnames,
        "signal_columns": signal_candidates,
        "dt_s": dt_s,
        "duration_hours": duration_hours,
    }


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("benchmark_seed_id", "") or "").strip()
            or str(row.get("case_id", "") or "").strip()
            or str(row.get("sha256", "") or "").strip()
            or str(row.get("path", "") or "").strip()
        )
        current = deduped.get(key)
        if current is None:
            deduped[key] = row
            continue
        current_path = str(current.get("path", "") or "")
        new_path = str(row.get("path", "") or "")
        current_score = (
            int(bool(current.get("benchmark_seed_id"))),
            int(bool(current.get("contract_pass"))),
            -len(current_path),
        )
        new_score = (
            int(bool(row.get("benchmark_seed_id"))),
            int(bool(row.get("contract_pass"))),
            -len(new_path),
        )
        if new_score > current_score:
            deduped[key] = row
    return list(deduped.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wind-root", default="implementation/phase1/open_data/wind")
    parser.add_argument("--probe-report", default="implementation/phase1/open_data/wind/tpu_case_pool_probe.json")
    parser.add_argument("--tpu-hffb-benchmark-report", default="implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json")
    parser.add_argument("--out", default="implementation/phase1/open_data/wind/wind_benchmark_asset_registry.json")
    args = parser.parse_args()

    wind_root = Path(args.wind_root)
    probe_report_path = Path(args.probe_report)
    tpu_benchmark_report_path = Path(args.tpu_hffb_benchmark_report)
    manifests = _discover_source_manifests(wind_root)
    asset_rows = [row for row in (_asset_row_from_manifest(path) for path in manifests) if row is not None]
    probe_report = _load_json(probe_report_path)
    tpu_benchmark_report = _load_json(tpu_benchmark_report_path)
    probe_rows = probe_report.get("rows") if isinstance(probe_report.get("rows"), list) else []
    benchmark_ready_rows = _dedupe_rows([
        row
        for row in asset_rows
        if bool(row.get("real_source", False)) and str(row.get("data_path", "")).lower().endswith(".csv")
    ])
    raw_probe_rows = _dedupe_rows([
        row
        for row in asset_rows
        if bool(row.get("real_source", False))
        and bool(row.get("contract_pass", False))
        and str(row.get("data_path", "")).lower().endswith(".mat")
        and str(row.get("source_origin_class", "") or "") == "official_external_benchmark"
    ])
    rejected_rows = [row for row in asset_rows if row not in benchmark_ready_rows and row not in raw_probe_rows]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "summary": {
            "benchmark_ready_asset_count": int(len(benchmark_ready_rows)),
            "raw_probe_manifest_count": int(len(raw_probe_rows)),
            "rejected_manifest_count": int(len(rejected_rows)),
            "official_external_benchmark_count": int(sum(1 for row in benchmark_ready_rows if row.get("source_origin_class") == "official_external_benchmark")),
            "materialized_tpu_seed_count": int(sum(1 for row in benchmark_ready_rows if str(row.get("benchmark_seed_id", "")).startswith("tpu_hffb_"))),
            "probe_case_count": int(len(probe_rows)),
            "probe_pass_count": int(sum(1 for row in probe_rows if bool(row.get("contract_pass", False)))),
            "tpu_hffb_benchmark_contract_pass": bool(tpu_benchmark_report.get("contract_pass", False)) if isinstance(tpu_benchmark_report, dict) else False,
            "tpu_hffb_selected_asset_count": int((tpu_benchmark_report.get("summary") or {}).get("selected_asset_count", 0)) if isinstance((tpu_benchmark_report or {}).get("summary"), dict) else 0,
            "tpu_hffb_isolated_case_count": int((tpu_benchmark_report.get("summary") or {}).get("isolated_case_count", 0)) if isinstance((tpu_benchmark_report or {}).get("summary"), dict) else 0,
            "tpu_hffb_interference_case_count": int((tpu_benchmark_report.get("summary") or {}).get("interference_case_count", 0)) if isinstance((tpu_benchmark_report or {}).get("summary"), dict) else 0,
        },
        "benchmark_ready_assets": benchmark_ready_rows,
        "raw_probe_manifests": raw_probe_rows,
        "rejected_source_manifests": rejected_rows,
        "tpu_probe_pool": probe_report,
        "tpu_hffb_benchmark_gate": tpu_benchmark_report if isinstance(tpu_benchmark_report, dict) else {},
    }
    _write_json(Path(args.out), payload)
    print(f"Wrote wind benchmark asset registry: {args.out}")


if __name__ == "__main__":
    main()
