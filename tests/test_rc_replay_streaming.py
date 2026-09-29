"""File-bounded replay validation and failure receipts without acceptance changes."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import shutil
import weakref

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
from structural_analysis.benchmark import rc_control_continuation_replay as replay
from structural_analysis.benchmark import rc_control_replay_files as files
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
from structural_analysis.io.neutral.loader import load_neutral_json


def store(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_bytes(value))


def inputs():
    model = load_neutral_json(Path(__file__).resolve().parents[1] / 'examples/public_rc_fiber_frame_cantilever.json')
    request = BoundedRCFiberDirectControlRequest(
        4, (-1e-6, -2e-6, 1e-6), allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -10., 0., 0.),),
    )
    return model, request


@pytest.fixture(scope='module')
def study(tmp_path_factory):
    root = tmp_path_factory.mktemp('original')/'study'
    benchmark_rc_control_seed_paths(*inputs(), source_revision='a'*40,
                                   output_directory=root, frozen_parent_continuation=True,
                                   record_assembly_work=True)
    return root


def execute(study, out):
    return replay.replay_rc_frozen_continuation_study(
        study, *inputs(), output_directory=out, replay_source_revision='b'*40,
    )


def test_inventory_retains_no_decoded_artifacts(tmp_path, monkeypatch):
    alive = weakref.WeakValueDictionary()
    peak = []
    original = files._validate_value
    class Tracked(dict):
        pass
    def track(raw, name):
        value = Tracked(original(raw, name))
        alive[id(value)] = value
        peak.append(len(alive))
        return value
    for i in range(32):
        store(tmp_path/f'{i:04}.json', {'values': list(range(50))})
    monkeypatch.setattr(files, '_validate_value', track)
    index = files.ReplayStudyFiles(tmp_path)
    assert len(index) == 32 and not alive
    assert max(peak) == 1
    for name in index:
        value = index[name]
        assert value['values'] == list(range(50))
        del value
    assert not alive


@pytest.mark.parametrize('limit', ['MAX_FILE_BYTES', 'MAX_STUDY_BYTES', 'MAX_STUDY_FILES'])
def test_budgets_reject_before_decoding(tmp_path, monkeypatch, limit):
    store(tmp_path/'a.json', {'v': 'payload'})
    monkeypatch.setattr(files, limit, 0)
    monkeypatch.setattr(files, '_validate_value', lambda *a: pytest.fail('decoded past budget'))
    with pytest.raises(ValueError, match='budget'):
        files.ReplayStudyFiles(tmp_path)


@pytest.mark.parametrize('kind', ['file', 'directory', 'root'])
def test_symlink_artifacts_rejected(tmp_path, kind):
    source = tmp_path/'source'
    source.mkdir()
    outside = tmp_path/'outside'
    outside.mkdir()
    store(outside/'a.json', {'value': 1})
    if kind == 'file':
        (source/'a.json').symlink_to(outside/'a.json')
    elif kind == 'directory':
        (source/'linked').symlink_to(outside, target_is_directory=True)
    else:
        source = tmp_path/'linked'
        source.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='local'):
        files.ReplayStudyFiles(source)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{} trailing', b'\xff'])
def test_strict_json_still_rejected(tmp_path, raw):
    (tmp_path/'a.json').write_bytes(raw)
    with pytest.raises(ValueError):
        files.ReplayStudyFiles(tmp_path)


def test_wrong_original_hash_fails_before_execution(tmp_path, monkeypatch):
    store(tmp_path/'comparison.json', {'report_hash': 'sha256:'+'0'*64})
    monkeypatch.setattr(replay, 'benchmark_rc_control_seed_paths', lambda *a, **k: pytest.fail('executed invalid original'))
    with pytest.raises(ValueError, match='report_hash'):
        execute(tmp_path, tmp_path.parent/(tmp_path.name+'-out'))


@pytest.mark.parametrize('change', ['payload', 'added', 'removed', 'symlink'])
def test_original_change_is_detected(tmp_path, change):
    store(tmp_path/'a.json', {'v': 1})
    index = files.ReplayStudyFiles(tmp_path)
    if change == 'payload':
        store(tmp_path/'a.json', {'v': 2})
    elif change == 'added':
        store(tmp_path/'b.json', {})
    elif change == 'removed':
        (tmp_path/'a.json').unlink()
    else:
        (tmp_path/'a.json').unlink()
        (tmp_path/'a.json').symlink_to('missing')
    with pytest.raises((ValueError, OSError)):
        index.verify_unchanged()


def test_changed_content_fails_lookup_and_returned_value_is_detached(tmp_path):
    store(tmp_path/'a.json', {'v': [1]})
    index = files.ReplayStudyFiles(tmp_path)
    index['a.json']['v'].append(2)
    assert index['a.json'] == {'v': [1]}
    store(tmp_path/'a.json', {'v': [2]})
    with pytest.raises(ValueError, match='changed'):
        index['a.json']


@pytest.mark.parametrize('name', ['../escape.json', '/tmp/escape.json', 'unknown.json'])
def test_lookup_requires_index_membership(tmp_path, name):
    store(tmp_path/'a.json', {})
    index = files.ReplayStudyFiles(tmp_path)
    with pytest.raises(KeyError):
        index[name]


def test_direct_comparator_matches_old_projection():
    rng = random.Random(1709)
    def tree(depth):
        if depth <= 0:
            return rng.choice([None, True, 1, 1.0, -0.0, 'a'])
        mode = rng.randrange(3)
        if mode == 0:
            return [tree(depth-1) for _ in range(rng.randrange(4))]
        if mode == 1:
            return {key: tree(depth-1) for key in rng.sample(
                ['value', 'wall_ns', 'phase_cpu_ns', 'step_hash', 'source_revision', 'work'], rng.randrange(7))}
        return tree(0)
    for _ in range(500):
        left = tree(3)
        right = copy.deepcopy(left) if rng.randrange(2) else tree(3)
        assert replay._same_without_execution_clocks(left, right) == (
            replay._without_execution_clocks(left) == replay._without_execution_clocks(right)
        )


def test_real_replay_retains_success_and_work(study, tmp_path):
    outcome = execute(study, tmp_path/'replay')
    assert outcome['numerical_reproduction_pass'] and not outcome['unknown_replay_work']
    assert outcome['fresh_native_calls'] > 16
    assert not outcome['independent_physical_validation']
    assert json.loads((tmp_path/'replay/audit.json').read_bytes()) == outcome


def test_fresh_exception_gets_terminal_receipt_and_original_exception(study, tmp_path, monkeypatch):
    error = RuntimeError('injected after a partial output')
    def interrupted(*args, **kwargs):
        root = kwargs['output_directory']
        root.mkdir()
        store(root/'partial-outcome.json', {'known_attempts': 1, 'complete': False})
        raise error
    monkeypatch.setattr(replay, 'benchmark_rc_control_seed_paths', interrupted)
    with pytest.raises(RuntimeError) as caught:
        execute(study, tmp_path/'replay')
    assert caught.value is error
    out = json.loads((tmp_path/'replay/audit.json').read_bytes())
    assert out['phase'] == 'fresh_execution' and out['status'] == 'failed'
    assert not out['numerical_reproduction_pass'] and out['unknown_replay_work']
    assert out['fresh_native_calls'] is None  # Never claim interrupted work is zero.
    assert (tmp_path/'replay/fresh/partial-outcome.json').exists()


def test_reader_failure_preserves_already_returned_known_work(study, tmp_path, monkeypatch):
    native = replay.benchmark_rc_control_seed_paths
    def corrupt_after_calculation(*args, **kwargs):
        report = native(*args, **kwargs)
        (kwargs['output_directory']/'corrupted.json').write_bytes(b'{')
        return report
    monkeypatch.setattr(replay, 'benchmark_rc_control_seed_paths', corrupt_after_calculation)
    with pytest.raises(ValueError):
        execute(study, tmp_path/'replay')
    out = json.loads((tmp_path/'replay/audit.json').read_bytes())
    assert out['phase'] == 'regenerated_artifacts'
    assert out['fresh_native_calls'] > 16 and not out['unknown_replay_work']
    assert not out['numerical_reproduction_pass']


def test_original_mutation_during_fresh_run_rejected(study, tmp_path, monkeypatch):
    original = tmp_path/'original'
    shutil.copytree(study, original)
    native = replay.benchmark_rc_control_seed_paths
    def mutate(*args, **kwargs):
        report = native(*args, **kwargs)
        store(original/'unannounced.json', {})
        return report
    monkeypatch.setattr(replay, 'benchmark_rc_control_seed_paths', mutate)
    with pytest.raises(ValueError, match='roster changed'):
        execute(original, tmp_path/'replay')
    out = json.loads((tmp_path/'replay/audit.json').read_bytes())
    assert out['phase'] == 'artifact_comparison' and not out['numerical_reproduction_pass']


def test_rehashed_work_change_remains_a_mismatch(study, tmp_path):
    original = tmp_path/'original'
    shutil.copytree(study, original)
    p = original/'comparison.json'
    report = json.loads(p.read_bytes())
    report['numerical_proposal_work']['native_core_calls_attempted'] = 0
    report['report_hash'] = _sha(_bytes({k:v for k,v in report.items() if k != 'report_hash'}))
    store(p, report)
    out = execute(original, tmp_path/'replay')
    assert not out['numerical_reproduction_pass']
    assert 'comparison.json' in out['mismatched_artifacts']


def test_receipt_write_error_does_not_replace_primary_error(study, tmp_path, monkeypatch):
    error = RuntimeError('numerical failure')
    def interrupted(*a, **k):
        raise error
    def unavailable(*a, **k):
        raise OSError('disk unavailable')
    monkeypatch.setattr(replay, 'benchmark_rc_control_seed_paths', interrupted)
    monkeypatch.setattr(replay, '_write_outcome', unavailable)
    with pytest.raises(RuntimeError) as caught:
        execute(study, tmp_path/'replay')
    assert caught.value is error
    assert (tmp_path/'replay/started.json').exists()
    assert not (tmp_path/'replay/audit.json').exists()
