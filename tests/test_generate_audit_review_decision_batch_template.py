from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_audit_review_decision_batch_template_filters_open_packets(tmp_path: Path) -> None:
    queue_manifest = tmp_path / "audit_review_queue.json"
    out = tmp_path / "audit_review_decision_batch_template.json"
    _write(
        queue_manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_items": [
                {
                    "packet_id": "connection|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "path": "/tmp/01.review_status.json",
                },
                {
                    "packet_id": "detail|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "queue_status": "acknowledged",
                    "path": "/tmp/02.review_status.json",
                },
                {
                    "packet_id": "closed|approved",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "queue_status": "approved",
                    "path": "/tmp/03.review_status.json",
                },
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_decision_batch_template.py",
            "--queue-manifest",
            str(queue_manifest),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["decision_item_count"] == 2
    assert payload["attestation"]["reviewer_name"] == ""
    assert payload["attestation"]["apply_live_acknowledged"] is False
    assert [row["packet_id"] for row in payload["updates"]] == ["connection|high", "detail|medium"]
    assert payload["updates"][0]["allowed_statuses"] == ["acknowledged", "approved", "rejected"]
    assert payload["updates"][1]["allowed_statuses"] == ["approved", "rejected"]
    assert out.with_suffix(".md").exists()
