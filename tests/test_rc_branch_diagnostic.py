"""Fixed-parent branch probes: elastic derivative and real concrete peak crossing."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.benchmark import rc_control_branch_diagnostic as branch
from structural_analysis.benchmark.rc_control_continuation_replay import _without_execution_clocks
from structural_analysis.io.neutral.loader import load_neutral_json


@pytest.fixture
def native():
    model = load_neutral_json(Path(__file__).resolve().parents[1]/'examples/public_rc_fiber_frame_cantilever.json')
    compiled, blockers, _ = public._compile(model)
    assert compiled is not None and not blockers
    problem = compiled.problem
    return problem, initial_stateful_fiber_frame2d_checkpoint(problem)


def observe(native, **kwargs):
    options = dict(control_global_dof=4, target_m=1e-6, coordinates=(1e-5, 0., 0., 0.),
                   direction=(2e-6, 0., 0., 0.))
    options.update(kwargs)
    return branch.observe_rc_control_branch_path(*native, **options)


def test_elastic_direction_matches_actual_assembled_jacobian(native):
    before = native[1].canonical_bytes()
    result = observe(native)
    assert result['complete'] and result['assembly_attempts'] == 5
    assert not result['unknown_work'] and not result['committed']
    assert result['newton_solves'] == 0 and not result['candidate_selected']
    assert native[1].canonical_bytes() == before
    for row in result['rows']:
        assert row['linearization_remainder_norm_kn'] < 1e-11
        assert not row['changed_sampled_branches']


def test_compression_peak_crossing_detected_without_changing_parent(native):
    before = native[1].canonical_bytes()
    options = dict(coordinates=(-.003-3e-12, 0., 0., 0.), direction=(6e-12, 0., 0., 0.), fractions=(0., .25, .5, .75, 1.))
    result = observe(native, **options)
    assert result['complete'] and native[1].canonical_bytes() == before
    first = [f for f in result['rows'][0]['fibers'] if f['kind'] == 'concrete']
    last = [f for f in result['rows'][-1]['fibers'] if f['kind'] == 'concrete']
    assert first and len(first) == len(last)
    assert all(f['consistent_tangent_mpa'] < 0 for f in first)
    assert all(f['consistent_tangent_mpa'] > 0 for f in last)
    assert max(abs(a['stress_mpa']-b['stress_mpa']) for a,b in zip(first,last)) < 1e-6
    assert result['rows'][-1]['changed_sampled_branches']
    repeated = observe(native, **options)
    assert _without_execution_clocks(result) == _without_execution_clocks(repeated)


@pytest.mark.parametrize('options', [
    {'direction': (0.,0.,0.,0.)}, {'direction': (True,0.,0.,0.)},
    {'direction': (float('inf'),0.,0.,0.)}, {'coordinates': (float('nan'),0.,0.,0.)},
    {'coordinates': (0.,)}, {'coordinates': ('0', '0', '0', '0')},
    {'fractions': (0.,)}, {'fractions': [0.,1.]}, {'fractions': (0.,True)},
    {'fractions': (.1,1.)}, {'fractions': (0.,1.,.5)}, {'fractions': (0.,.5,.5)},
    {'fractions': (0.,float('nan'))}, {'fractions': tuple(i/65 for i in range(66))},
    {'fractions': (0.,2.)}, {'control_global_dof': 0},
])
def test_bad_input_rejected_before_assembly(native, monkeypatch, options):
    def forbidden(*a, **k):
        pytest.fail('assembled invalid input')
    monkeypatch.setattr(branch.StatefulFiberFrame2DDisplacementControlStepAdapter, 'observe', forbidden)
    with pytest.raises(ValueError):
        observe(native, **options)


def test_diagnostic_exception_keeps_partial_rows_and_unknown_attempt(native, monkeypatch):
    original = branch.StatefulFiberFrame2DDisplacementControlStepAdapter.observe
    attempts = []
    def interrupted(self, x, *args, **kwargs):
        attempts.append(x.copy())
        if len(attempts) == 2:
            raise RuntimeError('injected at second sample')
        return original(self, x, *args, **kwargs)
    before = native[1].canonical_bytes()
    monkeypatch.setattr(branch.StatefulFiberFrame2DDisplacementControlStepAdapter, 'observe', interrupted)
    result = observe(native)
    assert not result['complete'] and result['unknown_work']
    assert result['assembly_attempts'] == 2
    assert result['rows'][0]['status'] == 'observed' and result['rows'][1]['error_type'] == 'RuntimeError'
    assert native[1].canonical_bytes() == before


def test_requested_arrays_not_mutated(native):
    origin = np.array([1e-5,0.,0.,0.])
    direction = np.array([2e-6,0.,0.,0.])
    left, right = origin.copy(), direction.copy()
    observe(native, coordinates=origin, direction=direction)
    assert np.array_equal(origin, left) and np.array_equal(direction, right)


def test_retained_coordinates_not_silently_treated_as_absolute(native):
    from types import SimpleNamespace
    # Deliberately synthetic marker: the unsupported profile is rejected first.
    problem = SimpleNamespace(coordinate_precision='twofold-increment')
    with pytest.raises(ValueError, match='binary64'):
        observe((problem, native[1]))
