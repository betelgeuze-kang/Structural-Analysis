from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from time import perf_counter_ns
from typing import Any

import numpy as np
import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.benchmark import rc_internal_portal_20mm_comparison as runner


def test_pinned_original_bytes_and_internal_problem_match_preflight() -> None:
    model = runner.FIXTURE_ROOT / "original-model.json"
    request = runner.FIXTURE_ROOT / "original-request.json"
    assert (
        hashlib.sha256(model.read_bytes()).hexdigest() == runner.ORIGINAL_MODEL_SHA256
    )
    assert hashlib.sha256(request.read_bytes()).hexdigest() == (
        runner.ORIGINAL_REQUEST_SHA256
    )
    case = runner.prepare_case()
    assert case.candidate_model_hash == runner.CANDIDATE_MODEL_HASH
    assert case.problem.contract_hash == runner.INTERNAL_PROBLEM_HASH
    assert case.problem.node_coordinates_m == (
        (0.0, 0.0),
        (4.0, 0.0),
        (0.0, 3.0),
        (4.0, 3.0),
    )
    assert case.problem.fixed_global_dofs == (0, 1, 2, 3, 4, 5)
    assert case.problem.reference_external_loads == ((9, 150.0),)
    assert case.problem.constant_external_loads == ((7, -25.0), (10, -25.0))
    assert case.preload_config.terminal_polishing is False


def test_changed_original_bytes_fail_before_internal_compilation(tmp_path) -> None:
    model = tmp_path / "model.json"
    request = tmp_path / "request.json"
    model.write_bytes((runner.FIXTURE_ROOT / "original-model.json").read_bytes())
    request.write_bytes((runner.FIXTURE_ROOT / "original-request.json").read_bytes())
    model.write_bytes(model.read_bytes() + b" ")
    with pytest.raises(ValueError, match="model bytes changed"):
        runner.prepare_case(model_path=model, request_path=request)
    model.write_bytes((runner.FIXTURE_ROOT / "original-model.json").read_bytes())
    request.write_bytes(request.read_bytes() + b" ")
    with pytest.raises(ValueError, match="request bytes changed"):
        runner.prepare_case(model_path=model, request_path=request)


def test_plan_is_20mm_only_and_reverses_all_four_arms() -> None:
    plan = runner.campaign_plan("a" * 40, runner.prepare_case())
    assert plan["planned_comparisons"] == 4
    assert plan["planned_paths"] == 16
    assert plan["targets_m"] == [-0.01, -0.02, 0.01]
    assert plan["mode_orders"] == [["fixed", "adaptive"], ["adaptive", "fixed"]]
    assert plan["arm_orders"][1] == list(reversed(plan["arm_orders"][0]))
    assert plan["learned_policy_present"] is False
    assert plan["learned_benefit_conclusion"] is None
    assert plan["internal_direct_terminal_polishing_supported"] is False
    assert plan["wall_budget_scope"].startswith("soft_deadline")
    assert len(plan["differences_from_original_48_path_plan"]) >= 5
    assert plan["plan_hash"].startswith("sha256:")


def test_real_fresh_preload_and_first_target_preserve_full_artifacts(tmp_path) -> None:
    case = runner.prepare_case()
    arm_root = tmp_path / "reference"
    report = runner._run_arm(
        case,
        arm_root,
        arm="reference",
        mode="fixed",
        deadline_ns=perf_counter_ns() + 60_000_000_000,
        targets_m=(-0.01,),
    )
    assert report["status"] == "complete"
    assert report["unknown_work"] is False
    assert report["preload_reexecuted_from_fresh_genesis"] is True
    assert report["preload"]["checkpoint_hash"] == runner.PREFLIGHT_PRELOAD_HASH
    assert report["preload"]["work"]["linear_solve_count"] == 2
    assert report["preload"]["work"]["assembly_call_count"] == 6
    assert report["accepted_checkpoint_hashes"] == [
        "sha256:c4fcba34c6b3afcbad10a70f127d6124de914db60b79cdc364ee966ee9808b0b"
    ]
    assert report["known_work_lower_bound"]["core_calls"] == 2
    assert report["known_work_lower_bound"]["linear_solve_count"] == 16
    assert report["known_work_lower_bound"]["assembly_call_count"] == 59
    step_artifact = json.loads(
        (arm_root / "target-000-attempt-0-step.json").read_bytes()
    )
    assert step_artifact["committed"] is True
    assert len(step_artifact["trial_solution"]["convergence_history"]) == 14
    assert step_artifact["metrics"]["parent_checkpoint_immutable"] is True
    assert (arm_root / "preload-step.json").is_file()
    assert (arm_root / "path.json").is_file()


@dataclass
class _TrialSolution:
    augmented_coordinates_m: np.ndarray


@dataclass
class _TrialStep:
    committed: bool
    accepted_checkpoint: Any
    metrics: dict[str, Any]
    trial_solution: _TrialSolution


