from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path('implementation/phase1/run_structural_contact_validation.py')


def test_run_structural_contact_validation_produces_full_6_of_6_report(tmp_path: Path) -> None:
    out = tmp_path / 'structural_contact_validation_report.json'
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--out', str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding='utf-8'))
    assert payload['contract_pass'] is True
    assert payload['reason_code'] == 'PASS'
    assert payload['checks']['contact_validation_pass'] is True
    assert payload['checks']['event_sequence_pass'] is True
    assert payload['checks']['support_search_surface_pass'] is True
    assert payload['checks']['node_to_surface_proxy_pass'] is True
    assert payload['checks']['contact_family_surface_pass'] is True
    assert payload['checks']['support_search_family_surface_pass'] is True
    assert payload['checks']['node_to_surface_proxy_family_surface_pass'] is True
    assert payload['summary']['validated_category_count'] == 6
    assert payload['summary']['required_category_count'] == 6
    assert payload['summary']['contact_family_count'] == 6
    assert payload['summary']['contact_uplift_event_sequence_mismatch'] == 0
    assert payload['summary']['foundation_support_model_types'] == ['p-y', 'pile_head', 'q-z', 't-z']
    assert payload['summary']['device_model_types'] == [
        'friction_pendulum',
        'lead_rubber_bearing',
        'tmd',
        'viscoelastic_damper',
        'viscous_damper',
    ]
    assert payload['summary']['support_library_group_counts'] == {'contact': 6, 'foundation': 4, 'device': 5}
    assert payload['summary']['support_search_model_types'] == [
        'friction_pendulum',
        'lead_rubber_bearing',
        'p-y',
        'pile_head',
        'q-z',
        't-z',
        'tmd',
        'viscoelastic_damper',
        'viscous_damper',
    ]
    assert payload['summary']['node_to_surface_proxy_model_types'] == [
        'friction_pendulum',
        'lead_rubber_bearing',
        'p-y',
        'q-z',
        't-z',
    ]
    assert payload['summary']['support_search_family_types'] == [
        'device_support_search',
        'foundation_support_search',
    ]
    assert payload['summary']['node_to_surface_proxy_family_types'] == [
        'device_support_search',
        'foundation_support_search',
    ]
    assert payload['summary']['search_ready_group_counts'] == {'contact': 6, 'support_ready': 9, 'node_to_surface_proxy': 5}
    assert payload['summary']['support_depth_score'] == 21
    assert payload['summary']['search_surface_mode_counts']['brace_end_support_search'] == 2
    assert payload['summary']['search_surface_mode_counts']['node_to_surface_isolation_proxy'] == 2
    assert payload['summary_line'].startswith('Structural contact validation: PASS')
    assert 'support_search=9' in payload['summary_line']
    assert 'node_surface_proxy=5' in payload['summary_line']
    assert sorted(payload['categories']) == ['bearing', 'compression_only', 'friction', 'gap', 'pounding', 'uplift']
    assert all(bool(row['validated']) for row in payload['categories'].values())
