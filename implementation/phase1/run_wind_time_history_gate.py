#!/usr/bin/env python3
"""Wind time-history benchmark gate for megatall across-wind validation."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    RustNonlinearNdthaConfig,
    build_story_load_profile,
    consume_dlpack_bundle,
    solve_nonlinear_frame_ndtha,
)
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from section_family_library import evaluate_story_section_profile


G = 9.80665

REASONS = {
    "PASS": "wind time-history gate passed",
    "ERR_INVALID_INPUT": "invalid wind gate input",
    "ERR_SOURCE_MANIFEST": "wind source manifest validation failed",
    "ERR_WIND_INPUT": "wind time-history input is missing or invalid",
    "ERR_CASES": "wind-capable benchmark cases missing or insufficient",
    "ERR_ENGINE_FAIL": "rust nonlinear engine failed during wind chunks",
    "ERR_VNV_FAIL": "wind vnv thresholds violated",
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


def _gpu_zero_cross_metrics(torch, x: np.ndarray, dt: float, eps: float) -> tuple[float, int]:
    with torch.no_grad():
        device = torch.device("cuda:0")
        y = torch.as_tensor(x, dtype=torch.float64, device=device)
        y = y - torch.mean(y)
        sign = torch.sign(y)
        sign = torch.where(torch.abs(y) <= float(eps), torch.zeros_like(sign), sign)
        nz = sign[sign != 0]
        reversals = int(torch.count_nonzero(nz[1:] != nz[:-1]).item()) if int(nz.numel()) >= 2 else 0
        cross = torch.logical_or(
            torch.logical_and(y[:-1] <= 0.0, y[1:] > 0.0),
            torch.logical_and(y[:-1] >= 0.0, y[1:] < 0.0),
        )
        crossing_count = int(torch.count_nonzero(cross).item())
        duration = max(float(dt) * max(int(y.numel()) - 1, 1), 1.0e-9)
        dom_freq = float(crossing_count) / (2.0 * duration) if crossing_count >= 2 else 0.0
        return dom_freq, reversals

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "wind_csv",
        "source_manifest",
        "target_split",
        "min_case_count",
        "max_case_count",
        "min_duration_hours",
        "min_load_reversals",
        "analysis_stride",
        "max_chunk_steps",
        "min_chunk_count",
        "ag_scale",
        "yield_drift_scale",
        "hardening_ratio",
        "pdelta_factor",
        "max_step_iterations",
        "step_tol",
        "adaptive_load_decay",
        "damping_force_cap_ratio",
        "collapse_drift_threshold_pct",
        "rayleigh_alpha",
        "rayleigh_beta",
        "max_drift_pct",
        "require_rust_backend",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "wind_csv": {"type": "string", "minLength": 1},
        "source_manifest": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "min_duration_hours": {"type": "number", "exclusiveMinimum": 0.0},
        "min_load_reversals": {"type": "integer", "minimum": 1},
        "analysis_stride": {"type": "integer", "minimum": 1},
        "max_chunk_steps": {"type": "integer", "minimum": 32},
        "min_chunk_count": {"type": "integer", "minimum": 1},
        "ag_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "yield_drift_scale": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "hardening_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pdelta_factor": {"type": "number", "minimum": 0.0},
        "max_step_iterations": {"type": "integer", "minimum": 1},
        "step_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "adaptive_load_decay": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "damping_force_cap_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "collapse_drift_threshold_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "rayleigh_alpha": {"type": "number", "minimum": 0.0},
        "rayleigh_beta": {"type": "number", "minimum": 0.0},
        "max_drift_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "require_rust_backend": {"type": "boolean"},
        "case_metrics_npz_out": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _load_wind_history(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 16:
        raise ValueError("wind csv must have >=16 rows")
    if "time_s" not in rows[0] or "across_wind_force_kN" not in rows[0]:
        raise ValueError("wind csv must include columns: time_s, across_wind_force_kN")

    t: list[float] = []
    fx: list[float] = []
    for i, r in enumerate(rows):
        try:
            ti = float(r["time_s"])
            fi = float(r["across_wind_force_kN"])
        except Exception as exc:
            raise ValueError(f"invalid row {i}: {exc}") from exc
        t.append(ti)
        fx.append(fi)

    t_arr = np.asarray(t, dtype=np.float64)
    fx_arr = np.asarray(fx, dtype=np.float64)
    dt = float(t_arr[1] - t_arr[0])
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("non-positive dt")
    if np.max(np.abs(np.diff(t_arr) - dt)) > 1e-6:
        raise ValueError("wind time axis must be uniform")
    return t_arr, fx_arr


def _wind_signal_metrics(x: np.ndarray, dt: float, eps: float = 1e-9) -> tuple[float, int, str]:
    if x.size < 8:
        return 0.0, 0, "cpu_numpy"
    torch = _load_gpu_torch()
    if torch is not None:
        try:
            dom_freq, rev = _gpu_zero_cross_metrics(torch, x, dt, eps)
            return dom_freq, rev, "rocm_torch_full"
        except Exception:
            if _gpu_preprocess_strict():
                raise RuntimeError("GPU preprocess required for wind metrics; CPU fallback disabled")

    if _gpu_preprocess_strict():
        raise RuntimeError("GPU preprocess required for wind metrics; GPU runtime unavailable")

    y_cpu = x - float(np.mean(x))
    s = np.sign(y_cpu)
    s[np.abs(y_cpu) <= eps] = 0.0
    rev = 0
    prev = 0.0
    for v in s:
        if v == 0.0:
            continue
        if prev != 0.0 and v != prev:
            rev += 1
        prev = v
    crossing_count = int(np.count_nonzero(np.logical_or(
        np.logical_and(y_cpu[:-1] <= 0.0, y_cpu[1:] > 0.0),
        np.logical_and(y_cpu[:-1] >= 0.0, y_cpu[1:] < 0.0),
    )))
    duration = max(float(dt) * max(int(x.size) - 1, 1), 1.0e-9)
    dom_freq = float(crossing_count) / (2.0 * duration) if crossing_count >= 2 else 0.0
    return dom_freq, int(rev), "cpu_numpy"


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


def _normalize_scale(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    mean = float(np.mean(arr)) if arr.size else 1.0
    if not math.isfinite(mean) or mean <= 1e-9:
        return np.ones_like(arr, dtype=np.float64)
    return arr / mean


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


def _validate_source_manifest(manifest: dict, wind_csv: Path) -> tuple[bool, str]:
    if not isinstance(manifest, dict):
        return False, "manifest is not object"
    if not bool(manifest.get("real_source", False)):
        return False, "real_source must be true"
    src = Path(str(manifest.get("data_path", "")).strip())
    if not src.exists():
        return False, "manifest data_path missing"
    if src.resolve() != wind_csv.resolve():
        return False, "manifest data_path does not match wind_csv"
    if not str(manifest.get("source_url", "")).strip():
        return False, "manifest source_url missing"
    sha = str(manifest.get("sha256", "")).strip().lower()
    if len(sha) != 64:
        return False, "manifest sha256 invalid"
    if sha != _sha256_file(wind_csv):
        return False, "manifest sha256 mismatch"
    return True, ""


def _default_case_metrics_npz_out(report_out: Path) -> Path:
    if report_out.suffix:
        return report_out.with_suffix(".metrics.npz")
    return report_out.parent / f"{report_out.name}.metrics.npz"


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
                raise RuntimeError(f"GPU DLPack consumer failed for wind key={key}")
    response = result.get("response")
    if isinstance(response, dict):
        values = response.get(str(key))
        if values is not None:
            arr = np.asarray(values, dtype=np.float64).reshape(-1)
            if arr.size > 0:
                return float(arr[-1]), "host_response"
    return float(default), "fallback_default"


def _write_case_metrics_npz(path: Path, rows: list[dict]) -> dict[str, object]:
    payload = {
        "case_ids": np.asarray([str(row.get("case_id", "")) for row in rows], dtype="<U128"),
        "splits": np.asarray([str(row.get("split", "")) for row in rows], dtype="<U32"),
        "topology_types": np.asarray([str(row.get("topology_type", "")) for row in rows], dtype="<U64"),
        "material_types": np.asarray([str(row.get("material_type", "")) for row in rows], dtype="<U64"),
        "chunk_count": np.asarray([int(row.get("chunk_count", 0)) for row in rows], dtype=np.int32),
        "coverage_ratio": np.asarray([float(row.get("coverage_ratio", 0.0)) for row in rows], dtype=np.float64),
        "max_drift_ratio_pct": np.asarray([float(row.get("max_drift_ratio_pct", 0.0)) for row in rows], dtype=np.float64),
        "max_plastic_story_count": np.asarray([int(row.get("max_plastic_story_count", 0)) for row in rows], dtype=np.int32),
        "residual_pre_top_m": np.asarray([float(row.get("residual_pre_settle_top_m_max_abs", 0.0)) for row in rows], dtype=np.float64),
        "residual_post_top_m": np.asarray([float(row.get("residual_top_m_max_abs", 0.0)) for row in rows], dtype=np.float64),
        "residual_pre_drift_pct": np.asarray([float(row.get("residual_pre_settle_drift_pct_max_abs", 0.0)) for row in rows], dtype=np.float64),
        "residual_post_drift_pct": np.asarray([float(row.get("residual_drift_pct_max_abs", 0.0)) for row in rows], dtype=np.float64),
        "residual_settle_chunk_count": np.asarray([int(row.get("residual_settle_chunk_count", 0)) for row in rows], dtype=np.int32),
        "section_stiffness_scale_min": np.asarray([float(((row.get("section_profile") or {}).get("stiffness_scale_min", 1.0))) for row in rows], dtype=np.float64),
        "material_model_pass": np.asarray([bool(row.get("material_model_pass", False)) for row in rows], dtype=np.bool_),
        "section_family_pass": np.asarray([bool(row.get("section_family_pass", False)) for row in rows], dtype=np.bool_),
        "residual_trace_pass": np.asarray([bool(row.get("residual_trace_pass", False)) for row in rows], dtype=np.bool_),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    return {"path": str(path), "case_count": len(rows), "storage": "npz_external"}


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="wind_time_history_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase3.run_wind_time_history_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--wind-csv", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.csv")
    p.add_argument("--source-manifest", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.manifest.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--min-case-count", type=int, default=2)
    p.add_argument("--max-case-count", type=int, default=4)
    p.add_argument("--min-duration-hours", type=float, default=10.0)
    p.add_argument("--min-load-reversals", type=int, default=100)
    p.add_argument("--analysis-stride", type=int, default=1)
    p.add_argument("--max-chunk-steps", type=int, default=2048)
    p.add_argument("--min-chunk-count", type=int, default=2)
    p.add_argument("--ag-scale", type=float, default=1.0)
    p.add_argument("--yield-drift-scale", type=float, default=0.60)
    p.add_argument("--hardening-ratio", type=float, default=0.20)
    p.add_argument("--pdelta-factor", type=float, default=1.0)
    p.add_argument("--max-step-iterations", type=int, default=16)
    p.add_argument("--step-tol", type=float, default=1e-4)
    p.add_argument("--adaptive-load-decay", type=float, default=0.85)
    p.add_argument("--damping-force-cap-ratio", type=float, default=0.6)
    p.add_argument("--collapse-drift-threshold-pct", type=float, default=10.0)
    p.add_argument("--rayleigh-alpha", type=float, default=0.03)
    p.add_argument("--rayleigh-beta", type=float, default=1e-6)
    p.add_argument("--max-drift-pct", type=float, default=8.0)
    p.add_argument("--require-rust-backend", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--case-metrics-npz-out", default="")
    p.add_argument("--out", default="implementation/phase1/wind_time_history_gate_report.json")
    args = p.parse_args()
    case_metrics_npz_out = Path(str(args.case_metrics_npz_out)) if str(args.case_metrics_npz_out).strip() else _default_case_metrics_npz_out(Path(args.out))

    input_payload = {
        "cases": str(args.cases),
        "wind_csv": str(args.wind_csv),
        "source_manifest": str(args.source_manifest),
        "target_split": str(args.target_split),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "min_duration_hours": float(args.min_duration_hours),
        "min_load_reversals": int(args.min_load_reversals),
        "analysis_stride": int(args.analysis_stride),
        "max_chunk_steps": int(args.max_chunk_steps),
        "min_chunk_count": int(args.min_chunk_count),
        "ag_scale": float(args.ag_scale),
        "yield_drift_scale": float(args.yield_drift_scale),
        "hardening_ratio": float(args.hardening_ratio),
        "pdelta_factor": float(args.pdelta_factor),
        "max_step_iterations": int(args.max_step_iterations),
        "step_tol": float(args.step_tol),
        "adaptive_load_decay": float(args.adaptive_load_decay),
        "damping_force_cap_ratio": float(args.damping_force_cap_ratio),
        "collapse_drift_threshold_pct": float(args.collapse_drift_threshold_pct),
        "rayleigh_alpha": float(args.rayleigh_alpha),
        "rayleigh_beta": float(args.rayleigh_beta),
        "max_drift_pct": float(args.max_drift_pct),
        "require_rust_backend": bool(args.require_rust_backend),
        "case_metrics_npz_out": str(case_metrics_npz_out),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_wind_time_history_gate")
        log_event(logger, logging.INFO, "wind_gate.start", inputs=input_payload)

        wind_path = Path(args.wind_csv)
        t_full, fx_full_kn = _load_wind_history(wind_path)
        dt_full = float(t_full[1] - t_full[0])
        duration_h = float((t_full[-1] - t_full[0]) / 3600.0)
        dom_freq_hz, reversals_full, preprocess_backend = _wind_signal_metrics(fx_full_kn, dt_full)

        manifest = _load_json(Path(args.source_manifest))
        source_manifest_pass, source_manifest_error = _validate_source_manifest(manifest, wind_path)
        if not source_manifest_pass:
            raise RuntimeError(f"{REASONS['ERR_SOURCE_MANIFEST']}: {source_manifest_error}")

        stride = int(args.analysis_stride)
        t = t_full[::stride]
        fx_kn = fx_full_kn[::stride]
        if t.size < 16:
            raise ValueError("analysis stride too large; effective time-series too short")
        dt = float(t[1] - t[0])

        cases_payload = _load_json(Path(args.cases))
        raw_cases = cases_payload.get("cases")
        if not isinstance(raw_cases, list):
            raise ValueError("cases[] missing")
        rows = [c for c in raw_cases if isinstance(c, dict) and str(c.get("hazard_type", "")).strip().lower() in {"wind", "combined"}]
        if str(args.target_split) != "all":
            rows = [c for c in rows if str(c.get("split", "")) == str(args.target_split)]
        rows = rows[: int(args.max_case_count)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"selected wind cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        rust_cfg = RustNonlinearFrameConfig(
            tolerance=max(1e-9, float(args.step_tol) * 0.1),
            max_iter=max(16, int(args.max_step_iterations) * 4),
            hardening_ratio=float(args.hardening_ratio),
            pdelta_factor=float(args.pdelta_factor),
        )

        ndtha_cfg = RustNonlinearNdthaConfig(
            dt_s=float(dt),
            newmark_beta=0.25,
            newmark_gamma=0.5,
            tolerance=float(args.step_tol),
            max_step_iterations=int(args.max_step_iterations),
            adaptive_load_decay=float(args.adaptive_load_decay),
            damping_force_cap_ratio=float(args.damping_force_cap_ratio),
            newton_max_iter=max(40, int(args.max_step_iterations) * 6),
            hardening_ratio=float(args.hardening_ratio),
            pdelta_factor=float(args.pdelta_factor),
            collapse_drift_threshold_pct=float(args.collapse_drift_threshold_pct),
        )

        out_rows: list[dict] = []
        all_converged = True
        rust_backend_all = True
        no_collapse_all = True
        section_family_all = True
        material_model_all = True
        max_drift_all = 0.0
        chunk_count_total = 0
        coverage_ratios: list[float] = []

        for case in rows:
            case_id = str(case.get("case_id", "unknown"))
            topology = str(case.get("topology_type", "rahmen"))
            material_type = str(case.get("material_type", "steel")).strip().lower()
            load_scale = float(case.get("load_scale", 1.0))
            story_n = _story_count_for_topology(topology)
            story_h = np.full(story_n, 3.2, dtype=np.float64)

            drift_hf_pct = float((((case.get("metrics") or {}).get("drift_ratio_pct") or {}).get("hf", 1.2)))
            base_hf_kn = float((((case.get("metrics") or {}).get("base_shear_kN") or {}).get("hf", 1000.0)))
            base_hf_n = max(1.0, base_hf_kn * 1000.0)
            floor_load = build_story_load_profile(story_n, base_hf_n, mode="triangular")
            story_k = _build_story_stiffness_from_drift(
                floor_load_n=floor_load,
                story_h_m=story_h,
                drift_ratio_hf=max(1e-6, drift_hf_pct / 100.0),
            )
            story_mass = np.linspace(5.2e5, 3.1e5, num=story_n, dtype=np.float64)
            story_damp = np.maximum(
                1e2,
                float(args.rayleigh_alpha) * story_mass + float(args.rayleigh_beta) * story_k,
            )
            story_yield = np.maximum(
                1e-4,
                float(args.yield_drift_scale) * (drift_hf_pct / 100.0) * story_h,
            )
            story_axial = (4.0e6 * load_scale) * np.linspace(1.3, 0.85, num=story_n, dtype=np.float64)

            drift_profile = np.linspace(
                max(2.0e-4, 0.45 * drift_hf_pct / 100.0),
                max(4.0e-4, drift_hf_pct / 100.0),
                num=story_n,
                dtype=np.float64,
            )
            section_profile = evaluate_story_section_profile(
                topology=topology,
                material_type=material_type,
                story_h_m=story_h,
                drift_ratio_profile=drift_profile,
                load_scale=load_scale,
            )
            story_k = story_k * _normalize_scale(section_profile["story_stiffness_scale"])
            story_yield = story_yield * _normalize_scale(section_profile["story_yield_scale"])
            section_ok = bool(float((section_profile.get("summary") or {}).get("stiffness_scale_min", 1.0)) >= 0.95)

            use_rc = material_type in {"rc", "composite", "rc_composite"}
            material_indices: dict[str, float | int] = {}
            material_model = "rc_composite" if use_rc else "steel_elastic_plastic"
            if use_rc:
                rc_mod = apply_rc_composite_profile(
                    story_k_n_per_m=story_k,
                    story_yield_drift_m=story_yield,
                    story_mass_kg=story_mass,
                    story_h_m=story_h,
                    drift_ratio_proxy=drift_profile,
                    elapsed_hours=max(duration_h, 1.0),
                    cycle_count=max(reversals_full, 1),
                    cfg=RCCompositeMaterialConfig(),
                )
                rc_k_scale = np.divide(
                    np.asarray(rc_mod["story_k_n_per_m"], dtype=np.float64),
                    np.maximum(story_k, 1e-9),
                )
                rc_y_scale = np.divide(
                    np.asarray(rc_mod["story_yield_drift_m"], dtype=np.float64),
                    np.maximum(story_yield, 1e-9),
                )
                story_k = story_k * _normalize_scale(rc_k_scale)
                story_yield = story_yield * _normalize_scale(rc_y_scale)
                story_mass = np.asarray(rc_mod["story_mass_kg"], dtype=np.float64)
                material_indices = dict(rc_mod.get("indices", {}))
            material_ok = bool(
                (not use_rc)
                or (
                    math.isfinite(float(material_indices.get("stiffness_scale_min", 1.0)))
                    and math.isfinite(float(material_indices.get("yield_scale_min", 1.0)))
                    and float(material_indices.get("yield_scale_min", 1.0)) >= 0.70
                )
            )

            # Wind force -> equivalent base acceleration (g) using total mass.
            ag_g = (fx_kn * 1000.0 / max(np.sum(story_mass), 1e-9)) / G
            ag_g = np.asarray(ag_g * float(args.ag_scale), dtype=np.float64)

            n_steps = int(ag_g.shape[0])
            max_chunk = int(args.max_chunk_steps)
            case_chunk_rows: list[dict] = []
            case_max_drift = 0.0
            case_plastic_max = 0
            converged_case = True
            rust_case = True
            collapsed_case = False
            done_steps = 0
            case_residual_pre_top_max = 0.0
            case_residual_post_top_max = 0.0
            case_residual_pre_drift_max = 0.0
            case_residual_post_drift_max = 0.0
            residual_trace_pass_case = True
            residual_settle_chunk_count = 0

            for i0 in range(0, n_steps, max_chunk):
                i1 = min(n_steps, i0 + max_chunk)
                ag_chunk = ag_g[i0:i1]
                solved = solve_nonlinear_frame_ndtha(
                    story_k_n_per_m=story_k,
                    story_h_m=story_h,
                    story_axial_n=story_axial,
                    story_yield_drift_m=story_yield,
                    story_mass_kg=story_mass,
                    story_damping_n_s_per_m=story_damp,
                    floor_load_base_n=floor_load,
                    ag_g=ag_chunk,
                    cfg=ndtha_cfg,
                    keep_device_artifacts=True,
                )
                checks = solved.get("checks") if isinstance(solved.get("checks"), dict) else {}
                backend = str(solved.get("backend", ""))
                chunk_converged = bool(solved.get("converged_all_steps", False))
                chunk_rust = bool(str(backend).startswith("rust_ffi_")) and int(solved.get("status", -999)) == 0
                chunk_collapsed = bool(solved.get("collapsed", False))
                max_drift_chunk = float(solved.get("max_drift_ratio_pct", 0.0))
                max_plastic_chunk = int(solved.get("max_plastic_story_count", 0))
                residual_pre_top = abs(float(solved.get("residual_pre_settle_top_displacement_m", solved.get("residual_top_displacement_m", 0.0))))
                residual_post_top = abs(float(solved.get("residual_top_displacement_m", 0.0)))
                residual_pre_drift = abs(float(solved.get("residual_pre_settle_drift_ratio_pct", solved.get("residual_drift_ratio_pct", 0.0))))
                residual_post_drift = abs(float(solved.get("residual_drift_ratio_pct", 0.0)))
                residual_settle_applied = bool(solved.get("residual_settle_applied", False))
                residual_settle_steps = int(solved.get("residual_settle_steps", 0))
                final_top_disp, response_backend = _extract_tail_scalar(
                    solved,
                    key="top_displacement_m",
                    default=0.0,
                )
                done_steps += int(solved.get("step_count_completed", i1 - i0))
                case_max_drift = max(case_max_drift, max_drift_chunk)
                case_plastic_max = max(case_plastic_max, max_plastic_chunk)
                converged_case = bool(converged_case and chunk_converged)
                rust_case = bool(rust_case and chunk_rust)
                collapsed_case = bool(collapsed_case or chunk_collapsed)
                case_residual_pre_top_max = max(case_residual_pre_top_max, residual_pre_top)
                case_residual_post_top_max = max(case_residual_post_top_max, residual_post_top)
                case_residual_pre_drift_max = max(case_residual_pre_drift_max, residual_pre_drift)
                case_residual_post_drift_max = max(case_residual_post_drift_max, residual_post_drift)
                residual_trace_pass_case = bool(
                    residual_trace_pass_case
                    and math.isfinite(residual_pre_top)
                    and math.isfinite(residual_post_top)
                    and math.isfinite(residual_pre_drift)
                    and math.isfinite(residual_post_drift)
                    and residual_post_top <= residual_pre_top + 1e-9
                    and residual_post_drift <= residual_pre_drift + 1e-9
                )
                residual_settle_chunk_count += int(residual_settle_applied)
                case_chunk_rows.append(
                    {
                        "chunk_index": int(len(case_chunk_rows)),
                        "step_start": int(i0),
                        "step_end": int(i1),
                        "step_count_completed": int(solved.get("step_count_completed", i1 - i0)),
                        "converged_all_steps": bool(chunk_converged),
                        "rust_backend_ok": bool(chunk_rust),
                        "collapsed": bool(chunk_collapsed),
                        "max_drift_ratio_pct": float(max_drift_chunk),
                        "max_plastic_story_count": int(max_plastic_chunk),
                        "residual_pre_settle_top_displacement_m": float(residual_pre_top),
                        "residual_top_displacement_m": float(residual_post_top),
                        "residual_pre_settle_drift_ratio_pct": float(residual_pre_drift),
                        "residual_drift_ratio_pct": float(residual_post_drift),
                        "residual_settle_applied": bool(residual_settle_applied),
                        "residual_settle_steps": int(residual_settle_steps),
                        "final_top_displacement_m": float(final_top_disp),
                        "response_backend": str(response_backend),
                        "status_code": int(solved.get("status_code", solved.get("status", -1))),
                        "line_search_backtracks": int(solved.get("line_search_backtracks_total", 0)),
                        "checks_head": {k: checks[k] for k in sorted(checks)[:6]},
                    }
                )

            coverage = float(done_steps / max(1, n_steps))
            coverage_ratios.append(coverage)
            chunk_count_total += len(case_chunk_rows)
            max_drift_all = max(max_drift_all, case_max_drift)
            all_converged = bool(all_converged and converged_case)
            rust_backend_all = bool(rust_backend_all and rust_case)
            no_collapse_all = bool(no_collapse_all and (not collapsed_case))
            section_family_all = bool(section_family_all and section_ok)
            material_model_all = bool(material_model_all and material_ok)
            out_rows.append(
                {
                    "case_id": case_id,
                    "split": str(case.get("split", "")),
                    "topology_type": topology,
                    "material_type": material_type,
                    "chunk_count": int(len(case_chunk_rows)),
                    "coverage_ratio": float(coverage),
                    "converged": bool(converged_case),
                    "rust_backend_ok": bool(rust_case),
                    "collapsed": bool(collapsed_case),
                    "max_drift_ratio_pct": float(case_max_drift),
                    "max_plastic_story_count": int(case_plastic_max),
                    "section_profile": dict(section_profile.get("summary", {})),
                    "section_family_counts": dict(section_profile.get("family_counts", {})),
                    "material_model": material_model,
                    "material_indices": material_indices,
                    "section_family_pass": bool(section_ok),
                    "material_model_pass": bool(material_ok),
                    "residual_pre_settle_top_m_max_abs": float(case_residual_pre_top_max),
                    "residual_top_m_max_abs": float(case_residual_post_top_max),
                    "residual_pre_settle_drift_pct_max_abs": float(case_residual_pre_drift_max),
                    "residual_drift_pct_max_abs": float(case_residual_post_drift_max),
                    "residual_trace_pass": bool(residual_trace_pass_case),
                    "residual_settle_chunk_count": int(residual_settle_chunk_count),
                    "chunk_rows_head": case_chunk_rows[:32],
                }
            )

        checks = {
            "source_manifest_pass": bool(source_manifest_pass),
            "wind_duration_pass": bool(duration_h >= float(args.min_duration_hours)),
            "wind_reversal_pass": bool(reversals_full >= int(args.min_load_reversals)),
            "case_count_pass": bool(len(rows) >= int(args.min_case_count)),
            "long_series_chunked_pass": bool(chunk_count_total >= int(args.min_chunk_count) and min(coverage_ratios or [0.0]) >= 0.95),
            "all_cases_converged": bool(all_converged),
            "rust_backend_used_pass": bool(rust_backend_all),
            "no_collapse_detected": bool(no_collapse_all),
            "drift_guard_pass": bool(max_drift_all <= float(args.max_drift_pct)),
            "section_family_pass": bool(section_family_all),
            "material_model_pass": bool(material_model_all),
            "residual_trace_pass": bool(all(bool(row.get("residual_trace_pass", False)) for row in out_rows)),
            "device_artifacts_consumed_pass": bool(
                all(
                    all(str(chunk.get("response_backend", "")) == "dlpack_zero_copy" for chunk in row.get("chunk_rows_head", []))
                    for row in out_rows
                )
            ),
        }
        contract_pass = bool(all(checks.values()))
        if not checks["source_manifest_pass"]:
            reason_code = "ERR_SOURCE_MANIFEST"
        elif not checks["wind_duration_pass"] or not checks["wind_reversal_pass"]:
            reason_code = "ERR_WIND_INPUT"
        elif not checks["case_count_pass"]:
            reason_code = "ERR_CASES"
        elif not checks["all_cases_converged"] or not checks["no_collapse_detected"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif bool(args.require_rust_backend) and not checks["rust_backend_used_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["section_family_pass"] or not checks["material_model_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["long_series_chunked_pass"] or not checks["drift_guard_pass"] or not checks["device_artifacts_consumed_pass"]:
            reason_code = "ERR_VNV_FAIL"
        else:
            reason_code = "PASS"

        metrics_npz_summary = _write_case_metrics_npz(case_metrics_npz_out, out_rows)
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-wind-time-history-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "artifacts": {
                "report_json": str(out),
                "case_metrics_npz_out": str(case_metrics_npz_out),
            },
            "summary": {
                "selected_case_count": int(len(rows)),
                "duration_hours": float(duration_h),
                "time_step_s": float(dt_full),
                "analysis_stride": int(stride),
                "effective_time_step_s": float(dt),
                "load_reversal_count": int(reversals_full),
                "dominant_frequency_hz": float(dom_freq_hz),
                "preprocess_backend": str(preprocess_backend),
                "total_chunk_count": int(chunk_count_total),
                "coverage_ratio_min": float(min(coverage_ratios or [0.0])),
                "max_drift_ratio_pct_all_cases": float(max_drift_all),
                "residual_pre_settle_top_m_max_abs": float(
                    max((float(row.get("residual_pre_settle_top_m_max_abs", 0.0)) for row in out_rows), default=0.0)
                ),
                "residual_top_m_max_abs": float(
                    max((float(row.get("residual_top_m_max_abs", 0.0)) for row in out_rows), default=0.0)
                ),
                "residual_pre_settle_drift_pct_max_abs": float(
                    max((float(row.get("residual_pre_settle_drift_pct_max_abs", 0.0)) for row in out_rows), default=0.0)
                ),
                "residual_drift_pct_max_abs": float(
                    max((float(row.get("residual_drift_pct_max_abs", 0.0)) for row in out_rows), default=0.0)
                ),
                "residual_settle_case_count": int(sum(1 for row in out_rows if int(row.get("residual_settle_chunk_count", 0)) > 0)),
                "section_family_coverage_min": float(
                    min(
                        float((row.get("section_profile") or {}).get("stiffness_scale_min", 1.0))
                        for row in out_rows
                    )
                    if out_rows
                    else 1.0
                ),
                "material_model_types": sorted({str(row.get("material_model", "")) for row in out_rows}),
                "device_artifact_consumer": "dlpack_zero_copy",
                "device_artifact_case_count": int(
                    sum(
                        1
                        for row in out_rows
                        if all(str(chunk.get("response_backend", "")) == "dlpack_zero_copy" for chunk in row.get("chunk_rows_head", []))
                    )
                ),
                "response_storage": "npz_external+inline_summary",
                "case_metrics_npz_case_count": int(metrics_npz_summary.get("case_count", 0)),
            },
            "rows": out_rows,
            "source_manifest": {
                "path": str(args.source_manifest),
                "real_source": bool(manifest.get("real_source", False)),
                "source_url": str(manifest.get("source_url", "")),
                "sha256": str(manifest.get("sha256", "")),
                "data_path": str(manifest.get("data_path", "")),
            },
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["artifact_archive_manifest"] = _archive([str(out), str(case_metrics_npz_out), str(args.wind_csv), str(args.source_manifest)])
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        log_event(
            logger,
            logging.INFO,
            "wind_gate.completed",
            contract_pass=bool(contract_pass),
            reason_code=reason_code,
            case_count=int(len(rows)),
            duration_hours=float(duration_h),
        )
        print(f"Wrote wind time-history gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, RuntimeError, InputContractError, FileNotFoundError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-wind-time-history-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "wind_gate.invalid_input", error=str(exc))
        print(f"Wrote wind time-history gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
