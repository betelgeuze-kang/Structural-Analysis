"""Protect additive timing attribution and unknown-work boundaries."""
import pytest
import importlib
from pathlib import Path

from scripts.diagnose_expanded_rc_runtime_costs import decompose


def _summary_snapshot(change=None):
    from dataclasses import asdict
    from structural_analysis.benchmark.rc_control_design import _bytes, _sha
    from structural_analysis.benchmark.rc_control_material_features import MATERIAL_SNAPSHOT_SCHEMA
    from structural_analysis.materials.concrete_damage import ConcreteDamageState
    from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState
    pairs = []
    for index, (kind, state) in enumerate([
        ('steel', UniaxialPlasticityState(plastic_strain=-0.02, accumulated_plastic_strain=0.03)),
        ('steel', UniaxialPlasticityState(plastic_strain=0.01, accumulated_plastic_strain=0.04)),
        ('concrete', ConcreteDamageState(tensile_damage=0.2)),
        ('concrete', ConcreteDamageState(tensile_damage=0.6)),
    ]):
        pairs.extend((f'member_0_point_0_fiber_{index}_{kind}_{field}', value)
                     for field, value in asdict(state).items())
    if change is not None:
        change(pairs)
    body = dict(schema_version=MATERIAL_SNAPSHOT_SCHEMA,
                problem_contract_hash='sha256:' + '1' * 64,
                parent_state_hash='sha256:' + '2' * 64,
                feature_names=[name for name, _ in pairs], values=[value for _, value in pairs])
    body['snapshot_hash'] = _sha(_bytes(body))
    return _bytes(body).decode()


def test_material_summary_keeps_signed_states_and_order_independent_unweighted_statistics():
    from scripts.rc_accepted_material_summary import accepted_material_summary
    args = ('sha256:' + '1' * 64, 'sha256:' + '2' * 64)
    result = accepted_material_summary(_summary_snapshot(), *args)
    values = dict(zip(result['feature_names'], result['values'], strict=True))
    assert len(values) == 27
    assert result['fiber_counts'] == {'steel': 2, 'concrete': 2}
    assert values['steel.plastic_strain.min'] == -0.02
    assert values['steel.plastic_strain.mean'] == -0.005
    assert values['steel.plastic_strain.max'] == 0.01
    assert values['concrete.tensile_damage.mean'] == pytest.approx(0.4)
    reordered = accepted_material_summary(_summary_snapshot(lambda pairs: pairs.reverse()), *args)
    assert reordered['values'] == result['values']
    assert reordered['snapshot_hash'] != result['snapshot_hash']


@pytest.mark.parametrize('parent', [None, '', 'sha256:' + '3' * 64])
def test_material_summary_requires_explicit_matching_parent(parent):
    from scripts.rc_accepted_material_summary import accepted_material_summary
    with pytest.raises(ValueError):
        accepted_material_summary(_summary_snapshot(), 'sha256:' + '1' * 64, parent)


@pytest.mark.parametrize('change', [
    lambda pairs: pairs.pop(),
    lambda pairs: pairs.__setitem__(0, (pairs[0][0].replace('plastic_strain', 'unknown'), 0.0)),
    lambda pairs: pairs.__setitem__(0, (pairs[0][0].replace('member_0', 'member_00'), 0.0)),
    lambda pairs: pairs.__setitem__(-1, (pairs[-1][0], -1.0)),
    lambda pairs: pairs.__setitem__(10, (pairs[10][0], 1.0)),
    lambda pairs: pairs.__setitem__(slice(None), [p for p in pairs if '_steel_' in p[0]]),
    lambda pairs: pairs.__setitem__(8, (pairs[8][0].replace('fiber_2', 'fiber_0'), 0.0)),
])
def test_material_summary_rejects_rehashed_incomplete_or_invalid_native_states(change):
    from scripts.rc_accepted_material_summary import accepted_material_summary
    with pytest.raises(ValueError):
        accepted_material_summary(_summary_snapshot(change), 'sha256:' + '1' * 64, 'sha256:' + '2' * 64)


