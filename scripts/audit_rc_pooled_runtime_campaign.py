"""Audit the complete pooled runtime campaign without solves or new fitting."""
import argparse
import json
import math
from pathlib import Path
from statistics import mean

from audit_grouped_rc_runtime_campaign import checked, read, require
from run_rc_pooled_runtime_campaign import NEW_INVENTORY, PINS, inputs
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes
from structural_analysis.benchmark.rc_control_training_diagnostics import _validated_training_data


def require_report_binding(plan, case_id, report):
    cases = [c for c in plan['cases'] if c['case_id'] == case_id and c['split'] == 'train']
    require(len(cases) == 1, 'unique declared training case required')
    case = cases[0]
    require(report['source_revision'] == plan['source_revision'] and
            report['model_checksum'] == case['model_hash'] and
            report['request'] == case['request'], 'comparison model/request/source binding')


def require_fit_method(source, plan, policy):
    expected = source.get('fit_solver_profile', learning.SVD_RIDGE_FIT_PROFILE)
    require(expected in (learning.SVD_RIDGE_FIT_PROFILE, learning.CONSTANT_SAFE_SVD_FIT_PROFILE)
            and plan.get('fit_solver_profile') == expected
            and policy.get('fit_solver_profile') == expected,
            'predeclared fit method differs')


def require_observations(report, enabled):
    attempts = 0
    wall_ns = 0
    for name, arm in {**report['arms'], 'fresh-reference': report['fresh_reference']}.items():
        for entry in arm['entries']:
            expected = enabled and name == 'proposal' and entry['target_index'] > 0 and entry.get('proposal_decision') == 'proposed'
            require(('initial_residual_observation' in entry) == expected,
                    'initial observation coverage differs')
            if not expected:
                continue
            obs = entry['initial_residual_observation']
            require(obs['complete'] and obs['parent_unchanged'] and not obs['committed']
                    and not obs['candidate_selected'] and obs['newton_solves'] == 0
                    and obs['parent_hash'] == entry['parent_hash']
                    and obs['target_m'] == entry['target_m'], 'initial observation parent or authority differs')
            require([r['name'] for r in obs['rows']] == ['secant', 'proposal'],
                    'initial observation candidate roster differs')
            for row in obs['rows']:
                require(row['status'] == 'observed' and not row['unknown_work']
                        and row['assembly_attempts'] == 1
                        and math.isfinite(row['relative_residual']) and row['relative_residual'] >= 0,
                        'initial observation work or residual differs')
                attempts += 1
            require(obs['rows'][1]['initial_augmented_coordinates_m'] == entry['proposal'],
                    'observed proposal differs from solver seed')
            measured = entry['initial_residual_observation_wall_ns']
            require(type(measured) is int and measured >= obs['wall_ns'] > 0,
                    'initial observation timing differs')
            wall_ns += measured
    require(wall_ns <= report['arms']['proposal']['wall_ns'], 'observation exceeds path cost')
    return attempts, wall_ns


