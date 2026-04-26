from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _execution_manifest_payload() -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-03-22T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS_EXECUTION_MANIFEST_READY",
        "summary": {
            "execution_mode": "limited",
            "ready_task_count": 2,
            "blocked_task_count": 1,
            "review_boundary_pending_count": 1,
            "review_boundary_assignee_label": "Kim Structural=1",
            "review_boundary_assignment_status_label": "assigned=1",
        },
        "ready_tasks": [
            {
                "task_id": "wind::seed_a",
                "phase": "component_wind",
                "benchmark_family": "tpu_raw_hffb_mapping",
                "submission_scope": "limited_external_benchmark",
                "execution_status": "ready",
                "input_path": "wind_a.json",
            },
            {
                "task_id": "hinge::seed_b",
                "phase": "component_hinge",
                "benchmark_family": "peer_spd_column_hinge",
                "submission_scope": "limited_external_benchmark",
                "execution_status": "ready",
                "input_path": "hinge_b.json",
            },
        ],
        "blocked_tasks": [
            {
                "task_id": "review::packet_x",
                "phase": "review_boundary",
                "benchmark_family": "connection_detailing",
                "submission_scope": "final_external_submission_only",
                "execution_status": "blocked",
                "input_path": "packet_x",
                "blocker_reason": "pending_review_boundary",
                "assignee_name": "Kim Structural",
                "assignment_status": "assigned",
            }
        ],
    }


