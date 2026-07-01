#!/usr/bin/env python3
"""Derivative-free Physics-Guided Orthogonal Branching (PGOB)."""

from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

from md3bead_soa import run_relaxation_case
from orthogonal_krylov_projection import build_krylov_basis, dot
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    build_story_load_profile,
    solve_nonlinear_frame,
)
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from solver_truthfulness_runtime import build_runtime_truthfulness, normalize_runtime_policy


SCHEMA_VERSION = "1.0"
REASONS = {
    "PASS": "forward-only derivative-free physical path branching completed",
    "ERR_EMPTY_BASIS": "krylov basis is empty",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_RUNTIME_POLICY": "runtime policy requires production-seeded branching but no production seed path was available",
}
INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out", "branches", "epsilon", "alpha", "mode"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
        "branches": {"type": "integer", "minimum": 2},
        "epsilon": {"type": "number", "exclusiveMinimum": 0.0},
        "alpha": {"type": "number", "exclusiveMinimum": 0.0},
        "mode": {"type": "string", "enum": ["train", "infer"]},
        "runtime_mode": {
            "type": "string",
            "enum": ["auto", "reduced-order", "production-seeded"],
        },
    },
}


def _runtime_truthfulness(*, runtime_mode: str, production_seed_runtime: dict | None = None) -> dict:
    return build_runtime_truthfulness(
        path_role="top_level_training_eval_branching",
        reduced_kind="explicit_reduced_order_physical_branching",
        reduced_backend="structural_reduced_order_relaxation",
        reduced_reason="explicit reduced-order physical branching path declared without surrogate runtime markers",
        runtime_policy=runtime_mode,
        production_seed_runtime=production_seed_runtime,
        production_seed_label="rust_nonlinear_frame_gpu_seed",
        execution_backend="cpu",
    )


def _maybe_frame_seed(residual: list[float], alpha: float, runtime_mode: str) -> tuple[dict | None, dict | None]:
    policy = normalize_runtime_policy(runtime_mode)
    if policy == "reduced-order":
        return None, None

    story_count = max(4, len(residual))
    residual_mag = [abs(float(x)) for x in residual]
    story_k = [76_000.0 + 6_800.0 * residual_mag[i % len(residual_mag)] + 1_100.0 * i for i in range(story_count)]
    story_h = [3.0 + 0.06 * i for i in range(story_count)]
    story_axial = [165_000.0 + 24_000.0 * i for i in range(story_count)]
    story_yield = [0.013 + 0.001 * (i % 2) for i in range(story_count)]
    base_shear_n = max(72_000.0, 20_000.0 * sum(residual_mag) * max(0.15, float(alpha)))
    floor_load_n = build_story_load_profile(story_count, base_shear_n, mode="triangular")

    try:
        seed_result = solve_nonlinear_frame(
            story_k_n_per_m=story_k,
            story_h_m=story_h,
            story_axial_n=story_axial,
            story_yield_drift_m=story_yield,
            floor_load_n=floor_load_n,
            cfg=RustNonlinearFrameConfig(
                tolerance=1e-7,
                max_iter=44,
                hardening_ratio=0.05,
                pdelta_factor=1.05,
            ),
            keep_device_artifacts=False,
        )
    except Exception as exc:  # noqa: BLE001
        if policy == "production-seeded":
            raise RuntimeError(REASONS["ERR_RUNTIME_POLICY"]) from exc
        return None, None

    seed_runtime = seed_result.get("runtime") if isinstance(seed_result.get("runtime"), dict) else {}
    if not bool(seed_runtime.get("production_kernel_path", False)):
        if policy == "production-seeded":
            raise RuntimeError(REASONS["ERR_RUNTIME_POLICY"])
        return None, seed_runtime

    return {
        "top_displacement_m": float(seed_result.get("top_displacement_m", 0.0) or 0.0),
        "max_abs_displacement_m": float(seed_result.get("max_abs_displacement_m", 0.0) or 0.0),
        "base_shear_kn": float(seed_result.get("base_shear_kn", 0.0) or 0.0),
        "plastic_story_count": int(seed_result.get("plastic_story_count", 0) or 0),
        "residual_inf": float(seed_result.get("residual_inf", 0.0) or 0.0),
    }, seed_runtime


