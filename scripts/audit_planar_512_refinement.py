"""Read-only comparison of pinned full 256 and 512 layer histories."""

import argparse
import json
from pathlib import Path

from scripts.audit_planar_256_refinement import (
    PROTOCOL_SHA256 as COARSE_PROTOCOL_SHA256,
    compare_steps,
)
from scripts.audit_planar_concrete_localization import read_checked, require, validate_path

PROTOCOL_SHA256 = "9e1ede09c94df2402765f8980d1c6d514dc71d87c23dc13312c7130c9e787f96"
COARSE_SHA256 = "ae168bdad5cc4d23f0b246df39b84b1b800458033fe4ba0c9f4acaed7d98b695"


def audit(coarse_root, fine_root, fine_sha256):
    coarse_protocol = read_checked(coarse_root / 'protocol.json', COARSE_PROTOCOL_SHA256)
    fine_protocol = read_checked(fine_root / 'protocol.json', PROTOCOL_SHA256)
    for field in ('source_revision', 'source_manifest_sha256', 'input_sha256',
                  'target_displacements_m', 'control_global_dof', 'configuration',
                  'same_proportional_force_vector', 'constant_axial_load'):
        require(coarse_protocol[field] == fine_protocol[field], 'protocol mismatch: ' + field)
    paths = [
        read_checked(coarse_root / 'repeat-0.json', COARSE_SHA256, maximum_bytes=2 * 1024**3),
        read_checked(fine_root / 'repeat-0.json', fine_sha256, maximum_bytes=4 * 1024**3),
    ]
    for path in paths:
        validate_path(path)
        require(path['control_global_dof'] == 15, 'control DOF mismatch')
    rows, maxima = compare_steps(paths[0]['steps'], paths[1]['steps'], 256)
    return {
        'schema': 'fixed-planar-256-512-comparison.v1',
        'source_revision': fine_protocol['source_revision'],
        'source_sha256': {'coarse': COARSE_SHA256, 'fine': fine_sha256},
        'protocol_sha256': {'coarse': COARSE_PROTOCOL_SHA256, 'fine': PROTOCOL_SHA256},
        'comparison_layers': [256, 512], 'matched_targets': 40,
        'original_group_screen': 0.01, 'maxima': maxima, 'comparisons': rows,
        'failed_group_counts': {
            kind: sum(not metric['within_exploratory_one_percent']
                      for row in rows for metric in row[kind].values())
            for kind in ('nodal_steel', 'concrete')
        },
        'composite_view_not_solver_artifact': True,
        'structural_solves': 0, 'training_fits': 0,
        'independent_physical_validation': False, 'public_api_extended': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse_root', type=Path)
    parser.add_argument('fine_root', type=Path)
    parser.add_argument('fine_sha256')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.coarse_root, args.fine_root, args.fine_sha256)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
