from __future__ import annotations

import json

import pytest

from structural_analysis.benchmark.stateful_corotational_composite_frame_cyclic import (
    COMPOSITE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2,
    COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS,
    COMPOSITE_FRAME_ELASTIC_AXIAL_RIGIDITY_KN,
    COMPOSITE_FRAME_ELASTIC_CENTROID_Y_M,
    COMPOSITE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2,
    COMPOSITE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION,
    COMPOSITE_FRAME_INITIAL_STEEL_FLEXURAL_RIGIDITY_FRACTION,
    COMPOSITE_FRAME_STEEL_FLEXURAL_RIGIDITY_KN_M2,
    STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_composite_frame_cyclic_benchmark,
    make_stateful_corotational_composite_frame_cyclic_problem,
)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_composite_frame_cyclic_benchmark()


def test_problem_is_mixed_steel_girder_concrete_slab_frame() -> None:
    problem = make_stateful_corotational_composite_frame_cyclic_problem()

    assert problem.node_coordinates_m == ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
    assert problem.fixed_global_dofs == (0, 1, 2)
    assert problem.free_global_dofs == (3, 4, 5, 6, 7, 8)
    assert problem.reference_external_loads == ((7, -100.0),)
    assert len(problem.members) == 2
    assert len(COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS) == 60
    for member in problem.members:
        kinds = [fiber.material_kind for fiber in member.element.section.fibers]
        assert kinds.count("steel") == 8
        assert kinds.count("concrete") == 8

    assert COMPOSITE_FRAME_ELASTIC_AXIAL_RIGIDITY_KN == pytest.approx(3_672_000.0)
    assert COMPOSITE_FRAME_ELASTIC_CENTROID_Y_M == pytest.approx(0.12352941176470587)
    assert COMPOSITE_FRAME_STEEL_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(
        47_554.637543252575
    )
    assert COMPOSITE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(
        18_702.171280276816
    )
    assert COMPOSITE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(
        66_256.8088235294
    )
    assert 0.70 < COMPOSITE_FRAME_INITIAL_STEEL_FLEXURAL_RIGIDITY_FRACTION < 0.75
    assert 0.25 < COMPOSITE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION < 0.30


