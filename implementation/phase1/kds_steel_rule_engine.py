#!/usr/bin/env python3
"""Reduced-order KDS steel member rule checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SteelMemberDemand:
    axial_kN: float = 0.0
    shear_kN: float = 0.0
    moment_kNm: float = 0.0
    buckling_factor: float = 1.0
    panel_zone_shear_kN: float = 0.0
    connection_shear_kN: float = 0.0
    connection_rotation_mrad: float = 0.0


@dataclass(frozen=True)
class SteelMemberCapacity:
    axial_kN: float = 1.0
    shear_kN: float = 1.0
    moment_kNm: float = 1.0
    buckling_factor_min: float = 1.0
    panel_zone_shear_kN: float = 1.0
    connection_shear_kN: float = 1.0
    connection_rotation_mrad: float = 1.0


@dataclass(frozen=True)
class SteelCheckResult:
    component: str
    clause: str
    demand: float
    capacity: float
    dcr: float


CLAUSE_MAP = {
    "beam:flexure": "KDS-STEEL-BEAM-FLEX-001",
    "beam:shear": "KDS-STEEL-BEAM-SHEAR-001",
    "beam:web_buckling": "KDS-STEEL-BEAM-WEB-001",
    "column:axial_flexure": "KDS-STEEL-COL-INT-001",
    "column:shear": "KDS-STEEL-COL-SHEAR-001",
    "column:local_buckling": "KDS-STEEL-COL-BUCKLING-001",
    "brace:axial": "KDS-STEEL-BRACE-AXIAL-001",
    "brace:buckling": "KDS-STEEL-BRACE-BUCKLING-001",
    "brace:gusset": "KDS-STEEL-BRACE-GUSSET-001",
    "connection:shear": "KDS-STEEL-CONN-SHEAR-001",
    "connection:rotation": "KDS-STEEL-CONN-ROT-001",
    "panel_zone:shear": "KDS-STEEL-PZ-SHEAR-001",
}


def _dcr(demand: float, capacity: float) -> float:
    return abs(float(demand)) / max(abs(float(capacity)), 1e-9)


def evaluate_steel_member(
    *,
    member_type: str,
    demand: SteelMemberDemand,
    capacity: SteelMemberCapacity,
    topology_type: str = "",
) -> list[SteelCheckResult]:
    member = str(member_type).strip().lower()
    topology = str(topology_type).strip().lower()

    if member == "beam":
        flexure = _dcr(demand.moment_kNm, capacity.moment_kNm)
        shear = _dcr(demand.shear_kN, capacity.shear_kN)
        web_buckling = 0.55 * flexure + 0.45 * shear
        return [
            SteelCheckResult("flexure", CLAUSE_MAP["beam:flexure"], demand.moment_kNm, capacity.moment_kNm, flexure),
            SteelCheckResult("shear", CLAUSE_MAP["beam:shear"], demand.shear_kN, capacity.shear_kN, shear),
            SteelCheckResult("web_local_buckling", CLAUSE_MAP["beam:web_buckling"], web_buckling, 1.0, web_buckling),
        ]

    if member == "column":
        axial_flexure = 0.60 * _dcr(demand.axial_kN, capacity.axial_kN) + 0.40 * _dcr(demand.moment_kNm, capacity.moment_kNm)
        shear = _dcr(demand.shear_kN, capacity.shear_kN)
        local_buckling = _dcr(capacity.buckling_factor_min, demand.buckling_factor)
        return [
            SteelCheckResult("axial_flexure", CLAUSE_MAP["column:axial_flexure"], axial_flexure, 1.0, axial_flexure),
            SteelCheckResult("shear", CLAUSE_MAP["column:shear"], demand.shear_kN, capacity.shear_kN, shear),
            SteelCheckResult("local_buckling", CLAUSE_MAP["column:local_buckling"], capacity.buckling_factor_min, demand.buckling_factor, local_buckling),
        ]

    if member == "brace":
        axial = _dcr(demand.axial_kN, capacity.axial_kN)
        buckling = _dcr(capacity.buckling_factor_min, demand.buckling_factor)
        gusset = 0.65 * axial + 0.35 * _dcr(demand.shear_kN, capacity.shear_kN)
        return [
            SteelCheckResult("axial", CLAUSE_MAP["brace:axial"], demand.axial_kN, capacity.axial_kN, axial),
            SteelCheckResult("buckling", CLAUSE_MAP["brace:buckling"], capacity.buckling_factor_min, demand.buckling_factor, buckling),
            SteelCheckResult("gusset_connection", CLAUSE_MAP["brace:gusset"], gusset, 1.0, gusset),
        ]

    if member == "connection" or topology == "jointed-frame":
        shear = _dcr(demand.connection_shear_kN, capacity.connection_shear_kN)
        rotation = _dcr(demand.connection_rotation_mrad, capacity.connection_rotation_mrad)
        panel_zone = _dcr(demand.panel_zone_shear_kN, capacity.panel_zone_shear_kN)
        return [
            SteelCheckResult("connection_shear", CLAUSE_MAP["connection:shear"], demand.connection_shear_kN, capacity.connection_shear_kN, shear),
            SteelCheckResult("connection_rotation", CLAUSE_MAP["connection:rotation"], demand.connection_rotation_mrad, capacity.connection_rotation_mrad, rotation),
            SteelCheckResult("panel_zone_shear", CLAUSE_MAP["panel_zone:shear"], demand.panel_zone_shear_kN, capacity.panel_zone_shear_kN, panel_zone),
        ]

    raise ValueError(f"unsupported member type: {member_type}")


def governing_result(results: list[SteelCheckResult]) -> SteelCheckResult:
    if not results:
        raise ValueError("empty steel check result set")
    return max(results, key=lambda item: float(item.dcr))


__all__ = [
    "SteelCheckResult",
    "SteelMemberCapacity",
    "SteelMemberDemand",
    "evaluate_steel_member",
    "governing_result",
]
