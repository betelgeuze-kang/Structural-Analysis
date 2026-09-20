"""Separate retained elapsed-time labels from measured solver-work reductions."""

from collections import Counter

from audit_rc_nested_switch_labels import label_from_repetitions
from prepare_rc_nested_switch_labels import require

COUNTERS = ('core_calls', 'newton_iterations', 'linear_solves')


def work_relation(repetition):
    if repetition['comparison_pass'] is not True:
        return dict(relation='unverified', delta=None)
    work = repetition['work']
    for arm in ('proposal', 'secant'):
        require(set(work[arm]) == set(COUNTERS)
                and all(type(work[arm][key]) is int and work[arm][key] >= 0 for key in COUNTERS),
                'complete nonnegative exact solver-work counters required')
    delta = {key: work['proposal'][key] - work['secant'][key] for key in COUNTERS}
    values = list(delta.values())
    if all(value == 0 for value in values):
        relation = 'equal'
    elif all(value <= 0 for value in values):
        relation = 'reduced'
    elif all(value >= 0 for value in values):
        relation = 'increased'
    else:
        relation = 'mixed'
    return dict(relation=relation, delta=delta)


def diagnose(audit):
    """Input must be the original authenticated nested-label audit artifact."""
    rows = []
    seen = set()
    for pair in audit['pairs']:
        key = (pair['outer_group_index'], pair['inner_group_index'], pair['source_sample_hash'])
        require(key not in seen, 'unique original nested pair required')
        seen.add(key)
        label = label_from_repetitions(pair['repetitions'])
        require(label == pair['label_result'], 'original elapsed-time label required')
        repetitions = sorted(pair['repetitions'], key=lambda row: row['repetition'])
        results = [work_relation(row) for row in repetitions]
        relations = {result['relation'] for result in results}
        relation = next(iter(relations)) if len(relations) == 1 else 'varies_across_repeats'
        rows.append(dict(outer_group_index=key[0], inner_group_index=key[1],
            source_sample_hash=key[2], case_id=pair['case_id'], parent_hash=pair['parent_hash'],
            time_label=label['label'], work_relation=relation,
            repetitions=[dict(repetition=row['repetition'], decision=row['decision'],
                              report_hash=row['report_hash'], path_time_ratio=row['path_time_ratio'],
                              **result) for row, result in zip(repetitions, results, strict=True)]))
    rows.sort(key=lambda row: (row['outer_group_index'], row['inner_group_index'], row['source_sample_hash']))
    return dict(pair_count=len(rows), rows=rows,
                all_pairs_by_work_relation=dict(Counter(row['work_relation'] for row in rows)),
                positive_time_labels_by_work_relation=dict(Counter(
                    row['work_relation'] for row in rows if row['time_label'] is True)),
                negative_time_labels_by_work_relation=dict(Counter(
                    row['work_relation'] for row in rows if row['time_label'] is False)),
                new_fits=0, new_solves=0, reserved_evaluation=False,
                identical_work_proves_identical_runtime=False,
                independent_evaluation=False, full_path_speedup_claim=False)
