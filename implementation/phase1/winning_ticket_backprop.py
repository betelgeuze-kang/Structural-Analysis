#!/usr/bin/env python3
"""Top-k weighted backprop with physics-guided orthogonal path branching.

Algorithm:
1) Scouting forward over K physically admissible branches with autograd OFF.
2) Physics loss evaluation and TOP-K branch selection.
3) Weighted targeted backprop over selected K branches.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

from md3bead_soa import run_relaxation_case
from orthogonal_krylov_projection import build_krylov_basis
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    build_story_load_profile,
    solve_nonlinear_frame,
)
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from solver_truthfulness_runtime import build_runtime_truthfulness, normalize_runtime_policy

EPS = 1e-12
REASONS = {
    "PASS": "top-k weighted targeted backprop completed",
    "ERR_TOPK_INVALID": "top-k must be >= 2 for weighted multi-branch training",
    "ERR_EMPTY_BASIS": "krylov basis is empty",
    "ERR_TARGETED_BACKPROP": "top-k weighted backprop failed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_RUNTIME_POLICY": "runtime policy requires production-seeded branch scoring but no production seed path was available",
}
INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out", "branches", "top_k", "temperature", "epsilon", "alpha", "lr"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
        "branches": {"type": "integer", "minimum": 2},
        "top_k": {"type": "integer", "minimum": 2},
        "temperature": {"type": "number", "exclusiveMinimum": 0.0},
        "epsilon": {"type": "number", "exclusiveMinimum": 0.0},
        "alpha": {"type": "number", "exclusiveMinimum": 0.0},
        "lr": {"type": "number", "exclusiveMinimum": 0.0},
        "runtime_mode": {
            "type": "string",
            "enum": ["auto", "reduced-order", "production-seeded"],
        },
    },
}


def _runtime_truthfulness(*, runtime_mode: str, production_seed_runtime: dict | None = None) -> dict:
    return build_runtime_truthfulness(
        path_role="top_level_training_eval_branch_selection",
        reduced_kind="explicit_reduced_order_relaxation_branching",
        reduced_backend="md3bead_soa_relaxation",
        reduced_reason="explicit reduced-order physical relaxation path declared without surrogate runtime markers",
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
    story_k = [82_000.0 + 7_500.0 * residual_mag[i % len(residual_mag)] + 1_250.0 * i for i in range(story_count)]
    story_h = [3.2 + 0.08 * i for i in range(story_count)]
    story_axial = [180_000.0 + 26_000.0 * i for i in range(story_count)]
    story_yield = [0.012 + 0.001 * (i % 3) for i in range(story_count)]
    base_shear_n = max(85_000.0, 24_000.0 * sum(residual_mag) * max(0.15, float(alpha)))
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
                max_iter=48,
                hardening_ratio=0.06,
                pdelta_factor=1.08,
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


def _operator_matrix() -> list[list[float]]:
    return [
        [4.0, -1.0, 0.0, 0.0, 0.0, 0.0],
        [-1.0, 4.0, -1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 4.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 4.0, -1.0, 0.0],
        [0.0, 0.0, 0.0, -1.0, 4.0, -1.0],
        [0.0, 0.0, 0.0, 0.0, -1.0, 4.0],
    ]


def _l2(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _simulate_loss(
    theta: list[float],
    residual: list[float],
    alpha: float,
    frame_seed: dict | None = None,
) -> tuple[list[float], float, float, float, dict]:
    # Branch scoring now uses explicit 3-bead SoA relaxation instead of algebraic surrogate updates.
    seed = frame_seed if isinstance(frame_seed, dict) else {}
    drive = abs(sum((t * r) for t, r in zip(theta, residual))) * float(alpha)
    drive += 180.0 * abs(float(seed.get("top_displacement_m", 0.0) or 0.0))
    decay_hint = max(0.90, min(0.985, 0.965 - 0.01 * (sum(theta) / max(len(theta), 1))))
    decay_hint -= min(0.02, 0.0015 * float(seed.get("plastic_story_count", 0) or 0))
    decay_hint = max(0.90, min(0.985, decay_hint))
    node_count = max(18, min(96, 20 + int(abs(residual[3]) + abs(residual[4]) + abs(residual[5]))))
    md = run_relaxation_case(
        node_count=node_count,
        base_force=max(60.0, min(320.0, 80.0 + 5.0 * drive)),
        max_steps=96,
        tol=5e-3,
        decay_hint=float(decay_hint),
        dt=0.0018,
    )

    # Keep branch update vector for backprop target alignment.
    gain = -float(alpha) / max(
        1.0,
        float(md.get("final_force_norm", 1.0)),
        1.0 + 1_000.0 * float(seed.get("residual_inf", 0.0) or 0.0),
    )
    delta_u = [gain * t * r for t, r in zip(theta, residual)]
    residual_next = [r + du for r, du in zip(residual, delta_u)]
    eq_norm = max(float(md.get("final_force_norm", 0.0)), _l2(residual_next))
    energy = float(md.get("potential_energy", 0.0)) + float(md.get("kinetic_energy", 0.0))
    energy += 0.0025 * float(seed.get("base_shear_kn", 0.0) or 0.0)
    temperature = float(md.get("system_temperature", 0.0))
    loss = eq_norm + 0.03 * math.log1p(max(0.0, energy)) + 0.002 * max(0.0, temperature)
    return delta_u, eq_norm, energy, loss, {
        "max_unbalanced_force": float(md.get("max_unbalanced_force", 0.0)),
        "kinetic_energy": float(md.get("kinetic_energy", 0.0)),
        "potential_energy": float(md.get("potential_energy", 0.0)),
        "system_temperature": float(temperature),
        "model": str(md.get("model", "3bead_ca_sc_cb")),
        "steps": int(md.get("steps", 0)),
        "production_seed_applied": bool(seed),
        "production_seed_top_displacement_m": float(seed.get("top_displacement_m", 0.0) or 0.0),
    }


def _softmax(xs: list[float]) -> list[float]:
    if not xs:
        return []
    m = max(xs)
    exps = [math.exp(x - m) for x in xs]
    s = sum(exps)
    if s <= EPS:
        return [1.0 / len(xs) for _ in xs]
    return [e / s for e in exps]


def run(
    branches: int,
    top_k: int,
    temperature: float,
    epsilon: float,
    alpha: float,
    lr: float,
    runtime_mode: str = "auto",
) -> dict:
    normalized_runtime_mode = normalize_runtime_policy(runtime_mode)
    try:
        frame_seed, seed_runtime = _maybe_frame_seed(
            [0.0, 0.0, 0.0, 11.0, -3.0, 2.0],
            alpha,
            normalized_runtime_mode,
        )
    except RuntimeError:
        return {
            "schema_version": "1.1",
            "run_id": "topk-weighted-backprop",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": _runtime_truthfulness(runtime_mode=normalized_runtime_mode),
            "contract_pass": False,
            "reason_code": "ERR_RUNTIME_POLICY",
            "reason": REASONS["ERR_RUNTIME_POLICY"],
        }
    runtime_truthfulness = _runtime_truthfulness(
        runtime_mode=normalized_runtime_mode,
        production_seed_runtime=seed_runtime if bool(seed_runtime and seed_runtime.get("production_kernel_path", False)) else None,
    )
    if not bool(runtime_truthfulness.get("runtime_policy_satisfied", True)):
        return {
            "schema_version": "1.1",
            "run_id": "topk-weighted-backprop",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": runtime_truthfulness,
            "contract_pass": False,
            "reason_code": "ERR_RUNTIME_POLICY",
            "reason": REASONS["ERR_RUNTIME_POLICY"],
        }
    if top_k < 2:
        return {
            "schema_version": "1.1",
            "run_id": "topk-weighted-backprop",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": runtime_truthfulness,
            "contract_pass": False,
            "reason_code": "ERR_TOPK_INVALID",
            "reason": REASONS["ERR_TOPK_INVALID"],
        }

    residual = [0.0, 0.0, 0.0, 11.0, -3.0, 2.0]
    theta_init = [1.0, 0.8, 0.7, 1.2, 0.9, 0.6]
    a = _operator_matrix()

    basis = build_krylov_basis(
        a,
        residual,
        m=max(2, branches, top_k),
        operator_source="matrix",
        operator_cmd=None,
        reorth_passes=2,
    )
    if not basis:
        return {
            "schema_version": "1.1",
            "run_id": "topk-weighted-backprop",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": runtime_truthfulness,
            "contract_pass": False,
            "reason_code": "ERR_EMPTY_BASIS",
            "reason": "krylov basis is empty",
        }

    # Stage-1 scouting: autograd OFF conceptually
    scouting = []
    for idx, q in enumerate(basis[:branches]):
        theta_i = [t + epsilon * qi for t, qi in zip(theta_init, q)]
        delta_u, eq_norm, energy, loss, md = _simulate_loss(theta_i, residual, alpha, frame_seed=frame_seed)
        scouting.append({
            "branch_id": idx,
            "theta": theta_i,
            "delta_u": delta_u,
            "equilibrium_norm": eq_norm,
            "energy_proxy": energy,
            "max_unbalanced_force": float(md["max_unbalanced_force"]),
            "system_temperature": float(md["system_temperature"]),
            "physical_model": str(md["model"]),
            "production_seed_applied": bool(md["production_seed_applied"]),
            "loss": loss,
        })

    sorted_candidates = sorted(scouting, key=lambda x: x["loss"])
    k = min(max(2, top_k), len(sorted_candidates))
    selected = sorted_candidates[:k]
    logits = [-(c["loss"] / max(float(temperature), EPS)) for c in selected]
    weights = _softmax(logits)

    torch_available = True
    backprop_ok = False
    theta_after = theta_init[:]
    weighted_loss_before = float(sum(w * c["loss"] for w, c in zip(weights, selected)))
    weighted_loss_after = weighted_loss_before
    selected_branch_ids = [int(c["branch_id"]) for c in selected]
    selected_losses = [float(c["loss"]) for c in selected]

    try:
        import torch  # type: ignore

        theta = torch.tensor(theta_init, dtype=torch.float32, requires_grad=True)
        r = torch.tensor(residual, dtype=torch.float32)

        total_loss = 0.0
        for w, cand in zip(weights, selected):
            q = torch.tensor(basis[int(cand["branch_id"])], dtype=torch.float32)
            theta_k = theta + float(epsilon) * q
            delta = -(float(alpha) * theta_k * r)
            residual_next = r + delta
            eq_norm = torch.sqrt(torch.sum(residual_next * residual_next) + 1e-12)
            energy = 0.5 * torch.sum(delta * delta)
            loss_k = eq_norm + 0.1 * energy
            total_loss = total_loss + float(w) * loss_k

        total_loss.backward()
        with torch.no_grad():
            if theta.grad is None:
                raise RuntimeError("theta.grad is None")
            theta_new = theta - float(lr) * theta.grad
        theta_after = [float(v) for v in theta_new]
        weighted_loss_after = float(total_loss.detach().item())
        backprop_ok = True
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.1",
            "run_id": "topk-weighted-backprop",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "algorithm": "topk_weighted_backprop_physics_guided_orthogonal_branching",
            "runtime_truthfulness": runtime_truthfulness,
            "contract_pass": False,
            "uses_backprop": True,
            "reason_code": "ERR_TARGETED_BACKPROP",
            "reason": f"{REASONS['ERR_TARGETED_BACKPROP']}: {exc}",
            "selection": {
                "strategy": "topk_weighted_backprop",
                "top_k": int(k),
                "selected_branch_ids": selected_branch_ids,
                "selected_losses": selected_losses,
                "normalized_weights": weights,
            },
            "targeted_backprop": {
                "autograd_enabled": True,
                "weighted_aggregation": True,
                "graph_count": int(k),
                "torch_available": torch_available,
                "success": False,
            },
        }

    contract_pass = bool(
        backprop_ok
        and len(selected_branch_ids) == k
        and k >= 2
        and abs(sum(weights) - 1.0) <= 1e-6
    )
    reason_code = "PASS" if contract_pass else "ERR_TARGETED_BACKPROP"
    reason = REASONS["PASS"] if contract_pass else REASONS["ERR_TARGETED_BACKPROP"]

    return {
        "schema_version": "1.1",
        "run_id": "topk-weighted-backprop",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "topk_weighted_backprop_physics_guided_orthogonal_branching",
        "runtime_truthfulness": runtime_truthfulness,
        "scouting": {
            "branches": len(scouting),
            "autograd_enabled": False,
            "candidates": scouting,
        },
        "selection": {
            "strategy": "topk_weighted_backprop",
            "top_k": int(k),
            "selected_branch_ids": selected_branch_ids,
            "selected_losses": selected_losses,
            "normalized_weights": weights,
            "discarded_branches": max(0, len(scouting) - k),
            "weighted_loss_before_backprop": weighted_loss_before,
        },
        "targeted_backprop": {
            "autograd_enabled": True,
            "weighted_aggregation": True,
            "graph_count": int(k),
            "torch_available": torch_available,
            "weighted_loss_after_backprop": weighted_loss_after,
            "success": backprop_ok,
        },
        "theta_before": theta_init,
        "theta_after": theta_after,
        "production_seed": frame_seed,
        "contract_pass": contract_pass,
        "uses_backprop": True,
        "reason_code": reason_code,
        "reason": reason,
    }


def main() -> None:
    logger = get_logger("phase1.winning_ticket_backprop")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/winning_ticket_backprop_report.json")
    parser.add_argument("--branches", type=int, default=16)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.25)
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--runtime-mode", choices=["auto", "reduced-order", "production-seeded"], default="auto")
    args = parser.parse_args()

    input_payload = {
        "out": str(args.out),
        "branches": int(args.branches),
        "top_k": int(args.top_k),
        "temperature": float(args.temperature),
        "epsilon": float(args.epsilon),
        "alpha": float(args.alpha),
        "lr": float(args.lr),
        "runtime_mode": str(args.runtime_mode),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.winning_ticket_backprop")
        if int(args.top_k) > int(args.branches):
            raise ValueError("top_k cannot exceed branches")
        log_event(logger, logging.INFO, "winning_ticket.start", inputs=input_payload)
        report = run(
            branches=args.branches,
            top_k=args.top_k,
            temperature=args.temperature,
            epsilon=args.epsilon,
            alpha=args.alpha,
            lr=args.lr,
            runtime_mode=args.runtime_mode,
        )
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "winning_ticket.completed",
            contract_pass=bool(report.get("contract_pass", False)),
            reason_code=str(report.get("reason_code", "")),
        )
        print(f"Wrote winning ticket backprop report: {out}")
        if not report.get("contract_pass", False):
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        report = {
            "schema_version": "1.1",
            "run_id": "topk-weighted-backprop",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_truthfulness": _runtime_truthfulness(runtime_mode=str(args.runtime_mode)),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "winning_ticket.invalid_input", error=str(exc))
        print(f"Wrote winning ticket backprop report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
