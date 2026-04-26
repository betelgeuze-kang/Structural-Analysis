#!/usr/bin/env python3
"""Run commercial CSV direct-compare gate and emit contract report.

Pipeline:
1) build benchmark cases from HF/LF commercial exports
2) run top-k benchmark contract on built cases
3) fail-fast if KPI or metric-source gate fails
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


REASONS = {
    "PASS": "commercial csv direct-compare gate passed",
    "ERR_INVALID_INPUT": "invalid gate input",
    "ERR_BUILD_FAIL": "commercial csv case build failed",
    "ERR_BENCHMARK_FAIL": "benchmark contract failed on commercial csv cases",
    "ERR_METRIC_SOURCE_FAIL": "metric source validation failed",
    "ERR_MEMBER_FORCE_FAIL": "member-force soft-accept gate failed",
}


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-2000:],
        (proc.stderr or "")[-2000:],
    )


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-csv", default="implementation/phase1/commercial_hf_export_sample.csv")
    p.add_argument("--lf-csv", default="implementation/phase1/commercial_lf_export_sample.csv")
    p.add_argument("--cases-out", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--benchmark-out", default="implementation/phase1/hf_benchmark_report.from_csv.json")
    p.add_argument("--comparison-out", default="implementation/phase1/topk_comparison_experiment_report.from_csv.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--epochs", type=int, default=120)
    p.add_argument("--branches", type=int, default=10)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--lr", type=float, default=0.055)
    p.add_argument("--epsilon", type=float, default=0.11)
    p.add_argument("--temperature", type=float, default=0.32)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--max-drift-error-pct", type=float, default=5.0)
    p.add_argument("--max-base-shear-error-pct", type=float, default=5.0)
    p.add_argument("--min-mode-shape-mac", type=float, default=0.95)
    p.add_argument("--max-buckling-factor-error-pct", type=float, default=5.0)
    p.add_argument("--require-top-displacement", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--run-member-force-gate", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-member-force", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--member-force-report", default="implementation/phase1/member_force_soft_accept_report.json")
    p.add_argument("--member-force-hf-column", default="axial_force_kN")
    p.add_argument("--member-force-lf-column", default="axial_force_kN")
    p.add_argument("--member-force-shear-y-hf-column", default="shear_force_y_kN")
    p.add_argument("--member-force-shear-y-lf-column", default="shear_force_y_kN")
    p.add_argument("--member-force-shear-z-hf-column", default="shear_force_z_kN")
    p.add_argument("--member-force-shear-z-lf-column", default="shear_force_z_kN")
    p.add_argument("--member-force-moment-y-hf-column", default="bending_moment_y_kNm")
    p.add_argument("--member-force-moment-y-lf-column", default="bending_moment_y_kNm")
    p.add_argument("--member-force-moment-z-hf-column", default="bending_moment_z_kNm")
    p.add_argument("--member-force-moment-z-lf-column", default="bending_moment_z_kNm")
    p.add_argument("--max-member-force-error-pct", type=float, default=5.0)
    p.add_argument("--max-member-force-soft-accept-error-pct", type=float, default=10.0)
    p.add_argument("--max-member-force-soft-accept-case-ratio", type=float, default=0.25)
    p.add_argument("--out", default="implementation/phase1/commercial_csv_gate_report.json")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    steps: list[dict] = []
    reason_code = "PASS"

    if int(args.top_k) < 2 or int(args.top_k) > int(args.branches):
        reason_code = "ERR_INVALID_INPUT"

    if reason_code == "PASS":
        build_cmd = [
            sys.executable,
            "implementation/phase1/build_cases_from_commercial_exports.py",
            "--hf-csv",
            str(args.hf_csv),
            "--lf-csv",
            str(args.lf_csv),
            "--metric-source",
            "commercial_solver_export",
            "--out",
            str(args.cases_out),
        ]
        if bool(args.require_top_displacement):
            build_cmd.append("--require-top-displacement")
        ok, sec, rc, so, se = _run(build_cmd)
        steps.append(
            {
                "step": "build_cases_from_commercial_exports",
                "seconds": float(sec),
                "return_code": int(rc),
                "command": shlex.join(build_cmd),
                "stdout_tail": so,
                "stderr_tail": se,
            }
        )
        if not ok:
            reason_code = "ERR_BUILD_FAIL"

    if reason_code == "PASS":
        bench_cmd = [
            sys.executable,
            "implementation/phase1/benchmark_kpi_contract.py",
            "--cases",
            str(args.cases_out),
            "--out",
            str(args.benchmark_out),
            "--comparison-out",
            str(args.comparison_out),
            "--target-split",
            str(args.target_split),
            "--epochs",
            str(int(args.epochs)),
            "--branches",
            str(int(args.branches)),
            "--top-k",
            str(int(args.top_k)),
            "--lr",
            str(float(args.lr)),
            "--epsilon",
            str(float(args.epsilon)),
            "--temperature",
            str(float(args.temperature)),
            "--seed",
            str(int(args.seed)),
            "--max-drift-error-pct",
            str(float(args.max_drift_error_pct)),
            "--max-base-shear-error-pct",
            str(float(args.max_base_shear_error_pct)),
            "--min-mode-shape-mac",
            str(float(args.min_mode_shape_mac)),
            "--max-buckling-factor-error-pct",
            str(float(args.max_buckling_factor_error_pct)),
            "--require-direct-metrics",
            "--accepted-metric-sources",
            "commercial_solver_export,engine_export_direct",
        ]
        ok, sec, rc, so, se = _run(bench_cmd)
        steps.append(
            {
                "step": "benchmark_kpi_contract",
                "seconds": float(sec),
                "return_code": int(rc),
                "command": shlex.join(bench_cmd),
                "stdout_tail": so,
                "stderr_tail": se,
            }
        )
        if not ok:
            reason_code = "ERR_BENCHMARK_FAIL"

    member_force_report: dict = {}
    if reason_code == "PASS" and bool(args.run_member_force_gate):
        mf_cmd = [
            sys.executable,
            "implementation/phase1/run_member_force_soft_accept_gate.py",
            "--hf-csv",
            str(args.hf_csv),
            "--lf-csv",
            str(args.lf_csv),
            "--components",
            "axial,shear_y,shear_z,moment_y,moment_z",
            "--axial-hf-col",
            str(args.member_force_hf_column),
            "--axial-lf-col",
            str(args.member_force_lf_column),
            "--shear-y-hf-col",
            str(args.member_force_shear_y_hf_column),
            "--shear-y-lf-col",
            str(args.member_force_shear_y_lf_column),
            "--shear-z-hf-col",
            str(args.member_force_shear_z_hf_column),
            "--shear-z-lf-col",
            str(args.member_force_shear_z_lf_column),
            "--moment-y-hf-col",
            str(args.member_force_moment_y_hf_column),
            "--moment-y-lf-col",
            str(args.member_force_moment_y_lf_column),
            "--moment-z-hf-col",
            str(args.member_force_moment_z_hf_column),
            "--moment-z-lf-col",
            str(args.member_force_moment_z_lf_column),
            "--max-hard-error-pct",
            str(float(args.max_member_force_error_pct)),
            "--max-soft-accept-error-pct",
            str(float(args.max_member_force_soft_accept_error_pct)),
            "--max-soft-accept-case-ratio",
            str(float(args.max_member_force_soft_accept_case_ratio)),
            "--out",
            str(args.member_force_report),
        ]
        if bool(args.require_member_force):
            mf_cmd.append("--require-member-force")
        else:
            mf_cmd.append("--no-require-member-force")
        ok, sec, rc, so, se = _run(mf_cmd)
        steps.append(
            {
                "step": "member_force_soft_accept_gate",
                "seconds": float(sec),
                "return_code": int(rc),
                "command": shlex.join(mf_cmd),
                "stdout_tail": so,
                "stderr_tail": se,
            }
        )
        member_force_report = _load_json(str(args.member_force_report))
        if not ok:
            reason_code = "ERR_MEMBER_FORCE_FAIL"

    benchmark = _load_json(str(args.benchmark_out))
    metric_source_validation = benchmark.get("metric_source_validation")
    metric_source_pass = bool(
        isinstance(metric_source_validation, dict)
        and metric_source_validation.get("pass", False)
    )
    if reason_code == "PASS" and not metric_source_pass:
        reason_code = "ERR_METRIC_SOURCE_FAIL"

    mf_checks = member_force_report.get("checks") if isinstance(member_force_report.get("checks"), dict) else {}
    mf_summary = member_force_report.get("summary") if isinstance(member_force_report.get("summary"), dict) else {}
    member_force_metric_present = bool(mf_checks.get("member_force_metric_present", False)) if bool(args.run_member_force_gate) else True
    member_force_soft_accept_pass = bool(mf_checks.get("soft_accept_gate_pass", False)) if bool(args.run_member_force_gate) else True
    member_force_hard_pass = bool(mf_checks.get("hard_gate_pass", False)) if bool(args.run_member_force_gate) else True
    member_force_5d_pass = bool(mf_checks.get("member_force_components_5d_pass", False)) if bool(args.run_member_force_gate) else True
    if reason_code == "PASS" and bool(args.run_member_force_gate) and (not member_force_soft_accept_pass or not member_force_5d_pass):
        reason_code = "ERR_MEMBER_FORCE_FAIL"

    kpi_metrics = benchmark.get("metrics") if isinstance(benchmark.get("metrics"), dict) else {}
    checks = {
        "build_cases_pass": bool(reason_code != "ERR_BUILD_FAIL"),
        "benchmark_pass": bool(benchmark.get("contract_pass", False)),
        "metric_source_pass": bool(metric_source_pass),
        "drift_within_5pct": float(kpi_metrics.get("drift_error_pct", 999.0)) <= 5.0,
        "base_shear_within_5pct": float(kpi_metrics.get("base_shear_error_pct", 999.0)) <= 5.0,
        "buckling_within_5pct": float(kpi_metrics.get("buckling_factor_error_pct", 999.0)) <= 5.0,
        "mac_above_095": float(kpi_metrics.get("mode_shape_mac", -1.0)) >= 0.95,
        "member_force_metric_present": bool(member_force_metric_present),
        "member_force_soft_accept_pass": bool(member_force_soft_accept_pass),
        "member_force_hard_pass": bool(member_force_hard_pass),
        "member_force_components_5d_pass": bool(member_force_5d_pass),
    }
    contract_pass = bool(reason_code == "PASS" and all(checks.values()))
    if reason_code == "PASS" and not contract_pass:
        reason_code = "ERR_BENCHMARK_FAIL"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-commercial-csv-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "hf_csv": str(args.hf_csv),
            "lf_csv": str(args.lf_csv),
            "cases_out": str(args.cases_out),
            "benchmark_out": str(args.benchmark_out),
            "comparison_out": str(args.comparison_out),
            "target_split": str(args.target_split),
            "epochs": int(args.epochs),
            "branches": int(args.branches),
            "top_k": int(args.top_k),
            "require_top_displacement": bool(args.require_top_displacement),
        },
        "artifacts": {
            "cases": str(args.cases_out),
            "benchmark": str(args.benchmark_out),
            "comparison": str(args.comparison_out),
            "member_force_report": str(args.member_force_report) if bool(args.run_member_force_gate) else "",
        },
        "checks": checks,
        "metrics": {
            "drift_error_pct": float(kpi_metrics.get("drift_error_pct", 999.0)),
            "base_shear_error_pct": float(kpi_metrics.get("base_shear_error_pct", 999.0)),
            "mode_shape_mac": float(kpi_metrics.get("mode_shape_mac", 0.0)),
            "buckling_factor_error_pct": float(kpi_metrics.get("buckling_factor_error_pct", 999.0)),
            "member_force_error_pct_p95": float(mf_summary.get("error_pct_p95", 999.0)) if bool(args.run_member_force_gate) else 0.0,
            "member_force_error_pct_max": float(mf_summary.get("error_pct_max", 999.0)) if bool(args.run_member_force_gate) else 0.0,
            "member_force_soft_accept_case_ratio": float(mf_summary.get("soft_accept_case_ratio", 0.0)) if bool(args.run_member_force_gate) else 0.0,
            "member_force_component_count": int(mf_summary.get("component_count_available", 0)) if bool(args.run_member_force_gate) else 0,
        },
        "steps": steps,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote commercial csv gate report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
