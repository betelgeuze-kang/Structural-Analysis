from __future__ import annotations

from dataclasses import replace
import json
import math

import numpy as np
import pytest

from structural_analysis.assembly import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION,
    StatefulCorotationalFiberFrame2DCheckpoint,
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials import (
    make_rectangular_stateful_rc_fiber_section,
)


L_FRAME_COORDINATES = ((0.0, 0.0), (3.0, 0.0), (3.0, 2.0))
STRAIGHT_FRAME_COORDINATES = ((0.0, 0.0), (3.0, 0.0), (6.0, 0.0))


def _problem(
    coordinates=L_FRAME_COORDINATES,
    *,
    case_id: str = "stateful-corotational-frame",
) -> StatefulCorotationalFiberFrame2DProblem:
    members = []
    for member_id, node_i, node_j in (("member-1", 0, 1), ("member-2", 1, 2)):
        members.append(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member_id,
                node_i=node_i,
                node_j=node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=(
                        coordinates[node_i],
                        coordinates[node_j],
                    ),
                    section=make_rectangular_stateful_rc_fiber_section(),
                    integration_order=3,
                    element_id=member_id,
                ),
            )
        )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id=case_id,
        node_coordinates_m=coordinates,
        members=tuple(members),
        fixed_global_dofs=(0, 1),
        reference_external_loads=((7, -10.0),),
        rotation_coordinate_scale_m=3.0,
    )


def _trial_free_coordinates(
    problem: StatefulCorotationalFiberFrame2DProblem,
    physical_displacements: np.ndarray,
) -> np.ndarray:
    generalized = physical_displacements / problem.physical_coordinate_scale
    return generalized[list(problem.free_global_dofs)]


def _accept_trial(
    problem: StatefulCorotationalFiberFrame2DProblem,
    parent: StatefulCorotationalFiberFrame2DCheckpoint,
    assembly,
) -> StatefulCorotationalFiberFrame2DCheckpoint:
    checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=problem.contract_hash,
        epoch=parent.epoch + 1,
        step_index=parent.step_index + 1,
        load_factor=assembly.target_load_factor,
        parent_state_hash=parent.state_hash,
        global_displacements=tuple(
            float(value) for value in assembly.global_displacements
        ),
        element_states=assembly.trial_element_states,
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
    return checkpoint


def _rigid_displacements(
    coordinates: tuple[tuple[float, float], ...],
    angle_rad: float,
) -> np.ndarray:
    rotation = np.asarray(
        [
            [math.cos(angle_rad), -math.sin(angle_rad)],
            [math.sin(angle_rad), math.cos(angle_rad)],
        ],
        dtype=np.float64,
    )
    initial = np.asarray(coordinates, dtype=np.float64)
    current = initial @ rotation.T
    displacements = np.empty(3 * len(coordinates), dtype=np.float64)
    for node_index in range(len(coordinates)):
        offset = 3 * node_index
        displacements[offset : offset + 2] = current[node_index] - initial[node_index]
        displacements[offset + 2] = angle_rad
    return displacements


