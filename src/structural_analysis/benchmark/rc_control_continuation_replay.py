"""Fresh numerical replay of experimental continuation files, not external V&V."""

import hashlib
import platform

import numpy as np
from pathlib import Path
import sys
from time import perf_counter_ns

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.benchmark.rc_control_frozen_continuation import (
    FROZEN_CONTINUATION_IDENTITY, FROZEN_CONTINUATION_FAILURE_IDENTITY,
    FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY, ADAPTIVE_FROZEN_CONTINUATION_IDENTITY,
)
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths


def _read_study(root):
    result = {}
    paths = sorted(root.rglob('*.json'))
    if len(paths) > 20000 or sum(p.stat().st_size for p in paths) > 512 * 1024**2:
        raise ValueError('study replay byte/file budget exceeded')
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('local original artifact required')
        raw = path.read_bytes()
        value = strict_json_object_bytes(raw, maximum_bytes=256 * 1024**2)
        for key in ('report_hash', 'path_hash', 'step_hash'):
            if key in value:
                body = {k: v for k, v in value.items() if k != key}
                expected = canonical_hash(body) if key == 'step_hash' else _sha(_bytes(body))
                if value[key] != expected:
                    raise ValueError(f'original {key} mismatch: {path.name}')
        result[path.relative_to(root).as_posix()] = value
    return result


def _without_execution_clocks(value):
    if isinstance(value, list):
        return [_without_execution_clocks(v) for v in value]
    if isinstance(value, dict):
        return {k: _without_execution_clocks(v) for k, v in value.items()
                if k not in ('wall_ns', 'cpu_ns', 'report_hash', 'path_hash',
                             'source_path_hash', 'source_revision')
                and not k.endswith(('_wall_ns', '_cpu_ns'))}
    return value


def replay_rc_frozen_continuation_study(
    study, model, request, *, output_directory, replay_source_revision,
):
    """Regenerate every arm, proposal trial and original artifact from model input.

    Numerical content, work and filenames must match exactly. Execution clocks
    are measured afresh, never compared as deterministic results. Commit labels
    remain attestations; actual loaded module byte fingerprints are recorded.
    """
    started = perf_counter_ns()
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
    regenerated = _read_study(output / 'fresh')
    differences = sorted(set(originals) ^ set(regenerated))
    differences += [name for name in sorted(set(originals) & set(regenerated))
                    if _without_execution_clocks(originals[name]) != _without_execution_clocks(regenerated[name])]
    modules = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if name.startswith('structural_analysis.') and filename and filename.endswith('.py'):
            modules[name] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
    invocations = [i for arm in [*fresh['arms'].values(), fresh['fresh_reference']]
                   for i in [*arm.get('preload_invocations', []),
                             *[i for e in arm['entries'] for i in e['invocations']]]]
    additional = fresh['numerical_proposal_work']
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
        'fresh_native_calls': sum(i['work']['core_calls'] for i in invocations if i['work'])
        + additional['native_core_calls_attempted'],
        'fresh_known_newton_iterations': sum(i['work']['newton_iterations'] for i in invocations if i['work'])
        + additional['known_newton_iterations'],
        'unknown_replay_work': not fresh['all_execution_work_reported'],
        'fresh_reference_comparisons_pass': all(c['full_history_pass'] for c in fresh['comparisons'].values()),
        'independent_physical_validation': False, 'design_approval': False,
        'wall_ns': perf_counter_ns() - started,
    }
    outcome['numerical_reproduction_pass'] &= not outcome['unknown_replay_work']
    outcome['audit_hash'] = _sha(_bytes(outcome))
    (output / 'audit.json').write_bytes(_bytes(outcome))
    return outcome
