from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/materialize_p1_operational_queues.py")


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _commercial(path: Path) -> Path:
    checks = {
        "real_source_pass": True,
        "benchmark_breadth_pass": True,
        "measured_dynamic_targets_pass": True,
        "measured_source_family_pass": True,
        "measured_case_count_pass": True,
        "accuracy_pass": True,
        "noise_robustness_pass": True,
        "ood_safety_pass": True,
        "gpu_strict_pass": True,
    }
    return _write_json(
        path,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "checks": checks,
            "grade": {"label": "Commercial", "commercial_pass": True},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
            },
            "residual_holdout_categories": [
                {"id": "licensed_engineer_review_required", "owner": "licensed_engineer"},
                {"id": "legacy_tool_cross_validation_required", "owner": "legacy_tool_owner"},
                {"id": "legal_authority_signoff_required", "owner": "authority_workflow_owner"},
            ],
        },
    )


def _external_submission(path: Path, *, missing_lifecycle: bool = False, submitted_first: bool = False) -> Path:
    rows = []
    for index, queue_id in enumerate(
        ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"],
        start=1,
    ):
        row = {
            "work_item_id": f"EB-{index:03d}",
            "queue_id": queue_id,
            "submission_id": f"p1-{queue_id}",
            "submission_scope": "full_external_submission_package",
            "owner": f"{queue_id}_owner",
            "status": "ready_for_full_submission",
            "queue_status": "ready_for_full_submission",
            "submission_lifecycle_status": "ready_to_submit",
            "submission_status": "ready_to_submit",
            "submission_owner_action": "submit_external_benchmark_package_and_attach_receipt",
            "submission_receipt": "pending",
            "submission_receipt_status": "pending_external_submission_receipt",
            "receipt_status": "pending_external_submission_receipt",
            "receipt_url": "",
            "submitted_at_utc": "",
            "last_checked_at_utc": "",
            "onepage_attestation": f"{queue_id} one-page attestation",
            "onepage_attestation_status": "ready_for_full_submission",
            "dry_run_evidence": f"{queue_id}: PASS",
            "closure_evidence_required": f"{queue_id}_submission_receipt",
            "closure_evidence_path": "",
            "closure_evidence_status": "pending",
            "status_lifecycle": {
                "current_status": "ready_for_full_submission",
                "submission_lifecycle_status": "ready_to_submit",
                "submission_owner_action": "submit_external_benchmark_package_and_attach_receipt",
            },
        }
        if submitted_first and index == 1:
            row.update(
                {
                    "submission_lifecycle_status": "submitted_receipt_attached",
                    "submission_status": "submitted_receipt_attached",
                    "submission_owner_action": "submission_receipt_attached_verify_roundtrip",
                    "submission_receipt": "https://bench.example/receipts/EB-001",
                    "submission_receipt_status": "attached",
                    "receipt_status": "attached",
                    "receipt_url": "https://bench.example/receipts/EB-001",
                    "submitted_at_utc": "2026-05-05T01:02:03Z",
                    "last_checked_at_utc": "2026-05-05T02:03:04Z",
                    "closure_evidence_path": "release_evidence/productization/EB-001.receipt.json",
                    "closure_evidence_status": "attached",
                    "status_lifecycle": {
                        "current_status": "ready_for_full_submission",
                        "submission_lifecycle_status": "submitted_receipt_attached",
                        "submission_owner_action": "submission_receipt_attached_verify_roundtrip",
                    },
                }
            )
        if missing_lifecycle:
            row.pop("submission_id")
            row.pop("status_lifecycle")
        rows.append(row)
    return _write_json(
        path,
        {
            "schema_version": "1.0",
            "contract_pass": not missing_lifecycle,
            "reason_code": "PASS_START_NOW_FULL" if not missing_lifecycle else "ERR_ARCHITECTURE_BLOCKERS",
            "summary": {
                "submission_queue_count": 4,
                "submission_queue_ready_count": 4,
                "submission_queue_review_pending_count": 0,
                "submission_queue_blocked_count": 0,
                "onepage_attestation_status": "ready_for_full_submission",
            },
            "submission_queue": rows,
        },
    )


def test_materialize_p1_operational_queues_writes_backlog_and_packet_templates(tmp_path: Path) -> None:
    commercial = _commercial(tmp_path / "commercial.json")
    external = _external_submission(tmp_path / "external.json")
    p1_breadth = _write_json(
        tmp_path / "p1-breadth.json",
        {"p1_benchmark_execution_unblocked": True},
    )
    out = tmp_path / "ops" / "p1_operational_queues.json"
    out_md = tmp_path / "ops" / "p1_operational_queues.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--commercial-readiness",
            str(commercial),
            "--external-benchmark-submission-readiness",
            str(external),
            "--p1-benchmark-breadth-status",
            str(p1_breadth),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
            "--json",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert payload["summary"]["external_submission_queue_count"] == 4
    assert payload["summary"]["residual_holdout_work_item_count"] == 3
    assert payload["summary"]["residual_holdout_open_count"] == 3
    assert payload["summary"]["full_commercial_replacement_ready"] is False
    assert payload["queues"]["external_benchmark_submission_work_items"][0]["receipt_template_path"].endswith(
        "EB-001.receipt_template.json"
    )
    assert payload["queues"]["residual_holdout_work_items"][0]["closure_packet_template_path"].endswith(
        "RH-001.closure_packet_template.json"
    )
    assert (tmp_path / "ops" / "external_benchmark_submission_queue" / "external_benchmark_submission_work_items.json").exists()
    assert (tmp_path / "ops" / "external_benchmark_submission_queue" / "EB-001.receipt_template.json").exists()
    assert (tmp_path / "ops" / "residual_holdout_queue" / "residual_holdout_work_items.json").exists()
    assert (tmp_path / "ops" / "residual_holdout_queue" / "RH-001.closure_packet_template.json").exists()
    assert "P1 Operational Queues" in markdown
    assert "`full_commercial_replacement_ready`: `False`" in markdown
    assert "p1-hardest_external_10case" in markdown
    assert "licensed_engineer_review_required" in markdown
    assert "Receipt Template" in markdown
    assert "EB-001.receipt_template.json" in markdown
    assert "RH-001.closure_packet_template.json" in markdown
    assert "submit_external_benchmark_package_and_attach_receipt" in markdown
    assert "complete_engineer_review_and_attach_signed_packet" in markdown


