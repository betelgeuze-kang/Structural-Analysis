from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_runtime_submission_lane import (
    build_native_authoring_runtime_submission_lane,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_runtime_submission_lane.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _family_artifacts(tmp_path: Path, family_id: str) -> dict[str, str]:
    family_dir = tmp_path / family_id
    artifacts = {
        "solver_session_json": family_dir / "native_authoring_solver_session.json",
        "solver_loadcomb_preview_mgt": family_dir / "native_authoring_solver_session.loadcomb_preview.mgt",
        "job_manifest_json": family_dir / "native_authoring_job_manifest.json",
        "batch_job_report_json": family_dir / "native_authoring_batch_job_report.json",
        "project_registry_json": family_dir / "native_authoring_project_registry.json",
        "project_package_zip": family_dir / "native_authoring_project_package.zip",
        "project_registry_public_key": family_dir / "native_authoring_project_registry_ed25519.pub.pem",
        "project_registry_signature": family_dir / "native_authoring_project_registry.signature.b64",
    }
    _write_json(artifacts["solver_session_json"], {"summary": {"combo_count": 12}})
    _write_text(artifacts["solver_loadcomb_preview_mgt"], "*LOADCOMB\n")
    _write_json(artifacts["job_manifest_json"], {"jobs": []})
    _write_json(artifacts["batch_job_report_json"], {"summary": {"snapshot_count": 3}})
    _write_json(artifacts["project_registry_json"], {"summary": {"approval_count": 3}})
    _write_bytes(artifacts["project_package_zip"], b"pk")
    _write_text(artifacts["project_registry_public_key"], "pub")
    _write_text(artifacts["project_registry_signature"], "sig\n")
    return {key: str(value) for key, value in artifacts.items()}


def test_build_native_authoring_runtime_submission_lane_merges_family_surfaces(tmp_path: Path) -> None:
    sample_artifacts = _family_artifacts(tmp_path, "sample_tower")
    steel_artifacts = _family_artifacts(tmp_path, "steel_braced_frame")
    Path(steel_artifacts["project_registry_json"]).unlink()
    Path(steel_artifacts["project_package_zip"]).unlink()
    Path(steel_artifacts["project_registry_signature"]).unlink()

    payload = build_native_authoring_runtime_submission_lane(
        family_rows=[
            {
                "family_id": "sample_tower",
                "family_label": "Sample Tower",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "project_id": "native-authoring-sample-tower",
                "project_name": "Native Authoring Sample Tower",
                "draft_label": "baseline",
                "commercialization_status": "ready",
                "commercialization_score": 100,
                "workspace_ready": True,
                "solver_ready": True,
                "runtime_ready": True,
                "ops_ready": True,
                "batch_ready": True,
                "registry_ready": True,
                "signature_verified": True,
                "story_count": 5,
                "node_count": 24,
                "member_count": 35,
                "load_pattern_count": 4,
                "solver_combo_count": 13,
                "solver_mesh_request_count": 2,
                "solver_mesh_cell_count": 588,
                "solver_load_case_count": 4,
                "solver_loadcomb_line_count": 37,
                "job_count": 3,
                "snapshot_count": 3,
                "approval_count": 3,
                "package_bytes": 66568,
                "registry_package_sha256": "sample-sha",
                "member_type_count": 2,
                "member_type_label": "beam, column",
                "contract_pass": True,
                "summary_line": "bundle sample",
                "artifacts": sample_artifacts,
            },
            {
                "family_id": "steel_braced_frame",
                "family_label": "Steel Braced Frame",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "project_id": "native-authoring-steel-braced",
                "project_name": "Native Authoring Steel Braced",
                "draft_label": "steel-alt",
                "commercialization_status": "ready",
                "commercialization_score": 92,
                "workspace_ready": True,
                "solver_ready": True,
                "runtime_ready": True,
                "ops_ready": True,
                "batch_ready": True,
                "registry_ready": False,
                "signature_verified": False,
                "story_count": 8,
                "node_count": 54,
                "member_count": 168,
                "load_pattern_count": 6,
                "solver_combo_count": 23,
                "solver_mesh_request_count": 1,
                "solver_mesh_cell_count": 10,
                "solver_load_case_count": 6,
                "solver_loadcomb_line_count": 65,
                "job_count": 3,
                "snapshot_count": 3,
                "approval_count": 0,
                "package_bytes": 97168,
                "registry_package_sha256": "",
                "member_type_count": 3,
                "member_type_label": "beam, brace, column",
                "contract_pass": True,
                "summary_line": "bundle steel",
                "artifacts": steel_artifacts,
            },
        ],
        track_rows=[
            {
                "family_id": "sample_tower",
                "family_label": "Sample Tower",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "project_id": "native-authoring-sample-tower",
                "project_name": "Native Authoring Sample Tower",
                "draft_label": "baseline",
                "commercialization_status": "ready",
                "commercialization_score": 100,
                "release_ready": True,
                "workspace_ready": True,
                "solver_ready": True,
                "runtime_ready": True,
                "ops_ready": True,
                "job_ready": True,
                "batch_ready": True,
                "registry_ready": True,
                "signature_verified": True,
                "solver_combo_count": 13,
                "solver_mesh_request_count": 2,
                "solver_mesh_cell_count": 588,
                "solver_load_case_count": 4,
                "solver_loadcomb_line_count": 37,
                "job_count": 3,
                "snapshot_count": 3,
                "approval_count": 3,
                "registry_package_sha256": "sample-sha",
                "track_summary_line": "sample track",
                "contract_pass": True,
                "artifacts": sample_artifacts,
            },
            {
                "family_id": "steel_braced_frame",
                "family_label": "Steel Braced Frame",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "project_id": "native-authoring-steel-braced",
                "project_name": "Native Authoring Steel Braced",
                "draft_label": "steel-alt",
                "commercialization_status": "ready",
                "commercialization_score": 92,
                "release_ready": False,
                "workspace_ready": True,
                "solver_ready": True,
                "runtime_ready": True,
                "ops_ready": True,
                "job_ready": True,
                "batch_ready": True,
                "registry_ready": False,
                "signature_verified": False,
                "solver_combo_count": 23,
                "solver_mesh_request_count": 1,
                "solver_mesh_cell_count": 10,
                "solver_load_case_count": 6,
                "solver_loadcomb_line_count": 65,
                "job_count": 3,
                "snapshot_count": 3,
                "approval_count": 0,
                "registry_package_sha256": "",
                "track_summary_line": "steel track",
                "contract_pass": True,
                "artifacts": steel_artifacts,
            },
        ],
        out=tmp_path / "native_authoring_runtime_submission_lane.json",
        generated_at="2026-04-19T12:00:00+00:00",
        portfolio_name="phase1-native-authoring-ops-portfolio",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["complete_source_family_count"] == 2
    assert payload["summary"]["submission_ready_count"] == 1
    assert payload["summary"]["runtime_ready_count"] == 2
    assert payload["summary"]["writeback_ready_count"] == 1
    assert payload["summary"]["full_ready_count"] == 1
    assert payload["summary"]["total_approval_count"] == 3
    assert "submission_ready=1" in payload["summary_line"]

    sample_row = next(row for row in payload["family_rows"] if row["family_id"] == "sample_tower")
    assert sample_row["submission_ready"] is True
    assert sample_row["runtime_ready"] is True
    assert sample_row["writeback_ready"] is True
    assert sample_row["lane_status"] == "ready"
    assert sample_row["summary_line"].startswith("sample_tower: submission=READY")

    steel_row = next(row for row in payload["family_rows"] if row["family_id"] == "steel_braced_frame")
    assert steel_row["submission_ready"] is False
    assert steel_row["submission_status"] == "narrowing"
    assert steel_row["runtime_ready"] is True
    assert steel_row["writeback_ready"] is False
    assert steel_row["writeback_status"] == "check"
    assert steel_row["lane_status"] == "narrowing"
    assert steel_row["job_manifest_present"] is True
    assert steel_row["registry_json_present"] is False


def test_generate_native_authoring_runtime_submission_lane_cli_reads_portfolio_and_track_json(
    tmp_path: Path,
) -> None:
    family_artifacts = _family_artifacts(tmp_path, "composite_podium")
    portfolio_json = tmp_path / "native_authoring_ops_portfolio.json"
    family_tracks_json = tmp_path / "native_authoring_family_tracks.json"
    out = tmp_path / "native_authoring_runtime_submission_lane.json"

    _write_json(
        portfolio_json,
        {
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "family_rows": [
                {
                    "family_id": "composite_podium",
                    "family_label": "Composite Podium",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "native-authoring-composite-podium",
                    "project_name": "Native Authoring Composite Podium",
                    "draft_label": "podium-heavy",
                    "commercialization_status": "ready",
                    "commercialization_score": 100,
                    "workspace_ready": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "ops_ready": True,
                    "batch_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "solver_combo_count": 23,
                    "solver_mesh_request_count": 3,
                    "solver_mesh_cell_count": 496,
                    "solver_load_case_count": 6,
                    "solver_loadcomb_line_count": 65,
                    "job_count": 3,
                    "snapshot_count": 3,
                    "approval_count": 3,
                    "registry_package_sha256": "podium-sha",
                    "contract_pass": True,
                    "summary_line": "portfolio row",
                    "artifacts": family_artifacts,
                }
            ],
        },
    )
    _write_json(
        family_tracks_json,
        {
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "track_rows": [
                {
                    "family_id": "composite_podium",
                    "family_label": "Composite Podium",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "native-authoring-composite-podium",
                    "project_name": "Native Authoring Composite Podium",
                    "draft_label": "podium-heavy",
                    "commercialization_status": "ready",
                    "commercialization_score": 100,
                    "release_ready": True,
                    "workspace_ready": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "ops_ready": True,
                    "job_ready": True,
                    "batch_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "solver_combo_count": 23,
                    "solver_mesh_request_count": 3,
                    "solver_mesh_cell_count": 496,
                    "solver_load_case_count": 6,
                    "solver_loadcomb_line_count": 65,
                    "job_count": 3,
                    "snapshot_count": 3,
                    "approval_count": 3,
                    "registry_package_sha256": "podium-sha",
                    "track_summary_line": "track row",
                    "contract_pass": True,
                    "artifacts": family_artifacts,
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio_json),
            "--family-tracks-json",
            str(family_tracks_json),
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
    assert payload["summary"]["family_count"] == 1
    assert payload["summary"]["submission_ready_count"] == 1
    assert payload["summary"]["runtime_ready_count"] == 1
    assert payload["summary"]["writeback_ready_count"] == 1
    assert payload["family_rows"][0]["family_id"] == "composite_podium"
    assert payload["family_rows"][0]["lane_status"] == "ready"
    assert "Native authoring runtime submission lane: PASS" in proc.stdout
