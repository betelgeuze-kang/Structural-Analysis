"""Smoke test for delivery evidence bundle orchestration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_delivery_evidence_bundle_writes_summary() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_delivery_evidence_bundle.py"),
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    bundle = json.loads(out.read_text(encoding="utf-8"))
    assert bundle["schema_version"] == "delivery-evidence-bundle.v1"
    assert bundle["summary"]["cross_validation_status"] in {
        "pass",
        "partial",
        "fail",
        "pass_with_marginal_metrics",
    }
    assert "holdout_evidence_hints" in bundle
