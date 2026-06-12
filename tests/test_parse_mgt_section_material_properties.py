#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from parse_mgt_section_material_properties import (  # noqa: E402
    load_mgt_section_material_properties,
    parse_mgt_boundary_groups,
    parse_mgt_beam_end_offsets,
    parse_mgt_elastic_links,
    parse_mgt_element_local_axis_rows,
    parse_mgt_material_properties,
    parse_mgt_plate_thickness_properties,
    parse_mgt_section_properties,
    scan_mgt_opening_source_markers,
    parse_mgt_story_eccentricity,
    parse_mgt_support_constraints,
)
from parse_midas_mgt_to_json_npz import _parse_elements  # noqa: E402

MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"


def test_sb800x300_section_inertia_within_one_percent() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    sections = parse_mgt_section_properties(text)
    assert 4 in sections
    sec = sections[4]
    assert sec["shape"] == "SB"
    assert sec["H_m"] == 0.8
    assert sec["B_m"] == 0.3
    hand_iy = 0.3 * 0.8**3 / 12.0
    assert abs(sec["Iy_m4"] - hand_iy) / hand_iy < 0.01


def test_material_moduli_from_mgt() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    materials = parse_mgt_material_properties(text)
    assert materials[1]["type"] == "CONC"
    assert abs(materials[1]["E_kN_per_m2"] - 3.25e7) / 3.25e7 < 0.01
    assert materials[2]["type"] == "STEEL"
    assert abs(materials[2]["E_kN_per_m2"] - 2.06e8) / 2.06e8 < 0.01
    assert materials[3]["type"] == "SRC"
    assert abs(materials[3]["E_kN_per_m2"] - 2.06e8) / 2.06e8 < 0.01
    assert abs(materials[3]["E_secondary_kN_per_m2"] - 3.25e7) / 3.25e7 < 0.01


def test_pipe_section_p50x4_parses() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    sections = parse_mgt_section_properties(text)
    assert 1088 in sections
    assert sections[1088]["shape"] == "P"
    assert sections[1088]["Iy_m4"] == sections[1088]["Iz_m4"]
    assert sections[1088]["A_m2"] > 0.0


def test_plate_thickness_rows_parse_from_mgt() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    thicknesses = parse_mgt_plate_thickness_properties(text)
    assert 5 in thicknesses
    assert thicknesses[5]["type"] == "VALUE"
    assert thicknesses[5]["same_thickness"] is True
    assert abs(thicknesses[5]["effective_thickness_m"] - 0.8) < 1.0e-9
    assert len(thicknesses) >= 20


def test_beam_end_offset_rows_parse_from_mgt() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    offsets = parse_mgt_beam_end_offsets(text)
    assert len(offsets) >= 300
    assert offsets[0]["element_ids"] == [903]
    assert offsets[0]["coordinate_system"] == "GLOBAL"
    assert abs(offsets[0]["i_offset_m"]["x"] + 0.009) < 1.0e-12
    assert abs(offsets[0]["j_offset_m"]["y"] + 0.099) < 1.0e-12
    assert max(abs(value) for row in offsets for value in row["offset_values_m"]) >= 0.45


def test_beam_end_offset_element_ranges_expand() -> None:
    text = """*OFFSET
1 to 3 by 2, GLOBAL, 0.1, 0, 0, 0.2, 0, 0, G
5to7, GLOBAL, 0, 0, 0, 0, 0, 0, G
"""
    offsets = parse_mgt_beam_end_offsets(text)
    assert offsets[0]["element_ids"] == [1, 3]
    assert offsets[0]["element_count"] == 2
    assert offsets[1]["element_ids"] == [5, 6, 7]


