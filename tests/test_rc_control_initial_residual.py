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


def runtime_observation(tmp_path, enabled=True):
    from pathlib import Path
    from structural_analysis.io.neutral.loader import load_neutral_json
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        benchmark_rc_control_seed_paths,
        secant_seed,
    )

    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    request = BoundedRCFiberDirectControlRequest(
        7, (-1e-6, -2e-6, 1e-6, 0.0), allow_reversals=True, maximum_reversals=3
    )
    return benchmark_rc_control_seed_paths(
        model,
        request,
        source_revision="0" * 40,
        output_directory=tmp_path,
        proposal=secant_seed,
        proposal_identity="sha256:" + "a" * 64,
        proposal_abstention_strategy="secant",
        observe_initial_residuals=enabled,
    )


def test_full_path_observation_keeps_actual_steps_and_charges_extra_work(
    tmp_path, monkeypatch
):
    report = runtime_observation(tmp_path / "observed")
    assert report["comparisons"]["proposal"]["full_history_pass"]
    arm = report["arms"]["proposal"]
    observed = [
        entry["initial_residual_observation"]
        for entry in arm["entries"]
        if "initial_residual_observation" in entry
    ]
    assert len(observed) == 3
    import importlib
    from copy import deepcopy
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    audit = importlib.import_module("audit_rc_pooled_runtime_campaign")
    assert audit.require_observations(report, True)[0] == 6
    damaged = deepcopy(report)
    damaged["arms"]["proposal"]["entries"][1]["initial_residual_observation"][
        "parent_hash"
    ] = "wrong"
    with pytest.raises(ValueError, match="parent or authority"):
        audit.require_observations(damaged, True)
    assert sum(row["assembly_attempts"] for obs in observed for row in obs["rows"]) == 6
    assert arm["wall_ns"] > sum(obs["wall_ns"] for obs in observed)
    for index, entry in enumerate(arm["entries"]):
        assert (
            tmp_path / f"observed/proposal/{index:03d}-1-step.json"
        ).read_bytes() == (
            tmp_path / f"observed/secant/{index:03d}-1-step.json"
        ).read_bytes()
        if "initial_residual_observation" in entry:
            obs = entry["initial_residual_observation"]
            assert obs["parent_hash"] == entry["parent_hash"]
            assert (
                obs["rows"][0]["relative_residual"]
                == obs["rows"][1]["relative_residual"]
            )
    assert all(
        "initial_residual_observation" not in entry
        for name in ("reference", "secant")
        for entry in report["arms"][name]["entries"]
    )


@pytest.mark.parametrize("mode", ["raised", "partial"])
def test_failed_observation_stops_path_and_has_no_speed_credit(
    tmp_path, monkeypatch, mode
):
    from structural_analysis.benchmark import rc_control_initial_residual as observer
    from structural_analysis.benchmark.rc_control_runtime_selection import (
        _runtime_score,
    )

    def fail(*args, **kwargs):
        if mode == "partial":
            return {"complete": False, "unknown_work": True}
        raise RuntimeError("observation failed")

    monkeypatch.setattr(observer, "observe_rc_control_initial_residuals", fail)
    report = runtime_observation(tmp_path / "failed")
    arm = report["arms"]["proposal"]
    assert arm["status"] == "incomplete"
    assert arm["failure"]["phase"] == "initial_residual_observation"
    assert arm["entries"][-1]["invocations"] == []
    assert arm["entries"][-1]["initial_residual_observation"]["unknown_work"]
    assert not report["comparisons"]["proposal"]["full_history_pass"]
    assert _runtime_score(report, [])["proposal_over_secant_path_wall_ratio"] is None


@pytest.mark.parametrize("enabled", [None, 1, "true"])
def test_observation_flag_is_strict_before_output(tmp_path, enabled):
    with pytest.raises(ValueError, match="initial residual observation"):
        runtime_observation(tmp_path / "invalid", enabled)
    assert not (tmp_path / "invalid").exists()


def test_observation_cost_is_separate_and_unknown_cost_is_rejected(monkeypatch):
    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("diagnose_expanded_rc_runtime_costs")
    entry = {
        "invocations": [],
        "recovery_wall_ns": 0,
        "proposal_wall_ns": 3,
        "initial_residual_observation": {"complete": True},
        "initial_residual_observation_wall_ns": 7,
    }
    arm = {"wall_ns": 20, "preload_invocations": [], "entries": [entry]}
    costs = module.decompose(arm, 0)
    assert costs["initial_residual_observation"] == 7
    assert costs["remaining_unattributed"] == 10
    entry["initial_residual_observation"]["complete"] = False
    with pytest.raises(ValueError, match="unknown initial residual"):
        module.decompose(arm, 0)
