"""Numerical proposal cost, unchanged native acceptance, and failure retention."""

from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
from structural_analysis.io.neutral.loader import load_neutral_json


def run(tmp_path, **options):
    return benchmark_rc_control_seed_paths(
        load_neutral_json(Path("examples/public_rc_fiber_frame_l_frame_material_history.json")),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-6, -2e-6, -1.5e-6), allow_reversals=True, maximum_reversals=1,
        ),
        source_revision="a" * 40, output_directory=tmp_path / "study",
        trust_region_reversal=True, **options,
    )


def test_full_path_reversal_is_costed_and_fresh_reference_checked(tmp_path):
    report = run(tmp_path, record_assembly_work=True)
    assert report['reference_repeat_exact']
    assert all(c['full_history_pass'] for c in report['comparisons'].values())
    arm = report['arms']['proposal']
    assert arm['status'] == 'complete'
    observations = [e['numerical_proposal'] for e in arm['entries']]
    assert [o['status'] for o in observations] == ['abstained', 'abstained', 'returned']
    last = observations[-1]
    assert last['assembly_attempts'] == sum(last['assembly_counts'].values()) > 0
    assert last['parent_unchanged'] and not last['optimizer_confers_acceptance']
    assert 0 < last['wall_ns'] <= arm['entries'][-1]['proposal_wall_ns'] < arm['wall_ns']
    assert arm['entries'][-1]['invocations']
    assert report['numerical_proposal']['cost_included_in_path_wall']


def test_optimizer_exception_retains_assembly_and_stops_before_terminal_newton(tmp_path, monkeypatch):
    from scipy import optimize

    def interrupted(fun, x, **kwargs):
        fun(x)
        raise RuntimeError('injected after a real full assembly')

    monkeypatch.setattr(optimize, 'least_squares', interrupted)
    report = run(tmp_path)
    arm = report['arms']['proposal']
    assert not report['all_execution_work_reported']
    assert arm['status'] == 'incomplete' and arm['accepted_target_count'] == 2
    last = arm['entries'][-1]
    assert last['numerical_proposal']['assembly_attempts'] == 1
    assert last['numerical_proposal']['unknown_work']
    assert last['numerical_proposal']['parent_unchanged']
    assert last['invocations'] == []
    assert arm['failure']['phase'] == 'numerical_proposal'
    assert not report['comparisons']['proposal']['full_history_pass']


@pytest.mark.parametrize('options', [
    {'proposal': lambda context: None},
    {'coordinate_precision': 'twofold-increment'},
    {'proposal_abstention_strategy': 'secant'},
])
def test_conflicting_strategy_rejected_before_output(tmp_path, options):
    with pytest.raises(ValueError, match='isolated binary64'):
        run(tmp_path, **options)
    assert not (tmp_path / 'study').exists()
