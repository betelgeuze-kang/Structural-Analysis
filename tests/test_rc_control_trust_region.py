"""Numerical proposal cost, unchanged native acceptance, and failure retention."""

from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
from structural_analysis.io.neutral.loader import load_neutral_json


def run(tmp_path, **options):
    return benchmark_rc_control_seed_paths(
        load_neutral_json(Path("examples/public_rc_fiber_frame_l_frame_material_history.json")),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-6, -2e-6, -1.5e-6), allow_reversals=True, maximum_reversals=1,
        ),
        source_revision="a" * 40, output_directory=tmp_path / "study",
        trust_region_reversal=not options.get('frozen_parent_continuation', False), **options,
    )


def test_full_path_reversal_is_costed_and_fresh_reference_checked(tmp_path):
    report = run(tmp_path, record_assembly_work=True)
    assert report['reference_repeat_exact']
    assert all(c['full_history_pass'] for c in report['comparisons'].values())
    arm = report['arms']['proposal']
    assert arm['status'] == 'complete'
    observations = [e['numerical_proposal'] for e in arm['entries']]
    assert [o['status'] for o in observations] == ['abstained', 'abstained', 'returned']
    last = observations[-1]
    assert last['assembly_attempts'] == sum(last['assembly_counts'].values()) > 0
    assert last['parent_unchanged'] and not last['optimizer_confers_acceptance']
    assert 0 < last['wall_ns'] <= arm['entries'][-1]['proposal_wall_ns'] < arm['wall_ns']
    assert arm['entries'][-1]['invocations']
    assert report['numerical_proposal']['cost_included_in_path_wall']


def test_optimizer_exception_retains_assembly_and_stops_before_terminal_newton(tmp_path, monkeypatch):
    from scipy import optimize

    def interrupted(fun, x, **kwargs):
        fun(x)
        raise RuntimeError('injected after a real full assembly')

    monkeypatch.setattr(optimize, 'least_squares', interrupted)
    report = run(tmp_path)
    arm = report['arms']['proposal']
    assert not report['all_execution_work_reported']
    assert arm['status'] == 'incomplete' and arm['accepted_target_count'] == 2
    last = arm['entries'][-1]
    assert last['numerical_proposal']['assembly_attempts'] == 1
    assert last['numerical_proposal']['unknown_work']
    assert last['numerical_proposal']['parent_unchanged']
    assert last['invocations'] == []
    assert arm['failure']['phase'] == 'numerical_proposal'
    assert not report['comparisons']['proposal']['full_history_pass']


@pytest.mark.parametrize('options', [
    {'proposal': lambda context: None},
    {'coordinate_precision': 'twofold-increment'},
    {'proposal_abstention_strategy': 'secant'},
])
def test_conflicting_strategy_rejected_before_output(tmp_path, options):
    with pytest.raises(ValueError, match='isolated binary64'):
        run(tmp_path, **options)
    assert not (tmp_path / 'study').exists()


@pytest.mark.parametrize('width,top,bottom,strategy,on_failure', [
    (0.48, 0.0002, 0.00025, 'trust_region_reversal', False),
    (0.32, 0.0002, 0.00025, 'frozen_parent_continuation', False),
    (0.32, 0.0002, 0.00025, 'frozen_parent_continuation', True),
    (0.32, 0.0003, 0.0004, 'frozen_parent_continuation', False),
    (0.32, 0.0003, 0.0004, 'frozen_parent_continuation', True),
    (0.48, 0.0002, 0.00025, 'frozen_parent_continuation', False),
    (0.48, 0.0002, 0.00025, 'frozen_parent_continuation', True),
])
def test_large_reversal_completes_proposal_without_crediting_failed_reference(
    tmp_path, width, top, bottom, strategy, on_failure,
):
    from structural_analysis.benchmark import fiber_frame_design as design

    model = design.apply_fiber_frame_section_changes(
        load_neutral_json(Path('examples/public_rc_fiber_frame_cantilever.json')),
        design.FiberFrameDesignCandidate('cheap', (
            design.FiberFrameSectionChange(
                'RC1', width_m=width, top_bar_area_m2=top, bottom_bar_area_m2=bottom,
            ),
        )),
    )
    report = benchmark_rc_control_seed_paths(
        model, BoundedRCFiberDirectControlRequest(
            4, (-0.02, -0.04, 0.02), allow_reversals=True, maximum_reversals=2,
            constant_nodal_loads=(('N2', -600., 0., 0.),),
        ),
        source_revision='a' * 40, output_directory=tmp_path / 'large',
        continuation_on_failure=on_failure, **{strategy: True},
    )
    assert report['arms']['proposal']['status'] == 'complete'
    assert report['arms']['proposal']['accepted_target_count'] == 3
    assert report['arms']['reference']['status'] == 'incomplete'
    assert report['fresh_reference']['status'] == 'incomplete'
    assert report['all_execution_work_reported']
    assert not report['comparisons']['proposal']['full_history_pass']
    assert not report['claims']['performance_improvement']
    assert not report['claims']['independent_validation']
    last = report['arms']['proposal']['entries'][-1]
    assert last['numerical_proposal']['parent_unchanged']
    assert last['invocations'][-1]['committed']
    assert last['invocations'][-1]['work']['core_calls'] == 1
    if on_failure:
        assert len(last['invocations']) == 2 and not last['invocations'][0]['committed']
        assert last['recovery_after_failed_invocation'] == 1
        assert last['proposal_decision'] == 'proposed_after_reference_failure'

    if strategy == 'frozen_parent_continuation':
        import json
        from structural_analysis.benchmark.rc_control_design import _sha

        work = report['numerical_proposal_work']
        assert work['native_core_calls_attempted'] == 16
        assert work['known_newton_iterations'] > 16 and not work['unknown_work']
        numerical = last['numerical_proposal']
        assert not numerical['intermediate_material_checkpoints_adopted']
        assert len(numerical['stages']) == 16
        parents = []
        for stage in numerical['stages']:
            ref = stage['artifact']
            raw = (tmp_path / 'large/proposal' / ref['path']).read_bytes()
            assert _sha(raw) == ref['sha256'] and len(raw) == ref['byte_length']
            record = json.loads(raw)
            parents.append(record['parent_checkpoint'])
            assert record['committed'] and stage['parent_hash'] == last['parent_hash']
        assert all(parent == parents[0] for parent in parents)


