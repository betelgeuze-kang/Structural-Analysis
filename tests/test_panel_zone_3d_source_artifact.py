from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"
VECTOR_GEOMETRY_KEYS = (
    "beam_axis_segment_m",
    "column_axis_segment_m",
    "column_rebar_segments_m",
    "beam_rebar_segments_m",
    "hoop_loops_m",
    "clash_points_m",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _assert_vector_geometry_keys(row: dict, *, clash_points: int | None = None) -> None:
    for key in VECTOR_GEOMETRY_KEYS:
        assert key in row
    assert row["beam_axis_segment_m"]["start_m"]["x"] < row["beam_axis_segment_m"]["end_m"]["x"]
    assert row["column_axis_segment_m"]["start_m"]["z"] < row["column_axis_segment_m"]["end_m"]["z"]
    assert len(row["column_rebar_segments_m"]) == 4
    assert len(row["beam_rebar_segments_m"]) == 4
    assert len(row["hoop_loops_m"]) == 3
    if clash_points is not None:
        assert len(row["clash_points_m"]) == clash_points


def _source_rows_for_kind(source_kind: str, member_id: str) -> list[dict]:
    if source_kind == "joint_geometry":
        return [{"member_id": member_id, "joint_id": "J-1"}]
    if source_kind == "rebar_anchorage":
        return [
            {
                "member_id": member_id,
                "available_anchorage_length_mm": 480.0,
                "required_anchorage_length_mm": 420.0,
            }
        ]
    if source_kind == "clash_verification":
        return [{"member_id": member_id, "clash_count": 0, "clearance_mm": 28.0}]
    raise ValueError(source_kind)


def _write_topology_report(source_dir: Path) -> Path:
    edges_path = source_dir / "opensees_edges.json"
    topology_path = source_dir / "opensees_topology_report.json"
    _write_json(
        edges_path,
        {
            "schema_version": "1.0",
            "node_count": 8,
            "edges": [[0, 1], [0, 2], [0, 3], [4, 5], [4, 6], [4, 7]],
            "source": "tests/opensees/mock_model.tcl",
        },
    )
    _write_json(
        topology_path,
        {
            "schema_version": "1.0",
            "run_id": "phase3-opensees-topology-parser",
            "artifacts": {"edges_json": str(edges_path)},
            "checks": {
                "real_topology_pass": True,
                "shell_beam_mix_pass": True,
            },
            "metrics": {
                "node_count": 8,
                "edge_count_undirected": 6,
                "mean_degree": 1.5,
                "max_degree": 3,
            },
            "contract_pass": True,
        },
    )
    return topology_path


def _write_phase3_pipeline_report(source_dir: Path, topology_report: Path) -> Path:
    pipeline_path = source_dir / "phase3_megastructure_pipeline_report.json"
    _write_json(
        pipeline_path,
        {
            "schema_version": "1.0",
            "run_id": "phase3-megastructure-open-pipeline",
            "reports": {"topology": str(topology_report)},
            "checks": {"topology_gate_pass": True},
            "contract_pass": True,
        },
    )
    return pipeline_path


def test_panel_zone_3d_source_artifact_marks_open_when_source_input_is_missing(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B301",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.12,
                    "section_signature": "SB-01",
                }
            ],
        },
    )
    out = tmp_path / "panel_zone_joint_geometry_3d.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            "joint_geometry",
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
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_INPUT_MISSING"
    assert payload["summary"]["candidate_member_count"] == 1
    assert payload["summary"]["source_status"] == "open"
    assert payload["checks"]["candidate_members_present"] is True
    assert payload["checks"]["source_input_present"] is False


def test_panel_zone_3d_source_artifact_emits_vector_geometry_when_centroid_exists(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "joint_geometry_source.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B401",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-41",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "rows": [
                {
                    "member_id": "B401",
                    "joint_id": "J-401",
                    "joint_centroid_m": {"x": 10.0, "y": 20.0, "z": 3.5},
                    "beam_length_mm": 4800.0,
                    "section_depth_mm": 800.0,
                    "section_width_mm": 400.0,
                    "clash_count": 2,
                }
            ],
        },
    )
    out = tmp_path / "panel_zone_joint_geometry_3d.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            "joint_geometry",
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    row = payload["artifacts"]["source_rows_head"][0]
    _assert_vector_geometry_keys(row, clash_points=2)


