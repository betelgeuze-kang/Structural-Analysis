from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.benchmark.lee_frame import (
    corotational_frame_element_response as legacy_frame_response,
)
from structural_analysis.elements.corotational_frame2d import (
    corotational_frame2d_response,
)


COORDINATES = np.array([[0.0, 0.0], [2.0, 0.5]], dtype=np.float64)
DISPLACEMENTS = np.array(
    [0.02, -0.01, 0.03, -0.04, 0.06, -0.02],
    dtype=np.float64,
)
MODULUS = 72_000_000.0
AREA = 6.0e-4
SECOND_MOMENT = 2.0e-8


def _evaluate(displacements: np.ndarray):
    return corotational_frame2d_response(
        node_coordinates_m=COORDINATES,
        element_displacements=displacements,
        youngs_modulus_kn_per_m2=MODULUS,
        area_m2=AREA,
        second_moment_m4=SECOND_MOMENT,
    )


def test_extracted_kernel_matches_existing_lee_frame_element() -> None:
    legacy = legacy_frame_response(
        node_coordinates_m=COORDINATES,
        element_displacements=DISPLACEMENTS,
        youngs_modulus_kn_per_m2=MODULUS,
        area_m2=AREA,
        second_moment_m4=SECOND_MOMENT,
    )
    extracted = _evaluate(DISPLACEMENTS)

    assert extracted.strain_energy_kn_m == pytest.approx(
        legacy.strain_energy_kn_m,
        rel=0.0,
        abs=1.0e-14,
    )
    assert extracted.initial_length_m == pytest.approx(legacy.initial_length_m)
    assert extracted.current_length_m == pytest.approx(legacy.current_length_m)
    assert extracted.chord_rotation_change_rad == pytest.approx(
        legacy.chord_rotation_change_rad
    )
    assert extracted.basic_deformations == pytest.approx(legacy.basic_deformations)
    assert extracted.basic_forces == pytest.approx(legacy.basic_forces)
    np.testing.assert_allclose(
        extracted.internal_force_global,
        legacy.internal_force_global,
        rtol=0.0,
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        extracted.consistent_tangent_global,
        legacy.consistent_tangent_global,
        rtol=0.0,
        atol=1.0e-10,
    )


def test_internal_force_is_energy_gradient() -> None:
    response = _evaluate(DISPLACEMENTS)
    epsilon = 1.0e-7
    finite_difference = np.zeros(6, dtype=np.float64)
    for index in range(6):
        forward = DISPLACEMENTS.copy()
        backward = DISPLACEMENTS.copy()
        forward[index] += epsilon
        backward[index] -= epsilon
        finite_difference[index] = (
            _evaluate(forward).strain_energy_kn_m
            - _evaluate(backward).strain_energy_kn_m
        ) / (2.0 * epsilon)

    scale = max(
        1.0,
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(np.linalg.norm(response.internal_force_global, ord=np.inf)),
    )
    error = float(
        np.linalg.norm(
            finite_difference - response.internal_force_global,
            ord=np.inf,
        )
        / scale
    )
    assert error <= 1.0e-7


def test_consistent_tangent_is_internal_force_jacobian() -> None:
    response = _evaluate(DISPLACEMENTS)
    epsilon = 1.0e-7
    finite_difference = np.zeros((6, 6), dtype=np.float64)
    for column in range(6):
        forward = DISPLACEMENTS.copy()
        backward = DISPLACEMENTS.copy()
        forward[column] += epsilon
        backward[column] -= epsilon
        finite_difference[:, column] = (
            _evaluate(forward).internal_force_global
            - _evaluate(backward).internal_force_global
        ) / (2.0 * epsilon)

    scale = max(
        1.0,
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(
            np.linalg.norm(
                response.consistent_tangent_global,
                ord=np.inf,
            )
        ),
    )
    error = float(
        np.linalg.norm(
            finite_difference - response.consistent_tangent_global,
            ord=np.inf,
        )
        / scale
    )
    assert error <= 2.0e-7
    np.testing.assert_allclose(
        response.consistent_tangent_global,
        response.consistent_tangent_global.T,
        rtol=0.0,
        atol=1.0e-12,
    )


def test_finite_rigid_translation_and_rotation_has_zero_strain_energy() -> None:
    response = corotational_frame2d_response(
        node_coordinates_m=np.array([[0.0, 0.0], [2.0, 0.0]]),
        element_displacements=np.array(
            [
                1.0,
                -2.0,
                math.pi / 2.0,
                -1.0,
                0.0,
                math.pi / 2.0,
            ]
        ),
        youngs_modulus_kn_per_m2=MODULUS,
        area_m2=AREA,
        second_moment_m4=SECOND_MOMENT,
    )

    assert response.current_length_m == pytest.approx(2.0)
    assert response.chord_rotation_change_rad == pytest.approx(math.pi / 2.0)
    assert response.basic_deformations == pytest.approx(
        (0.0, 0.0, 0.0),
        abs=1.0e-14,
    )
    assert response.strain_energy_kn_m == pytest.approx(0.0, abs=1.0e-14)
    np.testing.assert_allclose(response.internal_force_global, 0.0, atol=1.0e-12)


