"""Adversarial file/chain bindings for the bounded research reader."""

import json
import weakref

import pytest

from scripts import read_planar_path_artifacts as reader
from scripts.run_planar_256_refinement import file_sha256, write_path_artifacts


def packet(root):
    targets = [i / 500 for i in range(1, 41)]
    steps = [{'committed': True, 'metrics': {'solver_contract_pass': True,
                                            'target_control_displacement_m': target},
              'parent_checkpoint': {'state': i}, 'accepted_checkpoint': {'state': i + 1}}
             for i, target in enumerate(targets)]
    metadata = {'status': 'ready', 'contract_pass': True, 'control_global_dof': 15,
                'target_control_displacements_m': targets,
                'initial_checkpoint': {'state': 0}, 'final_checkpoint': {'state': 40},
                'steps': [], 'claim': 'synthetic test'}
    index = write_path_artifacts(root, metadata, iter(steps))
    return index


def save_index(root, index):
    (root / 'path-index.json').write_text(json.dumps(index))
    return file_sha256(root / 'path-index.json')


def rewrite(root, entry, mutate):
    p = root / entry['path']
    obj = json.loads(p.read_text())
    mutate(obj)
    p.write_text(json.dumps(obj))
    entry.update(bytes=p.stat().st_size, sha256=file_sha256(p))


def collect(root, index_sha, full_sha):
    return reader.read_path_artifacts(root, index_sha, full_sha,
                                      lambda step, i: step['accepted_checkpoint']['state'])


def test_complete_path_requires_original_full_bytes_and_all_forty_steps(tmp_path):
    index = packet(tmp_path)
    assert collect(tmp_path, file_sha256(tmp_path / 'path-index.json'),
                   index['full']['sha256']) == list(range(1, 41))


@pytest.mark.parametrize('change,error', [
    ('parent', 'checkpoint chain'), ('target', 'target mismatch'),
    ('unaccepted', 'step not accepted'), ('terminal', 'final checkpoint'),
    ('extra', 'do not reproduce original'), ('boolean_count', 'invalid step count'),
    ('missing', 'step count mismatch'), ('path', 'unexpected file path'),
    ('digest', 'original full-file digest'), ('full_corrupt', 'original full-file digest'),
])
def test_resigned_index_cannot_hide_corruption(tmp_path, change, error):
    index = packet(tmp_path)
    full_sha = index['full']['sha256']
    if change == 'parent':
        rewrite(tmp_path, index['steps'][1], lambda v: v.update(parent_checkpoint={'state': 9}))
    elif change == 'target':
        rewrite(tmp_path, index['steps'][1],
                lambda v: v['metrics'].update(target_control_displacement_m=0.1))
    elif change == 'unaccepted':
        rewrite(tmp_path, index['steps'][1], lambda v: v.update(committed=False))
    elif change == 'terminal':
        rewrite(tmp_path, index['metadata'], lambda v: v.update(final_checkpoint={'state': 99}))
    elif change == 'extra':
        rewrite(tmp_path, index['steps'][1], lambda v: v.update(extra='not in original'))
    elif change == 'boolean_count':
        index['step_count'] = True
    elif change == 'missing':
        index['steps'].pop()
    elif change == 'path':
        index['steps'][1]['path'] = '../outside.json'
    elif change == 'digest':
        index['full']['sha256'] = '0' * 64
    elif change == 'full_corrupt':
        p = tmp_path / 'repeat-0.json'
        p.write_bytes(p.read_bytes().replace(b'synthetic', b'tampered!', 1))
    with pytest.raises(ValueError, match=error):
        collect(tmp_path, save_index(tmp_path, index), full_sha)


def test_duplicate_step_keys_are_rejected_even_with_updated_hash(tmp_path):
    index = packet(tmp_path)
    entry = index['steps'][0]
    p = tmp_path / entry['path']
    p.write_text(p.read_text().replace('{', '{"committed": false,', 1))
    entry.update(bytes=p.stat().st_size, sha256=file_sha256(p))
    with pytest.raises(ValueError, match='duplicate'):
        collect(tmp_path, save_index(tmp_path, index), index['full']['sha256'])


def test_previous_decoded_step_is_released_before_next_read(tmp_path, monkeypatch):
    index = packet(tmp_path)
    original = reader.read_checked
    refs = []

    class Step(dict):
        pass

    def tracked(path, *args, **kwargs):
        obj = original(path, *args, **kwargs)
        if path.parent.name == 'steps':
            assert all(ref() is None for ref in refs)
            obj = Step(obj)
            refs.append(weakref.ref(obj))
        return obj

    monkeypatch.setattr(reader, 'read_checked', tracked)
    assert len(collect(tmp_path, file_sha256(tmp_path / 'path-index.json'),
                       index['full']['sha256'])) == 40
    assert len(refs) == 40 and all(ref() is None for ref in refs)


def test_reader_refuses_failed_complete_path(tmp_path):
    index = packet(tmp_path)
    rewrite(tmp_path, index['metadata'], lambda v: v.update(status='failed'))
    with pytest.raises(ValueError, match='path failed'):
        collect(tmp_path, save_index(tmp_path, index), index['full']['sha256'])
