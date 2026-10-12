"""A control-feasible trial crosses a damage kink without changing targets."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig as Config,
    solve_stateful_fiber_frame2d_displacement_control_step as solve_step,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

TARGETS = (0.0003, 0.0015, 0.0045, 0.009, 0.003, -0.0015, -0.006, 0.0, 0.006)
OPTIONS = dict(
    control_global_dof=3,
    allow_reversals=True,
    maximum_reversals=4,
    config=Config(initial_guess="control_target"),
)


@pytest.fixture(scope="module")
def problem():
    source = json.loads(
        (
            Path(__file__).parents[1]
            / "examples/public_rc_fiber_frame_explicit_layers.json"
        ).read_text()
    )
    source["loads"][0]["components"].update(FX=1, FY=0)
    compiled, blockers, _ = _compile(
        load_neutral_json_bytes(json.dumps(source).encode())
    )
    assert not blockers
    # Internal boundary only: this does not widen the public compiler profile.
    return replace(compiled.problem, fixed_global_dofs=(0, 1, 2, 4, 5))


@pytest.fixture(scope="module")
def histories(problem):
    full = paths.run_stateful_fiber_frame2d_control_path(problem, TARGETS, **OPTIONS)
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        problem, TARGETS[:4], **OPTIONS
    )
    assert full.status == prefix.status == "ready"
    return full, prefix


def test_damage_kink_yield_and_two_reversals_reach_all_authored_targets(histories):
    full, _ = histories
    assert full.accepted_target_prefix_m == TARGETS
    assert full.metrics["hidden_retries_or_cutbacks"] == 0
    states = [
        s
        for e in full.final_checkpoint.element_states
        for q in e.integration_point_states
        for s in q.fiber_states
    ]
    steel = [s for s in states if isinstance(s, UniaxialPlasticityState)]
    concrete = [s for s in states if isinstance(s, ConcreteDamageState)]
    assert max(s.accumulated_plastic_strain for s in steel) > 0.005
    assert max(s.tensile_damage for s in concrete) > 0
    assert max(s.compressive_damage for s in concrete) > 0
    for target, step in zip(TARGETS, full.steps, strict=True):
        assert step.committed
        assert step.accepted_checkpoint.global_displacements[3] == pytest.approx(
            target, abs=1e-12
        )
        assert all(
            step.accepted_checkpoint.global_displacements[i] == 0
            for i in (0, 1, 2, 4, 5)
        )
        assert step.metrics["equilibrium_gate_passed"]


def test_nonlinear_restart_and_failed_trial_preserve_exact_state(problem, histories):
    full, prefix = histories
    resumed = paths.run_stateful_fiber_frame2d_control_path(
        problem, TARGETS[4:], restart=prefix.restart_artifact(), **OPTIONS
    )
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )
    assert resumed.restart_artifact() == full.restart_artifact()
    assert resumed.metrics["prefix_replayed_step_count"] == 4
    parent = prefix.final_checkpoint
    before = parent.canonical_bytes()
    failed = solve_step(
        problem,
        parent,
        control_global_dof=3,
        target_control_displacement_m=TARGETS[4],
        config=Config(
            newton=NewtonRaphsonConfig(max_iterations=0), initial_guess="control_target"
        ),
    )
    assert not failed.committed
    assert failed.metrics["rollback_exact"]
    assert (
        before
        == parent.canonical_bytes()
        == failed.accepted_checkpoint.canonical_bytes()
    )


def test_legacy_initial_guess_restart_rejected_before_any_solver_work(
    problem, histories, monkeypatch
):
    payload = json.loads(histories[1].restart_artifact())
    config = payload["scope"]["configuration"]
    config["profile"] = "small-displacement-rc-fiber-direct-control.v1"
    config.pop("initial_guess")
    payload["scope"]["configuration_hash"] = canonical_hash(config)
    payload.pop("artifact_hash")
    payload["artifact_hash"] = paths._hash(paths._json(payload))

    def forbidden(*args, **kwargs):
        pytest.fail("configuration mismatch must reject before replay")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    with pytest.raises(
        ValueError, match="source/configuration/control/budget mismatch"
    ):
        paths.run_stateful_fiber_frame2d_control_path(
            problem, TARGETS[4:], restart=paths._json(payload), **OPTIONS
        )
