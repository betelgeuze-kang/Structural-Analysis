from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _touch(path: Path, content: str = "ok") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _build_workflow_fixture(tmp_path: Path, *, release_summary_overrides: dict | None = None) -> dict[str, Path]:
    release_registry = tmp_path / "release_registry.json"
    midas_interop = tmp_path / "interop.json"
    midas_native_roundtrip = tmp_path / "midas_native_roundtrip.json"
    provenance = tmp_path / "provenance.json"
    viewer_json = tmp_path / "viewer.json"
    viewer_html = tmp_path / "viewer.html"
    out = tmp_path / "out.json"
    signature_dir = tmp_path / "signing"
    artifacts_dir = tmp_path / "release_artifacts"
    kickoff_dir = tmp_path / "external_benchmark_kickoff"
    bundle_dir = tmp_path / "external_validation_submission_20260330T000000Z"
    results_explorer_dir = tmp_path / "results_explorer"
    irregular_source_catalog = tmp_path / "irregular_source_catalog.json"
    irregular_priority_families = tmp_path / "irregular_priority_families.json"
    irregular_triage_report = tmp_path / "irregular_triage_report.json"
    irregular_collection_report = tmp_path / "irregular_collection_report.json"
    irregular_gate_report = tmp_path / "irregular_structure_gate_report.json"
    irregular_top5_manifest = tmp_path / "irregular_top5_execution_manifest.json"
    korean_source_ingest_gate_report = tmp_path / "korean_source_ingest_gate_report.json"
    korean_structural_preview_promotion_queue = tmp_path / "korean_structural_preview_promotion_queue.json"
    public_key_path = _touch(signature_dir / "pub.pem")
    signature_out_path = _touch(signature_dir / "release_registry.signature.b64")
    release_artifact_paths = [
        _touch(artifacts_dir / "authoring_patch.json"),
        _touch(artifacts_dir / "audit_manifest.json"),
        _touch(artifacts_dir / "review_bundle.html"),
    ]
    for name in [
        "audit_review_decision_batch_template.json",
        "audit_review_decision_batch_template.md",
        "audit_review_decision_batch_approve_all.attested_example.json",
        "audit_review_decision_batch_approve_all.attested_example.md",
        "audit_review_decision_batch_mixed.attested_example.json",
        "audit_review_decision_batch_mixed.attested_example.md",
        "audit_review_decision_batch_approve_all.preview.json",
        "external_benchmark_submission_readiness_preview.approve_all.json",
        "external_benchmark_submission_readiness_preview.approve_all.md",
        "audit_review_decision_batch.live_preview.json",
        "audit_review_decision_batch.live_preview.md",
        "audit_review_decision_batch_run_report.json",
        "audit_review_decision_batch_preview_artifacts_report.json",
        "external_benchmark_execution_manifest.json",
        "external_benchmark_execution_status_manifest.json",
    ]:
        _touch(kickoff_dir / name)
    traceability_source_paths = [
        _touch(results_explorer_dir / "dynamic_time_history_report.json"),
        _touch(results_explorer_dir / "nonlinear_ndtha_stress_report.json"),
        _touch(results_explorer_dir / "hf_benchmark_report.atwood_open.json"),
        _touch(results_explorer_dir / "nonlinear_ndtha_stress_report.response.npz"),
    ]
    traceability_audit_paths = [
        _touch(results_explorer_dir / "release_gap_report.json"),
        _touch(results_explorer_dir / "execution_manifest.json"),
        _touch(results_explorer_dir / "execution_status.json"),
        _touch(results_explorer_dir / "change_summary_report.json"),
    ]
    traceability_output_paths = [
        _touch(viewer_html),
        _touch(results_explorer_dir / "analysis_evidence_gallery_onepage.html"),
    ]
    traceability_rerun_command = (
        "python implementation/phase1/generate_structural_optimization_visualization_viewer.py "
        f"--release-gap-report {results_explorer_dir / 'release_gap_report.json'} "
        f"--export-report {results_explorer_dir / 'export_report.json'} "
        f"--change-summary-report {results_explorer_dir / 'change_summary_report.json'} "
        f"--changes-report {results_explorer_dir / 'changes_report.json'} "
        f"--design-optimization-npz {results_explorer_dir / 'design_optimization.npz'} "
        f"--model-json {results_explorer_dir / 'model.json'} "
        f"--execution-manifest {results_explorer_dir / 'execution_manifest.json'} "
        f"--execution-status-manifest {results_explorer_dir / 'execution_status.json'} "
        f"--committee-package-report {results_explorer_dir / 'committee_package_report.json'} "
        f"--out-dir {results_explorer_dir}"
    )
    _touch(bundle_dir / "README.txt")
    _write(
        bundle_dir / "external_validation_onepage.json",
        {
            "metrics": {
                "external_benchmark_case_attestation_case_count": 10,
                "external_benchmark_case_attestation_manifest_count": 10,
                "external_benchmark_case_attestation_template_count": 0,
                "external_benchmark_case_attestation_receipt_count": 10,
                "external_benchmark_case_attestation_attested_count": 10,
                "external_benchmark_case_attestation_source_label": "manifest=10",
                "external_benchmark_case_attestation_status_label": "MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED=10",
            }
        },
    )
    _touch(bundle_dir / "external_validation_onepage.md")
    _touch(bundle_dir / "external_validation_onepage.html")
    _touch(bundle_dir / "external_validation_onepage.pdf")
    _write(
        tmp_path / "external_validation_latest.json",
        {
            "bundle_id": "20260330T000000Z",
            "dir": str(bundle_dir),
            "zip": _touch(tmp_path / "external_validation_submission_20260330T000000Z.zip"),
            "summary_json": str(bundle_dir / "external_validation_onepage.json"),
            "summary_md": str(bundle_dir / "external_validation_onepage.md"),
            "summary_html": str(bundle_dir / "external_validation_onepage.html"),
            "summary_pdf": str(bundle_dir / "external_validation_onepage.pdf"),
        },
    )
    irregular_families = []
    irregular_records = []
    irregular_priority_rows = []
    for idx in range(1, 6):
        family_id = f"IRR-{idx:02d}"
        irregular_priority_rows.append(
            {
                "id": family_id,
                "priority": idx,
                "authority_fit": "high" if idx <= 3 else "medium",
                "ai_learning_fit": "high",
                "recommended_kpi_or_validation_angle": f"validate-{family_id.lower()}",
                "irregularity_tags": ["irregular", "complex", f"tag-{idx}"],
                "why_it_matters": f"family {idx} matters for complex structural generalization",
            }
        )
        irregular_families.append(
            {
                "id": family_id,
                "source_record_count": 1,
                "local_ready_source_count": 1 if idx <= 3 else 0,
                "authority_fit": "high" if idx <= 3 else "medium",
                "ai_learning_fit": "high",
                "recommended_kpi_or_validation_angle": f"validate-{family_id.lower()}",
                "irregularity_tags": ["irregular", "complex", f"tag-{idx}"],
                "why_it_matters": f"family {idx} matters for complex structural generalization",
            }
        )
        irregular_records.append(
            {
                "family_id": family_id,
                "source_id": f"source-{idx}",
                "primary_format": "mgt" if idx <= 3 else "json_graph",
                "local_path": str(tmp_path / f"{family_id.lower()}.dat"),
                "collection_status": "ready" if idx <= 3 else "remote_candidate",
            }
        )
    _write(
        irregular_source_catalog,
        {
            "track_name": "irregular_structure_corpus_track",
            "summary": {
                "family_count": 5,
                "source_record_count": 5,
                "local_ready_count": 3,
                "remote_candidate_count": 2,
                "authority_high_like_count": 3,
                "ai_high_like_count": 5,
            },
            "structure_families": irregular_families,
            "source_records": irregular_records,
        },
    )
    _write(
        irregular_priority_families,
        {
            "track_name": "irregular_structure_corpus_track",
            "families": irregular_priority_rows,
        },
    )
    _write(
        irregular_triage_report,
        {
            "summary": {
                "native_roundtrip_candidate_count": 4,
                "solver_benchmark_candidate_count": 3,
                "ai_learning_candidate_count": 5,
                "quick_start_local_source_count": 3,
            }
        },
    )
    _write(
        irregular_collection_report,
        {
            "summary": {
                "collected_count": 5,
                "metadata_only_remote_candidate_count": 2,
                "status_counts": {"ready": 3, "remote_candidate": 2},
            }
        },
    )

    release_summary = {
        "mgt_export_direct_patch_change_count": 3,
        "mgt_export_group_local_connection_detailing_payload_available_count": 1,
        "mgt_export_group_local_detailing_payload_available_count": 1,
        "mgt_export_group_local_rebar_payload_available_count": 1,
        "mgt_export_connection_detailing_structured_payload_mapped_change_count": 1,
        "mgt_export_detailing_structured_payload_mapped_change_count": 1,
        "mgt_export_support_mode": "bounded_patch_subset",
        "mgt_export_evidence_model": "direct_patch_plus_audit_review_manifest",
        "mgt_export_audit_review_packet_count": 1,
        "mgt_export_audit_review_queue_item_count": 1,
        "mgt_export_audit_review_queue_status_label": "pending_review=1",
        "mgt_export_audit_review_queue_pending_count": 1,
        "mgt_export_audit_review_followup_item_count": 1,
        "mgt_export_audit_review_followup_status_label": "pending_review=1",
        "mgt_export_audit_review_resolution_item_count": 1,
        "mgt_export_audit_review_resolution_status_label": "pending_review=1",
        "mgt_export_instruction_sidecar_audit_only_change_count": 1,
        "mgt_export_instruction_sidecar_manual_input_change_count": 0,
        "mgt_export_connection_detailing_delivery_mode": "direct_patch_plus_sidecar_review",
        "mgt_export_detailing_delivery_mode": "direct_patch_plus_sidecar_review",
        "audit_review_decision_batch_template_item_count": 1,
        "audit_review_decision_batch_runner_reason_code": "PASS",
        "audit_review_decision_batch_runner_preview_ready_full": True,
        "external_benchmark_submission_preview_approve_all_reason_code": "PASS",
        "external_benchmark_submission_preview_reject_one_reason_code": "PASS",
        "external_benchmark_submission_preview_approve_all_ready_full": True,
        "external_benchmark_submission_preview_approve_all_pending_count": 0,
        "external_benchmark_submission_preview_approve_all_open_revision_count": 0,
        "deployment_model": "engineer_in_the_loop_accelerated_coverage",
    }
    if release_summary_overrides:
        release_summary.update(release_summary_overrides)

    _write(
        release_registry,
        {
            "contract_pass": True,
            "checks": {
                "public_key_written_pass": True,
                "signature_generated_pass": True,
                "signature_verified_pass": True,
            },
            "summary": release_summary,
            "signature": {
                "public_key_path": public_key_path,
                "signature_out": signature_out_path,
            },
            "registry_body": {
                "artifacts": [{"path": path} for path in release_artifact_paths],
            },
        },
    )
    _write(
        korean_source_ingest_gate_report,
        {
            "contract_pass": True,
            "summary_line": (
                "Korean source ingest gate: PASS | sources=4 | classes=4 | collected=0 | "
                "fingerprinted=0 | metadata_only=4 | rejected=0 | duplicate_sha_groups=0 | "
                "seed_complete=4 | exact_topology=1 | native_writeback=1 | p0_focus=3"
            ),
            "summary": {
                "source_count": 4,
                "source_class_count": 4,
                "collected_count": 0,
                "metadata_only_remote_candidate_count": 4,
                "rejected_count": 0,
                "fingerprinted_count": 0,
                "duplicate_sha_group_count": 0,
                "collection_summary_line": "Korean source collect: PASS | sources=4 | collected=0 | metadata_only=4 | rejected=0 | bytes=0",
                "ingest_summary_line": (
                    "Korean source ingest gate: PASS | sources=4 | classes=4 | collected=0 | "
                    "fingerprinted=0 | metadata_only=4 | rejected=0 | duplicate_sha_groups=0 | "
                    "seed_complete=4 | exact_topology=1 | native_writeback=1 | p0_focus=3"
                ),
            },
        },
    )
    _write(
        korean_structural_preview_promotion_queue,
        {
            "summary": {
                "candidate_total": 3,
                "pending_candidate_count": 0,
                "state": "closed_until_new_public_archive_exact_topology_candidate",
            }
        },
    )
    _write(
        midas_interop,
        {
            "contract_pass": True,
            "summary": {
                "loadcomb_roundtrip_pass": True,
                "bounded_subset_mode": "editor_seed+raw_recovery+preview_roundtrip",
                "preview_file_present_count": 1,
                "remaining_limits": ["primitive_load_cards_pending"],
            },
        },
    )
    _write(
        midas_native_roundtrip,
        {
            "contract_pass": True,
            "checks": {
                "corpus_manifest_present_pass": True,
                "native_text_case_present_pass": True,
                "native_writeback_ready_pass": True,
                "diff_receipt_coverage_pass": True,
                "per_case_writeback_pass": True,
                "topology_stability_pass": True,
                "load_contract_stability_pass": True,
                "loadcomb_exact_roundtrip_pass": True,
                "unknown_rows_zero_pass": True,
            },
            "summary": {
                "corpus_case_count": 6,
                "native_writeback_ready_count": 1,
                "public_native_writeback_ready_count": 1,
                "fixture_native_writeback_ready_count": 0,
                "receipt_count": 1,
                "source_family_count": 2,
                "structure_type_batch_count": 1,
                "taxonomy_case_counts": {"preserved_exact": 0, "canonical_rewrite": 1, "lossy_rewrite": 0},
                "pending_review_total": 2,
            },
        },
    )
    _write(provenance, {"contract_pass": True, "summary": {"row_count": 144, "exact_row_count": 144}})
    _write(
        viewer_json,
        {
            "commercial_parity_summary": {},
            "benchmark_execution": {},
            "detail_context": {},
            "case_context": {
                "general_fe_contact_matrix_summary_line": (
                    "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | "
                    "ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | "
                    "node_surface_proxy=5 | support_depth=21 | coupling_depth=31 | support_families=2/2 | "
                    "proxy_families=2/2"
                )
            },
            "results_explorer": {
                "available": True,
                "general_fe_contact_matrix_surface": {
                    "summary_line": (
                        "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | "
                        "interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | "
                        "support_search=9 | node_surface_proxy=5 | support_depth=21 | coupling_depth=31 | "
                        "support_families=2/2 | proxy_families=2/2"
                    ),
                    "compact_summary_label": "coupling depth=31 | support families=2/2 | proxy families=2/2",
                    "coupling_depth_score": 31,
                    "support_search_family_count": 2,
                    "support_search_family_requirement_count": 2,
                    "node_to_surface_proxy_family_count": 2,
                    "node_to_surface_proxy_family_requirement_count": 2,
                },
                "time_history": {
                    "available": True,
                    "lead": "dynamic_time_history_report.json의 실제 step trace를 viewer 안에서 바로 읽는 첫 번째 time-history surface입니다.",
                },
                "envelope": {
                    "available": True,
                    "lead": "nonlinear_ndtha_stress_report.json에서 peak drift envelope와 final drift를 같이 꺼내 envelope explorer의 첫 패널로 엮었습니다.",
                },
                "ndtha_response": {
                    "available": True,
                    "lead": "nonlinear_ndtha_stress_report.response.npz와 NDTHA report의 solver-control head를 함께 보여줍니다.",
                    "metrics": [],
                    "checks": [
                        "response archive present",
                        "solver-control history pass",
                        "solver-control sequence pass",
                        "case ids aligned",
                        "response npz pass",
                        "step-series depth present",
                    ],
                    "solver_control_event_labels": [],
                    "solver_control_available": True,
                    "solver_control_event_count": 0,
                    "solver_control_nonconverged_step_count": 0,
                    "solver_control_cutback_step_count": 0,
                    "solver_control_recommended_dt_scale_min": 1.0,
                    "step_series_depth_available": True,
                    "step_series_depth_value": 7,
                    "step_series_depth_label": "7",
                    "response_npz_series_case_count": 1,
                    "response_npz_series_contract_pass": True,
                    "response_npz_full_step_count_max": 7,
                    "response_npz_inline_step_count_max": 2,
                    "response_npz_available": True,
                    "response_npz_case_count": 1,
                    "response_npz_array_count": 5,
                    "response_npz_case_ids_label": "CASE-A",
                    "response_npz_case_keys_label": "CASE_A",
                    "material_effect_available": True,
                    "material_effect_row_count": 3,
                    "material_effect_depth_label": "3",
                    "response_npz_path": str(results_explorer_dir / "nonlinear_ndtha_stress_report.response.npz"),
                    "response_npz_href": str(results_explorer_dir / "nonlinear_ndtha_stress_report.response.npz"),
                    "response_npz_label": str(results_explorer_dir / "nonlinear_ndtha_stress_report.response.npz"),
                    "report_href": str(results_explorer_dir / "nonlinear_ndtha_stress_report.json"),
                    "report_label": str(results_explorer_dir / "nonlinear_ndtha_stress_report.json"),
                },
                "geometry_crosswalk": {
                    "available": True,
                    "lead": "kds_geometry_bridge summary와 full crosswalk depth를 별도 카드로 보여줍니다.",
                    "metrics": [],
                    "checks": [
                        "geometry bridge present",
                        "review ids mapped",
                        "full crosswalk depth present",
                    ],
                    "geometry_bridge_summary_label": "2/4 review ids mapped | exact=2 | heuristic=0 | rows exact=4 | rows heuristic=0 | confidence=manual_verified_exact_focus=2",
                    "geometry_bridge_source_label": "embedded metadata",
                    "geometry_bridge_contract_label": "0.1.0",
                    "review_row_count_label": "4",
                    "review_id_count_label": "2",
                    "mapped_review_id_count_label": "2",
                    "exact_review_id_count_label": "2",
                    "mapped_row_provenance_count_label": "4",
                    "exact_row_provenance_count_label": "4",
                    "full_crosswalk_depth_available": True,
                    "full_crosswalk_depth_value": 1056,
                    "full_crosswalk_depth_label": "1056",
                    "full_member_crosswalk_available": True,
                    "full_member_crosswalk_count_total": 242,
                    "full_member_crosswalk_expected_total": 242,
                    "full_member_crosswalk_pass": True,
                    "full_member_crosswalk_label": "242/242 PASS",
                    "full_section_crosswalk_available": True,
                    "full_section_crosswalk_count_total": 200,
                    "full_section_crosswalk_expected_total": 200,
                    "full_section_crosswalk_pass": True,
                    "full_section_crosswalk_label": "200/200 PASS",
                    "full_load_crosswalk_available": True,
                    "full_load_crosswalk_count_total": 51,
                    "full_load_crosswalk_expected_total": 51,
                    "full_load_crosswalk_pass": True,
                    "full_load_crosswalk_label": "51/51 PASS",
                    "full_crosswalk_detail_available": True,
                    "full_crosswalk_detail_label": "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS",
                    "report_href": str(results_explorer_dir / "midas_generator_33.json"),
                    "report_label": str(results_explorer_dir / "midas_generator_33.json"),
                },
                "contact_material_integration": {
                    "available": True,
                    "summary_label": "support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3",
                    "support_family_count": 2,
                    "proxy_family_count": 2,
                    "assembled_depth_value": 5,
                    "ndtha_step_series_depth_label": "7",
                    "ndtha_material_depth_label": "3",
                },
                "mode_shape": {
                    "available": True,
                    "lead": "hf_benchmark_report.atwood_open.json의 MAC / buckling / drift / base shear 비교를 mode-shape snapshot으로 바로 노출합니다.",
                },
                "traceability": {
                    "available": True,
                    "surface_sequence": ["time-history", "envelope", "ndtha-response", "mode-shape"],
                    "surface_chain_label": "time-history -> envelope -> ndtha-response -> mode-shape",
                    "surface_summary_label": "already-generated phase1 result reports",
                    "surface_depth_summary_label": "NDTHA step-series depth=7 | geometry full-crosswalk depth=1056",
                    "surface_detail_summary_label": "NDTHA material depth=3 | geometry full-crosswalk detail=full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS",
                    "contact_material_depth_summary_label": "support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3",
                    "ndtha_step_series_depth_label": "7",
                    "ndtha_material_depth_label": "3",
                    "geometry_full_crosswalk_depth_label": "1056",
                    "geometry_full_crosswalk_detail_label": "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS",
                    "rerun_label": "refresh results explorer from already-generated phase1 artifacts",
                    "rerun_command": traceability_rerun_command,
                    "source_reports": [
                        {
                            "key": "time-history",
                            "label": "Time-History Report",
                            "path": traceability_source_paths[0],
                            "href": traceability_source_paths[0],
                        },
                        {
                            "key": "envelope",
                            "label": "Envelope Report",
                            "path": traceability_source_paths[1],
                            "href": traceability_source_paths[1],
                        },
                        {
                            "key": "ndtha-response",
                            "label": "NDTHA Response NPZ",
                            "path": traceability_source_paths[3],
                            "href": traceability_source_paths[3],
                        },
                        {
                            "key": "mode-shape",
                            "label": "Mode-Shape Report",
                            "path": traceability_source_paths[2],
                            "href": traceability_source_paths[2],
                        },
                    ],
                    "audit_reports": [
                        {
                            "key": "release-gap",
                            "label": "Release Gap JSON",
                            "path": traceability_audit_paths[0],
                            "href": traceability_audit_paths[0],
                        },
                        {
                            "key": "execution-manifest",
                            "label": "Execution Manifest",
                            "path": traceability_audit_paths[1],
                            "href": traceability_audit_paths[1],
                        },
                        {
                            "key": "execution-status",
                            "label": "Execution Status",
                            "path": traceability_audit_paths[2],
                            "href": traceability_audit_paths[2],
                        },
                        {
                            "key": "change-summary",
                            "label": "Change Summary JSON",
                            "path": traceability_audit_paths[3],
                            "href": traceability_audit_paths[3],
                        },
                    ],
                    "output_reports": [
                        {
                            "key": "viewer-html",
                            "label": "Viewer HTML",
                            "path": traceability_output_paths[0],
                            "href": traceability_output_paths[0],
                        },
                        {
                            "key": "analysis-gallery-onepage",
                            "label": "Gallery One-Page HTML",
                            "path": traceability_output_paths[1],
                            "href": traceability_output_paths[1],
                        },
                    ],
                    "source_report_count": 3,
                    "audit_report_count": 4,
                    "output_report_count": 2,
                },
            },
            "viewer_mode": "review",
        },
    )
    viewer_html.write_text(
        "<html><body>Results Explorer Traceability Code-Check Drilldown MIDAS Load Combination Browser Reviewer appendix surface current slice csv refresh results explorer from already-generated phase1 artifacts</body></html>",
        encoding="utf-8",
    )

    return {
        "release_registry": release_registry,
        "midas_interop": midas_interop,
        "midas_native_roundtrip": midas_native_roundtrip,
        "provenance": provenance,
        "viewer_json": viewer_json,
        "viewer_html": viewer_html,
        "out": out,
        "irregular_source_catalog": irregular_source_catalog,
        "irregular_priority_families": irregular_priority_families,
        "irregular_triage_report": irregular_triage_report,
        "irregular_collection_report": irregular_collection_report,
        "irregular_gate_report": irregular_gate_report,
        "irregular_top5_manifest": irregular_top5_manifest,
        "korean_source_ingest_gate_report": korean_source_ingest_gate_report,
        "korean_structural_preview_promotion_queue": korean_structural_preview_promotion_queue,
    }


