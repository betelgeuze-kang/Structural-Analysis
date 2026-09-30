"""One full nonlinear path check of an untrained always-declining guard."""
import argparse
import json
from pathlib import Path

from run_grouped_rc_history_coverage import cases_with_history_coverage
from run_grouped_rc_runtime_campaign import ARITHMETIC
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_material_features as material
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import benchmark_rc_control_seed_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    case = next(c for c in cases_with_history_coverage(extended_line_search=True)
                if c.case_id == 'train-b-amp150')
    counts = {'guard': 0, 'capture': 0, 'proposal': 0}
    original = material.committed_material_snapshot

    def capture(*values):
        counts['capture'] += 1
        return original(*values)

    def guard(context):
        assert context.committed_material_state_json is None
        counts['guard'] += 1
        return False

    def proposal(context):
        counts['proposal'] += 1
        raise AssertionError('declined proposal must not execute')

    material.committed_material_snapshot = capture
    try:
        report = benchmark_rc_control_seed_paths(case.model, case.request,
            source_revision=args.source_revision, output_directory=args.output,
            proposal=proposal, proposal_identity=_sha(_bytes({'kind': 'unused-proposal-sentinel'})),
            proposal_guard=guard, proposal_guard_identity=_sha(_bytes({'kind': 'always-decline-untrained'})),
            capture_material_state=True, material_capture_scope='proposal-only',
            proposal_abstention_strategy='secant', **learning._arithmetic_kwargs(ARITHMETIC))
    finally:
        material.committed_material_snapshot = original
    assert counts == {'guard': len(case.request.targets_m), 'capture': 0, 'proposal': 0}
    assert report['reference_repeat_exact'] and report['all_execution_work_reported']
    assert all(row['full_history_pass'] for row in report['comparisons'].values())
    def selected(directory):
        return {path.name: path.read_bytes() for path in directory.iterdir()
                if path.name.endswith(('-step.json', '-response.json', '-context.json'))
                and '-guard-' not in path.name}
    left, right = selected(args.output/'secant'), selected(args.output/'proposal')
    assert left == right and left
    entries = report['arms']['proposal']['entries']
    assert all(e['proposal_guard']['allow_proposal'] is False and 'committed_material_capture' not in e for e in entries)
    work = {key: sum(inv['work'][key] for arm in (*report['arms'].values(), report['fresh_reference'])
                    for inv in [*arm.get('preload_invocations', []),
                                *(inv for entry in arm['entries'] for inv in entry['invocations'])])
            for key in ('core_calls', 'newton_iterations', 'linear_solves')}
    result = {'case_id': case.case_id, 'source_revision': args.source_revision,
        'report_hash': report['report_hash'], 'counts': counts, 'exact_numerical_context_files': len(left),
        'work': work, 'guard_callback_wall_ns': sum(e['proposal_guard']['wall_ns'] for e in entries),
        'secant_path_wall_ns': report['arms']['secant']['wall_ns'],
        'guarded_path_wall_ns': report['arms']['proposal']['wall_ns'],
        'whole_study_wall_ns': report['whole_study_wall_ns'],
        'trained_guard': False, 'fits': 0, 'repetitions': 1,
        'independent_validation': False, 'speedup_claim': False}
    _save(args.output, 'guard-probe-result.json', _bytes(result))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
