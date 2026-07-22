from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest

import structural_analysis.assembly as assembly_api
import structural_analysis.benchmark as benchmark_api
import structural_analysis.materials as materials_api
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_link import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION,
    StatefulCorotationalFiberFrame2DCompressionOnlyGapLink,
    StatefulCorotationalFiberFrame2DLinkProblem,
    assemble_stateful_corotational_fiber_frame2d_links,
    initial_stateful_corotational_fiber_frame2d_link_checkpoint,
    validate_stateful_corotational_fiber_frame2d_link_checkpoint,
)
from structural_analysis.benchmark.stateful_corotational_gap_linked_frame_cyclic import (
    GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M,
    GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    GAP_LINKED_FRAME_INITIAL_GAP_M,
    GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF,
    GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
    STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_gap_linked_frame_cyclic_benchmark,
    make_stateful_corotational_gap_linked_frame_cyclic_problem,
)
from structural_analysis.materials.bilinear_link import (
    BilinearCombinedHardeningLink,
    BilinearLinkState,
)
from structural_analysis.materials.compression_only_gap_link import (
    GAP_LINK_STATE_SCHEMA_VERSION,
    CompressionOnlyGapLink,
    CompressionOnlyGapLinkResponse,
    CompressionOnlyGapLinkState,
    finite_difference_gap_link_tangent_check,
    integrate_gap_link_deformation_history,
)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_gap_linked_frame_cyclic_benchmark()


def test_gap_material_has_unit_safe_active_set_state_and_tangent() -> None:
    material = CompressionOnlyGapLink(
        contact_stiffness_kn_per_m=5_000.0,
        initial_gap_m=0.004,
        material_id="test-compression-only-gap",
    )
    initial = material.initial_state()
    open_response = material.integrate(-0.003, initial)
    closure_response = material.integrate(-0.004, initial)
    closed_response = material.integrate(-0.005, initial)
    reopened_response = material.integrate(0.0, closed_response.state)
    open_tangent = finite_difference_gap_link_tangent_check(
        material,
        initial,
        deformation_m=-0.002,
    )
    closed_tangent = finite_difference_gap_link_tangent_check(
        material,
        initial,
        deformation_m=-0.006,
    )
    history = integrate_gap_link_deformation_history(
        material,
        (-0.003, -0.005, 0.0, -0.006, 0.0),
    )

    assert type(initial) is CompressionOnlyGapLinkState
    assert initial.to_dict()["schema_version"] == GAP_LINK_STATE_SCHEMA_VERSION
    assert initial.state_hash != BilinearLinkState().state_hash
    assert open_response.contact_active is False
    assert open_response.force_kn == 0.0
    assert open_response.consistent_tangent_kn_per_m == 0.0
    assert closure_response.signed_clearance_m == 0.0
    assert closure_response.contact_active is False
    assert closure_response.consistent_tangent_kn_per_m == 0.0
    assert closed_response.contact_active is True
    assert closed_response.active_set_transition == "closed"
    assert closed_response.force_kn == pytest.approx(-5.0)
    assert closed_response.consistent_tangent_kn_per_m == 5_000.0
    assert closed_response.recoverable_energy_kn_m == pytest.approx(0.0025)
    assert closed_response.yielded is False
    assert reopened_response.active_set_transition == "opened"
    assert reopened_response.state.closure_event_count == 1
    assert reopened_response.state.opening_event_count == 1
    assert open_tangent["pass"] is True
    assert open_tangent["analytic_consistent_tangent_kn_per_m"] == 0.0
    assert closed_tangent["pass"] is True
    assert closed_tangent["analytic_consistent_tangent_kn_per_m"] == 5_000.0
    assert history["closure_event_count"] == 2
    assert history["opening_event_count"] == 2
    assert history["final_state"]["contact_active"] is False

    with pytest.raises(ValueError, match="CompressionOnlyGapLinkState"):
        material.integrate(0.0, BilinearLinkState())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="relative_tolerance"):
        finite_difference_gap_link_tangent_check(
            material,
            initial,
            deformation_m=-0.006,
            relative_tolerance=0.0,
        )
    with pytest.raises(ValueError, match="event counts"):
        CompressionOnlyGapLinkState(
            contact_active=True,
            maximum_penetration_m=0.001,
        )
    with pytest.raises(ValueError, match="penetration history"):
        CompressionOnlyGapLinkState(maximum_penetration_m=0.001)


