"""Post-run target-aligned work diagnostics, not same-parent causal estimates."""

import math
from typing import Any

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import rc_control_design as study

_COUNTERS = ("core_calls", "newton_iterations", "linear_solves")
_DECISIONS = ("proposed", "abstained_to_secant", "abstained_to_reference")


def _natural(value):
    return type(value) is int and value >= 0


def _work(entry):
    invocations = entry["invocations"]
    if type(invocations) is not list or not invocations:
        raise ValueError("recorded target invocations required")
    result = dict.fromkeys(_COUNTERS, 0)
    for invocation in invocations:
        if invocation.get("unknown_work") is not False:
            raise ValueError("unknown target work cannot be scored")
        work = invocation["work"]
        if any(not _natural(work.get(k)) for k in _COUNTERS):
            raise ValueError("known integer target counters required")
        for key in _COUNTERS:
            result[key] += work[key]
    return result


def diagnose_control_step_work(raw, decisions, *, expected_report_hash):
    """Compare completed whole-path strategies at matching prescribed target indices.

    Decisions must be independently bound to the original experiment by the caller.
    Counter deltas include recovery/fallback invocations and never imply a causal
    same-parent intervention, independent validation, or prospective policy value.
    """
    try:
        return _diagnose(raw, decisions, expected_report_hash)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("malformed target work diagnostic input") from error


def _diagnose(raw, decisions, expected_hash):
    report = strict_json_object_bytes(raw, maximum_bytes=16 * 1024**2)
    digest = study._sha(
        study._bytes({k: v for k, v in report.items() if k != "report_hash"})
    )
    if (
        digest != report["report_hash"]
        or digest != expected_hash
        or report["schema_version"] != "experimental-rc-control-seed-comparison.v1"
        or report["all_execution_work_reported"] is not True
        or report["reference_repeat_exact"] is not True
    ):
        raise ValueError("pinned complete comparison required")
    targets = report["request"]["targets_m"]
    if (
        type(targets) is not list
        or not 1 <= len(targets) <= 4096
        or any(type(t) not in (int, float) or not math.isfinite(t) for t in targets)
        or type(decisions) is not list
        or len(decisions) != len(targets)
    ):
        raise ValueError("bounded aligned targets and decisions required")
    arms = {}
    for name in ("secant", "proposal"):
        arm = report["arms"][name]
        if (
            arm["status"] != "complete"
            or type(arm["accepted_target_count"]) is not int
            or arm["accepted_target_count"] != len(targets)
            or arm["requested_targets_m"] != targets
            or len(arm["entries"]) != len(targets)
            or report["comparisons"][name]["full_history_pass"] is not True
        ):
            raise ValueError("complete verified strategy paths required")
        arms[name] = arm["entries"]
    rows = []
    groups: dict[str, Any] = {}
    previous, direction, envelope = 0.0, None, 0.0
    for index, target in enumerate(targets):
        step = target - previous
        if step == 0:
            raise ValueError("distinct consecutive targets required")
        next_direction = 1 if step > 0 else -1
        phase = (
            "initial"
            if direction is None
            else "reversal"
            if direction != next_direction
            else "new_absolute_envelope"
            if abs(target) > envelope
            else "within_absolute_envelope"
        )
        decision = decisions[index]
        if (
            decision["target_m"] != target
            or type(decision["accepted_prefix_count"]) is not int
            or decision["accepted_prefix_count"] != index + 1
            or decision["decision"] not in _DECISIONS
        ):
            raise ValueError("decision target/order mismatch")
        counters = {}
        for name, entries in arms.items():
            entry = entries[index]
            if (
                type(entry["target_index"]) is not int
                or entry["target_index"] != index
                or entry["target_m"] != target
            ):
                raise ValueError("strategy target alignment mismatch")
            counters[name] = _work(entry)
        delta = {k: counters["proposal"][k] - counters["secant"][k] for k in _COUNTERS}
        row = {
            "target_index": index,
            "target_m": target,
            "phase": phase,
            "decision": decision["decision"],
            "work": counters,
            "proposal_minus_secant": delta,
            "same_parent_hash": arms["proposal"][index]["parent_hash"]
            == arms["secant"][index]["parent_hash"],
        }
        rows.append(row)
        key = decision["decision"] + ":" + phase
        group = groups.setdefault(
            key,
            {
                "targets": 0,
                "fewer_newton_targets": 0,
                "equal_newton_targets": 0,
                "more_newton_targets": 0,
                "secant": dict.fromkeys(_COUNTERS, 0),
                "proposal": dict.fromkeys(_COUNTERS, 0),
                "proposal_minus_secant": dict.fromkeys(_COUNTERS, 0),
            },
        )
        group["targets"] += 1
        group[
            "fewer_newton_targets"
            if delta["newton_iterations"] < 0
            else "more_newton_targets"
            if delta["newton_iterations"] > 0
            else "equal_newton_targets"
        ] += 1
        for counter in _COUNTERS:
            for name in ("secant", "proposal"):
                group[name][counter] += counters[name][counter]
            group["proposal_minus_secant"][counter] += delta[counter]
        previous, direction, envelope = (
            target,
            next_direction,
            max(envelope, abs(target)),
        )
    result = {
        "schema_version": "experimental-rc-control-target-work-diagnostic.v1",
        "source_report_hash": digest,
        "decision_digest": study._sha(study._bytes(decisions)),
        "rows": rows,
        "groups": groups,
        "scope": "posthoc_same_target_index_whole_path_strategy_work_including_fallback",
        "same_parent_causal_comparison": False,
        "prospective_policy_validated": False,
        "independent_physical_validation": False,
        "net_savings_proved": False,
    }
    result["report_hash"] = study._sha(study._bytes(result))
    return result
