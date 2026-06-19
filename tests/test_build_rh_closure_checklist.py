"""Tests for RH closure checklist builder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _open_rh_updates(path: Path) -> Path:
    payload = {
        "schema_version": "residual-holdout-closure-updates.v1",
        "updates": {
            "RH-001": {
                "status": "open",
                "owner": "licensed_engineer",
                "closure_evidence_required": "signed_engineer_review_packet",
                "closure_evidence_status": "pending",
            },
            "RH-002": {
                "status": "open",
                "owner": "legacy_tool_owner",
                "closure_evidence_required": "legacy_tool_cross_validation_report",
                "closure_evidence_status": "pending",
            },
            "RH-003": {
                "status": "open",
                "owner": "authority_workflow_owner",
                "closure_evidence_required": "authority_signoff_receipt_or_formal_hold",
                "closure_evidence_status": "pending",
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_build_rh_closure_checklist_lists_open_rows(tmp_path: Path) -> None:
    out = tmp_path / "rh_closure_checklist.json"
    rh_json = _open_rh_updates(tmp_path / "residual_holdout_closure_updates.json")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_closure_checklist.py"),
            "--rh-json",
            str(rh_json),
            "--output-json",
            str(out),
        ],
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
