from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_audit_review_decision_batch_examples_writes_safe_examples(tmp_path: Path) -> None:
    template = tmp_path / "audit_review_decision_batch_template.json"
    out_dir = tmp_path / "kickoff"
    _write(
        template,
        {
            "schema_version": "1.0",
            "summary": {"decision_item_count": 2},
            "updates": [
                {
                    "packet_id": "connection|high",
                    "status_file": "/tmp/01.review_status.json",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                    "current_status": "pending_review",
                    "allowed_statuses": ["acknowledged", "approved", "rejected"],
                },
                {
                    "packet_id": "detail|medium",
                    "status_file": "/tmp/02.review_status.json",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "current_status": "pending_review",
                    "allowed_statuses": ["acknowledged", "approved", "rejected"],
                },
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_decision_batch_examples.py",
            "--template-json",
            str(template),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    approve_all = json.loads(
        (out_dir / "audit_review_decision_batch_approve_all.attested_example.json").read_text(encoding="utf-8")
    )
    mixed = json.loads(
        (out_dir / "audit_review_decision_batch_mixed.attested_example.json").read_text(encoding="utf-8")
    )

    assert approve_all["contract_pass"] is True
    assert approve_all["example_only"] is True
    assert approve_all["summary"]["expected_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert approve_all["summary"]["expected_ready_full"] is True
    assert approve_all["attestation"]["apply_live_acknowledged"] is False
    assert [row["set_status"] for row in approve_all["updates"]] == ["approved", "approved"]
    assert (out_dir / "audit_review_decision_batch_approve_all.attested_example.md").exists()

    assert mixed["contract_pass"] is True
    assert mixed["example_only"] is True
    assert mixed["summary"]["expected_preview_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert mixed["summary"]["expected_open_revision_count"] == 1
    assert mixed["attestation"]["apply_live_acknowledged"] is False
    assert [row["set_status"] for row in mixed["updates"]] == ["approved", "rejected"]
    assert (out_dir / "audit_review_decision_batch_mixed.attested_example.md").exists()
