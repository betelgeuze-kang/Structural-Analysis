from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _write_release_policy_inputs(source_dir: Path, registry_summary: dict, registry_accel: dict) -> None:
    _write_json(
        source_dir / "commercial_readiness_report.json",
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
            "inputs": {"forbid_toy_cases": True},
        },
    )
    _write_json(
        source_dir / "real_source_multi_gate_report.json",
        {"contract_pass": True, "checks": {"all_real_source_pass": True, "all_toy_free_pass": True}},
    )
    _write_json(
        source_dir / "nonlinear_frame_engine_report.json",
        {
            "contract_pass": True,
            "checks": {
                "rust_backend_used_pass": True,
                "all_cases_converged": True,
                "drift_p95_pass": True,
                "base_shear_p95_pass": True,
                "top_disp_p95_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "nonlinear_pushover_stress_report.json",
        {
            "contract_pass": True,
            "checks": {
                "all_cases_converged": True,
                "plasticity_triggered_all_cases": True,
                "collapse_path_pass": True,
                "min_plastic_story_count_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "nonlinear_ndtha_stress_report.json",
        {
            "contract_pass": True,
            "checks": {
                "all_cases_converged": True,
                "pdelta_enabled_pass": True,
                "dynamic_reversal_pass": True,
                "rust_backend_used_pass": True,
                "plasticity_triggered_all_cases": True,
                "min_plastic_story_count_pass": True,
            },
        },
    )
    _write_json(
        source_dir / "phase3_megastructure_pipeline_report.json",
        {"contract_pass": True, "checks": {"shell_beam_mix_pass": True, "gpu_strict_pass": True, "real_source_verified": True}},
    )
    _write_json(source_dir / "opensees_topology_report.json", {"contract_pass": True, "checks": {"shell_beam_mix_pass": True}})
    _write_json(source_dir / "scaleout_io_profile_report.json", {"contract_pass": True, "checks": {"gpu_strict_pass": True}})
    _write_json(
        source_dir / "release" / "release_registry.json",
        {
            "contract_pass": True,
            "checks": {"signature_verified_pass": True},
            "summary": registry_summary,
            "registry_body": {"accelerated_coverage_provenance": registry_accel},
        },
    )


def test_freeze_release_snapshot_copies_new_artifacts_and_advanced_coverage(tmp_path: Path) -> None:
    source_dir = tmp_path / "phase1"
    release_dir = source_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    registry_summary = {
        "deployment_model": "engineer_in_the_loop_accelerated_coverage",
        "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
        "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
        "authority_catalog_diff_change_count": 2,
        "authority_catalog_routing_warning_active": True,
        "mgt_export_support_mode": "bounded_patch_subset",
        "mgt_export_direct_patch_change_count": 5,
        "mgt_export_instruction_sidecar_change_count": 7,
        "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=2, detailing=2, rebar=3",
        "mgt_export_rebar_payload_namespace_mode": "material_level_only",
        "mgt_export_rebar_payload_material_level_namespace_present": True,
        "mgt_export_rebar_payload_group_local_namespace_present": False,
        "mgt_export_group_local_rebar_payload_row_count": 0,
        "mgt_export_rebar_direct_patch_eligible_change_count": 0,
        "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=1",
        "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=3",
        "mgt_export_rebar_delivery_mode": "structured_sidecar_only",
        "mgt_export_evidence_model": "direct_patch_plus_structured_sidecar",
        "pbd_dynamic_hinge_refresh_ready": True,
        "pbd_hinge_state_mode": "fema356_recomputed_per_change",
        "pbd_hinge_refresh_reason": "Dynamic hinge refresh artifact is attached.",
        "panel_zone_3d_clash_ready": True,
        "panel_zone_constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
        "panel_zone_constructability_reason": "3D panel-zone clash artifact is attached.",
        "foundation_member_type_present": True,
        "foundation_member_type_count": 9,
        "foundation_optimization_ready": True,
        "foundation_optimization_mode": "active_foundation_member_optimization",
        "foundation_optimization_reason": "Foundation optimization artifact is attached.",
        "wind_tunnel_raw_mapping_ready": True,
        "wind_tunnel_mapping_mode": "raw_hffb_node_pressure_mapping",
        "wind_tunnel_mapping_reason": "Raw wind-tunnel mapping artifact is attached.",
    }
    registry_accel = {
        "deployment_model": "engineer_in_the_loop_accelerated_coverage",
        "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
        "comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
        "comparable_reference_strict_design_opt_cost_smoke": True,
        "authority_catalog_diff_change_count": 2,
        "authority_catalog_routing_warning_active": True,
        "mgt_export_support_mode": "bounded_patch_subset",
        "mgt_export_direct_patch_change_count": 5,
        "mgt_export_instruction_sidecar_change_count": 7,
        "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=2, detailing=2, rebar=3",
        "mgt_export_rebar_payload_namespace_mode": "material_level_only",
        "mgt_export_rebar_payload_material_level_namespace_present": True,
        "mgt_export_rebar_payload_group_local_namespace_present": False,
        "mgt_export_group_local_rebar_payload_row_count": 0,
        "mgt_export_rebar_direct_patch_eligible_change_count": 0,
        "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=1",
        "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=3",
        "mgt_export_rebar_delivery_mode": "structured_sidecar_only",
        "mgt_export_evidence_model": "direct_patch_plus_structured_sidecar",
        "pbd_dynamic_hinge_refresh_ready": True,
        "pbd_hinge_state_mode": "fema356_recomputed_per_change",
        "pbd_hinge_refresh_reason": "Dynamic hinge refresh artifact is attached.",
        "panel_zone_3d_clash_ready": True,
        "panel_zone_constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
        "panel_zone_constructability_reason": "3D panel-zone clash artifact is attached.",
        "foundation_member_type_present": True,
        "foundation_member_type_count": 9,
        "foundation_optimization_ready": True,
        "foundation_optimization_mode": "active_foundation_member_optimization",
        "foundation_optimization_reason": "Foundation optimization artifact is attached.",
        "wind_tunnel_raw_mapping_ready": True,
        "wind_tunnel_mapping_mode": "raw_hffb_node_pressure_mapping",
        "wind_tunnel_mapping_reason": "Raw wind-tunnel mapping artifact is attached.",
    }
    _write_release_policy_inputs(source_dir, registry_summary, registry_accel)

    _write_json(source_dir / "pbd_hinge_refresh_report.json", {"contract_pass": True})
    _write_json(source_dir / "panel_zone_clash_artifact.json", {"contract_pass": True})
    _write_json(source_dir / "panel_zone_clash_report.json", {"contract_pass": True})
    _write_json(source_dir / "wind_tunnel_raw_mapping.json", {"contract_pass": True})
    _write_json(source_dir / "wind_tunnel_raw_mapping_report.json", {"contract_pass": True})
    _write_json(source_dir / "release" / "design_optimization" / "foundation_optimization_artifact.json", {"contract_pass": True})
    _write_json(source_dir / "release" / "design_optimization" / "foundation_optimization_report.json", {"contract_pass": True})
    _write_json(source_dir / "release" / "release_gap_report.json", {"contract_pass": True})
    _write_text(source_dir / "release" / "release_gap_report.md", "# gap report\n")
    _write_json(source_dir / "release" / "committee_review" / "committee_review_package_report.json", {"contract_pass": True})
    _write_text(source_dir / "release" / "signing" / "release_registry.signature.b64", "c2lnbmF0dXJl")

    out = release_dir / "freeze_release_report.json"
    latest = release_dir / "phase3_nightly_latest.json"
    rel_files = [
        "commercial_readiness_report.json",
        "release/release_registry.json",
        "pbd_hinge_refresh_report.json",
        "panel_zone_clash_artifact.json",
        "panel_zone_clash_report.json",
        "wind_tunnel_raw_mapping.json",
        "wind_tunnel_raw_mapping_report.json",
        "release/design_optimization/foundation_optimization_artifact.json",
        "release/design_optimization/foundation_optimization_report.json",
        "release/release_gap_report.json",
        "release/release_gap_report.md",
        "release/committee_review/committee_review_package_report.json",
        "release/signing/release_registry.signature.b64",
    ]
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/freeze_release_snapshot.py",
            "--source-dir",
            str(source_dir),
            "--release-dir",
            str(release_dir),
            "--artifact-files",
            ",".join(rel_files),
            "--latest-pointer",
            str(latest),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["pbd_dynamic_hinge_refresh_ready"] is True
    assert report["panel_zone_3d_clash_ready"] is True
    assert report["foundation_optimization_ready"] is True
    assert report["foundation_member_type_count"] == 9
    assert report["wind_tunnel_raw_mapping_ready"] is True
    assert report["wind_tunnel_mapping_mode"] == "raw_hffb_node_pressure_mapping"

    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_payload["pbd_dynamic_hinge_refresh_ready"] is True
    assert latest_payload["panel_zone_3d_clash_ready"] is True
    assert latest_payload["foundation_optimization_ready"] is True
    assert latest_payload["wind_tunnel_raw_mapping_ready"] is True

    snapshot_dir = Path(latest_payload["path"])
    manifest = json.loads((snapshot_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    manifest_files = {entry["file"] for entry in manifest["files"]}
    assert set(rel_files).issubset(manifest_files)
    optional_files = {entry["file"]: entry for entry in manifest["optional_files"]}
    assert optional_files["panel_zone_joint_geometry_3d.json"]["present"] is False
    assert optional_files["panel_zone_rebar_anchorage_3d.json"]["present"] is False
    assert optional_files["panel_zone_clash_verification_3d.json"]["present"] is False
    assert optional_files["panel_zone_joint_geometry_3d_contract.json"]["present"] is False
    assert optional_files["panel_zone_rebar_anchorage_3d_contract.json"]["present"] is False
    assert optional_files["panel_zone_clash_verification_3d_contract.json"]["present"] is False
    assert manifest["accelerated_coverage"]["pbd_dynamic_hinge_refresh_ready"] is True
    assert manifest["accelerated_coverage"]["panel_zone_3d_clash_ready"] is True
    assert manifest["accelerated_coverage"]["foundation_optimization_ready"] is True
    assert manifest["accelerated_coverage"]["wind_tunnel_raw_mapping_ready"] is True

    for rel_path in rel_files:
        assert (snapshot_dir / rel_path).exists(), rel_path


def test_freeze_release_snapshot_records_optional_panel_zone_3d_source_contract_coverage(tmp_path: Path) -> None:
    source_dir = tmp_path / "phase1"
    release_dir = source_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    registry_summary = {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}
    registry_accel = {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}
    _write_release_policy_inputs(source_dir, registry_summary, registry_accel)
    _write_json(
        source_dir / "commercial_readiness_report.json",
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
            "inputs": {"forbid_toy_cases": True},
        },
    )
    _write_json(source_dir / "release" / "release_registry.json", {"contract_pass": True, "checks": {"signature_verified_pass": True}})
    _write_json(source_dir / "panel_zone_joint_geometry_3d_contract.json", {"contract_pass": True, "source_kind": "panel_zone_joint_geometry_3d"})

    out = release_dir / "freeze_release_report.json"
    latest = release_dir / "phase3_nightly_latest.json"
    cmd = [
        sys.executable,
        "implementation/phase1/freeze_release_snapshot.py",
        "--source-dir",
        str(source_dir),
        "--release-dir",
        str(release_dir),
        "--artifact-files",
        "commercial_readiness_report.json,release/release_registry.json",
        "--latest-pointer",
        str(latest),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    manifest = json.loads((Path(json.loads(latest.read_text(encoding="utf-8"))["path"]) / "snapshot_manifest.json").read_text(encoding="utf-8"))
    optional = {entry["file"]: entry for entry in manifest["optional_files"]}
    assert optional["panel_zone_joint_geometry_3d_contract.json"]["present"] is True
    assert optional["panel_zone_joint_geometry_3d_contract.json"]["optional"] is True
    assert (Path(json.loads(latest.read_text(encoding="utf-8"))["path"]) / "panel_zone_joint_geometry_3d_contract.json").exists()
    assert optional["panel_zone_rebar_anchorage_3d_contract.json"]["present"] is False
    assert optional["panel_zone_clash_verification_3d_contract.json"]["present"] is False


def test_freeze_release_snapshot_keeps_open_optional_panel_zone_source_artifact(tmp_path: Path) -> None:
    source_dir = tmp_path / "phase1"
    release_dir = source_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    registry_summary = {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}
    registry_accel = {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}
    _write_release_policy_inputs(source_dir, registry_summary, registry_accel)
    _write_json(
        source_dir / "commercial_readiness_report.json",
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
            "inputs": {"forbid_toy_cases": True},
        },
    )
    _write_json(source_dir / "release" / "release_registry.json", {"contract_pass": True, "checks": {"signature_verified_pass": True}})
    _write_json(
        source_dir / "panel_zone_joint_geometry_3d.json",
        {
            "contract_pass": False,
            "reason_code": "ERR_SOURCE_INPUT_MISSING",
            "source_kind": "panel_zone_joint_geometry_3d",
        },
    )

    out = release_dir / "freeze_release_report.json"
    latest = release_dir / "phase3_nightly_latest.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/freeze_release_snapshot.py",
            "--source-dir",
            str(source_dir),
            "--release-dir",
            str(release_dir),
            "--artifact-files",
            "commercial_readiness_report.json,release/release_registry.json",
            "--latest-pointer",
            str(latest),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    snapshot_dir = Path(json.loads(latest.read_text(encoding="utf-8"))["path"])
    manifest = json.loads((snapshot_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    optional = {entry["file"]: entry for entry in manifest["optional_files"]}
    assert optional["panel_zone_joint_geometry_3d.json"]["present"] is True
    assert optional["panel_zone_joint_geometry_3d.json"]["json_gate_pass"] is False
    assert (snapshot_dir / "panel_zone_joint_geometry_3d.json").exists()


def test_freeze_release_snapshot_uses_panel_fixture_contracts_in_manifest(tmp_path: Path) -> None:
    source_dir = tmp_path / "phase1"
    release_dir = source_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    registry_summary = {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}
    registry_accel = {"deployment_model": "engineer_in_the_loop_accelerated_coverage"}
    _write_release_policy_inputs(source_dir, registry_summary, registry_accel)
    _write_json(source_dir / "pbd_hinge_refresh_report.json", {"contract_pass": True})
    _write_json(source_dir / "panel_zone_clash_artifact.json", {"contract_pass": True})
    _write_json(source_dir / "panel_zone_clash_report.json", {"contract_pass": True})

    def _run_panel_source(source_kind: str, source_fixture: str, out_name: str) -> Path:
        out = source_dir / out_name
        proc = subprocess.run(
            [
                sys.executable,
                f"implementation/phase1/generate_panel_zone_{source_kind}_3d_source.py",
                "--design-optimization-dataset",
                str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
                "--source-input",
                str(FIXTURE_DIR / source_fixture),
                "--out",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return out

    def _run_panel_contract(source_kind: str, source_artifact: Path) -> Path:
        contract_name = {
            "joint_geometry": "panel_zone_joint_geometry_3d_contract.json",
            "rebar_anchorage": "panel_zone_rebar_anchorage_3d_contract.json",
            "clash_verification": "panel_zone_clash_verification_3d_contract.json",
        }[source_kind]
        out = source_dir / contract_name
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
        return out

    joint_source = _run_panel_source("joint_geometry", "joint_geometry_source.json", "panel_zone_joint_geometry_3d.json")
    anchorage_source = _run_panel_source("rebar_anchorage", "rebar_anchorage_source.json", "panel_zone_rebar_anchorage_3d.json")
    clash_source = _run_panel_source("clash_verification", "clash_verification_source.json", "panel_zone_clash_verification_3d.json")
    _run_panel_contract("joint_geometry", joint_source)
    _run_panel_contract("rebar_anchorage", anchorage_source)
    _run_panel_contract("clash_verification", clash_source)

    out = release_dir / "freeze_release_report.json"
    latest = release_dir / "phase3_nightly_latest.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/freeze_release_snapshot.py",
            "--source-dir",
            str(source_dir),
            "--release-dir",
            str(release_dir),
            "--artifact-files",
            "commercial_readiness_report.json,release/release_registry.json,pbd_hinge_refresh_report.json,panel_zone_clash_artifact.json,panel_zone_clash_report.json",
            "--latest-pointer",
            str(latest),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    snapshot_dir = Path(latest_payload["path"])
    manifest = json.loads((snapshot_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    optional = {entry["file"]: entry for entry in manifest["optional_files"]}
    assert optional["panel_zone_joint_geometry_3d.json"]["present"] is True
    assert optional["panel_zone_rebar_anchorage_3d.json"]["present"] is True
    assert optional["panel_zone_clash_verification_3d.json"]["present"] is True
    assert optional["panel_zone_joint_geometry_3d_contract.json"]["present"] is True
    assert optional["panel_zone_rebar_anchorage_3d_contract.json"]["present"] is True
    assert optional["panel_zone_clash_verification_3d_contract.json"]["present"] is True
    assert optional["panel_zone_joint_geometry_3d.json"]["json_gate_pass"] is True
    assert optional["panel_zone_rebar_anchorage_3d.json"]["json_gate_pass"] is True
    assert optional["panel_zone_clash_verification_3d.json"]["json_gate_pass"] is True
    assert optional["panel_zone_joint_geometry_3d_contract.json"]["json_gate_pass"] is True
    assert optional["panel_zone_rebar_anchorage_3d_contract.json"]["json_gate_pass"] is True
    assert optional["panel_zone_clash_verification_3d_contract.json"]["json_gate_pass"] is True
    assert (snapshot_dir / "panel_zone_joint_geometry_3d.json").exists()
    assert (snapshot_dir / "panel_zone_rebar_anchorage_3d.json").exists()
    assert (snapshot_dir / "panel_zone_clash_verification_3d.json").exists()
    assert (snapshot_dir / "panel_zone_joint_geometry_3d_contract.json").exists()
    assert (snapshot_dir / "panel_zone_rebar_anchorage_3d_contract.json").exists()
    assert (snapshot_dir / "panel_zone_clash_verification_3d_contract.json").exists()
