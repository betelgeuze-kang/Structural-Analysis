#!/usr/bin/env python3
"""Fiber-section utilities for reduced-order nonlinear members."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

try:
    from implementation.phase1.rc_constitutive_library import (
        ConcreteMaterial,
        SteelMaterial,
        concrete_response,
        steel_response,
    )
except ImportError:  # pragma: no cover - script execution fallback
    from rc_constitutive_library import (
        ConcreteMaterial,
        SteelMaterial,
        concrete_response,
        steel_response,
    )


StressFn = Callable[[float], float]


@dataclass(frozen=True)
class Fiber:
    y_m: float
    area_m2: float
    material: str


@dataclass
class FiberSection:
    fibers: list[Fiber]
    name: str = "section"


@dataclass(frozen=True)
class FiberSectionResponse:
    axial_force_n: float
    moment_z_n_m: float
    axial_stiffness_n: float
    flexural_stiffness_n_m2: float
    max_abs_strain: float
    steel_fiber_count: int
    concrete_fiber_count: int
    yielded_fiber_count: int
    cracked_fiber_count: int
    steel_max_abs_strain: float
    concrete_max_tension_strain: float
    concrete_max_compression_strain: float
    steel_yield_ratio_max: float
    concrete_crack_ratio_max: float
    concrete_crush_ratio_max: float
    yielded_steel_ratio: float
    cracked_concrete_ratio: float
    neutral_axis_y_m: float | None
    section_strain_energy_n: float


def rectangular_patch(
    *,
    width_m: float,
    depth_m: float,
    nx: int,
    ny: int,
    material: str,
) -> list[Fiber]:
    dx = float(width_m) / max(int(nx), 1)
    dy = float(depth_m) / max(int(ny), 1)
    area = dx * dy
    ys = np.linspace(-0.5 * depth_m + 0.5 * dy, 0.5 * depth_m - 0.5 * dy, num=max(int(ny), 1), dtype=np.float64)
    fibers: list[Fiber] = []
    for y in ys:
        for _ in range(max(int(nx), 1)):
            fibers.append(Fiber(y_m=float(y), area_m2=float(area), material=str(material)))
    return fibers


def rebar_layer(
    *,
    y_m: float,
    bar_count: int,
    area_each_m2: float,
    material: str = "steel",
) -> list[Fiber]:
    return [Fiber(y_m=float(y_m), area_m2=float(area_each_m2), material=str(material)) for _ in range(max(int(bar_count), 0))]


def make_rectangular_rc_section(
    *,
    width_m: float,
    depth_m: float,
    cover_m: float,
    concrete_fibers_x: int = 8,
    concrete_fibers_y: int = 12,
    top_bar_count: int = 4,
    bottom_bar_count: int = 4,
    bar_area_m2: float = 3.87e-4,
    name: str = "rect_rc",
) -> FiberSection:
    fibers = rectangular_patch(
        width_m=width_m,
        depth_m=depth_m,
        nx=concrete_fibers_x,
        ny=concrete_fibers_y,
        material="concrete",
    )
    y_top = 0.5 * float(depth_m) - float(cover_m)
    y_bottom = -0.5 * float(depth_m) + float(cover_m)
    fibers.extend(rebar_layer(y_m=y_top, bar_count=top_bar_count, area_each_m2=bar_area_m2))
    fibers.extend(rebar_layer(y_m=y_bottom, bar_count=bottom_bar_count, area_each_m2=bar_area_m2))
    return FiberSection(fibers=fibers, name=name)


def make_wide_flange_steel_section(
    *,
    flange_width_m: float,
    section_depth_m: float,
    flange_thickness_m: float,
    web_thickness_m: float,
    flange_fibers_x: int = 8,
    flange_fibers_y: int = 2,
    web_fibers_x: int = 2,
    web_fibers_y: int = 8,
    name: str = "wide_flange_steel",
) -> FiberSection:
    half_depth = 0.5 * float(section_depth_m)
    flange_core_depth = max(float(flange_thickness_m), 1.0e-3)
    web_depth = max(float(section_depth_m) - 2.0 * flange_core_depth, flange_core_depth)
    fibers: list[Fiber] = []
    fibers.extend(
        rectangular_patch(
            width_m=float(flange_width_m),
            depth_m=flange_core_depth,
            nx=flange_fibers_x,
            ny=flange_fibers_y,
            material="steel",
        )
    )
    fibers.extend(
        rectangular_patch(
            width_m=float(web_thickness_m),
            depth_m=web_depth,
            nx=web_fibers_x,
            ny=web_fibers_y,
            material="steel",
        )
    )
    fibers.extend(
        rectangular_patch(
            width_m=float(flange_width_m),
            depth_m=flange_core_depth,
            nx=flange_fibers_x,
            ny=flange_fibers_y,
            material="steel",
        )
    )
    shifted: list[Fiber] = []
    top_shift = half_depth - 0.5 * flange_core_depth
    bot_shift = -half_depth + 0.5 * flange_core_depth
    first_count = flange_fibers_x * flange_fibers_y
    second_count = web_fibers_x * web_fibers_y
    for idx, fiber in enumerate(fibers):
        if idx < first_count:
            shifted.append(Fiber(y_m=float(fiber.y_m + top_shift), area_m2=fiber.area_m2, material=fiber.material))
        elif idx < first_count + second_count:
            shifted.append(Fiber(y_m=float(fiber.y_m), area_m2=fiber.area_m2, material=fiber.material))
        else:
            shifted.append(Fiber(y_m=float(fiber.y_m + bot_shift), area_m2=fiber.area_m2, material=fiber.material))
    return FiberSection(fibers=shifted, name=name)


def make_composite_beam_section(
    *,
    slab_width_m: float,
    slab_depth_m: float,
    flange_width_m: float,
    section_depth_m: float,
    flange_thickness_m: float,
    web_thickness_m: float,
    cover_m: float = 0.04,
    top_bar_count: int = 4,
    bottom_bar_count: int = 0,
    bar_area_m2: float = 2.85e-4,
    name: str = "composite_beam",
) -> FiberSection:
    steel = make_wide_flange_steel_section(
        flange_width_m=flange_width_m,
        section_depth_m=section_depth_m,
        flange_thickness_m=flange_thickness_m,
        web_thickness_m=web_thickness_m,
        name=f"{name}_steel",
    )
    slab = make_rectangular_rc_section(
        width_m=slab_width_m,
        depth_m=slab_depth_m,
        cover_m=cover_m,
        concrete_fibers_x=8,
        concrete_fibers_y=4,
        top_bar_count=top_bar_count,
        bottom_bar_count=bottom_bar_count,
        bar_area_m2=bar_area_m2,
        name=f"{name}_slab",
    )
    slab_shift = 0.5 * float(section_depth_m) + 0.5 * float(slab_depth_m)
    fibers = list(steel.fibers)
    fibers.extend(
        Fiber(y_m=float(fiber.y_m + slab_shift), area_m2=fiber.area_m2, material=fiber.material)
        for fiber in slab.fibers
    )
    return FiberSection(fibers=fibers, name=name)


def _default_stress_models(
    concrete: ConcreteMaterial | None,
    steel: SteelMaterial | None,
) -> dict[str, StressFn]:
    cm = concrete or ConcreteMaterial()
    sm = steel or SteelMaterial()
    return {
        "concrete": lambda strain: concrete_response(strain, cm).stress_mpa,
        "steel": lambda strain: steel_response(strain, sm).stress_mpa,
    }


def evaluate_section_response(
    *,
    section: FiberSection,
    axial_strain: float,
    curvature_z_per_m: float,
    material_models: dict[str, StressFn] | None = None,
    concrete: ConcreteMaterial | None = None,
    steel: SteelMaterial | None = None,
) -> FiberSectionResponse:
    cm = concrete or ConcreteMaterial()
    sm = steel or SteelMaterial()
    if material_models is None:
        material_models = _default_stress_models(cm, sm)

    axial_force_n = 0.0
    moment_z_n_m = 0.0
    axial_stiffness_n = 0.0
    flexural_stiffness_n_m2 = 0.0
    max_abs_strain = 0.0
    steel_fiber_count = 0
    concrete_fiber_count = 0
    yielded = 0
    cracked = 0
    steel_max_abs_strain = 0.0
    concrete_max_tension_strain = 0.0
    concrete_max_compression_strain = 0.0
    steel_yield_ratio_max = 0.0
    concrete_crack_ratio_max = 0.0
    concrete_crush_ratio_max = 0.0
    section_strain_energy_n = 0.0
    dstrain = 1.0e-8

    for fiber in section.fibers:
        strain = float(axial_strain) - float(curvature_z_per_m) * float(fiber.y_m)
        max_abs_strain = max(max_abs_strain, abs(strain))
        stress_fn = material_models.get(fiber.material)
        if stress_fn is None:
            raise KeyError(f"material model missing: {fiber.material}")
        stress0 = float(stress_fn(strain))
        stress1 = float(stress_fn(strain + dstrain))
        tangent = (stress1 - stress0) / dstrain
        force_n = stress0 * 1.0e6 * float(fiber.area_m2)
        tangent_pa = tangent * 1.0e6
        axial_force_n += force_n
        moment_z_n_m += -force_n * float(fiber.y_m)
        axial_stiffness_n += tangent_pa * float(fiber.area_m2)
        flexural_stiffness_n_m2 += tangent_pa * float(fiber.area_m2) * float(fiber.y_m) ** 2
        section_strain_energy_n += 0.5 * abs(stress0 * 1.0e6 * strain * float(fiber.area_m2))
        if fiber.material == "steel":
            steel_fiber_count += 1
            steel_max_abs_strain = max(steel_max_abs_strain, abs(strain))
            steel_yield_ratio_max = max(steel_yield_ratio_max, abs(strain) / max(float(sm.eps_y), 1.0e-12))
            if abs(strain) > float(sm.eps_y):
                yielded += 1
        if fiber.material == "concrete":
            concrete_fiber_count += 1
            concrete_max_tension_strain = max(concrete_max_tension_strain, max(strain, 0.0))
            concrete_max_compression_strain = max(concrete_max_compression_strain, max(-strain, 0.0))
            concrete_crack_ratio_max = max(
                concrete_crack_ratio_max,
                max(strain, 0.0) / max(float(cm.eps_t_crack), 1.0e-12),
            )
            concrete_crush_ratio_max = max(
                concrete_crush_ratio_max,
                max(-strain, 0.0) / max(float(cm.eps_cu), 1.0e-12),
            )
            if strain > float(cm.eps_t_crack):
                cracked += 1

    neutral_axis_y_m = (
        float(axial_strain) / float(curvature_z_per_m)
        if abs(float(curvature_z_per_m)) > 1.0e-12
        else None
    )

    return FiberSectionResponse(
        axial_force_n=float(axial_force_n),
        moment_z_n_m=float(moment_z_n_m),
        axial_stiffness_n=float(axial_stiffness_n),
        flexural_stiffness_n_m2=float(flexural_stiffness_n_m2),
        max_abs_strain=float(max_abs_strain),
        steel_fiber_count=int(steel_fiber_count),
        concrete_fiber_count=int(concrete_fiber_count),
        yielded_fiber_count=int(yielded),
        cracked_fiber_count=int(cracked),
        steel_max_abs_strain=float(steel_max_abs_strain),
        concrete_max_tension_strain=float(concrete_max_tension_strain),
        concrete_max_compression_strain=float(concrete_max_compression_strain),
        steel_yield_ratio_max=float(steel_yield_ratio_max),
        concrete_crack_ratio_max=float(concrete_crack_ratio_max),
        concrete_crush_ratio_max=float(concrete_crush_ratio_max),
        yielded_steel_ratio=float(yielded / max(steel_fiber_count, 1)),
        cracked_concrete_ratio=float(cracked / max(concrete_fiber_count, 1)),
        neutral_axis_y_m=(float(neutral_axis_y_m) if neutral_axis_y_m is not None else None),
        section_strain_energy_n=float(section_strain_energy_n),
    )


__all__ = [
    "Fiber",
    "FiberSection",
    "FiberSectionResponse",
    "evaluate_section_response",
    "make_composite_beam_section",
    "make_rectangular_rc_section",
    "make_wide_flange_steel_section",
    "rectangular_patch",
    "rebar_layer",
]
