"""Contract tests for the deterministic modal generalized-eigen kernel."""

from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.solvers._generalized_eigen import (
    raw_modes_sha256,
    semantic_modes_sha256,
)
from structural_analysis.solvers.modal import ModalAnalysisError, solve_modal_modes


def test_two_dof_shear_system_matches_closed_form_modes() -> None:
    stiffness = np.asarray([[2.0, -1.0], [-1.0, 1.0]], dtype=np.float64)
    mass = np.eye(2, dtype=np.float64)

    solution = solve_modal_modes(stiffness, mass, mode_count=2)

    expected = ((3.0 - math.sqrt(5.0)) / 2.0, (3.0 + math.sqrt(5.0)) / 2.0)
    assert [mode.eigenvalue_rad2_per_s2 for mode in solution.modes] == pytest.approx(
        expected,
        rel=1.0e-14,
    )
    assert [mode.frequency_hz for mode in solution.modes] == pytest.approx(
        [math.sqrt(value) / (2.0 * math.pi) for value in expected],
        rel=1.0e-14,
    )
    assert max(mode.residual_relative_inf for mode in solution.modes) <= 1.0e-14
    assert solution.mass_orthogonality_error_inf <= 1.0e-14
    assert solution.stiffness_diagonalization_error_inf <= 1.0e-14
    assert solution.regularization_applied is False
    assert solution.fallback_used is False
    assert solution.deterministic_mode_basis is True
    assert solution.contract_pass is True


def test_modal_kernel_excludes_rigid_modes_without_regularization() -> None:
    solution = solve_modal_modes(
        np.diag([0.0, 4.0]),
        np.eye(2, dtype=np.float64),
        mode_count=1,
    )

    assert solution.rigid_mode_count == 1
    assert solution.modes[0].eigenvalue_rad2_per_s2 == pytest.approx(4.0)
    assert solution.stiffness_minimum_eigenvalue == pytest.approx(0.0)
    assert solution.regularization_applied is False


def test_modal_coordinate_scaling_recovers_physical_modes_and_eigenvalues() -> None:
    stiffness = np.asarray([[4.0, -1.0], [-1.0, 9.0]], dtype=np.float64)
    mass = np.asarray([[2.0, 0.0], [0.0, 3.0]], dtype=np.float64)
    unscaled = solve_modal_modes(stiffness, mass, mode_count=2)
    scaled = solve_modal_modes(
        stiffness,
        mass,
        mode_count=2,
        coordinate_recovery_scale=np.asarray([1.0, 0.125]),
    )

    assert [row.eigenvalue_rad2_per_s2 for row in scaled.modes] == pytest.approx(
        [row.eigenvalue_rad2_per_s2 for row in unscaled.modes],
        rel=1.0e-14,
    )
    for expected, actual in zip(unscaled.modes, scaled.modes, strict=True):
        assert actual.mass_normalized_shape == pytest.approx(
            expected.mass_normalized_shape,
            rel=1.0e-14,
            abs=1.0e-14,
        )
        assert actual.residual_relative_inf <= 1.0e-14
    assert scaled.stiffness_matrix_hash == unscaled.stiffness_matrix_hash
    assert scaled.mass_matrix_hash == unscaled.mass_matrix_hash


def test_modal_coordinate_scaling_rejects_invalid_scale() -> None:
    with pytest.raises(ModalAnalysisError, match="finite positive DOF vector"):
        solve_modal_modes(
            np.eye(2),
            np.eye(2),
            mode_count=1,
            coordinate_recovery_scale=np.asarray([1.0, 0.0]),
        )


def test_repeated_modal_eigenspace_has_stable_coordinate_axis_basis() -> None:
    stiffness = np.diag([4.0, 4.0, 9.0])
    mass = np.eye(3, dtype=np.float64)

    first = solve_modal_modes(stiffness, mass, mode_count=3)
    second = solve_modal_modes(stiffness, mass, mode_count=3)

    assert first.to_dict() == second.to_dict()
    assert [mode.mass_normalized_shape for mode in first.modes] == [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]
    assert first.raw_result_hash == second.raw_result_hash
    assert first.semantic_result_hash == second.semantic_result_hash
    assert first.raw_result_hash.startswith("sha256:")
    assert first.semantic_result_hash.startswith("sha256:")


def test_semantic_mode_hash_normalizes_sub_tolerance_vector_noise() -> None:
    values = [4.0]
    exact = np.asarray([[1.0], [0.0]], dtype=np.float64)
    negligible_noise = np.asarray([[1.0], [1.0e-14]], dtype=np.float64)
    material_change = np.asarray([[1.0], [1.0e-8]], dtype=np.float64)

    assert raw_modes_sha256(values, exact) != raw_modes_sha256(
        values,
        negligible_noise,
    )
    assert semantic_modes_sha256(values, exact) == semantic_modes_sha256(
        values,
        negligible_noise,
    )
    assert semantic_modes_sha256(values, exact) != semantic_modes_sha256(
        values,
        material_change,
    )


def test_modal_kernel_rejects_request_that_cuts_repeated_cluster() -> None:
    with pytest.raises(ModalAnalysisError, match="cuts a repeated or clustered"):
        solve_modal_modes(
            np.diag([4.0, 4.0, 9.0]),
            np.eye(3, dtype=np.float64),
            mode_count=1,
        )


@pytest.mark.parametrize(
    ("stiffness", "mass", "message"),
    [
        (np.eye(2), np.diag([1.0, 0.0]), "mass must be positive definite"),
        (
            np.asarray([[1.0, 0.1], [0.0, 1.0]]),
            np.eye(2),
            "symmetry error",
        ),
        (np.diag([-1.0, 2.0]), np.eye(2), "positive-semidefinite contract"),
    ],
)
def test_modal_kernel_rejects_invalid_matrix_contracts(
    stiffness: np.ndarray,
    mass: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(ModalAnalysisError, match=message):
        solve_modal_modes(stiffness, mass, mode_count=1)


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("rigid_mode_relative_tolerance", -1.0),
        ("residual_relative_tolerance", float("nan")),
        ("orthogonality_tolerance", True),
    ],
)
def test_modal_kernel_rejects_invalid_tolerances(keyword: str, value: float) -> None:
    with pytest.raises(ModalAnalysisError, match=keyword):
        solve_modal_modes(
            np.eye(2),
            np.eye(2),
            mode_count=1,
            **{keyword: value},
        )
