"""Fixed synthetic L-frame recovery comparison; no policy or physical qualification.

Run from an immutable source snapshot. All native failures and unknown work remain
visible; successful orchestration is not successful structural validation.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re
from time import perf_counter_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

DECLARATIONS = tuple(
    (f'{geometry}-{millimetres}mm', length, height, millimetres / 1000)
    for geometry, length, height in (('short', 2., 1.5), ('long', 3., 2.5))
    for millimetres in (20, 40, 60, 80)
)


def prepare_cases():
    example = Path(__file__).resolve().parents[1] / 'examples/public_rc_fiber_frame_l_frame_material_history.json'
    template = json.loads(example.read_bytes())
    cases = []
    for name, length, height, amplitude in DECLARATIONS:
        payload = deepcopy(template)
        for node in payload['nodes']:
            if node['id'] == 'N2':
                node['coordinates'] = [length, 0., 0.]
            elif node['id'] == 'N3':
                node['coordinates'] = [length, height, 0.]
        model = load_neutral_json_bytes(_bytes(payload), source_path=f'memory://{name}.json')
        request = BoundedRCFiberDirectControlRequest(
            7, (-amplitude / 2, -amplitude, amplitude / 2),
            allow_reversals=True, maximum_reversals=2,
            constant_nodal_loads=(('N3', 0., -25., 0.),),
        )
        request = replace(request, solver_config=replace(
            request.solver_config, newton=replace(request.solver_config.newton, terminal_polishing=True),
        ))
        cases.append((name, model, request))
    return cases


def campaign_plan(source_revision, cases):
    if not isinstance(source_revision, str) or re.fullmatch('[0-9a-f]{40}', source_revision) is None:
        raise ValueError('exact caller source revision required')
    plan = {
        'schema_version': 'synthetic-adaptive-rc-recovery-campaign.v1',
        'source_revision': source_revision, 'source_revision_is_attestation': True,
        'cases': [{'case_id': name, 'model': model.canonical_payload(), 'request': request.to_dict()}
                  for name, model, request in cases],
        'arithmetic': 'binary64', 'terminal_polishing': True,
        'arm_orders': [['reference', 'secant', 'proposal'], ['proposal', 'secant', 'reference']],
        'mode_orders': [['fixed', 'adaptive'], ['adaptive', 'fixed']],
        'planned_comparisons': len(cases) * 4, 'planned_paths': len(cases) * 16,
        'maximum_native_calls_conservative': sum(4 * 4 * (1 + 2 * len(q.targets_m))
                                                + 2 * (16 + 64) * len(q.targets_m)
                                                for _, _, q in cases),
        'independent_project_provenance': False, 'training_or_policy_promotion': False,
        'parallel_timing_runs': False, 'tolerances_changed': False,
    }
    plan['plan_hash'] = _sha(_bytes(plan))
    return plan


def run_campaign(source_revision, output_directory):
    cases = prepare_cases()
    plan = campaign_plan(source_revision, cases)
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'campaign-plan.json', _bytes(plan))
    started = perf_counter_ns()
    rows = []
    for name, model, request in cases:
        for repeat, mode_order in enumerate(plan['mode_orders']):
            for mode in mode_order:
                identity = f'{name}-r{repeat}-{mode}'
                row = {'case_id': name, 'repeat': repeat, 'mode': mode,
                       'status': 'started', 'unknown_work': True}
                _save(root, identity + '-started.json', _bytes(row))
                try:
                    report = benchmark_rc_control_seed_paths(
                        model, request, source_revision=source_revision,
                        output_directory=root / identity,
                        arm_order=tuple(plan['arm_orders'][repeat]),
                        frozen_parent_continuation=True, continuation_on_failure=True,
                        continuation_all_failed_targets=True, continuation_adaptive=mode == 'adaptive',
                        record_assembly_work=True, record_assembly_timing=True,
                    )
                    arms = {**report['arms'], 'fresh-reference': report['fresh_reference']}
                    row.update(status='returned', report_hash=report['report_hash'],
                               unknown_work=not report['all_execution_work_reported'],
                               arm_statuses={key: arm['status'] for key, arm in arms.items()})
                except Exception as exc:
                    row.update(status='raised', error_type=type(exc).__name__, error=str(exc))
                rows.append(row)
                _save(root, identity + '-outcome.json', _bytes(row))
    outcome = {
        'schema_version': 'synthetic-adaptive-rc-recovery-outcome.v1',
        'plan_hash': plan['plan_hash'], 'rows': rows,
        'observations_complete': all(r['status'] == 'returned' and not r['unknown_work'] for r in rows),
        'completed_paths': sum(status == 'complete' for r in rows for status in r.get('arm_statuses', {}).values()),
        'parent_wall_ns_before_final_write': perf_counter_ns() - started,
        'qualified_speedup': False, 'independent_physical_validation': False,
        'policy_promoted': False,
    }
    outcome['outcome_hash'] = _sha(_bytes(outcome))
    _save(root, 'campaign-outcome.json', _bytes(outcome))
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output-directory', required=True, type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if args.preflight_only:
        plan = campaign_plan(args.source_revision, prepare_cases())
        print(json.dumps({'plan_hash': plan['plan_hash'], 'cases': len(plan['cases']),
                          'comparisons': plan['planned_comparisons'], 'paths': plan['planned_paths'],
                          'maximum_native_calls': plan['maximum_native_calls_conservative'], 'solver_calls': 0}))
        return
    result = run_campaign(args.source_revision, args.output_directory)
    print(json.dumps({'output_directory': str(args.output_directory),
                      'observations_complete': result['observations_complete'],
                      'completed_paths': result['completed_paths'], 'qualified_speedup': False}))
    if not result['observations_complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
