from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly import (
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    initial_stateful_fiber_frame2d_checkpoint,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
    physical_3dof_to_canonical_6dof,
    physical_3dof_to_solver_generalized,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
    FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE,
    FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE,
    FIBER_FRAME_STATE_IR_USAGE_PROFILE,
    FiberFrameNonlinearKinematicStateError,
    _array_descriptor,
    _chain_payload,
    _state_payload,
    _transition_payload,
    create_fiber_frame_nonlinear_kinematic_state_chain,
    validate_fiber_frame_nonlinear_kinematic_state_array_bytes,
    validate_fiber_frame_nonlinear_kinematic_state_chain,
    validate_fiber_frame_nonlinear_kinematic_state_chain_manifest,
    validate_fiber_frame_nonlinear_kinematic_state_chain_shape,
    validate_fiber_frame_nonlinear_kinematic_state_manifest,
    validate_fiber_frame_nonlinear_kinematic_state_shape,
    validate_fiber_frame_nonlinear_kinematic_transition_receipt,
)
from structural_analysis.benchmark import (
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64
NODE_IDS = ("N1", "N2", "N3")


@pytest.fixture(scope="module")
def artifacts():
    problem = make_two_member_stateful_fiber_l_frame()
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5),
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    assert path.contract_pass is True
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        (
            path.initial_checkpoint,
            *(step.accepted_checkpoint for step in path.steps),
        ),
    )
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    chain = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )
    return problem, plan, checkpoint_chain, chain


def _rehash_state(state):
    return replace(
        state,
        state_hash=canonical_hash(_state_payload(state, include_state_hash=False)),
    )


def _rehash_transition(receipt):
    return replace(
        receipt,
        transition_hash=canonical_hash(
            _transition_payload(receipt, include_transition_hash=False)
        ),
    )


def _rehash_chain(chain):
    return replace(
        chain,
        chain_hash=canonical_hash(_chain_payload(chain, include_chain_hash=False)),
    )


def test_checkpoint_chain_maps_to_one_committed_state_per_checkpoint(artifacts) -> None:
    problem, plan, checkpoint_chain, chain = artifacts

    assert chain.authority_profile == FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE
    assert chain.carrier_profile == FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE
    assert chain.lifecycle_profile == FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE
    assert chain.state_ir_usage_profile == FIBER_FRAME_STATE_IR_USAGE_PROFILE
    assert chain.checkpoint_chain_hash == checkpoint_chain.chain_hash
    assert chain.execution_topology_plan_hash == plan.plan_hash
    assert chain.solver_coordinate_scaling_hash == plan.solver_coordinate_scaling_hash
    assert chain.state_count == len(checkpoint_chain.checkpoints) == 3
    assert chain.transition_count == chain.state_count - 1 == 2
    assert len(chain.solver_state_hashes) == chain.state_count
    assert chain.solver_state_hashes == tuple(
        state.state_hash for state in chain.committed_states
    )

    inactive = plan.array("inactive_physical_dofs")
    for index, (checkpoint, state) in enumerate(
        zip(checkpoint_chain.checkpoints, chain.committed_states, strict=True)
    ):
        assert state.role == "committed"
        assert state.epoch == state.step_index == checkpoint.epoch == index
        assert state.checkpoint_state_hash == checkpoint.state_hash
        assert state.parent_checkpoint_state_hash == checkpoint.parent_state_hash
        physical = state.array("checkpoint_displacement_physical_3dof")
        np.testing.assert_array_equal(physical, checkpoint.global_displacements)
        np.testing.assert_array_equal(
            state.array("canonical_displacement_si"),
            physical_3dof_to_canonical_6dof(plan, physical),
        )
        np.testing.assert_array_equal(
            state.array("solver_generalized_coordinates_m"),
            physical_3dof_to_solver_generalized(plan, physical),
        )
        np.testing.assert_array_equal(
            state.array("canonical_displacement_si")[inactive],
            0.0,
        )
    validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
        chain,
    )


def test_positive_epochs_replay_transient_trial_then_committed(artifacts) -> None:
    _, _, checkpoint_chain, chain = artifacts

    assert chain.committed_states[0].parent_state_hash is None
    for index, receipt in enumerate(chain.transitions, start=1):
        accepted = chain.committed_states[index - 1]
        committed = chain.committed_states[index]
        assert receipt.epoch == index
        assert receipt.parent_checkpoint_state_hash == (
            checkpoint_chain.checkpoints[index - 1].state_hash
        )
        assert receipt.checkpoint_state_hash == (
            checkpoint_chain.checkpoints[index].state_hash
        )
        assert receipt.accepted_state_hash == accepted.state_hash
        assert receipt.trial_state_hash == committed.parent_state_hash
        assert receipt.committed_state_hash == committed.state_hash
        assert (
            len(
                {
                    receipt.accepted_state_hash,
                    receipt.trial_state_hash,
                    receipt.committed_state_hash,
                }
            )
            == 3
        )
        validate_fiber_frame_nonlinear_kinematic_transition_receipt(receipt)


