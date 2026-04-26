from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_audit_review_owner_assignment_manifest_preserves_existing_assignment(tmp_path: Path) -> None:
    queue_manifest = tmp_path / "audit_review_queue.json"
    out = tmp_path / "audit_review_owner_assignments.json"
    _write(
        queue_manifest,
        {
            "audit_review_queue_items": [
                {
                    "packet_id": "connection|audit|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                },
                {
                    "packet_id": "detail|audit|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                },
            ]
        },
    )
    _write(
        out,
        {
            "assignment_rows": [
                {
                    "packet_id": "connection|audit|high",
                    "assignee_name": "Kim Structural",
                    "assignee_license_id": "SE-KR-001",
                    "assignment_status": "assigned",
                    "note": "Keep existing assignee",
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_owner_assignment_manifest.py",
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
    assert payload["summary"]["audit_review_assignment_item_count"] == 2
    assert payload["summary"]["audit_review_assignment_status_label"] == "assigned=1, unassigned=1"
    assert payload["summary"]["audit_review_assignment_assignee_label"] == "Kim Structural=1, unassigned=1"
    rows = {row["packet_id"]: row for row in payload["assignment_rows"]}
    assert rows["connection|audit|high"]["assignee_name"] == "Kim Structural"
    assert rows["connection|audit|high"]["assignment_status"] == "assigned"
    assert rows["detail|audit|medium"]["assignee_name"] == ""
    assert rows["detail|audit|medium"]["assignment_status"] == "unassigned"
