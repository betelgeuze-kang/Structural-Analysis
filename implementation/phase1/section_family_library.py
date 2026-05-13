#!/usr/bin/env python3
"""Story-wise section-family probes for reduced-order nonlinear runners."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from beam_column_nonlinear import BeamColumnProperties, solve_beam_column_response
from fiber_section import evaluate_section_response, make_rectangular_rc_section


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass(frozen=True)
class StorySectionFamily:
    story_index: int
    family_name: str
    width_m: float
    depth_m: float
    cover_m: float
    top_bar_count: int
    bottom_bar_count: int
    bar_area_m2: float
    curvature_factor: float
    axial_factor: float
    stiffness_bounds: tuple[float, float]
    yield_bounds: tuple[float, float]


def _family_name_for_story(topology: str, material_type: str, story_index: int, story_count: int) -> str:
    topo = str(topology).strip().lower()
    mat = str(material_type).strip().lower()
    z = float(story_index) / max(float(story_count - 1), 1.0)
    if topo == "wall-frame":
        if z <= 0.30:
            return "wall_boundary"
        if z <= 0.75:
            return "wall_web"
        return "slab_strip"
    if topo == "outrigger":
        if z <= 0.35:
            return "mega_column"
        if 0.35 < z < 0.70:
            return "outrigger_beam"
        return "core_column"
    if topo == "truss":
        if z <= 0.45:
            return "brace_chord"
        return "beam_strip"
    if mat in {"rc", "composite", "rc_composite"} and z > 0.70:
        return "slab_strip"
    return "frame_column" if z <= 0.50 else "beam_strip"


def _family_template(family_name: str) -> StorySectionFamily:
    table = {
        "wall_boundary": StorySectionFamily(0, family_name, 0.80, 0.90, 0.06, 8, 8, 5.07e-4, 1.20, 1.10, (0.96, 1.01), (0.96, 1.02)),
        "wall_web": StorySectionFamily(0, family_name, 0.55, 0.80, 0.05, 6, 6, 3.87e-4, 1.00, 1.00, (0.97, 1.01), (0.97, 1.02)),
        "slab_strip": StorySectionFamily(0, family_name, 0.90, 0.25, 0.04, 4, 4, 2.85e-4, 0.75, 0.80, (0.98, 1.01), (0.98, 1.02)),
        "mega_column": StorySectionFamily(0, family_name, 0.90, 1.00, 0.06, 8, 8, 5.07e-4, 1.05, 1.20, (0.97, 1.01), (0.97, 1.02)),
        "outrigger_beam": StorySectionFamily(0, family_name, 0.70, 0.85, 0.05, 6, 6, 3.87e-4, 1.15, 1.00, (0.97, 1.01), (0.97, 1.02)),
        "core_column": StorySectionFamily(0, family_name, 0.60, 0.75, 0.05, 6, 6, 3.87e-4, 0.95, 1.00, (0.98, 1.01), (0.98, 1.02)),
        "brace_chord": StorySectionFamily(0, family_name, 0.50, 0.65, 0.05, 4, 4, 3.10e-4, 1.10, 0.95, (0.98, 1.01), (0.98, 1.02)),
        "beam_strip": StorySectionFamily(0, family_name, 0.45, 0.65, 0.05, 4, 4, 3.10e-4, 0.90, 0.90, (0.98, 1.01), (0.98, 1.02)),
        "frame_column": StorySectionFamily(0, family_name, 0.55, 0.70, 0.05, 4, 4, 3.87e-4, 0.95, 1.00, (0.98, 1.01), (0.98, 1.02)),
    }
    return table.get(family_name, table["frame_column"])


def build_story_section_families(
    *,
    topology: str,
    material_type: str,
    story_count: int,
) -> list[StorySectionFamily]:
    families: list[StorySectionFamily] = []
    for idx in range(int(story_count)):
        family_name = _family_name_for_story(topology, material_type, idx, int(story_count))
        base = _family_template(family_name)
        families.append(
            StorySectionFamily(
                story_index=idx,
                family_name=family_name,
                width_m=base.width_m,
                depth_m=base.depth_m,
                cover_m=base.cover_m,
                top_bar_count=base.top_bar_count,
                bottom_bar_count=base.bottom_bar_count,
                bar_area_m2=base.bar_area_m2,
                curvature_factor=base.curvature_factor,
                axial_factor=base.axial_factor,
                stiffness_bounds=base.stiffness_bounds,
                yield_bounds=base.yield_bounds,
            )
        )
    return families


def evaluate_story_section_profile(
    *,
    topology: str,
    material_type: str,
    story_h_m: np.ndarray,
    drift_ratio_profile: np.ndarray,
    load_scale: float,
) -> dict:
    story_h = np.asarray(story_h_m, dtype=np.float64)
    drift = np.asarray(drift_ratio_profile, dtype=np.float64)
    n_story = int(story_h.shape[0])
    families = build_story_section_families(topology=topology, material_type=material_type, story_count=n_story)

    stiffness_scale = np.ones(n_story, dtype=np.float64)
    yield_scale = np.ones(n_story, dtype=np.float64)
    detail_rows: list[dict] = []
    family_counts: dict[str, int] = {}

    for i, family in enumerate(families):
        section = make_rectangular_rc_section(
            width_m=float(family.width_m),
            depth_m=float(family.depth_m),
            cover_m=float(family.cover_m),
            top_bar_count=int(family.top_bar_count),
            bottom_bar_count=int(family.bottom_bar_count),
            bar_area_m2=float(family.bar_area_m2),
            name=f"{family.family_name}_story_{i + 1}",
        )
        drift_i = float(abs(drift[i])) if i < drift.size else float(abs(drift[-1]))
        h_i = float(story_h[i]) if i < story_h.size else float(story_h[-1])
        axial_strain = _clamp(0.05 * drift_i * max(float(load_scale), 0.5) * float(family.axial_factor), 1.0e-5, 1.2e-4)
        curvature = _clamp(drift_i / max(h_i, 1e-9) * float(family.curvature_factor), 6.0e-5, 1.4e-3)
        elastic = evaluate_section_response(section=section, axial_strain=1.0e-5, curvature_z_per_m=0.0)
        nonlinear = evaluate_section_response(section=section, axial_strain=axial_strain, curvature_z_per_m=curvature)
        flex_ratio = float(nonlinear.flexural_stiffness_n_m2) / max(float(elastic.flexural_stiffness_n_m2), 1e-9)
        props = BeamColumnProperties(
            length_m=h_i,
            area_m2=float(family.width_m) * float(family.depth_m) * 0.78,
            e_mpa=30000.0,
            iy_m4=max(float(family.width_m) * float(family.depth_m) ** 3 / 12.0, 1e-6),
            yield_moment_kNm=800.0 * max(float(load_scale), 0.8) * float(family.axial_factor),
            hardening_ratio=0.05,
        )
        deformation = np.array([0.0, 0.0, curvature * h_i * 0.40, 0.0, drift_i * h_i, -curvature * h_i * 0.40], dtype=np.float64)
        beam = solve_beam_column_response(
            props=props,
            deformation_local=deformation,
            axial_force_n=3.0e6 * max(float(load_scale), 0.8) * float(family.axial_factor),
            include_geometric=True,
        )
        lo_k, hi_k = family.stiffness_bounds
        lo_y, hi_y = family.yield_bounds
        k_scale = _clamp(0.85 + 0.10 * flex_ratio + 0.05 * float(beam.tangent_scale), lo_k, hi_k)
        y_scale = _clamp(0.88 + 0.12 * float(beam.tangent_scale), lo_y, hi_y)
        stiffness_scale[i] = float(k_scale)
        yield_scale[i] = float(y_scale)
        family_counts[family.family_name] = int(family_counts.get(family.family_name, 0) + 1)
        detail_rows.append(
            {
                "story": int(i + 1),
                "family_name": family.family_name,
                "stiffness_scale": float(k_scale),
                "yield_scale": float(y_scale),
                "section_max_abs_strain": float(nonlinear.max_abs_strain),
                "section_steel_yield_ratio_max": float(nonlinear.steel_yield_ratio_max),
                "section_concrete_crack_ratio_max": float(nonlinear.concrete_crack_ratio_max),
                "section_concrete_crush_ratio_max": float(nonlinear.concrete_crush_ratio_max),
                "section_yielded_steel_ratio": float(nonlinear.yielded_steel_ratio),
                "section_cracked_concrete_ratio": float(nonlinear.cracked_concrete_ratio),
                "section_neutral_axis_y_m": (
                    float(nonlinear.neutral_axis_y_m) if nonlinear.neutral_axis_y_m is not None else None
                ),
                "section_strain_energy_n": float(nonlinear.section_strain_energy_n),
                "cracked_fiber_count": int(nonlinear.cracked_fiber_count),
                "yielded_fiber_count": int(nonlinear.yielded_fiber_count),
                "beam_tangent_scale": float(beam.tangent_scale),
                "beam_yielded_end_count": int(beam.yielded_end_count),
                "beam_max_trial_end_moment_ratio": float(np.max(beam.trial_end_moment_ratios)),
                "beam_max_plastic_rotation_proxy_rad": float(np.max(beam.plastic_rotation_proxy_rad)),
                "beam_stability_index": float(beam.stability_index),
                "beam_elastic_critical_axial_force_n": float(beam.elastic_critical_axial_force_n),
                "beam_strain_energy_n_m": float(beam.strain_energy_n_m),
                "section_moment_kNm": float(nonlinear.moment_z_n_m / 1000.0),
            }
        )

    return {
        "story_stiffness_scale": stiffness_scale,
        "story_yield_scale": yield_scale,
        "family_counts": family_counts,
        "detail_rows": detail_rows,
        "summary": {
            "story_count": int(n_story),
            "stiffness_scale_mean": float(np.mean(stiffness_scale)) if n_story else 1.0,
            "stiffness_scale_min": float(np.min(stiffness_scale)) if n_story else 1.0,
            "yield_scale_mean": float(np.mean(yield_scale)) if n_story else 1.0,
            "yield_scale_min": float(np.min(yield_scale)) if n_story else 1.0,
            "section_max_abs_strain": (
                float(max(float(row["section_max_abs_strain"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "section_steel_yield_ratio_max": (
                float(max(float(row["section_steel_yield_ratio_max"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "section_concrete_crack_ratio_max": (
                float(max(float(row["section_concrete_crack_ratio_max"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "section_concrete_crush_ratio_max": (
                float(max(float(row["section_concrete_crush_ratio_max"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "section_yielded_steel_ratio_mean": (
                float(np.mean([float(row["section_yielded_steel_ratio"]) for row in detail_rows])) if detail_rows else 0.0
            ),
            "section_cracked_concrete_ratio_mean": (
                float(np.mean([float(row["section_cracked_concrete_ratio"]) for row in detail_rows])) if detail_rows else 0.0
            ),
            "section_strain_energy_total_n": (
                float(sum(float(row["section_strain_energy_n"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "section_strain_energy_max_n": (
                float(max(float(row["section_strain_energy_n"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "beam_story_count": int(n_story),
            "beam_tangent_scale_mean": (
                float(np.mean([float(row["beam_tangent_scale"]) for row in detail_rows])) if detail_rows else 1.0
            ),
            "beam_tangent_scale_min": (
                float(min(float(row["beam_tangent_scale"]) for row in detail_rows)) if detail_rows else 1.0
            ),
            "beam_yielded_story_count": (
                int(sum(int(row["beam_yielded_end_count"]) > 0 for row in detail_rows)) if detail_rows else 0
            ),
            "beam_max_trial_end_moment_ratio": (
                float(max(float(row["beam_max_trial_end_moment_ratio"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "beam_max_plastic_rotation_proxy_rad": (
                float(max(float(row["beam_max_plastic_rotation_proxy_rad"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "beam_stability_index_mean": (
                float(np.mean([float(row["beam_stability_index"]) for row in detail_rows])) if detail_rows else 0.0
            ),
            "beam_stability_index_max": (
                float(max(float(row["beam_stability_index"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "beam_strain_energy_total_n_m": (
                float(sum(float(row["beam_strain_energy_n_m"]) for row in detail_rows)) if detail_rows else 0.0
            ),
            "beam_strain_energy_max_n_m": (
                float(max(float(row["beam_strain_energy_n_m"]) for row in detail_rows)) if detail_rows else 0.0
            ),
        },
    }


__all__ = [
    "StorySectionFamily",
    "build_story_section_families",
    "evaluate_story_section_profile",
]
