"""Run local RC cost searches, sharing verified physics across declared scenarios.

Repeat --experiment to rescreen/reprice in the SAME process. Existing experiment
and request formats are retained. The global new-model budget includes each
fresh model's original solve and full verification. No GPU or learned speedup
is claimed, and no cache is imported or persisted between invocations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.api.rc_fiber_frame_direct_control_request import decode_bounded_rc_fiber_direct_control_request
from structural_analysis.benchmark.fiber_frame_design_cli import read_design_experiment_with_material_history
from structural_analysis.benchmark.rc_control_cost_search import run_rc_control_cost_search
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.benchmark.rc_control_reuse import RCControlResultSession
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('model', 'request', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--experiment', required=True, type=Path, action='append')
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--scope-id', default='local-research')
    parser.add_argument('--max-new-model-analyses', type=int, default=17)
    args = parser.parse_args(argv)
    try:
        if not 1 <= len(args.experiment) <= 16:
            raise ValueError('one to sixteen experiment scenarios required')
        if not 0 <= args.max_new_model_analyses <= 17:
            raise ValueError('global new-model budget must be in [0, 17]')
        raw = _read(args.model, 16 * 1024 * 1024)
        strict_json_object_bytes(raw, maximum_bytes=16 * 1024 * 1024)
        model = load_neutral_json_bytes(raw, source_path=str(args.model))
        request = decode_bounded_rc_fiber_direct_control_request(_read(args.request, 128 * 1024))
        scenarios = [read_design_experiment_with_material_history(p) for p in args.experiment]
        if any(prices is None for _, prices, _, _, _ in scenarios):
            raise ValueError('each scenario needs explicit prices')
        session = RCControlResultSession(source_revision=args.source_revision, scope_id=args.scope_id)
        args.output.mkdir(parents=True, exist_ok=False)
        remaining = args.max_new_model_analyses
        summaries = []
        for index, (candidates, prices, terminal, history, material) in enumerate(scenarios):
            report = run_rc_control_cost_search(
                model, candidates, request, session=session, scope_id=args.scope_id,
                prices=prices, terminal_limits=terminal, history_limits=history,
                material_limits=material, output_directory=args.output / f'scenario-{index:03d}',
                max_new_model_analyses=remaining)
            remaining -= report['new_model_evaluations']
            summaries.append({key: report[key] for key in (
                'status', 'report_hash', 'cost_bound', 'new_model_evaluations',
                'reused_model_evaluations', 'new_work')})
            if report['new_work']['unknown_work']:
                break
        summary = {'schema_version': 'local-rc-cost-search-batch.v1',
                   'requested_scenario_count': len(scenarios), 'scenarios': summaries,
                   'remaining_new_model_budget': remaining,
                   'persistent_cache': False, 'performance_improvement': False}
        summary['report_hash'] = _sha(_bytes(summary))
        _save(args.output, 'batch.json', _bytes(summary))
        print(json.dumps(summary, allow_nan=False, sort_keys=True))
        return 0 if len(summaries) == len(scenarios) and all(
            r['status'] == 'pool_minimum_confirmed' for r in summaries) else 2
    except (ValueError, OSError) as error:
        print(f'local RC search failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
