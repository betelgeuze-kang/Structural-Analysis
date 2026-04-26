#!/usr/bin/env python3
"""Run step-1~5 roadmap toward 99.9 dynamic architecture."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


def _run(step: str, cmd: list[str], logs: list[dict]) -> None:
    t0 = time.time()
    subprocess.run(cmd, check=True)
    logs.append(
        {
            "step": step,
            "seconds": time.time() - t0,
            "command": shlex.join(cmd),
        }
    )


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="implementation/phase1/spatiotemporal_data")
    p.add_argument("--dataset", default="implementation/phase1/spatiotemporal_data/dynamic_cases.jsonl")
    p.add_argument("--base-cases", type=int, default=220)
    p.add_argument("--active-rounds", type=int, default=2)
    p.add_argument("--hard-topk", type=int, default=40)
    p.add_argument("--seq-len", type=int, default=120)
    p.add_argument("--epochs-step2", type=int, default=6)
    p.add_argument("--epochs-step3", type=int, default=6)
    p.add_argument("--epochs-step4", type=int, default=6)
    p.add_argument("--max-cases-train", type=int, default=360)
    p.add_argument("--out", default="implementation/phase1/spatiotemporal_data/roadmap_99_9_pipeline_report.json")
    args = p.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    dataset = str(args.dataset)
    bigdata_report = str(root / "bigdata_generation_report.json")
    step2_report = str(root / "tgnn_baseline_report.json")
    step3_report = str(root / "simplicial_tgnn_report.json")
    step4_report = str(root / "neural_operator_report.json")
    step5_report = str(root / "productization_gate_report.json")
    step6_report = "implementation/phase1/phasef_resilience_summary_report.json"

    logs: list[dict] = []

    _run(
        "step1_bigdata_active_learning",
        [
            sys.executable,
            "implementation/phase1/generate_spatiotemporal_bigdata.py",
            "--dataset-out",
            dataset,
            "--report-out",
            bigdata_report,
            "--base-cases",
            str(args.base_cases),
            "--active-rounds",
            str(args.active_rounds),
            "--hard-topk",
            str(args.hard_topk),
            "--seq-len",
            str(args.seq_len),
        ],
        logs,
    )
    _run(
        "step2_tgnn_baseline",
        [
            sys.executable,
            "implementation/phase1/train_tgnn_baseline.py",
            "--dataset",
            dataset,
            "--max-cases",
            str(args.max_cases_train),
            "--epochs",
            str(args.epochs_step2),
            "--out",
            step2_report,
            "--ckpt",
            str(root / "tgnn_baseline.pt"),
        ],
        logs,
    )
    _run(
        "step3_simplicial_tgnn",
        [
            sys.executable,
            "implementation/phase1/train_simplicial_tgnn.py",
            "--dataset",
            dataset,
            "--max-cases",
            str(args.max_cases_train),
            "--epochs",
            str(args.epochs_step3),
            "--baseline-report",
            step2_report,
            "--out",
            step3_report,
            "--ckpt",
            str(root / "simplicial_tgnn.pt"),
        ],
        logs,
    )
    _run(
        "step4_neural_operator",
        [
            sys.executable,
            "implementation/phase1/train_neural_operator_surrogate.py",
            "--dataset",
            dataset,
            "--max-cases",
            str(args.max_cases_train),
            "--epochs",
            str(args.epochs_step4),
            "--out",
            step4_report,
            "--ckpt",
            str(root / "neural_operator.pt"),
        ],
        logs,
    )
    _run(
        "step5_productization_gate",
        [
            sys.executable,
            "implementation/phase1/run_productization_gate.py",
            "--dataset",
            dataset,
            "--simplicial-report",
            step3_report,
            "--dynamic-report",
            "implementation/phase1/dynamic_time_history_report.json",
            "--cache-report",
            "implementation/phase1/branch64_microbatch_profile_report.json",
            "--max-cases",
            str(args.max_cases_train),
            "--out",
            step5_report,
        ],
        logs,
    )
    _run(
        "step6_phasef_resilience_pack",
        [
            sys.executable,
            "implementation/phase1/run_phasef_resilience_modules.py",
            "--out",
            step6_report,
        ],
        logs,
    )

    r1 = _load(bigdata_report)
    r2 = _load(step2_report)
    r3 = _load(step3_report)
    r4 = _load(step4_report)
    r5 = _load(step5_report)
    r6 = _load(step6_report)

    all_pass = bool(
        r1.get("contract_pass", False)
        and r2.get("contract_pass", False)
        and r3.get("contract_pass", False)
        and r4.get("contract_pass", False)
        and r5.get("contract_pass", False)
        and r6.get("contract_pass", False)
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-99_9-roadmap-pipeline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": logs,
        "reports": {
            "step1": bigdata_report,
            "step2": step2_report,
            "step3": step3_report,
            "step4": step4_report,
            "step5": step5_report,
            "step6": step6_report,
        },
        "summary": {
            "dataset_case_count": r1.get("outputs", {}).get("case_count", 0),
            "step2_val_mae_pct": r2.get("validation_metrics", {}).get("mae_pct"),
            "step3_val_mae_pct": r3.get("validation_metrics", {}).get("mae_pct"),
            "step3_torsion_improvement_pct_point": r3.get("comparison_to_baseline", {}).get("torsion_improvement_pct_point"),
            "step4_val_mae_pct": r4.get("validation_metrics", {}).get("mae_pct"),
            "step5_code_pass_ratio": r5.get("code_check_summary", {}).get("pass_ratio"),
            "step5_fallback_trigger_ratio": r5.get("fallback_summary", {}).get("trigger_ratio"),
            "step6_resilience_pass": r6.get("contract_pass"),
        },
        "all_pass": all_pass,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote roadmap 99.9 pipeline report: {out}")
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
