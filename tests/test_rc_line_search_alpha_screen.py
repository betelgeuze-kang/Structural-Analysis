from __future__ import annotations

import copy

import pytest

from scripts.screen_rc_line_search_alpha import (
    FEATURE_NAMES,
    TraceError,
    _cross_validate,
    _line_rows,
    _predict_skip,
)


def _step(*, accepted_index: int, trial_residual: float = 0.4):
    alphas = [1.0, 0.5, 0.25][: accepted_index + 1]
    attempts = [
        {
            "alpha": alpha,
            "accepted": index == accepted_index,
            "trial_relative_residual": trial_residual,
        }
        for index, alpha in enumerate(alphas)
    ]
    return {
        "trial_solution": {
            "convergence_history": [
                {
                    "iteration": 0,
                    "free_displacements_m": [0.1, 0.2],
                    "newton_increment_m": [0.01, -0.02],
                    "relative_residual": 0.5,
                    "line_search_attempt_count": len(attempts),
                    "line_search_alpha": alphas[-1],
                }
            ],
            "line_search_history": [
                {
                    "iteration": 0,
                    "starting_free_displacements_m": [0.1, 0.2],
                    "newton_increment_m": [0.01, -0.02],
                    "attempt_count": len(attempts),
                    "selected_alpha": alphas[-1],
                    "attempts": attempts,
                }
            ],
        },
    }


def _rows(step):
    return _line_rows(
        step,
        {"target_m": -0.002, "accepted_targets_m": [0.0, -0.001]},
        case_id="train-a-amp050",
        target_index=1,
        step_path="step.json",
        step_sha256="abc",
        context_path="context.json",
        context_sha256="def",
    )


def test_extracts_only_pretrial_features_and_first_accepted_alpha():
    original = _step(accepted_index=1)
    first = _rows(original)
    changed_trial_result = copy.deepcopy(original)
    changed_trial_result["trial_solution"]["line_search_history"][0]["attempts"][1][
        "trial_relative_residual"
    ] = 0.0001
    second = _rows(changed_trial_result)
    assert len(first) == 1
    assert first[0]["features"] == second[0]["features"]
    assert len(first[0]["features"]) == len(FEATURE_NAMES)
    assert first[0]["first_accepted_index"] == 1
    assert first[0]["observed_failed_trial_count"] == 1


def test_missing_or_nonprefix_trials_do_not_create_labels():
    missing = _step(accepted_index=0)
    missing["trial_solution"]["line_search_history"][0].pop("attempts")
    with pytest.raises(TraceError, match="trial record"):
        _rows(missing)

    nonprefix = _step(accepted_index=1)
    nonprefix["trial_solution"]["line_search_history"][0]["attempts"][0]["alpha"] = 0.25
    with pytest.raises(TraceError, match="alpha prefix"):
        _rows(nonprefix)


def test_no_accepted_alpha_remains_unverified():
    blocked = _step(accepted_index=1)
    trial = blocked["trial_solution"]
    trial["line_search_history"][0]["attempts"][-1]["accepted"] = False
    trial["line_search_history"][0]["selected_alpha"] = 0.0
    trial["convergence_history"][0]["line_search_alpha"] = 0.0
    row = _rows(blocked)[0]
    assert row["first_accepted_index"] is None
    assert row["observed_failed_trial_count"] == 2


def test_held_features_cannot_change_training_normalization():
    train = [
        {
            "features": [float(i), 0.0, 0.0, 0.0, 0.0],
            "first_accepted_index": 1,
            "case_id": "train-a-amp050",
            "target_index": i,
            "newton_iteration_index": 0,
        }
        for i in range(3)
    ]
    held = {"features": [1.0, 0.0, 0.0, 0.0, 0.0]}
    assert _predict_skip(train, held)[0] == 1
    held["features"][0] = 1000.0
    assert _predict_skip(train, held) == (0, "outside_training_range")


def test_group_split_excludes_every_held_case_and_counts_false_skip():
    rows = []
    for letter in "abcde":
        for amplitude in ("050", "100", "150"):
            rows.append(
                {
                    "case_id": f"train-{letter}-amp{amplitude}",
                    "target_index": 0,
                    "newton_iteration_index": 0,
                    "features": [1.0, 0.0, 0.0, 0.0, 0.0],
                    "first_accepted_index": 0 if letter == "e" else 1,
                }
            )
    folds, decision = _cross_validate(rows)
    assert len(folds) == 5
    for index, fold in enumerate(folds):
        assert fold["training_rows"] == 12
        assert fold["held_rows"] == 3
        assert all(
            case.startswith(f"train-{'abcde'[index]}-") for case in fold["held_cases"]
        )
    assert folds[4]["false_skips_unobserved_outcome"] == 3
    assert decision["supports_online_experiment_design"] is False
