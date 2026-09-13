"""Controlled diagnostic inputs; these do not represent physical solver runs."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark.rc_control_step_work import (
    _hash,
    analyze_rc_control_step_work,
)


def inputs():
    targets = [0.1, 0.2, -0.1]
    counts = {"secant": [2, 3, 4], "proposal": [2, 5, 3], "reference": [4, 4, 4]}
    paths, contexts = {}, {}
    for arm, work in counts.items():
        paths[arm] = {
            "status": "complete",
            "accepted_target_count": 3,
            "requested_targets_m": targets[:],
            "source_problem_hash": "sha256:" + "a" * 64,
            "entries": [
                {
                    "target_index": i,
                    "target_m": target,
                    "parent_hash": "sha256:" + str(i) * 64,
                    "invocations": [
                        {
                            "unknown_work": False,
                            "work": {
                                "core_calls": 1,
                                "newton_iterations": work[i],
                                "linear_solves": work[i],
                            },
                        }
                    ],
                }
                for i, target in enumerate(targets)
            ],
        }
        if arm != "reference":
            contexts[arm] = [
                {
                    "problem_contract_hash": "sha256:" + "a" * 64,
                    "control_global_dof": 4,
                    "control_free_index": 0,
                    "target_m": target,
                    "accepted_targets_m": [0.0, *targets[:i]],
                    "accepted_augmented_coordinates_m": [
                        [t, 0.0] for t in [0.0, *targets[:i]]
                    ],
                }
                for i, target in enumerate(targets)
            ]
    report = {
        "arms": paths,
        "fresh_reference": deepcopy(paths["reference"]),
        "request": {"targets_m": targets, "control_global_dof": 4},
        "reference_repeat_exact": True,
        "all_execution_work_reported": True,
        "comparisons": {arm: {"full_history_pass": True} for arm in paths},
    }
    return sign(report), contexts


def sign(report):
    report["report_hash"] = _hash(
        {k: v for k, v in report.items() if k != "report_hash"}
    )
    return report


def test_work_difference_and_reversal_keep_full_denominator_and_no_label_credit():
    report, contexts = inputs()
    original = deepcopy((report, contexts))
    result = analyze_rc_control_step_work(report, contexts)
    group = result["groups"]["all"]
    assert group["count"] == 3
    assert group["work"]["secant"]["newton_iterations"] == 9
    assert group["work"]["proposal"]["newton_iterations"] == 10
    assert [
        group[key]
        for key in (
            "fewer_newton_iterations",
            "equal_newton_iterations",
            "more_newton_iterations",
        )
    ] == [1, 1, 1]
    assert result["groups"]["reversal"]["count"] == 1
    assert result["groups"]["continuation"]["count"] == 1
    assert group["same_parent_and_prefix_count"] == 3
    assert not result["causal_training_labels_admitted"]
    assert not result["posthoc_step_selection_is_full_path_savings"]
    assert all(not row["causal_training_label_admitted"] for row in result["rows"])
    assert (report, contexts) == original


def test_same_parent_does_not_erase_different_older_secant_coordinate():
    report, contexts = inputs()
    contexts["proposal"][2]["accepted_augmented_coordinates_m"][0][1] = 1.0
    row = analyze_rc_control_step_work(report, contexts)["rows"][2]
    assert row["same_parent_hash"]
    assert not row["same_accepted_prefix"]


def test_signed_zero_prefixes_are_not_byte_identical():
    report, contexts = inputs()
    contexts["proposal"][1]["accepted_augmented_coordinates_m"][0][1] = -0.0
    assert not analyze_rc_control_step_work(report, contexts)["rows"][1][
        "same_accepted_prefix"
    ]


def test_different_parent_with_same_prefix_is_visible():
    report, contexts = inputs()
    report["arms"]["proposal"]["entries"][1]["parent_hash"] = "sha256:" + "f" * 64
    row = analyze_rc_control_step_work(sign(report), contexts)["rows"][1]
    assert not row["same_parent_hash"]
    assert row["same_accepted_prefix"]


@pytest.mark.parametrize("value", [True, -1, 1.5, None])
def test_invalid_work_does_not_become_zero(value):
    report, contexts = inputs()
    report["arms"]["proposal"]["entries"][0]["invocations"][0]["work"][
        "newton_iterations"
    ] = value
    with pytest.raises(ValueError, match="known nonnegative"):
        analyze_rc_control_step_work(sign(report), contexts)


def test_retry_work_is_included():
    report, contexts = inputs()
    inv = report["arms"]["proposal"]["entries"][0]["invocations"]
    inv.append(
        {
            "unknown_work": False,
            "work": {"core_calls": 1, "newton_iterations": 5, "linear_solves": 4},
        }
    )
    row = analyze_rc_control_step_work(sign(report), contexts)["rows"][0]
    assert row["work"]["proposal"] == {
        "core_calls": 2,
        "newton_iterations": 7,
        "linear_solves": 6,
    }


@pytest.mark.parametrize(
    "kind",
    [
        "unknown",
        "failed_comparison",
        "missing_comparison",
        "incomplete",
        "missing_entry",
        "bad_identity",
    ],
)
def test_unverified_or_incomplete_originals_reject(kind):
    report, contexts = inputs()
    if kind == "unknown":
        report["arms"]["proposal"]["entries"][1]["invocations"][0]["unknown_work"] = (
            True
        )
    elif kind == "failed_comparison":
        report["comparisons"]["proposal"]["full_history_pass"] = False
    elif kind == "missing_comparison":
        del report["comparisons"]["proposal"]
    elif kind == "incomplete":
        report["fresh_reference"]["status"] = "incomplete"
    elif kind == "missing_entry":
        report["arms"]["secant"]["entries"].pop()
    else:
        report["arms"]["secant"]["entries"][0]["parent_hash"] = None
    with pytest.raises(ValueError):
        analyze_rc_control_step_work(sign(report), contexts)


@pytest.mark.parametrize("kind", ["order", "target", "nan", "control_dof"])
def test_context_must_correspond_to_original_path(kind):
    report, contexts = inputs()
    context = contexts["proposal"][2]
    if kind == "order":
        context["accepted_targets_m"][1:] = [0.2, 0.1]
    elif kind == "target":
        context["target_m"] = 0.5
    elif kind == "nan":
        context["accepted_augmented_coordinates_m"][0][1] = float("nan")
    elif kind == "control_dof":
        context["control_global_dof"] = 5
    with pytest.raises(ValueError):
        analyze_rc_control_step_work(report, contexts)


def test_accepted_coordinate_is_not_replaced_with_commanded_target():
    report, contexts = inputs()
    contexts["proposal"][2]["accepted_augmented_coordinates_m"][-1][0] = (
        0.20000000000000004
    )
    row = analyze_rc_control_step_work(report, contexts)["rows"][2]
    assert not row["same_accepted_prefix"]
    assert row["accepted_coordinates_equal_commanded_targets"] == {
        "secant": True,
        "proposal": False,
    }
    assert (
        contexts["proposal"][2]["accepted_augmented_coordinates_m"][-1][0]
        == 0.20000000000000004
    )


def test_changed_comparison_hash_rejects():
    report, contexts = inputs()
    report["arms"]["proposal"]["entries"][0] = {}
    with pytest.raises(ValueError, match="comparison hash"):
        analyze_rc_control_step_work(report, contexts)
