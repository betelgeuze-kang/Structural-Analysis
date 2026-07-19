from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    assemble_stateful_axial_chain,
    finite_difference_stateful_axial_jacobian_check,
    initial_stateful_axial_state,
    run_stateful_axial_load_path,
    single_element_composite_section_bar_problem,
    solve_stateful_axial_load_step,
    two_element_composite_section_chain_problem,
)
from structural_analysis.materials.composite_section import (
    ParallelSteelConcreteSectionMaterial,
    finite_difference_composite_section_tangent_check,
    integrate_composite_section_history,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-9,
    increment_tolerance=1.0e-12,
    max_iterations=30,
)
LOAD_FACTORS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


@pytest.mark.parametrize("strain", (0.0003, 0.002, -0.002))
def test_parallel_composite_tangent_matches_same_parent_finite_difference(
    strain: float,
) -> None:
    material = ParallelSteelConcreteSectionMaterial()
    committed = material.initial_state()
    response = material.integrate(strain, committed)
    check = finite_difference_composite_section_tangent_check(
        material,
        committed,
        total_strain=strain,
    )
    weighted_stress = (
        material.steel_area_fraction * response.steel_response.stress_mpa
        + material.concrete_area_fraction
        * response.concrete_response.stress_mpa
    )
    weighted_tangent = (
        material.steel_area_fraction
        * response.steel_response.consistent_tangent_mpa
        + material.concrete_area_fraction
        * response.concrete_response.consistent_tangent_mpa
    )

    assert response.stress_mpa == pytest.approx(weighted_stress)
    assert response.consistent_tangent_mpa == pytest.approx(weighted_tangent)
    assert response.committed_state_hash == committed.state_hash
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-6
    assert committed == material.initial_state()


def test_composite_cyclic_path_updates_both_constituents_and_energy() -> None:
    material = ParallelSteelConcreteSectionMaterial()
    strains = (0.0, 0.0005, 0.002, 0.0, -0.002, 0.0, 0.002, 0.0)
    first = integrate_composite_section_history(material, strains)
    second = integrate_composite_section_history(material, strains)

    assert first == second
    assert first["reversal_count"] >= 3
    assert first["steel_yield_step_count"] >= 2
    assert first["concrete_damage_step_count"] >= 2
    assert first["constituent_state_gate_passed"] is True
    assert first["dissipation_nonnegative_monotonic"] is True
    assert first["energy_gate_passed"] is True
    assert first["cumulative_dissipated_energy_density_mj_per_m3"] > 0.0


def test_single_composite_bar_force_uses_area_weighted_constituent_response() -> None:
    material = ParallelSteelConcreteSectionMaterial()
    problem = single_element_composite_section_bar_problem(material=material)
    initial = initial_stateful_axial_state(problem)
    assembly = assemble_stateful_axial_chain(
        problem,
        initial,
        target_load_factor=1.0,
        trial_free_displacements_m=np.asarray([], dtype=float),
    )
    response = material.integrate(0.002, material.initial_state())
    expected_force_kn = response.stress_mpa * 0.1 * 1000.0

    row = assembly.element_responses[0]
    assert row["total_strain"] == pytest.approx(0.002)
    assert row["internal_force_kn"] == pytest.approx(expected_force_kn)
    assert row["material_response"]["yielded"] is True
    assert row["material_response"]["damage_evolved"] is True
    assert abs(sum(assembly.reactions_kn)) <= 1.0e-10


def test_two_element_composite_structure_replays_uniform_equilibrium_path() -> None:
    problem = two_element_composite_section_chain_problem()
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
        strains = [
            row["total_strain"]
            for row in step.trial_assembly.element_responses
        ]
        assert max(forces) - min(forces) <= 1.0e-8
        assert max(strains) - min(strains) <= 1.0e-12
        assert np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf) <= 1.0e-8
        assert step.metrics["regularization_used"] is False
        assert step.metrics["fallback_used"] is False
    assert all(
        state.steel_state.accumulated_plastic_strain > 0.0
        and state.concrete_state.tensile_damage > 0.0
        for state in first.final_state.material_states
    )


def test_composite_structure_jacobian_matches_same_parent_difference() -> None:
    problem = two_element_composite_section_chain_problem()
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
        epsilon=1.0e-9,
        relative_tolerance=1.0e-6,
    )

    assert path.status == "ready"
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-6


def test_failed_composite_newton_step_rolls_back_both_constituent_states() -> None:
    problem = two_element_composite_section_chain_problem()
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
