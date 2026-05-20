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
                "drawings": True,
                "data": True,
                "evidence": True,
                "manifest.json": True,
                "checksums.sha256": True,
                "README_DELIVERY.md": True,
                "DELIVERY_INDEX.md": True,
                "REVISION_HISTORY.md": True,
                "data/revision_policy.json": True,
            },
            "checksum_self_test": {"pass": True},
            "manifest_consistency_self_test": {"pass": True},
            "restore_smoke": {
                "pass": True,
                "viewer_shell_marker_pass": True,
                "delivery_index_marker_pass": True,
                "revision_policy_pass": True,
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
        },
    )
    viewer = _write_json(tmp_path / "viewer.json", {"contract_pass": True, "summary_line": "viewer pass"})
    visual = _write_json(tmp_path / "visual.json", {"contract_pass": True, "summary_line": "visual pass"})

    payload = check_workstation_delivery_readiness.check_workstation_delivery_readiness(
        hardware_profile=hardware,
        service_budget=budget,
        delivery_package_manifest=package,
        client_input_validation_report=client,
        job_record=job_record,
        job_retention_policy=retention,
        viewer_browser_performance_probe=viewer,
        viewer_visual_regression_baseline=visual,
    )

    assert payload["schema_version"] == "workstation-delivery-readiness.v1"
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
                "revision_policy_pass": False,
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
        {"contract_pass": False, "policy": {"delete_requires_explicit_confirmation": False}},
    )
    viewer = _write_json(tmp_path / "viewer.json", {"contract_pass": True})
    visual = _write_json(tmp_path / "visual.json", {"contract_pass": True})

    payload = check_workstation_delivery_readiness.check_workstation_delivery_readiness(
        hardware_profile=hardware,
        service_budget=budget,
        delivery_package_manifest=package,
        client_input_validation_report=client,
        job_record=job_record,
        job_retention_policy=retention,
        viewer_browser_performance_probe=viewer,
        viewer_visual_regression_baseline=visual,
    )

    assert payload["contract_pass"] is False
    assert "Delivery package manifest::delivery_package_manifest_not_green" in payload["blockers"]
    assert "Delivery package manifest::required_section_missing:viewer.html" in payload["blockers"]
    assert "Delivery package manifest::package_manifest_consistency_self_test_failed" in payload["blockers"]
    assert "Delivery package manifest::package_viewer_shell_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_delivery_index_marker_missing" in payload["blockers"]
    assert "Delivery package manifest::package_revision_policy_missing_or_invalid" in payload["blockers"]
    assert "Job reproducibility contract::job_folder_contract_failed" in payload["blockers"]
    assert "Job retention and cleanup policy::workstation_job_retention_policy_not_green" in payload["blockers"]
