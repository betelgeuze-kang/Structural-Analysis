"""Lossless intake of PEER's documented rectangular table and measured histories.

These records are source observations, not canonical solver models, training
admission, source authentication, licensing decisions or physical qualification.
"""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re


# Preserve position as well as label: several original column labels repeat.
RECTANGULAR_COLUMNS = (
    ("record_number", "No."),
    ("specimen_name", "Specimen Name"),
    ("comments", "Comments"),
    ("concrete_strength_mpa", "f'c (MPa)"),
    ("axial_load_kn", "Axial Load (kN)"),
    ("p_delta_code", "P-D"),
    ("width_mm", "B (mm)"),
    ("depth_mm", "H (mm)"),
    ("equivalent_cantilever_length_mm", "L (mm)"),
    ("splice_length_mm", "Lsplice (mm)"),
    ("test_configuration", "Config."),
    ("corner_bar_diameter_mm", "Diameter Corner (mm)"),
    ("intermediate_bar_diameter_mm", "Diameter Interm (mm)"),
    ("longitudinal_bar_count", "Total # Bars"),
    ("perpendicular_clear_cover_mm", "Clear Cover Perpendicular to Load (mm)"),
    ("perpendicular_intermediate_bar_count", "# Intermediate Bars"),
    ("parallel_clear_cover_mm", "Clear Cover Parallel to Load (mm)"),
    ("parallel_intermediate_bar_count", "# Intermediate Bars"),
    ("longitudinal_reinforcement_ratio", "Reinf Ratio"),
    ("corner_yield_stress_mpa", "fyl corner (MPa)"),
    ("corner_ultimate_strength_mpa", "fsu long corner (MPa)"),
    ("intermediate_yield_stress_mpa", "fyl interm (MPa)"),
    ("intermediate_ultimate_strength_mpa", "fsu long interm (MPa)"),
    ("longitudinal_steel_grade", "Steel Grade"),
    ("confinement_type", "Type of confinement"),
    ("confinement_code", "Confinement code"),
    ("shear_leg_count", "Nv"),
    ("close_hoop_diameter_mm", "Region of close spacing bar dia (mm)"),
    ("close_hoop_set_count", "No. hoop sets"),
    ("close_hoop_spacing_mm", "Spacing (mm)"),
    ("wide_hoop_diameter_mm", "Region of wide spacing bar dia (mm)"),
    ("wide_hoop_set_count", "No. hoop sets"),
    ("wide_hoop_spacing_mm", "Spacing (mm)"),
    ("transverse_volumetric_ratio", "Vol Trans Reinf Ratio"),
    ("transverse_yield_stress_mpa", "fyt (MPa)"),
    ("transverse_ultimate_strength_mpa", "fsu Trans"),
    ("transverse_steel_grade", "Steel Grade Trans"),
    ("failure_code", "Failure"),
    ("l_top_raw", "Ltop"),
    ("l_bottom_raw", "Lbottom"),
    ("l_beam_raw", "Lbeam"),
    ("measured_length_mm", "Lmeasured (mm)"),
    ("n_perpendicular_raw", "Nperp"),
    ("n_parallel_raw", "Npar"),
)
_KEY_INDEX = {key: i for i, (key, _) in enumerate(RECTANGULAR_COLUMNS)}
_NUMBER = re.compile(
    r"[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eEdD][+-]?[0-9]+)?\Z"
)


def _text(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 16 * 1024 * 1024:
        raise ValueError("bounded original source bytes required")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "UTF-8 source required; preserve original encoding separately"
        ) from exc


def _number(raw):
    value = raw.strip()
    if len(value) > 128 or not _NUMBER.fullmatch(value):
        raise ValueError("finite decimal source value required")
    try:
        result = Decimal(value.replace(",", "").replace("D", "E").replace("d", "e"))
    except InvalidOperation as exc:
        raise ValueError("finite decimal source value required") from exc
    if not result.is_finite():
        raise ValueError("finite decimal source value required")
    return result