def test_material_summary_audit_preserves_split_declarations_before_reading_parents(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_accepted_material_summaries')
    cases = [SimpleNamespace(split='train'), SimpleNamespace(split='validation')]
    monkeypatch.setattr(module, 'inputs', lambda *args: (cases, [], None, [], []))
    seen = []
    monkeypatch.setattr(module.learning, '_preflight', lambda roster, arithmetic: seen.append(roster) or {})
    def stop_before_parents(*args):
        raise RuntimeError('stop before parent reads')
    monkeypatch.setattr(module, 'reader', stop_before_parents)
    monkeypatch.setattr(sys, 'argv', ['audit', '--old-labels', str(tmp_path / 'old'),
        '--new-labels', str(tmp_path / 'new'), '--output', str(tmp_path / 'output'),
        '--source-revision', 'a' * 40])
    with pytest.raises(RuntimeError, match='stop before parent reads'):
        module.main()
    assert seen == [cases]
    assert not (tmp_path / 'output').exists()


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


def gate_row_fixture(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('rc_switch_gate_training_rows')
    groups = [['a'], ['b'], ['c']]
    tasks, rows = [], []
    for outer in range(3):
        for inner in range(3):
            if outer == inner:
                continue
            sample = 'sha256:' + str(inner) * 64
            task = dict(outer_group_index=outer, inner_group_index=inner,
                label_source_sample_hashes=[sample], label_case_ids=groups[inner],
                outer_evaluation_case_ids=groups[outer], seed_fit_index=len(tasks))
            tasks.append(task)
            repeats = nested_repeats()
            rows.append(dict(outer_group_index=outer, inner_group_index=inner,
                source_sample_hash=sample, case_id=groups[inner][0],
                seed_fit_index=task['seed_fit_index'], repetitions=repeats,
                label_result=module.label_from_repetitions(repeats),
                guard_features=dict(profile=module.PROFILE, feature_names=['target_m'], values=[.001])))
    return module, dict(pairs=rows), dict(groups=groups, label_tasks=tasks)


def test_gate_training_rows_exclude_outer_and_retain_unknown_denominator(monkeypatch):
    module, audit, plan = gate_row_fixture(monkeypatch)
    row = audit['pairs'][0]
    row['repetitions'][0]['comparison_pass'] = False
    row['repetitions'][0]['path_time_ratio'] = None
    row['label_result'] = module.label_from_repetitions(row['repetitions'])
    result = module.gate_training_rows(audit, plan, 0)
    assert result['excluded_case_ids'] == ['a']
    assert [row['case_id'] for row in result['training_rows']] == ['c']
    assert [row['case_id'] for row in result['unverified_rows']] == ['b']
    assert result['verified_positive_count'] == 1
    assert result['gate_fitted'] is False


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'outer_case', 'seed', 'label', 'nonfinite'])
def test_gate_training_rows_reject_transplanted_or_incomplete_inputs(monkeypatch, mutation):
    module, audit, plan = gate_row_fixture(monkeypatch)
    row = audit['pairs'][0]
    if mutation == 'missing':
        audit['pairs'].pop()
    elif mutation == 'duplicate':
        audit['pairs'][-1] = row
    elif mutation == 'outer_case':
        row['case_id'] = 'a'
    elif mutation == 'seed':
        row['seed_fit_index'] += 1
    elif mutation == 'label':
        row['label_result']['label'] = False
    else:
        row['guard_features']['values'][0] = float('nan')
    with pytest.raises(ValueError):
        module.gate_training_rows(audit, plan, 0)


def test_gate_training_rows_are_invariant_to_report_serialization_order(monkeypatch):
    module, audit, plan = gate_row_fixture(monkeypatch)
    original = module.gate_training_rows(audit, plan, 1)
    audit['pairs'].reverse()
    assert module.gate_training_rows(audit, plan, 1) == original


