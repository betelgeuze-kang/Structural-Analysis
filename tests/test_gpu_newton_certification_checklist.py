"""Tests for GPU Newton certification honesty checklist."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gpu_newton_checklist_without_terminal_artifact() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/gpu_newton_certification_checklist_test.json"
    missing_cert = REPO_ROOT / "implementation/phase1/release_evidence/productization/gpu_newton_terminal_certification_test_missing.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"),
            "--output-json",
            str(out),
            "--terminal-certification-json",
            str(missing_cert),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "not_certified"
    assert payload["gpu_newton_terminal_proven"] is False
    assert "gpu_newton_terminal_not_proven" in (payload.get("certification_blockers") or [])
    assert len(payload["required_evidence_before_terminal_claim"]) >= 3


def test_gpu_newton_checklist_with_terminal_artifact_when_present() -> None:
    cert = REPO_ROOT / "implementation/phase1/release_evidence/productization/gpu_newton_terminal_certification.json"
    if not cert.is_file():
        return
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/gpu_newton_certification_checklist_from_cert_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"),
            "--output-json",
            str(out),
            "--terminal-certification-json",
            str(cert),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    cert_payload = json.loads(cert.read_text(encoding="utf-8"))
    if cert_payload.get("gpu_newton_terminal_proven"):
        assert payload["status"] == "certified"
        assert payload["gpu_newton_terminal_proven"] is True
    else:
        assert payload["status"] == "not_certified"
