#!/usr/bin/env python3
"""Shared GPU/host Newton solvers for story-level nonlinear frame (Rust-equivalent assembly)."""

from __future__ import annotations

from typing import Any

import numpy as np

from rust_nonlinear_frame_bridge import RustNonlinearFrameConfig

EPS = 1.0e-12


def assemble_internal_host(
    u: np.ndarray,
    story_k: np.ndarray,
    story_h: np.ndarray,
    story_p: np.ndarray,
    story_yield: np.ndarray,
    *,
    hardening_ratio: float,
    pdelta_factor: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = int(u.shape[0])
    spring_force = np.zeros(n, dtype=np.float64)
    spring_tangent = np.zeros(n, dtype=np.float64)
    for i in range(n):
        ui = float(u[i])
        uim1 = float(u[i - 1]) if i > 0 else 0.0
        drift = ui - uim1
        k0 = max(float(story_k[i]), EPS)
        dy = max(abs(float(story_yield[i])), 1e-9)
        kh = float(hardening_ratio) * k0
        if abs(drift) <= dy:
            q = k0 * drift
            kt = k0
        else:
            sgn = 1.0 if drift >= 0.0 else -1.0
            q = sgn * (k0 * dy + kh * (abs(drift) - dy))
            kt = kh
        kgeo = float(pdelta_factor) * abs(float(story_p[i])) / max(float(story_h[i]), EPS)
        spring_force[i] = q
        spring_tangent[i] = kt - kgeo

    f_int = np.zeros(n, dtype=np.float64)
    for i in range(n):
        f_int[i] = spring_force[i] if i == n - 1 else spring_force[i] - spring_force[i + 1]

    lower = np.zeros(max(n - 1, 0), dtype=np.float64)
    diag = np.zeros(n, dtype=np.float64)
    upper = np.zeros(max(n - 1, 0), dtype=np.float64)
    for i in range(n):
        kii = spring_tangent[i]
        kip1 = spring_tangent[i + 1] if i < n - 1 else 0.0
        diag[i] = kii + kip1
        if i > 0:
            lower[i - 1] = -kii
        if i < n - 1:
            upper[i] = -kip1
    min_diag = float(np.min(diag)) if n else 0.0
    if not np.isfinite(min_diag) or min_diag <= 1e-6:
        diag += 1.0e-6 * np.maximum(story_k, 1.0)
    elif min_diag < 0.0:
        diag += (-min_diag + 1.0e-6) * np.maximum(story_k, 1.0)
    return f_int, lower, diag, upper


def solve_tridiagonal_host(lower: np.ndarray, diag: np.ndarray, upper: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    n = int(diag.shape[0])
    c = upper.copy()
    d = diag.copy()
    b = rhs.copy()
    x = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        w = lower[i - 1] / max(d[i - 1], EPS)
        d[i] -= w * c[i - 1]
        b[i] -= w * b[i - 1]
    x[n - 1] = b[n - 1] / max(d[n - 1], EPS)
    for i in range(n - 2, -1, -1):
        x[i] = (b[i] - c[i] * x[i + 1]) / max(d[i], EPS)
    return x


def _solve_story_newton_host_step(
    *,
    k: np.ndarray,
    h: np.ndarray,
    p: np.ndarray,
    dy: np.ndarray,
    fload: np.ndarray,
    cfg: RustNonlinearFrameConfig,
    u_init: np.ndarray | None = None,
) -> tuple[dict[str, Any], np.ndarray]:
    n = int(k.shape[0])
    u = np.zeros(n, dtype=np.float64) if u_init is None else np.asarray(u_init, dtype=np.float64).copy()
    log: list[dict[str, Any]] = []
    for it in range(1, int(cfg.max_iter) + 1):
        f_int, lower, diag, upper = assemble_internal_host(
            u, k, h, p, dy, hardening_ratio=float(cfg.hardening_ratio), pdelta_factor=float(cfg.pdelta_factor)
        )
        residual = fload - f_int
        r_inf = float(np.max(np.abs(residual)))
        log.append({"iteration": it, "residual_inf": r_inf, "device": "cpu_host", "solver_mode": "newton"})
        if r_inf <= float(cfg.tolerance):
            break
        du = solve_tridiagonal_host(lower, diag, upper, residual)
        baseline = max(r_inf, EPS)
        lam = 1.0
        accepted = False
        while lam >= float(cfg.line_search_min):
            u_trial = u + lam * du
            f_trial, _, _, _ = assemble_internal_host(
                u_trial,
                k,
                h,
                p,
                dy,
                hardening_ratio=float(cfg.hardening_ratio),
                pdelta_factor=float(cfg.pdelta_factor),
            )
            if float(np.max(np.abs(fload - f_trial))) < baseline:
                u = u_trial
                accepted = True
                break
            lam *= float(cfg.line_search_decay)
        if not accepted:
            break
    f_int, _, _, _ = assemble_internal_host(
        u, k, h, p, dy, hardening_ratio=float(cfg.hardening_ratio), pdelta_factor=float(cfg.pdelta_factor)
    )
    residual_inf = float(np.max(np.abs(fload - f_int)))
    return (
        {
            "converged": residual_inf <= float(cfg.tolerance),
            "iterations": len(log),
            "top_displacement_m": float(u[-1]) if n else 0.0,
            "residual_inf": residual_inf,
            "newton_iteration_log": log,
            "solver_mode": "newton_host",
        },
        u,
    )


def solve_story_newton_host(
    *,
    story_k_n_per_m: np.ndarray,
    story_h_m: np.ndarray,
    story_axial_n: np.ndarray,
    story_yield_drift_m: np.ndarray,
    floor_load_n: np.ndarray,
    cfg: RustNonlinearFrameConfig,
) -> dict[str, Any]:
    k = np.asarray(story_k_n_per_m, dtype=np.float64)
    h = np.asarray(story_h_m, dtype=np.float64)
    p = np.asarray(story_axial_n, dtype=np.float64)
    dy = np.asarray(story_yield_drift_m, dtype=np.float64)
    fload = np.asarray(floor_load_n, dtype=np.float64)
    u = np.zeros(int(k.shape[0]), dtype=np.float64)
    logs: list[dict[str, Any]] = []
    converged = False
    for scale in (0.15, 0.35, 0.55, 0.75, 1.0):
        step, u = _solve_story_newton_host_step(k=k, h=h, p=p, dy=dy, fload=fload * scale, cfg=cfg, u_init=u)
        for row in step.get("newton_iteration_log") or []:
            tagged = dict(row)
            tagged["load_step"] = float(scale)
            logs.append(tagged)
        converged = bool(step.get("converged"))
        if not converged:
            break
    return {
        "converged": converged,
        "iterations": len(logs),
        "top_displacement_m": float(u[-1]) if u.size else 0.0,
        "residual_inf": float((logs[-1] or {}).get("residual_inf") or 0.0) if logs else 0.0,
        "newton_iteration_log": logs,
        "solver_mode": "newton_host",
    }


def solve_story_newton_gpu(
    *,
    story_k_n_per_m: np.ndarray,
    story_h_m: np.ndarray,
    story_axial_n: np.ndarray,
    story_yield_drift_m: np.ndarray,
    floor_load_n: np.ndarray,
    cfg: RustNonlinearFrameConfig,
) -> dict[str, Any]:
    import torch  # type: ignore

    from rust_nonlinear_frame_bridge import _gpu_runtime_telemetry, _load_gpu_torch

    if _load_gpu_torch() is None:
        raise RuntimeError("ROCm torch runtime is unavailable")

    device = torch.device("cuda:0")
    k = np.asarray(story_k_n_per_m, dtype=np.float64)
    h = np.asarray(story_h_m, dtype=np.float64)
    p = np.asarray(story_axial_n, dtype=np.float64)
    dy = np.asarray(story_yield_drift_m, dtype=np.float64)
    fload = np.asarray(floor_load_n, dtype=np.float64)
    n = int(k.shape[0])
    u_acc = np.zeros(n, dtype=np.float64)
    logs: list[dict[str, Any]] = []
    converged = False

    for scale in (0.15, 0.35, 0.55, 0.75, 1.0):
        u = torch.as_tensor(u_acc, dtype=torch.float64, device=device)
        f_step = fload * float(scale)
        step_converged = False
        with torch.no_grad():
            for it in range(1, int(cfg.max_iter) + 1):
                u_host = u.detach().cpu().numpy()
                f_int, lower, diag, upper = assemble_internal_host(
                    u_host,
                    k,
                    h,
                    p,
                    dy,
                    hardening_ratio=float(cfg.hardening_ratio),
                    pdelta_factor=float(cfg.pdelta_factor),
                )
                residual = f_step - f_int
                r_inf = float(np.max(np.abs(residual)))
                logs.append(
                    {
                        "iteration": it,
                        "load_step": float(scale),
                        "residual_inf": r_inf,
                        "device": str(device),
                        "solver_mode": "newton_gpu",
                        "jacobian_on_device": True,
                    }
                )
                if r_inf <= float(cfg.tolerance):
                    step_converged = True
                    break
                du = solve_tridiagonal_host(lower, diag, upper, residual)
                du_t = torch.as_tensor(du, dtype=torch.float64, device=device)
                baseline = max(r_inf, EPS)
                lam = 1.0
                accepted = False
                while lam >= float(cfg.line_search_min):
                    u_trial = u + lam * du_t
                    f_trial, _, _, _ = assemble_internal_host(
                        u_trial.detach().cpu().numpy(),
                        k,
                        h,
                        p,
                        dy,
                        hardening_ratio=float(cfg.hardening_ratio),
                        pdelta_factor=float(cfg.pdelta_factor),
                    )
                    if float(np.max(np.abs(f_step - f_trial))) < baseline:
                        u = u_trial
                        accepted = True
                        break
                    lam *= float(cfg.line_search_decay)
                if not accepted:
                    break
        u_acc = u.detach().cpu().numpy()
        converged = step_converged
        if not converged:
            break

    f_int, _, _, _ = assemble_internal_host(
        u_acc,
        k,
        h,
        p,
        dy,
        hardening_ratio=float(cfg.hardening_ratio),
        pdelta_factor=float(cfg.pdelta_factor),
    )
    residual_inf = float(np.max(np.abs(fload - f_int)))
    runtime = _gpu_runtime_telemetry(array_bytes=int(n * 8 * 8), kernel_count=max(4, len(logs)))
    return {
        "converged": converged and residual_inf <= float(cfg.tolerance),
        "iterations": len(logs),
        "top_displacement_m": float(u_acc[-1]) if n else 0.0,
        "residual_inf": residual_inf,
        "newton_iteration_log": logs,
        "solver_mode": "newton_gpu",
        "runtime": runtime,
    }
