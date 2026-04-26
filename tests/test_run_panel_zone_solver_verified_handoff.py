from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"
LIVE_RELEASE_GAP = Path("implementation/phase1/release/release_gap_report.json")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_panel_zone_solver_verified_handoff_from_raw_sources_drives_green_panel_chain_without_touching_release(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, indent=2), encoding="utf-8")
    live_release_gap_hash_before = _sha256(LIVE_RELEASE_GAP)
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    clash_report = tmp_path / "panel_zone_clash_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--joint-geometry-source",
            str(FIXTURE_DIR / "joint_geometry_source.json"),
            "--rebar-anchorage-source",
            str(FIXTURE_DIR / "rebar_anchorage_source.json"),
            "--clash-verification-source",
            str(FIXTURE_DIR / "clash_verification_source.json"),
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--solver-verified-bundle-out",
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
            "--panel-zone-clash-artifact-out",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report-out",
            str(clash_report),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["inputs"]["input_mode"] == "raw_sources"
    assert payload["checks"]["panel_chain_pass"] is True
    assert payload["checks"]["release_surface_refresh_pass"] is True
    assert payload["checks"]["external_validation_refresh_pass"] is True
    assert "panel_zone_solver_verified_bundle" in [str(step.get("step")) for step in payload["steps"]]
    assert LIVE_RELEASE_GAP.exists()
    assert _sha256(LIVE_RELEASE_GAP) == live_release_gap_hash_before

    report_payload = _load_json(clash_report)
    assert report_payload["contract_pass"] is True
    assert report_payload["reason_code"] == "PASS"
    assert report_payload["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"


def test_run_panel_zone_solver_verified_handoff_accepts_prebuilt_bundle_and_skips_bundle_build(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, indent=2), encoding="utf-8")
    out = tmp_path / "panel_zone_solver_verified_handoff_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--solver-verified-bundle-in",
            str(FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"),
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
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
            "--panel-zone-clash-artifact-out",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report-out",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    assert payload["contract_pass"] is True
    assert payload["inputs"]["input_mode"] == "prebuilt_bundle"
    step_names = [str(step.get("step")) for step in payload["steps"]]
    assert "panel_zone_solver_verified_bundle" not in step_names
    assert payload["checks"]["panel_chain_pass"] is True
