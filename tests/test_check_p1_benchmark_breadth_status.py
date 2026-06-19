from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_p1_benchmark_breadth_status.py"
SPEC = importlib.util.spec_from_file_location("check_p1_benchmark_breadth_status", SCRIPT_PATH)
assert SPEC is not None
check_p1_benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_p1_benchmark)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _p1_status(
    path: Path,
    *,
    execution_unblocked: bool = False,
    core_evidence_closed: bool = True,
) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "p1-readiness-status.v1",
            "p0_core_evidence_closed": core_evidence_closed,
            "p1_inputs_ready": True,
            "p1_execution_unblocked": execution_unblocked,
            "p0_release_blocker": not execution_unblocked,
        },
    )


def _commercial(
    path: Path,
    *,
    ok: bool = True,
    commercial_pass: bool = True,
    engineer_in_loop_ready: bool = True,
    full_replacement_ready: bool = False,
) -> Path:
    checks = {
        "real_source_pass": True,
        "benchmark_breadth_pass": ok,
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
            "schema_version": "commercial-readiness.v1",
            "contract_pass": ok,
            "reason_code": "PASS" if ok else "ERR_BREADTH",
            "checks": checks,
            "grade": {
                "label": "Commercial" if commercial_pass else "Pre-commercial",
                "commercial_pass": commercial_pass,
            },
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "engineer_in_loop_accelerated_coverage_ready": engineer_in_loop_ready,
                "full_commercial_replacement_ready": full_replacement_ready,
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
            },
            "residual_holdout_categories": [
                {"id": "licensed_engineer_review_required"},
                {"id": "legacy_tool_cross_validation_required"},
            ],
        },
    )


def _benchmark(path: Path, *, ok: bool = True, label: str = "Benchmark") -> Path:
    return _write_json(
        path,
        {
            "schema_version": "benchmark-report.v1",
            "contract_pass": ok,
            "reason_code": "PASS" if ok else "ERR_BENCHMARK",
            "summary_line": f"{label}: {'PASS' if ok else 'FAIL'}",
        },
    )


def _external_submission(path: Path, *, ok: bool = True, blocked: bool = False) -> Path:
    status = "blocked" if blocked else "ready_for_full_submission"
    queue = []
    for idx, queue_id in enumerate(
        ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"],
        start=1,
    ):
        queue.append(
            {
                "work_item_id": f"EB-{idx:03d}",
                "queue_id": queue_id,
                "submission_id": f"p1-{queue_id}",
                "submission_scope": "full_external_submission_package",
                "owner": f"{queue_id}_owner",
                "status": status,
                "lifecycle_status": status,
                "submission_lifecycle_status": "blocked" if blocked else "ready_to_submit",
                "submission_status": "blocked" if blocked else "ready_to_submit",
                "submission_owner_action": (
                    "clear_blockers_before_submission"
                    if blocked
                    else "submit_external_benchmark_package_and_attach_receipt"
                ),
                "receipt_status": "blocked" if blocked else "pending_external_submission_receipt",
                "submission_receipt": "pending",
                "submission_receipt_status": "blocked" if blocked else "pending_external_submission_receipt",
                "receipt_url": "",
                "onepage_attestation": f"{queue_id} one-page attestation",
                "onepage_attestation_status": "ready_for_full_submission" if not blocked else "blocked",
                "dry_run_evidence": f"{queue_id}: PASS",
                "closure_evidence_required": f"{queue_id}_submission_receipt",
                "closure_evidence_path": "",
                "closure_evidence_status": "pending",
                "status_lifecycle": {
                    "current_status": status,
                    "submission_lifecycle_status": "blocked" if blocked else "ready_to_submit",
                    "submission_owner_action": (
                        "clear_blockers_before_submission"
                        if blocked
                        else "submit_external_benchmark_package_and_attach_receipt"
                    ),
                    "submitted": False,
                    "receipt_verified": False,
                    "closure_evidence_attached": False,
                    "terminal": False,
                },
            }
        )
    return _write_json(
        path,
        {
            "schema_version": "1.0",
            "contract_pass": ok,
            "reason_code": "PASS_START_NOW_FULL" if ok else "ERR_ARCHITECTURE_BLOCKERS",
            "summary": {
                "submission_queue_count": 4,
                "submission_queue_ready_count": 0 if blocked else 4,
                "submission_queue_review_pending_count": 0,
                "submission_queue_blocked_count": 4 if blocked else 0,
                "submission_lifecycle_ready_to_submit_count": 0 if blocked else 4,
                "submission_lifecycle_review_boundary_pending_count": 0,
                "submission_lifecycle_blocked_count": 4 if blocked else 0,
                "submission_receipt_pending_count": 0 if blocked else 4,
                "onepage_attestation_status": "ready_for_full_submission" if not blocked else "blocked",
            },
            "submission_queue": queue,
        },
    )


