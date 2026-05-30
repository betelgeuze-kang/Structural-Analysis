"""Tests for RH signed-closure packet template."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rh_signed_closure_template_lists_open_packets() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/rh_signed_closure_packet_template_test.json"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/build_rh_signed_closure_packet_template.py"), "--output-json", str(out)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "template_only"
    assert payload["open_count"] == 3
    assert "RH-001" in payload["packets"]
    assert payload["packets"]["RH-001"]["template_fields"]["reviewer_name"] == ""
