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
    StatefulCorotationalFiberFrame2DLink,
    StatefulCorotationalFiberFrame2DLinkProblem,
    StatefulCorotationalFiberFrame2DRotationalLink,
    assemble_stateful_corotational_fiber_frame2d_links,
    initial_stateful_corotational_fiber_frame2d_link_checkpoint,
)
from structural_analysis.benchmark.stateful_corotational_rotational_linked_frame_cyclic import (
    ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF,
    ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF,
    STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_rotational_linked_frame_cyclic_benchmark,
    make_stateful_corotational_rotational_linked_frame_cyclic_problem,
)
from structural_analysis.materials.bilinear_link import (
    BilinearCombinedHardeningLink,
    BilinearLinkState,
)
from structural_analysis.materials.bilinear_rotational_link import (
    ROTATIONAL_LINK_STATE_SCHEMA_VERSION,
    BilinearCombinedHardeningRotationalLink,
    BilinearRotationalLinkState,
    finite_difference_rotational_link_tangent_check,
    integrate_rotational_link_history,
)


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_rotational_linked_frame_cyclic_benchmark()


def test_moment_rotation_material_has_distinct_units_state_and_tangent() -> None:
    material = BilinearCombinedHardeningRotationalLink(
        initial_stiffness_kn_m_per_rad=5_000.0,
        yield_moment_kn_m=20.0,
        isotropic_hardening_kn_m_per_rad=200.0,
        kinematic_hardening_kn_m_per_rad=300.0,
        material_id="test-rotational-link",
    )
    state = material.initial_state()
    response = material.integrate(0.01, state)
    tangent = finite_difference_rotational_link_tangent_check(
        material,
        state,
        rotation_rad=0.01,
    )
    history = integrate_rotational_link_history(
        material,
        (0.002, 0.01, 0.0, -0.01, 0.0, 0.012),
    )

    assert type(state) is BilinearRotationalLinkState
    assert state.to_dict()["schema_version"] == ROTATIONAL_LINK_STATE_SCHEMA_VERSION
    assert state.state_hash != BilinearLinkState().state_hash
    assert response.yielded is True
    assert response.moment_kn_m == pytest.approx(22.727272727272727)
    assert response.consistent_tangent_kn_m_per_rad == pytest.approx(454.54545454545456)
    assert tangent["pass"] is True
    assert tangent["same_committed_parent_state"] is True
    assert tangent["relative_error"] <= tangent["relative_tolerance"]
    assert history["energy_gate_passed"] is True
    assert history["plastic_flow_reversal_count"] >= 1
    assert history["cumulative_dissipated_energy_kn_m"] > 0.0
    with pytest.raises(ValueError, match="BilinearRotationalLinkState"):
        material.integrate(0.0, BilinearLinkState())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="relative_tolerance"):
        finite_difference_rotational_link_tangent_check(
            material,
            state,
            rotation_rad=0.01,
            relative_tolerance=0.0,
        )


