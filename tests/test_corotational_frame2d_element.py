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
