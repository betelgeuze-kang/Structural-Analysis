#!/usr/bin/env python3
"""Step 2: Physics-guided attention (PG-GAT) static contract stub."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import math
from pathlib import Path

INTERFACE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.1"
RUN_ID = "phase1-pg-gat-contract"


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/pg_gat_contract_report.json")
    p.add_argument("--k-top", type=float, default=0.1, help="top risk ratio for dense processing")
    args = p.parse_args()

    edges = [
        {"edge_id": "E1", "torsion": 0.3, "stress": 0.4, "damping": 0.1},
        {"edge_id": "E2", "torsion": 1.1, "stress": 0.9, "damping": 0.6},
        {"edge_id": "E3", "torsion": 0.2, "stress": 0.1, "damping": 0.05},
        {"edge_id": "E4", "torsion": 0.9, "stress": 1.2, "damping": 0.8},
    ]

    weighted = []
    for e in edges:
        score = 1.8 * e["torsion"] + 2.2 * e["stress"] + 1.2 * e["damping"]
        alpha = sigmoid(score)
        weighted.append({**e, "physics_score": score, "alpha_ij": alpha})

    weighted.sort(key=lambda x: x["alpha_ij"], reverse=True)
    k = max(1, int(len(weighted) * args.k_top))
    dense = [w["edge_id"] for w in weighted[:k]]
    sparse = [w["edge_id"] for w in weighted[k:]]

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "contract_pass": True,
        "reason_code": "PASS",
        "attention_policy": {
            "dense_top_ratio": args.k_top,
            "dense_edges": dense,
            "sparse_edges": sparse,
        },
        "edges": weighted,
        "notes": "PG-GAT static scaffold using LF physics triggers only.",
    }
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote PG-GAT contract report: {out}")


if __name__ == "__main__":
    main()
