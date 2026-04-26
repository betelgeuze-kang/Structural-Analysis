#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.load_combination_engine import export_midas_loadcomb_from_model_payload
    from implementation.phase1.parse_midas_mgt_to_json_npz import _parse_loadcomb_rows
except ImportError:  # pragma: no cover - direct execution fallback
    from load_combination_engine import export_midas_loadcomb_from_model_payload
    from parse_midas_mgt_to_json_npz import _parse_loadcomb_rows


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path} does not contain a JSON object')
    return payload


def _extract_loadcomb_rows(text: str) -> list[str]:
    rows: list[str] = []
    inside = False
    for raw_line in str(text or '').splitlines():
        stripped = raw_line.strip()
        upper = stripped.upper()
        if upper.startswith('*LOADCOMB'):
            inside = True
            continue
        if inside and upper.startswith('*'):
            break
        if not inside or not stripped or stripped.startswith(';'):
            continue
        rows.append(stripped)
    return rows


def _entry_signature(row: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    signature = []
    for entry in (row.get('entries') or []):
        if not isinstance(entry, dict):
            continue
        reference_kind = str(entry.get('reference_kind', '') or '').strip().upper()
        reference_name = str(entry.get('reference_name', '') or '').strip()
        if reference_kind not in {'ST', 'CB'} or not reference_name:
            continue
        signature.append((reference_kind, reference_name, f"{float(entry.get('factor', 0.0) or 0.0):.12g}"))
    return tuple(signature)


def _factor_map_signature(row: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    factor_map = row.get('factor_map') if isinstance(row.get('factor_map'), dict) else {}
    return tuple(
        (str(case_name).strip(), f"{float(factor):.12g}")
        for case_name, factor in sorted(factor_map.items(), key=lambda item: str(item[0]))
        if str(case_name).strip()
    )


def build_roundtrip_report(*, model_payload: dict[str, Any], source_path: str = '', export_text: str | None = None) -> dict[str, Any]:
    model = model_payload.get('model') if isinstance(model_payload.get('model'), dict) else {}
    metadata = model.get('metadata') if isinstance(model.get('metadata'), dict) else {}
    raw_rows = [str(row).strip() for row in (model.get('load_combinations_raw') or []) if str(row).strip()]
    raw_combos = _parse_loadcomb_rows(raw_rows) if raw_rows else []
    rendered_text = export_text if export_text is not None else export_midas_loadcomb_from_model_payload(model_payload)
    exported_rows = _extract_loadcomb_rows(rendered_text)
    exported_combos = _parse_loadcomb_rows(exported_rows) if exported_rows else []

    raw_by_name = {
        str(row.get('name', '') or '').strip(): row
        for row in raw_combos
        if isinstance(row, dict) and str(row.get('name', '') or '').strip()
    }
    exported_by_name = {
        str(row.get('name', '') or '').strip(): row
        for row in exported_combos
        if isinstance(row, dict) and str(row.get('name', '') or '').strip()
    }
    raw_names = sorted(raw_by_name)
    exported_names = sorted(exported_by_name)
    shared_names = sorted(set(raw_names) & set(exported_names))
    missing_names = [name for name in raw_names if name not in exported_by_name]
    extra_names = [name for name in exported_names if name not in raw_by_name]

    exact_entry_row_match_names: list[str] = []
    exact_header_match_names: list[str] = []
    exact_factor_map_match_names: list[str] = []
    exact_expression_match_names: list[str] = []
    mismatched_entry_names: list[str] = []
    mismatched_header_names: list[str] = []
    mismatched_factor_map_names: list[str] = []
    mismatched_expression_names: list[str] = []

    direct_expression_candidate_count = 0
    combo_diffs: list[dict[str, Any]] = []
    for name in shared_names:
        raw_row = raw_by_name[name]
        exported_row = exported_by_name[name]
        raw_entry_signature = _entry_signature(raw_row)
        exported_entry_signature = _entry_signature(exported_row)
        raw_header = (
            str(raw_row.get('combination_type', '') or '').strip(),
            str(raw_row.get('limit_state', '') or '').strip(),
        )
        exported_header = (
            str(exported_row.get('combination_type', '') or '').strip(),
            str(exported_row.get('limit_state', '') or '').strip(),
        )
        raw_factor_map = _factor_map_signature(raw_row)
        exported_factor_map = _factor_map_signature(exported_row)
        raw_expression = str(raw_row.get('expression', '') or '').strip()
        exported_expression = str(exported_row.get('expression', '') or '').strip()
        is_direct_combo = not any(kind == 'CB' for kind, _, _ in raw_entry_signature)
        if is_direct_combo and raw_expression:
            direct_expression_candidate_count += 1

        if raw_entry_signature == exported_entry_signature:
            exact_entry_row_match_names.append(name)
        else:
            mismatched_entry_names.append(name)
        if raw_header == exported_header:
            exact_header_match_names.append(name)
        else:
            mismatched_header_names.append(name)
        if raw_factor_map == exported_factor_map:
            exact_factor_map_match_names.append(name)
        else:
            mismatched_factor_map_names.append(name)
        if (not is_direct_combo) or raw_expression == exported_expression:
            exact_expression_match_names.append(name)
        elif is_direct_combo:
            mismatched_expression_names.append(name)

        if raw_entry_signature != exported_entry_signature or raw_header != exported_header:
            combo_diffs.append(
                {
                    'name': name,
                    'raw_header': raw_header,
                    'exported_header': exported_header,
                    'raw_entry_signature': raw_entry_signature,
                    'exported_entry_signature': exported_entry_signature,
                }
            )

    raw_combo_count = len(raw_names)
    export_combo_count = len(exported_names)
    exact_name_coverage = float(len(shared_names) / raw_combo_count) if raw_combo_count else 1.0
    exact_entry_row_coverage = float(len(exact_entry_row_match_names) / raw_combo_count) if raw_combo_count else 1.0
    exact_header_coverage = float(len(exact_header_match_names) / raw_combo_count) if raw_combo_count else 1.0
    exact_factor_map_coverage = float(len(exact_factor_map_match_names) / raw_combo_count) if raw_combo_count else 1.0
    exact_expression_coverage = float(len(exact_expression_match_names) / direct_expression_candidate_count) if direct_expression_candidate_count else 1.0

    report = {
        'contract_version': '0.1.0',
        'supported': bool(raw_rows),
        'source_model_json': str(source_path or ''),
        'recovery_mode': str(((metadata.get('load_contract_recovery') or {}).get('mode', '') if isinstance(metadata.get('load_contract_recovery'), dict) else '') or ''),
        'raw_combo_count': raw_combo_count,
        'export_combo_count': export_combo_count,
        'raw_combo_names': raw_names,
        'export_combo_names': exported_names,
        'missing_combo_names': missing_names,
        'extra_combo_names': extra_names,
        'shared_combo_names': shared_names,
        'exact_name_coverage': exact_name_coverage,
        'exact_entry_row_match_count': len(exact_entry_row_match_names),
        'exact_entry_row_coverage': exact_entry_row_coverage,
        'exact_header_match_count': len(exact_header_match_names),
        'exact_header_coverage': exact_header_coverage,
        'exact_factor_map_match_count': len(exact_factor_map_match_names),
        'exact_factor_map_coverage': exact_factor_map_coverage,
        'direct_expression_candidate_count': direct_expression_candidate_count,
        'exact_expression_match_count': len(exact_expression_match_names),
        'exact_expression_coverage': exact_expression_coverage,
        'mismatched_entry_names': mismatched_entry_names,
        'mismatched_header_names': mismatched_header_names,
        'mismatched_factor_map_names': mismatched_factor_map_names,
        'mismatched_expression_names': mismatched_expression_names,
        'combo_diffs': combo_diffs[:12],
        'pass': bool(
            raw_combo_count == export_combo_count
            and not missing_names
            and not extra_names
            and not mismatched_entry_names
            and not mismatched_header_names
        ),
        'notes': [
            'Exact entry-row coverage is the primary round-trip signal for LOADCOMB export fidelity.',
            'Expression coverage is only scored for direct ST combinations; nested envelope descriptions may be synthesized.',
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Compare raw MIDAS LOADCOMB rows against exported editor-seed round-trip output.')
    parser.add_argument('--model-json', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--export-preview-out', type=Path, default=None)
    args = parser.parse_args()

    payload = _load_json(args.model_json)
    export_text = export_midas_loadcomb_from_model_payload(payload)
    report = build_roundtrip_report(model_payload=payload, source_path=str(args.model_json), export_text=export_text)

    if args.export_preview_out is not None:
        args.export_preview_out.parent.mkdir(parents=True, exist_ok=True)
        args.export_preview_out.write_text(export_text, encoding='utf-8')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    status = 'PASS' if report.get('pass') else 'WARN'
    print(
        f"{status} {args.model_json}: exact_entry_row_coverage={report['exact_entry_row_coverage']:.3f} "
        f"header_coverage={report['exact_header_coverage']:.3f} missing={len(report['missing_combo_names'])} extra={len(report['extra_combo_names'])}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
