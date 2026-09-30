"""Algebraic diagnostic checks; no physical validation."""

from copy import deepcopy

import pytest

from scripts.probe_planar_1024_witnesses import decompose, replay
from structural_analysis.materials.concrete_damage import AsymmetricConcreteDamageMaterial


def test_components_keep_sign_when_history_and_sampling_cancel():
    row = decompose(0.2, 0.5, 0.1, 0.3)
    assert row['signed_total'] == 0
    assert row['signed_history'] == pytest.approx(-0.3)
    assert row['signed_sampling'] == pytest.approx(0.3)


def test_equal_common_point_response_does_not_hide_sampling_difference():
    row = decompose(0.1, 0.1, 0.1, 0.5)
    assert row['signed_history'] == 0
    assert row['signed_sampling'] == pytest.approx(-0.2)
    assert row['signed_total'] == pytest.approx(-0.2)


@pytest.mark.parametrize('value', [True, None, '0.1', float('nan'), float('inf')])
def test_invalid_component_rejected(value):
    with pytest.raises(ValueError, match='finite'):
        decompose(0.1, value, 0.1, 0.2)


def histories():
    material = AsymmetricConcreteDamageMaterial()
    state = material.initial_state()
    coarse, fine = [], []
    for target, strain in zip((0.002, 0.004, 0.006), (0.0003, -0.002, 0.0001)):
        response = material.integrate(strain, state)
        state = response.state
        row = {'target_m': target,
               'generalized_strain': {'axial_strain': strain, 'curvature_z_per_m': 0.},
               'fibers': [{'state': state.to_dict(), 'stress_mpa': response.stress_mpa}]}
        coarse.append(row)
        child = deepcopy(row)
        child['fibers'].append(deepcopy(child['fibers'][0]))
        fine.append(child)
    return material, [deepcopy(coarse), coarse], [deepcopy(fine), fine]


def test_replay_preserves_reversal_history_and_exact_accepted_states():
    material, coarse, fine = histories()
    result = replay(material, coarse, fine)
    assert len(result) == 2
    for witness in result:
        assert witness['coarse_replay_exact']
        assert len(witness['rows']) == 3
        for row in witness['rows']:
            for field in row['fields'].values():
                assert field['signed_total'] == field['signed_history'] == field['signed_sampling'] == 0


def test_replay_rejects_changed_accepted_state():
    material, coarse, fine = histories()
    coarse[0][1]['fibers'][0]['state']['compressive_damage'] += 0.1
    with pytest.raises(ValueError, match='replay not exact'):
        replay(material, coarse, fine)
