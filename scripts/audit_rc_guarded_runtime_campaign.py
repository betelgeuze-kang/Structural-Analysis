"""Audit all original guarded full paths without refitting or structural solves."""

import argparse
from collections import OrderedDict
import json
from pathlib import Path
from statistics import mean

from audit_grouped_rc_runtime_campaign import checked, read, require
from audit_rc_expanded_same_parent_probe import require_work_counters
from run_rc_guarded_runtime_campaign import (
    prepare,
    score_path,
    ORDERS,
    GATE_PIN,
    RUNTIME_PIN,
    PINS,
    NEW_INVENTORY,
)
from rc_switch_gate import RidgeGate
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext


def require_arm_summary(full, summary):
    require(
        {
            k: v
            for k, v in full.items()
            if k not in ("response_history", "terminal_checkpoint", "preload_response")
        }
        == summary,
        "original complete arm receipt required",
    )


def require_declined_guard(entry, context):
    require(
        "committed_material_capture" not in entry
        and "committed_material_state_json" not in context
        and entry["proposal_decision"]
        in ("abstained_to_secant", "abstained_to_reference")
        and type(entry["proposal_wall_ns"]) is int
        and entry["proposal_wall_ns"] >= 0,
        "declined guard must retain timed deterministic fallback without capture",
    )


