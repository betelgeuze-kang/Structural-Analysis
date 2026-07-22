from __future__ import annotations

import json

import pytest

from structural_analysis.assembly import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.benchmark import (
    STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_SCHEMA_VERSION,
    STEEL_FRAME_CYCLIC_LOAD_FACTORS,
    STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2,
    STEEL_HARDENING_VARIANTS,
    build_stateful_corotational_steel_frame_cyclic_benchmark,
    finite_difference_stateful_corotational_fiber_frame2d_tangent_check,
    make_stateful_corotational_steel_frame_cyclic_problem,
)


ISOTROPIC_ID = "steel_bilinear_isotropic_hardening_frame"
KINEMATIC_ID = "steel_bilinear_kinematic_hardening_frame"
COMBINED_ID = "steel_bilinear_combined_hardening_frame"


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_steel_frame_cyclic_benchmark()


def _variants(receipt: dict) -> dict[str, dict]:
    return {row["variant"]["variant_id"]: row for row in receipt["hardening_variants"]}


def test_problem_is_two_member_steel_dominated_corotational_frame() -> None:
    problem = make_stateful_corotational_steel_frame_cyclic_problem(COMBINED_ID)

    assert problem.node_coordinates_m == ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
    assert problem.fixed_global_dofs == (0, 1, 2)
    assert problem.free_global_dofs == (3, 4, 5, 6, 7, 8)
    assert len(problem.members) == 2
    assert problem.reference_external_loads == ((7, -50.0),)
    assert STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(10_241.0)
    assert len(STEEL_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert tuple(row.variant_id for row in STEEL_HARDENING_VARIANTS) == (
        ISOTROPIC_ID,
        KINEMATIC_ID,
        COMBINED_ID,
    )


def test_all_three_hardening_variants_complete_the_cyclic_path(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    variants = _variants(result)

    assert result["contract_pass"] is True
    assert result["hardening_variant_count"] == 3
    assert set(variants) == {ISOTROPIC_ID, KINEMATIC_ID, COMBINED_ID}
    for row in variants.values():
        assert row["contract_pass"] is True
        assert row["path_status"] == "ready"
        assert row["requested_step_count"] == 30
        assert row["committed_step_count"] == 30
        assert row["path_ancestry_exact"] is True
        assert row["deterministic_replay_exact"] is True
        assert row["elastic_reference"]["pass"] is True
        assert row["elastic_reference"]["relative_error"] <= 1.0e-6
        assert row["damaged_step_count"] == 0
        assert row["fallback_count"] == 0
        assert row["regularization_count"] == 0
        assert row["line_search_history_entry_count"] > 0
        assert row["maximum_residual_inf_norm_kn"] <= 1.0e-8


def test_reverse_yield_and_energy_distinguish_hardening_branches(
    benchmark_receipt: dict,
) -> None:
    variants = _variants(benchmark_receipt)
    isotropic = variants[ISOTROPIC_ID]
    kinematic = variants[KINEMATIC_ID]
    combined = variants[COMBINED_ID]
    separation = benchmark_receipt["hardening_branch_separation"]

    assert separation["pass"] is True
    assert (
        separation["kinematic_energy_greater_than_combined_greater_than_isotropic"]
        is True
    )
    assert (
        separation["kinematic_component_reverse_yield_precedes_pure_isotropic"] is True
    )
    assert separation["elastic_variant_tip_displacement_spread_m"] <= 1.0e-13
    assert (
        kinematic["final_dissipated_energy_mj"]
        > combined["final_dissipated_energy_mj"]
        > isotropic["final_dissipated_energy_mj"]
        > 0.0
    )
    assert kinematic["first_reverse_yield_step_index"] == 19
    assert combined["first_reverse_yield_step_index"] == 19
    assert isotropic["first_reverse_yield_step_index"] == 20
    for row in variants.values():
        assert row["dissipation_nonnegative_monotonic"] is True
        assert row["material_state_extrema"]["maximum_accumulated_plastic_strain"] > 0.0
        assert row["material_state_extrema"]["maximum_concrete_damage"] == 0.0
        assert (
            row["material_state_extrema"][
                "maximum_concrete_dissipated_energy_density_mj_per_m3"
            ]
            == 0.0
        )


def test_yielded_same_parent_material_geometric_tangents_are_consistent(
    benchmark_receipt: dict,
) -> None:
    for row in benchmark_receipt["hardening_variants"]:
        tangent = row["same_parent_consistent_tangent"]
        quadratic = row["first_yield_quadratic_convergence"]

        assert tangent["pass"] is True
        assert tangent["same_committed_parent_checkpoint"] is True
        assert tangent["relative_inf_error"] <= tangent["relative_tolerance"]
        assert tangent["tangent_symmetry_error_kn_per_m"] <= 1.0e-9
        assert tangent["tangent_decomposition_error_kn_per_m"] <= 1.0e-8
        assert tangent["material_and_geometric_terms_active"] is True
        assert tangent["yielded_member_count"] > 0
        assert tangent["damaged_member_count"] == 0
        assert quadratic["pass"] is True
        assert quadratic["minimum_observed_order"] >= 1.8


def test_step_receipts_bind_residuals_line_search_and_energy(
    benchmark_receipt: dict,
) -> None:
    for variant in benchmark_receipt["hardening_variants"]:
        steps = variant["steps"]
        energies = [float(row["dissipated_energy_mj"]) for row in steps]

        assert [row["step_index"] for row in steps] == list(range(1, 31))
        assert [row["target_load_factor"] for row in steps] == list(
            STEEL_FRAME_CYCLIC_LOAD_FACTORS
        )
        assert energies == sorted(energies)
        assert energies[-1] == pytest.approx(variant["final_dissipated_energy_mj"])
        assert any(row["yielded_member_count"] > 0 for row in steps)
        assert any(row["line_search_used"] for row in steps)
        assert all(row["damaged_member_count"] == 0 for row in steps)
        assert all(row["fallback_used"] is False for row in steps)
        assert all(row["regularization_used"] is False for row in steps)


def test_forced_plastic_trial_rolls_back_exactly(
    benchmark_receipt: dict,
) -> None:
    rollback = benchmark_receipt["forced_failure_rollback"]

    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["trial_yielded_member_count"] > 0
    assert rollback["trial_damaged_member_count"] == 0
    assert (
        rollback["accepted_checkpoint_hash_after"] == rollback["parent_checkpoint_hash"]
    )
    assert rollback["exact"] is True


def test_receipt_preserves_scientific_claim_boundary(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert result["status"] == "partial"
    assert claims["bounded_two_member_corotational_fiber_frame"] is True
    assert claims["isotropic_kinematic_combined_linear_hardening"] is True
    assert claims["cyclic_steel_yield_and_nonnegative_dissipation"] is True
    assert claims["same_parent_material_plus_geometric_tangent"] is True
    assert claims["consistent_newton_commit_and_exact_rollback"] is True
    assert claims["analytic_elastic_prefix"] is True
    assert claims["pure_steel_section"] is False
    assert claims["concrete_damage_validation"] is False
    assert claims["finite_strain_or_multiaxial_steel"] is False
    assert claims["local_buckling_or_fracture"] is False
    assert claims["external_cyclic_member_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)


def test_invalid_variant_and_diagnostic_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="unsupported steel hardening variant"):
        make_stateful_corotational_steel_frame_cyclic_problem("unsupported")

    problem = make_stateful_corotational_steel_frame_cyclic_problem(COMBINED_ID)
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    parent_bytes = initial.canonical_bytes()
    with pytest.raises(ValueError, match="invalid shape or values"):
        finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
            problem,
            initial,
            target_load_factor=0.9,
            trial_free_coordinates_m=(0.0,),
        )
    with pytest.raises(ValueError, match="finite and positive"):
        finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
            problem,
            initial,
            target_load_factor=0.9,
            trial_free_coordinates_m=(0.0,) * len(problem.free_global_dofs),
            epsilon_m=0.0,
        )
    assert initial.canonical_bytes() == parent_bytes
