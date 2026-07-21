from __future__ import annotations

import json

import pytest

from structural_analysis.assembly import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE,
    StatefulCorotationalFiberFrame2DAdaptiveConfig,
    StatefulCorotationalFiberFrame2DAdaptiveError,
    StatefulCorotationalFiberFrame2DCheckpointArtifactError,
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    adaptive_stateful_corotational_fiber_frame2d_continuation,
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    read_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact,
    read_stateful_corotational_fiber_frame2d_checkpoint_artifact,
    validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint,
    write_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact,
    write_stateful_corotational_fiber_frame2d_checkpoint_artifact,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    NewtonRaphsonConfig,
)


COORDINATES = ((0.0, 0.0), (3.0, 0.0), (3.0, 2.0))


def _problem(
    *,
    case_id: str,
    reference_load_kn: float = -120.0,
    all_fixed: bool = False,
) -> StatefulCorotationalFiberFrame2DProblem:
    members = tuple(
        StatefulCorotationalFiberFrame2DMember(
            member_id=member_id,
            node_i=node_i,
            node_j=node_j,
            element=StatefulCorotationalFiberBeam2D(
                node_coordinates_m=(COORDINATES[node_i], COORDINATES[node_j]),
                section=make_rectangular_stateful_rc_fiber_section(),
                integration_order=3,
                element_id=member_id,
            ),
        )
        for member_id, node_i, node_j in (
            ("member-1", 0, 1),
            ("member-2", 1, 2),
        )
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id=case_id,
        node_coordinates_m=COORDINATES,
        members=members,
        fixed_global_dofs=(tuple(range(9)) if all_fixed else (0, 1, 2)),
        reference_external_loads=((6, reference_load_kn),),
        rotation_coordinate_scale_m=3.0,
    )


def _config(
    *,
    maximum_attempt_count: int = 32,
    max_iterations: int = 9,
) -> StatefulCorotationalFiberFrame2DAdaptiveConfig:
    return StatefulCorotationalFiberFrame2DAdaptiveConfig(
        target_load_factor=1.0,
        initial_step_size=1.0,
        minimum_step_size=0.0625,
        maximum_step_size=1.0,
        failed_step_reduction=0.5,
        fast_step_growth=2.0,
        fast_newton_iteration_threshold=6,
        maximum_attempt_count=maximum_attempt_count,
        newton_config=NewtonRaphsonConfig(max_iterations=max_iterations),
    )


@pytest.fixture(scope="module")
def adaptive_run():
    problem = _problem(case_id="corotational-adaptive-full-load")
    config = _config()
    result = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
    )
    return problem, config, result


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_actual_newton_failure_cuts_back_then_reaches_full_load(
    adaptive_run,
) -> None:
    problem, config, result = adaptive_run

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["target_load_factor_reached"] is True
    assert result.metrics["final_load_factor"] == 1.0
    assert result.metrics["attempt_count"] == 3
    assert result.metrics["accepted_step_count"] == 2
    assert result.metrics["failed_step_count"] == 1
    assert result.metrics["failed_step_reduction_count"] == 1
    assert result.metrics["fast_step_growth_count"] == 1
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["residual_and_increment_acceptance_gate"] is True
    assert result.metrics["parent_ancestry_gate"] is True
    assert result.metrics["parent_immutable_gate"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["damaged_member_step_count"] > 0
    assert result.metrics["final_relative_residual"] <= (
        config.newton_config.residual_tolerance
    )
    assert [row.outcome for row in result.attempts] == [
        "rolled_back",
        "committed",
        "committed",
    ]
    assert [row.target_load_factor for row in result.attempts] == [1.0, 0.5, 1.0]
    assert [row.attempted_step_size for row in result.attempts] == [1.0, 0.5, 0.5]
    assert [row.next_step_size for row in result.attempts] == [0.5, 1.0, 0.5]
    assert [row.step_grew for row in result.attempts] == [False, True, False]
    assert [row.accepted_checkpoint.load_factor for row in result.checkpoints] == [
        0.0,
        0.0,
        0.5,
        1.0,
    ]

    rejected = result.attempts[0]
    assert rejected.step_result.committed is False
    assert rejected.step_result.metrics["rollback_exact"] is True
    assert rejected.step_result.metrics["solver_contract_pass"] is False
    assert rejected.step_result.accepted_checkpoint is (
        rejected.step_result.parent_checkpoint
    )
    assert (
        rejected.step_result.accepted_checkpoint.canonical_bytes()
        == result.initial_checkpoint.accepted_checkpoint.canonical_bytes()
    )
    for accepted in result.attempts[1:]:
        assert accepted.step_result.committed is True
        assert accepted.step_result.metrics["solver_contract_pass"] is True
        assert accepted.step_result.metrics["residual_gate_passed"] is True
        assert accepted.step_result.metrics["increment_gate_passed"] is True

    payload = result.to_dict()
    assert payload["claims"]["adaptive_corotational_fiber_frame2d_path"] is True
    assert payload["claims"]["failed_step_reduction_exercised"] is True
    assert payload["claims"]["failed_step_full_state_rollback_exact"] is True
    assert payload["claims"]["source_bound_persisted_checkpoint"] is True
    assert payload["claims"]["checkpoint_chain_replay"] is False
    assert payload["claims"]["arc_length_branch"] is False
    assert payload["claims"]["production_sparse_solver"] is False
    assert payload["claims"]["rocm_hip_parity"] is False
    assert payload["claims"]["external_benchmark_acceptance"] is False
    assert payload["claims"]["g1_full_building_closure"] is False
    json.dumps(payload, allow_nan=False, sort_keys=True)

    repeated = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
    )
    assert repeated.to_dict() == result.to_dict()
    assert (
        repeated.final_state.canonical_bytes() == result.final_state.canonical_bytes()
    )


