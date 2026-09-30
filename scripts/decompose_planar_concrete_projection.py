"""Separate retained history and spatial sampling differences algebraically.

Derived fine midpoint values remain observations, not accepted solver fibers.
No structural solve, material replay, new threshold or causal claim is made.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts.audit_planar_concrete_localization import read_checked, require, sections, validate_path
from scripts.probe_planar_common_material_points import FINE_SHA256

POINT_INVENTORY = '48a9f4d2fafada99a732599e24212e2ba734c6e9f23a0fa59db60f663903ac8d'
FIELDS = ('tensile_damage', 'compressive_damage')


def decompose(coarse, fine_midpoint, fine_left, fine_right):
    require(all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
                for v in (coarse, fine_midpoint, fine_left, fine_right)),
            'finite damage values in [0,1] required')
    projected = (fine_left + fine_right) / 2
    total = coarse - projected
    history = coarse - fine_midpoint
    sampling = fine_midpoint - projected
    residual = total - (history + sampling)
    require(abs(residual) <= 1e-15, 'algebraic decomposition does not close')
    return dict(total=total, history=history, sampling=sampling, residual=residual,
                mixed_onset=(fine_left > 0) != (fine_right > 0))


def summarize(rows):
    require(bool(rows), 'point rows required')
    require(len({tuple(r['point']) for r in rows}) == len(rows), 'duplicate point')
    worst = max(rows, key=lambda r: abs(r['total']))
    return {
        'point_count': len(rows),
        'maximum_absolute_total': abs(worst['total']),
        'maximum_location': worst['point'],
        'components_at_total_maximum': {k: worst[k] for k in ('total', 'history', 'sampling', 'residual', 'mixed_onset')},
        'sum_absolute_total': math.fsum(abs(r['total']) for r in rows),
        'sum_absolute_history': math.fsum(abs(r['history']) for r in rows),
        'sum_absolute_sampling': math.fsum(abs(r['sampling']) for r in rows),
        'maximum_absolute_closure_residual': max(abs(r['residual']) for r in rows),
        'opposite_sign_component_cells': sum(r['history'] * r['sampling'] < 0 for r in rows),
        'sampling_magnitude_exceeds_history_cells': sum(abs(r['sampling']) > abs(r['history']) for r in rows),
        'mixed_onset_cells': sum(r['mixed_onset'] for r in rows),
    }


def run(points_root, fine_root):
    raw = (points_root / 'inventory.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == POINT_INVENTORY, 'original point inventory changed')
    index = {r['path']: r for r in json.loads(raw)['files']}
    point_raw = (points_root / 'report.json').read_bytes()
    require(len(point_raw) == index['report.json']['byte_length'] and
            hashlib.sha256(point_raw).hexdigest() == index['report.json']['sha256'],
            'original point report changed')
    points = json.loads(point_raw)
    require(points['schema'] == 'posthoc-all-common-material-points.v1' and
            points['derived_fine_values_are_solver_accepted_fibers'] is False and
            points['fine_sha256'] == FINE_SHA256, 'original derived-point scope required')
    path = read_checked(fine_root / 'repeat-0.json', FINE_SHA256, maximum_bytes=2 * 1024**3)
    validate_path(path)
    targets = path['target_control_displacements_m']
    require(len(targets) == 40 and len(set(targets)) == 40, 'complete forty-target sequence required')
    bound = [sections(step, 256, fields=FIELDS) for step in path['steps']]
    del path
    witnesses = points['witnesses']
    require(len(witnesses) == 2304 and all(w['coarse_replay_exact'] is True for w in witnesses),
            'all exactly replayed coarse points required')
    expected = {(mid, g, c) for mid in ('E1', 'E2', 'E3', 'E4', 'E5', 'E6')
                for g in range(3) for c in range(128)}
    require({(w['member'], w['gauss'], w['coarse_cell']) for w in witnesses} == expected,
            'complete unique point roster required')
    results = []
    for n, target in enumerate(targets):
        groups = {field: [] for field in FIELDS}
        for witness in witnesses:
            require([r['target_m'] for r in witness['rows']] == targets,
                    'point target sequence changed')
            mid, g, cell = witness['member'], witness['gauss'], witness['coarse_cell']
            y = -0.3 + (cell + 0.5) * 0.6 / 128
            require(witness['y_m'] == y, 'point coordinate changed')
            row = witness['rows'][n]
            children = bound[n][f'{mid}:gauss-{g}']['values']
            for field in FIELDS:
                values = decompose(row['coarse_accepted_values'][field],
                                   row['derived_fine_point_values'][field],
                                   children[2 * cell][field], children[2 * cell + 1][field])
                groups[field].append({'point': [mid, g, cell], **values})
        results.append({'target_m': target, 'fields': {k: summarize(v) for k, v in groups.items()}})
    return {'schema_version': 'retained-concrete-error-decomposition.v1',
            'source_point_inventory_sha256': POINT_INVENTORY,
            'source_point_report_sha256': index['report.json']['sha256'],
            'source_fine_path_sha256': FINE_SHA256, 'targets': results,
            'new_structural_solves': 0, 'new_material_integrations': 0,
            'original_screen_replaced': False, 'physical_validation': False,
            'scope': 'Signed algebraic decomposition at original coarse coordinates; not causal attribution or a volume integral.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('points_root', type=Path)
    parser.add_argument('fine_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = run(args.points_root, args.fine_root)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
