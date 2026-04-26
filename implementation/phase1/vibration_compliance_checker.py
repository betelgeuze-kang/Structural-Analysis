#!/usr/bin/env python3
"""Phase-E3: environment vibration compliance checker (KS/ISO profile)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


REASONS = {
    "PASS": "vibration compliance checks passed",
    "ERR_INVALID_INPUT": "invalid compliance input",
    "ERR_LIMIT_EXCEEDED": "vibration limit exceeded",
}


LIMITS_MM_S = {
    "KS_F_2866_RESIDENTIAL_DAY": {
        8.0: 0.20,
        16.0: 0.16,
        31.5: 0.12,
        63.0: 0.10,
    },
    "ISO_14837_OFFICE": {
        8.0: 0.18,
        16.0: 0.14,
        31.5: 0.11,
        63.0: 0.09,
    },
}


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _nearest_limit(limit_table: dict[float, float], freq: float) -> float:
    keys = sorted(limit_table.keys())
    k = min(keys, key=lambda x: abs(float(x) - float(freq)))
    return float(limit_table[k])


def run_compliance(
    *,
    attenuation_report: str,
    standard: str,
    min_pass_ratio: float,
) -> dict:
    if standard not in LIMITS_MM_S:
        raise ValueError(f"unsupported standard: {standard}")
    if not (0.0 <= min_pass_ratio <= 1.0):
        raise ValueError("min_pass_ratio must be in [0, 1]")

    attn = _load_json(attenuation_report)
    if not bool(attn.get("contract_pass", False)):
        raise ValueError("attenuation report contract_pass is false")

    rows = attn.get("curve_head")
    if not isinstance(rows, list) or len(rows) == 0:
        raise ValueError("attenuation curve_head is empty")

    limit_table = LIMITS_MM_S[standard]

    eval_rows: list[dict] = []
    pass_count = 0
    finite = True

    for row in rows:
        freq = float(row["freq_hz"])
        dist = float(row["distance_m"])
        vel = float(row["velocity_mm_s"])
        if not (math.isfinite(freq) and math.isfinite(dist) and math.isfinite(vel) and vel >= 0.0):
            finite = False
            continue

        limit = _nearest_limit(limit_table, freq)
        ok = vel <= limit
        if ok:
            pass_count += 1

        # 1e-9 m/s reference converted from mm/s.
        vel_m_s = vel * 1e-3
        vdb = 20.0 * math.log10(max(vel_m_s, 1e-12) / 1e-9)
        eval_rows.append(
            {
                "freq_hz": freq,
                "distance_m": dist,
                "velocity_mm_s": vel,
                "limit_mm_s": limit,
                "pass": bool(ok),
                "vibration_db": float(vdb),
            }
        )

    total = max(1, len(eval_rows))
    pass_ratio = pass_count / total

    checks = {
        "standard_supported": True,
        "finite_values": bool(finite),
        "compliance_ratio_pass": bool(pass_ratio >= float(min_pass_ratio)),
    }
    contract_pass = bool(all(checks.values()))
    reason_code = "PASS" if contract_pass else "ERR_LIMIT_EXCEEDED"

    return {
        "schema_version": "1.0",
        "run_id": "phase1-vibration-compliance-checker",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "attenuation_report": attenuation_report,
            "standard": standard,
            "min_pass_ratio": float(min_pass_ratio),
        },
        "checks": checks,
        "metrics": {
            "sample_count": int(len(eval_rows)),
            "pass_ratio": float(pass_ratio),
            "max_velocity_mm_s": float(max((r["velocity_mm_s"] for r in eval_rows), default=0.0)),
            "max_over_limit_ratio": float(
                max((r["velocity_mm_s"] / max(r["limit_mm_s"], 1e-12) for r in eval_rows), default=0.0)
            ),
            "max_vibration_db": float(max((r["vibration_db"] for r in eval_rows), default=0.0)),
        },
        "curve_head": eval_rows[:128],
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--attenuation", default="implementation/phase1/vibration_attenuation_report.json")
    p.add_argument("--standard", default="KS_F_2866_RESIDENTIAL_DAY")
    p.add_argument("--min-pass-ratio", type=float, default=0.95)
    p.add_argument("--out", default="implementation/phase1/vibration_compliance_report.json")
    args = p.parse_args()

    try:
        payload = run_compliance(
            attenuation_report=str(args.attenuation),
            standard=str(args.standard),
            min_pass_ratio=float(args.min_pass_ratio),
        )
    except Exception as exc:  # noqa: BLE001
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-vibration-compliance-checker",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote vibration compliance report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