def test_run_workflow_productization_gate_passes(tmp_path: Path) -> None:
    paths = _build_workflow_fixture(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_workflow_productization_gate.py",
            "--release-registry-report",
            str(paths["release_registry"]),
            "--midas-interoperability-report",
            str(paths["midas_interop"]),
            "--midas-native-roundtrip-report",
            str(paths["midas_native_roundtrip"]),
            "--row-provenance-export-report",
            str(paths["provenance"]),
            "--viewer-json",
            str(paths["viewer_json"]),
            "--viewer-html",
            str(paths["viewer_html"]),
            "--irregular-structure-source-catalog",
            str(paths["irregular_source_catalog"]),
            "--irregular-structure-priority-families",
            str(paths["irregular_priority_families"]),
            "--irregular-structure-triage-report",
            str(paths["irregular_triage_report"]),
            "--irregular-structure-collection-report",
            str(paths["irregular_collection_report"]),
            "--irregular-structure-gate-report",
            str(paths["irregular_gate_report"]),
            "--irregular-top5-execution-manifest",
            str(paths["irregular_top5_manifest"]),
            "--korean-source-ingest-gate-report",
            str(paths["korean_source_ingest_gate_report"]),
            "--korean-structural-preview-promotion-queue",
            str(paths["korean_structural_preview_promotion_queue"]),
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["authoring_action_automation_pass"] is True
    assert report["checks"]["audit_action_automation_pass"] is True
    assert report["checks"]["auto_approved_subset_pass"] is True
    assert report["checks"]["signed_submission_bundle_pass"] is True
    assert report["checks"]["viewer_results_surface_pass"] is True
    assert report["checks"]["results_explorer_traceability_pass"] is True
    assert report["checks"]["bounded_roundtrip_pass"] is True
    assert report["checks"]["native_midas_roundtrip_pass"] is True
    assert report["checks"]["irregular_structure_track_pass"] is True
    assert report["checks"]["results_explorer_ndtha_material_depth_pass"] is True
    assert report["checks"]["results_explorer_geometry_full_crosswalk_detail_pass"] is True
    assert report["checks"]["results_explorer_contact_coupling_pass"] is True
    assert report["checks"]["results_explorer_contact_material_depth_pass"] is True
    assert report["checks"]["results_explorer_general_fe_contact_surface_pass"] is True
    assert report["summary"]["generated_release_artifact_count"] >= 3
    assert report["summary"]["generated_authoring_artifact_count"] >= 6
    assert report["summary"]["generated_audit_artifact_count"] >= 6
    assert report["summary"]["generated_auto_approved_subset_count"] >= 3
    assert report["summary"]["generated_signed_submission_bundle_count"] >= 6
    assert report["summary"]["case_onepage_attestation_case_count"] == 10
    assert report["summary"]["case_onepage_attestation_manifest_count"] == 10
    assert report["summary"]["case_onepage_attestation_attested_count"] == 10
    assert report["summary"]["case_onepage_attestation_status_label"] == "MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED=10"
    assert report["summary"]["case_onepage_attestation_source_label"] == "manifest=10"
    assert report["summary"]["case_onepage_attestation_summary_source_label"] == "latest_bundle_summary"
    assert report["summary"]["results_explorer_traceability_available"] is True
    assert report["summary"]["results_explorer_traceability_pass"] is True
    assert report["summary"]["results_explorer_traceability_surface_chain_label"] == "time-history -> envelope -> ndtha-response -> mode-shape"
    assert report["summary"]["results_explorer_traceability_rerun_label"] == "refresh results explorer from already-generated phase1 artifacts"
    assert report["summary"]["results_explorer_traceability_source_report_count"] == 4
    assert report["summary"]["results_explorer_traceability_audit_report_count"] == 4
    assert report["summary"]["results_explorer_traceability_output_report_count"] == 2
    assert report["summary"]["results_explorer_traceability_surface_depth_summary_label"] == (
        "NDTHA step-series depth=7 | geometry full-crosswalk depth=1056 | geometry full-crosswalk aggregate="
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert report["summary"]["results_explorer_traceability_surface_detail_summary_label"] == "NDTHA material depth=3 | geometry full-crosswalk detail=full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    assert report["summary"]["results_explorer_traceability_ndtha_step_series_depth_label"] == "7"
    assert report["summary"]["results_explorer_traceability_ndtha_material_depth_label"] == "3"
    assert report["summary"]["results_explorer_traceability_geometry_full_crosswalk_depth_label"] == "1056"
    assert report["summary"]["results_explorer_traceability_geometry_full_crosswalk_aggregate_label"] == (
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert report["summary"]["results_explorer_traceability_geometry_full_crosswalk_detail_label"] == "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    assert report["summary"]["results_explorer_traceability_contact_coupling_summary_label"] == (
        "support families=2 | proxy families=2 | assembled depth=5"
    )
    assert report["summary"]["results_explorer_traceability_contact_support_family_count"] == 2
    assert report["summary"]["results_explorer_traceability_contact_proxy_family_count"] == 2
    assert report["summary"]["results_explorer_traceability_contact_assembled_depth_value"] == 5
    assert report["summary"]["results_explorer_traceability_contact_material_depth_summary_label"] == (
        "support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3"
    )
    assert report["summary"]["results_explorer_traceability_general_fe_contact_matrix_summary_line"] == (
        "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | "
        "ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | "
        "node_surface_proxy=5 | support_depth=21 | coupling_depth=31 | support_families=2/2 | "
        "proxy_families=2/2"
    )
    assert report["summary"]["results_explorer_traceability_general_fe_contact_compact_summary_label"] == (
        "coupling depth=31 | support families=2/2 | proxy families=2/2"
    )
    assert report["summary"]["results_explorer_traceability_general_fe_contact_coupling_depth_value"] == 31
    assert report["summary"]["results_explorer_traceability_general_fe_contact_support_family_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_support_family_expected_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_proxy_family_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_proxy_family_expected_count"] == 2
    assert report["summary"]["results_explorer_ndtha_step_series_depth_pass"] is True
    assert report["summary"]["results_explorer_ndtha_material_depth_pass"] is True
    assert report["summary"]["results_explorer_geometry_full_crosswalk_depth_pass"] is True
    assert report["summary"]["results_explorer_geometry_full_crosswalk_detail_pass"] is True
    assert report["summary"]["results_explorer_contact_coupling_pass"] is True
    assert report["summary"]["results_explorer_contact_material_depth_pass"] is True
    assert report["summary"]["results_explorer_general_fe_contact_surface_pass"] is True
    assert report["summary"]["results_explorer_traceability_source_report_labels"] == [
        "Time-History Report",
        "Envelope Report",
        "NDTHA Response NPZ",
        "Mode-Shape Report",
    ]
    assert report["summary"]["results_explorer_traceability_audit_report_labels"] == [
        "Release Gap JSON",
        "Execution Manifest",
        "Execution Status",
        "Change Summary JSON",
    ]
    assert report["summary"]["results_explorer_traceability_output_report_labels"] == [
        "Viewer HTML",
        "Gallery One-Page HTML",
    ]
    assert report["summary"]["native_roundtrip_ready_case_count"] == 1
    assert report["summary"]["irregular_structure_track_pass"] is True
    assert report["summary"]["irregular_structure_top5_count"] == 5
    assert report["summary"]["irregular_structure_top5_family_ids"] == [f"IRR-{idx:02d}" for idx in range(1, 6)]
    assert report["summary"]["korean_source_ingest_source_count"] == 4
    assert report["summary"]["korean_source_ingest_source_class_count"] == 4
    assert report["summary"]["korean_structural_preview_queue_candidate_total"] == 3
    assert report["summary"]["korean_structural_preview_queue_pending_candidate_count"] == 0
    assert "irregular_structure_track=yes" in report["summary_line"]
    assert "korean_source_ingest=yes" in report["summary_line"]
    assert "korean_structural_preview_queue=yes" in report["summary_line"]
    assert "results_explorer=yes(traceability=pass" in report["summary_line"]
    assert (
        "depths=NDTHA step-series depth=7 | geometry full-crosswalk depth=1056 | geometry full-crosswalk aggregate="
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    ) in report["summary_line"]
    assert "details=NDTHA material depth=3 | geometry full-crosswalk detail=full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS" in report["summary_line"]
    assert "general_fe_contact_matrix=General FE contact matrix: PASS | ready=10/10 | direct=6/6" in report["summary_line"]
    assert "coupling_depth=31 | support_families=2/2 | proxy_families=2/2" in report["summary_line"]
    assert "coupling=support families=2 | proxy families=2 | assembled depth=5" in report["summary_line"]
    assert "contact_material=support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3" in report["summary_line"]
    assert report["generated_artifacts"]["irregular_structure_gate_report_path"] == str(paths["irregular_gate_report"])
    assert report["generated_artifacts"]["irregular_top5_execution_manifest_path"] == str(paths["irregular_top5_manifest"])
    assert paths["irregular_gate_report"].exists()
    assert paths["irregular_top5_manifest"].exists()


def test_run_workflow_productization_gate_accepts_zero_touch_native_authoring(tmp_path: Path) -> None:
    paths = _build_workflow_fixture(
        tmp_path,
        release_summary_overrides={
            "mgt_export_support_mode": "native_authoring_supported_changeset",
            "mgt_export_evidence_model": "direct_patch_plus_zero_touch_verification_manifest",
            "mgt_export_audit_review_packet_count": 0,
            "mgt_export_audit_review_queue_item_count": 0,
            "mgt_export_audit_review_queue_status_label": "",
            "mgt_export_audit_review_queue_pending_count": 0,
            "mgt_export_audit_review_followup_item_count": 0,
            "mgt_export_audit_review_followup_status_label": "",
            "mgt_export_audit_review_resolution_item_count": 0,
            "mgt_export_audit_review_resolution_status_label": "",
            "mgt_export_instruction_sidecar_audit_only_change_count": 0,
            "mgt_export_instruction_sidecar_manual_input_change_count": 0,
            "mgt_export_connection_detailing_delivery_mode": "direct_patch_native_authoring_zero_touch_verified",
            "mgt_export_detailing_delivery_mode": "direct_patch_native_authoring_zero_touch_verified",
            "audit_review_decision_batch_template_item_count": 0,
            "audit_review_decision_batch_runner_reason_code": "PASS_ZERO_TOUCH_NO_OPEN_DECISION_ITEMS",
            "audit_review_decision_batch_runner_preview_ready_full": False,
            "external_benchmark_submission_preview_approve_all_reason_code": "PASS_NO_OPEN_DECISION_ITEMS",
            "external_benchmark_submission_preview_reject_one_reason_code": "PASS_NO_OPEN_DECISION_ITEMS",
            "external_benchmark_submission_preview_approve_all_ready_full": False,
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_workflow_productization_gate.py",
            "--release-registry-report",
            str(paths["release_registry"]),
            "--midas-interoperability-report",
            str(paths["midas_interop"]),
            "--midas-native-roundtrip-report",
            str(paths["midas_native_roundtrip"]),
            "--row-provenance-export-report",
            str(paths["provenance"]),
            "--viewer-json",
            str(paths["viewer_json"]),
            "--viewer-html",
            str(paths["viewer_html"]),
            "--irregular-structure-source-catalog",
            str(paths["irregular_source_catalog"]),
            "--irregular-structure-priority-families",
            str(paths["irregular_priority_families"]),
            "--irregular-structure-triage-report",
            str(paths["irregular_triage_report"]),
            "--irregular-structure-collection-report",
            str(paths["irregular_collection_report"]),
            "--irregular-structure-gate-report",
            str(paths["irregular_gate_report"]),
            "--irregular-top5-execution-manifest",
            str(paths["irregular_top5_manifest"]),
            "--korean-source-ingest-gate-report",
            str(paths["korean_source_ingest_gate_report"]),
            "--korean-structural-preview-promotion-queue",
            str(paths["korean_structural_preview_promotion_queue"]),
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["audit_approval_flow_pass"] is True
    assert report["checks"]["audit_action_automation_pass"] is True
    assert report["checks"]["results_explorer_traceability_pass"] is True
    assert report["summary"]["audit_packet_count"] == 0
    assert report["summary"]["audit_queue_count"] == 0
    assert report["summary"]["zero_touch_native_authoring_pass"] is True
    assert report["summary"]["zero_touch_no_open_decision_items_pass"] is True
    assert report["summary"]["zero_touch_native_authoring_count"] == 2
    assert report["summary"]["audit_flow_mode"] == "zero_touch_native_authoring"
    assert "audit=yes(mode=zero_touch_native_authoring" in report["summary_line"]
    assert "results_explorer=yes(traceability=pass" in report["summary_line"]


def test_run_workflow_productization_gate_consumes_structured_general_fe_surface(tmp_path: Path) -> None:
    paths = _build_workflow_fixture(tmp_path)
    viewer_payload = json.loads(paths["viewer_json"].read_text(encoding="utf-8"))
    viewer_payload.get("case_context", {}).pop("general_fe_contact_matrix_summary_line", None)
    viewer_payload.get("results_explorer", {}).pop("general_fe_contact_matrix_summary_line", None)
    traceability = viewer_payload.get("results_explorer", {}).get("traceability", {})
    if isinstance(traceability, dict):
        traceability.pop("general_fe_contact_matrix_summary_line", None)
    general_fe_surface = viewer_payload.get("results_explorer", {}).get("general_fe_contact_matrix_surface", {})
    if isinstance(general_fe_surface, dict):
        general_fe_surface.pop("summary_line", None)
        general_fe_surface["compact_summary_label"] = "coupling depth=31 | support families=2/2 | proxy families=2/2"
        general_fe_surface["coupling_depth_score"] = 31
        general_fe_surface["support_search_family_count"] = 2
        general_fe_surface["support_search_family_requirement_count"] = 2
        general_fe_surface["node_to_surface_proxy_family_count"] = 2
        general_fe_surface["node_to_surface_proxy_family_requirement_count"] = 2
    _write(paths["viewer_json"], viewer_payload)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_workflow_productization_gate.py",
            "--release-registry-report",
            str(paths["release_registry"]),
            "--midas-interoperability-report",
            str(paths["midas_interop"]),
            "--midas-native-roundtrip-report",
            str(paths["midas_native_roundtrip"]),
            "--row-provenance-export-report",
            str(paths["provenance"]),
            "--viewer-json",
            str(paths["viewer_json"]),
            "--viewer-html",
            str(paths["viewer_html"]),
            "--irregular-structure-source-catalog",
            str(paths["irregular_source_catalog"]),
            "--irregular-structure-priority-families",
            str(paths["irregular_priority_families"]),
            "--irregular-structure-triage-report",
            str(paths["irregular_triage_report"]),
            "--irregular-structure-collection-report",
            str(paths["irregular_collection_report"]),
            "--irregular-structure-gate-report",
            str(paths["irregular_gate_report"]),
            "--irregular-top5-execution-manifest",
            str(paths["irregular_top5_manifest"]),
            "--korean-source-ingest-gate-report",
            str(paths["korean_source_ingest_gate_report"]),
            "--korean-structural-preview-promotion-queue",
            str(paths["korean_structural_preview_promotion_queue"]),
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert report["checks"]["results_explorer_general_fe_contact_surface_pass"] is True
    assert report["summary"]["results_explorer_traceability_general_fe_contact_compact_summary_label"] == (
        "coupling depth=31 | support families=2/2 | proxy families=2/2"
    )
    assert report["summary"]["results_explorer_traceability_general_fe_contact_coupling_depth_value"] == 31
    assert report["summary"]["results_explorer_traceability_general_fe_contact_support_family_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_support_family_expected_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_proxy_family_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_proxy_family_expected_count"] == 2
    assert report["summary"]["results_explorer_traceability_general_fe_contact_matrix_summary_line"] == (
        "General FE contact matrix: PASS | coupling_depth=31 | support_families=2/2 | proxy_families=2/2"
    )


def test_run_workflow_productization_gate_rejects_missing_results_explorer_traceability(tmp_path: Path) -> None:
    paths = _build_workflow_fixture(tmp_path)
    viewer_payload = json.loads(paths["viewer_json"].read_text(encoding="utf-8"))
    viewer_payload["results_explorer"].pop("traceability", None)
    _write(paths["viewer_json"], viewer_payload)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_workflow_productization_gate.py",
            "--release-registry-report",
            str(paths["release_registry"]),
            "--midas-interoperability-report",
            str(paths["midas_interop"]),
            "--midas-native-roundtrip-report",
            str(paths["midas_native_roundtrip"]),
            "--row-provenance-export-report",
            str(paths["provenance"]),
            "--viewer-json",
            str(paths["viewer_json"]),
            "--viewer-html",
            str(paths["viewer_html"]),
            "--irregular-structure-source-catalog",
            str(paths["irregular_source_catalog"]),
            "--irregular-structure-priority-families",
            str(paths["irregular_priority_families"]),
            "--irregular-structure-triage-report",
            str(paths["irregular_triage_report"]),
            "--irregular-structure-collection-report",
            str(paths["irregular_collection_report"]),
            "--irregular-structure-gate-report",
            str(paths["irregular_gate_report"]),
            "--irregular-top5-execution-manifest",
            str(paths["irregular_top5_manifest"]),
            "--korean-source-ingest-gate-report",
            str(paths["korean_source_ingest_gate_report"]),
            "--korean-structural-preview-promotion-queue",
            str(paths["korean_structural_preview_promotion_queue"]),
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode != 0
    report = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_RESULTS_EXPLORER_TRACEABILITY"
