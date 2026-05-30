#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_condensed_solve_wires_native_status() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/mgt_global_fea_condensed_solve_test.json"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_condensed_solve.py"),
            "--roundtrip-json",
            str(roundtrip),
            "--output-json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["native_solve_status"] == "condensed_global_fea_wired"
