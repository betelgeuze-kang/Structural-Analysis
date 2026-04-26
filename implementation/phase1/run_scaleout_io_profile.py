#!/usr/bin/env python3
"""Stress test: scale-out memory I/O profiling for 1M+ DOF runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import shlex
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "scale-out I/O profile completed and 1M+ DOF microbatch gate passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_RUST_HIP_PATH_REQUIRED": "runtime hook / producer command does not use rust hip path",
    "ERR_GPU_STRICT_FAIL": "gpu strict policy failed (cpu backend/required/fallback detected)",
    "ERR_PROBE_FAIL": "zero-copy probe failed under configured policy",
    "ERR_PROFILE_RUN_FAIL": "cache profile run failed for one or more DOF levels",
    "ERR_1M_GATE_FAIL": "1M+ DOF microbatch/cache gate failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["runtime_hook_cmd", "producer_cmd", "dof_levels", "work_dir", "out"],
    "properties": {
        "runtime_hook_cmd": {"type": "string", "minLength": 1},
        "producer_cmd": {"type": "string", "minLength": 1},
        "dof_levels": {"type": "string", "minLength": 1},
        "branches": {"type": "integer", "minimum": 2},
        "chunk_candidates": {"type": "string", "minLength": 1},
        "state_components": {"type": "integer", "minimum": 1},
        "cache_mb": {"type": "number", "exclusiveMinimum": 0.0},
        "cache_headroom": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "graph_overhead_mb": {"type": "number", "minimum": 0.0},
        "cache_penalty_gain": {"type": "number", "exclusiveMinimum": 0.0},
        "repeats": {"type": "integer", "minimum": 1},
        "allow_cpu_required": {"type": "boolean"},
        "gpu_strict": {"type": "boolean"},
        "require_rust_hip_cmd": {"type": "boolean"},
        "disable_1m_gate": {"type": "boolean"},
        "max_host_copy_share": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_1m_branch_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "probe_report_in": {"type": "string"},
        "work_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _parse_dof_levels(text: str) -> list[int]:
    vals: list[int] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        v = int(tok)
        if v < 1000:
            raise ValueError("dof levels must be >= 1000")
        vals.append(v)
    vals = sorted(set(vals))
    if not vals:
        raise ValueError("at least one dof level is required")
    return vals


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-1500:],
        (proc.stderr or "")[-1500:],
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_finite(x: float) -> bool:
    return math.isfinite(float(x))


def _archive_outputs(test_name: str, paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name=test_name,
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def _cmd_looks_rust_hip(cmd: str) -> bool:
    c = str(cmd).lower()
    return ("rust_hip" in c) or ("run_hip_kernel" in c)


def main() -> None:
    logger = get_logger("phase1.run_scaleout_io_profile")
    p = argparse.ArgumentParser()
    p.add_argument("--runtime-hook-cmd", default="python3 implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--producer-cmd", default=f"{sys.executable} implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--dof-levels", default="100000,300000,1000000,3000000")
    p.add_argument("--branches", type=int, default=64)
    p.add_argument("--chunk-candidates", default="64,32,16,8,4,2,1")
    p.add_argument("--state-components", type=int, default=5)
    p.add_argument("--cache-mb", type=float, default=128.0)
    p.add_argument("--cache-headroom", type=float, default=0.72)
    p.add_argument("--graph-overhead-mb", type=float, default=24.0)
    p.add_argument("--cache-penalty-gain", type=float, default=0.85)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--gpu-strict", action="store_true")
    p.add_argument("--require-rust-hip-cmd", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--disable-1m-gate", action="store_true")
    p.add_argument("--max-host-copy-share", type=float, default=0.05)
    p.add_argument("--max-1m-branch-ms", type=float, default=500.0)
    p.add_argument("--probe-report-in", default="")
    p.add_argument("--work-dir", default="implementation/phase1/stress/scaleout")
    p.add_argument("--out", default="implementation/phase1/scaleout_io_profile_report.json")
    args = p.parse_args()

    input_payload = {
        "runtime_hook_cmd": str(args.runtime_hook_cmd),
        "producer_cmd": str(args.producer_cmd),
        "dof_levels": str(args.dof_levels),
        "branches": int(args.branches),
        "chunk_candidates": str(args.chunk_candidates),
        "state_components": int(args.state_components),
        "cache_mb": float(args.cache_mb),
        "cache_headroom": float(args.cache_headroom),
        "graph_overhead_mb": float(args.graph_overhead_mb),
        "cache_penalty_gain": float(args.cache_penalty_gain),
        "repeats": int(args.repeats),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "gpu_strict": bool(args.gpu_strict),
        "require_rust_hip_cmd": bool(args.require_rust_hip_cmd),
        "disable_1m_gate": bool(args.disable_1m_gate),
        "max_host_copy_share": float(args.max_host_copy_share),
        "max_1m_branch_ms": float(args.max_1m_branch_ms),
        "probe_report_in": str(args.probe_report_in),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
    }

    out_path = Path(args.out)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase-stress.run_scaleout_io_profile")
        dof_levels = _parse_dof_levels(args.dof_levels)
        log_event(logger, logging.INFO, "scaleout_io.start", dof_levels=dof_levels, allow_cpu_required=bool(args.allow_cpu_required))

        rust_cmd_policy_pass = bool(
            _cmd_looks_rust_hip(str(args.runtime_hook_cmd)) and _cmd_looks_rust_hip(str(args.producer_cmd))
        )

        probe_path = work_dir / "zero_copy_probe.scaleout.json"
        probe_in = Path(str(args.probe_report_in)) if str(args.probe_report_in).strip() else None
        if probe_in is not None and probe_in.exists():
            probe = _load_json(probe_in)
            ok_probe, sec_probe, rc_probe = True, 0.0, 0
            steps.append(
                {
                    "step": "zero_copy_probe",
                    "ok": True,
                    "seconds": 0.0,
                    "return_code": 0,
                    "command": f"reuse:{probe_in}",
                    "stdout_tail": "",
                    "stderr_tail": "",
                }
            )
            probe_path.write_text(json.dumps(probe, indent=2), encoding="utf-8")
        else:
            if probe_path.exists():
                probe_path.unlink()
            probe_cmd = [
                sys.executable,
                "implementation/phase1/zero_copy_real_probe.py",
                "--producer-cmd",
                str(args.producer_cmd),
                "--out",
                str(probe_path),
                *(["--gpu-strict"] if bool(args.gpu_strict) else []),
                *(["--allow-cpu-required"] if bool(args.allow_cpu_required) else []),
            ]
            ok_probe, sec_probe, rc_probe, stdout_probe, stderr_probe = _run(probe_cmd)
            steps.append(
                {
                    "step": "zero_copy_probe",
                    "ok": bool(ok_probe),
                    "seconds": float(sec_probe),
                    "return_code": int(rc_probe),
                    "command": shlex.join(probe_cmd),
                    "stdout_tail": stdout_probe,
                    "stderr_tail": stderr_probe,
                }
            )
            probe = _load_json(probe_path) if probe_path.exists() else {}
        probe_pass = bool(
            ok_probe
            and bool(probe.get("pass", False))
            and not bool(probe.get("cpu_fallback_used", False))
            and bool(probe.get("gpu_strict_pass", not bool(args.gpu_strict)))
            and float(probe.get("host_copy_share", 1.0)) <= float(args.max_host_copy_share)
        )

        level_rows: list[dict] = []
        profile_failures: list[dict] = []
        for n in dof_levels:
            level_out = work_dir / f"branch64_profile_n{int(n)}.json"
            cmd = [
                sys.executable,
                "implementation/phase1/profile_branch64_microbatch_cache.py",
                "--runtime-hook-cmd",
                str(args.runtime_hook_cmd),
                "--branches",
                str(int(args.branches)),
                "--chunk-candidates",
                str(args.chunk_candidates),
                "--node-count",
                str(int(n)),
                "--state-components",
                str(int(args.state_components)),
                "--cache-mb",
                str(float(args.cache_mb)),
                "--cache-headroom",
                str(float(args.cache_headroom)),
                "--graph-overhead-mb",
                str(float(args.graph_overhead_mb)),
                "--cache-penalty-gain",
                str(float(args.cache_penalty_gain)),
                "--repeats",
                str(int(args.repeats)),
                "--out",
                str(level_out),
            ]
            ok, sec, rc, stdout_tail, stderr_tail = _run(cmd)
            steps.append(
                {
                    "step": "branch64_profile",
                    "node_count": int(n),
                    "ok": bool(ok),
                    "seconds": float(sec),
                    "return_code": int(rc),
                    "command": shlex.join(cmd),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )
            if not level_out.exists():
                profile_failures.append({"node_count": int(n), "return_code": int(rc), "error": "profile report missing"})
                continue

            profile = _load_json(level_out)
            recommended = profile.get("recommended") if isinstance(profile.get("recommended"), dict) else {}
            full_batch = profile.get("full_batch_64") if isinstance(profile.get("full_batch_64"), dict) else {}
            checks = profile.get("checks") if isinstance(profile.get("checks"), dict) else {}
            level_rows.append(
                {
                    "node_count": int(n),
                    "report_path": str(level_out),
                    "contract_pass": bool(profile.get("contract_pass", False)),
                    "reason_code": str(profile.get("reason_code", "")),
                    "microbatch_available": bool(checks.get("microbatch_available", False)),
                    "full_batch_cache_fit": bool(checks.get("full_batch_cache_fit", False)),
                    "recommended_chunk_branches": int(recommended.get("chunk_branches", 0)) if recommended else 0,
                    "recommended_avg_branch_ms": float(recommended.get("avg_branch_ms", 0.0)) if recommended else math.inf,
                    "recommended_working_set_mb": float(recommended.get("estimated_working_set_mb", 0.0)) if recommended else math.inf,
                    "full_batch_avg_branch_ms": float(full_batch.get("avg_branch_ms", 0.0)) if full_batch else math.inf,
                }
            )

        level_rows = sorted(level_rows, key=lambda r: int(r["node_count"]))
        profile_scenarios_present = len(level_rows) == len(dof_levels)
        profiles_all_pass = bool(level_rows) and all(bool(r.get("contract_pass", False)) for r in level_rows)

        level_1m = next((r for r in level_rows if int(r["node_count"]) >= 1_000_000), None)
        has_1m_plus = isinstance(level_1m, dict)
        scaleout_1m_microbatch_pass = bool(
            isinstance(level_1m, dict)
            and bool(level_1m.get("microbatch_available", False))
            and int(level_1m.get("recommended_chunk_branches", 0)) > 0
            and int(level_1m.get("recommended_chunk_branches", 0)) <= 16
        )
        scaleout_1m_branch_latency_pass = bool(
            isinstance(level_1m, dict) and float(level_1m.get("recommended_avg_branch_ms", math.inf)) <= float(args.max_1m_branch_ms)
        )
        scaleout_1m_fullbatch_miss_expected = bool(
            isinstance(level_1m, dict) and not bool(level_1m.get("full_batch_cache_fit", True))
        )

        monotonic_working_set = True
        prev_ws = -math.inf
        for row in level_rows:
            ws = float(row.get("recommended_working_set_mb", 0.0))
            if not _is_finite(ws) or ws + 1e-9 < prev_ws:
                monotonic_working_set = False
                break
            prev_ws = ws

        saturation_detected_above_1m = any(
            int(r.get("node_count", 0)) > 1_000_000 and not bool(r.get("contract_pass", False))
            for r in level_rows
        )

        if bool(args.require_rust_hip_cmd) and not rust_cmd_policy_pass:
            reason_code = "ERR_RUST_HIP_PATH_REQUIRED"
        elif bool(args.gpu_strict) and not bool(probe.get("gpu_strict_pass", False)):
            reason_code = "ERR_GPU_STRICT_FAIL"
        elif not probe_pass:
            reason_code = "ERR_PROBE_FAIL"
        elif profile_failures or not profile_scenarios_present:
            reason_code = "ERR_PROFILE_RUN_FAIL"
        elif (not bool(args.disable_1m_gate)) and not (
            has_1m_plus and scaleout_1m_microbatch_pass and scaleout_1m_branch_latency_pass and scaleout_1m_fullbatch_miss_expected
        ):
            reason_code = "ERR_1M_GATE_FAIL"
        elif bool(args.disable_1m_gate) and not (profiles_all_pass and monotonic_working_set):
            reason_code = "ERR_PROFILE_RUN_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-scaleout-io-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "runtime_hook_cmd": str(args.runtime_hook_cmd),
                "producer_cmd": str(args.producer_cmd),
                "dof_levels": dof_levels,
                "branches": int(args.branches),
                "chunk_candidates": str(args.chunk_candidates),
                "state_components": int(args.state_components),
                "cache_mb": float(args.cache_mb),
                "cache_headroom": float(args.cache_headroom),
                "graph_overhead_mb": float(args.graph_overhead_mb),
                "cache_penalty_gain": float(args.cache_penalty_gain),
                "repeats": int(args.repeats),
                "allow_cpu_required": bool(args.allow_cpu_required),
                "gpu_strict": bool(args.gpu_strict),
                "require_rust_hip_cmd": bool(args.require_rust_hip_cmd),
                "disable_1m_gate": bool(args.disable_1m_gate),
                "max_host_copy_share": float(args.max_host_copy_share),
                "max_1m_branch_ms": float(args.max_1m_branch_ms),
            },
            "probe": {
                "report_path": str(probe_path),
                "probe_pass": bool(probe_pass),
                "strict_pass": bool(probe.get("pass", False)),
                "gpu_strict_pass": bool(probe.get("gpu_strict_pass", not bool(args.gpu_strict))),
                "cpu_fallback_used": bool(probe.get("cpu_fallback_used", False)),
                "host_copy_share": float(probe.get("host_copy_share", math.inf)),
                "host_copy_share_limit": float(args.max_host_copy_share),
            },
            "checks": {
                "probe_pass": bool(probe_pass),
                "gpu_strict_pass": bool(probe.get("gpu_strict_pass", not bool(args.gpu_strict))),
                "rust_hip_cmd_policy_pass": bool(rust_cmd_policy_pass),
                "profile_scenarios_present": bool(profile_scenarios_present),
                "profiles_all_pass": bool(profiles_all_pass),
                "has_1m_plus": bool(has_1m_plus),
                "scaleout_1m_microbatch_pass": bool(scaleout_1m_microbatch_pass),
                "scaleout_1m_branch_latency_pass": bool(scaleout_1m_branch_latency_pass),
                "scaleout_1m_fullbatch_miss_expected": bool(scaleout_1m_fullbatch_miss_expected),
                "saturation_detected_above_1m": bool(saturation_detected_above_1m),
                "monotonic_working_set": bool(monotonic_working_set),
                "disable_1m_gate": bool(args.disable_1m_gate),
            },
            "level_rows": level_rows,
            "profile_failures": profile_failures,
            "steps": steps,
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="scaleout_io_profile",
            paths=[str(args.out), str(args.work_dir)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "scaleout_io.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=reason_code,
            levels=len(level_rows),
        )
        print(f"Wrote scale-out IO profile report: {out_path}")
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "scaleout_io.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-scaleout-io-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="scaleout_io_profile",
            paths=[str(args.out), str(args.work_dir)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote scale-out IO profile report: {out_path}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "scaleout_io.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-scaleout-io-profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_PROFILE_RUN_FAIL",
            "reason": f"{REASONS['ERR_PROFILE_RUN_FAIL']}: {exc}",
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="scaleout_io_profile",
            paths=[str(args.out), str(args.work_dir)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote scale-out IO profile report: {out_path}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
