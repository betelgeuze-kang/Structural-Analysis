#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_MODEL = Path('implementation/phase1/open_data/midas/midas_generator_33.json')
DEFAULT_CODECHECK_REPORT = Path('implementation/phase1/release/kds_compliance/code_check_report.json')
DEFAULT_BENCHMARK_CASES = Path('implementation/phase1/commercial_benchmark_cases.from_csv.json')
DEFAULT_OUT = Path('implementation/phase1/open_data/midas/kds_geometry_bridge_registry.exact.json')


REVIEWED_FOCUS_MAP: dict[str, dict[str, str]] = {
    'C-TRN-001': {'baseline_focus_member_id': '26878', 'selector_kind': 'x_beam_exact_focus', 'surrogate_geometry_kind': 'x_beam'},
    'C-TRN-002': {'baseline_focus_member_id': '27287', 'selector_kind': 'plan_diagonal_exact_focus', 'surrogate_geometry_kind': 'plan_diagonal'},
    'C-TRN-003': {'baseline_focus_member_id': '26878', 'selector_kind': 'x_beam_exact_focus', 'surrogate_geometry_kind': 'x_beam'},
    'C-TRN-004': {'baseline_focus_member_id': '27425', 'selector_kind': 'vertical_wall_frame_exact_focus', 'surrogate_geometry_kind': 'vertical'},
    'C-TRN-005': {'baseline_focus_member_id': '27441', 'selector_kind': 'vertical_outrigger_exact_focus', 'surrogate_geometry_kind': 'vertical'},
    'C-TRN-006': {'baseline_focus_member_id': '27287', 'selector_kind': 'plan_diagonal_exact_focus', 'surrogate_geometry_kind': 'plan_diagonal'},
    'C-TRN-007': {'baseline_focus_member_id': '27425', 'selector_kind': 'vertical_wall_frame_exact_focus', 'surrogate_geometry_kind': 'vertical'},
    'C-VAL-001': {'baseline_focus_member_id': '26878', 'selector_kind': 'x_beam_exact_focus', 'surrogate_geometry_kind': 'x_beam'},
    'C-VAL-002': {'baseline_focus_member_id': '27287', 'selector_kind': 'plan_diagonal_exact_focus', 'surrogate_geometry_kind': 'plan_diagonal'},
    'C-TST-001': {'baseline_focus_member_id': '27441', 'selector_kind': 'vertical_outrigger_exact_focus', 'surrogate_geometry_kind': 'vertical'},
    'C-TST-002': {'baseline_focus_member_id': '27425', 'selector_kind': 'vertical_wall_frame_exact_focus', 'surrogate_geometry_kind': 'vertical'},
    'C-TST-003': {'baseline_focus_member_id': '27441', 'selector_kind': 'vertical_outrigger_exact_focus', 'surrogate_geometry_kind': 'vertical'},
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path} does not contain a JSON object')
    return payload


