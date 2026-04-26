from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_hardest_external_10case_program_executes_all_cases(tmp_path: Path) -> None:
    kickoff_dir = tmp_path / "kickoff"
    hardest_report = tmp_path / "hardest_external_10case_kickoff_gate_report.json"
    queue_manifest = tmp_path / "audit_review_queue.json"
    assignments = tmp_path / "audit_review_owner_assignments.json"
    approve_all_preview = kickoff_dir / "external_benchmark_submission_readiness_preview.approve_all.json"
    reject_one_preview = kickoff_dir / "external_benchmark_submission_readiness_preview.reject_one.json"
    decision_runner = kickoff_dir / "audit_review_decision_batch_run_report.json"

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
    _write_json(assignments, {"assignment_rows": []})
    _write_json(approve_all_preview, {"updates": [{"packet_id": "packet-a", "set_status": "approved"}, {"packet_id": "packet-b", "set_status": "approved"}]})
    _write_json(reject_one_preview, {"reason_code": "ERR_ARCHITECTURE_BLOCKERS"})
    _write_json(decision_runner, {"reason_code": "PASS"})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_hardest_external_10case_program.py",
            "--kickoff-dir",
            str(kickoff_dir),
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
            "--execution-manifest",
            str(kickoff_dir / "external_benchmark_execution_manifest.json"),
            "--status-manifest-out",
            str(kickoff_dir / "external_benchmark_execution_status_manifest.json"),
            "--updates-json",
            str(kickoff_dir / "external_benchmark_execution_updates.json"),
            "--runs-dir",
            str(kickoff_dir / "runs"),
            "--out",
            str(kickoff_dir / "hardest_external_10case_program_report.json"),
            "--no-refresh-release-surfaces",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads((kickoff_dir / "hardest_external_10case_program_report.json").read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["task_count"] == 10
    assert report["summary"]["completed_case_count"] == 10
    assert report["summary"]["kpi_receipt_count"] == 10
    assert report["summary"]["signed_bundle_count"] == 10
    assert Path(report["live_ready_template_json"]).exists()
