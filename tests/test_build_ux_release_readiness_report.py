from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ux_release_readiness_report.py"
SPEC = importlib.util.spec_from_file_location("build_ux_release_readiness_report", SCRIPT_PATH)
assert SPEC is not None
build_ux_release_readiness_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ux_release_readiness_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_native_sample_workflow_receipt_is_extracted_from_command_stdout() -> None:
    receipt = {
        "schema_version": "structural-native-viewer-sample-workflow-receipt.v1",
        "action": "viewer_sample_workflow",
        "execution_mode": "execute",
        "status": "passed",
        "source_map_sha256": "sha256:" + "1" * 64,
        "frontend_contract_receipt_hash": "sha256:" + "2" * 64,
        "tracked_sources": [
            {
                "label": "viewer_index",
                "path": "src/structure-viewer/index.html",
                "bytes": 1,
                "sha256": "sha256:" + "3" * 64,
            },
            {
                "label": "sample_workflow_probe",
                "path": "scripts/verify-structure-viewer-sample-workflow.mjs",
                "bytes": 1,
                "sha256": "sha256:" + "4" * 64,
            },
            {
                "label": "canvas_frame_probe",
                "path": "scripts/structure-viewer-canvas-frame.mjs",
                "bytes": 1,
                "sha256": "sha256:" + "5" * 64,
            },
        ],
        "max_sample_completion_minutes": 30.0,
        "requested_output": None,
        "published_output_path": None,
        "output_disposition": "temporary_removed_after_verification",
        "logical_command_template": [
            "node",
            "scripts/verify-structure-viewer-sample-workflow.mjs",
            "--fail-blocked",
            "--out",
            "{workflow_output}",
            "--max-minutes",
            "30",
        ],
        "artifact_schema_version": "structure-viewer-sample-workflow-smoke.v1",
        "artifact_sha256": "sha256:" + "6" * 64,
        "artifact_generated_at": "2026-08-13T12:34:56.789Z",
        "verified_step_count": 4,
        "sample_completion_minutes": 0.25,
        "step_rows_sha256": "sha256:" + "7" * 64,
        "significant_pixel_count": 1,
        "browser_error_count": 0,
        "browser_warning_count": 0,
        "runtime_requirements": {
            "node_required": True,
            "browser_required": True,
            "retained_node_internal_listener": True,
        },
        "rust_owned_listener_count": 0,
        "direct_processes_spawned": 1,
        "successful_exit_code": 0,
        "external_network_access_accounting": (
            "not_instrumented_probe_loopback_and_browser_page_requests"
        ),
        "deterministic_receipt": False,
        "claim_boundary": "bounded automated rehearsal",
    }
    canonical = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt["receipt_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    stdout = "npm banner\n" + json.dumps(receipt, separators=(",", ":")) + "\n"

    assert (
        build_ux_release_readiness_report._native_sample_workflow_receipt(stdout)
        == receipt
    )
    forged = {**receipt, "verified_step_count": 3}
    assert (
        build_ux_release_readiness_report._native_sample_workflow_receipt(
            json.dumps(forged)
        )
        == {}
    )
    assert (
        build_ux_release_readiness_report._native_sample_workflow_receipt(
            '{"schema_version":"first","schema_version":"forged"}'
        )
        == {}
    )
    assert (
        build_ux_release_readiness_report._native_sample_workflow_receipt(
            '{"sample_completion_minutes":NaN}'
        )
        == {}
    )


def test_browser_smoke_default_enters_through_direct_rust_command() -> None:
    args = build_ux_release_readiness_report.build_parser().parse_args([])

    assert args.browser_smoke_command == (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-sample-workflow --root ."
    )
    assert "npm" not in args.browser_smoke_command.split()


def test_ux_release_readiness_rejects_missing_native_receipt_after_run(
    tmp_path: Path,
) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 0},
            "review_queue": [],
        },
    )
    viewer_perf = _write(
        tmp_path / "viewer_perf.json",
        {"contract_pass": True, "reason_code": "PASS"},
    )

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke={
            "return_code": 0,
            "elapsed_seconds": 1,
            "native_receipt_valid": False,
        },
    )

    assert payload["contract_pass"] is False
    assert "browser_sample_rehearsal_pass" in payload["blockers"]
    assert payload["artifacts"]["sample_workflow_smoke"] == ""


def test_ux_release_readiness_accepts_claim_scoped_review_queue(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS_WITH_REVIEW_QUEUE",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 1},
            "review_queue": [
                {
                    "asset_ref": "RD-001",
                    "quality_tier": "ifc_geometry_ready_load_review",
                    "quality_flags": ["not_solver_exact"],
                    "claim_quality_flags": ["ifc_load_model_missing"],
                    "recommended_action": "attach IFC load-model evidence before analysis claim",
                }
            ],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke={"return_code": 0, "elapsed_seconds": 120},
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["claim_scoped_review_item_count"] == 1
    assert payload["summary"]["blocking_review_item_count"] == 0
    assert payload["summary"]["sample_completion_minutes"] == 2.0


def test_ux_release_readiness_blocks_unscoped_review_queue(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS_WITH_REVIEW_QUEUE",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 1},
            "review_queue": [
                {
                    "asset_ref": "RD-002",
                    "quality_tier": "proxy_preview_review",
                    "quality_flags": ["proxy_layout_not_true_geometry"],
                    "claim_quality_flags": [],
                    "recommended_action": "replace proxy or preview topology with solver-exact structural geometry",
                }
            ],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke={"return_code": 0, "elapsed_seconds": 120},
    )

    assert payload["contract_pass"] is False
    assert "claim_scoped_review_queue_pass" in payload["blockers"]
    assert payload["summary"]["blocking_review_item_count"] == 1


def test_ux_release_readiness_blocks_missing_browser_rehearsal(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 0},
            "review_queue": [],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke=None,
    )

    assert payload["contract_pass"] is False
    assert "browser_sample_rehearsal_pass" in payload["blockers"]
    assert "sample_completion_30min_pass" in payload["blockers"]


def test_ux_release_readiness_reads_sample_workflow_artifact(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS_WITH_REVIEW_QUEUE",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 1},
            "review_queue": [
                {
                    "asset_ref": "RD-001",
                    "quality_tier": "ifc_geometry_ready_load_review",
                    "quality_flags": ["not_solver_exact"],
                    "claim_quality_flags": ["ifc_load_model_missing"],
                    "recommended_action": "attach IFC load-model evidence before analysis claim",
                }
            ],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})
    sample_workflow = _write(
        tmp_path / "structure_viewer_sample_workflow_smoke.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "sample_completion_minutes": 4.5,
            "browser_error_count": 0,
            "browser_warning_count": 1,
        },
    )

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        sample_workflow_smoke_path=sample_workflow,
        max_sample_minutes=30.0,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["sample_completion_minutes"] == 4.5
    assert payload["browser_smoke"]["artifact_path"] == str(sample_workflow)
    assert payload["artifacts"]["sample_workflow_smoke"] == str(sample_workflow)
