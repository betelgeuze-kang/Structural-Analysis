"""Predeclared whole-group runtime selection from retained 99+66 labels."""
import argparse
from pathlib import Path
import re
from time import perf_counter_ns

from run_grouped_rc_runtime_campaign import ARITHMETIC
from run_rc_interior_training_coverage import expanded_cases
from run_rc_same_parent_seed_probe import PINS, reader
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save
from structural_analysis.benchmark.rc_control_runtime_selection import (
    _validate_case_rows, run_rc_control_runtime_selection,
)
from structural_analysis.benchmark.rc_control_training_diagnostics import _validated_training_data

NEW_INVENTORY = '23d28a47d891e1b45d7306007529a78d203a436677af0fd5fe9e7dbe4061af92'


def inputs(old_root, new_root):
    old = reader(old_root, PINS['labels'])
    new = reader(new_root, NEW_INVENTORY)
    original, added, combined, groups = expanded_cases()
    prepared = learning._preflight(combined, ARITHMETIC)
    samples = []
    profile = None
    costs = []
    for read, cases, expected in ((old, original, 99), (new, added, 66)):
        rows = read('study/labels/training-samples.json')
        policy = learning.RCControlSeedPolicy(_bytes(read('study/labels/policy.json')).decode())
        source, grouped, current = _validated_training_data(rows, policy)
        _validate_case_rows(cases, prepared, grouped, source, ARITHMETIC)
        if len(rows) != expected or (profile is not None and current != profile):
            raise ValueError('complete original labels and matching profiles required')
        profile = current
        samples.extend(rows)
        report = read('study/labels/learning-study.json')
        if not report['evaluation_deferred'] or report['evaluation_work']['known_work']['core_calls']:
            raise ValueError('reserved evaluations must remain unexecuted')
        costs.append({'report_hash': report['report_hash'], 'sample_count': expected,
                      'learning_wall_ns': report['whole_study_wall_ns'],
                      'generation_work': report['generation_work']})
    if len({s['sample_hash'] for s in samples}) != 165 or len(groups) != 5:
        raise ValueError('165 unique original samples in five groups required')
    return combined, samples, profile, groups, costs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-labels', required=True, type=Path)
    parser.add_argument('--new-labels', required=True, type=Path)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--fit-solver', choices=(learning.SVD_RIDGE_FIT_PROFILE,
                        learning.CONSTANT_SAFE_SVD_FIT_PROFILE),
                        default=learning.SVD_RIDGE_FIT_PROFILE)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    started = perf_counter_ns()
    cases, samples, profile, groups, costs = inputs(args.old_labels, args.new_labels)
    if args.preflight_only:
        print({'cases': len(cases), 'samples': len(samples), 'groups': len(groups),
               'planned_folds': 90, 'planned_full_paths': 360, 'fits': 0, 'solver_calls': 0})
        return
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes({
        'source_revision': args.source_revision,
        'fit_solver_profile': args.fit_solver,
        'input_inventories': {'old': PINS['labels'], 'new': NEW_INVENTORY},
        'source_sample_hashes': [s['sample_hash'] for s in samples],
        'groups': groups, 'ridge_grid': [1e4, 1e6], 'repetitions': 3,
        'planned_folds': 90, 'planned_full_paths': 360,
        'maximum_selection_fits': 31, 'maximum_selection_core_calls': 6840,
        'pooled_metadata_fit_count': 1, 'minimum_relative_improvement': 0.01,
        'historical_label_costs_separate': costs,
        'arithmetic_profile': ARITHMETIC, 'labels_regenerated': False,
        'reserved_evaluation_executed': False, 'independent_project_provenance': False,
        'parallel_timing_runs': False,
    }))
    # This fit binds the pooled policy schema; its weights/scales are not used
    # in withheld fits. Every selection fold refits only its complementary group.
    fitting = perf_counter_ns()
    policy = learning._fit(samples, profile, 1e4, 0.1, fit_solver=args.fit_solver)
    metadata_fit_wall_ns = perf_counter_ns() - fitting
    _save(root, 'pooled-policy.json', _bytes(policy.to_dict()))
    _save(root, 'pooled-fit.json', _bytes({'wall_ns': metadata_fit_wall_ns,
                                        'policy_hash': policy.policy_hash,
                                        'sample_count': len(samples), 'promoted': False}))
    result = run_rc_control_runtime_selection(
        cases, samples, policy, source_revision=args.source_revision,
        output_directory=root / 'selection', ridge_grid=(1e4, 1e6), repetitions=3,
        maximum_fits=31, maximum_core_calls=6840, arithmetic_profile=ARITHMETIC,
        withholding_strategy='connected_training_groups',
        proposal_abstention_strategy='secant', static_model_abstention=True,
    )
    _save(root, 'outcome.json', _bytes({
        'selection_result_hash': result['result_hash'],
        'selected_strategy': result['selected_strategy'],
        'parent_wall_ns_before_outcome_write': perf_counter_ns() - started,
        'pooled_metadata_fit_wall_ns': metadata_fit_wall_ns,
        'historical_label_costs_separate': costs,
        'reserved_evaluation_executed': False, 'net_savings_proved': False,
    }))
    print({'root': str(root), 'selected_strategy': result['selected_strategy']})


if __name__ == '__main__':
    main()
