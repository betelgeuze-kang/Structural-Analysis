from __future__ import annotations

from dataclasses import dataclass
import json
import math

import numpy as np
import pytest

from structural_analysis.elements.corotational_frame2d import (
    corotational_frame2d_response,
)
from structural_analysis.elements.corotational_frame2d_basic import (
    COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY,
    COROTATIONAL_FRAME2D_BASIC_DEFORMATION_ORDER,
    COROTATIONAL_FRAME2D_BASIC_FORCE_ORDER,
    COROTATIONAL_FRAME2D_GLOBAL_DOF_ORDER,
    Frame2DBasicConstitutiveResponse,
    assemble_corotational_frame2d_global_response,
    corotational_frame2d_basic_kinematics,
)


COORDINATES = np.asarray([[0.2, -0.1], [2.1, 0.7]], dtype=np.float64)
DISPLACEMENTS = np.asarray(
    [0.04, -0.03, 0.17, -0.08, 0.11, -0.09],
    dtype=np.float64,
)


@dataclass(frozen=True)
class _BasicResponse:
    basic_forces: np.ndarray
    consistent_tangent_basic: np.ndarray


def _kinematics(displacements: np.ndarray):
    return corotational_frame2d_basic_kinematics(
        node_coordinates_m=COORDINATES,
        element_displacements=displacements,
    )


def test_basic_deformation_gradient_matches_centered_difference() -> None:
    response = _kinematics(DISPLACEMENTS)
    epsilon = 1.0e-7
    finite_difference = np.zeros((3, 6), dtype=np.float64)
    for column in range(6):
        forward = DISPLACEMENTS.copy()
        backward = DISPLACEMENTS.copy()
        forward[column] += epsilon
        backward[column] -= epsilon
        finite_difference[:, column] = (
            _kinematics(forward).basic_deformations
            - _kinematics(backward).basic_deformations
        ) / (2.0 * epsilon)

    np.testing.assert_allclose(
        response.basic_deformation_gradient_global,
        finite_difference,
        rtol=2.0e-8,
        atol=2.0e-9,
    )


def test_basic_deformation_hessians_match_gradient_jacobian() -> None:
    response = _kinematics(DISPLACEMENTS)
    epsilon = 1.0e-6
    finite_difference = np.zeros((3, 6, 6), dtype=np.float64)
    for column in range(6):
        forward = DISPLACEMENTS.copy()
        backward = DISPLACEMENTS.copy()
        forward[column] += epsilon
        backward[column] -= epsilon
        finite_difference[:, :, column] = (
            _kinematics(forward).basic_deformation_gradient_global
            - _kinematics(backward).basic_deformation_gradient_global
        ) / (2.0 * epsilon)

    np.testing.assert_allclose(
        response.basic_deformation_hessians_global,
        finite_difference,
        rtol=2.0e-7,
        atol=2.0e-10,
    )
    np.testing.assert_allclose(
        response.basic_deformation_hessians_global,
        response.basic_deformation_hessians_global.transpose(0, 2, 1),
        rtol=0.0,
        atol=1.0e-15,
    )


def test_finite_rigid_motion_has_zero_basic_deformations() -> None:
    rigid_rotation = 2.2
    translation = np.asarray([0.4, -0.3], dtype=np.float64)
    rotation = np.asarray(
        [
            [math.cos(rigid_rotation), -math.sin(rigid_rotation)],
            [math.sin(rigid_rotation), math.cos(rigid_rotation)],
        ],
        dtype=np.float64,
    )
    current_coordinates = COORDINATES @ rotation.T + translation
    displacements = np.asarray(
        [
            *(current_coordinates[0] - COORDINATES[0]),
            rigid_rotation,
            *(current_coordinates[1] - COORDINATES[1]),
            rigid_rotation,
        ],
        dtype=np.float64,
    )

    response = _kinematics(displacements)

    assert response.current_length_m == pytest.approx(response.initial_length_m)
    assert response.chord_rotation_change_rad == pytest.approx(rigid_rotation)
    np.testing.assert_allclose(response.basic_deformations, 0.0, atol=1.0e-15)


def test_angle_change_uses_documented_principal_branch_without_unwrapping() -> None:
    rigid_rotation = 3.5
    rotation = np.asarray(
        [
            [math.cos(rigid_rotation), -math.sin(rigid_rotation)],
            [math.sin(rigid_rotation), math.cos(rigid_rotation)],
        ],
        dtype=np.float64,
    )
    current_coordinates = COORDINATES @ rotation.T
    displacements = np.asarray(
        [
            *(current_coordinates[0] - COORDINATES[0]),
            rigid_rotation,
            *(current_coordinates[1] - COORDINATES[1]),
            rigid_rotation,
        ],
        dtype=np.float64,
    )

    response = _kinematics(displacements)
    principal_rotation = math.atan2(
        math.sin(rigid_rotation),
        math.cos(rigid_rotation),
    )

    assert response.chord_rotation_change_rad == pytest.approx(principal_rotation)
    assert response.basic_deformations[1:] == pytest.approx((2.0 * math.pi,) * 2)
    assert "principal_atan2" in COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY


