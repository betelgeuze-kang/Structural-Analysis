#!/usr/bin/env python3
"""Generate Phase-A (A1~A5) contract report for railway/tunnel extension."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


SCHEMA_VERSION = "1.0"
RUN_ID = "phase1-phasea-contract"

REASONS = {
    "PASS": "phase-a contracts are valid",
    "ERR_DYNAMICS_DOMAIN_REPORT": "dynamics domain report (building/track/tunnel) is missing or invalid",
    "ERR_VEHICLE_SCHEMA": "vehicle model schema is missing required structure",
    "ERR_TUNNEL_SCHEMA": "tunnel lining schema is missing required structure",
    "ERR_SOIL_TABLE": "soil impedance table is missing required structure",
    "ERR_MATERIAL_RULE_TABLE": "material rule table missing railway/tunnel required rules",
    "ERR_JSON_IO": "one or more input json artifacts cannot be loaded",
}


def _load_json(path: str) -> tuple[dict | None, str | None]:
    p = Path(path)
    if not p.exists():
        return None, f"file not found: {path}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, f"json parse error ({path}): {exc}"


def _is_schema_root(payload: dict) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("$schema"), str)
        and payload.get("type") == "object"
        and isinstance(payload.get("properties"), dict)
        and isinstance(payload.get("required"), list)
    )


def _get_nested(d: dict, path: list[str]) -> object:
    cur: object = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _validate_domain_report(report: dict, expected_domain: str) -> list[str]:
    errs: list[str] = []
    if report.get("domain_type") != expected_domain:
        errs.append(f"domain_type must be {expected_domain}")
    if report.get("reason_code") != "PASS":
        errs.append("reason_code must be PASS")
    if report.get("contract_pass") is not True:
        errs.append("contract_pass must be true")
    if not isinstance(report.get("payload"), dict):
        errs.append("payload missing")
    return errs


def _validate_vehicle_schema(payload: dict) -> list[str]:
    errs: list[str] = []
    if not _is_schema_root(payload):
        return ["invalid schema root"]

    required = set(payload.get("required", []))
    must = {"schema_version", "vehicle_id", "car_body", "bogies", "wheelsets", "speed_m_s"}
    miss = sorted(must - required)
    if miss:
        errs.append(f"required keys missing: {','.join(miss)}")

    props = payload.get("properties", {})
    for k in must:
        if k not in props:
            errs.append(f"properties.{k} missing")

    if _get_nested(payload, ["properties", "car_body", "properties", "mass_kg"]) is None:
        errs.append("car_body.mass_kg missing")
    if _get_nested(payload, ["properties", "bogies", "items", "properties", "secondary_suspension"]) is None:
        errs.append("bogies.secondary_suspension missing")
    if _get_nested(payload, ["properties", "wheelsets", "items", "properties", "primary_suspension"]) is None:
        errs.append("wheelsets.primary_suspension missing")
    return errs


def _validate_tunnel_schema(payload: dict) -> list[str]:
    errs: list[str] = []
    if not _is_schema_root(payload):
        return ["invalid schema root"]

    required = set(payload.get("required", []))
    must = {"schema_version", "tunnel_id", "cross_section", "lining", "alignment"}
    miss = sorted(must - required)
    if miss:
        errs.append(f"required keys missing: {','.join(miss)}")

    if _get_nested(payload, ["properties", "cross_section", "properties", "shape"]) is None:
        errs.append("cross_section.shape missing")
    if _get_nested(payload, ["properties", "lining", "properties", "material", "properties", "E_Pa"]) is None:
        errs.append("lining.material.E_Pa missing")
    if _get_nested(payload, ["properties", "lining", "properties", "segment_joints"]) is None:
        errs.append("lining.segment_joints missing")
    if _get_nested(payload, ["properties", "alignment", "properties", "total_length_m"]) is None:
        errs.append("alignment.total_length_m missing")
    return errs


def _validate_soil_table_schema(payload: dict) -> list[str]:
    errs: list[str] = []
    if not _is_schema_root(payload):
        return ["invalid schema root"]

    required = set(payload.get("required", []))
    if "schema_version" not in required or "soil_profiles" not in required:
        errs.append("required must include schema_version and soil_profiles")

    layers = _get_nested(payload, ["properties", "soil_profiles", "additionalProperties", "properties", "layers"])
    if not isinstance(layers, dict):
        errs.append("soil_profiles.layers schema missing")
    else:
        layer_req = _get_nested(payload, ["properties", "soil_profiles", "additionalProperties", "properties", "layers", "items", "required"])
        if not isinstance(layer_req, list) or "shear_wave_velocity_m_s" not in layer_req:
            errs.append("layers.items.required.shear_wave_velocity_m_s missing")

    f_range = _get_nested(payload, ["properties", "soil_profiles", "additionalProperties", "properties", "impedance_functions", "properties", "frequency_range_hz"])
    if not isinstance(f_range, dict):
        errs.append("impedance_functions.frequency_range_hz missing")
    else:
        if int(f_range.get("minItems", 0)) != 2 or int(f_range.get("maxItems", 0)) != 2:
            errs.append("frequency_range_hz must be fixed-length [2]")
    return errs


def _validate_material_rule_table(payload: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(payload, dict):
        return ["material table must be object"]

    for family in ("railway_krs_2024", "tunnel_kds_2024"):
        if family not in payload or not isinstance(payload[family], dict) or len(payload[family]) == 0:
            errs.append(f"{family} missing/empty")

    railway_required = {"rail_steel_UIC60", "ballast_granite", "slab_track_concrete", "rail_fastener_pandrol"}
    tunnel_required = {"segment_concrete_C50", "segment_bolt_M30", "grout_backfill"}

    railway = payload.get("railway_krs_2024", {}) if isinstance(payload.get("railway_krs_2024"), dict) else {}
    tunnel = payload.get("tunnel_kds_2024", {}) if isinstance(payload.get("tunnel_kds_2024"), dict) else {}

    for name in sorted(railway_required):
        if name not in railway:
            errs.append(f"railway_krs_2024.{name} missing")
            continue
        rule = railway[name]
        if not isinstance(rule, dict) or not isinstance(rule.get("rule_id"), str):
            errs.append(f"railway_krs_2024.{name}.rule_id missing")
            continue
        y = rule.get("yield_strain_range")
        if not isinstance(y, list) or len(y) != 2:
            errs.append(f"railway_krs_2024.{name}.yield_strain_range invalid")

    for name in sorted(tunnel_required):
        if name not in tunnel:
            errs.append(f"tunnel_kds_2024.{name} missing")
            continue
        rule = tunnel[name]
        if not isinstance(rule, dict) or not isinstance(rule.get("rule_id"), str):
            errs.append(f"tunnel_kds_2024.{name}.rule_id missing")
            continue
        y = rule.get("yield_strain_range")
        if not isinstance(y, list) or len(y) != 2:
            errs.append(f"tunnel_kds_2024.{name}.yield_strain_range invalid")
    return errs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dyn-building", default="implementation/phase1/dynamics_boundary_report.building.json")
    p.add_argument("--dyn-track", default="implementation/phase1/dynamics_boundary_report.track.json")
    p.add_argument("--dyn-tunnel", default="implementation/phase1/dynamics_boundary_report.tunnel.json")
    p.add_argument("--dyn-coupled", default="implementation/phase1/dynamics_boundary_report.coupled.json")
    p.add_argument("--vehicle-schema", default="implementation/phase1/vehicle_model_schema.json")
    p.add_argument("--tunnel-schema", default="implementation/phase1/tunnel_lining_schema.json")
    p.add_argument("--soil-table", default="implementation/phase1/soil_impedance_table.json")
    p.add_argument("--material-table", default="implementation/phase1/material_rule_table.json")
    p.add_argument("--out", default="implementation/phase1/phasea_contract_report.json")
    args = p.parse_args()

    io_errors: list[str] = []
    domain_building, err = _load_json(args.dyn_building)
    if err:
        io_errors.append(err)
    domain_track, err = _load_json(args.dyn_track)
    if err:
        io_errors.append(err)
    domain_tunnel, err = _load_json(args.dyn_tunnel)
    if err:
        io_errors.append(err)
    domain_coupled, err = _load_json(args.dyn_coupled)
    if err:
        io_errors.append(err)
    vehicle_schema, err = _load_json(args.vehicle_schema)
    if err:
        io_errors.append(err)
    tunnel_schema, err = _load_json(args.tunnel_schema)
    if err:
        io_errors.append(err)
    soil_table, err = _load_json(args.soil_table)
    if err:
        io_errors.append(err)
    material_table, err = _load_json(args.material_table)
    if err:
        io_errors.append(err)

    dyn_errors: list[str] = []
    vehicle_errors: list[str] = []
    tunnel_errors: list[str] = []
    soil_errors: list[str] = []
    material_errors: list[str] = []

    if not io_errors:
        dyn_errors.extend(_validate_domain_report(domain_building, "building"))
        dyn_errors.extend(_validate_domain_report(domain_track, "track"))
        dyn_errors.extend(_validate_domain_report(domain_tunnel, "tunnel"))
        dyn_errors.extend(_validate_domain_report(domain_coupled, "coupled"))
        vehicle_errors = _validate_vehicle_schema(vehicle_schema)
        tunnel_errors = _validate_tunnel_schema(tunnel_schema)
        soil_errors = _validate_soil_table_schema(soil_table)
        material_errors = _validate_material_rule_table(material_table)

    checks = {
        "dynamics_domain_reports_pass": len(dyn_errors) == 0,
        "vehicle_schema_pass": len(vehicle_errors) == 0,
        "tunnel_schema_pass": len(tunnel_errors) == 0,
        "soil_impedance_table_pass": len(soil_errors) == 0,
        "material_rule_table_pass": len(material_errors) == 0,
    }

    if io_errors:
        reason_code = "ERR_JSON_IO"
    elif not checks["dynamics_domain_reports_pass"]:
        reason_code = "ERR_DYNAMICS_DOMAIN_REPORT"
    elif not checks["vehicle_schema_pass"]:
        reason_code = "ERR_VEHICLE_SCHEMA"
    elif not checks["tunnel_schema_pass"]:
        reason_code = "ERR_TUNNEL_SCHEMA"
    elif not checks["soil_impedance_table_pass"]:
        reason_code = "ERR_SOIL_TABLE"
    elif not checks["material_rule_table_pass"]:
        reason_code = "ERR_MATERIAL_RULE_TABLE"
    else:
        reason_code = "PASS"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "checks": checks,
        "errors": {
            "io": io_errors,
            "dynamics_domain_reports": dyn_errors,
            "vehicle_schema": vehicle_errors,
            "tunnel_schema": tunnel_errors,
            "soil_impedance_table": soil_errors,
            "material_rule_table": material_errors,
        },
        "inputs": {
            "dyn_building": args.dyn_building,
            "dyn_track": args.dyn_track,
            "dyn_tunnel": args.dyn_tunnel,
            "dyn_coupled": args.dyn_coupled,
            "vehicle_schema": args.vehicle_schema,
            "tunnel_schema": args.tunnel_schema,
            "soil_table": args.soil_table,
            "material_table": args.material_table,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote phase-a contract report: {out}")
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
