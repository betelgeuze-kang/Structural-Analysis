"""Whole-model frame/truss modal assembly and public-path tests."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from structural_analysis import AnalysisConfig, analyze, load_model
from structural_analysis.analyses.modal import (
    AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
    EIGEN_BACKEND,
    MODAL_CLAIM_BOUNDARY,
)
from structural_analysis.assembly.modal import assemble_modal_matrices
from structural_analysis.elements.axial import (
    axial_element_properties,
    axial_global_consistent_mass,
)
from structural_analysis.elements.frame3d import FrameProps, local_frame_consistent_mass


ROOT = Path(__file__).resolve().parents[1]


def _frame_payload(
    *,
    density: object = 7850.0,
    iy: float = 5.0e-5,
    iz: float = 8.0e-5,
    supports: list[dict[str, object]] | None = None,
    element_type: str = "frame",
) -> dict[str, object]:
    if supports is None:
        supports = [
            {"node": "N1", "dofs": "all"},
            {"node": "N2", "dofs": ["UX", "UZ", "RX", "RY"]},
        ]
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": element_type,
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.3,
                "density": density,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": iy,
                "iz": iz,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
    }


def _axial_payload() -> dict[str, object]:
    payload = _frame_payload(element_type="truss")
    payload["sections"] = [{"id": "S1", "type": "axial", "area": 0.02}]
    payload["supports"] = [
        {"node": "N1", "dofs": "all"},
        {"node": "N2", "dofs": ["UY", "UZ"]},
    ]
    return payload


def _write_model(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )


def test_frame_consistent_mass_is_positive_and_conserves_translation_mass() -> None:
    props = FrameProps(
        area_m2=0.02,
        e_n_per_m2=2.0e8,
        g_n_per_m2=7.692307692307692e7,
        iy_m4=5.0e-5,
        iz_m4=8.0e-5,
        j_m4=1.0e-5,
    )
    matrix = local_frame_consistent_mass(
        props,
        2.0,
        density_kg_per_m3=7850.0,
    )
    expected_mass_coefficient = 7850.0 * 0.02 * 2.0 / 1000.0

    assert np.array_equal(matrix, matrix.T)
    assert float(np.min(np.linalg.eigvalsh(matrix))) > 0.0
    for offset in (0, 1, 2):
        influence = np.zeros(12, dtype=np.float64)
        influence[[offset, offset + 6]] = 1.0
        assert float(influence @ matrix @ influence) == pytest.approx(
            expected_mass_coefficient,
            rel=1.0e-14,
        )


def test_axial_consistent_mass_is_global_translation_invariant() -> None:
    properties = axial_element_properties(
        element_id="T1",
        node_ids=("N1", "N2"),
        start_coordinates=(0.0, 0.0, 0.0),
        end_coordinates=(2.0, 1.0, -0.5),
        elastic_modulus=2.0e8,
        area=0.02,
    )
    matrix = axial_global_consistent_mass(
        properties,
        density_kg_per_m3=7850.0,
    )
    expected = 7850.0 * 0.02 * properties.length / 1000.0

    assert np.array_equal(matrix, matrix.T)
    assert float(np.min(np.linalg.eigvalsh(matrix))) > 0.0
    for offset in range(3):
        influence = np.zeros(6, dtype=np.float64)
        influence[[offset, offset + 3]] = 1.0
        assert float(influence @ matrix @ influence) == pytest.approx(expected)


def test_modal_assembly_records_physical_mass_and_reduced_dofs(tmp_path: Path) -> None:
    model_path = tmp_path / "frame.json"
    _write_model(model_path, _frame_payload())

    assembly, unsupported = assemble_modal_matrices(load_model(model_path))

    assert unsupported == []
    assert assembly is not None
    assert assembly.total_physical_mass_kg == pytest.approx(314.0)
    assert assembly.free_dofs == (7, 11)
    assert assembly.active_dofs == tuple(range(12))
    assert assembly.mass_matrix_unit == "kN_s2_per_m"
    free_mass = assembly.mass[np.ix_(assembly.free_dofs, assembly.free_dofs)]
    assert float(np.min(np.linalg.eigvalsh(free_mass))) > 0.0


def test_public_cantilever_modal_path_matches_one_element_closed_eigenvalues(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "cantilever.json"
    _write_model(model_path, _frame_payload())

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=2, tolerance=1.0e-10),
    )
    replay = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=2, tolerance=1.0e-10),
    )

    dimensionless = (12.4801921537537, 1211.5198078462463)
    scale = (2.0e8 * 8.0e-5) / ((7850.0 * 0.02 / 1000.0) * 2.0**4)
    expected_eigenvalues = [value * scale for value in dimensionless]
    assert result.status == "ready"
    assert result.solver == AUTHORITATIVE_CPU_MODAL_SOLVER_ID
    assert result.unsupported_features == []
    assert result.metrics["matrix_backend"] == EIGEN_BACKEND
    assert result.metrics["free_dof_count"] == 2
    assert result.metrics["mode_count"] == 2
    assert result.metrics["rigid_mode_count"] == 0
    assert result.metrics["total_physical_mass_kg"] == pytest.approx(314.0)
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert result.metrics["claim_boundary"] == MODAL_CLAIM_BOUNDARY
    assert result.metrics["whole_model_frame_truss_modal_workflow"] is True
    assert result.metrics["general_frame_shell_modal_workflow"] is False
    assert result.metrics["binary_mode_vector_artifact_connected"] is False
    assert result.metrics["mass_normalized_mode_vectors_inlined"] is False
    assert result.metrics["symmetric_coordinate_scaling_applied"] is True
    assert result.metrics["characteristic_length"] == pytest.approx(2.0)
    assert result.metrics["scaling_hash"].startswith("sha256:")
    assert result.metrics["equation_scaling_6dof"]["scaling_hash"] == (
        result.metrics["scaling_hash"]
    )
    assert result.metrics["scaled_mass_condition_number_status"] == "available"
    assert result.metrics["scaled_mass_condition_number"] > 0.0
    assert result.metrics["raw_result_hash"] == replay.metrics["raw_result_hash"]
    assert result.metrics["semantic_result_hash"] == replay.metrics["semantic_result_hash"]

    actual_eigenvalues = [
        row["eigenvalue_rad2_per_s2"] for row in result.metrics["modes"]
    ]
    assert actual_eigenvalues == pytest.approx(expected_eigenvalues, rel=2.0e-14)
    ratios = [
        row["directional_participation"]["UY"]["effective_modal_mass_ratio"]
        for row in result.metrics["modes"]
    ]
    assert sum(ratios) == pytest.approx(1.0, abs=1.0e-14)
    last_cumulative = result.metrics["modes"][-1]["directional_participation"][
        "UY"
    ]["cumulative_effective_modal_mass_ratio"]
    assert last_cumulative == pytest.approx(1.0, abs=1.0e-14)
    for row in result.metrics["modes"]:
        shapes = row["max_component_normalized_node_shapes"]
        base = shapes[0]["components"]
        assert all(value == 0.0 for value in base.values())
        assert max(
            abs(value)
            for node in shapes
            for value in node["components"].values()
        ) == pytest.approx(1.0)


def test_public_axial_modal_path_matches_consistent_mass_solution(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "axial.json"
    _write_model(model_path, _axial_payload())

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=1, tolerance=1.0e-10),
    )

    expected = 3.0 * 2.0e8 * 1000.0 / (7850.0 * 2.0**2)
    assert result.status == "ready"
    assert result.metrics["free_dof_count"] == 1
    assert result.metrics["modes"][0]["eigenvalue_rad2_per_s2"] == pytest.approx(
        expected,
        rel=1.0e-14,
    )


def test_free_free_frame_excludes_six_rigid_body_modes(tmp_path: Path) -> None:
    model_path = tmp_path / "free-free.json"
    _write_model(model_path, _frame_payload(supports=[]))

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=6, tolerance=1.0e-9),
    )

    assert result.status == "ready"
    assert result.metrics["free_dof_count"] == 12
    assert result.metrics["rigid_mode_count"] == 6
    assert len(result.metrics["modes"]) == 6
    assert all(row["frequency_hz"] > 0.0 for row in result.metrics["modes"])


def test_repeated_bending_cluster_must_be_selected_completely(tmp_path: Path) -> None:
    supports = [
        {"node": "N1", "dofs": "all"},
        {"node": "N2", "dofs": ["UX", "RX"]},
    ]
    model_path = tmp_path / "symmetric-frame.json"
    _write_model(
        model_path,
        _frame_payload(iy=8.0e-5, iz=8.0e-5, supports=supports),
    )
    model = load_model(model_path)

    cut = analyze(
        model,
        AnalysisConfig(analysis_type="modal", mode_count=1, tolerance=1.0e-9),
    )
    complete = analyze(
        model,
        AnalysisConfig(analysis_type="modal", mode_count=2, tolerance=1.0e-9),
    )

    assert cut.status == "blocked"
    assert cut.unsupported_features[0]["kind"] == (
        "modal_generalized_eigen_contract_failed"
    )
    assert "cuts a repeated" in cut.unsupported_features[0]["detail"]
    assert complete.status == "ready"
    frequencies = [row["frequency_hz"] for row in complete.metrics["modes"]]
    assert frequencies[0] == pytest.approx(frequencies[1], rel=1.0e-14)


@pytest.mark.parametrize("density", [None, 0.0, -1.0, True, "bad"])
def test_missing_or_invalid_density_blocks_without_fallback(
    tmp_path: Path,
    density: object,
) -> None:
    model_path = tmp_path / "invalid-density.json"
    _write_model(model_path, _frame_payload(density=density))

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=1),
    )

    assert result.status == "blocked"
    assert {row["kind"] for row in result.unsupported_features} == {
        "modal_material_density_missing_or_invalid"
    }
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False


def test_all_active_dofs_constrained_blocks_modal_analysis(tmp_path: Path) -> None:
    model_path = tmp_path / "all-constrained.json"
    _write_model(
        model_path,
        _frame_payload(
            supports=[
                {"node": "N1", "dofs": "all"},
                {"node": "N2", "dofs": "all"},
            ]
        ),
    )

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=1),
    )

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == "modal_free_active_dofs_missing"


@pytest.mark.parametrize(
    ("location", "field", "expected_kind"),
    [
        ("node", "mass_kg", "modal_nodal_mass_not_supported"),
        (
            "element",
            "additional_mass_kg_per_m",
            "modal_element_mass_override_not_supported",
        ),
        ("metadata", "nodal_masses", "modal_nodal_mass_not_supported"),
    ],
)
def test_unconnected_mass_inputs_are_not_silently_ignored(
    tmp_path: Path,
    location: str,
    field: str,
    expected_kind: str,
) -> None:
    payload = _frame_payload()
    if location == "node":
        payload["nodes"][1][field] = 100.0
    elif location == "element":
        payload["elements"][0][field] = 5.0
    else:
        payload["metadata"] = {field: [{"node": "N2", "mass_kg": 100.0}]}
    model_path = tmp_path / f"{location}-mass.json"
    _write_model(model_path, payload)

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="modal", mode_count=1),
    )

    assert result.status == "blocked"
    assert expected_kind in {row["kind"] for row in result.unsupported_features}
    assert result.metrics["fallback_used"] is False


def test_unsupported_element_and_configuration_fail_closed(tmp_path: Path) -> None:
    shell_path = tmp_path / "shell.json"
    _write_model(shell_path, _frame_payload(element_type="shell"))
    shell = analyze(
        load_model(shell_path),
        AnalysisConfig(analysis_type="modal", mode_count=1),
    )
    invalid_count = analyze(
        load_model(shell_path),
        AnalysisConfig(analysis_type="modal", mode_count=True),
    )
    bad_backend = analyze(
        load_model(shell_path),
        AnalysisConfig(
            analysis_type="modal",
            mode_count=1,
            eigen_backend="unapproved_backend",
        ),
    )

    assert shell.status == "blocked"
    assert "modal_element_not_supported" in {
        row["kind"] for row in shell.unsupported_features
    }
    assert invalid_count.status == "blocked"
    assert invalid_count.unsupported_features[0]["kind"] == "modal_mode_count_invalid"
    assert bad_backend.status == "blocked"
    assert bad_backend.unsupported_features[0]["kind"] == (
        "modal_eigen_backend_not_supported"
    )


def test_modal_cli_writes_engine_owned_result_and_validation_report(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "cantilever.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    _write_model(model_path, _frame_payload())
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "modal",
            "--mode-count",
            "2",
            "--tolerance",
            "1e-10",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "ready"
    assert result["solver"] == AUTHORITATIVE_CPU_MODAL_SOLVER_ID
    assert result["metrics"]["mode_count"] == 2
    assert result["metrics"]["provenance_policy"] == "engine_owned"
    assert report["contract_pass"] is True
    assert any("No reference payload" in row for row in report["warnings"])


def test_analysis_config_serializes_modal_controls() -> None:
    payload = AnalysisConfig(
        analysis_type="modal",
        mode_count=3,
        eigen_backend=EIGEN_BACKEND,
    ).to_dict()

    assert payload["mode_count"] == 3
    assert payload["eigen_backend"] == EIGEN_BACKEND
    assert math.isfinite(payload["tolerance"])
