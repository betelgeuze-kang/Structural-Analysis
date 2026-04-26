#!/usr/bin/env python3
"""Reduced-order KDS RC member rule checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RCMemberDemand:
    axial_kN: float = 0.0
    shear_kN: float = 0.0
    moment_kNm: float = 0.0
    drift_ratio_pct: float = 0.0
    punching_shear_kN: float = 0.0
    boundary_comp_kN: float = 0.0
    footing_bearing_kPa: float = 0.0
    footing_shear_kN: float = 0.0
    connection_shear_kN: float = 0.0
    connection_slip_mm: float = 0.0
    connection_rotation_mrad: float = 0.0


@dataclass(frozen=True)
class RCMemberCapacity:
    axial_kN: float = 1.0
    shear_kN: float = 1.0
    moment_kNm: float = 1.0
    drift_ratio_pct: float = 1.0
    punching_shear_kN: float = 1.0
    boundary_comp_kN: float = 1.0
    footing_bearing_kPa: float = 1.0
    footing_shear_kN: float = 1.0
    connection_shear_kN: float = 1.0
    connection_slip_mm: float = 1.0
    connection_rotation_mrad: float = 1.0


@dataclass(frozen=True)
class RCCheckResult:
    component: str
    clause: str
    demand: float
    capacity: float
    dcr: float


CLAUSE_MAP = {
    "beam:flexure": "KDS-RC-BEAM-FLEX-001",
    "beam:shear": "KDS-RC-BEAM-SHEAR-001",
    "column:axial_flexure": "KDS-RC-COL-INT-001",
    "column:shear": "KDS-RC-COL-SHEAR-001",
    "wall:axial_flexure": "KDS-RC-WALL-INT-001",
    "wall:shear": "KDS-RC-WALL-SHEAR-001",
    "wall:drift": "KDS-RC-WALL-DRIFT-001",
    "wall:boundary": "KDS-RC-WALL-BE-001",
    "slab:flexure": "KDS-RC-SLAB-FLEX-001",
    "slab:punching": "KDS-RC-SLAB-PUNCH-001",
    "foundation:bearing": "KDS-RC-FOUND-BEAR-001",
    "foundation:shear": "KDS-RC-FOUND-SHEAR-001",
    "connection:shear_friction": "KDS-RC-CONN-SHEAR-001",
    "connection:slip": "KDS-RC-CONN-SLIP-001",
    "connection:rotation": "KDS-RC-CONN-ROT-001",
}


def _dcr(demand: float, capacity: float) -> float:
    return abs(float(demand)) / max(abs(float(capacity)), 1e-9)


def evaluate_rc_member(
    *,
    member_type: str,
    demand: RCMemberDemand,
    capacity: RCMemberCapacity,
) -> list[RCCheckResult]:
    t = str(member_type).strip().lower()
    if t == "beam":
        return [
            RCCheckResult("flexure", CLAUSE_MAP["beam:flexure"], demand.moment_kNm, capacity.moment_kNm, _dcr(demand.moment_kNm, capacity.moment_kNm)),
            RCCheckResult("shear", CLAUSE_MAP["beam:shear"], demand.shear_kN, capacity.shear_kN, _dcr(demand.shear_kN, capacity.shear_kN)),
        ]
    if t == "column":
        interaction = 0.45 * _dcr(demand.axial_kN, capacity.axial_kN) + 0.55 * _dcr(demand.moment_kNm, capacity.moment_kNm)
        return [
            RCCheckResult("axial_flexure", CLAUSE_MAP["column:axial_flexure"], interaction, 1.0, interaction),
            RCCheckResult("shear", CLAUSE_MAP["column:shear"], demand.shear_kN, capacity.shear_kN, _dcr(demand.shear_kN, capacity.shear_kN)),
        ]
    if t == "wall":
        interaction = 0.35 * _dcr(demand.axial_kN, capacity.axial_kN) + 0.65 * _dcr(demand.moment_kNm, capacity.moment_kNm)
        return [
            RCCheckResult("axial_flexure", CLAUSE_MAP["wall:axial_flexure"], interaction, 1.0, interaction),
            RCCheckResult("shear", CLAUSE_MAP["wall:shear"], demand.shear_kN, capacity.shear_kN, _dcr(demand.shear_kN, capacity.shear_kN)),
            RCCheckResult("drift", CLAUSE_MAP["wall:drift"], demand.drift_ratio_pct, capacity.drift_ratio_pct, _dcr(demand.drift_ratio_pct, capacity.drift_ratio_pct)),
            RCCheckResult("boundary_element", CLAUSE_MAP["wall:boundary"], demand.boundary_comp_kN, capacity.boundary_comp_kN, _dcr(demand.boundary_comp_kN, capacity.boundary_comp_kN)),
        ]
    if t == "slab":
        return [
            RCCheckResult("flexure", CLAUSE_MAP["slab:flexure"], demand.moment_kNm, capacity.moment_kNm, _dcr(demand.moment_kNm, capacity.moment_kNm)),
            RCCheckResult("punching", CLAUSE_MAP["slab:punching"], demand.punching_shear_kN, capacity.punching_shear_kN, _dcr(demand.punching_shear_kN, capacity.punching_shear_kN)),
        ]
    if t == "foundation":
        return [
            RCCheckResult("bearing", CLAUSE_MAP["foundation:bearing"], demand.footing_bearing_kPa, capacity.footing_bearing_kPa, _dcr(demand.footing_bearing_kPa, capacity.footing_bearing_kPa)),
            RCCheckResult("shear", CLAUSE_MAP["foundation:shear"], demand.footing_shear_kN, capacity.footing_shear_kN, _dcr(demand.footing_shear_kN, capacity.footing_shear_kN)),
        ]
    if t == "connection":
        return [
            RCCheckResult("shear_friction", CLAUSE_MAP["connection:shear_friction"], demand.connection_shear_kN, capacity.connection_shear_kN, _dcr(demand.connection_shear_kN, capacity.connection_shear_kN)),
            RCCheckResult("slip", CLAUSE_MAP["connection:slip"], demand.connection_slip_mm, capacity.connection_slip_mm, _dcr(demand.connection_slip_mm, capacity.connection_slip_mm)),
            RCCheckResult("rotation", CLAUSE_MAP["connection:rotation"], demand.connection_rotation_mrad, capacity.connection_rotation_mrad, _dcr(demand.connection_rotation_mrad, capacity.connection_rotation_mrad)),
        ]
    raise ValueError(f"unsupported member type: {member_type}")


def governing_result(results: list[RCCheckResult]) -> RCCheckResult:
    if not results:
        raise ValueError("empty rc check result set")
    return max(results, key=lambda item: float(item.dcr))


__all__ = [
    "RCCheckResult",
    "RCMemberCapacity",
    "RCMemberDemand",
    "evaluate_rc_member",
    "governing_result",
]
