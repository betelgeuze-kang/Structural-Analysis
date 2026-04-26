from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_source_artifact(tmp_path: Path, source_kind: str, source_fixture: str, out_name: str) -> Path:
    out = tmp_path / out_name
    source_path = Path(source_fixture)
    if not source_path.is_absolute():
        source_path = FIXTURE_DIR / source_fixture
    proc = subprocess.run(
        [
            sys.executable,
            f"implementation/phase1/generate_panel_zone_{source_kind}_3d_source.py",
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--source-input",
            str(source_path),
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
    return out


def _run_contract(tmp_path: Path, source_kind: str, source_artifact: Path) -> Path:
    out = tmp_path / f"{source_kind}_contract.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_contract.py",
            "--source-kind",
            source_kind,
            "--source-artifact",
            str(source_artifact),
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
    return out


def test_panel_zone_3d_sample_fixtures_drive_green_path_into_artifact_and_report(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(dataset, _load_json(FIXTURE_DIR / "design_optimization_dataset_report.json"))

    joint_artifact = _run_source_artifact(tmp_path, "joint_geometry", "joint_geometry_source.json", "panel_zone_joint_geometry_3d.json")
    anchorage_artifact = _run_source_artifact(tmp_path, "rebar_anchorage", "rebar_anchorage_source.json", "panel_zone_rebar_anchorage_3d.json")
    clash_verification_artifact = _run_source_artifact(
        tmp_path,
        "clash_verification",
        "clash_verification_source.json",
        "panel_zone_clash_verification_3d.json",
    )

    joint_contract = _run_contract(tmp_path, "joint_geometry", joint_artifact)
    anchorage_contract = _run_contract(tmp_path, "rebar_anchorage", anchorage_artifact)
    clash_verification_contract = _run_contract(tmp_path, "clash_verification", clash_verification_artifact)

    clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint_contract),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage_contract),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification_contract),
            "--out",
            str(clash_artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    clash_payload = _load_json(clash_artifact)
    assert clash_payload["contract_pass"] is True
    assert clash_payload["reason_code"] == "PASS"
    assert clash_payload["summary"]["verification_tier"] == "true_3d_clash_and_anchorage_verified"
    assert clash_payload["source_provenance"]["required_sources_complete"] is True
    assert clash_payload["source_provenance"]["missing_required_sources"] == []

    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    report = tmp_path / "panel_zone_clash_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash_artifact),
            "--out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = _load_json(report)
    assert report_payload["contract_pass"] is True
    assert report_payload["reason_code"] == "PASS"
    assert report_payload["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert report_payload["summary"]["panel_zone_required_sources_complete"] is True
    assert report_payload["checks"]["panel_zone_clash_artifact_3d_verified"] is True
    assert report_payload["checks"]["panel_zone_required_sources_complete"] is True


def test_panel_zone_3d_solver_export_bundle_fixture_stays_unclassified_without_solver_metadata(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(dataset, _load_json(FIXTURE_DIR / "design_optimization_dataset_report.json"))

    joint_artifact = _run_source_artifact(
        tmp_path,
        "joint_geometry",
        "panel_zone_solver_export_bundle.json",
        "panel_zone_joint_geometry_3d.json",
    )
    anchorage_artifact = _run_source_artifact(
        tmp_path,
        "rebar_anchorage",
        "panel_zone_solver_export_bundle.json",
        "panel_zone_rebar_anchorage_3d.json",
    )
    clash_verification_artifact = _run_source_artifact(
        tmp_path,
        "clash_verification",
        "panel_zone_solver_export_bundle.json",
        "panel_zone_clash_verification_3d.json",
    )

    assert _load_json(joint_artifact)["summary"]["source_bundle_mode"] == "nested_solver_export"
    assert _load_json(anchorage_artifact)["summary"]["source_bundle_mode"] == "nested_solver_export"
    assert _load_json(clash_verification_artifact)["summary"]["source_bundle_mode"] == "nested_solver_export"

    joint_contract = _run_contract(tmp_path, "joint_geometry", joint_artifact)
    anchorage_contract = _run_contract(tmp_path, "rebar_anchorage", anchorage_artifact)
    clash_verification_contract = _run_contract(tmp_path, "clash_verification", clash_verification_artifact)

    clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint_contract),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage_contract),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification_contract),
            "--out",
            str(clash_artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    clash_payload = _load_json(clash_artifact)
    assert clash_payload["contract_pass"] is True
    assert clash_payload["summary"]["verification_tier"] == "validated_source_bridge_unclassified"
    assert clash_payload["source_provenance"]["solver_verified_bridge_complete"] is False
    assert clash_payload["source_provenance"]["topology_projected_bridge_complete"] is False


def test_panel_zone_3d_solver_verified_export_bundle_fixture_preserves_solver_bridge_provenance(tmp_path: Path) -> None:
    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(dataset, _load_json(FIXTURE_DIR / "design_optimization_dataset_report.json"))

    joint_artifact = _run_source_artifact(
        tmp_path,
        "joint_geometry",
        "panel_zone_solver_verified_export_bundle.json",
        "panel_zone_joint_geometry_3d.json",
    )
    anchorage_artifact = _run_source_artifact(
        tmp_path,
        "rebar_anchorage",
        "panel_zone_solver_verified_export_bundle.json",
        "panel_zone_rebar_anchorage_3d.json",
    )
    clash_verification_artifact = _run_source_artifact(
        tmp_path,
        "clash_verification",
        "panel_zone_solver_verified_export_bundle.json",
        "panel_zone_clash_verification_3d.json",
    )

    for artifact in (joint_artifact, anchorage_artifact, clash_verification_artifact):
        payload = _load_json(artifact)
        assert payload["summary"]["source_bundle_mode"] == "nested_solver_export"
        assert payload["summary"]["solver_verified"] is True
        assert payload["summary"]["topology_projected"] is False
        assert payload["summary"]["producer_backend"] == "panel_zone_external_solver"
        assert payload["summary"]["instruction_sidecar_evidence_model"] == "direct_solver_export"
        assert payload["summary"]["instruction_sidecar_rebar_delivery_mode"] == "solver_verified_layout_rows"
        assert payload["summary"]["verification_tier"].endswith("_solver_verified_validated_source")

    joint_contract = _run_contract(tmp_path, "joint_geometry", joint_artifact)
    anchorage_contract = _run_contract(tmp_path, "rebar_anchorage", anchorage_artifact)
    clash_verification_contract = _run_contract(tmp_path, "clash_verification", clash_verification_artifact)

    clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint_contract),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage_contract),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification_contract),
            "--out",
            str(clash_artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    clash_payload = _load_json(clash_artifact)
    assert clash_payload["contract_pass"] is True
    assert clash_payload["summary"]["verification_tier"] == "true_3d_clash_and_anchorage_verified"
    assert clash_payload["summary"]["verification_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert clash_payload["source_provenance"]["solver_verified_bridge_complete"] is True
    assert clash_payload["source_provenance"]["topology_projected_bridge_complete"] is False
    assert set(clash_payload["source_provenance"]["source_bundle_modes"].values()) == {"nested_solver_export"}
    assert all(
        str(value).endswith("_solver_verified_validated_source")
        for value in clash_payload["source_provenance"]["source_upstream_verification_tiers"].values()
    )
    assert clash_payload["source_provenance"]["instruction_sidecar_evidence_model"] == "direct_solver_export"
    assert clash_payload["source_provenance"]["instruction_sidecar_rebar_delivery_mode"] == "solver_verified_layout_rows"

    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    report = tmp_path / "panel_zone_clash_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash_artifact),
            "--out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = _load_json(report)
    assert report_payload["contract_pass"] is True
    assert report_payload["reason_code"] == "PASS"
    assert report_payload["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert report_payload["summary"]["panel_zone_solver_verified_bridge_complete"] is True
    assert report_payload["summary"]["panel_zone_topology_projected_bridge_complete"] is False
    assert report_payload["summary"]["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert set(report_payload["summary"]["panel_zone_source_bundle_modes"].values()) == {"nested_solver_export"}


def test_generated_panel_zone_solver_verified_bundle_drives_green_path(tmp_path: Path) -> None:
    bundle = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_export_bundle.py",
            "--joint-geometry-source",
            str(FIXTURE_DIR / "joint_geometry_source.json"),
            "--rebar-anchorage-source",
            str(FIXTURE_DIR / "rebar_anchorage_source.json"),
            "--clash-verification-source",
            str(FIXTURE_DIR / "clash_verification_source.json"),
            "--out",
            str(bundle),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    dataset = tmp_path / "design_optimization_dataset_report.json"
    _write_json(dataset, _load_json(FIXTURE_DIR / "design_optimization_dataset_report.json"))
    joint_artifact = _run_source_artifact(
        tmp_path,
        "joint_geometry",
        str(bundle),
        "panel_zone_joint_geometry_3d.json",
    )
    anchorage_artifact = _run_source_artifact(
        tmp_path,
        "rebar_anchorage",
        str(bundle),
        "panel_zone_rebar_anchorage_3d.json",
    )
    clash_verification_artifact = _run_source_artifact(
        tmp_path,
        "clash_verification",
        str(bundle),
        "panel_zone_clash_verification_3d.json",
    )
    assert _load_json(joint_artifact)["summary"]["solver_verified"] is True
    assert _load_json(anchorage_artifact)["summary"]["solver_verified"] is True
    assert _load_json(clash_verification_artifact)["summary"]["solver_verified"] is True

    joint_contract = _run_contract(tmp_path, "joint_geometry", joint_artifact)
    anchorage_contract = _run_contract(tmp_path, "rebar_anchorage", anchorage_artifact)
    clash_verification_contract = _run_contract(tmp_path, "clash_verification", clash_verification_artifact)

    clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint_contract),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage_contract),
            "--panel-zone-clash-verification-artifact",
            str(clash_verification_contract),
            "--out",
            str(clash_artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    clash_payload = _load_json(clash_artifact)
    assert clash_payload["contract_pass"] is True
    assert clash_payload["source_provenance"]["solver_verified_bridge_complete"] is True
