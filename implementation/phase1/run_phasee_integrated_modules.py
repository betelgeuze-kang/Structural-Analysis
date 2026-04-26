#!/usr/bin/env python3
"""Run Phase-E integrated modules (E1~E5)."""

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
    "PASS": "all phase-e integrated modules passed",
    "ERR_MODULE_FAIL": "one or more phase-e modules failed",
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
    p.add_argument("--out", default="implementation/phase1/phasee_integrated_summary_report.json")
    p.add_argument("--e1-out", default="implementation/phase1/substructuring_interface_report.json")
    p.add_argument("--e2-out", default="implementation/phase1/vibration_attenuation_report.json")
    p.add_argument("--e3-out", default="implementation/phase1/vibration_compliance_report.json")
    p.add_argument("--e5-out-json", default="implementation/phase1/whitebox_validation_report.json")
    p.add_argument("--e5-out-md", default="implementation/phase1/whitebox_validation_report.md")
    p.add_argument("--whitebox-accept-rel-err", type=float, default=0.05)
    p.add_argument("--whitebox-accept-abs-residual", type=float, default=0.01)
    args = p.parse_args()

    steps: list[dict] = []

    ok_e1 = _run(
        "E1_substructuring_interface",
        [
            sys.executable,
            "implementation/phase1/substructuring_interface.py",
            "--out",
            str(args.e1_out),
        ],
        steps,
    )
    ok_e2 = _run(
        "E2_vibration_attenuation_model",
        [
            sys.executable,
            "implementation/phase1/vibration_attenuation_model.py",
            "--substructuring",
            str(args.e1_out),
            "--out",
            str(args.e2_out),
        ],
        steps,
    )
    ok_e3 = _run(
        "E3_vibration_compliance_checker",
        [
            sys.executable,
            "implementation/phase1/vibration_compliance_checker.py",
            "--attenuation",
            str(args.e2_out),
            "--out",
            str(args.e3_out),
        ],
        steps,
    )
    ok_e5 = _run(
        "E5_whitebox_validation_extension",
        [
            sys.executable,
            "implementation/phase1/whitebox_validation_report.py",
            "--out-json",
            str(args.e5_out_json),
            "--out-md",
            str(args.e5_out_md),
            "--acceptance-rel-err",
            str(args.whitebox_accept_rel_err),
            "--acceptance-abs-residual",
            str(args.whitebox_accept_abs_residual),
        ],
        steps,
    )

    r1 = _load_json(str(args.e1_out))
    r2 = _load_json(str(args.e2_out))
    r3 = _load_json(str(args.e3_out))
    r5 = _load_json(str(args.e5_out_json))

    checks = {
        "E1_substructuring_interface": bool(ok_e1 and r1.get("contract_pass", False)),
        "E2_vibration_attenuation_model": bool(ok_e2 and r2.get("contract_pass", False)),
        "E3_vibration_compliance_checker": bool(ok_e3 and r3.get("contract_pass", False)),
        "E5_whitebox_validation_extension": bool(ok_e5 and r5.get("contract_pass", r5.get("summary", {}).get("pass", False))),
    }

    all_pass = all(checks.values())
    reason_code = "PASS" if all_pass else "ERR_MODULE_FAIL"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-phasee-integrated-modules",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "reports": {
            "E1": str(args.e1_out),
            "E2": str(args.e2_out),
            "E3": str(args.e3_out),
            "E5_json": str(args.e5_out_json),
            "E5_md": str(args.e5_out_md),
        },
        "steps": steps,
        "contract_pass": bool(all_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote phase-e integrated summary report: {out}")
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
