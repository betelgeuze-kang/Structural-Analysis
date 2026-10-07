"""Prepare retrospective measurement checkpoints; never dispatch a solver.

The original row sequence and axes are untouched. A first upward crossing is
an explicitly derived statistic, not a replacement experimental history.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path


MEASUREMENT_SHA256 = "f7dc12eb93be7bb22812e502cf6fb1802f9105c657ab2032c8cc1ce4e7673126"


def crossings(rows: list[dict], target: Decimal) -> list[dict]:
    """Return ordered, half-open upward crossings; preserve repeated crossings."""
    output = []
    for left, right in zip(rows, rows[1:]):
        x0, x1 = (Decimal(r["deflection_mm_xml"]) for r in (left, right))
        y0, y1 = (Decimal(r["load_kN_xml"]) for r in (left, right))
        if x0 < target <= x1:
            fraction = (target - x0) / (x1 - x0)
            output.append(
                {
                    "source_rows": [left["source_row"], right["source_row"]],
                    "fraction": str(fraction),
                    "load_channel_kN": str(y0 + fraction * (y1 - y0)),
                }
            )
    return output


def checkpoint(rows: list[dict], target: str) -> dict:
    hits = crossings(rows, Decimal(target))
    return {
        "deflection_mm": target,
        "status": "available" if hits else "outside_observed_upward_crossings",
        "upward_crossing_count": len(hits),
        "selected": hits[0] if hits else None,
        "all_crossings": hits,
    }


def prepare(measurements: Path, plan_path: Path) -> dict:
    raw = measurements.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MEASUREMENT_SHA256:
        raise ValueError("measurement_identity_mismatch")
    rows = [json.loads(line) for line in raw.splitlines()]
    if len(rows) != 2632 or [r["source_row"] for r in rows] != list(range(5, 2637)):
        raise ValueError("measurement_row_order_mismatch")
    plan_raw = plan_path.read_bytes()
    plan = json.loads(plan_raw)
    if plan["status"] != "HOLD" or plan["solver_dispatch_authorized"] is not False:
        raise ValueError("this_tool_only_prepares_held_comparisons")
    values = [checkpoint(rows, target) for target in plan["checkpoint_deflections_mm"]]
    index = {v["deflection_mm"]: v for v in values}
    left, right = (index[x]["selected"] for x in plan["early_secant_interval_mm"])
    stiffness = None
    if left is not None and right is not None:
        interval = [Decimal(x) for x in plan["early_secant_interval_mm"]]
        stiffness = str(
            (Decimal(right["load_channel_kN"]) - Decimal(left["load_channel_kN"]))
            / (interval[1] - interval[0])
        )
    return {
        "schema_version": "he-ref-retrospective-checkpoints.v1",
        "status": "HOLD",
        "specimen_count": 1,
        "measurement_pair_count": len(rows),
        "measurement_sha256": hashlib.sha256(raw).hexdigest(),
        "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "solver_run_count": 0,
        "physical_validation_claim": False,
        "force_convention": "unresolved_original_workbook_channel",
        "axis_zero_shift_mm": "0",
        "checkpoints": values,
        "early_secant_channel_kN_per_mm": stiffness,
        "early_secant_is_material_elastic_modulus": False,
        "raw_displacement_decreases": sum(
            Decimal(b["deflection_mm_xml"]) < Decimal(a["deflection_mm_xml"])
            for a, b in zip(rows, rows[1:])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.measurements, args.plan)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
