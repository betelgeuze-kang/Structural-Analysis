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
    StatefulCorotationalFiberFrame2DLink,
    StatefulCorotationalFiberFrame2DLinkProblem,
    assemble_stateful_corotational_fiber_frame2d_links,
    initial_stateful_corotational_fiber_frame2d_link_checkpoint,
)
from structural_analysis.benchmark.stateful_corotational_linked_frame_cyclic import (
    make_stateful_corotational_linked_frame_cyclic_problem,
)
from structural_analysis.benchmark.stateful_corotational_local_axis_linked_frame_cyclic import (
    LOCAL_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    LOCAL_AXIS_LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION,
    LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS,
    LOCAL_AXIS_LINKED_FRAME_NODE_COORDINATES_M,
    LOCAL_AXIS_LINKED_FRAME_REFERENCE_DIRECTION,
    STATEFUL_COROTATIONAL_LOCAL_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_local_axis_linked_frame_cyclic_benchmark,
    make_stateful_corotational_local_axis_linked_frame_cyclic_problem,
)
from structural_analysis.materials.bilinear_link import BilinearCombinedHardeningLink


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_local_axis_linked_frame_cyclic_benchmark()


def test_problem_uses_fixed_reference_45_degree_local_axis() -> None:
    problem = make_stateful_corotational_local_axis_linked_frame_cyclic_problem()
    frame = problem.frame_problem
    link = problem.links[0]
    root_half = math.sqrt(0.5)

    assert frame.node_coordinates_m == LOCAL_AXIS_LINKED_FRAME_NODE_COORDINATES_M
    assert frame.fixed_global_dofs == (0, 1, 2, 3, 4, 5)
    assert frame.free_global_dofs == (6, 7, 8)
    assert len(frame.members) == 1
    assert link.component == "local_axial"
    assert link.global_dofs() == LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS
    assert link.reference_direction_cosines(frame.node_coordinates_m) == pytest.approx(
        (root_half, root_half)
    )
    assert link.kinematic_vector(frame.node_coordinates_m) == pytest.approx(
        (-root_half, -root_half, root_half, root_half)
    )
    payload = link.contract_payload(frame.node_coordinates_m)
    assert payload["reference_direction_cosines"] == pytest.approx(
        LOCAL_AXIS_LINKED_FRAME_REFERENCE_DIRECTION
    )
    assert len(LOCAL_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert LOCAL_AXIS_LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION == pytest.approx(
        0.7347193840943683
    )
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION.endswith(".v3")
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION.endswith(
        ".v3"
    )


def test_local_axis_benchmark_is_exposed_from_public_namespace() -> None:
    assert (
        benchmark_api.build_stateful_corotational_local_axis_linked_frame_cyclic_benchmark
        is build_stateful_corotational_local_axis_linked_frame_cyclic_benchmark
    )
    assert (
        benchmark_api.make_stateful_corotational_local_axis_linked_frame_cyclic_problem
        is make_stateful_corotational_local_axis_linked_frame_cyclic_problem
    )


def test_zero_state_scatter_has_four_dof_direction_cosine_tangent() -> None:
    problem = make_stateful_corotational_local_axis_linked_frame_cyclic_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    row = assembly.link_assemblies[0]
    kinematic = np.asarray(row.kinematic_vector)
    expected_tangent = 5_000.0 * np.outer(kinematic, kinematic)

    assert row.global_dofs == LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS
    assert np.array_equal(row.internal_load_global_kn, np.zeros(4))
    assert np.array_equal(row.tangent_global_kn_per_m, expected_tangent)
    assert np.array_equal(
        assembly.link_material_tangent_global[
            np.ix_(
                LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS,
                LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS,
            )
        ],
        expected_tangent,
    )
    assert expected_tangent[0, 1] > 0.0
    assert expected_tangent[0, 3] < 0.0
    assert row.kinematic_vector.flags.writeable is False
    assert row.tangent_global_kn_per_m.flags.writeable is False
    with pytest.raises(ValueError, match="four-DOF link kinematic vector"):
        replace(row, kinematic_vector=(-1.0, 0.0, 1.0, 1.0))


def test_local_axis_definition_fails_closed_on_degenerate_or_duplicate_wiring() -> None:
    material = BilinearCombinedHardeningLink()
    local = StatefulCorotationalFiberFrame2DLink(
        link_id="local",
        node_i=0,
        node_j=1,
        component="local_axial",
        material=material,
    )
    with pytest.raises(ValueError, match="requires node coordinates"):
        local.contract_payload()
    with pytest.raises(ValueError, match="reference length"):
        local.reference_direction_cosines(((0.0, 0.0), (0.0, 0.0)))

    global_problem = make_stateful_corotational_linked_frame_cyclic_problem()
    duplicate_local = StatefulCorotationalFiberFrame2DLink(
        link_id="duplicate-local",
        node_i=1,
        node_j=3,
        component="local_axial",
        material=material,
    )
    with pytest.raises(ValueError, match="duplicate link endpoint"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="duplicate-global-local-axis",
            frame_problem=global_problem.frame_problem,
            links=(global_problem.links[0], duplicate_local),
        )

    fixed_local = StatefulCorotationalFiberFrame2DLink(
        link_id="fixed-local",
        node_i=0,
        node_j=2,
        component="local_axial",
        material=material,
    )
    with pytest.raises(ValueError, match="at least one free"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="fixed-global-local-axis",
            frame_problem=global_problem.frame_problem,
            links=(fixed_local,),
        )


def test_cyclic_local_axis_path_commits_replays_and_preserves_ancestry(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_LOCAL_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert result["contract_pass"] is True
    assert result["status"] == "partial"
    assert result["path_status"] == "ready"
    assert result["requested_step_count"] == 30
    assert result["committed_step_count"] == 30
    assert result["path_ancestry_exact"] is True
    assert result["deterministic_replay_exact"] is True
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0
    assert result["maximum_residual_inf_norm_kn"] == pytest.approx(
        1.2132765903061227e-09
    )
    assert result["maximum_vector_balance_error_kn"] == pytest.approx(
        1.2132801430198015e-09
    )


def test_local_axis_link_yields_reverses_and_dissipates(
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
        1.766982863964368
    )
    energy = [float(row["link_dissipated_energy_kn_m"]) for row in result["steps"]]
    assert energy == sorted(energy)


def test_local_axis_transform_elastic_prefix_and_mixed_tangent_pass(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["elastic_reference"]["pass"] is True
    assert result["elastic_reference"]["relative_error"] == pytest.approx(
        4.262539427780258e-05
    )
    assert result["maximum_force_transformation_error_kn"] == pytest.approx(
        7.105427357601002e-15
    )
    assert result["maximum_link_compatibility_error_m"] <= 1.0e-12
    assert result["link"]["off_axis_tangent_inf_norm_kn_per_m"] > 0.0
    tangent = result["same_parent_frame_link_tangent"]
    assert tangent["pass"] is True
    assert tangent["yielded_link_count"] == 1
    assert tangent["all_tangent_terms_active"] is True
    assert tangent["relative_inf_error"] == pytest.approx(3.903561874559493e-08)
    assert result["yielded_link_newton_quadratic_convergence"]["pass"] is True
    assert (
        result["yielded_link_newton_quadratic_convergence"]["minimum_observed_order"]
        >= 1.8
    )


def test_local_axis_claim_boundary_and_forced_failure_remain_explicit(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert claims["fixed_reference_local_axis_translational_link"] is True
    assert claims["four_dof_direction_cosine_force_and_tangent_scatter"] is True
    assert claims["updated_or_follower_link_axis"] is False
    assert claims["rotational_or_coupled_multi_axis_link_response"] is False
    assert claims["gap_contact_friction_or_uplift"] is False
    assert claims["external_device_acceptance"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert (
        "updated_and_follower_link_axis_not_implemented" in result["blockers_remaining"]
    )
    assert result["forced_failure_rollback"]["exact"] is True
    assert result["forced_failure_rollback"]["status"] == "blocked"
    assert result["forced_failure_rollback"]["terminal_reason"] == (
        "max_iterations_exceeded"
    )
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    assert json.loads(encoded) == result
