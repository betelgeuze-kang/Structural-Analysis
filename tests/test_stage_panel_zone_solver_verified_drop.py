from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_stage_panel_zone_solver_verified_drop_stages_manifested_raw_sources(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    out = tmp_path / "stage_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / "drop_package"),
            "--inbox-dir",
            str(inbox),
            "--clean",
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
    assert payload["artifacts"]["manifest"] == str(inbox / "panel_zone_handoff_manifest.json")
    assert (inbox / "joint_geometry.json").exists()
    assert (inbox / "rebar_anchorage.json").exists()
    assert (inbox / "clash_verification.json").exists()
    manifest = _load_json(inbox / "panel_zone_handoff_manifest.json")
    assert manifest["source_origin_class"] == "fixture_sample"
    assert manifest["inputs"]["joint_geometry_source"] == "joint_geometry.json"
    assert manifest["inputs"]["rebar_anchorage_source"] == "rebar_anchorage.json"
    assert manifest["inputs"]["clash_verification_source"] == "clash_verification.json"


def test_stage_panel_zone_solver_verified_drop_stages_bundle_input(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    out = tmp_path / "stage_report.json"
    bundle = FIXTURE_DIR / "panel_zone_solver_verified_export_bundle.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--solver-verified-bundle",
            str(bundle),
            "--inbox-dir",
            str(inbox),
            "--clean",
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
    assert payload["artifacts"]["bundle"] == str(inbox / "panel_zone_solver_verified_export_bundle.json")
    assert payload["artifacts"]["manifest"] == str(inbox / "panel_zone_handoff_manifest.json")
    assert (inbox / "panel_zone_solver_verified_export_bundle.json").exists()
    manifest = _load_json(inbox / "panel_zone_handoff_manifest.json")
    assert manifest["source_origin_class"] == "unclassified_external_source"
    assert manifest["inputs"]["solver_verified_bundle"] == "panel_zone_solver_verified_export_bundle.json"
    assert payload["summary"]["source_origin_class"] == "unclassified_external_source"


def test_stage_panel_zone_solver_verified_drop_preserves_trusted_manifest_origin(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    out = tmp_path / "stage_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / "trusted_drop_package"),
            "--inbox-dir",
            str(inbox),
            "--clean",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    manifest = _load_json(inbox / "panel_zone_handoff_manifest.json")
    assert payload["contract_pass"] is True
    assert payload["summary"]["source_origin_class"] == "trusted_external_solver_source"
    assert manifest["source_origin_class"] == "trusted_external_solver_source"
    assert payload["artifacts"]["member_mapping_sidecar"] == str(inbox / "member_mapping_sidecar.json")
    assert manifest["inputs"]["member_mapping_sidecar"] == "member_mapping_sidecar.json"
    assert (inbox / "member_mapping_sidecar.json").exists()
