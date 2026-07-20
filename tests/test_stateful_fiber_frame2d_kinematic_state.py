from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state import (
    FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
    FiberFrameNonlinearKinematicStateError,
    _chain_payload,
    _state_payload,
    create_fiber_frame_nonlinear_kinematic_state_chain,
    validate_fiber_frame_nonlinear_kinematic_array_bytes,
    validate_fiber_frame_nonlinear_kinematic_manifest,
    validate_fiber_frame_nonlinear_kinematic_state,
    validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint,
    validate_fiber_frame_nonlinear_kinematic_state_chain,
    validate_fiber_frame_nonlinear_kinematic_state_chain_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_scaling import (
    create_fiber_frame_physical_equation_scaling,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64


def _fixture():
    problem = make_two_member_stateful_fiber_l_frame()
    topology = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("N1", "N2", "N3"),
    )
    scaling = create_fiber_frame_physical_equation_scaling(problem, topology)
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5),
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    assert path.contract_pass is True
    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps),
    )
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        checkpoints,
    )
    chain = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        topology,
        scaling,
        checkpoint_chain,
    )
    return problem, topology, scaling, checkpoint_chain, chain


def test_checkpoint_chain_maps_to_exact_physical_generalized_and_six_dof_states() -> (
    None
):
    problem, topology, scaling, checkpoint_chain, chain = _fixture()

    assert chain.authority_profile == FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE
    assert chain.checkpoint_chain_hash == checkpoint_chain.chain_hash
    assert chain.topology_plan_hash == topology.plan_hash
    assert chain.physical_scaling_hash == scaling.scaling_hash
    assert chain.state_count == len(checkpoint_chain.checkpoints) == 3
    assert [state.epoch for state in chain.states] == [0, 1, 2]
    assert (
        chain.root_checkpoint_state_hash == checkpoint_chain.root_checkpoint.state_hash
    )
    assert chain.terminal_checkpoint_state_hash == (
        checkpoint_chain.terminal_checkpoint.state_hash
    )

    solver_to_physical = topology.array("solver_to_physical_global_dofs")
    inactive = topology.array("inactive_physical_dofs")
    coordinate_scale = topology.solver_coordinate_scaling.array(
        "generalized_from_physical_scale"
    )
    for checkpoint, state in zip(
        checkpoint_chain.checkpoints,
        chain.states,
        strict=True,
    ):
        physical = np.asarray(checkpoint.global_displacements, dtype=float)
        canonical = state.array("canonical_displacement_6dof")
        np.testing.assert_array_equal(
            state.array("physical_displacement_solver_order"),
            physical,
        )
        np.testing.assert_allclose(
            state.array("generalized_coordinates_solver_order"),
            coordinate_scale * physical,
            rtol=0.0,
            atol=2.0e-17,
        )
        np.testing.assert_array_equal(canonical[solver_to_physical], physical)
        np.testing.assert_array_equal(canonical[inactive], 0.0)
        assert state.checkpoint_state_hash == checkpoint.state_hash
        assert state.parent_checkpoint_state_hash == checkpoint.parent_state_hash
        validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint(
            problem,
            topology,
            scaling,
            checkpoint,
            state,
        )


def test_persisted_checkpoint_chain_produces_identical_kinematic_chain() -> None:
    problem, topology, scaling, checkpoint_chain, original = _fixture()
    artifact = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
        problem,
        checkpoint_chain,
    )
    restored_checkpoints = load_stateful_fiber_frame2d_checkpoint_chain_bytes(
        artifact,
        problem,
    )
    restored = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        topology,
        scaling,
        restored_checkpoints,
    )

    assert restored_checkpoints.chain_hash == checkpoint_chain.chain_hash
    assert restored.to_manifest() == original.to_manifest()
    for left, right in zip(original.states, restored.states, strict=True):
        for name in (
            "physical_displacement_solver_order",
            "generalized_coordinates_solver_order",
            "canonical_displacement_6dof",
        ):
            np.testing.assert_array_equal(left.array(name), right.array(name))


