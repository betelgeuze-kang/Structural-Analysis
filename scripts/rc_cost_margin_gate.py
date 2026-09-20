"""Fixed development gate predicting worst observed relative time margin.

This is not a confidence bound or a calibrated benefit probability. The target
does not include this new gate's own cost; full-path evaluation must charge it.
"""

import re
from time import perf_counter_ns

from audit_rc_nested_switch_labels import label_from_repetitions
from prepare_rc_nested_switch_labels import require
from rc_switch_gate import RidgeGate, _fit_gate
from rc_switch_gate_training_rows import gate_training_rows

TARGET_PROFILE = 'minimum-three-repeat-relative-time-margin.v1'


class CostMarginGate(RidgeGate):
    _schema = 'rc-pre-capture-cost-margin-gate.v1'
    _threshold = 0.01


def cost_target(repetitions):
    label = label_from_repetitions(repetitions)
    if label['label'] is None:
        return None
    allowed = {'proposed', 'abstained_to_secant', 'abstained_to_reference',
               'invalid_proposal_to_reference'}
    require(all(row['decision'] in allowed for row in repetitions), 'known proposal decisions required')
    margin = min(1.0 - row['path_time_ratio'] for row in repetitions)
    return margin if all(row['decision'] == 'proposed' for row in repetitions) else min(0.0, margin)


def cost_training_rows(audit, plan, outer):
    training = gate_training_rows(audit, plan, outer)
    originals = {(row['outer_group_index'], row['inner_group_index'], row['source_sample_hash']): row
                 for row in audit['pairs']}
    for row in training['training_rows']:
        original = originals[(outer, row['inner_group_index'], row['source_sample_hash'])]
        repeats = []
        for repeat in sorted(original['repetitions'], key=lambda value: value['repetition']):
            digest = repeat['report_hash']
            require(type(digest) is str and re.fullmatch('sha256:[0-9a-f]{64}', digest),
                    'original repetition report hash required')
            repeats.append({key: repeat[key] for key in
                            ('repetition', 'comparison_pass', 'decision', 'path_time_ratio', 'report_hash')})
        row['cost_repetitions'] = repeats
        row['cost_target'] = cost_target(repeats)
        require(row['cost_target'] is not None, 'verified cost target required')
    training['cost_target_profile'] = TARGET_PROFILE
    return training


def fit_cost_gate(training):
    return _fit_cost_gate(training, CostMarginGate)


def _fit_cost_gate(training, gate_class):
    started = perf_counter_ns()
    require(training['cost_target_profile'] == TARGET_PROFILE, 'fixed cost target profile required')
    targets = []
    for row in training['training_rows']:
        target = cost_target(row['cost_repetitions'])
        require(target is not None and type(row['cost_target']) is float
                and row['cost_target'] == target, 'original measured cost target required')
        require(row['label'] is label_from_repetitions(row['cost_repetitions'])['label'],
                'original benefit label required')
        targets.append(target)
    gate, receipt = _fit_gate(training, targets, gate_class)
    receipt['target_profile'] = TARGET_PROFILE
    receipt['gate_cost_in_training_target'] = False
    receipt['fit_wall_ns'] = perf_counter_ns() - started
    return gate, receipt
