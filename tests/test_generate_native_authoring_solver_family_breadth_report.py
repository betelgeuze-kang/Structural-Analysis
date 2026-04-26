from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_solver_family_breadth_report import (
    build_native_authoring_solver_family_breadth_report,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_solver_family_breadth_report.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_native_authoring_solver_family_breadth_report_surfaces_family_coverage(tmp_path: Path) -> None:
    out = tmp_path / "release" / "authoring" / "portfolio" / "native_authoring_solver_family_breadth_report.json"
    payload = build_native_authoring_solver_family_breadth_report(
        portfolio_report={
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "family_label": "Sample Tower",
                    "palette_family_count": 4,
                    "active_family_count": 2,
                    "member_type_count": 2,
                    "solver_ready": True,
                    "signature_verified": True,
                },
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "palette_family_count": 4,
                    "active_family_count": 1,
                    "member_type_count": 3,
                    "solver_ready": True,
                    "signature_verified": True,
                },
            ]
        },
        family_tracks_report={
            "track_rows": [
                {"family_id": "sample_tower", "release_ready": True, "solver_ready": True},
                {"family_id": "steel_braced_frame", "release_ready": True, "solver_ready": True},
            ]
        },
        runtime_submission_report={
            "summary": {"family_count": 2, "queued_submission_count": 0},
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "family_label": "Sample Tower",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "signature_verified": True,
                    "solver_combo_count": 13,
                    "solver_combo_status": "broad",
                    "solver_mesh_request_count": 2,
                    "solver_mesh_cell_count": 588,
                    "mesh_breadth_status": "broad",
                    "member_type_count": 2,
                    "palette_family_count": 4,
                    "active_family_count": 2,
                },
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "signature_verified": True,
                    "solver_combo_count": 23,
                    "solver_combo_status": "broad",
                    "solver_mesh_request_count": 1,
                    "solver_mesh_cell_count": 320,
                    "mesh_breadth_status": "targeted",
                    "member_type_count": 3,
                    "palette_family_count": 4,
                    "active_family_count": 1,
                },
            ],
        },
        out=out,
        generated_at="2026-04-20T12:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["broad_ready_family_count"] == 2
    assert payload["summary"]["full_breadth_family_count"] == 1
    assert payload["summary"]["mesh_broad_family_count"] == 1
    assert payload["summary"]["member_multi_family_count"] == 2
    assert payload["summary"]["family_status_label"] == "sample_tower:broad, steel_braced_frame:broad"
    assert "Native authoring solver family breadth: PASS" in payload["summary_line"]
    assert payload["family_rows"][0]["solver_family_breadth_status"] == "broad"
    assert payload["family_rows"][1]["mesh_breadth_status"] == "targeted"


def test_generate_native_authoring_solver_family_breadth_report_cli(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    family_tracks = tmp_path / "family_tracks.json"
    runtime_submission = tmp_path / "runtime_submission.json"
    out = tmp_path / "native_authoring_solver_family_breadth_report.json"

    _write_json(
        portfolio,
        {
            "family_rows": [
                {
                    "family_id": "composite_podium",
                    "family_label": "Composite Podium",
                    "palette_family_count": 4,
                    "active_family_count": 2,
                    "member_type_count": 3,
                }
            ]
        },
    )
    _write_json(
        family_tracks,
        {"track_rows": [{"family_id": "composite_podium", "release_ready": True, "solver_ready": True}]},
    )
    _write_json(
        runtime_submission,
        {
            "summary": {"family_count": 1, "queued_submission_count": 0},
            "family_rows": [
                {
                    "family_id": "composite_podium",
                    "family_label": "Composite Podium",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "signature_verified": True,
                    "solver_combo_count": 18,
                    "solver_combo_status": "broad",
                    "solver_mesh_request_count": 3,
                    "solver_mesh_cell_count": 720,
                    "mesh_breadth_status": "broad",
                    "member_type_count": 3,
                    "palette_family_count": 4,
                    "active_family_count": 2,
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio),
            "--family-tracks-json",
            str(family_tracks),
            "--runtime-submission-json",
            str(runtime_submission),
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
    assert payload["summary"]["broad_ready_family_count"] == 1
    assert payload["family_rows"][0]["family_id"] == "composite_podium"
    assert "Native authoring solver family breadth: PASS" in proc.stdout
