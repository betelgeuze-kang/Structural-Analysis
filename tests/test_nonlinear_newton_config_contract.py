from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("residual_tolerance", 0.0, "residual_tolerance"),
        ("residual_tolerance", -1.0e-8, "residual_tolerance"),
        ("residual_tolerance", math.inf, "residual_tolerance"),
        ("residual_tolerance", -math.inf, "residual_tolerance"),
        ("residual_tolerance", math.nan, "residual_tolerance"),
        ("residual_tolerance", True, "residual_tolerance"),
        ("residual_tolerance", "1e-8", "residual_tolerance"),
        ("increment_tolerance", 0.0, "increment_tolerance"),
        ("increment_tolerance", -1.0e-12, "increment_tolerance"),
        ("increment_tolerance", math.inf, "increment_tolerance"),
        ("increment_tolerance", math.nan, "increment_tolerance"),
        ("increment_tolerance", False, "increment_tolerance"),
    ),
)
def test_newton_config_rejects_nonpositive_or_nonfinite_tolerances(
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = {field: value}

    with pytest.raises(ValueError, match=message):
        NewtonRaphsonConfig(**kwargs)


@pytest.mark.parametrize("value", (-1, 1.5, True, "5"))
def test_newton_config_rejects_invalid_iteration_limit(value: object) -> None:
    with pytest.raises(ValueError, match="max_iterations"):
        NewtonRaphsonConfig(max_iterations=value)


@pytest.mark.parametrize(
    "alphas",
    (
        (),
        [],
        (1.0, 0.5, 0.5),
        (0.5, 1.0),
        (1.0, 0.0),
        (1.0, -0.5),
        (1.0, math.nan),
        (1.0, math.inf),
        (1.1, 0.5),
        (True,),
        "1.0,0.5",
    ),
)
def test_newton_config_rejects_invalid_backtracking_sequence(
    alphas: object,
) -> None:
    with pytest.raises(ValueError, match="line_search_alphas"):
        NewtonRaphsonConfig(line_search_alphas=alphas)


@pytest.mark.parametrize("backend", ("", "   ", None, 1))
def test_newton_config_rejects_invalid_backend_identifier(
    backend: object,
) -> None:
    with pytest.raises(ValueError, match="matrix_backend"):
        NewtonRaphsonConfig(matrix_backend=backend)


def test_newton_config_normalizes_supported_numeric_scalar_types() -> None:
    config = NewtonRaphsonConfig(
        residual_tolerance=np.float64(1.0e-9),
        increment_tolerance=np.float32(1.0e-11),
        max_iterations=np.int64(7),
        line_search_alphas=[np.float64(0.75), np.float32(0.25)],
    )

    assert type(config.residual_tolerance) is float
    assert type(config.increment_tolerance) is float
    assert type(config.max_iterations) is int
    assert config.max_iterations == 7
    assert config.line_search_alphas == (0.75, 0.25)
    assert all(type(value) is float for value in config.line_search_alphas)


def test_infinite_gate_false_pass_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="residual_tolerance"):
        NewtonRaphsonConfig(
            residual_tolerance=math.inf,
            increment_tolerance=math.inf,
        )