@dataclass(frozen=True)
class PeerRectangularRecord:
    source_sha256: str
    source_row_number: int
    cells: tuple[str, ...]

    def raw_value(self, key):
        return self.cells[_KEY_INDEX[key]]

    def decimal_value(self, key):
        """Explicit numeric lookup: blank/missing tokens differ from reported zero."""
        raw = self.raw_value(key)
        if raw.strip() in ("", "--", "NA", "N/A"):
            return None
        return _number(raw)


def decode_rectangular_properties(raw):
    """Require the observed 44-column order; never collapse duplicate labels."""
    rows = list(csv.reader(io.StringIO(_text(raw)), delimiter="\t", strict=True))
    if not rows or tuple(c.strip() for c in rows[0]) != tuple(
        label for _, label in RECTANGULAR_COLUMNS
    ):
        raise ValueError("exact PEER rectangular column layout required")
    while len(rows) > 1 and not rows[-1]:
        rows.pop()
    if not 2 <= len(rows) <= 10001:
        raise ValueError("bounded nonempty specimen table required")
    identity = hashlib.sha256(raw).hexdigest()
    records, seen = [], set()
    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(RECTANGULAR_COLUMNS):
            raise ValueError("original property row width differs")
        number = row[0].strip()
        if (
            not re.fullmatch(r"[1-9][0-9]*", number)
            or number in seen
            or not row[1].strip()
        ):
            raise ValueError("unique positive source number and specimen name required")
        seen.add(number)
        records.append(PeerRectangularRecord(identity, line_number, tuple(row)))
    return tuple(records)


@dataclass(frozen=True)
class PeerForceDisplacementHistory:
    source_sha256: str
    source_title_line: str
    title: str
    declared_pair_count: int
    points_mm_kn: tuple[tuple[Decimal, Decimal], ...]
    source_numeric_tokens: tuple[tuple[str, str] | tuple[str, str, str], ...]
    # PEER manual v1.0 section 3.2: optional third column, in kN. Absence
    # does not imply zero or a constant load from the specimen property table.
    axial_load_kn: tuple[Decimal, ...] | None = None

    @property
    def displacement_m(self):
        # Change only the base-ten exponent; preserve all digits regardless of
        # the caller's Decimal context precision.
        result = []
        for value, _ in self.points_mm_kn:
            parts = value.as_tuple()
            exponent = parts.exponent
            if not isinstance(exponent, int):
                raise ValueError("finite displacement required for unit conversion")
            result.append(Decimal((parts.sign, parts.digits, exponent - 3)))
        return tuple(result)


def decode_force_displacement_history(raw):
    """Preserve mm/kN observations and an optional synchronized axial kN channel.

    All rows must have the same two- or three-column layout. No sign convention,
    P-delta adjustment or commanded loading protocol is inferred from samples.
    """
    lines = _text(raw).splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 3:
        raise ValueError("title, declared count and full measured history required")
    title_fields = next(csv.reader([lines[0]], delimiter="\t", strict=True))
    if (
        not title_fields
        or not title_fields[0].strip()
        or any(x.strip() for x in title_fields[1:])
    ):
        raise ValueError("one original title required")
    count = lines[1].strip()
    if not re.fullmatch(r"[1-9][0-9]{0,5}", count):
        raise ValueError("bounded integer history count required")
    if int(count) != len(lines) - 2:
        raise ValueError("declared measured-history count differs")
    points, tokens, axial = [], [], []
    width = len(lines[2].split())
    if width not in (2, 3):
        raise ValueError("displacement/load pair and optional axial load required")
    for line in lines[2:]:
        fields = line.split()
        if len(fields) != width:
            raise ValueError("consistent measured-history column count required")
        tokens.append(tuple(fields))
        points.append((_number(fields[0]), _number(fields[1])))
        if width == 3:
            axial.append(_number(fields[2]))
    return PeerForceDisplacementHistory(
        hashlib.sha256(raw).hexdigest(),
        lines[0],
        title_fields[0],
        int(count),
        tuple(points),
        tuple(tokens),
        tuple(axial) if width == 3 else None,
    )
