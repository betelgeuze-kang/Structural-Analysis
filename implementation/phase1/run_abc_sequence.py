#!/usr/bin/env python3
"""Run A->B->C sequence for derivative-free physical path branching roadmap.

A: derivative-free physics-guided branching
B: bifurcation detector trigger contract
C: rust/hip/onnx native contract
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUT = Path("implementation/phase1")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    a_path = out_dir / "physics_branching_report.json"
    b_path = out_dir / "bifurcation_detector_report.json"
    c_path = out_dir / "rust_onnx_native_contract_report.json"

    _run([sys.executable, "implementation/phase1/physics_guided_branching.py", "--mode", "train", "--out", str(a_path)])
    _run([sys.executable, "implementation/phase1/bifurcation_detector_stub.py", "--out", str(b_path)])
    _run([sys.executable, "implementation/phase1/rust_onnx_native_contract_stub.py", "--out", str(c_path)])

    a = _load(a_path)
    b = _load(b_path)
    c = _load(c_path)

    report = {
        "schema_version": "1.0",
        "run_id": "abc-sequence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_a_branching_pass": bool(a.get("contract_pass", False) and not a.get("uses_backprop", True)),
        "phase_b_bifurcation_pass": bool(b.get("contract_pass", False)),
        "phase_c_rust_onnx_pass": bool(c.get("contract_pass", False)),
        "all_pass": bool(a.get("contract_pass", False) and not a.get("uses_backprop", True) and b.get("contract_pass", False) and c.get("contract_pass", False)),
        "artifacts": {
            "a": str(a_path),
            "b": str(b_path),
            "c": str(c_path),
        },
    }

    out = out_dir / "abc_sequence_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote ABC sequence report: {out}")

    if not report["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
