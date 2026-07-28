"""Contract tests for the deterministic linear-buckling eigen kernel."""

from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.benchmark.geometric_nonlinear import (
    assemble_euler_column_system,
)
from structural_analysis.solvers.buckling import (
    BucklingAnalysisError,
    solve_linear_buckling,
)
from structural_analysis.solvers.equation_scaling import (
    make_equation_scaling_6dof,
)


def test_singular_geometric_stiffness_filters_infinite_mode() -> None:
    solution = solve_linear_buckling(
        np.diag([6.0, 8.0, 10.0]),
        np.diag([3.0, 2.0, 0.0]),
        mode_count=2,
    )

    assert [mode.load_factor for mode in solution.modes] == pytest.approx([2.0, 4.0])
    assert solution.finite_positive_eigenvalue_count == 2
    assert solution.geometric_stiffness_positive_rank == 2
    assert solution.critical_load_factor == pytest.approx(2.0)
    assert max(mode.residual_relative_inf for mode in solution.modes) == 0.0
    assert solution.stiffness_orthogonality_error_inf <= 1.0e-14
    assert solution.geometric_diagonalization_error_inf <= 1.0e-14
    assert solution.regularization_applied is False
    assert solution.fallback_used is False
    assert solution.contract_pass is True


def test_small_scaled_geometric_stiffness_keeps_finite_mode() -> None:
    solution = solve_linear_buckling(
        np.eye(2, dtype=np.float64),
        np.diag([1.0e-15, 0.0]),
        mode_count=1,
    )

    assert solution.finite_positive_eigenvalue_count == 1
    assert solution.critical_load_factor == pytest.approx(1.0e15, rel=1.0e-14)
    assert solution.modes[0].residual_relative_inf <= 1.0e-14


def test_buckling_kernel_scaled_solve_preserves_physical_eigenproblem() -> None:
    stiffness = np.asarray([[100.0, 20.0], [20.0, 800.0]])
    geometric = np.asarray([[10.0, 1.0], [1.0, 20.0]])
    scaling = make_equation_scaling_6dof(
        reference_force=200.0,
        characteristic_length=4.0,
        dof_labels=("UX", "RZ"),
    )

    raw = solve_linear_buckling(stiffness, geometric, mode_count=2)
    scaled = solve_linear_buckling(
        stiffness,
        geometric,
        mode_count=2,
        equation_scaling=scaling,
    )

    assert [mode.load_factor for mode in scaled.modes] == pytest.approx(
        [mode.load_factor for mode in raw.modes],
        rel=1.0e-14,
    )
    assert scaled.equation_scaling_applied is True
    assert scaled.equation_scaling_hash == scaling.scaling_hash
    assert scaled.scaled_stiffness_condition_number is not None
    assert scaled.scaled_geometric_stiffness_condition_number is not None
    for mode in scaled.modes:
        assert mode.raw_translational_residual_norm is not None
        assert mode.raw_rotational_residual_norm is not None
        assert mode.scaled_residual_relative_inf is not None
        assert mode.scaled_residual_relative_inf <= 1.0e-14


def test_repeated_buckling_eigenspace_has_stable_coordinate_axis_basis() -> None:
    stiffness = np.diag([4.0, 4.0, 9.0])
    geometric = np.eye(3, dtype=np.float64)

    first = solve_linear_buckling(stiffness, geometric, mode_count=3)
    second = solve_linear_buckling(stiffness, geometric, mode_count=3)

    assert first.to_dict() == second.to_dict()
    assert [mode.max_component_normalized_shape for mode in first.modes] == [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]
    assert first.raw_result_hash == second.raw_result_hash
    assert first.semantic_result_hash == second.semantic_result_hash
    assert first.deterministic_mode_basis is True


def test_buckling_kernel_rejects_request_that_cuts_repeated_cluster() -> None:
    with pytest.raises(BucklingAnalysisError, match="cuts a repeated or clustered"):
        solve_linear_buckling(
            np.diag([4.0, 4.0, 9.0]),
            np.eye(3, dtype=np.float64),
            mode_count=1,
        )


def test_euler_column_kernel_matches_closed_form_critical_load() -> None:
    system = assemble_euler_column_system(element_count=16)
    solution = solve_linear_buckling(
        system.elastic_stiffness,
        system.unit_compression_geometric_stiffness,
        mode_count=1,
    )
    exact = math.pi**2 * system.flexural_rigidity_kn_m2 / system.length_m**2
    relative_error = abs(solution.critical_load_factor - exact) / exact

    assert relative_error <= 3.0e-6
    assert solution.modes[0].residual_relative_inf <= 1.0e-10
    assert solution.symmetry_projection_applied is False
    assert solution.regularization_applied is False
    assert solution.fallback_used is False


@pytest.mark.parametrize(
    ("stiffness", "geometric", "message"),
    [
        (np.diag([1.0, 0.0]), np.eye(2), "stiffness must be positive definite"),
        (np.eye(2), np.diag([1.0, -1.0]), "positive-semidefinite contract"),
        (
            np.eye(2),
            np.asarray([[1.0, 0.1], [0.0, 1.0]]),
            "symmetry error",
        ),
    ],
)
def test_buckling_kernel_rejects_invalid_matrix_contracts(
    stiffness: np.ndarray,
    geometric: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(BucklingAnalysisError, match=message):
        solve_linear_buckling(stiffness, geometric, mode_count=1)


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("finite_mode_relative_tolerance", -1.0),
        ("residual_relative_tolerance", float("inf")),
        ("orthogonality_tolerance", False),
    ],
)
def test_buckling_kernel_rejects_invalid_tolerances(
    keyword: str,
    value: float,
) -> None:
    with pytest.raises(BucklingAnalysisError, match=keyword):
        solve_linear_buckling(
            np.eye(2),
            np.eye(2),
            mode_count=2,
            **{keyword: value},
        )
