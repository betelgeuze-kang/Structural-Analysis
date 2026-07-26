from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest

import structural_analysis.assembly as assembly_api
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
    LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2,
    LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION,
    LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M,
    STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
    build_stateful_corotational_linked_frame_cyclic_benchmark,
    make_stateful_corotational_linked_frame_cyclic_problem,
)
from structural_analysis.materials.bilinear_link import BilinearCombinedHardeningLink


@pytest.fixture(scope="module")
def benchmark_receipt() -> dict:
    return build_stateful_corotational_linked_frame_cyclic_benchmark()


def test_problem_connects_two_free_frame_dofs_with_one_stateful_link() -> None:
    problem = make_stateful_corotational_linked_frame_cyclic_problem()
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
    assert len(frame.members) == 2
    assert link.link_id == "top-transfer-link"
    assert link.global_dofs() == (3, 9)
    assert link.component == "ux"
    assert link.material.initial_stiffness_kn_per_m == 5_000.0
    assert link.material.yield_force_kn == 20.0
    assert link.material.plastic_consistent_tangent_kn_per_m == pytest.approx(
        454.54545454545456
    )
    assert len(LINKED_FRAME_CYCLIC_LOAD_FACTORS) == 30
    assert LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2 == pytest.approx(8_193.25)
    assert LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M == (
        pytest.approx(910.3611111111111)
    )
    assert LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION == pytest.approx(
        0.4582799734197615
    )


def test_linked_frame_coupling_is_exposed_from_public_namespaces() -> None:
    assert assembly_api.StatefulCorotationalFiberFrame2DLinkProblem is (
        StatefulCorotationalFiberFrame2DLinkProblem
    )
    assert assembly_api.assemble_stateful_corotational_fiber_frame2d_links is (
        assemble_stateful_corotational_fiber_frame2d_links
    )
    assert benchmark_api.build_stateful_corotational_linked_frame_cyclic_benchmark is (
        build_stateful_corotational_linked_frame_cyclic_benchmark
    )


def test_zero_state_link_scatter_is_equal_opposite_and_symmetric() -> None:
    problem = make_stateful_corotational_linked_frame_cyclic_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    parent_bytes = checkpoint.canonical_bytes()
    assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )

    assert checkpoint.canonical_bytes() == parent_bytes
    assert checkpoint.to_dict()["schema_version"] == (
        STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION
    )
    assert assembly.to_dict()["schema_version"] == (
        STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION
    )
    assert np.array_equal(assembly.residual_kn, np.zeros(6))
    assert np.array_equal(
        assembly.link_assemblies[0].internal_load_global_kn,
        np.zeros(2),
    )
    expected_link_tangent = np.array([[5_000.0, -5_000.0], [-5_000.0, 5_000.0]])
    assert np.array_equal(
        assembly.link_assemblies[0].tangent_global_kn_per_m,
        expected_link_tangent,
    )
    assert np.array_equal(
        assembly.link_material_tangent_global[np.ix_((3, 9), (3, 9))],
        expected_link_tangent,
    )
    assert np.array_equal(
        assembly.material_tangent_global,
        assembly.frame_material_tangent_global + assembly.link_material_tangent_global,
    )
    assert np.array_equal(
        assembly.consistent_tangent_global,
        assembly.material_tangent_global + assembly.geometric_tangent_global,
    )
    assert assembly.global_displacements.flags.writeable is False
    assert assembly.jacobian_kn_per_m.flags.writeable is False
    with pytest.raises(ValueError, match="deformation does not match"):
        replace(assembly.link_assemblies[0], deformation_m=1.0)
    with pytest.raises(ValueError, match="sorted distinct"):
        replace(assembly, free_global_dofs=tuple(reversed(assembly.free_global_dofs)))


def test_link_definition_and_problem_fail_closed_on_unsupported_wiring() -> None:
    problem = make_stateful_corotational_linked_frame_cyclic_problem()
    material = BilinearCombinedHardeningLink()

    with pytest.raises(ValueError, match="component"):
        StatefulCorotationalFiberFrame2DLink(
            link_id="bad-component",
            node_i=1,
            node_j=3,
            component="rz",  # type: ignore[arg-type]
            material=material,
        )
    fixed_to_fixed = StatefulCorotationalFiberFrame2DLink(
        link_id="fixed-to-fixed",
        node_i=0,
        node_j=2,
        component="ux",
        material=material,
    )
    with pytest.raises(ValueError, match="at least one free"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-fixed-link",
            frame_problem=problem.frame_problem,
            links=(fixed_to_fixed,),
        )
    duplicate = StatefulCorotationalFiberFrame2DLink(
        link_id="duplicate",
        node_i=1,
        node_j=3,
        component="ux",
        material=material,
    )
    with pytest.raises(ValueError, match="duplicate link endpoint"):
        StatefulCorotationalFiberFrame2DLinkProblem(
            case_id="invalid-duplicate-link",
            frame_problem=problem.frame_problem,
            links=(problem.links[0], duplicate),
        )


