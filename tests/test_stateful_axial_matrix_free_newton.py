from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    StatefulAxialChainProblem,
    initial_stateful_axial_state,
    two_element_bilinear_link_chain_problem,
    two_element_composite_section_chain_problem,
    two_element_concrete_damage_chain_problem,
    two_element_stateful_steel_chain_problem,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (
    LoadControlledMatrixFreeNewtonConfig,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (
    MATRIX_FREE_CPU_FGMRES_PROFILE,
    MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION,
)
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA_HASH
from structural_analysis.solvers.nonlinear.stateful_axial_matrix_free_newton import (
    STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION,
    STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE,
    StatefulAxialMatrixFreeLoadStepProblem,
    StatefulAxialMatrixFreeNewtonError,
    finite_difference_stateful_axial_matrix_free_tangent_check,
    run_stateful_axial_matrix_free_load_path,
    solve_stateful_axial_matrix_free_load_step,
)


def _step_config(
    *,
    maximum_newton_iterations: int = 8,
) -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=1.0e-9,
        increment_absolute_tolerance_inf_m=1.0e-12,
        increment_relative_tolerance=1.0e-9,
        tangent_solve_residual_tolerance_inf_kn=1.0e-9,
        maximum_newton_iterations=maximum_newton_iterations,
    )


def test_parent_bound_increment_problem_exposes_consistent_matrix_free_action(
) -> None:
    problem = two_element_stateful_steel_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    step_problem = StatefulAxialMatrixFreeLoadStepProblem(
        problem,
        accepted,
        1.0,
    )
    check = finite_difference_stateful_axial_matrix_free_tangent_check(
        step_problem,
        displacement_increments_m=np.asarray([0.01, 0.02]),
        increment_load_factor=1.0,
        direction_m=np.asarray([0.4, -0.7]),
    )
    binding = step_problem.matrix_free_current_tangent_operator_binding()

    assert step_problem.initial_load_factor() == 0.0
    assert step_problem.actual_load_factor(1.0) == 1.0
    assert step_problem.equation_count == 2
    assert check["contract_pass"] is True
    assert check["same_accepted_material_parent_state"] is True
    assert check["relative_error"] <= check["relative_tolerance"]
    assert check["residual_formula_hash"] == RESIDUAL_FORMULA_HASH
    assert binding["schema_version"] == (
        MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
    )
    assert binding["case_id"] == step_problem.case_id
    assert binding["residual_formula_hash"] == RESIDUAL_FORMULA_HASH
    assert binding["current_tangent_action_contract"] == (
        STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION
    )
    assert accepted == initial_stateful_axial_state(problem)

    modified_material = replace(
        problem.elements[0].material,
        elastic_modulus_mpa=190_000.0,
    )
    modified_problem = replace(
        problem,
        elements=tuple(
            replace(element, material=modified_material)
            for element in problem.elements
        ),
    )
    modified_accepted = initial_stateful_axial_state(modified_problem)
    modified_step = StatefulAxialMatrixFreeLoadStepProblem(
        modified_problem,
        modified_accepted,
        1.0,
    )
    assert modified_accepted.state_hash == accepted.state_hash
    assert modified_step.source_problem_contract_hash != (
        step_problem.source_problem_contract_hash
    )
    assert modified_step.case_id != step_problem.case_id


def test_matrix_free_step_commits_material_state_only_after_all_gates() -> None:
    problem = two_element_stateful_steel_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    result = solve_stateful_axial_matrix_free_load_step(
        problem,
        accepted,
        target_load_factor=1.0,
        config=_step_config(),
    )
    payload = result.to_dict()
    tangent_rows = [
        row["tangent_solve"]
        for attempt in result.newton_result.attempts
        for row in attempt["history"]
        if "tangent_solve" in row
    ]
    line_search_rows = [
        candidate
        for attempt in result.newton_result.attempts
        for row in attempt["history"]
        for candidate in row.get("line_search", [])
    ]

    assert result.status == "ready"
    assert result.committed is True
    assert result.accepted_state is not accepted
    assert result.accepted_state.load_factor == 1.0
    assert result.accepted_state.step_index == accepted.step_index + 1
    assert result.metrics["solver_profile"] == MATRIX_FREE_CPU_FGMRES_PROFILE
    assert result.metrics["solver_contract_pass"] is True
    assert result.metrics["parent_state_unchanged_during_trial"] is True
    assert result.metrics["material_state_changed"] is True
    assert result.metrics["final_residual_inf_kn"] <= 1.0e-9
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert tangent_rows
    assert all(
        row["independent_explicit_residual_gate_passed"]
        for row in tangent_rows
    )
    assert line_search_rows
    assert any(row["strict_residual_decrease"] for row in line_search_rows)
    assert payload["profile"] == STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE
    assert payload["claims"][
        "consistent_residual_tangent_matrix_free_newton"
    ] is True
    assert payload["claims"]["material_state_commit_performed"] is True
    assert payload["claims"]["material_state_changed"] is True
    assert payload["claims"]["g1_full_building_closure"] is False
    assert accepted == initial_stateful_axial_state(problem)


