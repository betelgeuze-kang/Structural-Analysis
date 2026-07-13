"""Strict, SI-normalizing grammar for the initial MIDAS MGT v2 subset.

The parsers in this module intentionally accept only rows whose structural
meaning can be carried into ModelIR without positional-field recovery or
source-unit assumptions.  They parse already identified logical rows; block
sequencing and ``*USE-STLD`` state belong to the document parser above this
layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, radians, tanh
import re


_FORCE_TO_N = {"N": ("N", 1.0), "KN": ("kN", 1.0e3), "MN": ("MN", 1.0e6)}
_LENGTH_TO_M = {"M": ("m", 1.0), "MM": ("mm", 1.0e-3), "CM": ("cm", 1.0e-2)}
_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_NODE_ATOM_RE = re.compile(
    r"\s*(?P<start>\d+)(?:\s*to\s*(?P<end>\d+)"
    r"(?:\s*by\s*(?P<step>\d+))?)?(?=\s|$)",
    re.IGNORECASE,
)
_DOF_LABELS = ("Dx", "Dy", "Dz", "Rx", "Ry", "Rz")
_MAX_EXPANDED_NODE_IDS = 1_000_000


class MGTGrammarError(ValueError):
    """A stable, machine-readable rejection from the strict MGT grammar."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


