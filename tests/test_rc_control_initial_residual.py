"""Physical assembler observations, noncommit authority and failed-work retention."""

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.benchmark.rc_control_initial_residual import (
    observe_rc_control_initial_residuals,
)


def setup():
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    seed = tuple(0.0 for _ in range(len(problem.free_global_dofs) + 1))
    return problem, parent, seed


@pytest.mark.parametrize("retained", [False, True])
def test_residual_matches_actual_first_newton_assembly_and_preserves_parent(retained):
    problem, parent, seed = setup()
    if retained:
        problem = replace(
            problem,
            coordinate_precision="twofold-increment",
            members=tuple(
                replace(
                    member,
                    element=replace(
                        member.element,
                        coordinate_precision="twofold-increment",
                        strain_evaluation="exact-rational",
                    ),
                )
                for member in problem.members
            ),
        )
        parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    advance = control.solve_stateful_fiber_frame2d_displacement_control_step(
        problem, parent, control_global_dof=7, target_control_displacement_m=-0.5e-6
    )
    assert advance.committed
    parent = advance.accepted_checkpoint
    before = parent.canonical_bytes()
    other_seed = list(seed)
    other_seed[problem.free_global_dofs.index(7)] = -0.75e-6
    candidates = {"zero": seed, "displaced": tuple(other_seed)}
    report = observe_rc_control_initial_residuals(
        problem, parent, control_global_dof=7, target_m=-1e-6, candidates=candidates
    )
    assert report["complete"] and report["parent_unchanged"]
    assert not report["committed"] and not report["candidate_selected"]
    assert report["newton_solves"] == 0 and parent.canonical_bytes() == before
    for row in report["rows"]:
        solved = control.solve_stateful_fiber_frame2d_displacement_control_step(
            problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=-1e-6,
            initial_augmented_coordinates_m=candidates[row["name"]],
        )
        first = solved.trial_solution.convergence_history[0]
        assert row["initial_augmented_coordinates_m"] == list(candidates[row["name"]])
        assert parent.canonical_bytes() == before
        assert row["relative_residual"] == first["relative_residual"]
        assert np.array_equal(row["residual_kn"], first["residual_kn"])
        assert row["assembly_attempts"] == 1 and not row["unknown_work"]


def test_all_candidates_preflight_before_any_assembly(monkeypatch):
    problem, parent, seed = setup()

    def forbidden(*args):
        pytest.fail("must reject all malformed inputs before assembly")

    monkeypatch.setattr(
        control.StatefulFiberFrame2DDisplacementControlStepAdapter, "observe", forbidden
    )
    with pytest.raises(ValueError):
        observe_rc_control_initial_residuals(
            problem,
            parent,
            control_global_dof=7,
            target_m=-1e-6,
            candidates={"valid": seed, "invalid": (float("nan"),)},
        )


def test_failed_assembly_is_retained_without_running_later_candidates(monkeypatch):
    problem, parent, seed = setup()
    before = parent.canonical_bytes()
    calls = []

    def fail(*args):
        calls.append(1)
        raise ValueError("assembly diagnostic failure")

    monkeypatch.setattr(
        control.StatefulFiberFrame2DDisplacementControlStepAdapter, "observe", fail
    )
    report = observe_rc_control_initial_residuals(
        problem,
        parent,
        control_global_dof=7,
        target_m=-1e-6,
        candidates={"first": seed, "later": seed},
    )
    assert calls == [1] and not report["complete"]
    assert len(report["rows"]) == 1 and report["rows"][0]["unknown_work"]
    assert report["rows"][0]["error_type"] == "ValueError"
    assert parent.canonical_bytes() == before and not report["committed"]


def test_coordinate_failure_does_not_claim_an_assembly(monkeypatch):
    problem, parent, seed = setup()

    def fail(*args):
        raise ValueError("coordinate conversion failed")

    monkeypatch.setattr(
        control.StatefulFiberFrame2DDisplacementControlStepAdapter,
        "initial_free_displacements_m",
        fail,
    )
    report = observe_rc_control_initial_residuals(
        problem,
        parent,
        control_global_dof=7,
        target_m=-1e-6,
        candidates={"first": seed},
    )
    assert not report["complete"]
    assert report["rows"][0]["assembly_attempts"] == 0
    assert report["rows"][0]["unknown_work"]
    assert report["target_m"] == -1e-6 and report["control_global_dof"] == 7
