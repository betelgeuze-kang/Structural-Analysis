from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_midas_loadcomb_roundtrip_reports_exact_match() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / 'implementation/phase1/compare_midas_loadcomb_roundtrip.py',
        'compare_midas_loadcomb_roundtrip_test',
    )
    payload = {
        'model': {
            'load_combinations_raw': [
                'NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0',
                'ST, DEAD, 1.2, ST, LIVE, 1.6',
                'NAME=ENV1, GEN, ACTIVE, 0, 1, Envelope refs ULS1, 0, 0, 0',
                'CB, ULS1, 1',
            ],
            'metadata': {
                'load_combination_editor_seed': {
                    'summary': {'combination_count': 2},
                    'combination_nodes': [
                        {
                            'name': 'ULS1',
                            'editor_stage': 1,
                            'limit_state': 'STRENGTH',
                            'combination_type': 'GEN',
                            'expression': '1.2(D) + 1.6(L)',
                            'entry_rows': [
                                {'reference_kind': 'ST', 'reference_name': 'DEAD', 'factor': 1.2},
                                {'reference_kind': 'ST', 'reference_name': 'LIVE', 'factor': 1.6},
                            ],
                        },
                        {
                            'name': 'ENV1',
                            'editor_stage': 2,
                            'limit_state': 'ACTIVE',
                            'combination_type': 'GEN',
                            'expression': 'Envelope refs ULS1',
                            'entry_rows': [
                                {'reference_kind': 'CB', 'reference_name': 'ULS1', 'factor': 1.0},
                            ],
                        },
                    ],
                }
            },
        }
    }

    report = module.build_roundtrip_report(model_payload=payload, source_path='fixture.json')

    assert report['supported'] is True
    assert report['pass'] is True
    assert report['exact_name_coverage'] == 1.0
    assert report['exact_entry_row_coverage'] == 1.0
    assert report['exact_header_coverage'] == 1.0
    assert report['missing_combo_names'] == []
    assert report['extra_combo_names'] == []


def test_compare_midas_loadcomb_roundtrip_detects_entry_mismatch() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / 'implementation/phase1/compare_midas_loadcomb_roundtrip.py',
        'compare_midas_loadcomb_roundtrip_test_mismatch',
    )
    payload = {
        'model': {
            'load_combinations_raw': [
                'NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0',
                'ST, DEAD, 1.2, ST, LIVE, 1.6',
            ],
            'metadata': {
                'load_combination_editor_seed': {
                    'summary': {'combination_count': 1},
                    'combination_nodes': [
                        {
                            'name': 'ULS1',
                            'editor_stage': 1,
                            'limit_state': 'STRENGTH',
                            'combination_type': 'GEN',
                            'expression': '1.2(D) + 1.5(L)',
                            'entry_rows': [
                                {'reference_kind': 'ST', 'reference_name': 'DEAD', 'factor': 1.2},
                                {'reference_kind': 'ST', 'reference_name': 'LIVE', 'factor': 1.5},
                            ],
                        },
                    ],
                }
            },
        }
    }

    report = module.build_roundtrip_report(model_payload=payload, source_path='fixture.json')

    assert report['supported'] is True
    assert report['pass'] is False
    assert report['exact_entry_row_coverage'] == 0.0
    assert report['mismatched_entry_names'] == ['ULS1']
