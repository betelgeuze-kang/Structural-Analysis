from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from structural_analysis.assembly import (
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_STATE_IR_USAGE_PROFILE,
    create_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    create_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE,
    FiberFrameNonlinearExecutionStateBindingError,
    _binding_payload,
    _epoch_payload,
    create_fiber_frame_nonlinear_execution_state_binding,
    validate_fiber_frame_nonlinear_execution_state_binding,
    validate_fiber_frame_nonlinear_execution_state_binding_manifest,
    validate_fiber_frame_nonlinear_execution_state_binding_shape,
    validate_fiber_frame_nonlinear_execution_state_epoch_binding,
    validate_fiber_frame_nonlinear_execution_state_epoch_binding_manifest,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64
NODE_IDS = ("N1", "N2", "N3")


def _projection(problem, checkpoint_chain, plan, kinematic_chain):
    return create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hashes=kinematic_chain.solver_state_hashes,
    )


def _compose(problem, plan, scaling, checkpoint_chain, kinematic, material):
    return create_fiber_frame_nonlinear_execution_state_binding(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
    )


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
    scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )
    material = _projection(problem, checkpoint_chain, plan, kinematic)
    binding = _compose(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
    )
    return problem, plan, scaling, checkpoint_chain, kinematic, material, binding


def _rehash_epoch(row):
    provisional = replace(row, epoch_binding_hash="sha256:" + "0" * 64)
    return replace(
        provisional,
        epoch_binding_hash=canonical_hash(
            _epoch_payload(provisional, include_epoch_binding_hash=False)
        ),
    )


def _rehash_binding(binding):
    provisional = replace(binding, binding_hash="sha256:" + "0" * 64)
    return replace(
        provisional,
        binding_hash=canonical_hash(
            _binding_payload(provisional, include_binding_hash=False)
        ),
    )


def _rehash_manifest(manifest):
    unsigned = dict(manifest)
    unsigned.pop("binding_hash")
    manifest["binding_hash"] = canonical_hash(unsigned)
    return manifest


def test_complete_scaled_kinematic_material_binding_replays_exactly(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, kinematic, material, binding = artifacts
    second = _compose(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
    )

    assert binding == second
    assert binding.authority_profile == (
        FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE
    )
    assert binding.state_ir_usage_profile == FIBER_FRAME_STATE_IR_USAGE_PROFILE
    assert binding.epoch_count == len(checkpoint_chain.checkpoints) == 3
    assert binding.checkpoint_chain_hash == checkpoint_chain.chain_hash
    assert binding.execution_topology_plan_hash == plan.plan_hash
    assert binding.execution_topology_hash == plan.topology_hash
    assert binding.execution_operator_hash == plan.operator_hash
    assert binding.execution_numeric_buffer_hash == plan.numeric_buffer_hash
    assert binding.solver_coordinate_scaling_hash == (
        plan.solver_coordinate_scaling_hash
    )
    assert binding.physical_equation_scaling_binding_hash == scaling.binding_hash
    assert binding.engine_equation_scaling_hash == scaling.engine_equation_scaling_hash
    assert binding.engine_equation_scaling_source_commitment_hash == (
        scaling.engine_source_commitment_hash
    )
    assert binding.physical_equation_free_dofs_content_hash == (
        scaling.engine_scaling.source_free_dofs_content_hash
    )
    assert binding.physical_equation_scale_vector_content_hash == (
        scaling.engine_scaling.scale_vector_content_hash
    )
    assert binding.kinematic_state_chain_hash == kinematic.chain_hash
    assert binding.material_state_projection_chain_hash == material.chain_hash
    assert binding.solver_state_hashes == kinematic.solver_state_hashes
    assert binding.solver_state_hashes == tuple(
        projection.bundle.solver_state_hash for projection in material.projections
    )
    assert binding.material_state_bundle_hashes == tuple(
        projection.bundle.bundle_hash for projection in material.projections
    )
    assert binding.terminal_material_state_bundle_hash == (
        material.terminal_material_state_bundle_hash
    )
    for index, row in enumerate(binding.epoch_bindings):
        checkpoint = checkpoint_chain.checkpoints[index]
        assert row.checkpoint_state_hash == checkpoint.state_hash
        assert row.committed_kinematic_state_hash == (
            kinematic.committed_states[index].state_hash
        )
        assert row.material_projection_receipt_hash == (
            material.projections[index].receipt.receipt_hash
        )
        assert row.material_solver_state_hash == row.committed_kinematic_state_hash
        assert row.committed_material_state_bundle_hash == (
            material.projections[index].bundle.bundle_hash
        )

    manifest = binding.to_manifest()
    assert manifest["claim_boundary"]["physical_equation_scaling_bound"] is True
    assert manifest["claim_boundary"]["state_ir_v1_emitted"] is False
    assert manifest["claim_boundary"]["state_ir_v1_authority_overridden"] is False
    assert manifest["claim_boundary"]["nonlinear_numerical_result_authority"] is False
    assert manifest["claim_boundary"]["result_ir_authority"] is False
    assert "converged" not in repr(manifest)
    assert (
        validate_fiber_frame_nonlinear_execution_state_binding_manifest(manifest)
        == manifest
    )
    for row in manifest["epoch_bindings"]:
        assert (
            validate_fiber_frame_nonlinear_execution_state_epoch_binding_manifest(row)
            == row
        )
    validate_fiber_frame_nonlinear_execution_state_binding(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
        binding,
    )


def test_persisted_checkpoint_roundtrip_rebuilds_identical_binding(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, _, _, binding = artifacts
    payload = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
        problem,
        checkpoint_chain,
    )
    restored = load_stateful_fiber_frame2d_checkpoint_chain_bytes(payload, problem)
    restored_kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        restored,
    )
    restored_material = _projection(
        problem,
        restored,
        plan,
        restored_kinematic,
    )
    restored_binding = _compose(
        problem,
        plan,
        scaling,
        restored,
        restored_kinematic,
        restored_material,
    )

    assert restored.chain_hash == checkpoint_chain.chain_hash
    assert restored_binding == binding
    assert restored_binding.binding_hash == binding.binding_hash
    assert restored_binding.to_manifest() == binding.to_manifest()


