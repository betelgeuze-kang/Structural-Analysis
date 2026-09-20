"""Audit nested labels without using outer-group samples in seed fitting."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from dataclasses import replace

from audit_grouped_rc_runtime_campaign import checked, read, require
from audit_rc_expanded_same_parent_probe import (
    cache_accounting,
    require_source_binding,
    require_original_artifact,
    require_work_counters,
)
from run_rc_nested_switch_labels import (
    prepare, LABEL_RULE, retained_seed_cost, campaign_definition, INNER_CAMPAIGN,
    PINS, NEW_INVENTORY,
)
from structural_analysis.benchmark.rc_control_design import _bytes


def label_from_repetitions(repeats):
    require(
        len(repeats) == 3
        and all(type(row["repetition"]) is int for row in repeats)
        and {row["repetition"] for row in repeats} == {0, 1, 2},
        "three unique original repetitions required",
    )
    if any(row["comparison_pass"] is not True for row in repeats):
        return {
            "label": None,
            "status": "unverified",
            "reason": "incomplete_or_failed_comparison",
        }
    require(
        all(
            type(row["path_time_ratio"]) in (int, float)
            and math.isfinite(row["path_time_ratio"])
            and row["path_time_ratio"] > 0
            for row in repeats
        ),
        "positive finite measured ratios required",
    )
    positive = all(
        row["decision"] == "proposed"
        and row["path_time_ratio"] <= LABEL_RULE["maximum_positive_time_ratio"]
        for row in repeats
    )
    return {
        "label": positive,
        "status": "verified",
        "reason": "consistent_one_percent_proposal_benefit"
        if positive
        else "no_consistent_proposal_benefit",
    }


def audit(root):
    plan = read(root / "plan.json")
    outcome = read(root / "outcome.json")
    require(plan.get("campaign_profile") in (None, INNER_CAMPAIGN), "known label campaign required")
    inner_validation = plan.get("campaign_profile") == INNER_CAMPAIGN
    spec = campaign_definition(inner_validation)
    require(plan["source_inventories"] == dict(old=PINS["labels"], new=NEW_INVENTORY,
                                              seeds=spec["seed_pin"]),
            "original campaign inventory binding required")
    require(
        plan["repetitions"] == 3
        and plan["maximum_core_calls"] == spec["maximum_core_calls"]
        and plan["new_fits"] == 0
        and plan["reserved_evaluation"] is False
        and plan["complete_path_claim"] is False,
        "fixed probe scope",
    )
    prepared, roster, objects, costs = prepare(
        *(Path(plan["source_roots"][key]) for key in ("old", "new", "seeds")),
        inner_validation=inner_validation,
    )
    require(
        plan["roster"] == roster and plan["historical_label_costs_separate"] == costs,
        "original complete complementary-group input binding",
    )
    require(
        len(roster) == spec["pairs"] and len(outcome["records"]) == spec["comparisons"],
        "complete declared roster",
    )
    require(
        {(r["pair_index"], r["repetition"]) for r in outcome["records"]}
        == {(p, r) for p in range(spec["pairs"]) for r in range(3)},
        "unique complete reports",
    )
    require(
        plan["cache_before"] == {"hits": 0, "misses": 0, "maxsize": 4, "currsize": 0},
        "cold process cache required",
    )
    require(plan["label_rule"] == LABEL_RULE, "predeclared label rule required")
    require(
        plan["historical_seed_costs_separate"]
        == retained_seed_cost(Path(plan["source_roots"]["seeds"]), inner_validation=inner_validation),
        "original seed fitting costs required",
    )
    cache_accounting(roster, outcome["cache_after"])
    metrics = ("core_calls", "newton_iterations", "linear_solves")
    total = dict.fromkeys(metrics, 0)
    rows = []
    for pair, declaration in enumerate(plan["roster"]):
        case, _, parent, context = objects[pair]
        _, compiled, _, _, _ = prepared[case.case_id]
        request = replace(
            case.request,
            targets_m=(case.request.targets_m[declaration["target_index"]],),
        )
        repeats = []
        for record in (r for r in outcome["records"] if r["pair_index"] == pair):
            repeat = record["repetition"]
            require(
                read(root / f"record-{pair:03d}-{repeat}.json") == record,
                "immutable completion receipt",
            )
            name = f"pair-{pair:03d}-repeat-{repeat}/comparison.json"
            path = root / name
            report = checked(path, "report_hash")
            require_source_binding(
                report,
                case.model.canonical_model_checksum,
                case.request.to_dict(),
                request.to_dict(),
                compiled.problem.contract_hash,
            )
            require_original_artifact(
                path.parent, report["initial_parent_artifact"], "parent.json", parent
            )
            require_original_artifact(
                path.parent,
                report["accepted_context_artifact"],
                "accepted-context.json",
                _bytes(context.to_dict()),
            )
            require(
                report["source_revision"] == plan["source_revision"],
                "execution source revision",
            )
            require(
                report["capture_material_state"] is True
                and report["material_capture_scope"] == "proposal-only",
                "proposal state-capture cost retained",
            )
            require(
                report["report_hash"] == record["report_hash"]
                and report["proposal_identity"] == declaration["policy_hash"],
                "report and policy binding",
            )
            require(
                report["initial_parent_hash"] == declaration["parent_hash"]
                and report["source_target_index"] == declaration["target_index"],
                "source parent and target",
            )
            require(
                not report["original_complete_path_executed"]
                and report["comparison_scope"]
                == "one_target_from_one_supplied_native_parent_and_accepted_prefix",
                "single-target scope required",
            )
            require(
                report["arm_order"] == plan["arm_order_schedule"][repeat],
                "counterbalanced order",
            )
            require(
                report["absolute_tolerance"] == 1e-10
                and report["relative_tolerance"] == 1e-8,
                "original comparison tolerances",
            )
            require(
                set(report["arms"])
                == set(report["comparisons"])
                == {"reference", "secant", "proposal"}
                and report["all_execution_work_reported"] is True,
                "all declared arms and comparisons required",
            )
            arm_work = {}
            complete = True
            for name, arm in {
                **report["arms"],
                "fresh-reference": report["fresh_reference"],
            }.items():
                require(
                    not arm["preload_invocations"] and len(arm["entries"]) == 1,
                    "one step with no repeated preload",
                )
                require(
                    arm["entries"][0]["parent_hash"] == declaration["parent_hash"],
                    "identical native parent",
                )
                arm_work[name] = dict.fromkeys(metrics, 0)
                complete = complete and arm["status"] == "complete"
                for invocation in arm["entries"][0]["invocations"]:
                    require(invocation["unknown_work"] is False, "unknown solver work")
                    require_work_counters(invocation["work"])
                    for metric in metrics:
                        total[metric] += invocation["work"][metric]
                        arm_work[name][metric] += invocation["work"][metric]
            passed = complete and all(
                c["step_response_pass"] is True for c in report["comparisons"].values()
            )
            repeats.append(
                {
                    "repetition": repeat,
                    "comparison_pass": passed,
                    "decision": report["arms"]["proposal"]["entries"][0][
                        "proposal_decision"
                    ],
                    "path_time_ratio": report["arms"]["proposal"]["wall_ns"]
                    / report["arms"]["secant"]["wall_ns"]
                    if passed
                    else None,
                    "work": arm_work,
                    "report_hash": report["report_hash"],
                }
            )
        valid = all(r["comparison_pass"] for r in repeats)
        rows.append(
            {
                **declaration,
                "label_result": label_from_repetitions(repeats),
                "repetitions": repeats,
                "all_comparisons_pass": valid,
                "mean_path_time_ratio": mean(r["path_time_ratio"] for r in repeats)
                if valid
                else None,
            }
        )
    require(
        total["core_calls"] <= plan["maximum_core_calls"], "declared core-call budget"
    )
    return {
        "source_revision": plan["source_revision"],
        "pairs": rows,
        "report_count": spec["comparisons"],
        "retained_report_count": 0,
        "new_report_count": spec["comparisons"],
        "label_counts": {
            name: sum(row["label_result"]["label"] is value for row in rows)
            for name, value in (
                ("positive", True),
                ("negative", False),
                ("unverified", None),
            )
        },
        "label_rule": LABEL_RULE,
        "cache_after": outcome["cache_after"],
        "all_report_work": total,
        "passed_comparisons": sum(
            r["comparison_pass"] for row in rows for r in row["repetitions"]
        ),
        "proposed_count": sum(
            r["decision"] == "proposed" for row in rows for r in row["repetitions"]
        ),
        "faster_pair_means": sum(
            row["mean_path_time_ratio"] is not None and row["mean_path_time_ratio"] < 1
            for row in rows
        ),
        "current_invocation_wall_ns": outcome["wall_ns_before_outcome_write"],
        "complete_path_speedup_claim": False,
        "independent_evaluation": False,
        "new_fits": 0,
        "scope": "three-group-excluded development labels for additional inner gate validation; no fitted gate or independent generalization"
        if inner_validation else "nested development labels; whole outer and inner groups excluded from seed fitting; no fitted gate or independent generalization",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.study)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != "pairs"}))
