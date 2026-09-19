"""Audit a terminal grouped campaign without executing solvers or fitting models."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(value):
    return 'sha256:' + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def checked(path, field):
    value = read(path)
    if value[field] != digest({k: v for k, v in value.items() if k != field}):
        raise ValueError(f'identity mismatch: {path}')
    return value


def require(condition, description):
    if not condition:
        raise ValueError(description)


def audit(root):
    plan = checked(root / 'campaign-plan.json', 'plan_hash')
    labels = checked(root / 'labels/learning-study.json', 'report_hash')
    selection = checked(root / 'selection/result.json', 'result_hash')
    outcome = read(root / 'campaign-outcome.json')
    selection_plan = checked(root / 'selection/plan.json', 'plan_hash')
    require(outcome['status'] == 'completed', 'terminal successful campaign required')
    require(outcome['plan_hash'] == plan['plan_hash'], 'campaign plan binding')
    require(outcome['learning_report_hash'] == labels['report_hash'], 'label report binding')
    require(outcome['selection_result_hash'] == selection['result_hash'], 'selection binding')
    require(selection['plan_hash'] == selection_plan['plan_hash'], 'selection plan binding')
    require(plan['source_revision'] == labels['source_revision'] == selection['source_revision'],
            'consistent source revision required')
    require(labels['evaluation_deferred'] is True, 'evaluation must remain deferred')
    require(not selection['validation_or_holdout_execution'], 'selection executed evaluation')
    require(not labels['evaluation_work']['unknown_work'] and
            all(v == 0 for v in labels['evaluation_work']['known_work'].values()),
            'evaluation solver work must remain zero')
    for row in labels['evaluation']:
        require(row['status'] == 'not_attempted' and
                row['reason'] == 'evaluation_explicitly_deferred', 'evaluation outcome')
        require(not (root / 'labels' / row['case_id']).exists(), 'evaluation artifacts found')
    samples = read(root / 'labels/training-samples.json')
    train_ids = {c['case_id'] for c in plan['cases'] if c['split'] == 'train'}
    require({s['case_id'] for s in samples} == train_ids, 'exact training roster')
    groups = selection_plan['training_exclusion_groups']['groups']
    require(groups == plan['training_groups']['groups'], 'group plan mismatch')
    require(len(selection['folds']) == len(train_ids) * len(plan['ridge_grid']) * plan['repetitions'],
            'complete predeclared fold roster required')
    metrics = ('core_calls', 'newton_iterations', 'linear_solves')
    work = dict.fromkeys(metrics, 0)
    gate_counts = {}
    proposed = abstained = 0
    for fold in selection['folds']:
        persisted = read(root / 'selection' / f"fold-{fold['index']:04d}-outcome.json")
        require(persisted == fold, 'fold summary differs from original outcome')
        policy = checked(root / 'selection' / f"fit-{fold['fit_index']:04d}-policy.json", 'policy_hash')
        require(policy['policy_hash'] == fold['policy_hash'], 'fold policy binding')
        excluded = next(g for g in groups if fold['withheld_training_case'] in g)
        expected = {s['sample_hash'] for s in samples if s['case_id'] not in excluded}
        require(set(policy['training_sample_hashes']) == expected, 'withheld-group leakage')
        require(len(policy['training_sample_hashes']) == len(expected), 'duplicate training samples')
        gate = read(root / 'selection' / f"fold-{fold['index']:04d}-model-gate.json")
        gate_counts[gate['status']] = gate_counts.get(gate['status'], 0) + 1
        score = fold['score']
        proposed += score['proposed_count']
        abstained += score['abstained_count']
        require(score['full_comparison_pass'] and not score['execution_work']['unknown_work'],
                'incomplete or unknown fold work')
        for key in metrics:
            work[key] += score['execution_work']['known_work'][key]
    generation = []
    for row in labels['generation']:
        require(row['labels_eligible'], 'ineligible generation retained')
        path = read(root / 'labels' / row['case_id'] / 'generation/reference/path.json')
        require(path['status'] == 'complete', 'incomplete source path')
        maxima = dict.fromkeys(('tensile_damage', 'compressive_damage', 'accumulated_plastic_strain'), 0.0)
        for response in path['response_history']:
            for fiber in response['fiber_results']:
                for key in maxima:
                    maxima[key] = max(maxima[key], fiber['material_state'].get(key, 0.0))
        generation.append({'case_id': row['case_id'], 'target_count': len(path['response_history']),
                           'maximum_material_history': maxima})
    require(not labels['generation_work']['unknown_work'], 'unknown generation work')
    return {
        'source_revision': plan['source_revision'], 'plan_hash': plan['plan_hash'],
        'selection_result_hash': selection['result_hash'],
        'reserved_evaluation_executed': False,
        'training_sample_count': len(samples), 'exclusion_groups': groups,
        'completed_folds': len(selection['folds']),
        'fit_completed_count': selection['fit_completed_count'],
        'static_gate_counts': gate_counts,
        'proposal_count': proposed, 'abstention_count': abstained,
        'fold_work': work, 'generation_work': labels['generation_work']['known_work'],
        'generation_material_history': generation,
        'candidates': selection['candidates'], 'selected_strategy': selection['selected_strategy'],
        'selected_ridge': selection['selected_ridge'],
        'learning_wall_ns': labels['whole_study_wall_ns'],
        'selection_wall_ns': selection['wall_ns'],
        'parent_wall_ns': outcome['parent_wall_ns_before_final_write'],
        'net_savings_proved': False, 'independent_validation': False,
        'audit_scope': 'stored plan, policies, labels, fold receipts and reference material histories; no solver replay',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.study.resolve())
    with args.output.open('x') as handle:
        json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({'selected_strategy': result['selected_strategy'],
                      'folds': result['completed_folds'], 'work': result['fold_work']}))


if __name__ == '__main__':
    main()