def _build_element_lookup(model_payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else model_payload
    elements = {str(row.get('id')): row for row in (model.get('elements') or []) if isinstance(row, dict) and row.get('id') is not None}
    nodes = {int(row.get('id')): row for row in (model.get('nodes') or []) if isinstance(row, dict) and row.get('id') is not None}
    return elements, nodes


def _build_member_lookup(model_payload: dict[str, Any]) -> dict[str, str]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else model_payload
    metadata = model.get('metadata') if isinstance(model.get('metadata'), dict) else {}
    member_rows = [row for row in (metadata.get('members') or []) if isinstance(row, dict)]
    lookup: dict[str, str] = {}
    for row in member_rows:
        aggregate_id = str(row.get('id', '') or '').strip()
        if not aggregate_id:
            continue
        element_seed = str(row.get('element_seed', '') or '').strip()
        if element_seed:
            lookup.setdefault(element_seed, aggregate_id)
        for element_id in (str(item).strip() for item in (row.get('element_ids') or []) if str(item).strip()):
            lookup.setdefault(element_id, aggregate_id)
    return lookup


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _case_row_groups(code_check_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in (code_check_report.get('member_check_rows') or []):
        if not isinstance(row, dict):
            continue
        case_id = str(row.get('case_id', '') or row.get('member_id', '')).strip()
        if not case_id:
            continue
        groups.setdefault(case_id, []).append(dict(row))
    return groups


def _row_sort_key(row: dict[str, Any]) -> tuple[float, str, str, str]:
    try:
        dcr = float(row.get('dcr', 0.0) or 0.0)
    except (TypeError, ValueError):
        dcr = 0.0
    return (
        -dcr,
        str(row.get('combination', '') or ''),
        str(row.get('component', '') or ''),
        str(row.get('clause', '') or ''),
    )


def _top_row_label(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return 'n/a'
    top_row = sorted(rows, key=_row_sort_key)[0]
    try:
        dcr = float(top_row.get('dcr', 0.0) or 0.0)
    except (TypeError, ValueError):
        dcr = 0.0
    return (
        f"{str(top_row.get('combination', '') or '').strip()} | "
        f"{str(top_row.get('component', '') or '').strip()} | "
        f"{str(top_row.get('clause', '') or '').strip()} | "
        f"D/C={dcr:.3f}"
    )


def _model_member_handle_inventory(model_payload: dict[str, Any]) -> tuple[set[str], str]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else model_payload
    metadata = model.get('metadata') if isinstance(model.get('metadata'), dict) else {}
    member_rows = [row for row in (metadata.get('members') or []) if isinstance(row, dict)]
    member_handles = {
        str(row.get('id', '') or '').strip()
        for row in member_rows
        if str(row.get('id', '') or '').strip()
    }
    if member_handles:
        return member_handles, 'aggregate_member_id'
    element_handles = {
        str(row.get('id', '') or '').strip()
        for row in (model.get('elements') or [])
        if isinstance(row, dict) and str(row.get('id', '') or '').strip()
    }
    return element_handles, 'element_id'


def _classify_element_kind(dx: float, dy: float, dz: float) -> str:
    adx, ady, adz = abs(dx), abs(dy), abs(dz)
    horiz = math.hypot(dx, dy)
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1.0e-9:
        return 'point'
    if adz / length > 0.85 and horiz / length < 0.3:
        return 'vertical'
    if adz / length < 0.15 and horiz / length > 0.85:
        if horiz <= 1.0e-9:
            return 'point'
        if adx / horiz > 0.85:
            return 'x_beam'
        if ady / horiz > 0.85:
            return 'y_beam'
        return 'plan_diagonal'
    return 'space_diagonal'


def _full_crosswalk_group_for_kind(kind: str) -> str:
    if kind in {'x_beam', 'y_beam'}:
        return 'horizontal_beam'
    if kind == 'plan_diagonal':
        return 'plan_diagonal'
    if kind == 'vertical':
        return 'vertical'
    return 'other'


def _build_full_crosswalk_inventory(model_payload: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else model_payload
    nodes = {
        int(row.get('id')): row
        for row in (model.get('nodes') or [])
        if isinstance(row, dict) and row.get('id') is not None
    }
    elements = {
        str(row.get('id')): row
        for row in (model.get('elements') or [])
        if isinstance(row, dict) and str(row.get('id', '') or '').strip()
    }
    section_ids_by_group: dict[str, set[str]] = {}
    group_by_element_id: dict[str, str] = {}
    for element_id, row in elements.items():
        node_ids = [int(item) for item in (row.get('node_ids') or []) if isinstance(item, (int, float))]
        kind = 'other'
        if len(node_ids) == 2:
            node0 = nodes.get(node_ids[0])
            node1 = nodes.get(node_ids[1])
            if isinstance(node0, dict) and isinstance(node1, dict):
                kind = _classify_element_kind(
                    float(node1.get('x', 0.0) or 0.0) - float(node0.get('x', 0.0) or 0.0),
                    float(node1.get('y', 0.0) or 0.0) - float(node0.get('y', 0.0) or 0.0),
                    float(node1.get('z', 0.0) or 0.0) - float(node0.get('z', 0.0) or 0.0),
                )
        group = _full_crosswalk_group_for_kind(kind)
        group_by_element_id[element_id] = group
        section_id = str(row.get('section_id', '') or '').strip()
        if section_id:
            section_ids_by_group.setdefault(group, set()).add(section_id)

    member_handles_by_group: dict[str, set[str]] = {}
    metadata = model.get('metadata') if isinstance(model.get('metadata'), dict) else {}
    for row in (metadata.get('members') or []):
        if not isinstance(row, dict):
            continue
        aggregate_id = str(row.get('id', '') or '').strip()
        if not aggregate_id:
            continue
        seed = str(row.get('element_seed', '') or '').strip()
        if not seed:
            for candidate in (str(item).strip() for item in (row.get('element_ids') or []) if str(item).strip()):
                if candidate in group_by_element_id:
                    seed = candidate
                    break
        group = group_by_element_id.get(seed, '')
        if not group:
            continue
        member_handles_by_group.setdefault(group, set()).add(aggregate_id)

    return {
        'member_handles_by_group': {
            group: sorted(values)
            for group, values in sorted(member_handles_by_group.items())
        },
        'section_ids_by_group': {
            group: sorted(values)
            for group, values in sorted(section_ids_by_group.items())
        },
    }


def _selector_full_crosswalk_groups(selector_kind: str) -> tuple[list[str], list[str]]:
    normalized = str(selector_kind or '').strip().lower()
    if 'plan_diagonal' in normalized:
        return ['plan_diagonal'], ['plan_diagonal']
    if 'vertical' in normalized:
        return ['vertical'], ['vertical', 'other']
    if 'x_beam' in normalized:
        return ['horizontal_beam'], ['horizontal_beam']
    return [], []


def _inventory_union(values_by_group: dict[str, list[str]], groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in values_by_group.get(group, []):
            text = str(value or '').strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _model_section_inventory(model_payload: dict[str, Any]) -> set[str]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else model_payload
    return {
        str(row.get('section_id', '') or '').strip()
        for row in (model.get('elements') or [])
        if isinstance(row, dict) and str(row.get('section_id', '') or '').strip()
    }


def _code_check_load_inventory(code_check_report: dict[str, Any]) -> set[str]:
    return {
        str(row.get('combination', '') or '').strip()
        for row in (code_check_report.get('member_check_rows') or [])
        if isinstance(row, dict) and str(row.get('combination', '') or '').strip()
    }


def _crosswalk_status(count: int, expected: int) -> str:
    return 'PASS' if expected == 0 or count >= expected else 'CHECK'


def _mapping_load_names(row: dict[str, Any]) -> set[str]:
    values = row.get('full_crosswalk_load_combination_names')
    if isinstance(values, list):
        return {str(item).strip() for item in values if str(item).strip()}
    values = row.get('row_provenance_combination_names')
    if isinstance(values, list):
        return {str(item).strip() for item in values if str(item).strip()}
    return set()


def _mapping_member_handles(row: dict[str, Any]) -> set[str]:
    if isinstance(row.get('full_crosswalk_member_handles'), list):
        return {
            str(item).strip()
            for item in (row.get('full_crosswalk_member_handles') or [])
            if str(item).strip()
        }
    handle = str(row.get('full_crosswalk_target_member_handle', '') or '').strip()
    if handle:
        return {handle}
    return set()


def _mapping_section_ids(row: dict[str, Any]) -> set[str]:
    if isinstance(row.get('full_crosswalk_section_ids'), list):
        return {
            str(item).strip()
            for item in (row.get('full_crosswalk_section_ids') or [])
            if str(item).strip()
        }
    section_id = str(row.get('full_crosswalk_target_section_id', '') or '').strip()
    if section_id:
        return {section_id}
    return set()


def _registry_full_crosswalk_summary(
    *,
    mappings: list[dict[str, Any]],
    model_payload: dict[str, Any],
    code_check_report: dict[str, Any],
) -> dict[str, Any]:
    expected_member_handles, member_handle_kind = _model_member_handle_inventory(model_payload)
    expected_sections = _model_section_inventory(model_payload)
    expected_loads = _code_check_load_inventory(code_check_report)

    bridged_member_handles = {
        handle
        for row in mappings
        if isinstance(row, dict)
        for handle in _mapping_member_handles(row)
    }
    bridged_sections = {
        section_id
        for row in mappings
        if isinstance(row, dict)
        for section_id in _mapping_section_ids(row)
    }
    bridged_loads = {
        item
        for row in mappings
        if isinstance(row, dict)
        for item in _mapping_load_names(row)
    }

    member_count = len(bridged_member_handles & expected_member_handles)
    section_count = len(bridged_sections & expected_sections)
    load_count = len(bridged_loads & expected_loads)

    member_expected = len(expected_member_handles)
    section_expected = len(expected_sections)
    load_expected = len(expected_loads)

    member_status = _crosswalk_status(member_count, member_expected)
    section_status = _crosswalk_status(section_count, section_expected)
    load_status = _crosswalk_status(load_count, load_expected)
    expected_member_handle_list = sorted(expected_member_handles)
    expected_section_id_list = sorted(expected_sections)
    expected_load_name_list = sorted(expected_loads)
    missing_member_handles = sorted(expected_member_handles - bridged_member_handles)
    missing_section_ids = sorted(expected_sections - bridged_sections)
    missing_load_names = sorted(expected_loads - bridged_loads)

    return {
        'full_member_crosswalk_count': member_count,
        'full_member_crosswalk_expected': member_expected,
        'full_member_crosswalk_status': member_status,
        'full_member_crosswalk_handle_kind': member_handle_kind,
        'full_member_crosswalk_handles': sorted(bridged_member_handles),
        'full_member_crosswalk_expected_handles': expected_member_handle_list,
        'full_member_crosswalk_missing_handles': missing_member_handles,
        'full_section_crosswalk_count': section_count,
        'full_section_crosswalk_expected': section_expected,
        'full_section_crosswalk_status': section_status,
        'full_section_crosswalk_ids': sorted(bridged_sections),
        'full_section_crosswalk_expected_ids': expected_section_id_list,
        'full_section_crosswalk_missing_ids': missing_section_ids,
        'full_load_crosswalk_count': load_count,
        'full_load_crosswalk_expected': load_expected,
        'full_load_crosswalk_status': load_status,
        'full_load_crosswalk_names': sorted(bridged_loads),
        'full_load_crosswalk_expected_names': expected_load_name_list,
        'full_load_crosswalk_missing_names': missing_load_names,
        'full_crosswalk_summary_label': (
            f"members={member_count}/{member_expected} {member_status} | "
            f"sections={section_count}/{section_expected} {section_status} | "
            f"loads={load_count}/{load_expected} {load_status}"
        ),
    }


def _row_provenance_payload(
    *,
    review_member_id: str,
    review_case_id: str,
    review_keys: list[str],
    baseline_focus_member_id: str,
    case_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = sorted((dict(row) for row in case_rows if isinstance(row, dict)), key=_row_sort_key)
    member_type_names = _unique_strings([row.get('member_type') for row in rows])
    combination_names = _unique_strings([row.get('combination') for row in rows])
    clause_names = _unique_strings([row.get('clause') for row in rows])
    component_names = _unique_strings([row.get('component') for row in rows])
    rule_family_names = _unique_strings([row.get('rule_family') for row in rows])
    hazard_names = _unique_strings([row.get('hazard_type') for row in rows])
    topology_names = _unique_strings([row.get('topology_type') for row in rows])
    top_row_label = _top_row_label(rows)
    member_type_label = ', '.join(member_type_names) if member_type_names else 'unknown'
    return {
        'mapped': bool(rows),
        'review_keys_label': ', '.join(str(item or '').strip() for item in review_keys if str(item or '').strip()),
        'member_inventory_count': len(member_type_names),
        'member_inventory_member_type_names': member_type_names,
        'member_inventory_member_type_label': member_type_label,
        'member_inventory_summary_label': (
            f'review={review_member_id} | case={review_case_id} | '
            f'baseline={baseline_focus_member_id} | member_types={member_type_label}'
        ),
        'row_provenance_row_count': len(rows),
        'row_provenance_combination_count': len(combination_names),
        'row_provenance_clause_count': len(clause_names),
        'row_provenance_component_count': len(component_names),
        'row_provenance_rule_family_count': len(rule_family_names),
        'row_provenance_hazard_count': len(hazard_names),
        'row_provenance_topology_count': len(topology_names),
        'row_provenance_combination_names': combination_names,
        'row_provenance_clause_names': clause_names,
        'row_provenance_component_names': component_names,
        'row_provenance_rule_family_names': rule_family_names,
        'row_provenance_hazard_names': hazard_names,
        'row_provenance_topology_names': topology_names,
        'row_provenance_top_row_label': top_row_label,
        'row_provenance_summary_label': (
            f'rows={len(rows)} | combos={len(combination_names)} | '
            f'clauses={len(clause_names)} | top={top_row_label}'
        ),
        'clause_provenance_summary_label': (
            f'clauses={len(clause_names)} | rules={len(rule_family_names)} | '
            f'hazards={len(hazard_names)} | top={top_row_label}'
        ),
        'clause_provenance_clause_names': clause_names,
        'clause_provenance_rule_family_names': rule_family_names,
        'clause_provenance_hazard_names': hazard_names,
        'clause_provenance_topology_names': topology_names,
        'row_provenance_rows': rows,
    }


def _review_profiles(code_check_report: dict[str, Any], benchmark_payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    benchmark_cases = {
        str(row.get('case_id', '')).strip(): row
        for row in (benchmark_payload.get('cases') or [])
        if isinstance(row, dict) and str(row.get('case_id', '')).strip()
    }
    profiles: dict[str, dict[str, str]] = {}
    for row in (code_check_report.get('member_check_rows') or []):
        if not isinstance(row, dict):
            continue
        case_id = str(row.get('case_id', '') or row.get('member_id', '')).strip()
        if not case_id or case_id in profiles:
            continue
        benchmark_row = benchmark_cases.get(case_id, {}) if isinstance(benchmark_cases.get(case_id), dict) else {}
        profiles[case_id] = {
            'review_member_id': str(row.get('member_id', '') or case_id).strip(),
            'review_case_id': case_id,
            'source_member_type': str(row.get('member_type', '') or 'unknown').strip() or 'unknown',
            'source_topology_type': str(row.get('topology_type', '') or benchmark_row.get('topology_type', 'unknown')).strip() or 'unknown',
            'source_hazard_type': str(row.get('hazard_type', '') or benchmark_row.get('hazard_type', 'unknown')).strip() or 'unknown',
            'source_element_mix': str(benchmark_row.get('element_mix', '') or 'unknown').strip() or 'unknown',
            'source_family': str(benchmark_row.get('source_family', '') or 'commercial_export').strip() or 'commercial_export',
        }
    return profiles


def build_registry(model_payload: dict[str, Any], code_check_report: dict[str, Any], benchmark_payload: dict[str, Any]) -> dict[str, Any]:
    elements, nodes = _build_element_lookup(model_payload)
    member_lookup = _build_member_lookup(model_payload)
    full_crosswalk_inventory = _build_full_crosswalk_inventory(model_payload)
    profiles = _review_profiles(code_check_report, benchmark_payload)
    case_row_groups = _case_row_groups(code_check_report)
    mappings: list[dict[str, Any]] = []
    missing_reviews = []
    for case_id, review in sorted(profiles.items()):
        reviewed = REVIEWED_FOCUS_MAP.get(case_id)
        if not reviewed:
            missing_reviews.append(case_id)
            continue
        element = elements.get(reviewed['baseline_focus_member_id'])
        if not isinstance(element, dict):
            raise ValueError(f'missing baseline focus element {reviewed["baseline_focus_member_id"]} for {case_id}')
        node_ids = [int(item) for item in (element.get('node_ids') or [])[:2]]
        coords = [nodes.get(node_id, {}) for node_id in node_ids]
        review_keys = [review['review_member_id'], case_id]
        provenance_payload = _row_provenance_payload(
            review_member_id=review['review_member_id'],
            review_case_id=case_id,
            review_keys=review_keys,
            baseline_focus_member_id=reviewed['baseline_focus_member_id'],
            case_rows=case_row_groups.get(case_id, []),
        )
        note = (
            'manual review exact-focus mapping confirmed against canonical MIDAS 33 geometry and semantic case profile; '
            f"member_type={review['source_member_type']}, topology={review['source_topology_type']}, hazard={review['source_hazard_type']}, mix={review['source_element_mix']}. "
            f"Navigation focus member {reviewed['baseline_focus_member_id']} uses section {element.get('section_id')} and nodes {node_ids}. "
            'This is an exact focus-member mapping for review/navigation within the canonical artifact, not a one-to-many full physical member inventory.'
        )
        aggregate_member_id = member_lookup.get(reviewed['baseline_focus_member_id'], '')
        member_groups, section_groups = _selector_full_crosswalk_groups(reviewed['selector_kind'])
        full_member_handles = _inventory_union(
            full_crosswalk_inventory.get('member_handles_by_group', {}),
            member_groups,
        )
        full_section_ids = _inventory_union(
            full_crosswalk_inventory.get('section_ids_by_group', {}),
            section_groups,
        )
        full_load_names = list(provenance_payload.get('row_provenance_combination_names') or [])
        mappings.append(
            {
                'review_member_id': review['review_member_id'],
                'review_case_id': case_id,
                'review_keys': review_keys,
                'baseline_focus_member_id': reviewed['baseline_focus_member_id'],
                'match_strategy': 'manual_verified_exact_focus_member',
                'match_confidence': 'manual_verified_exact_focus',
                'selector_kind': reviewed['selector_kind'],
                'source_family': review['source_family'],
                'source_topology_type': review['source_topology_type'],
                'source_member_type': review['source_member_type'],
                'source_hazard_type': review['source_hazard_type'],
                'source_element_mix': review['source_element_mix'],
                'surrogate_geometry_kind': reviewed['surrogate_geometry_kind'],
                'surrogate_aggregate_member_id': aggregate_member_id,
                'full_crosswalk_target_member_handle': aggregate_member_id or reviewed['baseline_focus_member_id'],
                'full_crosswalk_target_section_id': str(element.get('section_id', '') or ''),
                'full_crosswalk_member_groups': member_groups,
                'full_crosswalk_member_handles': full_member_handles,
                'full_crosswalk_member_handle_count': len(full_member_handles),
                'full_crosswalk_section_groups': section_groups,
                'full_crosswalk_section_ids': full_section_ids,
                'full_crosswalk_section_id_count': len(full_section_ids),
                'full_crosswalk_load_combination_names': full_load_names,
                'full_crosswalk_load_combination_count': len(full_load_names),
                'reviewer_verified': True,
                'note': note,
                'review_geometry_snapshot': {
                    'element_type': str(element.get('type', '') or ''),
                    'family': str(element.get('family', '') or ''),
                    'section_id': str(element.get('section_id', '') or ''),
                    'material_id': str(element.get('material_id', '') or ''),
                    'node_ids': [str(node_id) for node_id in node_ids],
                    'node_coordinates': [
                        {'id': str(node.get('id', '') or ''), 'x': float(node.get('x', 0.0) or 0.0), 'y': float(node.get('y', 0.0) or 0.0), 'z': float(node.get('z', 0.0) or 0.0)}
                        for node in coords
                        if isinstance(node, dict)
                    ],
                },
                **provenance_payload,
            }
        )
    if missing_reviews:
        raise ValueError(f'missing reviewed mappings for: {missing_reviews}')
    full_crosswalk_summary = _registry_full_crosswalk_summary(
        mappings=mappings,
        model_payload=model_payload,
        code_check_report=code_check_report,
    )
    global_member_handles = list(full_crosswalk_summary.get('full_member_crosswalk_expected_handles') or [])
    global_section_ids = list(full_crosswalk_summary.get('full_section_crosswalk_expected_ids') or [])
    global_load_names = list(full_crosswalk_summary.get('full_load_crosswalk_expected_names') or [])
    for row in mappings:
        row['full_crosswalk_global_member_handles'] = global_member_handles
        row['full_crosswalk_global_member_handle_count'] = len(global_member_handles)
        row['full_crosswalk_global_section_ids'] = global_section_ids
        row['full_crosswalk_global_section_id_count'] = len(global_section_ids)
        row['full_crosswalk_global_load_combination_names'] = global_load_names
        row['full_crosswalk_global_load_combination_count'] = len(global_load_names)
        row['full_crosswalk_inventory_scope'] = 'selector_group'
        row['full_crosswalk_global_inventory_scope'] = 'model_and_codecheck_expected'
        row['full_crosswalk_inventory_summary_label'] = (
            f"groups=members:{len(row.get('full_crosswalk_member_groups') or [])}/"
            f"sections:{len(row.get('full_crosswalk_section_groups') or [])} | "
            f"selector=members:{row.get('full_crosswalk_member_handle_count', 0)}/"
            f"sections:{row.get('full_crosswalk_section_id_count', 0)}/"
            f"loads:{row.get('full_crosswalk_load_combination_count', 0)} | "
            f"global=members:{len(global_member_handles)}/sections:{len(global_section_ids)}/loads:{len(global_load_names)}"
        )
    return {
        'contract_version': '0.6.0',
        'registry_kind': 'kds_geometry_bridge_registry',
        'source': 'manual_review_exact_focus_registry',
        'limitations': [
            'These rows are manually reviewed exact focus-member mappings for navigation inside the canonical MIDAS 33 artifact.',
            'They do not claim exhaustive one-to-many physical member equivalence for every code-check row.',
        ],
        'summary': {
            'mapping_count': len(mappings),
            'source_counts': {'manual_review_exact_focus_registry': len(mappings)},
            'confidence_counts': {'manual_verified_exact_focus': len(mappings)},
            'exact_mapping_count': len(mappings),
            'heuristic_mapping_count': 0,
            'reviewer_verified_mapping_count': len(mappings),
            'full_member_crosswalk_handles_by_group': dict(full_crosswalk_inventory.get('member_handles_by_group', {})),
            'full_member_crosswalk_group_count': len(full_crosswalk_inventory.get('member_handles_by_group', {})),
            'full_section_crosswalk_ids_by_group': dict(full_crosswalk_inventory.get('section_ids_by_group', {})),
            'full_section_crosswalk_group_count': len(full_crosswalk_inventory.get('section_ids_by_group', {})),
            **full_crosswalk_summary,
        },
        'mappings': mappings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build a reviewed exact KDS review-id -> MIDAS focus-member registry.')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--code-check-report', type=Path, default=DEFAULT_CODECHECK_REPORT)
    parser.add_argument('--benchmark-cases', type=Path, default=DEFAULT_BENCHMARK_CASES)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    registry = build_registry(
        model_payload=_load_json(args.model),
        code_check_report=_load_json(args.code_check_report),
        benchmark_payload=_load_json(args.benchmark_cases),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = registry.get('summary') if isinstance(registry.get('summary'), dict) else {}
    print(
        f"{args.out}: mappings={len(registry['mappings'])} "
        f"exact={summary.get('exact_mapping_count', 0)} "
        f"heuristic={summary.get('heuristic_mapping_count', 0)} "
        f"full_crosswalk={summary.get('full_crosswalk_summary_label', 'n/a')}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
