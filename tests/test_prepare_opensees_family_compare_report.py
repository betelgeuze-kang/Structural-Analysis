from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1 import prepare_opensees_family_compare_report as family_compare


def _write_bridge_fixture(
    bridge_dir: Path,
    *,
    source_profile_label: str,
    viewer_ready: bool,
    nodes: list[dict[str, float | int]],
    elements: list[dict[str, object]],
    story_band_count: int,
    slab_count: int = 0,
    shellmitc4_count: int = 0,
) -> None:
    bridge_dir.mkdir(parents=True, exist_ok=True)
    (bridge_dir / 'bridge_report.json').write_text(
        json.dumps(
            {
                'summary': {
                    'viewer_ready': viewer_ready,
                    'source_profile_label': source_profile_label,
                }
            }
        ),
        encoding='utf-8',
    )
    (bridge_dir / 'model.json').write_text(
        json.dumps(
            {
                'model': {
                    'nodes': nodes,
                    'elements': elements,
                },
                'topology_metrics': {
                    'story_band_count': story_band_count,
                    'element_class_histogram': {'slab': slab_count},
                    'element_type_histogram': {'ShellMITC4': shellmitc4_count},
                },
            }
        ),
        encoding='utf-8',
    )


def _shared_frame_nodes() -> list[dict[str, float | int]]:
    return [
        {'id': 1, 'x': 0.0, 'y': 0.0, 'z': 0.0},
        {'id': 2, 'x': 0.0, 'y': 0.0, 'z': 3.0},
        {'id': 3, 'x': 4.0, 'y': 0.0, 'z': 3.0},
    ]


def _shared_frame_elements(*, beam_node_ids: list[int]) -> list[dict[str, object]]:
    return [
        {
            'id': 'E1',
            'node_ids': [1, 2],
            'story_band': 1,
            'zone_label': 'core',
            'group_id': 'S01:core:column',
            'family': 'column',
            'source_element_type': 'elasticBeamColumn',
        },
        {
            'id': 'E2',
            'node_ids': beam_node_ids,
            'story_band': 1,
            'zone_label': 'perimeter',
            'group_id': 'S01:perimeter:beam',
            'family': 'beam',
            'source_element_type': 'elasticBeamColumn',
        },
    ]

def test_build_report_recovers_shared_frame_and_shell_delta() -> None:
    report = family_compare.build_report()

    assert report['reason_code'] == 'FAMILY_COMPARE_READY'
    assert report['contract_pass'] is True

    summary = report['summary']
    assert summary['family_id'] == 'opensees_scbf16b_family'
    assert summary['node_sets_match'] is True
    assert summary['raw_node_sets_match'] is False
    assert summary['shared_frame_node_coverage_pass'] is True
    assert summary['shared_frame_coordinate_match'] is True
    assert summary['story_band_match'] is True
    assert summary['raw_story_band_count_match'] is False
    assert summary['shared_frame_story_signature_match'] is True
    assert summary['shared_node_count'] == 134
    assert summary['shared_element_count'] == 50
    assert summary['shared_frame_element_match'] is True
    assert summary['shell_mix_only_element_count'] == 139
    assert summary['frame_only_element_count'] == 0
    assert summary['shell_mix_shellmitc4_count'] == 5
    assert summary['frame_shellmitc4_count'] == 0
    assert 'shell-only node 318개와 element 139개' in summary['detail_note']

    compare_rows = report['compare_rows']
    shell_only_rows = report['shell_only_rows']
    assert compare_rows[0]['difference'] == 'frame preserved | shell_only=318 | frame_only=0'
    assert compare_rows[1]['difference'] == 'shared frame preserved | shell refinement present'
    assert any(row['dimension'] == 'shell/slab enrichment' for row in compare_rows)
    assert len(shell_only_rows) == 5
    assert shell_only_rows[0]['element_id'] == '990001'
    assert shell_only_rows[-1]['element_id'] == '990005'
    assert shell_only_rows[0]['story_band'] == 4
    assert shell_only_rows[-1]['story_band'] == 16
    assert shell_only_rows[0]['zone_label'] == 'intermediate'
    assert shell_only_rows[0]['source_element_type'] == 'ShellMITC4'
    assert 'Shared frame + shell-only delta' in report['compare_svg']
    assert 'orange=shell-only slab panel traces' in report['compare_svg']
    assert len(report['shell_mix_only_element_ids']) == 139
    assert report['shell_mix_only_element_ids'][:3] == ['4101100', '4102100', '4103100']
    assert report['shell_mix_only_element_ids'][-5:] == ['990001', '990002', '990003', '990004', '990005']


