"""Authored object-only contracts; no numerical, fit or campaign invocation."""

import copy
import hashlib
import json

import pytest

from rc_teacher_action_protocol import (
    DECISIONS,
    ENCLOSING_ARM_CLOCK_SCOPE,
    annotate_teacher_actions,
    prepare_teacher_action_protocol,
)


def digest(name):
    return "sha256:" + hashlib.sha256(name.encode()).hexdigest()


def declaration():
    """All hashes identify authored strings, never original numerical artifacts."""
    return {
        "source_head": "f" * 40,
        "source_plan_sha256": "a" * 64,
        "recipe": {"seed_ridge": 1.0, "profile": "authored-contract-fixture"},
        "teacher_state_roster": [
            {
                "teacher_fit_index": 0,
                "policy_hash": digest("authored-teacher"),
                "source_sample_hash": digest("authored-sample"),
                "parent_hash": digest("authored-parent"),
                "case_id": "authored-C",
                "target_index": 2,
                "expected_report_hashes": [digest(f"report{i}") for i in range(3)],
                "exclusion_provenance": {
                    "excluded_case_ids": ["authored-A", "authored-B"],
                    "training_case_ids": ["authored-C", "authored-D"],
                    "source_verified": False,
                },
            }
        ],
        "connected_train_exclusions": {
            "groups": [[f"authored-{name}"] for name in "ABCD"],
            "source_verified": False,
        },
        "resource_budgets": {
            "maximum_wall_seconds": 30,
            "maximum_output_bytes": 1024,
            "maximum_native_calls": 12,
            "maximum_fit_calls": 2,
            "maximum_rss_bytes": 1048576,
        },
        "timing_scope": {"nested_clocks_added": False, "full_cost_required": True},
    }


def observations(protocol):
    roster = protocol["teacher_state_roster"][0]
    identity = {
        key: copy.deepcopy(value)
        for key, value in roster.items()
        if key != "expected_report_hashes"
    }
    return [
        {
            **copy.deepcopy(identity),
            "repetition": i,
            "report_hash": digest(f"report{i}"),
            "decision": "proposed",
            "comparison_pass": True,
            "work_known": True,
            "work": {"core_calls": 1, "newton_iterations": 7, "linear_solves": 7},
            "clock_scope": ENCLOSING_ARM_CLOCK_SCOPE,
            "proposal_wall_ns": 900,
            "secant_wall_ns": 1000,
            "proposal_arm_rejected_trials": 0,
            "learned_proposal_rejected_trials": 0,
        }
        for i in range(3)
    ]


def completions(rows):
    keys = {
        "teacher_fit_index",
        "policy_hash",
        "source_sample_hash",
        "parent_hash",
        "case_id",
        "target_index",
        "exclusion_provenance",
        "repetition",
        "report_hash",
    }
    return [
        {**{k: copy.deepcopy(row[k]) for k in keys}, "source_binding_verified": True}
        for row in rows
    ]


def row_result(protocol, rows, **kwargs):
    return annotate_teacher_actions(protocol, rows, **kwargs)["rows"][0]


def test_preparation_is_detached_non_executable_and_does_not_predict_availability():
    original = declaration()
    saved = copy.deepcopy(original)
    protocol = prepare_teacher_action_protocol(**original)
    assert original == saved
    assert protocol["status"] == "prepared-not-executable"
    assert protocol["repetitions"] == 3
    assert protocol["declared_repeat_denominator"] == 3
    assert protocol["response_criterion_changed"] is False
    assert all(value is False for value in protocol["claims"].values())
    assert "availability" not in protocol
    assert "conditional_worst_benefit" not in protocol
    assert (
        protocol["known_work_scope"]
        == "supplied_native_three_counter_completeness_only"
    )
    original["teacher_state_roster"][0]["exclusion_provenance"]["source_verified"] = (
        True
    )
    assert protocol["teacher_state_roster"] == saved["teacher_state_roster"]
    assert json.loads(json.dumps(protocol, allow_nan=False)) == protocol


