"""Read-only byte, work, and scoped-price audit of a pin/roller budget packet.

The auditor rereads original files after the numerical subprocesses have ended.
It does not rerun an independent solver or qualify the synthetic price schedule.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from copy import deepcopy

MODEL = Path('examples/research/rc_reuse_campaign/pin-roller-steel-plastic.model.json')
REQUEST = Path('examples/research/rc_reuse_campaign/pin-roller-steel-plastic.request.json')
PRIOR_PAIR = Path('docs/engineering/rc-pin-roller-design-pair-20260929.audit.json')
LEGACY_RANKING = 'feasibility_then_price.v1'
BOUNDARY_RANKING = 'feasibility_then_cheaper_boundary.v1'

def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()

def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key in {path}: {key}')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError(f'non-finite JSON token in {path}: {value}')
    return json.loads(path.read_bytes(), object_pairs_hook=unique, parse_constant=nonfinite)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def check_hash_object(value, key):
    return value[key] == sha(canonical({k: v for k, v in value.items() if k != key}))

def check_frozen_ranking(pre, search_plan, check):
    """Audit this declared six-model schedule against preserved predictions.

    These are case-specific expected orders, not a second ranking implementation.
    The experiment runner calls the production candidate-ranking function.
    """
    strategy = pre.get('ranking_strategy')
    check(strategy in (LEGACY_RANKING, BOUNDARY_RANKING), 'unsupported frozen ranking strategy')
    price = search_plan['plans']['price_order']
    learned = search_plan['plans']['learned_order']
    check(price['ordering'] == ['w34','w38','w46','w50','w54'], 'price ordering unexpected')
    check(price['shortlist'] == ['w34','w38'], 'price shortlist unexpected')
    predictions = search_plan['predictions']
    check([r['candidate_id'] for r in predictions] == ['w34','w38','w46','w50','w54'], 'prediction roster unexpected')
    if strategy == LEGACY_RANKING:
        check(search_plan['schema_version'] == 'experimental-rc-control-candidate-search-plan.v2', 'legacy search plan schema changed')
        check('ranking' not in search_plan, 'legacy plan unexpectedly contains boundary ranking')
        check(learned['ordering'] == ['w50','w54','w34','w38','w46'], 'legacy learned ordering unexpected')
        check(learned['shortlist'] == ['w50','w54'], 'legacy learned shortlist unexpected')
        return
    if strategy != BOUNDARY_RANKING:
        return
    check(search_plan['schema_version'] == 'experimental-rc-control-candidate-search-plan.v3', 'boundary search plan schema changed')
    check(learned['ordering'] == ['w50','w46','w38','w34','w54'], 'boundary learned ordering unexpected')
    check(learned['shortlist'] == ['w50','w46'], 'boundary learned shortlist unexpected')
    ranking = search_plan.get('ranking')
    check(isinstance(ranking, dict), 'boundary ranking explanation missing')
    if not isinstance(ranking, dict):
        return
    check(ranking.get('strategy') == BOUNDARY_RANKING, 'boundary ranking strategy mismatch')
    check(ranking.get('predicted_feasible_seed_id') == 'w50', 'boundary seed mismatch')
    check(ranking.get('fallback_reason') is None, 'unexpected boundary fallback')
    check(ranking.get('uncertainty_calibrated') is False, 'boundary score falsely claims calibration')
    check(ranking.get('physical_result_authority') is False, 'boundary score falsely claims physical authority')
    expected_roles = {
        'w34': 'cheaper_predicted_boundary',
        'w38': 'cheaper_predicted_boundary',
        'w46': 'cheaper_predicted_boundary',
        'w50': 'predicted_feasible_seed',
        'w54': 'remaining_legacy_order',
    }
    explanations = ranking.get('rows')
    check(isinstance(explanations, list), 'boundary ranking rows missing')
    if not isinstance(explanations, list):
        return
    check([r.get('candidate_id') for r in explanations] == list(expected_roles), 'boundary ranking row order changed')
    if len(explanations) != len(predictions):
        return
    for predicted, explained in zip(predictions, explanations):
        cid = predicted['candidate_id']
        check(explained.get('role') == expected_roles[cid], f'{cid} boundary role mismatch')
        screens = predicted['predicted_screens']
        expected_score = None if screens is None else max(
            (screen['value'] - screen['limit']) / screen['value']
            if screen['value'] > screen['limit'] else 0.0
            for screen in screens.values()
        )
        score = explained.get('relative_exceedance')
        check(
            (expected_score is None and score is None)
            or (type(score) in (int, float) and math.isfinite(score)
                and math.isclose(score, expected_score, rel_tol=0, abs_tol=1e-15)),
            f'{cid} boundary score differs from frozen prediction',
        )

def derived_performance(result, request):
    """Recompute design metrics from this row's original accepted solver history."""
    history = result['response_history']
    if request.get('constant_nodal_loads'):
        history = [result['preload_response'], *history]
    if not history:
        raise ValueError('accepted solver history is empty')
    points = [point for response in history for point in response['fiber_results']]
    steel = [p['material_state'] for p in points if p['material_kind'] == 'steel']
    concrete = [p['material_state'] for p in points if p['material_kind'] == 'concrete']
    return {
        'maximum_translation_m': max(math.hypot(node['UX_m'], node['UY_m'], node['UZ_m']) for response in history for node in response['node_displacements']),
        'maximum_absolute_fiber_strain': max(abs(p['strain']) for p in points),
        'terminal_maximum_translation_m': max(math.hypot(node['UX_m'], node['UY_m'], node['UZ_m']) for node in history[-1]['node_displacements']),
        'terminal_maximum_absolute_fiber_strain': max(abs(p['strain']) for p in history[-1]['fiber_results']),
        'maximum_steel_accumulated_plastic_strain': max((p['accumulated_plastic_strain'] for p in steel), default=None),
        'maximum_concrete_tensile_damage': max((p['tensile_damage'] for p in concrete), default=None),
        'maximum_concrete_compressive_damage': max((p['compressive_damage'] for p in concrete), default=None),
        'terminal_load_factor': history[-1]['load_factor'],
        'minimum_load_factor': min(response['load_factor'] for response in history),
        'maximum_load_factor': max(response['load_factor'] for response in history),
        'accepted_epoch_count': len(history),
    }

