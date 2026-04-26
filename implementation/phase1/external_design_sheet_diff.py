#!/usr/bin/env python3
"""Deterministic external design sheet diff for commercialization workflows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_XLSX_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_DEFAULT_KEY_CANDIDATES = ("member_id", "mark", "id", "row_id", "case_id", "member")


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        headers = [str(item) for item in (reader.fieldnames or []) if str(item).strip()]
    return headers, rows, path.stem


def _load_json_rows(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows_raw = payload if isinstance(payload, list) else payload.get("rows", [])
    rows = [row for row in rows_raw if isinstance(row, dict)]
    headers = sorted({str(key) for row in rows for key in row.keys() if str(key).strip()})
    normalized = [{header: str(row.get(header, "") or "") for header in headers} for row in rows]
    return headers, normalized, path.stem


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in cell.iter(f"{_XLSX_NS}t")) for cell in root.findall(f"{_XLSX_NS}si")]


def _xlsx_sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {str(row.attrib.get("Id", "")): str(row.attrib.get("Target", "")) for row in rels}
    sheets = workbook.find(f"{_XLSX_NS}sheets")
    if sheets is None:
        return []
    out: list[tuple[str, str]] = []
    for sheet in sheets:
        name = str(sheet.attrib.get("name", "") or "")
        rel_id = str(sheet.attrib.get(f"{_XLSX_REL_NS}id", "") or "")
        target = rel_map.get(rel_id, "")
        if name and target:
            out.append((name, f"xl/{target}" if not target.startswith("xl/") else target))
    return out


def _xlsx_rows(zf: zipfile.ZipFile, target: str, shared: list[str]) -> list[list[str]]:
    root = ET.fromstring(zf.read(target))
    rows: list[list[str]] = []
    for row in root.findall(f".//{_XLSX_NS}row"):
        values: list[str] = []
        for cell in row.findall(f"{_XLSX_NS}c"):
            value_node = cell.find(f"{_XLSX_NS}v")
            value = str(value_node.text or "") if value_node is not None and value_node.text is not None else ""
            if str(cell.attrib.get("t", "") or "") == "s" and value:
                try:
                    value = shared[int(value)]
                except Exception:
                    pass
            values.append(value)
        rows.append(values)
    return rows


def _load_xlsx_rows(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    with zipfile.ZipFile(path) as zf:
        sheet_targets = _xlsx_sheet_targets(zf)
        if not sheet_targets:
            return [], [], ""
        shared = _xlsx_shared_strings(zf)
        sheet_name, sheet_path = sheet_targets[0]
        raw_rows = _xlsx_rows(zf, sheet_path, shared)
    if not raw_rows:
        return [], [], sheet_name
    headers = [str(cell).strip() for cell in raw_rows[0] if str(cell).strip()]
    rows: list[dict[str, str]] = []
    for raw in raw_rows[1:]:
        if not any(str(cell).strip() for cell in raw):
            continue
        row = {
            header: str(raw[index]).strip() if index < len(raw) else ""
            for index, header in enumerate(headers)
        }
        rows.append(row)
    return headers, rows, sheet_name


def load_tabular_rows(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return _load_csv_rows(path)
    if suffix == ".json":
        return _load_json_rows(path)
    if suffix == ".xlsx":
        return _load_xlsx_rows(path)
    raise ValueError(f"unsupported sheet format: {path.suffix}")


def _resolve_key_field(
    baseline_headers: list[str],
    revised_headers: list[str],
    key_fields: tuple[str, ...] = (),
) -> str:
    candidates = tuple(key_fields) + _DEFAULT_KEY_CANDIDATES
    baseline = {str(header).strip() for header in baseline_headers}
    revised = {str(header).strip() for header in revised_headers}
    for candidate in candidates:
        normalized = str(candidate).strip()
        if normalized and normalized in baseline and normalized in revised:
            return normalized
    shared = sorted(baseline & revised)
    if not shared:
        raise ValueError("no shared columns found between baseline and revised sheets")
    return shared[0]


def build_external_design_sheet_diff(
    *,
    baseline_path: Path,
    revised_path: Path,
    key_fields: tuple[str, ...] = (),
    numeric_tolerance: float = 1.0e-6,
    max_rows: int = 50,
) -> dict[str, Any]:
    baseline_headers, baseline_rows, baseline_sheet = load_tabular_rows(baseline_path)
    revised_headers, revised_rows, revised_sheet = load_tabular_rows(revised_path)
    key_field = _resolve_key_field(baseline_headers, revised_headers, key_fields=key_fields)
    shared_columns = [column for column in baseline_headers if column in set(revised_headers)]
    baseline_lookup = {
        str(row.get(key_field, "")).strip(): row
        for row in baseline_rows
        if str(row.get(key_field, "")).strip()
    }
    revised_lookup = {
        str(row.get(key_field, "")).strip(): row
        for row in revised_rows
        if str(row.get(key_field, "")).strip()
    }
    changed_rows: list[dict[str, Any]] = []
    added_row_keys = sorted(key for key in revised_lookup if key not in baseline_lookup)
    removed_row_keys = sorted(key for key in baseline_lookup if key not in revised_lookup)
    max_numeric_delta = 0.0

    for row_key in sorted(set(baseline_lookup) & set(revised_lookup)):
        before = baseline_lookup[row_key]
        after = revised_lookup[row_key]
        changed_columns: list[str] = []
        numeric_deltas: dict[str, float] = {}
        for column in shared_columns:
            if column == key_field:
                continue
            before_value = str(before.get(column, "") or "").strip()
            after_value = str(after.get(column, "") or "").strip()
            if before_value == after_value:
                continue
            changed_columns.append(column)
            before_num = _safe_float(before_value)
            after_num = _safe_float(after_value)
            if before_num is not None and after_num is not None:
                delta = abs(after_num - before_num)
                if delta > float(numeric_tolerance):
                    numeric_deltas[column] = float(delta)
                    max_numeric_delta = max(max_numeric_delta, float(delta))
        if not changed_columns:
            continue
        changed_rows.append(
            {
                "row_key": row_key,
                "changed_columns": changed_columns,
                "changed_column_count": len(changed_columns),
                "max_numeric_delta": float(max(numeric_deltas.values(), default=0.0)),
                "numeric_delta_columns": sorted(numeric_deltas),
                "before": {column: str(before.get(column, "") or "") for column in shared_columns},
                "after": {column: str(after.get(column, "") or "") for column in shared_columns},
            }
        )

    changed_rows.sort(key=lambda row: (float(row["max_numeric_delta"]), int(row["changed_column_count"])), reverse=True)
    summary_line = (
        f"External design sheet diff: {'PASS' if baseline_rows or revised_rows else 'CHECK'} | "
        f"sheet={revised_sheet or revised_path.stem} | key={key_field} | "
        f"changed={len(changed_rows)} | added={len(added_row_keys)} | removed={len(removed_row_keys)} | "
        f"max_delta={max_numeric_delta:.4f}"
    )
    return {
        "schema_version": "1.0",
        "report_family": "external_design_sheet_diff",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "baseline_path": str(baseline_path),
            "revised_path": str(revised_path),
            "baseline_sheet_name": baseline_sheet,
            "revised_sheet_name": revised_sheet,
            "key_field": key_field,
            "numeric_tolerance": float(numeric_tolerance),
        },
        "summary": {
            "baseline_row_count": int(len(baseline_lookup)),
            "revised_row_count": int(len(revised_lookup)),
            "changed_row_count": int(len(changed_rows)),
            "added_row_count": int(len(added_row_keys)),
            "removed_row_count": int(len(removed_row_keys)),
            "max_numeric_delta": float(max_numeric_delta),
            "shared_column_count": int(len(shared_columns)),
            "key_field": key_field,
        },
        "checks": {
            "key_field_present_pass": bool(key_field),
            "shared_columns_present_pass": bool(shared_columns),
        },
        "changed_rows": changed_rows[:max_rows],
        "added_row_keys": added_row_keys[:max_rows],
        "removed_row_keys": removed_row_keys[:max_rows],
        "summary_line": summary_line,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "external design sheet diff generated",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--revised", required=True)
    parser.add_argument("--key-fields", default="")
    parser.add_argument("--numeric-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    payload = build_external_design_sheet_diff(
        baseline_path=Path(args.baseline),
        revised_path=Path(args.revised),
        key_fields=tuple(token.strip() for token in str(args.key_fields).split(",") if token.strip()),
        numeric_tolerance=float(args.numeric_tolerance),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
