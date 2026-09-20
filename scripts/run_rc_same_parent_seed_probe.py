"""Counterbalance existing seeds on every eligible retained middle-geometry parent.

This is a post-hoc diagnostic, not policy training or complete-path selection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter_ns

from run_grouped_rc_history_coverage import cases_with_history_coverage
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext, benchmark_rc_control_seed_paths

PINS = {
    'labels': 'f850f7e65670bf4d6254039da2aca35269cbd1840b645d82308c2402017849f0',
    'runtime': 'd5e1d9d6727a827ba8f4011b9a52e9ca66be417bd927cae9dceb450e96a1aba2',
}
ARITHMETIC = 'retained-twofold-refinement.v1'
PREFIX_PIN = '90528a26fce7f06f6a768766120b14e0c6063e2a9aed07393a50c422a7688f13'


def save_record(root, record):
    """Each completed comparison gets its own immutable receipt."""
    _save(root, f"record-{record['pair_index']:03d}-{record['repetition']}.json", _bytes(record))


def reader(root, pin):
    raw = (root / 'inventory.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError('original inventory changed')
    index = {r['path']: r for r in json.loads(raw)['files']}

    def original(name):
        raw = (root / name).read_bytes()
        row = index[name]
        if len(raw) != row['byte_length'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError(f'original input changed: {name}')
        return json.loads(raw)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--retained-prefix', type=Path)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    started = perf_counter_ns()
    labels = reader(args.labels, PINS['labels'])
    runtime = reader(args.runtime, PINS['runtime'])
    cases = cases_with_history_coverage(extended_line_search=True)
    declared = labels('study/coverage-plan.json')['cases']
    if declared != [{'case_id': c.case_id, 'split': c.split, 'model': c.model.canonical_payload(),
                     'request': c.request.to_dict()} for c in cases]:
        raise ValueError('case declarations changed')
    prepared = learning._preflight(cases, ARITHMETIC)
    selection = runtime('study/selection/result.json')
    samples = labels('study/labels/training-samples.json')
    roster = []
    objects = []
    for case in cases:
        if case.case_id not in ('train-b-amp050', 'train-b-amp100', 'train-b-amp150'):
            continue
        for ridge in (1e4, 1e6):
            fold = next(f for f in selection['folds'] if f['withheld_training_case'] == case.case_id
                        and f['ridge'] == ridge and f['repetition_index'] == 0)
            policy = learning.RCControlSeedPolicy(_bytes(runtime(
                f"study/selection/fit-{fold['fit_index']:04d}-policy.json")).decode())
            expected = {s['sample_hash'] for s in samples if not s['case_id'].startswith('train-b-')}
            if policy.policy_hash != fold['policy_hash'] or set(policy.to_dict()['training_sample_hashes']) != expected or len(expected) != 66:
                raise ValueError('complementary policy binding')
            for index in range(1, 12):
                stem = f'study/labels/{case.case_id}/generation/reference/{index:03d}'
                step = labels(stem + '-1-step.json')
                context = RCControlSeedContext(**labels(stem + '-context.json'))
                if not step['committed'] or context.target_m != case.request.targets_m[index]:
                    raise ValueError('original accepted target required')
                row = {'case_id': case.case_id, 'ridge': ridge, 'target_index': index,
                       'policy_hash': policy.policy_hash, 'parent_hash': step['parent_checkpoint']['state_hash']}
                roster.append(row)
                objects.append((case, policy, index, _bytes(step['parent_checkpoint']), context))
    if len(objects) != 66:
        raise ValueError('all 66 declared seed-parent pairs required')
    prefix_reports = {}
    if args.retained_prefix:
        prefix = reader(args.retained_prefix, PREFIX_PIN)
        old_plan = prefix('study/plan.json')
        if old_plan['roster'] != roster or old_plan['source_inventories'] != PINS:
            raise ValueError('retained prefix protocol differs')
        # The pinned failed driver completed exactly the first two comparisons.
        for repeat in (0, 1):
            report = prefix(f'study/pair-000-repeat-{repeat}/comparison.json')
            if report['report_hash'] != _sha(_bytes({k: v for k, v in report.items() if k != 'report_hash'})):
                raise ValueError('retained report hash mismatch')
            if report['initial_parent_hash'] != roster[0]['parent_hash'] or report['proposal_identity'] != roster[0]['policy_hash']:
                raise ValueError('retained parent or policy differs')
            prefix_reports[(0, repeat)] = report
    if args.preflight_only:
        print(json.dumps({'pairs': len(objects), 'repetitions': 3, 'retained_reports': len(prefix_reports), 'solver_calls': 0}))
        return
    root = args.output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes({'source_revision': args.source_revision, 'source_inventories': PINS,
        'roster': roster, 'repetitions': 3, 'maximum_core_calls': 1188,
        'scope': 'posthoc_same_parent_single_target_diagnostic', 'new_fits': 0,
        'retained_prefix': str(args.retained_prefix.resolve()) if args.retained_prefix else None,
        'retained_prefix_inventory_sha256': PREFIX_PIN if args.retained_prefix else None,
        'retained_report_count': len(prefix_reports),
        'reserved_evaluation': False, 'complete_path_claim': False,
        'training_labels_or_policy_created': False, 'feature_capture_charged_to_proposal': True,
        'arm_order_schedule': [['reference', 'secant', 'proposal'], ['secant', 'proposal', 'reference'],
                               ['proposal', 'reference', 'secant']]}))
    records = []
    for pair_index, (case, policy, index, parent, context) in enumerate(objects):
        _, compiled, features, _, _ = prepared[case.case_id]

        def propose(current):
            return policy.propose(current, features, compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash, arithmetic_profile=ARITHMETIC,
                load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m)

        for repeat in range(3):
            order = ('reference', 'secant', 'proposal')
            order = order[repeat:] + order[:repeat]
            if (pair_index, repeat) in prefix_reports:
                report = prefix_reports[(pair_index, repeat)]
                if report['arm_order'] != list(order):
                    raise ValueError('retained arm order differs')
                record = {'pair_index': pair_index, 'repetition': repeat,
                          'report_hash': report['report_hash'], 'retained_from_prefix': True}
                records.append(record)
                save_record(root, record)
                continue
            report = benchmark_rc_control_seed_paths(case.model, case.request,
                source_revision=args.source_revision, output_directory=root / f'pair-{pair_index:03d}-repeat-{repeat}',
                proposal=propose, proposal_identity=policy.policy_hash, arm_order=order,
                parent_checkpoint_bytes=parent, accepted_context=context,
                capture_material_state=True, material_capture_scope='proposal-only',
                proposal_abstention_strategy='secant', **learning._arithmetic_kwargs(ARITHMETIC))
            record = {'pair_index': pair_index, 'repetition': repeat,
                      'report_hash': report['report_hash'], 'retained_from_prefix': False}
            records.append(record)
            save_record(root, record)
    _save(root, 'outcome.json', _bytes({'records': records, 'wall_ns_before_outcome_write': perf_counter_ns() - started,
                                      'retained_report_count': len(prefix_reports),
                                      'wall_scope': 'current invocation only; original failed driver wall time not reconstructed',
                                      'new_fits': 0, 'complete_path_claim': False, 'reserved_evaluation': False}))
    print(json.dumps({'completed_reports': len(records), 'root': str(root)}))


if __name__ == '__main__':
    main()
