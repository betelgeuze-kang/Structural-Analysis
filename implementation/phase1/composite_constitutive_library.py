#!/usr/bin/env python3
"""Dedicated reduced-order steel-concrete composite constitutive helpers with SRC/CFT/beam models."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

try:
    from implementation.phase1.bond_slip_interface import BondSlipMaterial, bond_slip_interaction_response
    from implementation.phase1.rc_constitutive_library import ConcreteMaterial, concrete_response
    from implementation.phase1.steel_constitutive_library import MaterialSnapshot, SteelMaterial, steel_response
except ImportError:  # pragma: no cover - script execution fallback
    from bond_slip_interface import BondSlipMaterial, bond_slip_interaction_response
    from rc_constitutive_library import ConcreteMaterial, concrete_response
    from steel_constitutive_library import MaterialSnapshot, SteelMaterial, steel_response


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass(frozen=True)
class CompositeActionMaterial:
    steel: SteelMaterial = field(default_factory=SteelMaterial)
    concrete: ConcreteMaterial = field(default_factory=ConcreteMaterial)
    connector_slip_y_strain: float = 8.0e-4
    connector_slip_u_strain: float = 4.0e-3
    residual_action_ratio: float = 0.25
    concrete_tension_carry_ratio: float = 0.15

    def bond_slip_material(self) -> BondSlipMaterial:
        return BondSlipMaterial(
            residual_ratio=float(self.residual_action_ratio),
            interaction_y=float(self.connector_slip_y_strain),
            interaction_u=float(self.connector_slip_u_strain),
        )


@dataclass(frozen=True)
class SRCSection:
    """Steel Reinforced Concrete section."""
    steel_area_m2: float = 0.02
    concrete_area_m2: float = 0.20
    steel_ratio: float = 0.05
    confinement_ratio: float = 1.20
    steel: SteelMaterial = field(default_factory=SteelMaterial)
    concrete: ConcreteMaterial = field(default_factory=ConcreteMaterial)


@dataclass(frozen=True)
class CFTSection:
    """Concrete Filled Tube section."""
    tube_area_m2: float = 0.01
    concrete_area_m2: float = 0.10
    tube_thickness_m: float = 0.012
    tube_diameter_m: float = 0.40
    confinement_ratio: float = 1.50
    steel: SteelMaterial = field(default_factory=SteelMaterial)
    concrete: ConcreteMaterial = field(default_factory=ConcreteMaterial)


@dataclass(frozen=True)
class CompositeBeamSection:
    """Composite beam with shear connectors."""
    steel_section_area_m2: float = 0.015
    concrete_slab_area_m2: float = 0.15
    slab_width_m: float = 1.50
    slab_thickness_m: float = 0.12
    connector_spacing_m: float = 0.30
    connector_capacity_kn: float = 100.0
    steel: SteelMaterial = field(default_factory=SteelMaterial)
    concrete: ConcreteMaterial = field(default_factory=ConcreteMaterial)


@dataclass(frozen=True)
class ShearConnector:
    """Shear connector for composite action."""
    diameter_m: float = 0.019
    length_m: float = 0.100
    fu_mpa: float = 450.0
    connector_type: str = "headed_stud"
    capacity_kn: float = 100.0
    stiffness_kn_per_mm: float = 200.0


@dataclass(frozen=True)
class CompositeSectionResponse:
    """Response of composite section."""
    axial_capacity_n: float
    moment_capacity_nm: float
    shear_capacity_n: float
    composite_action_ratio: float
    steel_stress_mpa: float
    concrete_stress_mpa: float
    neutral_axis_depth_m: float
    state_tag: str


@dataclass(frozen=True)
class CompositeActionSnapshot:
    steel: MaterialSnapshot
    concrete: object
    slip_strain: float
    action_ratio: float
    stress_mpa: float
    tangent_mpa: float
    connector_state_tag: str
    state_tag: str


def composite_action_response(
    *,
    steel_strain: float,
    concrete_strain: float,
    slip_strain: float,
    mat: CompositeActionMaterial | None = None,
) -> CompositeActionSnapshot:
    if mat is None:
        mat = CompositeActionMaterial()

    steel_snap = steel_response(float(steel_strain), mat.steel)
    concrete_snap = concrete_response(float(concrete_strain), mat.concrete)
    bond_slip = bond_slip_interaction_response(
        float(slip_strain),
        mat.bond_slip_material(),
        interaction_y=float(mat.connector_slip_y_strain),
        interaction_u=float(mat.connector_slip_u_strain),
        residual_ratio=float(mat.residual_action_ratio),
    )
    concrete_stress = float(concrete_snap.stress_mpa)
    concrete_tangent = float(concrete_snap.tangent_mpa)
    if concrete_stress > 0.0:
        tension_ratio = _clamp(mat.concrete_tension_carry_ratio, 0.0, 1.0)
        concrete_stress *= tension_ratio
        concrete_tangent *= tension_ratio
    stress_mpa = float(steel_snap.stress_mpa) + float(bond_slip.interaction_ratio) * concrete_stress
    tangent_mpa = float(steel_snap.tangent_mpa) + float(bond_slip.interaction_ratio) * concrete_tangent
    dominant_state = (
        steel_snap.state_tag
        if abs(float(steel_snap.stress_mpa)) >= abs(float(bond_slip.interaction_ratio) * concrete_stress)
        else concrete_snap.state_tag
    )
    return CompositeActionSnapshot(
        steel=steel_snap,
        concrete=concrete_snap,
        slip_strain=float(slip_strain),
        action_ratio=float(bond_slip.interaction_ratio),
        stress_mpa=float(stress_mpa),
        tangent_mpa=float(tangent_mpa),
        connector_state_tag=str(bond_slip.state_tag),
        state_tag=f"{bond_slip.state_tag}+{dominant_state}",
    )


def src_section_capacity(section: SRCSection) -> CompositeSectionResponse:
    """Calculate SRC section capacity with confinement effect."""
    steel_capacity = float(section.steel.fy_mpa) * float(section.steel_area_m2) * 1.0e6
    confined_fc = float(section.concrete.fc_mpa) * float(section.confinement_ratio)
    concrete_capacity = confined_fc * float(section.concrete_area_m2) * 1.0e6
    axial_capacity = steel_capacity + concrete_capacity
    
    steel_moment = steel_capacity * 0.5 * math.sqrt(max(float(section.steel_area_m2), 1e-9))
    concrete_moment = concrete_capacity * 0.4 * math.sqrt(max(float(section.concrete_area_m2), 1e-9))
    moment_capacity = steel_moment + concrete_moment
    
    shear_capacity = 0.6 * float(section.steel.fy_mpa) * float(section.steel_area_m2) * 1.0e6
    
    composite_ratio = _clamp(float(section.steel_ratio) * float(section.confinement_ratio), 0.0, 1.0)
    neutral_axis = 0.45 * math.sqrt(max(float(section.concrete_area_m2), 1e-9))
    
    return CompositeSectionResponse(
        axial_capacity_n=axial_capacity,
        moment_capacity_nm=moment_capacity,
        shear_capacity_n=shear_capacity,
        composite_action_ratio=composite_ratio,
        steel_stress_mpa=float(section.steel.fy_mpa),
        concrete_stress_mpa=confined_fc,
        neutral_axis_depth_m=neutral_axis,
        state_tag="src_section",
    )


def cft_section_capacity(section: CFTSection) -> CompositeSectionResponse:
    """Calculate CFT section capacity with confinement effect."""
    tube_capacity = float(section.steel.fy_mpa) * float(section.tube_area_m2) * 1.0e6
    confined_fc = float(section.concrete.fc_mpa) * float(section.confinement_ratio)
    concrete_capacity = confined_fc * float(section.concrete_area_m2) * 1.0e6
    axial_capacity = tube_capacity + concrete_capacity
    
    tube_moment = tube_capacity * 0.5 * float(section.tube_diameter_m) / 2.0
    concrete_moment = concrete_capacity * 0.4 * float(section.tube_diameter_m) / 2.0
    moment_capacity = tube_moment + concrete_moment
    
    shear_capacity = 0.6 * float(section.steel.fy_mpa) * float(section.tube_area_m2) * 1.0e6
    
    thickness_ratio = float(section.tube_thickness_m) / max(float(section.tube_diameter_m), 1e-9)
    composite_ratio = _clamp(float(section.confinement_ratio) * thickness_ratio * 10.0, 0.0, 1.0)
    neutral_axis = 0.45 * float(section.tube_diameter_m) / 2.0
    
    return CompositeSectionResponse(
        axial_capacity_n=axial_capacity,
        moment_capacity_nm=moment_capacity,
        shear_capacity_n=shear_capacity,
        composite_action_ratio=composite_ratio,
        steel_stress_mpa=float(section.steel.fy_mpa),
        concrete_stress_mpa=confined_fc,
        neutral_axis_depth_m=neutral_axis,
        state_tag="cft_section",
    )


def composite_beam_capacity(section: CompositeBeamSection) -> CompositeSectionResponse:
    """Calculate composite beam capacity with shear connector effect."""
    steel_capacity = float(section.steel.fy_mpa) * float(section.steel_section_area_m2) * 1.0e6
    concrete_capacity = float(section.concrete.fc_mpa) * float(section.concrete_slab_area_m2) * 1.0e6
    
    connector_count = float(section.slab_width_m) / max(float(section.connector_spacing_m), 0.01)
    total_connector_capacity = connector_count * float(section.connector_capacity_kn) * 1000.0
    
    effective_capacity = min(steel_capacity + concrete_capacity, total_connector_capacity)
    composite_ratio = _clamp(total_connector_capacity / max(steel_capacity + concrete_capacity, 1e-9), 0.0, 1.0)
    
    moment_capacity = effective_capacity * 0.5 * float(section.slab_thickness_m)
    shear_capacity = 0.6 * float(section.steel.fy_mpa) * float(section.steel_section_area_m2) * 1.0e6
    
    neutral_axis = 0.45 * float(section.slab_thickness_m)
    
    return CompositeSectionResponse(
        axial_capacity_n=effective_capacity,
        moment_capacity_nm=moment_capacity,
        shear_capacity_n=shear_capacity,
        composite_action_ratio=composite_ratio,
        steel_stress_mpa=float(section.steel.fy_mpa),
        concrete_stress_mpa=float(section.concrete.fc_mpa),
        neutral_axis_depth_m=neutral_axis,
        state_tag="composite_beam",
    )


def shear_connector_response(
    slip_mm: float,
    connector: ShearConnector | None = None,
) -> MaterialSnapshot:
    """Calculate shear connector force-slip response."""
    if connector is None:
        connector = ShearConnector()
    
    s = abs(float(slip_mm))
    sign = 1.0 if float(slip_mm) >= 0.0 else -1.0
    
    elastic_limit = float(connector.capacity_kn) / max(float(connector.stiffness_kn_per_mm), 1e-9)
    
    if s <= elastic_limit:
        return MaterialSnapshot(
            strain=slip_mm,
            stress_mpa=sign * float(connector.stiffness_kn_per_mm) * s,
            tangent_mpa=float(connector.stiffness_kn_per_mm),
            state_tag="connector_elastic",
        )
    
    residual = float(connector.capacity_kn) * 0.30
    if s <= 5.0 * elastic_limit:
        ratio = (s - elastic_limit) / max(4.0 * elastic_limit, 1e-9)
        force = float(connector.capacity_kn) + ratio * (residual - float(connector.capacity_kn))
        tangent = (residual - float(connector.capacity_kn)) / max(4.0 * elastic_limit, 1e-9)
        return MaterialSnapshot(
            strain=slip_mm,
            stress_mpa=sign * force,
            tangent_mpa=tangent,
            state_tag="connector_softening",
        )
    
    return MaterialSnapshot(
        strain=slip_mm,
        stress_mpa=sign * residual,
        tangent_mpa=0.0,
        state_tag="connector_residual",
    )


__all__ = [
    "CFTSection",
    "CompositeActionMaterial",
    "CompositeActionSnapshot",
    "CompositeBeamSection",
    "CompositeSectionResponse",
    "SRCSection",
    "ShearConnector",
    "cft_section_capacity",
    "composite_action_response",
    "composite_beam_capacity",
    "shear_connector_response",
    "src_section_capacity",
]
