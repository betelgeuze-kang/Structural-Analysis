from __future__ import annotations

import json

import pytest

from structural_analysis.benchmark.stateful_corotational_concrete_frame_cyclic import (
    CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2,
    CONCRETE_FRAME_CYCLIC_LOAD_FACTORS,
    CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2,
    CONCRETE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION,
    CONCRETE_FRAME_REINFORCEMENT_FLEXURAL_RIGIDITY_KN_M2,
    STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_concrete_frame_cyclic_benchmark,
    make_stateful_corotational_concrete_frame_cyclic_problem,
)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_concrete_frame_cyclic_benchmark()


def test_problem_is_concrete_dominated_two_member_corotational_frame() -> None:
    problem = make_stateful_corotational_concrete_frame_cyclic_problem()

    assert problem.node_coordinates_m == ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
    assert problem.fixed_global_dofs == (0, 1, 2)
    assert problem.free_global_dofs == (3, 4, 5, 6, 7, 8)
    assert len(problem.members) == 2
    assert problem.reference_external_loads == ((7, -100.0),)
    assert len(CONCRETE_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(31_500.0)
    assert CONCRETE_FRAME_REINFORCEMENT_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(
        10_240.0
    )
    assert CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(41_740.0)
    assert CONCRETE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION >= 0.75


def test_cyclic_concrete_frame_path_commits_and_replays_exactly(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["contract_pass"] is True
    assert result["status"] == "partial"
    assert result["path_status"] == "ready"
    assert result["requested_step_count"] == 30
    assert result["committed_step_count"] == 30
    assert result["path_ancestry_exact"] is True
    assert result["deterministic_replay_exact"] is True
    assert result["elastic_reference"]["pass"] is True
    assert result["elastic_reference"]["relative_error"] <= 1.0e-6
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0
    assert result["line_search_history_entry_count"] > 0
    assert result["maximum_residual_inf_norm_kn"] <= 1.0e-8


def test_both_concrete_damage_branches_evolve_across_reversal(
    benchmark_receipt: dict,
) -> None:
    damage = benchmark_receipt["damage_history"]
    final = damage["final_material_state"]

    assert damage["damage_irreversible"] is True
    assert damage["first_damage_step_index"] == 2
    assert damage["first_compressive_damage_step_index"] == 10
    assert damage["positive_loading_compressive_damage_step_indices"] == [10]
    assert damage["reverse_loading_compressive_damage_step_indices"] == [20]
    assert final["concrete_fiber_state_count"] == 48
    assert final["steel_fiber_state_count"] == 12
    assert final["tensile_damaged_concrete_state_count"] == 48
    assert final["compressive_damaged_concrete_state_count"] == 2
    assert final["maximum_tensile_damage"] > 0.0
    assert final["maximum_compressive_damage"] > 0.0
    assert final["maximum_concrete_dissipated_energy_density_mj_per_m3"] > 0.0
    assert final["maximum_steel_accumulated_plastic_strain"] == 0.0
    assert final["maximum_steel_dissipated_energy_density_mj_per_m3"] == 0.0


def test_damage_dissipation_is_nonnegative_and_grows_after_reversal(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    steps = result["steps"]
    energies = [float(row["dissipated_energy_mj"]) for row in steps]

    assert result["dissipation_nonnegative_monotonic"] is True
    assert result["reversal_dissipation_growth"] is True
    assert energies == sorted(energies)
    assert energies[19] > energies[9] > 0.0
    assert energies[-1] == pytest.approx(result["final_dissipated_energy_mj"])
    assert [row["step_index"] for row in steps] == list(range(1, 31))
    assert [row["target_load_factor"] for row in steps] == list(
        CONCRETE_FRAME_CYCLIC_LOAD_FACTORS
    )
    assert steps[9]["compressive_damage_increment_state_count"] == 1
    assert steps[19]["compressive_damage_increment_state_count"] == 1
    assert all(row["yielded_member_count"] == 0 for row in steps)
    assert any(row["line_search_used"] for row in steps)
    assert all(row["fallback_used"] is False for row in steps)
    assert all(row["regularization_used"] is False for row in steps)


def test_two_branch_same_parent_tangent_and_first_damage_newton_are_consistent(
    benchmark_receipt: dict,
) -> None:
    tangent = benchmark_receipt["same_parent_two_branch_consistent_tangent"]
    quadratic = benchmark_receipt["first_damage_quadratic_convergence"]

    assert tangent["pass"] is True
    assert tangent["same_committed_parent_checkpoint"] is True
    assert tangent["relative_inf_error"] <= tangent["relative_tolerance"]
    assert tangent["tangent_symmetry_error_kn_per_m"] <= 1.0e-9
    assert tangent["tangent_decomposition_error_kn_per_m"] <= 1.0e-8
    assert tangent["material_and_geometric_terms_active"] is True
    assert tangent["damaged_member_count"] == 2
    assert tangent["yielded_member_count"] == 0
    assert quadratic["pass"] is True
    assert quadratic["minimum_observed_order"] >= 1.8


def test_forced_damaged_trial_rolls_back_exactly(benchmark_receipt: dict) -> None:
    rollback = benchmark_receipt["forced_failure_rollback"]

    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["trial_damaged_member_count"] == 2
    assert rollback["trial_yielded_member_count"] == 0
    assert (
        rollback["accepted_checkpoint_hash_after"] == rollback["parent_checkpoint_hash"]
    )
    assert rollback["exact"] is True


def test_receipt_preserves_concrete_scientific_claim_boundary(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert claims["bounded_two_member_corotational_fiber_frame"] is True
    assert claims["asymmetric_tension_compression_concrete_damage"] is True
    assert claims["cyclic_concrete_damage_and_nonnegative_dissipation"] is True
    assert claims["same_parent_material_plus_geometric_tangent"] is True
    assert claims["consistent_newton_commit_and_exact_rollback"] is True
    assert claims["analytic_elastic_prefix"] is True
    assert claims["concrete_dominated_initial_flexural_rigidity"] is True
    assert claims["pure_concrete_section"] is False
    assert claims["mesh_objectivity"] is False
    assert claims["crack_band_or_fracture_energy_regularization"] is False
    assert claims["multiaxial_concrete_validity"] is False
    assert claims["external_cyclic_member_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)
