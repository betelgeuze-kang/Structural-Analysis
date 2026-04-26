"""CLI-level contract validation tests for phase1 modules."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
PHASE1_DIR = ROOT_DIR / "implementation" / "phase1"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
    )


def test_track_irregularity_rejects_invalid_dx(tmp_path: Path) -> None:
    report = tmp_path / "track_irregularity_invalid.json"
    proc = _run(
        [
            sys.executable,
            str(PHASE1_DIR / "track_irregularity_generator.py"),
            "--dx-m",
            "-0.01",
            "--out",
            str(report),
        ]
    )
    assert proc.returncode != 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_INVALID_INPUT"


def test_soil_tunnel_ssi_rejects_inverted_frequency_range(tmp_path: Path) -> None:
    report = tmp_path / "soil_ssi_invalid.json"
    proc = _run(
        [
            sys.executable,
            str(PHASE1_DIR / "soil_tunnel_ssi.py"),
            "--f-min-hz",
            "12.0",
            "--f-max-hz",
            "2.0",
            "--out",
            str(report),
        ]
    )
    assert proc.returncode != 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_INVALID_INPUT"
