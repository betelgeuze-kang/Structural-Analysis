from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_pbd_hinge_refresh_source_projects_rows_from_group_index_scope(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    dataset_npz = tmp_path / "design_opt_dataset.npz"
    changes = tmp_path / "changes.json"
    out = tmp_path / "hinge_refresh_source.json"
    _write_json(dataset, {"contract_pass": True, "summary": {"member_count": 3}})
    np.savez(
        dataset_npz,
        member_ids=np.asarray(["B101", "C101", "W901"], dtype=object),
        group_ids=np.asarray(["G_BEAM", "G_COL", "G_WALL"], dtype=object),
        group_index_per_member=np.asarray([7, 8, 9], dtype=np.int32),
        member_types=np.asarray(["beam", "column", "wall"], dtype=object),
        member_plastic_rotation_rad=np.asarray([0.008, 0.006, 0.004], dtype=np.float64),
        member_governing_dcr=np.asarray([0.82, 1.10, 0.65], dtype=np.float64),
        rebar_ratio=np.asarray([0.018, 0.074, 0.010], dtype=np.float64),
        member_hinge_state_source=np.asarray(["proxy", "proxy", "proxy"], dtype=object),
    )
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": "IGNORED_GROUP_NAME",
                    "group_index": 7,
                    "member_type": "beam",
                    "action_family": "rebar",
                    "before_rebar_ratio": 0.018,
                    "after_rebar_ratio": 0.012,
                },
                {
                    "group_id": "G_WALL",
                    "group_index": 9,
                    "member_type": "wall",
                    "action_family": "wall_thickness",
                    "before_rebar_ratio": 0.010,
                    "after_rebar_ratio": 0.010,
                },
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_source.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(dataset_npz),
            "--cost-reduction-changes",
            str(changes),
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
    assert payload["source_kind"] == "hinge_refresh_projected_from_optimization_changes"
    assert payload["source_provenance"]["group_index_match_count"] == 2
    assert payload["source_provenance"]["group_id_fallback_match_count"] == 0
    assert payload["summary"]["hinge_refresh_row_count"] == 2
    assert payload["summary"]["unique_member_count"] == 2
    assert payload["summary"]["rebar_sensitive_member_count"] == 1
    rows = payload["hinge_refresh_rows"]
    beam_row = next(row for row in rows if row["member_id"] == "B101")
    wall_row = next(row for row in rows if row["member_id"] == "W901")
    assert beam_row["rebar_sensitive"] is True
    assert beam_row["recomputed_from_rebar"] is True
    assert beam_row["source_projection_match_mode"] == "group_index"
    assert 0.0 < beam_row["yield_rotation"] < beam_row["ultimate_rotation"]
    assert wall_row["source_projection_match_mode"] == "group_index"
    assert "rebar_sensitive" not in wall_row


def test_pbd_hinge_refresh_source_feeds_artifact_and_report_positive_path(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    dataset_npz = tmp_path / "design_opt_dataset.npz"
    changes = tmp_path / "changes.json"
    source = tmp_path / "hinge_refresh_source.json"
    artifact = tmp_path / "hinge_refresh_artifact.json"
    report = tmp_path / "hinge_refresh_report.json"
    pbd = tmp_path / "pbd.json"
    midas = tmp_path / "midas.json"
    ndtha = tmp_path / "ndtha.json"

    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 3},
            "rows_head": [
                {"member_id": "B101", "member_type": "beam"},
                {"member_id": "C101", "member_type": "column"},
            ],
        },
    )
    np.savez(
        dataset_npz,
        member_ids=np.asarray(["B101", "C101", "W901"], dtype=object),
        group_ids=np.asarray(["G_BEAM", "G_COL", "G_WALL"], dtype=object),
        group_index_per_member=np.asarray([7, 8, 9], dtype=np.int32),
        member_types=np.asarray(["beam", "column", "wall"], dtype=object),
        member_plastic_rotation_rad=np.asarray([0.008, 0.006, 0.004], dtype=np.float64),
        member_governing_dcr=np.asarray([0.82, 1.10, 0.65], dtype=np.float64),
        rebar_ratio=np.asarray([0.018, 0.074, 0.010], dtype=np.float64),
        member_hinge_state_source=np.asarray(["proxy", "proxy", "proxy"], dtype=object),
    )
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": "G_BEAM",
                    "group_index": 7,
                    "member_type": "beam",
                    "action_family": "rebar",
                    "before_rebar_ratio": 0.018,
                    "after_rebar_ratio": 0.012,
                }
            ]
        },
    )
    _write_json(pbd, {"contract_pass": True, "metrics": {"drift_split_counts": {"test": 3}}})
    _write_json(midas, {"contract_pass": True})
    _write_json(ndtha, {"contract_pass": True})

    for cmd in (
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_source.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(dataset_npz),
            "--cost-reduction-changes",
            str(changes),
            "--out",
            str(source),
        ],
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(dataset_npz),
            "--cost-reduction-changes",
            str(changes),
            "--source-input",
            str(source),
            "--out",
            str(artifact),
        ],
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--midas-conversion",
            str(midas),
            "--ndtha-stress-report",
            str(ndtha),
            "--hinge-refresh-artifact",
            str(artifact),
            "--out",
            str(report),
        ],
    ):
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    assert artifact_payload["contract_pass"] is True
    assert artifact_payload["summary"]["source_artifact_kind"] == "hinge_refresh_projected_from_optimization_changes"
    assert artifact_payload["summary"]["candidate_scope_mode"] == "optimized_groups_from_npz"
    assert artifact_payload["summary"]["overlap_member_count"] == 1
    assert artifact_payload["summary"]["rebar_sensitive_member_count"] == 1
    assert report_payload["contract_pass"] is True
    assert report_payload["reason_code"] == "PASS"
    assert report_payload["summary"]["hinge_state_mode"] == "computed_member_local_hinge_refresh"
    assert report_payload["summary"]["hinge_refresh_artifact_kind"] == "hinge_refresh_projected_from_optimization_changes"
    assert report_payload["summary"]["hinge_refresh_source_mode"] == "rebar_sensitive_member_local_refresh"
    assert report_payload["summary"]["hinge_refresh_overlap_member_count"] == 1
    assert report_payload["summary"]["hinge_refresh_rebar_sensitive_member_count"] == 1
