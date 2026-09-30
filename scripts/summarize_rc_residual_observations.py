"""Summarize audited same-parent residual observations without fitting or solves."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from audit_grouped_rc_runtime_campaign import checked, require
from audit_rc_pooled_runtime_campaign import audit, require_observations


def rows_from_report(report, fold):
    require_observations(report, True)
    rows = []
    for entry in report['arms']['proposal']['entries']:
        observation = entry.get('initial_residual_observation')
        if observation is None:
            continue
        baseline, proposal = observation['rows']
        a, b = baseline['relative_residual'], proposal['relative_residual']
        ratio = b / a if a > 0 else None
        if ratio is not None and not math.isfinite(ratio):
            ratio = None
        rows.append({
            'case_id': fold['withheld_training_case'], 'ridge': fold['ridge'],
            'repetition_index': fold['repetition_index'], 'target_index': entry['target_index'],
            'parent_hash': entry['parent_hash'], 'comparison_hash': report['report_hash'],
            'secant_relative_residual': a, 'proposal_relative_residual': b,
            'proposal_over_secant_residual_ratio': ratio,
            'residual_order': 'lower' if b < a else 'higher' if b > a else 'equal',
            'secant_gate_passed': baseline['residual_gate_passed'],
            'proposal_gate_passed': proposal['residual_gate_passed'],
            'observation_wall_ns': entry['initial_residual_observation_wall_ns'],
            'observation_assembly_attempts': sum(r['assembly_attempts'] for r in observation['rows']),
        })
    return rows


def summarize_rows(rows):
    identity = [(r['case_id'], r['ridge'], r['repetition_index'], r['target_index']) for r in rows]
    require(len(identity) == len(set(identity)), 'duplicate residual observation identity')
    counts = Counter(r['residual_order'] for r in rows)
    return {
        'observations': len(rows),
        'unique_case_target_pairs': len({(r['case_id'], r['target_index']) for r in rows}),
        'unique_case_target_ridge_pairs': len({(r['case_id'], r['target_index'], r['ridge']) for r in rows}),
        'lower': counts['lower'], 'equal': counts['equal'], 'higher': counts['higher'],
        'secant_pass_proposal_fail': sum(r['secant_gate_passed'] and not r['proposal_gate_passed'] for r in rows),
        'proposal_pass_secant_fail': sum(r['proposal_gate_passed'] and not r['secant_gate_passed'] for r in rows),
        'observation_wall_ns': sum(r['observation_wall_ns'] for r in rows),
        'observation_assembly_attempts': sum(r['observation_assembly_attempts'] for r in rows),
    }


def diagnose(study, old_labels, new_labels):
    receipt = audit(study, old_labels, new_labels)
    result = checked(study / 'selection/result.json', 'result_hash')
    require(result.get('observe_initial_residuals') is True, 'observational campaign required')
    rows = []
    for fold in result['folds']:
        report = checked(study / f"selection/fold-{fold['index']:04d}/comparison.json", 'report_hash')
        rows.extend(rows_from_report(report, fold))
    totals = summarize_rows(rows)
    require(totals['observation_assembly_attempts'] == receipt['observation_assembly_attempts']
            and totals['observation_wall_ns'] == receipt['observation_wall_ns'],
            'observation summary differs from audited work')
    return {
        'schema_version': 'rc-control-residual-campaign-diagnostic.v1',
        'source_revision': receipt['source_revision'],
        'selection_result_hash': receipt['selection_result_hash'],
        'audit': receipt, 'totals': totals,
        'by_ridge': {str(ridge): summarize_rows([r for r in rows if r['ridge'] == ridge])
                     for ridge in sorted({r['ridge'] for r in rows})},
        'rows': rows, 'diagnostic_solver_calls': 0, 'diagnostic_fits': 0,
        'repeated_rows_are_independent_cases': False,
        'observational_history': 'proposal-arm accepted history only',
        'residual_improvement_proves_speedup': False,
        'independent_physical_validation': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('old_labels', type=Path)
    parser.add_argument('new_labels', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = diagnose(args.study, args.old_labels, args.new_labels)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(result['totals'])
