from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts import (
    CURRENT_TANGENT_OPERATOR_PROFILE,
    CURRENT_TANGENT_OPERATOR_SCHEMA_VERSION,
    CurrentTangentOperatorError,
    create_current_tangent_operator,
    validate_current_tangent_operator_manifest,
)


def _reference_csr() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dense = np.asarray(
        [
            [10.0, 2.0, 0.0],
            [2.0, 20.0, -1.0],
            [0.0, -1.0, 30.0],
        ],
        dtype=np.float64,
    )
    return (
        np.asarray([0, 2, 5, 7], dtype=np.int64),
        np.asarray([0, 1, 0, 1, 2, 1, 2], dtype=np.int64),
        np.asarray([10.0, 2.0, 2.0, 20.0, -1.0, -1.0, 30.0]),
        dense,
    )


def _geometry_arrays() -> tuple[np.ndarray, ...]:
    dofs = np.arange(12, dtype=np.int64).reshape(1, 12)
    relative = np.zeros((1, 3, 12), dtype=np.float64)
    relative[0, :, 0:3] = -np.eye(3)
    relative[0, :, 6:9] = np.eye(3)
    return (
        dofs,
        relative,
        np.asarray([[2.0, 0.0, 0.0]], dtype=np.float64),
        np.asarray([2.0], dtype=np.float64),
        np.asarray([50.0], dtype=np.float64),
    )


def _contract(*, background_free_value: float = 0.0):
    row_pointer, columns, values, _dense = _reference_csr()
    geometry = _geometry_arrays()
    background = np.zeros(12, dtype=np.float64)
    background[1] = 0.03
    background[0] = background_free_value
    frame_delta = np.zeros((1, 12, 12), dtype=np.float64)
    frame_delta[0] = np.diag(np.arange(1.0, 13.0))
    frame_delta[0, 0, 6] = -0.25
    frame_delta[0, 6, 0] = 0.5
    return create_current_tangent_operator(
        case_id="synthetic_current_tangent",
        residual_formula_hash="sha256:" + "1" * 64,
        source_action_contract="synthetic_exact_action.v1",
        reference_row_pointer=row_pointer,
        reference_column_indices=columns,
        reference_values_n_per_m=values,
        free_global_dofs=np.asarray([0, 6, 7], dtype=np.int64),
        background_global_displacements_m=background,
        frame_dofs=np.arange(12, dtype=np.int64).reshape(1, 12),
        frame_stiffness_delta_n_per_m=frame_delta,
        geometry_dofs=geometry[0],
        geometry_relative_translation_operators=geometry[1],
        geometry_reference_chords_m=geometry[2],
        geometry_reference_lengths_m=geometry[3],
        geometry_axial_stiffness_n_per_m=geometry[4],
    )


def _correction_force_free(
    free_state: np.ndarray,
    *,
    load_factor: float,
) -> np.ndarray:
    contract = _contract()
    free = contract.array("free_global_dofs")
    global_state = np.array(
        contract.array("background_global_displacements_m"),
        copy=True,
    )
    global_state[free] = free_state
    row_pointer, columns, values, dense = _reference_csr()
    del row_pointer, columns, values
    force = dense @ free_state

    frame_dofs = contract.array("frame_dofs")
    frame_delta = contract.array("frame_stiffness_delta_n_per_m")
    element_frame_force = frame_delta[0] @ global_state[frame_dofs[0]]
    global_frame_force = np.zeros(12, dtype=np.float64)
    np.add.at(global_frame_force, frame_dofs[0], element_frame_force)
    force += load_factor * global_frame_force[free]

    geometry_dofs = contract.array("geometry_dofs")[0]
    relative = contract.array("geometry_relative_translation_operators")[0]
    reference_chord = contract.array("geometry_reference_chords_m")[0]
    reference_length = contract.array("geometry_reference_lengths_m")[0]
    axial_stiffness = contract.array(
        "geometry_axial_stiffness_n_per_m"
    )[0]
    relative_translation = relative @ global_state[geometry_dofs]
    current_chord = reference_chord + relative_translation
    current_length = np.linalg.norm(current_chord)
    current_direction = current_chord / current_length
    reference_direction = reference_chord / reference_length
    extension = current_length - reference_length
    linear_extension = reference_direction @ relative_translation
    correction_end_force = axial_stiffness * (
        extension * current_direction
        - linear_extension * reference_direction
    )
    element_geometry_force = relative.T @ correction_end_force
    global_geometry_force = np.zeros(12, dtype=np.float64)
    np.add.at(
        global_geometry_force,
        geometry_dofs,
        element_geometry_force,
    )
    return force + global_geometry_force[free]


def test_current_tangent_contract_is_stable_immutable_and_schema_valid() -> None:
    first = _contract()
    second = _contract()

    assert first.schema_version == CURRENT_TANGENT_OPERATOR_SCHEMA_VERSION
    assert first.profile == CURRENT_TANGENT_OPERATOR_PROFILE
    assert first.contract_hash == second.contract_hash
    assert first.array_bundle_hash == second.array_bundle_hash
    assert first.equation_count == 3
    assert first.global_dof_count == 12
    assert first.reference_nnz == 7
    assert first.frame_element_count == 1
    assert first.geometry_element_count == 1
    assert validate_current_tangent_operator_manifest(first.to_manifest())

    for descriptor in first.descriptors:
        array = first.array(descriptor.name)
        assert array.flags.c_contiguous
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_current_tangent_action_matches_independent_residual_difference() -> None:
    contract = _contract()
    state = np.asarray([0.01, 0.04, 0.02], dtype=np.float64)
    direction = np.asarray([0.3, -0.2, 0.4], dtype=np.float64)
    load_factor = 0.75
    step = 1.0e-6

    action = contract.apply_n_per_m(state, load_factor, direction)
    finite_difference = (
        _correction_force_free(
            state + step * direction,
            load_factor=load_factor,
        )
        - _correction_force_free(
            state - step * direction,
            load_factor=load_factor,
        )
    ) / (2.0 * step)

    np.testing.assert_allclose(
        action,
        finite_difference,
        rtol=5.0e-9,
        atol=1.0e-8,
    )


def test_current_tangent_manifest_hash_tamper_fails_closed() -> None:
    manifest = deepcopy(_contract().to_manifest())
    manifest["dimensions"]["frame_element_count"] = 2

    with pytest.raises(
        CurrentTangentOperatorError,
        match="current_tangent_contract_hash_mismatch",
    ):
        validate_current_tangent_operator_manifest(manifest)


def test_current_tangent_background_must_be_zero_on_free_dofs() -> None:
    with pytest.raises(
        CurrentTangentOperatorError,
        match="current_tangent_background_free_entries_nonzero",
    ):
        _contract(background_free_value=0.01)


def test_current_tangent_apply_rejects_collapsed_geometry() -> None:
    contract = _contract()
    collapsed_state = np.asarray([0.0, -2.0, 0.03], dtype=np.float64)

    with pytest.raises(
        CurrentTangentOperatorError,
        match="current_tangent_geometry_chord_collapsed",
    ):
        contract.apply_n_per_m(
            collapsed_state,
            1.0,
            np.ones(3, dtype=np.float64),
        )