def _paths(tmp_path: Path) -> dict[str, object]:
    return {
        "p1_readiness_status": _p1_status(tmp_path / "p1.json"),
        "commercial_readiness": _commercial(tmp_path / "commercial.json"),
        "external_benchmark_submission_readiness": _external_submission(tmp_path / "external_submission.json"),
        "external_benchmark_submission_updates": tmp_path / "missing_eb_updates.json",
        "residual_holdout_closure_updates": tmp_path / "missing_rh_updates.json",
        "benchmark_reports": [
            _benchmark(tmp_path / "hf.json", label="HF benchmark"),
            _benchmark(tmp_path / "wind.json", label="Wind benchmark"),
            _benchmark(tmp_path / "hinge.json", label="Hinge benchmark"),
        ],
    }


def test_benchmark_breadth_is_ready_but_blocked_by_p0_release(tmp_path: Path) -> None:
    status = check_p1_benchmark.build_status(**_paths(tmp_path))
    commercial_gate = status["gates"][1]

    assert status["generated_at"]
    assert status["source_commit_sha"] is not None
    assert status["engine_version"]
    assert "input_checksums" in status
    assert status["reused_evidence"] is True
    assert status["reuse_policy"] == "status_rebuilt_from_existing_p1_readiness_commercial_benchmark_and_sidecar_receipts"
    assert status["benchmark_breadth_inputs_ready"] is True
    assert status["p1_benchmark_execution_unblocked"] is False
    assert status["p0_release_blocker"] is True
    assert status["next_action"] == "close P0-1 release publication before running P1 benchmark breadth"
    assert commercial_gate["commercial_grade_label"] == "Commercial"
    assert commercial_gate["commercial_deployment_mode"] == "engineer_in_the_loop_accelerated_coverage"
    assert commercial_gate["engineer_in_loop_accelerated_coverage_ready"] is True
    assert commercial_gate["full_commercial_replacement_ready"] is False
    assert commercial_gate["residual_holdout_category_count"] == 2
    assert commercial_gate["residual_holdout_work_item_count"] == 2
    work_items = {row["work_item_id"]: row for row in commercial_gate["residual_holdout_work_items"]}
    assert set(work_items) == {"RH-001", "RH-002"}
    assert work_items["RH-001"]["queue_name"] == "licensed_engineer_review_queue"
    assert work_items["RH-001"]["sla_label"] == "72h"
    assert work_items["RH-001"]["due_date"] == "assignment_plus_3_business_days"
    assert work_items["RH-001"]["closure_evidence_required"] == "signed_engineer_review_packet"
    assert work_items["RH-001"]["closure_evidence_status"] == "pending"
    assert work_items["RH-002"]["queue_status"] == "pending_cross_validation"
    external_gate = status["gates"][2]
    assert external_gate["label"] == "External benchmark submission queue"
    assert external_gate["submission_queue_count"] == 4
    assert external_gate["required_lifecycle_fields_present"] is True
    assert external_gate["submission_queue"][0]["work_item_id"] == "EB-001"
    assert external_gate["submission_queue"][0]["submission_id"] == "p1-hardest_external_10case"
    assert external_gate["submission_queue"][0]["receipt_url"] == ""
    assert external_gate["submission_queue"][0]["submission_receipt"] == "pending"
    assert external_gate["submission_queue"][0]["submission_receipt_status"] == "pending_external_submission_receipt"
    assert external_gate["submission_queue"][0]["closure_evidence_status"] == "pending"
    assert external_gate["submission_queue"][0]["status_lifecycle"]["current_status"] == "ready_for_full_submission"
    assert commercial_gate["commercial_scope_ready"] is True
    assert status["summary"]["commercialization_scope"] == {
        "commercial_grade_label": "Commercial",
        "commercial_deployment_mode": "engineer_in_the_loop_accelerated_coverage",
        "engineer_in_loop_accelerated_coverage_ready": True,
        "full_commercial_replacement_ready": False,
        "accelerated_coverage_target_pct_range": [95, 99],
        "residual_holdout_target_pct_range": [1, 5],
        "residual_holdout_category_count": 2,
        "residual_holdout_work_item_count": 2,
        "residual_holdout_open_count": 2,
        "residual_holdout_closure_evidence_pending_count": 2,
        "residual_holdout_closure_evidence_attached_count": 0,
        "residual_holdout_last_checked_count": 0,
        "residual_holdout_closure_updates_path": str(tmp_path / "missing_rh_updates.json"),
        "residual_holdout_closure_updates_present": False,
        "commercial_scope_ready": True,
    }
    assert status["summary"]["external_benchmark_submission"] == {
        "submission_queue_count": 4,
        "submission_queue_ready_count": 4,
        "submission_queue_review_pending_count": 0,
        "submission_queue_blocked_count": 0,
        "submission_lifecycle_ready_to_submit_count": 4,
        "submission_lifecycle_review_boundary_pending_count": 0,
        "submission_lifecycle_blocked_count": 0,
        "submission_receipt_attached_count": 0,
        "submission_receipt_pending_count": 4,
        "submission_last_checked_count": 0,
        "closure_evidence_attached_count": 0,
        "external_benchmark_submission_updates_path": str(tmp_path / "missing_eb_updates.json"),
        "external_benchmark_submission_updates_present": False,
        "external_benchmark_submission_updates_applied_count": 0,
        "onepage_attestation_status": "ready_for_full_submission",
        "required_lifecycle_fields_present": True,
    }


