from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_workstation_delivery_readiness.py"
SPEC = importlib.util.spec_from_file_location("check_workstation_delivery_readiness", SCRIPT_PATH)
assert SPEC is not None
check_workstation_delivery_readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_workstation_delivery_readiness)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_workstation_delivery_readiness_passes_green_artifacts(tmp_path: Path) -> None:
    hardware = _write_json(tmp_path / "hardware.json", {"contract_pass": True, "summary_line": "hardware pass"})
    budget = _write_json(tmp_path / "budget.json", {"contract_pass": True, "summary_line": "budget pass"})
    package = _write_json(
        tmp_path / "package.json",
        {
            "contract_pass": True,
            "package_path": "project_package.zip",
            "package_claim_boundary": "engineer review; not an autonomous replacement",
            "required_sections": {
                "report.pdf": True,
                "viewer.html": True,
                "ACCEPTANCE_PACKET.md": True,
                "drawings": True,
                "data": True,
                "evidence": True,
                "manifest.json": True,
                "checksums.sha256": True,
                "README_DELIVERY.md": True,
                "DELIVERY_INDEX.md": True,
                "REVISION_HISTORY.md": True,
                "DELIVERY_QA_SUMMARY.md": True,
                "HANDOFF_DIFF_SUMMARY.md": True,
                "data/handoff_diff_summary.json": True,
                "data/report_metadata.json": True,
                "data/revision_policy.json": True,
                "data/redelivery_comparison_manifest.json": True,
                "data/signing_manifest.json": True,
            },
            "checksum_self_test": {"pass": True},
            "manifest_consistency_self_test": {"pass": True},
            "restore_smoke": {
                "pass": True,
                "viewer_shell_marker_pass": True,
                "delivery_index_marker_pass": True,
                "acceptance_packet_marker_pass": True,
                "qa_summary_marker_pass": True,
                "handoff_diff_marker_pass": True,
                "pdf_magic_pass": True,
                "manifest_report_reference_pass": True,
                "manifest_acceptance_reference_pass": True,
                "manifest_claim_boundary_pass": True,
                "report_metadata_pass": True,
                "handoff_diff_summary_pass": True,
                "signing_manifest_pass": True,
                "revision_policy_pass": True,
                "redelivery_comparison_pass": True,
            },
            "job_folder_contract": {
                "pass": True,
                "job_dir": "jobs/J1",
                "required_paths": {
                    "input_manifest.json": True,
                    "run_log.jsonl": True,
                    "output_manifest.json": True,
                    "checksums.sha256": True,
                },
                "checksum_self_test": {"pass": True},
            },
        },
    )
    client = _write_json(tmp_path / "client.json", {"status": "needs_review", "missing_data_report": ["units"]})
    job_record = _write_json(
        tmp_path / "job.json",
        {"schema_version": "workstation-job-record.v1", "job_id": "J1"},
    )
    retention = _write_json(
        tmp_path / "retention.json",
        {
            "contract_pass": True,
            "latest_job_id": "J1",
            "policy": {
                "retention_days": 365,
                "max_completed_jobs": 200,
                "delete_requires_explicit_confirmation": True,
                "cleanup_dry_run_required": True,
            },
            "cleanup_preview": {
                "mode": "dry_run_only",
                "delete_operation_executed": False,
                "candidate_count": 0,
            },
        },
    )
    viewer = _write_json(tmp_path / "viewer.json", {"contract_pass": True, "summary_line": "viewer pass"})
    visual = _write_json(tmp_path / "visual.json", {"contract_pass": True, "summary_line": "visual pass"})
    delivery_viewer_smoke = _write_json(
        tmp_path / "delivery-viewer-smoke.json",
        {
            "contract_pass": True,
            "summary_line": "delivery viewer pass",
            "package_path": "project_package.zip",
            "static_checks": {
                "pass": True,
                "commercial_cockpit_alignment": {"status": "current_cockpit_delivery"},
            },
            "browser_checks": {"pass": True},
            "warnings": [],
        },
    )

    payload = check_workstation_delivery_readiness.check_workstation_delivery_readiness(
        hardware_profile=hardware,
        service_budget=budget,
        delivery_package_manifest=package,
        client_input_validation_report=client,
        job_record=job_record,
        job_retention_policy=retention,
        viewer_browser_performance_probe=viewer,
        viewer_visual_regression_baseline=visual,
        delivery_viewer_smoke=delivery_viewer_smoke,
    )

    assert payload["schema_version"] == "workstation-delivery-readiness.v1"
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["contract_pass"] is True
    assert payload["workstation_delivery_service_ready"] is True
    assert payload["summary_line"].startswith("Workstation delivery readiness: PASS")


