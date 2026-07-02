#!/usr/bin/env python3
"""JSON stdin/stdout stub for run_phase1_steps and bridge hooks.

Input JSON actions:
- step1_case: {force0, decay, max_steps, tol}
- step5_profile: {n}
- dlpack_bridge_probe: {}
- av_operator: {vector}
"""

import json
import math
import sys
import time


def handle_step1(payload: dict) -> dict:
    f = float(payload["force0"])
    decay = float(payload["decay"])
    max_steps = int(payload["max_steps"])
    tol = float(payload["tol"])
    converged = False
    steps = 0
    for s in range(1, max_steps + 1):
        f *= decay
        steps = s
        if f < tol:
            converged = True
            break
    return {"steps": steps, "final_force_norm": f, "converged": converged}


def handle_step5(payload: dict) -> dict:
    n = int(payload["n"])
    t0 = time.perf_counter()
    acc = 0.0
    for i in range(n):
        x = (i % 97) * 0.001
        acc += x * x + math.sin(x)
    sec = time.perf_counter() - t0
    peak_vram = n * 128
    current_vram = n * 96
    compute_seconds = sec * 0.82
    host_copy_seconds = sec * 0.11
    serialization_seconds = sec * 0.07
    return {
        "seconds": sec,
        "peak_vram_bytes": peak_vram,
        "current_vram_bytes": current_vram,
        "host_copy_bytes": 0,
        "compute_seconds": compute_seconds,
        "host_copy_seconds": host_copy_seconds,
        "serialization_seconds": serialization_seconds,
        "checksum": acc,
    }


def handle_dlpack_probe() -> dict:
    return {
        "producer_kind": "stub",
        "roundtrip_success": True,
        "shared_storage": True,
        "host_copy_bytes": 0,
        "device": "hip:0",
        "shape": [1024, 64],
        "dtype": "float32",
        "strides": [64, 1],
        "byte_offset": 0,
    }


def handle_av_operator(payload: dict) -> dict:
    v = payload["vector"]
    n = len(v)
    out = []
    for i in range(n):
        center = 4.0 * v[i]
        left = -1.0 * v[i - 1] if i > 0 else 0.0
        right = -1.0 * v[i + 1] if i < n - 1 else 0.0
        out.append(center + left + right)
    return {"result": out}


def main() -> None:
    payload = json.loads(sys.stdin.read())
    action = payload.get("action")
    if action == "step1_case":
        res = handle_step1(payload)
    elif action == "step5_profile":
        res = handle_step5(payload)
    elif action == "dlpack_bridge_probe":
        res = handle_dlpack_probe()
    elif action == "av_operator":
        res = handle_av_operator(payload)
    else:
        raise SystemExit(f"unsupported action: {action}")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
