from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    assemble_stateful_axial_chain,
    finite_difference_stateful_axial_jacobian_check,
    initial_stateful_axial_state,
    run_stateful_axial_load_path,
    single_element_bilinear_link_problem,
    solve_stateful_axial_load_step,
    two_element_bilinear_link_chain_problem,
)
from structural_analysis.materials.bilinear_link import (
    BilinearCombinedHardeningLink,
    finite_difference_link_tangent_check,
    integrate_link_deformation_history,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-10,
    increment_tolerance=1.0e-12,
    max_iterations=20,
)
LOAD_FACTORS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def test_link_return_mapping_and_tangent_use_force_deformation_units() -> None:
    material = BilinearCombinedHardeningLink()
    committed = material.initial_state()
    response = material.integrate(0.03, committed)
    check = finite_difference_link_tangent_check(
        material,
        committed,
        deformation_m=0.03,
    )
    expected_tangent = 10_000.0 * 500.0 / 10_500.0

    assert response.yielded is True
    assert response.force_kn == pytest.approx(109.52380952380952)
    assert response.consistent_tangent_kn_per_m == pytest.approx(expected_tangent)
    assert response.state.accumulated_plastic_deformation_m > 0.0
    assert response.state.dissipated_energy_kn_m > 0.0
    assert abs(response.final_yield_function_kn) <= 1.0e-10
    assert response.committed_state_hash == committed.state_hash
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-7
    assert committed == material.initial_state()


def test_link_cyclic_path_records_reversal_and_energy_dissipation() -> None:
    material = BilinearCombinedHardeningLink()
    deformations = (0.0, 0.005, 0.03, 0.0, -0.03, 0.0, 0.03, 0.0)
    first = integrate_link_deformation_history(material, deformations)
    second = integrate_link_deformation_history(material, deformations)

    assert first == second
    assert first["yielded_step_count"] >= 5
    assert first["plastic_flow_reversal_count"] >= 3
    assert first["dissipation_nonnegative_monotonic"] is True
    assert first["energy_gate_passed"] is True
    assert first["cumulative_dissipated_energy_kn_m"] > 0.0


def test_single_link_element_assembles_native_force_and_tangent() -> None:
    material = BilinearCombinedHardeningLink()
    problem = single_element_bilinear_link_problem(material=material)
    initial = initial_stateful_axial_state(problem)
    assembly = assemble_stateful_axial_chain(
        problem,
        initial,
        target_load_factor=1.0,
        trial_free_displacements_m=np.asarray([], dtype=float),
    )
    response = material.integrate(0.03, material.initial_state())
    row = assembly.element_responses[0]

    assert row["response_kind"] == "force_deformation"
    assert row["total_strain"] is None
    assert row["generalized_deformation"] == pytest.approx(0.03)
    assert row["internal_force_kn"] == pytest.approx(response.force_kn)
    assert row["tangent_kn_per_m"] == pytest.approx(
        response.consistent_tangent_kn_per_m
    )
    assert abs(sum(assembly.reactions_kn)) <= 1.0e-10


def test_two_link_structure_commits_uniform_hysteretic_path_deterministically() -> None:
    problem = two_element_bilinear_link_chain_problem()
    first = run_stateful_axial_load_path(problem, LOAD_FACTORS, config=CONFIG)
    second = run_stateful_axial_load_path(problem, LOAD_FACTORS, config=CONFIG)

    assert first.status == "ready"
    assert first.contract_pass is True
    assert first.to_dict() == second.to_dict()
    assert first.final_state.state_hash == second.final_state.state_hash
    for step in first.steps:
        forces = [
            row["internal_force_kn"]
            for row in step.trial_assembly.element_responses
        ]
        deformations = [
            row["generalized_deformation"]
            for row in step.trial_assembly.element_responses
        ]
        assert max(forces) - min(forces) <= 1.0e-10
        assert max(deformations) - min(deformations) <= 1.0e-12
        assert np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf) <= 1.0e-10
        assert step.metrics["regularization_used"] is False
        assert step.metrics["fallback_used"] is False
    assert all(
        state.accumulated_plastic_deformation_m > 0.0
        for state in first.final_state.material_states
    )


def test_two_link_structure_jacobian_matches_same_parent_difference() -> None:
    problem = two_element_bilinear_link_chain_problem()
    path = run_stateful_axial_load_path(
        problem,
        LOAD_FACTORS[:6],
        config=CONFIG,
    )
    check = finite_difference_stateful_axial_jacobian_check(
        problem,
        path.steps[4].accepted_state,
        target_load_factor=0.6,
        trial_free_displacements_m=path.steps[5].trial_solution.free_displacements_m,
    )

    assert path.status == "ready"
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-7


def test_failed_link_newton_step_rolls_back_exact_link_states() -> None:
    problem = two_element_bilinear_link_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    failed = solve_stateful_axial_load_step(
        problem,
        accepted,
        target_load_factor=1.0,
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    assert failed.status == "blocked"
    assert failed.committed is False
    assert failed.metrics["rollback_exact"] is True
    assert failed.accepted_state is accepted
    assert failed.accepted_state.state_hash == accepted.state_hash
    assert failed.accepted_state.canonical_bytes() == accepted.canonical_bytes()
