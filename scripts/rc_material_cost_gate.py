"""Offline fixed cost gate with parent-bound native summaries; no online guard."""

from copy import deepcopy
from math import isfinite
from time import perf_counter_ns

from rc_accepted_material_summary import PROFILE as SUMMARY_PROFILE
from rc_cost_margin_gate import CostMarginGate, _fit_cost_gate, cost_training_rows
from prepare_rc_nested_switch_labels import require
from structural_analysis.benchmark.rc_control_design import _bytes, _sha

PROFILE = 'rc-prefix-and-accepted-material-summary.v1'


class MaterialCostGate(CostMarginGate):
    _schema = 'rc-offline-material-cost-margin-gate.v1'
    _feature_profile = PROFILE

    def guard(self, model_features):
        raise ValueError('offline material gate has no cost-validated runtime adapter')


def material_training_rows(audit, plan, summaries, outer):
    """Call with authenticated artifacts; join by sample, case and parent."""
    training = cost_training_rows(audit, plan, outer)
    require(summaries['profile'] == SUMMARY_PROFILE and summaries['groups'] == plan['groups']
            and summaries['row_count'] == 165 and len(summaries['rows']) == 165
            and summaries['feature_count'] == 27, 'complete original material summary roster required')
    indexed = {}
    names = None
    for row in summaries['rows']:
        key, summary = row['source_sample_hash'], row['summary']
        require(key not in indexed, 'unique material source sample required')
        require(summary['profile'] == SUMMARY_PROFILE and len(summary['feature_names']) == 27
                and len(set(summary['feature_names'])) == 27 and len(summary['values']) == 27
                and all(type(value) in (int, float) and isfinite(value) for value in summary['values']),
                'finite aligned original material summary required')
        if names is None:
            names = summary['feature_names']
        require(summary['feature_names'] == names, 'consistent material summary names required')
        indexed[key] = row
    required = {row['source_sample_hash'] for row in audit['pairs']}
    require(set(indexed) == required, 'exact nested-label material sample coverage required')
    # Validate every join before selecting this outer complement.
    for row in audit['pairs']:
        original = indexed[row['source_sample_hash']]
        require(original['case_id'] == row['case_id']
                and original['summary']['parent_state_hash'] == row['parent_hash'],
                'material source case and original parent binding required')
    for row in training['training_rows']:
        original = indexed[row['source_sample_hash']]
        row['material_summary'] = deepcopy(original['summary'])
        row['original_step_bytes_hash'] = original['original_step_bytes_hash']
        row['values'].extend(original['summary']['values'])
    training['feature_profile'] = PROFILE
    training['feature_names'] = [*training['feature_names'], *('material.' + name for name in names)]
    training['material_summaries_hash'] = _sha(_bytes(summaries))
    return training


def fit_material_gate(training):
    started = perf_counter_ns()
    require(training['feature_profile'] == PROFILE, 'fixed material feature profile required')
    gate, receipt = _fit_cost_gate(training, MaterialCostGate)
    receipt['fit_wall_ns'] = perf_counter_ns() - started
    receipt['online_extraction_cost_in_target'] = False
    return gate, receipt
