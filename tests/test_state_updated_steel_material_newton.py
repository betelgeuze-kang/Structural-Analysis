from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    assemble_stateful_axial_chain,
    finite_difference_stateful_axial_jacobian_check,
    initial_stateful_axial_state,
    run_stateful_axial_load_path,
    single_element_stateful_steel_bar_problem,
    solve_stateful_axial_load_step,
    two_element_stateful_steel_chain_problem,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityState,
    finite_difference_consistent_tangent_check,
    integrate_strain_history,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-10,
    increment_tolerance=1.0e-12,
    max_iterations=20,
)


@pytest.mark.parametrize("value", (True, "0.0", 2**53 + 1, 0.0 + 0.0j))
def test_steel_state_and_material_reject_coercive_binary64_sources(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="losslessly representable real binary64"):
        UniaxialPlasticityState(plastic_strain=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="losslessly representable real binary64"):
        BilinearCombinedHardeningSteel(  # type: ignore[arg-type]
            yield_stress_mpa=value,
        )
    material = BilinearCombinedHardeningSteel()
    with pytest.raises(ValueError, match="losslessly representable real binary64"):
        material.integrate(value, material.initial_state())  # type: ignore[arg-type]


def test_steel_state_normalizes_exact_numeric_sources_before_hashing() -> None:
    state = UniaxialPlasticityState(
        plastic_strain=-0.0,
        backstress_mpa=0,
        accumulated_plastic_strain=0,
        dissipated_energy_density_mj_per_m3=0,
    )
    material = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000,
        yield_stress_mpa=250,
        isotropic_hardening_modulus_mpa=3_000,
        kinematic_hardening_modulus_mpa=5_000,
        yield_tolerance_mpa=0,
    )

    assert state.state_hash == UniaxialPlasticityState().state_hash
    assert all(
        type(value) is float
        for value in (
            state.plastic_strain,
            state.backstress_mpa,
            state.accumulated_plastic_strain,
            state.dissipated_energy_density_mj_per_m3,
            material.elastic_modulus_mpa,
            material.yield_stress_mpa,
        )
    )


@pytest.mark.parametrize(
    ("isotropic_hardening", "kinematic_hardening"),
    ((8_000.0, 0.0), (0.0, 8_000.0), (3_000.0, 5_000.0)),
)
def test_return_mapping_supports_isotropic_kinematic_and_combined_hardening(
    isotropic_hardening: float,
    kinematic_hardening: float,
) -> None:
    material = BilinearCombinedHardeningSteel(
        isotropic_hardening_modulus_mpa=isotropic_hardening,
        kinematic_hardening_modulus_mpa=kinematic_hardening,
    )
    committed = material.initial_state()
    response = material.integrate(0.01, committed)

    expected_tangent = 200_000.0 * 8_000.0 / 208_000.0
    assert response.yielded is True
    assert response.consistent_tangent_mpa == pytest.approx(expected_tangent)
    assert response.plastic_multiplier_increment > 0.0
    assert abs(response.final_yield_function_mpa) <= 1.0e-10
    assert response.state.accumulated_plastic_strain > 0.0
    assert response.state.dissipated_energy_density_mj_per_m3 > 0.0
    assert response.committed_state_hash == committed.state_hash
    assert committed == material.initial_state()


def test_material_consistent_tangent_uses_one_immutable_parent_state() -> None:
    material = BilinearCombinedHardeningSteel()
    committed = material.initial_state()
    parent_hash = committed.state_hash
    check = finite_difference_consistent_tangent_check(
        material,
        committed,
        total_strain=0.01,
    )

    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-7
    assert committed.state_hash == parent_hash
    assert committed.accumulated_plastic_strain == 0.0


def test_cyclic_path_records_reversal_and_nonnegative_energy_dissipation() -> None:
    material = BilinearCombinedHardeningSteel()
    strains = (0.0, 0.003, 0.008, 0.0, -0.008, 0.0, 0.008, 0.0)
    first = integrate_strain_history(material, strains)
    second = integrate_strain_history(material, strains)

    assert first == second
    assert first["yielded_step_count"] >= 3
    assert first["plastic_flow_reversal_count"] >= 2
    assert first["dissipation_nonnegative_monotonic"] is True
    assert first["energy_dissipation_gate_passed"] is True
    assert first["cumulative_dissipated_energy_density_mj_per_m3"] > 0.0
    dissipations = [
        row["trial_state"]["dissipated_energy_density_mj_per_m3"]
        for row in first["history"]
    ]
    assert dissipations == sorted(dissipations)


