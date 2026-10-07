"""Bounded path/restart contracts; no public authority or performance claims."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


TARGETS = (-1e-5, -2e-5, 1e-5, 0.0)
OPTIONS = dict(
    control_global_dof=4, allow_reversals=True, maximum_reversals=2, maximum_targets=6
)
run_path = paths.run_stateful_fiber_frame2d_control_path
Config = paths.StatefulFiberFrame2DDisplacementControlConfig


def _forbid(*_args, **_kwargs):
    pytest.fail("preflight must reject before any core solve, including prefix replay")


@pytest.fixture(autouse=True)
def no_public_analysis(monkeypatch):
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", _forbid)


@pytest.fixture(scope="module")
def problem():
    # Compile the original public cantilever recipe, retaining its actual RC laws.
    model = load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    compiled, unsupported, _ = public_api._compile(model)
    assert compiled is not None and not unsupported
    return compiled.problem


@pytest.fixture(scope="module")
def actual(problem):
    # Small elastic-range excursions exercise reversal scheduling. They are not
    # steel-yield evidence; root coordinates a separate predeclared material case.
    full = run_path(problem, TARGETS, **OPTIONS)
    prefix = run_path(problem, TARGETS[:2], **OPTIONS)
    assert full.status == prefix.status == "ready"
    raw = prefix.restart_artifact()
    resumed = run_path(problem, TARGETS[2:], restart=raw, **OPTIONS)
    assert resumed.status == "ready"
    return full, prefix, resumed, raw


def _seal(payload):
    payload = deepcopy(payload)
    payload.pop("artifact_hash", None)
    payload["artifact_hash"] = paths._hash(paths._json(payload))
    return paths._json(payload)


def test_cyclic_path_records_every_authored_target_and_keeps_authority_bounded(actual):
    full, _, _, _ = actual
    payload = full.to_dict()
    assert payload["requested_directions"] == [-1, -1, 1, -1]
    assert (
        payload["requested_reversal_count"] == payload["accepted_reversal_count"] == 2
    )
    assert full.accepted_target_prefix_m == TARGETS
    assert full.unattempted_targets_m == ()
    assert [
        row["target_control_displacement_m"] for row in payload["attempts"]
    ] == list(TARGETS)
    assert payload["metrics"]["requested_target_count"] == 4
    assert payload["metrics"]["attempted_target_count"] == 4
    assert payload["metrics"]["hidden_retries_or_cutbacks"] == 0
    assert all(
        value is False
        for key, value in payload["claims"].items()
        if key != "experimental_small_displacement_rc_control"
    )
    for index, step in enumerate(full.steps, 1):
        assert step.committed and step.accepted_checkpoint.epoch == index
        assert (
            step.accepted_checkpoint.parent_state_hash
            == step.parent_checkpoint.state_hash
        )
        assert (
            step.metrics["control_gate_passed"]
            and step.metrics["equilibrium_gate_passed"]
        )
        assert (
            abs(step.accepted_checkpoint.global_displacements[4] - TARGETS[index - 1])
            <= 1e-12
        )


def test_restart_replays_whole_prefix_and_preserves_exact_terminal_bytes_and_costs(
    problem, actual
):
    full, prefix, resumed, raw = actual
    assert prefix.restart_artifact() == raw
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )
    assert dump_stateful_fiber_frame2d_checkpoint_bytes(
        problem, resumed.final_checkpoint
    ) == dump_stateful_fiber_frame2d_checkpoint_bytes(problem, full.final_checkpoint)
    assert resumed.restart_artifact() == full.restart_artifact()
    assert len(resumed.steps) == len(resumed.replayed_steps) == 2
    metrics = resumed.metrics
    assert metrics["prefix_replayed_step_count"] == 2
    assert metrics["requested_target_count"] == metrics["attempted_target_count"] == 2
    assert metrics["cumulative_accepted_target_count"] == 4
    assert metrics["restart_verification_scope"] == "full_genesis_prefix_solver_replay"
    assert metrics["prefix_replay_work"]["unknown_solver_work_attempt_count"] == 0
    assert metrics["total_work"]["known_linear_solve_count"] == sum(
        step.trial_solution.metrics["linear_solve_count"]
        for step in (*resumed.replayed_steps, *resumed.steps)
    )
    assert metrics["total_work"]["attempted_step_count"] == 4


@pytest.mark.parametrize(
    "targets",
    [
        (),
        (0.0,),
        (-0.0,),
        (1e-5, 1e-5),
        (True,),
        ("0.1",),
        (float("nan"),),
        (float("inf"),),
        (2**53,),
        tuple(range(1, 257)),
    ],
)
def test_invalid_targets_reject_before_solve(problem, monkeypatch, targets):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError):
        run_path(problem, targets, control_global_dof=4)


@pytest.mark.parametrize(
    "change",
    [
        {"allow_reversals": 1},
        {"maximum_reversals": True},
        {"maximum_targets": True},
        {"maximum_targets": 0},
        {"maximum_targets": 256},
        {"maximum_reversals": -1},
        {"maximum_reversals": 255},
        {"maximum_reversals": 1},
        {"control_global_dof": True},
        {"control_global_dof": 5},
        {"control_global_dof": 0},
        {"config": {}},
    ],
)
def test_invalid_policy_or_control_rejects_before_solve(problem, monkeypatch, change):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError):
        run_path(problem, (-1e-5,), **({"control_global_dof": 4} | change))


@pytest.mark.parametrize(
    "options",
    [
        dict(control_global_dof=4),
        dict(control_global_dof=4, allow_reversals=True, maximum_reversals=1),
    ],
)
def test_reversal_denominator_including_unattempted_suffix_checked_before_solve(
    problem, monkeypatch, options
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError, match="reversal budget"):
        run_path(problem, TARGETS, **options)


@pytest.mark.parametrize(
    "suffix", [(1e-5, -1e-5, 1e-5), (1e-5, 2e-5, 3e-5, 4e-5, 5e-5), (-2e-5,)]
)
def test_resume_cumulative_budget_and_boundary_repeat_checked_before_replay(
    problem, actual, monkeypatch, suffix
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError):
        run_path(problem, suffix, restart=actual[3], **OPTIONS)


@pytest.mark.parametrize(
    "kind",
    [
        "extra",
        "nested_extra",
        "boolean_target",
        "unsafe_target",
        "direction",
        "reversal",
        "unit",
        "config",
        "claims",
        "parent_chain",
        "prefix_order",
        "epoch",
    ],
)
def test_resealed_invalid_restart_contract_fails_before_replay(
    problem, actual, monkeypatch, kind
):
    payload = json.loads(actual[3])
    if kind == "extra":
        payload["extra"] = None
    elif kind == "nested_extra":
        payload["accepted_step_bindings"][0]["extra"] = None
    elif kind == "boolean_target":
        payload["accepted_targets_m"][0] = True
    elif kind == "unsafe_target":
        payload["accepted_targets_m"][0] = 2**53
    elif kind == "direction":
        payload["direction"] = True
    elif kind == "reversal":
        payload["reversal_count"] = False
    elif kind == "unit":
        payload["scope"]["control_unit"] = "rad"
    elif kind == "config":
        payload["scope"]["configuration"]["control_tolerance_m"] *= 2
    elif kind == "claims":
        payload["claims"]["public_j1_j5_authority"] = True
    elif kind == "parent_chain":
        payload["accepted_step_bindings"][1]["parent_checkpoint_hash"] = (
            "sha256:" + "0" * 64
        )
    elif kind == "prefix_order":
        payload["accepted_targets_m"].reverse()
    elif kind == "epoch":
        payload["terminal_checkpoint"]["epoch"] = True
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError):
        run_path(problem, TARGETS[2:], restart=_seal(payload), **OPTIONS)


@pytest.mark.parametrize(
    "kind", ["duplicate", "noncanonical", "oversized", "deep", "bad_utf8", "nan"]
)
def test_restart_bytes_fail_closed_before_any_replay(
    problem, actual, monkeypatch, kind
):
    raw = actual[3]
    if kind == "duplicate":
        raw = b'{"a":1,"a":2}'
    elif kind == "noncanonical":
        raw += b"\n"
    elif kind == "oversized":
        raw = b" " * (paths.CONTROL_RESTART_MAX_BYTES + 1)
    elif kind == "deep":
        raw = b"[" * 65 + b"0" + b"]" * 65
    elif kind == "bad_utf8":
        raw = b"\xff"
    elif kind == "nan":
        raw = b'{"x":NaN}'
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError):
        run_path(problem, TARGETS[2:], restart=raw, **OPTIONS)


def test_exception_attempt_preserves_parent_suffix_and_unknown_cost(
    problem, actual, monkeypatch
):
    first = actual[0].steps[0]
    calls = []

    def failing(_problem, parent, *, target_control_displacement_m, **_kwargs):
        calls.append(target_control_displacement_m)
        if len(calls) == 1:
            return first
        assert parent is first.accepted_checkpoint
        raise ValueError("declared injected core failure after entry")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", failing
    )
    result = run_path(problem, TARGETS, **OPTIONS)
    assert calls == list(TARGETS[:2])
    assert result.status == "blocked"
    assert result.final_checkpoint is first.accepted_checkpoint
    assert result.accepted_target_prefix_m == TARGETS[:1]
    assert result.unattempted_targets_m == TARGETS[2:]
    payload = result.to_dict()
    assert len(result.steps) == 1 and len(payload["attempts"]) == 2
    assert payload["attempts"][-1]["failure"]["type"] == "ValueError"
    assert payload["attempts"][-1]["rollback_exact"] is True
    assert payload["metrics"]["suffix_work"]["unknown_solver_work_attempt_count"] == 1
    assert json.loads(result.restart_artifact())["accepted_targets_m"] == list(
        TARGETS[:1]
    )


def test_actual_nonconvergence_rolls_back_without_retry_or_candidate_omission(problem):
    cfg = Config(newton=NewtonRaphsonConfig(max_iterations=0))
    result = run_path(problem, TARGETS, config=cfg, **OPTIONS)
    assert result.status == "blocked"
    assert len(result.steps) == 1 and not result.steps[0].committed
    assert result.final_checkpoint is result.initial_checkpoint
    assert result.final_checkpoint.epoch == 0
    assert result.unattempted_targets_m == TARGETS[1:]
    assert result.metrics["failed_target_count"] == 1
    assert result.metrics["suffix_work"]["known_linear_solve_count"] == 0


def test_self_rehashed_changed_material_memory_rejected_by_full_prefix_replay(
    problem, actual, monkeypatch
):
    payload = json.loads(actual[3])
    checkpoint = actual[1].final_checkpoint
    element = checkpoint.element_states[0]
    section = element.integration_point_states[0]
    fibers = list(section.fiber_states)
    index = next(
        i for i, state in enumerate(fibers) if type(state) is UniaxialPlasticityState
    )
    fibers[index] = replace(
        fibers[index],
        accumulated_plastic_strain=fibers[index].accumulated_plastic_strain + 1e-4,
    )
    new_section = replace(section, fiber_states=tuple(fibers))
    new_element = replace(
        element,
        integration_point_states=(new_section, *element.integration_point_states[1:]),
    )
    changed = replace(
        checkpoint,
        element_states=(new_element, *checkpoint.element_states[1:]),
        state_hash="",
    )
    raw_checkpoint = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, changed)
    payload["terminal_checkpoint"] = json.loads(raw_checkpoint)
    payload["terminal_checkpoint_sha256"] = paths._hash(raw_checkpoint)
    payload["accepted_step_bindings"][-1]["accepted_checkpoint_hash"] = (
        changed.state_hash
    )
    calls = []
    real = paths.solve_stateful_fiber_frame2d_displacement_control_step

    def recording(*args, **kwargs):
        calls.append(kwargs["target_control_displacement_m"])
        return real(*args, **kwargs)

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", recording
    )
    with pytest.raises(
        paths.StatefulFiberFrame2DControlRestartError, match="replay/checkpoint"
    ) as error:
        run_path(problem, TARGETS[2:], restart=_seal(payload), **OPTIONS)
    assert calls == list(TARGETS[:2])
    assert error.value.to_dict()["replay_work"]["attempted_step_count"] == 2
    assert error.value.to_dict()["replay_work"]["known_linear_solve_count"] > 0


def test_changed_step_receipt_replay_failure_preserves_work_without_suffix(
    problem, actual, monkeypatch
):
    payload = json.loads(actual[3])
    payload["accepted_step_bindings"][0]["step_hash"] = "sha256:" + "0" * 64
    calls = []
    original = paths.solve_stateful_fiber_frame2d_displacement_control_step

    def recording(*args, **kwargs):
        calls.append(kwargs["target_control_displacement_m"])
        return original(*args, **kwargs)

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", recording
    )
    with pytest.raises(paths.StatefulFiberFrame2DControlRestartError):
        run_path(problem, TARGETS[2:], restart=_seal(payload), **OPTIONS)
    assert calls == list(TARGETS[:2])


def test_exports_are_detached_and_detect_later_nested_step_mutation(actual):
    result = deepcopy(actual[0])
    exported = result.to_dict()
    exported["claims"]["public_j1_j5_authority"] = True
    assert result.to_dict()["claims"]["public_j1_j5_authority"] is False
    result.steps[0].metrics["control_gate_passed"] = False
    with pytest.raises(ValueError, match="step changed"):
        result.to_dict()
    with pytest.raises(ValueError, match="step changed"):
        result.restart_artifact()


@pytest.mark.parametrize("field", ["initial_checkpoint", "final_checkpoint"])
def test_replaced_checkpoint_field_cannot_export_an_unrelated_saved_payload(
    actual, field
):
    full, prefix, _, _ = actual
    changed = replace(full, **{field: prefix.final_checkpoint})
    with pytest.raises(ValueError, match="checkpoint field binding"):
        changed.to_dict()
    with pytest.raises(ValueError, match="checkpoint field binding"):
        changed.restart_artifact()


def test_replay_only_restart_binds_single_snapshot_of_mutable_input(
    problem, actual, monkeypatch
):
    # Reuse real recorded steps only to test input transport and accounting.
    # This stub creates no new physical/replay evidence.
    _, prefix, _, raw = actual
    mutable = bytearray(raw)
    recorded = iter(prefix.steps)
    calls = []

    def retained_step(*_args, **kwargs):
        calls.append(kwargs["target_control_displacement_m"])
        mutable[:] = b"mutated by the owner after decoding"
        return next(recorded)

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", retained_step
    )
    replay = run_path(problem, (), restart=mutable, **OPTIONS)
    assert calls == list(TARGETS[:2])
    assert replay.status == "ready" and replay.steps == ()
    assert replay.to_dict()["restart_input_sha256"] == paths._hash(raw)
    assert replay.restart_artifact() == raw
    assert replay.metrics["requested_target_count"] == 0
    assert replay.metrics["total_work"]["attempted_step_count"] == 2


def test_changed_problem_or_policy_cannot_reset_restart_scope(
    problem, actual, monkeypatch
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    for changed_options in (
        {"maximum_targets": 7},
        {"maximum_reversals": 3},
        {"control_global_dof": 3},
        {"config": Config(control_tolerance_m=2e-12)},
    ):
        with pytest.raises(ValueError, match="source/configuration"):
            run_path(
                problem, TARGETS[2:], restart=actual[3], **(OPTIONS | changed_options)
            )
    changed = replace(problem, case_id="different-source")
    with pytest.raises(ValueError, match="source/configuration"):
        run_path(changed, TARGETS[2:], restart=actual[3], **OPTIONS)


@pytest.mark.parametrize("kind", ["move_all", "swap_groups", "reverse_suffix"])
def test_replay_suffix_partition_and_order_are_bound_to_recorded_attempts(actual, kind):
    full, _, resumed, _ = actual
    if kind == "move_all":
        changed = replace(full, replayed_steps=full.steps, steps=())
    elif kind == "swap_groups":
        changed = replace(
            resumed, steps=resumed.replayed_steps, replayed_steps=resumed.steps
        )
    else:
        changed = replace(full, steps=tuple(reversed(full.steps)))
    with pytest.raises(ValueError, match="replay/suffix"):
        changed.to_dict()
    with pytest.raises(ValueError, match="replay/suffix"):
        changed.restart_artifact()


@pytest.mark.parametrize(
    "kind",
    [
        "wrong_type",
        "wrong_parent",
        "wrong_ancestry",
        "source",
        "parent",
        "exception_source",
    ],
)
def test_invalid_return_preserves_prior_and_current_attempts_without_state_authority(
    problem, actual, monkeypatch, kind
):
    # Retained real steps are injected solely to exercise orchestration failures.
    source = deepcopy(problem)
    first, second = deepcopy(actual[0].steps[:2])
    initial_hash = source.contract_hash
    calls = []

    def invalid(_problem, parent, *, target_control_displacement_m, **_kwargs):
        calls.append(target_control_displacement_m)
        if len(calls) == 1:
            return first
        if kind == "wrong_type":
            return object()
        if kind == "wrong_parent":
            return replace(second, parent_checkpoint=first.parent_checkpoint)
        if kind == "wrong_ancestry":
            return replace(second, accepted_checkpoint=first.accepted_checkpoint)
        if kind in ("source", "exception_source"):
            object.__setattr__(source, "case_id", "changed-during-solve")
        else:
            object.__setattr__(parent, "state_hash", "sha256:" + "0" * 64)
        if kind == "exception_source":
            raise RuntimeError("injected failure after source mutation")
        return second

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", invalid
    )
    with pytest.raises(paths.StatefulFiberFrame2DControlExecutionError) as error:
        run_path(source, TARGETS, **OPTIONS)
    payload = error.value.to_dict()
    assert calls == list(TARGETS[:2])
    assert payload["status"] == "invalid_execution"
    assert payload["state_or_restart_export_available"] is False
    assert payload["context"]["phase"] == "suffix"
    assert payload["context"]["problem_contract_hash"] == initial_hash
    assert payload["context"]["failed_target_index"] == 1
    assert payload["context"]["unattempted_targets_m"] == list(TARGETS[2:])
    assert payload["work"]["attempted_step_count"] == 2
    assert payload["work"]["unknown_solver_work_attempt_count"] == 1
    assert (
        payload["work"]["known_linear_solve_count"]
        == first.trial_solution.metrics["linear_solve_count"]
    )
    assert payload["attempts"][0]["committed"] is True
    assert payload["attempts"][1]["step"] is None
    assert payload["attempts"][1]["accepted_checkpoint_hash"] is None
    assert payload["attempts"][1]["rollback_exact"] is None
    assert payload["attempts"][1]["artifact_contract_pass"] is False
    payload["attempts"].clear()
    assert len(error.value.to_dict()["attempts"]) == 2


@pytest.mark.parametrize("failed_call", [2, 4])
def test_invalid_restart_execution_preserves_replay_and_suffix_work(
    problem, actual, monkeypatch, failed_call
):
    retained = iter(actual[0].steps)
    calls = []

    def invalid(*_args, **kwargs):
        calls.append(kwargs["target_control_displacement_m"])
        return object() if len(calls) == failed_call else next(retained)

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", invalid
    )
    expected_error = (
        paths.StatefulFiberFrame2DControlRestartError
        if failed_call == 2
        else paths.StatefulFiberFrame2DControlExecutionError
    )
    with pytest.raises(expected_error) as error:
        run_path(problem, TARGETS[2:], restart=actual[3], **OPTIONS)
    payload = error.value.to_dict()
    assert calls == list(TARGETS[:failed_call])
    if failed_call == 2:
        assert payload["replay_work"]["attempted_step_count"] == 2
        assert payload["replay_work"]["unknown_solver_work_attempt_count"] == 1
        assert payload["execution_failure"]["context"]["phase"] == "prefix_replay"
        assert payload["replay_attempts"] == payload["execution_failure"]["attempts"]
    else:
        assert payload["prior_replay_work"]["attempted_step_count"] == 2
        assert payload["work"]["attempted_step_count"] == 2
        assert payload["total_work"]["attempted_step_count"] == 4
        assert payload["total_work"]["unknown_solver_work_attempt_count"] == 1
        assert payload["context"]["phase"] == "suffix"


def test_prior_attempt_snapshot_survives_nonfinite_mutation_before_later_failure(
    problem, actual, monkeypatch
):
    first = deepcopy(actual[0].steps[0])
    original_receipt = json.loads(paths._json(first.to_dict()))
    original_work = json.loads(paths._json(first.trial_solution.metrics))
    calls = []

    def invalid(*_args, **kwargs):
        calls.append(kwargs["target_control_displacement_m"])
        if len(calls) == 1:
            return first
        first.trial_solution.metrics["later_mutation"] = {"value": float("nan")}
        return object()

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", invalid
    )
    with pytest.raises(paths.StatefulFiberFrame2DControlExecutionError) as error:
        run_path(problem, TARGETS, **OPTIONS)
    payload = error.value.to_dict()
    assert calls == list(TARGETS[:2])
    assert payload["attempts"][0]["step"] == original_receipt
    assert payload["attempts"][0]["solver_work"] == original_work
    assert payload["work"]["attempted_step_count"] == 2
    assert payload["work"]["unknown_solver_work_attempt_count"] == 1
    assert (
        payload["work"]["known_linear_solve_count"]
        == original_work["linear_solve_count"]
    )