def test_benchmark_breadth_unblocks_after_p1_execution_gate(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["p1_readiness_status"] = _p1_status(tmp_path / "p1.json", execution_unblocked=True)

    status = check_p1_benchmark.build_status(**paths)

    assert status["benchmark_breadth_inputs_ready"] is True
    assert status["p1_benchmark_execution_unblocked"] is True
    assert status["next_action"] == "run P1 quality/fallback/benchmark breadth execution"


def test_benchmark_breadth_merges_residual_holdout_closure_sidecar(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    updates = _write_json(
        tmp_path / "rh_updates.json",
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": {
                "RH-001": {
                    "status": "closed",
                    "queue_status": "closure_evidence_attached",
                    "closure_evidence_path": "release_evidence/productization/RH-001.closure.json",
                    "closure_evidence_status": "signed_attached",
                    "last_checked_at_utc": "2026-05-05T04:05:06Z",
                    "closed_at_utc": "2026-05-05T04:06:07Z",
                }
            },
        },
    )
    paths["residual_holdout_closure_updates"] = updates

    status = check_p1_benchmark.build_status(**paths)
    commercial_gate = status["gates"][1]
    work_items = {row["work_item_id"]: row for row in commercial_gate["residual_holdout_work_items"]}

    assert work_items["RH-001"]["status"] == "closed"
    assert work_items["RH-001"]["closure_evidence_status"] == "signed_attached"
    assert work_items["RH-001"]["closure_evidence_path"].endswith("RH-001.closure.json")
    assert work_items["RH-001"]["last_checked_at_utc"] == "2026-05-05T04:05:06Z"
    scope = status["summary"]["commercialization_scope"]
    assert scope["residual_holdout_work_item_count"] == 2
    assert scope["residual_holdout_open_count"] == 1
    assert scope["residual_holdout_closure_evidence_pending_count"] == 1
    assert scope["residual_holdout_closure_evidence_attached_count"] == 1
    assert scope["residual_holdout_last_checked_count"] == 1
    assert scope["residual_holdout_closure_updates_present"] is True


