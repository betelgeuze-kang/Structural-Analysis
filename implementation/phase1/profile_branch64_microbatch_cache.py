#!/usr/bin/env python3
"""Profile branch-64 micro-batching with cache-aware runtime hooks.

This runner measures chunked branch execution (`branch_batch`) through the
Rust/HIP JSON hook and reports cache-fit outcomes for RDNA2 128MB Infinity
Cache style targets.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shlex
import statistics
import subprocess


REASONS = {
    "PASS": "at least one cache-safe micro-batch chunk found and profiled",
    "ERR_HOOK_EXEC": "runtime hook command failed or returned invalid payload",
    "ERR_NO_CACHE_SAFE_CHUNK": "no tested chunk fits cache headroom",
    "ERR_INVALID_INPUT": "invalid profile input parameters",
}


def _parse_chunks(text: str, branches: int) -> list[int]:
    out: list[int] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        c = int(tok)
        if c <= 0:
            continue
        out.append(min(c, branches))
    out = sorted(set(out), reverse=True)
    if branches not in out:
        out.insert(0, branches)
    return out


def _run_json(command: str, payload: dict) -> dict:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    try:
        return json.loads(proc.stdout)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"invalid JSON from hook: {exc}") from exc


def _mb(x: float) -> float:
    return float(x) / (1024.0 * 1024.0)


def _estimate_working_set_mb(
    node_count: int,
    branch_batch: int,
    state_components: int,
    graph_overhead_mb: float,
) -> float:
    state_bytes_per_branch = int(node_count) * 3 * int(state_components) * 4
    working_set_bytes = state_bytes_per_branch * int(branch_batch) + int(float(graph_overhead_mb) * 1024.0 * 1024.0)
    return _mb(working_set_bytes)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime-hook-cmd", default="python3 implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--branches", type=int, default=64)
    p.add_argument("--chunk-candidates", default="64,32,16,8,4")
    p.add_argument("--node-count", type=int, default=100_000)
    p.add_argument("--state-components", type=int, default=5)
    p.add_argument("--cache-mb", type=float, default=128.0)
    p.add_argument("--cache-headroom", type=float, default=0.72)
    p.add_argument("--graph-overhead-mb", type=float, default=24.0)
    p.add_argument("--cache-penalty-gain", type=float, default=0.85)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--gpu", default="AMD Radeon RX 6900 XT")
    p.add_argument("--out", default="implementation/phase1/branch64_microbatch_profile_report.json")
    args = p.parse_args()

    if int(args.branches) < 2 or int(args.node_count) < 2 or int(args.state_components) < 1 or int(args.repeats) < 1:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-branch64-microbatch-cache-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": REASONS["ERR_INVALID_INPUT"],
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    branches = int(args.branches)
    chunks = _parse_chunks(args.chunk_candidates, branches=branches)
    cache_headroom_bytes = float(args.cache_mb) * float(args.cache_headroom)

    scenarios: list[dict] = []
    hook_error: str | None = None

    for chunk in chunks:
        num_chunks = int(math.ceil(branches / max(1, chunk)))
        rep_total_seconds: list[float] = []
        rep_peak_vram_mb: list[float] = []
        rep_cache_penalty: list[float] = []
        cache_fit_per_call: list[bool] = []
        cache_fit_ratio_per_call: list[float] = []

        try:
            for _ in range(int(args.repeats)):
                # `step5_profile` is already parameterized by `branch_batch`,
                # so one hook call is enough to represent a repeated microbatch.
                req = {
                    "action": "step5_profile",
                    "n": int(args.node_count),
                    "branch_batch": int(chunk),
                    "state_components": int(args.state_components),
                    "cache_mb": float(args.cache_mb),
                    "graph_overhead_mb": float(args.graph_overhead_mb),
                    "cache_penalty_gain": float(args.cache_penalty_gain),
                }
                res = _run_json(args.runtime_hook_cmd, req)
                sec = float(res["seconds"])
                pvb = float(res.get("peak_vram_bytes", 0.0))
                penalty = float(res.get("cache_penalty", 1.0))
                fit = bool(res.get("cache_fit", False))
                ratio = float(res.get("cache_fit_ratio", 0.0))

                total_sec = sec * float(num_chunks)
                peak_vram = pvb
                penalties = [penalty]
                fits = [fit]
                ratios = [ratio]

                rep_total_seconds.append(total_sec)
                rep_peak_vram_mb.append(_mb(peak_vram))
                rep_cache_penalty.append(statistics.mean(penalties) if penalties else 1.0)
                cache_fit_per_call.extend(fits)
                cache_fit_ratio_per_call.extend(ratios)
        except Exception as exc:  # noqa: BLE001
            hook_error = str(exc)
            break

        avg_total = statistics.mean(rep_total_seconds) if rep_total_seconds else math.inf
        std_total = statistics.pstdev(rep_total_seconds) if len(rep_total_seconds) > 1 else 0.0
        avg_peak_vram_mb = statistics.mean(rep_peak_vram_mb) if rep_peak_vram_mb else 0.0
        avg_penalty = statistics.mean(rep_cache_penalty) if rep_cache_penalty else 1.0
        working_set_est_mb = _estimate_working_set_mb(
            node_count=int(args.node_count),
            branch_batch=int(chunk),
            state_components=int(args.state_components),
            graph_overhead_mb=float(args.graph_overhead_mb),
        )
        cache_safe = bool(working_set_est_mb <= cache_headroom_bytes)

        scenarios.append(
            {
                "chunk_branches": int(chunk),
                "num_chunks": int(num_chunks),
                "avg_total_seconds": float(avg_total),
                "std_total_seconds": float(std_total),
                "avg_peak_vram_mb": float(avg_peak_vram_mb),
                "avg_cache_penalty": float(avg_penalty),
                "avg_branch_ms": float((avg_total / branches) * 1000.0),
                "cache_safe_by_estimate": cache_safe,
                "estimated_working_set_mb": float(working_set_est_mb),
                "cache_headroom_mb": float(cache_headroom_bytes),
                "cache_fit_all_calls": bool(cache_fit_per_call and all(cache_fit_per_call)),
                "cache_fit_ratio_max": float(max(cache_fit_ratio_per_call) if cache_fit_ratio_per_call else 0.0),
            }
        )

    if hook_error is not None:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-branch64-microbatch-cache-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hardware": {"gpu": args.gpu, "cache_mb": float(args.cache_mb)},
            "inputs": {
                "runtime_hook_cmd": args.runtime_hook_cmd,
                "branches": branches,
                "chunk_candidates": chunks,
                "node_count": int(args.node_count),
                "state_components": int(args.state_components),
                "cache_headroom": float(args.cache_headroom),
                "graph_overhead_mb": float(args.graph_overhead_mb),
                "repeats": int(args.repeats),
            },
            "scenarios": scenarios,
            "contract_pass": False,
            "reason_code": "ERR_HOOK_EXEC",
            "reason": f"{REASONS['ERR_HOOK_EXEC']}: {hook_error}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        raise SystemExit(1)

    cache_safe = [s for s in scenarios if s["cache_safe_by_estimate"] and s["cache_fit_all_calls"]]
    full_batch = next((s for s in scenarios if int(s["chunk_branches"]) == branches), None)

    if not cache_safe:
        reason_code = "ERR_NO_CACHE_SAFE_CHUNK"
        contract_pass = False
        recommended = None
    else:
        recommended = min(cache_safe, key=lambda s: (float(s["avg_total_seconds"]), int(s["chunk_branches"])))
        reason_code = "PASS"
        contract_pass = True

    report = {
        "schema_version": "1.0",
        "run_id": "phase1-branch64-microbatch-cache-profile",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "gpu": args.gpu,
            "cache_mb": float(args.cache_mb),
            "cache_headroom_mb": float(cache_headroom_bytes),
        },
        "inputs": {
            "runtime_hook_cmd": args.runtime_hook_cmd,
            "branches": branches,
            "chunk_candidates": chunks,
            "node_count": int(args.node_count),
            "state_components": int(args.state_components),
            "cache_headroom": float(args.cache_headroom),
            "graph_overhead_mb": float(args.graph_overhead_mb),
            "cache_penalty_gain": float(args.cache_penalty_gain),
            "repeats": int(args.repeats),
        },
        "full_batch_64": full_batch,
        "scenarios": scenarios,
        "recommended": recommended,
        "checks": {
            "full_batch_cache_safe": bool(full_batch["cache_safe_by_estimate"]) if isinstance(full_batch, dict) else False,
            "full_batch_cache_fit": bool(full_batch["cache_fit_all_calls"]) if isinstance(full_batch, dict) else False,
            "microbatch_available": bool(cache_safe),
            "recommended_chunk_le_16": bool(recommended and int(recommended["chunk_branches"]) <= 16),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote branch64 microbatch cache profile report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
