"""Tests for RH engineer review HTML export."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_rh_engineer_review_html() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/rh_engineer_review_packet_test.html"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/build_rh_engineer_review_packet_html.py"), "--output-html", str(out)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "RH-001" in html
    assert "Sign-off fields" in html
