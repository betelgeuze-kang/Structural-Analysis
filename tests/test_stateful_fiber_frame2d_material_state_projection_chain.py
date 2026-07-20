from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.assembly import (
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_bundle import (
    FiberFrameMaterialStateProjectionError,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_AUTHORITY_PROFILE,
    _chain_payload,
    create_fiber_frame_material_state_projection_chain,
    validate_fiber_frame_material_state_projection_chain,
    validate_fiber_frame_material_state_projection_chain_shape,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64
PLAN_HASH = "sha256:" + "2" * 64
SOLVER_STATE_HASHES = tuple("sha256:" + character * 64 for character in ("3", "4", "5"))


def _checkpoint_chain():
    problem = make_two_member_stateful_fiber_l_frame()
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
    return problem, make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        checkpoints,
    )


def test_complete_checkpoint_chain_projects_and_replays_exactly() -> None:
    problem, checkpoint_chain = _checkpoint_chain()
    first = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=SOLVER_STATE_HASHES,
    )
    second = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=SOLVER_STATE_HASHES,
    )

    assert first == second
    assert first.authority_profile == (
        FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_AUTHORITY_PROFILE
    )
    assert first.checkpoint_chain_hash == checkpoint_chain.chain_hash
    assert first.problem_contract_hash == problem.contract_hash
    assert first.projection_count == len(checkpoint_chain.checkpoints) == 3
    assert [row.bundle.epoch for row in first.projections] == [0, 1, 2]
    assert [row.bundle.solver_state_hash for row in first.projections] == list(
        SOLVER_STATE_HASHES
    )
    assert first.root_checkpoint_state_hash == (
        checkpoint_chain.root_checkpoint.state_hash
    )
    assert first.terminal_checkpoint_state_hash == (
        checkpoint_chain.terminal_checkpoint.state_hash
    )
    assert first.terminal_material_state_bundle_hash == (
        first.projections[-1].bundle.bundle_hash
    )
    assert [row.receipt.parent_checkpoint_state_hash for row in first.projections] == [
        None,
        checkpoint_chain.checkpoints[0].state_hash,
        checkpoint_chain.checkpoints[1].state_hash,
    ]
    assert first.to_manifest()["claim_boundary"]["numerical_result_authority"] is False
    assert all(
        "state_bytes" not in entry
        for projection in first.to_manifest()["projections"]
        for entry in projection["material_state_bundle"]["entries"]
    )
    validate_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        first,
    )


def test_persisted_checkpoint_chain_produces_same_material_projection_chain() -> None:
    problem, checkpoint_chain = _checkpoint_chain()
    artifact = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
        problem,
        checkpoint_chain,
    )
    restored = load_stateful_fiber_frame2d_checkpoint_chain_bytes(
        artifact,
        problem,
    )
    original_projection = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=SOLVER_STATE_HASHES,
    )
    restored_projection = create_fiber_frame_material_state_projection_chain(
        problem,
        restored,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=SOLVER_STATE_HASHES,
    )

    assert restored.chain_hash == checkpoint_chain.chain_hash
    assert restored_projection == original_projection
    assert restored_projection.chain_hash == original_projection.chain_hash
    assert restored_projection.to_manifest() == original_projection.to_manifest()


def test_solver_state_hash_sequence_is_exactly_bounded_to_checkpoint_count() -> None:
    problem, checkpoint_chain = _checkpoint_chain()
    for invalid in (
        SOLVER_STATE_HASHES[:-1],
        (*SOLVER_STATE_HASHES, "sha256:" + "6" * 64),
    ):
        with pytest.raises(
            FiberFrameMaterialStateProjectionError,
            match="fiber_frame_projection_chain_solver_hash_count_mismatch",
        ):
            create_fiber_frame_material_state_projection_chain(
                problem,
                checkpoint_chain,
                model_ir_content_hash=MODEL_HASH,
                execution_plan_hash=PLAN_HASH,
                solver_state_hashes=invalid,
            )


def test_solver_state_history_changes_projection_chain_identity() -> None:
    problem, checkpoint_chain = _checkpoint_chain()
    first = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=SOLVER_STATE_HASHES,
    )
    changed_hashes = (
        SOLVER_STATE_HASHES[0],
        SOLVER_STATE_HASHES[1],
        "sha256:" + "9" * 64,
    )
    changed = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=changed_hashes,
    )

    assert first.checkpoint_chain_hash == changed.checkpoint_chain_hash
    assert first.projections[-1].receipt.checkpoint_state_hash == (
        changed.projections[-1].receipt.checkpoint_state_hash
    )
    assert first.projections[-1].bundle.solver_state_hash != (
        changed.projections[-1].bundle.solver_state_hash
    )
    assert first.chain_hash != changed.chain_hash


def test_projection_chain_authority_and_coherent_ancestry_tamper_fail_closed() -> None:
    problem, checkpoint_chain = _checkpoint_chain()
    projected = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hashes=SOLVER_STATE_HASHES,
    )
    promoted = replace(
        projected,
        authority_profile="authoritative_nonlinear_material_history",
    )
    with pytest.raises(
        FiberFrameMaterialStateProjectionError,
        match="fiber_frame_projection_chain_authority_profile_invalid",
    ):
        validate_fiber_frame_material_state_projection_chain_shape(promoted)

    tampered = replace(
        projected,
        checkpoint_chain_hash="sha256:" + "f" * 64,
    )
    coherently_rehashed = replace(
        tampered,
        chain_hash=canonical_hash(_chain_payload(tampered, include_chain_hash=False)),
    )
    validate_fiber_frame_material_state_projection_chain_shape(coherently_rehashed)
    with pytest.raises(
        FiberFrameMaterialStateProjectionError,
        match="fiber_frame_projection_chain_checkpoint_hash_mismatch",
    ):
        validate_fiber_frame_material_state_projection_chain(
            problem,
            checkpoint_chain,
            coherently_rehashed,
        )
