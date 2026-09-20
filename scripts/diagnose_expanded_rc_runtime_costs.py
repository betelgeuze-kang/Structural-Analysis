"""Decompose retained path timings; never treat divergent paths as causal labels."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean

if __package__:
    from .audit_grouped_rc_runtime_campaign import checked, read, require
else:
    from audit_grouped_rc_runtime_campaign import checked, read, require

INVENTORY = 'd5e1d9d6727a827ba8f4011b9a52e9ca66be417bd927cae9dceb450e96a1aba2'


def decompose(arm, preload_recovery_ns):
    entries = arm['entries']
    invocations = list(arm['preload_invocations']) + [i for e in entries for i in e['invocations']]
    require(all(not i['unknown_work'] for i in invocations), 'unknown invocation cost')
    timing = {
        'invocations': sum(i['wall_ns'] for i in invocations),
        'response_recovery': preload_recovery_ns + sum(e['recovery_wall_ns'] for e in entries),
        'proposal': sum(e['proposal_wall_ns'] for e in entries),
        'material_capture': sum(e.get('committed_material_capture', {}).get('wall_ns', 0)
                                for e in entries),
    }
    if any('proposal_guard' in entry for entry in entries):
        timing['proposal_guard'] = sum(entry.get('proposal_guard', {}).get('wall_ns', 0)
                                       for entry in entries)
    timing['remaining_unattributed'] = arm['wall_ns'] - sum(timing.values())
    require(all(type(v) is int and v >= 0 for v in timing.values()), 'overlapping or invalid timing')
    return timing


def diagnose(bundle):
    raw = (bundle / 'inventory.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == INVENTORY, 'original packet inventory')
    index = {r['path']: r for r in read(bundle / 'inventory.json')['files']}

    def original(name, hash_field=None):
        path = bundle / name
        raw = path.read_bytes()
        require(len(raw) == index[name]['byte_length'] and
                hashlib.sha256(raw).hexdigest() == index[name]['sha256'], 'original receipt changed')
        return checked(path, hash_field) if hash_field else read(path)

    result = original('study/selection/result.json', 'result_hash')
    groups = defaultdict(list)
    for fold in result['folds']:
        stem = f"study/selection/fold-{fold['index']:04d}"
        report = original(stem + '/comparison.json', 'report_hash')
        require(report['report_hash'] == fold['report_hash'], 'fold report binding')
        row = {'index': fold['index'], 'arms': {}, 'target_pairs': []}
        for name in ('secant', 'proposal'):
            recovery = original(stem + '/' + name + '/preload-recovery-outcome.json')
            require(recovery['status'] == 'returned', 'preload recovery incomplete')
            row['arms'][name] = decompose(report['arms'][name], recovery['wall_ns'])
        for left, right in zip(report['arms']['secant']['entries'], report['arms']['proposal']['entries'], strict=True):
            require((left['target_index'], left['target_m']) ==
                    (right['target_index'], right['target_m']), 'target alignment')
            searches = {}
            for name, entry in (('secant', left), ('proposal', right)):
                searches[name] = 0
                for invocation in entry['invocations']:
                    step = original(stem + f"/{name}/{entry['target_index']:03d}-{invocation['ordinal']}-step.json")
                    searches[name] += len(step['trial_solution']['line_search_history'])
            row['target_pairs'].append({
                'target_index': left['target_index'], 'target_m': left['target_m'],
                'same_parent': left['parent_hash'] == right['parent_hash'],
                'decision': right['proposal_decision'],
                'secant_newton': sum(i['work']['newton_iterations'] for i in left['invocations']),
                'proposal_newton': sum(i['work']['newton_iterations'] for i in right['invocations']),
                'secant_recorded_line_search_trials': searches['secant'],
                'proposal_recorded_line_search_trials': searches['proposal'],
            })
        groups[(fold['ridge'], fold['withheld_training_case'])].append(row)
    cases = []
    for (ridge, case), rows in sorted(groups.items()):
        require(len(rows) == 3, 'all three repetitions required')
        require(all(r['target_pairs'] == rows[0]['target_pairs'] for r in rows),
                'target work or parent relationships differ across repetitions')
        means = {name: {key: mean(r['arms'][name][key] for r in rows)
                        for key in rows[0]['arms'][name]} for name in ('secant', 'proposal')}
        cases.append({'ridge': ridge, 'case_id': case, 'fold_indices': [r['index'] for r in rows],
                      'mean_path_components_ns': means,
                      'mean_proposal_minus_secant_components_ns': {
                          k: means['proposal'][k] - means['secant'][k] for k in means['secant']},
                      'target_pairs': rows[0]['target_pairs']})
    return {
        'schema_version': 'rc-expanded-runtime-cost-diagnostic.v1',
        'source_inventory_sha256': INVENTORY, 'selection_result_hash': result['result_hash'],
        'cases': cases, 'new_solver_calls': 0, 'new_fits': 0,
        'timing_scope': 'disjoint recorded path components; static gate outside path is excluded; remainder has no finer attribution',
        'counterfactual_training_labels': False,
        'interpretation': 'Later arm parents may differ. Step differences describe complete strategies, not same-parent intervention labels. Any switching policy needs new full-path evaluation.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.bundle)
    with args.output.open('x') as handle:
        json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({'cases': len(result['cases']), 'new_solver_calls': 0}))
