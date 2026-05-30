"""Tests for RH closure checklist builder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_rh_closure_checklist_lists_open_rows() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/rh_closure_checklist_test.json"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/build_rh_closure_checklist.py"), "--output-json", str(out)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "pending_authority"
    assert payload["open_count"] == 3
    assert len(payload["rows"]) == 3
    assert all("signed" in " ".join(row["checklist"]).lower() for row in payload["rows"])
