#!/usr/bin/env python3
"""Simple code-check engine for member force demand/capacity reporting.

This module is intentionally deterministic and lightweight for CI usage:
- reads member-force style CSV
- evaluates per-case/component D/C
- reports governing case/component and contract pass
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

try:
    from implementation.phase1.kds_rc_rule_engine import RCMemberCapacity, RCMemberDemand, evaluate_rc_member
    from implementation.phase1.kds_steel_rule_engine import (
        SteelMemberCapacity,
        SteelMemberDemand,
        evaluate_steel_member,
    )
    from implementation.phase1.load_combination_engine import (
        KDS_CONCRETE_FAMILY,
        KDS_STEEL_BASIC_FAMILY,
        canonicalize_kds_family,
        generate_kds_service_combinations,
        generate_kds_steel_service_combinations,
        generate_kds_steel_strength_combinations,
        generate_kds_strength_combinations,
        generate_named_scale_library,
        infer_combination_family_from_midas_model,
        load_combinations_from_midas_model,
        match_runtime_to_kds,
    )
except ImportError:  # pragma: no cover - script execution fallback
    from kds_rc_rule_engine import RCMemberCapacity, RCMemberDemand, evaluate_rc_member
    from kds_steel_rule_engine import SteelMemberCapacity, SteelMemberDemand, evaluate_steel_member
    from load_combination_engine import (
        KDS_CONCRETE_FAMILY,
        KDS_STEEL_BASIC_FAMILY,
        canonicalize_kds_family,
        generate_kds_service_combinations,
        generate_kds_steel_service_combinations,
        generate_kds_steel_strength_combinations,
        generate_kds_strength_combinations,
        generate_named_scale_library,
        infer_combination_family_from_midas_model,
        load_combinations_from_midas_model,
        match_runtime_to_kds,
    )

COMPONENTS = {
    "axial_force_kN": ("axial_capacity_kN", 1.0),
    "shear_force_y_kN": ("shear_capacity_kN", 1.0),
    "shear_force_z_kN": ("shear_capacity_kN", 1.0),
    "bending_moment_y_kNm": ("moment_capacity_kNm", 1.0),
    "bending_moment_z_kNm": ("moment_capacity_kNm", 1.0),
}

COMPONENT_CLAUSES = {
    "axial_force_kN": "KDS-AXIAL-001",
    "shear_force_y_kN": "KDS-SHEAR-Y-001",
    "shear_force_z_kN": "KDS-SHEAR-Z-001",
    "bending_moment_y_kNm": "KDS-MOMENT-Y-001",
    "bending_moment_z_kNm": "KDS-MOMENT-Z-001",
}

DEFAULT_COMBINATION_LIBRARY = [
    ("ULS_GRAVITY_100", 1.00),
    ("ULS_GRAVITY_120", 1.20),
    ("ULS_GRAVITY_140", 1.40),
    ("ULS_GRAVITY_160", 1.60),
    ("ULS_WIND_X", 1.15),
    ("ULS_WIND_X_NEG", 1.15),
    ("ULS_WIND_Y", 1.18),
    ("ULS_WIND_Y_NEG", 1.18),
    ("ULS_SEISMIC_X_POS", 1.22),
    ("ULS_SEISMIC_X_NEG", 1.22),
    ("ULS_SEISMIC_Y_POS", 1.26),
    ("ULS_SEISMIC_Y_NEG", 1.26),
    ("ULS_TORSION_X_POS", 1.30),
    ("ULS_TORSION_X_NEG", 1.30),
    ("ULS_TORSION_Y_POS", 1.34),
    ("ULS_TORSION_Y_NEG", 1.34),
    ("SLS_WIND_100", 0.95),
    ("SLS_SEISMIC_085", 0.85),
    ("SLS_SERVICE", 0.92),
]

MEMBER_TYPE_FACTORS = {
    "beam": 1.00,
    "column": 1.00,
    "brace": 0.96,
    "wall": 0.92,
    "slab": 0.88,
    "foundation": 0.95,
    "connection": 0.90,
    "generic_frame": 1.00,
}

SERVICE_DRIFT_LIMIT_PCT = {
    "beam": 2.20,
    "column": 2.40,
    "brace": 1.80,
    "wall": 2.20,
    "slab": 0.70,
    "foundation": 0.20,
    "connection": 0.30,
    "generic_frame": 2.20,
}

MIN_BUCKLING_FACTOR = {
    "beam": 1.80,
    "column": 2.00,
    "brace": 1.70,
    "wall": 2.20,
    "slab": 1.60,
    "foundation": 2.50,
    "connection": 9.99,
    "generic_frame": 1.80,
}

EXTRA_CLAUSES = {
    "combined_interaction": "KDS-INT-FRAME-001",
    "drift_ratio_pct": "KDS-SVC-DRIFT-001",
    "buckling_factor": "KDS-STAB-BUCKLING-001",
}

TOPOLOGY_MEMBER_TYPE = {
    "rahmen": "beam",
    "truss": "brace",
    "wall-frame": "wall",
    "outrigger": "column",
    "jointed-frame": "connection",
}

REASONS = {
    "PASS": "code check passed",
    "ERR_INPUT": "invalid code-check input",
    "ERR_FAIL": "code check failed",
}

DEFAULT_COMBINATION_FAMILY = KDS_CONCRETE_FAMILY
STEEL_COMBINATION_FAMILY = KDS_STEEL_BASIC_FAMILY


def _read_rows(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        headers = list(rdr.fieldnames or [])
    return rows, headers


def _to_float(v: object, default: float = 0.0) -> float:
    try:
        return float(str(v).strip())
    except Exception:
        return float(default)


def _parse_scales(raw: str) -> list[float]:
    out = []
    for tok in str(raw).split(","):
        s = tok.strip()
        if not s:
            continue
        out.append(float(s))
    if not out:
        out = [1.0]
    return out


def _combination_library_from_scales(
    scales: list[float],
    *,
    family: str = DEFAULT_COMBINATION_FAMILY,
    limit_state: str = "ULS",
) -> list[tuple[str, float]]:
    family = canonicalize_kds_family(family)
    if not scales:
        try:
            return list(generate_named_scale_library(family=family, limit_state=limit_state))
        except Exception:
            return list(DEFAULT_COMBINATION_LIBRARY)
    return [(f"USER_COMBO_{i + 1:02d}", float(scale)) for i, scale in enumerate(scales)]


def _member_id(row: dict, idx: int) -> str:
    for key in ("member_id", "element_id", "case_id"):
        val = str(row.get(key, "")).strip()
        if val:
            return val
    return f"member-{idx}"


def _normalized_member_type(row: dict) -> str:
    raw_member_type = str(row.get("member_type", "")).strip().lower()
    topology_type = str(row.get("topology_type", "")).strip().lower()
    if raw_member_type and raw_member_type not in {"generic_frame", "generic"}:
        return raw_member_type
    return str(TOPOLOGY_MEMBER_TYPE.get(topology_type, "generic_frame"))


def _resolve_combination_family(
    requested_family: str | None,
    load_combination_model: dict | None,
) -> tuple[str, str]:
    explicit_family = str(requested_family or "").strip()
    if explicit_family:
        return canonicalize_kds_family(explicit_family), "user_input"
    if isinstance(load_combination_model, dict):
        inferred_family = canonicalize_kds_family(
            str(infer_combination_family_from_midas_model(load_combination_model) or "").strip()
        )
        if inferred_family:
            return inferred_family, "load_combination_model"
    return canonicalize_kds_family(DEFAULT_COMBINATION_FAMILY), "default"


def _reference_combinations(*, family: str, limit_state: str) -> list:
    family_normalized = canonicalize_kds_family(family).upper()
    limit_state_normalized = str(limit_state).strip().upper()
    if family_normalized == STEEL_COMBINATION_FAMILY.upper():
        return (
            generate_kds_steel_strength_combinations()
            if limit_state_normalized == "ULS"
            else generate_kds_steel_service_combinations()
        )
    return generate_kds_strength_combinations() if limit_state_normalized == "ULS" else generate_kds_service_combinations()


def evaluate_code_compliance(
    *,
    hf_csv: Path,
    capacity: dict[str, float],
    combination_scales: list[float],
    max_dcr: float,
    combination_family: str | None = None,
    combination_limit_state: str = "ULS",
    load_combination_model: dict | None = None,
) -> dict:
    rows, headers = _read_rows(hf_csv)
    if not rows:
        raise ValueError("hf csv has no rows")

    missing = [k for k in COMPONENTS if k not in headers]
    if missing:
        raise ValueError(f"required columns missing: {missing}")

    per_case: list[dict] = []
    combination_rows: list[dict] = []
    derived_rows: list[dict] = []
    global_max_dcr = 0.0
    governing_case = ""
    governing_member = ""
    governing_component = ""
    governing_scale = 1.0
    governing_combo = ""
    combination_provenance_rows: list[dict] = []
    effective_combination_family, combination_family_source = _resolve_combination_family(
        combination_family,
        load_combination_model,
    )
    combo_library = _combination_library_from_scales(
        combination_scales,
        family=effective_combination_family,
        limit_state=combination_limit_state,
    )
    if isinstance(load_combination_model, dict):
        runtime_combos = load_combinations_from_midas_model(load_combination_model)
        kds_combo_objs = _reference_combinations(
            family=effective_combination_family,
            limit_state=combination_limit_state,
        )
        if runtime_combos and kds_combo_objs:
            combination_provenance_rows = match_runtime_to_kds(
                runtime_combinations=runtime_combos,
                kds_combinations=kds_combo_objs,
            )
            runtime_by_name = {str(combo.name): combo for combo in runtime_combos}
            combo_library = []
            for kds_combo in kds_combo_objs:
                matched = next(
                    (
                        row
                        for row in combination_provenance_rows
                        if str(row.get("kds_name", "")) == str(kds_combo.name)
                    ),
                    None,
                )
                if matched is not None:
                    matched["reference_family"] = str(kds_combo.family)
                    matched["reference_family_source"] = str(combination_family_source)
                runtime_name = str((matched or {}).get("matched_runtime_name", ""))
                runtime_combo = runtime_by_name.get(runtime_name)
                combo_scale = float(runtime_combo.envelope_scale) if runtime_combo is not None else float(kds_combo.envelope_scale)
                combo_library.append((str(kds_combo.name), combo_scale))
    member_type_counts: dict[str, int] = {}
    clause_set: set[str] = set()
    member_ids_seen: set[str] = set()
    rc_rule_rows: list[dict] = []
    steel_rule_rows: list[dict] = []
    steel_design_active = bool(str(effective_combination_family).upper() == str(STEEL_COMBINATION_FAMILY).upper())
    steel_rule_target_count = 0

    for i, r in enumerate(rows):
        cid = str(r.get("case_id", f"row-{i}")).strip() or f"row-{i}"
        member_id = _member_id(r, i)
        member_type = _normalized_member_type(r)
        hazard_type = str(r.get("hazard_type", "unknown")).strip().lower() or "unknown"
        topology_type = str(r.get("topology_type", "generic")).strip().lower() or "generic"
        member_type_factor = float(MEMBER_TYPE_FACTORS.get(member_type, 1.0))
        member_type_counts[member_type] = int(member_type_counts.get(member_type, 0) + 1)
        member_ids_seen.add(member_id)
        case_max = 0.0
        case_governing_comp = ""
        case_governing_scale = 1.0
        case_governing_combo = ""
        component_peaks: dict[str, float] = {}
        case_check_rows: list[dict] = []
        for combo_name, scale in combo_library:
            axial_ratio = 0.0
            shear_ratio = 0.0
            moment_ratio = 0.0
            for comp, (cap_key, base_coeff) in COMPONENTS.items():
                demand = abs(_to_float(r.get(comp, 0.0))) * float(scale) * float(base_coeff)
                cap = max(abs(float(capacity[cap_key])), 1e-9)
                dcr = demand / (cap * member_type_factor)
                prev = component_peaks.get(comp, 0.0)
                if dcr > prev:
                    component_peaks[comp] = dcr
                row_payload = {
                    "member_id": member_id,
                    "case_id": cid,
                    "member_type": member_type,
                    "hazard_type": hazard_type,
                    "topology_type": topology_type,
                    "rule_family": "strength",
                    "combination": combo_name,
                    "combination_scale": float(scale),
                    "component": comp,
                    "clause": COMPONENT_CLAUSES.get(comp, "KDS-UNSPECIFIED"),
                    "demand": float(demand),
                    "capacity": float(cap * member_type_factor),
                    "dcr": float(dcr),
                }
                combination_rows.append(row_payload)
                case_check_rows.append(row_payload)
                clause_set.add(str(row_payload["clause"]))
                if comp == "axial_force_kN":
                    axial_ratio = float(dcr)
                elif comp in {"shear_force_y_kN", "shear_force_z_kN"}:
                    shear_ratio = max(float(shear_ratio), float(dcr))
                elif comp in {"bending_moment_y_kNm", "bending_moment_z_kNm"}:
                    moment_ratio = max(float(moment_ratio), float(dcr))
                if dcr > case_max:
                    case_max = dcr
                    case_governing_comp = comp
                    case_governing_scale = float(scale)
                    case_governing_combo = combo_name
            interaction_dcr = float(0.35 * axial_ratio + 0.25 * shear_ratio + 0.40 * moment_ratio)
            interaction_row = {
                "member_id": member_id,
                "case_id": cid,
                "member_type": member_type,
                "hazard_type": hazard_type,
                "topology_type": topology_type,
                "rule_family": "strength_interaction",
                "combination": combo_name,
                "combination_scale": float(scale),
                "component": "combined_interaction",
                "clause": EXTRA_CLAUSES["combined_interaction"],
                "demand": float(interaction_dcr),
                "capacity": 1.0,
                "dcr": float(interaction_dcr),
            }
            derived_rows.append(interaction_row)
            case_check_rows.append(interaction_row)
            clause_set.add(str(interaction_row["clause"]))
            if interaction_dcr > case_max:
                case_max = interaction_dcr
                case_governing_comp = "combined_interaction"
                case_governing_scale = float(scale)
                case_governing_combo = combo_name

        drift_limit = float(SERVICE_DRIFT_LIMIT_PCT.get(member_type, SERVICE_DRIFT_LIMIT_PCT["generic_frame"]))
        drift_ratio_pct = abs(_to_float(r.get("drift_ratio_pct", 0.0)))
        drift_dcr = float(drift_ratio_pct / max(drift_limit, 1e-9))
        drift_row = {
            "member_id": member_id,
            "case_id": cid,
            "member_type": member_type,
            "hazard_type": hazard_type,
            "topology_type": topology_type,
            "rule_family": "serviceability",
            "combination": "SVC_DRIFT",
            "combination_scale": 1.0,
            "component": "drift_ratio_pct",
            "clause": EXTRA_CLAUSES["drift_ratio_pct"],
            "demand": float(drift_ratio_pct),
            "capacity": float(drift_limit),
            "dcr": float(drift_dcr),
        }
        derived_rows.append(drift_row)
        case_check_rows.append(drift_row)
        clause_set.add(str(drift_row["clause"]))
        if drift_dcr > case_max:
            case_max = drift_dcr
            case_governing_comp = "drift_ratio_pct"
            case_governing_scale = 1.0
            case_governing_combo = "SVC_DRIFT"

        min_buckling = float(MIN_BUCKLING_FACTOR.get(member_type, MIN_BUCKLING_FACTOR["generic_frame"]))
        buckling_factor = max(_to_float(r.get("buckling_factor", 0.0)), 1e-9)
        buckling_dcr = float(min_buckling / buckling_factor)
        buckling_row = {
            "member_id": member_id,
            "case_id": cid,
            "member_type": member_type,
            "hazard_type": hazard_type,
            "topology_type": topology_type,
            "rule_family": "stability",
            "combination": "STAB_BUCKLING",
            "combination_scale": 1.0,
            "component": "buckling_factor",
            "clause": EXTRA_CLAUSES["buckling_factor"],
            "demand": float(min_buckling),
            "capacity": float(buckling_factor),
            "dcr": float(buckling_dcr),
        }
        derived_rows.append(buckling_row)
        case_check_rows.append(buckling_row)
        clause_set.add(str(buckling_row["clause"]))
        if buckling_dcr > case_max:
            case_max = buckling_dcr
            case_governing_comp = "buckling_factor"
            case_governing_scale = 1.0
            case_governing_combo = "STAB_BUCKLING"

        if member_type in {"beam", "column", "wall", "slab", "foundation", "connection"}:
            rc_demand = RCMemberDemand(
                axial_kN=abs(_to_float(r.get("axial_force_kN", 0.0))),
                shear_kN=max(
                    abs(_to_float(r.get("shear_force_y_kN", 0.0))),
                    abs(_to_float(r.get("shear_force_z_kN", 0.0))),
                ),
                moment_kNm=max(
                    abs(_to_float(r.get("bending_moment_y_kNm", 0.0))),
                    abs(_to_float(r.get("bending_moment_z_kNm", 0.0))),
                ),
                drift_ratio_pct=drift_ratio_pct,
                punching_shear_kN=0.55
                * max(
                    abs(_to_float(r.get("shear_force_y_kN", 0.0))),
                    abs(_to_float(r.get("shear_force_z_kN", 0.0))),
                ),
                boundary_comp_kN=abs(_to_float(r.get("axial_force_kN", 0.0))) + 0.25 * max(
                    abs(_to_float(r.get("bending_moment_y_kNm", 0.0))),
                    abs(_to_float(r.get("bending_moment_z_kNm", 0.0))),
                ),
                footing_bearing_kPa=0.12 * abs(_to_float(r.get("axial_force_kN", 0.0))),
                footing_shear_kN=max(
                    abs(_to_float(r.get("shear_force_y_kN", 0.0))),
                    abs(_to_float(r.get("shear_force_z_kN", 0.0))),
                ),
                connection_shear_kN=max(
                    abs(_to_float(r.get("shear_force_y_kN", 0.0))),
                    abs(_to_float(r.get("shear_force_z_kN", 0.0))),
                ),
                connection_slip_mm=0.08
                * max(
                    abs(_to_float(r.get("shear_force_y_kN", 0.0))),
                    abs(_to_float(r.get("shear_force_z_kN", 0.0))),
                ),
                connection_rotation_mrad=0.12
                * max(
                    abs(_to_float(r.get("bending_moment_y_kNm", 0.0))),
                    abs(_to_float(r.get("bending_moment_z_kNm", 0.0))),
                ),
            )
            rc_capacity = RCMemberCapacity(
                axial_kN=float(capacity["axial_capacity_kN"]) * member_type_factor,
                shear_kN=float(capacity["shear_capacity_kN"]) * member_type_factor,
                moment_kNm=float(capacity["moment_capacity_kNm"]) * member_type_factor,
                drift_ratio_pct=float(SERVICE_DRIFT_LIMIT_PCT.get(member_type, SERVICE_DRIFT_LIMIT_PCT["generic_frame"])),
                punching_shear_kN=float(capacity["shear_capacity_kN"]) * 0.85 * member_type_factor,
                boundary_comp_kN=float(capacity["axial_capacity_kN"]) * 0.90 * member_type_factor,
                footing_bearing_kPa=float(capacity["axial_capacity_kN"]) * 0.18 * member_type_factor,
                footing_shear_kN=float(capacity["shear_capacity_kN"]) * member_type_factor,
                connection_shear_kN=float(capacity["shear_capacity_kN"]) * 0.90 * member_type_factor,
                connection_slip_mm=float(capacity["shear_capacity_kN"]) * 0.025 * member_type_factor,
                connection_rotation_mrad=float(capacity["moment_capacity_kNm"]) * 0.05 * member_type_factor,
            )
            for rc_row in evaluate_rc_member(member_type=member_type, demand=rc_demand, capacity=rc_capacity):
                rc_payload = {
                    "member_id": member_id,
                    "case_id": cid,
                    "member_type": member_type,
                    "hazard_type": hazard_type,
                    "topology_type": topology_type,
                    "rule_family": "rc_detail",
                    "combination": "RC_DETAIL",
                    "combination_scale": 1.0,
                    "component": str(rc_row.component),
                    "clause": str(rc_row.clause),
                    "demand": float(rc_row.demand),
                    "capacity": float(rc_row.capacity),
                    "dcr": float(rc_row.dcr),
                }
                rc_rule_rows.append(rc_payload)
                case_check_rows.append(rc_payload)
                clause_set.add(str(rc_payload["clause"]))
                if float(rc_row.dcr) > case_max:
                    case_max = float(rc_row.dcr)
                    case_governing_comp = str(rc_row.component)
                    case_governing_scale = 1.0
                    case_governing_combo = "RC_DETAIL"

        if steel_design_active and member_type in {"beam", "column", "brace", "connection"}:
            steel_rule_target_count += 1
            primary_shear = max(
                abs(_to_float(r.get("shear_force_y_kN", 0.0))),
                abs(_to_float(r.get("shear_force_z_kN", 0.0))),
            )
            primary_moment = max(
                abs(_to_float(r.get("bending_moment_y_kNm", 0.0))),
                abs(_to_float(r.get("bending_moment_z_kNm", 0.0))),
            )
            steel_demand = SteelMemberDemand(
                axial_kN=abs(_to_float(r.get("axial_force_kN", 0.0))),
                shear_kN=primary_shear,
                moment_kNm=primary_moment,
                buckling_factor=buckling_factor,
                panel_zone_shear_kN=0.65 * primary_shear + 0.08 * primary_moment,
                connection_shear_kN=primary_shear,
                connection_rotation_mrad=0.06 * primary_moment,
            )
            steel_capacity = SteelMemberCapacity(
                axial_kN=float(capacity["axial_capacity_kN"]) * member_type_factor,
                shear_kN=float(capacity["shear_capacity_kN"]) * member_type_factor,
                moment_kNm=float(capacity["moment_capacity_kNm"]) * member_type_factor,
                buckling_factor_min=max(1.5, float(MIN_BUCKLING_FACTOR.get(member_type, MIN_BUCKLING_FACTOR["generic_frame"]))),
                panel_zone_shear_kN=float(capacity["shear_capacity_kN"]) * 0.95 * member_type_factor,
                connection_shear_kN=float(capacity["shear_capacity_kN"]) * 0.90 * member_type_factor,
                connection_rotation_mrad=float(capacity["moment_capacity_kNm"]) * 0.04 * member_type_factor,
            )
            for steel_row in evaluate_steel_member(
                member_type=member_type,
                demand=steel_demand,
                capacity=steel_capacity,
                topology_type=topology_type,
            ):
                steel_payload = {
                    "member_id": member_id,
                    "case_id": cid,
                    "member_type": member_type,
                    "hazard_type": hazard_type,
                    "topology_type": topology_type,
                    "rule_family": "steel_detail",
                    "combination": "STEEL_DETAIL",
                    "combination_scale": 1.0,
                    "component": str(steel_row.component),
                    "clause": str(steel_row.clause),
                    "demand": float(steel_row.demand),
                    "capacity": float(steel_row.capacity),
                    "dcr": float(steel_row.dcr),
                }
                steel_rule_rows.append(steel_payload)
                case_check_rows.append(steel_payload)
                clause_set.add(str(steel_payload["clause"]))
                if float(steel_row.dcr) > case_max:
                    case_max = float(steel_row.dcr)
                    case_governing_comp = str(steel_row.component)
                    case_governing_scale = 1.0
                    case_governing_combo = "STEEL_DETAIL"

        per_case.append(
            {
                "member_id": member_id,
                "case_id": cid,
                "member_type": member_type,
                "hazard_type": hazard_type,
                "topology_type": topology_type,
                "governing_component": case_governing_comp,
                "governing_scale": case_governing_scale,
                "governing_combination": case_governing_combo,
                "max_dcr": float(case_max),
                "component_peak_dcr": {k: float(v) for k, v in sorted(component_peaks.items())},
            }
        )
        if case_max > global_max_dcr:
            global_max_dcr = float(case_max)
            governing_case = cid
            governing_member = member_id
            governing_component = case_governing_comp
            governing_scale = case_governing_scale
            governing_combo = case_governing_combo

    derived_rows.extend(rc_rule_rows)
    derived_rows.extend(steel_rule_rows)
    all_check_rows = combination_rows + derived_rows
    contract_pass = bool(global_max_dcr <= float(max_dcr))
    reason_code = "PASS" if contract_pass else "ERR_FAIL"
    return {
        "schema_version": "1.0",
        "run_id": "phase1-code-check-engine",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "hf_csv": str(hf_csv),
            "capacity": {k: float(v) for k, v in sorted(capacity.items())},
            "combination_scales": [float(x) for x in combination_scales],
            "combination_family": str(effective_combination_family),
            "requested_combination_family": str(combination_family or ""),
            "combination_family_source": str(combination_family_source),
            "combination_limit_state": str(combination_limit_state),
            "max_dcr": float(max_dcr),
            "load_combination_model_present": bool(isinstance(load_combination_model, dict)),
        },
        "summary": {
            "case_count": int(len(per_case)),
            "member_count": int(len(member_ids_seen)),
            "combination_count": int(len(combo_library)),
            "combination_provenance_count": int(len(combination_provenance_rows)),
            "combination_row_count": int(len(combination_rows)),
            "derived_row_count": int(len(derived_rows)),
            "rc_rule_row_count": int(len(rc_rule_rows)),
            "steel_rule_row_count": int(len(steel_rule_rows)),
            "member_check_row_count": int(len(all_check_rows)),
            "serviceability_row_count": int(sum(1 for r in derived_rows if str(r.get("rule_family")) == "serviceability")),
            "stability_row_count": int(sum(1 for r in derived_rows if str(r.get("rule_family")) == "stability")),
            "interaction_row_count": int(sum(1 for r in derived_rows if str(r.get("rule_family")) == "strength_interaction")),
            "clause_count": int(len(clause_set)),
            "member_type_count": int(len(member_type_counts)),
            "governing_member_id": governing_member,
            "governing_case_id": governing_case,
            "governing_component": governing_component,
            "governing_scale": float(governing_scale),
            "governing_combination": governing_combo,
            "max_dcr": float(global_max_dcr),
            "member_type_counts": {k: int(v) for k, v in sorted(member_type_counts.items())},
        },
        "rows": per_case,
        "combination_rows": combination_rows,
        "combination_provenance_rows": combination_provenance_rows,
        "derived_rows": derived_rows,
        "rc_rule_rows": rc_rule_rows,
        "steel_rule_rows": steel_rule_rows,
        "member_check_rows": all_check_rows,
        "checks": {
            "max_dcr_pass": bool(contract_pass),
            "all_rows_finite": bool(all(float(r["max_dcr"]) == float(r["max_dcr"]) for r in per_case)),
            "combination_coverage_pass": bool(len(combination_rows) == len(per_case) * len(combo_library) * len(COMPONENTS)),
            "member_check_rows_min_pass": bool(len(all_check_rows) >= max(100, len(per_case) * len(COMPONENTS))),
            "clause_coverage_pass": bool(len(clause_set) >= 8),
            "rc_rule_rows_min_pass": bool(len(rc_rule_rows) >= max(4, len(per_case))),
            "steel_rule_rows_min_pass": bool(
                not steel_design_active
                or len(steel_rule_rows) >= max(3, steel_rule_target_count)
            ),
            "combination_provenance_pass": bool(
                not isinstance(load_combination_model, dict)
                or len(combination_provenance_rows) == len(combo_library)
            ),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-csv", default="implementation/phase1/commercial_hf_export_sample.csv")
    p.add_argument("--axial-capacity-kN", type=float, default=2200.0)
    p.add_argument("--shear-capacity-kN", type=float, default=380.0)
    p.add_argument("--moment-capacity-kNm", type=float, default=2600.0)
    p.add_argument("--combination-scales", default="1.0,1.2,1.4")
    p.add_argument("--combination-family", default="KDS-2022")
    p.add_argument("--combination-limit-state", default="ULS")
    p.add_argument("--load-comb-model-json", default="")
    p.add_argument("--max-dcr", type=float, default=1.0)
    p.add_argument("--out", default="implementation/phase1/release/kds_compliance/code_check_report.json")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = evaluate_code_compliance(
            hf_csv=Path(args.hf_csv),
            capacity={
                "axial_capacity_kN": float(args.axial_capacity_kN),
                "shear_capacity_kN": float(args.shear_capacity_kN),
                "moment_capacity_kNm": float(args.moment_capacity_kNm),
            },
            combination_scales=_parse_scales(str(args.combination_scales)),
            max_dcr=float(args.max_dcr),
            combination_family=str(args.combination_family),
            combination_limit_state=str(args.combination_limit_state),
            load_combination_model=(
                json.loads(Path(args.load_comb_model_json).read_text(encoding="utf-8"))
                if str(args.load_comb_model_json).strip()
                else None
            ),
        )
    except Exception as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-code-check-engine",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "hf_csv": str(args.hf_csv),
                "combination_scales": str(args.combination_scales),
                "max_dcr": float(args.max_dcr),
            },
            "contract_pass": False,
            "reason_code": "ERR_INPUT",
            "reason": f"{REASONS['ERR_INPUT']}: {exc}",
        }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote code check report: {out}")
    if not bool(report.get("contract_pass", False)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
