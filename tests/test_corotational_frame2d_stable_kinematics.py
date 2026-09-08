"""High-precision kinematic references; no material or solver gate changes."""

from __future__ import annotations

from decimal import Decimal, localcontext
import math

import numpy as np
import pytest

from structural_analysis.elements.corotational_frame2d_basic import (
    COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY,
    corotational_frame2d_basic_kinematics,
)


def _decimal_atan(value: Decimal) -> Decimal:
    """Independent absolute-angle reference via half angles and a power series."""
    multiplier = 1
    while abs(value) > Decimal("0.1"):
        value = value / (1 + (1 + value * value).sqrt())
        multiplier *= 2
    term = total = value
    for index in range(1, 150):
        term *= -value * value
        total += term / (2 * index + 1)
    return total * multiplier


def _decimal_reference(chord, relative_translation) -> tuple[float, float]:
    with localcontext() as context:
        context.prec = 90
        x, y, dx, dy = map(Decimal.from_float, (*chord, *relative_translation))
        # Subtract absolute lengths and angles at 90 digits, independently of
        # the rationalized length and relative cross/dot production expressions.
        extension = ((x + dx) ** 2 + (y + dy) ** 2).sqrt() - (x * x + y * y).sqrt()
        angle = _decimal_atan((y + dy) / (x + dx)) - _decimal_atan(y / x)
        return float(extension), float(angle)


def _kinematics(chord, relative_translation=(0.0, 0.0), rotations=(0.0, 0.0)):
    return corotational_frame2d_basic_kinematics(
        node_coordinates_m=((0.0, 0.0), chord),
        element_displacements=(
            0.0,
            0.0,
            rotations[0],
            *relative_translation,
            rotations[1],
        ),
    )


@pytest.mark.parametrize(
    ("chord", "delta"),
    (
        ((1.0, 0.0), (1.0e-17, 0.0)),
        ((1.0, 0.0), (-1.0e-17, 0.0)),
        ((1.0, 1.0), (1.0e-17, 1.0e-17)),
        ((1.0, 1.0), (-1.0e-17, -1.0e-17)),
        ((1.0, 1.0), (0.0, 1.0e-17)),
        ((0.1, 0.1), (0.0, 1.0e-17)),
        ((0.1, 0.1), (0.0, -1.0e-17)),
    ),
)
def test_tiny_extension_matches_independent_decimal_length_difference(chord, delta):
    expected, _ = _decimal_reference(chord, delta)
    observed = float(_kinematics(chord, delta).basic_deformations[0])
    legacy = float(np.linalg.norm(np.asarray(chord) + delta) - np.linalg.norm(chord))

    assert expected != 0.0
    assert abs(legacy - expected) > 0.1 * abs(expected)
    assert observed == pytest.approx(expected, rel=8.0e-16, abs=0.0)


@pytest.mark.parametrize(
    ("chord", "delta"),
    (
        ((1.0, 1.0), (0.0, 1.0e-17)),
        ((1.0, 1.0), (0.0, -1.0e-17)),
        ((0.1, 0.1), (0.0, 1.0e-17)),
        ((0.1, 0.1), (0.0, -1.0e-17)),
    ),
)
def test_tiny_relative_angle_matches_independent_decimal_absolute_angles(chord, delta):
    _, expected = _decimal_reference(chord, delta)
    current = np.asarray(chord) + delta
    raw_angle = math.atan2(current[1], current[0]) - math.atan2(chord[1], chord[0])
    legacy = math.atan2(math.sin(raw_angle), math.cos(raw_angle))
    observed = _kinematics(chord, delta)

    assert expected != 0.0
    assert abs(legacy - expected) > 0.1 * abs(expected)
    assert observed.chord_rotation_change_rad == pytest.approx(
        expected, rel=8.0e-16, abs=0.0
    )
    np.testing.assert_array_equal(
        observed.basic_deformations[1:],
        [-observed.chord_rotation_change_rad] * 2,
    )


@pytest.mark.parametrize("chord", ((1.0, 0.0), (1.0, 1.0), (-1.0, 2.0)))
def test_zero_displacement_remains_exactly_zero(chord):
    observed = _kinematics(chord)
    np.testing.assert_array_equal(observed.basic_deformations, np.zeros(3))
    assert observed.chord_rotation_change_rad == 0.0
    assert observed.current_length_m == observed.initial_length_m


@pytest.mark.parametrize(
    "chord",
    (
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
        (1.0, 1.0),
        (-1.0, 1.0),
        (-1.0, -1.0),
        (1.0, -1.0),
    ),
)
def test_exact_half_turn_retains_existing_signed_principal_branch(chord):
    delta = -2.0 * np.asarray(chord)
    current = np.asarray(chord) + delta
    raw_angle = math.atan2(current[1], current[0]) - math.atan2(chord[1], chord[0])
    expected = math.atan2(math.sin(raw_angle), math.cos(raw_angle))
    observed = _kinematics(chord, delta, (expected, expected))

    assert abs(expected) == math.pi
    assert observed.chord_rotation_change_rad == expected
    np.testing.assert_allclose(observed.basic_deformations, 0.0, atol=1.0e-15)
    assert COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY == (
        "principal_atan2_current_minus_initial.v1"
    )


@pytest.mark.parametrize("relative_y", (-1.0e-12, 1.0e-12))
def test_chords_on_either_side_of_half_turn_keep_their_branch(relative_y):
    observed = _kinematics((1.0, 0.0), (-2.0, relative_y))
    assert observed.chord_rotation_change_rad == math.atan2(relative_y, -1.0)


def test_scaled_rationalization_does_not_overflow_at_large_finite_half_turn():
    observed = _kinematics((1.0e154, 0.0), (-2.0e154, 0.0), (math.pi, math.pi))
    assert observed.current_length_m == observed.initial_length_m == 1.0e154
    np.testing.assert_array_equal(observed.basic_deformations, np.zeros(3))


def test_small_relative_extension_is_retained_on_a_large_finite_chord():
    observed = _kinematics((1.0e154, 0.0), (1.0e137, 0.0))
    assert observed.basic_deformations[0] == pytest.approx(1.0e137, rel=8.0e-16)
    assert observed.chord_rotation_change_rad == 0.0


@pytest.mark.parametrize("direction", ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)))
def test_evaluation_switch_preserves_decimal_accuracy_and_continuity(direction):
    chord = (1.0, 1.0)
    length = math.sqrt(2.0)
    switch = math.sqrt(math.sqrt(np.finfo(np.float64).eps)) * length
    observed_values = []
    expected_values = []
    for factor in (1.0 - 1.0e-6, 1.0 + 1.0e-6):
        delta = tuple(component * switch * factor for component in direction)
        expected = _decimal_reference(chord, delta)
        response = _kinematics(chord, delta)
        observed = (
            float(response.basic_deformations[0]),
            response.chord_rotation_change_rad,
        )
        observed_values.append(observed)
        expected_values.append(expected)
        # The switch joins equivalent formulas within float64 rounding error,
        # with no strain/force threshold or modification of the exact tangent.
        np.testing.assert_allclose(
            observed,
            expected,
            rtol=0.0,
            atol=4.0 * np.finfo(np.float64).eps * length,
        )
    observed_change = np.subtract(observed_values[1], observed_values[0])
    expected_change = np.subtract(expected_values[1], expected_values[0])
    np.testing.assert_allclose(
        observed_change,
        expected_change,
        rtol=0.0,
        atol=8.0 * np.finfo(np.float64).eps * length,
    )
