#!/usr/bin/env python3
"""Graph partitioning helper with METIS-first strategy.

- Primary backend: pymetis (if installed)
- Fallback backend: deterministic greedy partitioner

Outputs partition-quality report compatible with phase3 hardening gates.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
from typing import Iterable

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "partition quality report generated",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_METIS_REQUIRED": "pymetis backend required but unavailable",
    "ERR_GRAPH_INVALID": "invalid graph input",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["node_count", "k_partitions", "halo_depth", "weight_mode", "out"],
    "properties": {
        "node_count": {"type": "integer", "minimum": 2},
        "edges": {"type": "string"},
        "k_partitions": {"type": "integer", "minimum": 2},
        "halo_depth": {"type": "integer", "minimum": 1},
        "weight_mode": {"type": "string", "enum": ["uniform", "degree", "physics"]},
        "state_components": {"type": "integer", "minimum": 1},
        "max_cut_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_halo_node_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "require_metis": {"type": "boolean"},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_edges(path: Path) -> list[list[int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("edges", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("edge file must contain list or {edges:[...]}")
    out: list[list[int]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        u = int(row[0])
        v = int(row[1])
        if u == v:
            continue
        out.append([u, v])
    return out


def _build_adjacency(node_count: int, edges: list[list[int]]) -> list[list[int]]:
    adj = [[] for _ in range(node_count)]
    for u, v in edges:
        if not (0 <= u < node_count and 0 <= v < node_count):
            continue
        adj[u].append(v)
        adj[v].append(u)
    for i in range(node_count):
        if not adj[i] and node_count > 1:
            j = i - 1 if i > 0 else 1
            adj[i].append(j)
            adj[j].append(i)
        # deterministic unique ordering
        adj[i] = sorted(set(adj[i]))
    return adj


def _greedy_partition(adj: list[list[int]], k_partitions: int) -> list[int]:
    n = len(adj)
    if n == 0:
        return []
    # BFS order from high-degree seeds
    degrees = sorted(range(n), key=lambda i: len(adj[i]), reverse=True)
    visited = [False] * n
    order: list[int] = []
    for seed in degrees:
        if visited[seed]:
            continue
        q: deque[int] = deque([seed])
        visited[seed] = True
        while q:
            u = q.popleft()
            order.append(u)
            for v in adj[u]:
                if not visited[v]:
                    visited[v] = True
                    q.append(v)
    # assign contiguous blocks to minimize edge cut in chain-like orders
    part = [0] * n
    block = max(1, math.ceil(n / max(1, k_partitions)))
    for rank, node in enumerate(order):
        pid = min(k_partitions - 1, rank // block)
        part[node] = int(pid)
    return part


def _partition_metis(adj: list[list[int]], k_partitions: int) -> tuple[str, list[int], bool]:
    try:
        import pymetis  # type: ignore

        _, membership = pymetis.part_graph(int(k_partitions), adjacency=adj)
        return "pymetis", [int(x) for x in membership], True
    except Exception:
        return "greedy_fallback", _greedy_partition(adj, k_partitions), False


def _edge_cut(edges: list[list[int]], part: list[int]) -> int:
    cut = 0
    for u, v in edges:
        if 0 <= u < len(part) and 0 <= v < len(part) and part[u] != part[v]:
            cut += 1
    return cut


def _boundary_nodes(adj: list[list[int]], part: list[int]) -> set[int]:
    out: set[int] = set()
    for u, nbrs in enumerate(adj):
        pu = part[u]
        if any(part[v] != pu for v in nbrs):
            out.add(u)
    return out


def _halo_nodes(adj: list[list[int]], seeds: Iterable[int], depth: int) -> set[int]:
    out: set[int] = set(int(s) for s in seeds)
    if depth <= 1:
        return out
    frontier: set[int] = set(out)
    for _ in range(depth - 1):
        nxt: set[int] = set()
        for u in frontier:
            for v in adj[u]:
                if v not in out:
                    out.add(v)
                    nxt.add(v)
        if not nxt:
            break
        frontier = nxt
    return out


def _estimate_comm_bytes(edge_cut: int, state_components: int) -> float:
    # two-direction exchange per cut edge; float32 state
    return float(edge_cut) * float(max(1, state_components)) * 4.0 * 2.0


def partition_graph(
    *,
    node_count: int,
    edges: list[list[int]],
    k_partitions: int,
    halo_depth: int,
    weight_mode: str,
    state_components: int,
    require_metis: bool,
) -> dict:
    if node_count < 2 or k_partitions < 2:
        raise ValueError("node_count and k_partitions must be >=2")
    if halo_depth < 1:
        raise ValueError("halo_depth must be >=1")
    if weight_mode not in {"uniform", "degree", "physics"}:
        raise ValueError("invalid weight_mode")

    adj = _build_adjacency(node_count, edges)
    backend, part, metis_available = _partition_metis(adj, k_partitions)
    if require_metis and not metis_available:
        raise RuntimeError("pymetis unavailable while require_metis=true")

    cut = _edge_cut(edges, part)
    cut_ratio = float(cut) / float(max(1, len(edges)))

    bnodes = _boundary_nodes(adj, part)
    halo = _halo_nodes(adj, bnodes, halo_depth)
    halo_ratio = float(len(halo)) / float(max(1, node_count))

    part_counts = [0] * k_partitions
    for p in part:
        part_counts[int(p)] += 1
    balance_ratio = float(max(part_counts)) / float(max(1, min(part_counts)))

    comm_bytes = _estimate_comm_bytes(cut, state_components)

    return {
        "backend": backend,
        "metis_available": bool(metis_available),
        "node_count": int(node_count),
        "edge_count": int(len(edges)),
        "k_partitions": int(k_partitions),
        "partition_id_per_node": [int(x) for x in part],
        "partition_sizes": part_counts,
        "edge_cut": int(cut),
        "cut_ratio": float(cut_ratio),
        "halo_depth": int(halo_depth),
        "halo_node_count": int(len(halo)),
        "halo_node_ratio": float(halo_ratio),
        "partition_balance_ratio": float(balance_ratio),
        "estimated_comm_bytes": float(comm_bytes),
    }


def main() -> None:
    logger = get_logger("phase1.graph_partition_metis")
    p = argparse.ArgumentParser()
    p.add_argument("--node-count", type=int, default=20000)
    p.add_argument("--edges", default="")
    p.add_argument("--k-partitions", type=int, default=16)
    p.add_argument("--halo-depth", type=int, default=1)
    p.add_argument("--weight-mode", choices=["uniform", "degree", "physics"], default="degree")
    p.add_argument("--state-components", type=int, default=5)
    p.add_argument("--max-cut-ratio", type=float, default=0.12)
    p.add_argument("--max-halo-node-ratio", type=float, default=0.18)
    p.add_argument("--require-metis", action="store_true")
    p.add_argument("--out", default="implementation/phase1/partition_quality_report.json")
    args = p.parse_args()

    input_payload = {
        "node_count": int(args.node_count),
        "edges": str(args.edges),
        "k_partitions": int(args.k_partitions),
        "halo_depth": int(args.halo_depth),
        "weight_mode": str(args.weight_mode),
        "state_components": int(args.state_components),
        "max_cut_ratio": float(args.max_cut_ratio),
        "max_halo_node_ratio": float(args.max_halo_node_ratio),
        "require_metis": bool(args.require_metis),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.graph_partition_metis")

        if str(args.edges).strip():
            edges = _load_edges(Path(args.edges))
        else:
            # Deterministic chain proxy (cache-friendly default when explicit graph is absent).
            n = int(args.node_count)
            edges = [[i, i + 1] for i in range(n - 1)]

        result = partition_graph(
            node_count=int(args.node_count),
            edges=edges,
            k_partitions=int(args.k_partitions),
            halo_depth=int(args.halo_depth),
            weight_mode=str(args.weight_mode),
            state_components=int(args.state_components),
            require_metis=bool(args.require_metis),
        )

        checks = {
            "edge_cut_ratio_pass": bool(float(result["cut_ratio"]) <= float(args.max_cut_ratio)),
            "halo_node_ratio_pass": bool(float(result["halo_node_ratio"]) <= float(args.max_halo_node_ratio)),
            "metis_backend_pass": bool((not bool(args.require_metis)) or bool(result.get("metis_available", False))),
        }
        contract_pass = bool(all(checks.values()))

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-graph-partition-metis",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "result": result,
            "checks": checks,
            "contract_pass": bool(contract_pass),
            "reason_code": "PASS" if contract_pass else ("ERR_METIS_REQUIRED" if bool(args.require_metis) and not bool(result.get("metis_available", False)) else "ERR_GRAPH_INVALID"),
            "reason": REASONS["PASS"] if contract_pass else (REASONS["ERR_METIS_REQUIRED"] if bool(args.require_metis) and not bool(result.get("metis_available", False)) else REASONS["ERR_GRAPH_INVALID"]),
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "partition.completed", contract_pass=contract_pass, backend=result.get("backend"), cut_ratio=result.get("cut_ratio"))
        print(f"Wrote partition quality report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-graph-partition-metis",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote partition quality report: {out}")
        raise SystemExit(1)
    except RuntimeError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-graph-partition-metis",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_METIS_REQUIRED",
            "reason": f"{REASONS['ERR_METIS_REQUIRED']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote partition quality report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
