from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_panel_zone_solver_verified_export_bundle_normalizes_external_row_inputs(tmp_path: Path) -> None:
    out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
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
    assert payload["summary"]["solver_verified"] is True
    assert payload["summary"]["topology_projected"] is False
    assert payload["summary"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["summary"]["verification_tier"] == "solver_verified_3d_source_bundle"
    assert payload["summary"]["instruction_sidecar_evidence_model"] == "direct_solver_export"
    assert payload["summary"]["instruction_sidecar_rebar_delivery_mode"] == "solver_verified_layout_rows"
    assert payload["summary"]["source_row_counts"]["panel_zone_joint_geometry_3d"] == 1
    assert payload["summary"]["source_row_counts"]["panel_zone_rebar_anchorage_3d"] == 1
    assert payload["summary"]["source_row_counts"]["panel_zone_clash_verification_3d"] == 1
    for kind in (
        "panel_zone_joint_geometry_3d",
        "panel_zone_rebar_anchorage_3d",
        "panel_zone_clash_verification_3d",
    ):
        source_payload = payload["panel_zone_3d_results"][kind]
        assert source_payload["contract_pass"] is True
        assert source_payload["summary"]["solver_verified"] is True
        assert source_payload["summary"]["topology_projected"] is False
        assert source_payload["summary"]["source_bundle_mode"] == "nested_solver_export"
        assert source_payload["summary"]["producer_backend"] == "panel_zone_external_solver"
        assert source_payload["summary"]["verification_tier"] == "solver_verified_3d_source"


def test_generate_panel_zone_solver_verified_export_bundle_marks_open_when_required_fields_are_missing(tmp_path: Path) -> None:
    joint = tmp_path / "joint_geometry_source.json"
    anchorage = tmp_path / "rebar_anchorage_source.json"
    clash = tmp_path / "clash_verification_source.json"
    out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    _write_json(joint, {"rows": [{"member_id": "B401"}]})
    _write_json(anchorage, _load_json(FIXTURE_DIR / "rebar_anchorage_source.json"))
    _write_json(clash, _load_json(FIXTURE_DIR / "clash_verification_source.json"))

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_export_bundle.py",
            "--joint-geometry-source",
            str(joint),
            "--rebar-anchorage-source",
            str(anchorage),
            "--clash-verification-source",
            str(clash),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_ROWS_INVALID"
    assert payload["summary"]["required_sources_complete"] is False
    assert payload["summary"]["invalid_source_row_counts"]["panel_zone_joint_geometry_3d"] == 1
    assert payload["panel_zone_3d_results"]["panel_zone_joint_geometry_3d"]["contract_pass"] is False


def test_generate_panel_zone_solver_verified_export_bundle_embeds_member_mapping_sidecar(tmp_path: Path) -> None:
    out = tmp_path / "panel_zone_solver_verified_export_bundle.json"
    member_mapping_sidecar = tmp_path / "member_mapping_sidecar.json"
    _write_json(
        member_mapping_sidecar,
        {
            "mapping_mode": "explicit_member_id_map",
            "rows": [{"source_member_id": "B401", "candidate_member_id": "26705"}],
        },
    )
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
            "--member-mapping-sidecar",
            str(member_mapping_sidecar),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = _load_json(out)
    assert payload["member_mapping_sidecar"]["present"] is True
    assert payload["member_mapping_sidecar"]["mapping_mode"] == "explicit_member_id_map"
    assert payload["member_mapping_sidecar"]["row_count"] == 1
    assert payload["member_mapping_sidecar"]["member_map"] == {"B401": "26705"}
    assert payload["summary"]["member_mapping_sidecar_present"] is True
    assert payload["summary"]["member_mapping_sidecar_row_count"] == 1