def test_state_and_chain_manifests_are_descriptor_only_and_non_authoritative() -> None:
    _problem, _topology, _scaling, _checkpoints, chain = _fixture()
    state_manifest = chain.states[-1].to_manifest()
    chain_manifest = chain.to_manifest()

    assert validate_fiber_frame_nonlinear_kinematic_manifest(state_manifest) == (
        state_manifest
    )
    assert state_manifest["claim_boundary"]["material_state_history_bound"] is False
    assert state_manifest["claim_boundary"]["numerical_result_authority"] is False
    assert chain_manifest["claim_boundary"]["solver_convergence_authority"] is False
    assert "state_bytes" not in str(state_manifest)
    assert "element_states" not in str(chain_manifest)


def test_external_displacement_bytes_are_exactly_bound() -> None:
    _problem, _topology, _scaling, _checkpoints, chain = _fixture()
    state = chain.states[-1]
    name = "canonical_displacement_6dof"
    payload = state.array(name).tobytes(order="C")
    restored = validate_fiber_frame_nonlinear_kinematic_array_bytes(
        state,
        name=name,
        payload=payload,
    )
    np.testing.assert_array_equal(restored, state.array(name))

    tampered = bytearray(payload)
    tampered[-1] ^= 1
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_array_bytes_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_array_bytes(
            state,
            name=name,
            payload=tampered,
        )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_array_hash_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_array_bytes(
            state,
            name=name,
            payload=bytes(tampered),
        )


def test_retained_array_and_authority_tamper_fail_closed() -> None:
    _problem, _topology, _scaling, _checkpoints, chain = _fixture()
    state = chain.states[-1]
    arrays = dict(state._arrays)
    changed = state.array("canonical_displacement_6dof").copy()
    changed[0] += 1.0e-6
    arrays["canonical_displacement_6dof"] = immutable_array(changed, dtype="<f8")
    tampered = replace(state, _arrays=MappingProxyType(arrays))
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_descriptor_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state(tampered)

    promoted = replace(
        state,
        authority_profile="authoritative_nonlinear_kinematic_state",
    )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_authority_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state(promoted)


def test_coherently_rehashed_checkpoint_and_chain_binding_tamper_fail_replay() -> None:
    problem, topology, scaling, checkpoint_chain, chain = _fixture()
    state = chain.states[-1]
    changed_state = replace(
        state,
        source_commitment_hash="sha256:" + "9" * 64,
    )
    changed_state = replace(
        changed_state,
        state_hash=canonical_hash(_state_payload(changed_state, include_hash=False)),
    )
    validate_fiber_frame_nonlinear_kinematic_state(changed_state)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_source_replay_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint(
            problem,
            topology,
            scaling,
            checkpoint_chain.terminal_checkpoint,
            changed_state,
        )

    changed_chain = replace(
        chain,
        checkpoint_chain_hash="sha256:" + "8" * 64,
    )
    changed_chain = replace(
        changed_chain,
        chain_hash=canonical_hash(_chain_payload(changed_chain, include_hash=False)),
    )
    validate_fiber_frame_nonlinear_kinematic_state_chain_shape(changed_chain)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_chain_checkpoint_hash_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain(
            problem,
            topology,
            scaling,
            checkpoint_chain,
            changed_chain,
        )


def test_manifest_authority_and_unknown_field_tamper_fail_closed() -> None:
    _problem, _topology, _scaling, _checkpoints, chain = _fixture()
    manifest = deepcopy(chain.states[-1].to_manifest())
    manifest["authority_profile"] = "authoritative_nonlinear_state"
    unsigned = dict(manifest)
    unsigned.pop("state_hash")
    manifest["state_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_authority_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_manifest(manifest)

    unknown = deepcopy(chain.states[-1].to_manifest())
    unknown["reaction_authority"] = True
    unsigned = dict(unknown)
    unsigned.pop("state_hash")
    unknown["state_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_manifest_fields_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_manifest(unknown)
