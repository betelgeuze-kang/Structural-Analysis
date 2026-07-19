from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.sparse import csr_matrix


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (  # noqa: E402
    LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE,
    AdaptiveLoadControlledMatrixFreeNewtonConfig,
    LoadControlledMatrixFreeNewtonConfig,
    LoadControlledMatrixFreeNewtonError,
    adaptive_load_controlled_matrix_free_newton_continuation,
    load_controlled_matrix_free_newton_continuation,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    MatrixFreeCPUFGMRESConfig,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (  # noqa: E402
    VectorArcLengthTangentSolve,
)


@dataclass
class _NonlinearLoadProblem:
    stiffness_kn_per_m: np.ndarray
    cubic_kn_per_m3: np.ndarray
    load_kn: np.ndarray
    case_id: str = "load_controlled_matrix_free_newton_synthetic"
    reference_preconditioner_contract: str = (
        "synthetic-zero-state-reference-csr-preconditioner.v1"
    )

    @property
    def equation_count(self) -> int:
        return int(self.load_kn.size)

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(self.equation_count, dtype=np.float64)

    def initial_load_factor(self) -> float:
        return 0.0

    def reference_load_kn(self) -> np.ndarray:
        return self.load_kn.copy()

    def full_unit_zero_state_predictor_free_m(self) -> np.ndarray:
        return np.linalg.solve(self.stiffness_kn_per_m, self.load_kn)

    def reference_preconditioner_free_csr_n_per_m(self) -> csr_matrix:
        return csr_matrix(self.stiffness_kn_per_m * 1000.0)

    def residual_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        state = np.asarray(free_displacements_m, dtype=np.float64)
        return (
            self.stiffness_kn_per_m @ state
            + self.cubic_kn_per_m3 * state**3
            - float(load_factor) * self.load_kn
        )

    def negative_load_derivative_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        del free_displacements_m, load_factor
        return self.load_kn.copy()

    def consistent_state_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        del load_factor
        state = np.asarray(free_displacements_m, dtype=np.float64)
        tangent = self.stiffness_kn_per_m + np.diag(
            3.0 * self.cubic_kn_per_m3 * state**2
        )
        return tangent @ np.asarray(direction_m, dtype=np.float64)


def _problem() -> _NonlinearLoadProblem:
    return _NonlinearLoadProblem(
        stiffness_kn_per_m=np.asarray(
            [
                [14.0, -2.0, 0.0],
                [-2.0, 11.0, -1.0],
                [0.0, -1.0, 8.0],
            ],
            dtype=np.float64,
        ),
        cubic_kn_per_m3=np.asarray([20.0, 12.0, 8.0], dtype=np.float64),
        load_kn=np.asarray([1.0, 0.4, -0.2], dtype=np.float64),
    )


def _solver(problem: _NonlinearLoadProblem):
    return create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=MatrixFreeCPUFGMRESConfig(
            max_iterations=8,
            restart_length=3,
            relative_tolerance_l2=1.0e-12,
            absolute_tolerance_l2_kn=1.0e-14,
            explicit_residual_tolerance_inf_kn=1.0e-11,
        ),
    )


def _config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(0.25, 0.5, 0.75, 1.0),
        residual_tolerance_inf_kn=1.0e-11,
        increment_absolute_tolerance_inf_m=1.0e-11,
        increment_relative_tolerance=1.0e-8,
        tangent_solve_residual_tolerance_inf_kn=1.0e-11,
        maximum_newton_iterations=5,
    )