def test_three_actual_proposals_preserve_negative_zero_and_worst_elapsed_benefit():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    for row, wall in zip(rows, [500, 1250, 1000]):
        row["proposal_wall_ns"] = wall
    before = copy.deepcopy((protocol, rows))
    result = annotate_teacher_actions(protocol, rows)
    assert result["rows"][0]["conditional_worst_benefit"] == -0.25
    assert result["rows"][0]["availability"] == {
        "declared_repeats": 3,
        "ordinary_proposed": 3,
        "known_not_ordinary_proposed": 0,
        "unknown": 0,
    }
    assert result["rows"][0]["repetitions"][2]["conditional_benefit"] == 0.0
    assert "untouched" in result["rows"][0]["old_label"]
    assert all(v is False for v in result["claims"].values())
    assert (protocol, rows) == before


@pytest.mark.parametrize("decision", DECISIONS)
def test_every_runtime_state_is_explicit_and_recovery_is_not_ordinary_proposal(
    decision,
):
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    for row in rows:
        row["decision"] = decision
    result = annotate_teacher_actions(protocol, rows)
    state = result["rows"][0]
    assert result["decision_counts"][decision] == 3
    assert state["availability"]["unknown"] == 0
    if decision == "proposed":
        assert state["conditional_worst_benefit"] == pytest.approx(0.1)
        assert state["availability"]["ordinary_proposed"] == 3
    else:
        assert state["conditional_worst_benefit"] is None
        assert state["availability"]["known_not_ordinary_proposed"] == 3
        assert state["conditional_value_reasons"][0]["reasons"] == [
            "not_ordinary_proposed:" + decision
        ]


@pytest.mark.parametrize("decision", [None, True, 1, {}, "unknown_future_action"])
def test_unknown_decision_is_neither_proposal_nor_imputed_abstention(decision):
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[1]["decision"] = decision
    result = annotate_teacher_actions(protocol, rows)
    assert result["declared_repeat_denominator"] == 3
    assert result["unknown_action_repeats"] == 1
    assert result["rows"][0]["availability"]["ordinary_proposed"] == 2
    assert result["rows"][0]["conditional_worst_benefit"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("comparison_pass", 1),
        ("comparison_pass", None),
        ("comparison_pass", False),
        ("work_known", 1),
        ("work_known", None),
        ("work_known", False),
        ("work", None),
        ("clock_scope", None),
        ("clock_scope", "nested_inference_clock"),
        ("proposal_wall_ns", True),
        ("proposal_wall_ns", 900.0),
        ("proposal_wall_ns", 0),
        ("proposal_wall_ns", -1),
        ("proposal_wall_ns", None),
        ("proposal_wall_ns", float("nan")),
        ("proposal_wall_ns", float("inf")),
        ("proposal_wall_ns", 2**63),
        ("secant_wall_ns", "1000"),
        ("secant_wall_ns", False),
        ("secant_wall_ns", 0),
    ],
)
def test_wrong_cost_work_or_verdict_types_keep_observed_action_but_unknown_value(
    field, value
):
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[0][field] = value
    state = row_result(protocol, rows)
    assert state["availability"]["ordinary_proposed"] == 3
    assert state["conditional_worst_benefit"] is None
    assert state["repetitions"][0]["reasons"]
    json.dumps(state, allow_nan=False)


def test_partial_native_work_keeps_known_scalars_without_completeness_credit():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[0]["work"]["linear_solves"] = True
    rows[1]["work_known"] = False
    state = row_result(protocol, rows)
    assert state["conditional_worst_benefit"] is None
    assert state["repetitions"][0]["work"] == {
        "core_calls": 1,
        "newton_iterations": 7,
        "linear_solves": None,
    }
    assert state["repetitions"][1]["work"] == rows[1]["work"]
    assert all(r["native_work_known"] is False for r in state["repetitions"][:2])


@pytest.mark.parametrize("value", [False, -1, 1.0, "7", None, 2**63])
def test_exact_nonnegative_native_counters_cannot_be_coerced(value):
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[1]["work"]["newton_iterations"] = value
    state = row_result(protocol, rows)
    assert state["conditional_worst_benefit"] is None
    assert state["repetitions"][1]["work"]["newton_iterations"] is None
    assert state["repetitions"][1]["work"]["core_calls"] == 1


