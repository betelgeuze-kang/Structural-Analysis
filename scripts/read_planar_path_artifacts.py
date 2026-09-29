"""Read indexed planar paths with bounded step decoding and full-byte binding."""

import hashlib
import re

from scripts.audit_planar_concrete_localization import read_checked, require
from scripts.run_planar_256_refinement import file_sha256, iter_path_json


def _entry(root, entry, name, bound):
    require(type(entry) is dict and set(entry) == {'path', 'bytes', 'sha256'},
            'invalid file entry')
    require(entry['path'] == name, 'unexpected file path')
    require(type(entry['bytes']) is int and 0 < entry['bytes'] <= bound, 'invalid file size')
    require(type(entry['sha256']) is str and re.fullmatch('[0-9a-f]{64}', entry['sha256']),
            'invalid file digest')
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()), 'file escapes packet root')
    require(path.stat().st_size == entry['bytes'], 'file size mismatch')
    return path


def read_path_artifacts(root, index_sha256, full_sha256, consume_step):
    """Return compact results only after all files, chains and full bytes verify.

    consume_step must be a pure extractor: it runs before final full-byte binding.
    The caller must not publish its partial results or retain entire step objects.
    """
    index = read_checked(root / 'path-index.json', index_sha256, maximum_bytes=128 * 1024)
    require(set(index) == {'schema', 'full', 'metadata', 'steps', 'step_count'}
            and index['schema'] == 'fixed-planar-path-file-index.v1', 'invalid path index')
    require(type(index['step_count']) is int and 0 < index['step_count'] <= 255,
            'invalid step count')
    require(type(index['steps']) is list and len(index['steps']) == index['step_count'],
            'step count mismatch')
    full = _entry(root, index['full'], 'repeat-0.json', 32 * 1024**3)
    require(index['full']['sha256'] == full_sha256 and file_sha256(full) == full_sha256,
            'original full-file digest mismatch')
    meta = _entry(root, index['metadata'], 'path-metadata.json', 256 * 1024**2)
    metadata = read_checked(meta, index['metadata']['sha256'], maximum_bytes=256 * 1024**2)
    require(metadata['status'] == 'ready' and metadata['contract_pass'] is True, 'path failed')
    require(metadata['control_global_dof'] == 15, 'control DOF mismatch')
    require(type(metadata['steps']) is list and not metadata['steps'], 'invalid steps placeholder')
    targets = metadata['target_control_displacements_m']
    require(targets == [i / 500 for i in range(1, 41)] and index['step_count'] == 40,
            'full forty targets required')
    results = []

    def accepted_steps():
        previous = metadata['initial_checkpoint']
        for ordinal, entry in enumerate(index['steps']):
            path = _entry(root, entry, f'steps/{ordinal:04d}.json', 512 * 1024**2)
            step = read_checked(path, entry['sha256'], maximum_bytes=512 * 1024**2)
            require(step['committed'] is True and step['metrics']['solver_contract_pass'] is True,
                    'step not accepted')
            require(step['parent_checkpoint'] == previous, 'checkpoint chain mismatch')
            require(step['metrics']['target_control_displacement_m'] == targets[ordinal],
                    'target mismatch')
            results.append(consume_step(step, ordinal))
            previous = step['accepted_checkpoint']
            yield step
            del step
        require(previous == metadata['final_checkpoint'], 'final checkpoint mismatch')

    digest = hashlib.sha256()
    length = 0
    for chunk in iter_path_json(metadata, accepted_steps()):
        raw = chunk.encode('utf-8')
        digest.update(raw)
        length += len(raw)
    require(length == index['full']['bytes'] and digest.hexdigest() == full_sha256,
            'step files do not reproduce original full JSON')
    return results