def fitted_gate_fixture(monkeypatch, positive=True):
    module, audit, plan = gate_row_fixture(monkeypatch)
    if not positive:
        for row in audit['pairs']:
            row['repetitions'][0]['path_time_ratio'] = 1.1
            row['label_result'] = module.label_from_repetitions(row['repetitions'])
    training = module.gate_training_rows(audit, plan, 0)
    gate_module = importlib.import_module('rc_switch_gate')
    gate, receipt = gate_module.fit_gate(training)
    features = dict(profile=module.PROFILE, feature_names=['target_m'], values=[.001])
    return gate_module, gate, receipt, features, training


def test_fixed_gate_retains_decline_and_individual_bounds(monkeypatch):
    _, gate, receipt, features, training = fitted_gate_fixture(monkeypatch)
    assert gate.decision(features) is True
    assert receipt['verified_rows'] == len(training['training_rows'])
    assert receipt['fit_wall_ns'] > 0
    features['values'] = [.002]
    assert gate.decision(features) is False
    _, negative, _, features, _ = fitted_gate_fixture(monkeypatch, False)
    assert negative.decision(features) is False


def test_gate_normalization_and_identity_come_from_excluded_training_only(monkeypatch):
    import json
    module, gate, _, _, training = fitted_gate_fixture(monkeypatch)
    payload = json.loads(gate._json)
    assert payload['mean'] == [.001] and payload['scale'] == [1.0]
    assert payload['excluded_case_ids'] == ['a']
    assert payload['training_sample_hashes'] == [r['source_sample_hash'] for r in training['training_rows']]
    with pytest.raises(TypeError):
        gate._payload['threshold'] = 0
    payload['weights'][-1] += 1
    with pytest.raises(ValueError, match='gate hash mismatch'):
        module.RidgeGate(json.dumps(payload))
    training['training_rows'][0]['case_id'] = 'a'
    with pytest.raises(ValueError, match='outer group cannot enter gate fit'):
        module.fit_gate(training)


def test_gate_rejects_ambiguous_json_and_foreign_features(monkeypatch):
    module, gate, _, features, _ = fitted_gate_fixture(monkeypatch)
    with pytest.raises(ValueError):
        module.RidgeGate('{"threshold":0,' + gate._json[1:])
    features['feature_names'] = ['foreign']
    with pytest.raises(ValueError, match='gate feature binding'):
        gate.decision(features)


def test_gate_augmented_ridge_fit_matches_known_two_row_solution(monkeypatch):
    module, _, _, _, training = fitted_gate_fixture(monkeypatch)
    training['training_rows'][0].update(values=[-1.0], label=False)
    training['training_rows'][1].update(values=[1.0], label=True)
    training['verified_positive_count'] = training['verified_negative_count'] = 1
    gate, _ = module.fit_gate(training)
    assert gate._payload['mean'] == (0.0,)
    assert gate._payload['scale'] == (1.0,)
    assert gate._payload['weights'] == pytest.approx((1.0 / 3.0, .5))
    features = dict(profile=module.PROFILE, feature_names=['target_m'], values=[1.0])
    assert gate.decision(features) is True
    features['values'] = [-1.0]
    assert gate.decision(features) is False


def test_gate_repeated_decimal_constant_has_exact_center_and_unit_scale(monkeypatch):
    module, _, _, _, training = fitted_gate_fixture(monkeypatch)
    training['training_rows'] = [dict(training['training_rows'][0],
        values=[.02], source_sample_hash='sha256:' + format(i, '064x')) for i in range(132)]
    training['verified_positive_count'] = 132
    training['verified_negative_count'] = 0
    gate, _ = module.fit_gate(training)
    assert gate._payload['mean'] == (.02,)
    assert gate._payload['scale'] == (1.0,)
    assert gate.decision(dict(profile=module.PROFILE, feature_names=['target_m'], values=[.02])) is True


def cost_gate_fixture(monkeypatch):
    _, audit, plan = gate_row_fixture(monkeypatch)
    module = importlib.import_module('rc_cost_margin_gate')
    for row in audit['pairs']:
        for repetition in row['repetitions']:
            repetition['report_hash'] = 'sha256:' + format(repetition['repetition'], '064x')
    return module, audit, plan


