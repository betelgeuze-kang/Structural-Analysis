from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import implementation.phase1.generate_committee_review_package as committee_module
from implementation.phase1.prepare_external_validation_submission import _build_bundle
from tests.test_foundation_realish_fixture import (
    _run_dataset_fixture,
    _run_foundation_artifact_and_report,
    _run_parser_fixture,
)
from tests.test_external_validation_summary_extensions import _summary as _external_summary_template
from tests.test_panel_zone_3d_sample_green_path import (
    FIXTURE_DIR as PANEL_FIXTURE_DIR,
    _load_json as _load_panel_json,
    _run_contract,
    _run_source_artifact,
    _write_json as _write_panel_json,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_release_gap_with_panel_and_foundation_fixtures(
    tmp_path: Path,
    *,
    panel_source_fixture: str | None = None,
) -> tuple[Path, Path]:
    model_out, midas_report = _run_parser_fixture(tmp_path)
    foundation_dataset, foundation_npz = _run_dataset_fixture(tmp_path, model_path=model_out)
    _run_foundation_artifact_and_report(
        tmp_path=tmp_path,
        dataset_out=foundation_dataset,
        npz_out=foundation_npz,
        model_path=model_out,
    )
    foundation_report = tmp_path / "foundation_optimization_report.json"

    panel_dataset = tmp_path / "panel_dataset.json"
    _write_panel_json(panel_dataset, _load_panel_json(PANEL_FIXTURE_DIR / "design_optimization_dataset_report.json"))
    joint_source_fixture = panel_source_fixture or "joint_geometry_source.json"
    anchorage_source_fixture = panel_source_fixture or "rebar_anchorage_source.json"
    clash_source_fixture = panel_source_fixture or "clash_verification_source.json"

    joint_artifact = _run_source_artifact(tmp_path, "joint_geometry", joint_source_fixture, "panel_zone_joint_geometry_3d.json")
    anchorage_artifact = _run_source_artifact(tmp_path, "rebar_anchorage", anchorage_source_fixture, "panel_zone_rebar_anchorage_3d.json")
    clash_source_artifact = _run_source_artifact(
        tmp_path,
        "clash_verification",
        clash_source_fixture,
        "panel_zone_clash_verification_3d.json",
    )
    joint_contract = _run_contract(tmp_path, "joint_geometry", joint_artifact)
    anchorage_contract = _run_contract(tmp_path, "rebar_anchorage", anchorage_artifact)
    clash_contract = _run_contract(tmp_path, "clash_verification", clash_source_artifact)

    panel_clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(panel_dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint_contract),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage_contract),
            "--panel-zone-clash-verification-artifact",
            str(clash_contract),
            "--out",
            str(panel_clash_artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    pbd_package = tmp_path / "pbd_review_package_report.json"
    _write_json(
        pbd_package,
        {
            "contract_pass": True,
            "summary": {
                "response_storage": "npz_external+inline_summary",
                "case_metrics_npz_case_count": 11,
            },
            "artifacts": {
                "hinge_proxy_3d_png": "hinge_proxy_3d.png",
            },
        },
    )
    panel_report = tmp_path / "panel_zone_clash_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(panel_dataset),
            "--pbd-review-package",
            str(pbd_package),
            "--panel-zone-clash-artifact",
            str(panel_clash_artifact),
            "--out",
            str(panel_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    pbd_hinge = tmp_path / "pbd_hinge_refresh.json"
    wind_raw_mapping = tmp_path / "wind_raw_mapping.json"
    gap_report = tmp_path / "release_gap_report.json"
    gap_markdown = tmp_path / "release_gap_report.md"

    _write_json(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write_json(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write_json(
        ci,
        {
            "contract_pass": True,
            "all_pass": True,
            "midas_section_library_summary_line": "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3",
            "midas_kds_geometry_bridge_summary_line": "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0",
            "midas_kds_geometry_bridge_load_crosswalk_summary_line": "load_crosswalk=12/12 PASS",
            "midas_kds_geometry_bridge_load_crosswalk_count": 12,
            "midas_kds_geometry_bridge_load_crosswalk_expected": 12,
            "midas_kds_geometry_bridge_load_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_load_crosswalk_pass": True,
            "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": "semantic_crosswalk=12/12 PASS",
            "midas_kds_geometry_bridge_semantic_crosswalk_count": 12,
            "midas_kds_geometry_bridge_semantic_crosswalk_expected": 12,
            "midas_kds_geometry_bridge_semantic_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_semantic_crosswalk_pass": True,
            "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": "full_member_crosswalk=242/242 PASS",
            "midas_kds_geometry_bridge_full_member_crosswalk_count": 242,
            "midas_kds_geometry_bridge_full_member_crosswalk_expected": 242,
            "midas_kds_geometry_bridge_full_member_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_full_member_crosswalk_pass": True,
            "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": "full_section_crosswalk=200/200 PASS",
            "midas_kds_geometry_bridge_full_section_crosswalk_count": 200,
            "midas_kds_geometry_bridge_full_section_crosswalk_expected": 200,
            "midas_kds_geometry_bridge_full_section_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_full_section_crosswalk_pass": True,
            "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": "full_load_crosswalk=51/51 PASS",
            "midas_kds_geometry_bridge_full_load_crosswalk_count": 51,
            "midas_kds_geometry_bridge_full_load_crosswalk_expected": 51,
            "midas_kds_geometry_bridge_full_load_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_full_load_crosswalk_pass": True,
            "midas_loadcomb_roundtrip_summary_line": "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3",
            "solver_breadth_summary_line": "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate",
            "material_constitutive_summary_line": "Material constitutive gate: PASS | concrete_damage=yes(matrix=10/10,max=1.000) | cyclic_degradation=yes(matrix=8/8,residual_max=1.914%) | bond_interface=yes(matrix=11/11,bond_max=0.980) | matrix=29/29",
            "steel_composite_constitutive_gate_report": {
                "contract_pass": False,
                "summary_line": "Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks",
            },
            "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
            "contact_readiness_summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | schema=yes | solver=yes(ratio=0.994,max_force=6.52235N) | whitebox=yes(err=0.0048) | structural_contact=interface_compression_surrogate",
            "structural_contact_summary_line": "Structural contact readiness: PASS | bounded_contact=yes | impl=6/6 | validated=6/6 | ready=6/6 | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2 | partial_only=none | missing=none",
            "foundation_soil_link_summary_line": "Foundation/soil link: PASS | foundation_members=76 | optimized_groups=2 | ssi=yes | soil_tunnel=yes | impedance_schema=yes | links=6(bearing_bilinear,compression_only_penalty,coulomb_friction,kelvin_voigt_pounding,normal_gap_unilateral,uplift_seat_unilateral) | foundation_support=4(p-y,pile_head,q-z,t-z) | devices=5(friction_pendulum,lead_rubber_bearing,tmd,viscoelastic_damper,viscous_damper) | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2",
            "support_search_summary_line": "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21",
            "surface_interaction_benchmark_summary_line": "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4",
            "midas_interoperability_summary_line": "MIDAS interoperability/export readiness: PASS | seeds=3/3 | patterns=3/3 | preview=3/3 | roundtrip=3/3 exact_entry_row_min=1.00 | bounded_subset=editor_seed+raw_recovery+preview_roundtrip | limits=solver_ready_reconstruction_pending, normalized_factor_maps_pending, summary_grade_preview_only, primitive_load_cards_pending",
            "load_combination_engine_report": {
                "contract_pass": True,
                "summary_line": "Load-combination engine gate: PASS | combos=8 | families=4 | source=model.loads",
            },
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {},
            "frontend_payload": {},
        },
    )
    _write_json(static, {"pass": True})
    _write_json(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write_json(committee, {"metrics": {}})
    _write_json(
        pbd_hinge,
        {
            "contract_pass": False,
            "reason": "proxy hinge visualization remains attached",
            "summary": {"hinge_state_mode": "proxy_only_hinge_visualization"},
        },
    )
    _write_json(
        wind_raw_mapping,
        {
            "contract_pass": False,
            "reason": "raw wind mapping fixture is not attached in this committee regression",
            "summary": {"mapping_mode": "semantic_pressure_binding_only"},
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_release_gap_report.py",
            "--nightly-release",
            str(nightly),
            "--ci-gate",
            str(ci),
            "--static-validation",
            str(static),
            "--freeze-report",
            str(freeze),
            "--promotion-report",
            str(promotion),
            "--commercial-readiness",
            str(commercial),
            "--global-authority",
            str(authority),
            "--hip-kernel-smoke",
            str(hip),
            "--midas-conversion",
            str(midas_report),
            "--construction-sequence",
            str(construction),
            "--flexible-diaphragm",
            str(diaphragm),
            "--repro-version-lock",
            str(repro),
            "--release-registry",
            str(registry),
            "--kds-compliance",
            str(kds),
            "--solver-hip-e2e",
            str(solver_hip),
            "--rc-benchmark-lock",
            str(rc),
            "--quality-mgt-corpus",
            str(quality),
            "--committee-summary",
            str(committee),
            "--pbd-package",
            str(pbd_package),
            "--design-opt-dataset-report",
            str(foundation_dataset),
            "--pbd-hinge-refresh-report",
            str(pbd_hinge),
            "--panel-zone-clash-report",
            str(panel_report),
            "--foundation-optimization-report",
            str(foundation_report),
            "--wind-raw-mapping-report",
            str(wind_raw_mapping),
            "--out-json",
            str(gap_report),
            "--out-md",
            str(gap_markdown),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return gap_report, pbd_package


def _run_committee_package_with_panel_and_foundation_fixtures(
    tmp_path: Path,
    monkeypatch,
    *,
    panel_source_fixture: str | None = None,
) -> tuple[Path, Path]:
    gap_report, pbd_package = _run_release_gap_with_panel_and_foundation_fixtures(
        tmp_path,
        panel_source_fixture=panel_source_fixture,
    )

    pbd_metrics = tmp_path / "pbd_metrics.json"
    ndtha_stress = tmp_path / "ndtha_stress.json"
    ndtha_residual = tmp_path / "ndtha_residual.json"
    wind = tmp_path / "wind.json"
    ssi = tmp_path / "ssi.json"
    damper = tmp_path / "damper.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    release_registry = tmp_path / "release_registry.json"
    kds = tmp_path / "kds_summary.json"
    nightly = tmp_path / "nightly.json"
    promotion = tmp_path / "promotion.json"
    ci = tmp_path / "ci.json"
    authority_report = tmp_path / "authority_report.json"
    authority_catalog = tmp_path / "authority_catalog.json"
    design_opt_long = tmp_path / "design_opt_long.json"
    design_opt_cost = tmp_path / "design_opt_cost.json"
    out_dir = tmp_path / "committee_review"
    external_benchmark_submission_readiness = tmp_path / "external_benchmark_submission_readiness.json"
    external_benchmark_kickoff_dir = tmp_path / "external_benchmark_kickoff"
    external_benchmark_execution_manifest = (
        external_benchmark_kickoff_dir / "external_benchmark_execution_manifest.json"
    )
    external_benchmark_execution_status_manifest = (
        external_benchmark_kickoff_dir / "external_benchmark_execution_status_manifest.json"
    )
    external_benchmark_batch_job_report = (
        external_benchmark_kickoff_dir / "external_benchmark_batch_job_report.json"
    )

    _write_json(
        pbd_metrics,
        {
            "earthquake_case_count": 1,
            "drift_envelope_max_pct": 0.92,
            "drift_p95_max_pct": 0.88,
            "speedup_vs_estimate": 2.0,
            "energy_balance_relative_error_ref": 0.01,
            "residual_drift_pct_max_abs": 0.18,
        },
    )
    _write_json(
        ndtha_stress,
        {
            "summary": {
                "residual_pre_settle_top_displacement_m_max_abs": 0.01,
                "residual_pre_settle_drift_ratio_pct_max_abs": 0.1,
            }
        },
    )
    _write_json(
        ndtha_residual,
        {
            "contract_pass": True,
            "summary": {
                "residual_top_displacement_m_max_abs": 0.01,
                "residual_drift_ratio_pct_max_abs": 0.1,
                "fallback_rate": 0.0,
            },
            "checks": {"recommended_drift_pass": True},
            "residual_case_rows": [],
        },
    )
    _write_json(
        wind,
        {
            "contract_pass": True,
            "summary": {
                "duration_hours": 1.0,
                "load_reversal_count": 2,
                "residual_pre_settle_drift_pct_max_abs": 0.1,
                "residual_drift_pct_max_abs": 0.05,
            },
        },
    )
    _write_json(
        ssi,
        {
            "contract_pass": True,
            "summary": {
                "nonlinear_ratio_span": 0.1,
                "fixed_residual_drift_pct_max_abs": 0.05,
                "ssi_residual_drift_pct_max_abs": 0.05,
            },
        },
    )
    _write_json(
        damper,
        {
            "contract_pass": True,
            "summary": {
                "waveform_corr_min": 0.99,
                "phase_error_ms_max": 3.0,
            },
        },
    )
    for path in [construction, diaphragm, repro, kds, nightly, promotion]:
        _write_json(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "frontend_payload": {}})
    _write_json(
        release_registry,
        {
            "contract_pass": True,
            "summary": {
                "signing_algorithm": "ed25519",
                "artifact_count": 11,
                "project_registry_artifact_count": 8,
                "project_registry_approval_count": 2,
                "project_registry_package_sha256": "abc123pkg",
                "project_registry_package_bytes": 4096,
            },
            "checks": {
                "signature_verified_pass": True,
                "project_registry_signature_verified_pass": True,
            },
            "signature": {
                "public_key_path": str(tmp_path / "release_registry_ed25519.pub.pem"),
                "signature_out": str(tmp_path / "release_registry.signature.b64"),
            },
            "artifacts": {
                "project_registry_report": str(tmp_path / "project_registry.json"),
                "project_package_zip": str(tmp_path / "project_package.zip"),
                "project_registry_signature": str(tmp_path / "project_registry.signature.b64"),
            },
        },
    )
    _write_json(
        ci,
        {
            "all_pass": True,
            "midas_section_library_summary_line": "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3",
            "midas_kds_geometry_bridge_summary_line": "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0",
            "midas_kds_geometry_bridge_load_crosswalk_summary_line": "load_crosswalk=12/12 PASS",
            "midas_kds_geometry_bridge_load_crosswalk_count": 12,
            "midas_kds_geometry_bridge_load_crosswalk_expected": 12,
            "midas_kds_geometry_bridge_load_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_load_crosswalk_pass": True,
            "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": "semantic_crosswalk=12/12 PASS",
            "midas_kds_geometry_bridge_semantic_crosswalk_count": 12,
            "midas_kds_geometry_bridge_semantic_crosswalk_expected": 12,
            "midas_kds_geometry_bridge_semantic_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_semantic_crosswalk_pass": True,
            "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": "full_member_crosswalk=242/242 PASS",
            "midas_kds_geometry_bridge_full_member_crosswalk_count": 242,
            "midas_kds_geometry_bridge_full_member_crosswalk_expected": 242,
            "midas_kds_geometry_bridge_full_member_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_full_member_crosswalk_pass": True,
            "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": "full_section_crosswalk=200/200 PASS",
            "midas_kds_geometry_bridge_full_section_crosswalk_count": 200,
            "midas_kds_geometry_bridge_full_section_crosswalk_expected": 200,
            "midas_kds_geometry_bridge_full_section_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_full_section_crosswalk_pass": True,
            "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": "full_load_crosswalk=51/51 PASS",
            "midas_kds_geometry_bridge_full_load_crosswalk_count": 51,
            "midas_kds_geometry_bridge_full_load_crosswalk_expected": 51,
            "midas_kds_geometry_bridge_full_load_crosswalk_status": "PASS",
            "midas_kds_geometry_bridge_full_load_crosswalk_pass": True,
            "midas_loadcomb_roundtrip_summary_line": "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3",
            "solver_breadth_summary_line": "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate",
            "material_constitutive_summary_line": "Material constitutive gate: PASS | concrete_damage=yes(matrix=10/10,max=1.000) | cyclic_degradation=yes(matrix=8/8,residual_max=1.914%) | bond_interface=yes(matrix=11/11,bond_max=0.980) | matrix=29/29",
            "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
            "contact_readiness_summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | schema=yes | solver=yes(ratio=0.994,max_force=6.52235N) | whitebox=yes(err=0.0048) | structural_contact=interface_compression_surrogate",
            "surface_interaction_benchmark_summary_line": "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4",
            "midas_interoperability_summary_line": "MIDAS interoperability/export readiness: PASS | seeds=3/3 | patterns=3/3 | preview=3/3 | roundtrip=3/3 exact_entry_row_min=1.00 | bounded_subset=editor_seed+raw_recovery+preview_roundtrip | limits=solver_ready_reconstruction_pending, normalized_factor_maps_pending, summary_grade_preview_only, primitive_load_cards_pending",
            "load_combination_engine_report": {
                "contract_pass": True,
                "summary_line": "Load-combination engine gate: PASS | combos=8 | families=4 | source=model.loads",
            },
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "frontend_payload": {},
        },
    )
    _write_json(
        authority_report,
        {
            "contract_pass": True,
            "summary": {
                "sac_case_count": 0,
                "nheri_case_count": 0,
                "opensees_case_count": 0,
                "case_metrics_npz_case_count": 0,
                "case_metrics_npz_step_count": 0,
            },
            "checks": {
                "sac_pass": True,
                "nheri_pass": True,
                "opensees_pass": True,
            },
        },
    )
    _write_json(authority_catalog, {"tracks": {}})
    _write_json(
        design_opt_long,
        {
            "contract_pass": True,
            "summary": {"final_max_dcr": 0.93, "solver_feasible_final": True},
        },
    )
    _write_json(
        design_opt_cost,
        {
            "contract_pass": True,
            "summary": {"cost_reduction_proxy": 100.0, "changed_group_count": 1},
            "artifacts": {},
        },
    )
    _write_json(
        external_benchmark_submission_readiness,
        {
            "contract_pass": True,
            "summary": {
                "recommended_start_mode": "approve_all_then_start",
                "recommended_submission_scope": "full",
            },
        },
    )
    _write_json(
        external_benchmark_execution_manifest,
        {
            "contract_pass": True,
            "summary": {
                "execution_mode": "kickoff_ready",
                "ready_task_count": 3,
                "blocked_task_count": 1,
                "review_boundary_pending_count": 1,
            },
            "review_boundary_preview": {
                "approve_all_reason_code": "PASS_START_NOW_FULL",
                "approve_all_ready_full": True,
                "reject_one_reason_code": "HOLD_REVIEW",
                "reject_one_open_revision_count": 1,
            },
        },
    )
    _write_json(
        external_benchmark_execution_status_manifest,
        {
            "contract_pass": True,
            "summary": {
                "status_mode": "active",
                "executable_task_count": 3,
                "planned_task_count": 4,
                "in_progress_task_count": 1,
                "completed_task_count": 2,
                "failed_task_count": 0,
                "finished_task_count": 2,
                "completion_ratio": 0.5,
            },
        },
    )
    _write_json(
        external_benchmark_batch_job_report,
        {
            "contract_pass": True,
            "summary_line": "Batch job runner: PASS | jobs=4 | completed=2 | failed=0 | reruns=1 | snapshots=3",
            "summary": {
                "job_count": 4,
                "completed_count": 2,
                "failed_count": 0,
                "rerun_count_total": 1,
                "snapshot_count": 3,
            },
        },
    )
    _write_json(
        external_benchmark_kickoff_dir / "audit_review_decision_batch_template.json",
        {
            "summary": {
                "decision_item_count": 3,
                "current_status_label": "ready",
                "review_owner_label": "committee",
                "review_priority_label": "high",
            }
        },
    )
    _write_json(
        external_benchmark_kickoff_dir / "audit_review_decision_batch_approve_all.attested_example.json",
        {"summary": {"expected_preview_reason_code": "PASS_START_NOW_FULL"}},
    )
    _write_json(
        external_benchmark_kickoff_dir / "audit_review_decision_batch_mixed.attested_example.json",
        {"summary": {"expected_preview_reason_code": "HOLD_REVIEW"}},
    )
    _write_json(
        external_benchmark_kickoff_dir / "external_benchmark_submission_readiness_preview.approve_all.json",
        {
            "reason_code": "PASS_START_NOW_FULL",
            "readiness_preview": {
                "summary": {
                    "ready_to_start_full_submission_now": True,
                    "audit_review_queue_pending_count": 0,
                    "audit_review_resolution_open_revision_count": 0,
                }
            },
        },
    )
    _write_json(
        external_benchmark_kickoff_dir / "external_benchmark_submission_readiness_preview.reject_one.json",
        {
            "reason_code": "HOLD_REVIEW",
            "readiness_preview": {
                "summary": {
                    "ready_to_start_full_submission_now": False,
                    "audit_review_queue_pending_count": 1,
                    "audit_review_resolution_open_revision_count": 1,
                    "blocker_label": "manual_review",
                }
            },
        },
    )
    _write_json(
        external_benchmark_kickoff_dir / "audit_review_decision_batch_run_report.json",
        {
            "reason_code": "PASS_START_NOW_FULL",
            "apply_live": True,
            "live_applied": False,
            "preview_reason_code": "PASS_START_NOW_FULL",
            "preview_ready_full": True,
            "preview_pending_count": 0,
            "preview_open_revision_count": 0,
        },
    )
    _write_json(
        external_benchmark_kickoff_dir / "audit_review_decision_batch.live_preview.json",
        {"reason_code": "PASS_START_NOW_FULL"},
    )

    monkeypatch.setattr(committee_module, "load_design_opt_reports", lambda: {})
    monkeypatch.setattr(committee_module, "entrypoint_status_rows", lambda reports: [])
    monkeypatch.setattr(committee_module, "entrypoint_group_rows", lambda rows: [])
    monkeypatch.setattr(committee_module, "_load_design_change_rows", lambda report: [])
    monkeypatch.setattr(committee_module, "_load_accepted_candidate_rows", lambda report: [])
    monkeypatch.setattr(
        committee_module,
        "_load_blocked_action_summary",
        lambda report: {
            "blocked_action_row_count": 0,
            "illegal_by_mask": 0,
            "illegal_by_mask_family_label": "",
            "no_cost_gain": 0,
            "blocked_no_cost_group_count": 0,
            "blocked_no_cost_explain_row_count": 0,
            "accepted_candidate_explain_row_count": 0,
            "accepted_candidate_selected_count": 0,
            "accepted_candidate_unselected_count": 0,
            "constructability_hard_gate_block_count": 0,
            "constructability_hard_gate_reason_label": "",
            "objective_profile": "",
            "budget_mode": "",
        },
    )

    def _write_pdf_stub(
        path: Path,
        cards,
        rows,
        artifacts,
        metrics,
        authority_rows,
        residual_case_rows,
        design_change_rows,
        blocked_action_summary,
        accepted_candidate_rows,
        design_opt_entrypoint_rows,
        design_opt_entrypoint_groups,
        smoke_recent_samples,
        residual_holdout_buckets,
        residual_holdout_detail_rows,
        residual_holdout_matrix_rows,
        authority_catalog_diff,
    ) -> None:
        Path(path).write_bytes(b"%PDF-1.4\n% committee fixture regression\n%%EOF\n")

    monkeypatch.setattr(committee_module, "_write_pdf", _write_pdf_stub)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_committee_review_package.py",
            "--pbd-package",
            str(pbd_package),
            "--pbd-metrics",
            str(pbd_metrics),
            "--ndtha-stress-report",
            str(ndtha_stress),
            "--ndtha-residual-report",
            str(ndtha_residual),
            "--wind-report",
            str(wind),
            "--ssi-report",
            str(ssi),
            "--damper-report",
            str(damper),
            "--construction-report",
            str(construction),
            "--diaphragm-report",
            str(diaphragm),
            "--repro-report",
            str(repro),
            "--release-registry",
            str(release_registry),
            "--kds-summary",
            str(kds),
            "--nightly-report",
            str(nightly),
            "--promotion-report",
            str(promotion),
            "--ci-report",
            str(ci),
            "--gap-report",
            str(gap_report),
            "--authority-report",
            str(authority_report),
            "--authority-catalog",
            str(authority_catalog),
            "--external-benchmark-submission-readiness-report",
            str(external_benchmark_submission_readiness),
            "--external-benchmark-execution-manifest-report",
            str(external_benchmark_execution_manifest),
            "--external-benchmark-execution-status-manifest-report",
            str(external_benchmark_execution_status_manifest),
            "--design-opt-long-report",
            str(design_opt_long),
            "--design-opt-cost-report",
            str(design_opt_cost),
            "--out-dir",
            str(out_dir),
        ],
    )

    committee_module.main()
    return gap_report, out_dir


def test_committee_review_package_surfaces_panel_and_foundation_fixture_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gap_report, out_dir = _run_committee_package_with_panel_and_foundation_fixtures(tmp_path, monkeypatch)

    summary = json.loads((out_dir / "committee_summary.json").read_text(encoding="utf-8"))
    package = json.loads((out_dir / "committee_review_package_report.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "committee_review_report.md").read_text(encoding="utf-8")
    csv_text = (out_dir / "committee_summary.csv").read_text(encoding="utf-8")
    dashboard_html = (out_dir / "committee_review_dashboard.html").read_text(encoding="utf-8")

    assert "route-selection-target" in dashboard_html
    assert 'id="committee-authority-table"' in dashboard_html
    assert 'id="committee-selected-candidates"' in dashboard_html
    assert 'id="committee-design-change-table"' in dashboard_html
    assert 'id="committee-appendix-row-provenance"' in dashboard_html
    assert 'id="committee-appendix-row-provenance-table"' in dashboard_html
    assert 'id="committee-appendix-row-provenance-hazard-table"' in dashboard_html
    assert 'id="committee-appendix-row-provenance-rule-family-table"' in dashboard_html
    assert "Open Viewer Row" in dashboard_html
    assert "Open Viewer Slice" in dashboard_html
    assert "route_track" in dashboard_html
    assert "route_candidate_id" in dashboard_html
    assert "route_action_name" in dashboard_html
    assert "route_appendix_block" in dashboard_html
    assert "route_combination_name" in dashboard_html
    assert "route_clause_label" in dashboard_html
    assert "route_hazard_type" in dashboard_html
    assert "route_rule_family" in dashboard_html

    assert summary["panel_zone_3d_clash_ready"] is True
    assert summary["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert summary["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert summary["panel_zone_validated_source_row_count_total"] == 3
    assert summary["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert summary["foundation_optimization_ready"] is True
    assert summary["foundation_scope_source"] == "dataset_summary"
    assert summary["foundation_artifact_scan_mode"] == "npz_full"
    assert summary["upstream_foundation_label_count"] == 4
    assert summary["upstream_foundation_provenance_mode"] == "dataset_scope_only"
    assert summary["midas_section_library_summary_line"] == "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3"
    assert summary["midas_kds_geometry_bridge_summary_line"] == "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0"
    assert summary["midas_kds_geometry_bridge_load_crosswalk_summary_line"] == "load_crosswalk=12/12 PASS"
    assert summary["midas_kds_geometry_bridge_load_crosswalk_count"] == 12
    assert summary["midas_kds_geometry_bridge_load_crosswalk_expected"] == 12
    assert summary["midas_kds_geometry_bridge_load_crosswalk_status"] == "PASS"
    assert summary["midas_kds_geometry_bridge_load_crosswalk_pass"] is True
    assert summary["midas_kds_geometry_bridge_semantic_crosswalk_summary_line"] == "semantic_crosswalk=12/12 PASS"
    assert summary["midas_kds_geometry_bridge_semantic_crosswalk_count"] == 12
    assert summary["midas_kds_geometry_bridge_semantic_crosswalk_expected"] == 12
    assert summary["midas_kds_geometry_bridge_semantic_crosswalk_status"] == "PASS"
    assert summary["midas_kds_geometry_bridge_semantic_crosswalk_pass"] is True
    assert summary["midas_kds_geometry_bridge_full_member_crosswalk_summary_line"] == "full_member_crosswalk=242/242 PASS"
    assert summary["midas_kds_geometry_bridge_full_member_crosswalk_count"] == 242
    assert summary["midas_kds_geometry_bridge_full_member_crosswalk_expected"] == 242
    assert summary["midas_kds_geometry_bridge_full_member_crosswalk_status"] == "PASS"
    assert summary["midas_kds_geometry_bridge_full_member_crosswalk_pass"] is True
    assert summary["midas_kds_geometry_bridge_full_section_crosswalk_summary_line"] == "full_section_crosswalk=200/200 PASS"
    assert summary["midas_kds_geometry_bridge_full_section_crosswalk_count"] == 200
    assert summary["midas_kds_geometry_bridge_full_section_crosswalk_expected"] == 200
    assert summary["midas_kds_geometry_bridge_full_section_crosswalk_status"] == "PASS"
    assert summary["midas_kds_geometry_bridge_full_section_crosswalk_pass"] is True
    assert summary["midas_kds_geometry_bridge_full_load_crosswalk_summary_line"] == "full_load_crosswalk=51/51 PASS"
    assert summary["midas_kds_geometry_bridge_full_load_crosswalk_count"] == 51
    assert summary["midas_kds_geometry_bridge_full_load_crosswalk_expected"] == 51
    assert summary["midas_kds_geometry_bridge_full_load_crosswalk_status"] == "PASS"
    assert summary["midas_kds_geometry_bridge_full_load_crosswalk_pass"] is True
    assert summary["midas_kds_geometry_bridge_full_crosswalk_depth"] == 12
    assert summary["support_search_summary_line"] == "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21"
    assert summary["support_search_count"] == 9
    assert summary["workflow_productization_summary_line"].startswith("Workflow/interoperability productization: PASS")
    assert summary["workflow_contact_coupling_summary"] == {
        "summary_label": "support families=2 | proxy families=2 | assembled depth=5",
        "pass": True,
        "support_family_count": 2,
        "proxy_family_count": 2,
        "assembled_depth_value": 5,
    }
    assert summary["general_fe_contact_matrix_summary"] == {
        "summary_label": "ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | "
        "support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21",
        "pass": True,
        "support_search_count": 9,
        "node_surface_proxy_count": 5,
        "support_depth_score": 21,
    }
    assert summary["general_fe_contact_matrix_summary_line"] == (
        "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | "
        "ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | "
        "node_surface_proxy=5 | support_depth=21"
    )
    assert "support_families=2 | proxy_families=2" in summary["structural_contact_summary_line"]
    assert "support_families=2 | proxy_families=2" in summary["foundation_soil_link_summary_line"]
    assert summary["ndtha_step_series_depth"] == 2400
    assert summary["midas_loadcomb_roundtrip_summary_line"] == "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3"
    assert summary["solver_breadth_summary_line"] == "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate"
    assert summary["material_constitutive_summary_line"].startswith("Material constitutive gate: PASS | concrete_damage=yes(matrix=10/10")
    assert summary["steel_composite_constitutive_gate_pass"] is False
    assert summary["steel_composite_constitutive_gate_summary_line"] == (
        "Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks"
    )
    assert summary["midas_kds_row_provenance_export_summary_line"].startswith(
        "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144"
    )
    assert summary["contact_readiness_summary_line"].startswith("Contact readiness: PASS")
    assert summary["surface_interaction_benchmark_summary_line"] == "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4"
    assert summary["midas_interoperability_summary_line"].startswith("MIDAS interoperability/export readiness: PASS")
    assert summary["load_combination_engine_pass"] is True
    assert summary["load_combination_engine_summary_line"] == "Load-combination engine gate: PASS | combos=8 | families=4 | source=model.loads"
    for key in (
        "mgt_export_group_local_rebar_payload_row_count",
        "mgt_export_group_local_rebar_payload_available_count",
        "mgt_export_rebar_direct_patch_eligible_change_count",
        "mgt_export_patched_material_row_count",
        "mgt_export_cloned_material_count",
    ):
        assert summary["metrics"][key] == summary[key]

    advanced = {str(row.get("id")): row for row in summary["advanced_holdouts"]}
    advanced_status = {str(row.get("id")): row for row in summary["advanced_holdout_status_rows"]}
    assert summary["advanced_holdout_total_count"] == 4
    assert summary["advanced_holdout_closed_count"] == 2
    assert summary["advanced_holdout_open_count"] == 2
    assert summary["advanced_holdout_status_label"] == "closed=2/4 | open=2 | severities=P0:2, P1:2"
    assert advanced_status["panel_zone_3d_clash_and_anchorage"]["closure_state"] == "closed"
    assert advanced_status["panel_zone_3d_clash_and_anchorage"]["mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert "status_label=release_ready" in advanced_status["panel_zone_3d_clash_and_anchorage"]["evidence_snippet"]
    assert advanced_status["foundation_mat_pile_optimization"]["closure_state"] == "closed"
    assert "scope_source=dataset_summary" in advanced_status["foundation_mat_pile_optimization"]["evidence_snippet"]
    assert advanced_status["pbd_dynamic_hinge_refresh"]["closure_state"] == "open"
    assert advanced_status["wind_tunnel_raw_mapping"]["closure_state"] == "open"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["ready"] is True
    assert "source=design_optimization_dataset_npz:true_3d_clash_and_anchorage_verified" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert advanced["foundation_mat_pile_optimization"]["ready"] is True
    assert "scope_source=dataset_summary" in advanced["foundation_mat_pile_optimization"]["evidence"]
    assert "raw_source_labels=3" in advanced["foundation_mat_pile_optimization"]["evidence"]

    assert package["metrics"]["panel_zone_3d_clash_ready"] is True
    assert package["metrics"]["advanced_holdout_total_count"] == 4
    assert package["metrics"]["advanced_holdout_closed_count"] == 2
    assert package["metrics"]["advanced_holdout_open_count"] == 2
    assert package["metrics"]["advanced_holdout_status_label"] == "closed=2/4 | open=2 | severities=P0:2, P1:2"
    assert package["metrics"]["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert package["metrics"]["panel_zone_validated_source_row_count_total"] == 3
    assert package["metrics"]["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert package["metrics"]["foundation_optimization_ready"] is True
    assert package["metrics"]["foundation_scope_source"] == "dataset_summary"
    assert package["metrics"]["upstream_foundation_label_count"] == 4
    assert package["metrics"]["midas_section_library_summary_line"] == "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3"
    assert package["metrics"]["midas_kds_geometry_bridge_summary_line"] == "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0"
    assert package["metrics"]["midas_kds_geometry_bridge_load_crosswalk_summary_line"] == "load_crosswalk=12/12 PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_load_crosswalk_count"] == 12
    assert package["metrics"]["midas_kds_geometry_bridge_load_crosswalk_expected"] == 12
    assert package["metrics"]["midas_kds_geometry_bridge_load_crosswalk_status"] == "PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_load_crosswalk_pass"] is True
    assert package["metrics"]["midas_kds_geometry_bridge_semantic_crosswalk_summary_line"] == "semantic_crosswalk=12/12 PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_semantic_crosswalk_count"] == 12
    assert package["metrics"]["midas_kds_geometry_bridge_semantic_crosswalk_expected"] == 12
    assert package["metrics"]["midas_kds_geometry_bridge_semantic_crosswalk_status"] == "PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_semantic_crosswalk_pass"] is True
    assert package["metrics"]["midas_kds_geometry_bridge_full_member_crosswalk_summary_line"] == "full_member_crosswalk=242/242 PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_full_member_crosswalk_count"] == 242
    assert package["metrics"]["midas_kds_geometry_bridge_full_member_crosswalk_expected"] == 242
    assert package["metrics"]["midas_kds_geometry_bridge_full_member_crosswalk_status"] == "PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_full_member_crosswalk_pass"] is True
    assert package["metrics"]["midas_kds_geometry_bridge_full_section_crosswalk_summary_line"] == "full_section_crosswalk=200/200 PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_full_section_crosswalk_count"] == 200
    assert package["metrics"]["midas_kds_geometry_bridge_full_section_crosswalk_expected"] == 200
    assert package["metrics"]["midas_kds_geometry_bridge_full_section_crosswalk_status"] == "PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_full_section_crosswalk_pass"] is True
    assert package["metrics"]["midas_kds_geometry_bridge_full_load_crosswalk_summary_line"] == "full_load_crosswalk=51/51 PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_full_load_crosswalk_count"] == 51
    assert package["metrics"]["midas_kds_geometry_bridge_full_load_crosswalk_expected"] == 51
    assert package["metrics"]["midas_kds_geometry_bridge_full_load_crosswalk_status"] == "PASS"
    assert package["metrics"]["midas_kds_geometry_bridge_full_load_crosswalk_pass"] is True
    assert package["metrics"]["midas_kds_geometry_bridge_full_crosswalk_depth"] == 12
    assert package["metrics"]["support_search_summary_line"] == "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21"
    assert package["metrics"]["support_search_count"] == 9
    assert package["metrics"]["workflow_productization_summary_line"].startswith("Workflow/interoperability productization: PASS")
    assert package["metrics"]["workflow_contact_coupling_summary"] == summary["workflow_contact_coupling_summary"]
    assert package["metrics"]["general_fe_contact_matrix_summary"] == summary["general_fe_contact_matrix_summary"]
    assert package["metrics"]["general_fe_contact_matrix_summary_line"] == summary["general_fe_contact_matrix_summary_line"]
    assert "support_families=2 | proxy_families=2" in package["metrics"]["structural_contact_summary_line"]
    assert "support_families=2 | proxy_families=2" in package["metrics"]["foundation_soil_link_summary_line"]
    assert package["metrics"]["ndtha_step_series_depth"] == 2400
    assert package["metrics"]["midas_loadcomb_roundtrip_summary_line"] == "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3"
    assert package["metrics"]["solver_breadth_summary_line"] == "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate"
    assert package["metrics"]["material_constitutive_summary_line"].startswith("Material constitutive gate: PASS | concrete_damage=yes(matrix=10/10")
    assert package["metrics"]["steel_composite_constitutive_gate_pass"] is False
    assert package["metrics"]["steel_composite_constitutive_gate_summary_line"] == (
        "Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks"
    )
    assert package["metrics"]["midas_kds_row_provenance_export_summary_line"].startswith(
        "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144"
    )
    assert package["metrics"]["contact_readiness_summary_line"].startswith("Contact readiness: PASS")
    assert package["metrics"]["surface_interaction_benchmark_summary_line"] == "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4"
    assert package["metrics"]["midas_interoperability_summary_line"].startswith("MIDAS interoperability/export readiness: PASS")
    assert package["metrics"]["load_combination_engine_pass"] is True
    assert package["metrics"]["load_combination_engine_summary_line"] == "Load-combination engine gate: PASS | combos=8 | families=4 | source=model.loads"
    assert package["metrics"]["project_registry_artifact_count"] == 8
    assert package["metrics"]["project_registry_approval_count"] == 2
    assert package["metrics"]["project_registry_package_sha256"] == "abc123pkg"
    assert package["metrics"]["project_registry_package_bytes"] == 4096
    assert package["metrics"]["project_registry_signature_verified"] is True
    assert package["metrics"]["external_benchmark_batch_job_contract_pass"] is True
    assert package["metrics"]["external_benchmark_batch_job_summary_line"] == (
        "Batch job runner: PASS | jobs=4 | completed=2 | failed=0 | reruns=1 | snapshots=3"
    )
    assert package["metrics"]["external_benchmark_batch_job_count"] == 4
    assert package["metrics"]["external_benchmark_batch_completed_count"] == 2
    assert package["metrics"]["external_benchmark_batch_failed_count"] == 0
    assert package["metrics"]["external_benchmark_batch_rerun_count"] == 1
    assert package["metrics"]["external_benchmark_batch_snapshot_count"] == 3
    assert package["artifacts"]["project_registry_report"].endswith("project_registry.json")
    assert package["artifacts"]["project_package_zip"].endswith("project_package.zip")
    assert package["artifacts"]["project_registry_signature"].endswith("project_registry.signature.b64")
    assert package["artifacts"]["external_benchmark_batch_job_report_json"].endswith(
        "external_benchmark_batch_job_report.json"
    )

    assert "`panel_zone_3d_clash_ready`: `True`" in markdown
    assert "`panel_zone_source_contract_mode`: `true_3d_clash_and_anchorage_verified`" in markdown
    assert "`panel_zone_validated_source_row_count_total`: `3`" in markdown
    assert "`panel_zone_validated_source_overlap_member_count_min`: `1`" in markdown
    assert "`foundation_optimization_ready`: `True`" in markdown
    assert "`foundation_scope_source`: `dataset_summary`" in markdown
    assert "`upstream_foundation_label_count`: `4`" in markdown
    assert "`raw_source_foundation_label_count`: `3`" in markdown
    assert "`midas_kds_geometry_bridge_load_crosswalk_summary_line`: `load_crosswalk=12/12 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_semantic_crosswalk_summary_line`: `semantic_crosswalk=12/12 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_member_crosswalk_summary_line`: `full_member_crosswalk=242/242 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_section_crosswalk_summary_line`: `full_section_crosswalk=200/200 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_load_crosswalk_summary_line`: `full_load_crosswalk=51/51 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_crosswalk_depth`: `12`" in markdown
    assert "`support_search_summary_line`: `Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21`" in markdown
    assert "support_families=2 | proxy_families=2" in markdown
    assert "`ndtha_step_series_depth`: `2400`" in markdown
    assert "`upstream_foundation_provenance_mode`: `dataset_scope_only`" in markdown
    assert "`midas_section_library_summary_line`: `MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3`" in markdown
    assert "`midas_kds_geometry_bridge_summary_line`: `MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0`" in markdown
    assert "`midas_loadcomb_roundtrip_summary_line`: `MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3`" in markdown
    assert "`solver_breadth_summary_line`: `Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate`" in markdown
    assert "`material_constitutive_summary_line`: `Material constitutive gate: PASS | concrete_damage=yes(matrix=10/10" in markdown
    assert "`steel_composite_constitutive_gate`: `pass=False | Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks`" in markdown
    assert "`midas_kds_row_provenance_export_summary_line`: `MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144" in markdown
    assert "`contact_readiness_summary_line`: `Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only" in markdown
    assert "`surface_interaction_benchmark_summary_line`: `Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4`" in markdown
    assert "`load_combination_engine_gate`: `pass=True | Load-combination engine gate: PASS | combos=8 | families=4 | source=model.loads`" in markdown
    assert "`constitutive_interaction_families`" in markdown
    assert "material and steel/composite constitutive gates are surfaced explicitly" in markdown
    assert "Appendix: MIDAS KDS Row Provenance Export" in markdown
    assert "row-provenance sync" in markdown
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in markdown
    assert "viewer_row_url" in markdown
    assert "viewer_slice_url" in markdown
    assert "`midas_interoperability_summary_line`: `MIDAS interoperability/export readiness: PASS | seeds=3/3 | patterns=3/3 | preview=3/3 | roundtrip=3/3" in markdown
    assert "advanced_holdout_provenance,panel_zone_3d_clash_ready,True,PASS" in csv_text
    assert "advanced_holdout_provenance,panel_zone_source_contract_mode,true_3d_clash_and_anchorage_verified,INFO" in csv_text
    assert "validated_rows=3" in csv_text
    assert "min_overlap=1" in csv_text
    assert "advanced_holdout_provenance,foundation_optimization_ready,True,PASS" in csv_text
    assert "advanced_holdout_provenance,foundation_scope_source,dataset_summary,INFO" in csv_text
    assert "raw_source_labels=3" in csv_text
    assert "detailing_payload=direct_patch_native_authoring_zero_touch_verified" in dashboard_html
    assert "MGT detailing direct-patch eligible" in dashboard_html
    assert "MGT export sidecar audit-only" in dashboard_html
    assert "MGT export sidecar manual-input" in dashboard_html
    assert "MGT audit review manifest" in dashboard_html
    assert "MGT audit review packets" in dashboard_html
    assert "MGT audit packet files" in dashboard_html
    assert "Steel/composite constitutive gate" in dashboard_html
    assert "pass=False | Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks" in dashboard_html
    assert "MGT audit review queue" in dashboard_html
    assert "MGT audit queue status" in dashboard_html
    assert "MGT audit follow-up actions" in dashboard_html
    assert "MGT audit follow-up owner" in dashboard_html
    assert "MGT audit follow-up status" in dashboard_html
    assert "MIDAS section-library validator" in dashboard_html
    assert "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3" in dashboard_html
    assert "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21" in dashboard_html
    assert "support_families=2 | proxy_families=2" in dashboard_html
    assert "MIDAS KDS geometry-bridge load crosswalk" in dashboard_html
    assert "load_crosswalk=12/12 PASS" in dashboard_html
    assert "MIDAS KDS geometry-bridge semantic crosswalk" in dashboard_html
    assert "semantic_crosswalk=12/12 PASS" in dashboard_html
    assert "MIDAS KDS geometry full-crosswalk depth" in dashboard_html
    assert "12 (min(load/semantic crosswalk))" in dashboard_html
    assert "NDTHA step-series depth" in dashboard_html
    assert "2400 (max completed steps)" in dashboard_html
    assert "Contact readiness" in dashboard_html
    assert "Surface interaction benchmark" in dashboard_html
    assert "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4" in dashboard_html
    assert "Constitutive/interaction families" in dashboard_html
    assert "material and steel/composite constitutive gates are surfaced explicitly" in dashboard_html
    assert "MIDAS KDS Row Provenance Export" in dashboard_html
    assert "row-provenance sync" in dashboard_html
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in dashboard_html
    assert "viewer_row_url" in dashboard_html
    assert "viewer_slice_url" in dashboard_html
    assert "MIDAS interoperability/export readiness" in dashboard_html
    assert "Load-combination engine gate" in dashboard_html
    assert "pass=True | Load-combination engine gate: PASS | combos=8 | families=4 | source=model.loads" in dashboard_html
    assert "MIDAS LOADCOMB round-trip validator" in dashboard_html
    assert "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3" in dashboard_html
    assert "Advanced Holdout Closure" in dashboard_html
    assert "closed=2/4 | open=2 | severities=P0:2, P1:2" in dashboard_html
    assert "Panel-zone 3D clash and anchorage coverage" in dashboard_html
    assert "Foundation / mat / pile optimization" in dashboard_html
    assert "## Advanced Holdout Closure" in markdown
    assert "advanced_holdout_closure,panel_zone_3d_clash_and_anchorage,closed,PASS" in csv_text
    assert "advanced_holdout_closure,foundation_mat_pile_optimization,closed,PASS" in csv_text
    assert "advanced_holdout_closure,pbd_dynamic_hinge_refresh,open,INFO" in csv_text


def test_committee_review_package_surfaces_measured_benchmark_breadth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    measured_payload = {
        "contract_pass": True,
        "summary_line": (
            "Measured benchmark breadth: PASS | baseline=2/51 | opensees_delta=6/7 | "
            "authority_delta=2/6 | external_delta=10/10 | measured_families=20 | "
            "measured_cases=74 | parser_ready=3"
        ),
        "summary": {
            "baseline_measured_family_count": 2,
            "baseline_measured_case_count": 51,
            "opensees_incremental_family_count": 6,
            "opensees_incremental_case_count": 7,
            "authority_incremental_family_count": 2,
            "authority_incremental_case_count": 6,
            "external_incremental_family_count": 10,
            "external_incremental_case_count": 10,
            "measured_family_count": 20,
            "measured_case_count": 74,
            "opensees_parser_ready_case_count": 3,
        },
    }
    original_load_json = committee_module._load_json

    def _load_json_with_measured(path: Path | str) -> dict:
        if str(path).endswith("measured_benchmark_breadth_report.json"):
            return measured_payload
        return original_load_json(path)

    monkeypatch.setattr(committee_module, "_load_json", _load_json_with_measured)

    _, out_dir = _run_committee_package_with_panel_and_foundation_fixtures(tmp_path, monkeypatch)

    summary = json.loads((out_dir / "committee_summary.json").read_text(encoding="utf-8"))
    package = json.loads((out_dir / "committee_review_package_report.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "committee_review_report.md").read_text(encoding="utf-8")
    dashboard_html = (out_dir / "committee_review_dashboard.html").read_text(encoding="utf-8")

    assert summary["metrics"]["measured_benchmark_breadth_summary_line"] == measured_payload["summary_line"]
    assert summary["metrics"]["measured_benchmark_family_count"] == 20
    assert summary["metrics"]["measured_benchmark_case_count"] == 74
    assert package["metrics"]["measured_benchmark_breadth_summary_line"] == measured_payload["summary_line"]
    assert package["metrics"]["measured_benchmark_family_count"] == 20
    assert package["metrics"]["measured_benchmark_case_count"] == 74
    assert package["artifacts"]["measured_benchmark_breadth_report"].endswith(
        "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json"
    )
    assert "Measured benchmark breadth: PASS" in markdown
    assert "baseline=2/51" in markdown
    assert "Measured benchmark breadth" in dashboard_html
    assert "baseline=2/51" in dashboard_html
    assert "measured=20/74" in dashboard_html


def test_committee_review_package_surfaces_peer_blind_compare_lane_and_landing_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    compare_payload = json.loads(
        Path("implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json").read_text(
            encoding="utf-8"
        )
    )
    landing_payload = json.loads(
        Path(
            "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
        ).read_text(encoding="utf-8")
    )

    _, out_dir = _run_committee_package_with_panel_and_foundation_fixtures(tmp_path, monkeypatch)

    summary = json.loads((out_dir / "committee_summary.json").read_text(encoding="utf-8"))
    package = json.loads((out_dir / "committee_review_package_report.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "committee_review_report.md").read_text(encoding="utf-8")
    dashboard_html = (out_dir / "committee_review_dashboard.html").read_text(encoding="utf-8")

    assert summary["metrics"]["peer_blind_prediction_compare_summary_line"] == compare_payload["summary_line"]
    assert summary["metrics"]["peer_blind_prediction_compare_case_count"] == 10
    assert summary["metrics"]["peer_blind_prediction_compare_measured_response_ready"] is bool(
        compare_payload.get("summary", {}).get("measured_response_ready", False)
    )
    assert summary["metrics"]["peer_blind_prediction_compare_entry_label"] == compare_payload["results_explorer"]["entry_label"]
    assert summary["metrics"]["peer_blind_prediction_compare_source_family"] == compare_payload["results_explorer"]["source_family"]
    assert summary["metrics"]["peer_blind_prediction_compare_summary_label"] == compare_payload["results_explorer"]["summary_label"]
    assert summary["metrics"]["peer_blind_prediction_measured_response_landing_summary_line"] == landing_payload["summary_line"]
    assert summary["metrics"]["peer_blind_prediction_measured_response_landing_contract_pass"] is bool(
        landing_payload.get("contract_pass", False)
    )
    assert summary["metrics"]["peer_blind_prediction_measured_response_landing_state"] == str(
        landing_payload.get("landing_state", "") or ""
    )
    assert summary["metrics"]["peer_blind_prediction_measured_response_landing_matched_file_count"] == int(
        landing_payload.get("summary", {}).get("matched_file_count", 0)
    )

    assert package["metrics"]["peer_blind_prediction_compare_summary_line"] == compare_payload["summary_line"]
    assert package["metrics"]["peer_blind_prediction_measured_response_landing_summary_line"] == landing_payload["summary_line"]
    assert package["artifacts"]["peer_blind_prediction_compare_report"].endswith(
        "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json"
    )
    assert package["artifacts"]["peer_blind_prediction_measured_response_landing_manifest"].endswith(
        "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
    )

    assert "PEER Blind Compare" in markdown
    assert compare_payload["summary_line"] in markdown
    assert "PEER Landing Manifest" in markdown
    assert landing_payload["summary_line"] in markdown
    assert (
        f"measured_response_ready={bool(compare_payload.get('summary', {}).get('measured_response_ready', False))}"
        in dashboard_html
    )
    assert "PEER Blind Compare" in dashboard_html
    assert "PEER Landing Manifest" in dashboard_html
    assert f"state={landing_payload.get('landing_state', '')}" in dashboard_html
    assert f"matched={int(landing_payload.get('summary', {}).get('matched_file_count', 0))}" in dashboard_html


def test_external_validation_bundle_surfaces_panel_solver_bundle_fixture_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gap_report, out_dir = _run_committee_package_with_panel_and_foundation_fixtures(
        tmp_path,
        monkeypatch,
        panel_source_fixture="panel_zone_solver_verified_export_bundle.json",
    )

    committee_summary = json.loads((out_dir / "committee_summary.json").read_text(encoding="utf-8"))
    summary = _external_summary_template()
    summary["metrics"]["panel_zone_3d_clash_ready"] = bool(committee_summary["panel_zone_3d_clash_ready"])
    summary["metrics"]["panel_zone_constructability_mode"] = str(committee_summary["panel_zone_constructability_mode"])
    summary["metrics"]["panel_zone_source_contract_mode"] = str(committee_summary["panel_zone_source_contract_mode"])
    summary["metrics"]["panel_zone_validated_source_row_count_total"] = int(
        committee_summary["panel_zone_validated_source_row_count_total"]
    )
    summary["metrics"]["panel_zone_validated_source_overlap_member_count_min"] = int(
        committee_summary["panel_zone_validated_source_overlap_member_count_min"]
    )
    summary["metrics"]["foundation_optimization_ready"] = bool(committee_summary["foundation_optimization_ready"])
    summary["metrics"]["foundation_scope_source"] = str(committee_summary["foundation_scope_source"])
    summary["metrics"]["foundation_artifact_scan_mode"] = str(committee_summary["foundation_artifact_scan_mode"])
    summary["metrics"]["upstream_foundation_label_count"] = int(committee_summary["upstream_foundation_label_count"])
    summary["metrics"]["raw_source_foundation_label_count"] = int(committee_summary["raw_source_foundation_label_count"])
    summary["metrics"]["upstream_foundation_provenance_mode"] = str(
        committee_summary["upstream_foundation_provenance_mode"]
    )
    summary["checks"]["committee_review_package"] = "PASS"

    release_dir = tmp_path / "external_release"
    bundle_dir, bundle_zip, summary_json, summary_md, summary_html, summary_pdf, removed = _build_bundle(
        release_dir=release_dir,
        bundle_name="external_validation_submission_fixture_panel_bundle",
        artifacts=[
            str(gap_report),
            str(out_dir / "committee_summary.json"),
            str(out_dir / "committee_review_package_report.json"),
            str(out_dir / "committee_review_report.md"),
            str(out_dir / "committee_review_dashboard.html"),
        ],
        summary=summary,
        prune_old=False,
        prune_prefix="external_validation_submission_",
    )

    assert removed == []
    assert bundle_dir.exists()
    assert bundle_zip.exists()
    assert summary_json.exists()
    assert summary_md.exists()
    assert summary_html.exists()
    assert summary_pdf.exists()

    summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
    html = summary_html.read_text(encoding="utf-8")
    markdown = summary_md.read_text(encoding="utf-8")
    assert summary_payload["metrics"]["panel_zone_3d_clash_ready"] is True
    assert summary_payload["metrics"]["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert summary_payload["metrics"]["panel_zone_validated_source_row_count_total"] == 3
    assert summary_payload["metrics"]["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert "Panel-zone source coverage" in html
    assert "validated rows=3 | min overlap=1" in html
    assert "`panel_zone_validated_source_row_count_total`: `3`" in markdown
