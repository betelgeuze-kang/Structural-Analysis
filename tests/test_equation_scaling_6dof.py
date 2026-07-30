from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis import load_model
from structural_analysis.analyses import run_authoritative_linear_static
from structural_analysis.solvers.equation_scaling_6dof import (
    EquationScaling6DOFError,
    create_equation_scaling_6dof,
    equilibration_vectors_6dof,
    exact_scaled_condition_number_1,
    scale_linear_system_6dof,
    scaled_increment_metrics_6dof,
    scaled_residual_metrics_6dof,
)


def _scaling():
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    reference_load = np.zeros(12)
    reference_load[6] = 5.0
    reference_load[11] = 20.0
    return create_equation_scaling_6dof(
        source_identity_hash="sha256:" + "1" * 64,
        node_coordinates_m=coordinates,
        reference_equation_load=reference_load,
        free_dofs=(6, 11),
    )


def test_common_6dof_scaling_balances_force_moment_rows_and_rotation_columns() -> None:
    scaling = _scaling()
    stiffness = np.diag([100.0, 400.0])
    rhs = np.asarray([10.0, 20.0])

    scaled_stiffness, scaled_rhs, recovery = scale_linear_system_6dof(
        stiffness,
        rhs,
        (6, 11),
        scaling,
    )
    scaled_solution = np.linalg.solve(scaled_stiffness, scaled_rhs)
    physical_solution = recovery * scaled_solution

    assert scaling.characteristic_length_m == pytest.approx(2.0)
    assert scaling.reference_force == pytest.approx(10.0)
    assert scaling.residual_rotation_scale == pytest.approx(20.0)
    assert scaled_stiffness == pytest.approx(np.diag([100.0, 100.0]))
    assert scaled_rhs == pytest.approx([10.0, 10.0])
    assert physical_solution == pytest.approx([0.1, 0.05])
    assert exact_scaled_condition_number_1(scaled_stiffness) == pytest.approx(1.0)

    residual = scaled_residual_metrics_6dof([5.0, 10.0], (6, 11), scaling)
    increment = scaled_increment_metrics_6dof([0.02, 0.01], (6, 11), scaling)
    assert residual == pytest.approx(
        {"translation": 5.0, "rotation": 10.0, "scaled": 0.5}
    )
    assert increment == pytest.approx(
        {"translation": 0.02, "rotation": 0.01, "scaled": 0.01}
    )


def test_6dof_equilibration_characteristic_length_does_not_change_physical_solution() -> None:
    free_dofs = (6, 11)
    stiffness = np.asarray([[100.0, 40.0], [40.0, 400.0]])
    rhs = np.asarray([10.0, 20.0])
    expected = np.linalg.solve(stiffness, rhs)

    for characteristic_length_m in (0.5, 2.0, 8.0):
        row_scale, column_scale = equilibration_vectors_6dof(
            free_dofs,
            characteristic_length_m,
        )
        scaled_stiffness = (
            row_scale[:, None] * stiffness * column_scale[None, :]
        )
        scaled_rhs = row_scale * rhs
        recovered = column_scale * np.linalg.solve(scaled_stiffness, scaled_rhs)
        assert recovered == pytest.approx(expected, rel=1.0e-13, abs=1.0e-15)


