"""Declared two-trial search, truthful work, and immutable retry authority."""

from dataclasses import replace
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear import newton
from tests.test_rc_nonlinear_reversal_integration import SEARCH
from tests.test_rc_pin_roller_main import model

CONFIG = replace(SEARCH, initial_trial_policy="accepted_then_prescribed")


@pytest.fixture(scope="module")
def witness():
    payload = (
        Path(__file__).parent / "fixtures/rc_mathern_nominal_uncalibrated.json"
    ).read_bytes()
    compiled, blockers, _ = _compile(
        load_neutral_json_bytes(payload), experimental_pin_roller_beam=True
    )
    assert compiled is not None and not blockers
    targets = (-1e-5, -1e-4, -2.5e-4) + tuple(-i * 0.0005 for i in range(1, 37))
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets, control_global_dof=10, config=SEARCH
    )
    assert prefix.status == "ready"
    return compiled.problem, prefix.final_checkpoint


def run(witness, config=CONFIG):
    problem, parent = witness
    return control.solve_stateful_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_global_dof=10,
        target_control_displacement_m=-0.0185,
        config=config,
    )


def test_retry_work_matches_instrumented_dense_solves_and_commits_once(
    witness, monkeypatch
):
    problem, parent = witness
    original = parent.canonical_bytes()
    calls = []
    solve = newton._solve_vector_increment

    def counted(*args, **kwargs):
        calls.append(1)
        return solve(*args, **kwargs)

    monkeypatch.setattr(newton, "_solve_vector_increment", counted)
    step = run(witness)
    trace = step.initial_trial_search()
    work = step.solver_work()
    assert step.committed and len(trace["trials"]) == 2
    assert [r["committed"] for r in trace["trials"]] == [False, True]
    assert (
        trace["trials"][0]["solver"]["metrics"]["terminal_reason"]
        == "line_search_failed_to_reduce_residual"
    )
    assert work["linear_solve_count"] == work["iteration_count"] == len(calls)
    assert work["initial_trial_unknown_work_count"] == 0
    assert (
        work["linear_solve_count"] > step.trial_solution.metrics["linear_solve_count"]
    )
    assert step.accepted_checkpoint.epoch == parent.epoch + 1
    assert step.accepted_checkpoint.parent_state_hash == parent.state_hash
    assert parent.canonical_bytes() == original
    trace["trials"][0]["solver"]["metrics"]["detail"] = "changed detached copy"
    assert (
        step.initial_trial_search()["trials"][0]["solver"]["metrics"]["detail"]
        != "changed detached copy"
    )
    assert run(witness).step_hash == step.step_hash


def test_second_trial_exception_keeps_first_work_and_unknown_attempt(
    witness, monkeypatch
):
    problem, parent = witness
    original = parent.canonical_bytes()
    actual = control.newton_raphson_vector
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("bounded injected failure")
        return actual(*args, **kwargs)

    monkeypatch.setattr(control, "newton_raphson_vector", fail_second)
    terminal, steps, attempts = paths._execute_raw(
        problem, parent, (-0.0185,), 10, CONFIG, problem.contract_hash, phase="suffix"
    )
    assert terminal is parent and steps == () and len(calls) == 2
    work = paths._counts(attempts)
    assert work["known_linear_solve_count"] > 0
    assert work["unknown_solver_work_attempt_count"] == 1
    assert attempts[0]["solver_work"]["declared_initial_trial_attempt_count"] == 2
    assert parent.canonical_bytes() == original