def test_problem_checkpoint_and_zero_assembly_are_deterministic() -> None:
    problem = _problem()
    repeated_problem = _problem()
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    repeated_initial = initial_stateful_corotational_fiber_frame2d_checkpoint(
        repeated_problem
    )
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )

    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_SCHEMA_VERSION.endswith(".v1")
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION.endswith(".v1")
    assert "K_geometric" in STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY
    assert "S_transpose" in STATEFUL_COROTATIONAL_FIBER_FRAME2D_COORDINATE_SCALING
    assert problem.contract_hash == repeated_problem.contract_hash
    assert initial.state_hash == repeated_initial.state_hash
    assert initial.canonical_bytes() == repeated_initial.canonical_bytes()
    assert initial.epoch == initial.step_index == 0
    assert initial.parent_state_hash is None
    assert problem.free_global_dofs == (2, 3, 4, 5, 6, 7, 8)
    np.testing.assert_array_equal(
        problem.physical_coordinate_scale,
        np.asarray([1.0, 1.0, 1.0 / 3.0] * 3),
    )
    assert not problem.physical_coordinate_scale.flags.writeable
    np.testing.assert_allclose(assembly.internal_loads_global, 0.0, atol=1.0e-12)
    np.testing.assert_allclose(assembly.residual_kn, 0.0, atol=1.0e-12)
    np.testing.assert_allclose(assembly.geometric_tangent_global, 0.0, atol=1.0e-12)
    np.testing.assert_array_equal(
        assembly.consistent_tangent_global,
        assembly.material_tangent_global,
    )
    assert np.linalg.norm(assembly.material_tangent_global, ord=np.inf) > 0.0
    assert assembly.parent_checkpoint_hash == initial.state_hash
    assert tuple(state.step_index for state in assembly.trial_element_states) == (1, 1)
    for array in (
        assembly.generalized_coordinates_m,
        assembly.global_displacements,
        assembly.residual_kn,
        assembly.jacobian_kn_per_m,
        assembly.internal_loads_global,
        assembly.material_tangent_global,
        assembly.geometric_tangent_global,
        assembly.consistent_tangent_global,
    ):
        assert not array.flags.writeable
    json.dumps(initial.to_dict(), allow_nan=False, sort_keys=True)
    json.dumps(assembly.to_dict(), allow_nan=False, sort_keys=True)


def test_shared_node_scatter_residual_and_tangent_decomposition() -> None:
    problem = _problem()
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    physical_displacements = np.asarray(
        [0.0, 0.0, -0.004, -0.0005, 0.0008, 0.006, 0.001, -0.001, -0.003],
        dtype=np.float64,
    )
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.4,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            physical_displacements,
        ),
    )
    expected_internal = np.zeros(problem.global_dof_count)
    expected_material = np.zeros((problem.global_dof_count, problem.global_dof_count))
    expected_geometric = np.zeros_like(expected_material)
    expected_consistent = np.zeros_like(expected_material)
    for row in assembly.member_assemblies:
        dofs = row.global_dofs
        expected_internal[list(dofs)] += row.internal_load_global
        expected_material[np.ix_(dofs, dofs)] += row.material_tangent_global
        expected_geometric[np.ix_(dofs, dofs)] += row.geometric_tangent_global
        expected_consistent[np.ix_(dofs, dofs)] += row.consistent_tangent_global

    assert assembly.member_assemblies[0].global_dofs == (0, 1, 2, 3, 4, 5)
    assert assembly.member_assemblies[1].global_dofs == (3, 4, 5, 6, 7, 8)
    np.testing.assert_array_equal(assembly.internal_loads_global, expected_internal)
    np.testing.assert_array_equal(assembly.material_tangent_global, expected_material)
    np.testing.assert_array_equal(assembly.geometric_tangent_global, expected_geometric)
    np.testing.assert_allclose(
        assembly.consistent_tangent_global,
        expected_consistent,
        rtol=5.0e-16,
        atol=5.0e-10,
    )
    np.testing.assert_array_equal(
        assembly.consistent_tangent_global,
        assembly.material_tangent_global + assembly.geometric_tangent_global,
    )
    np.testing.assert_allclose(
        assembly.internal_loads_global[3:6],
        assembly.member_assemblies[0].internal_load_global[3:6]
        + assembly.member_assemblies[1].internal_load_global[:3],
        rtol=0.0,
        atol=0.0,
    )
    expected_external = 0.4 * problem.reference_external_load_vector()
    physical_residual = expected_internal - expected_external
    free = list(problem.free_global_dofs)
    free_scale = problem.physical_coordinate_scale[free]
    np.testing.assert_array_equal(assembly.external_loads_global, expected_external)
    np.testing.assert_allclose(
        assembly.residual_kn,
        free_scale * physical_residual[free],
        rtol=0.0,
        atol=1.0e-12,
    )
    np.testing.assert_array_equal(assembly.reactions_global[free], 0.0)
    np.testing.assert_array_equal(
        assembly.reactions_global[list(problem.fixed_global_dofs)],
        physical_residual[list(problem.fixed_global_dofs)],
    )


