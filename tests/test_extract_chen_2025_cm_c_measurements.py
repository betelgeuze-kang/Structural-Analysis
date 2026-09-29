from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest

from scripts import extract_chen_2025_cm_c_measurements as intake


def _workbook(*, missing_h3: bool = False, formula_g2: bool = False,
              text_g2: bool = False, extra_tail: bool = False,
              wrong_label: bool = False) -> bytes:
    cells = [
        '<c r="H1" t="s"><v>1</v></c>' if wrong_label else '<c r="H1" t="s"><v>0</v></c>',
        '<c r="G2"><v>0</v></c>',
        '<c r="H2"><v>5.2542099999999996</v></c>',
        '<c r="G3"><v>-1.687E-4</v></c>',
        '<c r="H3"><v>5.41621</v></c>',
    ]
    if missing_h3:
        cells.pop()
    if formula_g2:
        cells[1] = '<c r="G2"><f>1-1</f><v>0</v></c>'
    if text_g2:
        cells[1] = '<c r="G2" t="s"><v>2</v></c>'
    if extra_tail:
        cells.append('<c r="G4"><v>0.1</v></c>')
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>' + "".join(cells) + '</sheetData></worksheet>')
    workbook = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="load-mid-span deflection" sheetId="2" r:id="rId2"/>'
                '</sheets></workbook>')
    relations = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
    strings = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<si><t>CM-C</t></si><si><t>ASC-C</t></si><si><t>0</t></si></sst>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/sharedStrings.xml", strings)
        archive.writestr("xl/worksheets/sheet2.xml", sheet)
    return buffer.getvalue()


def test_preserves_worksheet_rows_and_numeric_xml() -> None:
    assert intake.parse_cm_c_sheet(_workbook(), last_row=3) == [
        {"source_row": 2, "plot_x_xml": "0", "plot_y_xml": "5.2542099999999996"},
        {"source_row": 3, "plot_x_xml": "-1.687E-4", "plot_y_xml": "5.41621"},
    ]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"missing_h3": True}, "cm_c_measurement_pair_missing:3"),
        ({"formula_g2": True}, "cm_c_measurement_not_numeric:2"),
        ({"text_g2": True}, "cm_c_measurement_not_numeric:2"),
        ({"extra_tail": True}, "unreviewed_cm_c_tail"),
        ({"wrong_label": True}, "cm_c_label_changed"),
    ],
)
def test_rejects_ambiguous_or_modified_measurement_channel(
    mutation: dict[str, bool], reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        intake.parse_cm_c_sheet(_workbook(**mutation), last_row=3)


def _dataset(*, license_name: str = "CC BY 4.0") -> bytes:
    return json.dumps({
        "id": "5y8dzgpg9j", "version": 1, "doi": {"id": intake.DATASET_DOI},
        "owner": {"first_name": "Yidong", "last_name": "Chen"},
        "data_licence": {"short_name": license_name,
                         "url": "http://creativecommons.org/licenses/by/4.0"},
    }).encode()


def _files(*, sha256: str = intake.SOURCE_SHA256) -> bytes:
    return json.dumps([{
        "filename": intake.SOURCE_NAME, "id": intake.SOURCE_FILE_ID,
        "size": intake.SOURCE_SIZE,
        "content_details": {"size": intake.SOURCE_SIZE, "sha256_hash": sha256},
    }]).encode()


def test_source_rights_and_file_identity_are_distinct_gates(tmp_path: Path) -> None:
    assert intake._source_receipt(_dataset(), _files())["license"] == "CC BY 4.0"
    with pytest.raises(ValueError, match="data_license_unverified"):
        intake._source_receipt(_dataset(license_name="other"), _files())
    with pytest.raises(ValueError, match="source_file_metadata_invalid"):
        intake._source_receipt(_dataset(), _files(sha256="0" * 64))
    with pytest.raises(ValueError, match="duplicate_json_key:id"):
        intake._source_receipt(b'{"id":"5y8dzgpg9j","id":"other"}', _files())
    fake = tmp_path / "fake.xlsx"
    fake.write_bytes(_workbook())
    dataset = tmp_path / "dataset.json"
    dataset.write_bytes(_dataset())
    files = tmp_path / "files.json"
    files.write_bytes(_files())
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="source_workbook_identity_mismatch"):
        intake.extract(fake, dataset, files, output)
    assert not output.exists()
