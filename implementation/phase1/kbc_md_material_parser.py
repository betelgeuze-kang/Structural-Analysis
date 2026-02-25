#!/usr/bin/env python3
"""KBC/IBC <-> 2-Bead MD forcefield parser.

Converts structural properties (E, A, Iy, Iz, L0, fy) into MD-style parameters.
Adds regulation mapping, warning severity, and parser quality gate outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SUPPORTED_UNITS = {"SI", "N-mm", "kN-m"}
DEFAULT_RULE_TABLE = Path("implementation/phase1/material_rule_table.json")


def to_si(row: dict) -> dict:
    units = row.get("units", "SI")
    E = float(row["E"])
    A = float(row["A"])
    Iy = float(row["Iy"])
    Iz = float(row["Iz"])
    L0 = float(row["L0"])
    fy = float(row["fy"])

    if units == "SI":
        return {"E": E, "A": A, "Iy": Iy, "Iz": Iz, "L0": L0, "fy": fy}
    if units == "N-mm":
        return {
            "E": E * 1e6,
            "A": A * 1e-6,
            "Iy": Iy * 1e-12,
            "Iz": Iz * 1e-12,
            "L0": L0 * 1e-3,
            "fy": fy * 1e6,
        }
    if units == "kN-m":
        return {"E": E * 1e3, "A": A, "Iy": Iy, "Iz": Iz, "L0": L0, "fy": fy * 1e3}
    raise ValueError(f"unsupported units: {units}")


def load_rule_table(path: Path) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "kbc_2021": {
                        "steel": {"rule_id": "KBC-STEEL-2021", "hinge_softening": 0.15, "yield_strain_range": [0.0005, 0.02]},
                        "concrete": {"rule_id": "KBC-CONCRETE-2021", "hinge_softening": 0.1, "yield_strain_range": [0.0002, 0.01]},
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _warn(level: str, message: str) -> dict:
    return {"level": level, "message": message}


def map_row(row: dict, rule_table: dict) -> dict:
    source_units = row.get("units", "SI")
    regulation = row.get("regulation", "kbc_2021").lower()
    material_type = row.get("material_type", "steel").lower()
    section_class = row.get("section_class", "default")
    temp_factor = float(row.get("temperature_factor", 1.0))
    time_factor = float(row.get("time_factor", 1.0))

    warnings: list[dict] = []
    if source_units not in SUPPORTED_UNITS:
        warnings.append(_warn("critical", f"unsupported unit flag: {source_units}"))
    if temp_factor <= 0 or time_factor <= 0:
        warnings.append(_warn("critical", "temperature_factor/time_factor must be positive"))
    elif temp_factor < 0.9 or time_factor < 0.9:
        warnings.append(_warn("warn", "environment factors indicate significant stiffness reduction"))

    si = to_si(row)
    E, A, Iy, Iz, L0, fy = si["E"], si["A"], si["Iy"], si["Iz"], si["L0"], si["fy"]

    # effective stiffness with environmental modifiers (coarse first-order model)
    effective_E = E * temp_factor * time_factor
    kb = effective_E * A / L0
    ktheta_y = effective_E * Iy / L0
    ktheta_z = effective_E * Iz / L0
    yield_strain = fy / max(effective_E, 1e-12)

    reg_rules = rule_table.get(regulation, {})
    material_rule = reg_rules.get(material_type)
    if not material_rule:
        rule_id = "UNKNOWN"
        hinge_softening = 0.12
        warnings.append(_warn("critical", f"regulation/material mapping missing: {regulation}/{material_type}"))
        yield_range = (0.0, 1.0)
    else:
        rule_id = material_rule["rule_id"]
        hinge_softening = float(material_rule["hinge_softening"])
        yr = material_rule.get("yield_strain_range", [0.0, 1.0])
        yield_range = (float(yr[0]), float(yr[1]))

    if not (yield_range[0] <= yield_strain <= yield_range[1]):
        warnings.append(
            _warn(
                "warn",
                f"yield_strain out of recommended range {yield_range}: {yield_strain:.6g}",
            )
        )

    return {
        "member_id": row.get("member_id", "unknown"),
        "material_type": material_type,
        "regulation": regulation,
        "regulation_rule_id": rule_id,
        "section_class": section_class,
        "source_units": source_units,
        "si_normalized": {"E": effective_E, "A": A, "Iy": Iy, "Iz": Iz, "L0": L0, "fy": fy},
        "Kb": kb,
        "Ktheta_y": ktheta_y,
        "Ktheta_z": ktheta_z,
        "yield_strain": yield_strain,
        "hinge_softening": hinge_softening,
        "parser_warnings": warnings,
    }


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return list(data.get("rows", []))
        if isinstance(data, list):
            return data
        raise ValueError("JSON input must be a list or {rows:[...]} object")

    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _unit_consistency(mapped: list[dict]) -> bool:
    if len(mapped) < 2:
        return True
    # compare first two records expected to represent same member in alternate units
    a, b = mapped[0], mapped[1]
    for key in ("Kb", "Ktheta_y", "Ktheta_z", "yield_strain"):
        av = float(a[key])
        bv = float(b[key])
        if abs(av) <= 1e-12:
            continue
        rel = abs(av - bv) / abs(av)
        if rel > 1e-6:
            return False
    return True


def _regulation_mapping_pass(mapped: list[dict]) -> bool:
    return all(row.get("regulation_rule_id") != "UNKNOWN" for row in mapped)


def _warning_summary(mapped: list[dict]) -> dict:
    summary = {"critical": 0, "warn": 0, "info": 0}
    for row in mapped:
        for warning in row.get("parser_warnings", []):
            level = warning.get("level", "info")
            summary[level] = summary.get(level, 0) + 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="implementation/phase1/material_input_sample.csv")
    parser.add_argument("--out", default="implementation/phase1/material_map_report.json")
    parser.add_argument("--rule-table", default=str(DEFAULT_RULE_TABLE))
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        in_path.parent.mkdir(parents=True, exist_ok=True)
        in_path.write_text(
            "member_id,units,E,A,Iy,Iz,L0,fy,material_type,regulation,section_class,temperature_factor,time_factor\n"
            "M1,SI,2.1e11,0.018,8.0e-5,3.0e-5,6.0,3.55e8,steel,kbc_2021,wide_flange,1.0,1.0\n"
            "M1_ALT,N-mm,210000,18000,8.0e7,3.0e7,6000,355,steel,kbc_2021,wide_flange,1.0,1.0\n"
            "M2,SI,3.0e10,0.12,2.2e-3,1.7e-3,4.2,3.0e7,concrete,ibc_2021,rectangular,0.98,0.95\n"
            "M3,SI,2.0e11,0.022,7.5e-5,2.8e-5,5.5,2.75e8,steel,kbc_2021,box,1.0,0.98\n",
            encoding="utf-8",
        )

    rule_table = load_rule_table(Path(args.rule_table))
    mapped = [map_row(r, rule_table) for r in read_rows(in_path)]
    unit_consistency_pass = _unit_consistency(mapped)
    regulation_mapping_pass = _regulation_mapping_pass(mapped)
    warning_summary = _warning_summary(mapped)
    critical_warning_count = int(warning_summary.get("critical", 0))
    parser_quality_pass = unit_consistency_pass and regulation_mapping_pass and critical_warning_count == 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "mapped": mapped,
                "source": str(in_path),
                "rule_table": str(args.rule_table),
                "unit_consistency_pass": unit_consistency_pass,
                "regulation_mapping_pass": regulation_mapping_pass,
                "warning_summary": warning_summary,
                "critical_warning_count": critical_warning_count,
                "parser_quality_pass": parser_quality_pass,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote material mapping report: {out}")


if __name__ == "__main__":
    main()
