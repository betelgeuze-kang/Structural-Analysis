from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = "implementation/phase1/run_external_benchmark_refresh_lane.py"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _manifest() -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-03-22T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS_EXECUTION_MANIFEST_READY",
        "summary": {
            "execution_mode": "limited",
            "review_boundary_pending_count": 0,
        },
        "ready_tasks": [
            {"task_id": "wind::seed_a", "phase": "component_wind"},
            {"task_id": "hinge::seed_b", "phase": "component_hinge"},
        ],
        "blocked_tasks": [],
    }


def _updates(*, second_status: str = "completed", missing_kpi: bool = False, missing_bundle: bool = False) -> dict:
    rows = [
        {
            "task_id": "wind::seed_a",
            "lifecycle_status": "completed",
            "updated_at": "2026-03-22T00:01:00+00:00",
            "kpi_receipt_path": "runs/wind/kpi.json",
            "case_bundle_zip_path": "runs/wind/bundle.zip",
        },
        {
            "task_id": "hinge::seed_b",
            "lifecycle_status": second_status,
            "updated_at": "2026-03-22T00:02:00+00:00",
            "kpi_receipt_path": "" if missing_kpi else "runs/hinge/kpi.json",
            "case_bundle_zip_path": "" if missing_bundle else "runs/hinge/bundle.zip",
        },
    ]
    return {"schema_version": "1.0", "updates": rows}


def _run(tmp_path: Path, updates: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    manifest = _write_json(tmp_path / "external_benchmark_execution_manifest.json", _manifest())
    updates_json = _write_json(tmp_path / "external_benchmark_execution_updates.json", updates)
    status_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    report_out = tmp_path / "external_benchmark_refresh_lane_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            SCRIPT,
            "--execution-manifest",
            str(manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_out),
            "--report-out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    report = json.loads(report_out.read_text(encoding="utf-8"))
    return proc, report


def test_external_benchmark_refresh_lane_passes_complete_status(tmp_path: Path) -> None:
    proc, report = _run(tmp_path, _updates())

    assert proc.returncode == 0, proc.stderr
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS_EXTERNAL_BENCHMARK_REFRESH_LANE"
    assert report["blockers"] == []
    summary = report["summary"]
    assert summary["status_mode"] == "execution_complete_no_fail"
    assert summary["release_surface_status_mode"] == "execution_complete_no_fail"
    assert summary["completed_task_count"] == 2
    assert summary["planned_task_count"] == 0
    assert summary["in_progress_task_count"] == 0
    assert summary["failed_task_count"] == 0
    assert summary["kpi_receipt_task_count"] == 2
    assert summary["case_bundle_zip_task_count"] == 2
    assert (tmp_path / "external_benchmark_execution_status_manifest.md").exists()


def test_external_benchmark_refresh_lane_blocks_incomplete_statuses(tmp_path: Path) -> None:
    for status, expected in [
        ("planned", "planned_task_count_nonzero:1"),
        ("in_progress", "in_progress_task_count_nonzero:1"),
        ("failed", "failed_task_count_nonzero:1"),
    ]:
        proc, report = _run(tmp_path / status, _updates(second_status=status))
        assert proc.returncode == 3
        assert report["contract_pass"] is False
        assert expected in report["blockers"]


def test_external_benchmark_refresh_lane_blocks_missing_receipts_or_bundles(tmp_path: Path) -> None:
    proc, report = _run(tmp_path / "kpi", _updates(missing_kpi=True))
    assert proc.returncode == 3
    assert "kpi_receipt_task_count_below_executable:1/2" in report["blockers"]

    proc, report = _run(tmp_path / "bundle", _updates(missing_bundle=True))
    assert proc.returncode == 3
    assert "case_bundle_zip_task_count_below_executable:1/2" in report["blockers"]
