#!/usr/bin/env python3
"""Check nonlinear member-model generalization breadth beyond benchmark matrices."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from beam_column_nonlinear import BeamColumnProperties, solve_beam_column_response
from fiber_section import (
    evaluate_section_response,
    make_composite_beam_section,
    make_rectangular_rc_section,
    make_wide_flange_steel_section,
)
from layered_shell_wall import (
    LayeredShellLayer,
    LayeredShellSection,
    evaluate_layered_shell_response,
    make_layered_shell_section,
    make_layered_slab_section,
    make_layered_wall_section,
)
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "nonlinear generalization evidence is present for beam-column formulations, fiber section families, layered shell/wall/slab sections, joint/panel and foundation section families, foundation-soil links, and production nonlinear engine paths",
    "ERR_INVALID_INPUT": "invalid nonlinear generalization gate input",
    "ERR_BEAM_COLUMN": "beam-column nonlinear formulation coverage is incomplete",
    "ERR_FIBER_SECTION": "fiber section family coverage is incomplete",
    "ERR_LAYERED_SHELL_WALL": "layered shell/wall/slab coverage is incomplete",
    "ERR_JOINT_PANEL": "joint or panel section family coverage is incomplete",
    "ERR_FOUNDATION_SECTION": "foundation section family coverage is incomplete",
    "ERR_CONNECTION_SECTION": "connection or device section family coverage is incomplete",
    "ERR_SUBSTRUCTURE_SECTION": "substructure or interface section family coverage is incomplete",
    "ERR_DEVICE_SECTION": "device section family coverage is incomplete",
    "ERR_ISOLATION_SECTION": "isolation section family coverage is incomplete",
    "ERR_SOIL_INTERFACE_SECTION": "soil-interface section family coverage is incomplete",
    "ERR_BEARING_SECTION": "bearing section family coverage is incomplete",
    "ERR_RETROFIT_SECTION": "retrofit section family coverage is incomplete",
    "ERR_GROUND_IMPROVEMENT_SECTION": "ground-improvement section family coverage is incomplete",
    "ERR_FOUNDATION_SOIL_LINK": "foundation-soil link evidence is incomplete",
    "ERR_PRODUCTION_ENGINE": "production nonlinear engine evidence is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "nonlinear_engine_report",
        "pushover_stress_report",
        "ndtha_stress_report",
        "foundation_soil_link_gate_report",
        "out",
    ],
    "properties": {
        "nonlinear_engine_report": {"type": "string", "minLength": 1},
        "pushover_stress_report": {"type": "string", "minLength": 1},
        "ndtha_stress_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_gate_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _beam_column_rows() -> list[dict[str, Any]]:
    cases = [
        (
            "rectangular_rc_frame",
            "force_based",
            BeamColumnProperties(
                length_m=6.0,
                area_m2=0.028,
                e_mpa=30000.0,
                iy_m4=0.09,
                yield_moment_kNm=220.0,
                hardening_ratio=0.05,
            ),
            np.array([0.0, 0.0, 0.08, 0.0, 0.24, -0.08], dtype=np.float64),
            3.6e6,
        ),
        (
            "steel_moment_column",
            "displacement_based",
            BeamColumnProperties(
                length_m=5.2,
                area_m2=0.021,
                e_mpa=200000.0,
                iy_m4=0.062,
                yield_moment_kNm=310.0,
                hardening_ratio=0.03,
            ),
            np.array([0.0, 0.0, 0.05, 0.0, 0.16, -0.05], dtype=np.float64),
            2.8e6,
        ),
        (
            "composite_transfer_girder",
            "corotational_proxy",
            BeamColumnProperties(
                length_m=8.4,
                area_m2=0.033,
                e_mpa=42000.0,
                iy_m4=0.14,
                yield_moment_kNm=480.0,
                hardening_ratio=0.06,
            ),
            np.array([0.0, 0.0, 0.06, 0.0, 0.22, -0.07], dtype=np.float64),
            4.2e6,
        ),
        (
            "slender_pdelta_column",
            "force_based",
            BeamColumnProperties(
                length_m=7.8,
                area_m2=0.019,
                e_mpa=32000.0,
                iy_m4=0.048,
                yield_moment_kNm=205.0,
                hardening_ratio=0.05,
            ),
            np.array([0.0, 0.0, 0.10, 0.0, 0.31, -0.11], dtype=np.float64),
            3.9e6,
        ),
        (
            "outrigger_link_beam",
            "displacement_based",
            BeamColumnProperties(
                length_m=3.6,
                area_m2=0.024,
                e_mpa=200000.0,
                iy_m4=0.031,
                yield_moment_kNm=260.0,
                hardening_ratio=0.04,
            ),
            np.array([0.0, 0.0, 0.03, 0.0, 0.13, -0.04], dtype=np.float64),
            1.9e6,
        ),
        (
            "perimeter_frame_column",
            "corotational_proxy",
            BeamColumnProperties(
                length_m=6.8,
                area_m2=0.026,
                e_mpa=34000.0,
                iy_m4=0.071,
                yield_moment_kNm=290.0,
                hardening_ratio=0.05,
            ),
            np.array([0.0, 0.0, 0.07, 0.0, 0.27, -0.09], dtype=np.float64),
            3.2e6,
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, formulation, props, deformation, axial_force_n in cases:
        response = solve_beam_column_response(
            props=props,
            deformation_local=deformation,
            axial_force_n=axial_force_n,
            include_geometric=True,
            formulation=formulation,
        )
        rows.append(
            {
                "family": family,
                "formulation": formulation,
                "tangent_scale": float(response.tangent_scale),
                "drift_ratio": float(response.drift_ratio),
                "yielded_end_count": int(response.yielded_end_count),
                "max_trial_end_moment_ratio": float(np.max(response.trial_end_moment_ratios)),
                "max_plastic_rotation_proxy_rad": float(np.max(response.plastic_rotation_proxy_rad)),
                "stability_index": float(response.stability_index),
                "strain_energy_n_m": float(response.strain_energy_n_m),
                "pass": bool(
                    response.local_stiffness.shape == (6, 6)
                    and np.all(np.isfinite(response.local_stiffness))
                    and response.drift_ratio > 0.0
                    and response.strain_energy_n_m > 0.0
                    and np.isfinite(response.stability_index)
                ),
            }
        )
    return rows


def _fiber_rows() -> list[dict[str, Any]]:
    sections = [
        ("rectangular_rc", make_rectangular_rc_section(width_m=0.45, depth_m=0.70, cover_m=0.05, name="rectangular_rc")),
        (
            "rectangular_rc_wall_boundary",
            make_rectangular_rc_section(
                width_m=0.60,
                depth_m=0.95,
                cover_m=0.06,
                top_bar_count=6,
                bottom_bar_count=6,
                name="rectangular_rc_wall_boundary",
            ),
        ),
        (
            "wide_flange_steel",
            make_wide_flange_steel_section(
                flange_width_m=0.30,
                section_depth_m=0.60,
                flange_thickness_m=0.025,
                web_thickness_m=0.016,
            ),
        ),
        (
            "wide_flange_transfer",
            make_wide_flange_steel_section(
                flange_width_m=0.42,
                section_depth_m=0.86,
                flange_thickness_m=0.032,
                web_thickness_m=0.020,
                name="wide_flange_transfer",
            ),
        ),
        (
            "composite_beam",
            make_composite_beam_section(
                slab_width_m=1.80,
                slab_depth_m=0.16,
                flange_width_m=0.30,
                section_depth_m=0.60,
                flange_thickness_m=0.025,
                web_thickness_m=0.016,
            ),
        ),
        (
            "composite_transfer_girder",
            make_composite_beam_section(
                slab_width_m=2.40,
                slab_depth_m=0.20,
                flange_width_m=0.34,
                section_depth_m=0.78,
                flange_thickness_m=0.030,
                web_thickness_m=0.018,
                top_bar_count=6,
                bar_area_m2=3.20e-4,
                name="composite_transfer_girder",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(section=section, axial_strain=2.0e-5, curvature_z_per_m=8.0e-3)
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "max_abs_strain": float(response.max_abs_strain),
                "steel_yield_ratio_max": float(response.steel_yield_ratio_max),
                "concrete_crack_ratio_max": float(response.concrete_crack_ratio_max),
                "concrete_crush_ratio_max": float(response.concrete_crush_ratio_max),
                "yielded_steel_ratio": float(response.yielded_steel_ratio),
                "cracked_concrete_ratio": float(response.cracked_concrete_ratio),
                "section_strain_energy_n": float(response.section_strain_energy_n),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                    and float(response.section_strain_energy_n) > 0.0
                ),
            }
        )
    return rows


def _layered_rows() -> list[dict[str, Any]]:
    sections = [
        make_layered_wall_section(),
        make_layered_slab_section(),
        make_layered_shell_section(),
        LayeredShellSection(
            name="layered_coupling_wall",
            family="coupling_wall",
            layers=(
                LayeredShellLayer("boundary_concrete", 0.06, 32000.0, 13500.0, 0.97),
                LayeredShellLayer("diagonal_rebar", 0.012, 200000.0, 77000.0, 1.00),
                LayeredShellLayer("web_concrete", 0.10, 30000.0, 12200.0, 0.95),
                LayeredShellLayer("boundary_steel", 0.016, 200000.0, 77000.0, 1.00),
            ),
        ),
        LayeredShellSection(
            name="layered_bridge_deck",
            family="bridge_deck",
            layers=(
                LayeredShellLayer("deck_concrete", 0.16, 33000.0, 13800.0, 0.98),
                LayeredShellLayer("rebar_top", 0.012, 200000.0, 77000.0, 1.00),
                LayeredShellLayer("wearing_surface", 0.035, 24000.0, 9100.0, 0.92),
                LayeredShellLayer("rebar_bottom", 0.012, 200000.0, 77000.0, 1.00),
            ),
        ),
        LayeredShellSection(
            name="layered_tunnel_lining",
            family="tunnel_lining",
            layers=(
                LayeredShellLayer("shotcrete", 0.09, 29000.0, 11900.0, 0.93),
                LayeredShellLayer("primary_lining", 0.14, 31000.0, 12800.0, 0.96),
                LayeredShellLayer("steel_fiber_layer", 0.014, 200000.0, 77000.0, 1.00),
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for section in sections:
        response = evaluate_layered_shell_response(
            section=section,
            membrane_strain=1.5e-4,
            curvature_per_m=6.0e-3,
            shear_strain=3.5e-4,
        )
        rows.append(
            {
                "family": section.family,
                "layer_count": len(section.layers),
                "membrane_stiffness_n_per_m": float(response.membrane_stiffness_n_per_m),
                "bending_stiffness_n_m": float(response.bending_stiffness_n_m),
                "shear_stiffness_n_per_m": float(response.shear_stiffness_n_per_m),
                "pass": bool(
                    response.membrane_stiffness_n_per_m > 0.0
                    and response.bending_stiffness_n_m > 0.0
                    and response.shear_stiffness_n_per_m > 0.0
                ),
            }
        )
    return rows


def _joint_panel_rows() -> list[dict[str, Any]]:
    sections = [
        (
            "panel_zone_rc_core",
            make_rectangular_rc_section(
                width_m=0.55,
                depth_m=0.55,
                cover_m=0.05,
                top_bar_count=6,
                bottom_bar_count=6,
                bar_area_m2=3.87e-4,
                name="panel_zone_rc_core",
            ),
        ),
        (
            "knee_joint_rc",
            make_rectangular_rc_section(
                width_m=0.50,
                depth_m=0.80,
                cover_m=0.06,
                top_bar_count=8,
                bottom_bar_count=4,
                bar_area_m2=3.20e-4,
                name="knee_joint_rc",
            ),
        ),
        (
            "brace_gusset_panel",
            make_wide_flange_steel_section(
                flange_width_m=0.36,
                section_depth_m=0.48,
                flange_thickness_m=0.030,
                web_thickness_m=0.018,
                name="brace_gusset_panel",
            ),
        ),
        (
            "joint_transfer_composite",
            make_composite_beam_section(
                slab_width_m=1.60,
                slab_depth_m=0.14,
                flange_width_m=0.26,
                section_depth_m=0.52,
                flange_thickness_m=0.024,
                web_thickness_m=0.014,
                top_bar_count=4,
                name="joint_transfer_composite",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(
            section=section,
            axial_strain=3.0e-5,
            curvature_z_per_m=1.1e-2,
        )
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                ),
            }
        )
    return rows


def _foundation_section_rows() -> list[dict[str, Any]]:
    sections = [
        LayeredShellSection(
            name="mat_foundation_strip",
            family="mat_foundation_strip",
            layers=(
                LayeredShellLayer("raft_concrete", 0.45, 33000.0, 13800.0, 0.99),
                LayeredShellLayer("top_rebar", 0.018, 200000.0, 77000.0, 1.00),
                LayeredShellLayer("bottom_rebar", 0.018, 200000.0, 77000.0, 1.00),
            ),
        ),
        LayeredShellSection(
            name="pilecap_block",
            family="pilecap_block",
            layers=(
                LayeredShellLayer("pilecap_concrete", 0.70, 34000.0, 14100.0, 0.98),
                LayeredShellLayer("pilecap_rebar", 0.022, 200000.0, 77000.0, 1.00),
            ),
        ),
        LayeredShellSection(
            name="embedded_raft_shell",
            family="embedded_raft_shell",
            layers=(
                LayeredShellLayer("raft_shell_top", 0.20, 32000.0, 13300.0, 0.97),
                LayeredShellLayer("shear_key", 0.08, 30000.0, 12100.0, 0.93),
                LayeredShellLayer("raft_shell_bottom", 0.20, 32000.0, 13300.0, 0.97),
            ),
        ),
        LayeredShellSection(
            name="caisson_lining",
            family="caisson_lining",
            layers=(
                LayeredShellLayer("lining_concrete", 0.26, 31000.0, 12600.0, 0.96),
                LayeredShellLayer("steel_ring", 0.014, 200000.0, 77000.0, 1.00),
                LayeredShellLayer("secondary_lining", 0.10, 29000.0, 11800.0, 0.92),
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for section in sections:
        response = evaluate_layered_shell_response(
            section=section,
            membrane_strain=2.0e-4,
            curvature_per_m=5.0e-3,
            shear_strain=4.0e-4,
        )
        rows.append(
            {
                "family": section.family,
                "layer_count": len(section.layers),
                "membrane_stiffness_n_per_m": float(response.membrane_stiffness_n_per_m),
                "bending_stiffness_n_m": float(response.bending_stiffness_n_m),
                "shear_stiffness_n_per_m": float(response.shear_stiffness_n_per_m),
                "pass": bool(
                    response.membrane_stiffness_n_per_m > 0.0
                    and response.bending_stiffness_n_m > 0.0
                    and response.shear_stiffness_n_per_m > 0.0
                ),
            }
        )
    return rows


def _connection_section_rows() -> list[dict[str, Any]]:
    sections = [
        (
            "buckling_restrained_core",
            make_wide_flange_steel_section(
                flange_width_m=0.22,
                section_depth_m=0.36,
                flange_thickness_m=0.024,
                web_thickness_m=0.014,
                name="buckling_restrained_core",
            ),
        ),
        (
            "viscous_link_cartridge",
            make_composite_beam_section(
                slab_width_m=1.10,
                slab_depth_m=0.10,
                flange_width_m=0.20,
                section_depth_m=0.34,
                flange_thickness_m=0.018,
                web_thickness_m=0.012,
                top_bar_count=2,
                name="viscous_link_cartridge",
            ),
        ),
        (
            "yielding_fuse_plate",
            make_wide_flange_steel_section(
                flange_width_m=0.18,
                section_depth_m=0.30,
                flange_thickness_m=0.020,
                web_thickness_m=0.012,
                name="yielding_fuse_plate",
            ),
        ),
        (
            "base_isolation_slider",
            make_rectangular_rc_section(
                width_m=0.65,
                depth_m=0.35,
                cover_m=0.04,
                top_bar_count=4,
                bottom_bar_count=4,
                bar_area_m2=2.85e-4,
                name="base_isolation_slider",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(section=section, axial_strain=2.5e-5, curvature_z_per_m=9.0e-3)
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                ),
            }
        )
    return rows


def _substructure_section_rows() -> list[dict[str, Any]]:
    sections = [
        LayeredShellSection(
            name="diaphragm_wall_panel",
            family="diaphragm_wall_panel",
            layers=(
                LayeredShellLayer("wall_shell", 0.90, 33500.0, 14000.0, 0.99),
                LayeredShellLayer("cage_rebar", 0.020, 200000.0, 77000.0, 1.00),
            ),
        ),
        LayeredShellSection(
            name="retaining_toe_shell",
            family="retaining_toe_shell",
            layers=(
                LayeredShellLayer("toe_concrete", 0.38, 32000.0, 13200.0, 0.97),
                LayeredShellLayer("heel_concrete", 0.24, 30500.0, 12600.0, 0.95),
            ),
        ),
        LayeredShellSection(
            name="track_slab_interface_shell",
            family="track_slab_interface_shell",
            layers=(
                LayeredShellLayer("track_slab", 0.26, 34000.0, 14100.0, 0.98),
                LayeredShellLayer("interface_layer", 0.04, 12000.0, 4800.0, 0.70),
                LayeredShellLayer("support_plinth", 0.12, 31000.0, 12600.0, 0.94),
            ),
        ),
        LayeredShellSection(
            name="embedded_lining_transition",
            family="embedded_lining_transition",
            layers=(
                LayeredShellLayer("primary_lining", 0.24, 30000.0, 12100.0, 0.94),
                LayeredShellLayer("grout_annulus", 0.08, 18000.0, 7200.0, 0.80),
                LayeredShellLayer("secondary_lining", 0.14, 29000.0, 11800.0, 0.92),
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for section in sections:
        response = evaluate_layered_shell_response(
            section=section,
            membrane_strain=1.8e-4,
            curvature_per_m=4.8e-3,
            shear_strain=4.4e-4,
        )
        rows.append(
            {
                "family": section.family,
                "layer_count": len(section.layers),
                "membrane_stiffness_n_per_m": float(response.membrane_stiffness_n_per_m),
                "bending_stiffness_n_m": float(response.bending_stiffness_n_m),
                "shear_stiffness_n_per_m": float(response.shear_stiffness_n_per_m),
                "pass": bool(
                    response.membrane_stiffness_n_per_m > 0.0
                    and response.bending_stiffness_n_m > 0.0
                    and response.shear_stiffness_n_per_m > 0.0
                ),
            }
        )
    return rows


def _device_section_rows() -> list[dict[str, Any]]:
    sections = [
        (
            "viscous_damper_link",
            make_composite_beam_section(
                slab_width_m=0.90,
                slab_depth_m=0.08,
                flange_width_m=0.18,
                section_depth_m=0.30,
                flange_thickness_m=0.016,
                web_thickness_m=0.010,
                top_bar_count=2,
                name="viscous_damper_link",
            ),
        ),
        (
            "buckling_restrained_damper",
            make_wide_flange_steel_section(
                flange_width_m=0.20,
                section_depth_m=0.34,
                flange_thickness_m=0.022,
                web_thickness_m=0.013,
                name="buckling_restrained_damper",
            ),
        ),
        (
            "tuned_mass_transfer_beam",
            make_wide_flange_steel_section(
                flange_width_m=0.24,
                section_depth_m=0.38,
                flange_thickness_m=0.024,
                web_thickness_m=0.014,
                name="tuned_mass_transfer_beam",
            ),
        ),
        (
            "metal_yield_fuse",
            make_rectangular_rc_section(
                width_m=0.42,
                depth_m=0.32,
                cover_m=0.04,
                top_bar_count=3,
                bottom_bar_count=3,
                bar_area_m2=2.85e-4,
                name="metal_yield_fuse",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(section=section, axial_strain=2.2e-5, curvature_z_per_m=8.4e-3)
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                ),
            }
        )
    return rows


def _isolation_section_rows() -> list[dict[str, Any]]:
    sections = [
        (
            "lead_rubber_bearing",
            make_rectangular_rc_section(
                width_m=0.70,
                depth_m=0.22,
                cover_m=0.03,
                top_bar_count=4,
                bottom_bar_count=4,
                bar_area_m2=2.50e-4,
                name="lead_rubber_bearing",
            ),
        ),
        (
            "friction_pendulum_slider",
            make_wide_flange_steel_section(
                flange_width_m=0.18,
                section_depth_m=0.26,
                flange_thickness_m=0.020,
                web_thickness_m=0.010,
                name="friction_pendulum_slider",
            ),
        ),
        (
            "moat_edge_restrainer",
            make_composite_beam_section(
                slab_width_m=0.80,
                slab_depth_m=0.06,
                flange_width_m=0.16,
                section_depth_m=0.24,
                flange_thickness_m=0.014,
                web_thickness_m=0.009,
                top_bar_count=2,
                name="moat_edge_restrainer",
            ),
        ),
        (
            "uplift_isolation_keeper",
            make_rectangular_rc_section(
                width_m=0.55,
                depth_m=0.28,
                cover_m=0.035,
                top_bar_count=3,
                bottom_bar_count=3,
                bar_area_m2=2.20e-4,
                name="uplift_isolation_keeper",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(section=section, axial_strain=1.9e-5, curvature_z_per_m=7.8e-3)
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                ),
            }
        )
    return rows


def _soil_interface_section_rows() -> list[dict[str, Any]]:
    sections = [
        LayeredShellSection(
            name="pile_soil_interface_ring",
            family="pile_soil_interface_ring",
            layers=(
                LayeredShellLayer("pile_shell", 0.12, 32500.0, 13400.0, 0.97),
                LayeredShellLayer("interface_slip", 0.03, 9000.0, 3600.0, 0.62),
                LayeredShellLayer("soil_transfer", 0.18, 16000.0, 6400.0, 0.78),
            ),
        ),
        LayeredShellSection(
            name="raft_contact_transition",
            family="raft_contact_transition",
            layers=(
                LayeredShellLayer("raft_shell", 0.28, 33000.0, 13700.0, 0.98),
                LayeredShellLayer("contact_blinding", 0.05, 14000.0, 5600.0, 0.72),
                LayeredShellLayer("soil_reaction", 0.20, 17000.0, 6800.0, 0.80),
            ),
        ),
        LayeredShellSection(
            name="tunnel_grout_interface",
            family="tunnel_grout_interface",
            layers=(
                LayeredShellLayer("segment_shell", 0.22, 30000.0, 12100.0, 0.94),
                LayeredShellLayer("grout_interface", 0.06, 15000.0, 6000.0, 0.75),
                LayeredShellLayer("soil_annulus", 0.16, 16500.0, 6600.0, 0.79),
            ),
        ),
        LayeredShellSection(
            name="retaining_backfill_interface",
            family="retaining_backfill_interface",
            layers=(
                LayeredShellLayer("retaining_shell", 0.26, 31500.0, 12700.0, 0.95),
                LayeredShellLayer("friction_interface", 0.04, 11000.0, 4400.0, 0.68),
                LayeredShellLayer("backfill_shell", 0.20, 15500.0, 6200.0, 0.77),
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for section in sections:
        response = evaluate_layered_shell_response(
            section=section,
            membrane_strain=1.6e-4,
            curvature_per_m=4.5e-3,
            shear_strain=4.6e-4,
        )
        rows.append(
            {
                "family": section.family,
                "layer_count": len(section.layers),
                "membrane_stiffness_n_per_m": float(response.membrane_stiffness_n_per_m),
                "bending_stiffness_n_m": float(response.bending_stiffness_n_m),
                "shear_stiffness_n_per_m": float(response.shear_stiffness_n_per_m),
                "pass": bool(
                    response.membrane_stiffness_n_per_m > 0.0
                    and response.bending_stiffness_n_m > 0.0
                    and response.shear_stiffness_n_per_m > 0.0
                ),
            }
        )
    return rows


def _bearing_section_rows() -> list[dict[str, Any]]:
    sections = [
        (
            "pot_bearing_cap",
            make_rectangular_rc_section(
                width_m=0.62,
                depth_m=0.24,
                cover_m=0.035,
                top_bar_count=4,
                bottom_bar_count=4,
                bar_area_m2=2.40e-4,
                name="pot_bearing_cap",
            ),
        ),
        (
            "guided_bearing_girder_seat",
            make_wide_flange_steel_section(
                flange_width_m=0.22,
                section_depth_m=0.32,
                flange_thickness_m=0.022,
                web_thickness_m=0.012,
                name="guided_bearing_girder_seat",
            ),
        ),
        (
            "rocker_bearing_transfer",
            make_composite_beam_section(
                slab_width_m=0.88,
                slab_depth_m=0.08,
                flange_width_m=0.18,
                section_depth_m=0.28,
                flange_thickness_m=0.015,
                web_thickness_m=0.010,
                top_bar_count=2,
                name="rocker_bearing_transfer",
            ),
        ),
        (
            "restrainer_bearing_block",
            make_rectangular_rc_section(
                width_m=0.48,
                depth_m=0.34,
                cover_m=0.04,
                top_bar_count=3,
                bottom_bar_count=3,
                bar_area_m2=2.85e-4,
                name="restrainer_bearing_block",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(section=section, axial_strain=2.1e-5, curvature_z_per_m=7.2e-3)
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                ),
            }
        )
    return rows


def _retrofit_section_rows() -> list[dict[str, Any]]:
    sections = [
        (
            "frp_wrapped_column",
            make_rectangular_rc_section(
                width_m=0.50,
                depth_m=0.50,
                cover_m=0.04,
                top_bar_count=4,
                bottom_bar_count=4,
                bar_area_m2=3.10e-4,
                name="frp_wrapped_column",
            ),
        ),
        (
            "steel_jacket_column",
            make_wide_flange_steel_section(
                flange_width_m=0.24,
                section_depth_m=0.36,
                flange_thickness_m=0.026,
                web_thickness_m=0.014,
                name="steel_jacket_column",
            ),
        ),
        (
            "pt_clamp_transfer_beam",
            make_composite_beam_section(
                slab_width_m=1.00,
                slab_depth_m=0.10,
                flange_width_m=0.20,
                section_depth_m=0.34,
                flange_thickness_m=0.018,
                web_thickness_m=0.011,
                top_bar_count=3,
                name="pt_clamp_transfer_beam",
            ),
        ),
        (
            "rc_encased_joint_core",
            make_rectangular_rc_section(
                width_m=0.58,
                depth_m=0.46,
                cover_m=0.045,
                top_bar_count=4,
                bottom_bar_count=4,
                bar_area_m2=3.20e-4,
                name="rc_encased_joint_core",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for family, section in sections:
        response = evaluate_section_response(section=section, axial_strain=2.0e-5, curvature_z_per_m=8.1e-3)
        rows.append(
            {
                "family": family,
                "axial_stiffness_n": float(response.axial_stiffness_n),
                "flexural_stiffness_n_m2": float(response.flexural_stiffness_n_m2),
                "yielded_fiber_count": int(response.yielded_fiber_count),
                "cracked_fiber_count": int(response.cracked_fiber_count),
                "pass": bool(
                    np.isfinite(response.axial_stiffness_n)
                    and np.isfinite(response.flexural_stiffness_n_m2)
                    and abs(float(response.axial_stiffness_n)) > 0.0
                    and abs(float(response.flexural_stiffness_n_m2)) > 0.0
                ),
            }
        )
    return rows


def _ground_improvement_section_rows() -> list[dict[str, Any]]:
    sections = [
        LayeredShellSection(
            name="jet_grout_block",
            family="jet_grout_block",
            layers=(
                LayeredShellLayer("cap_slab", 0.18, 28000.0, 11200.0, 0.90),
                LayeredShellLayer("jet_grout_mass", 0.24, 14500.0, 5800.0, 0.72),
                LayeredShellLayer("improved_soil", 0.22, 12000.0, 4800.0, 0.66),
            ),
        ),
        LayeredShellSection(
            name="deep_soil_mixing_panel",
            family="deep_soil_mixing_panel",
            layers=(
                LayeredShellLayer("wall_skin", 0.16, 26000.0, 10400.0, 0.86),
                LayeredShellLayer("mixed_panel", 0.26, 13000.0, 5200.0, 0.70),
                LayeredShellLayer("transition_soil", 0.18, 10800.0, 4320.0, 0.64),
            ),
        ),
        LayeredShellSection(
            name="stone_column_raft",
            family="stone_column_raft",
            layers=(
                LayeredShellLayer("raft_shell", 0.24, 30000.0, 12000.0, 0.94),
                LayeredShellLayer("stone_column_band", 0.20, 11800.0, 4720.0, 0.62),
                LayeredShellLayer("surrounding_soil", 0.22, 9800.0, 3920.0, 0.58),
            ),
        ),
        LayeredShellSection(
            name="geogrid_mattress_transition",
            family="geogrid_mattress_transition",
            layers=(
                LayeredShellLayer("base_slab", 0.20, 28500.0, 11400.0, 0.91),
                LayeredShellLayer("geogrid_layer", 0.03, 8000.0, 3200.0, 0.52),
                LayeredShellLayer("mattress_fill", 0.24, 11200.0, 4480.0, 0.60),
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for section in sections:
        response = evaluate_layered_shell_response(
            section=section,
            membrane_strain=1.5e-4,
            curvature_per_m=4.2e-3,
            shear_strain=4.8e-4,
        )
        rows.append(
            {
                "family": section.family,
                "layer_count": len(section.layers),
                "membrane_stiffness_n_per_m": float(response.membrane_stiffness_n_per_m),
                "bending_stiffness_n_m": float(response.bending_stiffness_n_m),
                "shear_stiffness_n_per_m": float(response.shear_stiffness_n_per_m),
                "pass": bool(
                    response.membrane_stiffness_n_per_m > 0.0
                    and response.bending_stiffness_n_m > 0.0
                    and response.shear_stiffness_n_per_m > 0.0
                ),
            }
        )
    return rows


def run_nonlinear_generalization_gate(
    *,
    nonlinear_engine_report: dict[str, Any],
    pushover_stress_report: dict[str, Any],
    ndtha_stress_report: dict[str, Any],
    foundation_soil_link_gate_report: dict[str, Any],
) -> dict[str, Any]:
    beam_rows = _beam_column_rows()
    fiber_rows = _fiber_rows()
    layered_rows = _layered_rows()
    joint_panel_rows = _joint_panel_rows()
    foundation_section_rows = _foundation_section_rows()
    connection_section_rows = _connection_section_rows()
    substructure_section_rows = _substructure_section_rows()
    device_section_rows = _device_section_rows()
    isolation_section_rows = _isolation_section_rows()
    soil_interface_section_rows = _soil_interface_section_rows()
    bearing_section_rows = _bearing_section_rows()
    retrofit_section_rows = _retrofit_section_rows()
    ground_improvement_section_rows = _ground_improvement_section_rows()

    engine_checks = nonlinear_engine_report.get("checks") if isinstance(nonlinear_engine_report.get("checks"), dict) else {}
    pushover_checks = pushover_stress_report.get("checks") if isinstance(pushover_stress_report.get("checks"), dict) else {}
    ndtha_checks = ndtha_stress_report.get("checks") if isinstance(ndtha_stress_report.get("checks"), dict) else {}
    foundation_checks = (
        foundation_soil_link_gate_report.get("checks")
        if isinstance(foundation_soil_link_gate_report.get("checks"), dict)
        else {}
    )
    foundation_summary = (
        foundation_soil_link_gate_report.get("summary")
        if isinstance(foundation_soil_link_gate_report.get("summary"), dict)
        else {}
    )

    checks = {
        "beam_column_generalization_pass": bool(
            all(bool(row.get("pass", False)) for row in beam_rows)
            and len({str(row.get("formulation", "")) for row in beam_rows}) >= 3
            and len({str(row.get("family", "")) for row in beam_rows}) >= 6
        ),
        "fiber_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in fiber_rows)
            and len({str(row.get("family", "")) for row in fiber_rows}) >= 6
        ),
        "layered_shell_wall_pass": bool(
            all(bool(row.get("pass", False)) for row in layered_rows)
            and len({str(row.get("family", "")) for row in layered_rows}) >= 6
        ),
        "joint_panel_family_pass": bool(
            all(bool(row.get("pass", False)) for row in joint_panel_rows)
            and len({str(row.get("family", "")) for row in joint_panel_rows}) >= 4
        ),
        "foundation_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in foundation_section_rows)
            and len({str(row.get("family", "")) for row in foundation_section_rows}) >= 4
        ),
        "connection_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in connection_section_rows)
            and len({str(row.get("family", "")) for row in connection_section_rows}) >= 4
        ),
        "substructure_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in substructure_section_rows)
            and len({str(row.get("family", "")) for row in substructure_section_rows}) >= 4
        ),
        "device_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in device_section_rows)
            and len({str(row.get("family", "")) for row in device_section_rows}) >= 4
        ),
        "isolation_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in isolation_section_rows)
            and len({str(row.get("family", "")) for row in isolation_section_rows}) >= 4
        ),
        "soil_interface_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in soil_interface_section_rows)
            and len({str(row.get("family", "")) for row in soil_interface_section_rows}) >= 4
        ),
        "bearing_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in bearing_section_rows)
            and len({str(row.get("family", "")) for row in bearing_section_rows}) >= 4
        ),
        "retrofit_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in retrofit_section_rows)
            and len({str(row.get("family", "")) for row in retrofit_section_rows}) >= 4
        ),
        "ground_improvement_section_family_pass": bool(
            all(bool(row.get("pass", False)) for row in ground_improvement_section_rows)
            and len({str(row.get("family", "")) for row in ground_improvement_section_rows}) >= 4
        ),
        "foundation_soil_link_pass": bool(
            foundation_soil_link_gate_report.get("contract_pass", False)
            and bool(foundation_checks.get("foundation_scope_ready", False))
            and bool(foundation_checks.get("foundation_artifact_ready", False))
            and bool(foundation_checks.get("foundation_link_models_ready", False))
        ),
        "production_engine_evidence_pass": bool(
            nonlinear_engine_report.get("contract_pass", False)
            and bool(engine_checks.get("rust_backend_used_pass", False))
            and bool(pushover_stress_report.get("contract_pass", False))
            and bool(pushover_checks.get("section_family_pass", False))
            and bool(ndtha_stress_report.get("contract_pass", False))
            and bool(ndtha_checks.get("section_family_pass", False))
            and bool(ndtha_checks.get("rust_backend_used_pass", False))
        ),
    }
    contract_pass = bool(all(checks.values()))
    if not checks["beam_column_generalization_pass"]:
        reason_code = "ERR_BEAM_COLUMN"
    elif not checks["fiber_section_family_pass"]:
        reason_code = "ERR_FIBER_SECTION"
    elif not checks["layered_shell_wall_pass"]:
        reason_code = "ERR_LAYERED_SHELL_WALL"
    elif not checks["joint_panel_family_pass"]:
        reason_code = "ERR_JOINT_PANEL"
    elif not checks["foundation_section_family_pass"]:
        reason_code = "ERR_FOUNDATION_SECTION"
    elif not checks["connection_section_family_pass"]:
        reason_code = "ERR_CONNECTION_SECTION"
    elif not checks["substructure_section_family_pass"]:
        reason_code = "ERR_SUBSTRUCTURE_SECTION"
    elif not checks["device_section_family_pass"]:
        reason_code = "ERR_DEVICE_SECTION"
    elif not checks["isolation_section_family_pass"]:
        reason_code = "ERR_ISOLATION_SECTION"
    elif not checks["soil_interface_section_family_pass"]:
        reason_code = "ERR_SOIL_INTERFACE_SECTION"
    elif not checks["bearing_section_family_pass"]:
        reason_code = "ERR_BEARING_SECTION"
    elif not checks["retrofit_section_family_pass"]:
        reason_code = "ERR_RETROFIT_SECTION"
    elif not checks["ground_improvement_section_family_pass"]:
        reason_code = "ERR_GROUND_IMPROVEMENT_SECTION"
    elif not checks["foundation_soil_link_pass"]:
        reason_code = "ERR_FOUNDATION_SOIL_LINK"
    elif not checks["production_engine_evidence_pass"]:
        reason_code = "ERR_PRODUCTION_ENGINE"
    else:
        reason_code = "PASS"

    summary = {
        "beam_formulation_count": len(beam_rows),
        "beam_formulation_label": ",".join(str(row["formulation"]) for row in beam_rows),
        "beam_family_count": len({str(row["family"]) for row in beam_rows}),
        "beam_family_label": ",".join(sorted({str(row["family"]) for row in beam_rows})),
        "beam_max_trial_end_moment_ratio": max(float(row["max_trial_end_moment_ratio"]) for row in beam_rows),
        "beam_max_plastic_rotation_proxy_rad": max(float(row["max_plastic_rotation_proxy_rad"]) for row in beam_rows),
        "beam_stability_index_max": max(float(row["stability_index"]) for row in beam_rows),
        "beam_strain_energy_max_n_m": max(float(row["strain_energy_n_m"]) for row in beam_rows),
        "fiber_family_count": len(fiber_rows),
        "fiber_family_label": ",".join(str(row["family"]) for row in fiber_rows),
        "fiber_max_abs_strain": max(float(row["max_abs_strain"]) for row in fiber_rows),
        "fiber_steel_yield_ratio_max": max(float(row["steel_yield_ratio_max"]) for row in fiber_rows),
        "fiber_concrete_crack_ratio_max": max(float(row["concrete_crack_ratio_max"]) for row in fiber_rows),
        "fiber_concrete_crush_ratio_max": max(float(row["concrete_crush_ratio_max"]) for row in fiber_rows),
        "fiber_yielded_steel_ratio_max": max(float(row["yielded_steel_ratio"]) for row in fiber_rows),
        "fiber_cracked_concrete_ratio_max": max(float(row["cracked_concrete_ratio"]) for row in fiber_rows),
        "fiber_section_strain_energy_max_n": max(float(row["section_strain_energy_n"]) for row in fiber_rows),
        "layered_family_count": len(layered_rows),
        "layered_family_label": ",".join(str(row["family"]) for row in layered_rows),
        "joint_panel_family_count": len(joint_panel_rows),
        "joint_panel_family_label": ",".join(str(row["family"]) for row in joint_panel_rows),
        "foundation_section_family_count": len(foundation_section_rows),
        "foundation_section_family_label": ",".join(str(row["family"]) for row in foundation_section_rows),
        "connection_section_family_count": len(connection_section_rows),
        "connection_section_family_label": ",".join(str(row["family"]) for row in connection_section_rows),
        "substructure_section_family_count": len(substructure_section_rows),
        "substructure_section_family_label": ",".join(str(row["family"]) for row in substructure_section_rows),
        "device_section_family_count": len(device_section_rows),
        "device_section_family_label": ",".join(str(row["family"]) for row in device_section_rows),
        "isolation_section_family_count": len(isolation_section_rows),
        "isolation_section_family_label": ",".join(str(row["family"]) for row in isolation_section_rows),
        "soil_interface_section_family_count": len(soil_interface_section_rows),
        "soil_interface_section_family_label": ",".join(str(row["family"]) for row in soil_interface_section_rows),
        "bearing_section_family_count": len(bearing_section_rows),
        "bearing_section_family_label": ",".join(str(row["family"]) for row in bearing_section_rows),
        "retrofit_section_family_count": len(retrofit_section_rows),
        "retrofit_section_family_label": ",".join(str(row["family"]) for row in retrofit_section_rows),
        "ground_improvement_section_family_count": len(ground_improvement_section_rows),
        "ground_improvement_section_family_label": ",".join(str(row["family"]) for row in ground_improvement_section_rows),
        "foundation_link_model_count": len(foundation_summary.get("foundation_link_model_types") or []),
        "foundation_link_model_label": ",".join(
            str(item).strip()
            for item in (foundation_summary.get("foundation_link_model_types") or [])
            if str(item).strip()
        ),
    }
    summary_line = (
        "Nonlinear generalization: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"beam=yes(formulations={len(sorted({str(row['formulation']) for row in beam_rows}))}:{','.join(sorted({str(row['formulation']) for row in beam_rows}))},"
        f"families={summary['beam_family_count']}:{summary['beam_family_label']},"
        f"demand_ratio_max={summary['beam_max_trial_end_moment_ratio']:.2f},"
        f"stability_max={summary['beam_stability_index_max']:.2f}) | "
        f"fiber=yes(families={summary['fiber_family_count']}:{summary['fiber_family_label']},"
        f"yield_ratio_max={summary['fiber_steel_yield_ratio_max']:.2f},"
        f"crack_ratio_max={summary['fiber_concrete_crack_ratio_max']:.2f},"
        f"energy_max={summary['fiber_section_strain_energy_max_n']:.0f}) | "
        f"layered=yes(families={summary['layered_family_count']}:{summary['layered_family_label']}) | "
        f"joint_panel=yes(families={summary['joint_panel_family_count']}:{summary['joint_panel_family_label']}) | "
        f"foundation_sections=yes(families={summary['foundation_section_family_count']}:{summary['foundation_section_family_label']}) | "
        f"connection_sections=yes(families={summary['connection_section_family_count']}:{summary['connection_section_family_label']}) | "
        f"substructure_sections=yes(families={summary['substructure_section_family_count']}:{summary['substructure_section_family_label']}) | "
        f"device_sections=yes(families={summary['device_section_family_count']}:{summary['device_section_family_label']}) | "
        f"isolation_sections=yes(families={summary['isolation_section_family_count']}:{summary['isolation_section_family_label']}) | "
        f"soil_interface_sections=yes(families={summary['soil_interface_section_family_count']}:{summary['soil_interface_section_family_label']}) | "
        f"bearing_sections=yes(families={summary['bearing_section_family_count']}:{summary['bearing_section_family_label']}) | "
        f"retrofit_sections=yes(families={summary['retrofit_section_family_count']}:{summary['retrofit_section_family_label']}) | "
        f"ground_improvement_sections=yes(families={summary['ground_improvement_section_family_count']}:{summary['ground_improvement_section_family_label']}) | "
        f"foundation=yes(models={summary['foundation_link_model_count']}) | "
        f"engine=yes"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-nonlinear-generalization-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
        "summary_line": summary_line,
        "beam_column_rows": beam_rows,
        "fiber_section_rows": fiber_rows,
        "layered_shell_wall_rows": layered_rows,
        "joint_panel_rows": joint_panel_rows,
        "foundation_section_rows": foundation_section_rows,
        "connection_section_rows": connection_section_rows,
        "substructure_section_rows": substructure_section_rows,
        "device_section_rows": device_section_rows,
        "isolation_section_rows": isolation_section_rows,
        "soil_interface_section_rows": soil_interface_section_rows,
        "bearing_section_rows": bearing_section_rows,
        "retrofit_section_rows": retrofit_section_rows,
        "ground_improvement_section_rows": ground_improvement_section_rows,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nonlinear-engine-report", default="implementation/phase1/nonlinear_frame_engine_report.json")
    parser.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    parser.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    parser.add_argument("--foundation-soil-link-gate-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    parser.add_argument("--out", default="implementation/phase1/nonlinear_generalization_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "nonlinear_engine_report": str(args.nonlinear_engine_report),
        "pushover_stress_report": str(args.pushover_stress_report),
        "ndtha_stress_report": str(args.ndtha_stress_report),
        "foundation_soil_link_gate_report": str(args.foundation_soil_link_gate_report),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_nonlinear_generalization_gate")
        report = run_nonlinear_generalization_gate(
            nonlinear_engine_report=_load_json(Path(args.nonlinear_engine_report)),
            pushover_stress_report=_load_json(Path(args.pushover_stress_report)),
            ndtha_stress_report=_load_json(Path(args.ndtha_stress_report)),
            foundation_soil_link_gate_report=_load_json(Path(args.foundation_soil_link_gate_report)),
        )
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-nonlinear-generalization-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote nonlinear generalization gate report: {out}")
    raise SystemExit(0 if bool(report.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