def test_failed_boundary_persisted_restart_is_exact(
    adaptive_run,
    tmp_path,
) -> None:
    problem, config, one_shot = adaptive_run
    failed_boundary = one_shot.checkpoints[1]
    raw = failed_boundary.to_bytes()
    loaded = load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
        raw,
        problem,
        config,
    )
    restarted = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
        checkpoint=loaded,
    )

    assert failed_boundary.accepted_checkpoint.load_factor == 0.0
    assert failed_boundary.progress.attempt_count == 1
    assert failed_boundary.progress.failed_step_count == 1
    assert failed_boundary.next_step_size == 0.5
    assert loaded.to_bytes() == raw
    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.metrics["attempt_count"] == one_shot.metrics["attempt_count"]
    assert (
        restarted.metrics["accepted_step_count"]
        == (one_shot.metrics["accepted_step_count"])
    )
    assert (
        restarted.metrics["failed_step_count"]
        == (one_shot.metrics["failed_step_count"])
    )
    assert restarted.final_checkpoint.checkpoint_hash == (
        one_shot.final_checkpoint.checkpoint_hash
    )
    assert restarted.final_state.state_hash == one_shot.final_state.state_hash
    assert restarted.final_state.canonical_bytes() == (
        one_shot.final_state.canonical_bytes()
    )
    assert tuple(
        state.canonical_bytes() for state in restarted.final_state.element_states
    ) == tuple(state.canonical_bytes() for state in one_shot.final_state.element_states)

    adaptive_path = tmp_path / "adaptive-checkpoint.json"
    write_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact(
        problem,
        config,
        failed_boundary,
        adaptive_path,
    )
    restored_adaptive = (
        read_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact(
            problem,
            config,
            adaptive_path,
        )
    )
    assert restored_adaptive.to_bytes() == raw
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="already exists",
    ):
        write_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact(
            problem,
            config,
            failed_boundary,
            adaptive_path,
        )

    base_raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem,
        one_shot.final_state,
    )
    restored_base = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        base_raw,
        problem,
    )
    assert restored_base.state_hash == one_shot.final_state.state_hash
    assert restored_base.canonical_bytes() == one_shot.final_state.canonical_bytes()
    base_path = tmp_path / "accepted-corotational-checkpoint.json"
    write_stateful_corotational_fiber_frame2d_checkpoint_artifact(
        problem,
        one_shot.final_state,
        base_path,
    )
    assert (
        read_stateful_corotational_fiber_frame2d_checkpoint_artifact(
            problem,
            base_path,
        ).canonical_bytes()
        == one_shot.final_state.canonical_bytes()
    )
    with pytest.raises(
        StatefulCorotationalFiberFrame2DCheckpointArtifactError,
        match="already exists",
    ):
        write_stateful_corotational_fiber_frame2d_checkpoint_artifact(
            problem,
            one_shot.final_state,
            base_path,
        )
    assert STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE == (
        "canonical-signed-zero-preserving-utf8-json.v1"
    )


def test_minimum_step_exhaustion_retains_exact_initial_checkpoint() -> None:
    problem = _problem(case_id="corotational-adaptive-minimum-step")
    config = StatefulCorotationalFiberFrame2DAdaptiveConfig(
        initial_step_size=0.5,
        minimum_step_size=0.25,
        maximum_step_size=0.5,
        maximum_attempt_count=8,
        newton_config=NewtonRaphsonConfig(max_iterations=0),
    )
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    initial_bytes = initial.canonical_bytes()
    result = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
        initial_state=initial,
    )

    assert result.status == "blocked"
    assert result.terminal_reason == "minimum_step_size_exhausted"
    assert result.metrics["contract_pass"] is False
    assert result.metrics["attempt_count"] == 2
    assert result.metrics["accepted_step_count"] == 0
    assert result.metrics["failed_step_count"] == 2
    assert result.metrics["rollback_exact"] is True
    assert result.final_state is initial
    assert result.final_state.canonical_bytes() == initial_bytes
    assert [row.target_load_factor for row in result.attempts] == [0.5, 0.25]
    assert all(row.outcome == "rolled_back" for row in result.attempts)


