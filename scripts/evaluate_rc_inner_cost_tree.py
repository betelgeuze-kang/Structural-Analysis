"""Post-hoc fixed prefix-tree development comparison; never auto-promote."""

import argparse
from pathlib import Path
import re
from time import perf_counter_ns

from evaluate_rc_inner_gate_variants import inputs
from prepare_rc_nested_switch_labels import require
from rc_offline_cost_tree import MAX_DEPTH, MIN_LEAF, THRESHOLD, fit_cost_tree
from score_rc_gate_validation import score_gate
from structural_analysis.benchmark.rc_control_design import _bytes, _save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('new-labels', 'old-labels', 'seeds', 'old-seeds', 'summaries', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--new-labels-inventory', required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_revision), 'exact source revision required')
    started = perf_counter_ns()
    folds = inputs(args.new_labels, args.new_labels_inventory, args.old_labels,
                   args.seeds, args.old_seeds, args.summaries)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'plan.json', _bytes(dict(source_revision=args.source_revision,
        new_label_inventory=args.new_labels_inventory, folds=20, maximum_gate_fits=20,
        feature_variant='prefix_only', maximum_depth=MAX_DEPTH, minimum_leaf_rows=MIN_LEAF,
        threshold=THRESHOLD, posthoc_model_family=True, parameter_search=False,
        reserved_evaluation=False, full_path_evaluation=False, new_solves=0)))
    records = []
    for prefix, _material in folds:
        training, validation = prefix['training'], prefix['validation']
        name = f"outer-{training['outer_group_index']}-validation-{training['validation_group_index']}-prefix-tree"
        _save(root, name+'-training.json', _bytes(training))
        _save(root, name+'-validation.json', _bytes(validation))
        if not training['training_rows']:
            record = dict(name=name, fitted=False, status='no_verified_training_rows',
                          validation_rows=validation['declared_row_count'], promoted=False)
        else:
            gate, receipt = fit_cost_tree(training)
            _save(root, name+'-policy.json', gate._json.encode())
            score = score_gate(gate, validation)
            _save(root, name+'-score.json', _bytes(score))
            record = dict(name=name, fitted=True, status='scored', fit=receipt,
                          counts=score['counts'], promoted=False)
        _save(root, name+'-result.json', _bytes(record))
        records.append(record)
    result = dict(records=records, new_gate_fits=sum(r['fitted'] for r in records), new_solves=0,
        wall_ns_before_result_write=perf_counter_ns()-started, posthoc_model_family=True,
        parameter_search=False, reserved_evaluation=False, winner_selected=False,
        promoted=False, full_path_speedup_claim=False)
    _save(root, 'result.json', _bytes(result))
    print(dict(completed_folds=len(records), new_gate_fits=result['new_gate_fits']))


if __name__ == '__main__':
    main()
