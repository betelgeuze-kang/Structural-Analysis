#!/usr/bin/env python3
"""Buckling eigen contract report using LF export-derived surrogates.

Input priority:
1) --lf-json (nodes/edges)
2) --edges-csv + --nodes-csv
3) built-in fallback sample
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.1"
RUN_ID = "phase1-buckling-eigen-contract"

REASON_CODES = {
    "PASS": "buckling eigen contract is valid",
    "ERR_BUCKLING_EIGEN_INVALID": "critical load factor or mode metadata is invalid",
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
    if isinstance(nodes, list) and isinstance(edges, list) and nodes and edges:
        return nodes, edges
    return None


def _load_csv(edges_csv: Path, nodes_csv: Path) -> tuple[list[dict], list[dict]] | None:
    if not edges_csv.exists() or not nodes_csv.exists():
        return None
    with edges_csv.open("r", encoding="utf-8", newline="") as f:
        edges = list(csv.DictReader(f))
    with nodes_csv.open("r", encoding="utf-8", newline="") as f:
        nodes = list(csv.DictReader(f))
    if not edges or not nodes:
        return None
    return nodes, edges


def _fallback() -> tuple[list[dict], list[dict]]:
    nodes = [
        {"node_id": "N1", "ux": 0.0, "uy": 0.0, "uz": 0.0},
        {"node_id": "N2", "ux": 0.0013, "uy": -0.0008, "uz": 0.0004},
    ]
    edges = [
        {"edge_id": "E1", "local_stiffness": 12_700_000.0, "yield_index": 0.62},
        {"edge_id": "E2", "local_stiffness": 8_800_000.0, "yield_index": 0.48},
    ]
    return nodes, edges


def _node_shape(nodes: list[dict]) -> list[float]:
    vals: list[float] = []
    for n in nodes:
        ux = _safe_float(n.get("ux"))
        uy = _safe_float(n.get("uy"))
        uz = _safe_float(n.get("uz"))
        vals.append(math.sqrt(ux * ux + uy * uy + uz * uz))

    if len(vals) == 0:
        return [0.0, 0.42, 1.0, 0.39]
    vmax = max(abs(v) for v in vals)
    if vmax <= 1e-12:
        return [0.0 for _ in vals]
    return [v / vmax for v in vals]


def _eigenvalue_from_edge(edge: dict, mean_stiffness: float, stiffness_gain: float, yield_penalty_gain: float) -> float:
    k = max(_safe_float(edge.get("local_stiffness"), 1.0), 1e-9)
    yi = max(0.0, _safe_float(edge.get("yield_index"), 0.0))
    stiffness_ratio = k / max(mean_stiffness, 1e-9)
    return max(0.2, 2.0 + stiffness_gain * stiffness_ratio - yield_penalty_gain * min(yi, 2.0))


def _build_modes(nodes: list[dict], edges: list[dict], mode_count: int, stiffness_gain: float, yield_penalty_gain: float) -> list[dict]:
    if not edges:
        return []
    mode_count = max(1, int(mode_count))

    stiffnesses = [max(_safe_float(e.get("local_stiffness"), 1.0), 1e-9) for e in edges]
    mean_stiffness = sum(stiffnesses) / len(stiffnesses)
    base_shape = _node_shape(nodes)
    if not base_shape:
        base_shape = [0.0, 0.42, 1.0, 0.39]

    modes: list[dict] = []
    for i in range(mode_count):
        edge = edges[i % len(edges)]
        eigenvalue = _eigenvalue_from_edge(
            edge=edge,
            mean_stiffness=mean_stiffness,
            stiffness_gain=stiffness_gain,
            yield_penalty_gain=yield_penalty_gain,
        )
        decay = max(0.2, 1.0 - 0.08 * i)
        phase = 1.0 if (i % 2 == 0) else -1.0
        normalized_shape = [float(phase * decay * v) for v in base_shape]
        modes.append(
            {
                "mode_id": i + 1,
                "source_edge_id": str(edge.get("edge_id", f"E{i + 1}")),
                "eigenvalue": float(eigenvalue),
                "normalized_shape": normalized_shape,
            }
        )

    return modes


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/buckling_contract_report.json")
    p.add_argument("--lf-json", default="implementation/phase1/lf_output_sample.json")
    p.add_argument("--edges-csv", default="implementation/phase1/step_outputs/ulf_edges.csv")
    p.add_argument("--nodes-csv", default="implementation/phase1/step_outputs/ulf_nodes.csv")
    p.add_argument("--mode-count", type=int, default=2)
    p.add_argument("--stiffness-gain", type=float, default=0.8)
    p.add_argument("--yield-penalty-gain", type=float, default=0.9)
    p.add_argument("--min-critical-load-factor", type=float, default=1.0)
    args = p.parse_args()

    source_mode = "fallback"
    loaded = _load_lf_json(Path(args.lf_json))
    if loaded is not None:
        nodes, edges = loaded
        source_mode = "lf_json"
    else:
        loaded = _load_csv(Path(args.edges_csv), Path(args.nodes_csv))
        if loaded is not None:
            nodes, edges = loaded
            source_mode = "csv"
        else:
            nodes, edges = _fallback()

    modes = _build_modes(
        nodes=nodes,
        edges=edges,
        mode_count=args.mode_count,
        stiffness_gain=float(args.stiffness_gain),
        yield_penalty_gain=float(args.yield_penalty_gain),
    )

    critical_load_factor = min((float(m["eigenvalue"]) for m in modes), default=0.0)
    mode_count = len(modes)
    pass_flag = bool(critical_load_factor >= args.min_critical_load_factor and mode_count > 0)
    reason_code = "PASS" if pass_flag else "ERR_BUCKLING_EIGEN_INVALID"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": pass_flag,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
        "source": {
            "mode": source_mode,
            "lf_json": args.lf_json,
            "edges_csv": args.edges_csv,
            "nodes_csv": args.nodes_csv,
        },
        "critical_load_factor": float(critical_load_factor),
        "mode_count": mode_count,
        "selected_mode": 1 if mode_count > 0 else None,
        "buckling_modes": modes,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote buckling contract report: {out}")
    if not pass_flag:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
