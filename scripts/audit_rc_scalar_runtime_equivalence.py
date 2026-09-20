"""Require unchanged retained numerical bytes after scalar serialization changes.

This supplements, rather than replaces, each campaign's full runtime audit.
Timings, selected strategy and source attestations are deliberately not compared.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_grouped_rc_runtime_campaign import checked, require

OLD_INVENTORY = 'a2c9b9d141db3c4718d3d69e02590a82d91282ed1994bce2a11c8e39c20b8409'
SUFFIXES = ('-step.json', '-response.json', '-context.json')


def numerical_files(folder):
    return {p.relative_to(folder).as_posix(): p for p in folder.rglob('*.json')
            if p.name.endswith(SUFFIXES)}


def compare_fold(old, new, index):
    left, right = numerical_files(old), numerical_files(new)
    prefix = old.relative_to(old.parents[2]).as_posix() + '/'
    expected = {name[len(prefix):] for name in index
                if name.startswith(prefix) and name.endswith(SUFFIXES)}
    require(bool(left) and set(left) == set(right) == expected,
            'numerical file roster changed')
    counts = dict.fromkeys(SUFFIXES, 0)
    for name, path in sorted(left.items()):
        original = path.read_bytes()
        relative = path.relative_to(old.parents[2]).as_posix()
        receipt = index[relative]
        require(len(original) == receipt['byte_length'] and
                hashlib.sha256(original).hexdigest() == receipt['sha256'],
                'original numerical receipt changed')
        require(right[name].read_bytes() == original, 'numerical bytes changed: ' + name)
        counts[next(s for s in SUFFIXES if name.endswith(s))] += 1
    return counts


def audit(old, new):
    raw = (old / 'inventory.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == OLD_INVENTORY, 'original inventory changed')
    index = {r['path']: r for r in json.loads(raw)['files']}
    original_result = (old / 'study/selection/result.json').read_bytes()
    receipt = index['study/selection/result.json']
    require(len(original_result) == receipt['byte_length'] and
            hashlib.sha256(original_result).hexdigest() == receipt['sha256'],
            'original result receipt changed')
    outcomes = []
    for root in (old, new):
        result = checked(root / 'study/selection/result.json', 'result_hash')
        require(len(result['folds']) == 90 and
                {f['index'] for f in result['folds']} == set(range(90)),
                'complete unique 90-fold result required')
        outcomes.append({f['index']: f for f in result['folds']})
    totals = dict.fromkeys(SUFFIXES, 0)
    for number in range(90):
        a, b = (r[number] for r in outcomes)
        for field in ('withheld_training_case', 'ridge', 'repetition_index', 'policy_hash'):
            require(a[field] == b[field], 'paired fold identity changed')
        counts = compare_fold(old / f'study/selection/fold-{number:04d}',
                              new / f'study/selection/fold-{number:04d}', index)
        for key, value in counts.items():
            totals[key] += value
    return {'schema_version': 'rc-scalar-numerical-equivalence.v1',
            'original_inventory_sha256': OLD_INVENTORY, 'completed_folds': 90,
            'exact_byte_counts': totals, 'new_solver_calls': 0, 'new_fits': 0,
            'whole_path_speedup_proved': False,
            'scope': 'steps, preload responses and input contexts; both full campaign audits also required'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old', type=Path)
    parser.add_argument('new', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.old, args.new)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
