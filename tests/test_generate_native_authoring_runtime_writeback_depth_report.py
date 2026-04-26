from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_runtime_writeback_depth_report import (
    build_native_authoring_runtime_writeback_depth_report,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_runtime_writeback_depth_report.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_native_authoring_runtime_writeback_depth_report_surfaces_project_depth(
    tmp_path: Path,
) -> None:
    out = tmp_path / "release" / "authoring" / "portfolio" / "native_authoring_runtime_writeback_depth_report.json"
    payload = build_native_authoring_runtime_writeback_depth_report(
        portfolio_report={
            "family_rows": [
                {"family_id": "sample_tower", "project_id": "tower-a", "project_name": "Tower A"},
                {
                    "family_id": "steel_braced_frame",
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                },
            ]
        },
        runtime_submission_report={
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "approval_count": 2,
                    "snapshot_count": 3,
                    "submission_status": "released",
                },
                {
                    "family_id": "steel_braced_frame",
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "approval_count": 1,
                    "snapshot_count": 1,
                    "submission_status": "released",
                },
            ]
        },
        registry_index_report={
            "project_rows": [
                {
                    "project_id": "tower-a",
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 2,
                    "latest_approved_count": 2,
                    "registry_count": 1,
                },
                {
                    "project_id": "frame-b",
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 1,
                    "latest_approved_count": 1,
                    "registry_count": 1,
                },
            ]
        },
        out=out,
        generated_at="2026-04-20T13:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["depth_ready_family_count"] == 2
    assert payload["summary"]["signature_verified_family_count"] == 2
    assert payload["summary"]["package_reproducible_family_count"] == 2
    assert payload["summary"]["queue_clear_family_count"] == 2
    assert payload["family_rows"][0]["runtime_writeback_depth_status"] == "full"
    assert "Native authoring runtime writeback depth: PASS" in payload["summary_line"]


def test_generate_native_authoring_runtime_writeback_depth_report_cli(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    runtime_submission = tmp_path / "runtime_submission.json"
    registry_index = tmp_path / "registry_index.json"
    out = tmp_path / "native_authoring_runtime_writeback_depth_report.json"

    _write_json(
        portfolio,
        {"family_rows": [{"family_id": "composite_podium", "project_id": "podium-c"}]},
    )
    _write_json(
        runtime_submission,
        {
            "family_rows": [
                {
                    "family_id": "composite_podium",
                    "project_id": "podium-c",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "approval_count": 2,
                    "snapshot_count": 2,
                    "submission_status": "released",
                }
            ]
        },
    )
    _write_json(
        registry_index,
        {
            "project_rows": [
                {
                    "project_id": "podium-c",
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 2,
                    "latest_approved_count": 2,
                    "registry_count": 1,
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio),
            "--runtime-submission-json",
            str(runtime_submission),
            "--registry-index-json",
            str(registry_index),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["depth_ready_family_count"] == 1
    assert payload["family_rows"][0]["family_id"] == "composite_podium"
    assert "Native authoring runtime writeback depth: PASS" in proc.stdout