def test_global_assembly_is_objective_under_superposed_finite_rotation() -> None:
    problem = _problem(case_id="assembly-objectivity")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    baseline_displacements = np.asarray(
        [0.0, 0.0, -0.004, -0.0005, 0.0008, 0.006, 0.001, -0.001, -0.003],
        dtype=np.float64,
    )
    baseline = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.0,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            baseline_displacements,
        ),
    )
    rigid_rotation = 1.1
    rotation = np.asarray(
        [
            [math.cos(rigid_rotation), -math.sin(rigid_rotation)],
            [math.sin(rigid_rotation), math.cos(rigid_rotation)],
        ],
        dtype=np.float64,
    )
    initial_coordinates = np.asarray(problem.node_coordinates_m, dtype=np.float64)
    baseline_current = initial_coordinates + baseline_displacements.reshape(3, 3)[:, :2]
    rotated_current = baseline_current @ rotation.T
    rotated_displacements = np.empty(problem.global_dof_count, dtype=np.float64)
    transformation = np.zeros(
        (problem.global_dof_count, problem.global_dof_count),
        dtype=np.float64,
    )
    for node_index in range(len(problem.node_coordinates_m)):
        offset = 3 * node_index
        rotated_displacements[offset : offset + 2] = (
            rotated_current[node_index] - initial_coordinates[node_index]
        )
        rotated_displacements[offset + 2] = (
            baseline_displacements[offset + 2] + rigid_rotation
        )
        transformation[offset : offset + 2, offset : offset + 2] = rotation
        transformation[offset + 2, offset + 2] = 1.0
    rotated = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.0,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            rotated_displacements,
        ),
    )

    for baseline_row, rotated_row in zip(
        baseline.member_assemblies,
        rotated.member_assemblies,
        strict=True,
    ):
        np.testing.assert_allclose(
            rotated_row.response.kinematics.basic_deformations,
            baseline_row.response.kinematics.basic_deformations,
            rtol=0.0,
            atol=5.0e-16,
        )
        np.testing.assert_allclose(
            rotated_row.response.basic_forces,
            baseline_row.response.basic_forces,
            rtol=0.0,
            atol=1.0e-9,
        )
    np.testing.assert_allclose(
        rotated.internal_loads_global,
        transformation @ baseline.internal_loads_global,
        rtol=1.0e-12,
        atol=1.0e-9,
    )
    for rotated_tangent, baseline_tangent in (
        (rotated.material_tangent_global, baseline.material_tangent_global),
        (rotated.geometric_tangent_global, baseline.geometric_tangent_global),
        (rotated.consistent_tangent_global, baseline.consistent_tangent_global),
    ):
        np.testing.assert_allclose(
            rotated_tangent,
            transformation @ baseline_tangent @ transformation.T,
            rtol=1.0e-12,
            atol=1.0e-8,
        )


