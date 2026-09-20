"""Fit fixed cost-margin development gates from retained audited nested labels."""

import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

from fit_rc_switch_gates import LABEL_PIN, SEED_PIN
from prepare_rc_nested_switch_labels import require
from rc_cost_margin_gate import TARGET_PROFILE, CostMarginGate, cost_training_rows, fit_cost_gate
from run_rc_same_parent_seed_probe import reader
from structural_analysis.benchmark.rc_control_design import _bytes, _save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('labels', 'seeds', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_revision), 'exact source revision required')
    started = perf_counter_ns()
    original = reader(args.labels, LABEL_PIN)
    audit = original('audit.json')
    require(original('stage-result.json')['status'] == 'completed_and_audited'
            and original('audit-result.json')['exit_code'] == 0
            and original('execution-result.json')['exit_code'] == 0
            and audit['report_count'] == 1980 and len(audit['pairs']) == 660,
            'complete original nested campaign required')
    plan = reader(args.seeds, SEED_PIN)('nested-plan.json')
    require(len(plan['groups']) == 5, 'fixed five outer groups required')
    assemblies = [cost_training_rows(audit, plan, outer) for outer in range(5)]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'fit-plan.json', _bytes(dict(source_revision=args.source_revision,
        label_inventory=LABEL_PIN, seed_inventory=SEED_PIN, target_profile=TARGET_PROFILE,
        ridge=CostMarginGate._ridge, threshold=CostMarginGate._threshold,
        gate_count=5, reserved_evaluation=False, structural_solves=0,
        historical_label_costs_separate=original('execution-result.json'),
        historical_audit_costs_separate=original('audit-result.json'),
        historical_seed_costs_separate=original('study/plan.json')['historical_seed_costs_separate'])))
    receipts = []
    for training in assemblies:
        index = training['outer_group_index']
        _save(root, f'outer-{index}-training.json', _bytes(training))
        gate, receipt = fit_cost_gate(training)
        _save(root, f'outer-{index}-gate.json', gate._json.encode())
        decisions = [gate.decision(dict(profile=training['feature_profile'],
            feature_names=training['feature_names'], values=row['values']))
            for row in training['training_rows']]
        receipts.append(dict(outer_group_index=index, **receipt,
            training_proposal_count=sum(decisions),
            training_true_positive=sum(d and row['label'] for d, row in
                                       zip(decisions, training['training_rows'], strict=True)),
            training_false_positive=sum(d and not row['label'] for d, row in
                                        zip(decisions, training['training_rows'], strict=True)),
            positive_count=training['verified_positive_count'],
            negative_count=training['verified_negative_count']))
    result = dict(source_revision=args.source_revision, fits=receipts,
        wall_ns_before_result_write=perf_counter_ns()-started,
        all_training_decisions_decline=all(row['training_proposal_count'] == 0 for row in receipts),
        structural_solves=0, reserved_evaluation=False, full_path_speedup_claim=False,
        independent_evaluation=False, full_path_evaluation_performed=False)
    _save(root, 'fit-result.json', _bytes(result))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
