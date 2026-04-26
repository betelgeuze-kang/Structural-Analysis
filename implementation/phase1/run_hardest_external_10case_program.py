#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_KICKOFF_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")
DEFAULT_EXECUTION_MANIFEST = DEFAULT_KICKOFF_DIR / "external_benchmark_execution_manifest.json"
DEFAULT_STATUS_MANIFEST = DEFAULT_KICKOFF_DIR / "external_benchmark_execution_status_manifest.json"
DEFAULT_UPDATES_JSON = DEFAULT_KICKOFF_DIR / "external_benchmark_execution_updates.json"
DEFAULT_RUNS_DIR = DEFAULT_KICKOFF_DIR / "runs"
DEFAULT_OUT = DEFAULT_KICKOFF_DIR / "hardest_external_10case_program_report.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd: list[str]) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    except Exception:
        payload = {}
    return proc.returncode, payload, proc.stdout.strip(), proc.stderr.strip()


def _ready_hardest_task_ids(execution_manifest: dict[str, Any]) -> list[str]:
    rows = execution_manifest.get("ready_tasks") if isinstance(execution_manifest.get("ready_tasks"), list) else []
    return [
        str(row.get("task_id", "") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("phase", "") or "") == "hardest_case"
    ]


def _task_row_map(status_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = status_manifest.get("tasks") if isinstance(status_manifest.get("tasks"), list) else []
    return {
        str(row.get("task_id", "") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("task_id", "") or "").strip()
    }


def _build_live_ready_template(kickoff_dir: Path) -> str:
    preview_path = kickoff_dir / "audit_review_decision_batch_approve_all.preview.json"
    example_path = kickoff_dir / "audit_review_decision_batch_approve_all.attested_example.json"
    out_path = kickoff_dir / "audit_review_decision_batch_approve_all.live_ready_template.json"
    preview_payload = _load_json(preview_path)
    example_payload = _load_json(example_path)
    template_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS_TEMPLATE_READY",
        "reason": "ready-to-fill live apply template generated from approve-all preview",
        "template_mode": "approve_all_live_ready",
        "attestation": dict(example_payload.get("attestation", {}))
        if isinstance(example_payload.get("attestation"), dict)
        else {},
        "updates": list(preview_payload.get("updates", []))
        if isinstance(preview_payload.get("updates"), list)
        else [],
    }
    _write_json(out_path, template_payload)
    return str(out_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kickoff-dir", default=str(DEFAULT_KICKOFF_DIR))
    parser.add_argument(
        "--hardest-external-10case-kickoff-report",
        default="implementation/phase1/hardest_external_10case_kickoff_gate_report.json",
    )
    parser.add_argument(
        "--audit-review-queue-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json",
    )
    parser.add_argument(
        "--audit-review-assignment-manifest",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_owner_assignments.json",
    )
    parser.add_argument("--approve-all-preview", default="")
    parser.add_argument("--reject-one-preview", default="")
    parser.add_argument("--decision-runner-report", default="")
    parser.add_argument("--execution-manifest", default=str(DEFAULT_EXECUTION_MANIFEST))
    parser.add_argument("--status-manifest-out", default=str(DEFAULT_STATUS_MANIFEST))
    parser.add_argument("--updates-json", default=str(DEFAULT_UPDATES_JSON))
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    kickoff_dir = Path(args.kickoff_dir)
    execution_manifest_path = Path(args.execution_manifest)
    status_manifest_out = Path(args.status_manifest_out)
    updates_json = Path(args.updates_json)
    runs_dir = Path(args.runs_dir)

    steps: list[dict[str, Any]] = []
    cmd_manifest = [
        sys.executable,
        "implementation/phase1/generate_external_benchmark_execution_manifest.py",
        "--out-dir",
        str(kickoff_dir),
        "--hardest-external-10case-kickoff-report",
        str(args.hardest_external_10case_kickoff_report),
        "--audit-review-queue-manifest",
        str(args.audit_review_queue_manifest),
        "--audit-review-assignment-manifest",
        str(args.audit_review_assignment_manifest),
    ]
    if str(args.approve_all_preview).strip():
        cmd_manifest.extend(["--approve-all-preview", str(args.approve_all_preview)])
    if str(args.reject_one_preview).strip():
        cmd_manifest.extend(["--reject-one-preview", str(args.reject_one_preview)])
    if str(args.decision_runner_report).strip():
        cmd_manifest.extend(["--decision-runner-report", str(args.decision_runner_report)])
    rc, payload, stdout, stderr = _run(cmd_manifest)
    steps.append(
        {
            "step": "generate_execution_manifest",
            "command": cmd_manifest,
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
            "report": payload,
        }
    )
    if rc != 0:
        report = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_MANIFEST_GENERATION_FAILED",
            "steps": steps,
        }
        _write_json(Path(args.out), report)
        raise SystemExit(1)

    execution_manifest = _load_json(execution_manifest_path)
    task_ids = _ready_hardest_task_ids(execution_manifest)
    for task_id in task_ids:
        start_cmd = [
            sys.executable,
            "implementation/phase1/start_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest_path),
            "--runs-dir",
            str(runs_dir),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--task-id",
            task_id,
            "--note",
            "hardest external 10-case kickoff",
        ]
        if args.dry_run:
            start_cmd.append("--dry-run")
        rc, payload, stdout, stderr = _run(start_cmd)
        steps.append(
            {
                "step": f"start::{task_id}",
                "command": start_cmd,
                "returncode": rc,
                "stdout": stdout,
                "stderr": stderr,
                "report": payload,
            }
        )
        if rc != 0:
            break

        exec_cmd = [
            sys.executable,
            "implementation/phase1/execute_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest_path),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--runs-dir",
            str(runs_dir),
            "--task-id",
            task_id,
        ]
        if args.dry_run:
            exec_cmd.append("--dry-run")
        rc, payload, stdout, stderr = _run(exec_cmd)
        steps.append(
            {
                "step": f"execute::{task_id}",
                "command": exec_cmd,
                "returncode": rc,
                "stdout": stdout,
                "stderr": stderr,
                "report": payload,
            }
        )
        if rc != 0:
            break

    refresh_cmd = [
        sys.executable,
        "implementation/phase1/update_external_benchmark_execution_status.py",
        "--execution-manifest",
        str(execution_manifest_path),
        "--updates-json",
        str(updates_json),
        "--status-manifest-out",
        str(status_manifest_out),
    ]
    if args.refresh_release_surfaces:
        refresh_cmd.append("--refresh-release-surfaces")
    if args.dry_run:
        refresh_cmd.append("--dry-run")
    rc, payload, stdout, stderr = _run(refresh_cmd)
    steps.append(
        {
            "step": "refresh_status_and_release_surfaces",
            "command": refresh_cmd,
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
            "report": payload,
        }
    )

    status_manifest = _load_json(status_manifest_out)
    task_rows = _task_row_map(status_manifest)
    completed_rows = [
        row for task_id, row in task_rows.items()
        if task_id.startswith("hardest::") and str(row.get("lifecycle_status", "") or "") == "completed"
    ]
    receipt_count = sum(1 for row in completed_rows if str(row.get("kpi_receipt_path", "") or "").strip())
    bundle_count = sum(1 for row in completed_rows if str(row.get("case_bundle_zip_path", "") or "").strip())
    live_ready_template_path = _build_live_ready_template(kickoff_dir)
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": rc == 0,
        "reason_code": "PASS" if rc == 0 else "ERR_HARDEST_10CASE_PROGRAM",
        "summary": {
            "task_count": len(task_ids),
            "completed_case_count": len(completed_rows),
            "kpi_receipt_count": receipt_count,
            "signed_bundle_count": bundle_count,
            "review_pending_count": int(
                status_manifest.get("summary", {}).get("review_boundary_pending_count", 0) or 0
            ),
            "full_submission_ready": bool(
                execution_manifest.get("summary", {}).get("full_submission_ready", False)
            ),
        },
        "execution_manifest": str(execution_manifest_path),
        "status_manifest": str(status_manifest_out),
        "updates_json": str(updates_json),
        "live_ready_template_json": live_ready_template_path,
        "steps": steps,
        "completed_cases": [
            {
                "task_id": str(row.get("task_id", "") or ""),
                "artifact_path": str(row.get("artifact_path", "") or ""),
                "kpi_receipt_path": str(row.get("kpi_receipt_path", "") or ""),
                "case_bundle_zip_path": str(row.get("case_bundle_zip_path", "") or ""),
                "bundle_id": str(row.get("bundle_id", "") or ""),
            }
            for row in completed_rows
        ],
    }
    _write_json(Path(args.out), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
