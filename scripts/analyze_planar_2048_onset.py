"""Read-only threshold diagnostic for the retained 1024/2048 damage witness.

The saved witness contains all forty accepted targets. This observer reads that
small, pinned result; it does not rescan the structural paths or create fibers.
"""

import argparse
import json
import math
from pathlib import Path

from scripts.audit_planar_concrete_localization import read_checked, require
from scripts.probe_planar_1024_witnesses import INPUT_SHA
from scripts.probe_planar_2048_witness import (
    COARSE_INDEX, COARSE_SHA, FINE_INDEX, FINE_SHA, WITNESS,
)
from scripts.probe_planar_common_material_points import REVISION


WITNESS_SHA = '6972ca9a60e710bb5e7fe51875a21d2c1482bc09642ad357ed005c020c3c2208'
COMPARISON_SHA = '68983726cf740f32cb6e20b47148cb2a1b4079206659a93c7ceb7b602c4be7e4'
MATERIAL_SHA = 'dcbc837fee1ceb746ad3b2f1d76428a33a7c7fcb699562a0370a556fd028f9e4'
POSITIONS = ('coarse_accepted', 'derived_fine_midpoint',
             'fine_left_accepted', 'fine_right_accepted')


def analyze(witness, model, comparison):
    """Check the full saved history before reporting the selected onset point."""
    require(witness['schema'] == 'posthoc-1024-2048-witness-decomposition.v1'
            and witness['source_revision'] == REVISION
            and witness['material_sha256'] == MATERIAL_SHA, 'witness source mismatch')
    require(witness['source_sha256'] == {'coarse': COARSE_SHA, 'fine': FINE_SHA}
            and witness['index_sha256'] == {'coarse': COARSE_INDEX, 'fine': FINE_INDEX},
            'witness path pins mismatch')
    require(witness['structural_solves'] == witness['training_fits'] == 0
            and witness['material_integrations'] == 80
            and witness['original_projection_screen_replaced'] is False,
            'witness authority mismatch')
    require(len(witness['witnesses']) == 1, 'one witness required')
    selected = witness['witnesses'][0]
    require((selected['member'], selected['gauss'], selected['coarse_cell']) == WITNESS
            and selected['coarse_replay_exact'] is True, 'witness identity mismatch')
    rows = selected['rows']
    require(len(rows) == 40 and [r['target_m'] for r in rows]
            == [i / 500 for i in range(1, 41)], 'complete target history required')

    materials = [m['parameters'] for m in model['materials'] if m['id'] == 'concrete']
    require(len(materials) == 1, 'unique concrete parameters required')
    p = materials[0]
    modulus, strength, rate = (p['elastic_modulus_pa'], p['tensile_strength_pa'],
                               p['tensile_softening_rate'])
    require(all(type(v) in (float, int) and math.isfinite(v) and v > 0
                for v in (modulus, strength, rate)), 'invalid concrete parameters')
    threshold = strength / modulus

    failures = comparison['failed_groups']
    require(comparison['original_group_screen'] == .01 and len(failures) == 1,
            'original comparison screen mismatch')
    failure = failures[0]
    require((failure['target_m'], failure['category'], failure['field'],
             failure['witness_section'], failure['witness_cell'])
            == (.074, 'concrete', 'tensile_damage', 'E3:gauss-2', 269),
            'original failure identity mismatch')
    denominator = max(failure['finer_infinity_norm'], failure['denominator_floor'])
    require(denominator > 0 and failure['within_exploratory_one_percent'] is False
            and failure['relative_group_difference'] > comparison['original_group_screen'],
            'original denominator or failure mismatch')

    first_damage = {position: None for position in POSITIONS}
    previous_history = {position: 0.0 for position in POSITIONS}
    evaluated = []
    for row in rows:
        history = row['fields']['tensile_history_strain']
        damage = row['fields']['tensile_damage']
        margins = {}
        for position in POSITIONS:
            h, d = history[position], damage[position]
            require(type(h) in (float, int) and math.isfinite(h) and h >= 0
                    and type(d) in (float, int) and math.isfinite(d) and 0 <= d < 1,
                    'invalid retained tensile state')
            require(h >= previous_history[position], 'tensile history decreased')
            previous_history[position] = h
            expected = (0.0 if h <= threshold else
                        min(1 - threshold / h * math.exp(-rate * (h - threshold)),
                            math.nextafter(1.0, 0.0)))
            require(math.isclose(d, expected, rel_tol=1e-12, abs_tol=1e-12),
                    'retained damage inconsistent with material law')
            if d > 0 and first_damage[position] is None:
                first_damage[position] = row['target_m']
            margins[position] = h - threshold
        total = damage['coarse_accepted'] - (
            damage['fine_left_accepted'] + damage['fine_right_accepted']) / 2
        require(math.isclose(total, damage['signed_total'], abs_tol=1e-14)
                and math.isclose(total,
                    damage['signed_history'] + damage['signed_sampling'], abs_tol=1e-14),
                'retained decomposition mismatch')
        evaluated.append({'target_m': row['target_m'], 'threshold_margins': margins,
                          'accepted_damage_difference': total})

    at_74 = evaluated[36]
    require(at_74['target_m'] == .074
            and math.isclose(abs(at_74['accepted_damage_difference']),
                             failure['absolute_difference'], abs_tol=1e-14)
            and math.isclose(abs(at_74['accepted_damage_difference']) / denominator,
                             failure['relative_group_difference'], abs_tol=1e-14),
            'original 1% result not reproduced')
    return {
        'schema': 'posthoc-1024-2048-tensile-onset-diagnostic.v1',
        'source_sha256': {'witness': WITNESS_SHA, 'input': INPUT_SHA,
                          'comparison': COMPARISON_SHA},
        'target_count_checked': len(rows), 'tensile_threshold_strain': threshold,
        'first_positive_damage_target_m': first_damage,
        'at_72_mm': evaluated[35], 'at_74_mm': at_74,
        'at_76_mm': evaluated[37],
        'original_relative_group_difference': failure['relative_group_difference'],
        'original_group_screen': comparison['original_group_screen'],
        'original_screen_pass': False,
        'structural_solves': 0, 'material_integrations': 0,
        'physical_validation': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('witness_result', type=Path)
    parser.add_argument('fine_input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    witness = read_checked(args.witness_result, WITNESS_SHA, maximum_bytes=1024**2)
    model = read_checked(args.fine_input, INPUT_SHA, maximum_bytes=1024**2)
    comparison = read_checked(
        Path(__file__).resolve().parents[1] /
        'docs/engineering/planar-2048-refinement-20260920.summary.json',
        COMPARISON_SHA, maximum_bytes=1024**2)
    with args.output.open('x') as stream:
        stream.write(json.dumps(analyze(witness, model, comparison),
                                indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