def test_material_solver_state_sequence_must_equal_j3_states(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, kinematic, _, _ = artifacts
    wrong_hashes = tuple("sha256:" + character * 64 for character in ("7", "8", "9"))
    independently_valid_material = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hashes=wrong_hashes,
    )

    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_solver_state_history_mismatch",
    ):
        _compose(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            independently_valid_material,
        )


@pytest.mark.parametrize(
    ("model_hash", "plan_hash"),
    (
        ("sha256:" + "a" * 64, None),
        (None, "sha256:" + "b" * 64),
    ),
)
def test_material_chain_must_share_exact_model_and_plan(
    artifacts,
    model_hash,
    plan_hash,
) -> None:
    problem, plan, scaling, checkpoint_chain, kinematic, _, _ = artifacts
    independently_valid_material = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=model_hash or plan.model_ir_content_hash,
        execution_plan_hash=plan_hash or plan.plan_hash,
        solver_state_hashes=kinematic.solver_state_hashes,
    )

    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_source_binding_mismatch",
    ):
        _compose(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            independently_valid_material,
        )


def test_wrong_checkpoint_or_kinematic_ancestry_fails_closed(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, _, material, _ = artifacts
    other_path = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.2, 0.4),
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    assert other_path.contract_pass is True
    other_checkpoints = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        (
            other_path.initial_checkpoint,
            *(step.accepted_checkpoint for step in other_path.steps),
        ),
    )
    other_kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        other_checkpoints,
    )

    with pytest.raises(ValueError):
        _compose(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            other_kinematic,
            material,
        )


def test_coherently_rehashed_outer_source_substitution_fails_replay(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, kinematic, material, binding = artifacts
    tampered = replace(
        binding,
        material_state_projection_chain_hash="sha256:" + "f" * 64,
    )
    tampered = _rehash_binding(tampered)

    validate_fiber_frame_nonlinear_execution_state_binding_shape(tampered)
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_source_replay_mismatch",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            tampered,
        )


def test_coherent_epoch_state_substitution_passes_shape_but_fails_replay(
    artifacts,
) -> None:
    problem, plan, scaling, checkpoint_chain, kinematic, material, binding = artifacts
    changed_row = _rehash_epoch(
        replace(
            binding.epoch_bindings[-1],
            committed_kinematic_state_hash="sha256:" + "e" * 64,
            material_solver_state_hash="sha256:" + "e" * 64,
        )
    )
    changed = replace(
        binding,
        terminal_kinematic_state_hash=changed_row.committed_kinematic_state_hash,
        epoch_bindings=(*binding.epoch_bindings[:-1], changed_row),
    )
    changed = _rehash_binding(changed)

    validate_fiber_frame_nonlinear_execution_state_binding_shape(changed)
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_source_replay_mismatch",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            changed,
        )


def test_coherent_cross_epoch_ancestry_substitution_fails_shape(artifacts) -> None:
    *_, binding = artifacts
    changed_row = _rehash_epoch(
        replace(
            binding.epoch_bindings[-1],
            accepted_material_state_bundle_hash="sha256:" + "d" * 64,
        )
    )
    changed = replace(
        binding,
        epoch_bindings=(*binding.epoch_bindings[:-1], changed_row),
    )
    changed = _rehash_binding(changed)

    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_epoch_ancestry_mismatch",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_shape(changed)


