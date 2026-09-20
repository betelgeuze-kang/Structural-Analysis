"""Evaluate two fixed gate representations on complete audited inner folds."""

import argparse
from pathlib import Path
import re
from time import perf_counter_ns

from fit_rc_material_cost_gates import SUMMARY_PIN
from fit_rc_switch_gates import LABEL_PIN
from prepare_rc_nested_switch_labels import require
from rc_cost_margin_gate import fit_cost_gate
from rc_gate_validation_rows import assemble_fold, append_material_inputs
from rc_material_cost_gate import fit_material_gate
from run_rc_nested_switch_labels import INNER_CAMPAIGN, INNER_SEED_PIN, SEED_PIN
from run_rc_same_parent_seed_probe import reader
from score_rc_gate_validation import score_gate
from structural_analysis.benchmark.rc_control_design import _bytes, _save


def inputs(new_root, new_pin, old_root, seeds_root, old_seeds_root, summaries_root):
    require(type(new_pin) is str and re.fullmatch('[0-9a-f]{64}', new_pin),
            'complete new campaign inventory pin required')
    new = reader(new_root, new_pin)
    old = reader(old_root, LABEL_PIN)
    seeds, old_seeds = reader(seeds_root, INNER_SEED_PIN), reader(old_seeds_root, SEED_PIN)
    for read in (new, old):
        require(read('stage-result.json')['status'] == 'completed_and_audited'
                and read('execution-result.json')['exit_code'] == 0
                and read('audit-result.json')['exit_code'] == 0,
                'complete audited numerical campaign required')
    declaration = new('study/plan.json')
    require(declaration['campaign_profile'] == INNER_CAMPAIGN
            and declaration['source_inventories']['seeds'] == INNER_SEED_PIN,
            'original triple-excluded label source required')
    new_audit, old_audit = new('audit.json'), old('audit.json')
    require(new_audit['report_count'] == 2970 and old_audit['report_count'] == 1980
            and new_audit['source_revision'] == declaration['source_revision'],
            'complete new and retained comparison counts required')
    plan = seeds('study/plan.json')
    require(len(plan['gate_folds']) == 20, 'all twenty declared inner folds required')
    new_hashes = {row['fit_index']: row['policy_hash'] for row in seeds('study/seeds/fit-receipts.json')['fits']}
    old_hashes = {row['fit_index']: row['policy_hash'] for row in old_seeds('seed-fits/fit-receipts.json')['fits']}
    summaries = reader(summaries_root, SUMMARY_PIN)('audit/summaries.json')
    require(summaries['groups'] == plan['groups'], 'original material summary groups required')
    # Validate every fold before any output directory or fit is created.
    prepared = []
    for fold in plan['gate_folds']:
        tables = assemble_fold(new_audit, old_audit, plan,
            fold['outer_group_index'], fold['validation_group_index'],
            new_policy_hashes=new_hashes, old_policy_hashes=old_hashes)
        prepared.append((tables, append_material_inputs(tables, summaries)))
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('new-labels', 'old-labels', 'seeds', 'old-seeds', 'summaries', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
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
        new_label_inventory=args.new_labels_inventory, old_label_inventory=LABEL_PIN,
        new_seed_inventory=INNER_SEED_PIN, old_seed_inventory=SEED_PIN,
        summary_inventory=SUMMARY_PIN, variants=['prefix_cost', 'material_cost'],
        folds=20, maximum_gate_fits=40, ridge=1.0, threshold=.01,
        new_solves=0, reserved_evaluation=False, full_path_evaluation=False,
        hyperparameter_search=False)))
    records = []
    for pair in folds:
        for variant, tables, fit in zip(('prefix_cost', 'material_cost'), pair,
                                        (fit_cost_gate, fit_material_gate), strict=True):
            training, validation = tables['training'], tables['validation']
            name = f"outer-{training['outer_group_index']}-validation-{training['validation_group_index']}-{variant}"
            _save(root, name + '-training.json', _bytes(training))
            _save(root, name + '-validation.json', _bytes(validation))
            if not training['training_rows']:
                record = dict(name=name, status='no_verified_training_rows', fitted=False,
                              validation_rows=validation['declared_row_count'], promoted=False)
            else:
                gate, receipt = fit(training)
                _save(root, name + '-policy.json', gate._json.encode())
                score = score_gate(gate, validation)
                _save(root, name + '-score.json', _bytes(score))
                record = dict(name=name, status='scored', fitted=True, fit=receipt,
                              counts=score['counts'], promoted=False)
            _save(root, name + '-result.json', _bytes(record))
            records.append(record)
    result = dict(records=records, new_gate_fits=sum(row['fitted'] for row in records),
        wall_ns_before_result_write=perf_counter_ns()-started, new_solves=0,
        reserved_evaluation=False, hyperparameter_search=False,
        winner_selected=False, full_path_speedup_claim=False, promoted=False)
    _save(root, 'result.json', _bytes(result))
    print(dict(completed_variant_folds=len(records), new_gate_fits=result['new_gate_fits']))


if __name__ == '__main__':
    main()
