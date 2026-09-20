"""One fixed offline cost-regression tree; no runtime adapter or promotion."""

from dataclasses import dataclass, field
import math
import re
from time import perf_counter_ns
from types import MappingProxyType

import numpy as np

from audit_rc_nested_switch_labels import label_from_repetitions
from prepare_rc_nested_switch_labels import require
from rc_cost_margin_gate import TARGET_PROFILE, cost_target
from rc_switch_prefix_features import PROFILE
from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.benchmark.rc_control_design import _bytes, _sha

SCHEMA = 'rc-offline-prefix-cost-tree.v1'
MAX_DEPTH = 3
MIN_LEAF = 8
THRESHOLD = .01


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _freeze(node, dimensions, depth=0):
    require(type(node) is dict and depth <= MAX_DEPTH, 'bounded tree required')
    leaf = 'value' in node
    expected = {'value', 'sample_count'} if leaf else {'feature_index', 'cut', 'left', 'right', 'sample_count'}
    require(set(node) == expected and type(node['sample_count']) is int
            and node['sample_count'] > 0, 'exact tree node fields and count required')
    require(depth == 0 or node['sample_count'] >= MIN_LEAF, 'minimum child support required')
    if leaf:
        require(_finite(node['value']), 'finite leaf value required')
        return MappingProxyType(dict(node))
    require(depth < MAX_DEPTH and type(node['feature_index']) is int
            and 0 <= node['feature_index'] < dimensions and _finite(node['cut']),
            'valid bounded split required')
    left, right = (_freeze(node[key], dimensions, depth+1) for key in ('left', 'right'))
    require(left['sample_count'] + right['sample_count'] == node['sample_count'],
            'complete child support required')
    return MappingProxyType(dict(node, left=left, right=right))


@dataclass(frozen=True)
class OfflineCostTree:
    _json: str = field(repr=False)
    _payload: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        require(type(self._json) is str, 'tree JSON required')
        p = strict_json_object_bytes(self._json.encode(), maximum_bytes=1024*1024)
        require(set(p) == {'schema_version', 'feature_profile', 'feature_names', 'minimum', 'maximum',
                'max_depth', 'min_leaf', 'threshold', 'tree', 'outer_group_index', 'excluded_case_ids',
                'training_sample_hashes', 'positive_count', 'negative_count', 'training_rows_hash', 'policy_hash'},
                'exact tree policy fields required')
        require(p['schema_version'] == SCHEMA and p['feature_profile'] == PROFILE
                and type(p['max_depth']) is int and p['max_depth'] == MAX_DEPTH
                and type(p['min_leaf']) is int and p['min_leaf'] == MIN_LEAF
                and type(p['threshold']) is float and p['threshold'] == THRESHOLD,
                'fixed tree profile required')
        require(p['policy_hash'] == _sha(_bytes({k:v for k,v in p.items() if k != 'policy_hash'})),
                'tree policy hash mismatch')
        names = p['feature_names']
        require(type(names) is list and names and all(type(n) is str and n for n in names)
                and len(set(names)) == len(names), 'unique tree feature names required')
        for key in ('minimum', 'maximum'):
            require(type(p[key]) is list and len(p[key]) == len(names)
                    and all(_finite(v) for v in p[key]), 'finite aligned tree bounds required')
        require(all(a <= b for a,b in zip(p['minimum'], p['maximum'])), 'ordered tree bounds required')
        require(type(p['outer_group_index']) is int and p['outer_group_index'] >= 0,
                'outer group identity required')
        cases = p['excluded_case_ids']
        require(type(cases) is list and cases and all(type(c) is str and c for c in cases)
                and len(set(cases)) == len(cases), 'excluded cases required')
        hashes = p['training_sample_hashes']
        require(type(hashes) is list and hashes and len(set(hashes)) == len(hashes)
                and all(type(h) is str and re.fullmatch('sha256:[0-9a-f]{64}', h) for h in hashes)
                and type(p['training_rows_hash']) is str
                and re.fullmatch('sha256:[0-9a-f]{64}', p['training_rows_hash']), 'original training hashes required')
        require(all(type(p[k]) is int and p[k] >= 0 for k in ('positive_count', 'negative_count'))
                and p['positive_count'] + p['negative_count'] == len(hashes), 'complete tree label counts required')
        tree = _freeze(p['tree'], len(names))
        require(tree['sample_count'] == len(hashes), 'complete root support required')
        object.__setattr__(self, '_payload', MappingProxyType({
            k: tree if k == 'tree' else tuple(v) if isinstance(v, list) else v for k,v in p.items()}))

    @property
    def policy_hash(self):
        return self._payload['policy_hash']

    def decision(self, features):
        p = self._payload
        require(features['profile'] == PROFILE and tuple(features['feature_names']) == p['feature_names'],
                'tree inference feature binding required')
        values = features['values']
        require(len(values) == len(p['minimum']) and all(_finite(v) for v in values),
                'finite aligned tree inference values required')
        if p['positive_count'] == 0 or any(v < lo or v > hi for v,lo,hi in
                zip(values, p['minimum'], p['maximum'])):
            return False
        node = p['tree']
        while 'value' not in node:
            node = node['left'] if values[node['feature_index']] <= node['cut'] else node['right']
        return node['value'] >= p['threshold']

    def guard(self, model_features):
        raise ValueError('offline tree has no cost-validated runtime adapter')


