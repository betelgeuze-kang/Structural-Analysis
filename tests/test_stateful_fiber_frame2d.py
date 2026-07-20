from __future__ import annotations

from dataclasses import replace
import json
import math

import numpy as np
import pytest

from structural_analysis.assembly import (
    StatefulFiberFrame2DCheckpoint,
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
    small_displacement_frame2d_transformation,
    solve_stateful_fiber_frame2d_load_step,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.benchmark import (
    build_stateful_fiber_frame2d_benchmark,
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.elements import StatefulFiberBeam2D


def test_fixed_chord_transformation_is_orthogonal_and_energy_conjugate() -> None:
    angle = 0.617
    coordinates = (
        (1.0, -2.0),
        (1.0 + 3.0 * math.cos(angle), -2.0 + 3.0 * math.sin(angle)),
    )
    transformation = small_displacement_frame2d_transformation(coordinates)
    global_displacements = np.asarray(
        (0.01, -0.02, 0.003, -0.04, 0.05, -0.006),
        dtype=np.float64,
    )
    local_force = np.asarray((2.0, -3.0, 4.0, -5.0, 6.0, -7.0))
    local_displacements = transformation @ global_displacements
    global_force = transformation.T @ local_force

    assert transformation.shape == (6, 6)
    assert transformation.flags.writeable is False
    assert np.allclose(transformation @ transformation.T, np.eye(6), atol=1.0e-15)
    assert float(local_force @ local_displacements) == pytest.approx(
        float(global_force @ global_displacements),
        abs=1.0e-15,
    )


def test_two_element_cantilever_matches_closed_form_and_commits_checkpoint() -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    result = solve_stateful_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=1.0,
    )
    expected_tip_displacement = -10.0 * 3.0**3 / (3.0 * 253_200.0)
    expected_tip_rotation = -10.0 * 3.0**2 / (2.0 * 253_200.0)

    assert result.status == "ready"
    assert result.committed is True
    assert result.metrics["solver_contract_pass"] is True
    assert result.metrics["section_and_element_parent_binding_passed"] is True
    assert result.accepted_checkpoint.epoch == 1
    assert result.accepted_checkpoint.parent_state_hash == initial.state_hash
    assert result.accepted_checkpoint.global_displacements[7] == pytest.approx(
        expected_tip_displacement,
        abs=1.0e-15,
    )
    assert result.accepted_checkpoint.global_displacements[8] == pytest.approx(
        expected_tip_rotation,
        abs=1.0e-15,
    )
    assert result.trial_assembly.reactions_global[:3] == pytest.approx(
        (0.0, 10.0, 30.0),
        abs=1.0e-10,
    )
    assert np.allclose(
        result.trial_assembly.jacobian_kn_per_m,
        result.trial_assembly.jacobian_kn_per_m.T,
        atol=1.0e-9,
    )


def test_frame_benchmark_replays_restart_and_keeps_claims_bounded() -> None:
    first = build_stateful_fiber_frame2d_benchmark()
    second = build_stateful_fiber_frame2d_benchmark()

    assert first == second
    assert first["status"] == "partial"
    assert first["contract_pass"] is True
    verification = first["verification"]
    assert verification["axial_curvature_section_protocol_passed"] is True
    assert verification["two_element_elastic_closed_form_passed"] is True
    assert verification["fixed_transform_rotation_invariance_passed"] is True
    assert verification["consistent_global_tangent_finite_difference_passed"] is True
    assert verification["checkpoint_parent_hash_and_epoch_chain_passed"] is True
    assert verification["nonlinear_member_state_update_passed"] is True
    assert verification["deterministic_replay_exact"] is True
    assert verification["in_memory_checkpoint_restart_exact"] is True
    assert verification["forced_failure_rollback_exact"] is True
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0
    assert first["global_tangent_finite_difference"]["relative_inf_error"] <= 5.0e-6
    assert first["rotation_invariance"]["local_displacement_inf_error"] <= 1.0e-13
    assert first["nonlinear_l_frame_path"]["final_epoch"] == 4
    assert first["claims"]["two_member_dense_global_assembly"] is True
    assert first["claims"]["persistent_checkpoint_roundtrip"] is False
    assert first["claims"]["geometric_nonlinearity"] is False
    assert first["claims"]["mesh_objective_distributed_plasticity"] is False
    assert first["claims"]["external_validation"] is False
    assert first["claims"]["production_sparse_or_rocm_hip"] is False
    assert first["claims"]["full_building_equilibrium"] is False
    assert first["claims"]["g1_closure"] is False
    json.dumps(first, sort_keys=True, allow_nan=False)


def test_checkpoint_validation_rejects_wrong_contract_and_global_local_mismatch() -> (
    None
):
    problem = make_two_element_stateful_fiber_cantilever()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    wrong_contract = StatefulFiberFrame2DCheckpoint(
        case_id=initial.case_id,
        problem_contract_hash="sha256:" + "0" * 64,
        epoch=initial.epoch,
        step_index=initial.step_index,
        load_factor=initial.load_factor,
        parent_state_hash=initial.parent_state_hash,
        global_displacements=initial.global_displacements,
        element_states=initial.element_states,
    )
    with pytest.raises(ValueError, match="problem_contract_hash"):
        validate_stateful_fiber_frame2d_checkpoint(problem, wrong_contract)

    committed = solve_stateful_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=1.0,
    ).accepted_checkpoint
    displaced = list(committed.global_displacements)
    displaced[7] += 1.0e-4
    inconsistent = replace(
        committed,
        global_displacements=tuple(displaced),
        state_hash="",
    )
    with pytest.raises(ValueError, match="local displacement"):
        validate_stateful_fiber_frame2d_checkpoint(problem, inconsistent)

    with pytest.raises(ValueError, match="positive-epoch"):
        StatefulFiberFrame2DCheckpoint(
            case_id=committed.case_id,
            problem_contract_hash=committed.problem_contract_hash,
            epoch=1,
            step_index=1,
            load_factor=1.0,
            parent_state_hash=None,
            global_displacements=committed.global_displacements,
            element_states=committed.element_states,
        )


def test_global_assembly_rejects_element_response_from_wrong_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)
    checkpoint_bytes = checkpoint.canonical_bytes()
    integrate = StatefulFiberBeam2D.integrate

    def tampered_integrate(
        element: StatefulFiberBeam2D,
        local_displacements: object,
        committed_state: object,
    ) -> object:
        response = integrate(element, local_displacements, committed_state)
        return replace(response, parent_state_hash="sha256:" + "0" * 64)

    monkeypatch.setattr(StatefulFiberBeam2D, "integrate", tampered_integrate)

    with pytest.raises(ValueError, match="element response parent_state_hash"):
        assemble_stateful_fiber_frame2d(
            problem,
            checkpoint,
            target_load_factor=0.0,
            trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
        )

    assert checkpoint.canonical_bytes() == checkpoint_bytes
