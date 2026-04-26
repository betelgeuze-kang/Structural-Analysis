#!/usr/bin/env python3
"""3-Bead branch cache budget estimator for RDNA2-class GPUs.

Estimates whether branch-parallel working sets fit in Infinity Cache and
recommends micro-batch branch chunk size.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def _mb(x: float) -> float:
    return x / (1024.0 * 1024.0)


def _parse_branches(text: str) -> list[int]:
    out: list[int] = []
    for t in str(text).split(","):
        t = t.strip()
        if not t:
            continue
        out.append(max(1, int(t)))
    if not out:
        raise SystemExit("--branches-list must contain at least one integer")
    return out


def _scenario(
    node_count: int,
    branches: int,
    beads_per_node: int,
    bytes_per_scalar: int,
    coords_components: int,
    state_components: int,
    graph_overhead_mb: float,
    activation_overhead_mb: float,
    cache_bytes: int,
    cache_headroom: float,
) -> dict:
    coord_bytes_per_branch = node_count * beads_per_node * coords_components * bytes_per_scalar
    state_bytes_per_branch = node_count * beads_per_node * state_components * bytes_per_scalar

    coords_total = coord_bytes_per_branch * branches
    state_total = state_bytes_per_branch * branches

    overhead_bytes = int((graph_overhead_mb + activation_overhead_mb) * 1024.0 * 1024.0)
    working_set = state_total + overhead_bytes

    fit_full = working_set <= cache_bytes
    fit_ratio = working_set / max(cache_bytes, 1)

    target_bytes = int(cache_bytes * cache_headroom)
    per_branch_total = state_bytes_per_branch
    available_for_branches = max(1, target_bytes - overhead_bytes)
    recommended_chunk = max(1, available_for_branches // max(per_branch_total, 1))
    recommended_chunk = min(branches, int(recommended_chunk))

    chunk_working_set = per_branch_total * recommended_chunk + overhead_bytes
    chunk_fit = chunk_working_set <= cache_bytes

    return {
        "branches": int(branches),
        "coord_bytes_per_branch": int(coord_bytes_per_branch),
        "state_bytes_per_branch": int(state_bytes_per_branch),
        "coords_total_mb": _mb(coords_total),
        "state_total_mb": _mb(state_total),
        "working_set_mb": _mb(working_set),
        "cache_mb": _mb(cache_bytes),
        "cache_fit_full_batch": fit_full,
        "cache_fit_ratio": fit_ratio,
        "recommended_micro_batch_branches": int(recommended_chunk),
        "recommended_micro_batch_working_set_mb": _mb(chunk_working_set),
        "recommended_micro_batch_fits_cache": bool(chunk_fit),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--node-count", type=int, default=100_000)
    p.add_argument("--branches-list", default="10,64")
    p.add_argument("--beads-per-node", type=int, default=3)
    p.add_argument("--bytes-per-scalar", type=int, default=4)
    p.add_argument("--coords-components", type=int, default=3)
    p.add_argument("--state-components", type=int, default=5, help="compact branch state (e.g., x,y,z,force,residual)")
    p.add_argument("--graph-overhead-mb", type=float, default=10.0)
    p.add_argument("--activation-overhead-mb", type=float, default=14.0)
    p.add_argument("--cache-mb", type=float, default=128.0)
    p.add_argument("--cache-headroom", type=float, default=0.72)
    p.add_argument("--out", default="implementation/phase1/three_bead_cache_budget_report.json")
    args = p.parse_args()

    cache_bytes = int(float(args.cache_mb) * 1024.0 * 1024.0)
    branches = _parse_branches(args.branches_list)

    scenarios = [
        _scenario(
            node_count=max(1, int(args.node_count)),
            branches=b,
            beads_per_node=max(1, int(args.beads_per_node)),
            bytes_per_scalar=max(1, int(args.bytes_per_scalar)),
            coords_components=max(1, int(args.coords_components)),
            state_components=max(1, int(args.state_components)),
            graph_overhead_mb=float(args.graph_overhead_mb),
            activation_overhead_mb=float(args.activation_overhead_mb),
            cache_bytes=cache_bytes,
            cache_headroom=float(args.cache_headroom),
        )
        for b in branches
    ]

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-3bead-cache-budget",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "node_count": int(args.node_count),
            "branches_list": branches,
            "beads_per_node": int(args.beads_per_node),
            "bytes_per_scalar": int(args.bytes_per_scalar),
            "coords_components": int(args.coords_components),
            "state_components": int(args.state_components),
            "graph_overhead_mb": float(args.graph_overhead_mb),
            "activation_overhead_mb": float(args.activation_overhead_mb),
            "cache_mb": float(args.cache_mb),
            "cache_headroom": float(args.cache_headroom),
        },
        "scenarios": scenarios,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote cache budget report: {out}")


if __name__ == "__main__":
    main()