def test_materialize_p1_operational_queues_fails_when_external_queue_is_not_operational(tmp_path: Path) -> None:
    out = tmp_path / "ops" / "p1_operational_queues.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--commercial-readiness",
            str(_commercial(tmp_path / "commercial.json")),
            "--external-benchmark-submission-readiness",
            str(_external_submission(tmp_path / "external.json", missing_lifecycle=True)),
            "--out",
            str(out),
            "--json",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["summary"]["external_submission_operational"] is False


def test_materialize_p1_operational_queues_preserves_submission_receipt_update_fields(tmp_path: Path) -> None:
    out = tmp_path / "ops" / "p1_operational_queues.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--commercial-readiness",
            str(_commercial(tmp_path / "commercial.json")),
            "--external-benchmark-submission-readiness",
            str(_external_submission(tmp_path / "external.json", submitted_first=True)),
            "--out",
            str(out),
            "--json",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    row = payload["queues"]["external_benchmark_submission_work_items"][0]
    assert row["receipt_url"] == "https://bench.example/receipts/EB-001"
    assert row["receipt_status"] == "attached"
    assert row["submitted_at_utc"] == "2026-05-05T01:02:03Z"
    assert row["last_checked_at_utc"] == "2026-05-05T02:03:04Z"
    assert row["closure_evidence_status"] == "attached"
    assert payload["summary"]["external_submission_receipt_attached_count"] == 1
    assert payload["summary"]["external_submission_last_checked_count"] == 1
    assert payload["summary"]["external_submission_closure_evidence_attached_count"] == 1
    receipt_template = json.loads(Path(row["receipt_template_path"]).read_text(encoding="utf-8"))
    assert receipt_template["last_checked_at_utc"] == "2026-05-05T02:03:04Z"


def test_materialize_p1_operational_queues_merges_residual_holdout_closure_sidecar(tmp_path: Path) -> None:
    out = tmp_path / "ops" / "p1_operational_queues.json"
    out_md = tmp_path / "ops" / "p1_operational_queues.md"
    updates = _write_json(
        tmp_path / "rh_updates.json",
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": {
                "RH-001": {
                    "status": "closed",
                    "queue_status": "closure_evidence_attached",
                    "closure_evidence_path": "release_evidence/productization/RH-001.closure.json",
                    "closure_evidence_status": "attached",
                    "last_checked_at_utc": "2026-05-05T04:05:06Z",
                    "closed_at_utc": "2026-05-05T04:06:07Z",
                },
                "legacy_tool_cross_validation_required": {
                    "closure_evidence_path": "release_evidence/productization/RH-002.cross_validation.json",
                    "last_checked_at_utc": "2026-05-05T05:06:07Z",
                },
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--commercial-readiness",
            str(_commercial(tmp_path / "commercial.json")),
            "--external-benchmark-submission-readiness",
            str(_external_submission(tmp_path / "external.json")),
            "--residual-holdout-closure-updates",
            str(updates),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
            "--json",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    rows = {row["work_item_id"]: row for row in payload["queues"]["residual_holdout_work_items"]}
    assert rows["RH-001"]["status"] == "closed"
    assert rows["RH-001"]["closure_evidence_status"] == "attached"
    assert rows["RH-001"]["last_checked_at_utc"] == "2026-05-05T04:05:06Z"
    assert rows["RH-002"]["closure_evidence_status"] == "attached"
    assert rows["RH-002"]["closure_evidence_path"].endswith("RH-002.cross_validation.json")
    assert payload["summary"]["residual_holdout_work_item_count"] == 3
    assert payload["summary"]["residual_holdout_open_count"] == 1
    assert payload["summary"]["residual_holdout_closure_evidence_pending_count"] == 1
    assert payload["summary"]["residual_holdout_closure_evidence_attached_count"] == 2
    assert payload["summary"]["residual_holdout_last_checked_count"] == 2

    closure_template = json.loads(Path(rows["RH-001"]["closure_packet_template_path"]).read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert closure_template["closure_evidence_path"].endswith("RH-001.closure.json")
    assert closure_template["last_checked_at_utc"] == "2026-05-05T04:05:06Z"
    assert "RH-001.closure.json" in markdown
    assert "2026-05-05T04:05:06Z" in markdown
