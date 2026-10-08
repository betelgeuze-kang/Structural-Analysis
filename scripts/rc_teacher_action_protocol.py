"""Pure declarations and local TRAIN annotations; no execution or learning authority."""

import hashlib
import json
import math

PROTOCOL_SCHEMA = "rc-teacher-action-protocol.v1"
ANNOTATION_SCHEMA = "rc-teacher-action-annotations.v1"
REPETITIONS = 3
ENCLOSING_ARM_CLOCK_SCOPE = (
    "whole_path_including_proposal_numerical_attempts_recovery_and_step_io"
    "_excluding_final_path_write"
)
DECISIONS = (
    "proposed",
    "abstained_to_secant",
    "abstained_to_reference",
    "invalid_proposal_to_reference",
    "guard_failed",
    "proposed_after_reference_failure",
    "recovery_declined",
)
_IDENTITY = {
    "teacher_fit_index",
    "policy_hash",
    "source_sample_hash",
    "parent_hash",
    "case_id",
    "target_index",
    "exclusion_provenance",
}
_WORK = {"core_calls", "newton_iterations", "linear_solves"}
_OBSERVATION = _IDENTITY | {
    "repetition",
    "report_hash",
    "decision",
    "comparison_pass",
    "work_known",
    "work",
    "clock_scope",
    "proposal_wall_ns",
    "secant_wall_ns",
    "proposal_arm_rejected_trials",
    "learned_proposal_rejected_trials",
}
_CLAIMS = {
    "executable": False,
    "old_labels_replaced": False,
    "training_performed": False,
    "producer_attestation": False,
    "hardware_attestation": False,
    "connected_exclusions_verified": False,
    "whole_assembly_material_work_established": False,
    "final_path_write_cost_established": False,
    "whole_job_cost_established": False,
    "total_ai_net_benefit_established": False,
    "production_gain": False,
    "independent_physical_qualification": False,
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**63 - 1


def _digest(value, *, prefix=True, nullable=False):
    if value is None:
        return nullable
    if type(value) is not str:
        return False
    if prefix:
        if not value.startswith("sha256:"):
            return False
        value = value[7:]
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _plain(value):
    """Detach exact JSON types and reject nonfinite declaration/provenance values."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        _require(math.isfinite(value), "nonfinite JSON declaration")
        return value
    if type(value) is list:
        return [_plain(v) for v in value]
    if type(value) is dict:
        _require(all(type(k) is str for k in value), "JSON keys must be strings")
        return {k: _plain(v) for k, v in value.items()}
    raise ValueError("plain JSON types required")


def _object(value, name):
    _require(type(value) is dict and bool(value), name + " must be a nonempty object")
    return _plain(value)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


def _identity(row):
    _require(type(row) is dict and _IDENTITY <= row.keys(), "identity fields required")
    result = {key: row[key] for key in _IDENTITY}
    for key in ("teacher_fit_index", "target_index"):
        _require(_integer(result[key]), "exact nonnegative " + key + " required")
    _require(
        type(result["case_id"]) is str and bool(result["case_id"].strip()),
        "nonempty case_id required",
    )
    for key in ("policy_hash", "source_sample_hash", "parent_hash"):
        _require(_digest(result[key], nullable=True), "invalid " + key)
    result["exclusion_provenance"] = _object(
        result["exclusion_provenance"], "exclusion_provenance"
    )
    return _plain(result)


def _key(row):
    return row["teacher_fit_index"], row["case_id"], row["target_index"]


def prepare_teacher_action_protocol(
    *,
    source_head,
    source_plan_sha256,
    recipe,
    teacher_state_roster,
    connected_train_exclusions,
    resource_budgets,
    timing_scope,
):
    """Freeze a non-executable declaration without inspecting outcome or availability."""
    _require(
        type(source_head) is str
        and len(source_head) == 40
        and all(c in "0123456789abcdef" for c in source_head),
        "exact source HEAD required",
    )
    _require(
        _digest(source_plan_sha256, prefix=False), "raw source plan SHA256 required"
    )
    _require(
        type(teacher_state_roster) is list and bool(teacher_state_roster),
        "nonempty complete declared roster required",
    )
    exclusions = _object(connected_train_exclusions, "connected_train_exclusions")
    groups = exclusions.get("groups")
    _require(type(groups) is list and bool(groups), "declared TRAIN groups required")
    train_cases = set()
    for group in groups:
        _require(type(group) is list and bool(group), "nonempty TRAIN group required")
        for case_id in group:
            _require(
                type(case_id) is str and bool(case_id.strip()),
                "nonempty declared TRAIN case_id required",
            )
            _require(case_id not in train_cases, "duplicate declared TRAIN case")
            train_cases.add(case_id)
    roster, seen, teachers = [], set(), {}
    for row in teacher_state_roster:
        _require(
            type(row) is dict and row.keys() == _IDENTITY | {"expected_report_hashes"},
            "exact declared roster fields required",
        )
        identity = _identity(row)
        _require(
            identity["case_id"] in train_cases, "case outside declared TRAIN groups"
        )
        key = _key(identity)
        _require(key not in seen, "duplicate declared teacher/state")
        seen.add(key)
        reports = row["expected_report_hashes"]
        _require(
            type(reports) is list
            and len(reports) == REPETITIONS
            and all(_digest(v, nullable=True) for v in reports),
            "three expected report hash slots required",
        )
        teacher = _canonical(
            [identity["policy_hash"], identity["exclusion_provenance"]]
        )
        index = identity["teacher_fit_index"]
        _require(
            index not in teachers or teachers[index] == teacher,
            "teacher policy or exclusion provenance changed within roster",
        )
        teachers[index] = teacher
        roster.append({**identity, "expected_report_hashes": list(reports)})
    budgets = _object(resource_budgets, "resource_budgets")
    _require(
        all(_integer(v, minimum=1) for v in budgets.values()),
        "positive exact-int resource ceilings required",
    )
    protocol = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "prepared-not-executable",
        "source_head": source_head,
        "source_plan_sha256": source_plan_sha256,
        "recipe": _object(recipe, "recipe"),
        "teacher_state_roster": roster,
        "connected_train_exclusions": exclusions,
        "resource_budgets": budgets,
        "timing_scope": _object(timing_scope, "timing_scope"),
        "repetitions": REPETITIONS,
        "declared_state_count": len(roster),
        "declared_repeat_denominator": len(roster) * REPETITIONS,
        "response_criterion_changed": False,
        "observation_scope": "local_authored_train_annotations_only",
        "conditional_value_scope": "supplied_elapsed_arm_clock_observation_only",
        "known_work_scope": "supplied_native_three_counter_completeness_only",
        "enclosing_arm_clock_scope": ENCLOSING_ARM_CLOCK_SCOPE,
        "completion_binding_requirement": (
            "None expected hash requires separate original completion mapping; "
            "immutable preparation is never overwritten"
        ),
        "full_path_requirements": {
            "chronological_own_arm_predecessors": True,
            "complete_offline_and_online_cost": True,
            "final_path_write_and_whole_job_cost": True,
            "same_frozen_model_request_arithmetic_and_response_criterion": True,
            "authoritative_independent_physical_verification_for_production": True,
        },
        "claims": dict(_CLAIMS),
    }
    return {**protocol, "protocol_hash": _hash(protocol)}


def _checked_protocol(protocol):
    _require(type(protocol) is dict, "protocol object required")
    keys = (
        "source_head",
        "source_plan_sha256",
        "recipe",
        "teacher_state_roster",
        "connected_train_exclusions",
        "resource_budgets",
        "timing_scope",
    )
    _require(all(k in protocol for k in keys), "protocol declaration incomplete")
    expected = prepare_teacher_action_protocol(**{k: protocol[k] for k in keys})
    _require(_canonical(_plain(protocol)) == _canonical(expected), "protocol changed")
    return expected


def _indexed(rows, declared, *, completion=False):
    _require(type(rows) is list, "observation/completion list required")
    indexed = {}
    for row in rows:
        _require(type(row) is dict, "observation/completion object required")
        allowed = (
            _IDENTITY | {"repetition", "report_hash", "source_binding_verified"}
            if completion
            else _OBSERVATION
        )
        _require(row.keys() <= allowed, "unexpected observation/completion field")
        identity = _identity(row)
        key = _key(identity)
        _require(key in declared, "foreign undeclared teacher/state")
        _require(
            _canonical(identity) == _canonical(_identity(declared[key])),
            "policy/sample/parent/case/target/exclusion identity mismatch",
        )
        repetition = row.get("repetition")
        _require(
            _integer(repetition) and repetition < REPETITIONS,
            "exact repetition index0..2 required",
        )
        slot = (*key, repetition)
        _require(slot not in indexed, "duplicate observation/completion repetition")
        if completion:
            _require(
                _digest(row.get("report_hash")), "valid completion report hash required"
            )
        indexed[slot] = row
    return indexed


def _bound(row, declared, completion, repetition):
    if any(
        declared[k] is None
        for k in ("policy_hash", "source_sample_hash", "parent_hash")
    ):
        return "binding_unavailable"
    actual = row.get("report_hash")
    if not _digest(actual):
        return "report_hash_unavailable_or_invalid"
    if completion is not None:
        _require(actual == completion["report_hash"], "completion report hash mismatch")
    expected = declared["expected_report_hashes"][repetition]
    if expected is not None:
        _require(actual == expected, "original expected report hash mismatch")
        return None
    if completion is None:
        return "completion_binding_missing"
    if completion.get("source_binding_verified") is not True:
        return "completion_binding_unverified"
    return None


def _repeat(row, declared, completion, repetition):
    result = {
        "repetition": repetition,
        "report_hash": None,
        "decision": None,
        "ordinary_proposal_observed": None,
        "comparison_pass": None,
        "native_work_known": False,
        "work": dict.fromkeys(sorted(_WORK)),
        "proposal_wall_ns": None,
        "secant_wall_ns": None,
        "elapsed_arm_ratio": None,
        "conditional_benefit": None,
        "proposal_arm_rejected_trials": None,
        "learned_proposal_rejected_trials": None,
        "reasons": [],
        "rejection_count_reasons": [],
    }
    if row is None:
        result["reasons"] = ["missing_repetition"]
        return result
    bound = _bound(row, declared, completion, repetition)
    if bound:
        result["reasons"].append(bound)
    else:
        result["report_hash"] = row["report_hash"]
        decision = row.get("decision")
        if type(decision) is str and decision in DECISIONS:
            result["decision"] = decision
            result["ordinary_proposal_observed"] = decision == "proposed"
            if decision != "proposed":
                result["reasons"].append("not_ordinary_proposed:" + decision)
        else:
            result["reasons"].append("decision_unknown_or_invalid")
    passed = row.get("comparison_pass")
    if type(passed) is bool:
        result["comparison_pass"] = passed
    if passed is not True:
        result["reasons"].append("comparison_failed_or_unknown")
    work = row.get("work")
    for key in sorted(_WORK):
        if type(work) is dict and _integer(work.get(key)):
            result["work"][key] = work[key]
        else:
            result["reasons"].append("native_" + key + "_unknown_or_invalid")
    known = (
        row.get("work_known") is True
        and type(work) is dict
        and work.keys() == _WORK
        and all(_integer(v) for v in work.values())
    )
    result["native_work_known"] = known
    if not known:
        result["reasons"].append("native_work_unknown_or_invalid")
    if row.get("clock_scope") != ENCLOSING_ARM_CLOCK_SCOPE:
        result["reasons"].append("enclosing_arm_clock_scope_missing_or_invalid")
    for key in ("proposal_wall_ns", "secant_wall_ns"):
        value = row.get(key)
        if _integer(value, minimum=1):
            result[key] = value
        else:
            result["reasons"].append(key + "_unknown_or_invalid")
    for key in ("proposal_arm_rejected_trials", "learned_proposal_rejected_trials"):
        if _integer(row.get(key)):
            result[key] = row[key]
        else:
            result["rejection_count_reasons"].append(key + "_unknown_or_invalid")
    arm_rejections = result["proposal_arm_rejected_trials"]
    learned_rejections = result["learned_proposal_rejected_trials"]
    _require(
        arm_rejections is None
        or learned_rejections is None
        or learned_rejections <= arm_rejections,
        "learned rejected trials exceed proposal-arm rejected trials",
    )
    if not result["reasons"]:
        ratio = result["proposal_wall_ns"] / result["secant_wall_ns"]
        result["elapsed_arm_ratio"] = ratio
        result["conditional_benefit"] = 1.0 - ratio
    return result


def annotate_teacher_actions(protocol, observations, *, completion_bindings=None):
    """Separate observed ordinary-action availability from supplied conditional cost."""
    checked = _checked_protocol(protocol)
    roster = checked["teacher_state_roster"]
    declared = {_key(row): row for row in roster}
    observed = _indexed(observations, declared)
    completions = _indexed(
        [] if completion_bindings is None else completion_bindings,
        declared,
        completion=True,
    )
    _require(completions.keys() <= observed.keys(), "completion without observation")
    rows = []
    for declared_row in roster:
        key = _key(declared_row)
        repeats = [
            _repeat(
                observed.get((*key, repetition)),
                declared_row,
                completions.get((*key, repetition)),
                repetition,
            )
            for repetition in range(REPETITIONS)
        ]
        available = sum(r["ordinary_proposal_observed"] is True for r in repeats)
        unavailable = sum(r["ordinary_proposal_observed"] is False for r in repeats)
        unknown = REPETITIONS - available - unavailable
        benefits = [r["conditional_benefit"] for r in repeats]
        value = min(benefits) if all(v is not None for v in benefits) else None
        rows.append(
            {
                **declared_row,
                "repetitions": repeats,
                "availability": {
                    "declared_repeats": REPETITIONS,
                    "ordinary_proposed": available,
                    "known_not_ordinary_proposed": unavailable,
                    "unknown": unknown,
                },
                "conditional_worst_benefit": value,
                "conditional_value_reasons": [
                    {"repetition": r["repetition"], "reasons": r["reasons"]}
                    for r in repeats
                    if r["reasons"]
                ],
                "old_label": "untouched; this annotation is not a replacement label",
            }
        )
    decisions = {decision: 0 for decision in DECISIONS}
    for row in rows:
        for repeat in row["repetitions"]:
            if repeat["decision"] in decisions:
                decisions[repeat["decision"]] += 1
    result = {
        "schema_version": ANNOTATION_SCHEMA,
        "status": "local-train-annotations-only",
        "protocol_hash": checked["protocol_hash"],
        "declared_state_count": len(roster),
        "declared_repeat_denominator": len(roster) * REPETITIONS,
        "supplied_observation_count": len(observed),
        "decision_counts": decisions,
        "unknown_action_repeats": sum(row["availability"]["unknown"] for row in rows),
        "states_with_conditional_value": sum(
            row["conditional_worst_benefit"] is not None for row in rows
        ),
        "rows": rows,
        "claims": dict(_CLAIMS),
        "conditional_value_scope": checked["conditional_value_scope"],
        "known_work_scope": checked["known_work_scope"],
        "completion_binding_scope": "supplied source identity consistency; not attestation",
    }
    return {**result, "annotation_hash": _hash(result)}
