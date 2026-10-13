"""Original-metric accuracy and domain tests, not experimental RC validation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.optimize import brentq

from structural_analysis import AnalysisConfig, analyze, load_model
from structural_analysis.solvers.modal import ModalAnalysisError, solve_modal_modes
import structural_analysis.solvers.modal.solver as kernel


FIXED_FRAME = Path(__file__).parent / "fixtures" / "modal_rc_parameters_40_frames.json"


def test_fixed_80_dof_public_frame_meets_original_accuracy_without_hook() -> None:
    # The unchanged input is an authored elastic software case, not a specimen.
    result = analyze(
        load_model(FIXED_FRAME),
        AnalysisConfig(analysis_type="modal", mode_count=3, tolerance=1.0e-9),
    )
    assert result.status == "ready"
    assert result.unsupported_features == []
    assert result.metrics["free_dof_count"] == 80
    assert result.metrics["mode_count"] == 3
    assert result.metrics["eigen_extraction_profile"] == kernel.RECIPROCAL_EXTRACTION_PROFILE
    assert result.metrics["rigid_mode_count"] == 0
    assert result.metrics["mass_orthogonality_error_inf"] <= 1.0e-9
    assert result.metrics["stiffness_diagonalization_error_inf"] <= 1.0e-9
    assert result.metrics["fallback_used"] is False
    assert result.metrics["regularization_used"] is False
    assert result.metrics["sparse_modal_backend_connected"] is False
    assert result.metrics["release_readiness"] is False
    assert max(row["residual_norm"] for row in result.convergence_history) <= 1.0e-9

    # Independent continuous beam eigenvalues; this looser bound measures mesh
    # discretization, and does not replace the original 1e-9 algebraic gates.
    roots = [
        brentq(lambda x: math.cosh(x) * math.cos(x) + 1.0, left, right)
        for left, right in [(1.0, 2.0), (4.0, 5.0), (7.0, 8.0)]
    ]
    e_n_per_m2 = 30_000_000.0 * 1000.0  # Input's default kN/m2 -> N/m2.
    inertia = 0.002133333333333334
    density_times_area = 2500.0 * 0.16
    expected = [b**4 * e_n_per_m2 * inertia / (density_times_area * 3.0**4) for b in roots]
    actual = [row["eigenvalue_rad2_per_s2"] for row in result.metrics["modes"]]
    assert actual == pytest.approx(expected, rel=1.0e-5)


def test_rotated_semidefinite_problem_keeps_rigid_mode_and_direct_route() -> None:
    solution = solve_modal_modes(
        np.asarray([[1.0, -1.0], [-1.0, 1.0]]),
        np.diag([2.0, 3.0]),
        mode_count=1,
    )
    assert solution.eigen_extraction_profile == kernel.DIRECT_EXTRACTION_PROFILE
    assert solution.rigid_mode_count == 1
    assert solution.modes[0].eigenvalue_rad2_per_s2 == pytest.approx(5.0 / 6.0)
    assert solution.modes[0].residual_relative_inf <= 1.0e-14
    assert not solution.fallback_used


def test_ill_conditioned_mass_uses_direct_spectral_rigid_classification() -> None:
    # K alone is perfectly conditioned; it does not certify the whole pencil.
    solution = solve_modal_modes(
        np.eye(3), np.diag([1.0e-14, 1.0, 1.0]), mode_count=1
    )
    assert solution.eigen_extraction_profile == kernel.DIRECT_EXTRACTION_PROFILE
    assert solution.rigid_mode_count == 2
    assert solution.rigid_mode_spectral_scale == pytest.approx(1.0e14)
    assert solution.modes[0].eigenvalue_rad2_per_s2 == pytest.approx(1.0e14)
    assert not solution.fallback_used


def test_positive_near_zero_stiffness_preserves_zero_rigid_tolerance() -> None:
    solution = solve_modal_modes(
        np.diag([5.0e-15, 4.0]),
        np.eye(2),
        mode_count=2,
        rigid_mode_relative_tolerance=0.0,
    )
    assert solution.eigen_extraction_profile == kernel.DIRECT_EXTRACTION_PROFILE
    assert solution.rigid_mode_count == 0
    assert [row.eigenvalue_rad2_per_s2 for row in solution.modes] == pytest.approx(
        [5.0e-15, 4.0], rel=1.0e-14, abs=0.0
    )


def test_repeated_eigenspace_with_nondiagonal_mass_is_deterministic() -> None:
    mass = np.asarray([[2.0, 0.1, 0.0], [0.1, 1.0, 0.0], [0.0, 0.0, 3.0]])
    factor = np.linalg.cholesky(mass)
    stiffness = factor @ np.diag([4.0, 4.0, 9.0]) @ factor.T
    first = solve_modal_modes(stiffness, mass, mode_count=3)
    second = solve_modal_modes(stiffness, mass, mode_count=3)
    assert first.to_dict() == second.to_dict()
    assert first.eigen_extraction_profile == kernel.RECIPROCAL_EXTRACTION_PROFILE
    assert [row.eigenvalue_rad2_per_s2 for row in first.modes] == pytest.approx([4, 4, 9])
    assert first.mass_orthogonality_error_inf <= 1.0e-12
    with pytest.raises(ModalAnalysisError, match="cuts a repeated or clustered"):
        solve_modal_modes(stiffness, mass, mode_count=1)


def test_reciprocal_failure_is_not_retried_with_direct_vectors(monkeypatch: Any) -> None:
    original = kernel.eigh
    calls: list[bool] = []

    def failing_extraction(left: np.ndarray, right: np.ndarray, **kwargs: Any) -> Any:
        values_only = bool(kwargs.get("eigvals_only", False))
        calls.append(values_only)
        if values_only:
            return original(left, right, **kwargs)
        raise np.linalg.LinAlgError("controlled reciprocal extraction failure")

    monkeypatch.setattr(kernel, "eigh", failing_extraction)
    with pytest.raises(ModalAnalysisError, match="controlled reciprocal extraction failure"):
        solve_modal_modes(np.diag([4.0, 9.0]), np.eye(2), mode_count=2)
    assert calls == [True, False]


@pytest.mark.parametrize("bad_value", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_reciprocal_output_is_rejected(monkeypatch: Any, bad_value: float) -> None:
    original = kernel.eigh

    def corrupted_extraction(left: np.ndarray, right: np.ndarray, **kwargs: Any) -> Any:
        if kwargs.get("eigvals_only"):
            return original(left, right, **kwargs)
        return np.asarray([bad_value, 0.25]), np.eye(2)

    monkeypatch.setattr(kernel, "eigh", corrupted_extraction)
    with pytest.raises(ModalAnalysisError, match="reciprocal extraction must be finite and positive"):
        solve_modal_modes(np.diag([4.0, 9.0]), np.eye(2), mode_count=2)
