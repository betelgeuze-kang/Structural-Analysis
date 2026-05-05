from __future__ import annotations

import json
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
            "checks": {
                "real_source_pass": True,
                "gpu_strict_pass": True,
            },
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


def _write_queue_manifest(tmp_path: Path) -> Path:
    queue_manifest = tmp_path / "audit_review_queue.json"
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
    return queue_manifest


def test_preview_external_benchmark_submission_after_review_updates_predicts_full_submission(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    queue_manifest = _write_queue_manifest(tmp_path)
    batch = tmp_path / "updates.json"
    out = tmp_path / "preview.json"
    _write(
        batch,
        {
            "updates": [
                {"packet_id": "connection|high", "set_status": "approved"},
                {"packet_id": "detail|medium", "set_status": "approved"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/preview_external_benchmark_submission_after_review_updates.py",
            "--queue-manifest",
            str(queue_manifest),
            "--batch-updates-json",
            str(batch),
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
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "PASS_START_NOW_FULL"
    assert payload["summary"]["preview_queue_pending_count"] == 0
    assert payload["summary"]["preview_resolution_open_revision_count"] == 0
    assert payload["readiness_preview"]["summary"]["ready_to_start_full_submission_now"] is True
    markdown = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "External Benchmark Submission Readiness Preview" in markdown
    assert "predicted_reason_code" in markdown
    assert "PASS_START_NOW_FULL" in markdown
    assert "connection|high" in markdown
    assert "approved" in markdown


def test_preview_external_benchmark_submission_after_review_updates_blocks_open_revision(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    queue_manifest = _write_queue_manifest(tmp_path)
    batch = tmp_path / "updates.json"
    out = tmp_path / "preview.json"
    _write(
        batch,
        {
            "updates": [
                {"packet_id": "connection|high", "set_status": "approved"},
                {"packet_id": "detail|medium", "set_status": "rejected", "resolution": "needs revision"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/preview_external_benchmark_submission_after_review_updates.py",
            "--queue-manifest",
            str(queue_manifest),
            "--batch-updates-json",
            str(batch),
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
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert payload["summary"]["preview_queue_pending_count"] == 0
    assert payload["summary"]["preview_resolution_open_revision_count"] == 1
    assert "audit_review_resolution_has_open_revisions" in payload["readiness_preview"]["summary"]["blockers"]
    markdown = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "External Benchmark Submission Readiness Preview" in markdown
    assert "ERR_ARCHITECTURE_BLOCKERS" in markdown
    assert "detail|medium" in markdown
    assert "rejected" in markdown
