"""Whole-model frame initial-stress buckling assembly and public-path tests."""

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
from structural_analysis.analyses.buckling import (
    AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
    BUCKLING_CLAIM_BOUNDARY,
    BUCKLING_EIGEN_BACKEND,
)
from structural_analysis.assembly.buckling import (
    GEOMETRIC_STIFFNESS_FORMULATION,
    assemble_linear_buckling_matrices,
)
from structural_analysis.elements.frame3d import local_frame_geometric_stiffness


ROOT = Path(__file__).resolve().parents[1]


def _column_payload(
    *,
    element_count: int = 16,
    iy: float = 6.0e-5,
    iz: float = 8.0e-5,
    axial_load_kn: float = -100.0,
) -> dict[str, object]:
    length = 3.0
    nodes = [
        {
            "id": f"N{index}",
            "coordinates": [length * index / element_count, 0.0, 0.0],
        }
        for index in range(element_count + 1)
    ]
    elements = [
        {
            "id": f"E{index}",
            "type": "frame",
            "nodes": [f"N{index}", f"N{index + 1}"],
            "section": "S1",
            "material": "M1",
        }
        for index in range(element_count)
    ]
    supports: list[dict[str, object]] = []
    for index in range(element_count + 1):
        dofs = ["RX"]
        if index == 0:
            dofs.append("UX")
        if index in {0, element_count}:
            dofs.extend(["UY", "UZ"])
        supports.append({"node": f"N{index}", "dofs": dofs})
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.3,
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
        "loads": [
            {
                "node": f"N{element_count}",
                "components": [axial_load_kn, 0.0, 0.0, 0.0, 0.0, 0.0],
            }
        ],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
    }


def _write_model(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )


def _run(
    path: Path,
    *,
    mode_count: int = 2,
    load_case: str | None = None,
) -> object:
    return analyze(
        load_model(path),
        AnalysisConfig(
            analysis_type="linear_buckling",
            mode_count=mode_count,
            tolerance=1.0e-8,
            eigen_backend=BUCKLING_EIGEN_BACKEND,
            load_case=load_case,
        ),
    )


def test_local_frame_geometric_stiffness_matches_consistent_plane_matrix() -> None:
    length = 3.0
    compression = 100.0
    matrix = local_frame_geometric_stiffness(
        length,
        compression_force_kn=compression,
    )
    expected = (compression / (30.0 * length)) * np.asarray(
        [
            [36.0, 3.0 * length, -36.0, 3.0 * length],
            [3.0 * length, 4.0 * length**2, -3.0 * length, -(length**2)],
            [-36.0, -3.0 * length, 36.0, -3.0 * length],
            [3.0 * length, -(length**2), -3.0 * length, 4.0 * length**2],
        ]
    )

    assert np.array_equal(matrix, matrix.T)
    assert matrix[np.ix_((1, 5, 7, 11), (1, 5, 7, 11))] == pytest.approx(
        expected
    )
    assert float(np.min(np.linalg.eigvalsh(matrix))) >= -1.0e-12
    assert np.count_nonzero(matrix[[0, 3, 6, 9], :]) == 0


