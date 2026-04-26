#!/usr/bin/env python3
"""Step-1: active-learning big-data generator for spatio-temporal topology."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random

from spatiotemporal_dataset_utils import (
    CaseConfig,
    build_random_case,
    load_jsonl,
    mutate_hard_case,
    write_jsonl,
)


REASONS = {
    "PASS": "spatio-temporal active-learning dataset generated",
    "ERR_INVALID_INPUT": "invalid generation input",
    "ERR_EMPTY_DATASET": "no generated cases",
}


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        v = str(row.get(key, "unknown"))
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-out", default="implementation/phase1/spatiotemporal_data/dynamic_cases.jsonl")
    p.add_argument("--report-out", default="implementation/phase1/spatiotemporal_data/bigdata_generation_report.json")
    p.add_argument("--base-cases", type=int, default=600)
    p.add_argument("--active-rounds", type=int, default=3)
    p.add_argument("--hard-topk", type=int, default=80)
    p.add_argument("--seq-len", type=int, default=160)
    p.add_argument("--dt", type=float, default=0.01)
    p.add_argument("--coupling-k", type=float, default=2800.0)
    p.add_argument("--seed", type=int, default=23)
    args = p.parse_args()

    if (
        int(args.base_cases) < 10
        or int(args.active_rounds) < 0
        or int(args.hard_topk) < 1
        or int(args.seq_len) < 40
        or float(args.dt) <= 0.0
        or float(args.coupling_k) <= 0.0
    ):
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-spatiotemporal-bigdata-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": REASONS["ERR_INVALID_INPUT"],
        }
        out = Path(args.report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    rng = random.Random(int(args.seed))
    cfg = CaseConfig(seq_len=int(args.seq_len), dt=float(args.dt), coupling_k=float(args.coupling_k))
    rows: list[dict] = []

    for i in range(int(args.base_cases)):
        rows.append(build_random_case(case_id=f"C-{i:07d}", cfg=cfg, rng=rng))

    next_id = len(rows)
    active_new_counts: list[int] = []
    for _round in range(int(args.active_rounds)):
        hard_sorted = sorted(rows, key=lambda x: float(x.get("difficulty_score", 0.0)), reverse=True)
        selected = hard_sorted[: min(len(hard_sorted), int(args.hard_topk))]
        new_rows: list[dict] = []
        for source in selected:
            case_id = f"C-{next_id:07d}"
            next_id += 1
            new_rows.append(mutate_hard_case(source=source, cfg=cfg, new_case_id=case_id, rng=rng))
        rows.extend(new_rows)
        active_new_counts.append(len(new_rows))

    if not rows:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-spatiotemporal-bigdata-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_EMPTY_DATASET",
            "reason": REASONS["ERR_EMPTY_DATASET"],
        }
        out = Path(args.report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    dataset_path = Path(args.dataset_out)
    write_jsonl(dataset_path, rows)
    loaded = load_jsonl(dataset_path)

    hard_count = sum(1 for r in loaded if str(r.get("ood_tag")) != "in_distribution")
    torsion_count = sum(1 for r in loaded if bool(r.get("torsion_sensitive", False)))
    split_counts = _count_by(loaded, "split")
    topo_counts = _count_by(loaded, "topology_type")
    material_counts = _count_by(loaded, "material_type")
    ood_counts = _count_by(loaded, "ood_tag")
    avg_difficulty = sum(float(r.get("difficulty_score", 0.0)) for r in loaded) / max(1, len(loaded))

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-spatiotemporal-bigdata-generator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "base_cases": int(args.base_cases),
            "active_rounds": int(args.active_rounds),
            "hard_topk": int(args.hard_topk),
            "seq_len": int(args.seq_len),
            "dt": float(args.dt),
            "coupling_k": float(args.coupling_k),
            "seed": int(args.seed),
        },
        "outputs": {
            "dataset_path": str(dataset_path),
            "case_count": len(loaded),
            "split_counts": split_counts,
            "topology_counts": topo_counts,
            "material_counts": material_counts,
            "ood_counts": ood_counts,
            "hard_case_count": hard_count,
            "hard_case_ratio": hard_count / max(1, len(loaded)),
            "torsion_sensitive_count": torsion_count,
            "avg_difficulty_score": avg_difficulty,
            "active_learning_new_cases_per_round": active_new_counts,
        },
        "contract_pass": len(loaded) >= int(args.base_cases),
        "reason_code": "PASS",
        "reason": REASONS["PASS"],
    }

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote spatio-temporal dataset: {dataset_path}")
    print(f"Wrote bigdata generation report: {report_path}")
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
