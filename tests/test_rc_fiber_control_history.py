"""Original long response streams, actual replay, and retained failed work."""

import json
from pathlib import Path

import pytest

from structural_analysis.api import rc_fiber_control_history as history
from structural_analysis.api import rc_fiber_frame_direct_control as bounded
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

TARGETS = (-1e-5, -2e-5, 1e-5)
CONSTANT = (("N2", -600.0, 0.0, 0.0),)
OPTIONS = dict(control_global_dof=4, allow_reversals=True, maximum_reversals=2)


@pytest.fixture(scope="module")
def model():
    return load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )


def stream(model, targets=TARGETS, **options):
    return history.stream_rc_fiber_control_history(
        model, targets, **(OPTIONS | options)
    )


def forbidden(*args, **kwargs):
    pytest.fail("unexpected numerical execution")


@pytest.fixture(scope="module", params=[(), CONSTANT])
def actual(request, model):
    options = dict(constant_nodal_loads=request.param)
    run = stream(model, **options)
    records = list(run)
    original = bounded.analyze_bounded_rc_fiber_direct_control(
        model, TARGETS, **OPTIONS, **options
    ).to_dict()
    return options, run.report, records, original


def test_original_transition_response_and_checkpoint_match_cumulative_api(actual):
    options, report, records, original = actual
    transitions = [json.loads(raw) for raw in records[1:]]
    expected = original["response_history"]
    attempts = original["path"]["attempts"]
    if options["constant_nodal_loads"]:
        expected = [original["preload_response"], *expected]
        attempts = [*original["path"]["preload_attempts"], *attempts]
    assert [row["response"] for row in transitions] == expected
    assert [row["attempt"] for row in transitions] == attempts
    assert (
        transitions[-1]["accepted_checkpoint"] == original["path"]["final_checkpoint"]
    )
    assert report["status"] == "ready"
    assert report["core_invocations_started"] == len(transitions)
    assert report["total_work"] == original["path"]["metrics"]["total_work"]
    assert not report["storage_durability_verified"]
    assert not report["claims"]["independent_physical_validation"]


def test_resume_original_prefix_replays_bytes_and_separates_costs(model, actual):
    options, report, records, _ = actual
    prefix = records[:3]
    resumed = stream(model, prior_records=iter(prefix), **options)
    assert list(resumed) == records
    final = resumed.report
    assert final["status"] == "ready"
    assert final["total_work"] == report["total_work"]
    assert final["replay_work"]["attempted_step_count"] == 2
    assert final["new_work"]["attempted_step_count"] == len(records) - 3
    assert final["preload_work"]["attempted_step_count"] == bool(
        options["constant_nodal_loads"]
    )


def test_300_constant_targets_pause_at_255_and_preserve_every_original_record(
    model, tmp_path
):
    targets = tuple(-(i + 1) * 1e-7 for i in range(300))
    options = dict(constant_nodal_loads=CONSTANT)
    complete = stream(model, targets, **options)
    full_dir = tmp_path / "full"
    full_dir.mkdir()
    for index, raw in enumerate(complete):
        (full_dir / f"{index:04d}.json").write_bytes(raw)
    assert complete.report["status"] == "ready"

    paused = stream(model, targets, **options)
    iterator = iter(paused)
    prefix_dir = tmp_path / "prefix"
    prefix_dir.mkdir()
    # Header, preload, then 255 lateral targets; no hidden next target call.
    for index in range(257):
        (prefix_dir / f"{index:04d}.json").write_bytes(next(iterator))
    iterator.close()
    assert paused.report["status"] == "paused"
    assert paused.report["accepted_target_count"] == 255
    assert paused.report["core_invocations_started"] == 256

    prior = (p.read_bytes() for p in sorted(prefix_dir.iterdir()))
    resumed = stream(model, targets, prior_records=prior, **options)
    for index, raw in enumerate(resumed):
        assert raw == (full_dir / f"{index:04d}.json").read_bytes()
        record = json.loads(raw)
        if index:
            assert record["response"]["epoch"] == index
            assert record["accepted_checkpoint"]["epoch"] == index
    assert index == 301
    assert resumed.report["status"] == "ready"
    assert resumed.report["accepted_target_count"] == 300
    assert resumed.report["replayed_transition_count"] == 256
    assert resumed.report["replay_work"]["attempted_step_count"] == 256
    assert resumed.report["new_work"]["attempted_step_count"] == 45
    assert resumed.report["total_work"] == complete.report["total_work"]
    assert (
        resumed.report["last_emitted_checkpoint_hash"]
        == complete.report["last_emitted_checkpoint_hash"]
    )