def test_public_two_plane_column_converges_to_euler_load_and_replays(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "column.json"
    _write_model(model_path, _column_payload())

    result = _run(model_path)
    replay = _run(model_path)
    expected = sorted(
        [
            math.pi**2 * 2.0e8 * 6.0e-5 / 3.0**2 / 100.0,
            math.pi**2 * 2.0e8 * 8.0e-5 / 3.0**2 / 100.0,
        ]
    )
    actual = [row["load_factor"] for row in result.metrics["modes"]]

    assert result.status == "ready"
    assert result.solver == AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID
    assert result.unsupported_features == []
    assert actual == pytest.approx(expected, rel=3.0e-6)
    assert result.metrics["critical_load_factor"] == actual[0]
    assert result.metrics["reference_static_solver_id"] == (
        "authoritative_cpu_linear_fea_3d_v1"
    )
    assert result.metrics["reference_load_factor"] == 1.0
    assert result.metrics["geometric_stiffness_formulation"] == (
        GEOMETRIC_STIFFNESS_FORMULATION
    )
    assert result.metrics["matrix_backend"] == BUCKLING_EIGEN_BACKEND
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert result.metrics["whole_model_frame_linear_buckling_workflow"] is True
    assert result.metrics["general_frame_shell_linear_buckling_workflow"] is False
    assert result.metrics["binary_mode_vector_artifact_connected"] is False
    assert result.metrics["claim_boundary"] == BUCKLING_CLAIM_BOUNDARY
    assert result.metrics["raw_result_hash"] == replay.metrics["raw_result_hash"]
    assert result.metrics["semantic_result_hash"] == (
        replay.metrics["semantic_result_hash"]
    )
    scaling = result.metrics["equation_scaling"]
    assert scaling["status"] == "available"
    assert scaling["value"]["solve_applied"] is True
    assert scaling["value"]["characteristic_length"] == pytest.approx(3.0)
    assert scaling["value"]["reference_force"] > 0.0
    assert scaling["value"]["scaling_hash"].startswith("sha256:")
    assert (
        scaling["value"]["scaled_stiffness_condition_number"]["status"]
        == "available"
    )
    assert (
        scaling["value"]["scaled_geometric_stiffness_condition_number"][
            "status"
        ]
        == "available"
    )
    assert (
        scaling["value"]["scaled_geometric_stiffness_condition_number"][
            "value"
        ]
        > 0.0
    )
    assert (
        result.metrics["reference_static_equation_scaling"]["status"]
        == "available"
    )
    compressions = result.metrics["reference_member_compression_forces"]
    assert len(compressions) == 16
    assert [row["reference_compression_force_kn"] for row in compressions] == (
        pytest.approx([100.0] * 16, rel=1.0e-12)
    )
    for row in result.metrics["modes"]:
        assert row["scaled_residual_relative_inf"] is not None
        assert row["scaled_residual_relative_inf"] <= 1.0e-8
        assert row["raw_translational_residual_norm"] is not None
        assert row["raw_rotational_residual_norm"] is not None
        shapes = row["max_component_normalized_node_shapes"]
        assert max(
            abs(value)
            for node in shapes
            for value in node["components"].values()
        ) == pytest.approx(1.0)


def test_critical_physical_load_is_invariant_to_reference_load_scale(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "column-100.json"
    second_path = tmp_path / "column-200.json"
    _write_model(first_path, _column_payload(axial_load_kn=-100.0))
    _write_model(second_path, _column_payload(axial_load_kn=-200.0))

    first = _run(first_path, mode_count=1)
    second = _run(second_path, mode_count=1)

    assert first.status == "ready"
    assert second.status == "ready"
    assert first.metrics["critical_load_factor"] * 100.0 == pytest.approx(
        second.metrics["critical_load_factor"] * 200.0,
        rel=1.0e-12,
    )


def test_symmetric_bending_cluster_must_be_selected_completely(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "symmetric-column.json"
    _write_model(model_path, _column_payload(iy=8.0e-5, iz=8.0e-5))

    cut = _run(model_path, mode_count=1)
    complete = _run(model_path, mode_count=2)

    assert cut.status == "blocked"
    assert cut.unsupported_features[0]["kind"] == (
        "buckling_generalized_eigen_contract_failed"
    )
    assert "cuts a repeated" in cut.unsupported_features[0]["detail"]
    assert complete.status == "ready"
    factors = [row["load_factor"] for row in complete.metrics["modes"]]
    assert factors[0] == pytest.approx(factors[1], rel=1.0e-12)


def test_reference_tension_is_not_discarded_or_projected(tmp_path: Path) -> None:
    model_path = tmp_path / "tension.json"
    _write_model(model_path, _column_payload(axial_load_kn=100.0))

    result = _run(model_path, mode_count=1)

    assert result.status == "blocked"
    assert {row["kind"] for row in result.unsupported_features} == {
        "buckling_reference_tension_not_supported"
    }
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False


def test_reference_state_without_compression_blocks(tmp_path: Path) -> None:
    payload = _column_payload()
    payload["loads"] = [
        {"node": "N16", "components": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]}
    ]
    model_path = tmp_path / "transverse.json"
    _write_model(model_path, payload)

    result = _run(model_path, mode_count=1)

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == (
        "buckling_reference_compression_missing"
    )


@pytest.mark.parametrize("element_type", ["truss", "shell"])
def test_unsupported_element_families_fail_closed(
    tmp_path: Path,
    element_type: str,
) -> None:
    payload = _column_payload(element_count=1)
    payload["elements"][0]["type"] = element_type
    if element_type == "truss":
        payload["sections"] = [{"id": "S1", "type": "axial", "area": 0.02}]
    model_path = tmp_path / f"{element_type}.json"
    _write_model(model_path, payload)

    result = _run(model_path, mode_count=1)

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == "buckling_element_not_supported"


def test_non_nodal_reference_load_fails_closed_before_static_solve(
    tmp_path: Path,
) -> None:
    payload = _column_payload()
    payload["loads"][0]["kind"] = "distributed_line"
    model_path = tmp_path / "distributed.json"
    _write_model(model_path, payload)

    result = _run(model_path, mode_count=1)

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == (
        "buckling_reference_load_type_not_supported"
    )
    assert result.metrics["reference_static_status"] == "not_run"


def test_named_reference_load_case_must_be_selected(tmp_path: Path) -> None:
    payload = _column_payload()
    payload["loads"] = [
        {
            "node": "N16",
            "components": [-100.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "load_case": "LC100",
        },
        {
            "node": "N16",
            "components": [-200.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "load_case": "LC200",
        },
    ]
    model_path = tmp_path / "cases.json"
    _write_model(model_path, payload)

    missing_selection = _run(model_path, mode_count=1)
    selected = _run(model_path, mode_count=1, load_case="LC200")

    assert missing_selection.status == "blocked"
    assert missing_selection.unsupported_features[0]["kind"] == (
        "buckling_reference_static_state_failed"
    )
    assert selected.status == "ready"
    assert selected.metrics["reference_load_case"] == "LC200"
    assert selected.metrics["reference_member_compression_forces"][0][
        "reference_compression_force_kn"
    ] == pytest.approx(200.0)


@pytest.mark.parametrize(
    ("config", "kind"),
    [
        (
            AnalysisConfig(analysis_type="linear_buckling", mode_count=True),
            "buckling_mode_count_invalid",
        ),
        (
            AnalysisConfig(analysis_type="linear_buckling", tolerance=True),
            "buckling_tolerance_invalid",
        ),
        (
            AnalysisConfig(
                analysis_type="linear_buckling",
                mode_count=1,
                eigen_backend="unapproved_backend",
            ),
            "buckling_eigen_backend_not_supported",
        ),
    ],
)
def test_invalid_public_configuration_fails_closed(
    tmp_path: Path,
    config: AnalysisConfig,
    kind: str,
) -> None:
    model_path = tmp_path / "column.json"
    _write_model(model_path, _column_payload())

    result = analyze(load_model(model_path), config)

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == kind


def test_reference_force_imbalance_is_rejected_by_assembly(tmp_path: Path) -> None:
    model_path = tmp_path / "one-element.json"
    _write_model(model_path, _column_payload(element_count=1))
    model = load_model(model_path)

    assembly, unsupported = assemble_linear_buckling_matrices(
        model,
        reference_member_forces=[
            {
                "id": "E0",
                "local_end_forces": {"FX_I": 100.0, "FX_J": -90.0},
            }
        ],
    )

    assert assembly is None
    assert unsupported[0]["kind"] == "buckling_reference_axial_force_imbalance"


def test_mixed_reference_tension_is_rejected_by_assembly(tmp_path: Path) -> None:
    model_path = tmp_path / "two-element.json"
    _write_model(model_path, _column_payload(element_count=2))
    model = load_model(model_path)

    assembly, unsupported = assemble_linear_buckling_matrices(
        model,
        reference_member_forces=[
            {
                "id": "E0",
                "local_end_forces": {"FX_I": 100.0, "FX_J": -100.0},
            },
            {
                "id": "E1",
                "local_end_forces": {"FX_I": -50.0, "FX_J": 50.0},
            },
        ],
    )

    assert assembly is None
    assert unsupported[0]["kind"] == "buckling_reference_tension_not_supported"


def test_buckling_cli_writes_engine_owned_result_and_validation_report(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "column.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    _write_model(model_path, _column_payload())
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.cli",
            str(model_path),
            "--analysis-type",
            "linear_buckling",
            "--mode-count",
            "2",
            "--tolerance",
            "1e-8",
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
    assert result["solver"] == AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID
    assert result["metrics"]["mode_count"] == 2
    assert result["metrics"]["provenance_policy"] == "engine_owned"
    assert report["contract_pass"] is True
    assert any("No reference payload" in row for row in report["warnings"])
