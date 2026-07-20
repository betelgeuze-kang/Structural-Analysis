from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.assembly import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES,
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE,
    StatefulFiberFrame2DCheckpointArtifactError,
    StatefulFiberFrame2DCheckpoint,
    assemble_stateful_fiber_frame2d,
    dump_stateful_fiber_frame2d_checkpoint_bytes,
    initial_stateful_fiber_frame2d_checkpoint,
    load_stateful_fiber_frame2d_checkpoint_bytes,
    read_stateful_fiber_frame2d_checkpoint_artifact,
    run_stateful_fiber_frame2d_load_path,
    small_displacement_frame2d_transformation,
    solve_stateful_fiber_frame2d_load_step,
    stateful_fiber_frame2d_checkpoint_artifact_hash,
    validate_stateful_fiber_frame2d_checkpoint,
    write_stateful_fiber_frame2d_checkpoint_artifact,
)
from structural_analysis.benchmark import (
    build_stateful_fiber_frame2d_benchmark,
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.elements import StatefulFiberBeam2D
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


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
    assert verification["persistent_checkpoint_roundtrip_and_restart_exact"] is True
    assert verification["forced_failure_rollback_exact"] is True
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0
    assert first["global_tangent_finite_difference"]["relative_inf_error"] <= 5.0e-6
    assert first["rotation_invariance"]["local_displacement_inf_error"] <= 1.0e-13
    assert first["nonlinear_l_frame_path"]["final_epoch"] == 4
    assert first["claims"]["two_member_dense_global_assembly"] is True
    assert first["claims"]["persistent_checkpoint_roundtrip"] is True
    assert first["claims"]["persistent_checkpoint_ancestor_chain_bundle"] is False
    assert first["claims"]["generalized_section_state_codec_registry"] is False
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


def test_persisted_checkpoint_roundtrip_resumes_exact_nonlinear_path(
    tmp_path: Path,
) -> None:
    factors = (0.25, 0.5, 0.75, 1.0)
    config = NewtonRaphsonConfig(max_iterations=40)
    problem = make_two_member_stateful_fiber_l_frame()
    uninterrupted = run_stateful_fiber_frame2d_load_path(
        problem,
        factors,
        config=config,
    )
    prefix = run_stateful_fiber_frame2d_load_path(
        problem,
        factors[:2],
        config=config,
    )
    checkpoint = prefix.final_checkpoint
    artifact = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, checkpoint)
    artifact_path = tmp_path / "frame-checkpoint.json"

    written = write_stateful_fiber_frame2d_checkpoint_artifact(
        problem,
        checkpoint,
        artifact_path,
    )
    restored = read_stateful_fiber_frame2d_checkpoint_artifact(problem, written)
    resumed = run_stateful_fiber_frame2d_load_path(
        problem,
        factors[2:],
        initial_checkpoint=restored,
        config=config,
    )

    assert STATEFUL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE.endswith(".v1")
    assert artifact_path.read_bytes() == artifact
    assert stateful_fiber_frame2d_checkpoint_artifact_hash(artifact).startswith(
        "sha256:"
    )
    assert restored.state_hash == checkpoint.state_hash
    assert restored.canonical_bytes() == checkpoint.canonical_bytes()
    assert restored.to_dict() == checkpoint.to_dict()
    assert dump_stateful_fiber_frame2d_checkpoint_bytes(problem, restored) == artifact
    assert resumed.contract_pass is True
    assert resumed.initial_checkpoint.state_hash == checkpoint.state_hash
    assert (
        resumed.final_checkpoint.state_hash == uninterrupted.final_checkpoint.state_hash
    )
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == uninterrupted.final_checkpoint.canonical_bytes()
    )
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="already exists",
    ):
        write_stateful_fiber_frame2d_checkpoint_artifact(
            problem,
            checkpoint,
            artifact_path,
        )


def test_checkpoint_artifact_preserves_signed_zero_exactly() -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    signed_zero = replace(
        initial,
        global_displacements=tuple(-0.0 for _ in initial.global_displacements),
        state_hash="",
    )
    artifact = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, signed_zero)
    restored = load_stateful_fiber_frame2d_checkpoint_bytes(artifact, problem)

    assert b"-0.0" in artifact
    assert restored.state_hash == signed_zero.state_hash
    assert restored.canonical_bytes() == signed_zero.canonical_bytes()
    assert all(
        math.copysign(1.0, value) == -1.0 for value in restored.global_displacements
    )


def test_checkpoint_artifact_rejects_noncanonical_and_tampered_payloads() -> None:
    problem = make_two_member_stateful_fiber_l_frame()
    checkpoint = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.25,),
        config=NewtonRaphsonConfig(max_iterations=40),
    ).final_checkpoint
    artifact = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, checkpoint)

    duplicate_key = artifact.replace(
        b'{"case_id":',
        b'{"case_id":"duplicate","case_id":',
        1,
    )
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="duplicate key",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(duplicate_key, problem)

    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="not canonical JSON",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(artifact + b"\n", problem)

    non_finite = artifact.replace(
        b'"load_factor":0.25',
        b'"load_factor":NaN',
        1,
    )
    assert non_finite != artifact
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="non-finite token",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(non_finite, problem)

    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="byte limit",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(
            b" " * (STATEFUL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES + 1),
            problem,
        )

    payload = json.loads(artifact)
    payload["unexpected"] = True
    unexpected = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="schema validation failed",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(unexpected, problem)

    del payload["unexpected"]
    payload["epoch"] = True
    invalid_integer = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="schema validation failed",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(invalid_integer, problem)

    payload["epoch"] = checkpoint.epoch
    payload["element_states"][0]["integration_point_states"][0]["fiber_states"][0][
        "state_hash"
    ] = "sha256:" + "0" * 64
    nested_tamper = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="hash or canonical value mismatch",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(nested_tamper, problem)

    wrong_problem = make_two_element_stateful_fiber_cantilever(angle_rad=0.617)
    with pytest.raises(
        StatefulFiberFrame2DCheckpointArtifactError,
        match="does not match",
    ):
        load_stateful_fiber_frame2d_checkpoint_bytes(artifact, wrong_problem)
