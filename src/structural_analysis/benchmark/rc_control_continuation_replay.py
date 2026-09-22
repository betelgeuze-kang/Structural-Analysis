"""Fresh numerical replay of experimental continuation files, not external V&V."""

import hashlib
import platform
import os

import numpy as np
from pathlib import Path
import sys
from time import perf_counter_ns

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_frozen_continuation import (
    FROZEN_CONTINUATION_IDENTITY, FROZEN_CONTINUATION_FAILURE_IDENTITY,
    FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY, ADAPTIVE_FROZEN_CONTINUATION_IDENTITY,
)
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
from structural_analysis.benchmark.rc_control_replay_files import ReplayStudyFiles


def _read_study(root):
    return ReplayStudyFiles(root)


def _without_execution_clocks(value):
    if isinstance(value, list):
        return [_without_execution_clocks(v) for v in value]
    if isinstance(value, dict):
        return {k: _without_execution_clocks(v) for k, v in value.items()
                if k not in ('wall_ns', 'cpu_ns', 'report_hash', 'path_hash',
                             'source_path_hash', 'source_revision')
                and not k.endswith(('_wall_ns', '_cpu_ns'))}
    return value


def _same_without_execution_clocks(left, right):
    """Exactly the prior projection/equality rule, without recursive copies."""
    if isinstance(left, dict) and isinstance(right, dict):
        def keys(value):
            return {k for k in value
                    if k not in ('wall_ns', 'cpu_ns', 'report_hash', 'path_hash',
                                 'source_path_hash', 'source_revision')
                    and not k.endswith(('_wall_ns', '_cpu_ns'))}
        names = keys(left)
        return names == keys(right) and all(
            _same_without_execution_clocks(left[k], right[k]) for k in names
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same_without_execution_clocks(a, b) for a, b in zip(left, right)
        )
    return left == right


def _write_outcome(output, outcome):
    """Publish a complete audit atomically; never replace the original study."""
    temporary = output / '.audit-in-progress'
    with temporary.open('xb') as stream:
        stream.write(_bytes(outcome))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output / 'audit.json')


def _fresh_work(fresh):
    invocations = [i for arm in [*fresh['arms'].values(), fresh['fresh_reference']]
                   for i in [*arm.get('preload_invocations', []),
                             *[i for e in arm['entries'] for i in e['invocations']]]]
    additional = fresh['numerical_proposal_work']
    return {
        'fresh_native_calls': sum(i['work']['core_calls'] for i in invocations if i['work'])
        + additional['native_core_calls_attempted'],
        'fresh_known_newton_iterations': sum(i['work']['newton_iterations'] for i in invocations if i['work'])
        + additional['known_newton_iterations'],
        'unknown_replay_work': not fresh['all_execution_work_reported'],
    }


