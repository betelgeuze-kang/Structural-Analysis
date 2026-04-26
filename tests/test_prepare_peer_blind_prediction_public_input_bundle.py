from pathlib import Path
import sys
import zipfile


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_peer_blind_prediction_public_input_bundle as bundle_report  # noqa: E402


def _write_minimal_xlsx(path: Path, shared_strings: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{text}</t></si>" for text in shared_strings)
            + "</sst>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
    <row r="2"><c r="A2"><v>0.0</v></c><c r="B2"><v>1.0</v></c></row>
  </sheetData>
</worksheet>""",
        )


def test_peer_public_input_bundle_report_surfaces_pending_measured_response(tmp_path: Path) -> None:
    root = tmp_path / "peer"
    root.mkdir()
    _write_minimal_xlsx(root / "GMs.xlsx", ["GM1", "Acc X [g]"])
    materials_xlsx = tmp_path / "materials.xlsx"
    _write_minimal_xlsx(materials_xlsx, ["Concrete", "Stress [ksi]"])
    with zipfile.ZipFile(root / "Materials.zip", "w") as zf:
        zf.write(materials_xlsx, arcname="Materials.xlsx")
        zf.writestr("Grout_datasheet.pdf", b"pdf")
    (root / "Construction_Drawings.pdf").write_bytes(b"pdf")

    source_manifest = {
        "expected_groups": {
            "geometry_model": {"present": True},
            "material_properties": {"present": True},
            "excitation_history": {"present": True},
            "measured_response": {"present": False},
        },
        "summary": {"required_group_pass_count": 3},
    }
    payload = bundle_report.build_report(root, source_manifest)

    assert payload["contract_pass"] is True
    assert payload["summary"]["geometry_doc_count"] == 1
    assert payload["summary"]["material_bundle_present"] is True
    assert payload["summary"]["gm_workbook_present"] is True
    assert payload["summary"]["measured_response_pending"] is True
