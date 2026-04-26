#!/usr/bin/env python3
"""Materialize a TPU HFFB seed manifest from a downloaded raw CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


RUN_ID = "phase1-prepare-tpu-hffb-seed"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "TPU HFFB seed manifest prepared from raw CSV input.",
    "ERR_SEED_NOT_FOUND": "seed_id is not defined in the TPU HFFB seed manifest.",
    "ERR_RAW_WIND_MISSING": "raw wind csv is missing or unreadable.",
    "ERR_RAW_WIND_INVALID": "raw wind csv could not be profiled into a valid benchmark seed input.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _find_seed(seed_manifest: dict[str, Any], seed_id: str) -> dict[str, Any]:
    rows = seed_manifest.get("seed_cases", [])
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("seed_id", "")).strip() == seed_id:
            return row
    return {}


def _profile_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or []) if str(name or "").strip()]
        rows = list(reader)
    if not fieldnames or not rows:
        return {}

    time_candidates = [name for name in fieldnames if name.lower() in {"time", "time_s", "t", "time_sec"}]
    signal_candidates = [
        name
        for name in fieldnames
        if any(token in name.lower() for token in ("pressure", "cp", "force", "load", "signal_"))
        and name.lower() not in {"time", "time_s", "t", "time_sec"}
    ]
    dt_s = math.nan
    duration_hours = math.nan
    if time_candidates:
        time_name = time_candidates[0]
        times = [_safe_float(row.get(time_name)) for row in rows]
        finite = [value for value in times if math.isfinite(value)]
        if len(finite) >= 2:
            diffs = [finite[idx + 1] - finite[idx] for idx in range(len(finite) - 1) if math.isfinite(finite[idx + 1] - finite[idx])]
            positive = [diff for diff in diffs if diff > 0.0]
            if positive:
                dt_s = min(positive)
            duration_hours = max(0.0, (finite[-1] - finite[0]) / 3600.0)
    return {
        "row_count": int(len(rows)),
        "fieldnames": fieldnames,
        "signal_columns": signal_candidates,
        "dt_s": None if not math.isfinite(dt_s) else float(dt_s),
        "duration_hours": None if not math.isfinite(duration_hours) else float(duration_hours),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed-manifest",
        default="implementation/phase1/open_data/wind/tpu_hffb_seed_manifest.json",
    )
    parser.add_argument("--seed-id", required=True)
    parser.add_argument("--raw-wind", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-name", default="")
    parser.add_argument("--hazard-type", default="wind_hffb")
    parser.add_argument("--dt-s", type=float, default=math.nan)
    parser.add_argument("--duration-hours", type=float, default=math.nan)
    parser.add_argument("--out-manifest", default="")
    parser.add_argument("--out-report", default="")
    args = parser.parse_args()

    seed_manifest_path = Path(args.seed_manifest)
    seed_manifest = _load_json(seed_manifest_path)
    seed = _find_seed(seed_manifest, str(args.seed_id).strip())
    raw_wind_path = Path(args.raw_wind)

    reason_code = "PASS"
    reason = REASONS[reason_code]
    csv_profile: dict[str, Any] = {}

    if not seed:
        reason_code = "ERR_SEED_NOT_FOUND"
        reason = REASONS[reason_code]
    elif not raw_wind_path.exists():
        reason_code = "ERR_RAW_WIND_MISSING"
        reason = REASONS[reason_code]
    else:
        try:
            csv_profile = _profile_csv(raw_wind_path)
        except Exception:
            csv_profile = {}
        if not csv_profile or int(csv_profile.get("row_count", 0)) <= 0:
            reason_code = "ERR_RAW_WIND_INVALID"
            reason = REASONS[reason_code]

    if str(args.out_manifest).strip():
        out_manifest = Path(str(args.out_manifest).strip())
    else:
        out_manifest = Path(str(((seed.get("expected_local_targets") or {}).get("source_manifest", "")) or ""))
        if not str(out_manifest).strip():
            out_manifest = raw_wind_path.with_suffix(".manifest.json")

    if str(args.out_report).strip():
        out_report = Path(str(args.out_report).strip())
    else:
        out_report = out_manifest.with_suffix(".prepare_report.json")

    source_url = str(args.source_url).strip()
    if not source_url:
        urls = seed_manifest.get("source_urls", [])
        if isinstance(urls, list) and urls:
            source_url = str(urls[0]).strip()

    source_name = str(args.source_name).strip() or f"TPU HFFB seed {args.seed_id}"
    dt_s = float(args.dt_s) if math.isfinite(float(args.dt_s)) else _safe_float(csv_profile.get("dt_s"))
    duration_hours = (
        float(args.duration_hours)
        if math.isfinite(float(args.duration_hours))
        else _safe_float(csv_profile.get("duration_hours"))
    )

    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_name": source_name,
        "source_url": source_url,
        "real_source": True,
        "hazard_type": str(args.hazard_type).strip() or "wind_hffb",
        "data_path": str(raw_wind_path),
        "sha256": _sha256_file(raw_wind_path) if raw_wind_path.exists() else "",
        "duration_hours": None if not math.isfinite(duration_hours) else float(duration_hours),
        "dt_s": None if not math.isfinite(dt_s) else float(dt_s),
        "benchmark_seed_id": str(args.seed_id).strip(),
        "case_role": str(seed.get("case_role", "") or ""),
        "holdout_split": str(seed.get("holdout_split", "") or ""),
        "source_origin_class": "official_external_benchmark",
        "seed_catalog_path": str(seed_manifest_path),
        "selection_filters": seed.get("selection_filters", {}) if isinstance(seed.get("selection_filters"), dict) else {},
        "csv_profile": csv_profile,
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
    }

    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "seed_manifest": str(seed_manifest_path),
            "seed_id": str(args.seed_id).strip(),
            "raw_wind": str(raw_wind_path),
            "source_url": source_url,
            "source_name": source_name,
        },
        "summary": {
            "holdout_split": str(seed.get("holdout_split", "") or ""),
            "case_role": str(seed.get("case_role", "") or ""),
            "row_count": int(csv_profile.get("row_count", 0)),
            "signal_column_count": int(len(csv_profile.get("signal_columns", []))) if isinstance(csv_profile.get("signal_columns"), list) else 0,
            "dt_s": manifest_payload.get("dt_s"),
            "duration_hours": manifest_payload.get("duration_hours"),
        },
        "artifacts": {
            "out_manifest": str(out_manifest),
        },
    }

    _write_json(out_manifest, manifest_payload)
    _write_json(out_report, report_payload)
    print(f"Wrote TPU HFFB source manifest: {out_manifest}")
    print(f"Wrote TPU HFFB seed report: {out_report}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
