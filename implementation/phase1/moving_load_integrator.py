#!/usr/bin/env python3
"""Phase-B2 moving load/mass Newmark integrator for track dynamics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Callable

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from track_lf_solver import apply_euler_beam_operator, cg_solve_matrix_free


REASONS = {
    "PASS": "moving-load Newmark integration completed and checks passed",
    "ERR_INVALID_INPUT": "invalid moving-load integration inputs",
    "ERR_SOLVER_DIVERGENCE": "newmark or linear solve diverged",
    "ERR_ENERGY_DIVERGENCE": "energy or residual checks failed",
}

MOVING_LOAD_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "speed_m_s",
        "axle_loads_n",
        "axle_offsets_m",
        "length_m",
        "node_count",
        "dt_s",
        "total_time_s",
        "mass_per_m",
        "ei",
        "winkler_k",
        "pasternak_g",
        "alpha_m",
        "beta_k",
        "max_disp_m",
        "max_residual_ratio",
        "max_energy_balance_error",
        "out",
    ],
    "properties": {
        "speed_m_s": {"type": "number", "exclusiveMinimum": 0.0},
        "axle_loads_n": {"type": "array", "items": {"type": "number"}, "minItems": 1},
        "axle_offsets_m": {"type": "array", "items": {"type": "number"}, "minItems": 1},
        "length_m": {"type": "number", "exclusiveMinimum": 0.0},
        "node_count": {"type": "integer", "minimum": 9},
        "dt_s": {"type": "number", "exclusiveMinimum": 0.0},
        "total_time_s": {"type": "number", "exclusiveMinimum": 0.0},
        "mass_per_m": {"type": "number", "exclusiveMinimum": 0.0},
        "ei": {"type": "number", "exclusiveMinimum": 0.0},
        "winkler_k": {"type": "number", "minimum": 0.0},
        "pasternak_g": {"type": "number", "minimum": 0.0},
        "alpha_m": {"type": "number", "minimum": 0.0},
        "beta_k": {"type": "number", "minimum": 0.0},
        "max_disp_m": {"type": "number", "exclusiveMinimum": 0.0},
        "max_residual_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "max_energy_balance_error": {"type": "number", "exclusiveMinimum": 0.0},
        "dense_cached_solve_max_nodes": {"type": "integer", "minimum": 9},
        "dense_cached_solve_budget_mb": {"type": "number", "exclusiveMinimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


@dataclass
class MovingLoadConfig:
    length_m: float = 60.0
    node_count: int = 161
    support_type: str = "pinned"
    bending_stiffness_n_m2: float = 6.5e6
    winkler_k_n_per_m2: float = 6.0e6
    pasternak_g_n: float = 1.2e6
    mass_per_length_kg_m: float = 400.0
    rayleigh_alpha_m: float = 0.02
    rayleigh_beta_k: float = 3e-5
    dt_s: float = 0.0025
    total_time_s: float = 1.2
    beta_newmark: float = 0.25
    gamma_newmark: float = 0.5
    cg_tol: float = 1e-8
    cg_max_iter: int = 1200
    dense_cached_solve_max_nodes: int = 641
    dense_cached_solve_budget_mb: float = 96.0


def _validate(cfg: MovingLoadConfig) -> None:
    if cfg.length_m <= 0.0:
        raise ValueError("length_m must be > 0")
    if cfg.node_count < 9:
        raise ValueError("node_count must be >= 9")
    if cfg.support_type not in {"pinned", "fixed"}:
        raise ValueError("support_type must be pinned|fixed")
    if cfg.bending_stiffness_n_m2 <= 0.0:
        raise ValueError("bending_stiffness_n_m2 must be > 0")
    if cfg.winkler_k_n_per_m2 < 0.0 or cfg.pasternak_g_n < 0.0:
        raise ValueError("foundation parameters must be >= 0")
    if cfg.mass_per_length_kg_m <= 0.0:
        raise ValueError("mass_per_length_kg_m must be > 0")
    if cfg.dt_s <= 0.0 or cfg.total_time_s <= cfg.dt_s:
        raise ValueError("dt_s must be > 0 and total_time_s > dt_s")
    if cfg.beta_newmark <= 0.0 or cfg.gamma_newmark <= 0.0:
        raise ValueError("newmark beta/gamma must be > 0")
    if cfg.dense_cached_solve_max_nodes < 9 or cfg.dense_cached_solve_budget_mb <= 0.0:
        raise ValueError("dense cached solve policy invalid")


def _stiffness_operator(cfg: MovingLoadConfig, dx: float) -> Callable[[np.ndarray], np.ndarray]:
    def _op(v: np.ndarray) -> np.ndarray:
        return apply_euler_beam_operator(
            v,
            dx=dx,
            bending_stiffness_n_m2=cfg.bending_stiffness_n_m2,
            winkler_k_n_per_m2=cfg.winkler_k_n_per_m2,
            pasternak_g_n=cfg.pasternak_g_n,
            support_type=cfg.support_type,
        )

    return _op


def _moving_axle_q(
    *,
    t_s: float,
    speed_m_s: float,
    axle_loads_n: np.ndarray | list[float],
    axle_offsets_m: np.ndarray | list[float],
    length_m: float,
    node_count: int,
) -> tuple[np.ndarray, int]:
    dx = float(length_m) / float(node_count - 1)
    q = np.zeros(node_count, dtype=np.float64)
    loads = np.asarray(axle_loads_n, dtype=np.float64)
    offsets = np.asarray(axle_offsets_m, dtype=np.float64)
    positions = float(speed_m_s) * float(t_s) - offsets
    active_mask = (positions >= 0.0) & (positions <= float(length_m))
    active_count = int(np.count_nonzero(active_mask))
    if active_count > 0:
        active_positions = positions[active_mask]
        active_loads = loads[active_mask]
        xi = active_positions / dx
        i0 = np.floor(xi).astype(np.int64)
        i1 = np.minimum(node_count - 1, i0 + 1)
        w1 = xi - i0.astype(np.float64)
        w0 = 1.0 - w1
        np.add.at(q, i0, (active_loads * w0) / dx)
        np.add.at(q, i1, (active_loads * w1) / dx)

    q[0] = 0.0
    q[-1] = 0.0
    return q, active_count


def _precompute_load_schedule(
    *,
    steps: int,
    dt_s: float,
    speed_m_s: float,
    axle_loads_n: np.ndarray,
    axle_offsets_m: np.ndarray,
    length_m: float,
    node_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    schedule = np.zeros((int(steps), int(node_count)), dtype=np.float64)
    active_counts = np.zeros(int(steps), dtype=np.int32)
    for step_idx in range(int(steps)):
        q_step, active_count = _moving_axle_q(
            t_s=float(step_idx + 1) * float(dt_s),
            speed_m_s=float(speed_m_s),
            axle_loads_n=axle_loads_n,
            axle_offsets_m=axle_offsets_m,
            length_m=float(length_m),
            node_count=int(node_count),
        )
        schedule[step_idx, :] = q_step
        active_counts[step_idx] = int(active_count)
    return schedule, active_counts


def _assemble_dense_operator_matrix(
    operator: Callable[[np.ndarray], np.ndarray],
    *,
    size: int,
) -> np.ndarray:
    eye = np.eye(int(size), dtype=np.float64)
    cols = [operator(eye[:, i]) for i in range(int(size))]
    return np.column_stack(cols)


def run_moving_load_integration(
    cfg: MovingLoadConfig,
    *,
    speed_m_s: float,
    axle_loads_n: list[float],
    axle_offsets_m: list[float],
    max_disp_m: float,
    max_residual_ratio: float,
    max_energy_balance_error: float,
) -> dict:
    _validate(cfg)
    if len(axle_loads_n) == 0 or len(axle_loads_n) != len(axle_offsets_m):
        raise ValueError("axle_loads_n and axle_offsets_m must have same non-zero length")
    if float(speed_m_s) <= 0.0:
        raise ValueError("speed_m_s must be > 0")

    n = int(cfg.node_count)
    dx = float(cfg.length_m) / float(n - 1)
    dt = float(cfg.dt_s)
    steps = int(round(float(cfg.total_time_s) / dt))

    beta = float(cfg.beta_newmark)
    gamma = float(cfg.gamma_newmark)

    m_line = float(cfg.mass_per_length_kg_m)
    alpha_m = float(cfg.rayleigh_alpha_m)
    beta_k = float(cfg.rayleigh_beta_k)

    k_op = _stiffness_operator(cfg, dx)

    # Effective operator A(u_{n+1}) = m0*u + k0*K(u)
    m0 = (m_line / (beta * dt * dt)) + (gamma / (beta * dt)) * (alpha_m * m_line)
    k0 = 1.0 + (gamma / (beta * dt)) * beta_k

    def c_op(v: np.ndarray) -> np.ndarray:
        return alpha_m * m_line * v + beta_k * k_op(v)

    def a_op(v: np.ndarray) -> np.ndarray:
        out = m0 * v + k0 * k_op(v)
        out[0] = v[0]
        out[-1] = v[-1]
        return out

    dense_cached_solve_estimated_mb = float((3 * n * n * np.dtype(np.float64).itemsize) / (1024.0 * 1024.0))
    enable_dense_cached_solve = bool(
        n <= int(cfg.dense_cached_solve_max_nodes)
        and dense_cached_solve_estimated_mb <= float(cfg.dense_cached_solve_budget_mb)
    )
    a_dense: np.ndarray | None = None
    a_dense_inv: np.ndarray | None = None
    dense_cached_solve_mode = "cg_fallback"
    if enable_dense_cached_solve:
        a_dense = _assemble_dense_operator_matrix(a_op, size=n)
        try:
            a_dense_inv = np.linalg.inv(a_dense)
            if not np.all(np.isfinite(a_dense_inv)):
                a_dense_inv = None
                dense_cached_solve_mode = "cached_dense_solve"
            else:
                dense_cached_solve_mode = "cached_inverse"
        except np.linalg.LinAlgError:
            dense_cached_solve_mode = "cached_dense_solve"

    u = np.zeros(n, dtype=np.float64)
    v = np.zeros(n, dtype=np.float64)
    a = np.zeros(n, dtype=np.float64)
    axle_loads_arr = np.asarray(axle_loads_n, dtype=np.float64)
    axle_offsets_arr = np.asarray(axle_offsets_m, dtype=np.float64)
    load_schedule, active_axle_schedule = _precompute_load_schedule(
        steps=steps,
        dt_s=dt,
        speed_m_s=float(speed_m_s),
        axle_loads_n=axle_loads_arr,
        axle_offsets_m=axle_offsets_arr,
        length_m=cfg.length_m,
        node_count=n,
    )
    t0 = time.perf_counter()

    max_abs_u = 0.0
    max_abs_a = 0.0
    max_abs_residual = 0.0
    input_work = 0.0
    dissipation = 0.0
    last_k_u = np.zeros(n, dtype=np.float64)
    active_axle_counts: list[int] = []
    sparse_contact_step_count = 0

    trace_head: list[dict] = []
    converged_linear = True

    for step in range(1, steps + 1):
        t = float(step) * dt
        f = load_schedule[step - 1]
        active_axle_count = int(active_axle_schedule[step - 1])
        active_axle_counts.append(int(active_axle_count))
        if active_axle_count <= 0:
            sparse_contact_step_count += 1

        u_pred = u + dt * v + (0.5 - beta) * dt * dt * a
        v_pred = v + (1.0 - gamma) * dt * a
        u_pred[0] = 0.0
        u_pred[-1] = 0.0
        c_u_pred = c_op(u_pred)
        c_v_pred = c_op(v_pred)

        rhs = f + (m_line / (beta * dt * dt)) * u_pred + (gamma / (beta * dt)) * c_u_pred - c_v_pred
        rhs[0] = 0.0
        rhs[-1] = 0.0

        if a_dense_inv is not None:
            u_next = a_dense_inv @ rhs
            lin_res = float(np.linalg.norm(a_op(u_next) - rhs, ord=np.inf))
            rhs_inf = max(float(np.linalg.norm(rhs, ord=np.inf)), 1.0)
            lin_rel = lin_res / rhs_inf
            lin_ok = bool(np.isfinite(lin_rel) and lin_rel <= max(float(cfg.cg_tol) * 100.0, 1e-8))
            if (not lin_ok) and (a_dense is not None):
                u_next = np.linalg.solve(a_dense, rhs)
                lin_res = float(np.linalg.norm(a_op(u_next) - rhs, ord=np.inf))
                rhs_inf = max(float(np.linalg.norm(rhs, ord=np.inf)), 1.0)
                lin_rel = lin_res / rhs_inf
                lin_ok = bool(np.isfinite(lin_rel) and lin_rel <= max(float(cfg.cg_tol) * 100.0, 1e-8))
                dense_cached_solve_mode = "cached_dense_solve"
        elif a_dense is not None:
            u_next = np.linalg.solve(a_dense, rhs)
            lin_res = float(np.linalg.norm(a_op(u_next) - rhs, ord=np.inf))
            rhs_inf = max(float(np.linalg.norm(rhs, ord=np.inf)), 1.0)
            lin_rel = lin_res / rhs_inf
            lin_ok = bool(np.isfinite(lin_rel) and lin_rel <= max(float(cfg.cg_tol) * 100.0, 1e-8))
        else:
            u_next, _, lin_res, lin_ok = cg_solve_matrix_free(
                a_op,
                rhs,
                x0=u,
                tol=float(cfg.cg_tol),
                max_iter=int(cfg.cg_max_iter),
            )
        if not lin_ok:
            converged_linear = False

        u_next[0] = 0.0
        u_next[-1] = 0.0

        a_next = (u_next - u_pred) / (beta * dt * dt)
        v_next = v_pred + gamma * dt * a_next
        c_v_next = c_op(v_next)
        k_u_next = k_op(u_next)
        last_k_u = k_u_next

        r = m_line * a_next + c_v_next + k_u_next - f
        r[0] = 0.0
        r[-1] = 0.0

        max_abs_u = max(max_abs_u, float(np.max(np.abs(u_next))))
        max_abs_a = max(max_abs_a, float(np.max(np.abs(a_next))))
        max_abs_residual = max(max_abs_residual, float(np.max(np.abs(r))))

        # Energy/work tracking.
        input_work += float(np.sum(f * v_next) * dx * dt)
        dissipation += float(np.sum(np.maximum(c_v_next * v_next, 0.0)) * dx * dt)

        if step <= 200:
            trace_head.append(
                {
                    "step": int(step),
                    "time_s": t,
                    "active_axle_count": int(active_axle_count),
                    "max_abs_u_m": float(np.max(np.abs(u_next))),
                    "max_abs_a_mps2": float(np.max(np.abs(a_next))),
                    "max_abs_residual": float(np.max(np.abs(r))),
                    "linear_residual": float(lin_res),
                }
            )

        u, v, a = u_next, v_next, a_next

    kinetic = 0.5 * m_line * float(np.sum(v * v) * dx)
    potential = 0.5 * float(np.sum(u * last_k_u) * dx)
    energy_balance_rel = abs((kinetic + potential + dissipation) - input_work) / max(abs(input_work), 1e-9)

    max_force = max(float(max(axle_loads_n)), 1.0)
    residual_ratio = max_abs_residual / max(max_force / max(dx, 1e-9), 1e-9)
    elapsed_seconds = max(time.perf_counter() - t0, 1e-12)
    time_steps_per_second = float(steps) / float(elapsed_seconds)
    milliseconds_per_step = 1000.0 * float(elapsed_seconds) / max(float(steps), 1.0)

    finite_ok = bool(
        np.isfinite(max_abs_u)
        and np.isfinite(max_abs_a)
        and np.isfinite(max_abs_residual)
        and np.isfinite(energy_balance_rel)
    )
    non_divergent = bool(finite_ok and max_abs_u <= float(max_disp_m))
    residual_ok = bool(finite_ok and residual_ratio <= float(max_residual_ratio))
    energy_ok = bool(finite_ok and energy_balance_rel <= float(max_energy_balance_error))

    if (not finite_ok) or (not non_divergent) or (not converged_linear):
        reason_code = "ERR_SOLVER_DIVERGENCE"
    elif (not residual_ok) or (not energy_ok):
        reason_code = "ERR_ENERGY_DIVERGENCE"
    else:
        reason_code = "PASS"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-moving-load-integrator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "config": cfg.__dict__,
            "speed_m_s": float(speed_m_s),
            "axle_loads_n": [float(x) for x in axle_loads_n],
            "axle_offsets_m": [float(x) for x in axle_offsets_m],
            "steps": int(steps),
        },
        "checks": {
            "finite_response": finite_ok,
            "non_divergent_response": non_divergent,
            "linear_solver_converged": converged_linear,
            "equilibrium_residual_pass": residual_ok,
            "energy_balance_pass": energy_ok,
        },
        "metrics": {
            "max_displacement_m": float(max_abs_u),
            "max_acceleration_mps2": float(max_abs_a),
            "max_residual": float(max_abs_residual),
            "residual_ratio": float(residual_ratio),
            "elapsed_seconds": float(elapsed_seconds),
            "time_steps_per_second": float(time_steps_per_second),
            "milliseconds_per_step": float(milliseconds_per_step),
            "step_count": int(steps),
            "input_work_j": float(input_work),
            "dissipated_energy_j": float(dissipation),
            "final_kinetic_j": float(kinetic),
            "final_potential_j": float(potential),
            "energy_balance_relative_error": float(energy_balance_rel),
            "active_axle_count_mean": float(np.mean(active_axle_counts)) if active_axle_counts else 0.0,
            "active_axle_count_max": int(max(active_axle_counts)) if active_axle_counts else 0,
            "sparse_contact_step_count": int(sparse_contact_step_count),
            "sparse_contact_step_ratio": float(sparse_contact_step_count / max(steps, 1)),
            "batched_axle_assembly_enabled": True,
            "batched_track_load_schedule_enabled": True,
            "batched_track_solve_enabled": bool(a_dense is not None),
            "cached_track_solve_inverse_enabled": bool(a_dense_inv is not None),
            "dense_cached_solve_enabled": bool(a_dense is not None),
            "dense_cached_solve_mode": str(dense_cached_solve_mode),
            "dense_cached_solve_max_nodes": int(cfg.dense_cached_solve_max_nodes),
            "dense_cached_solve_budget_mb": float(cfg.dense_cached_solve_budget_mb),
            "dense_cached_solve_estimated_mb": float(dense_cached_solve_estimated_mb),
        },
        "trace_head": trace_head,
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    return payload


def main() -> None:
    logger = get_logger("phase1.moving_load_integrator")
    p = argparse.ArgumentParser()
    p.add_argument("--speed-m-s", type=float, default=22.2)
    p.add_argument("--axle-loads-n", default="85000,85000,85000,85000")
    p.add_argument("--axle-offsets-m", default="0.0,2.5,5.0,7.5")
    p.add_argument("--length-m", type=float, default=60.0)
    p.add_argument("--node-count", type=int, default=161)
    p.add_argument("--dt-s", type=float, default=0.0025)
    p.add_argument("--total-time-s", type=float, default=1.2)
    p.add_argument("--mass-per-m", type=float, default=400.0)
    p.add_argument("--ei", type=float, default=6.5e6)
    p.add_argument("--winkler-k", type=float, default=6.0e6)
    p.add_argument("--pasternak-g", type=float, default=1.2e6)
    p.add_argument("--alpha-m", type=float, default=0.02)
    p.add_argument("--beta-k", type=float, default=3e-5)
    p.add_argument("--max-disp-m", type=float, default=0.08)
    p.add_argument("--max-residual-ratio", type=float, default=0.08)
    p.add_argument("--max-energy-balance-error", type=float, default=0.45)
    p.add_argument("--dense-cached-solve-max-nodes", type=int, default=641)
    p.add_argument("--dense-cached-solve-budget-mb", type=float, default=96.0)
    p.add_argument("--out", default="implementation/phase1/moving_load_integrator_report.json")
    args = p.parse_args()

    try:
        axle_loads = [float(x.strip()) for x in str(args.axle_loads_n).split(",") if x.strip()]
        axle_offsets = [float(x.strip()) for x in str(args.axle_offsets_m).split(",") if x.strip()]
        input_payload = {
            "speed_m_s": float(args.speed_m_s),
            "axle_loads_n": axle_loads,
            "axle_offsets_m": axle_offsets,
            "length_m": float(args.length_m),
            "node_count": int(args.node_count),
            "dt_s": float(args.dt_s),
            "total_time_s": float(args.total_time_s),
            "mass_per_m": float(args.mass_per_m),
            "ei": float(args.ei),
            "winkler_k": float(args.winkler_k),
            "pasternak_g": float(args.pasternak_g),
            "alpha_m": float(args.alpha_m),
            "beta_k": float(args.beta_k),
            "max_disp_m": float(args.max_disp_m),
            "max_residual_ratio": float(args.max_residual_ratio),
            "max_energy_balance_error": float(args.max_energy_balance_error),
            "dense_cached_solve_max_nodes": int(args.dense_cached_solve_max_nodes),
            "dense_cached_solve_budget_mb": float(args.dense_cached_solve_budget_mb),
            "out": str(args.out),
        }
        validate_input_contract(
            input_payload,
            MOVING_LOAD_INPUT_SCHEMA,
            label="phase-b2.moving_load_integrator",
        )
        log_event(logger, logging.INFO, "moving_load.start", inputs=input_payload)

        cfg = MovingLoadConfig(
            length_m=float(args.length_m),
            node_count=int(args.node_count),
            bending_stiffness_n_m2=float(args.ei),
            winkler_k_n_per_m2=float(args.winkler_k),
            pasternak_g_n=float(args.pasternak_g),
            mass_per_length_kg_m=float(args.mass_per_m),
            rayleigh_alpha_m=float(args.alpha_m),
            rayleigh_beta_k=float(args.beta_k),
            dt_s=float(args.dt_s),
            total_time_s=float(args.total_time_s),
            dense_cached_solve_max_nodes=int(args.dense_cached_solve_max_nodes),
            dense_cached_solve_budget_mb=float(args.dense_cached_solve_budget_mb),
        )

        payload = run_moving_load_integration(
            cfg,
            speed_m_s=float(args.speed_m_s),
            axle_loads_n=axle_loads,
            axle_offsets_m=axle_offsets,
            max_disp_m=float(args.max_disp_m),
            max_residual_ratio=float(args.max_residual_ratio),
            max_energy_balance_error=float(args.max_energy_balance_error),
        )
        log_event(
            logger,
            logging.INFO,
            "moving_load.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "moving_load.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-moving-load-integrator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote moving load integrator report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "moving_load.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-moving-load-integrator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote moving load integrator report: {out}")
        raise SystemExit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote moving load integrator report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
