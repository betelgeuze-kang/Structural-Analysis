#!/usr/bin/env python3
"""Rail/tunnel postprocess utility for serviceability and lining review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "rail/tunnel postprocess metrics passed serviceability and lining benchmarks",
    "ERR_INVALID_INPUT": "invalid rail/tunnel postprocess input",
    "ERR_BENCHMARK_FAIL": "rail/tunnel postprocess benchmark thresholds were exceeded",
}

DEFAULT_THRESHOLDS = {
    "max_abs_settlement_mm": 12.0,
    "max_diff_settlement_mm": 4.0,
    "min_clearance_mm": 80.0,
    "max_lining_utilization": 1.0,
    "max_vibration_velocity_mm_s": 0.25,
    "nominal_clearance_mm": 110.0,
    "lining_moment_capacity_kNm": 650.0,
    "lining_strain_capacity": 0.0025,
}

POSTPROCESS_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_id", "track_samples", "lining_samples"],
    "properties": {
        "case_id": {"type": "string", "minLength": 1},
        "metadata": {"type": "object"},
        "track_samples": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["chainage_m", "rail_settlement_mm"],
                "properties": {
                    "chainage_m": {"type": "number"},
                    "rail_settlement_mm": {"type": "number"},
                    "tunnel_crown_settlement_mm": {"type": "number"},
                    "clearance_mm": {"type": "number"},
                    "nominal_clearance_mm": {"type": "number"},
                    "location_id": {"type": "string"},
                },
            },
        },
        "lining_samples": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["ring_id"],
                "properties": {
                    "ring_id": {"type": "string", "minLength": 1},
                    "position_deg": {"type": "number"},
                    "moment_kNm": {"type": "number"},
                    "moment_capacity_kNm": {"type": "number", "exclusiveMinimum": 0.0},
                    "axial_force_kN": {"type": "number"},
                    "axial_capacity_kN": {"type": "number", "exclusiveMinimum": 0.0},
                    "shear_kN": {"type": "number"},
                    "shear_capacity_kN": {"type": "number", "exclusiveMinimum": 0.0},
                    "longitudinal_strain": {"type": "number"},
                    "strain_capacity": {"type": "number", "exclusiveMinimum": 0.0},
                    "utilization": {"type": "number", "minimum": 0.0},
                    "utilization_ratio": {"type": "number", "minimum": 0.0},
                },
            },
        },
        "vibration_samples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["velocity_mm_s"],
                "properties": {
                    "chainage_m": {"type": "number"},
                    "velocity_mm_s": {"type": "number", "minimum": 0.0},
                    "freq_hz": {"type": "number", "exclusiveMinimum": 0.0},
                    "location_id": {"type": "string"},
                },
            },
        },
        "benchmarks": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_abs_settlement_mm": {"type": "number", "exclusiveMinimum": 0.0},
                "max_diff_settlement_mm": {"type": "number", "exclusiveMinimum": 0.0},
                "min_clearance_mm": {"type": "number", "exclusiveMinimum": 0.0},
                "max_lining_utilization": {"type": "number", "exclusiveMinimum": 0.0},
                "max_vibration_velocity_mm_s": {"type": "number", "exclusiveMinimum": 0.0},
                "nominal_clearance_mm": {"type": "number", "exclusiveMinimum": 0.0},
                "lining_moment_capacity_kNm": {"type": "number", "exclusiveMinimum": 0.0},
                "lining_strain_capacity": {"type": "number", "exclusiveMinimum": 0.0},
            },
        },
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _require_float(value: Any, label: str) -> float:
    out = _optional_float(value)
    if out is None:
        raise ValueError(f"{label} must be numeric")
    return out


def _default_case_payload() -> dict[str, Any]:
    return {
        "case_id": "rail_tunnel_demo_case",
        "metadata": {
            "line_id": "DEMO-L1",
            "asset_id": "TN-12-450",
            "source_mode": "demo_fixture",
            "nominal_clearance_mm": DEFAULT_THRESHOLDS["nominal_clearance_mm"],
        },
        "track_samples": [
            {
                "location_id": "CH000",
                "chainage_m": 0.0,
                "rail_settlement_mm": -1.2,
                "tunnel_crown_settlement_mm": -0.8,
                "clearance_mm": 108.0,
            },
            {
                "location_id": "CH010",
                "chainage_m": 10.0,
                "rail_settlement_mm": -2.9,
                "tunnel_crown_settlement_mm": -1.5,
                "clearance_mm": 103.0,
            },
            {
                "location_id": "CH020",
                "chainage_m": 20.0,
                "rail_settlement_mm": -4.8,
                "tunnel_crown_settlement_mm": -2.4,
                "clearance_mm": 99.0,
            },
            {
                "location_id": "CH030",
                "chainage_m": 30.0,
                "rail_settlement_mm": -3.6,
                "tunnel_crown_settlement_mm": -1.8,
                "clearance_mm": 101.0,
            },
            {
                "location_id": "CH040",
                "chainage_m": 40.0,
                "rail_settlement_mm": -1.4,
                "tunnel_crown_settlement_mm": -0.9,
                "clearance_mm": 107.0,
            },
        ],
        "lining_samples": [
            {
                "ring_id": "R-118",
                "position_deg": 0.0,
                "moment_kNm": 265.0,
                "moment_capacity_kNm": 540.0,
                "axial_force_kN": 940.0,
                "axial_capacity_kN": 1650.0,
                "shear_kN": 82.0,
                "shear_capacity_kN": 150.0,
                "longitudinal_strain": 0.00105,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-118",
                "position_deg": 90.0,
                "moment_kNm": 192.0,
                "moment_capacity_kNm": 540.0,
                "axial_force_kN": 1010.0,
                "axial_capacity_kN": 1650.0,
                "shear_kN": 74.0,
                "shear_capacity_kN": 150.0,
                "longitudinal_strain": 0.00112,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-119",
                "position_deg": 0.0,
                "moment_kNm": 298.0,
                "moment_capacity_kNm": 540.0,
                "axial_force_kN": 1030.0,
                "axial_capacity_kN": 1650.0,
                "shear_kN": 88.0,
                "shear_capacity_kN": 150.0,
                "longitudinal_strain": 0.00126,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-119",
                "position_deg": 180.0,
                "moment_kNm": 236.0,
                "moment_capacity_kNm": 540.0,
                "axial_force_kN": 980.0,
                "axial_capacity_kN": 1650.0,
                "shear_kN": 79.0,
                "shear_capacity_kN": 150.0,
                "longitudinal_strain": 0.00121,
                "strain_capacity": 0.0025,
            },
        ],
        "vibration_samples": [
            {"location_id": "CH010", "chainage_m": 10.0, "velocity_mm_s": 0.13, "freq_hz": 16.0},
            {"location_id": "CH020", "chainage_m": 20.0, "velocity_mm_s": 0.18, "freq_hz": 31.5},
            {"location_id": "CH030", "chainage_m": 30.0, "velocity_mm_s": 0.16, "freq_hz": 16.0},
        ],
    }


def _validate_thresholds(thresholds: dict[str, float]) -> None:
    for key, value in thresholds.items():
        if value <= 0.0:
            raise ValueError(f"{key} must be > 0")


def _merge_thresholds(
    case_payload: dict[str, Any],
    *,
    max_abs_settlement_mm: float | None,
    max_diff_settlement_mm: float | None,
    min_clearance_mm: float | None,
    max_lining_utilization: float | None,
    max_vibration_velocity_mm_s: float | None,
    nominal_clearance_mm: float | None,
    lining_moment_capacity_kNm: float | None,
    lining_strain_capacity: float | None,
) -> dict[str, float]:
    raw = case_payload.get("benchmarks", {})
    source = raw if isinstance(raw, dict) else {}
    thresholds = {
        "max_abs_settlement_mm": float(
            max_abs_settlement_mm
            if max_abs_settlement_mm is not None
            else source.get("max_abs_settlement_mm", DEFAULT_THRESHOLDS["max_abs_settlement_mm"])
        ),
        "max_diff_settlement_mm": float(
            max_diff_settlement_mm
            if max_diff_settlement_mm is not None
            else source.get("max_diff_settlement_mm", DEFAULT_THRESHOLDS["max_diff_settlement_mm"])
        ),
        "min_clearance_mm": float(
            min_clearance_mm
            if min_clearance_mm is not None
            else source.get("min_clearance_mm", DEFAULT_THRESHOLDS["min_clearance_mm"])
        ),
        "max_lining_utilization": float(
            max_lining_utilization
            if max_lining_utilization is not None
            else source.get("max_lining_utilization", DEFAULT_THRESHOLDS["max_lining_utilization"])
        ),
        "max_vibration_velocity_mm_s": float(
            max_vibration_velocity_mm_s
            if max_vibration_velocity_mm_s is not None
            else source.get("max_vibration_velocity_mm_s", DEFAULT_THRESHOLDS["max_vibration_velocity_mm_s"])
        ),
        "nominal_clearance_mm": float(
            nominal_clearance_mm
            if nominal_clearance_mm is not None
            else source.get("nominal_clearance_mm", DEFAULT_THRESHOLDS["nominal_clearance_mm"])
        ),
        "lining_moment_capacity_kNm": float(
            lining_moment_capacity_kNm
            if lining_moment_capacity_kNm is not None
            else source.get("lining_moment_capacity_kNm", DEFAULT_THRESHOLDS["lining_moment_capacity_kNm"])
        ),
        "lining_strain_capacity": float(
            lining_strain_capacity
            if lining_strain_capacity is not None
            else source.get("lining_strain_capacity", DEFAULT_THRESHOLDS["lining_strain_capacity"])
        ),
    }
    _validate_thresholds(thresholds)
    return thresholds


def _sample_clearance_mm(sample: dict[str, Any], default_nominal_clearance_mm: float) -> float | None:
    direct = _optional_float(sample.get("clearance_mm"))
    if direct is not None:
        return direct
    nominal = _optional_float(sample.get("nominal_clearance_mm"))
    if nominal is None:
        nominal = float(default_nominal_clearance_mm)
    rail = abs(_require_float(sample.get("rail_settlement_mm"), "track_samples[].rail_settlement_mm"))
    tunnel = abs(_optional_float(sample.get("tunnel_crown_settlement_mm")) or 0.0)
    return float(nominal - rail - tunnel)


def _sample_utilization(sample: dict[str, Any], thresholds: dict[str, float]) -> tuple[float, str]:
    direct = _optional_float(sample.get("utilization"))
    if direct is None:
        direct = _optional_float(sample.get("utilization_ratio"))
    if direct is not None:
        return max(float(direct), 0.0), "direct"

    candidates: list[tuple[str, float]] = []
    moment = _optional_float(sample.get("moment_kNm"))
    if moment is not None:
        capacity = _optional_float(sample.get("moment_capacity_kNm"))
        if capacity is None:
            capacity = float(thresholds["lining_moment_capacity_kNm"])
        if capacity > 0.0:
            candidates.append(("moment", abs(moment) / capacity))

    axial = _optional_float(sample.get("axial_force_kN"))
    axial_capacity = _optional_float(sample.get("axial_capacity_kN"))
    if axial is not None and axial_capacity is not None and axial_capacity > 0.0:
        candidates.append(("axial", abs(axial) / axial_capacity))

    shear = _optional_float(sample.get("shear_kN"))
    shear_capacity = _optional_float(sample.get("shear_capacity_kN"))
    if shear is not None and shear_capacity is not None and shear_capacity > 0.0:
        candidates.append(("shear", abs(shear) / shear_capacity))

    strain = _optional_float(sample.get("longitudinal_strain"))
    if strain is not None:
        strain_capacity = _optional_float(sample.get("strain_capacity"))
        if strain_capacity is None:
            strain_capacity = float(thresholds["lining_strain_capacity"])
        if strain_capacity > 0.0:
            candidates.append(("strain", abs(strain) / strain_capacity))

    if not candidates:
        return 0.0, "not_available"

    mode, value = max(candidates, key=lambda item: (item[1], item[0]))
    return float(value), str(mode)


def _summarize_lining_samples(
    lining_samples: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in lining_samples:
        ring_id = str(sample.get("ring_id", "")).strip()
        grouped.setdefault(ring_id, []).append(sample)

    ring_summaries: list[dict[str, Any]] = []
    for ring_id, rows in grouped.items():
        peak_moment = max((abs(_optional_float(row.get("moment_kNm")) or 0.0) for row in rows), default=0.0)
        peak_axial = max((abs(_optional_float(row.get("axial_force_kN")) or 0.0) for row in rows), default=0.0)
        peak_shear = max((abs(_optional_float(row.get("shear_kN")) or 0.0) for row in rows), default=0.0)
        peak_strain = max((abs(_optional_float(row.get("longitudinal_strain")) or 0.0) for row in rows), default=0.0)

        utilizations = [_sample_utilization(row, thresholds) for row in rows]
        max_utilization, governing_mode = max(utilizations, key=lambda item: (item[0], item[1]))

        ring_summaries.append(
            {
                "ring_id": ring_id,
                "sample_count": int(len(rows)),
                "peak_moment_kNm": float(peak_moment),
                "peak_axial_force_kN": float(peak_axial),
                "peak_shear_kN": float(peak_shear),
                "peak_longitudinal_strain": float(peak_strain),
                "max_utilization": float(max_utilization),
                "governing_mode": str(governing_mode),
            }
        )

    ring_summaries.sort(key=lambda row: (-float(row["max_utilization"]), -float(row["peak_moment_kNm"]), str(row["ring_id"])))
    governing = ring_summaries[0] if ring_summaries else {
        "ring_id": "",
        "max_utilization": 0.0,
        "peak_moment_kNm": 0.0,
        "peak_axial_force_kN": 0.0,
        "peak_shear_kN": 0.0,
        "peak_longitudinal_strain": 0.0,
        "governing_mode": "not_available",
    }
    return ring_summaries, governing


def _benchmark_row(
    *,
    metric: str,
    value: float,
    threshold: float,
    unit: str,
    comparison: str,
    evaluated: bool = True,
    note: str = "",
) -> dict[str, Any]:
    if not evaluated:
        return {
            "metric": metric,
            "value": float(value),
            "threshold": float(threshold),
            "unit": unit,
            "comparison": comparison,
            "evaluated": False,
            "pass": True,
            "usage_ratio": 0.0,
            "margin": 0.0,
            "note": note,
        }

    if comparison == "<=":
        passed = bool(value <= threshold)
        usage_ratio = float(value / max(threshold, 1e-12))
        margin = float(threshold - value)
    elif comparison == ">=":
        passed = bool(value >= threshold)
        usage_ratio = float(threshold / max(value, 1e-12))
        margin = float(value - threshold)
    else:
        raise ValueError(f"unsupported comparison: {comparison}")

    return {
        "metric": metric,
        "value": float(value),
        "threshold": float(threshold),
        "unit": unit,
        "comparison": comparison,
        "evaluated": True,
        "pass": bool(passed),
        "usage_ratio": float(usage_ratio),
        "margin": float(margin),
        "note": note,
    }


def _maintenance_actions(benchmark_rows: list[dict[str, Any]]) -> tuple[str, list[str], str]:
    evaluated = [row for row in benchmark_rows if bool(row.get("evaluated", False))]
    if not evaluated:
        return "routine", ["continue_routine_monitoring"], "no evaluated maintenance benchmarks"

    governing = max(evaluated, key=lambda row: float(row.get("usage_ratio", 0.0)))
    governing_metric = str(governing.get("metric", ""))
    governing_ratio = float(governing.get("usage_ratio", 0.0))
    benchmark_pass = all(bool(row.get("pass", True)) for row in evaluated)

    actions: list[str] = []
    if governing_metric in {"max_abs_settlement_mm", "max_diff_settlement_mm"} or governing_ratio >= 0.75:
        actions.append("track_relevel_survey")
    if governing_metric == "min_clearance_mm" or any(str(row.get("metric")) == "min_clearance_mm" and float(row.get("margin", 0.0)) < 10.0 for row in evaluated):
        actions.append("clearance_recheck_before_speed_change")
    if any(str(row.get("metric")) == "max_lining_utilization" and float(row.get("usage_ratio", 0.0)) >= 0.75 for row in evaluated):
        actions.append("lining_joint_detail_inspection")
    if any(str(row.get("metric")) == "max_vibration_velocity_mm_s" and float(row.get("usage_ratio", 0.0)) >= 0.75 for row in evaluated):
        actions.append("rail_grinding_and_fastener_review")
    if not actions:
        actions.append("continue_routine_monitoring")

    if not benchmark_pass or governing_ratio >= 1.0:
        priority = "urgent"
    elif governing_ratio >= 0.85:
        priority = "inspect_soon"
    else:
        priority = "routine"

    status_line = f"maintenance={priority} | governing_metric={governing_metric} | usage={governing_ratio:.3f}"
    return priority, sorted(set(actions)), status_line


def build_postprocess_report(
    case_payload: dict[str, Any],
    *,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    validate_input_contract(case_payload, POSTPROCESS_INPUT_SCHEMA, label="rail_tunnel_postprocess")

    metadata = case_payload.get("metadata", {})
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object when provided")
    metadata = metadata if isinstance(metadata, dict) else {}

    track_samples = list(case_payload["track_samples"])
    lining_samples = list(case_payload["lining_samples"])
    vibration_samples = list(case_payload.get("vibration_samples", []))

    track_samples.sort(key=lambda row: (_require_float(row.get("chainage_m"), "track_samples[].chainage_m"), str(row.get("location_id", ""))))

    nominal_clearance_mm = _optional_float(metadata.get("nominal_clearance_mm"))
    if nominal_clearance_mm is None:
        nominal_clearance_mm = float(thresholds["nominal_clearance_mm"])

    rail_settlements = [_require_float(row.get("rail_settlement_mm"), "track_samples[].rail_settlement_mm") for row in track_samples]
    tunnel_settlements = [float(_optional_float(row.get("tunnel_crown_settlement_mm")) or 0.0) for row in track_samples]
    clearances = [float(_sample_clearance_mm(row, nominal_clearance_mm) or 0.0) for row in track_samples]

    differential_rows: list[dict[str, Any]] = []
    max_diff_settlement_mm = 0.0
    max_gradient_mm_per_m = 0.0
    for prev, curr in zip(track_samples, track_samples[1:]):
        prev_chainage = _require_float(prev.get("chainage_m"), "track_samples[].chainage_m")
        curr_chainage = _require_float(curr.get("chainage_m"), "track_samples[].chainage_m")
        span = max(curr_chainage - prev_chainage, 1e-12)
        diff = abs(
            _require_float(curr.get("rail_settlement_mm"), "track_samples[].rail_settlement_mm")
            - _require_float(prev.get("rail_settlement_mm"), "track_samples[].rail_settlement_mm")
        )
        gradient = diff / span
        max_diff_settlement_mm = max(max_diff_settlement_mm, diff)
        max_gradient_mm_per_m = max(max_gradient_mm_per_m, gradient)
        differential_rows.append(
            {
                "from_chainage_m": float(prev_chainage),
                "to_chainage_m": float(curr_chainage),
                "differential_settlement_mm": float(diff),
                "gradient_mm_per_m": float(gradient),
            }
        )

    ring_summaries, governing_ring = _summarize_lining_samples(lining_samples, thresholds)

    vibration_values = [float(_optional_float(row.get("velocity_mm_s")) or 0.0) for row in vibration_samples]
    vibration_eval = bool(vibration_values)
    max_vibration_velocity = max(vibration_values) if vibration_values else 0.0
    p95_index = max(0, int(round(0.95 * max(len(vibration_values), 1))) - 1)
    vibration_sorted = sorted(vibration_values)
    vibration_p95 = vibration_sorted[p95_index] if vibration_sorted else 0.0

    benchmark_rows = [
        _benchmark_row(
            metric="max_abs_settlement_mm",
            value=max(abs(value) for value in rail_settlements),
            threshold=thresholds["max_abs_settlement_mm"],
            unit="mm",
            comparison="<=",
        ),
        _benchmark_row(
            metric="max_diff_settlement_mm",
            value=max_diff_settlement_mm,
            threshold=thresholds["max_diff_settlement_mm"],
            unit="mm",
            comparison="<=",
        ),
        _benchmark_row(
            metric="min_clearance_mm",
            value=min(clearances),
            threshold=thresholds["min_clearance_mm"],
            unit="mm",
            comparison=">=",
        ),
        _benchmark_row(
            metric="max_lining_utilization",
            value=float(governing_ring["max_utilization"]),
            threshold=thresholds["max_lining_utilization"],
            unit="ratio",
            comparison="<=",
        ),
        _benchmark_row(
            metric="max_vibration_velocity_mm_s",
            value=max_vibration_velocity,
            threshold=thresholds["max_vibration_velocity_mm_s"],
            unit="mm/s",
            comparison="<=",
            evaluated=vibration_eval,
            note="" if vibration_eval else "no vibration_samples provided",
        ),
    ]

    evaluated_rows = [row for row in benchmark_rows if bool(row.get("evaluated", False))]
    benchmark_pass = bool(all(bool(row.get("pass", True)) for row in evaluated_rows))
    governing_row = max(evaluated_rows, key=lambda row: float(row.get("usage_ratio", 0.0))) if evaluated_rows else None
    maintenance_priority, maintenance_actions, maintenance_line = _maintenance_actions(benchmark_rows)
    reason_code = "PASS" if benchmark_pass else "ERR_BENCHMARK_FAIL"

    summary_line = (
        f"Rail/tunnel postprocess: {reason_code.replace('ERR_', '').replace('_', ' ')} | "
        f"settlement={max(abs(value) for value in rail_settlements):.3f}/{thresholds['max_abs_settlement_mm']:.3f}mm | "
        f"diff={max_diff_settlement_mm:.3f}/{thresholds['max_diff_settlement_mm']:.3f}mm | "
        f"clearance={min(clearances):.3f}/{thresholds['min_clearance_mm']:.3f}mm | "
        f"utilization={float(governing_ring['max_utilization']):.3f}/{thresholds['max_lining_utilization']:.3f}"
    )
    if vibration_eval:
        summary_line += (
            f" | vibration={max_vibration_velocity:.3f}/{thresholds['max_vibration_velocity_mm_s']:.3f}mm/s"
        )
    summary_line += f" | {maintenance_line}"

    return {
        "schema_version": "1.0",
        "run_id": "phase1-rail-tunnel-postprocess",
        "generated_at": _now_iso(),
        "inputs": {
            "case_id": str(case_payload["case_id"]),
            "source_mode": str(metadata.get("source_mode", "combined_input_json")),
            "thresholds": thresholds,
            "track_sample_count": int(len(track_samples)),
            "lining_sample_count": int(len(lining_samples)),
            "vibration_sample_count": int(len(vibration_samples)),
        },
        "checks": {
            "track_samples_present": bool(len(track_samples) >= 2),
            "lining_samples_present": bool(len(lining_samples) >= 1),
            "benchmark_pass": bool(benchmark_pass),
            "vibration_evaluated": bool(vibration_eval),
        },
        "summaries": {
            "settlement": {
                "max_abs_rail_settlement_mm": float(max(abs(value) for value in rail_settlements)),
                "max_abs_tunnel_crown_settlement_mm": float(max(abs(value) for value in tunnel_settlements)),
                "max_combined_settlement_mm": float(
                    max(abs(rail) + abs(tunnel) for rail, tunnel in zip(rail_settlements, tunnel_settlements))
                ),
                "max_diff_settlement_mm": float(max_diff_settlement_mm),
                "max_gradient_mm_per_m": float(max_gradient_mm_per_m),
            },
            "clearance": {
                "min_clearance_mm": float(min(clearances)),
                "clearance_margin_mm": float(min(clearances) - thresholds["min_clearance_mm"]),
                "nominal_clearance_mm": float(nominal_clearance_mm),
                "max_clearance_loss_mm": float(max(nominal_clearance_mm - value for value in clearances)),
            },
            "lining_response": {
                "ring_count": int(len(ring_summaries)),
                "governing_ring_id": str(governing_ring["ring_id"]),
                "peak_moment_kNm": float(max(row["peak_moment_kNm"] for row in ring_summaries)),
                "peak_axial_force_kN": float(max(row["peak_axial_force_kN"] for row in ring_summaries)),
                "peak_shear_kN": float(max(row["peak_shear_kN"] for row in ring_summaries)),
                "peak_longitudinal_strain": float(max(row["peak_longitudinal_strain"] for row in ring_summaries)),
            },
            "utilization": {
                "max_lining_utilization": float(governing_ring["max_utilization"]),
                "governing_mode": str(governing_ring["governing_mode"]),
                "governing_ring_id": str(governing_ring["ring_id"]),
            },
            "vibration": {
                "evaluated": bool(vibration_eval),
                "max_velocity_mm_s": float(max_vibration_velocity),
                "p95_velocity_mm_s": float(vibration_p95),
            },
            "maintenance": {
                "priority": maintenance_priority,
                "recommended_actions": maintenance_actions,
                "status_line": maintenance_line,
            },
        },
        "track_samples_head": track_samples[:16],
        "track_differential_head": differential_rows[:16],
        "lining_ring_summaries": ring_summaries[:16],
        "vibration_samples_head": vibration_samples[:16],
        "benchmark_rows": benchmark_rows,
        "summary_line": summary_line,
        "contract_pass": bool(benchmark_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "benchmark_overview": {
            "governing_metric": str(governing_row.get("metric", "")) if governing_row else "",
            "governing_usage_ratio": float(governing_row.get("usage_ratio", 0.0)) if governing_row else 0.0,
            "passed_count": int(sum(1 for row in evaluated_rows if bool(row.get("pass", True)))),
            "evaluated_count": int(len(evaluated_rows)),
        },
    }


def build_benchmark_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "phase1-rail-tunnel-postprocess-benchmark",
        "generated_at": _now_iso(),
        "case_id": str((report.get("inputs") or {}).get("case_id", "")),
        "thresholds": dict(((report.get("inputs") or {}).get("thresholds") or {})),
        "benchmark_rows": list(report.get("benchmark_rows", [])),
        "summary_line": str(report.get("summary_line", "")),
        "contract_pass": bool(report.get("contract_pass", False)),
        "reason_code": str(report.get("reason_code", "ERR_INVALID_INPUT")),
        "reason": str(report.get("reason", REASONS["ERR_INVALID_INPUT"])),
    }


def _coerce_track_samples_from_reports(
    track_report: dict[str, Any],
    tunnel_report: dict[str, Any] | None,
    nominal_clearance_mm: float,
) -> list[dict[str, Any]]:
    if not bool(track_report.get("contract_pass", False)):
        raise ValueError("track report contract_pass is false")

    length_m = float(((track_report.get("inputs") or {}).get("length_m")) or 0.0)
    w_mid_m = float((((track_report.get("benchmarks") or {}).get("timoshenko") or {}).get("w_mid_m")) or 0.0)
    if length_m <= 0.0:
        raise ValueError("track report length_m is missing")

    tunnel_disp_m = 0.0
    if tunnel_report is not None:
        if not bool(tunnel_report.get("contract_pass", False)):
            raise ValueError("tunnel seismic report contract_pass is false")
        tunnel_disp_m = float(((tunnel_report.get("metrics") or {}).get("max_disp_m")) or 0.0)

    rail_mm = abs(w_mid_m) * 1000.0
    tunnel_mm = abs(tunnel_disp_m) * 1000.0
    mid_clearance = float(nominal_clearance_mm - rail_mm - tunnel_mm)

    return [
        {
            "location_id": "track_left",
            "chainage_m": 0.0,
            "rail_settlement_mm": 0.0,
            "tunnel_crown_settlement_mm": 0.0,
            "clearance_mm": float(nominal_clearance_mm),
        },
        {
            "location_id": "track_midspan",
            "chainage_m": float(length_m * 0.5),
            "rail_settlement_mm": float(-rail_mm),
            "tunnel_crown_settlement_mm": float(-tunnel_mm),
            "clearance_mm": float(mid_clearance),
        },
        {
            "location_id": "track_right",
            "chainage_m": float(length_m),
            "rail_settlement_mm": 0.0,
            "tunnel_crown_settlement_mm": 0.0,
            "clearance_mm": float(nominal_clearance_mm),
        },
    ]


def _coerce_lining_samples_from_reports(
    segment_report: dict[str, Any] | None,
    tunnel_report: dict[str, Any] | None,
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    if segment_report is None and tunnel_report is None:
        raise ValueError("at least one lining source report is required")

    samples: list[dict[str, Any]] = []
    if segment_report is not None:
        if not bool(segment_report.get("contract_pass", False)):
            raise ValueError("segment report contract_pass is false")
        peak_moment = float(((segment_report.get("metrics") or {}).get("peak_moment_n_m")) or 0.0) / 1000.0
        post_peak = float(((segment_report.get("metrics") or {}).get("post_peak_max_n_m")) or 0.0) / 1000.0
        samples.append(
            {
                "ring_id": "joint_peak",
                "position_deg": 0.0,
                "moment_kNm": float(peak_moment),
                "moment_capacity_kNm": float(thresholds["lining_moment_capacity_kNm"]),
                "utilization": float(peak_moment / max(thresholds["lining_moment_capacity_kNm"], 1e-12)),
            }
        )
        samples.append(
            {
                "ring_id": "joint_residual",
                "position_deg": 180.0,
                "moment_kNm": float(post_peak),
                "moment_capacity_kNm": float(thresholds["lining_moment_capacity_kNm"]),
            }
        )

    if tunnel_report is not None:
        if not bool(tunnel_report.get("contract_pass", False)):
            raise ValueError("tunnel seismic report contract_pass is false")
        peak_strain = float(((tunnel_report.get("metrics") or {}).get("max_longitudinal_strain")) or 0.0)
        peak_disp_mm = float(((tunnel_report.get("metrics") or {}).get("max_disp_m")) or 0.0) * 1000.0
        samples.append(
            {
                "ring_id": "longitudinal_global",
                "position_deg": 90.0,
                "moment_kNm": float(peak_disp_mm * 2.0),
                "moment_capacity_kNm": float(thresholds["lining_moment_capacity_kNm"]),
                "longitudinal_strain": float(peak_strain),
                "strain_capacity": float(thresholds["lining_strain_capacity"]),
            }
        )

    return samples


def _coerce_vibration_samples_from_report(vibration_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if vibration_report is None:
        return []
    if not bool(vibration_report.get("contract_pass", False)):
        raise ValueError("vibration report contract_pass is false")
    rows = vibration_report.get("curve_head", [])
    if not isinstance(rows, list):
        raise ValueError("vibration report curve_head must be an array")
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        vel = _optional_float(row.get("velocity_mm_s"))
        if vel is None:
            continue
        out.append(
            {
                "location_id": str(row.get("location_id", f"vib_{idx:03d}")),
                "chainage_m": float(_optional_float(row.get("distance_m")) or idx),
                "freq_hz": float(_optional_float(row.get("freq_hz")) or 0.0),
                "velocity_mm_s": float(vel),
            }
        )
    return out


def _build_case_from_component_reports(
    *,
    track_report_path: str | None,
    tunnel_seismic_report_path: str | None,
    segment_report_path: str | None,
    vibration_report_path: str | None,
    nominal_clearance_mm: float,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    track_report = _load_json(track_report_path) if track_report_path else None
    tunnel_report = _load_json(tunnel_seismic_report_path) if tunnel_seismic_report_path else None
    segment_report = _load_json(segment_report_path) if segment_report_path else None
    vibration_report = _load_json(vibration_report_path) if vibration_report_path else None

    if track_report is None:
        raise ValueError("track-report is required when building from component reports")

    case_payload = {
        "case_id": "rail_tunnel_component_reports",
        "metadata": {
            "source_mode": "phase1_component_reports",
            "track_report": track_report_path or "",
            "tunnel_seismic_report": tunnel_seismic_report_path or "",
            "segment_report": segment_report_path or "",
            "vibration_report": vibration_report_path or "",
            "nominal_clearance_mm": float(nominal_clearance_mm),
        },
        "track_samples": _coerce_track_samples_from_reports(track_report, tunnel_report, nominal_clearance_mm),
        "lining_samples": _coerce_lining_samples_from_reports(segment_report, tunnel_report, thresholds),
        "vibration_samples": _coerce_vibration_samples_from_report(vibration_report),
    }
    validate_input_contract(case_payload, POSTPROCESS_INPUT_SCHEMA, label="rail_tunnel_postprocess.component_reports")
    return case_payload


def resolve_case_payload(
    *,
    input_path: str | None,
    track_report_path: str | None,
    tunnel_seismic_report_path: str | None,
    segment_report_path: str | None,
    vibration_report_path: str | None,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    component_paths = [
        track_report_path,
        tunnel_seismic_report_path,
        segment_report_path,
        vibration_report_path,
    ]
    using_components = any(path for path in component_paths)
    using_input = bool(input_path)

    if using_input and using_components:
        raise ValueError("use either --input or component report arguments, not both")

    if using_input:
        case_payload = _load_json(input_path)
        validate_input_contract(case_payload, POSTPROCESS_INPUT_SCHEMA, label="rail_tunnel_postprocess")
        metadata = case_payload.get("metadata", {})
        if isinstance(metadata, dict) and "source_mode" not in metadata:
            metadata = dict(metadata)
            metadata["source_mode"] = "combined_input_json"
            case_payload = dict(case_payload)
            case_payload["metadata"] = metadata
        return case_payload

    if using_components:
        return _build_case_from_component_reports(
            track_report_path=track_report_path,
            tunnel_seismic_report_path=tunnel_seismic_report_path,
            segment_report_path=segment_report_path,
            vibration_report_path=vibration_report_path,
            nominal_clearance_mm=thresholds["nominal_clearance_mm"],
            thresholds=thresholds,
        )

    case_payload = _default_case_payload()
    case_payload["benchmarks"] = thresholds
    validate_input_contract(case_payload, POSTPROCESS_INPUT_SCHEMA, label="rail_tunnel_postprocess.demo")
    return case_payload


def run_postprocess(
    *,
    input_path: str | None,
    track_report_path: str | None,
    tunnel_seismic_report_path: str | None,
    segment_report_path: str | None,
    vibration_report_path: str | None,
    max_abs_settlement_mm: float | None,
    max_diff_settlement_mm: float | None,
    min_clearance_mm: float | None,
    max_lining_utilization: float | None,
    max_vibration_velocity_mm_s: float | None,
    nominal_clearance_mm: float | None,
    lining_moment_capacity_kNm: float | None,
    lining_strain_capacity: float | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    seed_case = _load_json(input_path) if input_path else _default_case_payload()
    thresholds = _merge_thresholds(
        seed_case,
        max_abs_settlement_mm=max_abs_settlement_mm,
        max_diff_settlement_mm=max_diff_settlement_mm,
        min_clearance_mm=min_clearance_mm,
        max_lining_utilization=max_lining_utilization,
        max_vibration_velocity_mm_s=max_vibration_velocity_mm_s,
        nominal_clearance_mm=nominal_clearance_mm,
        lining_moment_capacity_kNm=lining_moment_capacity_kNm,
        lining_strain_capacity=lining_strain_capacity,
    )

    case_payload = resolve_case_payload(
        input_path=input_path,
        track_report_path=track_report_path,
        tunnel_seismic_report_path=tunnel_seismic_report_path,
        segment_report_path=segment_report_path,
        vibration_report_path=vibration_report_path,
        thresholds=thresholds,
    )
    report = build_postprocess_report(case_payload, thresholds=thresholds)
    benchmark = build_benchmark_payload(report)
    return report, benchmark


def _error_payload(message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    report = {
        "schema_version": "1.0",
        "run_id": "phase1-rail-tunnel-postprocess",
        "generated_at": _now_iso(),
        "contract_pass": False,
        "reason_code": "ERR_INVALID_INPUT",
        "reason": f"{REASONS['ERR_INVALID_INPUT']}: {message}",
        "summary_line": f"Rail/tunnel postprocess: ERR INVALID INPUT | {message}",
        "benchmark_rows": [],
    }
    return report, build_benchmark_payload(report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--track-report")
    parser.add_argument("--tunnel-seismic-report")
    parser.add_argument("--segment-report")
    parser.add_argument("--vibration-report")
    parser.add_argument("--max-abs-settlement-mm", type=float)
    parser.add_argument("--max-diff-settlement-mm", type=float)
    parser.add_argument("--min-clearance-mm", type=float)
    parser.add_argument("--max-lining-utilization", type=float)
    parser.add_argument("--max-vibration-velocity-mm-s", type=float)
    parser.add_argument("--nominal-clearance-mm", type=float)
    parser.add_argument("--lining-moment-capacity-kNm", type=float)
    parser.add_argument("--lining-strain-capacity", type=float)
    parser.add_argument("--out", default="implementation/phase1/rail_tunnel_postprocess_report.json")
    parser.add_argument("--benchmark-out", default="implementation/phase1/rail_tunnel_postprocess_benchmark.json")
    args = parser.parse_args()

    try:
        report, benchmark = run_postprocess(
            input_path=str(args.input) if args.input else None,
            track_report_path=str(args.track_report) if args.track_report else None,
            tunnel_seismic_report_path=str(args.tunnel_seismic_report) if args.tunnel_seismic_report else None,
            segment_report_path=str(args.segment_report) if args.segment_report else None,
            vibration_report_path=str(args.vibration_report) if args.vibration_report else None,
            max_abs_settlement_mm=_optional_float(args.max_abs_settlement_mm),
            max_diff_settlement_mm=_optional_float(args.max_diff_settlement_mm),
            min_clearance_mm=_optional_float(args.min_clearance_mm),
            max_lining_utilization=_optional_float(args.max_lining_utilization),
            max_vibration_velocity_mm_s=_optional_float(args.max_vibration_velocity_mm_s),
            nominal_clearance_mm=_optional_float(args.nominal_clearance_mm),
            lining_moment_capacity_kNm=_optional_float(args.lining_moment_capacity_kNm),
            lining_strain_capacity=_optional_float(args.lining_strain_capacity),
        )
    except (InputContractError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        report, benchmark = _error_payload(str(exc))

    _write_json(args.out, report)
    _write_json(args.benchmark_out, benchmark)
    print(f"Wrote rail/tunnel postprocess report: {args.out}")
    print(f"Wrote rail/tunnel postprocess benchmark: {args.benchmark_out}")
    if not report.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
