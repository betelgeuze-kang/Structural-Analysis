#!/usr/bin/env python3
"""Trust-region and arc-length compatible line search for equilibrium Newton."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np


def max_alpha_within_displacement_cap(
    *,
    u: np.ndarray,
    delta: np.ndarray,
    node_xyz: np.ndarray,
    displacement_cap_m: float,
    translation_metrics: Callable[[np.ndarray, np.ndarray], dict[str, Any]],
    max_translation_increment_m: float | None = None,
    bracket_iterations: int = 28,
) -> float:
    """Binary-search the largest alpha with max translation <= displacement_cap_m."""
    cap = float(displacement_cap_m)
    if cap <= 0.0:
        return 0.0
    base = np.asarray(u, dtype=np.float64)
    step = np.asarray(delta, dtype=np.float64)
    xyz = np.asarray(node_xyz, dtype=np.float64)
    current = float(translation_metrics(base, xyz).get("max_translation_m") or 0.0)
    if max_translation_increment_m is not None and float(max_translation_increment_m) > 0.0:
        cap = min(cap, current + float(max_translation_increment_m))
    if current >= cap:
        return 0.0
    trial = base + step
    if float(translation_metrics(trial, xyz).get("max_translation_m") or 0.0) <= cap:
        return 1.0
    lo = 0.0
    hi = 1.0
    for _ in range(max(int(bracket_iterations), 1)):
        mid = 0.5 * (lo + hi)
        trial = base + mid * step
        if float(translation_metrics(trial, xyz).get("max_translation_m") or 0.0) <= cap:
            lo = mid
        else:
            hi = mid
    return float(lo)


def trust_region_line_search_alphas(
    *,
    u: np.ndarray,
    delta: np.ndarray,
    node_xyz: np.ndarray | None,
    displacement_cap_m: float | None,
    translation_metrics: Callable[[np.ndarray, np.ndarray], dict[str, Any]] | None,
    max_translation_increment_m: float | None = None,
    base_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    ),
    arc_length_floor: float = 1.0e-4,
    include_negative: bool = False,
) -> tuple[float, ...]:
    """Candidate alphas capped by trust region, with arc-length style geometric falloff."""
    if (
        displacement_cap_m is None
        or node_xyz is None
        or translation_metrics is None
        or float(np.max(np.abs(delta))) <= 1.0e-18
    ):
        if not include_negative:
            return base_alphas
        signed = list(base_alphas)
        for alpha in base_alphas:
            neg = -float(alpha)
            if all(abs(neg - existing) > 1.0e-12 for existing in signed):
                signed.append(neg)
        return tuple(signed)
    alpha_cap = max_alpha_within_displacement_cap(
        u=u,
        delta=delta,
        node_xyz=node_xyz,
        displacement_cap_m=float(displacement_cap_m),
        translation_metrics=translation_metrics,
        max_translation_increment_m=max_translation_increment_m,
    )
    if alpha_cap <= 0.0:
        return (0.0,)
    candidates: list[float] = []
    for alpha in base_alphas:
        capped = min(float(alpha), float(alpha_cap))
        if capped > 0.0 and all(abs(capped - existing) > 1.0e-12 for existing in candidates):
            candidates.append(capped)
    geometric = float(alpha_cap)
    while geometric >= float(arc_length_floor):
        if all(abs(geometric - existing) > 1.0e-12 for existing in candidates):
            candidates.append(geometric)
        geometric *= 0.5
    if include_negative:
        for alpha in tuple(candidates):
            neg = -float(alpha)
            if all(abs(neg - existing) > 1.0e-12 for existing in candidates):
                candidates.append(neg)
    return tuple(sorted(candidates, key=lambda value: (value < 0.0, -abs(value), -value)))


def select_residual_descent_alpha(
    *,
    u: np.ndarray,
    delta: np.ndarray,
    residual_inf: float,
    assemble_residual: Callable[..., tuple[Any, Any, Any, np.ndarray, Any, dict[str, Any]]],
    alphas: tuple[float, ...],
    node_xyz: np.ndarray | None = None,
    displacement_cap_m: float | None = None,
    max_translation_increment_m: float | None = None,
    translation_metrics: Callable[[np.ndarray, np.ndarray], dict[str, Any]] | None = None,
    residual_only_free: np.ndarray | None = None,
    residual_only_external_load: np.ndarray | None = None,
) -> tuple[float, float, np.ndarray, list[dict[str, Any]]]:
    """Pick the best alpha that reduces the equilibrium residual."""
    best_alpha = 0.0
    best_residual_inf = float(residual_inf)
    best_u = np.asarray(u, dtype=np.float64)
    trial_rows: list[dict[str, Any]] = []
    residual_only_supported = bool(
        getattr(assemble_residual, "supports_residual_only", False)
        and residual_only_free is not None
    )
    for alpha in alphas:
        if abs(float(alpha)) <= 0.0:
            trial_rows.append({"alpha": float(alpha), "residual_inf_n": float(residual_inf), "skipped": True})
            continue
        candidate = np.asarray(u, dtype=np.float64) + float(alpha) * np.asarray(delta, dtype=np.float64)
        if (
            displacement_cap_m is not None
            and node_xyz is not None
            and translation_metrics is not None
        ):
            xyz = np.asarray(node_xyz, dtype=np.float64)
            base_metrics = translation_metrics(np.asarray(u, dtype=np.float64), xyz)
            current_translation = float(base_metrics.get("max_translation_m") or 0.0)
            effective_cap = float(displacement_cap_m)
            if max_translation_increment_m is not None and float(max_translation_increment_m) > 0.0:
                effective_cap = min(
                    effective_cap,
                    current_translation + float(max_translation_increment_m),
                )
            trial_metrics = translation_metrics(candidate, xyz)
            if float(trial_metrics.get("max_translation_m") or 0.0) > effective_cap:
                trial_rows.append(
                    {
                        "alpha": float(alpha),
                        "residual_inf_n": None,
                        "displacement_cap_exceeded": True,
                    }
                )
                continue
        if residual_only_supported:
            try:
                _k, _f, _free, trial_residual, _rhs, _meta = assemble_residual(
                    candidate,
                    residual_only=True,
                    free_override=np.asarray(residual_only_free, dtype=np.int64),
                    external_load_override=residual_only_external_load,
                )
                used_residual_only = True
            except TypeError:
                _k, _f, _free, trial_residual, _rhs, _meta = assemble_residual(candidate)
                used_residual_only = False
        else:
            _k, _f, _free, trial_residual, _rhs, _meta = assemble_residual(candidate)
            used_residual_only = False
        trial_inf = float(np.max(np.abs(trial_residual))) if trial_residual.size else float("inf")
        trial_row: dict[str, Any] = {
            "alpha": float(alpha),
            "residual_inf_n": trial_inf,
            "residual_only_assembly": bool(used_residual_only),
        }
        if isinstance(_meta, dict):
            if "shell_operator_cache_size" in _meta:
                trial_row["shell_operator_cache_size"] = int(
                    _meta.get("shell_operator_cache_size") or 0
                )
            shell_meta = _meta.get("shell_meta")
            if isinstance(shell_meta, dict):
                if "shell_internal_force_cache_hit" in shell_meta:
                    trial_row["shell_internal_force_cache_hit"] = bool(
                        shell_meta.get("shell_internal_force_cache_hit")
                    )
                if "shell_internal_force_cache_enabled" in shell_meta:
                    trial_row["shell_internal_force_cache_enabled"] = bool(
                        shell_meta.get("shell_internal_force_cache_enabled")
                    )
        trial_rows.append(trial_row)
        if trial_inf < best_residual_inf:
            best_residual_inf = trial_inf
            best_alpha = float(alpha)
            best_u = candidate
    return best_alpha, best_residual_inf, best_u, trial_rows
