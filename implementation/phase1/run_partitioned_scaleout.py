#!/usr/bin/env python3
"""Partition-aware scale-out runner for 1M/3M/10M DOF gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import shlex
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "partitioned scaleout passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_PARTITION_FAIL": "graph partition quality failed",
    "ERR_REAL_GRAPH_FAIL": "real graph constraints violated",
    "ERR_PROFILE_FAIL": "scaleout profile failed",
    "ERR_CI_MODE_FAIL": "ci-mode specific gate failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dof_levels", "partitions", "branches", "chunk_candidates", "ci_mode", "out"],
    "properties": {
        "dof_levels": {"type": "string", "minLength": 1},
        "partitions": {"type": "integer", "minimum": 2},
        "branches": {"type": "integer", "minimum": 2},
        "chunk_candidates": {"type": "string", "minLength": 1},
        "halo_depth": {"type": "integer", "minimum": 1},
        "sample_nodes": {"type": "integer", "minimum": 1000},
        "state_components": {"type": "integer", "minimum": 1},
        "edge_cut_ratio_max": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "halo_node_ratio_max": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "gpu_strict": {"type": "boolean"},
        "allow_cpu_required": {"type": "boolean"},
        "scaleout_probe_report": {"type": "string"},
        "graph_jsonl": {"type": "string"},
        "edge_list_json": {"type": "string"},
        "min_graph_nodes": {"type": "integer", "minimum": 1},
        "require_real_graph": {"type": "boolean"},
        "max_projection_ratio": {"type": "number", "minimum": 0.0},
        "require_feti_at_or_above_dof": {"type": "integer", "minimum": 0},
        "feti_execution_mode": {"type": "string", "enum": ["emulation", "boundary_sync"]},
        "feti_steps": {"type": "integer", "minimum": 10},
        "feti_bandwidth_gbps": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_latency_us": {"type": "number", "minimum": 0.0},
        "feti_compute_us_per_node": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_overlap_cap": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "feti_jitter_pct": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "feti_max_iters": {"type": "integer", "minimum": 1},
        "feti_gap_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_force_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_rho": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_relax": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "feti_min_converged_step_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "feti_max_sync_stall_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "feti_max_p99_step_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_max_straggler_ratio": {"type": "number", "exclusiveMinimum": 1.0},
        "feti_min_overlap_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "ci_mode": {"type": "string", "enum": ["pr", "nightly"]},
        "work_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _parse_int_csv(text: str) -> list[int]:
    out = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(int(tok))
    out = sorted(set(out))
    if not out:
        raise ValueError("at least one dof level is required")
    return out


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-1600:],
        (proc.stderr or "")[-1600:],
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _log_log_slope(rows: list[dict], value_key: str) -> float | None:
    pts: list[tuple[float, float]] = []
    for row in rows:
        x = float(row.get("node_count", 0))
        y = float(row.get(value_key, math.nan))
        if x > 0.0 and y > 0.0 and math.isfinite(x) and math.isfinite(y):
            pts.append((math.log(x), math.log(y)))
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom <= 1e-12:
        return None
    numer = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return float(numer / denom)


def _finite_or_default(x: object, default: float = math.inf) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    return v if math.isfinite(v) else default


def _is_synthetic_graph_source(path: str) -> bool:
    s = str(Path(path).name).lower()
    return any(tok in s for tok in ("atwood", "demo", "sample", "sanity", "synthetic", "fake"))


def _load_base_graph_from_jsonl(path: str) -> tuple[int, list[list[int]]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"graph jsonl not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            node_count = int(row.get("node_count", 0) or 0)
            edges = row.get("edges")
            if node_count > 1 and isinstance(edges, list) and len(edges) > 0:
                out_edges: list[list[int]] = []
                for e in edges:
                    if isinstance(e, (list, tuple)) and len(e) >= 2:
                        u = int(e[0])
                        v = int(e[1])
                        if 0 <= u < node_count and 0 <= v < node_count and u != v:
                            out_edges.append([u, v])
                if out_edges:
                    return node_count, out_edges
    raise ValueError(f"no valid graph rows found in jsonl: {p}")


def _load_graph_from_edge_json(path: str) -> tuple[int, list[list[int]]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"edge json not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"edge json must be object: {p}")
    node_count = int(payload.get("node_count", 0) or 0)
    edges = payload.get("edges")
    if node_count <= 1 or not isinstance(edges, list) or not edges:
        raise ValueError(f"edge json missing node_count/edges: {p}")
    out: list[list[int]] = []
    for e in edges:
        if isinstance(e, (list, tuple)) and len(e) >= 2:
            u = int(e[0])
            v = int(e[1])
            if 0 <= u < node_count and 0 <= v < node_count and u != v:
                out.append([u, v])
    if not out:
        raise ValueError(f"edge json has no valid edges: {p}")
    return node_count, out


def _expand_graph_edges(base_nodes: int, base_edges: list[list[int]], target_nodes: int) -> list[list[int]]:
    if target_nodes <= 1:
        return []
    if target_nodes <= base_nodes:
        return [[u, v] for u, v in base_edges if u < target_nodes and v < target_nodes]
    reps = int(math.ceil(float(target_nodes) / float(base_nodes)))
    out: list[list[int]] = []
    for r in range(reps):
        off = r * base_nodes
        for u, v in base_edges:
            uu = off + int(u)
            vv = off + int(v)
            if uu < target_nodes and vv < target_nodes:
                out.append([uu, vv])
        # bridge neighboring tiles to keep global connectivity.
        if r > 0:
            left = (r - 1) * base_nodes + (base_nodes - 1)
            right = r * base_nodes
            if left < target_nodes and right < target_nodes:
                out.append([left, right])
    return out


def _archive_outputs(test_name: str, paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name=test_name,
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase3.run_partitioned_scaleout")
    p = argparse.ArgumentParser()
    p.add_argument("--dof-levels", default="1000000,3000000,10000000")
    p.add_argument("--partitions", type=int, default=16)
    p.add_argument("--branches", type=int, default=64)
    p.add_argument("--chunk-candidates", default="64,32,16,8,4,2,1")
    p.add_argument("--halo-depth", type=int, default=1)
    p.add_argument("--sample-nodes", type=int, default=20000)
    p.add_argument("--state-components", type=int, default=5)
    p.add_argument("--min-graph-nodes", type=int, default=200)
    p.add_argument("--max-projection-ratio", type=float, default=2000.0)
    p.add_argument("--edge-cut-ratio-max", type=float, default=0.12)
    p.add_argument("--halo-node-ratio-max", type=float, default=0.18)
    p.add_argument("--gpu-strict", action="store_true")
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--scaleout-probe-report", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    p.add_argument("--graph-jsonl", default="")
    p.add_argument("--edge-list-json", default="")
    p.add_argument("--require-real-graph", action="store_true")
    p.add_argument("--require-feti-at-or-above-dof", type=int, default=3_000_000)
    p.add_argument("--feti-execution-mode", choices=["emulation", "boundary_sync"], default="boundary_sync")
    p.add_argument("--feti-steps", type=int, default=300)
    p.add_argument("--feti-bandwidth-gbps", type=float, default=768.0)
    p.add_argument("--feti-latency-us", type=float, default=0.5)
    p.add_argument("--feti-compute-us-per-node", type=float, default=0.20)
    p.add_argument("--feti-overlap-cap", type=float, default=0.70)
    p.add_argument("--feti-jitter-pct", type=float, default=0.12)
    p.add_argument("--feti-max-iters", type=int, default=12)
    p.add_argument("--feti-gap-tol", type=float, default=8e-4)
    p.add_argument("--feti-force-tol", type=float, default=1e-3)
    p.add_argument("--feti-rho", type=float, default=0.6)
    p.add_argument("--feti-relax", type=float, default=0.45)
    p.add_argument("--feti-min-converged-step-ratio", type=float, default=1.0)
    p.add_argument("--feti-max-sync-stall-ratio", type=float, default=0.36)
    p.add_argument("--feti-max-p99-step-ms", type=float, default=550.0)
    p.add_argument("--feti-max-straggler-ratio", type=float, default=2.4)
    p.add_argument("--feti-min-overlap-ratio", type=float, default=0.35)
    p.add_argument("--ci-mode", choices=["pr", "nightly"], default="pr")
    p.add_argument("--work-dir", default="implementation/phase1/stress/partitioned_scaleout")
    p.add_argument("--out", default="implementation/phase1/partitioned_scaleout_report.json")
    args = p.parse_args()

    input_payload = {
        "dof_levels": str(args.dof_levels),
        "partitions": int(args.partitions),
        "branches": int(args.branches),
        "chunk_candidates": str(args.chunk_candidates),
        "halo_depth": int(args.halo_depth),
        "sample_nodes": int(args.sample_nodes),
        "state_components": int(args.state_components),
        "edge_cut_ratio_max": float(args.edge_cut_ratio_max),
        "halo_node_ratio_max": float(args.halo_node_ratio_max),
        "min_graph_nodes": int(args.min_graph_nodes),
        "gpu_strict": bool(args.gpu_strict),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "scaleout_probe_report": str(args.scaleout_probe_report),
        "graph_jsonl": str(args.graph_jsonl),
        "edge_list_json": str(args.edge_list_json),
        "require_real_graph": bool(args.require_real_graph),
        "max_projection_ratio": float(args.max_projection_ratio),
        "require_feti_at_or_above_dof": int(args.require_feti_at_or_above_dof),
        "feti_execution_mode": str(args.feti_execution_mode),
        "feti_steps": int(args.feti_steps),
        "feti_bandwidth_gbps": float(args.feti_bandwidth_gbps),
        "feti_latency_us": float(args.feti_latency_us),
        "feti_compute_us_per_node": float(args.feti_compute_us_per_node),
        "feti_overlap_cap": float(args.feti_overlap_cap),
        "feti_jitter_pct": float(args.feti_jitter_pct),
        "feti_max_iters": int(args.feti_max_iters),
        "feti_gap_tol": float(args.feti_gap_tol),
        "feti_force_tol": float(args.feti_force_tol),
        "feti_rho": float(args.feti_rho),
        "feti_relax": float(args.feti_relax),
        "feti_min_converged_step_ratio": float(args.feti_min_converged_step_ratio),
        "feti_max_sync_stall_ratio": float(args.feti_max_sync_stall_ratio),
        "feti_max_p99_step_ms": float(args.feti_max_p99_step_ms),
        "feti_max_straggler_ratio": float(args.feti_max_straggler_ratio),
        "feti_min_overlap_ratio": float(args.feti_min_overlap_ratio),
        "ci_mode": str(args.ci_mode),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_partitioned_scaleout")
        levels = _parse_int_csv(args.dof_levels)
        log_event(logger, logging.INFO, "partitioned_scaleout.start", levels=levels, ci_mode=str(args.ci_mode))

        steps: list[dict] = []
        level_rows: list[dict] = []
        base_graph_nodes = 0
        base_graph_edges: list[list[int]] = []
        if bool(args.require_real_graph):
            if not str(args.edge_list_json).strip():
                raise ValueError("--edge-list-json is required when --require-real-graph is enabled")
            if _is_synthetic_graph_source(str(args.edge_list_json)):
                raise ValueError("synthetic graph source is forbidden under strict real-graph mode")
        if str(args.edge_list_json).strip():
            base_graph_nodes, base_graph_edges = _load_graph_from_edge_json(str(args.edge_list_json))
            if int(args.min_graph_nodes) > 0 and base_graph_nodes < int(args.min_graph_nodes):
                raise ValueError(
                    f"base graph node_count={base_graph_nodes} below min_graph_nodes={int(args.min_graph_nodes)}"
                )
        elif str(args.graph_jsonl).strip():
            base_graph_nodes, base_graph_edges = _load_base_graph_from_jsonl(str(args.graph_jsonl))
            if bool(args.require_real_graph) and _is_synthetic_graph_source(str(args.graph_jsonl)):
                raise ValueError("synthetic graph source is forbidden under strict real-graph mode")

        for n in levels:
            # Partition quality on representative sampled graph (keeps runtime bounded)
            sample_nodes = int(min(max(1000, int(args.sample_nodes)), max(1000, int(n))))
            projection_ratio = math.inf
            max_projection_ratio = float(args.max_projection_ratio)
            projection_ratio_pass = True
            if base_graph_nodes > 0:
                projection_ratio = float(n) / float(base_graph_nodes)
                projection_ratio_pass = max_projection_ratio <= 0.0 or projection_ratio <= max_projection_ratio
            part_out = work_dir / f"partition_quality_n{int(n)}.json"
            part_cmd = [
                sys.executable,
                "implementation/phase1/graph_partition_metis.py",
                "--node-count",
                str(sample_nodes),
                "--k-partitions",
                str(int(args.partitions)),
                "--halo-depth",
                str(int(args.halo_depth)),
                "--state-components",
                str(int(args.state_components)),
                "--max-cut-ratio",
                str(float(args.edge_cut_ratio_max)),
                "--max-halo-node-ratio",
                str(float(args.halo_node_ratio_max)),
                "--out",
                str(part_out),
            ]
            real_graph_used = False
            if base_graph_nodes > 1 and len(base_graph_edges) > 0:
                expanded = _expand_graph_edges(base_graph_nodes, base_graph_edges, sample_nodes)
                if expanded:
                    edge_file = work_dir / f"partition_edges_n{int(n)}.json"
                    edge_file.write_text(json.dumps({"edges": expanded}), encoding="utf-8")
                    part_cmd.extend(["--edges", str(edge_file)])
                    real_graph_used = True

            ok_p, sec_p, rc_p, out_p, err_p = _run(part_cmd)
            steps.append(
                {
                    "step": "partition_quality",
                    "node_count": int(n),
                    "projection_ratio": float(projection_ratio),
                    "projection_ratio_pass": bool(projection_ratio_pass),
                    "graph_source": str(args.edge_list_json) if str(args.edge_list_json).strip() else str(args.graph_jsonl),
                    "graph_source_real": bool(base_graph_nodes > 1 and not _is_synthetic_graph_source(str(args.edge_list_json or args.graph_jsonl))),
                    "real_graph_used": bool(real_graph_used),
                    "seconds": float(sec_p),
                    "return_code": int(rc_p),
                    "command": shlex.join(part_cmd),
                    "stdout_tail": out_p,
                    "stderr_tail": err_p,
                }
            )
            if not part_out.exists():
                feti_required = int(args.require_feti_at_or_above_dof) > 0 and int(n) >= int(args.require_feti_at_or_above_dof)
                level_rows.append(
                    {
                        "node_count": int(n),
                        "profiled_node_count": int(sample_nodes),
                        "projection_ratio": float(projection_ratio),
                        "projection_ratio_pass": bool(projection_ratio_pass),
                        "graph_source_real": bool(
                            base_graph_nodes > 1
                            and not _is_synthetic_graph_source(str(args.edge_list_json or args.graph_jsonl))
                        ),
                        "scaleout_graph_source_real": bool(
                            base_graph_nodes > 1
                            and not _is_synthetic_graph_source(str(args.edge_list_json or args.graph_jsonl))
                        ),
                        "real_graph_used": bool(real_graph_used),
                        "partition_report": str(part_out),
                        "scaleout_report": "",
                        "partition_contract_pass": False,
                        "partition_cut_ratio": math.inf,
                        "partition_halo_node_ratio": math.inf,
                        "partition_balance_ratio": math.inf,
                        "partition_estimated_comm_bytes": math.inf,
                        "partition_quality_threshold_pass": False,
                        "scaleout_contract_pass": False,
                        "scaleout_gpu_strict_pass": False,
                        "scaleout_1m_microbatch_pass": False,
                        "feti_required": bool(feti_required),
                        "feti_sync_report": "",
                        "feti_sync_contract_pass": False,
                        "feti_backend": "",
                        "feti_converged_step_ratio": 0.0,
                        "feti_sync_stall_ratio": math.inf,
                        "feti_p99_step_ms": math.inf,
                        "feti_straggler_ratio": math.inf,
                        "feti_comm_overlap_ratio": 0.0,
                        "feti_p95_iterations": math.inf,
                        "recommended_working_set_mb": math.inf,
                        "recommended_avg_branch_ms": math.inf,
                        "projected_total_working_set_mb": math.inf,
                        "projected_total_avg_branch_ms": math.inf,
                    }
                )
                continue
            part = _load_json(part_out)
            part_res = part.get("result") if isinstance(part.get("result"), dict) else {}
            part_sizes = part_res.get("partition_sizes") if isinstance(part_res.get("partition_sizes"), list) else []
            max_part_nodes = max([int(x) for x in part_sizes if isinstance(x, (int, float))], default=sample_nodes)
            halo_ratio = _finite_or_default(part_res.get("halo_node_ratio", 0.0), 0.0)
            part_fraction = float(max_part_nodes) / float(max(1, sample_nodes))
            profiled_nodes = int(max(1000, math.ceil(float(n) * part_fraction * (1.0 + max(0.0, halo_ratio)))))
            # Keep profiled node size bounded by physical node count.
            profiled_nodes = min(int(n), profiled_nodes)

            # Scaleout profile at requested DOF
            scale_out = work_dir / f"scaleout_n{int(n)}.json"
            sc_cmd = [
                sys.executable,
                "implementation/phase1/run_scaleout_io_profile.py",
                "--dof-levels",
                str(int(profiled_nodes)),
                "--branches",
                str(int(args.branches)),
                "--chunk-candidates",
                str(args.chunk_candidates),
                "--state-components",
                str(int(args.state_components)),
                "--out",
                str(scale_out),
                "--disable-1m-gate",
                *( ["--probe-report-in", str(args.scaleout_probe_report)] if str(args.scaleout_probe_report).strip() else [] ),
                *( ["--gpu-strict"] if bool(args.gpu_strict) else [] ),
                *( ["--allow-cpu-required"] if bool(args.allow_cpu_required) else [] ),
            ]
            ok_s, sec_s, rc_s, out_s, err_s = _run(sc_cmd)
            steps.append(
                {
                    "step": "scaleout_profile",
                    "node_count": int(n),
                    "seconds": float(sec_s),
                    "return_code": int(rc_s),
                    "command": shlex.join(sc_cmd),
                    "stdout_tail": out_s,
                    "stderr_tail": err_s,
                }
            )
            sc = _load_json(scale_out) if scale_out.exists() else {}
            sc_rows = sc.get("level_rows") if isinstance(sc.get("level_rows"), list) else []
            sc_first = sc_rows[0] if sc_rows else {}
            rec_ws_mb = _finite_or_default(sc_first.get("recommended_working_set_mb", math.inf))
            rec_lat_ms = _finite_or_default(sc_first.get("recommended_avg_branch_ms", math.inf))
            feti_required = int(args.require_feti_at_or_above_dof) > 0 and int(n) >= int(args.require_feti_at_or_above_dof)
            feti_report = work_dir / f"feti_sync_n{int(n)}.json"
            feti_contract_pass = not bool(feti_required)
            feti_backend = ""
            feti_converged_step_ratio = 0.0
            feti_sync_stall_ratio = 0.0
            feti_p99_step_ms = 0.0
            feti_straggler_ratio = 0.0
            feti_comm_overlap_ratio = 0.0
            feti_p95_iterations = 0.0
            if bool(feti_required):
                feti_cmd = [
                    sys.executable,
                    "implementation/phase1/feti_lite_single_gpu.py",
                    "--partition-report",
                    str(part_out),
                    "--execution-mode",
                    str(args.feti_execution_mode),
                    "--steps",
                    str(int(args.feti_steps)),
                    "--bandwidth-gbps",
                    str(float(args.feti_bandwidth_gbps)),
                    "--latency-us",
                    str(float(args.feti_latency_us)),
                    "--compute-us-per-node",
                    str(float(args.feti_compute_us_per_node)),
                    "--overlap-cap",
                    str(float(args.feti_overlap_cap)),
                    "--jitter-pct",
                    str(float(args.feti_jitter_pct)),
                    "--max-feti-iters",
                    str(int(args.feti_max_iters)),
                    "--gap-tol",
                    str(float(args.feti_gap_tol)),
                    "--force-tol",
                    str(float(args.feti_force_tol)),
                    "--rho",
                    str(float(args.feti_rho)),
                    "--relax",
                    str(float(args.feti_relax)),
                    "--min-converged-step-ratio",
                    str(float(args.feti_min_converged_step_ratio)),
                    "--max-sync-stall-ratio",
                    str(float(args.feti_max_sync_stall_ratio)),
                    "--max-p99-step-ms",
                    str(float(args.feti_max_p99_step_ms)),
                    "--max-straggler-ratio",
                    str(float(args.feti_max_straggler_ratio)),
                    "--min-overlap-ratio",
                    str(float(args.feti_min_overlap_ratio)),
                    "--out",
                    str(feti_report),
                ]
                ok_f, sec_f, rc_f, out_f, err_f = _run(feti_cmd)
                steps.append(
                    {
                        "step": "feti_sync_profile",
                        "node_count": int(n),
                        "seconds": float(sec_f),
                        "return_code": int(rc_f),
                        "command": shlex.join(feti_cmd),
                        "stdout_tail": out_f,
                        "stderr_tail": err_f,
                    }
                )
                feti_payload = _load_json(feti_report) if feti_report.exists() else {}
                feti_result = feti_payload.get("result") if isinstance(feti_payload.get("result"), dict) else {}
                feti_contract_pass = bool(ok_f and feti_payload.get("contract_pass", False))
                feti_backend = str(feti_result.get("backend", ""))
                feti_converged_step_ratio = _finite_or_default(feti_result.get("converged_step_ratio", 0.0), 0.0)
                feti_sync_stall_ratio = _finite_or_default(feti_result.get("sync_stall_ratio", math.inf))
                feti_p99_step_ms = _finite_or_default(feti_result.get("p99_step_ms", math.inf))
                feti_straggler_ratio = _finite_or_default(feti_result.get("straggler_ratio", math.inf))
                feti_comm_overlap_ratio = _finite_or_default(feti_result.get("comm_overlap_ratio", 0.0), 0.0)
                feti_p95_iterations = _finite_or_default(feti_result.get("p95_feti_iterations", math.inf))
            projected_total_ws_mb = rec_ws_mb * float(int(args.partitions))
            projected_total_lat_ms = rec_lat_ms * float(int(args.partitions))
            part_cut_ratio = float((part.get("result") or {}).get("cut_ratio", math.inf))
            part_halo_ratio = float((part.get("result") or {}).get("halo_node_ratio", math.inf))
            partition_quality_threshold_pass = bool(
                math.isfinite(part_cut_ratio)
                and math.isfinite(part_halo_ratio)
                and part_cut_ratio <= float(args.edge_cut_ratio_max)
                and part_halo_ratio <= float(args.halo_node_ratio_max)
            )

            level_rows.append(
                {
                    "node_count": int(n),
                    "profiled_node_count": int(profiled_nodes),
                    "projection_ratio": float(projection_ratio),
                    "projection_ratio_pass": bool(projection_ratio_pass),
                    "graph_source_real": bool(
                        base_graph_nodes > 1
                        and not _is_synthetic_graph_source(str(args.edge_list_json or args.graph_jsonl))
                    ),
                    "scaleout_graph_source_real": bool(base_graph_nodes > 1 and not _is_synthetic_graph_source(str(args.edge_list_json or args.graph_jsonl))),
                    "real_graph_used": bool(real_graph_used),
                    "partition_report": str(part_out),
                    "scaleout_report": str(scale_out),
                    "partition_contract_pass": bool(part.get("contract_pass", False)),
                    "partition_cut_ratio": float(part_cut_ratio),
                    "partition_halo_node_ratio": float(part_halo_ratio),
                    "partition_balance_ratio": float((part.get("result") or {}).get("partition_balance_ratio", math.inf)),
                    "partition_estimated_comm_bytes": float((part.get("result") or {}).get("estimated_comm_bytes", math.inf)),
                    "partition_quality_threshold_pass": bool(partition_quality_threshold_pass),
                    "scaleout_contract_pass": bool(sc.get("contract_pass", False)),
                    "scaleout_gpu_strict_pass": bool((sc.get("checks") or {}).get("gpu_strict_pass", not bool(args.gpu_strict))),
                    "scaleout_1m_microbatch_pass": bool((sc.get("checks") or {}).get("scaleout_1m_microbatch_pass", False)),
                    "feti_required": bool(feti_required),
                    "feti_sync_report": str(feti_report) if bool(feti_required) else "",
                    "feti_sync_contract_pass": bool(feti_contract_pass),
                    "feti_backend": str(feti_backend),
                    "feti_converged_step_ratio": float(feti_converged_step_ratio),
                    "feti_sync_stall_ratio": float(feti_sync_stall_ratio),
                    "feti_p99_step_ms": float(feti_p99_step_ms),
                    "feti_straggler_ratio": float(feti_straggler_ratio),
                    "feti_comm_overlap_ratio": float(feti_comm_overlap_ratio),
                    "feti_p95_iterations": float(feti_p95_iterations),
                    "recommended_working_set_mb": float(rec_ws_mb),
                    "recommended_avg_branch_ms": float(rec_lat_ms),
                    "projected_total_working_set_mb": float(projected_total_ws_mb),
                    "projected_total_avg_branch_ms": float(projected_total_lat_ms),
                }
            )

        # Mode-specific gate
        by_n = {int(r["node_count"]): r for r in level_rows}
        pr_required = [x for x in (1_000_000, 3_000_000) if x in by_n]
        nightly_required = [x for x in (1_000_000, 3_000_000, 10_000_000) if x in by_n]

        def _row_pass(row: dict) -> bool:
            feti_ok = (
                not bool(row.get("feti_required", False))
                or (
                    bool(row.get("feti_sync_contract_pass", False))
                    and str(row.get("feti_backend", "")).startswith("feti_lite")
                )
            )
            return bool(
                row.get("partition_contract_pass", False)
                and row.get("partition_quality_threshold_pass", False)
                and row.get("scaleout_contract_pass", False)
                and row.get("scaleout_gpu_strict_pass", True)
                and feti_ok
            )

        pr_scale_pass = bool(pr_required) and all(_row_pass(by_n[n]) for n in pr_required)
        nightly_scale_pass = bool(nightly_required) and all(_row_pass(by_n[n]) for n in nightly_required)
        feti_required_rows = [r for r in level_rows if bool(r.get("feti_required", False))]
        feti_required_levels_pass = bool(feti_required_rows) and all(_row_pass(r) for r in feti_required_rows)

        mem_slope = _log_log_slope(level_rows, "projected_total_working_set_mb")
        lat_slope = _log_log_slope(level_rows, "projected_total_avg_branch_ms")
        # O(N)-friendly envelope: roughly linear/sublinear memory, weakly superlinear latency.
        on_scaling_regression_pass = bool(
            (mem_slope is not None and mem_slope <= 1.35)
            and (lat_slope is not None and lat_slope <= 1.60)
        )
        real_graph_used_all = all(bool(r.get("real_graph_used", False)) for r in level_rows) if level_rows else False

        if any(not bool(r.get("partition_contract_pass", False)) for r in level_rows):
            reason_code = "ERR_PARTITION_FAIL"
        elif any(not bool(r.get("partition_quality_threshold_pass", False)) for r in level_rows):
            reason_code = "ERR_PARTITION_FAIL"
        elif bool(args.require_real_graph) and any(
            not bool(r.get("graph_source_real", False)) for r in level_rows
        ):
            reason_code = "ERR_REAL_GRAPH_FAIL"
        elif bool(args.require_real_graph) and not real_graph_used_all:
            reason_code = "ERR_REAL_GRAPH_FAIL"
        elif any(not bool(r.get("projection_ratio_pass", False)) for r in level_rows):
            reason_code = "ERR_REAL_GRAPH_FAIL"
        elif any(not bool(r.get("scaleout_contract_pass", False)) for r in level_rows):
            reason_code = "ERR_PROFILE_FAIL"
        elif any(bool(r.get("feti_required", False)) and not bool(r.get("feti_sync_contract_pass", False)) for r in level_rows):
            reason_code = "ERR_PROFILE_FAIL"
        elif str(args.ci_mode) == "pr" and (not pr_scale_pass or not on_scaling_regression_pass):
            reason_code = "ERR_CI_MODE_FAIL"
        elif str(args.ci_mode) == "nightly" and (not nightly_scale_pass or not on_scaling_regression_pass):
            reason_code = "ERR_CI_MODE_FAIL"
        else:
            reason_code = "PASS"

        contract_pass = bool(reason_code == "PASS")

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-partitioned-scaleout",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": {
                "pr_scale_pass": bool(pr_scale_pass),
                "nightly_scale_pass": bool(nightly_scale_pass),
                "gpu_strict_required": bool(args.gpu_strict),
                "gpu_strict_pass": all(bool(r.get("scaleout_gpu_strict_pass", True)) for r in level_rows),
                "feti_required_levels_pass": bool(feti_required_levels_pass or not feti_required_rows),
                "feti_required_level_count": int(len(feti_required_rows)),
                "on_scaling_regression_pass": bool(on_scaling_regression_pass),
                "real_graph_required": bool(args.require_real_graph),
                "real_graph_used": bool(real_graph_used_all),
                "real_graph_source": str(args.edge_list_json) if str(args.edge_list_json).strip() else str(args.graph_jsonl),
                "graph_source_is_real": bool(not _is_synthetic_graph_source(str(args.edge_list_json or args.graph_jsonl))),
                "max_projection_ratio": float(args.max_projection_ratio),
                "projection_ratio_enforced": bool(float(args.max_projection_ratio) > 0.0),
                "projection_ratio_pass": bool(all(bool(r.get("projection_ratio_pass", False)) for r in level_rows)),
                "partition_quality_threshold_pass": bool(
                    all(bool(r.get("partition_quality_threshold_pass", False)) for r in level_rows)
                ),
            },
            "complexity_regression": {
                "memory_loglog_slope": None if mem_slope is None else float(mem_slope),
                "latency_loglog_slope": None if lat_slope is None else float(lat_slope),
                "memory_slope_limit": 1.35,
                "latency_slope_limit": 1.60,
            },
            "level_rows": level_rows,
            "steps": steps,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name=f"partitioned_scaleout_{str(args.ci_mode)}",
            paths=[str(args.out), str(args.work_dir)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "partitioned_scaleout.completed", contract_pass=contract_pass, ci_mode=str(args.ci_mode))
        print(f"Wrote partitioned scaleout report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-partitioned-scaleout",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name=f"partitioned_scaleout_{str(args.ci_mode)}",
            paths=[str(args.out), str(args.work_dir)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote partitioned scaleout report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