def test_load_controlled_matrix_free_newton_reaches_target() -> None:
    problem = _problem()
    solver = _solver(problem)

    result = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=_config(),
    )

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["target_load_factor_reached"] is True
    assert result.metrics["accepted_step_count"] == 4
    assert result.metrics["failed_step_count"] == 0
    assert result.metrics["checkpoint_count"] == 5
    assert result.metrics["tangent_solve_count"] >= 4
    assert result.metrics["maximum_tangent_solve_iterations"] <= 3
    assert result.metrics["maximum_checkpoint_residual_inf_kn"] <= 1.0e-11
    assert result.metrics["final_residual_inf_kn"] <= 1.0e-11
    assert (
        result.metrics["maximum_accepted_increment_inf_m"] <= 1.0e-11
        or result.metrics["maximum_accepted_relative_increment"] <= 1.0e-8
    )
    assert result.metrics["residual_and_increment_acceptance_gate"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.final_checkpoint.load_factor == 1.0
    assert all(
        attempt["history"][-1]["residual_gate_passed"] is True
        and attempt["history"][-1]["increment_gate_passed"] is True
        and attempt["history"][-1]["convergence_gate_passed"] is True
        for attempt in result.attempts
    )
    assert any(
        row.get("accepted_without_applying_converged_correction") is True
        for attempt in result.attempts
        for row in attempt["history"]
    )
    np.testing.assert_allclose(
        problem.residual_kn(result.final_free_displacements_m, 1.0),
        np.zeros(problem.equation_count),
        atol=1.0e-11,
    )
    payload = result.to_dict()
    assert payload["solver_profile"] == solver.profile
    assert payload["claims"]["load_controlled_matrix_free_newton_path"] is True
    assert payload["claims"]["accepted_trial_displacement_state"] is True
    assert payload["claims"]["residual_and_increment_acceptance_gate"] is True
    assert payload["claims"]["failed_step_rollback_exact"] is False
    assert payload["claims"]["material_state_commit_rollback"] is False
    assert payload["claims"]["arc_length_branch"] is False
    assert payload["claims"]["production_matrix_free_krylov"] is False
    assert payload["claims"]["g1_full_building_closure"] is False
    assert LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE in result.path_contract_hash or (
        result.path_contract_hash.startswith("sha256:")
    )


def test_midpoint_restart_reproduces_terminal_checkpoint_exactly() -> None:
    problem = _problem()
    solver = _solver(problem)
    config = _config()
    one_shot = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=config,
    )
    midpoint = [
        row for row in one_shot.checkpoints if row.load_factor == 0.5
    ][0]

    restarted = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=config,
        checkpoint=midpoint,
    )

    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.initial_checkpoint.state_hash == midpoint.state_hash
    assert restarted.final_checkpoint.state_hash == (
        one_shot.final_checkpoint.state_hash
    )
    np.testing.assert_array_equal(
        restarted.final_free_displacements_m,
        one_shot.final_free_displacements_m,
    )


def _adaptive_config() -> AdaptiveLoadControlledMatrixFreeNewtonConfig:
    return AdaptiveLoadControlledMatrixFreeNewtonConfig(
        target_load_factor=1.0,
        initial_step_size=1.0,
        minimum_step_size=0.25,
        maximum_step_size=1.0,
        failed_step_reduction=0.5,
        fast_step_growth=2.0,
        fast_newton_solve_threshold=1,
        maximum_attempt_count=8,
        step_config=LoadControlledMatrixFreeNewtonConfig(
            target_load_factors=(1.0,),
            residual_tolerance_inf_kn=1.0e-6,
            increment_absolute_tolerance_inf_m=1.0e-10,
            increment_relative_tolerance=1.0e-2,
            tangent_solve_residual_tolerance_inf_kn=1.0e-11,
            maximum_newton_iterations=1,
        ),
    )


