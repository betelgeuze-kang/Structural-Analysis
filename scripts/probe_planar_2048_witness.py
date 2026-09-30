"""Bounded post-hoc replay of the sole retained 1024/2048 failing witness."""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from scripts.audit_planar_concrete_localization import read_checked, require
from scripts.probe_planar_1024_witnesses import INPUT_SHA, replay
from scripts.probe_planar_common_material_points import REVISION, material_class, section_at
from scripts.read_planar_path_artifacts import read_path_artifacts

COARSE_SHA = '2f923d7537b4ddf10ce19e0959fd081767466442e9f438ef1265c7461154446b'
COARSE_INDEX = 'effa668ba984929d1e8e0410146eef39dff438e359a44f6a49b7c4a8749dfbe5'
FINE_SHA = '434faa33ae5360b332897d3e0c7171844a95182630082d9f9689a885d7ff71f6'
FINE_INDEX = 'e1fabd392c7a32648cac7afd610483940fff467cdcf0413bce2e1a057a66878d'
WITNESS = ('E3', 2, 269)


def extract_step(step, layers):
    require(type(layers) is int and layers in (1024, 2048), 'fixed layer pair required')
    mid, gauss, cell = WITNESS
    section = section_at(step, mid, gauss)
    states = section['trial_state']['fiber_states']
    responses = section['fiber_responses']
    require(len(states) == len(responses) == layers + 2, 'fiber count mismatch')
    g = section['generalized_strain']
    fibers = []
    for index in ((cell,) if layers == 1024 else (2 * cell, 2 * cell + 1)):
        response = responses[index]
        require(response['trial_state'] == states[index], 'fiber binding mismatch')
        y = -0.3 + (index + 0.5) * 0.6 / layers
        require(math.isclose(response['total_strain'],
                             g['axial_strain'] - g['curvature_z_per_m'] * y,
                             rel_tol=1e-12, abs_tol=1e-14), 'fiber location mismatch')
        fibers.append({'state': deepcopy(states[index]), 'stress_mpa': response['stress_mpa']})
    return {'target_m': step['metrics']['target_control_displacement_m'],
            'generalized_strain': deepcopy(g), 'fibers': fibers}


def probe(coarse_root, fine_root):
    cls, material_sha = material_class(fine_root)
    model = read_checked(fine_root / 'input.json', INPUT_SHA)
    p = next(m['parameters'] for m in model['materials'] if m['id'] == 'concrete')
    material = cls(elastic_modulus_mpa=p['elastic_modulus_pa'] / 1e6,
                   tensile_strength_mpa=p['tensile_strength_pa'] / 1e6,
                   compressive_strength_mpa=p['compressive_strength_pa'] / 1e6,
                   tensile_softening_rate=p['tensile_softening_rate'],
                   compressive_softening_rate=p['compressive_softening_rate'],
                   history_tolerance=p['history_tolerance'])
    histories = []
    for root, index, full, layers in ((coarse_root, COARSE_INDEX, COARSE_SHA, 1024),
                                     (fine_root, FINE_INDEX, FINE_SHA, 2048)):
        histories.append(read_path_artifacts(root, index, full,
                         lambda step, ordinal: extract_step(step, layers)))
    witnesses = replay(material, [histories[0]], [histories[1]],
                       witnesses=(WITNESS,), coarse_layers=1024)
    return {'schema': 'posthoc-1024-2048-witness-decomposition.v1',
            'source_revision': REVISION, 'material_sha256': material_sha,
            'source_sha256': {'coarse': COARSE_SHA, 'fine': FINE_SHA},
            'index_sha256': {'coarse': COARSE_INDEX, 'fine': FINE_INDEX},
            'witnesses': witnesses, 'structural_solves': 0, 'training_fits': 0,
            'material_integrations': 80,
            'selection': 'Sole failing tensile-damage group selected after comparison: 74 mm.',
            'causal_attribution': False, 'derived_midpoints_are_accepted_solver_fibers': False,
            'original_projection_screen_replaced': False, 'physical_validation': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse_root', type=Path)
    parser.add_argument('fine_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = probe(args.coarse_root, args.fine_root)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
