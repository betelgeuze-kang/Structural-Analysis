"""Audit retained-label runtime receipts without fitting or executing a solver."""
import argparse
import hashlib
from pathlib import Path

from audit_grouped_rc_runtime_campaign import checked, read, require


def audit(study, label_bundle):
    source = read(study / 'training-source.json')
    raw = (label_bundle / 'inventory.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == source['original_inventory_sha256'],
            'original label inventory changed')
    index = {r['path']: r for r in read(label_bundle / 'inventory.json')['files']}
    for name in ('coverage-plan.json', 'labels/learning-study.json',
                 'labels/training-samples.json', 'labels/policy.json'):
        raw = (label_bundle / 'study' / name).read_bytes()
        row = index['study/' + name]
        require(len(raw) == row['byte_length'] and
                hashlib.sha256(raw).hexdigest() == row['sha256'], 'label input changed')
    original = label_bundle / 'study'
    coverage = checked(original / 'coverage-plan.json', 'plan_hash')
    labels = checked(original / 'labels/learning-study.json', 'report_hash')
    policy = checked(original / 'labels/policy.json', 'policy_hash')
    samples = read(original / 'labels/training-samples.json')
    root = study / 'selection'
    plan = checked(root / 'plan.json', 'plan_hash')
    result = checked(root / 'result.json', 'result_hash')
    outcome = read(study / 'campaign-outcome.json')
    require(source['label_plan_hash'] == coverage['plan_hash'] and
            source['learning_report_hash'] == labels['report_hash'], 'label bindings')
    require(source['label_source_revision'] == coverage['source_revision'] ==
            labels['source_revision'], 'label source revisions')
    require(source['source_revision'] == plan['source_revision'] == result['source_revision'],
            'runtime source revisions')
    require(outcome['selection_result_hash'] == result['result_hash'] and
            result['plan_hash'] == plan['plan_hash'], 'runtime bindings')
    require(plan['source_policy_hash'] == policy['policy_hash'], 'source policy binding')
    require(len(samples) == 99 and all(r['labels_eligible'] for r in labels['generation']),
            'complete source labels required')
    require(labels['evaluation_deferred'] and not labels['evaluation_work']['unknown_work']
            and all(v == 0 for v in labels['evaluation_work']['known_work'].values()),
            'evaluation work must be zero')
    require(not result['validation_or_holdout_execution'] and
            not outcome['reserved_evaluation_executed'], 'reserved execution')
    train = {c['case_id'] for c in coverage['cases'] if c['split'] == 'train'}
    require(train == {s['case_id'] for s in samples} == set(plan['training_case_order']),
            'training roster')
    require(set(plan['source_sample_hashes']) == {s['sample_hash'] for s in samples},
            'source sample roster')
    groups = plan['training_exclusion_groups']['groups']
    require(len(groups) == 3 and all(len(g) == 3 for g in groups) and
            {x for g in groups for x in g} == train, 'three complete geometry groups')
    require(plan['ridge_grid'] == source['ridge_grid'] == [1e4, 1e6] and
            plan['repetitions'] == source['repetitions'] == 3, 'predeclared grid')
    expected_roster = {(c, r, n) for c in train for r in plan['ridge_grid'] for n in range(3)}
    actual_roster = [(f['withheld_training_case'], f['ridge'], f['repetition_index'])
                     for f in result['folds']]
    require(len(actual_roster) == 54 and set(actual_roster) == expected_roster,
            'complete unique fold roster')
    work = dict.fromkeys(('core_calls', 'newton_iterations', 'linear_solves'), 0)
    proposed = abstained = 0
    gate_counts = {}
    case_counts = {}
    for f in result['folds']:
        stem = f"fold-{f['index']:04d}"
        require(read(root / (stem + '-outcome.json')) == f, 'persisted fold mismatch')
        p = checked(root / f"fit-{f['fit_index']:04d}-policy.json", 'policy_hash')
        require(p['policy_hash'] == f['policy_hash'], 'frozen policy binding')
        group = next(g for g in groups if f['withheld_training_case'] in g)
        expected = {s['sample_hash'] for s in samples if s['case_id'] not in group}
        require(len(expected) == len(p['training_sample_hashes']) == 66 and
                set(p['training_sample_hashes']) == expected, 'excluded-group leakage')
        require(f['arm_order'] == plan['arm_order_schedule'][f['repetition_index']],
                'counterbalanced arm order')
        score = f['score']
        require(f['status'] == 'completed' and score['full_comparison_pass'] and
                not score['execution_work']['unknown_work'], 'incomplete fold')
        report = checked(root / stem / 'comparison.json', 'report_hash')
        require(report['report_hash'] == f['report_hash'] and
                report['proposal_identity'] == p['policy_hash'], 'comparison binding')
        require(report['absolute_tolerance'] == 1e-10 and report['relative_tolerance'] == 1e-8
                and all(c['full_history_pass'] for c in report['comparisons'].values()),
                'full histories at original tolerance required')
        actual_work = dict.fromkeys(work, 0)
        for arm in [*report['arms'].values(), report['fresh_reference']]:
            require(arm['status'] == 'complete' and arm['accepted_target_count'] == 12,
                    'all four full paths required')
            invocations = list(arm['preload_invocations'])
            invocations.extend(i for e in arm['entries'] for i in e['invocations'])
            for invocation in invocations:
                require(not invocation['unknown_work'], 'unknown invocation work')
                for key in actual_work:
                    actual_work[key] += invocation['work'][key]
        require(actual_work == score['execution_work']['known_work'], 'invocation cost sum')
        decisions = read(root / (stem + '-decisions.json'))
        require(sum(d['decision'] == 'proposed' for d in decisions) == score['proposed_count']
                and sum(d['decision'].startswith('abstained') for d in decisions) ==
                score['abstained_count'], 'proposal decision count')
        proposed += score['proposed_count']
        abstained += score['abstained_count']
        by_case = case_counts.setdefault(f['withheld_training_case'],
                                        {'proposed': 0, 'abstained': 0})
        by_case['proposed'] += score['proposed_count']
        by_case['abstained'] += score['abstained_count']
        for k in work:
            work[k] += score['execution_work']['known_work'][k]
        gate = read(root / (stem + '-model-gate.json'))
        gate_counts[gate['status']] = gate_counts.get(gate['status'], 0) + 1
    require(source['original_generation_work'] == labels['generation_work'] and
            source['original_label_study_wall_ns'] == labels['whole_study_wall_ns'] ==
            outcome['label_study_wall_ns_separate'], 'separate label cost binding')
    return {
        'source_revision': result['source_revision'], 'selection_result_hash': result['result_hash'],
        'label_source_revision': source['label_source_revision'],
        'label_inventory_sha256': source['original_inventory_sha256'],
        'completed_folds': len(actual_roster), 'exclusion_groups': groups,
        'training_sample_count': len(samples), 'fit_completed_count': result['fit_completed_count'],
        'proposed_count': proposed, 'abstained_count': abstained, 'case_counts': case_counts,
        'static_gate_counts': gate_counts, 'fold_work': work,
        'label_generation_work': labels['generation_work'],
        'label_study_wall_ns_separate': labels['whole_study_wall_ns'],
        'selection_wall_ns': result['wall_ns'],
        'parent_wall_ns': outcome['parent_wall_ns_before_outcome_write'],
        'candidates': result['candidates'], 'selected_strategy': result['selected_strategy'],
        'selected_ridge': result['selected_ridge'], 'reserved_evaluation_executed': False,
        'independent_evaluation': False, 'net_savings_proved': False,
        'audit_scope': 'retained input hashes, grouped policy exclusion, complete fold roster and costs; no solver replay',
    }


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('label_bundle', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.study, args.label_bundle)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps(result, sort_keys=True))
