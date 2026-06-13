#!/usr/bin/env python3
"""Cached residual-only finite-difference JVP helpers for MGT probes."""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np


ResidualAssembler = Callable[
    ...,
    tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]],
]


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


class ResidualJvpBatchCache:
    """Cache full residual JVP columns keyed by global DOF and epsilon."""

    def __init__(
        self,
        *,
        assemble_residual: ResidualAssembler,
        base_u: np.ndarray,
        base_free: np.ndarray,
        base_residual: np.ndarray,
        reference_f_ext: np.ndarray,
        prefer_residual_only: bool = True,
    ) -> None:
        self._assemble_residual = assemble_residual
        self._base_u = np.asarray(base_u, dtype=np.float64)
        self._base_free = np.asarray(base_free, dtype=np.int64)
        self._base_residual = np.asarray(base_residual, dtype=np.float64)
        self._reference_f_ext = np.asarray(reference_f_ext, dtype=np.float64)
        self._prefer_residual_only = bool(prefer_residual_only)
        self._cache: dict[tuple[int, float], tuple[np.ndarray, dict[str, Any]]] = {}
        self._request_count = 0
        self._hit_count = 0
        self._miss_count = 0
        self._residual_only_count = 0
        self._full_assembly_count = 0
        self._unstable_free_count = 0
        self._assembly_seconds = 0.0

    def evaluate_global_dof(
        self,
        *,
        global_dof: int,
        epsilon: float,
    ) -> tuple[np.ndarray | None, dict[str, Any]]:
        self._request_count += 1
        global_dof = int(global_dof)
        epsilon = float(epsilon)
        key = (global_dof, epsilon)
        cached = self._cache.get(key)
        if cached is not None:
            self._hit_count += 1
            jvp, cached_row = cached
            return np.asarray(jvp, dtype=np.float64).copy(), {
                **cached_row,
                "cache_hit": True,
                "assembly_seconds": 0.0,
            }

        self._miss_count += 1
        trial_u = self._base_u.copy()
        trial_u[global_dof] += epsilon
        used_residual_only = False
        started = time.perf_counter()
        try:
            if not self._prefer_residual_only:
                raise TypeError("residual_only_disabled")
            _k, _f, trial_free, trial_residual, _rhs, trial_meta = self._assemble_residual(
                trial_u,
                residual_only=True,
                free_override=self._base_free,
                external_load_override=self._reference_f_ext,
            )
            used_residual_only = True
            self._residual_only_count += 1
        except TypeError:
            _k, _f, trial_free, trial_residual, _rhs, trial_meta = self._assemble_residual(
                trial_u,
                external_load_override=self._reference_f_ext,
            )
            self._full_assembly_count += 1
        assembly_seconds = float(time.perf_counter() - started)
        self._assembly_seconds += assembly_seconds
        trial_free_idx = np.asarray(trial_free, dtype=np.int64)
        free_stable = bool(
            trial_free_idx.shape == self._base_free.shape
            and np.array_equal(trial_free_idx, self._base_free)
        )
        row = {
            "global_dof": global_dof,
            "node_index": int(global_dof // 6),
            "dof_index": int(global_dof % 6),
            "epsilon_m": epsilon,
            "cache_hit": False,
            "residual_only_assembly": bool(used_residual_only),
            "assembly_seconds": assembly_seconds,
            "free_dof_set_stable": free_stable,
            "probe_direct_residual_inf_n": _max_abs(np.asarray(trial_residual, dtype=np.float64)),
        }
        if isinstance(trial_meta, dict):
            shell_meta = trial_meta.get("shell_meta")
            if isinstance(shell_meta, dict):
                row["shell_internal_force_cache_hit"] = bool(
                    shell_meta.get("shell_internal_force_cache_hit")
                )
            row["shell_operator_cache_size"] = trial_meta.get("shell_operator_cache_size")
        if not free_stable:
            self._unstable_free_count += 1
            row["reason"] = "free_dof_set_changed"
            return None, row

        jvp = (
            np.asarray(trial_residual, dtype=np.float64) - self._base_residual
        ) / epsilon
        row["jacobian_action_inf_n_per_m"] = _max_abs(jvp)
        row["jacobian_action_l2_n_per_m"] = (
            float(np.linalg.norm(jvp)) if jvp.size else 0.0
        )
        self._cache[key] = (np.asarray(jvp, dtype=np.float64).copy(), dict(row))
        return jvp, row

    def summary(self) -> dict[str, Any]:
        return {
            "request_count": int(self._request_count),
            "cache_hit_count": int(self._hit_count),
            "cache_miss_count": int(self._miss_count),
            "cache_size": int(len(self._cache)),
            "residual_only_assembly_count": int(self._residual_only_count),
            "full_assembly_count": int(self._full_assembly_count),
            "unstable_free_dof_probe_count": int(self._unstable_free_count),
            "assembly_seconds": float(self._assembly_seconds),
        }


def build_fd_jvp_submatrix(
    *,
    cache: ResidualJvpBatchCache,
    free: np.ndarray,
    target_rows: np.ndarray,
    support_cols: np.ndarray,
    epsilon: float,
) -> tuple[np.ndarray | None, list[dict[str, Any]], dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    targets = np.asarray(target_rows, dtype=np.int64)
    supports = np.asarray(support_cols, dtype=np.int64)
    submatrix = np.zeros((int(targets.size), int(supports.size)), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    stable = True
    for column_index, local_col in enumerate(supports.tolist()):
        global_dof = int(free_idx[int(local_col)])
        jvp, row = cache.evaluate_global_dof(
            global_dof=global_dof,
            epsilon=float(epsilon),
        )
        row["local_col"] = int(local_col)
        row["column_index"] = int(column_index)
        rows.append(row)
        if jvp is None:
            stable = False
            break
        submatrix[:, int(column_index)] = np.asarray(jvp, dtype=np.float64)[targets]
    summary = {
        **cache.summary(),
        "target_row_count": int(targets.size),
        "support_size": int(supports.size),
        "finite_difference_epsilon_m": float(epsilon),
        "free_dof_set_stable": bool(stable),
    }
    return (submatrix if stable else None), rows, summary