def test_nonlinear_global_jacobian_matches_same_parent_finite_difference() -> None:
    problem = _problem(STRAIGHT_FRAME_COORDINATES, case_id="nonlinear-fd")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    history_displacements = np.asarray(
        [0.0, 0.0, -0.006, -0.0006, 0.0, 0.006, -0.0012, 0.0, 0.018],
        dtype=np.float64,
    )
    history = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.0,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            history_displacements,
        ),
    )
    committed = _accept_trial(problem, initial, history)
    parent_bytes = committed.canonical_bytes()
    trial_displacements = np.asarray(
        [
            0.0,
            0.0,
            -0.012,
            -0.0007,
            0.0004,
            0.012,
            -0.0015,
            -0.001,
            0.026,
        ],
        dtype=np.float64,
    )
    trial_coordinates = _trial_free_coordinates(problem, trial_displacements)
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        committed,
        target_load_factor=0.3,
        trial_free_coordinates_m=trial_coordinates,
    )
    epsilon = 1.0e-8
    finite_difference = np.zeros_like(assembly.jacobian_kn_per_m)
    for column in range(len(trial_coordinates)):
        perturbation = np.zeros_like(trial_coordinates)
        perturbation[column] = epsilon
        forward = assemble_stateful_corotational_fiber_frame2d(
            problem,
            committed,
            target_load_factor=0.3,
            trial_free_coordinates_m=trial_coordinates + perturbation,
        )
        backward = assemble_stateful_corotational_fiber_frame2d(
            problem,
            committed,
            target_load_factor=0.3,
            trial_free_coordinates_m=trial_coordinates - perturbation,
        )
        finite_difference[:, column] = (forward.residual_kn - backward.residual_kn) / (
            2.0 * epsilon
        )

    scale = max(
        1.0,
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(np.linalg.norm(assembly.jacobian_kn_per_m, ord=np.inf)),
    )
    relative_error = float(
        np.linalg.norm(
            finite_difference - assembly.jacobian_kn_per_m,
            ord=np.inf,
        )
        / scale
    )

    assert relative_error <= 1.0e-7
    assert (
        sum(
            row.response.yielded_integration_point_count
            for row in assembly.member_assemblies
        )
        > 0
    )
    assert (
        sum(
            row.response.damaged_integration_point_count
            for row in assembly.member_assemblies
        )
        > 0
    )
    assert np.linalg.norm(assembly.material_tangent_global, ord=np.inf) > 0.0
    assert np.linalg.norm(assembly.geometric_tangent_global, ord=np.inf) > 0.0
    np.testing.assert_allclose(
        assembly.jacobian_kn_per_m,
        assembly.jacobian_kn_per_m.T,
        rtol=0.0,
        atol=1.0e-9,
    )
    assert committed.canonical_bytes() == parent_bytes
    repeated = assemble_stateful_corotational_fiber_frame2d(
        problem,
        committed,
        target_load_factor=0.3,
        trial_free_coordinates_m=trial_coordinates,
    )
    assert tuple(state.state_hash for state in assembly.trial_element_states) == tuple(
        state.state_hash for state in repeated.trial_element_states
    )


def test_multi_turn_rigid_rotation_tracks_every_member_checkpoint() -> None:
    problem = _problem(case_id="multi-turn")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    initial_bytes = initial.canonical_bytes()
    first = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.0,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            _rigid_displacements(problem.node_coordinates_m, 2.2),
        ),
    )
    first_checkpoint = _accept_trial(problem, initial, first)
    second_coordinates = _trial_free_coordinates(
        problem,
        _rigid_displacements(problem.node_coordinates_m, 4.4),
    )
    second = assemble_stateful_corotational_fiber_frame2d(
        problem,
        first_checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=second_coordinates,
    )
    repeated = assemble_stateful_corotational_fiber_frame2d(
        problem,
        first_checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=second_coordinates,
    )
    second_checkpoint = _accept_trial(problem, first_checkpoint, second)
    repeated_checkpoint = _accept_trial(problem, first_checkpoint, repeated)

    np.testing.assert_allclose(first.internal_loads_global, 0.0, atol=1.0e-12)
    np.testing.assert_allclose(second.internal_loads_global, 0.0, atol=1.0e-12)
    assert tuple(
        state.chord_rotation_change_rad for state in first.trial_element_states
    ) == pytest.approx((2.2, 2.2))
    assert tuple(
        state.chord_rotation_change_rad for state in second.trial_element_states
    ) == pytest.approx((4.4, 4.4))
    for row in (*first.member_assemblies, *second.member_assemblies):
        np.testing.assert_allclose(
            row.response.kinematics.basic_deformations,
            0.0,
            atol=1.0e-15,
        )
    assert second_checkpoint.epoch == second_checkpoint.step_index == 2
    assert second_checkpoint.parent_state_hash == first_checkpoint.state_hash
    assert second_checkpoint.state_hash == repeated_checkpoint.state_hash
    assert second_checkpoint.canonical_bytes() == repeated_checkpoint.canonical_bytes()
    assert initial.canonical_bytes() == initial_bytes


