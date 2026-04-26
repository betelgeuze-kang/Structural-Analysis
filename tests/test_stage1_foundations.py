from __future__ import annotations

import numpy as np

from implementation.phase1.beam_column_nonlinear import (
    BeamColumnProperties,
    elastic_local_stiffness,
    solve_beam_column_response,
)
from implementation.phase1.cost_model import MemberCostInput, estimate_member_cost, estimate_project_cost
from implementation.phase1.design_optimization_env import (
    DesignOptimizationConfig,
    aggregate_group_state,
    apply_group_action,
    evaluate_reward,
    greedy_constrained_search,
    run_two_stage_search,
)
from implementation.phase1.fiber_section import evaluate_section_response, make_rectangular_rc_section
from implementation.phase1.kds_rc_rule_engine import (
    RCMemberCapacity,
    RCMemberDemand,
    evaluate_rc_member,
    governing_result,
)
from implementation.phase1.load_combination_engine import (
    generate_kds_service_combinations,
    generate_kds_strength_combinations,
    generate_named_scale_library,
)
from implementation.phase1.rc_constitutive_library import (
    BondSlipMaterial,
    ConcreteMaterial,
    SteelMaterial,
    bond_slip_response,
    concrete_response,
    steel_response,
)
from implementation.phase1.section_family_library import build_story_section_families, evaluate_story_section_profile


def test_rc_constitutive_concrete_softens_after_peak() -> None:
    mat = ConcreteMaterial(fc_mpa=35.0)
    peak = concrete_response(-0.0020, mat)
    post_peak = concrete_response(-0.0032, mat)
    crack = concrete_response(0.00025, mat)
    assert abs(post_peak.stress_mpa) < abs(peak.stress_mpa)
    assert crack.state_tag == "tension_softening"
    assert crack.stress_mpa > 0.0


def test_rc_constitutive_steel_yields_and_hardens() -> None:
    mat = SteelMaterial(fy_mpa=420.0, hardening_ratio=0.02)
    elastic = steel_response(0.0005, mat)
    plastic = steel_response(0.01, mat)
    assert elastic.state_tag == "elastic"
    assert plastic.state_tag in {"plastic_hardening", "plastic_capped"}
    assert abs(plastic.stress_mpa) > abs(elastic.stress_mpa)


def test_bond_slip_has_softening_branch() -> None:
    mat = BondSlipMaterial(k0_kn_per_mm=100.0, slip_y_mm=0.5, slip_u_mm=2.0)
    peak = bond_slip_response(0.5, mat)
    softened = bond_slip_response(1.5, mat)
    assert peak.state_tag == "bond_elastic"
    assert softened.state_tag == "bond_softening"
    assert abs(softened.stress_mpa) < abs(peak.stress_mpa)


def test_fiber_section_zero_curvature_gives_near_zero_moment() -> None:
    section = make_rectangular_rc_section(width_m=0.4, depth_m=0.6, cover_m=0.05)
    result = evaluate_section_response(section=section, axial_strain=5.0e-5, curvature_z_per_m=0.0)
    assert abs(result.moment_z_n_m) < 1.0e4
    assert result.axial_stiffness_n > 0.0


def test_fiber_section_curvature_creates_moment_and_cracking() -> None:
    section = make_rectangular_rc_section(width_m=0.4, depth_m=0.6, cover_m=0.05)
    result = evaluate_section_response(section=section, axial_strain=0.0, curvature_z_per_m=0.01)
    assert abs(result.moment_z_n_m) > 0.0
    assert result.cracked_fiber_count >= 0


def test_beam_column_stiffness_is_symmetric() -> None:
    props = BeamColumnProperties(length_m=6.0, area_m2=0.025, e_mpa=30000.0, iy_m4=0.08)
    k = elastic_local_stiffness(props)
    assert k.shape == (6, 6)
    assert np.allclose(k, k.T)


def test_beam_column_yielding_reduces_tangent_scale() -> None:
    props = BeamColumnProperties(length_m=6.0, area_m2=0.025, e_mpa=30000.0, iy_m4=0.08, yield_moment_kNm=150.0, hardening_ratio=0.05)
    deformation = np.array([0.0, 0.0, 0.10, 0.0, 0.30, -0.10], dtype=np.float64)
    result = solve_beam_column_response(props=props, deformation_local=deformation, axial_force_n=3.0e6)
    assert result.tangent_scale <= 1.0
    assert result.yielded_end_count >= 1
    assert result.drift_ratio > 0.0