def test_benchmark_breadth_merges_external_submission_update_sidecar(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    updates = _write_json(
        tmp_path / "eb_updates.json",
        {
            "schema_version": "external-benchmark-submission-updates.v1",
            "updates": {
                "hardest_external_10case": {
                    "receipt_url": "https://bench.example/receipts/EB-001",
                    "receipt_status": "attached",
                    "submitted_at_utc": "2026-05-05T01:02:03Z",
                    "last_checked_at_utc": "2026-05-05T02:03:04Z",
                    "closure_evidence_status": "attached",
                }
            },
        },
    )
    paths["external_benchmark_submission_updates"] = updates

    status = check_p1_benchmark.build_status(**paths)
    external_gate = status["gates"][2]
    first = external_gate["submission_queue"][0]

    assert first["receipt_url"] == "https://bench.example/receipts/EB-001"
    assert first["receipt_status"] == "attached"
    assert first["last_checked_at_utc"] == "2026-05-05T02:03:04Z"
    assert external_gate["external_benchmark_submission_updates_applied_count"] == 1
    summary = status["summary"]["external_benchmark_submission"]
    assert summary["external_benchmark_submission_updates_present"] is True
    assert summary["external_benchmark_submission_updates_applied_count"] == 1
    assert summary["submission_receipt_attached_count"] == 1
    assert summary["submission_last_checked_count"] == 1


def test_benchmark_breadth_blocks_on_failed_report(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["benchmark_reports"] = [
        _benchmark(tmp_path / "hf.json", label="HF benchmark"),
        _benchmark(tmp_path / "wind.json", ok=False, label="Wind benchmark"),
    ]

    status = check_p1_benchmark.build_status(**paths)
    failed_gate = next(gate for gate in status["gates"] if str(gate.get("path", "")).endswith("wind.json"))

    assert status["benchmark_breadth_inputs_ready"] is False
    assert failed_gate["status"] == "blocked"
    assert failed_gate["reason_code"] == "ERR_BENCHMARK"


def test_benchmark_breadth_blocks_on_non_operational_external_submission_queue(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["external_benchmark_submission_readiness"] = _external_submission(
        tmp_path / "external_submission.json",
        ok=False,
        blocked=True,
    )

    status = check_p1_benchmark.build_status(**paths)
    external_gate = status["gates"][2]

    assert status["benchmark_breadth_inputs_ready"] is False
    assert external_gate["status"] == "blocked"
    assert external_gate["submission_queue_blocked_count"] == 4


def test_benchmark_breadth_blocks_when_commercial_scope_is_not_ready(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["commercial_readiness"] = _commercial(
        tmp_path / "commercial.json",
        engineer_in_loop_ready=False,
        full_replacement_ready=False,
    )

    status = check_p1_benchmark.build_status(**paths)
    commercial_gate = status["gates"][1]

    assert status["benchmark_breadth_inputs_ready"] is False
    assert commercial_gate["status"] == "blocked"
    assert commercial_gate["commercial_scope_ready"] is False
    assert commercial_gate["engineer_in_loop_accelerated_coverage_ready"] is False
    assert commercial_gate["full_commercial_replacement_ready"] is False


def test_benchmark_breadth_passes_publication_index_to_readiness_builder(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    paths.pop("p1_readiness_status")
    publication_index = tmp_path / "release-publication-evidence-index.json"

    def fake_build_p1_readiness_status(*, publication_evidence_index=None, **_kwargs):
        assert publication_evidence_index == publication_index
        return {
            "schema_version": "p1-readiness-status.v1",
            "p0_core_evidence_closed": True,
            "p1_inputs_ready": True,
            "p1_execution_unblocked": True,
            "p0_release_blocker": False,
            "publication_evidence_index": str(publication_index),
        }

    monkeypatch.setattr(check_p1_benchmark, "build_p1_readiness_status", fake_build_p1_readiness_status)

    status = check_p1_benchmark.build_status(publication_evidence_index=publication_index, **paths)

    assert status["p1_benchmark_execution_unblocked"] is True
    assert status["publication_evidence_index"] == str(publication_index)


def test_cli_writes_markdown_and_fails_when_blocked(tmp_path: Path, capsys) -> None:
    paths = _paths(tmp_path)
    out_md = tmp_path / "p1-benchmark.md"

    exit_code = check_p1_benchmark.main(
        [
            "--p1-readiness-status",
            str(paths["p1_readiness_status"]),
            "--commercial-readiness",
            str(paths["commercial_readiness"]),
            "--external-benchmark-submission-readiness",
            str(paths["external_benchmark_submission_readiness"]),
            "--external-benchmark-submission-updates",
            str(paths["external_benchmark_submission_updates"]),
            "--residual-holdout-closure-updates",
            str(paths["residual_holdout_closure_updates"]),
            "--benchmark-report",
            str(paths["benchmark_reports"][0]),
            "--benchmark-report",
            str(paths["benchmark_reports"][1]),
            "--benchmark-report",
            str(paths["benchmark_reports"][2]),
            "--out-md",
            str(out_md),
            "--fail-blocked",
        ]
    )

    captured = capsys.readouterr()
    markdown = out_md.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "P1 Benchmark Breadth Status" in captured.out
    assert "P1 work slice: `quality/fallback/benchmark breadth`" in captured.out
    assert "P1 Benchmark Breadth Status" in markdown
    assert "P1 work slice: `quality/fallback/benchmark breadth`" in markdown


def test_cli_fail_core_open_ignores_p1_execution_blocker(tmp_path: Path, capsys) -> None:
    paths = _paths(tmp_path)

    exit_code = check_p1_benchmark.main(
        [
            "--p1-readiness-status",
            str(paths["p1_readiness_status"]),
            "--commercial-readiness",
            str(paths["commercial_readiness"]),
            "--external-benchmark-submission-readiness",
            str(paths["external_benchmark_submission_readiness"]),
            "--external-benchmark-submission-updates",
            str(paths["external_benchmark_submission_updates"]),
            "--residual-holdout-closure-updates",
            str(paths["residual_holdout_closure_updates"]),
            "--benchmark-report",
            str(paths["benchmark_reports"][0]),
            "--benchmark-report",
            str(paths["benchmark_reports"][1]),
            "--benchmark-report",
            str(paths["benchmark_reports"][2]),
            "--json",
            "--fail-core-open",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"p0_core_evidence_closed": true' in captured.out
    assert '"p1_benchmark_execution_unblocked": false' in captured.out


def test_cli_fail_core_open_fails_when_core_evidence_is_open(tmp_path: Path, capsys) -> None:
    paths = _paths(tmp_path)
    paths["p1_readiness_status"] = _p1_status(
        tmp_path / "p1.json",
        execution_unblocked=False,
        core_evidence_closed=False,
    )

    exit_code = check_p1_benchmark.main(
        [
            "--p1-readiness-status",
            str(paths["p1_readiness_status"]),
            "--commercial-readiness",
            str(paths["commercial_readiness"]),
            "--external-benchmark-submission-readiness",
            str(paths["external_benchmark_submission_readiness"]),
            "--external-benchmark-submission-updates",
            str(paths["external_benchmark_submission_updates"]),
            "--residual-holdout-closure-updates",
            str(paths["residual_holdout_closure_updates"]),
            "--benchmark-report",
            str(paths["benchmark_reports"][0]),
            "--benchmark-report",
            str(paths["benchmark_reports"][1]),
            "--benchmark-report",
            str(paths["benchmark_reports"][2]),
            "--json",
            "--fail-core-open",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"p0_core_evidence_closed": false' in captured.out
