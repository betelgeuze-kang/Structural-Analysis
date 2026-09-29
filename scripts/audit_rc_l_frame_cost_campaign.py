"""Verify the complete public L-frame process campaign without new solves."""
import argparse
import json
from pathlib import Path

from run_rc_cost_pruning_campaign import inspect_report, summarize_pair
from structural_analysis.benchmark.rc_control_design import _sha
from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes


def read(path):
    return strict_json_object_bytes(path.read_bytes(), maximum_bytes=2 * 1024 * 1024)


def audit(root):
    plan = read(root / 'plan.json')
    outcome = read(root / 'outcome.json')
    if (plan['orders'] != [['full', 'pruned'], ['pruned', 'full']] * 2
            or type(plan.get('planned_process_count')) is not int
            or plan['planned_process_count'] != 8
            or len(outcome['pairs']) != 4):
        raise ValueError('complete four-pair denominator required')
    if outcome.get('all_pairs_comparable') is not True:
        raise ValueError('successful campaign outcome required')
    for artifact in plan['inputs'].values():
        raw = (root / artifact['path']).read_bytes()
        if len(raw) != artifact['byte_length'] or _sha(raw) != artifact['sha256']:
            raise ValueError('original declared input changed')
    clocks = {'full': 0, 'pruned': 0}
    work = {mode: dict.fromkeys(('api_invocations', 'attempted_steps', 'newton', 'linear_solves'), 0)
            for mode in clocks}
    previous_results = {}
    pairs = []
    material_rows = None
    for repeat, order in enumerate(plan['orders']):
        reports = {mode: inspect_report(root / f'r{repeat}-{mode}') for mode in order}
        stored = read(root / f'pair-{repeat}.json')
        processes = {mode: read(root / f'r{repeat}-{mode}.process.json') for mode in order}
        rebuilt = summarize_pair(reports, processes)
        if rebuilt != stored or stored != outcome['pairs'][repeat] or not rebuilt['comparable']:
            raise ValueError('pair is incomplete, incomparable or changed')
        pairs.append(rebuilt)
        for mode, report in reports.items():
            if report['source_revision'] != plan['source_revision']:
                raise ValueError('exact source revision required')
            hashes = {r['candidate_id']: r['artifacts']['result']['sha256'] for r in report['rows'] if r['invocations']}
            if mode in previous_results and hashes != previous_results[mode]:
                raise ValueError('repeated result identities differ')
            previous_results[mode] = hashes
            clocks[mode] += processes[mode]['wall_ns']
            for row in report['rows']:
                for invocation in row['invocations']:
                    w = invocation['work']
                    if invocation['unknown_execution_work'] or w['unknown_solver_work_attempt_count']:
                        raise ValueError('unknown numerical work')
                    work[mode]['api_invocations'] += 1
                    work[mode]['attempted_steps'] += w['attempted_step_count']
                    work[mode]['newton'] += w['known_newton_iteration_count']
                    work[mode]['linear_solves'] += w['known_linear_solve_count']
            if mode == 'full' and material_rows is None:
                material_rows = [{k: row[k] for k in ('candidate_id', 'performance', 'quantities', 'material_estimate')}
                                 for row in report['rows']]
    return {'source_revision': plan['source_revision'], 'completed_processes': 8, 'pairs': pairs,
            'process_wall_ns_sums': clocks, 'pruned_over_full_ratio_of_sums': clocks['pruned'] / clocks['full'],
            'work_sums': work, 'full_model_observations': material_rows,
            'repeated_and_retained_result_hashes_match': True,
            'learned_speedup': False, 'independent_physical_validation': False,
            'scope': plan['scope'], 'synthetic_design_screens': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.study)
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ('pairs', 'full_model_observations')}))
