#!/usr/bin/env python3
"""Refresh external benchmark execution status without changing task lifecycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from generate_external_benchmark_execution_status_manifest import (
    _build_markdown,
    _load_updates_by_task,
    build_execution_status_manifest,
)


REASON_PASS = "PASS_EXTERNAL_BENCHMARK_REFRESH_LANE"
REASON_BLOCKED = "ERR_EXTERNAL_BENCHMARK_REFRESH_LANE_BLOCKED"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _completion_blockers(summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    executable = int(summary.get("executable_task_count", 0) or 0)
    completed = int(summary.get("completed_task_count", 0) or 0)
    planned = int(summary.get("planned_task_count", 0) or 0)
    in_progress = int(summary.get("in_progress_task_count", 0) or 0)
    failed = int(summary.get("failed_task_count", 0) or 0)
    kpi = int(summary.get("kpi_receipt_task_count", 0) or 0)
    bundles = int(summary.get("case_bundle_zip_task_count", 0) or 0)
    status_mode = str(summary.get("status_mode", "") or "")
    release_status_mode = str(summary.get("release_surface_status_mode", "") or "")

    if executable <= 0:
        blockers.append("executable_task_count_zero")
    if status_mode != "execution_complete_no_fail":
        blockers.append(f"status_mode_not_execution_complete_no_fail:{status_mode}")
    if release_status_mode != "execution_complete_no_fail":
        blockers.append(f"release_surface_status_mode_not_execution_complete_no_fail:{release_status_mode}")
    if completed != executable:
        blockers.append(f"completed_task_count_below_executable:{completed}/{executable}")
    if planned:
        blockers.append(f"planned_task_count_nonzero:{planned}")
    if in_progress:
        blockers.append(f"in_progress_task_count_nonzero:{in_progress}")
    if failed:
        blockers.append(f"failed_task_count_nonzero:{failed}")
    if kpi != executable:
        blockers.append(f"kpi_receipt_task_count_below_executable:{kpi}/{executable}")
    if bundles != executable:
        blockers.append(f"case_bundle_zip_task_count_below_executable:{bundles}/{executable}")
    return blockers


def build_refresh_report(
    *,
    execution_manifest_path: Path,
    updates_json_path: Path,
    status_manifest_out: Path,
) -> dict[str, Any]:
    execution_manifest = _load_json(execution_manifest_path)
    if not execution_manifest:
        return {
            "schema_version": "external-benchmark-refresh-lane.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_EXECUTION_MANIFEST_INVALID",
            "blockers": [f"execution_manifest_invalid:{execution_manifest_path}"],
        }

    updates_by_task = _load_updates_by_task(updates_json_path)
    status_manifest = build_execution_status_manifest(
        execution_manifest,
        execution_manifest_path=str(execution_manifest_path),
        updates_path=str(updates_json_path),
        updates_by_task=updates_by_task,
    )
    status_manifest_out.parent.mkdir(parents=True, exist_ok=True)
    _write_json(status_manifest_out, status_manifest)
    status_manifest_out.with_suffix(".md").write_text(_build_markdown(status_manifest), encoding="utf-8")

    summary = status_manifest.get("summary") if isinstance(status_manifest.get("summary"), dict) else {}
    blockers = _completion_blockers(summary)
    return {
        "schema_version": "external-benchmark-refresh-lane.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": REASON_PASS if not blockers else REASON_BLOCKED,
        "blockers": blockers,
        "summary": {
            "status_mode": summary.get("status_mode"),
            "release_surface_status_mode": summary.get("release_surface_status_mode"),
            "executable_task_count": summary.get("executable_task_count"),
            "completed_task_count": summary.get("completed_task_count"),
            "planned_task_count": summary.get("planned_task_count"),
            "in_progress_task_count": summary.get("in_progress_task_count"),
            "failed_task_count": summary.get("failed_task_count"),
            "kpi_receipt_task_count": summary.get("kpi_receipt_task_count"),
            "case_bundle_zip_task_count": summary.get("case_bundle_zip_task_count"),
            "completion_ratio": summary.get("completion_ratio"),
        },
        "artifacts": {
            "execution_manifest": str(execution_manifest_path),
            "updates_json": str(updates_json_path),
            "status_manifest": str(status_manifest_out),
            "status_manifest_md": str(status_manifest_out.with_suffix(".md")),
        },
        "claim_boundary": (
            "This local refresh verifies the checked-in external benchmark execution status manifest "
            "still reports execution_complete_no_fail from existing completed updates. It does not "
            "re-run, submit, or externally approve benchmark cases."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execution-manifest",
        type=Path,
        default=Path("implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json"),
    )
    parser.add_argument(
        "--updates-json",
        type=Path,
        default=Path("implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_updates.json"),
    )
    parser.add_argument(
        "--status-manifest-out",
        type=Path,
        default=Path("implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json"),
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=Path("implementation/phase1/release_evidence/productization/external_benchmark_refresh_lane_report.json"),
    )
    args = parser.parse_args()

    report = build_refresh_report(
        execution_manifest_path=args.execution_manifest,
        updates_json_path=args.updates_json,
        status_manifest_out=args.status_manifest_out,
    )
    _write_json(args.report_out, report)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    print(
        "external-benchmark-refresh-lane: "
        f"{'PASS' if report.get('contract_pass') else 'BLOCKED'} | "
        f"status={summary.get('status_mode')} | "
        f"completed={summary.get('completed_task_count')}/{summary.get('executable_task_count')} | "
        f"blockers={len(report.get('blockers') or [])}"
    )
    return 0 if report.get("contract_pass") else 3


if __name__ == "__main__":
    raise SystemExit(main())
