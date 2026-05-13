from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_release_gap_report import (
    DEFAULT_NATIVE_AUTHORING_FAMILY_TRACKS,
    DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT,
    DEFAULT_NATIVE_AUTHORING_LOCAL_RUNTIME_SCENARIO_DEPTH_REPORT,
    DEFAULT_NATIVE_AUTHORING_MULTI_PROJECT_RUNTIME_WRITEBACK_REPORT,
    DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO,
    DEFAULT_NATIVE_AUTHORING_RUNTIME_SUBMISSION_LANE,
    DEFAULT_NATIVE_AUTHORING_RUNTIME_WRITEBACK_DEPTH_REPORT,
    DEFAULT_NATIVE_AUTHORING_SOLVER_FAMILY_BREADTH_REPORT,
    DEFAULT_NATIVE_AUTHORING_WRITEBACK_BREADTH_REPORT,
    DEFAULT_PROJECT_OPS_SERVICE_SNAPSHOT,
    _native_authoring_lane_surface,
    _panel_zone_external_validation_surface,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_release_gap_boundary_only_solver_verified_does_not_close_panel_zone_external_validation() -> None:
    surface = _panel_zone_external_validation_surface(
        {
            "panel_zone_validation_boundary": "solver_verified",
            "panel_zone_external_validation_status_label": "solver_verified",
            "panel_zone_external_validation_source_count": 3,
            "panel_zone_external_validation_validated_source_count": 3,
            "panel_zone_external_validation_exact_source_count": 3,
            "panel_zone_external_validation_fallback_source_count": 0,
            "panel_zone_external_validation_candidate_member_count": 3,
            "panel_zone_external_validation_validated_member_count": 3,
            "panel_zone_external_validation_exact_member_count": 3,
            "panel_zone_external_validation_validated_row_count_total": 9,
            "panel_zone_external_validation_exact_validated_row_count": 9,
        }
    )

    assert surface["artifact_closed"] is False
    assert surface["closure_mode"] == "open_exact_validated"
    assert surface["status_label"] == "validated_exact_gap"


def test_release_gap_report_includes_nightly_smoke_summary(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    material_gate = tmp_path / "material_constitutive_gate_report.json"
    loadcomb_gate = tmp_path / "load_combination_engine_gate_report.json"
    reference_regression = tmp_path / "reference_regression_report.json"
    advanced_ssi = tmp_path / "advanced_ssi_report.json"
    wind_workflow = tmp_path / "wind_workflow_report.json"
    irregular_gate_report = tmp_path / "irregular_structure_gate_report.json"
    irregular_top5_manifest = tmp_path / "irregular_top5_execution_manifest.json"
    irregular_source_catalog = tmp_path / "irregular_structure_source_catalog.json"
    irregular_priority_manifest = tmp_path / "priority_irregular_structure_families.json"
    irregular_triage_report = tmp_path / "irregular_structure_triage_report.json"
    irregular_collection_report = tmp_path / "irregular_structure_collection_report.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"
    out_png = tmp_path / "gap_smoke.png"

    _write(
        nightly,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "design_optimization_cost_reduction_smoke": {"contract_pass": True, "reason_code": "PASS"},
            "design_optimization_cost_reduction_smoke_history": {
                "history": [
                    {
                        "generated_at": "2026-03-15T00:00:00+00:00",
                        "contract_pass": True,
                        "reason_code": "PASS",
                        "trial_feasible": True,
                        "baseline_runtime_s": 1.2,
                        "trial_runtime_s": 0.05,
                        "baseline_max_dcr": 0.95,
                        "trial_max_dcr": 0.93,
                        "trial_action_name": "rebar_down",
                    }
                ],
                "summary": {
                    "count": 4,
                    "pass_rate": 1.0,
                    "trial_feasible_rate": 1.0,
                }
            },
            "design_optimization_cost_reduction_smoke_strict_recommendation": {
                "strict_ready": True,
                "recommendation": "candidate_for_strict_enable",
            },
        },
    )
    _write(
        committee,
        {
            "midas_kds_row_provenance_preview_rows": [
                {
                    "combination_name": "gLCB1",
                    "member_id": "C-TST-003",
                    "clause_label": "KDS-MOMENT-Y-001",
                    "baseline_focus_member_id": "27441",
                    "bridge_row_provenance_mode_label": "exact row-level provenance",
                    "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                    "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column",
                }
            ],
            "midas_kds_row_provenance_clause_filter_rows": [
                {
                    "clause_label": "KDS-MOMENT-Y-001",
                    "row_count": 12,
                    "member_count": 12,
                    "combination_count": 6,
                    "top_member_id": "C-TST-003",
                    "top_dcr_label": "1.216",
                }
            ],
            "midas_kds_row_provenance_member_filter_rows": [
                {
                    "member_id": "C-TST-003",
                    "baseline_focus_member_id": "27441",
                    "row_count": 12,
                    "clause_count": 1,
                    "combination_count": 6,
                    "top_clause_label": "KDS-MOMENT-Y-001",
                }
            ],
            "midas_kds_row_provenance_hazard_filter_rows": [
                {
                    "hazard_type": "seismic",
                    "row_count": 12,
                    "member_count": 12,
                    "clause_count": 1,
                    "combination_count": 6,
                    "top_clause_label": "KDS-MOMENT-Y-001",
                    "top_dcr_label": "1.216",
                }
            ],
            "midas_kds_row_provenance_rule_family_filter_rows": [
                {
                    "rule_family": "moment",
                    "row_count": 12,
                    "member_count": 12,
                    "hazard_count": 1,
                    "combination_count": 6,
                    "top_clause_label": "KDS-MOMENT-Y-001",
                    "top_dcr_label": "1.216",
                }
            ],
            "artifact_links": {
                "midas_kds_row_provenance_export_json": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json",
                "midas_kds_row_provenance_export_csv": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
                "midas_kds_row_provenance_export_report": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
            },
            "external_benchmark_submission_queue_rows": [
                {
                    "queue_id": "hardest_external_10case",
                    "submission_scope": "hardest_external_benchmark_program",
                    "owner": "benchmark_program_owner",
                    "status": "ready_for_full_submission",
                    "onepage_attestation": "hardest external 10-case one-page attestation",
                    "onepage_attestation_status": "ready_for_full_submission",
                    "dry_run_evidence": "hardest_external_10case_kickoff: PASS_START_NOW_FULL",
                },
                {
                    "queue_id": "tpu_hffb",
                    "submission_scope": "component_wind_benchmark_submission",
                    "owner": "wind_benchmark_owner",
                    "status": "ready_for_full_submission",
                    "onepage_attestation": "TPU/HFFB component benchmark one-page attestation",
                    "onepage_attestation_status": "ready_for_full_submission",
                    "dry_run_evidence": "tpu_hffb_benchmark_gate: PASS",
                },
                {
                    "queue_id": "peer_spd_hinge",
                    "submission_scope": "component_hinge_benchmark_submission",
                    "owner": "pbd_benchmark_owner",
                    "status": "ready_for_full_submission",
                    "onepage_attestation": "PEER/SPD hinge component one-page attestation",
                    "onepage_attestation_status": "ready_for_full_submission",
                    "dry_run_evidence": (
                        "peer_spd_hinge_benchmark_gate: PASS | "
                        "peer_spd_hinge_fixture_regression: PASS | "
                        "peer_spd_hinge_alignment: PASS"
                    ),
                },
                {
                    "queue_id": "korean_public_structures",
                    "submission_scope": "korean_public_structure_release_review",
                    "owner": "korean_source_owner",
                    "status": "ready_for_full_submission",
                    "onepage_attestation": "Korean public structures provenance one-page attestation",
                    "onepage_attestation_status": "ready_for_full_submission",
                    "dry_run_evidence": "korean_public_structures: PASS",
                },
            ],
        },
    )
    irregular_top5_rows = [
        {
            "family_id": f"IRR-{idx:02d}",
            "priority": idx,
            "execution_mode": "ready_local_now" if idx <= 3 else "remote_source_hunt_needed",
            "source_record_count": 1,
            "local_ready_source_count": 1 if idx <= 3 else 0,
            "remote_candidate_source_count": 0 if idx <= 3 else 1,
            "authority_fit": "high",
            "ai_learning_fit": "high",
        }
        for idx in range(1, 6)
    ]
    _write(
        irregular_source_catalog,
        {
            "track_name": "irregular_structure_corpus_track",
            "summary": {"family_count": 5, "source_record_count": 5, "local_ready_count": 3, "remote_candidate_count": 2},
            "structure_families": [{"id": row["family_id"], "local_ready_source_count": row["local_ready_source_count"]} for row in irregular_top5_rows],
            "source_records": [
                {
                    "family_id": row["family_id"],
                    "source_id": f"src-{idx}",
                    "primary_format": "mgt",
                    "local_path": str(tmp_path / f"{row['family_id'].lower()}.mgt"),
                    "collection_status": "ready" if idx <= 3 else "remote_candidate",
                }
                for idx, row in enumerate(irregular_top5_rows, start=1)
            ],
        },
    )
    _write(
        irregular_priority_manifest,
        {"track_name": "irregular_structure_corpus_track", "families": [{"id": row["family_id"], "priority": row["priority"]} for row in irregular_top5_rows]},
    )
    _write(
        irregular_triage_report,
        {"summary": {"native_roundtrip_candidate_count": 4, "solver_benchmark_candidate_count": 3, "ai_learning_candidate_count": 5, "quick_start_local_source_count": 3}},
    )
    _write(
        irregular_collection_report,
        {"summary": {"collected_count": 5, "metadata_only_remote_candidate_count": 2, "status_counts": {"ready": 3, "remote_candidate": 2}}},
    )
    _write(
        irregular_gate_report,
        {
            "summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
            "summary": {"top5_count": 5, "top5_family_ids": [row["family_id"] for row in irregular_top5_rows]},
        },
    )
    _write(
        irregular_top5_manifest,
        {
            "summary": {"top5_count": 5, "track_name": "irregular_structure_corpus_track"},
            "top5_families": irregular_top5_rows,
        },
    )
    _write(
        ci,
        {
            "contract_pass": True,
            "all_pass": True,
            "workflow_productization_summary_line": "Workflow/interoperability productization: PASS | authoring=yes(direct_patch=25,payloads=17,generated=6) | signed=yes(artifacts=9) | audit=yes(packets=2,followup=2,resolution=2) | audit_actions=yes(queue=2,generated=6) | case_attestation=yes(cases=10,manifests=10,templates=0,receipts=10,attested=10,status=MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED=10) | auto_approved=yes(reason=PASS_START_NOW_FULL,generated=3) | submission_bundle=yes(bundle=20260401T000000Z,generated=7) | approval=yes(approve_all_ready=True) | viewer=yes(results+review) | native_roundtrip=yes(corpus=6,ready=1,public=1,native_public=1,preview_public=0,fixture=0,repo=0,experiment=0,receipts=1,types=1,taxonomy=exact:0,canonical:1,lossy:0) | irregular_structure_track=yes(families=5,sources=5,local_ready=3,remote_candidates=2,native_candidates=4,solver_candidates=3,ai_candidates=5,top5=5,gate=irregular_structure_gate_report.json,manifest=irregular_top5_execution_manifest.json) | roundtrip=editor_seed+raw_recovery+preview_roundtrip | exact_rows=144",
            "korean_source_ingest_summary_line": (
                "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | seed=4 | topo=1 | native=1 | p0=3"
            ),
            "korean_structural_preview_queue_summary_line": "KR preview queue: PASS | cand=4 | pend=1 | state=open",
            "workflow_productization_report": {
                "summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
                "summary": {
                    "irregular_structure_track_pass": True,
                    "irregular_structure_track_summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
                    "results_explorer_traceability_contact_coupling_summary_label": "support families=2 | proxy families=2 | assembled depth=5",
                    "results_explorer_traceability_contact_support_family_count": 2,
                    "results_explorer_traceability_contact_proxy_family_count": 2,
                    "results_explorer_traceability_contact_assembled_depth_value": 5,
                    "results_explorer_contact_coupling_pass": True,
                    "results_explorer_traceability_contact_material_depth_summary_label": "support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=2400/3",
                    "korean_source_ingest_summary_line": (
                        "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | seed=4 | topo=1 | native=1 | p0=3"
                    ),
                    "korean_structural_preview_queue_summary_line": "KR preview queue: PASS | cand=4 | pend=1 | state=open",
                    "irregular_structure_family_count": 5,
                    "irregular_structure_source_record_count": 5,
                    "irregular_structure_local_ready_count": 3,
                    "irregular_structure_remote_candidate_count": 2,
                    "irregular_structure_native_roundtrip_candidate_count": 4,
                    "irregular_structure_solver_benchmark_candidate_count": 3,
                    "irregular_structure_ai_learning_candidate_count": 5,
                    "irregular_structure_top5_count": 5,
                    "irregular_structure_top5_family_ids": [row["family_id"] for row in irregular_top5_rows],
                    "irregular_structure_gate_report_path": str(irregular_gate_report),
                    "irregular_top5_execution_manifest_path": str(irregular_top5_manifest),
                    "irregular_structure_source_catalog_path": str(irregular_source_catalog),
                    "irregular_priority_manifest_path": str(irregular_priority_manifest),
                    "irregular_structure_collection_report_path": str(irregular_collection_report),
                    "irregular_triage_report_path": str(irregular_triage_report),
                },
                "generated_artifacts": {
                    "irregular_structure_gate_report_path": str(irregular_gate_report),
                    "irregular_top5_execution_manifest_path": str(irregular_top5_manifest),
                    "irregular_source_catalog_path": str(irregular_source_catalog),
                    "irregular_priority_manifest_path": str(irregular_priority_manifest),
                    "irregular_collection_report_path": str(irregular_collection_report),
                    "irregular_triage_report_path": str(irregular_triage_report),
                },
            },
            "midas_section_library_summary_line": "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3",
            "midas_kds_geometry_bridge_summary_line": "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0 | full_member_crosswalk=242/242 PASS | full_section_crosswalk=200/200 PASS | full_load_crosswalk=51/51 PASS",
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
            "midas_kds_geometry_bridge_full_crosswalk_depth": 36,
            "midas_loadcomb_roundtrip_summary_line": "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3",
            "solver_breadth_summary_line": "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate",
            "steel_composite_constitutive_gate_report": {
                "contract_pass": False,
                "summary_line": "Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks",
            },
            "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
            "contact_readiness_summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | schema=yes | solver=yes(ratio=0.994,max_force=6.52235N) | whitebox=yes(err=0.0048) | structural_contact=interface_compression_surrogate",
            "general_fe_contact_matrix_summary_line": "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21",
            "structural_contact_summary_line": "Structural contact readiness: PASS | bounded_contact=yes | impl=6/6 | validated=6/6 | ready=6/6 | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2 | partial_only=none | missing=none",
            "foundation_soil_link_summary_line": "Foundation/soil link: PASS | foundation_members=76 | optimized_groups=2 | ssi=yes | soil_tunnel=yes | impedance_schema=yes | links=6(bearing_bilinear,compression_only_penalty,coulomb_friction,kelvin_voigt_pounding,normal_gap_unilateral,uplift_seat_unilateral) | foundation_support=4(p-y,pile_head,q-z,t-z) | devices=5(friction_pendulum,lead_rubber_bearing,tmd,viscoelastic_damper,viscous_damper) | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2",
            "support_search_summary_line": "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2",
            "midas_interoperability_summary_line": "MIDAS interoperability/export readiness: PASS | seeds=3/3 | patterns=3/3 | preview=3/3 | roundtrip=3/3 exact_entry_row_min=1.00 | bounded_subset=editor_seed+raw_recovery+preview_roundtrip | limits=solver_ready_reconstruction_pending, normalized_factor_maps_pending, summary_grade_preview_only, primitive_load_cards_pending",
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {},
            "frontend_payload": {},
        },
    )
    for path in [freeze, promotion, commercial, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        material_gate,
        {
            "contract_pass": False,
            "summary_line": "Material constitutive gate: CHECK | concrete_damage=yes(matrix=48/48,max=1.000) | cyclic_degradation=yes(matrix=46/46,residual_max=1.914%) | bond_interface=yes(matrix=48/48,bond_max=0.980) | matrix=395/400",
            "summary": {
                "calibration_matrix_pass_row_count": 395,
                "cyclic_library_reversal_count": 6,
                "bond_interface_cyclic_reversal_count": 4,
                "bond_interface_cyclic_max_strength_degradation": 0.22,
            },
        },
    )
    _write(
        loadcomb_gate,
        {
            "contract_pass": True,
            "summary_line": "Load-combination engine gate: PASS | models=3 | nested=6 max_depth=2 | breadth=rc, seismic, wind | rc/wind/seismic=24/12/12",
            "summary": {
                "combo_count": 24,
                "family_count": 3,
                "max_nested_depth": 2,
            },
        },
    )
    _write(
        reference_regression,
        {
            "contract_pass": True,
            "summary_line": "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0",
            "summary": {
                "case_count": 8,
                "passing_case_count": 8,
                "metric_count": 34,
                "passing_metric_count": 34,
            },
        },
    )
    _write(
        advanced_ssi,
        {
            "contract_pass": True,
            "summary_line": "Advanced SSI: PASS | layers=3 | groups=2 | peak_transfer=PILE_PERIM@2.49Hz x2.66 | group_eff=PILE_PERIM:0.47",
            "summary": {
                "peak_transfer_ratio_max": 2.66,
                "peak_transfer_group_id": "PILE_PERIM",
                "min_group_interaction_efficiency_ratio": 0.47,
            },
        },
    )
    _write(
        wind_workflow,
        {
            "contract_pass": True,
            "summary_line": "Wind workflow: PASS | exposure=C | stories=6 | accel=10.3/24.0mg | comfort=acceptable | cases=8",
            "summary": {
                "occupant_comfort_class": "acceptable",
                "occupant_comfort_crosswind_bias_ratio": 1.24,
            },
        },
    )

    cmd = [
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
        str(midas),
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
        "--material-constitutive-gate-report",
        str(material_gate),
        "--load-combination-engine-gate-report",
        str(loadcomb_gate),
        "--reference-regression-report",
        str(reference_regression),
        "--advanced-ssi-report",
        str(advanced_ssi),
        "--wind-workflow-report",
        str(wind_workflow),
        "--committee-summary",
        str(committee),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
        "--out-smoke-history-png",
        str(out_png),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    release_status = payload["release_status"]
    summary = payload["summary"]
    assert release_status["nightly_smoke_pass"] is True
    assert release_status["nightly_smoke_history_count"] == 4
    assert release_status["nightly_smoke_strict_ready"] is True
    assert release_status["nightly_smoke_strict_recommendation"] == "candidate_for_strict_enable"
    assert release_status["midas_section_library_summary_line"] == "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3"
    assert release_status["midas_kds_geometry_bridge_summary_line"] == "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0 | full_member_crosswalk=242/242 PASS | full_section_crosswalk=200/200 PASS | full_load_crosswalk=51/51 PASS"
    assert release_status["midas_kds_geometry_bridge_load_crosswalk_summary_line"] == "load_crosswalk=12/12 PASS"
    assert release_status["midas_kds_geometry_bridge_load_crosswalk_count"] == 12
    assert release_status["midas_kds_geometry_bridge_load_crosswalk_expected"] == 12
    assert release_status["midas_kds_geometry_bridge_load_crosswalk_status"] == "PASS"
    assert release_status["midas_kds_geometry_bridge_load_crosswalk_pass"] is True
    assert release_status["midas_kds_geometry_bridge_semantic_crosswalk_summary_line"] == "semantic_crosswalk=12/12 PASS"
    assert release_status["midas_kds_geometry_bridge_semantic_crosswalk_count"] == 12
    assert release_status["midas_kds_geometry_bridge_semantic_crosswalk_expected"] == 12
    assert release_status["midas_kds_geometry_bridge_semantic_crosswalk_status"] == "PASS"
    assert release_status["midas_kds_geometry_bridge_semantic_crosswalk_pass"] is True
    assert release_status["midas_kds_geometry_bridge_full_member_crosswalk_summary_line"] == "full_member_crosswalk=242/242 PASS"
    assert release_status["midas_kds_geometry_bridge_full_member_crosswalk_count"] == 242
    assert release_status["midas_kds_geometry_bridge_full_member_crosswalk_expected"] == 242
    assert release_status["midas_kds_geometry_bridge_full_member_crosswalk_status"] == "PASS"
    assert release_status["midas_kds_geometry_bridge_full_member_crosswalk_pass"] is True
    assert release_status["midas_kds_geometry_bridge_full_section_crosswalk_summary_line"] == "full_section_crosswalk=200/200 PASS"
    assert release_status["midas_kds_geometry_bridge_full_section_crosswalk_count"] == 200
    assert release_status["midas_kds_geometry_bridge_full_section_crosswalk_expected"] == 200
    assert release_status["midas_kds_geometry_bridge_full_section_crosswalk_status"] == "PASS"
    assert release_status["midas_kds_geometry_bridge_full_section_crosswalk_pass"] is True
    assert release_status["midas_kds_geometry_bridge_full_load_crosswalk_summary_line"] == "full_load_crosswalk=51/51 PASS"
    assert release_status["midas_kds_geometry_bridge_full_load_crosswalk_count"] == 51
    assert release_status["midas_kds_geometry_bridge_full_load_crosswalk_expected"] == 51
    assert release_status["midas_kds_geometry_bridge_full_load_crosswalk_status"] == "PASS"
    assert release_status["midas_kds_geometry_bridge_full_load_crosswalk_pass"] is True
    assert release_status["midas_kds_geometry_bridge_full_crosswalk_depth"] == 12
    assert (
        release_status["support_search_summary_line"]
        == "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2"
    )
    assert release_status["support_search_count"] == 9
    assert "support_families=2 | proxy_families=2" in release_status["structural_contact_summary_line"]
    assert release_status["general_fe_contact_matrix_summary_line"] == (
        "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | "
        "ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | "
        "node_surface_proxy=5 | support_depth=21"
    )
    assert "support_families=2 | proxy_families=2" in release_status["foundation_soil_link_summary_line"]
    assert release_status["midas_loadcomb_roundtrip_summary_line"] == "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3"
    assert release_status["solver_breadth_summary_line"] == "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate"
    assert release_status["material_constitutive_summary_line"] == (
        "Material constitutive gate: CHECK | concrete_damage=yes(matrix=48/48,max=1.000) | "
        "cyclic_degradation=yes(matrix=46/46,residual_max=1.914%) | "
        "bond_interface=yes(matrix=48/48,bond_max=0.980) | matrix=395/400"
    )
    assert release_status["material_constitutive_pass"] is False
    assert release_status["material_constitutive_calibration_matrix_pass_row_count"] == 395
    assert release_status["material_constitutive_cyclic_library_reversal_count"] == 6
    assert release_status["material_constitutive_bond_interface_cyclic_reversal_count"] == 4
    assert release_status["steel_composite_constitutive_gate_pass"] is False
    assert release_status["steel_composite_constitutive_gate_summary_line"] == (
        "Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks"
    )
    assert release_status["midas_kds_row_provenance_export_summary_line"] == "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144"
    assert release_status["contact_readiness_summary_line"].startswith("Contact readiness: PASS")
    assert release_status["midas_interoperability_summary_line"].startswith("MIDAS interoperability/export readiness: PASS")
    assert release_status["load_combination_engine_pass"] is True
    assert release_status["load_combination_engine_summary_line"] == (
        "Load-combination engine gate: PASS | models=3 | nested=6 max_depth=2 | "
        "breadth=rc, seismic, wind | rc/wind/seismic=24/12/12"
    )
    assert release_status["load_combination_engine_combo_count"] == 24
    assert release_status["load_combination_engine_family_count"] == 3
    assert release_status["load_combination_engine_max_nested_depth"] == 2
    assert release_status["reference_regression_pass"] is True
    assert release_status["reference_regression_summary_line"] == (
        "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0"
    )
    assert release_status["reference_regression_case_count"] == 8
    assert release_status["reference_regression_passing_case_count"] == 8
    assert release_status["reference_regression_metric_count"] == 34
    assert release_status["reference_regression_passing_metric_count"] == 34
    assert release_status["advanced_ssi_pass"] is True
    assert release_status["advanced_ssi_summary_line"] == (
        "Advanced SSI: PASS | layers=3 | groups=2 | peak_transfer=PILE_PERIM@2.49Hz x2.66 | group_eff=PILE_PERIM:0.47"
    )
    assert release_status["advanced_ssi_peak_transfer_ratio_max"] == 2.66
    assert release_status["advanced_ssi_peak_transfer_group_id"] == "PILE_PERIM"
    assert release_status["advanced_ssi_min_group_interaction_efficiency_ratio"] == 0.47
    assert release_status["wind_workflow_pass"] is True
    assert release_status["wind_workflow_summary_line"] == (
        "Wind workflow: PASS | exposure=C | stories=6 | accel=10.3/24.0mg | comfort=acceptable | cases=8"
    )
    assert release_status["wind_workflow_occupant_comfort_class"] == "acceptable"
    assert release_status["wind_workflow_occupant_comfort_crosswind_bias_ratio"] == 1.24
    assert release_status["workflow_contact_coupling_summary_line"] == (
        "Workflow contact coupling: PASS | support families=2 | proxy families=2 | assembled depth=5"
    )
    assert release_status["workflow_contact_coupling_pass"] is True
    assert release_status["workflow_contact_support_family_count"] == 2
    assert release_status["workflow_contact_proxy_family_count"] == 2
    assert release_status["workflow_contact_assembled_depth_value"] == 5
    assert summary["midas_section_library_summary_line"] == "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3"
    assert summary["midas_kds_geometry_bridge_summary_line"] == "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0 | full_member_crosswalk=242/242 PASS | full_section_crosswalk=200/200 PASS | full_load_crosswalk=51/51 PASS"
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
    assert (
        summary["support_search_summary_line"]
        == "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2"
    )
    assert summary["support_search_count"] == 9
    assert "support_families=2 | proxy_families=2" in summary["structural_contact_summary_line"]
    assert summary["general_fe_contact_matrix_summary_line"] == (
        "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | "
        "ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | "
        "node_surface_proxy=5 | support_depth=21"
    )
    assert "support_families=2 | proxy_families=2" in summary["foundation_soil_link_summary_line"]
    assert summary["midas_loadcomb_roundtrip_summary_line"] == "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3"
    assert summary["solver_breadth_summary_line"] == "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate"
    assert summary["material_constitutive_summary_line"] == (
        "Material constitutive gate: CHECK | concrete_damage=yes(matrix=48/48,max=1.000) | "
        "cyclic_degradation=yes(matrix=46/46,residual_max=1.914%) | "
        "bond_interface=yes(matrix=48/48,bond_max=0.980) | matrix=395/400"
    )
    assert summary["material_constitutive_pass"] is False
    assert summary["material_constitutive_calibration_matrix_pass_row_count"] == 395
    assert summary["material_constitutive_cyclic_library_reversal_count"] == 6
    assert summary["material_constitutive_bond_interface_cyclic_reversal_count"] == 4
    assert summary["steel_composite_constitutive_gate_pass"] is False
    assert summary["steel_composite_constitutive_gate_summary_line"] == (
        "Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks"
    )
    assert summary["midas_kds_row_provenance_export_summary_line"] == "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144"
    assert summary["contact_readiness_summary_line"].startswith("Contact readiness: PASS")
    assert summary["midas_interoperability_summary_line"].startswith("MIDAS interoperability/export readiness: PASS")
    assert summary["load_combination_engine_pass"] is True
    assert summary["load_combination_engine_summary_line"] == (
        "Load-combination engine gate: PASS | models=3 | nested=6 max_depth=2 | "
        "breadth=rc, seismic, wind | rc/wind/seismic=24/12/12"
    )
    assert summary["load_combination_engine_combo_count"] == 24
    assert summary["load_combination_engine_family_count"] == 3
    assert summary["load_combination_engine_max_nested_depth"] == 2
    assert summary["reference_regression_pass"] is True
    assert summary["reference_regression_summary_line"] == (
        "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0"
    )
    assert summary["reference_regression_case_count"] == 8
    assert summary["reference_regression_passing_case_count"] == 8
    assert summary["reference_regression_metric_count"] == 34
    assert summary["reference_regression_passing_metric_count"] == 34
    assert summary["advanced_ssi_pass"] is True
    assert summary["advanced_ssi_summary_line"] == (
        "Advanced SSI: PASS | layers=3 | groups=2 | peak_transfer=PILE_PERIM@2.49Hz x2.66 | group_eff=PILE_PERIM:0.47"
    )
    assert summary["advanced_ssi_peak_transfer_ratio_max"] == 2.66
    assert summary["advanced_ssi_peak_transfer_group_id"] == "PILE_PERIM"
    assert summary["advanced_ssi_min_group_interaction_efficiency_ratio"] == 0.47
    assert summary["wind_workflow_pass"] is True
    assert summary["wind_workflow_summary_line"] == (
        "Wind workflow: PASS | exposure=C | stories=6 | accel=10.3/24.0mg | comfort=acceptable | cases=8"
    )
    assert summary["wind_workflow_occupant_comfort_class"] == "acceptable"
    assert summary["wind_workflow_occupant_comfort_crosswind_bias_ratio"] == 1.24
    assert summary["workflow_contact_coupling_summary_line"] == (
        "Workflow contact coupling: PASS | support families=2 | proxy families=2 | assembled depth=5"
    )
    assert summary["workflow_contact_coupling_pass"] is True
    assert summary["workflow_contact_support_family_count"] == 2
    assert summary["workflow_contact_proxy_family_count"] == 2
    assert summary["workflow_contact_assembled_depth_value"] == 5
    assert payload["artifacts"]["smoke_history_png"] == str(out_png)
    assert out_png.exists()
    assert payload["nightly_smoke_trend"]["sample_count"] == 1
    assert isinstance(payload["nightly_smoke_recent_samples"], list)
    assert any("Design-optimization cost smoke probe is stable" == row["title"] for row in payload["observed_strengths"])
    markdown = out_md.read_text(encoding="utf-8")
    assert "nightly_smoke_pass" in markdown
    assert "nightly_smoke_strict_recommendation" in markdown
    assert "MIDAS section-library validator" in markdown
    assert "MIDAS section-library: ok | artifacts=3 | embedded=3 | representative_links=3" in markdown
    assert "MIDAS KDS geometry-bridge validator" in markdown
    assert "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0" in markdown
    assert "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21" in markdown
    assert "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21" in markdown
    assert "support_families=2 | proxy_families=2" in markdown
    assert "MIDAS KDS geometry-bridge load crosswalk" in markdown
    assert "load_crosswalk=12/12 PASS" in markdown
    assert "MIDAS KDS geometry-bridge semantic crosswalk" in markdown
    assert "semantic_crosswalk=12/12 PASS" in markdown
    assert "MIDAS KDS geometry full-crosswalk depth" in markdown
    assert "min(load/semantic crosswalk)" in markdown
    assert "MIDAS LOADCOMB round-trip validator" in markdown
    assert "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3" in markdown
    assert "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0" in markdown
    assert "Workflow contact coupling" in markdown
    assert "Workflow contact coupling: PASS | support families=2 | proxy families=2 | assembled depth=5" in markdown
    assert "KR ingest" in markdown
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in markdown
    assert "Solver breadth" in markdown
    assert "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=1,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=interface_compression_surrogate" in markdown
    assert "NDTHA step-series depth" in markdown
    assert "Material constitutive gate" in markdown
    assert "pass=False | Material constitutive gate: CHECK | concrete_damage=yes(matrix=48/48,max=1.000)" in markdown
    assert "Material constitutive depth: `matrix_rows=395` | `cyclic_reversals=6` | `bond_cyclic_reversals=4`" in markdown
    assert "Steel/composite constitutive gate" in markdown
    assert "pass=False | Steel/composite constitutive gate: CHECK | steel=9/12 | composite=6/8 | source=constituent_benchmarks" in markdown
    assert "MIDAS KDS row provenance export" in markdown
    assert "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144" in markdown
    assert "Constitutive/interaction families" in markdown
    assert "material and steel/composite constitutive gates are surfaced explicitly" in markdown
    assert "## Appendix: MIDAS KDS Row Provenance Export" in markdown
    assert "## Appendix: Irregular Structure Track" in markdown
    assert "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5" in markdown
    assert "irregular_structure_gate_report.json" in markdown
    assert "irregular_top5_execution_manifest.json" in markdown
    assert "irregular_structure_source_catalog.json" in markdown
    assert "priority_irregular_structure_families.json" in markdown
    assert "irregular_structure_collection_report.json" in markdown
    assert "irregular_structure_triage_report.json" in markdown
    assert "IRR-01" in markdown
    assert "row-provenance sync" in markdown
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in markdown
    assert "viewer_row_url" in markdown
    assert "viewer_slice_url" in markdown
    assert "midas_kds_row_provenance_table.csv" in markdown
    assert "KDS-MOMENT-Y-001" in markdown
    assert "| Clause | Rows | Members | Combos | Top Member | Top D/C |" in markdown
    assert "| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |" in markdown
    assert "| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |" in markdown
    assert "| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |" in markdown
    assert "Contact readiness" in markdown
    assert "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only" in markdown
    assert "MIDAS interoperability/export readiness" in markdown
    assert "MIDAS interoperability/export readiness: PASS | seeds=3/3 | patterns=3/3 | preview=3/3 | roundtrip=3/3" in markdown
    assert "Load-combination engine gate" in markdown
    assert "pass=True | Load-combination engine gate: PASS | models=3 | nested=6 max_depth=2 | breadth=rc, seismic, wind | rc/wind/seismic=24/12/12" in markdown
    assert "Load-combination engine depth: `combos=24` | `families=3` | `nested_depth=2`" in markdown
    assert "Advanced SSI gate" in markdown
    assert "pass=True | Advanced SSI: PASS | layers=3 | groups=2 | peak_transfer=PILE_PERIM@2.49Hz x2.66 | group_eff=PILE_PERIM:0.47" in markdown
    assert "Advanced SSI metrics: `peak_transfer=2.660` (PILE_PERIM) | `group_efficiency=0.470`" in markdown
    assert "Wind workflow gate" in markdown
    assert "pass=True | Wind workflow: PASS | exposure=C | stories=6 | accel=10.3/24.0mg | comfort=acceptable | cases=8" in markdown
    assert "Wind workflow metrics: `comfort_class=acceptable` | `crosswind_bias=1.240`" in markdown
    assert "smoke_history_png" in markdown


def test_release_gap_report_surfaces_panel_zone_status_semantics(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    pbd = tmp_path / "pbd.json"
    dataset = tmp_path / "dataset.json"
    foundation = tmp_path / "foundation.json"
    wind = tmp_path / "wind.json"
    material_gate = tmp_path / "material_constitutive_gate_report.json"
    load_gate = tmp_path / "load_combination_engine_gate_report.json"
    advanced_ssi = tmp_path / "advanced_ssi_report.json"
    wind_workflow = tmp_path / "wind_workflow_report.json"
    panel_zone = tmp_path / "panel_zone.json"
    panel_zone_inbox = tmp_path / "panel_zone_inbox.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, commercial, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(pbd, {"contract_pass": True, "summary": {}})
    _write(dataset, {"contract_pass": True, "summary": {}, "rows_head": []})
    _write(foundation, {"contract_pass": False, "summary": {}})
    _write(wind, {"contract_pass": False, "summary": {}})
    _write(material_gate, {"contract_pass": True, "summary_line": "Material constitutive gate: PASS | matrix=1/1"})
    _write(load_gate, {"contract_pass": True, "summary_line": "Load-combination engine gate: PASS | combos=1"})
    _write(
        advanced_ssi,
        {
            "contract_pass": True,
            "summary_line": "Advanced SSI: PASS | layers=1 | groups=1 | peak_transfer=MAT@2.00Hz x1.10 | group_eff=MAT:1.00",
            "summary": {
                "peak_transfer_ratio_max": 1.1,
                "peak_transfer_group_id": "MAT",
                "min_group_interaction_efficiency_ratio": 1.0,
            },
        },
    )
    _write(
        wind_workflow,
        {
            "contract_pass": True,
            "summary_line": "Wind workflow: PASS | exposure=B | stories=3 | accel=3.0/12.0mg | comfort=calm | cases=8",
            "summary": {
                "occupant_comfort_class": "calm",
                "occupant_comfort_crosswind_bias_ratio": 1.0,
            },
        },
    )
    _write(
        panel_zone,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": "Internal engine completed panel-zone joint geometry, anchorage, and clash recomputation with validated member overlap; external verification now serves as an optional audit boundary.",
            "summary": {
                "constructability_mode": "internal_engine_panel_zone_3d_clash_and_anchorage_complete",
                "panel_zone_internal_engine_complete": True,
                "panel_zone_external_validation_pending": True,
                "panel_zone_validation_boundary": "external_validation_only",
            },
        },
    )
    _write(
        panel_zone_inbox,
        {
            "contract_pass": True,
            "summary": {
                "panel_zone_solver_verified_inbox_status_mode": "empty_without_history",
                "panel_zone_solver_verified_pending_input": False,
            },
        },
    )

    cmd = [
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
        str(midas),
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
        "--pbd-package",
        str(pbd),
        "--design-opt-dataset-report",
        str(dataset),
        "--foundation-optimization-report",
        str(foundation),
        "--wind-raw-mapping-report",
        str(wind),
        "--panel-zone-clash-report",
        str(panel_zone),
        "--panel-zone-solver-verified-inbox-status-report",
        str(panel_zone_inbox),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    release_status = payload["release_status"]
    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}

    assert summary["panel_zone_status_label"] == "validated_fallback_only_gap_no_solver_input"
    assert summary["panel_zone_advisory_only"] is True
    assert summary["panel_zone_release_blocking"] is False
    assert summary["panel_zone_external_validation_status_label"] == "validated_fallback_only_gap_no_solver_input"
    assert summary["panel_zone_external_validation_advisory_only"] is True
    assert summary["panel_zone_external_validation_release_blocking"] is False
    assert summary["panel_zone_external_validation_artifact_closed"] is False
    assert summary["panel_zone_external_validation_closure_mode"] == "open_fallback_validated"
    assert summary["panel_zone_external_validation_required_evidence"] == "solver_verified_3d_clash_and_anchorage_artifact"
    assert "artifact_closed=False" in summary["panel_zone_external_validation_summary_line"]
    assert "closure_mode=open_fallback_validated" in summary["panel_zone_external_validation_summary_line"]
    assert "required_evidence=solver_verified_3d_clash_and_anchorage_artifact" in summary["panel_zone_external_validation_summary_line"]
    assert summary["panel_zone_external_validation_local_closure_state"] == "awaiting_solver_verified_drop"
    assert "wait_for_solver_drop" in summary["panel_zone_external_validation_local_closure_label"]
    assert summary["panel_zone_external_validation_provenance_summary_label"].startswith(
        "validated_sources=3/3 | exact_sources=0/3 | fallback_sources=3/3"
    )
    assert summary["advanced_holdout_count"] == 4
    assert summary["advanced_holdout_ready_count"] == 2
    assert summary["advanced_holdout_open_count"] == 2
    assert (
        summary["advanced_holdout_status_label"]
        == "foundation_mat_pile_optimization:open, panel_zone_3d_clash_and_anchorage:closed, pbd_dynamic_hinge_refresh:closed, wind_tunnel_raw_mapping:open"
    )
    assert summary["external_benchmark_submission_queue_count"] == 4
    assert summary["external_benchmark_submission_queue_ready_count"] == 4
    assert summary["external_benchmark_submission_queue_review_pending_count"] == 0
    assert summary["external_benchmark_submission_queue_blocked_count"] == 0
    assert summary["external_benchmark_submission_onepage_attestation_status"] == "ready_for_full_submission"
    assert summary["external_benchmark_submission_summary_line"] == (
        "External benchmark submission queue: queue=4 | ready=4 | review_pending=0 | "
        "blocked=0 | receipt_attached=0 | receipt_pending=4 | "
        "onepage_attestation_status=ready_for_full_submission | "
        "start_mode=start_now_full_external_submission | "
        "submission_scope=full_external_submission_package | blocker=none | caution=none"
    )
    assert "inbox=empty_without_history" in summary["panel_zone_external_validation_closing_summary_label"]
    assert release_status["panel_zone_status_label"] == "validated_fallback_only_gap_no_solver_input"
    assert release_status["panel_zone_advisory_only"] is True
    assert release_status["panel_zone_release_blocking"] is False
    assert release_status["panel_zone_external_validation_status_label"] == "validated_fallback_only_gap_no_solver_input"
    assert release_status["panel_zone_external_validation_advisory_only"] is True
    assert release_status["panel_zone_external_validation_release_blocking"] is False
    assert release_status["panel_zone_external_validation_closure_mode"] == "open_fallback_validated"
    assert release_status["panel_zone_external_validation_local_closure_state"] == "awaiting_solver_verified_drop"
    assert release_status["advanced_holdout_count"] == 4
    assert release_status["advanced_holdout_ready_count"] == 2
    assert release_status["advanced_holdout_open_count"] == 2
    assert release_status["advanced_holdout_status_label"] == summary["advanced_holdout_status_label"]
    assert release_status["external_benchmark_submission_queue_count"] == 4
    assert release_status["external_benchmark_submission_queue_ready_count"] == 4
    assert release_status["external_benchmark_submission_queue_review_pending_count"] == 0
    assert release_status["external_benchmark_submission_queue_blocked_count"] == 0
    assert release_status["external_benchmark_submission_onepage_attestation_status"] == "ready_for_full_submission"
    assert release_status["external_benchmark_submission_summary_line"] == summary["external_benchmark_submission_summary_line"]
    assert advanced["pbd_dynamic_hinge_refresh"]["status"] == "closed"
    assert advanced["pbd_dynamic_hinge_refresh"]["status_label"].startswith("closed_")
    assert advanced["pbd_dynamic_hinge_refresh"]["closure_label"] == advanced["pbd_dynamic_hinge_refresh"]["status_label"]
    assert advanced["pbd_dynamic_hinge_refresh"]["why_it_remains"].startswith(
        "Closed in the current commercialization surface:"
    )
    assert advanced["pbd_dynamic_hinge_refresh"]["exit_criteria"].startswith("Keep `")
    assert "evidence attached and stable across release artifacts." in advanced["pbd_dynamic_hinge_refresh"]["exit_criteria"]
    assert advanced["pbd_dynamic_hinge_refresh"]["next_step"] == (
        "Monitor this closed holdout for regressions in the next release pass."
    )
    assert advanced["panel_zone_3d_clash_and_anchorage"]["status"] == "closed"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["status_label"] == "validated_fallback_only_gap_no_solver_input"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["closure_label"] == "validated_fallback_only_gap_no_solver_input"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["advisory_only"] is True
    assert advanced["panel_zone_3d_clash_and_anchorage"]["release_blocking"] is False
    assert advanced["panel_zone_3d_clash_and_anchorage"]["why_it_remains"].startswith(
        "Closed in the current commercialization surface:"
    )
    assert "Internal engine completed panel-zone joint geometry" in advanced[
        "panel_zone_3d_clash_and_anchorage"
    ]["why_it_remains"]
    assert "internal_engine_panel_zone_3d_clash_and_anchorage_complete" in advanced[
        "panel_zone_3d_clash_and_anchorage"
    ]["exit_criteria"]
    assert advanced["panel_zone_3d_clash_and_anchorage"]["next_step"] == (
        "Monitor this closed holdout for regressions in the next release pass."
    )
    assert "artifact_closed=False" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "closure_mode=open_fallback_validated" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "external_validation_status=validated_fallback_only_gap_no_solver_input" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "status_label=validated_fallback_only_gap_no_solver_input" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "local_closure_state=awaiting_solver_verified_drop" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "required_evidence=solver_verified_3d_clash_and_anchorage_artifact" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "coverage=validated_sources=3/3 | exact_sources=0/3 | fallback_sources=3/3" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "Advanced holdouts: `count=4` | `ready=2` | `open=2`" in markdown
    assert "| Area | Status | Label | Mode | Why It Remains | Exit Criteria | Next Step |" in markdown
    assert "Dynamic plastic-hinge refresh | closed | closed_" in markdown
    assert "Panel-zone 3D clash and anchorage coverage | closed | validated_fallback_only_gap_no_solver_input" in markdown
    assert (
        "External benchmark submission queue: `External benchmark submission queue: queue=4 | "
        "ready=4 | review_pending=0 | blocked=0 | "
        "receipt_attached=0 | receipt_pending=4 | "
        "onepage_attestation_status=ready_for_full_submission"
    ) in markdown
    assert "| Work Item | Queue | Submission ID | Scope | Owner | Status | Receipt | Receipt Status | Onepage Status | Dry-run Evidence |" in markdown
    assert "hardest_external_10case" in markdown
    assert "tpu_hffb" in markdown
    assert "peer_spd_hinge" in markdown
    assert "korean_public_structures" in markdown


def test_release_gap_report_accepts_committee_artifacts_fallback(tmp_path: Path) -> None:
    required_payloads = {
        "nightly": {"contract_pass": True},
        "ci": {
            "contract_pass": True,
            "all_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {},
            "frontend_payload": {},
        },
        "static": {"pass": True},
        "freeze": {"contract_pass": True},
        "promotion": {"contract_pass": True},
        "commercial": {"contract_pass": True},
        "authority": {"contract_pass": True},
        "hip": {"contract_pass": True},
        "midas": {"contract_pass": True},
        "construction": {"contract_pass": True},
        "diaphragm": {"contract_pass": True},
        "repro": {"contract_pass": True},
        "kds": {"contract_pass": True},
        "committee": {
            "artifacts": {
                "midas_kds_row_provenance_export_json": "fallback_row_provenance.json",
                "midas_kds_row_provenance_export_csv": "fallback_row_provenance.csv",
                "midas_kds_row_provenance_export_report": "fallback_row_provenance_report.json",
                "project_registry_report": "fallback_project_registry.json",
                "project_package_zip": "fallback_project_package.zip",
                "project_registry_signature": "fallback_project_registry.signature.b64",
                "external_benchmark_batch_job_report_json": "fallback_external_benchmark_batch_job_report.json",
            }
        },
    }
    paths: dict[str, Path] = {}
    for name, payload in required_payloads.items():
        path = tmp_path / f"{name}.json"
        _write(path, payload)
        paths[name] = path

    history_root = tmp_path / "history"
    history_root.mkdir()
    missing = tmp_path / "missing.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(paths["nightly"]),
        "--ci-gate",
        str(paths["ci"]),
        "--static-validation",
        str(paths["static"]),
        "--freeze-report",
        str(paths["freeze"]),
        "--promotion-report",
        str(paths["promotion"]),
        "--commercial-readiness",
        str(paths["commercial"]),
        "--global-authority",
        str(paths["authority"]),
        "--hip-kernel-smoke",
        str(paths["hip"]),
        "--midas-conversion",
        str(paths["midas"]),
        "--mgt-export-output-mgt",
        str(tmp_path / "missing.mgt"),
        "--mgt-export-report",
        str(missing),
        "--mgt-export-audit-review-queue-manifest",
        str(missing),
        "--mgt-export-audit-review-followup-manifest",
        str(missing),
        "--construction-sequence",
        str(paths["construction"]),
        "--flexible-diaphragm",
        str(paths["diaphragm"]),
        "--repro-version-lock",
        str(paths["repro"]),
        "--release-registry",
        str(missing),
        "--kds-compliance",
        str(paths["kds"]),
        "--solver-hip-e2e",
        str(missing),
        "--solver-truthfulness-report",
        str(missing),
        "--hardest-external-10case-kickoff-report",
        str(missing),
        "--rc-benchmark-lock",
        str(missing),
        "--quality-mgt-corpus",
        str(missing),
        "--pbd-package",
        str(missing),
        "--design-opt-dataset-report",
        str(missing),
        "--pbd-hinge-refresh-report",
        str(missing),
        "--panel-zone-clash-report",
        str(missing),
        "--panel-zone-solver-verified-inbox-status-report",
        str(missing),
        "--foundation-optimization-report",
        str(missing),
        "--wind-raw-mapping-report",
        str(missing),
        "--performance-profiling-report",
        str(missing),
        "--committee-summary",
        str(paths["committee"]),
        "--nightly-history-root",
        str(history_root),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["artifacts"]["midas_kds_row_provenance_export_json"] == "fallback_row_provenance.json"
    assert payload["artifacts"]["midas_kds_row_provenance_export_csv"] == "fallback_row_provenance.csv"
    assert payload["artifacts"]["midas_kds_row_provenance_export_report"] == "fallback_row_provenance_report.json"
    assert payload["artifacts"]["project_registry_report"] == "fallback_project_registry.json"
    assert payload["artifacts"]["project_package_zip"] == "fallback_project_package.zip"
    assert payload["artifacts"]["project_registry_signature"] == "fallback_project_registry.signature.b64"
    assert (
        payload["artifacts"]["external_benchmark_batch_job_report_json"]
        == "fallback_external_benchmark_batch_job_report.json"
    )
    assert out_md.exists()


def test_release_gap_report_surfaces_project_registry_and_batch_summary(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "generate_release_gap_report.py"
    )
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [freeze, promotion, authority, hip, midas, construction, diaphragm, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(repro, {"contract_pass": True, "summary": {"replay_runs": 2, "seed": 7}, "checks": {"lock_manifest_written": True}})
    _write(
        ci,
        {
            "contract_pass": True,
            "all_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {},
            "frontend_payload": {},
        },
    )
    _write(commercial, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "deployment_model": {}})
    _write(
        registry,
        {
            "contract_pass": True,
            "summary": {
                "signing_algorithm": "ed25519",
                "artifact_count": 11,
                "project_registry_artifact_count": 8,
                "project_registry_approval_count": 2,
                "project_registry_package_sha256": "pkgsha256",
                "project_registry_package_bytes": 4096,
            },
            "checks": {
                "signature_verified_pass": True,
                "project_registry_signature_verified_pass": True,
            },
            "signature": {"public_key_path": "release_registry_ed25519.pub.pem"},
            "artifacts": {
                "project_registry_report": "release_project_registry.json",
                "project_package_zip": "release_project_package.zip",
                "project_registry_signature": "release_project_registry.signature.b64",
            },
        },
    )
    _write(
        committee,
        {
            "metrics": {
                "external_benchmark_batch_job_summary_line": "Batch job runner: PASS | jobs=4 | completed=2 | failed=0 | reruns=1 | snapshots=3",
                "external_benchmark_batch_job_contract_pass": True,
                "external_benchmark_batch_job_count": 4,
                "external_benchmark_batch_completed_count": 2,
                "external_benchmark_batch_failed_count": 0,
                "external_benchmark_batch_rerun_count": 1,
            },
            "artifact_links": {
                "external_benchmark_batch_job_report_json": "committee_batch_job_report.json",
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
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
            str(midas),
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
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["project_registry_artifact_count"] == 8
    assert payload["summary"]["project_registry_approval_count"] == 2
    assert payload["summary"]["project_registry_package_sha256"] == "pkgsha256"
    assert payload["summary"]["project_registry_package_bytes"] == 4096
    assert payload["summary"]["project_registry_signature_verified"] is True
    assert payload["summary"]["external_benchmark_batch_job_contract_pass"] is True
    assert payload["summary"]["external_benchmark_batch_job_count"] == 4
    assert payload["summary"]["external_benchmark_batch_completed_count"] == 2
    assert payload["summary"]["external_benchmark_batch_failed_count"] == 0
    assert payload["summary"]["external_benchmark_batch_rerun_count"] == 1
    assert payload["artifacts"]["project_registry_report"] == "release_project_registry.json"
    assert payload["artifacts"]["project_package_zip"] == "release_project_package.zip"
    assert payload["artifacts"]["project_registry_signature"] == "release_project_registry.signature.b64"
    assert payload["artifacts"]["external_benchmark_batch_job_report_json"] == "committee_batch_job_report.json"
    assert any("project_pkg=4096B" in str(row.get("evidence", "")) for row in payload["observed_strengths"])
    governance_gap = next(row for row in payload["remaining_gaps"] if row["id"] == "GAP-P2-002")
    assert "project_registry_package_bytes=4096" in governance_gap["evidence"]
    assert out_md.exists()


def test_release_gap_report_surfaces_native_authoring_commercialization_lane(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "generate_release_gap_report.py"
    )
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    solver_session = tmp_path / "native_authoring_solver_session.json"
    ops_bundle = tmp_path / "native_authoring_ops_bundle.json"
    portfolio_report = tmp_path / "native_authoring_ops_portfolio.json"
    family_tracks = tmp_path / "native_authoring_family_tracks.json"
    runtime_submission = tmp_path / "native_authoring_runtime_submission_lane.json"
    runtime_writeback_depth = tmp_path / "native_authoring_runtime_writeback_depth_report.json"
    local_runtime_scenario_depth = (
        tmp_path / "native_authoring_local_runtime_scenario_depth_report.json"
    )
    local_variant_writeback_trace = (
        tmp_path / "native_authoring_local_variant_writeback_trace_report.json"
    )
    multi_project_runtime_writeback = (
        tmp_path / "native_authoring_multi_project_runtime_writeback_report.json"
    )
    solver_family_breadth = tmp_path / "native_authoring_solver_family_breadth_report.json"
    project_ops_service_snapshot = tmp_path / "project_ops_service_snapshot.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [freeze, promotion, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        ci,
        {
            "contract_pass": True,
            "all_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {},
            "frontend_payload": {},
        },
    )
    _write(commercial, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "deployment_model": {}})
    _write(
        solver_session,
        {
            "contract_pass": True,
            "summary_line": "Native authoring solver session: PASS | meshes=2 | cells=588 | combos=13 | family=KDS-2022",
            "authoring_controls": {
                "section_palette": [
                    "steel_h_600x200",
                    "steel_box_400x400x16",
                    "rc_column_700x700",
                    "rc_wall_300x3000",
                    "cft_box_700x700",
                    "deck_beam_500x250",
                ],
            },
            "summary": {
                "model_id": "native-authoring-sample-tower",
                "mesh_request_count": 2,
                "combo_count": 13,
                "load_case_count": 4,
                "loadcomb_line_count": 37,
                "family": "KDS-2022",
                "session_ready": True,
            },
            "authoring_summary": {
                "model_id": "native-authoring-sample-tower",
                "native_authoring_ready": True,
                "section_usage_counts": {
                    "rc_column_700x700": 20,
                    "steel_h_600x200": 15,
                },
                "member_type_counts": {
                    "beam": 15,
                    "column": 20,
                },
            },
            "mesh_session": {
                "request_count": 2,
                "total_estimated_cells": 588,
            },
            "load_combination_session": {
                "family": "KDS-2022",
                "runtime_summary": {
                    "combo_count": 13,
                    "runtime_case_count": 4,
                    "authoring_ready": True,
                },
                "loadcomb_preview_line_count": 37,
            },
            "artifacts": {
                "session_summary_json": "authoring/native_authoring_solver_session.json",
                "loadcomb_preview_mgt": "authoring/native_authoring_solver_session.loadcomb_preview.mgt",
            },
        },
    )
    _write(
        portfolio_report,
        {
            "contract_pass": True,
            "summary_line": "Native authoring ops portfolio: PASS | families=2 | complete=2 | ready=2 | job_ready=2 | submission_ready=2 | writeback_ready=2 | signature=2 | combos=21 | snapshots=3",
            "summary": {
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "project_count": 2,
                "complete_project_count": 2,
                "ready_family_count": 2,
                "signature_verified_count": 2,
                "package_reproducible_count": 1,
                "family_count": 2,
                "complete_family_count": 2,
                "release_ready_family_count": 2,
                "max_solver_combo_count": 21,
                "solver_combo_count": 34,
                "max_solver_mesh_request_count": 3,
                "solver_mesh_request_count": 5,
                "family_status_label": "sample_tower:ready, steel_braced_frame:ready",
            },
            "scan": {
                "summary": {
                    "unmatched_input_count": 1,
                },
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "commercialization_status": "ready",
                    "release_ready": True,
                    "ops_ready": True,
                    "contract_pass": False,
                    "reason_code": "PASS",
                    "solver_combo_count": 13,
                    "solver_mesh_request_count": 2,
                },
                {
                    "family_id": "steel_braced_frame",
                    "commercialization_status": "ready",
                    "release_ready": True,
                    "ops_ready": True,
                    "contract_pass": False,
                    "reason_code": "PASS",
                    "solver_combo_count": 21,
                    "solver_mesh_request_count": 3,
                },
            ],
            "artifacts": {
                "project_registry_portfolio_workspace_json": "project_registry_portfolio_workspace.json",
                "project_registry_index_json": "project_registry_index.json",
            },
        },
    )
    _write(
        ops_bundle,
        {
            "contract_pass": True,
            "summary_line": "Native authoring ops bundle: PASS | source=loaded | ready=True | solver_combos=13 | jobs=3 | snapshots=3 | package_artifacts=4",
            "checks": {
                "workspace_summary_ready_pass": True,
                "project_registry_signature_verified_pass": True,
            },
            "summary": {
                "workspace_artifact_count": 3,
                "solver_session_artifact_count": 2,
                "solver_combo_count": 13,
                "solver_mesh_request_count": 2,
                "solver_load_case_count": 4,
                "solver_loadcomb_line_count": 37,
                "job_count": 3,
                "snapshot_count": 3,
                "registry_artifact_count": 4,
                "registry_approval_count": 3,
                "registry_package_sha256": "authoringpkgsha256",
            },
            "inputs": {
                "workspace_summary": "authoring/native_authoring_workspace_summary.json",
                "workspace_summary_source_mode": "loaded",
                "loadcomb_preview_out": "authoring/native_authoring_solver_session.loadcomb_preview.mgt",
                "solver_session_source_mode": "generated",
                "job_manifest_out": "authoring/native_authoring_job_manifest.json",
                "batch_report_out": "authoring/native_authoring_batch_job_report.json",
                "project_registry_out": "authoring/native_authoring_project_registry.json",
                "project_package_out": "authoring/native_authoring_project_package.zip",
                "public_key_out": "signing/native_authoring_project_registry_ed25519.pub.pem",
                "signature_out": "signing/native_authoring_project_registry.signature.b64",
                "out": "authoring/native_authoring_ops_bundle.json",
            },
            "artifacts": {
                "workspace_summary_json": "authoring/native_authoring_workspace_summary.json",
                "solver_session_json": "authoring/native_authoring_solver_session.json",
                "solver_loadcomb_preview_mgt": "authoring/native_authoring_solver_session.loadcomb_preview.mgt",
                "job_manifest_json": "authoring/native_authoring_job_manifest.json",
                "batch_job_report_json": "authoring/native_authoring_batch_job_report.json",
                "project_registry_json": "authoring/native_authoring_project_registry.json",
                "project_package_zip": "authoring/native_authoring_project_package.zip",
                "project_registry_public_key": "signing/native_authoring_project_registry_ed25519.pub.pem",
                "project_registry_signature": "signing/native_authoring_project_registry.signature.b64",
            },
            "batch_job_report_summary": {
                "job_count": 3,
                "snapshot_count": 3,
            },
            "project_registry_summary": {
                "artifact_count": 4,
                "approval_count": 3,
                "package_sha256": "authoringpkgsha256",
                "package_bytes": 56191,
            },
        },
    )
    _write(
        family_tracks,
        {
            "contract_pass": True,
            "summary_line": "Native authoring family tracks: READY | families=2 | ready=2 | max_combos=21 | max_meshes=3",
            "summary": {
                "family_count": 2,
                "ready_family_count": 2,
                "max_solver_combo_count": 21,
                "max_solver_mesh_request_count": 3,
                "family_status_label": "sample_tower:ready, steel_braced_frame:ready",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "commercialization_status": "ready",
                    "family_ready": True,
                    "solver_combo_count": 13,
                    "solver_mesh_request_count": 2,
                },
                {
                    "family_id": "steel_braced_frame",
                    "commercialization_status": "ready",
                    "family_ready": True,
                    "solver_combo_count": 21,
                    "solver_mesh_request_count": 3,
                },
            ],
            "artifacts": {
                "native_authoring_family_tracks_json": "authoring/portfolio/native_authoring_family_tracks.json",
            },
        },
    )
    _write(
        runtime_submission,
        {
            "contract_pass": True,
            "summary_line": "Native authoring runtime submission lane: READY | submissions=2 | ready=2 | writeback_ready=2 | queue=1",
            "summary": {
                "runtime_submission_ready": True,
                "submission_count": 2,
                "ready_submission_count": 2,
                "submission_ready_count": 2,
                "writeback_ready_count": 2,
                "queue_count": 1,
                "family_status_label": "sample_tower:ready, steel_braced_frame:ready",
                "submission_status_label": "sample_tower:ready, steel_braced_frame:queued",
            },
            "submission_rows": [
                {
                    "family_id": "sample_tower",
                    "submission_status": "ready",
                    "runtime_ready": True,
                    "writeback_ready": True,
                },
                {
                    "family_id": "steel_braced_frame",
                    "submission_status": "queued",
                    "runtime_ready": True,
                    "writeback_ready": True,
                },
            ],
            "artifacts": {
                "native_authoring_runtime_submission_lane_json": "authoring/portfolio/native_authoring_runtime_submission_lane.json",
            },
        },
    )
    _write(
        runtime_writeback_depth,
        {
            "contract_pass": True,
            "summary_line": "Native authoring runtime writeback depth: PASS | families=2 | full_depth=2 | targeted=0 | registry=2 | signature=2 | repro=2 | snapshot=2 | queue_clear=1",
            "summary": {
                "runtime_writeback_depth_ready": True,
                "family_count": 2,
                "depth_ready_family_count": 2,
                "targeted_family_count": 0,
                "signature_verified_family_count": 2,
                "package_reproducible_family_count": 2,
                "snapshot_ready_family_count": 2,
                "queue_clear_family_count": 1,
                "family_status_label": "sample_tower:full, steel_braced_frame:full",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "runtime_writeback_depth_status": "full",
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
                {
                    "family_id": "steel_braced_frame",
                    "runtime_writeback_depth_status": "full",
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": False,
                },
            ],
            "artifacts": {
                "native_authoring_runtime_writeback_depth_report_json": "authoring/portfolio/native_authoring_runtime_writeback_depth_report.json",
            },
        },
    )
    _write(
        local_runtime_scenario_depth,
        {
            "contract_pass": True,
            "summary_line": "Native authoring local runtime scenario depth: PASS | families=2 | deep=2 | targeted=0 | trace_ready=2 | mesh_ready=2 | runtime_ready=2 | omitted=1",
            "summary": {
                "local_runtime_scenario_depth_ready": True,
                "family_count": 2,
                "depth_ready_family_count": 2,
                "targeted_family_count": 0,
                "trace_ready_family_count": 2,
                "mesh_trace_ready_family_count": 2,
                "runtime_ready_family_count": 2,
                "omitted_library_family_count": 1,
                "family_status_label": "sample_tower:deep, steel_braced_frame:deep",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "local_runtime_scenario_depth_status": "deep",
                    "trace_ready": True,
                    "mesh_trace_ready": True,
                    "runtime_ready": True,
                    "omitted_library_combination_count": 1,
                },
                {
                    "family_id": "steel_braced_frame",
                    "local_runtime_scenario_depth_status": "deep",
                    "trace_ready": True,
                    "mesh_trace_ready": True,
                    "runtime_ready": True,
                    "omitted_library_combination_count": 0,
                },
            ],
            "artifacts": {
                "native_authoring_local_runtime_scenario_depth_report_json": "authoring/portfolio/native_authoring_local_runtime_scenario_depth_report.json",
            },
        },
    )
    _write(
        local_variant_writeback_trace,
        {
            "contract_pass": True,
            "summary_line": "Native authoring local variant/writeback trace: PASS | families=2 | deep=2 | targeted=0 | workspace_variant=2 | solver_variant=2 | writeback_trace=2 | active_multi=2 | combo_multi=2 | signed=2 | omitted=1",
            "summary": {
                "local_variant_writeback_trace_ready": True,
                "family_count": 2,
                "deep_ready_family_count": 2,
                "targeted_family_count": 0,
                "workspace_variant_ready_family_count": 2,
                "solver_variant_ready_family_count": 2,
                "writeback_trace_ready_family_count": 2,
                "active_multi_family_count": 2,
                "combo_multi_family_count": 2,
                "signed_writeback_family_count": 2,
                "omitted_library_family_count": 1,
                "family_status_label": "sample_tower:deep, steel_braced_frame:deep",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "local_variant_writeback_trace_status": "deep",
                    "workspace_variant_ready": True,
                    "solver_variant_ready": True,
                    "writeback_trace_ready": True,
                    "workspace_active_family_count": 2,
                    "solver_combo_family_count": 3,
                    "signature_verified": True,
                    "omitted_library_combination_count": 1,
                },
                {
                    "family_id": "steel_braced_frame",
                    "local_variant_writeback_trace_status": "deep",
                    "workspace_variant_ready": True,
                    "solver_variant_ready": True,
                    "writeback_trace_ready": True,
                    "workspace_active_family_count": 2,
                    "solver_combo_family_count": 3,
                    "signature_verified": True,
                    "omitted_library_combination_count": 0,
                },
            ],
            "artifacts": {
                "native_authoring_local_variant_writeback_trace_report_json": "authoring/portfolio/native_authoring_local_variant_writeback_trace_report.json",
            },
        },
    )
    _write(
        solver_family_breadth,
        {
            "contract_pass": True,
            "summary_line": "Native authoring solver family breadth: PASS | families=2 | broad_ready=2 | full_breadth=1 | solver_ready=2 | combo_broad=2 | mesh_coverage=2 | mesh_broad=1 | member_multi=2 | queue=0",
            "summary": {
                "solver_family_breadth_ready": True,
                "family_count": 2,
                "broad_ready_family_count": 2,
                "full_breadth_family_count": 1,
                "mesh_broad_family_count": 1,
                "member_multi_family_count": 2,
                "family_status_label": "sample_tower:broad, steel_braced_frame:broad",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "solver_family_breadth_status": "broad",
                    "broad_solver_family_ready": True,
                    "member_family_breadth_ready": True,
                },
                {
                    "family_id": "steel_braced_frame",
                    "solver_family_breadth_status": "broad",
                    "broad_solver_family_ready": True,
                    "member_family_breadth_ready": True,
                },
            ],
            "artifacts": {
                "native_authoring_solver_family_breadth_report_json": "authoring/portfolio/native_authoring_solver_family_breadth_report.json",
            },
        },
    )
    _write(
        multi_project_runtime_writeback,
        {
            "contract_pass": True,
            "summary_line": "Native authoring multi-project runtime/writeback: PASS | projects=2 | families=2 | project_families=2 | full_depth=2 | ready_projects=2 | signature=2 | repro=2 | snapshot=2 | queue_clear=2",
            "summary": {
                "multi_project_runtime_writeback_ready": True,
                "project_count": 2,
                "family_count": 2,
                "project_family_count": 2,
                "full_depth_project_family_count": 2,
                "targeted_project_family_count": 0,
                "ready_project_count": 2,
                "signature_verified_project_count": 2,
                "package_reproducible_project_count": 2,
                "snapshot_ready_project_count": 2,
                "queue_clear_project_count": 2,
                "project_status_label": "sample_tower:ready, steel_braced_frame:ready",
            },
            "project_rows": [
                {"project_id": "PJT-001", "project_ready": True},
                {"project_id": "PJT-002", "project_ready": True},
            ],
            "project_family_rows": [
                {"project_id": "PJT-001", "family_id": "sample_tower", "full_depth_ready": True},
                {"project_id": "PJT-002", "family_id": "steel_braced_frame", "full_depth_ready": True},
            ],
            "artifacts": {
                "native_authoring_multi_project_runtime_writeback_report_json": (
                    "authoring/portfolio/native_authoring_multi_project_runtime_writeback_report.json"
                ),
            },
        },
    )
    writeback_breadth = tmp_path / "native_authoring_writeback_breadth_report.json"
    _write(
        writeback_breadth,
        {
            "contract_pass": True,
            "summary_line": "Native authoring writeback breadth: PASS | families=2 | broad_ready=2 | full_breadth=1 | mesh_broad=1",
            "summary": {
                "writeback_breadth_ready": True,
                "family_count": 2,
                "broad_ready_family_count": 2,
                "full_breadth_family_count": 1,
                "mesh_broad_family_count": 1,
                "family_status_label": "sample_tower:broad, steel_braced_frame:broad",
            },
            "family_rows": [
                {"family_id": "sample_tower", "writeback_breadth_status": "broad", "broad_writeback_ready": True},
                {
                    "family_id": "steel_braced_frame",
                    "writeback_breadth_status": "broad",
                    "broad_writeback_ready": True,
                },
            ],
            "artifacts": {
                "native_authoring_writeback_breadth_report_json": "authoring/portfolio/native_authoring_writeback_breadth_report.json",
            },
        },
    )
    _write(
        project_ops_service_snapshot,
        {
            "contract_pass": True,
            "summary_line": "Project ops service snapshot: READY | projects=3 | families=2 | endpoints=4",
            "summary": {
                "service_ready": True,
                "project_count": 3,
                "family_count": 2,
                "ready_family_count": 2,
                "endpoint_count": 4,
                "family_status_label": "sample_tower:ready, steel_braced_frame:ready",
            },
            "project_rows": [
                {"project_id": "PJT-001"},
                {"project_id": "PJT-002"},
                {"project_id": "PJT-003"},
            ],
            "family_rows": [
                {"family_id": "sample_tower", "commercialization_status": "ready"},
                {"family_id": "steel_braced_frame", "commercialization_status": "ready"},
            ],
            "endpoint_rows": [
                {"endpoint_id": "health"},
                {"endpoint_id": "summary"},
                {"endpoint_id": "projects"},
                {"endpoint_id": "families"},
            ],
            "artifacts": {
                "project_ops_service_snapshot_json": "project_ops_service_snapshot.json",
            },
            "paths": {
                "snapshot_json": "project_ops_service_snapshot.json",
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
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
            str(midas),
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
            "--native-authoring-solver-session-report",
            str(solver_session),
            "--native-authoring-ops-bundle-report",
            str(ops_bundle),
            "--native-authoring-portfolio-report",
            str(portfolio_report),
            "--native-authoring-family-tracks-report",
            str(family_tracks),
            "--native-authoring-runtime-submission-report",
            str(runtime_submission),
            "--native-authoring-runtime-writeback-depth-report",
            str(runtime_writeback_depth),
            "--native-authoring-local-runtime-scenario-depth-report",
            str(local_runtime_scenario_depth),
            "--native-authoring-local-variant-writeback-trace-report",
            str(local_variant_writeback_trace),
            "--native-authoring-multi-project-runtime-writeback-report",
            str(multi_project_runtime_writeback),
            "--native-authoring-solver-family-breadth-report",
            str(solver_family_breadth),
            "--native-authoring-writeback-breadth-report",
            str(writeback_breadth),
            "--project-ops-service-snapshot",
            str(project_ops_service_snapshot),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["native_authoring_commercialization_status"] == "ready"
    assert payload["summary"]["native_authoring_lane_ready"] is True
    assert (
        payload["summary"]["native_authoring_solver_session_summary_line"]
        == "Native authoring solver session: PASS | meshes=2 | cells=588 | combos=13 | family=KDS-2022"
    )
    assert (
        payload["summary"]["native_authoring_ops_bundle_summary_line"]
        == "Native authoring ops bundle: PASS | source=loaded | ready=True | solver_combos=13 | jobs=3 | snapshots=3 | package_artifacts=4"
    )
    assert payload["summary"]["native_authoring_solver_session_total_estimated_cells"] == 588
    assert payload["summary"]["native_authoring_ops_bundle_job_count"] == 3
    assert payload["summary"]["native_authoring_ops_bundle_registry_package_bytes"] == 56191
    assert payload["summary"]["native_authoring_palette_family_count"] == 4
    assert payload["summary"]["native_authoring_active_family_count"] == 2
    assert payload["summary"]["native_authoring_member_type_label"] == "beam, column"
    assert payload["summary"]["native_authoring_portfolio_project_count"] == 2
    assert payload["summary"]["native_authoring_portfolio_unmatched_input_count"] == 1
    assert payload["summary"]["native_authoring_portfolio_family_count"] == 2
    assert payload["summary"]["native_authoring_portfolio_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_portfolio_max_solver_combo_count"] == 21
    assert payload["summary"]["native_authoring_portfolio_max_solver_mesh_request_count"] == 3
    assert payload["summary"]["native_authoring_portfolio_release_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_portfolio_family_status_label"] == "sample_tower:ready, steel_braced_frame:ready"
    assert payload["summary"]["native_authoring_family_tracks_attached"] is True
    assert (
        payload["summary"]["native_authoring_family_tracks_summary_line"]
        == "Native authoring family tracks: READY | families=2 | ready=2 | max_combos=21 | max_meshes=3"
    )
    assert payload["summary"]["native_authoring_family_track_count"] == 2
    assert payload["summary"]["native_authoring_family_track_ready_count"] == 2
    assert payload["summary"]["native_authoring_family_track_max_solver_combo_count"] == 21
    assert payload["summary"]["native_authoring_family_track_max_solver_mesh_request_count"] == 3
    assert payload["summary"]["native_authoring_family_track_status_label"] == "sample_tower:ready, steel_braced_frame:ready"
    assert payload["summary"]["native_authoring_runtime_submission_attached"] is True
    assert payload["summary"]["native_authoring_runtime_submission_ready"] is True
    assert (
        payload["summary"]["native_authoring_runtime_submission_summary_line"]
        == "Native authoring runtime submission lane: READY | submissions=2 | ready=2 | writeback_ready=2 | queue=1"
    )
    assert payload["summary"]["native_authoring_runtime_submission_count"] == 2
    assert payload["summary"]["native_authoring_runtime_submission_ready_count"] == 2
    assert payload["summary"]["native_authoring_runtime_writeback_ready_count"] == 2
    assert payload["summary"]["native_authoring_runtime_submission_queue_count"] == 1
    assert payload["summary"]["native_authoring_runtime_family_status_label"] == "sample_tower:ready, steel_braced_frame:ready"
    assert payload["summary"]["native_authoring_runtime_submission_status_label"] == "sample_tower:ready, steel_braced_frame:queued"
    assert payload["summary"]["native_authoring_runtime_writeback_depth_attached"] is True
    assert payload["summary"]["native_authoring_runtime_writeback_depth_ready"] is True
    assert (
        payload["summary"]["native_authoring_runtime_writeback_depth_summary_line"]
        == "Native authoring runtime writeback depth: PASS | families=2 | full_depth=2 | targeted=0 | registry=2 | signature=2 | repro=2 | snapshot=2 | queue_clear=1"
    )
    assert payload["summary"]["native_authoring_runtime_writeback_depth_family_count"] == 2
    assert payload["summary"]["native_authoring_runtime_writeback_depth_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_runtime_writeback_depth_targeted_family_count"] == 0
    assert payload["summary"]["native_authoring_runtime_writeback_depth_signature_family_count"] == 2
    assert payload["summary"]["native_authoring_runtime_writeback_depth_repro_family_count"] == 2
    assert payload["summary"]["native_authoring_runtime_writeback_depth_snapshot_family_count"] == 2
    assert payload["summary"]["native_authoring_runtime_writeback_depth_queue_clear_family_count"] == 1
    assert payload["summary"]["native_authoring_runtime_writeback_depth_status_label"] == (
        "sample_tower:full, steel_braced_frame:full"
    )
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_attached"] is True
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_ready"] is True
    assert (
        payload["summary"]["native_authoring_local_runtime_scenario_depth_summary_line"]
        == "Native authoring local runtime scenario depth: PASS | families=2 | deep=2 | targeted=0 | trace_ready=2 | mesh_ready=2 | runtime_ready=2 | omitted=1"
    )
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_family_count"] == 2
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_targeted_family_count"] == 0
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_trace_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_mesh_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_runtime_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_omitted_family_count"] == 1
    assert payload["summary"]["native_authoring_local_runtime_scenario_depth_status_label"] == (
        "sample_tower:deep, steel_braced_frame:deep"
    )
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_attached"] is True
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_ready"] is True
    assert (
        payload["summary"]["native_authoring_local_variant_writeback_trace_summary_line"]
        == "Native authoring local variant/writeback trace: PASS | families=2 | deep=2 | targeted=0 | workspace_variant=2 | solver_variant=2 | writeback_trace=2 | active_multi=2 | combo_multi=2 | signed=2 | omitted=1"
    )
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_targeted_family_count"] == 0
    assert payload["summary"]["native_authoring_local_variant_workspace_variant_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_solver_variant_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_ready_family_trace_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_active_multi_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_combo_multi_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_signed_writeback_family_count"] == 2
    assert payload["summary"]["native_authoring_local_variant_trace_omitted_family_count"] == 1
    assert payload["summary"]["native_authoring_local_variant_writeback_trace_status_label"] == (
        "sample_tower:deep, steel_braced_frame:deep"
    )
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_attached"] is True
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_ready"] is True
    assert (
        payload["summary"]["native_authoring_multi_project_runtime_writeback_summary_line"]
        == "Native authoring multi-project runtime/writeback: PASS | projects=2 | families=2 | project_families=2 | full_depth=2 | ready_projects=2 | signature=2 | repro=2 | snapshot=2 | queue_clear=2"
    )
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_project_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_project_family_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_full_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_ready_project_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_signature_project_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_repro_project_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_snapshot_project_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_queue_clear_project_count"] == 2
    assert payload["summary"]["native_authoring_multi_project_runtime_writeback_status_label"] == (
        "sample_tower:ready, steel_braced_frame:ready"
    )
    assert payload["summary"]["native_authoring_solver_family_breadth_attached"] is True
    assert payload["summary"]["native_authoring_solver_family_breadth_ready"] is True
    assert (
        payload["summary"]["native_authoring_solver_family_breadth_summary_line"]
        == "Native authoring solver family breadth: PASS | families=2 | broad_ready=2 | full_breadth=1 | solver_ready=2 | combo_broad=2 | mesh_coverage=2 | mesh_broad=1 | member_multi=2 | queue=0"
    )
    assert payload["summary"]["native_authoring_solver_family_breadth_family_count"] == 2
    assert payload["summary"]["native_authoring_solver_family_breadth_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_solver_family_breadth_full_family_count"] == 1
    assert payload["summary"]["native_authoring_solver_family_breadth_mesh_broad_family_count"] == 1
    assert payload["summary"]["native_authoring_solver_family_breadth_member_multi_family_count"] == 2
    assert payload["summary"]["native_authoring_solver_family_breadth_status_label"] == (
        "sample_tower:broad, steel_braced_frame:broad"
    )
    assert payload["summary"]["native_authoring_writeback_breadth_attached"] is True
    assert payload["summary"]["native_authoring_writeback_breadth_ready"] is True
    assert (
        payload["summary"]["native_authoring_writeback_breadth_summary_line"]
        == "Native authoring writeback breadth: PASS | families=2 | broad_ready=2 | full_breadth=1 | mesh_broad=1"
    )
    assert payload["summary"]["native_authoring_writeback_breadth_family_count"] == 2
    assert payload["summary"]["native_authoring_writeback_breadth_ready_family_count"] == 2
    assert payload["summary"]["native_authoring_writeback_breadth_full_family_count"] == 1
    assert payload["summary"]["native_authoring_writeback_breadth_mesh_broad_family_count"] == 1
    assert payload["summary"]["native_authoring_writeback_breadth_status_label"] == (
        "sample_tower:broad, steel_braced_frame:broad"
    )
    assert payload["summary"]["project_ops_service_attached"] is True
    assert payload["summary"]["project_ops_service_ready"] is True
    assert "sample_tower:ready" in payload["summary"]["project_ops_service_family_status_label"]
    assert "steel_braced_frame:ready" in payload["summary"]["project_ops_service_family_status_label"]
    assert payload["summary"]["project_ops_service_summary_line"].startswith(
        "Project ops service snapshot: READY | projects=3 | families="
    )
    assert payload["summary"]["project_ops_service_summary_line"].endswith("| endpoints=4")
    assert payload["summary"]["project_ops_service_project_count"] == 3
    assert payload["summary"]["project_ops_service_family_count"] >= 2
    assert payload["summary"]["project_ops_service_ready_family_count"] >= 2
    assert payload["summary"]["project_ops_service_endpoint_count"] == 4
    assert payload["summary"]["native_authoring_ready_family_count_alignment_label"].startswith(
        "portfolio=2 | tracks=2 | runtime=2 | service="
    )
    assert "portfolio=sample_tower:ready, steel_braced_frame:ready" in payload["summary"]["native_authoring_family_status_alignment_label"]
    assert "runtime=sample_tower:ready, steel_braced_frame:ready" in payload["summary"]["native_authoring_family_status_alignment_label"]
    assert "service=sample_tower:ready" in payload["summary"]["native_authoring_family_status_alignment_label"]
    assert payload["summary"]["native_authoring_surface_consistency_ready"] is False
    assert payload["summary"]["native_authoring_surface_consistency_aligned_family_count"] == 2
    assert payload["summary"]["native_authoring_surface_consistency_expected_family_count"] == 2
    assert (
        payload["summary"]["native_authoring_surface_consistency_summary_line"]
        == "Native authoring surface consistency: CHECK | aligned=2/2 | portfolio_ready=2 | tracks_ready=2 | runtime_ready=2 | writeback_ready=2 | service_ready=2 | queue=1"
    )
    assert payload["artifacts"]["native_authoring_ops_bundle_json"] == "authoring/native_authoring_ops_bundle.json"
    assert payload["artifacts"]["native_authoring_workspace_summary_json"] == "authoring/native_authoring_workspace_summary.json"
    assert payload["artifacts"]["native_authoring_solver_session_json"] == "authoring/native_authoring_solver_session.json"
    assert (
        payload["artifacts"]["native_authoring_solver_loadcomb_preview_mgt"]
        == "authoring/native_authoring_solver_session.loadcomb_preview.mgt"
    )
    assert payload["artifacts"]["native_authoring_job_manifest_json"] == "authoring/native_authoring_job_manifest.json"
    assert (
        payload["artifacts"]["native_authoring_batch_job_report_json"]
        == "authoring/native_authoring_batch_job_report.json"
    )
    assert payload["artifacts"]["native_authoring_project_registry_json"] == "authoring/native_authoring_project_registry.json"
    assert payload["artifacts"]["native_authoring_project_package_zip"] == "authoring/native_authoring_project_package.zip"
    assert (
        payload["artifacts"]["native_authoring_project_registry_signature"]
        == "signing/native_authoring_project_registry.signature.b64"
    )
    assert payload["artifacts"]["native_authoring_portfolio_json"] == str(portfolio_report)
    assert payload["artifacts"]["native_authoring_portfolio_workspace_json"] == "project_registry_portfolio_workspace.json"
    assert (
        payload["artifacts"]["native_authoring_family_tracks_json"]
        == "authoring/portfolio/native_authoring_family_tracks.json"
    )
    assert (
        payload["artifacts"]["native_authoring_runtime_submission_lane_json"]
        == "authoring/portfolio/native_authoring_runtime_submission_lane.json"
    )
    assert (
        payload["artifacts"]["native_authoring_runtime_writeback_depth_report_json"]
        == "authoring/portfolio/native_authoring_runtime_writeback_depth_report.json"
    )
    assert (
        payload["artifacts"]["native_authoring_local_runtime_scenario_depth_report_json"]
        == "authoring/portfolio/native_authoring_local_runtime_scenario_depth_report.json"
    )
    assert (
        payload["artifacts"]["native_authoring_local_variant_writeback_trace_report_json"]
        == "authoring/portfolio/native_authoring_local_variant_writeback_trace_report.json"
    )
    assert (
        payload["artifacts"]["native_authoring_multi_project_runtime_writeback_report_json"]
        == "authoring/portfolio/native_authoring_multi_project_runtime_writeback_report.json"
    )
    assert (
        payload["artifacts"]["native_authoring_solver_family_breadth_report_json"]
        == "authoring/portfolio/native_authoring_solver_family_breadth_report.json"
    )
    assert (
        payload["artifacts"]["native_authoring_writeback_breadth_report_json"]
        == "authoring/portfolio/native_authoring_writeback_breadth_report.json"
    )
    assert payload["artifacts"]["project_ops_service_snapshot_json"] == "project_ops_service_snapshot.json"
    native_authoring_strength = next(
        row
        for row in payload["observed_strengths"]
        if row["title"] == "Native authoring commercialization lane is attached"
    )
    assert "status=ready" in native_authoring_strength["evidence"]
    assert "palette_families=4" in native_authoring_strength["evidence"]
    assert "portfolio_projects=2" in native_authoring_strength["evidence"]
    assert "portfolio_families=2" in native_authoring_strength["evidence"]
    assert "max_combos=21" in native_authoring_strength["evidence"]
    native_authoring_gap = next(row for row in payload["remaining_gaps"] if row["id"] == "GAP-P1-006")
    assert native_authoring_gap["status"] == "closed"
    assert "commercialization_status=ready" in native_authoring_gap["evidence"]
    assert "palette_families=4" in native_authoring_gap["evidence"]
    assert "portfolio_unmatched=1" in native_authoring_gap["evidence"]
    assert "portfolio_families=2" in native_authoring_gap["evidence"]
    assert "family_status=sample_tower:ready, steel_braced_frame:ready" in native_authoring_gap["evidence"]
    assert "tracks=attached:True,families=2,ready=2,max_combos=21,max_meshes=3" in native_authoring_gap["evidence"]
    assert "runtime_lane=attached:True,ready=True,submissions=2,writeback_ready=2,queue=1" in native_authoring_gap["evidence"]
    assert "runtime_writeback_depth=attached:True,ready=True,families=2,full=2,signature=2,repro=2,snapshot=2,queue_clear=1" in native_authoring_gap["evidence"]
    assert "local_runtime_depth=attached:True,ready=True,families=2,deep=2,targeted=0,trace=2,mesh=2,runtime=2,omitted=1" in native_authoring_gap["evidence"]
    assert "local_variant_trace=attached:True,ready=True,families=2,deep=2,targeted=0,workspace_variant=2,solver_variant=2,writeback_trace=2,active_multi=2,combo_multi=2,signed=2,omitted=1" in native_authoring_gap["evidence"]
    assert "multi_project_runtime=attached:True,ready=True,projects=2,project_families=2,full=2,ready_projects=2,signature=2,repro=2,snapshot=2,queue_clear=2" in native_authoring_gap["evidence"]
    assert "solver_family_breadth=attached:True,ready=True,families=2,broad_ready=2,full=1,mesh_broad=1" in native_authoring_gap["evidence"]
    assert "writeback_breadth=attached:True,ready=True,families=2,broad_ready=2,full=1,mesh_broad=1" in native_authoring_gap["evidence"]
    assert "ops_service=attached:True,ready=True,projects=3,families=2,endpoints=4" in native_authoring_gap["evidence"]

    markdown = out_md.read_text(encoding="utf-8")
    assert "Native authoring commercialization lane" in markdown
    assert "Native authoring solver session: PASS | meshes=2 | cells=588 | combos=13 | family=KDS-2022" in markdown
    assert "Native authoring ops bundle: PASS | source=loaded | ready=True | solver_combos=13 | jobs=3 | snapshots=3 | package_artifacts=4" in markdown
    assert "Native authoring breadth" in markdown
    assert "Native authoring portfolio" in markdown
    assert "Native authoring portfolio families" in markdown
    assert "Native authoring runtime submission lane" in markdown
    assert "Native authoring runtime writeback depth" in markdown
    assert "Native authoring local runtime scenario depth" in markdown
    assert "Native authoring local variant/writeback trace" in markdown
    assert "Native authoring multi-project runtime/writeback" in markdown
    assert "Native authoring solver family breadth" in markdown
    assert "Native authoring writeback breadth" in markdown
    assert "Native authoring family tracks" in markdown
    assert "Project ops service snapshot" in markdown
    assert "family_status=`sample_tower:ready, steel_braced_frame:ready`" in markdown


def test_native_authoring_default_portfolio_surface_tracks_commercialization_artifacts() -> None:
    portfolio_report = json.loads(DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO.read_text(encoding="utf-8"))
    family_tracks_report = json.loads(DEFAULT_NATIVE_AUTHORING_FAMILY_TRACKS.read_text(encoding="utf-8"))
    runtime_submission_report = json.loads(
        DEFAULT_NATIVE_AUTHORING_RUNTIME_SUBMISSION_LANE.read_text(encoding="utf-8")
    )
    runtime_writeback_depth_report = json.loads(
        DEFAULT_NATIVE_AUTHORING_RUNTIME_WRITEBACK_DEPTH_REPORT.read_text(encoding="utf-8")
    )
    local_runtime_scenario_depth_report = json.loads(
        DEFAULT_NATIVE_AUTHORING_LOCAL_RUNTIME_SCENARIO_DEPTH_REPORT.read_text(encoding="utf-8")
    )
    local_variant_writeback_trace_report = (
        json.loads(
            DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT.read_text(
                encoding="utf-8"
            )
        )
        if DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT.exists()
        else {}
    )
    multi_project_runtime_writeback_report = json.loads(
        DEFAULT_NATIVE_AUTHORING_MULTI_PROJECT_RUNTIME_WRITEBACK_REPORT.read_text(encoding="utf-8")
    )
    solver_family_breadth_report = json.loads(
        DEFAULT_NATIVE_AUTHORING_SOLVER_FAMILY_BREADTH_REPORT.read_text(encoding="utf-8")
    )
    writeback_breadth_report = json.loads(
        DEFAULT_NATIVE_AUTHORING_WRITEBACK_BREADTH_REPORT.read_text(encoding="utf-8")
    )
    project_ops_service_snapshot_report = json.loads(
        DEFAULT_PROJECT_OPS_SERVICE_SNAPSHOT.read_text(encoding="utf-8")
    )

    surface = _native_authoring_lane_surface(
        {},
        {},
        portfolio_report=portfolio_report,
        family_tracks_report=family_tracks_report,
        runtime_submission_report=runtime_submission_report,
        runtime_writeback_depth_report=runtime_writeback_depth_report,
        local_runtime_scenario_depth_report=local_runtime_scenario_depth_report,
        local_variant_writeback_trace_report=local_variant_writeback_trace_report,
        multi_project_runtime_writeback_report=multi_project_runtime_writeback_report,
        solver_family_breadth_report=solver_family_breadth_report,
        writeback_breadth_report=writeback_breadth_report,
        project_ops_service_snapshot_report=project_ops_service_snapshot_report,
        solver_session_path=Path("native_authoring_solver_session.json"),
        ops_bundle_path=Path("native_authoring_ops_bundle.json"),
        portfolio_path=DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO,
        family_tracks_path=DEFAULT_NATIVE_AUTHORING_FAMILY_TRACKS,
        runtime_submission_path=DEFAULT_NATIVE_AUTHORING_RUNTIME_SUBMISSION_LANE,
        runtime_writeback_depth_path=DEFAULT_NATIVE_AUTHORING_RUNTIME_WRITEBACK_DEPTH_REPORT,
        local_runtime_scenario_depth_path=DEFAULT_NATIVE_AUTHORING_LOCAL_RUNTIME_SCENARIO_DEPTH_REPORT,
        local_variant_writeback_trace_path=DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT,
        multi_project_runtime_writeback_path=DEFAULT_NATIVE_AUTHORING_MULTI_PROJECT_RUNTIME_WRITEBACK_REPORT,
        solver_family_breadth_path=DEFAULT_NATIVE_AUTHORING_SOLVER_FAMILY_BREADTH_REPORT,
        writeback_breadth_path=DEFAULT_NATIVE_AUTHORING_WRITEBACK_BREADTH_REPORT,
        project_ops_service_snapshot_path=DEFAULT_PROJECT_OPS_SERVICE_SNAPSHOT,
    )

    portfolio_summary = portfolio_report["summary"]
    family_tracks_summary = family_tracks_report["summary"]
    runtime_submission_summary = runtime_submission_report["summary"]

    assert DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO == Path(
        "implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json"
    )
    assert surface["native_authoring_portfolio_ready_family_count"] == portfolio_summary["ready_family_count"]
    assert surface["native_authoring_portfolio_family_status_label"].startswith(
        "belt_truss_mega_frame:ready"
    )
    assert "rc_wall_core:ready" in surface["native_authoring_portfolio_family_status_label"]
    assert surface["native_authoring_portfolio_max_solver_combo_count"] == portfolio_summary["max_solver_combo_count"]
    assert (
        surface["native_authoring_portfolio_max_solver_mesh_request_count"]
        == portfolio_summary["max_solver_mesh_request_count"]
    )
    assert surface["native_authoring_family_track_ready_count"] == family_tracks_summary["ready_family_count"]
    assert surface["native_authoring_runtime_family_status_label"].startswith(
        "belt_truss_mega_frame:ready"
    )
    assert "rc_wall_core:ready" in surface["native_authoring_runtime_family_status_label"]
    assert surface["project_ops_service_ready_family_count"] == portfolio_summary["family_count"]
    assert surface["project_ops_service_family_status_label"].startswith(
        "belt_truss_mega_frame:ready"
    )
    assert "rc_wall_core:ready" in surface["project_ops_service_family_status_label"]
    assert surface["native_authoring_runtime_writeback_depth_attached"] is True
    assert surface["native_authoring_runtime_writeback_depth_ready"] is True
    assert surface["native_authoring_runtime_writeback_depth_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_runtime_scenario_depth_attached"] is True
    assert surface["native_authoring_local_runtime_scenario_depth_ready"] is True
    assert surface["native_authoring_local_runtime_scenario_depth_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_writeback_trace_attached"] is True
    assert surface["native_authoring_local_variant_writeback_trace_ready"] is True
    assert surface["native_authoring_local_variant_writeback_trace_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_writeback_trace_ready_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_workspace_variant_ready_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_solver_variant_ready_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_writeback_trace_ready_family_trace_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_active_multi_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_combo_multi_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_signed_writeback_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_local_variant_trace_omitted_family_count"] == 3
    assert "families=8" in surface["native_authoring_local_variant_writeback_trace_summary_line"]
    assert "active_multi=8" in surface["native_authoring_local_variant_writeback_trace_summary_line"]
    assert surface["native_authoring_multi_project_runtime_writeback_attached"] is True
    assert surface["native_authoring_multi_project_runtime_writeback_ready"] is True
    assert surface["native_authoring_multi_project_runtime_writeback_project_count"] >= portfolio_summary["family_count"]
    assert surface["native_authoring_multi_project_runtime_writeback_project_family_count"] >= portfolio_summary["family_count"]
    assert surface["native_authoring_solver_family_breadth_attached"] is True
    assert surface["native_authoring_solver_family_breadth_ready"] is True
    assert surface["native_authoring_solver_family_breadth_family_count"] == portfolio_summary["family_count"]
    assert surface["native_authoring_writeback_breadth_attached"] is True
    assert surface["native_authoring_writeback_breadth_ready"] is True
    assert surface["native_authoring_writeback_breadth_family_count"] == portfolio_summary["family_count"]
    assert surface["project_ops_service_project_count"] >= portfolio_summary["family_count"]
    assert surface["project_ops_service_family_count"] == portfolio_summary["family_count"]
    assert "families=8" in surface["project_ops_service_summary_line"]
    expected_alignment = (
        f"portfolio={portfolio_summary['family_count']} | "
        f"tracks={family_tracks_summary['family_count']} | "
        f"runtime={runtime_submission_summary['family_count']} | "
        f"service={portfolio_summary['family_count']}"
    )
    assert surface["native_authoring_ready_family_count_alignment_label"] == expected_alignment
    assert "portfolio=belt_truss_mega_frame:ready" in surface["native_authoring_family_status_alignment_label"]
    assert "runtime=belt_truss_mega_frame:ready" in surface["native_authoring_family_status_alignment_label"]
    assert "service=belt_truss_mega_frame:ready" in surface["native_authoring_family_status_alignment_label"]


def test_release_gap_report_surfaces_commercial_workflow_breadth_summary(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "generate_release_gap_report.py"
    )
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"
    commercial_workflow_report = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "commercial_workflow_breadth_report.json"
    )

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [
        ci,
        freeze,
        promotion,
        authority,
        hip,
        midas,
        construction,
        diaphragm,
        repro,
        registry,
        kds,
        solver_hip,
        rc,
        quality,
    ]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {"mode": "engineer_in_the_loop_accelerated_coverage"},
        },
    )
    commercial_workflow_report.parent.mkdir(parents=True, exist_ok=True)
    _write(
        commercial_workflow_report,
        {
            "summary_line": (
                "Commercial workflow breadth: CHECK | construction_stage=yes(history=4,max_shortening=18.400mm) | "
                "rail_tunnel=no(serviceability=watchlist,maintenance=high,actions=3) | "
                "design_redesign_loop=no(traceability=0.620,ng_members=2,suggestions=5,strengthen=3,reduce=2,clauses=6)"
            ),
            "checks": {"pass": True},
            "summary": {
                "construction_stage_ready": True,
                "construction_stage_history_snapshot_count": 4,
                "construction_stage_max_differential_shortening_mm": 18.4,
                "rail_tunnel_ready": False,
                "rail_tunnel_serviceability_status": "watchlist",
                "rail_tunnel_maintenance_priority": "high",
                "rail_tunnel_recommended_action_count": 3,
                "design_redesign_loop_ready": False,
                "design_report_traceability_ratio": 0.62,
                "design_report_ng_member_count": 2,
                "section_optimizer_suggestion_count": 5,
                "section_optimizer_strengthen_count": 3,
                "section_optimizer_reduce_count": 2,
                "governing_clause_count": 6,
            },
            "artifacts": {
                "viewer_surface_json": "release/visualization/structural_optimization_viewer.json",
                "workbench_surface_md": "implementation/phase1/release/commercial_workflow_breadth_appendix.md",
            },
            "rows": [
                {"surface": "construction_stage", "ready": True, "signal": "history_snapshot_count", "value": 4},
                {"surface": "rail_tunnel", "ready": False, "signal": "maintenance_priority", "value": "high"},
                {"surface": "design_redesign_loop", "ready": False, "signal": "traceability_ratio", "value": 0.62},
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
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
            str(midas),
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
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["commercial_workflow_breadth_summary_line"].startswith("Commercial workflow breadth: CHECK")
    assert summary["commercial_workflow_breadth_pass"] is True
    assert summary["commercial_workflow_breadth_report_path"] == "implementation/phase1/release/commercial_workflow_breadth_report.json"
    assert summary["commercial_workflow_breadth_ready_surface_count"] == 1
    assert summary["commercial_workflow_breadth_total_surface_count"] == 3
    assert summary["commercial_workflow_breadth_gap_status"] == "narrowing"
    assert summary["commercial_workflow_breadth_summary"]["construction_stage_ready"] is True
    assert summary["commercial_workflow_breadth_summary"]["construction_stage_history_snapshot_count"] == 4
    assert summary["commercial_workflow_breadth_summary"]["construction_stage_max_differential_shortening_mm"] == 18.4
    assert summary["commercial_workflow_breadth_summary"]["rail_tunnel_ready"] is False
    assert summary["commercial_workflow_breadth_summary"]["rail_tunnel_serviceability_status"] == "watchlist"
    assert summary["commercial_workflow_breadth_summary"]["rail_tunnel_maintenance_priority"] == "high"
    assert summary["commercial_workflow_breadth_summary"]["rail_tunnel_recommended_action_count"] == 3
    assert summary["commercial_workflow_breadth_summary"]["design_redesign_loop_ready"] is False
    assert summary["commercial_workflow_breadth_summary"]["design_report_traceability_ratio"] == 0.62
    assert summary["commercial_workflow_breadth_summary"]["design_report_ng_member_count"] == 2
    assert summary["commercial_workflow_breadth_summary"]["section_optimizer_suggestion_count"] == 5
    assert summary["commercial_workflow_breadth_summary"]["section_optimizer_strengthen_count"] == 3
    assert summary["commercial_workflow_breadth_summary"]["section_optimizer_reduce_count"] == 2
    assert summary["commercial_workflow_breadth_summary"]["governing_clause_count"] == 6
    assert payload["artifacts"]["commercial_workflow_breadth_report_json"] == (
        "implementation/phase1/release/commercial_workflow_breadth_report.json"
    )
    assert payload["artifacts"]["commercial_workflow_breadth_artifact_links"] == {
        "viewer_surface_json": "release/visualization/structural_optimization_viewer.json",
        "workbench_surface_md": "implementation/phase1/release/commercial_workflow_breadth_appendix.md",
    }
    assert any(
        row["title"] == "Commercial workflow breadth surface is attached"
        and "ready_surfaces=1/3" in row["evidence"]
        and "serviceability=watchlist" in row["evidence"]
        and "traceability_ratio=0.620" in row["evidence"]
        for row in payload["observed_strengths"]
    )
    breadth_gap = next(row for row in payload["remaining_gaps"] if row["id"] == "GAP-P1-007")
    assert breadth_gap["status"] == "narrowing"
    assert "construction_stage_ready=True" in breadth_gap["evidence"]
    assert "rail_tunnel_ready=False" in breadth_gap["evidence"]
    assert "design_redesign_loop_ready=False" in breadth_gap["evidence"]

    markdown = out_md.read_text(encoding="utf-8")
    assert "Commercial workflow breadth" in markdown
    assert "Construction-stage breadth" in markdown
    assert "Rail/tunnel breadth" in markdown
    assert "Design redesign-loop breadth" in markdown
    assert "## Appendix: Commercial Workflow Breadth" in markdown
    assert "structural_optimization_viewer.json" in markdown
    assert "commercial_workflow_breadth_appendix.md" in markdown
    assert "| surface | ready | signal | value |" in markdown
    assert "traceability_ratio" in markdown


def test_release_gap_report_surfaces_measured_benchmark_breadth_summary(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "generate_release_gap_report.py"
    )
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"
    measured_report = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "benchmark_expansion"
        / "measured_benchmark_breadth_report.json"
    )

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [
        ci,
        freeze,
        promotion,
        authority,
        hip,
        midas,
        construction,
        diaphragm,
        repro,
        registry,
        kds,
        solver_hip,
        rc,
        quality,
    ]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {"mode": "engineer_in_the_loop_accelerated_coverage"},
        },
    )
    measured_report.parent.mkdir(parents=True, exist_ok=True)
    _write(
        measured_report,
        {
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
                "opensees_parser_ready_case_count": 3,
                "measured_family_count": 20,
                "measured_case_count": 74,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
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
            str(midas),
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
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["measured_benchmark_breadth_summary_line"].startswith("Measured benchmark breadth: PASS")
    assert summary["baseline_measured_family_count"] == 2
    assert summary["baseline_measured_case_count"] == 51
    assert summary["opensees_incremental_family_count"] == 6
    assert summary["opensees_incremental_case_count"] == 7
    assert summary["authority_incremental_family_count"] == 2
    assert summary["authority_incremental_case_count"] == 6
    assert summary["external_incremental_family_count"] == 10
    assert summary["external_incremental_case_count"] == 10
    assert summary["opensees_parser_ready_case_count"] == 3
    assert summary["measured_benchmark_family_count"] == 20
    assert summary["measured_benchmark_case_count"] == 74

    markdown = out_md.read_text(encoding="utf-8")
    assert "Measured benchmark breadth" in markdown
    assert "baseline=2/51" in markdown


def test_release_gap_report_surfaces_peer_blind_prediction_real_compare_and_landing_manifest(
    tmp_path: Path,
) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "generate_release_gap_report.py"
    )
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"
    compare_report = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release"
        / "benchmark_expansion"
        / "peer_blind_prediction_compare_report.json"
    )
    landing_manifest = (
        tmp_path
        / "implementation"
        / "phase1"
        / "open_data"
        / "pbd_hinge"
        / "edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
    )

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [
        ci,
        freeze,
        promotion,
        authority,
        hip,
        midas,
        construction,
        diaphragm,
        repro,
        registry,
        kds,
        solver_hip,
        rc,
        quality,
    ]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {"mode": "engineer_in_the_loop_accelerated_coverage"},
        },
    )
    compare_report.parent.mkdir(parents=True, exist_ok=True)
    landing_manifest.parent.mkdir(parents=True, exist_ok=True)
    _write(
        compare_report,
        {
            "contract_pass": True,
            "summary": {
                "case_count": 10,
                "build_case_count": 10,
                "measured_response_ready": False,
                "acceleration_channel_count": 0,
                "drift_channel_count": 0,
            },
            "results_explorer": {
                "entry_kind": "blind_prediction_compare_family",
                "entry_label": "PEER Blind Prediction Compare Family",
                "source_family": "edefense_peer_blind_prediction",
                "summary_label": "blind prediction compare pending measured response",
            },
        },
    )
    _write(
        landing_manifest,
        {
            "contract_pass": False,
            "landing_state": "pending",
            "summary": {
                "matched_file_count": 1,
                "csv_file_count": 1,
                "acceleration_candidate_count": 1,
                "drift_candidate_count": 0,
                "sensor_candidate_count": 2,
            },
            "matched_files": ["measured_response_acceleration.csv"],
            "expected_patterns": ["*accel*.csv", "*drift*.csv"],
            "input_root": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01",
            "required_group_pass_count": 3,
            "required_group_count": 4,
            "next_action": "land drift csv",
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
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
            str(midas),
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
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert (
        summary["peer_blind_prediction_compare_summary_line"]
        == "PEER blind compare lane: PENDING | cases=10 | measured_response=pending | channels=0"
    )
    assert summary["peer_blind_prediction_compare_case_count"] == 10
    assert summary["peer_blind_prediction_compare_build_case_count"] == 10
    assert summary["peer_blind_prediction_compare_measured_response_ready"] is False
    assert summary["peer_blind_prediction_compare_channel_count"] == 0
    assert summary["peer_blind_prediction_compare_entry_kind"] == "blind_prediction_compare_family"
    assert summary["peer_blind_prediction_compare_entry_label"] == "PEER Blind Prediction Compare Family"
    assert summary["peer_blind_prediction_compare_source_family"] == "edefense_peer_blind_prediction"
    assert (
        summary["peer_blind_prediction_compare_summary_label"]
        == "blind prediction compare pending measured response"
    )
    assert (
        summary["peer_blind_prediction_measured_response_landing_summary_line"]
        == "E-Defense/PEER measured-response landing: PENDING | matched=1 | patterns=2 | groups=3/4 | root=edefense_peer_blind_prediction_seed_01"
    )
    assert summary["peer_blind_prediction_measured_response_landing_pass"] is False
    assert summary["peer_blind_prediction_measured_response_landing_state"] == "pending"
    assert summary["peer_blind_prediction_measured_response_landing_matched_file_count"] == 1
    assert summary["peer_blind_prediction_measured_response_landing_csv_file_count"] == 1
    assert summary["peer_blind_prediction_measured_response_landing_acceleration_candidate_count"] == 1
    assert summary["peer_blind_prediction_measured_response_landing_drift_candidate_count"] == 0
    assert summary["peer_blind_prediction_measured_response_landing_sensor_candidate_count"] == 2
    assert summary["peer_blind_prediction_measured_response_landing_expected_pattern_count"] == 2
    assert summary["peer_blind_prediction_measured_response_landing_required_group_pass_count"] == 3
    assert summary["peer_blind_prediction_measured_response_landing_required_group_count"] == 4
    assert summary["peer_blind_prediction_measured_response_landing_next_action"] == "land drift csv"
    assert (
        payload["artifacts"]["peer_blind_prediction_compare_report"]
        == "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json"
    )
    assert (
        payload["artifacts"]["peer_blind_prediction_measured_response_landing_manifest"]
        == "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
    )

    markdown = out_md.read_text(encoding="utf-8")
    assert "PEER blind-prediction real compare lane" in markdown
    assert "measured_response=pending" in markdown
    assert "PEER blind-prediction measured-response landing" in markdown
    assert "groups=3/4" in markdown
