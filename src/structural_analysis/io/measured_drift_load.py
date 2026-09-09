"""Preserve measured drift/load CSVs without guessing drift units or time bases.

The observed header declares kN, but ``Drift ratio`` does not establish whether
its values are fractions or percentages. These observations are not commanded
displacements, synchronized biaxial samples, or solver training targets.
"""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re


_HEADER = ("Drift ratio", "Load (kN)")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_MAX_BYTES = 16 * 1024 * 1024
_MAX_POINTS = 200_000


@dataclass(frozen=True)
class MeasuredDriftLoadHistory:
    source_sha256: str
    source_header: tuple[str, str]
    source_numeric_tokens: tuple[tuple[str, str], ...]
    points_reported_drift_kn: tuple[tuple[Decimal, Decimal], ...]
    trailing_blank_record_count: int

    @property
    def point_count(self) -> int:
        return len(self.points_reported_drift_kn)


def _number(token: str) -> Decimal:
    value = token.strip()
    if not 0 < len(value) <= 128 or not _NUMBER.fullmatch(value):
        raise ValueError("finite decimal drift/load cell required")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("finite decimal drift/load cell required") from exc
    if not result.is_finite():
        raise ValueError("finite decimal drift/load cell required")
    return result


def decode_measured_drift_load_csv(raw: bytes) -> MeasuredDriftLoadHistory:
    """Decode the observed two-column layout without changing any observation.

    CSV cell text, decimal exponents, signed zeros and repeated samples remain in
    source order. Only empty CSV records at the end are separated, with their
    count retained. Empty interior records and missing cells are errors. No
    drift-to-displacement conversion or cross-file alignment is performed.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        raise ValueError("bounded nonempty original CSV bytes required")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("UTF-8 original CSV bytes required") from exc
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if header is None or tuple(header) != _HEADER:
            raise ValueError("exact Drift ratio,Load (kN) header required")
        tokens: list[tuple[str, str]] = []
        points: list[tuple[Decimal, Decimal]] = []
        trailing_blank_records = 0
        for row in reader:
            if not row:
                trailing_blank_records += 1
                continue
            if trailing_blank_records:
                raise ValueError("interior blank CSV record is not an observation")
            if len(row) != 2:
                raise ValueError("exactly two drift/load cells required")
            if len(points) >= _MAX_POINTS:
                raise ValueError("bounded drift/load point count required")
            pair = (row[0], row[1])
            points.append((_number(pair[0]), _number(pair[1])))
            tokens.append(pair)
    except csv.Error as exc:
        raise ValueError("well-formed original CSV required") from exc
    if not points:
        raise ValueError("at least one measured drift/load observation required")
    return MeasuredDriftLoadHistory(
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_header=_HEADER,
        source_numeric_tokens=tuple(tokens),
        points_reported_drift_kn=tuple(points),
        trailing_blank_record_count=trailing_blank_records,
    )