def test_load_combination_engine_exposes_strength_and_service_sets() -> None:
    uls = generate_kds_strength_combinations()
    sls = generate_kds_service_combinations()
    lib = generate_named_scale_library()
    assert len(uls) >= 10
    assert len(sls) >= 5
    assert len(lib) == len(uls)
    assert any(name.endswith("EX+") for name, _ in lib)


def test_kds_rc_rule_engine_returns_governing_dcr() -> None:
    demand = RCMemberDemand(axial_kN=1800.0, shear_kN=320.0, moment_kNm=520.0, drift_ratio_pct=1.5, punching_shear_kN=0.0)
    capacity = RCMemberCapacity(axial_kN=2400.0, shear_kN=400.0, moment_kNm=600.0, drift_ratio_pct=2.0, punching_shear_kN=300.0)
    results = evaluate_rc_member(member_type="wall", demand=demand, capacity=capacity)
    gov = governing_result(results)
    assert len(results) == 4
    assert gov.dcr > 0.0
    assert gov.clause.startswith("KDS-RC-WALL-")


def test_kds_rc_rule_engine_supports_foundation() -> None:
    demand = RCMemberDemand(footing_bearing_kPa=180.0, footing_shear_kN=220.0)
    capacity = RCMemberCapacity(footing_bearing_kPa=240.0, footing_shear_kN=300.0)
    results = evaluate_rc_member(member_type="foundation", demand=demand, capacity=capacity)
    assert len(results) == 2
    assert all(r.clause.startswith("KDS-RC-FOUND-") for r in results)


def test_kds_rc_rule_engine_supports_connection() -> None:
    demand = RCMemberDemand(connection_shear_kN=120.0, connection_slip_mm=2.5, connection_rotation_mrad=4.0)
    capacity = RCMemberCapacity(connection_shear_kN=180.0, connection_slip_mm=3.0, connection_rotation_mrad=6.0)
    results = evaluate_rc_member(member_type="connection", demand=demand, capacity=capacity)
    assert len(results) == 3
    assert all(r.clause.startswith("KDS-RC-CONN-") for r in results)


def test_cost_model_returns_positive_total() -> None:
    member = MemberCostInput(
        member_id="C1",
        member_type="column",
        length_m=3.2,
        volume_m3=1.1,
        steel_mass_kg=120.0,
        rebar_ratio=0.025,
        congestion_index=0.3,
    )
    breakdown = estimate_member_cost(member)
    project = estimate_project_cost([member])
    assert breakdown.total_cost > 0.0
    assert breakdown.lap_splice_penalty >= 0.0
    assert breakdown.anchorage_penalty >= 0.0
    assert breakdown.detailing_penalty >= 0.0
    assert project["total_cost"] >= breakdown.total_cost
    assert project["lap_splice_penalty"] >= 0.0
    assert project["anchorage_penalty"] >= 0.0
    assert project["detailing_penalty"] >= 0.0


def test_design_optimization_env_applies_mask_and_reward() -> None:
    ratios = np.asarray([0.02, 0.03], dtype=np.float64)
    mask = np.asarray([[True, True], [False, True]], dtype=np.bool_)
    cfg = DesignOptimizationConfig(rebar_step=0.01)
    reduced = apply_group_action(rebar_ratio=ratios, action_mask=mask, group_index=0, direction=-1, cfg=cfg)
    blocked = apply_group_action(rebar_ratio=ratios, action_mask=mask, group_index=1, direction=-1, cfg=cfg)
    assert reduced[0] < ratios[0]
    assert blocked[1] == ratios[1]
    reward = evaluate_reward(
        total_cost=1000.0,
        max_dcr=1.1,
        drift_pct=1.2,
        drift_limit_pct=1.0,
        residual_drift_pct=0.8,
        residual_drift_limit_pct=0.5,
        dcr_limit=1.0,
        cfg=cfg,
    )
    assert reward < -1000.0


