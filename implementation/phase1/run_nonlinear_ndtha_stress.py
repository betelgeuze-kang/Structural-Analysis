#!/usr/bin/env python3
"""Nonlinear Dynamic Time-History (NDTHA) collapse stress gate.

This gate targets two hard constraints:
1) geometric nonlinearity must be enabled (pdelta_factor >= 1.0)
2) time-history with load reversals must converge under nonlinear response

Implementation uses Rust nonlinear frame solver as the restoring-force corrector
inside an implicit Newmark fixed-point loop.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import time
import re
from typing import Any

import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile
from section_family_library import evaluate_story_section_profile
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    RustNonlinearNdthaConfig,
    build_story_load_profile,
    consume_dlpack_bundle,
    solve_nonlinear_frame_ndtha,
)
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


G = 9.80665

REASONS = {
    "PASS": "ndtha nonlinear collapse stress passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CASES": "benchmark cases missing/invalid",
    "ERR_GM_INPUT": "ground-motion input is missing or invalid",
    "ERR_PDELTA_DISABLED": "geometric nonlinearity is disabled (pdelta_factor < 1.0)",
    "ERR_DYNAMICS_NOT_REVERSED": "ground-motion sequence lacks dynamic load reversals",
    "ERR_RAYLEIGH_DAMPING_DISABLED": "rayleigh damping is disabled (alpha=0 and beta=0)",
    "ERR_ENGINE_FAIL": "rust nonlinear solver failed during ndtha step iterations",
    "ERR_NDTHA_CONVERGENCE_FAIL": "ndtha fixed-point loop diverged at one or more steps",
    "ERR_COLLAPSE_CUTOFF": "collapse drift threshold exceeded; run marked as COLLAPSED",
    "ERR_PLASTICITY_NOT_TRIGGERED": "ndtha run did not trigger plastic stories",
}


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "target_split",
        "ground_motion_csv",
        "min_case_count",
        "max_case_count",
        "ag_scale",
        "yield_drift_scale",
        "hardening_ratio",
        "pdelta_factor",
        "dt_scale",
        "newmark_beta",
        "newmark_gamma",
        "max_step_iterations",
        "step_tol",
        "adaptive_load_decay",
        "damping_force_cap_ratio",
        "min_load_reversals",
        "min_plastic_story_count",
        "collapse_drift_threshold_pct",
        "rayleigh_alpha",
        "rayleigh_beta",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "ground_motion_csv": {"type": "string", "minLength": 1},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "ag_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "yield_drift_scale": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "hardening_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pdelta_factor": {"type": "number", "minimum": 0.0},
        "dt_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "newmark_beta": {"type": "number", "exclusiveMinimum": 0.0},
        "newmark_gamma": {"type": "number", "exclusiveMinimum": 0.0},
        "max_step_iterations": {"type": "integer", "minimum": 1},
        "step_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "adaptive_load_decay": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "damping_force_cap_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "max_steps": {"type": "integer", "minimum": 2},
        "min_load_reversals": {"type": "integer", "minimum": 1},
        "min_plastic_story_count": {"type": "integer", "minimum": 1},
        "collapse_drift_threshold_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "rayleigh_alpha": {"type": "number", "minimum": 0.0},
        "rayleigh_beta": {"type": "number", "minimum": 0.0},
        "material_model": {"type": "string", "enum": ["steel_elastic_plastic", "rc_composite"]},
        "rc_cracking_strain": {"type": "number", "exclusiveMinimum": 0.0},
        "rc_creep_rate_per_hour": {"type": "number", "minimum": 0.0},
        "rc_bond_slip_ratio_ref": {"type": "number", "exclusiveMinimum": 0.0},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
        "response_npz_out": {"type": "string", "minLength": 1},
        "inline_response_limit": {"type": "integer", "minimum": 0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ground_motion(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 3:
        raise ValueError("ground-motion csv must have at least 3 rows")
    if "time_s" not in rows[0] or "accel_g" not in rows[0]:
        raise ValueError("ground-motion csv must contain time_s, accel_g columns")

    t = []
    ag = []
    for i, r in enumerate(rows):
        try:
            ti = float(r["time_s"])
            ai = float(r["accel_g"])
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"non-numeric ground-motion row at index {i}: {exc}") from exc
        t.append(ti)
        ag.append(ai)

    t_arr = np.asarray(t, dtype=np.float64)
    ag_arr = np.asarray(ag, dtype=np.float64)
    dt = float(t_arr[1] - t_arr[0])
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("ground-motion dt must be positive")
    if np.max(np.abs(np.diff(t_arr) - dt)) > 1e-6:
        raise ValueError("ground-motion time axis must have uniform dt")
    return t_arr, ag_arr


def _count_reversals(ag: np.ndarray, eps: float = 1e-6) -> int:
    if ag.size < 3:
        return 0
    signs = np.sign(ag)
    signs[np.abs(ag) <= eps] = 0.0
    rev = 0
    prev = 0.0
    for s in signs:
        if s == 0.0:
            continue
        if prev != 0.0 and s != prev:
            rev += 1
        prev = s
    return int(rev)


def _story_count_for_topology(topology: str) -> int:
    t = str(topology).strip().lower()
    if t == "outrigger":
        return 24
    if t == "wall-frame":
        return 20
    if t == "truss":
        return 16
    if t == "rahmen":
        return 12
    return 14


def _build_story_stiffness_from_drift(
    *,
    floor_load_n: np.ndarray,
    story_h_m: np.ndarray,
    drift_ratio_hf: float,
) -> np.ndarray:
    n = int(story_h_m.shape[0])
    s = np.linspace(1.0, 1.25, num=n, dtype=np.float64)
    shear = np.cumsum(np.flip(floor_load_n))
    shear = np.flip(shear)
    drift_ratio_target = max(1e-6, float(drift_ratio_hf))
    drift_denom = np.maximum(story_h_m * s, 1e-9)
    base = float(np.max(shear / drift_denom) / drift_ratio_target)
    return np.maximum(1e3, base) * s


def _drift_ratio_pct(u_story: np.ndarray, story_h_m: np.ndarray) -> float:
    if u_story.size == 0:
        return 0.0
    du = np.diff(np.concatenate([[0.0], u_story]))
    return 100.0 * float(np.max(np.abs(du / np.maximum(story_h_m, 1e-9))))


def _finite_abs_tail(values: list[float]) -> float:
    finite = [abs(float(v)) for v in values if math.isfinite(float(v))]
    return float(finite[-1]) if finite else math.nan


def _finite_abs_max(values: list[float]) -> float:
    finite = [abs(float(v)) for v in values if math.isfinite(float(v))]
    return float(max(finite)) if finite else math.nan


def _response_array(response: dict, key: str, *, dtype) -> np.ndarray:
    value = response.get(key, [])
    if value is None:
        return np.asarray([], dtype=dtype)
    return np.asarray(value, dtype=dtype).reshape(-1)


def _response_arrays_from_result(solved: dict) -> tuple[dict[str, np.ndarray], str]:
    specs: dict[str, Any] = {
        "top_displacement_m": np.float64,
        "drift_ratio_pct": np.float64,
        "base_shear_kN": np.float64,
        "core_drift_pct": np.float64,
        "core_shear_kN": np.float64,
        "step_iterations": np.int32,
        "step_plastic_story_count": np.int32,
        "step_residual_inf": np.float64,
        "story_drift_envelope_pct": np.float64,
        "final_story_drift_pct": np.float64,
    }
    artifacts = solved.get("device_artifacts")
    if isinstance(artifacts, dict) and bool(solved.get("device_artifacts_available", False)):
        try:
            tensors = consume_dlpack_bundle(artifacts)
            out: dict[str, np.ndarray] = {}
            for key, dtype in specs.items():
                tensor = tensors.get(str(key))
                if tensor is None:
                    out[str(key)] = np.asarray([], dtype=dtype)
                    continue
                out[str(key)] = np.asarray(tensor.detach().cpu().numpy(), dtype=dtype).reshape(-1)
            step_conv = tensors.get("step_converged")
            if step_conv is not None:
                out["step_converged"] = np.asarray(step_conv.detach().cpu().numpy(), dtype=np.bool_).reshape(-1)
            else:
                out["step_converged"] = np.asarray([], dtype=np.bool_)
            return out, "dlpack_zero_copy"
        except Exception:
            pass

    response = solved.get("response") if isinstance(solved.get("response"), dict) else {}
    out = {str(key): _response_array(response, str(key), dtype=dtype) for key, dtype in specs.items()}
    out["step_converged"] = _response_array(response, "step_converged", dtype=np.bool_)
    return out, "host_response"


def _response_series_row_count(response_arrays: dict[str, np.ndarray]) -> int:
    keys = (
        "top_displacement_m",
        "drift_ratio_pct",
        "base_shear_kN",
        "core_drift_pct",
        "core_shear_kN",
        "step_converged",
        "step_iterations",
        "step_plastic_story_count",
        "step_residual_inf",
    )
    lengths = [int(np.asarray(response_arrays.get(key, np.asarray([]))).reshape(-1).shape[0]) for key in keys]
    if not lengths or any(length <= 0 for length in lengths):
        return 0
    return int(min(lengths))


def _derive_series_kinematics(
    *,
    time_s: np.ndarray,
    top_displacement_m: np.ndarray,
    ground_acceleration_g: np.ndarray,
) -> dict[str, np.ndarray]:
    row_len = min(
        int(np.asarray(time_s).reshape(-1).shape[0]),
        int(np.asarray(top_displacement_m).reshape(-1).shape[0]),
        int(np.asarray(ground_acceleration_g).reshape(-1).shape[0]),
    )
    if row_len <= 0:
        empty = np.asarray([], dtype=np.float64)
        return {
            "top_velocity_mps": empty,
            "top_acceleration_mps2": empty,
            "ground_acceleration_g": empty,
        }

    time_axis = np.asarray(time_s[:row_len], dtype=np.float64)
    top = np.asarray(top_displacement_m[:row_len], dtype=np.float64)
    ground = np.asarray(ground_acceleration_g[:row_len], dtype=np.float64)
    if row_len == 1:
        velocity = np.zeros(1, dtype=np.float64)
        acceleration = np.zeros(1, dtype=np.float64)
    else:
        edge_order = 1 if row_len < 3 else 2
        velocity = np.asarray(np.gradient(top, time_axis, edge_order=edge_order), dtype=np.float64)
        acceleration = np.asarray(np.gradient(velocity, time_axis, edge_order=edge_order), dtype=np.float64)
    return {
        "top_velocity_mps": velocity,
        "top_acceleration_mps2": acceleration,
        "ground_acceleration_g": ground,
    }


def _default_response_npz_out(report_out: Path) -> Path:
    if report_out.suffix:
        return report_out.with_suffix(".response.npz")
    return report_out.parent / f"{report_out.name}.response.npz"


def _artifact_key_token(text: str, *, fallback: str) -> str:
    token = re.sub(r"[^0-9A-Za-z_]+", "_", str(text).strip())
    token = token.strip("_")
    return token or fallback


def _write_ndtha_response_npz(path: Path, rows: list[dict]) -> dict[str, object]:
    payload: dict[str, np.ndarray] = {}
    case_keys: list[str] = []
    case_ids: list[str] = []
    for idx, row in enumerate(rows):
        case_id = str(row.get("case_id", f"case_{idx+1}"))
        artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), dict) else {}
        prefix = str(artifacts.get("response_npz_key_prefix", f"case_{idx+1:03d}"))
        response = row.get("response_artifact_data") if isinstance(row.get("response_artifact_data"), dict) else {}
        if not response:
            continue
        case_keys.append(prefix)
        case_ids.append(case_id)
        payload[f"{prefix}__time_s"] = np.asarray(response.get("time_s", []), dtype=np.float64)
        payload[f"{prefix}__top_displacement_m"] = np.asarray(response.get("top_displacement_m", []), dtype=np.float64)
        payload[f"{prefix}__drift_ratio_pct"] = np.asarray(response.get("drift_ratio_pct", []), dtype=np.float64)
        payload[f"{prefix}__base_shear_kN"] = np.asarray(response.get("base_shear_kN", []), dtype=np.float64)
        payload[f"{prefix}__core_drift_pct"] = np.asarray(response.get("core_drift_pct", []), dtype=np.float64)
        payload[f"{prefix}__core_shear_kN"] = np.asarray(response.get("core_shear_kN", []), dtype=np.float64)
        payload[f"{prefix}__step_converged"] = np.asarray(response.get("step_converged", []), dtype=np.bool_)
        payload[f"{prefix}__step_iterations"] = np.asarray(response.get("step_iterations", []), dtype=np.int32)
        payload[f"{prefix}__step_plastic_story_count"] = np.asarray(response.get("step_plastic_story_count", []), dtype=np.int32)
        payload[f"{prefix}__step_residual_inf"] = np.asarray(response.get("step_residual_inf", []), dtype=np.float64)
        payload[f"{prefix}__story_drift_envelope_pct"] = np.asarray(response.get("story_drift_envelope_pct", []), dtype=np.float64)
        payload[f"{prefix}__final_story_drift_pct"] = np.asarray(response.get("final_story_drift_pct", []), dtype=np.float64)
        payload[f"{prefix}__top_velocity_mps"] = np.asarray(response.get("top_velocity_mps", []), dtype=np.float64)
        payload[f"{prefix}__top_acceleration_mps2"] = np.asarray(response.get("top_acceleration_mps2", []), dtype=np.float64)
        payload[f"{prefix}__ground_acceleration_g"] = np.asarray(response.get("ground_acceleration_g", []), dtype=np.float64)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["case_keys"] = np.asarray(case_keys, dtype="<U128")
    payload["case_ids"] = np.asarray(case_ids, dtype="<U128")
    np.savez_compressed(path, **payload)
    return {
        "path": str(path),
        "case_count": len(case_keys),
        "array_count": len(payload),
        "storage": "npz_external",
    }


def _build_ndtha_solver_control_summary(
    *,
    step_conv: np.ndarray,
    step_iters: np.ndarray,
    step_plastic: np.ndarray,
    step_resid: np.ndarray,
    dt: float,
    max_step_iterations: int,
    step_tol: float,
    adaptive_load_decay: float,
    collapsed: bool,
    collapse_step: int,
) -> dict[str, object]:
    row_len = min(len(step_conv), len(step_iters), len(step_plastic), len(step_resid))
    iteration_watch_threshold = max(2, int(math.ceil(float(max_step_iterations) * 0.75)))
    event_rows: list[dict[str, object]] = []
    cutback_steps: list[int] = []
    residual_spike_steps: list[int] = []
    plastic_transition_steps: list[int] = []
    nonconverged_steps: list[int] = []
    collapse_event_steps: list[int] = []
    prev_plastic = 0
    recommended_dt_scale_min = 1.0

    for i in range(row_len):
        converged = bool(step_conv[i])
        step_iter = int(step_iters[i])
        plastic_count = int(step_plastic[i])
        residual_inf = float(step_resid[i])
        is_collapse = bool(collapsed and collapse_step == i)
        tags: list[str] = []
        severity = "info"
        recommended_dt_scale = 1.0
        recommended_load_decay = float(adaptive_load_decay)

        if not converged:
            tags.append("step_nonconverged")
            severity = "error"
            recommended_dt_scale = min(recommended_dt_scale, 0.5)
            recommended_load_decay = min(recommended_load_decay, max(0.30, float(adaptive_load_decay) * 0.85))
            nonconverged_steps.append(i)
            cutback_steps.append(i)
        elif step_iter >= int(max_step_iterations):
            tags.append("iteration_budget_exhausted")
            severity = "warn"
            recommended_dt_scale = min(recommended_dt_scale, 0.5)
            recommended_load_decay = min(recommended_load_decay, max(0.35, float(adaptive_load_decay) * 0.90))
            cutback_steps.append(i)
        elif step_iter >= iteration_watch_threshold:
            tags.append("iteration_budget_near_limit")
            severity = "warn"
            recommended_dt_scale = min(recommended_dt_scale, 0.75)
            recommended_load_decay = min(recommended_load_decay, max(0.40, float(adaptive_load_decay) * 0.95))
            cutback_steps.append(i)

        residual_spike = bool((not math.isfinite(residual_inf)) or residual_inf > max(float(step_tol) * 25.0, 1e-9))
        if residual_spike:
            tags.append("residual_spike")
            severity = "error" if not converged else "warn"
            recommended_dt_scale = min(recommended_dt_scale, 0.5 if not converged else 0.75)
            recommended_load_decay = min(recommended_load_decay, max(0.35, float(adaptive_load_decay) * 0.90))
            residual_spike_steps.append(i)
            if i not in cutback_steps:
                cutback_steps.append(i)

        if plastic_count > prev_plastic:
            tags.append("plastic_front_advance")
            plastic_transition_steps.append(i)
        if is_collapse:
            tags.append("collapse_detected")
            severity = "error"
            recommended_dt_scale = min(recommended_dt_scale, 0.5)
            recommended_load_decay = min(recommended_load_decay, max(0.30, float(adaptive_load_decay) * 0.85))
            collapse_event_steps.append(i)
        prev_plastic = plastic_count

        if tags:
            recommended_dt_scale_min = min(recommended_dt_scale_min, float(recommended_dt_scale))
            primary_event = tags[0]
            if is_collapse:
                primary_event = "collapse_detected"
            elif "step_nonconverged" in tags:
                primary_event = "step_nonconverged"
            elif "residual_spike" in tags:
                primary_event = "residual_spike"
            event_rows.append(
                {
                    "step": int(i),
                    "time_s": float(i * dt),
                    "severity": severity,
                    "event": primary_event,
                    "tags": tags,
                    "iterations": step_iter,
                    "plastic_story_count": plastic_count,
                    "residual_inf": residual_inf,
                    "recommended_dt_scale": float(recommended_dt_scale),
                    "recommended_adaptive_load_decay": float(recommended_load_decay),
                }
            )

    finite_residuals = [float(v) for v in step_resid[:row_len] if math.isfinite(float(v))]
    event_head = event_rows[:32]
    return {
        "step_count_evaluated": int(row_len),
        "event_count": int(len(event_rows)),
        "event_history_head": event_head,
        "event_history_truncated": bool(len(event_rows) > len(event_head)),
        "event_history_available": True,
        "cutback_recommended_step_count": int(len(cutback_steps)),
        "cutback_recommended_steps_head": [int(v) for v in cutback_steps[:32]],
        "cutback_recommended_step_ratio": float(len(cutback_steps) / row_len) if row_len else 0.0,
        "nonconverged_step_count": int(len(nonconverged_steps)),
        "nonconverged_steps_head": [int(v) for v in nonconverged_steps[:32]],
        "residual_spike_step_count": int(len(residual_spike_steps)),
        "residual_spike_steps_head": [int(v) for v in residual_spike_steps[:32]],
        "plastic_transition_step_count": int(len(plastic_transition_steps)),
        "plastic_transition_steps_head": [int(v) for v in plastic_transition_steps[:32]],
        "collapse_event_count": int(len(collapse_event_steps)),
        "collapse_event_steps_head": [int(v) for v in collapse_event_steps[:32]],
        "max_step_iterations_observed": int(max((int(v) for v in step_iters[:row_len]), default=0)),
        "max_step_residual_inf": float(max(finite_residuals, default=0.0)),
        "iteration_watch_threshold": int(iteration_watch_threshold),
        "next_run_control": {
            "recommended_dt_scale_min": float(recommended_dt_scale_min if event_rows else 1.0),
            "recommended_adaptive_load_decay": float(
                max(
                    0.30,
                    min(
                        float(adaptive_load_decay),
                        float(adaptive_load_decay)
                        * (0.85 if nonconverged_steps or collapse_event_steps else (0.90 if cutback_steps else 1.0)),
                    ),
                )
            ),
        },
        "event_sequence_pass": bool(not nonconverged_steps and not collapse_event_steps),
    }


def _sanitize_ndtha_residual_metrics(
    *,
    raw_top_m: float,
    raw_drift_pct: float,
    top_history_m: list[float],
    drift_history_pct: list[float],
    final_story_drift_pct: list[float],
    collapsed: bool,
    collapse_top_m: float,
    collapse_drift_pct: float,
    collapse_drift_threshold_pct: float,
) -> dict[str, object]:
    top_tail = _finite_abs_tail(top_history_m)
    drift_tail = _finite_abs_max(final_story_drift_pct)
    if not math.isfinite(drift_tail):
        drift_tail = _finite_abs_tail(drift_history_pct)

    hist_top_cap = _finite_abs_max(top_history_m)
    hist_drift_cap = _finite_abs_max(drift_history_pct)
    top_cap = max(
        1.0,
        abs(float(collapse_top_m)) * 1.25,
        (hist_top_cap * 1.5) if math.isfinite(hist_top_cap) else 0.0,
    )
    drift_cap = max(
        float(collapse_drift_threshold_pct),
        abs(float(collapse_drift_pct)) * 1.25,
        (hist_drift_cap * 1.25) if math.isfinite(hist_drift_cap) else 0.0,
    )

    raw_top_ok = bool(math.isfinite(raw_top_m) and abs(float(raw_top_m)) <= top_cap)
    raw_drift_ok = bool(math.isfinite(raw_drift_pct) and abs(float(raw_drift_pct)) <= drift_cap)
    use_raw = bool(raw_top_ok and raw_drift_ok)

    if use_raw:
        residual_top_m = abs(float(raw_top_m))
        residual_drift_pct = abs(float(raw_drift_pct))
        source = "solver_raw"
    elif collapsed:
        residual_top_m = max(
            abs(float(collapse_top_m)),
            top_tail if math.isfinite(top_tail) else 0.0,
        )
        residual_drift_pct = max(
            abs(float(collapse_drift_pct)),
            drift_tail if math.isfinite(drift_tail) else 0.0,
        )
        source = "collapse_state"
    else:
        residual_top_m = top_tail if math.isfinite(top_tail) else 0.0
        residual_drift_pct = drift_tail if math.isfinite(drift_tail) else 0.0
        source = "history_tail"

    return {
        "residual_top_displacement_m": float(residual_top_m),
        "residual_drift_ratio_pct": float(residual_drift_pct),
        "raw_residual_top_displacement_m": float(raw_top_m) if math.isfinite(raw_top_m) else math.inf,
        "raw_residual_drift_ratio_pct": float(raw_drift_pct) if math.isfinite(raw_drift_pct) else math.inf,
        "residual_metric_source": str(source),
        "residual_metric_fallback_used": bool(not use_raw),
        "residual_metric_sane": bool(math.isfinite(residual_top_m) and math.isfinite(residual_drift_pct)),
    }


def _build_ndtha_report_surfaces(
    *,
    case_rows: list[dict],
    checks: dict[str, bool],
    response_npz_summary: dict[str, object],
) -> dict[str, object]:
    residual_sources: dict[str, int] = {}
    residual_fallback_case_ids: list[str] = []
    solver_raw_case_ids: list[str] = []
    history_tail_case_ids: list[str] = []
    collapse_state_case_ids: list[str] = []
    cutback_case_ids: list[str] = []
    response_case_keys: list[str] = []
    response_case_ids: list[str] = []
    response_series_case_count = 0
    empty_series_case_ids: list[str] = []
    response_full_step_count_max = 0
    response_inline_step_count_max = 0
    solver_event_count_total = 0
    solver_nonconverged_step_total = 0
    recommended_dt_scale_min = 1.0
    residual_top_max_abs = 0.0
    residual_drift_max_abs = 0.0
    residual_pre_settle_top_max_abs = 0.0
    residual_pre_settle_drift_max_abs = 0.0
    residual_settle_case_count = 0
    story_drift_envelope_max = 0.0
    final_story_drift_max = 0.0

    for row in case_rows:
        case_id = str(row.get("case_id", ""))
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), dict) else {}
        solver_control = summary.get("solver_control") if isinstance(summary.get("solver_control"), dict) else {}

        source = str(summary.get("residual_metric_source", "")).strip() or "unknown"
        residual_sources[source] = int(residual_sources.get(source, 0) + 1)
        if bool(summary.get("residual_metric_fallback_used", False)):
            residual_fallback_case_ids.append(case_id)
        if source == "solver_raw":
            solver_raw_case_ids.append(case_id)
        elif source == "history_tail":
            history_tail_case_ids.append(case_id)
        elif source == "collapse_state":
            collapse_state_case_ids.append(case_id)

        if bool(summary.get("residual_settle_applied", False)):
            residual_settle_case_count += 1
        residual_top_max_abs = max(
            residual_top_max_abs,
            abs(float(summary.get("residual_top_displacement_m", 0.0) or 0.0)),
        )
        residual_drift_max_abs = max(
            residual_drift_max_abs,
            abs(float(summary.get("residual_drift_ratio_pct", 0.0) or 0.0)),
        )
        residual_pre_settle_top_max_abs = max(
            residual_pre_settle_top_max_abs,
            abs(float(summary.get("residual_pre_settle_top_displacement_m", 0.0) or 0.0)),
        )
        residual_pre_settle_drift_max_abs = max(
            residual_pre_settle_drift_max_abs,
            abs(float(summary.get("residual_pre_settle_drift_ratio_pct", 0.0) or 0.0)),
        )
        story_drift_envelope = response.get("story_drift_envelope_pct") or []
        final_story_drift = response.get("final_story_drift_pct") or []
        if story_drift_envelope:
            story_drift_envelope_max = max(
                story_drift_envelope_max,
                max(abs(float(v)) for v in story_drift_envelope),
            )
        if final_story_drift:
            final_story_drift_max = max(
                final_story_drift_max,
                max(abs(float(v)) for v in final_story_drift),
            )

        solver_event_count_total += int(solver_control.get("event_count", 0) or 0)
        solver_nonconverged_step_total += int(solver_control.get("nonconverged_step_count", 0) or 0)
        recommended_dt_scale_min = min(
            recommended_dt_scale_min,
            float((((solver_control.get("next_run_control") or {}).get("recommended_dt_scale_min", 1.0)))),
        )
        if int(solver_control.get("cutback_recommended_step_count", 0) or 0) > 0:
            cutback_case_ids.append(case_id)

        case_key = str(artifacts.get("response_npz_key_prefix", "")).strip()
        if case_key:
            response_case_keys.append(case_key)
        if case_id:
            response_case_ids.append(case_id)
        response_full_step_count_max = max(
            response_full_step_count_max,
            int(artifacts.get("response_full_step_count", 0) or 0),
        )
        response_inline_step_count_max = max(
            response_inline_step_count_max,
            int(artifacts.get("response_inline_step_count", 0) or 0),
        )
        if int(artifacts.get("response_full_step_count", 0) or 0) > 0:
            response_series_case_count += 1
        elif case_id:
            empty_series_case_ids.append(case_id)

    cutback_case_ids = sorted(dict.fromkeys(cutback_case_ids))
    response_case_keys = list(dict.fromkeys(response_case_keys))
    response_case_ids = list(dict.fromkeys(response_case_ids))
    ordered_source_counts = {key: residual_sources[key] for key in sorted(residual_sources)}
    status = "PASS" if all(bool(v) for v in checks.values()) else "CHECK"
    summary_line = (
        f"Nonlinear NDTHA stress: {status} | cases={len(case_rows)} | "
        f"response_npz={int(response_npz_summary.get('case_count', 0))}/{len(case_rows)} | "
        f"step_series={response_series_case_count}/{len(case_rows)} | "
        f"residual_sources={','.join(f'{k}:{v}' for k, v in ordered_source_counts.items()) or 'none'} | "
        f"solver_events={solver_event_count_total} | cutback_cases={len(cutback_case_ids)} | "
        f"dt_scale_min={recommended_dt_scale_min:.2f}"
    )
    return {
        "summary_line": summary_line,
        "solver_control": {
            "history_pass": bool(checks.get("solver_control_history_pass", False)),
            "event_sequence_pass": bool(
                all(bool((((row.get("summary") or {}).get("solver_control") or {}).get("event_sequence_pass", False))) for row in case_rows)
            ),
            "event_count_total": int(solver_event_count_total),
            "nonconverged_step_total": int(solver_nonconverged_step_total),
            "cutback_case_ids": cutback_case_ids,
            "cutback_case_count": int(len(cutback_case_ids)),
            "recommended_dt_scale_min": float(recommended_dt_scale_min),
        },
        "response_npz": {
            **response_npz_summary,
            "case_keys": response_case_keys,
            "case_ids": response_case_ids,
            "series_case_count": int(response_series_case_count),
            "empty_series_case_ids": empty_series_case_ids,
            "series_contract_pass": bool(response_series_case_count == len(case_rows)),
            "full_step_count_max": int(response_full_step_count_max),
            "inline_step_count_max": int(response_inline_step_count_max),
        },
        "residual_metric": {
            "sanity_pass": bool(checks.get("residual_metric_sanity_pass", False)),
            "source_counts": ordered_source_counts,
            "fallback_case_ids": residual_fallback_case_ids,
            "fallback_case_count": int(len(residual_fallback_case_ids)),
            "solver_raw_case_ids": solver_raw_case_ids,
            "history_tail_case_ids": history_tail_case_ids,
            "collapse_state_case_ids": collapse_state_case_ids,
            "top_displacement_m_max_abs": float(residual_top_max_abs),
            "drift_ratio_pct_max_abs": float(residual_drift_max_abs),
            "pre_settle_top_displacement_m_max_abs": float(residual_pre_settle_top_max_abs),
            "pre_settle_drift_ratio_pct_max_abs": float(residual_pre_settle_drift_max_abs),
            "settle_case_count": int(residual_settle_case_count),
        },
        "residual_tail_metrics": {
            "story_drift_envelope_pct_max_abs": float(story_drift_envelope_max),
            "final_story_drift_pct_max_abs": float(final_story_drift_max),
            "tail_source": "row.response.story_drift_envelope_pct+final_story_drift_pct",
        },
    }


def _validate_metric_source(cases: list[dict], accepted: set[str]) -> tuple[bool, list[str]]:
    bad: list[str] = []
    for i, c in enumerate(cases):
        src = str(c.get("metric_source", "")).strip()
        if src not in accepted:
            bad.append(str(c.get("case_id", f"case-{i}")))
    return len(bad) == 0, bad


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="nonlinear_ndtha_stress",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def _run_ndtha_case(
    *,
    rust_cfg: RustNonlinearFrameConfig,
    story_k: np.ndarray,
    story_h: np.ndarray,
    story_p: np.ndarray,
    story_yield_drift: np.ndarray,
    story_mass: np.ndarray,
    story_damp: np.ndarray,
    floor_load_base: np.ndarray,
    ag: np.ndarray,
    dt: float,
    beta: float,
    gamma: float,
    max_step_iterations: int,
    step_tol: float,
    adaptive_load_decay: float,
    damping_force_cap_ratio: float,
    collapse_drift_threshold_pct: float,
    inline_response_limit: int = 256,
) -> dict:
    n_story = int(story_k.shape[0])
    n_step = int(ag.shape[0])
    ndtha_cfg = RustNonlinearNdthaConfig(
        dt_s=float(dt),
        newmark_beta=float(beta),
        newmark_gamma=float(gamma),
        tolerance=float(step_tol),
        max_step_iterations=int(max_step_iterations),
        adaptive_load_decay=float(adaptive_load_decay),
        damping_force_cap_ratio=float(damping_force_cap_ratio),
        newton_max_iter=int(max(8, rust_cfg.max_iter)),
        line_search_decay=float(rust_cfg.line_search_decay),
        line_search_min=float(rust_cfg.line_search_min),
        hardening_ratio=float(rust_cfg.hardening_ratio),
        pdelta_factor=float(rust_cfg.pdelta_factor),
        collapse_drift_threshold_pct=float(collapse_drift_threshold_pct),
    )
    solved = solve_nonlinear_frame_ndtha(
        story_k_n_per_m=story_k,
        story_h_m=story_h,
        story_axial_n=story_p,
        story_yield_drift_m=story_yield_drift,
        story_mass_kg=story_mass,
        story_damping_n_s_per_m=story_damp,
        floor_load_base_n=floor_load_base,
        ag_g=ag,
        cfg=ndtha_cfg,
        keep_device_artifacts=True,
    )
    response_arrays, response_consumer = _response_arrays_from_result(solved)
    initial_series_row_count = _response_series_row_count(response_arrays)
    if int(solved.get("step_count_completed", 0)) > 0 and initial_series_row_count <= 0:
        solved_host = solve_nonlinear_frame_ndtha(
            story_k_n_per_m=story_k,
            story_h_m=story_h,
            story_axial_n=story_p,
            story_yield_drift_m=story_yield_drift,
            story_mass_kg=story_mass,
            story_damping_n_s_per_m=story_damp,
            floor_load_base_n=floor_load_base,
            ag_g=ag,
            cfg=ndtha_cfg,
            keep_device_artifacts=False,
        )
        host_response_arrays, _ = _response_arrays_from_result(solved_host)
        if _response_series_row_count(host_response_arrays) > 0:
            solved = {**solved, **solved_host}
            response_arrays = host_response_arrays
            response_consumer = "host_response_rerun"
    top_disp_hist = np.asarray(response_arrays.get("top_displacement_m", np.asarray([], dtype=np.float64)), dtype=np.float64)
    drift_hist = np.asarray(response_arrays.get("drift_ratio_pct", np.asarray([], dtype=np.float64)), dtype=np.float64)
    base_shear_hist = np.asarray(response_arrays.get("base_shear_kN", np.asarray([], dtype=np.float64)), dtype=np.float64)
    core_drift_hist = np.asarray(response_arrays.get("core_drift_pct", np.asarray([], dtype=np.float64)), dtype=np.float64)
    core_shear_hist = np.asarray(response_arrays.get("core_shear_kN", np.asarray([], dtype=np.float64)), dtype=np.float64)
    step_conv = np.asarray(response_arrays.get("step_converged", np.asarray([], dtype=np.bool_)), dtype=np.bool_)
    step_iters = np.asarray(response_arrays.get("step_iterations", np.asarray([], dtype=np.int32)), dtype=np.int32)
    step_plastic = np.asarray(response_arrays.get("step_plastic_story_count", np.asarray([], dtype=np.int32)), dtype=np.int32)
    step_resid = np.asarray(response_arrays.get("step_residual_inf", np.asarray([], dtype=np.float64)), dtype=np.float64)
    story_drift_envelope = np.asarray(response_arrays.get("story_drift_envelope_pct", np.asarray([], dtype=np.float64)), dtype=np.float64)
    final_story_drift_pct = np.asarray(response_arrays.get("final_story_drift_pct", np.asarray([], dtype=np.float64)), dtype=np.float64)

    backend_ok = bool(str(solved.get("backend", "")).startswith("rust_ffi_") and int(solved.get("status", -999)) == 0)
    converged_all = bool(solved.get("converged_all_steps", False))
    rust_ok_all = bool(solved.get("rust_backend_all_steps", False) and backend_ok)
    step_count_completed = int(solved.get("step_count_completed", min(n_step, len(top_disp_hist))))
    collapse_step = int(solved.get("collapse_step", -1))
    collapsed = bool(solved.get("collapsed", False))
    core_story_index = 0
    row_len = min(step_count_completed, len(top_disp_hist), len(drift_hist), len(base_shear_hist), len(core_drift_hist), len(core_shear_hist), len(step_conv), len(step_iters), len(step_plastic), len(step_resid))
    time_hist = np.asarray([float(i * dt) for i in range(row_len)], dtype=np.float64)
    derived_kinematics = _derive_series_kinematics(
        time_s=time_hist,
        top_displacement_m=top_disp_hist[:row_len],
        ground_acceleration_g=ag[:row_len],
    )
    solver_control = _build_ndtha_solver_control_summary(
        step_conv=step_conv[:row_len],
        step_iters=step_iters[:row_len],
        step_plastic=step_plastic[:row_len],
        step_resid=step_resid[:row_len],
        dt=float(dt),
        max_step_iterations=int(max_step_iterations),
        step_tol=float(step_tol),
        adaptive_load_decay=float(adaptive_load_decay),
        collapsed=bool(collapsed),
        collapse_step=int(collapse_step),
    )
    solver_control_events = {
        int(row.get("step", -1)): row for row in (solver_control.get("event_history_head") or []) if isinstance(row, dict)
    }

    step_rows: list[dict] = []
    for i in range(row_len):
        is_collapse = bool(collapsed and collapse_step == i)
        status = "COLLAPSED" if is_collapse else ("OK" if step_conv[i] else "FAIL")
        solver_event = solver_control_events.get(int(i), {})
        step_rows.append(
            {
                "step": int(i),
                "time_s": float(i * dt),
                "ag_g": float(ag[i]) if i < n_step else 0.0,
                "status": status,
                "converged": bool(step_conv[i] and not is_collapse),
                "rust_backend_ok": bool(backend_ok),
                "iterations": int(step_iters[i]),
                "plastic_story_count": int(step_plastic[i]),
                "top_displacement_m": float(top_disp_hist[i]),
                "base_shear_kN": float(base_shear_hist[i]),
                "core_story_drift_pct": float(core_drift_hist[i]),
                "core_story_shear_kN": float(core_shear_hist[i]),
                "drift_ratio_pct": float(drift_hist[i]),
                "residual_inf": float(step_resid[i]),
                "solver_event": str(solver_event.get("event", "")) if solver_event else "",
                "solver_event_severity": str(solver_event.get("severity", "")) if solver_event else "",
                "recommended_dt_scale": float(solver_event.get("recommended_dt_scale", 1.0)) if solver_event else 1.0,
            }
        )

    residual_metrics = _sanitize_ndtha_residual_metrics(
        raw_top_m=float(solved.get("residual_top_displacement_m", 0.0)),
        raw_drift_pct=float(solved.get("residual_drift_ratio_pct", 0.0)),
        top_history_m=[float(x) for x in top_disp_hist[:row_len]],
        drift_history_pct=[float(x) for x in drift_hist[:row_len]],
        final_story_drift_pct=[float(x) for x in final_story_drift_pct.tolist()],
        collapsed=bool(collapsed),
        collapse_top_m=float(solved.get("collapse_top_displacement_m", 0.0)),
        collapse_drift_pct=float(solved.get("collapse_drift_ratio_pct", 0.0)),
        collapse_drift_threshold_pct=float(collapse_drift_threshold_pct),
    )
    return {
        "engine_backend": str(solved.get("backend", "")),
        "converged_all_steps": bool(converged_all),
        "rust_backend_all_steps": bool(rust_ok_all),
        "step_rows_head": step_rows[:500],
        "step_count_completed": int(step_count_completed),
        "max_plastic_story_count": int(solved.get("max_plastic_story_count", 0)),
        "max_drift_ratio_pct": float(solved.get("max_drift_ratio_pct", 0.0)),
        "avg_step_iterations": float(solved.get("avg_step_iterations", 0.0)),
        "collapsed": bool(collapsed),
        "collapse_step": int(collapse_step),
        "collapse_time_s": float(solved.get("collapse_time_s", 0.0)),
        "collapse_drift_ratio_pct": float(solved.get("collapse_drift_ratio_pct", 0.0)),
        "collapse_top_displacement_m": float(solved.get("collapse_top_displacement_m", 0.0)),
        "residual_pre_settle_top_displacement_m": float(solved.get("residual_pre_settle_top_displacement_m", 0.0)),
        "residual_pre_settle_drift_ratio_pct": float(solved.get("residual_pre_settle_drift_ratio_pct", 0.0)),
        "residual_settle_applied": bool(solved.get("residual_settle_applied", False)),
        "residual_settle_steps": int(solved.get("residual_settle_steps", 0)),
        "story_count": int(n_story),
        "story_drift_envelope_pct": [float(x) for x in story_drift_envelope.tolist()],
        "final_story_drift_pct": [float(x) for x in final_story_drift_pct.tolist()],
        **residual_metrics,
        "response_storage": "npz_external+inline_head",
        "response_device_consumer": str(response_consumer),
        "response_full_step_count": int(row_len),
        "response_inline_step_count": int(row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit)),
        "solver_control": solver_control,
        "response": {
            "time_s": [float(x) for x in time_hist[: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "top_displacement_m": [float(x) for x in top_disp_hist[: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "top_velocity_mps": [float(x) for x in derived_kinematics["top_velocity_mps"][: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "top_acceleration_mps2": [float(x) for x in derived_kinematics["top_acceleration_mps2"][: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "ground_acceleration_g": [float(x) for x in derived_kinematics["ground_acceleration_g"][: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "drift_ratio_pct": [float(x) for x in drift_hist[: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "base_shear_kN": [float(x) for x in base_shear_hist[: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            "core_wall_hysteresis": {
                "story_index": int(core_story_index + 1),
                "drift_pct": [float(x) for x in core_drift_hist[: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
                "shear_kN": [float(x) for x in core_shear_hist[: (row_len if inline_response_limit <= 0 else min(row_len, inline_response_limit))]],
            },
        },
        "response_artifact_data": {
            "time_s": [float(x) for x in time_hist],
            "top_displacement_m": [float(x) for x in top_disp_hist[:row_len]],
            "top_velocity_mps": [float(x) for x in derived_kinematics["top_velocity_mps"]],
            "top_acceleration_mps2": [float(x) for x in derived_kinematics["top_acceleration_mps2"]],
            "ground_acceleration_g": [float(x) for x in derived_kinematics["ground_acceleration_g"]],
            "drift_ratio_pct": [float(x) for x in drift_hist[:row_len]],
            "base_shear_kN": [float(x) for x in base_shear_hist[:row_len]],
            "core_drift_pct": [float(x) for x in core_drift_hist[:row_len]],
            "core_shear_kN": [float(x) for x in core_shear_hist[:row_len]],
            "step_converged": [bool(x) for x in step_conv[:row_len]],
            "step_iterations": [int(x) for x in step_iters[:row_len]],
            "step_plastic_story_count": [int(x) for x in step_plastic[:row_len]],
            "step_residual_inf": [float(x) for x in step_resid[:row_len]],
            "story_drift_envelope_pct": [float(x) for x in story_drift_envelope.tolist()],
            "final_story_drift_pct": [float(x) for x in final_story_drift_pct.tolist()],
        },
    }


def main() -> None:
    logger = get_logger("phase3.run_nonlinear_ndtha_stress")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--min-case-count", type=int, default=3)
    p.add_argument("--max-case-count", type=int, default=6)
    p.add_argument("--ag-scale", type=float, default=2.0)
    p.add_argument("--yield-drift-scale", type=float, default=0.45)
    p.add_argument("--hardening-ratio", type=float, default=0.2)
    p.add_argument("--pdelta-factor", type=float, default=1.0)
    p.add_argument("--dt-scale", type=float, default=1.0)
    p.add_argument("--newmark-beta", type=float, default=0.25)
    p.add_argument("--newmark-gamma", type=float, default=0.5)
    p.add_argument("--max-step-iterations", type=int, default=16)
    p.add_argument("--step-tol", type=float, default=1e-4)
    p.add_argument("--adaptive-load-decay", type=float, default=0.82)
    p.add_argument("--damping-force-cap-ratio", type=float, default=0.6)
    p.add_argument("--max-steps", type=int, default=2400)
    p.add_argument("--min-load-reversals", type=int, default=20)
    p.add_argument("--min-plastic-story-count", type=int, default=1)
    p.add_argument("--collapse-drift-threshold-pct", type=float, default=10.0)
    p.add_argument("--rayleigh-alpha", type=float, default=0.03)
    p.add_argument("--rayleigh-beta", type=float, default=1e-6)
    p.add_argument("--material-model", choices=["steel_elastic_plastic", "rc_composite"], default="rc_composite")
    p.add_argument("--rc-cracking-strain", type=float, default=2.2e-4)
    p.add_argument("--rc-creep-rate-per-hour", type=float, default=0.008)
    p.add_argument("--rc-bond-slip-ratio-ref", type=float, default=0.003)
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    p.add_argument("--response-npz-out", default="")
    p.add_argument("--inline-response-limit", type=int, default=256)
    p.add_argument("--out", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    args = p.parse_args()

    response_npz_out = Path(str(args.response_npz_out)) if str(args.response_npz_out).strip() else _default_response_npz_out(Path(args.out))
    input_payload = {
        "cases": str(args.cases),
        "target_split": str(args.target_split),
        "ground_motion_csv": str(args.ground_motion_csv),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "ag_scale": float(args.ag_scale),
        "yield_drift_scale": float(args.yield_drift_scale),
        "hardening_ratio": float(args.hardening_ratio),
        "pdelta_factor": float(args.pdelta_factor),
        "dt_scale": float(args.dt_scale),
        "newmark_beta": float(args.newmark_beta),
        "newmark_gamma": float(args.newmark_gamma),
        "max_step_iterations": int(args.max_step_iterations),
        "step_tol": float(args.step_tol),
        "adaptive_load_decay": float(args.adaptive_load_decay),
        "damping_force_cap_ratio": float(args.damping_force_cap_ratio),
        "max_steps": int(args.max_steps),
        "min_load_reversals": int(args.min_load_reversals),
        "min_plastic_story_count": int(args.min_plastic_story_count),
        "collapse_drift_threshold_pct": float(args.collapse_drift_threshold_pct),
        "rayleigh_alpha": float(args.rayleigh_alpha),
        "rayleigh_beta": float(args.rayleigh_beta),
        "material_model": str(args.material_model),
        "rc_cracking_strain": float(args.rc_cracking_strain),
        "rc_creep_rate_per_hour": float(args.rc_creep_rate_per_hour),
        "rc_bond_slip_ratio_ref": float(args.rc_bond_slip_ratio_ref),
        "accepted_metric_sources": str(args.accepted_metric_sources),
        "response_npz_out": str(response_npz_out),
        "inline_response_limit": int(args.inline_response_limit),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_nonlinear_ndtha_stress")
        log_event(logger, 20, "ndtha.start", inputs=input_payload)
        t0 = time.time()
        if float(args.pdelta_factor) < 1.0:
            raise RuntimeError(REASONS["ERR_PDELTA_DISABLED"])
        if float(args.rayleigh_alpha) <= 0.0 and float(args.rayleigh_beta) <= 0.0:
            raise RuntimeError(REASONS["ERR_RAYLEIGH_DAMPING_DISABLED"])

        try:
            t_raw, ag_raw = _load_ground_motion(Path(args.ground_motion_csv))
        except Exception as exc:  # noqa: BLE001
            report = {
                "schema_version": "1.0",
                "run_id": "phase3-rust-nonlinear-ndtha-stress",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "inputs": input_payload,
                "contract_pass": False,
                "reason_code": "ERR_GM_INPUT",
                "reason": f"{REASONS['ERR_GM_INPUT']}: {exc}",
            }
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Wrote nonlinear ndtha stress report: {out}")
            raise SystemExit(1)

        dt = float((t_raw[1] - t_raw[0]) * float(args.dt_scale))
        ag = np.asarray(ag_raw, dtype=np.float64) * float(args.ag_scale)
        max_steps = min(int(args.max_steps), int(ag.shape[0]))
        ag = ag[:max_steps]
        reversal_count = _count_reversals(ag)
        if reversal_count < int(args.min_load_reversals):
            report = {
                "schema_version": "1.0",
                "run_id": "phase3-rust-nonlinear-ndtha-stress",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "inputs": input_payload,
                "ground_motion": {
                    "path": str(args.ground_motion_csv),
                    "step_count": int(ag.shape[0]),
                    "dt_s": float(dt),
                    "max_abs_accel_g": float(np.max(np.abs(ag))) if ag.size else 0.0,
                    "reversal_count": int(reversal_count),
                },
                "contract_pass": False,
                "reason_code": "ERR_DYNAMICS_NOT_REVERSED",
                "reason": REASONS["ERR_DYNAMICS_NOT_REVERSED"],
            }
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Wrote nonlinear ndtha stress report: {out}")
            raise SystemExit(1)

        payload = _load_json(Path(args.cases))
        cases = payload.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError("cases[] missing")
        rows = [c for c in cases if isinstance(c, dict)]
        if str(args.target_split) != "all":
            rows = [c for c in rows if str(c.get("split", "")) == str(args.target_split)]
        rows = rows[: int(args.max_case_count)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"selected cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        accepted_sources = {x.strip() for x in str(args.accepted_metric_sources).split(",") if x.strip()}
        metric_source_ok, metric_source_bad = _validate_metric_source(rows, accepted_sources)

        rust_cfg = RustNonlinearFrameConfig(
            tolerance=float(args.step_tol) * 0.1,
            max_iter=120,
            hardening_ratio=float(args.hardening_ratio),
            pdelta_factor=float(args.pdelta_factor),
        )

        case_rows: list[dict] = []
        converged_all = True
        rust_backend_all = True
        plastic_all = True
        collapsed_any = False
        collapsed_case_ids: list[str] = []
        peak_plastic: list[int] = []
        peak_drift: list[float] = []
        mean_iters: list[float] = []
        material_all_ok = True
        material_effect_rows: list[dict] = []
        residual_sanity_all = True
        residual_fallback_case_ids: list[str] = []
        residual_sources: dict[str, int] = {}
        solver_control_event_count_total = 0
        solver_control_cutback_case_ids: list[str] = []
        solver_control_nonconverged_step_total = 0
        solver_control_dt_scale_min = 1.0
        npz_case_keys_seen: set[str] = set()

        for c in rows:
            case_id = str(c.get("case_id", "unknown"))
            topology = str(c.get("topology_type", "rahmen"))
            material_type = str(c.get("material_type", "steel")).strip().lower()
            story_count = _story_count_for_topology(topology)
            story_h = np.full(story_count, 3.2, dtype=np.float64)

            metrics = c.get("metrics") if isinstance(c.get("metrics"), dict) else {}
            drift_hf_pct = float(((metrics.get("drift_ratio_pct") or {}).get("hf", 0.0)))
            base_hf_kn = float(((metrics.get("base_shear_kN") or {}).get("hf", 0.0)))
            load_scale = float(c.get("load_scale", 1.0))

            drift_hf = max(1e-6, drift_hf_pct / 100.0)
            base_hf_n = max(1.0, base_hf_kn * 1000.0)
            floor_load_base = build_story_load_profile(story_count, base_hf_n, mode="triangular")
            story_k = _build_story_stiffness_from_drift(
                floor_load_n=floor_load_base,
                story_h_m=story_h,
                drift_ratio_hf=drift_hf,
            )
            section_profile = evaluate_story_section_profile(
                topology=topology,
                material_type=material_type,
                story_h_m=story_h,
                drift_ratio_profile=np.linspace(drift_hf * 1.06, drift_hf * 0.94, num=story_count, dtype=np.float64),
                load_scale=load_scale,
            )
            story_k = story_k * np.asarray(section_profile["story_stiffness_scale"], dtype=np.float64)
            story_yield_drift = np.full(
                story_count,
                # Dynamic NDTHA requires lower effective yield drift than static/HF reference scaling.
                max(1e-5, drift_hf * float(np.mean(story_h)) * float(args.yield_drift_scale) * 0.12),
                dtype=np.float64,
            )
            story_yield_drift = story_yield_drift * np.asarray(section_profile["story_yield_scale"], dtype=np.float64)
            story_p = (4.2e6 * float(load_scale)) * np.linspace(1.25, 0.85, num=story_count, dtype=np.float64)
            story_mass = (2.1e5 * float(load_scale)) * np.linspace(1.25, 0.85, num=story_count, dtype=np.float64)
            use_rc = bool(str(args.material_model) == "rc_composite" or material_type in {"rc", "composite", "rc_composite"})
            material_indices: dict[str, float] = {
                "cracking_index_mean": 0.0,
                "creep_index_mean": 0.0,
                "bond_slip_index_mean": 0.0,
            }
            if use_rc:
                rc_cfg = RCCompositeMaterialConfig(
                    cracking_strain=float(args.rc_cracking_strain),
                    creep_rate_per_hour=float(args.rc_creep_rate_per_hour),
                    bond_slip_ratio_ref=float(args.rc_bond_slip_ratio_ref),
                )
                rc_mod = apply_rc_composite_profile(
                    story_k_n_per_m=story_k,
                    story_yield_drift_m=story_yield_drift,
                    story_mass_kg=story_mass,
                    story_h_m=story_h,
                    drift_ratio_proxy=np.linspace(drift_hf * 1.2, drift_hf * 0.8, num=story_count, dtype=np.float64),
                    elapsed_hours=(float(dt) * float(max_steps) / 3600.0),
                    cycle_count=max(1, int(reversal_count)),
                    cfg=rc_cfg,
                )
                story_k = np.asarray(rc_mod.get("story_k_n_per_m", story_k), dtype=np.float64)
                story_yield_drift = np.asarray(rc_mod.get("story_yield_drift_m", story_yield_drift), dtype=np.float64)
                idx = rc_mod.get("indices")
                if isinstance(idx, dict):
                    material_indices = {str(k): float(v) for k, v in idx.items() if isinstance(v, (int, float))}
            story_damp = float(args.rayleigh_alpha) * story_mass + float(args.rayleigh_beta) * story_k

            nd = _run_ndtha_case(
                rust_cfg=rust_cfg,
                story_k=story_k,
                story_h=story_h,
                story_p=story_p,
                story_yield_drift=story_yield_drift,
                story_mass=story_mass,
                story_damp=story_damp,
                floor_load_base=floor_load_base,
                ag=ag,
                dt=dt,
                beta=float(args.newmark_beta),
                gamma=float(args.newmark_gamma),
                max_step_iterations=int(args.max_step_iterations),
                step_tol=float(args.step_tol),
                adaptive_load_decay=float(args.adaptive_load_decay),
                damping_force_cap_ratio=float(args.damping_force_cap_ratio),
                collapse_drift_threshold_pct=float(args.collapse_drift_threshold_pct),
                inline_response_limit=int(args.inline_response_limit),
            )
            artifact_prefix_base = _artifact_key_token(case_id, fallback=f"case_{len(case_rows)+1:03d}")
            artifact_prefix = artifact_prefix_base
            suffix_idx = 2
            while artifact_prefix in npz_case_keys_seen:
                artifact_prefix = f"{artifact_prefix_base}_{suffix_idx}"
                suffix_idx += 1
            npz_case_keys_seen.add(artifact_prefix)

            case_converged = bool(nd.get("converged_all_steps", False))
            case_backend_ok = bool(
                nd.get("rust_backend_all_steps", False)
                and str(nd.get("engine_backend", "")) == "rust_ffi_nonlinear_frame_ndtha"
            )
            case_peak_plastic = int(nd.get("max_plastic_story_count", 0))
            case_plastic_ok = bool(case_peak_plastic >= int(args.min_plastic_story_count))
            case_collapsed = bool(nd.get("collapsed", False))

            converged_all = bool(converged_all and case_converged)
            rust_backend_all = bool(rust_backend_all and case_backend_ok)
            plastic_all = bool(plastic_all and case_plastic_ok)
            collapsed_any = bool(collapsed_any or case_collapsed)
            if case_collapsed:
                collapsed_case_ids.append(case_id)
            peak_plastic.append(case_peak_plastic)
            peak_drift.append(float(nd.get("max_drift_ratio_pct", 0.0)))
            mean_iters.append(float(nd.get("avg_step_iterations", 0.0)))
            material_ok = bool(
                (not use_rc)
                or (
                    float(material_indices.get("cracking_index_mean", 0.0)) > 0.0
                    and float(material_indices.get("stiffness_scale_mean", 1.0)) < 1.0
                )
            )
            material_all_ok = bool(material_all_ok and material_ok)
            residual_sane = bool(nd.get("residual_metric_sane", False))
            residual_source = str(nd.get("residual_metric_source", "unknown"))
            residual_sanity_all = bool(residual_sanity_all and residual_sane)
            residual_sources[residual_source] = int(residual_sources.get(residual_source, 0) + 1)
            if bool(nd.get("residual_metric_fallback_used", False)):
                residual_fallback_case_ids.append(case_id)
            solver_control = nd.get("solver_control") if isinstance(nd.get("solver_control"), dict) else {}
            solver_control_event_count_total += int(solver_control.get("event_count", 0))
            solver_control_nonconverged_step_total += int(solver_control.get("nonconverged_step_count", 0))
            solver_control_dt_scale_min = min(
                float(solver_control_dt_scale_min),
                float((((solver_control.get("next_run_control") or {}).get("recommended_dt_scale_min", 1.0)))),
            )
            if int(solver_control.get("cutback_recommended_step_count", 0)) > 0:
                solver_control_cutback_case_ids.append(case_id)
            material_effect_rows.append(
                {
                    "case_id": case_id,
                    "use_rc_composite_model": bool(use_rc),
                    "material_model_pass": bool(material_ok),
                    "indices": material_indices,
                    "section_profile_summary": dict(section_profile.get("summary", {})),
                    "section_family_counts": dict(section_profile.get("family_counts", {})),
                }
            )

            case_rows.append(
                {
                    "case_id": case_id,
                    "split": str(c.get("split", "")),
                    "topology_type": topology,
                    "hazard_type": str(c.get("hazard_type", "")),
                    "checks": {
                        "converged_all_steps": case_converged,
                        "rust_backend_all_steps": case_backend_ok,
                        "engine_backend": str(nd.get("engine_backend", "")),
                        "plasticity_triggered": case_plastic_ok,
                        "collapsed": bool(case_collapsed),
                    },
                    "summary": {
                        "step_count_completed": int(nd.get("step_count_completed", 0)),
                        "max_plastic_story_count": int(case_peak_plastic),
                        "max_drift_ratio_pct": float(nd.get("max_drift_ratio_pct", 0.0)),
                        "avg_step_iterations": float(nd.get("avg_step_iterations", 0.0)),
                        "story_count": int(nd.get("story_count", story_count)),
                        "residual_top_displacement_m": float(nd.get("residual_top_displacement_m", 0.0)),
                        "residual_drift_ratio_pct": float(nd.get("residual_drift_ratio_pct", 0.0)),
                        "residual_pre_settle_top_displacement_m": float(nd.get("residual_pre_settle_top_displacement_m", 0.0)),
                        "residual_pre_settle_drift_ratio_pct": float(nd.get("residual_pre_settle_drift_ratio_pct", 0.0)),
                        "raw_residual_top_displacement_m": float(nd.get("raw_residual_top_displacement_m", 0.0)),
                        "raw_residual_drift_ratio_pct": float(nd.get("raw_residual_drift_ratio_pct", 0.0)),
                        "residual_metric_source": str(nd.get("residual_metric_source", "")),
                        "residual_metric_fallback_used": bool(nd.get("residual_metric_fallback_used", False)),
                        "residual_settle_applied": bool(nd.get("residual_settle_applied", False)),
                        "residual_settle_steps": int(nd.get("residual_settle_steps", 0)),
                        "collapse_step": int(nd.get("collapse_step", -1)),
                        "collapse_time_s": float(nd.get("collapse_time_s", 0.0)),
                        "collapse_drift_ratio_pct": float(nd.get("collapse_drift_ratio_pct", 0.0)),
                        "collapse_top_displacement_m": float(nd.get("collapse_top_displacement_m", 0.0)),
                        "material_model": "rc_composite" if use_rc else "steel_elastic_plastic",
                        "material_indices": material_indices,
                        "section_profile": dict(section_profile.get("summary", {})),
                        "section_family_counts": dict(section_profile.get("family_counts", {})),
                        "runtime": dict(nd.get("runtime", {})) if isinstance(nd.get("runtime"), dict) else {},
                        "response_device_consumer": str(nd.get("response_device_consumer", "")),
                        "solver_control": dict(solver_control),
                    },
                    "response": {
                        "story_drift_envelope_pct": nd.get("story_drift_envelope_pct", []),
                        "final_story_drift_pct": nd.get("final_story_drift_pct", []),
                        "time_s": ((nd.get("response") or {}).get("time_s", [])),
                        "top_displacement_m": ((nd.get("response") or {}).get("top_displacement_m", [])),
                        "drift_ratio_pct": ((nd.get("response") or {}).get("drift_ratio_pct", [])),
                        "base_shear_kN": ((nd.get("response") or {}).get("base_shear_kN", [])),
                        "core_wall_hysteresis": ((nd.get("response") or {}).get("core_wall_hysteresis", {})),
                    },
                    "response_artifact_data": dict(nd.get("response_artifact_data", {})),
                    "artifacts": {
                        "response_npz_path": str(response_npz_out),
                        "response_npz_key_prefix": artifact_prefix,
                        "response_storage": str(nd.get("response_storage", "npz_external+inline_head")),
                        "response_full_step_count": int(nd.get("response_full_step_count", 0)),
                        "response_inline_step_count": int(nd.get("response_inline_step_count", 0)),
                    },
                    "steps_head": nd.get("step_rows_head", []),
                    "section_probe_head": list(section_profile.get("detail_rows", []))[:12],
                }
            )

        response_npz_summary = _write_ndtha_response_npz(response_npz_out, case_rows)
        for row in case_rows:
            row.pop("response_artifact_data", None)

        checks = {
            "metric_source_pass": bool(metric_source_ok),
            "pdelta_enabled_pass": bool(float(args.pdelta_factor) >= 1.0),
            "dynamic_reversal_pass": bool(reversal_count >= int(args.min_load_reversals)),
            "rayleigh_damping_pass": bool(float(args.rayleigh_alpha) > 0.0 or float(args.rayleigh_beta) > 0.0),
            "collapse_cutoff_guard_pass": bool(float(args.collapse_drift_threshold_pct) > 0.0),
            "no_collapse_detected": bool(not collapsed_any),
            "all_cases_converged": bool(converged_all),
            "rust_backend_used_pass": bool(rust_backend_all),
            "plasticity_triggered_all_cases": bool(plastic_all),
            "min_plastic_story_count_pass": bool(all(v >= int(args.min_plastic_story_count) for v in peak_plastic)),
            "material_model_pass": bool(material_all_ok),
            "section_family_pass": bool(all(float(((row.get("section_profile_summary") or {}).get("stiffness_scale_min", 1.0)) >= 0.95) for row in material_effect_rows)),
            "residual_metric_sanity_pass": bool(residual_sanity_all),
            "solver_control_history_pass": bool(all(isinstance(((row.get("summary") or {}).get("solver_control")), dict) for row in case_rows)),
        }
        contract_pass = bool(all(checks.values()))
        report_surfaces = _build_ndtha_report_surfaces(
            case_rows=case_rows,
            checks=checks,
            response_npz_summary=response_npz_summary,
        )

        if not checks["metric_source_pass"]:
            reason_code = "ERR_CASES"
        elif not checks["pdelta_enabled_pass"]:
            reason_code = "ERR_PDELTA_DISABLED"
        elif not checks["dynamic_reversal_pass"]:
            reason_code = "ERR_DYNAMICS_NOT_REVERSED"
        elif not checks["rayleigh_damping_pass"]:
            reason_code = "ERR_RAYLEIGH_DAMPING_DISABLED"
        elif not checks["collapse_cutoff_guard_pass"]:
            reason_code = "ERR_INVALID_INPUT"
        elif not checks["no_collapse_detected"]:
            reason_code = "ERR_COLLAPSE_CUTOFF"
        elif not checks["rust_backend_used_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["all_cases_converged"]:
            reason_code = "ERR_NDTHA_CONVERGENCE_FAIL"
        elif not checks["plasticity_triggered_all_cases"] or not checks["min_plastic_story_count_pass"]:
            reason_code = "ERR_PLASTICITY_NOT_TRIGGERED"
        elif not checks["material_model_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["residual_metric_sanity_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        else:
            reason_code = "PASS"

        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-ndtha-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary_line": str(report_surfaces["summary_line"]),
            "inputs": input_payload,
            "runtime": {
                "backend": "rust_ffi_nonlinear_frame_ndtha",
                "cpu_fallback_used": False,
                "main_loop_backends": sorted(
                    {
                        str(((row.get("summary") or {}).get("runtime") or {}).get("main_loop_backend", ""))
                        for row in case_rows
                    }
                ),
            },
            "ground_motion": {
                "path": str(args.ground_motion_csv),
                "step_count": int(ag.shape[0]),
                "dt_s": float(dt),
                "max_abs_accel_g": float(np.max(np.abs(ag))) if ag.size else 0.0,
                "reversal_count": int(reversal_count),
                "source": "el_centro_like_synthetic" if "el_centro_like" in Path(args.ground_motion_csv).name else "external_csv",
            },
            "checks": checks,
            "artifacts": {
                "report_json": str(out),
                "response_npz_out": str(response_npz_out),
            },
            "solver_control": dict(report_surfaces["solver_control"]),
            "response_npz": dict(report_surfaces["response_npz"]),
            "residual_metric": dict(report_surfaces["residual_metric"]),
            "residual_tail_metrics": dict(report_surfaces["residual_tail_metrics"]),
            "summary": {
                "case_count": len(case_rows),
                "peak_plastic_story_count_min": min(peak_plastic) if peak_plastic else 0,
                "peak_plastic_story_count_mean": statistics.fmean(peak_plastic) if peak_plastic else 0.0,
                "max_drift_ratio_pct_max": max(peak_drift) if peak_drift else 0.0,
                "avg_step_iterations_mean": statistics.fmean(mean_iters) if mean_iters else 0.0,
                "residual_top_displacement_m_max_abs": max(
                    (abs(float((row.get("summary") or {}).get("residual_top_displacement_m", 0.0))) for row in case_rows),
                    default=0.0,
                ),
                "residual_drift_ratio_pct_max_abs": max(
                    (abs(float((row.get("summary") or {}).get("residual_drift_ratio_pct", 0.0))) for row in case_rows),
                    default=0.0,
                ),
                "residual_pre_settle_top_displacement_m_max_abs": max(
                    (abs(float((row.get("summary") or {}).get("residual_pre_settle_top_displacement_m", 0.0))) for row in case_rows),
                    default=0.0,
                ),
                "residual_pre_settle_drift_ratio_pct_max_abs": max(
                    (abs(float((row.get("summary") or {}).get("residual_pre_settle_drift_ratio_pct", 0.0))) for row in case_rows),
                    default=0.0,
                ),
                "residual_settle_case_count": sum(1 for row in case_rows if bool((row.get("summary") or {}).get("residual_settle_applied", False))),
                "elapsed_wall_s": float(time.time() - t0),
                "metric_source_invalid_case_ids": metric_source_bad,
                "collapsed_case_ids": collapsed_case_ids,
                "residual_metric_fallback_case_ids": residual_fallback_case_ids,
                "residual_metric_source_counts": residual_sources,
                "solver_control_event_count_total": int(solver_control_event_count_total),
                "solver_control_nonconverged_step_total": int(solver_control_nonconverged_step_total),
                "solver_control_cutback_case_ids": solver_control_cutback_case_ids,
                "solver_control_recommended_dt_scale_min": float(solver_control_dt_scale_min),
                "material_model": str(args.material_model),
                "response_storage": "npz_external+inline_head",
                "response_binary_consumer": (
                    "dlpack_zero_copy_primary"
                    if all(str((row.get("summary") or {}).get("response_device_consumer", "")) == "dlpack_zero_copy" for row in case_rows)
                    else "mixed_host_or_device"
                ),
                "response_npz_case_count": int(response_npz_summary.get("case_count", 0)),
                "inline_response_limit": int(args.inline_response_limit),
            },
            "rows": case_rows,
            "material_effect_rows": material_effect_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        archive_manifest = _archive([str(out), str(response_npz_out), str(args.cases), str(args.ground_motion_csv)])
        if archive_manifest:
            report["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, 20, "ndtha.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote nonlinear ndtha stress report: {out}")
        if not contract_pass:
            raise SystemExit(1)
    except RuntimeError as exc:
        msg = str(exc)
        if REASONS["ERR_PDELTA_DISABLED"] in msg:
            reason_code = "ERR_PDELTA_DISABLED"
        elif REASONS["ERR_RAYLEIGH_DAMPING_DISABLED"] in msg:
            reason_code = "ERR_RAYLEIGH_DAMPING_DISABLED"
        else:
            reason_code = "ERR_INVALID_INPUT"
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-ndtha-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": f"{REASONS[reason_code]}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, 40, "ndtha.runtime_error", error=str(exc), reason_code=reason_code)
        print(f"Wrote nonlinear ndtha stress report: {out}")
        raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-ndtha-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, 40, "ndtha.invalid_input", error=str(exc))
        print(f"Wrote nonlinear ndtha stress report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