def test_adaptive_matrix_free_newton_reduces_failed_steps_and_reaches_target() -> None:
    problem = _problem()
    result = adaptive_load_controlled_matrix_free_newton_continuation(
        problem,
        _solver(problem),
        config=_adaptive_config(),
    )

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["target_load_factor_reached"] is True
    assert result.metrics["attempt_count"] == 5
    assert result.metrics["accepted_step_count"] == 3
    assert result.metrics["failed_step_count"] == 2
    assert result.metrics["failed_step_reduction_count"] == 2
    assert result.metrics["fast_step_growth_count"] == 2
    assert result.metrics["checkpoint_count"] == 4
    assert result.metrics["minimum_attempted_step_size"] == 0.25
    assert result.metrics["maximum_attempted_step_size"] == 1.0
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["residual_and_increment_acceptance_gate"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert [row["target_load_factor"] for row in result.attempts] == [
        1.0,
        0.5,
        1.0,
        0.75,
        1.0,
    ]
    assert [row["outcome"] for row in result.attempts] == [
        "rolled_back",
        "committed",
        "rolled_back",
        "committed",
        "committed",
    ]
    assert all(
        row["rollback_exact"] is True
        for row in result.attempts
        if row["outcome"] == "rolled_back"
    )
    payload = result.to_dict()
    assert payload["claims"][
        "adaptive_load_controlled_matrix_free_newton_path"
    ] is True
    assert payload["claims"]["failed_step_reduction_exercised"] is True
    assert payload["claims"]["failed_step_rollback_exact"] is True
    assert payload["claims"]["material_state_commit_rollback"] is False
    assert payload["claims"]["arc_length_branch"] is False
    assert payload["claims"]["rocm_hip_parity"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


def test_adaptive_matrix_free_newton_restart_is_exact() -> None:
    problem = _problem()
    solver = _solver(problem)
    config = _adaptive_config()
    one_shot = adaptive_load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=config,
    )
    checkpoint = [
        row for row in one_shot.checkpoints if row.load_factor == 0.75
    ][0]

    restarted = adaptive_load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=config,
        checkpoint=checkpoint,
    )

    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.initial_checkpoint.state_hash == checkpoint.state_hash
    assert restarted.final_checkpoint.state_hash == (
        one_shot.final_checkpoint.state_hash
    )
    np.testing.assert_array_equal(
        restarted.final_free_displacements_m,
        one_shot.final_free_displacements_m,
    )


@dataclass(frozen=True)
class _RejectingStateSolver:
    profile: str = "rejecting-state-solver.v1"
    contract_hash: str = "sha256:" + "a" * 64

    def solve_at_state(
        self,
        problem,
        free_displacements_m,
        right_hand_side_kn,
        *,
        load_factor,
        solve_id,
    ) -> VectorArcLengthTangentSolve:
        del problem, free_displacements_m, load_factor, solve_id
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=False,
            terminal_reason="injected_failure",
            solution_free=tuple(np.zeros_like(right_hand_side_kn)),
            receipt={"fallback_count": 0, "regularization_count": 0},
        )


def test_failed_tangent_solve_rolls_back_exactly() -> None:
    problem = _problem()
    result = load_controlled_matrix_free_newton_continuation(
        problem,
        _RejectingStateSolver(),
        config=_config(),
    )

    assert result.status == "blocked"
    assert result.terminal_reason == (
        "tangent_solve_explicit_residual_gate_failed"
    )
    assert result.final_checkpoint.load_factor == 0.0
    assert result.final_checkpoint.state_hash == (
        result.initial_checkpoint.state_hash
    )
    assert result.metrics["failed_step_count"] == 1
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["residual_and_increment_acceptance_gate"] is False
    attempt = result.attempts[0]
    assert attempt["accepted"] is False
    assert attempt["rollback_performed"] is True
    assert attempt["rollback_exact"] is True
    assert attempt["accepted_state_hash_before"] == (
        attempt["accepted_state_hash_after"]
    )
    assert result.to_dict()["claims"]["failed_step_rollback_exact"] is True


def test_checkpoint_tamper_fails_closed() -> None:
    problem = _problem()
    result = load_controlled_matrix_free_newton_continuation(
        problem,
        _solver(problem),
        config=_config(),
    )
    checkpoint = result.checkpoints[1]

    with pytest.raises(
        LoadControlledMatrixFreeNewtonError,
        match="state_hash mismatch",
    ):
        replace(
            checkpoint,
            free_displacements_m=(
                checkpoint.free_displacements_m + 1.0e-6
            ),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_load_factors": ()},
        {"target_load_factors": (0.5, 0.25)},
        {"residual_tolerance_inf_kn": 0.0},
        {"increment_absolute_tolerance_inf_m": 0.0},
        {"increment_relative_tolerance": 0.0},
        {"maximum_newton_iterations": 0},
        {"line_search_reduction": 1.0},
    ],
)
def test_config_fails_closed(kwargs: dict) -> None:
    with pytest.raises(LoadControlledMatrixFreeNewtonError):
        LoadControlledMatrixFreeNewtonConfig(**kwargs)