def test_epoch_zero_is_exact_zero_and_state_ir_authority_is_not_emitted(
    artifacts,
) -> None:
    _, _, _, chain = artifacts
    root = chain.committed_states[0]
    manifest = chain.to_manifest()
    state_claims = root.to_manifest()["claim_boundary"]
    transition_claims = chain.transitions[0].to_manifest()["claim_boundary"]

    assert root.role == "committed"
    assert root.epoch == root.step_index == 0
    assert root.load_factor == 0.0
    assert root.parent_state_hash is None
    assert root.parent_checkpoint_state_hash is None
    for name in (
        "checkpoint_displacement_physical_3dof",
        "solver_generalized_coordinates_m",
        "canonical_displacement_si",
    ):
        np.testing.assert_array_equal(root.array(name), 0.0)
    assert manifest["claim_boundary"]["state_ir_v1_object_emitted"] is False
    assert manifest["claim_boundary"]["state_ir_v1_complete_state_claim"] is False
    assert manifest["claim_boundary"]["constitutive_state_history_bound"] is False
    assert manifest["claim_boundary"]["solver_convergence_authority"] is False
    assert state_claims["complete_checkpoint_chain_bound"] is False
    assert state_claims["trial_commit_lifecycle_replayed"] is False
    assert transition_claims["complete_checkpoint_chain_bound"] is False
    assert transition_claims["trial_state_payload_replayed_by_receipt_alone"] is False
    assert "stateless_linear_elastic" not in str(manifest)
    assert "'constitutive_state':" not in str(manifest)
    assert "velocity_si" not in str(manifest)
    assert "acceleration_si" not in str(manifest)


def test_persisted_checkpoint_roundtrip_produces_identical_state_chain(
    artifacts,
) -> None:
    problem, plan, checkpoint_chain, chain = artifacts
    encoded = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
        problem,
        checkpoint_chain,
    )
    restored = load_stateful_fiber_frame2d_checkpoint_chain_bytes(encoded, problem)
    replayed = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        restored,
    )

    assert restored.chain_hash == checkpoint_chain.chain_hash
    assert replayed == chain
    assert replayed.chain_hash == chain.chain_hash
    assert replayed.to_manifest() == chain.to_manifest()
    for actual, expected in zip(
        replayed.committed_states,
        chain.committed_states,
        strict=True,
    ):
        for name in (
            "checkpoint_displacement_physical_3dof",
            "solver_generalized_coordinates_m",
            "canonical_displacement_si",
        ):
            np.testing.assert_array_equal(actual.array(name), expected.array(name))


def test_extending_checkpoint_chain_preserves_existing_state_and_transition_hashes(
    artifacts,
) -> None:
    problem, plan, checkpoint_chain, full_chain = artifacts
    prefix_checkpoints = checkpoint_chain.checkpoints[:2]
    prefix_source = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        prefix_checkpoints,
    )
    prefix_chain = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        prefix_source,
    )

    assert prefix_chain.checkpoint_chain_hash != full_chain.checkpoint_chain_hash
    assert prefix_chain.chain_hash != full_chain.chain_hash
    assert prefix_chain.solver_state_hashes == full_chain.solver_state_hashes[:2]
    assert prefix_chain.transitions[0].transition_hash == (
        full_chain.transitions[0].transition_hash
    )


def test_state_arrays_are_immutable_and_external_bytes_fail_closed(artifacts) -> None:
    _, _, _, chain = artifacts
    state = chain.committed_states[-1]
    for descriptor in state.descriptors:
        array = state.array(descriptor.name)
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array.setflags(write=True)
        restored = validate_fiber_frame_nonlinear_kinematic_state_array_bytes(
            state,
            name=descriptor.name,
            payload=array.tobytes(order="C"),
        )
        np.testing.assert_array_equal(restored, array)

    name = "canonical_displacement_si"
    raw = bytearray(state.array(name).tobytes(order="C"))
    raw[-1] ^= 1
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_array_bytes_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_array_bytes(
            state,
            name=name,
            payload=raw,
        )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_array_hash_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_array_bytes(
            state,
            name=name,
            payload=bytes(raw),
        )


