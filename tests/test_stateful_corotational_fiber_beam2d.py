from __future__ import annotations

from dataclasses import replace
import json
import math

import numpy as np
import pytest

from structural_analysis.elements import (
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
    StatefulCorotationalFiberBeam2D,
    StatefulCorotationalFiberBeam2DState,
    StatefulFiberBeam2D,
)
from structural_analysis.materials import (
    make_rectangular_stateful_rc_fiber_section,
)


LENGTH = 3.0
COORDINATES = np.asarray([[0.0, 0.0], [LENGTH, 0.0]], dtype=np.float64)


def _element(
    coordinates=COORDINATES,
    *,
    element_id: str = "corotational-member-1",
) -> StatefulCorotationalFiberBeam2D:
    return StatefulCorotationalFiberBeam2D(
        node_coordinates_m=coordinates,
        section=make_rectangular_stateful_rc_fiber_section(),
        integration_order=3,
        element_id=element_id,
    )


def _uniform_basic_displacements(
    axial_strain: float,
    curvature_per_m: float,
) -> np.ndarray:
    return np.asarray(
        [
            0.0,
            0.0,
            -0.5 * curvature_per_m * LENGTH,
            axial_strain * LENGTH,
            0.0,
            0.5 * curvature_per_m * LENGTH,
        ],
        dtype=np.float64,
    )


def _rigid_displacements(
    coordinates: np.ndarray,
    angle_rad: float,
    *,
    translation=(0.3, -0.4),
) -> np.ndarray:
    rotation = np.asarray(
        [
            [math.cos(angle_rad), -math.sin(angle_rad)],
            [math.sin(angle_rad), math.cos(angle_rad)],
        ],
        dtype=np.float64,
    )
    current = coordinates @ rotation.T + np.asarray(translation)
    return np.asarray(
        [
            *(current[0] - coordinates[0]),
            angle_rad,
            *(current[1] - coordinates[1]),
            angle_rad,
        ],
        dtype=np.float64,
    )


def test_contract_projection_and_initial_state_are_deterministic() -> None:
    element = _element()
    repeated = _element()
    initial = element.initial_state()

    assert STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION.endswith(".v1")
    assert STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION.endswith(".v1")
    assert "nearest_integer_ties_to_positive_infinity" in (
        STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP
    )
    assert element.initial_length_m == LENGTH
    assert element.contract_hash == repeated.contract_hash
    assert initial.state_hash == repeated.initial_state().state_hash
    assert initial.step_index == 0
    assert initial.chord_rotation_change_rad == 0.0
    assert initial.element_displacements == (0.0,) * 6
    np.testing.assert_array_equal(
        element.basic_projection_to_local,
        np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        ),
    )
    assert not element.basic_projection_to_local.flags.writeable
    with pytest.raises(ValueError):
        element.basic_projection_to_local.setflags(write=True)
    json.dumps(initial.to_dict(), allow_nan=False, sort_keys=True)


