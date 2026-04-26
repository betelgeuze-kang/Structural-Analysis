#!/usr/bin/env python3
"""Normalize landed E-Defense / PEER measured-response files into a structured artifact."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import io
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


DEFAULT_INPUT_ROOT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01")
DEFAULT_TEMPLATE = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_template.json"
)
DEFAULT_LANDING_MANIFEST = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json"
)

SOURCE_KIND_HINTS: dict[str, tuple[str, ...]] = {
    "acceleration": ("measured_response_acceleration", "acceleration", "accel", "response"),
    "drift": ("measured_response_drift", "drift"),
    "sensor_manifest": ("sensor_manifest", "sensor", "sensors"),
}
SOURCE_KIND_SUFFIXES: dict[str, tuple[str, ...]] = {
    "acceleration": (".csv", ".tsv", ".txt", ".xlsx", ".zip"),
    "drift": (".csv", ".tsv", ".txt", ".xlsx", ".zip"),
    "sensor_manifest": (".json", ".csv", ".tsv", ".txt", ".xlsx", ".zip"),
}

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _source_format_from_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        return suffix.lstrip(".")
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".zip":
        return "zip"
    if suffix == ".json":
        return "json"
    return suffix.lstrip(".") or "unknown"


def _decode_text_bytes(blob: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "latin-1"):
        try:
            return blob.decode(encoding)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


def _normalize_header_name(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _looks_like_sensor_manifest_headers(headers: list[str]) -> bool:
    normalized = {_normalize_header_name(header) for header in headers}
    sensor_hits = len(normalized & {"sensor_id", "story_label", "component", "units", "channel_id", "direction"})
    has_time_axis = any(header.startswith("time") for header in normalized)
    has_response_channels = bool(normalized & {"accel_x_g", "accel_y_g", "accel_z_g", "drift_ratio_x", "drift_ratio_y"})
    return sensor_hits >= 2 and not has_time_axis and not has_response_channels


def _sniff_dialect(sample: str, default_delimiter: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        if default_delimiter == "\t":
            return csv.excel_tab
        return csv.excel


def _read_delimited_headers_and_samples(
    handle: Any, sample_rows: int = 5, default_delimiter: str = ","
) -> tuple[list[str], list[dict[str, str]], int]:
    sample = handle.read(4096)
    if hasattr(handle, "seek"):
        handle.seek(0)
    dialect = _sniff_dialect(sample, default_delimiter=default_delimiter)
    reader = csv.DictReader(handle, dialect=dialect)
    headers = list(reader.fieldnames or [])
    rows: list[dict[str, str]] = []
    count = 0
    for row in reader:
        count += 1
        if len(rows) < sample_rows:
            rows.append({str(k): str(v) for k, v in row.items()})
    return headers, rows, count


def _read_csv_headers_and_samples(path: Path, sample_rows: int = 5) -> tuple[list[str], list[dict[str, str]], int]:
    default_delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = _decode_text_bytes(path.read_bytes())
    with io.StringIO(text) as handle:
        return _read_delimited_headers_and_samples(handle, sample_rows=sample_rows, default_delimiter=default_delimiter)


def _excel_column_index(reference: str) -> int:
    letters = "".join(ch for ch in reference if ch.isalpha()).upper()
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return max(value - 1, 0)


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.findall(f"{{{XLSX_NS}}}si"):
        text_bits = [node.text or "" for node in si.iterfind(f".//{{{XLSX_NS}}}t")]
        strings.append("".join(text_bits))
    return strings


def _xlsx_first_sheet_path(zf: zipfile.ZipFile) -> str | None:
    if "xl/workbook.xml" not in zf.namelist():
        return None
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_map: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            rel_id = str(rel.attrib.get("Id", "") or "")
            target = str(rel.attrib.get("Target", "") or "")
            if rel_id and target:
                rels_map[rel_id] = target
    first_sheet = workbook.find(f".//{{{XLSX_NS}}}sheet")
    if first_sheet is None:
        return None
    rel_id = str(first_sheet.attrib.get(f"{{{XLSX_REL_NS}}}id", "") or "")
    target = rels_map.get(rel_id, "")
    if not target:
        return None
    if not target.startswith("xl/"):
        target = f"xl/{target.lstrip('/')}"
    return target


def _score_text_against_kind(text: str, logical_kind: str) -> int:
    lower = text.lower()
    if logical_kind == "acceleration":
        score = 0
        for token in ("accel", "response", "history", "measurement"):
            if token in lower:
                score += 3
        if "drift" in lower:
            score -= 2
        return score
    if logical_kind == "drift":
        score = 0
        for token in ("drift", "disp", "story", "interstory"):
            if token in lower:
                score += 3
        if "accel" in lower:
            score -= 2
        return score
    score = 0
    for token in ("sensor", "manifest", "layout", "metadata", "channel", "measurement"):
        if token in lower:
            score += 3
    return score


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = str(cell.attrib.get("t", "") or "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iterfind(f".//{{{XLSX_NS}}}t"))
    if cell_type == "s":
        value = cell.findtext(f"{{{XLSX_NS}}}v", default="")
        try:
            index = int(value or 0)
        except Exception:
            index = 0
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    if cell_type == "b":
        value = cell.findtext(f"{{{XLSX_NS}}}v", default="")
        return "TRUE" if value == "1" else "FALSE"
    return cell.findtext(f"{{{XLSX_NS}}}v", default="") or ""


def _read_xlsx_headers_and_samples_from_zipfile(
    zf: zipfile.ZipFile, sample_rows: int = 5
) -> tuple[list[str], list[dict[str, str]], int]:
    sheet_path = _xlsx_first_sheet_path(zf)
    if not sheet_path or sheet_path not in zf.namelist():
        return [], [], 0
    shared_strings = _xlsx_shared_strings(zf)
    sheet_root = ET.fromstring(zf.read(sheet_path))
    rows: list[dict[str, str]] = []
    headers: list[str] = []
    count = 0
    for row in sheet_root.findall(f".//{{{XLSX_NS}}}sheetData/{{{XLSX_NS}}}row"):
        count += 1
        values: dict[int, str] = {}
        max_index = -1
        for cell in row.findall(f"{{{XLSX_NS}}}c"):
            reference = str(cell.attrib.get("r", "") or "")
            index = _excel_column_index(reference) if reference else len(values)
            max_index = max(max_index, index)
            values[index] = _xlsx_cell_text(cell, shared_strings)
        if count == 1:
            headers = [values.get(idx, f"column_{idx + 1}") or f"column_{idx + 1}" for idx in range(max_index + 1)]
            continue
        row_dict = {headers[idx] if idx < len(headers) else f"column_{idx + 1}": values.get(idx, "") for idx in range(max_index + 1)}
        if len(rows) < sample_rows:
            rows.append(row_dict)
    return headers, rows, max(count - 1, 0)


def _xlsx_sheet_summaries(zf: zipfile.ZipFile, sample_rows: int = 5) -> list[dict[str, Any]]:
    shared_strings = _xlsx_shared_strings(zf)
    sheet_paths: list[tuple[str, str]] = []
    if "xl/workbook.xml" in zf.namelist():
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_map: dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in zf.namelist():
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
                rel_id = str(rel.attrib.get("Id", "") or "")
                target = str(rel.attrib.get("Target", "") or "")
                if rel_id and target:
                    rels_map[rel_id] = target
        for sheet in workbook.findall(f".//{{{XLSX_NS}}}sheet"):
            rel_id = str(sheet.attrib.get(f"{{{XLSX_REL_NS}}}id", "") or "")
            target = rels_map.get(rel_id, "")
            if not target:
                continue
            if not target.startswith("xl/"):
                target = f"xl/{target.lstrip('/')}"
            sheet_paths.append((str(sheet.attrib.get("name", "") or ""), target))
    if not sheet_paths:
        fallback = _xlsx_first_sheet_path(zf)
        if fallback:
            sheet_paths.append(("", fallback))

    summaries: list[dict[str, Any]] = []
    for worksheet_name, sheet_path in sheet_paths:
        if sheet_path not in zf.namelist():
            continue
        sheet_root = ET.fromstring(zf.read(sheet_path))
        rows: list[dict[str, str]] = []
        headers: list[str] = []
        count = 0
        for row in sheet_root.findall(f".//{{{XLSX_NS}}}sheetData/{{{XLSX_NS}}}row"):
            count += 1
            values: dict[int, str] = {}
            max_index = -1
            for cell in row.findall(f"{{{XLSX_NS}}}c"):
                reference = str(cell.attrib.get("r", "") or "")
                index = _excel_column_index(reference) if reference else len(values)
                max_index = max(max_index, index)
                values[index] = _xlsx_cell_text(cell, shared_strings)
            if count == 1:
                headers = [values.get(idx, f"column_{idx + 1}") or f"column_{idx + 1}" for idx in range(max_index + 1)]
                continue
            row_dict = {
                headers[idx] if idx < len(headers) else f"column_{idx + 1}": values.get(idx, "")
                for idx in range(max_index + 1)
            }
            if len(rows) < sample_rows:
                rows.append(row_dict)
        if headers:
            summaries.append(
                {
                    "worksheet_name": worksheet_name,
                    "sheet_path": sheet_path,
                    "headers": headers,
                    "rows": rows,
                    "row_count": max(count - 1, 0),
                }
            )
    return summaries


def _pick_best_xlsx_sheet(zf: zipfile.ZipFile, logical_kind: str, sample_rows: int = 5) -> tuple[list[str], list[dict[str, str]], int, str]:
    summaries = _xlsx_sheet_summaries(zf, sample_rows=sample_rows)
    if not summaries:
        return [], [], 0, ""

    def _score(summary: dict[str, Any]) -> tuple[int, int]:
        worksheet_name = str(summary.get("worksheet_name", "") or "")
        headers = [str(item) for item in (summary.get("headers") or [])]
        header_score = _score_text_against_kind(" ".join(headers), logical_kind)
        name_score = _score_text_against_kind(worksheet_name, logical_kind)
        row_count = int(summary.get("row_count", 0) or 0)
        return (name_score + header_score, row_count)

    best = max(summaries, key=_score)
    return (
        [str(item) for item in (best.get("headers") or [])],
        [row for row in (best.get("rows") or []) if isinstance(row, dict)],
        int(best.get("row_count", 0) or 0),
        str(best.get("worksheet_name", "") or ""),
    )


def _candidate_path_score(path: Path, logical_kind: str) -> int:
    score = _score_text_against_kind(path.name, logical_kind)
    suffix = path.suffix.lower()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                member_name = _zip_member_candidates(zf.namelist(), logical_kind)
                if member_name:
                    score = max(score, _score_text_against_kind(member_name, logical_kind) + 3)
        elif suffix == ".xlsx":
            with zipfile.ZipFile(path) as zf:
                headers, _rows, _row_count, worksheet_name = _pick_best_xlsx_sheet(zf, logical_kind)
            if logical_kind == "sensor_manifest":
                if _looks_like_sensor_manifest_headers(headers):
                    score = max(score, _score_text_against_kind(f"{worksheet_name} {' '.join(headers)}", logical_kind) + 2)
            else:
                score = max(score, _score_text_against_kind(f"{worksheet_name} {' '.join(headers)}", logical_kind) + (2 if headers else 0))
        elif suffix in {".csv", ".tsv", ".txt"}:
            headers, _rows, _row_count = _read_csv_headers_and_samples(path)
            if logical_kind == "sensor_manifest":
                if _looks_like_sensor_manifest_headers(headers):
                    score = max(score, _score_text_against_kind(" ".join(headers), logical_kind) + 1)
            else:
                score = max(score, _score_text_against_kind(" ".join(headers), logical_kind) + (1 if headers else 0))
    except Exception:
        return score
    return score


def _read_xlsx_headers_and_samples(path: Path, sample_rows: int = 5) -> tuple[list[str], list[dict[str, str]], int]:
    with zipfile.ZipFile(path) as zf:
        return _read_xlsx_headers_and_samples_from_zipfile(zf, sample_rows=sample_rows)


def _summarize_tabular_source(
    source_path: str,
    source_format: str,
    headers: list[str],
    rows: list[dict[str, str]],
    row_count: int,
    worksheet_name: str = "",
) -> dict[str, Any]:
    time_headers = [header for header in headers if header.lower().startswith("time")]
    id_headers = [
        header
        for header in headers
        if _normalize_header_name(header) in {"sensor_id", "story_label", "component", "case_label", "gm_label"}
    ]
    channel_headers = [header for header in headers if header not in set(time_headers + id_headers)]
    case_labels = sorted(
        {
            str(row.get("case_label", "") or row.get("gm_label", "") or "")
            for row in rows
            if str(row.get("case_label", "") or row.get("gm_label", "") or "")
        }
    )
    return {
        "path": source_path,
        "source_format": source_format,
        "worksheet_name": worksheet_name,
        "headers": headers,
        "time_headers": time_headers,
        "id_headers": id_headers,
        "channel_headers": channel_headers,
        "channel_count": len(channel_headers),
        "row_count": row_count,
        "sample_rows": rows,
        "case_labels": case_labels,
    }


def _find_first_existing(input_root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = input_root / rel
        if path.exists():
            return path
    return None


def _csv_channel_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    headers, rows, row_count = _read_csv_headers_and_samples(path)
    time_headers = [header for header in headers if header.lower().startswith("time")]
    id_headers = [
        header
        for header in headers
        if header.lower() in {"sensor_id", "story_label", "component", "case_label", "gm_label"}
    ]
    channel_headers = [header for header in headers if header not in set(time_headers + id_headers)]
    case_labels = sorted({str(row.get("case_label", "") or row.get("gm_label", "") or "") for row in rows if str(row.get("case_label", "") or row.get("gm_label", "") or "")})
    return {
        "path": str(path),
        "headers": headers,
        "time_headers": time_headers,
        "id_headers": id_headers,
        "channel_headers": channel_headers,
        "channel_count": len(channel_headers),
        "row_count": row_count,
        "sample_rows": rows,
        "case_labels": case_labels,
    }


def _candidate_source_file(input_root: Path, preferred_paths: list[str], logical_kind: str) -> Path | None:
    suffixes = SOURCE_KIND_SUFFIXES[logical_kind]
    patterns: list[str] = []
    direct_candidates: list[Path] = []
    for rel in preferred_paths:
        if not rel:
            continue
        rel_path = Path(rel)
        haystack = f"{rel_path.as_posix().lower()} {rel_path.stem.lower()}"
        if not any(hint in haystack for hint in SOURCE_KIND_HINTS[logical_kind]):
            continue
        direct_candidates.append(input_root / rel_path)
        stem = rel_path.stem
        if not stem:
            continue
        for suffix in suffixes:
            patterns.extend([f"{stem}{suffix}", f"*{stem}*{suffix}"])
    for hint in SOURCE_KIND_HINTS[logical_kind]:
        for suffix in suffixes:
            patterns.extend([f"{hint}{suffix}", f"*{hint}*{suffix}"])

    for candidate in _unique_paths(direct_candidates):
        if candidate.exists() and candidate.is_file():
            return candidate

    seen: set[Path] = set()
    for pattern in patterns:
        try:
            matches = sorted(path for path in input_root.rglob(pattern) if path.is_file())
        except Exception:
            continue
        for match in matches:
            if match in seen:
                continue
            seen.add(match)
            return match
    fallback_candidates = sorted(
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SOURCE_KIND_SUFFIXES[logical_kind]
    )
    if fallback_candidates:
        best_path = max(
            fallback_candidates,
            key=lambda path: (_candidate_path_score(path, logical_kind), -len(path.as_posix())),
        )
        if _candidate_path_score(best_path, logical_kind) <= 0:
            return None
        return best_path
    return None


def _zip_member_candidates(member_names: list[str], logical_kind: str) -> str | None:
    suffixes = SOURCE_KIND_SUFFIXES[logical_kind]
    members = [name for name in member_names if name and not name.endswith("/")]
    if not members:
        return None

    def _score(member_name: str) -> tuple[int, int]:
        basename = Path(member_name).name
        suffix = Path(basename).suffix.lower()
        suffix_score = 2 if suffix in suffixes else 0
        hint_score = 0
        for hint in SOURCE_KIND_HINTS[logical_kind]:
            if fnmatch.fnmatch(basename.lower(), f"{hint}{suffix}".lower()) or fnmatch.fnmatch(
                basename.lower(), f"*{hint}*{suffix}".lower()
            ):
                hint_score += 4
        hint_score += _score_text_against_kind(basename, logical_kind)
        return (hint_score + suffix_score, -len(member_name))

    return max(members, key=_score)


def _read_source_table_summary(path: Path | None, logical_kind: str) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        headers, rows, row_count = _read_csv_headers_and_samples(path)
        source_format = _source_format_from_suffix(suffix)
        if logical_kind == "sensor_manifest":
            return {
                "path": str(path),
                "source_format": source_format,
                "row_count": row_count,
                "sample_rows": rows,
                "sensors": rows,
            }
        return _summarize_tabular_source(str(path), source_format, headers, rows, row_count)
    if suffix == ".xlsx":
        with zipfile.ZipFile(path) as zf:
            headers, rows, row_count, worksheet_name = _pick_best_xlsx_sheet(zf, logical_kind)
        source_format = _source_format_from_suffix(suffix)
        if logical_kind == "sensor_manifest":
            return {
                "path": str(path),
                "source_format": source_format,
                "worksheet_name": worksheet_name,
                "row_count": row_count,
                "sample_rows": rows,
                "sensors": rows,
            }
        return _summarize_tabular_source(str(path), source_format, headers, rows, row_count, worksheet_name=worksheet_name)
    if suffix == ".json" and logical_kind == "sensor_manifest":
        payload = _load_json(path)
        if isinstance(payload.get("sensors"), list):
            sensor_rows = [row for row in payload.get("sensors", []) if isinstance(row, dict)]
        elif isinstance(payload, list):
            sensor_rows = [row for row in payload if isinstance(row, dict)]
        else:
            sensor_rows = []
        return {
            "path": str(path),
            "source_format": "json",
            "row_count": len(sensor_rows),
            "sample_rows": sensor_rows[:5],
            "sensors": sensor_rows,
            "payload": payload,
        }
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as zf:
                member_name = _zip_member_candidates(zf.namelist(), logical_kind)
                if not member_name:
                    return {}
                member_suffix = Path(member_name).suffix.lower()
                source_path = f"{path}!{member_name}"
                if member_suffix in {".csv", ".tsv", ".txt"}:
                    default_delimiter = "\t" if member_suffix == ".tsv" else ","
                    with zf.open(member_name) as raw_handle:
                        text_handle = io.StringIO(_decode_text_bytes(raw_handle.read()))
                    with text_handle as handle:
                        headers, rows, row_count = _read_delimited_headers_and_samples(
                            handle,
                            default_delimiter=default_delimiter,
                        )
                    source_format = f"zip:{_source_format_from_suffix(member_suffix)}"
                    if logical_kind == "sensor_manifest":
                        return {
                            "path": source_path,
                            "source_format": source_format,
                            "row_count": row_count,
                            "sample_rows": rows,
                            "sensors": rows,
                        }
                    return _summarize_tabular_source(source_path, source_format, headers, rows, row_count)
                if member_suffix == ".xlsx":
                    with zf.open(member_name) as raw_handle:
                        member_bytes = raw_handle.read()
                    with zipfile.ZipFile(io.BytesIO(member_bytes)) as member_zip:
                        headers, rows, row_count, worksheet_name = _pick_best_xlsx_sheet(member_zip, logical_kind)
                    source_format = "zip:xlsx"
                    if logical_kind == "sensor_manifest":
                        return {
                            "path": source_path,
                            "source_format": source_format,
                            "worksheet_name": worksheet_name,
                            "row_count": row_count,
                            "sample_rows": rows,
                            "sensors": rows,
                        }
                    return _summarize_tabular_source(
                        source_path,
                        source_format,
                        headers,
                        rows,
                        row_count,
                        worksheet_name=worksheet_name,
                    )
                if member_suffix == ".json" and logical_kind == "sensor_manifest":
                    with zf.open(member_name) as raw_handle:
                        payload = json.loads(raw_handle.read().decode("utf-8"))
                    if isinstance(payload.get("sensors"), list):
                        sensor_rows = [row for row in payload.get("sensors", []) if isinstance(row, dict)]
                    elif isinstance(payload, list):
                        sensor_rows = [row for row in payload if isinstance(row, dict)]
                    else:
                        sensor_rows = []
                    return {
                        "path": source_path,
                        "source_format": "zip:json",
                        "row_count": len(sensor_rows),
                        "sample_rows": sensor_rows[:5],
                        "sensors": sensor_rows,
                        "payload": payload,
                    }
        except zipfile.BadZipFile:
            return {}
    return {}


def build_normalized(input_root: Path, template: dict[str, Any], landing_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    preferred_layout = template.get("preferred_bundle_layout") if isinstance(template.get("preferred_bundle_layout"), list) else []
    preferred_paths = [str(row.get("path", "") or "") for row in preferred_layout if isinstance(row, dict) and str(row.get("path", "") or "")]
    landing_manifest = landing_manifest if isinstance(landing_manifest, dict) else {}
    landing_summary = landing_manifest.get("summary") if isinstance(landing_manifest.get("summary"), dict) else {}
    landing_manifest_present = bool(landing_manifest)
    landing_manifest_contract_pass = bool(landing_manifest.get("contract_pass", False))

    acceleration_path = _candidate_source_file(input_root, preferred_paths, "acceleration")
    drift_path = _candidate_source_file(input_root, preferred_paths, "drift")
    sensor_manifest_path = _candidate_source_file(input_root, preferred_paths, "sensor_manifest")

    acceleration_summary = _read_source_table_summary(acceleration_path, "acceleration")
    drift_summary = _read_source_table_summary(drift_path, "drift")
    sensor_manifest_summary = _read_source_table_summary(sensor_manifest_path, "sensor_manifest")

    acceleration_present = bool(acceleration_summary)
    inferred_sensor_rows: list[dict[str, Any]] = []
    if not sensor_manifest_summary:
        inferred_seen: set[tuple[str, str, str, str]] = set()
        for summary in (acceleration_summary, drift_summary):
            sample_rows = summary.get("sample_rows") if isinstance(summary.get("sample_rows"), list) else []
            channel_headers = summary.get("channel_headers") if isinstance(summary.get("channel_headers"), list) else []
            if sample_rows:
                for row in sample_rows:
                    if not isinstance(row, dict):
                        continue
                    sensor_id = str(row.get("sensor_id", "") or row.get("channel_id", "") or "").strip()
                    story_label = str(row.get("story_label", "") or "").strip()
                    component = str(row.get("component", "") or "").strip()
                    units = str(row.get("units", "") or "").strip()
                    if sensor_id or story_label:
                        key = (sensor_id, story_label, component, units)
                        if key not in inferred_seen:
                            inferred_seen.add(key)
                            inferred_sensor_rows.append(
                                {
                                    "sensor_id": sensor_id,
                                    "story_label": story_label,
                                    "component": component,
                                    "units": units,
                                }
                            )
                if inferred_sensor_rows:
                    break
            if channel_headers:
                inferred_sensor_rows = [
                    {"sensor_id": str(header), "story_label": "", "component": "", "units": ""}
                    for header in channel_headers
                ]
                break
    metadata_present = bool(sensor_manifest_summary or inferred_sensor_rows)
    contract_pass = bool(acceleration_present and metadata_present)
    acceleration_source_format = str(acceleration_summary.get("source_format", "") or "")
    drift_source_format = str(drift_summary.get("source_format", "") or "")
    sensor_manifest_source_format = str(sensor_manifest_summary.get("source_format", "") or "")
    sensor_rows = sensor_manifest_summary.get("sensors") if isinstance(sensor_manifest_summary.get("sensors"), list) else []
    if not sensor_rows and inferred_sensor_rows:
        sensor_rows = inferred_sensor_rows
    combined_case_labels = sorted(
        {
            *[str(item) for item in (acceleration_summary.get("case_labels") or []) if str(item or "")],
            *[str(item) for item in (drift_summary.get("case_labels") or []) if str(item or "")],
        }
    )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_root": str(input_root),
        "landing_manifest": str(DEFAULT_LANDING_MANIFEST),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_MEASURED_RESPONSE_BUNDLE_INCOMPLETE",
        "reason": (
            "Measured response bundle is landed and normalized for blind-prediction compare flow."
            if contract_pass
            else "Measured response bundle is still incomplete. Acceleration history and sensor metadata are both required."
        ),
        "summary_line": (
            f"E-Defense/PEER measured-response normalize: {'PASS' if contract_pass else 'PENDING'} | "
            f"accel_channels={int(acceleration_summary.get('channel_count', 0) or 0)} | "
            f"drift_channels={int(drift_summary.get('channel_count', 0) or 0)} | "
            f"sensor_rows={len(sensor_rows)} | case_labels={len(combined_case_labels)} | "
            f"formats=accel:{acceleration_source_format or 'missing'}|drift:{drift_source_format or 'missing'}|"
            f"sensor:{sensor_manifest_source_format or 'missing'} | "
            f"landing_manifest={'recorded' if landing_manifest_present else 'missing'}"
        ),
        "summary": {
            "acceleration_channel_count": int(acceleration_summary.get("channel_count", 0) or 0),
            "drift_channel_count": int(drift_summary.get("channel_count", 0) or 0),
            "sensor_row_count": len(sensor_rows),
            "case_label_count": len(combined_case_labels),
            "landing_manifest_matched_file_count": int(landing_summary.get("matched_file_count", 0) or 0),
            "landing_manifest_contract_pass": landing_manifest_contract_pass,
            "landing_manifest_csv_file_count": int(landing_summary.get("csv_file_count", 0) or 0),
            "acceleration_source_format": acceleration_source_format,
            "drift_source_format": drift_source_format,
            "sensor_manifest_source_format": sensor_manifest_source_format,
        },
        "bundle_state": {
            "acceleration_present": acceleration_present,
            "drift_present": bool(drift_summary),
            "sensor_manifest_present": metadata_present,
            "landing_manifest_present": landing_manifest_present,
            "acceleration_source_format": acceleration_source_format,
            "drift_source_format": drift_source_format,
            "sensor_manifest_source_format": sensor_manifest_source_format,
        },
        "landing_manifest_summary": {
            "summary_line": str(landing_manifest.get("summary_line", "") or ""),
            "matched_file_count": int(landing_summary.get("matched_file_count", 0) or 0),
            "csv_file_count": int(landing_summary.get("csv_file_count", 0) or 0),
            "contract_pass": landing_manifest_contract_pass,
        },
        "measured_response_landing_manifest": landing_manifest,
        "acceleration_summary": acceleration_summary,
        "drift_summary": drift_summary,
        "sensor_manifest_summary": {
            "path": str(sensor_manifest_summary.get("path", "") or ""),
            "source_format": sensor_manifest_source_format or ("inferred" if inferred_sensor_rows else ""),
            "worksheet_name": str(sensor_manifest_summary.get("worksheet_name", "") or ""),
            "sensor_row_count": len(sensor_rows),
            "sensors": sensor_rows[:10],
        },
        "case_labels": combined_case_labels,
        "next_action": (
            "Proceed to blind-prediction benchmark-case generation."
            if contract_pass
            else "Land measured_response_acceleration.(csv|txt|tsv|xlsx|zip) and sensor_manifest.(json|csv|xlsx|zip), then rerun this adapter."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--landing-manifest", default=str(DEFAULT_LANDING_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_normalized(
        Path(args.input_root),
        _load_json(Path(args.template)),
        _load_json(Path(args.landing_manifest)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense/PEER measured-response normalized artifact: {out_path}")


if __name__ == "__main__":
    main()
