from pathlib import Path
import json
import sys
import zipfile
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import normalize_edefense_peer_measured_response_bundle as adapter  # noqa: E402


def _write_minimal_xlsx(path: Path, sheets: list[tuple[str, list[list[str]]]]) -> None:
    def _cell_ref(col_index: int, row_index: int) -> str:
        value = col_index + 1
        label = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            label = chr(65 + remainder) + label
        return f"{label}{row_index}"

    workbook_sheet_tags = []
    workbook_rel_tags = []
    sheet_xml_map: dict[str, str] = {}
    for index, (sheet_name, rows) in enumerate(sheets, start=1):
        workbook_sheet_tags.append(
            f'<sheet name="{sheet_name}" sheetId="{index}" r:id="rId{index}"/>'
        )
        workbook_rel_tags.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        row_tags = []
        for row_index, row in enumerate(rows, start=1):
            cell_tags = []
            for col_index, value in enumerate(row):
                cell_tags.append(
                    f'<c r="{_cell_ref(col_index, row_index)}" t="inlineStr"><is><t>{value}</t></is></c>'
                )
            row_tags.append(f'<row r="{row_index}">{"".join(cell_tags)}</row>')
        sheet_xml_map[f"xl/worksheets/sheet{index}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_tags)}</sheetData>'
            "</worksheet>"
        )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for index in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(workbook_sheet_tags)}</sheets>'
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(workbook_rel_tags)}'
            "</Relationships>",
        )
        for member_path, xml_text in sheet_xml_map.items():
            archive.writestr(member_path, xml_text)


def _excel_column_name(index: int) -> str:
    index += 1
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _write_minimal_inline_xlsx(path: Path, rows: list[list[str]]) -> None:
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            ref = f"{_excel_column_name(col_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _write_zip_archive(path: Path, members: dict[str, str]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for member_name, content in members.items():
            archive.writestr(member_name, content)


