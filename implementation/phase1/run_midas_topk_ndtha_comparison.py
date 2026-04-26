#!/usr/bin/env python3
"""Run Top-k + NDTHA comparison bundle and emit a single summary report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs


REASONS = {
    "PASS": "midas topk+ndtha comparison passed",
    "ERR_TOPK_FAIL": "top-k precision suite failed",
    "ERR_NDTHA_FAIL": "ndtha stress gate failed",
    "ERR_SUMMARY_FAIL": "summary gate failed",
}


def _run(step: str, cmd: list[str], steps: list[dict]) -> bool:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    steps.append(
        {
            "step": step,
            "seconds": float(dt),
            "return_code": int(proc.returncode),
            "command": shlex.join(cmd),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    )
    return proc.returncode == 0


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="midas_topk_ndtha_comparison",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--midas-conversion-report", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--topk-seeds", default="11,23,47")
    p.add_argument("--topk-epochs", type=int, default=180)
    p.add_argument("--topk-branches", type=int, default=8)
    p.add_argument("--topk-k", type=int, default=3)
    p.add_argument("--topk-target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--ndtha-target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--ndtha-min-case-count", type=int, default=3)
    p.add_argument("--ndtha-max-case-count", type=int, default=6)
    p.add_argument("--ndtha-ag-scale", type=float, default=2.0)
    p.add_argument("--topk-out", default="implementation/phase1/topk_precision_suite_report.midas_bundle.json")
    p.add_argument("--ndtha-out", default="implementation/phase1/nonlinear_ndtha_stress_report.midas_bundle.json")
    p.add_argument("--out", default="implementation/phase1/midas_topk_ndtha_comparison_report.json")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    steps: list[dict] = []
    reason_code = "PASS"

    cmd_topk = [
        sys.executable,
        "implementation/phase1/run_topk_precision_experiments.py",
        "--cases",
        str(args.cases),
        "--seeds",
        str(args.topk_seeds),
        "--epochs",
        str(int(args.topk_epochs)),
        "--branches",
        str(int(args.topk_branches)),
        "--top-k",
        str(int(args.topk_k)),
        "--target-split",
        str(args.topk_target_split),
        "--require-direct-metrics",
        "--out",
        str(args.topk_out),
    ]
    if reason_code == "PASS" and not _run("topk_precision_suite", cmd_topk, steps):
        reason_code = "ERR_TOPK_FAIL"

    cmd_ndtha = [
        sys.executable,
        "implementation/phase1/run_nonlinear_ndtha_stress.py",
        "--cases",
        str(args.cases),
        "--target-split",
        str(args.ndtha_target_split),
        "--ground-motion-csv",
        str(args.ground_motion_csv),
        "--min-case-count",
        str(int(args.ndtha_min_case_count)),
        "--max-case-count",
        str(int(args.ndtha_max_case_count)),
        "--ag-scale",
        str(float(args.ndtha_ag_scale)),
        "--yield-drift-scale",
        "0.45",
        "--hardening-ratio",
        "0.2",
        "--pdelta-factor",
        "1.0",
        "--max-step-iterations",
        "16",
        "--step-tol",
        "1e-4",
        "--adaptive-load-decay",
        "0.82",
        "--damping-force-cap-ratio",
        "0.6",
        "--max-steps",
        "2400",
        "--min-load-reversals",
        "20",
        "--min-plastic-story-count",
        "1",
        "--collapse-drift-threshold-pct",
        "10.0",
        "--rayleigh-alpha",
        "0.03",
        "--rayleigh-beta",
        "1e-6",
        "--accepted-metric-sources",
        "commercial_solver_export,engine_export_direct",
        "--out",
        str(args.ndtha_out),
    ]
    if reason_code == "PASS" and not _run("ndtha_stress_bundle", cmd_ndtha, steps):
        reason_code = "ERR_NDTHA_FAIL"

    topk = _load(str(args.topk_out))
    ndtha = _load(str(args.ndtha_out))
    mgt = _load(str(args.midas_conversion_report))

    topk_pass = bool((topk.get("checks") or {}).get("suite_pass", False))
    ndtha_checks = ndtha.get("checks") if isinstance(ndtha.get("checks"), dict) else {}
    ndtha_summary = ndtha.get("summary") if isinstance(ndtha.get("summary"), dict) else {}
    ndtha_pass = bool(
        ndtha.get("contract_pass", False)
        and bool(ndtha_checks.get("all_cases_converged", False))
        and bool(ndtha_checks.get("plasticity_triggered_all_cases", False))
    )
    mgt_pass = bool(mgt.get("contract_pass", False))

    if reason_code == "PASS" and not (topk_pass and ndtha_pass and mgt_pass):
        reason_code = "ERR_SUMMARY_FAIL"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-midas-topk-ndtha-comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "cases": str(args.cases),
            "ground_motion_csv": str(args.ground_motion_csv),
            "midas_conversion_report": str(args.midas_conversion_report),
            "topk_seeds": str(args.topk_seeds),
            "topk_epochs": int(args.topk_epochs),
            "topk_branches": int(args.topk_branches),
            "topk_k": int(args.topk_k),
            "topk_target_split": str(args.topk_target_split),
            "ndtha_target_split": str(args.ndtha_target_split),
            "ndtha_min_case_count": int(args.ndtha_min_case_count),
            "ndtha_max_case_count": int(args.ndtha_max_case_count),
            "ndtha_ag_scale": float(args.ndtha_ag_scale),
        },
        "reports": {
            "topk": str(args.topk_out),
            "ndtha": str(args.ndtha_out),
            "midas_mgt_conversion": str(args.midas_conversion_report),
        },
        "metrics": {
            "mgt_node_count": int((mgt.get("metrics") or {}).get("node_count", 0)),
            "mgt_element_count": int((mgt.get("metrics") or {}).get("element_count", 0)),
            "mgt_dummy_node_removed_count": int((mgt.get("metrics") or {}).get("dummy_node_removed_count", 0)),
            "topk_drift_mean_pct": float((topk.get("summary_metrics") or {}).get("drift_error_pct_mean", 0.0)),
            "topk_base_shear_mean_pct": float((topk.get("summary_metrics") or {}).get("base_shear_error_pct_mean", 0.0)),
            "topk_mac_mean": float((topk.get("summary_metrics") or {}).get("mode_shape_mac_mean", 0.0)),
            "ndtha_case_count": int(ndtha_summary.get("case_count", 0)),
            "ndtha_all_cases_converged": bool(ndtha_checks.get("all_cases_converged", False)),
            "ndtha_peak_plastic_story_count_mean": float(ndtha_summary.get("peak_plastic_story_count_mean", 0.0)),
            "ndtha_max_drift_ratio_pct_max": float(ndtha_summary.get("max_drift_ratio_pct_max", 0.0)),
            "ndtha_avg_step_iterations_mean": float(ndtha_summary.get("avg_step_iterations_mean", 0.0)),
        },
        "checks": {
            "mgt_conversion_pass": mgt_pass,
            "topk_pass": topk_pass,
            "ndtha_pass": ndtha_pass,
            "bundle_pass": bool(reason_code == "PASS"),
        },
        "steps": steps,
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    archive_manifest = _archive(
        [
            str(args.out),
            str(args.topk_out),
            str(args.ndtha_out),
            str(args.midas_conversion_report),
        ]
    )
    if archive_manifest:
        payload["artifact_archive_manifest"] = archive_manifest
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote MIDAS Top-k/NDTHA comparison report: {out}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
