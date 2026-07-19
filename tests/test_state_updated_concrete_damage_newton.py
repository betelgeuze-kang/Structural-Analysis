from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    assemble_stateful_axial_chain,
    finite_difference_stateful_axial_jacobian_check,
    initial_stateful_axial_state,
    run_stateful_axial_load_path,
    single_element_concrete_damage_bar_problem,
    solve_stateful_axial_load_step,
    two_element_concrete_damage_chain_problem,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    finite_difference_concrete_damage_tangent_check,
    integrate_concrete_damage_history,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-9,
    increment_tolerance=1.0e-12,
    max_iterations=30,
)
LOAD_FACTORS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


@pytest.mark.parametrize(
    ("strain", "branch"),
    ((0.0003, "tension"), (-0.002, "compression")),
)
def test_concrete_damage_tension_and_compression_tangents_match_finite_difference(
    strain: float,
    branch: str,
) -> None:
    material = AsymmetricConcreteDamageMaterial()
    committed = material.initial_state()
    check = finite_difference_concrete_damage_tangent_check(
        material,
        committed,
        total_strain=strain,
    )
    response = material.integrate(strain, committed)

    assert response.active_branch == branch
    assert response.damage_evolved is True
    assert response.active_damage > 0.0
    assert response.consistent_tangent_mpa < 0.0
    assert response.state.dissipated_energy_density_mj_per_m3 > 0.0
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-6
    assert committed == material.initial_state()


def test_concrete_damage_is_irreversible_and_unloads_with_secant_stiffness() -> None:
    material = AsymmetricConcreteDamageMaterial()
    initial = material.initial_state()
    damaged = material.integrate(-0.002, initial)
    unloading = material.integrate(-0.0005, damaged.state)

    expected_unloading_tangent = material.elastic_modulus_mpa * (
        1.0 - damaged.state.compressive_damage
    )
    assert damaged.damage_evolved is True
    assert unloading.damage_evolved is False
    assert unloading.state.compressive_damage == damaged.state.compressive_damage
    assert unloading.state.compressive_history_strain == (
        damaged.state.compressive_history_strain
    )
    assert unloading.consistent_tangent_mpa == pytest.approx(
        expected_unloading_tangent
    )
    assert unloading.consistent_tangent_mpa > 0.0
    assert unloading.state.dissipated_energy_density_mj_per_m3 == (
        damaged.state.dissipated_energy_density_mj_per_m3
    )


def test_concrete_cyclic_path_records_both_damage_branches_and_energy() -> None:
    material = AsymmetricConcreteDamageMaterial()
    strains = (
        0.0,
        -0.0005,
        -0.002,
        0.0,
        0.0002,
        0.0,
        -0.003,
        0.0,
        0.0004,
        0.0,
    )
    first = integrate_concrete_damage_history(material, strains)
    second = integrate_concrete_damage_history(material, strains)

    assert first == second
    assert first["reversal_count"] >= 4
    assert first["damage_evolution_step_count"] >= 4
    assert first["damage_irreversible"] is True
    assert first["dissipation_nonnegative_monotonic"] is True
    assert first["energy_damage_gate_passed"] is True
    assert first["final_state"]["tensile_damage"] > 0.0
    assert first["final_state"]["compressive_damage"] > 0.0
    assert first["cumulative_dissipated_energy_density_mj_per_m3"] > 0.0


def test_single_concrete_bar_matches_analytic_compression_softening_response() -> None:
    problem = single_element_concrete_damage_bar_problem()
    initial = initial_stateful_axial_state(problem)
    assembly = assemble_stateful_axial_chain(
        problem,
        initial,
        target_load_factor=1.0,
        trial_free_displacements_m=np.asarray([], dtype=float),
    )

    expected_stress = -30.0 * math.exp(-400.0 * (0.002 - 0.001))
    expected_force_kn = expected_stress * 0.01 * 1000.0
    row = assembly.element_responses[0]
    assert row["total_strain"] == pytest.approx(-0.002)
    assert row["internal_force_kn"] == pytest.approx(expected_force_kn)
    assert row["material_response"]["damage_evolved"] is True
    assert row["material_response"]["active_branch"] == "compression"
    assert assembly.reactions_kn[0] == pytest.approx(-expected_force_kn)
    assert assembly.reactions_kn[1] == pytest.approx(expected_force_kn)
    assert assembly.residual_kn.size == 0


def test_two_element_damage_structure_commits_localized_softening_path_exactly() -> None:
    problem = two_element_concrete_damage_chain_problem()
    first = run_stateful_axial_load_path(problem, LOAD_FACTORS, config=CONFIG)
    second = run_stateful_axial_load_path(problem, LOAD_FACTORS, config=CONFIG)

    assert first.status == "ready"
    assert first.contract_pass is True
    assert all(step.committed for step in first.steps)
    assert first.to_dict() == second.to_dict()
    assert first.final_state.state_hash == second.final_state.state_hash
    assert all(
        step.metrics["regularization_used"] is False
        and step.metrics["fallback_used"] is False
        for step in first.steps
    )
    for step in first.steps:
        forces = [
            row["internal_force_kn"]
            for row in step.trial_assembly.element_responses
        ]
        assert max(forces) - min(forces) <= 1.0e-8
        assert np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf) <= 1.0e-8

    final_strains = [
        row["total_strain"]
        for row in first.steps[-1].trial_assembly.element_responses
    ]
    assert abs(final_strains[0] - final_strains[1]) > 0.003
    assert sum(final_strains) == pytest.approx(-0.004)
    final_damage = [
        state.compressive_damage for state in first.final_state.material_states
    ]
    assert max(final_damage) > 0.9
    assert min(final_damage) == 0.0


def test_localized_damage_structure_jacobian_matches_same_parent_difference() -> None:
    problem = two_element_concrete_damage_chain_problem()
    path = run_stateful_axial_load_path(
        problem,
        LOAD_FACTORS[:6],
        config=CONFIG,
    )
    parent = path.steps[4].accepted_state
    trial = path.steps[5].trial_solution.free_displacements_m
    check = finite_difference_stateful_axial_jacobian_check(
        problem,
        parent,
        target_load_factor=0.6,
        trial_free_displacements_m=trial,
        epsilon=1.0e-9,
        relative_tolerance=1.0e-6,
    )

    assert path.status == "ready"
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-6


def test_failed_concrete_damage_newton_step_rolls_back_exact_state() -> None:
    problem = two_element_concrete_damage_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    failed = solve_stateful_axial_load_step(
        problem,
        accepted,
        target_load_factor=0.75,
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    assert failed.status == "blocked"
    assert failed.committed is False
    assert failed.metrics["rollback_exact"] is True
    assert failed.accepted_state is accepted
    assert failed.accepted_state.state_hash == accepted.state_hash
    assert failed.accepted_state.canonical_bytes() == accepted.canonical_bytes()
    assert failed.metrics["material_state_changed"] is False