def audit(study, old_labels, new_labels):
    cases, samples, profile, groups, costs = inputs(old_labels, new_labels)
    source = read(study / 'plan.json')
    root = study / 'selection'
    plan = checked(root / 'plan.json', 'plan_hash')
    result = checked(root / 'result.json', 'result_hash')
    outcome = read(study / 'outcome.json')
    pooled = learning.RCControlSeedPolicy((study / 'pooled-policy.json').read_text())
    require_fit_method(source, plan, pooled.to_dict())
    require(source.get('observe_initial_residuals', False) is plan.get('observe_initial_residuals', False),
            'residual observation plan differs')
    _, _, pooled_profile = _validated_training_data(samples, pooled)
    require(pooled_profile == profile, 'pooled metadata differs')
    require(source['input_inventories'] == {'old': PINS['labels'], 'new': NEW_INVENTORY},
            'original inventories differ')
    require(source['source_revision'] == plan['source_revision'] == result['source_revision'],
            'runtime source revisions')
    require(outcome['selection_result_hash'] == result['result_hash'] and
            result['plan_hash'] == plan['plan_hash'], 'runtime bindings')
    require(plan['source_policy_hash'] == pooled.policy_hash and
            plan['source_policy_weights_and_preprocessing_used'] is False, 'pooled policy use')
    require(source['historical_label_costs_separate'] == outcome['historical_label_costs_separate'] == costs,
            'separate historical label costs differ')
    require(source['labels_regenerated'] is False and result['new_training_labels'] == 0 and
            result['validation_or_holdout_execution'] is False and
            outcome['reserved_evaluation_executed'] is False, 'unplanned training or evaluation')
    train = {c.case_id for c in cases if c.split == 'train'}
    require(len(train) == 15 and len(samples) == 165 and len(groups) == 5 and
            all(len(g) == 3 for g in groups), 'complete five-group source data required')
    require(set(plan['training_case_order']) == train and
            plan['training_exclusion_groups']['groups'] == source['groups'] == groups,
            'training exclusion roster differs')
    require(plan['source_sample_hashes'] == source['source_sample_hashes'] ==
            [s['sample_hash'] for s in samples], 'source sample identities differ')
    require(plan['ridge_grid'] == source['ridge_grid'] == [1e4, 1e6] and
            plan['repetitions'] == source['repetitions'] == 3 and
            plan['minimum_relative_improvement'] == source['minimum_relative_improvement'] == 0.01,
            'predeclared selection settings differ')
    require(sorted(c['ridge'] for c in result['candidates']) == [1e4, 1e6],
            'complete unique candidate roster required')
    expected_roster = {(c, r, n) for c in train for r in plan['ridge_grid'] for n in range(3)}
    actual_roster = [(f['withheld_training_case'], f['ridge'], f['repetition_index'])
                     for f in result['folds']]
    require(len(actual_roster) == 90 and set(actual_roster) == expected_roster,
            'complete unique fold roster')
    work = dict.fromkeys(('core_calls', 'newton_iterations', 'linear_solves'), 0)
    proposed = abstained = 0
    observation_assemblies = observation_wall_ns = 0
    gate_counts = {}
    case_counts = {}
    per_fold_arm_work = []
    for f in result['folds']:
        stem = f"fold-{f['index']:04d}"
        require(read(root / (stem + '-outcome.json')) == f, 'persisted fold mismatch')
        p = checked(root / f"fit-{f['fit_index']:04d}-policy.json", 'policy_hash')
        learning.RCControlSeedPolicy(_bytes(p).decode())
        require_fit_method(source, plan, p)
        require(p['policy_hash'] == f['policy_hash'], 'frozen policy binding')
        group = next(g for g in groups if f['withheld_training_case'] in g)
        expected = {s['sample_hash'] for s in samples if s['case_id'] not in group}
        require(len(expected) == len(p['training_sample_hashes']) == 132 and
                set(p['training_sample_hashes']) == expected, 'excluded-group leakage')
        require(f['arm_order'] == plan['arm_order_schedule'][f['repetition_index']],
                'counterbalanced arm order')
        score = f['score']
        require(f['status'] == 'completed' and score['full_comparison_pass'] and
                not score['execution_work']['unknown_work'], 'incomplete fold')
        report = checked(root / stem / 'comparison.json', 'report_hash')
        require_report_binding(plan, f['withheld_training_case'], report)
        count, duration = require_observations(report, source.get('observe_initial_residuals', False))
        observation_assemblies += count
        observation_wall_ns += duration
        require(report['arm_order'] == f['arm_order'], 'reported arm order differs')
        require(('initial_residual_observation' in report) is source.get('observe_initial_residuals', False),
                'residual observation report differs')
        require(report['report_hash'] == f['report_hash'] and
                report['proposal_identity'] == p['policy_hash'], 'comparison binding')
        require(report['absolute_tolerance'] == 1e-10 and report['relative_tolerance'] == 1e-8
                and all(c['full_history_pass'] for c in report['comparisons'].values()),
                'full histories at original tolerance required')
        actual_work = dict.fromkeys(work, 0)
        arm_work = {}
        for arm_name, arm in {**report['arms'], 'fresh-reference': report['fresh_reference']}.items():
            require(arm['status'] == 'complete' and arm['accepted_target_count'] == 12,
                    'all four full paths required')
            arm_work[arm_name] = {**dict.fromkeys(work, 0), 'wall_ns': arm['wall_ns']}
            invocations = list(arm['preload_invocations'])
            invocations.extend(i for e in arm['entries'] for i in e['invocations'])
            for invocation in invocations:
                require(not invocation['unknown_work'], 'unknown invocation work')
                for key in actual_work:
                    actual_work[key] += invocation['work'][key]
                    arm_work[arm_name][key] += invocation['work'][key]
        per_fold_arm_work.append({'fold_index': f['index'], 'case_id': f['withheld_training_case'],
                                  'ridge': f['ridge'], 'arms': arm_work})
        require(actual_work == score['execution_work']['known_work'], 'invocation cost sum')
        decisions = read(root / (stem + '-decisions.json'))
        require(sum(d['decision'] == 'proposed' for d in decisions) == score['proposed_count']
                and sum(d['decision'].startswith('abstained') for d in decisions) ==
                score['abstained_count'], 'proposal decision count')
        ratio = (report['arms']['proposal']['wall_ns'] + f['static_model_gate_wall_ns']) / report['arms']['secant']['wall_ns']
        require(math.isclose(ratio, score['proposal_over_secant_path_wall_ratio'],
                             rel_tol=1e-14), 'path and gate timing ratio')
        proposed += score['proposed_count']
        abstained += score['abstained_count']
        by_case = case_counts.setdefault(f['withheld_training_case'],
                                        {'proposed': 0, 'abstained': 0})
        by_case['proposed'] += score['proposed_count']
        by_case['abstained'] += score['abstained_count']
        for k in work:
            work[k] += score['execution_work']['known_work'][k]
        gate = checked(root / (stem + '-model-gate.json'), 'gate_hash')
        require(gate['gate_hash'] == f['static_model_gate_hash'] and
                gate['policy_hash'] == p['policy_hash'] and
                gate['problem_contract_hash'] == report['compiled_problem_contract_hash'],
                'static gate source binding')
        gate_counts[gate['status']] = gate_counts.get(gate['status'], 0) + 1
    require(observation_assemblies <= source.get('maximum_observation_assemblies', 0),
            'initial observation assembly budget exceeded')
    for candidate in result['candidates']:
        folds = [f for f in result['folds'] if f['ridge'] == candidate['ridge']]
        equal_case_mean = mean(mean(f['score']['proposal_over_secant_path_wall_ratio']
                                    for f in folds if f['withheld_training_case'] == case)
                               for case in train)
        require(math.isclose(equal_case_mean, candidate['score'], rel_tol=1e-14),
                'equal-case selection score')
        require(candidate['proposed_count'] == sum(f['score']['proposed_count'] for f in folds),
                'candidate proposal count')
    eligible = [c for c in result['candidates'] if c['proposed_count'] > 0 and
                c['score'] < 1 - plan['minimum_relative_improvement']]
    winner = min(eligible, key=lambda c: (c['score'], -c['ridge'])) if eligible else None
    require(result['selected_strategy'] == ('learned_svd' if winner else 'secant') and
            result['selected_ridge'] == (winner['ridge'] if winner else None),
            'predeclared selection decision')
    fits = result['fit_records']
    require(len(fits) == result['fit_attempt_count'] == result['fit_completed_count'] and
            len(fits) == (31 if winner else 30), 'complete fit denominator required')
    for index, fit in enumerate(fits):
        require(fit['index'] == index and fit['status'] == 'completed' and
                read(root / f'fit-{index:04d}-outcome.json') == fit, 'fit receipt differs')
        require(type(fit['wall_ns']) is int and fit['wall_ns'] > 0, 'finite fit cost required')
    metadata = read(study / 'pooled-fit.json')
    require(metadata['policy_hash'] == pooled.policy_hash and metadata['sample_count'] == 165 and
            type(metadata['wall_ns']) is int and metadata['wall_ns'] > 0 and
            metadata['wall_ns'] == outcome['pooled_metadata_fit_wall_ns'], 'pooled fit cost binding')
    require(work['core_calls'] <= source['maximum_selection_core_calls'] == 6840 and
            plan['maximum_fits'] == source['maximum_selection_fits'] == 31,
            'predeclared work budget differs')
    if winner:
        selected = learning.RCControlSeedPolicy(_bytes(result['selected_policy']).decode())
        require_fit_method(source, plan, selected.to_dict())
        _validated_training_data(samples, selected)
    else:
        require(result['selected_policy'] is None, 'unexpected selected policy')
    return {'source_revision': result['source_revision'], 'selection_result_hash': result['result_hash'],
            'completed_folds': len(actual_roster), 'groups': groups, 'sample_count': 165,
            'observation_assembly_attempts': observation_assemblies,
            'observation_wall_ns': observation_wall_ns,
            'fold_work': work, 'proposed_count': proposed, 'abstained_count': abstained,
            'case_counts': case_counts, 'static_gate_counts': gate_counts,
            'per_fold_arm_work': per_fold_arm_work, 'candidates': result['candidates'],
            'selected_strategy': result['selected_strategy'], 'selected_ridge': result['selected_ridge'],
            'selection_fit_count': len(fits), 'selection_fit_wall_ns_sum': sum(f['wall_ns'] for f in fits),
            'pooled_metadata_fit_wall_ns': metadata['wall_ns'],
            'historical_label_costs_separate': costs, 'selection_wall_ns': result['wall_ns'],
            'parent_wall_ns': outcome['parent_wall_ns_before_outcome_write'],
            'reserved_evaluation_executed': False, 'independent_evaluation': False,
            'net_savings_proved': False, 'audit_solver_calls': 0, 'audit_fits': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('old_labels', type=Path)
    parser.add_argument('new_labels', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.study, args.old_labels, args.new_labels)
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print({k: v for k, v in result.items() if k not in ('per_fold_arm_work', 'candidates')})
