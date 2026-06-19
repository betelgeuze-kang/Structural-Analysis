"""Tests for RH signed-closure packet template."""

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
                "closure_evidence_required": "signed_engineer_review_packet",
                "supplementary_evidence_path": "",
                "supplementary_metric_note": "",
            },
            "RH-002": {
                "status": "open",
                "closure_evidence_required": "legacy_tool_cross_validation_report",
                "supplementary_evidence_path": "",
                "supplementary_metric_note": "",
            },
            "RH-003": {
                "status": "open",
                "closure_evidence_required": "authority_signoff_receipt_or_formal_hold",
                "supplementary_evidence_path": "",
                "supplementary_metric_note": "",
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_rh_signed_closure_template_lists_open_packets(tmp_path: Path) -> None:
    out = tmp_path / "rh_signed_closure_packet_template.json"
    rh_json = _open_rh_updates(tmp_path / "residual_holdout_closure_updates.json")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_signed_closure_packet_template.py"),
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
    assert payload["status"] == "template_only"
    assert payload["open_count"] == 3
    assert "RH-001" in payload["packets"]
    assert payload["packets"]["RH-001"]["template_fields"]["reviewer_name"] == ""
