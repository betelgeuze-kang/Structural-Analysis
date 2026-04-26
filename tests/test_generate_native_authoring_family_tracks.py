from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_family_tracks import (
    build_native_authoring_family_tracks,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_family_tracks.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sample_family_rows() -> list[dict]:
    return [
        {
            "family_id": "steel_braced_frame",
            "family_label": "Steel Braced Frame",
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "project_id": "native-authoring-steel-braced",
            "project_name": "Native Authoring Steel Braced",
            "draft_label": "steel-alt",
            "authoring_family_id": "steel_braced_frame",
            "draft_json_path": "drafts/steel-alt.json",
            "commercialization_status": "ready",
            "commercialization_score": 91,
            "workspace_ready": True,
            "solver_ready": True,
            "runtime_ready": True,
            "ops_ready": True,
            "batch_ready": True,
            "registry_ready": True,
            "signature_verified": True,
            "story_count": 8,
            "node_count": 88,
            "member_count": 132,
            "load_pattern_count": 6,
            "solver_combo_count": 12,
            "solver_mesh_request_count": 3,
            "solver_mesh_cell_count": 4096,
            "solver_load_case_count": 6,
            "solver_loadcomb_line_count": 14,
            "job_count": 3,
            "snapshot_count": 2,
            "approval_count": 3,
            "package_bytes": 2048,
            "registry_package_sha256": "abc123",
            "palette_section_count": 5,
            "palette_family_count": 4,
            "palette_family_label": "composite, deck/floor, rc, steel",
            "active_section_count": 3,
            "active_family_count": 2,
            "active_family_label": "rc, steel",
            "member_type_count": 3,
            "member_type_label": "beam, brace, column",
            "contract_pass": True,
            "reason_code": "PASS",
            "summary_line": "bundle ready",
            "commercialization_summary_line": "steel_braced_frame: READY | score=91",
            "artifacts": {
                "native_authoring_ops_bundle_json": "release/steel_braced_frame/native_authoring_ops_bundle.json"
            },
        },
        {
            "family_id": "rc_wall_core",
            "family_label": "RC Wall Core",
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "project_id": "native-authoring-rc-wall-core",
            "project_name": "Native Authoring RC Wall Core",
            "draft_label": "core-residential",
            "authoring_family_id": "rc_wall_core",
            "draft_json_path": "drafts/core-residential.json",
            "commercialization_status": "narrowing",
            "commercialization_score": 68,
            "workspace_ready": True,
            "solver_ready": True,
            "runtime_ready": True,
            "ops_ready": True,
            "batch_ready": True,
            "registry_ready": False,
            "signature_verified": False,
            "story_count": 9,
            "node_count": 96,
            "member_count": 144,
            "load_pattern_count": 6,
            "solver_combo_count": 8,
            "solver_mesh_request_count": 1,
            "solver_mesh_cell_count": 1536,
            "solver_load_case_count": 6,
            "solver_loadcomb_line_count": 10,
            "job_count": 3,
            "snapshot_count": 0,
            "approval_count": 2,
            "package_bytes": 1536,
            "registry_package_sha256": "def456",
            "palette_section_count": 4,
            "palette_family_count": 3,
            "palette_family_label": "deck/floor, rc, steel",
            "active_section_count": 2,
            "active_family_count": 1,
            "active_family_label": "rc",
            "member_type_count": 2,
            "member_type_label": "column, wall",
            "contract_pass": True,
            "reason_code": "PASS",
            "summary_line": "bundle narrowing",
            "commercialization_summary_line": "rc_wall_core: NARROWING | score=68",
            "artifacts": {
                "native_authoring_ops_bundle_json": "release/rc_wall_core/native_authoring_ops_bundle.json"
            },
        },
    ]


def test_build_native_authoring_family_tracks_generates_release_surface(tmp_path: Path) -> None:
    out = tmp_path / "release" / "authoring" / "portfolio" / "native_authoring_family_tracks.json"
    payload = build_native_authoring_family_tracks(
        family_rows=_sample_family_rows(),
        out=out,
        generated_at="2026-04-19T12:00:00+00:00",
        portfolio_name="phase1-native-authoring-ops-portfolio",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["ready_family_count"] == 1
    assert payload["summary"]["narrowing_family_count"] == 1
    assert payload["summary"]["release_ready_count"] == 1
    assert payload["summary"]["job_ready_count"] == 1
    assert payload["summary"]["registry_ready_count"] == 1
    assert payload["summary"]["max_solver_combo_count"] == 12
    assert payload["summary"]["max_solver_mesh_cell_count"] == 4096
    assert payload["artifacts"]["native_authoring_family_tracks_json"] == str(out)

    steel_track = next(row for row in payload["track_rows"] if row["family_id"] == "steel_braced_frame")
    assert steel_track["track_id"] == "native_authoring_family::steel_braced_frame"
    assert steel_track["release_ready"] is True
    assert steel_track["job_ready"] is True
    assert steel_track["registry_ready"] is True
    assert steel_track["solver_combo_status"] == "broad"
    assert steel_track["mesh_breadth_status"] == "broad"
    assert "release_ready=True" in steel_track["track_summary_line"]

    rc_track = next(row for row in payload["track_rows"] if row["family_id"] == "rc_wall_core")
    assert rc_track["release_ready"] is False
    assert rc_track["job_ready"] is False
    assert rc_track["registry_ready"] is False
    assert rc_track["solver_combo_status"] == "targeted"
    assert rc_track["mesh_breadth_status"] == "targeted"
    assert "job_ready=False" in rc_track["track_summary_line"]

    persisted = json.loads(out.read_text(encoding="utf-8"))
    assert persisted["summary"]["mesh_status_label"]


def test_generate_native_authoring_family_tracks_cli_reads_portfolio_json(tmp_path: Path) -> None:
    portfolio_json = tmp_path / "native_authoring_ops_portfolio.json"
    _write_json(
        portfolio_json,
        {
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "family_rows": _sample_family_rows(),
        },
    )
    out = tmp_path / "native_authoring_family_tracks.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio_json),
            "--out",
            str(out),
            "--generated-at",
            "2026-04-19T12:30:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["inputs"]["portfolio_json_path"] == str(portfolio_json)
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["release_ready_count"] == 1
    assert payload["track_rows"][0]["portfolio_name"] == "phase1-native-authoring-ops-portfolio"
    assert "Native authoring family tracks: PASS" in proc.stdout
