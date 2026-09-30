"""Compare original same-parent labels across distinct nested seed policies.

This is cross-policy sensitivity, not contradictory rows within a single gate's
training complement and not a pooled prediction-error lower bound.
"""

from collections import defaultdict

from audit_rc_nested_switch_labels import label_from_repetitions
from diagnose_rc_nested_work_benefit import work_relation
from prepare_rc_nested_switch_labels import require
from structural_analysis.benchmark.rc_control_design import _bytes, _sha


def diagnose(audit, plan):
    expected = {(task['outer_group_index'], task['inner_group_index'], sample): task
                for task in plan['label_tasks'] for sample in task['label_source_sample_hashes']}
    require(len(expected) == sum(len(task['label_source_sample_hashes']) for task in plan['label_tasks']),
            'unique declared nested observations required')
    seen, grouped = set(), defaultdict(list)
    for pair in audit['pairs']:
        key = (pair['outer_group_index'], pair['inner_group_index'], pair['source_sample_hash'])
        require(key in expected and key not in seen, 'unique original policy observation required')
        seen.add(key)
        task = expected[key]
        require(pair['seed_fit_index'] == task['seed_fit_index']
                and pair['case_id'] in task['label_case_ids']
                and pair['case_id'] not in task['outer_evaluation_case_ids'], 'original nested seed binding required')
        require(pair['label_result'] == label_from_repetitions(pair['repetitions']),
                'original repeated time label required')
        grouped[key[2]].append(pair)
    require(seen == set(expected), 'complete original policy observations required')
    rows = []
    for sample, pairs in sorted(grouped.items()):
        first = pairs[0]
        require(len(pairs) == len(plan['groups']) - 1
                and len({pair['policy_hash'] for pair in pairs}) == len(pairs),
                'one distinct seed per other outer group required')
        for pair in pairs:
            require(all(pair[key] == first[key] for key in
                        ('case_id', 'parent_hash', 'inner_group_index', 'guard_features')),
                    'identical original parent and guard inputs required')
        observations = []
        for pair in sorted(pairs, key=lambda row: row['outer_group_index']):
            repeats = sorted(pair['repetitions'], key=lambda row: row['repetition'])
            observations.append(dict(outer_group_index=pair['outer_group_index'],
                policy_hash=pair['policy_hash'], time_label=pair['label_result']['label'],
                work_relations=[work_relation(repeat)['relation'] for repeat in repeats],
                report_hashes=[repeat['report_hash'] for repeat in repeats]))
        rows.append(dict(source_sample_hash=sample, case_id=first['case_id'],
            parent_hash=first['parent_hash'], guard_features_hash=_sha(_bytes(first['guard_features'])),
            time_label_changes=len({row['time_label'] for row in observations}) > 1,
            work_categories_change=len({tuple(row['work_relations']) for row in observations}) > 1,
            observations=observations))
    return dict(parent_count=len(rows), pair_count=len(seen), rows=rows,
                parents_with_time_label_changes=sum(row['time_label_changes'] for row in rows),
                parents_with_work_category_changes=sum(row['work_categories_change'] for row in rows),
                new_fits=0, new_solves=0, reserved_evaluation=False,
                contradictory_labels_within_one_gate_claim=False,
                independent_generalization_claim=False)
