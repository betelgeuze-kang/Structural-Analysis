import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation" / "phase1"))

from design_optimization_explain_schema import build_explain_row, validate_explain_rows


def test_explain_row_has_required_fields():
    row = build_explain_row(
        candidate_id='c1',
        stage='stage_b',
        budget_mode='medium',
        objective_profile='cost_first',
        group_id='G1',
        group_index=0,
        story_band=1,
        zone_label='perimeter',
        member_type='slab',
        semantic_group='S1',
        action_name='slab_thickness_down',
        action_family='slab_thickness',
        selected_in_final_loop=True,
        selected_event_index=1,
        current_max_dcr=0.9,
        trial_max_dcr=0.95,
        final_max_dcr=0.93,
        current_cost=100.0,
        trial_cost=95.0,
        delta_cost=5.0,
        current_drift_pct=1.2,
        trial_drift_pct=1.25,
        current_residual_drift_pct=0.1,
        trial_residual_drift_pct=0.12,
        current_congestion=0.3,
        trial_congestion=0.28,
        current_detailing_complexity=0.2,
        trial_detailing_complexity=0.18,
        current_constructability=0.34,
        trial_constructability=0.29,
        current_robustness_margin=0.4,
        trial_robustness_margin=0.38,
        current_multi_hazard_margin=0.45,
        trial_multi_hazard_margin=0.43,
        current_member_governing_dcr=0.9,
        trial_member_governing_dcr=0.95,
        current_member_governing_clause='KDS-MOMENT-Y-001',
        trial_member_governing_clause='KDS-MOMENT-Y-001',
        reason_selected='selected_best_gain_in_batch',
        reason_rejected='',
        detail='structured row',
    )
    report = validate_explain_rows([row])
    assert report['contract_pass'] is True
    for key in (
        'current_max_dcr',
        'trial_max_dcr',
        'final_max_dcr',
        'current_cost',
        'trial_cost',
        'delta_cost',
        'current_constructability',
        'trial_constructability',
        'reason_selected',
        'reason_rejected',
        'detail',
    ):
        assert key in row


def test_explain_row_accepts_constructability_hard_gate_rejection_reason():
    row = build_explain_row(
        candidate_id='r1',
        stage='stage_b',
        budget_mode='medium',
        objective_profile='balanced_practice',
        group_id='G2',
        group_index=1,
        story_band=2,
        zone_label='core',
        member_type='beam',
        semantic_group='B1',
        action_name='connection_detailing_down',
        action_family='connection_detailing',
        selected_in_final_loop=False,
        selected_event_index=0,
        current_max_dcr=0.82,
        trial_max_dcr=0.82,
        final_max_dcr=0.79,
        current_cost=100.0,
        trial_cost=100.0,
        delta_cost=0.0,
        current_drift_pct=1.1,
        trial_drift_pct=1.1,
        current_residual_drift_pct=0.1,
        trial_residual_drift_pct=0.1,
        current_congestion=0.21,
        trial_congestion=0.24,
        current_detailing_complexity=0.61,
        trial_detailing_complexity=0.62,
        current_constructability=0.41,
        trial_constructability=0.42,
        current_robustness_margin=0.4,
        trial_robustness_margin=0.4,
        current_multi_hazard_margin=0.45,
        trial_multi_hazard_margin=0.45,
        current_member_governing_dcr=0.82,
        trial_member_governing_dcr=0.82,
        current_member_governing_clause='KDS-BEAM-001',
        trial_member_governing_clause='KDS-BEAM-001',
        reason_selected='',
        reason_rejected='rejected_constructability_hard_gate',
        detail='blocked by constructability hard gate',
    )
    report = validate_explain_rows([row])
    assert report['contract_pass'] is True