def verified_row_claim_violations(row, result, comparison, request):
    """Check saved row claims against its own result, not another solver arm."""
    performance = derived_performance(result, request)
    limits = {**comparison['history_limits'], **comparison['material_limits']}
    if comparison['terminal_limits'] is not None:
        limits.update({f'terminal_{key}': value for key, value in comparison['terminal_limits'].items()})
    screens = {
        key: {
            'value': performance[key],
            'limit': limit,
            'status': 'unavailable' if performance[key] is None else 'pass' if performance[key] <= limit else 'fail',
        }
        for key, limit in limits.items()
    }
    violations = []
    if canonical(row['performance']) != canonical(performance):
        violations.append('performance differs from original result history')
    if canonical(row['screens']) != canonical(screens):
        violations.append('screens differ from original result and frozen limits')
    eligible = all(screen['status'] == 'pass' for screen in screens.values())
    if type(row['selection_eligible']) is not bool or row['selection_eligible'] is not eligible:
        violations.append('selection eligibility differs from original result screens')
    return violations

def audit_packet(SOURCE, ROOT):
    SOURCE, ROOT = Path(SOURCE).resolve(), Path(ROOT).resolve()
    violations = []
    def check(condition, reason):
        if not condition:
            violations.append(reason)
    pre = load(ROOT/'plan.json')
    check((ROOT/'plan.sha256').read_text().split()[0] == sha((ROOT/'plan.json').read_bytes()), 'frozen plan hash mismatch')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip()
    check(pre['source_revision'] == revision, 'source revision mismatch')
    check(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=SOURCE, text=True).strip(), 'source checkout is not clean')
    source_model = SOURCE/MODEL
    source_request = SOURCE/REQUEST
    check(sha(source_model.read_bytes()) == pre['source_model_sha256'], 'source model bytes changed')
    check(sha(source_request.read_bytes()) == pre['source_request_sha256'], 'source request bytes changed')
    check(sha((SOURCE/PRIOR_PAIR).read_bytes()) == pre['prior_pair_audit_sha256'], 'prior pair byte binding changed')
    if pre['schema'] == 'synthetic-pin-roller-v4-candidate-budget-predeclaration.v1':
        check(sha((ROOT/'prepare.py').read_bytes()) == pre['preparation_script_sha256'], 'preparation script changed')
    elif pre['schema'] == 'synthetic-pin-roller-v4-candidate-budget-predeclaration.v2':
        check(sha((SOURCE/'scripts/run_rc_pin_roller_budget_study.py').read_bytes()) == pre['runner_sha256'], 'runner source changed')
    else:
        check(False, 'unsupported frozen plan schema')
    for name, expected in pre['input_sha256'].items():
        check(sha((ROOT/'inputs'/name).read_bytes()) == expected, f'input changed: {name}')
    check((ROOT/'inputs/request.json').read_bytes() == source_request.read_bytes(), 'request differs from authored source')
    train_widths, online_widths = pre['training_widths_m'], pre['online_widths_m']
    check(not set(train_widths) & set(online_widths), 'training/online widths overlap')
    check(len(online_widths) >= 4 and pre['full_analysis_budget_per_online_arm_including_baseline'] < len(online_widths), 'pool/budget mismatch')
    request = load(ROOT/'inputs/request.json')
    expected_targets = request['targets_m']
    expected_supports = {('N2','UX'),('N2','UY'),('N6','UY')}
    train = load(ROOT/'training/training.json')
    policy = load(ROOT/'training/policy.json')
    train_plan = load(ROOT/'training/plan.json')
    search_plan = load(ROOT/'search/plan.json')
    search_policy = load(ROOT/'search/policy.json')
    search_training = load(ROOT/'search/historical-training.json')
    search = load(ROOT/'search/result.json')
    check(check_hash_object(train,'report_hash'), 'training report internal hash mismatch')
    check(check_hash_object(policy,'policy_hash'), 'policy internal hash mismatch')
    check(check_hash_object(search_plan,'plan_hash'), 'search plan internal hash mismatch')
    check(check_hash_object(search_policy,'policy_hash'), 'search policy internal hash mismatch')
    check(check_hash_object(search_training,'report_hash'), 'search historical training internal hash mismatch')
    check(check_hash_object(search,'report_hash'), 'search report internal hash mismatch')
    check(search['plan_hash'] == search_plan['plan_hash'], 'search report plan hash mismatch')
    check(search['source_revision'] == search_plan['source_revision'] == pre['source_revision'], 'search source revision mismatch')
    check(train['policy_hash'] == search['historical_training_cost']['policy_hash'] == policy['policy_hash'], 'training/policy binding mismatch')
    check(train['report_hash'] == search['historical_training_cost']['report_hash'], 'historical training receipt mismatch')
    check(search['historical_training_cost'] == train, 'search embedded training report differs from original')
    check(search_plan['policy_hash'] == search_policy['policy_hash'] == policy['policy_hash'], 'search plan policy hash mismatch')
    check(search_plan['training_report_hash'] == search_training['report_hash'] == train['report_hash'], 'search plan training report hash mismatch')
    check((ROOT/'search/policy.json').read_bytes() == (ROOT/'training/policy.json').read_bytes(), 'search policy bytes differ from training original')
    check((ROOT/'search/historical-training.json').read_bytes() == (ROOT/'training/training.json').read_bytes(), 'search historical training bytes differ from training original')
    check(train_plan['source_revision'] == train['source_revision'] == pre['source_revision'], 'training source revision mismatch')
    check(train_plan['context_hash'] == policy['context_hash'] and train_plan['training_model_identities'] == policy['training_model_identities'], 'training plan/policy context or model identity mismatch')
    check(train['label_comparison_hash'] == policy['label_comparison_hash'] == search_policy['label_comparison_hash'], 'training policy label comparison hash mismatch')
    check(set(train_plan['training_model_identities']).isdisjoint({r['model_identity'] for r in search_plan['pool']}), 'physical model identity overlap')
    check(search_plan['control_request'] == request, 'search control request differs')
    check(search_plan['full_analysis_budget_per_arm'] == pre['full_analysis_budget_per_online_arm_including_baseline'], 'online budget changed')
    check(search_plan['oracle_after_online_arms'] is True, 'oracle ordering contract missing')
    check(search_plan.get('line_search_assembly_reuse') is None and search_plan.get('design_execution_policy') is None, 'optimization switch enabled')
    check(len(search_plan['pool']) == len(online_widths), 'online pool incomplete')
    check(search['candidate_denominator'] == len(online_widths), 'result denominator mismatch')
    check_frozen_ranking(pre, search_plan, check)
    training_experiment = load(ROOT/'inputs/training-experiment.json')
    online_experiment = load(ROOT/'inputs/online-experiment.json')
    for field, expected in (('history_limits', online_experiment['history_limits']), ('material_limits', online_experiment['material_history_limits']), ('terminal_limits', online_experiment['terminal_limits'])):
        check(canonical(search_plan[field]) == canonical(expected), f'search {field} differs from frozen input')
    price_input = online_experiment['prices']
    normalized_price = {
        **price_input,
        'concrete_per_m3': float(price_input['concrete_per_m3']),
        'rebar_per_kg': float(price_input['rebar_per_kg']),
    }
    expected_price_hash = sha(canonical({'schema_version': 'declared-rc-material-prices.v1', **normalized_price}))
    check(search_plan['price_table_hash'] == expected_price_hash, 'search price hash differs from frozen input table')
    online_base = load(ROOT/'inputs/online-model.json')
    training_base = load(ROOT/'inputs/training-model.json')
    source_base = load(source_model)
    for baseline, width in ((online_base, online_widths[0]), (training_base, train_widths[0])):
        expected = deepcopy(source_base)
        expected['sections'][0]['width_m'] = width
        expected['metadata']['case_id'] = f'synthetic-pin-roller-v4-budget-width-{width:.2f}'
        check(baseline == expected, 'generated baseline differs from the committed source model')
    for index, width in enumerate(online_widths):
        cid = 'baseline' if index == 0 else f'w{round(width*100):02d}'
        expected = deepcopy(online_base)
        expected['sections'][0]['width_m'] = width
        pool_row = search_plan['pool'][index]
        ref = pool_row['model_artifact']
        model_path = ROOT/'search'/ref['path']
        check(pool_row['candidate_id'] == cid and ref['path'] == f'pool/{cid}.json', f'{cid} pool identity mismatch')
        if not model_path.resolve().is_relative_to((ROOT/'search').resolve()):
            check(False, f'{cid} pool model escapes packet')
            continue
        check(len(model_path.read_bytes()) == ref['byte_length'] and sha(model_path.read_bytes()) == ref['sha256'], f'{cid} pool model byte mismatch')
        check(load(model_path) == expected, f'{cid} pool model physical change mismatch')
    for index, width in enumerate(train_widths):
        cid = 'baseline' if index == 0 else f'w{round(width*100):02d}'
        expected = deepcopy(training_base)
        expected['sections'][0]['width_m'] = width
        check(load(ROOT/'training'/'labels'/cid/'model.json') == expected, f'{cid} training model physical change mismatch')

    categories = {'training_labels': ROOT/'training/labels', 'price_order': ROOT/'search/price_order', 'learned_order': ROOT/'search/learned_order', 'exhaustive_oracle': ROOT/'search/exhaustive_oracle'}
    rows = {}
    summary = {}
    artifact_count = 0
    comparison_hashes = {}
    required_roles = {'analysis_outcome', 'analysis_started', 'checkpoint', 'model', 'result', 'verification', 'verification_outcome', 'verification_started'}
    for name, directory in categories.items():
        comparison = load(directory/'comparison.json')
        expected_experiment = training_experiment if name == 'training_labels' else online_experiment
        expected_limits = {
            'history_limits': expected_experiment['history_limits'],
            'material_limits': expected_experiment['material_history_limits'],
            'terminal_limits': None if name == 'training_labels' else expected_experiment['terminal_limits'],
        }
        for field, expected in expected_limits.items():
            check(canonical(comparison[field]) == canonical(expected), f'{name} {field} differs from frozen input')
        check(check_hash_object(comparison,'report_hash'), f'{name} comparison internal hash mismatch')
        comparison_hashes[name] = comparison['report_hash']
        check(comparison['status'] == 'complete', f'{name} comparison incomplete')
        check(comparison['control_request'] == request, f'{name} request mismatch')
        check(comparison['source_revision'] == pre['source_revision'], f'{name} source revision mismatch')
        if name != 'training_labels':
            check(comparison['price_table_hash'] == search_plan['price_table_hash'], f'{name} common price table mismatch')
        category_rows = {}
        counters = {'attempted_step_count':0,'known_linear_solve_count':0,'known_newton_iteration_count':0,'unknown_solver_work_attempt_count':0}
        unknown_ids = []
        failed_ids = []
        for row in comparison['rows']:
            cid = row['candidate_id']
            check(cid not in category_rows, f'{name} duplicate candidate ID')
            category_rows[cid] = row
            if name != 'training_labels' and row['material_estimate'] is not None:
                estimate = row['material_estimate']
                check(estimate['price_table_hash'] == search_plan['price_table_hash'] and estimate['currency'] == 'KRW' and estimate['scope'] == 'gross_concrete_and_straight_authored_longitudinal_rebar.v1', f'{name}/{cid} price or quantity basis mismatch')
            if row['status'] != 'verified' or row['failure'] is not None or row['full_reference_verification_pass'] is not True:
                failed_ids.append(cid)
            if set(row['artifacts']) != required_roles:
                check(False, f'{name}/{cid} artifact phase roster mismatch')
                unknown_ids.append(cid)
                continue
            for role, ref in row['artifacts'].items():
                expected_name = role.replace('_', '-') + '.json'
                check(ref['path'] == f'{cid}/{expected_name}', f'{name}/{cid}/{role} artifact path mismatch')
                file = directory/ref['path']
                if not file.resolve().is_relative_to(directory.resolve()):
                    check(False, f'{name}/{cid}/{role} reference escapes packet')
                    continue
                if not file.is_file():
                    check(False, f'{name}/{cid}/{role} missing')
                    continue
                raw = file.read_bytes()
                artifact_count += 1
                check(len(raw) == ref['byte_length'] and sha(raw) == ref['sha256'], f'{name}/{cid}/{role} byte mismatch')
            invocations = row.get('invocations')
            phase_roster_ok = (
                isinstance(invocations, list)
                and len(invocations) == 2
                and [inv.get('phase') for inv in invocations if isinstance(inv, dict)] == ['analysis', 'verification']
            )
            check(phase_roster_ok, f'{name}/{cid} missing or reordered analysis/verification invocations')
            work_unknown = not phase_roster_ok
            if phase_roster_ok:
                for phase, invocation in zip(('analysis', 'verification'), invocations):
                    started = load(directory/row['artifacts'][f'{phase}_started']['path'])
                    outcome = load(directory/row['artifacts'][f'{phase}_outcome']['path'])
                    check(started == {'phase': phase, 'status': 'started', 'unknown_execution_work': True, 'work': None}, f'{name}/{cid}/{phase} start record mismatch')
                    check(outcome == invocation, f'{name}/{cid}/{phase} outcome differs from comparison invocation')
                    work = invocation.get('work')
                    valid_work = (
                        invocation.get('status') == 'returned'
                        and invocation.get('unknown_execution_work') is False
                        and type(invocation.get('wall_ns')) is int and invocation['wall_ns'] > 0
                        and type(invocation.get('process_cpu_ns')) is int and invocation['process_cpu_ns'] >= 0
                        and isinstance(work, dict) and set(work) == set(counters)
                        and all(type(work[key]) is int and work[key] >= 0 for key in counters)
                        and work['unknown_solver_work_attempt_count'] == 0
                        and work['attempted_step_count'] > 0
                        and work['known_linear_solve_count'] > 0
                        and work['known_newton_iteration_count'] > 0
                    )
                    check(valid_work, f'{name}/{cid}/{phase} complete solver work is not known')
                    if not valid_work:
                        work_unknown = True
                    else:
                        for key in counters:
                            counters[key] += work[key]
            if work_unknown:
                unknown_ids.append(cid)
            if row['full_reference_verification_pass'] is True:
                result = load(directory/row['artifacts']['result']['path'])
                verification = load(directory/row['artifacts']['verification']['path'])
                check(check_hash_object(result, 'result_hash'), f'{name}/{cid} original result internal hash mismatch')
                check(result['status'] == 'ready' and result['contract_pass'] is True and result['failure'] is None and not result['unsupported_features'], f'{name}/{cid} original result is not complete')
                if phase_roster_ok:
                    check(result['metrics']['control_work'] == invocations[0]['work'], f'{name}/{cid} analysis work differs from original result')
                    check(verification['replay_control_work'] == invocations[1]['work'], f'{name}/{cid} verification work differs from original replay')
                authored = result['request']
                check(
                    all(authored.get(key) == request[key] for key in ('experimental_pin_roller_beam','control_global_dof','targets_m','allow_reversals','maximum_reversals','maximum_targets'))
                    and authored['configuration']['newton'] == request['solver_config']['newton']
                    and all(authored['configuration'][key] == request['solver_config'][key] for key in ('control_tolerance_m','load_factor_coordinate_scale_m')),
                    f'{name}/{cid} result request mismatch',
                )
                check(result['path']['accepted_target_prefix_m'] == expected_targets, f'{name}/{cid} incomplete target path')
                check(len(result['response_history']) == len(expected_targets), f'{name}/{cid} response count mismatch')
                check(all({(v['node_id'],v['dof']) for v in response['support_reactions']} == expected_supports for response in result['response_history']), f'{name}/{cid} reaction support mismatch')
                check(
                    verification['status'] == 'valid_artifact'
                    and verification['contract_pass'] is True
                    and verification['artifact_contract_pass'] is True
                    and verification['fresh_source_execution_invoked'] is True
                    and verification['solver_replay_performed'] is True
                    and verification['physical_path_complete'] is True
                    and verification['verified_result_hash'] == result['result_hash']
                    and verification['errors'] == []
                    and verification['unavailable_execution_work'] is False,
                    f'{name}/{cid} fresh replay unavailable or bound to another result',
                )
                for violation in verified_row_claim_violations(row, result, comparison, request):
                    check(False, f'{name}/{cid} {violation}')
        rows[name] = category_rows
        if name != 'training_labels':
            eligible = [row for row in comparison['rows'] if row['selection_eligible']]
            expected_selected = min(eligible, key=lambda row: (row['material_estimate']['total'], row['candidate_id']))['candidate_id'] if eligible else None
            check(comparison['selected_candidate_id'] == expected_selected, f'{name} selected result contradicts verified prices and screens')
        summary[name] = {'row_count':len(category_rows),'selected_candidate_id':comparison['selected_candidate_id'],'failed_candidate_ids':failed_ids,'unknown_work_candidate_ids':unknown_ids,'known_work':counters,'full_solver_invocations':sum(len(row['invocations']) for row in comparison['rows'])}
    check(summary['training_labels']['row_count'] == len(train_widths), 'training row count mismatch')
    check(summary['price_order']['row_count'] == summary['learned_order']['row_count'] == pre['full_analysis_budget_per_online_arm_including_baseline'], 'online actual request count mismatch')
    check(summary['exhaustive_oracle']['row_count'] == len(online_widths), 'oracle full pool incomplete')
    check(list(rows['price_order']) == ['baseline', *search_plan['plans']['price_order']['shortlist']], 'price rows differ from frozen shortlist')
    check(list(rows['learned_order']) == ['baseline', *search_plan['plans']['learned_order']['shortlist']], 'learned rows differ from frozen shortlist')
    check(list(rows['exhaustive_oracle']) == ['baseline', *search_plan['plans']['price_order']['ordering']], 'oracle rows differ from complete frozen pool')
    check(set(rows['training_labels']) == {'baseline', *[f'w{round(w*100):02d}' for w in train_widths[1:]]}, 'training row identity mismatch')
    check(all(not s['failed_candidate_ids'] and not s['unknown_work_candidate_ids'] for s in summary.values()), 'failed or unknown work present')
    check(train['label_comparison_hash'] == comparison_hashes['training_labels'], 'training label comparison hash mismatch')
    check(train['label_invocations'] == [inv for row in rows['training_labels'].values() for inv in row.get('invocations', [])], 'training label invocation ledger mismatch')
    check(search['arms']['price_order']['selected_candidate_id'] == summary['price_order']['selected_candidate_id'], 'price selection mismatch')
    check(search['arms']['learned_order']['selected_candidate_id'] == summary['learned_order']['selected_candidate_id'], 'learned selection mismatch')
    check(search['oracle']['selected_candidate_id'] == summary['exhaustive_oracle']['selected_candidate_id'], 'oracle selection mismatch')
    for name in ('price_order', 'learned_order', 'exhaustive_oracle'):
        arm = search['oracle'] if name == 'exhaustive_oracle' else search['arms'][name]
        check(arm == load(ROOT/'search'/f'{name}-outcome.json'), f'{name} arm differs from original outcome')
        check(arm['comparison_hash'] == comparison_hashes[name], f'{name} arm comparison hash mismatch')
        check(arm['comparison_path'] == f'{name}/comparison.json', f'{name} arm comparison path mismatch')
        expected_work = {
            'api_invocation_count': summary[name]['full_solver_invocations'],
            'known_counters': summary[name]['known_work'],
            'unknown_work': False,
        }
        check(arm['execution_work'] == expected_work, f'{name} arm execution work disagrees with raw invocations')
        check(arm['request_count'] == summary[name]['row_count'] and arm['status'] == 'completed' and arm['unknown_work_until_outcome'] is False, f'{name} arm incomplete or count mismatch')
        expected_ids = list(rows[name])
        check(load(ROOT/'search'/f'{name}-started.json') == {'candidate_ids': expected_ids, 'status': 'started', 'unknown_work_until_outcome': True}, f'{name} start record differs from frozen candidate order')
    for name in ('price_order', 'learned_order'):
        for cid, row in rows[name].items():
            oracle_row = rows['exhaustive_oracle'][cid]
            check(row['artifacts']['model']['sha256'] == oracle_row['artifacts']['model']['sha256'], f'{name}/{cid} model differs from oracle')
            check(row['quantities'] == oracle_row['quantities'], f'{name}/{cid} quantities differ from oracle')
            check(row['material_estimate'] == oracle_row['material_estimate'], f'{name}/{cid} scoped estimate differs from oracle')
    fit_start = load(ROOT/'training/fit-started.json')
    fit_outcome = load(ROOT/'training/fit-outcome.json')
    check(fit_start == {'status':'started','unknown_fit_work_until_outcome':True}, 'training fit start record mismatch')
    check(fit_outcome == train['fit'], 'training fit outcome differs from training report')
    check(fit_outcome['status'] == 'completed' and fit_outcome['unknown_fit_work_until_outcome'] is False and fit_outcome['method'] == train_plan['fit_method'], 'training fit incomplete or method changed')
    check(all(type(fit_outcome[key]) is int and fit_outcome[key] >= 0 for key in ('wall_ns', 'cpu_ns')), 'training fit timing unavailable')
    launcher_outcomes = {}
    if pre['schema'] == 'synthetic-pin-roller-v4-candidate-budget-predeclaration.v2':
        for phase, child_wall in (('training', train['wall_ns']), ('search', search['online_and_optional_oracle_wall_ns'])):
            check(load(ROOT/f'{phase}-started.json') == {'phase':phase,'status':'started','unknown_work_until_outcome':True}, f'{phase} launcher start record mismatch')
            outcome = load(ROOT/f'{phase}-outcome.json')
            launcher_outcomes[phase] = outcome
            check(outcome['phase'] == phase and outcome['status'] == 'returned' and outcome['exit_code'] == 0 and outcome['unknown_work_until_outcome'] is False, f'{phase} launcher did not complete')
            check(outcome['wall_scope'] == 'subprocess_including_imports_preparation_solver_replay_and_report_write', f'{phase} launcher wall scope changed')
            check(all(type(outcome[key]) is int and outcome[key] >= 0 for key in ('wall_ns','launcher_cpu_ns','child_cpu_ns')), f'{phase} launcher timing unavailable')
            check(child_wall <= outcome['wall_ns'], f'{phase} child report wall exceeds launcher wall')
            check((ROOT/f'{phase}-stdout.txt').is_file() and (ROOT/f'{phase}-stderr.txt').is_file(), f'{phase} launcher streams unavailable')
    check(fit_outcome['wall_ns'] <= train['wall_ns'], 'training fit wall exceeds training report wall')
    experiment = online_experiment
    price = experiment['prices']
    limits = {**experiment['history_limits'], **experiment['material_history_limits']}
    limits.update({f'terminal_{key}': value for key, value in experiment['terminal_limits'].items()})
    model = load(ROOT/'inputs/online-model.json')
    depth = model['sections'][0]['depth_m']
    bar_area = model['sections'][0]['bar_area_m2']
    bar_count = model['sections'][0]['top_bar_count'] + model['sections'][0]['bottom_bar_count']
    nodes = {n['id']:n['coordinates'] for n in model['nodes']}
    total_length = sum(math.dist(nodes[e['nodes'][0]],nodes[e['nodes'][1]]) for e in model['elements'])
    longitudinal_rebar_mass_kg = total_length * bar_count * bar_area * 7850.0
    oracle_rows = rows['exhaustive_oracle']
    oracle_table = []
    for index, width in enumerate(online_widths):
        cid = 'baseline' if index == 0 else f'w{round(width*100):02d}'
        row = oracle_rows[cid]
        pool_row = search_plan['pool'][index]
        check(row['artifacts']['model']['sha256'] == pool_row['model_artifact']['sha256'], f'{cid} oracle model differs from frozen pool')
        check(row['quantities'] == pool_row['quantities'], f'{cid} frozen pool quantities differ from oracle')
        check(row['material_estimate'] == pool_row['material_estimate'], f'{cid} frozen pool estimate differs from oracle')
        check(row['quantities']['model_checksum'] == pool_row['model_checksum'], f'{cid} quantity model identity differs from frozen pool')
        estimate = width * depth * total_length * price['concrete_per_m3'] + longitudinal_rebar_mass_kg * price['rebar_per_kg']
        check(math.isclose(estimate,row['material_estimate']['total'],rel_tol=0,abs_tol=1e-9), f'{cid} scoped arithmetic mismatch')
        quantities = row['quantities']
        check(check_hash_object(quantities, 'quantity_hash'), f'{cid} quantity internal hash mismatch')
        check(row['material_estimate']['quantity_hash'] == quantities['quantity_hash'], f'{cid} estimate quantity hash mismatch')
        check(math.isclose(quantities['totals']['gross_concrete_volume_m3'], width * depth * total_length, rel_tol=0, abs_tol=1e-10), f'{cid} concrete quantity mismatch')
        check(math.isclose(quantities['totals']['longitudinal_rebar_mass_kg'], longitudinal_rebar_mass_kg, rel_tol=0, abs_tol=1e-10), f'{cid} rebar mass mismatch')
        member_lengths = {e['id']: math.dist(nodes[e['nodes'][0]], nodes[e['nodes'][1]]) for e in model['elements']}
        check({member['member_id'] for member in quantities['members']} == set(member_lengths) and len(quantities['members']) == len(member_lengths), f'{cid} member quantity roster differs from source')
        estimate_members = {member['member_id']: member for member in row['material_estimate']['members']}
        check(set(estimate_members) == set(member_lengths) and len(row['material_estimate']['members']) == len(member_lengths), f'{cid} member cost roster differs from source')
        for member in quantities['members']:
            check(math.isclose(member['length_m'], member_lengths[member['member_id']], rel_tol=0, abs_tol=1e-10), f'{cid}/{member["member_id"]} member length differs from source')
            check(math.isclose(member['gross_concrete_volume_m3'], width * depth * member['length_m'], rel_tol=0, abs_tol=1e-10), f'{cid}/{member["member_id"]} member concrete mismatch')
            check(math.isclose(member['longitudinal_rebar_mass_kg'], bar_count * bar_area * member['length_m'] * 7850.0, rel_tol=0, abs_tol=1e-10), f'{cid}/{member["member_id"]} member steel mismatch')
            cost = estimate_members[member['member_id']]
            check(math.isclose(cost['concrete'], member['gross_concrete_volume_m3'] * price['concrete_per_m3'], rel_tol=0, abs_tol=1e-10), f'{cid}/{member["member_id"]} member concrete cost mismatch')
            check(math.isclose(cost['longitudinal_rebar'], member['longitudinal_rebar_mass_kg'] * price['rebar_per_kg'], rel_tol=0, abs_tol=1e-10), f'{cid}/{member["member_id"]} member steel cost mismatch')
        check(math.isclose(sum(cost['concrete'] + cost['longitudinal_rebar'] for cost in estimate_members.values()), row['material_estimate']['total'], rel_tol=0, abs_tol=1e-9), f'{cid} member costs do not sum to scoped total')
        screen = row['screens']['maximum_absolute_fiber_strain']
        check(screen['status'] == ('pass' if screen['value'] <= pre['history_maximum_absolute_fiber_strain_limit'] else 'fail'), f'{cid} strain screen mismatch')
        check(set(row['screens']) == set(limits), f'{cid} requested screen roster mismatch')
        for key, limit in limits.items():
            found = row['screens'][key]
            value = found['value']
            check(type(value) in (int, float) and math.isfinite(value) and found['limit'] == limit and found['status'] == ('pass' if value <= limit else 'fail'), f'{cid}/{key} requested screen arithmetic mismatch')
        check(row['selection_eligible'] is (row['full_reference_verification_pass'] and all(screen['status'] == 'pass' for screen in row['screens'].values())), f'{cid} selected eligibility mismatch')
        oracle_table.append({'candidate_id':cid,'width_m':width,'history_maximum_absolute_fiber_strain':screen['value'],'history_strain_screen':screen['status'],'full_reference_verified':row['full_reference_verification_pass'],'scoped_synthetic_estimate':row['material_estimate']['total']})
    feasible = [r for r in oracle_table if oracle_rows[r['candidate_id']]['selection_eligible']]
    cheapest = min(feasible,key=lambda r:r['scoped_synthetic_estimate']) if feasible else None
    check(cheapest is not None and cheapest['candidate_id'] == summary['exhaustive_oracle']['selected_candidate_id'], 'oracle cheapest feasible mismatch')
    cost_audit = search['candidate_cost_optimality_audit']
    check(cost_audit['pool_minimum_feasible_candidate_ids'] == ([cheapest['candidate_id']] if cheapest else None), 'reported finite pool optimum mismatch')
    learned_id = summary['learned_order']['selected_candidate_id']
    expected_gap = None if cheapest is None or learned_id is None else rows['learned_order'][learned_id]['material_estimate']['total'] - cheapest['scoped_synthetic_estimate']
    observed_gap = cost_audit['arms']['learned_order']['selected_minus_pool_minimum_estimate']
    check((expected_gap is None and observed_gap is None) or (expected_gap is not None and type(observed_gap) in (int, float) and math.isclose(observed_gap, expected_gap, rel_tol=0, abs_tol=1e-9)), 'reported learned pool cost gap mismatch')
    missed = [r['candidate_id'] for r in oracle_table if r['candidate_id'] not in {'baseline', *search_plan['plans']['learned_order']['shortlist']} and oracle_rows[r['candidate_id']]['selection_eligible'] and learned_id is not None and r['scoped_synthetic_estimate'] < rows['learned_order'][learned_id]['material_estimate']['total']]
    check(cost_audit['arms']['learned_order']['missed_cheaper_feasible_candidate_ids'] == missed, 'reported missed cheaper candidates mismatch')
    predicted_failure_ids = {r['candidate_id'] for r in search_plan['predictions'] if not r['prediction']['abstained'] and any(screen['status'] == 'fail' for screen in r['predicted_screens'].values())}
    if cost_audit['schema_version'] == 'rc-control-candidate-cost-optimality.v2':
        check(cost_audit['arms']['learned_order']['missed_cheaper_false_negative_candidate_ids'] == [cid for cid in missed if cid in predicted_failure_ids], 'reported cheaper false negatives mismatch')
    check(search['candidate_coverage_audit']['arms']['learned_order']['false_negative_candidate_ids'] == ['w46'], 'false negative audit mismatch')
    files = []
    for path in ROOT.rglob('*'):
        if path.is_symlink():
            check(False, f'packet symlink: {path.relative_to(ROOT)}')
        elif path.is_file() and path.name != 'audit.json':
            files.append(path)
    files.sort()
    inventory = [[str(path.relative_to(ROOT)), len(path.read_bytes()), sha(path.read_bytes())] for path in files]
    report = {
        'schema':'synthetic-pin-roller-v4-budget-byte-and-arithmetic-audit.v2',
        'pass':not violations,
        'violations':violations,
        'source_revision':pre['source_revision'],
        'frozen_plan_sha256':sha((ROOT/'plan.json').read_bytes()),
        'training_report_hash':train['report_hash'],
        'search_report_hash':search['report_hash'],
        'search_plan_hash':search_plan['plan_hash'],
        'training_and_pool_physical_identities_disjoint':set(train_plan['training_model_identities']).isdisjoint({r['model_identity'] for r in search_plan['pool']}),
        'referenced_artifacts_hashed':artifact_count,
        'packet_file_count_excluding_audit':len(files),
        'packet_file_inventory_sha256':sha(canonical(inventory)),
        'comparisons':summary,
        'nested_cost_scopes':{'training_fit':fit_outcome,'launcher_phases':launcher_outcomes,'interpretation':'Solver invocation counters cover the comparison rows; fit and launcher intervals are nested and must not be summed with them.'},
        'oracle_table':oracle_table,
        'online_budget_including_baseline':pre['full_analysis_budget_per_online_arm_including_baseline'],
        'oracle_separate_after_online_arms':search_plan['oracle_after_online_arms'],
        'learned_selected_minus_pool_minimum_synthetic_estimate':observed_gap,
        'learned_missed_cheaper_feasible_candidate_ids':missed,
        'interpretation':'One synthetic fixed-family same-engine study. Byte and scoped price arithmetic audit; no independent physical validation, code compliance, quote, or general speedup.',
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit_packet(args.source, args.packet)
    target = args.output or args.packet/'audit.json'
    with target.open('xb') as stream:
        stream.write((json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
    print(json.dumps({'pass':report['pass'],'violations':report['violations'],'referenced_artifacts_hashed':report['referenced_artifacts_hashed'],'comparisons':report['comparisons'],'oracle_table':report['oracle_table']},sort_keys=True))
    raise SystemExit(0 if report['pass'] else 1)

if __name__ == '__main__':
    main()
