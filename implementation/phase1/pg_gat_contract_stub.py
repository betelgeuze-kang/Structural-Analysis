#!/usr/bin/env python3
"""Step 2: Physics-guided attention (PG-GAT) contract report.

Replaces static edge constants with LF export-derived edge signals.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

INTERFACE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.2"
RUN_ID = "phase1-pg-gat-contract"

REASON_CODES = {
    "PASS": "PG-GAT attention contract is valid",
    "ERR_EMPTY_EDGES": "no edges available for attention scoring",
}


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _load_from_lf_json(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    edges = payload.get("edges")
    if isinstance(edges, list) and edges:
        return edges
    return None


def _load_from_edges_csv(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows if rows else None


def _fallback_edges() -> list[dict]:
    return [
        {"edge_id": "E1", "axial_force": 221.4, "shear_force": 43.9, "moment": 18.3, "local_stiffness": 12_700_000.0, "yield_index": 0.62},
        {"edge_id": "E2", "axial_force": 184.0, "shear_force": 38.0, "moment": 11.7, "local_stiffness": 10_400_000.0, "yield_index": 0.37},
        {"edge_id": "E3", "axial_force": 145.0, "shear_force": 27.0, "moment": 8.4, "local_stiffness": 8_100_000.0, "yield_index": 0.21},
        {"edge_id": "E4", "axial_force": 266.0, "shear_force": 52.0, "moment": 24.9, "local_stiffness": 13_800_000.0, "yield_index": 0.74},
    ]


def _edge_features(edge: dict, torsion_scale: float, stress_scale: float) -> dict:
    moment = abs(_safe_float(edge.get("moment")))
    local_stiffness = max(abs(_safe_float(edge.get("local_stiffness"), 1.0)), 1e-9)
    axial = abs(_safe_float(edge.get("axial_force")))
    shear = abs(_safe_float(edge.get("shear_force")))
    yield_index = max(0.0, _safe_float(edge.get("yield_index")))

    torsion = (moment / local_stiffness) * torsion_scale
    stress = (axial + 0.35 * shear) / max(stress_scale, 1e-9)
    damping = min(1.0, 0.5 * yield_index)

    return {
        "torsion": float(torsion),
        "stress": float(stress),
        "damping": float(damping),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/pg_gat_contract_report.json")
    p.add_argument("--lf-json", default="implementation/phase1/lf_output_sample.json")
    p.add_argument("--edges-csv", default="implementation/phase1/step_outputs/ulf_edges.csv")
    p.add_argument("--k-top", type=float, default=0.1, help="top risk ratio for dense processing")
    p.add_argument("--torsion-scale", type=float, default=50000.0)
    p.add_argument("--stress-scale", type=float, default=400.0)
    p.add_argument("--w-torsion", type=float, default=1.8)
    p.add_argument("--w-stress", type=float, default=2.2)
    p.add_argument("--w-damping", type=float, default=1.2)
    args = p.parse_args()

    source_mode = "fallback"
    edges = _load_from_lf_json(Path(args.lf_json))
    if edges is not None:
        source_mode = "lf_json"
    else:
        edges = _load_from_edges_csv(Path(args.edges_csv))
        if edges is not None:
            source_mode = "edges_csv"
        else:
            edges = _fallback_edges()

    weighted = []
    for e in edges:
        f = _edge_features(e, torsion_scale=float(args.torsion_scale), stress_scale=float(args.stress_scale))
        score = (
            float(args.w_torsion) * f["torsion"]
            + float(args.w_stress) * f["stress"]
            + float(args.w_damping) * f["damping"]
        )
        alpha = _sigmoid(score)
        weighted.append(
            {
                "edge_id": str(e.get("edge_id", "unknown")),
                **f,
                "physics_score": float(score),
                "alpha_ij": float(alpha),
                "yield_index": _safe_float(e.get("yield_index")),
            }
        )

    if not weighted:
        reason_code = "ERR_EMPTY_EDGES"
        contract_pass = False
        dense = []
        sparse = []
    else:
        weighted.sort(key=lambda x: x["alpha_ij"], reverse=True)
        ratio = min(max(float(args.k_top), 0.0), 1.0)
        k = max(1, int(round(len(weighted) * ratio)))
        k = min(k, len(weighted))
        dense = [w["edge_id"] for w in weighted[:k]]
        sparse = [w["edge_id"] for w in weighted[k:]]
        reason_code = "PASS"
        contract_pass = True

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
        "source": {
            "mode": source_mode,
            "lf_json": args.lf_json,
            "edges_csv": args.edges_csv,
        },
        "attention_policy": {
            "dense_top_ratio": float(args.k_top),
            "dense_edges": dense,
            "sparse_edges": sparse,
        },
        "weights": {
            "torsion": float(args.w_torsion),
            "stress": float(args.w_stress),
            "damping": float(args.w_damping),
        },
        "edges": weighted,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote PG-GAT contract report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
