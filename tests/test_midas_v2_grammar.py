from __future__ import annotations

from dataclasses import FrozenInstanceError
from math import pi

import pytest

from structural_analysis.io.midas.v2.grammar import (
    LogicalRow,
    MGTGrammarError,
    parse_concentrated_load,
    parse_constraint,
    parse_element,
    parse_material,
    parse_node,
    parse_section,
    parse_static_load_case,
    parse_structure_type,
    parse_unit,
    split_positional,
)


def _row(text: str, line_number: int = 1) -> LogicalRow:
    return LogicalRow(text=text, line_number=line_number, source="fixture.mgt")


def _metre_units():
    return parse_unit(_row("KN, M, KJ, C"))


def _millimetre_units():
    return parse_unit(_row("KN, MM, J, C"))


def _sb_row(*, height: float = 0.8, width: float = 0.3) -> LogicalRow:
    return _row(
        f"4, DBUSER, SB, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, "
        f"{height}, {width}, 0, 0, 0, 0, 0, 0, 0, 0"
    )


def test_split_positional_preserves_internal_and_trailing_empty_fields() -> None:
    tokens = split_positional(_row("1, CONC, C40, 0, 0, , C, NO, 0.05, 2, 1, 2, ,"))

    assert tokens[5] == ""
    assert tokens[-2:] == ("", "")
    assert len(tokens) == 14


@pytest.mark.parametrize(
    ("text", "force_unit", "length_unit", "force_scale", "length_scale"),
    [
        ("N, M, J, C", "N", "m", 1.0, 1.0),
        ("kN, mm, J, C", "kN", "mm", 1.0e3, 1.0e-3),
        ("MN, cm, J, C", "MN", "cm", 1.0e6, 1.0e-2),
    ],
)
def test_parse_unit_accepts_only_the_explicit_four_field_subset(
    text: str,
    force_unit: str,
    length_unit: str,
    force_scale: float,
    length_scale: float,
) -> None:
    units = parse_unit(_row(text))

    assert units.force_unit == force_unit
    assert units.length_unit == length_unit
    assert units.force_to_n == force_scale
    assert units.length_to_m == length_scale


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("KN, M, C", "MGT_V2_UNIT_ARITY"),
        ("KIP, M, J, C", "MGT_V2_UNIT_FORCE"),
        ("KN, FT, J, C", "MGT_V2_UNIT_LENGTH"),
        ("KN, M, J,", "MGT_V2_UNIT_EMPTY"),
    ],
)
def test_parse_unit_rejects_ambiguous_rows(text: str, code: str) -> None:
    with pytest.raises(MGTGrammarError) as caught:
        parse_unit(_row(text, line_number=11))

    assert caught.value.code == code
    assert "fixture.mgt:11" in caught.value.message


def test_structure_type_converts_source_gravity_to_si() -> None:
    structure = parse_structure_type(
        _row("0, 1, 1, NO, NO, 9806, 0, NO, NO, NO"),
        _millimetre_units(),
    )

    assert structure.gravity_source == 9806.0
    assert structure.gravity_m_s2 == pytest.approx(9.806)
    assert structure.mass_offset is False
    assert structure.self_weight is False


def test_structure_type_requires_positive_finite_gravity() -> None:
    with pytest.raises(MGTGrammarError) as caught:
        parse_structure_type(
            _row("0, 1, 1, NO, YES, 0, 0, YES, YES, NO"),
            _metre_units(),
        )

    assert caught.value.code == "MGT_V2_STRUCTURE_TYPE_GRAVITY"


def test_node_requires_positive_id_and_converts_coordinates() -> None:
    node = parse_node(_row("1, 820, -20, 0"), _millimetre_units())

    assert node.coordinates_m == pytest.approx((0.82, -0.02, 0.0))

    with pytest.raises(MGTGrammarError, match="positive integer"):
        parse_node(_row("0, 0, 0, 0"), _metre_units())
    with pytest.raises(MGTGrammarError) as nonfinite:
        parse_node(_row("1, nan, 0, 0"), _metre_units())
    assert nonfinite.value.code == "MGT_V2_NODE_FINITE"