def test_cost_target_keeps_worst_repeat_loss_and_no_abstention_gain(monkeypatch):
    module, _, _ = cost_gate_fixture(monkeypatch)
    repeats = nested_repeats()
    repeats[1]['path_time_ratio'] = 1.4
    assert module.cost_target(repeats) == pytest.approx(-.4)
    repeats[1]['path_time_ratio'] = .98
    assert module.cost_target(repeats) == pytest.approx(.02)
    repeats[1]['decision'] = 'abstained_to_secant'
    assert module.cost_target(repeats) == 0.
    repeats[1]['comparison_pass'] = False
    repeats[1]['path_time_ratio'] = None
    assert module.cost_target(repeats) is None


def test_cost_training_rows_preserve_exclusion_and_measured_reports(monkeypatch):
    module, audit, plan = cost_gate_fixture(monkeypatch)
    training = module.cost_training_rows(audit, plan, 0)
    assert training['excluded_case_ids'] == ['a']
    assert all(row['case_id'] != 'a' and row['cost_target'] == pytest.approx(.02)
               and len(row['cost_repetitions']) == 3 for row in training['training_rows'])
    gate, receipt = module.fit_cost_gate(training)
    assert gate._payload['threshold'] == .01
    assert receipt['gate_cost_in_training_target'] is False
    assert gate.decision(dict(profile=training['feature_profile'],
                              feature_names=training['feature_names'], values=[.001])) is True
    original = importlib.import_module('rc_switch_gate')
    with pytest.raises(ValueError, match='fixed gate profile'):
        original.RidgeGate(gate._json)


@pytest.mark.parametrize('mutation', ['target', 'label', 'outer', 'profile', 'unverified'])
def test_cost_fit_rejects_changed_targets_and_scope(monkeypatch, mutation):
    module, audit, plan = cost_gate_fixture(monkeypatch)
    training = module.cost_training_rows(audit, plan, 0)
    row = training['training_rows'][0]
    if mutation == 'target':
        row['cost_target'] = .5
    elif mutation == 'label':
        row['label'] = False
    elif mutation == 'outer':
        row['case_id'] = 'a'
    elif mutation == 'profile':
        training['cost_target_profile'] = 'other'
    else:
        row['cost_repetitions'][0]['comparison_pass'] = False
        row['cost_repetitions'][0]['path_time_ratio'] = None
    with pytest.raises(ValueError):
        module.fit_cost_gate(training)


def test_cost_margin_fit_matches_known_two_row_ridge_solution(monkeypatch):
    module, audit, plan = cost_gate_fixture(monkeypatch)
    training = module.cost_training_rows(audit, plan, 0)
    for row, x, ratio in zip(training['training_rows'], [-1., 1.], [1.25, .5]):
        row['values'] = [x]
        for repetition in row['cost_repetitions']:
            repetition['path_time_ratio'] = ratio
        row['cost_target'] = module.cost_target(row['cost_repetitions'])
        row['label'] = ratio <= .99
    gate, _ = module.fit_cost_gate(training)
    assert gate._payload['weights'] == pytest.approx((.25, .125))


def material_gate_fixture(monkeypatch):
    from copy import deepcopy
    from scripts.rc_accepted_material_summary import accepted_material_summary
    cost, audit, plan = cost_gate_fixture(monkeypatch)
    training = cost.cost_training_rows(audit, plan, 0)
    module = importlib.import_module('rc_material_cost_gate')
    monkeypatch.setattr(module, 'cost_training_rows', lambda *args: deepcopy(training))
    summary = accepted_material_summary(_summary_snapshot(), 'sha256:' + '1' * 64, 'sha256:' + '2' * 64)
    rows = []
    for i in range(165):
        source = (training['training_rows'][i] if i < len(training['training_rows']) else
                  dict(source_sample_hash=f'sha256:{i:064x}', case_id='other'))
        rows.append(dict(source_sample_hash=source['source_sample_hash'], case_id=source['case_id'],
                         original_step_bytes_hash='sha256:' + '3' * 64, summary=deepcopy(summary)))
    audit = dict(pairs=[dict(source_sample_hash=row['source_sample_hash'], case_id=row['case_id'],
                            parent_hash=summary['parent_state_hash']) for row in rows])
    summaries = dict(profile=summary['profile'], groups=plan['groups'], row_count=165,
                     feature_count=27, rows=rows)
    return module, audit, plan, summaries


