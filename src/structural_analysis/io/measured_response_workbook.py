"""Bind measured channels to explicit units and campaign/specimen/test identity.

This is a measured response input, not a commanded loading path or a canonical
structural model. Unit conversion is exact; physical sensor correspondence and
the caller's campaign grouping still require source review.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import re

from .measured_numeric_workbook import (
    MeasuredNumericWorkbook,
    decode_measured_numeric_workbook,
)


_UNITS = {
    ("displacement", "mm"): ("m", -3),
    ("displacement", "m"): ("m", 0),
    ("force", "kN"): ("N", 3),
    ("force", "N"): ("N", 0),
    ("strain", "%"): ("1", -2),
    ("strain", "1"): ("1", 0),
    ("drift_ratio", "%"): ("1", -2),
    ("drift_ratio", "1"): ("1", 0),
    ("observation_index", "1"): ("1", 0),
}


@dataclass(frozen=True)
class MeasuredChannelSpec:
    column_id: str
    quantity: str
    source_unit: str
    expected_header: tuple[str | None, ...]


@dataclass(frozen=True)
class MeasuredResponseWorkbook:
    source: MeasuredNumericWorkbook
    channels: tuple[MeasuredChannelSpec, ...]
    campaign_id: str
    specimen_id: str
    test_id: str

    def channel_si(self, column_id: str) -> tuple[Decimal, ...]:
        """Convert every original sample, retaining order and signed zero.

        Decimal multiplication/scaleb can round under ambient context precision.
        Changing the tuple exponent gives the exact power-of-ten unit conversion
        even when the caller uses a short decimal context.
        """
        spec = self.channels[self.source.column_ids.index(column_id)]
        _, shift = _UNITS[spec.quantity, spec.source_unit]
        result = []
        for value in self.source.channel(column_id):
            parts = value.as_tuple()
            if not isinstance(parts.exponent, int):
                raise ValueError("finite measured decimal required")
            try:
                converted = Decimal((parts.sign, parts.digits, parts.exponent + shift))
            except (InvalidOperation, OverflowError) as exc:
                raise ValueError("converted decimal exponent is out of range") from exc
            if not converted.is_finite():
                raise ValueError("converted decimal exponent is out of range")
            result.append(converted)
        return tuple(result)

    def si_unit(self, column_id: str) -> str:
        spec = self.channels[self.source.column_ids.index(column_id)]
        return _UNITS[spec.quantity, spec.source_unit][0]


def decode_measured_response_workbook(
    raw: bytes,
    *,
    expected_source_sha256: str,
    sheet_name: str,
    channels: tuple[MeasuredChannelSpec, ...],
    campaign_id: str,
    specimen_id: str,
    test_id: str,
) -> MeasuredResponseWorkbook:
    """Read every column with an explicit source-bound channel specification.

    Each complete header column must match exactly, including blank cells. No
    header substring guesses a unit. All channel specs use the same header depth,
    and the underlying reader requires consecutive columns starting with A.
    Campaign/specimen/test IDs are retained labels, not proof of an independent
    split. Multiple tests of one structure should retain the same campaign ID.
    """
    if (
        type(raw) is not bytes
        or type(expected_source_sha256) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256)
        or hashlib.sha256(raw).hexdigest() != expected_source_sha256
    ):
        raise ValueError("original workbook bytes must match the declared SHA-256")
    for value in (campaign_id, specimen_id, test_id):
        if type(value) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", value
        ):
            raise ValueError("explicit bounded campaign/specimen/test IDs required")
    if type(channels) is not tuple or not 1 <= len(channels) <= 256:
        raise ValueError("complete immutable channel specifications required")
    for spec in channels:
        if (
            type(spec) is not MeasuredChannelSpec
            or type(spec.column_id) is not str
            or type(spec.quantity) is not str
            or type(spec.source_unit) is not str
            or (spec.quantity, spec.source_unit) not in _UNITS
            or type(spec.expected_header) is not tuple
            or not 1 <= len(spec.expected_header) <= 32
            or any(
                type(cell) is not str and cell is not None
                for cell in spec.expected_header
            )
        ):
            raise ValueError("explicit quantity/unit and exact header tuple required")
    depth = len(channels[0].expected_header)
    if any(len(spec.expected_header) != depth for spec in channels):
        raise ValueError("one consistent source header depth required")
    table = decode_measured_numeric_workbook(
        raw,
        sheet_name=sheet_name,
        columns=tuple(spec.column_id for spec in channels),
        header_rows=depth,
    )
    for index, spec in enumerate(channels):
        actual = tuple(row[index] for row in table.header_cells)
        if actual != spec.expected_header:
            raise ValueError(f"source header mismatch in column {spec.column_id}")
    return MeasuredResponseWorkbook(
        source=table,
        channels=channels,
        campaign_id=campaign_id,
        specimen_id=specimen_id,
        test_id=test_id,
    )
