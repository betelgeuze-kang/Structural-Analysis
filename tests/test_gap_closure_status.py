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
    assert payload["sections"]["ai_freeze_boundary"]["status"] == "ready"
    assert payload["sections"]["ai_freeze_boundary"]["contract_pass"] is True
    assert payload["sections"]["ai_freeze_boundary"]["autonomous_ai_engine_claim"] is False
    assert payload["sections"]["ai_freeze_boundary"]["surrogate_truth_claim_frozen"] is True
    assert payload["sections"]["ai_freeze_boundary"]["ai_training_frozen"] is True
    assert payload["sections"]["ai_freeze_boundary"]["shadow_solver_gated_only"] is True
    assert payload["sections"]["ai_freeze_boundary"]["production_pareto_policy_claim"] is False
    assert "does not prove autonomous structural-design AI" in payload["sections"]["ai_freeze_boundary"][
        "claim_boundary"
    ]
    assert payload["artifacts"]["ai_freeze_boundary_status"].endswith("ai_freeze_boundary_status.json")
    audit = payload["sections"]["gap_ledger_evidence_audit"]
    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["row_count"] == 20
    assert audit["closed_row_count"] == 17
    assert audit["nonclosed_row_count"] == 3
    assert audit["closed_evidence_coverage"]["closed_rows_with_evidence_count"] == 17
    assert audit["closed_evidence_coverage"]["closed_missing_claim_boundary_ids"] == []
    assert audit["nonclosed_visibility"]["nonclosed_rows_with_claim_boundary_count"] == 3
    assert "does not create authoritative evidence" in audit["claim_boundary"]
    assert payload["artifacts"]["gap_ledger_evidence_audit"].endswith("gap_ledger_evidence_audit.json")
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