def test_problem_connects_free_top_rotations_with_unit_safe_link() -> None:
    problem = make_stateful_corotational_rotational_linked_frame_cyclic_problem()
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
    assert link.link_id == "top-rotation-transfer-link"
    assert link.component == "rz"
    assert link.global_dofs() == (
        ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF,
        ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF,
    )
    assert np.array_equal(link.kinematic_vector(), (-1.0, 1.0))
    assert link.material.initial_stiffness_kn_m_per_rad == 5_000.0
    assert link.material.yield_moment_kn_m == 20.0
    assert link.material.plastic_consistent_tangent_kn_m_per_rad == pytest.approx(
        454.54545454545456
    )
    assert len(ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION.endswith(".v7")
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION.endswith(
        ".v7"
    )


def test_rotational_link_is_exposed_from_public_namespaces() -> None:
    assert assembly_api.StatefulCorotationalFiberFrame2DRotationalLink is (
        StatefulCorotationalFiberFrame2DRotationalLink
    )
    assert materials_api.BilinearCombinedHardeningRotationalLink is (
        BilinearCombinedHardeningRotationalLink
    )
    assert (
        benchmark_api.build_stateful_corotational_rotational_linked_frame_cyclic_benchmark
        is build_stateful_corotational_rotational_linked_frame_cyclic_benchmark
    )


def test_zero_state_scatter_and_rotation_scaling_are_consistent(
    benchmark_receipt: dict,
) -> None:
    problem = make_stateful_corotational_rotational_linked_frame_cyclic_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    parent_bytes = checkpoint.canonical_bytes()
    assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    row = assembly.link_assemblies[0]
    expected = np.array(((5_000.0, -5_000.0), (-5_000.0, 5_000.0)))

    assert checkpoint.canonical_bytes() == parent_bytes
    assert np.array_equal(assembly.residual_kn, np.zeros(6))
    assert np.array_equal(row.internal_moments_global_kn_m, np.zeros(2))
    assert np.array_equal(row.tangent_global_kn_m_per_rad, expected)
    assert np.array_equal(
        assembly.link_material_tangent_global[np.ix_(row.global_dofs, row.global_dofs)],
        expected,
    )
    assert np.array_equal(assembly.link_geometric_tangent_global, np.zeros((12, 12)))
    assert benchmark_receipt["rotation_coordinate_scaling"]["pass"] is True
    assert benchmark_receipt["common_rotation_objectivity"]["pass"] is True
    with pytest.raises(ValueError, match="rotation does not match"):
        replace(row, rotation_rad=1.0)


def test_link_definitions_fail_closed_on_mixed_units() -> None:
    problem = make_stateful_corotational_rotational_linked_frame_cyclic_problem()
    rotational_material = BilinearCombinedHardeningRotationalLink()
    translational_material = BilinearCombinedHardeningLink()

    with pytest.raises(ValueError, match="component"):
        StatefulCorotationalFiberFrame2DLink(
            link_id="bad-translational-rz",
            node_i=1,
            node_j=3,
            component="rz",  # type: ignore[arg-type]
            material=translational_material,
        )
    with pytest.raises(ValueError, match="rotational link material"):
        StatefulCorotationalFiberFrame2DRotationalLink(
            link_id="bad-rotational-material",
            node_i=1,
            node_j=3,
            material=translational_material,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="component"):
        StatefulCorotationalFiberFrame2DRotationalLink(
            link_id="bad-rotational-component",
            node_i=1,
            node_j=3,
            material=rotational_material,
            component="ux",  # type: ignore[arg-type]
        )
    fixed_to_fixed = StatefulCorotationalFiberFrame2DRotationalLink(
        link_id="fixed-to-fixed-rotation",
        node_i=0,
        node_j=2,
        material=rotational_material,
    )
    with pytest.raises(ValueError, match="at least one free"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-fixed-rotational-link",
            frame_problem=problem.frame_problem,
            links=(fixed_to_fixed,),
        )
    reversed_duplicate = StatefulCorotationalFiberFrame2DRotationalLink(
        link_id="reversed-duplicate-rotation",
        node_i=3,
        node_j=1,
        material=rotational_material,
    )
    with pytest.raises(ValueError, match="duplicate link endpoint"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-duplicate-rotational-link",
            frame_problem=problem.frame_problem,
            links=(problem.links[0], reversed_duplicate),
        )


def test_cyclic_path_yields_reverses_transfers_and_replays(
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
    assert result["yielded_step_indices"] == [
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
        27,
        28,
        29,
        30,
    ]
    assert result["reverse_loading_yielded_step_indices"] == [16, 17, 18, 19, 20]
    assert result["plastic_flow_reversal_count"] == 2
    assert result["dissipation_nonnegative_monotonic"] is True
    assert result["final_link_dissipated_energy_kn_m"] == pytest.approx(
        1.3957333424163187
    )
    assert (
        0.0
        <= result["maximum_residual_inf_norm_kn"]
        <= result["maximum_residual_inf_norm_tolerance_kn"]
    )
    assert (
        0.0
        <= result["maximum_moment_transfer_error_kn_m"]
        <= result["maximum_moment_transfer_error_tolerance_kn_m"]
    )
    assert result["maximum_link_compatibility_error_rad"] == 0.0
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0


def test_elastic_prefix_and_same_parent_tangents_are_consistent(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    elastic = result["elastic_reference"]
    full_tangent = result["same_parent_frame_link_tangent"]
    material_tangent = result["same_parent_moment_rotation_material_tangent"]
    quadratic = result["yielded_link_newton_quadratic_convergence"]

    assert elastic["pass"] is True
    assert elastic["relative_error"] == pytest.approx(2.083390139053011e-06)
    assert full_tangent["pass"] is True
    assert full_tangent["same_committed_parent_checkpoint"] is True
    assert full_tangent["yielded_link_count"] == 1
    assert (
        0.0 <= full_tangent["relative_inf_error"] <= full_tangent["relative_tolerance"]
    )
    assert material_tangent["pass"] is True
    assert (
        0.0
        <= material_tangent["relative_error"]
        <= material_tangent["relative_tolerance"]
    )
    assert quadratic["pass"] is True
    assert quadratic["minimum_observed_order"] >= 1.8
    assert result["maximum_frame_geometric_tangent_inf_norm"] > 0.0
    assert result["maximum_link_geometric_tangent_inf_norm"] == 0.0


def test_forced_failure_rolls_back_both_state_families_exactly(
    benchmark_receipt: dict,
) -> None:
    rollback = benchmark_receipt["forced_failure_rollback"]

    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["parent_link_accumulated_plastic_rotation_rad"] > 0.0
    assert (
        rollback["accepted_checkpoint_hash_after"] == rollback["parent_checkpoint_hash"]
    )
    assert (
        rollback["accepted_link_state_hash_after"] == rollback["parent_link_state_hash"]
    )
    assert rollback["exact"] is True


def test_receipt_preserves_scalar_rotation_claim_boundary(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert claims["bounded_two_member_corotational_fiber_frame"] is True
    assert claims["free_to_free_scalar_relative_rz_link"] is True
    assert claims["distinct_moment_rotation_material_and_state_units"] is True
    assert claims["state_updated_link_moment_and_tangent_scatter"] is True
    assert claims["cyclic_link_yield_reversal_and_nonnegative_dissipation"] is True
    assert claims["atomic_frame_and_link_checkpoint_commit"] is True
    assert claims["same_parent_frame_link_consistent_tangent"] is True
    assert claims["common_rotation_objectivity"] is True
    assert claims["analytic_elastic_moment_transfer_prefix"] is True
    assert claims["coupled_multi_axis_link_response"] is False
    assert claims["inelastic_frame_member_and_link_interaction"] is False
    assert claims["gap_contact_friction_or_uplift"] is False
    assert claims["viscous_rate_degradation_or_pinching"] is False
    assert claims["shell_or_3d_connection_integration"] is False
    assert claims["external_device_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)
