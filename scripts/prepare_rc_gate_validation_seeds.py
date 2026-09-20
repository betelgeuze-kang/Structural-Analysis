"""Fit the declared three-group-excluded seed policies; no label solves."""

import argparse
from pathlib import Path
import re
from time import perf_counter_ns

from plan_rc_gate_inner_validation import inner_validation_plan, require_fold_seed_exclusions
from prepare_rc_nested_switch_labels import fit_declared_seeds, require
from run_rc_pooled_runtime_campaign import inputs
from structural_analysis.benchmark.rc_control_design import _bytes, _save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-labels', 'new-labels', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_revision), 'exact source revision required')
    started = perf_counter_ns()
    _, samples, profile, groups, costs = inputs(args.old_labels, args.new_labels)
    plan = inner_validation_plan(groups, samples)
    require(len(samples) == 165 and plan['planned_new_seed_fits'] == 10
            and plan['planned_new_unique_parent_pairs'] == 990, 'fixed five-group protocol required')
    identities = {row['sample_hash']: row['case_id'] for row in samples}
    for fold in plan['gate_folds']:
        require_fold_seed_exclusions(plan, fold, identities)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes(dict(plan, source_revision=args.source_revision,
        historical_label_costs_separate=costs, source_sample_hashes=sorted(identities))))
    receipts = fit_declared_seeds(plan, samples, profile, root / 'seeds')
    require(len(receipts) == 10 and all(row['sample_count'] == 66 for row in receipts),
            'ten exact 66-row seed fits required')
    result = dict(source_revision=args.source_revision, completed_seed_fits=len(receipts),
        seed_fit_wall_ns=sum(row['wall_ns'] for row in receipts),
        wall_ns_before_result_write=perf_counter_ns() - started,
        new_gate_fits=0, new_solves=0, new_label_comparisons=0,
        reserved_evaluation=False, gate_validation_performed=False, promoted=False)
    _save(root, 'result.json', _bytes(result))
    print(result)


if __name__ == '__main__':
    main()
