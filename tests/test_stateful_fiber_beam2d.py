from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest

from structural_analysis.benchmark import (
    FiberBeamCantileverNewtonConfig,
    build_stateful_fiber_beam2d_benchmark,
    solve_stateful_fiber_beam2d_cantilever,
)
from structural_analysis.elements import (
    StatefulFiberBeam2D,
    finite_difference_stateful_fiber_beam2d_tangent_check,
    integrate_stateful_fiber_beam2d_history,
)
from structural_analysis.materials import (
    StatefulFiberSectionResponse,
    StatefulFiberSectionState,
    StatefulRCFiberSection,
    make_rectangular_stateful_rc_fiber_section,
)


def _element() -> StatefulFiberBeam2D:
    return StatefulFiberBeam2D(
        section=make_rectangular_stateful_rc_fiber_section(),
        length_m=3.0,
        integration_order=3,
    )


def test_uniform_section_strain_maps_to_exact_element_end_forces() -> None:
    element = _element()
    repeated = _element()
    initial = element.initial_state()
    local = np.array(
        element.uniform_generalized_strain_displacements(
            -3.0e-4,
            6.0e-3,
        ),
        copy=True,
    )
    assert local.flags.writeable is True
    local_before = local.copy()
    response = element.integrate(local, initial)
    section_resultants = response.section_responses[0].resultants

    assert element.contract_hash == repeated.contract_hash
    assert initial.state_hash == repeated.initial_state().state_hash
    assert len(initial.integration_point_states) == 3
    assert response.state.step_index == 1
    assert np.allclose(
        response.generalized_strains,
        np.tile((-3.0e-4, 6.0e-3), (3, 1)),
        rtol=0.0,
        atol=1.0e-15,
    )
    assert np.allclose(
        response.internal_force_local,
        (
            -section_resultants[0],
            0.0,
            -section_resultants[1],
            section_resultants[0],
            0.0,
            section_resultants[1],
        ),
        rtol=1.0e-13,
        atol=1.0e-10,
    )
    assert response.yielded_integration_point_count == 3
    assert response.damaged_integration_point_count == 3
    assert response.dissipated_energy_mj > 0.0
    assert response.local_displacements.flags.writeable is False
    assert response.internal_force_local.flags.writeable is False
    assert response.consistent_tangent_local.flags.writeable is False
    assert local.flags.writeable is True
    assert np.array_equal(local, local_before)
    assert initial == element.initial_state()


def test_elastic_cantilever_matches_closed_form_tip_response_and_reactions() -> None:
    element = _element()
    result = solve_stateful_fiber_beam2d_cantilever(
        element,
        element.initial_state(),
        target_tip_load=(0.0, -10.0, 0.0),
    )
    flexural_rigidity = 253_200.0
    length = element.length_m
    expected_transverse = -10.0 * length**3 / (3.0 * flexural_rigidity)
    expected_rotation = -10.0 * length**2 / (2.0 * flexural_rigidity)

    assert result.status == "ready"
    assert result.metrics["contract_pass"] is True
    assert result.solution_tip_displacements[0] == pytest.approx(0.0, abs=1.0e-18)
    assert result.solution_tip_displacements[1] == pytest.approx(
        expected_transverse,
        abs=1.0e-15,
    )
    assert result.solution_tip_displacements[2] == pytest.approx(
        expected_rotation,
        abs=1.0e-15,
    )
    assert result.trial_response.internal_force_local[:3] == pytest.approx(
        (0.0, 10.0, 30.0),
        abs=1.0e-10,
    )
    assert result.metrics["final_scaled_residual_inf_norm"] <= 1.0e-10
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert (
        len(
            {
                state.state_hash
                for state in result.accepted_state.integration_point_states
            }
        )
        == element.integration_order
    )


def test_nonlinear_element_tangent_matches_same_parent_finite_difference() -> None:
    element = _element()
    parent = element.initial_state()
    parent_bytes = parent.canonical_bytes()
    check = finite_difference_stateful_fiber_beam2d_tangent_check(
        element,
        parent,
    )

    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_inf_error"] <= check["relative_tolerance"]
    assert check["tangent_symmetry_error"] <= 1.0e-10
    assert parent.canonical_bytes() == parent_bytes
    assert parent == element.initial_state()


def test_element_rejects_section_response_bound_to_wrong_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    element = _element()
    parent = element.initial_state()
    parent_bytes = parent.canonical_bytes()
    integrate = StatefulRCFiberSection.integrate

    def tampered_integrate(
        section: StatefulRCFiberSection,
        generalized_strain: object,
        committed_state: StatefulFiberSectionState,
    ) -> StatefulFiberSectionResponse:
        response = integrate(section, generalized_strain, committed_state)
        return replace(response, parent_state_hash="sha256:" + "0" * 64)

    monkeypatch.setattr(StatefulRCFiberSection, "integrate", tampered_integrate)

    with pytest.raises(ValueError, match="section response parent_state_hash"):
        element.integrate(np.zeros(6), parent)

    assert parent.canonical_bytes() == parent_bytes


