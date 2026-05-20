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
    assert payload["restore_smoke"]["revision_policy_pass"] is True
    assert any(row["path"] == "manifest.json" for row in payload["file_rows"])
    assert any(row["path"] == "DELIVERY_INDEX.md" for row in payload["file_rows"])
    assert any(row["path"] == "REVISION_HISTORY.md" for row in payload["file_rows"])
    assert any(row["path"] == "data/revision_policy.json" for row in payload["file_rows"])
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


def test_package_manifest_consistency_blocks_missing_zip(tmp_path: Path) -> None:
    payload = build_workstation_delivery_package.verify_package_manifest_consistency(tmp_path / "missing.zip")

    assert payload["pass"] is False
    assert payload["reason"] == "package_missing"
