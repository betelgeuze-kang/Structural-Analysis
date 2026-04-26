from __future__ import annotations

import numpy as np

from implementation.phase1.beam_column_nonlinear import (
    BeamColumnProperties,
    frame_2d_transformation_from_nodes,
    solve_beam_column_global_response,
    solve_beam_column_response,
    solve_beam_column_supported_response,
)


def test_frame_2d_transformation_from_nodes_is_orthonormal() -> None:
    transform = frame_2d_transformation_from_nodes(node_i=(0.0, 0.0), node_j=(3.0, 4.0))
    assert transform.shape == (6, 6)
    assert np.allclose(transform.T @ transform, np.eye(6), atol=1.0e-12)


def test_solve_beam_column_global_response_returns_symmetric_global_stiffness() -> None:
    props = BeamColumnProperties(length_m=5.0, area_m2=0.03, e_mpa=30000.0, iy_m4=0.05, yield_moment_kNm=220.0)
    deformation = np.array([0.0, 0.001, 0.01, 0.0005, -0.0015, -0.008], dtype=np.float64)
    result = solve_beam_column_global_response(
        props=props,
        deformation_global=deformation,
        node_i=(0.0, 0.0),
        node_j=(4.0, 3.0),
        axial_force_n=1.5e6,
        formulation="corotational_proxy",
    )
    assert result.global_stiffness.shape == (6, 6)
    assert np.allclose(result.global_stiffness, result.global_stiffness.T, atol=1.0e-9)
    assert result.local_response.drift_ratio > 0.0
    assert result.local_response.stability_index > 0.0
    assert result.local_response.strain_energy_n_m > 0.0
    assert result.local_response.final_end_moments_kNm.shape == (2,)
    assert np.linalg.norm(result.internal_force_global) > 0.0


def test_solve_beam_column_supported_response_balances_cantilever_reactions() -> None:
    props = BeamColumnProperties(length_m=5.0, area_m2=0.03, e_mpa=30000.0, iy_m4=0.05, yield_moment_kNm=1.0e6)
    result = solve_beam_column_supported_response(
        props=props,
        node_i=(0.0, 0.0),
        node_j=(5.0, 0.0),
        external_force_global=np.array([0.0, 0.0, 0.0, 0.0, -50_000.0, 0.0], dtype=np.float64),
        restrained_dofs=(0, 1, 2),
        formulation="force_based",
    )
    assert result.free_dofs == (3, 4, 5)
    assert np.allclose(result.displacement_global[list(result.restrained_dofs)], 0.0, atol=1.0e-12)
    assert result.displacement_global[4] < 0.0
    assert np.allclose(result.free_dof_residual, 0.0, atol=1.0e-6)
    assert np.isclose(result.reaction_global[1], 50_000.0, rtol=1.0e-6, atol=1.0e-3)
    assert np.isclose(result.reaction_global[2], 250_000.0, rtol=1.0e-6, atol=1.0e-3)


def test_solve_beam_column_supported_response_softens_after_yielding() -> None:
    load = np.array([0.0, 0.0, 0.0, 0.0, -50_000.0, 0.0], dtype=np.float64)
    elastic_like = BeamColumnProperties(
        length_m=5.0,
        area_m2=0.03,
        e_mpa=30000.0,
        iy_m4=0.05,
        yield_moment_kNm=1.0e6,
        hardening_ratio=0.05,
    )
    yielding = BeamColumnProperties(
        length_m=5.0,
        area_m2=0.03,
        e_mpa=30000.0,
        iy_m4=0.05,
        yield_moment_kNm=60.0,
        hardening_ratio=0.05,
    )
    elastic_result = solve_beam_column_supported_response(
        props=elastic_like,
        node_i=(0.0, 0.0),
        node_j=(5.0, 0.0),
        external_force_global=load,
        restrained_dofs=(0, 1, 2),
        formulation="force_based",
    )
    yielding_result = solve_beam_column_supported_response(
        props=yielding,
        node_i=(0.0, 0.0),
        node_j=(5.0, 0.0),
        external_force_global=load,
        restrained_dofs=(0, 1, 2),
        formulation="force_based",
        max_iterations=3,
    )
    assert yielding_result.member_response.local_response.yielded_end_count >= 1
    assert yielding_result.member_response.local_response.tangent_scale < 1.0
    assert abs(yielding_result.displacement_global[4]) > abs(elastic_result.displacement_global[4])


def test_solve_beam_column_response_tracks_end_specific_hinge_demand() -> None:
    props = BeamColumnProperties(
        length_m=6.0,
        area_m2=0.028,
        e_mpa=30000.0,
        iy_m4=0.09,
        yield_moment_kNm=140.0,
        hardening_ratio=0.05,
    )
    response = solve_beam_column_response(
        props=props,
        deformation_local=np.array([0.0, 0.0, 0.16, 0.0, 0.18, -0.02], dtype=np.float64),
        axial_force_n=2.4e6,
        include_geometric=True,
        formulation="force_based",
    )
    assert response.trial_end_moment_ratios[0] > response.trial_end_moment_ratios[1]
    assert response.end_tangent_scales[0] < response.end_tangent_scales[1]
    assert response.plastic_rotation_proxy_rad[0] >= response.plastic_rotation_proxy_rad[1]
    assert response.strain_energy_n_m > 0.0


def test_solve_beam_column_response_reports_stability_proxy_from_axial_force() -> None:
    props = BeamColumnProperties(length_m=7.0, area_m2=0.022, e_mpa=32000.0, iy_m4=0.052, yield_moment_kNm=260.0)
    deformation = np.array([0.0, 0.0, 0.08, 0.0, 0.21, -0.07], dtype=np.float64)
    low_axial = solve_beam_column_response(
        props=props,
        deformation_local=deformation,
        axial_force_n=0.8e6,
        include_geometric=True,
        formulation="corotational_proxy",
    )
    high_axial = solve_beam_column_response(
        props=props,
        deformation_local=deformation,
        axial_force_n=3.2e6,
        include_geometric=True,
        formulation="corotational_proxy",
    )
    assert high_axial.stability_index > low_axial.stability_index
    assert np.isclose(high_axial.elastic_critical_axial_force_n, low_axial.elastic_critical_axial_force_n)
    assert high_axial.elastic_critical_axial_force_n > 0.0
