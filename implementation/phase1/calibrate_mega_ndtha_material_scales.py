#!/usr/bin/env python3
"""Build calibration profile for mega NDTHA partitioned stress runs.

This derives coarse global scaling factors from HF benchmark exports so that
the 10M projected surrogate does not start from aggressively unstable scales.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics


REASONS = {
    "PASS": "mega ndtha calibration profile generated",
    "ERR_INVALID_INPUT": "invalid calibration input",
    "ERR_CASES": "benchmark cases missing/invalid",
}


def _clip(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def _load(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_cases(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        rows = payload.get("cases")
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    return []


def _metric_hf(case: dict, name: str) -> float | None:
    m = case.get("metrics")
    if not isinstance(m, dict):
        return None
    mm = m.get(name)
    if not isinstance(mm, dict):
        return None
    try:
        v = float(mm.get("hf"))
    except Exception:
        return None
    return v if math.isfinite(v) else None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--target-drift-pct", type=float, default=1.5)
    p.add_argument("--ref-base-shear-kn", type=float, default=15000.0)
    p.add_argument("--out", default="implementation/phase1/mega_ndtha_calibration_profile.json")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        if float(args.target_drift_pct) <= 0.0 or float(args.ref_base_shear_kn) <= 0.0:
            raise ValueError("target/ref values must be > 0")

        payload = _load(str(args.cases))
        cases = _as_cases(payload)
        if len(cases) == 0:
            raise RuntimeError("no benchmark cases")

        drift_vals = []
        shear_vals = []
        for c in cases:
            d = _metric_hf(c, "drift_ratio_pct")
            s = _metric_hf(c, "base_shear_kN")
            if d is not None:
                drift_vals.append(float(d))
            if s is not None:
                shear_vals.append(float(s))

        if len(drift_vals) == 0:
            raise RuntimeError("no hf drift metrics")

        drift_median = float(statistics.median(drift_vals))
        shear_median = float(statistics.median(shear_vals)) if shear_vals else float(args.ref_base_shear_kn)

        # Coarse physically-motivated scaling:
        # lower drift target -> higher stiffness, and mass adjusted to avoid
        # over-shifting natural frequencies in one shot.
        stiffness_scale = _clip(drift_median / max(0.05, float(args.target_drift_pct)), 0.5, 3.0)
        mass_scale = _clip(1.0 / math.sqrt(max(1e-9, stiffness_scale)), 0.6, 1.6)
        yield_scale = _clip(drift_median / max(0.05, float(args.target_drift_pct)), 0.6, 1.8)
        axial_scale = _clip((max(1.0, shear_median) / float(args.ref_base_shear_kn)) ** 0.25, 0.7, 1.8)

        base_shear_scale = _clip(shear_median / float(args.ref_base_shear_kn), 0.05, 1.5)

        result = {
            "stiffness_scale": float(stiffness_scale),
            "mass_scale": float(mass_scale),
            "yield_scale": float(yield_scale),
            "axial_scale": float(axial_scale),
            "base_shear_scale": float(base_shear_scale),
        }
        checks = {
            "positive_scales": all(float(v) > 0.0 for v in result.values()),
            "finite_scales": all(math.isfinite(float(v)) for v in result.values()),
        }
        contract_pass = bool(all(checks.values()))
        reason_code = "PASS" if contract_pass else "ERR_INVALID_INPUT"

        report = {
            "schema_version": "1.0",
            "run_id": "phase3-mega-ndtha-calibration",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "cases": str(args.cases),
                "target_drift_pct": float(args.target_drift_pct),
                "ref_base_shear_kn": float(args.ref_base_shear_kn),
            },
            "summary": {
                "case_count": int(len(cases)),
                "hf_drift_median_pct": float(drift_median),
                "hf_base_shear_median_kn": float(shear_median),
            },
            "scales": result,
            "checks": checks,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote mega NDTHA calibration profile: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except RuntimeError as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-mega-ndtha-calibration",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {"cases": str(args.cases)},
            "contract_pass": False,
            "reason_code": "ERR_CASES",
            "reason": f"{REASONS['ERR_CASES']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote mega NDTHA calibration profile: {out}")
        raise SystemExit(1)
    except Exception as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-mega-ndtha-calibration",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {"cases": str(args.cases)},
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote mega NDTHA calibration profile: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
