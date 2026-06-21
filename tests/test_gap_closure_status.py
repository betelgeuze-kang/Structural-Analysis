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
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert "does not create external receipts" in payload["claim_boundary"]
    assert "drawing_comparison_p1_p3" in payload["sections"]
    assert payload["sections"]["drawing_comparison_p1_p3"]["status"] == "complete"
    assert payload["delivery_status"] in {"ready", "review_required", "missing"}
    assert payload["authority_holdout_status"] in {"open", "closed"}
    assert payload["full_gap_ledger_status"] == "open"
    assert payload["full_gap_ledger_ready"] is False
    assert payload["full_gap_ledger_summary"]["total_count"] == len(payload["ledger_requirements"])
    assert payload["full_gap_ledger_summary"]["total_count"] >= 20
    assert payload["full_gap_ledger_summary"]["nonclosed_claim_boundary_missing_count"] == 0
    nonclosed_rows = [row for row in payload["ledger_requirements"] if not row["closed"]]
    assert nonclosed_rows
    assert all(str(row["claim_boundary"]).strip() for row in nonclosed_rows)
    g1 = next(row for row in payload["ledger_requirements"] if row["id"] == "G1")
    assert "G1 remains partial" in g1["claim_boundary"]
    assert "does not close full-mesh full-load 3D nonlinear equilibrium" in g1["claim_boundary"]


def test_report_gap_closure_status_uses_explicit_productization_dir(tmp_path: Path) -> None:
    productization = tmp_path / "productization"
    productization.mkdir()
    (productization / "delivery_evidence_bundle.json").write_text(
        json.dumps(
            {
                "schema_version": "delivery-evidence-bundle.v1",
                "status": "ready",
                "blockers": [],
                "summary": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (productization / "residual_holdout_closure_updates.json").write_text(
        json.dumps({"updates": {}}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "gap_closure_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_gap_closure_status.py"),
            "--productization-dir",
            str(productization),
            "--output-json",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["delivery_status"] == "ready"
    assert payload["artifacts"]["delivery_evidence_bundle"] == str(
        productization / "delivery_evidence_bundle.json"
    )
    assert payload["full_gap_ledger_summary"]["total_count"] == len(payload["ledger_requirements"])