@dataclass(frozen=True, slots=True)
class LogicalRow:
    """One data row after block/header recognition, with source provenance."""

    text: str
    line_number: int = 0
    source: str = ""

    @property
    def raw(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class MGTUnit:
    force_unit: str
    length_unit: str
    heat_unit: str
    temperature_unit: str
    force_to_n: float
    length_to_m: float

    @property
    def force_scale_to_n(self) -> float:
        return self.force_to_n

    @property
    def length_scale_to_m(self) -> float:
        return self.length_to_m


@dataclass(frozen=True, slots=True)
class MGTStructureType:
    structure_type: int
    mass_type: int
    self_mass_type: int
    mass_offset: bool
    self_weight: bool
    gravity_source: float
    gravity_m_s2: float
    reference_temperature: float
    align_beam: bool
    align_slab: bool
    rotate_rigid: bool


@dataclass(frozen=True, slots=True)
class MGTNode:
    id: int
    x_m: float
    y_m: float
    z_m: float

    @property
    def coordinates_m(self) -> tuple[float, float, float]:
        return (self.x_m, self.y_m, self.z_m)


@dataclass(frozen=True, slots=True)
class MGTMaterial:
    id: int
    material_type: str
    name: str
    specific_heat: float
    heat_coefficient: float
    temperature_unit: str
    damping_ratio: float
    youngs_modulus_pa: float
    poisson_ratio: float
    thermal_expansion: float
    density_n_per_m3: float

    @property
    def e_pa(self) -> float:
        return self.youngs_modulus_pa

    @property
    def density_si(self) -> float:
        return self.density_n_per_m3


@dataclass(frozen=True, slots=True)
class MGTSection:
    id: int
    name: str
    section_type: str
    shape: str
    height_m: float
    width_m: float
    area_m2: float
    shear_area_y_m2: float
    shear_area_z_m2: float
    iy_m4: float
    iz_m4: float
    j_m4: float

    @property
    def asy_m2(self) -> float:
        return self.shear_area_y_m2

    @property
    def asz_m2(self) -> float:
        return self.shear_area_z_m2


@dataclass(frozen=True, slots=True)
class MGTElement:
    id: int
    element_type: str
    material_id: int
    section_id: int
    node_i: int
    node_j: int
    angle_deg: float
    angle_rad: float
    subtype: int

    @property
    def node_ids(self) -> tuple[int, int]:
        return (self.node_i, self.node_j)


@dataclass(frozen=True, slots=True)
class MGTConstraint:
    node_ids: tuple[int, ...]
    restraint_code: str
    restraint_mask: tuple[bool, bool, bool, bool, bool, bool]
    restrained_dofs: tuple[str, ...]
    group: str


@dataclass(frozen=True, slots=True)
class MGTStaticLoadCase:
    name: str
    load_type: str
    description: str


@dataclass(frozen=True, slots=True)
class MGTConcentratedLoad:
    node_ids: tuple[int, ...]
    fx_n: float
    fy_n: float
    fz_n: float
    mx_nm: float
    my_nm: float
    mz_nm: float
    group: str
    structure_type_name: str

    @property
    def forces_n(self) -> tuple[float, float, float]:
        return (self.fx_n, self.fy_n, self.fz_n)

    @property
    def moments_nm(self) -> tuple[float, float, float]:
        return (self.mx_nm, self.my_nm, self.mz_nm)


def split_positional(row: LogicalRow) -> tuple[str, ...]:
    """Split a logical CSV row while retaining every internal/trailing empty."""

    if not isinstance(row, LogicalRow):
        raise TypeError("split_positional expects a LogicalRow")
    text = row.text.rstrip("\r\n")
    if "\n" in text or "\r" in text:
        _raise(row, "MGT_V2_MULTILINE_ROW", "logical rows must contain one line")
    return tuple(token.strip() for token in text.strip().split(","))


def parse_unit(row: LogicalRow) -> MGTUnit:
    tokens = _expect_arity(row, "UNIT", {4})
    _require_nonempty(row, "UNIT", tokens, range(4))

    force_key = tokens[0].upper()
    length_key = tokens[1].upper()
    if force_key not in _FORCE_TO_N:
        _raise(
            row,
            "MGT_V2_UNIT_FORCE",
            f"unsupported force unit {tokens[0]!r}; expected N, kN, or MN",
        )
    if length_key not in _LENGTH_TO_M:
        _raise(
            row,
            "MGT_V2_UNIT_LENGTH",
            f"unsupported length unit {tokens[1]!r}; expected m, mm, or cm",
        )

    force_unit, force_scale = _FORCE_TO_N[force_key]
    length_unit, length_scale = _LENGTH_TO_M[length_key]
    return MGTUnit(
        force_unit=force_unit,
        length_unit=length_unit,
        heat_unit=tokens[2],
        temperature_unit=tokens[3],
        force_to_n=force_scale,
        length_to_m=length_scale,
    )


def parse_structure_type(row: LogicalRow, units: MGTUnit) -> MGTStructureType:
    tokens = _expect_arity(row, "STRUCTURE_TYPE", {10})
    _require_nonempty(row, "STRUCTURE_TYPE", tokens, range(10))
    structure_type = _parse_int(row, "STRUCTURE_TYPE", "iSTYP", tokens[0])
    mass_type = _parse_int(row, "STRUCTURE_TYPE", "iMASS", tokens[1])
    self_mass_type = _parse_int(row, "STRUCTURE_TYPE", "iSMAS", tokens[2])
    gravity = _parse_float(row, "STRUCTURE_TYPE", "GRAV", tokens[5])
    if gravity <= 0.0:
        _raise(row, "MGT_V2_STRUCTURE_TYPE_GRAVITY", "GRAV must be positive")

    return MGTStructureType(
        structure_type=structure_type,
        mass_type=mass_type,
        self_mass_type=self_mass_type,
        mass_offset=_parse_yes_no(row, "STRUCTURE_TYPE", "bMASSOFFSET", tokens[3]),
        self_weight=_parse_yes_no(row, "STRUCTURE_TYPE", "bSELFWEIGHT", tokens[4]),
        gravity_source=gravity,
        gravity_m_s2=gravity * units.length_to_m,
        reference_temperature=_parse_float(row, "STRUCTURE_TYPE", "TEMPER", tokens[6]),
        align_beam=_parse_yes_no(row, "STRUCTURE_TYPE", "bALIGNBEAM", tokens[7]),
        align_slab=_parse_yes_no(row, "STRUCTURE_TYPE", "bALIGNSLAB", tokens[8]),
        rotate_rigid=_parse_yes_no(row, "STRUCTURE_TYPE", "bROTRIGID", tokens[9]),
    )


def parse_node(row: LogicalRow, units: MGTUnit) -> MGTNode:
    tokens = _expect_arity(row, "NODE", {4})
    _require_nonempty(row, "NODE", tokens, range(4))
    node_id = _parse_positive_id(row, "NODE", "iNO", tokens[0])
    coordinates = tuple(
        _parse_float(row, "NODE", label, token) * units.length_to_m
        for label, token in zip(("X", "Y", "Z"), tokens[1:], strict=True)
    )
    return MGTNode(node_id, coordinates[0], coordinates[1], coordinates[2])


def parse_material(row: LogicalRow, units: MGTUnit) -> MGTMaterial:
    tokens = _expect_arity(row, "MATERIAL", {15})
    _require_nonempty(row, "MATERIAL", tokens, (*range(5), *range(6, 15)))
    material_id = _parse_positive_id(row, "MATERIAL", "iMAT", tokens[0])
    material_type = tokens[1].upper()
    if material_type not in {"CONC", "STEEL", "USER"}:
        _raise(
            row,
            "MGT_V2_MATERIAL_TYPE",
            "TYPE must be CONC, STEEL, or USER for the strict subset",
        )
    if tokens[5] != "":
        _raise(
            row,
            "MGT_V2_MATERIAL_PLAST",
            "PLAST must be the preserved empty field at position 6",
        )
    if tokens[7].upper() != "NO":
        _raise(row, "MGT_V2_MATERIAL_BMASS", "bMASS must be NO")
    if tokens[9] != "2":
        _raise(row, "MGT_V2_MATERIAL_SELECTOR", "DATA1 selector must be 2")

    youngs_modulus = _parse_float(row, "MATERIAL", "ELAST", tokens[10])
    poisson = _parse_float(row, "MATERIAL", "POISN", tokens[11])
    density = _parse_float(row, "MATERIAL", "DEN", tokens[13])
    mass = _parse_float(row, "MATERIAL", "MASS", tokens[14])
    if youngs_modulus <= 0.0:
        _raise(row, "MGT_V2_MATERIAL_E", "ELAST must be positive")
    if not -1.0 < poisson < 0.5:
        _raise(row, "MGT_V2_MATERIAL_NU", "POISN must satisfy -1 < nu < 0.5")
    if density < 0.0:
        _raise(row, "MGT_V2_MATERIAL_DENSITY", "DEN must be non-negative")
    if mass != 0.0:
        _raise(row, "MGT_V2_MATERIAL_MASS", "MASS must be exactly zero")

    return MGTMaterial(
        id=material_id,
        material_type=material_type,
        name=tokens[2],
        specific_heat=_parse_float(row, "MATERIAL", "SPHEAT", tokens[3]),
        heat_coefficient=_parse_float(row, "MATERIAL", "HEATCO", tokens[4]),
        temperature_unit=tokens[6],
        damping_ratio=_parse_float(row, "MATERIAL", "DAMPRATIO", tokens[8]),
        youngs_modulus_pa=(youngs_modulus * units.force_to_n / units.length_to_m**2),
        poisson_ratio=poisson,
        thermal_expansion=_parse_float(row, "MATERIAL", "THERMAL", tokens[12]),
        density_n_per_m3=density * units.force_to_n / units.length_to_m**3,
    )


def parse_section(row: LogicalRow, units: MGTUnit) -> MGTSection:
    tokens = _expect_arity(row, "SECTION", {24})
    _require_nonempty(row, "SECTION", tokens, range(24))
    section_id = _parse_positive_id(row, "SECTION", "iSEC", tokens[0])
    if tokens[1].upper() != "DBUSER":
        _raise(row, "MGT_V2_SECTION_TYPE", "TYPE must be DBUSER")
    if tokens[3].upper() != "CC":
        _raise(row, "MGT_V2_SECTION_OFFSET", "OFFSET must be centered code CC")
    for index, label in zip(
        range(4, 10), ("iCENT", "iREF", "iHORZ", "HUSER", "iVERT", "VUSER"), strict=True
    ):
        if _parse_float(row, "SECTION", label, tokens[index]) != 0.0:
            _raise(
                row,
                "MGT_V2_SECTION_OFFSET",
                f"{label} must be zero for a centered section",
            )
    if tokens[10].upper() != "YES" or tokens[11].upper() != "NO":
        _raise(
            row,
            "MGT_V2_SECTION_FLAGS",
            "strict SB sections require bSD=YES and bWE=NO",
        )
    if tokens[12].upper() != "SB":
        _raise(row, "MGT_V2_SECTION_SHAPE", "SHAPE must be SB")
    if tokens[13] != "2":
        _raise(row, "MGT_V2_SECTION_SELECTOR", "DATA1 selector must be 2")

    height_source = _parse_float(row, "SECTION", "D1", tokens[14])
    width_source = _parse_float(row, "SECTION", "D2", tokens[15])
    if height_source <= 0.0 or width_source <= 0.0:
        _raise(row, "MGT_V2_SECTION_DIMENSION", "D1 and D2 must be positive")
    for index in range(16, 24):
        if _parse_float(row, "SECTION", f"D{index - 13}", tokens[index]) != 0.0:
            _raise(
                row,
                "MGT_V2_SECTION_DIMENSION",
                "D3 through D10 must be zero for the strict SB rectangle",
            )

    height = height_source * units.length_to_m
    width = width_source * units.length_to_m
    area = width * height
    return MGTSection(
        id=section_id,
        name=tokens[2],
        section_type="DBUSER",
        shape="SB",
        height_m=height,
        width_m=width,
        area_m2=area,
        shear_area_y_m2=(5.0 / 6.0) * area,
        shear_area_z_m2=(5.0 / 6.0) * area,
        iy_m4=width * height**3 / 12.0,
        iz_m4=height * width**3 / 12.0,
        j_m4=rectangle_saint_venant_j(width, height),
    )


def parse_element(row: LogicalRow) -> MGTElement:
    tokens = _expect_arity(row, "ELEMENT", {8})
    _require_nonempty(row, "ELEMENT", tokens, range(8))
    if tokens[1].upper() != "BEAM":
        _raise(row, "MGT_V2_ELEMENT_TYPE", "TYPE must be BEAM")
    subtype = _parse_int(row, "ELEMENT", "iSUB", tokens[7])
    if subtype != 0:
        _raise(row, "MGT_V2_ELEMENT_SUBTYPE", "iSUB must be zero")
    node_i = _parse_positive_id(row, "ELEMENT", "iN1", tokens[4])
    node_j = _parse_positive_id(row, "ELEMENT", "iN2", tokens[5])
    if node_i == node_j:
        _raise(row, "MGT_V2_ELEMENT_DEGENERATE", "iN1 and iN2 must differ")
    angle = _parse_float(row, "ELEMENT", "ANGLE", tokens[6])
    return MGTElement(
        id=_parse_positive_id(row, "ELEMENT", "iEL", tokens[0]),
        element_type="BEAM",
        material_id=_parse_positive_id(row, "ELEMENT", "iMAT", tokens[2]),
        section_id=_parse_positive_id(row, "ELEMENT", "iPRO", tokens[3]),
        node_i=node_i,
        node_j=node_j,
        angle_deg=angle,
        angle_rad=radians(angle),
        subtype=subtype,
    )


def parse_constraint(row: LogicalRow) -> MGTConstraint:
    tokens = _expect_arity(row, "CONSTRAINT", {2, 3})
    _require_nonempty(row, "CONSTRAINT", tokens, (0, 1))
    code = tokens[1]
    if re.fullmatch(r"[01]{6}", code) is None:
        _raise(
            row,
            "MGT_V2_CONSTRAINT_MASK",
            "restraint mask must be exactly six binary digits",
        )
    mask = tuple(flag == "1" for flag in code)
    return MGTConstraint(
        node_ids=_parse_node_expression(row, "CONSTRAINT", tokens[0]),
        restraint_code=code,
        restraint_mask=mask,  # type: ignore[arg-type]
        restrained_dofs=tuple(
            label
            for label, restrained in zip(_DOF_LABELS, mask, strict=True)
            if restrained
        ),
        group=tokens[2] if len(tokens) == 3 else "",
    )


def parse_static_load_case(row: LogicalRow) -> MGTStaticLoadCase:
    tokens = _expect_arity(row, "STLDCASE", {3})
    _require_nonempty(row, "STLDCASE", tokens, (0, 1))
    return MGTStaticLoadCase(tokens[0], tokens[1], tokens[2])


def parse_concentrated_load(
    row: LogicalRow,
    units: MGTUnit,
) -> MGTConcentratedLoad:
    tokens = _expect_arity(row, "CONLOAD", {7, 8, 9})
    _require_nonempty(row, "CONLOAD", tokens, range(7))
    values = tuple(
        _parse_float(row, "CONLOAD", label, token)
        for label, token in zip(
            ("FX", "FY", "FZ", "MX", "MY", "MZ"), tokens[1:7], strict=True
        )
    )
    force_scale = units.force_to_n
    moment_scale = units.force_to_n * units.length_to_m
    return MGTConcentratedLoad(
        node_ids=_parse_node_expression(row, "CONLOAD", tokens[0]),
        fx_n=values[0] * force_scale,
        fy_n=values[1] * force_scale,
        fz_n=values[2] * force_scale,
        mx_nm=values[3] * moment_scale,
        my_nm=values[4] * moment_scale,
        mz_nm=values[5] * moment_scale,
        group=tokens[7] if len(tokens) >= 8 else "",
        structure_type_name=tokens[8] if len(tokens) == 9 else "",
    )


def _expect_arity(
    row: LogicalRow,
    grammar: str,
    allowed: set[int],
) -> tuple[str, ...]:
    tokens = split_positional(row)
    if len(tokens) not in allowed:
        expected = ", ".join(str(value) for value in sorted(allowed))
        _raise(
            row,
            f"MGT_V2_{grammar}_ARITY",
            f"expected {expected} positional fields, received {len(tokens)}",
        )
    return tokens


def _require_nonempty(
    row: LogicalRow,
    grammar: str,
    tokens: tuple[str, ...],
    indexes: range | tuple[int, ...],
) -> None:
    for index in indexes:
        if tokens[index] == "":
            _raise(
                row,
                f"MGT_V2_{grammar}_EMPTY",
                f"field {index + 1} must not be empty",
            )


def _parse_int(row: LogicalRow, grammar: str, field: str, token: str) -> int:
    if _INTEGER_RE.fullmatch(token) is None:
        _raise(
            row,
            f"MGT_V2_{grammar}_INTEGER",
            f"{field} must be an integer, received {token!r}",
        )
    return int(token)


def _parse_positive_id(row: LogicalRow, grammar: str, field: str, token: str) -> int:
    value = _parse_int(row, grammar, field, token)
    if value <= 0:
        _raise(
            row,
            f"MGT_V2_{grammar}_ID",
            f"{field} must be a positive integer",
        )
    return value


def _parse_float(row: LogicalRow, grammar: str, field: str, token: str) -> float:
    try:
        value = float(token)
    except ValueError:
        _raise(
            row,
            f"MGT_V2_{grammar}_NUMBER",
            f"{field} must be numeric, received {token!r}",
        )
    if not isfinite(value):
        _raise(
            row,
            f"MGT_V2_{grammar}_FINITE",
            f"{field} must be finite",
        )
    return value


def _parse_yes_no(
    row: LogicalRow,
    grammar: str,
    field: str,
    token: str,
) -> bool:
    normalized = token.upper()
    if normalized not in {"YES", "NO"}:
        _raise(
            row,
            f"MGT_V2_{grammar}_BOOLEAN",
            f"{field} must be YES or NO",
        )
    return normalized == "YES"


def _parse_node_expression(
    row: LogicalRow,
    grammar: str,
    expression: str,
) -> tuple[int, ...]:
    text = expression.strip()
    if not text:
        _raise(row, f"MGT_V2_{grammar}_NODE_EXPR", "node expression is empty")

    node_ids: list[int] = []
    seen: set[int] = set()
    position = 0
    while position < len(text):
        match = _NODE_ATOM_RE.match(text, position)
        if match is None:
            _raise(
                row,
                f"MGT_V2_{grammar}_NODE_EXPR",
                f"invalid node expression near {text[position:]!r}",
            )
        start = int(match.group("start"))
        end_token = match.group("end")
        step_token = match.group("step")
        if start <= 0:
            _raise(
                row,
                f"MGT_V2_{grammar}_NODE_ID",
                "node identifiers must be positive",
            )
        if end_token is None:
            expanded = (start,)
        else:
            end = int(end_token)
            step = int(step_token) if step_token is not None else 1
            if end <= 0:
                _raise(
                    row,
                    f"MGT_V2_{grammar}_NODE_ID",
                    "node identifiers must be positive",
                )
            if step <= 0:
                _raise(
                    row,
                    f"MGT_V2_{grammar}_RANGE_STEP",
                    "range step must be positive",
                )
            stop = end + 1 if start <= end else end - 1
            signed_step = step if start <= end else -step
            expanded = range(start, stop, signed_step)

        for node_id in expanded:
            if node_id in seen:
                _raise(
                    row,
                    f"MGT_V2_{grammar}_DUPLICATE_NODE",
                    f"node {node_id} appears more than once",
                )
            seen.add(node_id)
            node_ids.append(node_id)
            if len(node_ids) > _MAX_EXPANDED_NODE_IDS:
                _raise(
                    row,
                    f"MGT_V2_{grammar}_RANGE_SIZE",
                    "node expression expands beyond the safety limit",
                )
        position = match.end()

    return tuple(node_ids)


def rectangle_saint_venant_j(width: float, height: float) -> float:
    """Return the Saint-Venant torsion constant using the rectangle series."""

    long_side = max(width, height)
    short_side = min(width, height)
    series = 0.0
    for odd in range(1, 402, 2):
        term = tanh(odd * pi * long_side / (2.0 * short_side)) / odd**5
        series += term
        if term < 1.0e-16:
            break
    correction = 1.0 - (192.0 * short_side / (pi**5 * long_side)) * series
    return long_side * short_side**3 * correction / 3.0


def _raise(row: LogicalRow, code: str, message: str) -> None:
    location = f"line {row.line_number}: " if row.line_number > 0 else ""
    if row.source:
        location = (
            f"{row.source}:{row.line_number}: "
            if row.line_number > 0
            else f"{row.source}: "
        )
    raise MGTGrammarError(code, location + message)


__all__ = [
    "LogicalRow",
    "MGTConcentratedLoad",
    "MGTConstraint",
    "MGTElement",
    "MGTGrammarError",
    "MGTMaterial",
    "MGTNode",
    "MGTSection",
    "MGTStaticLoadCase",
    "MGTStructureType",
    "MGTUnit",
    "parse_concentrated_load",
    "parse_constraint",
    "parse_element",
    "parse_material",
    "parse_node",
    "parse_section",
    "parse_static_load_case",
    "parse_structure_type",
    "parse_unit",
    "rectangle_saint_venant_j",
    "split_positional",
]
