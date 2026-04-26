from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_source_contract(tmp_path: Path, source_kind: str, source_payload: dict) -> Path:
    source_artifact = tmp_path / f"{source_kind}.source.json"
    _write_json(source_artifact, source_payload)
    out = tmp_path / f"{source_kind}.contract.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_contract.py",
            "--source-kind",
            source_kind,
            "--source-artifact",
            str(source_artifact),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return out


def test_panel_zone_clash_artifact_produces_low_constructability_candidates(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 12, "group_count": 5},
            "rows_head": [
                {
                    "member_id": "B101",
                    "member_type": "beam",
                    "constructability_score": 0.12,
                    "anchorage_complexity": 0.73,
                    "detailing_violation_ratio": 0.56,
                },
                {
                    "member_id": "B102",
                    "member_type": "beam",
                    "constructability_score": 0.36,
                    "anchorage_complexity": 0.21,
                    "detailing_violation_ratio": 0.10,
                },
            ],
        },
    )
    out = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
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
    assert payload["summary"]["artifact_mode"] == "constructability_proxy_candidate_scan"
    assert payload["summary"]["low_constructability_row_count"] == 1
    assert payload["artifacts"]["interference_row_count"] == 1
    assert payload["artifacts"]["interference_rows_head"][0]["member_id"] == "B101"
    assert payload["checks"]["proxy_only"] is True


def test_panel_zone_clash_artifact_scans_full_dataset_npz_not_rows_head(tmp_path: Path) -> None:
    report = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        report,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "H001",
                    "member_type": "beam",
                    "constructability_score": 0.41,
                    "anchorage_complexity": 0.12,
                    "detailing_violation_ratio": 0.08,
                }
            ],
        },
    )
    npz_path = tmp_path / "design_optimization_dataset.npz"
    np.savez(
        npz_path,
        member_ids=np.asarray(["A001", "A002", "A003", "A004"], dtype=object),
        member_types=np.asarray(["beam", "beam", "column", "wall"], dtype=object),
        group_ids=np.asarray(["G1", "G2", "G3", "G4"], dtype=object),
        section_signatures=np.asarray(["S1", "S2", "S3", "S4"], dtype=object),
        constructability_score=np.asarray([0.31, 0.18, 0.44, 0.12], dtype=np.float64),
        anchorage_complexity=np.asarray([0.10, 0.71, 0.22, 0.83], dtype=np.float64),
        detailing_violation_ratio=np.asarray([0.07, 0.61, 0.15, 0.64], dtype=np.float64),
    )
    out = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(report),
            "--design-optimization-npz",
            str(npz_path),
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
    assert payload["summary"]["artifact_mode"] == "constructability_proxy_candidate_scan"
    assert payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert payload["summary"]["low_constructability_row_count"] == 2
    assert payload["artifacts"]["interference_row_count"] == 2
    assert {row["member_id"] for row in payload["artifacts"]["interference_rows_head"]} == {"A002", "A004"}
    assert payload["source_provenance"]["input_kind"] == "npz_full"
    assert payload["source_provenance"]["topology_capable_input"] is True
    assert payload["source_provenance"]["true_3d_clash_verified"] is False
    assert payload["source_provenance"]["missing_required_sources"] == [
        "panel_zone_joint_geometry_3d",
        "panel_zone_rebar_anchorage_3d",
        "panel_zone_clash_verification_3d",
    ]
    assert payload["summary"]["source_contract_mode"] == "topology_capable_proxy_scan"


