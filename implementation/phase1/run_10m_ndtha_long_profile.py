#!/usr/bin/env python3
"""Automate long-duration 10M DOF NDTHA profiling with repeated continuous runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shlex
import statistics
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "10m ndtha long profile passed",
    "ERR_INVALID_INPUT": "invalid long profile input",
    "ERR_RUST_BACKEND_FAIL": "one or more long ndtha runs did not use rust backend",
    "ERR_RUN_FAIL": "one or more long ndtha runs failed",
    "ERR_VARIANCE_FAIL": "cross-run variance is too high",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "runs",
        "partitioned_scaleout",
        "topology_report",
        "ground_motion_csv",
        "target_dof",
        "partitions",
        "halo_coupling_gain",
        "out",
    ],
    "properties": {
        "runs": {"type": "integer", "minimum": 1},
        "partitioned_scaleout": {"type": "string", "minLength": 1},
        "topology_report": {"type": "string", "minLength": 1},
        "ground_motion_csv": {"type": "string", "minLength": 1},
        "target_dof": {"type": "integer", "minimum": 1000000},
        "partitions": {"type": "integer", "minimum": 2},
        "halo_coupling_gain": {"type": "number", "exclusiveMinimum": 0.0},
        "require_rust_backend": {"type": "boolean"},
        "max_cov_elapsed": {"type": "number", "minimum": 0.0},
        "max_cov_peak_vram": {"type": "number", "minimum": 0.0},
        "work_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _run(cmd: list[str]) -> tuple[int, float, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc.returncode, time.time() - t0, (proc.stdout or ""), (proc.stderr or "")


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cov(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = statistics.fmean(values)
    if abs(mean) <= 1e-12:
        return 0.0
    return abs(statistics.pstdev(values) / mean)


def main() -> None:
    logger = get_logger("phase3.run_10m_ndtha_long_profile")
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--partitioned-scaleout", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--topology-report", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--target-dof", type=int, default=10_000_000)
    p.add_argument("--partitions", type=int, default=16)
    p.add_argument("--halo-coupling-gain", type=float, default=1.0)
    p.add_argument("--require-rust-backend", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--max-cov-elapsed", type=float, default=0.25)
    p.add_argument("--max-cov-peak-vram", type=float, default=0.25)
    p.add_argument("--work-dir", default="implementation/phase1/stress/ndtha_long_profile")
    p.add_argument("--out", default="implementation/phase1/ndtha_long_profile_report.json")
    args = p.parse_args()

    input_payload = {
        "runs": int(args.runs),
        "partitioned_scaleout": str(args.partitioned_scaleout),
        "topology_report": str(args.topology_report),
        "ground_motion_csv": str(args.ground_motion_csv),
        "target_dof": int(args.target_dof),
        "partitions": int(args.partitions),
        "halo_coupling_gain": float(args.halo_coupling_gain),
        "require_rust_backend": bool(args.require_rust_backend),
        "max_cov_elapsed": float(args.max_cov_elapsed),
        "max_cov_peak_vram": float(args.max_cov_peak_vram),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_10m_ndtha_long_profile")
        log_event(logger, logging.INFO, "ndtha_long_profile.start", inputs=input_payload)

        rows: list[dict] = []
        elapsed_values: list[float] = []
        peak_vram_values: list[float] = []
        step_wall_values: list[float] = []
        halo_exchange_values: list[float] = []
        retry_overhead_values: list[float] = []
        solver_values: list[float] = []
        state_update_values: list[float] = []
        interface_values: list[float] = []
        solver_reuse_ratio_values: list[float] = []
        stiffness_refresh_count_values: list[int] = []
        retry_attempt_count_values: list[int] = []
        retry_attempts_per_completed_step_values: list[float] = []
        rust_backend_pass_values: list[bool] = []
        all_ok = True
        artifacts: list[str] = []

        for idx in range(int(args.runs)):
            run_out = work_dir / f"mega_ndtha_run_{idx+1}.json"
            cmd = [
                sys.executable,
                "implementation/phase1/run_mega_ndtha_partitioned_stress.py",
                "--partitioned-scaleout",
                str(args.partitioned_scaleout),
                "--topology-report",
                str(args.topology_report),
                "--ground-motion-csv",
                str(args.ground_motion_csv),
                "--target-dof",
                str(int(args.target_dof)),
                "--partitions",
                str(int(args.partitions)),
                "--halo-coupling-gain",
                str(float(args.halo_coupling_gain)),
                "--min-halo-coupling-gain",
                str(float(args.halo_coupling_gain)),
                "--pdelta-factor",
                "1.0",
                "--rayleigh-alpha",
                "0.03",
                "--rayleigh-beta",
                "1e-6",
                "--feti-step-max-iter",
                "80",
                "--feti-step-gap-tol",
                "0.05",
                "--feti-step-top-tol-m",
                "0.05",
                "--feti-step-relax",
                "0.15",
                "--feti-step-relax-min",
                "0.05",
                "--feti-step-update-cap-m",
                "0.05",
                "--feti-step-gap-reduction-target",
                "0.01",
                "--feti-step-top-reduction-target",
                "0.01",
                "--allow-feti-soft-accept",
                "--feti-soft-gap-factor",
                "10.0",
                "--feti-soft-top-factor",
                "10.0",
                "--step-guard-max-retries",
                "12",
                "--step-guard-retry-load-decay",
                "0.25",
                "--step-guard-max-top-jump-m",
                "200.0",
                "--step-guard-max-drift-increment-pct",
                "100.0",
                "--step-guard-max-energy-jump-ratio",
                "1000000.0",
                "--state-update-max-backtracks",
                "14",
                "--state-update-shrink",
                "0.3",
                "--state-update-min-alpha",
                "0.002",
                "--require-full-duration",
                "--max-steps",
                "0",
                "--out",
                str(run_out),
            ]
            rc, sec, so, se = _run(cmd)
            rpt = _load(run_out)
            checks = rpt.get("checks") if isinstance(rpt.get("checks"), dict) else {}
            summary = rpt.get("summary") if isinstance(rpt.get("summary"), dict) else {}
            runtime = rpt.get("runtime_profile") if isinstance(rpt.get("runtime_profile"), dict) else {}
            rust_backend_pass = bool(checks.get("rust_backend_used_pass", False))
            rust_backend_pass_values.append(bool(rust_backend_pass))
            run_ok = bool(
                rc == 0
                and bool(rpt.get("contract_pass", False))
                and bool(checks.get("all_steps_converged", False))
                and bool(checks.get("full_duration_pass", False))
                and bool(checks.get("plasticity_triggered_all_partitions", False))
            )
            all_ok = bool(all_ok and run_ok)
            elapsed_s = float(summary.get("elapsed_wall_s", sec))
            peak_vram_mb = float(runtime.get("peak_vram_mb", 0.0))
            step_wall_s = float(summary.get("step_wall_seconds_total", elapsed_s))
            halo_exchange_s = float(summary.get("halo_exchange_seconds_total", 0.0))
            retry_overhead_s = float(summary.get("retry_overhead_seconds_total", 0.0))
            solver_s = float(summary.get("solver_seconds_total", 0.0))
            state_update_s = float(summary.get("state_update_seconds_total", 0.0))
            interface_s = float(summary.get("interface_seconds_total", 0.0))
            solver_reuse_ratio = float(summary.get("solver_reuse_ratio", 0.0))
            stiffness_refresh_count = int(summary.get("stiffness_refresh_count_total", 0) or 0)
            retry_attempt_count = int(summary.get("retry_attempt_count_total", 0) or 0)
            retry_attempts_per_completed_step = float(summary.get("retry_attempts_per_completed_step", 0.0))
            elapsed_values.append(elapsed_s)
            peak_vram_values.append(peak_vram_mb)
            step_wall_values.append(step_wall_s)
            halo_exchange_values.append(halo_exchange_s)
            retry_overhead_values.append(retry_overhead_s)
            solver_values.append(solver_s)
            state_update_values.append(state_update_s)
            interface_values.append(interface_s)
            solver_reuse_ratio_values.append(solver_reuse_ratio)
            stiffness_refresh_count_values.append(stiffness_refresh_count)
            retry_attempt_count_values.append(retry_attempt_count)
            retry_attempts_per_completed_step_values.append(retry_attempts_per_completed_step)
            artifacts.append(str(run_out))
            rows.append(
                {
                    "run_index": idx + 1,
                    "ok": bool(run_ok),
                    "return_code": int(rc),
                    "command": shlex.join(cmd),
                    "report_path": str(run_out),
                    "elapsed_wall_s": elapsed_s,
                    "step_wall_seconds_total": step_wall_s,
                    "halo_exchange_seconds_total": halo_exchange_s,
                    "retry_overhead_seconds_total": retry_overhead_s,
                    "solver_seconds_total": solver_s,
                    "state_update_seconds_total": state_update_s,
                    "interface_seconds_total": interface_s,
                    "solver_reuse_ratio": solver_reuse_ratio,
                    "stiffness_refresh_count_total": stiffness_refresh_count,
                    "retry_attempt_count_total": retry_attempt_count,
                    "retry_attempts_per_completed_step": retry_attempts_per_completed_step,
                    "peak_vram_mb": peak_vram_mb,
                    "rust_backend_used_pass": bool(rust_backend_pass),
                    "stdout_tail": so[-1200:],
                    "stderr_tail": se[-1200:],
                }
            )

        cov_elapsed = _cov(elapsed_values)
        cov_vram = _cov(peak_vram_values)
        rust_backend_all_runs_pass = bool(all(rust_backend_pass_values)) if rust_backend_pass_values else False
        checks = {
            "all_runs_pass": bool(all_ok),
            "rust_backend_all_runs_pass": bool(rust_backend_all_runs_pass),
            "elapsed_cov_pass": bool(cov_elapsed <= float(args.max_cov_elapsed)),
            "peak_vram_cov_pass": bool(cov_vram <= float(args.max_cov_peak_vram)),
        }
        contract_pass = bool(all(checks.values()))
        if bool(args.require_rust_backend) and not checks["rust_backend_all_runs_pass"]:
            reason_code = "ERR_RUST_BACKEND_FAIL"
        elif not checks["all_runs_pass"]:
            reason_code = "ERR_RUN_FAIL"
        elif not checks["elapsed_cov_pass"] or not checks["peak_vram_cov_pass"]:
            reason_code = "ERR_VARIANCE_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-10m-ndtha-long-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "elapsed_wall_s_mean": statistics.fmean(elapsed_values) if elapsed_values else 0.0,
                "elapsed_wall_s_cov": float(cov_elapsed),
                "peak_vram_mb_mean": statistics.fmean(peak_vram_values) if peak_vram_values else 0.0,
                "peak_vram_mb_cov": float(cov_vram),
                "step_wall_seconds_mean": statistics.fmean(step_wall_values) if step_wall_values else 0.0,
                "halo_exchange_seconds_mean": statistics.fmean(halo_exchange_values) if halo_exchange_values else 0.0,
                "retry_overhead_seconds_mean": statistics.fmean(retry_overhead_values) if retry_overhead_values else 0.0,
                "solver_seconds_mean": statistics.fmean(solver_values) if solver_values else 0.0,
                "state_update_seconds_mean": statistics.fmean(state_update_values) if state_update_values else 0.0,
                "interface_seconds_mean": statistics.fmean(interface_values) if interface_values else 0.0,
                "solver_reuse_ratio_mean": statistics.fmean(solver_reuse_ratio_values) if solver_reuse_ratio_values else 0.0,
                "stiffness_refresh_count_mean": statistics.fmean(stiffness_refresh_count_values) if stiffness_refresh_count_values else 0.0,
                "retry_attempt_count_mean": statistics.fmean(retry_attempt_count_values) if retry_attempt_count_values else 0.0,
                "retry_attempts_per_completed_step_mean": (
                    statistics.fmean(retry_attempts_per_completed_step_values)
                    if retry_attempts_per_completed_step_values
                    else 0.0
                ),
                "halo_share_of_step_mean": (
                    statistics.fmean(
                        float(halo) / max(float(step), 1e-12)
                        for halo, step in zip(halo_exchange_values, step_wall_values)
                    )
                    if halo_exchange_values and step_wall_values
                    else 0.0
                ),
                "retry_share_of_step_mean": (
                    statistics.fmean(
                        float(retry) / max(float(step), 1e-12)
                        for retry, step in zip(retry_overhead_values, step_wall_values)
                    )
                    if retry_overhead_values and step_wall_values
                    else 0.0
                ),
            },
            "rows": rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            manifest = archive_test_outputs(
                test_name="ndtha_long_profile",
                paths=[str(out), *artifacts],
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
            payload["artifact_archive_manifest"] = str(manifest)
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass
        log_event(logger, logging.INFO, "ndtha_long_profile.completed", contract_pass=contract_pass, reason_code=reason_code)
        print(f"Wrote ndtha long profile report: {out}")
        if not contract_pass:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-10m-ndtha-long-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "ndtha_long_profile.invalid_input", error=str(exc))
        print(f"Wrote ndtha long profile report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
