#!/usr/bin/env python3
"""Results explorer for contour, mode shape, time-history, and envelope visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


@dataclass(frozen=True)
class ContourResult:
    """Contour plot data for structural results."""
    result_type: str
    values: tuple[float, ...]
    min_value: float
    max_value: float
    mean_value: float
    locations: tuple[tuple[float, float], ...]
    state_tag: str


@dataclass(frozen=True)
class ModeShapeResult:
    """Mode shape data for modal analysis."""
    mode_number: int
    frequency_hz: float
    period_s: float
    participation_factor_x: float
    participation_factor_y: float
    participation_factor_z: float
    modal_mass_ratio_x: float
    modal_mass_ratio_y: float
    modal_mass_ratio_z: float
    amplitudes: tuple[float, ...]
    state_tag: str


@dataclass(frozen=True)
class TimeHistoryResult:
    """Time-history result data."""
    result_type: str
    time_steps: tuple[float, ...]
    values: tuple[float, ...]
    peak_value: float
    peak_time: float
    rms_value: float
    state_tag: str


@dataclass(frozen=True)
class EnvelopeResult:
    """Envelope result data."""
    result_type: str
    max_values: tuple[float, ...]
    min_values: tuple[float, ...]
    max_locations: tuple[tuple[float, float], ...]
    min_locations: tuple[tuple[float, float], ...]
    governing_max: float
    governing_min: float
    state_tag: str


def evaluate_contour(
    *,
    result_type: str,
    values: tuple[float, ...],
    locations: tuple[tuple[float, float], ...],
) -> ContourResult:
    """Evaluate contour plot data."""
    if not values:
        return ContourResult(
            result_type=result_type,
            values=(),
            min_value=0.0,
            max_value=0.0,
            mean_value=0.0,
            locations=(),
            state_tag="empty",
        )
    
    min_val = min(values)
    max_val = max(values)
    mean_val = sum(values) / len(values)
    
    return ContourResult(
        result_type=result_type,
        values=values,
        min_value=min_val,
        max_value=max_val,
        mean_value=mean_val,
        locations=locations,
        state_tag="contour",
    )


def evaluate_mode_shape(
    *,
    mode_number: int,
    frequency_hz: float,
    amplitudes: tuple[float, ...],
    participation_factors: tuple[float, float, float] = (1.0, 0.0, 0.0),
    modal_mass_ratios: tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> ModeShapeResult:
    """Evaluate mode shape data."""
    freq = max(float(frequency_hz), 1e-9)
    period = 1.0 / freq
    
    return ModeShapeResult(
        mode_number=mode_number,
        frequency_hz=freq,
        period_s=period,
        participation_factor_x=float(participation_factors[0]),
        participation_factor_y=float(participation_factors[1]),
        participation_factor_z=float(participation_factors[2]),
        modal_mass_ratio_x=float(modal_mass_ratios[0]),
        modal_mass_ratio_y=float(modal_mass_ratios[1]),
        modal_mass_ratio_z=float(modal_mass_ratios[2]),
        amplitudes=amplitudes,
        state_tag="mode_shape",
    )


def evaluate_time_history(
    *,
    result_type: str,
    time_steps: tuple[float, ...],
    values: tuple[float, ...],
) -> TimeHistoryResult:
    """Evaluate time-history result data."""
    if not values or not time_steps:
        return TimeHistoryResult(
            result_type=result_type,
            time_steps=(),
            values=(),
            peak_value=0.0,
            peak_time=0.0,
            rms_value=0.0,
            state_tag="empty",
        )
    
    peak_val = max(abs(v) for v in values)
    peak_idx = max(range(len(values)), key=lambda i: abs(values[i]))
    peak_time = time_steps[peak_idx] if peak_idx < len(time_steps) else 0.0
    rms_val = math.sqrt(sum(v**2 for v in values) / len(values))
    
    return TimeHistoryResult(
        result_type=result_type,
        time_steps=time_steps,
        values=values,
        peak_value=peak_val,
        peak_time=peak_time,
        rms_value=rms_val,
        state_tag="time_history",
    )


def evaluate_envelope(
    *,
    result_type: str,
    max_values: tuple[float, ...],
    min_values: tuple[float, ...],
    locations: tuple[tuple[float, float], ...],
) -> EnvelopeResult:
    """Evaluate envelope result data."""
    if not max_values or not min_values:
        return EnvelopeResult(
            result_type=result_type,
            max_values=(),
            min_values=(),
            max_locations=(),
            min_locations=(),
            governing_max=0.0,
            governing_min=0.0,
            state_tag="empty",
        )
    
    governing_max = max(max_values)
    governing_min = min(min_values)
    
    max_loc = locations[:len(max_values)]
    min_loc = locations[:len(min_values)]
    
    return EnvelopeResult(
        result_type=result_type,
        max_values=max_values,
        min_values=min_values,
        max_locations=max_loc,
        min_locations=min_loc,
        governing_max=governing_max,
        governing_min=governing_min,
        state_tag="envelope",
    )


def build_results_summary(
    *,
    contour: ContourResult | None = None,
    mode_shapes: tuple[ModeShapeResult, ...] = (),
    time_histories: tuple[TimeHistoryResult, ...] = (),
    envelope: EnvelopeResult | None = None,
) -> dict[str, Any]:
    """Build summary of all results."""
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "result_types": [],
        "state_tags": [],
    }
    
    if contour is not None:
        summary["result_types"].append(contour.result_type)
        summary["state_tags"].append(contour.state_tag)
        summary["contour"] = {
            "result_type": contour.result_type,
            "min_value": contour.min_value,
            "max_value": contour.max_value,
            "mean_value": contour.mean_value,
            "value_count": len(contour.values),
        }
    
    if mode_shapes:
        summary["result_types"].append("modal")
        summary["state_tags"].append("mode_shape")
        summary["modal"] = {
            "mode_count": len(mode_shapes),
            "fundamental_frequency_hz": mode_shapes[0].frequency_hz if mode_shapes else 0.0,
            "fundamental_period_s": mode_shapes[0].period_s if mode_shapes else 0.0,
        }
    
    if time_histories:
        summary["result_types"].append("time_history")
        summary["state_tags"].append("time_history")
        summary["time_history"] = {
            "history_count": len(time_histories),
            "peak_values": [h.peak_value for h in time_histories],
            "rms_values": [h.rms_value for h in time_histories],
        }
    
    if envelope is not None:
        summary["result_types"].append(envelope.result_type)
        summary["state_tags"].append(envelope.state_tag)
        summary["envelope"] = {
            "result_type": envelope.result_type,
            "governing_max": envelope.governing_max,
            "governing_min": envelope.governing_min,
        }
    
    summary["state_tags"] = tuple(sorted(set(summary["state_tags"])))
    summary["result_types"] = tuple(sorted(set(summary["result_types"])))
    
    return summary


__all__ = [
    "ContourResult",
    "ModeShapeResult",
    "TimeHistoryResult",
    "EnvelopeResult",
    "evaluate_contour",
    "evaluate_mode_shape",
    "evaluate_time_history",
    "evaluate_envelope",
    "build_results_summary",
]
