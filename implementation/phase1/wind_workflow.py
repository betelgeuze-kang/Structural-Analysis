#!/usr/bin/env python3
"""Deterministic wind workflow with exposure profile, load cases, and serviceability summary."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract


RUN_ID = "phase1-wind-workflow"
SCHEMA_VERSION = "1.0"
G = 9.80665

EXPOSURE_PRESETS: dict[str, dict[str, float]] = {
    "B": {"alpha": 7.0, "zg_m": 365.76, "min_kz": 0.70, "turbulence_intensity": 0.22},
    "C": {"alpha": 9.5, "zg_m": 274.32, "min_kz": 0.85, "turbulence_intensity": 0.18},
    "D": {"alpha": 11.5, "zg_m": 213.36, "min_kz": 1.03, "turbulence_intensity": 0.14},
}

SERIES_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "number", "exclusiveMinimum": 0.0},
        {
            "type": "array",
            "minItems": 1,
            "items": {"type": "number", "exclusiveMinimum": 0.0},
        },
    ]
}

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["site", "building"],
    "properties": {
        "site": {
            "type": "object",
            "additionalProperties": False,
            "required": ["basic_wind_speed_mps", "exposure"],
            "properties": {
                "basic_wind_speed_mps": {"type": "number", "exclusiveMinimum": 0.0},
                "exposure": {"type": "string", "enum": sorted(EXPOSURE_PRESETS)},
                "topographic_factor": {"type": "number", "exclusiveMinimum": 0.0},
                "directionality_factor": {"type": "number", "exclusiveMinimum": 0.0},
                "importance_factor": {"type": "number", "exclusiveMinimum": 0.0},
                "gust_factor": {"type": "number", "exclusiveMinimum": 0.0},
            },
        },
        "building": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "plan_dim_x_m",
                "plan_dim_y_m",
                "story_heights_m",
                "story_masses_t",
                "story_stiffness_kNpm",
                "fundamental_period_s",
                "damping_ratio",
            ],
            "properties": {
                "name": {"type": "string"},
                "story_count": {"type": "integer", "minimum": 1},
                "plan_dim_x_m": {"type": "number", "exclusiveMinimum": 0.0},
                "plan_dim_y_m": {"type": "number", "exclusiveMinimum": 0.0},
                "story_heights_m": SERIES_SCHEMA,
                "story_masses_t": SERIES_SCHEMA,
                "story_masses_top_t": {"type": "number", "exclusiveMinimum": 0.0},
                "story_stiffness_kNpm": SERIES_SCHEMA,
                "story_stiffness_top_kNpm": {"type": "number", "exclusiveMinimum": 0.0},
                "fundamental_period_s": {"type": "number", "exclusiveMinimum": 0.0},
                "damping_ratio": {"type": "number", "exclusiveMinimum": 0.0},
                "mode_shape_exponent": {"type": "number", "exclusiveMinimum": 0.0},
                "force_coefficient": {"type": "number", "exclusiveMinimum": 0.0},
                "across_wind_factor": {"type": "number", "exclusiveMinimum": 0.0},
                "strength_scale": {"type": "number", "exclusiveMinimum": 0.0},
                "service_scale": {"type": "number", "exclusiveMinimum": 0.0},
            },
        },
        "criteria": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "strength_drift_limit_ratio": {"type": "number", "exclusiveMinimum": 0.0},
                "service_drift_limit_ratio": {"type": "number", "exclusiveMinimum": 0.0},
                "peak_acceleration_limit_mg": {"type": "number", "exclusiveMinimum": 0.0},
                "rms_acceleration_limit_mg": {"type": "number", "exclusiveMinimum": 0.0},
            },
        },
    },
}

REASONS = {
    "PASS": "wind workflow completed and serviceability checks passed",
    "CHECK": "wind workflow completed with one or more serviceability exceedances",
    "ERR_INVALID_INPUT": "wind workflow input is invalid",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _positive_float(value: Any, label: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(out) or out <= 0.0:
        raise ValueError(f"{label} must be > 0")
    return out


def _int_count(value: Any, label: str) -> int:
    try:
        out = int(value)
    except Exception as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if out <= 0:
        raise ValueError(f"{label} must be >= 1")
    return out


def _expand_story_series(
    value: Any,
    count: int,
    *,
    label: str,
    top_value: Any | None = None,
) -> list[float]:
    if isinstance(value, list):
        if len(value) != count:
            raise ValueError(f"{label} must have {count} entries")
        return [_positive_float(item, f"{label}[{idx}]") for idx, item in enumerate(value)]
    start = _positive_float(value, label)
    if top_value is None:
        return [start for _ in range(count)]
    stop = _positive_float(top_value, f"{label}_top")
    if count == 1:
        return [start]
    return [
        start + (stop - start) * float(idx) / float(count - 1)
        for idx in range(count)
    ]


def _story_count_from_building(building: dict[str, Any]) -> int:
    count_raw = building.get("story_count")
    if count_raw is not None:
        count = _int_count(count_raw, "building.story_count")
        for key in ("story_heights_m", "story_masses_t", "story_stiffness_kNpm"):
            if isinstance(building.get(key), list) and len(building[key]) != count:
                raise ValueError(f"building.{key} length must match building.story_count")
        return count
    for key in ("story_heights_m", "story_masses_t", "story_stiffness_kNpm"):
        if isinstance(building.get(key), list):
            return len(building[key])
    raise ValueError("building.story_count is required when story inputs are scalar")


def _criteria_with_defaults(criteria: dict[str, Any] | None) -> dict[str, float]:
    src = criteria or {}
    return {
        "strength_drift_limit_ratio": _positive_float(src.get("strength_drift_limit_ratio", 0.020), "criteria.strength_drift_limit_ratio"),
        "service_drift_limit_ratio": _positive_float(src.get("service_drift_limit_ratio", 0.010), "criteria.service_drift_limit_ratio"),
        "peak_acceleration_limit_mg": _positive_float(src.get("peak_acceleration_limit_mg", 18.0), "criteria.peak_acceleration_limit_mg"),
        "rms_acceleration_limit_mg": _positive_float(src.get("rms_acceleration_limit_mg", 12.0), "criteria.rms_acceleration_limit_mg"),
    }


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_input_contract(payload, INPUT_SCHEMA, label="wind_workflow")

    site_raw = payload["site"]
    building_raw = payload["building"]
    count = _story_count_from_building(building_raw)
    exposure = str(site_raw["exposure"]).strip().upper()
    preset = EXPOSURE_PRESETS[exposure]

    story_heights_m = _expand_story_series(building_raw["story_heights_m"], count, label="building.story_heights_m")
    story_masses_t = _expand_story_series(
        building_raw["story_masses_t"],
        count,
        label="building.story_masses_t",
        top_value=building_raw.get("story_masses_top_t"),
    )
    story_stiffness_kNpm = _expand_story_series(
        building_raw["story_stiffness_kNpm"],
        count,
        label="building.story_stiffness_kNpm",
        top_value=building_raw.get("story_stiffness_top_kNpm"),
    )

    cumulative = 0.0
    story_mid_elevations_m: list[float] = []
    story_top_elevations_m: list[float] = []
    for height in story_heights_m:
        story_mid_elevations_m.append(cumulative + 0.5 * height)
        cumulative += height
        story_top_elevations_m.append(cumulative)
    roof_height_m = cumulative
    mode_shape_exponent = _positive_float(building_raw.get("mode_shape_exponent", 1.15), "building.mode_shape_exponent")
    mode_shape = [
        max(1.0e-6, math.pow(top / max(roof_height_m, 1.0e-6), mode_shape_exponent))
        for top in story_top_elevations_m
    ]
    total_mass_t = float(sum(story_masses_t))

    site = {
        "basic_wind_speed_mps": _positive_float(site_raw["basic_wind_speed_mps"], "site.basic_wind_speed_mps"),
        "exposure": exposure,
        "topographic_factor": _positive_float(site_raw.get("topographic_factor", 1.0), "site.topographic_factor"),
        "directionality_factor": _positive_float(site_raw.get("directionality_factor", 0.85), "site.directionality_factor"),
        "importance_factor": _positive_float(site_raw.get("importance_factor", 1.0), "site.importance_factor"),
        "gust_factor": _positive_float(site_raw.get("gust_factor", 0.85), "site.gust_factor"),
        "terrain_gradient_alpha": float(preset["alpha"]),
        "terrain_gradient_height_m": float(preset["zg_m"]),
        "min_kz": float(preset["min_kz"]),
        "turbulence_intensity": float(preset["turbulence_intensity"]),
    }
    building = {
        "name": str(building_raw.get("name", "tower") or "tower"),
        "story_count": int(count),
        "plan_dim_x_m": _positive_float(building_raw["plan_dim_x_m"], "building.plan_dim_x_m"),
        "plan_dim_y_m": _positive_float(building_raw["plan_dim_y_m"], "building.plan_dim_y_m"),
        "story_heights_m": story_heights_m,
        "story_masses_t": story_masses_t,
        "story_stiffness_kNpm": story_stiffness_kNpm,
        "story_mid_elevations_m": story_mid_elevations_m,
        "story_top_elevations_m": story_top_elevations_m,
        "roof_height_m": roof_height_m,
        "total_mass_t": total_mass_t,
        "fundamental_period_s": _positive_float(building_raw["fundamental_period_s"], "building.fundamental_period_s"),
        "damping_ratio": _positive_float(building_raw["damping_ratio"], "building.damping_ratio"),
        "mode_shape_exponent": mode_shape_exponent,
        "mode_shape": mode_shape,
        "force_coefficient": _positive_float(building_raw.get("force_coefficient", 1.30), "building.force_coefficient"),
        "across_wind_factor": _positive_float(building_raw.get("across_wind_factor", 1.20), "building.across_wind_factor"),
        "strength_scale": _positive_float(building_raw.get("strength_scale", 1.00), "building.strength_scale"),
        "service_scale": _positive_float(building_raw.get("service_scale", 0.70), "building.service_scale"),
    }
    criteria = _criteria_with_defaults(payload.get("criteria"))
    return {"site": site, "building": building, "criteria": criteria}


def _velocity_pressure_kpa(site: dict[str, Any], z_m: float) -> tuple[float, float]:
    z_eff = max(4.57, float(z_m))
    alpha = float(site["terrain_gradient_alpha"])
    zg_m = float(site["terrain_gradient_height_m"])
    min_kz = float(site["min_kz"])
    kz = max(min_kz, 2.01 * math.pow(min(z_eff, zg_m) / zg_m, 2.0 / alpha))
    qz_kpa = (
        0.000613
        * float(site["basic_wind_speed_mps"]) ** 2
        * kz
        * float(site["topographic_factor"])
        * float(site["directionality_factor"])
        * float(site["importance_factor"])
    )
    return float(kz), float(qz_kpa)


def _build_story_profile_from_normalized(workflow: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    site = workflow["site"]
    building = workflow["building"]
    count = int(building["story_count"])
    profile: list[dict[str, Any]] = []
    roof_qz = 0.0
    roof_kz = 0.0
    service_ratio = float(building["service_scale"]) / max(float(building["strength_scale"]), 1.0e-9)

    for idx in range(count):
        story = idx + 1
        height_m = float(building["story_heights_m"][idx])
        elevation_m = float(building["story_mid_elevations_m"][idx])
        mode_shape = float(building["mode_shape"][idx])
        kz, qz_kpa = _velocity_pressure_kpa(site, elevation_m)
        roof_kz = kz
        roof_qz = qz_kpa
        projected_area_x_m2 = height_m * float(building["plan_dim_x_m"])
        projected_area_y_m2 = height_m * float(building["plan_dim_y_m"])
        shape_factor = 0.85 + 0.35 * mode_shape
        force_x_strength_kN = qz_kpa * projected_area_x_m2 * float(site["gust_factor"]) * float(building["force_coefficient"]) * float(building["strength_scale"]) * shape_factor
        force_y_strength_kN = (
            qz_kpa
            * projected_area_y_m2
            * float(site["gust_factor"])
            * float(building["force_coefficient"])
            * float(building["strength_scale"])
            * float(building["across_wind_factor"])
            * shape_factor
        )
        row = {
            "story": story,
            "story_label": f"L{story:02d}",
            "height_m": height_m,
            "elevation_m": elevation_m,
            "top_elevation_m": float(building["story_top_elevations_m"][idx]),
            "story_mass_t": float(building["story_masses_t"][idx]),
            "story_stiffness_kNpm": float(building["story_stiffness_kNpm"][idx]),
            "mode_shape": mode_shape,
            "kz": kz,
            "qz_kpa": qz_kpa,
            "projected_area_x_m2": projected_area_x_m2,
            "projected_area_y_m2": projected_area_y_m2,
            "strength_force_x_kN": force_x_strength_kN,
            "strength_force_y_kN": force_y_strength_kN,
            "service_force_x_kN": force_x_strength_kN * service_ratio,
            "service_force_y_kN": force_y_strength_kN * service_ratio,
        }
        profile.append(row)

    site_summary = {
        "exposure": str(site["exposure"]),
        "terrain_gradient_alpha": float(site["terrain_gradient_alpha"]),
        "terrain_gradient_height_m": float(site["terrain_gradient_height_m"]),
        "turbulence_intensity": float(site["turbulence_intensity"]),
        "roof_kz": float(roof_kz),
        "roof_velocity_pressure_kpa": float(roof_qz),
        "roof_height_m": float(building["roof_height_m"]),
    }
    return profile, site_summary


def build_story_wind_profile(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the story-by-story wind profile for a normalized building/site payload."""
    workflow = _normalize_payload(payload)
    profile, _ = _build_story_profile_from_normalized(workflow)
    return profile


