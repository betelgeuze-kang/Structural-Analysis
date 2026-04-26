from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


DEFAULT_EXECUTION_MANIFEST = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json"
)
DEFAULT_RUNS_DIR = Path("implementation/phase1/release/external_benchmark_kickoff/runs")
DEFAULT_STATUS_UPDATER = Path("implementation/phase1/update_external_benchmark_execution_status.py")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sanitize_task_id(task_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task_id.strip()).strip("._") or "task"


def _task_lookup(execution_manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    for row in execution_manifest.get("ready_tasks", []):
        if isinstance(row, dict) and str(row.get("task_id", "") or "") == task_id:
            return row
    return {}


def _run_markdown(run_payload: dict[str, Any]) -> str:
    return (
        "# External Benchmark Task Run\n\n"
        f"- `task_id`: `{run_payload.get('task_id', '')}`\n"
        f"- `phase`: `{run_payload.get('phase', '')}`\n"
        f"- `benchmark_family`: `{run_payload.get('benchmark_family', '')}`\n"
        f"- `status`: `{run_payload.get('status', '')}`\n"
        f"- `started_at`: `{run_payload.get('started_at', '')}`\n"
        f"- `input_path`: `{run_payload.get('input_path', '')}`\n"
        f"- `source_origin_class`: `{run_payload.get('source_origin_class', '')}`\n"
        f"- `note`: `{run_payload.get('note', '')}`\n"
    )


def _default_updates_json(execution_manifest_path: Path) -> Path:
    return execution_manifest_path.parent / "external_benchmark_execution_updates.json"


def _default_status_manifest_out(execution_manifest_path: Path) -> Path:
    return execution_manifest_path.parent / "external_benchmark_execution_status_manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-manifest", default=str(DEFAULT_EXECUTION_MANIFEST))
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--updates-json", default="")
    parser.add_argument("--status-manifest-out", default="")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--note", default="benchmark execution started")
    parser.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    execution_manifest_path = Path(args.execution_manifest)
    execution_manifest = _load_json(execution_manifest_path)
    if not execution_manifest:
        raise SystemExit(f"invalid execution manifest: {execution_manifest_path}")
    updates_json = Path(str(args.updates_json).strip() or _default_updates_json(execution_manifest_path))
    status_manifest_out = Path(
        str(args.status_manifest_out).strip() or _default_status_manifest_out(execution_manifest_path)
    )

    task_id = str(args.task_id).strip()
    task = _task_lookup(execution_manifest, task_id)
    if not task:
        report = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_TASK_NOT_FOUND",
            "task_id": task_id,
            "execution_manifest": str(execution_manifest_path),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    now = datetime.now(timezone.utc).isoformat()
    run_dir = Path(args.runs_dir) / _sanitize_task_id(task_id)
    run_json = run_dir / "benchmark_task_run.json"
    run_md = run_dir / "benchmark_task_run.md"
    run_payload = {
        "schema_version": "1.0",
        "generated_at": now,
        "task_id": task_id,
        "phase": str(task.get("phase", "") or ""),
        "benchmark_family": str(task.get("benchmark_family", "") or ""),
        "submission_scope": str(task.get("submission_scope", "") or ""),
        "status": "in_progress",
        "started_at": now,
        "input_path": str(task.get("input_path", "") or ""),
        "source_origin_class": str(task.get("source_origin_class", "") or ""),
        "holdout_split": str(task.get("holdout_split", "") or ""),
        "execution_manifest": str(execution_manifest_path),
        "note": str(args.note or ""),
        "task": task,
    }

    updater_cmd = [
        sys.executable,
        str(DEFAULT_STATUS_UPDATER),
        "--execution-manifest",
        str(execution_manifest_path),
        "--updates-json",
        str(updates_json),
        "--status-manifest-out",
        str(status_manifest_out),
        "--task-id",
        task_id,
        "--set-status",
        "in_progress",
        "--note",
        str(args.note or ""),
        "--artifact-path",
        str(run_json),
    ]
    if args.refresh_release_surfaces:
        updater_cmd.append("--refresh-release-surfaces")
    if args.dry_run:
        updater_cmd.append("--dry-run")

    if not args.dry_run:
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_json, run_payload)
        run_md.write_text(_run_markdown(run_payload), encoding="utf-8")

    proc = subprocess.run(updater_cmd, check=False, capture_output=True, text=True)
    update_report = {}
    try:
        update_report = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        update_report = {}

    contract_pass = proc.returncode == 0 and bool(update_report.get("contract_pass", False) or args.dry_run)
    reason_code = str(update_report.get("reason_code", "PASS") if contract_pass else "ERR_STATUS_UPDATE_FAILED")

    report = {
        "schema_version": "1.0",
        "generated_at": now,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "dry_run": bool(args.dry_run),
        "task_id": task_id,
        "run_dir": str(run_dir),
        "run_json": str(run_json),
        "run_md": str(run_md),
        "updates_json": str(updates_json),
        "status_manifest_out": str(status_manifest_out),
        "refresh_release_surfaces": bool(args.refresh_release_surfaces),
        "updater_command": updater_cmd,
        "update_report": update_report,
    }
    if proc.returncode != 0:
        report["status_update_stderr"] = proc.stderr.strip()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
