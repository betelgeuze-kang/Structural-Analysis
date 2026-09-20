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


@pytest.mark.parametrize('width,top,bottom,strategy', [
    (0.48, 0.0002, 0.00025, 'trust_region_reversal'),
    (0.32, 0.0002, 0.00025, 'frozen_parent_continuation'),
    (0.32, 0.0003, 0.0004, 'frozen_parent_continuation'),
    (0.48, 0.0002, 0.00025, 'frozen_parent_continuation'),
])
def test_large_reversal_completes_proposal_without_crediting_failed_reference(
    tmp_path, width, top, bottom, strategy,
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
        **{strategy: True},
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
    assert last['invocations'][0]['committed']
    assert last['invocations'][0]['work']['core_calls'] == 1

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
