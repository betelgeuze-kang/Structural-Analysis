#!/usr/bin/env python3
"""Derivative-free Physics-Guided Orthogonal Branching (PGOB).

Implements path-branching learning/inference without backpropagation:
- construct orthogonal physical basis from residual space
- evaluate K physically admissible branch candidates by forward-only scoring
- choose best branch and evolve parameters in derivative-free manner
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from orthogonal_krylov_projection import build_krylov_basis, dot


SCHEMA_VERSION = "1.0"


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


def simulate_forward(theta: list[float], residual: list[float], alpha: float) -> tuple[list[float], float, float]:
    """Forward-only residual correction surrogate.

    No gradients/backprop are used. Candidate quality combines:
    - equilibrium residual norm
    - potential-energy proxy
    """
    delta_u = [-(alpha * t * r) for t, r in zip(theta, residual)]
    residual_next = [r + du for r, du in zip(residual, delta_u)]
    eq_norm = l2(residual_next)
    energy_proxy = 0.5 * sum((du * du) for du in delta_u)
    return delta_u, eq_norm, energy_proxy


def run(branch_k: int, epsilon: float, alpha: float, mode: str) -> dict:
    residual = [0.0, 0.0, 0.0, 11.0, -3.0, 2.0]
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
            "branch_count": 0,
            "reason_code": "ERR_EMPTY_BASIS",
            "contract_pass": False,
        }

    candidates = []
    for idx, q in enumerate(basis[:branch_k]):
        theta_i = [t + epsilon * qi for t, qi in zip(theta, q)]
        delta_u, eq_norm, energy = simulate_forward(theta_i, residual, alpha=alpha)
        candidates.append(
            {
                "branch_id": idx,
                "theta": theta_i,
                "delta_u": delta_u,
                "equilibrium_norm": eq_norm,
                "energy_proxy": energy,
                "loss": eq_norm + 0.1 * energy,
            }
        )

    best = min(candidates, key=lambda c: c["loss"])
    theta_next = best["theta"]
    # branch-path inference: use best physically admissible branch directly.
    u_lf = [0.0, 0.0, 0.0, 0.0012, -0.0007, 0.0003]
    u_final = [u + du for u, du in zip(u_lf, best["delta_u"])]

    # Bifurcation confidence: spread between best and second-best branch
    losses = sorted(c["loss"] for c in candidates)
    bifurcation_margin = 0.0 if len(losses) < 2 else losses[1] - losses[0]

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": "pgob-branching",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "algorithm": "physics_guided_orthogonal_branching_derivative_free",
        "uses_backprop": False,
        "branch_count": len(candidates),
        "epsilon": epsilon,
        "alpha": alpha,
        "basis_dim": len(basis),
        "best_branch_id": best["branch_id"],
        "bifurcation_margin": bifurcation_margin,
        "theta_before": theta,
        "theta_after": theta_next,
        "u_final": u_final,
        "candidates": candidates,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "forward-only derivative-free physical path branching completed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/physics_branching_report.json")
    parser.add_argument("--branches", type=int, default=4)
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument("--mode", choices=["train", "infer"], default="train")
    args = parser.parse_args()

    report = run(branch_k=args.branches, epsilon=args.epsilon, alpha=args.alpha, mode=args.mode)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote physics branching report: {out}")
    if not report.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
