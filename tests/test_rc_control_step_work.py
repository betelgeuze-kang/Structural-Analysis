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


def parent_inputs():
    import json

    report, contexts = inputs()
    context = contexts["secant"][0]
    report.update(
        schema_version="experimental-rc-control-parent-step-comparison.v1",
        initial_parent_hash="sha256:" + "0" * 64,
        compiled_problem_contract_hash="sha256:" + "a" * 64,
        source_target_index=0,
        source_request=deepcopy(report["request"]),
        accepted_context_artifact={
            "sha256": _hash(context),
            "byte_length": len(
                json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
            ),
        },
    )
    report["request"]["targets_m"] = [0.1]
    for path in [*report["arms"].values(), report["fresh_reference"]]:
        path.update(
            schema_version="experimental-rc-control-parent-step-path.v1",
            initial_parent_hash=report["initial_parent_hash"],
            supplied_prefix_target_count=1,
            accepted_target_count=1,
            requested_targets_m=[0.1],
            entries=path["entries"][:1],
            preload_reexecuted=False,
            wall_ns=100,
        )
    for comparison in report["comparisons"].values():
        comparison.clear()
        comparison["step_response_pass"] = True
    return sign(report), context


def test_parent_step_work_includes_recovery_without_training_admission():
    from structural_analysis.benchmark.rc_control_step_work import (
        analyze_rc_control_parent_step_work,
    )

    report, context = parent_inputs()
    invocations = report["arms"]["proposal"]["entries"][0]["invocations"]
    invocations.insert(0, deepcopy(invocations[0]))
    invocations[0]["status"] = "failed"
    report["arms"]["proposal"]["wall_ns"] = 123
    sign(report)
    original = deepcopy((report, context))
    result = analyze_rc_control_parent_step_work(report, context)
    assert result["proposal_minus_secant_work"] == {
        "core_calls": 1,
        "newton_iterations": 2,
        "linear_solves": 2,
    }
    assert result["proposal_minus_secant_wall_ns"] == 23
    assert result["local_context_binding_checked"]
    assert not result["causal_training_labels_admitted"]
    assert not result["source_authentication_performed"]
    assert not result["complete_path_performance_evidence"]
    assert (report, context) == original


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r, c: r["comparisons"]["proposal"].update(step_response_pass=False),
        lambda r, c: r.update(reference_repeat_exact=False),
        lambda r, c: r["arms"]["proposal"].update(status="incomplete"),
        lambda r, c: r["arms"]["proposal"].update(
            initial_parent_hash="sha256:" + "f" * 64
        ),
        lambda r, c: r["arms"]["proposal"]["entries"][0].update(
            parent_hash="sha256:" + "f" * 64
        ),
        lambda r, c: r["arms"]["proposal"].update(supplied_prefix_target_count=True),
        lambda r, c: r["arms"]["proposal"].update(wall_ns=0),
        lambda r, c: r["arms"]["proposal"].update(wall_ns=True),
        lambda r, c: r["arms"]["proposal"]["entries"][0]["invocations"][0].update(
            unknown_work=True
        ),
        lambda r, c: r["arms"]["proposal"]["entries"][0]["invocations"][0][
            "work"
        ].update(linear_solves=-1),
        lambda r, c: r["accepted_context_artifact"].update(byte_length=True),
        lambda r, c: c["accepted_augmented_coordinates_m"][0].__setitem__(0, 1.0),
        lambda r, c: r.update(source_target_index=True),
        lambda r, c: r["request"].update(control_global_dof=3),
    ],
)
def test_parent_step_rejects_failed_unknown_or_mismatched_sources(mutation):
    from structural_analysis.benchmark.rc_control_step_work import (
        analyze_rc_control_parent_step_work,
    )

    report, context = parent_inputs()
    mutation(report, context)
    sign(report)
    with pytest.raises(ValueError):
        analyze_rc_control_parent_step_work(report, context)


def test_parent_step_rejects_report_tampering():
    from structural_analysis.benchmark.rc_control_step_work import (
        analyze_rc_control_parent_step_work,
    )

    report, context = parent_inputs()
    report["arms"]["proposal"]["wall_ns"] = 1
    with pytest.raises(ValueError, match="hash differs"):
        analyze_rc_control_parent_step_work(report, context)
