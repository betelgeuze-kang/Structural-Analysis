from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_audit_review_followup_manifest_maps_statuses(tmp_path: Path) -> None:
    queue_manifest = tmp_path / "audit_review_queue.json"
    out = tmp_path / "audit_review_followup_manifest.json"
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
                    "queue_status": "pending_review",
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
                    "queue_status": "approved",
                    "path": str(tmp_path / "02.review_status.json"),
                    "packet_file_path": str(tmp_path / "02.audit_packet.json"),
                    "change_count": 5,
                    "row_count": 5,
                },
                {
                    "packet_id": "rebar|audit|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "queue_status": "rejected",
                    "path": str(tmp_path / "03.review_status.json"),
                    "packet_file_path": str(tmp_path / "03.audit_packet.json"),
                    "change_count": 2,
                    "row_count": 2,
                },
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_followup_manifest.py",
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
    rows = payload["audit_review_followup_rows"]
    assert rows[0]["followup_action"] == "wait_for_review"
    assert rows[0]["followup_owner"] == "licensed_engineer"
    assert rows[1]["followup_action"] == "close_packet"
    assert rows[1]["followup_owner"] == "none"
    assert rows[2]["followup_action"] == "reopen_revision_cycle"
    assert rows[2]["followup_owner"] == "design_engineer"
    summary = payload["summary"]
    assert summary["audit_review_followup_item_count"] == 3
    assert summary["audit_review_followup_open_item_count"] == 2
    assert summary["audit_review_followup_closed_item_count"] == 1
    assert summary["audit_review_followup_action_counts"] == {
        "close_packet": 1,
        "reopen_revision_cycle": 1,
        "wait_for_review": 1,
    }


def test_generate_audit_review_followup_manifest_adds_sla_ageing_and_review_owner(tmp_path: Path) -> None:
    queue_manifest = tmp_path / "audit_review_queue.json"
    out = tmp_path / "audit_review_followup_manifest.json"
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
                    "review_owner": "kim.licensed",
                    "queue_status": "pending_review",
                    "last_transition_at_utc": "2026-03-18T00:00:00+00:00",
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
                    "review_owner": "lee.designer",
                    "queue_status": "rejected",
                    "last_transition_at_utc": "2026-03-20T00:00:00+00:00",
                    "path": str(tmp_path / "02.review_status.json"),
                    "packet_file_path": str(tmp_path / "02.audit_packet.json"),
                    "change_count": 5,
                    "row_count": 5,
                },
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_followup_manifest.py",
            "--queue-manifest",
            str(queue_manifest),
            "--out",
            str(out),
            "--reference-time-utc",
            "2026-03-21T12:00:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    rows = payload["audit_review_followup_rows"]
    assert rows[0]["review_owner"] == "kim.licensed"
    assert rows[0]["sla_state"] == "overdue"
    assert rows[0]["age_bucket"] == "72_to_168h"
    assert rows[0]["overdue"] is True
    assert rows[1]["followup_action"] == "reopen_revision_cycle"
    assert rows[1]["review_owner"] == "lee.designer"
    assert rows[1]["sla_state"] == "within_sla"
    summary = payload["summary"]
    assert summary["audit_review_followup_review_owner_label"] == "kim.licensed=1, lee.designer=1"
    assert summary["audit_review_followup_sla_state_label"] == "overdue=1, within_sla=1"
    assert summary["audit_review_followup_age_bucket_label"] == "24_to_72h=1, 72_to_168h=1"
    assert summary["audit_review_followup_overdue_item_count"] == 1
    assert summary["audit_review_followup_oldest_open_packet_id"] == "connection|audit|high"


def test_generate_audit_review_followup_manifest_applies_assignment_manifest(tmp_path: Path) -> None:
    queue_manifest = tmp_path / "audit_review_queue.json"
    assignment_manifest = tmp_path / "audit_review_owner_assignments.json"
    out = tmp_path / "audit_review_followup_manifest.json"
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
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "last_transition_at_utc": "2026-03-21T00:00:00+00:00",
                    "path": str(tmp_path / "01.review_status.json"),
                    "packet_file_path": str(tmp_path / "01.audit_packet.json"),
                    "change_count": 6,
                    "row_count": 6,
                }
            ],
        },
    )
    _write(
        assignment_manifest,
        {
            "assignment_rows": [
                {
                    "packet_id": "connection|audit|high",
                    "assignee_name": "Kim Structural",
                    "assignee_license_id": "SE-KR-001",
                    "assignment_status": "assigned",
                    "assignment_updated_at_utc": "2026-03-21T01:00:00+00:00",
                    "note": "Primary reviewer",
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_followup_manifest.py",
            "--queue-manifest",
            str(queue_manifest),
            "--assignment-manifest",
            str(assignment_manifest),
            "--out",
            str(out),
            "--reference-time-utc",
            "2026-03-21T12:00:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    row = payload["audit_review_followup_rows"][0]
    assert row["assigned_reviewer_name"] == "Kim Structural"
    assert row["assigned_reviewer_license_id"] == "SE-KR-001"
    assert row["assignment_status"] == "assigned"
    assert payload["summary"]["audit_review_followup_assignee_label"] == "Kim Structural=1"
    assert payload["summary"]["audit_review_followup_assignment_status_label"] == "assigned=1"