def test_first_exception_does_not_retry(witness, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("first failure")

    monkeypatch.setattr(control, "newton_raphson_vector", fail)
    with pytest.raises(control.StatefulFiberInitialTrialSearchError) as error:
        run(witness)
    assert len(calls) == 1
    assert error.value.solver_work()["initial_trial_unknown_work_count"] == 1


def test_limited_iterations_do_not_trigger_undeclared_retry(witness):
    step = run(
        witness, replace(CONFIG, newton=replace(CONFIG.newton, max_iterations=0))
    )
    assert not step.committed and step.accepted_checkpoint is witness[1]
    assert len(step.initial_trial_search()["trials"]) == 1
    assert step.solver_work()["initial_trial_unknown_work_count"] == 1


def test_search_restart_reversal_and_policy_binding():
    compiled, blockers, _ = _compile(model(), experimental_pin_roller_beam=True)
    assert compiled is not None and not blockers
    targets = (-1e-6, -2e-6, 1e-6, 0.0)
    options = dict(control_global_dof=10, allow_reversals=True, maximum_reversals=2)
    full = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets, config=CONFIG, **options
    )
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets[:2], config=CONFIG, **options
    )
    resumed = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem,
        targets[2:],
        config=CONFIG,
        restart=prefix.restart_artifact(),
        **options,
    )
    assert full.status == resumed.status == "ready"
    assert full.restart_artifact() == resumed.restart_artifact()
    assert all(len(step.initial_trial_search()["trials"]) == 1 for step in full.steps)
    request = BoundedRCFiberDirectControlRequest(
        10, targets, CONFIG, True, 2, experimental_pin_roller_beam=True
    )
    assert decode_bounded_rc_fiber_direct_control_request(request.to_dict()) == request
    with pytest.raises(
        ValueError, match="source/configuration/control/budget mismatch"
    ):
        paths.run_stateful_fiber_frame2d_control_path(
            compiled.problem,
            targets[2:],
            config=SEARCH,
            restart=prefix.restart_artifact(),
            **options,
        )


def test_both_failed_trials_restore_parent_and_retain_both_costs(witness, monkeypatch):
    original = control.StatefulFiberFrame2DDisplacementControlStepAdapter.initial_free_displacements_m

    def force_accepted_start(adapter):
        return original(
            replace(
                adapter,
                config=replace(
                    adapter.config, initial_trial_policy="accepted_checkpoint"
                ),
            )
        )

    monkeypatch.setattr(
        control.StatefulFiberFrame2DDisplacementControlStepAdapter,
        "initial_free_displacements_m",
        force_accepted_start,
    )
    before = witness[1].canonical_bytes()
    step = run(witness)
    assert not step.committed and step.accepted_checkpoint is witness[1]
    trace = step.initial_trial_search()
    assert len(trace["trials"]) == 2 and all(
        not r["committed"] for r in trace["trials"]
    )
    assert step.solver_work()["initial_trial_unknown_work_count"] == 0
    assert step.solver_work()["linear_solve_count"] == sum(
        r["work"]["known_linear_solve_count"] for r in trace["trials"]
    )
    assert witness[1].canonical_bytes() == before


def test_frozen_failed_trial_survives_later_metadata_mutation(witness, monkeypatch):
    actual = control.newton_raphson_vector
    observed = []

    def mutate_prior(*args, **kwargs):
        if observed:
            observed[0].metrics["detail"] = "later mutation"
        result = actual(*args, **kwargs)
        observed.append(result)
        return result

    monkeypatch.setattr(control, "newton_raphson_vector", mutate_prior)
    step = run(witness)
    assert step.committed
    assert (
        step.initial_trial_search()["trials"][0]["solver"]["metrics"]["detail"]
        == "line_search_failed_to_reduce_residual"
    )


def test_mutated_parent_never_gets_a_second_trial(witness, monkeypatch):
    problem, old = witness
    parent = replace(old)
    actual = control.newton_raphson_vector
    calls = []

    def corrupt(*args, **kwargs):
        calls.append(1)
        result = actual(*args, **kwargs)
        values = list(parent.global_displacements)
        values[0] += 1e-4
        object.__setattr__(parent, "global_displacements", tuple(values))
        return result

    monkeypatch.setattr(control, "newton_raphson_vector", corrupt)
    with pytest.raises(
        control.StatefulFiberInitialTrialSearchError, match="source or parent changed|checkpoint state hash validation failed"
    ):
        run((problem, parent))
    assert len(calls) == 1


def test_initial_trace_tampering_is_not_exportable(witness):
    import json

    step = run(witness)
    for change in ("work", "parent", "budget", "terminal"):
        trace = step.initial_trial_search()
        if change == "work":
            trace["trials"][0]["work"]["known_linear_solve_count"] = -1
        elif change == "parent":
            trace["trials"][0]["parent_checkpoint_hash"] = "sha256:" + "0" * 64
        elif change == "budget":
            trace["maximum_trials"] = 3
        else:
            trace["trials"][-1]["solver"]["metrics"]["linear_solve_count"] += 1
        forged = replace(step, initial_trial_search_json=json.dumps(trace).encode())
        with pytest.raises(ValueError, match="initial trial"):
            forged.to_dict()
