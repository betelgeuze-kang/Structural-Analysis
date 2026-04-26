#!/usr/bin/env python3
"""Calibrate optimization objective scales from design-change evidence."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Any

from design_optimization_env import DesignOptimizationConfig


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _profile_path(path: str | Path | None = None) -> Path:
    if path is None:
        return Path(__file__).with_name("design_objective_profiles.json")
    return Path(path)


def load_objective_profiles(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    payload = _load_json(_profile_path(path))
    profiles: dict[str, dict[str, float]] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        profiles[str(key)] = {str(k): float(v) for k, v in value.items()}
    return profiles


def calibrate_objective_weights(
    *,
    dataset_report: dict[str, Any],
    change_summary: dict[str, Any],
    solver_loop_report: dict[str, Any],
    wind_report: dict[str, Any],
    ssi_report: dict[str, Any],
    base_cfg: DesignOptimizationConfig,
) -> dict[str, Any]:
    dataset_summary = dataset_report.get("summary", {}) if isinstance(dataset_report.get("summary"), dict) else {}
    solver_summary = solver_loop_report.get("summary", {}) if isinstance(solver_loop_report.get("summary"), dict) else {}
    wind_summary = wind_report.get("summary", {}) if isinstance(wind_report.get("summary"), dict) else {}
    ssi_summary = ssi_report.get("summary", {}) if isinstance(ssi_report.get("summary"), dict) else {}
    rows = change_summary.get("change_summary_rows") if isinstance(change_summary.get("change_summary_rows"), list) else []

    total_rows = max(len(rows), 1)
    perimeter_slab_rows = sum(
        1
        for row in rows
        if str(row.get("zone_label", "")).strip().lower() == "perimeter"
        and str(row.get("member_type", "")).strip().lower() == "slab"
    )
    transfer_core_rows = sum(
        1
        for row in rows
        if str(row.get("zone_label", "")).strip().lower() in {"transfer", "core"}
    )
    semantic_rows = sum(int(row.get("semantic_group_count", 0) or 0) for row in rows)
    worst_after_dcr = max((float(row.get("max_dcr_after_max", 0.0) or 0.0) for row in rows), default=0.0)

    perimeter_slab_ratio = float(perimeter_slab_rows) / float(total_rows)
    transfer_core_ratio = float(transfer_core_rows) / float(total_rows)
    semantic_ratio = float(semantic_rows) / float(max(sum(int(row.get("changed_group_count", 0) or 0) for row in rows), 1))
    wind_residual = float(wind_summary.get("residual_drift_pct_max_abs", 0.0) or 0.0)
    ssi_residual = float(ssi_summary.get("ssi_residual_drift_pct_max_abs", 0.0) or 0.0)
    global_residual = float(dataset_summary.get("residual_drift_pct_max_abs", 0.0) or 0.0)
    baseline_max_dcr = float(solver_summary.get("baseline_max_dcr", 0.0) or 0.0)
    final_max_dcr = float(solver_summary.get("final_max_dcr", 0.0) or 0.0)

    congestion_scale = float(
        base_cfg.congestion_penalty_scale
        * (1.0 + 0.35 * transfer_core_ratio + 0.15 * max(perimeter_slab_ratio - 0.5, 0.0))
    )
    detailing_scale = float(
        base_cfg.detailing_complexity_penalty_scale
        * (1.0 + 0.55 * semantic_ratio + 0.40 * max(worst_after_dcr - 0.90, 0.0))
    )
    robustness_scale = float(
        base_cfg.robustness_penalty_scale
        * (
            1.0
            + 0.70 * max(final_max_dcr - 0.85, 0.0)
            + 0.20 * max(baseline_max_dcr - 1.0, 0.0)
            + 0.20 * transfer_core_ratio
        )
    )
    multi_hazard_scale = float(
        base_cfg.multi_hazard_penalty_scale
        * (
            1.0
            + 0.45 * min(wind_residual / 0.05, 2.0)
            + 0.35 * min(ssi_residual / 0.05, 2.0)
            + 0.15 * min(global_residual / 0.50, 4.0)
        )
    )
    base_sensitivity = float(
        base_cfg.base_sensitivity
        * (1.0 + 0.12 * transfer_core_ratio + 0.08 * max(final_max_dcr - 0.90, 0.0))
    )

    calibrated_cfg = replace(
        base_cfg,
        congestion_penalty_scale=congestion_scale,
        detailing_complexity_penalty_scale=detailing_scale,
        robustness_penalty_scale=robustness_scale,
        multi_hazard_penalty_scale=multi_hazard_scale,
        base_sensitivity=base_sensitivity,
    )
    return {
        "base_config": asdict(base_cfg),
        "calibrated_config": asdict(calibrated_cfg),
        "signals": {
            "perimeter_slab_ratio": perimeter_slab_ratio,
            "transfer_core_ratio": transfer_core_ratio,
            "semantic_ratio": semantic_ratio,
            "worst_after_dcr": worst_after_dcr,
            "wind_residual_drift_pct": wind_residual,
            "ssi_residual_drift_pct": ssi_residual,
            "global_residual_drift_pct": global_residual,
            "baseline_max_dcr": baseline_max_dcr,
            "final_max_dcr": final_max_dcr,
        },
    }


def _overlay_profile(
    cfg: DesignOptimizationConfig,
    profile: dict[str, float],
) -> DesignOptimizationConfig:
    payload: dict[str, float] = {}
    if "cost_weight" in profile:
        payload["cost_weight"] = float(cfg.cost_weight) * float(profile["cost_weight"])
    if "constructability_weight" in profile:
        payload["constructability_weight"] = float(cfg.constructability_weight) * float(profile["constructability_weight"])
    if "congestion_weight" in profile:
        payload["congestion_weight"] = float(cfg.congestion_weight) * float(profile["congestion_weight"])
    if "detailing_complexity_weight" in profile:
        payload["detailing_complexity_weight"] = float(cfg.detailing_complexity_weight) * float(profile["detailing_complexity_weight"])
    if "robustness_weight" in profile:
        payload["robustness_weight"] = float(cfg.robustness_weight) * float(profile["robustness_weight"])
    if "multi_hazard_weight" in profile:
        payload["multi_hazard_weight"] = float(cfg.multi_hazard_weight) * float(profile["multi_hazard_weight"])
    if "drift_weight_multiplier" in profile:
        payload["drift_weight_multiplier"] = float(cfg.drift_weight_multiplier) * float(profile["drift_weight_multiplier"])
    if "residual_weight_multiplier" in profile:
        payload["residual_weight_multiplier"] = float(cfg.residual_weight_multiplier) * float(profile["residual_weight_multiplier"])
    if "connection_weight_multiplier" in profile:
        payload["connection_weight_multiplier"] = float(cfg.connection_weight_multiplier) * float(profile["connection_weight_multiplier"])
    if "ssi_weight_multiplier" in profile:
        payload["ssi_weight_multiplier"] = float(cfg.ssi_weight_multiplier) * float(profile["ssi_weight_multiplier"])
    return replace(cfg, **payload) if payload else cfg


def apply_objective_calibration(
    cfg: DesignOptimizationConfig,
    calibration_report: dict[str, Any] | None,
) -> DesignOptimizationConfig:
    if not calibration_report:
        return cfg
    calibrated = calibration_report.get("calibrated_config")
    if not isinstance(calibrated, dict):
        return cfg
    payload = {}
    for field_name in DesignOptimizationConfig.__dataclass_fields__.keys():
        if field_name in calibrated:
            payload[field_name] = calibrated[field_name]
    if not payload:
        return cfg
    return replace(cfg, **payload)


def apply_objective_profile(
    cfg: DesignOptimizationConfig,
    *,
    profile_name: str = "balanced_practice",
    profile_path: str | Path | None = None,
) -> DesignOptimizationConfig:
    profiles = load_objective_profiles(profile_path)
    profile = profiles.get(str(profile_name), {})
    if not profile:
        return cfg
    return _overlay_profile(cfg, profile)


def build_objective_profile_report(
    *,
    base_cfg: DesignOptimizationConfig,
    calibration_report: dict[str, Any] | None,
    profile_name: str,
    profile_path: str | Path | None = None,
    project_type: str = "generic",
    why_selected: str = "",
) -> dict[str, Any]:
    calibrated_cfg = apply_objective_calibration(base_cfg, calibration_report)
    final_cfg = apply_objective_profile(calibrated_cfg, profile_name=profile_name, profile_path=profile_path)
    profiles = load_objective_profiles(profile_path)
    profile = profiles.get(str(profile_name), {})
    return {
        "profile_name": str(profile_name),
        "project_type": str(project_type),
        "why_selected": str(why_selected or f"profile overlay applied: {profile_name}"),
        "base_weights": {
            "cost_weight": float(base_cfg.cost_weight),
            "constructability_weight": float(base_cfg.constructability_weight),
            "congestion_weight": float(base_cfg.congestion_weight),
            "detailing_complexity_weight": float(base_cfg.detailing_complexity_weight),
            "robustness_weight": float(base_cfg.robustness_weight),
            "multi_hazard_weight": float(base_cfg.multi_hazard_weight),
        },
        "profile_multipliers": dict(profile),
        "final_weights": {
            "cost_weight": float(final_cfg.cost_weight),
            "constructability_weight": float(final_cfg.constructability_weight),
            "congestion_weight": float(final_cfg.congestion_weight),
            "detailing_complexity_weight": float(final_cfg.detailing_complexity_weight),
            "robustness_weight": float(final_cfg.robustness_weight),
            "multi_hazard_weight": float(final_cfg.multi_hazard_weight),
            "drift_weight_multiplier": float(final_cfg.drift_weight_multiplier),
            "residual_weight_multiplier": float(final_cfg.residual_weight_multiplier),
            "connection_weight_multiplier": float(final_cfg.connection_weight_multiplier),
            "ssi_weight_multiplier": float(final_cfg.ssi_weight_multiplier),
        },
    }


__all__ = [
    "apply_objective_calibration",
    "apply_objective_profile",
    "build_objective_profile_report",
    "calibrate_objective_weights",
    "load_objective_profiles",
]
