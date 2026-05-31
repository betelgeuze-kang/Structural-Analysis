#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from parse_mgt_section_material_properties import (  # noqa: E402
    load_mgt_section_material_properties,
    parse_mgt_material_properties,
    parse_mgt_section_properties,
)

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


def test_load_mgt_section_material_properties_bundle() -> None:
    bundle = load_mgt_section_material_properties(MGT)
    assert "sections" in bundle and "materials" in bundle
    assert len(bundle["sections"]) >= 1
    assert len(bundle["materials"]) >= 3