def test_same_parent_trial_branches_are_rollback_safe_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problem = _problem(STRAIGHT_FRAME_COORDINATES, case_id="branching")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    history_displacements = np.asarray(
        [0.0, 0.0, -0.006, -0.0006, 0.0, 0.006, -0.0012, 0.0, 0.018],
        dtype=np.float64,
    )
    history = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.0,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            history_displacements,
        ),
    )
    committed = _accept_trial(problem, initial, history)
    parent_bytes = committed.canonical_bytes()
    positive_displacements = history_displacements.copy()
    positive_displacements[8] = 0.03
    negative_displacements = history_displacements.copy()
    negative_displacements[8] = -0.03
    positive_coordinates = _trial_free_coordinates(problem, positive_displacements)
    positive = assemble_stateful_corotational_fiber_frame2d(
        problem,
        committed,
        target_load_factor=0.2,
        trial_free_coordinates_m=positive_coordinates,
    )
    negative = assemble_stateful_corotational_fiber_frame2d(
        problem,
        committed,
        target_load_factor=0.2,
        trial_free_coordinates_m=_trial_free_coordinates(
            problem,
            negative_displacements,
        ),
    )
    repeated = assemble_stateful_corotational_fiber_frame2d(
        problem,
        committed,
        target_load_factor=0.2,
        trial_free_coordinates_m=positive_coordinates,
    )

    assert committed.canonical_bytes() == parent_bytes
    assert tuple(state.state_hash for state in positive.trial_element_states) != tuple(
        state.state_hash for state in negative.trial_element_states
    )
    assert tuple(state.state_hash for state in positive.trial_element_states) == tuple(
        state.state_hash for state in repeated.trial_element_states
    )
    signed_zero_displacements = list(initial.global_displacements)
    signed_zero_displacements[7] = -0.0
    signed_zero_tamper = replace(
        initial,
        global_displacements=tuple(signed_zero_displacements),
        state_hash="",
    )
    with pytest.raises(ValueError, match="element displacement"):
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            problem,
            signed_zero_tamper,
        )
    with pytest.raises(ValueError, match="member response state"):
        replace(
            positive,
            trial_element_states=tuple(reversed(positive.trial_element_states)),
        )

    integrate = StatefulCorotationalFiberBeam2D.integrate

    def tampered_integrate(element, element_displacements, parent):
        response = integrate(element, element_displacements, parent)
        return replace(response, parent_state_hash="sha256:" + "0" * 64)

    monkeypatch.setattr(
        StatefulCorotationalFiberBeam2D,
        "integrate",
        tampered_integrate,
    )
    with pytest.raises(ValueError, match="parent_state_hash"):
        assemble_stateful_corotational_fiber_frame2d(
            problem,
            committed,
            target_load_factor=0.2,
            trial_free_coordinates_m=positive_coordinates,
        )
    assert committed.canonical_bytes() == parent_bytes


def test_problem_and_trial_inputs_fail_closed() -> None:
    problem = _problem()
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    wrong_geometry_element = StatefulCorotationalFiberBeam2D(
        node_coordinates_m=((0.0, 0.0), (2.5, 0.0)),
        section=make_rectangular_stateful_rc_fiber_section(),
        element_id="member-1",
    )
    wrong_geometry_member = StatefulCorotationalFiberFrame2DMember(
        member_id="member-1",
        node_i=0,
        node_j=1,
        element=wrong_geometry_element,
    )
    with pytest.raises(ValueError, match="coordinates"):
        StatefulCorotationalFiberFrame2DProblem(
            case_id="wrong-geometry",
            node_coordinates_m=L_FRAME_COORDINATES,
            members=(wrong_geometry_member,),
            fixed_global_dofs=(0, 1),
            reference_external_loads=((7, -1.0),),
            rotation_coordinate_scale_m=3.0,
        )
    with pytest.raises(ValueError, match="non-empty tuple"):
        replace(problem, fixed_global_dofs=())
    with pytest.raises(ValueError, match="unique"):
        replace(problem, reference_external_loads=((7, -1.0), (7, -2.0)))
    with pytest.raises(ValueError, match="shape or values"):
        assemble_stateful_corotational_fiber_frame2d(
            problem,
            initial,
            target_load_factor=0.0,
            trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs) - 1),
        )
    with pytest.raises(ValueError, match="target_load_factor"):
        assemble_stateful_corotational_fiber_frame2d(
            problem,
            initial,
            target_load_factor=True,
            trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
        )
    with pytest.raises(ValueError, match="load_factor"):
        StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=0,
            step_index=0,
            load_factor=True,
            parent_state_hash=None,
            global_displacements=(0.0,) * problem.global_dof_count,
            element_states=initial.element_states,
        )
