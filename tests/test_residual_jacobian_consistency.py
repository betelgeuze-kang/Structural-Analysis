from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.solvers.nonlinear.residual_jacobian_consistency import (
    DirectionalConsistencyConfig,
    ResidualJacobianConsistencyError,
    probe_residual_jacobian_directional_consistency,
    validate_directional_receipt,
)


def _residual(state: np.ndarray) -> np.ndarray:
    x, y = state
    return np.asarray([x * x + 3.0 * y, np.sin(x) - y**3], dtype=np.float64)


def _jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
    x, y = state
    jacobian = np.asarray(
        [[2.0 * x, 3.0], [np.cos(x), -3.0 * y * y]],
        dtype=np.float64,
    )
    return jacobian @ direction


def test_exact_nonlinear_operator_passes_multiple_directional_steps() -> None:
    receipt = probe_residual_jacobian_directional_consistency(
        source_commit_sha="a" * 40,
        operator_id="bounded_nonlinear_reference.v1",
        backend_id="cpu_fp64",
        accepted_state=np.asarray([0.4, -0.2]),
        direction=np.asarray([2.0, -1.0]),
        residual=_residual,
        jacobian_vector_product=_jvp,
    )

    validate_directional_receipt(receipt)
    assert receipt.consistent_residual_jacobian_newton_gate_passed is True
    assert receipt.passing_step_count >= 2
    assert receipt.numerical_authority == "diagnostic_only"
    assert receipt.product_authority == "none"
    assert receipt.equation_count == 2
    assert all(row.physical_step > 0.0 for row in receipt.steps)


def test_inconsistent_jacobian_fails_without_promoting_authority() -> None:
    def wrong_jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
        return _jvp(state, direction) + np.asarray([0.2, -0.1])

    receipt = probe_residual_jacobian_directional_consistency(
        source_commit_sha="b" * 40,
        operator_id="wrong_operator.v1",
        backend_id="cpu_fp64",
        accepted_state=[0.4, -0.2],
        direction=[1.0, 1.0],
        residual=_residual,
        jacobian_vector_product=wrong_jvp,
    )

    validate_directional_receipt(receipt)
    assert receipt.consistent_residual_jacobian_newton_gate_passed is False
    assert receipt.passing_step_count == 0
    assert receipt.numerical_authority == "diagnostic_only"
    assert receipt.product_authority == "none"


def test_gate_rejects_fallback_regularization_and_nonphysical_profiles() -> None:
    with pytest.raises(
        ResidualJacobianConsistencyError,
        match="fallback_or_regularization_forbidden",
    ):
        DirectionalConsistencyConfig(fallback_allowed=True).validate()
    with pytest.raises(ResidualJacobianConsistencyError, match="physical_residual"):
        DirectionalConsistencyConfig(residual_kind="fixed_point_residual").validate()
    with pytest.raises(ResidualJacobianConsistencyError, match="accepted_state"):
        DirectionalConsistencyConfig(jacobian_epoch="trial_state").validate()


def test_callbacks_receive_read_only_state_and_direction() -> None:
    mutation_attempts: list[str] = []

    def residual(state: np.ndarray) -> np.ndarray:
        assert state.flags.writeable is False
        try:
            state[0] = 99.0
        except ValueError:
            mutation_attempts.append("residual")
        return state * state

    def jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
        assert state.flags.writeable is False
        assert direction.flags.writeable is False
        try:
            direction[0] = 99.0
        except ValueError:
            mutation_attempts.append("jvp")
        return 2.0 * state * direction

    receipt = probe_residual_jacobian_directional_consistency(
        source_commit_sha="c" * 40,
        operator_id="immutable_callback_reference.v1",
        backend_id="cpu_fp64",
        accepted_state=[0.3, -0.4],
        direction=[1.0, 2.0],
        residual=residual,
        jacobian_vector_product=jvp,
    )

    assert receipt.consistent_residual_jacobian_newton_gate_passed is True
    assert "residual" in mutation_attempts
    assert "jvp" in mutation_attempts


def test_nonfinite_and_shape_mismatch_fail_closed() -> None:
    with pytest.raises(ResidualJacobianConsistencyError, match="accepted_state_nonfinite"):
        probe_residual_jacobian_directional_consistency(
            source_commit_sha="d" * 40,
            operator_id="invalid.v1",
            backend_id="cpu_fp64",
            accepted_state=[np.nan],
            direction=[1.0],
            residual=lambda state: state,
            jacobian_vector_product=lambda state, direction: direction,
        )

    with pytest.raises(ResidualJacobianConsistencyError, match="residual_shape_mismatch"):
        probe_residual_jacobian_directional_consistency(
            source_commit_sha="e" * 40,
            operator_id="invalid-shape.v1",
            backend_id="cpu_fp64",
            accepted_state=[1.0, 2.0],
            direction=[1.0, 0.0],
            residual=lambda state: np.asarray([state[0]]),
            jacobian_vector_product=lambda state, direction: direction,
        )
