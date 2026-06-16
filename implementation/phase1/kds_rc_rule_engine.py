#!/usr/bin/env python3
"""KDS RC member rule checks with detailed design provisions."""

from __future__ import annotations

from dataclasses import dataclass
import math


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
    torsion_kNm: float = 0.0
    deflection_mm: float = 0.0
    crack_width_mm: float = 0.0
    vibration_hz: float = 0.0


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
    torsion_kNm: float = 1.0
    deflection_limit_mm: float = 1.0
    crack_width_limit_mm: float = 1.0
    vibration_limit_hz: float = 1.0


@dataclass(frozen=True)
class RCCheckResult:
    component: str
    clause: str
    demand: float
    capacity: float
    dcr: float


@dataclass(frozen=True)
class RCSectionDesign:
    """RC section design parameters."""
    width_m: float = 0.30
    depth_m: float = 0.50
    cover_m: float = 0.04
    fc_mpa: float = 30.0
    fy_mpa: float = 400.0
    bar_diameter_m: float = 0.019
    bar_count: int = 4
    stirrup_diameter_m: float = 0.013
    stirrup_spacing_m: float = 0.20


CLAUSE_MAP = {
    "beam:flexure": "KDS-RC-BEAM-FLEX-001",
    "beam:shear": "KDS-RC-BEAM-SHEAR-001",
    "beam:torsion": "KDS-RC-BEAM-TORS-001",
    "beam:deflection": "KDS-RC-BEAM-DEF-001",
    "beam:crack": "KDS-RC-BEAM-CRACK-001",
    "column:axial_flexure": "KDS-RC-COL-INT-001",
    "column:shear": "KDS-RC-COL-SHEAR-001",
    "column:slenderness": "KDS-RC-COL-SLEND-001",
    "wall:axial_flexure": "KDS-RC-WALL-INT-001",
    "wall:shear": "KDS-RC-WALL-SHEAR-001",
    "wall:drift": "KDS-RC-WALL-DRIFT-001",
    "wall:boundary": "KDS-RC-WALL-BE-001",
    "wall:coupling": "KDS-RC-WALL-COUP-001",
    "slab:flexure": "KDS-RC-SLAB-FLEX-001",
    "slab:punching": "KDS-RC-SLAB-PUNCH-001",
    "slab:deflection": "KDS-RC-SLAB-DEF-001",
    "slab:vibration": "KDS-RC-SLAB-VIB-001",
    "foundation:bearing": "KDS-RC-FOUND-BEAR-001",
    "foundation:shear": "KDS-RC-FOUND-SHEAR-001",
    "foundation:flexure": "KDS-RC-FOUND-FLEX-001",
    "connection:shear_friction": "KDS-RC-CONN-SHEAR-001",
    "connection:slip": "KDS-RC-CONN-SLIP-001",
    "connection:rotation": "KDS-RC-CONN-ROT-001",
}


def _dcr(demand: float, capacity: float) -> float:
    return abs(float(demand)) / max(abs(float(capacity)), 1e-9)


def calculate_rc_section_capacity(section: RCSectionDesign) -> RCMemberCapacity:
    """Calculate RC section capacity based on design parameters."""
    width = max(float(section.width_m), 0.01)
    depth = max(float(section.depth_m), 0.01)
    cover = min(float(section.cover_m), 0.5 * min(width, depth))
    fc = max(float(section.fc_mpa), 15.0)
    fy = max(float(section.fy_mpa), 300.0)
    
    effective_depth = depth - cover - 0.5 * float(section.bar_diameter_m)
    bar_area = math.pi * (0.5 * float(section.bar_diameter_m)) ** 2
    total_steel_area = float(section.bar_count) * bar_area
    
    steel_ratio = total_steel_area / max(width * effective_depth, 1e-9)
    steel_ratio = min(steel_ratio, 0.04)
    
    moment_capacity = 0.9 * total_steel_area * fy * (effective_depth - 0.5 * total_steel_area * fy / (0.85 * fc * width))
    moment_capacity = max(moment_capacity, 1.0)
    
    shear_capacity = 0.17 * math.sqrt(fc) * width * effective_depth * 1000.0
    
    axial_capacity = (0.85 * fc * (width * depth - total_steel_area) + total_steel_area * fy) * 1000.0
    
    torsion_capacity = 0.33 * math.sqrt(fc) * width * depth * min(width, depth) * 1000.0
    
    deflection_limit = 25.0
    
    crack_width_limit = 0.30
    
    vibration_limit = 8.0
    
    drift_limit = 0.50
    
    return RCMemberCapacity(
        axial_kN=axial_capacity,
        shear_kN=shear_capacity,
        moment_kNm=moment_capacity,
        drift_ratio_pct=drift_limit,
        punching_shear_kN=shear_capacity * 1.2,
        boundary_comp_kN=axial_capacity * 0.3,
        footing_bearing_kPa=300.0,
        footing_shear_kN=shear_capacity,
        connection_shear_kN=shear_capacity * 0.8,
        connection_slip_mm=2.0,
        connection_rotation_mrad=10.0,
        torsion_kNm=torsion_capacity,
        deflection_limit_mm=deflection_limit,
        crack_width_limit_mm=crack_width_limit,
        vibration_limit_hz=vibration_limit,
    )


