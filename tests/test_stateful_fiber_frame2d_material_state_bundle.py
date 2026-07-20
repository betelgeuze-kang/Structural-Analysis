from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.assembly import (
    dump_stateful_fiber_frame2d_checkpoint_bytes,
    initial_stateful_fiber_frame2d_checkpoint,
    load_stateful_fiber_frame2d_checkpoint_bytes,
    solve_stateful_fiber_frame2d_load_step,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_bundle import (
    FIBER_FRAME_MATERIAL_STATE_AUTHORITY_PROFILE,
    FiberFrameMaterialStateProjectionError,
    advance_fiber_frame_material_state_projection,
    create_initial_fiber_frame_material_state_projection,
    validate_fiber_frame_material_state_projection,
)
from structural_analysis.benchmark import (
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64
PLAN_HASH = "sha256:" + "2" * 64
STATE_E0_HASH = "sha256:" + "3" * 64
STATE_E1_HASH = "sha256:" + "4" * 64
STATE_E2_HASH = "sha256:" + "5" * 64


def _constituent_states(checkpoint):
    return tuple(
        fiber_state
        for element_state in checkpoint.element_states
        for section_state in element_state.integration_point_states
        for fiber_state in section_state.fiber_states
    )


def _expected_integration_point_count(problem) -> int:
    return sum(member.element.integration_order for member in problem.members)


def test_initial_projection_is_deterministic_ordered_and_descriptor_only() -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    frame_checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)

    first = create_initial_fiber_frame_material_state_projection(
        problem,
        frame_checkpoint,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )
    second = create_initial_fiber_frame_material_state_projection(
        problem,
        frame_checkpoint,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )

    states = _constituent_states(frame_checkpoint)
    assert first == second
    assert first.receipt.authority_profile == (
        FIBER_FRAME_MATERIAL_STATE_AUTHORITY_PROFILE
    )
    assert first.receipt.problem_contract_hash == problem.contract_hash
    assert first.receipt.checkpoint_state_hash == frame_checkpoint.state_hash
    assert first.receipt.checkpoint_epoch == 0
    assert first.receipt.parent_checkpoint_state_hash is None
    assert first.receipt.trial_bundle_hash is None
    assert first.receipt.member_count == len(problem.members)
    assert first.receipt.beam_integration_point_count == (
        _expected_integration_point_count(problem)
    )
    assert first.receipt.fiber_state_count == len(states)
    assert first.bundle.entry_count == len(states)
    assert first.bundle.epoch == 0
    assert first.bundle.role == "committed"
    assert first.bundle.model_ir_content_hash == MODEL_HASH
    assert first.bundle.execution_plan_hash == PLAN_HASH
    assert first.bundle.solver_state_hash == STATE_E0_HASH
    assert [row.data_hash for row in first.bundle.entries] == [
        state.state_hash for state in states
    ]
    assert [row.entity_id for row in first.bundle.entries] == sorted(
        row.entity_id for row in first.bundle.entries
    )
    manifest = first.to_manifest()
    assert manifest["claim_boundary"]["numerical_result_authority"] is False
    assert manifest["claim_boundary"]["constitutive_law_replayed"] is False
    assert all(
        "state_bytes" not in entry
        for entry in manifest["material_state_bundle"]["entries"]
    )
    validate_fiber_frame_material_state_projection(
        problem,
        frame_checkpoint,
        first,
    )


def test_initial_projection_rejects_non_genesis_epoch_zero_material_history() -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)
    element = checkpoint.element_states[0]
    section = element.integration_point_states[0]
    fiber_state = section.fiber_states[0]
    altered_fiber_state = replace(
        fiber_state,
        dissipated_energy_density_mj_per_m3=1.0,
    )
    altered_section = replace(
        section,
        fiber_states=(altered_fiber_state, *section.fiber_states[1:]),
    )
    altered_element = replace(
        element,
        integration_point_states=(
            altered_section,
            *element.integration_point_states[1:],
        ),
    )
    non_genesis = replace(
        checkpoint,
        element_states=(altered_element, *checkpoint.element_states[1:]),
        state_hash="",
    )

    with pytest.raises(
        FiberFrameMaterialStateProjectionError,
        match="fiber_frame_projection_initial_checkpoint_mismatch",
    ):
        create_initial_fiber_frame_material_state_projection(
            problem,
            non_genesis,
            model_ir_content_hash=MODEL_HASH,
            execution_plan_hash=PLAN_HASH,
            solver_state_hash=STATE_E0_HASH,
        )


def test_committed_checkpoint_projection_binds_parent_entries_and_persistence() -> None:
    problem = make_two_member_stateful_fiber_l_frame()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    accepted = create_initial_fiber_frame_material_state_projection(
        problem,
        parent,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )
    step = solve_stateful_fiber_frame2d_load_step(
        problem,
        parent,
        target_load_factor=0.25,
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    assert step.committed is True
    child = step.accepted_checkpoint

    first = advance_fiber_frame_material_state_projection(
        problem,
        parent,
        child,
        accepted,
        solver_state_hash=STATE_E1_HASH,
    )
    artifact = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, child)
    restored = load_stateful_fiber_frame2d_checkpoint_bytes(artifact, problem)
    replay = advance_fiber_frame_material_state_projection(
        problem,
        parent,
        restored,
        accepted,
        solver_state_hash=STATE_E1_HASH,
    )

    assert first == replay
    assert first.receipt.checkpoint_state_hash == child.state_hash
    assert first.receipt.parent_checkpoint_state_hash == parent.state_hash
    assert first.receipt.trial_bundle_hash == first.bundle.parent_bundle_hash
    assert first.bundle.role == "committed"
    assert first.bundle.epoch == 1
    assert first.bundle.solver_state_hash == STATE_E1_HASH
    assert [row.parent_state_data_hash for row in first.bundle.entries] == [
        row.data_hash for row in accepted.bundle.entries
    ]
    validate_fiber_frame_material_state_projection(
        problem,
        child,
        first,
        parent_checkpoint=parent,
        accepted_projection=accepted,
    )


