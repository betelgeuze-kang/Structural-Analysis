"""Fixed repeated outer-group full paths for trained pre-capture gates."""

import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

from prepare_rc_nested_switch_labels import require
from rc_switch_gate import RidgeGate
from run_rc_expanded_same_parent_probe import complementary_samples, RUNTIME_PIN
from run_rc_same_parent_seed_probe import reader, PINS, save_record
from run_rc_pooled_runtime_campaign import inputs, ARITHMETIC, NEW_INVENTORY
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save
from structural_analysis.benchmark.rc_control_runtime_selection import _runtime_score
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)

GATE_PIN = "05164ea961023ccaf19e1f6ec0bd7f6d1a9a6f3ed8d948e21d6ec420cca192e2"
ORDERS = [
    ["reference", "secant", "proposal"],
    ["secant", "proposal", "reference"],
    ["proposal", "reference", "secant"],
]


def score_path(report, decisions, setup_ns):
    score = _runtime_score(report, decisions, proposal_setup_wall_ns=setup_ns)
    score["score_scope"] = score["score_scope"].replace(
        "static model gate computation and record write",
        "gate/seed policy construction and callback setup",
    )
    return score


def prepare(old_root, new_root, runtime_root, gate_root):
    cases, samples, _, groups, costs = inputs(old_root, new_root)
    prepared = learning._preflight(cases, ARITHMETIC)
    groups = sorted((sorted(group) for group in groups), key=lambda group: group[0])
    runtime, gates = reader(runtime_root, RUNTIME_PIN), reader(gate_root, GATE_PIN)
    selection = runtime("study/selection/result.json")
    by_id = {case.case_id: case for case in cases if case.split == "train"}
    objects, roster = [], []
    for outer, group in enumerate(groups):
        gate = RidgeGate(_bytes(gates(f"fits/outer-{outer}-gate.json")).decode())
        training = gates(f"fits/outer-{outer}-training.json")
        require(
            gate._payload["outer_group_index"] == outer
            and list(gate._payload["excluded_case_ids"]) == group
            and training["excluded_case_ids"] == group
            and all(row["case_id"] not in group for row in training["training_rows"]),
            "whole outer group excluded from gate fit",
        )
        for case_id in group:
            case = by_id[case_id]
            expected = complementary_samples(samples, groups, case_id)
            folds = [
                f
                for f in selection["folds"]
                if f["withheld_training_case"] == case_id
                and f["ridge"] == 1e4
                and f["repetition_index"] == 0
            ]
            require(len(folds) == 1, "one original seed fold required")
            fold = folds[0]
            seed = learning.RCControlSeedPolicy(
                _bytes(
                    runtime(f"study/selection/fit-{fold['fit_index']:04d}-policy.json")
                ).decode()
            )
            require(
                seed.policy_hash == fold["policy_hash"]
                and len(seed.to_dict()["training_sample_hashes"]) == len(expected)
                and set(seed.to_dict()["training_sample_hashes"]) == expected,
                "whole outer group excluded from seed fit",
            )
            roster.append(
                dict(
                    case_id=case_id,
                    outer_group_index=outer,
                    split=case.split,
                    seed_policy_hash=seed.policy_hash,
                    gate_policy_hash=gate.policy_hash,
                    model_hash=case.model.canonical_model_checksum,
                    request=case.request.to_dict(),
                )
            )
            objects.append((case, seed._json, gate._json))
    require(
        len(roster) == 15 and len({r["case_id"] for r in roster}) == 15,
        "all fifteen training cases required",
    )
    historical = dict(
        original_label_costs=costs,
        retained_seed_fit_records=selection["fit_records"],
        gate_fits=gates("fits/fit-result.json"),
        gate_fit_process=gates("execution-result.json"),
        failed_gate_fit=gates("prior-failed-fit.json"),
        gate_training_campaign=gates("fits/fit-plan.json"),
    )
    return prepared, roster, objects, historical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old-labels", "new-labels", "runtime", "gates", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    require(
        re.fullmatch("[0-9a-f]{40}", args.source_revision),
        "exact source revision required",
    )
    before = learning._inference_policy_payload.cache_info()._asdict()
    require(
        before == dict(hits=0, misses=0, maxsize=4, currsize=0),
        "fresh process cache required",
    )
    started = perf_counter_ns()
    prepared, roster, objects, historical = prepare(
        args.old_labels, args.new_labels, args.runtime, args.gates
    )
    if args.preflight_only:
        print(
            json.dumps(
                dict(
                    cases=15,
                    comparisons=45,
                    full_paths=180,
                    new_fits=0,
                    new_solves=0,
                    reserved_evaluations=0,
                )
            )
        )
        return
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(
        root,
        "plan.json",
        _bytes(
            dict(
                source_revision=args.source_revision,
                source_roots=dict(
                    old=str(args.old_labels.resolve()),
                    new=str(args.new_labels.resolve()),
                    runtime=str(args.runtime.resolve()),
                    gates=str(args.gates.resolve()),
                ),
                source_inventories=dict(
                    old=PINS["labels"],
                    new=NEW_INVENTORY,
                    runtime=RUNTIME_PIN,
                    gates=GATE_PIN,
                ),
                roster=roster,
                historical_costs_separate=historical,
                repetitions=3,
                comparisons=45,
                full_paths=180,
                maximum_core_calls=3420,
                new_fits=0,
                reserved_evaluation=False,
                independent_evaluation=False,
                minimum_relative_improvement=0.01,
                arm_order_schedule=ORDERS,
                cache_before=before,
                threshold_search=False,
                own_accepted_history=True,
                score_scope="full arm plus per-comparison gate and seed construction; historical training costs separate",
                cache_scope="one fresh process; bounded parsing reuse; not cold per arm",
            )
        ),
    )
    records = []
    core_calls = 0
    for pair_index, (case, seed_json, gate_json) in enumerate(objects):
        _, compiled, features, _, _ = prepared[case.case_id]
        for repeat in range(3):
            setup_start = perf_counter_ns()
            seed = learning.RCControlSeedPolicy(seed_json)
            gate = RidgeGate(gate_json)

            def propose(context):
                value = seed.propose(
                    context,
                    features,
                    compiled.problem.free_global_dofs,
                    case.request.solver_config.contract_hash,
                    arithmetic_profile=ARITHMETIC,
                    load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
                )
                return value

            guard = gate.guard(features)
            setup_ns = perf_counter_ns() - setup_start
            _save(
                root,
                f"pair-{pair_index:03d}-repeat-{repeat}-started.json",
                _bytes(
                    dict(
                        pair_index=pair_index,
                        repetition=repeat,
                        setup_wall_ns=setup_ns,
                        unknown_work_until_outcome=True,
                    )
                ),
            )
            report = benchmark_rc_control_seed_paths(
                case.model,
                case.request,
                source_revision=args.source_revision,
                output_directory=root / f"pair-{pair_index:03d}-repeat-{repeat}",
                proposal=propose,
                proposal_identity=seed.policy_hash,
                proposal_guard=guard,
                proposal_guard_identity=gate.policy_hash,
                arm_order=tuple(ORDERS[repeat]),
                capture_material_state=True,
                material_capture_scope="proposal-only",
                proposal_abstention_strategy="secant",
                **learning._arithmetic_kwargs(ARITHMETIC),
            )
            decisions = [
                dict(decision=entry["proposal_decision"])
                for entry in report["arms"]["proposal"]["entries"]
            ]
            score = score_path(report, decisions, setup_ns)
            record = dict(
                pair_index=pair_index,
                repetition=repeat,
                report_hash=report["report_hash"],
                setup_wall_ns=setup_ns,
                decisions=decisions,
                score=score,
            )
            save_record(root, record)
            records.append(record)
            core_calls += score["execution_work"]["known_work"]["core_calls"]
            require(core_calls <= 3420, "declared core-call budget exhausted")
    _save(
        root,
        "outcome.json",
        _bytes(
            dict(
                records=records,
                wall_ns_before_outcome_write=perf_counter_ns() - started,
                cache_after=learning._inference_policy_payload.cache_info()._asdict(),
                new_fits=0,
                reserved_evaluation=False,
                independent_evaluation=False,
            )
        ),
    )
    print(json.dumps(dict(completed_reports=len(records), root=str(root))), flush=True)


if __name__ == "__main__":
    main()
