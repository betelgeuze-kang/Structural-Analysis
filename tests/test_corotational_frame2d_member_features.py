from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.assembly.corotational_frame2d_member_features import (
    CorotationalFrame2DMemberFeatures,
    consistent_uniform_load_element_global,
    element_end_coordinates_m,
    integrate_corotational_frame2d_member_features,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_engineering_recovery import (
    create_corotational_fiber_frame_engineering_result_ir,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    compile_corotational_fiber_frame_general_profile,
    create_corotational_fiber_frame_general_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    compare_corotational_fiber_frame_dense_sparse_assembly,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


def _feature_element(
    features: CorotationalFrame2DMemberFeatures,
    *,
    node_coordinates: tuple[tuple[float, float], tuple[float, float]] = (
        (0.0, 0.0),
        (4.0, 0.0),
    ),
) -> StatefulCorotationalFiberBeam2D:
    return StatefulCorotationalFiberBeam2D(
        node_coordinates_m=element_end_coordinates_m(
            node_coordinates[0], node_coordinates[1], features
        ),
        section=make_rectangular_stateful_rc_fiber_section(),
        integration_order=3,
        element_id="feature-member",
    )


def _combined_features() -> CorotationalFrame2DMemberFeatures:
    return CorotationalFrame2DMemberFeatures(
        offset_i_global_m=(0.2, 0.1),
        offset_j_global_m=(-0.15, 0.05),
        release_j_rz=True,
        uniform_load_local_kn_per_m=(1.2, -4.0),
    )


def test_uniform_dead_load_uses_initial_local_consistent_vector() -> None:
    features = CorotationalFrame2DMemberFeatures(
        offset_i_global_m=(0.2, 0.0),
        offset_j_global_m=(-0.2, 0.0),
        uniform_load_local_kn_per_m=(0.0, -2.0),
    )
    element = _feature_element(features)

    assert element.initial_length_m == 3.5999999999999996
    np.testing.assert_allclose(
        consistent_uniform_load_element_global(element, features),
        [0.0, -3.6, -2.16, 0.0, -3.6, 2.16],
        rtol=0.0,
        atol=2.0e-15,
    )


def test_explicit_local_axis_and_self_weight_share_consistent_load_operator() -> None:
    features = CorotationalFrame2DMemberFeatures(
        offset_i_global_m=(0.2, 0.0),
        offset_j_global_m=(-0.2, 0.0),
        uniform_load_local_kn_per_m=(0.0, -2.0),
        local_x_axis_global=(1.0, 0.0),
        local_y_axis_global=(0.0, 1.0),
        local_axis_explicit=True,
        self_weight_local_kn_per_m=(0.0, -1.0),
        self_weight_mass_per_length_kg_per_m=100.0,
        self_weight_gravity_global_m_per_s2=(0.0, -10.0),
    )
    element = _feature_element(features)

    np.testing.assert_allclose(
        consistent_uniform_load_element_global(element, features),
        [0.0, -5.4, -3.24, 0.0, -5.4, 3.24],
        rtol=0.0,
        atol=3.0e-15,
    )
    assert features.has_self_weight is True
    assert features.combined_uniform_load_local_kn_per_m == (0.0, -3.0)
    assert features.to_dict()["local_axis_explicit"] is True


def test_explicit_local_axis_must_match_initial_member_chord() -> None:
    features = CorotationalFrame2DMemberFeatures(
        local_x_axis_global=(0.0, 1.0),
        local_y_axis_global=(-1.0, 0.0),
        local_axis_explicit=True,
    )
    element = _feature_element(features)

    with pytest.raises(ValueError, match="must match the initial member chord"):
        consistent_uniform_load_element_global(element, features)


def test_combined_feature_residual_tangent_matches_same_parent_finite_difference() -> (
    None
):
    features = _combined_features()
    element = _feature_element(features)
    parent = element.initial_state()
    nodal = np.asarray([0.0, 0.0, 0.01, 0.01, -0.02, -0.015])
    response = integrate_corotational_frame2d_member_features(
        element,
        features,
        nodal,
        parent,
        target_load_factor=0.7,
    )
    repeated = integrate_corotational_frame2d_member_features(
        element,
        features,
        nodal,
        parent,
        target_load_factor=0.7,
    )

    step = 1.0e-7
    finite_difference = np.zeros((6, 6), dtype=np.float64)
    for column in range(6):
        forward_coordinates = nodal.copy()
        backward_coordinates = nodal.copy()
        forward_coordinates[column] += step
        backward_coordinates[column] -= step
        forward = integrate_corotational_frame2d_member_features(
            element,
            features,
            forward_coordinates,
            parent,
            target_load_factor=0.7,
        )
        backward = integrate_corotational_frame2d_member_features(
            element,
            features,
            backward_coordinates,
            parent,
            target_load_factor=0.7,
        )
        forward_residual = (
            forward.nodal_internal_load_global
            - forward.nodal_equivalent_external_load_global
        )
        backward_residual = (
            backward.nodal_internal_load_global
            - backward.nodal_equivalent_external_load_global
        )
        finite_difference[:, column] = (forward_residual - backward_residual) / (
            2.0 * step
        )

    scaled_error = float(
        np.max(np.abs(finite_difference - response.consistent_tangent_global))
        / max(1.0, float(np.max(np.abs(finite_difference))))
    )
    assert scaled_error < 5.0e-8
    assert abs(response.element_net_end_force_global[5]) < 1.0e-11
    assert np.max(np.abs(response.release_residual_kn_m)) < 1.0e-11
    assert response.release_iterations > 0
    assert response.response_hash == repeated.response_hash
    assert response.element_response.state.state_hash == (
        repeated.element_response.state.state_hash
    )


def _feature_problem() -> StatefulCorotationalFiberFrame2DProblem:
    nodes = ((0.0, 0.0), (4.0, 0.0))
    features = CorotationalFrame2DMemberFeatures(
        offset_i_global_m=(0.2, 0.0),
        offset_j_global_m=(-0.2, 0.0),
        release_j_rz=True,
        uniform_load_local_kn_per_m=(0.0, -2.0),
    )
    element = _feature_element(features, node_coordinates=nodes)
    member = StatefulCorotationalFiberFrame2DMember(
        member_id=element.element_id,
        node_i=0,
        node_j=1,
        element=element,
        features=features,
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="released-offset-distributed-cantilever",
        node_coordinates_m=nodes,
        members=(member,),
        fixed_global_dofs=(0, 1, 2, 5),
        reference_external_loads=(),
        rotation_coordinate_scale_m=4.0,
    )


def test_feature_load_path_sparse_parity_checkpoint_and_exact_recovery() -> None:
    problem = _feature_problem()
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    parity = compare_corotational_fiber_frame_dense_sparse_assembly(
        problem,
        initial,
        target_load_factor=0.25,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    compilation = compile_corotational_fiber_frame_general_profile(
        problem,
        model_content_hash=canonical_hash(
            {"fixture": "released-offset-distributed-cantilever.v1"}
        ),
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5, 0.75, 1.0),
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-9,
            max_iterations=60,
        ),
    )
    adapter = create_corotational_fiber_frame_general_j1_j5_adapter(compilation, path)
    engineering = create_corotational_fiber_frame_engineering_result_ir(
        engineering_result_id="engineering.released_offset_distributed_cantilever",
        source_adapter=adapter,
    )

    assert all(parity.checks.values())
    assert path.contract_pass is True
    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem, path.final_checkpoint
    )
    np.testing.assert_allclose(
        engineering.artifact("reaction_force_n")[0],
        [0.0, 7200.0],
        rtol=0.0,
        atol=2.0e-6,
    )
    assert abs(engineering.artifact("member_end_moment_nm")[0, 1]) < 1.0e-8
    assert engineering.metrics["member_feature_scaled_linf"] == 0.0
    assert engineering.metrics["external_scatter_scaled_linf"] == 0.0
    assert engineering.metrics["release_equilibrium_scaled_linf"] < 1.0e-12
    assert engineering.authority_axes["member_features"] == "exact_bounded_candidate"
    assert "member_end_releases_not_supported" not in engineering.limitations
    assert "rigid_offsets_not_supported" not in engineering.limitations
    assert "distributed_member_loads_not_supported" not in engineering.limitations
