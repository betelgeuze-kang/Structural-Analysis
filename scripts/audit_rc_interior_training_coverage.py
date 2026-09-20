"""Bind new training labels to original accepted steps, then diagnose coverage.

No solver calls, fitting, evaluation paths or policy promotion occur here.
"""
import argparse
from collections import Counter
from pathlib import Path

from run_grouped_rc_history_coverage import reference_parent_range_checks
from run_grouped_rc_runtime_campaign import ARITHMETIC
from run_rc_interior_training_coverage import expanded_cases
from run_rc_same_parent_seed_probe import PINS, reader
from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_runtime_selection import _validate_case_rows
from structural_analysis.benchmark.rc_control_training_diagnostics import _validated_training_data


def read(path):
    return strict_json_object_bytes(b'{"value":' + path.read_bytes() + b'}',
                                    maximum_bytes=256 * 1024 * 1024)['value']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def audit(root, retained_root):
    prior = reader(retained_root, PINS['labels'])
    original, new, combined, groups = expanded_cases()
    plan = read(root / 'plan.json')
    require(plan['groups'] == groups and plan['generation_case_ids'] == [c.case_id for c in new],
            'declared generation roster or groups changed')
    require(plan['combined_cases'] == [{'case_id': c.case_id, 'split': c.split,
                                       'model': c.model.canonical_payload(),
                                       'request': c.request.to_dict()} for c in combined],
            'declared model or request changed')
    prepared = learning._preflight(combined, ARITHMETIC)
    old_samples = prior('study/labels/training-samples.json')
    old_policy = learning.RCControlSeedPolicy(_bytes(prior('study/labels/policy.json')).decode())
    old_source, old_grouped, old_profile = _validated_training_data(old_samples, old_policy)
    _validate_case_rows(original, prepared, old_grouped, old_source, ARITHMETIC)
    samples = read(root / 'labels/training-samples.json')
    policy = learning.RCControlSeedPolicy((root / 'labels/policy.json').read_text())
    source, grouped, profile = _validated_training_data(samples, policy)
    _validate_case_rows(new, prepared, grouped, source, ARITHMETIC)
    require(profile == old_profile, 'old and new feature/solver profiles differ')
    require(len(samples) == 66 and len(old_samples) == 99, 'complete 66 plus 99 labels required')
    require(not (set(grouped) & set(old_grouped)), 'new cases overlap retained cases')
    report = read(root / 'labels/learning-study.json')
    require(report['source_revision'] == plan['source_revision'], 'declared source differs')
    require(report['report_hash'] == _sha(_bytes({k: v for k, v in report.items() if k != 'report_hash'})),
            'learning report hash mismatch')
    require(report['evaluation_deferred'] is True, 'reserved evaluation deferral required')
    require(report['evaluation_work']['known_work']['core_calls'] == 0,
            'reserved solver calls forbidden')
    require(len(report['generation']) == 6 and all(r['labels_eligible'] for r in report['generation']),
            'all six generation paths must verify')
    for sample in samples:
        folder = root / 'labels' / sample['case_id'] / 'generation/reference'
        stem = f"{sample['target_index']:03d}"
        raw = (folder / (stem + '-1-step.json')).read_bytes()
        require(_sha(raw) == sample['original_step_bytes_hash'], 'original label step bytes changed')
        step = read(folder / (stem + '-1-step.json'))
        require(step['committed'] is True, 'accepted original label required')
        require(step['parent_checkpoint']['state_hash'] == sample['parent_hash'], 'parent mismatch')
        require(step['trial_solution']['augmented_coordinates_m'] == sample['accepted_coordinates'],
                'accepted label coordinates mismatch')
        require(read(folder / (stem + '-context.json')) == sample['context'], 'original context mismatch')
    pooled = old_samples + samples
    require(len({s['sample_hash'] for s in pooled}) == 165, 'duplicate pooled samples')
    ranges = reference_parent_range_checks(pooled, policy.to_dict(), groups, 0.1)
    counts = Counter(row['case_id'] for row in ranges if row['range_eligible'])
    return {'old_label_count': 99, 'new_label_count': 66, 'pooled_label_count': 165,
            'groups': groups, 'range_eligible_counts': dict(sorted(counts.items())),
            'range_checks': ranges, 'generation_work': report['generation_work'],
            'learning_wall_ns': report['whole_study_wall_ns'],
            'new_label_step_bindings_verified': 66,
            'new_policy_hash': policy.policy_hash,
            'retained_labels_inventory_sha256': PINS['labels'],
            'new_sample_file_sha256': _sha((root / 'labels/training-samples.json').read_bytes()),
            'fitting_samples_per_excluded_group': 132,
            'range_eligibility_proves_runtime_benefit': False,
            'reserved_evaluation_executed': False, 'independent_project_provenance': False,
            'solver_calls': 0, 'new_fits_in_audit': 0, 'policy_promoted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('retained_labels', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.study, args.retained_labels)
    _save(args.output.parent, args.output.name, _bytes(result))
    print({k: v for k, v in result.items() if k not in ('range_checks', 'generation_work')})
