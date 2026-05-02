#!/usr/bin/env python3
"""SSI boundary benchmark gate using nonlinear p-y / t-z style attenuation."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile
from rust_nonlinear_frame_bridge import (
    RustNonlinearNdthaConfig,
    build_story_load_profile,
    consume_dlpack_bundle,
    solve_nonlinear_frame_ndtha,
)
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from section_family_library import evaluate_story_section_profile
from soil_tunnel_ssi import SOIL_PRESETS, _impedance_curve


G = 9.80665

REASONS = {
    "PASS": "ssi boundary gate passed",
    "ERR_INVALID_INPUT": "invalid ssi boundary input",
    "ERR_CASES": "insufficient seismic-capable cases for ssi gate",
    "ERR_GM_INPUT": "ground-motion input is missing or invalid",
    "ERR_SSI_MODEL": "ssi nonlinear boundary model invalid",
    "ERR_ENGINE_FAIL": "rust nonlinear engine failed during ssi run",
    "ERR_VNV_FAIL": "ssi vnv thresholds violated",
}


def _gpu_preprocess_strict() -> bool:
    return str(os.environ.get("PHASE1_GPU_PREPROCESS_STRICT", "")).strip().lower() in {"1", "true", "yes", "on"}


def _load_gpu_torch():
    if str(os.environ.get("PHASE1_GPU_PREPROCESS", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    try:
        import torch  # type: ignore
    except Exception:
        return None
    try:
        if bool(torch.cuda.is_available()):
            return torch
    except Exception:
        return None
    return None


def _gpu_zero_cross_frequency(torch, x: np.ndarray, dt: float) -> float:
    with torch.no_grad():
        device = torch.device("cuda:0")
        y = torch.as_tensor(x, dtype=torch.float64, device=device)
        y = y - torch.mean(y)
        cross = torch.logical_or(
            torch.logical_and(y[:-1] <= 0.0, y[1:] > 0.0),
            torch.logical_and(y[:-1] >= 0.0, y[1:] < 0.0),
        )
        crossing_count = int(torch.count_nonzero(cross).item())
        duration = max(float(dt) * max(int(y.numel()) - 1, 1), 1.0e-9)
        return float(crossing_count) / (2.0 * duration) if crossing_count >= 2 else 0.0

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "ground_motion_csv",
        "target_split",
        "soil_profile",
        "min_case_count",
        "max_case_count",
        "py_k0",
        "py_y50_m",
        "tz_k0",
        "tz_z50_m",
        "max_step_iterations",
        "step_tol",
        "adaptive_load_decay",
        "damping_force_cap_ratio",
        "collapse_drift_threshold_pct",
        "rayleigh_alpha",
        "rayleigh_beta",
        "min_shear_delta_ratio",
        "max_shear_delta_ratio",
        "min_nonlinear_ratio_span",
        "allow_cpu_required",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "ground_motion_csv": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "soil_profile": {"type": "string", "enum": sorted(SOIL_PRESETS)},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "py_k0": {"type": "number", "exclusiveMinimum": 0.0},
        "py_y50_m": {"type": "number", "exclusiveMinimum": 0.0},
        "tz_k0": {"type": "number", "exclusiveMinimum": 0.0},
        "tz_z50_m": {"type": "number", "exclusiveMinimum": 0.0},
        "max_step_iterations": {"type": "integer", "minimum": 1},
        "step_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "adaptive_load_decay": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "damping_force_cap_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "collapse_drift_threshold_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "rayleigh_alpha": {"type": "number", "minimum": 0.0},
        "rayleigh_beta": {"type": "number", "minimum": 0.0},
        "min_shear_delta_ratio": {"type": "number", "minimum": 0.0},
        "max_shear_delta_ratio": {"type": "number", "minimum": 0.0},
        "min_nonlinear_ratio_span": {"type": "number", "minimum": 0.0},
        "allow_cpu_required": {"type": "boolean"},
        "case_metrics_npz_out": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ground_motion(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 8:
        raise ValueError("ground-motion csv must have >=8 rows")
    if "time_s" not in rows[0] or "accel_g" not in rows[0]:
        raise ValueError("ground-motion csv must include time_s, accel_g")
    t, ag = [], []
    for i, r in enumerate(rows):
        try:
            t.append(float(r["time_s"]))
            ag.append(float(r["accel_g"]))
        except Exception as exc:
            raise ValueError(f"invalid gm row {i}: {exc}") from exc
    t_arr = np.asarray(t, dtype=np.float64)
    ag_arr = np.asarray(ag, dtype=np.float64)
    dt = float(t_arr[1] - t_arr[0])
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("non-positive dt")
    if np.max(np.abs(np.diff(t_arr) - dt)) > 1e-6:
        raise ValueError("ground-motion dt must be uniform")
    return t_arr, ag_arr


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
    shear = np.cumsum(np.flip(floor_load_n))
    shear = np.flip(shear)
    s = np.linspace(1.0, 1.25, num=n, dtype=np.float64)
    denom = np.maximum(story_h_m * s, 1e-9)
    base = float(np.max(shear / denom) / max(drift_ratio_hf, 1e-6))
    return np.maximum(1e3, base) * s


def _ssi_preprocess_metrics(
    *,
    ag: np.ndarray,
    dt: float,
    transfer: float,
    py_y50_m: float,
    tz_z50_m: float,
) -> tuple[float, np.ndarray, str]:
    if ag.size < 8:
        return 0.0, np.ones_like(ag, dtype=np.float64), "cpu_numpy"
    torch = _load_gpu_torch()
    if torch is not None:
        try:
            with torch.no_grad():
                device = torch.device("cuda:0")
                dom_freq = _gpu_zero_cross_frequency(torch, ag, dt)
                a_ms2 = torch.abs(torch.as_tensor(ag, dtype=torch.float64, device=device)) * float(G)
                py_ratio = 1.0 / (1.0 + torch.pow(a_ms2 / max(float(py_y50_m) * 50.0, 1e-6), 1.1))
                tz_ratio = 1.0 / (1.0 + torch.pow(a_ms2 / max(float(tz_z50_m) * 60.0, 1e-6), 1.0))
                nonlinear_ratio = torch.clamp(float(transfer) * torch.sqrt(py_ratio * tz_ratio), min=0.20, max=1.0)
                return dom_freq, nonlinear_ratio.detach().to("cpu").numpy(), "rocm_torch_full"
        except Exception:
            if _gpu_preprocess_strict():
                raise RuntimeError("GPU preprocess required for SSI metrics; CPU fallback disabled")

    if _gpu_preprocess_strict():
        raise RuntimeError("GPU preprocess required for SSI metrics; GPU runtime unavailable")

    y_cpu = ag - float(np.mean(ag))
    crossing_count = int(np.count_nonzero(np.logical_or(
        np.logical_and(y_cpu[:-1] <= 0.0, y_cpu[1:] > 0.0),
        np.logical_and(y_cpu[:-1] >= 0.0, y_cpu[1:] < 0.0),
    )))
    duration = max(float(dt) * max(int(ag.size) - 1, 1), 1.0e-9)
    dom_freq = float(crossing_count) / (2.0 * duration) if crossing_count >= 2 else 0.0
    a_ms2 = np.abs(ag) * G
    py_ratio = 1.0 / (1.0 + np.power(a_ms2 / max(float(py_y50_m) * 50.0, 1e-6), 1.1))
    tz_ratio = 1.0 / (1.0 + np.power(a_ms2 / max(float(tz_z50_m) * 60.0, 1e-6), 1.0))
    nonlinear_ratio = np.clip(float(transfer) * np.sqrt(py_ratio * tz_ratio), 0.20, 1.0)
    return dom_freq, np.asarray(nonlinear_ratio, dtype=np.float64), "cpu_numpy"


def _default_case_metrics_npz_out(report_out: Path) -> Path:
    if report_out.suffix:
        return report_out.with_suffix(".metrics.npz")
    return report_out.parent / f"{report_out.name}.metrics.npz"


def _section_family_beam_demand_summary(section_profiles: list[dict]) -> dict[str, float | int | bool]:
    profiles = [item for item in section_profiles if isinstance(item, dict)]
    if not profiles:
        return {
            "present": False,
            "profile_count": 0,
            "beam_tangent_scale_min": 0.0,
            "beam_tangent_scale_mean": 0.0,
            "beam_yielded_story_count_max": 0,
            "beam_max_trial_end_moment_ratio": 0.0,
            "beam_stability_index_max": 0.0,
            "beam_strain_energy_total_n_m": 0.0,
        }
    tangent_values = [float(profile.get("beam_tangent_scale_min", 0.0) or 0.0) for profile in profiles]
    yielded_values = [int(profile.get("beam_yielded_story_count", 0) or 0) for profile in profiles]
    demand_values = [float(profile.get("beam_max_trial_end_moment_ratio", 0.0) or 0.0) for profile in profiles]
    stability_values = [float(profile.get("beam_stability_index_max", 0.0) or 0.0) for profile in profiles]
    energy_values = [float(profile.get("beam_strain_energy_total_n_m", 0.0) or 0.0) for profile in profiles]
    return {
        "present": bool(len(profiles) > 0 and min(tangent_values, default=0.0) > 0.0 and sum(energy_values) > 0.0),
        "profile_count": len(profiles),
        "beam_tangent_scale_min": float(min(tangent_values) if tangent_values else 0.0),
        "beam_tangent_scale_mean": float(np.mean(tangent_values) if tangent_values else 0.0),
        "beam_yielded_story_count_max": int(max(yielded_values) if yielded_values else 0),
        "beam_max_trial_end_moment_ratio": float(max(demand_values) if demand_values else 0.0),
        "beam_stability_index_max": float(max(stability_values) if stability_values else 0.0),
        "beam_strain_energy_total_n_m": float(sum(energy_values)),
    }


def _extract_tail_scalar(result: dict, *, key: str, default: float) -> tuple[float, str]:
    artifacts = result.get("device_artifacts")
    if isinstance(artifacts, dict) and bool(result.get("device_artifacts_available", False)):
        try:
            tensors = consume_dlpack_bundle(artifacts)
            tensor = tensors.get(str(key))
            if tensor is not None and int(getattr(tensor, "numel", lambda: 0)()) > 0:
                return float(tensor.reshape(-1)[-1].item()), "dlpack_zero_copy"
        except Exception:
            if _gpu_preprocess_strict():
                raise RuntimeError(f"GPU DLPack consumer failed for SSI key={key}")
    response = result.get("response")
    if isinstance(response, dict):
        values = response.get(str(key))
        if values is not None:
            arr = np.asarray(values, dtype=np.float64).reshape(-1)
            if arr.size > 0:
                return float(arr[-1]), "host_response"
    return float(default), "fallback_default"


def _response_backend_contract(rows: list[dict], *, allow_cpu_required: bool) -> dict[str, object]:
    backend_rows: list[str] = []
    for row in rows:
        for side in ("fixed", "ssi"):
            payload = row.get(side)
            if isinstance(payload, dict):
                backend_rows.append(str(payload.get("response_backend", "") or "missing"))
            else:
                backend_rows.append("missing")
    backend_set = sorted(set(backend_rows))
    has_backends = bool(backend_rows)
    dlpack_all = bool(has_backends and all(item == "dlpack_zero_copy" for item in backend_rows))
    host_response_all = bool(
        has_backends
        and all(item in {"dlpack_zero_copy", "host_response"} for item in backend_rows)
        and any(item == "host_response" for item in backend_rows)
    )
    cpu_required_allowed = bool(allow_cpu_required and host_response_all)
    return {
        "response_backends": backend_set,
        "device_artifacts_consumed": dlpack_all,
        "host_response_consumed": host_response_all,
        "cpu_required_allowed": cpu_required_allowed,
        "response_artifacts_consumed_pass": bool(dlpack_all or cpu_required_allowed),
        "consumer_label": (
            "dlpack_zero_copy"
            if dlpack_all
            else "host_response_cpu_allowed"
            if cpu_required_allowed
            else ",".join(backend_set) or "none"
        ),
    }


def _write_case_metrics_npz(path: Path, rows: list[dict]) -> dict[str, object]:
    payload = {
        "case_ids": np.asarray([str(row.get("case_id", "")) for row in rows], dtype="<U128"),
        "splits": np.asarray([str(row.get("split", "")) for row in rows], dtype="<U32"),
        "topology_types": np.asarray([str(row.get("topology_type", "")) for row in rows], dtype="<U64"),
        "fixed_max_base_shear_kN": np.asarray([float(((row.get("fixed") or {}).get("max_base_shear_kN", 0.0))) for row in rows], dtype=np.float64),
        "ssi_max_base_shear_kN": np.asarray([float(((row.get("ssi") or {}).get("max_base_shear_kN", 0.0))) for row in rows], dtype=np.float64),
        "fixed_residual_pre_top_m": np.asarray([float(((row.get("fixed") or {}).get("residual_pre_settle_top_displacement_m", 0.0))) for row in rows], dtype=np.float64),
        "fixed_residual_post_top_m": np.asarray([float(((row.get("fixed") or {}).get("residual_top_displacement_m", 0.0))) for row in rows], dtype=np.float64),
        "ssi_residual_pre_top_m": np.asarray([float(((row.get("ssi") or {}).get("residual_pre_settle_top_displacement_m", 0.0))) for row in rows], dtype=np.float64),
        "ssi_residual_post_top_m": np.asarray([float(((row.get("ssi") or {}).get("residual_top_displacement_m", 0.0))) for row in rows], dtype=np.float64),
        "fixed_residual_pre_drift_pct": np.asarray([float(((row.get("fixed") or {}).get("residual_pre_settle_drift_ratio_pct", 0.0))) for row in rows], dtype=np.float64),
        "fixed_residual_post_drift_pct": np.asarray([float(((row.get("fixed") or {}).get("residual_drift_ratio_pct", 0.0))) for row in rows], dtype=np.float64),
        "ssi_residual_pre_drift_pct": np.asarray([float(((row.get("ssi") or {}).get("residual_pre_settle_drift_ratio_pct", 0.0))) for row in rows], dtype=np.float64),
        "ssi_residual_post_drift_pct": np.asarray([float(((row.get("ssi") or {}).get("residual_drift_ratio_pct", 0.0))) for row in rows], dtype=np.float64),
        "shear_delta_ratio": np.asarray([float(row.get("shear_delta_ratio", 0.0)) for row in rows], dtype=np.float64),
        "material_model_pass": np.asarray([bool(row.get("material_model_pass", False)) for row in rows], dtype=np.bool_),
        "residual_trace_pass": np.asarray([bool(row.get("residual_trace_pass", False)) for row in rows], dtype=np.bool_),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    return {"path": str(path), "case_count": len(rows), "storage": "npz_external"}


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="ssi_boundary_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase3.run_ssi_boundary_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--soil-profile", default="dense_sand", choices=sorted(SOIL_PRESETS))
    p.add_argument("--min-case-count", type=int, default=2)
    p.add_argument("--max-case-count", type=int, default=4)
    p.add_argument("--py-k0", type=float, default=5.0e7)
    p.add_argument("--py-y50-m", type=float, default=0.03)
    p.add_argument("--tz-k0", type=float, default=3.2e7)
    p.add_argument("--tz-z50-m", type=float, default=0.02)
    p.add_argument("--max-step-iterations", type=int, default=16)
    p.add_argument("--step-tol", type=float, default=1e-4)
    p.add_argument("--adaptive-load-decay", type=float, default=0.82)
    p.add_argument("--damping-force-cap-ratio", type=float, default=0.6)
    p.add_argument("--collapse-drift-threshold-pct", type=float, default=10.0)
    p.add_argument("--rayleigh-alpha", type=float, default=0.03)
    p.add_argument("--rayleigh-beta", type=float, default=1e-6)
    p.add_argument("--min-shear-delta-ratio", type=float, default=0.05)
    p.add_argument("--max-shear-delta-ratio", type=float, default=1.50)
    p.add_argument("--min-nonlinear-ratio-span", type=float, default=0.05)
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--case-metrics-npz-out", default="")
    p.add_argument("--out", default="implementation/phase1/ssi_boundary_gate_report.json")
    args = p.parse_args()
    case_metrics_npz_out = Path(str(args.case_metrics_npz_out)) if str(args.case_metrics_npz_out).strip() else _default_case_metrics_npz_out(Path(args.out))

    input_payload = {
        "cases": str(args.cases),
        "ground_motion_csv": str(args.ground_motion_csv),
        "target_split": str(args.target_split),
        "soil_profile": str(args.soil_profile),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "py_k0": float(args.py_k0),
        "py_y50_m": float(args.py_y50_m),
        "tz_k0": float(args.tz_k0),
        "tz_z50_m": float(args.tz_z50_m),
        "max_step_iterations": int(args.max_step_iterations),
        "step_tol": float(args.step_tol),
        "adaptive_load_decay": float(args.adaptive_load_decay),
        "damping_force_cap_ratio": float(args.damping_force_cap_ratio),
        "collapse_drift_threshold_pct": float(args.collapse_drift_threshold_pct),
        "rayleigh_alpha": float(args.rayleigh_alpha),
        "rayleigh_beta": float(args.rayleigh_beta),
        "min_shear_delta_ratio": float(args.min_shear_delta_ratio),
        "max_shear_delta_ratio": float(args.max_shear_delta_ratio),
        "min_nonlinear_ratio_span": float(args.min_nonlinear_ratio_span),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "case_metrics_npz_out": str(case_metrics_npz_out),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_ssi_boundary_gate")
        if float(args.max_shear_delta_ratio) < float(args.min_shear_delta_ratio):
            raise ValueError("max_shear_delta_ratio must be >= min_shear_delta_ratio")
        log_event(logger, logging.INFO, "ssi_gate.start", inputs=input_payload)

        t, ag = _load_ground_motion(Path(args.ground_motion_csv))
        dt = float(t[1] - t[0])

        soil = SOIL_PRESETS[str(args.soil_profile)]
        dom_f_cpu = _ssi_preprocess_metrics(
            ag=np.asarray(ag[: max(8, min(int(ag.shape[0]), 32))], dtype=np.float64),
            dt=float(dt),
            transfer=1.0,
            py_y50_m=float(args.py_y50_m),
            tz_z50_m=float(args.tz_z50_m),
        )[0]
        f_probe = np.asarray([max(dom_f_cpu, 0.2)], dtype=np.float64)
        kf, cf = _impedance_curve(
            freq_hz=f_probe,
            k0=float(soil["k0"]),
            c0=float(soil["c0"]),
            stiff_exp=float(soil["stiff_exp"]),
            damp_slope=float(soil["damp_slope"]),
            ref_hz=1.0,
        )
        transfer = 1.0 / max(1.0, float(np.sqrt((kf[0] / 1e8) ** 2 + (cf[0] / 1e6) ** 2)))
        transfer = float(np.clip(transfer, 0.35, 0.98))
        dom_f, nonlinear_ratio, preprocess_backend = _ssi_preprocess_metrics(
            ag=ag,
            dt=float(dt),
            transfer=float(transfer),
            py_y50_m=float(args.py_y50_m),
            tz_z50_m=float(args.tz_z50_m),
        )
        if not np.all(np.isfinite(nonlinear_ratio)):
            raise ValueError("nonlinear boundary ratio contains non-finite values")

        cases_payload = _load_json(Path(args.cases))
        raw_cases = cases_payload.get("cases")
        if not isinstance(raw_cases, list):
            raise ValueError("cases[] missing")
        rows = [
            c
            for c in raw_cases
            if isinstance(c, dict) and str(c.get("hazard_type", "")).strip().lower() in {"seismic", "combined"}
        ]
        if str(args.target_split) != "all":
            rows = [c for c in rows if str(c.get("split", "")) == str(args.target_split)]
        rows = rows[: int(args.max_case_count)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"selected seismic cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        out_rows: list[dict] = []
        rust_backend_all = True
        converged_all = True
        no_collapse_all = True
        shear_delta_ratios: list[float] = []
        section_family_all = True
        material_model_all = True

        for case in rows:
            case_id = str(case.get("case_id", "unknown"))
            topology = str(case.get("topology_type", "rahmen"))
            material_type = str(case.get("material_type", "steel")).strip().lower()
            n = _story_count_for_topology(topology)
            story_h = np.full(n, 3.2, dtype=np.float64)
            drift_hf_pct = float((((case.get("metrics") or {}).get("drift_ratio_pct") or {}).get("hf", 1.0)))
            base_hf_kn = float((((case.get("metrics") or {}).get("base_shear_kN") or {}).get("hf", 1000.0)))
            floor_load = build_story_load_profile(n, max(base_hf_kn * 1000.0, 1.0), mode="triangular")
            story_k = _build_story_stiffness_from_drift(
                floor_load_n=floor_load,
                story_h_m=story_h,
                drift_ratio_hf=max(drift_hf_pct / 100.0, 1e-6),
            )
            section_profile = evaluate_story_section_profile(
                topology=topology,
                material_type=material_type,
                story_h_m=story_h,
                drift_ratio_profile=np.linspace(
                    max(drift_hf_pct / 100.0, 1e-6) * 1.04,
                    max(drift_hf_pct / 100.0, 1e-6) * 0.96,
                    num=n,
                    dtype=np.float64,
                ),
                load_scale=float(case.get("load_scale", 1.0)),
            )
            story_k = story_k * np.asarray(section_profile["story_stiffness_scale"], dtype=np.float64)
            story_mass = np.linspace(5.2e5, 3.0e5, num=n, dtype=np.float64)
            story_damp = np.maximum(
                1e2,
                float(args.rayleigh_alpha) * story_mass + float(args.rayleigh_beta) * story_k,
            )
            story_yield = np.maximum(1e-4, 0.55 * (drift_hf_pct / 100.0) * story_h)
            story_yield = story_yield * np.asarray(section_profile["story_yield_scale"], dtype=np.float64)
            story_axial = (4.2e6 * float(case.get("load_scale", 1.0))) * np.linspace(1.3, 0.85, num=n, dtype=np.float64)
            use_rc = bool(material_type in {"rc", "composite", "rc_composite"})
            material_indices: dict[str, float] = {
                "cracking_index_mean": 0.0,
                "stiffness_scale_mean": 1.0,
            }
            if use_rc:
                rc_mod = apply_rc_composite_profile(
                    story_k_n_per_m=story_k,
                    story_yield_drift_m=story_yield,
                    story_mass_kg=story_mass,
                    story_h_m=story_h,
                    drift_ratio_proxy=np.linspace(
                        max(drift_hf_pct / 100.0, 1e-6) * 1.18,
                        max(drift_hf_pct / 100.0, 1e-6) * 0.82,
                        num=n,
                        dtype=np.float64,
                    ),
                    elapsed_hours=(float(dt) * float(ag.shape[0]) / 3600.0),
                    cycle_count=max(1, int(np.count_nonzero(np.diff(np.signbit(ag))))),
                    cfg=RCCompositeMaterialConfig(),
                )
                story_k = np.asarray(rc_mod.get("story_k_n_per_m", story_k), dtype=np.float64)
                story_yield = np.asarray(rc_mod.get("story_yield_drift_m", story_yield), dtype=np.float64)
                idx = rc_mod.get("indices")
                if isinstance(idx, dict):
                    material_indices = {str(k): float(v) for k, v in idx.items() if isinstance(v, (int, float))}
                story_damp = np.maximum(
                    1e2,
                    float(args.rayleigh_alpha) * story_mass + float(args.rayleigh_beta) * story_k,
                )

            cfg = RustNonlinearNdthaConfig(
                dt_s=float(dt),
                tolerance=float(args.step_tol),
                max_step_iterations=int(args.max_step_iterations),
                adaptive_load_decay=float(args.adaptive_load_decay),
                damping_force_cap_ratio=float(args.damping_force_cap_ratio),
                newton_max_iter=max(40, int(args.max_step_iterations) * 6),
                hardening_ratio=0.2,
                pdelta_factor=1.0,
                collapse_drift_threshold_pct=float(args.collapse_drift_threshold_pct),
            )

            fixed = solve_nonlinear_frame_ndtha(
                story_k_n_per_m=story_k,
                story_h_m=story_h,
                story_axial_n=story_axial,
                story_yield_drift_m=story_yield,
                story_mass_kg=story_mass,
                story_damping_n_s_per_m=story_damp,
                floor_load_base_n=floor_load,
                ag_g=ag,
                cfg=cfg,
                keep_device_artifacts=True,
            )
            ssi = solve_nonlinear_frame_ndtha(
                story_k_n_per_m=story_k,
                story_h_m=story_h,
                story_axial_n=story_axial,
                story_yield_drift_m=story_yield,
                story_mass_kg=story_mass,
                story_damping_n_s_per_m=story_damp,
                floor_load_base_n=floor_load,
                ag_g=np.asarray(ag * nonlinear_ratio, dtype=np.float64),
                cfg=cfg,
                keep_device_artifacts=True,
            )

            fixed_conv = bool(fixed.get("converged_all_steps", False))
            ssi_conv = bool(ssi.get("converged_all_steps", False))
            fixed_rust = bool(str(fixed.get("backend", "")).startswith("rust_ffi_")) and int(fixed.get("status", -999)) == 0
            ssi_rust = bool(str(ssi.get("backend", "")).startswith("rust_ffi_")) and int(ssi.get("status", -999)) == 0
            fixed_collapsed = bool(fixed.get("collapsed", False))
            ssi_collapsed = bool(ssi.get("collapsed", False))
            fixed_pre_top = abs(float(fixed.get("residual_pre_settle_top_displacement_m", fixed.get("residual_top_displacement_m", 0.0))))
            fixed_post_top = abs(float(fixed.get("residual_top_displacement_m", 0.0)))
            fixed_pre_drift = abs(float(fixed.get("residual_pre_settle_drift_ratio_pct", fixed.get("residual_drift_ratio_pct", 0.0))))
            fixed_post_drift = abs(float(fixed.get("residual_drift_ratio_pct", 0.0)))
            ssi_pre_top = abs(float(ssi.get("residual_pre_settle_top_displacement_m", ssi.get("residual_top_displacement_m", 0.0))))
            ssi_post_top = abs(float(ssi.get("residual_top_displacement_m", 0.0)))
            ssi_pre_drift = abs(float(ssi.get("residual_pre_settle_drift_ratio_pct", ssi.get("residual_drift_ratio_pct", 0.0))))
            ssi_post_drift = abs(float(ssi.get("residual_drift_ratio_pct", 0.0)))
            residual_trace_pass_case = bool(
                math.isfinite(fixed_pre_top)
                and math.isfinite(fixed_post_top)
                and math.isfinite(fixed_pre_drift)
                and math.isfinite(fixed_post_drift)
                and math.isfinite(ssi_pre_top)
                and math.isfinite(ssi_post_top)
                and math.isfinite(ssi_pre_drift)
                and math.isfinite(ssi_post_drift)
                and fixed_post_top <= fixed_pre_top + 1e-9
                and fixed_post_drift <= fixed_pre_drift + 1e-9
                and ssi_post_top <= ssi_pre_top + 1e-9
                and ssi_post_drift <= ssi_pre_drift + 1e-9
            )

            base_fixed, fixed_response_backend = _extract_tail_scalar(
                fixed,
                key="base_shear_kN",
                default=float(fixed.get("max_base_shear_kN", base_hf_kn)),
            )
            base_ssi, ssi_response_backend = _extract_tail_scalar(
                ssi,
                key="base_shear_kN",
                default=float(ssi.get("max_base_shear_kN", base_hf_kn)),
            )
            shear_delta_ratio = abs(base_ssi - base_fixed) / max(abs(base_fixed), 1e-9)
            shear_delta_ratios.append(float(shear_delta_ratio))

            rust_backend_all = bool(rust_backend_all and fixed_rust and ssi_rust)
            converged_all = bool(converged_all and fixed_conv and ssi_conv)
            no_collapse_all = bool(no_collapse_all and (not fixed_collapsed) and (not ssi_collapsed))
            section_ok = bool(float((section_profile.get("summary") or {}).get("stiffness_scale_min", 1.0)) >= 0.95)
            material_ok = bool((not use_rc) or (float(material_indices.get("cracking_index_mean", 0.0)) > 0.0 and float(material_indices.get("stiffness_scale_mean", 1.0)) < 1.0))
            section_family_all = bool(section_family_all and section_ok)
            material_model_all = bool(material_model_all and material_ok)

            out_rows.append(
                {
                    "case_id": case_id,
                    "split": str(case.get("split", "")),
                    "topology_type": topology,
                    "fixed": {
                        "converged_all_steps": bool(fixed_conv),
                        "rust_backend_ok": bool(fixed_rust),
                        "collapsed": bool(fixed_collapsed),
                        "max_drift_ratio_pct": float(fixed.get("max_drift_ratio_pct", 0.0)),
                        "max_base_shear_kN": float(base_fixed),
                        "residual_pre_settle_top_displacement_m": float(fixed_pre_top),
                        "residual_top_displacement_m": float(fixed_post_top),
                        "residual_pre_settle_drift_ratio_pct": float(fixed_pre_drift),
                        "residual_drift_ratio_pct": float(fixed_post_drift),
                        "residual_settle_applied": bool(fixed.get("residual_settle_applied", False)),
                        "residual_settle_steps": int(fixed.get("residual_settle_steps", 0)),
                        "response_backend": str(fixed_response_backend),
                    },
                    "ssi": {
                        "converged_all_steps": bool(ssi_conv),
                        "rust_backend_ok": bool(ssi_rust),
                        "collapsed": bool(ssi_collapsed),
                        "max_drift_ratio_pct": float(ssi.get("max_drift_ratio_pct", 0.0)),
                        "max_base_shear_kN": float(base_ssi),
                        "residual_pre_settle_top_displacement_m": float(ssi_pre_top),
                        "residual_top_displacement_m": float(ssi_post_top),
                        "residual_pre_settle_drift_ratio_pct": float(ssi_pre_drift),
                        "residual_drift_ratio_pct": float(ssi_post_drift),
                        "residual_settle_applied": bool(ssi.get("residual_settle_applied", False)),
                        "residual_settle_steps": int(ssi.get("residual_settle_steps", 0)),
                        "response_backend": str(ssi_response_backend),
                    },
                    "shear_delta_ratio": float(shear_delta_ratio),
                    "section_profile": dict(section_profile.get("summary", {})),
                    "section_family_counts": dict(section_profile.get("family_counts", {})),
                    "material_model": "rc_composite" if use_rc else "steel_elastic_plastic",
                    "material_indices": material_indices,
                    "material_model_pass": bool(material_ok),
                    "residual_trace_pass": bool(residual_trace_pass_case),
                }
            )

        ratio_span = float(np.max(nonlinear_ratio) - np.min(nonlinear_ratio))
        section_demand_summary = _section_family_beam_demand_summary(
            [row.get("section_profile", {}) for row in out_rows]
        )
        response_contract = _response_backend_contract(out_rows, allow_cpu_required=bool(args.allow_cpu_required))
        checks = {
            "case_count_pass": bool(len(rows) >= int(args.min_case_count)),
            "ssi_nonlinear_boundary_active": bool(ratio_span >= float(args.min_nonlinear_ratio_span)),
            "ssi_transfer_finite": bool(np.all(np.isfinite(nonlinear_ratio))),
            "all_cases_converged": bool(converged_all),
            "rust_backend_used_pass": bool(rust_backend_all),
            "no_collapse_detected": bool(no_collapse_all),
            "section_family_pass": bool(section_family_all),
            "material_model_pass": bool(material_model_all),
            "shear_delta_pass": bool(
                len(shear_delta_ratios) > 0
                and min(shear_delta_ratios) >= float(args.min_shear_delta_ratio)
                and max(shear_delta_ratios) <= float(args.max_shear_delta_ratio)
            ),
            "residual_trace_pass": bool(all(bool(row.get("residual_trace_pass", False)) for row in out_rows)),
            "response_artifacts_consumed_pass": bool(response_contract["response_artifacts_consumed_pass"]),
            "device_artifacts_consumed_pass": bool(response_contract["response_artifacts_consumed_pass"]),
            "cpu_required_allowed_pass": bool(
                (not bool(args.allow_cpu_required))
                or bool(response_contract["device_artifacts_consumed"])
                or bool(response_contract["cpu_required_allowed"])
            ),
        }
        contract_pass = bool(all(checks.values()))
        if not checks["case_count_pass"]:
            reason_code = "ERR_CASES"
        elif not checks["ssi_transfer_finite"] or not checks["ssi_nonlinear_boundary_active"]:
            reason_code = "ERR_SSI_MODEL"
        elif not checks["all_cases_converged"] or not checks["no_collapse_detected"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["section_family_pass"] or not checks["material_model_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif (
            not checks["shear_delta_pass"]
            or not checks["rust_backend_used_pass"]
            or not checks["response_artifacts_consumed_pass"]
            or not checks["cpu_required_allowed_pass"]
        ):
            reason_code = "ERR_VNV_FAIL"
        else:
            reason_code = "PASS"

        metrics_npz_summary = _write_case_metrics_npz(case_metrics_npz_out, out_rows)
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-ssi-boundary-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "artifacts": {
                "report_json": str(out),
                "case_metrics_npz_out": str(case_metrics_npz_out),
            },
            "summary": {
                "selected_case_count": int(len(rows)),
                "soil_profile": str(args.soil_profile),
                "dominant_frequency_hz": float(dom_f),
                "preprocess_backend": str(preprocess_backend),
                "nonlinear_ratio_min": float(np.min(nonlinear_ratio)),
                "nonlinear_ratio_max": float(np.max(nonlinear_ratio)),
                "nonlinear_ratio_span": float(ratio_span),
                "shear_delta_ratio_min": float(min(shear_delta_ratios) if shear_delta_ratios else math.inf),
                "shear_delta_ratio_max": float(max(shear_delta_ratios) if shear_delta_ratios else math.inf),
                "fixed_residual_pre_settle_top_m_max_abs": float(
                    max((float((row.get("fixed") or {}).get("residual_pre_settle_top_displacement_m", 0.0)) for row in out_rows), default=0.0)
                ),
                "fixed_residual_top_m_max_abs": float(
                    max((float((row.get("fixed") or {}).get("residual_top_displacement_m", 0.0)) for row in out_rows), default=0.0)
                ),
                "fixed_residual_pre_settle_drift_pct_max_abs": float(
                    max((float((row.get("fixed") or {}).get("residual_pre_settle_drift_ratio_pct", 0.0)) for row in out_rows), default=0.0)
                ),
                "fixed_residual_drift_pct_max_abs": float(
                    max((float((row.get("fixed") or {}).get("residual_drift_ratio_pct", 0.0)) for row in out_rows), default=0.0)
                ),
                "ssi_residual_pre_settle_top_m_max_abs": float(
                    max((float((row.get("ssi") or {}).get("residual_pre_settle_top_displacement_m", 0.0)) for row in out_rows), default=0.0)
                ),
                "ssi_residual_top_m_max_abs": float(
                    max((float((row.get("ssi") or {}).get("residual_top_displacement_m", 0.0)) for row in out_rows), default=0.0)
                ),
                "ssi_residual_pre_settle_drift_pct_max_abs": float(
                    max((float((row.get("ssi") or {}).get("residual_pre_settle_drift_ratio_pct", 0.0)) for row in out_rows), default=0.0)
                ),
                "ssi_residual_drift_pct_max_abs": float(
                    max((float((row.get("ssi") or {}).get("residual_drift_ratio_pct", 0.0)) for row in out_rows), default=0.0)
                ),
                "residual_settle_case_count": int(
                    sum(
                        1
                        for row in out_rows
                        if bool((row.get("fixed") or {}).get("residual_settle_applied", False))
                        or bool((row.get("ssi") or {}).get("residual_settle_applied", False))
                    )
                ),
                "device_artifact_consumer": str(response_contract["consumer_label"]),
                "response_artifact_consumer": str(response_contract["consumer_label"]),
                "response_backends": list(response_contract["response_backends"]),
                "cpu_required_allowed": bool(response_contract["cpu_required_allowed"]),
                "device_artifact_case_count": int(
                    sum(
                        1
                        for row in out_rows
                        if str((row.get("fixed") or {}).get("response_backend", "")) == "dlpack_zero_copy"
                        and str((row.get("ssi") or {}).get("response_backend", "")) == "dlpack_zero_copy"
                    )
                ),
                "response_storage": "npz_external+inline_summary",
                "response_binary_consumer": (
                    "dlpack_zero_copy_primary"
                    if bool(out_rows)
                    and all(
                        str((row.get("fixed") or {}).get("response_backend", "")) == "dlpack_zero_copy"
                        and str((row.get("ssi") or {}).get("response_backend", "")) == "dlpack_zero_copy"
                        for row in out_rows
                    )
                    else "mixed_host_or_device"
                ),
                "case_metrics_npz_case_count": int(metrics_npz_summary.get("case_count", 0)),
                "section_family_beam_tangent_scale_min": float(section_demand_summary["beam_tangent_scale_min"]),
                "section_family_beam_tangent_scale_mean": float(section_demand_summary["beam_tangent_scale_mean"]),
                "section_family_beam_yielded_story_count_max": int(
                    section_demand_summary["beam_yielded_story_count_max"]
                ),
                "section_family_beam_max_trial_end_moment_ratio": float(
                    section_demand_summary["beam_max_trial_end_moment_ratio"]
                ),
                "section_family_beam_stability_index_max": float(
                    section_demand_summary["beam_stability_index_max"]
                ),
                "section_family_beam_strain_energy_total_n_m": float(
                    section_demand_summary["beam_strain_energy_total_n_m"]
                ),
            },
            "summary_line": (
                f"SSI boundary: {'PASS' if contract_pass else 'CHECK'} | "
                f"cases={len(rows)} | "
                f"ratio_span={float(ratio_span):.3f} | "
                f"shear_delta_max={float(max(shear_delta_ratios) if shear_delta_ratios else math.inf):.3f} | "
                f"residual_settle={int(sum(bool(row.get('residual_trace_pass', False)) for row in out_rows))}/{len(out_rows)} | "
                f"section_demand={'pass' if bool(section_demand_summary['present']) else 'tracked'}"
                f"(tangent={float(section_demand_summary['beam_tangent_scale_min']):.2f},"
                f"demand={float(section_demand_summary['beam_max_trial_end_moment_ratio']):.2f},"
                f"stability={float(section_demand_summary['beam_stability_index_max']):.2f})"
            ),
            "reasons": [
                (
                    f"ssi_boundary={'pass' if checks['ssi_nonlinear_boundary_active'] and checks['ssi_transfer_finite'] else 'check'} via "
                    f"ratio_min={float(np.min(nonlinear_ratio)):.3f}, "
                    f"ratio_max={float(np.max(nonlinear_ratio)):.3f}, "
                    f"ratio_span={float(ratio_span):.3f}."
                ),
                (
                    f"residual_trace={'pass' if checks['residual_trace_pass'] else 'check'} via "
                    f"cases={len(out_rows)}, "
                    f"fixed_post_max={float(max((float((row.get('fixed') or {}).get('residual_drift_ratio_pct', 0.0)) for row in out_rows), default=0.0)):.4f}, "
                    f"ssi_post_max={float(max((float((row.get('ssi') or {}).get('residual_drift_ratio_pct', 0.0)) for row in out_rows), default=0.0)):.4f}."
                ),
                (
                    f"section_family_demand={'pass' if bool(section_demand_summary['present']) else 'tracked'} via "
                    f"profiles={int(section_demand_summary['profile_count'])}, "
                    f"tangent={float(section_demand_summary['beam_tangent_scale_min']):.2f}, "
                    f"yielded_story_max={int(section_demand_summary['beam_yielded_story_count_max'])}, "
                    f"demand={float(section_demand_summary['beam_max_trial_end_moment_ratio']):.2f}, "
                    f"stability={float(section_demand_summary['beam_stability_index_max']):.2f}."
                ),
            ],
            "rows": out_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["artifact_archive_manifest"] = _archive([str(out), str(case_metrics_npz_out), str(args.ground_motion_csv)])
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "ssi_gate.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote SSI boundary gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, FileNotFoundError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-ssi-boundary-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "ssi_gate.invalid_input", error=str(exc))
        print(f"Wrote SSI boundary gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
