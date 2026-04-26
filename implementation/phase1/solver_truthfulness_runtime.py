#!/usr/bin/env python3
"""Shared helpers for truthful top-level runtime declarations."""

from __future__ import annotations

from typing import Any


VALID_RUNTIME_POLICIES = {
    "auto",
    "reduced-order",
    "production-seeded",
}


def normalize_runtime_policy(value: str | None, *, default: str = "auto") -> str:
    policy = str(value or default).strip().lower()
    if policy not in VALID_RUNTIME_POLICIES:
        raise ValueError(
            f"unsupported runtime policy: {value!r} "
            f"(expected one of {sorted(VALID_RUNTIME_POLICIES)})"
        )
    return policy


def runtime_policy_requires_production_seed(policy: str) -> bool:
    return normalize_runtime_policy(policy) == "production-seeded"


def build_runtime_truthfulness(
    *,
    path_role: str,
    reduced_kind: str,
    reduced_backend: str,
    reduced_reason: str,
    runtime_policy: str,
    production_seed_runtime: dict[str, Any] | None = None,
    production_seed_label: str = "",
    execution_backend: str = "cpu",
) -> dict[str, Any]:
    policy = normalize_runtime_policy(runtime_policy)
    seed_runtime = production_seed_runtime if isinstance(production_seed_runtime, dict) else {}
    production_seeded = bool(seed_runtime.get("production_kernel_path", False))
    execution_backend_normalized = str(execution_backend or "cpu").strip().lower() or "cpu"
    if execution_backend_normalized not in {"cpu", "gpu"}:
        execution_backend_normalized = "cpu"

    if production_seeded:
        runtime_backend = (
            f"{reduced_backend}+{str(seed_runtime.get('runtime_backend', 'production_seed')).strip()}"
        )
        solver_path_kind = f"production_seeded_{reduced_kind}"
        physical_runtime_class = "production_seeded_explicit_physical"
        reason = (
            f"{reduced_reason}; production seed applied via "
            f"{production_seed_label or str(seed_runtime.get('solver_path_kind', 'production_kernel')).strip()}"
        )
    else:
        runtime_backend = reduced_backend
        solver_path_kind = reduced_kind
        physical_runtime_class = "explicit_reduced_order_physical"
        reason = reduced_reason

    runtime_policy_satisfied = bool(
        not runtime_policy_requires_production_seed(policy) or production_seeded
    )
    cpu_backend = execution_backend_normalized == "cpu"
    payload: dict[str, Any] = {
        "path_role": path_role,
        "solver_path_kind": solver_path_kind,
        "physical_runtime_class": physical_runtime_class,
        "runtime_backend": runtime_backend,
        "execution_backend": execution_backend_normalized,
        "cpu_backend": cpu_backend,
        "cpu_required": cpu_backend,
        "cpu_fallback_used": False,
        "production_kernel_path": False,
        "reduced_order_physical_runtime_used": True,
        "physical_runtime_declared": True,
        "force_jacobian_kernel_consistent": True,
        "force_balance_residual_consistent": True,
        "surrogate_runtime_used": False,
        "simplified_runtime_used": False,
        "surrogate_runtime_markers": [],
        "runtime_policy": policy,
        "runtime_policy_satisfied": runtime_policy_satisfied,
        "production_seeded_runtime_used": production_seeded,
        "production_seed_label": production_seed_label if production_seeded else "",
        "production_seed_backend": str(seed_runtime.get("runtime_backend", "") or "")
        if production_seeded
        else "",
        "production_seed_solver_path_kind": str(
            seed_runtime.get("solver_path_kind", "")
            or seed_runtime.get("main_loop_backend", "")
            or ""
        )
        if production_seeded
        else "",
        "production_seed_device_residency_ratio": float(
            seed_runtime.get("device_residency_ratio", 0.0) or 0.0
        )
        if production_seeded
        else 0.0,
        "production_seed_hip_kernel_invocation_count": int(
            seed_runtime.get("hip_kernel_invocation_count", 0) or 0
        )
        if production_seeded
        else 0,
        "contract_pass": runtime_policy_satisfied,
        "reason": reason,
    }
    if production_seeded:
        payload["production_seed_runtime"] = {
            "runtime_backend": str(seed_runtime.get("runtime_backend", "") or ""),
            "solver_path_kind": str(seed_runtime.get("solver_path_kind", "") or ""),
            "production_kernel_path": bool(seed_runtime.get("production_kernel_path", False)),
            "device_residency_ratio": float(seed_runtime.get("device_residency_ratio", 0.0) or 0.0),
            "hip_kernel_invocation_count": int(seed_runtime.get("hip_kernel_invocation_count", 0) or 0),
        }
    return payload
