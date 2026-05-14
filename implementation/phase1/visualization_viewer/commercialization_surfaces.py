from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


DEFAULT_COMMERCIAL_WORKFLOW_BREADTH_REPORT = Path(
    'implementation/phase1/release/commercial_workflow_breadth_report.json'
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _safe_int(value: Any, default: int | None = 0) -> int | None:
    try:
        return int(value)
    except Exception:
        return default


def _format_result_metric(
    value: Any,
    *,
    decimals: int = 3,
    suffix: str = '',
    scale: float = 1.0,
) -> str:
    try:
        number = float(value) * scale
    except Exception:
        return 'n/a'
    if abs(number) >= 1000:
        return f'{number:,.{decimals}f}{suffix}'
    return f'{number:.{decimals}f}{suffix}'


def _summary_line_indicates_ready(summary_line: str) -> bool:
    normalized = str(summary_line or '').strip().lower()
    if not normalized:
        return False
    return (
        normalized.startswith('pass')
        or normalized.startswith('ok')
        or ': pass' in normalized
        or '| pass' in normalized
        or ': ok' in normalized
        or '| ok' in normalized
    )


def _summary_line_excerpt(summary_line: str, *, focus_tokens: list[str] | None = None, max_bits: int = 3) -> str:
    text = str(summary_line or '').strip()
    if not text:
        return ''
    bits = [bit.strip() for bit in text.split('|') if bit.strip()]
    if not bits:
        return text
    selected = [bits[0]]
    if focus_tokens:
        for token in focus_tokens:
            normalized_token = str(token or '').strip().lower()
            if not normalized_token:
                continue
            for bit in bits[1:]:
                if normalized_token in bit.lower() and bit not in selected:
                    selected.append(bit)
                    if len(selected) >= max_bits:
                        return ' | '.join(selected[:max_bits])
    for bit in bits[1:]:
        if bit not in selected:
            selected.append(bit)
        if len(selected) >= max_bits:
            break
    return ' | '.join(selected[:max_bits])


def build_commercialization_depth_surface(release_gap_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = release_gap_payload if isinstance(release_gap_payload, Mapping) else {}
    summary = payload.get('summary') if isinstance(payload.get('summary'), Mapping) else {}
    if not summary:
        return {
            'available': False,
            'label': 'P0/P1 Commercialization Depth',
            'disclaimer': 'release gap summary 기반의 bounded depth surface입니다. full solver replacement parity를 뜻하지 않습니다.',
            'count': 0,
            'ready_count': 0,
            'open_count': 0,
            'p0_total_count': 0,
            'p0_ready_count': 0,
            'p1_total_count': 0,
            'p1_ready_count': 0,
            'headline': 'release gap summary unavailable',
            'rows': [],
        }

    material_summary_line = str(
        summary.get('material_constitutive_summary_line', '')
        or summary.get('element_material_breadth_summary_line', '')
        or summary.get('ndtha_material_summary_line', '')
        or ''
    ).strip()
    material_scope_line = str(
        summary.get('element_material_breadth_summary_line', '')
        or summary.get('solver_breadth_summary_line', '')
        or ''
    ).strip()
    load_summary_line = str(
        summary.get('load_combination_editor_commercialization_summary_line', '')
        or summary.get('load_combination_engine_summary_line', '')
        or summary.get('midas_loadcomb_roundtrip_summary_line', '')
        or summary.get('mgt_export_loadcomb_roundtrip_summary_line', '')
        or ''
    ).strip()
    load_scope_line = str(
        summary.get('load_combination_editor_commercialization_summary_line', '')
        or summary.get('load_combination_editor_required_target_match_label', '')
        or summary.get('midas_loadcomb_roundtrip_summary_line', '')
        or summary.get('mgt_export_loadcomb_roundtrip_summary_line', '')
        or ''
    ).strip()
    reference_regression_summary_line = str(summary.get('reference_regression_summary_line', '') or '').strip()
    reference_regression_report_path = str(summary.get('reference_regression_report_path', '') or '').strip()
    advanced_ssi_summary_line = str(
        summary.get('advanced_ssi_summary_line', '')
        or summary.get('foundation_soil_link_summary_line', '')
        or summary.get('general_fe_contact_matrix_summary_line', '')
        or summary.get('solver_breadth_summary_line', '')
        or ''
    ).strip()
    advanced_ssi_scope_line = str(
        summary.get('general_fe_contact_matrix_summary_line', '')
        or summary.get('solver_breadth_summary_line', '')
        or ''
    ).strip()
    wind_mode = str(summary.get('wind_tunnel_mapping_mode', '') or '').strip()
    wind_reason = str(summary.get('wind_tunnel_mapping_reason', '') or '').strip()
    wind_dynamic_fallback = _summary_line_excerpt(
        str(summary.get('material_constitutive_summary_line', '') or ''),
        focus_tokens=['wind_dynamic_response', 'raw_pressure_field_mapping'],
    )
    wind_summary_line = str(summary.get('wind_workflow_summary_line', '') or '').strip()
    if not wind_summary_line:
        wind_segments = [f"Wind mapping: {'PASS' if bool(summary.get('wind_tunnel_raw_mapping_ready', False)) else 'CHECK'}"]
        if wind_mode:
            wind_segments.append(f"mode={wind_mode}")
        if wind_reason:
            wind_segments.append(wind_reason)
        elif wind_dynamic_fallback:
            wind_segments.append(wind_dynamic_fallback)
        wind_summary_line = ' | '.join(segment for segment in wind_segments if segment)

    rows = [
        {
            'id': 'material_depth',
            'label': 'Material / constitutive depth',
            'priority': 'P0',
            'ready': bool(material_summary_line) and _summary_line_indicates_ready(material_summary_line),
            'summary_line': material_summary_line,
            'summary_excerpt': _summary_line_excerpt(
                material_summary_line,
                focus_tokens=['concrete_damage', 'cyclic_degradation', 'bond_interface', 'matrix='],
            ) or 'material constitutive summary unavailable',
            'evidence_excerpt': _summary_line_excerpt(
                material_scope_line,
                focus_tokens=['panel_cyclic', 'assembled_depth', 'contact=', 'materials='],
            ) or 'element/material breadth summary unavailable',
        },
        {
            'id': 'load_depth',
            'label': 'Load / combination depth',
            'priority': 'P0',
            'ready': bool(load_summary_line) and (
                bool(summary.get('load_combination_editor_commercialization_pass', False))
                or bool(summary.get('load_combination_engine_pass', False))
                or _summary_line_indicates_ready(load_summary_line)
            ),
            'summary_line': load_summary_line,
            'summary_excerpt': _summary_line_excerpt(
                load_summary_line,
                focus_tokens=[
                    'kds_match=',
                    'selfweight',
                    'nodal',
                    'surface',
                    'pressure',
                    'codecheck=',
                    'exact_roundtrip',
                    'kds_strength_avg',
                    'cases=',
                    'artifacts=',
                ],
            ) or 'load-combination summary unavailable',
            'evidence_excerpt': _summary_line_excerpt(
                load_scope_line,
                focus_tokens=['kds_match=', 'codecheck=', 'entry_row_coverage', 'artifacts=', 'combos='],
            ) or 'roundtrip evidence unavailable',
        },
        {
            'id': 'reference_regression',
            'label': 'Reference regression loop',
            'priority': 'P0',
            'ready': bool(reference_regression_summary_line) and (
                bool(summary.get('reference_regression_pass', False))
                or _summary_line_indicates_ready(reference_regression_summary_line)
            ),
            'summary_line': reference_regression_summary_line,
            'summary_excerpt': _summary_line_excerpt(
                reference_regression_summary_line,
                focus_tokens=['cases=', 'metrics=', 'classes=', 'max_norm_err='],
            ) or 'reference regression summary unavailable',
            'evidence_excerpt': (
                f"report={reference_regression_report_path}"
                if reference_regression_report_path
                else 'reference regression report unavailable'
            ),
        },
        {
            'id': 'advanced_ssi_depth',
            'label': 'Advanced SSI / interaction depth',
            'priority': 'P1',
            'ready': bool(advanced_ssi_summary_line) and (
                bool(summary.get('advanced_ssi_pass', False))
                or (
                    _summary_line_indicates_ready(advanced_ssi_summary_line)
                    and 'ssi=yes' in f"{advanced_ssi_summary_line} | {advanced_ssi_scope_line}".lower()
                )
            ),
            'summary_line': advanced_ssi_summary_line,
            'summary_excerpt': _summary_line_excerpt(
                advanced_ssi_summary_line,
                focus_tokens=[
                    'peak_transfer',
                    'group_eff',
                    'detune',
                    'ssi=yes',
                    'soil_tunnel=yes',
                    'impedance_schema=yes',
                    'links=',
                ],
            ) or 'advanced SSI summary unavailable',
            'evidence_excerpt': _summary_line_excerpt(
                advanced_ssi_scope_line,
                focus_tokens=['ssi=yes', 'support_depth=', 'coupling_depth=', 'support_search='],
            ) or 'interaction/contact depth summary unavailable',
        },
        {
            'id': 'wind_depth',
            'label': 'Wind / raw mapping depth',
            'priority': 'P1',
            'ready': bool(summary.get('wind_workflow_pass', False) or summary.get('wind_tunnel_raw_mapping_ready', False)),
            'summary_line': wind_summary_line,
            'summary_excerpt': _summary_line_excerpt(
                wind_summary_line,
                focus_tokens=['comfort=', 'crosswind', 'mode=', 'wind mapping', 'raw_pressure_field_mapping', 'wind_dynamic_response'],
            ) or 'wind summary unavailable',
            'evidence_excerpt': wind_dynamic_fallback or 'wind/material coupling summary unavailable',
        },
    ]
    for row in rows:
        row['status'] = 'PASS' if bool(row.get('ready', False)) else 'CHECK'
        row['status_tone'] = 'ok' if bool(row.get('ready', False)) else 'warn'

    p0_rows = [row for row in rows if str(row.get('priority', '') or '') == 'P0']
    p1_rows = [row for row in rows if str(row.get('priority', '') or '') == 'P1']
    ready_count = sum(1 for row in rows if bool(row.get('ready', False)))
    count = len(rows)
    p0_ready_count = sum(1 for row in p0_rows if bool(row.get('ready', False)))
    p1_ready_count = sum(1 for row in p1_rows if bool(row.get('ready', False)))
    headline = (
        f"P0 {p0_ready_count}/{len(p0_rows)} | "
        f"P1 {p1_ready_count}/{len(p1_rows)} | "
        f"total {ready_count}/{count}"
    )
    return {
        'available': bool(rows),
        'label': 'P0/P1 Commercialization Depth',
        'disclaimer': 'release gap summary 기반의 bounded depth surface입니다. full solver replacement parity를 뜻하지 않습니다.',
        'count': int(count),
        'ready_count': int(ready_count),
        'open_count': int(max(count - ready_count, 0)),
        'p0_total_count': int(len(p0_rows)),
        'p0_ready_count': int(p0_ready_count),
        'p1_total_count': int(len(p1_rows)),
        'p1_ready_count': int(p1_ready_count),
        'headline': headline,
        'rows': rows,
    }


def _commercial_workflow_ratio_label(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return 'n/a'
    if 0.0 <= number <= 1.0:
        return f'{number:.1%}'
    return f'{number:.3f}'


def build_commercial_workflow_breadth_surface(
    report_payload: Mapping[str, Any] | None,
    *,
    artifact_href: str = '',
    artifact_path: str | Path = '',
) -> dict[str, Any]:
    payload = report_payload if isinstance(report_payload, Mapping) else {}
    summary = payload.get('summary') if isinstance(payload.get('summary'), Mapping) else {}
    checks = payload.get('checks') if isinstance(payload.get('checks'), Mapping) else {}
    summary_line = str(payload.get('summary_line', '') or '').strip()
    resolved_artifact_path = Path(str(artifact_path or DEFAULT_COMMERCIAL_WORKFLOW_BREADTH_REPORT))
    artifact_name = resolved_artifact_path.name
    if not (summary or checks or summary_line):
        return {
            'available': False,
            'label': 'Commercial Workflow Breadth',
            'disclaimer': 'construction-stage / rail-tunnel / redesign-loop breadth evidence is not attached yet.',
            'status_label': 'commercial_workflow_breadth_unavailable',
            'status_tone': 'warn',
            'headline': 'commercial workflow breadth unavailable',
            'summary_line': 'commercial workflow breadth unavailable',
            'traceability_summary_label': '',
            'count': 0,
            'ready_count': 0,
            'open_count': 0,
            'checks_pass': False,
            'artifact_href': str(artifact_href or ''),
            'artifact_name': artifact_name,
            'rows': [],
        }

    construction_stage_ready = bool(summary.get('construction_stage_ready', False))
    construction_stage_history_snapshot_count = int(
        _safe_int(summary.get('construction_stage_history_snapshot_count', 0), 0) or 0
    )
    construction_stage_max_differential_shortening_mm = summary.get(
        'construction_stage_max_differential_shortening_mm'
    )
    construction_stage_max_differential_shortening_label = _format_result_metric(
        construction_stage_max_differential_shortening_mm,
        decimals=3,
        suffix=' mm',
    )

    rail_tunnel_ready = bool(summary.get('rail_tunnel_ready', False))
    rail_tunnel_serviceability_status = str(summary.get('rail_tunnel_serviceability_status', '') or 'n/a')
    rail_tunnel_maintenance_priority = str(summary.get('rail_tunnel_maintenance_priority', '') or 'n/a')
    rail_tunnel_recommended_action_count = int(
        _safe_int(summary.get('rail_tunnel_recommended_action_count', 0), 0) or 0
    )

    design_redesign_loop_ready = bool(summary.get('design_redesign_loop_ready', False))
    design_report_traceability_ratio = summary.get('design_report_traceability_ratio')
    design_report_traceability_ratio_label = _commercial_workflow_ratio_label(design_report_traceability_ratio)
    design_report_ng_member_count = int(_safe_int(summary.get('design_report_ng_member_count', 0), 0) or 0)
    section_optimizer_suggestion_count = int(
        _safe_int(summary.get('section_optimizer_suggestion_count', 0), 0) or 0
    )
    section_optimizer_strengthen_count = int(
        _safe_int(summary.get('section_optimizer_strengthen_count', 0), 0) or 0
    )
    section_optimizer_reduce_count = int(_safe_int(summary.get('section_optimizer_reduce_count', 0), 0) or 0)
    governing_clause_count = int(_safe_int(summary.get('governing_clause_count', 0), 0) or 0)
    checks_pass = bool(checks.get('pass', False))

    rows = [
        {
            'id': 'construction_stage',
            'label': 'Construction-stage breadth',
            'ready': construction_stage_ready,
            'summary_line': (
                f"construction_stage={'PASS' if construction_stage_ready else 'CHECK'} | "
                f"history_snapshots={construction_stage_history_snapshot_count} | "
                f"max_differential_shortening={construction_stage_max_differential_shortening_label}"
            ),
            'summary_excerpt': (
                f"history snapshots={construction_stage_history_snapshot_count} | "
                f"max shortening={construction_stage_max_differential_shortening_label}"
            ),
            'evidence_excerpt': (
                'construction-stage history snapshots and differential shortening coverage '
                'are attached through the workflow breadth contract.'
            ),
        },
        {
            'id': 'rail_tunnel_serviceability',
            'label': 'Rail / tunnel serviceability',
            'ready': rail_tunnel_ready,
            'summary_line': (
                f"rail_tunnel={'PASS' if rail_tunnel_ready else 'CHECK'} | "
                f"serviceability={rail_tunnel_serviceability_status} | "
                f"maintenance={rail_tunnel_maintenance_priority} | "
                f"actions={rail_tunnel_recommended_action_count}"
            ),
            'summary_excerpt': (
                f"serviceability={rail_tunnel_serviceability_status} | "
                f"maintenance={rail_tunnel_maintenance_priority}"
            ),
            'evidence_excerpt': f"recommended actions={rail_tunnel_recommended_action_count}",
        },
        {
            'id': 'design_redesign_loop',
            'label': 'Design redesign loop breadth',
            'ready': design_redesign_loop_ready,
            'summary_line': (
                f"design_redesign_loop={'PASS' if design_redesign_loop_ready else 'CHECK'} | "
                f"traceability={design_report_traceability_ratio_label} | "
                f"ng_members={design_report_ng_member_count} | "
                f"suggestions={section_optimizer_suggestion_count}"
            ),
            'summary_excerpt': (
                f"traceability={design_report_traceability_ratio_label} | "
                f"ng members={design_report_ng_member_count}"
            ),
            'evidence_excerpt': (
                f"optimizer suggestions={section_optimizer_suggestion_count} | "
                f"strengthen={section_optimizer_strengthen_count} | "
                f"reduce={section_optimizer_reduce_count} | "
                f"governing clauses={governing_clause_count}"
            ),
        },
    ]
    for row in rows:
        row['status'] = 'PASS' if bool(row.get('ready', False)) else 'CHECK'
        row['status_tone'] = 'ok' if bool(row.get('ready', False)) else 'warn'

    ready_count = sum(1 for row in rows if bool(row.get('ready', False)))
    count = len(rows)
    open_count = max(count - ready_count, 0)
    traceability_summary_label = ' | '.join(
        part
        for part in [
            f"checks={'PASS' if checks_pass else 'CHECK'}",
            f"construction_snapshots={construction_stage_history_snapshot_count}",
            f"rail_actions={rail_tunnel_recommended_action_count}",
            f"design_traceability={design_report_traceability_ratio_label}",
        ]
        if part
    )
    return {
        'available': True,
        'label': 'Commercial Workflow Breadth',
        'disclaimer': (
            'construction-stage / rail-tunnel / redesign-loop breadth is shown as a scoped '
            'commercialization/readiness surface from the workflow breadth contract.'
        ),
        'status_label': (
            'commercial_workflow_breadth_ready'
            if checks_pass and open_count == 0 and ready_count > 0
            else 'commercial_workflow_breadth_partial'
        ),
        'status_tone': 'ok' if checks_pass and open_count == 0 and ready_count > 0 else 'warn',
        'headline': (
            f"ready {ready_count}/{count} | "
            f"checks={'PASS' if checks_pass else 'CHECK'} | "
            f"clauses={governing_clause_count}"
        ),
        'summary_line': summary_line or traceability_summary_label,
        'traceability_summary_label': traceability_summary_label,
        'count': int(count),
        'ready_count': int(ready_count),
        'open_count': int(open_count),
        'checks_pass': checks_pass,
        'artifact_href': str(artifact_href or ''),
        'artifact_name': artifact_name,
        'construction_stage_ready': construction_stage_ready,
        'construction_stage_history_snapshot_count': construction_stage_history_snapshot_count,
        'construction_stage_max_differential_shortening_mm': _safe_float(
            construction_stage_max_differential_shortening_mm,
            0.0,
        ),
        'construction_stage_max_differential_shortening_label': construction_stage_max_differential_shortening_label,
        'rail_tunnel_ready': rail_tunnel_ready,
        'rail_tunnel_serviceability_status': rail_tunnel_serviceability_status,
        'rail_tunnel_maintenance_priority': rail_tunnel_maintenance_priority,
        'rail_tunnel_recommended_action_count': rail_tunnel_recommended_action_count,
        'design_redesign_loop_ready': design_redesign_loop_ready,
        'design_report_traceability_ratio': _safe_float(design_report_traceability_ratio, 0.0),
        'design_report_traceability_ratio_label': design_report_traceability_ratio_label,
        'design_report_ng_member_count': design_report_ng_member_count,
        'section_optimizer_suggestion_count': section_optimizer_suggestion_count,
        'section_optimizer_strengthen_count': section_optimizer_strengthen_count,
        'section_optimizer_reduce_count': section_optimizer_reduce_count,
        'governing_clause_count': governing_clause_count,
        'rows': rows,
    }
