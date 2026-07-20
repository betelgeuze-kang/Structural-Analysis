from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.assembly.stateful_fiber_frame2d_material_state_bundle import (
    STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_CLAIM_BOUNDARY,
    STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_PROFILE,
    StatefulFiberFrame2DMaterialStateAdapterError,
    adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle,
    create_initial_stateful_fiber_frame2d_material_state_bundle,
    validate_stateful_fiber_frame2d_material_state_bundle_projection,
    validate_stateful_fiber_frame2d_material_state_bundle_transition,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


def _hash(value: int) -> str:
    return f"sha256:{value:064x}"


def _path():
    problem = make_two_member_stateful_fiber_l_frame()
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5),
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    return problem, path


def _entry_count(problem) -> int:
    return sum(
        member.element.integration_order * len(member.element.section.fibers)
        for member in problem.members
    )


def test_checkpoint_fiber_states_project_through_exact_bundle_lineage() -> None:
    problem, path = _path()
    initial_checkpoint = path.initial_checkpoint
    first_checkpoint = path.steps[0].accepted_checkpoint
    second_checkpoint = path.steps[1].accepted_checkpoint
    initial_checkpoint_bytes = dump_stateful_fiber_frame2d_checkpoint_bytes(
        problem,
        initial_checkpoint,
    )
    initial_bundle = create_initial_stateful_fiber_frame2d_material_state_bundle(
        problem,
        initial_checkpoint,
        model_ir_content_hash=_hash(1),
        execution_plan_hash=_hash(2),
        solver_state_hash=_hash(3),
    )

    first = adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
        problem,
        initial_checkpoint,
        first_checkpoint,
        initial_bundle,
        trial_solver_state_hash=_hash(4),
        committed_solver_state_hash=_hash(5),
    )
    second = adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
        problem,
        first_checkpoint,
        second_checkpoint,
        first.committed_bundle,
        trial_solver_state_hash=_hash(6),
        committed_solver_state_hash=_hash(7),
    )

    assert initial_bundle.entry_count == _entry_count(problem)
    first_fiber_state = (
        initial_checkpoint.element_states[0].integration_point_states[0].fiber_states[0]
    )
    assert initial_bundle.state_bytes(0) == first_fiber_state.canonical_bytes()
    assert initial_bundle.bundle_id.endswith(initial_checkpoint.state_hash[7:])
    assert (
        first.adapter_profile == STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_PROFILE
    )
    assert first.trial_bundle.parent_bundle_hash == initial_bundle.bundle_hash
    assert first.committed_bundle.parent_bundle_hash == first.trial_bundle.bundle_hash
    assert first.committed_bundle.bundle_id.endswith(first_checkpoint.state_hash[7:])
    assert first.committed_bundle.epoch == first_checkpoint.epoch == 1
    assert second.committed_bundle.epoch == second_checkpoint.epoch == 2
    assert second.trial_bundle.parent_bundle_hash == first.committed_bundle.bundle_hash
    assert all(
        trial.parent_state_data_hash == accepted.data_hash
        for accepted, trial in zip(
            initial_bundle.entries,
            first.trial_bundle.entries,
            strict=True,
        )
    )
    assert (
        first.committed_bundle.integration_point_order_hash
        == initial_bundle.integration_point_order_hash
        == second.committed_bundle.integration_point_order_hash
    )
    assert (
        dump_stateful_fiber_frame2d_checkpoint_bytes(problem, initial_checkpoint)
        == initial_checkpoint_bytes
    )
    assert (
        STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_CLAIM_BOUNDARY[
            "checkpoint_restoration_authority"
        ]
        is False
    )
    assert (
        STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_CLAIM_BOUNDARY[
            "numerical_result_authority"
        ]
        is False
    )
    assert (
        STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_CLAIM_BOUNDARY[
            "release_readiness"
        ]
        is False
    )


