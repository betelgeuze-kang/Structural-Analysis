#!/usr/bin/env python3
"""Phase-D1: generate track-dynamics residual learning dataset."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random

import numpy as np

from rust_track_lf_bridge import RustTrackConfig, solve_track_point_load
from solver_truthfulness_runtime import build_runtime_truthfulness, normalize_runtime_policy
from spatiotemporal_dataset_utils import write_jsonl


REASONS = {
    "PASS": "track dynamics dataset generated",
    "ERR_INVALID_INPUT": "invalid generation input",
    "ERR_DATASET_EMPTY": "generated dataset is empty",
    "ERR_RESIDUAL": "generated responses violate residual gate",
    "ERR_RUNTIME_POLICY": "runtime policy requires production-seeded track dataset generation but no production seed path was available",
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
        reduced_kind="explicit_reduced_order_track_dynamics_dataset",
        reduced_backend="numpy_explicit_track_dynamics",
        reduced_reason="explicit reduced-order physical track dynamics dataset generation declared without surrogate runtime markers",
        runtime_policy=runtime_mode,
        production_seed_runtime=production_seed_runtime,
        production_seed_label="rust_track_lf_gpu_seed",
        execution_backend="cpu",
    )
    payload["production_seed_case_count"] = int(total_cases)
    payload["production_seed_success_count"] = int(seeded_cases)
    payload["production_seed_all_cases"] = bool(total_cases > 0 and seeded_cases == total_cases)
    return payload


def _maybe_track_seed(
    *,
    node_features: list[list[float]],
    node_count: int,
    length_m: float,
    load_amp: float,
    runtime_mode: str,
) -> tuple[np.ndarray | None, dict | None, dict | None]:
    policy = normalize_runtime_policy(runtime_mode)
    if policy == "reduced-order":
        return None, None, None

    mean_stiff = float(sum(row[1] for row in node_features) / max(1, len(node_features)))
    bend = max(8.5e6, mean_stiff * (length_m / max(node_count, 1)) ** 2 * 0.9)
    shear = max(4.0e5, mean_stiff * 0.08)
    point_position_m = 0.5 * float(length_m)
    try:
        seed_result = solve_track_point_load(
            RustTrackConfig(
                length_m=float(length_m),
                node_count=int(node_count),
                support_type="pinned",
                theory="timoshenko",
                bending_stiffness_n_m2=float(bend),
                shear_stiffness_n=float(shear),
                winkler_k_n_per_m2=2.6e7,
                pasternak_g_n=4.8e5,
                tolerance=1e-8,
                cg_max_iter=160,
                point_force_n=float(load_amp),
                point_position_m=float(point_position_m),
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

    displacement = np.asarray(seed_result.get("displacement_m", []), dtype=np.float64).reshape(-1)
    if displacement.shape[0] != int(node_count):
        return None, seed_runtime, None
    seed_metrics = {
        "seed_max_abs_displacement_m": float(seed_result.get("max_abs_displacement_m", 0.0) or 0.0),
        "seed_mid_displacement_m": float(seed_result.get("mid_displacement_m", 0.0) or 0.0),
    }
    return displacement, seed_runtime, seed_metrics


@dataclass(frozen=True)
class TrackDynConfig:
    seq_len: int
    dt: float
    coupling_k: float


def _split(case_idx: int) -> str:
    bucket = case_idx % 10
    if bucket <= 6:
        return "train"
    if bucket == 7:
        return "val"
    return "test"


def _chain_edges(node_count: int) -> list[list[int]]:
    return [[i, i + 1] for i in range(node_count - 1)]


def _build_features(node_count: int, irregularity_amp: float, rng: random.Random) -> list[list[float]]:
    rows: list[list[float]] = []
    for i in range(node_count):
        h = i / max(1, node_count - 1)
        mass = 320.0 + 90.0 * rng.random()
        stiff = (4.8e4 + 2.2e4 * rng.random()) * (1.0 + 0.35 * (h - 0.5) ** 2)
        damp = 155.0 + 70.0 * rng.random()
        irr = irregularity_amp * (0.6 + 0.8 * rng.random())
        rows.append([mass, stiff, damp, h, irr])
    return rows


def _moving_position_index(seq_len: int, dt: float, node_count: int, length_m: float, speed_m_s: float) -> list[int]:
    dx = length_m / max(1, node_count - 1)
    out: list[int] = []
    x0 = -0.08 * length_m
    for t in range(seq_len):
        x = x0 + speed_m_s * (t * dt)
        idx = int(round(max(0.0, min(length_m, x)) / max(dx, 1e-9)))
        idx = max(0, min(node_count - 1, idx))
        out.append(idx)
    return out


def _simulate_case(
    *,
    node_features: list[list[float]],
    positions: list[int],
    cfg: TrackDynConfig,
    load_amp: float,
    load_sigma_node: float,
    forcing_freq_hz: float,
    production_seed_profile: np.ndarray | None = None,
) -> tuple[list[list[float]], list[float], dict]:
    n = len(node_features)
    seq_len = int(cfg.seq_len)
    dt = float(cfg.dt)

    m = np.array([max(120.0, row[0]) for row in node_features], dtype=np.float64)
    k = np.array([max(1e4, row[1]) for row in node_features], dtype=np.float64)
    c = np.array([max(10.0, row[2]) for row in node_features], dtype=np.float64)
    irr = np.array([row[4] for row in node_features], dtype=np.float64)

    if production_seed_profile is not None and production_seed_profile.shape[0] == n:
        # Use production-kernel static shape as a light initial-condition seed,
        # not as a dominant displacement field for the dynamic rollout.
        u = 0.002 * np.asarray(production_seed_profile, dtype=np.float64).copy()
    else:
        u = np.zeros(n, dtype=np.float64)
    v = np.zeros(n, dtype=np.float64)
    a = np.zeros(n, dtype=np.float64)

    response: list[list[float]] = []
    gm: list[float] = []

    max_disp = 0.0
    max_residual = 0.0
    max_ext = 0.0

    nodes = np.arange(n, dtype=np.float64)

    for t in range(seq_len):
        pos = float(positions[t])
        phase = 2.0 * math.pi * forcing_freq_hz * float(t * dt)
        envelope = 0.5 + 0.5 * math.sin(phase)
        load_shape = np.exp(-0.5 * ((nodes - pos) / max(load_sigma_node, 1e-6)) ** 2)
        ext = (load_amp * envelope) * load_shape + 1800.0 * irr * math.sin(0.8 * phase)

        for i in range(n):
            coupling = 0.0
            if i > 0:
                coupling += u[i] - u[i - 1]
            if i + 1 < n:
                coupling += u[i] - u[i + 1]
            coupling *= float(cfg.coupling_k)

            int_force = c[i] * v[i] + k[i] * u[i] + coupling
            a[i] = (ext[i] - int_force) / m[i]

        v += dt * a
        u += dt * v

        # Re-compute residual on updated state.
        for i in range(n):
            coupling = 0.0
            if i > 0:
                coupling += u[i] - u[i - 1]
            if i + 1 < n:
                coupling += u[i] - u[i + 1]
            coupling *= float(cfg.coupling_k)
            int_force = c[i] * v[i] + k[i] * u[i] + coupling
            r = m[i] * a[i] + int_force - ext[i]
            max_residual = max(max_residual, abs(float(r)))

        max_disp = max(max_disp, float(np.max(np.abs(u))))
        max_ext = max(max_ext, float(np.max(np.abs(ext))))
        response.append([float(x) for x in u.tolist()])
        gm.append(float(np.mean(ext) / max(1e-6, load_amp)))

    eq_ratio = max_residual / max(max_ext, 1.0)
    metrics = {
        "max_disp_m": float(max_disp),
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
    p.add_argument("--cases", type=int, default=240)
    p.add_argument("--seq-len", type=int, default=120)
    p.add_argument("--dt", type=float, default=0.01)
    p.add_argument("--node-min", type=int, default=48)
    p.add_argument("--node-max", type=int, default=112)
    p.add_argument("--coupling-k", type=float, default=2400.0)
    p.add_argument("--max-eq-residual", type=float, default=0.45)
    p.add_argument("--out-dataset", default="implementation/phase1/spatiotemporal_data/track_dynamic_cases.jsonl")
    p.add_argument("--out", default="implementation/phase1/track_dynamics_dataset_report.json")
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--runtime-mode", choices=["auto", "reduced-order", "production-seeded"], default="auto")
    args = p.parse_args()

    normalized_runtime_mode = normalize_runtime_policy(args.runtime_mode)

    if (
        int(args.cases) < 12
        or int(args.seq_len) < 32
        or float(args.dt) <= 0.0
        or int(args.node_min) < 16
        or int(args.node_max) < int(args.node_min)
        or float(args.coupling_k) <= 0.0
    ):
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-track-dynamics-dataset",
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
    cfg = TrackDynConfig(seq_len=int(args.seq_len), dt=float(args.dt), coupling_k=float(args.coupling_k))

    rows: list[dict] = []
    residual_ratios: list[float] = []
    max_disps: list[float] = []
    production_seed_success_count = 0
    production_seed_runtime: dict | None = None

    for i in range(int(args.cases)):
        node_count = rng.randint(int(args.node_min), int(args.node_max))
        length_m = rng.uniform(55.0, 120.0)
        speed_m_s = rng.uniform(14.0, 38.0)
        irregularity_amp = rng.uniform(1.0e-6, 6.0e-6)
        load_amp = rng.uniform(2.8e4, 6.6e4)
        load_sigma = rng.uniform(1.8, 4.2)
        forcing_freq = rng.uniform(0.8, 3.0)

        features = _build_features(node_count=node_count, irregularity_amp=irregularity_amp, rng=rng)
        try:
            seed_profile, seed_runtime, seed_metrics = _maybe_track_seed(
                node_features=features,
                node_count=node_count,
                length_m=length_m,
                load_amp=load_amp,
                runtime_mode=normalized_runtime_mode,
            )
        except RuntimeError:
            payload = {
                "schema_version": "1.0",
                "run_id": "phase1-generate-track-dynamics-dataset",
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
        positions = _moving_position_index(
            seq_len=int(cfg.seq_len),
            dt=float(cfg.dt),
            node_count=node_count,
            length_m=length_m,
            speed_m_s=speed_m_s,
        )
        response, gm, metrics = _simulate_case(
            node_features=features,
            positions=positions,
            cfg=cfg,
            load_amp=load_amp,
            load_sigma_node=load_sigma,
            forcing_freq_hz=forcing_freq,
            production_seed_profile=seed_profile,
        )
        residual_ratios.append(float(metrics["equilibrium_residual"]))
        max_disps.append(float(metrics["max_disp_m"]))

        rows.append(
            {
                "case_id": f"TRK-{i:06d}",
                "split": _split(i),
                "domain": "track",
                "topology_type": "track-beam",
                "material_type": "steel",
                "ood_tag": "ood_hazard" if speed_m_s > 32.0 else "in_distribution",
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
                    "coupling_k": float(cfg.coupling_k),
                    "load_amp": float(load_amp),
                    "load_sigma_node": float(load_sigma),
                    "forcing_freq_hz": float(forcing_freq),
                    "simulator": "track_explicit_v1",
                    "runtime_mode": normalized_runtime_mode,
                },
                "moving_load_position_idx": positions,
                "moving_load_speed_m_s": float(speed_m_s),
                "metrics": metrics,
                "production_seed": seed_metrics or {},
            }
        )

    if not rows:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-generate-track-dynamics-dataset",
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
        "run_id": "phase1-generate-track-dynamics-dataset",
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
            "coupling_k": float(args.coupling_k),
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
    print(f"Wrote track dynamics dataset: {dataset_path}")
    print(f"Wrote track dataset report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
