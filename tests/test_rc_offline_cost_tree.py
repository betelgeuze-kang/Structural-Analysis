"""Deterministic small-tree behavior and strict offline policy boundaries."""

from copy import deepcopy
import json
import importlib
from pathlib import Path

import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha

OfflineCostTree = fit_cost_tree = score_gate = TARGET_PROFILE = PROFILE = None


@pytest.fixture(autouse=True)
def script_imports(monkeypatch):
    global OfflineCostTree, fit_cost_tree, score_gate, TARGET_PROFILE, PROFILE
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    tree = importlib.import_module('rc_offline_cost_tree')
    OfflineCostTree, fit_cost_tree = tree.OfflineCostTree, tree.fit_cost_tree
    TARGET_PROFILE, PROFILE = tree.TARGET_PROFILE, tree.PROFILE
    score_gate = importlib.import_module('score_rc_gate_validation').score_gate


def row(index, positive, *, case='train'):
    repeats = [dict(repetition=i, comparison_pass=True, decision='proposed',
                    path_time_ratio=.75 if positive else 1.25,
                    report_hash='sha256:'+format(index*3+i, '064x')) for i in range(3)]
    return dict(case_id=case, source_sample_hash='sha256:'+format(index, '064x'),
                parent_hash='sha256:'+'a'*64, policy_hash='sha256:'+'b'*64,
                values=[float(index)], label=positive, cost_target=.25 if positive else -.25,
                cost_repetitions=repeats)


def training():
    return dict(outer_group_index=0, validation_group_index=1, excluded_case_ids=['held', 'outer'],
                feature_profile=PROFILE, feature_names=['prefix.x'], cost_target_profile=TARGET_PROFILE,
                training_rows=[row(i, i>=8) for i in range(16)], unverified_rows=[])


def features(value):
    return dict(profile=PROFILE, feature_names=['prefix.x'], values=[value])


def resign(payload):
    payload['policy_hash'] = _sha(_bytes({k:v for k,v in payload.items() if k != 'policy_hash'}))
    return _bytes(payload).decode()


def test_piecewise_cost_split_and_outside_bound_decline():
    t = training()
    original = deepcopy(t)
    gate, receipt = fit_cost_tree(t)
    assert t == original
    p = json.loads(gate._json)
    assert p['tree']['feature_index'] == 0 and p['tree']['cut'] == 7.
    assert p['tree']['left'] == dict(value=-.25, sample_count=8)
    assert p['tree']['right'] == dict(value=.25, sample_count=8)
    assert gate.decision(features(7.)) is False
    assert gate.decision(features(8.)) is True
    assert gate.decision(features(16.)) is False
    assert fit_cost_tree(t)[0].policy_hash == gate.policy_hash
    assert receipt['verified_rows'] == 16
    with pytest.raises(TypeError):
        gate._payload['tree']['left']['value'] = 99
    with pytest.raises(ValueError, match='offline'):
        gate.guard(None)


def test_minimum_leaf_support_prevents_isolating_tiny_positive_cluster():
    t = training()
    t['training_rows'] = [row(i, i>=14) for i in range(16)]
    gate, _ = fit_cost_tree(t)
    assert gate.decision(features(15.)) is False


def test_constant_target_stays_one_leaf():
    t = training()
    t['training_rows'] = [row(i, True) for i in range(24)]
    gate, _ = fit_cost_tree(t)
    assert json.loads(gate._json)['tree'] == dict(value=.25, sample_count=24)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), '1'])
def test_invalid_inputs_rejected_before_fit_and_at_inference(value):
    t = training()
    gate, _ = fit_cost_tree(t)
    t['training_rows'][0]['values'] = [value]
    with pytest.raises(ValueError, match='finite'):
        fit_cost_tree(t)
    with pytest.raises(ValueError, match='finite'):
        gate.decision(features(value))


def test_excluded_case_and_changed_cost_target_are_rejected():
    t = training()
    t['training_rows'][0]['case_id'] = 'held'
    with pytest.raises(ValueError, match='excluded'):
        fit_cost_tree(t)
    t = training()
    t['training_rows'][0]['cost_target'] = .5
    with pytest.raises(ValueError, match='original measured'):
        fit_cost_tree(t)


@pytest.mark.parametrize('mutation', ['depth', 'support', 'feature_bool', 'nonfinite', 'threshold'])
def test_rehashed_invalid_policy_still_rejected(mutation):
    gate, _ = fit_cost_tree(training())
    p = json.loads(gate._json)
    if mutation == 'depth':
        p['max_depth'] = 4
    elif mutation == 'support':
        p['tree']['left']['sample_count'] = 7
    elif mutation == 'feature_bool':
        p['tree']['feature_index'] = False
    elif mutation == 'nonfinite':
        p['tree']['left']['value'] = 'NaN'
    else:
        p['threshold'] = .001
    with pytest.raises(ValueError):
        OfflineCostTree(resign(p))


def test_duplicate_key_policy_rejected():
    gate, _ = fit_cost_tree(training())
    with pytest.raises(ValueError):
        OfflineCostTree('{"threshold":0.5,'+gate._json[1:])


def test_common_scorer_keeps_held_case_and_sample_exclusions():
    gate, _ = fit_cost_tree(training())
    negative, positive = row(100, False, case='held'), row(101, True, case='held')
    negative['values'] = [2.]
    positive['values'] = [12.]
    validation = dict(rows=[negative,positive], declared_row_count=2, unverified_count=0,
                      feature_profile=PROFILE, feature_names=['prefix.x'])
    score = score_gate(gate, validation)
    assert score['counts']['true_positive'] == score['counts']['true_negative'] == 1
    assert score['full_path_evaluation'] is False
    validation['rows'][0]['source_sample_hash'] = training()['training_rows'][0]['source_sample_hash']
    with pytest.raises(ValueError, match='excluded'):
        score_gate(gate, validation)