def test_common_6dof_scaling_hash_is_source_bound_and_invalid_inputs_fail_closed() -> None:
    first = _scaling()
    second = _scaling()
    changed = create_equation_scaling_6dof(
        source_identity_hash="sha256:" + "2" * 64,
        node_coordinates_m=[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        reference_equation_load=[0.0] * 6 + [5.0, 0.0, 0.0, 0.0, 0.0, 20.0],
        free_dofs=(6, 11),
    )

    assert first.scaling_hash == second.scaling_hash
    assert first.scaling_hash != changed.scaling_hash
    assert first.to_manifest()["source_free_dofs_hash"].startswith("sha256:")
    with pytest.raises(EquationScaling6DOFError, match="duplicate or out of range"):
        create_equation_scaling_6dof(
            source_identity_hash="sha256:" + "3" * 64,
            node_coordinates_m=[[0.0, 0.0, 0.0]],
            reference_equation_load=[0.0] * 6,
            free_dofs=(0, 0),
        )
    tampered = replace(first, scaling_hash="sha256:" + "f" * 64)
    with pytest.raises(EquationScaling6DOFError, match="scaling hash mismatch"):
        scale_linear_system_6dof(
            np.diag([100.0, 400.0]),
            np.asarray([10.0, 20.0]),
            (6, 11),
            tampered,
        )
    with pytest.raises(EquationScaling6DOFError, match="exact EquationScaling6DOF"):
        scale_linear_system_6dof(
            np.diag([100.0, 400.0]),
            np.asarray([10.0, 20.0]),
            (6, 11),
            object(),  # type: ignore[arg-type]
        )
    with pytest.raises(
        EquationScaling6DOFError,
        match="free DOFs do not match equation scaling source binding",
    ):
        scale_linear_system_6dof(
            np.diag([100.0, 400.0]),
            np.asarray([10.0, 20.0]),
            (7, 10),
            first,
        )
    with pytest.raises(
        EquationScaling6DOFError,
        match="free_dofs are duplicate or out of range",
    ):
        scale_linear_system_6dof(
            np.diag([100.0, 400.0]),
            np.asarray([10.0, 20.0]),
            (6, 6),
            first,
        )

    with pytest.raises(
        EquationScaling6DOFError,
        match="source_identity_hash must be a canonical sha256 hash",
    ):
        create_equation_scaling_6dof(
            source_identity_hash="not-a-source-hash",
            node_coordinates_m=[[0.0, 0.0, 0.0]],
            reference_equation_load=[0.0] * 6,
            free_dofs=(0,),
        )


@pytest.mark.parametrize(
    ("coordinates", "loads"),
    (
        ([[False, 0.0, 0.0]], [0.0] * 6),
        ([["0", "0", "0"]], [0.0] * 6),
        ([[0.0 + 0.0j, 0.0, 0.0]], [0.0] * 6),
        ([[2**53 + 1, 0.0, 0.0]], [0.0] * 6),
        ([[0.0, 0.0, 0.0]], [False] + [0.0] * 5),
        ([[0.0, 0.0, 0.0]], ["0"] * 6),
        ([[0.0, 0.0, 0.0]], [0.0 + 0.0j] * 6),
        ([[0.0, 0.0, 0.0]], [2**53 + 1] + [0.0] * 5),
    ),
)
def test_common_6dof_scaling_rejects_coercive_or_lossy_source_arrays(
    coordinates: object,
    loads: object,
) -> None:
    with pytest.raises(
        EquationScaling6DOFError,
        match="losslessly representable real binary64 values",
    ):
        create_equation_scaling_6dof(
            source_identity_hash="sha256:" + "4" * 64,
            node_coordinates_m=coordinates,
            reference_equation_load=loads,
            free_dofs=(0,),
        )


@pytest.mark.parametrize(
    "vector",
    (
        [True, 0.0],
        ["5", "10"],
        [5.0 + 0.0j, 10.0],
        [2**53 + 1, 0.0],
    ),
)
def test_common_6dof_metrics_reject_coercive_or_lossy_vectors(
    vector: object,
) -> None:
    scaling = _scaling()
    for metric in (scaled_residual_metrics_6dof, scaled_increment_metrics_6dof):
        with pytest.raises(
            EquationScaling6DOFError,
            match="losslessly representable real binary64 values",
        ):
            metric(vector, (6, 11), scaling)


@pytest.mark.parametrize(
    "matrix",
    (
        np.eye(2, dtype=np.bool_),
        np.asarray([["100", "0"], ["0", "400"]]),
        np.asarray([[100.0 + 0.0j, 0.0], [0.0, 400.0]]),
        [[2**53 + 1, 0.0], [0.0, 400.0]],
        csr_matrix(np.eye(2, dtype=np.bool_)),
        csr_matrix(np.asarray([[2**53 + 1, 0], [0, 400]], dtype=np.int64)),
    ),
)
def test_common_6dof_linear_algebra_rejects_coercive_or_lossy_matrices(
    matrix: object,
) -> None:
    scaling = _scaling()
    with pytest.raises(
        EquationScaling6DOFError,
        match="losslessly representable real binary64 values",
    ):
        scale_linear_system_6dof(matrix, [10.0, 20.0], (6, 11), scaling)
    with pytest.raises(
        EquationScaling6DOFError,
        match="losslessly representable real binary64 values",
    ):
        exact_scaled_condition_number_1(matrix)


@pytest.mark.parametrize("rhs", ([True, 0.0], ["10", "20"], [10.0 + 0.0j, 20.0]))
def test_common_6dof_linear_system_rejects_coercive_rhs(rhs: object) -> None:
    with pytest.raises(
        EquationScaling6DOFError,
        match="losslessly representable real binary64 values",
    ):
        scale_linear_system_6dof(
            np.diag([100.0, 400.0]),
            rhs,
            (6, 11),
            _scaling(),
        )


def test_all_6dof_metric_paths_validate_scaling_and_exact_free_dof_binding() -> None:
    scaling = _scaling()
    tampered = replace(scaling, characteristic_length_m=4.0)

    with pytest.raises(
        EquationScaling6DOFError,
        match="rotation residual scale does not match force-length scaling",
    ):
        scaled_residual_metrics_6dof([5.0, 10.0], (6, 11), tampered)
    with pytest.raises(
        EquationScaling6DOFError,
        match="free DOFs do not match equation scaling source binding",
    ):
        scaled_increment_metrics_6dof([0.02, 0.01], (7, 10), scaling)
    with pytest.raises(
        EquationScaling6DOFError,
        match="free_dofs must contain integers",
    ):
        equilibration_vectors_6dof((6.0, 11), 2.0)  # type: ignore[arg-type]
    with pytest.raises(
        EquationScaling6DOFError,
        match="unique non-negative integers",
    ):
        scaled_residual_metrics_6dof([5.0, 10.0], (6, 6), scaling)
    with pytest.raises(
        EquationScaling6DOFError,
        match="validated source-bound manifest",
    ):
        scaled_residual_metrics_6dof(
            [5.0, 10.0],
            (6, 11),
            object(),
        )


def _write_frame(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "structural-analysis-canonical-model.v1",
                "units": {"length": "m", "force": "kN"},
                "coordinate_system": {
                    "axis_order": ["X", "Y", "Z"],
                    "up_axis": "Z",
                },
                "nodes": [
                    {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
                    {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
                ],
                "elements": [
                    {
                        "id": "F1",
                        "type": "frame",
                        "nodes": ["N1", "N2"],
                        "section": "S1",
                        "material": "M1",
                    }
                ],
                "materials": [
                    {
                        "id": "M1",
                        "type": "elastic",
                        "elastic_modulus": 200.0e6,
                        "poisson_ratio": 0.3,
                    }
                ],
                "sections": [
                    {
                        "id": "S1",
                        "type": "frame",
                        "area": 0.02,
                        "iy": 8.0e-5,
                        "iz": 5.0e-5,
                        "torsional_constant": 1.0e-5,
                    }
                ],
                "loads": [
                    {"node": "N2", "components": {"FY": -10.0, "MX": 5.0}}
                ],
                "supports": [{"node": "N1", "dofs": "all"}],
            }
        ),
        encoding="utf-8",
    )


def test_public_linear_dense_and_sparse_use_identical_6dof_scaling(tmp_path: Path) -> None:
    path = tmp_path / "mixed-force-moment-frame.json"
    _write_frame(path)
    model = load_model(path)
    dense = run_authoritative_linear_static(
        model,
        tolerance=1.0e-9,
        matrix_backend="numpy_linalg_solve_dense",
    )
    sparse = run_authoritative_linear_static(
        model,
        tolerance=1.0e-9,
        matrix_backend="scipy_sparse_spsolve_cpu",
    )

    assert dense.status == sparse.status == "ready"
    assert dense.metrics["characteristic_length"] == pytest.approx(2.0)
    assert dense.metrics["scaling_hash"] == sparse.metrics["scaling_hash"]
    assert dense.metrics["equation_scaling_6dof"] == sparse.metrics[
        "equation_scaling_6dof"
    ]
    assert dense.metrics["dimensionless_scaled_residual"] <= 1.0e-9
    assert sparse.metrics["dimensionless_scaled_residual"] <= 1.0e-9
    assert dense.metrics["scaled_condition_number_status"] == "available"
    assert dense.metrics["scaled_condition_number"] > 0.0
    assert dense.metrics["raw_translation_increment"] >= 0.0
    assert dense.metrics["raw_rotation_increment"] >= 0.0
    assert dense.metrics["scaled_increment"] >= 0.0
    for node_id, components in dense.metrics["displacements"].items():
        assert components == pytest.approx(sparse.metrics["displacements"][node_id])
