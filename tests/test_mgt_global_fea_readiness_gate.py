"""Tests for MGT global FEA readiness preflight gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_global_fea_readiness_passes_optimized_roundtrip() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/mgt_global_fea_readiness_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_readiness_gate.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["readiness_for_global_fea_wiring"] is True
    assert payload["native_solve_status"] == "not_wired"
    assert payload["metrics"]["element_count"] >= 1000
