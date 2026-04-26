from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from implementation.phase1.batch_job_runner import build_batch_job_report
from implementation.phase1.generate_external_benchmark_execution_status_manifest import (
    build_execution_status_manifest,
)


DEFAULT_EXECUTION_MANIFEST = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json"
)
DEFAULT_UPDATES_JSON = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_updates.json"
)
DEFAULT_STATUS_MANIFEST = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json"
)
DEFAULT_BATCH_JOB_REPORT = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_batch_job_report.json"
)
DEFAULT_BATCH_SNAPSHOT_ROOT = Path(
    "implementation/phase1/release/external_benchmark_kickoff/batch_snapshots"
)
DEFAULT_COMMITTEE_SCRIPT = Path("implementation/phase1/generate_committee_review_package.py")
DEFAULT_REGISTRY_SCRIPT = Path("implementation/phase1/generate_signed_release_registry.py")
DEFAULT_EXTERNAL_SCRIPT = Path("implementation/phase1/prepare_external_validation_submission.py")

ALLOWED_STATUSES = {"planned", "in_progress", "completed", "failed"}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_updates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = str(row.get("task_id", "") or "").strip()
        if not task_id:
            continue
        status = str(row.get("lifecycle_status", "") or "").strip()
        if status not in ALLOWED_STATUSES:
            continue
        normalized[task_id] = {
            "task_id": task_id,
            "lifecycle_status": status,
            "updated_at": str(row.get("updated_at", "") or datetime.now(timezone.utc).isoformat()),
            "note": str(row.get("note", "") or ""),
            "artifact_path": str(row.get("artifact_path", "") or ""),
            "kpi_receipt_path": str(row.get("kpi_receipt_path", "") or ""),
            "case_bundle_dir": str(row.get("case_bundle_dir", "") or ""),
            "case_bundle_zip_path": str(row.get("case_bundle_zip_path", "") or ""),
            "bundle_id": str(row.get("bundle_id", "") or ""),
        }
    return normalized


