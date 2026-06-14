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
        batch_residual_evaluator: Callable[..., tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]] | None = None,
        batch_replay_backend: str = "cpu",
        hipcc: Any = None,
        force_rebuild_hip: bool = False,
    ) -> None:
        self._assemble_residual = assemble_residual
        self._base_u = np.asarray(base_u, dtype=np.float64)
        self._base_free = np.asarray(base_free, dtype=np.int64)
        self._base_residual = np.asarray(base_residual, dtype=np.float64)
        self._reference_f_ext = np.asarray(reference_f_ext, dtype=np.float64)
        self._prefer_residual_only = bool(prefer_residual_only)
        self._batch_residual_evaluator = batch_residual_evaluator
        self._batch_replay_backend = str(batch_replay_backend or "cpu")
        self._hipcc = hipcc
        self._force_rebuild_hip = bool(force_rebuild_hip)
        self._cache: dict[tuple[int, float], tuple[np.ndarray, dict[str, Any]]] = {}
        self._request_count = 0
        self._hit_count = 0
        self._miss_count = 0
        self._residual_only_count = 0
        self._full_assembly_count = 0
        self._unstable_free_count = 0
        self._assembly_seconds = 0.0
        self._batch_replay_count = 0
        self._batch_replay_state_count = 0
        self._batch_replay_seconds = 0.0
        self._batch_replay_fallback_count = 0
        self._batch_replay_backend_error = ""

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

    def evaluate_global_dofs_batch(
        self,
        *,
        global_dofs: list[int],
        epsilon: float,
        batch_chunk_size: int,
    ) -> list[tuple[np.ndarray | None, dict[str, Any]]]:
        if self._batch_residual_evaluator is None or int(batch_chunk_size) <= 1:
            return [
                self.evaluate_global_dof(global_dof=int(global_dof), epsilon=float(epsilon))
                for global_dof in global_dofs
            ]
        epsilon = float(epsilon)
        chunk_size = max(int(batch_chunk_size), 1)
        results: list[tuple[np.ndarray | None, dict[str, Any]] | None] = [None] * len(global_dofs)
        missing_indices: list[int] = []
        for index, raw_global_dof in enumerate(global_dofs):
            self._request_count += 1
            global_dof = int(raw_global_dof)
            key = (global_dof, epsilon)
            cached = self._cache.get(key)
            if cached is not None:
                self._hit_count += 1
                jvp, cached_row = cached
                results[index] = (
                    np.asarray(jvp, dtype=np.float64).copy(),
                    {**cached_row, "cache_hit": True, "assembly_seconds": 0.0},
                )
                continue
            self._miss_count += 1
            missing_indices.append(index)
        for start in range(0, len(missing_indices), chunk_size):
            chunk_indices = missing_indices[start : start + chunk_size]
            states = np.repeat(self._base_u[np.newaxis, :], len(chunk_indices), axis=0)
            for local_index, result_index in enumerate(chunk_indices):
                states[local_index, int(global_dofs[result_index])] += epsilon
            started = time.perf_counter()
            try:
                evaluator_kwargs: dict[str, Any] = {
                    "external_load_override": self._reference_f_ext,
                    "free_override": self._base_free,
                    "backend": self._batch_replay_backend,
                }
                if self._hipcc is not None:
                    evaluator_kwargs["hipcc"] = self._hipcc
                evaluator_kwargs["force_rebuild_hip"] = self._force_rebuild_hip
                trial_residual_batch, trial_free, _rhs, batch_meta = self._batch_residual_evaluator(
                    states,
                    **evaluator_kwargs,
                )
            except Exception as exc:  # pragma: no cover - recorded in probe JSON
                self._batch_replay_backend_error = str(exc)
                self._batch_replay_fallback_count += len(chunk_indices)
                self._request_count -= len(chunk_indices)
                self._miss_count -= len(chunk_indices)
                for result_index in chunk_indices:
                    results[result_index] = self.evaluate_global_dof(
                        global_dof=int(global_dofs[result_index]),
                        epsilon=epsilon,
                    )
                continue
            elapsed = float(time.perf_counter() - started)
            self._batch_replay_count += 1
            self._batch_replay_state_count += int(states.shape[0])
            self._batch_replay_seconds += elapsed
            trial_free_idx = np.asarray(trial_free, dtype=np.int64)
            free_stable = bool(
                trial_free_idx.shape == self._base_free.shape
                and np.array_equal(trial_free_idx, self._base_free)
            )
            residual_rows = np.asarray(trial_residual_batch, dtype=np.float64)
            for local_index, result_index in enumerate(chunk_indices):
                global_dof = int(global_dofs[result_index])
                row = {
                    "global_dof": global_dof,
                    "node_index": int(global_dof // 6),
                    "dof_index": int(global_dof % 6),
                    "epsilon_m": epsilon,
                    "cache_hit": False,
                    "residual_only_assembly": bool(batch_meta.get("residual_only_assembly", True)),
                    "assembly_seconds": elapsed / max(int(states.shape[0]), 1),
                    "batch_replay": True,
                    "batch_replay_index": int(local_index),
                    "batch_replay_size": int(states.shape[0]),
                    "batch_replay_backend": batch_meta.get("residual_batch_backend"),
                    "hip_full_residual_batch_replay": bool(batch_meta.get("hip_full_residual_batch_replay")),
                    "free_dof_set_stable": free_stable,
                    "probe_direct_residual_inf_n": (
                        _max_abs(residual_rows[local_index])
                        if residual_rows.ndim == 2 and local_index < int(residual_rows.shape[0])
                        else 0.0
                    ),
                    "batch_meta": batch_meta,
                }
                if not free_stable:
                    self._unstable_free_count += 1
                    row["reason"] = "free_dof_set_changed"
                    results[result_index] = (None, row)
                    continue
                trial_residual = np.asarray(residual_rows[local_index], dtype=np.float64)
                jvp = (trial_residual - self._base_residual) / epsilon
                row["jacobian_action_inf_n_per_m"] = _max_abs(jvp)
                row["jacobian_action_l2_n_per_m"] = (
                    float(np.linalg.norm(jvp)) if jvp.size else 0.0
                )
                self._cache[(global_dof, epsilon)] = (
                    np.asarray(jvp, dtype=np.float64).copy(),
                    dict(row),
                )
                results[result_index] = (jvp, row)
        return [
            result
            if result is not None
            else self.evaluate_global_dof(global_dof=int(global_dofs[index]), epsilon=epsilon)
            for index, result in enumerate(results)
        ]

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
            "batch_residual_replay_enabled": self._batch_residual_evaluator is not None,
            "batch_replay_backend": self._batch_replay_backend,
            "batch_replay_count": int(self._batch_replay_count),
            "batch_replay_state_count": int(self._batch_replay_state_count),
            "batch_replay_seconds": float(self._batch_replay_seconds),
            "batch_replay_fallback_count": int(self._batch_replay_fallback_count),
            "batch_replay_backend_error": self._batch_replay_backend_error,
        }


def build_fd_jvp_submatrix(
    *,
    cache: ResidualJvpBatchCache,
    free: np.ndarray,
    target_rows: np.ndarray,
    support_cols: np.ndarray,
    epsilon: float,
    batch_chunk_size: int = 1,
) -> tuple[np.ndarray | None, list[dict[str, Any]], dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    targets = np.asarray(target_rows, dtype=np.int64)
    supports = np.asarray(support_cols, dtype=np.int64)
    submatrix = np.zeros((int(targets.size), int(supports.size)), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    stable = True
    global_dofs = [int(free_idx[int(local_col)]) for local_col in supports.tolist()]
    jvp_rows = cache.evaluate_global_dofs_batch(
        global_dofs=global_dofs,
        epsilon=float(epsilon),
        batch_chunk_size=int(batch_chunk_size),
    )
    for column_index, (local_col, jvp_row) in enumerate(
        zip(supports.tolist(), jvp_rows, strict=False)
    ):
        jvp, row = jvp_row
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
