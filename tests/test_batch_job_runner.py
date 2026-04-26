from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.batch_job_runner import build_batch_job_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_batch_job_runner_tracks_reruns_and_snapshots(tmp_path: Path) -> None:
    artifact_a = tmp_path / "case_a_result.json"
    artifact_b = tmp_path / "case_b_result.json"
    artifact_a.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    artifact_b.write_text(json.dumps({"status": "stale"}), encoding="utf-8")
    job_manifest = {
        "jobs": [
            {
                "job_id": "case-a",
                "phase": "analysis",
                "lifecycle_status": "planned",
                "artifact_paths": [str(artifact_a)],
            },
            {
                "job_id": "case-b",
                "phase": "analysis",
                "lifecycle_status": "completed",
                "artifact_paths": [str(artifact_b)],
                "rerun_count": 1,
            },
        ]
    }
    updates = {
        "updates": [
            {
                "job_id": "case-a",
                "lifecycle_status": "completed",
                "artifact_paths": [str(artifact_a)],
                "note": "analysis complete",
            },
            {
                "job_id": "case-b",
                "request_rerun": True,
                "note": "input changed",
            },
        ]
    }
    out = tmp_path / "batch" / "batch_report.json"
    payload = build_batch_job_report(
        job_manifest=job_manifest,
        updates_payload=updates,
        snapshot_root=tmp_path / "snapshots",
        out=out,
        generated_at="2026-04-19T04:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["job_count"] == 2
    assert payload["summary"]["snapshot_count"] == 1
    assert payload["summary"]["rerun_requested_count"] == 1
    case_a = next(row for row in payload["queue_rows"] if row["job_id"] == "case-a")
    case_b = next(row for row in payload["queue_rows"] if row["job_id"] == "case-b")
    assert case_a["lifecycle_status"] == "completed"
    assert Path(case_a["latest_snapshot"]).exists()
    assert case_b["lifecycle_status"] == "planned_rerun"
    assert case_b["rerun_count"] == 2
    assert case_b["latest_snapshot"] == ""


def test_batch_job_runner_cli_supports_ready_and_blocked_task_manifest(tmp_path: Path) -> None:
    artifact = tmp_path / "task_result.json"
    artifact.write_text(json.dumps({"drift": 0.82}), encoding="utf-8")
    job_manifest = tmp_path / "execution_manifest.json"
    updates = tmp_path / "updates.json"
    out = tmp_path / "runner" / "batch_report.json"
    _write_json(
        job_manifest,
        {
            "ready_tasks": [
                {
                    "task_id": "wind::seed-001",
                    "phase": "component_wind",
                    "benchmark_family": "tpu_raw_hffb_mapping",
                }
            ],
            "blocked_tasks": [
                {
                    "task_id": "review::packet-001",
                    "phase": "review_boundary",
                    "benchmark_family": "audit_packet",
                }
            ],
        },
    )
    _write_json(
        updates,
        {
            "updates": [
                {
                    "task_id": "wind::seed-001",
                    "lifecycle_status": "completed",
                    "artifact_paths": [str(artifact)],
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/batch_job_runner.py",
            "--job-manifest",
            str(job_manifest),
            "--updates-json",
            str(updates),
            "--snapshot-root",
            str(tmp_path / "snapshots"),
            "--out",
            str(out),
            "--generated-at",
            "2026-04-19T05:00:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["job_count"] == 2
    assert payload["summary"]["snapshot_count"] == 1
    assert payload["summary"]["completed_count"] == 1
    assert payload["summary"]["blocked_count"] == 1
    completed = next(row for row in payload["queue_rows"] if row["job_id"] == "wind::seed-001")
    blocked = next(row for row in payload["queue_rows"] if row["job_id"] == "review::packet-001")
    assert completed["lifecycle_status"] == "completed"
    assert Path(completed["latest_snapshot"]).exists()
    assert blocked["lifecycle_status"] == "blocked"
