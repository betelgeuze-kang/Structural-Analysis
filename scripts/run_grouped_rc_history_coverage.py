"""Predeclared training-only history coverage experiment, without evaluation paths.

Range eligibility on original reference-parent labels is a diagnostic only: it
neither executes a proposed seed nor predicts runtime benefit.
"""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

import numpy as np
from run_grouped_rc_runtime_campaign import ARITHMETIC, prepare_cases
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_learning_split import control_training_exclusion_groups

AMPLITUDES = (("050", 0.5), ("100", 1.0), ("150", 1.5))


def cases_with_history_coverage(*, extended_line_search=False):
    cases = []
    for original in prepare_cases():
        if original.split != 'train':
            cases.append(original)
            continue
        for suffix, scale in AMPLITUDES:
            cases.append(learning.RCControlLearningCase(
                f'{original.case_id}-amp{suffix}', original.project_id,
                original.geometry_family_id, original.load_history_id, original.split,
                original.model, replace(original.request,
                    targets_m=tuple(scale * x for x in original.request.targets_m)),
            ))
    if extended_line_search:
        cases = [learning.RCControlLearningCase(
            c.case_id, c.project_id, c.geometry_family_id, c.load_history_id, c.split,
            c.model, replace(c.request, solver_config=replace(c.request.solver_config,
                newton=replace(c.request.solver_config.newton,
                    line_search_alphas=tuple(2.0 ** -i for i in range(13))))),
        ) for c in cases]
    learning._preflight(cases, ARITHMETIC)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output-directory', required=True, type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--extended-line-search', action='store_true')
    args = parser.parse_args()
    if re.fullmatch('[0-9a-f]{40}', args.source_revision) is None:
        raise ValueError('exact frozen source revision required')
    started = perf_counter_ns()
    cases = cases_with_history_coverage(extended_line_search=args.extended_line_search)
    groups = control_training_exclusion_groups(cases)['groups']
    if len(groups) != 3 or any(len(g) != 3 for g in groups):
        raise ValueError('three whole geometry/history families required')
    plan = {
        'schema_version': 'rc-grouped-training-history-coverage.v2' if args.extended_line_search else 'rc-grouped-training-history-coverage.v1',
        **({'line_search_extension': {
            'prior_failed_plan_hash': 'sha256:36ee7c9d5dcaefd807c43cedc44981cbecdf37fdc2899e4808bcf7795933afaa',
            'alphas': [2.0 ** -i for i in range(13)],
            'scope': 'all_declared_requests_including_unexecuted_reserved_cases',
            'numerical_acceptance_tolerances_changed': False,
            'maximum_iterations_changed': False,
        }} if args.extended_line_search else {}),
        'source_revision': args.source_revision,
        'prior_campaign_plan_hash': 'sha256:eb3a0235184260625da8eadcef5f242d7e3f866e764e267c96a1c2289d56bd2b',
        'amplitude_multipliers': [scale for _, scale in AMPLITUDES],
        'cases': [{'case_id': c.case_id, 'split': c.split,
                   'model': c.model.canonical_payload(), 'request': c.request.to_dict()}
                  for c in cases],
        'groups': groups, 'ood_margin': 0.1, 'ridge': 1e4,
        'arithmetic_profile': ARITHMETIC, 'evaluation_deferred': True,
        'independent_project_provenance': False,
        'actual_proposal_or_runtime_claim': False,
    }
    plan['plan_hash'] = _sha(_bytes(plan))
    if args.preflight_only:
        print(json.dumps({'groups': groups, 'case_count': len(cases), 'solver_calls': 0}))
        return
    root = args.output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'coverage-plan.json', _bytes(plan))
    labels = learning.run_rc_control_learning_study(
        cases, source_revision=args.source_revision, output_directory=root / 'labels',
        ridge=plan['ridge'], ood_margin=plan['ood_margin'],
        feature_profile=learning.MATERIAL_FEATURE_PROFILE, arithmetic_profile=ARITHMETIC,
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE, defer_evaluation=True,
    )
    samples = json.loads((root / 'labels/training-samples.json').read_bytes())
    complete = labels['policy'] is not None and all(r['labels_eligible'] for r in labels['generation'])
    rows = []
    if complete:
        names = labels['policy']['material_feature_names']
        for group in groups:
            fit_rows = [s for s in samples if s['case_id'] not in group]
            held = [s for s in samples if s['case_id'] in group]
            x = np.asarray([s['features'] for s in fit_rows], dtype=float)
            low, high = x.min(axis=0), x.max(axis=0)
            slack = np.maximum((high - low) * plan['ood_margin'], 1e-12)
            for sample in held:
                value = np.asarray(sample['features'], dtype=float)
                violations = np.flatnonzero((value < low - slack) | (value > high + slack))
                rows.append({'case_id': sample['case_id'], 'target_index': sample['target_index'],
                             'sample_hash': sample['sample_hash'], 'excluded_group': group,
                             'fitting_sample_count': len(fit_rows),
                             'range_eligible': len(violations) == 0,
                             'violating_features': [names[int(i)] for i in violations]})
    outcome = {
        'schema_version': 'rc-grouped-training-history-coverage-outcome.v1',
        'plan_hash': plan['plan_hash'], 'learning_report_hash': labels['report_hash'],
        'status': 'completed' if complete else 'incomplete_labels',
        'sample_count': len(samples), 'reference_parent_range_checks': rows,
        'generation_work': labels['generation_work'], 'evaluation_work': labels['evaluation_work'],
        'learning_wall_ns': labels['whole_study_wall_ns'],
        'parent_wall_ns_before_final_write': perf_counter_ns() - started,
        'actual_runtime_proposals': None, 'net_savings_proved': False,
        'independent_validation': False,
    }
    _save(root, 'coverage-outcome.json', _bytes(outcome))
    print(json.dumps({'status': outcome['status'], 'samples': len(samples),
                      'range_eligible': sum(r['range_eligible'] for r in rows)}))
    if not complete:
        raise RuntimeError('incomplete original labels; no range conclusion authorized')


if __name__ == '__main__':
    main()