def test_single_bar_element_newton_matches_analytic_bilinear_solution() -> None:
    problem = single_element_stateful_steel_bar_problem()
    initial = initial_stateful_axial_state(problem)
    result = solve_stateful_axial_load_step(
        problem,
        initial,
        target_load_factor=1.0,
        config=CONFIG,
    )

    hardening = 8_000.0
    plastic_tangent = 200_000.0 * hardening / (200_000.0 + hardening)
    expected_strain = 250.0 / 200_000.0 + (300.0 - 250.0) / plastic_tangent
    expected_displacement = 2.0 * expected_strain

    assert result.status == "ready"
    assert result.committed is True
    assert result.metrics["solver_contract_pass"] is True
    assert result.metrics["material_state_changed"] is True
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    assert result.accepted_state.displacements_m[-1] == pytest.approx(
        expected_displacement,
        abs=1.0e-14,
    )
    assert result.trial_assembly.residual_kn.tolist() == pytest.approx([0.0])
    assert result.trial_assembly.element_responses[0][
        "internal_force_kn"
    ] == pytest.approx(3_000.0)


def test_two_element_structure_cyclic_path_commits_state_and_replays_exactly() -> None:
    problem = two_element_stateful_steel_chain_problem()
    factors = (0.5, 1.0, 0.0, -1.0, 0.0, 1.0)
    first = run_stateful_axial_load_path(problem, factors, config=CONFIG)
    second = run_stateful_axial_load_path(problem, factors, config=CONFIG)

    assert first.status == "ready"
    assert first.contract_pass is True
    assert len(first.steps) == len(factors)
    assert all(step.committed for step in first.steps)
    assert first.final_state.state_hash == second.final_state.state_hash
    assert first.to_dict() == second.to_dict()
    assert all(
        state.dissipated_energy_density_mj_per_m3 > 0.0
        for state in first.final_state.material_states
    )
    for step, factor in zip(first.steps, factors, strict=True):
        element_forces = [
            row["internal_force_kn"]
            for row in step.trial_assembly.element_responses
        ]
        assert max(element_forces) - min(element_forces) <= 1.0e-9
        assert element_forces[-1] == pytest.approx(3_000.0 * factor, abs=1.0e-9)
        assert np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf) <= 1.0e-9


def test_stateful_structure_jacobian_matches_same_parent_finite_difference() -> None:
    problem = two_element_stateful_steel_chain_problem()
    half_step = solve_stateful_axial_load_step(
        problem,
        initial_stateful_axial_state(problem),
        target_load_factor=0.5,
        config=CONFIG,
    )
    full_step = solve_stateful_axial_load_step(
        problem,
        half_step.accepted_state,
        target_load_factor=1.0,
        config=CONFIG,
    )
    check = finite_difference_stateful_axial_jacobian_check(
        problem,
        half_step.accepted_state,
        target_load_factor=1.0,
        trial_free_displacements_m=full_step.trial_solution.free_displacements_m,
    )

    assert half_step.committed is True
    assert full_step.committed is True
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_error"] <= 1.0e-7


def test_failed_material_newton_step_rolls_back_exact_accepted_state() -> None:
    problem = two_element_stateful_steel_chain_problem()
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
    assert failed.metrics["material_state_changed"] is False
    assert failed.trial_assembly.element_responses[0]["material_response"][
        "yielded"
    ] is True


def test_stateful_accepted_checkpoint_rejects_forged_hash() -> None:
    problem = single_element_stateful_steel_bar_problem()
    state = initial_stateful_axial_state(problem)

    with pytest.raises(ValueError, match="hash does not match"):
        replace(state, state_hash="sha256:" + "0" * 64)


def test_assembly_reconstructs_committed_equilibrium_without_state_mutation() -> None:
    problem = two_element_stateful_steel_chain_problem()
    path = run_stateful_axial_load_path(problem, (0.5, 1.0), config=CONFIG)
    accepted = path.final_state
    free = np.asarray(accepted.displacements_m)[list(problem.free_node_indices)]
    replay = assemble_stateful_axial_chain(
        problem,
        accepted,
        target_load_factor=accepted.load_factor,
        trial_free_displacements_m=free,
    )

    assert replay.parent_state_hash == accepted.state_hash
    assert np.linalg.norm(replay.residual_kn, ord=np.inf) <= 1.0e-9
    assert all(
        before.state_hash == after.state_hash
        for before, after in zip(
            accepted.material_states,
            replay.trial_material_states,
            strict=True,
        )
    )
