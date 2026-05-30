"""Tests for MGT global FEA mesh contract gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mesh_contract_passes_optimized_roundtrip() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/mgt_global_fea_mesh_contract_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_mesh_contract_gate.py"),
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
    assert payload["mesh_contract_ready"] is True
