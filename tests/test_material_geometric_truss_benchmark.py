from __future__ import annotations

import json
from typing import Any

import numpy as np
import pytest

from structural_analysis.benchmark.material_geometric_truss import (
    MATERIAL_GEOMETRIC_TRUSS_SCHEMA_VERSION,
    StatefulTwoBarTrussAcceptedState,
    StatefulTwoBarTrussProblem,
    corotational_truss_element_response,
    finite_difference_two_bar_truss_tangent_check,
    material_geometric_two_bar_truss_benchmark,
    run_stateful_two_bar_truss_load_path,
    solve_stateful_two_bar_truss_load_step,
    symmetric_scalar_equilibrium_displacement_m,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict[str, Any]:
    return material_geometric_two_bar_truss_benchmark()


def test_current_chord_element_is_objective_for_a_rigid_quarter_turn() -> None:
    material = BilinearCombinedHardeningSteel()
    committed = material.initial_state()
    response = corotational_truss_element_response(
        element_id="rigid-rotation-bar",
        base_coordinate_m=(0.0, 0.0),
        initial_apex_coordinate_m=(1.0, 0.0),
        apex_displacement_m=(-1.0, 1.0),
        area_m2=0.001,
        material=material,
        committed_state=committed,
    )

    assert response.current_length_m == pytest.approx(response.initial_length_m)
    assert response.engineering_strain == pytest.approx(0.0)
    np.testing.assert_allclose(response.internal_force_kn, np.zeros(2), atol=1e-12)
    np.testing.assert_allclose(
        response.geometric_tangent_kn_per_m,
        np.zeros((2, 2)),
        atol=1e-12,
    )
    assert response.material_response.state is committed
    assert response.current_direction == pytest.approx([0.0, 1.0])


def test_material_and_geometric_tangent_matches_same_parent_difference() -> None:
    problem = StatefulTwoBarTrussProblem()
    parent = problem.initial_state()
    parent_bytes = parent.canonical_bytes()
    check = finite_difference_two_bar_truss_tangent_check(problem, parent)

    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["both_tangent_terms_required"] is True
    assert check["full_tangent_relative_inf_error"] <= 1.0e-8
    assert check["material_only_relative_inf_error"] >= 1.0e-2
    assert check["geometric_only_relative_inf_error"] >= 0.9
    assert check["tangent_symmetry_relative_inf_error"] <= 1.0e-12
    assert parent.canonical_bytes() == parent_bytes


def test_two_dof_newton_matches_independent_symmetric_scalar_reduction() -> None:
    problem = StatefulTwoBarTrussProblem()
    parent = problem.initial_state()
    step = solve_stateful_two_bar_truss_load_step(
        problem,
        parent,
        target_load_factor=0.8,
    )
    reference_vertical = symmetric_scalar_equilibrium_displacement_m(
        problem,
        parent,
        target_load_factor=0.8,
    )

    assert step.committed is True
    assert step.status == "ready"
    assert step.accepted_state.step_index == 1
    assert step.accepted_state.apex_displacements_m[0] == pytest.approx(
        0.0,
        abs=1.0e-14,
    )
    assert step.accepted_state.apex_displacements_m[1] == pytest.approx(
        reference_vertical,
        abs=1.0e-12,
    )
    assert reference_vertical == pytest.approx(-0.005521170805293557)
    assert step.metrics["residual_inf_norm_kn"] <= 1.0e-8
    assert step.metrics["material_and_geometric_terms_active"] is True
    assert step.metrics["tangent_decomposition_inf_error_kn_per_m"] <= 1.0e-10
    assert step.trial_solution.metrics["regularization_used"] is False
    assert step.trial_solution.metrics["fallback_used"] is False


def test_failed_newton_attempt_rolls_back_exactly_after_plastic_trial() -> None:
    problem = StatefulTwoBarTrussProblem()
    parent = problem.initial_state()
    parent_bytes = parent.canonical_bytes()
    failed = solve_stateful_two_bar_truss_load_step(
        problem,
        parent,
        target_load_factor=1.2,
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    assert failed.status == "blocked"
    assert failed.committed is False
    assert failed.accepted_state is parent
    assert failed.accepted_state.canonical_bytes() == parent_bytes
    assert failed.metrics["parent_state_unchanged_during_trial"] is True
    assert failed.metrics["material_state_changed"] is True
    assert failed.metrics["rollback_exact"] is True
    assert failed.trial_solution.metrics["terminal_reason"] == (
        "max_iterations_exceeded"
    )
    assert any(
        response.material_response.yielded
        for response in failed.final_assembly.element_responses
    )


def test_cyclic_force_path_commits_reversal_and_dissipation(
    benchmark_receipt: dict[str, Any],
) -> None:
    cyclic = benchmark_receipt["cyclic_path"]
    path = cyclic["path_result"]
    metrics = path["metrics"]
    final_material = path["final_state"]["material_states"][0]

    assert path["status"] == "ready"
    assert metrics["contract_pass"] is True
    assert metrics["requested_step_count"] == 17
    assert metrics["committed_step_count"] == 17
    assert metrics["rollback_step_count"] == 0
    assert metrics["material_state_changed_step_count"] == 3
    assert metrics["line_search_history_recorded"] is True
    assert metrics["line_search_history_entry_count"] > 0
    assert metrics["backtracking_used"] is False
    assert cyclic["plastic_flow_reversal_count"] >= 1
    assert cyclic["dissipation_nonnegative_monotonic"] is True
    assert final_material["dissipated_energy_density_mj_per_m3"] == pytest.approx(
        0.14250045676880574
    )


def test_benchmark_receipt_keeps_claims_and_errors_bounded(
    benchmark_receipt: dict[str, Any],
) -> None:
    result = benchmark_receipt
    claims = result["claims"]
    reference = result["analytic_symmetric_reduction"]
    solver = result["solver_summary"]

    assert result["schema_version"] == MATERIAL_GEOMETRIC_TRUSS_SCHEMA_VERSION
    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert result["quadratic_convergence"]["pass"] is True
    assert result["quadratic_convergence"]["quadratic_window_count"] >= 2
    assert result["quadratic_convergence"]["maximum_quadratic_ratio"] <= 0.1
    assert reference["maximum_vertical_displacement_abs_error_m"] <= 1.0e-10
    assert reference["maximum_horizontal_symmetry_abs_error_m"] <= 1.0e-12
    assert solver["maximum_residual_inf_norm_kn"] <= 1.0e-7
    assert solver["failed_step_rollback_exact"] is True
    assert solver["regularization_count"] == 0
    assert solver["fallback_count"] == 0

    assert claims["bounded_2d_two_bar_material_geometric_coupling"] is True
    assert claims["exact_current_chord_kinematics"] is True
    assert claims["algorithmic_material_and_geometric_tangent"] is True
    assert claims["same_parent_finite_difference_tangent"] is True
    assert claims["stateful_newton_commit_rollback"] is True
    assert claims["cyclic_plastic_dissipation"] is True
    assert claims["independent_symmetric_scalar_reduction"] is True
    assert claims["general_2d_3d_corotational_truss"] is False
    assert claims["frame_shell_material_geometric_coupling"] is False
    assert claims["distributed_plasticity"] is False
    assert claims["finite_strain_constitutive_model"] is False
    assert claims["arc_length_limit_point_continuation"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["external_code_to_code_validation"] is False
    assert claims["experimental_validation"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)


def test_receipt_and_state_hashes_are_deterministic(
    benchmark_receipt: dict[str, Any],
) -> None:
    repeated = material_geometric_two_bar_truss_benchmark()

    assert json.dumps(
        repeated,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == json.dumps(
        benchmark_receipt,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert (
        repeated["cyclic_path"]["path_result"]["final_state"]["state_hash"]
        == benchmark_receipt["cyclic_path"]["path_result"]["final_state"]["state_hash"]
    )


def test_invalid_state_path_and_geometry_fail_closed() -> None:
    problem = StatefulTwoBarTrussProblem()
    state = problem.initial_state()
    with pytest.raises(ValueError, match="state_hash"):
        StatefulTwoBarTrussAcceptedState(
            case_id=state.case_id,
            step_index=state.step_index,
            load_factor=state.load_factor,
            apex_displacements_m=state.apex_displacements_m,
            material_states=state.material_states,
            state_hash="sha256:" + "0" * 64,
        )
    with pytest.raises(ValueError, match="non-empty"):
        run_stateful_two_bar_truss_load_path(problem, ())
    with pytest.raises(ValueError, match="positive"):
        StatefulTwoBarTrussProblem(area_m2=0.0)
    with pytest.raises(ValueError, match="degenerate"):
        corotational_truss_element_response(
            element_id="collapsed",
            base_coordinate_m=(0.0, 0.0),
            initial_apex_coordinate_m=(1.0, 0.0),
            apex_displacement_m=(-1.0, 0.0),
            area_m2=0.001,
            material=problem.material,
            committed_state=problem.material.initial_state(),
        )
