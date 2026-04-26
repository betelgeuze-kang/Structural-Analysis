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
            "ready_task_count": 1,
            "blocked_task_count": 0,
            "review_boundary_pending_count": 0,
        },
        "ready_tasks": [
            {
                "task_id": "wind::seed_a",
                "phase": "component_wind",
                "benchmark_family": "tpu_raw_hffb_mapping",
                "submission_scope": "limited_external_benchmark",
                "execution_status": "ready",
                "input_path": "wind_a.json",
                "source_origin_class": "official_external_benchmark",
                "holdout_split": "val",
            }
        ],
        "blocked_tasks": [],
    }


def test_start_external_benchmark_task_dry_run(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    runs_dir = tmp_path / "runs"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    status_manifest_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/start_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--runs-dir",
            str(runs_dir),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--task-id",
            "wind::seed_a",
            "--refresh-release-surfaces",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["contract_pass"] is True
    assert report["task_id"] == "wind::seed_a"
    assert report["update_report"]["release_surface_refresh_guard_status"] == "dry_run_preview"
    assert not runs_dir.exists()
    assert not updates_json.exists()
    assert not status_manifest_out.exists()


def test_start_external_benchmark_task_writes_run_artifact(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    runs_dir = tmp_path / "runs"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    status_manifest_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/start_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--runs-dir",
            str(runs_dir),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--task-id",
            "wind::seed_a",
            "--note",
            "kickoff",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    run_json = Path(report["run_json"])
    run_md = Path(report["run_md"])
    assert run_json.exists()
    assert run_md.exists()
    payload = json.loads(run_json.read_text(encoding="utf-8"))
    assert payload["status"] == "in_progress"
    assert payload["task_id"] == "wind::seed_a"
    assert payload["note"] == "kickoff"
    assert updates_json.exists()
    assert status_manifest_out.exists()
    assert report["update_report"]["summary"]["in_progress_task_count"] == 1


def test_start_external_benchmark_task_missing_task_fails(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    _write_json(execution_manifest, _execution_manifest_payload())

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/start_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--task-id",
            "missing::task",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    report = json.loads(proc.stdout)
    assert report["reason_code"] == "ERR_TASK_NOT_FOUND"