def test_generate_external_benchmark_execution_status_manifest(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())
    _write_json(
        updates_json,
        {
            "updates": [
                {"task_id": "wind::seed_a", "lifecycle_status": "completed", "updated_at": "2026-03-22T00:01:00+00:00"},
                {"task_id": "hinge::seed_b", "lifecycle_status": "in_progress", "updated_at": "2026-03-22T00:02:00+00:00"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_execution_status_manifest.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["execution_mode"] == "limited"
    assert summary["status_mode"] == "execution_in_progress"
    assert summary["release_surface_status_mode"] == "execution_in_progress"
    assert summary["release_surface_status_label"] == "execution in progress"
    assert summary["planned_task_count"] == 0
    assert summary["in_progress_task_count"] == 1
    assert summary["completed_task_count"] == 1
    assert summary["failed_task_count"] == 0
    assert summary["release_surface_not_run_task_count"] == 0
    assert summary["release_surface_failed_task_count"] == 0
    assert summary["blocked_task_count"] == 1
    assert summary["review_boundary_pending_count"] == 1
    assert summary["review_boundary_assignee_label"] == "Kim Structural=1"
    assert summary["review_boundary_assignment_status_label"] == "assigned=1"
    assert any(row["task_id"] == "wind::seed_a" and row["lifecycle_status"] == "completed" for row in payload["tasks"])
    md_text = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "release_surface_status_mode" in md_text
    assert "release_surface_status_counts" in md_text


def test_generate_external_benchmark_execution_status_manifest_reports_not_run_this_snapshot(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())
    _write_json(updates_json, {"updates": []})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_execution_status_manifest.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["status_mode"] == "planned_only"
    assert summary["release_surface_status_mode"] == "not_run_this_snapshot"
    assert summary["release_surface_status_label"] == "not run this snapshot"
    assert summary["planned_task_count"] == 2
    assert summary["release_surface_not_run_task_count"] == 2
    assert summary["release_surface_failed_task_count"] == 0
    md_text = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "not run this snapshot" in md_text
    assert "release_surface_status_counts" in md_text


def test_update_external_benchmark_execution_status_writes_updates_and_manifest(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_external_benchmark_execution_status.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(out),
            "--task-id",
            "wind::seed_a",
            "--set-status",
            "completed",
            "--note",
            "wind seed complete",
            "--artifact-path",
            "logs/wind_seed_a.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    updates_payload = json.loads(updates_json.read_text(encoding="utf-8"))
    assert updates_payload["updates"][0]["task_id"] == "wind::seed_a"
    status_payload = json.loads(out.read_text(encoding="utf-8"))
    summary = status_payload["summary"]
    assert summary["completed_task_count"] == 1
    assert summary["planned_task_count"] == 1
    assert summary["blocked_task_count"] == 1
    assert summary["status_mode"] == "execution_in_progress"
    assert summary["release_surface_status_mode"] == "execution_in_progress"
    assert summary["release_surface_status_label"] == "execution in progress"
    assert summary["release_surface_not_run_task_count"] == 1
    assert summary["release_surface_failed_task_count"] == 0
    wind_task = next(row for row in status_payload["tasks"] if row["task_id"] == "wind::seed_a")
    assert wind_task["artifact_path"] == "logs/wind_seed_a.json"
    batch_report = out.with_name("external_benchmark_batch_job_report.json")
    assert batch_report.exists()
    batch_payload = json.loads(batch_report.read_text(encoding="utf-8"))
    assert batch_payload["contract_pass"] is True
    assert batch_payload["summary"]["job_count"] == 3
    assert batch_payload["summary"]["completed_count"] == 1
    stdout_report = json.loads(proc.stdout)
    assert stdout_report["batch_job_report_out"] == str(batch_report)
    assert stdout_report["batch_job_runner_report"]["contract_pass"] is True
    md_text = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "release_surface_status_mode" in md_text
    assert "release_surface_status_counts" in md_text


def test_update_external_benchmark_execution_status_refresh_release_surfaces_dry_run(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_external_benchmark_execution_status.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(out),
            "--task-id",
            "wind::seed_a",
            "--set-status",
            "in_progress",
            "--refresh-release-surfaces",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["release_surface_refresh_requested"] is True
    assert report["release_surface_refresh_guard_status"] == "dry_run_preview"
    assert report["release_surface_refresh_results"] == []
    assert report["dropped_stale_update_task_ids"] == []
    assert report["batch_job_runner_report"] == {}
    assert not updates_json.exists()
    assert not out.exists()
    assert not out.with_name("external_benchmark_batch_job_report.json").exists()


def test_update_external_benchmark_execution_status_prunes_stale_updates(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())
    _write_json(
        updates_json,
        {
            "updates": [
                {"task_id": "stale::task", "lifecycle_status": "completed", "updated_at": "2026-03-22T00:01:00+00:00"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_external_benchmark_execution_status.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(out),
            "--task-id",
            "wind::seed_a",
            "--set-status",
            "completed",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["dropped_stale_update_task_ids"] == ["stale::task"]
    stored = json.loads(updates_json.read_text(encoding="utf-8"))
    assert [row["task_id"] for row in stored["updates"]] == ["wind::seed_a"]


def test_generate_external_benchmark_execution_status_manifest_reports_execution_complete_no_fail(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())
    _write_json(
        updates_json,
        {
            "updates": [
                {"task_id": "wind::seed_a", "lifecycle_status": "completed", "updated_at": "2026-03-22T00:01:00+00:00"},
                {"task_id": "hinge::seed_b", "lifecycle_status": "completed", "updated_at": "2026-03-22T00:02:00+00:00"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_execution_status_manifest.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["status_mode"] == "execution_complete_no_fail"
    assert summary["release_surface_status_mode"] == "execution_complete_no_fail"
    assert summary["release_surface_status_label"] == "execution complete no fail"
    assert summary["completed_task_count"] == 2
    assert summary["in_progress_task_count"] == 0
    assert summary["failed_task_count"] == 0
    assert summary["planned_task_count"] == 0
    assert summary["release_surface_not_run_task_count"] == 0
    assert summary["release_surface_failed_task_count"] == 0
    assert summary["completion_ratio"] == 1.0
    md_text = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "execution complete no fail" in md_text
    assert "release_surface_status_counts" in md_text


def test_generate_external_benchmark_execution_status_manifest_reports_failed_this_snapshot(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())
    _write_json(
        updates_json,
        {
            "updates": [
                {"task_id": "wind::seed_a", "lifecycle_status": "failed", "updated_at": "2026-03-22T00:01:00+00:00"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_execution_status_manifest.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["status_mode"] == "execution_failure_present"
    assert summary["release_surface_status_mode"] == "failed_this_snapshot"
    assert summary["release_surface_status_label"] == "failed this snapshot"
    assert summary["failed_task_count"] == 1
    assert summary["planned_task_count"] == 1
    assert summary["release_surface_not_run_task_count"] == 1
    assert summary["release_surface_failed_task_count"] == 1
    md_text = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "failed this snapshot" in md_text
    assert "release_surface_status_counts" in md_text


def test_update_external_benchmark_execution_status_prunes_stale_running_updates(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())
    _write_json(
        updates_json,
        {
            "updates": [
                {"task_id": "stale::task", "lifecycle_status": "in_progress", "updated_at": "2026-03-22T00:01:00+00:00"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_external_benchmark_execution_status.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(out),
            "--task-id",
            "wind::seed_a",
            "--set-status",
            "completed",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["dropped_stale_update_task_ids"] == ["stale::task"]
    stored = json.loads(updates_json.read_text(encoding="utf-8"))
    assert [row["task_id"] for row in stored["updates"]] == ["wind::seed_a"]
    assert stored["updates"][0]["lifecycle_status"] == "completed"
    status_payload = json.loads(out.read_text(encoding="utf-8"))
    assert status_payload["summary"]["completed_task_count"] == 1
    assert status_payload["summary"]["status_mode"] == "execution_in_progress"
