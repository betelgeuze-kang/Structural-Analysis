from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_prepare_midas_binary_decoded_preview_bridge(tmp_path: Path) -> None:
    inventory_json = tmp_path / "meb_decoded_inventory.json"
    inventory_report = tmp_path / "meb_decoded_inventory_report.json"
    refresh_report = tmp_path / "meb_inventory_refresh_report.json"
    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    bridge_report = out_dir / "bridge_report.json"

    _write_json(
        inventory_json,
        {
            "geometry_preview": {
                "mode": "heuristic_xy_segment_preview",
                "source_table": "xVPNT",
                "candidate_segments_xy": [
                    {"x1": 0.0, "y1": 0.0, "x2": 4.0, "y2": 0.0},
                    {"x1": 4.0, "y1": 0.0, "x2": 4.0, "y2": 3.0},
                    {"x1": 4.0, "y1": 3.0, "x2": 0.0, "y2": 3.0},
                ],
            },
            "summary": {
                "geometry_preview_segment_count": 3,
                "geometry_preview_point_count": 4,
                "geometry_preview_source_table": "xVPNT",
            },
        },
    )
    _write_json(
        inventory_report,
        {
            "reason_code": "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY",
            "summary": {
                "geometry_preview_ready": True,
                "geometry_preview_segment_count": 3,
                "geometry_preview_point_count": 4,
                "geometry_preview_source_table": "xVPNT",
            },
        },
    )
    _write_json(
        refresh_report,
        {
            "selected_member_name": "sample_rc_house.meb",
            "selected_reason_code": "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_midas_binary_decoded_preview_bridge.py",
            "--source-id",
            "sample_rc_house",
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(refresh_report),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(bridge_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(bridge_report.read_text(encoding="utf-8"))
    assert report_payload["contract_pass"] is True
    assert report_payload["summary"]["viewer_ready"] is True
    assert report_payload["summary"]["preview_segment_count"] == 3
    assert report_payload["summary"]["preview_point_count"] == 4
    assert report_payload["summary"]["source_table"] == "xVPNT"
    assert report_payload["summary"]["preview_basis"] == "table_directory_heuristic"
    assert report_payload["summary"]["preview_projection_label"] == ""
    assert report_payload["summary"]["preview_anchor_table_names"] == []
    assert report_payload["summary"]["preview_surface_bucket"] == "verified-preview"
    assert report_payload["summary"]["preview_surface_status_label"] == "viewer-ready verified preview 3d bridge"
    assert report_payload["summary"]["preview_surface_status_tone"] == "ok"
    assert report_payload["summary"]["preview_readiness_stage_label"] == "viewer-ready verified preview"
    assert report_payload["summary"]["preview_exactness_tier"] == "verified-geometry"
    assert report_payload["summary"]["preview_exactness_label"] == "verified geometry preview"
    assert report_payload["summary"]["preview_exactness_signal_source"] == "geometry_preview_ready"

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert model_payload["topology_metrics"]["element_count"] == 3
    assert model_payload["model"]["metadata"]["bridge_family"] == "decoded_preview_baseline"
    assert model_payload["model"]["metadata"]["preview_basis"] == "table_directory_heuristic"
    assert model_payload["model"]["elements"][0]["family"] == "beam_preview"
    assert model_payload["model"]["metadata"]["preview_surface_status_label"] == "viewer-ready verified preview 3d bridge"
    assert model_payload["model"]["metadata"]["preview_exactness_tier"] == "verified-geometry"

    dataset = np.load(dataset_npz, allow_pickle=True)
    assert "member_ids" in dataset.files
    assert "story_band_index" in dataset.files
    assert dataset["member_ids"].shape[0] == 3
    assert dataset["story_band_index"].shape[0] == 3


def test_prepare_midas_binary_decoded_preview_bridge_from_point_scan(tmp_path: Path) -> None:
    inventory_json = tmp_path / "meb_decoded_inventory.json"
    inventory_report = tmp_path / "meb_decoded_inventory_report.json"
    refresh_report = tmp_path / "meb_inventory_refresh_report.json"
    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    bridge_report = out_dir / "bridge_report.json"

    _write_json(
        inventory_json,
        {
            "geometry_preview": {
                "mode": "heuristic_xyz_point_scan",
                "projection_label": "XY",
                "source_table": "raw_f64_xyz_scan",
                "candidate_points_xy": [
                    [0.0, 0.0],
                    [4.0, 0.0],
                    [4.0, 3.0],
                    [0.0, 3.0],
                    [0.0, 0.0],
                ],
            },
            "summary": {
                "geometry_preview_point_count": 5,
                "geometry_preview_segment_count": 0,
                "geometry_preview_source_table": "raw_f64_xyz_scan",
                "geometry_preview_mode": "heuristic_xyz_point_scan",
            },
        },
    )
    _write_json(
        inventory_report,
        {
            "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
            "summary": {
                "geometry_preview_ready": False,
                "geometry_preview_point_count": 5,
                "geometry_preview_segment_count": 0,
                "geometry_preview_source_table": "raw_f64_xyz_scan",
                "geometry_preview_mode": "heuristic_xyz_point_scan",
            },
        },
    )
    _write_json(
        refresh_report,
        {
            "selected_member_name": "sample_beam.mcb",
            "selected_reason_code": "PASS_TABLE_DIRECTORY_ONLY",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_midas_binary_decoded_preview_bridge.py",
            "--source-id",
            "sample_beam",
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(refresh_report),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(bridge_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(bridge_report.read_text(encoding="utf-8"))
    assert report_payload["contract_pass"] is True
    assert report_payload["summary"]["viewer_ready"] is True
    assert report_payload["summary"]["preview_state_label"] == "unverified raw preview"
    assert report_payload["summary"]["family_assumption"] == "point_scan_preview"
    assert report_payload["summary"]["bridge_mode"] == "point_scan_chain"
    assert report_payload["summary"]["accepted_type_label"].startswith("heuristic_point_link=")
    assert report_payload["summary"]["preview_basis"] == "raw_xyz_scan"
    assert report_payload["summary"]["preview_projection_label"] == "XY"
    assert report_payload["summary"]["preview_surface_bucket"] == "raw-preview"
    assert report_payload["summary"]["preview_surface_status_label"] == "raw preview-derived 3d candidate"
    assert report_payload["summary"]["preview_readiness_stage_label"] == "raw preview candidate"
    assert report_payload["summary"]["preview_exactness_tier"] == "raw-preview"
    assert report_payload["summary"]["preview_exactness_label"] == "raw preview"
    assert report_payload["summary"]["preview_exactness_signal_source"] == "geometry_preview.mode"

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert model_payload["model"]["metadata"]["bridge_mode"] == "point_scan_chain"
    assert model_payload["model"]["metadata"]["preview_state_label"] == "unverified raw preview"
    assert model_payload["model"]["metadata"]["preview_basis"] == "raw_xyz_scan"
    assert model_payload["model"]["metadata"]["preview_surface_bucket"] == "raw-preview"
    assert model_payload["model"]["metadata"]["preview_exactness_tier"] == "raw-preview"
    assert model_payload["model"]["elements"][0]["family"] == "point_scan_preview"

    dataset = np.load(dataset_npz, allow_pickle=True)
    assert dataset["member_ids"].shape[0] >= 1


def test_prepare_midas_binary_decoded_preview_bridge_from_mcvl_hint_preview(tmp_path: Path) -> None:
    inventory_json = tmp_path / "meb_decoded_inventory.json"
    inventory_report = tmp_path / "meb_decoded_inventory_report.json"
    refresh_report = tmp_path / "meb_inventory_refresh_report.json"
    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    bridge_report = out_dir / "bridge_report.json"

    _write_json(
        inventory_json,
        {
            "geometry_preview": {
                "mode": "mcvl_node_hint_preview",
                "projection_label": "XY",
                "source_table": "NODE/ELEM hinted ranges",
                "candidate_points_xy": [
                    [212.0, 212.9],
                    [217.1, -43.0],
                    [-19.0, 173.0],
                    [263.0, 73.0],
                    [284.0, 106.0],
                ],
            },
            "summary": {
                "geometry_preview_point_count": 5,
                "geometry_preview_segment_count": 0,
                "geometry_preview_source_table": "NODE/ELEM hinted ranges",
                "geometry_preview_mode": "mcvl_node_hint_preview",
            },
        },
    )
    _write_json(
        inventory_report,
        {
            "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
            "summary": {
                "geometry_preview_ready": False,
                "geometry_preview_point_count": 5,
                "geometry_preview_segment_count": 0,
                "geometry_preview_source_table": "NODE/ELEM hinted ranges",
                "geometry_preview_mode": "mcvl_node_hint_preview",
            },
        },
    )
    _write_json(
        refresh_report,
        {
            "selected_member_name": "sample_beam.mcb",
            "selected_reason_code": "PASS_TABLE_DIRECTORY_ONLY",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_midas_binary_decoded_preview_bridge.py",
            "--source-id",
            "sample_beam",
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(refresh_report),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(bridge_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(bridge_report.read_text(encoding="utf-8"))
    assert report_payload["contract_pass"] is True
    assert report_payload["summary"]["preview_state_label"] == "unverified hint preview"
    assert report_payload["summary"]["family_assumption"] == "mcvl_hint_preview"
    assert report_payload["summary"]["bridge_mode"] == "point_scan_chain"
    assert report_payload["summary"]["accepted_type_label"].startswith("hint_point_link=")
    assert report_payload["summary"]["preview_basis"] == "mcvl_node_elem_hint"
    assert report_payload["summary"]["preview_projection_label"] == "XY"
    assert report_payload["summary"]["preview_surface_bucket"] == "hint-preview"
    assert report_payload["summary"]["preview_surface_status_label"] == "hint-guided preview-derived 3d candidate"
    assert report_payload["summary"]["preview_readiness_stage_label"] == "hint preview candidate"
    assert report_payload["summary"]["preview_exactness_tier"] == "hint-preview"
    assert report_payload["summary"]["preview_exactness_label"] == "hint-guided preview"
    assert report_payload["summary"]["preview_exactness_signal_source"] == "geometry_preview.mode"

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert model_payload["model"]["metadata"]["preview_state_label"] == "unverified hint preview"
    assert model_payload["model"]["metadata"]["preview_basis"] == "mcvl_node_elem_hint"
    assert model_payload["model"]["metadata"]["preview_surface_bucket"] == "hint-preview"
    assert model_payload["model"]["metadata"]["preview_exactness_tier"] == "hint-preview"
    assert model_payload["model"]["elements"][0]["family"] == "mcvl_hint_preview"


def test_prepare_midas_binary_decoded_preview_bridge_from_table_local_preview(tmp_path: Path) -> None:
    inventory_json = tmp_path / "meb_decoded_inventory.json"
    inventory_report = tmp_path / "meb_decoded_inventory_report.json"
    refresh_report = tmp_path / "meb_inventory_refresh_report.json"
    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    bridge_report = out_dir / "bridge_report.json"

    _write_json(
        inventory_json,
        {
            "geometry_preview": {
                "mode": "table_local_xyz_preview",
                "projection_label": "XY",
                "source_table": "ELEM local offsets",
                "candidate_points_xy": [
                    [0.0, 0.0],
                    [2.5, 0.0],
                    [2.5, 1.25],
                    [0.0, 1.25],
                ],
            },
            "summary": {
                "geometry_preview_point_count": 4,
                "geometry_preview_segment_count": 0,
                "geometry_preview_source_table": "ELEM local offsets",
                "geometry_preview_mode": "table_local_xyz_preview",
            },
        },
    )
    _write_json(
        inventory_report,
        {
            "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
            "summary": {
                "geometry_preview_ready": False,
                "geometry_preview_point_count": 4,
                "geometry_preview_segment_count": 0,
                "geometry_preview_source_table": "ELEM local offsets",
                "geometry_preview_mode": "table_local_xyz_preview",
            },
        },
    )
    _write_json(
        refresh_report,
        {
            "selected_member_name": "sample_table_local.meb",
            "selected_reason_code": "PASS_TABLE_DIRECTORY_ONLY",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_midas_binary_decoded_preview_bridge.py",
            "--source-id",
            "sample_table_local",
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(refresh_report),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(bridge_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(bridge_report.read_text(encoding="utf-8"))
    assert report_payload["contract_pass"] is True
    assert report_payload["summary"]["preview_state_label"] == "unverified table-local preview"
    assert report_payload["summary"]["family_assumption"] == "table_local_preview"
    assert report_payload["summary"]["bridge_mode"] == "table_local_point_chain"
    assert report_payload["summary"]["accepted_type_label"].startswith("table_point_link=")
    assert report_payload["summary"]["source_table"] == "ELEM local offsets"
    assert report_payload["summary"]["preview_basis"] == "table_local_payload"
    assert report_payload["summary"]["preview_projection_label"] == "XY"
    assert report_payload["summary"]["preview_exactness_tier"] == "table-local-preview"
    assert report_payload["summary"]["preview_exactness_label"] == "table-local preview"
    assert report_payload["summary"]["preview_exactness_signal_source"] == "geometry_preview.mode"

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert model_payload["model"]["metadata"]["preview_state_label"] == "unverified table-local preview"
    assert model_payload["model"]["metadata"]["preview_basis"] == "table_local_payload"
    assert model_payload["model"]["metadata"]["bridge_mode"] == "table_local_point_chain"
    assert model_payload["model"]["metadata"]["preview_exactness_tier"] == "table-local-preview"
    assert model_payload["model"]["elements"][0]["family"] == "table_local_preview"

    dataset = np.load(dataset_npz, allow_pickle=True)
    assert dataset["member_ids"].shape[0] >= 1


def test_prepare_midas_binary_decoded_preview_bridge_from_ascii_table_local_preview(tmp_path: Path) -> None:
    inventory_json = tmp_path / "meb_decoded_inventory.json"
    inventory_report = tmp_path / "meb_decoded_inventory_report.json"
    refresh_report = tmp_path / "meb_inventory_refresh_report.json"
    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    bridge_report = out_dir / "bridge_report.json"

    _write_json(
        inventory_json,
        {
            "geometry_preview": {
                "mode": "table_local_ascii_preview",
                "projection_label": "XY",
                "source_table": "ASCII:*POINT/*MEMBER_ADD",
                "anchor_table_names": ["*POINT", "*MEMBER_ADD"],
                "candidate_segments_xy": [
                    {"x1": 0.0, "y1": 0.0, "x2": 4.0, "y2": 0.0},
                    {"x1": 4.0, "y1": 0.0, "x2": 4.0, "y2": 3.0},
                    {"x1": 4.0, "y1": 3.0, "x2": 0.0, "y2": 3.0},
                    {"x1": 0.0, "y1": 3.0, "x2": 0.0, "y2": 0.0},
                ],
                "candidate_points_xy": [
                    [0.0, 0.0],
                    [4.0, 0.0],
                    [4.0, 3.0],
                    [0.0, 3.0],
                ],
                "topology_preview_ready": True,
                "topology_readiness_label": "topology-grounded member-add preview",
                "missing_member_path_count": 0,
                "missing_member_reference_count": 0,
            },
            "summary": {
                "geometry_preview_point_count": 4,
                "geometry_preview_segment_count": 4,
                "geometry_preview_source_table": "ASCII:*POINT/*MEMBER_ADD",
                "geometry_preview_mode": "table_local_ascii_preview",
                "topology_preview_ready": True,
                "topology_readiness_label": "topology-grounded member-add preview",
                "missing_member_path_count": 0,
                "missing_member_reference_count": 0,
            },
        },
    )
    _write_json(
        inventory_report,
        {
            "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
            "summary": {
                "geometry_preview_ready": False,
                "geometry_preview_point_count": 4,
                "geometry_preview_segment_count": 4,
                "geometry_preview_source_table": "ASCII:*POINT/*MEMBER_ADD",
                "geometry_preview_mode": "table_local_ascii_preview",
                "topology_preview_ready": True,
                "topology_readiness_label": "topology-grounded member-add preview",
                "missing_member_path_count": 0,
                "missing_member_reference_count": 0,
            },
        },
    )
    _write_json(
        refresh_report,
        {
            "selected_member_name": "sample_ascii_table_local.mmbx",
            "selected_reason_code": "PASS_TABLE_DIRECTORY_ONLY",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_midas_binary_decoded_preview_bridge.py",
            "--source-id",
            "sample_ascii_table_local",
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(refresh_report),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(bridge_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(bridge_report.read_text(encoding="utf-8"))
    assert report_payload["summary"]["preview_state_label"] == "unverified table-local preview"
    assert report_payload["summary"]["preview_basis"] == "embedded_ascii_point_member"
    assert report_payload["summary"]["preview_projection_label"] == "XY"
    assert report_payload["summary"]["preview_anchor_table_names"] == ["*POINT", "*MEMBER_ADD"]
    assert report_payload["summary"]["bridge_mode"] == "table_local_segment_preview"
    assert report_payload["summary"]["accepted_type_label"] == "table_segment=4"
    assert report_payload["summary"]["source_table"] == "ASCII:*POINT/*MEMBER_ADD"
    assert report_payload["summary"]["preview_surface_status_label"] == "topology-grounded preview-derived 3d candidate"
    assert report_payload["summary"]["preview_readiness_stage_label"] == "topology-grounded preview candidate"
    assert report_payload["summary"]["topology_preview_ready"] is True
    assert report_payload["summary"]["topology_readiness_label"] == "topology-grounded member-add preview"
    assert report_payload["summary"]["missing_member_path_count"] == 0
    assert report_payload["summary"]["missing_member_reference_count"] == 0
    assert report_payload["summary"]["preview_exactness_tier"] == "topology-grounded"
    assert report_payload["summary"]["preview_exactness_label"] == "topology-grounded preview"

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert model_payload["model"]["metadata"]["preview_basis"] == "embedded_ascii_point_member"
    assert model_payload["model"]["metadata"]["preview_anchor_table_names"] == ["*POINT", "*MEMBER_ADD"]
    assert model_payload["model"]["metadata"]["bridge_mode"] == "table_local_segment_preview"
    assert model_payload["model"]["metadata"]["preview_surface_status_label"] == "topology-grounded preview-derived 3d candidate"
    assert model_payload["model"]["metadata"]["preview_readiness_stage_label"] == "topology-grounded preview candidate"
    assert model_payload["model"]["metadata"]["topology_preview_ready"] is True
    assert model_payload["model"]["metadata"]["topology_readiness_label"] == "topology-grounded member-add preview"
    assert model_payload["model"]["metadata"]["preview_exactness_tier"] == "topology-grounded"


def test_prepare_midas_binary_decoded_preview_bridge_propagates_summary_probe_exactness(tmp_path: Path) -> None:
    inventory_json = tmp_path / "meb_decoded_inventory.json"
    inventory_report = tmp_path / "meb_decoded_inventory_report.json"
    refresh_report = tmp_path / "meb_inventory_refresh_report.json"
    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    bridge_report = out_dir / "bridge_report.json"

    _write_json(
        inventory_json,
        {
            "geometry_preview": {
                "mode": "table_local_ascii_preview",
                "projection_label": "XY",
                "source_table": "ASCII:*POINT/*MEMBER_ADD",
                "anchor_table_names": ["*POINT", "*MEMBER_ADD"],
                "candidate_segments_xy": [
                    {"x1": 0.0, "y1": 0.0, "x2": 4.0, "y2": 0.0},
                    {"x1": 4.0, "y1": 0.0, "x2": 4.0, "y2": 3.0},
                    {"x1": 4.0, "y1": 3.0, "x2": 0.0, "y2": 3.0},
                    {"x1": 0.0, "y1": 3.0, "x2": 0.0, "y2": 0.0},
                ],
                "candidate_points_xy": [
                    [0.0, 0.0],
                    [4.0, 0.0],
                    [4.0, 3.0],
                    [0.0, 3.0],
                ],
            },
            "summary": {
                "geometry_preview_point_count": 4,
                "geometry_preview_segment_count": 4,
                "geometry_preview_source_table": "ASCII:*POINT/*MEMBER_ADD",
                "geometry_preview_mode": "table_local_ascii_preview",
                "topology_preview_ready": True,
                "table_local_preview_probe": {
                    "topology_grounding_label": "explicit_member_add_paths",
                    "topology_preview_ready": True,
                    "topology_readiness_label": "topology-grounded member-add preview",
                    "topology_node_count": 4,
                    "topology_edge_count": 4,
                    "topology_component_count": 1,
                    "member_path_count": 1,
                    "resolved_member_path_count": 1,
                    "member_path_resolution_rate": 1.0,
                    "member_reference_count": 4,
                    "resolved_member_reference_count": 4,
                    "member_reference_resolution_rate": 1.0,
                    "missing_member_path_count": 0,
                    "missing_member_reference_count": 0,
                    "resolved_member_path_samples": [[101, 102, 103, 104]],
                    "exact_topology_candidate": True,
                    "exact_topology_promoted": False,
                },
            },
        },
    )
    _write_json(
        inventory_report,
        {
            "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
            "summary": {
                "geometry_preview_ready": False,
                "geometry_preview_point_count": 4,
                "geometry_preview_segment_count": 4,
                "geometry_preview_source_table": "ASCII:*POINT/*MEMBER_ADD",
                "geometry_preview_mode": "table_local_ascii_preview",
            },
        },
    )
    _write_json(
        refresh_report,
        {
            "selected_member_name": "sample_summary_probe.mmbx",
            "selected_reason_code": "PASS_TABLE_DIRECTORY_ONLY",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_midas_binary_decoded_preview_bridge.py",
            "--source-id",
            "sample_summary_probe",
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(refresh_report),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(bridge_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(bridge_report.read_text(encoding="utf-8"))
    assert report_payload["summary"]["topology_preview_ready"] is True
    assert report_payload["summary"]["exact_topology_candidate"] is True
    assert report_payload["summary"]["exact_topology_promoted"] is False
    assert report_payload["summary"]["topology_grounding_label"] == "explicit_member_add_paths"
    assert report_payload["summary"]["topology_readiness_label"] == "topology-grounded member-add preview"
    assert report_payload["summary"]["resolved_member_path_samples"] == [[101, 102, 103, 104]]
    assert report_payload["summary"]["preview_surface_status_label"] == "exact recovered topology-derived 3d candidate"
    assert report_payload["summary"]["preview_readiness_stage_label"] == "exact recovered topology candidate"
    assert report_payload["summary"]["preview_exactness_tier"] == "exact-topology-candidate"
    assert report_payload["summary"]["preview_exactness_label"] == "exact topology candidate"
    assert report_payload["summary"]["preview_exactness_signal_source"] == "inventory_summary.table_local_preview_probe"
    assert report_payload["summary"]["topology_signal_field_sources"]["exact_topology_candidate"] == "inventory_summary.table_local_preview_probe"
    assert report_payload["summary"]["topology_signal_field_sources"]["topology_preview_ready"] == "inventory_summary"

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    metadata = model_payload["model"]["metadata"]
    assert metadata["exact_topology_candidate"] is True
    assert metadata["exact_topology_promoted"] is False
    assert metadata["preview_exactness_tier"] == "exact-topology-candidate"
    assert metadata["preview_exactness_signal_source"] == "inventory_summary.table_local_preview_probe"
    assert metadata["topology_signal_field_sources"]["exact_topology_candidate"] == "inventory_summary.table_local_preview_probe"
