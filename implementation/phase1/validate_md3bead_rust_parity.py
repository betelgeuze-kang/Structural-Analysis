#!/usr/bin/env python3
"""Validate 1:1 parity between Python 3-Bead reference and Rust hook path."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shlex
import subprocess

from md3bead_soa import run_relaxation_case, run_workload_pass

SCHEMA_VERSION = "1.0"
RUN_ID = "phase1-rust-md3bead-parity"

REASON_CODES = {
    "PASS": "rust hook and python reference are numerically equivalent within tolerance",
    "ERR_HOOK_EXEC": "rust hook execution failed",
    "ERR_PARITY_STEP1": "step1_case parity mismatch",
    "ERR_PARITY_STEP5": "step5_profile parity mismatch",
}


def _run_json_cmd(command: str, payload: dict) -> dict:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _close(a: float, b: float, atol: float, rtol: float) -> bool:
    return abs(a - b) <= (atol + rtol * max(abs(a), abs(b), 1.0))


def _parse_float_list(text: str) -> list[float]:
    vals = [float(x.strip()) for x in str(text).split(",") if x.strip()]
    if not vals:
        raise SystemExit("list must not be empty")
    return vals


def _parse_int_list(text: str) -> list[int]:
    vals = [int(x.strip()) for x in str(text).split(",") if x.strip()]
    if not vals:
        raise SystemExit("list must not be empty")
    return vals


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rust-hook-cmd", default="python3 implementation/phase1/rust_hip_md3bead_hook.py")
    p.add_argument("--node-count", type=int, default=96)
    p.add_argument("--forces", default="120,180,260")
    p.add_argument("--decays", default="0.965,0.958,0.952")
    p.add_argument("--max-steps", type=int, default=400)
    p.add_argument("--tol", type=float, default=1e-2)
    p.add_argument("--profile-sizes", default="2000,4000,8000")
    p.add_argument("--atol", type=float, default=1e-4)
    p.add_argument("--rtol", type=float, default=5e-4)
    p.add_argument("--out", default="implementation/phase1/rust_md3bead_parity_report.json")
    args = p.parse_args()

    forces = _parse_float_list(args.forces)
    decays = _parse_float_list(args.decays)
    if len(forces) != len(decays):
        raise SystemExit("--forces and --decays must have same length")
    profile_sizes = _parse_int_list(args.profile_sizes)

    step1_rows = []
    step1_all_pass = True
    step5_rows = []
    step5_all_pass = True

    try:
        for i, (force0, decay) in enumerate(zip(forces, decays), start=1):
            py = run_relaxation_case(
                node_count=int(args.node_count),
                base_force=float(force0),
                max_steps=int(args.max_steps),
                tol=float(args.tol),
                decay_hint=float(decay),
            )
            rs = _run_json_cmd(
                args.rust_hook_cmd,
                {
                    "action": "step1_case",
                    "force0": force0,
                    "decay": decay,
                    "max_steps": int(args.max_steps),
                    "tol": float(args.tol),
                    "node_count": int(args.node_count),
                },
            )

            fields = [
                "final_force_norm",
                "max_unbalanced_force",
                "kinetic_energy",
                "system_temperature",
                "potential_energy",
            ]
            field_checks = {}
            for key in fields:
                a = float(py.get(key, 0.0))
                b = float(rs.get(key, 0.0))
                ok = _close(a, b, atol=float(args.atol), rtol=float(args.rtol))
                field_checks[key] = {
                    "python": a,
                    "rust": b,
                    "abs_diff": abs(a - b),
                    "pass": ok,
                }

            steps_equal = int(py.get("steps", -1)) == int(rs.get("steps", -2))
            converged_equal = bool(py.get("converged", False)) == bool(rs.get("converged", True))
            model_equal = str(py.get("model", "")) == str(rs.get("model", ""))
            row_pass = steps_equal and converged_equal and model_equal and all(v["pass"] for v in field_checks.values())
            step1_all_pass = step1_all_pass and row_pass

            step1_rows.append(
                {
                    "case_id": f"C{i}",
                    "force0": force0,
                    "decay": decay,
                    "steps_equal": steps_equal,
                    "converged_equal": converged_equal,
                    "model_equal": model_equal,
                    "fields": field_checks,
                    "pass": row_pass,
                }
            )

        for n in profile_sizes:
            py = run_workload_pass(node_count=n, steps=3)
            rs = _run_json_cmd(args.rust_hook_cmd, {"action": "step5_profile", "n": int(n)})
            fields = ["work_scalar", "max_unbalanced_force"]
            field_checks = {}
            for key in fields:
                a = float(py.get(key, 0.0))
                b = float(rs.get(key, 0.0))
                ok = _close(a, b, atol=float(args.atol), rtol=float(args.rtol))
                field_checks[key] = {
                    "python": a,
                    "rust": b,
                    "abs_diff": abs(a - b),
                    "pass": ok,
                }

            bead_equal = int(py.get("bead_count", -1)) == int(rs.get("bead_count", -2))
            bond_equal = int(py.get("bond_count", -1)) == int(rs.get("bond_count", -2))
            model_equal = str(py.get("model", "")) == str(rs.get("model", ""))
            row_pass = bead_equal and bond_equal and model_equal and all(v["pass"] for v in field_checks.values())
            step5_all_pass = step5_all_pass and row_pass
            step5_rows.append(
                {
                    "n": int(n),
                    "bead_equal": bead_equal,
                    "bond_equal": bond_equal,
                    "model_equal": model_equal,
                    "fields": field_checks,
                    "pass": row_pass,
                }
            )

    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_HOOK_EXEC",
            "reason": f"{REASON_CODES['ERR_HOOK_EXEC']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote parity report: {out}")
        raise SystemExit(1)

    if not step1_all_pass:
        reason_code = "ERR_PARITY_STEP1"
    elif not step5_all_pass:
        reason_code = "ERR_PARITY_STEP5"
    else:
        reason_code = "PASS"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
        "config": {
            "rust_hook_cmd": args.rust_hook_cmd,
            "node_count": int(args.node_count),
            "forces": forces,
            "decays": decays,
            "max_steps": int(args.max_steps),
            "tol": float(args.tol),
            "profile_sizes": profile_sizes,
            "atol": float(args.atol),
            "rtol": float(args.rtol),
        },
        "step1_parity": {
            "pass": step1_all_pass,
            "rows": step1_rows,
        },
        "step5_parity": {
            "pass": step5_all_pass,
            "rows": step5_rows,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote parity report: {out}")
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
