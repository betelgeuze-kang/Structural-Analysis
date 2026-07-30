#!/usr/bin/env python3
"""Dynamic time-history contract with seismic input using Newmark-beta.

The script validates that a Rayleigh-damped SDOF surrogate can process
ground-motion time histories without numerical divergence.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from newton_adaptive_damping import AdaptiveNewtonConfig, solve_with_adaptive_damping
from structural_analysis.dynamics import build_transient_checkpoint_authority


G = 9.80665

REASONS = {
    "PASS": "dynamic time-history integration and energy checks passed",
    "ERR_GM_INPUT": "ground-motion input is missing or invalid",
    "ERR_NEWMARK_STABILITY": "newmark integration diverged or produced non-finite response",
    "ERR_ENERGY_DIVERGENCE": "energy balance or equilibrium residual checks failed",
    "ERR_CHECKPOINT_AUTHORITY": "transient checkpoint source-authentic replay failed",
}


def _generate_default_ground_motion(path: Path, duration_s: float, dt_s: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    steps = max(2, int(round(duration_s / dt_s)) + 1)
    rows = [("time_s", "accel_g")]
    for i in range(steps):
        t = i * dt_s
        ag = (
            0.31 * math.exp(-0.035 * t) * math.sin(2.0 * math.pi * 1.7 * t)
            + 0.18 * math.exp(-0.022 * t) * math.sin(2.0 * math.pi * 4.8 * t + 0.55)
            + 0.07 * math.exp(-0.12 * max(0.0, t - 8.0)) * math.sin(2.0 * math.pi * 8.4 * t)
        )
        ag = max(-0.85, min(0.85, ag))
        rows.append((f"{t:.6f}", f"{ag:.8f}"))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerows(rows)


def _load_ground_motion(path: Path) -> tuple[list[float], list[float]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if len(rows) < 2:
        raise ValueError("ground-motion csv must have at least 2 rows")
    if "time_s" not in rows[0] or "accel_g" not in rows[0]:
        raise ValueError("ground-motion csv must contain time_s, accel_g columns")

    t: list[float] = []
    ag: list[float] = []
    for idx, row in enumerate(rows):
        try:
            ti = float(row["time_s"])
            ai = float(row["accel_g"])
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"non-numeric row at index {idx}: {exc}") from exc
        t.append(ti)
        ag.append(ai)

    dt = t[1] - t[0]
    if dt <= 0.0:
        raise ValueError("time_s must be strictly increasing")
    for i in range(2, len(t)):
        dti = t[i] - t[i - 1]
        if abs(dti - dt) > 1e-6:
            raise ValueError("time_s must have constant dt spacing")
    return t, ag


def _newmark_sdof(
    ag_g: list[float],
    dt: float,
    period_s: float,
    damping_ratio: float,
    mass_kg: float,
    beta: float = 0.25,
    gamma: float = 0.5,
    use_adaptive_newton: bool = True,
    adaptive_cfg: AdaptiveNewtonConfig | None = None,
    nonlinear_stiffness_ratio: float = 0.02,
) -> dict:
    wn = (2.0 * math.pi) / max(period_s, 1e-6)
    k = mass_kg * wn * wn
    c = 2.0 * damping_ratio * mass_kg * wn

    a0 = 1.0 / (beta * dt * dt)
    a1 = gamma / (beta * dt)
    a2 = 1.0 / (beta * dt)
    a3 = (1.0 / (2.0 * beta)) - 1.0
    a4 = (gamma / beta) - 1.0
    a5 = dt * ((gamma / (2.0 * beta)) - 1.0)
    k_eff = k + a0 * mass_kg + a1 * c
    k_nl = float(max(0.0, nonlinear_stiffness_ratio) * k)
    reference_force_n = max(
        mass_kg * max(abs(value) for value in ag_g) * G,
        1.0,
    )

    u = 0.0
    v = 0.0
    a = -ag_g[0] * G
    d_energy = 0.0
    in_work = 0.0

    max_abs_u = 0.0
    max_abs_v = 0.0
    max_abs_a = 0.0
    max_abs_residual = 0.0
    max_base_shear = 0.0
    newton_step_count = 0
    newton_converged_count = 0
    newton_backtracks_total = 0

    trace = []
    for i, ag in enumerate(ag_g):
        p = -mass_kg * ag * G
        if i == 0:
            residual = mass_kg * a + c * v + k * u + k_nl * u * abs(u) - p
        else:
            p_eff = p + mass_kg * (a0 * u + a2 * v + a3 * a) + c * (a1 * u + a4 * v + a5 * a)
            if use_adaptive_newton:
                cfg = adaptive_cfg or AdaptiveNewtonConfig(max_iter=24, tol=1e-10, lambda_init=1e-3)

                def _residual_fn(x: np.ndarray) -> np.ndarray:
                    uu = float(x[0])
                    val = (
                        k_eff * uu + k_nl * uu * abs(uu) - p_eff
                    ) / reference_force_n
                    return np.array([val], dtype=float)

                def _jacobian_fn(x: np.ndarray) -> np.ndarray:
                    uu = float(x[0])
                    jj = (
                        k_eff + 2.0 * k_nl * abs(uu)
                    ) / reference_force_n
                    return np.array([[jj]], dtype=float)

                solved = solve_with_adaptive_damping(np.array([u], dtype=float), _residual_fn, _jacobian_fn, cfg)
                u_next = float(solved["state"][0])
                newton_step_count += 1
                if bool(solved.get("converged", False)):
                    newton_converged_count += 1
                newton_backtracks_total += int(solved.get("line_search_backtracks", 0))
            else:
                if k_nl <= 0.0 or p_eff == 0.0:
                    u_next = p_eff / max(k_eff, 1e-12)
                else:
                    magnitude = (
                        2.0
                        * abs(p_eff)
                        / (
                            k_eff
                            + math.sqrt(
                                k_eff * k_eff
                                + 4.0 * k_nl * abs(p_eff)
                            )
                        )
                    )
                    u_next = math.copysign(magnitude, p_eff)
            a_next = a0 * (u_next - u) - a2 * v - a3 * a
            v_next = v + dt * ((1.0 - gamma) * a + gamma * a_next)
            u, v, a = u_next, v_next, a_next
            residual = (
                mass_kg * a
                + c * v
                + k * u
                + k_nl * u * abs(u)
                - p
            )

        external_work_increment = p * v * dt
        damping_dissipation_increment = c * v * v * dt
        plastic_dissipation_increment = 0.0
        d_energy += damping_dissipation_increment
        in_work += external_work_increment
        e_mech = (
            0.5 * mass_kg * v * v
            + 0.5 * k * u * u
            + k_nl * abs(u) ** 3 / 3.0
        )
        base_shear = abs(k * u + k_nl * u * abs(u) + c * v)

        max_abs_u = max(max_abs_u, abs(u))
        max_abs_v = max(max_abs_v, abs(v))
        max_abs_a = max(max_abs_a, abs(a))
        max_abs_residual = max(max_abs_residual, abs(residual))
        max_base_shear = max(max_base_shear, base_shear)

        trace.append(
            {
                "step": i,
                "force_n": p,
                "u_m": u,
                "v_mps": v,
                "a_mps2": a,
                "residual_n": residual,
                "e_mech_j": e_mech,
                "external_work_increment_j": external_work_increment,
                "damping_dissipation_increment_j": (
                    damping_dissipation_increment
                ),
                "plastic_dissipation_increment_j": (
                    plastic_dissipation_increment
                ),
            }
        )

    final_mech = (
        0.5 * mass_kg * v * v
        + 0.5 * k * u * u
        + k_nl * abs(u) ** 3 / 3.0
    )
    ref_force = reference_force_n
    residual_ratio = max_abs_residual / max(ref_force, 1e-9)
    energy_balance_rel = abs((final_mech + d_energy) - in_work) / max(abs(in_work), 1e-9)

    return {
        "trace": trace,
        "metrics": {
            "max_displacement_m": max_abs_u,
            "max_velocity_mps": max_abs_v,
            "max_acceleration_mps2": max_abs_a,
            "peak_base_shear_n": max_base_shear,
            "equilibrium_residual_max_n": max_abs_residual,
            "equilibrium_residual_ratio": residual_ratio,
            "dissipated_energy_j": d_energy,
            "damping_dissipation_j": d_energy,
            "plastic_dissipation_j": 0.0,
            "input_work_j": in_work,
            "final_mechanical_energy_j": final_mech,
            "energy_balance_relative_error": energy_balance_rel,
            "adaptive_newton_step_count": int(newton_step_count),
            "adaptive_newton_converged_count": int(newton_converged_count),
            "adaptive_newton_backtracks_total": int(newton_backtracks_total),
        },
        "system": {
            "mass_kg": mass_kg,
            "stiffness_n_per_m": k,
            "damping_n_s_per_m": c,
            "period_s": period_s,
            "damping_ratio": damping_ratio,
            "newmark_beta": beta,
            "newmark_gamma": gamma,
            "time_step_s": dt,
            "adaptive_newton_enabled": bool(use_adaptive_newton),
            "nonlinear_stiffness_ratio": float(nonlinear_stiffness_ratio),
            "nonlinear_stiffness_n_per_m2": k_nl,
            "plastic_dissipation_model": "none",
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--auto-generate-input", action="store_true")
    p.add_argument("--duration-s", type=float, default=60.0)
    p.add_argument("--dt-s", type=float, default=0.01)
    p.add_argument("--period-s", type=float, default=0.9)
    p.add_argument("--damping-ratio", type=float, default=0.05)
    p.add_argument("--mass-kg", type=float, default=250_000.0)
    p.add_argument("--use-adaptive-newton", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--adaptive-newton-max-iter", type=int, default=24)
    p.add_argument("--adaptive-newton-tol", type=float, default=1e-10)
    p.add_argument("--nonlinear-stiffness-ratio", type=float, default=0.02)
    p.add_argument("--max-disp-m", type=float, default=1.5)
    p.add_argument("--max-residual-ratio", type=float, default=0.03)
    p.add_argument("--max-energy-balance-error", type=float, default=0.35)
    p.add_argument("--out", default="implementation/phase1/dynamic_time_history_report.json")
    args = p.parse_args()

    gm_path = Path(args.ground_motion_csv)

    try:
        if args.auto_generate_input and not gm_path.exists():
            _generate_default_ground_motion(gm_path, duration_s=float(args.duration_s), dt_s=float(args.dt_s))
        t, ag = _load_ground_motion(gm_path)
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-dynamic-time-history",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_GM_INPUT",
            "reason": f"{REASONS['ERR_GM_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote dynamic time-history report: {out}")
        raise SystemExit(1)

    dt = t[1] - t[0]
    result = _newmark_sdof(
        ag_g=ag,
        dt=dt,
        period_s=float(args.period_s),
        damping_ratio=float(args.damping_ratio),
        mass_kg=float(args.mass_kg),
        use_adaptive_newton=bool(args.use_adaptive_newton),
        adaptive_cfg=AdaptiveNewtonConfig(
            max_iter=int(args.adaptive_newton_max_iter),
            tol=float(args.adaptive_newton_tol),
            lambda_init=1e-3,
        ),
        nonlinear_stiffness_ratio=float(args.nonlinear_stiffness_ratio),
    )
    replay_result = _newmark_sdof(
        ag_g=ag,
        dt=dt,
        period_s=float(args.period_s),
        damping_ratio=float(args.damping_ratio),
        mass_kg=float(args.mass_kg),
        use_adaptive_newton=bool(args.use_adaptive_newton),
        adaptive_cfg=AdaptiveNewtonConfig(
            max_iter=int(args.adaptive_newton_max_iter),
            tol=float(args.adaptive_newton_tol),
            lambda_init=1e-3,
        ),
        nonlinear_stiffness_ratio=float(args.nonlinear_stiffness_ratio),
    )
    initial_state = {
        "displacement_m": 0.0,
        "velocity_mps": 0.0,
        "acceleration_mps2": -float(ag[0]) * G,
    }
    force_history = tuple(
        -float(args.mass_kg) * float(acceleration_g) * G
        for acceleration_g in ag
    )
    checkpoint_authority = build_transient_checkpoint_authority(
        parent_content=gm_path.read_bytes(),
        force_history=force_history,
        initial_state=initial_state,
        source_result=result,
        replay_result=replay_result,
        source_authentic_requested=True,
    )
    metrics = result["metrics"]

    finite_ok = all(math.isfinite(float(v)) for v in metrics.values())
    non_divergent = finite_ok and float(metrics["max_displacement_m"]) <= float(args.max_disp_m)
    residual_ok = finite_ok and float(metrics["equilibrium_residual_ratio"]) <= float(args.max_residual_ratio)
    energy_ok = finite_ok and float(metrics["energy_balance_relative_error"]) <= float(args.max_energy_balance_error)
    stable = bool(non_divergent and residual_ok and energy_ok)
    checkpoint_ok = bool(checkpoint_authority.source_authentic_checkpoint)
    newton_ok = True
    if bool(args.use_adaptive_newton):
        steps = max(1, int(result["metrics"].get("adaptive_newton_step_count", 0)))
        conv = int(result["metrics"].get("adaptive_newton_converged_count", 0))
        newton_ok = bool(conv / steps >= 0.95)
        stable = bool(stable and newton_ok)
    stable = bool(stable and checkpoint_ok)

    if not checkpoint_ok:
        reason_code = "ERR_CHECKPOINT_AUTHORITY"
    elif not finite_ok or not non_divergent or not newton_ok:
        reason_code = "ERR_NEWMARK_STABILITY"
    elif not residual_ok or not energy_ok:
        reason_code = "ERR_ENERGY_DIVERGENCE"
    else:
        reason_code = "PASS"

    report = {
        "schema_version": "1.0",
        "run_id": "phase1-dynamic-time-history",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ground_motion": {
            "path": str(gm_path),
            "sample_count": len(t),
            "dt_s": dt,
            "duration_s": t[-1],
            "max_abs_accel_g": max(abs(x) for x in ag),
            "source": "el_centro_like_synthetic" if "el_centro_like" in gm_path.name else "external_csv",
        },
        "system": result["system"],
        "checks": {
            "finite_response": finite_ok,
            "non_divergent_response": non_divergent,
            "equilibrium_residual_pass": residual_ok,
            "energy_balance_pass": energy_ok,
            "newmark_stability_pass": stable,
            "adaptive_newton_converged_pass": bool(newton_ok),
            "source_authentic_checkpoint_pass": checkpoint_ok,
        },
        "metrics": metrics,
        "trace": result["trace"],
        "trace_head": result["trace"][:400],
        "transient_checkpoint": checkpoint_authority.to_dict(),
        "contract_pass": bool(stable),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote dynamic time-history report: {out}")
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