def fit_cost_tree(training):
    """Use authenticated verified rows only; no validation statistics or labels."""
    started = perf_counter_ns()
    require(training['feature_profile'] == PROFILE and training['cost_target_profile'] == TARGET_PROFILE,
            'fixed prefix cost target required')
    rows = training['training_rows']
    require(type(rows) is list and rows and all(type(r['label']) is bool for r in rows),
            'nonempty verified tree training rows required')
    require(all(r['case_id'] not in training['excluded_case_ids'] for r in rows),
            'excluded cases cannot enter tree training')
    names = training['feature_names']
    require(type(names) is list and names and all(type(n) is str and n for n in names)
            and len(set(names)) == len(names), 'unique tree feature names required')
    require(all(type(r['values']) is list and len(r['values']) == len(names)
                and all(_finite(v) for v in r['values']) for r in rows), 'finite aligned tree inputs required')
    targets = []
    for row in rows:
        target = cost_target(row['cost_repetitions'])
        require(target is not None and type(row['cost_target']) is float and row['cost_target'] == target
                and row['label'] is label_from_repetitions(row['cost_repetitions'])['label'],
                'original measured tree target required')
        targets.append(target)
    x = np.asarray([r['values'] for r in rows], dtype=float)
    y = np.asarray(targets, dtype=float)
    # A training-only scalar preserves split ordering while bounding squared losses.
    target_scale = max(1., float(np.max(np.abs(y))))
    scaled = y / target_scale

    def loss(indices):
        values = scaled[indices]
        return float(np.sum((values - values.mean())**2))

    def grow(indices, depth):
        leaf = dict(value=math.fsum(float(y[i])/len(indices) for i in indices), sample_count=len(indices))
        if depth == MAX_DEPTH or len(indices) < 2*MIN_LEAF or np.all(y[indices] == y[indices[0]]):
            return leaf
        best_loss, best = loss(indices), None
        # Stable feature/value traversal supplies deterministic tie breaking.
        for feature in range(x.shape[1]):
            for cut in np.unique(x[indices, feature])[:-1]:
                mask = x[indices, feature] <= cut
                left, right = indices[mask], indices[~mask]
                if len(left) < MIN_LEAF or len(right) < MIN_LEAF:
                    continue
                candidate = loss(left) + loss(right)
                if candidate < best_loss:
                    best_loss, best = candidate, (feature, float(cut), left, right)
        if best is None:
            return leaf
        feature, cut, left, right = best
        return dict(feature_index=feature, cut=cut, left=grow(left, depth+1),
                    right=grow(right, depth+1), sample_count=len(indices))

    tree = grow(np.arange(len(rows)), 0)
    positives = sum(r['label'] for r in rows)
    p = dict(schema_version=SCHEMA, feature_profile=PROFILE, feature_names=names,
        minimum=x.min(0).tolist(), maximum=x.max(0).tolist(), max_depth=MAX_DEPTH, min_leaf=MIN_LEAF,
        threshold=THRESHOLD, tree=tree, outer_group_index=training['outer_group_index'],
        excluded_case_ids=training['excluded_case_ids'], training_sample_hashes=[r['source_sample_hash'] for r in rows],
        positive_count=positives, negative_count=len(rows)-positives, training_rows_hash=_sha(_bytes(training)))
    p['policy_hash'] = _sha(_bytes(p))
    gate = OfflineCostTree(_bytes(p).decode())
    return gate, dict(policy_hash=gate.policy_hash, fit_wall_ns=perf_counter_ns()-started,
        target_profile=TARGET_PROFILE, verified_rows=len(rows), unverified_rows_excluded=len(training['unverified_rows']),
        target_scale_for_split_loss=target_scale, maximum_depth=MAX_DEPTH, minimum_leaf_rows=MIN_LEAF,
        offline_only=True, gate_cost_in_training_target=False, independent_evaluation=False)
