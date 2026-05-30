"""Tests for RH supplementary evidence sync."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_sync_holdout_attaches_supplementary_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    rh = tmp_path / "rh.json"
    bundle.write_text(
        json.dumps(
            {
                "holdout_evidence_hints": {
                    "RH-001": {"supplementary_artifact": "/tmp/reanalysis.json", "note": "test"},
                },
                "summary": {
                    "reanalysis_status": "pass_with_story_proxy_check",
                    "mgt_integrity_status": "verified",
                    "cross_validation_status": "pass_with_marginal_metrics",
                    "cross_validation_marginal_accepted": 1,
                    "story_reanalysis_status": "pass",
                    "mgt_pipeline_status": "story_proxy_pass",
                },
            }
        ),
        encoding="utf-8",
    )
    rh.write_text(
        json.dumps(
            {
                "schema_version": "residual-holdout-closure-updates.v1",
                "updates": {
                    "RH-001": {"status": "open", "closure_evidence_status": "pending"},
                    "RH-002": {"status": "open"},
                },
            }
        ),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/sync_holdout_supplementary_evidence.py"),
        "--bundle-json",
        str(bundle),
        "--residual-holdout-json",
        str(rh),
        "--output-json",
        str(rh),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(rh.read_text(encoding="utf-8"))
    row = payload["updates"]["RH-001"]
    assert row["supplementary_evidence_path"] == "/tmp/reanalysis.json"
    assert row["status"] == "open"
    assert "mgt_integrity=verified" in row.get("supplementary_metric_note", "")
