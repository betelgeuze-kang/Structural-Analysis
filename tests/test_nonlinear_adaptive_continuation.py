from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly.nonlinear_static import (
    AxialChainLoadContinuationAdapter,
    finite_difference_assembled_jacobian_check,
    refined_strain_cubic_axial_chain_mesh_problem,
)
from structural_analysis.solvers.nonlinear.continuation import (
    AdaptiveContinuationConfig,
    ContinuationContractError,
    adaptive_load_continuation,
    validate_continuation_checkpoint,
)
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
    assess_quadratic_convergence,
)


class _FullyConstrainedEquilibriumProblem:
    def __init__(
        self,
        owner: _FullyConstrainedContinuationProblem,
        load_factor: float,
    ) -> None:
        self.owner = owner
        self.load_factor = load_factor
        self.case_id = f"{owner.case_id}@load={load_factor}"

    def reference_force_scale(self) -> float:
        raise AssertionError("no-solve continuation must not observe residual scale")

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert free_displacements_m.shape == (0,)
        self.owner.assembled_load_factors.append(self.load_factor)
        if not self.owner.valid_assembly:
            return np.asarray([1.0]), np.asarray([[1.0]])
        return np.asarray([], dtype=float), np.empty((0, 0), dtype=float)


class _FullyConstrainedContinuationProblem:
    case_id = "fully_constrained_adaptive_continuation"

    def __init__(self, *, valid_assembly: bool = True) -> None:
        self.valid_assembly = valid_assembly
        self.assembled_load_factors: list[float] = []

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([], dtype=float)

    def problem_at_load_factor(
        self,
        load_factor: float,
        accepted_free_displacements_m: np.ndarray,
    ) -> _FullyConstrainedEquilibriumProblem:
        assert accepted_free_displacements_m.shape == (0,)
        return _FullyConstrainedEquilibriumProblem(self, load_factor)


def _problem() -> AxialChainLoadContinuationAdapter:
    return AxialChainLoadContinuationAdapter(
        refined_strain_cubic_axial_chain_mesh_problem(element_count=2)
    )


def _newton_config(*, max_iterations: int = 4) -> NewtonRaphsonConfig:
    return NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=max_iterations,
    )


def _continuation_config(
    *,
    target: float = 1.0,
    initial_step: float = 0.5,
    minimum_step: float = 0.125,
) -> AdaptiveContinuationConfig:
    return AdaptiveContinuationConfig(
        target_load_factor=target,
        initial_step_size=initial_step,
        minimum_step_size=minimum_step,
        maximum_step_size=0.5,
        failed_step_reduction=0.5,
        fast_step_growth=1.0,
        fast_iteration_threshold=4,
        maximum_attempt_count=20,
    )


