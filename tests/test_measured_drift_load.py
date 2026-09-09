"""Synthetic drift/load observations exercise source fidelity, not RC physics."""

from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
import hashlib

import pytest

from structural_analysis.io.measured_drift_load import decode_measured_drift_load_csv


HEADER = b"Drift ratio,Load (kN)\n"


def test_preserves_original_tokens_reversals_offsets_and_signed_zero():
    raw = HEADER + b"+0.1000,-0.00000\n+0.1000,7.5000\n-0.25000,-8.20000\n\n"
    history = decode_measured_drift_load_csv(raw)
    assert history.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert history.source_header == ("Drift ratio", "Load (kN)")
    assert history.source_numeric_tokens == (
        ("+0.1000", "-0.00000"),
        ("+0.1000", "7.5000"),
        ("-0.25000", "-8.20000"),
    )
    assert history.point_count == 3
    assert history.trailing_blank_record_count == 1
    assert (
        history.points_reported_drift_kn[0][0].as_tuple()
        == Decimal("0.1000").as_tuple()
    )
    assert (
        history.points_reported_drift_kn[0][1].as_tuple()
        == Decimal("-0.00000").as_tuple()
    )
    assert history.points_reported_drift_kn[-1] == (Decimal("-0.25"), Decimal("-8.2"))
    with pytest.raises(FrozenInstanceError):
        history.trailing_blank_record_count = 0


def test_low_precision_context_does_not_round_or_rescale_reported_drift():
    with localcontext() as context:
        context.prec = 2
        history = decode_measured_drift_load_csv(
            HEADER + b"1.234567890123456789,2.345678901234567890\n"
        )
    assert tuple(x.as_tuple() for x in history.points_reported_drift_kn[0]) == (
        Decimal("1.234567890123456789").as_tuple(),
        Decimal("2.345678901234567890").as_tuple(),
    )


def test_csv_encoding_quotes_and_trailing_empty_records_are_explicit():
    raw = b'\xef\xbb\xbfDrift ratio,Load (kN)\r\n" 1.20e-2 ","+3.00E+1"\r\n\r\n\r\n'
    history = decode_measured_drift_load_csv(raw)
    assert history.source_numeric_tokens == ((" 1.20e-2 ", "+3.00E+1"),)
    assert history.points_reported_drift_kn == ((Decimal("0.0120"), Decimal("30.0")),)
    assert history.trailing_blank_record_count == 2


def test_independent_axis_files_keep_unequal_counts_without_truncation():
    x = decode_measured_drift_load_csv(HEADER + b"0,1\n1,2\n")
    y = decode_measured_drift_load_csv(HEADER + b"0,3\n0,4\n1,5\n")
    assert (x.point_count, y.point_count) == (2, 3)
    assert y.points_reported_drift_kn[-1] == (Decimal("1"), Decimal("5"))
    assert x.source_sha256 != y.source_sha256


@pytest.mark.parametrize(
    "body",
    [
        b"0,1\n\n1,2\n",
        b"0,1\n,\n",
        b"0,\n",
        b"0,NA\n",
        b"NaN,1\n",
        b"0,Infinity\n",
        b"0,1,2\n",
        b"0\n",
        b'"0,1\n',
        b"1_000,1\n",
        b"0x10,1\n",
        b'"1,000",1\n',
        b"1\x00,2\n",
        b"1" * 129 + b",2\n",
    ],
)
def test_missing_malformed_or_nonfinite_observations_are_not_dropped(body):
    with pytest.raises(ValueError):
        decode_measured_drift_load_csv(HEADER + body)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        HEADER,
        HEADER + b"\n\n",
        b"Drift ratio,Load (N)\n0,1\n",
        b"Drift ratio (%),Load (kN)\n0,1\n",
        b"Load (kN),Drift ratio\n0,1\n",
        b"Drift ratio,Drift ratio\n0,1\n",
        b"\xff",
        bytearray(HEADER + b"0,1\n"),
    ],
)
def test_requires_original_bytes_and_observed_header(raw):
    with pytest.raises(ValueError):
        decode_measured_drift_load_csv(raw)


def test_resource_limits_reject_before_silent_truncation(monkeypatch):
    import structural_analysis.io.measured_drift_load as module

    monkeypatch.setattr(module, "_MAX_BYTES", 30)
    with pytest.raises(ValueError, match="bounded nonempty"):
        decode_measured_drift_load_csv(HEADER + b"0,12345678901234567890\n")
    monkeypatch.setattr(module, "_MAX_BYTES", 1024)
    monkeypatch.setattr(module, "_MAX_POINTS", 1)
    with pytest.raises(ValueError, match="point count"):
        decode_measured_drift_load_csv(HEADER + b"0,1\n1,2\n")
