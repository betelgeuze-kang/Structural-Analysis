"""Prospective alpha opportunity accounting is a work observation only."""

import pytest

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