def test_continuation_interruption_retains_known_stages_and_unknown_attempt(tmp_path, monkeypatch):
    from structural_analysis.benchmark import rc_control_frozen_continuation as module

    original = module.solve_stateful_fiber_frame2d_displacement_control_step
    calls = []

    def interrupted(problem, parent, **options):
        calls.append(parent.canonical_bytes())
        if len(calls) == 2:
            raise RuntimeError('injected second trial interruption')
        return original(problem, parent, **options)

    monkeypatch.setattr(module, 'solve_stateful_fiber_frame2d_displacement_control_step', interrupted)
    report = run(tmp_path, frozen_parent_continuation=True)
    assert calls[0] == calls[1]
    assert not report['all_execution_work_reported']
    work = report['numerical_proposal_work']
    assert work['unknown_work'] and work['native_core_calls_attempted'] == 2
    assert work['known_newton_iterations'] > 0
    arm = report['arms']['proposal']
    assert arm['status'] == 'incomplete' and arm['accepted_target_count'] == 2
    last = arm['entries'][-1]
    assert not last['invocations']
    stages = last['numerical_proposal']['stages']
    assert not stages[0]['unknown_work'] and stages[1]['unknown_work']
    assert stages[0]['artifact']


@pytest.fixture(scope='module')
def continuation_original(tmp_path_factory):
    from structural_analysis.benchmark import fiber_frame_design as design

    root = tmp_path_factory.mktemp('continuation-original')
    model = design.apply_fiber_frame_section_changes(
        load_neutral_json(Path('examples/public_rc_fiber_frame_cantilever.json')),
        design.FiberFrameDesignCandidate('cheap', (design.FiberFrameSectionChange(
            'RC1', width_m=0.32, top_bar_area_m2=0.0002, bottom_bar_area_m2=0.00025,
        ),)),
    )
    request = BoundedRCFiberDirectControlRequest(
        4, (-.02, -.04, .02), allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -600., 0., 0.),),
    )
    benchmark_rc_control_seed_paths(
        model, request, source_revision='a' * 40, output_directory=root / 'study',
        frozen_parent_continuation=True, record_assembly_work=True, record_assembly_timing=True,
    )
    return root / 'study', model, request


def test_fresh_original_replay_counts_all_trials_without_promoting_reference(tmp_path, continuation_original):
    from structural_analysis.benchmark.rc_control_continuation_replay import replay_rc_frozen_continuation_study

    study, model, request = continuation_original
    result = replay_rc_frozen_continuation_study(
        study, model, request, output_directory=tmp_path / 'replay', replay_source_revision='b' * 40,
    )
    assert result['numerical_reproduction_pass'] and not result['mismatched_artifacts']
    assert result['fresh_native_calls'] == 33 and result['fresh_known_newton_iterations'] > 33
    assert not result['fresh_reference_comparisons_pass']
    assert not result['independent_physical_validation']
    assert not result['original_execution_clocks_authenticated']
    assert result['loaded_source_sha256']


