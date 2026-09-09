"""Lossless observations and invalid/misleading workbook inputs."""

from decimal import Decimal
import hashlib
import io
import zipfile

import pytest

from structural_analysis.io import measured_numeric_workbook as module


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
ROWS = (
    '<row r="1"><c r="A1" t="s"><v>0</v></c>'
    '<c r="B1" t="inlineStr"><is><t>Force (kN)</t></is></c></row>'
    '<row r="2"><c r="A2"><v>-0.000E+2</v></c><c r="B2"><v>1e-03</v></c></row>'
    '<row r="3"><c r="A3"><v>-0.000E+2</v></c><c r="B3"><v>1e-03</v></c></row>'
)


def _workbook(
    rows=ROWS, *, target="worksheets/sheet1.xml", mode="Internal", extra=None
):
    members = {
        "xl/workbook.xml": (
            f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>'
            '<sheet name="Measurements" sheetId="1" r:id="r1"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{PACKAGE_REL}">'
            f'<Relationship Id="r1" Type="{REL}/worksheet" Target="{target}" '
            f'TargetMode="{mode}"/></Relationships>'
        ),
        "xl/sharedStrings.xml": (
            f'<sst xmlns="{NS}"><si><r><t>Displacement</t></r>'
            "<r><t> (mm)</t></r></si></sst>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{NS}"><dimension ref="A1:B1"/>'
            f"<sheetData>{rows}</sheetData></worksheet>"
        ),
    }
    if extra:
        members.update(extra)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return out.getvalue()


def _decode(raw, **overrides):
    return module.decode_measured_numeric_workbook(
        raw,
        **(
            {"sheet_name": "Measurements", "columns": ("A", "B"), "header_rows": 1}
            | overrides
        ),
    )


def test_preserves_all_cells_repeated_rows_signed_zero_and_header_text():
    raw = _workbook()
    table = _decode(raw)
    assert table.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert table.header_cells == (("Displacement (mm)", "Force (kN)"),)
    assert table.source_row_numbers == (2, 3)
    assert table.point_count == 2
    assert table.source_numeric_tokens == (("-0.000E+2", "1e-03"),) * 2
    assert table.channel("A")[0].as_tuple() == Decimal("-0.000E+2").as_tuple()
    assert table.channel("B") == (Decimal("0.001"),) * 2
    with pytest.raises(ValueError):
        table.channel("C")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('<c r="B2"><v>1e-03</v></c>', ""),
        ('<c r="B2">', '<c r="C2">'),
        ('<c r="A2">', '<c r="A3">'),
        ('<row r="3">', '<row r="4">'),
        ('<c r="B2"><v>1e-03</v></c>', '<c r="B2"><v>1</v></c><c r="B2"><v>2</v></c>'),
        ('<c r="B2">', '<c r="B2"><f>1+1</f>'),
        ('<c r="B2">', '<c r="B2"><v>2</v>'),
        ('<c r="B2">', '<c r="B2"><is><t>2</t></is>'),
        ('<c r="B1" t="inlineStr">', '<c r="B1" t="inlineStr"><f>1+1</f>'),
        ("<v>1e-03</v>", "<v>NaN</v>"),
        ("<v>1e-03</v>", "<v>Infinity</v>"),
        ('<c r="B2">', '<c r="B2" t="s">'),
        ("<v>0</v>", "<v>-1</v>"),
        ("<v>0</v>", "<v>123</v>"),
        ("<v>1e-03</v>", "<v>1,000</v>"),
    ],
)
def test_rejects_missing_ambiguous_formula_and_nonnumeric_observations(old, new):
    with pytest.raises(ValueError):
        _decode(_workbook(ROWS.replace(old, new, 1)))


@pytest.mark.parametrize(
    "options",
    [
        {"sheet_name": "Unknown"},
        {"header_rows": True},
        {"header_rows": 0},
        {"columns": ("A",)},
        {"columns": ("B", "A")},
        {"columns": ("A", "A")},
        {"columns": ("a", "B")},
        {"columns": ["A", "B"]},
    ],
)
def test_requires_complete_explicit_table_selection(options):
    with pytest.raises(ValueError):
        _decode(_workbook(), **options)


@pytest.mark.parametrize(
    ("target", "mode"),
    [("https://example.invalid/sheet.xml", "External"), ("../outside.xml", "Internal")],
)
def test_does_not_follow_external_or_traversing_relationships(target, mode):
    with pytest.raises(ValueError):
        _decode(_workbook(target=target, mode=mode))


def test_rejects_dtd_before_expanding_entities():
    with pytest.raises(ValueError, match="DTD"):
        _decode(
            _workbook(
                extra={
                    "xl/sharedStrings.xml": '<!DOCTYPE sst [<!ENTITY x "123">]><sst/>'
                }
            )
        )


def test_rejects_duplicate_zip_members():
    out = io.BytesIO(_workbook())
    with zipfile.ZipFile(out, "a") as archive:
        with pytest.warns(UserWarning):
            archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(ValueError, match="unique members"):
        _decode(out.getvalue())


def test_bounds_actual_expansion_and_rows(monkeypatch):
    raw = _workbook()
    monkeypatch.setattr(module, "_MAX_EXPANDED_BYTES", 4)
    with pytest.raises(ValueError, match="bounded"):
        _decode(raw)
    monkeypatch.setattr(module, "_MAX_EXPANDED_BYTES", 128 * 1024 * 1024)
    monkeypatch.setattr(module, "_MAX_ROWS", 1)
    with pytest.raises(ValueError, match="consecutive"):
        _decode(raw)


def test_rejects_nonworkbook_and_nonbyte_input():
    for raw in (b"", b"not a ZIP", "not bytes"):
        with pytest.raises(ValueError):
            _decode(raw)
