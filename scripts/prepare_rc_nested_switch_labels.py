"""Predeclare nested group exclusions for learned switching-label generation.

This prepares provenance only; no fits, solves, classifier or validation claim.
"""
import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

import numpy as np

from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save

from run_rc_pooled_runtime_campaign import inputs


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nested_plan(groups, samples):
    require(type(groups) is list and len(groups) >= 3, 'three or more exclusion groups required')
    require(all(type(group) is list and group and all(type(name) is str and name for name in group)
                for group in groups), 'named nonempty groups required')
    names = [name for group in groups for name in group]
    require(len(names) == len(set(names)), 'overlapping exclusion groups')
    require(type(samples) is list and samples, 'original samples required')
    hashes = [row['sample_hash'] for row in samples]
    require(all(type(value) is str and re.fullmatch('sha256:[0-9a-f]{64}', value) for value in hashes)
            and len(hashes) == len(set(hashes)), 'unique original sample hashes required')
    require(all(row['split'] == 'train' for row in samples)
            and {row['case_id'] for row in samples} == set(names), 'training-only complete case roster required')
    ordered = sorted((sorted(group) for group in groups), key=lambda group: group[0])
    fits, tasks = [], []
    fit_ids = {}
    for outer, outer_cases in enumerate(ordered):
        for inner, inner_cases in enumerate(ordered):
            if inner == outer:
                continue
            excluded = tuple(sorted((outer, inner)))
            expected = sorted(row['sample_hash'] for row in samples
                              if row['case_id'] not in set(outer_cases + inner_cases))
            require(expected, 'nonempty nested seed training complement required')
            if excluded not in fit_ids:
                fit_ids[excluded] = len(fits)
                fits.append({'fit_index': len(fits), 'excluded_group_indices': list(excluded),
                             'excluded_case_ids': sorted(outer_cases + inner_cases),
                             'training_sample_hashes': expected, 'ridge': 10000.0})
            tasks.append({'outer_group_index': outer, 'outer_evaluation_case_ids': outer_cases,
                          'inner_group_index': inner, 'label_case_ids': inner_cases,
                          'seed_fit_index': fit_ids[excluded],
                          'label_source_sample_hashes': sorted(row['sample_hash'] for row in samples
                                                              if row['case_id'] in inner_cases)})
    return {'schema_version': 'rc-nested-switch-label-provenance.v1',
            'groups': ordered, 'seed_fits': fits, 'label_tasks': tasks,
            'repetitions': 3, 'new_fits_executed': 0, 'new_solves_executed': 0,
            'reserved_evaluation_executed': False, 'independent_provenance': False,
            'gate_trained': False, 'full_path_speedup_claim': False,
            'fit_reuse_scope': 'identical two-group complements shared across directed label tasks',
            'ridge_selection_scope': 'fixed from prior development diagnostics; not independent model selection'}


def validate_seed_training_hashes(policy, fit):
    actual = policy['training_sample_hashes']
    require(type(actual) is list and len(actual) == len(set(actual))
            and sorted(actual) == fit['training_sample_hashes'],
            'seed policy must exclude both outer and inner groups exactly')


def fit_declared_seeds(plan, samples, profile, directory):
    """Fit only declared complements; these policies are not promoted."""
    by_hash = {row['sample_hash']: row for row in samples}
    require(len(by_hash) == len(samples), 'unique original samples required')
    directory.mkdir(parents=True, exist_ok=False)
    receipts = []
    for fit in plan['seed_fits']:
        selected = [by_hash[value] for value in fit['training_sample_hashes']]
        require(all(row['case_id'] not in fit['excluded_case_ids'] for row in selected),
                'excluded case in seed complement')
        started = perf_counter_ns()
        policy = learning._fit(selected, profile, fit['ridge'], 0.1,
                               fit_solver=learning.SVD_RIDGE_FIT_PROFILE)
        elapsed = perf_counter_ns() - started
        payload = policy.to_dict()
        validate_seed_training_hashes(payload, fit)
        x = np.asarray([row['features'] for row in selected])
        require(np.array_equal(np.asarray(payload['feature_mean']), x.mean(axis=0))
                and np.array_equal(np.asarray(payload['feature_min']), x.min(axis=0))
                and np.array_equal(np.asarray(payload['feature_max']), x.max(axis=0)),
                'normalization must use only declared complement')
        name = f"fit-{fit['fit_index']:03d}-policy.json"
        artifact = _save(directory, name, _bytes(payload))
        receipts.append({'fit_index': fit['fit_index'], 'sample_count': len(selected),
                         'policy_hash': policy.policy_hash, 'wall_ns': elapsed,
                         'artifact': artifact, 'complement_feature_statistics_exact': True,
                         'promoted': False})
    _save(directory, 'fit-receipts.json', _bytes({'fits': receipts, 'gate_trained': False,
        'structural_solves': 0, 'reserved_evaluation_executed': False}))
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-labels', type=Path, required=True)
    parser.add_argument('--new-labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _, samples, _, groups, costs = inputs(args.old_labels, args.new_labels)
    plan = nested_plan(groups, samples)
    require(len(groups) == 5 and len(samples) == 165
            and len(plan['seed_fits']) == 10 and len(plan['label_tasks']) == 20,
            'fixed five-group study required')
    plan['historical_label_costs_separate'] = costs
    plan['planned_label_parent_pairs'] = sum(len(task['label_source_sample_hashes']) for task in plan['label_tasks'])
    plan['planned_comparisons'] = plan['planned_label_parent_pairs'] * plan['repetitions']
    plan['planned_single_target_paths'] = 4 * plan['planned_comparisons']
    with args.output.open('x') as stream:
        stream.write(json.dumps(plan, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: value for key, value in plan.items()
                      if key.startswith('planned_') or key.startswith('new_')}))


if __name__ == '__main__':
    main()