def audit(root):
    plan, outcome = read(root / "plan.json"), read(root / "outcome.json")
    prepared, roster, objects, historical = prepare(
        *(Path(plan["source_roots"][key]) for key in ("old", "new", "runtime", "gates"))
    )
    require(
        plan["roster"] == roster and plan["historical_costs_separate"] == historical,
        "original complete cases, policies and historical costs required",
    )
    require(
        plan["repetitions"] == 3
        and plan["comparisons"] == 45
        and plan["full_paths"] == 180
        and plan["maximum_core_calls"] == 3420
        and plan["arm_order_schedule"] == ORDERS
        and plan["minimum_relative_improvement"] == 0.01
        and plan["threshold_search"] is False
        and plan["reserved_evaluation"] is False
        and plan["new_fits"] == 0,
        "fixed full-path campaign scope required",
    )
    require(
        plan["source_inventories"]
        == dict(
            old=PINS["labels"], new=NEW_INVENTORY, runtime=RUNTIME_PIN, gates=GATE_PIN
        ),
        "original inventory declarations required",
    )
    require(
        plan["own_accepted_history"] is True
        and plan["independent_evaluation"] is False
        and outcome["new_fits"] == 0
        and outcome["reserved_evaluation"] is False
        and outcome["independent_evaluation"] is False,
        "no undeclared fitting or reserved evaluation",
    )
    records = outcome["records"]
    require(
        len(records) == 45
        and [(r["pair_index"], r["repetition"]) for r in records]
        == [(p, r) for p in range(15) for r in range(3)],
        "complete ordered original reports required",
    )
    require(
        plan["cache_before"] == dict(hits=0, misses=0, maxsize=4, currsize=0),
        "cold initial cache required",
    )
    cache = OrderedDict()
    hits = misses = allowed = declined = 0
    total = dict.fromkeys(("core_calls", "newton_iterations", "linear_solves"), 0)
    all_rows = []
    for record in records:
        pair, repeat = record["pair_index"], record["repetition"]
        declaration = roster[pair]
        case, _, gate_json = objects[pair]
        _, compiled, features, _, _ = prepared[case.case_id]
        gate = RidgeGate(gate_json)
        callback = gate.guard(features)
        stem = f"pair-{pair:03d}-repeat-{repeat}"
        path = root / stem
        require(
            read(root / f"record-{pair:03d}-{repeat}.json") == record,
            "immutable completion receipt required",
        )
        started = read(root / f"{stem}-started.json")
        require(
            type(record["setup_wall_ns"]) is int
            and record["setup_wall_ns"] >= 0
            and started["setup_wall_ns"] == record["setup_wall_ns"],
            "original setup cost required",
        )
        report = checked(path / "comparison.json", "report_hash")
        require(
            report["report_hash"] == record["report_hash"]
            and report["source_revision"] == plan["source_revision"]
            and report["model_checksum"] == declaration["model_hash"]
            and report["request"] == declaration["request"]
            and report["compiled_problem_contract_hash"]
            == compiled.problem.contract_hash,
            "original source model and loading history required",
        )
        require(
            report["proposal_identity"] == declaration["seed_policy_hash"]
            and report["proposal_guard"]
            == dict(
                identity=gate.policy_hash,
                identity_is_attestation=False,
                input_scope="accepted_prefix_before_material_capture",
                decline_strategy="secant",
                errors_fail_path=True,
            ),
            "original guarded policies required",
        )
        require(
            report["absolute_tolerance"] == 1e-10
            and report["relative_tolerance"] == 1e-8
            and report["arm_order"] == ORDERS[repeat]
            and report["capture_material_state"] is True
            and report["material_capture_scope"] == "proposal-only"
            and report["proposal_abstention_strategy"] == "secant",
            "original comparison contract required",
        )
        decisions = [
            dict(decision=e["proposal_decision"])
            for e in report["arms"]["proposal"]["entries"]
        ]
        require(
            decisions == record["decisions"]
            and score_path(report, decisions, record["setup_wall_ns"])
            == record["score"],
            "all original decisions and scored costs required",
        )
        actual_work = dict.fromkeys(total, 0)
        for name, arm in {
            **report["arms"],
            "fresh-reference": report["fresh_reference"],
        }.items():
            require_arm_summary(checked(path / name / "path.json", "path_hash"), arm)
            if arm["status"] == "complete":
                require(
                    arm["accepted_target_count"] == 12 and len(arm["entries"]) == 12,
                    "all twelve targets required",
                )
            invocations = list(arm["preload_invocations"])
            invocations.extend(i for e in arm["entries"] for i in e["invocations"])
            for invocation in invocations:
                require(
                    invocation["unknown_work"] is False, "known execution work required"
                )
                require_work_counters(invocation["work"])
                for key in total:
                    actual_work[key] += invocation["work"][key]
            if name != "proposal":
                require(
                    all("proposal_guard" not in e for e in arm["entries"]),
                    "baseline must not use gate",
                )
        for key in total:
            total[key] += actual_work[key]
        require(
            actual_work == record["score"]["execution_work"]["known_work"],
            "complete invocation work sum required",
        )
        for index, entry in enumerate(report["arms"]["proposal"]["entries"]):
            original = read(path / "proposal" / f"{index:03d}-guard-context.json")
            require(
                "committed_material_state_json" not in original,
                "pre-capture guard context required",
            )
            context = read(path / "proposal" / f"{index:03d}-context.json")
            require(
                {
                    k: v
                    for k, v in context.items()
                    if k != "committed_material_state_json"
                }
                == original,
                "same own-prefix gate and proposal context required",
            )
            receipt = read(path / "proposal" / f"{index:03d}-guard-outcome.json")
            require(
                receipt == entry["proposal_guard"], "original guard outcome required"
            )
            if receipt["status"] == "returned":
                decision = callback(RCControlSeedContext(**original))
                require(
                    type(receipt["allow_proposal"]) is bool
                    and receipt["allow_proposal"] == decision,
                    "original frozen gate decision required",
                )
                if decision:
                    allowed += 1
                    require(
                        "committed_material_capture" in entry,
                        "allowed capture cost required",
                    )
                    key = declaration["seed_policy_hash"]
                    if key in cache:
                        hits += 1
                        cache.move_to_end(key)
                    else:
                        misses += 1
                        cache[key] = None
                        if len(cache) > 4:
                            cache.popitem(last=False)
                else:
                    declined += 1
                    require_declined_guard(entry, context)
        all_rows.append(
            dict(case_id=case.case_id, repetition=repeat, score=record["score"])
        )
    require(total["core_calls"] <= 3420, "declared core-call budget required")
    require(
        outcome["cache_after"]
        == dict(hits=hits, misses=misses, maxsize=4, currsize=len(cache)),
        "exact guarded proposal cache accounting required",
    )
    complete = all(
        r["score"]["full_comparison_pass"]
        and not r["score"]["execution_work"]["unknown_work"]
        for r in all_rows
    )
    by_case = [
        dict(
            case_id=c["case_id"],
            mean_ratio=mean(
                r["score"]["proposal_over_secant_path_wall_ratio"]
                for r in all_rows
                if r["case_id"] == c["case_id"]
            )
            if complete
            else None,
        )
        for c in roster
    ]
    ratio = mean(r["mean_ratio"] for r in by_case) if complete else None
    proposed = sum(r["score"]["proposed_count"] for r in all_rows)
    return dict(
        rows=all_rows,
        cases=by_case,
        report_count=45,
        full_comparison_pass=complete,
        equal_case_mean_ratio=ratio,
        guard_allowed=allowed,
        guard_declined=declined,
        proposed_count=proposed,
        all_execution_work=total,
        cache_after=outcome["cache_after"],
        development_runtime_eligible=complete and proposed > 0 and ratio < 0.99,
        historical_training_costs_amortized=False,
        net_savings_proved=False,
        independent_evaluation=False,
        reserved_evaluation=False,
        new_fits=0,
        wall_ns_before_outcome_write=outcome["wall_ns_before_outcome_write"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.study)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "cases")}))
