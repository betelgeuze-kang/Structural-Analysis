"""Recompute leave-family-out feature ranges from original complete labels."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from audit_grouped_rc_runtime_campaign import checked, digest, read, require
from structural_analysis.benchmark.rc_control_learning import RCControlSeedPolicy
from structural_analysis.benchmark.rc_control_training_diagnostics import control_policy_feature_names


def range_checks(samples, groups, names, margin):
    output = []
    for group in groups:
        fitting = [s for s in samples if s['case_id'] not in group]
        held = [s for s in samples if s['case_id'] in group]
        require(bool(fitting) and bool(held), 'nonempty complementary groups')
        low = [min(column) for column in zip(*(s['features'] for s in fitting), strict=True)]
        high = [max(column) for column in zip(*(s['features'] for s in fitting), strict=True)]
        for sample in held:
            violations = [names[i] for i, value in enumerate(sample['features'])
                          if value < low[i] - max((high[i] - low[i]) * margin, 1e-12)
                          or value > high[i] + max((high[i] - low[i]) * margin, 1e-12)]
            output.append({'case_id': sample['case_id'], 'target_index': sample['target_index'],
                           'sample_hash': sample['sample_hash'], 'excluded_group': group,
                           'fitting_sample_count': len(fitting), 'range_eligible': not violations,
                           'violating_features': violations})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--baseline-study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--recover-missing-summary', action='store_true')
    args = parser.parse_args()
    plan = checked(args.study / 'coverage-plan.json', 'plan_hash')
    labels = checked(args.study / 'labels/learning-study.json', 'report_hash')
    recovered = args.recover_missing_summary and not (args.study / 'coverage-outcome.json').exists()
    if recovered:
        outcome = {'status': 'completed', 'plan_hash': plan['plan_hash'],
                   'learning_report_hash': labels['report_hash'], 'parent_wall_ns_before_final_write': None}
    else:
        outcome = read(args.study / 'coverage-outcome.json')
    require(outcome['status'] == 'completed', 'complete labels required')
    require(outcome['plan_hash'] == plan['plan_hash'] and
            outcome['learning_report_hash'] == labels['report_hash'], 'receipt binding')
    require(labels['evaluation_deferred'] is True, 'evaluation not deferred')
    require(labels['evaluation_work']['known_work']['core_calls'] == 0 and
            not labels['evaluation_work']['unknown_work'], 'evaluation work')
    for row in labels['evaluation']:
        require(row['status'] == 'not_attempted' and
                row['reason'] == 'evaluation_explicitly_deferred', 'reserved outcome')
        require(not (args.study / 'labels' / row['case_id']).exists(), 'reserved result found')
    for row in labels['generation']:
        require(row['labels_eligible'] and all(c['full_history_pass'] for c in
                row['report']['comparisons'].values()), 'ineligible source history')
    samples = read(args.study / 'labels/training-samples.json')
    policy = checked(args.study / 'labels/policy.json', 'policy_hash')
    require(policy == labels['policy'], 'policy artifact binding')
    names = control_policy_feature_names(RCControlSeedPolicy(json.dumps(policy)))
    for s in samples:
        require(s['sample_hash'] == digest({k: v for k, v in s.items() if k != 'sample_hash'}),
                'sample hash mismatch')
        require(len(s['features']) == len(names) and all(math.isfinite(x) for x in s['features']),
                'invalid feature dimensions or values')
    require(len({s['sample_hash'] for s in samples}) == len(samples), 'duplicate sample')
    require(set(policy['training_sample_hashes']) == {s['sample_hash'] for s in samples},
            'policy training roster differs')
    actual = range_checks(samples, plan['groups'], names, plan['ood_margin'])
    if not recovered:
        require(actual == outcome['reference_parent_range_checks'], 'independent range recomputation differs')
    counts = Counter(r['case_id'] for r in actual)
    eligible = Counter(r['case_id'] for r in actual if r['range_eligible'])
    baseline_plan = checked(args.baseline_study / 'campaign-plan.json', 'plan_hash')
    baseline_labels = checked(args.baseline_study / 'labels/learning-study.json', 'report_hash')
    require(baseline_plan['plan_hash'] == plan['prior_campaign_plan_hash'], 'baseline plan binding')
    require(names == control_policy_feature_names(RCControlSeedPolicy(json.dumps(baseline_labels['policy']))), 'feature layout changed')
    baseline_samples = read(args.baseline_study / 'labels/training-samples.json')
    for s in baseline_samples:
        require(s['sample_hash'] == digest({k: v for k, v in s.items() if k != 'sample_hash'}),
                'baseline sample identity mismatch')
    require(set(baseline_labels['policy']['training_sample_hashes']) ==
            {s['sample_hash'] for s in baseline_samples}, 'baseline training roster differs')
    baseline = range_checks(baseline_samples, baseline_plan['training_groups']['groups'], names,
                            baseline_labels['policy']['ood_margin'])
    comparisons = []
    for old in baseline_samples:
        new = next(s for s in samples if s['case_id'] == old['case_id'] + '-amp100'
                   and s['target_index'] == old['target_index'])
        comparisons.append(old['features'] == new['features'])
    report = {'source_revision': plan['source_revision'], 'plan_hash': plan['plan_hash'],
              'range_summary_recovered_without_solver_or_fit': recovered,
              'sample_count': len(samples), 'range_eligible_count': sum(eligible.values()),
              'cases': [{'case_id': c, 'samples': counts[c], 'range_eligible': eligible[c]}
                        for c in sorted(counts)],
              'baseline_range_eligible_count': sum(r['range_eligible'] for r in baseline),
              'baseline_sample_count': len(baseline),
              'amplitude_one_feature_vectors_exact_count': sum(comparisons),
              'generation_work': labels['generation_work'],
              'learning_wall_ns': labels['whole_study_wall_ns'],
              'parent_wall_ns': outcome['parent_wall_ns_before_final_write'],
              'reserved_evaluation_executed': False,
              'range_eligibility_is_runtime_proposal': False, 'net_savings_proved': False}
    with args.output.open('x') as handle:
        json.dump(report, handle, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