def evaluate_rc_member(
    *,
    member_type: str,
    demand: RCMemberDemand,
    capacity: RCMemberCapacity,
) -> list[RCCheckResult]:
    t = str(member_type).strip().lower()
    if t == "beam":
        results = [
            RCCheckResult("flexure", CLAUSE_MAP["beam:flexure"], demand.moment_kNm, capacity.moment_kNm, _dcr(demand.moment_kNm, capacity.moment_kNm)),
            RCCheckResult("shear", CLAUSE_MAP["beam:shear"], demand.shear_kN, capacity.shear_kN, _dcr(demand.shear_kN, capacity.shear_kN)),
        ]
        if demand.torsion_kNm > 0.0:
            results.append(RCCheckResult("torsion", CLAUSE_MAP["beam:torsion"], demand.torsion_kNm, capacity.torsion_kNm, _dcr(demand.torsion_kNm, capacity.torsion_kNm)))
        if demand.deflection_mm > 0.0:
            results.append(RCCheckResult("deflection", CLAUSE_MAP["beam:deflection"], demand.deflection_mm, capacity.deflection_limit_mm, _dcr(demand.deflection_mm, capacity.deflection_limit_mm)))
        if demand.crack_width_mm > 0.0:
            results.append(RCCheckResult("crack", CLAUSE_MAP["beam:crack"], demand.crack_width_mm, capacity.crack_width_limit_mm, _dcr(demand.crack_width_mm, capacity.crack_width_limit_mm)))
        return results
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
        results = [
            RCCheckResult("flexure", CLAUSE_MAP["slab:flexure"], demand.moment_kNm, capacity.moment_kNm, _dcr(demand.moment_kNm, capacity.moment_kNm)),
            RCCheckResult("punching", CLAUSE_MAP["slab:punching"], demand.punching_shear_kN, capacity.punching_shear_kN, _dcr(demand.punching_shear_kN, capacity.punching_shear_kN)),
        ]
        if demand.deflection_mm > 0.0:
            results.append(RCCheckResult("deflection", CLAUSE_MAP["slab:deflection"], demand.deflection_mm, capacity.deflection_limit_mm, _dcr(demand.deflection_mm, capacity.deflection_limit_mm)))
        if demand.vibration_hz > 0.0:
            results.append(RCCheckResult("vibration", CLAUSE_MAP["slab:vibration"], capacity.vibration_limit_hz, demand.vibration_hz, _dcr(capacity.vibration_limit_hz, demand.vibration_hz)))
        return results
    if t == "foundation":
        return [
            RCCheckResult("bearing", CLAUSE_MAP["foundation:bearing"], demand.footing_bearing_kPa, capacity.footing_bearing_kPa, _dcr(demand.footing_bearing_kPa, capacity.footing_bearing_kPa)),
            RCCheckResult("shear", CLAUSE_MAP["foundation:shear"], demand.footing_shear_kN, capacity.footing_shear_kN, _dcr(demand.footing_shear_kN, capacity.footing_shear_kN)),
            RCCheckResult("flexure", CLAUSE_MAP["foundation:flexure"], demand.moment_kNm, capacity.moment_kNm, _dcr(demand.moment_kNm, capacity.moment_kNm)),
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


def design_rc_beam(
    *,
    width_m: float = 0.30,
    depth_m: float = 0.50,
    span_m: float = 6.0,
    dead_load_kn_per_m: float = 20.0,
    live_load_kn_per_m: float = 15.0,
    fc_mpa: float = 30.0,
    fy_mpa: float = 400.0,
) -> dict:
    """Design RC beam with simplified provisions."""
    width = max(float(width_m), 0.20)
    depth = max(float(depth_m), 0.30)
    span = max(float(span_m), 1.0)
    fc = max(float(fc_mpa), 20.0)
    fy = max(float(fy_mpa), 300.0)
    
    wu = 1.2 * float(dead_load_kn_per_m) + 1.6 * float(live_load_kn_per_m)
    moment = wu * span**2 / 8.0
    shear = wu * span / 2.0
    
    effective_depth = depth - 0.06
    bar_area = 0.000285
    required_steel_area = moment * 1e6 / (0.9 * fy * effective_depth * 0.8)
    bar_count = max(2, int(required_steel_area / bar_area))
    
    section = RCSectionDesign(
        width_m=width,
        depth_m=depth,
        fc_mpa=fc,
        fy_mpa=fy_mpa,
        bar_count=bar_count,
    )
    capacity = calculate_rc_section_capacity(section)
    
    demand = RCMemberDemand(
        shear_kN=shear,
        moment_kNm=moment,
    )
    checks = evaluate_rc_member(member_type="beam", demand=demand, capacity=capacity)
    governing = governing_result(checks)
    
    return {
        "member_type": "beam",
        "width_m": width,
        "depth_m": depth,
        "span_m": span,
        "wu_kn_per_m": wu,
        "moment_kNm": moment,
        "shear_kN": shear,
        "bar_count": bar_count,
        "bar_area_mm2": bar_count * bar_area * 1e6,
        "capacity": capacity,
        "checks": checks,
        "governing_dcr": governing.dcr,
        "governing_clause": governing.clause,
    }


__all__ = [
    "RCCheckResult",
    "RCMemberCapacity",
    "RCMemberDemand",
    "RCSectionDesign",
    "calculate_rc_section_capacity",
    "design_rc_beam",
    "evaluate_rc_member",
    "governing_result",
]