def test_superposed_finite_rigid_motion_preserves_basic_and_section_response() -> None:
    element = _element()
    parent = element.initial_state()
    axial_extension = -6.0e-4
    rotation_i = -4.0e-3
    rotation_j = 7.0e-3
    baseline_displacements = np.asarray(
        [0.0, 0.0, rotation_i, axial_extension, 0.0, rotation_j],
        dtype=np.float64,
    )
    baseline = element.integrate(baseline_displacements, parent)

    rigid_rotation = 1.1
    rotation = np.asarray(
        [
            [math.cos(rigid_rotation), -math.sin(rigid_rotation)],
            [math.sin(rigid_rotation), math.cos(rigid_rotation)],
        ],
        dtype=np.float64,
    )
    translation = np.asarray([0.4, -0.2], dtype=np.float64)
    current_coordinates = (
        np.asarray([[0.0, 0.0], [LENGTH + axial_extension, 0.0]]) @ rotation.T
        + translation
    )
    rotated_displacements = np.asarray(
        [
            *(current_coordinates[0] - COORDINATES[0]),
            rigid_rotation + rotation_i,
            *(current_coordinates[1] - COORDINATES[1]),
            rigid_rotation + rotation_j,
        ],
        dtype=np.float64,
    )
    rotated = element.integrate(rotated_displacements, parent)
    transformation = np.zeros((6, 6), dtype=np.float64)
    transformation[:2, :2] = rotation
    transformation[2, 2] = 1.0
    transformation[3:5, 3:5] = rotation
    transformation[5, 5] = 1.0

    np.testing.assert_allclose(
        rotated.kinematics.basic_deformations,
        baseline.kinematics.basic_deformations,
        rtol=0.0,
        atol=2.0e-15,
    )
    np.testing.assert_allclose(
        rotated.basic_forces,
        baseline.basic_forces,
        rtol=0.0,
        atol=1.0e-11,
    )
    np.testing.assert_allclose(
        rotated.internal_force_global,
        transformation @ baseline.internal_force_global,
        rtol=0.0,
        atol=1.0e-11,
    )
    np.testing.assert_allclose(
        rotated.consistent_tangent_global,
        transformation @ baseline.consistent_tangent_global @ transformation.T,
        rtol=2.0e-13,
        atol=2.0e-9,
    )
    assert parent == element.initial_state()


def test_committed_chord_angle_unwraps_sequential_multi_turn_rigid_motion() -> None:
    coordinates = np.asarray([[0.2, -0.1], [2.7, 0.8]], dtype=np.float64)
    element = _element(coordinates)
    initial = element.initial_state()
    first = element.integrate(
        _rigid_displacements(coordinates, 2.2),
        initial,
    )
    second = element.integrate(
        _rigid_displacements(coordinates, 4.4),
        first.state,
    )
    trial_kinematics = element.trial_basic_kinematics(
        _rigid_displacements(coordinates, 4.4),
        first.state,
    )
    repeated = element.integrate(
        _rigid_displacements(coordinates, 4.4),
        first.state,
    )

    assert first.state.chord_rotation_change_rad == pytest.approx(2.2)
    assert second.state.chord_rotation_change_rad == pytest.approx(4.4)
    assert trial_kinematics.chord_rotation_change_rad == pytest.approx(4.4)
    np.testing.assert_allclose(first.kinematics.basic_deformations, 0.0, atol=1.0e-15)
    np.testing.assert_allclose(second.kinematics.basic_deformations, 0.0, atol=1.0e-15)
    np.testing.assert_allclose(first.internal_force_global, 0.0, atol=1.0e-12)
    np.testing.assert_allclose(second.internal_force_global, 0.0, atol=1.0e-12)
    np.testing.assert_allclose(
        second.fiber_beam_response.generalized_strains,
        0.0,
        atol=1.0e-15,
    )
    assert first.parent_state_hash == initial.state_hash
    assert second.parent_state_hash == first.state.state_hash
    assert second.state.step_index == 2
    assert second.state.state_hash == repeated.state.state_hash
    assert second.state.canonical_bytes() == repeated.state.canonical_bytes()


