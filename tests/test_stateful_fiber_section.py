from __future__ import annotations

import json

import numpy as np
import pytest

from structural_analysis.materials import (
    FiberSectionNewtonConfig,
    StatefulFiberSectionState,
    StatefulRCFiberSection,
    StatefulSectionFiber,
    build_stateful_rc_fiber_section_benchmark,
    finite_difference_stateful_fiber_section_tangent_check,
    integrate_stateful_fiber_section_history,
    make_rectangular_stateful_rc_fiber_section,
    solve_stateful_fiber_section_resultants,
)
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.uniaxial_plasticity import (
    UniaxialPlasticityState,
)


def test_rectangular_rc_fiber_geometry_state_and_elastic_tangent_are_exact() -> None:
    section = make_rectangular_stateful_rc_fiber_section()
    repeated = make_rectangular_stateful_rc_fiber_section()
    initial = section.initial_state()
    response = section.integrate((0.0, 0.0), initial)

    assert section.contract_hash == repeated.contract_hash
    assert initial.state_hash == repeated.initial_state().state_hash
    assert len(section.fibers) == 14
    assert sum(f.material_kind == "concrete" for f in section.fibers) == 12
    assert sum(f.material_kind == "steel" for f in section.fibers) == 2
    assert (
        sum(isinstance(state, ConcreteDamageState) for state in initial.fiber_states)
        == 12
    )
    assert (
        sum(
            isinstance(state, UniaxialPlasticityState) for state in initial.fiber_states
        )
        == 2
    )
    assert response.parent_state_hash == initial.state_hash
    assert response.state.step_index == 1
    assert response.resultants.tolist() == [0.0, 0.0]
    assert response.consistent_tangent[0, 0] == pytest.approx(7_819_200.0)
    assert response.consistent_tangent[1, 1] == pytest.approx(253_200.0)
    assert response.consistent_tangent[0, 1] == pytest.approx(0.0, abs=1.0e-9)
    assert np.array_equal(
        response.consistent_tangent,
        response.consistent_tangent.T,
    )
    assert np.all(np.linalg.eigvalsh(response.consistent_tangent) > 0.0)
    assert response.consistent_tangent.flags.writeable is False
    assert response.fiber_strains.flags.writeable is False
    assert response.fiber_stresses_mpa.flags.writeable is False
    assert initial == section.initial_state()


def test_nonlinear_section_tangent_matches_same_parent_finite_difference() -> None:
    section = make_rectangular_stateful_rc_fiber_section()
    parent = section.initial_state()
    parent_bytes = parent.canonical_bytes()
    response = section.integrate((-3.0e-4, 6.0e-3), parent)
    check = finite_difference_stateful_fiber_section_tangent_check(
        section,
        parent,
    )

    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_inf_error"] <= check["relative_tolerance"]
    assert check["tangent_symmetry_error"] == 0.0
    assert response.consistent_tangent[0, 1] != 0.0
    assert response.yielded_steel_fiber_count > 0
    assert response.damaged_concrete_fiber_count > 0
    assert parent.canonical_bytes() == parent_bytes
    assert parent == section.initial_state()


def test_cyclic_section_history_updates_fibers_and_dissipation_exactly() -> None:
    section = make_rectangular_stateful_rc_fiber_section()
    path = (
        (-2.0e-4, 0.0),
        (-2.0e-4, 4.0e-3),
        (-2.0e-4, 9.0e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, -5.0e-3),
        (-2.0e-4, -9.0e-3),
        (-2.0e-4, 0.0),
    )
    first = integrate_stateful_fiber_section_history(section, path)
    second = integrate_stateful_fiber_section_history(section, path)

    assert first == second
    assert first["step_count"] == len(path)
    assert first["curvature_reversal_count"] >= 2
    assert first["yielded_step_count"] > 0
    assert first["concrete_damage_step_count"] > 0
    assert first["dissipated_energy_nonnegative_monotonic"] is True
    assert first["final_dissipated_energy_mj_per_m"] > 0.0
    assert first["final_state"]["state_hash"] != section.initial_state().state_hash