def l2(v: list[float]) -> float:
    return math.sqrt(max(sum(x * x for x in v), 0.0))


def _operator_matrix() -> list[list[float]]:
    return [
        [4.0, -1.0, 0.0, 0.0, 0.0, 0.0],
        [-1.0, 4.0, -1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 4.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 4.0, -1.0, 0.0],
        [0.0, 0.0, 0.0, -1.0, 4.0, -1.0],
        [0.0, 0.0, 0.0, 0.0, -1.0, 4.0],
    ]


def mat_vec(a: list[list[float]], x: list[float]) -> list[float]:
    return [dot(row, x) for row in a]


def simulate_forward(
    theta: list[float],
    residual: list[float],
    alpha: float,
    frame_seed: dict | None = None,
) -> tuple[list[float], float, float, dict]:
    """Forward-only residual correction with explicit 3-bead relaxation scoring."""
    seed = frame_seed if isinstance(frame_seed, dict) else {}
    drive = abs(sum((t * r) for t, r in zip(theta, residual))) * float(alpha)
    drive += 150.0 * abs(float(seed.get("top_displacement_m", 0.0) or 0.0))
    md = run_relaxation_case(
        node_count=max(16, min(84, 18 + int(abs(residual[3]) + abs(residual[4]) + abs(residual[5])))),
        base_force=max(70.0, min(300.0, 90.0 + 4.5 * drive)),
        max_steps=88,
        tol=5e-3,
        decay_hint=max(0.91, min(0.975, 0.96 - 0.002 * float(seed.get("plastic_story_count", 0) or 0))),
        dt=0.0019,
    )

    gain = -float(alpha) / max(
        1.0,
        float(md.get("final_force_norm", 1.0)),
        1.0 + 1_000.0 * float(seed.get("residual_inf", 0.0) or 0.0),
    )
    delta_u = [gain * t * r for t, r in zip(theta, residual)]
    residual_next = [r + du for r, du in zip(residual, delta_u)]
    eq_norm = max(l2(residual_next), float(md.get("final_force_norm", 0.0)))
    energy_proxy = float(md.get("potential_energy", 0.0)) + float(md.get("kinetic_energy", 0.0))
    energy_proxy += 0.002 * float(seed.get("base_shear_kn", 0.0) or 0.0)
    return delta_u, eq_norm, energy_proxy, {
        "max_unbalanced_force": float(md.get("max_unbalanced_force", 0.0)),
        "system_temperature": float(md.get("system_temperature", 0.0)),
        "model": str(md.get("model", "3bead_ca_sc_cb")),
        "production_seed_applied": bool(seed),
    }