def test_build_report_accepts_shell_only_enrichment_when_shared_frame_is_preserved(
    monkeypatch,
    tmp_path: Path,
) -> None:
    shell_dir = tmp_path / 'shell'
    frame_dir = tmp_path / 'frame'
    frame_nodes = _shared_frame_nodes()
    shell_nodes = [*frame_nodes, {'id': 4, 'x': 2.0, 'y': 0.0, 'z': 3.0}]

    _write_bridge_fixture(
        frame_dir,
        source_profile_label='frame-brace mix',
        viewer_ready=True,
        nodes=frame_nodes,
        elements=_shared_frame_elements(beam_node_ids=[2, 3]),
        story_band_count=1,
    )
    _write_bridge_fixture(
        shell_dir,
        source_profile_label='shell-beam mix',
        viewer_ready=True,
        nodes=shell_nodes,
        elements=[
            *_shared_frame_elements(beam_node_ids=[2, 3]),
            {
                'id': 'S1',
                'node_ids': [2, 4, 3],
                'story_band': 10,
                'zone_label': 'intermediate',
                'group_id': 'S10:intermediate:slab',
                'family': 'slab',
                'source_element_type': 'ShellMITC4',
            },
        ],
        story_band_count=3,
        slab_count=1,
        shellmitc4_count=1,
    )

    monkeypatch.setattr(family_compare, 'SHELL_BRIDGE_DIR', shell_dir)
    monkeypatch.setattr(family_compare, 'FRAME_BRIDGE_DIR', frame_dir)

    report = family_compare.build_report()

    assert report['reason_code'] == 'FAMILY_COMPARE_READY'
    assert report['contract_pass'] is True
    assert report['summary']['node_sets_match'] is True
    assert report['summary']['raw_node_sets_match'] is False
    assert report['summary']['story_band_match'] is True
    assert report['summary']['raw_story_band_count_match'] is False
    assert report['summary']['shell_mix_only_element_count'] == 1
    assert report['shell_only_rows'][0]['element_id'] == 'S1'


def test_build_report_rejects_shared_frame_connectivity_change(
    monkeypatch,
    tmp_path: Path,
) -> None:
    shell_dir = tmp_path / 'shell'
    frame_dir = tmp_path / 'frame'
    frame_nodes = _shared_frame_nodes()
    shell_nodes = [*frame_nodes, {'id': 4, 'x': 2.0, 'y': 0.0, 'z': 6.0}]

    _write_bridge_fixture(
        frame_dir,
        source_profile_label='frame-brace mix',
        viewer_ready=True,
        nodes=frame_nodes,
        elements=_shared_frame_elements(beam_node_ids=[2, 3]),
        story_band_count=1,
    )
    _write_bridge_fixture(
        shell_dir,
        source_profile_label='shell-beam mix',
        viewer_ready=True,
        nodes=shell_nodes,
        elements=[
            *_shared_frame_elements(beam_node_ids=[2, 4]),
            {
                'id': 'S1',
                'node_ids': [2, 4, 3],
                'story_band': 10,
                'zone_label': 'intermediate',
                'group_id': 'S10:intermediate:slab',
                'family': 'slab',
                'source_element_type': 'ShellMITC4',
            },
        ],
        story_band_count=3,
        slab_count=1,
        shellmitc4_count=1,
    )

    monkeypatch.setattr(family_compare, 'SHELL_BRIDGE_DIR', shell_dir)
    monkeypatch.setattr(family_compare, 'FRAME_BRIDGE_DIR', frame_dir)

    report = family_compare.build_report()

    assert report['reason_code'] == 'FAMILY_COMPARE_PARTIAL'
    assert report['contract_pass'] is False
    assert report['summary']['node_sets_match'] is True
    assert report['summary']['shared_frame_element_match'] is False
    assert report['summary']['story_band_match'] is False
