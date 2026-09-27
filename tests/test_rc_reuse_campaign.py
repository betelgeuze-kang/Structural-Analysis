"""Campaign retention, frozen input identity, and failed-case accounting."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_rc_reuse_campaign as campaign


ROOT = Path(__file__).resolve().parents[1]


def plan(tmp_path, names=('failed', 'later')):
    (tmp_path / 'model.json').write_text('{"original":true}')
    (tmp_path / 'request.json').write_bytes(
        (ROOT / 'examples/public_rc_fiber_frame_constant_axial_control_request.json').read_bytes()
    )
    payload = {'schema': 'rc-reuse-campaign-plan.v1', 'repetitions': 2,
               'arithmetic': 'retained', 'record_assembly_timing': True,
               'cases': [{'id': n, 'model': 'model.json', 'request': 'request.json'}
                         for n in names]}
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(payload))
    return path, payload


def write_success(output, *, source, model_raw, request_raw):
    output.mkdir()
    request = campaign.decode_bounded_rc_fiber_direct_control_request(request_raw)
    comparisons = {
        name: {'full_history_pass': True} for name in ('reference', 'secant', 'proposal')
    }
    report = {
        'schema_version': 'experimental-rc-control-seed-comparison.v2',
        'source_revision': source, 'source_revision_is_attestation': False,
        'request': request.to_dict(), 'arm_order': ['reference', 'secant', 'proposal'],
        'proposal_requested': True, 'reference_repeat_exact': True,
        'all_execution_work_reported': True,
        'arms': {name: {'status': 'complete'} for name in comparisons},
        'fresh_reference': {'status': 'complete'}, 'comparisons': comparisons,
    }
    report['report_hash'] = 'sha256:' + hashlib.sha256(
        campaign.canonical_bytes(report)
    ).hexdigest()
    rows = []
    for repetition in range(2):
        pair = {}
        for strategy, enabled in (('baseline', False), ('reuse', True)):
            name = f'retained-True-constant-False-rep-{repetition}-{enabled}'
            benchmark = output / name
            (benchmark / 'reference').mkdir(parents=True)
            (benchmark / 'reference' / 'target-0-step.json').write_text('{"state":1}')
            count = 8 if enabled else 10
            work = {
                'schema_version': 'vector-newton-assembly-dispatch-work.v1',
                'scope': 'vector_newton_problem_assembly_dispatches_only',
                'call_count': count, 'returned_count': count,
                'exception_count': 0, 'in_flight_count': 0,
                'calls': [
                    {'ordinal': ordinal, 'phase': 'primary_iteration',
                     'status': 'returned', 'compensated': False}
                    for ordinal in range(1, count + 1)
                ],
                **({'line_search_reuse_hit_count': 2} if enabled else {}),
            }
            (benchmark / 'reference' / 'target-0-outcome.json').write_text(
                json.dumps({'status': 'returned', 'newton_assembly_work': work})
            )
            (benchmark / 'comparison.json').write_text(json.dumps(report))
            pair[strategy] = {
                'directory': name, 'wall_ns': 1000 if not enabled else 900,
                'step_count': 1, 'actual_newton_dispatches': 10 if not enabled else 8,
                'reused_dispatches': 0 if not enabled else 2,
            }
        rows.append({
            'retained': True, 'constant': True, 'repetition': repetition,
            'order': [False, True] if repetition % 2 == 0 else [True, False],
            **pair, 'native_step_bytes_exact': True, 'whole_benchmark_wall_ratio': 0.9,
        })
    summary = {
        'schema': 'rc-immediate-line-search-reuse-experiment.v1',
        'base_revision': source,
        'script_sha256': hashlib.sha256(Path(campaign.experiment.__file__).read_bytes()).hexdigest(),
        'model_sha256': hashlib.sha256(model_raw).hexdigest(),
        'scope': 'one supplied model and unmodified supplied request',
        'case': 'supplied', 'arithmetic_selection': 'retained',
        'implementation': 'native',
        'timing_scope': 'whole benchmark including serialization, verification, and recording',
        'default_solver_changed': False, 'learned_policy': False,
        'independent_physical_validation': False, 'concurrent_execution_supported': False,
        'rows': rows, 'supplied_request_sha256': hashlib.sha256(request_raw).hexdigest(),
        'supplied_target_count': len(request.targets_m),
        'supplied_constant_load_count': len(request.constant_nodal_loads),
        'assembly_timing_recording': True,
    }
    (output / 'summary.json').write_text(json.dumps(summary))
    return summary


def test_complete_source_bound_two_repetition_receipt_is_accepted(tmp_path, monkeypatch):
    path, _ = plan(tmp_path, names=('valid',))
    source = campaign.subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()

    def execute(output, repetitions, **kwargs):
        assert repetitions == 2
        write_success(
            output, source=source, model_raw=kwargs['model_path'].read_bytes(),
            request_raw=kwargs['request_path'].read_bytes(),
        )

    monkeypatch.setattr(campaign.experiment, 'run', execute)
    output = tmp_path / 'output'
    assert campaign.run(path, output) is True
    receipt = json.loads((output / 'campaign.json').read_text())
    assert receipt['campaign_complete'] and receipt['all_cases_completed']
    assert receipt['aggregate_speed_ratio'] is None
    assert receipt['cases'][0]['status'] == 'completed'


def test_failed_case_retained_later_case_runs_on_frozen_inputs(tmp_path, monkeypatch):
    path, _ = plan(tmp_path)
    original_model = (tmp_path / 'model.json').read_bytes()
    source = campaign.subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    seen = []

    def execute(output, repetitions, **kwargs):
        seen.append((output.parent.name, kwargs['model_path'].read_bytes()))
        assert repetitions == 2 and kwargs['record_assembly_timing'] is True
        if len(seen) == 1:
            output.mkdir()
            (tmp_path / 'model.json').write_text('changed after campaign freeze')
            (output / 'failure.json').write_text('{"whole_benchmark_wall_ratio":null}')
            raise ValueError('original full-history failure')
        summary = write_success(
            output, source=source, model_raw=kwargs['model_path'].read_bytes(),
            request_raw=kwargs['request_path'].read_bytes(),
        )
        summary['rows'] = []
        (output / 'summary.json').write_text(json.dumps(summary))

    monkeypatch.setattr(campaign.experiment, 'run', execute)
    output = tmp_path / 'output'
    assert campaign.run(path, output) is False
    assert [n for n, _ in seen] == ['failed', 'later']
    assert seen[0][1] == seen[1][1] == original_model
    receipt = json.loads((output / 'campaign.json').read_text())
    assert receipt['campaign_complete'] and not receipt['all_cases_completed']
    assert receipt['aggregate_speed_ratio'] is None
    assert receipt['cases'][0]['error']['message'] == 'original full-history failure'
    assert receipt['cases'][1]['status'] == 'failed'
    assert 'repetition count mismatch' in receipt['cases'][1]['error']['message']
    assert all(r['case_wall_ns'] >= 0 for r in receipt['cases'])
    assert sum(r['case_wall_ns'] for r in receipt['cases']) <= receipt['campaign_wall_ns_through_receipt']
    for row in receipt['cases']:
        for bound in row['receipts'].values():
            raw = (output / bound['path']).read_bytes()
            assert len(raw) == bound['bytes']
            assert hashlib.sha256(raw).hexdigest() == bound['sha256']
    with pytest.raises(FileExistsError):
        campaign.run(path, output)
    assert len(seen) == 2


@pytest.mark.parametrize('mutation', [
    'duplicate_pair', 'wrong_order', 'nonboolean_order', 'model_hash', 'request_hash',
    'missing_comparison', 'resealed_failed_history', 'changed_native_step', 'wrong_ratio',
    'inflated_dispatches', 'missing_outcome', 'malformed_outcome',
    'duplicate_outcome_key',
])
def test_invalid_saved_receipt_fails_case_but_preserves_original_and_runs_later(
    tmp_path, monkeypatch, mutation
):
    path, _ = plan(tmp_path, names=('invalid', 'later'))
    source = campaign.subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()

    def execute(output, repetitions, **kwargs):
        summary = write_success(
            output, source=source, model_raw=kwargs['model_path'].read_bytes(),
            request_raw=kwargs['request_path'].read_bytes(),
        )
        if output.parent.name != 'invalid':
            return
        if mutation == 'duplicate_pair':
            summary['rows'][1] = deepcopy(summary['rows'][0])
        elif mutation == 'wrong_order':
            summary['rows'][1]['order'] = [False, True]
        elif mutation == 'nonboolean_order':
            summary['rows'][0]['order'] = [0, 1]
        elif mutation == 'model_hash':
            summary['model_sha256'] = '0' * 64
        elif mutation == 'request_hash':
            summary['supplied_request_sha256'] = '0' * 64
        elif mutation == 'missing_comparison':
            (output / summary['rows'][0]['baseline']['directory'] / 'comparison.json').unlink()
        elif mutation == 'resealed_failed_history':
            report_path = output / summary['rows'][0]['baseline']['directory'] / 'comparison.json'
            report = json.loads(report_path.read_text())
            report['comparisons']['proposal']['full_history_pass'] = False
            report.pop('report_hash')
            report['report_hash'] = 'sha256:' + hashlib.sha256(
                campaign.canonical_bytes(report)
            ).hexdigest()
            report_path.write_text(json.dumps(report))
        elif mutation == 'changed_native_step':
            (output / summary['rows'][0]['reuse']['directory'] /
             'reference/target-0-step.json').write_text('{"state":2}')
        elif mutation == 'inflated_dispatches':
            for strategy in ('baseline', 'reuse'):
                summary['rows'][0][strategy]['actual_newton_dispatches'] += 1
        elif mutation in ('missing_outcome', 'malformed_outcome',
                          'duplicate_outcome_key'):
            outcome_path = (output / summary['rows'][0]['baseline']['directory'] /
                            'reference/target-0-outcome.json')
            if mutation == 'missing_outcome':
                outcome_path.unlink()
            else:
                outcome = json.loads(outcome_path.read_text())
                if mutation == 'malformed_outcome':
                    outcome['newton_assembly_work']['call_count'] = True
                    outcome_path.write_text(json.dumps(outcome))
                else:
                    outcome_path.write_text(
                        '{"status":"returned",' + json.dumps(outcome)[1:]
                    )
        else:
            summary['rows'][0]['whole_benchmark_wall_ratio'] = 0.5
        (output / 'summary.json').write_text(json.dumps(summary))

    monkeypatch.setattr(campaign.experiment, 'run', execute)
    output = tmp_path / 'output'
    assert campaign.run(path, output) is False
    receipt = json.loads((output / 'campaign.json').read_text())
    assert receipt['campaign_complete'] and not receipt['all_cases_completed']
    assert [row['status'] for row in receipt['cases']] == ['failed', 'completed']
    assert receipt['aggregate_speed_ratio'] is None
    raw = (output / 'invalid/results/summary.json').read_bytes()
    assert receipt['cases'][0]['receipts']['summary.json']['sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('change', ['duplicate', 'traversal', 'bool_repeats', 'unknown', 'missing_file'])
def test_plan_rejected_before_execution_or_output(tmp_path, monkeypatch, change):
    path, payload = plan(tmp_path)
    if change == 'duplicate':
        payload['cases'][1]['id'] = 'failed'
    elif change == 'traversal':
        payload['cases'][0]['id'] = '../outside'
    elif change == 'bool_repeats':
        payload['repetitions'] = True
    elif change == 'unknown':
        payload['unvalidated'] = True
    else:
        payload['cases'][1]['model'] = 'missing.json'
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(campaign.experiment, 'run', lambda *a, **k: pytest.fail('must not execute'))
    with pytest.raises((ValueError, FileNotFoundError)):
        campaign.run(path, tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_duplicate_json_key_and_interrupt_are_not_silently_accepted(tmp_path, monkeypatch):
    path, payload = plan(tmp_path)
    path.write_text('{"schema":1,"schema":2}')
    with pytest.raises(ValueError):
        campaign.run(path, tmp_path / 'output')
    path.write_text(json.dumps(payload))

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(campaign.experiment, 'run', interrupted)
    with pytest.raises(KeyboardInterrupt):
        campaign.run(path, tmp_path / 'output')
    assert not (tmp_path / 'output/campaign.json').exists()


def test_return_without_success_receipt_is_not_completion(tmp_path, monkeypatch):
    path, _ = plan(tmp_path)
    monkeypatch.setattr(campaign.experiment, 'run', lambda *a, **k: None)
    assert campaign.run(path, tmp_path / 'output') is False
    receipt = json.loads((tmp_path / 'output/campaign.json').read_text())
    assert receipt['recorded_case_count'] == 2
    assert all(r['status'] == 'failed' for r in receipt['cases'])
    assert all('without its success receipt' in r['error']['message'] for r in receipt['cases'])
