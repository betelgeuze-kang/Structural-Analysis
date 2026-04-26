from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    ("source_kind", "expected_kind"),
    [
        ("joint_geometry", "panel_zone_joint_geometry_3d"),
        ("rebar_anchorage", "panel_zone_rebar_anchorage_3d"),
        ("clash_verification", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_contract_validates_matching_source_artifact(
    tmp_path: Path,
    source_kind: str,
    expected_kind: str,
) -> None:
    source_artifact = tmp_path / f"{source_kind}.json"
    _write_json(
        source_artifact,
        {
            "contract_pass": True,
            "source_kind": expected_kind,
            "verification_tier": f"{expected_kind}_raw_source",
        },
    )
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

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["source_kind"] == expected_kind
    assert payload["summary"]["source_status"] == "validated"
    assert payload["summary"]["source_kind_match"] is True
    assert payload["summary"]["verification_tier"] == f"{expected_kind}_contract_validated"
    assert payload["source_provenance"]["source_artifact_present"] is True
    assert payload["source_provenance"]["source_artifact_contract_pass"] is True
    assert payload["source_provenance"]["source_kind_match"] is True


def test_panel_zone_3d_source_contract_uses_open_skeleton_when_source_is_missing(tmp_path: Path) -> None:
    out = tmp_path / "missing_contract.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_contract.py",
            "--source-kind",
            "joint_geometry",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_ARTIFACT_MISSING"
    assert payload["summary"]["source_status"] == "open"
    assert payload["source_provenance"]["source_artifact_present"] is False
    assert payload["source_provenance"]["required_source_missing"] is True


def test_panel_zone_3d_source_contract_rejects_kind_mismatch(tmp_path: Path) -> None:
    source_artifact = tmp_path / "wrong_kind_source.json"
    _write_json(
        source_artifact,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_rebar_anchorage_3d",
        },
    )
    out = tmp_path / "mismatch_contract.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_contract.py",
            "--source-kind",
            "joint_geometry",
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

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_KIND_MISMATCH"
    assert payload["source_provenance"]["source_kind_match"] is False


def test_panel_zone_3d_source_contract_carries_upstream_source_coverage_provenance(tmp_path: Path) -> None:
    source_artifact = tmp_path / "joint_geometry_source.json"
    _write_json(
        source_artifact,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "summary": {
                "verification_tier": "panel_zone_joint_geometry_3d_validated_source",
            },
            "source_provenance": {
                "source_row_count": 3,
                "valid_source_row_count": 2,
                "invalid_source_row_count": 1,
                "candidate_member_count": 4,
                "overlap_member_count": 2,
                "candidate_scan_mode": "npz_full",
                "topology_capable_input": True,
                "source_bundle_mode": "nested_solver_export",
                "required_source_fields": ["joint_id"],
                "source_input_path": "tests/fixtures/panel_zone_3d/joint_geometry_source.json",
                "candidate_member_ids_head": ["B401", "B402"],
                "source_member_ids_head": ["B401", "B999"],
                "overlap_member_ids_head": ["B401", "B402"],
            },
        },
    )
    out = tmp_path / "joint_geometry_contract.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_contract.py",
            "--source-kind",
            "joint_geometry",
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

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["source_provenance"]["source_row_count"] == 3
    assert payload["source_provenance"]["valid_source_row_count"] == 2
    assert payload["source_provenance"]["invalid_source_row_count"] == 1
    assert payload["source_provenance"]["candidate_member_count"] == 4
    assert payload["source_provenance"]["overlap_member_count"] == 2
    assert payload["source_provenance"]["candidate_scan_mode"] == "npz_full"
    assert payload["source_provenance"]["topology_capable_input"] is True
    assert payload["source_provenance"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["source_provenance"]["source_input_path"].endswith("joint_geometry_source.json")
    assert payload["source_provenance"]["required_source_fields"] == ["joint_id"]
    assert payload["summary"]["source_row_count"] == 3
    assert payload["summary"]["valid_source_row_count"] == 2
    assert payload["summary"]["overlap_member_count"] == 2
    assert payload["summary"]["candidate_scan_mode"] == "npz_full"
    assert payload["summary"]["topology_capable_input"] is True
    assert payload["summary"]["source_bundle_mode"] == "nested_solver_export"
    assert payload["summary"]["upstream_verification_tier"] == "panel_zone_joint_geometry_3d_validated_source"
    assert payload["checks"]["source_overlap_present"] is True


def test_panel_zone_3d_source_contract_preserves_member_mapping_sidecar_surface(tmp_path: Path) -> None:
    source_artifact = tmp_path / "joint_geometry_source.json"
    _write_json(
        source_artifact,
        {
            "contract_pass": True,
            "source_kind": "panel_zone_joint_geometry_3d",
            "summary": {
                "verification_tier": "panel_zone_joint_geometry_3d_solver_verified_validated_source",
            },
            "source_provenance": {
                "member_mapping_sidecar_present": True,
                "member_mapping_sidecar_path": "/tmp/member_mapping_sidecar.json",
                "member_mapping_sidecar_mode": "explicit_member_id_map",
                "member_mapping_sidecar_row_count": 1,
                "member_mapping_sidecar_applied_row_count": 1,
                "member_mapping_sidecar_unmapped_source_member_count": 0,
            },
        },
    )
    out = tmp_path / "joint_geometry_contract.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_3d_source_contract.py",
            "--source-kind",
            "joint_geometry",
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

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source_provenance"]["member_mapping_sidecar_present"] is True
    assert payload["source_provenance"]["member_mapping_sidecar_mode"] == "explicit_member_id_map"
    assert payload["source_provenance"]["member_mapping_sidecar_row_count"] == 1
    assert payload["source_provenance"]["member_mapping_sidecar_applied_row_count"] == 1
    assert payload["summary"]["member_mapping_sidecar_present"] is True
    assert payload["summary"]["member_mapping_sidecar_mode"] == "explicit_member_id_map"
    assert payload["summary"]["member_mapping_sidecar_row_count"] == 1
    assert payload["summary"]["member_mapping_sidecar_applied_row_count"] == 1


@pytest.mark.parametrize(
    ("entrypoint", "source_kind"),
    [
        ("implementation/phase1/generate_panel_zone_joint_geometry_3d_contract.py", "panel_zone_joint_geometry_3d"),
        ("implementation/phase1/generate_panel_zone_rebar_anchorage_3d_contract.py", "panel_zone_rebar_anchorage_3d"),
        ("implementation/phase1/generate_panel_zone_clash_verification_3d_contract.py", "panel_zone_clash_verification_3d"),
    ],
)
def test_panel_zone_3d_source_contract_entrypoints_emit_open_skeleton_when_missing(
    tmp_path: Path,
    entrypoint: str,
    source_kind: str,
) -> None:
    out = tmp_path / f"{source_kind}.json"
    proc = subprocess.run(
        [
            sys.executable,
            entrypoint,
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source_kind"] == source_kind
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_ARTIFACT_MISSING"
    assert payload["summary"]["source_status"] == "open"