def test_measured_response_adapter_detects_landed_bundle(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    (root / "measured_response_acceleration.csv").write_text(
        "time_s,sensor_id,case_label,accel_x_g,accel_y_g,accel_z_g\n"
        "0.0,S01,GM1,0.1,0.0,0.0\n"
        "0.1,S01,GM1,0.2,0.0,0.0\n",
        encoding="utf-8",
    )
    (root / "measured_response_drift.csv").write_text(
        "time_s,story_label,case_label,drift_ratio_x,drift_ratio_y\n"
        "0.0,L2,GM1,0.001,0.0\n",
        encoding="utf-8",
    )
    (root / "sensor_manifest.json").write_text(
        json.dumps({"sensors": [{"sensor_id": "S01", "story_label": "L2", "component": "x", "units": "g"}]}),
        encoding="utf-8",
    )
    template = {"preferred_bundle_layout": [{"path": "measured_response_acceleration.csv"}]}
    landing_manifest = {
        "contract_pass": True,
        "landing_state": "recorded",
        "summary_line": "E-Defense/PEER measured-response landing manifest: RECORDED | matched=2 | csv=1 | accel_candidates=1 | drift_candidates=1 | sensors=1",
        "summary": {
            "matched_file_count": 2,
            "csv_file_count": 1,
            "acceleration_candidate_count": 1,
            "drift_candidate_count": 1,
            "sensor_candidate_count": 1,
        },
        "matched_files": ["measured_response_acceleration.csv", "sensor_manifest.json"],
        "expected_patterns": ["*response*.csv"],
        "source_manifest": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json",
    }
    payload = adapter.build_normalized(root, template, landing_manifest)

    assert payload["contract_pass"] is True
    assert payload["summary"]["acceleration_channel_count"] == 3
    assert payload["summary"]["sensor_row_count"] == 1
    assert payload["case_labels"] == ["GM1"]
    assert payload["summary"]["landing_manifest_matched_file_count"] == 2
    assert payload["summary"]["landing_manifest_contract_pass"] is True
    assert payload["bundle_state"]["landing_manifest_present"] is True
    assert payload["bundle_state"]["acceleration_source_format"] == "csv"
    assert payload["bundle_state"]["drift_source_format"] == "csv"
    assert payload["bundle_state"]["sensor_manifest_source_format"] == "json"
    assert payload["landing_manifest_summary"]["contract_pass"] is True
    assert payload["measured_response_landing_manifest"]["landing_state"] == "recorded"
    assert payload["summary_line"].endswith("landing_manifest=recorded")


def test_measured_response_adapter_supports_alternate_bundle_formats(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    _write_minimal_inline_xlsx(
        root / "measured_response_acceleration.xlsx",
        [
            ["time_s", "sensor_id", "case_label", "accel_x_g", "accel_y_g", "accel_z_g"],
            ["0.0", "S01", "GM2", "0.1", "0.0", "0.0"],
            ["0.1", "S01", "GM2", "0.2", "0.0", "0.0"],
        ],
    )
    (root / "measured_response_drift.txt").write_text(
        "time_s\tstory_label\tcase_label\tdrift_ratio_x\tdrift_ratio_y\n"
        "0.0\tL2\tGM2\t0.001\t0.0\n",
        encoding="utf-8",
    )
    _write_zip_archive(
        root / "sensor_manifest.zip",
        {
            "sensor_manifest.csv": (
                "sensor_id,story_label,component,units\n"
                "S01,L2,x,g\n"
                "S02,L3,y,g\n"
            )
        },
    )
    template = {"preferred_bundle_layout": [{"path": "measured_response_acceleration.csv"}]}
    landing_manifest = {
        "contract_pass": True,
        "landing_state": "recorded",
        "summary_line": "E-Defense/PEER measured-response landing manifest: RECORDED | matched=3 | csv=1 | accel_candidates=1 | drift_candidates=1 | sensors=1",
        "summary": {
            "matched_file_count": 3,
            "csv_file_count": 1,
            "acceleration_candidate_count": 1,
            "drift_candidate_count": 1,
            "sensor_candidate_count": 1,
        },
        "matched_files": ["measured_response_acceleration.xlsx", "measured_response_drift.txt", "sensor_manifest.zip"],
        "expected_patterns": ["*response*.csv"],
        "source_manifest": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json",
    }
    payload = adapter.build_normalized(root, template, landing_manifest)

    assert payload["contract_pass"] is True
    assert payload["summary"]["acceleration_channel_count"] == 3
    assert payload["summary"]["drift_channel_count"] == 2
    assert payload["summary"]["sensor_row_count"] == 2
    assert payload["bundle_state"]["acceleration_source_format"] == "xlsx"
    assert payload["bundle_state"]["drift_source_format"] == "txt"
    assert payload["bundle_state"]["sensor_manifest_source_format"] == "zip:csv"
    assert payload["acceleration_summary"]["source_format"] == "xlsx"
    assert payload["drift_summary"]["source_format"] == "txt"
    assert payload["sensor_manifest_summary"]["source_format"] == "zip:csv"
    assert payload["summary_line"].endswith("landing_manifest=recorded")


def test_measured_response_adapter_stays_pending_without_files(tmp_path: Path) -> None:
    payload = adapter.build_normalized(tmp_path, {"preferred_bundle_layout": []}, {"contract_pass": False, "summary": {}})
    assert payload["contract_pass"] is False
    assert payload["bundle_state"]["acceleration_present"] is False
    assert payload["reason_code"] == "ERR_MEASURED_RESPONSE_BUNDLE_INCOMPLETE"
    assert payload["measured_response_landing_manifest"]["contract_pass"] is False


def test_measured_response_adapter_reads_zip_txt_bundle(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    archive_path = root / "peer_measured_bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "accel_history.txt",
            "time_s\tsensor_id\tcase_label\taccel_x_g\taccel_y_g\taccel_z_g\n"
            "0.0\tS01\tGM1\t0.10\t0.00\t0.00\n"
            "0.1\tS01\tGM1\t0.15\t0.00\t0.00\n",
        )
        archive.writestr(
            "sensor_layout.csv",
            "sensor_id,story_label,component,units\nS01,L2,X,g\n",
        )
    payload = adapter.build_normalized(
        root,
        {"preferred_bundle_layout": []},
        {"contract_pass": True, "summary": {"matched_file_count": 1, "csv_file_count": 0}},
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["acceleration_channel_count"] == 3
    assert payload["summary"]["sensor_row_count"] == 1
    assert payload["summary"]["acceleration_source_format"] == "zip:txt"
    assert payload["summary"]["sensor_manifest_source_format"] == "zip:csv"
    assert payload["case_labels"] == ["GM1"]


def test_measured_response_adapter_reads_xlsx_and_infers_sensor_rows(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    workbook = root / "official_measurement_package.xlsx"
    _write_minimal_xlsx(
        workbook,
        [
            (
                "Sensor Layout",
                [
                    ["sensor_id", "story_label", "component", "units"],
                    ["S01", "L2", "X", "g"],
                ],
            ),
            (
                "Acceleration History",
                [
                    ["time_s", "sensor_id", "case_label", "accel_x_g", "accel_y_g", "accel_z_g"],
                    ["0.0", "S01", "GM1", "0.1", "0.0", "0.0"],
                    ["0.1", "S01", "GM1", "0.2", "0.0", "0.0"],
                ],
            ),
        ],
    )
    payload = adapter.build_normalized(
        root,
        {"preferred_bundle_layout": []},
        {"contract_pass": True, "summary": {"matched_file_count": 1, "csv_file_count": 0}},
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["acceleration_source_format"] == "xlsx"
    assert payload["summary"]["sensor_manifest_source_format"] == "xlsx"
    assert payload["sensor_manifest_summary"]["worksheet_name"] == "Sensor Layout"
    assert payload["case_labels"] == ["GM1"]


def test_measured_response_adapter_inferrs_sensor_rows_when_manifest_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    (root / "response_history.txt").write_text(
        "time_s\tsensor_id\tcase_label\taccel_x_g\taccel_y_g\taccel_z_g\n"
        "0.0\tS02\tGM2\t0.05\t0.00\t0.00\n"
        "0.1\tS02\tGM2\t0.08\t0.00\t0.00\n",
        encoding="utf-8",
    )

    payload = adapter.build_normalized(
        root,
        {"preferred_bundle_layout": []},
        {"contract_pass": False, "summary": {}},
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["sensor_row_count"] == 1
    assert payload["sensor_manifest_summary"]["source_format"] == "inferred"
    assert payload["sensor_manifest_summary"]["sensors"][0]["sensor_id"] == "S02"
