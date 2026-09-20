"""Post-hoc two-witness decomposition of the retained 512/1024 comparison.

Derived common-coordinate material responses are not accepted solver fibers.
"""

import argparse
import gc
import json
import math
from pathlib import Path

from scripts.audit_planar_concrete_localization import read_checked, require, validate_path
from scripts.probe_planar_common_material_points import FIELDS, REVISION, material_class, section_at

COARSE_SHA = '2e5974645b6f6fbc81eb8f647a9d6af049007856a466e50bc41b6f685d3fbfd3'
FINE_SHA = '2f923d7537b4ddf10ce19e0959fd081767466442e9f438ef1265c7461154446b'
INPUT_SHA = '34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e'
WITNESSES = (('E2', 0, 7), ('E3', 2, 132))


def extract(path, layers):
    validate_path(path)
    require(path['control_global_dof'] == 15, 'control mismatch')
    targets = [i / 500 for i in range(1, 41)]
    require(path['target_control_displacements_m'] == targets, 'forty targets required')
    out = []
    for mid, gauss, cell in WITNESSES:
        rows = []
        for step in path['steps']:
            section = section_at(step, mid, gauss)
            states = section['trial_state']['fiber_states']
            responses = section['fiber_responses']
            require(len(states) == len(responses) == layers + 2, 'fiber count mismatch')
            indices = (cell,) if layers == 512 else (2 * cell, 2 * cell + 1)
            g = section['generalized_strain']
            fibers = []
            for index in indices:
                response = responses[index]
                require(response['trial_state'] == states[index], 'fiber binding mismatch')
                y = -0.3 + (index + 0.5) * 0.6 / layers
                require(math.isclose(response['total_strain'],
                                     g['axial_strain'] - g['curvature_z_per_m'] * y,
                                     rel_tol=1e-12, abs_tol=1e-14), 'fiber location mismatch')
                fibers.append({'state': states[index], 'stress_mpa': response['stress_mpa']})
            rows.append({'target_m': step['metrics']['target_control_displacement_m'],
                         'generalized_strain': g, 'fibers': fibers})
        out.append(rows)
    return out


def decompose(coarse, midpoint, left, right):
    require(all(type(v) in (int, float) and math.isfinite(v)
                for v in (coarse, midpoint, left, right)), 'finite values required')
    projected = (left + right) / 2
    total, history, sampling = coarse - projected, coarse - midpoint, midpoint - projected
    require(math.isclose(total, history + sampling, rel_tol=1e-12, abs_tol=1e-14),
            'decomposition identity mismatch')
    return {'coarse_accepted': coarse, 'derived_fine_midpoint': midpoint,
            'fine_left_accepted': left, 'fine_right_accepted': right,
            'signed_total': total, 'signed_history': history, 'signed_sampling': sampling}


def replay(material, coarse, fine, *, witnesses=WITNESSES, coarse_layers=512):
    require(type(coarse_layers) is int and coarse_layers > 0, 'positive exact layer count required')
    out = []
    for identity, aa, bb in zip(witnesses, coarse, fine, strict=True):
        cp, fp = material.initial_state(), material.initial_state()
        mid, gauss, cell = identity
        require(type(cell) is int and 0 <= cell < coarse_layers, 'coarse cell outside layer range')
        y = -0.3 + (cell + 0.5) * 0.6 / coarse_layers
        rows = []
        for a, b in zip(aa, bb, strict=True):
            require(a['target_m'] == b['target_m'], 'target mismatch')
            g, h = a['generalized_strain'], b['generalized_strain']
            cr = material.integrate(g['axial_strain'] - g['curvature_z_per_m'] * y, cp)
            fr = material.integrate(h['axial_strain'] - h['curvature_z_per_m'] * y, fp)
            cp, fp = cr.state, fr.state
            actual = a['fibers'][0]
            require(cp.to_dict() == actual['state'] and cr.stress_mpa == actual['stress_mpa'],
                    'coarse material replay not exact')
            fields = {}
            for field in (*FIELDS, 'stress_mpa'):
                c = cr.stress_mpa if field == 'stress_mpa' else getattr(cp, field)
                m = fr.stress_mpa if field == 'stress_mpa' else getattr(fp, field)
                child = [fiber['stress_mpa'] if field == 'stress_mpa' else fiber['state'][field]
                         for fiber in b['fibers']]
                fields[field] = decompose(c, m, *child)
            rows.append({'target_m': a['target_m'], 'fields': fields})
        out.append({'member': mid, 'gauss': gauss, 'coarse_cell': cell, 'y_m': y,
                    'coarse_replay_exact': True, 'rows': rows})
    return out


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
    for root, digest, layers, bound in ((coarse_root, COARSE_SHA, 512, 4 * 1024**3),
                                        (fine_root, FINE_SHA, 1024, 8 * 1024**3)):
        path = read_checked(root / 'repeat-0.json', digest, maximum_bytes=bound)
        histories.append(extract(path, layers))
        del path
        gc.collect()
    return {'schema': 'posthoc-512-1024-witness-decomposition.v1',
            'source_revision': REVISION, 'material_sha256': material_sha,
            'source_sha256': {'coarse': COARSE_SHA, 'fine': FINE_SHA},
            'witnesses': replay(material, *histories), 'structural_solves': 0,
            'training_fits': 0, 'material_integrations': 160,
            'selection': 'Two maxima selected after the completed comparison; not independent evaluation.',
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
