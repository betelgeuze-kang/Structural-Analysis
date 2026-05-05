from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "report_commercialization_level.py"
SPEC = importlib.util.spec_from_file_location("report_commercialization_level", SCRIPT_PATH)
assert SPEC is not None
report_commercialization_level = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_commercialization_level)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _commercial(path: Path, *, full_replacement_ready: bool = False) -> Path:
    return _write_json(
        path,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "checks": {
                "real_source_pass": True,
                "benchmark_breadth_pass": True,
                "measured_dynamic_targets_pass": True,
                "measured_source_family_pass": True,
                "measured_case_count_pass": True,
                "accuracy_pass": True,
                "noise_robustness_pass": True,
                "ood_safety_pass": True,
                "gpu_strict_pass": True,
            },
            "grade": {"label": "Commercial", "commercial_pass": True},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": full_replacement_ready,
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


def _external(path: Path, *, attached_count: int = 0) -> Path:
    rows = []
    for index, queue_id in enumerate(
        ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"],
        start=1,
    ):
        attached = index <= attached_count
        rows.append(
            {
                "work_item_id": f"EB-{index:03d}",
                "queue_id": queue_id,
                "submission_id": f"p1-{queue_id}",
                "status": "ready_for_full_submission",
                "submission_lifecycle_status": "submitted_receipt_attached" if attached else "ready_to_submit",
                "submission_owner_action": (
                    "submission_receipt_attached_verify_roundtrip"
                    if attached
                    else "submit_external_benchmark_package_and_attach_receipt"
                ),
                "submission_receipt": f"https://bench.example/{queue_id}" if attached else "pending",
                "receipt_url": f"https://bench.example/{queue_id}" if attached else "",
                "receipt_status": "attached" if attached else "pending_external_submission_receipt",
                "closure_evidence_required": f"{queue_id}_submission_receipt",
                "closure_evidence_status": "attached" if attached else "pending",
                "status_lifecycle": {
                    "current_status": "ready_for_full_submission",
                    "submission_lifecycle_status": "submitted_receipt_attached" if attached else "ready_to_submit",
                    "submission_owner_action": (
                        "submission_receipt_attached_verify_roundtrip"
                        if attached
                        else "submit_external_benchmark_package_and_attach_receipt"
                    ),
                },
            }
        )
    return _write_json(
        path,
        {
            "contract_pass": True,
            "reason_code": "PASS_START_NOW_FULL",
            "summary": {
                "submission_queue_count": 4,
                "submission_receipt_attached_count": attached_count,
                "submission_receipt_pending_count": 4 - attached_count,
            },
            "submission_queue": rows,
        },
    )


def test_report_commercialization_level_marks_engineer_in_loop_commercial_assist(tmp_path: Path) -> None:
    payload = report_commercialization_level.build_report(
        commercial_readiness=_commercial(tmp_path / "commercial.json"),
        external_benchmark_submission_readiness=_external(tmp_path / "external.json"),
        p1_benchmark_breadth_status=tmp_path / "missing-p1-breadth.json",
        p1_operational_queues=tmp_path / "missing-ops.json",
    )

    assert payload["contract_pass"] is True
    assert payload["commercialization_score"] == 7.0
    assert payload["commercialization_level"] == "L3"
    assert payload["commercialization_level_label"] == "engineer_in_loop_commercial_assist_ready"
    assert payload["commercial_scope"]["full_commercial_replacement_ready"] is False
    assert "not a full autonomous commercial replacement" in payload["recommended_claim"]
    assert "external_submission_receipts_pending=4" in payload["blockers"]
    assert "p1_benchmark_execution_blocked_by_p0_or_execution_gate" in payload["blockers"]
    assert "residual_holdout_closure_pending=3" in payload["blockers"]
    assert "full_commercial_replacement_ready=false" in payload["blockers"]
    assert "p1_benchmark_breadth_inputs_ready" in payload["accelerators"]
    assert "residual_holdout_operational_queue_present" in payload["accelerators"]


def test_report_commercialization_level_promotes_when_evidence_closes(tmp_path: Path) -> None:
    p1_breadth = _write_json(
        tmp_path / "p1-breadth.json",
        {"p1_benchmark_execution_unblocked": True},
    )
    ops = _write_json(
        tmp_path / "ops.json",
        {
            "contract_pass": True,
            "summary": {
                "residual_holdout_work_item_count": 3,
                "residual_holdout_open_count": 0,
                "residual_holdout_closure_evidence_pending_count": 0,
            },
        },
    )

    payload = report_commercialization_level.build_report(
        commercial_readiness=_commercial(tmp_path / "commercial.json"),
        external_benchmark_submission_readiness=_external(tmp_path / "external.json", attached_count=4),
        p1_benchmark_breadth_status=p1_breadth,
        p1_operational_queues=ops,
    )

    assert payload["commercialization_score"] == 9.0
    assert payload["commercialization_level"] == "L4"
    assert payload["commercialization_level_label"] == "commercial_operations_ready_with_evidence_closure"
    assert payload["commercial_scope"]["full_commercial_replacement_ready"] is False
    assert payload["blockers"] == ["full_commercial_replacement_ready=false"]


def test_report_commercialization_level_reads_residual_holdout_sidecar(tmp_path: Path) -> None:
    rh_updates = _write_json(
        tmp_path / "rh-updates.json",
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": {
                "RH-001": {
                    "status": "closed",
                    "closure_evidence_path": "release_evidence/productization/RH-001.closure.json",
                    "closure_evidence_status": "attached",
                },
                "RH-002": {
                    "status": "closed",
                    "closure_evidence_path": "release_evidence/productization/RH-002.closure.json",
                    "closure_evidence_status": "attached",
                },
                "RH-003": {
                    "status": "closed",
                    "closure_evidence_path": "release_evidence/productization/RH-003.closure.json",
                    "closure_evidence_status": "attached",
                },
            },
        },
    )

    payload = report_commercialization_level.build_report(
        commercial_readiness=_commercial(tmp_path / "commercial.json"),
        external_benchmark_submission_readiness=_external(tmp_path / "external.json"),
        residual_holdout_closure_updates=rh_updates,
        p1_benchmark_breadth_status=tmp_path / "missing-p1-breadth.json",
        p1_operational_queues=tmp_path / "missing-ops.json",
    )

    assert payload["commercialization_score"] == 7.5
    assert "residual_holdout_closure_evidence_closed" in payload["accelerators"]
    assert all(not blocker.startswith("residual_holdout_closure_pending") for blocker in payload["blockers"])
    assert payload["artifacts"]["residual_holdout_closure_updates"].endswith("rh-updates.json")
