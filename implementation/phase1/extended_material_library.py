#!/usr/bin/env python3
"""Extended constitutive library for comprehensive structural materials.

Provides reduced-order material laws for:
- Prestressed concrete (bonded/unbonded tendons)
- Structural cables (high-strength steel, CFRP cables)
- FRP composites (GFRP, CFRP, AFRP)
- Geotechnical/foundation (soil, rock, pile, mat)
- Timber (glulam, CLT, LVL)
- Fasteners (bolts, anchors, welds)
- Dampers and seismic isolators
- Masonry and cold-formed steel
- Durability/corrosion models
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Tuple


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


# =============================================================================
# Prestressed Concrete
# =============================================================================

@dataclass(frozen=True)
class PrestressingSteel:
    """Prestressing strand/wire material (e.g., 1860 MPa strand)."""
    fpk_mpa: float = 1860.0
    fpy_mpa: float = 1670.0
    ep_mpa: float = 195000.0
    eps_pu: float = 0.035
    relaxation_1000h: float = 0.025  # 2.5% relaxation at 1000h
    low_relaxation: bool = True
    bonded: bool = True

    @property
    def eps_py(self) -> float:
        return float(self.fpy_mpa) / max(float(self.ep_mpa), 1e-9)


@dataclass(frozen=True)
class PrestressingDuct:
    """Duct/sheath for prestressing tendons."""
    diameter_mm: float = 60.0
    friction_coeff: float = 0.20
    wobble_coeff: float = 0.005  # per meter
    bonded: bool = True


@dataclass(frozen=True)
class PrestressedConcreteSection:
    """Prestressed concrete section with tendon layout."""
    concrete_area_m2: float = 0.30
    tendon_area_m2: float = 0.004
    prestress_force_kn: float = 5000.0
    eccentricity_m: float = 0.30
    concrete_fc_mpa: float = 40.0
    steel: PrestressingSteel = field(default_factory=PrestressingSteel)
    duct: PrestressingDuct = field(default_factory=PrestressingDuct)
    time_loss_ratio: float = 0.15  # combined long-term losses


def prestressing_steel_response(strain: float, mat: PrestressingSteel | None = None) -> "MaterialSnapshot":
    """Prestressing steel stress-strain with relaxation-aware bounds."""
    if mat is None:
        mat = PrestressingSteel()
    e = float(strain)
    ep = float(mat.ep_mpa)
    eps_y = mat.eps_py
    ea = abs(e)
    sign = 1.0 if e >= 0.0 else -1.0

    if ea <= eps_y:
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * ep * ea,
            tangent_mpa=ep,
            state_tag="prestress_elastic",
        )

    # Yield plateau with slight hardening (prestressing steel has limited plateau)
    hardening_ratio = 0.008
    plastic = ea - eps_y
    stress_abs = float(mat.fpy_mpa) + hardening_ratio * ep * plastic
    stress_abs = min(stress_abs, float(mat.fpk_mpa))

    if ea >= float(mat.eps_pu):
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * stress_abs,
            tangent_mpa=0.0,
            state_tag="prestress_fracture",
        )

    state_tag = "prestress_hardening" if stress_abs < float(mat.fpk_mpa) else "prestress_peak"
    tangent = hardening_ratio * ep if stress_abs < float(mat.fpk_mpa) else 0.0
    return MaterialSnapshot(strain=e, stress_mpa=sign * stress_abs, tangent_mpa=tangent, state_tag=state_tag)


def prestress_loss_ratio(
    *,
    initial_force_kn: float,
    age_days: float,
    mat: PrestressingSteel | None = None,
    creep_factor: float = 1.0,
    shrinkage_strain: float = 0.0002,
) -> float:
    """Estimate combined prestress loss ratio (anchorage, friction, elastic, creep, shrinkage, relaxation)."""
    if mat is None:
        mat = PrestressingSteel()
    # Simplified combined loss model
    elastic_loss = 0.05
    creep_loss = _clamp(0.10 * creep_factor, 0.0, 0.20)
    shrinkage_loss = _clamp(shrinkage_strain * float(mat.ep_mpa) / max(float(mat.fpk_mpa), 1.0) * 1000.0, 0.0, 0.10)
    relaxation_loss = _clamp(
        float(mat.relaxation_1000h) * (0.5 + 0.5 * math.log(max(age_days, 1.0) / 1000.0 + 1.0)),
        0.0,
        0.12,
    )
    total = _clamp(elastic_loss + creep_loss + shrinkage_loss + relaxation_loss, 0.0, 0.55)
    return total


# =============================================================================
# Structural Cables
# =============================================================================

@dataclass(frozen=True)
class CableMaterial:
    """High-strength structural cable (e.g., suspension bridge cables)."""
    fpu_mpa: float = 1770.0
    fpy_mpa: float = 1590.0
    ep_mpa: float = 195000.0
    eps_pu: float = 0.040
    damping_ratio: float = 0.005
    cable_type: str = "locked_coil"  # locked_coil, spiral_strand, parallel_wire, CFRP

    @property
    def eps_py(self) -> float:
        return float(self.fpy_mpa) / max(float(self.ep_mpa), 1e-9)


def cable_response(strain: float, mat: CableMaterial | None = None) -> "MaterialSnapshot":
    """Cable stress-strain with geometric stiffness for sag."""
    if mat is None:
        mat = CableMaterial()
    e = float(strain)
    ep = float(mat.ep_mpa)
    ea = abs(e)
    sign = 1.0 if e >= 0.0 else -1.0
    eps_y = mat.eps_py

    if ea <= eps_y:
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * ep * ea,
            tangent_mpa=ep,
            state_tag="cable_elastic",
        )

    hardening_ratio = 0.005
    plastic = ea - eps_y
    stress_abs = float(mat.fpy_mpa) + hardening_ratio * ep * plastic
    stress_abs = min(stress_abs, float(mat.fpu_mpa))

    if ea >= float(mat.eps_pu):
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * stress_abs,
            tangent_mpa=0.0,
            state_tag="cable_fracture",
        )

    state_tag = "cable_hardening" if stress_abs < float(mat.fpu_mpa) else "cable_peak"
    tangent = hardening_ratio * ep if stress_abs < float(mat.fpu_mpa) else 0.0
    return MaterialSnapshot(strain=e, stress_mpa=sign * stress_abs, tangent_mpa=tangent, state_tag=state_tag)


# =============================================================================
# FRP (Fiber Reinforced Polymer)
# =============================================================================

@dataclass(frozen=True)
class FRPMaterial:
    """FRP material (GFRP, CFRP, AFRP, BFRP)."""
    ffu_mpa: float = 2400.0  # ultimate strength
    ffe_mpa: float = 1500.0  # design strength (environmental reduction applied)
    ef_mpa: float = 165000.0
    eps_fu: float = 0.015
    fiber_type: str = "CFRP"  # GFRP, CFRP, AFRP, BFRP
    fiber_orientation: str = "uni"  # uni, bi, quad, random
    environmental_reduction: float = 0.85  # for concrete exposure
    fire_resistance_min: float = 30.0  # minutes
    creep_rupture_limit: float = 0.55  # 55% of ffu for sustained load

    @property
    def eps_fe(self) -> float:
        return float(self.ffe_mpa) / max(float(self.ef_mpa), 1e-9)


def frp_response(strain: float, mat: FRPMaterial | None = None) -> "MaterialSnapshot":
    """Linear-elastic brittle FRP response with creep rupture cap."""
    if mat is None:
        mat = FRPMaterial()
    e = float(strain)
    ef = float(mat.ef_mpa)
    ea = abs(e)
    sign = 1.0 if e >= 0.0 else -1.0

    stress_abs = ef * ea
    # Environmental reduction
    stress_abs *= float(mat.environmental_reduction)

    # Creep rupture limit for sustained
    creep_limit = float(mat.ffe_mpa) * float(mat.creep_rupture_limit)
    if stress_abs > creep_limit:
        state_tag = "frp_creep_rupture_zone"
    else:
        state_tag = "frp_elastic"

    if ea >= float(mat.eps_fu):
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * min(stress_abs, float(mat.ffu_mpa)),
            tangent_mpa=0.0,
            state_tag="frp_rupture",
        )

    return MaterialSnapshot(
        strain=e,
        stress_mpa=sign * min(stress_abs, float(mat.ffu_mpa)),
        tangent_mpa=ef * float(mat.environmental_reduction),
        state_tag=state_tag,
    )


# =============================================================================
# Geotechnical / Foundation
# =============================================================================

@dataclass(frozen=True)
class SoilMaterial:
    """Soil material for foundation analysis (Mohr-Coulomb)."""
    cohesion_kpa: float = 25.0
    friction_angle_deg: float = 30.0
    unit_weight_kn_m3: float = 18.0
    elastic_modulus_mpa: float = 30.0
    poisson_ratio: float = 0.30
    dilation_angle_deg: float = 5.0
    soil_type: str = "clay"  # clay, sand, silt, rock, gravel
    ocr: float = 1.0  # over-consolidation ratio
    permeability_m_s: float = 1.0e-7

    @property
    def friction_angle_rad(self) -> float:
        return math.radians(float(self.friction_angle_deg))


@dataclass(frozen=True)
class RockMaterial:
    """Rock mass material (Hoek-Brown)."""
    intact_ucs_mpa: float = 50.0
    gsi: float = 60.0  # Geological Strength Index
    mi: float = 15.0  # material constant
    disturbance_d: float = 0.0
    elastic_modulus_mpa: float = 5000.0
    poisson_ratio: float = 0.25


def soil_mohr_coulomb_response(
    strain: float,
    confining_pressure_kpa: float = 0.0,
    mat: SoilMaterial | None = None,
) -> "MaterialSnapshot":
    """Reduced-order Mohr-Coulomb soil response."""
    if mat is None:
        mat = SoilMaterial()
    e = float(strain)
    ea = abs(e)
    sign = 1.0 if e >= 0.0 else -1.0
    es = float(mat.elastic_modulus_mpa)

    # Elastic
    if ea < 0.001:
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * es * ea,
            tangent_mpa=es,
            state_tag="soil_elastic",
        )

    phi = mat.friction_angle_rad
    cohesion = float(mat.cohesion_kpa) / 1000.0  # MPa
    confining = float(confining_pressure_kpa) / 1000.0
    shear_strength = cohesion + confining * math.tan(phi)

    # Plastic softening
    plastic_strain = max(0.0, ea - 0.001)
    residual = shear_strength * 0.70
    softening_ratio = _clamp(plastic_strain / 0.010, 0.0, 1.0)
    stress_abs = shear_strength - softening_ratio * (shear_strength - residual)
    tangent = -0.30 * es if softening_ratio < 1.0 else 0.0

    return MaterialSnapshot(
        strain=e,
        stress_mpa=sign * stress_abs,
        tangent_mpa=tangent,
        state_tag="soil_plastic" if softening_ratio < 1.0 else "soil_residual",
    )


def rock_hoek_brown_response(
    strain: float,
    confining_pressure_mpa: float = 0.0,
    mat: RockMaterial | None = None,
) -> "MaterialSnapshot":
    """Simplified Hoek-Brown rock mass response."""
    if mat is None:
        mat = RockMaterial()
    e = float(strain)
    ea = abs(e)
    sign = 1.0 if e >= 0.0 else -1.0
    es = float(mat.elastic_modulus_mpa)

    if ea < 0.0005:
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * es * ea,
            tangent_mpa=es,
            state_tag="rock_elastic",
        )

    # Hoek-Brown failure envelope
    ci = float(mat.intact_ucs_mpa)
    gsi = float(mat.gsi)
    mi = float(mat.mi)
    d = float(mat.disturbance_d)
    mb = mi * math.exp((gsi - 100.0) / 28.0 - 8.0 * d / 3.0)
    s = math.exp((gsi - 100.0) / 9.0 - 2.0 * d / 3.0)
    a = 0.5 + math.exp(-gsi / 15.0) / 6.0

    sig3 = max(float(confining_pressure_mpa), 0.0)
    sig1 = sig3 + ci * (mb * sig3 / ci + s) ** a
    strength = sig1 - sig3

    plastic_strain = max(0.0, ea - 0.0005)
    residual = strength * 0.60
    softening_ratio = _clamp(plastic_strain / 0.005, 0.0, 1.0)
    stress_abs = strength - softening_ratio * (strength - residual)

    return MaterialSnapshot(
        strain=e,
        stress_mpa=sign * stress_abs,
        tangent_mpa=0.0 if softening_ratio >= 1.0 else -0.40 * es,
        state_tag="rock_damaged" if softening_ratio < 1.0 else "rock_residual",
    )


# =============================================================================
# Timber
# =============================================================================

@dataclass(frozen=True)
class TimberMaterial:
    """Timber/gluam/CLT/LVL material with orthotropic behavior."""
    fc_0_mpa: float = 24.0  # compression parallel
    ft_0_mpa: float = 18.0  # tension parallel
    fc_90_mpa: float = 4.0  # compression perpendicular
    ft_90_mpa: float = 0.5  # tension perpendicular
    fv_mpa: float = 3.5  # shear
    e_0_mpa: float = 12000.0
    e_90_mpa: float = 400.0
    g_mpa: float = 750.0
    density_kg_m3: float = 450.0
    moisture_content: float = 12.0  # %
    timber_type: str = "glulam"  # glulam, clt, lvl, solid_sawn
    grade: str = "GL24h"
    fire_retardant: bool = False
    preservative_treatment: str = "none"  # none, CCA, ACQ, boron
    duration_of_load_factor: float = 0.80  # for medium-term


def timber_response(strain: float, direction: str = "parallel", mat: TimberMaterial | None = None) -> "MaterialSnapshot":
    """Orthotropic timber response."""
    if mat is None:
        mat = TimberMaterial()
    e = float(strain)
    sign = 1.0 if e >= 0.0 else -1.0
    ea = abs(e)

    if direction == "perpendicular":
        ec = float(mat.e_90_mpa)
        fc = float(mat.fc_90_mpa)
        ft = float(mat.ft_90_mpa)
    else:
        ec = float(mat.e_0_mpa)
        fc = float(mat.fc_0_mpa)
        ft = float(mat.ft_0_mpa)

    # Parallel behavior
    if e >= 0.0:
        # Tension
        eps_t = ft / max(ec, 1e-9)
        if ea <= eps_t:
            return MaterialSnapshot(strain=e, stress_mpa=ec * ea, tangent_mpa=ec, state_tag="timber_tension_elastic")
        return MaterialSnapshot(strain=e, stress_mpa=ft, tangent_mpa=0.0, state_tag="timber_tension_rupture")
    else:
        # Compression with plastic plateau and softening
        eps_c = fc / max(ec, 1e-9)
        if ea <= eps_c:
            return MaterialSnapshot(strain=e, stress_mpa=sign * ec * ea, tangent_mpa=ec, state_tag="timber_compression_elastic")
        plastic = ea - eps_c
        residual = fc * 0.50
        softening = _clamp(plastic / 0.010, 0.0, 1.0)
        stress_abs = fc - softening * (fc - residual)
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * stress_abs,
            tangent_mpa=0.0 if softening >= 1.0 else -0.30 * ec,
            state_tag="timber_compression_crushing" if softening < 1.0 else "timber_compression_residual",
        )


# =============================================================================
# Fasteners: Bolts, Anchors, Welds
# =============================================================================

@dataclass(frozen=True)
class BoltMaterial:
    """High-strength structural bolt (e.g., F10T, S10T)."""
    fyb_mpa: float = 900.0
    fub_mpa: float = 1000.0
    grade: str = "F10T"
    nominal_diameter_mm: float = 22.0
    hole_diameter_mm: float = 24.0
    friction_surface_class: str = "A"  # A, B, C for slip-critical
    slip_coefficient: float = 0.40
    preload_ratio: float = 0.70  # of fub


@dataclass(frozen=True)
class AnchorMaterial:
    """Post-installed or cast-in anchor."""
    fut_mpa: float = 800.0
    nominal_diameter_mm: float = 16.0
    embedment_depth_mm: float = 120.0
    anchor_type: str = "wedge"  # wedge, undercut, adhesive, expansion, cast_in
    concrete_grade_mpa: float = 27.0
    edge_distance_mm: float = 100.0
    spacing_mm: float = 150.0


@dataclass(frozen=True)
class WeldMaterial:
    """Weld metal material."""
    fyw_mpa: float = 400.0
    fuw_mpa: float = 490.0
    electrode_grade: str = "E490"
    throat_thickness_mm: float = 6.0
    weld_type: str = "fillet"  # fillet, butt, plug, slot


def bolt_slip_resistance(bolt: BoltMaterial | None = None) -> float:
    """Calculate slip resistance per bolt (kN)."""
    if bolt is None:
        bolt = BoltMaterial()
    preload = float(bolt.preload_ratio) * float(bolt.fub_mpa) * math.pi * (float(bolt.nominal_diameter_mm) / 2.0) ** 2 / 1000.0
    resistance = float(bolt.slip_coefficient) * preload / 1.25  # safety factor
    return resistance


def anchor_tension_capacity(anchor: AnchorMaterial | None = None) -> float:
    """Calculate anchor tension capacity (kN) per CCD method approximation."""
    if anchor is None:
        anchor = AnchorMaterial()
    area = math.pi * (float(anchor.nominal_diameter_mm) / 2.0) ** 2
    steel_capacity = float(anchor.fut_mpa) * area / 1000.0
    # Concrete cone breakout (simplified CCD)
    hef = float(anchor.embedment_depth_mm)
    kc = 10.0 if anchor.anchor_type in ("wedge", "undercut") else 7.0
    cone_capacity = kc * math.sqrt(float(anchor.concrete_grade_mpa)) * (hef / 10.0) ** 1.5
    return min(steel_capacity, cone_capacity)


def weld_shear_capacity(weld: WeldMaterial | None = None) -> float:
    """Calculate weld shear capacity per mm length (kN/mm)."""
    if weld is None:
        weld = WeldMaterial()
    throat = float(weld.throat_thickness_mm)
    # Korean KDS design: fw = 0.6 * fuw / 1.25
    fw = 0.6 * float(weld.fuw_mpa) / 1.25 / 1000.0
    return fw * throat


# =============================================================================
# Dampers and Seismic Isolators
# =============================================================================

@dataclass(frozen=True)
class ViscousDamper:
    """Fluid viscous damper."""
    cd_kn_s_m: float = 500.0  # damping coefficient
    velocity_exponent: float = 0.35  # 0.3~0.5 typical
    max_force_kn: float = 2000.0
    stroke_mm: float = 200.0
    temperature_range_c: Tuple[float, float] = (-20.0, 60.0)


def viscous_damper_force(velocity_m_s: float, damper: ViscousDamper | None = None) -> float:
    """Calculate damper force (kN) given velocity (m/s)."""
    if damper is None:
        damper = ViscousDamper()
    v = abs(float(velocity_m_s))
    alpha = float(damper.velocity_exponent)
    force = float(damper.cd_kn_s_m) * (v ** alpha)
    return math.copysign(min(force, float(damper.max_force_kn)), float(velocity_m_s))


@dataclass(frozen=True)
class LeadRubberBearing:
    """Lead-rubber seismic isolator (LRB)."""
    characteristic_strength_kn: float = 150.0
    post_yield_stiffness_kn_m: float = 8000.0
    yield_displacement_mm: float = 10.0
    max_displacement_mm: float = 300.0
    vertical_capacity_kn: float = 5000.0
    rubber_layers: int = 20
    rubber_thickness_mm: float = 3.0
    lead_core_diameter_mm: float = 50.0


def lrb_response(displacement_mm: float, bearing: LeadRubberBearing | None = None) -> "MaterialSnapshot":
    """Bilinear LRB response."""
    if bearing is None:
        bearing = LeadRubberBearing()
    d = float(displacement_mm)
    sign = 1.0 if d >= 0.0 else -1.0
    dy = float(bearing.yield_displacement_mm)
    q = float(bearing.characteristic_strength_kn)
    kr = float(bearing.post_yield_stiffness_kn_m)

    if abs(d) <= dy:
        k0 = (q / dy) + kr
        force = k0 * d
        return MaterialSnapshot(
            strain=d,
            stress_mpa=force,
            tangent_mpa=k0,
            state_tag="lrb_elastic",
        )

    force = sign * q + kr * d
    return MaterialSnapshot(
        strain=d,
        stress_mpa=force,
        tangent_mpa=kr,
        state_tag="lrb_yielded",
    )


@dataclass(frozen=True)
class FrictionPendulumBearing:
    """Friction pendulum system (FPS) isolator."""
    friction_coeff: float = 0.06
    radius_m: float = 2.0
    max_displacement_mm: float = 400.0
    vertical_capacity_kn: float = 8000.0
    self_centering: bool = True


def fps_response(displacement_mm: float, bearing: FrictionPendulumBearing | None = None) -> "MaterialSnapshot":
    """FPS restoring force."""
    if bearing is None:
        bearing = FrictionPendulumBearing()
    d = float(displacement_mm)
    r = float(bearing.radius_m)
    mu = float(bearing.friction_coeff)
    w = float(bearing.vertical_capacity_kn)

    restoring = (w / max(r, 1e-9)) * (d / 1000.0)  # kN
    friction = mu * w * math.copysign(1.0, d)
    force = restoring + friction

    return MaterialSnapshot(
        strain=d,
        stress_mpa=force,
        tangent_mpa=w / max(r, 1e-9),
        state_tag="fps_restoring",
    )


# =============================================================================
# Masonry and Cold-Formed Steel
# =============================================================================

@dataclass(frozen=True)
class MasonryMaterial:
    """Reinforced/unreinforced masonry."""
    fm_mpa: float = 12.0  # masonry compressive strength
    ft_mpa: float = 0.30
    grout_strength_mpa: float = 18.0
    rebar_grade: str = "SD400"
    unit_weight_kn_m3: float = 18.0
    wall_thickness_mm: float = 190.0
    reinforcement_ratio: float = 0.002


def masonry_compression_response(strain: float, mat: MasonryMaterial | None = None) -> "MaterialSnapshot":
    """Parabolic masonry compression response."""
    if mat is None:
        mat = MasonryMaterial()
    e = float(strain)
    ea = abs(e)
    sign = 1.0 if e >= 0.0 else -1.0
    fm = float(mat.fm_mpa)
    eps_m = 0.003

    if ea <= eps_m:
        x = ea / eps_m
        stress = fm * (2.0 * x - x * x)
        tangent = fm * (2.0 - 2.0 * x) / eps_m
        return MaterialSnapshot(strain=e, stress_mpa=sign * stress, tangent_mpa=tangent, state_tag="masonry_compression")

    residual = fm * 0.20
    return MaterialSnapshot(strain=e, stress_mpa=sign * residual, tangent_mpa=0.0, state_tag="masonry_crushed")


@dataclass(frozen=True)
class ColdFormedSteel:
    """Cold-formed steel section material."""
    fy_mpa: float = 345.0
    fu_mpa: float = 450.0
    e_mpa: float = 203000.0
    local_buckling_strain: float = 0.008
    distortional_buckling_strain: float = 0.012
    section_thickness_mm: float = 1.5
    section_depth_mm: float = 150.0


def cold_formed_steel_response(strain: float, mat: ColdFormedSteel | None = None) -> "MaterialSnapshot":
    """Cold-formed steel with local/distortional buckling."""
    if mat is None:
        mat = ColdFormedSteel()
    e = float(strain)
    sign = 1.0 if e >= 0.0 else -1.0
    ea = abs(e)
    es = float(mat.e_mpa)
    ey = float(mat.fy_mpa) / max(es, 1e-9)

    if ea <= ey:
        return MaterialSnapshot(strain=e, stress_mpa=sign * es * ea, tangent_mpa=es, state_tag="cfs_elastic")

    hardening = 0.012
    plastic = ea - ey
    stress_abs = float(mat.fy_mpa) + hardening * es * plastic

    # Local buckling degradation
    if ea > float(mat.local_buckling_strain):
        degradation = _clamp((ea - float(mat.local_buckling_strain)) / 0.010, 0.0, 0.60)
        stress_abs *= (1.0 - degradation)

    # Distortional buckling
    if ea > float(mat.distortional_buckling_strain):
        degradation = _clamp((ea - float(mat.distortional_buckling_strain)) / 0.008, 0.0, 0.40)
        stress_abs *= (1.0 - degradation)

    stress_abs = max(stress_abs, float(mat.fy_mpa) * 0.20)
    return MaterialSnapshot(strain=e, stress_mpa=sign * stress_abs, tangent_mpa=hardening * es, state_tag="cfs_hardening")


# =============================================================================
# Durability / Corrosion / Fire
# =============================================================================

@dataclass(frozen=True)
class CorrosionModel:
    """Steel reinforcement corrosion model."""
    corrosion_rate_mm_year: float = 0.05
    concrete_cover_mm: float = 40.0
    chloride_threshold_percent: float = 0.40
    current_chloride_percent: float = 0.10
    carbonation_depth_mm: float = 5.0
    time_years: float = 10.0

    @property
    def remaining_cover_mm(self) -> float:
        return max(0.0, float(self.concrete_cover_mm) - float(self.corrosion_rate_mm_year) * float(self.time_years))

    @property
    def corrosion_initiated(self) -> bool:
        return self.remaining_cover_mm <= 0.0 or float(self.current_chloride_percent) >= float(self.chloride_threshold_percent)

    @property
    def diameter_loss_percent(self) -> float:
        if not self.corrosion_initiated:
            return 0.0
        active_years = max(0.0, float(self.time_years) - float(self.concrete_cover_mm) / max(float(self.corrosion_rate_mm_year), 1e-9))
        loss = float(self.corrosion_rate_mm_year) * active_years * 2.0  # diameter loss
        return _clamp(loss, 0.0, 50.0)


@dataclass(frozen=True)
class FireModel:
    """Material degradation under fire exposure."""
    fire_duration_min: float = 60.0
    iso_fire_curve: bool = True
    steel_temperature_c: float = 0.0
    concrete_temperature_c: float = 0.0
    timber_char_rate_mm_min: float = 0.65

    @property
    def steel_reduction_factor(self) -> float:
        """EC3 steel strength reduction at elevated temperature."""
        t = float(self.steel_temperature_c)
        if t <= 400.0:
            return 1.0
        if t <= 500.0:
            return 1.0 - (t - 400.0) * 0.0022
        if t <= 600.0:
            return 0.78 - (t - 500.0) * 0.0025
        if t <= 700.0:
            return 0.53 - (t - 600.0) * 0.0023
        if t <= 800.0:
            return 0.30 - (t - 700.0) * 0.0016
        return max(0.0, 0.14 - (t - 800.0) * 0.0007)

    @property
    def concrete_reduction_factor(self) -> float:
        """EC2 concrete strength reduction at elevated temperature."""
        t = float(self.concrete_temperature_c)
        if t <= 100.0:
            return 1.0
        if t <= 400.0:
            return 1.0 - (t - 100.0) * 0.0013
        if t <= 600.0:
            return 0.61 - (t - 400.0) * 0.0012
        if t <= 800.0:
            return 0.37 - (t - 600.0) * 0.0010
        if t <= 1000.0:
            return 0.17 - (t - 800.0) * 0.0007
        return 0.03

    @property
    def timber_char_depth_mm(self) -> float:
        return float(self.timber_char_rate_mm_min) * float(self.fire_duration_min)


@dataclass(frozen=True)
class FatigueModel:
    """S-N fatigue model for steel details."""
    detail_category_mpa: float = 90.0  # fatigue detail category
    stress_range_mpa: float = 50.0
    cycles_to_failure: float = 2.0e6
    cumulative_damage: float = 0.0
    slope_m: float = 3.0  # S-N curve slope

    def remaining_life_cycles(self, stress_range_mpa: float | None = None) -> float:
        """Calculate remaining fatigue life in cycles."""
        sr = float(stress_range_mpa) if stress_range_mpa is not None else float(self.stress_range_mpa)
        delta_sigma = float(self.detail_category_mpa)
        m = float(self.slope_m)
        if sr <= 0.0:
            return float("inf")
        n = (delta_sigma / sr) ** m * float(self.cycles_to_failure)
        remaining = n * (1.0 - float(self.cumulative_damage))
        return max(0.0, remaining)


# =============================================================================
# Shared snapshot class (mirrors existing libraries)
# =============================================================================

@dataclass(frozen=True)
class MaterialSnapshot:
    strain: float
    stress_mpa: float
    tangent_mpa: float
    state_tag: str


# =============================================================================
# Master material registry for viewer integration
# =============================================================================

MATERIAL_FAMILY_REGISTRY = {
    "concrete": {"module": "rc_constitutive_library", "class": "ConcreteMaterial"},
    "steel": {"module": "steel_constitutive_library", "class": "SteelMaterial"},
    "composite": {"module": "composite_constitutive_library", "class": "CompositeActionMaterial"},
    "prestressing": {"module": "extended_material_library", "class": "PrestressingSteel"},
    "cable": {"module": "extended_material_library", "class": "CableMaterial"},
    "frp": {"module": "extended_material_library", "class": "FRPMaterial"},
    "soil": {"module": "extended_material_library", "class": "SoilMaterial"},
    "rock": {"module": "extended_material_library", "class": "RockMaterial"},
    "timber": {"module": "extended_material_library", "class": "TimberMaterial"},
    "bolt": {"module": "extended_material_library", "class": "BoltMaterial"},
    "anchor": {"module": "extended_material_library", "class": "AnchorMaterial"},
    "weld": {"module": "extended_material_library", "class": "WeldMaterial"},
    "viscous_damper": {"module": "extended_material_library", "class": "ViscousDamper"},
    "lrb": {"module": "extended_material_library", "class": "LeadRubberBearing"},
    "fps": {"module": "extended_material_library", "class": "FrictionPendulumBearing"},
    "masonry": {"module": "extended_material_library", "class": "MasonryMaterial"},
    "cold_formed_steel": {"module": "extended_material_library", "class": "ColdFormedSteel"},
}


def get_material_families() -> dict:
    """Return the complete material family registry."""
    return dict(MATERIAL_FAMILY_REGISTRY)


__all__ = [
    # Prestressing
    "PrestressingSteel",
    "PrestressingDuct",
    "PrestressedConcreteSection",
    "prestressing_steel_response",
    "prestress_loss_ratio",
    # Cables
    "CableMaterial",
    "cable_response",
    # FRP
    "FRPMaterial",
    "frp_response",
    # Geotechnical
    "SoilMaterial",
    "RockMaterial",
    "soil_mohr_coulomb_response",
    "rock_hoek_brown_response",
    # Timber
    "TimberMaterial",
    "timber_response",
    # Fasteners
    "BoltMaterial",
    "AnchorMaterial",
    "WeldMaterial",
    "bolt_slip_resistance",
    "anchor_tension_capacity",
    "weld_shear_capacity",
    # Dampers/Isolators
    "ViscousDamper",
    "LeadRubberBearing",
    "FrictionPendulumBearing",
    "viscous_damper_force",
    "lrb_response",
    "fps_response",
    # Masonry/CFS
    "MasonryMaterial",
    "masonry_compression_response",
    "ColdFormedSteel",
    "cold_formed_steel_response",
    # Durability
    "CorrosionModel",
    "FireModel",
    "FatigueModel",
    # Shared
    "MaterialSnapshot",
    "MATERIAL_FAMILY_REGISTRY",
    "get_material_families",
]
