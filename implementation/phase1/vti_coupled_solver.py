#!/usr/bin/env python3
"""Phase-B3 vehicle-track interaction coupled solver (Picard/Newton-style loop)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import time

import numpy as np

from newton_adaptive_damping import AdaptiveNewtonConfig, solve_with_adaptive_damping
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from track_irregularity_generator import IrregularityConfig, generate_profile, sample_profile_at
from track_lf_solver import TrackLFConfig, solve_track_static


REASONS = {
    "PASS": "vti coupled solver converged under configured coupling criteria",
    "ERR_INVALID_INPUT": "invalid coupled solver input",
    "ERR_COUPLING_DIVERGENCE": "picard/newton-style coupling did not converge",
    "ERR_DYNAMIC_DIVERGENCE": "vehicle dynamics diverged",
}

VTI_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "length_m",
        "node_count",
        "speed_m_s",
        "dt_s",
        "total_time_s",
        "axle_offsets_m",
        "axle_mass_kg",
        "carbody_mass_kg",
        "suspension_k",
        "suspension_c",
        "hertz_k",
        "coupling_max_iter",
        "coupling_tol",
        "relaxation",
        "max_disp_limit",
        "irregularity_class",
        "irregularity_seed",
        "use_adaptive_newton",
        "adaptive_newton_max_iter",
        "adaptive_newton_tol",
        "out",
    ],
    "properties": {
        "length_m": {"type": "number", "exclusiveMinimum": 0.0},
        "node_count": {"type": "integer", "minimum": 9},
        "speed_m_s": {"type": "number", "exclusiveMinimum": 0.0},
        "dt_s": {"type": "number", "exclusiveMinimum": 0.0},
        "total_time_s": {"type": "number", "exclusiveMinimum": 0.0},
        "axle_offsets_m": {"type": "array", "items": {"type": "number"}, "minItems": 2},
        "axle_mass_kg": {"type": "number", "exclusiveMinimum": 0.0},
        "carbody_mass_kg": {"type": "number", "exclusiveMinimum": 0.0},
        "suspension_k": {"type": "number", "exclusiveMinimum": 0.0},
        "suspension_c": {"type": "number", "minimum": 0.0},
        "hertz_k": {"type": "number", "exclusiveMinimum": 0.0},
        "coupling_max_iter": {"type": "integer", "minimum": 1},
        "coupling_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "relaxation": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "max_disp_limit": {"type": "number", "exclusiveMinimum": 0.0},
        "irregularity_class": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "irregularity_seed": {"type": "integer"},
        "use_adaptive_newton": {"type": "boolean"},
        "adaptive_newton_max_iter": {"type": "integer", "minimum": 1},
        "adaptive_newton_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "adaptive_newton_conv_ratio_min": {
            "type": "number",
            "exclusiveMinimum": 0.0,
            "maximum": 1.0,
        },
        "contact_window_margin_m": {"type": "number", "minimum": 0.0},
        "contact_window_release_gap_m": {"type": "number"},
        "contact_window_force_floor_n": {"type": "number", "minimum": 0.0},
        "retained_force_min_force_n": {"type": "number", "minimum": 0.0},
        "retained_force_gap_tol_m": {"type": "number", "minimum": 0.0},
        "retained_force_track_disp_tol_m": {"type": "number", "minimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


@dataclass
class VTICoupledConfig:
    length_m: float = 60.0
    node_count: int = 161
    speed_m_s: float = 22.2
    dt_s: float = 0.005
    total_time_s: float = 0.8
    axle_offsets_m: tuple[float, ...] = (6.0, 8.5, 11.0, 13.5)
    axle_mass_kg: float = 1500.0
    carbody_mass_kg: float = 25000.0
    suspension_k_n_m: float = 7.5e5
    suspension_c_n_s_m: float = 1.5e4
    hertz_k_n_m_3_2: float = 1.05e9
    coupling_max_iter: int = 12
    coupling_tol: float = 2e-3
    relaxation: float = 0.55
    max_disp_limit_m: float = 0.12
    use_adaptive_newton: bool = True
    adaptive_newton_max_iter: int = 18
    adaptive_newton_tol: float = 1e-8
    adaptive_newton_lambda_init: float = 1e-3
    adaptive_newton_conv_ratio_min: float = 0.98
    contact_compliance_floor_m_per_n: float = 1e-11
    contact_compliance_cap_m_per_n: float = 5e-7
    contact_window_margin_m: float = 0.75
    contact_window_release_gap_m: float = -5e-4
    contact_window_force_floor_n: float = 250.0
    retained_force_min_force_n: float = 25.0
    retained_force_gap_tol_m: float = 1.0e-3
    retained_force_track_disp_tol_m: float = 1.0e-3



def _validate(cfg: VTICoupledConfig) -> None:
    if cfg.length_m <= 0.0 or cfg.node_count < 9:
        raise ValueError("length_m > 0 and node_count >= 9 required")
    if cfg.speed_m_s <= 0.0:
        raise ValueError("speed_m_s must be > 0")
    if cfg.dt_s <= 0.0 or cfg.total_time_s <= cfg.dt_s:
        raise ValueError("dt_s must be > 0 and total_time_s > dt_s")
    if len(cfg.axle_offsets_m) < 2:
        raise ValueError("at least two axles are required")
    if cfg.axle_mass_kg <= 0.0 or cfg.carbody_mass_kg <= 0.0:
        raise ValueError("masses must be > 0")
    if cfg.suspension_k_n_m <= 0.0 or cfg.suspension_c_n_s_m < 0.0:
        raise ValueError("suspension parameters invalid")
    if cfg.hertz_k_n_m_3_2 <= 0.0:
        raise ValueError("hertz stiffness must be > 0")
    if cfg.coupling_max_iter < 1 or cfg.coupling_tol <= 0.0:
        raise ValueError("coupling iterations/tolerance invalid")
    if not (0.0 < cfg.relaxation <= 1.0):
        raise ValueError("relaxation must be in (0, 1]")
    if cfg.adaptive_newton_max_iter < 1 or cfg.adaptive_newton_tol <= 0.0:
        raise ValueError("adaptive newton iterations/tolerance invalid")
    if not (0.0 < cfg.adaptive_newton_conv_ratio_min <= 1.0):
        raise ValueError("adaptive_newton_conv_ratio_min must be in (0, 1]")
    if cfg.contact_compliance_floor_m_per_n <= 0.0 or cfg.contact_compliance_cap_m_per_n <= cfg.contact_compliance_floor_m_per_n:
        raise ValueError("contact compliance bounds invalid")
    if cfg.contact_window_margin_m < 0.0 or cfg.contact_window_force_floor_n < 0.0 or cfg.retained_force_min_force_n < 0.0:
        raise ValueError("contact window margin/force floor invalid")
    if cfg.retained_force_gap_tol_m < 0.0 or cfg.retained_force_track_disp_tol_m < 0.0:
        raise ValueError("retained-force warm start tolerances invalid")



def _distribute_point_forces_q(
    *,
    node_count: int,
    length_m: float,
    positions_m: list[float],
    forces_n: np.ndarray,
) -> np.ndarray:
    dx = float(length_m) / float(node_count - 1)
    q = np.zeros(node_count, dtype=np.float64)
    for x, f in zip(positions_m, forces_n):
        if x < 0.0 or x > float(length_m):
            continue
        xi = x / dx
        i0 = int(math.floor(xi))
        i1 = min(node_count - 1, i0 + 1)
        w1 = xi - float(i0)
        w0 = 1.0 - w1
        q[i0] += (float(f) * w0) / dx
        q[i1] += (float(f) * w1) / dx
    q[0] = 0.0
    q[-1] = 0.0
    return q


def _interp_from_grid(x_grid: np.ndarray, values: np.ndarray, x_query: float) -> float:
    if x_query <= float(x_grid[0]):
        return float(values[0])
    if x_query >= float(x_grid[-1]):
        return float(values[-1])
    return float(np.interp(x_query, x_grid, values))


def _solve_contact_force_adaptive(
    *,
    force_guess_n: float,
    force_ref_n: float,
    axle_disp_m: float,
    track_disp_m: float,
    irregularity_m: float,
    hertz_k_n_m_3_2: float,
    compliance_m_per_n: float,
    cfg: VTICoupledConfig,
) -> tuple[float, dict]:
    x0 = np.array([max(0.0, float(force_guess_n))], dtype=np.float64)
    k_h = float(hertz_k_n_m_3_2)
    f_ref = float(max(0.0, force_ref_n))
    base_gap = float(axle_disp_m - irregularity_m - track_disp_m)
    compliance = float(max(cfg.contact_compliance_floor_m_per_n, min(cfg.contact_compliance_cap_m_per_n, compliance_m_per_n)))

    def _residual(x: np.ndarray) -> np.ndarray:
        f_raw = float(x[0])
        if f_raw <= 0.0:
            return np.array([f_raw], dtype=np.float64)
        gap = base_gap - compliance * (f_raw - f_ref)
        if gap <= 0.0:
            return np.array([f_raw], dtype=np.float64)
        target = k_h * (gap ** 1.5)
        return np.array([f_raw - target], dtype=np.float64)

    def _jacobian(x: np.ndarray) -> np.ndarray:
        f_raw = float(x[0])
        if f_raw <= 0.0:
            return np.array([[1.0]], dtype=np.float64)
        gap = base_gap - compliance * (f_raw - f_ref)
        if gap <= 0.0:
            return np.array([[1.0]], dtype=np.float64)
        dtarget_df = k_h * 1.5 * math.sqrt(gap) * (-compliance)
        return np.array([[1.0 - dtarget_df]], dtype=np.float64)

    solved = solve_with_adaptive_damping(
        x0,
        _residual,
        _jacobian,
        AdaptiveNewtonConfig(
            max_iter=int(cfg.adaptive_newton_max_iter),
            tol=float(cfg.adaptive_newton_tol),
            lambda_init=float(cfg.adaptive_newton_lambda_init),
        ),
    )
    return max(0.0, float(solved["state"][0])), solved


def run_vti_coupled_solver(cfg: VTICoupledConfig, *, irregularity_class: str, irregularity_seed: int) -> dict:
    _validate(cfg)
    t0 = time.perf_counter()

    steps = int(round(float(cfg.total_time_s) / float(cfg.dt_s)))
    n_axles = len(cfg.axle_offsets_m)
    x_grid = np.linspace(0.0, float(cfg.length_m), int(cfg.node_count), dtype=np.float64)

    # Track model for inner coupling solve.
    track_cfg = TrackLFConfig(
        length_m=float(cfg.length_m),
        node_count=int(cfg.node_count),
        support_type="pinned",
        theory="euler",
        bending_stiffness_n_m2=6.5e6,
        shear_stiffness_n=2.45e8,
        winkler_k_n_per_m2=6.0e6,
        pasternak_g_n=1.2e6,
        tolerance=1e-6,
        cg_max_iter=400,
    )

    irr_cfg = IrregularityConfig(
        length_m=float(cfg.length_m),
        dx_m=float(cfg.length_m) / float(cfg.node_count - 1),
        quality_class=str(irregularity_class),
        seed=int(irregularity_seed),
    )
    x_irr, z_irr, irr_metrics = generate_profile(irr_cfg)

    # Vehicle state (vertical, positive downward).
    zc = 0.0
    vc = 0.0
    za = np.zeros(n_axles, dtype=np.float64)
    va = np.zeros(n_axles, dtype=np.float64)

    contact_forces = np.full(n_axles, 80_000.0, dtype=np.float64)

    coupling_iter_hist: list[int] = []
    converged_steps = 0
    max_track_disp = 0.0
    max_contact_force = 0.0
    newton_call_count = 0
    newton_converged_count = 0
    newton_backtracks_total = 0
    newton_iterations_total = 0
    broadphase_pair_count_total = 0
    broadphase_span_candidate_pair_count_total = 0
    broadphase_candidate_pair_count_total = 0
    broadphase_rejected_pair_count_total = 0
    broadphase_gap_rejected_pair_count_total = 0
    track_static_call_count = 0
    track_static_pruned_count = 0
    contact_window_open_pair_count_total = 0
    contact_window_retained_pair_count_total = 0
    retained_force_warm_start_count = 0
    stable_zero_gap_skip_count = 0
    last_gap_predictor = np.full(n_axles, np.nan, dtype=np.float64)
    last_track_window_disp = np.full(n_axles, np.nan, dtype=np.float64)

    trace_head: list[dict] = []

    for step in range(1, steps + 1):
        t = step * float(cfg.dt_s)
        positions = [float(cfg.speed_m_s) * t - float(off) for off in cfg.axle_offsets_m]
        irr_vals = np.array([sample_profile_at(x_irr, z_irr, x) for x in positions], dtype=np.float64)

        # Coupling fixed-point loop: F_contact <-> rail deflection
        prev = contact_forces.copy()
        converged = False
        w_at_axles = np.zeros(n_axles, dtype=np.float64)
        track_disp = np.zeros(int(cfg.node_count), dtype=np.float64)

        for it in range(1, int(cfg.coupling_max_iter) + 1):
            pre_broadphase_candidate_count = 0
            for j in range(n_axles):
                xj = float(positions[j])
                in_window = bool(
                    (-float(cfg.contact_window_margin_m)) <= xj <= (float(cfg.length_m) + float(cfg.contact_window_margin_m))
                )
                if in_window:
                    contact_window_open_pair_count_total += 1
                if not in_window:
                    continue
                force_ref = float(max(0.0, contact_forces[j]))
                gap_predictor = float(za[j] - w_at_axles[j] - irr_vals[j])
                if force_ref > float(cfg.contact_window_force_floor_n):
                    contact_window_retained_pair_count_total += 1
                if gap_predictor > float(cfg.contact_window_release_gap_m) or force_ref > float(cfg.contact_window_force_floor_n):
                    pre_broadphase_candidate_count += 1

            if pre_broadphase_candidate_count <= 0:
                track_static_pruned_count += 1
                track_disp.fill(0.0)
                w_at_axles.fill(0.0)
            else:
                track_static_call_count += 1
                q = _distribute_point_forces_q(
                    node_count=int(cfg.node_count),
                    length_m=float(cfg.length_m),
                    positions_m=positions,
                    forces_n=contact_forces,
                )
                sres = solve_track_static(track_cfg, q)
                track_disp = np.array(sres.displacement_m, dtype=np.float64)

                for j in range(n_axles):
                    xj = positions[j]
                    if xj < 0.0 or xj > float(cfg.length_m):
                        w_at_axles[j] = 0.0
                    else:
                        w_at_axles[j] = _interp_from_grid(x_grid, track_disp, xj)

            broadphase_pair_count_total += int(n_axles)
            broadphase_candidate_mask = np.zeros(n_axles, dtype=bool)
            broadphase_span_candidates_this_iter = 0
            broadphase_candidates_this_iter = 0
            broadphase_rejected_this_iter = 0
            for j in range(n_axles):
                xj = float(positions[j])
                in_span = bool(0.0 <= xj <= float(cfg.length_m))
                if in_span:
                    broadphase_span_candidates_this_iter += 1
                in_window = bool(
                    (-float(cfg.contact_window_margin_m)) <= xj <= (float(cfg.length_m) + float(cfg.contact_window_margin_m))
                )
                force_ref = float(max(0.0, contact_forces[j]))
                gap_predictor = float(za[j] - w_at_axles[j] - irr_vals[j])
                candidate = bool(
                    in_span
                    and in_window
                    and (
                        gap_predictor > float(cfg.contact_window_release_gap_m)
                        or force_ref > float(cfg.contact_window_force_floor_n)
                    )
                )
                broadphase_candidate_mask[j] = candidate
                if candidate:
                    broadphase_candidates_this_iter += 1
                else:
                    broadphase_rejected_this_iter += 1
                    if in_span:
                        broadphase_gap_rejected_pair_count_total += 1

            broadphase_span_candidate_pair_count_total += int(broadphase_span_candidates_this_iter)
            broadphase_candidate_pair_count_total += int(broadphase_candidates_this_iter)
            broadphase_rejected_pair_count_total += int(broadphase_rejected_this_iter)

            if bool(cfg.use_adaptive_newton):
                target = np.zeros(n_axles, dtype=np.float64)
                for j in range(n_axles):
                    if not bool(broadphase_candidate_mask[j]):
                        continue
                    force_ref = float(max(0.0, contact_forces[j]))
                    gap_predictor = float(za[j] - w_at_axles[j] - irr_vals[j])
                    if (
                        np.isfinite(last_gap_predictor[j])
                        and np.isfinite(last_track_window_disp[j])
                        and abs(gap_predictor - float(last_gap_predictor[j])) <= float(cfg.retained_force_gap_tol_m)
                        and abs(float(w_at_axles[j]) - float(last_track_window_disp[j])) <= float(cfg.retained_force_track_disp_tol_m)
                    ):
                        if force_ref >= float(cfg.retained_force_min_force_n):
                            target[j] = force_ref
                            retained_force_warm_start_count += 1
                            continue
                        stable_gap_tol = max(float(cfg.retained_force_gap_tol_m), abs(float(cfg.contact_window_release_gap_m)))
                        if gap_predictor <= stable_gap_tol:
                            target[j] = 0.0
                            stable_zero_gap_skip_count += 1
                            continue
                    disp_ref = abs(float(w_at_axles[j]))
                    compliance = disp_ref / max(force_ref, 1.0)
                    solved_force, solved_meta = _solve_contact_force_adaptive(
                        force_guess_n=float(contact_forces[j]),
                        force_ref_n=force_ref,
                        axle_disp_m=float(za[j]),
                        track_disp_m=float(w_at_axles[j]),
                        irregularity_m=float(irr_vals[j]),
                        hertz_k_n_m_3_2=float(cfg.hertz_k_n_m_3_2),
                        compliance_m_per_n=float(compliance),
                        cfg=cfg,
                    )
                    target[j] = solved_force
                    newton_call_count += 1
                    if bool(solved_meta.get("converged", False)):
                        newton_converged_count += 1
                    newton_backtracks_total += int(solved_meta.get("line_search_backtracks", 0))
                    newton_iterations_total += int(solved_meta.get("iterations", 0))
            else:
                delta = za - w_at_axles - irr_vals
                delta_pos = np.clip(delta, 0.0, None)
                target = float(cfg.hertz_k_n_m_3_2) * np.power(delta_pos, 1.5)
                target = np.where(broadphase_candidate_mask, target, 0.0)
            contact_forces = (1.0 - float(cfg.relaxation)) * contact_forces + float(cfg.relaxation) * target
            contact_forces = np.where(broadphase_candidate_mask, contact_forces, 0.0)

            rel = float(np.max(np.abs(contact_forces - prev)) / max(np.max(np.abs(contact_forces)), 1.0))
            prev = contact_forces.copy()
            if rel <= float(cfg.coupling_tol):
                converged = True
                coupling_iter_hist.append(it)
                converged_steps += 1
                break

        if not converged:
            coupling_iter_hist.append(int(cfg.coupling_max_iter))

        last_gap_predictor = np.asarray(za - w_at_axles - irr_vals, dtype=np.float64)
        last_track_window_disp = np.asarray(w_at_axles, dtype=np.float64)

        # Vehicle update (semi-implicit Euler).
        spring = float(cfg.suspension_k_n_m) * (za - zc)
        damper = float(cfg.suspension_c_n_s_m) * (va - vc)

        a_car = float(np.sum(spring + damper) / float(cfg.carbody_mass_kg))
        a_axle = (-(spring + damper) - contact_forces) / float(cfg.axle_mass_kg)

        vc += a_car * float(cfg.dt_s)
        zc += vc * float(cfg.dt_s)

        va += a_axle * float(cfg.dt_s)
        za += va * float(cfg.dt_s)

        step_max_disp = float(np.max(np.abs(track_disp)))
        step_max_force = float(np.max(np.abs(contact_forces)))
        max_track_disp = max(max_track_disp, step_max_disp)
        max_contact_force = max(max_contact_force, step_max_force)

        if step <= 180:
            trace_head.append(
                {
                    "step": int(step),
                    "time_s": float(t),
                    "coupling_iters": int(coupling_iter_hist[-1]),
                    "coupling_converged": bool(converged),
                    "max_track_disp_m": step_max_disp,
                    "max_contact_force_n": step_max_force,
                    "carbody_disp_m": float(zc),
                }
            )

        if not np.isfinite(zc) or not np.isfinite(vc) or not np.all(np.isfinite(za)) or not np.all(np.isfinite(va)):
            break

    converged_ratio = float(converged_steps / max(steps, 1))
    mean_iters = float(np.mean(coupling_iter_hist)) if coupling_iter_hist else float(cfg.coupling_max_iter)
    elapsed_seconds = max(time.perf_counter() - t0, 1e-12)
    time_steps_per_second = float(steps) / float(elapsed_seconds)
    newton_calls_per_second = float(newton_call_count) / float(elapsed_seconds)
    broadphase_candidate_ratio = float(broadphase_candidate_pair_count_total / max(broadphase_pair_count_total, 1))
    broadphase_rejected_ratio = float(broadphase_rejected_pair_count_total / max(broadphase_pair_count_total, 1))

    finite_ok = bool(
        np.isfinite(max_track_disp)
        and np.isfinite(max_contact_force)
        and np.isfinite(converged_ratio)
        and np.isfinite(mean_iters)
    )
    coupling_ok = bool(converged_ratio >= 0.95)
    dynamic_ok = bool(finite_ok and max_track_disp <= float(cfg.max_disp_limit_m))
    newton_converged_ratio = (
        float(newton_converged_count / max(newton_call_count, 1))
        if bool(cfg.use_adaptive_newton)
        else 1.0
    )
    if bool(cfg.use_adaptive_newton) and newton_call_count == 0 and (retained_force_warm_start_count + stable_zero_gap_skip_count) > 0:
        newton_converged_ratio = 1.0
    newton_ok = bool(
        (not bool(cfg.use_adaptive_newton))
        or (newton_converged_ratio >= float(cfg.adaptive_newton_conv_ratio_min))
    )

    if not finite_ok or not dynamic_ok:
        reason_code = "ERR_DYNAMIC_DIVERGENCE"
    elif not coupling_ok or not newton_ok:
        reason_code = "ERR_COUPLING_DIVERGENCE"
    else:
        reason_code = "PASS"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-vti-coupled-solver",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "config": {
                "length_m": cfg.length_m,
                "node_count": cfg.node_count,
                "speed_m_s": cfg.speed_m_s,
                "dt_s": cfg.dt_s,
                "total_time_s": cfg.total_time_s,
                "axle_offsets_m": list(cfg.axle_offsets_m),
                "axle_mass_kg": cfg.axle_mass_kg,
                "carbody_mass_kg": cfg.carbody_mass_kg,
                "suspension_k_n_m": cfg.suspension_k_n_m,
                "suspension_c_n_s_m": cfg.suspension_c_n_s_m,
                "hertz_k_n_m_3_2": cfg.hertz_k_n_m_3_2,
                "coupling_max_iter": cfg.coupling_max_iter,
                "coupling_tol": cfg.coupling_tol,
                "relaxation": cfg.relaxation,
                "max_disp_limit_m": cfg.max_disp_limit_m,
                "use_adaptive_newton": cfg.use_adaptive_newton,
                "adaptive_newton_max_iter": cfg.adaptive_newton_max_iter,
                "adaptive_newton_tol": cfg.adaptive_newton_tol,
                "adaptive_newton_conv_ratio_min": cfg.adaptive_newton_conv_ratio_min,
                "contact_window_margin_m": cfg.contact_window_margin_m,
                "contact_window_release_gap_m": cfg.contact_window_release_gap_m,
                "contact_window_force_floor_n": cfg.contact_window_force_floor_n,
                "retained_force_min_force_n": cfg.retained_force_min_force_n,
                "retained_force_gap_tol_m": cfg.retained_force_gap_tol_m,
                "retained_force_track_disp_tol_m": cfg.retained_force_track_disp_tol_m,
            },
            "irregularity": {
                "class": irregularity_class,
                "seed": int(irregularity_seed),
            },
        },
        "checks": {
            "finite_response": finite_ok,
            "coupling_converged_ratio_pass": coupling_ok,
            "dynamic_disp_pass": dynamic_ok,
            "adaptive_newton_converged_pass": bool(newton_ok),
        },
        "metrics": {
            "step_count": int(steps),
            "converged_steps": int(converged_steps),
            "converged_ratio": converged_ratio,
            "mean_coupling_iters": mean_iters,
            "elapsed_seconds": float(elapsed_seconds),
            "time_steps_per_second": float(time_steps_per_second),
            "adaptive_newton_calls_per_second": float(newton_calls_per_second),
            "max_track_disp_m": float(max_track_disp),
            "max_contact_force_n": float(max_contact_force),
            "adaptive_newton_call_count": int(newton_call_count),
            "adaptive_newton_converged_count": int(newton_converged_count),
            "adaptive_newton_converged_ratio": float(newton_converged_ratio),
            "adaptive_newton_backtracks_total": int(newton_backtracks_total),
            "adaptive_newton_avg_iterations": (
                float(newton_iterations_total / max(newton_call_count, 1))
                if bool(cfg.use_adaptive_newton)
                else 0.0
            ),
            "broadphase_pair_count_total": int(broadphase_pair_count_total),
            "broadphase_span_candidate_pair_count_total": int(broadphase_span_candidate_pair_count_total),
            "broadphase_candidate_pair_count_total": int(broadphase_candidate_pair_count_total),
            "broadphase_rejected_pair_count_total": int(broadphase_rejected_pair_count_total),
            "broadphase_gap_rejected_pair_count_total": int(broadphase_gap_rejected_pair_count_total),
            "broadphase_candidate_pair_ratio": float(broadphase_candidate_ratio),
            "broadphase_rejected_pair_ratio": float(broadphase_rejected_ratio),
            "broadphase_candidate_pairs_per_step": float(broadphase_candidate_pair_count_total / max(steps, 1)),
            "broadphase_rejected_pairs_per_step": float(broadphase_rejected_pair_count_total / max(steps, 1)),
            "track_static_call_count": int(track_static_call_count),
            "track_static_pruned_count": int(track_static_pruned_count),
            "track_static_pruned_ratio": float(track_static_pruned_count / max(track_static_call_count + track_static_pruned_count, 1)),
            "contact_window_open_pair_count_total": int(contact_window_open_pair_count_total),
            "contact_window_retained_pair_count_total": int(contact_window_retained_pair_count_total),
            "contact_window_retained_pair_ratio": float(contact_window_retained_pair_count_total / max(contact_window_open_pair_count_total, 1)),
            "retained_force_warm_start_count": int(retained_force_warm_start_count),
            "retained_force_warm_start_ratio": float(retained_force_warm_start_count / max(broadphase_candidate_pair_count_total, 1)),
            "stable_zero_gap_skip_count": int(stable_zero_gap_skip_count),
            "stable_zero_gap_skip_ratio": float(stable_zero_gap_skip_count / max(broadphase_candidate_pair_count_total, 1)),
        },
        "irregularity_metrics": irr_metrics,
        "trace_head": trace_head,
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    return payload


def main() -> None:
    logger = get_logger("phase1.vti_coupled_solver")
    p = argparse.ArgumentParser()
    p.add_argument("--length-m", type=float, default=60.0)
    p.add_argument("--node-count", type=int, default=161)
    p.add_argument("--speed-m-s", type=float, default=22.2)
    p.add_argument("--dt-s", type=float, default=0.005)
    p.add_argument("--total-time-s", type=float, default=0.8)
    p.add_argument("--axle-offsets-m", default="6.0,8.5,11.0,13.5")
    p.add_argument("--axle-mass-kg", type=float, default=1500.0)
    p.add_argument("--carbody-mass-kg", type=float, default=25000.0)
    p.add_argument("--suspension-k", type=float, default=7.5e5)
    p.add_argument("--suspension-c", type=float, default=1.5e4)
    p.add_argument("--hertz-k", type=float, default=1.05e9)
    p.add_argument("--coupling-max-iter", type=int, default=12)
    p.add_argument("--coupling-tol", type=float, default=2e-3)
    p.add_argument("--relaxation", type=float, default=0.55)
    p.add_argument("--max-disp-limit", type=float, default=0.12)
    p.add_argument("--use-adaptive-newton", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--adaptive-newton-max-iter", type=int, default=18)
    p.add_argument("--adaptive-newton-tol", type=float, default=1e-8)
    p.add_argument("--adaptive-newton-conv-ratio-min", type=float, default=0.98)
    p.add_argument("--contact-window-margin-m", type=float, default=0.75)
    p.add_argument("--contact-window-release-gap-m", type=float, default=-5e-4)
    p.add_argument("--contact-window-force-floor-n", type=float, default=250.0)
    p.add_argument("--retained-force-min-force-n", type=float, default=25.0)
    p.add_argument("--retained-force-gap-tol-m", type=float, default=1.0e-3)
    p.add_argument("--retained-force-track-disp-tol-m", type=float, default=1.0e-3)
    p.add_argument("--irregularity-class", default="B", choices=["A", "B", "C", "D"])
    p.add_argument("--irregularity-seed", type=int, default=23)
    p.add_argument("--out", default="implementation/phase1/vti_coupled_solver_report.json")
    args = p.parse_args()

    try:
        offsets = tuple(float(x.strip()) for x in str(args.axle_offsets_m).split(",") if x.strip())
        input_payload = {
            "length_m": float(args.length_m),
            "node_count": int(args.node_count),
            "speed_m_s": float(args.speed_m_s),
            "dt_s": float(args.dt_s),
            "total_time_s": float(args.total_time_s),
            "axle_offsets_m": list(offsets),
            "axle_mass_kg": float(args.axle_mass_kg),
            "carbody_mass_kg": float(args.carbody_mass_kg),
            "suspension_k": float(args.suspension_k),
            "suspension_c": float(args.suspension_c),
            "hertz_k": float(args.hertz_k),
            "coupling_max_iter": int(args.coupling_max_iter),
            "coupling_tol": float(args.coupling_tol),
            "relaxation": float(args.relaxation),
            "max_disp_limit": float(args.max_disp_limit),
            "use_adaptive_newton": bool(args.use_adaptive_newton),
            "adaptive_newton_max_iter": int(args.adaptive_newton_max_iter),
            "adaptive_newton_tol": float(args.adaptive_newton_tol),
            "adaptive_newton_conv_ratio_min": float(args.adaptive_newton_conv_ratio_min),
            "contact_window_margin_m": float(args.contact_window_margin_m),
            "contact_window_release_gap_m": float(args.contact_window_release_gap_m),
            "contact_window_force_floor_n": float(args.contact_window_force_floor_n),
            "retained_force_min_force_n": float(args.retained_force_min_force_n),
            "retained_force_gap_tol_m": float(args.retained_force_gap_tol_m),
            "retained_force_track_disp_tol_m": float(args.retained_force_track_disp_tol_m),
            "irregularity_class": str(args.irregularity_class),
            "irregularity_seed": int(args.irregularity_seed),
            "out": str(args.out),
        }
        validate_input_contract(input_payload, VTI_INPUT_SCHEMA, label="phase-b3.vti_coupled_solver")
        log_event(logger, logging.INFO, "vti.start", inputs=input_payload)
        cfg = VTICoupledConfig(
            length_m=float(args.length_m),
            node_count=int(args.node_count),
            speed_m_s=float(args.speed_m_s),
            dt_s=float(args.dt_s),
            total_time_s=float(args.total_time_s),
            axle_offsets_m=offsets,
            axle_mass_kg=float(args.axle_mass_kg),
            carbody_mass_kg=float(args.carbody_mass_kg),
            suspension_k_n_m=float(args.suspension_k),
            suspension_c_n_s_m=float(args.suspension_c),
            hertz_k_n_m_3_2=float(args.hertz_k),
            coupling_max_iter=int(args.coupling_max_iter),
            coupling_tol=float(args.coupling_tol),
            relaxation=float(args.relaxation),
            max_disp_limit_m=float(args.max_disp_limit),
            use_adaptive_newton=bool(args.use_adaptive_newton),
            adaptive_newton_max_iter=int(args.adaptive_newton_max_iter),
            adaptive_newton_tol=float(args.adaptive_newton_tol),
            adaptive_newton_conv_ratio_min=float(args.adaptive_newton_conv_ratio_min),
            contact_window_margin_m=float(args.contact_window_margin_m),
            contact_window_release_gap_m=float(args.contact_window_release_gap_m),
            contact_window_force_floor_n=float(args.contact_window_force_floor_n),
            retained_force_min_force_n=float(args.retained_force_min_force_n),
            retained_force_gap_tol_m=float(args.retained_force_gap_tol_m),
            retained_force_track_disp_tol_m=float(args.retained_force_track_disp_tol_m),
        )
        payload = run_vti_coupled_solver(
            cfg,
            irregularity_class=str(args.irregularity_class),
            irregularity_seed=int(args.irregularity_seed),
        )
        log_event(
            logger,
            logging.INFO,
            "vti.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "vti.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-vti-coupled-solver",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote VTI coupled solver report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "vti.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-vti-coupled-solver",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote VTI coupled solver report: {out}")
        raise SystemExit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote VTI coupled solver report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