@pytest.mark.parametrize("prior", [[], [b"{}"], ["not original bytes"], [b""]])
def test_invalid_or_missing_header_rejects_before_any_solve(model, monkeypatch, prior):
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    run = stream(model, prior_records=prior)
    with pytest.raises(history.RCFiberControlHistoryError):
        list(run)
    assert run.report["total_work"]["attempted_step_count"] == 0


def test_changed_constant_pattern_rejects_before_preload(model, actual, monkeypatch):
    options, _, records, _ = actual
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    monkeypatch.setattr(history, "_execute_preload", forbidden)
    run = stream(
        model, prior_records=records, constant_nodal_loads=(("N2", -601.0, 0.0, 0.0),)
    )
    with pytest.raises(
        history.RCFiberControlHistoryError, match="header/source/request"
    ):
        list(run)
    assert run.report["core_invocations_started"] == 0


def test_resealed_record_cannot_replace_actual_source_replay(model, actual):
    options, _, records, _ = actual
    changed = json.loads(records[1])
    changed["response"]["load_factor"] += 7.0
    changed.pop("record_hash")
    changed["record_hash"] = history._hash(history._json(changed))
    run = stream(model, prior_records=[records[0], history._json(changed)], **options)
    with pytest.raises(
        history.RCFiberControlHistoryError, match="original source replay"
    ) as caught:
        list(run)
    report = caught.value.to_dict()
    assert report["accepted_target_count"] == 0
    assert report["replay_work"]["attempted_step_count"] == 1
    assert report["response_reassembly_verified_count"] == 1
    assert report["last_emitted_checkpoint_hash"] is None
    report["status"] = "forged"
    assert run.report["status"] == "invalid_execution"


def test_extra_prior_records_prevent_terminal_readiness(model, actual):
    options, report, records, _ = actual
    run = stream(model, prior_records=[*records, records[-1]], **options)
    with pytest.raises(history.RCFiberControlHistoryError, match="beyond requested"):
        list(run)
    assert run.report["total_work"] == report["total_work"]
    assert run.report["status"] == "invalid_execution"


def test_failed_actual_preload_retains_work_without_lateral_calls(model, monkeypatch):
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    run = stream(
        model,
        constant_nodal_loads=(("N2", -30000.0, 0.0, 0.0),),
        config=paths.StatefulFiberFrame2DDisplacementControlConfig(
            newton=NewtonRaphsonConfig(max_iterations=1)
        ),
    )
    with pytest.raises(
        history.RCFiberControlHistoryError, match="preload did not converge"
    ):
        list(run)
    report = run.report
    assert report["core_invocations_started"] == 1
    assert report["preload_work"]["unknown_solver_work_attempt_count"] == 1
    assert report["accepted_target_count"] == 0
    assert report["execution_failure"]["attempts"][0]["step"]["committed"] is False


def test_control_exception_emits_rollback_and_stops_with_unknown_work(
    model, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("original core failure")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", fail
    )
    run = stream(model)
    rows = [json.loads(raw) for raw in run]
    assert len(rows) == 2
    assert rows[1]["attempt"]["failure"]["message"] == "original core failure"
    assert rows[1]["attempt"]["rollback_exact"] is True
    assert rows[1]["accepted_checkpoint"]["epoch"] == 0
    assert rows[1]["response"] is None
    assert run.report["status"] == "blocked"
    assert run.report["total_work"]["unknown_solver_work_attempt_count"] == 1


def test_recovery_failure_keeps_completed_cost_and_last_emitted_state(
    model, monkeypatch
):
    recover = history._recover_step
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("original response failure")
        return recover(*args, **kwargs)

    monkeypatch.setattr(history, "_recover_step", fail_second)
    run = stream(model)
    iterator = iter(run)
    next(iterator)
    first = json.loads(next(iterator))
    with pytest.raises(
        history.RCFiberControlHistoryError, match="original response failure"
    ):
        next(iterator)
    report = run.report
    assert report["accepted_target_count"] == 1
    assert (
        report["last_emitted_checkpoint_hash"]
        == first["accepted_checkpoint"]["state_hash"]
    )
    assert report["total_work"]["attempted_step_count"] == 2
    assert report["total_work"]["unknown_solver_work_attempt_count"] == 0
    assert report["response_reassembly_attempts"] == 2
    assert report["response_reassembly_verified_count"] == 1


def test_keyboard_interrupt_retains_started_unknown_call_and_original_exception(
    model, monkeypatch
):
    interruption = KeyboardInterrupt("cancelled inside core")

    def cancel(*args, **kwargs):
        raise interruption

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", cancel
    )
    run = stream(model)
    with pytest.raises(KeyboardInterrupt) as caught:
        list(run)
    assert caught.value is interruption
    assert run.report["status"] == "interrupted"
    assert run.report["core_invocations_started"] == 1
    assert run.report["total_work"]["unknown_solver_work_attempt_count"] == 1