def test_restart_cannot_reset_persisted_attempt_budget() -> None:
    problem = _problem(case_id="corotational-adaptive-attempt-budget")
    config = _config(maximum_attempt_count=1, max_iterations=0)
    first = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
    )
    loaded = load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
        first.final_checkpoint.to_bytes(),
        problem,
        config,
    )
    restarted = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
        checkpoint=loaded,
    )

    assert first.status == "blocked"
    assert first.terminal_reason == "maximum_attempt_count_exhausted"
    assert first.metrics["attempt_count"] == 1
    assert first.final_checkpoint.next_step_size == 0.5
    assert restarted.status == "blocked"
    assert restarted.terminal_reason == "maximum_attempt_count_exhausted"
    assert restarted.metrics["attempt_count"] == 1
    assert restarted.metrics["run_attempt_count"] == 0
    assert restarted.final_checkpoint.checkpoint_hash == (
        first.final_checkpoint.checkpoint_hash
    )


def test_fully_constrained_path_commits_reaction_only_without_convergence_claim() -> (
    None
):
    problem = _problem(
        case_id="corotational-adaptive-reaction-only",
        reference_load_kn=-20.0,
        all_fixed=True,
    )
    config = _config()
    result = adaptive_stateful_corotational_fiber_frame2d_continuation(
        problem,
        config=config,
    )

    assert result.status == "ready"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["accepted_step_count"] == 1
    assert result.metrics["iterative_solver_step_count"] == 0
    assert result.metrics["no_solve_reaction_only_step_count"] == 1
    assert result.metrics["newton_iteration_count"] == 0
    assert result.final_state.load_factor == 1.0
    step = result.attempts[0].step_result
    assert step.metrics["no_solve_contract_pass"] is True
    assert step.metrics["terminal_disposition"] == (NO_SOLVE_REACTION_ONLY_DISPOSITION)
    assert step.trial_solution.metrics["solver_executed"] is False
    assert step.trial_solution.metrics["convergence_claim"] is False
    assert (
        result.to_dict()["claims"]["consistent_material_geometric_newton_step_executed"]
        is False
    )


def test_checkpoint_artifacts_reject_tampering_and_wrong_contracts(
    adaptive_run,
) -> None:
    problem, config, result = adaptive_run
    boundary = result.checkpoints[1]
    raw = boundary.to_bytes()

    tampered = json.loads(raw)
    tampered["boundary"]["next_step_size"] = 0.25
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="checkpoint_hash mismatch",
    ):
        load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
            _canonical_json(tampered),
            problem,
            config,
        )

    unknown = json.loads(raw)
    unknown["unexpected"] = True
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="keys mismatch",
    ):
        load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
            _canonical_json(unknown),
            problem,
            config,
        )

    duplicate = raw.replace(b'{"boundary":', b'{"boundary":{},"boundary":', 1)
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="duplicate key",
    ):
        load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
            duplicate,
            problem,
            config,
        )
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="not canonical JSON",
    ):
        load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
            raw + b"\n",
            problem,
            config,
        )

    changed_config = StatefulCorotationalFiberFrame2DAdaptiveConfig(
        target_load_factor=0.75,
        initial_step_size=0.75,
        maximum_step_size=0.75,
        newton_config=config.newton_config,
    )
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="path contract mismatch",
    ):
        validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
            boundary,
            problem,
            changed_config,
        )

    base_raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem,
        result.final_state,
    )
    base_tampered = json.loads(base_raw)
    base_tampered["element_states"][0]["chord_rotation_change_rad"] += 0.01
    with pytest.raises(
        StatefulCorotationalFiberFrame2DCheckpointArtifactError,
        match="hash or canonical value mismatch",
    ):
        load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
            _canonical_json(base_tampered),
            problem,
        )
    wrong_problem = _problem(case_id="wrong-corotational-checkpoint-source")
    with pytest.raises(
        StatefulCorotationalFiberFrame2DCheckpointArtifactError,
        match="supplied frame problem",
    ):
        load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
            base_raw,
            wrong_problem,
        )


def test_invalid_adaptive_inputs_fail_closed(adaptive_run) -> None:
    problem, config, result = adaptive_run
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="minimum_step_size",
    ):
        StatefulCorotationalFiberFrame2DAdaptiveConfig(
            initial_step_size=0.25,
            minimum_step_size=0.5,
        )
    with pytest.raises(
        StatefulCorotationalFiberFrame2DAdaptiveError,
        match="initial_state cannot be combined",
    ):
        adaptive_stateful_corotational_fiber_frame2d_continuation(
            problem,
            config=config,
            initial_state=result.initial_checkpoint.accepted_checkpoint,
            checkpoint=result.initial_checkpoint,
        )
