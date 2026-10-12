"""Explicit third seed, accepted-state ancestry, and restart history continuity."""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear import newton
from tests.test_rc_initial_trial_search import CONFIG
from tests.test_rc_pin_roller_main import model

SECANT = replace(CONFIG, initial_trial_policy="accepted_then_prescribed_then_secant")


@pytest.fixture(scope="module")
def crossing_path():
    payload = (
        Path(__file__).parent / "fixtures/rc_mathern_nominal_uncalibrated.json"
    ).read_bytes()
    compiled, blockers, _ = _compile(
        load_neutral_json_bytes(payload), experimental_pin_roller_beam=True
    )
    assert compiled is not None and not blockers
    targets = (
        (-1e-5, -0.0001, -0.00025, -0.0005)
        + tuple(-i / 2000 for i in range(2, 51))
        + tuple(-i / 400 for i in range(9, -1, -1))
    )
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem,
        targets,
        control_global_dof=10,
        config=SECANT,
        allow_reversals=True,
        maximum_reversals=2,
    )
    assert prefix.status == "ready" and len(prefix.steps) == 63
    return compiled.problem, prefix


@pytest.fixture(scope="module")
def zero_crossing(crossing_path):
    problem, prefix = crossing_path
    return problem, prefix.steps[-1].parent_checkpoint, prefix.final_checkpoint


def step(witness, **kwargs):
    problem, previous, parent = witness
    return control.solve_stateful_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_global_dof=10,
        target_control_displacement_m=0.0025,
        config=SECANT,
        previous_checkpoint=previous,
        **kwargs,
    )


def test_third_seed_resolves_real_zero_crossing_and_counts_every_solve(
    zero_crossing, monkeypatch
):
    problem, previous, parent = zero_crossing
    before = (previous.canonical_bytes(), parent.canonical_bytes())
    calls = []
    actual = newton._solve_vector_increment

    def counted(*args, **kwargs):
        calls.append(1)
        return actual(*args, **kwargs)

    monkeypatch.setattr(newton, "_solve_vector_increment", counted)
    result = step(zero_crossing)
    assert result.committed
    trace = result.initial_trial_search()
    assert [t["committed"] for t in trace["trials"]] == [False, False, True]
    assert trace["maximum_trials"] == 3
    assert (
        trace["trials"][-1]["prediction"]["previous_checkpoint_hash"]
        == previous.state_hash
    )
    assert result.solver_work()["linear_solve_count"] == len(calls)
    assert result.solver_work()["initial_trial_unknown_work_count"] == 0
    assert before == (previous.canonical_bytes(), parent.canonical_bytes())
    assert result.accepted_checkpoint.epoch == parent.epoch + 1
    assert result.accepted_checkpoint.parent_state_hash == parent.state_hash
    forged = json.loads(json.dumps(trace))
    forged["trials"][-1]["prediction"]["ratio"] += 1
    with pytest.raises(ValueError, match="secant prediction"):
        replace(result, initial_trial_search_json=json.dumps(forged).encode()).to_dict()


