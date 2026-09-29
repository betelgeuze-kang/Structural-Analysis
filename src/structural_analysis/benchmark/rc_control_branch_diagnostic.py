"""Bounded, noncommitting branch observations on one native RC parent.

This is a binary64 diagnostic, not a new line search or an acceptance gate.
Equal sampled branch labels do not prove smoothness between the samples. No
initial value is selected and no intermediate material state is adopted.
"""
from __future__ import annotations

from time import perf_counter_ns

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    StatefulFiberFrame2DDisplacementControlStepAdapter,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import ConcreteDamageResponse
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityResponse
from structural_analysis.solvers.nonlinear.newton import _relative_residual_vector

MAX_BRANCH_SAMPLES = 65


def _vector(value, count, name):
    raw = np.asarray(value)
    if raw.dtype.kind not in 'iuf' or raw.shape != (count,):
        raise ValueError(f'{name} must be an explicit finite real vector')
    if isinstance(value, (tuple, list)) and any(isinstance(v, (bool, np.bool_)) for v in value):
        raise ValueError(f'{name} must not contain booleans')
    result = np.array(raw, dtype=np.float64, copy=True)
    if not np.all(np.isfinite(result)):
        raise ValueError(f'{name} must be finite')
    result.setflags(write=False)
    return result


def _fiber_rows(observation):
    rows = []
    for member in observation.frame_assembly.member_assemblies:
        for section_index, section in enumerate(member.response.section_responses):
            for fiber_index, fiber in enumerate(section.fiber_responses):
                if type(fiber) is ConcreteDamageResponse:
                    kind = 'concrete'
                    branch = [fiber.active_branch, fiber.damage_evolved]
                elif type(fiber) is UniaxialPlasticityResponse:
                    kind = 'steel'
                    branch = ['plastic' if fiber.yielded else 'elastic', fiber.yielded]
                else:
                    raise ValueError('supported native steel/concrete responses required')
                tangent = float(fiber.consistent_tangent_mpa)
                values = (float(fiber.total_strain), float(fiber.stress_mpa), tangent)
                if not all(np.isfinite(v) for v in values):
                    raise ValueError('finite native fiber diagnostics required')
                rows.append({
                    'member_id': member.member_id, 'section_index': section_index,
                    'fiber_index': fiber_index, 'kind': kind,
                    'branch': branch, 'tangent_sign': int(np.sign(tangent)),
                    'total_strain': values[0], 'stress_mpa': values[1],
                    'consistent_tangent_mpa': tangent,
                    'committed_state_hash': fiber.committed_state_hash,
                })
    return rows


def _signature(row):
    return (row['kind'], tuple(row['branch']), row['tangent_sign'])


