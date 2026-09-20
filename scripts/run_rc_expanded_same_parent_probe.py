"""Prepare all B/D/E retained-parent probes with whole-group-excluded policies.

Post-hoc diagnosis only: no fitting, reserved evaluation, or full-path speed claim.
"""
import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

from run_rc_pooled_runtime_campaign import ARITHMETIC, NEW_INVENTORY, inputs
from run_rc_same_parent_seed_probe import PINS, reader, save_record
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save
from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext, benchmark_rc_control_seed_paths,
)

RUNTIME_PIN = 'e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0'
CASE_IDS = tuple(f'train-{group}-amp{amplitude}' for group in 'bde'
                 for amplitude in ('050', '100', '150'))


def complementary_samples(samples, groups, case_id):
    matches = [set(group) for group in groups if case_id in group]
    if len(matches) != 1 or len(matches[0]) != 3:
        raise ValueError('one complete three-case exclusion group required')
    expected = {row['sample_hash'] for row in samples if row['case_id'] not in matches[0]}
    if len(expected) != 132:
        raise ValueError('132 complementary original samples required')
    return expected


def prepare(old_root, new_root, runtime_root):
    cases, samples, profile, groups, costs = inputs(old_root, new_root)
    del profile
    prepared = learning._preflight(cases, ARITHMETIC)
    old, new = reader(old_root, PINS['labels']), reader(new_root, NEW_INVENTORY)
    runtime = reader(runtime_root, RUNTIME_PIN)
    selection = runtime('study/selection/result.json')
    by_id = {case.case_id: case for case in cases}
    objects, roster = [], []
    for case_id in CASE_IDS:
        case = by_id[case_id]
        labels = old if case_id.startswith('train-b-') else new
        expected = complementary_samples(samples, groups, case_id)
        for ridge in (1e4, 1e6):
            folds = [fold for fold in selection['folds']
                     if fold['withheld_training_case'] == case_id and fold['ridge'] == ridge
                     and fold['repetition_index'] == 0]
            if len(folds) != 1:
                raise ValueError('one original fold required')
            fold = folds[0]
            policy = learning.RCControlSeedPolicy(_bytes(runtime(
                f"study/selection/fit-{fold['fit_index']:04d}-policy.json")).decode())
            if policy.policy_hash != fold['policy_hash'] or set(policy.to_dict()['training_sample_hashes']) != expected:
                raise ValueError('whole-group complementary policy mismatch')
            for index in range(1, 12):
                stem = f'study/labels/{case_id}/generation/reference/{index:03d}'
                step = labels(stem + '-1-step.json')
                context = RCControlSeedContext(**labels(stem + '-context.json'))
                if not step['committed'] or context.target_m != case.request.targets_m[index]:
                    raise ValueError('original accepted target required')
                roster.append({'case_id': case_id, 'ridge': ridge, 'target_index': index,
                               'policy_hash': policy.policy_hash,
                               'parent_hash': step['parent_checkpoint']['state_hash']})
                objects.append((case, policy, _bytes(step['parent_checkpoint']), context))
    if len(objects) != 198:
        raise ValueError('all 198 B/D/E policy-parent pairs required')
    return prepared, roster, objects, costs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-labels', 'new-labels', 'runtime', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    initial_cache = learning._inference_policy_payload.cache_info()._asdict()
    if initial_cache != {'hits': 0, 'misses': 0, 'maxsize': 4, 'currsize': 0}:
        raise ValueError('fresh process with empty policy cache required')
    started = perf_counter_ns()
    prepared, roster, objects, costs = prepare(args.old_labels, args.new_labels, args.runtime)
    if args.preflight_only:
        print(json.dumps({'pairs': len(objects), 'repetitions': 3, 'single_target_paths': 2376,
                          'new_fits': 0, 'solver_calls': 0, 'reserved_evaluations': 0}))
        return
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes({'source_revision': args.source_revision,
        'source_roots': {'old': str(args.old_labels.resolve()), 'new': str(args.new_labels.resolve()),
                         'runtime': str(args.runtime.resolve())},
        'source_inventories': {'old': PINS['labels'], 'new': NEW_INVENTORY, 'runtime': RUNTIME_PIN},
        'roster': roster, 'repetitions': 3, 'maximum_core_calls': 3564,
        'new_fits': 0, 'reserved_evaluation': False, 'complete_path_claim': False,
        'scope': 'posthoc_all_b_d_e_same_parent_single_target_diagnostic',
        'historical_label_costs_separate': costs,
        'feature_capture_charged_to_proposal': True,
        'cache_before': initial_cache,
        'cache_scope': 'one fresh process; bounded reuse across calls; not cold per arm',
        'arm_order_schedule': [['reference', 'secant', 'proposal'],
                               ['secant', 'proposal', 'reference'], ['proposal', 'reference', 'secant']]}))
    records = []
    for pair_index, (case, policy, parent, context) in enumerate(objects):
        _, compiled, features, _, _ = prepared[case.case_id]

        def propose(current):
            return policy.propose(current, features, compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash, arithmetic_profile=ARITHMETIC,
                load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m)

        for repeat in range(3):
            order = ('reference', 'secant', 'proposal')
            order = order[repeat:] + order[:repeat]
            report = benchmark_rc_control_seed_paths(case.model, case.request,
                source_revision=args.source_revision,
                output_directory=root / f'pair-{pair_index:03d}-repeat-{repeat}',
                proposal=propose, proposal_identity=policy.policy_hash, arm_order=order,
                parent_checkpoint_bytes=parent, accepted_context=context,
                capture_material_state=True, material_capture_scope='proposal-only',
                proposal_abstention_strategy='secant', **learning._arithmetic_kwargs(ARITHMETIC))
            record = {'pair_index': pair_index, 'repetition': repeat, 'report_hash': report['report_hash']}
            save_record(root, record)
            records.append(record)
    _save(root, 'outcome.json', _bytes({'records': records,
        'wall_ns_before_outcome_write': perf_counter_ns() - started,
        'cache_after': learning._inference_policy_payload.cache_info()._asdict(),
        'new_fits': 0, 'complete_path_claim': False, 'reserved_evaluation': False}))
    print(json.dumps({'completed_reports': len(records), 'root': str(root)}))


if __name__ == '__main__':
    main()