def test_panel_zone_clash_artifact_upgrades_to_true_3d_when_all_required_sources_are_valid(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 6, "group_count": 3},
            "rows_head": [
                {
                    "member_id": "B201",
                    "member_type": "beam",
                    "constructability_score": 0.16,
                    "anchorage_complexity": 0.72,
                    "detailing_violation_ratio": 0.61,
                }
            ],
        },
    )
    joint = _generate_source_contract(
        tmp_path,
        "joint_geometry",
        {"contract_pass": True, "source_kind": "panel_zone_joint_geometry_3d"},
    )
    anchorage = _generate_source_contract(
        tmp_path,
        "rebar_anchorage",
        {"contract_pass": True, "source_kind": "panel_zone_rebar_anchorage_3d"},
    )
    clash_verification = _generate_source_contract(
        tmp_path,
        "clash_verification",
        {"contract_pass": True, "source_kind": "panel_zone_clash_verification_3d"},
    )
    out = tmp_path / "panel_zone_clash_artifact.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification),
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
    assert payload["summary"]["verification_tier"] == "true_3d_clash_and_anchorage_verified"
    assert payload["summary"]["source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert payload["source_provenance"]["required_sources_complete"] is True
    assert payload["source_provenance"]["missing_required_sources"] == []
    assert payload["source_provenance"]["true_3d_clash_verified"] is True
    assert payload["source_provenance"]["true_3d_anchorage_verified"] is True


def test_panel_zone_clash_artifact_preserves_member_mapping_sidecar_surface(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 6, "group_count": 3},
            "rows_head": [
                {
                    "member_id": "B203",
                    "member_type": "beam",
                    "constructability_score": 0.13,
                    "anchorage_complexity": 0.69,
                    "detailing_violation_ratio": 0.57,
                }
            ],
        },
    )
    joint = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_verification = tmp_path / "panel_zone_clash_verification_3d.json"
    for path, source_kind in (
        (joint, "panel_zone_joint_geometry_3d"),
        (anchorage, "panel_zone_rebar_anchorage_3d"),
        (clash_verification, "panel_zone_clash_verification_3d"),
    ):
        _write_json(
            path,
            {
                "contract_pass": True,
                "source_kind": source_kind,
                "summary": {
                    "verification_tier": f"{source_kind}_solver_verified_validated_source",
                },
                "source_provenance": {
                    "source_kind": source_kind,
                    "solver_verified": True,
                    "member_mapping_sidecar_present": True,
                    "member_mapping_sidecar_path": "/tmp/member_mapping_sidecar.json",
                    "member_mapping_sidecar_mode": "explicit_member_id_map",
                    "member_mapping_sidecar_row_count": 1,
                    "member_mapping_sidecar_applied_row_count": 1,
                    "member_mapping_sidecar_unmapped_source_member_count": 0,
                },
            },
        )
    out = tmp_path / "panel_zone_clash_artifact.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source_provenance"]["member_mapping_sidecar_present"] is True
    assert payload["source_provenance"]["member_mapping_sidecar_mode"] == "explicit_member_id_map"
    assert payload["source_provenance"]["member_mapping_sidecar_row_count"] == 1
    assert payload["source_provenance"]["member_mapping_sidecar_applied_row_count"] == 1
    assert payload["summary"]["member_mapping_sidecar_present"] is True
    assert payload["summary"]["member_mapping_sidecar_mode"] == "explicit_member_id_map"
    assert payload["summary"]["member_mapping_sidecar_row_count"] == 1
    assert payload["summary"]["member_mapping_sidecar_applied_row_count"] == 1
    assert (
        payload["source_provenance"]["source_member_mapping_sidecar_present"]["panel_zone_joint_geometry_3d"]
        is True
    )


def test_panel_zone_clash_artifact_rejects_mislabeled_3d_source_contract(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 6, "group_count": 3},
            "rows_head": [
                {
                    "member_id": "B202",
                    "member_type": "beam",
                    "constructability_score": 0.14,
                    "anchorage_complexity": 0.71,
                    "detailing_violation_ratio": 0.58,
                }
            ],
        },
    )
    joint = tmp_path / "panel_zone_joint_geometry_3d.json"
    anchorage = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_verification = tmp_path / "panel_zone_clash_verification_3d.json"
    _write_json(joint, {"contract_pass": True, "source_kind": "panel_zone_joint_geometry_3d"})
    _write_json(anchorage, {"contract_pass": True, "source_kind": "panel_zone_rebar_anchorage_3d"})
    _write_json(clash_verification, {"contract_pass": True, "source_kind": "panel_zone_rebar_anchorage_3d"})
    out = tmp_path / "panel_zone_clash_artifact.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification),
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
    assert payload["summary"]["verification_tier"] == "topology_capable_proxy_scan"
    assert payload["source_provenance"]["required_sources_complete"] is False
    assert "panel_zone_clash_verification_3d" in payload["source_provenance"]["missing_required_sources"]