def test_generic_basic_response_recovers_elastic_force_and_exact_tangent() -> None:
    modulus = 72_000_000.0
    area = 6.0e-4
    second_moment = 2.0e-8
    kinematics = _kinematics(DISPLACEMENTS)
    length = kinematics.initial_length_m
    basic_tangent = np.asarray(
        [
            [modulus * area / length, 0.0, 0.0],
            [
                0.0,
                4.0 * modulus * second_moment / length,
                2.0 * modulus * second_moment / length,
            ],
            [
                0.0,
                2.0 * modulus * second_moment / length,
                4.0 * modulus * second_moment / length,
            ],
        ],
        dtype=np.float64,
    )
    basic_response = _BasicResponse(
        basic_forces=basic_tangent @ kinematics.basic_deformations,
        consistent_tangent_basic=basic_tangent,
    )

    assert isinstance(basic_response, Frame2DBasicConstitutiveResponse)
    recovered = assemble_corotational_frame2d_global_response(
        kinematics=kinematics,
        basic_response=basic_response,
    )
    elastic = corotational_frame2d_response(
        node_coordinates_m=COORDINATES,
        element_displacements=DISPLACEMENTS,
        youngs_modulus_kn_per_m2=modulus,
        area_m2=area,
        second_moment_m4=second_moment,
    )

    np.testing.assert_allclose(
        recovered.internal_force_global,
        elastic.internal_force_global,
        rtol=0.0,
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        recovered.consistent_tangent_global,
        elastic.consistent_tangent_global,
        rtol=0.0,
        atol=1.0e-10,
    )
    np.testing.assert_allclose(
        recovered.consistent_tangent_global,
        recovered.material_tangent_global + recovered.geometric_tangent_global,
        rtol=0.0,
        atol=1.0e-12,
    )


def test_public_metadata_serialization_and_arrays_are_immutable() -> None:
    kinematics = _kinematics(DISPLACEMENTS)
    basic_response = _BasicResponse(
        basic_forces=np.asarray([13.0, -2.0, 5.0]),
        consistent_tangent_basic=np.diag([100.0, 20.0, 30.0]),
    )
    recovered = assemble_corotational_frame2d_global_response(
        kinematics=kinematics,
        basic_response=basic_response,
    )

    assert COROTATIONAL_FRAME2D_GLOBAL_DOF_ORDER == (
        "ux_i_m",
        "uy_i_m",
        "theta_i_rad",
        "ux_j_m",
        "uy_j_m",
        "theta_j_rad",
    )
    assert len(COROTATIONAL_FRAME2D_BASIC_DEFORMATION_ORDER) == 3
    assert len(COROTATIONAL_FRAME2D_BASIC_FORCE_ORDER) == 3
    for array in (
        kinematics.current_direction,
        kinematics.basic_deformations,
        kinematics.basic_deformation_gradient_global,
        kinematics.basic_deformation_hessians_global,
        recovered.internal_force_global,
        recovered.material_tangent_global,
        recovered.geometric_tangent_global,
        recovered.consistent_tangent_global,
    ):
        assert not array.flags.writeable
    with pytest.raises(ValueError):
        kinematics.basic_deformations[0] = 0.0
    with pytest.raises(ValueError):
        recovered.consistent_tangent_global[0, 0] = 0.0
    json.dumps(kinematics.to_dict(), allow_nan=False, sort_keys=True)
    json.dumps(recovered.to_dict(), allow_nan=False, sort_keys=True)


@pytest.mark.parametrize(
    ("coordinates", "displacements", "message"),
    [
        ([[0.0, 0.0]], np.zeros(6), "2x2"),
        (COORDINATES, np.zeros(5), "six-vector"),
        (np.zeros((2, 2)), np.zeros(6), "must not coincide"),
        (
            [[0.0, 0.0], [1.0, 0.0]],
            [0.0, 0.0, 0.0, -1.0, 0.0, 0.0],
            "current chord is degenerate",
        ),
    ],
)
def test_invalid_kinematic_inputs_fail_closed(
    coordinates,
    displacements,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        corotational_frame2d_basic_kinematics(
            node_coordinates_m=coordinates,
            element_displacements=displacements,
        )


def test_invalid_basic_response_fails_closed() -> None:
    kinematics = _kinematics(DISPLACEMENTS)

    with pytest.raises(ValueError, match="Frame2DBasicConstitutiveResponse"):
        assemble_corotational_frame2d_global_response(
            kinematics=kinematics,
            basic_response=object(),
        )
    with pytest.raises(ValueError, match="basic_forces"):
        assemble_corotational_frame2d_global_response(
            kinematics=kinematics,
            basic_response=_BasicResponse(
                basic_forces=np.zeros(2),
                consistent_tangent_basic=np.eye(3),
            ),
        )
    with pytest.raises(ValueError, match="consistent_tangent_basic"):
        assemble_corotational_frame2d_global_response(
            kinematics=kinematics,
            basic_response=_BasicResponse(
                basic_forces=np.zeros(3),
                consistent_tangent_basic=np.eye(2),
            ),
        )