def test_problem_connects_free_global_x_dofs_with_bounded_gap() -> None:
    problem = make_stateful_corotational_gap_linked_frame_cyclic_problem()
    frame = problem.frame_problem
    link = problem.links[0]

    assert frame.node_coordinates_m == (
        (0.0, 0.0),
        (0.0, 3.0),
        (3.0, 0.0),
        (3.0, 3.0),
    )
    assert frame.fixed_global_dofs == (0, 1, 2, 6, 7, 8)
    assert frame.free_global_dofs == (3, 4, 5, 9, 10, 11)
    assert link.link_id == "top-compression-only-gap"
    assert link.component == "ux"
    assert link.global_dofs() == (
        GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF,
        GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
    )
    assert np.array_equal(link.kinematic_vector(), (-1.0, 1.0))
    assert link.material.contact_stiffness_kn_per_m == (
        GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M
    )
    assert link.material.initial_gap_m == GAP_LINKED_FRAME_INITIAL_GAP_M
    assert len(GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION.endswith(".v6")
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION.endswith(
        ".v6"
    )


def test_gap_link_is_exposed_from_public_namespaces() -> None:
    assert assembly_api.StatefulCorotationalFiberFrame2DCompressionOnlyGapLink is (
        StatefulCorotationalFiberFrame2DCompressionOnlyGapLink
    )
    assert materials_api.CompressionOnlyGapLink is CompressionOnlyGapLink
    assert (
        benchmark_api.build_stateful_corotational_gap_linked_frame_cyclic_benchmark
        is build_stateful_corotational_gap_linked_frame_cyclic_benchmark
    )


def test_open_and_closed_scatter_use_the_declared_one_sided_tangent() -> None:
    problem = make_stateful_corotational_gap_linked_frame_cyclic_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    parent_bytes = checkpoint.canonical_bytes()
    open_assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    open_row = open_assembly.link_assemblies[0]
    closed_coordinates = np.zeros(len(problem.free_global_dofs))
    closed_coordinates[3] = -0.005
    closed_assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=closed_coordinates,
    )
    closed_row = closed_assembly.link_assemblies[0]
    expected_closed_tangent = np.array(((5_000.0, -5_000.0), (-5_000.0, 5_000.0)))

    assert checkpoint.canonical_bytes() == parent_bytes
    assert type(open_row.response) is CompressionOnlyGapLinkResponse
    assert open_row.response.contact_active is False
    assert np.array_equal(open_row.internal_load_global_kn, np.zeros(2))
    assert np.array_equal(open_row.tangent_global_kn_per_m, np.zeros((2, 2)))
    assert closed_row.response.contact_active is True
    assert closed_row.response.force_kn == pytest.approx(-5.0)
    assert np.array_equal(closed_row.internal_load_global_kn, (5.0, -5.0))
    assert np.array_equal(
        closed_row.tangent_global_kn_per_m,
        expected_closed_tangent,
    )
    assert np.array_equal(
        closed_assembly.link_geometric_tangent_global,
        np.zeros((12, 12)),
    )
    with pytest.raises(ValueError, match="deformation does not match"):
        replace(closed_row, deformation_m=0.0)


def test_gap_definition_and_checkpoint_fail_closed_on_mixed_types() -> None:
    problem = make_stateful_corotational_gap_linked_frame_cyclic_problem()
    gap_material = CompressionOnlyGapLink()
    bilinear_material = BilinearCombinedHardeningLink()

    with pytest.raises(ValueError, match="gap-link material"):
        StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
            link_id="bad-gap-material",
            node_i=1,
            node_j=3,
            material=bilinear_material,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="component"):
        StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
            link_id="bad-gap-component",
            node_i=1,
            node_j=3,
            material=gap_material,
            component="uy",  # type: ignore[arg-type]
        )
    fixed_to_fixed = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="fixed-to-fixed-gap",
        node_i=0,
        node_j=2,
        material=gap_material,
    )
    with pytest.raises(ValueError, match="at least one free"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-fixed-gap",
            frame_problem=problem.frame_problem,
            links=(fixed_to_fixed,),
        )
    reversed_duplicate = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="reversed-duplicate-gap",
        node_i=3,
        node_j=1,
        material=gap_material,
    )
    with pytest.raises(ValueError, match="duplicate link endpoint"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-duplicate-gap",
            frame_problem=problem.frame_problem,
            links=(problem.links[0], reversed_duplicate),
        )

    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    mixed = replace(
        checkpoint,
        link_states=(BilinearLinkState(),),
        state_hash="",
    )
    with pytest.raises(ValueError, match="state type does not match"):
        validate_stateful_corotational_fiber_frame2d_link_checkpoint(problem, mixed)


