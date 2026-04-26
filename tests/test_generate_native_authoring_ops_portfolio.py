from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_ops_portfolio import (
    build_native_authoring_ops_portfolio,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_ops_portfolio.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_native_authoring_ops_portfolio_generates_multi_family_surfaces(tmp_path: Path) -> None:
    draft_json = tmp_path / "drafts" / "steel_alt.json"
    _write_json(
        draft_json,
        {
            "format": "native-authoring-workspace-draft",
            "version": 1,
            "authoring_controls": {
                "story_count": 7,
                "bay_count": 5,
                "floor_height_m": 3.6,
                "load_pattern_count": 6,
                "section_id": "steel_box_400x400x16",
            },
        },
    )

    out_dir = tmp_path / "release" / "authoring" / "portfolio"
    signing_dir = tmp_path / "release" / "signing" / "portfolio"
    out = out_dir / "native_authoring_ops_portfolio.json"
    batch_out = out_dir / "native_authoring_ops_portfolio_batch.json"
    registry_index_out = out_dir / "native_authoring_project_registry_index.json"
    registry_workspace_out = out_dir / "native_authoring_project_registry_workspace.json"
    family_tracks_out = out_dir / "native_authoring_family_tracks.json"
    runtime_submission_lane_out = out_dir / "native_authoring_runtime_submission_lane.json"
    runtime_writeback_depth_out = out_dir / "native_authoring_runtime_writeback_depth_report.json"
    multi_project_runtime_writeback_out = out_dir / "native_authoring_multi_project_runtime_writeback_report.json"
    solver_family_breadth_out = out_dir / "native_authoring_solver_family_breadth_report.json"
    local_runtime_scenario_depth_out = out_dir / "native_authoring_local_runtime_scenario_depth_report.json"
    local_variant_writeback_trace_out = out_dir / "native_authoring_local_variant_writeback_trace_report.json"
    writeback_breadth_out = out_dir / "native_authoring_writeback_breadth_report.json"

    payload = build_native_authoring_ops_portfolio(
        portfolio_payload={
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "project_id": "native-authoring-sample-tower",
                    "project_name": "Native Authoring Sample Tower",
                    "draft_label": "baseline",
                    "story_count": 5,
                    "bay_count": 3,
                    "floor_height_m": 3.9,
                    "load_pattern_count": 4,
                    "section_id": "steel_h_600x200",
                },
                {
                    "family_id": "steel_braced_frame",
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "draft_label": "steel-alt",
                    "draft_json_path": str(draft_json),
                },
            ],
        },
        out_dir=out_dir,
        signing_dir=signing_dir,
        out=out,
        batch_out=batch_out,
        registry_index_out=registry_index_out,
        registry_workspace_out=registry_workspace_out,
        snapshot_root=out_dir / "snapshots",
        generated_at="2026-04-19T12:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["complete_family_count"] == 2
    assert payload["summary"]["ready_family_count"] == 2
    assert payload["summary"]["narrowing_family_count"] == 0
    assert payload["summary"]["family_track_count"] == 2
    assert payload["summary"]["release_ready_family_count"] == 2
    assert payload["summary"]["job_ready_family_count"] == 2
    assert payload["summary"]["registry_ready_family_count"] == 2
    assert payload["summary"]["submission_ready_family_count"] == 2
    assert payload["summary"]["runtime_ready_family_count"] == 2
    assert payload["summary"]["writeback_ready_family_count"] == 2
    assert payload["summary"]["full_lane_ready_family_count"] == 2
    assert payload["summary"]["runtime_writeback_depth_ready_family_count"] == 2
    assert payload["summary"]["runtime_writeback_depth_targeted_family_count"] == 0
    assert payload["summary"]["multi_project_runtime_writeback_ready_project_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_full_project_family_count"] == 2
    assert payload["summary"]["solver_family_breadth_ready_family_count"] == 2
    assert payload["summary"]["solver_family_breadth_full_family_count"] >= 1
    assert payload["summary"]["local_runtime_scenario_depth_ready_family_count"] == 2
    assert payload["summary"]["local_runtime_scenario_trace_ready_family_count"] == 2
    assert payload["summary"]["local_runtime_scenario_mesh_ready_family_count"] == 2
    assert payload["summary"]["local_variant_writeback_trace_ready_family_count"] == 2
    assert payload["summary"]["local_variant_workspace_variant_ready_family_count"] == 2
    assert payload["summary"]["local_variant_solver_variant_ready_family_count"] == 2
    assert payload["summary"]["local_variant_writeback_signed_family_count"] == 2
    assert payload["summary"]["writeback_breadth_ready_family_count"] == 2
    assert payload["summary"]["writeback_breadth_full_family_count"] >= 1
    assert payload["summary"]["registry_project_count"] == 2
    assert payload["summary"]["registry_signature_verified_count"] == 2
    assert payload["family_tracks_summary"]["family_count"] == 2
    assert payload["family_tracks_summary"]["job_ready_count"] == 2
    assert payload["family_tracks_summary"]["registry_ready_count"] == 2
    assert payload["artifacts"]["native_authoring_family_tracks_json"] == str(family_tracks_out)
    assert payload["artifacts"]["native_authoring_runtime_submission_lane_json"] == str(
        runtime_submission_lane_out
    )
    assert payload["artifacts"]["native_authoring_runtime_writeback_depth_report_json"] == str(
        runtime_writeback_depth_out
    )
    assert payload["artifacts"]["native_authoring_multi_project_runtime_writeback_report_json"] == str(
        multi_project_runtime_writeback_out
    )
    assert payload["artifacts"]["native_authoring_solver_family_breadth_report_json"] == str(
        solver_family_breadth_out
    )
    assert payload["artifacts"]["native_authoring_local_runtime_scenario_depth_report_json"] == str(
        local_runtime_scenario_depth_out
    )
    assert payload["artifacts"]["native_authoring_local_variant_writeback_trace_report_json"] == str(
        local_variant_writeback_trace_out
    )
    assert payload["artifacts"]["native_authoring_writeback_breadth_report_json"] == str(
        writeback_breadth_out
    )
    assert payload["runtime_submission_lane_summary"]["family_count"] == 2
    assert payload["runtime_submission_lane_summary"]["submission_ready_count"] == 2
    assert "Native authoring runtime submission lane: PASS" in payload["runtime_submission_lane_summary_line"]
    assert payload["runtime_writeback_depth_summary"]["family_count"] == 2
    assert payload["runtime_writeback_depth_summary"]["depth_ready_family_count"] == 2
    assert "Native authoring runtime writeback depth: PASS" in payload["runtime_writeback_depth_summary_line"]
    assert payload["multi_project_runtime_writeback_summary"]["project_count"] == 2
    assert payload["multi_project_runtime_writeback_summary"]["full_depth_project_family_count"] == 2
    assert "Native authoring multi-project runtime/writeback: PASS" in payload["multi_project_runtime_writeback_summary_line"]
    assert payload["solver_family_breadth_summary"]["family_count"] == 2
    assert payload["solver_family_breadth_summary"]["broad_ready_family_count"] == 2
    assert "Native authoring solver family breadth: PASS" in payload["solver_family_breadth_summary_line"]
    assert payload["local_runtime_scenario_depth_summary"]["family_count"] == 2
    assert payload["local_runtime_scenario_depth_summary"]["depth_ready_family_count"] == 2
    assert "Native authoring local runtime scenario depth: PASS" in payload["local_runtime_scenario_depth_summary_line"]
    assert payload["local_variant_writeback_trace_summary"]["family_count"] == 2
    assert payload["local_variant_writeback_trace_summary"]["deep_ready_family_count"] == 2
    assert "Native authoring local variant/writeback trace: PASS" in payload["local_variant_writeback_trace_summary_line"]
    assert payload["writeback_breadth_summary"]["family_count"] == 2
    assert payload["writeback_breadth_summary"]["broad_ready_family_count"] == 2
    assert "Native authoring writeback breadth: PASS" in payload["writeback_breadth_summary_line"]

    family_ids = [row["family_id"] for row in payload["family_rows"]]
    assert family_ids == ["sample_tower", "steel_braced_frame"]
    steel_row = next(row for row in payload["family_rows"] if row["family_id"] == "steel_braced_frame")
    assert steel_row["draft_json_path"] == str(draft_json)
    assert steel_row["contract_pass"] is True
    assert steel_row["commercialization_status"] == "ready"
    assert steel_row["commercialization_score"] >= 80
    assert steel_row["signature_verified"] is True
    assert steel_row["solver_ready"] is True
    assert steel_row["family_label"] == "Steel Braced Frame"
    assert steel_row["member_type_count"] == 4
    assert steel_row["palette_family_count"] >= 4
    assert "steel_braced_frame: READY" in steel_row["commercialization_summary_line"]

    sample_row = next(row for row in payload["family_rows"] if row["family_id"] == "sample_tower")
    assert sample_row["family_label"] == "Sample Tower"
    assert sample_row["member_type_label"] == "beam, column"
    assert sample_row["active_family_label"] == "rc, steel"

    family_tracks_payload = json.loads(family_tracks_out.read_text(encoding="utf-8"))
    assert family_tracks_payload["contract_pass"] is True
    assert family_tracks_payload["summary"]["family_count"] == 2
    assert family_tracks_payload["summary"]["ready_family_count"] == 2
    assert family_tracks_payload["summary"]["release_ready_count"] == 2
    assert family_tracks_payload["summary"]["job_ready_count"] == 2
    assert family_tracks_payload["summary"]["registry_ready_count"] == 2
    steel_track = next(
        row for row in family_tracks_payload["track_rows"] if row["family_id"] == "steel_braced_frame"
    )
    assert steel_track["track_id"] == "native_authoring_family::steel_braced_frame"
    assert steel_track["release_ready"] is True
    assert steel_track["job_ready"] is True
    assert steel_track["registry_ready"] is True
    expected_mesh_status = (
        "broad"
        if steel_track["solver_mesh_request_count"] >= 2 and steel_track["solver_mesh_cell_count"] > 0
        else "targeted"
        if steel_track["solver_mesh_request_count"] > 0 or steel_track["solver_mesh_cell_count"] > 0
        else "none"
    )
    assert steel_track["mesh_breadth_status"] == expected_mesh_status
    sample_track = next(row for row in family_tracks_payload["track_rows"] if row["family_id"] == "sample_tower")
    assert sample_track["release_ready"] is True
    assert sample_track["job_ready"] is True
    assert sample_track["registry_ready"] is True

    runtime_submission_lane_payload = json.loads(runtime_submission_lane_out.read_text(encoding="utf-8"))
    assert runtime_submission_lane_payload["contract_pass"] is True
    assert runtime_submission_lane_payload["summary"]["family_count"] == 2
    assert runtime_submission_lane_payload["summary"]["submission_ready_count"] == 2
    assert runtime_submission_lane_payload["summary"]["runtime_ready_count"] == 2
    assert runtime_submission_lane_payload["summary"]["writeback_ready_count"] == 2
    steel_lane_row = next(
        row for row in runtime_submission_lane_payload["family_rows"] if row["family_id"] == "steel_braced_frame"
    )
    assert steel_lane_row["submission_ready"] is True
    assert steel_lane_row["runtime_ready"] is True
    assert steel_lane_row["writeback_ready"] is True
    assert steel_lane_row["lane_status"] == "ready"
    runtime_writeback_depth_payload = json.loads(
        runtime_writeback_depth_out.read_text(encoding="utf-8")
    )
    assert runtime_writeback_depth_payload["contract_pass"] is True
    assert runtime_writeback_depth_payload["summary"]["family_count"] == 2
    assert runtime_writeback_depth_payload["summary"]["depth_ready_family_count"] == 2
    assert runtime_writeback_depth_payload["summary"]["signature_verified_family_count"] == 2
    multi_project_runtime_writeback_payload = json.loads(
        multi_project_runtime_writeback_out.read_text(encoding="utf-8")
    )
    assert multi_project_runtime_writeback_payload["contract_pass"] is True
    assert multi_project_runtime_writeback_payload["summary"]["project_count"] == 2
    assert multi_project_runtime_writeback_payload["summary"]["project_family_count"] == 2
    assert multi_project_runtime_writeback_payload["summary"]["ready_project_count"] == 2
    solver_family_breadth_payload = json.loads(solver_family_breadth_out.read_text(encoding="utf-8"))
    assert solver_family_breadth_payload["contract_pass"] is True
    assert solver_family_breadth_payload["summary"]["family_count"] == 2
    assert solver_family_breadth_payload["summary"]["broad_ready_family_count"] == 2
    assert solver_family_breadth_payload["summary"]["member_multi_family_count"] == 2
    writeback_breadth_payload = json.loads(writeback_breadth_out.read_text(encoding="utf-8"))
    assert writeback_breadth_payload["contract_pass"] is True
    assert writeback_breadth_payload["summary"]["family_count"] == 2
    assert writeback_breadth_payload["summary"]["broad_ready_family_count"] == 2
    assert writeback_breadth_payload["summary"]["mesh_broad_family_count"] >= 1

    for family_id in family_ids:
        family_dir = out_dir / family_id
        assert (family_dir / "native_authoring_ops_bundle.json").exists()
        assert (family_dir / "native_authoring_project_registry.json").exists()
        bundle_payload = json.loads((family_dir / "native_authoring_ops_bundle.json").read_text(encoding="utf-8"))
        assert bundle_payload["summary"]["family_id"] == family_id
        assert bundle_payload["summary"]["portfolio_name"] == "phase1-native-authoring-ops-portfolio"

    batch_payload = json.loads(batch_out.read_text(encoding="utf-8"))
    assert batch_payload["contract_pass"] is True
    assert batch_payload["summary"]["job_count"] == 2
    assert batch_payload["summary"]["completed_count"] == 2
    assert batch_payload["summary"]["snapshot_count"] == 2

    index_payload = json.loads(registry_index_out.read_text(encoding="utf-8"))
    assert index_payload["contract_pass"] is True
    assert index_payload["summary"]["project_count"] == 2
    assert index_payload["summary"]["family_count"] == 2
    assert index_payload["summary"]["portfolio_count"] == 1
    assert len(index_payload["family_rows"]) == 2
    assert {row["family_id"] for row in index_payload["family_rows"]} == set(family_ids)

    workspace_payload = json.loads(registry_workspace_out.read_text(encoding="utf-8"))
    assert workspace_payload["run_id"] == "phase1-project-registry-portfolio-workspace"
    assert len(workspace_payload["family_rows"]) == 2
    assert payload["summary"]["family_status_label"]
    assert "runtime_writeback_depth=2" in payload["summary_line"]
    assert "ready=2" in payload["summary_line"]