def _case_response(
    workflow: dict[str, Any],
    *,
    case_id: str,
    direction: str,
    limit_state: str,
    sign: int,
    story_forces_kN: list[float],
) -> dict[str, Any]:
    building = workflow["building"]
    site = workflow["site"]
    heights = [float(value) for value in building["story_heights_m"]]
    elevations = [float(value) for value in building["story_mid_elevations_m"]]
    stiffness = [float(value) for value in building["story_stiffness_kNpm"]]
    mode_shape = [float(value) for value in building["mode_shape"]]
    masses_kg = [float(value) * 1000.0 for value in building["story_masses_t"]]

    signed_story_forces = [float(sign) * abs(force) for force in story_forces_kN]
    story_shears: list[float] = [0.0 for _ in signed_story_forces]
    running = 0.0
    for idx in range(len(signed_story_forces) - 1, -1, -1):
        running += signed_story_forces[idx]
        story_shears[idx] = running

    story_drifts_m = [story_shears[idx] / max(stiffness[idx], 1.0e-9) for idx in range(len(story_shears))]
    floor_displacements_m: list[float] = []
    displacement = 0.0
    for drift in story_drifts_m:
        displacement += drift
        floor_displacements_m.append(displacement)

    drift_ratios = [abs(story_drifts_m[idx]) / max(heights[idx], 1.0e-9) for idx in range(len(story_drifts_m))]
    roof_drift_ratio = abs(floor_displacements_m[-1]) / max(float(building["roof_height_m"]), 1.0e-9)
    base_shear_kN = abs(story_shears[0]) if story_shears else 0.0
    overturning_moment_kNm = abs(sum(signed_story_forces[idx] * elevations[idx] for idx in range(len(signed_story_forces))))

    total_mass_kg = max(sum(masses_kg), 1.0e-9)
    modal_mass = max(sum(masses_kg[idx] * mode_shape[idx] ** 2 for idx in range(len(masses_kg))), 1.0e-9)
    modal_sum = sum(masses_kg[idx] * mode_shape[idx] for idx in range(len(masses_kg)))
    effective_mass_ratio = min(0.95, max(0.30, (modal_sum * modal_sum) / (total_mass_kg * modal_mass)))
    weighted_mode = sum(abs(signed_story_forces[idx]) * mode_shape[idx] for idx in range(len(signed_story_forces))) / max(
        sum(abs(force) for force in signed_story_forces),
        1.0e-9,
    )

    base_accel_mps2 = base_shear_kN * 1000.0 / total_mass_kg
    participation_modifier = 0.45 + 0.55 * effective_mass_ratio
    period_modifier = min(1.50, 0.75 + 0.10 * float(building["fundamental_period_s"]))
    damping_modifier = min(1.60, max(0.70, math.sqrt(0.02 / max(float(building["damping_ratio"]), 1.0e-6))))
    turbulence_modifier = 0.90 + 1.20 * float(site["turbulence_intensity"])
    direction_modifier = 1.00 if direction == "X" else 1.00 + 0.10 * max(float(building["across_wind_factor"]) - 1.0, 0.0)
    state_modifier = 1.05 if limit_state == "service" else 0.95
    shape_modifier = 0.75 + 0.20 * weighted_mode
    peak_top_accel_mps2 = (
        base_accel_mps2
        * participation_modifier
        * period_modifier
        * damping_modifier
        * turbulence_modifier
        * direction_modifier
        * state_modifier
        * shape_modifier
    )
    rms_top_accel_mps2 = peak_top_accel_mps2 / max(2.60 + 0.60 * effective_mass_ratio, 1.0)

    max_story_drift_ratio = max(drift_ratios) if drift_ratios else 0.0
    governing_story = 1 + max(range(len(drift_ratios)), key=drift_ratios.__getitem__) if drift_ratios else 0
    return {
        "case_id": case_id,
        "direction": direction,
        "limit_state": limit_state,
        "sign": int(sign),
        "base_shear_kN": float(base_shear_kN),
        "overturning_moment_kNm": float(overturning_moment_kNm),
        "max_story_drift_ratio": float(max_story_drift_ratio),
        "roof_drift_ratio": float(roof_drift_ratio),
        "governing_story": int(governing_story),
        "top_peak_acceleration_mg": float(peak_top_accel_mps2 / G * 1000.0),
        "top_rms_acceleration_mg": float(rms_top_accel_mps2 / G * 1000.0),
        "modal_effective_mass_ratio": float(effective_mass_ratio),
        "story_forces_kN": signed_story_forces,
        "story_shears_kN": story_shears,
        "story_drifts_m": story_drifts_m,
        "story_drift_ratios": drift_ratios,
        "floor_displacements_m": floor_displacements_m,
    }


