from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    newton_raphson_scalar,
    newton_raphson_vector,
)


@dataclass(frozen=True)
class _FlatResidualScalarProblem:
    case_id: str = "flat_residual_scalar_line_search_guard"
    external_force_kn: float = 0.0
    initial_displacement_m: float = 0.0

    def internal_force(self, displacement_m: float) -> float:
        del displacement_m
        return 1.0

    def tangent_stiffness(self, displacement_m: float) -> float:
        del displacement_m
        return 1.0

    def residual(self, displacement_m: float) -> float:
        del displacement_m
        return 1.0

    def reference_force_scale(self) -> float:
        return 1.0


@dataclass(frozen=True)
class _FlatResidualVectorProblem:
    case_id: str = "flat_residual_vector_line_search_guard"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([0.0], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert free_displacements_m.shape == (1,)
        return np.asarray([1.0], dtype=float), np.asarray([[1.0]], dtype=float)


def test_scalar_zero_applied_increment_cannot_masquerade_as_accepted_trial() -> None:
    solution = newton_raphson_scalar(
        _FlatResidualScalarProblem(),
        config=NewtonRaphsonConfig(max_iterations=5),
    )

    assert solution.status == "blocked"
    assert solution.displacement_m == 0.0
    assert solution.metrics["detail"] == "line_search_failed_to_reduce_residual"
    assert len(solution.convergence_history) == 1
    assert solution.convergence_history[0]["increment_gate_passed"] is True
    assert solution.convergence_history[0]["accepted"] is False
    assert solution.line_search_history[0]["selected_alpha"] == 0.0
    assert all(
        attempt["accepted"] is False
        for attempt in solution.line_search_history[0]["attempts"]
    )


def test_vector_zero_applied_increment_cannot_masquerade_as_accepted_trial() -> None:
    solution = newton_raphson_vector(
        _FlatResidualVectorProblem(),
        config=NewtonRaphsonConfig(max_iterations=5),
    )

    assert solution.status == "blocked"
    np.testing.assert_array_equal(
        solution.free_displacements_m,
        np.asarray([0.0], dtype=float),
    )
    assert solution.metrics["detail"] == "line_search_failed_to_reduce_residual"
    assert len(solution.convergence_history) == 1
    assert solution.convergence_history[0]["increment_gate_passed"] is True
    assert solution.convergence_history[0]["accepted"] is False
    assert solution.line_search_history[0]["selected_alpha"] == 0.0
    assert all(
        attempt["accepted"] is False
        for attempt in solution.line_search_history[0]["attempts"]
    )
