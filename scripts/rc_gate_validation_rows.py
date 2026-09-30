"""Join authenticated triple-excluded train labels and retained validation labels.

This in-memory boundary does not authenticate files. Callers must first audit
both campaigns and verify the original seed-policy receipts.
"""

from copy import deepcopy
import math
import re

from audit_rc_nested_switch_labels import label_from_repetitions
from rc_cost_margin_gate import TARGET_PROFILE, cost_target
from rc_switch_prefix_features import PROFILE
from prepare_rc_nested_switch_labels import require


def _index(audit, tasks, policy_hashes, *, retained):
    axes = ('outer_group_index', 'inner_group_index') if retained else ('task_index',)
    expected = {(*(task[axis] for axis in axes), sample): task
                for task in tasks for sample in task['label_source_sample_hashes']}
    require(len(expected) == sum(len(task['label_source_sample_hashes']) for task in tasks),
            'unique complete label task declaration required')
    require(len(audit['pairs']) == len(expected), 'complete audited campaign required')
    result = {}
    names = None
    for pair in audit['pairs']:
        require(all(type(pair[axis]) is int for axis in axes), 'exact label task indices required')
        key = (*(pair[axis] for axis in axes), pair['source_sample_hash'])
        require(key in expected and key not in result, 'unique declared label pair required')
        task = expected[key]
        require(type(pair['seed_fit_index']) is int
                and pair['seed_fit_index'] == task['seed_fit_index']
                and pair['case_id'] in task['label_case_ids']
                and pair['policy_hash'] == policy_hashes[task['seed_fit_index']],
                'original producing seed policy and case required')
        if not retained:
            require(type(pair['label_group_index']) is int
                    and pair['label_group_index'] == task['label_group_index'],
                    'original label group required')
        label = label_from_repetitions(pair['repetitions'])
        require(pair['label_result'] == label, 'original measured label required')
        features = pair['guard_features']
        current, values = features['feature_names'], features['values']
        require(features['profile'] == PROFILE and type(current) is list and current
                and all(type(name) is str and name for name in current)
                and len(set(current)) == len(current) and type(values) is list
                and len(values) == len(current)
                and all(type(value) in (int, float) and math.isfinite(value) for value in values),
                'finite aligned original prefix features required')
        if names is None:
            names = current
        require(current == names, 'consistent original feature schema required')
        repeats = []
        for repeat in sorted(pair['repetitions'], key=lambda row: row['repetition']):
            require(type(repeat['report_hash']) is str
                    and re.fullmatch('sha256:[0-9a-f]{64}', repeat['report_hash']),
                    'original report identity required')
            repeats.append({field: repeat[field] for field in
                            ('repetition', 'comparison_pass', 'decision', 'path_time_ratio', 'report_hash')})
        result[key] = dict(case_id=pair['case_id'], source_sample_hash=pair['source_sample_hash'],
            parent_hash=pair['parent_hash'], seed_fit_index=pair['seed_fit_index'],
            policy_hash=pair['policy_hash'], values=list(values), label=label['label'],
            cost_repetitions=repeats, cost_target=cost_target(repeats))
    require(set(result) == set(expected), 'complete original label coverage required')
    return result, names


def assemble_fold(new_audit, retained_audit, plan, outer, validation, *, new_policy_hashes, old_policy_hashes):
    require(type(outer) is int and type(validation) is int and outer != validation,
            'distinct exact outer and validation group indices required')
    folds = [fold for fold in plan['gate_folds']
             if (fold['outer_group_index'], fold['validation_group_index']) == (outer, validation)]
    require(len(folds) == 1, 'one declared gate validation fold required')
    fold = folds[0]
    tasks = plan['unique_new_label_tasks']
    new, names = _index(new_audit, tasks, new_policy_hashes, retained=False)
    old_tasks = [item['validation_label_task'] for item in plan['gate_folds']]
    old, old_names = _index(retained_audit, old_tasks, old_policy_hashes, retained=True)
    require(names == old_names, 'matching training and validation feature schemas required')
    parents = {}
    for row in [*new.values(), *old.values()]:
        signature = (row['case_id'], row['parent_hash'], row['values'])
        sample = row['source_sample_hash']
        require(sample not in parents or parents[sample] == signature,
                'same source sample must retain original parent and features')
        parents[sample] = signature
    selected_tasks = set(fold['training_label_task_indices'])
    train = [deepcopy(row) for key, row in sorted(new.items()) if key[0] in selected_tasks]
    check = [deepcopy(row) for key, row in sorted(old.items()) if key[:2] == (outer, validation)]
    forbidden = set(fold['excluded_case_ids'])
    require(len(train) == fold['gate_training_row_count'] and len(check) == fold['validation_row_count']
            and all(row['case_id'] not in forbidden for row in train)
            and all(row['case_id'] in plan['groups'][validation] for row in check)
            and not {row['source_sample_hash'] for row in train}.intersection(
                row['source_sample_hash'] for row in check), 'complete disjoint train/validation split required')
    verified = [row for row in train if row['label'] is not None]
    training = dict(outer_group_index=outer, validation_group_index=validation,
                excluded_case_ids=list(fold['excluded_case_ids']), feature_profile=PROFILE,
                feature_names=list(names), cost_target_profile=TARGET_PROFILE,
                training_rows=verified, unverified_rows=[row for row in train if row['label'] is None],
                verified_positive_count=sum(row['label'] is True for row in verified),
                verified_negative_count=sum(row['label'] is False for row in verified),
                normalization_scope='verified training rows only; no validation statistics',
                gate_fitted=False, independent_evaluation=False)
    return dict(training=training, validation=dict(outer_group_index=outer,
        validation_group_index=validation, feature_profile=PROFILE, feature_names=list(names),
        rows=check, unverified_count=sum(row['label'] is None for row in check),
        declared_row_count=fold['validation_row_count'], independent_evaluation=False))


def append_material_inputs(tables, summaries):
    """Append only each row's own accepted-parent material statistics."""
    from rc_material_cost_gate import PROFILE as MATERIAL_PROFILE, material_summary_index
    indexed, names = material_summary_index(summaries)
    result = deepcopy(tables)
    for table, collections in ((result['training'], ('training_rows', 'unverified_rows')),
                               (result['validation'], ('rows',))):
        require(table['feature_profile'] == PROFILE, 'original prefix input table required')
        for collection in collections:
            for row in table[collection]:
                require(row['source_sample_hash'] in indexed, 'original material source sample required')
                original = indexed[row['source_sample_hash']]
                summary = original['summary']
                require(original['case_id'] == row['case_id']
                        and summary['parent_state_hash'] == row['parent_hash'],
                        'original material parent and case binding required')
                row['material_summary'] = deepcopy(summary)
                row['original_step_bytes_hash'] = original['original_step_bytes_hash']
                row['values'].extend(summary['values'])
        table['feature_profile'] = MATERIAL_PROFILE
        table['feature_names'] = [*table['feature_names'], *('material.' + name for name in names)]
    # Do not put the complete summary artifact hash (which includes validation
    # and outer-group inputs) inside the object passed to the training fitter.
    return result
