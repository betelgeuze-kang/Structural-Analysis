#!/usr/bin/env python3
"""Phase-D4 moving-load attention kernel for speed/position-aware graph updates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


REASONS = {
    "PASS": "moving-load attention kernel validated",
    "ERR_INVALID_INPUT": "invalid attention input",
    "ERR_SHAPE": "attention kernel shape or monotonicity check failed",
}


def compute_moving_load_attention(
    *,
    node_count: int,
    position_idx: int,
    speed_m_s: float,
    gain: float = 0.35,
    bandwidth_nodes: float = 6.0,
) -> list[float]:
    """Return per-node additive attention weights in [0, gain]."""
    if node_count < 3:
        raise ValueError("node_count must be >= 3")
    if not (0.0 <= gain <= 2.0):
        raise ValueError("gain must be in [0, 2]")
    if bandwidth_nodes <= 0.0:
        raise ValueError("bandwidth_nodes must be > 0")
    if speed_m_s < 0.0:
        raise ValueError("speed_m_s must be >= 0")

    pos = max(0, min(node_count - 1, int(position_idx)))
    speed_scale = max(0.55, min(1.85, 1.0 + 0.018 * (float(speed_m_s) - 20.0)))
    sigma = float(bandwidth_nodes) * speed_scale

    weights: list[float] = []
    inv = 1.0 / max(1e-9, 2.0 * sigma * sigma)
    for i in range(node_count):
        d = float(i - pos)
        base = math.exp(-(d * d) * inv)
        weights.append(float(gain) * base)

    peak = max(weights)
    if peak <= 1e-12:
        return [0.0 for _ in weights]
    # Keep peak exactly at gain for stable scaling.
    scale = float(gain) / peak
    return [w * scale for w in weights]


def torch_moving_load_attention(
    torch,
    *,
    node_count: int,
    position_idx: int,
    speed_m_s: float,
    gain: float = 0.35,
    bandwidth_nodes: float = 6.0,
    device: str | None = None,
):
    """Torch tensor variant used by T-GNN forward pass."""
    if node_count < 3:
        raise ValueError("node_count must be >= 3")
    if bandwidth_nodes <= 0.0:
        raise ValueError("bandwidth_nodes must be > 0")

    pos = max(0, min(node_count - 1, int(position_idx)))
    idx = torch.arange(node_count, dtype=torch.float32, device=device)
    speed_scale = max(0.55, min(1.85, 1.0 + 0.018 * (float(speed_m_s) - 20.0)))
    sigma = float(bandwidth_nodes) * speed_scale
    coeff = -1.0 / max(1e-9, 2.0 * sigma * sigma)
    g = torch.exp(coeff * (idx - float(pos)) ** 2)
    g = g / torch.clamp(torch.max(g), min=1e-9)
    return float(gain) * g


def _check_monotonic_away_from_peak(weights: list[float], peak_idx: int) -> bool:
    if peak_idx <= 0 or peak_idx >= len(weights) - 1:
        return False
    left = weights[: peak_idx + 1]
    right = weights[peak_idx:]
    left_ok = all(left[i] >= left[i - 1] - 1e-9 for i in range(1, len(left)))
    right_ok = all(right[i] <= right[i - 1] + 1e-9 for i in range(1, len(right)))
    return bool(left_ok and right_ok)


def _effective_support(weights: list[float], frac: float = 0.25) -> int:
    if not weights:
        return 0
    threshold = max(weights) * float(frac)
    return sum(1 for w in weights if w >= threshold)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--node-count", type=int, default=161)
    p.add_argument("--position-idx", type=int, default=80)
    p.add_argument("--speed-low", type=float, default=15.0)
    p.add_argument("--speed-high", type=float, default=35.0)
    p.add_argument("--gain", type=float, default=0.35)
    p.add_argument("--bandwidth", type=float, default=6.0)
    p.add_argument("--out", default="implementation/phase1/moving_load_attention_report.json")
    args = p.parse_args()

    try:
        low = compute_moving_load_attention(
            node_count=int(args.node_count),
            position_idx=int(args.position_idx),
            speed_m_s=float(args.speed_low),
            gain=float(args.gain),
            bandwidth_nodes=float(args.bandwidth),
        )
        high = compute_moving_load_attention(
            node_count=int(args.node_count),
            position_idx=int(args.position_idx),
            speed_m_s=float(args.speed_high),
            gain=float(args.gain),
            bandwidth_nodes=float(args.bandwidth),
        )
    except Exception as exc:  # noqa: BLE001
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-moving-load-attention",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote moving-load attention report: {out}")
        raise SystemExit(1)

    peak_idx = int(args.position_idx)
    peak_centered = int(max(range(len(low)), key=lambda i: low[i])) == max(0, min(int(args.node_count) - 1, peak_idx))
    bounded = min(low) >= -1e-9 and max(low) <= float(args.gain) + 1e-9
    shape_ok = _check_monotonic_away_from_peak(low, max(1, min(int(args.node_count) - 2, peak_idx)))
    support_low = _effective_support(low)
    support_high = _effective_support(high)
    speed_scaling = bool(support_high >= support_low)

    checks = {
        "peak_centered": bool(peak_centered),
        "bounded_nonnegative": bool(bounded),
        "shape_monotonic": bool(shape_ok),
        "speed_scaling_monotonic": bool(speed_scaling),
    }
    contract_pass = all(checks.values())
    reason_code = "PASS" if contract_pass else "ERR_SHAPE"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-moving-load-attention",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "node_count": int(args.node_count),
            "position_idx": int(args.position_idx),
            "speed_low": float(args.speed_low),
            "speed_high": float(args.speed_high),
            "gain": float(args.gain),
            "bandwidth": float(args.bandwidth),
        },
        "checks": checks,
        "metrics": {
            "support_low_count": int(support_low),
            "support_high_count": int(support_high),
            "peak_value": float(max(low)),
            "sum_low": float(sum(low)),
            "sum_high": float(sum(high)),
        },
        "sample_head": {
            "low_speed": [float(v) for v in low[:16]],
            "high_speed": [float(v) for v in high[:16]],
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote moving-load attention report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
