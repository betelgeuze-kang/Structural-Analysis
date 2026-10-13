"""Read a complete corrected sensor CSV as a declared ordinal reference.

This is an input compiler for the native ordinal-history profile.  It does not
identify a sensor reduction formula, recover a physical clock or tare, choose
material laws, or admit a source-to-model physical comparison automatically.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import math
import os
from pathlib import Path
import stat
from typing import TYPE_CHECKING

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

if TYPE_CHECKING:
    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
        OrdinalHistoryPlan,
    )

CORRECTED_SENSOR_REFERENCE_SCOPE = "declared-rate-independent-channel-reference.v1"
MAX_SENSOR_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SENSOR_RECORDS = 65536
INCH_TO_M = 0.0254
KIP_TO_KN = 0.45359237 * 9.80665
_HEADER_ROLES = (
    "Sensor_Data",
    "Sensor_Name",
    "Sensor_Type",
    "Sensor_Direction",
    "Measurement_Type",
    "Sensor_Unit",
    "Sensor_Time",
)


def _hash_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 512:
        raise ValueError(f"{name} must be a nonempty bounded string")
    return value


def _digest(value: object) -> str:
    if (
        type(value) is not str
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(c not in "0123456789abcdef" for c in value[7:])
    ):
        raise ValueError("source checksum must be a lowercase prefixed SHA-256")
    return value


@dataclass(frozen=True)
class CorrectedSensorReferenceMapping:
    """Frozen, explicit signs; unit conversion is fixed and no retare is applied."""

    source_id: str
    target_channel: str
    axial_channel: str
    observed_force_channel: str
    target_sign: int
    axial_sign: int
    observed_force_sign: int
    declaration: str

    def __post_init__(self) -> None:
        for name in (
            "source_id",
            "target_channel",
            "axial_channel",
            "observed_force_channel",
            "declaration",
        ):
            _text(getattr(self, name), name)
        if (
            len({self.target_channel, self.axial_channel, self.observed_force_channel})
            != 3
        ):
            raise ValueError("select three distinct source channels")
        for name in ("target_sign", "axial_sign", "observed_force_sign"):
            value = getattr(self, name)
            if type(value) is not int or value not in (-1, 1):
                raise ValueError("channel signs must be explicitly -1 or +1")

    def to_dict(self) -> dict:
        return {
            "schema_version": CORRECTED_SENSOR_REFERENCE_SCOPE,
            "source_id": self.source_id,
            "target_channel": self.target_channel,
            "axial_channel": self.axial_channel,
            "observed_force_channel": self.observed_force_channel,
            "target_sign": self.target_sign,
            "axial_sign": self.axial_sign,
            "observed_force_sign": self.observed_force_sign,
            "declaration": self.declaration,
            "target_source_unit": "in",
            "axial_source_unit": "kip",
            "observed_force_source_unit": "kip",
            "target_m_per_source_unit": INCH_TO_M,
            "force_kn_per_source_unit": KIP_TO_KN,
            "source_offset_or_retare": "none",
            "time_role": "source ordinal; no seconds or rate inference",
            "source_measurement_formula_confirmed": False,
            "independent_physical_validation": False,
        }


@dataclass(frozen=True)
class CompiledSensorReference:
    """All numerical rows, including repeats, with original row identities."""

    plan: OrdinalHistoryPlan
    mapping: CorrectedSensorReferenceMapping
    header_sha256: str
    source_bytes: int
    source_record_indices: tuple[int, ...]
    observed_force_kn: tuple[float, ...]


def _number(text: str, name: str) -> float:
    if not text or text != text.strip():
        raise ValueError(f"missing or padded numeric {name}")
    try:
        value = float(text)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"invalid numeric {name}") from exc
    if not math.isfinite(value):
        raise ValueError(f"nonfinite numeric {name}")
    return value


def _open_source_no_links(source: Path) -> int:
    """Pin each directory and refuse symlinks in every path component."""

    absolute = source if source.is_absolute() else Path.cwd() / source
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent_fd = os.open(absolute.anchor, directory_flags)
    try:
        for component in absolute.parts[1:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        return os.open(
            absolute.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)


def compile_corrected_sensor_reference(
    path: str | Path,
    *,
    expected_source_sha256: str,
    expected_record_count: int,
    mapping: CorrectedSensorReferenceMapping,
) -> CompiledSensorReference:
    """Require the whole checksum/count before creating any executable plan.

    Source rows are zero-based CSV record indices, including comments/headers;
    they are not claimed to be physical timestamps or unprocessed DAQ records.
    The entire file and every parsed data cell are hashed.  Non-selected sensor
    columns remain bound to the plan through each source-row hash and source
    file checksum.  This function executes no numerical solver or worker.
    """

    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
        HistoryRow,
        OrdinalHistoryPlan,
    )

    expected_source_sha256 = _digest(expected_source_sha256)
    if (
        type(expected_record_count) is not int
        or not 1 <= expected_record_count <= MAX_SENSOR_RECORDS
    ):
        raise ValueError("expected complete record count is outside profile admission")
    if type(mapping) is not CorrectedSensorReferenceMapping:
        raise ValueError("explicit corrected-sensor reference mapping required")
    source = Path(path)
    name = source.name.lower()
    if (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
        or ".env." in name
    ):
        raise ValueError("environment files are not sensor inputs")
    if source.suffix.lower() != ".csv":
        raise ValueError("the sensor source must be a CSV file")
    fd = _open_source_no_links(source)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 0 < before.st_size <= MAX_SENSOR_SOURCE_BYTES
        ):
            raise ValueError("sensor source must be a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_SENSOR_SOURCE_BYTES + 1)
        after = os.fstat(fd)
        if (
            len(raw) != before.st_size
            or len(raw) > MAX_SENSOR_SOURCE_BYTES
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise ValueError("sensor source changed during the bounded read")
    finally:
        os.close(fd)
    if _hash_bytes(raw) != expected_source_sha256:
        raise ValueError("complete source checksum mismatch")
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
        comments: list[list[str]] = []
        metadata: list[list[str]] = []
        rows: list = []
        source_indices: list[int] = []
        observed: list[float] = []
        width = None
        for source_index, cells in enumerate(reader):
            if not cells or any(len(cell.encode("utf-8")) > 512 for cell in cells):
                raise ValueError("empty or oversized CSV source record")
            if width is None:
                width = len(cells)
            if len(cells) != width or not 4 <= width <= 64:
                raise ValueError("CSV source record width mismatch")
            if not metadata and cells[0].startswith("#"):
                if len(comments) >= 32:
                    raise ValueError("too many CSV source comment records")
                comments.append(cells)
                continue
            if len(metadata) < len(_HEADER_ROLES):
                if cells[0] != _HEADER_ROLES[len(metadata)]:
                    raise ValueError("corrected sensor metadata role/order mismatch")
                metadata.append(cells)
                if len(metadata) == len(_HEADER_ROLES):
                    if metadata[0][1] != "Corrected" or metadata[-1][1] != "0":
                        raise ValueError(
                            "only the explicitly declared corrected ordinal source is admitted"
                        )
                    names = metadata[1]
                    if (
                        names[0] != "Sensor_Name"
                        or names[1] != "Time"
                        or len(set(names)) != width
                    ):
                        raise ValueError(
                            "source sensor names must be distinct with Time first"
                        )
                    selected = (
                        mapping.target_channel,
                        mapping.axial_channel,
                        mapping.observed_force_channel,
                    )
                    if any(name not in names for name in selected):
                        raise ValueError("unknown selected source channel")
                    target, axial, lateral = (names.index(name) for name in selected)
                    for index, sensor_type, quantity, unit in (
                        (target, "Displacement", "displacement", "in"),
                        (axial, "Force", "force", "kip"),
                        (lateral, "Force", "force", "kip"),
                    ):
                        if (
                            metadata[2][index],
                            metadata[4][index],
                            metadata[5][index],
                        ) != (sensor_type, quantity, unit):
                            raise ValueError(
                                "selected source channel type or unit mismatch"
                            )
                continue
            ordinal = len(rows)
            if ordinal >= expected_record_count:
                raise ValueError(
                    "source has more than the declared complete record count"
                )
            if cells[0] != "" or cells[1] != str(ordinal):
                raise ValueError("source ordinal is missing, reordered or noncanonical")
            target_m = (
                _number(cells[target], "target") * INCH_TO_M * mapping.target_sign
            )
            axial_kn = (
                _number(cells[axial], "axial force") * KIP_TO_KN * mapping.axial_sign
            )
            observed_kn = (
                _number(cells[lateral], "observed force")
                * KIP_TO_KN
                * mapping.observed_force_sign
            )
            if not all(math.isfinite(v) for v in (target_m, axial_kn, observed_kn)):
                raise ValueError("source unit conversion overflow")
            row_hash = canonical_hash(
                {"schema_version": "corrected-sensor-csv-record.v1", "cells": cells}
            )
            rows.append(HistoryRow(ordinal, source_index, row_hash, target_m, axial_kn))
            source_indices.append(source_index)
            observed.append(observed_kn)
        if len(metadata) != len(_HEADER_ROLES) or len(rows) != expected_record_count:
            raise ValueError(
                "source does not contain the declared complete record count"
            )
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("invalid UTF-8 or CSV source") from exc
    header_hash = canonical_hash({"comments": comments, "metadata": metadata})
    mapping_hash = canonical_hash(
        {"mapping": mapping.to_dict(), "source_header_sha256": header_hash}
    )
    plan = OrdinalHistoryPlan(
        tuple(rows), mapping.source_id, expected_source_sha256, mapping_hash
    )
    return CompiledSensorReference(
        plan, mapping, header_hash, len(raw), tuple(source_indices), tuple(observed)
    )
