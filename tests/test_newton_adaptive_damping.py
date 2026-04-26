from __future__ import annotations

import math

import numpy as np

from newton_adaptive_damping import AdaptiveNewtonConfig, solve_with_adaptive_damping


def test_adaptive_newton_converges_on_nonlinear_system() -> None:
    def residual(x: np.ndarray) -> np.ndarray:
        return np.array(
            [
                x[0] * x[0] - 2.0,
                math.tanh(x[1]) - math.tanh(0.5),
            ],
            dtype=float,
        )

    def jacobian(x: np.ndarray) -> np.ndarray:
        return np.array(
            [
                [2.0 * x[0], 0.0],
                [0.0, 1.0 / math.cosh(x[1]) ** 2],
            ],
            dtype=float,
        )

    cfg = AdaptiveNewtonConfig(max_iter=100, tol=1e-8)
    result = solve_with_adaptive_damping(np.array([2.5, -1.5]), residual, jacobian, cfg)

    assert result["converged"] is True
    assert int(result["iterations"]) <= 100
    assert float(result["residual_norm_final"]) <= 1e-6
    assert len(result["lambda_history"]) >= 2


def test_adaptive_newton_handles_near_singular_jacobian() -> None:
    def residual(x: np.ndarray) -> np.ndarray:
        return np.array([x[0] ** 3, x[1] - 1.0], dtype=float)

    def jacobian(x: np.ndarray) -> np.ndarray:
        return np.array([[3.0 * x[0] * x[0], 0.0], [0.0, 1.0]], dtype=float)

    cfg = AdaptiveNewtonConfig(max_iter=60, tol=1e-8, lambda_init=1e-3)
    result = solve_with_adaptive_damping(np.array([0.2, 2.0]), residual, jacobian, cfg)

    assert int(result["iterations"]) > 0
    assert math.isfinite(float(result["residual_norm_final"]))
    assert all(math.isfinite(float(v)) for v in result["lambda_history"])


def test_adaptive_newton_records_line_search_cutback_history() -> None:
    def residual(x: np.ndarray) -> np.ndarray:
        value = float(x[0])
        if value <= 0.0:
            return np.array([1.0e9], dtype=float)
        return np.array([math.log(value)], dtype=float)

    def jacobian(x: np.ndarray) -> np.ndarray:
        value = max(float(x[0]), 1.0e-9)
        return np.array([[1.0 / value]], dtype=float)

    cfg = AdaptiveNewtonConfig(max_iter=40, tol=1e-8, lambda_init=1e-2)
    result = solve_with_adaptive_damping(np.array([10.0]), residual, jacobian, cfg)

    assert result["converged"] is True
    assert int(result["line_search_backtracks"]) >= 1
    assert int(result["cutback_count"]) >= 1
    assert any("cutback" in str(row.get("event", "")) for row in result["event_history"])
    assert all("residual_after" in row for row in result["event_history"])
