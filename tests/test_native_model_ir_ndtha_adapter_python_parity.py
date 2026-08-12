from __future__ import annotations

import json
import math
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL_FIXTURE = (
    ROOT / "native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json"
)
PRODUCT_REQUEST = (
    ROOT / "native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"
)


def test_fixed_guided_frame3d_adapter_closed_form_matches_neutral_golden() -> None:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    request = json.loads(PRODUCT_REQUEST.read_text(encoding="utf-8"))

    nodes = {node["id"]: node for node in model["nodes"]}
    element = model["elements"][0]
    material = model["materials"][0]
    section = model["sections"][0]
    load_pattern = model["load_patterns"][0]
    base = nodes[element["node_ids"][0]]
    floor = nodes[element["node_ids"][1]]

    height_m = floor["coordinates_m"][2] - base["coordinates_m"][2]
    elastic_modulus_pa = material["parameters"]["elastic_modulus_pa"]
    density_kg_m3 = material["parameters"]["density_kg_m3"]
    area_m2 = section["parameters"]["area_m2"]
    iy_m4 = section["parameters"]["iy_m4"]
    stiffness_n_per_m = 12.0 * elastic_modulus_pa * iy_m4 / height_m**3
    mass_kg = 0.5 * density_kg_m3 * area_m2 * height_m
    damping_ratio = 0.00025
    damping_n_s_per_m = (
        2.0 * damping_ratio * math.sqrt(stiffness_n_per_m * mass_kg)
    )
    floor_load_n = load_pattern["nodal_loads"][0]["components_si"]["FX"]

    expected = request["inputs"]
    assert height_m == pytest.approx(expected["story_h_m"][0], rel=0.0, abs=1e-15)
    assert stiffness_n_per_m == pytest.approx(
        expected["story_k_n_per_m"][0], rel=0.0, abs=1e-8
    )
    assert mass_kg == pytest.approx(expected["story_mass_kg"][0], rel=0.0, abs=1e-12)
    assert damping_n_s_per_m == pytest.approx(
        expected["story_damping_n_s_per_m"][0], rel=0.0, abs=1e-12
    )
    assert floor_load_n == expected["floor_load_base_n"][0]
    assert expected["story_axial_n"] == [0.0]
    assert expected["story_yield_drift_m"] == [0.01]


def test_adapter_fixture_encodes_the_exact_bounded_profile() -> None:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))

    assert model["capability_profile"] == "engine_v2_phase0_linear_3d"
    assert len(model["nodes"]) == 2
    assert len(model["materials"]) == 1
    assert len(model["sections"]) == 1
    assert len(model["elements"]) == 1
    assert len(model["constraints"]) == 2
    assert len(model["load_patterns"]) == 1
    assert model["load_combinations"] == []
    assert model["time_functions"] == []
    assert model["construction_stages"] == []
    assert model["roundtrip_map"] == []
    assert model["unsupported_features"] == []
    assert model["elements"][0]["type"] == "frame_3d"
    assert model["elements"][0]["formulation"] == "euler_bernoulli_3d"
    assert model["materials"][0]["law_id"] == "linear_elastic_isotropic"
    assert model["sections"][0]["family_id"] == "frame_3d"
    assert model["constraints"][0]["dofs"] == ["UX", "UY", "UZ", "RX", "RY", "RZ"]
    assert model["constraints"][1]["dofs"] == ["UY", "UZ", "RX", "RY", "RZ"]
