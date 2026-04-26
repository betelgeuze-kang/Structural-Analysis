#!/usr/bin/env python3
"""Single-GPU FETI-lite synchronization benchmark.

This models interface constraint iterations (gap continuity + force balance)
between partitioned subdomains on a single GPU runtime.
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
    "PASS": "feti-lite sync benchmark passed",
    "ERR_INVALID_INPUT": "invalid feti-lite sync input",
    "ERR_SYNC_OVERLOAD": "feti-lite sync benchmark exceeded budget",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["partition_report", "out"],
    "properties": {
        "partition_report": {"type": "string", "minLength": 1},
        "execution_mode": {"type": "string", "enum": ["emulation", "boundary_sync"]},
        "steps": {"type": "integer", "minimum": 10},
        "dt_s": {"type": "number", "exclusiveMinimum": 0.0},
        "bandwidth_gbps": {"type": "number", "exclusiveMinimum": 0.0},
        "latency_us": {"type": "number", "minimum": 0.0},
        "compute_us_per_node": {"type": "number", "exclusiveMinimum": 0.0},
        "overlap_cap": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "jitter_pct": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "seed": {"type": "integer"},
        "max_feti_iters": {"type": "integer", "minimum": 1},
        "gap_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "force_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "rho": {"type": "number", "exclusiveMinimum": 0.0},
        "relax": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "state_components": {"type": "integer", "minimum": 1},
        "min_converged_step_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_sync_stall_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_p99_step_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "max_straggler_ratio": {"type": "number", "exclusiveMinimum": 1.0},
        "min_overlap_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ring_edges(k: int) -> list[tuple[int, int]]:
    if k <= 1:
        return []
    if k == 2:
        return [(0, 1)]
    return [(i, (i + 1) % k) for i in range(k)]


def emulate_feti_sync(
    partition_report: dict,
    *,
    execution_mode: str = "emulation",
    steps: int,
    dt_s: float,
    bandwidth_gbps: float,
    latency_us: float,
    compute_us_per_node: float,
    overlap_cap: float,
    jitter_pct: float,
    seed: int,
    max_feti_iters: int,
    gap_tol: float,
    force_tol: float,
    rho: float,
    relax: float,
    state_components: int,
) -> dict:
    result = partition_report.get("result") if isinstance(partition_report.get("result"), dict) else {}
    part_sizes = result.get("partition_sizes") if isinstance(result.get("partition_sizes"), list) else []
    k = int(len(part_sizes))
    if k <= 0:
        raise ValueError("partition report missing partition sizes")

    node_count = int(result.get("node_count", sum(int(x) for x in part_sizes)))
    est_comm_bytes_step = float(result.get("estimated_comm_bytes", 0.0))
    halo_ratio = float(result.get("halo_node_ratio", 0.0))

    part = np.asarray([max(1, int(x)) for x in part_sizes], dtype=np.float64)
    part_w = part / max(np.sum(part), 1.0)
    k_eff = np.maximum(part, 1.0) * (1.0 + max(0.0, halo_ratio))
    edges = _ring_edges(k)

    bw_bytes_per_s = float(bandwidth_gbps) * 1e9 / 8.0
    rng = np.random.default_rng(int(seed))

    base_compute_s = part * float(compute_us_per_node) * 1e-6
    comm_bytes_per_iter = max(float(len(edges) * 2 * max(1, int(state_components)) * 4), est_comm_bytes_step / max(1.0, float(k)))
    # boundary_sync mode models explicit halo exchange/event fencing on single GPU.
    # emulation mode keeps historical lightweight proxy for compatibility.
    mode = str(execution_mode).strip().lower()
    if mode not in {"emulation", "boundary_sync"}:
        raise ValueError(f"unsupported execution_mode: {execution_mode}")
    latency_scale = 0.05 if mode == "boundary_sync" else 0.02
    latency_s_iter = float(latency_us) * 1e-6 * max(1, len(edges)) * latency_scale

    x = np.zeros(k, dtype=np.float64)
    phase = np.linspace(0.0, 2.0 * math.pi, num=k, endpoint=False, dtype=np.float64)

    step_ms: list[float] = []
    stall_ratio: list[float] = []
    overlap_ratio: list[float] = []
    lag_ms: list[float] = []
    feti_iters: list[int] = []
    max_gap_per_step: list[float] = []
    force_imbalance_per_step: list[float] = []
    converged_steps = 0

    for s in range(int(steps)):
        forcing_amp = 2e-4 * (1.0 + 2.0 * min(0.3, max(0.0, halo_ratio)))
        forcing = forcing_amp * np.sin(0.17 * float(s) + phase)
        x_pred = 0.94 * x + forcing
        x_it = x_pred.copy()
        lam = np.zeros(len(edges), dtype=np.float64)
        degree = np.zeros(k, dtype=np.float64)
        for i, j in edges:
            degree[i] += 1.0
            degree[j] += 1.0
        degree = np.maximum(degree, 1.0)

        converged = False
        iter_used = int(max_feti_iters)
        step_max_gap = math.inf
        step_force_imb = math.inf

        for it in range(1, int(max_feti_iters) + 1):
            corr = np.zeros(k, dtype=np.float64)
            net_force = np.zeros(k, dtype=np.float64)
            max_gap = 0.0
            total_abs_force = 0.0
            for eidx, (i, j) in enumerate(edges):
                gap = float(x_it[i] - x_it[j])
                # damped dual update to avoid runaway oscillation
                lam[eidx] = 0.82 * float(lam[eidx]) + float(rho) * gap
                kij = 0.5 * (float(k_eff[i]) + float(k_eff[j]))
                force = float(kij * gap + lam[eidx])
                total_abs_force += abs(force)
                net_force[i] += force
                net_force[j] -= force
                # primal continuity correction towards edge-average + dual pressure
                avg = 0.5 * (float(x_it[i]) + float(x_it[j]))
                corr[i] += float(avg - x_it[i]) - float(lam[eidx] / max(1.0, float(k_eff[i])))
                corr[j] += float(avg - x_it[j]) + float(lam[eidx] / max(1.0, float(k_eff[j])))
                max_gap = max(max_gap, abs(gap))
            x_it = x_it + float(relax) * (corr / degree)
            # bounded tether to local predictor to keep timestep-stable
            x_it = 0.92 * x_it + 0.08 * x_pred

            force_imb = float(abs(float(np.sum(net_force))) / max(1e-12, float(total_abs_force)))
            step_max_gap = float(max_gap)
            step_force_imb = float(force_imb)
            if step_max_gap <= float(gap_tol) and step_force_imb <= float(force_tol):
                converged = True
                iter_used = int(it)
                break

        x = x_it
        if converged:
            converged_steps += 1

        # Time model: local compute + iterative interface exchange.
        iter_factor = float(max(1, iter_used))
        local_compute = base_compute_s * (1.0 + 0.22 * iter_factor * (0.5 + halo_ratio))
        comm_local = (comm_bytes_per_iter * iter_factor * part_w) / max(bw_bytes_per_s, 1e-9) + latency_s_iter * iter_factor

        overlap = min(float(overlap_cap), max(0.05, 0.62 - 0.18 * halo_ratio + 0.06 / iter_factor))
        effective_comm = np.maximum(0.0, comm_local - overlap * local_compute)

        jit = rng.uniform(1.0 - jitter_pct, 1.0 + jitter_pct, size=k)
        local_total = (local_compute + effective_comm) * jit

        # Deterministic straggler pressure to emulate sync waiting.
        straggler_idx = int((s + int(seed)) % max(1, k))
        local_total[straggler_idx] *= float(rng.uniform(1.0, 1.12))

        step_s = float(np.max(local_total))
        step_ms.append(step_s * 1000.0)
        stall_ratio.append(float(np.sum(effective_comm) / max(np.sum(local_total), 1e-12)))
        overlap_ratio.append(float(1.0 - np.sum(effective_comm) / max(np.sum(comm_local), 1e-12)))
        lag_ms.append(float((np.max(local_total) - np.median(local_total)) * 1000.0))
        feti_iters.append(int(iter_used))
        max_gap_per_step.append(float(step_max_gap))
        force_imbalance_per_step.append(float(step_force_imb))

    step_arr = np.asarray(step_ms, dtype=np.float64)
    stall_arr = np.asarray(stall_ratio, dtype=np.float64)
    overlap_arr = np.asarray(overlap_ratio, dtype=np.float64)
    lag_arr = np.asarray(lag_ms, dtype=np.float64)
    it_arr = np.asarray(feti_iters, dtype=np.float64)
    gap_arr = np.asarray(max_gap_per_step, dtype=np.float64)
    fimb_arr = np.asarray(force_imbalance_per_step, dtype=np.float64)

    p50 = float(np.percentile(step_arr, 50))
    p99 = float(np.percentile(step_arr, 99))

    sim_comm_gbps = float((comm_bytes_per_iter * float(np.mean(it_arr)) / max(np.mean(step_arr) * 1e-3, 1e-12)) * 8.0 / 1e9)
    converged_ratio = float(converged_steps) / float(max(1, int(steps)))

    backend_name = "feti_lite_boundary_sync" if mode == "boundary_sync" else "feti_lite_single_gpu"
    return {
        "backend": backend_name,
        "execution_mode": mode,
        "partition_count": int(k),
        "node_count": int(node_count),
        "estimated_comm_bytes_per_step": float(est_comm_bytes_step),
        "avg_step_ms": float(np.mean(step_arr)),
        "p95_step_ms": float(np.percentile(step_arr, 95)),
        "p99_step_ms": float(p99),
        "straggler_ratio": float(p99 / max(p50, 1e-12)),
        "sync_stall_ratio": float(np.mean(stall_arr)),
        "comm_overlap_ratio": float(np.mean(overlap_arr)),
        "p95_partition_lag_ms": float(np.percentile(lag_arr, 95)),
        "p99_partition_lag_ms": float(np.percentile(lag_arr, 99)),
        "mean_feti_iterations": float(np.mean(it_arr)),
        "p95_feti_iterations": float(np.percentile(it_arr, 95)),
        "max_gap_norm": float(np.max(gap_arr)) if gap_arr.size else math.inf,
        "max_force_imbalance": float(np.max(fimb_arr)) if fimb_arr.size else math.inf,
        "converged_step_ratio": float(converged_ratio),
        "simulated_comm_gbps": float(sim_comm_gbps),
        "simulated_steps": int(steps),
        "dt_s": float(dt_s),
    }


def main() -> None:
    logger = get_logger("phase3.feti_lite_single_gpu")
    p = argparse.ArgumentParser()
    p.add_argument("--partition-report", required=True)
    p.add_argument("--execution-mode", choices=["emulation", "boundary_sync"], default="boundary_sync")
    p.add_argument("--steps", type=int, default=300)
    p.add_argument("--dt-s", type=float, default=0.01)
    p.add_argument("--bandwidth-gbps", type=float, default=32.0)
    p.add_argument("--latency-us", type=float, default=40.0)
    p.add_argument("--compute-us-per-node", type=float, default=0.20)
    p.add_argument("--overlap-cap", type=float, default=0.70)
    p.add_argument("--jitter-pct", type=float, default=0.08)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--max-feti-iters", type=int, default=12)
    p.add_argument("--gap-tol", type=float, default=8e-4)
    p.add_argument("--force-tol", type=float, default=1e-3)
    p.add_argument("--rho", type=float, default=0.6)
    p.add_argument("--relax", type=float, default=0.45)
    p.add_argument("--state-components", type=int, default=5)
    p.add_argument("--min-converged-step-ratio", type=float, default=1.0)
    p.add_argument("--max-sync-stall-ratio", type=float, default=0.36)
    p.add_argument("--max-p99-step-ms", type=float, default=550.0)
    p.add_argument("--max-straggler-ratio", type=float, default=2.4)
    p.add_argument("--min-overlap-ratio", type=float, default=0.35)
    p.add_argument("--out", default="implementation/phase1/feti_lite_sync_report.json")
    args = p.parse_args()

    input_payload = {
        "partition_report": str(args.partition_report),
        "execution_mode": str(args.execution_mode),
        "steps": int(args.steps),
        "dt_s": float(args.dt_s),
        "bandwidth_gbps": float(args.bandwidth_gbps),
        "latency_us": float(args.latency_us),
        "compute_us_per_node": float(args.compute_us_per_node),
        "overlap_cap": float(args.overlap_cap),
        "jitter_pct": float(args.jitter_pct),
        "seed": int(args.seed),
        "max_feti_iters": int(args.max_feti_iters),
        "gap_tol": float(args.gap_tol),
        "force_tol": float(args.force_tol),
        "rho": float(args.rho),
        "relax": float(args.relax),
        "state_components": int(args.state_components),
        "min_converged_step_ratio": float(args.min_converged_step_ratio),
        "max_sync_stall_ratio": float(args.max_sync_stall_ratio),
        "max_p99_step_ms": float(args.max_p99_step_ms),
        "max_straggler_ratio": float(args.max_straggler_ratio),
        "min_overlap_ratio": float(args.min_overlap_ratio),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.feti_lite_single_gpu")
        p_report = _load(str(args.partition_report))
        result = emulate_feti_sync(
            p_report,
            execution_mode=str(args.execution_mode),
            steps=int(args.steps),
            dt_s=float(args.dt_s),
            bandwidth_gbps=float(args.bandwidth_gbps),
            latency_us=float(args.latency_us),
            compute_us_per_node=float(args.compute_us_per_node),
            overlap_cap=float(args.overlap_cap),
            jitter_pct=float(args.jitter_pct),
            seed=int(args.seed),
            max_feti_iters=int(args.max_feti_iters),
            gap_tol=float(args.gap_tol),
            force_tol=float(args.force_tol),
            rho=float(args.rho),
            relax=float(args.relax),
            state_components=int(args.state_components),
        )
        checks = {
            "converged_step_ratio_pass": bool(float(result["converged_step_ratio"]) >= float(args.min_converged_step_ratio)),
            "gap_tol_pass": bool(float(result["max_gap_norm"]) <= float(args.gap_tol)),
            "force_tol_pass": bool(float(result["max_force_imbalance"]) <= float(args.force_tol)),
            "sync_stall_budget_pass": bool(float(result["sync_stall_ratio"]) <= float(args.max_sync_stall_ratio)),
            "p99_step_budget_pass": bool(float(result["p99_step_ms"]) <= float(args.max_p99_step_ms)),
            "straggler_budget_pass": bool(float(result["straggler_ratio"]) <= float(args.max_straggler_ratio)),
            "overlap_ratio_pass": bool(float(result["comm_overlap_ratio"]) >= float(args.min_overlap_ratio)),
        }
        contract_pass = bool(all(checks.values()))
        reason_code = "PASS" if contract_pass else "ERR_SYNC_OVERLOAD"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-feti-lite-single-gpu",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "result": result,
            "checks": checks,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(
            logger,
            20,
            "feti_lite_sync.completed",
            contract_pass=contract_pass,
            reason_code=reason_code,
            converged_step_ratio=result.get("converged_step_ratio"),
        )
        print(f"Wrote feti-lite sync report: {out}")
        if not contract_pass:
            raise SystemExit(1)
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-feti-lite-single-gpu",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote feti-lite sync report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
