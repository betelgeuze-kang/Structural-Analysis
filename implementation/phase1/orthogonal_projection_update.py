#!/usr/bin/env python3
"""Priority-1 implementation: physics residual subspace projection update.

Forward-only derivative-free scaffold:
  1) Build orthonormal basis Q from B (Gram-Schmidt)
  2) P = Q Q^T
  3) r_proj = P r
  4) U_final = U_LF - alpha * r_proj
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(v: list[float]) -> float:
    return math.sqrt(dot(v, v))


def mat_vec(m: list[list[float]], v: list[float]) -> list[float]:
    return [dot(row, v) for row in m]


def transpose(m: list[list[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*m)]


def mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    bt = transpose(b)
    return [[dot(row, col) for col in bt] for row in a]


def gram_schmidt_columns(basis: list[list[float]]) -> list[list[float]]:
    # basis is n x k matrix (rows x cols)
    cols = transpose(basis)
    q_cols: list[list[float]] = []
    for v in cols:
        w = v[:]
        for q in q_cols:
            proj = dot(w, q)
            w = [wi - proj * qi for wi, qi in zip(w, q)]
        nrm = norm(w)
        if nrm > 1e-12:
            q_cols.append([wi / nrm for wi in w])
    if not q_cols:
        raise ValueError("basis is rank-deficient; cannot build projector")
    return transpose(q_cols)  # back to n x r


def build_projector(basis: list[list[float]]) -> list[list[float]]:
    q = gram_schmidt_columns(basis)
    return mat_mul(q, transpose(q))


def project_residual(residual: list[float], projector: list[list[float]]) -> list[float]:
    return mat_vec(projector, residual)


def forward_projection_update(u_lf: list[float], residual: list[float], basis: list[list[float]], alpha: float) -> dict:
    p = build_projector(basis)
    r_proj = project_residual(residual, p)
    u_final = [u - alpha * rp for u, rp in zip(u_lf, r_proj)]
    return {
        "u_lf": u_lf,
        "residual": residual,
        "projected_residual": r_proj,
        "u_final": u_final,
        "projector": p,
        "residual_norm_before": norm(residual),
        "residual_norm_projected": norm(r_proj),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/projection_update_report.json")
    parser.add_argument("--alpha", type=float, default=0.35)
    args = parser.parse_args()

    u_lf = [0.0, 0.0, 0.0, 0.0012, -0.0007, 0.0003]
    residual = [0.0, 0.0, 0.0, 11.0, -3.0, 2.0]
    basis = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]

    report = forward_projection_update(u_lf, residual, basis, alpha=args.alpha)
    report["alpha"] = args.alpha
    report["notes"] = "Forward-only orthogonal projection scaffold; replace basis with LF engine/Krylov basis in integration stage."

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote projection report: {out}")


if __name__ == "__main__":
    main()
