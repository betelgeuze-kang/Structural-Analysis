from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from structural_analysis.benchmark.geometric_nonlinear import TwoBarShallowArch
from structural_analysis.solvers.nonlinear.arc_length import (
    ARC_LENGTH_CONSTRAINT_FORMULA,
    ARC_LENGTH_EQUILIBRIUM_FORMULA,
    ArcLengthContractError,
    ScalarArcLengthConfig,
    scalar_arc_length_continuation,
    validate_scalar_arc_length_checkpoint,
)


@dataclass(frozen=True)
class ShallowArchArcLengthProblem:
    case_id: str = "two_bar_shallow_arch_arc_length"
    arch: TwoBarShallowArch = field(default_factory=TwoBarShallowArch)

    def initial_displacement_m(self) -> float:
        return 0.0

    def initial_load_kn(self) -> float:
        return 0.0

    def internal_force_kn(self, displacement_m: float) -> float:
        return self.arch.internal_force_kn(displacement_m)

    def consistent_tangent_kn_per_m(self, displacement_m: float) -> float:
        return self.arch.consistent_tangent_kn_per_m(displacement_m)


def test_arc_length_crosses_limit_point_and_follows_snapthrough_path() -> None:
    problem = ShallowArchArcLengthProblem()
    result = scalar_arc_length_continuation(problem)
    metrics = result.metrics

    assert result.status == "ready"
    assert result.terminal_reason == "target_displacement_reached"
    assert metrics["contract_pass"] is True
    assert metrics["target_displacement_reached"] is True
    assert metrics["consistent_tangent_sign_change_observed"] is True
    assert metrics["descending_load_branch_observed"] is True
    assert metrics["negative_load_branch_observed"] is True
    assert metrics["rehardening_branch_observed"] is True
    assert metrics["displacement_monotonic_increasing"] is True
    assert metrics["maximum_checkpoint_equilibrium_residual_kn"] <= 1.0e-10

    exact_displacement, exact_load = problem.arch.first_limit_point()
    rows = list(result.checkpoints)
    below = max(
        (row for row in rows if row.displacement_m < exact_displacement),
        key=lambda row: row.displacement_m,
    )
    above = min(
        (row for row in rows if row.displacement_m > exact_displacement),
        key=lambda row: row.displacement_m,
    )
    assert below.displacement_m < exact_displacement < above.displacement_m
    assert below.load_kn < exact_load
    assert above.load_kn < exact_load
    assert max(below.load_kn, above.load_kn) == pytest.approx(exact_load, rel=0.02)


def test_failed_corrector_rolls_back_hash_and_reduces_arc_length() -> None:
    result = scalar_arc_length_continuation(ShallowArchArcLengthProblem())
    rejected = [row for row in result.attempts if row["accepted"] is False]

    assert len(rejected) == 1
    row = rejected[0]
    assert row["stop_reason"] == "maximum_corrector_iterations_exhausted"
    assert row["arc_length_m"] == pytest.approx(0.08)
    assert row["next_arc_length_m"] == pytest.approx(0.04)
    assert row["accepted_state_hash_before"] == row["accepted_state_hash_after"]
    assert row["accepted_displacement_m_before"] == row["accepted_displacement_m_after"]
    assert row["accepted_load_kn_before"] == row["accepted_load_kn_after"]
    assert row["rollback_exact"] is True
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0


def test_checkpoint_restart_reaches_bit_identical_terminal_state() -> None:
    problem = ShallowArchArcLengthProblem()
    one_shot = scalar_arc_length_continuation(problem)
    midpoint = one_shot.checkpoints[7]
    restarted = scalar_arc_length_continuation(problem, resume_from=midpoint)

    assert restarted.status == "ready"
    assert restarted.initial_checkpoint.state_hash == midpoint.state_hash
    assert restarted.final_checkpoint == one_shot.final_checkpoint
    assert restarted.final_checkpoint.state_hash == one_shot.final_checkpoint.state_hash
    assert restarted.metrics["fallback_count"] == 0
    assert restarted.metrics["regularization_count"] == 0


def test_checkpoint_hash_tamper_fails_closed() -> None:
    checkpoint = scalar_arc_length_continuation(
        ShallowArchArcLengthProblem()
    ).checkpoints[3]
    tampered = replace(checkpoint, displacement_m=checkpoint.displacement_m + 1.0e-6)

    with pytest.raises(ArcLengthContractError, match="state_hash mismatch"):
        validate_scalar_arc_length_checkpoint(tampered)


def test_accepted_steps_satisfy_both_augmented_newton_gates() -> None:
    result = scalar_arc_length_continuation(ShallowArchArcLengthProblem())

    for attempt in result.attempts:
        if attempt["accepted"] is not True:
            continue
        assert abs(attempt["equilibrium_residual_kn"]) <= 1.0e-10
        assert abs(attempt["constraint_residual_m2"]) <= 1.0e-12
        assert attempt["corrector_history"][-1]["converged"] is True
        assert attempt["fallback_used"] is False
        assert attempt["regularization_used"] is False


def test_arc_length_result_is_deterministic_and_formula_explicit() -> None:
    first = scalar_arc_length_continuation(
        ShallowArchArcLengthProblem()
    ).to_dict()
    second = scalar_arc_length_continuation(
        ShallowArchArcLengthProblem()
    ).to_dict()

    assert first == second
    assert first["equilibrium_formula"] == ARC_LENGTH_EQUILIBRIUM_FORMULA
    assert first["constraint_formula"] == ARC_LENGTH_CONSTRAINT_FORMULA


@pytest.mark.parametrize(
    "config",
    [
        ScalarArcLengthConfig(initial_arc_length_m=0.0),
        ScalarArcLengthConfig(
            minimum_arc_length_m=0.09,
            initial_arc_length_m=0.08,
        ),
        ScalarArcLengthConfig(failed_step_reduction=1.0),
        ScalarArcLengthConfig(maximum_corrector_iterations=0),
        ScalarArcLengthConfig(maximum_attempt_count=1.5),  # type: ignore[arg-type]
    ],
)
def test_invalid_arc_length_configuration_fails_closed(
    config: ScalarArcLengthConfig,
) -> None:
    with pytest.raises(ArcLengthContractError):
        scalar_arc_length_continuation(
            ShallowArchArcLengthProblem(),
            config=config,
        )
