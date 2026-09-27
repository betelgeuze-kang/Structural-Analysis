"""Guard full-history and original-screen checks in the post-hoc onset reader."""

from copy import deepcopy
import math

import pytest

from scripts import analyze_planar_2048_onset as onset


def fixture():
    threshold = 1e-4
    rate = 3000.0

    def damage(history):
        return (0.0 if history <= threshold else
                1 - threshold / history * math.exp(-rate * (history - threshold)))

    rows = []
    for index in range(1, 41):
        target = index / 500
        histories = {position: (0.0 if index < 37 else 0.00012)
                     for position in onset.POSITIONS}
        if index == 37:
            histories = dict.fromkeys(onset.POSITIONS, 0.000099)
            histories['fine_right_accepted'] = 0.000102
        damages = {position: damage(h) for position, h in histories.items()}
        projected = (damages['fine_left_accepted'] +
                     damages['fine_right_accepted']) / 2
        total = damages['coarse_accepted'] - projected
        history_term = damages['coarse_accepted'] - damages['derived_fine_midpoint']
        damages.update(signed_total=total, signed_history=history_term,
                       signed_sampling=damages['derived_fine_midpoint'] - projected)
        rows.append({'target_m': target,
                     'fields': {'tensile_history_strain': histories,
                                'tensile_damage': damages}})
    witness = {
        'schema': 'posthoc-1024-2048-witness-decomposition.v1',
        'source_revision': onset.REVISION,
        'material_sha256': onset.MATERIAL_SHA,
        'source_sha256': {'coarse': onset.COARSE_SHA, 'fine': onset.FINE_SHA},
        'index_sha256': {'coarse': onset.COARSE_INDEX, 'fine': onset.FINE_INDEX},
        'structural_solves': 0, 'training_fits': 0, 'material_integrations': 80,
        'original_projection_screen_replaced': False,
        'witnesses': [{'member': 'E3', 'gauss': 2, 'coarse_cell': 269,
                       'coarse_replay_exact': True, 'rows': rows}],
    }
    model = {'materials': [{'id': 'concrete', 'parameters': {
        'elastic_modulus_pa': 3e10, 'tensile_strength_pa': 3e6,
        'tensile_softening_rate': rate}}]}
    failure = {'target_m': .074, 'category': 'concrete', 'field': 'tensile_damage',
               'witness_section': 'E3:gauss-2', 'witness_cell': 269,
               'finer_infinity_norm': 1.0, 'denominator_floor': 1e-12,
               'within_exploratory_one_percent': False,
               'absolute_difference': abs(rows[36]['fields']['tensile_damage']['signed_total']),
               'relative_group_difference': abs(rows[36]['fields']['tensile_damage']['signed_total'])}
    comparison = {'original_group_screen': .01, 'failed_groups': [failure]}
    return witness, model, comparison


def test_full_history_reproduces_unchanged_screen_and_onset_order():
    result = onset.analyze(*fixture())
    assert result['target_count_checked'] == 40
    assert result['first_positive_damage_target_m'] == {
        'coarse_accepted': .076, 'derived_fine_midpoint': .076,
        'fine_left_accepted': .076, 'fine_right_accepted': .074}
    assert result['at_74_mm']['threshold_margins']['fine_right_accepted'] > 0
    assert result['at_74_mm']['threshold_margins']['coarse_accepted'] < 0
    assert result['original_screen_pass'] is False


@pytest.mark.parametrize('mutation, message', [
    ('missing_target', 'complete target history'),
    ('changed_damage', 'inconsistent with material law'),
    ('changed_denominator', 'original 1% result not reproduced'),
])
def test_rejects_incomplete_or_inconsistent_evidence(mutation, message):
    witness, model, comparison = deepcopy(fixture())
    if mutation == 'missing_target':
        witness['witnesses'][0]['rows'].pop(4)
    elif mutation == 'changed_damage':
        witness['witnesses'][0]['rows'][36]['fields']['tensile_damage'][
            'fine_right_accepted'] = 0.5
    else:
        comparison['failed_groups'][0]['finer_infinity_norm'] = .5
    with pytest.raises(ValueError, match=message):
        onset.analyze(witness, model, comparison)