def test_cyclic_path_opens_closes_transfers_and_replays(
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
    assert result["active_step_indices"] == [
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
    ]
    assert result["closure_transition_step_indices"] == [6, 22]
    assert result["opening_transition_step_indices"] == [15, 29]
    assert result["final_closure_event_count"] == 2
    assert result["final_opening_event_count"] == 2
    assert result["maximum_penetration_m"] == pytest.approx(0.0014993474415900248)
    assert result["force_sign_pass"] is True
    assert result["conservative_return_to_open_pass"] is True
    assert (
        0.0
        <= result["maximum_residual_inf_norm_kn"]
        <= result["maximum_residual_inf_norm_tolerance_kn"]
    )
    assert (
        0.0
        <= result["maximum_force_transfer_error_kn"]
        <= result["maximum_force_transfer_error_tolerance_kn"]
    )
    assert result["maximum_link_compatibility_error_m"] == 0.0
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0


def test_analytic_branches_and_same_parent_tangents_are_consistent(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    onset = result["analytic_contact_onset"]
    open_branch = result["analytic_open_branch"]
    closed_branch = result["analytic_contact_branch"]
    open_full = result["same_parent_open_frame_gap_tangent"]
    closed_full = result["same_parent_closed_frame_gap_tangent"]
    open_material = result["same_parent_open_material_tangent"]
    closed_material = result["same_parent_closed_material_tangent"]
    quadratic = result["closed_active_set_newton_quadratic_convergence"]

    assert onset["bracket_pass"] is True
    assert onset["analytic_load_factor"] == pytest.approx(-0.18207222222222222)
    assert open_branch["pass"] is True
    assert 0.0 <= open_branch["relative_error"] <= open_branch["relative_tolerance"]
    assert closed_branch["pass"] is True
    assert 0.0 <= closed_branch["relative_error"] <= closed_branch["relative_tolerance"]
    assert open_full["pass"] is True
    assert open_full["same_committed_parent_checkpoint"] is True
    assert open_full["link_material_tangent_inf_norm_kn_per_m"] == 0.0
    assert 0.0 <= open_full["relative_inf_error"] <= open_full["relative_tolerance"]
    assert closed_full["pass"] is True
    assert closed_full["same_committed_parent_checkpoint"] is True
    assert closed_full["link_material_tangent_inf_norm_kn_per_m"] > 0.0
    assert closed_full["link_geometric_tangent_inf_norm_kn_per_m"] == 0.0
    assert 0.0 <= closed_full["relative_inf_error"] <= closed_full["relative_tolerance"]
    assert open_material["pass"] is True
    assert open_material["relative_error"] == 0.0
    assert closed_material["pass"] is True
    assert (
        0.0
        <= closed_material["relative_error"]
        <= closed_material["relative_tolerance"]
    )
    assert quadratic["pass"] is True
    assert quadratic["minimum_observed_order"] >= 1.8
    assert result["maximum_frame_geometric_tangent_inf_norm_kn_per_m"] > 0.0
    assert result["maximum_link_geometric_tangent_inf_norm_kn_per_m"] == 0.0
    assert result["common_translation_objectivity"]["exact"] is True


def test_forced_failure_rolls_back_active_gap_state_exactly(
    benchmark_receipt: dict,
) -> None:
    rollback = benchmark_receipt["forced_failure_rollback"]

    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["parent_contact_active"] is True
    assert (
        rollback["accepted_checkpoint_hash_after"] == rollback["parent_checkpoint_hash"]
    )
    assert (
        rollback["accepted_link_state_hash_after"] == rollback["parent_link_state_hash"]
    )
    assert rollback["exact"] is True


def test_receipt_preserves_bounded_unilateral_claim_boundary(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert claims["bounded_two_member_corotational_fiber_frame"] is True
    assert claims["scalar_global_x_compression_only_gap"] is True
    assert claims["frictionless_continuous_unilateral_response"] is True
    assert claims["open_closed_active_set_checkpoint_history"] is True
    assert claims["same_parent_open_and_closed_consistent_tangents"] is True
    assert claims["atomic_frame_and_gap_checkpoint_commit"] is True
    assert claims["consistent_newton_commit_and_exact_rollback"] is True
    assert claims["analytic_open_contact_onset_and_closed_branch"] is True
    assert claims["local_or_follower_contact_normal"] is False
    assert claims["friction_impact_or_coupled_contact"] is False
    assert claims["general_foundation_uplift_validation"] is False
    assert claims["inelastic_contact_or_member_interaction"] is False
    assert claims["shell_or_three_dimensional_contact"] is False
    assert claims["external_contact_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)