def test_manufactured_section_newton_path_replays_and_has_bounded_claims() -> None:
    first = build_stateful_rc_fiber_section_benchmark()
    second = build_stateful_rc_fiber_section_benchmark()

    assert first == second
    assert first["status"] == "partial"
    assert first["contract_pass"] is True
    assert first["verification"]["manufactured_newton_path_gate_passed"] is True
    assert first["verification"]["manufactured_newton_step_count"] == 6
    assert (
        first["verification"]["maximum_manufactured_solution_error_inf_norm"] <= 1.0e-10
    )
    assert first["verification"]["fallback_count"] == 0
    assert first["verification"]["regularization_count"] == 0
    assert first["verification"]["quadratic_convergence_gate_passed"] is True
    assert first["verification"]["minimum_tail_observed_convergence_order"] >= 1.8
    assert first["verification"]["damped_line_search_gate_passed"] is True
    assert first["verification"]["damped_line_search_minimum_alpha"] < 1.0
    assert (
        first["verification"]["damped_line_search_solution_error_inf_norm"] <= 1.0e-10
    )
    assert all(
        step["newton_result"]["status"] == "ready"
        and step["newton_result"]["metrics"]["contract_pass"] is True
        and step["newton_result"]["metrics"]["parent_state_immutable"] is True
        for step in first["manufactured_newton_path"]["steps"]
    )
    assert first["claims"]["bounded_stateful_rc_fiber_section"] is True
    assert first["claims"]["general_frame_or_shell_element"] is False
    assert first["claims"]["external_validation"] is False
    assert first["claims"]["production_sparse_or_rocm_hip"] is False
    assert first["claims"]["full_building_equilibrium"] is False
    assert first["claims"]["g1_closure"] is False
    assert (
        first["damped_line_search"]["newton_result"]["metrics"]["line_search_used"]
        is True
    )
    json.dumps(first, sort_keys=True, allow_nan=False)


def test_failed_section_newton_step_rolls_back_every_fiber_exactly() -> None:
    section = make_rectangular_stateful_rc_fiber_section()
    parent = section.initial_state()
    parent_bytes = parent.canonical_bytes()
    target = section.integrate((-2.0e-4, 6.0e-3), parent).resultants
    failed = solve_stateful_fiber_section_resultants(
        section,
        parent,
        target_resultants=target,
        config=FiberSectionNewtonConfig(maximum_iterations=0),
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


def test_section_contracts_fail_closed_for_invalid_geometry_and_state() -> None:
    with pytest.raises(ValueError, match="less than half"):
        make_rectangular_stateful_rc_fiber_section(cover_m=0.3)
    with pytest.raises(ValueError, match="at least 2"):
        make_rectangular_stateful_rc_fiber_section(concrete_layer_count=1)
    with pytest.raises(ValueError, match="strictly decreasing"):
        FiberSectionNewtonConfig(line_search_alphas=(1.0, 1.0))

    duplicate_fibers = (
        StatefulSectionFiber("same", 0.0, 0.1, "concrete"),
        StatefulSectionFiber("same", 0.1, 0.01, "steel"),
    )
    with pytest.raises(ValueError, match="unique"):
        StatefulRCFiberSection(fibers=duplicate_fibers)

    section = make_rectangular_stateful_rc_fiber_section()
    initial = section.initial_state()
    wrong_section = StatefulFiberSectionState(
        section_id="different-section",
        section_contract_hash=initial.section_contract_hash,
        step_index=initial.step_index,
        axial_strain=initial.axial_strain,
        curvature_z_per_m=initial.curvature_z_per_m,
        fiber_states=initial.fiber_states,
    )
    with pytest.raises(ValueError, match="section_id"):
        section.integrate((0.0, 0.0), wrong_section)

    different_contract = make_rectangular_stateful_rc_fiber_section(width_m=0.5)
    with pytest.raises(ValueError, match="section_contract_hash"):
        different_contract.integrate((0.0, 0.0), initial)
