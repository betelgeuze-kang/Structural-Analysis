"""Numerical regression, not measured validation of the Mathern beam.

Nominal geometry/material E/strength inputs: Mathern & Yang 2021,
https://doi.org/10.3390/ma14030506, Figure 1/Table 1. The fixture deliberately
uses an uncalibrated perfect-bond small-displacement model, perfectly plastic
steel and software-default concrete damage rates (3000/400). It does not
reproduce the paper's CDP/bond law, rupture, shrinkage or experimental curve.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    solve_stateful_fiber_frame2d_displacement_control_step as solve,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from tests.test_rc_nonlinear_reversal_integration import SEARCH
from tests.test_rc_pin_roller_main import model

PRESCRIBED = replace(SEARCH, initial_trial_policy="prescribed_control")


def test_nominal_beam_crack_onset_uses_same_equations_and_gates():
    payload = (
        Path(__file__).parent / "fixtures/rc_mathern_nominal_uncalibrated.json"
    ).read_bytes()
    compiled, blockers, _ = _compile(
        load_neutral_json_bytes(payload), experimental_pin_roller_beam=True
    )
    assert compiled is not None and not blockers
    targets = (-1e-5, -1e-4, -2.5e-4) + tuple(-i * 0.0005 for i in range(1, 37))
    targets += tuple(-i / 10000 for i in range(181, 185))
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem,
        targets,
        control_global_dof=10,
        config=SEARCH,
    )
    assert prefix.status == "ready"
    # Pins the historical configuration identity: opt-in must not rewrite it.
    assert (
        SEARCH.contract_hash
        == "sha256:3bf1e7dd28ae549e2573e3b851783224444e0b20880c32522b8b2c130c72ddf0"
    )
    parent = prefix.final_checkpoint
    original = parent.canonical_bytes()
    legacy = solve(
        compiled.problem,
        parent,
        control_global_dof=10,
        target_control_displacement_m=-0.0185,
        config=SEARCH,
    )
    assert not legacy.committed
    assert (
        legacy.trial_solution.metrics["terminal_reason"]
        == "line_search_failed_to_reduce_residual"
    )
    assert legacy.accepted_checkpoint is parent
    chosen = solve(
        compiled.problem,
        parent,
        control_global_dof=10,
        target_control_displacement_m=-0.0185,
        config=PRESCRIBED,
    )
    assert chosen.committed
    assert chosen.metrics["equilibrium_gate_passed"]
    assert chosen.metrics["control_gate_passed"]
    assert chosen.trial_solution.metrics["increment_gate_passed"]
    assert not chosen.trial_solution.metrics["fallback_used"]
    assert not chosen.trial_solution.metrics["regularization_used"]
    assert abs(chosen.accepted_checkpoint.global_displacements[10] + 0.0185) <= 1e-12
    assert parent.canonical_bytes() == original
    failed = solve(
        compiled.problem,
        parent,
        control_global_dof=10,
        target_control_displacement_m=-0.0185,
        config=replace(PRESCRIBED, newton=replace(SEARCH.newton, max_iterations=0)),
    )
    assert not failed.committed and failed.accepted_checkpoint is parent
    assert parent.canonical_bytes() == original


def test_opted_path_restart_reversal_and_policy_mismatch(monkeypatch):
    compiled, blockers, _ = _compile(model(), experimental_pin_roller_beam=True)
    assert compiled is not None and not blockers
    targets = (-1e-6, -2e-6, 1e-6, 0.0)
    options = dict(control_global_dof=10, allow_reversals=True, maximum_reversals=2)
    full = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets, config=PRESCRIBED, **options
    )
    prefix = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem, targets[:2], config=PRESCRIBED, **options
    )
    resumed = paths.run_stateful_fiber_frame2d_control_path(
        compiled.problem,
        targets[2:],
        config=PRESCRIBED,
        restart=prefix.restart_artifact(),
        **options,
    )
    assert full.status == resumed.status == "ready"
    assert full.restart_artifact() == resumed.restart_artifact()

    def forbidden(*args, **kwargs):
        pytest.fail("policy mismatch must reject before replay")

    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
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
