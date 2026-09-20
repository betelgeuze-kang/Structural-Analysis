"""Prepare leakage-resistant inner gate validation without fitting or solving.

Existing two-group seed exclusions suffice for the existing outer experiment.
An additional gate-validation group requires three-group exclusions in seeds
that generate gate-training labels. This planner does not claim that the
existing outer-only results are leaky.
"""

from itertools import combinations

from prepare_rc_nested_switch_labels import nested_plan, require


def inner_validation_plan(groups, samples):
    original = nested_plan(groups, samples)
    groups = original['groups']
    require(len(groups) >= 4, 'at least four groups for three-group exclusion required')
    group_samples = [sorted(row['sample_hash'] for row in samples if row['case_id'] in group)
                     for group in groups]
    fits, fit_ids = [], {}
    for excluded in combinations(range(len(groups)), 3):
        fit_ids[excluded] = len(fits)
        excluded_cases = sorted(case for index in excluded for case in groups[index])
        training = sorted(row['sample_hash'] for row in samples if row['case_id'] not in excluded_cases)
        require(training, 'nonempty three-group seed complement required')
        fits.append(dict(fit_index=len(fits), excluded_group_indices=list(excluded),
                         excluded_case_ids=excluded_cases, training_sample_hashes=training,
                         ridge=10000.0))
    tasks, task_ids, folds = [], {}, []
    original_tasks = {(task['outer_group_index'], task['inner_group_index']): task
                      for task in original['label_tasks']}
    for outer in range(len(groups)):
        for validation in range(len(groups)):
            if outer == validation:
                continue
            training_tasks = []
            for inner in range(len(groups)):
                if inner in (outer, validation):
                    continue
                excluded = tuple(sorted((outer, validation, inner)))
                fit_index = fit_ids[excluded]
                key = (fit_index, inner)
                if key not in task_ids:
                    task_ids[key] = len(tasks)
                    tasks.append(dict(task_index=len(tasks), seed_fit_index=fit_index,
                        label_group_index=inner, label_case_ids=groups[inner],
                        label_source_sample_hashes=group_samples[inner]))
                training_tasks.append(task_ids[key])
            retained = original_tasks[(outer, validation)]
            folds.append(dict(outer_group_index=outer, validation_group_index=validation,
                excluded_case_ids=sorted(groups[outer] + groups[validation]),
                training_label_task_indices=training_tasks,
                validation_label_task=dict(retained),
                gate_training_row_count=sum(len(tasks[index]['label_source_sample_hashes'])
                                            for index in training_tasks),
                validation_row_count=len(group_samples[validation])))
    pairs = sum(len(task['label_source_sample_hashes']) for task in tasks)
    return dict(schema_version='rc-gate-inner-validation-provenance.v1', groups=groups,
                seed_fits=fits, unique_new_label_tasks=tasks, gate_folds=folds,
                planned_new_seed_fits=len(fits), planned_new_unique_parent_pairs=pairs,
                planned_new_comparisons=pairs * original['repetitions'],
                planned_new_single_target_paths=pairs * original['repetitions'] * 4,
                planned_gate_validation_folds=len(folds), new_fits_executed=0,
                new_solves_executed=0, reserved_evaluation_executed=False,
                validation_label_reuse_requires_original_artifact_binding=True,
                independent_project_validation=False,
                scope='provenance plan only; no classifier or hyperparameter selected')


def require_fold_seed_exclusions(plan, fold, sample_case_ids):
    """Reject gate-training labels whose producing seeds saw the held-out cases."""
    forbidden = set(fold['excluded_case_ids'])
    fits = {fit['fit_index']: fit for fit in plan['seed_fits']}
    tasks = {task['task_index']: task for task in plan['unique_new_label_tasks']}
    for index in fold['training_label_task_indices']:
        task = tasks[index]
        require(not forbidden.intersection(task['label_case_ids']), 'held-out gate label case forbidden')
        fit = fits[task['seed_fit_index']]
        require(forbidden.union(task['label_case_ids']).issubset(fit['excluded_case_ids']),
                'seed must exclude outer, validation and label groups')
        require(all(sample_case_ids[identity] not in forbidden.union(task['label_case_ids'])
                    for identity in fit['training_sample_hashes']),
                'held-out data in gate-label seed training')
        expected = {identity for identity, case in sample_case_ids.items()
                    if case not in fit['excluded_case_ids']}
        require(len(fit['training_sample_hashes']) == len(expected)
                and set(fit['training_sample_hashes']) == expected,
                'complete exact seed complement required')
