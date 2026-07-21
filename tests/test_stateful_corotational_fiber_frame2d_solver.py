from __future__ import annotations

import json

import numpy as np
import pytest

from structural_analysis.assembly import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    run_stateful_corotational_fiber_frame2d_load_path,
    solve_stateful_corotational_fiber_frame2d_load_step,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    NewtonRaphsonConfig,
)


COORDINATES = ((0.0, 0.0), (3.0, 0.0), (3.0, 2.0))


def _problem(
    *,
    case_id: str,
    reference_load_kn: float = -20.0,
    all_fixed: bool = False,
) -> StatefulCorotationalFiberFrame2DProblem:
    members = tuple(
        StatefulCorotationalFiberFrame2DMember(
            member_id=member_id,
            node_i=node_i,
            node_j=node_j,
            element=StatefulCorotationalFiberBeam2D(
                node_coordinates_m=(COORDINATES[node_i], COORDINATES[node_j]),
                section=make_rectangular_stateful_rc_fiber_section(),
                integration_order=3,
                element_id=member_id,
            ),
        )
        for member_id, node_i, node_j in (
            ("member-1", 0, 1),
            ("member-2", 1, 2),
        )
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id=case_id,
        node_coordinates_m=COORDINATES,
        members=members,
        fixed_global_dofs=(tuple(range(9)) if all_fixed else (0, 1, 2)),
        reference_external_loads=((6, reference_load_kn),),
        rotation_coordinate_scale_m=3.0,
    )


def test_consistent_newton_step_commits_only_the_converged_trial() -> None:
    problem = _problem(case_id="corotational-newton-step")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    parent_bytes = initial.canonical_bytes()

    result = solve_stateful_corotational_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=1.0,
    )

    assert result.status == "ready"
    assert result.committed is True
    assert result.metrics["solver_contract_pass"] is True
    assert result.metrics["iterative_solver_contract_pass"] is True
    assert result.metrics["no_solve_contract_pass"] is False
    assert result.metrics["tangent_definition"] == (
        "material_plus_geometric_consistent"
    )
    assert result.metrics["section_and_element_parent_binding_passed"] is True
    assert result.metrics["solver_assembly_coordinate_residual_binding_passed"] is True
    assert result.metrics["parent_checkpoint_immutable"] is True
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert result.accepted_checkpoint.epoch == 1
    assert result.accepted_checkpoint.step_index == 1
    assert result.accepted_checkpoint.load_factor == 1.0
    assert result.accepted_checkpoint.parent_state_hash == initial.state_hash
    assert initial.canonical_bytes() == parent_bytes
    assert tuple(
        state.step_index for state in result.accepted_checkpoint.element_states
    ) == (1, 1)
    assert result.trial_solution.metrics["relative_residual"] <= (
        result.trial_solution.config.residual_tolerance
    )
    assert result.trial_solution.metrics["final_increment_abs_m"] <= (
        result.trial_solution.config.increment_tolerance
    )
    assert (
        np.linalg.norm(
            result.trial_assembly.geometric_tangent_global,
            ord=np.inf,
        )
        > 0.0
    )
    np.testing.assert_array_equal(
        result.trial_solution.free_displacements_m,
        result.trial_assembly.generalized_coordinates_m[list(problem.free_global_dofs)],
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem,
        result.accepted_checkpoint,
    )
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)