def test_node_identity_changes_state_chain_identity_without_changing_checkpoints(
    artifacts,
) -> None:
    problem, plan, checkpoint_chain, chain = artifacts
    renamed_plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("A", "B", "C"),
    )
    renamed = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        renamed_plan,
        checkpoint_chain,
    )

    assert renamed.checkpoint_chain_hash == chain.checkpoint_chain_hash
    assert renamed.execution_topology_plan_hash != plan.plan_hash
    assert renamed.committed_states[-1].checkpoint_state_hash == (
        chain.committed_states[-1].checkpoint_state_hash
    )
    assert renamed.committed_states[-1].state_hash != (
        chain.committed_states[-1].state_hash
    )
    assert renamed.chain_hash != chain.chain_hash


def test_wrong_plan_checkpoint_ancestry_and_problem_fail_closed(artifacts) -> None:
    problem, plan, checkpoint_chain, chain = artifacts
    renamed_plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("A", "B", "C"),
    )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_chain_source_binding_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain(
            problem,
            renamed_plan,
            checkpoint_chain,
            chain,
        )

    other_path = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.2, 0.4),
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    assert other_path.contract_pass is True
    other_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        (
            other_path.initial_checkpoint,
            *(step.accepted_checkpoint for step in other_path.steps),
        ),
    )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_chain_source_binding_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain(
            problem,
            plan,
            other_chain,
            chain,
        )

    other_problem = make_two_element_stateful_fiber_cantilever()
    with pytest.raises(ValueError):
        validate_fiber_frame_nonlinear_kinematic_state_chain(
            other_problem,
            plan,
            checkpoint_chain,
            chain,
        )


def test_authority_carrier_and_lifecycle_promotion_fail_closed(artifacts) -> None:
    _, _, _, chain = artifacts
    promoted_chain = replace(chain, authority_profile="authoritative_result_state")
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_authority_profile_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain_shape(promoted_chain)

    promoted_state = replace(
        chain.committed_states[-1],
        state_ir_usage_profile="state_ir_v1_complete_nonlinear_state",
    )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_ir_usage_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_shape(promoted_state)

    promoted_transition = replace(
        chain.transitions[-1],
        lifecycle_profile="authoritative_nonlinear_commit",
    )
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_lifecycle_profile_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_transition_receipt(promoted_transition)


def test_coherently_rehashed_canonical_inactive_dof_tamper_fails_shape(
    artifacts,
) -> None:
    _, _, _, chain = artifacts
    state = chain.committed_states[-1]
    arrays = dict(state._arrays)
    canonical = state.array("canonical_displacement_si").copy()
    canonical[2] = 1.0e-12
    arrays["canonical_displacement_si"] = immutable_array(canonical, dtype="<f8")
    frozen = MappingProxyType(arrays)
    changed = replace(
        state,
        _arrays=frozen,
        descriptors=tuple(
            _array_descriptor(name, frozen[name], state.node_ids) for name in arrays
        ),
        state_hash="sha256:" + "0" * 64,
    )
    changed = _rehash_state(changed)

    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_canonical_mapping_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_shape(changed)


def test_coherent_displacement_tamper_passes_shape_but_fails_source_replay(
    artifacts,
) -> None:
    problem, plan, checkpoint_chain, chain = artifacts
    state = chain.committed_states[-1]
    physical = state.array("checkpoint_displacement_physical_3dof").copy()
    physical[int(problem.free_global_dofs[0])] += 1.0e-7
    arrays = MappingProxyType(
        {
            "checkpoint_displacement_physical_3dof": immutable_array(
                physical,
                dtype="<f8",
            ),
            "solver_generalized_coordinates_m": physical_3dof_to_solver_generalized(
                plan,
                physical,
            ),
            "canonical_displacement_si": physical_3dof_to_canonical_6dof(
                plan,
                physical,
            ),
        }
    )
    changed_state = replace(
        state,
        _arrays=arrays,
        descriptors=tuple(
            _array_descriptor(name, arrays[name], state.node_ids) for name in arrays
        ),
        state_hash="sha256:" + "0" * 64,
    )
    changed_state = _rehash_state(changed_state)
    receipt = replace(
        chain.transitions[-1],
        committed_state_hash=changed_state.state_hash,
        transition_hash="sha256:" + "0" * 64,
    )
    receipt = _rehash_transition(receipt)
    states = (*chain.committed_states[:-1], changed_state)
    transitions = (*chain.transitions[:-1], receipt)
    changed_chain = replace(
        chain,
        committed_states=states,
        transitions=transitions,
        terminal_kinematic_state_hash=changed_state.state_hash,
        chain_hash="sha256:" + "0" * 64,
    )
    changed_chain = _rehash_chain(changed_chain)

    validate_fiber_frame_nonlinear_kinematic_state_chain_shape(changed_chain)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_checkpoint_displacement_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain(
            problem,
            plan,
            checkpoint_chain,
            changed_chain,
        )