def test_adaptive_continuation_rolls_back_failed_step_and_reaches_full_load() -> None:
    result = adaptive_load_continuation(
        _problem(),
        config=_continuation_config(),
        newton_config=_newton_config(),
    )

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["final_load_factor"] == 1.0
    assert result.metrics["accepted_step_count"] == 4
    assert result.metrics["rejected_attempt_count"] == 1
    assert result.metrics["rollback_exact_all"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["residual_formula_hash"] == RESIDUAL_FORMULA_HASH

    assert [row["trial_load_factor"] for row in result.attempts] == [
        0.5,
        0.25,
        0.5,
        0.75,
        1.0,
    ]
    rejected = result.attempts[0]
    assert rejected["outcome"] == "rolled_back"
    # A low replay residual must not override the step solver's blocked terminal
    # contract; both gates remain false until the solver emits a ready receipt.
    assert rejected["relative_residual"] == 0.0
    assert rejected["residual_gate_passed"] is False
    assert rejected["increment_gate_passed"] is False
    assert rejected["accepted_state_hash_before"] == rejected["accepted_state_hash_after"]
    assert rejected["trial_state_hash"] != rejected["accepted_state_hash_after"]
    assert rejected["rollback_exact"] is True
    assert all(row["committed"] is True for row in result.attempts[1:])
    assert all(row["residual_gate_passed"] is True for row in result.attempts[1:])
    assert all(row["increment_gate_passed"] is True for row in result.attempts[1:])
    assert len(result.checkpoints) == 5
    assert all(validate_continuation_checkpoint(row) is row for row in result.checkpoints)


def test_checkpoint_restart_reproduces_the_one_shot_final_state_exactly() -> None:
    problem = _problem()
    solver_config = _newton_config()
    one_shot = adaptive_load_continuation(
        problem,
        config=_continuation_config(),
        newton_config=solver_config,
    )
    first_half = adaptive_load_continuation(
        problem,
        config=_continuation_config(target=0.5),
        newton_config=solver_config,
    )
    resumed = adaptive_load_continuation(
        problem,
        config=_continuation_config(target=1.0, initial_step=0.25),
        newton_config=solver_config,
        resume_from=first_half.final_checkpoint,
    )

    assert first_half.status == "ready"
    assert first_half.final_checkpoint.load_factor == 0.5
    assert resumed.status == "ready"
    assert resumed.metrics["checkpoint_restart_used"] is True
    assert resumed.final_checkpoint.state_hash == one_shot.final_checkpoint.state_hash
    assert (
        resumed.final_checkpoint.free_displacements_m
        == one_shot.final_checkpoint.free_displacements_m
    )


def test_minimum_step_exhaustion_keeps_the_initial_accepted_state() -> None:
    result = adaptive_load_continuation(
        _problem(),
        config=_continuation_config(minimum_step=0.25),
        newton_config=_newton_config(max_iterations=1),
    )

    assert result.status == "blocked"
    assert result.terminal_reason == "minimum_step_size_exhausted"
    assert result.metrics["contract_pass"] is False
    assert result.metrics["final_load_factor"] == 0.0
    assert result.metrics["accepted_step_count"] == 0
    assert result.metrics["rejected_attempt_count"] == 2
    assert result.metrics["rollback_exact_all"] is True
    assert result.final_checkpoint is result.initial_checkpoint
    assert all(row["outcome"] == "rolled_back" for row in result.attempts)


def test_checkpoint_validation_rejects_a_forged_state_hash() -> None:
    result = adaptive_load_continuation(
        _problem(),
        config=_continuation_config(target=0.5),
        newton_config=_newton_config(),
    )
    forged = replace(result.final_checkpoint, state_hash="sha256:" + "0" * 64)

    with pytest.raises(ContinuationContractError, match="state_hash mismatch"):
        validate_continuation_checkpoint(forged)


def test_full_load_step_has_consistent_jacobian_and_quadratic_convergence() -> None:
    problem = _problem()
    result = adaptive_load_continuation(
        problem,
        config=_continuation_config(),
        newton_config=_newton_config(),
    )
    final_attempt = next(
        row for row in reversed(result.attempts) if row["outcome"] == "committed"
    )
    quadratic = assess_quadratic_convergence(final_attempt["convergence_history"])
    tangent = finite_difference_assembled_jacobian_check(
        problem.mesh_problem,
        np.asarray(result.final_checkpoint.free_displacements_m, dtype=float),
    )

    assert quadratic["pass"] is True
    assert quadratic["order_sample_count"] >= 2
    assert quadratic["minimum_observed_order"] >= 1.8
    assert tangent["pass"] is True
    assert tangent["max_abs_error"] <= 1.0e-6


def test_fully_constrained_continuation_commits_no_solve_load_checkpoints() -> None:
    problem = _FullyConstrainedContinuationProblem()
    result = adaptive_load_continuation(
        problem,
        config=_continuation_config(),
        newton_config=NewtonRaphsonConfig(
            matrix_backend="deliberately_unused_backend"
        ),
    )

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert problem.assembled_load_factors == [0.5, 1.0]
    assert result.metrics["contract_pass"] is True
    assert result.metrics["accepted_step_count"] == 2
    assert result.metrics["rejected_attempt_count"] == 0
    assert result.metrics["no_solve_reaction_only_step_count"] == 2
    assert result.metrics["iterative_solver_step_count"] == 0
    assert result.metrics["solver_executed_step_count"] == 0
    assert result.metrics["newton_convergence_claim_count"] == 0
    assert result.metrics["solver_executed"] is False
    assert result.metrics["convergence_claim"] is False
    assert result.metrics["reaction_observation_only"] is True
    assert result.metrics["terminal_dispositions"] == [
        NO_SOLVE_REACTION_ONLY_DISPOSITION
    ]
    assert [row.load_factor for row in result.checkpoints] == [0.0, 0.5, 1.0]
    assert len({row.state_hash for row in result.checkpoints}) == 3
    for attempt in result.attempts:
        assert attempt["outcome"] == "committed"
        assert attempt["commit_contract_pass"] is True
        assert attempt["iterative_solver_contract_pass"] is False
        assert attempt["no_solve_contract_pass"] is True
        assert attempt["terminal_disposition"] == (
            NO_SOLVE_REACTION_ONLY_DISPOSITION
        )
        assert attempt["terminal_reason"] == "free_equation_space_empty"
        assert attempt["solver_executed"] is False
        assert attempt["active_equation_count"] == 0
        assert attempt["residual_norm_applicable"] is False
        assert attempt["increment_norm_applicable"] is False
        assert attempt["residual_gate_passed"] is None
        assert attempt["increment_gate_passed"] is None
        assert attempt["relative_residual"] is None
        assert attempt["convergence_claim"] is False
        assert attempt["reaction_observation_only"] is True
        assert attempt["iteration_count"] == 0
        assert attempt["linear_solve_count"] == 0
        assert attempt["line_search_step_count"] == 0


def test_invalid_fully_constrained_continuation_assembly_rolls_back() -> None:
    problem = _FullyConstrainedContinuationProblem(valid_assembly=False)
    result = adaptive_load_continuation(
        problem,
        config=_continuation_config(minimum_step=0.25),
    )

    assert result.status == "blocked"
    assert result.terminal_reason == "minimum_step_size_exhausted"
    assert result.final_checkpoint is result.initial_checkpoint
    assert result.metrics["accepted_step_count"] == 0
    assert result.metrics["rejected_attempt_count"] == 2
    assert result.metrics["contract_pass"] is False
    assert all(row["outcome"] == "rolled_back" for row in result.attempts)
    assert all(row["rollback_exact"] is True for row in result.attempts)
    assert all(
        row["terminal_disposition"]
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        for row in result.attempts
    )
    assert all(
        row["terminal_reason"] == "zero_equation_assembly_contract_invalid"
        for row in result.attempts
    )
    assert all(row["commit_contract_pass"] is False for row in result.attempts)


def test_adaptive_continuation_receipt_is_deterministic() -> None:
    first = adaptive_load_continuation(
        _problem(),
        config=_continuation_config(),
        newton_config=_newton_config(),
    )
    second = adaptive_load_continuation(
        _problem(),
        config=_continuation_config(),
        newton_config=_newton_config(),
    )

    assert first.to_dict() == second.to_dict()