def test_material_preserves_empty_plast_and_converts_e_and_density_to_si() -> None:
    material = parse_material(
        _row(
            "1, CONC, C40, 0, 0, , C, NO, 0.05, 2, 3.2500e+07, 0.25, 1.0000e-05, 26, 0"
        ),
        _metre_units(),
    )

    assert material.material_type == "CONC"
    assert material.youngs_modulus_pa == pytest.approx(3.25e10)
    assert material.density_n_per_m3 == pytest.approx(2.6e4)
    assert material.poisson_ratio == 0.25


def test_material_uses_length_dimension_when_source_is_kn_mm() -> None:
    material = parse_material(
        _row("2, USER, Tendon, 0, 0, , C, NO, 0, 2, 196, 0, 1e-5, 7.85e-8, 0"),
        _millimetre_units(),
    )

    assert material.youngs_modulus_pa == pytest.approx(196.0e9)
    assert material.density_n_per_m3 == pytest.approx(78_500.0)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            "1, CONC, C40, 0, 0, C, NO, 0.05, 2, 3.25e7, 0.25, 1e-5, 26, 0",
            "MGT_V2_MATERIAL_ARITY",
        ),
        (
            "1, CONC, C40, 0, 0, X, C, NO, 0.05, 2, 3.25e7, 0.25, 1e-5, 26, 0",
            "MGT_V2_MATERIAL_PLAST",
        ),
        (
            "1, CONC, C40, 0, 0, , C, YES, 0.05, 2, 3.25e7, 0.25, 1e-5, 26, 0",
            "MGT_V2_MATERIAL_BMASS",
        ),
        (
            "1, CONC, C40, 0, 0, , C, NO, 0.05, 1, 3.25e7, 0.25, 1e-5, 26, 0",
            "MGT_V2_MATERIAL_SELECTOR",
        ),
        (
            "1, CONC, C40, 0, 0, , C, NO, 0.05, 2, 3.25e7, 0.5, 1e-5, 26, 0",
            "MGT_V2_MATERIAL_NU",
        ),
        (
            "1, CONC, C40, 0, 0, , C, NO, 0.05, 2, 3.25e7, 0.25, 1e-5, 26, 1",
            "MGT_V2_MATERIAL_MASS",
        ),
    ],
)
def test_material_rejects_every_unsupported_positional_variant(
    text: str,
    code: str,
) -> None:
    with pytest.raises(MGTGrammarError) as caught:
        parse_material(_row(text), _metre_units())

    assert caught.value.code == code


def test_section_computes_si_rectangle_properties() -> None:
    section = parse_section(_sb_row(), _metre_units())

    assert section.height_m == 0.8
    assert section.width_m == 0.3
    assert section.area_m2 == pytest.approx(0.24)
    assert section.shear_area_y_m2 == pytest.approx(0.2)
    assert section.shear_area_z_m2 == pytest.approx(0.2)
    assert section.iy_m4 == pytest.approx(0.3 * 0.8**3 / 12.0)
    assert section.iz_m4 == pytest.approx(0.8 * 0.3**3 / 12.0)
    assert 0.0 < section.j_m4 < section.iy_m4 + section.iz_m4


def test_section_uses_saint_venant_rectangle_series_for_square() -> None:
    section = parse_section(_sb_row(height=1.0, width=1.0), _metre_units())

    assert section.j_m4 == pytest.approx(0.140577014955, rel=1.0e-10)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            "4, VALUE, SB, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, "
            "0.8, 0.3, 0, 0, 0, 0, 0, 0, 0, 0",
            "MGT_V2_SECTION_TYPE",
        ),
        (
            "4, DBUSER, SB, CC, 0, 0, 1, 0, 0, 0, YES, NO, SB, 2, "
            "0.8, 0.3, 0, 0, 0, 0, 0, 0, 0, 0",
            "MGT_V2_SECTION_OFFSET",
        ),
        (
            "4, DBUSER, SB, CC, 0, 0, 0, 0, 0, 0, YES, NO, P, 2, "
            "0.8, 0.3, 0, 0, 0, 0, 0, 0, 0, 0",
            "MGT_V2_SECTION_SHAPE",
        ),
    ],
)
def test_section_rejects_nonexplicit_or_noncentered_variants(
    text: str,
    code: str,
) -> None:
    with pytest.raises(MGTGrammarError) as caught:
        parse_section(_row(text), _metre_units())

    assert caught.value.code == code


