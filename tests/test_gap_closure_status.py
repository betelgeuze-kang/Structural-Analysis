"""Tests for gap closure status rollup."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_report_gap_closure_status() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/gap_closure_status.json"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/report_gap_closure_status.py"), "--output-json", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "gap-closure-status.v1"
    assert "drawing_comparison_p1_p3" in payload["sections"]
    assert payload["sections"]["drawing_comparison_p1_p3"]["status"] == "complete"
    assert payload["delivery_status"] in {"ready", "review_required", "missing"}
    assert payload["authority_holdout_status"] in {"open", "closed"}
