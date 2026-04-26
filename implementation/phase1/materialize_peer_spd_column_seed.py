#!/usr/bin/env python3
"""One-shot PEER SPD column seed materializer: fetch text resource, build raw JSON, normalize fixture."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


RUN_ID = "phase1-materialize-peer-spd-column-seed"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "PEER SPD column seeds materialized into raw specimen JSON and hinge fixtures.",
    "ERR_FETCH_STEP": "Raw hysteresis resource fetch step failed for one or more seeds.",
    "ERR_NORMALIZE_STEP": "Fixture normalization step failed for one or more seeds.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _seed_ids(seed_manifest: dict[str, Any], requested: list[str]) -> list[str]:
    if requested:
        return [str(seed_id).strip() for seed_id in requested if str(seed_id).strip()]
    rows = seed_manifest.get("seed_cases")
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            seed_id = str(row.get("seed_id", "")).strip()
            if seed_id:
                out.append(seed_id)
    return out


def _find_seed(seed_manifest: dict[str, Any], seed_id: str) -> dict[str, Any]:
    rows = seed_manifest.get("seed_cases")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("seed_id", "")).strip() == seed_id:
            return row
    return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-manifest", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json")
    parser.add_argument("--candidates", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_candidates.json")
    parser.add_argument("--specimen-pages-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_specimen_pages_report.json")
    parser.add_argument("--seed-id", action="append", default=[])
    parser.add_argument("--resource-out-dir", default="implementation/phase1/open_data/pbd_hinge/peer_spd_resources")
    parser.add_argument("--fetch-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_hysteresis_resources_report.json")
    parser.add_argument("--out-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_materialize_report.json")
    parser.add_argument("--prefer-cache", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    seed_manifest_path = Path(args.seed_manifest)
    seed_manifest = _load_json(seed_manifest_path)
    seed_ids = _seed_ids(seed_manifest, args.seed_id)

    fetch_cmd = [
        sys.executable,
        "implementation/phase1/fetch_peer_spd_hysteresis_resources.py",
        "--seed-manifest",
        str(seed_manifest_path),
        "--candidates",
        str(args.candidates),
        "--specimen-pages-report",
        str(args.specimen_pages_report),
        "--out-dir",
        str(args.resource_out_dir),
        "--out-report",
        str(args.fetch_report),
    ]
    for seed_id in seed_ids:
        fetch_cmd.extend(["--seed-id", seed_id])
    if bool(args.prefer_cache):
        fetch_cmd.append("--prefer-cache")
    fetch_proc = _run(fetch_cmd)

    reason_code = "PASS"
    reason = REASONS[reason_code]
    normalize_rows: list[dict[str, Any]] = []
    if fetch_proc.returncode != 0:
        reason_code = "ERR_FETCH_STEP"
        reason = REASONS[reason_code]
    else:
        for seed_id in seed_ids:
            seed = _find_seed(seed_manifest, seed_id)
            expected_targets = seed.get("expected_local_targets", {}) if isinstance(seed.get("expected_local_targets"), dict) else {}
            raw_json = Path(str(expected_targets.get("raw_json", "")))
            proc = _run(
                [
                    sys.executable,
                    "implementation/phase1/normalize_peer_spd_column_seed.py",
                    "--seed-manifest",
                    str(seed_manifest_path),
                    "--seed-id",
                    seed_id,
                    "--raw-specimen-json",
                    str(raw_json),
                ]
            )
            normalize_rows.append(
                {
                    "seed_id": seed_id,
                    "raw_json": str(raw_json),
                    "returncode": int(proc.returncode),
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                }
            )
            if proc.returncode != 0:
                reason_code = "ERR_NORMALIZE_STEP"
                reason = REASONS[reason_code]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "seed_manifest": str(seed_manifest_path),
            "candidates": str(args.candidates),
            "specimen_pages_report": str(args.specimen_pages_report),
            "seed_ids": seed_ids,
            "resource_out_dir": str(args.resource_out_dir),
            "fetch_report": str(args.fetch_report),
            "prefer_cache": bool(args.prefer_cache),
        },
        "steps": {
            "fetch": {
                "returncode": int(fetch_proc.returncode),
                "stdout": fetch_proc.stdout,
                "stderr": fetch_proc.stderr,
                "report": str(args.fetch_report),
            },
            "normalize": normalize_rows,
        },
        "summary": {
            "selected_seed_count": int(len(seed_ids)),
            "normalized_seed_count": int(sum(1 for row in normalize_rows if int(row.get("returncode", 1)) == 0)),
        },
    }
    _write_json(Path(args.out_report), payload)
    print(f"Wrote PEER SPD column materialization report: {args.out_report}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
