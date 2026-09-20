"""Reconstruct 165 training-only summaries from pinned original parents; no fits."""

import argparse
from pathlib import Path
import re
from time import perf_counter_ns

from rc_accepted_material_summary import PROFILE, accepted_material_summary
from run_rc_pooled_runtime_campaign import ARITHMETIC, NEW_INVENTORY, inputs
from run_rc_same_parent_seed_probe import PINS, reader
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    load_stateful_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_material_features import committed_material_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-labels', 'new-labels', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    started = perf_counter_ns()
    cases, samples, _, groups, costs = inputs(args.old_labels, args.new_labels)
    prepared = learning._preflight([case for case in cases if case.split == 'train'], ARITHMETIC)
    readers = {False: reader(args.old_labels, PINS['labels']),
               True: reader(args.new_labels, NEW_INVENTORY)}
    old_cases = set(groups[0] + groups[1] + groups[2])
    rows = []
    for sample in samples:
        case_id = sample['case_id']
        if sample['split'] != 'train' or case_id not in prepared:
            raise ValueError('original training-only roster required')
        read = readers[case_id not in old_cases]
        root = args.old_labels if case_id in old_cases else args.new_labels
        stem = f"study/labels/{case_id}/generation/reference/{sample['target_index']:03d}"
        step = read(stem + '-1-step.json')
        context = read(stem + '-context.json')
        if (context != sample['context'] or step['committed'] is not True
                or step['trial_solution']['augmented_coordinates_m'] != sample['accepted_coordinates']
                or _sha((root / (stem + '-1-step.json')).read_bytes()) != sample['original_step_bytes_hash']):
            raise ValueError('original label context and step required')
        problem = prepared[case_id][1].problem
        parent = load_stateful_fiber_frame2d_checkpoint_bytes(_bytes(step['parent_checkpoint']), problem)
        if parent.state_hash != sample['parent_hash']:
            raise ValueError('original accepted parent required')
        snapshot = committed_material_snapshot(problem, parent)
        if snapshot != context['committed_material_state_json']:
            raise ValueError('retained snapshot must reproduce native accepted parent exactly')
        summary = accepted_material_summary(snapshot, problem.contract_hash, parent.state_hash)
        rows.append(dict(case_id=case_id, source_sample_hash=sample['sample_hash'],
                         original_step_bytes_hash=sample['original_step_bytes_hash'], summary=summary))
    names = rows[0]['summary']['feature_names']
    if len(rows) != 165 or any(row['summary']['feature_names'] != names for row in rows):
        raise ValueError('complete consistently ordered 165-row summary required')
    result = dict(source_revision=args.source_revision, profile=PROFILE,
                  input_inventories=dict(old=PINS['labels'], new=NEW_INVENTORY),
                  rows=rows, row_count=len(rows), feature_count=len(names), groups=groups,
                  historical_label_costs_separate=costs, structural_solves=0, new_fits=0,
                  reserved_evaluation_executed=False, policy_changed=False,
                  online_extraction_cost_measured=False,
                  audit_wall_ns=perf_counter_ns() - started)
    args.output.mkdir(parents=True, exist_ok=False)
    _save(args.output, 'summaries.json', _bytes(result))
    print(dict(row_count=len(rows), feature_count=len(names), structural_solves=0, new_fits=0,
               audit_wall_ns=result['audit_wall_ns']))


if __name__ == '__main__':
    main()