def test_cyclic_composite_frame_commits_and_replays_exactly(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["contract_pass"] is True
    assert result["status"] == "partial"
    assert result["path_status"] == "ready"
    assert result["requested_step_count"] == 60
    assert result["committed_step_count"] == 60
    assert result["path_ancestry_exact"] is True
    assert result["deterministic_replay_exact"] is True
    assert result["elastic_prefix"] == {
        "step_count": 5,
        "no_material_state_evolution": True,
    }
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0
    assert result["line_search_history_entry_count"] > 0
    assert (
        result["maximum_residual_inf_norm_kn"]
        <= result["maximum_residual_inf_norm_tolerance_kn"]
    )


def test_both_constituents_evolve_on_the_same_structure_path(
    benchmark_receipt: dict,
) -> None:
    history = benchmark_receipt["material_history"]
    final = history["final_material_state"]

    assert history["irreversible"] is True
    assert history["tensile_damage_evolution_step_indices"] == [
        *range(6, 21),
        60,
    ]
    assert history["compressive_damage_evolution_step_indices"] == [38, 39, 40]
    assert history["steel_plastic_evolution_step_indices"] == [19, 20]
    assert history["simultaneous_steel_plastic_concrete_damage_step_indices"] == [
        19,
        20,
    ]
    assert final["concrete_fiber_state_count"] == 48
    assert final["steel_fiber_state_count"] == 48
    assert final["tensile_damaged_concrete_state_count"] == 37
    assert final["compressive_damaged_concrete_state_count"] == 6
    assert final["plastified_steel_state_count"] == 2
    assert final["maximum_tensile_damage"] > 0.0
    assert final["maximum_compressive_damage"] > 0.0
    assert final["maximum_steel_accumulated_plastic_strain"] > 0.0
    assert final["maximum_steel_dissipated_energy_density_mj_per_m3"] > 0.0
    assert final["maximum_concrete_dissipated_energy_density_mj_per_m3"] > 0.0


def test_steel_and_concrete_dissipation_are_separately_monotonic(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    dissipation = result["dissipation"]
    steps = result["steps"]

    assert dissipation["steel_nonnegative_monotonic"] is True
    assert dissipation["concrete_nonnegative_monotonic"] is True
    assert dissipation["total_nonnegative_monotonic"] is True
    assert dissipation["reversal_growth"] is True
    assert dissipation["final_steel_mj"] > 0.0
    assert dissipation["final_concrete_mj"] > 0.0
    assert dissipation["final_total_mj"] == pytest.approx(
        dissipation["final_steel_mj"] + dissipation["final_concrete_mj"]
    )
    assert dissipation["maximum_component_sum_error_mj"] <= 1.0e-15
    for name in ("steel_mj", "concrete_mj", "total_mj"):
        values = [float(row["dissipated_energy"][name]) for row in steps]
        assert values == sorted(values)
        assert values[-1] == pytest.approx(dissipation[f"final_{name}"])
    assert (
        steps[39]["dissipated_energy"]["total_mj"]
        > steps[19]["dissipated_energy"]["total_mj"]
    )


def test_mixed_and_reverse_damage_same_parent_tangents_are_consistent(
    benchmark_receipt: dict,
) -> None:
    mixed = benchmark_receipt["same_parent_simultaneous_mixed_tangent"]
    reverse = benchmark_receipt[
        "same_parent_compression_damage_after_plastic_history_tangent"
    ]
    quadratic = benchmark_receipt[
        "first_simultaneous_mixed_newton_quadratic_convergence"
    ]

    for tangent in (mixed, reverse):
        assert tangent["pass"] is True
        assert tangent["same_committed_parent_checkpoint"] is True
        assert tangent["relative_inf_error"] <= tangent["relative_tolerance"]
        assert tangent["tangent_symmetry_error_kn_per_m"] <= 1.0e-9
        assert tangent["tangent_decomposition_error_kn_per_m"] <= 1.0e-8
        assert tangent["material_and_geometric_terms_active"] is True
        assert tangent["damaged_member_count"] > 0
    assert mixed["yielded_member_count"] > 0
    assert quadratic["pass"] is True
    assert quadratic["minimum_observed_order"] >= 1.8
    assert quadratic["relative_residual_roundoff_floor"] == 1.0e-7
    assert quadratic["excluded_terminal_roundoff_history_count"] == 1


def test_forced_mixed_trial_rolls_back_exactly(benchmark_receipt: dict) -> None:
    rollback = benchmark_receipt["forced_failure_rollback"]

    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["trial_yielded_member_count"] > 0
    assert rollback["trial_damaged_member_count"] > 0
    assert (
        rollback["accepted_checkpoint_hash_after"] == rollback["parent_checkpoint_hash"]
    )
    assert rollback["exact"] is True


def test_receipt_preserves_composite_scientific_claim_boundary(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert claims["bounded_two_member_corotational_fiber_frame"] is True
    assert claims["perfect_bond_steel_girder_concrete_slab_section"] is True
    assert claims["simultaneous_steel_plasticity_and_concrete_damage"] is True
    assert claims["cyclic_constituent_dissipation"] is True
    assert claims["same_parent_material_plus_geometric_tangent"] is True
    assert claims["consistent_newton_commit_and_exact_rollback"] is True
    assert claims["general_composite_section_breadth"] is False
    assert claims["partial_interaction_or_connector_slip"] is False
    assert claims["composite_shear_transfer_validation"] is False
    assert claims["local_buckling_or_fracture"] is False
    assert claims["mesh_objectivity_or_fracture_energy_regularization"] is False
    assert claims["multiaxial_material_validity"] is False
    assert claims["external_cyclic_member_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)
