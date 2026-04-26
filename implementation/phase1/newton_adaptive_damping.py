#!/usr/bin/env python3
"""Adaptive-damped Newton solver utilities.

Core API:
solve_with_adaptive_damping(state, residual_fn, jacobian_fn, cfg) -> result
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np


@dataclass
class AdaptiveNewtonConfig:
    max_iter: int = 80
    tol: float = 1e-6
    lambda_init: float = 1e-2
    lambda_up: float = 4.0
    lambda_down: float = 0.5
    lambda_min: float = 1e-8
    lambda_max: float = 1e8
    line_search_max_backtracks: int = 10
    line_search_shrink: float = 0.5
    sufficient_decrease: float = 1e-4
    stagnation_window: int = 3
    stagnation_min_improvement: float = 0.02
    stagnation_lambda_boost: float = 2.0


def _norm2(v: np.ndarray) -> float:
    return float(np.linalg.norm(v, ord=2))


def _safe_solve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    try:
        return np.linalg.solve(a, b)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(a, b, rcond=None)[0]


def _should_apply_stagnation_cutback(
    residual_history: list[float],
    cfg: AdaptiveNewtonConfig,
) -> bool:
    window = max(0, int(cfg.stagnation_window))
    if window <= 0 or len(residual_history) < window + 1:
        return False
    latest = float(residual_history[-1])
    window_start = float(residual_history[-1 - window])
    if not math.isfinite(latest) or not math.isfinite(window_start):
        return False
    if latest <= float(cfg.tol):
        return False
    min_improvement = max(0.0, float(cfg.stagnation_min_improvement))
    required_latest = window_start * max(0.0, 1.0 - min_improvement)
    return bool(latest >= required_latest)


def solve_with_adaptive_damping(
    state: np.ndarray,
    residual_fn: Callable[[np.ndarray], np.ndarray],
    jacobian_fn: Callable[[np.ndarray], np.ndarray],
    cfg: AdaptiveNewtonConfig | None = None,
) -> dict:
    if cfg is None:
        cfg = AdaptiveNewtonConfig()

    x = np.array(state, dtype=float).reshape(-1)
    lam = float(cfg.lambda_init)
    lambda_history: list[float] = [lam]
    residual_history: list[float] = []
    line_search_backtracks = 0
    cutback_count = 0
    stagnation_events = 0
    event_history: list[dict[str, float | int | bool | str]] = []

    r = np.array(residual_fn(x), dtype=float).reshape(-1)
    r0_norm = _norm2(r)
    residual_history.append(r0_norm)

    converged = bool(r0_norm <= float(cfg.tol))
    iters = 0

    while (not converged) and iters < int(cfg.max_iter):
        iters += 1
        j = np.array(jacobian_fn(x), dtype=float)
        if j.ndim != 2 or j.shape[0] != r.shape[0] or j.shape[1] != x.shape[0]:
            raise ValueError("jacobian shape mismatch")

        # Levenberg-Marquardt style step: (J^T J + λI) δ = -J^T r
        h = j.T @ j
        g = j.T @ r
        a = h + lam * np.eye(h.shape[0], dtype=float)
        delta = _safe_solve(a, -g)

        old_norm = _norm2(r)
        alpha = 1.0
        accepted = False
        iter_backtracks = 0
        lam_before = float(lam)
        new_norm = old_norm

        for bt in range(int(cfg.line_search_max_backtracks) + 1):
            x_try = x + alpha * delta
            r_try = np.array(residual_fn(x_try), dtype=float).reshape(-1)
            new_norm = _norm2(r_try)
            # Armijo-like sufficient decrease
            if new_norm <= old_norm * (1.0 - float(cfg.sufficient_decrease) * alpha):
                accepted = True
                x = x_try
                r = r_try
                break
            alpha *= float(cfg.line_search_shrink)
            line_search_backtracks += 1
            iter_backtracks += 1

        if accepted:
            lam = max(float(cfg.lambda_min), lam * float(cfg.lambda_down))
        else:
            lam = min(float(cfg.lambda_max), lam * float(cfg.lambda_up))

        lambda_history.append(lam)
        residual_history.append(_norm2(r))
        residual_after = float(residual_history[-1])
        stagnation_cutback = False
        if _should_apply_stagnation_cutback(residual_history, cfg):
            boosted = min(float(cfg.lambda_max), max(float(lam), lam_before) * float(cfg.stagnation_lambda_boost))
            if boosted > lam + 1e-18:
                lam = boosted
                lambda_history[-1] = float(lam)
                stagnation_cutback = True
                stagnation_events += 1
                cutback_count += 1
        if iter_backtracks > 0 or not accepted:
            cutback_count += 1
        event = "accepted_full_step"
        if not accepted:
            event = "rejected_step"
        elif iter_backtracks > 0:
            event = "accepted_line_search_cutback"
        if stagnation_cutback:
            event = f"{event}+stagnation_cutback"
        reduction_ratio = 0.0 if old_norm <= 0.0 else residual_after / old_norm
        event_history.append(
            {
                "iteration": int(iters),
                "event": event,
                "accepted": bool(accepted),
                "line_search_backtracks": int(iter_backtracks),
                "step_scale": float(alpha if accepted else 0.0),
                "lambda_before": float(lam_before),
                "lambda_after": float(lam),
                "residual_before": float(old_norm),
                "residual_after": float(residual_after),
                "residual_reduction_ratio": float(reduction_ratio),
                "stagnation_cutback": bool(stagnation_cutback),
            }
        )
        converged = bool(residual_history[-1] <= float(cfg.tol))

        if not math.isfinite(residual_history[-1]):
            converged = False
            break

    return {
        "state": x.tolist(),
        "converged": bool(converged),
        "iterations": int(iters),
        "lambda_history": [float(v) for v in lambda_history],
        "line_search_backtracks": int(line_search_backtracks),
        "cutback_count": int(cutback_count),
        "stagnation_events": int(stagnation_events),
        "residual_norm_initial": float(r0_norm),
        "residual_norm_final": float(residual_history[-1] if residual_history else r0_norm),
        "residual_history": [float(v) for v in residual_history],
        "event_history": event_history,
    }


def _demo_residual(x: np.ndarray) -> np.ndarray:
    # simple nonlinear system with known root around (sqrt(2), 0.5)
    return np.array([
        x[0] * x[0] - 2.0,
        math.tanh(x[1]) - math.tanh(0.5),
    ])


def _demo_jacobian(x: np.ndarray) -> np.ndarray:
    return np.array([
        [2.0 * x[0], 0.0],
        [0.0, 1.0 / math.cosh(x[1]) ** 2],
    ])


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/newton_adaptive_damping_report.json")
    p.add_argument("--max-iter", type=int, default=80)
    p.add_argument("--tol", type=float, default=1e-6)
    args = p.parse_args()

    cfg = AdaptiveNewtonConfig(max_iter=int(args.max_iter), tol=float(args.tol))
    result = solve_with_adaptive_damping(np.array([2.8, -2.0]), _demo_residual, _demo_jacobian, cfg)

    payload = {
        "schema_version": "1.0",
        "run_id": "phase3-newton-adaptive-damping",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "max_iter": int(args.max_iter),
            "tol": float(args.tol),
        },
        "result": result,
        "checks": {
            "converged": bool(result.get("converged", False)),
            "iterations_within_budget": int(result.get("iterations", 10**9)) <= int(args.max_iter),
            "residual_below_tol": float(result.get("residual_norm_final", math.inf)) <= float(args.tol),
        },
        "contract_pass": bool(result.get("converged", False) and float(result.get("residual_norm_final", math.inf)) <= float(args.tol)),
        "reason_code": "PASS" if bool(result.get("converged", False)) else "ERR_NO_CONVERGENCE",
        "reason": "adaptive newton converged" if bool(result.get("converged", False)) else "adaptive newton did not converge",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote adaptive newton report: {out}")
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
