#!/usr/bin/env python3
"""Run Phase-C tunnel dynamics modules (C1~C5)."""

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
    "PASS": "all phase-c tunnel modules passed",
    "ERR_MODULE_FAIL": "one or more phase-c modules failed",
}

PHASEC_RUNNER_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out", "c1_out", "c2_out", "c3_out", "c4_out", "c5_out", "graph_out", "load_csv"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
        "c1_out": {"type": "string", "minLength": 1},
        "c2_out": {"type": "string", "minLength": 1},
        "c3_out": {"type": "string", "minLength": 1},
        "c4_out": {"type": "string", "minLength": 1},
        "c5_out": {"type": "string", "minLength": 1},
        "graph_out": {"type": "string", "minLength": 1},
        "load_csv": {"type": "string", "minLength": 1},
    },
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
    logger = get_logger("phase1.run_phasec_tunnel_modules")
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/phasec_tunnel_summary_report.json")
    p.add_argument("--c1-out", default="implementation/phase1/tunnel_graph_converter_report.json")
    p.add_argument("--c2-out", default="implementation/phase1/tunnel_segment_joint_report.json")
    p.add_argument("--c3-out", default="implementation/phase1/soil_tunnel_ssi_report.json")
    p.add_argument("--c4-out", default="implementation/phase1/train_passage_load_report.json")
    p.add_argument("--c5-out", default="implementation/phase1/tunnel_seismic_longitudinal_report.json")
    p.add_argument("--graph-out", default="implementation/phase1/tunnel_graph.json")
    p.add_argument("--load-csv", default="implementation/phase1/open_data/tunnel/train_passage_load.csv")
    args = p.parse_args()

    input_payload = {
        "out": str(args.out),
        "c1_out": str(args.c1_out),
        "c2_out": str(args.c2_out),
        "c3_out": str(args.c3_out),
        "c4_out": str(args.c4_out),
        "c5_out": str(args.c5_out),
        "graph_out": str(args.graph_out),
        "load_csv": str(args.load_csv),
    }
    try:
        validate_input_contract(
            input_payload,
            PHASEC_RUNNER_INPUT_SCHEMA,
            label="phase-c.run_phasec_tunnel_modules",
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "phasec.invalid_input", error=str(exc))
        raise SystemExit(1)

    log_event(logger, logging.INFO, "phasec.start", inputs=input_payload)
    steps: list[dict] = []

    ok_c1 = _run(
        "C1_tunnel_graph_converter",
        [
            sys.executable,
            "implementation/phase1/tunnel_graph_converter.py",
            "--out-graph",
            str(args.graph_out),
            "--out",
            str(args.c1_out),
        ],
        steps,
    )

    ok_c2 = _run(
        "C2_tunnel_segment_joint_nonlinear",
        [
            sys.executable,
            "implementation/phase1/tunnel_segment_joint_nonlinear.py",
            "--out",
            str(args.c2_out),
        ],
        steps,
    )

    ok_c3 = _run(
        "C3_soil_tunnel_ssi",
        [
            sys.executable,
            "implementation/phase1/soil_tunnel_ssi.py",
            "--out",
            str(args.c3_out),
        ],
        steps,
    )

    ok_c4 = _run(
        "C4_train_passage_load_generator",
        [
            sys.executable,
            "implementation/phase1/train_passage_load_generator.py",
            "--out-csv",
            str(args.load_csv),
            "--out",
            str(args.c4_out),
        ],
        steps,
    )

    ok_c5 = _run(
        "C5_tunnel_seismic_longitudinal",
        [
            sys.executable,
            "implementation/phase1/tunnel_seismic_longitudinal.py",
            "--out",
            str(args.c5_out),
        ],
        steps,
    )

    r1 = _load_json(str(args.c1_out))
    r2 = _load_json(str(args.c2_out))
    r3 = _load_json(str(args.c3_out))
    r4 = _load_json(str(args.c4_out))
    r5 = _load_json(str(args.c5_out))

    checks = {
        "C1_tunnel_graph_converter": bool(ok_c1 and r1.get("contract_pass", False)),
        "C2_tunnel_segment_joint_nonlinear": bool(ok_c2 and r2.get("contract_pass", False)),
        "C3_soil_tunnel_ssi": bool(ok_c3 and r3.get("contract_pass", False)),
        "C4_train_passage_load_generator": bool(ok_c4 and r4.get("contract_pass", False)),
        "C5_tunnel_seismic_longitudinal": bool(ok_c5 and r5.get("contract_pass", False)),
    }

    all_pass = all(checks.values())
    reason_code = "PASS" if all_pass else "ERR_MODULE_FAIL"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-phasec-tunnel-modules",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "reports": {
            "C1": str(args.c1_out),
            "C2": str(args.c2_out),
            "C3": str(args.c3_out),
            "C4": str(args.c4_out),
            "C5": str(args.c5_out),
            "graph_json": str(args.graph_out),
            "load_csv": str(args.load_csv),
        },
        "steps": steps,
        "contract_pass": bool(all_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote phase-c tunnel summary report: {out}")
    log_event(
        logger,
        logging.INFO,
        "phasec.completed",
        contract_pass=bool(all_pass),
        reason_code=reason_code,
    )
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
