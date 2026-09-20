"""Add two declared synthetic training groups without replaying old labels.

This expands training coverage only. Reserved evaluations stay unexecuted.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re
from time import perf_counter_ns

from run_grouped_rc_history_coverage import AMPLITUDES, cases_with_history_coverage
from run_grouped_rc_runtime_campaign import ARITHMETIC
from run_rc_same_parent_seed_probe import PINS, reader
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save
from structural_analysis.benchmark.rc_control_learning_split import control_training_exclusion_groups
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


DECLARATIONS = (
    ('train-d', (2.7, 2.2), (-0.5, -1.5, -3, -6.2, -3, 1, 4, 5.2, 2, -2, -4.2, 0)),
    ('train-e', (3.3, 2.6), (-0.5, -1.5, -3, -7.2, -3, 1, 4, 5.8, 2, -2, -5.2, 0)),
)


def expanded_cases():
    original = cases_with_history_coverage(extended_line_search=True)
    template = json.loads((Path(__file__).resolve().parents[1] /
                           'examples/public_rc_fiber_frame_l_frame_material_history.json').read_bytes())
    new = []
    for name, lengths, millimetres in DECLARATIONS:
        payload = deepcopy(template)
        for node in payload['nodes']:
            if node['id'] == 'N2':
                node['coordinates'] = [lengths[0], 0.0, 0.0]
            elif node['id'] == 'N3':
                node['coordinates'] = [lengths[0], lengths[1], 0.0]
        model = load_neutral_json_bytes(_bytes(payload), source_path=f'memory://{name}.json')
        for suffix, scale in AMPLITUDES:
            request = replace(original[0].request,
                              targets_m=tuple(scale * v / 1000 for v in millimetres))
            new.append(learning.RCControlLearningCase(
                f'{name}-amp{suffix}', f'synthetic-{name}', f'synthetic-{name}',
                f'synthetic-{name}', 'train', model, request))
    combined = original + new
    learning._preflight(combined, ARITHMETIC)
    groups = control_training_exclusion_groups(combined)['groups']
    if len(groups) != 5 or any(len(group) != 3 for group in groups):
        raise ValueError('five separate whole training groups required')
    return original, new, combined, groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained-labels', required=True, type=Path)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    original, new, combined, groups = expanded_cases()
    retained = reader(args.retained_labels, PINS['labels'])
    prior_plan = retained('study/coverage-plan.json')
    def declarations(cases):
        return [{'case_id': c.case_id, 'split': c.split,
                 'model': c.model.canonical_payload(),
                 'request': c.request.to_dict()} for c in cases]
    if prior_plan['cases'] != declarations(original):
        raise ValueError('original cases changed')
    if len(retained('study/labels/training-samples.json')) != 99:
        raise ValueError('all 99 original labels required')
    generation_cases = new + [c for c in original if c.split != 'train']
    if args.preflight_only:
        print(json.dumps({'combined_cases': len(combined), 'groups': groups,
                          'new_training_cases': len(new), 'new_expected_samples': 66,
                          'reserved_cases_executed': 0, 'solver_calls': 0}))
        return
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes({
        'source_revision': args.source_revision, 'combined_cases': declarations(combined),
        'generation_case_ids': [c.case_id for c in new], 'groups': groups,
        'retained_labels_inventory_sha256': PINS['labels'],
        'retained_label_count': 99, 'retained_label_regeneration': False,
        'new_expected_sample_count': 66, 'independent_project_provenance': False,
        'evaluation_deferred': True, 'arithmetic_profile': ARITHMETIC,
        'purpose': 'two new interior synthetic training groups; no claim of runtime benefit',
    }))
    started = perf_counter_ns()
    report = learning.run_rc_control_learning_study(
        generation_cases, source_revision=args.source_revision, output_directory=root / 'labels',
        ridge=1e4, ood_margin=0.1, feature_profile=learning.MATERIAL_FEATURE_PROFILE,
        arithmetic_profile=ARITHMETIC, fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
        defer_evaluation=True)
    samples = json.loads((root / 'labels/training-samples.json').read_bytes())
    complete = len(samples) == 66 and all(r['labels_eligible'] for r in report['generation'])
    _save(root, 'outcome.json', _bytes({
        'complete_new_labels': complete, 'sample_count': len(samples),
        'generation_work': report['generation_work'], 'evaluation_work': report['evaluation_work'],
        'learning_report_hash': report['report_hash'],
        'learning_wall_ns': report['whole_study_wall_ns'],
        'generation_parent_wall_ns': perf_counter_ns() - started,
        'source_preflight_wall_excluded': True, 'reserved_evaluation_executed': False,
        'new_policy_is_not_promoted': True, 'net_savings_proved': False,
    }))
    print(json.dumps({'complete_new_labels': complete, 'sample_count': len(samples)}))
    if not complete:
        raise RuntimeError('incomplete new labels; original failures retained')


if __name__ == '__main__':
    main()
