#!/usr/bin/env python3
"""Profile P0 engine path latencies (zero-copy probe + Rust/Python track LF)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import time

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "p0 engine path profiling completed",
    "ERR_INVALID_INPUT": "invalid profiler input",
    "ERR_PROBE_FAIL": "zero-copy probe failed",
    "ERR_TRACK_RUST_FAIL": "rust track benchmark failed",
    "ERR_TRACK_PY_FAIL": "python track benchmark failed",
    "ERR_PROFILE_FIELDS": "required performance fields are missing",
    "ERR_SPEEDUP_FAIL": "rust speedup requirement not satisfied",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["producer_cmd", "node_count", "out"],
    "properties": {
        "producer_cmd": {"type": "string", "minLength": 1},
        "node_count": {"type": "integer", "minimum": 7},
        "length_m": {"type": "number", "exclusiveMinimum": 0.0},
        "bending_stiffness": {"type": "number", "exclusiveMinimum": 0.0},
        "shear_stiffness": {"type": "number", "exclusiveMinimum": 0.0},
        "point_force_n": {"type": "number", "exclusiveMinimum": 0.0},
        "max_relative_error": {"type": "number", "exclusiveMinimum": 0.0},
        "allow_cpu_required": {"type": "boolean"},
        "require_rust_hip": {"type": "boolean"},
        "require_rust_faster": {"type": "boolean"},
        "out": {"type": "string", "minLength": 1},
    },
}


def _run(cmd: list[str]) -> tuple[bool, float, str, str, int]:
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        (proc.stdout or "")[-1600:],
        (proc.stderr or "")[-1600:],
        int(proc.returncode),
    )


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _theory_elapsed(report: dict, theory: str) -> float:
    return float(((report.get("benchmarks") or {}).get(theory) or {}).get("elapsed_seconds", 0.0))


def main() -> None:
    logger = get_logger("phase1.profile_p0_engine_path")

    p = argparse.ArgumentParser()
    p.add_argument("--producer-cmd", default=f"{sys.executable} implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--require-rust-hip", action="store_true")
    p.add_argument("--require-rust-faster", action="store_true")
    p.add_argument("--node-count", type=int, default=201)
    p.add_argument("--length-m", type=float, default=25.0)
    p.add_argument("--bending-stiffness", type=float, default=6.5e6)
    p.add_argument("--shear-stiffness", type=float, default=2.45e8)
    p.add_argument("--point-force-n", type=float, default=100_000.0)
    p.add_argument("--max-relative-error", type=float, default=0.05)
    p.add_argument("--probe-out", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    p.add_argument("--track-rust-out", default="implementation/phase1/track_lf_solver_report.rust_profile.json")
    p.add_argument("--track-python-out", default="implementation/phase1/track_lf_solver_report.python_profile.json")
    p.add_argument("--out", default="implementation/phase1/p0_engine_perf_report.json")
    args = p.parse_args()

    input_payload = {
        "producer_cmd": str(args.producer_cmd),
        "node_count": int(args.node_count),
        "length_m": float(args.length_m),
        "bending_stiffness": float(args.bending_stiffness),
        "shear_stiffness": float(args.shear_stiffness),
        "point_force_n": float(args.point_force_n),
        "max_relative_error": float(args.max_relative_error),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "require_rust_hip": bool(args.require_rust_hip),
        "require_rust_faster": bool(args.require_rust_faster),
        "out": str(args.out),
    }

    steps: list[dict] = []
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase0.profile_p0_engine_path")
        log_event(logger, logging.INFO, "p0_profile.start", inputs=input_payload)

        probe_cmd = [
            sys.executable,
            "implementation/phase1/zero_copy_real_probe.py",
            "--producer-cmd",
            str(args.producer_cmd),
            "--out",
            str(args.probe_out),
            *(["--allow-cpu-required"] if bool(args.allow_cpu_required) else []),
            *(["--require-rust-hip"] if bool(args.require_rust_hip) else []),
        ]
        ok_probe, sec_probe, out_probe, err_probe, rc_probe = _run(probe_cmd)
        steps.append(
            {
                "step": "zero_copy_probe",
                "command": shlex.join(probe_cmd),
                "ok": ok_probe,
                "return_code": rc_probe,
                "seconds": sec_probe,
                "stdout_tail": out_probe,
                "stderr_tail": err_probe,
            }
        )

        common_track = [
            "--node-count",
            str(args.node_count),
            "--length-m",
            str(args.length_m),
            "--bending-stiffness",
            str(args.bending_stiffness),
            "--shear-stiffness",
            str(args.shear_stiffness),
            "--point-force-n",
            str(args.point_force_n),
            "--max-relative-error",
            str(args.max_relative_error),
        ]

        rust_cmd = [
            sys.executable,
            "implementation/phase1/track_lf_solver.py",
            "--engine",
            "rust",
            *common_track,
            "--out",
            str(args.track_rust_out),
        ]
        ok_rust, sec_rust, out_rust, err_rust, rc_rust = _run(rust_cmd)
        steps.append(
            {
                "step": "track_lf_rust",
                "command": shlex.join(rust_cmd),
                "ok": ok_rust,
                "return_code": rc_rust,
                "seconds": sec_rust,
                "stdout_tail": out_rust,
                "stderr_tail": err_rust,
            }
        )

        py_cmd = [
            sys.executable,
            "implementation/phase1/track_lf_solver.py",
            "--engine",
            "python",
            *common_track,
            "--out",
            str(args.track_python_out),
        ]
        ok_py, sec_py, out_py, err_py, rc_py = _run(py_cmd)
        steps.append(
            {
                "step": "track_lf_python",
                "command": shlex.join(py_cmd),
                "ok": ok_py,
                "return_code": rc_py,
                "seconds": sec_py,
                "stdout_tail": out_py,
                "stderr_tail": err_py,
            }
        )

        probe = _load(str(args.probe_out))
        track_rust = _load(str(args.track_rust_out))
        track_py = _load(str(args.track_python_out))

        rust_euler = _theory_elapsed(track_rust, "euler")
        rust_timo = _theory_elapsed(track_rust, "timoshenko")
        py_euler = _theory_elapsed(track_py, "euler")
        py_timo = _theory_elapsed(track_py, "timoshenko")

        speedup_euler = py_euler / max(rust_euler, 1e-12)
        speedup_timo = py_timo / max(rust_timo, 1e-12)

        has_perf_fields = all(v > 0.0 for v in [rust_euler, rust_timo, py_euler, py_timo])
        probe_pass = bool(probe.get("pass", False))
        rust_pass = bool(track_rust.get("contract_pass", False)) and bool(
            (track_rust.get("checks") or {}).get("rust_kernel_used", False)
        )
        py_pass = bool(track_py.get("contract_pass", False))
        speedup_pass = bool(speedup_euler >= 1.0 and speedup_timo >= 1.0)

        if not probe_pass:
            reason_code = "ERR_PROBE_FAIL"
        elif not rust_pass:
            reason_code = "ERR_TRACK_RUST_FAIL"
        elif not py_pass:
            reason_code = "ERR_TRACK_PY_FAIL"
        elif not has_perf_fields:
            reason_code = "ERR_PROFILE_FIELDS"
        elif bool(args.require_rust_faster) and not speedup_pass:
            reason_code = "ERR_SPEEDUP_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-profile-p0-engine-path",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": {
                "probe_pass": probe_pass,
                "track_rust_pass": rust_pass,
                "track_python_pass": py_pass,
                "has_performance_fields": has_perf_fields,
                "speedup_pass": speedup_pass,
            },
            "performance": {
                "zero_copy_timing_breakdown_seconds": probe.get("timing_breakdown_seconds", {}),
                "rust_elapsed_seconds": {"euler": rust_euler, "timoshenko": rust_timo},
                "python_elapsed_seconds": {"euler": py_euler, "timoshenko": py_timo},
                "speedup_python_over_rust": {"euler": speedup_euler, "timoshenko": speedup_timo},
            },
            "artifacts": {
                "probe": str(args.probe_out),
                "track_rust": str(args.track_rust_out),
                "track_python": str(args.track_python_out),
            },
            "steps": steps,
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
            "p0_profile.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=reason_code,
        )
        print(f"Wrote P0 engine perf report: {out}")
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "p0_profile.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-profile-p0-engine-path",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote P0 engine perf report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "p0_profile.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-profile-p0-engine-path",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote P0 engine perf report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