def test_build_native_authoring_ops_portfolio_default_scaffold_covers_eight_families(tmp_path: Path) -> None:
    out_dir = tmp_path / "release" / "authoring" / "portfolio"
    signing_dir = tmp_path / "release" / "signing" / "portfolio"
    out = out_dir / "native_authoring_ops_portfolio.json"
    batch_out = out_dir / "native_authoring_ops_portfolio_batch.json"
    registry_index_out = out_dir / "native_authoring_project_registry_index.json"
    registry_workspace_out = out_dir / "native_authoring_project_registry_workspace.json"

    payload = build_native_authoring_ops_portfolio(
        out_dir=out_dir,
        signing_dir=signing_dir,
        out=out,
        batch_out=batch_out,
        registry_index_out=registry_index_out,
        registry_workspace_out=registry_workspace_out,
        snapshot_root=out_dir / "snapshots",
        generated_at="2026-04-21T12:00:00+00:00",
    )

    expected_family_ids = [
        "sample_tower",
        "steel_braced_frame",
        "rc_wall_core",
        "composite_podium",
        "outrigger_transfer_tower",
        "dual_system_hospital",
        "belt_truss_mega_frame",
        "deep_transfer_basement",
    ]

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 8
    assert payload["summary"]["complete_family_count"] == 8
    assert payload["summary"]["ready_family_count"] == 8
    assert payload["summary"]["family_track_count"] == 8
    assert payload["summary"]["release_ready_family_count"] == 8
    assert payload["summary"]["submission_ready_family_count"] == 8
    assert payload["summary"]["runtime_ready_family_count"] == 8
    assert payload["summary"]["writeback_ready_family_count"] == 8
    assert payload["summary"]["solver_family_breadth_ready_family_count"] == 8
    assert payload["summary"]["local_runtime_scenario_depth_ready_family_count"] == 8
    assert payload["summary"]["writeback_breadth_ready_family_count"] == 8
    assert [row["family_id"] for row in payload["family_rows"]] == expected_family_ids

    belt_row = next(row for row in payload["family_rows"] if row["family_id"] == "belt_truss_mega_frame")
    assert belt_row["commercialization_status"] == "ready"
    assert belt_row["member_type_count"] == 5
    assert belt_row["solver_mesh_request_count"] == 6
    assert belt_row["active_family_label"] == "composite, deck/floor, rc, steel"

    deep_row = next(row for row in payload["family_rows"] if row["family_id"] == "deep_transfer_basement")
    assert deep_row["commercialization_status"] == "ready"
    assert deep_row["member_type_count"] == 5
    assert deep_row["solver_mesh_request_count"] == 7
    assert deep_row["active_family_label"] == "composite, deck/floor, rc, steel"

    family_tracks_payload = json.loads((out_dir / "native_authoring_family_tracks.json").read_text(encoding="utf-8"))
    assert family_tracks_payload["summary"]["family_count"] == 8
    assert family_tracks_payload["summary"]["ready_family_count"] == 8

    solver_family_breadth_payload = json.loads(
        (out_dir / "native_authoring_solver_family_breadth_report.json").read_text(encoding="utf-8")
    )
    assert solver_family_breadth_payload["summary"]["family_count"] == 8
    assert solver_family_breadth_payload["summary"]["broad_ready_family_count"] == 8

    local_runtime_depth_payload = json.loads(
        (out_dir / "native_authoring_local_runtime_scenario_depth_report.json").read_text(encoding="utf-8")
    )
    assert local_runtime_depth_payload["summary"]["family_count"] == 8
    assert local_runtime_depth_payload["summary"]["depth_ready_family_count"] == 8