def test_cyclic_linked_frame_commits_replays_and_preserves_ancestry(
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
    assert result["fallback_count"] == 0
    assert result["regularization_count"] == 0
    assert result["line_search_history_entry_count"] > 0
    assert result["maximum_residual_inf_norm_kn"] == pytest.approx(
        4.256719421391608e-10
    )
    assert (
        result["maximum_residual_inf_norm_kn"]
        <= result["maximum_residual_inf_norm_tolerance_kn"]
    )


def test_link_yields_reverses_and_transfers_force_between_frames(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt

    assert result["yielded_step_indices"] == [
        6,
        7,
        8,
        9,
        10,
        17,
        18,
        19,
        20,
        28,
        29,
        30,
    ]
    assert result["reverse_loading_yielded_step_indices"] == [17, 18, 19, 20]
    assert result["plastic_flow_reversal_count"] == 2
    assert result["dissipation_nonnegative_monotonic"] is True
    assert result["final_link_dissipated_energy_kn_m"] == pytest.approx(
        1.2517198603421096
    )
    assert result["maximum_force_transfer_error_kn"] == pytest.approx(
        3.2082780876407924e-10
    )
    assert (
        result["maximum_force_transfer_error_kn"]
        <= result["maximum_force_transfer_error_tolerance_kn"]
    )
    assert result["maximum_link_compatibility_error_m"] == 0.0
    assert result["elastic_reference"]["pass"] is True
    assert result["elastic_reference"]["relative_error"] <= 1.0e-4
    energy = [float(row["link_dissipated_energy_kn_m"]) for row in result["steps"]]
    assert energy == sorted(energy)
    assert energy[-1] == pytest.approx(result["final_link_dissipated_energy_kn_m"])


def test_same_parent_frame_link_tangent_and_newton_order_are_consistent(
    benchmark_receipt: dict,
) -> None:
    tangent = benchmark_receipt["same_parent_frame_link_tangent"]
    quadratic = benchmark_receipt["yielded_link_newton_quadratic_convergence"]

    assert tangent["pass"] is True
    assert tangent["same_committed_parent_checkpoint"] is True
    assert tangent["yielded_link_count"] == 1
    assert tangent["yielded_member_count"] == 0
    assert tangent["damaged_member_count"] == 0
    assert tangent["all_tangent_terms_active"] is True
    # The centered-difference diagnostic varies at the last few ulps across
    # supported BLAS/NumPy builds; the declared scientific tolerance is the
    # contract, not one platform's floating-point fingerprint.
    assert tangent["relative_inf_error"] > 0.0
    assert tangent["relative_inf_error"] <= tangent["relative_tolerance"]
    assert tangent["tangent_symmetry_error_kn_per_m"] <= 1.0e-9
    assert tangent["frame_link_material_split_error_kn_per_m"] <= 1.0e-8
    assert tangent["material_geometric_split_error_kn_per_m"] <= 1.0e-8
    assert quadratic["pass"] is True
    assert quadratic["minimum_observed_order"] == pytest.approx(4.203443045019442)
    assert quadratic["minimum_observed_order"] >= 1.8
    assert quadratic["relative_residual_roundoff_floor"] == 1.0e-7
    assert quadratic["excluded_terminal_roundoff_history_count"] == 1


def test_forced_failure_rolls_back_frame_and_link_state_exactly(
    benchmark_receipt: dict,
) -> None:
    rollback = benchmark_receipt["forced_failure_rollback"]

    assert rollback["status"] == "blocked"
    assert rollback["terminal_reason"] == "max_iterations_exceeded"
    assert rollback["parent_link_accumulated_plastic_deformation_m"] > 0.0
    assert (
        rollback["accepted_checkpoint_hash_after"] == rollback["parent_checkpoint_hash"]
    )
    assert (
        rollback["accepted_link_state_hash_after"] == rollback["parent_link_state_hash"]
    )
    assert rollback["exact"] is True


def test_receipt_preserves_link_integration_claim_boundary(
    benchmark_receipt: dict,
) -> None:
    result = benchmark_receipt
    claims = result["claims"]

    assert result["schema_version"] == (
        STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
    )
    assert claims["bounded_two_member_corotational_fiber_frame"] is True
    assert claims["free_to_free_global_axis_translational_link"] is True
    assert claims["state_updated_link_force_and_tangent_scatter"] is True
    assert claims["cyclic_link_yield_reversal_and_nonnegative_dissipation"] is True
    assert claims["atomic_frame_and_link_checkpoint_commit"] is True
    assert claims["same_parent_frame_link_geometric_tangent"] is True
    assert claims["consistent_newton_commit_and_exact_rollback"] is True
    assert claims["analytic_elastic_force_transfer_prefix"] is True
    assert claims["inelastic_frame_member_and_link_interaction"] is False
    assert claims["rotational_or_multi_axis_link_coupling"] is False
    assert claims["local_axis_link_transformation"] is False
    assert claims["gap_contact_friction_or_uplift"] is False
    assert claims["viscous_rate_degradation_or_pinching"] is False
    assert claims["shell_connection_integration"] is False
    assert claims["external_device_acceptance"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert claims["commercial_readiness"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)
