"""Lossless source intake only: fixtures do not claim experimental validation."""

from decimal import Decimal, localcontext
import hashlib

import pytest

from structural_analysis.io.peer_structural_performance import (
    RECTANGULAR_COLUMNS,
    decode_force_displacement_history,
    decode_rectangular_properties,
)


def table(*, updates=None, headers=None, duplicate=False):
    row = ["0"] * 44
    row[0], row[1] = "1", "synthetic source specimen"
    for index, value in (updates or {}).items():
        row[index] = value
    head = headers or [label for _, label in RECTANGULAR_COLUMNS]
    lines = ["\t".join(head), "\t".join(row)]
    if duplicate:
        lines.append(lines[1])
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def test_duplicate_labels_preserve_direction_and_spacing_region():
    raw = table(updates={15: "1", 17: "3", 28: "4", 29: "75", 31: "6", 32: "150"})
    (record,) = decode_rectangular_properties(raw)
    assert record.raw_value("perpendicular_intermediate_bar_count") == "1"
    assert record.raw_value("parallel_intermediate_bar_count") == "3"
    assert record.raw_value("close_hoop_set_count") == "4"
    assert record.raw_value("wide_hoop_set_count") == "6"
    assert record.decimal_value("close_hoop_spacing_mm") == 75
    assert record.decimal_value("wide_hoop_spacing_mm") == 150
    assert record.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert len(record.cells) == 44


def test_missing_strength_remains_distinct_from_reported_zero_and_real_zero_load():
    (record,) = decode_rectangular_properties(
        table(updates={20: "--", 22: "", 8: "1,000"})
    )
    assert record.decimal_value("corner_ultimate_strength_mpa") is None
    assert record.decimal_value("intermediate_ultimate_strength_mpa") is None
    assert record.decimal_value("transverse_ultimate_strength_mpa") == 0
    assert record.decimal_value("axial_load_kn") == 0
    assert record.raw_value("equivalent_cantilever_length_mm") == "1,000"
    assert record.decimal_value("equivalent_cantilever_length_mm") == 1000


def test_layout_change_and_duplicate_specimen_number_are_rejected():
    headers = [label for _, label in RECTANGULAR_COLUMNS]
    headers[6], headers[7] = headers[7], headers[6]
    with pytest.raises(ValueError, match="layout"):
        decode_rectangular_properties(table(headers=headers))
    with pytest.raises(ValueError, match="unique"):
        decode_rectangular_properties(table(duplicate=True))
    with pytest.raises(ValueError, match="row width"):
        decode_rectangular_properties(table().rstrip() + b"\textra\n")


def test_history_preserves_reversals_repeated_observations_and_measured_origin():
    raw = b'"synthetic cyclic record"\t\r\n5\t\r\n0\t0.0005\r\n1\t2\r\n1\t2.1\r\n-2\t-3\r\n0\t-0.1\r\n'
    history = decode_force_displacement_history(raw)
    assert history.declared_pair_count == 5
    assert history.title == "synthetic cyclic record"
    assert history.points_mm_kn[0][1] == Decimal("0.0005")
    assert history.displacement_m == tuple(
        map(Decimal, ["0", ".001", ".001", "-.002", "0"])
    )
    assert history.source_numeric_tokens[2] == ("1", "2.1")
    assert history.source_sha256 == hashlib.sha256(raw).hexdigest()


def test_unit_conversion_does_not_round_under_a_low_precision_context():
    raw = b"precision fixture\n2\n1.12345678901234567890 1D+2\n-1.2 -3\n"
    with localcontext() as context:
        context.prec = 3
        history = decode_force_displacement_history(raw)
        assert (
            history.displacement_m[0].as_tuple()
            == Decimal(".00112345678901234567890").as_tuple()
        )
        assert history.points_mm_kn[0][1] == 100


@pytest.mark.parametrize(
    "body",
    [
        "sample\n3\n0 0\n1 2\n",
        "sample\n2\n0 0\n1 NaN\n",
        "sample\n2\n0 0\n1 inf\n",
        "sample\n2\n0 0\n1 2 3\n",
        "sample\n2\n0 0\n1,23 2\n",
        "sample\n2\n\n1 2\n",
        "sample\n2.0\n0 0\n1 2\n",
    ],
)
def test_corrupt_or_ambiguous_history_is_not_repaired_silently(body):
    with pytest.raises(ValueError):
        decode_force_displacement_history(body.encode())
