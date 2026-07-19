from __future__ import annotations

from dataclasses import replace
import json
from typing import Any

import numpy as np
import pytest

from structural_analysis.benchmark.material_geometric_truss import (
    StatefulTwoBarTrussProblem,
)
from structural_analysis.benchmark.material_geometric_truss_arc_length import (
    MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
    MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION,
    MaterialGeometricArcLengthError,
    MaterialGeometricArcLengthStepProblem,
    analytic_monotonic_limit_point,
    analytic_monotonic_symmetric_load_factor,
    build_material_geometric_arc_length_benchmark,
    build_material_geometric_arc_length_path_contract_hash,
    create_dense_material_geometric_state_tangent_solver,
    finite_difference_material_geometric_arc_length_linearization_check,
    stateful_material_geometric_arc_length_continuation,
    validate_material_geometric_arc_length_checkpoint,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthConfig,
)


@pytest.fixture(scope="module")
def problem() -> StatefulTwoBarTrussProblem:
    return StatefulTwoBarTrussProblem()


@pytest.fixture(scope="module")
def path_result(problem: StatefulTwoBarTrussProblem):
    return stateful_material_geometric_arc_length_continuation(problem)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict[str, Any]:
    return build_material_geometric_arc_length_benchmark()


def test_local_arc_problem_linearization_uses_one_immutable_parent(
    problem: StatefulTwoBarTrussProblem,
) -> None:
    parent = problem.initial_state()
    parent_bytes = parent.canonical_bytes()
    step_problem = MaterialGeometricArcLengthStepProblem(
        problem,
        parent,
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG.initial_arc_length_m,
    )
    check = finite_difference_material_geometric_arc_length_linearization_check(
        step_problem
    )

    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["displacement_jacobian_relative_inf_error"] <= 1.0e-8
    assert check["negative_load_derivative_relative_inf_error"] <= 1.0e-8
    assert parent.canonical_bytes() == parent_bytes
    assert step_problem.actual_displacements_m((0.0, -0.01)) == pytest.approx(
        [0.0, -0.01]
    )
    assert step_problem.actual_load_factor(0.5) == pytest.approx(0.5)


def test_dense_state_tangent_solver_passes_explicit_residual_gate(
    problem: StatefulTwoBarTrussProblem,
) -> None:
    step_problem = MaterialGeometricArcLengthStepProblem(
        problem,
        problem.initial_state(),
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG.initial_arc_length_m,
    )
    solver = create_dense_material_geometric_state_tangent_solver(problem)
    state = np.asarray([0.0, -0.005])
    right_hand_side = problem.reference_load_kn()
    solve = solver.solve_at_state(
        step_problem,
        state,
        right_hand_side,
        load_factor=0.8,
        solve_id="test-dense-state-solve",
    )
    solution = np.asarray(solve.solution_free)
    explicit = step_problem.consistent_state_tangent_action_kn_per_m(
        state,
        0.8,
        solution,
    )

    assert solve.contract_pass is True
    assert solve.terminal_reason == "converged"
    assert solve.profile == solver.profile
    assert solve.contract_hash == solver.contract_hash
    assert explicit == pytest.approx(right_hand_side, abs=1.0e-10)
    assert solve.receipt["matrix_storage"] == "numpy_dense_2x2"
    assert solve.receipt["explicit_residual_inf_norm_kn"] <= 1.0e-10


def test_stateful_arc_length_crosses_limit_point_without_fallback(
    path_result,
) -> None:
    result = path_result
    metrics = result.metrics

    assert result.status == "ready"
    assert result.terminal_reason == "target_monitor_displacement_reached"
    assert metrics["contract_pass"] is True
    assert metrics["accepted_step_count"] == 12
    assert metrics["rejected_step_count"] == 1
    assert metrics["failed_step_reduction_count"] == 1
    assert metrics["maximum_load_step_index"] == 3
    assert metrics["maximum_load_factor"] == pytest.approx(0.9523764071492837)
    assert metrics["final_load_factor"] == pytest.approx(0.9047160186128145)
    assert metrics["final_monitor_displacement_m"] == pytest.approx(
        -0.050492519708786654
    )
    assert metrics["descending_load_branch_observed"] is True
    assert metrics["vertical_tangent_sign_change_observed"] is True
    assert metrics["material_and_geometric_tangent_terms_active"] is True
    assert metrics["material_state_changed_step_count"] == 11
    assert metrics["tangent_solve_count"] == 117
    assert metrics["dense_2x2_state_tangent_solver"] is True
    assert metrics["maximum_accepted_residual_inf_norm_kn"] <= 1.0e-8
    assert metrics["maximum_accepted_constraint_residual_m2"] <= 1.0e-12
    assert metrics["fallback_count"] == 0
    assert metrics["regularization_count"] == 0
    assert result.to_dict()["claims"]["dense_2x2_state_tangent_solves"] is True
    assert result.final_state.material_states[
        0
    ].dissipated_energy_density_mj_per_m3 == pytest.approx(1.7477601986809785)


