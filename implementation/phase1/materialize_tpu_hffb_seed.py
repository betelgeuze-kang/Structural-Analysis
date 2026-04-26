#!/usr/bin/env python3
"""One-shot TPU HFFB seed materializer: fetch MAT, convert to CSV, prepare manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


RUN_ID = "phase1-materialize-tpu-hffb-seed"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "TPU HFFB seed materialized successfully from case page and MAT source.",
    "ERR_FETCH_STEP": "TPU MAT fetch step failed.",
    "ERR_CONVERT_STEP": "TPU MAT-to-CSV conversion step failed.",
    "ERR_PREPARE_STEP": "TPU seed manifest preparation step failed.",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-id", required=True)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--case-id", default="")
    parser.add_argument("--case-page-url", default="")
    parser.add_argument("--case-page-html", default="")
    parser.add_argument("--mat-url", default="")
    parser.add_argument("--mat-index", type=int, default=0)
    parser.add_argument("--dataset-key", default="")
    parser.add_argument("--time-key", default="")
    parser.add_argument("--source-name", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--out-report", default="")
    args = parser.parse_args()

    seed_id = str(args.seed_id).strip()
    out_dir = Path(str(args.out_dir).strip()) if str(args.out_dir).strip() else Path("implementation/phase1/open_data/wind/tpu") / seed_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fetched_mat = out_dir / f"{seed_id}.mat"
    fetch_manifest = out_dir / f"{seed_id}.fetch_manifest.json"
    fetch_report = out_dir / f"{seed_id}.fetch_report.json"
    out_csv = out_dir / f"{seed_id}.csv"
    convert_report = out_dir / f"{seed_id}.convert_report.json"
    out_manifest = out_dir / f"{seed_id}.source_manifest.json"
    prepare_report = out_dir / f"{seed_id}.prepare_report.json"
    out_report = Path(str(args.out_report).strip()) if str(args.out_report).strip() else out_dir / f"{seed_id}.materialize_report.json"

    fetch_cmd = [
        sys.executable,
        "implementation/phase1/fetch_tpu_case_mat.py",
        "--out-mat",
        str(fetched_mat),
        "--source-manifest-out",
        str(fetch_manifest),
        "--out-report",
        str(fetch_report),
        "--mat-index",
        str(int(args.mat_index)),
    ]
    if str(args.case_id).strip():
        fetch_cmd.extend(["--case-id", str(args.case_id).strip()])
    if str(args.case_page_url).strip():
        fetch_cmd.extend(["--case-page-url", str(args.case_page_url).strip()])
    if str(args.case_page_html).strip():
        fetch_cmd.extend(["--case-page-html", str(args.case_page_html).strip()])
    if str(args.mat_url).strip():
        fetch_cmd.extend(["--mat-url", str(args.mat_url).strip()])
    fetch_proc = _run(fetch_cmd)

    reason_code = "PASS"
    reason = REASONS[reason_code]

    convert_proc: subprocess.CompletedProcess[str] | None = None
    prepare_proc: subprocess.CompletedProcess[str] | None = None
    if fetch_proc.returncode != 0:
        reason_code = "ERR_FETCH_STEP"
        reason = REASONS[reason_code]
    else:
        convert_cmd = [
            sys.executable,
            "implementation/phase1/convert_tpu_mat_to_csv.py",
            "--input-mat",
            str(fetched_mat),
            "--out-csv",
            str(out_csv),
            "--out-report",
            str(convert_report),
        ]
        if str(args.dataset_key).strip():
            convert_cmd.extend(["--dataset-key", str(args.dataset_key).strip()])
        if str(args.time_key).strip():
            convert_cmd.extend(["--time-key", str(args.time_key).strip()])
        convert_proc = _run(convert_cmd)
        if convert_proc.returncode != 0:
            reason_code = "ERR_CONVERT_STEP"
            reason = REASONS[reason_code]

    if reason_code == "PASS":
        fetch_manifest_payload = _load_json(fetch_manifest)
        prepare_cmd = [
            sys.executable,
            "implementation/phase1/prepare_tpu_hffb_seed.py",
            "--seed-id",
            seed_id,
            "--raw-wind",
            str(out_csv),
            "--out-manifest",
            str(out_manifest),
            "--out-report",
            str(prepare_report),
        ]
        source_name = str(args.source_name).strip() or str(fetch_manifest_payload.get("source_name", "")).strip()
        source_url = str(args.source_url).strip() or str(fetch_manifest_payload.get("source_url", "")).strip()
        if source_name:
            prepare_cmd.extend(["--source-name", source_name])
        if source_url:
            prepare_cmd.extend(["--source-url", source_url])
        prepare_proc = _run(prepare_cmd)
        if prepare_proc.returncode != 0:
            reason_code = "ERR_PREPARE_STEP"
            reason = REASONS[reason_code]

    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "seed_id": seed_id,
            "out_dir": str(out_dir),
            "case_id": str(args.case_id).strip(),
            "case_page_url": str(args.case_page_url).strip(),
            "case_page_html": str(args.case_page_html).strip(),
            "mat_url": str(args.mat_url).strip(),
            "mat_index": int(args.mat_index),
            "dataset_key": str(args.dataset_key).strip(),
            "time_key": str(args.time_key).strip(),
        },
        "steps": {
            "fetch": {
                "returncode": int(fetch_proc.returncode),
                "stdout": fetch_proc.stdout,
                "stderr": fetch_proc.stderr,
                "report": str(fetch_report),
            },
            "convert": {
                "returncode": int(convert_proc.returncode) if convert_proc is not None else None,
                "stdout": convert_proc.stdout if convert_proc is not None else "",
                "stderr": convert_proc.stderr if convert_proc is not None else "",
                "report": str(convert_report),
            },
            "prepare": {
                "returncode": int(prepare_proc.returncode) if prepare_proc is not None else None,
                "stdout": prepare_proc.stdout if prepare_proc is not None else "",
                "stderr": prepare_proc.stderr if prepare_proc is not None else "",
                "report": str(prepare_report),
            },
        },
        "artifacts": {
            "fetched_mat": str(fetched_mat) if fetched_mat.exists() else "",
            "out_csv": str(out_csv) if out_csv.exists() else "",
            "out_manifest": str(out_manifest) if out_manifest.exists() else "",
        },
    }
    _write_json(out_report, report_payload)
    print(f"Wrote TPU seed materialization report: {out_report}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