def test_workstation_delivery_readiness_blocks_bad_package(tmp_path: Path) -> None:
    hardware = _write_json(tmp_path / "hardware.json", {"contract_pass": True})
    budget = _write_json(tmp_path / "budget.json", {"contract_pass": True})
    package = _write_json(
        tmp_path / "package.json",
        {
            "contract_pass": False,
            "package_claim_boundary": "",
            "required_sections": {"viewer.html": False},
            "checksum_self_test": {"pass": False},
            "manifest_consistency_self_test": {"pass": False},
            "restore_smoke": {
                "pass": False,
                "viewer_shell_marker_pass": False,
                "delivery_index_marker_pass": False,
                "acceptance_packet_marker_pass": False,
                "qa_summary_marker_pass": False,
                "handoff_diff_marker_pass": False,
                "pdf_magic_pass": False,
                "manifest_report_reference_pass": False,
                "manifest_acceptance_reference_pass": False,
                "manifest_claim_boundary_pass": False,
                "report_metadata_pass": False,
                "handoff_diff_summary_pass": False,
                "signing_manifest_pass": False,
                "revision_policy_pass": False,
                "redelivery_comparison_pass": False,
            },
            "job_folder_contract": {"pass": False, "required_paths": {}, "checksum_self_test": {"pass": False}},
        },
    )
    client = _write_json(tmp_path / "client.json", {"status": "ready"})
    job_record = _write_json(
        tmp_path / "job.json",
        {"schema_version": "workstation-job-record.v1", "job_id": "J1"},
    )
    retention = _write_json(
        tmp_path / "retention.json",
        {
            "contract_pass": False,
            "policy": {"delete_requires_explicit_confirmation": False},
            "cleanup_preview": {"mode": "delete", "delete_operation_executed": True},
        },
    )
    viewer = _write_json(tmp_path / "viewer.json", {"contract_pass": True})
    visual = _write_json(tmp_path / "visual.json", {"contract_pass": True})
    delivery_viewer_smoke = _write_json(
        tmp_path / "delivery-viewer-smoke.json",
        {
            "contract_pass": False,
            "static_checks": {"pass": False},
            "browser_checks": {"pass": False},
            "blockers": ["browser_delivery_viewer_open_failed"],
        },
    )

    payload = check_workstation_delivery_readiness.check_workstation_delivery_readiness(
        hardware_profile=hardware,
        service_budget=budget,
        delivery_package_manifest=package,
        client_input_validation_report=client,
        job_record=job_record,
        job_retention_policy=retention,
        viewer_browser_performance_probe=viewer,
        viewer_visual_regression_baseline=visual,
        delivery_viewer_smoke=delivery_viewer_smoke,
    )

    assert payload["contract_pass"] is False
    assert "Delivery package manifest::delivery_package_manifest_not_green" in payload["blockers"]
    assert "Delivery package manifest::required_section_missing:viewer.html" in payload["blockers"]
    assert "Delivery package manifest::package_manifest_consistency_self_test_failed" in payload["blockers"]
    assert "Delivery package manifest::package_viewer_shell_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_delivery_index_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_acceptance_packet_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_qa_summary_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_handoff_diff_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_pdf_magic_missing" in payload["blockers"]
    assert "Delivery package manifest::package_manifest_report_reference_missing" in payload["blockers"]
    assert "Delivery package manifest::package_manifest_acceptance_reference_missing" in payload["blockers"]
    assert "Delivery package manifest::package_manifest_claim_boundary_missing" in payload["blockers"]
    assert "Delivery package manifest::package_report_metadata_missing_or_invalid" in payload["blockers"]
    assert "Delivery package manifest::package_handoff_diff_summary_missing_or_invalid" in payload["blockers"]
    assert "Delivery package manifest::package_signing_manifest_missing_or_invalid" in payload["blockers"]
    assert "Delivery package manifest::package_revision_policy_missing_or_invalid" in payload["blockers"]
    assert "Delivery package manifest::package_redelivery_comparison_missing_or_invalid" in payload["blockers"]
    assert "Customer-open delivery viewer smoke::workstation_delivery_viewer_smoke_not_green" in payload["blockers"]
    assert "Customer-open delivery viewer smoke::workstation_delivery_viewer_static_failed" in payload["blockers"]
    assert "Customer-open delivery viewer smoke::workstation_delivery_viewer_browser_failed" in payload["blockers"]
    assert "Customer-open delivery viewer smoke::workstation_delivery_viewer_not_current_commercial_cockpit" in payload["blockers"]
    assert "Job reproducibility contract::job_folder_contract_failed" in payload["blockers"]
    assert "Job retention and cleanup policy::workstation_job_retention_policy_not_green" in payload["blockers"]
    assert "Job retention and cleanup policy::job_retention_cleanup_preview_not_dry_run" in payload["blockers"]
    assert "Job retention and cleanup policy::job_retention_cleanup_deleted_files" in payload["blockers"]


