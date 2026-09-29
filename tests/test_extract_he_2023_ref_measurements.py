from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from scripts import extract_he_2023_ref_measurements as intake


def _workbook(*, missing_c6: bool = False, formula_b5: bool = False,
              extra_tail: bool = False, text_b5: bool = False) -> bytes:
    cells = [
        '<c r="B2" t="s"><v>0</v></c>',
        '<c r="B3" t="s"><v>1</v></c>',
        '<c r="C3" t="s"><v>2</v></c>',
        '<c r="B4" t="s"><v>3</v></c>',
        '<c r="C4" t="s"><v>4</v></c>',
        '<c r="B5"><v>3.4759999999999999E-3</v></c>',
        '<c r="C5"><v>0</v></c>',
        '<c r="B6"><v>0.1</v></c>',
        '<c r="C6"><v>1.2</v></c>',
    ]
    if missing_c6:
        cells.pop()
    if formula_b5:
        cells[5] = '<c r="B5"><f>1+1</f><v>2</v></c>'
    if text_b5:
        cells[5] = '<c r="B5" t="s"><v>5</v></c>'
    if extra_tail:
        cells.append('<c r="B7"><v>0.2</v></c>')
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>' + "".join(cells) + '</sheetData></worksheet>')
    workbook = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Ref beam" sheetId="1" r:id="rId1"/></sheets></workbook>')
    relations = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
    strings = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               + "".join(f'<si><t>{value}</t></si>' for value in
                         ['LVDT results', 'Deflection', 'Load', 'mm', 'kN', '0.1']) + '</sst>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/sharedStrings.xml", strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def test_preserves_original_excel_row_and_numeric_lexemes() -> None:
    rows = intake.parse_ref_sheet(_workbook(), last_row=6)
    assert rows == [
        {"source_row": 5, "deflection_mm_xml": "3.4759999999999999E-3", "load_kN_xml": "0"},
        {"source_row": 6, "deflection_mm_xml": "0.1", "load_kN_xml": "1.2"},
    ]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"missing_c6": True}, "measurement_pair_missing:6"),
        ({"formula_b5": True}, "formula_in_measurement_channel"),
        ({"text_b5": True}, "measurement_pair_not_numeric_cells:5"),
        ({"extra_tail": True}, "unreviewed_measurement_tail"),
    ],
)
def test_rejects_non_original_or_ambiguous_measurement_channel(
    mutation: dict[str, bool], reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        intake.parse_ref_sheet(_workbook(**mutation), last_row=6)


def _record(license_id: str = "cc-by-4.0") -> bytes:
    return json.dumps({
        "id": 10082010,
        "doi": intake.DATASET_DOI,
        "metadata": {"license": {"id": license_id},
                     "creators": [{"name": "He, Shan"}],
                     "related_identifiers": [{"identifier": intake.ARTICLE_DOI,
                                              "relation": "isPublishedIn"}]},
        "files": [{"key": intake.SOURCE_NAME, "size": intake.SOURCE_SIZE,
                   "checksum": f"md5:{intake.SOURCE_MD5}"}],
    }).encode()


def test_source_rights_and_identity_are_separate_gates(tmp_path: Path) -> None:
    assert intake._record_receipt(_record())["license"] == "CC BY 4.0"
    with pytest.raises(ValueError, match="data_license_unverified"):
        intake._record_receipt(_record("other-license"))
    with pytest.raises(ValueError, match="duplicate_json_key:id"):
        intake._record_receipt(b'{"id":10082010,"id":10082011}')
    workbook = tmp_path / "fake.xlsx"
    workbook.write_bytes(_workbook())
    record = tmp_path / "record.json"
    record.write_bytes(_record())
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="source_workbook_identity_mismatch"):
        intake.extract(workbook, record, output)
    assert not output.exists()
    assert hashlib.sha256(workbook.read_bytes()).hexdigest() != intake.SOURCE_SHA256