def test_two_step_projection_chain_is_exact_and_epoch_aligned() -> None:
    problem = make_two_member_stateful_fiber_l_frame()
    checkpoint0 = initial_stateful_fiber_frame2d_checkpoint(problem)
    projection0 = create_initial_fiber_frame_material_state_projection(
        problem,
        checkpoint0,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )
    step1 = solve_stateful_fiber_frame2d_load_step(
        problem,
        checkpoint0,
        target_load_factor=0.25,
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    checkpoint1 = step1.accepted_checkpoint
    projection1 = advance_fiber_frame_material_state_projection(
        problem,
        checkpoint0,
        checkpoint1,
        projection0,
        solver_state_hash=STATE_E1_HASH,
    )
    step2 = solve_stateful_fiber_frame2d_load_step(
        problem,
        checkpoint1,
        target_load_factor=0.5,
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    checkpoint2 = step2.accepted_checkpoint
    projection2 = advance_fiber_frame_material_state_projection(
        problem,
        checkpoint1,
        checkpoint2,
        projection1,
        solver_state_hash=STATE_E2_HASH,
    )

    assert step1.committed is True
    assert step2.committed is True
    assert checkpoint2.parent_state_hash == checkpoint1.state_hash
    assert projection2.bundle.epoch == checkpoint2.epoch == 2
    assert projection2.receipt.parent_checkpoint_state_hash == checkpoint1.state_hash
    assert [row.parent_state_data_hash for row in projection2.bundle.entries] == [
        row.data_hash for row in projection1.bundle.entries
    ]
    validate_fiber_frame_material_state_projection(
        problem,
        checkpoint2,
        projection2,
        parent_checkpoint=checkpoint1,
        accepted_projection=projection1,
    )


def test_member_order_changes_source_identity_and_bundle_identity() -> None:
    original_problem = make_two_member_stateful_fiber_l_frame()
    reordered_problem = replace(
        original_problem,
        members=tuple(reversed(original_problem.members)),
    )
    original_checkpoint = initial_stateful_fiber_frame2d_checkpoint(original_problem)
    reordered_checkpoint = initial_stateful_fiber_frame2d_checkpoint(reordered_problem)
    original = create_initial_fiber_frame_material_state_projection(
        original_problem,
        original_checkpoint,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )
    reordered = create_initial_fiber_frame_material_state_projection(
        reordered_problem,
        reordered_checkpoint,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )

    assert original_problem.contract_hash != reordered_problem.contract_hash
    assert (
        original.receipt.source_identity_hash != reordered.receipt.source_identity_hash
    )
    assert original.bundle.bundle_hash != reordered.bundle.bundle_hash
    with pytest.raises(ValueError, match="problem_contract_hash"):
        validate_fiber_frame_material_state_projection(
            reordered_problem,
            original_checkpoint,
            original,
        )


def test_wrong_checkpoint_parent_and_wrong_accepted_projection_fail_closed() -> None:
    problem = make_two_member_stateful_fiber_l_frame()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    accepted = create_initial_fiber_frame_material_state_projection(
        problem,
        parent,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )
    child = solve_stateful_fiber_frame2d_load_step(
        problem,
        parent,
        target_load_factor=0.25,
        config=NewtonRaphsonConfig(max_iterations=40),
    ).accepted_checkpoint
    wrong_parent_child = replace(
        child,
        parent_state_hash="sha256:" + "f" * 64,
        state_hash="",
    )
    with pytest.raises(
        FiberFrameMaterialStateProjectionError,
        match="fiber_frame_projection_checkpoint_parent_mismatch",
    ):
        advance_fiber_frame_material_state_projection(
            problem,
            parent,
            wrong_parent_child,
            accepted,
            solver_state_hash=STATE_E1_HASH,
        )

    other_problem = make_two_element_stateful_fiber_cantilever()
    other_parent = initial_stateful_fiber_frame2d_checkpoint(other_problem)
    other_projection = create_initial_fiber_frame_material_state_projection(
        other_problem,
        other_parent,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )
    with pytest.raises(ValueError, match="problem_contract_hash"):
        advance_fiber_frame_material_state_projection(
            problem,
            parent,
            child,
            other_projection,
            solver_state_hash=STATE_E1_HASH,
        )


def test_receipt_and_bundle_authority_tamper_fail_closed() -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)
    projection = create_initial_fiber_frame_material_state_projection(
        problem,
        checkpoint,
        model_ir_content_hash=MODEL_HASH,
        execution_plan_hash=PLAN_HASH,
        solver_state_hash=STATE_E0_HASH,
    )

    promoted_receipt = replace(
        projection.receipt,
        authority_profile="authoritative_nonlinear_engineering_state",
    )
    with pytest.raises(
        FiberFrameMaterialStateProjectionError,
        match="fiber_frame_projection_authority_profile_invalid",
    ):
        validate_fiber_frame_material_state_projection(
            problem,
            checkpoint,
            replace(projection, receipt=promoted_receipt),
        )

    wrong_solver_receipt = replace(
        projection.receipt,
        solver_state_hash="sha256:" + "9" * 64,
    )
    with pytest.raises(
        FiberFrameMaterialStateProjectionError,
        match="fiber_frame_projection_receipt_hash_mismatch",
    ):
        validate_fiber_frame_material_state_projection(
            problem,
            checkpoint,
            replace(projection, receipt=wrong_solver_receipt),
        )
