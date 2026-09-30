"""Score excluded-group decisions without turning unknown labels into negatives."""

from time import perf_counter_ns

from audit_rc_nested_switch_labels import label_from_repetitions
from prepare_rc_nested_switch_labels import require
from rc_cost_margin_gate import cost_target
from rc_switch_gate import RidgeGate
from rc_offline_cost_tree import OfflineCostTree
from structural_analysis.benchmark.rc_control_design import _bytes, _sha


def score_gate(gate, validation):
    require(isinstance(gate, (RidgeGate, OfflineCostTree)), 'validated fixed gate policy required')
    rows = validation['rows']
    require(type(rows) is list and rows and type(validation['declared_row_count']) is int
            and validation['declared_row_count'] == len(rows),
            'complete nonempty validation denominator required')
    hashes = [row['source_sample_hash'] for row in rows]
    require(len(set(hashes)) == len(hashes)
            and not set(hashes).intersection(gate._payload['training_sample_hashes']),
            'unique validation samples excluded from gate training required')
    require(all(row['case_id'] in gate._payload['excluded_case_ids'] for row in rows),
            'whole validation cases must be excluded from gate training')
    decisions, inference_ns = [], 0
    # Freeze every prediction using only original prefix features before scoring
    # any measured labels. The policy is already immutable and fitted.
    for row in rows:
        features = dict(profile=validation['feature_profile'],
                        feature_names=validation['feature_names'], values=row['values'])
        started = perf_counter_ns()
        decision = gate.decision(features)
        inference_ns += perf_counter_ns() - started
        require(type(decision) is bool, 'exact Boolean gate decision required')
        decisions.append(decision)
    counts = dict(true_positive=0, false_positive=0, true_negative=0, false_negative=0,
                  proposed_unverified=0, declined_unverified=0)
    records = []
    for row, decision in zip(rows, decisions, strict=True):
        label = label_from_repetitions(row['cost_repetitions'])['label']
        target = cost_target(row['cost_repetitions'])
        require(row['label'] is label and ((target is None and row['cost_target'] is None)
                or (type(row['cost_target']) is float and row['cost_target'] == target)),
                'unchanged measured validation label and cost target required')
        if label is None:
            category = 'proposed_unverified' if decision else 'declined_unverified'
        elif decision:
            category = 'true_positive' if label else 'false_positive'
        else:
            category = 'false_negative' if label else 'true_negative'
        counts[category] += 1
        records.append(dict(source_sample_hash=row['source_sample_hash'], case_id=row['case_id'],
            parent_hash=row['parent_hash'], producing_seed_policy_hash=row['policy_hash'],
            decision=decision, measured_label=label, measured_worst_repeat_margin=target,
            category=category, report_hashes=[repeat['report_hash'] for repeat in row['cost_repetitions']]))
    unknown = counts['proposed_unverified'] + counts['declined_unverified']
    require(type(validation['unverified_count']) is int and validation['unverified_count'] == unknown,
            'complete unknown validation count required')
    known_selected = counts['true_positive'] + counts['false_positive']
    positives = counts['true_positive'] + counts['false_negative']
    return dict(policy_hash=gate.policy_hash, validation_rows_hash=_sha(_bytes(validation)),
        declared_rows=len(rows), verified_rows=len(rows)-unknown, counts=counts,
        precision_on_verified_proposals=counts['true_positive']/known_selected if known_selected else None,
        recall_on_verified_positives=counts['true_positive']/positives if positives else None,
        verification_fraction=(len(rows)-unknown)/len(rows),
        inference_call_wall_ns=inference_ns,
        inference_cost_scope='decision calls only; excludes setup, feature extraction, validation and reporting',
        all_required_rows_verified=unknown == 0, records=records,
        full_path_evaluation=False, total_runtime_benefit_measured=False,
        promoted=False, independent_project_evaluation=False)
