from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_audit_review_resolution_manifest_writes_resolution_artifacts(tmp_path: Path) -> None:
    queue_manifest = tmp_path / "audit_review_queue.json"
    followup_manifest = tmp_path / "audit_review_followup_manifest.json"
    out = tmp_path / "audit_review_resolution_manifest.json"
    out_dir = tmp_path / "audit_review_resolution_files"
    _write(
        queue_manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_items": [
                {
                    "packet_id": "connection|audit|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "queue_status": "approved",
                    "review_owner": "kim.licensed",
                    "resolution": "approved",
                    "path": str(tmp_path / "01.review_status.json"),
                    "packet_file_path": str(tmp_path / "01.audit_packet.json"),
                    "change_count": 6,
                    "row_count": 6,
                },
                {
                    "packet_id": "detail|audit|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "queue_status": "rejected",
                    "review_owner": "lee.designer",
                    "resolution": "needs detailing revision",
                    "path": str(tmp_path / "02.review_status.json"),
                    "packet_file_path": str(tmp_path / "02.audit_packet.json"),
                    "change_count": 5,
                    "row_count": 5,
                },
            ],
        },
    )
    _write(
        followup_manifest,
        {
            "schema_version": "1.0",
            "audit_review_followup_rows": [
                {
                    "packet_id": "connection|audit|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "queue_status": "approved",
                    "followup_action": "close_packet",
                    "followup_owner": "none",
                    "review_owner": "kim.licensed",
                    "status_file_path": str(tmp_path / "01.review_status.json"),
                    "packet_file_path": str(tmp_path / "01.audit_packet.json"),
                    "change_count": 6,
                    "row_count": 6,
                },
                {
                    "packet_id": "detail|audit|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "queue_status": "rejected",
                    "followup_action": "reopen_revision_cycle",
                    "followup_owner": "design_engineer",
                    "review_owner": "lee.designer",
                    "status_file_path": str(tmp_path / "02.review_status.json"),
                    "packet_file_path": str(tmp_path / "02.audit_packet.json"),
                    "change_count": 5,
                    "row_count": 5,
                },
            ],
            "summary": {},
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_resolution_manifest.py",
            "--queue-manifest",
            str(queue_manifest),
            "--followup-manifest",
            str(followup_manifest),
            "--out",
            str(out),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["audit_review_resolution_item_count"] == 2
    assert summary["audit_review_resolution_file_count"] == 2
    assert summary["audit_review_resolution_action_counts"] == {
        "close_packet": 1,
        "reopen_revision_cycle": 1,
    }
    assert summary["audit_review_resolution_status_counts"] == {
        "closed_packet": 1,
        "revision_package_open": 1,
    }
    rows = payload["audit_review_resolution_rows"]
    assert rows[0]["resolution_status"] == "closed_packet"
    assert rows[1]["resolution_owner"] == "lee.designer"
    files = sorted(out_dir.glob("*.resolution.json"))
    assert len(files) == 2
