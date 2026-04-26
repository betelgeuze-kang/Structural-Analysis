#!/usr/bin/env python3
"""Phase1 Priority-B: zero-copy producer readiness probe.

Validates that an external producer command returns the required DLPack bridge fields.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shlex
import subprocess
import sys
from pathlib import Path

REQUIRED_FIELDS = [
    "roundtrip_success",
    "shared_storage",
    "host_copy_bytes",
    "device",
    "shape",
    "dtype",
    "strides",
    "byte_offset",
    "challenge_echo",
]


def _run_json_cmd(command: str, payload: dict) -> dict:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def run(producer_cmd: str, require_rust_hip: bool, allow_cpu_required: bool, gpu_strict: bool) -> dict:
    challenge = secrets.token_hex(16)
    probe_length = 8192
    probe_alpha = 1.125
    data = _run_json_cmd(
        producer_cmd,
        {
            "action": "dlpack_bridge_probe",
            "challenge": challenge,
            "probe_length": probe_length,
            "probe_alpha": probe_alpha,
            "probe_seed": 23,
        },
    )
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    contract_pass = len(missing) == 0

    runtime_kind = data.get("producer_kind", "unknown")
    rust_hip_ready = runtime_kind == "rust_hip"
    challenge_ok = str(data.get("challenge_echo", "")) == challenge
    runtime_backend = str(data.get("runtime_backend", "unknown"))
    cpu_backend = ("cpu" in runtime_backend.lower()) or ("cpu" in str(data.get("device", "")).lower())
    cpu_required = bool(data.get("cpu_required", False))
    cpu_fallback_used = bool(cpu_backend and not cpu_required)
    cpu_allowed = bool((not cpu_backend) or (cpu_required and allow_cpu_required))
    gpu_strict_pass = bool((not gpu_strict) or (not cpu_backend and not cpu_required and not cpu_fallback_used))

    shape = data.get("shape", [])
    tensor_elems = int(shape[0]) * int(shape[1]) if isinstance(shape, list) and len(shape) >= 2 else 0
    tensor_bytes = int(data.get("tensor_bytes", max(tensor_elems * 4, 1)))
    host_copy_bytes = int(data.get("host_copy_bytes", 1))
    host_copy_share = float(host_copy_bytes) / float(max(tensor_bytes, 1))
    host_copy_share_limit = 0.05
    host_copy_share_pass = bool(host_copy_share <= host_copy_share_limit)

    pass_cond = (
        contract_pass
        and challenge_ok
        and cpu_allowed
        and gpu_strict_pass
        and bool(data.get("roundtrip_success"))
        and bool(data.get("shared_storage"))
        and host_copy_bytes == 0
        and host_copy_share_pass
    )
    if require_rust_hip:
        pass_cond = pass_cond and rust_hip_ready

    next_action = "connect Rust/HIP producer and rerun with --require-rust-hip" if not rust_hip_ready else "ready for strict rust-hip validation"
    strict_rust_hip_pass = bool(pass_cond and rust_hip_ready)
    timing_breakdown_seconds = {
        "compute": float(data.get("compute_seconds", 0.0012)),
        "host_copy": float(data.get("host_copy_seconds", 0.0)),
        "serialization": float(data.get("serialization_seconds", 0.0004)),
    }
    return {
        "producer_cmd": producer_cmd,
        "contract_pass": contract_pass,
        "missing_fields": missing,
        "runtime_kind": runtime_kind,
        "runtime_backend": runtime_backend,
        "rust_hip_ready": rust_hip_ready,
        "challenge_ok": challenge_ok,
        "cpu_backend": cpu_backend,
        "cpu_required": cpu_required,
        "cpu_fallback_used": cpu_fallback_used,
        "cpu_allowed": cpu_allowed,
        "gpu_strict": bool(gpu_strict),
        "gpu_strict_pass": bool(gpu_strict_pass),
        "allow_cpu_required": bool(allow_cpu_required),
        "strict_rust_hip_pass": strict_rust_hip_pass,
        "host_copy_share": host_copy_share,
        "host_copy_share_limit": host_copy_share_limit,
        "host_copy_share_pass": host_copy_share_pass,
        "timing_breakdown_seconds": timing_breakdown_seconds,
        "next_action": next_action,
        "pass": pass_cond,
        "probe": data,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--producer-cmd", default=f"{sys.executable} implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--require-rust-hip", action="store_true")
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--gpu-strict", action="store_true")
    p.add_argument("--out", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    args = p.parse_args()

    report = run(args.producer_cmd, args.require_rust_hip, bool(args.allow_cpu_required), bool(args.gpu_strict))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote zero-copy real probe report: {out}")
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
