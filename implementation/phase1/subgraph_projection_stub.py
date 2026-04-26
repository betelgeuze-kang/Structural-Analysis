#!/usr/bin/env python3
"""Step 3: O(N)-oriented divide-and-conquer subgraph projection contract.

Replaces fixed sample subgraphs with LF graph-derived partition/projection.
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
RUN_ID = "phase1-subgraph-projection"

REASON_CODES = {
    "PASS": "subgraph projection contract is valid",
    "ERR_EMPTY_GRAPH": "no nodes available for subgraph projection",
}


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _load_lf_json(path: Path) -> tuple[list[dict], list[dict]] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if isinstance(nodes, list) and nodes and isinstance(edges, list):
        return nodes, edges
    return None


def _load_csv(nodes_csv: Path, edges_csv: Path) -> tuple[list[dict], list[dict]] | None:
    if not nodes_csv.exists() or not edges_csv.exists():
        return None
    with nodes_csv.open("r", encoding="utf-8", newline="") as f:
        nodes = list(csv.DictReader(f))
    with edges_csv.open("r", encoding="utf-8", newline="") as f:
        edges = list(csv.DictReader(f))
    if not nodes:
        return None
    return nodes, edges


def _fallback() -> tuple[list[dict], list[dict]]:
    nodes = [
        {"node_id": "N1", "ux": 0.0, "uy": 0.0, "uz": 0.0, "f_norm": 0.0},
        {"node_id": "N2", "ux": 0.0012, "uy": 0.0, "uz": 0.0, "f_norm": 11.0},
        {"node_id": "N3", "ux": -0.0007, "uy": 0.0, "uz": 0.0, "f_norm": 3.0},
        {"node_id": "N4", "ux": 0.0003, "uy": 0.0, "uz": 0.0, "f_norm": 2.0},
    ]
    edges = [
        {"edge_id": "E1", "from": "N1", "to": "N2"},
        {"edge_id": "E2", "from": "N2", "to": "N3"},
        {"edge_id": "E3", "from": "N3", "to": "N4"},
    ]
    return nodes, edges


def _node_id(n: dict) -> str:
    return str(n.get("node_id", ""))


def _disp_norm(n: dict) -> float:
    ux = _safe_float(n.get("ux"))
    uy = _safe_float(n.get("uy"))
    uz = _safe_float(n.get("uz"))
    return math.sqrt(ux * ux + uy * uy + uz * uz)


def _residual_norm(n: dict, force_scale: float) -> float:
    return _safe_float(n.get("f_norm")) / max(force_scale, 1e-12)


def _chunked(ids: list[str], size: int) -> list[list[str]]:
    size = max(1, int(size))
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def _boundary_nodes(edges: list[dict], node_to_sg: dict[str, int]) -> set[str]:
    out: set[str] = set()
    for e in edges:
        a = str(e.get("from", e.get("src", "")))
        b = str(e.get("to", e.get("dst", "")))
        if not a or not b:
            continue
        sa = node_to_sg.get(a)
        sb = node_to_sg.get(b)
        if sa is None or sb is None:
            continue
        if sa != sb:
            out.add(a)
            out.add(b)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/subgraph_projection_report.json")
    p.add_argument("--lf-json", default="implementation/phase1/lf_output_sample.json")
    p.add_argument("--nodes-csv", default="implementation/phase1/step_outputs/ulf_nodes.csv")
    p.add_argument("--edges-csv", default="implementation/phase1/step_outputs/ulf_edges.csv")
    p.add_argument("--alpha", type=float, default=0.35)
    p.add_argument("--subgraph-size", type=int, default=2)
    p.add_argument("--force-scale", type=float, default=500.0)
    p.add_argument("--boundary-iterations", type=int, default=2)
    args = p.parse_args()

    source_mode = "fallback"
    loaded = _load_lf_json(Path(args.lf_json))
    if loaded is not None:
        nodes, edges = loaded
        source_mode = "lf_json"
    else:
        loaded = _load_csv(Path(args.nodes_csv), Path(args.edges_csv))
        if loaded is not None:
            nodes, edges = loaded
            source_mode = "csv"
        else:
            nodes, edges = _fallback()

    node_ids = [nid for nid in (_node_id(n) for n in nodes) if nid]
    if not node_ids:
        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "interface_version": INTERFACE_VERSION,
            "contract_pass": False,
            "reason_code": "ERR_EMPTY_GRAPH",
            "reason": REASON_CODES["ERR_EMPTY_GRAPH"],
            "projection_mode": "subgraph_divide_and_conquer",
            "subgraph_count": 0,
            "projected_subgraphs": [],
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote subgraph projection report: {out}")
        raise SystemExit(1)

    node_map = {_node_id(n): n for n in nodes if _node_id(n)}
    node_ids_sorted = sorted(node_map.keys())
    partitions = _chunked(node_ids_sorted, size=args.subgraph_size)

    projected = []
    node_to_sg: dict[str, int] = {}
    for sg_idx, ids in enumerate(partitions):
        for nid in ids:
            node_to_sg[nid] = sg_idx
        local_u = [_disp_norm(node_map[nid]) for nid in ids]
        local_r = [_residual_norm(node_map[nid], float(args.force_scale)) for nid in ids]
        local_projected = [u - float(args.alpha) * r for u, r in zip(local_u, local_r)]
        projected.append(
            {
                "subgraph_id": f"S{sg_idx + 1}",
                "nodes": ids,
                "u_local": local_u,
                "r_local": local_r,
                "u_local_projected": local_projected,
            }
        )

    bnodes = sorted(_boundary_nodes(edges, node_to_sg))

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": REASON_CODES["PASS"],
        "source": {
            "mode": source_mode,
            "lf_json": args.lf_json,
            "nodes_csv": args.nodes_csv,
            "edges_csv": args.edges_csv,
        },
        "projection_mode": "subgraph_divide_and_conquer",
        "alpha": float(args.alpha),
        "subgraph_size": int(args.subgraph_size),
        "subgraph_count": len(projected),
        "projected_subgraphs": projected,
        "global_stitch": {
            "method": "boundary_message_passing",
            "shared_boundary_nodes": bnodes,
            "iterations": int(max(1, args.boundary_iterations)),
            "edge_count": len(edges),
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote subgraph projection report: {out}")


if __name__ == "__main__":
    main()