def test_boundary_entities_parse_from_mgt() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    links = parse_mgt_elastic_links(text)
    story_eccentricity = parse_mgt_story_eccentricity(text)
    boundary_groups = parse_mgt_boundary_groups(text)

    assert len(constraints) == 8
    assert constraints[0]["node_ids"][:4] == [4210, 4212, 4214, 4216]
    assert constraints[0]["restraint_code"] == "111000"
    assert constraints[0]["restrained_dofs"] == ["Dx", "Dy", "Dz"]
    assert sum(row["node_count"] for row in constraints) == 2133
    assert len(links) == 1692
    assert links[0]["link_type"] == "GEN"
    assert links[0]["node_i"] == 4211
    assert links[0]["node_j"] == 4
    assert links[0]["stiffness"]["SDx"] == 1.0e6
    assert links[0]["stiffness"]["SRz"] == 0.001
    assert story_eccentricity["include_seismic_eccentricity"] is True
    assert story_eccentricity["include_wind_eccentricity"] is False
    assert story_eccentricity["seismic_eccentricity_percent"] == 5.0
    assert boundary_groups[0]["name"] == "1#"


def test_element_local_axis_rows_parse_from_mgt() -> None:
    text = MGT.read_text(encoding="utf-8", errors="ignore")
    rows = parse_mgt_element_local_axis_rows(text)
    line_rows = [row for row in rows if row["family"] == "line"]
    surface_rows = [row for row in rows if row["family"] == "surface"]
    nonzero_line = [row for row in line_rows if abs(row["angle_deg"]) > 1.0e-12]
    assert len(line_rows) >= 5500
    assert len(surface_rows) == 7152
    assert len(nonzero_line) == 150
    assert max(abs(row["angle_deg"]) for row in line_rows) >= 90.0
    assert all(row["lcaxis_code"] == 0 for row in surface_rows)
    opening_scan = scan_mgt_opening_source_markers(text)
    assert opening_scan["opening_marker_row_count"] == 0


def test_compact_planar_width_id_does_not_alias_to_lcaxis() -> None:
    text = """*ELEMENT
1, PLATE, 1, 2, 10, 11, 12, 13, 4, 7
2, PLATE, 1, 2, 10, 11, 12, 13, 4, 7, 3
"""
    rows = parse_mgt_element_local_axis_rows(text)
    compact, explicit = rows

    assert compact["width_id"] == 7
    assert compact["lcaxis_code"] == 0
    assert compact["lcaxis_token_present"] is False
    assert compact["lcaxis_source"] == "default_lcaxis_token_omitted"

    assert explicit["width_id"] == 7
    assert explicit["lcaxis_code"] == 3
    assert explicit["lcaxis_token_present"] is True
    assert explicit["lcaxis_source"] == "explicit_lcaxis_token"


def test_roundtrip_parser_compact_planar_width_id_does_not_alias_to_lcaxis() -> None:
    rows, meta = _parse_elements(
        [
            "1, PLATE, 1, 2, 10, 11, 12, 13, 4, 7",
            "2, PLATE, 1, 2, 10, 11, 12, 13, 4, 7, 3",
        ],
        {10, 11, 12, 13},
    )
    compact, explicit = rows

    assert compact["width_id"] == 7
    assert compact["lcaxis_code"] == 0
    assert compact["lcaxis_token_present"] is False
    assert compact["lcaxis_source"] == "default_lcaxis_token_omitted"

    assert explicit["width_id"] == 7
    assert explicit["lcaxis_code"] == 3
    assert explicit["lcaxis_token_present"] is True
    assert explicit["lcaxis_source"] == "explicit_lcaxis_token"
    assert meta["surface_lcaxis_token_count"] == 1
    assert meta["surface_nonzero_lcaxis_count"] == 1
    assert meta["surface_compact_lcaxis_token_count"] == 1


def test_load_mgt_section_material_properties_bundle() -> None:
    bundle = load_mgt_section_material_properties(MGT)
    assert "sections" in bundle and "materials" in bundle and "plate_thicknesses" in bundle
    assert len(bundle["sections"]) >= 1
    assert len(bundle["materials"]) >= 3
    assert len(bundle["plate_thicknesses"]) >= 20
    assert len(bundle["beam_end_offsets"]) >= 300
    assert len(bundle["support_constraints"]) == 8
    assert len(bundle["elastic_links"]) == 1692
    assert bundle["story_eccentricity"]["wind_eccentricity_percent"] == 15.0
    assert len(bundle["boundary_groups"]) == 1
    assert len(bundle["element_local_axes"]) >= 12000
    assert bundle["opening_source_markers"]["opening_marker_row_count"] == 0