def replay_rc_frozen_continuation_study(
    study, model, request, *, output_directory, replay_source_revision,
):
    """Regenerate every arm, proposal trial and original artifact from model input.

    Numerical content, work and filenames must match exactly. Execution clocks
    are measured afresh, never compared as deterministic results. Commit labels
    remain attestations; actual loaded module byte fingerprints are recorded.
    """
    started = perf_counter_ns()
    if Path(study).is_symlink() or Path(output_directory).is_symlink():
        raise ValueError('separate local original and replay directories required')
    study, output = Path(study).resolve(), Path(output_directory).resolve()
    if output == study or output.is_relative_to(study) or study.is_relative_to(output):
        raise ValueError('separate original and replay directories required')
    originals = _read_study(study)
    report = originals['comparison.json']
    if (report.get('numerical_proposal', {}).get('identity') not in (FROZEN_CONTINUATION_IDENTITY, FROZEN_CONTINUATION_FAILURE_IDENTITY, FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY, ADAPTIVE_FROZEN_CONTINUATION_IDENTITY)
            or report['request'] != request.to_dict()
            or report['model_checksum'] != model.canonical_model_checksum
            or report['schema_version'] != 'experimental-rc-control-seed-comparison.v2'):
        raise ValueError('matching constant-load continuation model/request required')
    arithmetic_keys = (
        'coordinate_precision', 'strain_evaluation', 'material_arithmetic',
        'fiber_strain_evaluation', 'force_accumulation', 'terminal_coordinate_precision',
        'terminal_refinement_limit',
    )
    arithmetic = {k: report[k] for k in arithmetic_keys if k in report}
    if arithmetic:
        from structural_analysis.benchmark.rc_control_learning import (
            _arithmetic_kwargs, RETAINED_LEARNING_ARITHMETIC_PROFILE,
        )
        if arithmetic != _arithmetic_kwargs(RETAINED_LEARNING_ARITHMETIC_PROFILE):
            raise ValueError('original binary64 or complete retained arithmetic profile required')
    unsupported = ('capture_material_state', 'proposal_guard', 'initial_residual_observation',
                   'initial_parent_artifact', 'line_search_assembly_reuse')
    if any(key in report for key in unsupported):
        raise ValueError('original complete-path continuation profile required')
    for name in [*report['arm_order'], 'fresh-reference']:
        path = originals[name + '/path.json']
        phase = report.get('assembly_phase_work', {}).get(name)
        if phase is not None and phase['source_path_hash'] != path['path_hash']:
            raise ValueError('original phase/path binding mismatch')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'started.json').write_bytes(_bytes({
        'original_report_hash': report['report_hash'], 'replay_work_unknown_until_outcome': True,
    }))
    work = {'fresh_native_calls': None, 'fresh_known_newton_iterations': None,
            'unknown_replay_work': True}
    phase = 'fresh_execution'
    try:
        fresh = benchmark_rc_control_seed_paths(
            model, request, source_revision=replay_source_revision,
            output_directory=output / 'fresh', frozen_parent_continuation=True,
            continuation_on_failure=report['numerical_proposal']['identity'] in (FROZEN_CONTINUATION_FAILURE_IDENTITY, FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY, ADAPTIVE_FROZEN_CONTINUATION_IDENTITY),
            continuation_all_failed_targets=report['numerical_proposal']['identity'] in (FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY, ADAPTIVE_FROZEN_CONTINUATION_IDENTITY),
            continuation_adaptive=report['numerical_proposal']['identity'] == ADAPTIVE_FROZEN_CONTINUATION_IDENTITY,
            arm_order=tuple(report['arm_order']),
            absolute_tolerance=report['absolute_tolerance'], relative_tolerance=report['relative_tolerance'],
            record_assembly_work='assembly_work_recording' in report,
            record_assembly_timing=report.get('assembly_timing_recording', False),
            **arithmetic,
        )
        work = _fresh_work(fresh)
        phase = 'regenerated_artifacts'
        regenerated = _read_study(output / 'fresh')
        phase = 'artifact_comparison'
        differences = sorted(set(originals) ^ set(regenerated))
        for name in sorted(set(originals) & set(regenerated)):
            if not _same_without_execution_clocks(originals[name], regenerated[name]):
                differences.append(name)
        originals.verify_unchanged()
        regenerated.verify_unchanged()
        modules = {}
        for name, module in tuple(sys.modules.items()):
            filename = getattr(module, '__file__', None)
            if name.startswith('structural_analysis.') and filename and filename.endswith('.py'):
                modules[name] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        outcome = {
            'schema_version': 'rc-frozen-continuation-original-replay.v1',
            'original_report_hash': report['report_hash'], 'fresh_report_hash': fresh['report_hash'],
            'original_source_revision_attestation': report['source_revision'],
            'replay_source_revision_attestation': replay_source_revision,
            'loaded_source_sha256': modules, 'python_version': platform.python_version(),
            'numpy_version': np.__version__,
            'artifact_count': len(originals), 'mismatched_artifacts': differences,
            'numerical_reproduction_pass': not differences,
            'original_execution_clocks_authenticated': False,
            **work,
            'fresh_reference_comparisons_pass': all(c['full_history_pass'] for c in fresh['comparisons'].values()),
            'independent_physical_validation': False, 'design_approval': False,
            'wall_ns': perf_counter_ns() - started,
        }
        outcome['numerical_reproduction_pass'] &= not outcome['unknown_replay_work']
        outcome['audit_hash'] = _sha(_bytes(outcome))
        phase = 'audit_publication'
        _write_outcome(output, outcome)
        return outcome
    except BaseException as error:
        # Keep the primary exception behavior. The receipt is additional evidence,
        # not a successful audit or a claim that an interrupted solve cost zero.
        failed = {
            'schema_version': 'rc-frozen-continuation-original-replay.v1',
            'status': 'failed', 'phase': phase, 'error_type': type(error).__name__,
            'original_report_hash': report['report_hash'],
            'replay_source_revision_attestation': replay_source_revision,
            'numerical_reproduction_pass': False,
            'fresh_reference_comparisons_pass': False,
            'original_execution_clocks_authenticated': False,
            'independent_physical_validation': False, 'design_approval': False,
            **work, 'wall_ns': perf_counter_ns() - started,
        }
        failed['audit_hash'] = _sha(_bytes(failed))
        try:
            _write_outcome(output, failed)
        except Exception as publication_error:
            if hasattr(error, 'add_note'):
                error.add_note('Replay failure receipt could not be published: '
                               + type(publication_error).__name__)
        raise