def test_iteration_limited_failure_rolls_back_material_state_exactly() -> None:
    problem = two_element_stateful_steel_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    parent_bytes = accepted.canonical_bytes()
    material_bytes = tuple(
        state.canonical_bytes() for state in accepted.material_states
    )
    result = solve_stateful_axial_matrix_free_load_step(
        problem,
        accepted,
        target_load_factor=1.0,
        config=_step_config(maximum_newton_iterations=1),
    )
    payload = result.to_dict()
    yielded_trial = result.step_problem.assemble(
        np.asarray([0.0155, 0.031]),
        1.0,
    )

    assert result.status == "blocked"
    assert result.committed is False
    assert result.newton_result.terminal_reason == (
        "maximum_newton_iterations_exhausted"
    )
    assert result.accepted_state is accepted
    assert result.accepted_state.canonical_bytes() == parent_bytes
    assert tuple(
        state.canonical_bytes()
        for state in result.accepted_state.material_states
    ) == material_bytes
    assert result.metrics["rollback_performed"] is True
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["material_state_changed"] is False
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert any(
        before.state_hash != trial.state_hash
        for before, trial in zip(
            accepted.material_states,
            yielded_trial.trial_material_states,
            strict=True,
        )
    )
    assert payload["claims"][
        "failed_step_material_state_rollback_exact"
    ] is True
    assert payload["claims"]["material_state_commit_performed"] is False


def test_cyclic_matrix_free_path_commits_and_restarts_deterministically() -> None:
    problem = two_element_stateful_steel_chain_problem()
    factors = (0.5, 1.0, 0.0, -1.0, 0.0, 1.0)
    first = run_stateful_axial_matrix_free_load_path(
        problem,
        factors,
        config=_step_config(),
    )
    replay = run_stateful_axial_matrix_free_load_path(
        problem,
        factors,
        config=_step_config(),
    )
    prefix = run_stateful_axial_matrix_free_load_path(
        problem,
        factors[:2],
        config=_step_config(),
    )
    resumed = run_stateful_axial_matrix_free_load_path(
        problem,
        factors[2:],
        initial_state=prefix.final_state,
        config=_step_config(),
    )
    payload = first.to_dict()

    assert first.status == "ready"
    assert first.contract_pass is True
    assert len(first.steps) == len(factors)
    assert all(step.committed for step in first.steps)
    assert first.final_state.state_hash == replay.final_state.state_hash
    assert first.to_dict() == replay.to_dict()
    assert resumed.status == "ready"
    assert resumed.final_state.state_hash == first.final_state.state_hash
    assert first.steps[0].metrics["tangent_solve_count"] == 0
    assert first.steps[0].to_dict()["claims"][
        "consistent_residual_tangent_matrix_free_newton"
    ] is False
    assert first.steps[1].metrics["tangent_solve_count"] > 0
    assert first.steps[1].to_dict()["claims"][
        "consistent_residual_tangent_matrix_free_newton"
    ] is True
    assert all(
        state.dissipated_energy_density_mj_per_m3 > 0.0
        for state in first.final_state.material_states
    )
    assert payload["metrics"]["fallback_count"] == 0
    assert payload["metrics"]["regularization_count"] == 0
    assert payload["metrics"]["material_state_changed_step_count"] >= 3
    assert payload["claims"]["transactional_material_state_load_path"] is True
    assert payload["claims"]["g1_full_building_closure"] is False


@pytest.mark.parametrize(
    ("problem_factory", "load_factors"),
    (
        (two_element_stateful_steel_chain_problem, (0.5, 1.0)),
        (
            two_element_concrete_damage_chain_problem,
            (0.25, 0.5, 0.75, 1.0),
        ),
        (
            two_element_composite_section_chain_problem,
            (0.25, 0.5, 0.75, 1.0),
        ),
        (two_element_bilinear_link_chain_problem, (0.5, 1.0)),
    ),
)
def test_matrix_free_material_path_covers_all_stateful_axial_families(
    problem_factory,
    load_factors: tuple[float, ...],
) -> None:
    problem = problem_factory()
    result = run_stateful_axial_matrix_free_load_path(
        problem,
        load_factors,
        config=_step_config(),
    )

    assert result.status == "ready"
    assert result.contract_pass is True
    assert result.final_state.load_factor == load_factors[-1]
    assert result.final_state.step_index == len(load_factors)
    assert any(
        step.metrics["material_state_changed"] for step in result.steps
    )
    assert all(
        step.metrics["final_residual_inf_kn"] <= 1.0e-9
        for step in result.steps
    )
    assert all(step.metrics["fallback_count"] == 0 for step in result.steps)
    assert all(
        step.metrics["regularization_count"] == 0
        for step in result.steps
    )


def test_stateful_matrix_free_step_rejects_ambiguous_or_invalid_contracts(
) -> None:
    problem = two_element_stateful_steel_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    invalid_targets = replace(
        _step_config(),
        target_load_factors=(0.5, 1.0),
    )
    with pytest.raises(
        StatefulAxialMatrixFreeNewtonError,
        match="must target exactly",
    ):
        solve_stateful_axial_matrix_free_load_step(
            problem,
            accepted,
            target_load_factor=1.0,
            config=invalid_targets,
        )
    with pytest.raises(
        StatefulAxialMatrixFreeNewtonError,
        match="must differ",
    ):
        StatefulAxialMatrixFreeLoadStepProblem(
            problem,
            accepted,
            accepted.load_factor,
        )

    fully_constrained = StatefulAxialChainProblem(
        case_id="stateful_axial_matrix_free_no_free_equations",
        node_count=2,
        elements=problem.elements[:1],
        fixed_nodes=(0, 1),
        reference_external_forces_kn=(),
    )
    with pytest.raises(
        StatefulAxialMatrixFreeNewtonError,
        match="at least one free equation",
    ):
        StatefulAxialMatrixFreeLoadStepProblem(
            fully_constrained,
            initial_stateful_axial_state(fully_constrained),
            1.0,
        )
