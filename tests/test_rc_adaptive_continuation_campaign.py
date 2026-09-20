"""Campaign orchestration checks; fake reports do not count as numerical evidence."""
import json

import pytest

from scripts import run_rc_adaptive_continuation_campaign as campaign


def test_roster_and_budget_do_not_claim_independent_projects():
    cases = campaign.prepare_cases()
    plan = campaign.campaign_plan('a' * 40, cases)
    assert len(cases) == 8 and plan['planned_comparisons'] == 32 and plan['planned_paths'] == 128
    assert plan['maximum_native_calls_conservative'] == 4736
    assert not plan['independent_project_provenance']
    assert len({m.canonical_model_checksum for _, m, _ in cases}) == 2
    assert {q.targets_m for _, _, q in cases} == {(-a / 2, -a, a / 2) for a in (.02, .04, .06, .08)}
    assert all(q.constant_nodal_loads == (('N3', 0., -25., 0.),) and q.solver_config.newton.terminal_polishing for _, _, q in cases)


@pytest.mark.parametrize("inject_error", [False, True])
def test_orders_incomplete_paths_and_unknown_work_remain_visible(tmp_path, monkeypatch, inject_error):
    calls = []

    def fake(model, request, **options):
        calls.append(options)
        if inject_error and len(calls) == 2:
            raise RuntimeError('injected unknown execution')
        return {'report_hash': 'synthetic', 'all_execution_work_reported': True,
                'arms': {'reference': {'status': 'incomplete'}, 'secant': {'status': 'incomplete'},
                         'proposal': {'status': 'complete'}}, 'fresh_reference': {'status': 'incomplete'}}

    monkeypatch.setattr(campaign, 'benchmark_rc_control_seed_paths', fake)
    result = campaign.run_campaign('a' * 40, tmp_path / 'campaign')
    assert len(calls) == 32 and len(result['rows']) == 32
    assert [c['continuation_adaptive'] for c in calls[:4]] == [False, True, True, False]
    assert [c['arm_order'][0] for c in calls[:4]] == ['reference', 'reference', 'proposal', 'proposal']
    assert all(c['continuation_on_failure'] and c['continuation_all_failed_targets'] for c in calls)
    assert result['observations_complete'] == (not inject_error)
    assert result['completed_paths'] == (31 if inject_error else 32)
    if inject_error:
        assert result['rows'][1]['unknown_work'] and result['rows'][1]['status'] == 'raised'
    assert not result['qualified_speedup'] and not result['policy_promoted']
    saved = json.loads((tmp_path / 'campaign/campaign-outcome.json').read_bytes())
    assert saved == result


def test_invalid_revision_does_not_create_output(tmp_path):
    with pytest.raises(ValueError, match='source revision'):
        campaign.run_campaign('not-a-revision', tmp_path / 'campaign')
    assert not (tmp_path / 'campaign').exists()


def test_preflight_does_not_execute_or_create_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(campaign, 'benchmark_rc_control_seed_paths', lambda *a, **k: pytest.fail('no numerical execution'))
    monkeypatch.setattr('sys.argv', ['campaign', '--source-revision', 'a' * 40,
                                   '--output-directory', str(tmp_path / 'campaign'), '--preflight-only'])
    campaign.main()
    result = json.loads(capsys.readouterr().out)
    assert result['solver_calls'] == 0 and result['paths'] == 128
    assert not (tmp_path / 'campaign').exists()
