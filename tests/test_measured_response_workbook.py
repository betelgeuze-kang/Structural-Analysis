"""Exact measured units, provenance, grouping and rejected channel assumptions."""

from dataclasses import replace
from decimal import Decimal, localcontext
import hashlib
import io
import zipfile

import pytest

from structural_analysis.io.measured_response_workbook import (
    MeasuredChannelSpec,
    decode_measured_response_workbook,
)


def workbook():
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package = "http://schemas.openxmlformats.org/package/2006/relationships"
    headers = ("TopDisp", "BaseShear", "TopDrift", "Bar strain", "Point")
    tokens = ("-0.000E+2", "123456789012345678901234567890.123", "-1.25", "2.5", "1")
    cols = "ABCDE"
    first = "".join(
        f'<c r="{c}1" t="inlineStr"><is><t>{h}</t></is></c>'
        for c, h in zip(cols, headers)
    )
    rows = "".join(
        f'<row r="{r}">'
        + "".join(f'<c r="{c}{r}"><v>{t}</v></c>' for c, t in zip(cols, tokens))
        + "</row>"
        for r in (2, 3)
    )
    members = {
        "xl/workbook.xml": f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="Measured" sheetId="1" r:id="r1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{package}"><Relationship Id="r1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}"><sheetData><row r="1">{first}</row>{rows}</sheetData></worksheet>',
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    return out.getvalue(), headers, tokens


def decode(raw, headers, **overrides):
    quantities = ("displacement", "force", "drift_ratio", "strain", "observation_index")
    units = ("mm", "kN", "%", "%", "1")
    specs = tuple(
        MeasuredChannelSpec(c, q, u, (h,))
        for c, q, u, h in zip("ABCDE", quantities, units, headers)
    )
    args = dict(
        expected_source_sha256=hashlib.sha256(raw).hexdigest(),
        sheet_name="Measured",
        channels=specs,
        campaign_id="campaign-1",
        specimen_id="frame-1",
        test_id="unretrofitted",
    )
    return decode_measured_response_workbook(raw, **(args | overrides))


def test_all_channels_convert_exactly_under_short_decimal_context():
    raw, headers, tokens = workbook()
    with localcontext() as ctx:
        ctx.prec = 3
        result = decode(raw, headers)
        assert result.channel_si("A")[0].as_tuple() == Decimal("-0.000E-1").as_tuple()
        assert (
            result.channel_si("B")
            == (Decimal("123456789012345678901234567890123"),) * 2
        )
        assert result.channel_si("C") == (Decimal("-0.0125"),) * 2
        assert result.channel_si("D") == (Decimal("0.025"),) * 2
        assert result.channel_si("E") == (Decimal("1"),) * 2
        assert not any(ctx.flags.values())
    assert result.source.source_numeric_tokens == (tokens, tokens)
    assert result.source.source_row_numbers == (2, 3)
    assert tuple(result.si_unit(c) for c in "ABCDE") == ("m", "N", "1", "1", "1")
    assert result.campaign_id == "campaign-1" and result.specimen_id == "frame-1"
    assert result.source.source_sha256 == hashlib.sha256(raw).hexdigest()


def test_same_structure_test_states_keep_explicit_campaign_identity():
    raw, headers, _ = workbook()
    first = decode(raw, headers)
    second = decode(raw, headers, test_id="retrofitted")
    assert first.campaign_id == second.campaign_id
    assert first.specimen_id == second.specimen_id
    assert first.test_id != second.test_id


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "wrong_dimension",
        "unknown_unit",
        "duplicate",
        "gap",
        "missing",
        "depth",
        "mutable",
        "nontext",
    ],
)
def test_rejects_ambiguous_or_incomplete_channel_mapping(mutation):
    raw, headers, _ = workbook()
    specs = list(decode(raw, headers).channels)
    if mutation == "header":
        specs[0] = replace(specs[0], expected_header=("TopDisp (m)",))
    elif mutation == "wrong_dimension":
        specs[0] = replace(specs[0], source_unit="kN")
    elif mutation == "unknown_unit":
        specs[0] = replace(specs[0], source_unit="inch")
    elif mutation == "duplicate":
        specs[1] = replace(specs[1], column_id="A")
    elif mutation == "gap":
        specs[1] = replace(specs[1], column_id="G")
    elif mutation == "missing":
        specs.pop()
    elif mutation == "depth":
        specs[0] = replace(specs[0], expected_header=(None, "TopDisp"))
    elif mutation == "mutable":
        specs[0] = replace(specs[0], expected_header=["TopDisp"])
    elif mutation == "nontext":
        specs[0] = replace(specs[0], quantity=[])
    with pytest.raises(ValueError):
        decode(raw, headers, channels=tuple(specs))


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_source_sha256": "0" * 64},
        {"expected_source_sha256": "invalid"},
        {"campaign_id": ""},
        {"specimen_id": "bad\nidentity"},
        {"test_id": "a" * 161},
        {"channels": ()},
    ],
)
def test_source_and_identity_required(overrides):
    raw, headers, _ = workbook()
    with pytest.raises(ValueError):
        decode(raw, headers, **overrides)


def test_unknown_column_does_not_select_another_measurement():
    raw, headers, _ = workbook()
    result = decode(raw, headers)
    with pytest.raises(ValueError):
        result.channel_si("F")
    with pytest.raises(ValueError):
        result.si_unit("F")