def observe_rc_control_branch_path(
    problem, parent, *, control_global_dof, target_m,
    coordinates, direction, fractions=(0.0, 0.25, 0.5, 0.75, 1.0), config=None,
):
    """Observe R(x+alpha*d), J*d and native branch labels on a fixed parent.

    All samples are prepared before assembly. On a native exception, preserve
    completed rows, mark the interrupted attempt unknown, and stop. No Newton
    solve, fit, candidate selection, or checkpoint commitment is performed.
    """
    started = perf_counter_ns()
    if problem.coordinate_precision != 'binary64':
        raise ValueError('branch diagnostic currently requires binary64 coordinates')
    if type(fractions) is not tuple or not 2 <= len(fractions) <= MAX_BRANCH_SAMPLES:
        raise ValueError('two to 65 explicit sample fractions required')
    if any(type(v) not in (int, float) or not np.isfinite(v) or not 0 <= v <= 1 for v in fractions):
        raise ValueError('finite numeric fractions in [0,1] required')
    if fractions[0] != 0 or any(a >= b for a, b in zip(fractions, fractions[1:])):
        raise ValueError('strictly increasing fractions starting at zero required')
    count = len(problem.free_global_dofs) + 1
    origin = _vector(coordinates, count, 'coordinates')
    step = _vector(direction, count, 'direction')
    if not np.any(step):
        raise ValueError('nonzero diagnostic direction required')
    cfg = config if config is not None else StatefulFiberFrame2DDisplacementControlConfig()
    before = parent.canonical_bytes()
    rows, adapters = [], []
    for fraction in fractions:
        with np.errstate(over='raise', invalid='raise'):
            try:
                sample = origin + float(fraction) * step
            except FloatingPointError as exc:
                raise ValueError('finite sample coordinates required') from exc
        adapters.append(StatefulFiberFrame2DDisplacementControlStepAdapter(
            problem, parent, control_global_dof, target_m, cfg, tuple(sample),
        ))
    binding = {
        'problem_contract_hash': problem.contract_hash, 'parent_hash': parent.state_hash,
        'control_global_dof': control_global_dof, 'target_m': float(target_m),
        'coordinates': origin.tolist(), 'direction': step.tolist(),
        'fractions': [float(v) for v in fractions], 'solver_config': cfg.to_manifest(),
    }
    base_residual = base_directional = None
    base_fibers = None
    for index, (fraction, adapter) in enumerate(zip(fractions, adapters)):
        tick = perf_counter_ns()
        row = {'fraction': float(fraction), 'status': 'failed',
               'assembly_attempts': 1, 'unknown_work': True}
        try:
            observation = adapter.observe(adapter.initial_free_displacements_m())
            fibers = _fiber_rows(observation)
            residual = observation.augmented_residual_kn
            tangent_direction = observation.augmented_jacobian_kn_per_m @ step
            if index == 0:
                base_residual = residual.copy()
                base_directional = tangent_direction.copy()
                base_fibers = fibers
            if len(fibers) != len(base_fibers):
                raise ValueError('native fiber roster changed during observation')
            changes = []
            for old, current in zip(base_fibers, fibers):
                keys = ('member_id', 'section_index', 'fiber_index', 'kind', 'committed_state_hash')
                if any(old[key] != current[key] for key in keys):
                    raise ValueError('native fiber/parent binding changed')
                if _signature(old) != _signature(current):
                    changes.append({key: current[key] for key in keys[:4]})
            increment = residual - base_residual
            linear = float(fraction) * base_directional
            relative = float(_relative_residual_vector(adapter, residual))
            remainder = float(np.linalg.norm(increment - linear))
            if (not np.all(np.isfinite(residual))
                    or not np.all(np.isfinite(tangent_direction))
                    or not np.all(np.isfinite(increment))
                    or not np.all(np.isfinite(linear))
                    or not np.isfinite(relative) or not np.isfinite(remainder)
                    or not np.isfinite(observation.control_error_m)):
                raise ValueError('nonfinite computed diagnostic values')
            row.update(
                status='observed', unknown_work=False, fibers=fibers,
                residual_kn=residual.tolist(),
                relative_residual=relative,
                jacobian_times_direction_kn=tangent_direction.tolist(),
                residual_increment_kn=increment.tolist(),
                baseline_linear_prediction_kn=linear.tolist(),
                linearization_remainder_norm_kn=remainder,
                changed_sampled_branches=changes,
                control_error_m=float(observation.control_error_m),
            )
        except Exception as exc:
            row.update(error_type=type(exc).__name__)
        finally:
            row['wall_ns'] = perf_counter_ns() - tick
            if parent.canonical_bytes() != before:
                raise RuntimeError('branch diagnostic mutated original parent')
        rows.append(row)
        if row['unknown_work']:
            break
    return {
        'schema_version': 'rc-control-branch-path-observation.v1',
        'input_binding': binding, 'input_hash': canonical_hash(binding),
        'rows': rows, 'requested_samples': len(fractions),
        'assembly_attempts': len(rows), 'unknown_work': any(r['unknown_work'] for r in rows),
        'complete': len(rows) == len(fractions) and all(r['status'] == 'observed' for r in rows),
        'parent_unchanged': True, 'newton_solves': 0, 'committed': False,
        'candidate_selected': False, 'qualification_claim': False,
        'sample_labels_prove_interval_smoothness': False,
        'wall_ns': perf_counter_ns() - started,
    }
