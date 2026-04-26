#!/usr/bin/env python3
"""Phase-C1 tunnel ring/segment graph converter (BIM/CAD -> graph scaffold)."""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "tunnel ring-segment graph conversion succeeded",
    "ERR_INVALID_INPUT": "invalid tunnel graph conversion input",
    "ERR_GRAPH_INVALID": "graph topology is disconnected or inconsistent",
}

TUNNEL_GRAPH_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "ring_count",
        "segments_per_ring",
        "ring_spacing_m",
        "radius_m",
        "out_graph",
        "out",
    ],
    "properties": {
        "ring_count": {"type": "integer", "minimum": 2},
        "segments_per_ring": {"type": "integer", "minimum": 3},
        "ring_spacing_m": {"type": "number", "exclusiveMinimum": 0.0},
        "radius_m": {"type": "number", "exclusiveMinimum": 0.0},
        "out_graph": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _node_id(ring: int, seg: int) -> str:
    return f"R{ring:04d}_S{seg:03d}"


def _build_graph(
    *,
    ring_count: int,
    segments_per_ring: int,
    ring_spacing_m: float,
    radius_m: float,
) -> tuple[list[dict], list[dict]]:
    nodes: list[dict] = []
    edges: list[dict] = []

    for r in range(ring_count):
        z = float(r) * float(ring_spacing_m)
        for s in range(segments_per_ring):
            th = (2.0 * math.pi * float(s)) / float(segments_per_ring)
            x = float(radius_m) * math.cos(th)
            y = float(radius_m) * math.sin(th)
            nodes.append(
                {
                    "node_id": _node_id(r, s),
                    "ring_index": int(r),
                    "segment_index": int(s),
                    "xyz_m": [x, y, z],
                }
            )

    # Circumferential edges
    for r in range(ring_count):
        for s in range(segments_per_ring):
            s_next = (s + 1) % segments_per_ring
            edges.append(
                {
                    "edge_id": f"E_CIRC_{r:04d}_{s:03d}",
                    "src": _node_id(r, s),
                    "dst": _node_id(r, s_next),
                    "kind": "circumferential_joint",
                }
            )

    # Longitudinal edges (ring-to-ring)
    for r in range(ring_count - 1):
        for s in range(segments_per_ring):
            edges.append(
                {
                    "edge_id": f"E_LONG_{r:04d}_{s:03d}",
                    "src": _node_id(r, s),
                    "dst": _node_id(r + 1, s),
                    "kind": "ring_joint",
                }
            )

    return nodes, edges


def _is_connected(nodes: list[dict], edges: list[dict]) -> bool:
    if not nodes:
        return False
    adj: dict[str, list[str]] = {str(n["node_id"]): [] for n in nodes}
    for e in edges:
        s = str(e["src"])
        d = str(e["dst"])
        if s in adj and d in adj:
            adj[s].append(d)
            adj[d].append(s)

    start = str(nodes[0]["node_id"])
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return len(seen) == len(nodes)


def main() -> None:
    logger = get_logger("phase1.tunnel_graph_converter")
    p = argparse.ArgumentParser()
    p.add_argument("--ring-count", type=int, default=80)
    p.add_argument("--segments-per-ring", type=int, default=7)
    p.add_argument("--ring-spacing-m", type=float, default=1.5)
    p.add_argument("--radius-m", type=float, default=4.1)
    p.add_argument("--out-graph", default="implementation/phase1/tunnel_graph.json")
    p.add_argument("--out", default="implementation/phase1/tunnel_graph_converter_report.json")
    args = p.parse_args()

    try:
        input_payload = {
            "ring_count": int(args.ring_count),
            "segments_per_ring": int(args.segments_per_ring),
            "ring_spacing_m": float(args.ring_spacing_m),
            "radius_m": float(args.radius_m),
            "out_graph": str(args.out_graph),
            "out": str(args.out),
        }
        validate_input_contract(
            input_payload,
            TUNNEL_GRAPH_INPUT_SCHEMA,
            label="phase-c1.tunnel_graph_converter",
        )
        log_event(logger, logging.INFO, "tunnel_graph.start", inputs=input_payload)
        ring_count = input_payload["ring_count"]
        segs = input_payload["segments_per_ring"]
        spacing = input_payload["ring_spacing_m"]
        radius = input_payload["radius_m"]

        nodes, edges = _build_graph(
            ring_count=ring_count,
            segments_per_ring=segs,
            ring_spacing_m=spacing,
            radius_m=radius,
        )

        expected_nodes = ring_count * segs
        expected_edges = ring_count * segs + (ring_count - 1) * segs
        connected = _is_connected(nodes, edges)
        counts_ok = (len(nodes) == expected_nodes) and (len(edges) == expected_edges)

        if not connected or not counts_ok:
            reason_code = "ERR_GRAPH_INVALID"
        else:
            reason_code = "PASS"

        graph_payload = {
            "schema_version": "1.0",
            "domain": "tunnel",
            "graph_type": "ring_segment_multigraph",
            "nodes": nodes,
            "edges": edges,
        }
        out_graph = Path(args.out_graph)
        out_graph.parent.mkdir(parents=True, exist_ok=True)
        out_graph.write_text(json.dumps(graph_payload, indent=2), encoding="utf-8")

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-graph-converter",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "ring_count": ring_count,
                "segments_per_ring": segs,
                "ring_spacing_m": spacing,
                "radius_m": radius,
            },
            "outputs": {
                "graph_json": str(out_graph),
            },
            "metrics": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "expected_node_count": expected_nodes,
                "expected_edge_count": expected_edges,
            },
            "checks": {
                "counts_match": bool(counts_ok),
                "connected_graph": bool(connected),
            },
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        log_event(
            logger,
            logging.INFO,
            "tunnel_graph.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "tunnel_graph.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-graph-converter",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "tunnel_graph.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-graph-converter",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote tunnel graph converter report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