def test_missing_repeat_and_initial_binding_keep_complete_declared_denominator():
    args = declaration()
    initial = copy.deepcopy(args["teacher_state_roster"][0])
    initial.update(
        teacher_fit_index=1,
        target_index=0,
        policy_hash=None,
        source_sample_hash=None,
        parent_hash=None,
        expected_report_hashes=[None] * 3,
    )
    args["teacher_state_roster"].append(initial)
    protocol = prepare_teacher_action_protocol(**args)
    rows = observations(protocol)[:2]
    result = annotate_teacher_actions(protocol, rows)
    assert result["declared_state_count"] == 2
    assert result["declared_repeat_denominator"] == 6
    assert result["supplied_observation_count"] == 2
    assert result["unknown_action_repeats"] == 4
    assert all(state["conditional_worst_benefit"] is None for state in result["rows"])
    assert result["rows"][0]["repetitions"][2]["reasons"] == ["missing_repetition"]
    assert result["rows"][1]["repetitions"][0]["work"] == {
        "core_calls": None,
        "linear_solves": None,
        "newton_iterations": None,
    }


@pytest.mark.parametrize("key", ["policy_hash", "source_sample_hash", "parent_hash"])
def test_pending_identity_is_hold_even_with_report_and_supplied_positive_clocks(key):
    args = declaration()
    args["teacher_state_roster"][0][key] = None
    protocol = prepare_teacher_action_protocol(**args)
    state = row_result(protocol, observations(protocol))
    assert state["availability"]["unknown"] == 3
    assert state["conditional_worst_benefit"] is None
    assert all("binding_unavailable" in r["reasons"] for r in state["repetitions"])


def test_future_report_hashes_bind_completion_without_rewriting_preparation():
    args = declaration()
    args["teacher_state_roster"][0]["expected_report_hashes"] = [None] * 3
    protocol = prepare_teacher_action_protocol(**args)
    saved = copy.deepcopy(protocol)
    rows = observations(protocol)
    mapping = completions(rows)
    assert row_result(protocol, rows)["conditional_worst_benefit"] is None
    result = annotate_teacher_actions(protocol, rows, completion_bindings=mapping)
    assert result["rows"][0]["conditional_worst_benefit"] == pytest.approx(0.1)
    assert result["protocol_hash"] == saved["protocol_hash"]
    assert protocol == saved
    assert result["claims"]["producer_attestation"] is False


@pytest.mark.parametrize("verified", [False, 1, "true", None])
def test_completion_verification_is_exact_bool_and_incomplete_is_unknown(verified):
    args = declaration()
    args["teacher_state_roster"][0]["expected_report_hashes"] = [None] * 3
    protocol = prepare_teacher_action_protocol(**args)
    rows = observations(protocol)
    mapping = completions(rows)
    mapping[1]["source_binding_verified"] = verified
    state = row_result(protocol, rows, completion_bindings=mapping)
    assert state["conditional_worst_benefit"] is None
    assert state["availability"]["unknown"] == 1
    assert "completion_binding_unverified" in state["repetitions"][1]["reasons"]


@pytest.mark.parametrize("future", [False, True])
def test_contradictory_completion_hash_rejected_even_when_expected_hash_matches(future):
    args = declaration()
    if future:
        args["teacher_state_roster"][0]["expected_report_hashes"] = [None] * 3
    protocol = prepare_teacher_action_protocol(**args)
    rows = observations(protocol)
    mapping = completions(rows)
    mapping[0]["report_hash"] = digest("foreign-report")
    with pytest.raises(ValueError, match="completion report hash mismatch"):
        annotate_teacher_actions(protocol, rows, completion_bindings=mapping)


def test_expected_original_hash_mismatch_rejected():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[0]["report_hash"] = digest("foreign-report")
    with pytest.raises(ValueError, match="expected report hash mismatch"):
        annotate_teacher_actions(protocol, rows)


@pytest.mark.parametrize(
    "field,value",
    [
        ("teacher_fit_index", 1),
        ("policy_hash", digest("foreign-policy")),
        ("source_sample_hash", digest("foreign-sample")),
        ("parent_hash", digest("future-parent")),
        ("case_id", "foreign-case"),
        ("target_index", 3),
        ("exclusion_provenance", {"groups": ["foreign"]}),
    ],
)
def test_foreign_or_future_observation_identity_rejected(field, value):
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[1][field] = value
    with pytest.raises(ValueError, match="undeclared|identity mismatch"):
        annotate_teacher_actions(protocol, rows)