def test_predictor_rejects_nonadjacent_state_before_newton(zero_crossing, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid predecessor reached Newton")

    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    problem, previous, parent = zero_crossing
    with pytest.raises(ValueError, match="immediate accepted parent"):
        step((problem, parent, parent))


def test_missing_predecessor_does_not_invent_a_third_trial(zero_crossing):
    problem, _, parent = zero_crossing
    result = step((problem, None, parent))
    trace = result.initial_trial_search()
    assert not result.committed and result.accepted_checkpoint is parent
    assert trace["secant_predecessor_hash"] is None
    assert len(trace["trials"]) == 2
    assert result.solver_work()["initial_trial_unknown_work_count"] == 0


def test_old_policy_rejects_predecessor_before_newton(zero_crossing, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("undeclared predecessor reached Newton")

    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    problem, previous, parent = zero_crossing
    with pytest.raises(ValueError, match="requires the declared secant policy"):
        control.solve_stateful_fiber_frame2d_displacement_control_step(
            problem,
            parent,
            control_global_dof=10,
            target_control_displacement_m=0.0025,
            config=CONFIG,
            previous_checkpoint=previous,
        )


def test_secant_coordinate_scaling_and_source_binding(zero_crossing):
    problem, previous, parent = zero_crossing
    adapter, prediction = control._secant_prediction(
        problem, parent, previous, 10, 0.0025, SECANT
    )
    physical = np.asarray(parent.global_displacements) + prediction["ratio"] * (
        np.asarray(parent.global_displacements)
        - np.asarray(previous.global_displacements)
    )
    expected = np.r_[
        (physical / problem.physical_coordinate_scale)[list(problem.free_global_dofs)],
        SECANT.load_factor_coordinate_scale_m
        * (
            parent.load_factor
            + prediction["ratio"] * (parent.load_factor - previous.load_factor)
        ),
    ]
    np.testing.assert_allclose(
        adapter.initial_free_displacements_m(), expected, rtol=1e-14, atol=1e-20
    )
    assert prediction["parent_checkpoint_hash"] == parent.state_hash


def test_secant_bootstrap_and_split_history_are_exact():
    compiled, blockers, _ = _compile(model(), experimental_pin_roller_beam=True)
    assert compiled is not None and not blockers
    options = dict(
        control_global_dof=10, config=SECANT, allow_reversals=True, maximum_reversals=2
    )
    targets = (-1e-6, -2e-6, 1e-6, 0.0)
    full = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets, **options
    )
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets[:2], **options
    )
    resumed = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets[2:], restart=prefix.restart_artifact(), **options
    )
    assert full.status == resumed.status == "ready"
    assert full.restart_artifact() == resumed.restart_artifact()
    assert full.steps[0].initial_trial_search()["secant_predecessor_hash"] is None
    assert (
        resumed.steps[0].initial_trial_search()["secant_predecessor_hash"]
        == prefix.steps[-1].parent_checkpoint.state_hash
    )


def test_third_seed_restart_boundary_reconstructs_the_same_history(
    crossing_path, zero_crossing
):
    problem, prefix = crossing_path
    uninterrupted_step = step(zero_crossing)
    resumed = paths.run_stateful_fiber_frame2d_control_path(
        problem,
        (0.0025,),
        control_global_dof=10,
        config=SECANT,
        allow_reversals=True,
        maximum_reversals=2,
        restart=prefix.restart_artifact(),
    )
    assert resumed.status == "ready"
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == uninterrupted_step.accepted_checkpoint.canonical_bytes()
    )
    assert resumed.steps[0].to_dict() == uninterrupted_step.to_dict()
    assert len(resumed.steps[0].initial_trial_search()["trials"]) == 3
    with pytest.raises(
        ValueError, match="source/configuration/control/budget mismatch"
    ):
        paths.run_stateful_fiber_frame2d_control_path(
            problem,
            (0.0025,),
            control_global_dof=10,
            config=CONFIG,
            allow_reversals=True,
            maximum_reversals=2,
            restart=prefix.restart_artifact(),
        )


def test_third_exception_retains_two_failures_and_unknown_work(
    zero_crossing, monkeypatch
):
    actual = control.newton_raphson_vector
    calls = []

    def fail_third(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("bounded third trial failure")
        return actual(*args, **kwargs)

    monkeypatch.setattr(control, "newton_raphson_vector", fail_third)
    problem, previous, parent = zero_crossing
    before = (previous.canonical_bytes(), parent.canonical_bytes())
    with pytest.raises(control.StatefulFiberInitialTrialSearchError) as error:
        step(zero_crossing)
    work = error.value.solver_work()
    assert len(calls) == work["declared_initial_trial_attempt_count"] == 3
    assert work["initial_trial_unknown_work_count"] == 1
    assert work["linear_solve_count"] > 0
    assert before == (previous.canonical_bytes(), parent.canonical_bytes())
