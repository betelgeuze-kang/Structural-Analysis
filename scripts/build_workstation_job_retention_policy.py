#!/usr/bin/env python3
"""Build a local retention policy manifest for workstation delivery job folders."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "workstation-job-retention-policy.v1"
DEFAULT_OUT = Path("implementation/phase1/workstation_job_retention_policy.json")
DEFAULT_JOB_ROOT = Path("implementation/phase1/workstation_jobs")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _job_rows(job_root: Path) -> list[dict[str, Any]]:
    rows = []
    if not job_root.exists():
        return rows
    for job_dir in sorted(path for path in job_root.iterdir() if path.is_dir()):
        checksums = job_dir / "checksums.sha256"
        rows.append(
            {
                "job_id": job_dir.name,
                "path": str(job_dir),
                "input_manifest": str(job_dir / "input_manifest.json"),
                "run_log": str(job_dir / "run_log.jsonl"),
                "output_manifest": str(job_dir / "output_manifest.json"),
                "checksums": str(checksums),
                "checksums_available": checksums.exists(),
                "checksums_sha256": _sha256_path(checksums) if checksums.exists() else "",
            }
        )
    return rows


def _parse_job_timestamp(job_id: str) -> datetime | None:
    token = job_id.split("-", 1)[0]
    try:
        return datetime.strptime(token, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _cleanup_preview(
    *,
    rows: list[dict[str, Any]],
    latest_job_id: str,
    generated_at: datetime,
    retention_days: int,
    max_completed_jobs: int,
) -> dict[str, Any]:
    sortable_rows = []
    for row in rows:
        job_id = str(row.get("job_id", ""))
        timestamp = _parse_job_timestamp(job_id)
        age_days = (generated_at - timestamp).days if timestamp else None
        sortable_rows.append(
            {
                **row,
                "parsed_timestamp": timestamp.isoformat() if timestamp else "",
                "age_days": age_days,
                "is_latest": job_id == latest_job_id,
            }
        )

    by_newest = sorted(
        sortable_rows,
        key=lambda row: row["parsed_timestamp"] or row["job_id"],
        reverse=True,
    )
    retained_by_count = {str(row["job_id"]) for row in by_newest[:max(max_completed_jobs, 0)]}
    candidates = []
    retained_count = 0
    for row in by_newest:
        job_id = str(row["job_id"])
        reasons = []
        if row["is_latest"]:
            retained_count += 1
            continue
        if row["age_days"] is not None and row["age_days"] > retention_days:
            reasons.append("older_than_retention_days")
        if job_id not in retained_by_count:
            reasons.append("exceeds_max_completed_jobs")
        if reasons:
            candidates.append(
                {
                    "job_id": job_id,
                    "path": row["path"],
                    "age_days": row["age_days"],
                    "reasons": reasons,
                    "action": "would_delete_if_explicitly_confirmed",
                }
            )
        else:
            retained_count += 1

    return {
        "mode": "dry_run_only",
        "delete_operation_executed": False,
        "requires_explicit_confirmation": True,
        "candidate_count": len(candidates),
        "retained_count": retained_count,
        "candidate_rows": candidates,
    }


def build_workstation_job_retention_policy(
    *,
    job_root: Path = DEFAULT_JOB_ROOT,
    retention_days: int = 365,
    max_completed_jobs: int = 200,
) -> dict[str, Any]:
    generated_at_dt = datetime.now(timezone.utc)
    rows = _job_rows(job_root)
    latest_path = job_root / "latest_job_id.txt"
    latest_job_id = latest_path.read_text(encoding="utf-8").strip() if latest_path.exists() else ""
    latest_dir = job_root / latest_job_id if latest_job_id else None
    blockers = [
        *(["job_root_missing"] if not job_root.exists() else []),
        *(["latest_job_id_missing"] if job_root.exists() and not latest_job_id else []),
        *(["latest_job_dir_missing"] if latest_dir and not latest_dir.exists() else []),
        *(["retention_days_below_minimum"] if retention_days < 30 else []),
        *(["max_completed_jobs_below_minimum"] if max_completed_jobs < 1 else []),
        *(["job_checksum_manifest_missing"] if any(not row["checksums_available"] for row in rows) else []),
    ]
    contract_pass = not blockers
    cleanup_preview = _cleanup_preview(
        rows=rows,
        latest_job_id=latest_job_id,
        generated_at=generated_at_dt,
        retention_days=retention_days,
        max_completed_jobs=max_completed_jobs,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at_dt.isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_WORKSTATION_JOB_RETENTION_POLICY_BLOCKED",
        "summary_line": (
            f"Workstation job retention policy: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"jobs={len(rows)} | retention_days={retention_days} | max_jobs={max_completed_jobs}"
        ),
        "job_root": str(job_root),
        "latest_job_id": latest_job_id,
        "policy": {
            "retention_days": retention_days,
            "max_completed_jobs": max_completed_jobs,
            "delete_requires_explicit_confirmation": True,
            "cleanup_dry_run_required": True,
            "keep_latest_job": True,
            "keep_delivered_package_manifests": True,
        },
        "cleanup_policy": {
            "automatic_delete_enabled": False,
            "manual_cleanup_gate": "External-State confirmation required before deleting job folders.",
            "dry_run_command": "python3 scripts/build_workstation_job_retention_policy.py --json",
        },
        "cleanup_preview": cleanup_preview,
        "job_rows": rows,
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-root", type=Path, default=DEFAULT_JOB_ROOT)
    parser.add_argument("--retention-days", type=int, default=365)
    parser.add_argument("--max-completed-jobs", type=int, default=200)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_workstation_job_retention_policy(
        job_root=args.job_root,
        retention_days=args.retention_days,
        max_completed_jobs=args.max_completed_jobs,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
