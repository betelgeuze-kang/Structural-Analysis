"""Prospective alpha opportunity accounting is a work observation only."""

import json

import pytest

from scripts.audit_rc_alpha_opportunity_campaign import (
    _preload_trial_scope,
    _target_trial_scope,
)
from scripts.run_rc_alpha_opportunity_campaign import (
    _account_trial_dispatches,
    prepare_cases,
)
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
)


def test_prospective_cases_are_training_only_and_whole_group_distinct():
    cases = prepare_cases()
    assert [case.case_id for case in cases] == [
        "train-alpha-h",
        "train-alpha-i",
        "train-alpha-j",
    ]
    assert {case.split for case in cases} == {"train"}
    assert len({case.model.canonical_model_checksum for case in cases}) == 3
    assert len({tuple(case.request.targets_m) for case in cases}) == 3
    assert control_training_exclusion_groups(cases)["groups"] == [
        [case.case_id] for case in cases
    ]


def test_failed_trial_dispatch_cost_is_joined_by_solver_order():
    rows = [
        {"trial_count": 2, "observed_failed_trial_count": 1},
        {"trial_count": 1, "observed_failed_trial_count": 0},
    ]
    calls = [
        {"phase": "primary_iteration", "status": "returned", "wall_ns": 7},
        {"phase": "line_search", "status": "returned", "wall_ns": 11},
        {"phase": "line_search", "status": "returned", "wall_ns": 13},
        {"phase": "line_search", "status": "returned", "wall_ns": 17},
    ]
    assert _account_trial_dispatches(rows, calls) == {
        "trial_dispatches": 3,
        "failed_trial_dispatch_wall_ns": 11,
    }


def test_no_accepted_alpha_charges_every_failed_dispatch():
    rows = [{"trial_count": 2, "observed_failed_trial_count": 2}]
    calls = [
        {"phase": "line_search", "status": "returned", "wall_ns": 11},
        {"phase": "line_search", "status": "returned", "wall_ns": 13},
    ]
    assert _account_trial_dispatches(rows, calls)["failed_trial_dispatch_wall_ns"] == 24


@pytest.mark.parametrize(
    "calls",
    [
        [{"phase": "line_search", "status": "returned", "wall_ns": 11}],
        [
            {"phase": "line_search", "status": "returned", "wall_ns": 11},
            {"phase": "line_search", "status": "raised", "wall_ns": 13},
        ],
        [
            {"phase": "line_search", "status": "returned", "wall_ns": True},
            {"phase": "line_search", "status": "returned", "wall_ns": 13},
        ],
    ],
)
def test_missing_failed_or_unmeasured_trial_dispatch_is_ineligible(calls):
    with pytest.raises(ValueError):
        _account_trial_dispatches(
            [{"trial_count": 2, "observed_failed_trial_count": 1}], calls
        )


def _preload_fixture(*, accepted=True):
    attempts = [
        {"alpha": 1.0, "accepted": False, "trial_residual_kn": [11.0]},
        {
            "alpha": 0.5,
            "accepted": accepted,
            "trial_residual_kn": [5.0 if accepted else 12.0],
        },
    ]
    selected = 0.5 if accepted else 0.0
    step = {
        "status": "ready",
        "committed": True,
        "trial_solution": {
            "line_search_history": [
                {
                    "iteration": 0,
                    "starting_free_displacements_m": [0.0],
                    "newton_increment_m": [1.0],
                    "attempt_count": 2,
                    "selected_alpha": selected,
                    "attempts": attempts,
                }
            ],
            "convergence_history": [
                {
                    "iteration": 0,
                    "free_displacements_m": [0.0],
                    "newton_increment_m": [1.0],
                    "line_search_attempt_count": 2,
                    "line_search_alpha": selected,
                    "residual_kn": [10.0],
                }
            ],
        },
    }
    outcome = {
        "status": "returned",
        "unknown_work": False,
        "committed": True,
        "newton_assembly_work": {
            "calls": [
                {"phase": "primary_iteration", "status": "returned", "wall_ns": 7},
                {"phase": "line_search", "status": "returned", "wall_ns": 11},
                {"phase": "line_search", "status": "returned", "wall_ns": 13},
            ]
        },
    }
    return step, outcome


@pytest.mark.parametrize("accepted,failed", [(True, 1), (False, 2)])
def test_preload_trace_counts_only_preload_trials_and_wall(accepted, failed):
    step, outcome = _preload_fixture(accepted=accepted)
    assert _preload_trial_scope(step, outcome) == {
        "line_searches": 1,
        "trials": 2,
        "failed_trials": failed,
        "line_search_assembly_wall_ns": 24,
        "failed_trial_dispatch_wall_ns": 11 if accepted else 24,
    }


def test_preload_trace_rejects_false_acceptance_or_missing_dispatch():
    step, outcome = _preload_fixture()
    step["trial_solution"]["line_search_history"][0]["attempts"][0]["accepted"] = True
    with pytest.raises(ValueError, match="acceptance"):
        _preload_trial_scope(step, outcome)
    step, outcome = _preload_fixture()
    outcome["newton_assembly_work"]["calls"].pop()
    with pytest.raises(ValueError, match="count differ"):
        _preload_trial_scope(step, outcome)


def test_target_wall_excludes_separate_preload_outcome(tmp_path):
    arm = tmp_path / "secant"
    arm.mkdir()
    (arm / "000-1-outcome.json").write_text(
        json.dumps(
            {
                "newton_assembly_work": {
                    "calls": [
                        {"phase": "line_search", "status": "returned", "wall_ns": 17},
                        {
                            "phase": "final_observation",
                            "status": "returned",
                            "wall_ns": 19,
                        },
                    ]
                }
            }
        )
    )
    (arm / "preload-outcome.json").write_text(
        json.dumps(
            {
                "newton_assembly_work": {
                    "calls": [{"phase": "line_search", "wall_ns": 23}]
                }
            }
        )
    )
    counted = {
        "line_searches": 1,
        "trials": 1,
        "failed_trials": 0,
        "failed_trial_dispatch_wall_ns": 0,
    }
    assert _target_trial_scope(tmp_path, counted, 1) == {
        "line_searches": 1,
        "trials": 1,
        "failed_trials": 0,
        "line_search_assembly_wall_ns": 17,
        "failed_trial_dispatch_wall_ns": 0,
    }
    with pytest.raises(ValueError, match="count differ"):
        _target_trial_scope(tmp_path, {**counted, "trials": 2}, 1)
