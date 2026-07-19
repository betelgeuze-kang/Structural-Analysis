from __future__ import annotations

from dataclasses import replace
import json
from typing import Any

import numpy as np
import pytest

from structural_analysis.benchmark.material_geometric_fgmres_arc_length import (
    MATERIAL_GEOMETRIC_FGMRES_ARC_LENGTH_SCHEMA_VERSION,
    MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE,
    build_material_geometric_cpu_fgmres_arc_length_benchmark,
    create_material_geometric_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.benchmark.material_geometric_truss import (
    StatefulTwoBarTrussProblem,
)
from structural_analysis.benchmark.material_geometric_truss_arc_length import (
    MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
    MATERIAL_GEOMETRIC_ARC_LENGTH_EXTERNAL_SOLVER_PROFILE,
    MaterialGeometricArcLengthError,
    MaterialGeometricArcLengthStepProblem,
    build_material_geometric_arc_length_path_contract_hash,
    stateful_material_geometric_arc_length_continuation,
    validate_material_geometric_arc_length_checkpoint,
)
from structural_analysis.engine_v2.cpu_fgmres_tangent import (
    CPU_FGMRES_TANGENT_SOLVE_PROFILE,
)


@pytest.fixture(scope="module")
def problem() -> StatefulTwoBarTrussProblem:
    return StatefulTwoBarTrussProblem()


@pytest.fixture(scope="module")
def receipt() -> dict[str, Any]:
    return build_material_geometric_cpu_fgmres_arc_length_benchmark()


def test_dedicated_engine_v2_tangent_solve_matches_direct_reference(
    problem: StatefulTwoBarTrussProblem,
) -> None:
    solver = create_material_geometric_cpu_fgmres_state_tangent_solver(problem)
    step_problem = MaterialGeometricArcLengthStepProblem(
        problem,
        problem.initial_state(),
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG.initial_arc_length_m,
    )
    state = np.asarray([0.0, -0.005], dtype=float)
    right_hand_side = problem.reference_load_kn()
    solve = solver.solve_at_state(
        step_problem,
        state,
        right_hand_side,
        load_factor=0.8,
        solve_id="direct-reference-test",
    )
    identity = np.eye(2)
    tangent = np.column_stack(
        [
            step_problem.consistent_state_tangent_action_kn_per_m(
                state,
                0.8,
                identity[:, column],
            )
            for column in range(2)
        ]
    )
    direct = np.linalg.solve(tangent, right_hand_side)
    manifest = solve.receipt["engine_v2_tangent_solve"]

    assert solve.contract_pass is True
    assert solve.profile == MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE
    assert np.asarray(solve.solution_free) == pytest.approx(direct, abs=1.0e-15)
    assert tangent @ np.asarray(solve.solution_free) == pytest.approx(
        right_hand_side,
        abs=1.0e-12,
    )
    assert solve.receipt["matrix_binding"] == (
        "exact_two_equation_reduced_csr_si_converted"
    )
    assert solve.receipt["physical_to_engine_force_scale_n_per_kn"] == 1_000.0
    assert manifest["profile"] == CPU_FGMRES_TANGENT_SOLVE_PROFILE
    assert manifest["solver"]["free_count"] == 2
    assert manifest["solver"]["fallback_count"] == 0
    assert manifest["solver"]["regularization_count"] == 0
    assert solver.binding["plan"].array("csr_column_indices").size == 20


def test_external_solver_identity_changes_the_path_contract(
    problem: StatefulTwoBarTrussProblem,
) -> None:
    solver = create_material_geometric_cpu_fgmres_state_tangent_solver(problem)
    dense_hash = build_material_geometric_arc_length_path_contract_hash(
        problem,
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
    )
    fgmres_hash = build_material_geometric_arc_length_path_contract_hash(
        problem,
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
        state_tangent_solver=solver,
    )

    assert dense_hash == (
        "sha256:bdd9a8dd563d348c6ffc30ab34e21cc94d79251415f6e13d959246e10567fc77"
    )
    assert fgmres_hash.startswith("sha256:")
    assert fgmres_hash != dense_hash


def test_external_solver_checkpoint_rejects_a_dense_resume_contract(
    problem: StatefulTwoBarTrussProblem,
) -> None:
    solver = create_material_geometric_cpu_fgmres_state_tangent_solver(problem)
    short_config = replace(
        MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
        target_monitor_displacement_m=-0.003,
        initial_arc_length_m=0.004,
        maximum_arc_length_m=0.004,
        maximum_attempt_count=8,
    )
    result = stateful_material_geometric_arc_length_continuation(
        problem,
        config=short_config,
        state_tangent_solver=solver,
    )
    checkpoint = result.final_checkpoint

    assert (
        validate_material_geometric_arc_length_checkpoint(
            checkpoint,
            problem,
            short_config,
            state_tangent_solver=solver,
        )
        is checkpoint
    )
    with pytest.raises(MaterialGeometricArcLengthError, match="path contract"):
        validate_material_geometric_arc_length_checkpoint(
            checkpoint,
            problem,
            short_config,
        )


def test_complete_stateful_path_uses_cpu_fgmres_for_every_tangent_solve(
    receipt: dict[str, Any],
) -> None:
    verification = receipt["verification"]
    solver_result = receipt["solver_result"]

    assert receipt["schema_version"] == (
        MATERIAL_GEOMETRIC_FGMRES_ARC_LENGTH_SCHEMA_VERSION
    )
    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["reduced_equation_count"] == 2
    assert receipt["reduced_csr_nnz"] == 4
    assert verification["engine_v2_cpu_fgmres_every_tangent_solve"] is True
    assert verification["execution_plan_equation_scaling_binding_passed"] is True
    assert verification["tangent_solve_count"] == 117
    assert verification["maximum_tangent_solve_iteration_count"] <= 2
    assert (
        verification["maximum_tangent_solve_explicit_residual_inf_norm_kn"] <= 1.0e-12
    )
    assert solver_result["profile"] == (
        MATERIAL_GEOMETRIC_ARC_LENGTH_EXTERNAL_SOLVER_PROFILE
    )
    assert solver_result["metrics"]["tangent_solver_profile"] == (
        MATERIAL_GEOMETRIC_FGMRES_STATE_TANGENT_SOLVER_PROFILE
    )
    assert solver_result["metrics"]["accepted_step_count"] == 12
    assert solver_result["metrics"]["rejected_step_count"] == 1
    assert solver_result["metrics"]["fallback_count"] == 0
    assert solver_result["metrics"]["regularization_count"] == 0
    assert solver_result["claims"]["dense_2x2_state_tangent_solves"] is False


def test_replay_restart_dense_reference_and_claim_boundaries(
    receipt: dict[str, Any],
) -> None:
    verification = receipt["verification"]
    claims = receipt["claims"]

    assert verification["deterministic_replay_exact"] is True
    assert verification["checkpoint_restart_exact"] is True
    assert verification["restart_boundary_outcome"] == "rolled_back"
    assert verification["dense_reference_path_gate_passed"] is True
    assert verification["same_dense_reference_accepted_state_count"] is True
    assert (
        verification["maximum_dense_reference_displacement_absolute_error_m"] <= 1.0e-15
    )
    assert verification["maximum_dense_reference_load_factor_absolute_error"] <= 1.0e-14
    assert verification["maximum_dense_reference_material_state_absolute_error"] == 0.0
    assert claims["bounded_material_geometric_arc_length_cpu_fgmres"] is True
    assert claims["engine_v2_cpu_fgmres_every_tangent_solve"] is True
    assert claims["dense_reference_path_equivalence"] is True
    assert claims["general_2d_3d_truss_frame_shell"] is False
    assert claims["production_scale_sparse_preconditioner"] is False
    assert claims["finite_strain_constitutive_behavior"] is False
    assert claims["production_rocm_hip_nonlinear_parity"] is False
    assert claims["durable_serialized_checkpoint"] is False
    assert claims["external_validation"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert receipt["blockers_remaining"]
    json.dumps(receipt, allow_nan=False, sort_keys=True)


def test_cached_receipt_is_returned_as_an_isolated_copy(
    receipt: dict[str, Any],
) -> None:
    receipt["verification"]["tangent_solve_count"] = -1
    repeated = build_material_geometric_cpu_fgmres_arc_length_benchmark()

    assert repeated["verification"]["tangent_solve_count"] == 117
