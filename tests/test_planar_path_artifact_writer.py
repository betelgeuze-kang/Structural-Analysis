"""Byte identity and bounded traversal checks for research artifact storage."""

import hashlib
import json
import weakref

import pytest

from scripts.run_planar_256_refinement import file_sha256, write_path_artifacts


@pytest.mark.parametrize('steps', [[], [{'a': [1, -0.0, 1e-12], 'nested': {'b': '\n한글'}}],
                                  [{'accepted': True}, {'accepted': False, 'value': None}]])
def test_original_full_json_bytes_and_index_hashes(tmp_path, steps):
    metadata = {'schema': 'example', 'contract_pass': bool(steps),
                'nested': {'items': [1, {'x': 'é'}]}, 'steps': [], 'claim': 'bounded'}
    expected = (json.dumps({**metadata, 'steps': steps}, indent=2, allow_nan=False) + '\n').encode()
    receipt = write_path_artifacts(tmp_path, metadata, iter(steps))
    assert (tmp_path / 'repeat-0.json').read_bytes() == expected
    assert receipt['full']['sha256'] == hashlib.sha256(expected).hexdigest()
    assert receipt['step_count'] == len(steps)
    for entry in [receipt['full'], receipt['metadata'], *receipt['steps']]:
        p = tmp_path / entry['path']
        assert p.stat().st_size == entry['bytes']
        assert file_sha256(p) == entry['sha256']
    assert json.loads((tmp_path / 'path-metadata.json').read_text()) == metadata


def test_previous_step_dictionary_is_released_before_requesting_next(tmp_path):
    class Step(dict):
        pass

    def steps():
        value = Step(values=[1, 2, 3])
        previous = weakref.ref(value)
        yield value
        del value
        assert previous() is None
        yield Step(values=[4, 5, 6])

    write_path_artifacts(tmp_path, {'steps': []}, steps())


def test_invalid_step_leaves_no_completed_index(tmp_path):
    with pytest.raises(ValueError):
        write_path_artifacts(tmp_path, {'steps': []}, iter([{'x': float('nan')}]))
    assert not (tmp_path / 'path-index.json').exists()


def test_existing_full_result_is_never_overwritten(tmp_path):
    full = tmp_path / 'repeat-0.json'
    full.write_bytes(b'original')
    with pytest.raises(FileExistsError):
        write_path_artifacts(tmp_path, {'steps': []}, iter([]))
    assert full.read_bytes() == b'original'
