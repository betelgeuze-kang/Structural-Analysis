"""Generate all declared nested switching labels from retained native parents."""

import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

from prepare_rc_nested_switch_labels import (
    nested_plan,
    validate_seed_training_hashes,
    require,
)
from rc_switch_prefix_features import prefix_features
from run_rc_pooled_runtime_campaign import inputs, ARITHMETIC, NEW_INVENTORY
from run_rc_same_parent_seed_probe import reader, PINS, save_record
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _sha, _save
from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext,
    benchmark_rc_control_seed_paths,
)

SEED_PIN = "547112b912e6ff77fc43e755daa8ce12467d7a72766ec2ada3875e4c40263c49"
LABEL_RULE = {
    "repetitions": 3,
    "maximum_positive_time_ratio": 0.99,
    "all_repeats_must_pass": True,
    "actual_proposal_required": True,
    "unverified_label": None,
    "timing_scope": "proposal_arm_including_capture_inference_solves_recovery_io",
}


def retained_seed_cost(seed_root):
    receipt = reader(seed_root, SEED_PIN)("seed-stage-result.json")
    require(
        receipt["seed_fits"] == 10 and receipt["new_structural_solves"] == 0,
        "original seed stage scope",
    )
    return {
        "seed_stage_receipt": receipt,
        "cost_scope": "reused historical seed fits; fit time is contained in stage time",
        "complete_historical_cost_measured": False,
        "unmeasured_scope": "later normalization audit and inventory preparation",
    }


