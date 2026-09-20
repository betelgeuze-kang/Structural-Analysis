"""Assemble complete outer-group-excluded gate inputs from an audited campaign.

This is an in-memory boundary, not an artifact authenticator. Callers must first
verify the original campaign using audit_rc_nested_switch_labels.audit.
"""
import math

from audit_rc_nested_switch_labels import label_from_repetitions
from prepare_rc_nested_switch_labels import require
from rc_switch_prefix_features import PROFILE


def gate_training_rows(audit, plan, outer):
    groups = plan['groups']
    require(type(outer) is int and 0 <= outer < len(groups), 'valid outer group required')
    tasks = plan['label_tasks']
    expected = {
        (task['outer_group_index'], task['inner_group_index'], sample): task
        for task in tasks for sample in task['label_source_sample_hashes']
    }
    require(len(expected) == sum(len(t['label_source_sample_hashes']) for t in tasks),
            'unique declared nested labels required')
    rows = audit['pairs']
    require(len(rows) == len(expected), 'complete audited label roster required')
    observed = set()
    selected, unverified = [], []
    feature_names = None
    for row in rows:
        key = (row['outer_group_index'], row['inner_group_index'], row['source_sample_hash'])
        require(key in expected and key not in observed, 'original unique nested label required')
        observed.add(key)
        task = expected[key]
        require(row['case_id'] in task['label_case_ids']
                and row['case_id'] not in task['outer_evaluation_case_ids']
                and row['seed_fit_index'] == task['seed_fit_index'], 'nested case and seed binding required')
        label = label_from_repetitions(row['repetitions'])
        require(row['label_result'] == label, 'original measured label required')
        if key[0] != outer:
            continue
        features = row['guard_features']
        names, values = features['feature_names'], features['values']
        require(features['profile'] == PROFILE and type(names) is list and names
                and all(type(name) is str and name for name in names)
                and len(set(names)) == len(names) and len(values) == len(names)
                and all(type(value) in (int, float) and math.isfinite(value) for value in values),
                'aligned finite pre-solve features required')
        if feature_names is None:
            feature_names = names
        require(names == feature_names, 'consistent feature schema required')
        identity = {'inner_group_index': key[1], 'source_sample_hash': key[2],
                    'case_id': row['case_id'], 'seed_fit_index': row['seed_fit_index']}
        if label['label'] is None:
            unverified.append(identity)
        else:
            selected.append({**identity, 'values': list(values), 'label': label['label']})
    require(observed == set(expected), 'complete original task coverage required')
    # Input serialization order must not become part of fitting/normalization.
    def order(row):
        return row['inner_group_index'], row['source_sample_hash']
    selected.sort(key=order)
    unverified.sort(key=order)
    return {'outer_group_index': outer, 'excluded_case_ids': list(groups[outer]),
            'feature_profile': PROFILE, 'feature_names': feature_names,
            'training_rows': selected, 'unverified_rows': unverified,
            'verified_positive_count': sum(row['label'] is True for row in selected),
            'verified_negative_count': sum(row['label'] is False for row in selected),
            'normalization_scope': 'verified training rows of this outer complement only',
            'gate_fitted': False, 'independent_evaluation': False}
