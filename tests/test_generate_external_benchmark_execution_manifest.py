from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_external_benchmark_execution_manifest_prefers_hardest_10case_catalog(tmp_path: Path) -> None:
    out_dir = tmp_path / "kickoff"
    hardest_report = tmp_path / "hardest_external_10case_kickoff_gate_report.json"
    queue_manifest = tmp_path / "audit_review_queue.json"
    assignments = tmp_path / "audit_review_owner_assignments.json"
    approve_all_preview = out_dir / "external_benchmark_submission_readiness_preview.approve_all.json"
    reject_one_preview = out_dir / "external_benchmark_submission_readiness_preview.reject_one.json"
    decision_runner = out_dir / "audit_review_decision_batch_run_report.json"

    _write_json(
        hardest_report,
        {
            "contract_pass": True,
            "summary": {
                "ready_to_start_now": True,
                "ready_to_start_full_submission_now": False,
                "recommended_start_mode": "start_now_limited_external_benchmark",
                "review_pending_count": 2,
            },
            "case_rows": [{"case_id": "peer_tbi_tall_building_ndtha"}],
        },
    )
    _write_json(
        queue_manifest,
        {
            "audit_review_queue_items": [
                {
                    "packet_id": "packet-a",
                    "action_family": "detailing",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                    "change_count": 3,
                },
                {
                    "packet_id": "packet-b",
                    "action_family": "connection_detailing",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "change_count": 2,
                },
            ]
        },
    )
    _write_json(
        assignments,
        {
            "assignment_rows": [],
        },
    )
    _write_json(approve_all_preview, {"reason_code": "PASS_START_NOW_FULL", "summary": {"predicted_ready_to_start_full_submission_now": True}})
    _write_json(reject_one_preview, {"reason_code": "ERR_ARCHITECTURE_BLOCKERS", "summary": {"preview_resolution_open_revision_count": 1}})
    _write_json(decision_runner, {"reason_code": "PASS", "preview_reason_code": "PASS_START_NOW_FULL", "apply_live": False})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_execution_manifest.py",
            "--out-dir",
            str(out_dir),
            "--hardest-external-10case-kickoff-report",
            str(hardest_report),
            "--audit-review-queue-manifest",
            str(queue_manifest),
            "--audit-review-assignment-manifest",
            str(assignments),
            "--approve-all-preview",
            str(approve_all_preview),
            "--reject-one-preview",
            str(reject_one_preview),
            "--decision-runner-report",
            str(decision_runner),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((out_dir / "external_benchmark_execution_manifest.json").read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["case_task_count"] == 10
    assert payload["summary"]["ready_task_count"] == 10
    assert payload["summary"]["blocked_task_count"] == 2
    assert payload["ready_tasks"][0]["phase"] == "hardest_case"
    assert payload["ready_tasks"][0]["task_id"].startswith("hardest::")
    assert payload["blocked_tasks"][0]["phase"] == "review_boundary"
