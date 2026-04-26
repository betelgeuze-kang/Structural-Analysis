#!/usr/bin/env python3
"""Phase-F1: multi-scale L3 streaming planner for high-frequency dynamics."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


REASONS = {
    "PASS": "multi-scale L3 streaming profile passed",
    "ERR_INVALID_INPUT": "invalid multi-scale streaming input",
    "ERR_NO_CACHE_SAFE_CHUNK": "no cache-safe microbatch chunk found for high-frequency setting",
}


def _mb(v: float) -> float:
    return float(v) / (1024.0 * 1024.0)


def run_profile(
    *,
    total_nodes: int,
    branches: int,
    freq_max_hz: float,
    l3_cache_mb: float,
    node_state_bytes: int,
    near_field_ratio: float,
    far_field_coarsen: float,
    chunk_candidates: list[int],
) -> dict:
    if total_nodes <= 0 or branches <= 0 or freq_max_hz <= 0.0 or l3_cache_mb <= 0.0:
        raise ValueError("invalid positive inputs")
    if node_state_bytes < 24:
        raise ValueError("node_state_bytes is unrealistically small")
    if not (0.01 <= near_field_ratio <= 0.9):
        raise ValueError("near_field_ratio must be in [0.01, 0.9]")
    if far_field_coarsen < 1.0:
        raise ValueError("far_field_coarsen must be >= 1.0")
    if not chunk_candidates:
        raise ValueError("chunk_candidates cannot be empty")

    # 80Hz baseline mesh -> refine near field for high frequency, but keep
    # expansion bounded so the active window stays streamable.
    refinement = max(1.0, float(freq_max_hz) / 80.0)
    near_expand = 1.0 + 0.35 * (refinement - 1.0)
    near_nodes_full = int(total_nodes * near_field_ratio * near_expand)
    near_nodes_full = min(max(1, near_nodes_full), total_nodes)

    far_nodes_full = max(0, total_nodes - int(total_nodes * near_field_ratio))
    far_nodes_effective = int(far_nodes_full / far_field_coarsen)
    active_nodes_window = max(1, min(total_nodes, near_nodes_full + far_nodes_effective))

    # Keep some budget headroom for graph metadata/activations.
    usable_l3_mb = float(l3_cache_mb) * 0.82
    scenarios = []
    cache_safe_chunks = []

    for chunk in sorted(set(int(c) for c in chunk_candidates if int(c) > 0)):
        chunk_eff = min(int(branches), int(chunk))
        work_bytes = active_nodes_window * int(node_state_bytes) * chunk_eff
        work_mb = _mb(work_bytes)
        pressure = work_mb / max(usable_l3_mb, 1e-9)
        cache_safe = pressure <= 1.0
        if cache_safe:
            cache_safe_chunks.append(chunk_eff)

        est_reloads = int(math.ceil(branches / max(1, chunk_eff)))
        scenarios.append(
            {
                "chunk": int(chunk_eff),
                "active_nodes_window": int(active_nodes_window),
                "working_set_mb": float(work_mb),
                "usable_l3_mb": float(usable_l3_mb),
                "cache_pressure_ratio": float(pressure),
                "cache_safe": bool(cache_safe),
                "branch_reload_count": int(est_reloads),
            }
        )

    recommended = None
    if cache_safe_chunks:
        # Prefer larger chunk for throughput as long as it is cache-safe.
        best = max(cache_safe_chunks)
        recommended = next((s for s in scenarios if int(s["chunk"]) == int(best)), None)

    checks = {
        "high_frequency_target": bool(freq_max_hz >= 500.0),
        "windowed_o_n_streaming": bool(active_nodes_window <= int(total_nodes * 0.6)),
        "near_field_refined": bool(refinement > 1.0),
        "has_cache_safe_chunk": bool(len(cache_safe_chunks) > 0),
    }

    if not checks["has_cache_safe_chunk"]:
        reason_code = "ERR_NO_CACHE_SAFE_CHUNK"
    else:
        reason_code = "PASS"

    return {
        "schema_version": "1.0",
        "run_id": "phase1-multiscale-l3-streaming-profile",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "total_nodes": int(total_nodes),
            "branches": int(branches),
            "freq_max_hz": float(freq_max_hz),
            "l3_cache_mb": float(l3_cache_mb),
            "node_state_bytes": int(node_state_bytes),
            "near_field_ratio": float(near_field_ratio),
            "far_field_coarsen": float(far_field_coarsen),
            "chunk_candidates": [int(c) for c in sorted(set(chunk_candidates))],
        },
        "checks": checks,
        "metrics": {
            "refinement_factor": float(refinement),
            "active_nodes_window": int(active_nodes_window),
            "active_node_ratio": float(active_nodes_window / max(1, total_nodes)),
            "cache_safe_chunk_count": int(len(cache_safe_chunks)),
            "max_cache_safe_chunk": int(max(cache_safe_chunks) if cache_safe_chunks else 0),
            "recommended_chunk": int(recommended["chunk"]) if isinstance(recommended, dict) else 0,
            "recommended_working_set_mb": float(recommended["working_set_mb"]) if isinstance(recommended, dict) else float("nan"),
        },
        "scenarios": scenarios,
        "recommended": recommended,
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--total-nodes", type=int, default=120000)
    p.add_argument("--branches", type=int, default=64)
    p.add_argument("--freq-max-hz", type=float, default=500.0)
    p.add_argument("--l3-cache-mb", type=float, default=128.0)
    p.add_argument("--node-state-bytes", type=int, default=96)
    p.add_argument("--near-field-ratio", type=float, default=0.14)
    p.add_argument("--far-field-coarsen", type=float, default=6.0)
    p.add_argument("--chunk-candidates", default="8,12,16,24,32")
    p.add_argument("--out", default="implementation/phase1/multiscale_l3_streaming_report.json")
    args = p.parse_args()

    try:
        chunks = [int(v.strip()) for v in str(args.chunk_candidates).split(",") if v.strip()]
        payload = run_profile(
            total_nodes=int(args.total_nodes),
            branches=int(args.branches),
            freq_max_hz=float(args.freq_max_hz),
            l3_cache_mb=float(args.l3_cache_mb),
            node_state_bytes=int(args.node_state_bytes),
            near_field_ratio=float(args.near_field_ratio),
            far_field_coarsen=float(args.far_field_coarsen),
            chunk_candidates=chunks,
        )
    except Exception as exc:  # noqa: BLE001
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-multiscale-l3-streaming-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote multi-scale L3 streaming report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
