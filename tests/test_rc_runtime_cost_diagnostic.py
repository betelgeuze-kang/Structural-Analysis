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
