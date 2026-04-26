from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_multi_project_runtime_writeback_report import (
    build_native_authoring_multi_project_runtime_writeback_report,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_multi_project_runtime_writeback_report.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_native_authoring_multi_project_runtime_writeback_report(tmp_path: Path) -> None:
    out = tmp_path / "native_authoring_multi_project_runtime_writeback_report.json"
    payload = build_native_authoring_multi_project_runtime_writeback_report(
        portfolio_report={
            "family_rows": [
                {
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "family_id": "sample_tower",
                    "family_label": "Sample Tower",
                    "snapshot_count": 2,
                },
                {
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "snapshot_count": 1,
                },
            ]
        },
        runtime_submission_report={
            "family_rows": [
                {
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "family_id": "sample_tower",
                    "submission_ready": True,
                    "runtime_ready": True,
                    "writeback_ready": True,
                    "submission_status": "released",
                    "approval_count": 2,
                    "snapshot_count": 2,
                    "solver_combo_count": 13,
                    "solver_mesh_request_count": 2,
                },
                {
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "family_id": "steel_braced_frame",
                    "submission_ready": True,
                    "runtime_ready": True,
                    "writeback_ready": True,
                    "submission_status": "released",
                    "approval_count": 1,
                    "snapshot_count": 1,
                    "solver_combo_count": 11,
                    "solver_mesh_request_count": 3,
                },
            ]
        },
        runtime_writeback_depth_report={
            "family_rows": [
                {
                    "project_id": "tower-a",
                    "family_id": "sample_tower",
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "package_reproducible": True,
                    "approved_count": 2,
                    "approval_count": 2,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
                {
                    "project_id": "frame-b",
                    "family_id": "steel_braced_frame",
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "package_reproducible": True,
                    "approved_count": 1,
                    "approval_count": 1,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
            ]
        },
        registry_workspace_report={
            "project_rows": [
                {
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "registry_count": 1,
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 2,
                    "latest_approved_count": 2,
                },
                {
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "registry_count": 1,
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 1,
                    "latest_approved_count": 1,
                },
            ]
        },
        out=out,
        generated_at="2026-04-20T00:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["project_family_count"] == 2
    assert payload["summary"]["full_depth_project_family_count"] == 2
    assert payload["summary"]["ready_project_count"] == 2
    assert payload["summary"]["signature_verified_project_count"] == 2
    assert payload["summary"]["package_reproducible_project_count"] == 2
    assert payload["summary"]["snapshot_ready_project_count"] == 2
    assert payload["summary"]["queue_clear_project_count"] == 2
    assert payload["project_rows"][0]["ready"] is True
    assert payload["project_family_rows"][0]["project_family_status"] == "full"
    assert "Native authoring multi-project runtime/writeback: PASS" in payload["summary_line"]

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["summary"]["project_count"] == 2
    assert written["summary"]["ready_project_count"] == 2


def test_generate_native_authoring_multi_project_runtime_writeback_report_cli(tmp_path: Path) -> None:
    portfolio_json = tmp_path / "portfolio.json"
    runtime_json = tmp_path / "runtime.json"
    depth_json = tmp_path / "depth.json"
    workspace_json = tmp_path / "workspace.json"
    out = tmp_path / "out.json"

    _write_json(
        portfolio_json,
        {
            "family_rows": [
                {"project_id": "tower-a", "family_id": "sample_tower", "project_name": "Tower A"},
            ]
        },
    )
    _write_json(
        runtime_json,
        {
            "family_rows": [
                {
                    "project_id": "tower-a",
                    "family_id": "sample_tower",
                    "submission_ready": True,
                    "runtime_ready": True,
                    "writeback_ready": True,
                    "submission_status": "released",
                    "approval_count": 1,
                    "snapshot_count": 1,
                }
            ]
        },
    )
    _write_json(
        depth_json,
        {
            "family_rows": [
                {
                    "project_id": "tower-a",
                    "family_id": "sample_tower",
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "package_reproducible": True,
                    "approval_count": 1,
                    "approved_count": 1,
                    "snapshot_ready": True,
                    "queue_clear": True,
                }
            ]
        },
    )
    _write_json(
        workspace_json,
        {
            "project_rows": [
                {
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "registry_count": 1,
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 1,
                    "latest_approved_count": 1,
                }
            ]
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio_json),
            "--runtime-submission-json",
            str(runtime_json),
            "--runtime-writeback-depth-json",
            str(depth_json),
            "--registry-workspace-json",
            str(workspace_json),
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Native authoring multi-project runtime/writeback: PASS" in completed.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["project_count"] == 1
