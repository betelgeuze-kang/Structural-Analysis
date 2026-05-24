from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_workstation_delivery_package.py"
SPEC = importlib.util.spec_from_file_location("build_workstation_delivery_package", SCRIPT_PATH)
assert SPEC is not None
build_workstation_delivery_package = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_workstation_delivery_package)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_delivery_package_manifest_checksum_and_restore(tmp_path: Path) -> None:
    viewer = _write_text(tmp_path / "viewer.html", "<html><body>Structural Insight Viewer</body></html>")
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.4\n%%EOF\n")
    drawings = tmp_path / "drawings"
    _write_text(drawings / "plan.svg", "<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    client = _write_json(tmp_path / "client.json", {"status": "ready", "contract_pass": True})
    hardware = _write_json(tmp_path / "hardware.json", {"contract_pass": True})
    budget = _write_json(tmp_path / "budget.json", {"contract_pass": True})
    probe = _write_json(tmp_path / "probe.json", {"contract_pass": True})
    visual = _write_json(tmp_path / "visual.json", {"contract_pass": True})
    support = _write_json(tmp_path / "support.json", {"contract_pass": True})
    source_model = _write_json(
        tmp_path / "model.json",
        {"model": {"nodes": [{"id": "N1", "x": 0, "y": 0, "z": 0}], "elements": [{"id": "E1"}]}},
    )

    payload = build_workstation_delivery_package.build_workstation_delivery_package(
        out=tmp_path / "project_package.zip",
        manifest_out=tmp_path / "manifest.json",
        job_record_out=tmp_path / "job.json",
        job_root=tmp_path / "jobs",
        viewer_html=viewer,
        report_pdf=report,
        drawings_dir=drawings,
        client_validation_report=client,
        hardware_profile=hardware,
        service_budget=budget,
        viewer_browser_performance_probe=probe,
        viewer_visual_regression_baseline=visual,
        support_bundle_manifest=support,
        source_model=source_model,
    )

    assert payload["schema_version"] == "workstation-delivery-package-manifest.v1"
    assert payload["contract_pass"] is True
    assert payload["required_sections"]["viewer.html"] is True
    assert payload["checksum_self_test"]["pass"] is True
    assert payload["manifest_consistency_self_test"]["pass"] is True
    assert payload["restore_smoke"]["pass"] is True
    assert payload["restore_smoke"]["viewer_shell_marker_pass"] is True
    assert payload["restore_smoke"]["delivery_index_marker_pass"] is True
    assert payload["restore_smoke"]["acceptance_packet_marker_pass"] is True
    assert payload["restore_smoke"]["qa_summary_marker_pass"] is True
    assert payload["restore_smoke"]["handoff_diff_marker_pass"] is True
    assert payload["restore_smoke"]["pdf_magic_pass"] is True
    assert payload["restore_smoke"]["manifest_report_reference_pass"] is True
    assert payload["restore_smoke"]["manifest_acceptance_reference_pass"] is True
    assert payload["restore_smoke"]["manifest_claim_boundary_pass"] is True
    assert payload["restore_smoke"]["report_metadata_pass"] is True
    assert payload["restore_smoke"]["handoff_diff_summary_pass"] is True
    assert payload["restore_smoke"]["signing_manifest_pass"] is True
    assert payload["restore_smoke"]["revision_policy_pass"] is True
    assert payload["restore_smoke"]["redelivery_comparison_pass"] is True
    assert any(row["path"] == "manifest.json" for row in payload["file_rows"])
    assert any(row["path"] == "ACCEPTANCE_PACKET.md" for row in payload["file_rows"])
    assert any(row["path"] == "DELIVERY_QA_SUMMARY.md" for row in payload["file_rows"])
    assert any(row["path"] == "HANDOFF_DIFF_SUMMARY.md" for row in payload["file_rows"])
    assert any(row["path"] == "DELIVERY_INDEX.md" for row in payload["file_rows"])
    assert any(row["path"] == "REVISION_HISTORY.md" for row in payload["file_rows"])
    assert any(row["path"] == "data/handoff_diff_summary.json" for row in payload["file_rows"])
    assert any(row["path"] == "data/report_metadata.json" for row in payload["file_rows"])
    assert any(row["path"] == "data/revision_policy.json" for row in payload["file_rows"])
    assert any(row["path"] == "data/redelivery_comparison_manifest.json" for row in payload["file_rows"])
    assert any(row["path"] == "data/signing_manifest.json" for row in payload["file_rows"])
    assert payload["job_record"]["schema_version"] == "workstation-job-record.v1"
    assert payload["job_folder_contract"]["pass"] is True
    job_dir = Path(payload["job_folder_contract"]["job_dir"])
    assert (job_dir / "input_manifest.json").exists()
    assert (job_dir / "run_log.jsonl").exists()
    assert (job_dir / "output_manifest.json").exists()
    assert (job_dir / "checksums.sha256").exists()


def test_job_folder_verifier_blocks_missing_checksums(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_json(job_dir / "input_manifest.json", {"schema_version": "workstation-job-input-manifest.v1"})
    _write_text(job_dir / "run_log.jsonl", "{}\n")
    _write_json(job_dir / "output_manifest.json", {"schema_version": "workstation-job-output-manifest.v1"})

    payload = build_workstation_delivery_package.verify_job_folder(job_dir)

    assert payload["pass"] is False
    assert payload["required_paths"]["checksums.sha256"] is False


def test_restore_package_smoke_blocks_missing_zip(tmp_path: Path) -> None:
    payload = build_workstation_delivery_package.restore_package_smoke(tmp_path / "missing.zip")

    assert payload["pass"] is False
    assert payload["reason"] == "package_missing"


def test_restore_package_smoke_blocks_non_pdf_report(tmp_path: Path) -> None:
    package = tmp_path / "bad.zip"
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    (root / "drawings").mkdir()
    (root / "evidence").mkdir()
    _write_text(root / "DELIVERY_INDEX.md", "## Open Order\n## Acceptance Checklist\n")
    _write_text(
        root / "ACCEPTANCE_PACKET.md",
        "## Acceptance Decision\n## Package Integrity\n## Engineer Review Required\n",
    )
    _write_text(
        root / "DELIVERY_QA_SUMMARY.md",
        "## Customer-Visible QA Status\n## Included Checks\n## Hidden/Internal Checks\n",
    )
    _write_text(
        root / "HANDOFF_DIFF_SUMMARY.md",
        "# Customer Handoff Diff Summary\n## Package Changes\n## Review Guidance\n",
    )
    _write_text(root / "REVISION_HISTORY.md", "# Revision History\n")
    _write_text(root / "README_DELIVERY.md", "# Delivery\n")
    _write_text(root / "viewer.html", "<html><body>Structural Insight Viewer</body></html>")
    _write_text(root / "report.pdf", "not a pdf")
    _write_json(
        root / "data" / "revision_policy.json",
        {
            "schema_version": "workstation-delivery-revision-policy.v1",
            "policy": {"redelivery_requires_new_package": True},
        },
    )
    _write_json(
        root / "data" / "report_metadata.json",
        {
            "schema_version": "workstation-delivery-report-metadata.v1",
            "current_job_id": "J1",
            "engineer_review_required": True,
            "manifest_path": "manifest.json",
            "qa_summary_path": "DELIVERY_QA_SUMMARY.md",
            "report_path": "report.pdf",
            "report_sha256": build_workstation_delivery_package._sha256_path(root / "report.pdf"),
            "revision_history_path": "REVISION_HISTORY.md",
            "revision_policy_path": "data/revision_policy.json",
        },
    )
    _write_json(
        root / "data" / "handoff_diff_summary.json",
        {
            "schema_version": "workstation-delivery-handoff-diff-summary.v1",
            "comparison_scope": "package_member_delta",
            "current_job_id": "J1",
            "data_path": "data/handoff_diff_summary.json",
            "engineer_review_required": True,
            "summary": {
                "added_count": 0,
                "changed_count": 0,
                "removed_count": 0,
                "unchanged_count": 1,
            },
            "summary_markdown_path": "HANDOFF_DIFF_SUMMARY.md",
        },
    )
    _write_json(
        root / "data" / "redelivery_comparison_manifest.json",
        {
            "schema_version": "workstation-delivery-redelivery-comparison.v1",
            "current_job_id": "J1",
            "engineer_review_required": True,
            "redelivery_policy": {"previous_packages_must_not_be_overwritten": True},
        },
    )
    _write_json(
        root / "data" / "signing_manifest.json",
        {
            "schema_version": "workstation-delivery-signing-manifest.v1",
            "current_job_id": "J1",
            "engineer_review_required": True,
            "key_material_included": False,
            "offline_signing_required": True,
            "private_key_included": False,
            "signable_payload": ["manifest.json", "checksums.sha256"],
            "signed": False,
            "signing_status": "unsigned_placeholder",
            "verification_status": "not_signed",
        },
    )
    rows = build_workstation_delivery_package._checksum_rows(root, include_manifest=False)
    _write_json(
        root / "manifest.json",
        {
            "package_claim_boundary": "requires structural engineer review",
            "current_job_id": "J1",
            "output_rows": rows,
        },
    )
    build_workstation_delivery_package._write_checksums(
        root,
        build_workstation_delivery_package._checksum_rows(root, include_manifest=True),
    )
    build_workstation_delivery_package._write_zip(root, package)

    payload = build_workstation_delivery_package.restore_package_smoke(package)

    assert payload["pass"] is False
    assert payload["qa_summary_marker_pass"] is True
    assert payload["handoff_diff_marker_pass"] is True
    assert payload["report_metadata_pass"] is True
    assert payload["handoff_diff_summary_pass"] is True
    assert payload["signing_manifest_pass"] is True
    assert payload["pdf_magic_pass"] is False


def test_package_manifest_consistency_blocks_missing_zip(tmp_path: Path) -> None:
    payload = build_workstation_delivery_package.verify_package_manifest_consistency(tmp_path / "missing.zip")

    assert payload["pass"] is False
    assert payload["reason"] == "package_missing"
