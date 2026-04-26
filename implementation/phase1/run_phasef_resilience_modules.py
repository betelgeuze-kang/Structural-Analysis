#!/usr/bin/env python3
"""Run Phase-F resilience modules (F1~F3) and emit integrated summary."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


REASONS = {
    "PASS": "phase-f resilience modules passed",
    "ERR_MODULE_FAIL": "one or more phase-f modules failed",
}


def _run(step: str, cmd: list[str], logs: list[dict]) -> bool:
    t0 = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True)
    logs.append(
        {
            "step": step,
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
    p = argparse.ArgumentParser()
    p.add_argument("--f1-out", default="implementation/phase1/multiscale_l3_streaming_report.json")
    p.add_argument("--f2-out", default="implementation/phase1/phase_correction_assimilation_report.json")
    p.add_argument("--f3-out", default="implementation/phase1/heterogeneous_soil_ood_report.json")
    p.add_argument("--out", default="implementation/phase1/phasef_resilience_summary_report.json")
    args = p.parse_args()

    steps: list[dict] = []

    ok_f1 = _run(
        "F1_multiscale_l3_streaming",
        [
            sys.executable,
            "implementation/phase1/multiscale_l3_streaming_profile.py",
            "--out",
            str(args.f1_out),
        ],
        steps,
    )
    ok_f2 = _run(
        "F2_phase_correction_assimilation",
        [
            sys.executable,
            "implementation/phase1/phase_correction_assimilation.py",
            "--out",
            str(args.f2_out),
        ],
        steps,
    )
    ok_f3 = _run(
        "F3_heterogeneous_soil_ood_gate",
        [
            sys.executable,
            "implementation/phase1/heterogeneous_soil_ood_gate.py",
            "--out",
            str(args.f3_out),
        ],
        steps,
    )

    r1 = _load_json(str(args.f1_out))
    r2 = _load_json(str(args.f2_out))
    r3 = _load_json(str(args.f3_out))

    checks = {
        "F1_multiscale_l3_streaming": bool(ok_f1 and r1.get("contract_pass", False)),
        "F2_phase_correction_assimilation": bool(ok_f2 and r2.get("contract_pass", False)),
        "F3_heterogeneous_soil_ood_gate": bool(ok_f3 and r3.get("contract_pass", False)),
    }

    all_pass = bool(all(checks.values()))
    reason_code = "PASS" if all_pass else "ERR_MODULE_FAIL"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-phasef-resilience-modules",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "reports": {
            "F1": str(args.f1_out),
            "F2": str(args.f2_out),
            "F3": str(args.f3_out),
        },
        "steps": steps,
        "contract_pass": all_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote phase-f resilience summary report: {out}")
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
