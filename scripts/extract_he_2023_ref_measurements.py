"""Preserve the licensed He 2023 Ref-beam measurements without admitting them.

Input files must be downloaded from the versioned Zenodo record. This tool is
offline: it does not infer a load convention, create a solver model, or select
training/evaluation rows.
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


RECORD_URL = "https://zenodo.org/records/10082010"
RECORD_API_URL = "https://zenodo.org/api/records/10082010"
ARTICLE_DOI = "10.1016/j.engstruct.2023.116584"
DATASET_DOI = "10.5281/zenodo.10082010"
SOURCE_NAME = "Data summary.xlsx"
SOURCE_SIZE = 276_386
SOURCE_MD5 = "738cf9caa83da2f6f41f1a6c714f4c14"
SOURCE_SHA256 = "96503244fcb5bdebd461a572e8252ce3f39d8b6f9888829fe877e2efcf09c89a"
FIRST_ROW = 5
LAST_ROW = 2636
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_receipt(raw: bytes) -> dict[str, str | int]:
    record = strict_json_loads(raw)
    _require(isinstance(record, dict), "wrong_zenodo_record")
    metadata = record.get("metadata", {})
    files = record.get("files", [])
    _require(
        isinstance(metadata, dict) and isinstance(files, list), "wrong_zenodo_record"
    )
    _require(
        record.get("id") == 10082010 and record.get("doi") == DATASET_DOI,
        "wrong_zenodo_record",
    )
    _require(
        metadata.get("license", {}).get("id") == "cc-by-4.0", "data_license_unverified"
    )
    _require(
        any(
            item.get("identifier") == ARTICLE_DOI
            and item.get("relation") == "isPublishedIn"
            for item in metadata.get("related_identifiers", [])
        ),
        "article_link_unverified",
    )
    _require(
        any(item.get("name") == "He, Shan" for item in metadata.get("creators", [])),
        "creator_unverified",
    )
    _require(
        len(files) == 1
        and files[0].get("key") == SOURCE_NAME
        and files[0].get("size") == SOURCE_SIZE
        and files[0].get("checksum") == f"md5:{SOURCE_MD5}",
        "source_file_metadata_invalid",
    )
    return {
        "record_id": 10082010,
        "record_api_url": RECORD_API_URL,
        "record_sha256": _digest(raw),
        "dataset_doi": DATASET_DOI,
        "article_doi": ARTICLE_DOI,
        "creator": "He, Shan",
        "license": "CC BY 4.0",
    }


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    _require(name in archive.namelist(), f"missing_xlsx_member:{name}")
    return ET.fromstring(archive.read(name))


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    _require(cell.find(f"{MAIN}f") is None, "formula_in_measurement_channel")
    value = cell.find(f"{MAIN}v")
    _require(value is not None and value.text is not None, "empty_measurement_cell")
    if cell.get("t") == "s":
        index = int(value.text)
        _require(0 <= index < len(shared), "shared_string_out_of_range")
        return shared[index]
    _require(cell.get("t") in (None, "n"), "non_numeric_measurement_cell")
    return value.text


def _decimal(value: str) -> str:
    _require(len(value) <= 64, "measurement_value_too_long")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("non_numeric_measurement_value") from exc
    _require(
        parsed.is_finite() and abs(parsed) < Decimal("1e9"),
        "non_finite_or_unbounded_measurement",
    )
    return value


def parse_ref_sheet(
    workbook: bytes, *, first_row: int = FIRST_ROW, last_row: int = LAST_ROW
) -> list[dict[str, str | int]]:
    """Return raw XML numeric strings with original worksheet row order."""
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        _require(
            len(names) == len(set(names)) and len(names) <= 64,
            "duplicate_or_excess_xlsx_members",
        )
        _require(
            all(
                not info.flag_bits & 1 and info.file_size <= 2_000_000 for info in infos
            )
            and sum(info.file_size for info in infos) <= 5_000_000,
            "encrypted_or_oversized_xlsx_member",
        )
        workbook_xml = _xml(archive, "xl/workbook.xml")
        sheets = [
            sheet
            for sheet in workbook_xml.iter(f"{MAIN}sheet")
            if sheet.get("name") == "Ref beam"
        ]
        _require(len(sheets) == 1, "reference_sheet_missing_or_duplicated")
        relation_id = sheets[0].get(REL_ID)
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets = [
            relation.get("Target")
            for relation in relationships.iter(f"{PACKAGE_REL}Relationship")
            if relation.get("Id") == relation_id
        ]
        _require(targets == ["worksheets/sheet1.xml"], "reference_sheet_target_changed")
        strings_xml = _xml(archive, "xl/sharedStrings.xml")
        shared = [
            "".join(node.text or "" for node in item.iter(f"{MAIN}t"))
            for item in strings_xml.iter(f"{MAIN}si")
        ]
        sheet = _xml(archive, "xl/worksheets/sheet1.xml")
        cells: dict[str, ET.Element] = {}
        for cell in sheet.iter(f"{MAIN}c"):
            address = cell.get("r", "")
            if re.fullmatch(r"[BC][0-9]+", address):
                _require(address not in cells, "duplicate_measurement_cell")
                cells[address] = cell
        for address, expected in {
            "B2": "LVDT results",
            "B3": "Deflection",
            "C3": "Load",
            "B4": "mm",
            "C4": "kN",
        }.items():
            _require(
                address in cells and _cell_text(cells[address], shared) == expected,
                f"channel_label_changed:{address}",
            )
        _require(
            not any(int(address[1:]) > last_row for address in cells),
            "unreviewed_measurement_tail",
        )
        rows = []
        for number in range(first_row, last_row + 1):
            b, c = f"B{number}", f"C{number}"
            _require(b in cells and c in cells, f"measurement_pair_missing:{number}")
            _require(
                cells[b].get("t") in (None, "n") and cells[c].get("t") in (None, "n"),
                f"measurement_pair_not_numeric_cells:{number}",
            )
            rows.append(
                {
                    "source_row": number,
                    "deflection_mm_xml": _decimal(_cell_text(cells[b], shared)),
                    "load_kN_xml": _decimal(_cell_text(cells[c], shared)),
                }
            )
    return rows


def extract(workbook_path: Path, record_path: Path, output_dir: Path) -> dict:
    workbook = workbook_path.read_bytes()
    _require(
        len(workbook) == SOURCE_SIZE
        and hashlib.md5(workbook).hexdigest() == SOURCE_MD5
        and _digest(workbook) == SOURCE_SHA256,
        "source_workbook_identity_mismatch",
    )
    source = _record_receipt(record_path.read_bytes())
    rows = parse_ref_sheet(workbook)
    _require(len(rows) == 2632, "unexpected_measurement_count")
    peak = max(rows, key=lambda row: Decimal(str(row["load_kN_xml"])))
    decreases = sum(
        Decimal(str(right["deflection_mm_xml"]))
        < Decimal(str(left["deflection_mm_xml"]))
        for left, right in zip(rows, rows[1:])
    )
    _require(
        peak["source_row"] == 2153 and decreases == 74,
        "published_curve_crosscheck_failed",
    )
    payload = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )
    receipt = {
        "schema_version": "he-2023-ref-original-measurement-extraction.v1",
        "source_role": "published_experimental_measurement_source_only",
        "source": source,
        "original_file": {
            "name": SOURCE_NAME,
            "byte_length": SOURCE_SIZE,
            "md5": SOURCE_MD5,
            "sha256": SOURCE_SHA256,
            "sheet": "Ref beam",
            "deflection_cells": "B5:B2636",
            "load_cells": "C5:C2636",
        },
        "derived_file": {
            "name": "measurements.jsonl",
            "sha256": _digest(payload),
            "row_count": len(rows),
            "order": "original_worksheet_row",
            "numeric_representation": "original_xlsx_xml_decimal_string",
        },
        "first_source_row": rows[0]["source_row"],
        "last_source_row": rows[-1]["source_row"],
        "peak_source_row": peak["source_row"],
        "adjacent_deflection_decrease_count": decreases,
        "distinct_specimen_count": 1,
        "admitted_training_row_count": 0,
        "admitted_locked_evaluation_row_count": 0,
        "fixed_parameter_solver_comparison_count": 0,
        "unresolved": [
            "total_vs_per_nose_load",
            "clear_cover_vs_bar_coordinate",
            "specimen_specific_concrete_and_steel_properties",
            "shear_bond_and_support_scope",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "measurements.jsonl").write_bytes(payload)
    (output_dir / "source-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = extract(args.workbook, args.record, args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "row_count": receipt["derived_file"]["row_count"],
                "sha256": receipt["derived_file"]["sha256"],
                "admitted_training_row_count": 0,
                "admitted_locked_evaluation_row_count": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