def _generate_load_cases_from_normalized(
    workflow: dict[str, Any],
    story_profile: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for limit_state, prefix in (("strength", "W_STR"), ("service", "W_SVC")):
        for direction in ("X", "Y"):
            key = f"{limit_state}_force_{direction.lower()}_kN"
            story_forces = [float(row[key]) for row in story_profile]
            for sign, suffix in ((1, "POS"), (-1, "NEG")):
                cases.append(
                    _case_response(
                        workflow,
                        case_id=f"{prefix}_{direction}_{suffix}",
                        direction=direction,
                        limit_state=limit_state,
                        sign=sign,
                        story_forces_kN=story_forces,
                    )
                )
    return cases


def generate_wind_load_cases(
    payload: dict[str, Any],
    story_profile: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return directional strength/service wind cases for the input payload."""
    workflow = _normalize_payload(payload)
    profile = story_profile if story_profile is not None else _build_story_profile_from_normalized(workflow)[0]
    return _generate_load_cases_from_normalized(workflow, profile)


def _governing_case(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    if not cases:
        return {}
    return max(cases, key=lambda row: float(row.get(key, 0.0) or 0.0))


def _comfort_class(utilization: float) -> str:
    ratio = max(float(utilization), 0.0)
    if ratio < 0.40:
        return "calm"
    if ratio < 0.70:
        return "acceptable"
    if ratio < 0.90:
        return "perceptible"
    if ratio < 1.00:
        return "attention"
    return "exceedance"


def _build_occupant_comfort_summary(
    service_cases: list[dict[str, Any]],
    criteria: dict[str, float],
) -> dict[str, Any]:
    case_rows: list[dict[str, Any]] = []
    for case in service_cases:
        peak_mg = float(case.get("top_peak_acceleration_mg", 0.0) or 0.0)
        rms_mg = float(case.get("top_rms_acceleration_mg", 0.0) or 0.0)
        peak_utilization = peak_mg / max(float(criteria["peak_acceleration_limit_mg"]), 1.0e-9)
        rms_utilization = rms_mg / max(float(criteria["rms_acceleration_limit_mg"]), 1.0e-9)
        governing_utilization = max(peak_utilization, rms_utilization)
        motion_sensitivity_index = math.sqrt(max(peak_utilization * rms_utilization, 0.0))
        case_rows.append(
            {
                "case_id": str(case.get("case_id", "")),
                "direction": str(case.get("direction", "")),
                "peak_acceleration_mg": float(peak_mg),
                "rms_acceleration_mg": float(rms_mg),
                "peak_utilization": float(peak_utilization),
                "rms_utilization": float(rms_utilization),
                "governing_utilization": float(governing_utilization),
                "comfort_class": _comfort_class(governing_utilization),
                "motion_sensitivity_index": float(motion_sensitivity_index),
            }
        )

    governing = max(
        case_rows,
        key=lambda row: (float(row["governing_utilization"]), float(row["motion_sensitivity_index"]), str(row["case_id"])),
    ) if case_rows else {
        "case_id": "",
        "direction": "",
        "peak_acceleration_mg": 0.0,
        "rms_acceleration_mg": 0.0,
        "peak_utilization": 0.0,
        "rms_utilization": 0.0,
        "governing_utilization": 0.0,
        "comfort_class": "calm",
        "motion_sensitivity_index": 0.0,
    }
    direction_peak = {
        direction: max(
            (float(row.get("peak_acceleration_mg", 0.0) or 0.0) for row in case_rows if row.get("direction") == direction),
            default=0.0,
        )
        for direction in ("X", "Y")
    }
    crosswind_bias_ratio = direction_peak["Y"] / max(direction_peak["X"], 1.0e-9)
    return {
        "case_rows": case_rows,
        "overall_class": str(governing["comfort_class"]),
        "governing_case_id": str(governing["case_id"]),
        "governing_direction": str(governing["direction"]),
        "governing_peak_acceleration_mg": float(governing["peak_acceleration_mg"]),
        "governing_rms_acceleration_mg": float(governing["rms_acceleration_mg"]),
        "governing_utilization": float(governing["governing_utilization"]),
        "motion_sensitivity_index": float(governing["motion_sensitivity_index"]),
        "peak_reserve_mg": float(criteria["peak_acceleration_limit_mg"]) - float(governing["peak_acceleration_mg"]),
        "rms_reserve_mg": float(criteria["rms_acceleration_limit_mg"]) - float(governing["rms_acceleration_mg"]),
        "crosswind_bias_ratio": float(crosswind_bias_ratio),
    }


def run_wind_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the wind workflow and return a JSON-serializable report payload."""
    workflow = _normalize_payload(payload)
    profile, site_summary = _build_story_profile_from_normalized(workflow)
    cases = _generate_load_cases_from_normalized(workflow, profile)
    criteria = workflow["criteria"]
    building = workflow["building"]

    strength_cases = [case for case in cases if case["limit_state"] == "strength"]
    service_cases = [case for case in cases if case["limit_state"] == "service"]
    strength_drift_case = _governing_case(strength_cases, "max_story_drift_ratio")
    service_drift_case = _governing_case(service_cases, "max_story_drift_ratio")
    service_peak_case = _governing_case(service_cases, "top_peak_acceleration_mg")
    service_rms_case = _governing_case(service_cases, "top_rms_acceleration_mg")

    strength_drift = float(strength_drift_case.get("max_story_drift_ratio", 0.0))
    service_drift = float(service_drift_case.get("max_story_drift_ratio", 0.0))
    peak_accel = float(service_peak_case.get("top_peak_acceleration_mg", 0.0))
    rms_accel = float(service_rms_case.get("top_rms_acceleration_mg", 0.0))
    occupant_comfort = _build_occupant_comfort_summary(service_cases, criteria)

    checks = {
        "story_profile_complete": bool(len(profile) == int(building["story_count"])),
        "load_cases_generated": bool(len(cases) == 8),
        "strength_drift_within_limit": bool(strength_drift <= float(criteria["strength_drift_limit_ratio"])),
        "service_drift_within_limit": bool(service_drift <= float(criteria["service_drift_limit_ratio"])),
        "peak_acceleration_within_limit": bool(peak_accel <= float(criteria["peak_acceleration_limit_mg"])),
        "rms_acceleration_within_limit": bool(rms_accel <= float(criteria["rms_acceleration_limit_mg"])),
    }
    checks["serviceability_pass"] = bool(
        checks["strength_drift_within_limit"]
        and checks["service_drift_within_limit"]
        and checks["peak_acceleration_within_limit"]
        and checks["rms_acceleration_within_limit"]
    )

    utilizations = [
        {
            "metric": "service_story_drift_ratio",
            "value": service_drift,
            "limit": float(criteria["service_drift_limit_ratio"]),
            "case_id": str(service_drift_case.get("case_id", "")),
        },
        {
            "metric": "peak_acceleration_mg",
            "value": peak_accel,
            "limit": float(criteria["peak_acceleration_limit_mg"]),
            "case_id": str(service_peak_case.get("case_id", "")),
        },
        {
            "metric": "rms_acceleration_mg",
            "value": rms_accel,
            "limit": float(criteria["rms_acceleration_limit_mg"]),
            "case_id": str(service_rms_case.get("case_id", "")),
        },
    ]
    governing = max(
        utilizations,
        key=lambda row: float(row["value"]) / max(float(row["limit"]), 1.0e-9),
    )
    status = "PASS" if checks["serviceability_pass"] else "CHECK"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": workflow,
        "site_summary": site_summary,
        "story_profile": profile,
        "load_cases": cases,
        "drift_summary": {
            "strength_governing_case_id": str(strength_drift_case.get("case_id", "")),
            "strength_governing_story": int(strength_drift_case.get("governing_story", 0) or 0),
            "strength_max_story_drift_ratio": strength_drift,
            "strength_roof_drift_ratio": float(strength_drift_case.get("roof_drift_ratio", 0.0)),
            "service_governing_case_id": str(service_drift_case.get("case_id", "")),
            "service_governing_story": int(service_drift_case.get("governing_story", 0) or 0),
            "service_max_story_drift_ratio": service_drift,
            "service_roof_drift_ratio": float(service_drift_case.get("roof_drift_ratio", 0.0)),
        },
        "acceleration_summary": {
            "governing_peak_case_id": str(service_peak_case.get("case_id", "")),
            "governing_rms_case_id": str(service_rms_case.get("case_id", "")),
            "top_peak_acceleration_mg": peak_accel,
            "top_rms_acceleration_mg": rms_accel,
            "modal_effective_mass_ratio": float(service_peak_case.get("modal_effective_mass_ratio", 0.0)),
        },
        "serviceability": {
            "status": status,
            "governing_metric": str(governing["metric"]),
            "governing_case_id": str(governing["case_id"]),
            "governing_value": float(governing["value"]),
            "governing_limit": float(governing["limit"]),
            "governing_utilization": float(governing["value"]) / max(float(governing["limit"]), 1.0e-9),
        },
        "occupant_comfort": occupant_comfort,
        "checks": checks,
        "summary": {
            "building_name": str(building["name"]),
            "story_count": int(building["story_count"]),
            "roof_height_m": float(building["roof_height_m"]),
            "total_mass_t": float(building["total_mass_t"]),
            "load_case_count": int(len(cases)),
            "base_shear_strength_x_kN": float(_governing_case([case for case in strength_cases if case["direction"] == "X"], "base_shear_kN").get("base_shear_kN", 0.0)),
            "base_shear_strength_y_kN": float(_governing_case([case for case in strength_cases if case["direction"] == "Y"], "base_shear_kN").get("base_shear_kN", 0.0)),
            "max_story_drift_ratio_strength": strength_drift,
            "max_story_drift_ratio_service": service_drift,
            "top_peak_acceleration_mg": peak_accel,
            "top_rms_acceleration_mg": rms_accel,
            "serviceability_status": status,
            "occupant_comfort_class": str(occupant_comfort["overall_class"]),
            "occupant_comfort_governing_case_id": str(occupant_comfort["governing_case_id"]),
            "occupant_comfort_crosswind_bias_ratio": float(occupant_comfort["crosswind_bias_ratio"]),
        },
        "contract_pass": True,
        "reason_code": status,
        "reason": REASONS[status],
    }
    report["summary_line"] = (
        f"Wind workflow: {status} | exposure={site_summary['exposure']} | "
        f"stories={int(building['story_count'])} | "
        f"base_shear_y={report['summary']['base_shear_strength_y_kN']:.1f}kN | "
        f"drift={service_drift:.4f}/{criteria['service_drift_limit_ratio']:.4f} | "
        f"accel={peak_accel:.1f}/{criteria['peak_acceleration_limit_mg']:.1f}mg | "
        f"comfort={occupant_comfort['overall_class']} | "
        f"cases={len(cases)}"
    )
    return report


def _parse_csv_floats(raw: str) -> list[float] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    values = [item.strip() for item in text.split(",")]
    return [_positive_float(item, "csv_value") for item in values if item]


def _payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    story_heights = _parse_csv_floats(args.story_heights_m)
    story_masses = _parse_csv_floats(args.story_masses_t)
    story_stiffness = _parse_csv_floats(args.story_stiffness_kNpm)
    building: dict[str, Any] = {
        "name": str(args.name),
        "story_count": int(args.story_count),
        "plan_dim_x_m": float(args.plan_dim_x_m),
        "plan_dim_y_m": float(args.plan_dim_y_m),
        "story_heights_m": story_heights if story_heights is not None else float(args.story_height_m),
        "story_masses_t": story_masses if story_masses is not None else float(args.story_mass_t),
        "story_stiffness_kNpm": story_stiffness if story_stiffness is not None else float(args.stiffness_base_kNpm),
        "fundamental_period_s": float(args.fundamental_period_s),
        "damping_ratio": float(args.damping_ratio),
        "mode_shape_exponent": float(args.mode_shape_exponent),
        "force_coefficient": float(args.force_coefficient),
        "across_wind_factor": float(args.across_wind_factor),
        "strength_scale": float(args.strength_scale),
        "service_scale": float(args.service_scale),
    }
    if story_stiffness is None:
        building["story_stiffness_top_kNpm"] = float(args.stiffness_top_kNpm)
    payload = {
        "site": {
            "basic_wind_speed_mps": float(args.basic_wind_speed_mps),
            "exposure": str(args.exposure).upper(),
            "topographic_factor": float(args.topographic_factor),
            "directionality_factor": float(args.directionality_factor),
            "importance_factor": float(args.importance_factor),
            "gust_factor": float(args.gust_factor),
        },
        "building": building,
        "criteria": {
            "strength_drift_limit_ratio": float(args.strength_drift_limit_ratio),
            "service_drift_limit_ratio": float(args.service_drift_limit_ratio),
            "peak_acceleration_limit_mg": float(args.peak_acceleration_limit_mg),
            "rms_acceleration_limit_mg": float(args.rms_acceleration_limit_mg),
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="tower")
    parser.add_argument("--basic-wind-speed-mps", type=float, default=44.0)
    parser.add_argument("--exposure", default="C")
    parser.add_argument("--topographic-factor", type=float, default=1.0)
    parser.add_argument("--directionality-factor", type=float, default=0.85)
    parser.add_argument("--importance-factor", type=float, default=1.0)
    parser.add_argument("--gust-factor", type=float, default=0.85)
    parser.add_argument("--story-count", type=int, default=20)
    parser.add_argument("--story-height-m", type=float, default=4.0)
    parser.add_argument("--story-heights-m", default="")
    parser.add_argument("--plan-dim-x-m", type=float, default=36.0)
    parser.add_argument("--plan-dim-y-m", type=float, default=28.0)
    parser.add_argument("--story-mass-t", type=float, default=1200.0)
    parser.add_argument("--story-masses-t", default="")
    parser.add_argument("--story-stiffness-kNpm", default="")
    parser.add_argument("--stiffness-base-kNpm", type=float, default=850000.0)
    parser.add_argument("--stiffness-top-kNpm", type=float, default=420000.0)
    parser.add_argument("--fundamental-period-s", type=float, default=4.2)
    parser.add_argument("--damping-ratio", type=float, default=0.02)
    parser.add_argument("--mode-shape-exponent", type=float, default=1.15)
    parser.add_argument("--force-coefficient", type=float, default=1.30)
    parser.add_argument("--across-wind-factor", type=float, default=1.20)
    parser.add_argument("--strength-scale", type=float, default=1.00)
    parser.add_argument("--service-scale", type=float, default=0.70)
    parser.add_argument("--strength-drift-limit-ratio", type=float, default=0.020)
    parser.add_argument("--service-drift-limit-ratio", type=float, default=0.010)
    parser.add_argument("--peak-acceleration-limit-mg", type=float, default=18.0)
    parser.add_argument("--rms-acceleration-limit-mg", type=float, default=12.0)
    parser.add_argument("--out", default="implementation/phase1/wind_workflow_report.json")
    args = parser.parse_args()

    out_path = Path(args.out)
    try:
        report = run_wind_workflow(_payload_from_args(args))
        report["artifacts"] = {"report_json": str(out_path)}
        _write_json(out_path, report)
        print(f"Wrote wind workflow report: {out_path}")
    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        _write_json(out_path, payload)
        print(f"Wrote wind workflow report: {out_path}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
