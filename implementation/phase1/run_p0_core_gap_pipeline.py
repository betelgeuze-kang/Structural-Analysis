#!/usr/bin/env python3
"""Run P0 core-gap pipeline: Rust engine path + public HF benchmark validation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "p0 core gaps passed (rust engine + public hf benchmark)",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_P0_ENGINE_FAIL": "p0-1 rust engine path failed",
    "ERR_P0_ENGINE_PROFILE_FAIL": "p0-1 rust engine performance profiling failed",
    "ERR_P0_HIP_KERNEL_FAIL": "p0-1 hip kernel smoke failed",
    "ERR_P0_BENCHMARK_BUILD_FAIL": "p0-2 benchmark dataset build failed",
    "ERR_P0_BENCHMARK_KPI_FAIL": "p0-2 benchmark top-k KPI failed",
    "ERR_P0_BENCHMARK_SUITE_FAIL": "p0-2 benchmark multi-seed suite failed",
    "ERR_P0_BENCHMARK_VALIDATION_FAIL": "p0-2 benchmark validation failed",
    "ERR_P0_BENCHMARK_DATA_FAIL": "p0-2 benchmark dataset checks failed",
    "ERR_P0_BENCHMARK_FAIL": "p0-2 public hf benchmark path failed",
}

P0_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["producer_cmd", "epochs", "branches", "top_k", "target_split", "out"],
    "properties": {
        "producer_cmd": {"type": "string", "minLength": 1},
        "require_rust_hip": {"type": "boolean"},
        "allow_cpu_required": {"type": "boolean"},
        "profile_require_rust_faster": {"type": "boolean"},
        "require_hip_kernel": {"type": "boolean"},
        "epochs": {"type": "integer", "minimum": 1},
        "branches": {"type": "integer", "minimum": 2},
        "top_k": {"type": "integer", "minimum": 2},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "min_public_hf_cases": {"type": "integer", "minimum": 1},
        "out": {"type": "string", "minLength": 1},
    },
}

RUN_ENV_OVERRIDES: dict[str, str] = {}


def _run(cmd: list[str]) -> tuple[bool, float, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env={**os.environ, **RUN_ENV_OVERRIDES})
    dt = time.time() - t0
    return proc.returncode == 0, dt, (proc.stdout or "")[-1500:], (proc.stderr or "")[-1500:]


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    logger = get_logger("phase1.run_p0_core_gap_pipeline")
    p = argparse.ArgumentParser()
    p.add_argument("--probe-out", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    p.add_argument("--track-out", default="implementation/phase1/track_lf_solver_report.json")
    p.add_argument("--perf-out", default="implementation/phase1/p0_engine_perf_report.json")
    p.add_argument("--accuracy-out", default="implementation/phase1/real_accuracy_validation_report.json")
    p.add_argument("--producer-cmd", default=f"{sys.executable} implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--require-rust-hip", action="store_true")
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--profile-require-rust-faster", action="store_true")
    p.add_argument("--require-hip-kernel", action="store_true")
    p.add_argument("--hip-smoke-out", default="implementation/phase1/hip_kernel_smoke_report.json")
    p.add_argument("--epochs", type=int, default=120)
    p.add_argument("--branches", type=int, default=10)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--min-public-hf-cases", type=int, default=3)
    p.add_argument("--out", default="implementation/phase1/p0_core_gap_report.json")
    args = p.parse_args()

    input_payload = {
        "producer_cmd": str(args.producer_cmd),
        "require_rust_hip": bool(args.require_rust_hip),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "profile_require_rust_faster": bool(args.profile_require_rust_faster),
        "require_hip_kernel": bool(args.require_hip_kernel),
        "epochs": int(args.epochs),
        "branches": int(args.branches),
        "top_k": int(args.top_k),
        "target_split": str(args.target_split),
        "min_public_hf_cases": int(args.min_public_hf_cases),
        "out": str(args.out),
    }

    logs: list[dict] = []
    try:
        validate_input_contract(input_payload, P0_INPUT_SCHEMA, label="phase0.run_p0_core_gap_pipeline")
        if int(args.top_k) > int(args.branches):
            raise ValueError("top_k cannot exceed branches")
        if bool(args.require_rust_hip) and not bool(args.allow_cpu_required):
            RUN_ENV_OVERRIDES["PHASE1_DISABLE_CPU_FALLBACK"] = "1"
            RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS"] = "1"
            RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS_STRICT"] = "1"
        log_event(logger, logging.INFO, "p0_core_gap.start", inputs=input_payload)

        probe_cmd = [
            sys.executable,
            "implementation/phase1/zero_copy_real_probe.py",
            "--producer-cmd",
            str(args.producer_cmd),
            "--out",
            str(args.probe_out),
        ]
        if bool(args.allow_cpu_required):
            probe_cmd.append("--allow-cpu-required")
        if args.require_rust_hip:
            probe_cmd.append("--require-rust-hip")
        ok_probe, sec_probe, out_probe, err_probe = _run(probe_cmd)
        logs.append(
            {
                "step": "p0_1_zero_copy_probe",
                "command": shlex.join(probe_cmd),
                "seconds": sec_probe,
                "ok": ok_probe,
                "stdout_tail": out_probe,
                "stderr_tail": err_probe,
            }
        )

        track_cmd = [
            sys.executable,
            "implementation/phase1/track_lf_solver.py",
            "--engine",
            "rust",
            "--out",
            str(args.track_out),
        ]
        ok_track, sec_track, out_track, err_track = _run(track_cmd)
        logs.append(
            {
                "step": "p0_1_track_rust_kernel",
                "command": shlex.join(track_cmd),
                "seconds": sec_track,
                "ok": ok_track,
                "stdout_tail": out_track,
                "stderr_tail": err_track,
            }
        )

        perf_cmd = [
            sys.executable,
            "implementation/phase1/profile_p0_engine_path.py",
            "--producer-cmd",
            str(args.producer_cmd),
            "--probe-out",
            str(args.probe_out),
            "--track-rust-out",
            str(args.track_out),
            "--out",
            str(args.perf_out),
            *(["--allow-cpu-required"] if bool(args.allow_cpu_required) else []),
            *(["--require-rust-hip"] if bool(args.require_rust_hip) else []),
            *(["--require-rust-faster"] if bool(args.profile_require_rust_faster) else []),
        ]
        ok_perf, sec_perf, out_perf, err_perf = _run(perf_cmd)
        logs.append(
            {
                "step": "p0_1_engine_perf_profile",
                "command": shlex.join(perf_cmd),
                "seconds": sec_perf,
                "ok": ok_perf,
                "stdout_tail": out_perf,
                "stderr_tail": err_perf,
            }
        )

        hip_cmd = [
            sys.executable,
            "implementation/phase1/run_hip_kernel_smoke.py",
            "--out",
            str(args.hip_smoke_out),
            "--strict" if bool(args.require_hip_kernel) else "--no-strict",
        ]
        ok_hip, sec_hip, out_hip, err_hip = _run(hip_cmd)
        logs.append(
            {
                "step": "p0_1_hip_kernel_smoke",
                "command": shlex.join(hip_cmd),
                "seconds": sec_hip,
                "ok": ok_hip,
                "stdout_tail": out_hip,
                "stderr_tail": err_hip,
            }
        )

        acc_cmd = [
            sys.executable,
            "implementation/phase1/run_real_accuracy_validation.py",
            "--summary-out",
            str(args.accuracy_out),
            "--epochs",
            str(args.epochs),
            "--branches",
            str(args.branches),
            "--top-k",
            str(args.top_k),
            "--target-split",
            str(args.target_split),
            "--min-public-hf-cases",
            str(args.min_public_hf_cases),
        ]
        ok_acc, sec_acc, out_acc, err_acc = _run(acc_cmd)
        logs.append(
            {
                "step": "p0_2_real_accuracy_public_hf",
                "command": shlex.join(acc_cmd),
                "seconds": sec_acc,
                "ok": ok_acc,
                "stdout_tail": out_acc,
                "stderr_tail": err_acc,
            }
        )

        probe = _load(str(args.probe_out))
        track = _load(str(args.track_out))
        perf = _load(str(args.perf_out))
        hip = _load(str(args.hip_smoke_out))
        acc = _load(str(args.accuracy_out))

        profile_pass = bool(ok_perf) and bool(perf.get("contract_pass", False))
        hip_pass = bool(ok_hip and bool(hip.get("contract_pass", False)))
        p0_1_ok = bool(ok_probe and ok_track and profile_pass and ((not bool(args.require_hip_kernel)) or hip_pass)) and bool(probe.get("pass", False)) and bool(
            track.get("checks", {}).get("rust_kernel_used", False)
        )
        p0_2_ok = bool(ok_acc) and bool(acc.get("checks", {}).get("public_hf_case_count_pass", False)) and bool(
            acc.get("checks", {}).get("direct_metric_source_pass", False)
        ) and bool(acc.get("overall_pass", False))

        acc_reason = str(acc.get("reason_code", "")).strip()
        if not p0_1_ok:
            if not profile_pass:
                reason_code = "ERR_P0_ENGINE_PROFILE_FAIL"
            elif bool(args.require_hip_kernel) and not hip_pass:
                reason_code = "ERR_P0_HIP_KERNEL_FAIL"
            else:
                reason_code = "ERR_P0_ENGINE_FAIL"
        elif not p0_2_ok:
            if acc_reason == "ERR_BUILD_CASES_FAIL":
                reason_code = "ERR_P0_BENCHMARK_BUILD_FAIL"
            elif acc_reason == "ERR_BENCHMARK_FAIL":
                reason_code = "ERR_P0_BENCHMARK_KPI_FAIL"
            elif acc_reason == "ERR_SUITE_FAIL":
                reason_code = "ERR_P0_BENCHMARK_SUITE_FAIL"
            elif acc_reason == "ERR_VALIDATION_FAIL":
                if not bool(acc.get("checks", {}).get("public_hf_case_count_pass", False)) or not bool(
                    acc.get("checks", {}).get("direct_metric_source_pass", False)
                ):
                    reason_code = "ERR_P0_BENCHMARK_DATA_FAIL"
                else:
                    reason_code = "ERR_P0_BENCHMARK_VALIDATION_FAIL"
            else:
                reason_code = "ERR_P0_BENCHMARK_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-p0-core-gap-pipeline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "probe_out": str(args.probe_out),
                "track_out": str(args.track_out),
                "perf_out": str(args.perf_out),
                "accuracy_out": str(args.accuracy_out),
                "producer_cmd": str(args.producer_cmd),
                "require_rust_hip": bool(args.require_rust_hip),
                "allow_cpu_required": bool(args.allow_cpu_required),
                "profile_require_rust_faster": bool(args.profile_require_rust_faster),
                "require_hip_kernel": bool(args.require_hip_kernel),
                "epochs": int(args.epochs),
                "branches": int(args.branches),
                "top_k": int(args.top_k),
                "target_split": str(args.target_split),
                "min_public_hf_cases": int(args.min_public_hf_cases),
            },
            "checks": {
                "p0_1_rust_engine_pass": p0_1_ok,
                "p0_1_engine_profile_pass": profile_pass,
                "p0_1_hip_kernel_pass": hip_pass,
                "p0_1_profile_reason_code": str(perf.get("reason_code", "")) or None,
                "p0_1_hip_reason_code": str(hip.get("reason_code", "")) or None,
                "p0_2_public_benchmark_pass": p0_2_ok,
                "p0_2_reason_code": acc_reason or None,
            },
            "artifacts": {
                "probe": str(args.probe_out),
                "track": str(args.track_out),
                "perf": str(args.perf_out),
                "hip_smoke": str(args.hip_smoke_out),
                "accuracy": str(args.accuracy_out),
            },
            "steps": logs,
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "p0_core_gap.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=reason_code,
        )
        print(f"Wrote P0 core gap report: {out}")
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "p0_core_gap.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-p0-core-gap-pipeline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote P0 core gap report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "p0_core_gap.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-p0-core-gap-pipeline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote P0 core gap report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