def test_cyclic_element_history_updates_gauss_states_and_energy_exactly() -> None:
    element = _element()
    generalized_path = (
        (-2.0e-4, 0.0),
        (-2.0e-4, 4.0e-3),
        (-2.0e-4, 9.0e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, -5.0e-3),
        (-2.0e-4, -9.0e-3),
        (-2.0e-4, 0.0),
    )
    path = tuple(
        element.uniform_generalized_strain_displacements(axial, curvature)
        for axial, curvature in generalized_path
    )
    first = integrate_stateful_fiber_beam2d_history(element, path)
    second = integrate_stateful_fiber_beam2d_history(element, path)

    assert first == second
    assert first["step_count"] == len(path)
    assert first["curvature_reversal_count"] >= 2
    assert first["yielded_step_count"] > 0
    assert first["concrete_damage_step_count"] > 0
    assert first["dissipated_energy_nonnegative_monotonic"] is True
    assert first["final_dissipated_energy_mj"] > 0.0
    assert first["final_state"]["state_hash"] != element.initial_state().state_hash


def test_beam_benchmark_replays_newton_and_keeps_claims_bounded() -> None:
    first = build_stateful_fiber_beam2d_benchmark()
    second = build_stateful_fiber_beam2d_benchmark()

    assert first == second
    assert first["status"] == "partial"
    assert first["contract_pass"] is True
    verification = first["verification"]
    assert verification["elastic_euler_bernoulli_reference_passed"] is True
    assert verification["elastic_cantilever_tip_load_passed"] is True
    assert verification["rigid_body_patch_passed"] is True
    assert verification["consistent_6x6_tangent_finite_difference_passed"] is True
    assert verification["cyclic_gauss_state_and_energy_gate_passed"] is True
    assert verification["manufactured_cantilever_newton_gate_passed"] is True
    assert verification["manufactured_cantilever_step_count"] == 6
    assert verification["maximum_manufactured_solution_error_inf_norm"] <= 1.0e-10
    assert verification["quadratic_convergence_gate_passed"] is True
    assert verification["minimum_tail_observed_convergence_order"] >= 1.8
    assert verification["damped_line_search_gate_passed"] is True
    assert verification["damped_line_search_minimum_alpha"] <= 0.125
    assert verification["damped_line_search_solution_error_inf_norm"] <= 1.0e-10
    assert verification["gauss_point_state_coupling_passed"] is True
    assert verification["section_response_parent_binding_passed"] is True
    assert verification["deterministic_replay_exact"] is True
    assert verification["forced_failure_rollback_exact"] is True
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0
    assert first["claims"]["bounded_stateful_rc_fiber_beam2d_element"] is True
    assert first["claims"]["authoritative_restart_chain"] is False
    assert first["claims"]["product_commit_path"] is False
    assert first["claims"]["generalized_axial_curvature_section_protocol"] is False
    assert first["claims"]["multi_element_global_assembly"] is False
    assert first["claims"]["geometric_nonlinearity"] is False
    assert first["claims"]["general_plastic_hinge_or_distributed_plasticity"] is False
    assert first["claims"]["external_validation"] is False
    assert first["claims"]["production_sparse_or_rocm_hip"] is False
    assert first["claims"]["full_building_equilibrium"] is False
    assert first["claims"]["g1_closure"] is False
    json.dumps(first, sort_keys=True, allow_nan=False)


def test_failed_cantilever_newton_step_rolls_back_all_gauss_states() -> None:
    element = _element()
    parent = element.initial_state()
    parent_bytes = parent.canonical_bytes()
    truth = element.integrate(
        element.uniform_generalized_strain_displacements(-2.0e-4, 6.0e-3),
        parent,
    )
    failed = solve_stateful_fiber_beam2d_cantilever(
        element,
        parent,
        target_tip_load=truth.internal_force_local[3:],
        config=FiberBeamCantileverNewtonConfig(maximum_iterations=0),
    )

    assert failed.status == "blocked"
    assert failed.committed is False
    assert failed.terminal_reason == "maximum_iterations_exhausted"
    assert failed.accepted_state is parent
    assert failed.accepted_state.canonical_bytes() == parent_bytes
    assert failed.metrics["contract_pass"] is False
    assert failed.metrics["parent_state_immutable"] is True
    assert failed.metrics["rollback_exact"] is True
    assert failed.metrics["fallback_count"] == 0
    assert failed.metrics["regularization_count"] == 0


def test_element_and_cantilever_contracts_fail_closed() -> None:
    section = make_rectangular_stateful_rc_fiber_section()
    with pytest.raises(ValueError, match="positive"):
        StatefulFiberBeam2D(section=section, length_m=0.0)
    with pytest.raises(ValueError, match="2 or 3"):
        StatefulFiberBeam2D(section=section, integration_order=4)
    with pytest.raises(ValueError, match=r"\[-1, 1\]"):
        _element().strain_displacement_matrix(1.1)
    with pytest.raises(ValueError, match="strictly decreasing"):
        FiberBeamCantileverNewtonConfig(line_search_alphas=(1.0, 1.0))

    element = _element()
    parent = element.initial_state()
    different_contract = StatefulFiberBeam2D(
        section=section,
        length_m=4.0,
        element_id=element.element_id,
    )
    with pytest.raises(ValueError, match="element_contract_hash"):
        different_contract.integrate(np.zeros(6), parent)

    translated = element.integrate(
        (1.0e-3, 0.0, 0.0, 1.0e-3, 0.0, 0.0),
        parent,
    ).state
    with pytest.raises(ValueError, match="fixed zero base"):
        solve_stateful_fiber_beam2d_cantilever(
            element,
            translated,
            target_tip_load=(0.0, 0.0, 0.0),
        )
