"""Preserve Chen 2025 CM-C workbook coordinates without admitting measurements.

Inputs are the versioned Mendeley Data API record, its public file list, and
the original workbook. This offline extraction does not define solver inputs,
units, a comparison window, or a training/evaluation split.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

if __package__:
    from .strict_json import strict_json_loads
else:
    from strict_json import strict_json_loads


DATASET_URL = "https://data.mendeley.com/datasets/5y8dzgpg9j/1"
DATASET_API_URL = "https://data.mendeley.com/public-api/datasets/5y8dzgpg9j?version=1"
FILES_API_URL = (
    "https://data.mendeley.com/public-api/datasets/5y8dzgpg9j/files"
    "?folder_id=root&version=1&$start=0&$limit=1000"
)
DATASET_DOI = "10.17632/5y8dzgpg9j.1"
SOURCE_NAME = "Origin data.xlsx"
SOURCE_SIZE = 2_589_099
SOURCE_SHA256 = "9091e971ed8dfd1800572ea14a6b3293ced5a6f4adb70dfe26de821bf99b7825"
SOURCE_FILE_ID = "74e65ed7-664c-45e8-bcf7-cd51a4924597"
SHEET_NAME = "load-mid-span deflection"
FIRST_ROW = 2
LAST_ROW = 13481
ROW_COUNT = LAST_ROW - FIRST_ROW + 1
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_receipt(dataset_raw: bytes, files_raw: bytes) -> dict:
    dataset = strict_json_loads(dataset_raw)
    files = strict_json_loads(files_raw)
    _require(isinstance(dataset, dict) and isinstance(files, list), "source_metadata_invalid")
    doi = dataset.get("doi")
    owner = dataset.get("owner")
    license_data = dataset.get("data_licence")
    _require(dataset.get("id") == "5y8dzgpg9j" and dataset.get("version") == 1
             and isinstance(doi, dict) and doi.get("id") == DATASET_DOI,
             "dataset_identity_invalid")
    _require(isinstance(owner, dict) and owner.get("first_name") == "Yidong"
             and owner.get("last_name") == "Chen", "dataset_creator_unverified")
    _require(isinstance(license_data, dict)
             and license_data.get("short_name") == "CC BY 4.0"
             and license_data.get("url") in (
                 "http://creativecommons.org/licenses/by/4.0",
                 "https://creativecommons.org/licenses/by/4.0/",
             ), "data_license_unverified")
    _require(len(files) == 1 and isinstance(files[0], dict), "source_file_list_invalid")
    source_file = files[0]
    details = source_file.get("content_details")
    _require(source_file.get("filename") == SOURCE_NAME
             and source_file.get("id") == SOURCE_FILE_ID
             and source_file.get("size") == SOURCE_SIZE
             and isinstance(details, dict)
             and details.get("size") == SOURCE_SIZE
             and details.get("sha256_hash") == SOURCE_SHA256,
             "source_file_metadata_invalid")
    return {
        "dataset_url": DATASET_URL,
        "dataset_api_url": DATASET_API_URL,
        "files_api_url": FILES_API_URL,
        "dataset_doi": DATASET_DOI,
        "dataset_record_sha256": _sha256(dataset_raw),
        "file_list_sha256": _sha256(files_raw),
        "creator": "Yidong Chen",
        "license": "CC BY 4.0",
        "source_file_id": SOURCE_FILE_ID,
    }


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    _require(name in archive.namelist(), f"missing_xlsx_member:{name}")
    return ET.fromstring(archive.read(name))


def _decimal(value: str) -> str:
    _require(len(value) <= 64, "measurement_value_too_long")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("non_numeric_measurement_value") from exc
    _require(parsed.is_finite() and abs(parsed) < Decimal("1e9"),
             "non_finite_or_unbounded_measurement")
    return value


def parse_cm_c_sheet(workbook: bytes, *, first_row: int = FIRST_ROW,
                     last_row: int = LAST_ROW) -> list[dict[str, str | int]]:
    """Return the original G/H numeric XML text and worksheet row numbers."""
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        _require(len(names) == len(set(names)) and len(names) <= 64,
                 "duplicate_or_excess_xlsx_members")
        _require(all(not info.flag_bits & 1 and info.file_size <= 10_000_000 for info in infos)
                 and sum(info.file_size for info in infos) <= 20_000_000,
                 "encrypted_or_oversized_xlsx_member")
        sheets = [sheet for sheet in _xml(archive, "xl/workbook.xml").iter(f"{MAIN}sheet")
                  if sheet.get("name") == SHEET_NAME]
        _require(len(sheets) == 1, "cm_c_sheet_missing_or_duplicated")
        relation_id = sheets[0].get(REL_ID)
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets = [relation.get("Target")
                   for relation in relationships.iter(f"{PACKAGE_REL}Relationship")
                   if relation.get("Id") == relation_id]
        _require(targets == ["worksheets/sheet2.xml"], "cm_c_sheet_target_changed")
        shared = ["".join(node.text or "" for node in item.iter(f"{MAIN}t"))
                  for item in _xml(archive, "xl/sharedStrings.xml").iter(f"{MAIN}si")]
        cells: dict[str, ET.Element] = {}
        for cell in _xml(archive, "xl/worksheets/sheet2.xml").iter(f"{MAIN}c"):
            address = cell.get("r", "")
            if re.fullmatch(r"[GH][0-9]+", address):
                _require(address not in cells, "duplicate_cm_c_cell")
                cells[address] = cell
        label = cells.get("H1")
        _require(label is not None and label.get("t") == "s"
                 and label.find(f"{MAIN}f") is None, "cm_c_label_changed")
        label_value = label.findtext(f"{MAIN}v")
        _require(label_value is not None and label_value.isdecimal()
                 and int(label_value) < len(shared)
                 and shared[int(label_value)] == "CM-C", "cm_c_label_changed")
        _require("G1" not in cells and not any(int(address[1:]) > last_row
                                              for address in cells), "unreviewed_cm_c_tail")
        rows = []
        for number in range(first_row, last_row + 1):
            pair = [cells.get(f"{col}{number}") for col in "GH"]
            _require(all(cell is not None for cell in pair),
                     f"cm_c_measurement_pair_missing:{number}")
            values = []
            for cell in pair:
                assert cell is not None
                _require(cell.get("t") in (None, "n") and cell.find(f"{MAIN}f") is None,
                         f"cm_c_measurement_not_numeric:{number}")
                value = cell.findtext(f"{MAIN}v")
                _require(value is not None, f"cm_c_measurement_pair_missing:{number}")
                values.append(_decimal(value))
            rows.append({"source_row": number, "plot_x_xml": values[0],
                         "plot_y_xml": values[1]})
    return rows


def extract(workbook_path: Path, dataset_path: Path, files_path: Path,
            output_dir: Path) -> dict:
    workbook = workbook_path.read_bytes()
    _require(len(workbook) == SOURCE_SIZE and _sha256(workbook) == SOURCE_SHA256,
             "source_workbook_identity_mismatch")
    source = _source_receipt(dataset_path.read_bytes(), files_path.read_bytes())
    rows = parse_cm_c_sheet(workbook)
    _require(len(rows) == ROW_COUNT, "unexpected_cm_c_row_count")
    peak = max(rows, key=lambda row: Decimal(str(row["plot_y_xml"])))
    decreases = sum(Decimal(str(right["plot_x_xml"])) < Decimal(str(left["plot_x_xml"]))
                    for left, right in zip(rows, rows[1:]))
    _require(peak["source_row"] == 13391 and decreases == 5610,
             "published_curve_crosscheck_failed")
    payload = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                       for row in rows)
    receipt = {
        "schema_version": "chen-2025-cm-c-original-measurement-extraction.v1",
        "source_role": "published_experimental_measurement_source_only",
        "source": source,
        "original_file": {"name": SOURCE_NAME, "byte_length": SOURCE_SIZE,
                          "sha256": SOURCE_SHA256, "sheet": SHEET_NAME,
                          "plot_x_cells": "G2:G13481", "plot_y_cells": "H2:H13481"},
        "derived_file": {"name": "measurements.jsonl", "sha256": _sha256(payload),
                         "row_count": len(rows), "order": "original_worksheet_row",
                         "numeric_representation": "original_xlsx_xml_decimal_string"},
        "first_source_row": rows[0]["source_row"],
        "last_source_row": rows[-1]["source_row"],
        "peak_plot_y_source_row": peak["source_row"],
        "adjacent_plot_x_decrease_count": decreases,
        "distinct_specimen_count": 1,
        "admitted_training_row_count": 0,
        "admitted_locked_evaluation_row_count": 0,
        "fixed_parameter_solver_comparison_count": 0,
        "unresolved": ["plot_axis_units_in_workbook", "total_vs_per_nose_load",
                       "support_referenced_midspan_deflection_datum",
                       "specimen_specific_concrete_properties",
                       "bar_coordinates_and_model_physics_scope"],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "measurements.jsonl").write_bytes(payload)
    (output_dir / "source-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--dataset-record", type=Path, required=True)
    parser.add_argument("--file-list", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = extract(args.workbook, args.dataset_record, args.file_list, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "row_count": receipt["derived_file"]["row_count"],
                      "sha256": receipt["derived_file"]["sha256"],
                      "admitted_training_row_count": 0, "admitted_locked_evaluation_row_count": 0},
                     sort_keys=True))


if __name__ == "__main__":
    main()