def test_panel_zone_3d_source_artifact_reuses_joint_geometry_for_bundle_vector_keys(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "panel_zone_bundle_source.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B402",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.10,
                    "section_signature": "SB-42",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "summary": {
                "producer_backend": "panel_zone_external_solver",
                "source_bundle_mode": "nested_solver_export",
            },
            "panel_zone_3d_results": {
                "panel_zone_joint_geometry_3d": {
                    "contract_pass": True,
                    "source_kind": "panel_zone_joint_geometry_3d",
                    "rows": [
                        {
                            "member_id": "B402",
                            "joint_id": "J-402",
                            "panel_zone_id": "PZ-402",
                            "joint_centroid_m": {"x": 4.0, "y": 5.0, "z": 3.2},
                            "beam_length_mm": 4200.0,
                            "section_width_mm": 380.0,
                            "section_depth_mm": 720.0,
                        }
                    ],
                },
                "panel_zone_rebar_anchorage_3d": {
                    "contract_pass": True,
                    "source_kind": "panel_zone_rebar_anchorage_3d",
                    "rows": [
                        {
                            "member_id": "B402",
                            "available_anchorage_length_mm": 480.0,
                            "required_anchorage_length_mm": 420.0,
                            "development_length_mm": 520.0,
                        }
                    ],
                },
                "panel_zone_clash_verification_3d": {
                    "contract_pass": True,
                    "source_kind": "panel_zone_clash_verification_3d",
                    "rows": [
                        {
                            "member_id": "B402",
                            "clash_count": 1,
                            "clearance_mm": 24.0,
                            "clash_pass": False,
                        }
                    ],
                },
            },
        },
    )

    anchorage_out = tmp_path / "panel_zone_rebar_anchorage_3d.json"
    clash_out = tmp_path / "panel_zone_clash_verification_3d.json"
    for source_kind, out in (
        ("rebar_anchorage", anchorage_out),
        ("clash_verification", clash_out),
    ):
        proc = subprocess.run(
            [
                sys.executable,
                "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
                "--source-kind",
                source_kind,
                "--design-optimization-dataset",
                str(dataset),
                "--source-input",
                str(source_input),
                "--out",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr

    anchorage_payload = json.loads(anchorage_out.read_text(encoding="utf-8"))
    anchorage_row = anchorage_payload["artifacts"]["source_rows_head"][0]
    _assert_vector_geometry_keys(anchorage_row, clash_points=0)
    assert anchorage_row["joint_centroid_m"] == {"x": 4.0, "y": 5.0, "z": 3.2}

    clash_payload = json.loads(clash_out.read_text(encoding="utf-8"))
    clash_row = clash_payload["artifacts"]["source_rows_head"][0]
    _assert_vector_geometry_keys(clash_row, clash_points=1)
    assert clash_row["joint_centroid_m"] == {"x": 4.0, "y": 5.0, "z": 3.2}


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_bridges_opensees_topology_report(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    topology_report = _write_topology_report(tmp_path)
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B900",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-90",
                }
            ],
        },
    )
    out = tmp_path / f"{expected_kind}.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(topology_report),
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
    assert payload["source_kind"] == expected_kind
    assert payload["summary"]["source_bundle_mode"] == "opensees_topology_bridge"
    assert payload["summary"]["producer_backend"] == "opensees_topology_report"
    assert payload["summary"]["topology_projected"] is True
    assert payload["summary"]["solver_verified"] is False
    assert payload["summary"]["verification_tier"] == f"{expected_kind}_topology_projected_validated_source"
    assert "solver-verified 3D clash rows are not attached" in payload["reason"]
    assert payload["summary"]["source_row_count"] == 1
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["source_provenance"]["source_topology_real_pass"] is True
    assert payload["source_provenance"]["source_topology_edges_path"].endswith("opensees_edges.json")
    assert payload["source_provenance"]["source_input_kind"] == "opensees_topology_bridge"
    _assert_vector_geometry_keys(payload["artifacts"]["source_rows_head"][0], clash_points=0)


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_bridges_phase3_pipeline_report(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    topology_report = _write_topology_report(tmp_path)
    pipeline_report = _write_phase3_pipeline_report(tmp_path, topology_report)
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B901",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.10,
                    "section_signature": "SB-91",
                }
            ],
        },
    )
    out = tmp_path / f"{expected_kind}.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(pipeline_report),
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
    assert payload["summary"]["source_bundle_mode"] == "phase3_pipeline_topology_bridge"
    assert payload["summary"]["producer_backend"] == "phase3_pipeline_topology_report"
    assert payload["summary"]["solver_verified"] is False
    assert payload["summary"]["verification_tier"] == f"{expected_kind}_topology_projected_validated_source"
    assert payload["source_provenance"]["source_topology_report"].endswith("opensees_topology_report.json")
    _assert_vector_geometry_keys(payload["artifacts"]["source_rows_head"][0], clash_points=0)