def test_nonlinear_global_tangent_matches_same_parent_force_jacobian() -> None:
    element = _element()
    initial = element.initial_state()
    committed = element.integrate(
        _uniform_basic_displacements(-2.0e-4, 4.0e-3),
        initial,
    ).state
    parent_bytes = committed.canonical_bytes()
    trial = _uniform_basic_displacements(-2.0e-4, 9.0e-3)
    response = element.integrate(trial, committed)
    epsilon = 1.0e-8
    finite_difference = np.zeros((6, 6), dtype=np.float64)
    for column in range(6):
        perturbation = np.zeros(6, dtype=np.float64)
        perturbation[column] = epsilon
        finite_difference[:, column] = (
            element.integrate(
                trial + perturbation,
                committed,
            ).internal_force_global
            - element.integrate(
                trial - perturbation,
                committed,
            ).internal_force_global
        ) / (2.0 * epsilon)

    scale = max(
        1.0,
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(np.linalg.norm(response.consistent_tangent_global, ord=np.inf)),
    )
    relative_error = float(
        np.linalg.norm(
            finite_difference - response.consistent_tangent_global,
            ord=np.inf,
        )
        / scale
    )

    assert relative_error <= 1.0e-7
    assert response.yielded_integration_point_count == 3
    assert response.damaged_integration_point_count == 3
    assert response.dissipated_energy_mj > 0.0
    projection = element.basic_projection_to_local
    np.testing.assert_allclose(
        response.fiber_beam_response.local_displacements,
        projection @ response.kinematics.basic_deformations,
        rtol=0.0,
        atol=1.0e-15,
    )
    np.testing.assert_allclose(
        response.basic_forces,
        projection.T @ response.fiber_beam_response.internal_force_local,
        rtol=0.0,
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        response.consistent_tangent_basic,
        projection.T
        @ response.fiber_beam_response.consistent_tangent_local
        @ projection,
        rtol=0.0,
        atol=1.0e-12,
    )
    assert np.linalg.norm(response.material_tangent_global, ord=np.inf) > 0.0
    assert np.linalg.norm(response.geometric_tangent_global, ord=np.inf) > 0.0
    np.testing.assert_allclose(
        response.consistent_tangent_global,
        response.material_tangent_global + response.geometric_tangent_global,
        rtol=0.0,
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        response.consistent_tangent_global,
        response.consistent_tangent_global.T,
        rtol=0.0,
        atol=1.0e-9,
    )
    assert committed.canonical_bytes() == parent_bytes


def _cyclic_history():
    element = _element()
    state = element.initial_state()
    path = (
        (-2.0e-4, 0.0),
        (-2.0e-4, 4.0e-3),
        (-2.0e-4, 9.0e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, -5.0e-3),
        (-2.0e-4, -9.0e-3),
        (-2.0e-4, 0.0),
    )
    energies: list[float] = []
    yielded: list[int] = []
    damaged: list[int] = []
    for axial_strain, curvature in path:
        response = element.integrate(
            _uniform_basic_displacements(axial_strain, curvature),
            state,
        )
        state = response.state
        energies.append(response.dissipated_energy_mj)
        yielded.append(response.yielded_integration_point_count)
        damaged.append(response.damaged_integration_point_count)
    return state, tuple(energies), tuple(yielded), tuple(damaged)


def test_cyclic_rc_state_replays_exactly_and_dissipation_is_monotonic() -> None:
    first = _cyclic_history()
    second = _cyclic_history()
    first_state, energies, yielded, damaged = first

    assert first_state.state_hash == second[0].state_hash
    assert first_state.canonical_bytes() == second[0].canonical_bytes()
    assert energies == second[1]
    assert energies[-1] > 0.0
    assert all(
        later >= earlier
        for earlier, later in zip(energies[:-1], energies[1:], strict=True)
    )
    assert max(yielded) == 3
    assert max(damaged) == 3
    assert first_state.step_index == len(energies)


def test_trial_states_do_not_mutate_or_alias_the_committed_parent() -> None:
    element = _element()
    committed = element.integrate(
        _uniform_basic_displacements(-2.0e-4, 4.0e-3),
        element.initial_state(),
    ).state
    parent_bytes = committed.canonical_bytes()
    positive = element.integrate(
        _uniform_basic_displacements(-2.0e-4, 9.0e-3),
        committed,
    )
    negative = element.integrate(
        _uniform_basic_displacements(-2.0e-4, -9.0e-3),
        committed,
    )
    repeated = element.integrate(
        _uniform_basic_displacements(-2.0e-4, 9.0e-3),
        committed,
    )

    assert committed.canonical_bytes() == parent_bytes
    assert positive.parent_state_hash == committed.state_hash
    assert negative.parent_state_hash == committed.state_hash
    assert positive.state.state_hash != negative.state.state_hash
    assert positive.state.state_hash == repeated.state.state_hash
    assert positive.state.canonical_bytes() == repeated.state.canonical_bytes()


