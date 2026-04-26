#!/usr/bin/env python3
"""Batch job runner scaffold for queue, rerun, and snapshot management."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


REASONS = {
    "PASS": "batch job queue and snapshots updated",
    "ERR_INPUT": "invalid job manifest or updates",
    "ERR_SNAPSHOT": "one or more snapshot artifacts could not be materialized",
}

ALLOWED_STATUSES = {"planned", "planned_rerun", "blocked", "in_progress", "completed", "failed"}


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _sanitize_job_id(job_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(job_id).strip()).strip("._") or "job"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _normalize_artifact_paths(row: dict[str, Any]) -> list[str]:
    if isinstance(row.get("artifact_paths"), list):
        return [str(item).strip() for item in row["artifact_paths"] if str(item).strip()]
    if str(row.get("artifact_path", "")).strip():
        return [str(row.get("artifact_path", "")).strip()]
    return []


def _normalize_job_rows(job_manifest: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(job_manifest, list):
        source_rows = [row for row in job_manifest if isinstance(row, dict)]
    elif isinstance(job_manifest, dict) and isinstance(job_manifest.get("jobs"), list):
        source_rows = [row for row in job_manifest["jobs"] if isinstance(row, dict)]
    else:
        source_rows = []
        if isinstance(job_manifest, dict):
            for bucket, default_status in (("ready_tasks", "planned"), ("blocked_tasks", "blocked")):
                bucket_rows = job_manifest.get(bucket)
                if not isinstance(bucket_rows, list):
                    continue
                for row in bucket_rows:
                    if not isinstance(row, dict):
                        continue
                    normalized = dict(row)
                    normalized.setdefault("lifecycle_status", default_status)
                    source_rows.append(normalized)
    for index, row in enumerate(source_rows, start=1):
        job_id = str(row.get("job_id", row.get("task_id", f"job-{index:04d}"))).strip()
        status = str(row.get("lifecycle_status", row.get("status", row.get("execution_status", "planned")))).strip()
        if status.startswith("ready"):
            status = "planned"
        if status not in ALLOWED_STATUSES:
            status = "planned"
        rows.append(
            {
                "job_id": job_id,
                "phase": str(row.get("phase", "")),
                "benchmark_family": str(row.get("benchmark_family", "")),
                "submission_scope": str(row.get("submission_scope", "")),
                "lifecycle_status": status,
                "input_path": str(row.get("input_path", "")),
                "artifact_paths": _normalize_artifact_paths(row),
                "rerun_count": int(row.get("rerun_count", 0) or 0),
                "note": str(row.get("note", "")),
                "latest_snapshot": str(row.get("latest_snapshot", "")),
            }
        )
    return rows


def _normalize_updates(payload: dict[str, Any] | list[Any] | None) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    elif isinstance(payload, dict):
        if isinstance(payload.get("updates"), list):
            rows = [row for row in payload["updates"] if isinstance(row, dict)]
        elif isinstance(payload.get("jobs"), list):
            rows = [row for row in payload["jobs"] if isinstance(row, dict)]
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        job_id = str(row.get("job_id", row.get("task_id", ""))).strip()
        if not job_id:
            continue
        status = str(row.get("lifecycle_status", row.get("status", ""))).strip()
        if status and status not in ALLOWED_STATUSES:
            status = ""
        out[job_id] = {
            "job_id": job_id,
            "lifecycle_status": status,
            "artifact_paths": _normalize_artifact_paths(row),
            "request_rerun": bool(row.get("request_rerun", False)),
            "note": str(row.get("note", "")),
            "updated_at": str(row.get("updated_at", "") or datetime.now(timezone.utc).isoformat()),
        }
    return out


def _snapshot_manifest(job_row: dict[str, Any], artifact_paths: list[Path], snapshot_root: Path, generated_at: str) -> dict[str, Any]:
    snapshot_dir = snapshot_root / _sanitize_job_id(str(job_row["job_id"]))
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "path": str(path),
            "label": path.name,
            "sha256": _sha256_file(path),
            "bytes": int(path.stat().st_size),
        }
        for path in artifact_paths
    ]
    payload = {
        "schema_version": "1.0",
        "job_id": str(job_row["job_id"]),
        "generated_at": generated_at,
        "snapshot_id": f"{_sanitize_job_id(str(job_row['job_id']))}__snapshot",
        "artifact_rows": entries,
        "summary": {
            "artifact_count": len(entries),
        },
    }
    out = snapshot_dir / "snapshot_manifest.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["path"] = str(out)
    return payload


def build_batch_job_report(
    *,
    job_manifest: dict[str, Any] | list[Any],
    updates_payload: dict[str, Any] | list[Any] | None,
    snapshot_root: Path,
    out: Path,
    materialize_snapshots: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    rows = _normalize_job_rows(job_manifest)
    updates = _normalize_updates(updates_payload)
    snapshot_rows: list[dict[str, Any]] = []
    snapshot_errors: list[dict[str, str]] = []
    rerun_requested_count = 0

    for row in rows:
        update = updates.get(str(row["job_id"]), {})
        if bool(update.get("request_rerun", False)):
            row["rerun_count"] = int(row.get("rerun_count", 0)) + 1
            row["lifecycle_status"] = "planned_rerun"
            rerun_requested_count += 1
        elif str(update.get("lifecycle_status", "")).strip():
            row["lifecycle_status"] = str(update["lifecycle_status"])
        if update.get("artifact_paths"):
            row["artifact_paths"] = list(update["artifact_paths"])
        if str(update.get("note", "")).strip():
            row["note"] = str(update["note"])

        if not materialize_snapshots:
            continue
        if str(row.get("lifecycle_status", "")) not in {"completed", "failed"}:
            continue
        artifact_paths = [Path(path) for path in row.get("artifact_paths", []) if str(path).strip()]
        if not artifact_paths:
            continue
        if any(not path.exists() for path in artifact_paths):
            snapshot_errors.append(
                {
                    "job_id": str(row["job_id"]),
                    "reason": "missing_artifact_path",
                }
            )
            continue
        snapshot_payload = _snapshot_manifest(row, artifact_paths, snapshot_root, timestamp)
        row["latest_snapshot"] = str(snapshot_payload["path"])
        snapshot_rows.append(snapshot_payload)

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("lifecycle_status", "planned"))
        status_counts[status] = int(status_counts.get(status, 0) + 1)

    checks = {
        "queue_rows_present_pass": len(rows) > 0,
        "rerun_requests_tracked_pass": rerun_requested_count == sum(
            1 for update in updates.values() if bool(update.get("request_rerun", False))
        ),
        "snapshot_manifest_written_pass": len(snapshot_errors) == 0,
    }
    reason_code = "PASS"
    if not rows:
        reason_code = "ERR_INPUT"
    elif snapshot_errors:
        reason_code = "ERR_SNAPSHOT"
    contract_pass = bool(reason_code == "PASS" and all(checks.values()))

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-batch-job-runner",
        "generated_at": timestamp,
        "inputs": {
            "snapshot_root": str(snapshot_root),
            "out": str(out),
            "materialize_snapshots": bool(materialize_snapshots),
        },
        "summary": {
            "job_count": len(rows),
            "status_counts": status_counts,
            "snapshot_count": len(snapshot_rows),
            "rerun_requested_count": rerun_requested_count,
            "completed_count": int(status_counts.get("completed", 0)),
            "failed_count": int(status_counts.get("failed", 0)),
            "planned_count": int(status_counts.get("planned", 0) + status_counts.get("planned_rerun", 0)),
            "blocked_count": int(status_counts.get("blocked", 0)),
        },
        "checks": checks,
        "queue_rows": rows,
        "snapshot_rows": snapshot_rows,
        "snapshot_errors": snapshot_errors,
        "summary_line": (
            "Batch job runner: "
            f"{reason_code} | jobs={len(rows)} | snapshots={len(snapshot_rows)} | "
            f"reruns={rerun_requested_count} | statuses={','.join(f'{k}={v}' for k, v in sorted(status_counts.items())) or 'none'}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-manifest", required=True)
    parser.add_argument("--updates-json", default="")
    parser.add_argument("--snapshot-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--materialize-snapshots", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    job_manifest = _load_json(Path(args.job_manifest))
    updates_payload = _load_json(Path(args.updates_json)) if str(args.updates_json).strip() else {}
    payload = build_batch_job_report(
        job_manifest=job_manifest,
        updates_payload=updates_payload,
        snapshot_root=Path(args.snapshot_root),
        out=Path(args.out),
        materialize_snapshots=bool(args.materialize_snapshots),
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