def test_generate_native_authoring_ops_portfolio_cli_reads_manifest(tmp_path: Path) -> None:
    draft_json = tmp_path / "drafts" / "podium_heavy.json"
    _write_json(
        draft_json,
        {
            "format": "native-authoring-workspace-draft",
            "version": 1,
            "authoring_controls": {
                "family_id": "composite_podium",
                "story_count": 6,
                "bay_count": 4,
                "floor_height_m": 4.1,
                "load_pattern_count": 6,
                "section_id": "deck_beam_500x250",
            },
        },
    )
    manifest = tmp_path / "portfolio.json"
    _write_json(
        manifest,
        {
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "family_rows": [
                {
                    "family_id": "composite_podium",
                    "project_id": "native-authoring-composite-podium",
                    "project_name": "Native Authoring Composite Podium",
                    "draft_label": "podium-heavy",
                    "draft_json_path": str(draft_json),
                }
            ],
        },
    )

    out_dir = tmp_path / "release" / "portfolio"
    out = out_dir / "native_authoring_ops_portfolio.json"
    batch_out = out_dir / "native_authoring_ops_portfolio_batch.json"
    registry_index_out = out_dir / "native_authoring_project_registry_index.json"
    registry_workspace_out = out_dir / "native_authoring_project_registry_workspace.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(manifest),
            "--out-dir",
            str(out_dir),
            "--signing-dir",
            str(tmp_path / "release" / "signing"),
            "--out",
            str(out),
            "--batch-out",
            str(batch_out),
            "--registry-index-out",
            str(registry_index_out),
            "--registry-workspace-out",
            str(registry_workspace_out),
            "--snapshot-root",
            str(out_dir / "snapshots"),
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
    assert payload["summary"]["ready_family_count"] == 1
    assert payload["summary"]["family_track_count"] == 1
    assert payload["summary"]["submission_ready_family_count"] == 1
    assert payload["summary"]["writeback_ready_family_count"] == 1
    assert payload["summary"]["writeback_breadth_ready_family_count"] == 1
    assert payload["family_tracks_summary"]["job_ready_count"] == 1
    assert payload["runtime_submission_lane_summary"]["family_count"] == 1
    assert payload["family_rows"][0]["family_id"] == "composite_podium"
    assert payload["family_rows"][0]["family_label"] == "Composite Podium"
    assert payload["family_rows"][0]["member_type_label"] == "beam, column, slab"
    family_tracks_payload = json.loads((out_dir / "native_authoring_family_tracks.json").read_text(encoding="utf-8"))
    assert family_tracks_payload["summary"]["family_count"] == 1
    assert family_tracks_payload["track_rows"][0]["family_id"] == "composite_podium"
    assert family_tracks_payload["track_rows"][0]["job_ready"] is True
    runtime_submission_lane_payload = json.loads(
        (out_dir / "native_authoring_runtime_submission_lane.json").read_text(encoding="utf-8")
    )
    assert runtime_submission_lane_payload["summary"]["family_count"] == 1
    assert runtime_submission_lane_payload["family_rows"][0]["family_id"] == "composite_podium"
    assert runtime_submission_lane_payload["family_rows"][0]["writeback_ready"] is True
    writeback_breadth_payload = json.loads(
        (out_dir / "native_authoring_writeback_breadth_report.json").read_text(encoding="utf-8")
    )
    assert writeback_breadth_payload["summary"]["broad_ready_family_count"] == 1
    assert "Native authoring ops portfolio: PASS" in proc.stdout