def test_response_arrays_are_immutable() -> None:
    response = _evaluate(DISPLACEMENTS)
    assert not response.internal_force_global.flags.writeable
    assert not response.consistent_tangent_global.flags.writeable
    with pytest.raises(ValueError):
        response.internal_force_global[0] = 0.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"youngs_modulus_kn_per_m2": True}, "youngs_modulus"),
        ({"youngs_modulus_kn_per_m2": 0.0}, "youngs_modulus"),
        ({"area_m2": -1.0}, "area_m2"),
        ({"second_moment_m4": np.inf}, "second_moment_m4"),
        ({"node_coordinates_m": [[0.0, 0.0]]}, "2x2"),
        ({"element_displacements": np.zeros(5)}, "six-vector"),
        (
            {"node_coordinates_m": [[0.0, 0.0], [0.0, 0.0]]},
            "must not coincide",
        ),
        (
            {
                "node_coordinates_m": [[0.0, 0.0], [1.0, 0.0]],
                "element_displacements": [0.0, 0.0, 0.0, -1.0, 0.0, 0.0],
            },
            "current chord is degenerate",
        ),
    ],
)
def test_invalid_inputs_fail_closed(overrides, message) -> None:
    arguments = {
        "node_coordinates_m": COORDINATES,
        "element_displacements": DISPLACEMENTS,
        "youngs_modulus_kn_per_m2": MODULUS,
        "area_m2": AREA,
        "second_moment_m4": SECOND_MOMENT,
    }
    arguments.update(overrides)
    with pytest.raises(ValueError, match=message):
        corotational_frame2d_response(**arguments)


@pytest.mark.parametrize("axial_strain", [-1.0e-3, 0.0, 1.0e-3])
@pytest.mark.parametrize("second_moment", [2.0e-8, 2.0e-4])
@pytest.mark.parametrize(
    ("initial_angle", "rigid_rotation"),
    [
        (0.0, 0.0),
        (math.pi - 0.02, 0.05),
        (-math.pi + 0.02, -0.05),
        (0.6, 2.0),
    ],
    ids=["horizontal", "positive-atan2-cut", "negative-atan2-cut", "large-rotation"],
)
def test_axial_prestress_matches_closed_form_under_rigid_motion(
    axial_strain: float,
    second_moment: float,
    initial_angle: float,
    rigid_rotation: float,
) -> None:
    """Analytic local beam response, independently rotated into global axes.

    The strain stays small while rotations are finite. The two cut cases cross
    the absolute atan2 cut, but not the relative-angle branch at +/- pi.
    Compression can make the free-element tangent indefinite; positivity or a
    finite condition number is not assumed for its rigid translation modes.
    This stateless elastic check does not validate buckling loads, a global
    solver, cyclic history, or multi-turn angle unwrapping.
    """
    length = 2.0
    extension = length * axial_strain
    current_length = length + extension
    current_angle = initial_angle + rigid_rotation
    initial_direction = np.array([math.cos(initial_angle), math.sin(initial_angle)])
    current_direction = np.array([math.cos(current_angle), math.sin(current_angle)])
    translation = np.array([0.25, -0.5])
    coordinates = np.array([[0.0, 0.0], length * initial_direction])
    displacement_j = translation + current_length * current_direction - coordinates[1]
    displacements = np.array(
        [*translation, rigid_rotation, *displacement_j, rigid_rotation]
    )
    response = corotational_frame2d_response(
        node_coordinates_m=coordinates,
        element_displacements=displacements,
        youngs_modulus_kn_per_m2=MODULUS,
        area_m2=AREA,
        second_moment_m4=second_moment,
    )

    # Closed-form axial energy and prestress, without kinematics/assembly helpers.
    axial_stiffness = MODULUS * AREA / length
    axial_force = axial_stiffness * extension
    expected_energy = 0.5 * axial_stiffness * extension**2
    expected_force_local = np.array([-axial_force, 0.0, 0.0, axial_force, 0.0, 0.0])

    # A transverse chord increment changes its angle by dy/l and its length by
    # dy**2/(2*l). Thus N/l adds geometric stiffness to the elastic 12*EI/(L*l**2).
    flexural_stiffness = MODULUS * second_moment / length
    transverse = 12.0 * flexural_stiffness / current_length**2
    transverse += axial_force / current_length
    coupling = 6.0 * flexural_stiffness / current_length
    end_rotation = 4.0 * flexural_stiffness
    cross_rotation = 2.0 * flexural_stiffness
    expected_tangent_local = np.array(
        [
            [axial_stiffness, 0.0, 0.0, -axial_stiffness, 0.0, 0.0],
            [0.0, transverse, coupling, 0.0, -transverse, coupling],
            [0.0, coupling, end_rotation, 0.0, -coupling, cross_rotation],
            [-axial_stiffness, 0.0, 0.0, axial_stiffness, 0.0, 0.0],
            [0.0, -transverse, -coupling, 0.0, transverse, -coupling],
            [0.0, coupling, cross_rotation, 0.0, -coupling, end_rotation],
        ]
    )
    cosine, sine = current_direction
    local_to_global = np.eye(6)
    planar_rotation = np.array([[cosine, -sine], [sine, cosine]])
    local_to_global[:2, :2] = planar_rotation
    local_to_global[3:5, 3:5] = planar_rotation
    expected_force = local_to_global @ expected_force_local
    expected_tangent = local_to_global @ expected_tangent_local @ local_to_global.T

    assert np.isfinite(response.strain_energy_kn_m)
    assert np.all(np.isfinite(response.internal_force_global))
    assert np.all(np.isfinite(response.consistent_tangent_global))
    np.testing.assert_allclose(
        response.basic_deformations, [extension, 0.0, 0.0], rtol=0.0, atol=1.0e-14
    )
    np.testing.assert_allclose(
        response.strain_energy_kn_m, expected_energy, rtol=2.0e-12, atol=1.0e-14
    )
    np.testing.assert_allclose(
        response.internal_force_global, expected_force, rtol=2.0e-12, atol=1.0e-10
    )
    np.testing.assert_allclose(
        response.consistent_tangent_global,
        expected_tangent,
        rtol=2.0e-12,
        atol=1.0e-10,
    )
    translations = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]] * 2)
    np.testing.assert_allclose(
        response.consistent_tangent_global @ translations, 0.0, rtol=0.0, atol=1.0e-10
    )
