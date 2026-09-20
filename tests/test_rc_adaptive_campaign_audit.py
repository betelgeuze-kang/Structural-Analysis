"""Actual small campaign plus rehashed metadata corruption; no external V&V claim."""
import json
import shutil

import pytest

from scripts import audit_rc_adaptive_continuation_campaign as auditor
from scripts import run_rc_adaptive_continuation_campaign as runner
from structural_analysis.benchmark.rc_control_design import _bytes, _sha


@pytest.fixture(scope='module')
def actual_campaign(tmp_path_factory):
    root = tmp_path_factory.mktemp('adaptive-audit-original') / 'study'
    cases = [runner.prepare_cases()[1]]  # Short/40 mm: fixed fails, adaptive completes.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runner, 'prepare_cases', lambda: cases)
        runner.run_campaign('a' * 40, root)
    return root, cases


def configure(monkeypatch, actual_campaign):
    root, cases = actual_campaign
    monkeypatch.setattr(auditor, 'prepare_cases', lambda: cases)
    return root


def rehash(value, field):
    value[field] = _sha(_bytes({k: v for k, v in value.items() if k != field}))
    return value


def mutate_report(root, change):
    identity = 'short-40mm-r0-adaptive'
    path = root / identity / 'comparison.json'
    report = json.loads(path.read_bytes())
    change(report)
    path.write_bytes(_bytes(rehash(report, 'report_hash')))
    outcome_path = root / 'campaign-outcome.json'
    outcome = json.loads(outcome_path.read_bytes())
    row = next(r for r in outcome['rows'] if r['repeat'] == 0 and r['mode'] == 'adaptive')
    row['report_hash'] = report['report_hash']
    (root / (identity + '-outcome.json')).write_bytes(_bytes(row))
    outcome_path.write_bytes(_bytes(rehash(outcome, 'outcome_hash')))


def test_read_only_audit_retains_failed_paths_and_does_not_rerun_solver(actual_campaign, monkeypatch):
    root = configure(monkeypatch, actual_campaign)
    from structural_analysis.assembly import stateful_fiber_frame2d_displacement_control as native
    monkeypatch.setattr(native, 'solve_stateful_fiber_frame2d_displacement_control_step',
                        lambda *a, **k: pytest.fail('audit must not rerun numerical solving'))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*.json')}
    result = auditor.audit(root)
    assert result['totals']['paths'] == 16 and result['totals']['complete_paths'] == 2
    assert result['totals']['ordinary_native_calls'] + result['totals']['additional_native_calls'] == 90
    case = result['cases'][0]
    assert case['complete']['fixed'] == [False, False]
    assert case['complete']['adaptive'] == [True, True]
    assert case['complete_repeats_exact']['adaptive']
    assert case['adaptive_over_fixed_ratio'] is None
    assert not result['numerical_reexecution_performed']
    assert not result['original_execution_clocks_authenticated']
    assert not result['independent_physical_validation']
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob('*.json')}


@pytest.mark.parametrize('field', ['completion', 'work', 'ordinary_work'])
def test_rehashed_false_completion_or_work_is_rejected(actual_campaign, tmp_path, monkeypatch, field):
    original = configure(monkeypatch, actual_campaign)
    root = tmp_path / 'copy'
    shutil.copytree(original, root)

    def change(report):
        if field == 'completion':
            report['comparisons']['proposal']['full_history_pass'] = True
        elif field == 'work':
            report['numerical_proposal_work']['known_newton_iterations'] -= 1
        else:
            arm = report['arms']['proposal']
            arm['entries'][0]['invocations'][0]['work']['newton_iterations'] -= 1
            path_file = root / 'short-40mm-r0-adaptive/proposal/path.json'
            path = json.loads(path_file.read_bytes())
            path['entries'] = arm['entries']
            path_file.write_bytes(_bytes(rehash(path, 'path_hash')))
            arm['path_hash'] = path['path_hash']
            report['assembly_phase_work']['proposal']['source_path_hash'] = path['path_hash']

    mutate_report(root, change)
    with pytest.raises(ValueError, match='full_history_pass|known_newton_iterations|ordinary work'):
        auditor.audit(root)


def test_missing_comparison_is_rejected_before_reading_paths(actual_campaign, tmp_path, monkeypatch):
    original = configure(monkeypatch, actual_campaign)
    root = tmp_path / 'missing'
    root.mkdir()
    shutil.copy2(original / 'campaign-plan.json', root)
    outcome = json.loads((original / 'campaign-outcome.json').read_bytes())
    outcome['rows'].pop()
    (root / 'campaign-outcome.json').write_bytes(_bytes(rehash(outcome, 'outcome_hash')))
    with pytest.raises(ValueError, match='rows'):
        auditor.audit(root)


def test_duplicate_metadata_keys_are_rejected(actual_campaign, tmp_path, monkeypatch):
    original = configure(monkeypatch, actual_campaign)
    root = tmp_path / 'duplicate'
    root.mkdir()
    raw = (original / 'campaign-plan.json').read_bytes()
    (root / 'campaign-plan.json').write_bytes(b'{"plan_hash":"duplicate",' + raw[1:])
    with pytest.raises(ValueError, match='duplicate'):
        auditor.audit(root)


@pytest.mark.parametrize('value', [0, -1, True, 1.5])
def test_invalid_clock_types_and_values_are_rejected(value):
    with pytest.raises(ValueError, match='positive integer'):
        auditor._positive_int(value, 'path wall time')


def test_trial_reference_cannot_escape_local_originals(tmp_path):
    with pytest.raises(ValueError, match='local trial artifact'):
        auditor._artifact_bytes(tmp_path / '../outside.json', tmp_path)


def test_cli_refuses_output_inside_originals_before_audit(tmp_path, monkeypatch):
    monkeypatch.setattr('sys.argv', ['audit', str(tmp_path), '--output', str(tmp_path / 'audit.json')])
    monkeypatch.setattr(auditor, 'audit', lambda root: pytest.fail('must reject output first'))
    with pytest.raises(ValueError, match='separate audit output'):
        auditor.main()
    assert not (tmp_path / 'audit.json').exists()


def test_partial_history_cannot_be_relabelled_complete():
    request = runner.prepare_cases()[1][2]
    path = {'requested_targets_m': list(request.targets_m), 'accepted_target_count': 0,
            'response_history': [], 'status': 'complete', 'failure': None}
    with pytest.raises(ValueError, match='complete path status'):
        auditor._check_path_evidence({}, 'proposal', path, request)