def test_panel_zone_clash_artifact_aggregates_upstream_source_coverage_from_contracts(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 8, "group_count": 4},
            "rows_head": [
                {
                    "member_id": "B401",
                    "member_type": "beam",
                    "constructability_score": 0.12,
                    "anchorage_complexity": 0.74,
                    "detailing_violation_ratio": 0.63,
                }
            ],
        },
    )
    joint = _generate_source_contract(
        tmp_path,
        "joint_geometry",
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "source_provenance": {
                "source_row_count": 2,
                "valid_source_row_count": 2,
                "invalid_source_row_count": 0,
                "candidate_member_count": 1,
                "overlap_member_count": 1,
                "candidate_scan_mode": "npz_full",
                "topology_capable_input": True,
                "source_input_path": "joint_geometry_source.json",
            },
        },
    )
    anchorage = _generate_source_contract(
        tmp_path,
        "rebar_anchorage",
        {
            "contract_pass": True,
            "source_kind": "panel_zone_rebar_anchorage_3d",
            "source_provenance": {
                "source_row_count": 1,
                "valid_source_row_count": 1,
                "invalid_source_row_count": 0,
                "candidate_member_count": 1,
                "overlap_member_count": 1,
                "candidate_scan_mode": "npz_full",
                "topology_capable_input": True,
                "source_input_path": "rebar_anchorage_source.json",
            },
        },
    )
    clash_verification = _generate_source_contract(
        tmp_path,
        "clash_verification",
        {
            "contract_pass": True,
            "source_kind": "panel_zone_clash_verification_3d",
            "source_provenance": {
                "source_row_count": 3,
                "valid_source_row_count": 2,
                "invalid_source_row_count": 1,
                "candidate_member_count": 1,
                "overlap_member_count": 1,
                "candidate_scan_mode": "npz_full",
                "topology_capable_input": True,
                "source_input_path": "clash_verification_source.json",
            },
        },
    )
    out = tmp_path / "panel_zone_clash_artifact.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification),
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
    assert payload["summary"]["validated_source_row_count_total"] == 5
    assert payload["summary"]["validated_source_overlap_member_count_min"] == 1
    assert payload["source_provenance"]["source_valid_row_counts"] == {
        "panel_zone_joint_geometry_3d": 2,
        "panel_zone_rebar_anchorage_3d": 1,
        "panel_zone_clash_verification_3d": 2,
    }
    assert payload["source_provenance"]["source_overlap_member_counts"] == {
        "panel_zone_joint_geometry_3d": 1,
        "panel_zone_rebar_anchorage_3d": 1,
        "panel_zone_clash_verification_3d": 1,
    }
    assert payload["source_provenance"]["source_candidate_scan_modes"] == {
        "panel_zone_joint_geometry_3d": "npz_full",
        "panel_zone_rebar_anchorage_3d": "npz_full",
        "panel_zone_clash_verification_3d": "npz_full",
    }
    assert payload["source_provenance"]["source_input_paths"] == {
        "panel_zone_joint_geometry_3d": "joint_geometry_source.json",
        "panel_zone_rebar_anchorage_3d": "rebar_anchorage_source.json",
        "panel_zone_clash_verification_3d": "clash_verification_source.json",
    }
    assert payload["source_provenance"]["source_artifacts"]["panel_zone_joint_geometry_3d"]["valid_source_row_count"] == 2
    assert payload["source_provenance"]["source_artifacts"]["panel_zone_clash_verification_3d"]["invalid_source_row_count"] == 1
