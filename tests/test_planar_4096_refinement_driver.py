"""4096 driver gates and bounded output behavior without a structural solve."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import run_planar_256_refinement as runner
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
)


@pytest.mark.parametrize('layers', [1024, 2048, 4096])
def test_pinned_protocol_bytes_keep_existing_digests(layers, tmp_path):
    record = runner.protocol_record(
        layers, layers // 2, 461,
        StatefulCorotationalFiberFrame2DDisplacementControlConfig(),
    )
    path = tmp_path / 'protocol.json'
    runner.write_json(path, record)
    assert runner.file_sha256(path) == runner.PROTOCOL_SHA256[layers]
    assert record['target_displacements_m'] == tuple(i / 500 for i in range(1, 41))
    assert record['constant_axial_load'] is False


def test_cli_lists_4096_without_launching_solve():
    result = subprocess.run(
        [sys.executable, str(Path(runner.__file__)), '--help'],
        capture_output=True, text=True, check=True,
    )
    assert '--layers {256,512,1024,2048,4096}' in result.stdout


def test_4096_still_rejects_changed_frozen_manifest_before_output(tmp_path):
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    (bundle / 'inputs-manifest.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='manifest changed'):
        runner.run(bundle, tmp_path, tmp_path, layers=4096)
    assert sorted(path.name for path in tmp_path.iterdir()) == ['bundle']


def test_output_preflight_requires_measurable_space_for_reader_caps(tmp_path, monkeypatch):
    required = (runner.MAX_FULL_JSON_BYTES + 40 * runner.MAX_STEP_JSON_BYTES
                + runner.MAX_METADATA_JSON_BYTES + runner.OUTPUT_FORMAT_RESERVE_BYTES)
    monkeypatch.setattr(runner.shutil, 'disk_usage',
                        lambda path: SimpleNamespace(free=required))
    runner.preflight_output_format(4096, tmp_path)
    monkeypatch.setattr(runner.shutil, 'disk_usage',
                        lambda path: SimpleNamespace(free=required - 1))
    with pytest.raises(ValueError, match='output capacity unestablished'):
        runner.preflight_output_format(4096, tmp_path)

    def unavailable(path):
        raise OSError('unavailable')

    monkeypatch.setattr(runner.shutil, 'disk_usage', unavailable)
    with pytest.raises(ValueError, match='cannot measure free space'):
        runner.preflight_output_format(4096, tmp_path)
    runner.preflight_output_format(2048, tmp_path)


def test_step_limit_keeps_partial_packet_and_explicit_failure_summary(tmp_path):
    step = {'committed': True, 'claim': 'synthetic'}
    maximum_step = len((json.dumps(step, indent=2) + '\n').encode()) - 1
    with pytest.raises(runner.OutputFormatLimitError, match='step JSON') as caught:
        runner.write_path_artifacts(
            tmp_path, {'steps': []}, iter([step]),
            maximum_full_bytes=100_000, maximum_step_bytes=maximum_step,
            maximum_steps=40,
        )
    partial_step = tmp_path / 'steps/0000.json'
    before = partial_step.read_bytes()
    path = SimpleNamespace(
        steps=[SimpleNamespace(committed=True) for _ in range(40)],
        status='ready', contract_pass=True,
    )
    runner.record_output_format_failure(
        tmp_path, layers=4096, target_count=40, path=path,
        solve_wall_ns=12345, through_failure_wall_ns=67890,
        error=caught.value,
    )
    failure = json.loads((tmp_path / 'failure-summary.json').read_text())
    assert failure['status'] == 'incomplete'
    assert failure['reason_code'] == 'output_format_limit'
    assert failure['solve_wall_ns'] == 12345
    assert failure['through_failure_wall_ns'] == 67890
    assert failure['requested_targets'] == 40
    assert failure['attempted_targets'] == 40
    assert failure['committed_steps'] == 40
    assert failure['written_bytes']['step_json'] == len(before)
    assert failure['written_bytes']['total'] == (
        (tmp_path / 'repeat-0.json').stat().st_size + len(before)
    )
    assert partial_step.read_bytes() == before
    assert not (tmp_path / 'path-index.json').exists()


def test_full_limit_stops_before_index_and_preserves_completed_step(tmp_path):
    step = {'committed': True, 'claim': 'synthetic'}
    metadata = {'steps': []}
    full = ''.join(runner.iter_path_json(metadata, iter([step]))).encode()
    step_bytes = (json.dumps(step, indent=2) + '\n').encode()
    with pytest.raises(runner.OutputFormatLimitError, match='full JSON'):
        runner.write_path_artifacts(
            tmp_path, metadata, iter([step]),
            maximum_full_bytes=len(full) - 1,
            maximum_step_bytes=len(step_bytes), maximum_steps=40,
        )
    assert (tmp_path / 'steps/0000.json').read_bytes() == step_bytes
    assert not (tmp_path / 'path-index.json').exists()


def test_step_count_limit_stops_before_unplanned_file_or_index(tmp_path):
    with pytest.raises(runner.OutputFormatLimitError, match='bounded 1-step'):
        runner.write_path_artifacts(
            tmp_path, {'steps': []}, iter([{'step': 1}, {'step': 2}]),
            maximum_full_bytes=100_000, maximum_step_bytes=100_000,
            maximum_steps=1,
        )
    assert (tmp_path / 'steps/0000.json').exists()
    assert not (tmp_path / 'steps/0001.json').exists()
    assert not (tmp_path / 'path-index.json').exists()


def test_exact_output_bounds_preserve_original_full_json_bytes(tmp_path):
    step = {'committed': True, 'claim': 'synthetic'}
    metadata = {'steps': [], 'source': 'frozen'}
    full = (json.dumps({**metadata, 'steps': [step]}, indent=2, allow_nan=False)
            + '\n').encode()
    step_bytes = (json.dumps(step, indent=2, allow_nan=False) + '\n').encode()
    receipt = runner.write_path_artifacts(
        tmp_path, metadata, iter([step]), maximum_full_bytes=len(full),
        maximum_step_bytes=len(step_bytes), maximum_steps=40,
    )
    assert (tmp_path / 'repeat-0.json').read_bytes() == full
    assert receipt['full']['sha256'] == hashlib.sha256(full).hexdigest()
    assert (tmp_path / 'path-index.json').is_file()
