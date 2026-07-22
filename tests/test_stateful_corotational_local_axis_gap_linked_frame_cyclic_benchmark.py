from __future__ import annotations

from dataclasses import replace
import json
import math

import numpy as np
import pytest

import structural_analysis.benchmark as benchmark_api
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_link import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION,
    StatefulCorotationalFiberFrame2DCompressionOnlyGapLink,
    StatefulCorotationalFiberFrame2DLinkProblem,
    assemble_stateful_corotational_fiber_frame2d_links,
    initial_stateful_corotational_fiber_frame2d_link_checkpoint,
)
from structural_analysis.benchmark.stateful_corotational_local_axis_gap_linked_frame_cyclic import (
    LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M,
    LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M,
    LOCAL_AXIS_GAP_LINKED_FRAME_LINK_GLOBAL_DOFS,
    LOCAL_AXIS_GAP_LINKED_FRAME_NODE_COORDINATES_M,
    LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION,
    STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark,
    make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem,
)
from structural_analysis.materials.compression_only_gap_link import (
    CompressionOnlyGapLink,
    CompressionOnlyGapLinkResponse,
)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark()


def test_problem_uses_fixed_reference_45_degree_contact_normal() -> None:
    problem = make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem()
    frame = problem.frame_problem
    link = problem.links[0]
    root_half = math.sqrt(0.5)

    assert frame.node_coordinates_m == LOCAL_AXIS_GAP_LINKED_FRAME_NODE_COORDINATES_M
    assert frame.fixed_global_dofs == (0, 1, 2, 3, 4, 5)
    assert frame.free_global_dofs == (6, 7, 8)
    assert link.component == "local_axial"
    assert link.global_dofs() == LOCAL_AXIS_GAP_LINKED_FRAME_LINK_GLOBAL_DOFS
    assert link.reference_direction_cosines(frame.node_coordinates_m) == pytest.approx(
        (root_half, root_half)
    )
    assert link.kinematic_vector(frame.node_coordinates_m) == pytest.approx(
        (-root_half, -root_half, root_half, root_half)
    )
    payload = link.contract_payload(frame.node_coordinates_m)
    assert payload["contact_normal"] == ("fixed_reference_local_axis_node_i_to_node_j")
    assert payload["reference_direction_cosines"] == pytest.approx(
        LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION
    )
    assert payload["axis_update"] == "none_fixed_reference_normal"
    assert payload["geometric_tangent"] == "zero_fixed_reference_normal"
    assert link.material.contact_stiffness_kn_per_m == (
        LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M
    )
    assert link.material.initial_gap_m == LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M
    assert len(LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION.endswith(".v6")
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION.endswith(
        ".v6"
    )


def test_local_axis_gap_benchmark_is_exposed_from_public_namespace() -> None:
    assert (
        benchmark_api.build_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark
        is build_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark
    )
    assert (
        benchmark_api.make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem
        is make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem
    )


def test_open_and_closed_scatter_use_four_dof_fixed_normal_tangent() -> None:
    problem = make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    parent_bytes = checkpoint.canonical_bytes()
    open_assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    direction = np.asarray(LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION)
    closed_coordinates = np.zeros(len(problem.free_global_dofs))
    closed_coordinates[:2] = -0.005 * direction
    closed_assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=closed_coordinates,
    )
    open_row = open_assembly.link_assemblies[0]
    closed_row = closed_assembly.link_assemblies[0]
    expected_kinematic = np.concatenate((-direction, direction))
    expected_tangent = 5_000.0 * np.outer(expected_kinematic, expected_kinematic)

    assert checkpoint.canonical_bytes() == parent_bytes
    assert type(open_row.response) is CompressionOnlyGapLinkResponse
    assert open_row.response.contact_active is False
    assert np.array_equal(open_row.internal_load_global_kn, np.zeros(4))
    assert np.array_equal(open_row.tangent_global_kn_per_m, np.zeros((4, 4)))
    assert closed_row.response.contact_active is True
    assert closed_row.response.force_kn == pytest.approx(-5.0)
    assert np.array_equal(closed_row.kinematic_vector, expected_kinematic)
    assert np.array_equal(closed_row.tangent_global_kn_per_m, expected_tangent)
    assert np.array_equal(
        closed_assembly.link_geometric_tangent_global,
        np.zeros((9, 9)),
    )
    assert closed_row.kinematic_vector.flags.writeable is False
    with pytest.raises(ValueError, match="four-DOF link kinematic vector"):
        replace(closed_row, kinematic_vector=(-1.0, 0.0, 1.0, 1.0))