def test_design_optimization_env_greedy_search_reduces_cost() -> None:
    dataset = {
        "group_index_per_member": np.asarray([0, 0, 1, 1], dtype=np.int32),
        "unique_group_ids": np.asarray(["G0", "G1"]),
        "rebar_ratio": np.asarray([0.03, 0.03, 0.02, 0.02], dtype=np.float64),
        "max_dcr": np.asarray([0.55, 0.58, 0.92, 0.95], dtype=np.float64),
        "congestion_index": np.asarray([0.20, 0.20, 0.35, 0.35], dtype=np.float64),
        "lap_splice_ratio": np.asarray([0.10, 0.10, 0.18, 0.18], dtype=np.float64),
        "anchorage_complexity": np.asarray([0.15, 0.15, 0.30, 0.30], dtype=np.float64),
        "detailing_violation_ratio": np.asarray([0.02, 0.02, 0.12, 0.12], dtype=np.float64),
        "volume_m3": np.asarray([1.0, 1.0, 1.5, 1.5], dtype=np.float64),
        "steel_mass_kg": np.asarray([80.0, 80.0, 120.0, 120.0], dtype=np.float64),
        "member_types": np.asarray(["beam", "beam", "column", "column"]),
        "drift_envelope_max_pct": np.asarray([1.2, 1.2, 1.2, 1.2], dtype=np.float64),
        "residual_drift_pct_max_abs": np.asarray([0.3, 0.3, 0.3, 0.3], dtype=np.float64),
        "action_mask": np.asarray([[True, True], [True, True]], dtype=np.bool_),
    }
    state = aggregate_group_state(dataset)
    result = greedy_constrained_search(state=state, cfg=DesignOptimizationConfig(rebar_step=0.002, max_iterations=8))
    assert result["iteration_count"] >= 1
    assert result["final_reward"] >= result["baseline_reward"]


def test_design_optimization_env_two_stage_repairs_violation() -> None:
    dataset = {
        "group_index_per_member": np.asarray([0, 0, 1, 1], dtype=np.int32),
        "unique_group_ids": np.asarray(["G0", "G1"]),
        "rebar_ratio": np.asarray([0.01, 0.01, 0.015, 0.015], dtype=np.float64),
        "max_dcr": np.asarray([1.10, 1.05, 0.95, 0.96], dtype=np.float64),
        "congestion_index": np.asarray([0.20, 0.20, 0.30, 0.30], dtype=np.float64),
        "lap_splice_ratio": np.asarray([0.10, 0.10, 0.16, 0.16], dtype=np.float64),
        "anchorage_complexity": np.asarray([0.20, 0.20, 0.35, 0.35], dtype=np.float64),
        "detailing_violation_ratio": np.asarray([0.15, 0.15, 0.10, 0.10], dtype=np.float64),
        "volume_m3": np.asarray([1.0, 1.0, 1.5, 1.5], dtype=np.float64),
        "steel_mass_kg": np.asarray([80.0, 80.0, 120.0, 120.0], dtype=np.float64),
        "member_types": np.asarray(["column", "column", "beam", "beam"]),
        "zone_labels": np.asarray(["core", "core", "perimeter", "perimeter"]),
        "story_band_index": np.asarray([0, 0, 1, 1], dtype=np.int32),
        "drift_envelope_max_pct": np.asarray([3.2, 3.2, 3.2, 3.2], dtype=np.float64),
        "residual_drift_pct_max_abs": np.asarray([0.9, 0.9, 0.9, 0.9], dtype=np.float64),
        "action_mask": np.asarray([[True, True], [True, True]], dtype=np.bool_),
    }
    state = aggregate_group_state(dataset)
    result = run_two_stage_search(state=state, cfg=DesignOptimizationConfig(rebar_step=0.002, max_iterations=16))
    assert result["baseline_violation_score"] >= result["final_violation_score"]
    assert result["iteration_count_stage1"] >= 1


def test_section_family_library_generates_story_profile() -> None:
    families = build_story_section_families(topology="wall-frame", material_type="rc_composite", story_count=8)
    profile = evaluate_story_section_profile(
        topology="wall-frame",
        material_type="rc_composite",
        story_h_m=np.full(8, 3.2, dtype=np.float64),
        drift_ratio_profile=np.linspace(0.01, 0.006, num=8, dtype=np.float64),
        load_scale=1.0,
    )
    assert len(families) == 8
    assert "wall_boundary" in {f.family_name for f in families}
    assert profile["summary"]["story_count"] == 8
    assert float(profile["summary"]["stiffness_scale_min"]) >= 0.95
    assert len(profile["detail_rows"]) == 8
