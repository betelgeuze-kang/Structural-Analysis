"""Predeclared synthetic nonlinear tuning campaign with untouched evaluation paths.

Run from an immutable committed snapshot. This does not authenticate independent
projects and does not evaluate/promote a policy on the reserved cases.
"""
from copy import deepcopy
from dataclasses import replace
import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
)
from structural_analysis.benchmark.rc_control_runtime_selection import (
    run_rc_control_runtime_selection,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

# Coordinates and reversal ratios differ before observing any campaign results.
# IDs describe synthetic scenarios, never authenticated separate projects.
DECLARATIONS = (
    ('train-a', 'train', (2.0, 1.5), (-0.5, -1.5, -3, -6, -3, 1, 4, 6, 2, -2, -5, 0)),
    ('train-b', 'train', (3.0, 2.5), (-0.5, -1.5, -3, -7, -3, 1, 4, 6, 2, -2, -4, 0)),
    ('train-c', 'train', (4.0, 3.1), (-0.5, -1.5, -3, -8, -3, 1, 4, 5, 2, -2, -6, 0)),
    ('reserved-validation', 'validation', (2.5, 2.0), (-0.5, -1.5, -3, -6.5, -3, 1, 4, 5.5, 2, -2, -4.5, 0)),
    ('reserved-holdout', 'holdout', (3.6, 2.9), (-0.5, -1.5, -3, -7.5, -3, 1, 4, 6.5, 2, -2, -5.5, 0)),
)
ARITHMETIC = 'retained-twofold-refinement.v1'


def prepare_cases():
    source = Path(__file__).resolve().parents[1] / 'examples/public_rc_fiber_frame_l_frame_material_history.json'
    template = json.loads(source.read_bytes())
    cases = []
    for name, split, lengths, millimetres in DECLARATIONS:
        payload = deepcopy(template)
        for node in payload['nodes']:
            if node['id'] == 'N2':
                node['coordinates'] = [lengths[0], 0.0, 0.0]
            elif node['id'] == 'N3':
                node['coordinates'] = [lengths[0], lengths[1], 0.0]
        model = load_neutral_json_bytes(_bytes(payload), source_path=f'memory://{name}.json')
        request = BoundedRCFiberDirectControlRequest(
            7, tuple(v / 1000 for v in millimetres), allow_reversals=True,
            maximum_reversals=3, constant_nodal_loads=(('N3', 0.0, -20.0, 0.0),),
        )
        request = replace(request, solver_config=replace(
            request.solver_config,
            newton=replace(request.solver_config.newton, terminal_polishing=True),
        ))
        cases.append(learning.RCControlLearningCase(
            name, f'synthetic-{name}', f'synthetic-{name}', f'synthetic-{name}',
            split, model, request,
        ))
    learning._preflight(cases, ARITHMETIC)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output-directory', required=True, type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if re.fullmatch('[0-9a-f]{40}', args.source_revision) is None:
        raise ValueError('exact source revision required')
    started = perf_counter_ns()
    cases = prepare_cases()
    groups = control_training_exclusion_groups(cases)
    if groups['groups'] != [['train-a'], ['train-b'], ['train-c']]:
        raise ValueError('predeclared three distinct synthetic training groups required')
    plan = {
        'schema_version': 'synthetic-grouped-rc-runtime-campaign.v1',
        'source_revision': args.source_revision,
        'cases': [{'case_id': c.case_id, 'split': c.split,
                   'model': c.model.canonical_payload(), 'request': c.request.to_dict()}
                  for c in cases],
        'training_groups': groups,
        'ridge_grid': [1e4, 1e6], 'repetitions': 3,
        'maximum_fits': 7, 'maximum_core_calls': 1368,
        'minimum_relative_improvement': 0.01,
        'arithmetic_profile': ARITHMETIC,
        'evaluation_deferred': True,
        'independent_project_provenance': False,
        'parallel_timing_runs': False,
        'fit_and_label_costs_excluded_from_fold_ratio': True,
        'net_savings_proved': False,
    }
    plan['plan_hash'] = _sha(_bytes(plan))
    if args.preflight_only:
        print(json.dumps({'plan_hash': plan['plan_hash'], 'groups': groups['groups'],
                          'case_count': len(cases), 'solver_calls': 0}))
        return
    root = args.output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'campaign-plan.json', _bytes(plan))
    labels = learning.run_rc_control_learning_study(
        cases, source_revision=args.source_revision, output_directory=root / 'labels',
        ridge=1e4, feature_profile=learning.MATERIAL_FEATURE_PROFILE,
        arithmetic_profile=ARITHMETIC, fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
        defer_evaluation=True,
    )
    if labels['policy'] is None:
        _save(root, 'campaign-outcome.json', _bytes({
            'status': 'training_failed', 'plan_hash': plan['plan_hash'],
            'evaluation_executed': False, 'net_savings_proved': False,
        }))
        raise RuntimeError('training did not produce a policy; retain original failures')
    samples = json.loads((root / 'labels/training-samples.json').read_bytes())
    result = run_rc_control_runtime_selection(
        cases, samples, learning.RCControlSeedPolicy(_bytes(labels['policy']).decode()),
        source_revision=args.source_revision, output_directory=root / 'selection',
        ridge_grid=(1e4, 1e6), repetitions=3, maximum_fits=7, maximum_core_calls=1368,
        arithmetic_profile=ARITHMETIC, withholding_strategy='connected_training_groups',
        proposal_abstention_strategy='secant', static_model_abstention=True,
    )
    _save(root, 'campaign-outcome.json', _bytes({
        'status': 'completed', 'plan_hash': plan['plan_hash'],
        'learning_report_hash': labels['report_hash'],
        'selection_result_hash': result['result_hash'],
        'selected_strategy': result['selected_strategy'],
        'generation_work': labels['generation_work'],
        'learning_wall_ns': labels['whole_study_wall_ns'],
        'selection_wall_ns': result['wall_ns'],
        'parent_wall_ns_before_final_write': perf_counter_ns() - started,
        'evaluation_executed': False, 'net_savings_proved': False,
        'timing_repeats_are_independent_cases': False,
    }))
    print(json.dumps({'output_directory': str(root),
                      'selected_strategy': result['selected_strategy']}))


if __name__ == '__main__':
    main()
