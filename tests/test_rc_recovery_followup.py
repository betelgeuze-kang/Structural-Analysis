"""Follow-up integration: actual accepted history, experimental seeds, safe I/O."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig as Config,
    StatefulFiberFrame2DDisplacementControlStepAdapter as Adapter,
    solve_stateful_fiber_frame2d_displacement_control_step as solve,
)
from structural_analysis.benchmark import rc_control_branch_diagnostic as diagnostic
from structural_analysis.benchmark import rc_control_branch_seed as candidate
from structural_analysis.benchmark import rc_control_replay_files as files
from structural_analysis.benchmark import rc_recovery_cli as cli
from structural_analysis.benchmark.rc_control_continuation_replay import _without_execution_clocks
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]


def model():
    return load_neutral_json(ROOT/'examples/public_rc_fiber_frame_cantilever.json')


@pytest.fixture
def native():
    compiled, blockers, _ = public._compile(model())
    assert compiled is not None and not blockers
    return compiled.problem, initial_stateful_fiber_frame2d_checkpoint(compiled.problem)


@pytest.fixture
def accepted_native():
    authored = model()
    authored.loads[0]['components'].update(FX=-10., FY=0.)
    compiled, blockers, _ = public._compile(authored)
    assert compiled is not None and not blockers
    problem = compiled.problem
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    result = solve(problem, parent, control_global_dof=3, target_control_displacement_m=-.002)
    assert result.committed
    accepted = result.accepted_checkpoint
    states = [state for element in accepted.to_dict()['element_states']
              for point in element['integration_point_states'] for state in point['fiber_states']]
    assert max(state.get('compressive_history_strain', 0) for state in states) > 0
    return problem, accepted


def start(native, *, dof=4, target=1e-6):
    problem, parent = native
    adapter = Adapter(problem, parent, dof, target, Config())
    x = adapter.initial_free_displacements_m()
    observed = adapter.observe(x)
    direction = np.linalg.solve(observed.augmented_jacobian_kn_per_m, -observed.augmented_residual_kn)
    return dict(control_global_dof=dof, target_m=target,
                coordinates=x, direction=direction)


@pytest.mark.parametrize('target', [1e-6, -1e-6, 2e-6])
def test_candidate_is_finite_costed_and_confirmed_only_by_native(native, target):
    options = start(native, target=target)
    before = native[1].canonical_bytes()
    result = candidate.run_rc_branch_sampled_seed(*native, **options)
    assert result['status'] == 'native_accepted' and result['native_accepted']
    assert result['native_core_calls_attempted'] == 1
    assert result['diagnostic_assembly_attempts'] == 18
    assert not result['unknown_work'] and not result['candidate_confers_acceptance']
    assert result['native_step']['committed']
    assert result['native_step']['parent_checkpoint'] == native[1].to_dict()
    assert result['native_step']['trial_solution']['metrics']['relative_residual'] <= Config().newton.residual_tolerance
    assert native[1].canonical_bytes() == before
    assert not result['full_history_verified'] and not result['original_80mm_witness_qualified']
    assert not result['design_approval']


def test_no_descent_means_no_native_attempt(native, monkeypatch):
    options = start(native)
    options['direction'] *= -1
    monkeypatch.setattr(candidate, 'solve_stateful_fiber_frame2d_displacement_control_step',
                        lambda *a, **k: pytest.fail('non-descending candidate dispatched'))
    result = candidate.run_rc_branch_sampled_seed(*native, **options)
    assert result['status'] == 'abstained' and result['seed'] is None
    assert result['native_core_calls_attempted'] == 0 and not result['native_accepted']


def test_real_nonzero_history_is_preserved_and_repeated(accepted_native):
    options = start(accepted_native, dof=3, target=-.0015)
    before = accepted_native[1].canonical_bytes()
    out = diagnostic.observe_rc_control_branch_path(*accepted_native, **options)
    again = diagnostic.observe_rc_control_branch_path(*accepted_native, **options)
    assert out['complete'] and out['input_binding']['parent_hash'] == accepted_native[1].state_hash
    assert _without_execution_clocks(out) == _without_execution_clocks(again)
    assert accepted_native[1].canonical_bytes() == before
    # Native compression history is nonzero; this fixture is not a claimed
    # accepted plastic/damaged or original 80mm checkpoint.
    result = candidate.run_rc_branch_sampled_seed(*accepted_native, **options)
    assert result['native_accepted'] and accepted_native[1].canonical_bytes() == before


def test_wrong_problem_parent_pair_is_rejected(native, accepted_native):
    with pytest.raises(ValueError):
        diagnostic.observe_rc_control_branch_path(native[0], accepted_native[1], **start(native))


def test_diagnostic_interruption_cannot_choose_completed_partial_samples(native, monkeypatch):
    options = start(native)
    original = diagnostic.StatefulFiberFrame2DDisplacementControlStepAdapter.observe
    calls = []
    def interrupted(self, x):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('injected third diagnostic sample')
        return original(self, x)
    monkeypatch.setattr(diagnostic.StatefulFiberFrame2DDisplacementControlStepAdapter, 'observe', interrupted)
    monkeypatch.setattr(candidate, 'solve_stateful_fiber_frame2d_displacement_control_step',
                        lambda *a, **k: pytest.fail('partial diagnostic promoted'))
    result = candidate.run_rc_branch_sampled_seed(*native, **options)
    assert result['unknown_work'] and result['diagnostic_assembly_attempts'] == 3
    assert result['native_core_calls_attempted'] == 0 and result['seed'] is None


def test_native_exception_does_not_erase_attempt(native, monkeypatch):
    options = start(native)
    def broken(*a, **k):
        raise RuntimeError('native interrupted')
    monkeypatch.setattr(candidate, 'solve_stateful_fiber_frame2d_displacement_control_step', broken)
    result = candidate.run_rc_branch_sampled_seed(*native, **options)
    assert result['status'] == 'failed' and result['phase'] == 'native_confirmation'
    assert result['native_core_calls_attempted'] == 1 and result['unknown_work']
    assert not result['native_accepted'] and result['native_step'] is None


def test_descending_residual_is_not_native_acceptance(native, monkeypatch):
    options = start(native)
    # Controlled rejected confirmation: admission plumbing, not solver physics.
    result = SimpleNamespace(committed=False, trial_solution=SimpleNamespace(metrics={
        'newton_iteration_count': 2, 'linear_solve_count': 2}),
        to_dict=lambda: {'committed': False})
    monkeypatch.setattr(candidate, 'solve_stateful_fiber_frame2d_displacement_control_step', lambda *a, **k: result)
    out = candidate.run_rc_branch_sampled_seed(*native, **options)
    assert out['status'] == 'native_rejected' and not out['native_accepted']
    assert out['known_newton_iterations'] == 2 and not out['unknown_work']


@pytest.mark.parametrize('fractions', [(0.,), (0., True), (0.,.5,.5), (0., float('inf')), tuple(i/65 for i in range(66))])
def test_candidate_rejects_bad_budget_or_grid_before_solving(native, monkeypatch, fractions):
    options = start(native)
    monkeypatch.setattr(candidate, 'solve_stateful_fiber_frame2d_displacement_control_step', lambda *a, **k: pytest.fail('invalid dispatch'))
    with pytest.raises(ValueError):
        candidate.run_rc_branch_sampled_seed(*native, fractions=fractions, **options)


def test_candidate_rejects_retained_coordinate_profile_before_assembly(native):
    with pytest.raises(ValueError, match='binary64'):
        candidate.run_rc_branch_sampled_seed(SimpleNamespace(coordinate_precision='twofold-increment'),
            native[1], **start(native))


def test_computed_nonfinite_diagnostic_is_not_serialized_as_success(native, monkeypatch):
    options = start(native)
    monkeypatch.setattr(diagnostic, '_relative_residual_vector', lambda *a: float('inf'))
    out = diagnostic.observe_rc_control_branch_path(*native, **options)
    assert not out['complete'] and out['unknown_work']
    assert out['assembly_attempts'] == 1 and out['rows'][0]['error_type'] == 'ValueError'
    json.dumps(out, allow_nan=False)


def test_initial_reader_binds_one_read_then_performs_full_recheck(tmp_path, monkeypatch):
    for i in range(5):
        (tmp_path/f'{i}.json').write_text('{"value":1}')
    calls = []
    original = files._open_regular
    def counted(path, root):
        calls.append(path.name)
        return original(path, root)
    monkeypatch.setattr(files, '_open_regular', counted)
    index = files.ReplayStudyFiles(tmp_path)
    assert len(calls) == 10  # initial same-byte validate plus complete hash recheck
    assert index['0.json'] == {'value': 1} and len(calls) == 11


def test_mutation_during_initial_decode_is_still_rejected(tmp_path, monkeypatch):
    path = tmp_path/'a.json'; path.write_text('{"value":1}')
    original = files._validate_value
    def changed(raw, name):
        value = original(raw, name)
        path.write_text('{"value":2}')
        return value
    monkeypatch.setattr(files, '_validate_value', changed)
    with pytest.raises(ValueError, match='changed'):
        files.ReplayStudyFiles(tmp_path)


def write_request(tmp_path):
    request = BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6, 1e-6), allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -10., 0., 0.),))
    path = tmp_path/'request.json'; path.write_text(json.dumps(request.to_dict()))
    return path


def arguments(tmp_path):
    return ['run', '--model', str(ROOT/'examples/public_rc_fiber_frame_cantilever.json'),
            '--request', str(write_request(tmp_path)), '--output', str(tmp_path/'out'),
            '--strategy', 'adaptive-failed-target', '--source-revision', 'a'*40]


def test_cli_actual_run_and_fresh_replay_agree(tmp_path, capsys):
    assert cli.main(arguments(tmp_path)+['--replay']) == 0
    summary = json.loads((tmp_path/'out/summary.json').read_bytes())
    assert summary['status'] == 'completed'
    assert summary['fresh_replay']['numerical_reproduction_pass']
    assert summary['fresh_replay']['fresh_native_calls'] > 0
    assert all(arm['accepted_target_count'] == arm['requested_target_count'] == 3 for arm in summary['arms'].values())
    assert not summary['design_approval'] and not summary['independent_physical_validation']
    assert cli.main(['summary','--study',str(tmp_path/'out/study')]) == 0
    assert not (tmp_path/'out/.summary-writing').exists()


def test_cli_cannot_overwrite_output(tmp_path, capsys):
    args = arguments(tmp_path); (tmp_path/'out').mkdir(); (tmp_path/'out/keep').write_text('unchanged')
    assert cli.main(args) == 2
    assert (tmp_path/'out/keep').read_text() == 'unchanged'
    assert not (tmp_path/'out/started.json').exists()


@pytest.mark.parametrize('bad', ['', 'main', 'a'*39, 'A'*40])
def test_cli_source_label_rejected_before_output(tmp_path, capsys, bad):
    args = arguments(tmp_path); args[-1] = bad
    assert cli.main(args) == 2 and not (tmp_path/'out').exists()


def test_cli_bad_request_rejected_before_output(tmp_path, capsys):
    args = arguments(tmp_path); (tmp_path/'request.json').write_text('{"x":1,"x":2}')
    assert cli.main(args) == 2 and not (tmp_path/'out').exists()


def test_cli_failure_leaves_unknown_work_not_success(tmp_path, monkeypatch, capsys):
    args = arguments(tmp_path)
    def interrupted(*a, **k):
        raise RuntimeError('after output reservation')
    monkeypatch.setattr(cli, 'benchmark_rc_control_seed_paths', interrupted)
    assert cli.main(args) == 2
    summary = json.loads((tmp_path/'out/summary.json').read_bytes())
    assert summary['status'] == 'failed' and summary['unknown_execution_work']
    assert not summary['design_approval']


def test_unsupported_replay_scope_rejected_before_computation(tmp_path, monkeypatch, capsys):
    args = arguments(tmp_path)
    request = BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6, 1e-6), allow_reversals=True, maximum_reversals=2)
    (tmp_path/'request.json').write_text(json.dumps(request.to_dict()))
    monkeypatch.setattr(cli, 'benchmark_rc_control_seed_paths', lambda *a, **k: pytest.fail('unsupported replay computed'))
    assert cli.main(args+['--replay']) == 2
    assert not (tmp_path/'out').exists()


@pytest.fixture(scope='module')
def review_study(tmp_path_factory):
    from structural_analysis.benchmark.rc_control_recovery_execution import benchmark_rc_control_seed_paths
    from structural_analysis.benchmark.rc_control_recovery_strategy import RCControlRecoveryStrategy

    root = tmp_path_factory.mktemp('review-integrity')/'study'
    request = BoundedRCFiberDirectControlRequest(
        4, (-1e-6, -2e-6, 1e-6), allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -10., 0., 0.),),
    )
    benchmark_rc_control_seed_paths(
        model(), request, source_revision='a'*40, output_directory=root,
        recovery_strategy=RCControlRecoveryStrategy('adaptive-failed-target'),
    )
    return root


def _rewrite_report(root, report):
    from structural_analysis.benchmark.rc_control_design import _bytes, _sha

    body = {key: value for key, value in report.items() if key != 'report_hash'}
    report['report_hash'] = _sha(_bytes(body))
    (root/'comparison.json').write_bytes(_bytes(report))


@pytest.mark.parametrize('mutation', [
    'empty-comparisons', 'missing-comparison', 'empty-arms', 'missing-arm',
    'missing-path', 'changed-embedded-path', 'nonboolean-work', 'nonboolean-pass',
    'duplicate-arm-order', 'comparison-contradiction', 'request-mismatch',
])
def test_summary_rejects_inconsistent_metadata_even_after_rehash(
    tmp_path, review_study, mutation, capsys,
):
    import shutil

    root = tmp_path/'altered'
    shutil.copytree(review_study, root)
    report = json.loads((root/'comparison.json').read_bytes())
    if mutation == 'empty-comparisons':
        report['comparisons'] = {}
    elif mutation == 'missing-comparison':
        report['comparisons'].pop('proposal')
    elif mutation == 'empty-arms':
        report['arms'] = {}
    elif mutation == 'missing-arm':
        report['arms'].pop('proposal')
    elif mutation == 'missing-path':
        (root/'proposal/path.json').unlink()
    elif mutation == 'changed-embedded-path':
        report['arms']['proposal']['failure'] = {'kind': 'contradiction'}
    elif mutation == 'nonboolean-work':
        report['all_execution_work_reported'] = 'true'
    elif mutation == 'nonboolean-pass':
        report['comparisons']['proposal']['full_history_pass'] = 1
    elif mutation == 'duplicate-arm-order':
        report['arm_order'] = ['reference', 'reference', 'proposal']
    elif mutation == 'comparison-contradiction':
        report['comparisons']['proposal']['structure_match'] = False
    else:
        (root/'request.json').write_text('{}')
    _rewrite_report(root, report)
    with pytest.raises((ValueError, KeyError)):
        cli.summarize_rc_recovery_study(root)
    assert cli.main(['summary', '--study', str(root)]) == 2


def test_valid_review_keeps_declared_acceptance_separate_from_physics(review_study):
    result = cli.summarize_rc_recovery_study(review_study)
    assert result['declared_full_history_comparisons_pass']
    assert result['artifact_hashes_checked']
    assert not result['fresh_replay_executed_by_summary']
    assert not result['declared_counts_are_independently_audited']
    assert not result['independent_physical_validation'] and not result['design_approval']


def test_valid_failed_comparison_remains_readable(tmp_path, review_study):
    import shutil

    root = tmp_path/'failed-comparison'
    shutil.copytree(review_study, root)
    report = json.loads((root/'comparison.json').read_bytes())
    report['comparisons']['proposal']['full_history_pass'] = False
    report['comparisons']['proposal']['physical_values_within_tolerance'] = False
    _rewrite_report(root, report)
    assert not cli.summarize_rc_recovery_study(root)['declared_full_history_comparisons_pass']


@pytest.mark.parametrize('changed', [
    {'fresh_reference_comparisons_pass': False},
    {'unknown_replay_work': True},
    {'numerical_reproduction_pass': 1},
])
def test_run_cannot_promote_incomplete_fresh_audit(tmp_path, monkeypatch, changed, capsys):
    # Controlled audit result tests CLI admission, not fresh numerical accuracy.
    audit = dict(numerical_reproduction_pass=True, fresh_reference_comparisons_pass=True,
                 fresh_native_calls=1, fresh_known_newton_iterations=1,
                 unknown_replay_work=False, audit_hash='sha256:'+'a'*64)
    audit.update(changed)
    monkeypatch.setattr(cli, 'replay_rc_frozen_continuation_study', lambda *a, **k: audit)
    assert cli.main(arguments(tmp_path)+['--replay']) == 1
    summary = json.loads((tmp_path/'out/summary.json').read_bytes())
    assert summary['status'] == 'incomplete_or_unverified'
    assert not summary['design_approval']


@pytest.fixture(scope='module')
def damaged_native(tmp_path_factory):
    from structural_analysis.api import rc_fiber_frame_direct_control as api
    from structural_analysis.benchmark import fiber_frame_design as design
    from structural_analysis.benchmark.rc_control_recovery_execution import benchmark_rc_control_seed_paths
    from structural_analysis.benchmark.rc_control_recovery_strategy import RCControlRecoveryStrategy
    from structural_analysis.benchmark.rc_control_design import _bytes
    from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
        load_stateful_fiber_frame2d_checkpoint_bytes,
    )

    authored = design.apply_fiber_frame_section_changes(
        model(), design.FiberFrameDesignCandidate('history-witness', (
            design.FiberFrameSectionChange('RC1', width_m=.32,
                                          top_bar_area_m2=.0002, bottom_bar_area_m2=.00025),
        )),
    )
    request = BoundedRCFiberDirectControlRequest(
        4, (-.02, -.04, .02), allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -600., 0., 0.),),
    )
    root = tmp_path_factory.mktemp('accepted-damaged-history')/'study'
    report = benchmark_rc_control_seed_paths(
        authored, request, source_revision='a'*40, output_directory=root,
        recovery_strategy=RCControlRecoveryStrategy('adaptive-failed-target'),
    )
    assert report['arms']['reference']['accepted_target_count'] == 2
    assert report['arms']['reference']['status'] == 'incomplete'
    assert report['arms']['proposal']['status'] == 'complete'
    assert not report['comparisons']['proposal']['full_history_pass']
    compiled, blockers, _ = public._compile(authored)
    assert compiled is not None and not blockers
    compiled = api._with_constant_loading(compiled, request.constant_nodal_loads)
    step = json.loads((root/'reference/001-1-step.json').read_bytes())
    assert step['committed']
    parent = load_stateful_fiber_frame2d_checkpoint_bytes(_bytes(step['accepted_checkpoint']), compiled.problem)
    states = [state for element in parent.to_dict()['element_states']
              for point in element['integration_point_states'] for state in point['fiber_states']]
    assert max(state.get('tensile_damage', 0) for state in states) > .5
    assert max(state.get('accumulated_plastic_strain', 0) for state in states) > 0
    return compiled.problem, parent, request.solver_config, root


@pytest.mark.parametrize('target', [-.038, -.039999, .02])
def test_sampled_seed_on_actual_damage_and_plasticity_keeps_original_parent(damaged_native, target):
    problem, parent, config, root = damaged_native
    adapter = Adapter(problem, parent, 4, target, config)
    coordinates = adapter.initial_free_displacements_m()
    observation = adapter.observe(coordinates)
    direction = np.linalg.solve(observation.augmented_jacobian_kn_per_m,
                                -observation.augmented_residual_kn)
    before = parent.canonical_bytes()
    options = dict(control_global_dof=4, target_m=target, coordinates=coordinates,
                   direction=direction, config=config)
    first = candidate.run_rc_branch_sampled_seed(problem, parent, **options)
    second = candidate.run_rc_branch_sampled_seed(problem, parent, **options)
    assert _without_execution_clocks(first) == _without_execution_clocks(second)
    assert parent.canonical_bytes() == before
    assert first['native_accepted'] and first['native_core_calls_attempted'] == 1
    assert first['diagnostic_assembly_attempts'] == 18 and not first['unknown_work']
    assert first['native_step']['parent_checkpoint'] == parent.to_dict()
    assert first['native_step']['trial_solution']['metrics']['relative_residual'] <= config.newton.residual_tolerance
    assert not first['intermediate_material_checkpoints_adopted']
    assert not first['direction_construction_work_included']
    assert not first['full_history_verified'] and not first['original_80mm_witness_qualified']
    assert not first['independent_physical_validation'] and not first['design_approval']
    # Persist explicit direction construction separately from the candidate's budget.
    (root.parent/f'branch-witness-{target}.json').write_text(json.dumps({
        'direction_construction_assemblies': 1, 'direction_linear_solves': 1,
        'parent_hash': parent.state_hash, 'candidate': first,
        'scope': 'known small cantilever; not original 80mm witness or full-path speedup',
    }, allow_nan=False))
