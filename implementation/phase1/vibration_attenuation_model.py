#!/usr/bin/env python3
"""Phase-E2: vibration attenuation model along railway-tunnel-building path."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


REASONS = {
    "PASS": "vibration attenuation model passed",
    "ERR_INVALID_INPUT": "invalid attenuation model input",
    "ERR_MONOTONICITY": "attenuation monotonicity checks failed",
}


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_attenuation(
    *,
    substructuring_report: str | None,
    distance_min_m: float,
    distance_max_m: float,
    distance_step_m: float,
) -> dict:
    if distance_min_m <= 0.0 or distance_max_m <= distance_min_m or distance_step_m <= 0.0:
        raise ValueError("distance range is invalid")

    sub_payload = None
    if substructuring_report:
        p = Path(substructuring_report)
        if p.exists():
            sub_payload = _load_json(str(p))

    base_ref_mm_s = 0.14
    sub_ok = True
    if isinstance(sub_payload, dict):
        sub_ok = bool(sub_payload.get("contract_pass", False))
        if sub_ok:
            base_ref_mm_s = max(
                0.02,
                min(
                    0.35,
                    1e3 * float(sub_payload.get("metrics", {}).get("max_track_disp_m", 1.4e-4)),
                ),
            )

    freq_bands = [8.0, 16.0, 31.5, 63.0]
    distances = []
    x = float(distance_min_m)
    while x <= float(distance_max_m) + 1e-9:
        distances.append(round(x, 6))
        x += float(distance_step_m)

    rows: list[dict] = []
    by_freq: dict[float, list[float]] = {f: [] for f in freq_bands}

    for f_hz in freq_bands:
        alpha = 0.010 + 0.00045 * f_hz
        f_scale = 1.0 / (1.0 + 0.018 * f_hz)
        for d in distances:
            amp = base_ref_mm_s * f_scale * math.exp(-alpha * d) / math.sqrt(max(d, 1.0))
            by_freq[f_hz].append(amp)
            rows.append(
                {
                    "freq_hz": float(f_hz),
                    "distance_m": float(d),
                    "velocity_mm_s": float(amp),
                }
            )

    finite_ok = all(math.isfinite(v) and v >= 0.0 for values in by_freq.values() for v in values)
    monotonic_distance = True
    for values in by_freq.values():
        if any(values[i] > values[i - 1] + 1e-12 for i in range(1, len(values))):
            monotonic_distance = False
            break

    # Higher frequency should attenuate stronger at far distance.
    far_idx = len(distances) - 1
    high_freq_decay = by_freq[63.0][far_idx] <= by_freq[8.0][far_idx] + 1e-12

    checks = {
        "substructuring_linked": bool(sub_ok),
        "finite_values": bool(finite_ok),
        "monotonic_distance_decay": bool(monotonic_distance),
        "high_frequency_decay_stronger": bool(high_freq_decay),
    }
    contract_pass = bool(finite_ok and monotonic_distance and high_freq_decay and sub_ok)
    reason_code = "PASS" if contract_pass else "ERR_MONOTONICITY"

    return {
        "schema_version": "1.0",
        "run_id": "phase1-vibration-attenuation-model",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "substructuring_report": substructuring_report,
            "distance_min_m": float(distance_min_m),
            "distance_max_m": float(distance_max_m),
            "distance_step_m": float(distance_step_m),
            "freq_bands_hz": freq_bands,
            "base_reference_velocity_mm_s": float(base_ref_mm_s),
        },
        "checks": checks,
        "metrics": {
            "distance_count": len(distances),
            "max_velocity_mm_s": float(max(max(vs) for vs in by_freq.values())),
            "min_velocity_mm_s": float(min(min(vs) for vs in by_freq.values())),
            "far_field_ratio_63_to_8": float(by_freq[63.0][far_idx] / max(by_freq[8.0][far_idx], 1e-12)),
        },
        "curve_head": rows[:128],
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--substructuring", default="implementation/phase1/substructuring_interface_report.json")
    p.add_argument("--distance-min-m", type=float, default=5.0)
    p.add_argument("--distance-max-m", type=float, default=120.0)
    p.add_argument("--distance-step-m", type=float, default=5.0)
    p.add_argument("--out", default="implementation/phase1/vibration_attenuation_report.json")
    args = p.parse_args()

    try:
        payload = run_attenuation(
            substructuring_report=str(args.substructuring) if args.substructuring else None,
            distance_min_m=float(args.distance_min_m),
            distance_max_m=float(args.distance_max_m),
            distance_step_m=float(args.distance_step_m),
        )
    except Exception as exc:  # noqa: BLE001
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-vibration-attenuation-model",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote vibration attenuation report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
