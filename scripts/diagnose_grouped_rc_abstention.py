"""Post-hoc range diagnostics of stored material-policy inputs; no solver or fit.

Use the campaign's frozen package on PYTHONPATH. Does not alter OOD margins or
promote a policy. Repeated folds are reduced to one original repetition per fit.
"""
from collections import Counter
import argparse
import json
from pathlib import Path

import numpy as np
from structural_analysis.ai.fiber_frame_warm_start_features import (
    decode_fiber_frame_warm_start_model_features,
)
from structural_analysis.benchmark.rc_control_material_features import material_control_features
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.study
    result = json.loads((root / 'selection/result.json').read_bytes())
    declared = json.loads((root / 'labels/plan.json').read_bytes())
    features = {r['case_id']: decode_fiber_frame_warm_start_model_features(r['model_features'])
                for r in declared['cases']}
    records = []
    for fold in result['folds']:
        if fold['repetition_index'] != 0:
            continue
        index = fold['index']
        gate = json.loads((root / 'selection' / f'fold-{index:04d}-model-gate.json').read_bytes())
        row = {'case_id': fold['withheld_training_case'], 'ridge': fold['ridge'],
               'fold_index': index, 'static_gate': gate['status']}
        if gate['status'] == 'rejected':
            row['static_violations'] = gate['violations']
            records.append(row)
            continue
        policy = json.loads((root / 'selection' / f"fit-{fold['fit_index']:04d}-policy.json").read_bytes())
        counts = Counter()
        per_target = []
        for path in sorted((root / 'selection' / f'fold-{index:04d}' / 'proposal').glob('*-context.json')):
            context = RCControlSeedContext(**json.loads(path.read_bytes()))
            if len(context.accepted_targets_m) < 2:
                continue
            x, names = material_control_features(context, features[row['case_id']])
            if names != policy['material_feature_names']:
                raise ValueError('feature names changed')
            low, high = np.asarray(policy['feature_min']), np.asarray(policy['feature_max'])
            slack = np.maximum((high - low) * policy['ood_margin'], 1e-12)
            indices = np.flatnonzero((x < low - slack) | (x > high + slack))
            counts.update(names[int(i)] for i in indices)
            per_target.append({'target_m': context.target_m, 'range_violation_count': len(indices),
                               'first_violations': [{'feature': names[int(i)], 'value': float(x[i]),
                                                     'low': float(low[i]), 'high': float(high[i]),
                                                     'slack': float(slack[i])} for i in indices[:4]]})
        row['noninitial_targets'] = per_target
        row['feature_violation_frequency'] = dict(counts.most_common())
        records.append(row)
    report = {'schema_version': 'posthoc-grouped-material-range-diagnostics.v1',
              'source_revision': result['source_revision'], 'selection_result_hash': result['result_hash'],
              'solver_calls': 0, 'fits': 0, 'policy_changed': False,
              'is_independent_evaluation': False, 'records': records}
    with args.output.open('x') as handle:
        json.dump(report, handle, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({'records': len(records), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
