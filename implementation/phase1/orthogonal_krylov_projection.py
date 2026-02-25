#!/usr/bin/env python3
"""Derivative-free projection update using iterative orthogonal basis growth.

Avoids explicit matrix inverse by constructing an orthonormal basis from
residual-informed vectors (Krylov-like sequence scaffold) and projecting onto it.
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
import subprocess
from pathlib import Path


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(v: list[float]) -> float:
    return math.sqrt(max(dot(v, v), 0.0))


def axpy(a: float, x: list[float], y: list[float]) -> list[float]:
    return [a * xi + yi for xi, yi in zip(x, y)]


def mat_vec(a: list[list[float]], x: list[float]) -> list[float]:
    return [dot(row, x) for row in a]


def _run_json_cmd(command: str, payload: dict) -> dict:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def apply_operator(x: list[float], operator_source: str, operator_cmd: str | None, a: list[list[float]]) -> list[float]:
    if operator_source == "matrix":
        return mat_vec(a, x)
    if operator_source == "hook":
        if not operator_cmd:
            raise ValueError("operator_source=hook requires --operator-cmd")
        res = _run_json_cmd(operator_cmd, {"action": "av_operator", "vector": x})
        return [float(v) for v in res["result"]]
    raise ValueError(f"unsupported operator source: {operator_source}")


def normalize(v: list[float]) -> list[float]:
    n = norm(v)
    return [vi / n for vi in v] if n > 1e-12 else v[:]


def orthogonalize(v: list[float], basis: list[list[float]], reorth_passes: int = 1) -> list[float]:
    w = v[:]
    for _ in range(max(1, reorth_passes)):
        for q in basis:
            c = dot(w, q)
            w = axpy(-c, q, w)
    return w


def build_krylov_basis(a: list[list[float]], r0: list[float], m: int, operator_source: str, operator_cmd: str | None, reorth_passes: int) -> list[list[float]]:
    basis: list[list[float]] = []
    v = normalize(r0)
    if norm(v) <= 1e-12:
        return basis
    basis.append(v)
    for _ in range(1, m):
        w = apply_operator(basis[-1], operator_source, operator_cmd, a)
        w = orthogonalize(w, basis, reorth_passes=reorth_passes)
        nw = norm(w)
        if nw <= 1e-10:
            break
        basis.append([wi / nw for wi in w])
    return basis


def project_onto_basis(v: list[float], basis: list[list[float]]) -> list[float]:
    out = [0.0 for _ in v]
    for q in basis:
        c = dot(v, q)
        out = axpy(c, q, out)
    return out


def orthogonality_error(basis: list[list[float]]) -> float:
    if not basis:
        return 0.0
    max_err = 0.0
    for i, qi in enumerate(basis):
        for j, qj in enumerate(basis):
            val = dot(qi, qj)
            target = 1.0 if i == j else 0.0
            max_err = max(max_err, abs(val - target))
    return max_err


def run(alpha: float, m: int, operator_source: str = "matrix", operator_cmd: str | None = None, reduction_threshold: float = 0.98, ortho_threshold: float = 1e-6, reorth_passes: int = 2, max_reorth_passes: int = 5) -> dict:
    # SPD-like toy operator (stand-in for K-like system matrix action)
    a = [
        [4.0, -1.0, 0.0, 0.0, 0.0, 0.0],
        [-1.0, 4.0, -1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 4.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 4.0, -1.0, 0.0],
        [0.0, 0.0, 0.0, -1.0, 4.0, -1.0],
        [0.0, 0.0, 0.0, 0.0, -1.0, 4.0],
    ]
    u_lf = [0.0, 0.0, 0.0, 0.0012, -0.0007, 0.0003]
    r = [0.0, 0.0, 0.0, 11.0, -3.0, 2.0]

    used_reorth = reorth_passes
    basis = build_krylov_basis(a, r, m=m, operator_source=operator_source, operator_cmd=operator_cmd, reorth_passes=used_reorth)
    ortho_err = orthogonality_error(basis)
    while ortho_err > ortho_threshold and used_reorth < max_reorth_passes:
        used_reorth += 1
        basis = build_krylov_basis(a, r, m=m, operator_source=operator_source, operator_cmd=operator_cmd, reorth_passes=used_reorth)
        ortho_err = orthogonality_error(basis)

    r_proj = project_onto_basis(r, basis)

    before = norm(r)
    after = norm([ri - rpi for ri, rpi in zip(r, r_proj)])
    u_final = [u - alpha * rp for u, rp in zip(u_lf, r_proj)]
    residual_after_update = [ri - alpha * rpi for ri, rpi in zip(r, r_proj)]

    ratio = 0.0 if before == 0 else after / before

    if ortho_err <= ortho_threshold:
        reason_code = "PASS"
        suggested_reorth_pass = used_reorth
    elif ortho_err <= ortho_threshold * 10:
        reason_code = "ORTHO_NEAR_THRESHOLD"
        suggested_reorth_pass = min(max_reorth_passes, used_reorth + 1)
    else:
        reason_code = "ORTHO_FAIL_REORTH_REQUIRED"
        suggested_reorth_pass = min(max_reorth_passes, max(used_reorth + 1, 3))

    return {
        "alpha": alpha,
        "krylov_dim": len(basis),
        "operator_source": operator_source,
        "residual_norm_before": before,
        "residual_norm_after_projection_complement": after,
        "krylov_residual_after_update": norm(residual_after_update),
        "projection_quality": {
            "reduction_ratio": ratio,
            "threshold": reduction_threshold,
            "projected_not_worse": ratio <= 1.0 + 1e-9,
            "threshold_pass": ratio <= reduction_threshold,
            "orthogonality_error": ortho_err,
            "orthogonality_threshold": ortho_threshold,
            "orthogonality_pass": ortho_err <= ortho_threshold,
            "reorth_passes": used_reorth,
            "max_reorth_passes": max_reorth_passes,
            "reason_code": reason_code,
            "suggested_reorth_pass": suggested_reorth_pass,
        },
        "u_final": u_final,
        "basis": basis,
        "notes": "Inverse-free iterative projection scaffold (GMRES/Krylov style).",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/krylov_projection_report.json")
    parser.add_argument("--alpha", type=float, default=0.35)
    parser.add_argument("--m", type=int, default=4)
    parser.add_argument("--operator-source", choices=["matrix", "hook"], default="matrix")
    parser.add_argument("--operator-cmd", help="JSON stdin/stdout command for A·v operator when --operator-source=hook")
    parser.add_argument("--reduction-threshold", type=float, default=0.98)
    parser.add_argument("--orthogonality-threshold", type=float, default=1e-6)
    parser.add_argument("--reorth-passes", type=int, default=2)
    parser.add_argument("--max-reorth-passes", type=int, default=5)
    args = parser.parse_args()

    report = run(
        alpha=args.alpha,
        m=args.m,
        operator_source=args.operator_source,
        operator_cmd=args.operator_cmd,
        reduction_threshold=args.reduction_threshold,
        ortho_threshold=args.orthogonality_threshold,
        reorth_passes=args.reorth_passes,
        max_reorth_passes=args.max_reorth_passes,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote krylov projection report: {out}")


if __name__ == "__main__":
    main()
