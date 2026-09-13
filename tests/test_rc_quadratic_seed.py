"""Causal optional baseline, including nonuniform and reversed target paths."""

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext,
    quadratic_seed,
)


def context(targets=(0.0, 0.2, 0.7), target=1.1):
    return RCControlSeedContext(
        problem_contract_hash="sha256:" + "a" * 64,
        control_global_dof=1,
        control_free_index=1,
        target_m=target,
        accepted_targets_m=targets,
        accepted_augmented_coordinates_m=tuple(
            (2 + 3 * t + 4 * t * t, t, 7 - 2 * t) for t in targets
        ),
    )


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_nonuniform_quadratic_and_linear_coordinates(sign):
    c = context(tuple(sign * x for x in (0.0, 0.2, 0.7)), sign * 1.1)
    original = c.to_dict()
    t = c.target_m
    assert quadratic_seed(c) == pytest.approx((2 + 3 * t + 4 * t * t, t, 7 - 2 * t))
    assert quadratic_seed(c)[1] == t
    assert c.to_dict() == original


@pytest.mark.parametrize(
    "targets,target",
    [
        ((), 1.0),
        ((0.0,), 1.0),
        ((0.0, 0.5), 1.0),
        ((0.0, 0.0, 0.5), 1.0),
        ((0.0, 0.5, 0.5), 1.0),
        ((0.0, 0.5, 1.0), 1.0),
        ((0.0, 1.0, 0.5), 0.0),
        ((0.0, 0.5, 1.0), 0.5),
        ((0.0, 0.5, 1.0), float("inf")),
    ],
)
def test_abstention_leaves_fallback_to_caller(targets, target):
    assert quadratic_seed(context(targets, target)) is None


def test_only_last_three_accepted_states_enter_prediction():
    c = context()
    prefixed = replace(
        c,
        accepted_targets_m=(-999.0, *c.accepted_targets_m),
        accepted_augmented_coordinates_m=(
            (float("nan"),) * 3,
            *c.accepted_augmented_coordinates_m,
        ),
        committed_material_state_json='{"unused": true}',
    )
    assert quadratic_seed(prefixed) == quadratic_seed(c)


def test_nonfinite_arithmetic_abstains_without_runtime_warning():
    c = context()
    c = replace(
        c,
        accepted_augmented_coordinates_m=(
            (1e308, 0, 0),
            (-1e308, 0.2, 0),
            (1e308, 0.7, 0),
        ),
    )
    with np.errstate(all="raise"):
        assert quadratic_seed(c) is None


def test_tiny_monotone_increments_do_not_underflow_sign_gate():
    targets = (0.0, 1e-180, 2e-180)
    c = replace(
        context(targets, 3e-180),
        accepted_augmented_coordinates_m=tuple((t, t, t) for t in targets),
    )
    assert quadratic_seed(c) == (3e-180,) * 3