def test_element_accepts_only_full_eight_field_beam_and_converts_angle() -> None:
    element = parse_element(_row("201, BEAM, 1, 4, 216, 215, 180, 0"))

    assert element.node_ids == (216, 215)
    assert element.angle_rad == pytest.approx(pi)

    with pytest.raises(MGTGrammarError) as abbreviated:
        parse_element(_row("1, BEAM, 1, 1, 1, 2"))
    assert abbreviated.value.code == "MGT_V2_ELEMENT_ARITY"
    with pytest.raises(MGTGrammarError) as subtype:
        parse_element(_row("1, BEAM, 1, 1, 1, 2, 0, 1"))
    assert subtype.value.code == "MGT_V2_ELEMENT_SUBTYPE"


def test_constraint_expands_compact_spaced_and_descending_ranges() -> None:
    constraint = parse_constraint(_row("1to5by2 8 10 to 12, 111000, FOUNDATION"))
    descending = parse_constraint(_row("5to1by2, 001001,"))

    assert constraint.node_ids == (1, 3, 5, 8, 10, 11, 12)
    assert constraint.restraint_mask == (True, True, True, False, False, False)
    assert constraint.restrained_dofs == ("Dx", "Dy", "Dz")
    assert constraint.group == "FOUNDATION"
    assert descending.node_ids == (5, 3, 1)
    assert descending.group == ""


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("1to3, 11100,", "MGT_V2_CONSTRAINT_MASK"),
        ("1to3by0, 111000,", "MGT_V2_CONSTRAINT_RANGE_STEP"),
        ("1to3 3, 111000,", "MGT_V2_CONSTRAINT_DUPLICATE_NODE"),
        ("1toX, 111000,", "MGT_V2_CONSTRAINT_NODE_EXPR"),
    ],
)
def test_constraint_rejects_ambiguous_node_or_mask_syntax(text: str, code: str) -> None:
    with pytest.raises(MGTGrammarError) as caught:
        parse_constraint(_row(text))

    assert caught.value.code == code


def test_static_load_case_requires_three_fields_and_preserves_empty_description() -> (
    None
):
    load_case = parse_static_load_case(_row("DEAD, D,"))

    assert load_case.name == "DEAD"
    assert load_case.load_type == "D"
    assert load_case.description == ""

    with pytest.raises(MGTGrammarError) as abbreviated:
        parse_static_load_case(_row("DEAD, D"))
    assert abbreviated.value.code == "MGT_V2_STLDCASE_ARITY"


def test_concentrated_load_preserves_optional_empties_and_converts_si() -> None:
    load = parse_concentrated_load(
        _row("1to5by2, 1, -2, 3, 4, -5, 6, ,"),
        _metre_units(),
    )

    assert load.node_ids == (1, 3, 5)
    assert load.forces_n == pytest.approx((1.0e3, -2.0e3, 3.0e3))
    assert load.moments_nm == pytest.approx((4.0e3, -5.0e3, 6.0e3))
    assert load.group == ""
    assert load.structure_type_name == ""


def test_concentrated_load_uses_force_times_length_for_kn_mm_moments() -> None:
    load = parse_concentrated_load(
        _row("1, 1, 2, 3, 4, 5, 6, BG1"),
        _millimetre_units(),
    )

    assert load.forces_n == pytest.approx((1.0e3, 2.0e3, 3.0e3))
    assert load.moments_nm == pytest.approx((4.0, 5.0, 6.0))
    assert load.group == "BG1"


def test_concentrated_load_rejects_internal_empty_or_nonfinite_component() -> None:
    with pytest.raises(MGTGrammarError) as empty:
        parse_concentrated_load(_row("1, 1, , 3, 4, 5, 6"), _metre_units())
    assert empty.value.code == "MGT_V2_CONLOAD_EMPTY"

    with pytest.raises(MGTGrammarError) as nonfinite:
        parse_concentrated_load(_row("1, 1, inf, 3, 4, 5, 6"), _metre_units())
    assert nonfinite.value.code == "MGT_V2_CONLOAD_FINITE"


def test_parsed_records_are_immutable() -> None:
    node = parse_node(_row("1, 0, 0, 0"), _metre_units())

    with pytest.raises(FrozenInstanceError):
        node.x_m = 1.0  # type: ignore[misc]