def test_duplicate_observations_and_completions_are_not_dropped():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    with pytest.raises(ValueError, match="duplicate"):
        annotate_teacher_actions(protocol, rows + [copy.deepcopy(rows[0])])
    mapping = completions(rows)
    with pytest.raises(ValueError, match="duplicate"):
        annotate_teacher_actions(
            protocol, rows, completion_bindings=mapping + [mapping[0]]
        )


@pytest.mark.parametrize("value", [True, -1, 3, 1.0, "1", None])
def test_repetition_indices_exact_and_bounded(value):
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[0]["repetition"] = value
    with pytest.raises(ValueError, match="repetition index"):
        annotate_teacher_actions(protocol, rows)


def test_arm_rejection_does_not_invent_learned_rejection_or_discard_recovery_cost():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[0].update(
        decision="abstained_to_secant",
        proposal_arm_rejected_trials=1,
        proposal_wall_ns=4000,
        work={"core_calls": 2, "newton_iterations": 20, "linear_solves": 20},
    )
    del rows[0]["learned_proposal_rejected_trials"]
    state = row_result(protocol, rows)
    repeat = state["repetitions"][0]
    assert repeat["proposal_arm_rejected_trials"] == 1
    assert repeat["learned_proposal_rejected_trials"] is None
    assert repeat["work"]["newton_iterations"] == 20
    assert repeat["proposal_wall_ns"] == 4000
    assert state["conditional_worst_benefit"] is None


def test_explicit_inconsistent_rejection_counts_rejected():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    rows[0]["learned_proposal_rejected_trials"] = 1
    with pytest.raises(ValueError, match="exceed"):
        annotate_teacher_actions(protocol, rows)


def test_declaration_rejects_case_outside_train_and_duplicate_train_membership():
    args = declaration()
    args["teacher_state_roster"][0]["case_id"] = "reserved-holdout"
    with pytest.raises(ValueError, match="outside declared TRAIN"):
        prepare_teacher_action_protocol(**args)
    args = declaration()
    args["connected_train_exclusions"]["groups"].append(["authored-C"])
    with pytest.raises(ValueError, match="duplicate declared TRAIN"):
        prepare_teacher_action_protocol(**args)


@pytest.mark.parametrize("field", ["teacher_fit_index", "target_index"])
def test_declaration_does_not_accept_boolean_indices(field):
    args = declaration()
    args["teacher_state_roster"][0][field] = True
    with pytest.raises(ValueError, match="exact nonnegative"):
        prepare_teacher_action_protocol(**args)


def test_duplicate_declaration_and_same_teacher_policy_drift_rejected():
    args = declaration()
    args["teacher_state_roster"].append(copy.deepcopy(args["teacher_state_roster"][0]))
    with pytest.raises(ValueError, match="duplicate declared teacher"):
        prepare_teacher_action_protocol(**args)
    args["teacher_state_roster"][1]["target_index"] = 3
    args["teacher_state_roster"][1]["policy_hash"] = digest("different-teacher")
    with pytest.raises(ValueError, match="teacher policy"):
        prepare_teacher_action_protocol(**args)


@pytest.mark.parametrize("value", [True, 1.0, 0, -1, None, 2**63])
def test_resource_budget_exact_positive_int(value):
    args = declaration()
    args["resource_budgets"]["maximum_native_calls"] = value
    with pytest.raises(ValueError, match="positive exact-int"):
        prepare_teacher_action_protocol(**args)


def test_self_hash_and_fixed_claims_are_not_caller_overrideable():
    protocol = prepare_teacher_action_protocol(**declaration())
    changed = copy.deepcopy(protocol)
    changed["claims"]["production_gain"] = True
    with pytest.raises(ValueError, match="protocol changed"):
        annotate_teacher_actions(changed, observations(protocol))
    changed = copy.deepcopy(protocol)
    changed["recipe"]["seed_ridge"] = 0.001
    with pytest.raises(ValueError, match="protocol changed"):
        annotate_teacher_actions(changed, observations(protocol))


def test_permuted_observations_do_not_change_annotation_or_input_objects():
    protocol = prepare_teacher_action_protocol(**declaration())
    rows = observations(protocol)
    expected = annotate_teacher_actions(protocol, rows)
    assert annotate_teacher_actions(protocol, rows[::-1]) == expected
    assert json.loads(json.dumps(expected, allow_nan=False)) == expected
