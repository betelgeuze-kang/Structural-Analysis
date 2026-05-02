from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_support_reports(tmp_path: Path) -> dict[str, Path]:
    gap = tmp_path / "release_gap_report.json"
    commercial = tmp_path / "commercial_readiness_report.json"
    tpu = tmp_path / "tpu_hffb_benchmark_gate_report.json"
    peer = tmp_path / "peer_spd_hinge_benchmark_gate_report.json"
    fixture = tmp_path / "peer_spd_hinge_fixture_regression_report.json"
    alignment = tmp_path / "peer_spd_hinge_refresh_alignment_report.json"
    _write(
        gap,
        {
            "summary": {
                "panel_zone_3d_clash_ready": True,
                "panel_zone_validation_boundary": "external_validation_only",
                "pbd_dynamic_hinge_refresh_ready": True,
                "foundation_optimization_ready": True,
                "wind_tunnel_raw_mapping_ready": True,
                "mgt_export_evidence_model": "direct_patch_plus_audit_review_manifest",
                "mgt_export_instruction_sidecar_change_count": 0,
                "mgt_export_audit_review_queue_pending_count": 2,
                "mgt_export_audit_review_followup_overdue_item_count": 0,
                "mgt_export_audit_review_resolution_open_revision_count": 0,
            }
        },
    )
    _write(
        commercial,
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
        },
    )
    for path in (tpu, peer, fixture, alignment):
        _write(path, {"contract_pass": True})
    return {
        "gap": gap,
        "commercial": commercial,
        "tpu": tpu,
        "peer": peer,
        "fixture": fixture,
        "alignment": alignment,
    }


def test_generate_audit_review_decision_batch_previews_builds_preview_chain(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    queue_manifest = tmp_path / "audit_review_queue.json"
    template = tmp_path / "audit_review_decision_batch_template.json"
    out_dir = tmp_path / "kickoff"
    _write(
        queue_manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_status_directory": str(tmp_path / "queue_status"),
            "audit_review_queue_items": [
                {
                    "packet_id": "connection|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "acknowledged": False,
                    "resolution": "",
                    "path": "/tmp/01.review_status.json",
                    "change_count": 6,
                    "row_count": 6,
                },
                {
                    "packet_id": "detail|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "acknowledged": False,
                    "resolution": "",
                    "path": "/tmp/02.review_status.json",
                    "change_count": 5,
                    "row_count": 5,
                },
            ],
        },
    )
    _write(
        template,
        {
            "schema_version": "1.0",
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
            "implementation/phase1/generate_audit_review_decision_batch_previews.py",
            "--queue-manifest",
            str(queue_manifest),
            "--template-json",
            str(template),
            "--release-gap-report",
            str(reports["gap"]),
            "--commercial-readiness-report",
            str(reports["commercial"]),
            "--tpu-hffb-benchmark-report",
            str(reports["tpu"]),
            "--peer-spd-hinge-benchmark-report",
            str(reports["peer"]),
            "--peer-spd-hinge-fixture-regression-report",
            str(reports["fixture"]),
            "--peer-spd-hinge-alignment-report",
            str(reports["alignment"]),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
    )
    assert proc.returncode == 0, proc.stderr

    approve_preview = json.loads(
        (out_dir / "external_benchmark_submission_readiness_preview.approve_all.json").read_text(encoding="utf-8")
    )
    reject_preview = json.loads(
        (out_dir / "external_benchmark_submission_readiness_preview.reject_one.json").read_text(encoding="utf-8")
    )
    run_report = json.loads(
        (out_dir / "audit_review_decision_batch_run_report.json").read_text(encoding="utf-8")
    )
    preview_artifacts_report = json.loads(
        (out_dir / "audit_review_decision_batch_preview_artifacts_report.json").read_text(encoding="utf-8")
    )

    assert approve_preview["reason_code"] == "PASS_START_NOW_FULL"
    assert reject_preview["reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert run_report["reason_code"] == "PASS"
    assert run_report["apply_live"] is False
    assert run_report["live_applied"] is False
    assert preview_artifacts_report["contract_pass"] is True
    assert (out_dir / "audit_review_decision_batch_approve_all.preview.json").exists()
    assert (out_dir / "audit_review_decision_batch_reject_one.preview.json").exists()


def test_generate_audit_review_decision_batch_previews_accepts_zero_touch_no_open_items(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    queue_manifest = tmp_path / "audit_review_queue.json"
    template = tmp_path / "audit_review_decision_batch_template.json"
    out_dir = tmp_path / "kickoff"
    _write(
        queue_manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_status_directory": str(tmp_path / "queue_status"),
            "audit_review_queue_items": [],
        },
    )
    _write(
        template,
        {
            "schema_version": "1.0",
            "contract_pass": False,
            "reason_code": "ERR_NO_OPEN_DECISION_ITEMS",
            "reason": "no open review packets need reviewer decisions",
            "updates": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_audit_review_decision_batch_previews.py",
            "--queue-manifest",
            str(queue_manifest),
            "--template-json",
            str(template),
            "--release-gap-report",
            str(reports["gap"]),
            "--commercial-readiness-report",
            str(reports["commercial"]),
            "--tpu-hffb-benchmark-report",
            str(reports["tpu"]),
            "--peer-spd-hinge-benchmark-report",
            str(reports["peer"]),
            "--peer-spd-hinge-fixture-regression-report",
            str(reports["fixture"]),
            "--peer-spd-hinge-alignment-report",
            str(reports["alignment"]),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
    )
    assert proc.returncode == 0, proc.stderr

    approve_preview = json.loads(
        (out_dir / "external_benchmark_submission_readiness_preview.approve_all.json").read_text(encoding="utf-8")
    )
    run_report = json.loads(
        (out_dir / "audit_review_decision_batch_run_report.json").read_text(encoding="utf-8")
    )
    preview_artifacts_report = json.loads(
        (out_dir / "audit_review_decision_batch_preview_artifacts_report.json").read_text(encoding="utf-8")
    )

    assert approve_preview["reason_code"] == "PASS_NO_OPEN_DECISION_ITEMS"
    assert approve_preview["summary"]["zero_touch_native_authoring"] is True
    assert run_report["reason_code"] == "PASS_ZERO_TOUCH_NO_OPEN_DECISION_ITEMS"
    assert run_report["apply_live"] is False
    assert preview_artifacts_report["contract_pass"] is True
    assert preview_artifacts_report["reason_code"] == "PASS_NO_OPEN_DECISION_ITEMS"
    assert (out_dir / "audit_review_decision_batch.live_preview.md").exists()
