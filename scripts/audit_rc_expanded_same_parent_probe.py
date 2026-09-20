"""Audit every retained B/D/E parent probe without solving or fitting."""
import argparse
import json
from pathlib import Path
from statistics import mean
from collections import OrderedDict

from run_rc_expanded_same_parent_probe import prepare

from audit_grouped_rc_runtime_campaign import checked, read, require


def cache_accounting(roster, observed):
    cache = OrderedDict()
    misses = hits = 0
    for row in roster:
        for _ in range(3):
            key = row['policy_hash']
            if key in cache:
                hits += 1
                cache.move_to_end(key)
            else:
                misses += 1
                cache[key] = None
                if len(cache) > 4:
                    cache.popitem(last=False)
    require(type(observed) is dict and all(type(v) is int for v in observed.values()),
            'integer cache counters required')
    require(observed == {'hits': hits, 'misses': misses, 'maxsize': 4, 'currsize': len(cache)},
            'complete ordered policy-cache accounting')
    return observed


def audit(root):
    plan = read(root / 'plan.json')
    outcome = read(root / 'outcome.json')
    require(plan['repetitions'] == 3 and plan['maximum_core_calls'] == 3564
            and plan['new_fits'] == 0 and plan['reserved_evaluation'] is False
            and plan['complete_path_claim'] is False, 'fixed probe scope')
    _, roster, _, costs = prepare(*(Path(plan['source_roots'][key]) for key in ('old', 'new', 'runtime')))
    require(plan['roster'] == roster and plan['historical_label_costs_separate'] == costs,
            'original complete complementary-group input binding')
    require(len(roster) == 198 and len(outcome['records']) == 594, 'complete declared roster')
    require({(r['pair_index'], r['repetition']) for r in outcome['records']} ==
            {(p, r) for p in range(198) for r in range(3)}, 'unique complete reports')
    require(plan['cache_before'] == {'hits': 0, 'misses': 0, 'maxsize': 4, 'currsize': 0},
            'cold process cache required')
    cache_accounting(roster, outcome['cache_after'])
    metrics = ('core_calls', 'newton_iterations', 'linear_solves')
    total = dict.fromkeys(metrics, 0)
    rows = []
    for pair, declaration in enumerate(plan['roster']):
        repeats = []
        for record in (r for r in outcome['records'] if r['pair_index'] == pair):
            repeat = record['repetition']
            require(read(root / f'record-{pair:03d}-{repeat}.json') == record, 'immutable completion receipt')
            name = f'pair-{pair:03d}-repeat-{repeat}/comparison.json'
            path = root / name
            report = checked(path, 'report_hash')
            require(report['source_revision'] == plan['source_revision'], 'execution source revision')
            require(report['capture_material_state'] is True and report['material_capture_scope'] == 'proposal-only',
                    'proposal state-capture cost retained')
            require(report['report_hash'] == record['report_hash'] and
                    report['proposal_identity'] == declaration['policy_hash'], 'report and policy binding')
            require(report['initial_parent_hash'] == declaration['parent_hash'] and
                    report['source_target_index'] == declaration['target_index'], 'source parent and target')
            require(not report['original_complete_path_executed'] and
                    report['comparison_scope'] == 'one_target_from_one_supplied_native_parent_and_accepted_prefix',
                    'single-target scope required')
            require(report['arm_order'] == plan['arm_order_schedule'][repeat], 'counterbalanced order')
            require(report['absolute_tolerance'] == 1e-10 and report['relative_tolerance'] == 1e-8,
                    'original comparison tolerances')
            arm_work = {}
            complete = True
            for name, arm in {**report['arms'], 'fresh-reference': report['fresh_reference']}.items():
                require(not arm['preload_invocations'] and len(arm['entries']) == 1,
                        'one step with no repeated preload')
                require(arm['entries'][0]['parent_hash'] == declaration['parent_hash'], 'identical native parent')
                arm_work[name] = dict.fromkeys(metrics, 0)
                complete = complete and arm['status'] == 'complete'
                for invocation in arm['entries'][0]['invocations']:
                    require(not invocation['unknown_work'], 'unknown solver work')
                    for metric in metrics:
                        total[metric] += invocation['work'][metric]
                        arm_work[name][metric] += invocation['work'][metric]
            passed = complete and all(c['step_response_pass'] for c in report['comparisons'].values())
            repeats.append({'repetition': repeat, 'comparison_pass': passed,
                'decision': report['arms']['proposal']['entries'][0]['proposal_decision'],
                'path_time_ratio': report['arms']['proposal']['wall_ns'] / report['arms']['secant']['wall_ns'] if passed else None,
                'work': arm_work, 'report_hash': report['report_hash']})
        valid = all(r['comparison_pass'] for r in repeats)
        rows.append({**declaration, 'repetitions': repeats, 'all_comparisons_pass': valid,
                     'mean_path_time_ratio': mean(r['path_time_ratio'] for r in repeats) if valid else None})
    require(total['core_calls'] <= plan['maximum_core_calls'], 'declared core-call budget')
    return {'source_revision': plan['source_revision'], 'pairs': rows, 'report_count': 594,
        'retained_report_count': 0, 'new_report_count': 594,
        'cache_after': outcome['cache_after'], 'all_report_work': total,
        'passed_comparisons': sum(r['comparison_pass'] for row in rows for r in row['repetitions']),
        'proposed_count': sum(r['decision'] == 'proposed' for row in rows for r in row['repetitions']),
        'faster_pair_means': sum(row['mean_path_time_ratio'] is not None and row['mean_path_time_ratio'] < 1 for row in rows),
        'current_invocation_wall_ns': outcome['wall_ns_before_outcome_write'],
        'complete_path_speedup_claim': False, 'independent_evaluation': False, 'new_fits': 0,
        'scope': 'posthoc same-parent step diagnostics; previous labels and policy-fit costs remain separate; no fitted switching policy or oracle speedup'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.study)
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'pairs'}))
