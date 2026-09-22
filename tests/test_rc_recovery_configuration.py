"""Legacy parity and native paths for explicit recovery strategy selection."""
from dataclasses import FrozenInstanceError
from itertools import product
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
from structural_analysis.benchmark.rc_control_recovery_strategy import (
    RCControlRecoveryStrategy as Strategy, resolve_rc_recovery_strategy as resolve,
)
from structural_analysis.benchmark.rc_control_recovery_execution import benchmark_rc_control_seed_paths
from structural_analysis.benchmark.rc_control_continuation_replay import _without_execution_clocks
from structural_analysis.io.neutral.loader import load_neutral_json

NAMES = ('trust_region_reversal', 'frozen_parent_continuation', 'continuation_on_failure',
         'continuation_all_failed_targets', 'continuation_adaptive')
MODES = ('none', 'trust-region-reversal', 'frozen-reversal', 'frozen-failed-reversal',
         'frozen-failed-target', 'adaptive-failed-target')
VALID = {(False, False, False, False, False): 'none',
         (True, False, False, False, False): 'trust-region-reversal',
         (False, True, False, False, False): 'frozen-reversal',
         (False, True, True, False, False): 'frozen-failed-reversal',
         (False, True, True, True, False): 'frozen-failed-target',
         (False, True, True, True, True): 'adaptive-failed-target'}


def inputs():
    model = load_neutral_json(Path(__file__).resolve().parents[1] / 'examples/public_rc_fiber_frame_cantilever.json')
    request = BoundedRCFiberDirectControlRequest(
        4, (-1e-6, -2e-6, 1e-6), allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -10.0, 0.0, 0.0),),
    )
    return model, request


@pytest.mark.parametrize('flags', list(product((False, True), repeat=5)))
def test_exhaustive_legacy_flag_matrix(flags):
    kwargs = dict(zip(NAMES, flags))
    if flags not in VALID:
        with pytest.raises(ValueError):
            resolve(**kwargs)
    else:
        result = resolve(**kwargs)
        assert result.mode == VALID[flags] and result.legacy_options() == kwargs


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('bad', [1, None, 'false', np.bool_(False)])
def test_nonboolean_flags_remain_invalid(name, bad):
    with pytest.raises(ValueError):
        resolve(**{name: bad})


@pytest.mark.parametrize('mode', MODES)
def test_configuration_is_detached_and_immutable(mode):
    strategy = Strategy(mode)
    options = strategy.legacy_options()
    options['continuation_adaptive'] = not options['continuation_adaptive']
    assert options != strategy.legacy_options()
    with pytest.raises(FrozenInstanceError):
        strategy.mode = 'none'
    if strategy.identity is not None:
        assert Strategy.from_identity(strategy.identity) == strategy


@pytest.mark.parametrize('mode', ['', 'future', True, None, {}])
def test_unknown_mode_rejected(mode):
    with pytest.raises(ValueError):
        Strategy(mode)


@pytest.mark.parametrize('options', [
    {'recovery_strategy': 'adaptive-failed-target'},
    {'recovery_strategy': Strategy('none'), 'frozen_parent_continuation': True},
    {'recovery_strategy': Strategy('adaptive-failed-target'), 'observe_initial_residuals': True},
    {'recovery_strategy': Strategy('frozen-reversal'), 'proposal': lambda c: None},
    {'recovery_strategy': Strategy('trust-region-reversal'), 'coordinate_precision': 'twofold-increment'},
])
def test_invalid_selection_rejected_before_output(tmp_path, options):
    with pytest.raises(ValueError):
        benchmark_rc_control_seed_paths(*inputs(), source_revision='a'*40,
                                        output_directory=tmp_path/'study', **options)
    assert not (tmp_path/'study').exists()


@pytest.mark.parametrize('mode', MODES)
def test_explicit_and_legacy_native_paths_have_identical_nonclock_artifacts(tmp_path, mode):
    import json
    strategy = Strategy(mode)
    results = []
    for name, options in [('legacy', strategy.legacy_options()), ('explicit', {'recovery_strategy': strategy})]:
        results.append(benchmark_rc_control_seed_paths(
            *inputs(), source_revision='a'*40, output_directory=tmp_path/name,
            record_assembly_work=True, **options,
        ))
    assert _without_execution_clocks(results[0]) == _without_execution_clocks(results[1])
    left = {p.relative_to(tmp_path/'legacy').as_posix(): p for p in (tmp_path/'legacy').rglob('*.json')}
    right = {p.relative_to(tmp_path/'explicit').as_posix(): p for p in (tmp_path/'explicit').rglob('*.json')}
    assert left.keys() == right.keys()
    for name in left:
        assert _without_execution_clocks(json.loads(left[name].read_bytes())) == _without_execution_clocks(json.loads(right[name].read_bytes())), name
    if mode in ('frozen-failed-reversal', 'frozen-failed-target', 'adaptive-failed-target'):
        assert results[1]['numerical_proposal_work']['native_core_calls_attempted'] == 0


def test_new_modules_registered_without_narrowing_full_test_gate():
    import shlex
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root/'.github/workflows/python-test-collection.yml').read_text(), Loader=yaml.BaseLoader)
    job = workflow['jobs']['development_contracts']
    run = next(s['run'] for s in job['steps'] if s['name'] == 'Run development contracts from the committed checkout')
    words = shlex.split(run)
    for name in ('test_rc_recovery_configuration.py', 'test_rc_replay_streaming.py', 'test_rc_branch_diagnostic.py'):
        assert words.count('tests/'+name) == 1
        assert (root/'tests'/name).is_file()
    full = workflow['jobs']['full']
    assert full['needs'] == 'full_shards' and full['if'] == '${{ always() }}'
    assert full['steps'][0]['run'] == 'test "$FULL_SHARDS_RESULT" = "success"'
    assert workflow['jobs']['full_shards']['strategy']['matrix']['shard'] == ['0','1','2','3']
    assert workflow['permissions'] == {'contents': 'read'}