def prepare(old_root, new_root, seed_root):
    cases, samples, _, groups, costs = inputs(old_root, new_root)
    expected = nested_plan(groups, samples)
    seeds = reader(seed_root, SEED_PIN)
    stored = seeds("nested-plan.json")
    require(
        all(stored[key] == value for key, value in expected.items()),
        "original nested declaration changed",
    )
    prepared = learning._preflight(cases, ARITHMETIC)
    policies = {}
    for fit in expected["seed_fits"]:
        policy = learning.RCControlSeedPolicy(
            _bytes(seeds(f"seed-fits/fit-{fit['fit_index']:03d}-policy.json")).decode()
        )
        validate_seed_training_hashes(policy.to_dict(), fit)
        require(policy.to_dict()["ridge"] == fit["ridge"], "declared ridge changed")
        policies[fit["fit_index"]] = policy
    old, new = reader(old_root, PINS["labels"]), reader(new_root, NEW_INVENTORY)
    by_case = {case.case_id: case for case in cases}
    by_sample = {(row["case_id"], row["target_index"]): row for row in samples}
    require(len(by_sample) == 165, "unique original target samples required")
    roster, objects = [], []
    for task_index, task in enumerate(expected["label_tasks"]):
        observed = set()
        for case_id in task["label_case_ids"]:
            case = by_case[case_id]
            source = new if case_id.startswith(("train-d-", "train-e-")) else old
            policy = policies[task["seed_fit_index"]]
            for index in range(1, 12):
                sample = by_sample[(case_id, index)]
                stem = f"study/labels/{case_id}/generation/reference/{index:03d}"
                step = source(stem + "-1-step.json")
                context = RCControlSeedContext(**source(stem + "-context.json"))
                require(
                    step["committed"] is True
                    and context.target_m == case.request.targets_m[index]
                    and sample["context"] == context.to_dict()
                    and sample["parent_hash"] == step["parent_checkpoint"]["state_hash"]
                    and sample["original_step_bytes_hash"] == _sha(_bytes(step)),
                    "original sample/parent/context binding",
                )
                observed.add(sample["sample_hash"])
                features = prefix_features(context, prepared[case_id][2])
                roster.append(
                    {
                        "task_index": task_index,
                        "outer_group_index": task["outer_group_index"],
                        "inner_group_index": task["inner_group_index"],
                        "case_id": case_id,
                        "target_index": index,
                        "seed_fit_index": task["seed_fit_index"],
                        "policy_hash": policy.policy_hash,
                        "source_sample_hash": sample["sample_hash"],
                        "parent_hash": sample["parent_hash"],
                        "guard_features": features,
                    }
                )
                objects.append(
                    (case, policy, _bytes(step["parent_checkpoint"]), context)
                )
        require(
            observed == set(task["label_source_sample_hashes"]),
            "complete inner label source group required",
        )
    require(
        len(roster) == 660 and len(policies) == 10,
        "complete nested label scope required",
    )
    return prepared, roster, objects, costs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old-labels", "new-labels", "seeds", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    require(
        re.fullmatch("[0-9a-f]{40}", args.source_revision),
        "exact source revision required",
    )
    require(
        learning._inference_policy_payload.cache_info()._asdict()
        == {"hits": 0, "misses": 0, "maxsize": 4, "currsize": 0},
        "fresh process cache required",
    )
    started = perf_counter_ns()
    prepared, roster, objects, costs = prepare(
        args.old_labels, args.new_labels, args.seeds
    )
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "pairs": len(roster),
                    "comparisons": 1980,
                    "single_target_paths": 7920,
                    "new_fits": 0,
                    "new_solves": 0,
                    "reserved_evaluations": 0,
                }
            )
        )
        return
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(
        root,
        "plan.json",
        _bytes(
            {
                "source_revision": args.source_revision,
                "source_roots": {
                    "old": str(args.old_labels.resolve()),
                    "new": str(args.new_labels.resolve()),
                    "seeds": str(args.seeds.resolve()),
                },
                "source_inventories": {
                    "old": PINS["labels"],
                    "new": NEW_INVENTORY,
                    "seeds": SEED_PIN,
                },
                "roster": roster,
                "label_rule": LABEL_RULE,
                "repetitions": 3,
                "maximum_core_calls": 11880,
                "historical_label_costs_separate": costs,
                "seed_fits_reused": 10,
                "historical_seed_costs_separate": retained_seed_cost(args.seeds),
                "new_fits": 0,
                "gate_trained": False,
                "reserved_evaluation": False,
                "complete_path_claim": False,
                "feature_capture_charged_to_proposal": True,
                "cache_before": {"hits": 0, "misses": 0, "maxsize": 4, "currsize": 0},
                "cache_scope": "fresh process; bounded reuse across calls; not cold per arm",
                "arm_order_schedule": [
                    ["reference", "secant", "proposal"],
                    ["secant", "proposal", "reference"],
                    ["proposal", "reference", "secant"],
                ],
            }
        ),
    )
    records = []
    for pair_index, (case, policy, parent, context) in enumerate(objects):
        _, compiled, features, _, _ = prepared[case.case_id]

        def propose(current):
            return policy.propose(
                current,
                features,
                compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash,
                arithmetic_profile=ARITHMETIC,
                load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
            )

        for repeat in range(3):
            order = ("reference", "secant", "proposal")
            order = order[repeat:] + order[:repeat]
            report = benchmark_rc_control_seed_paths(
                case.model,
                case.request,
                source_revision=args.source_revision,
                output_directory=root / f"pair-{pair_index:03d}-repeat-{repeat}",
                proposal=propose,
                proposal_identity=policy.policy_hash,
                arm_order=order,
                parent_checkpoint_bytes=parent,
                accepted_context=context,
                capture_material_state=True,
                material_capture_scope="proposal-only",
                proposal_abstention_strategy="secant",
                **learning._arithmetic_kwargs(ARITHMETIC),
            )
            record = {
                "pair_index": pair_index,
                "repetition": repeat,
                "report_hash": report["report_hash"],
            }
            save_record(root, record)
            records.append(record)
    _save(
        root,
        "outcome.json",
        _bytes(
            {
                "records": records,
                "cache_after": learning._inference_policy_payload.cache_info()._asdict(),
                "wall_ns_before_outcome_write": perf_counter_ns() - started,
                "new_fits": 0,
                "reserved_evaluation": False,
                "gate_trained": False,
            }
        ),
    )
    print(
        json.dumps({"completed_reports": len(records), "root": str(root)}), flush=True
    )


if __name__ == "__main__":
    main()
