#!/usr/bin/env python3
"""Phase1 Priority-A: LF -> GNN one-batch E2E smoke.

Loads LF exports (ulf_nodes/ulf_edges/ulf_meta), runs one-batch residual correction
using torch backend when available (fallback: pure python), and emits CI report.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


INTERFACE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.1"
RUN_ID = "phase1-lf-gnn-smoke"

REASON_CODES = {
    "PASS": "one-batch ingestion + correction completed",
    "ERR_EMPTY_NODES": "nodes csv has no rows",
    "ERR_EMPTY_EDGES": "edges csv has no rows",
    "ERR_META_UNIT": "meta.unit_system missing",
    "ERR_EMPTY_CORRECTION": "no corrected nodes emitted",
}


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class CsvBatchLoader:
    def __init__(self, rows: list[dict], batch_size: int) -> None:
        self.rows = rows
        self.batch_size = max(1, batch_size)

    def __iter__(self) -> Iterator[list[dict]]:
        for i in range(0, len(self.rows), self.batch_size):
            yield self.rows[i:i + self.batch_size]


def _apply_residual_batch_python(batch: list[dict], gain: float) -> list[dict]:
    corrected = []
    for n in batch:
        ux = float(n.get("ux", 0.0))
        uy = float(n.get("uy", 0.0))
        uz = float(n.get("uz", 0.0))
        f_norm = float(n.get("f_norm", 0.0))
        du = -gain * f_norm
        corrected.append({"node_id": n.get("node_id"), "ux": ux + du, "uy": uy + du, "uz": uz + du})
    return corrected


def _apply_residual_batch_torch(batch: list[dict], edges: list[dict], meta: dict, gain: float) -> list[dict]:
    from gnn_residual_model import run_one_batch

    return run_one_batch(batch, edges, meta, gain)


def run(nodes_csv: Path, edges_csv: Path, meta_json: Path, batch_size: int, gain: float) -> dict:
    nodes = _read_csv(nodes_csv)
    edges = _read_csv(edges_csv)
    meta = json.loads(meta_json.read_text(encoding="utf-8"))

    loader = CsvBatchLoader(nodes, batch_size=batch_size)

    backend = "python"
    torch_available = False
    try:
        import torch  # type: ignore  # noqa: F401

        torch_available = True
        backend = "torch"
    except Exception:
        torch_available = False

    corrected = []
    batch_count = 0
    for batch in loader:
        batch_count += 1
        if torch_available:
            corrected.extend(_apply_residual_batch_torch(batch, edges, meta, gain=gain))
        else:
            corrected.extend(_apply_residual_batch_python(batch, gain=gain))
        break  # one-batch smoke

    if len(nodes) == 0:
        reason_code = "ERR_EMPTY_NODES"
    elif len(edges) == 0:
        reason_code = "ERR_EMPTY_EDGES"
    elif not bool(meta.get("unit_system")):
        reason_code = "ERR_META_UNIT"
    elif len(corrected) == 0:
        reason_code = "ERR_EMPTY_CORRECTION"
    else:
        reason_code = "PASS"

    pass_cond = reason_code == "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "ingest": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "meta_unit_system": meta.get("unit_system"),
            "meta_solver": meta.get("solver"),
        },
        "inference": {
            "backend": backend,
            "model_module": "gnn_residual_model" if torch_available else "python_fallback",
            "model_api_version": "1.0.0",
            "torch_available": torch_available,
            "batch_size": batch_size,
            "processed_batches": batch_count,
            "processed_nodes": len(corrected),
            "residual_gain": gain,
            "residual_correction_applied": True,
            "sample_corrected_node": corrected[0] if corrected else None,
        },
        "pass": pass_cond,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nodes", default="implementation/phase1/step_outputs/ulf_nodes.csv")
    p.add_argument("--edges", default="implementation/phase1/step_outputs/ulf_edges.csv")
    p.add_argument("--meta", default="implementation/phase1/step_outputs/ulf_meta.json")
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--gain", type=float, default=0.001)
    p.add_argument("--out", default="implementation/phase1/lf_to_gnn_e2e_smoke_report.json")
    args = p.parse_args()

    report = run(Path(args.nodes), Path(args.edges), Path(args.meta), batch_size=args.batch_size, gain=args.gain)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote LF->GNN smoke report: {out}")
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
