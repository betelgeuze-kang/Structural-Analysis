"""Observe step work without turning different trajectories into causal labels.

These summaries never fit a policy or execute a solver. A matching parent hash
alone does not mean secant used the same accepted coordinate prefix. Even both
matching identities remain local consistency evidence, not source authentication
or permission to train on a validation case.
"""

from __future__ import annotations

import hashlib
import json
import math
import re


_ARMS = ("secant", "proposal")
_WORK = ("core_calls", "newton_iterations", "linear_solves")
_PREFIX = (
    "problem_contract_hash",
    "control_global_dof",
    "control_free_index",
    "target_m",
    "accepted_targets_m",
    "accepted_augmented_coordinates_m",
)


def _hash(value):
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _natural(value):
    if type(value) is not int or value < 0:
        raise ValueError("known nonnegative integer work required")
    return value


def _identity(value):
    if type(value) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("original SHA-256 identity required")
    return value


def _finite(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("finite original coordinate required")
    return value


def _counts(entry):
    invocations = entry["invocations"]
    if type(invocations) is not list or not invocations:
        raise ValueError("original numerical invocations required")
    totals = dict.fromkeys(_WORK, 0)
    for invocation in invocations:
        if invocation["unknown_work"] is not False:
            raise ValueError("unknown numerical work cannot supply a work difference")
        for key in _WORK:
            totals[key] += _natural(invocation["work"][key])
        if not invocation["work"]["core_calls"]:
            raise ValueError("recorded invocation must include a core call")
    return totals


def _prefix(context, entry, path, targets, index):
    prefix = {key: context[key] for key in _PREFIX}
    accepted = prefix["accepted_targets_m"]
    coordinates = prefix["accepted_augmented_coordinates_m"]
    if (
        prefix["problem_contract_hash"] != path["source_problem_hash"]
        or prefix["target_m"] != targets[index]
        or entry["target_index"] != index
        or type(entry["target_index"]) is not int
        or entry["target_m"] != targets[index]
        or type(accepted) is not list
        or len(accepted) != index + 1
        or accepted[1:] != targets[:index]
        or type(coordinates) is not list
        or len(coordinates) != len(accepted)
        or not coordinates
        or any(type(row) is not list or len(row) < 2 for row in coordinates)
        or len({len(row) for row in coordinates}) != 1
        or type(prefix["control_global_dof"]) is not int
        or prefix["control_global_dof"] < 0
        or type(prefix["control_free_index"]) is not int
        or not 0 <= prefix["control_free_index"] < len(coordinates[0]) - 1
    ):
        raise ValueError("original ordered context and path must correspond")
    for value in [
        prefix["target_m"],
        *accepted,
        *(v for row in coordinates for v in row),
    ]:
        _finite(value)
    return prefix


def analyze_rc_control_step_work(report, contexts):
    """Compare complete original paths and keep causal-label eligibility false.

    ``contexts`` contains each arm's original ordered context dictionaries.
    Their external file/hash bindings must be checked by the source auditor.
    Failed comparisons and unknown work reject, never become zero-cost samples.
    """
    if report["report_hash"] != _hash(
        {k: v for k, v in report.items() if k != "report_hash"}
    ):
        raise ValueError("original comparison hash differs")
    if (
        report["all_execution_work_reported"] is not True
        or report["reference_repeat_exact"] is not True
        or set(report["arms"]) != {"reference", *_ARMS}
        or set(report["comparisons"]) != set(report["arms"])
        or any(
            c["full_history_pass"] is not True for c in report["comparisons"].values()
        )
        or set(contexts) != set(_ARMS)
    ):
        raise ValueError(
            "complete verified path comparisons and both contexts required"
        )
    paths = {name: report["arms"][name] for name in _ARMS}
    targets = report["request"]["targets_m"]
    if type(targets) is not list or not 1 <= len(targets) <= 65536:
        raise ValueError("bounded complete original targets required")
    for target in targets:
        _finite(target)
    for path in [*report["arms"].values(), report["fresh_reference"]]:
        _identity(path["source_problem_hash"])
        if (
            path["status"] != "complete"
            or path["requested_targets_m"] != targets
            or path["accepted_target_count"] != len(targets)
            or type(path["accepted_target_count"]) is not int
            or len(path["entries"]) != len(targets)
        ):
            raise ValueError("every declared original path must be complete")
        for entry in path["entries"]:
            _identity(entry["parent_hash"])
            _counts(entry)
    if any(len(contexts[name]) != len(targets) for name in _ARMS):
        raise ValueError("one original context per requested target required")
    rows = []
    for index, target in enumerate(targets):
        entries = {name: paths[name]["entries"][index] for name in _ARMS}
        prefixes = {
            name: _prefix(
                contexts[name][index], entries[name], paths[name], targets, index
            )
            for name in _ARMS
        }
        prefix_hashes = {name: _hash(prefixes[name]) for name in _ARMS}
        if any(
            p["control_global_dof"] != report["request"]["control_global_dof"]
            for p in prefixes.values()
        ):
            raise ValueError("original control DOF differs")
        work = {name: _counts(entries[name]) for name in _ARMS}
        differences = {k: work["proposal"][k] - work["secant"][k] for k in _WORK}
        earlier = prefixes["secant"]["accepted_targets_m"]
        direction = (target > earlier[-1]) - (target < earlier[-1])
        previous_direction = (
            0
            if len(earlier) < 2
            else ((earlier[-1] > earlier[-2]) - (earlier[-1] < earlier[-2]))
        )
        rows.append(
            {
                "target_index": index,
                "target_m": target,
                "history_position": "first_target"
                if index == 0
                else "reversal"
                if direction * previous_direction < 0
                else "continuation",
                "proposal_decision": entries["proposal"].get("proposal_decision"),
                "work": work,
                "proposal_minus_secant_work": differences,
                "same_parent_hash": entries["secant"]["parent_hash"]
                == entries["proposal"]["parent_hash"],
                "same_accepted_prefix": prefix_hashes["secant"]
                == prefix_hashes["proposal"],
                "prefix_hashes": prefix_hashes,
                "accepted_coordinates_equal_commanded_targets": {
                    name: all(
                        q[prefix["control_free_index"]] == t
                        for q, t in zip(
                            prefix["accepted_augmented_coordinates_m"],
                            prefix["accepted_targets_m"],
                            strict=True,
                        )
                    )
                    for name, prefix in prefixes.items()
                },
                "causal_training_label_admitted": False,
            }
        )
    groups = {}
    for name in ("all", "first_target", "reversal", "continuation"):
        selected = (
            rows
            if name == "all"
            else [r for r in rows if r["history_position"] == name]
        )
        groups[name] = {
            "count": len(selected),
            "fewer_newton_iterations": sum(
                r["proposal_minus_secant_work"]["newton_iterations"] < 0
                for r in selected
            ),
            "equal_newton_iterations": sum(
                r["proposal_minus_secant_work"]["newton_iterations"] == 0
                for r in selected
            ),
            "more_newton_iterations": sum(
                r["proposal_minus_secant_work"]["newton_iterations"] > 0
                for r in selected
            ),
            "work": {
                arm: {key: sum(r["work"][arm][key] for r in selected) for key in _WORK}
                for arm in _ARMS
            },
            "same_parent_and_prefix_count": sum(
                r["same_parent_hash"] and r["same_accepted_prefix"] for r in selected
            ),
        }
    result = {
        "schema_version": "rc-control-step-work-observation.v1",
        "source_comparison_hash": report["report_hash"],
        "groups": groups,
        "rows": rows,
        "scope": "observed separate complete trajectories, not same-parent counterfactual execution",
        "source_authentication_performed": False,
        "causal_training_labels_admitted": False,
        "posthoc_step_selection_is_full_path_savings": False,
        "independent_physical_validation": False,
    }
    return result | {"report_hash": _hash(result)}
