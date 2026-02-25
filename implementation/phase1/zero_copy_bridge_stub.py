#!/usr/bin/env python3
"""Rust(HIP) <-> PyTorch zero-copy bridge scaffold using DLPack interface.

Supports optional external producer command through JSON stdin/stdout.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path


def _run_json_cmd(command: str, payload: dict) -> dict:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def run_stub(producer_cmd: str | None = None) -> dict:
    report: dict = {
        "dlpack_protocol": "enabled-by-interface",
        "torch_available": False,
        "roundtrip_success": False,
        "shared_storage": False,
        "host_copy_bytes": 0,
        "notes": [],
    }

    if producer_cmd:
        external = _run_json_cmd(producer_cmd, {"action": "dlpack_bridge_probe"})
        report.update(
            {
                "producer_cmd_used": True,
                "roundtrip_success": bool(external.get("roundtrip_success", False)),
                "shared_storage": bool(external.get("shared_storage", False)),
                "host_copy_bytes": int(external.get("host_copy_bytes", 0)),
                "device": external.get("device", "unknown"),
                "shape": external.get("shape", []),
                "dtype": external.get("dtype", "unknown"),
                "strides": external.get("strides", []),
                "byte_offset": int(external.get("byte_offset", 0)),
            }
        )
        report["notes"].append("External producer command path validated.")
    else:
        report["producer_cmd_used"] = False
        try:
            import torch  # type: ignore

            report["torch_available"] = True
            x = torch.arange(12, dtype=torch.float32, device="cpu").reshape(3, 4)
            capsule = torch.utils.dlpack.to_dlpack(x)
            y = torch.utils.dlpack.from_dlpack(capsule)
            shared = x.storage().data_ptr() == y.storage().data_ptr()
            report["roundtrip_success"] = bool(shared and x.shape == y.shape)
            report["shape"] = list(x.shape)
            report["dtype"] = str(x.dtype)
            report["strides"] = list(x.stride())
            report["byte_offset"] = 0
            report["shared_storage"] = shared
            report["device"] = str(x.device)
            report["notes"].append("CPU DLPack roundtrip checked; replace with HIP device tensor in Rust bridge stage.")
        except Exception as exc:  # noqa: BLE001
            report["notes"].append(f"torch/DLPack runtime unavailable: {exc}")
            report["notes"].append("Stub still defines JSON contract for Rust->Python bridge integration.")

    report["rust_bridge_contract"] = {
        "producer": "Rust HIP runtime exports DLPack capsule pointer",
        "consumer": "PyTorch from_dlpack without host copy",
        "expected_fields": ["shape", "dtype", "device", "strides", "byte_offset", "host_copy_bytes"],
    }
    report["pass_criteria"] = {
        "roundtrip_success": True,
        "shared_storage": True,
        "host_copy_bytes": 0,
    }
    report["pass"] = bool(report["roundtrip_success"] and report["shared_storage"] and int(report["host_copy_bytes"]) == 0)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/zero_copy_bridge_report.json")
    parser.add_argument("--producer-cmd", help="Optional external producer command for bridge probe")
    args = parser.parse_args()

    report = run_stub(producer_cmd=args.producer_cmd)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote zero-copy bridge report: {out}")


if __name__ == "__main__":
    main()