def test_fixed_frozen_parent_stages_never_adopt_intermediate_checkpoint(
    monkeypatch, tmp_path
) -> None:
    case = runner.prepare_case()
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(case.problem)
    parent_bytes = parent.canonical_bytes()
    observed: list[tuple[float, Any]] = []

    def fake_step(_case, _root, _name, supplied_parent, target, _seed, _work):
        observed.append((target, supplied_parent))
        return (
            _TrialStep(
                True,
                object(),
                {"rollback_exact": None},
                _TrialSolution(np.zeros(7)),
            ),
            {"unknown_work": False},
        )

    monkeypatch.setattr(runner, "_invoke_step", fake_step)
    seed, stages, unknown, reason = runner._frozen_parent_seed(
        case,
        tmp_path,
        parent,
        -0.01,
        "fixed",
        runner._empty_work(),
        perf_counter_ns() + 60_000_000_000,
    )
    assert seed == (0.0,) * 7
    assert len(stages) == 16
    assert unknown is False
    assert reason == "target_coordinate_reached"
    assert all(supplied is parent for _target, supplied in observed)
    assert observed[-1][0] == -0.01
    assert parent.canonical_bytes() == parent_bytes


def test_deadline_before_arm_keeps_zero_known_work(tmp_path) -> None:
    report = runner._run_arm(
        runner.prepare_case(),
        tmp_path / "skipped",
        arm="reference",
        mode="fixed",
        deadline_ns=0,
    )
    assert report["status"] == "incomplete"
    assert report["terminal_reason"] == "campaign_wall_budget_exhausted_before_path"
    assert report["unknown_work"] is False
    assert report["preload_reexecuted_from_fresh_genesis"] is False
    assert report["known_work_lower_bound"]["core_calls"] == 0


def test_campaign_roster_retains_incomplete_and_unknown_rows(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(runner, "_git_head", lambda: "a" * 40)
    observed: list[tuple[str, str, str]] = []

    def fake_arm(_case, root, *, arm, mode, deadline_ns):
        observed.append((root.name.split("-")[1], mode, arm))
        status = "incomplete" if len(observed) == 3 else "complete"
        unknown = len(observed) == 7
        return {
            "status": status,
            "unknown_work": unknown,
            "accepted_checkpoint_hashes": ["sha256:" + "b" * 64],
            "path_hash": "sha256:" + "c" * 64,
            "target_history": [],
        }

    monkeypatch.setattr(runner, "_run_arm", fake_arm)
    outcome = runner.run_campaign("a" * 40, tmp_path / "campaign")
    assert len(observed) == 16
    assert len(outcome["rows"]) == 4
    assert outcome["completed_paths"] == 15
    assert outcome["observations_complete"] is False
    assert outcome["exact_source_comparison_eligible"] is False
    assert outcome["qualified_fixed_adaptive_timing_ratio"] is None
    assert outcome["learned_benefit_conclusion"] is None
    assert outcome["rows"][0]["arm_statuses"]["frozen_parent_recovery"] == (
        "incomplete"
    )
    assert outcome["rows"][1]["unknown_work"] is True
    assert outcome["rows"][0]["arm_order"] == list(runner.ARM_ORDERS[0])
    assert outcome["rows"][2]["arm_order"] == list(runner.ARM_ORDERS[1])


def test_changed_source_keeps_complete_observations_but_disallows_comparison(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(runner, "_git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "_pinned_source_unchanged", lambda _plan: False)

    def fake_arm(_case, _root, *, arm, mode, deadline_ns):
        return {
            "status": "complete",
            "unknown_work": False,
            "accepted_checkpoint_hashes": ["sha256:" + "b" * 64],
            "path_hash": "sha256:" + "c" * 64,
            "target_history": [],
        }

    monkeypatch.setattr(runner, "_run_arm", fake_arm)
    outcome = runner.run_campaign("a" * 40, tmp_path / "changed-source")
    assert outcome["completed_paths"] == 16
    assert outcome["observations_complete"] is True
    assert outcome["source_unchanged"] is False
    assert outcome["exact_source_comparison_eligible"] is False
    assert outcome["qualified_fixed_adaptive_timing_ratio"] is None
    assert outcome["learned_benefit_conclusion"] is None


def test_pinned_source_rechecks_both_fixture_hashes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner, "_git_head", lambda: "a" * 40)
    original_model_bytes = (runner.FIXTURE_ROOT / "original-model.json").read_bytes()
    for name in ("original-model.json", "original-request.json"):
        (tmp_path / name).write_bytes((runner.FIXTURE_ROOT / name).read_bytes())
    case = runner.prepare_case()
    plan = runner.campaign_plan("a" * 40, case)
    monkeypatch.setattr(runner, "FIXTURE_ROOT", tmp_path)
    assert runner._pinned_source_unchanged(plan) is True
    model_path = tmp_path / "original-model.json"
    model_path.write_bytes(model_path.read_bytes() + b" ")
    assert runner._pinned_source_unchanged(plan) is False
    model_path.write_bytes(original_model_bytes)
    request_path = tmp_path / "original-request.json"
    request_path.write_bytes(request_path.read_bytes() + b" ")
    assert runner._pinned_source_unchanged(plan) is False


def test_campaign_rejects_stale_source_before_creating_output(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(runner, "_git_head", lambda: "b" * 40)
    root = tmp_path / "not-created"
    with pytest.raises(ValueError, match="current checkout HEAD"):
        runner.run_campaign("a" * 40, root)
    assert not root.exists()