def test_epoch_solver_equality_and_lifecycle_distinctness_fail_closed(
    artifacts,
) -> None:
    *_, binding = artifacts
    row = binding.epoch_bindings[-1]
    wrong_solver = _rehash_epoch(
        replace(row, material_solver_state_hash="sha256:" + "c" * 64)
    )
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_epoch_binding_solver_state_mismatch",
    ):
        validate_fiber_frame_nonlinear_execution_state_epoch_binding(wrong_solver)

    collapsed_trial = _rehash_epoch(
        replace(
            row,
            trial_kinematic_state_hash=row.accepted_kinematic_state_hash,
        )
    )
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_epoch_binding_lifecycle_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_epoch_binding(collapsed_trial)


def test_authority_state_ir_and_manifest_claim_promotion_fail_closed(
    artifacts,
) -> None:
    *_, binding = artifacts
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_authority_profile_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_shape(
            replace(binding, authority_profile="authoritative_nonlinear_result")
        )
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_state_ir_usage_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_shape(
            replace(binding, state_ir_usage_profile="state_ir_v1_complete_state")
        )

    promoted = deepcopy(binding.to_manifest())
    promoted["claim_boundary"]["result_ir_authority"] = True
    _rehash_manifest(promoted)
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_claim_boundary_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_manifest(promoted)


def test_manifest_scalar_container_and_key_types_are_exact(artifacts) -> None:
    *_, binding = artifacts
    wrong_count = deepcopy(binding.to_manifest())
    wrong_count["epoch_count"] = True
    _rehash_manifest(wrong_count)
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_index_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_manifest(wrong_count)

    wrong_nodes = deepcopy(binding.to_manifest())
    wrong_nodes["bindings"]["node_ids"] = tuple(wrong_nodes["bindings"]["node_ids"])
    _rehash_manifest(wrong_nodes)
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_node_ids_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_manifest(wrong_nodes)

    extra_key = deepcopy(binding.to_manifest())
    extra_key["terminal"] = True
    _rehash_manifest(extra_key)
    with pytest.raises(
        FiberFrameNonlinearExecutionStateBindingError,
        match="fiber_frame_nonlinear_binding_manifest_keys_invalid",
    ):
        validate_fiber_frame_nonlinear_execution_state_binding_manifest(extra_key)


def test_prefix_epoch_bindings_are_append_stable(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, _, _, binding = artifacts
    prefix_checkpoints = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        checkpoint_chain.checkpoints[:2],
    )
    prefix_kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        prefix_checkpoints,
    )
    prefix_material = _projection(
        problem,
        prefix_checkpoints,
        plan,
        prefix_kinematic,
    )
    prefix_binding = _compose(
        problem,
        plan,
        scaling,
        prefix_checkpoints,
        prefix_kinematic,
        prefix_material,
    )

    assert prefix_binding.checkpoint_chain_hash != binding.checkpoint_chain_hash
    assert prefix_binding.binding_hash != binding.binding_hash
    assert prefix_binding.epoch_bindings == binding.epoch_bindings[:2]
    assert prefix_binding.solver_state_hashes == binding.solver_state_hashes[:2]


def test_physical_equation_scaling_identity_changes_final_binding(artifacts) -> None:
    problem, plan, scaling, checkpoint_chain, kinematic, material, binding = artifacts
    changed_scaling = create_stateful_fiber_frame2d_physical_equation_scaling(
        problem,
        plan,
        minimum_reference_force_n=scaling.reference_force_n * 10.0,
    )
    changed = _compose(
        problem,
        plan,
        changed_scaling,
        checkpoint_chain,
        kinematic,
        material,
    )

    assert changed_scaling.binding_hash != scaling.binding_hash
    assert changed.engine_equation_scaling_hash != binding.engine_equation_scaling_hash
    assert changed.physical_equation_scale_vector_content_hash != (
        binding.physical_equation_scale_vector_content_hash
    )
    assert changed.binding_hash != binding.binding_hash
    assert changed.epoch_bindings != binding.epoch_bindings


def test_single_genesis_checkpoint_composes_without_fake_trials() -> None:
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
    scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )
    material = _projection(problem, checkpoint_chain, plan, kinematic)
    binding = _compose(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
    )

    assert binding.epoch_count == 1
    row = binding.epoch_bindings[0]
    assert row.parent_checkpoint_state_hash is None
    assert row.accepted_kinematic_state_hash is None
    assert row.trial_kinematic_state_hash is None
    assert row.accepted_material_state_bundle_hash is None
    assert row.trial_material_state_bundle_hash is None
    assert binding.root_checkpoint_state_hash == binding.terminal_checkpoint_state_hash
    assert binding.root_kinematic_state_hash == binding.terminal_kinematic_state_hash
    assert binding.root_material_state_bundle_hash == (
        binding.terminal_material_state_bundle_hash
    )
