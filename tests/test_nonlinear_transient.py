"""Focused contracts for the bounded nonlinear transient reference path."""

from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from structural_analysis.solvers.nonlinear.transient import (
    NONLINEAR_TRANSIENT_PROFILE,
    BilinearMaterialState,
    BilinearOscillator,
    NonlinearTransientConfig,
    NonlinearTransientError,
    evaluate_bilinear_restoring_force,
    resume_bilinear_transient,
    solve_bilinear_transient,
)


def test_linear_free_vibration_matches_closed_form_and_conserves_energy() -> None:
    model = BilinearOscillator(
        mass_kn_s2_per_m=1.0,
        elastic_stiffness_kn_per_m=4.0,
        yield_force_kn=1000.0,
        post_yield_stiffness_ratio=0.05,
    )
    config = NonlinearTransientConfig(time_step_s=0.005)

    solution = solve_bilinear_transient(
        model,
        [0.0] * 201,
        config=config,
        initial_displacement_m=0.1,
    )

    exact = 0.1 * math.cos(2.0)
    assert solution.steps[-1].displacement_m == pytest.approx(exact, abs=2.0e-6)
    assert solution.maximum_absolute_energy_balance_error_kn_m <= 5.0e-14
    assert solution.maximum_relative_residual <= 2.0e-12
    assert solution.yielded_step_count == 0
    assert solution.profile == NONLINEAR_TRANSIENT_PROFILE
    assert solution.deterministic is True
    assert solution.regularization_used is False
    assert solution.fallback_used is False
    assert solution.contract_pass is True


def test_bilinear_return_mapping_has_consistent_elastic_and_plastic_tangents() -> None:
    model = BilinearOscillator(
        mass_kn_s2_per_m=1.0,
        elastic_stiffness_kn_per_m=100.0,
        yield_force_kn=5.0,
        post_yield_stiffness_ratio=0.1,
    )
    state = BilinearMaterialState()

    elastic = evaluate_bilinear_restoring_force(model, 0.02, state)
    plastic = evaluate_bilinear_restoring_force(model, 0.10, state)
    increment = 1.0e-7
    perturbed = evaluate_bilinear_restoring_force(model, 0.10 + increment, state)

    assert elastic.yielded is False
    assert elastic.force_kn == pytest.approx(2.0)
    assert elastic.tangent_kn_per_m == pytest.approx(100.0)
    assert plastic.yielded is True
    assert plastic.force_kn == pytest.approx(5.5)
    assert plastic.tangent_kn_per_m == pytest.approx(10.0)
    assert (perturbed.force_kn - plastic.force_kn) / increment == pytest.approx(
        plastic.tangent_kn_per_m,
        rel=1.0e-8,
    )
    assert plastic.state.plastic_dissipation_kn_m > 0.0


def test_cyclic_nonlinear_history_accumulates_path_state_without_fallback() -> None:
    model = BilinearOscillator(
        mass_kn_s2_per_m=0.5,
        elastic_stiffness_kn_per_m=1000.0,
        yield_force_kn=5.0,
        post_yield_stiffness_ratio=0.05,
        damping_kn_s_per_m=0.5,
    )
    config = NonlinearTransientConfig(time_step_s=0.01)
    forces = [15.0 * math.sin(2.0 * math.pi * index * 0.01) for index in range(401)]

    solution = solve_bilinear_transient(model, forces, config=config)
    terminal_state = solution.checkpoints[-1].material_state

    assert solution.yielded_step_count > 100
    assert terminal_state.cumulative_plastic_displacement_m > 1.0
    assert terminal_state.plastic_dissipation_kn_m > 1.0
    assert terminal_state.plastic_displacement_m < 0.0
    assert solution.maximum_relative_residual <= 1.0e-10
    assert all(step.newton_iterations <= 3 for step in solution.steps[1:])
    assert solution.fallback_used is False


def test_checkpoint_resume_reproduces_full_chain_exactly() -> None:
    model = BilinearOscillator(0.5, 1000.0, 5.0, 0.05, 0.5)
    config = NonlinearTransientConfig(time_step_s=0.01)
    forces = [12.0 * math.sin(0.07 * index) for index in range(241)]

    full = solve_bilinear_transient(model, forces, config=config)
    prefix = solve_bilinear_transient(model, forces[:121], config=config)
    resumed = resume_bilinear_transient(
        model,
        prefix.checkpoints[-1],
        forces[121:],
        config=config,
    )
    joined = (*prefix.checkpoints, *resumed.checkpoints[1:])

    assert joined == full.checkpoints
    assert resumed.checkpoints[-1] == full.checkpoints[-1]
    assert resumed.steps[-1] == full.steps[-1]
    assert resumed.start_step_index == 120
    assert resumed.end_step_index == 240
    assert full.exact_checkpoint_resume_supported is True
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "src/structural_analysis/schemas/nonlinear_transient_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(full.checkpoints[-1].to_dict())


def test_checkpoint_tamper_and_cross_model_resume_fail_closed() -> None:
    model = BilinearOscillator(1.0, 100.0, 5.0, 0.05)
    config = NonlinearTransientConfig(time_step_s=0.01)
    solution = solve_bilinear_transient(model, [0.0, 1.0, 2.0], config=config)
    checkpoint = solution.checkpoints[-1]

    with pytest.raises(NonlinearTransientError, match="checkpoint hash mismatch"):
        resume_bilinear_transient(
            model,
            replace(checkpoint, displacement_m=checkpoint.displacement_m + 0.01),
            [0.0],
            config=config,
        )

    other_model = replace(model, mass_kn_s2_per_m=2.0)
    with pytest.raises(NonlinearTransientError, match="model hash mismatch"):
        resume_bilinear_transient(
            other_model,
            checkpoint,
            [0.0],
            config=config,
        )


def test_invalid_profile_inputs_and_newton_failure_do_not_fallback() -> None:
    with pytest.raises(ValueError, match="post_yield_stiffness_ratio"):
        BilinearOscillator(1.0, 100.0, 5.0, 1.0)
    with pytest.raises(ValueError, match="average acceleration"):
        NonlinearTransientConfig(time_step_s=0.01, newmark_beta=0.3)
    with pytest.raises(ValueError, match="initial value"):
        solve_bilinear_transient(
            BilinearOscillator(1.0, 100.0, 5.0, 0.0),
            [],
            config=NonlinearTransientConfig(time_step_s=0.01),
        )

    with pytest.raises(NonlinearTransientError, match="failed Newton convergence"):
        solve_bilinear_transient(
            BilinearOscillator(1.0, 100.0, 5.0, 0.0),
            [0.0, 100.0],
            config=NonlinearTransientConfig(
                time_step_s=0.01,
                maximum_iterations=1,
            ),
        )