def test_nonlinear_load_path_is_deterministic_and_advances_damage_history() -> None:
    problem = _problem(
        case_id="corotational-newton-damage-path",
        reference_load_kn=-120.0,
    )
    factors = (0.25, 0.5, 0.75, 1.0)

    first = run_stateful_corotational_fiber_frame2d_load_path(problem, factors)
    repeated = run_stateful_corotational_fiber_frame2d_load_path(problem, factors)

    assert first.status == "ready"
    assert first.contract_pass is True
    assert len(first.steps) == len(factors)
    assert first.final_checkpoint.epoch == len(factors)
    assert first.final_checkpoint.load_factor == 1.0
    assert first.final_checkpoint.state_hash == repeated.final_checkpoint.state_hash
    assert first.final_checkpoint.canonical_bytes() == (
        repeated.final_checkpoint.canonical_bytes()
    )
    assert first.to_dict() == repeated.to_dict()
    assert any(step.metrics["damaged_member_count"] > 0 for step in first.steps)
    assert any(step.trial_solution.metrics["line_search_used"] for step in first.steps)
    parent = first.initial_checkpoint
    for epoch, (factor, step) in enumerate(zip(factors, first.steps), start=1):
        assert step.parent_checkpoint.state_hash == parent.state_hash
        assert step.accepted_checkpoint.parent_state_hash == parent.state_hash
        assert step.accepted_checkpoint.epoch == epoch
        assert step.accepted_checkpoint.load_factor == factor
        parent = step.accepted_checkpoint


def test_failed_step_returns_the_exact_accepted_checkpoint() -> None:
    problem = _problem(case_id="corotational-newton-rollback")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    parent_bytes = initial.canonical_bytes()
    parent_element_hashes = tuple(state.state_hash for state in initial.element_states)

    result = solve_stateful_corotational_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=1.0,
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    assert result.status == "blocked"
    assert result.committed is False
    assert result.accepted_checkpoint is initial
    assert result.accepted_checkpoint.state_hash == initial.state_hash
    assert result.accepted_checkpoint.canonical_bytes() == parent_bytes
    assert result.metrics["solver_contract_pass"] is False
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["section_and_element_parent_binding_passed"] is True
    assert result.metrics["solver_assembly_coordinate_residual_binding_passed"] is True
    assert tuple(state.state_hash for state in initial.element_states) == (
        parent_element_hashes
    )
    assert all(
        row.response.parent_state_hash == parent.state_hash
        for row, parent in zip(
            result.trial_assembly.member_assemblies,
            initial.element_states,
            strict=True,
        )
    )


def test_load_path_stops_at_failure_and_retains_last_commit() -> None:
    problem = _problem(case_id="corotational-newton-path-stop")
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.0, 1.0),
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    assert path.status == "blocked"
    assert path.contract_pass is False
    assert len(path.steps) == 2
    assert path.steps[0].committed is True
    assert path.steps[1].committed is False
    assert path.final_checkpoint is path.steps[0].accepted_checkpoint
    assert path.steps[1].accepted_checkpoint is path.final_checkpoint
    assert path.steps[1].parent_checkpoint is path.final_checkpoint
    assert path.final_checkpoint.epoch == 1
    assert path.final_checkpoint.load_factor == 0.0
    assert path.steps[1].metrics["rollback_exact"] is True


def test_all_fixed_problem_uses_reaction_only_terminal_contract() -> None:
    problem = _problem(
        case_id="corotational-reaction-only",
        all_fixed=True,
    )
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)

    result = solve_stateful_corotational_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=0.5,
    )

    assert result.status == "ready"
    assert result.committed is True
    assert result.metrics["solver_contract_pass"] is True
    assert result.metrics["iterative_solver_contract_pass"] is False
    assert result.metrics["no_solve_contract_pass"] is True
    assert result.metrics["terminal_disposition"] == (
        NO_SOLVE_REACTION_ONLY_DISPOSITION
    )
    assert result.trial_solution.metrics["solver_executed"] is False
    assert result.trial_solution.metrics["convergence_claim"] is False
    assert result.trial_assembly.residual_kn.shape == (0,)
    assert result.trial_assembly.jacobian_kn_per_m.shape == (0, 0)
    assert result.trial_assembly.reactions_global[6] == pytest.approx(10.0)
    np.testing.assert_array_equal(
        result.accepted_checkpoint.global_displacements,
        np.zeros(problem.global_dof_count),
    )


def test_load_path_rejects_empty_or_nonfinite_targets() -> None:
    problem = _problem(case_id="corotational-newton-input")

    with pytest.raises(ValueError, match="non-empty"):
        run_stateful_corotational_fiber_frame2d_load_path(problem, ())
    with pytest.raises(ValueError, match="finite"):
        run_stateful_corotational_fiber_frame2d_load_path(problem, (float("nan"),))
