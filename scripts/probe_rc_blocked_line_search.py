"""Replay two retained blocked steps from identical native parents; no fitting.

This post-hoc diagnostic does not qualify a complete path or alter defaults.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _save
from structural_analysis.benchmark.rc_control_learning import _arithmetic_kwargs
from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext, benchmark_rc_control_seed_paths,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

INVENTORY_SHA256 = 'cffefc0082c58e75d07f6e7df712bea1e8eaab9b66ceb368990fd00b633e4f70'
CASES = (('train-a-amp050', 6), ('train-a-amp150', 2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    raw = (args.bundle / 'inventory.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA256:
        raise ValueError('original inventory identity changed')
    index = {r['path']: r for r in json.loads(raw)['files']}

    def original(name):
        data = (args.bundle / name).read_bytes()
        identity = index[name]
        if len(data) != identity['byte_length'] or hashlib.sha256(data).hexdigest() != identity['sha256']:
            raise ValueError(f'original artifact changed: {name}')
        return json.loads(data)

    campaign = original('study/coverage-plan.json')
    prepared = []
    for name, target_index in CASES:
        row = next(c for c in campaign['cases'] if c['case_id'] == name)
        model = load_neutral_json_bytes(_bytes(row['model']), source_path=f'memory://{name}.json')
        request = decode_bounded_rc_fiber_direct_control_request(_bytes(row['request']))
        stem = f'study/labels/{name}/generation/reference/{target_index:03d}'
        step = original(stem + '-1-step.json')
        if step['committed'] or step['metrics']['terminal_reason'] != 'line_search_failed_to_reduce_residual':
            raise ValueError('expected original blocked line-search step')
        context = RCControlSeedContext(**original(stem + '-context.json'))
        prepared.append((name, model, request, _bytes(step['parent_checkpoint']), context))
    root = args.output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes({
        'source_revision': args.source_revision, 'original_inventory_sha256': INVENTORY_SHA256,
        'scope': 'posthoc_single_step_from_identical_retained_parent',
        'cases': list(CASES), 'alphas': [2.0 ** -i for i in range(13)],
        'changed_setting': 'line_search_alphas_only', 'maximum_iterations_unchanged': True,
        'tolerances_unchanged': True, 'complete_path_claim': False,
    }))
    records = []
    started = perf_counter_ns()
    for name, model, request, parent, context in prepared:
        for profile in ('original', 'extended'):
            changed = request if profile == 'original' else replace(request, solver_config=replace(
                request.solver_config, newton=replace(request.solver_config.newton,
                    line_search_alphas=tuple(2.0 ** -i for i in range(13)))))
            report = benchmark_rc_control_seed_paths(
                model, changed, source_revision=args.source_revision,
                output_directory=root / f'{name}-{profile}', arm_order=('reference', 'secant'),
                parent_checkpoint_bytes=parent, accepted_context=context,
                **_arithmetic_kwargs('retained-twofold-refinement.v1'),
            )
            records.append({'case_id': name, 'profile': profile, 'report': report})
    _save(root, 'outcome.json', _bytes({'records': records,
        'wall_ns_before_outcome_write': perf_counter_ns() - started,
        'complete_path_claim': False, 'policy_fit_performed': False}))
    print(json.dumps({'reports': len(records), 'root': str(root)}))


if __name__ == '__main__':
    main()
