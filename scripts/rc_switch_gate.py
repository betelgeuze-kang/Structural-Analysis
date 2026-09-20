"""Fixed development ridge classifier for the pre-capture guard.

Scores are regression outputs, not probabilities. Bounds only screen individual
features; they do not establish joint support or independent generalization.
"""
from dataclasses import dataclass, field
from time import perf_counter_ns
from types import MappingProxyType
import re

import numpy as np

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from rc_switch_prefix_features import PROFILE, prefix_features
from prepare_rc_nested_switch_labels import require

SCHEMA = 'rc-pre-capture-ridge-gate.v1'
RIDGE = 1.0
THRESHOLD = 0.75


@dataclass(frozen=True)
class RidgeGate:
    _schema = SCHEMA
    _ridge = RIDGE
    _threshold = THRESHOLD
    _json: str = field(repr=False)
    _payload: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        require(type(self._json) is str, 'gate JSON required')
        payload = strict_json_object_bytes(self._json.encode(), maximum_bytes=1024 * 1024)
        require(set(payload) == {'schema_version', 'feature_profile', 'feature_names',
                'mean', 'scale', 'minimum', 'maximum', 'weights', 'ridge', 'threshold',
                'outer_group_index', 'excluded_case_ids', 'training_sample_hashes',
                'positive_count', 'negative_count', 'training_rows_hash', 'policy_hash'},
                'exact gate fields required')
        require(payload['schema_version'] == self._schema and payload['feature_profile'] == PROFILE
                and type(payload['ridge']) is float and payload['ridge'] == self._ridge
                and type(payload['threshold']) is float and payload['threshold'] == self._threshold,
                'fixed gate profile required')
        require(payload['policy_hash'] == _sha(_bytes({k: v for k, v in payload.items() if k != 'policy_hash'})),
                'gate hash mismatch')
        names = payload['feature_names']
        require(type(names) is list and names and all(type(n) is str and n for n in names)
                and len(set(names)) == len(names), 'unique feature names required')
        for key in ('mean', 'scale', 'minimum', 'maximum', 'weights'):
            values = payload[key]
            require(type(values) is list and len(values) == len(names) + (key == 'weights')
                    and all(type(v) in (int, float) and np.isfinite(v) for v in values),
                    'finite aligned gate arrays required')
        require(all(v > 0 for v in payload['scale'])
                and all(low <= center <= high for low, center, high in
                        zip(payload['minimum'], payload['mean'], payload['maximum'])),
                'valid gate normalization required')
        require(type(payload['outer_group_index']) is int and payload['outer_group_index'] >= 0,
                'outer group identity required')
        cases = payload['excluded_case_ids']
        require(type(cases) is list and cases and all(type(v) is str and v for v in cases)
                and len(set(cases)) == len(cases), 'excluded cases required')
        hashes = payload['training_sample_hashes']
        require(type(hashes) is list and hashes and len(set(hashes)) == len(hashes)
                and all(type(h) is str and re.fullmatch('sha256:[0-9a-f]{64}', h) for h in hashes)
                and type(payload['training_rows_hash']) is str
                and re.fullmatch('sha256:[0-9a-f]{64}', payload['training_rows_hash']),
                'original training hashes required')
        require(all(type(payload[k]) is int and payload[k] >= 0 for k in ('positive_count', 'negative_count'))
                and payload['positive_count'] + payload['negative_count'] == len(hashes),
                'complete verified label counts required')
        # Detach mutable input and retain only immutable tuples/scalars internally.
        object.__setattr__(self, '_payload', MappingProxyType({
            key: tuple(value) if isinstance(value, list) else value for key, value in payload.items()}))

    @property
    def policy_hash(self):
        return self._payload['policy_hash']

    def decision(self, features):
        p = self._payload
        require(features['profile'] == PROFILE
                and tuple(features['feature_names']) == p['feature_names'], 'gate feature binding required')
        values = features['values']
        require(len(values) == len(p['mean'])
                and all(type(v) in (int, float) and np.isfinite(v) for v in values),
                'finite gate inference inputs required')
        x = np.asarray(values, dtype=float)
        if p['positive_count'] == 0 or np.any(x < p['minimum']) or np.any(x > p['maximum']):
            return False
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            z = (x - p['mean']) / p['scale']
            score = float(np.append(z, 1.0) @ np.asarray(p['weights']))
        require(np.isfinite(score), 'finite gate score required')
        return score >= p['threshold']

    def guard(self, model_features):
        def decide(context):
            return self.decision(prefix_features(context, model_features))
        return decide


def fit_gate(training):
    """Call only with original independently audited gate_training_rows output."""
    started = perf_counter_ns()
    gate, receipt = _fit_gate(training, [row['label'] for row in training['training_rows']], RidgeGate)
    receipt['fit_wall_ns'] = perf_counter_ns() - started
    return gate, receipt


def _fit_gate(training, targets, gate_class):
    """Shared fixed-normalization solve; target semantics belong to the gate profile."""
    started = perf_counter_ns()
    rows = training['training_rows']
    require(rows and all(type(row['label']) is bool for row in rows), 'verified nonempty gate labels required')
    require(all(row['case_id'] not in training['excluded_case_ids'] for row in rows),
            'outer group cannot enter gate fit')
    require(training['feature_profile'] == PROFILE, 'pre-solve feature profile required')
    x = np.asarray([row['values'] for row in rows], dtype=float)
    require(x.ndim == 2 and x.shape[1] == len(training['feature_names']) and np.all(np.isfinite(x)),
            'finite aligned gate training matrix required')
    y = np.asarray(targets, dtype=float)
    require(y.shape == (len(rows),) and np.all(np.isfinite(y)), 'finite aligned gate targets required')
    minimum, maximum = x.min(axis=0), x.max(axis=0)
    constant = minimum == maximum
    # Repeated decimal constants can acquire a tiny spurious mean/std offset.
    center = np.where(constant, minimum, x.mean(axis=0))
    scale = np.where(constant, 1.0, x.std(axis=0))
    scale = np.where(scale > 0, scale, 1.0)
    z = np.column_stack(((x - center) / scale, np.ones(len(x))))
    penalty = np.eye(z.shape[1]) * np.sqrt(gate_class._ridge)
    penalty[-1, -1] = 0.0
    weights = np.linalg.lstsq(np.vstack((z, penalty)), np.concatenate((y, np.zeros(z.shape[1]))), rcond=None)[0]
    positives = sum(row['label'] for row in rows)
    payload = dict(schema_version=gate_class._schema, feature_profile=PROFILE,
        feature_names=training['feature_names'], mean=center.tolist(), scale=scale.tolist(),
        minimum=minimum.tolist(), maximum=maximum.tolist(), weights=weights.tolist(),
        ridge=gate_class._ridge, threshold=gate_class._threshold, outer_group_index=training['outer_group_index'],
        excluded_case_ids=training['excluded_case_ids'],
        training_sample_hashes=[row['source_sample_hash'] for row in rows],
        positive_count=positives, negative_count=len(rows)-positives,
        training_rows_hash=_sha(_bytes(training)))
    payload['policy_hash'] = _sha(_bytes(payload))
    gate = gate_class(_bytes(payload).decode())
    return gate, {'fit_wall_ns': perf_counter_ns()-started, 'verified_rows': len(rows),
                  'unverified_rows_excluded': len(training['unverified_rows']),
                  'independent_evaluation': False, 'policy_hash': gate.policy_hash}
