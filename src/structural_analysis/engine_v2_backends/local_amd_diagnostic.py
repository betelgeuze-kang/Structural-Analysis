"""Bounded local AMD discovery, never a structural/GPU qualification receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading


def _command(
    argv: list[str], *, timeout: float = 5.0, maximum_bytes: int = 262144
) -> dict:
    if (
        not 0 < timeout <= 30
        or type(maximum_bytes) is not int
        or not 1 <= maximum_bytes <= 1048576
    ):
        raise ValueError("bounded timeout and output limit required")
    data = bytearray()
    failures = []
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    assert process.stdout is not None

    def read():
        try:
            while chunk := process.stdout.read(8192):
                if len(data) + len(chunk) > maximum_bytes:
                    failures.append("output_limit")
                    return
                data.extend(chunk)
        except OSError:
            failures.append("read_failed")

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    status = "unknown"
    try:
        thread.join(timeout)
        if thread.is_alive():
            status = "timeout"
        elif failures:
            status = failures[0]
        else:
            try:
                status = (
                    "completed" if process.wait(timeout=0.25) == 0 else "nonzero_exit"
                )
            except subprocess.TimeoutExpired:
                status = "timeout"
    finally:
        # This helper owns a new process group. Kill only that group, including
        # any child keeping the output pipe alive; never inherited host jobs.
        if status not in ("completed", "nonzero_exit"):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=2)
        thread.join(1)
        if not thread.is_alive():
            process.stdout.close()
    return {
        "status": status,
        "output_bytes": len(data),
        "output_sha256": hashlib.sha256(data).hexdigest(),
        "text": data.decode("utf-8", errors="replace"),
    }


def diagnose_amd_environment() -> dict:
    report = {
        "schema_version": "local-amd-discovery.v1",
        "platform": sys.platform,
        "status": "unsupported_platform",
        "rocminfo_available": False,
        "kfd_present": False,
        "kfd_read_write_access": False,
        "observed_agents": [],
        "probe": None,
        "claims": {
            "gpu_kernel_executed": False,
            "structural_profile_verified": False,
            "cpu_gpu_parity": False,
            "performance_improvement": False,
            "vram_capacity_qualified": False,
        },
    }
    if not sys.platform.startswith("linux"):
        return report
    report["kfd_present"] = Path("/dev/kfd").exists()
    report["kfd_read_write_access"] = os.access("/dev/kfd", os.R_OK | os.W_OK)
    executable = shutil.which("rocminfo")
    if executable is None:
        report["status"] = "rocminfo_unavailable"
        return report
    report["rocminfo_available"] = True
    try:
        result = _command([executable])
    except OSError:
        report["status"] = "probe_launch_failed"
        return report
    report["probe"] = {
        k: result[k] for k in ("status", "output_bytes", "output_sha256")
    }
    if result["status"] != "completed":
        report["status"] = "probe_failed"
        return report
    report["observed_agents"] = sorted(
        set(re.findall(r"(?m)^\s*Name:\s*(gfx[0-9a-f]+)\s*$", result["text"]))
    )
    report["status"] = (
        "agents_detected_not_qualified"
        if report["observed_agents"]
        else "no_gpu_agent_reported"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = diagnose_amd_environment()
    raw = (
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    if args.output is not None:
        with args.output.open("xb") as stream:
            stream.write(raw)
    print(raw.decode(), end="")
    return 0 if report["status"] == "agents_detected_not_qualified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