@pytest.mark.parametrize('mutation', ['stage', 'work'])
def test_replay_rejects_rehashed_numerical_or_work_falsification(
    tmp_path, continuation_original, mutation,
):
    import json
    import shutil
    from structural_analysis.benchmark.rc_control_design import _bytes, _sha
    from structural_analysis.benchmark.rc_control_continuation_replay import replay_rc_frozen_continuation_study

    original, model, request = continuation_original
    study = tmp_path / 'modified'
    shutil.copytree(original, study)
    path = study / ('proposal/002-continuation-000.json' if mutation == 'stage' else 'comparison.json')
    value = json.loads(path.read_bytes())
    if mutation == 'stage':
        value['trial_solution']['metrics']['relative_residual'] = 0.5
        key = 'step_hash'
    else:
        value['numerical_proposal_work']['native_core_calls_attempted'] = 0
        key = 'report_hash'
    value.pop(key)
    from structural_analysis.engine_v2.contracts._canonical import canonical_hash
    value[key] = canonical_hash(value) if key == 'step_hash' else _sha(_bytes(value))
    path.write_bytes(_bytes(value))
    result = replay_rc_frozen_continuation_study(
        study, model, request, output_directory=tmp_path / 'replay', replay_source_revision='b' * 40,
    )
    assert not result['numerical_reproduction_pass']
    assert path.relative_to(study).as_posix() in result['mismatched_artifacts']
    assert result['fresh_native_calls'] == 33


def test_replay_rejects_changed_request_before_running(tmp_path, continuation_original, monkeypatch):
    from dataclasses import replace
    from structural_analysis.benchmark import rc_control_continuation_replay as replay

    original, model, request = continuation_original
    monkeypatch.setattr(replay, 'benchmark_rc_control_seed_paths', lambda *a, **k: pytest.fail('must preflight'))
    with pytest.raises(ValueError, match='matching constant-load'):
        replay.replay_rc_frozen_continuation_study(
            original, model, replace(request, targets_m=(-.02, -.04, .01)),
            output_directory=tmp_path / 'replay', replay_source_revision='b' * 40,
        )
    assert not (tmp_path / 'replay').exists()


def test_failure_only_strategy_does_no_trial_work_on_successful_native_paths(tmp_path, monkeypatch):
    import json
    from structural_analysis.benchmark.rc_control_frozen_continuation import FrozenParentContinuationProposal

    monkeypatch.setattr(FrozenParentContinuationProposal, 'propose',
                        lambda *a, **k: pytest.fail('successful ordinary solve must not trigger trials'))
    report = run(tmp_path, frozen_parent_continuation=True, continuation_on_failure=True)
    assert all(c['full_history_pass'] for c in report['comparisons'].values())
    assert report['numerical_proposal_work']['native_core_calls_attempted'] == 0
    assert report['numerical_proposal_work']['known_newton_iterations'] == 0
    assert all(e['numerical_proposal']['status'] == 'deferred' for e in report['arms']['proposal']['entries'])
    for index in range(3):
        reference = json.loads((tmp_path / 'study/reference' / f'{index:03d}-1-step.json').read_bytes())
        proposal = json.loads((tmp_path / 'study/proposal' / f'{index:03d}-1-step.json').read_bytes())
        assert reference == proposal


def test_failure_only_original_replay_preserves_failed_attempt_and_all_costs(tmp_path, continuation_original):
    from structural_analysis.benchmark.rc_control_continuation_replay import replay_rc_frozen_continuation_study

    _, model, request = continuation_original
    original = benchmark_rc_control_seed_paths(
        model, request, source_revision='a' * 40, output_directory=tmp_path / 'original',
        frozen_parent_continuation=True, continuation_on_failure=True,
    )
    assert original['arms']['proposal']['status'] == 'complete'
    replay = replay_rc_frozen_continuation_study(
        tmp_path / 'original', model, request, output_directory=tmp_path / 'replay',
        replay_source_revision='b' * 40,
    )
    assert replay['numerical_reproduction_pass']
    assert replay['fresh_native_calls'] == 34
    assert not replay['fresh_reference_comparisons_pass']


def test_failed_reversal_recovery_stops_on_unknown_trial_without_retrying(tmp_path, continuation_original, monkeypatch):
    from structural_analysis.benchmark import rc_control_frozen_continuation as module

    _, model, request = continuation_original
    original = module.solve_stateful_fiber_frame2d_displacement_control_step
    calls = []

    def interrupted(problem, parent, **options):
        calls.append(parent.state_hash)
        if len(calls) == 2:
            raise RuntimeError('trial interruption')
        return original(problem, parent, **options)

    monkeypatch.setattr(module, 'solve_stateful_fiber_frame2d_displacement_control_step', interrupted)
    report = benchmark_rc_control_seed_paths(
        model, request, source_revision='a' * 40, output_directory=tmp_path / 'failure',
        frozen_parent_continuation=True, continuation_on_failure=True,
    )
    assert len(calls) == 2 and calls[0] == calls[1]
    last = report['arms']['proposal']['entries'][-1]
    assert len(last['invocations']) == 1
    assert not last['invocations'][0]['committed'] and last['invocations'][0]['rollback_exact']
    assert report['numerical_proposal_work']['native_core_calls_attempted'] == 2
    assert report['numerical_proposal_work']['unknown_work']
    assert not report['all_execution_work_reported']
    assert report['arms']['proposal']['status'] == 'incomplete'