def test_workstation_delivery_readiness_blocks_legacy_delivery_viewer(tmp_path: Path) -> None:
    hardware = _write_json(tmp_path / "hardware.json", {"contract_pass": True})
    budget = _write_json(tmp_path / "budget.json", {"contract_pass": True})
    package = _write_json(
        tmp_path / "package.json",
        {
            "contract_pass": True,
            "package_claim_boundary": "structural engineer review required",
            "required_sections": {
                "report.pdf": True,
                "viewer.html": True,
                "drawings": True,
                "data": True,
                "evidence": True,
                "manifest.json": True,
                "checksums.sha256": True,
                "README_DELIVERY.md": True,
            },
            "checksum_self_test": {"pass": True},
            "manifest_consistency_self_test": {"pass": True},
            "restore_smoke": {"pass": True},
            "job_folder_contract": {"pass": True, "required_paths": {}, "checksum_self_test": {"pass": True}},
        },
    )
    client = _write_json(tmp_path / "client.json", {"status": "ready"})
    job_record = _write_json(tmp_path / "job.json", {"schema_version": "workstation-job-record.v1", "job_id": "J1"})
    retention = _write_json(
        tmp_path / "retention.json",
        {
            "contract_pass": True,
            "policy": {"delete_requires_explicit_confirmation": True, "cleanup_dry_run_required": True},
            "cleanup_preview": {"mode": "dry_run_only", "delete_operation_executed": False},
        },
    )
    viewer = _write_json(tmp_path / "viewer.json", {"contract_pass": True})
    visual = _write_json(tmp_path / "visual.json", {"contract_pass": True})
    delivery_viewer_smoke = _write_json(
        tmp_path / "delivery-viewer-smoke.json",
        {
            "contract_pass": True,
            "static_checks": {
                "pass": True,
                "commercial_cockpit_alignment": {"status": "legacy_singlefile_delivery_gap"},
            },
            "browser_checks": {"pass": True},
        },
    )

    payload = check_workstation_delivery_readiness.check_workstation_delivery_readiness(
        hardware_profile=hardware,
        service_budget=budget,
        delivery_package_manifest=package,
        client_input_validation_report=client,
        job_record=job_record,
        job_retention_policy=retention,
        viewer_browser_performance_probe=viewer,
        viewer_visual_regression_baseline=visual,
        delivery_viewer_smoke=delivery_viewer_smoke,
    )

    assert payload["contract_pass"] is False
    assert "Customer-open delivery viewer smoke::workstation_delivery_viewer_not_current_commercial_cockpit" in payload["blockers"]