def test_rejected_arc_attempt_retains_exact_material_and_structure_bytes(
    path_result,
) -> None:
    rejected = [row for row in path_result.attempts if not row.committed]

    assert len(rejected) == 1
    attempt = rejected[0]
    assert attempt.outcome == "rolled_back"
    assert attempt.accepted_state is attempt.parent_state
    assert attempt.accepted_state.canonical_bytes() == (
        attempt.parent_state.canonical_bytes()
    )
    assert attempt.rollback_exact is True
    assert attempt.arc_length_m == pytest.approx(0.008)
    assert attempt.next_arc_length_m == pytest.approx(0.004)
    assert attempt.checkpoint.current_arc_length_m == pytest.approx(0.004)
    assert attempt.vector_result.metrics["fallback_count"] == 0
    assert attempt.vector_result.metrics["regularization_count"] == 0
    assert (
        attempt.to_dict()["vector_result"]["metrics"][
            "maximum_accepted_constraint_residual_m2"
        ]
        is None
    )


def test_restart_from_rejected_boundary_is_bit_identical(
    problem: StatefulTwoBarTrussProblem,
    path_result,
) -> None:
    boundary = next(
        row
        for row in path_result.checkpoints
        if row.last_attempt_outcome == "rolled_back"
    )
    restarted = stateful_material_geometric_arc_length_continuation(
        problem,
        checkpoint=boundary,
    )

    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.initial_checkpoint is boundary
    assert restarted.final_checkpoint == path_result.final_checkpoint
    assert restarted.final_state.state_hash == path_result.final_state.state_hash
    assert restarted.final_state.canonical_bytes() == (
        path_result.final_state.canonical_bytes()
    )


def test_closed_form_monotonic_curve_brackets_limit_point(
    problem: StatefulTwoBarTrussProblem,
    benchmark_receipt: dict[str, Any],
) -> None:
    reference = benchmark_receipt["analytic_monotonic_reference"]
    limit = analytic_monotonic_limit_point(problem)

    assert analytic_monotonic_symmetric_load_factor(problem, 0.0) == 0.0
    assert limit["vertical_displacement_m"] == pytest.approx(-0.015179934566880651)
    assert limit["load_factor"] == pytest.approx(0.952395478327033)
    assert reference["gate_passed"] is True
    assert reference["maximum_load_factor_abs_error"] <= 1.0e-9
    assert reference["sampled_maximum_load_factor_shortfall"] <= 5.0e-5
    bracket = reference["limit_point_bracket"]
    assert (
        bracket["lower_vertical_displacement_m"]
        >= (bracket["analytic_vertical_displacement_m"])
    )
    assert (
        bracket["upper_vertical_displacement_m"]
        <= (bracket["analytic_vertical_displacement_m"])
    )


def test_benchmark_replay_restart_and_claims_stay_bounded(
    benchmark_receipt: dict[str, Any],
) -> None:
    result = benchmark_receipt
    verification = result["verification"]
    claims = result["claims"]

    assert result["schema_version"] == MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION
    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert verification["deterministic_replay_exact"] is True
    assert verification["checkpoint_restart_exact"] is True
    assert verification["restart_boundary_outcome"] == "rolled_back"
    assert verification["adaptive_failed_step_rollback_gate_passed"] is True
    assert verification["descending_load_branch_observed"] is True
    assert verification["vertical_tangent_sign_change_observed"] is True
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0

    assert claims["bounded_stateful_material_geometric_arc_length"] is True
    assert claims["limit_point_and_descending_branch"] is True
    assert claims["adaptive_failed_step_rollback"] is True
    assert claims["deterministic_checkpoint_restart"] is True
    assert claims["closed_form_monotonic_curve_agreement"] is True
    assert claims["general_2d_3d_truss_frame_shell"] is False
    assert claims["finite_strain_constitutive_behavior"] is False
    assert claims["durable_serialized_checkpoint"] is False
    assert claims["external_code_to_code_validation"] is False
    assert claims["experimental_validation"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)


def test_checkpoint_and_path_contracts_fail_closed(
    problem: StatefulTwoBarTrussProblem,
    path_result,
) -> None:
    boundary = path_result.checkpoints[2]
    with pytest.raises(MaterialGeometricArcLengthError, match="checkpoint_hash"):
        replace(
            boundary,
            current_arc_length_m=boundary.current_arc_length_m * 0.5,
        )
    with pytest.raises(MaterialGeometricArcLengthError, match="source problem"):
        validate_material_geometric_arc_length_checkpoint(
            boundary,
            StatefulTwoBarTrussProblem(area_m2=0.002),
            MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
        )
    invalid_config = replace(
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
        target_monitor_dof_index=0,
    )
    with pytest.raises(MaterialGeometricArcLengthError, match="vertical"):
        build_material_geometric_arc_length_path_contract_hash(
            problem,
            invalid_config,
        )
    with pytest.raises(MaterialGeometricArcLengthError, match="already reached"):
        stateful_material_geometric_arc_length_continuation(
            problem,
            config=replace(
                MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
                target_monitor_displacement_m=-0.001,
            ),
            initial_state=path_result.final_state,
        )
    with pytest.raises(MaterialGeometricArcLengthError, match="analytic branch"):
        analytic_monotonic_symmetric_load_factor(problem, 0.001)


def test_default_config_is_the_bounded_two_dof_contract() -> None:
    config: VectorArcLengthConfig = MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG

    assert config.target_monitor_dof_index == 1
    assert config.target_monitor_displacement_m == -0.05
    assert config.target_direction == -1
    assert config.displacement_metric_weights == (1.0, 1.0)
    assert config.initial_arc_length_m == 0.008
    assert config.failed_step_reduction == 0.5
    assert config.maximum_corrector_iterations == 5
