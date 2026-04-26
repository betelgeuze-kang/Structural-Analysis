from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_npz(path: Path, *, member_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        member_ids=np.asarray([member_id], dtype=object),
        member_types=np.asarray(["beam"], dtype=object),
        section_signatures=np.asarray(["SB800X400"], dtype=object),
        constructability_score=np.asarray([0.12], dtype=np.float64),
    )


def _synthetic_midas_model(member_id: str) -> dict:
    return {
        "model": {
            "nodes": [
                {"id": 10, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 11, "x": 4.5, "y": 0.0, "z": 0.0},
                {"id": 12, "x": 0.0, "y": 0.0, "z": 3.2},
            ],
            "elements": [
                {"id": int(member_id), "type": "BEAM", "family": "beam", "node_ids": [10, 11], "section_id": 20, "material_id": 1},
                {"id": 901, "type": "BEAM", "family": "beam", "node_ids": [10, 12], "section_id": 20, "material_id": 1},
            ],
            "sections": [
                {
                    "id": 20,
                    "name": "DBUSER",
                    "raw_tokens": ["SB800X4002.00", "CC", "0", "0", "0", "0", "0", "0", "YES", "NO", "SB", "2", "0.8", "0.4"],
                }
            ],
        }
    }


def test_panel_zone_solver_export_bundle_builds_topology_projected_rows(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    npz_path = tmp_path / "design_optimization_dataset.npz"
    midas_json = tmp_path / "midas_model.json"
    out = tmp_path / "panel_zone_solver_export_bundle.json"
    member_id = "900"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 1, "group_count": 1},
            "rows_head": [
                {
                    "member_id": member_id,
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.12,
                    "section_signature": "SB800X400",
                }
            ],
        },
    )
    _write_npz(npz_path, member_id=member_id)
    _write_json(midas_json, _synthetic_midas_model(member_id))

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_export_bundle.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(npz_path),
            "--midas-json",
            str(midas_json),
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
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["producer_backend"] == "midas_topology_projection"
    assert payload["summary"]["topology_projected"] is True
    assert payload["summary"]["solver_verified"] is False
    assert payload["summary"]["matched_candidate_member_count"] == 1
    assert payload["panel_zone_3d_results"]["panel_zone_joint_geometry_3d"]["rows"][0]["member_id"] == member_id
    assert payload["panel_zone_3d_results"]["panel_zone_rebar_anchorage_3d"]["rows"][0]["member_id"] == member_id
    assert payload["panel_zone_3d_results"]["panel_zone_clash_verification_3d"]["rows"][0]["member_id"] == member_id


def test_panel_zone_source_artifact_propagates_topology_projected_metadata_from_bundle(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    npz_path = tmp_path / "design_optimization_dataset.npz"
    midas_json = tmp_path / "midas_model.json"
    bundle = tmp_path / "panel_zone_solver_export_bundle.json"
    source_out = tmp_path / "panel_zone_joint_geometry_3d.json"
    member_id = "900"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 1, "group_count": 1},
            "rows_head": [
                {
                    "member_id": member_id,
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.12,
                    "section_signature": "SB800X400",
                }
            ],
        },
    )
    _write_npz(npz_path, member_id=member_id)
    _write_json(midas_json, _synthetic_midas_model(member_id))

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_export_bundle.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(npz_path),
            "--midas-json",
            str(midas_json),
            "--out",
            str(bundle),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_joint_geometry_3d_source.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(npz_path),
            "--source-input",
            str(bundle),
            "--out",
            str(source_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(source_out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["producer_backend"] == "midas_topology_projection"
    assert payload["summary"]["topology_projected"] is True
    assert payload["summary"]["solver_verified"] is False
    assert payload["source_provenance"]["producer_backend"] == "midas_topology_projection"
    assert payload["source_provenance"]["topology_projected"] is True
    assert payload["source_provenance"]["solver_verified"] is False


def test_panel_zone_solver_export_bundle_summarizes_instruction_sidecar_overlap(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    npz_path = tmp_path / "design_optimization_dataset.npz"
    midas_json = tmp_path / "midas_model.json"
    sidecar_json = tmp_path / "midas_model.optimized.instruction_sidecar.json"
    export_report_json = tmp_path / "midas_model.optimized.export_report.json"
    out = tmp_path / "panel_zone_solver_export_bundle.json"
    member_id = "900"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 1, "group_count": 1},
            "rows_head": [
                {
                    "member_id": member_id,
                    "member_type": "beam",
                    "group_id": "S04:transfer:nogroup:beam:SB800X400",
                    "constructability_score": 0.12,
                    "section_signature": "SB800X400",
                }
            ],
        },
    )
    _write_npz(npz_path, member_id=member_id)
    _write_json(midas_json, _synthetic_midas_model(member_id))
    _write_json(
        sidecar_json,
        {
            "schema_version": "1.0",
            "instruction_sidecar_rows": [
                {
                    "group_id": "S04:transfer:nogroup:beam:SB800X400",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_manual_update",
                }
            ],
            "summary": {
                "instruction_sidecar_change_count": 1,
                "instruction_sidecar_action_family_counts": {"connection_detailing": 1},
                "instruction_sidecar_followup_type_counts": {"connection_detailing_manual_update": 1},
                "instruction_sidecar_review_priority_counts": {"high": 1},
                "evidence_model": "instruction_sidecar_only",
                "rebar_delivery_mode": "group_local_sidecar",
            },
        },
    )
    _write_json(export_report_json, {"summary": {"instruction_sidecar_change_count": 1}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_export_bundle.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(npz_path),
            "--midas-json",
            str(midas_json),
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
    assert summary["instruction_sidecar_present"] is True
    assert summary["instruction_sidecar_change_count"] == 1
    assert summary["instruction_sidecar_candidate_overlap_mode"] == "section_signature"
    assert summary["instruction_sidecar_overlap_row_count"] == 1
    assert summary["instruction_sidecar_overlap_member_count"] == 1
    assert summary["instruction_sidecar_overlap_group_count"] == 1
