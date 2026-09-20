"""Protect additive timing attribution and unknown-work boundaries."""
import pytest

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


def test_overlapping_timers_and_unknown_work_are_not_presented_as_complete_costs():
    arm = {'wall_ns': 10, 'preload_invocations': [{'wall_ns': 11, 'unknown_work': False}],
           'entries': []}
    with pytest.raises(ValueError, match='overlapping or invalid timing'):
        decompose(arm, 0)
    arm['preload_invocations'][0]['unknown_work'] = True
    with pytest.raises(ValueError, match='unknown invocation cost'):
        decompose(arm, 0)
