#!/usr/bin/env python3
"""Build and run HIP kernel smoke suite (single-GPU)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "hip kernel smoke passed",
    "ERR_INVALID_INPUT": "invalid hip smoke input",
    "ERR_HIP_COMPILER_MISSING": "hipcc compiler is missing",
    "ERR_HIP_BUILD_FAIL": "hip kernel build failed",
    "ERR_HIP_RUN_FAIL": "hip kernel execution failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source", "binary", "n", "reps", "out"],
    "properties": {
        "source": {"type": "string", "minLength": 1},
        "binary": {"type": "string", "minLength": 1},
        "beam_source": {"type": "string", "minLength": 1},
        "beam_binary": {"type": "string", "minLength": 1},
        "enable_beam_kernel": {"type": "boolean"},
        "hipcc": {"type": "string", "minLength": 1},
        "rocm_path": {"type": "string"},
        "rocm_device_lib_path": {"type": "string"},
        "n": {"type": "integer", "minimum": 1024},
        "reps": {"type": "integer", "minimum": 1},
        "strict": {"type": "boolean"},
        "out": {"type": "string", "minLength": 1},
    },
}


def _discover_rocm_device_lib_path(explicit: str | None) -> str:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
    local = Path(__file__).resolve().parent / "third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
    candidates = [
        local,
        Path("/opt/rocm/amdgcn/bitcode"),
        Path("/opt/rocm/lib/bitcode"),
        Path("/opt/rocm-6.0.2/amdgcn/bitcode"),
        Path("/opt/rocm-5.7.1/amdgcn/bitcode"),
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return ""


def _run(cmd: list[str]) -> tuple[int, float, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc.returncode, time.time() - t0, (proc.stdout or ""), (proc.stderr or "")


def _resolve_hipcc(path_or_name: str) -> str:
    direct = Path(path_or_name)
    if direct.exists() and direct.is_file():
        return str(direct)
    found = shutil.which(path_or_name)
    if found:
        return found
    for cand in ("/opt/rocm/bin/hipcc", "/opt/rocm-6.0.2/bin/hipcc", "/opt/rocm-5.7.1/bin/hipcc"):
        if Path(cand).exists():
            return cand
    return ""


def _build_and_run_kernel(
    *,
    source: str,
    binary: str,
    hipcc_path: str,
    rocm_path: str,
    rocm_device_lib_path: str,
    n: int,
    reps: int,
) -> dict:
    src = Path(source)
    if not src.exists():
        raise ValueError(f"source not found: {src}")
    bin_path = Path(binary)
    bin_path.parent.mkdir(parents=True, exist_ok=True)

    build_cmd = [hipcc_path]
    if rocm_path:
        build_cmd.append(f"--rocm-path={rocm_path}")
    if rocm_device_lib_path:
        build_cmd.append(f"--rocm-device-lib-path={rocm_device_lib_path}")
    build_cmd.extend([str(src), "-O3", "-std=c++17", "-o", str(bin_path)])
    build_rc, build_sec, build_so, build_se = _run(build_cmd)
    if build_rc != 0:
        return {
            "ok": False,
            "build": {
                "command": shlex.join(build_cmd),
                "seconds": float(build_sec),
                "return_code": int(build_rc),
                "stdout_tail": build_so[-1200:],
                "stderr_tail": build_se[-1200:],
            },
            "run": {},
            "backend": {
                "source": str(src),
                "binary": str(bin_path),
            },
        }

    run_cmd = [str(bin_path), str(int(n)), str(int(reps))]
    run_rc, run_sec, run_so, run_se = _run(run_cmd)
    run_json = {}
    try:
        run_json = json.loads((run_so.strip().splitlines()[-1] if run_so.strip() else "{}"))
    except Exception:
        run_json = {}

    return {
        "ok": bool(build_rc == 0 and run_rc == 0 and run_json.get("ok", False)),
        "build": {
            "command": shlex.join(build_cmd),
            "seconds": float(build_sec),
            "return_code": int(build_rc),
            "stdout_tail": build_so[-1200:],
            "stderr_tail": build_se[-1200:],
        },
        "run": {
            "command": shlex.join(run_cmd),
            "seconds": float(run_sec),
            "return_code": int(run_rc),
            "stdout_tail": run_so[-1200:],
            "stderr_tail": run_se[-1200:],
            "metrics": run_json,
        },
        "backend": {
            "source": str(src),
            "binary": str(bin_path),
        },
    }


def main() -> None:
    logger = get_logger("phase1.run_hip_kernel_smoke")
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="implementation/phase1/hip_kernels/axpy_kernel.hip.cpp")
    p.add_argument("--binary", default="implementation/phase1/hip_kernels/axpy_kernel_smoke")
    p.add_argument("--beam-source", default="implementation/phase1/hip_kernels/beam_element_kernel.hip.cpp")
    p.add_argument("--beam-binary", default="implementation/phase1/hip_kernels/beam_element_kernel_smoke")
    p.add_argument("--enable-beam-kernel", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--hipcc", default="hipcc")
    p.add_argument("--rocm-path", default="/opt/rocm")
    p.add_argument("--rocm-device-lib-path", default="")
    p.add_argument("--n", type=int, default=1_048_576)
    p.add_argument("--reps", type=int, default=30)
    p.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--out", default="implementation/phase1/hip_kernel_smoke_report.json")
    args = p.parse_args()

    input_payload = {
        "source": str(args.source),
        "binary": str(args.binary),
        "beam_source": str(args.beam_source),
        "beam_binary": str(args.beam_binary),
        "enable_beam_kernel": bool(args.enable_beam_kernel),
        "hipcc": str(args.hipcc),
        "rocm_path": str(args.rocm_path),
        "rocm_device_lib_path": str(args.rocm_device_lib_path),
        "n": int(args.n),
        "reps": int(args.reps),
        "strict": bool(args.strict),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase0.run_hip_kernel_smoke")
        log_event(logger, logging.INFO, "hip_smoke.start", inputs=input_payload)

        hipcc_path = _resolve_hipcc(str(args.hipcc))
        if not hipcc_path:
            raise RuntimeError("ERR_HIP_COMPILER_MISSING")

        rocm_path = str(args.rocm_path).strip()
        rocm_device_lib_path = _discover_rocm_device_lib_path(str(args.rocm_device_lib_path).strip())
        primary = _build_and_run_kernel(
            source=str(args.source),
            binary=str(args.binary),
            hipcc_path=hipcc_path,
            rocm_path=rocm_path,
            rocm_device_lib_path=rocm_device_lib_path,
            n=int(args.n),
            reps=int(args.reps),
        )
        if not bool(primary.get("ok", False)):
            if int((primary.get("build") or {}).get("return_code", 0)) != 0:
                raise RuntimeError("ERR_HIP_BUILD_FAIL")
            raise RuntimeError("ERR_HIP_RUN_FAIL")

        secondary = {}
        secondary_enabled = bool(args.enable_beam_kernel)
        secondary_ok = True
        if secondary_enabled:
            secondary = _build_and_run_kernel(
                source=str(args.beam_source),
                binary=str(args.beam_binary),
                hipcc_path=hipcc_path,
                rocm_path=rocm_path,
                rocm_device_lib_path=rocm_device_lib_path,
                n=int(args.n),
                reps=int(args.reps),
            )
            secondary_ok = bool(secondary.get("ok", False))
            if not secondary_ok:
                if int((secondary.get("build") or {}).get("return_code", 0)) != 0:
                    raise RuntimeError("ERR_HIP_BUILD_FAIL")
                raise RuntimeError("ERR_HIP_RUN_FAIL")

        payload = {
            "schema_version": "1.0",
            "run_id": "phase0-hip-kernel-smoke",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "backend": {
                "kind": "hipcc_kernel",
                "compiler_path": hipcc_path,
                "rocm_path": rocm_path,
                "rocm_device_lib_path": rocm_device_lib_path,
                "primary": primary.get("backend", {}),
                "secondary": secondary.get("backend", {}) if secondary_enabled else {},
            },
            "build": {"primary": primary.get("build", {}), "secondary": secondary.get("build", {}) if secondary_enabled else {}},
            "run": {"primary": primary.get("run", {}), "secondary": secondary.get("run", {}) if secondary_enabled else {}},
            "checks": {
                "hip_compiler_present": True,
                "build_pass": bool(primary.get("ok", False) and (not secondary_enabled or secondary_ok)),
                "run_pass": bool(primary.get("ok", False) and (not secondary_enabled or secondary_ok)),
                "kernel_backend_pass": True,
                "beam_kernel_enabled": bool(secondary_enabled),
                "beam_kernel_pass": bool((not secondary_enabled) or secondary_ok),
            },
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": REASONS["PASS"],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "hip_smoke.completed", contract_pass=True, reason_code="PASS")
        print(f"Wrote hip kernel smoke report: {out}")
    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase0-hip-kernel-smoke",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "hip_smoke.invalid_input", error=str(exc))
        print(f"Wrote hip kernel smoke report: {out}")
        raise SystemExit(1)
    except RuntimeError as exc:
        code = str(exc)
        if code not in REASONS:
            code = "ERR_HIP_RUN_FAIL"
        payload = {
            "schema_version": "1.0",
            "run_id": "phase0-hip-kernel-smoke",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": code,
            "reason": REASONS.get(code, REASONS["ERR_HIP_RUN_FAIL"]),
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "hip_smoke.runtime_error", reason_code=code)
        print(f"Wrote hip kernel smoke report: {out}")
        if bool(args.strict):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
