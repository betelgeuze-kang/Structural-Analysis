#!/usr/bin/env python3
"""Reduced-order advanced SSI workflow for layered soil and grouped foundations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    from implementation.phase1.runtime_contracts import InputContractError, validate_input_contract
except ImportError:  # pragma: no cover - direct script execution fallback
    from runtime_contracts import InputContractError, validate_input_contract


G = 9.80665
DEFAULT_OUT = Path("implementation/phase1/advanced_ssi_report.json")

REASONS = {
    "PASS": "advanced reduced-order SSI workflow completed with finite impedance, transfer, and amplification summaries",
    "ERR_INVALID_INPUT": "invalid advanced SSI input",
    "ERR_SSI_NUMERICS": "advanced SSI numerical checks failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["soil_profile", "foundation_groups"],
    "properties": {
        "soil_profile": {
            "type": "object",
            "additionalProperties": False,
            "required": ["profile_id", "layers"],
            "properties": {
                "profile_id": {"type": "string", "minLength": 1},
                "groundwater_depth_m": {"type": "number", "minimum": 0.0},
                "layers": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "layer_id",
                            "thickness_m",
                            "density_kg_m3",
                            "shear_wave_velocity_m_s",
                            "damping_ratio",
                            "poisson_ratio",
                        ],
                        "properties": {
                            "layer_id": {"type": "string", "minLength": 1},
                            "thickness_m": {"type": "number", "exclusiveMinimum": 0.0},
                            "density_kg_m3": {"type": "number", "exclusiveMinimum": 0.0},
                            "shear_wave_velocity_m_s": {"type": "number", "exclusiveMinimum": 0.0},
                            "damping_ratio": {"type": "number", "minimum": 0.0, "maximum": 0.35},
                            "poisson_ratio": {"type": "number", "minimum": 0.0, "maximum": 0.49},
                        },
                    },
                },
            },
        },
        "foundation_groups": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "group_id",
                    "foundation_type",
                    "count",
                    "length_m",
                    "width_m",
                    "embedment_m",
                    "mass_tonnes",
                    "structure_period_s",
                ],
                "properties": {
                    "group_id": {"type": "string", "minLength": 1},
                    "foundation_type": {"type": "string", "minLength": 1},
                    "count": {"type": "integer", "minimum": 1},
                    "length_m": {"type": "number", "exclusiveMinimum": 0.0},
                    "width_m": {"type": "number", "exclusiveMinimum": 0.0},
                    "embedment_m": {"type": "number", "minimum": 0.0},
                    "mass_tonnes": {"type": "number", "exclusiveMinimum": 0.0},
                    "structure_period_s": {"type": "number", "exclusiveMinimum": 0.0},
                    "structural_damping_ratio": {"type": "number", "minimum": 0.0, "maximum": 0.3},
                    "base_shear_share": {"type": "number", "minimum": 0.0},
                },
            },
        },
        "hazard": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "dominant_frequency_hz": {"type": "number", "exclusiveMinimum": 0.0},
                "pga_g": {"type": "number", "minimum": 0.0},
            },
        },
        "frequency_grid": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "f_min_hz": {"type": "number", "exclusiveMinimum": 0.0},
                "f_max_hz": {"type": "number", "exclusiveMinimum": 0.0},
                "f_count": {"type": "integer", "minimum": 16},
                "reference_frequency_hz": {"type": "number", "exclusiveMinimum": 0.0},
            },
        },
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("advanced SSI input must be a JSON object")
    return payload


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _clip(value: float, lower: float, upper: float) -> float:
    return float(min(max(value, lower), upper))


def _profile_depth(layers: list[dict[str, Any]]) -> float:
    return float(sum(_safe_float(layer.get("thickness_m"), 0.0) for layer in layers))


def _vs30(layers: list[dict[str, Any]]) -> float:
    remaining = 30.0
    travel_time = 0.0
    last_vs = 0.0
    for layer in layers:
        thickness = _safe_float(layer.get("thickness_m"), 0.0)
        vs = _safe_float(layer.get("shear_wave_velocity_m_s"), 0.0)
        if thickness <= 0.0 or vs <= 0.0 or remaining <= 0.0:
            continue
        use = min(thickness, remaining)
        travel_time += use / max(vs, 1.0e-9)
        remaining -= use
        last_vs = vs
    if remaining > 0.0 and last_vs > 0.0:
        travel_time += remaining / last_vs
        remaining = 0.0
    return 30.0 / max(travel_time, 1.0e-9) if remaining <= 1.0e-9 else 0.0


def _annotate_layers(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    depth_top = 0.0
    for layer in layers:
        thickness = _safe_float(layer.get("thickness_m"), 0.0)
        density = _safe_float(layer.get("density_kg_m3"), 0.0)
        vs = _safe_float(layer.get("shear_wave_velocity_m_s"), 0.0)
        damping = _safe_float(layer.get("damping_ratio"), 0.0)
        nu = _safe_float(layer.get("poisson_ratio"), 0.0)
        shear_modulus = density * vs * vs
        annotated.append(
            {
                "layer_id": str(layer.get("layer_id", "")).strip(),
                "thickness_m": thickness,
                "depth_top_m": depth_top,
                "depth_bottom_m": depth_top + thickness,
                "density_kg_m3": density,
                "shear_wave_velocity_m_s": vs,
                "damping_ratio": damping,
                "poisson_ratio": nu,
                "shear_modulus_mpa": shear_modulus / 1.0e6,
            }
        )
        depth_top += thickness
    return annotated


def _layer_overlap(top: float, bottom: float, depth: float) -> float:
    return max(0.0, min(bottom, depth) - top)


def _effective_soil_properties(
    layers: list[dict[str, Any]],
    *,
    influence_depth_m: float,
) -> dict[str, Any]:
    used_layers: list[dict[str, Any]] = []
    total = 0.0
    inv_vs_sum = 0.0
    density_sum = 0.0
    damping_sum = 0.0
    nu_sum = 0.0
    shear_modulus_sum = 0.0
    vs_values: list[float] = []
    for layer in layers:
        overlap = _layer_overlap(
            _safe_float(layer.get("depth_top_m")),
            _safe_float(layer.get("depth_bottom_m")),
            influence_depth_m,
        )
        if overlap <= 0.0:
            continue
        density = _safe_float(layer.get("density_kg_m3"))
        vs = _safe_float(layer.get("shear_wave_velocity_m_s"))
        damping = _safe_float(layer.get("damping_ratio"))
        nu = _safe_float(layer.get("poisson_ratio"))
        shear_modulus = density * vs * vs
        total += overlap
        inv_vs_sum += overlap / max(vs, 1.0e-9)
        density_sum += overlap * density
        damping_sum += overlap * damping
        nu_sum += overlap * nu
        shear_modulus_sum += overlap * shear_modulus
        vs_values.append(vs)
        used_layers.append(
            {
                "layer_id": str(layer.get("layer_id", "")).strip(),
                "used_thickness_m": overlap,
                "weight_ratio": 0.0,
            }
        )
    if total <= 0.0:
        raise ValueError("no soil layers intersect the influence depth")
    for row in used_layers:
        row["weight_ratio"] = round(_safe_float(row.get("used_thickness_m")) / total, 6)
    eq_vs = total / max(inv_vs_sum, 1.0e-9)
    eq_density = density_sum / total
    eq_damping = damping_sum / total
    eq_nu = nu_sum / total
    eq_shear_modulus = shear_modulus_sum / total
    stratification_ratio = max(vs_values) / max(min(vs_values), 1.0e-9)
    return {
        "influence_depth_m": float(influence_depth_m),
        "equivalent_shear_wave_velocity_m_s": float(eq_vs),
        "equivalent_density_kg_m3": float(eq_density),
        "equivalent_damping_ratio": float(eq_damping),
        "equivalent_poisson_ratio": float(eq_nu),
        "equivalent_shear_modulus_mpa": float(eq_shear_modulus / 1.0e6),
        "stratification_ratio": float(stratification_ratio),
        "contributing_layers": used_layers,
    }


def _foundation_equivalent_radius(group: dict[str, Any]) -> float:
    length = _safe_float(group.get("length_m"))
    width = _safe_float(group.get("width_m"))
    return math.sqrt(max(length * width, 1.0e-12) / math.pi)


def _frequency_grid(payload: dict[str, Any]) -> tuple[np.ndarray, float]:
    freq_cfg = payload.get("frequency_grid") if isinstance(payload.get("frequency_grid"), dict) else {}
    f_min = _safe_float(freq_cfg.get("f_min_hz"), 0.4)
    f_max = _safe_float(freq_cfg.get("f_max_hz"), 12.0)
    f_count = _safe_int(freq_cfg.get("f_count"), 48)
    ref_hz = _safe_float(freq_cfg.get("reference_frequency_hz"), 3.0)
    if f_min <= 0.0 or f_max <= f_min or f_count < 16 or ref_hz <= 0.0:
        raise ValueError("invalid frequency_grid settings")
    return np.linspace(f_min, f_max, f_count, dtype=np.float64), ref_hz


def _hazard_settings(payload: dict[str, Any]) -> tuple[float, float]:
    hazard = payload.get("hazard") if isinstance(payload.get("hazard"), dict) else {}
    dominant_frequency_hz = _safe_float(hazard.get("dominant_frequency_hz"), 2.5)
    pga_g = _safe_float(hazard.get("pga_g"), 0.28)
    if dominant_frequency_hz <= 0.0 or pga_g < 0.0:
        raise ValueError("invalid hazard settings")
    return dominant_frequency_hz, pga_g


def _coupled_impedance_curves(
    *,
    freq_hz: np.ndarray,
    soil: dict[str, Any],
    group: dict[str, Any],
    ref_hz: float,
) -> dict[str, Any]:
    radius = _foundation_equivalent_radius(group)
    area = math.pi * radius * radius
    eq_density = _safe_float(soil.get("equivalent_density_kg_m3"))
    eq_vs = _safe_float(soil.get("equivalent_shear_wave_velocity_m_s"))
    eq_nu = _clip(_safe_float(soil.get("equivalent_poisson_ratio"), 0.3), 0.05, 0.48)
    eq_damping = _clip(_safe_float(soil.get("equivalent_damping_ratio"), 0.05), 0.01, 0.20)
    stratification_ratio = max(_safe_float(soil.get("stratification_ratio"), 1.0), 1.0)
    embedment_m = _safe_float(group.get("embedment_m"))
    aspect_ratio = max(_safe_float(group.get("length_m")) / max(_safe_float(group.get("width_m")), 1.0e-9), 1.0)
    mass_tonnes = _safe_float(group.get("mass_tonnes"))
    structure_period_s = _safe_float(group.get("structure_period_s"))
    structural_damping_ratio = _clip(_safe_float(group.get("structural_damping_ratio"), 0.05), 0.02, 0.18)
    count = max(_safe_int(group.get("count"), 1), 1)

    shear_modulus = eq_density * eq_vs * eq_vs
    vp = eq_vs * math.sqrt(max(2.0 * (1.0 - eq_nu) / max(1.0 - 2.0 * eq_nu, 1.0e-6), 1.01))
    embedment_factor = 1.0 + 0.18 * min(embedment_m / max(radius, 1.0e-9), 2.0)
    compliance_divisor = 2.2 + 0.4 * aspect_ratio + 0.35 * stratification_ratio + 0.25 * embedment_factor
    static_k_horizontal = (8.0 * shear_modulus * radius / max(2.0 - eq_nu, 1.0e-6)) * embedment_factor / compliance_divisor
    static_k_vertical = (4.0 * shear_modulus * radius / max(1.0 - eq_nu, 1.0e-6)) * embedment_factor / (
        0.9 * compliance_divisor
    )
    static_k_rocking = (
        (8.0 * shear_modulus * radius**3 / max(3.0 * (1.0 - eq_nu), 1.0e-6)) * embedment_factor / (1.1 * compliance_divisor)
    )

    modal_mass_scale = 1.0 + 5.0 * structure_period_s + 0.12 * float(count)
    effective_mass_kg = max(mass_tonnes * 1000.0 * modal_mass_scale, 1.0)
    critical_damping_ratio = _clip(eq_damping + structural_damping_ratio + 0.04 + 0.015 * (stratification_ratio - 1.0), 0.08, 0.28)
    critical_c_horizontal = 2.0 * critical_damping_ratio * math.sqrt(max(static_k_horizontal * effective_mass_kg, 1.0))
    critical_c_vertical = 2.0 * critical_damping_ratio * math.sqrt(max(static_k_vertical * effective_mass_kg, 1.0))
    critical_c_rocking = 2.0 * critical_damping_ratio * math.sqrt(max(static_k_rocking * effective_mass_kg * radius * radius, 1.0))

    radiation_scale = eq_density * eq_vs * area
    static_c_horizontal = max(critical_c_horizontal, radiation_scale * (0.55 + 0.06 * embedment_factor))
    static_c_vertical = max(critical_c_vertical, eq_density * vp * area * (0.35 + 0.04 * embedment_factor))
    static_c_rocking = max(critical_c_rocking, eq_density * eq_vs * radius**4 * (0.20 + 0.03 * embedment_factor))

    freq_ratio = np.maximum(freq_hz / ref_hz, 1.0e-6)
    stiffness_scale = 1.0 + 0.18 * np.sqrt(freq_ratio) + 0.04 * (stratification_ratio - 1.0) * np.log1p(freq_ratio)
    damping_scale = 1.0 + (0.30 + eq_damping) * freq_ratio
    k_horizontal = static_k_horizontal * stiffness_scale
    k_vertical = static_k_vertical * (1.0 + 0.14 * np.sqrt(freq_ratio))
    k_rocking = static_k_rocking * (1.0 + 0.12 * np.sqrt(freq_ratio))
    c_horizontal = static_c_horizontal * damping_scale
    c_vertical = static_c_vertical * (1.0 + (0.24 + eq_damping) * freq_ratio)
    c_rocking = static_c_rocking * (1.0 + (0.20 + eq_damping) * freq_ratio)

    complex_horizontal = k_horizontal + 1j * (2.0 * np.pi * freq_hz * c_horizontal)
    foundation_transfer = np.abs(complex_horizontal / np.maximum(np.abs(complex_horizontal - effective_mass_kg * (2.0 * np.pi * freq_hz) ** 2), 1.0e-12))
    structure_frequency_hz = 1.0 / max(structure_period_s, 1.0e-9)
    structural_ratio = freq_hz / max(structure_frequency_hz, 1.0e-9)
    structural_magnification = 1.0 / np.sqrt(
        np.maximum((1.0 - structural_ratio**2) ** 2 + (2.0 * critical_damping_ratio * structural_ratio) ** 2, 1.0e-12)
    )
    coupled_amplification = foundation_transfer * structural_magnification

    return {
        "radius_m": float(radius),
        "area_m2": float(area),
        "effective_mass_kg": float(effective_mass_kg),
        "critical_damping_ratio": float(critical_damping_ratio),
        "structure_frequency_hz": float(structure_frequency_hz),
        "static_k_horizontal_n_m": float(static_k_horizontal),
        "static_k_vertical_n_m": float(static_k_vertical),
        "static_k_rocking_n_m_rad": float(static_k_rocking),
        "static_c_horizontal_ns_m": float(static_c_horizontal),
        "static_c_vertical_ns_m": float(static_c_vertical),
        "static_c_rocking_ns_m_rad": float(static_c_rocking),
        "k_horizontal_n_m": k_horizontal,
        "k_vertical_n_m": k_vertical,
        "k_rocking_n_m_rad": k_rocking,
        "c_horizontal_ns_m": c_horizontal,
        "c_vertical_ns_m": c_vertical,
        "c_rocking_ns_m_rad": c_rocking,
        "foundation_transfer_ratio": foundation_transfer,
        "coupled_amplification_ratio": coupled_amplification,
    }


def _curve_at_frequency(freq_hz: np.ndarray, values: np.ndarray, target_hz: float) -> float:
    return float(np.interp(target_hz, freq_hz, values))


def _head_rows(
    *,
    freq_hz: np.ndarray,
    impedance: dict[str, Any],
    row_count: int = 8,
) -> list[dict[str, float]]:
    return [
        {
            "frequency_hz": float(freq_hz[i]),
            "k_horizontal_n_m": float(impedance["k_horizontal_n_m"][i]),
            "c_horizontal_ns_m": float(impedance["c_horizontal_ns_m"][i]),
            "foundation_transfer_ratio": float(impedance["foundation_transfer_ratio"][i]),
            "coupled_amplification_ratio": float(impedance["coupled_amplification_ratio"][i]),
        }
        for i in range(min(row_count, int(freq_hz.size)))
    ]


def _bandwidth_window(freq_hz: np.ndarray, values: np.ndarray, peak_idx: int) -> tuple[float, float, float]:
    if values.size == 0:
        return 0.0, 0.0, 0.0
    peak = float(values[peak_idx])
    if peak <= 0.0:
        return float(freq_hz[peak_idx]), float(freq_hz[peak_idx]), 0.0
    threshold = peak / math.sqrt(2.0)
    left_idx = int(peak_idx)
    while left_idx > 0 and float(values[left_idx - 1]) >= threshold:
        left_idx -= 1
    right_idx = int(peak_idx)
    while right_idx < int(values.size) - 1 and float(values[right_idx + 1]) >= threshold:
        right_idx += 1
    left_hz = float(freq_hz[left_idx])
    right_hz = float(freq_hz[right_idx])
    return left_hz, right_hz, max(right_hz - left_hz, 0.0)


def _frequency_response_metrics(
    *,
    freq_hz: np.ndarray,
    transfer: np.ndarray,
    amplification: np.ndarray,
    transfer_peak_idx: int,
    amplification_peak_idx: int,
    hazard_frequency_hz: float,
    structure_frequency_hz: float,
    reference_frequency_hz: float,
) -> dict[str, Any]:
    freq_step_hz = float(np.median(np.diff(freq_hz))) if int(freq_hz.size) >= 2 else 0.0
    transfer_left_hz, transfer_right_hz, transfer_bandwidth_hz = _bandwidth_window(
        freq_hz,
        transfer,
        transfer_peak_idx,
    )
    amplification_left_hz, amplification_right_hz, amplification_bandwidth_hz = _bandwidth_window(
        freq_hz,
        amplification,
        amplification_peak_idx,
    )
    peak_transfer_frequency_hz = float(freq_hz[transfer_peak_idx])
    peak_amplification_frequency_hz = float(freq_hz[amplification_peak_idx])
    peak_transfer_ratio = max(float(transfer[transfer_peak_idx]), 1.0e-9)
    peak_amplification_ratio = max(float(amplification[amplification_peak_idx]), 1.0e-9)
    hazard_transfer_ratio = _curve_at_frequency(freq_hz, transfer, hazard_frequency_hz)
    hazard_amplification_ratio = _curve_at_frequency(freq_hz, amplification, hazard_frequency_hz)
    reference_transfer_ratio = _curve_at_frequency(freq_hz, transfer, reference_frequency_hz)
    reference_amplification_ratio = _curve_at_frequency(freq_hz, amplification, reference_frequency_hz)
    transfer_decay_ratio = float(transfer[-1]) / peak_transfer_ratio
    amplification_decay_ratio = float(amplification[-1]) / peak_amplification_ratio
    return {
        "frequency_resolution_hz": float(freq_step_hz),
        "peak_transfer_frequency_hz": float(peak_transfer_frequency_hz),
        "peak_amplification_frequency_hz": float(peak_amplification_frequency_hz),
        "transfer_half_power_left_hz": float(transfer_left_hz),
        "transfer_half_power_right_hz": float(transfer_right_hz),
        "transfer_half_power_bandwidth_hz": float(transfer_bandwidth_hz),
        "transfer_quality_factor": float(peak_transfer_frequency_hz / max(transfer_bandwidth_hz, 1.0e-9)),
        "amplification_half_power_left_hz": float(amplification_left_hz),
        "amplification_half_power_right_hz": float(amplification_right_hz),
        "amplification_half_power_bandwidth_hz": float(amplification_bandwidth_hz),
        "amplification_quality_factor": float(
            peak_amplification_frequency_hz / max(amplification_bandwidth_hz, 1.0e-9)
        ),
        "hazard_detuning_ratio": float(
            abs(hazard_frequency_hz - peak_amplification_frequency_hz) / max(peak_amplification_frequency_hz, 1.0e-9)
        ),
        "structure_detuning_ratio": float(
            abs(structure_frequency_hz - peak_transfer_frequency_hz) / max(peak_transfer_frequency_hz, 1.0e-9)
        ),
        "hazard_transfer_utilization_ratio": float(hazard_transfer_ratio / peak_transfer_ratio),
        "hazard_amplification_utilization_ratio": float(hazard_amplification_ratio / peak_amplification_ratio),
        "reference_transfer_utilization_ratio": float(reference_transfer_ratio / peak_transfer_ratio),
        "reference_amplification_utilization_ratio": float(reference_amplification_ratio / peak_amplification_ratio),
        "transfer_high_frequency_decay_ratio": float(transfer_decay_ratio),
        "amplification_high_frequency_decay_ratio": float(amplification_decay_ratio),
    }


def _pile_group_interaction_metrics(
    *,
    group: dict[str, Any],
    radius_m: float,
    effective_soil: dict[str, Any],
) -> dict[str, Any]:
    count = max(_safe_int(group.get("count"), 1), 1)
    length_m = _safe_float(group.get("length_m"))
    width_m = _safe_float(group.get("width_m"))
    area_m2 = max(length_m * width_m, 1.0e-12)
    embedment_m = _safe_float(group.get("embedment_m"))
    stratification_ratio = max(_safe_float(effective_soil.get("stratification_ratio"), 1.0), 1.0)
    center_spacing_proxy_m = min(length_m, width_m) / max(math.sqrt(float(count)), 1.0)
    spacing_to_radius_ratio = center_spacing_proxy_m / max(radius_m, 1.0e-9)
    embedment_ratio = embedment_m / max(radius_m, 1.0e-9)
    if count <= 1:
        return {
            "grouping_regime": "single_foundation",
            "footprint_area_m2": float(area_m2),
            "tributary_area_per_foundation_m2": float(area_m2),
            "center_spacing_proxy_m": float(center_spacing_proxy_m),
            "spacing_to_radius_ratio": float(spacing_to_radius_ratio),
            "embedment_ratio": float(embedment_ratio),
            "radiation_overlap_ratio": 0.0,
            "interaction_efficiency_ratio": 1.0,
            "shadowing_index": 0.0,
            "load_share_ratio_per_foundation": 1.0,
        }
    density_factor = min(float(count) / max(area_m2, 1.0e-9), 1.0)
    shadowing_index = _clip(
        0.08 * max(count - 1, 0) / max(spacing_to_radius_ratio, 0.75)
        + 0.05 * density_factor
        + 0.03 * max(stratification_ratio - 1.0, 0.0)
        - 0.02 * min(embedment_ratio, 2.0),
        0.0,
        0.55,
    )
    interaction_efficiency_ratio = float(1.0 - shadowing_index)
    radiation_overlap_ratio = _clip(
        max(count - 1, 0) / max(float(count) + 2.0 * spacing_to_radius_ratio, 1.0),
        0.0,
        0.85,
    )
    if spacing_to_radius_ratio < 0.90:
        grouping_regime = "compact_group"
    elif spacing_to_radius_ratio < 1.25:
        grouping_regime = "moderate_group"
    else:
        grouping_regime = "spread_group"
    return {
        "grouping_regime": grouping_regime,
        "footprint_area_m2": float(area_m2),
        "tributary_area_per_foundation_m2": float(area_m2 / float(count)),
        "center_spacing_proxy_m": float(center_spacing_proxy_m),
        "spacing_to_radius_ratio": float(spacing_to_radius_ratio),
        "embedment_ratio": float(embedment_ratio),
        "radiation_overlap_ratio": float(radiation_overlap_ratio),
        "interaction_efficiency_ratio": float(interaction_efficiency_ratio),
        "shadowing_index": float(shadowing_index),
        "load_share_ratio_per_foundation": float(1.0 / float(count)),
    }


def _group_report(
    *,
    group: dict[str, Any],
    layers: list[dict[str, Any]],
    freq_hz: np.ndarray,
    ref_hz: float,
    hazard_frequency_hz: float,
    pga_g: float,
) -> dict[str, Any]:
    radius = _foundation_equivalent_radius(group)
    influence_depth_m = min(_profile_depth(layers), max(2.0 * radius + _safe_float(group.get("embedment_m")), 6.0))
    effective_soil = _effective_soil_properties(layers, influence_depth_m=influence_depth_m)
    impedance = _coupled_impedance_curves(freq_hz=freq_hz, soil=effective_soil, group=group, ref_hz=ref_hz)

    transfer = np.asarray(impedance["foundation_transfer_ratio"], dtype=np.float64)
    amplification = np.asarray(impedance["coupled_amplification_ratio"], dtype=np.float64)
    transfer_peak_idx = int(np.argmax(transfer))
    amplification_peak_idx = int(np.argmax(amplification))
    structure_frequency_hz = _safe_float(impedance.get("structure_frequency_hz"))
    transfer_at_structure = _curve_at_frequency(freq_hz, transfer, structure_frequency_hz)
    transfer_at_hazard = _curve_at_frequency(freq_hz, transfer, hazard_frequency_hz)
    amplification_at_structure = _curve_at_frequency(freq_hz, amplification, structure_frequency_hz)
    amplification_at_hazard = _curve_at_frequency(freq_hz, amplification, hazard_frequency_hz)
    demand_modifier = 1.0 + 0.8 * pga_g * transfer_at_structure
    frequency_response_metrics = _frequency_response_metrics(
        freq_hz=freq_hz,
        transfer=transfer,
        amplification=amplification,
        transfer_peak_idx=transfer_peak_idx,
        amplification_peak_idx=amplification_peak_idx,
        hazard_frequency_hz=hazard_frequency_hz,
        structure_frequency_hz=structure_frequency_hz,
        reference_frequency_hz=ref_hz,
    )
    pile_group_interaction = _pile_group_interaction_metrics(
        group=group,
        radius_m=radius,
        effective_soil=effective_soil,
    )

    reference_index = int(np.argmin(np.abs(freq_hz - ref_hz)))
    return {
        "group_id": str(group.get("group_id", "")).strip(),
        "foundation_type": str(group.get("foundation_type", "")).strip(),
        "count": _safe_int(group.get("count"), 0),
        "contact_area_m2": round(_safe_float(group.get("length_m")) * _safe_float(group.get("width_m")), 6),
        "equivalent_radius_m": round(radius, 6),
        "embedment_m": round(_safe_float(group.get("embedment_m")), 6),
        "structure_period_s": round(_safe_float(group.get("structure_period_s")), 6),
        "structure_frequency_hz": round(structure_frequency_hz, 6),
        "effective_soil": effective_soil,
        "impedance_reference": {
            "reference_frequency_hz": round(float(freq_hz[reference_index]), 6),
            "k_horizontal_n_m": round(float(impedance["k_horizontal_n_m"][reference_index]), 3),
            "c_horizontal_ns_m": round(float(impedance["c_horizontal_ns_m"][reference_index]), 3),
            "k_vertical_n_m": round(float(impedance["k_vertical_n_m"][reference_index]), 3),
            "c_vertical_ns_m": round(float(impedance["c_vertical_ns_m"][reference_index]), 3),
            "k_rocking_n_m_rad": round(float(impedance["k_rocking_n_m_rad"][reference_index]), 3),
            "c_rocking_ns_m_rad": round(float(impedance["c_rocking_ns_m_rad"][reference_index]), 3),
            "effective_mass_kg": round(_safe_float(impedance.get("effective_mass_kg")), 3),
            "critical_damping_ratio": round(_safe_float(impedance.get("critical_damping_ratio")), 6),
        },
        "transfer_summary": {
            "peak_transfer_ratio": round(float(transfer[transfer_peak_idx]), 6),
            "peak_transfer_frequency_hz": round(float(freq_hz[transfer_peak_idx]), 6),
            "hazard_transfer_ratio": round(transfer_at_hazard, 6),
            "structure_transfer_ratio": round(transfer_at_structure, 6),
        },
        "amplification_summary": {
            "peak_amplification_ratio": round(float(amplification[amplification_peak_idx]), 6),
            "peak_amplification_frequency_hz": round(float(freq_hz[amplification_peak_idx]), 6),
            "hazard_amplification_ratio": round(amplification_at_hazard, 6),
            "structure_amplification_ratio": round(amplification_at_structure, 6),
            "demand_modifier": round(float(demand_modifier), 6),
        },
        "frequency_response_metrics": frequency_response_metrics,
        "pile_group_interaction": pile_group_interaction,
        "curve_head": _head_rows(freq_hz=freq_hz, impedance=impedance),
    }


def build_report(payload: dict[str, Any], *, source_path: str = "") -> dict[str, Any]:
    validate_input_contract(payload, INPUT_SCHEMA, label="phase1.advanced_ssi")
    soil_profile = payload.get("soil_profile") if isinstance(payload.get("soil_profile"), dict) else {}
    layer_rows = soil_profile.get("layers") if isinstance(soil_profile.get("layers"), list) else []
    group_rows = payload.get("foundation_groups") if isinstance(payload.get("foundation_groups"), list) else []
    if not layer_rows:
        raise ValueError("soil_profile.layers must not be empty")
    if not group_rows:
        raise ValueError("foundation_groups must not be empty")

    layers = _annotate_layers([row for row in layer_rows if isinstance(row, dict)])
    groups = sorted([row for row in group_rows if isinstance(row, dict)], key=lambda row: str(row.get("group_id", "")))
    group_ids = [str(row.get("group_id", "")).strip() for row in groups]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("foundation group_id values must be unique")

    freq_hz, ref_hz = _frequency_grid(payload)
    hazard_frequency_hz, pga_g = _hazard_settings(payload)
    soil_layer_velocity_values = [_safe_float(layer.get("shear_wave_velocity_m_s")) for layer in layers]
    soil_impedance_contrast_ratio_max = (
        max(
            max(soil_layer_velocity_values[i], soil_layer_velocity_values[i + 1]) / max(min(soil_layer_velocity_values[i], soil_layer_velocity_values[i + 1]), 1.0e-9)
            for i in range(max(len(soil_layer_velocity_values) - 1, 0))
        )
        if len(soil_layer_velocity_values) >= 2
        else 1.0
    )

    group_reports = [
        _group_report(
            group=group,
            layers=layers,
            freq_hz=freq_hz,
            ref_hz=ref_hz,
            hazard_frequency_hz=hazard_frequency_hz,
            pga_g=pga_g,
        )
        for group in groups
    ]

    peak_transfer_group = max(group_reports, key=lambda row: _safe_float((row.get("transfer_summary") or {}).get("peak_transfer_ratio")))
    peak_amplification_group = max(
        group_reports,
        key=lambda row: _safe_float((row.get("amplification_summary") or {}).get("peak_amplification_ratio")),
    )
    hazard_detuning_group = max(
        group_reports,
        key=lambda row: _safe_float((row.get("frequency_response_metrics") or {}).get("hazard_detuning_ratio")),
    )
    interaction_governing_group = min(
        group_reports,
        key=lambda row: _safe_float((row.get("pile_group_interaction") or {}).get("interaction_efficiency_ratio"), 1.0),
    )
    reference_groups = [
        {
            "group_id": row["group_id"],
            "foundation_type": row["foundation_type"],
            "k_horizontal_n_m": _safe_float((row.get("impedance_reference") or {}).get("k_horizontal_n_m")),
            "c_horizontal_ns_m": _safe_float((row.get("impedance_reference") or {}).get("c_horizontal_ns_m")),
            "k_vertical_n_m": _safe_float((row.get("impedance_reference") or {}).get("k_vertical_n_m")),
            "c_vertical_ns_m": _safe_float((row.get("impedance_reference") or {}).get("c_vertical_ns_m")),
            "k_rocking_n_m_rad": _safe_float((row.get("impedance_reference") or {}).get("k_rocking_n_m_rad")),
            "c_rocking_ns_m_rad": _safe_float((row.get("impedance_reference") or {}).get("c_rocking_ns_m_rad")),
        }
        for row in group_reports
    ]
    transfer_groups = [
        {
            "group_id": row["group_id"],
            "peak_transfer_ratio": _safe_float((row.get("transfer_summary") or {}).get("peak_transfer_ratio")),
            "peak_transfer_frequency_hz": _safe_float((row.get("transfer_summary") or {}).get("peak_transfer_frequency_hz")),
            "hazard_transfer_ratio": _safe_float((row.get("transfer_summary") or {}).get("hazard_transfer_ratio")),
        }
        for row in group_reports
    ]
    amplification_groups = [
        {
            "group_id": row["group_id"],
            "peak_amplification_ratio": _safe_float((row.get("amplification_summary") or {}).get("peak_amplification_ratio")),
            "peak_amplification_frequency_hz": _safe_float((row.get("amplification_summary") or {}).get("peak_amplification_frequency_hz")),
            "structure_amplification_ratio": _safe_float((row.get("amplification_summary") or {}).get("structure_amplification_ratio")),
            "demand_modifier": _safe_float((row.get("amplification_summary") or {}).get("demand_modifier")),
        }
        for row in group_reports
    ]
    frequency_response_groups = [
        {
            "group_id": row["group_id"],
            "hazard_detuning_ratio": _safe_float((row.get("frequency_response_metrics") or {}).get("hazard_detuning_ratio")),
            "structure_detuning_ratio": _safe_float((row.get("frequency_response_metrics") or {}).get("structure_detuning_ratio")),
            "transfer_half_power_bandwidth_hz": _safe_float(
                (row.get("frequency_response_metrics") or {}).get("transfer_half_power_bandwidth_hz")
            ),
            "amplification_half_power_bandwidth_hz": _safe_float(
                (row.get("frequency_response_metrics") or {}).get("amplification_half_power_bandwidth_hz")
            ),
            "transfer_high_frequency_decay_ratio": _safe_float(
                (row.get("frequency_response_metrics") or {}).get("transfer_high_frequency_decay_ratio")
            ),
            "amplification_high_frequency_decay_ratio": _safe_float(
                (row.get("frequency_response_metrics") or {}).get("amplification_high_frequency_decay_ratio")
            ),
        }
        for row in group_reports
    ]
    pile_group_interaction_groups = [
        {
            "group_id": row["group_id"],
            "grouping_regime": str((row.get("pile_group_interaction") or {}).get("grouping_regime", "") or ""),
            "interaction_efficiency_ratio": _safe_float(
                (row.get("pile_group_interaction") or {}).get("interaction_efficiency_ratio"),
                1.0,
            ),
            "shadowing_index": _safe_float((row.get("pile_group_interaction") or {}).get("shadowing_index")),
            "spacing_to_radius_ratio": _safe_float(
                (row.get("pile_group_interaction") or {}).get("spacing_to_radius_ratio")
            ),
            "radiation_overlap_ratio": _safe_float(
                (row.get("pile_group_interaction") or {}).get("radiation_overlap_ratio")
            ),
        }
        for row in group_reports
    ]

    checks = {
        "soil_layering_present": bool(len(layers) >= 1),
        "foundation_grouping_consistent": bool(len(group_ids) == len(set(group_ids)) and all(_safe_int(row.get("count"), 0) > 0 for row in groups)),
        "positive_impedance": bool(all(entry["k_horizontal_n_m"] > 0.0 and entry["c_horizontal_ns_m"] > 0.0 for entry in reference_groups)),
        "finite_transfer": bool(
            all(math.isfinite(_safe_float(item.get("peak_transfer_ratio"))) and math.isfinite(_safe_float(item.get("hazard_transfer_ratio"))) for item in transfer_groups)
        ),
        "transfer_band_pass": bool(max(_safe_float(item.get("peak_transfer_ratio")) for item in transfer_groups) <= 3.5),
        "amplification_band_pass": bool(max(_safe_float(item.get("peak_amplification_ratio")) for item in amplification_groups) <= 4.5),
        "frequency_response_metrics_finite": bool(
            all(
                math.isfinite(_safe_float(item.get("hazard_detuning_ratio")))
                and math.isfinite(_safe_float(item.get("transfer_half_power_bandwidth_hz")))
                and math.isfinite(_safe_float(item.get("amplification_half_power_bandwidth_hz")))
                and _safe_float(item.get("transfer_half_power_bandwidth_hz")) >= 0.0
                and _safe_float(item.get("amplification_half_power_bandwidth_hz")) >= 0.0
                for item in frequency_response_groups
            )
        ),
        "pile_group_interaction_metrics_finite": bool(
            all(
                0.0 <= _safe_float(item.get("interaction_efficiency_ratio"), 1.0) <= 1.0
                and 0.0 <= _safe_float(item.get("shadowing_index")) <= 1.0
                and math.isfinite(_safe_float(item.get("spacing_to_radius_ratio")))
                for item in pile_group_interaction_groups
            )
        ),
    }
    contract_pass = bool(all(checks.values()))
    reason_code = "PASS" if contract_pass else "ERR_SSI_NUMERICS"

    summary = {
        "soil_profile_id": str(soil_profile.get("profile_id", "")).strip(),
        "soil_layer_count": len(layers),
        "soil_total_depth_m": round(_profile_depth(layers), 6),
        "vs30_m_s": round(_vs30(layers), 6),
        "groundwater_depth_m": round(_safe_float(soil_profile.get("groundwater_depth_m"), 0.0), 6),
        "foundation_group_count": len(group_reports),
        "foundation_instance_count": int(sum(_safe_int(row.get("count"), 0) for row in groups)),
        "reference_frequency_hz": round(ref_hz, 6),
        "hazard_frequency_hz": round(hazard_frequency_hz, 6),
        "hazard_pga_g": round(pga_g, 6),
        "peak_transfer_ratio_max": round(_safe_float((peak_transfer_group.get("transfer_summary") or {}).get("peak_transfer_ratio")), 6),
        "peak_transfer_frequency_hz": round(_safe_float((peak_transfer_group.get("transfer_summary") or {}).get("peak_transfer_frequency_hz")), 6),
        "peak_transfer_group_id": peak_transfer_group["group_id"],
        "peak_amplification_ratio_max": round(
            _safe_float((peak_amplification_group.get("amplification_summary") or {}).get("peak_amplification_ratio")), 6
        ),
        "peak_amplification_frequency_hz": round(
            _safe_float((peak_amplification_group.get("amplification_summary") or {}).get("peak_amplification_frequency_hz")), 6
        ),
        "peak_amplification_group_id": peak_amplification_group["group_id"],
        "governing_response_group_id": peak_amplification_group["group_id"],
        "soil_impedance_contrast_ratio_max": round(float(soil_impedance_contrast_ratio_max), 6),
        "max_hazard_detuning_ratio": round(
            _safe_float((hazard_detuning_group.get("frequency_response_metrics") or {}).get("hazard_detuning_ratio")),
            6,
        ),
        "max_hazard_detuning_group_id": hazard_detuning_group["group_id"],
        "min_group_interaction_efficiency_ratio": round(
            _safe_float((interaction_governing_group.get("pile_group_interaction") or {}).get("interaction_efficiency_ratio"), 1.0),
            6,
        ),
        "min_group_interaction_group_id": interaction_governing_group["group_id"],
    }
    summary_line = (
        f"Advanced SSI: {'PASS' if contract_pass else 'CHECK'} | "
        f"layers={summary['soil_layer_count']} | groups={summary['foundation_group_count']} | "
        f"vs30={summary['vs30_m_s']:.1f} m/s | "
        f"peak_transfer={summary['peak_transfer_group_id']}@{summary['peak_transfer_frequency_hz']:.2f}Hz x{summary['peak_transfer_ratio_max']:.2f} | "
        f"peak_amp={summary['peak_amplification_group_id']}@{summary['peak_amplification_frequency_hz']:.2f}Hz x{summary['peak_amplification_ratio_max']:.2f} | "
        f"contrast={summary['soil_impedance_contrast_ratio_max']:.2f} | "
        f"detune={summary['max_hazard_detuning_group_id']}:{summary['max_hazard_detuning_ratio']:.2f} | "
        f"group_eff={summary['min_group_interaction_group_id']}:{summary['min_group_interaction_efficiency_ratio']:.2f}"
    )

    return {
        "schema_version": "1.0",
        "run_id": "phase1-advanced-ssi",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
        "inputs": {
            "profile_json": source_path,
            "reference_frequency_hz": ref_hz,
            "hazard_frequency_hz": hazard_frequency_hz,
            "hazard_pga_g": pga_g,
        },
        "checks": checks,
        "summary": summary,
        "soil_profile_summary": {
            "profile_id": summary["soil_profile_id"],
            "total_depth_m": summary["soil_total_depth_m"],
            "vs30_m_s": summary["vs30_m_s"],
            "groundwater_depth_m": summary["groundwater_depth_m"],
            "layer_rows": layers,
        },
        "foundation_group_summary": {
            "group_count": summary["foundation_group_count"],
            "foundation_instance_count": summary["foundation_instance_count"],
            "group_ids": [row["group_id"] for row in group_reports],
            "foundation_types": sorted({row["foundation_type"] for row in group_reports}),
        },
        "impedance_summary": {
            "reference_frequency_hz": summary["reference_frequency_hz"],
            "tokens": [
                "k_horizontal_n_m",
                "c_horizontal_ns_m",
                "k_vertical_n_m",
                "c_vertical_ns_m",
                "k_rocking_n_m_rad",
                "c_rocking_ns_m_rad",
            ],
            "groups": reference_groups,
        },
        "transfer_summary": {
            "hazard_frequency_hz": summary["hazard_frequency_hz"],
            "governing_group_id": summary["peak_transfer_group_id"],
            "peak_transfer_ratio_max": summary["peak_transfer_ratio_max"],
            "groups": transfer_groups,
        },
        "amplification_summary": {
            "governing_group_id": summary["peak_amplification_group_id"],
            "peak_amplification_ratio_max": summary["peak_amplification_ratio_max"],
            "groups": amplification_groups,
        },
        "frequency_response_summary": {
            "governing_group_id": summary["max_hazard_detuning_group_id"],
            "max_hazard_detuning_ratio": summary["max_hazard_detuning_ratio"],
            "groups": frequency_response_groups,
        },
        "pile_group_interaction_summary": {
            "governing_group_id": summary["min_group_interaction_group_id"],
            "min_interaction_efficiency_ratio": summary["min_group_interaction_efficiency_ratio"],
            "groups": pile_group_interaction_groups,
        },
        "group_reports": group_reports,
        "results_explorer": {
            "entry_kind": "advanced_ssi_reduced_order",
            "entry_label": "Advanced SSI reduced-order",
            "source_family": "advanced_ssi",
            "summary_label": summary_line,
        },
    }


def _error_payload(*, out: str, error: str, profile_json: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "phase1-advanced-ssi",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": False,
        "reason_code": "ERR_INVALID_INPUT",
        "reason": f"{REASONS['ERR_INVALID_INPUT']}: {error}",
        "inputs": {"profile_json": profile_json, "out": out},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = build_report(_load_json(Path(args.profile_json)), source_path=str(args.profile_json))
    except (FileNotFoundError, ValueError, InputContractError) as exc:
        payload = _error_payload(out=str(args.out), error=str(exc), profile_json=str(args.profile_json))
    except Exception as exc:  # noqa: BLE001
        payload = _error_payload(out=str(args.out), error=repr(exc), profile_json=str(args.profile_json))

    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote advanced SSI report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