def test_parent_step_budget_includes_internal_continuation_calls(tmp_path, continuation_original):
    import json
    from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext
    from structural_analysis.benchmark.rc_control_design import _bytes

    study, model, request = continuation_original
    raw = json.loads((study / 'proposal/002-context.json').read_bytes())
    raw['accepted_targets_m'] = tuple(raw['accepted_targets_m'])
    raw['accepted_augmented_coordinates_m'] = tuple(map(tuple, raw['accepted_augmented_coordinates_m']))
    context = RCControlSeedContext(**raw)
    stage = json.loads((study / 'proposal/002-continuation-000.json').read_bytes())
    report = benchmark_rc_control_seed_paths(
        model, request, source_revision='a' * 40, output_directory=tmp_path / 'parent',
        frozen_parent_continuation=True, continuation_on_failure=True,
        parent_checkpoint_bytes=_bytes(stage['parent_checkpoint']), accepted_context=context,
    )
    assert report['maximum_numerical_core_calls'] == 22
    arms = [*report['arms'].values(), report['fresh_reference']]
    ordinary = sum(i['work']['core_calls'] for a in arms for e in a['entries'] for i in e['invocations'])
    assert ordinary + report['numerical_proposal_work']['native_core_calls_attempted'] <= report['maximum_numerical_core_calls']
    assert report['arms']['proposal']['status'] == 'complete'


@pytest.mark.parametrize('amplitude', [.02, .04])
def test_failed_first_l_frame_target_uses_original_parent_continuation(tmp_path, amplitude):
    import json

    model = load_neutral_json(Path('examples/public_rc_fiber_frame_l_frame_material_history.json'))
    request = BoundedRCFiberDirectControlRequest(
        7, (-amplitude / 2, -amplitude, amplitude / 2),
        allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N3', 0., -25., 0.),),
    )
    report = benchmark_rc_control_seed_paths(
        model, request, source_revision='a' * 40, output_directory=tmp_path / 'l-frame',
        frozen_parent_continuation=True, continuation_on_failure=True,
        continuation_all_failed_targets=True,
    )
    arm = report['arms']['proposal']
    assert arm['status'] == ('complete' if amplitude == .02 else 'incomplete')
    assert arm['accepted_target_count'] == (3 if amplitude == .02 else 0)
    assert report['arms']['reference']['status'] == 'incomplete'
    assert not report['comparisons']['proposal']['full_history_pass']
    assert report['all_execution_work_reported']
    assert report['numerical_proposal']['maximum_additional_native_calls'] == 48
    assert report['numerical_proposal_work']['native_core_calls_attempted'] <= 48
    first = arm['entries'][0]
    assert not first['invocations'][0]['committed']
    if amplitude == .02:
        assert len(first['invocations']) == 2 and first['invocations'][1]['committed']
        assert first['numerical_proposal']['native_core_calls_attempted'] == 16
        from structural_analysis.benchmark.rc_control_continuation_replay import replay_rc_frozen_continuation_study
        replay = replay_rc_frozen_continuation_study(
            tmp_path / 'l-frame', model, request, output_directory=tmp_path / 'replay',
            replay_source_revision='b' * 40,
        )
        assert replay['numerical_reproduction_pass'] and not replay['fresh_reference_comparisons_pass']
    else:
        assert len(first['invocations']) == 1
        trial = first['numerical_proposal']
        assert trial['status'] == 'blocked' and not trial['unknown_work']
        assert trial['native_core_calls_attempted'] == len(trial['stages']) == 8
        assert not trial['stages'][-1]['committed']
    for entry in arm['entries']:
        for stage in entry['numerical_proposal'].get('stages', []):
            raw = json.loads((tmp_path / 'l-frame/proposal' / stage['artifact']['path']).read_bytes())
            assert raw['parent_checkpoint']['state_hash'] == entry['parent_hash']


def test_all_target_scope_requires_failure_only_mode_before_output(tmp_path):
    with pytest.raises(ValueError, match='all-target continuation'):
        run(tmp_path, frozen_parent_continuation=True, continuation_all_failed_targets=True)
    assert not (tmp_path / 'study').exists()
