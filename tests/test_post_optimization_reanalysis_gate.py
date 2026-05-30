"""Tests for post-optimization reanalysis gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
CHANGES = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json"
)


def test_reanalysis_gate_records_roundtrip_and_changes() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/reanalysis_gate_test.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_post_optimization_reanalysis_gate.py"),
        "--optimized-roundtrip-json",
        str(ROUNDTRIP),
        "--changes-json",
        str(CHANGES),
        "--output-json",
        str(out),
        "--require-changes",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema_version"] == "post-optimization-reanalysis-gate.v2"
    assert report["roundtrip_summary"]["element_count"] == 12728
    assert report["change_summary"]["change_count"] > 0
    assert "proxy_solver_divergence" in report
    assert report["mgt_integrity"]["integrity_status"] in {
        "verified",
        "verified_without_expected_sha",
        "sha_mismatch",
    }


def test_reanalysis_gate_sync_mgt_provenance() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/reanalysis_gate_sync_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_post_optimization_reanalysis_gate.py"),
            "--optimized-roundtrip-json",
            str(ROUNDTRIP),
            "--changes-json",
            str(CHANGES),
            "--output-json",
            str(out),
            "--sync-mgt-provenance",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["mgt_sync"]["status"] == "synced"
    assert report["mgt_integrity"]["integrity_status"] == "verified"