def test_panel_zone_3d_source_artifact_passes_with_matching_source_rows(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "joint_geometry_solver.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B302",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-02",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "rows": [{"member_id": "B302", "joint_id": "J-1"}],
        },
    )
    out = tmp_path / "panel_zone_joint_geometry_3d.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            "joint_geometry",
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
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
    assert payload["source_kind"] == "panel_zone_joint_geometry_3d"
    assert payload["summary"]["source_row_count"] == 1
    assert payload["summary"]["valid_source_row_count"] == 1
    assert payload["summary"]["invalid_source_row_count"] == 0
    assert payload["summary"]["candidate_member_count"] == 1
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["checks"]["source_kind_match"] is True
    assert payload["checks"]["source_rows_present"] is True
    assert payload["checks"]["source_member_overlap_present"] is True


def test_panel_zone_3d_source_artifact_rejects_non_overlapping_source_rows(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "joint_geometry_solver.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B304",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-04",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "rows": [{"member_id": "B999", "joint_id": "J-99"}],
        },
    )
    out = tmp_path / "panel_zone_joint_geometry_3d.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            "joint_geometry",
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_MEMBER_OVERLAP_MISSING"
    assert payload["summary"]["valid_source_row_count"] == 1
    assert payload["summary"]["overlap_member_count"] == 0
    assert payload["checks"]["source_member_overlap_present"] is False


def test_panel_zone_3d_source_artifact_rejects_rows_missing_kind_specific_fields(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "joint_geometry_solver.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B305",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-05",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "rows": [{"member_id": "B305"}],
        },
    )
    out = tmp_path / "panel_zone_joint_geometry_3d.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            "joint_geometry",
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_REQUIRED_FIELDS_MISSING"
    assert payload["summary"]["valid_source_row_count"] == 0
    assert payload["summary"]["invalid_source_row_count"] == 1
    assert payload["checks"]["source_rows_present"] is False


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_accepts_nested_solver_export_bundle(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B401",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-41",
                }
            ],
        },
    )
    out = tmp_path / f"{source_kind}_bundle_source.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(FIXTURE_DIR / "panel_zone_solver_export_bundle.json"),
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
    assert payload["source_kind"] == expected_kind
    assert payload["summary"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["source_provenance"]["source_bundle_detected"] is True
    assert payload["source_provenance"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["summary"]["source_row_count"] == 1
    assert payload["summary"]["overlap_member_count"] == 1


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_promotes_solver_verified_bundle_root_metadata(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B401",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-41",
                }
            ],
        },
    )
    out = tmp_path / f"{source_kind}_solver_verified_bundle_source.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"),
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
    assert payload["source_kind"] == expected_kind
    assert payload["reason"] == "panel-zone 3D source artifact is attached and candidate rows are bound"
    assert payload["summary"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["summary"]["producer_backend"] == "panel_zone_external_solver"
    assert payload["summary"]["solver_verified"] is True
    assert payload["summary"]["topology_projected"] is False
    assert payload["summary"]["verification_tier"] == f"{expected_kind}_solver_verified_validated_source"
    assert payload["summary"]["upstream_verification_tier"] == "solver_verified_3d_source_bundle"
    assert payload["summary"]["instruction_sidecar_evidence_model"] == "direct_solver_export"
    assert payload["summary"]["instruction_sidecar_rebar_delivery_mode"] == "solver_verified_layout_rows"
    assert payload["source_provenance"]["source_bundle_detected"] is True
    assert payload["source_provenance"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["source_provenance"]["producer_backend"] == "panel_zone_external_solver"
    assert payload["source_provenance"]["solver_verified"] is True
    assert payload["source_provenance"]["topology_projected"] is False
    assert payload["source_provenance"]["upstream_verification_tier"] == "solver_verified_3d_source_bundle"
    assert payload["summary"]["source_row_count"] == 1
    assert payload["summary"]["overlap_member_count"] == 1


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_passes_with_kind_specific_required_fields(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / f"{source_kind}_solver.json"
    member_id = "B320"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": member_id,
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-20",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "source_kind": expected_kind,
            "rows": _source_rows_for_kind(source_kind, member_id),
        },
    )
    out = tmp_path / f"{expected_kind}.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
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
    assert payload["summary"]["valid_source_row_count"] == 1
    assert payload["summary"]["invalid_source_row_count"] == 0
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["checks"]["required_source_fields_present"] is True
    assert payload["source_provenance"]["required_source_fields"] == list(_source_rows_for_kind(source_kind, member_id)[0].keys())[1:]


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_applies_member_mapping_sidecar_before_overlap_check(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "solver_verified_bundle.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "26705",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-20",
                }
            ],
        },
    )
    source_row = _source_rows_for_kind(source_kind, "B401")[0]
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "summary": {
                "producer_backend": "panel_zone_external_solver",
                "source_bundle_mode": "nested_solver_export",
                "solver_verified": True,
                "topology_projected": False,
                "verification_tier": "solver_verified_3d_source_bundle",
            },
            "member_mapping_sidecar": {
                "present": True,
                "mapping_mode": "explicit_member_id_map",
                "row_count": 1,
                "rows": [{"source_member_id": "B401", "candidate_member_id": "26705"}],
                "member_map": {"B401": "26705"},
            },
            "panel_zone_3d_results": {
                expected_kind: {
                    "contract_pass": True,
                    "summary": {
                        "source_kind": expected_kind,
                        "producer_backend": "panel_zone_external_solver",
                        "source_bundle_mode": "nested_solver_export",
                        "solver_verified": True,
                        "topology_projected": False,
                        "verification_tier": "solver_verified_3d_source",
                    },
                    "rows": [source_row],
                }
            },
        },
    )
    out = tmp_path / f"{expected_kind}.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
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
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["source_provenance"]["raw_source_member_ids_head"] == ["B401"]
    assert payload["source_provenance"]["source_member_ids_head"] == ["26705"]
    assert payload["summary"]["member_mapping_sidecar_present"] is True
    assert payload["summary"]["member_mapping_sidecar_applied_row_count"] == 1


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_prefers_member_map_before_rows_for_sidecar_conflicts(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / "solver_verified_bundle.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "26705",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-20",
                }
            ],
        },
    )
    source_row = _source_rows_for_kind(source_kind, "B401")[0]
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "summary": {
                "producer_backend": "panel_zone_external_solver",
                "source_bundle_mode": "nested_solver_export",
                "solver_verified": True,
                "topology_projected": False,
                "verification_tier": "solver_verified_3d_source_bundle",
            },
            "member_mapping_sidecar": {
                "present": True,
                "mapping_mode": "explicit_member_id_map",
                "row_count": 2,
                "rows": [{"source_member_id": "B401", "candidate_member_id": "does-not-overlap"}],
                "member_map": {"B401": "26705"},
            },
            "panel_zone_3d_results": {
                expected_kind: {
                    "contract_pass": True,
                    "source_kind": expected_kind,
                    "rows": [source_row],
                }
            },
        },
    )
    out = tmp_path / f"{expected_kind}.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
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
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["source_provenance"]["raw_source_member_ids_head"] == ["B401"]
    assert payload["source_provenance"]["source_member_ids_head"] == ["26705"]
    assert payload["summary"]["member_mapping_sidecar_applied_row_count"] == 1
    assert payload["artifacts"]["source_rows_head"][0]["source_member_id"] == "B401"
    assert payload["artifacts"]["source_rows_head"][0]["member_id"] == "26705"