def test_response_arrays_are_immutable_and_json_serializable() -> None:
    element = _element()
    response = element.integrate(
        _uniform_basic_displacements(-2.0e-4, 9.0e-3),
        element.initial_state(),
    )

    for array in (
        response.basic_forces,
        response.consistent_tangent_basic,
        response.internal_force_global,
        response.material_tangent_global,
        response.geometric_tangent_global,
        response.consistent_tangent_global,
    ):
        assert not array.flags.writeable
    with pytest.raises(ValueError):
        response.basic_forces[0] = 0.0
    with pytest.raises(ValueError):
        response.consistent_tangent_global[0, 0] = 0.0
    payload = response.to_dict()
    assert payload["schema_version"] == (
        STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION
    )
    assert element.dissipated_energy_mj(response.state) == (
        response.dissipated_energy_mj
    )
    json.dumps(payload, allow_nan=False, sort_keys=True)


def test_element_rejects_tampered_inner_parent_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    element = _element()
    parent = element.initial_state()
    parent_bytes = parent.canonical_bytes()
    integrate = StatefulFiberBeam2D.integrate

    def tampered_integrate(
        beam: StatefulFiberBeam2D,
        local_displacements: object,
        committed_state: object,
    ):
        response = integrate(beam, local_displacements, committed_state)
        return replace(response, parent_state_hash="sha256:" + "0" * 64)

    monkeypatch.setattr(StatefulFiberBeam2D, "integrate", tampered_integrate)

    with pytest.raises(ValueError, match="fiber-beam response parent state"):
        element.integrate(np.zeros(6), parent)
    assert parent.canonical_bytes() == parent_bytes


def test_state_and_element_contracts_fail_closed() -> None:
    element = _element()
    initial = element.initial_state()

    wrong_contract = replace(
        initial,
        element_contract_hash="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="element_contract_hash"):
        element.validate_state(wrong_contract)

    wrong_displacement = replace(
        initial,
        element_displacements=(0.0, 0.0, 0.0, 1.0e-3, 0.0, 0.0),
    )
    with pytest.raises(ValueError, match="local displacement"):
        element.validate_state(wrong_displacement)

    wrong_angle = replace(initial, chord_rotation_change_rad=0.1)
    with pytest.raises(ValueError, match="chord rotation"):
        element.validate_state(wrong_angle)

    wrong_turn = replace(initial, chord_rotation_change_rad=2.0 * math.pi)
    with pytest.raises(ValueError, match="local displacement"):
        element.validate_state(wrong_turn)

    different_geometry = _element(
        np.asarray([[0.0, 0.0], [4.0, 0.0]]),
    )
    with pytest.raises(ValueError, match="element_contract_hash"):
        different_geometry.validate_state(initial)

    with pytest.raises(ValueError, match="step indices"):
        StatefulCorotationalFiberBeam2DState(
            element_id=initial.element_id,
            element_contract_hash=initial.element_contract_hash,
            step_index=1,
            element_displacements=initial.element_displacements,
            chord_rotation_change_rad=0.0,
            basic_beam_state=initial.basic_beam_state,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"node_coordinates_m": [[0.0, 0.0]]}, "2x2"),
        ({"node_coordinates_m": np.zeros((2, 2))}, "must not coincide"),
        ({"integration_order": 4}, "2 or 3"),
        ({"element_id": " "}, "non-empty"),
    ],
)
def test_invalid_element_inputs_fail_closed(overrides, message: str) -> None:
    arguments = {
        "node_coordinates_m": COORDINATES,
        "section": make_rectangular_stateful_rc_fiber_section(),
        "integration_order": 3,
        "element_id": "corotational-member-1",
    }
    arguments.update(overrides)
    with pytest.raises(ValueError, match=message):
        StatefulCorotationalFiberBeam2D(**arguments)

    element = _element()
    with pytest.raises(ValueError, match="six-vector"):
        element.integrate(np.zeros(5), element.initial_state())
