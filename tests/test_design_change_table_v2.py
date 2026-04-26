from pathlib import Path
import json
import subprocess

REPORT = Path('implementation/phase1/release/design_optimization/design_optimization_cost_reduction_report.json')
CHANGES = Path('implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json')


def _ensure_reports():
    if REPORT.exists() and CHANGES.exists():
        return
    subprocess.run(['python3', 'implementation/phase1/run_design_optimization_cost_reduction.py'], check=True)


def test_design_change_rows_have_v2_columns():
    _ensure_reports()
    payload = json.loads(CHANGES.read_text(encoding='utf-8'))
    rows = payload.get('changes', [])
    assert rows
    row = rows[0]
    for key in (
        'before_section',
        'after_section',
        'before_rebar_ratio',
        'after_rebar_ratio',
        'before_thickness_scale',
        'after_thickness_scale',
        'before_detailing_quality',
        'after_detailing_quality',
        'governing_member_governing_dcr_before',
        'governing_member_governing_dcr_after',
        'drift_before_pct',
        'drift_after_pct',
        'residual_before_pct',
        'residual_after_pct',
        'constructability_delta',
        'overdesign_margin_delta',
        'reason_selected',
    ):
        assert key in row
