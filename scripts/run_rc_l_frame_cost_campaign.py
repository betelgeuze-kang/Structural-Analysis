"""Predeclared repeated public-CLI design/pruning check on a nonlinear L frame."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter_ns

from run_grouped_rc_runtime_campaign import prepare_cases
from run_rc_cost_pruning_campaign import inspect_report, summarize_pair
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.rc_control_design import _bytes, _save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact frozen source revision required')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    case = prepare_cases()[0]
    request = replace(case.request, solver_config=replace(case.request.solver_config,
        newton=replace(case.request.solver_config.newton,
                       line_search_alphas=tuple(2.0 ** -i for i in range(13)))))
    candidates = [design.FiberFrameDesignCandidate(name, (design.FiberFrameSectionChange(
        'RC1', top_bar_area_m2=area, bottom_bar_area_m2=area),))
        for name, area in [('cheap', 0.00035), ('middle', 0.00040), ('costly', 0.00045)]]
    experiment = {'schema_version': 'rc-fiber-design-experiment.v3',
        'candidates': [c.to_dict() for c in candidates],
        'prices': asdict(design.FiberFrameMaterialPrices(100, 2, 'USD', '2026-09-20',
                                                      'synthetic L-frame study; not a quote')),
        'terminal_limits': None,
        'history_limits': asdict(design.FiberFrameHistoryLimits(0.1, 0.02)),
        'material_history_limits': asdict(design.FiberFrameMaterialHistoryLimits(0.05, 1, 1))}
    artifacts = {}
    for name, value in {'model': case.model.canonical_payload(), 'request': request.to_dict(),
                        'experiment': experiment}.items():
        artifacts[name] = _save(root, name + '.json', _bytes(value))
    orders = [['full', 'pruned'], ['pruned', 'full']] * 2
    _save(root, 'plan.json', _bytes({'source_revision': args.source_revision, 'inputs': artifacts,
        'orders': orders, 'case_id': 'known-l-frame-a', 'planned_process_count': 8,
        'public_cli_arithmetic': 'unchanged', 'retained_learning_arithmetic_used': False,
        'independent_geometry_or_project': False, 'newton_tolerances_changed': False,
        'synthetic_design_screens': True, 'material_regime_requires_observation': True,
        'scope': 'complete CLI process includes input, all analyses, fresh verification and output; preparation, audit and review excluded'}))
    records = []
    started = perf_counter_ns()
    for repeat, order in enumerate(orders):
        processes, reports = {}, {}
        for mode in order:
            folder = root / f'r{repeat}-{mode}'
            command = [sys.executable, '-m', 'structural_analysis.benchmark.rc_control_design_cli',
                '--source-revision', args.source_revision, '--output', str(folder)]
            for name in artifacts:
                command += ['--' + name, str(root / (name + '.json'))]
            if mode == 'pruned':
                command += ['--prune-cost-dominated']
            wall = perf_counter_ns()
            with (root / f'r{repeat}-{mode}.stdout').open('xb') as out, (root / f'r{repeat}-{mode}.stderr').open('xb') as err:
                completed = subprocess.run(command, stdout=out, stderr=err)
            process = {'return_code': completed.returncode, 'wall_ns': perf_counter_ns() - wall,
                       'arguments': command}
            processes[mode] = process
            _save(root, f'r{repeat}-{mode}.process.json', _bytes(process))
            try:
                reports[mode] = inspect_report(folder)
            except Exception as exc:
                process['audit_error'] = f'{type(exc).__name__}: {exc}'
        record = summarize_pair(reports, processes)
        records.append(record)
        _save(root, f'pair-{repeat}.json', _bytes(record))
        print(json.dumps({'repeat': repeat, 'comparable': record['comparable']}), flush=True)
    complete = len(records) == 4 and all(r['comparable'] for r in records)
    _save(root, 'outcome.json', _bytes({'pairs': records, 'all_pairs_comparable': complete,
        'measured_parent_wall_ns': perf_counter_ns() - started,
        'training_or_ai_used': False, 'independent_physical_validation': False}))
    raise SystemExit(0 if complete else 1)


if __name__ == '__main__':
    main()
