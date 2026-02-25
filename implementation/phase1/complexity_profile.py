#!/usr/bin/env python3
"""O(N) guardrail profiler scaffold for Phase 1.

This does not benchmark HIP kernels yet; it provides a reproducible, local check
that the current LF preprocessing/export path remains near-linear as N grows.
"""

import argparse
import json
import math
import time
from pathlib import Path


def synthetic_linear_workload(n: int) -> float:
    """A deterministic O(N) stand-in for LF data preparation path."""
    acc = 0.0
    for i in range(n):
        x = (i % 97) * 0.001
        acc += x * x + 0.5 * x
    return acc


def run_profile(sizes: list[int], repeats: int) -> list[dict]:
    rows = []
    for n in sizes:
        best = float("inf")
        checksum = 0.0
        for _ in range(repeats):
            t0 = time.perf_counter()
            checksum = synthetic_linear_workload(n)
            elapsed = time.perf_counter() - t0
            best = min(best, elapsed)
        rows.append({"n": n, "seconds": best, "checksum": checksum})
    return rows


def fit_power_law(rows: list[dict]) -> float:
    """Fit log(seconds)=a+p*log(n), return p."""
    xs = [math.log(r["n"]) for r in rows]
    ys = [math.log(max(r["seconds"], 1e-12)) for r in rows]

    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    return num / den if den > 0 else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="2000,4000,8000,16000,32000")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", default="implementation/phase1/complexity_report.json")
    parser.add_argument("--lower", type=float, default=0.85)
    parser.add_argument("--upper", type=float, default=1.15)
    args = parser.parse_args()

    sizes = [int(x.strip()) for x in args.sizes.split(",") if x.strip()]
    rows = run_profile(sizes, args.repeats)
    p = fit_power_law(rows)
    within_guardrail = args.lower <= p <= args.upper

    report = {
        "sizes": sizes,
        "repeats": args.repeats,
        "rows": rows,
        "slope_p": p,
        "guardrail": {"lower": args.lower, "upper": args.upper},
        "within_guardrail": within_guardrail,
        "note": "Scaffold measurement for LF preprocessing path; replace workload with Rust/HIP runtime hook when available.",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Wrote complexity report: {out}")
    print(f"Estimated slope p = {p:.4f}")
    print("Guardrail pass" if within_guardrail else "Guardrail warning")


if __name__ == "__main__":
    main()
