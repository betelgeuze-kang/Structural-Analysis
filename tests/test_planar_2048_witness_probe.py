"""Small extraction and coordinate checks; no retained path scans or solves."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import probe_planar_2048_witness as probe
from scripts.probe_planar_1024_witnesses import replay


def section(layers):
    g = {'axial_strain': .002, 'curvature_z_per_m': .01}
    states = [{'marker': i} for i in range(layers + 2)]
    responses = [dict(trial_state=s, stress_mpa=float(i),
                      total_strain=g['axial_strain'] - g['curvature_z_per_m'] *
                      (-.3 + (i + .5) * .6 / layers)) for i, s in enumerate(states)]
    return dict(generalized_strain=g, trial_state={'fiber_states': states}, fiber_responses=responses)


@pytest.mark.parametrize('layers,indices', [(1024, [269]), (2048, [538, 539])])
def test_extracts_only_bound_cells_without_retaining_native_objects(monkeypatch, layers, indices):
    original = section(layers)
    monkeypatch.setattr(probe, 'section_at', lambda step, member, gauss: original)
    result = probe.extract_step({'metrics': {'target_control_displacement_m': .074}}, layers)
    assert [row['state']['marker'] for row in result['fibers']] == indices
    assert result['target_m'] == .074
    original['generalized_strain']['axial_strain'] = 999
    original['trial_state']['fiber_states'][indices[0]]['marker'] = -1
    assert result['generalized_strain']['axial_strain'] == .002
    assert result['fibers'][0]['state']['marker'] == indices[0]


@pytest.mark.parametrize('mutation', ['location', 'binding', 'count'])
def test_rejects_misbound_native_fiber(monkeypatch, mutation):
    original = section(2048)
    if mutation == 'location':
        original['fiber_responses'][538]['total_strain'] += .001
    elif mutation == 'binding':
        original['fiber_responses'][538]['trial_state'] = {'marker': -1}
    else:
        original['fiber_responses'].pop()
    monkeypatch.setattr(probe, 'section_at', lambda step, member, gauss: original)
    with pytest.raises(ValueError, match='mismatch'):
        probe.extract_step({'metrics': {'target_control_displacement_m': .074}}, 2048)


def test_replay_uses_new_coarse_coordinate(monkeypatch):
    import scripts.probe_planar_1024_witnesses as shared
    monkeypatch.setattr(shared, 'FIELDS', ())
    y = -.3 + (269 + .5) * .6 / 1024
    strain = .002 - .01 * y
    calls = []

    class Material:
        def initial_state(self):
            return None

        def integrate(self, value, state):
            calls.append(value)
            return SimpleNamespace(state=SimpleNamespace(to_dict=lambda: {}), stress_mpa=value)

    row = dict(target_m=.074, generalized_strain=dict(axial_strain=.002, curvature_z_per_m=.01),
               fibers=[dict(state={}, stress_mpa=strain)])
    fine = deepcopy(row)
    fine['fibers'] *= 2
    result = replay(Material(), [[row]], [[fine]], witnesses=(probe.WITNESS,), coarse_layers=1024)
    assert calls == [strain, strain]
    assert result[0]['y_m'] == y
    assert result[0]['rows'][0]['fields']['stress_mpa']['signed_total'] == 0
