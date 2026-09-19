"""Campaign retention, frozen input identity, and failed-case accounting."""
import hashlib
import json

import pytest

from scripts import run_rc_reuse_campaign as campaign


def plan(tmp_path):
    (tmp_path / 'model.json').write_text('{"original":true}')
    (tmp_path / 'request.json').write_text('{}')
    payload = {'schema': 'rc-reuse-campaign-plan.v1', 'repetitions': 2,
               'arithmetic': 'retained', 'record_assembly_timing': True,
               'cases': [{'id': n, 'model': 'model.json', 'request': 'request.json'}
                         for n in ('failed', 'later')]}
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(payload))
    return path, payload


def test_failed_case_retained_later_case_runs_on_frozen_inputs(tmp_path, monkeypatch):
    path, _ = plan(tmp_path)
    seen = []

    def execute(output, repetitions, **kwargs):
        seen.append((output.parent.name, kwargs['model_path'].read_bytes()))
        assert repetitions == 2 and kwargs['record_assembly_timing'] is True
        output.mkdir()
        if len(seen) == 1:
            (tmp_path / 'model.json').write_text('changed after campaign freeze')
            (output / 'failure.json').write_text('{"whole_benchmark_wall_ratio":null}')
            raise ValueError('original full-history failure')
        (output / 'summary.json').write_text('{"rows":[]}')

    monkeypatch.setattr(campaign.experiment, 'run', execute)
    output = tmp_path / 'output'
    assert campaign.run(path, output) is False
    assert [n for n, _ in seen] == ['failed', 'later']
    assert seen[0][1] == seen[1][1] == b'{"original":true}'
    receipt = json.loads((output / 'campaign.json').read_text())
    assert receipt['campaign_complete'] and not receipt['all_cases_completed']
    assert receipt['aggregate_speed_ratio'] is None
    assert receipt['cases'][0]['error']['message'] == 'original full-history failure'
    assert receipt['cases'][1]['status'] == 'completed'
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
