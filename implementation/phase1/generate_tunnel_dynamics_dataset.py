#!/usr/bin/env python3
"""Phase-D2: generate tunnel-dynamics residual learning dataset."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random

import numpy as np

from rust_nonlinear_frame_bridge import (
    RustNonlinearNdthaConfig,
    build_story_load_profile,
    solve_nonlinear_frame_ndtha,
)
from solver_truthfulness_runtime import build_runtime_truthfulness, normalize_runtime_policy
from spatiotemporal_dataset_utils import write_jsonl


REASONS = {
    "PASS": "tunnel dynamics dataset generated",
    "ERR_INVALID_INPUT": "invalid generation input",
    "ERR_DATASET_EMPTY": "generated dataset is empty",
    "ERR_RESIDUAL": "generated responses violate residual gate",
    "ERR_RUNTIME_POLICY": "runtime policy requires production-seeded tunnel dataset generation but no production seed path was available",
}


def _runtime_truthfulness(
    *,
    runtime_mode: str,
    production_seed_runtime: dict | None = None,
    total_cases: int = 0,
    seeded_cases: int = 0,
) -> dict:
    payload = build_runtime_truthfulness(
        path_role="top_level_dataset_generation",
        reduced_kind="explicit_reduced_order_tunnel_dynamics_dataset",
        reduced_backend="numpy_explicit_tunnel_dynamics",
        reduced_reason="explicit reduced-order physical tunnel dynamics dataset generation declared without surrogate runtime markers",
        runtime_policy=runtime_mode,
        production_seed_runtime=production_seed_runtime,
        production_seed_label="rust_nonlinear_frame_ndtha_gpu_seed",
        execution_backend="cpu",
    )
    payload["production_seed_case_count"] = int(total_cases)
    payload["production_seed_success_count"] = int(seeded_cases)
    payload["production_seed_all_cases"] = bool(total_cases > 0 and seeded_cases == total_cases)
    return payload


def _maybe_tunnel_seed(
    *,
    node_features: list[list[float]],
    node_count: int,
    seismic_g: list[float],
    pressure_pa: list[float],
    runtime_mode: str,
) -> tuple[np.ndarray | None, dict | None, dict | None]:
    policy = normalize_runtime_policy(runtime_mode)
    if policy == "reduced-order":
        return None, None, None

    story_count = max(6, min(12, int(round(node_count / 12.0))))
    sample_x = np.linspace(0, max(0, node_count - 1), num=story_count, dtype=np.float64)
    node_x = np.arange(node_count, dtype=np.float64)
    mass_nodes = np.asarray([row[0] for row in node_features], dtype=np.float64)
    stiff_nodes = np.asarray([row[1] for row in node_features], dtype=np.float64)
    damp_nodes = np.asarray([row[2] for row in node_features], dtype=np.float64)
    soil_nodes = np.asarray([row[4] for row in node_features], dtype=np.float64)
    story_mass = np.interp(sample_x, node_x, mass_nodes)
    story_k = np.interp(sample_x, node_x, stiff_nodes)
    story_damp = np.interp(sample_x, node_x, damp_nodes)
    story_axial = 190_000.0 + 42_000.0 * np.arange(story_count, dtype=np.float64)
    story_h = np.full(story_count, 3.1, dtype=np.float64)
    story_yield = 0.014 + 0.002 * np.interp(sample_x, node_x, soil_nodes)
    base_force = max(95_000.0, float(max(abs(v) for v in pressure_pa)) * story_count * 220.0)
    try:
        seed_result = solve_nonlinear_frame_ndtha(
            story_k_n_per_m=story_k,
            story_h_m=story_h,
            story_axial_n=story_axial,
            story_yield_drift_m=story_yield,
            story_mass_kg=story_mass,
            story_damping_n_s_per_m=story_damp,
            floor_load_base_n=build_story_load_profile(story_count, base_force, mode="triangular"),
            ag_g=np.asarray(seismic_g, dtype=np.float64),
            cfg=RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=16,
                hardening_ratio=0.18,
                pdelta_factor=1.05,
            ),
            keep_device_artifacts=False,
        )
    except Exception as exc:  # noqa: BLE001
        if policy == "production-seeded":
            raise RuntimeError(REASONS["ERR_RUNTIME_POLICY"]) from exc
        return None, None, None

    seed_runtime = seed_result.get("runtime") if isinstance(seed_result.get("runtime"), dict) else {}
    if not bool(seed_runtime.get("production_kernel_path", False)):
        if policy == "production-seeded":
            raise RuntimeError(REASONS["ERR_RUNTIME_POLICY"])
        return None, seed_runtime, None

    response = seed_result.get("response") if isinstance(seed_result.get("response"), dict) else {}
    final_story_drift_pct = np.asarray(response.get("final_story_drift_pct", []), dtype=np.float64).reshape(-1)
    if final_story_drift_pct.shape[0] != story_count:
        return None, seed_runtime, None
    story_disp = np.cumsum((final_story_drift_pct / 100.0) * story_h)
    seed_profile = np.interp(node_x, sample_x, story_disp)
    seed_metrics = {
        "seed_max_drift_ratio_pct": float(seed_result.get("max_drift_ratio_pct", 0.0) or 0.0),
        "seed_residual_drift_ratio_pct": float(seed_result.get("residual_drift_ratio_pct", 0.0) or 0.0),
        "seed_max_top_displacement_m": float(np.max(np.abs(seed_profile))) if seed_profile.size else 0.0,
    }
    return seed_profile, seed_runtime, seed_metrics


@dataclass(frozen=True)
class TunnelDynConfig:
    seq_len: int
    dt: float
    axial_coupling_k: float


def _split(case_idx: int) -> str:
    bucket = case_idx % 10
    if bucket <= 6:
        return "train"
    if bucket == 7:
        return "val"
    return "test"


def _chain_edges(node_count: int) -> list[list[int]]:
    return [[i, i + 1] for i in range(node_count - 1)]


def _build_features(node_count: int, depth_ref_m: float, rng: random.Random) -> list[list[float]]:
    rows: list[list[float]] = []
    for i in range(node_count):
        h = i / max(1, node_count - 1)
        depth = depth_ref_m * (0.85 + 0.3 * h)
        mass = 7600.0 + 1800.0 * rng.random()
        stiff = (3.8e6 + 1.4e6 * rng.random()) * (1.0 + 0.2 * math.sin(2.0 * math.pi * h))
        damp = 5.8e4 + 2.1e4 * rng.random()
        soil_ratio = 0.8 + 0.5 * rng.random()
        rows.append([mass, stiff, damp, depth / max(depth_ref_m, 1.0), soil_ratio])
    return rows


def _seismic_signal(seq_len: int, dt: float, amp: float, rng: random.Random) -> list[float]:
    phi1 = rng.uniform(0.0, 2.0 * math.pi)
    phi2 = rng.uniform(0.0, 2.0 * math.pi)
    f1 = rng.uniform(0.5, 1.8)
    f2 = rng.uniform(2.1, 4.4)
    out: list[float] = []
    for i in range(seq_len):
        t = i * dt
        g = amp * (
            0.68 * math.exp(-0.035 * t) * math.sin(2.0 * math.pi * f1 * t + phi1)
            + 0.32 * math.exp(-0.06 * t) * math.sin(2.0 * math.pi * f2 * t + phi2)
        )
        out.append(max(-0.95, min(0.95, g)))
    return out


def _pressure_wave(seq_len: int, dt: float, amp_pa: float, speed_factor: float) -> list[float]:
    out: list[float] = []
    period = max(0.55, 1.6 / max(speed_factor, 0.5))
    sigma = 0.065 * period
    for i in range(seq_len):
        t = i * dt
        phase = t % period
        center = 0.38 * period
        wave = amp_pa * math.exp(-0.5 * ((phase - center) / max(sigma, 1e-6)) ** 2)
        out.append(wave)
    return out


def _simulate_case(
    *,
    node_features: list[list[float]],
    seismic_g: list[float],
    pressure_pa: list[float],
    cfg: TunnelDynConfig,
    pressure_decay: float,
    production_seed_profile: np.ndarray | None = None,
) -> tuple[list[list[float]], list[float], dict]:
    n = len(node_features)
    seq_len = int(cfg.seq_len)
    dt = float(cfg.dt)

    m = np.array([max(1200.0, row[0]) for row in node_features], dtype=np.float64)
    k = np.array([max(1e5, row[1]) for row in node_features], dtype=np.float64)
    c = np.array([max(1e3, row[2]) for row in node_features], dtype=np.float64)
    depth = np.array([row[3] for row in node_features], dtype=np.float64)
    soil_ratio = np.array([row[4] for row in node_features], dtype=np.float64)

    if production_seed_profile is not None and production_seed_profile.shape[0] == n:
        u = 0.04 * np.asarray(production_seed_profile, dtype=np.float64).copy()
    else:
        u = np.zeros(n, dtype=np.float64)
    v = np.zeros(n, dtype=np.float64)
    a = np.zeros(n, dtype=np.float64)

    response: list[list[float]] = []
    gm: list[float] = []

    max_disp = 0.0
    max_residual = 0.0
    max_ext = 0.0

    idx = np.arange(n, dtype=np.float64)
    end_weight = np.exp(-pressure_decay * idx / max(1.0, n - 1))

    for t in range(seq_len):
        ag = float(seismic_g[t]) * 9.80665
        p = float(pressure_pa[t])

        seismic_force = -m * ag * (0.82 + 0.22 * depth)
        pressure_force = 1.5e-3 * p * end_weight * soil_ratio
        ext = seismic_force + pressure_force

        for i in range(n):
            coupling = 0.0
            if i > 0:
                coupling += u[i] - u[i - 1]
            if i + 1 < n:
                coupling += u[i] - u[i + 1]
            coupling *= float(cfg.axial_coupling_k)

            int_force = c[i] * v[i] + k[i] * u[i] + coupling
            a[i] = (ext[i] - int_force) / m[i]

        v += dt * a
        u += dt * v

        for i in range(n):
            coupling = 0.0
            if i > 0:
                coupling += u[i] - u[i - 1]
            if i + 1 < n:
                coupling += u[i] - u[i + 1]
            coupling *= float(cfg.axial_coupling_k)
            int_force = c[i] * v[i] + k[i] * u[i] + coupling
            r = m[i] * a[i] + int_force - ext[i]
            max_residual = max(max_residual, abs(float(r)))

        max_disp = max(max_disp, float(np.max(np.abs(u))))
        max_ext = max(max_ext, float(np.max(np.abs(ext))))
        response.append([float(x) for x in u.tolist()])
        gm.append(float(np.mean(seismic_force) / max(1e-6, np.max(np.abs(seismic_force)))))

    strain_max = 0.0
    if n >= 2:
        du = np.diff(np.array(response[-1], dtype=np.float64))
        strain_max = float(np.max(np.abs(du)))

    eq_ratio = max_residual / max(max_ext, 1.0)
    metrics = {
        "max_disp_m": float(max_disp),
        "max_longitudinal_strain": float(strain_max),
        "equilibrium_residual": float(eq_ratio),
        "max_external_force": float(max_ext),
    }
    return response, gm, metrics


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        v = str(row.get(key, "unknown"))
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", type=int, default=220)
    p.add_argument("--seq-len", type=int, default=120)
    p.add_argument("--dt", type=float, default=0.01)
    p.add_argument("--node-min", type=int, default=42)
    p.add_argument("--node-max", type=int, default=140)
    p.add_argument("--axial-coupling-k", type=float, default=2.9e5)
    p.add_argument("--max-eq-residual", type=float, default=0.45)
    p.add_argument("--out-dataset", default="implementation/phase1/spatiotemporal_data/tunnel_dynamic_cases.jsonl")
    p.add_argument("--out", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    p.add_argument("--seed", type=int, default=31)
    p.add_argument("--runtime-mode", choices=["auto", "reduced-order", "production-seeded"], default="auto")
    args = p.parse_args()

    normalized_runtime_mode = normalize_runtime_policy(args.runtime_mode)

    if (
        int(args.cases) < 12
        or int(args.seq_len) < 32
        or float(args.dt) <= 0.0
        or int(args.node_min) < 16
        or int(args.node_max) < int(args.node_min)
        or float(args.axial_coupling_k) <= 0.0
    ):
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-tunnel-dynamics-dataset",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": _runtime_truthfulness(runtime_mode=normalized_runtime_mode),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": REASONS["ERR_INVALID_INPUT"],
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    rng = random.Random(int(args.seed))
    cfg = TunnelDynConfig(seq_len=int(args.seq_len), dt=float(args.dt), axial_coupling_k=float(args.axial_coupling_k))

    rows: list[dict] = []
    residual_ratios: list[float] = []
    max_disps: list[float] = []
    production_seed_success_count = 0
    production_seed_runtime: dict | None = None

    for i in range(int(args.cases)):
        node_count = rng.randint(int(args.node_min), int(args.node_max))
        depth_ref = rng.uniform(14.0, 42.0)
        seismic_amp = rng.uniform(0.08, 0.36)
        pressure_amp = rng.uniform(420.0, 1680.0)
        speed_factor = rng.uniform(0.7, 1.5)
        pressure_decay = rng.uniform(0.35, 1.15)

        features = _build_features(node_count=node_count, depth_ref_m=depth_ref, rng=rng)
        seismic = _seismic_signal(int(cfg.seq_len), float(cfg.dt), seismic_amp, rng)
        pressure = _pressure_wave(int(cfg.seq_len), float(cfg.dt), pressure_amp, speed_factor)
        try:
            seed_profile, seed_runtime, seed_metrics = _maybe_tunnel_seed(
                node_features=features,
                node_count=node_count,
                seismic_g=seismic,
                pressure_pa=pressure,
                runtime_mode=normalized_runtime_mode,
            )
        except RuntimeError:
            payload = {
                "schema_version": "1.0",
                "run_id": "phase1-generate-tunnel-dynamics-dataset",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "runtime_truthfulness": _runtime_truthfulness(
                    runtime_mode=normalized_runtime_mode,
                    production_seed_runtime=production_seed_runtime,
                    total_cases=int(args.cases),
                    seeded_cases=production_seed_success_count,
                ),
                "contract_pass": False,
                "reason_code": "ERR_RUNTIME_POLICY",
                "reason": REASONS["ERR_RUNTIME_POLICY"],
            }
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            raise SystemExit(1)
        if seed_profile is not None:
            production_seed_success_count += 1
            production_seed_runtime = seed_runtime

        response, gm, metrics = _simulate_case(
            node_features=features,
            seismic_g=seismic,
            pressure_pa=pressure,
            cfg=cfg,
            pressure_decay=pressure_decay,
            production_seed_profile=seed_profile,
        )
        residual_ratios.append(float(metrics["equilibrium_residual"]))
        max_disps.append(float(metrics["max_disp_m"]))

        rows.append(
            {
                "case_id": f"TUN-{i:06d}",
                "split": _split(i),
                "domain": "tunnel",
                "topology_type": "tunnel-ring-chain",
                "material_type": "rc",
                "ood_tag": "ood_hazard" if seismic_amp > 0.28 else "in_distribution",
                "torsion_sensitive": False,
                "seq_len": int(cfg.seq_len),
                "dt": float(cfg.dt),
                "node_count": int(node_count),
                "node_features": features,
                "edges": _chain_edges(node_count),
                "faces": [],
                "ground_motion_g": gm,
                "response_u": response,
                "physics_params": {
                    "axial_coupling_k": float(cfg.axial_coupling_k),
                    "pressure_decay": float(pressure_decay),
                    "simulator": "tunnel_explicit_v1",
                    "runtime_mode": normalized_runtime_mode,
                },
                "metrics": metrics,
                "seismic_input_g": seismic,
                "pressure_wave_pa": pressure,
                "production_seed": seed_metrics or {},
            }
        )

    if not rows:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-tunnel-dynamics-dataset",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": _runtime_truthfulness(
                runtime_mode=normalized_runtime_mode,
                production_seed_runtime=production_seed_runtime,
                total_cases=int(args.cases),
                seeded_cases=production_seed_success_count,
            ),
            "contract_pass": False,
            "reason_code": "ERR_DATASET_EMPTY",
            "reason": REASONS["ERR_DATASET_EMPTY"],
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    dataset_path = Path(args.out_dataset)
    write_jsonl(dataset_path, rows)

    split_counts = _count_by(rows, "split")
    max_eq = max(residual_ratios) if residual_ratios else 0.0
    eq_pass = bool(max_eq <= float(args.max_eq_residual))
    split_has_val_test = bool(split_counts.get("val", 0) > 0 and split_counts.get("test", 0) > 0)

    checks = {
        "dataset_nonempty": len(rows) > 0,
        "split_has_val_test": split_has_val_test,
        "finite_response": all(math.isfinite(v) for v in residual_ratios + max_disps),
        "equilibrium_residual_pass": eq_pass,
    }
    contract_pass = all(checks.values())
    if not eq_pass:
        reason_code = "ERR_RESIDUAL"
    else:
        reason_code = "PASS" if contract_pass else "ERR_DATASET_EMPTY"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-generate-tunnel-dynamics-dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_truthfulness": _runtime_truthfulness(
            runtime_mode=normalized_runtime_mode,
            production_seed_runtime=production_seed_runtime,
            total_cases=int(args.cases),
            seeded_cases=production_seed_success_count,
        ),
        "inputs": {
            "cases": int(args.cases),
            "seq_len": int(args.seq_len),
            "dt": float(args.dt),
            "node_min": int(args.node_min),
            "node_max": int(args.node_max),
            "axial_coupling_k": float(args.axial_coupling_k),
            "max_eq_residual": float(args.max_eq_residual),
            "seed": int(args.seed),
            "runtime_mode": normalized_runtime_mode,
        },
        "outputs": {
            "dataset_path": str(dataset_path),
            "case_count": len(rows),
            "split_counts": split_counts,
        },
        "checks": checks,
        "metrics": {
            "max_equilibrium_residual": float(max_eq),
            "mean_equilibrium_residual": float(sum(residual_ratios) / max(1, len(residual_ratios))),
            "max_displacement_m": float(max(max_disps) if max_disps else 0.0),
            "mean_displacement_m": float(sum(max_disps) / max(1, len(max_disps))),
        },
        "sample_case_ids": [rows[i]["case_id"] for i in range(min(6, len(rows)))],
        "production_seed_success_count": int(production_seed_success_count),
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS.get(reason_code, REASONS["ERR_DATASET_EMPTY"]),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote tunnel dynamics dataset: {dataset_path}")
    print(f"Wrote tunnel dataset report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
