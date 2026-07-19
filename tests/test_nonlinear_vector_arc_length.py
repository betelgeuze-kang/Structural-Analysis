from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.benchmark.coupled_shallow_arch_arc_length import (
    COUPLED_SHALLOW_ARCH_VECTOR_ARC_LENGTH_CONFIG,
    CoupledShallowArchArcLengthProblem,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA,
    VECTOR_ARC_LENGTH_RESIDUAL_FORMULA,
    VectorArcLengthConfig,
    VectorArcLengthContractError,
    validate_vector_arc_length_checkpoint,
    vector_arc_length_continuation,
)


def _config(**overrides) -> VectorArcLengthConfig:
    values = {
        "failed_step_reduction": (
            COUPLED_SHALLOW_ARCH_VECTOR_ARC_LENGTH_CONFIG.failed_step_reduction
        ),
        "maximum_corrector_iterations": (
            COUPLED_SHALLOW_ARCH_VECTOR_ARC_LENGTH_CONFIG.maximum_corrector_iterations
        ),
    }
    values.update(overrides)
    return VectorArcLengthConfig(**values)


def test_vector_arc_length_follows_coupled_two_dof_snapthrough_path() -> None:
    problem = CoupledShallowArchArcLengthProblem()
    result = vector_arc_length_continuation(problem, config=_config())
    metrics = result.metrics

    assert result.status == "ready"
    assert result.terminal_reason == "target_monitor_displacement_reached"
    assert metrics["contract_pass"] is True
    assert metrics["equation_count"] == 2
    assert metrics["descending_load_branch_observed"] is True
    assert metrics["negative_load_factor_observed"] is True
    assert metrics["rehardening_load_branch_observed"] is True
    assert metrics["fallback_count"] == 0
    assert metrics["regularization_count"] == 0
    assert metrics["maximum_checkpoint_residual_inf_norm_kn"] <= 1.0e-10
    assert metrics["maximum_accepted_constraint_residual_m2"] <= 1.0e-12

    for checkpoint in result.checkpoints:
        primary, coupled = checkpoint.free_displacements_m
        assert coupled == pytest.approx(problem.coupling_ratio * primary, abs=1.0e-12)
        assert checkpoint.load_factor == pytest.approx(
            problem.arch.internal_force_kn(primary),
            abs=1.0e-10,
        )


def test_vector_arc_length_has_exact_failed_step_rollback() -> None:
    result = vector_arc_length_continuation(
        CoupledShallowArchArcLengthProblem(),
        config=_config(),
    )
    rejected = [row for row in result.attempts if row["accepted"] is False]

    assert len(rejected) >= 1
    assert all(row["rollback_exact"] is True for row in rejected)
    assert all(
        row["accepted_state_hash_before"] == row["accepted_state_hash_after"]
        for row in rejected
    )
    assert all(row["fallback_used"] is False for row in result.attempts)
    assert all(row["regularization_used"] is False for row in result.attempts)


def test_vector_arc_length_restart_is_bit_identical() -> None:
    problem = CoupledShallowArchArcLengthProblem()
    config = _config()
    one_shot = vector_arc_length_continuation(problem, config=config)
    midpoint = one_shot.checkpoints[len(one_shot.checkpoints) // 2]
    restarted = vector_arc_length_continuation(
        problem,
        config=config,
        resume_from=midpoint,
    )

    assert restarted.status == "ready"
    assert restarted.initial_checkpoint == midpoint
    assert restarted.final_checkpoint == one_shot.final_checkpoint


def test_vector_checkpoint_binds_the_path_configuration() -> None:
    problem = CoupledShallowArchArcLengthProblem()
    config = _config()
    checkpoint = vector_arc_length_continuation(
        problem,
        config=config,
    ).checkpoints[3]

    with pytest.raises(VectorArcLengthContractError, match="path contract"):
        vector_arc_length_continuation(
            problem,
            config=replace(config, load_factor_metric_scale_m=0.003),
            resume_from=checkpoint,
        )


def test_vector_checkpoint_tamper_fails_closed() -> None:
    checkpoint = vector_arc_length_continuation(
        CoupledShallowArchArcLengthProblem(),
        config=_config(),
    ).checkpoints[3]
    tampered_values = list(checkpoint.free_displacements_m)
    tampered_values[0] += 1.0e-6
    tampered = replace(
        checkpoint,
        free_displacements_m=tuple(tampered_values),
    )

    with pytest.raises(VectorArcLengthContractError, match="state_hash mismatch"):
        validate_vector_arc_length_checkpoint(tampered)


def test_vector_arc_length_is_deterministic_and_formula_explicit() -> None:
    problem = CoupledShallowArchArcLengthProblem()
    config = _config()
    first = vector_arc_length_continuation(problem, config=config).to_dict()
    second = vector_arc_length_continuation(problem, config=config).to_dict()

    assert first == second
    assert first["residual_formula"] == VECTOR_ARC_LENGTH_RESIDUAL_FORMULA
    assert first["constraint_formula"] == VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA
    assert first["path_contract_hash"].startswith("sha256:")


def test_vector_consistent_tangent_matches_centered_finite_difference() -> None:
    problem = CoupledShallowArchArcLengthProblem()
    displacement = np.asarray([0.21, 0.0735], dtype=float)
    tangent = problem.consistent_tangent_kn_per_m(displacement)
    step = 1.0e-7
    finite_difference = np.column_stack(
        [
            (
                problem.internal_force_kn(
                    displacement + step * np.eye(2, dtype=float)[:, column]
                )
                - problem.internal_force_kn(
                    displacement - step * np.eye(2, dtype=float)[:, column]
                )
            )
            / (2.0 * step)
            for column in range(2)
        ]
    )

    np.testing.assert_allclose(tangent, finite_difference, rtol=1.0e-8, atol=1.0e-5)
    np.testing.assert_allclose(tangent, tangent.T, rtol=0.0, atol=0.0)


@pytest.mark.parametrize(
    "config",
    [
        _config(target_monitor_dof_index=2),
        _config(target_direction=0),
        _config(displacement_metric_weights=(1.0,)),
        _config(displacement_metric_weights=(1.0, 0.0)),
        _config(maximum_attempt_count=2.5),  # type: ignore[arg-type]
    ],
)
def test_invalid_vector_arc_length_config_fails_closed(
    config: VectorArcLengthConfig,
) -> None:
    with pytest.raises(VectorArcLengthContractError):
        vector_arc_length_continuation(
            CoupledShallowArchArcLengthProblem(),
            config=config,
        )
