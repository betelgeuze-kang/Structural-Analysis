"""Tests for GPU Newton certification honesty checklist."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gpu_newton_checklist_not_certified() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/gpu_newton_certification_checklist_test.json"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"), "--output-json", str(out)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "not_certified"
    assert payload["gpu_newton_terminal_proven"] is False
    assert payload["certification_blockers"] == ["gpu_newton_terminal_not_proven"]
    assert len(payload["required_evidence_before_terminal_claim"]) >= 3
