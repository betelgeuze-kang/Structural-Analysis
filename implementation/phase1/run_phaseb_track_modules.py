#!/usr/bin/env python3
"""Run Phase-B track dynamics modules (B1~B4) in sequence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import time

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "all phase-b track modules passed",
    "ERR_MODULE_FAIL": "one or more phase-b modules failed",
}

PHASEB_RUNNER_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out", "b1_out", "b2_out", "b3_out", "b4_out", "irregularity_csv"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
        "b1_out": {"type": "string", "minLength": 1},
        "b2_out": {"type": "string", "minLength": 1},
        "b3_out": {"type": "string", "minLength": 1},
        "b4_out": {"type": "string", "minLength": 1},
        "irregularity_csv": {"type": "string", "minLength": 1},
    },
}


def _run(name: str, cmd: list[str], logs: list[dict]) -> bool:
    t0 = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True)
    logs.append(
        {
            "step": name,
            "seconds": time.time() - t0,
            "command": shlex.join(cmd),
            "return_code": int(proc.returncode),
            "stdout_tail": (proc.stdout or "")[-1200:],
            "stderr_tail": (proc.stderr or "")[-1200:],
        }
    )
    return proc.returncode == 0


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    logger = get_logger("phase1.run_phaseb_track_modules")
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/phaseb_track_summary_report.json")
    p.add_argument("--b1-out", default="implementation/phase1/track_lf_solver_report.json")
    p.add_argument("--b2-out", default="implementation/phase1/moving_load_integrator_report.json")
    p.add_argument("--b3-out", default="implementation/phase1/vti_coupled_solver_report.json")
    p.add_argument("--b4-out", default="implementation/phase1/track_irregularity_report.json")
    p.add_argument("--irregularity-csv", default="implementation/phase1/open_data/track/irregularity_profile.csv")
    args = p.parse_args()

    input_payload = {
        "out": str(args.out),
        "b1_out": str(args.b1_out),
        "b2_out": str(args.b2_out),
        "b3_out": str(args.b3_out),
        "b4_out": str(args.b4_out),
        "irregularity_csv": str(args.irregularity_csv),
    }
    try:
        validate_input_contract(
            input_payload,
            PHASEB_RUNNER_INPUT_SCHEMA,
            label="phase-b.run_phaseb_track_modules",
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "phaseb.invalid_input", error=str(exc))
        raise SystemExit(1)

    log_event(logger, logging.INFO, "phaseb.start", inputs=input_payload)
    logs: list[dict] = []

    ok_b4 = _run(
        "B4_track_irregularity_generator",
        [
            sys.executable,
            "implementation/phase1/track_irregularity_generator.py",
            "--out-csv",
            str(args.irregularity_csv),
            "--out",
            str(args.b4_out),
        ],
        logs,
    )

    ok_b1 = _run(
        "B1_track_lf_solver",
        [
            sys.executable,
            "implementation/phase1/track_lf_solver.py",
            "--out",
            str(args.b1_out),
        ],
        logs,
    )

    ok_b2 = _run(
        "B2_moving_load_integrator",
        [
            sys.executable,
            "implementation/phase1/moving_load_integrator.py",
            "--out",
            str(args.b2_out),
        ],
        logs,
    )

    ok_b3 = _run(
        "B3_vti_coupled_solver",
        [
            sys.executable,
            "implementation/phase1/vti_coupled_solver.py",
            "--out",
            str(args.b3_out),
        ],
        logs,
    )

    r_b1 = _load_json(str(args.b1_out))
    r_b2 = _load_json(str(args.b2_out))
    r_b3 = _load_json(str(args.b3_out))
    r_b4 = _load_json(str(args.b4_out))

    checks = {
        "B1_track_lf_solver": bool(ok_b1 and r_b1.get("contract_pass", False)),
        "B2_moving_load_integrator": bool(ok_b2 and r_b2.get("contract_pass", False)),
        "B3_vti_coupled_solver": bool(ok_b3 and r_b3.get("contract_pass", False)),
        "B4_track_irregularity_generator": bool(ok_b4 and r_b4.get("contract_pass", False)),
    }

    all_pass = all(checks.values())
    reason_code = "PASS" if all_pass else "ERR_MODULE_FAIL"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-phaseb-track-modules",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "reports": {
            "B1": str(args.b1_out),
            "B2": str(args.b2_out),
            "B3": str(args.b3_out),
            "B4": str(args.b4_out),
            "irregularity_csv": str(args.irregularity_csv),
        },
        "steps": logs,
        "contract_pass": bool(all_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote phase-b track summary report: {out}")
    log_event(
        logger,
        logging.INFO,
        "phaseb.completed",
        contract_pass=bool(all_pass),
        reason_code=reason_code,
    )
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
