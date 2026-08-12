from __future__ import annotations

import json
from pathlib import Path

import pytest

from structural_analysis.io.midas.raw_parser import (
    parse_float_token,
    parse_int_token,
    parse_midas_mgt,
    split_csv_like,
)


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "native/tests/golden/mgt_import_health_v1.json"


def _golden_cases() -> list[dict[str, object]]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "structural-native-mgt-python-oracle.v1"
    return list(payload["cases"])


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda case: str(case["case_id"]))
def test_python_raw_parser_owns_the_frozen_native_mgt_input_matrix(
    case: dict[str, object],
) -> None:
    path = ROOT / str(case["source_path"])
    parsed = parse_midas_mgt(path)
    assert parsed.source_checksum == case["source_hash"]
    assert parsed.line_count == case["line_count"]
    assert parsed.section_counts == case["section_counts"]


def test_exact_numeric_fixture_has_independent_closed_form_properties() -> None:
    case = _golden_cases()[0]
    parsed = parse_midas_mgt(ROOT / str(case["source_path"]))
    units = split_csv_like(parsed.section("UNIT")[0])
    assert units[:2] == ["N", "M"]

    nodes = [split_csv_like(row) for row in parsed.section("NODE")]
    assert [parse_int_token(row[0]) for row in nodes] == [1, 2]
    height_m = float(nodes[1][3]) - float(nodes[0][3])
    assert height_m == 3.2

    material = split_csv_like(parsed.section("MATERIAL")[0])
    youngs_modulus_pa = parse_float_token(material[2])
    density_kg_m3 = parse_float_token(material[4])
    assert youngs_modulus_pa == 200_000_000_000.0
    assert density_kg_m3 == 8_000.0

    section = split_csv_like(parsed.section("SECTION")[0])
    area_m2 = parse_float_token(section[2])
    iy_m4 = parse_float_token(section[3])
    assert area_m2 == 1.25
    assert iy_m4 == pytest.approx(0.0006826666666666668, abs=0.0)

    stiffness_n_per_m = 12.0 * youngs_modulus_pa * iy_m4 / height_m**3
    lumped_floor_mass_kg = density_kg_m3 * area_m2 * height_m / 2.0
    assert stiffness_n_per_m == pytest.approx(50_000_000.0, rel=0.0, abs=1.0e-8)
    assert lumped_floor_mass_kg == pytest.approx(16_000.0, rel=0.0, abs=0.0)

    constraint_rows = [split_csv_like(row) for row in parsed.section("CONSTRAINT")]
    assert constraint_rows == [["1", "111111"], ["2", "011111"]]
    load = split_csv_like(parsed.section("CONLOAD")[0])
    assert parse_int_token(load[0]) == 2
    assert [parse_float_token(value) for value in load[1:7]] == [
        200_000.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    ]