def run(branch_k: int, epsilon: float, alpha: float, mode: str, runtime_mode: str = "auto") -> dict:
    normalized_runtime_mode = normalize_runtime_policy(runtime_mode)
    residual = [0.0, 0.0, 0.0, 11.0, -3.0, 2.0]
    try:
        frame_seed, seed_runtime = _maybe_frame_seed(residual, alpha, normalized_runtime_mode)
    except RuntimeError:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": "pgob-branching",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "runtime_truthfulness": _runtime_truthfulness(runtime_mode=normalized_runtime_mode),
            "branch_count": 0,
            "reason_code": "ERR_RUNTIME_POLICY",
            "contract_pass": False,
            "reason": REASONS["ERR_RUNTIME_POLICY"],
        }
    runtime_truthfulness = _runtime_truthfulness(
        runtime_mode=normalized_runtime_mode,
        production_seed_runtime=seed_runtime if bool(seed_runtime and seed_runtime.get("production_kernel_path", False)) else None,
    )
    if not bool(runtime_truthfulness.get("runtime_policy_satisfied", True)):
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": "pgob-branching",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "runtime_truthfulness": runtime_truthfulness,
            "branch_count": 0,
            "reason_code": "ERR_RUNTIME_POLICY",
            "contract_pass": False,
            "reason": REASONS["ERR_RUNTIME_POLICY"],
        }
    theta = [1.0, 0.8, 0.7, 1.2, 0.9, 0.6]
    a = _operator_matrix()

    basis = build_krylov_basis(
        a,
        residual,
        m=max(2, branch_k),
        operator_source="matrix",
        operator_cmd=None,
        reorth_passes=2,
    )
    if not basis:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": "pgob-branching",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "runtime_truthfulness": runtime_truthfulness,
            "branch_count": 0,
            "reason_code": "ERR_EMPTY_BASIS",
            "contract_pass": False,
            "reason": REASONS["ERR_EMPTY_BASIS"],
        }

    candidates = []
    for idx, q in enumerate(basis[:branch_k]):
        theta_i = [t + epsilon * qi for t, qi in zip(theta, q)]
        delta_u, eq_norm, energy, md = simulate_forward(theta_i, residual, alpha=alpha, frame_seed=frame_seed)
        candidates.append(
            {
                "branch_id": idx,
                "theta": theta_i,
                "delta_u": delta_u,
                "equilibrium_norm": eq_norm,
                "energy_proxy": energy,
                "max_unbalanced_force": float(md["max_unbalanced_force"]),
                "system_temperature": float(md["system_temperature"]),
                "physical_model": str(md["model"]),
                "production_seed_applied": bool(md["production_seed_applied"]),
                "loss": eq_norm + 0.1 * energy,
            }
        )

    best = min(candidates, key=lambda c: c["loss"])
    theta_next = best["theta"]
    u_lf = [0.0, 0.0, 0.0, 0.0012, -0.0007, 0.0003]
    u_final = [u + du for u, du in zip(u_lf, best["delta_u"])]

    losses = sorted(c["loss"] for c in candidates)
    bifurcation_margin = 0.0 if len(losses) < 2 else losses[1] - losses[0]

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": "pgob-branching",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "algorithm": "physics_guided_orthogonal_branching_derivative_free",
        "runtime_truthfulness": runtime_truthfulness,
        "uses_backprop": False,
        "branch_count": len(candidates),
        "epsilon": epsilon,
        "alpha": alpha,
        "basis_dim": len(basis),
        "best_branch_id": best["branch_id"],
        "bifurcation_margin": bifurcation_margin,
        "theta_before": theta,
        "theta_after": theta_next,
        "production_seed": frame_seed,
        "u_final": u_final,
        "candidates": candidates,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": REASONS["PASS"],
    }


def main() -> None:
    logger = get_logger("phase1.physics_guided_branching")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/physics_branching_report.json")
    parser.add_argument("--branches", type=int, default=4)
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument("--mode", choices=["train", "infer"], default="train")
    parser.add_argument("--runtime-mode", choices=["auto", "reduced-order", "production-seeded"], default="auto")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    input_payload = {
        "out": str(args.out),
        "branches": int(args.branches),
        "epsilon": float(args.epsilon),
        "alpha": float(args.alpha),
        "mode": str(args.mode),
        "runtime_mode": str(args.runtime_mode),
    }
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.physics_guided_branching")
        log_event(logger, logging.INFO, "physics_branching.start", inputs=input_payload)
        report = run(
            branch_k=args.branches,
            epsilon=args.epsilon,
            alpha=args.alpha,
            mode=args.mode,
            runtime_mode=args.runtime_mode,
        )
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "physics_branching.completed",
            contract_pass=bool(report.get("contract_pass", False)),
            reason_code=str(report.get("reason_code", "")),
        )
        print(f"Wrote physics branching report: {out}")
        if not report.get("contract_pass", False):
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": "pgob-branching",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": _runtime_truthfulness(runtime_mode=str(args.runtime_mode)),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "physics_branching.invalid_input", error=str(exc))
        print(f"Wrote physics branching report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