def test_coherent_solver_state_ancestry_tamper_fails_replay(artifacts) -> None:
    problem, plan, checkpoint_chain, chain = artifacts
    state = chain.committed_states[-1]
    changed_state = replace(
        state,
        parent_state_hash="sha256:" + "9" * 64,
        state_hash="sha256:" + "0" * 64,
    )
    changed_state = _rehash_state(changed_state)
    receipt = replace(
        chain.transitions[-1],
        trial_state_hash=changed_state.parent_state_hash,
        committed_state_hash=changed_state.state_hash,
        transition_hash="sha256:" + "0" * 64,
    )
    receipt = _rehash_transition(receipt)
    changed_chain = replace(
        chain,
        committed_states=(*chain.committed_states[:-1], changed_state),
        transitions=(*chain.transitions[:-1], receipt),
        terminal_kinematic_state_hash=changed_state.state_hash,
        chain_hash="sha256:" + "0" * 64,
    )
    changed_chain = _rehash_chain(changed_chain)

    validate_fiber_frame_nonlinear_kinematic_state_chain_shape(changed_chain)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_chain_state_replay_mismatch",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain(
            problem,
            plan,
            checkpoint_chain,
            changed_chain,
        )


def test_descriptor_only_manifests_validate_and_semantic_tamper_fails(
    artifacts,
) -> None:
    _, _, _, chain = artifacts
    manifest = chain.to_manifest()
    state_manifest = deepcopy(manifest["committed_states"][-1])

    assert validate_fiber_frame_nonlinear_kinematic_state_chain_manifest(manifest) == (
        manifest
    )
    assert validate_fiber_frame_nonlinear_kinematic_state_manifest(state_manifest) == (
        state_manifest
    )

    state_manifest["layout"]["canonical_components"] = ["BAD"]
    unsigned_state = dict(state_manifest)
    unsigned_state.pop("state_hash")
    state_manifest["state_hash"] = canonical_hash(unsigned_state)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_layout_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_manifest(state_manifest)

    promoted = deepcopy(manifest)
    promoted["claim_boundary"]["nonlinear_numerical_result_authority"] = True
    unsigned_chain = dict(promoted)
    unsigned_chain.pop("chain_hash")
    promoted["chain_hash"] = canonical_hash(unsigned_chain)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_claim_boundary_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain_manifest(promoted)


def test_exact_scalar_and_container_types_fail_closed(artifacts) -> None:
    _, _, _, chain = artifacts
    state = chain.committed_states[-1]
    invalid_epoch = replace(state, epoch=True)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_index_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_shape(invalid_epoch)

    mutable_arrays = replace(state, _arrays=dict(state._arrays))
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_state_array_map_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_shape(mutable_arrays)

    list_node_ids = replace(state, node_ids=list(state.node_ids))
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_stable_id_tuple_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_shape(list_node_ids)

    manifest = deepcopy(state.to_manifest())
    manifest["coordinates"]["epoch"] = float(state.epoch)
    unsigned = dict(manifest)
    unsigned.pop("state_hash")
    manifest["state_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_index_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_manifest(manifest)

    oversized = replace(chain, state_count=257)
    with pytest.raises(
        FiberFrameNonlinearKinematicStateError,
        match="fiber_frame_kinematic_chain_state_count_invalid",
    ):
        validate_fiber_frame_nonlinear_kinematic_state_chain_shape(oversized)


def test_single_genesis_checkpoint_chain_is_supported() -> None:
    problem = make_two_member_stateful_fiber_l_frame()
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        (initial_stateful_fiber_frame2d_checkpoint(problem),),
    )
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    chain = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )

    assert chain.state_count == 1
    assert chain.transition_count == 0
    assert chain.transitions == ()
    assert chain.root_checkpoint_state_hash == chain.terminal_checkpoint_state_hash
    assert chain.root_kinematic_state_hash == chain.terminal_kinematic_state_hash
    validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
        chain,
    )
