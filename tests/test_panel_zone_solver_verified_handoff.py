from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_panel_zone_solver_verified_handoff_builds_bundle_and_drives_green_path(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    bundle = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    clash_report = tmp_path / "panel_zone_clash_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
        "--design-optimization-dataset",
        str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
        "--pbd-review-package",
        str(pbd),
        "--joint-geometry-source",
        str(FIXTURE_DIR / "joint_geometry_source.json"),
        "--rebar-anchorage-source",
        str(FIXTURE_DIR / "rebar_anchorage_source.json"),
        "--clash-verification-source",
        str(FIXTURE_DIR / "clash_verification_source.json"),
        "--panel-zone-solver-export-bundle",
        str(bundle),
        "--panel-zone-joint-geometry-source-output",
        str(tmp_path / "panel_zone_joint_geometry_3d.json"),
        "--panel-zone-rebar-anchorage-source-output",
        str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
        "--panel-zone-clash-verification-source-output",
        str(tmp_path / "panel_zone_clash_verification_3d.json"),
        "--panel-zone-joint-geometry-contract",
        str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
        "--panel-zone-rebar-anchorage-contract",
        str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
        "--panel-zone-clash-verification-contract",
        str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
        "--panel-zone-clash-artifact",
        str(tmp_path / "panel_zone_clash_artifact.json"),
        "--panel-zone-clash-report",
        str(clash_report),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    handoff = _load_json(out)
    assert handoff["contract_pass"] is True
    assert handoff["reason_code"] == "PASS"
    assert handoff["summary"]["source_input_mode"] == "raw_sources"
    assert handoff["summary"]["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert handoff["summary"]["validated_source_row_count_total"] == 3
    assert handoff["summary"]["validated_source_overlap_member_count_min"] == 1
    step_names = [str(step.get("step")) for step in handoff["steps"]]
    assert "panel_zone_solver_verified_bundle" in step_names
    assert "panel_zone_clash_report" in step_names
    assert "release_gap_report" not in step_names

    clash_payload = _load_json(clash_report)
    assert clash_payload["contract_pass"] is True
    assert clash_payload["reason_code"] == "PASS"
    assert clash_payload["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"


def test_panel_zone_solver_verified_handoff_dry_run_plans_release_refresh_steps(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
        "--design-optimization-dataset",
        str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
        "--pbd-review-package",
        str(pbd),
        "--panel-zone-solver-export-bundle",
        str(FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"),
        "--panel-zone-joint-geometry-source-output",
        str(tmp_path / "panel_zone_joint_geometry_3d.json"),
        "--panel-zone-rebar-anchorage-source-output",
        str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
        "--panel-zone-clash-verification-source-output",
        str(tmp_path / "panel_zone_clash_verification_3d.json"),
        "--panel-zone-joint-geometry-contract",
        str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
        "--panel-zone-rebar-anchorage-contract",
        str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
        "--panel-zone-clash-verification-contract",
        str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
        "--panel-zone-clash-artifact",
        str(tmp_path / "panel_zone_clash_artifact.json"),
        "--panel-zone-clash-report",
        str(tmp_path / "panel_zone_clash_report.json"),
        "--refresh-release-surfaces",
        "--refresh-external-validation",
        "--dry-run",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    handoff = _load_json(out)
    assert handoff["contract_pass"] is True
    assert handoff["summary"]["source_input_mode"] == "prebuilt_bundle"
    assert handoff["summary"]["release_surface_refresh_model"] == "gap -> registry -> committee -> gap -> registry -> external"
    steps = handoff["steps"]
    step_names = [str(step.get("step")) for step in steps]
    assert step_names == [
        "panel_zone_joint_geometry_source",
        "panel_zone_joint_geometry_contract",
        "panel_zone_rebar_anchorage_source",
        "panel_zone_rebar_anchorage_contract",
        "panel_zone_clash_verification_source",
        "panel_zone_clash_verification_contract",
        "panel_zone_clash_artifact",
        "panel_zone_clash_report",
        "release_gap_report",
        "release_registry_pass1",
        "committee_review_package",
        "release_registry_pass2",
        "external_validation_submission",
    ]
    for step in steps:
        assert step["status"] == "dry_run"
        assert step["ok"] is True
    assert "prepare_external_validation_submission.py" in steps[-1]["command"]


def test_panel_zone_solver_verified_handoff_accepts_preferred_verified_bundle_alias(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-verified-export-bundle",
            str(FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    handoff = _load_json(out)
    assert handoff["contract_pass"] is True
    assert handoff["summary"]["source_input_mode"] == "prebuilt_bundle"
    assert handoff["checks"]["panel_chain_pass"] is True


def test_panel_zone_solver_verified_handoff_discovers_manifested_drop_dir(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
        "--design-optimization-dataset",
        str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
        "--pbd-review-package",
        str(pbd),
        "--source-drop-dir",
        str(FIXTURE_DIR / "drop_package"),
        "--panel-zone-joint-geometry-source-output",
        str(tmp_path / "panel_zone_joint_geometry_3d.json"),
        "--panel-zone-rebar-anchorage-source-output",
        str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
        "--panel-zone-clash-verification-source-output",
        str(tmp_path / "panel_zone_clash_verification_3d.json"),
        "--panel-zone-joint-geometry-contract",
        str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
        "--panel-zone-rebar-anchorage-contract",
        str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
        "--panel-zone-clash-verification-contract",
        str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
        "--panel-zone-clash-artifact",
        str(tmp_path / "panel_zone_clash_artifact.json"),
        "--panel-zone-clash-report",
        str(tmp_path / "panel_zone_clash_report.json"),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    handoff = _load_json(out)
    assert handoff["contract_pass"] is True
    assert handoff["summary"]["source_input_mode"] == "raw_sources"
    assert handoff["summary"]["source_origin_class"] == "fixture_sample"
    discovered = handoff["inputs"]["discovered_inputs"]
    assert discovered["joint"].endswith("joint_geometry_source.json")
    assert discovered["anchorage"].endswith("rebar_anchorage_source.json")
    assert discovered["clash"].endswith("clash_verification_source.json")


def test_panel_zone_solver_verified_handoff_blocks_live_refresh_for_unclassified_source(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-export-bundle",
            str(FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--refresh-release-surfaces",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    handoff = _load_json(out)
    assert handoff["reason_code"] == "ERR_RELEASE_REFRESH_SOURCE_UNCLASSIFIED"
    assert handoff["checks"]["panel_chain_pass"] is True
    assert handoff["checks"]["release_refresh_source_allowed"] is False
    assert handoff["summary"]["source_origin_class"] == "unclassified_external_source"
    assert handoff["summary"]["release_surface_refresh_guard_status"] == "blocked_unclassified_source"
    step_names = [str(step.get("step")) for step in handoff["steps"]]
    assert "panel_zone_clash_report" in step_names
    assert "release_gap_report" not in step_names


def test_panel_zone_solver_verified_handoff_allows_trusted_raw_source_class_in_dry_run_refresh(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--joint-geometry-source",
            str(FIXTURE_DIR / "joint_geometry_source.json"),
            "--rebar-anchorage-source",
            str(FIXTURE_DIR / "rebar_anchorage_source.json"),
            "--clash-verification-source",
            str(FIXTURE_DIR / "clash_verification_source.json"),
            "--source-origin-class",
            "trusted_external_solver_source",
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--refresh-release-surfaces",
            "--dry-run",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    handoff = _load_json(out)
    assert handoff["contract_pass"] is True
    assert handoff["checks"]["release_refresh_source_allowed"] is True
    assert handoff["summary"]["source_origin_class"] == "trusted_external_solver_source"
    assert handoff["summary"]["release_surface_refresh_guard_status"] == "allowed"


def test_panel_zone_solver_verified_handoff_reads_trusted_origin_from_drop_dir_manifest(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--source-drop-dir",
            str(FIXTURE_DIR / "trusted_drop_package"),
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--refresh-release-surfaces",
            "--dry-run",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    handoff = _load_json(out)
    assert handoff["contract_pass"] is True
    assert handoff["checks"]["release_refresh_source_allowed"] is True
    assert handoff["summary"]["source_origin_class"] == "trusted_external_solver_source"
    assert handoff["summary"]["release_surface_refresh_guard_status"] == "allowed"
    assert "release_gap_report" in [str(step.get("step")) for step in handoff["steps"]]
