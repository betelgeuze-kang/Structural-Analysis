#!/usr/bin/env python3
"""Run repeated Top-k precision experiments and aggregate statistics.

This runner is strict by design:
- no fallback paths
- any failed benchmark run aborts the suite
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import statistics
import subprocess
import sys


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    return statistics.pstdev(xs) if len(xs) >= 2 else 0.0


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.json")
    p.add_argument("--out", default="implementation/phase1/topk_precision_suite_report.json")
    p.add_argument("--work-dir", default="implementation/phase1")
    p.add_argument("--seeds", default="11,17,23,31,47")
    p.add_argument("--epochs", type=int, default=180)
    p.add_argument("--branches", type=int, default=8)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--lr", type=float, default=0.06)
    p.add_argument("--epsilon", type=float, default=0.12)
    p.add_argument("--temperature", type=float, default=0.35)
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--max-drift-error-pct", type=float, default=5.0)
    p.add_argument("--max-base-shear-error-pct", type=float, default=5.0)
    p.add_argument("--min-mode-shape-mac", type=float, default=0.95)
    p.add_argument("--max-buckling-factor-error-pct", type=float, default=5.0)
    p.add_argument("--max-drift-std-pct", type=float, default=0.6)
    p.add_argument("--max-base-shear-std-pct", type=float, default=0.6)
    p.add_argument("--max-buckling-std-pct", type=float, default=0.6)
    p.add_argument("--max-mac-std", type=float, default=0.01)
    p.add_argument("--require-direct-metrics", action="store_true")
    p.add_argument(
        "--accepted-metric-sources",
        default="engine_export_direct,commercial_solver_export",
        help="comma-separated accepted metric_source values when --require-direct-metrics is enabled",
    )
    args = p.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    if len(seeds) == 0:
        raise SystemExit("--seeds must contain at least one integer")

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    per_seed_reports: list[dict] = []
    for seed in seeds:
        hf_out = work_dir / f"hf_benchmark_report.seed_{seed}.json"
        cmp_out = work_dir / f"topk_comparison_experiment_report.seed_{seed}.json"
        cmd = [
            sys.executable,
            "implementation/phase1/benchmark_kpi_contract.py",
            "--cases",
            args.cases,
            "--out",
            str(hf_out),
            "--comparison-out",
            str(cmp_out),
            "--target-split",
            args.target_split,
            "--epochs",
            str(args.epochs),
            "--branches",
            str(args.branches),
            "--top-k",
            str(args.top_k),
            "--lr",
            str(args.lr),
            "--epsilon",
            str(args.epsilon),
            "--temperature",
            str(args.temperature),
            "--seed",
            str(seed),
            "--max-drift-error-pct",
            str(args.max_drift_error_pct),
            "--max-base-shear-error-pct",
            str(args.max_base_shear_error_pct),
            "--min-mode-shape-mac",
            str(args.min_mode_shape_mac),
            "--max-buckling-factor-error-pct",
            str(args.max_buckling_factor_error_pct),
        ]
        if args.require_direct_metrics:
            cmd.extend(
                [
                    "--require-direct-metrics",
                    "--accepted-metric-sources",
                    args.accepted_metric_sources,
                ]
            )
        _run(cmd)
        r = _load(hf_out)
        if not bool(r.get("kpi_pass", False)):
            raise SystemExit(f"seed {seed} failed KPI")
        per_seed_reports.append(
            {
                "seed": seed,
                "hf_report": str(hf_out),
                "comparison_report": str(cmp_out),
                "metrics": r["metrics"],
                "improvement_pct": r.get("comparison", {}).get("improvement_pct", {}),
            }
        )

    drift_vals = [float(r["metrics"]["drift_error_pct"]) for r in per_seed_reports]
    base_vals = [float(r["metrics"]["base_shear_error_pct"]) for r in per_seed_reports]
    mac_vals = [float(r["metrics"]["mode_shape_mac"]) for r in per_seed_reports]
    buck_vals = [float(r["metrics"]["buckling_factor_error_pct"]) for r in per_seed_reports]

    summary_metrics = {
        "drift_error_pct_mean": _mean(drift_vals),
        "drift_error_pct_std": _stdev(drift_vals),
        "base_shear_error_pct_mean": _mean(base_vals),
        "base_shear_error_pct_std": _stdev(base_vals),
        "mode_shape_mac_mean": _mean(mac_vals),
        "mode_shape_mac_std": _stdev(mac_vals),
        "buckling_factor_error_pct_mean": _mean(buck_vals),
        "buckling_factor_error_pct_std": _stdev(buck_vals),
    }

    stable = (
        summary_metrics["drift_error_pct_std"] <= args.max_drift_std_pct
        and summary_metrics["base_shear_error_pct_std"] <= args.max_base_shear_std_pct
        and summary_metrics["buckling_factor_error_pct_std"] <= args.max_buckling_std_pct
        and summary_metrics["mode_shape_mac_std"] <= args.max_mac_std
    )
    quality = (
        summary_metrics["drift_error_pct_mean"] <= args.max_drift_error_pct
        and summary_metrics["base_shear_error_pct_mean"] <= args.max_base_shear_error_pct
        and summary_metrics["buckling_factor_error_pct_mean"] <= args.max_buckling_factor_error_pct
        and summary_metrics["mode_shape_mac_mean"] >= args.min_mode_shape_mac
    )
    suite_pass = bool(stable and quality)

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-topk-precision-suite",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_split": args.target_split,
        "config": {
            "cases": args.cases,
            "seeds": seeds,
            "epochs": int(args.epochs),
            "branches": int(args.branches),
            "top_k": int(args.top_k),
            "lr": float(args.lr),
            "epsilon": float(args.epsilon),
            "temperature": float(args.temperature),
            "require_direct_metrics": bool(args.require_direct_metrics),
            "accepted_metric_sources": [s.strip() for s in str(args.accepted_metric_sources).split(",") if s.strip()],
        },
        "thresholds": {
            "max_drift_error_pct": float(args.max_drift_error_pct),
            "max_base_shear_error_pct": float(args.max_base_shear_error_pct),
            "min_mode_shape_mac": float(args.min_mode_shape_mac),
            "max_buckling_factor_error_pct": float(args.max_buckling_factor_error_pct),
            "max_drift_std_pct": float(args.max_drift_std_pct),
            "max_base_shear_std_pct": float(args.max_base_shear_std_pct),
            "max_buckling_std_pct": float(args.max_buckling_std_pct),
            "max_mac_std": float(args.max_mac_std),
        },
        "summary_metrics": summary_metrics,
        "checks": {
            "quality_pass": quality,
            "stability_pass": stable,
            "suite_pass": suite_pass,
        },
        "per_seed": per_seed_reports,
        "command_example": shlex.join(
            [
                sys.executable,
                "implementation/phase1/run_topk_precision_experiments.py",
                "--cases",
                args.cases,
                "--seeds",
                args.seeds,
                "--top-k",
                str(args.top_k),
            ]
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote Top-k precision suite report: {out}")
    if not suite_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
