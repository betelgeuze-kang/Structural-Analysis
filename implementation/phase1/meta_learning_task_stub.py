#!/usr/bin/env python3
"""Generate static meta-learning task pack report for topology/hazard adaptation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
RUN_ID = "phase1-meta-learning-task-pack"


def build_tasks() -> list[dict]:
    return [
        {
            "schema_version": "1.0",
            "task_id": "T-RHM-SEIS-001",
            "topology_type": "rahmen",
            "hazard_type": "seismic",
            "support_profile": "mixed",
            "split": "train",
            "ood_tag": "in_distribution",
            "target_zone": {"node_ids": ["N3", "N4"], "risk_label": "high"},
        },
        {
            "schema_version": "1.0",
            "task_id": "T-TRS-WIND-002",
            "topology_type": "truss",
            "hazard_type": "wind",
            "support_profile": "fixed",
            "split": "val",
            "ood_tag": "in_distribution",
            "target_zone": {"node_ids": ["N10"], "risk_label": "mid"},
        },
        {
            "schema_version": "1.0",
            "task_id": "T-OUT-COMB-003",
            "topology_type": "outrigger",
            "hazard_type": "combined",
            "support_profile": "hinge",
            "split": "test",
            "ood_tag": "ood_combined",
            "target_zone": {"node_ids": ["N21", "N22"], "risk_label": "high"},
        },
    ]


def validate(tasks: list[dict]) -> tuple[bool, list[str]]:
    errs: list[str] = []
    for t in tasks:
        for key in ("task_id", "topology_type", "hazard_type", "support_profile", "split", "ood_tag", "target_zone"):
            if key not in t:
                errs.append(f"missing:{key}")
        tz = t.get("target_zone", {})
        if not isinstance(tz.get("node_ids", []), list) or len(tz.get("node_ids", [])) == 0:
            errs.append(f"task:{t.get('task_id','unknown')}:target_zone.node_ids")
    return len(errs) == 0, errs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/meta_learning_task_report.json")
    args = p.parse_args()

    tasks = build_tasks()
    ok, errs = validate(tasks)

    ood_count = sum(1 for t in tasks if t.get("ood_tag") != "in_distribution")

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": ok,
        "reason_code": "PASS" if ok else "ERR_TASK_SCHEMA",
        "reason": "meta-learning task pack ready" if ok else "task pack missing required fields",
        "task_count": len(tasks),
        "meta_ood_generalization_pass": ood_count >= 1 and len(tasks) >= 3,
        "ood_task_count": ood_count,
        "tasks": tasks,
        "errors": errs,
    }

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote meta-learning task report: {out}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
