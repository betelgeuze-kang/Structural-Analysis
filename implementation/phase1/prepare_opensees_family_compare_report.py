from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_BRIDGE_DIR = REPO_ROOT / 'implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix'
FRAME_BRIDGE_DIR = REPO_ROOT / 'implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b'
OUTPUT_JSON = REPO_ROOT / 'implementation/phase1/release/benchmark_expansion/opensees_scbf_family_compare.json'
OUTPUT_MD = REPO_ROOT / 'implementation/phase1/release/benchmark_expansion/opensees_scbf_family_compare.md'


def _load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as fp:
        data = json.load(fp)
    return data if isinstance(data, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _element_ids(model_payload: dict[str, Any]) -> set[str]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else {}
    rows = model.get('elements') if isinstance(model.get('elements'), list) else []
    return {str(row.get('id', '') or '') for row in rows if isinstance(row, dict) and str(row.get('id', '') or '')}


def _node_ids(model_payload: dict[str, Any]) -> set[int]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else {}
    rows = model.get('nodes') if isinstance(model.get('nodes'), list) else []
    return {_safe_int(row.get('id')) for row in rows if isinstance(row, dict)}


def _histogram_value(histogram: dict[str, Any], key: str) -> int:
    if not isinstance(histogram, dict):
        return 0
    return _safe_int(histogram.get(key, 0))


def _node_map(model_payload: dict[str, Any]) -> dict[int, tuple[float, float, float]]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else {}
    rows = model.get('nodes') if isinstance(model.get('nodes'), list) else []
    mapping: dict[int, tuple[float, float, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        node_id = _safe_int(row.get('id'))
        mapping[node_id] = (
            float(row.get('x', 0.0) or 0.0),
            float(row.get('y', 0.0) or 0.0),
            float(row.get('z', 0.0) or 0.0),
        )
    return mapping


def _element_rows(model_payload: dict[str, Any]) -> list[dict[str, Any]]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else {}
    rows = model.get('elements') if isinstance(model.get('elements'), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _element_lookup(model_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get('id', '') or ''): row
        for row in _element_rows(model_payload)
        if str(row.get('id', '') or '')
    }


def _element_node_ids(row: dict[str, Any]) -> list[int]:
    node_ids = row.get('node_ids') if isinstance(row.get('node_ids'), list) else []
    return [_safe_int(node_id) for node_id in node_ids]


def _element_level_signature(
    row: dict[str, Any],
    node_map: dict[int, tuple[float, float, float]],
) -> tuple[float, ...]:
    return tuple(
        sorted(
            {
                round(float(node_map[node_id][2]), 6)
                for node_id in _element_node_ids(row)
                if node_id in node_map
            }
        )
    )


def _shared_frame_contract(
    shell_model: dict[str, Any],
    frame_model: dict[str, Any],
) -> dict[str, Any]:
    shell_node_map = _node_map(shell_model)
    frame_node_map = _node_map(frame_model)
    shell_element_lookup = _element_lookup(shell_model)
    frame_element_lookup = _element_lookup(frame_model)

    shell_node_ids = set(shell_node_map)
    frame_node_ids = set(frame_node_map)
    shell_element_ids = set(shell_element_lookup)
    frame_element_ids = set(frame_element_lookup)
    shared_element_ids = shell_element_ids & frame_element_ids

    frame_nodes_preserved = frame_node_ids.issubset(shell_node_ids)
    frame_elements_preserved = frame_element_ids.issubset(shell_element_ids)
    shared_node_coordinates_match = frame_nodes_preserved and all(
        shell_node_map[node_id] == frame_node_map[node_id]
        for node_id in frame_node_ids
    )

    shared_element_connectivity_match = frame_elements_preserved
    shared_frame_story_signature_match = frame_elements_preserved
    for element_id in frame_element_ids:
        shell_row = shell_element_lookup.get(element_id)
        frame_row = frame_element_lookup.get(element_id)
        if not isinstance(shell_row, dict) or not isinstance(frame_row, dict):
            shared_element_connectivity_match = False
            shared_frame_story_signature_match = False
            continue
        shell_node_ids_for_element = _element_node_ids(shell_row)
        frame_node_ids_for_element = _element_node_ids(frame_row)
        if shell_node_ids_for_element != frame_node_ids_for_element:
            shared_element_connectivity_match = False
        if _element_level_signature(shell_row, shell_node_map) != _element_level_signature(frame_row, frame_node_map):
            shared_frame_story_signature_match = False

    shared_frame_match = bool(
        frame_nodes_preserved
        and frame_elements_preserved
        and shared_node_coordinates_match
        and shared_element_connectivity_match
        and shared_frame_story_signature_match
    )
    return {
        'frame_nodes_preserved': frame_nodes_preserved,
        'frame_elements_preserved': frame_elements_preserved,
        'shared_node_coordinates_match': shared_node_coordinates_match,
        'shared_element_connectivity_match': shared_element_connectivity_match,
        'shared_frame_story_signature_match': shared_frame_story_signature_match,
        'shared_frame_match': shared_frame_match,
        'shared_element_ids': shared_element_ids,
    }


def _point_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), max(xs), min(ys), max(ys)


def _family_compare_geometry(
    shell_model: dict[str, Any],
    *,
    shared_element_ids: set[str],
    shell_only_element_ids: set[str],
) -> dict[str, Any]:
    nodes = _node_map(shell_model)
    elements = _element_rows(shell_model)
    points: list[tuple[float, float]] = []
    shared_segments: list[dict[str, Any]] = []
    shell_only_faces: list[dict[str, Any]] = []

    for row in elements:
        element_id = str(row.get('id', '') or '')
        node_ids = [int(item) for item in (row.get('node_ids') or []) if _safe_int(item) in nodes]
        story_band = _safe_int(row.get('story_band'))
        zone_label = str(row.get('zone_label', '') or 'unknown')
        source_element_type = str(row.get('source_element_type', '') or 'unknown')
        family = str(row.get('family', '') or 'unknown')
        group_id = str(row.get('group_id', '') or 'unknown')
        if element_id in shell_only_element_ids and len(node_ids) >= 3:
            face_points = [(float(nodes[node_id][0]), float(nodes[node_id][2])) for node_id in node_ids]
            points.extend(face_points)
            centroid_x = sum(point[0] for point in face_points) / len(face_points)
            centroid_y = sum(point[1] for point in face_points) / len(face_points)
            shell_only_faces.append(
                {
                    'element_id': element_id,
                    'story_band': story_band,
                    'story_band_label': f"S{story_band:02d}" if story_band > 0 else 'unknown',
                    'zone_label': zone_label,
                    'group_id': group_id,
                    'family': family,
                    'source_element_type': source_element_type,
                    'node_ids': node_ids,
                    'centroid': [round(centroid_x, 6), round(centroid_y, 6)],
                    'points_xz': [[round(point[0], 6), round(point[1], 6)] for point in face_points],
                }
            )
            continue
        if element_id not in shared_element_ids or len(node_ids) < 2:
            continue
        for start_node, end_node in zip(node_ids, node_ids[1:]):
            p1 = (float(nodes[start_node][0]), float(nodes[start_node][2]))
            p2 = (float(nodes[end_node][0]), float(nodes[end_node][2]))
            points.extend([p1, p2])
            shared_segments.append(
                {
                    'element_id': element_id,
                    'story_band': story_band,
                    'story_band_label': f"S{story_band:02d}" if story_band > 0 else 'unknown',
                    'zone_label': zone_label,
                    'group_id': group_id,
                    'family': family,
                    'source_element_type': source_element_type,
                    'points_xz': [
                        [round(p1[0], 6), round(p1[1], 6)],
                        [round(p2[0], 6), round(p2[1], 6)],
                    ],
                }
            )

    if not points:
        return {'shared_segments': [], 'shell_only_faces': [], 'bounds': {}, 'story_bands': []}
    min_x, max_x, min_y, max_y = _point_bounds(points)
    story_bands = sorted(
        {
            str(row.get('story_band_label', '') or 'unknown')
            for row in [*shared_segments, *shell_only_faces]
            if str(row.get('story_band_label', '') or 'unknown')
        },
        key=lambda label: _safe_int(str(label).lstrip('S')),
    )
    return {
        'shared_segments': shared_segments,
        'shell_only_faces': shell_only_faces,
        'bounds': {
            'min_x': round(min_x, 6),
            'max_x': round(max_x, 6),
            'min_y': round(min_y, 6),
            'max_y': round(max_y, 6),
        },
        'story_bands': story_bands,
    }


def _family_compare_svg(
    compare_geometry: dict[str, Any],
    *,
    width: int = 620,
    height: int = 360,
) -> str:
    shared_segments = compare_geometry.get('shared_segments') if isinstance(compare_geometry.get('shared_segments'), list) else []
    shell_only_faces = compare_geometry.get('shell_only_faces') if isinstance(compare_geometry.get('shell_only_faces'), list) else []
    points: list[tuple[float, float]] = []
    for row in shared_segments:
        segment_points = row.get('points_xz') if isinstance(row, dict) else []
        if isinstance(segment_points, list) and len(segment_points) >= 2:
            points.extend(
                (float(point[0]), float(point[1]))
                for point in segment_points[:2]
                if isinstance(point, list) and len(point) >= 2
            )
    for row in shell_only_faces:
        face_points = row.get('points_xz') if isinstance(row, dict) else []
        if isinstance(face_points, list):
            points.extend(
                (float(point[0]), float(point[1]))
                for point in face_points
                if isinstance(point, list) and len(point) >= 2
            )
    if not points:
        return ''
    min_x, max_x, min_y, max_y = _point_bounds(points)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    padding = 28.0
    scale = min((width - 2 * padding) / span_x, (height - 2 * padding) / span_y)
    offset_x = (width - span_x * scale) / 2.0
    offset_y = (height - span_y * scale) / 2.0

    def _map(point: tuple[float, float]) -> tuple[float, float]:
        px = offset_x + (point[0] - min_x) * scale
        py = height - (offset_y + (point[1] - min_y) * scale)
        return round(px, 2), round(py, 2)

    grid = []
    for ratio in [0.2, 0.4, 0.6, 0.8]:
        y = round(padding + (height - 2 * padding) * ratio, 2)
        x = round(padding + (width - 2 * padding) * ratio, 2)
        grid.append(f"<line x1='{padding}' y1='{y}' x2='{width - padding}' y2='{y}' stroke='rgba(125,134,145,0.10)'/>")
        grid.append(f"<line x1='{x}' y1='{padding}' x2='{x}' y2='{height - padding}' stroke='rgba(125,134,145,0.10)'/>")

    shared_lines = []
    for row in shared_segments:
        points_xz = row.get('points_xz') if isinstance(row, dict) else []
        if not isinstance(points_xz, list) or len(points_xz) < 2:
            continue
        p1 = (float(points_xz[0][0]), float(points_xz[0][1]))
        p2 = (float(points_xz[1][0]), float(points_xz[1][1]))
        x1, y1 = _map(p1)
        x2, y2 = _map(p2)
        shared_lines.append(
            f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='rgba(120,126,135,0.30)' stroke-width='2.4' stroke-linecap='round'/>"
        )
    shell_faces_markup = []
    for row in shell_only_faces:
        face_points = row.get('points_xz') if isinstance(row, dict) else []
        if not isinstance(face_points, list) or len(face_points) < 3:
            continue
        polygon_points = ' '.join(
            f"{_map((float(point[0]), float(point[1])))[0]},{_map((float(point[0]), float(point[1])))[1]}"
            for point in face_points
            if isinstance(point, list) and len(point) >= 2
        )
        shell_faces_markup.append(
            f"<polygon points='{polygon_points}' fill='rgba(217,111,50,0.22)' stroke='#c46b2d' stroke-width='3.8' stroke-linejoin='round' opacity='0.98'/>"
        )

    return (
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='OpenSees family compare overlay' class='overlay-svg'>"
        f"<rect x='0' y='0' width='{width}' height='{height}' rx='18' fill='#fffdf8' stroke='#d8cfbf'/>"
        f"<rect x='18' y='18' width='{width - 36}' height='{height - 36}' rx='16' fill='rgba(245,239,228,0.78)' stroke='rgba(162,146,120,0.20)'/>"
        f"{''.join(grid)}"
        f"{''.join(shared_lines)}"
        f"{''.join(shell_faces_markup)}"
        "<text x='26' y='34' fill='#2c3b4f' font-size='16' font-weight='700'>Shared frame + shell-only delta</text>"
        "<text x='26' y='54' fill='#667085' font-size='12'>gray=shared frame | orange=shell-only slab panel traces</text>"
        "</svg>"
    )


def build_report() -> dict[str, Any]:
    shell_report = _load_json(SHELL_BRIDGE_DIR / 'bridge_report.json')
    frame_report = _load_json(FRAME_BRIDGE_DIR / 'bridge_report.json')
    shell_model = _load_json(SHELL_BRIDGE_DIR / 'model.json')
    frame_model = _load_json(FRAME_BRIDGE_DIR / 'model.json')

    shell_summary = shell_report.get('summary') if isinstance(shell_report.get('summary'), dict) else {}
    frame_summary = frame_report.get('summary') if isinstance(frame_report.get('summary'), dict) else {}
    shell_metrics = shell_model.get('topology_metrics') if isinstance(shell_model.get('topology_metrics'), dict) else {}
    frame_metrics = frame_model.get('topology_metrics') if isinstance(frame_model.get('topology_metrics'), dict) else {}

    shell_nodes = _node_ids(shell_model)
    frame_nodes = _node_ids(frame_model)
    shared_nodes = shell_nodes & frame_nodes
    shell_only_nodes = sorted(shell_nodes - frame_nodes)
    frame_only_nodes = sorted(frame_nodes - shell_nodes)

    shell_elements = _element_ids(shell_model)
    frame_elements = _element_ids(frame_model)
    shared_frame_contract = _shared_frame_contract(shell_model, frame_model)
    shared_elements = shared_frame_contract['shared_element_ids']
    shell_only_elements = sorted(shell_elements - frame_elements)
    frame_only_elements = sorted(frame_elements - shell_elements)
    shell_element_lookup = _element_lookup(shell_model)

    shell_class_hist = shell_metrics.get('element_class_histogram') if isinstance(shell_metrics.get('element_class_histogram'), dict) else {}
    frame_class_hist = frame_metrics.get('element_class_histogram') if isinstance(frame_metrics.get('element_class_histogram'), dict) else {}
    shell_type_hist = shell_metrics.get('element_type_histogram') if isinstance(shell_metrics.get('element_type_histogram'), dict) else {}
    frame_type_hist = frame_metrics.get('element_type_histogram') if isinstance(frame_metrics.get('element_type_histogram'), dict) else {}

    shell_slab_count = _histogram_value(shell_class_hist, 'slab')
    frame_slab_count = _histogram_value(frame_class_hist, 'slab')
    shell_shellmitc4_count = _histogram_value(shell_type_hist, 'ShellMITC4')
    frame_shellmitc4_count = _histogram_value(frame_type_hist, 'ShellMITC4')

    raw_node_sets_match = shell_nodes == frame_nodes
    raw_story_band_count_match = _safe_int(shell_metrics.get('story_band_count')) == _safe_int(frame_metrics.get('story_band_count'))
    node_sets_match = bool(
        shared_frame_contract['frame_nodes_preserved']
        and shared_frame_contract['shared_node_coordinates_match']
    )
    story_band_match = bool(shared_frame_contract['shared_frame_story_signature_match'])
    shared_frame_element_match = bool(
        shared_frame_contract['frame_elements_preserved']
        and shared_frame_contract['shared_element_connectivity_match']
    )
    viewer_ready = bool(shell_summary.get('viewer_ready', False)) and bool(frame_summary.get('viewer_ready', False))
    contract_pass = bool(
        viewer_ready
        and node_sets_match
        and shared_frame_element_match
        and story_band_match
        and not frame_only_elements
    )

    focus_label = f"shared frame + {shell_shellmitc4_count} shell slab panels"
    detail_note = (
        "두 OpenSees baseline은 shared frame을 바탕으로 비교하고, "
        f"shell-beam mix가 shell-only node {len(shell_only_nodes)}개와 element {len(shell_only_elements)}개를 더하지만 "
        f"ShellMITC4 slab {shell_shellmitc4_count}개를 포함한 enrichment로 읽는 family compare입니다."
    )
    summary = {
        'family_id': 'opensees_scbf16b_family',
        'shell_mix_profile_label': str(shell_summary.get('source_profile_label', '') or 'shell-beam mix'),
        'frame_profile_label': str(frame_summary.get('source_profile_label', '') or 'frame-brace mix'),
        'shared_node_count': len(shared_nodes),
        'node_sets_match': node_sets_match,
        'raw_node_sets_match': raw_node_sets_match,
        'shared_frame_node_coverage_pass': bool(shared_frame_contract['frame_nodes_preserved']),
        'shared_frame_coordinate_match': bool(shared_frame_contract['shared_node_coordinates_match']),
        'shared_element_count': len(shared_elements),
        'shared_frame_element_match': shared_frame_element_match,
        'shell_mix_only_element_count': len(shell_only_elements),
        'frame_only_element_count': len(frame_only_elements),
        'story_band_match': story_band_match,
        'raw_story_band_count_match': raw_story_band_count_match,
        'shared_frame_story_signature_match': bool(shared_frame_contract['shared_frame_story_signature_match']),
        'shell_mix_slab_count': shell_slab_count,
        'frame_slab_count': frame_slab_count,
        'shell_mix_shellmitc4_count': shell_shellmitc4_count,
        'frame_shellmitc4_count': frame_shellmitc4_count,
        'focus_label': focus_label,
        'detail_note': detail_note,
    }
    compare_rows = [
        {
            'dimension': 'node set',
            'shell_beam_mix': len(shell_nodes),
            'frame_brace': len(frame_nodes),
            'difference': (
                'same'
                if raw_node_sets_match
                else f'frame preserved | shell_only={len(shell_only_nodes)} | frame_only={len(frame_only_nodes)}'
            ),
            'reading_note': 'shell-beam mix는 shell discretization node를 더 가질 수 있으므로, readiness는 shared frame node 좌표가 유지되는지로 읽습니다.',
        },
        {
            'dimension': 'story bands',
            'shell_beam_mix': _safe_int(shell_metrics.get('story_band_count')),
            'frame_brace': _safe_int(frame_metrics.get('story_band_count')),
            'difference': (
                'same'
                if raw_story_band_count_match
                else 'shared frame preserved | shell refinement present'
            ),
            'reading_note': 'shell meshing은 더 촘촘한 story-band index를 만들 수 있으므로, readiness는 raw count 대신 shared frame vertical signature를 기준으로 읽습니다.',
        },
        {
            'dimension': 'shared frame elements',
            'shell_beam_mix': len(shared_elements),
            'frame_brace': len(shared_elements),
            'difference': f'shared={len(shared_elements)}',
            'reading_note': 'shared element는 두 source가 공통으로 갖는 frame/bracing 골격입니다.',
        },
        {
            'dimension': 'shell/slab enrichment',
            'shell_beam_mix': shell_shellmitc4_count,
            'frame_brace': frame_shellmitc4_count,
            'difference': f'+{shell_shellmitc4_count} shell slab panels',
            'reading_note': 'shell-beam mix만 slab shell panel을 갖습니다. frame-brace baseline에는 이 면요소가 없습니다.',
        },
    ]
    shell_only_rows = []
    for element_id in shell_only_elements:
        element = shell_element_lookup.get(str(element_id), {})
        source_element_type = str(element.get('source_element_type', '') or 'unknown')
        family = str(element.get('family', '') or 'unknown')
        if source_element_type != 'ShellMITC4' and family != 'slab':
            continue
        story_band = _safe_int(element.get('story_band'))
        shell_only_rows.append(
            {
                'element_id': str(element_id),
                'story_band': story_band,
                'story_band_label': f"S{story_band:02d}" if story_band > 0 else 'unknown',
                'zone_label': str(element.get('zone_label', '') or 'unknown'),
                'group_id': str(element.get('group_id', '') or 'unknown'),
                'source_element_type': source_element_type,
                'node_ids': [int(node_id) for node_id in (element.get('node_ids') or [])],
                'family': family if family != 'unknown' else 'slab',
            }
        )
    compare_geometry = _family_compare_geometry(
        shell_model,
        shared_element_ids=shared_elements,
        shell_only_element_ids=set(shell_only_elements),
    )
    compare_svg = _family_compare_svg(compare_geometry)
    return {
        'schema_version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'report_family': 'opensees_scbf_family_compare',
        'contract_pass': contract_pass,
        'reason_code': 'FAMILY_COMPARE_READY' if contract_pass else 'FAMILY_COMPARE_PARTIAL',
        'summary': summary,
        'compare_mode': 'lightweight_svg',
        'compare_rows': compare_rows,
        'story_options': compare_geometry.get('story_bands', []),
        'shell_only_rows': shell_only_rows,
        'compare_geometry': compare_geometry,
        'compare_svg': compare_svg,
        'shell_mix_only_element_ids': shell_only_elements,
        'frame_only_element_ids': frame_only_elements,
        'shell_only_node_ids': shell_only_nodes,
        'frame_only_node_ids': frame_only_nodes,
    }


def write_outputs(report: dict[str, Any]) -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = report.get('summary') if isinstance(report.get('summary'), dict) else {}
    markdown = '\n'.join(
        [
            '# OpenSees SCBF Family Compare',
            '',
            f"- reason_code: `{report.get('reason_code', 'n/a')}`",
            f"- contract_pass: `{str(bool(report.get('contract_pass', False))).lower()}`",
            f"- focus: `{summary.get('focus_label', 'n/a')}`",
            f"- shared_node_count: `{summary.get('shared_node_count', 0)}`",
            f"- shared_element_count: `{summary.get('shared_element_count', 0)}`",
            f"- shell_mix_only_element_count: `{summary.get('shell_mix_only_element_count', 0)}`",
            f"- frame_only_element_count: `{summary.get('frame_only_element_count', 0)}`",
            f"- shell_only_ids: `{', '.join(str(item) for item in report.get('shell_mix_only_element_ids', [])) or 'n/a'}`",
            '',
            str(summary.get('detail_note', '') or ''),
        ]
    ).strip() + '\n'
    OUTPUT_MD.write_text(markdown, encoding='utf-8')


def main() -> None:
    report = build_report()
    write_outputs(report)
    print(f'Wrote OpenSees family compare report: {OUTPUT_JSON}')


if __name__ == '__main__':
    main()
