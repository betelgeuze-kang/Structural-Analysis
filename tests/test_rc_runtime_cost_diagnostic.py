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
