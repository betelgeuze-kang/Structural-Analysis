"""Audit complete same-parent probes, preserving step/full-path distinctions."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean

from audit_grouped_rc_runtime_campaign import checked, read, require


def audit(root):
    plan = read(root / 'plan.json')
    outcome = read(root / 'outcome.json')
    require(len(plan['roster']) == 66 and len(outcome['records']) == 198, 'complete declared roster')
    require({(r['pair_index'], r['repetition']) for r in outcome['records']} ==
            {(p, r) for p in range(66) for r in range(3)}, 'unique complete reports')
    prefix = Path(plan['retained_prefix'])
    require(hashlib.sha256((prefix / 'inventory.json').read_bytes()).hexdigest() ==
            plan['retained_prefix_inventory_sha256'], 'prefix inventory')
    prefix_index = {r['path']: r for r in read(prefix / 'inventory.json')['files']}
    prefix_revision = read(prefix / 'study/plan.json')['source_revision']
    metrics = ('core_calls', 'newton_iterations', 'linear_solves')
    total = dict.fromkeys(metrics, 0)
    rows = []
    for pair, declaration in enumerate(plan['roster']):
        repeats = []
        for record in (r for r in outcome['records'] if r['pair_index'] == pair):
            repeat = record['repetition']
            require(read(root / f'record-{pair:03d}-{repeat}.json') == record, 'immutable completion receipt')
            name = f'pair-{pair:03d}-repeat-{repeat}/comparison.json'
            if record['retained_from_prefix']:
                require(pair == 0 and repeat in (0, 1), 'exact original completed prefix')
                path = prefix / 'study' / name
                raw = path.read_bytes()
                original = prefix_index['study/' + name]
                require(len(raw) == original['byte_length'] and
                        hashlib.sha256(raw).hexdigest() == original['sha256'], 'retained report changed')
            else:
                path = root / name
            report = checked(path, 'report_hash')
            require(report['source_revision'] == (prefix_revision if record['retained_from_prefix'] else plan['source_revision']),
                    'execution source revision')
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
    return {'source_revision': plan['source_revision'], 'pairs': rows, 'report_count': 198,
        'retained_report_count': 2, 'new_report_count': 196, 'all_report_work': total,
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
