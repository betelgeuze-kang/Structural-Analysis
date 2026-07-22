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
    StatefulCorotationalFiberFrame2DLinkProblem,
    assemble_stateful_corotational_fiber_frame2d_links,
    initial_stateful_corotational_fiber_frame2d_link_checkpoint,
)
from structural_analysis.benchmark.stateful_corotational_local_axis_linked_frame_cyclic import (
    make_stateful_corotational_local_axis_linked_frame_cyclic_problem,
)
from structural_analysis.benchmark.stateful_corotational_updated_axis_linked_frame_cyclic import (
    STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
    UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    UPDATED_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS,
    UPDATED_AXIS_LINKED_FRAME_NODE_COORDINATES_M,
    UPDATED_AXIS_LINKED_FRAME_REFERENCE_DIRECTION,
    build_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark,
    make_stateful_corotational_updated_axis_linked_frame_cyclic_problem,
)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark()


def test_problem_uses_current_chord_updated_axial_kinematics() -> None:
    problem = make_stateful_corotational_updated_axis_linked_frame_cyclic_problem()
    frame = problem.frame_problem
    link = problem.links[0]
    zero = np.zeros(problem.global_dof_count, dtype=np.float64)
    root_half = math.sqrt(0.5)

    assert frame.node_coordinates_m == UPDATED_AXIS_LINKED_FRAME_NODE_COORDINATES_M
    assert frame.fixed_global_dofs == (0, 1, 2, 3, 4, 5)
    assert frame.free_global_dofs == (6, 7, 8)
    assert len(frame.members) == 1
    assert link.component == "updated_axial"
    assert link.global_dofs() == UPDATED_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS
    assert link.reference_length_m(frame.node_coordinates_m) == pytest.approx(
        3.0 * math.sqrt(2.0)
    )
    assert link.reference_direction_cosines(frame.node_coordinates_m) == pytest.approx(
        (root_half, root_half)
    )
    assert link.kinematic_vector(frame.node_coordinates_m, zero) == pytest.approx(
        (-root_half, -root_half, root_half, root_half)
    )
    payload = link.contract_payload(frame.node_coordinates_m)
    assert payload["axis_update"] == "current_endpoint_chord"
    assert payload["deformation_measure"] == "current_length-reference_length"
    assert payload["geometric_tangent"] == "force*current_length_hessian"
    assert payload["reference_direction_cosines"] == pytest.approx(
        UPDATED_AXIS_LINKED_FRAME_REFERENCE_DIRECTION
    )
    assert len(UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION.endswith(".v3")
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION.endswith(
        ".v3"
    )


def test_updated_axis_benchmark_is_exposed_from_public_namespace() -> None:
    assert (
        benchmark_api.build_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark
        is build_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark
    )
    assert (
        benchmark_api.make_stateful_corotational_updated_axis_linked_frame_cyclic_problem
        is make_stateful_corotational_updated_axis_linked_frame_cyclic_problem
    )


def test_zero_state_has_material_scatter_and_dormant_geometric_term() -> None:
    problem = make_stateful_corotational_updated_axis_linked_frame_cyclic_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    row = assembly.link_assemblies[0]
    kinematic = np.asarray(row.kinematic_vector)
    expected_material = 5_000.0 * np.outer(kinematic, kinematic)

    assert row.component == "updated_axial"
    assert row.global_dofs == UPDATED_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS
    assert np.array_equal(row.internal_load_global_kn, np.zeros(4))
    assert np.array_equal(row.material_tangent_global_kn_per_m, expected_material)
    assert np.linalg.norm(row.deformation_hessian_per_m, ord=np.inf) > 0.0
    assert np.array_equal(row.geometric_tangent_global_kn_per_m, np.zeros((4, 4)))
    assert np.array_equal(row.tangent_global_kn_per_m, expected_material)
    assert np.array_equal(assembly.link_geometric_tangent_global, np.zeros((9, 9)))
    assert row.deformation_hessian_per_m.flags.writeable is False
    assert row.geometric_tangent_global_kn_per_m.flags.writeable is False
    with pytest.raises(ValueError, match="deformation hessian"):
        replace(row, deformation_hessian_per_m=np.zeros((4, 4)))


def test_updated_axis_definition_fails_closed_on_missing_collapsed_or_duplicate_geometry() -> (
    None
):
    problem = make_stateful_corotational_updated_axis_linked_frame_cyclic_problem()
    frame = problem.frame_problem
    link = problem.links[0]
    coordinates = frame.node_coordinates_m

    with pytest.raises(ValueError, match="requires global displacements"):
        link.kinematic_vector(coordinates)

    collapsed = np.zeros(problem.global_dof_count, dtype=np.float64)
    anchor = np.asarray(coordinates[link.node_i], dtype=np.float64)
    top = np.asarray(coordinates[link.node_j], dtype=np.float64)
    collapsed[3 * link.node_j : 3 * link.node_j + 2] = anchor - top
    with pytest.raises(ValueError, match="current length"):
        link.current_length_and_direction(coordinates, collapsed)

    fixed_problem = make_stateful_corotational_local_axis_linked_frame_cyclic_problem()
    duplicate_updated = replace(
        fixed_problem.links[0],
        link_id="duplicate-updated-link",
        component="updated_axial",
    )
    with pytest.raises(ValueError, match="duplicate link endpoint"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="duplicate-fixed-and-updated-axis",
            frame_problem=fixed_problem.frame_problem,
            links=(fixed_problem.links[0], duplicate_updated),
        )


def test_cyclic_updated_axis_path_commits_replays_and_preserves_ancestry(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert result["contract_pass"] is True
    assert result["status"] == "partial"
    assert result["path_status"] == "ready"
    assert result["paired_fixed_reference_path_status"] == "ready"
    assert result["requested_step_count"] == 30
    assert result["committed_step_count"] == 30
    assert result["path_ancestry_exact"] is True
    assert result["deterministic_replay_exact"] is True
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0
    assert result["maximum_residual_inf_norm_kn"] == pytest.approx(
        6.854250500509806e-11
    )
    assert result["maximum_vector_balance_error_kn"] == pytest.approx(
        6.854250500509806e-11
    )


def test_updated_axis_link_yields_reverses_and_dissipates(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["yielded_step_indices"] == [
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        15,
        16,
        17,
        18,
        19,
        20,
        26,
        27,
        28,
        29,
        30,
    ]
    assert result["reverse_loading_yielded_step_indices"] == [16, 17, 18, 19, 20]
    assert result["plastic_flow_reversal_count"] == 2
    assert result["dissipation_nonnegative_monotonic"] is True
    assert result["final_link_dissipated_energy_kn_m"] == pytest.approx(
        1.766987234658431
    )
    energy = [float(row["link_dissipated_energy_kn_m"]) for row in result["steps"]]
    assert energy == sorted(energy)


def test_updated_axis_objectivity_force_transform_and_geometric_tangent_pass(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["elastic_reference"]["pass"] is True
    assert result["maximum_current_axis_rotation_rad"] == pytest.approx(
        0.006257204667228011
    )
    assert result["maximum_updated_minus_fixed_projection_m"] == pytest.approx(
        8.358220677855827e-05
    )
    assert result["maximum_updated_fixed_link_force_difference_kn"] == pytest.approx(
        0.11875325949426951
    )
    assert result["maximum_link_geometric_tangent_inf_norm_kn_per_m"] == pytest.approx(
        19.54895796865197
    )
    assert result["maximum_force_transformation_error_kn"] == pytest.approx(
        7.105427357601002e-15
    )
    assert result["maximum_link_compatibility_error_m"] == 0.0

    objectivity = result["rigid_body_and_length_hessian_objectivity"]
    assert objectivity["pass"] is True
    assert objectivity["rigid_deformation_error_m"] == 0.0
    assert objectivity["rotated_direction_error"] <= 1.0e-15
    assert objectivity["hessian_relative_inf_error"] == pytest.approx(
        1.6210969094876404e-09
    )

    tangent = result["same_parent_frame_link_tangent"]
    assert tangent["pass"] is True
    assert tangent["yielded_link_count"] == 1
    assert tangent["link_geometric_tangent_inf_norm_kn_per_m"] > 0.0
    assert tangent["frame_link_geometric_split_error_kn_per_m"] == 0.0
    assert tangent["relative_inf_error"] == pytest.approx(9.231993823594698e-09)
    reverse_tangent = result["same_parent_reverse_frame_link_tangent"]
    assert reverse_tangent["pass"] is True
    assert reverse_tangent["yielded_link_count"] == 1
    assert reverse_tangent["link_geometric_tangent_inf_norm_kn_per_m"] > 0.0
    assert reverse_tangent["relative_inf_error"] <= 1.0e-7
    assert result["yielded_link_newton_quadratic_convergence"]["pass"] is True
    assert (
        result["yielded_link_newton_quadratic_convergence"]["minimum_observed_order"]
        >= 1.8
    )


def test_updated_axis_claim_boundary_and_forced_failure_remain_explicit(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert claims["updated_current_axis_internal_translational_link"] is True
    assert claims["current_length_force_and_consistent_geometric_tangent"] is True
    assert claims["rigid_body_objective_link_kinematics"] is True
    assert claims["general_nonconservative_follower_external_load"] is False
    assert claims["rotational_or_coupled_multi_axis_link_response"] is False
    assert claims["gap_contact_friction_or_uplift"] is False
    assert claims["external_device_acceptance"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert (
        "rotational_and_coupled_multi_axis_link_response_not_implemented"
        in result["blockers_remaining"]
    )
    assert result["forced_failure_rollback"]["exact"] is True
    assert result["forced_failure_rollback"]["status"] == "blocked"
    assert result["forced_failure_rollback"]["terminal_reason"] == (
        "max_iterations_exceeded"
    )
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    assert json.loads(encoded) == result
