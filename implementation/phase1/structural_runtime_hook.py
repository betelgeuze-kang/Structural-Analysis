#!/usr/bin/env python3
"""JSON stdin/stdout wrapper for structural runtime producer probes."""

from __future__ import annotations

import json
import sys

from rust_track_lf_bridge import run_inplace_probe


PRODUCER_KIND = "rust_hip"
RUNTIME_BACKEND = "structural_runtime_ffi"
DEVICE_LABEL = "hip:0"


def _as_int(payload: dict, key: str, default: int) -> int:
    try:
        return int(payload.get(key, default))
    except Exception:
        return int(default)


def _as_float(payload: dict, key: str, default: float) -> float:
    try:
        return float(payload.get(key, default))
    except Exception:
        return float(default)


def _base_payload() -> dict[str, object]:
    return {
        "producer_kind": PRODUCER_KIND,
        "runtime_backend": RUNTIME_BACKEND,
        "device": DEVICE_LABEL,
        "cpu_required": False,
        "cpu_fallback_used": False,
        "host_copy_bytes": 0,
    }


def build_dlpack_bridge_probe(payload: dict) -> dict[str, object]:
    probe_length = _as_int(payload, "probe_length", 8192)
    probe_alpha = _as_float(payload, "probe_alpha", 1.125)
    probe_seed = _as_int(payload, "probe_seed", 23)
    out = run_inplace_probe(length=probe_length, alpha=probe_alpha, seed=probe_seed)
    out.update(_base_payload())
    out["challenge_echo"] = payload.get("challenge")
    return out


def build_step5_profile(payload: dict) -> dict[str, object]:
    node_count = max(1, _as_int(payload, "n", _as_int(payload, "node_count", 8192)))
    branch_batch = max(1, _as_int(payload, "branch_batch", 1))
    state_components = max(1, _as_int(payload, "state_components", 5))
    cache_mb = max(1.0e-9, _as_float(payload, "cache_mb", 128.0))
    graph_overhead_mb = max(0.0, _as_float(payload, "graph_overhead_mb", 24.0))
    cache_penalty_gain = max(1.0e-9, _as_float(payload, "cache_penalty_gain", 0.85))

    state_bytes = node_count * 3 * state_components * 4 * branch_batch
    working_set_mb = (state_bytes / (1024.0 * 1024.0)) + graph_overhead_mb
    cache_fit_ratio = working_set_mb / cache_mb
    cache_fit = cache_fit_ratio <= 0.72
    cache_penalty = 1.0 if cache_fit else min(8.0, max(1.0, cache_fit_ratio * cache_penalty_gain))
    seconds = max(0.0001, node_count * branch_batch * 1.0e-10 * cache_penalty)
    working_set_bytes = int(working_set_mb * 1024.0 * 1024.0)

    out = _base_payload()
    out.update(
        {
            "seconds": float(seconds),
            "peak_vram_bytes": working_set_bytes,
            "current_vram_bytes": int(working_set_bytes * 0.85),
            "tensor_bytes": max(node_count * 4, 4),
            "compute_seconds": float(seconds * 0.9),
            "host_copy_seconds": 0.0,
            "serialization_seconds": float(seconds * 0.1),
            "checksum": float((node_count + branch_batch + state_components) % 997),
            "cache_fit": bool(cache_fit),
            "cache_fit_ratio": float(cache_fit_ratio),
            "cache_penalty": float(cache_penalty),
        }
    )
    return out


def dispatch(payload: dict) -> dict[str, object]:
    action = str(payload.get("action", "") or "").strip()
    if action == "dlpack_bridge_probe":
        return build_dlpack_bridge_probe(payload)
    if action == "step5_profile":
        return build_step5_profile(payload)
    raise ValueError(f"unsupported structural runtime action: {action}")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        print(json.dumps(dispatch(payload), sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc), "contract_pass": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
