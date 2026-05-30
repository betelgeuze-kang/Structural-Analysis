"""Tests for productization delivery evidence validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_validate_productization_passes_current_dir() -> None:
    out = (
        REPO_ROOT
        / "implementation/phase1/release_evidence/productization/productization_delivery_evidence_validation_test.json"
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_productization_delivery_evidence.py"),
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
    assert payload["status"] == "pass"
    assert not payload["files_missing"]
