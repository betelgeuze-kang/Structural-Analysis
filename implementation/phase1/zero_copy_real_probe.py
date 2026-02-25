#!/usr/bin/env python3
"""Phase1 Priority-B: zero-copy producer readiness probe.

Validates that an external producer command returns the required DLPack bridge fields.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
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


def run(producer_cmd: str, require_rust_hip: bool) -> dict:
    data = _run_json_cmd(producer_cmd, {"action": "dlpack_bridge_probe"})
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    contract_pass = len(missing) == 0

    runtime_kind = data.get("producer_kind", "unknown")
    rust_hip_ready = runtime_kind == "rust_hip"

    pass_cond = contract_pass and bool(data.get("roundtrip_success")) and bool(data.get("shared_storage")) and int(data.get("host_copy_bytes", 1)) == 0
    if require_rust_hip:
        pass_cond = pass_cond and rust_hip_ready

    next_action = "connect Rust/HIP producer and rerun with --require-rust-hip" if not rust_hip_ready else "ready for strict rust-hip validation"
    strict_rust_hip_pass = bool(pass_cond and rust_hip_ready)
    return {
        "producer_cmd": producer_cmd,
        "contract_pass": contract_pass,
        "missing_fields": missing,
        "runtime_kind": runtime_kind,
        "rust_hip_ready": rust_hip_ready,
        "strict_rust_hip_pass": strict_rust_hip_pass,
        "next_action": next_action,
        "pass": pass_cond,
        "probe": data,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--producer-cmd", default="python implementation/phase1/engine_hook_stub.py")
    p.add_argument("--require-rust-hip", action="store_true")
    p.add_argument("--out", default="implementation/phase1/zero_copy_real_probe_report.json")
    args = p.parse_args()

    report = run(args.producer_cmd, args.require_rust_hip)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote zero-copy real probe report: {out}")
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
