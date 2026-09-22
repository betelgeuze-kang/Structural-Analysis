"""Explicit local RC study/replay CLI; never merge, publish, or approve a design.

Run with ``python -m structural_analysis.benchmark.rc_recovery_cli --help``.
Only new local output directories are allowed. Source labels are attestations,
not authenticated provenance. Summary validates artifact hashes, not physics.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter_ns

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_continuation_replay import replay_rc_frozen_continuation_study
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_recovery_strategy import RCControlRecoveryStrategy
from structural_analysis.benchmark.rc_control_replay_files import ReplayStudyFiles
from structural_analysis.benchmark.rc_control_recovery_execution import benchmark_rc_control_seed_paths
from structural_analysis.io.neutral.loader import load_neutral_json

_MODES = ('frozen-reversal', 'frozen-failed-reversal', 'frozen-failed-target', 'adaptive-failed-target')


def summarize_rc_recovery_study(study):
    """Read all bounded artifacts; do not equate self-consistency with acceptance."""
    files = ReplayStudyFiles(Path(study))
    report = files['comparison.json']
    if report.get('schema_version') not in ('experimental-rc-control-seed-comparison.v1',
                                            'experimental-rc-control-seed-comparison.v2'):
        raise ValueError('supported seed-comparison report required')
    arms = {}
    for name, arm in [*report['arms'].items(), ('fresh-reference', report['fresh_reference'])]:
        count = arm['accepted_target_count']
        total = len(report['request']['targets_m'])
        if type(count) is not int or not 0 <= count <= total:
            raise ValueError('bounded integer accepted target count required')
        if arm['status'] not in ('complete', 'incomplete') or (arm['status'] == 'complete' and count != total):
            raise ValueError('inconsistent completion declaration')
        arms[name] = {
            'status': arm['status'], 'accepted_target_count': arm['accepted_target_count'],
            'requested_target_count': len(report['request']['targets_m']),
            'failure': arm.get('failure'),
        }
    files.verify_unchanged()
    return {
        'schema_version': 'rc-recovery-local-review.v1',
        'original_report_hash': report['report_hash'],
        'original_source_revision_attestation': report['source_revision'],
        'artifact_hashes_checked': True, 'artifact_count': len(files),
        'arms': arms, 'numerical_proposal_work': report['numerical_proposal_work'],
        'all_execution_work_reported': report['all_execution_work_reported'],
        'declared_full_history_comparisons_pass': all(
            c['full_history_pass'] is True for c in report['comparisons'].values()
        ),
        'fresh_replay_executed_by_summary': False,
        'declared_counts_are_independently_audited': False,
        'original_execution_clocks_authenticated': False,
        'independent_physical_validation': False, 'design_approval': False,
    }


def _write_summary(output, value):
    # The command owns this newly created directory; never replace prior output.
    value['summary_hash'] = _sha(_bytes(value))
    temporary = output / '.summary-writing'
    with temporary.open('xb') as stream:
        stream.write(_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output / 'summary.json')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    review = commands.add_parser('summary', help='read-only, bounded hash validation')
    review.add_argument('--study', type=Path, required=True)
    run = commands.add_parser('run', help='execute an opt-in original study; no approvals')
    run.add_argument('--model', type=Path, required=True)
    run.add_argument('--request', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--source-revision', required=True)
    run.add_argument('--strategy', choices=_MODES, required=True)
    run.add_argument('--replay', action='store_true', help='pay for a separate full numerical replay')
    args = parser.parse_args(argv)
    if args.command == 'summary':
        try:
            print(json.dumps(summarize_rc_recovery_study(args.study), ensure_ascii=False, indent=2))
            return 0
        except (ValueError, KeyError, OSError, TypeError) as exc:
            print(f'Summary rejected: {type(exc).__name__}: {exc}', file=sys.stderr)
            return 2
    output = None
    started = perf_counter_ns()
    try:
        if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
            raise ValueError('explicit forty-character source revision required')
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('output must be a new directory')
        model = load_neutral_json(args.model)
        with args.request.open('rb') as stream:
            raw = stream.read(128 * 1024 + 1)
        request = decode_bounded_rc_fiber_direct_control_request(
            strict_json_object_bytes(raw, maximum_bytes=128 * 1024)
        )
        if args.replay and not request.constant_nodal_loads:
            raise ValueError('fresh continuation replay requires the existing constant-load v2 profile')
        strategy = RCControlRecoveryStrategy(args.strategy)
        args.output.mkdir(parents=True, exist_ok=False)
        output = args.output.resolve()
        (output / 'started.json').write_bytes(_bytes({
            'status': 'started', 'source_revision_attestation': args.source_revision,
            'work_unknown_until_outcome': True,
        }))
        benchmark_rc_control_seed_paths(
            model, request, source_revision=args.source_revision,
            output_directory=output / 'study', recovery_strategy=strategy,
            record_assembly_work=True,
        )
        summary = summarize_rc_recovery_study(output / 'study')
        if args.replay:
            audit = replay_rc_frozen_continuation_study(
                output / 'study', model, request, output_directory=output / 'replay',
                replay_source_revision=args.source_revision,
            )
            summary['fresh_replay'] = {
                key: audit[key] for key in (
                    'numerical_reproduction_pass', 'fresh_reference_comparisons_pass',
                    'fresh_native_calls', 'fresh_known_newton_iterations', 'unknown_replay_work',
                    'audit_hash',
                )
            }
        passed = (summary['declared_full_history_comparisons_pass']
                  and summary['all_execution_work_reported'])
        if args.replay:
            passed = passed and summary['fresh_replay']['numerical_reproduction_pass']
        summary.update(status='completed' if passed else 'incomplete_or_unverified',
                       command_wall_ns=perf_counter_ns() - started)
        _write_summary(output, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    except (Exception, KeyboardInterrupt) as exc:
        if output is not None:
            failure = {
                'schema_version': 'rc-recovery-local-review.v1', 'status': 'failed',
                'error_type': type(exc).__name__, 'unknown_execution_work': True,
                'design_approval': False, 'independent_physical_validation': False,
                'command_wall_ns': perf_counter_ns() - started,
            }
            try:
                _write_summary(output, failure)
            except OSError:
                pass
        print(f'Execution stopped: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 2


if __name__ == '__main__':
    raise SystemExit(main())