def _load_update_store(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("updates") if isinstance(payload.get("updates"), list) else []
    return _normalize_updates([row for row in rows if isinstance(row, dict)])


def _build_update_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if str(args.batch_updates_json).strip():
        payload = _load_json(Path(args.batch_updates_json))
        batch_rows = payload.get("updates") if isinstance(payload.get("updates"), list) else []
        rows.extend([row for row in batch_rows if isinstance(row, dict)])
    if str(args.task_id).strip():
        rows.append(
            {
                "task_id": str(args.task_id),
                "lifecycle_status": str(args.set_status),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "note": str(args.note or ""),
                "artifact_path": str(args.artifact_path or ""),
                "kpi_receipt_path": str(args.kpi_receipt_path or ""),
                "case_bundle_dir": str(args.case_bundle_dir or ""),
                "case_bundle_zip_path": str(args.case_bundle_zip_path or ""),
                "bundle_id": str(args.bundle_id or ""),
            }
        )
    return rows


def _known_task_ids(execution_manifest: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for bucket in ("ready_tasks", "blocked_tasks"):
        rows = execution_manifest.get(bucket) if isinstance(execution_manifest.get(bucket), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            task_id = str(row.get("task_id", "") or "").strip()
            if task_id:
                ids.add(task_id)
    return ids


def _status_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    return (
        "# External Benchmark Execution Status Update\n\n"
        f"- `status_mode`: `{summary.get('status_mode', '')}`\n"
        f"- `release_surface_status_mode`: `{summary.get('release_surface_status_mode', '')}`\n"
        f"- `release_surface_status_label`: `{summary.get('release_surface_status_label', '')}`\n"
        f"- `release_surface_status_counts`: `not_run={int(summary.get('release_surface_not_run_task_count', 0))} | "
        f"failed={int(summary.get('release_surface_failed_task_count', 0))}`\n"
        f"- `planned_task_count`: `{int(summary.get('planned_task_count', 0))}`\n"
        f"- `in_progress_task_count`: `{int(summary.get('in_progress_task_count', 0))}`\n"
        f"- `completed_task_count`: `{int(summary.get('completed_task_count', 0))}`\n"
        f"- `failed_task_count`: `{int(summary.get('failed_task_count', 0))}`\n"
    )


def _refresh_release_surfaces() -> list[dict[str, Any]]:
    commands = [
        ("committee_review_package", [sys.executable, str(DEFAULT_COMMITTEE_SCRIPT)]),
        ("signed_release_registry", [sys.executable, str(DEFAULT_REGISTRY_SCRIPT)]),
        ("external_validation_submission", [sys.executable, str(DEFAULT_EXTERNAL_SCRIPT)]),
    ]
    results: list[dict[str, Any]] = []
    for label, cmd in commands:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        result = {
            "step": label,
            "command": cmd,
            "returncode": int(proc.returncode),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "contract_pass": proc.returncode == 0,
        }
        results.append(result)
        if proc.returncode != 0:
            raise RuntimeError(
                f"release surface refresh failed at {label}: {proc.stderr.strip() or proc.stdout.strip()}"
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-manifest", default=str(DEFAULT_EXECUTION_MANIFEST))
    parser.add_argument("--updates-json", default=str(DEFAULT_UPDATES_JSON))
    parser.add_argument("--status-manifest-out", default=str(DEFAULT_STATUS_MANIFEST))
    parser.add_argument("--batch-updates-json", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--set-status", choices=sorted(ALLOWED_STATUSES), default="planned")
    parser.add_argument("--note", default="")
    parser.add_argument("--artifact-path", default="")
    parser.add_argument("--kpi-receipt-path", default="")
    parser.add_argument("--case-bundle-dir", default="")
    parser.add_argument("--case-bundle-zip-path", default="")
    parser.add_argument("--bundle-id", default="")
    parser.add_argument("--batch-job-report-out", default="")
    parser.add_argument("--batch-snapshot-root", default="")
    parser.add_argument("--materialize-batch-snapshots", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    execution_manifest_path = Path(args.execution_manifest)
    execution_manifest = _load_json(execution_manifest_path)
    if not execution_manifest:
        raise SystemExit(f"invalid execution manifest: {execution_manifest_path}")

    existing_updates = _load_update_store(Path(args.updates_json))
    incoming_rows = _build_update_rows(args)
    merged_updates = dict(existing_updates)
    merged_updates.update(_normalize_updates(incoming_rows))
    known_task_ids = _known_task_ids(execution_manifest)
    stale_update_task_ids = sorted(task_id for task_id in merged_updates.keys() if task_id not in known_task_ids)
    merged_updates = {task_id: row for task_id, row in merged_updates.items() if task_id in known_task_ids}

    status_manifest = build_execution_status_manifest(
        execution_manifest,
        execution_manifest_path=str(execution_manifest_path),
        updates_path=str(args.updates_json),
        updates_by_task=merged_updates,
    )

    refresh_requested = bool(args.refresh_release_surfaces)
    refresh_guard_status = "not_requested"
    refresh_results: list[dict[str, Any]] = []
    batch_job_report: dict[str, Any] = {}
    batch_job_report_out = Path(str(args.batch_job_report_out).strip()) if str(args.batch_job_report_out).strip() else Path(args.status_manifest_out).with_name(DEFAULT_BATCH_JOB_REPORT.name)
    batch_snapshot_root = Path(str(args.batch_snapshot_root).strip()) if str(args.batch_snapshot_root).strip() else Path(args.status_manifest_out).with_name(DEFAULT_BATCH_SNAPSHOT_ROOT.name)

    if refresh_requested and args.dry_run:
        refresh_guard_status = "dry_run_preview"

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS",
        "dry_run": bool(args.dry_run),
        "summary": status_manifest.get("summary", {}),
        "updated_task_ids": sorted(merged_updates.keys()),
        "dropped_stale_update_task_ids": stale_update_task_ids,
        "updates_json": str(args.updates_json),
        "status_manifest_out": str(args.status_manifest_out),
        "batch_job_report_out": str(batch_job_report_out),
        "batch_snapshot_root": str(batch_snapshot_root),
        "materialize_batch_snapshots": bool(args.materialize_batch_snapshots),
        "batch_job_runner_report": batch_job_report,
        "release_surface_refresh_requested": refresh_requested,
        "release_surface_refresh_guard_status": refresh_guard_status,
        "release_surface_refresh_results": refresh_results,
    }

    if not args.dry_run:
        updates_payload = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updates": list(merged_updates.values()),
        }
        _write_json(Path(args.updates_json), updates_payload)
        _write_json(Path(args.status_manifest_out), status_manifest)
        Path(args.status_manifest_out).with_suffix(".md").write_text(
            _status_markdown(status_manifest),
            encoding="utf-8",
        )
        batch_job_report = build_batch_job_report(
            job_manifest=execution_manifest,
            updates_payload=updates_payload,
            snapshot_root=batch_snapshot_root,
            out=batch_job_report_out,
            materialize_snapshots=bool(args.materialize_batch_snapshots),
        )
        report["batch_job_runner_report"] = batch_job_report
        if refresh_requested:
            try:
                refresh_results = _refresh_release_surfaces()
                refresh_guard_status = "executed"
            except Exception as exc:
                report["contract_pass"] = False
                report["reason_code"] = "ERR_REFRESH_RELEASE_SURFACES"
                report["release_surface_refresh_guard_status"] = "failed"
                report["release_surface_refresh_results"] = refresh_results
                report["refresh_error"] = str(exc)
                print(json.dumps(report, ensure_ascii=False, indent=2))
                raise SystemExit(1)

    report["release_surface_refresh_guard_status"] = refresh_guard_status
    report["release_surface_refresh_results"] = refresh_results
    report["batch_job_runner_report"] = batch_job_report

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
