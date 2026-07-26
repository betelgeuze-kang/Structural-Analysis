"""Focused tests for P2 shear, warping, and imperfection candidates."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from structural_analysis.assembly.initial_imperfection import (
    INITIAL_IMPERFECTION_PROFILE,
    sinusoidal_member_imperfection_mesh,
)
from structural_analysis.elements.frame3d import FrameProps, local_frame_stiffness
from structural_analysis.elements.corotational_frame3d import (
    COROTATIONAL_FRAME3D_PROFILE,
    corotational_frame3d_response,
    corotational_frame3d_strain_energy,
)
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
    local_timoshenko_frame_stiffness,
    timoshenko_basic_bending_stiffness,
)
from structural_analysis.elements.torsion_warping import (
    TorsionWarpingProperties,
    condensed_twist_stiffness,
    local_torsion_warping_stiffness,
    torsion_warping_response,
)


def _frame_props() -> FrameProps:
    return FrameProps(
        area_m2=0.02,
        e_n_per_m2=2.0e8,
        g_n_per_m2=8.0e7,
        iy_m4=5.0e-5,
        iz_m4=8.0e-5,
        j_m4=1.0e-5,
    )


def test_timoshenko_cantilever_matches_bending_plus_shear_closed_form() -> None:
    props = _frame_props()
    length = 2.0
    shear_area_y = 0.015
    section = TimoshenkoFrame3DSection(props, shear_area_y, 0.012)
    stiffness = local_timoshenko_frame_stiffness(section, length)
    free_stiffness = stiffness[6:12, 6:12]
    load = np.zeros(6, dtype=np.float64)
    load[1] = 10.0
    displacement = np.linalg.solve(free_stiffness, load)
    expected = (
        10.0 * length**3 / (3.0 * props.e_n_per_m2 * props.iz_m4)
        + 10.0 * length / (props.g_n_per_m2 * shear_area_y)
    )

    assert displacement[1] == pytest.approx(expected, rel=1.0e-13)
    assert np.array_equal(stiffness, stiffness.T)
    assert np.count_nonzero(np.linalg.eigvalsh(stiffness) > 1.0e-7) == 6
    assert stiffness.flags.writeable is False


def test_timoshenko_converges_to_euler_bernoulli_and_basic_matrix_is_positive() -> None:
    props = _frame_props()
    length = 3.0
    section = TimoshenkoFrame3DSection(props, 1.0e12, 1.0e12)
    timoshenko = local_timoshenko_frame_stiffness(section, length)
    euler = local_frame_stiffness(props, length)
    basic = timoshenko_basic_bending_stiffness(
        flexural_rigidity_kn_m2=props.e_n_per_m2 * props.iz_m4,
        shear_rigidity_kn=props.g_n_per_m2 * 0.015,
        length_m=length,
    )

    np.testing.assert_allclose(timoshenko, euler, rtol=2.0e-14, atol=1.0e-8)
    assert float(np.min(np.linalg.eigvalsh(basic))) > 0.0
    assert basic.flags.writeable is False


def test_warping_kernel_recovers_saint_venant_after_gradient_condensation() -> None:
    properties = TorsionWarpingProperties(
        shear_modulus_kn_per_m2=8.0e7,
        torsional_constant_m4=2.0e-5,
        elastic_modulus_kn_per_m2=2.0e8,
        warping_constant_m6=0.0,
    )
    length = 4.0
    tangent = local_torsion_warping_stiffness(properties, length)
    condensed = condensed_twist_stiffness(tangent)
    expected = (
        properties.shear_modulus_kn_per_m2
        * properties.torsional_constant_m4
        / length
        * np.asarray([[1.0, -1.0], [-1.0, 1.0]])
    )

    np.testing.assert_allclose(condensed, expected, rtol=1.0e-13, atol=1.0e-10)
    assert np.array_equal(tangent, tangent.T)
    assert tangent.flags.writeable is False


def test_warping_energy_is_zero_for_rigid_twist_and_exact_for_linear_twist() -> None:
    properties = TorsionWarpingProperties(8.0e7, 2.0e-5, 2.0e8, 3.0e-7)
    length = 4.0
    rigid = torsion_warping_response(
        properties,
        length,
        [0.2, 0.0, 0.2, 0.0],
    )
    twist_gradient = 0.03
    linear = torsion_warping_response(
        properties,
        length,
        [0.0, twist_gradient, twist_gradient * length, twist_gradient],
    )
    expected = 0.5 * (
        properties.shear_modulus_kn_per_m2
        * properties.torsional_constant_m4
        * twist_gradient**2
        * length
    )

    assert rigid.strain_energy_kn_m == pytest.approx(0.0, abs=1.0e-12)
    assert np.linalg.norm(rigid.generalized_forces, ord=np.inf) <= 1.0e-10
    assert linear.strain_energy_kn_m == pytest.approx(expected, rel=1.0e-13)
    assert linear.tangent.flags.writeable is False


def test_sinusoidal_initial_imperfection_is_explicit_oriented_and_hashed() -> None:
    mesh = sinusoidal_member_imperfection_mesh(
        [1.0, 2.0, 3.0],
        [5.0, 2.0, 3.0],
        element_count=4,
        local_y_amplitude_m=0.004,
        local_z_amplitude_m=-0.003,
        roll_deg=30.0,
    )
    offsets = mesh.imperfect_coordinates_m - mesh.nominal_coordinates_m

    assert mesh.profile == INITIAL_IMPERFECTION_PROFILE
    np.testing.assert_array_equal(offsets[[0, -1]], np.zeros((2, 3)))
    assert np.linalg.norm(offsets[2]) == pytest.approx(0.005)
    assert mesh.mesh_hash.startswith("sha256:")
    assert mesh.nominal_coordinates_m.flags.writeable is False
    assert mesh.imperfect_coordinates_m.flags.writeable is False
    assert mesh.to_manifest()["mesh_hash"] == mesh.mesh_hash


def test_frame3d_candidates_reject_implicit_or_unbounded_properties() -> None:
    props = _frame_props()
    with pytest.raises(ValueError, match="effective_shear_area_y_m2"):
        TimoshenkoFrame3DSection(props, 0.0, 0.01)
    with pytest.raises(ValueError, match="warping_constant_m6"):
        TorsionWarpingProperties(8.0e7, 2.0e-5, 2.0e8, -1.0)
    with pytest.raises(ValueError, match="L/20"):
        sinusoidal_member_imperfection_mesh(
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            element_count=4,
            local_y_amplitude_m=0.1,
        )


def test_corotational_frame3d_zero_state_matches_timoshenko_tangent() -> None:
    props = _frame_props()
    section = TimoshenkoFrame3DSection(props, 0.015, 0.012)
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])

    response = corotational_frame3d_response(
        node_coordinates_m=coordinates,
        element_displacements=np.zeros(12),
        section=section,
    )
    reference = local_timoshenko_frame_stiffness(section, 2.0)

    assert response.profile == COROTATIONAL_FRAME3D_PROFILE
    assert response.strain_energy_kn_m == 0.0
    assert np.max(np.abs(response.internal_force_global)) <= 1.0e-8
    np.testing.assert_allclose(
        response.consistent_tangent_global,
        reference,
        rtol=5.0e-8,
        atol=0.1,
    )
    assert np.array_equal(
        response.consistent_tangent_global,
        response.consistent_tangent_global.T,
    )


def test_corotational_frame3d_is_objective_under_finite_rigid_motion() -> None:
    section = TimoshenkoFrame3DSection(_frame_props(), 0.015, 0.012)
    coordinates = np.asarray([[1.0, 2.0, 3.0], [2.5, 3.0, 4.0]])
    rotation_vector = np.asarray([0.3, -0.2, 0.4])
    rotation = Rotation.from_rotvec(rotation_vector).as_matrix()
    translation = np.asarray([0.7, -0.3, 0.2])
    moved = (rotation @ coordinates.T).T + translation
    displacement = np.zeros(12)
    displacement[0:3] = moved[0] - coordinates[0]
    displacement[6:9] = moved[1] - coordinates[1]
    displacement[3:6] = rotation_vector
    displacement[9:12] = rotation_vector

    response = corotational_frame3d_response(
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        section=section,
        local_axis_roll_deg=17.0,
    )

    assert response.strain_energy_kn_m <= 1.0e-20
    assert np.max(np.abs(response.basic_deformations)) <= 1.0e-12
    assert np.max(np.abs(response.internal_force_global)) <= 1.0e-7


def test_corotational_frame3d_force_and_tangent_derive_from_same_energy() -> None:
    section = TimoshenkoFrame3DSection(_frame_props(), 0.015, 0.012)
    coordinates = np.asarray([[0.2, -0.1, 0.3], [2.1, 0.7, 1.2]])
    displacement = np.asarray(
        [
            0.01,
            -0.02,
            0.015,
            0.03,
            -0.02,
            0.01,
            0.04,
            0.025,
            -0.01,
            -0.015,
            0.025,
            0.035,
        ]
    )
    response = corotational_frame3d_response(
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        section=section,
        local_axis_roll_deg=13.0,
    )

    for index in (0, 1, 3, 7, 10):
        step = 5.0e-7 * (
            max(response.initial_length_m, 1.0) if index % 6 < 3 else 1.0
        )
        plus = displacement.copy()
        minus = displacement.copy()
        plus[index] += step
        minus[index] -= step
        finite_difference = (
            corotational_frame3d_strain_energy(
                node_coordinates_m=coordinates,
                element_displacements=plus,
                section=section,
                local_axis_roll_deg=13.0,
            )
            - corotational_frame3d_strain_energy(
                node_coordinates_m=coordinates,
                element_displacements=minus,
                section=section,
                local_axis_roll_deg=13.0,
            )
        ) / (2.0 * step)
        assert response.internal_force_global[index] == pytest.approx(
            finite_difference,
            rel=1.0e-8,
            abs=1.0e-7,
        )

    column = 7
    step = 1.0e-5
    plus = displacement.copy()
    minus = displacement.copy()
    plus[column] += step
    minus[column] -= step
    plus_response = corotational_frame3d_response(
        node_coordinates_m=coordinates,
        element_displacements=plus,
        section=section,
        local_axis_roll_deg=13.0,
    )
    minus_response = corotational_frame3d_response(
        node_coordinates_m=coordinates,
        element_displacements=minus,
        section=section,
        local_axis_roll_deg=13.0,
    )
    finite_difference_column = (
        plus_response.internal_force_global - minus_response.internal_force_global
    ) / (2.0 * step)
    np.testing.assert_allclose(
        response.consistent_tangent_global[:, column],
        finite_difference_column,
        rtol=1.0e-5,
        atol=0.1,
    )
