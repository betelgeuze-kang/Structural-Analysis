#!/usr/bin/env python3
"""Material evidence bridge: export extended material library snapshots to viewer JSON.

This module serializes reduced-order constitutive responses into compact JSON
that the Structure Viewer can render as stress-strain curves, capacity envelopes,
and material property cards.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from typing import Any

from implementation.phase1.extended_material_library import (
    AnchorMaterial,
    BoltMaterial,
    CableMaterial,
    ColdFormedSteel,
    CompositeActionMaterial,
    CorrosionModel,
    FatigueModel,
    FireModel,
    FRPMaterial,
    LeadRubberBearing,
    MasonryMaterial,
    MaterialSnapshot,
    PrestressingSteel,
    RockMaterial,
    SoilMaterial,
    TimberMaterial,
    ViscousDamper,
    WeldMaterial,
    bolt_slip_resistance,
    anchor_tension_capacity,
    weld_shear_capacity,
    lrb_response,
    cable_response,
    frp_response,
    soil_mohr_coulomb_response,
    rock_hoek_brown_response,
    timber_response,
    masonry_compression_response,
    cold_formed_steel_response,
    prestressing_steel_response,
)
from implementation.phase1.rc_constitutive_library import (
    ConcreteMaterial,
    SteelMaterial,
    concrete_response,
    steel_response,
    CompositeActionMaterial as RcCompositeActionMaterial,
    composite_action_response,
)


def _to_json_friendly(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_json_friendly(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_friendly(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_json_friendly(v) for k, v in value.items()}
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            return None
        return round(value, 8)
    return value


def _make_curve_points(response_fn, strain_range, mat=None, **kwargs):
    points = []
    for strain in strain_range:
        snap = response_fn(strain, mat) if mat is None else response_fn(strain, mat=mat, **kwargs)
        if isinstance(snap, MaterialSnapshot):
            points.append({
                "x": round(float(snap.strain), 6),
                "y": round(float(snap.stress_mpa), 3),
                "tag": str(snap.state_tag),
            })
        elif hasattr(snap, "envelope") and hasattr(snap, "restoring"):
            points.append({
                "x": round(float(snap.restoring.strain), 6),
                "y": round(float(snap.restoring.stress_mpa), 3),
                "tag": str(snap.restoring.state_tag),
            })
    return points


def _make_lrb_curve_points(displacements, bearing):
    points = []
    for d in displacements:
        snap = lrb_response(d, bearing)
        points.append({
            "x": round(float(snap.strain), 3),
            "y": round(float(snap.stress_mpa), 3),
            "tag": str(snap.state_tag),
        })
    return points


def build_material_evidence_payload(
    *,
    concrete: ConcreteMaterial | None = None,
    steel: SteelMaterial | None = None,
    prestressing: PrestressingSteel | None = None,
    cable: CableMaterial | None = None,
    frp: FRPMaterial | None = None,
    soil: SoilMaterial | None = None,
    rock: RockMaterial | None = None,
    timber: TimberMaterial | None = None,
    masonry: MasonryMaterial | None = None,
    cold_formed: ColdFormedSteel | None = None,
    bolt: BoltMaterial | None = None,
    anchor: AnchorMaterial | None = None,
    weld: WeldMaterial | None = None,
    lrb: LeadRubberBearing | None = None,
    viscous_damper: ViscousDamper | None = None,
    composite: CompositeActionMaterial | None = None,
    corrosion: CorrosionModel | None = None,
    fire: FireModel | None = None,
    fatigue: FatigueModel | None = None,
) -> dict:
    """Build a comprehensive material evidence payload for the viewer."""

    payload = {
        "schema_version": "material-evidence.v1",
        "materials": {},
        "capacity_checks": {},
        "durability": {},
    }

    # Concrete stress-strain curve
    if concrete is not None:
        strain_range = [-0.005 + i * 0.0002 for i in range(51)]
        payload["materials"]["concrete"] = {
            "family": "concrete",
            "properties": _to_json_friendly(concrete),
            "curve": _make_curve_points(concrete_response, strain_range, concrete),
            "peak_compression": {
                "fc_mpa": round(float(concrete.fc_mpa), 1),
                "eps_c0": round(float(concrete.eps_c0), 4),
                "eps_cu": round(float(concrete.eps_cu), 4),
            },
        }

    # Steel stress-strain curve
    if steel is not None:
        strain_range = [-0.015 + i * 0.0006 for i in range(51)]
        payload["materials"]["steel"] = {
            "family": "steel",
            "properties": _to_json_friendly(steel),
            "curve": _make_curve_points(steel_response, strain_range, steel),
            "yield_point": {
                "fy_mpa": round(float(steel.fy_mpa), 1),
                "eps_y": round(float(steel.eps_y), 6),
            },
        }

    # Prestressing steel
    if prestressing is not None:
        strain_range = [-0.01 + i * 0.001 for i in range(41)]
        payload["materials"]["prestressing"] = {
            "family": "prestressing",
            "properties": _to_json_friendly(prestressing),
            "curve": _make_curve_points(prestressing_steel_response, strain_range, prestressing),
            "relaxation_1000h": round(float(prestressing.relaxation_1000h), 4),
        }

    # Cable
    if cable is not None:
        strain_range = [-0.005 + i * 0.001 for i in range(46)]
        payload["materials"]["cable"] = {
            "family": "cable",
            "properties": _to_json_friendly(cable),
            "curve": _make_curve_points(cable_response, strain_range, cable),
            "damping_ratio": round(float(cable.damping_ratio), 4),
        }

    # FRP
    if frp is not None:
        strain_range = [i * 0.0003 for i in range(51)]
        payload["materials"]["frp"] = {
            "family": "frp",
            "properties": _to_json_friendly(frp),
            "curve": _make_curve_points(frp_response, strain_range, frp),
            "fiber_type": str(frp.fiber_type),
            "environmental_reduction": round(float(frp.environmental_reduction), 3),
        }

    # Soil
    if soil is not None:
        strain_range = [-0.01 + i * 0.0004 for i in range(51)]
        payload["materials"]["soil"] = {
            "family": "soil",
            "properties": _to_json_friendly(soil),
            "curve": _make_curve_points(soil_mohr_coulomb_response, strain_range, soil, confining_pressure_kpa=50.0),
            "cohesion_kpa": round(float(soil.cohesion_kpa), 2),
            "friction_angle_deg": round(float(soil.friction_angle_deg), 1),
        }

    # Rock
    if rock is not None:
        strain_range = [-0.005 + i * 0.0002 for i in range(51)]
        payload["materials"]["rock"] = {
            "family": "rock",
            "properties": _to_json_friendly(rock),
            "curve": _make_curve_points(rock_hoek_brown_response, strain_range, rock, confining_pressure_mpa=5.0),
            "gsi": round(float(rock.gsi), 1),
            "mi": round(float(rock.mi), 1),
        }

    # Timber
    if timber is not None:
        strain_range = [-0.01 + i * 0.0004 for i in range(51)]
        payload["materials"]["timber"] = {
            "family": "timber",
            "properties": _to_json_friendly(timber),
            "curve_parallel": _make_curve_points(lambda e: timber_response(e, direction="parallel", mat=timber), strain_range),
            "curve_perpendicular": _make_curve_points(lambda e: timber_response(e, direction="perpendicular", mat=timber), strain_range),
            "grade": str(timber.grade),
        }

    # Masonry
    if masonry is not None:
        strain_range = [-0.005 + i * 0.0002 for i in range(26)]
        payload["materials"]["masonry"] = {
            "family": "masonry",
            "properties": _to_json_friendly(masonry),
            "curve": _make_curve_points(masonry_compression_response, strain_range, masonry),
            "fm_mpa": round(float(masonry.fm_mpa), 1),
        }

    # Cold-formed steel
    if cold_formed is not None:
        strain_range = [-0.015 + i * 0.0006 for i in range(51)]
        payload["materials"]["cold_formed_steel"] = {
            "family": "cold_formed_steel",
            "properties": _to_json_friendly(cold_formed),
            "curve": _make_curve_points(cold_formed_steel_response, strain_range, cold_formed),
        }

    # Bolt capacity
    if bolt is not None:
        payload["capacity_checks"]["bolt_slip_resistance_kn"] = round(bolt_slip_resistance(bolt), 2)
        payload["materials"]["bolt"] = {
            "family": "bolt",
            "properties": _to_json_friendly(bolt),
        }

    # Anchor capacity
    if anchor is not None:
        payload["capacity_checks"]["anchor_tension_capacity_kn"] = round(anchor_tension_capacity(anchor), 2)
        payload["materials"]["anchor"] = {
            "family": "anchor",
            "properties": _to_json_friendly(anchor),
        }

    # Weld capacity
    if weld is not None:
        payload["capacity_checks"]["weld_shear_capacity_kn_per_mm"] = round(weld_shear_capacity(weld), 4)
        payload["materials"]["weld"] = {
            "family": "weld",
            "properties": _to_json_friendly(weld),
        }

    # LRB hysteresis
    if lrb is not None:
        displacements = [-250 + i * 10 for i in range(51)]
        payload["materials"]["lrb"] = {
            "family": "lrb",
            "properties": _to_json_friendly(lrb),
            "hysteresis": _make_lrb_curve_points(displacements, lrb),
            "characteristic_strength_kn": round(float(lrb.characteristic_strength_kn), 1),
        }

    # Viscous damper
    if viscous_damper is not None:
        velocities = [-2.0 + i * 0.08 for i in range(51)]
        payload["materials"]["viscous_damper"] = {
            "family": "viscous_damper",
            "properties": _to_json_friendly(viscous_damper),
            "force_velocity_curve": [
                {"v": round(v, 3), "f": round(float(viscous_damper_force(v, viscous_damper)), 2)}
                for v in velocities
            ],
        }

    # Composite action
    if composite is not None:
        payload["materials"]["composite"] = {
            "family": "composite",
            "properties": _to_json_friendly(composite),
        }

    # Durability
    if corrosion is not None:
        payload["durability"]["corrosion"] = {
            "corrosion_initiated": bool(corrosion.corrosion_initiated),
            "remaining_cover_mm": round(float(corrosion.remaining_cover_mm), 2),
            "diameter_loss_percent": round(float(corrosion.diameter_loss_percent), 2),
        }
    if fire is not None:
        payload["durability"]["fire"] = {
            "steel_reduction_factor": round(float(fire.steel_reduction_factor), 4),
            "concrete_reduction_factor": round(float(fire.concrete_reduction_factor), 4),
            "timber_char_depth_mm": round(float(fire.timber_char_depth_mm), 2),
        }
    if fatigue is not None:
        payload["durability"]["fatigue"] = {
            "remaining_life_cycles": round(float(fatigue.remaining_life_cycles()), 0),
            "detail_category_mpa": round(float(fatigue.detail_category_mpa), 1),
            "stress_range_mpa": round(float(fatigue.stress_range_mpa), 1),
        }

    return payload


def export_material_evidence_json(
    output_path: str,
    **kwargs,
) -> str:
    """Export material evidence to a JSON file for the viewer."""
    payload = build_material_evidence_payload(**kwargs)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path


if __name__ == "__main__":
    # Demo export with all default materials
    demo = build_material_evidence_payload(
        concrete=ConcreteMaterial(fc_mpa=30.0),
        steel=SteelMaterial(fy_mpa=420.0),
        prestressing=PrestressingSteel(),
        cable=CableMaterial(),
        frp=FRPMaterial(),
        soil=SoilMaterial(),
        rock=RockMaterial(),
        timber=TimberMaterial(),
        masonry=MasonryMaterial(),
        cold_formed=ColdFormedSteel(),
        bolt=BoltMaterial(),
        anchor=AnchorMaterial(),
        weld=WeldMaterial(),
        lrb=LeadRubberBearing(),
        viscous_damper=ViscousDamper(),
        corrosion=CorrosionModel(),
        fire=FireModel(),
        fatigue=FatigueModel(),
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2)[:2000])
