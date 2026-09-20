"""Account for cold policy parsing and bounded reuse in a completed campaign."""
import argparse
from collections import OrderedDict
import json
from pathlib import Path

from audit_grouped_rc_runtime_campaign import checked, read, require
from structural_analysis.benchmark.rc_control_design import _bytes


def reference_counts(keys):
    cache = OrderedDict()
    hits = misses = 0
    for key in keys:
        if key in cache:
            hits += 1
            cache.move_to_end(key)
        else:
            misses += 1
            cache[key] = None
            if len(cache) > 4:
                cache.popitem(last=False)
    return dict(hits=hits, misses=misses, maxsize=4, currsize=len(cache))


def validate_receipt(before, outcome, expected):
    for counts in (before, outcome['before'], outcome['after']):
        require(type(counts) is dict and set(counts) == {'hits', 'misses', 'maxsize', 'currsize'}
                and all(type(v) is int and v >= 0 for v in counts.values()),
                'exact nonnegative integer cache counters required')
    require(before == dict(hits=0, misses=0, maxsize=4, currsize=0) == outcome['before'],
            'empty original process cache required')
    require(outcome['cold_process'] is True and
            outcome['cache_cleared_between_folds'] is False, 'cache lifecycle differs')
    require(outcome['after'] == expected, 'cache counters differ from full call roster')


def audit(root):
    result = checked(root / 'study/selection/result.json', 'result_hash')
    require(len(result['folds']) == 90 and
            [f['index'] for f in result['folds']] == list(range(90)),
            'complete ordered 90-fold roster required')
    keys = []
    skipped = 0
    for fold in result['folds']:
        prefix = root / f"study/selection/fold-{fold['index']:04d}"
        gate = checked(prefix.with_name(prefix.name + '-model-gate.json'), 'gate_hash')
        report = checked(prefix / 'comparison.json', 'report_hash')
        policy = checked(root / f"study/selection/fit-{fold['fit_index']:04d}-policy.json", 'policy_hash')
        require(gate['gate_hash'] == fold['static_model_gate_hash'] and
                report['report_hash'] == fold['report_hash'] and
                policy['policy_hash'] == fold['policy_hash'] == gate['policy_hash'],
                'fold cache inputs do not bind')
        entries = report['arms']['proposal']['entries']
        require(len(entries) == 12 and report['arms']['proposal']['status'] == 'complete',
                'complete proposal paths required')
        require(gate['status'] in ('rejected', 'not_rejected'), 'unknown model gate')
        if gate['status'] == 'rejected':
            skipped += len(entries)
        else:
            keys.extend([_bytes(policy).decode()] * len(entries))
    expected = reference_counts(keys)
    validate_receipt(read(root / 'inference-cache-start.json'),
                     read(root / 'inference-cache-outcome.json'), expected)
    return {'schema_version': 'rc-policy-cache-accounting.v1',
            'selection_result_hash': result['result_hash'], 'expected_and_observed': expected,
            'inference_calls': len(keys), 'static_gate_bypassed_calls': skipped,
            'cold_process': True, 'each_path_starts_cold': False,
            'new_solver_calls': 0, 'new_fits': 0,
            'scope': 'lifecycle counters only; full runtime and numerical equivalence audits also required'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