@pytest.mark.parametrize(
    ("source_kind", "expected_kind", "rows"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d", [{"member_id": "B330"}]),
        (
            "rebar_anchorage",
            "panel_zone_rebar_anchorage_3d",
            [{"member_id": "B331", "available_anchorage_length_mm": 480.0}],
        ),
        (
            "clash_verification",
            "panel_zone_clash_verification_3d",
            [{"member_id": "B332", "clash_count": 0}],
        ),
    ],
)
def test_panel_zone_3d_source_artifact_rejects_missing_kind_specific_required_fields(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
    rows: list[dict],
) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    source_input = tmp_path / f"{source_kind}_solver.json"
    member_id = rows[0]["member_id"]
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": member_id,
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.11,
                    "section_signature": "SB-30",
                }
            ],
        },
    )
    _write_json(
        source_input,
        {
            "contract_pass": True,
            "source_kind": expected_kind,
            "rows": rows,
        },
    )
    out = tmp_path / f"{expected_kind}.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_artifact.py",
            "--source-kind",
            source_kind,
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source_input),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_REQUIRED_FIELDS_MISSING"
    assert payload["summary"]["valid_source_row_count"] == 0
    assert payload["summary"]["invalid_source_row_count"] == 1
    assert payload["checks"]["required_source_fields_present"] is False


@pytest.mark.parametrize(
    ("entrypoint", "expected_kind"),
    [
        ("implementation/phase1/generate_panel_zone_joint_geometry_3d_source.py", "panel_zone_joint_geometry_3d"),
        ("implementation/phase1/generate_panel_zone_rebar_anchorage_3d_source.py", "panel_zone_rebar_anchorage_3d"),
        ("implementation/phase1/generate_panel_zone_clash_verification_3d_source.py", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_artifact_entrypoints_emit_expected_kind(tmp_path: Path, entrypoint: str, expected_kind: str) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 4, "group_count": 2},
            "rows_head": [
                {
                    "member_id": "B303",
                    "member_type": "beam",
                    "group_id": "G1",
                    "constructability_score": 0.10,
                    "section_signature": "SB-03",
                }
            ],
        },
    )
    out = tmp_path / f"{expected_kind}.json"

    proc = subprocess.run(
        [
            sys.executable,
            entrypoint,
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
    assert payload["source_kind"] == expected_kind
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_INPUT_MISSING"
