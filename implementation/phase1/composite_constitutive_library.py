#!/usr/bin/env python3
"""Dedicated reduced-order steel-concrete composite constitutive helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

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


__all__ = [
    "CompositeActionMaterial",
    "CompositeActionSnapshot",
    "composite_action_response",
]