def test_local_axis_gap_definition_fails_closed() -> None:
    material = CompressionOnlyGapLink()
    local = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="local-gap",
        node_i=0,
        node_j=2,
        component="local_axial",
        material=material,
    )
    with pytest.raises(ValueError, match="requires node coordinates"):
        local.contract_payload()
    with pytest.raises(ValueError, match="reference length"):
        local.reference_direction_cosines(((0.0, 0.0), (1.0, 0.0), (0.0, 0.0)))
    with pytest.raises(ValueError, match="component"):
        StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
            link_id="bad-updated-gap",
            node_i=0,
            node_j=2,
            component="updated_axial",  # type: ignore[arg-type]
            material=material,
        )

    problem = make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem()
    fixed_to_fixed = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="fixed-gap",
        node_i=0,
        node_j=1,
        component="local_axial",
        material=material,
    )
    with pytest.raises(ValueError, match="at least one free"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-fixed-gap",
            frame_problem=problem.frame_problem,
            links=(fixed_to_fixed,),
        )
    reversed_duplicate = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="reversed-local-gap",
        node_i=2,
        node_j=0,
        component="local_axial",
        material=material,
    )
    with pytest.raises(ValueError, match="duplicate link endpoint"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-duplicate-gap",
            frame_problem=problem.frame_problem,
            links=(problem.links[0], reversed_duplicate),
        )


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
    assert result["maximum_penetration_m"] == pytest.approx(0.004830650257828986)
    assert result["force_sign_pass"] is True
    assert result["conservative_return_to_open_pass"] is True
    assert (
        0.0
        <= result["maximum_residual_inf_norm_kn"]
        <= result["maximum_residual_inf_norm_tolerance_kn"]
    )
    assert (
        0.0
        <= result["maximum_vector_balance_error_kn"]
        <= result["maximum_vector_balance_error_tolerance_kn"]
    )
    assert (
        0.0
        <= result["maximum_force_transformation_error_kn"]
        <= result["maximum_force_transformation_error_tolerance_kn"]
    )
    assert (
        0.0
        <= result["maximum_link_compatibility_error_m"]
        <= result["maximum_link_compatibility_error_tolerance_m"]
    )
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0


def test_linearized_branches_tangents_and_covariance_are_consistent(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    onset = result["analytic_contact_onset"]
    open_branch = result["analytic_open_branch"]
    closed_branch = result["analytic_contact_branch"]
    open_full = result["same_parent_open_frame_gap_tangent"]
    closed_full = result["same_parent_closed_frame_gap_tangent"]
    covariance = result["fixed_reference_rotation_covariance"]

    assert onset["bracket_pass"] is True
    assert onset["analytic_load_factor"] == pytest.approx(-0.18053192936553764)
    assert open_branch["reference_class"] == "small_displacement_linearized_carrier"
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
    assert result["same_parent_open_material_tangent"]["pass"] is True
    assert result["same_parent_closed_material_tangent"]["pass"] is True
    assert result["closed_active_set_newton_quadratic_convergence"]["pass"] is True
    assert result["maximum_frame_geometric_tangent_inf_norm_kn_per_m"] > 0.0
    assert result["maximum_link_geometric_tangent_inf_norm_kn_per_m"] == 0.0
    assert covariance["pass"] is True
    assert covariance["force_covariance_error_kn"] == 0.0
    assert 0.0 <= covariance["maximum_error"] <= covariance["tolerance"]


def test_rollback_and_claim_boundary_remain_explicit(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    rollback = result["forced_failure_rollback"]
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["parent_contact_active"] is True
    assert rollback["exact"] is True
    assert claims["bounded_inclined_corotational_fiber_frame"] is True
    assert claims["scalar_fixed_reference_local_axis_compression_only_gap"] is True
    assert claims["four_dof_direction_cosine_force_and_tangent_scatter"] is True
    assert claims["coordinate_rotation_covariance"] is True
    assert claims["updated_or_follower_contact_normal"] is False
    assert claims["friction_impact_or_coupled_contact"] is False
    assert claims["general_foundation_uplift_validation"] is False
    assert claims["external_contact_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)
