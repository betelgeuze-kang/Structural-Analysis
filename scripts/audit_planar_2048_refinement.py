"""Bounded full-history 1024/2048 comparison with pinned coarse features."""

import argparse
import hashlib
import os
from pathlib import Path

from scripts.audit_planar_256_refinement import CONCRETE, compare_features, nodal_steel
from scripts.audit_planar_concrete_localization import read_checked, require, sections
from scripts.read_planar_path_artifacts import read_path_artifacts
from scripts.run_planar_256_refinement import write_json
from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes

COARSE_SHA = '2f923d7537b4ddf10ce19e0959fd081767466442e9f438ef1265c7461154446b'
COARSE_PROTOCOL_SHA = 'e620f118fc72a7af34b8a527649dcddc3d1b78902922aab2860baa92ba73432b'
PROTOCOL_SHA = '6508da674654590141a1b4084b9f59069a70db834da8c4070be153f0dccf9e43'
FEATURES_SHA = 'bc7e6b6666bcc6104ceb9fed33af6039db7a53827c2c71c2d9919951359c119a'
COARSE_INVENTORY_SHA = '8b2333e4e1c55200425444516d08786cd1550e715c5d4d04b0f754b9960fdce2'


def coarse_features(root):
    inventory = read_checked(root / 'inventory.json', COARSE_INVENTORY_SHA)
    matches = [row for row in inventory['files'] if row['path'] == 'result.json']
    require(len(matches) == 1, 'unique coarse verification receipt required')
    receipt = read_checked(root / 'result.json', matches[0]['sha256'])
    require(receipt['original_full_sha256'] == COARSE_SHA
            and receipt['features_sha256'] == FEATURES_SHA
            and receipt['verified_steps'] == 40, 'coarse feature provenance mismatch')
    # The feature payload is a JSON array; wrap only after verified byte reading.
    path = root / 'features.json'
    with path.open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        require(0 < size <= 512 * 1024**2, 'coarse features too large or empty')
        raw = stream.read(size + 1)
    require(len(raw) == size, 'coarse feature size changed')
    require(hashlib.sha256(raw).hexdigest() == FEATURES_SHA, 'coarse features digest mismatch')
    features = strict_json_object_bytes(b'{"features":' + raw + b'}',
                                       maximum_bytes=512 * 1024**2 + 20)['features']
    require(type(features) is list and [row['target_m'] for row in features]
            == [i / 500 for i in range(1, 41)], 'full coarse feature targets required')
    return features


def audit(coarse_root, feature_root, fine_root, fine_sha256, fine_index_sha256):
    coarse_protocol = read_checked(coarse_root / 'protocol.json', COARSE_PROTOCOL_SHA)
    fine_protocol = read_checked(fine_root / 'protocol.json', PROTOCOL_SHA)
    for field in ('source_revision', 'source_manifest_sha256', 'input_sha256',
                  'target_displacements_m', 'control_global_dof', 'configuration',
                  'same_proportional_force_vector', 'constant_axial_load'):
        require(coarse_protocol[field] == fine_protocol[field], 'protocol mismatch: ' + field)
    coarse = coarse_features(feature_root)

    def feature(step, ordinal):
        return {'target_m': step['metrics']['target_control_displacement_m'],
                'sections': sections(step, 2048, CONCRETE),
                'nodal_steel': nodal_steel(step, 2048)}

    fine = read_path_artifacts(fine_root, fine_index_sha256, fine_sha256, feature)
    rows, maxima = compare_features(coarse, fine, 1024)
    return {'schema': 'fixed-planar-1024-2048-comparison.v1',
            'source_revision': fine_protocol['source_revision'],
            'source_sha256': {'coarse': COARSE_SHA, 'fine': fine_sha256},
            'protocol_sha256': {'coarse': COARSE_PROTOCOL_SHA, 'fine': PROTOCOL_SHA},
            'coarse_features_sha256': FEATURES_SHA,
            'coarse_verification_inventory_sha256': COARSE_INVENTORY_SHA,
            'fine_index_sha256': fine_index_sha256,
            'comparison_layers': [1024, 2048], 'matched_targets': 40,
            'original_group_screen': 0.01, 'maxima': maxima, 'comparisons': rows,
            'failed_group_counts': {
                kind: sum(not metric['within_exploratory_one_percent']
                          for row in rows for metric in row[kind].values())
                for kind in ('nodal_steel', 'concrete')},
            'composite_view_not_solver_artifact': True, 'structural_solves': 0,
            'training_fits': 0, 'independent_physical_validation': False,
            'public_api_extended': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse_root', type=Path)
    parser.add_argument('feature_root', type=Path)
    parser.add_argument('fine_root', type=Path)
    parser.add_argument('fine_sha256')
    parser.add_argument('fine_index_sha256')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    write_json(args.output, audit(args.coarse_root, args.feature_root, args.fine_root,
                                 args.fine_sha256, args.fine_index_sha256))