@pytest.mark.parametrize(
    "targets, options",
    [
        ((), {}),
        ((1e-5, 1e-5), {}),
        ((True,), {}),
        ((float("nan"),), {}),
        ((1e-5,), {"maximum_targets": 4097}),
        ((1e-5,), {"maximum_targets": True}),
        ((1e-5,), {"config": False}),
        ((1e-5,), {"allow_reversals": False}),
    ],
)
def test_invalid_authored_inputs_reject_without_solves(
    model, monkeypatch, targets, options
):
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    with pytest.raises(ValueError):
        stream(model, targets, **options)


def test_iterator_is_lazy_single_use_and_report_is_detached(model, monkeypatch):
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    run = stream(model)
    assert run.report["status"] == "not_started"
    iterator = iter(run)
    next(iterator)  # Header only; no solve.
    iterator.close()
    assert run.report["status"] == "paused"
    report = run.report
    report["total_work"]["attempted_step_count"] = 100
    assert run.report["total_work"]["attempted_step_count"] == 0
    with pytest.raises(ValueError, match="single-use"):
        iter(run)


def test_source_mutation_by_prior_iterator_rejects_before_solve(model, monkeypatch):
    config = paths.StatefulFiberFrame2DDisplacementControlConfig()
    fresh = stream(model, config=config)
    iterator = iter(fresh)
    header = next(iterator)
    iterator.close()

    def prior():
        yield header
        object.__setattr__(config, "control_tolerance_m", 1e-9)
        yield b"{}"

    monkeypatch.setattr(history, "_execute_raw", forbidden)
    run = stream(model, config=config, prior_records=prior())
    with pytest.raises(history.RCFiberControlHistoryError, match="while reading prior"):
        list(run)
    assert run.report["core_invocations_started"] == 0


def test_zero_first_target_uses_actual_preloaded_origin(model):
    run = stream(
        model,
        (0.0,),
        constant_nodal_loads=(("N2", -600.0, -0.1, 0.0),),
        allow_reversals=False,
        maximum_reversals=0,
    )
    rows = [json.loads(raw) for raw in run]
    assert run.report["status"] == "ready"
    assert rows[1]["response"]["node_displacements"][1]["UY_m"] < 0
    assert rows[2]["response"]["node_displacements"][1]["UY_m"] == pytest.approx(
        0.0, abs=1e-12
    )
    assert run.report["total_work"]["attempted_step_count"] == 2


def test_origin_dependent_reversal_rejection_keeps_preload_cost(model, monkeypatch):
    # Preload displaces the controlled node below zero. The next two targets
    # reverse direction from that real origin, although both are negative.
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    run = stream(
        model,
        (-1e-8, -2e-8),
        constant_nodal_loads=(("N2", -600.0, -0.1, 0.0),),
        allow_reversals=False,
        maximum_reversals=0,
    )
    with pytest.raises(history.RCFiberControlHistoryError, match="reversal budget"):
        list(run)
    assert run.report["preload_work"]["attempted_step_count"] == 1
    assert run.report["accepted_target_count"] == 0
    assert run.report["emitted_transition_count"] == 1


def test_oversized_original_record_rejects_before_core_call(model, monkeypatch):
    fresh = stream(model)
    iterator = iter(fresh)
    header = next(iterator)
    iterator.close()
    monkeypatch.setattr(history, "_execute_raw", forbidden)
    monkeypatch.setattr(history, "HISTORY_RECORD_MAX_BYTES", len(header) + 1)
    # Rebuild the header because its declared byte bound is part of its identity.
    fresh = stream(model)
    iterator = iter(fresh)
    header = next(iterator)
    iterator.close()
    run = stream(
        model, prior_records=[header, b" " * (history.HISTORY_RECORD_MAX_BYTES + 1)]
    )
    with pytest.raises(history.RCFiberControlHistoryError, match="bounded nonempty"):
        list(run)
    assert run.report["core_invocations_started"] == 0


def test_header_only_prefix_is_valid_and_full_prefix_rechecks_all_targets(
    model, actual
):
    options, report, records, _ = actual
    for prior, replay_count in ((records[:1], 0), (records, len(records) - 1)):
        run = stream(model, prior_records=prior, **options)
        assert list(run) == records
        assert run.report["status"] == "ready"
        assert run.report["replayed_transition_count"] == replay_count
        assert run.report["total_work"] == report["total_work"]


def test_unbounded_target_iterator_is_stopped_at_declared_budget(model, monkeypatch):
    consumed = 0

    def targets():
        nonlocal consumed
        while True:
            consumed += 1
            yield consumed * 1e-7

    monkeypatch.setattr(history, "_compile", forbidden)
    with pytest.raises(ValueError, match="target budget"):
        stream(model, targets(), maximum_targets=300)
    assert consumed == 301
