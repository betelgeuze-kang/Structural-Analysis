"""Lossless, positional intake of the archived ACI 369 rectangular CSV.

The descriptor row is deliberately opaque: the observed export contains a hidden
field that misaligns descriptions with headers. No units, missingness, test
configuration, canonical model or training permission is inferred here.
"""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re


# Includes repeated labels and the original trailing blank field.
ARCHIVE_HEADERS = (
    "ID",
    "References",
    "First Author",
    "Col.Name",
    "Data File",
    "Section depth (h) [in.]",
    "Section width (b) [in.]",
    "d1 [in.]",
    "d2 [in.]",
    "Clear Cover cc [in.]",
    "lc [in.]",
    "a [in.]",
    "a/d1",
    "Longi. bars along first face (perp.)",
    "Bar dia. [in.]",
    "Longi. bars along second face (perp.)",
    "Bar dia. [in.]",
    "Longi. bars in middle layers(perp.)",
    "Longi. bars in middle layers (parl.)",
    "Bar dia. [in.]",
    "fy (longi. reinf.) [psi]",
    "pL (longi. reinf.)",
    "Trans. reinf. legs perp. to load",
    "Trans. reinf. legs parl. to load",
    "Trans. bar dia. [in.]",
    "Spacing of trans. reinf. (s) [in.]",
    "fy (trans. reinf.) [psi]",
    "pt (trans. reinf. volumetric ratio)",
    "pv (trans. reinf. ratio)",
    "s/d1 (primary)",
    "s/d2 (secondary)",
    "Seismic hoops",
    "f'c [psi]",
    "Axial load(P) [kips]",
    "Axial load ratio",
    "Spliced longi. bars",
    "Splice length [in.]",
    "Splice height [in.]",
    "Test configuration",
    "Number of loading directions",
    "Maximum lateral load (primary) (Vmax1) [kips]",
    "Drift ratio at Vmax1 [%]",
    "Drift ratio at 0.8Vmax1 [%]",
    "Drift ratio at 0.25Vmax [%]",
    "Drift ratio at axial failure (primary) [%]",
    "Lateral load at axial failure (primary) [kips]",
    "Vp1 (primary) [kips]",
    "Vo1 (primary) [kips]",
    "Vp1/Vo1",
    "Maximum lateral load (secondary) (Vmax2) [kips]",
    "Drift ratio at Vmax2 [%]",
    "Drift ratio at 0.8Vmax2 [%]",
    "Drift ratio at 0.25Vmax2 [%]",
    "Drift ratio at axial failure (secondary) [%]",
    "Lateral load at axial failure (secondary) [kips]",
    "Vp2 (secondary) [kips]",
    "Vo2 (secondary) [kips]",
    "Vp2/Vo2",
    "",
)

_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


@dataclass(frozen=True)
class AciColumnArchiveRecord:
    source_sha256: str
    source_record_number: int
    cells: tuple[str, ...]

    def raw_value(self, position: int) -> str:
        """Use an explicit position; duplicate header names never collapse."""
        if type(position) is not int or not 0 <= position < len(ARCHIVE_HEADERS):
            raise ValueError("bounded integer column position required")
        return self.cells[position]

    def decimal_token_value(self, position: int) -> Decimal:
        """Parse a raw numeric token, without granting physical meaning to zero.

        No unit conversion or missing/end-point interpretation is performed.
        Empty, textual and nonfinite fields reject instead of becoming zero.
        """
        token = self.raw_value(position)
        if len(token) > 128 or not _NUMBER.fullmatch(token):
            raise ValueError("finite original numeric token required")
        try:
            value = Decimal(token)
        except InvalidOperation as exc:
            raise ValueError("finite original numeric token required") from exc
        if not value.is_finite():
            raise ValueError("finite original numeric token required")
        return value


@dataclass(frozen=True)
class AciColumnArchive:
    source_sha256: str
    source_byte_length: int
    headers: tuple[str, ...]
    descriptors: tuple[str, ...]
    records: tuple[AciColumnArchiveRecord, ...]

    @property
    def descriptor_alignment_verified(self) -> bool:
        return False

    @property
    def training_admission_granted(self) -> bool:
        return False


def decode_aci_column_archive(
    raw: bytes, *, expected_source_sha256: str
) -> AciColumnArchive:
    """Preserve captured cells; reject changed layout before typed downstream use.

    The supplied hash binds original bytes, not publisher authenticity or reuse
    rights. source_record_number counts logical CSV records, not physical lines,
    since quoted references or descriptions may contain embedded line breaks.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("bounded original archive bytes required")
    digest = hashlib.sha256(raw).hexdigest()
    if (
        type(expected_source_sha256) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256)
        or digest != expected_source_sha256
    ):
        raise ValueError("original archive SHA-256 mismatch")
    try:
        reader = csv.reader(
            io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True
        )
        header = tuple(next(reader))
        descriptors = tuple(next(reader))
        marker = next(reader)
        if header != ARCHIVE_HEADERS or len(descriptors) != len(header):
            raise ValueError("archived header/descriptor layout mismatch")
        if marker != ["DATASTART"]:
            raise ValueError("archive DATASTART marker required")
        rows = []
        identities = set()
        for number, parsed in enumerate(reader, 4):
            if number > 8195:
                raise ValueError("bounded archive record count required")
            cells = tuple(parsed)
            if len(cells) != len(header) or cells[-1] != "":
                raise ValueError("archive record width or trailing field mismatch")
            record_id = cells[0]
            if (
                not re.fullmatch(r"[1-9][0-9]{0,8}", record_id)
                or record_id in identities
            ):
                raise ValueError("unique positive archive record IDs required")
            identities.add(record_id)
            rows.append(AciColumnArchiveRecord(digest, number, cells))
    except (UnicodeDecodeError, csv.Error, StopIteration) as exc:
        raise ValueError("complete UTF-8 archive CSV required") from exc
    if not rows:
        raise ValueError("at least one archive data record required")
    return AciColumnArchive(digest, len(raw), header, descriptors, tuple(rows))