def test_material_gate_preserves_cost_target_and_exclusion_but_has_no_runtime_adapter(monkeypatch):
    module, audit, plan, summaries = material_gate_fixture(monkeypatch)
    training = module.material_training_rows(audit, plan, summaries, 0)
    gate, receipt = module.fit_material_gate(training)
    assert len(training['feature_names']) == 28
    assert gate._payload['excluded_case_ids'] == ('a',)
    assert gate._payload['threshold'] == .01 and gate._payload['ridge'] == 1.0
    assert receipt['online_extraction_cost_in_target'] is False
    with pytest.raises(ValueError, match='no cost-validated runtime adapter'):
        gate.guard(None)
    with pytest.raises(ValueError, match='fixed gate profile'):
        importlib.import_module('rc_cost_margin_gate').CostMarginGate(gate._json)
    assert gate.decision(dict(profile=module.PROFILE, feature_names=training['feature_names'],
                              values=training['training_rows'][0]['values']))


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'foreign', 'case', 'parent', 'nan', 'names'])
def test_material_gate_rejects_incomplete_or_transplanted_parent_joins(monkeypatch, mutation):
    module, audit, plan, summaries = material_gate_fixture(monkeypatch)
    row = summaries['rows'][0]
    if mutation == 'missing':
        summaries['rows'].pop()
    elif mutation == 'duplicate':
        summaries['rows'][-1] = row
    elif mutation == 'foreign':
        row['source_sample_hash'] = 'sha256:' + 'f' * 64
    elif mutation == 'case':
        row['case_id'] = 'foreign'
    elif mutation == 'parent':
        row['summary']['parent_state_hash'] = 'sha256:' + 'f' * 64
    elif mutation == 'nan':
        row['summary']['values'][0] = float('nan')
    else:
        row['summary']['feature_names'][0] = 'foreign'
    with pytest.raises(ValueError):
        module.material_training_rows(audit, plan, summaries, 0)


def test_guarded_runtime_score_includes_policy_setup_and_full_path_validity(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_rc_guarded_runtime_campaign import score_path
    report = guard_run(tmp_path, lambda context: False, lambda context: pytest.fail('declined proposer called'))
    decisions = [dict(decision=e['proposal_decision']) for e in report['arms']['proposal']['entries']]
    score = score_path(report, decisions, 12345)
    assert score['full_comparison_pass'] is True
    assert score['proposal_scored_wall_ns'] == report['arms']['proposal']['wall_ns'] + 12345
    assert score['proposal_over_secant_path_wall_ratio'] == score['proposal_scored_wall_ns'] / report['arms']['secant']['wall_ns']
    report['reference_repeat_exact'] = False
    assert score_path(report, decisions, 12345)['proposal_over_secant_path_wall_ratio'] is None


def test_guarded_audit_retains_fallback_timing_and_full_arm_binding(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    from audit_rc_guarded_runtime_campaign import require_arm_summary, require_declined_guard
    summary = dict(path_hash='bound', status='complete')
    require_arm_summary(dict(summary, response_history=[1], terminal_checkpoint={}, preload_response={}), summary)
    with pytest.raises(ValueError):
        require_arm_summary(dict(summary, status='failed'), summary)
    entry = dict(proposal_decision='abstained_to_secant', proposal_wall_ns=100)
    require_declined_guard(entry, {})
    with pytest.raises(ValueError):
        require_declined_guard(entry, dict(committed_material_state_json='captured'))
