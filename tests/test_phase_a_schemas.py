"""Phase-A tests: JSON schema structure and material rule table validation."""
from __future__ import annotations

import pytest


# ── Vehicle Model Schema ─────────────────────────────────────────────────────

class TestVehicleModelSchema:
    def test_has_required_fields(self, vehicle_schema: dict):
        required = vehicle_schema.get("required", [])
        for field in ["schema_version", "vehicle_id", "car_body", "bogies", "wheelsets", "speed_m_s"]:
            assert field in required, f"Missing required field: {field}"

    def test_car_body_requires_mass_and_inertia(self, vehicle_schema: dict):
        car_body = vehicle_schema["properties"]["car_body"]
        req = car_body.get("required", [])
        assert "mass_kg" in req
        assert "moment_of_inertia_pitch_kg_m2" in req
        assert "moment_of_inertia_roll_kg_m2" in req

    def test_contact_model_enum_values(self, vehicle_schema: dict):
        contact = vehicle_schema["properties"]["contact_model"]
        assert set(contact["enum"]) == {"hertzian", "linearized_hertz", "custom"}

    def test_speed_has_exclusive_minimum(self, vehicle_schema: dict):
        speed = vehicle_schema["properties"]["speed_m_s"]
        assert speed.get("exclusiveMinimum") == 0

    def test_wheelsets_min_items(self, vehicle_schema: dict):
        ws = vehicle_schema["properties"]["wheelsets"]
        assert ws.get("minItems", 0) >= 2

    def test_bogie_secondary_suspension_keys(self, vehicle_schema: dict):
        bogie_items = vehicle_schema["properties"]["bogies"]["items"]
        susp = bogie_items["properties"]["secondary_suspension"]
        susp_req = susp.get("required", [])
        assert "k_vertical_N_m" in susp_req
        assert "c_vertical_Ns_m" in susp_req


# ── Tunnel Lining Schema ─────────────────────────────────────────────────────

class TestTunnelLiningSchema:
    def test_has_required_fields(self, tunnel_schema: dict):
        req = tunnel_schema.get("required", [])
        for field in ["schema_version", "tunnel_id", "cross_section", "lining", "alignment"]:
            assert field in req

    def test_tunnel_type_includes_shield_tbm(self, tunnel_schema: dict):
        tt = tunnel_schema["properties"]["tunnel_type"]
        assert "shield_tbm" in tt.get("enum", [])

    def test_cross_section_shape_enum(self, tunnel_schema: dict):
        cs = tunnel_schema["properties"]["cross_section"]["properties"]["shape"]
        shapes = cs.get("enum", [])
        assert "circular" in shapes
        assert "horseshoe" in shapes

    def test_lining_material_requires_E_and_density(self, tunnel_schema: dict):
        mat = tunnel_schema["properties"]["lining"]["properties"]["material"]
        req = mat.get("required", [])
        assert "E_Pa" in req
        assert "density_kg_m3" in req

    def test_segment_joint_has_rotational_stiffness(self, tunnel_schema: dict):
        joints = tunnel_schema["properties"]["lining"]["properties"]["segment_joints"]
        assert "rotational_stiffness_Nm_rad" in joints["properties"]


# ── Soil Impedance Table ─────────────────────────────────────────────────────

class TestSoilImpedanceTable:
    def test_has_soil_profiles(self, soil_impedance_schema: dict):
        assert "soil_profiles" in soil_impedance_schema.get("required", [])

    def test_soil_class_enum_values(self, soil_impedance_schema: dict):
        profile = soil_impedance_schema["properties"]["soil_profiles"]["additionalProperties"]
        soil_class = profile["properties"]["soil_class"]
        classes = soil_class.get("enum", [])
        assert "soft_clay" in classes
        assert "dense_sand" in classes
        assert "weathered_rock" in classes

    def test_layers_require_shear_wave_velocity(self, soil_impedance_schema: dict):
        profile = soil_impedance_schema["properties"]["soil_profiles"]["additionalProperties"]
        layer_item = profile["properties"]["layers"]["items"]
        req = layer_item.get("required", [])
        assert "shear_wave_velocity_m_s" in req

    def test_track_subgrade_section_exists(self, soil_impedance_schema: dict):
        assert "track_subgrade" in soil_impedance_schema["properties"]


# ── Material Rule Table ──────────────────────────────────────────────────────

class TestMaterialRuleTable:
    def test_has_building_codes(self, material_rule_table: dict):
        assert "kbc_2021" in material_rule_table
        assert "kbc_2024" in material_rule_table

    def test_has_railway_rules(self, material_rule_table: dict):
        assert "railway_krs_2024" in material_rule_table
        rail = material_rule_table["railway_krs_2024"]
        assert "rail_steel_UIC60" in rail
        assert "ballast_granite" in rail
        assert "rail_fastener_pandrol" in rail

    def test_has_tunnel_rules(self, material_rule_table: dict):
        assert "tunnel_kds_2024" in material_rule_table
        tunnel = material_rule_table["tunnel_kds_2024"]
        assert "segment_concrete_C50" in tunnel
        assert "segment_bolt_M30" in tunnel

    def test_rail_UIC60_has_physical_properties(self, material_rule_table: dict):
        rail = material_rule_table["railway_krs_2024"]["rail_steel_UIC60"]
        assert rail["E_Pa"] == pytest.approx(2.1e11, rel=1e-3)
        assert rail["density_kg_m3"] == pytest.approx(7850, rel=1e-2)
        assert "I_m4" in rail
        assert "A_m2" in rail

    def test_every_material_has_hinge_softening(self, material_rule_table: dict):
        for code_name, code_data in material_rule_table.items():
            for mat_name, mat_data in code_data.items():
                assert "hinge_softening" in mat_data, \
                    f"{code_name}.{mat_name} missing hinge_softening"

    def test_every_material_has_yield_strain_range(self, material_rule_table: dict):
        for code_name, code_data in material_rule_table.items():
            for mat_name, mat_data in code_data.items():
                rng = mat_data.get("yield_strain_range")
                assert rng is not None, f"{code_name}.{mat_name} missing yield_strain_range"
                assert len(rng) == 2
                assert rng[0] < rng[1]


# ── Dynamics Boundary Contract Schema ────────────────────────────────────────

class TestDynamicsBoundarySchema:
    def test_has_title(self, dynamics_boundary_schema: dict):
        assert "title" in dynamics_boundary_schema

    def test_schema_is_json_schema_draft(self, dynamics_boundary_schema: dict):
        schema_url = dynamics_boundary_schema.get("$schema", "")
        assert "json-schema.org" in schema_url
