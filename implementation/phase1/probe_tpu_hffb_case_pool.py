#!/usr/bin/env python3
"""Probe TPU HFFB case ids and summarize which official cases are usable."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


RUN_ID = "phase1-probe-tpu-hffb-case-pool"
SCHEMA_VERSION = "1.0"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fixture_report_map(entries: list[str]) -> dict[str, Path]:
    fixtures: dict[str, Path] = {}
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(
                "--fetch-report-fixture entries must use CASE_ID=REPORT_JSON"
            )
        case_id, report_path = entry.split("=", 1)
        case_id = case_id.strip()
        report_path = report_path.strip()
        if not case_id or not report_path:
            raise SystemExit(
                "--fetch-report-fixture entries must use CASE_ID=REPORT_JSON"
            )
        fixtures[case_id] = Path(report_path)
    return fixtures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument(
        "--fetch-report-fixture",
        action="append",
        default=[],
        help=(
            "Use a prebuilt fetch report for one case instead of live TPU network fetch. "
            "Format: CASE_ID=REPORT_JSON. Intended for offline/default tests; live "
            "fetch remains the explicit integration path when this is omitted."
        ),
    )
    parser.add_argument("--probe-dir", default="implementation/phase1/open_data/wind/tpu/probes")
    parser.add_argument("--out-report", default="implementation/phase1/open_data/wind/tpu_case_pool_probe.json")
    args = parser.parse_args()

    case_ids = [str(value).strip() for value in args.case_id if str(value).strip()]
    fetch_report_fixtures = _fixture_report_map(args.fetch_report_fixture)
    probe_dir = Path(args.probe_dir)
    out_report = Path(args.out_report)
    probe_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    pass_count = 0
    empty_count = 0
    fetch_error_blockers: list[str] = []
    for case_id in case_ids:
        out_mat = probe_dir / f"case_{case_id}.mat"
        out_manifest = probe_dir / f"case_{case_id}.manifest.json"
        out_fetch_report = probe_dir / f"case_{case_id}.report.json"
        fixture_report = fetch_report_fixtures.get(case_id)
        fetch_mode = "fixture_report" if fixture_report is not None else "live_fetch"
        if fixture_report is not None:
            fetch_report = _load_json(fixture_report)
            _write_json(out_fetch_report, fetch_report)
            fetch_returncode = 0 if fetch_report.get("contract_pass") is True else 1
        else:
            proc = subprocess.run(
                [
                    sys.executable,
                    "implementation/phase1/fetch_tpu_case_mat.py",
                    "--case-id",
                    case_id,
                    "--out-mat",
                    str(out_mat),
                    "--source-manifest-out",
                    str(out_manifest),
                    "--out-report",
                    str(out_fetch_report),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            fetch_report = _load_json(out_fetch_report)
            fetch_returncode = int(proc.returncode)
        summary = fetch_report.get("summary") if isinstance(fetch_report.get("summary"), dict) else {}
        reason_code = str(fetch_report.get("reason_code", ""))
        if reason_code == "PASS":
            pass_count += 1
        if reason_code == "ERR_MAT_EMPTY":
            empty_count += 1
        if reason_code not in {"PASS", "ERR_MAT_EMPTY"}:
            fetch_error_blockers.append(f"case_{case_id}:{reason_code or 'missing_reason_code'}")
        rows.append(
            {
                "case_id": case_id,
                "contract_pass": bool(fetch_report.get("contract_pass", False)),
                "reason_code": reason_code,
                "source_name": str(summary.get("case_title", "") or ""),
                "mat_link_count": int(summary.get("mat_link_count", 0) or 0),
                "resolved_mat_url": str(summary.get("resolved_mat_url", "") or ""),
                "size_bytes": int(summary.get("size_bytes", 0) or 0),
                "probe_report": str(out_fetch_report),
                "probe_manifest": str(out_manifest),
                "probe_mat_path": str(out_mat) if out_mat.exists() else "",
                "fetch_returncode": fetch_returncode,
                "fetch_mode": fetch_mode,
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(rows) and pass_count > 0 and not fetch_error_blockers,
        "summary": {
            "probed_case_count": int(len(rows)),
            "pass_count": int(pass_count),
            "empty_count": int(empty_count),
            "usable_case_ids": [row["case_id"] for row in rows if bool(row.get("contract_pass", False))],
            "empty_case_ids": [row["case_id"] for row in rows if str(row.get("reason_code", "")) == "ERR_MAT_EMPTY"],
            "fetch_error_count": int(len(fetch_error_blockers)),
        },
        "rows": rows,
        "blockers": fetch_error_blockers,
    }
    _write_json(out_report, payload)
    print(f"Wrote TPU case pool probe report: {out_report}")


if __name__ == "__main__":
    main()
