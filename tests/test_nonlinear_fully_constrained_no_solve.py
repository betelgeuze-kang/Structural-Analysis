from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    StatefulAxialChainProblem,
    initial_stateful_axial_state,
    run_stateful_axial_load_path,
    single_element_bilinear_link_problem,
    single_element_composite_section_bar_problem,
    single_element_concrete_damage_bar_problem,
    solve_stateful_axial_load_step,
)
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    NewtonRaphsonConfig,
    newton_raphson_vector,
)


class _ZeroEquationProblem:
    case_id = "fully_constrained_zero_equation_contract"

    def __init__(
        self,
        *,
        valid_assembly: bool = True,
        assembly_error: Exception | None = None,
    ) -> None:
        self.valid_assembly = valid_assembly
        self.assembly_error = assembly_error
        self.assemble_count = 0

    def reference_force_scale(self) -> float:
        raise AssertionError("no-solve disposition must not observe a residual scale")

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        self.assemble_count += 1
        assert free_displacements_m.shape == (0,)
        if self.assembly_error is not None:
            raise self.assembly_error
        if self.valid_assembly:
            return np.asarray([], dtype=float), np.empty((0, 0), dtype=float)
        return np.asarray([1.0], dtype=float), np.asarray([[1.0]], dtype=float)


def test_zero_equation_problem_routes_without_newton_or_linear_solve() -> None:
    problem = _ZeroEquationProblem()
    solution = newton_raphson_vector(
        problem,
        config=NewtonRaphsonConfig(matrix_backend="deliberately_unused_backend"),
    )

    assert solution.status == "ready"
    assert problem.assemble_count == 1
    assert solution.free_displacements_m.shape == (0,)
    assert solution.convergence_history == []
    assert solution.line_search_history == []
    assert solution.metrics["terminal_disposition"] == (
        NO_SOLVE_REACTION_ONLY_DISPOSITION
    )
    assert solution.metrics["terminal_reason"] == "free_equation_space_empty"
    assert solution.metrics["solver_executed"] is False
    assert solution.metrics["newton_iteration_count"] == 0
    assert solution.metrics["linear_solve_count"] == 0
    assert solution.metrics["line_search_step_count"] == 0
    assert solution.metrics["matrix_backend"] is None
    assert solution.metrics["relative_residual"] is None
    assert solution.metrics["residual_gate_passed"] is None
    assert solution.metrics["increment_gate_passed"] is None
    assert solution.metrics["convergence_claim"] is False
    assert solution.metrics["reaction_observation_only"] is True
    assert solution.metrics["regularization_used"] is False
    assert solution.metrics["fallback_used"] is False
    assert solution.metrics["contract_pass"] is True


def test_zero_equation_assembly_shape_mismatch_fails_closed() -> None:
    problem = _ZeroEquationProblem(valid_assembly=False)
    solution = newton_raphson_vector(problem)

    assert solution.status == "blocked"
    assert solution.metrics["terminal_disposition"] == (
        NO_SOLVE_REACTION_ONLY_DISPOSITION
    )
    assert solution.metrics["terminal_reason"] == (
        "zero_equation_assembly_contract_invalid"
    )
    assert solution.metrics["solver_executed"] is False
    assert solution.metrics["assembly_contract_valid"] is False
    assert solution.metrics["contract_pass"] is False
    assert solution.unsupported_features[0]["guard_outcome"] == "blocked"


def test_zero_equation_assembly_exception_fails_closed() -> None:
    problem = _ZeroEquationProblem(assembly_error=IndexError("invalid fixture"))
    solution = newton_raphson_vector(problem)

    assert solution.status == "blocked"
    assert problem.assemble_count == 1
    assert solution.metrics["terminal_disposition"] == (
        NO_SOLVE_REACTION_ONLY_DISPOSITION
    )
    assert solution.metrics["terminal_reason"] == (
        "zero_equation_assembly_contract_invalid"
    )
    assert solution.metrics["solver_executed"] is False
    assert solution.metrics["assembly_contract_valid"] is False
    assert solution.metrics["contract_pass"] is False


@pytest.mark.parametrize(
    "problem_factory",
    (
        single_element_concrete_damage_bar_problem,
        single_element_composite_section_bar_problem,
        single_element_bilinear_link_problem,
    ),
)
def test_prescribed_single_element_commits_constitutive_state_without_solver(
    problem_factory: Callable[[], StatefulAxialChainProblem],
) -> None:
    problem = problem_factory()
    parent = initial_stateful_axial_state(problem)
    result = solve_stateful_axial_load_step(
        problem,
        parent,
        target_load_factor=1.0,
    )

    assert problem.free_node_indices == ()
    assert result.status == "ready"
    assert result.committed is True
    assert result.parent_state is parent
    assert result.accepted_state is not parent
    assert result.accepted_state.step_index == 1
    assert result.accepted_state.load_factor == 1.0
    assert result.accepted_state.state_hash != parent.state_hash
    assert result.trial_assembly.residual_kn.shape == (0,)
    assert result.trial_assembly.jacobian_kn_per_m.shape == (0, 0)
    assert abs(float(np.sum(result.trial_assembly.reactions_kn))) <= 1.0e-10
    assert result.metrics["terminal_disposition"] == (
        NO_SOLVE_REACTION_ONLY_DISPOSITION
    )
    assert result.metrics["terminal_reason"] == "free_equation_space_empty"
    assert result.metrics["terminal_contract_pass"] is True
    assert result.metrics["iterative_solver_contract_pass"] is False
    assert result.metrics["no_solve_contract_pass"] is True
    assert result.metrics["solver_executed"] is False
    assert result.metrics["active_equation_count"] == 0
    assert result.metrics["no_solve_reaction_only"] is True
    assert result.metrics["convergence_claim"] is False
    assert result.metrics["residual_gate_applicable"] is False
    assert result.metrics["increment_gate_applicable"] is False
    assert result.metrics["residual_gate_passed"] is None
    assert result.metrics["increment_gate_passed"] is None
    assert result.metrics["material_state_changed"] is True
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False


def test_prescribed_no_solve_load_path_replays_state_hashes_exactly() -> None:
    problem = single_element_bilinear_link_problem()
    first = run_stateful_axial_load_path(problem, (0.5, 1.0))
    second = run_stateful_axial_load_path(problem, (0.5, 1.0))

    assert first.status == "ready"
    assert first.contract_pass is True
    assert first.to_dict() == second.to_dict()
    assert first.final_state.state_hash == second.final_state.state_hash
    assert all(step.committed for step in first.steps)
    assert all(
        step.metrics["no_solve_reaction_only"] is True
        and step.metrics["solver_executed"] is False
        and step.metrics["convergence_claim"] is False
        for step in first.steps
    )
