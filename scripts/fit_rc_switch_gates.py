"""Fit five fixed gates from the pinned, completed nested development audit."""
import argparse
import json
from pathlib import Path
import re
from time import perf_counter_ns

from prepare_rc_nested_switch_labels import require
from run_rc_same_parent_seed_probe import reader
from run_rc_nested_switch_labels import SEED_PIN
from rc_switch_gate_training_rows import gate_training_rows
from rc_switch_gate import fit_gate, RIDGE, THRESHOLD
from structural_analysis.benchmark.rc_control_design import _bytes, _save

LABEL_PIN = '35fd7ed0e4552eb1a093bf1394e8bdcf5fbe694464761085c194a8f8ee88b4fb'


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
    status = original('stage-result.json')
    require(status['status'] == 'completed_and_audited'
            and original('audit-result.json')['exit_code'] == 0
            and original('execution-result.json')['exit_code'] == 0
            and audit['report_count'] == 1980 and len(audit['pairs']) == 660,
            'complete original nested campaign required')
    plan = reader(args.seeds, SEED_PIN)('nested-plan.json')
    require(len(plan['groups']) == 5, 'fixed five outer groups required')
    assemblies = [gate_training_rows(audit, plan, outer) for outer in range(5)]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'fit-plan.json', _bytes(dict(source_revision=args.source_revision,
        label_inventory=LABEL_PIN, seed_inventory=SEED_PIN, ridge=RIDGE, threshold=THRESHOLD,
        gate_count=5, reserved_evaluation=False, structural_solves=0,
        historical_label_costs_separate=original('execution-result.json'),
        historical_audit_costs_separate=original('audit-result.json'),
        historical_seed_costs_separate=original('study/plan.json')['historical_seed_costs_separate'])))
    receipts = []
    for training in assemblies:
        index = training['outer_group_index']
        _save(root, f'outer-{index}-training.json', _bytes(training))
        gate, receipt = fit_gate(training)
        _save(root, f'outer-{index}-gate.json', gate._json.encode())
        receipts.append(dict(outer_group_index=index, **receipt,
            positive_count=training['verified_positive_count'], negative_count=training['verified_negative_count']))
    result = dict(source_revision=args.source_revision, fits=receipts,
        wall_ns_before_result_write=perf_counter_ns()-started,
        structural_solves=0, reserved_evaluation=False, full_path_speedup_claim=False,
        independent_evaluation=False)
    _save(root, 'fit-result.json', _bytes(result))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
