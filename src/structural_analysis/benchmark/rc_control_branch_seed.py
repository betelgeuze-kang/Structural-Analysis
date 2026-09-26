"""Experimental fixed-parent, branch-sampled seeds; native Newton alone accepts.

This opt-in diagnostic candidate is not installed as a production recovery
strategy. Sampling a lower residual does not prove smoothness, convergence,
physical branch selection, or an advantage over the existing continuation.
"""
from __future__ import annotations

from time import perf_counter_ns

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    solve_stateful_fiber_frame2d_displacement_control_step,
)
from structural_analysis.benchmark.rc_control_branch_diagnostic import (
    observe_rc_control_branch_path,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.assembly_work import VectorAssemblyWorkRecorder

# Fixed predeclared grid. No changes based on observed experimental outcomes.
DEFAULT_BRANCH_FRACTIONS = (0.0,) + tuple(2.0**-i for i in range(16, -1, -1))


def run_rc_branch_sampled_seed(
    problem, parent, *, control_global_dof, target_m, coordinates, direction,
    fractions=DEFAULT_BRANCH_FRACTIONS, config=None,
):
    """Observe one direction and confirm at most one candidate with native gates.

    The user-supplied direction is not credited as free Newton work; constructing
    it is outside this function's scope. Equal-residual candidates prefer fewer
    sampled branch changes, then the smaller fraction. No completed sample is
    used after an interrupted diagnostic. Intermediate material states are never
    adopted; the returned native step is the only possible accepted transition.
    """
    started = perf_counter_ns()
    cfg = config if config is not None else StatefulFiberFrame2DDisplacementControlConfig()
    before = parent.canonical_bytes()
    diagnostic = observe_rc_control_branch_path(
        problem, parent, control_global_dof=control_global_dof, target_m=target_m,
        coordinates=coordinates, direction=direction, fractions=fractions, config=cfg,
    )
    report = {
        'schema_version': 'experimental-rc-branch-sampled-seed.v1',
        'status': 'blocked', 'diagnostic': diagnostic,
        'input_hash': diagnostic['input_hash'], 'parent_hash': parent.state_hash,
        'seed': None, 'selected_fraction': None, 'native_step': None,
        'diagnostic_assembly_attempts': diagnostic['assembly_attempts'],
        'native_core_calls_attempted': 0, 'known_newton_iterations': 0,
        'known_linear_solves': 0, 'unknown_work': diagnostic['unknown_work'],
        'native_accepted': False, 'candidate_confers_acceptance': False,
        'intermediate_material_checkpoints_adopted': False,
        'original_80mm_witness_qualified': False,
        'full_history_verified': False, 'independent_physical_validation': False,
        'design_approval': False, 'direction_construction_work_included': False,
    }
    recorder = VectorAssemblyWorkRecorder(record_wall_time=True)
    phase = 'candidate_selection'
    try:
        if not diagnostic['complete'] or diagnostic['unknown_work']:
            report['reason'] = 'incomplete_diagnostic'
        else:
            baseline = diagnostic['rows'][0]['relative_residual']
            eligible = [row for row in diagnostic['rows'][1:]
                        if row['relative_residual'] < baseline]
            if not eligible:
                report.update(status='abstained', reason='no_strict_residual_descent')
            else:
                chosen = min(eligible, key=lambda row: (
                    row['relative_residual'], len(row['changed_sampled_branches']),
                    row['fraction'],
                ))
                binding = diagnostic['input_binding']
                seed = (np.asarray(binding['coordinates'], dtype=float)
                        + chosen['fraction'] * np.asarray(binding['direction'], dtype=float))
                if not np.all(np.isfinite(seed)):
                    raise ValueError('nonfinite candidate')
                report.update(seed=seed.tolist(), selected_fraction=chosen['fraction'],
                              selected_branch_changes=chosen['changed_sampled_branches'],
                              selected_relative_residual=chosen['relative_residual'])
                phase = 'native_confirmation'
                report['native_core_calls_attempted'] = 1
                step = solve_stateful_fiber_frame2d_displacement_control_step(
                    problem, parent, control_global_dof=control_global_dof,
                    target_control_displacement_m=target_m, config=cfg,
                    initial_augmented_coordinates_m=tuple(seed), assembly_work=recorder,
                )
                metrics = step.trial_solution.metrics
                report.update(
                    status='native_accepted' if step.committed else 'native_rejected',
                    native_step=step.to_dict(), native_accepted=step.committed,
                    known_newton_iterations=metrics['newton_iteration_count'],
                    known_linear_solves=metrics['linear_solve_count'],
                )
    except Exception as exc:
        report.update(status='failed', phase=phase, error_type=type(exc).__name__,
                      unknown_work=True, native_accepted=False)
    finally:
        if parent.canonical_bytes() != before:
            raise RuntimeError('branch-sampled seed mutated original parent')
        report.update(parent_unchanged=True, native_assembly_work=recorder.to_dict(),
                      wall_ns=perf_counter_ns() - started)
    report['report_hash'] = canonical_hash(report)
    return report
