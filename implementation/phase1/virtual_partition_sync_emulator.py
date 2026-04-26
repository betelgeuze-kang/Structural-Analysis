#!/usr/bin/env python3
"""Single-GPU virtual async sync emulator for partitioned halo exchange.

This emulates MPI/RPC-like partition synchronization cost without multi-GPU setup.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "virtual partition sync stress passed",
    "ERR_INVALID_INPUT": "invalid sync emulator input",
    "ERR_SYNC_OVERLOAD": "sync stress exceeds configured limits",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["partition_report", "out"],
    "properties": {
        "partition_report": {"type": "string", "minLength": 1},
        "steps": {"type": "integer", "minimum": 10},
        "dt_s": {"type": "number", "exclusiveMinimum": 0.0},
        "bandwidth_gbps": {"type": "number", "exclusiveMinimum": 0.0},
        "latency_us": {"type": "number", "minimum": 0.0},
        "compute_us_per_node": {"type": "number", "exclusiveMinimum": 0.0},
        "overlap_cap": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "jitter_pct": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "seed": {"type": "integer"},
        "max_sync_stall_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_p99_step_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "max_straggler_ratio": {"type": "number", "exclusiveMinimum": 1.0},
        "min_overlap_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def emulate_sync(partition_report: dict, *, steps: int, dt_s: float, bandwidth_gbps: float, latency_us: float, compute_us_per_node: float, overlap_cap: float, jitter_pct: float, seed: int) -> dict:
    result = partition_report.get("result") if isinstance(partition_report.get("result"), dict) else {}
    part_sizes = result.get("partition_sizes") if isinstance(result.get("partition_sizes"), list) else []
    k = int(len(part_sizes))
    if k <= 0:
        raise ValueError("partition report missing partition sizes")

    node_count = int(result.get("node_count", sum(int(x) for x in part_sizes)))
    est_comm_bytes_total = float(result.get("estimated_comm_bytes", 0.0))
    halo_ratio = float(result.get("halo_node_ratio", 0.0))

    bw_bytes_per_s = float(bandwidth_gbps) * 1e9 / 8.0
    rng = np.random.default_rng(int(seed))

    part = np.array([max(1, int(x)) for x in part_sizes], dtype=np.float64)
    part_w = part / np.sum(part)

    base_compute_s = part * float(compute_us_per_node) * 1e-6
    # Partition-local communication load (weighted + imbalance jitter)
    comm_bytes_part = est_comm_bytes_total * part_w

    step_times: list[float] = []
    stall_ratios: list[float] = []
    overlap_ratios: list[float] = []
    lag_ms: list[float] = []

    for _ in range(int(steps)):
        imb = rng.normal(loc=1.0, scale=0.08, size=k)
        imb = np.clip(imb, 0.7, 1.4)
        compute_s = base_compute_s * imb

        # bytes + per-partition message latency proxy
        msg_count = np.maximum(1.0, np.ceil((halo_ratio * part) / 1024.0))
        comm_s = (comm_bytes_part * imb) / max(bw_bytes_per_s, 1e-9) + (msg_count * float(latency_us) * 1e-6)

        # async overlap proxy: lower halo ratio -> better overlap
        overlap = min(float(overlap_cap), max(0.05, 0.72 - 0.55 * halo_ratio))
        effective_comm_s = np.maximum(0.0, comm_s - overlap * compute_s)
        local_s = compute_s + effective_comm_s

        jitter = rng.uniform(1.0 - jitter_pct, 1.0 + jitter_pct, size=k)
        local_s = local_s * jitter

        # straggler injection
        straggler_idx = int(rng.integers(0, k))
        local_s[straggler_idx] *= float(rng.uniform(1.0, 1.25))

        step_s = float(np.max(local_s))
        step_times.append(step_s)

        stall = float(np.sum(effective_comm_s) / max(np.sum(local_s), 1e-12))
        overlap_ratio = float(1.0 - np.sum(effective_comm_s) / max(np.sum(comm_s), 1e-12))
        stall_ratios.append(stall)
        overlap_ratios.append(overlap_ratio)
        lag_ms.append(float((np.max(local_s) - np.median(local_s)) * 1000.0))

    step_arr = np.asarray(step_times, dtype=np.float64)
    stall_arr = np.asarray(stall_ratios, dtype=np.float64)
    overlap_arr = np.asarray(overlap_ratios, dtype=np.float64)
    lag_arr = np.asarray(lag_ms, dtype=np.float64)

    p50 = float(np.percentile(step_arr, 50))
    p95 = float(np.percentile(step_arr, 95))
    p99 = float(np.percentile(step_arr, 99))

    sim_comm_gbps = float((est_comm_bytes_total / max(np.mean(step_arr), 1e-12)) * 8.0 / 1e9)

    return {
        "partition_count": int(k),
        "node_count": int(node_count),
        "estimated_comm_bytes_per_step": float(est_comm_bytes_total),
        "avg_step_ms": float(np.mean(step_arr) * 1000.0),
        "p95_step_ms": float(p95 * 1000.0),
        "p99_step_ms": float(p99 * 1000.0),
        "straggler_ratio": float(p99 / max(p50, 1e-12)),
        "sync_stall_ratio": float(np.mean(stall_arr)),
        "comm_overlap_ratio": float(np.mean(overlap_arr)),
        "p95_partition_lag_ms": float(np.percentile(lag_arr, 95)),
        "p99_partition_lag_ms": float(np.percentile(lag_arr, 99)),
        "simulated_comm_gbps": float(sim_comm_gbps),
        "simulated_steps": int(steps),
        "dt_s": float(dt_s),
    }


def main() -> None:
    logger = get_logger("phase3.virtual_partition_sync_emulator")
    p = argparse.ArgumentParser()
    p.add_argument("--partition-report", required=True)
    p.add_argument("--steps", type=int, default=300)
    p.add_argument("--dt-s", type=float, default=0.01)
    p.add_argument("--bandwidth-gbps", type=float, default=32.0)
    p.add_argument("--latency-us", type=float, default=40.0)
    p.add_argument("--compute-us-per-node", type=float, default=0.20)
    p.add_argument("--overlap-cap", type=float, default=0.70)
    p.add_argument("--jitter-pct", type=float, default=0.12)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--max-sync-stall-ratio", type=float, default=0.36)
    p.add_argument("--max-p99-step-ms", type=float, default=550.0)
    p.add_argument("--max-straggler-ratio", type=float, default=2.4)
    p.add_argument("--min-overlap-ratio", type=float, default=0.35)
    p.add_argument("--out", default="implementation/phase1/virtual_partition_sync_report.json")
    args = p.parse_args()

    input_payload = {
        "partition_report": str(args.partition_report),
        "steps": int(args.steps),
        "dt_s": float(args.dt_s),
        "bandwidth_gbps": float(args.bandwidth_gbps),
        "latency_us": float(args.latency_us),
        "compute_us_per_node": float(args.compute_us_per_node),
        "overlap_cap": float(args.overlap_cap),
        "jitter_pct": float(args.jitter_pct),
        "seed": int(args.seed),
        "max_sync_stall_ratio": float(args.max_sync_stall_ratio),
        "max_p99_step_ms": float(args.max_p99_step_ms),
        "max_straggler_ratio": float(args.max_straggler_ratio),
        "min_overlap_ratio": float(args.min_overlap_ratio),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.virtual_partition_sync_emulator")
        p_report = _load(str(args.partition_report))
        result = emulate_sync(
            p_report,
            steps=int(args.steps),
            dt_s=float(args.dt_s),
            bandwidth_gbps=float(args.bandwidth_gbps),
            latency_us=float(args.latency_us),
            compute_us_per_node=float(args.compute_us_per_node),
            overlap_cap=float(args.overlap_cap),
            jitter_pct=float(args.jitter_pct),
            seed=int(args.seed),
        )

        checks = {
            "sync_stall_budget_pass": bool(float(result["sync_stall_ratio"]) <= float(args.max_sync_stall_ratio)),
            "p99_step_budget_pass": bool(float(result["p99_step_ms"]) <= float(args.max_p99_step_ms)),
            "straggler_budget_pass": bool(float(result["straggler_ratio"]) <= float(args.max_straggler_ratio)),
            "overlap_ratio_pass": bool(float(result["comm_overlap_ratio"]) >= float(args.min_overlap_ratio)),
        }
        contract_pass = bool(all(checks.values()))
        reason_code = "PASS" if contract_pass else "ERR_SYNC_OVERLOAD"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-virtual-partition-sync-emulator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "result": result,
            "checks": checks,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, 20, "sync_emulator.completed", contract_pass=contract_pass, reason_code=reason_code)
        print(f"Wrote virtual sync report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-virtual-partition-sync-emulator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote virtual sync report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