def test_checkpoint_bundle_projection_is_deterministic_and_exactly_validated() -> None:
    problem, path = _path()
    initial_checkpoint = path.initial_checkpoint
    checkpoint = path.steps[0].accepted_checkpoint
    initial_bundle = create_initial_stateful_fiber_frame2d_material_state_bundle(
        problem,
        initial_checkpoint,
        model_ir_content_hash=_hash(11),
        execution_plan_hash=_hash(12),
        solver_state_hash=_hash(13),
    )
    first = adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
        problem,
        initial_checkpoint,
        checkpoint,
        initial_bundle,
        trial_solver_state_hash=_hash(14),
        committed_solver_state_hash=_hash(15),
    )
    replay = adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
        problem,
        initial_checkpoint,
        checkpoint,
        initial_bundle,
        trial_solver_state_hash=_hash(14),
        committed_solver_state_hash=_hash(15),
    )

    assert first.trial_bundle.bundle_hash == replay.trial_bundle.bundle_hash
    assert first.committed_bundle.bundle_hash == replay.committed_bundle.bundle_hash
    assert first.trial_bundle.to_manifest() == replay.trial_bundle.to_manifest()
    assert first.committed_bundle.to_manifest() == replay.committed_bundle.to_manifest()
    assert (
        validate_stateful_fiber_frame2d_material_state_bundle_transition(
            problem,
            initial_checkpoint,
            checkpoint,
            initial_bundle,
            first,
        )
        is first
    )
    with pytest.raises(
        StatefulFiberFrame2DMaterialStateAdapterError,
        match="fiber_frame_material_bundle_engine_binding_mismatch",
    ):
        validate_stateful_fiber_frame2d_material_state_bundle_projection(
            problem,
            initial_checkpoint,
            initial_bundle,
            expected_role="committed",
            model_ir_content_hash=_hash(99),
            execution_plan_hash=_hash(12),
            solver_state_hash=_hash(13),
        )
    with pytest.raises(
        StatefulFiberFrame2DMaterialStateAdapterError,
        match="fiber_frame_material_transition_binding_mismatch",
    ):
        validate_stateful_fiber_frame2d_material_state_bundle_transition(
            problem,
            initial_checkpoint,
            checkpoint,
            initial_bundle,
            replace(first, checkpoint_state_hash=_hash(98)),
        )


def test_checkpoint_bundle_adapter_rejects_wrong_parent_and_projection() -> None:
    problem, path = _path()
    initial_checkpoint = path.initial_checkpoint
    checkpoint = path.steps[0].accepted_checkpoint
    initial_bundle = create_initial_stateful_fiber_frame2d_material_state_bundle(
        problem,
        initial_checkpoint,
        model_ir_content_hash=_hash(21),
        execution_plan_hash=_hash(22),
        solver_state_hash=_hash(23),
    )
    broken_parent = replace(
        checkpoint,
        parent_state_hash=_hash(24),
        state_hash="",
    )

    with pytest.raises(
        StatefulFiberFrame2DMaterialStateAdapterError,
        match="fiber_frame_material_checkpoint_parent_mismatch",
    ):
        adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
            problem,
            initial_checkpoint,
            broken_parent,
            initial_bundle,
            trial_solver_state_hash=_hash(25),
            committed_solver_state_hash=_hash(26),
        )

    wrong_projection = replace(
        initial_bundle,
        bundle_id="fiber-frame.committed.e0." + "0" * 64,
    )
    with pytest.raises(
        StatefulFiberFrame2DMaterialStateAdapterError,
        match="fiber_frame_material_bundle_invalid",
    ):
        adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
            problem,
            initial_checkpoint,
            checkpoint,
            wrong_projection,
            trial_solver_state_hash=_hash(27),
            committed_solver_state_hash=_hash(28),
        )

    with pytest.raises(
        StatefulFiberFrame2DMaterialStateAdapterError,
        match="fiber_frame_material_bundle_type_invalid",
    ):
        adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
            problem,
            initial_checkpoint,
            checkpoint,
            None,
            trial_solver_state_hash=_hash(29),
            committed_solver_state_hash=_hash(30),
        )
