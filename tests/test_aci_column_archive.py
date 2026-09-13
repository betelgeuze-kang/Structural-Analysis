"""Archive layout and raw source values must survive before source interpretation."""

import csv
from decimal import Decimal, localcontext
import hashlib
import io

import pytest

from structural_analysis.io.aci_column_archive import (
    ARCHIVE_HEADERS,
    decode_aci_column_archive,
)


def fixture_rows():
    first = ["1", 'Author, A.\n"Original report"', "Author", "A1", "/archive/1.csv"]
    first += ["0"] * 53 + [""]
    first[14], first[16], first[19] = "0.25", "0.50", "0.75"
    first[5] = "1.2345678901234567890123456789"
    first[6] = "-0.000"
    second = first.copy()
    second[:4] = ["2", "Different report", "Other author", "A1"]
    descriptors = [""] * 59
    # The real export's misplaced history description must never label depth.
    descriptors[5] = '"desc":"History of lateral loads and displacements"'
    return [list(ARCHIVE_HEADERS), descriptors, ["DATASTART"], first, second]


def encode(rows):
    output = io.StringIO(newline="")
    csv.writer(output).writerows(rows)
    return output.getvalue().encode()


def decode(raw):
    return decode_aci_column_archive(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )


def test_preserves_duplicate_headers_distinct_bars_embedded_lines_and_unaligned_metadata():
    rows = fixture_rows()
    raw = encode(rows)
    table = decode(raw)
    assert table.source_byte_length == len(raw)
    assert table.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert table.headers == tuple(rows[0])
    assert table.descriptors == tuple(rows[1])
    assert [r.cells for r in table.records] == [tuple(r) for r in rows[3:]]
    assert [r.source_record_number for r in table.records] == [4, 5]
    assert all(r.source_sha256 == table.source_sha256 for r in table.records)
    assert [table.records[0].raw_value(i) for i in [14, 16, 19]] == [
        "0.25",
        "0.50",
        "0.75",
    ]
    assert not table.descriptor_alignment_verified
    assert not table.training_admission_granted


def test_numeric_lookup_preserves_exact_decimal_and_signed_zero_without_units():
    record = decode(encode(fixture_rows())).records[0]
    with localcontext() as context:
        context.prec = 2
        assert record.decimal_token_value(5) == Decimal(
            "1.2345678901234567890123456789"
        )
        assert record.decimal_token_value(6).as_tuple() == Decimal("-0.000").as_tuple()


@pytest.mark.parametrize(
    "value", ["", "NA", "NaN", "Infinity", "1e9999999999999999999999", "9" * 129]
)
def test_missing_nonfinite_and_unrepresentable_values_are_not_zero(value):
    rows = fixture_rows()
    rows[3][5] = value
    record = decode(encode(rows)).records[0]
    assert record.raw_value(5) == value
    with pytest.raises(ValueError, match="finite original numeric"):
        record.decimal_token_value(5)


@pytest.mark.parametrize("position", [True, -1, 59, 5.0, "5"])
def test_positional_access_rejects_ambiguous_or_out_of_bounds_indices(position):
    with pytest.raises(ValueError, match="integer column position"):
        decode(encode(fixture_rows())).records[0].raw_value(position)


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "descriptor_width",
        "marker",
        "row_width",
        "trailing",
        "duplicate_id",
        "zero_id",
        "no_records",
    ],
)
def test_rehashed_malformed_structure_still_rejected(mutation):
    rows = fixture_rows()
    if mutation == "header":
        rows[0][5] = "Section depth (h) [mm]"
    elif mutation == "descriptor_width":
        rows[1].pop()
    elif mutation == "marker":
        rows[2] = ["DATASTART", ""]
    elif mutation == "row_width":
        rows[3].pop()
    elif mutation == "trailing":
        rows[3][-1] = "unmapped value"
    elif mutation == "duplicate_id":
        rows[4][0] = rows[3][0]
    elif mutation == "zero_id":
        rows[3][0] = "0"
    else:
        rows = rows[:3]
    with pytest.raises(ValueError):
        decode(encode(rows))


def test_source_bytes_hash_required_and_truncated_utf8_or_quotes_reject():
    raw = encode(fixture_rows())
    with pytest.raises(ValueError, match="SHA-256"):
        decode_aci_column_archive(
            raw + b"\n", expected_source_sha256=hashlib.sha256(raw).hexdigest()
        )
    for broken in [b"\xff", b'"unterminated', encode(fixture_rows()[:2])]:
        with pytest.raises(ValueError):
            decode(broken)
