"""Protect additive timing attribution and unknown-work boundaries."""
import pytest
import importlib
from pathlib import Path

from scripts.diagnose_expanded_rc_runtime_costs import decompose


def test_disjoint_timers_retain_unattributed_time_and_preload():
    arm = {'wall_ns': 100, 'preload_invocations': [{'wall_ns': 10, 'unknown_work': False}],
           'entries': [{'invocations': [{'wall_ns': 30, 'unknown_work': False}],
                        'recovery_wall_ns': 15, 'proposal_wall_ns': 5,
                        'committed_material_capture': {'wall_ns': 7}}]}
    assert decompose(arm, 3) == {
        'invocations': 40, 'response_recovery': 18, 'proposal': 5,
        'material_capture': 7, 'remaining_unattributed': 30,
    }


@pytest.mark.parametrize('changed', ['model_checksum', 'source_revision', 'request'])
def test_pooled_runtime_audit_rejects_transplanted_case_results(changed, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    binding = importlib.import_module('audit_rc_pooled_runtime_campaign').require_report_binding
    request = {'targets_m': [0.001, -0.002]}
    plan = {'source_revision': 'source', 'cases': [
        {'case_id': 'case', 'split': 'train', 'model_hash': 'model', 'request': request}]}
    report = {'source_revision': 'source', 'model_checksum': 'model', 'request': request}
    binding(plan, 'case', report)
    report[changed] = {'targets_m': [0.001, -0.003]} if changed == 'request' else 'foreign'
    with pytest.raises(ValueError, match='comparison model/request/source binding'):
        binding(plan, 'case', report)


def test_overlapping_timers_and_unknown_work_are_not_presented_as_complete_costs():
    arm = {'wall_ns': 10, 'preload_invocations': [{'wall_ns': 11, 'unknown_work': False}],
           'entries': []}
    with pytest.raises(ValueError, match='overlapping or invalid timing'):
        decompose(arm, 0)
    arm['preload_invocations'][0]['unknown_work'] = True
    with pytest.raises(ValueError, match='unknown invocation cost'):
        decompose(arm, 0)


def test_policy_cache_accounting_replays_eviction_and_exact_content(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_policy_cache_receipt')
    assert module.reference_counts(['a', 'b', 'c', 'd', 'a', 'e', 'b']) == {
        'hits': 1, 'misses': 6, 'maxsize': 4, 'currsize': 4,
    }
    assert module.reference_counts(['{"a":1}', '{"a": 1}', '{"a":1}']) == {
        'hits': 1, 'misses': 2, 'maxsize': 4, 'currsize': 2,
    }


@pytest.mark.parametrize('change', ['none', 'hot_start', 'wrong_hits', 'boolean', 'cleared'])
def test_policy_cache_receipt_requires_cold_complete_accounting(monkeypatch, change):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_policy_cache_receipt')
    before = dict(hits=0, misses=0, maxsize=4, currsize=0)
    expected = dict(hits=9, misses=1, maxsize=4, currsize=1)
    outcome = dict(before=dict(before), after=dict(expected), cold_process=True,
                   cache_cleared_between_folds=False)
    if change == 'hot_start':
        before['currsize'] = outcome['before']['currsize'] = 1
    elif change == 'wrong_hits':
        outcome['after']['hits'] = 8
    elif change == 'boolean':
        outcome['after']['misses'] = True
    elif change == 'cleared':
        outcome['cache_cleared_between_folds'] = True
    if change == 'none':
        module.validate_receipt(before, outcome, expected)
    else:
        with pytest.raises(ValueError):
            module.validate_receipt(before, outcome, expected)


def test_expanded_parent_probe_excludes_whole_group_not_only_case(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('run_rc_expanded_same_parent_probe')
    groups = [[f'{group}-{amplitude}' for amplitude in range(3)] for group in 'abcde']
    samples = [{'case_id': case, 'sample_hash': f'{case}-{index}'}
               for group in groups for case in group for index in range(11)]
    result = module.complementary_samples(samples, groups, 'b-1')
    assert len(result) == 132
    assert all(not value.startswith('b-') for value in result)
    assert set(module.CASE_IDS) == {f'train-{g}-amp{a}' for g in 'bde' for a in ('050', '100', '150')}
    with pytest.raises(ValueError, match='one complete'):
        module.complementary_samples(samples, groups + [groups[1]], 'b-1')
    with pytest.raises(ValueError, match='132 complementary'):
        module.complementary_samples(samples[:-1], groups, 'b-1')


def test_expanded_parent_cache_accounts_repeats_and_rejects_boolean_counter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_expanded_same_parent_probe')
    roster = [{'policy_hash': str(i)} for i in range(6)]
    counters = {'hits': 12, 'misses': 6, 'maxsize': 4, 'currsize': 4}
    assert module.cache_accounting(roster, counters) == counters
    with pytest.raises(ValueError, match='ordered policy-cache'):
        module.cache_accounting(roster, dict(counters, misses=5))
    with pytest.raises(ValueError, match='integer cache'):
        module.cache_accounting(roster, dict(counters, hits=True))


@pytest.mark.parametrize('field', ['model_checksum', 'source_request', 'request', 'compiled_problem_contract_hash'])
def test_expanded_parent_audit_rejects_other_case_report(monkeypatch, field):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_expanded_same_parent_probe')
    report = dict(model_checksum='model', source_request={'targets': [1, 2]},
                  request={'targets': [2]}, compiled_problem_contract_hash='problem')
    module.require_source_binding(report, 'model', {'targets': [1, 2]}, {'targets': [2]}, 'problem')
    report[field] = 'foreign'
    with pytest.raises(ValueError, match='original model'):
        module.require_source_binding(report, 'model', {'targets': [1, 2]}, {'targets': [2]}, 'problem')


def test_expanded_parent_audit_checks_original_artifact_bytes(monkeypatch, tmp_path):
    import hashlib
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_expanded_same_parent_probe')
    expected = b'{"parent":1}'
    descriptor = {'path': 'parent.json', 'byte_length': len(expected),
                  'sha256': 'sha256:' + hashlib.sha256(expected).hexdigest()}
    (tmp_path/'parent.json').write_bytes(expected)
    module.require_original_artifact(tmp_path, descriptor, 'parent.json', expected)
    (tmp_path/'parent.json').write_bytes(b'{"parent":2}')
    with pytest.raises(ValueError, match='artifact bytes'):
        module.require_original_artifact(tmp_path, descriptor, 'parent.json', expected)
    with pytest.raises(ValueError, match='artifact descriptor'):
        module.require_original_artifact(tmp_path, dict(descriptor, path='../parent.json'), 'parent.json', expected)


@pytest.mark.parametrize('value', [True, -1, 1.0])
def test_expanded_parent_audit_requires_known_integer_work(monkeypatch, value):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_expanded_same_parent_probe')
    module.require_work_counters({'core_calls': 1, 'newton_iterations': 4, 'linear_solves': 4})
    with pytest.raises(ValueError, match='integer work'):
        module.require_work_counters({'core_calls': value, 'newton_iterations': 4, 'linear_solves': 4})


def nested_fixture():
    import hashlib
    groups = [[f'{group}-{amp}' for amp in range(3)] for group in 'abcde']
    samples = [{'case_id': case, 'split': 'train',
                'sample_hash': 'sha256:' + hashlib.sha256(f'{case}-{i}'.encode()).hexdigest()}
               for group in groups for case in group for i in range(11)]
    return groups, samples


def test_nested_switch_labels_reject_single_exclusion_policy(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('prepare_rc_nested_switch_labels')
    groups, samples = nested_fixture()
    plan = module.nested_plan(groups, samples)
    assert len(plan['seed_fits']) == 10 and len(plan['label_tasks']) == 20
    assert all(len(fit['training_sample_hashes']) == 99 for fit in plan['seed_fits'])
    fit = plan['seed_fits'][0]
    policy = {'training_sample_hashes': fit['training_sample_hashes']}
    module.validate_seed_training_hashes(policy, fit)
    old_policy = {'training_sample_hashes': [s['sample_hash'] for s in samples if s['case_id'] not in groups[1]]}
    assert len(old_policy['training_sample_hashes']) == 132
    with pytest.raises(ValueError, match='both outer and inner'):
        module.validate_seed_training_hashes(old_policy, fit)
    assert module.nested_plan(list(reversed(groups)), list(reversed(samples))) == plan


@pytest.mark.parametrize('damage', ['overlap', 'duplicate', 'reserved', 'missing_case'])
def test_nested_switch_plan_rejects_ambiguous_training_provenance(monkeypatch, damage):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('prepare_rc_nested_switch_labels')
    groups, samples = nested_fixture()
    if damage == 'overlap':
        groups[-1].append(groups[0][0])
    elif damage == 'duplicate':
        samples.append(samples[0])
    elif damage == 'reserved':
        samples[0]['split'] = 'evaluation'
    else:
        samples = [s for s in samples if s['case_id'] != groups[0][0]]
    with pytest.raises(ValueError):
        module.nested_plan(groups, samples)


def guard_problem():
    from structural_analysis.io.neutral.loader import load_neutral_json
    from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
    return load_neutral_json(Path('examples/public_rc_fiber_frame_l_frame_material_history.json')), BoundedRCFiberDirectControlRequest(
        7, (-1e-6, -2e-6, 1e-6, 0.), allow_reversals=True, maximum_reversals=3)


def guard_run(tmp_path, guard, proposal):
    from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
    model, request = guard_problem()
    return benchmark_rc_control_seed_paths(model, request, source_revision='0'*40,
        output_directory=tmp_path/'run', proposal=proposal, proposal_identity='sha256:'+'a'*64,
        proposal_guard=guard, proposal_guard_identity='sha256:'+'b'*64,
        capture_material_state=True, material_capture_scope='proposal-only',
        proposal_abstention_strategy='secant')


def test_declined_guard_skips_capture_and_proposal_with_exact_secant_steps(tmp_path, monkeypatch):
    from structural_analysis.benchmark import rc_control_material_features as material
    def unexpected(*args):
        pytest.fail('declined guard reached capture or proposal')
    monkeypatch.setattr(material, 'committed_material_snapshot', unexpected)
    contexts = []
    def guard(context):
        contexts.append(context)
        assert context.committed_material_state_json is None
        return False
    report = guard_run(tmp_path, guard, unexpected)
    assert len(contexts) == 4 and report['comparisons']['proposal']['full_history_pass'] is True
    for index, entry in enumerate(report['arms']['proposal']['entries']):
        assert entry['proposal_guard']['allow_proposal'] is False
        assert type(entry['proposal_guard']['wall_ns']) is int
        assert 'committed_material_capture' not in entry
        assert (tmp_path/f'run/proposal/{index:03d}-1-step.json').read_bytes() == (tmp_path/f'run/secant/{index:03d}-1-step.json').read_bytes()
    assert all('proposal_guard' not in e for name in ('reference', 'secant') for e in report['arms'][name]['entries'])


def test_accepted_guard_precedes_capture_and_preserves_seed_validation(tmp_path, monkeypatch):
    from structural_analysis.benchmark import rc_control_material_features as material
    from structural_analysis.benchmark.rc_control_seed_runtime import secant_seed
    events=[]
    original=material.committed_material_snapshot
    def capture(*args):
        events.append('capture')
        return original(*args)
    monkeypatch.setattr(material, 'committed_material_snapshot', capture)
    def guard(context):
        assert context.committed_material_state_json is None
        events.append('guard')
        return True
    def propose(context):
        assert context.committed_material_state_json is not None
        events.append('proposal')
        return secant_seed(context)
    report=guard_run(tmp_path, guard, propose)
    assert events == ['guard', 'capture', 'proposal'] * 4
    assert report['comparisons']['proposal']['full_history_pass'] is True
    assert all('committed_material_capture' in e for e in report['arms']['proposal']['entries'])


@pytest.mark.parametrize('mode', ['nonboolean', 'exception'])
def test_failed_guard_is_recorded_and_cannot_pass_full_path(tmp_path, monkeypatch, mode):
    from structural_analysis.benchmark import rc_control_material_features as material
    def unexpected(*args):
        pytest.fail('failed guard reached capture or proposal')
    monkeypatch.setattr(material, 'committed_material_snapshot', unexpected)
    def guard(context):
        if mode == 'exception':
            raise RuntimeError('guard failed')
        return 1
    report=guard_run(tmp_path, guard, unexpected)
    arm=report['arms']['proposal']
    assert arm['status'] != 'complete'
    assert report['comparisons']['proposal']['full_history_pass'] is False
    assert arm['failure']['phase'] == 'proposal_guard'
    assert arm['entries'][0]['proposal_guard']['status'] == 'raised'
    assert arm['entries'][0]['invocations'] == []
    from structural_analysis.benchmark.rc_control_runtime_selection import _runtime_score
    assert _runtime_score(report, [])['proposal_over_secant_path_wall_ratio'] is None


def test_guard_timing_is_separate_and_not_hidden_in_remainder():
    arm={'wall_ns':100, 'preload_invocations':[], 'entries':[{
        'invocations':[{'wall_ns':20,'unknown_work':False}], 'recovery_wall_ns':10,
        'proposal_wall_ns':5, 'proposal_guard':{'wall_ns':7}}]}
    result=decompose(arm,0)
    assert result['proposal_guard']==7 and result['remaining_unattributed']==58
    assert sum(result.values())==100


@pytest.mark.parametrize('change', [ {'proposal_guard_identity':None}, {'proposal':None},
    {'proposal_guard':42}, {'proposal_guard_identity':'unbound'}, {'proposal_abstention_strategy':'reference'}])
def test_guard_configuration_rejected_before_output(tmp_path, change):
    from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
    options=dict(proposal=lambda context:None,proposal_identity='sha256:'+'a'*64,
        proposal_guard=lambda context:False,proposal_guard_identity='sha256:'+'b'*64,
        proposal_abstention_strategy='secant')
    options.update(change)
    with pytest.raises(ValueError, match='identified proposal guard'):
        benchmark_rc_control_seed_paths(None,None,source_revision='guard-test',output_directory=tmp_path/'run',**options)
    assert not (tmp_path/'run').exists()


def nested_label_reader(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    return importlib.import_module('audit_rc_nested_switch_labels').label_from_repetitions


def nested_repeats():
    return [dict(repetition=i, comparison_pass=True, decision='proposed', path_time_ratio=.98) for i in range(3)]


def test_nested_label_requires_every_repeat_and_actual_proposals(monkeypatch):
    label = nested_label_reader(monkeypatch)
    rows = nested_repeats()
    assert label(rows)['label'] is True
    rows[1]['path_time_ratio'] = .995
    assert label(rows)['label'] is False
    rows[1]['path_time_ratio'] = .98
    rows[2]['decision'] = 'abstained'
    assert label(rows)['label'] is False
    rows[2]['comparison_pass'] = False
    rows[2]['path_time_ratio'] = None
    assert label(rows)['label'] is None
    assert label(rows)['status'] == 'unverified'


@pytest.mark.parametrize('ratio', [True, 0, -1, float('nan'), float('inf'), None, '0.98'])
def test_nested_label_rejects_invalid_measured_cost(monkeypatch, ratio):
    rows = nested_repeats()
    rows[1]['path_time_ratio'] = ratio
    with pytest.raises(ValueError, match='positive finite measured ratios'):
        nested_label_reader(monkeypatch)(rows)


@pytest.mark.parametrize('repetitions', [[0, 0, 2], [0, 1], [False, 1, 2]])
def test_nested_label_rejects_missing_or_ambiguous_repetition(monkeypatch, repetitions):
    rows = [dict(repetition=i, comparison_pass=True, decision='proposed', path_time_ratio=.98) for i in repetitions]
    with pytest.raises(ValueError, match='three unique original repetitions'):
        nested_label_reader(monkeypatch)(rows)


def test_switch_features_ignore_material_state_and_prefix_length():
    from dataclasses import replace
    from types import SimpleNamespace
    from scripts.rc_switch_prefix_features import prefix_features, PROFILE
    from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext
    context = RCControlSeedContext('compiled', 7, 0, .003, (.001, .002), ((.001, 1.), (.002, 2.)))
    model = SimpleNamespace(problem_contract_hash='compiled', feature_names=('width',), values=(.4,))
    expected = prefix_features(context, model)
    changed = replace(context, committed_material_state_json='not parsed',
        accepted_targets_m=(0., *context.accepted_targets_m),
        accepted_augmented_coordinates_m=((0., 0.), *context.accepted_augmented_coordinates_m))
    assert prefix_features(changed, model) == expected
    assert expected['profile'] == PROFILE
    assert expected['feature_names'] == ['model.width', 'target_m', 'target_increment_m',
        'previous_target_increment_m', 'last_coordinate_0', 'last_coordinate_1',
        'coordinate_increment_0', 'coordinate_increment_1']
    assert expected['values'] == [.4, .003, .001, .001, .002, 2., .001, 1.]
