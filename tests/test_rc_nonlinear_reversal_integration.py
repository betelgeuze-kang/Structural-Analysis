"""Authored nonlinear beam histories; no measured specimen or speedup claims."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig
from tests.test_rc_pin_roller_main import beam


TARGETS = tuple(-i * 1e-5 for i in range(1, 12)) + (-5e-5, 5e-5, 0.0)
OPTIONS = dict(control_global_dof=10, allow_reversals=True, maximum_reversals=3)
# Declared extra search work, with the SAME equilibrium/increment/control gates.
# Keep default-policy failure tests: this is not a silent retry or new default.
SEARCH = StatefulFiberFrame2DDisplacementControlConfig(
    newton=NewtonRaphsonConfig(
        max_iterations=100, line_search_alphas=tuple(2.0**-i for i in range(16))
    )
)


def problem_for(material_case):
    payload = beam()
    layers = json.loads(
        (
            Path(__file__).parents[1]
            / "examples/public_rc_fiber_frame_explicit_layers.json"
        ).read_text()
    )
    payload.update({key: layers[key] for key in ("materials", "sections")})
    if material_case == "synthetic-early-yield":
        # Deliberately nonphysical low strengths exercise both yield laws before
        # damage. They are not fitted to an experiment or claimed as RC inputs.
        for material in payload["materials"]:
            if material["type"] == "bilinear_combined_hardening_steel":
                material["yield_stress_mpa"] = 4.0 if material["id"] == "steel" else 8.0
    model = load_neutral_json_bytes(json.dumps(payload).encode())
    compiled, blockers, _ = _compile(model, experimental_pin_roller_beam=True)
    assert compiled is not None and not blockers
    return compiled.problem


def states(checkpoint):
    return tuple(
        state
        for element in checkpoint.element_states
        for section in element.integration_point_states
        for state in section.fiber_states
    )


@pytest.fixture(scope="module", params=["authored-damage", "synthetic-early-yield"])
def history(request):
    problem = problem_for(request.param)
    full = paths.run_stateful_fiber_frame2d_control_path(
        problem, TARGETS, config=SEARCH, **OPTIONS
    )
    assert full.status == "ready"
    return request.param, problem, full


def test_nonlinear_histories_really_damage_and_reverse_without_healing(history):
    case, _, full = history
    assert full.accepted_target_prefix_m == TARGETS
    assert full.to_dict()["accepted_reversal_count"] == 2
    assert full.metrics["hidden_retries_or_cutbacks"] == 0
    previous = states(full.initial_checkpoint)
    for target, step in zip(TARGETS, full.steps, strict=True):
        assert step.committed
        assert step.metrics["control_gate_passed"]
        assert step.metrics["equilibrium_gate_passed"]
        assert abs(step.accepted_checkpoint.global_displacements[10] - target) <= 1e-12
        current = states(step.accepted_checkpoint)
        for old, new in zip(previous, current, strict=True):
            assert (
                new.dissipated_energy_density_mj_per_m3
                >= old.dissipated_energy_density_mj_per_m3
            )
            if isinstance(new, UniaxialPlasticityState):
                assert new.accumulated_plastic_strain >= old.accumulated_plastic_strain
            else:
                assert new.tensile_damage >= old.tensile_damage
                assert new.compressive_damage >= old.compressive_damage
        previous = current
    assert max(getattr(s, "tensile_damage", 0) for s in previous) > 0.03
    plastic = max(
        s.accumulated_plastic_strain
        for s in previous
        if isinstance(s, UniaxialPlasticityState)
    )
    if case == "synthetic-early-yield":
        assert plastic > 2e-4
        assert (
            sum(
                s.accumulated_plastic_strain > 0
                for s in previous
                if isinstance(s, UniaxialPlasticityState)
            )
            > 1
        )
    else:
        assert plastic == 0  # Damage success must not be described as steel yield.


@pytest.mark.parametrize("split", [1, 11, 13])
def test_restarts_before_yield_after_damage_and_after_reversal_are_exact(
    history, split
):
    _, problem, full = history
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        problem, TARGETS[:split], config=SEARCH, **OPTIONS
    )
    raw = prefix.restart_artifact()
    resumed = paths.run_stateful_fiber_frame2d_control_path(
        problem, TARGETS[split:], restart=raw, config=SEARCH, **OPTIONS
    )
    assert resumed.status == "ready"
    assert prefix.restart_artifact() == raw
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )
    assert resumed.restart_artifact() == full.restart_artifact()
    assert len(resumed.replayed_steps) == split
    assert resumed.metrics["total_work"]["attempted_step_count"] == len(TARGETS)
    assert resumed.metrics["prefix_replay_work"]["attempted_step_count"] == split


def test_half_sized_increments_also_reach_nonlinear_reversed_state(history):
    _, problem, _ = history
    targets = tuple(-i * 5e-6 for i in range(1, 23)) + TARGETS[-3:]
    result = paths.run_stateful_fiber_frame2d_control_path(
        problem, targets, config=SEARCH, **OPTIONS
    )
    assert result.status == "ready"
    assert result.accepted_target_prefix_m == targets
    assert result.metrics["total_work"]["attempted_step_count"] == len(targets)
    assert result.metrics["hidden_retries_or_cutbacks"] == 0
    assert (
        max(getattr(s, "tensile_damage", 0) for s in states(result.final_checkpoint))
        > 0
    )


def test_default_policy_failure_retains_exact_parent_and_unknown_future(history):
    _, problem, _ = history
    result = paths.run_stateful_fiber_frame2d_control_path(problem, TARGETS, **OPTIONS)
    assert result.status == "blocked"
    failed = result.steps[-1]
    assert not failed.committed
    assert (
        failed.trial_solution.metrics["terminal_reason"]
        == "line_search_failed_to_reduce_residual"
    )
    assert (
        failed.accepted_checkpoint.canonical_bytes()
        == failed.parent_checkpoint.canonical_bytes()
    )
    assert (
        result.final_checkpoint.canonical_bytes()
        == failed.parent_checkpoint.canonical_bytes()
    )
    accepted = len(result.accepted_target_prefix_m)
    assert result.accepted_target_prefix_m == TARGETS[:accepted]
    assert result.unattempted_targets_m == TARGETS[accepted + 1 :]
    retry = paths.run_stateful_fiber_frame2d_control_path(
        problem, TARGETS[accepted:], restart=result.restart_artifact(), **OPTIONS
    )
    assert retry.status == "blocked"
    assert retry.restart_artifact() == result.restart_artifact()
    assert len(retry.steps) == 1
    assert retry.metrics["prefix_replay_work"]["attempted_step_count"] == accepted
    assert retry.metrics["total_work"]["attempted_step_count"] == accepted + 1


def test_restart_cannot_silently_change_search_budget(history, monkeypatch):
    _, problem, full = history

    def forbidden(*args, **kwargs):
        pytest.fail("changed restart policy must reject before replay")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    with pytest.raises(
        ValueError, match="source/configuration/control/budget mismatch"
    ):
        paths.run_stateful_fiber_frame2d_control_path(
            problem,
            (-1e-5,),
            restart=full.restart_artifact(),
            config=replace(SEARCH, newton=replace(SEARCH.newton, max_iterations=99)),
            **OPTIONS,
        )


def test_declared_search_policy_preserves_tolerances_and_public_request_roundtrip():
    default = StatefulFiberFrame2DDisplacementControlConfig()
    assert SEARCH.newton.residual_tolerance == default.newton.residual_tolerance
    assert SEARCH.newton.increment_tolerance == default.newton.increment_tolerance
    assert SEARCH.control_tolerance_m == default.control_tolerance_m
    request = BoundedRCFiberDirectControlRequest(
        10,
        TARGETS,
        solver_config=SEARCH,
        allow_reversals=True,
        maximum_reversals=3,
        experimental_pin_roller_beam=True,
    )
    assert decode_bounded_rc_fiber_direct_control_request(request.to_dict()) == request
