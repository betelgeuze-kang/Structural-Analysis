from __future__ import annotations

import importlib.util
import json
import numpy as np
from pathlib import Path
import subprocess
import sys


def _load_viewer_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/generate_structural_optimization_visualization_viewer.py"
    spec = importlib.util.spec_from_file_location("viewer_module_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _native_authoring_family_specs(
    tmp_path: Path,
    *,
    sample_solver_session_path: Path | None = None,
    loadcomb_preview_path: Path | None = None,
) -> list[dict[str, object]]:
    base_rows = [
        ("belt_truss_mega_frame", "Belt-Truss Mega Frame", "belt-truss", "beam, brace, column, slab +1", 270, 9, 23, 6, 4),
        ("composite_podium", "Composite Podium", "podium-heavy", "beam, column, slab", 188, 7, 21, 5, 4),
        ("deep_transfer_basement", "Deep Transfer Basement", "deep-transfer", "beam, wall, slab", 164, 6, 18, 4, 3),
        ("dual_system_hospital", "Dual-System Hospital", "hospital", "beam, brace, column, wall", 241, 8, 22, 5, 4),
        ("outrigger_transfer_tower", "Outrigger Transfer Tower", "outrigger", "beam, column, outrigger", 211, 8, 20, 5, 3),
        ("rc_wall_core", "RC Wall Core", "core-residential", "RC wall", 81, 6, 17, 2, 2),
        ("sample_tower", "Sample Tower", "baseline", "beam, column", 35, 4, 13, 2, 2),
        ("steel_braced_frame", "Steel Braced Frame", "braced-frame", "beam, brace, column", 129, 5, 16, 3, 2),
    ]
    specs: list[dict[str, object]] = []
    for index, (
        family_id,
        family_label,
        draft_label,
        member_type_label,
        member_count,
        load_pattern_count,
        solver_combo_count,
        solver_mesh_request_count,
        active_family_count,
    ) in enumerate(base_rows, start=1):
        family_dir = tmp_path / family_id
        solver_session_json = (
            sample_solver_session_path
            if family_id == "sample_tower" and sample_solver_session_path is not None
            else family_dir / "native_authoring_solver_session.json"
        )
        loadcomb_preview_mgt = (
            loadcomb_preview_path
            if family_id == "sample_tower" and loadcomb_preview_path is not None
            else family_dir / "native_authoring_solver_session.loadcomb_preview.mgt"
        )
        specs.append(
            {
                "family_id": family_id,
                "family_label": family_label,
                "draft_label": draft_label,
                "project_id": f"native-authoring-{family_id.replace('_', '-')}",
                "project_name": f"Native Authoring {family_label}",
                "member_type_label": member_type_label,
                "member_count": member_count,
                "load_pattern_count": load_pattern_count,
                "solver_combo_count": solver_combo_count,
                "solver_mesh_request_count": solver_mesh_request_count,
                "solver_mesh_cell_count": 420 + index * 96,
                "solver_load_case_count": 4 + (index % 4),
                "solver_loadcomb_line_count": 32 + index * 3,
                "job_count": 3,
                "snapshot_count": 3,
                "approval_count": 3,
                "node_count": 24 + index * 12,
                "story_count": 5 + index,
                "palette_family_count": 4,
                "palette_family_label": "Composite, Steel, RC, CFT",
                "active_family_count": active_family_count,
                "active_family_label": {
                    2: "Beam, Column",
                    3: "Beam, Column, Wall",
                    4: "Beam, Brace, Column, Wall",
                }.get(active_family_count, "Beam, Column"),
                "artifacts": {
                    "workspace_summary_json": str(family_dir / "native_authoring_workspace_summary.json"),
                    "workspace_draft_json": str(family_dir / "native_authoring_workspace_draft.json"),
                    "solver_session_json": str(solver_session_json),
                    "solver_session_artifact_json": str(solver_session_json),
                    "solver_loadcomb_preview_mgt": str(loadcomb_preview_mgt),
                    "loadcomb_preview_mgt": str(loadcomb_preview_mgt),
                    "job_manifest_json": str(family_dir / "native_authoring_job_manifest.json"),
                    "batch_job_report_json": str(family_dir / "native_authoring_batch_job_report.json"),
                    "project_registry_json": str(family_dir / "native_authoring_project_registry.json"),
                    "project_package_zip": str(family_dir / "native_authoring_project_package.zip"),
                    "project_registry_public_key": str(
                        tmp_path / "signing" / family_id / "native_authoring_project_registry_ed25519.pub.pem"
                    ),
                    "project_registry_signature": str(
                        tmp_path / "signing" / family_id / "native_authoring_project_registry.signature.b64"
                    ),
                },
            }
        )
    return specs


def test_make_midas_load_pattern_context_supports_raw_recovery_and_kds(tmp_path: Path) -> None:
    module = _load_viewer_module()
    model_json = tmp_path / "raw_combo_only.json"
    kds_report = tmp_path / "code_check_report.json"
    _write_json(
        model_json,
        {
            "model": {
                "metadata": {
                    "kds_geometry_bridge": {
                        "contract_version": "0.1.0",
                        "summary": {
                            "review_row_count": 1,
                            "review_id_count": 1,
                            "mapped_review_id_count": 1,
                            "exact_mapped_review_id_count": 1,
                            "heuristic_mapped_review_id_count": 0,
                            "mapped_row_provenance_count": 1,
                            "unmapped_review_id_count": 0,
                            "exact_mapped_row_provenance_count": 1,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"manual_embedding": 1},
                            "confidence_counts": {"exact_id": 1},
                        },
                        "bridge_rows": [
                            {
                                "review_member_id": "C-TST-003",
                                "review_case_id": "C-TST-003",
                                "baseline_focus_member_id": "502101",
                                "match_strategy": "manual_embedding",
                                "match_confidence": "external_map",
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_summary_label": "rows=1 | combos=1 | clauses=1 | top=KDS_ULS_2 | bending_moment_y_kNm | KDS-MOMENT-Y-001 | D/C=1.216",
                                "row_provenance_top_row_label": "KDS_ULS_2 | bending_moment_y_kNm | KDS-MOMENT-Y-001 | D/C=1.216",
                                "note": "explicit bridge to baseline member 502101",
                            }
                        ],
                    }
                },
                "load_combinations_raw": [
                    "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0",
                    "ST, DEAD, 1.2, ST, LIVE, 1.6",
                    "NAME=ENV1, GEN, ACTIVE, 0, 1, Envelope refs ULS1, 0, 0, 0",
                    "CB, ULS1, 1",
                ],
            }
        },
    )
    _write_json(
        kds_report,
        {
            "combination_provenance_rows": [
                {
                    "kds_name": "KDS_ULS_2",
                    "matched_runtime_name": "ULS1",
                    "matched_runtime_factor_map": {"D": 1.2, "L": 1.6},
                    "match_score": 0.8333333333333333,
                }
            ],
            "member_check_rows": [
                {
                    "combination": "KDS_ULS_2",
                    "member_id": "C-TST-003",
                    "member_type": "column",
                    "component": "bending_moment_y_kNm",
                    "demand": 3162.159,
                    "capacity": 2600.0,
                    "dcr": 1.2162149999999998,
                    "clause": "KDS-MOMENT-Y-001",
                }
            ],
        },
    )

    module.DEFAULT_KDS_COMPLIANCE_REPORT = kds_report
    context = module._make_midas_load_pattern_context(model_json)
    highlights = {
        str(row["name"]): row
        for row in context["load_combination_highlights"]
    }

    assert context["load_pattern_library_available"] is True
    assert context["load_pattern_source_label"] == "viewer fallback raw recovery"
    assert context["load_combination_editor_seed_source_label"] == "viewer fallback raw recovery"
    assert context["load_combination_browser_available"] is True
    assert context["load_contract_recovery_available"] is True
    assert context["load_contract_recovery_mode_label"] == "combination_only_raw_recovery"
    assert context["load_contract_recovery_summary_label"] == "raw rows=4 | combos=2 | cases=2 | edges=3"
    assert "structured primitive loads are unavailable" in context["load_pattern_recovery_notice_label"]
    assert "combination browser and LOADCOMB round-trip are the authoritative surfaces" in context["load_combination_recovery_notice_label"]
    assert context["load_combination_kds_coverage_label"] == "1/2 runtime combos matched"
    assert context["load_combination_geometry_bridge_available"] is True
    assert context["load_combination_geometry_bridge_source_label"] == "embedded metadata"
    assert context["load_combination_geometry_bridge_summary_label"] == "1/1 review ids mapped | exact=1 | heuristic=0 | rows exact=1 | rows heuristic=0 | confidence=exact_id=1"
    assert highlights["ULS1"]["kds_best_label"] == "KDS_ULS_2 (83%)"
    assert "best mapped KDS combo" in highlights["ULS1"]["kds_note_label"]
    assert highlights["ULS1"]["geometry_bridge_summary_label"] == "1/1 review ids mapped | exact=1 | heuristic=0 | rows exact=1 | rows heuristic=0 | confidence=exact_id=1"
    assert highlights["ULS1"]["code_check_topline_label"] == "member C-TST-003 | column | bending_moment_y_kNm | D/C=1.216"
    assert "3162.159 / 2600.000" in highlights["ULS1"]["code_check_note_label"]
    assert highlights["ULS1"]["recovery_mode_label"] == "combination_only_raw_recovery"
    assert "LOADCOMB round-trip" in highlights["ULS1"]["recovery_notice_label"]
    assert len(highlights["ULS1"]["code_check_top_rows"]) == 1
    assert highlights["ULS1"]["code_check_top_rows"][0]["member_id"] == "C-TST-003"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["row_count_label"] == "1"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["member_id"] == "C-TST-003"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["baseline_focus_member_id"] == "502101"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["bridge_match_strategy_label"] == "manual_embedding"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["bridge_row_provenance_mode_label"] == "exact row-level provenance"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["bridge_member_inventory_summary_label"].startswith("review=C-TST-003")
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["bridge_review_keys_label"] == "C-TST-003"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["clause_title_label"] == "Major-axis flexure check"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["clause_combo_row_count_label"] == "1"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["clause_provenance_summary_label"] == "rows=1 | members=1 | rules=1 | hazards=1"
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["row_index"] == 0
    assert context["load_combination_codecheck_table_by_name"]["ULS1"]["table_rows"][0]["viewer_row_ref"] == "ULS1::0::C-TST-003::C-TST-003"
    assert "nested combo stays browser-side" in highlights["ENV1"]["kds_note_label"]


def test_summarize_shell_only_story_rows_adds_mini_highlight_metadata() -> None:
    module = _load_viewer_module()
    summary = module._summarize_shell_only_story_rows(
        [
            {
                "story_band": 4,
                "zone_label": "perimeter",
                "family": "slab",
                "source_element_type": "shell",
                "group_id": "S04:intermediate:slab",
                "element_id": "990001",
                "node_ids": ["n1", "n2", "n3", "n4"],
            },
            {
                "story_band": 5,
                "zone_label": "perimeter",
                "family": "slab",
                "source_element_type": "shell",
                "group_id": "S05:intermediate:slab",
                "element_id": "990002",
                "node_ids": ["n5", "n6", "n7", "n8"],
            },
        ]
    )

    assert summary["total_panel_count"] == 2
    assert summary["story_path_label"] == "S04 -> S05"
    assert summary["story_focus_label"] == "S04, S05"
    assert summary["rows"][0]["story_step_label"] == "step 1/2"
    assert summary["rows"][0]["story_highlight_label"] == "S04 · step 1/2"
    assert summary["rows"][0]["story_highlight_note_label"] == "S04 adds 1 shell panel at this story height"
    assert summary["rows"][1]["story_step_label"] == "step 2/2"
    assert summary["rows"][1]["story_highlight_label"] == "S05 · step 2/2"
    assert summary["rows"][1]["story_highlight_note_label"] == "S05 adds 1 shell panel at this story height"


def test_results_explorer_payload_surfaces_step_series_and_geometry_depths(tmp_path: Path) -> None:
    module = _load_viewer_module()
    dynamic_report = tmp_path / "dynamic_time_history_report.json"
    ndtha_report = tmp_path / "nonlinear_ndtha_stress_report.json"
    hf_report = tmp_path / "hf_benchmark_report.atwood_open.json"
    model_json = tmp_path / "midas_generator_33.json"
    response_npz = tmp_path / "nonlinear_ndtha_stress_report.response.npz"
    geometry_validation_report = tmp_path / "midas_kds_geometry_bridge_validation_report.json"
    structural_contact_gate_report = tmp_path / "structural_contact_gate_report.json"
    foundation_soil_link_gate_report = tmp_path / "foundation_soil_link_gate_report.json"
    element_material_breadth_gate_report = tmp_path / "element_material_breadth_gate_report.json"
    general_fe_contact_benchmark_gate_report = tmp_path / "general_fe_contact_benchmark_gate_report.json"

    np.savez(
        response_npz,
        case_ids=np.array(["CASE-A"], dtype=object),
        case_keys=np.array(["CASE_A"], dtype=object),
    )
    _write_json(dynamic_report, {"metrics": {}, "checks": {}, "trace_head": []})
    _write_json(
        ndtha_report,
        {
            "summary": {
                "case_count": 1,
                "max_drift_ratio_pct_max": 0.2,
                "residual_drift_ratio_pct_max_abs": 0.05,
                "peak_plastic_story_count_mean": 1.0,
                "elapsed_wall_s": 1.5,
            },
            "checks": {"solver_control_history_pass": True, "residual_metric_sanity_pass": True},
            "material_effect_rows": [
                {"case_id": "CASE-A"},
                {"case_id": "CASE-B"},
                {"case_id": "CASE-C"},
            ],
            "rows": [
                {
                    "case_id": "CASE-A",
                    "summary": {"material_model": "rc"},
                    "response": {
                        "story_drift_envelope_pct": [0.1, 0.2],
                        "final_story_drift_pct": [0.03, 0.04],
                    },
                    "artifacts": {
                        "response_npz_out": str(response_npz),
                    },
                    "solver_control": {
                        "event_history_head": [
                            {"step": 1, "event": "cutback", "severity": "warn", "recommended_dt_scale": 0.5}
                        ],
                        "event_count_total": 1,
                        "nonconverged_step_total": 0,
                        "cutback_case_count": 1,
                        "recommended_dt_scale_min": 0.5,
                    },
                }
            ],
            "response_npz": {
                "path": str(response_npz),
                "case_count": 1,
                "array_count": 5,
                "storage": "npz_external",
                "series_case_count": 1,
                "series_contract_pass": True,
                "full_step_count_max": 7,
                "inline_step_count_max": 2,
            },
            "solver_control": {
                "history_pass": True,
                "event_sequence_pass": True,
                "event_count_total": 1,
                "nonconverged_step_total": 0,
                "cutback_case_count": 1,
                "recommended_dt_scale_min": 0.5,
            },
        },
    )
    _write_json(
        geometry_validation_report,
        {
            "summary": {
                "full_member_crosswalk_count_total": 242,
                "full_member_crosswalk_expected_total": 242,
                "full_section_crosswalk_count_total": 200,
                "full_section_crosswalk_expected_total": 200,
                "full_load_crosswalk_count_total": 51,
                "full_load_crosswalk_expected_total": 51,
            },
                "checks": {
                "full_member_crosswalk_pass": True,
                "full_section_crosswalk_pass": True,
                "full_load_crosswalk_pass": True,
            },
        },
    )
    _write_json(
        structural_contact_gate_report,
        {
            "support_surface_evidence": {
                "support_search_family_types": ["device_support_search", "foundation_support_search"],
                "node_to_surface_proxy_family_types": ["device_support_search", "foundation_support_search"],
            }
        },
    )
    _write_json(
        foundation_soil_link_gate_report,
        {
            "summary": {
                "support_search_family_types": ["device_support_search", "foundation_support_search"],
                "node_to_surface_proxy_family_types": ["device_support_search", "foundation_support_search"],
            }
        },
    )
    _write_json(
        element_material_breadth_gate_report,
        {
            "summary": {
                "assembled_global_depth_signal_count": 5,
            }
        },
    )
    _write_json(
        general_fe_contact_benchmark_gate_report,
        {
            "summary": {
                "support_search_family_count": 2,
                "node_to_surface_proxy_family_count": 2,
                "coupling_depth_score": 31,
            },
            "summary_line": (
                "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | "
                "interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | "
                "support_search=9 | node_surface_proxy=5 | support_depth=21 | coupling_depth=31 | "
                "support_families=2/2 | proxy_families=2/2"
            ),
        },
    )
    _write_json(
        hf_report,
        {
            "metrics": {},
            "checks": {},
            "comparison": {},
        },
    )
    _write_json(
        model_json,
        {
            "model": {
                "metadata": {
                    "kds_geometry_bridge": {
                        "contract_version": "0.1.0",
                        "summary": {
                            "review_row_count": 4,
                            "review_id_count": 2,
                            "mapped_review_id_count": 2,
                            "exact_mapped_review_id_count": 2,
                            "heuristic_mapped_review_id_count": 0,
                            "mapped_row_provenance_count": 4,
                            "exact_mapped_row_provenance_count": 4,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"manual_verified_exact_focus": 2},
                            "confidence_counts": {"manual_verified_exact_focus": 2},
                        },
                        "bridge_rows": [
                            {
                                "review_member_id": "M-001",
                                "review_case_id": "M-001",
                                "baseline_focus_member_id": "101",
                                "match_strategy": "manual_verified_exact_focus",
                                "match_confidence": "manual_verified_exact_focus",
                                "row_provenance_row_count": 2,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_summary_label": "rows=2 | combos=1 | clauses=1",
                                "row_provenance_top_row_label": "KDS_ULS_2 | bending_moment_y_kNm | KDS-MOMENT-Y-001 | D/C=1.216",
                                "note": "explicit bridge to baseline member 101",
                            }
                        ],
                    }
                }
            }
        },
    )

    module.DEFAULT_DYNAMIC_TIME_HISTORY_REPORT = dynamic_report
    module.DEFAULT_NDTHA_STRESS_REPORT = ndtha_report
    module.DEFAULT_HF_BENCHMARK_REPORT = hf_report
    module.DEFAULT_MODEL_JSON = model_json
    module.DEFAULT_MIDAS_KDS_GEOMETRY_BRIDGE_VALIDATION_REPORT = geometry_validation_report
    module.DEFAULT_STRUCTURAL_CONTACT_GATE_REPORT = structural_contact_gate_report
    module.DEFAULT_FOUNDATION_SOIL_LINK_GATE_REPORT = foundation_soil_link_gate_report
    module.DEFAULT_ELEMENT_MATERIAL_BREADTH_GATE_REPORT = element_material_breadth_gate_report
    module.DEFAULT_GENERAL_FE_CONTACT_BENCHMARK_GATE_REPORT = general_fe_contact_benchmark_gate_report

    results = module._results_explorer_payload({}, base_dir=tmp_path, model_json_path=model_json)
    html = module._results_explorer_markup(results)

    assert results["ndtha_response"]["step_series_depth_available"] is True
    assert results["ndtha_response"]["step_series_depth_label"] == "7"
    assert results["ndtha_response"]["material_effect_depth_available"] is True
    assert results["ndtha_response"]["material_effect_row_count"] == 3
    assert results["ndtha_response"]["material_effect_depth_label"] == "3"
    assert results["ndtha_step_series_depth_available"] is True
    assert results["ndtha_step_series_depth_label"] == "7"
    assert results["ndtha_material_depth_available"] is True
    assert results["ndtha_material_depth_label"] == "3"
    assert results["contact_material_depth_available"] is True
    assert results["contact_material_depth_summary_label"] == (
        "support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3"
    )
    assert results["general_fe_contact_coupling_available"] is True
    assert results["general_fe_contact_coupling_summary_label"] == (
        "support families=2 | proxy families=2 | coupling depth=31 | assembled depth=5"
    )
    assert results["general_fe_contact_matrix_summary_line"].startswith("General FE contact matrix: PASS")
    assert results["contact_material_integration"]["support_family_count"] == 2
    assert results["contact_material_integration"]["proxy_family_count"] == 2
    assert results["contact_material_integration"]["assembled_depth_value"] == 5
    assert results["geometry_crosswalk"]["available"] is True
    assert results["geometry_crosswalk"]["full_crosswalk_depth_available"] is True
    assert results["geometry_crosswalk"]["full_crosswalk_depth_label"] == "4"
    assert results["geometry_crosswalk"]["full_member_crosswalk_label"] == "242/242 PASS"
    assert results["geometry_crosswalk"]["full_section_crosswalk_label"] == "200/200 PASS"
    assert results["geometry_crosswalk"]["full_load_crosswalk_label"] == "51/51 PASS"
    assert results["geometry_crosswalk"]["full_crosswalk_aggregate_label"] == (
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert results["geometry_crosswalk"]["full_crosswalk_detail_label"] == (
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert results["geometry_full_crosswalk_depth_available"] is True
    assert results["geometry_full_crosswalk_depth_label"] == "4"
    assert results["geometry_full_crosswalk_detail_available"] is True
    assert results["geometry_full_crosswalk_detail_label"] == (
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert results["traceability"]["surface_depth_summary_label"] == (
        "NDTHA step-series depth=7 | geometry full-crosswalk depth=4 | geometry full-crosswalk aggregate="
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert results["traceability"]["ndtha_step_series_depth_label"] == "7"
    assert results["traceability"]["geometry_full_crosswalk_depth_label"] == "4"
    assert results["traceability"]["surface_detail_summary_label"] == (
        "NDTHA material depth=3 | geometry full-crosswalk detail=full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert results["traceability"]["ndtha_material_depth_label"] == "3"
    assert results["traceability"]["contact_material_depth_summary_label"] == (
        "support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3"
    )
    assert results["traceability"]["general_fe_contact_coupling_summary_label"] == (
        "support families=2 | proxy families=2 | coupling depth=31 | assembled depth=5"
    )
    assert results["traceability"]["geometry_full_crosswalk_aggregate_label"] == (
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert results["traceability"]["geometry_full_crosswalk_detail_label"] == (
        "full member=242/242 PASS | full section=200/200 PASS | full load=51/51 PASS"
    )
    assert "Geometry Crosswalk" in html
    assert "Full bridge crosswalk depth and aggregate" in html
    assert "step-series depth" in html
    assert "full crosswalk depth" in html
    assert "NDTHA material depth=3" in html
    assert "general-fe/contact=support families=2 | proxy families=2 | coupling depth=31 | assembled depth=5" in html
    assert "contact-material=support families=2 | proxy families=2 | assembled depth=5 | NDTHA/material depth=7/3" in html
    assert "full member=242/242 PASS" in html
    assert "full section=200/200 PASS" in html
    assert "full load=51/51 PASS" in html


def test_resolve_row_provenance_deep_link_prefers_filtered_subset_row_and_member_context(tmp_path: Path) -> None:
    module = _load_viewer_module()
    model_json = tmp_path / "model.json"
    kds_report = tmp_path / "code_check_report.json"
    _write_json(
        model_json,
        {
            "model": {
                "metadata": {
                    "kds_geometry_bridge": {
                        "contract_version": "0.1.0",
                        "summary": {
                            "review_row_count": 2,
                            "review_id_count": 2,
                            "mapped_review_id_count": 2,
                            "exact_mapped_review_id_count": 2,
                            "heuristic_mapped_review_id_count": 0,
                            "mapped_row_provenance_count": 2,
                            "unmapped_review_id_count": 0,
                            "exact_mapped_row_provenance_count": 2,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"manual_embedding": 2},
                            "confidence_counts": {"exact_id": 2},
                        },
                        "bridge_rows": [
                            {
                                "review_member_id": "C-GRV-001",
                                "review_case_id": "C-GRV-001",
                                "baseline_focus_member_id": "502101",
                                "match_strategy": "manual_embedding",
                                "match_confidence": "external_map",
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_summary_label": "rows=1 | combos=1 | clauses=1",
                                "row_provenance_top_row_label": "ULS1 | gravity",
                                "note": "gravity row",
                            },
                            {
                                "review_member_id": "C-WND-002",
                                "review_case_id": "C-WND-002",
                                "baseline_focus_member_id": "502202",
                                "match_strategy": "manual_embedding",
                                "match_confidence": "external_map",
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_summary_label": "rows=1 | combos=1 | clauses=1",
                                "row_provenance_top_row_label": "ULS1 | wind",
                                "note": "wind row",
                            },
                        ],
                    }
                },
                "load_combinations_raw": [
                    "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.0(WX), 0, 0, 0",
                    "ST, DEAD, 1.2, ST, WINDX, 1.0",
                ],
            }
        },
    )
    _write_json(
        kds_report,
        {
            "combination_provenance_rows": [
                {
                    "kds_name": "KDS_ULS_2",
                    "matched_runtime_name": "ULS1",
                    "matched_runtime_factor_map": {"D": 1.2, "WX": 1.0},
                    "match_score": 0.9,
                }
            ],
            "member_check_rows": [
                {
                    "combination": "KDS_ULS_2",
                    "member_id": "C-GRV-001",
                    "member_type": "column",
                    "component": "bending_moment_y_kNm",
                    "hazard_type": "gravity",
                    "rule_family": "moment",
                    "topology_type": "frame",
                    "demand": 3000.0,
                    "capacity": 2500.0,
                    "dcr": 1.20,
                    "clause": "KDS-MOMENT-Y-001",
                },
                {
                    "combination": "KDS_ULS_2",
                    "member_id": "C-WND-002",
                    "member_type": "column",
                    "component": "shear_force_y_kN",
                    "hazard_type": "wind",
                    "rule_family": "shear",
                    "topology_type": "frame",
                    "demand": 900.0,
                    "capacity": 1200.0,
                    "dcr": 0.75,
                    "clause": "KDS-SHEAR-Y-001",
                },
            ],
        },
    )

    module.DEFAULT_KDS_COMPLIANCE_REPORT = kds_report
    context = module._make_midas_load_pattern_context(model_json)
    table_by_name = context["load_combination_codecheck_table_by_name"]
    resolved = module._resolve_row_provenance_deep_link(
        table_by_name=table_by_name,
        query={
            "source": "row_provenance_subset_csv",
            "combination": "ULS1",
            "hazard": "wind",
            "member_set": "502101|502202",
            "view": "midas",
            "focus": "interactive3d",
            "results_card": "time-history",
            "results_series": "1",
            "codecheck_surface": "drilldown",
        },
    )

    assert resolved["matched_via"] == "filtered_first"
    assert resolved["row_index"] == 1
    assert resolved["hazard_label"] == "wind"
    assert resolved["rule_family_label"] == "shear"
    assert resolved["focus_member"] == "502202"
    assert resolved["row_ref"] == "ULS1::1::C-WND-002::C-WND-002"
    assert resolved["viewer_reading_mode"] == "midas"
    assert resolved["focus_target"] == "interactive3d"
    assert resolved["results_card"] == "time-history"
    assert resolved["results_series_index"] == 1
    assert resolved["codecheck_surface"] == "drilldown"
    assert resolved["reverse_sync_contract_version"] == "viewer_subset_reverse_jump_v11"
    assert resolved["results_companion"] == "interactive"
    assert resolved["results_companion_focus_key"] == "chart-marker:0"
    assert resolved["results_companion_selection_key"] == "results-companion:interactive"
    assert resolved["member_ids"] == ["502101", "502202"]
    assert resolved["selection_set_count"] == 2
    assert resolved["selection_label"] == "502101, 502202"
    assert resolved["codecheck_companion"] == "detail"
    assert resolved["codecheck_companion_focus_key"] == "row-provenance:jump-row"
    assert resolved["codecheck_companion_selection_key"] == "codecheck-companion:detail"
    assert resolved["results_sample_index"] == 0
    assert resolved["results_detail_focus_key"] == "chart-marker:0"
    assert resolved["results_detail_selection_key"] == "results-detail:chart"
    assert resolved["results_detail_item_index"] == 0
    assert resolved["results_companion_item_index"] == 0
    assert resolved["codecheck_filtered_row_index"] == 0
    assert resolved["codecheck_clause_index"] == 1
    assert resolved["codecheck_hazard_index"] == 1
    assert resolved["codecheck_rule_family_index"] == 1
    assert resolved["results_detail_block"] == "chart"
    assert resolved["codecheck_detail_block"] == "row-provenance"
    assert resolved["codecheck_appendix_block"] == "subset-summary"
    assert resolved["codecheck_detail_focus_key"] == "row-provenance:jump-row"
    assert resolved["codecheck_detail_selection_key"] == "codecheck-detail:row-provenance"
    assert resolved["codecheck_companion_item_index"] == 0
    assert resolved["codecheck_detail_item_index"] == 0
    assert resolved["codecheck_appendix_focus_key"] == "subset:current-slice"
    assert resolved["codecheck_appendix_selection_key"] == "codecheck-appendix:subset-summary"
    assert resolved["codecheck_appendix_item_index"] == 0
    assert resolved["interactive_detail_more"] == "open"
    assert resolved["overlay_detail_more"] == "open"
    assert resolved["baseline_secondary"] == "elevation"


def test_viewer_source_contains_reverse_sync_results_and_codecheck_contract() -> None:
    source_text = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/generate_structural_optimization_visualization_viewer.py"
    ).read_text(encoding="utf-8")

    assert "resultsCard: String(initialDeepLinkParams.get('results_card') || '').trim().toLowerCase()" in source_text
    assert "codecheckSurface: String(initialDeepLinkParams.get('codecheck_surface') || '').trim().toLowerCase()" in source_text
    assert "resultsCompanion: String(initialDeepLinkParams.get('results_companion') || '').trim().toLowerCase()" in source_text
    assert "codecheckCompanion: String(initialDeepLinkParams.get('codecheck_companion') || '').trim().toLowerCase()" in source_text
    assert "resultsSampleIndex: String(" in source_text
    assert "resultsDetailItemIndex: String(" in source_text
    assert "resultsCompanionItemIndex: String(" in source_text
    assert "codecheckFilteredRowIndex: String(" in source_text
    assert "codecheckClauseIndex: String(" in source_text
    assert "codecheckHazardIndex: String(" in source_text
    assert "codecheckRuleFamilyIndex: String(" in source_text
    assert "codecheckCompanionItemIndex: String(" in source_text
    assert "resultsDetailBlock: String(" in source_text
    assert "codecheckDetailBlock: String(initialDeepLinkParams.get('codecheck_detail_block') || '').trim().toLowerCase()" in source_text
    assert "codecheckAppendixBlock: String(" in source_text
    assert "resultsCompanionFocusKey: String(initialDeepLinkParams.get('results_companion_focus_key') || '').trim()," in source_text
    assert "resultsDetailFocusKey: String(initialDeepLinkParams.get('results_detail_focus_key') || '').trim()," in source_text
    assert "codecheckCompanionFocusKey: String(initialDeepLinkParams.get('codecheck_companion_focus_key') || '').trim()," in source_text
    assert "resultsCompanionSelectionKey: String(initialDeepLinkParams.get('results_companion_selection_key') || '').trim()," in source_text
    assert "resultsDetailSelectionKey: String(initialDeepLinkParams.get('results_detail_selection_key') || '').trim()," in source_text
    assert "codecheckCompanionSelectionKey: String(initialDeepLinkParams.get('codecheck_companion_selection_key') || '').trim()," in source_text
    assert "overlayRowId: String(initialDeepLinkParams.get('overlay_row_id') || '').trim()," in source_text
    assert "panelZoneGroupId: String(initialDeepLinkParams.get('panel_zone_group_id') || '').trim()," in source_text
    assert "panelZoneSectionSignature: String(initialDeepLinkParams.get('panel_zone_section_signature') || '').trim()," in source_text
    assert "panelZoneLinkMode: String(initialDeepLinkParams.get('panel_zone_link_mode') || '').trim().toLowerCase()," in source_text
    assert "benchmarkFamily: String(initialDeepLinkParams.get('benchmark_family') || '').trim()," in source_text
    assert "benchmarkStoryBand: String(initialDeepLinkParams.get('benchmark_story_band') || '').trim()," in source_text
    assert "benchmarkZoneId: String(initialDeepLinkParams.get('benchmark_zone_id') || '').trim()," in source_text
    assert "benchmarkZoneLabel: String(initialDeepLinkParams.get('benchmark_zone_label') || '').trim()," in source_text
    assert "benchmarkMatrix: String(initialDeepLinkParams.get('benchmark_matrix') || '').trim().toLowerCase()," in source_text
    assert "writebackDiffJson: String(initialDeepLinkParams.get('writeback_diff_json') || '').trim()," in source_text
    assert "writebackDiffHtml: String(initialDeepLinkParams.get('writeback_diff_html') || '').trim()," in source_text
    assert "writebackReport: String(initialDeepLinkParams.get('writeback_report') || '').trim()," in source_text
    assert "writebackPatchManifest: String(initialDeepLinkParams.get('writeback_patch_manifest') || '').trim()," in source_text
    assert "writebackInstructionSidecar: String(initialDeepLinkParams.get('writeback_instruction_sidecar') || '').trim()," in source_text
    assert "writebackOutputMgt: String(initialDeepLinkParams.get('writeback_output_mgt') || '').trim()," in source_text
    assert "writebackCompareJson: String(initialDeepLinkParams.get('writeback_compare_json') || '').trim()," in source_text
    assert "writebackCompareHtml: String(initialDeepLinkParams.get('writeback_compare_html') || '').trim()," in source_text
    assert "writebackCompareStatus: String(initialDeepLinkParams.get('writeback_compare_status') || '').trim()," in source_text
    assert "writebackCompareSummary: String(initialDeepLinkParams.get('writeback_compare_summary') || '').trim()," in source_text
    assert "writebackCompareKindSummary: String(initialDeepLinkParams.get('writeback_compare_kind_summary') || '').trim()," in source_text
    assert "writebackCompareRowIds: parsePipeTokenList(initialDeepLinkParams.get('writeback_compare_row_ids') || '')," in source_text
    assert "writebackCompareRowCount: String(initialDeepLinkParams.get('writeback_compare_row_count') || '').trim()," in source_text
    assert "const hasWritebackDiffContext = [" in source_text
    assert "resultsWritebackDiffContext" in source_text
    assert "updateResultsWritebackDiffShell" in source_text
    assert "const isPanelZoneRowProvenanceSource = initialDeepLinkSource.startsWith('panel_zone_row_provenance');" in source_text
    assert "const isAnyRowProvenanceSource = initialDeepLinkSource.startsWith('row_provenance') || isPanelZoneRowProvenanceSource;" in source_text
    assert "codecheckDetailFocusKey: String(initialDeepLinkParams.get('codecheck_detail_focus_key') || '').trim()," in source_text
    assert "codecheckDetailSelectionKey: String(initialDeepLinkParams.get('codecheck_detail_selection_key') || '').trim()," in source_text
    assert "codecheckAppendixFocusKey: String(initialDeepLinkParams.get('codecheck_appendix_focus_key') || '').trim()," in source_text
    assert "codecheckAppendixSelectionKey: String(initialDeepLinkParams.get('codecheck_appendix_selection_key') || '').trim()," in source_text
    assert "codecheckDetailItemIndex: String(" in source_text
    assert "codecheckAppendixItemIndex: String(" in source_text
    assert "interactiveDetailMore: String(initialDeepLinkParams.get('interactive_detail_more') || '').trim().toLowerCase()" in source_text
    assert "overlayDetailMore: String(initialDeepLinkParams.get('overlay_detail_more') || '').trim().toLowerCase()" in source_text
    assert "baselineSecondary: parsePipeTokenList(initialDeepLinkParams.get('baseline_secondary') || '')" in source_text
    assert "data-results-companion-section='interactive'" in source_text
    assert "data-results-detail-block='chart'" in source_text
    assert "data-midas-load-codecheck-role='reviewer-appendix'" in source_text
    assert 'data-midas-load-codecheck-detail-block="row-provenance"' in source_text
    assert 'data-midas-load-codecheck-appendix-block="subset-summary"' in source_text
    assert "const resolveMidasLoadCodecheckPreferredMemberIds = (options = {{}}) => {{" in source_text
    assert "const summarizeMidasLoadCodecheckSelectionSet = (rowsOrEntries = [], preferredMemberIds = [], diagnosticsOptions = {{}}) => {{" in source_text
    assert "buildMidasLoadCodecheckMissingReasonLabel" in source_text
    assert "buildMidasLoadCodecheckMissingReasonHint" in source_text
    assert "diagnoseMidasLoadCodecheckMissingMember" in source_text
    assert "memberSummaries" in source_text
    assert "matchedMemberIds" in source_text
    assert "missingMemberIds" in source_text
    assert "missingMemberDiagnostics" in source_text
    assert "missingReasonSummaryLabel" in source_text
    assert "missingReasonActionSummaryLabel" in source_text
    assert "selectionSetMatchedRowCount" in source_text
    assert "selection-set members" in source_text
    assert "data-midas-load-codecheck-detail-block=\"selection-set\"" in source_text
    assert "Selection-set review surface" in source_text
    assert "selection-set:matched-rows" in source_text
    assert "buildResultsSelectionSetCompareHtml" in source_text
    assert "getResultsSelectionSetMemberHref" in source_text
    assert "results-selection-set-compare-shell" in source_text
    assert "results-selection-set-matrix-wrap" in source_text
    assert "results-selection-set-matrix-head-member" in source_text
    assert "results-selection-set-matrix-cell" in source_text
    assert "results-selection-set-member-matrix" in source_text
    assert "results-selection-set-member-card" in source_text
    assert "results-selection-set-compare-summary" in source_text
    assert "results-selection-set-compare-console" in source_text
    assert "results-selection-set-member-console" in source_text
    assert "results-selection-set-member-console-item" in source_text
    assert "Selection-set compare console" in source_text
    assert "Selection-set side-by-side matrix" in source_text
    assert "per-member console metrics and review actions tied to the current results sample" in source_text
    assert "Compare summary" in source_text
    assert "Member status console" in source_text
    assert "Per-member detail console" in source_text
    assert "Missing diagnostics" in source_text
    assert "Suggested actions" in source_text
    assert "Missing reason" in source_text
    assert "Suggested action" in source_text
    assert "Writeback review" in source_text
    assert "Writeback action" in source_text
    assert "Writeback status" in source_text
    assert "Writeback next step" in source_text
    assert "Writeback diff row matrix" in source_text
    assert "open writeback diff row review" in source_text
    assert "open writeback-linked member review" in source_text
    assert "Actual regenerated artifact compare" in source_text
    assert "open regenerated compare review" in source_text
    assert "open regenerated compare JSON" in source_text
    assert "before / after review from the same optimized member overlay" in source_text
    assert "Writeback Diff Review" in source_text
    assert "data-results-writeback-diff-link='html'" in source_text
    assert "data-results-writeback-diff-link='compare-html'" in source_text
    assert "data-results-writeback-diff-link='compare-json'" in source_text
    assert "Open standalone diff review" in source_text
    assert "Row density" in source_text
    assert "Governing D/C spread" in source_text
    assert "Member profile" in source_text
    assert "Case / bridge state" in source_text
    assert "Bridge / aliases" in source_text
    assert "Next review step" in source_text
    assert "selection-set compare" in source_text
    assert "open governing row" in source_text
    assert "current slice csv" in source_text
    assert "Next:" in source_text
    assert "midas-load-codecheck-table-chip" in source_text
    assert "setMidasLoadCodecheckDetailBlock(requestedDetailBlock" in source_text
    assert "setResultsExplorerDetailBlock(cardKey, requestedDetailBlock" in source_text
    assert "setMidasLoadCodecheckAppendixBlock(requestedAppendixBlock" in source_text
    assert "syncResultsExplorerCard(getResultsExplorerActiveCardKey());" in source_text
    assert "data-deep-link-selection-key" in source_text
    assert "midasLoadCodecheckState.filteredRowDisplayIndex = 0;" in source_text
    assert "midasLoadCodecheckState.clauseSelectionIndex = 0;" in source_text
    assert "const resolveInitialViewerReadingMode = () => {{" in source_text
    assert source_text.index("setViewerReadingMode(initialViewerReadingMode);") < source_text.index(
        "applyInitialViewerDeepLink();"
    )


def test_native_authoring_solver_ops_evidence_surfaces_solver_session_and_ops_bundle(tmp_path: Path) -> None:
    module = _load_viewer_module()
    workspace_summary = tmp_path / "native_authoring_workspace_summary.json"
    solver_session = tmp_path / "native_authoring_solver_session.json"
    ops_bundle = tmp_path / "native_authoring_ops_bundle.json"
    batch_job_report = tmp_path / "native_authoring_batch_job_report.json"
    portfolio_workspace = tmp_path / "project_registry_portfolio_workspace.json"
    ops_portfolio = tmp_path / "native_authoring_ops_portfolio.json"
    family_corpus_manifest = tmp_path / "native_authoring_family_corpus_manifest.json"
    runtime_submission_lane = tmp_path / "native_authoring_runtime_submission_lane.json"
    runtime_writeback_depth = tmp_path / "native_authoring_runtime_writeback_depth_report.json"
    local_runtime_scenario_depth = tmp_path / "native_authoring_local_runtime_scenario_depth_report.json"
    local_variant_writeback_trace = tmp_path / "native_authoring_local_variant_writeback_trace_report.json"
    solver_family_breadth = tmp_path / "native_authoring_solver_family_breadth_report.json"
    writeback_breadth = tmp_path / "native_authoring_writeback_breadth_report.json"
    project_ops_service_snapshot = tmp_path / "project_ops_service_snapshot.json"
    multi_project_runtime_writeback = (
        tmp_path / "native_authoring_multi_project_runtime_writeback_report.json"
    )
    family_solver_session = tmp_path / "portfolio_sample_tower_solver_session.json"
    loadcomb_preview = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"
    loadcomb_preview.write_text("*LOADCOMB\n", encoding="utf-8")
    family_specs = _native_authoring_family_specs(
        tmp_path,
        sample_solver_session_path=family_solver_session,
        loadcomb_preview_path=loadcomb_preview,
    )
    family_count = len(family_specs)
    total_combo_count = sum(int(spec["solver_combo_count"]) for spec in family_specs)
    total_mesh_request_count = sum(int(spec["solver_mesh_request_count"]) for spec in family_specs)

    _write_json(
        workspace_summary,
        {
            "summary_line": "Native authoring bundle: PASS | stories=5 | nodes=24 | members=35 | loads=4 | unsupported=0 | unresolved=0 | score=100.0",
            "contract_pass": True,
            "editor_controls": {
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
                "model_id": "authoring-tower-a",
                "native_authoring_ready": True,
                "solver_ready_score": 100.0,
                "member_type_counts": {
                    "beam": 15,
                    "column": 20,
                },
            },
        },
    )
    _write_json(
        solver_session,
        {
            "session_id": "authoring-session-01",
            "summary_line": "Native authoring solver session: PASS | meshes=2 | cells=588 | combos=13 | family=KDS-2022",
            "contract_pass": True,
            "summary": {
                "model_id": "authoring-tower-a",
                "combo_count": 13,
                "mesh_request_count": 2,
                "load_case_count": 4,
                "loadcomb_line_count": 37,
                "family": "KDS-2022",
                "session_ready": True,
            },
            "authoring_summary": {
                "model_id": "authoring-tower-a",
                "native_authoring_ready": True,
                "solver_ready_score": 100.0,
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
                "loadcomb_preview_line_count": 37,
                "runtime_summary": {
                    "authoring_ready": True,
                    "combo_count": 13,
                    "runtime_case_count": 4,
                    "summary_line": "Runtime load-combination authoring: PASS | combos=13 | linear=13 | nested=0 | max_depth=1 | cases=4 | unresolved=0",
                },
            },
            "artifacts": {
                "loadcomb_preview_mgt": str(loadcomb_preview),
            },
        },
    )
    _write_json(
        batch_job_report,
        {
            "summary_line": "Batch job runner: PASS | jobs=3 | snapshots=3 | reruns=0 | statuses=completed=3",
            "contract_pass": True,
            "summary": {
                "job_count": 3,
                "snapshot_count": 3,
            },
        },
    )
    _write_json(
        family_solver_session,
        {
            "contract_pass": True,
            "summary": {
                "session_ready": True,
                "combo_count": 13,
                "mesh_request_count": 2,
                "member_count": 35,
                "load_pattern_count": 4,
            },
            "selected_family": {
                "label": "Sample Tower",
                "description": "Baseline mixed RC-steel tower scaffold.",
            },
            "authoring_summary": {
                "member_type_counts": {
                    "beam": 15,
                    "column": 20,
                },
            },
        },
    )
    _write_json(
        portfolio_workspace,
        {
            "summary_line": "Project registry portfolio workspace: PASS | projects=8 | unique=8 | complete=8 | signature=8 | repro=8",
            "contract_pass": True,
            "summary": {
                "project_count": family_count,
                "complete_project_count": family_count,
                "signature_verified_count": family_count,
                "package_reproducible_count": family_count,
                "family_count": family_count,
                "ready_family_count": family_count,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "draft_labels": [str(spec["draft_label"])],
                    "project_ids": [str(spec["project_id"])],
                    "registry_count": 1,
                    "complete_registry_count": 1,
                    "signature_verified_count": 1,
                    "package_reproducible_count": 1,
                    "latest_path": str(spec["artifacts"]["project_registry_json"]),
                    "latest_project_name": str(spec["project_name"]),
                }
                for spec in family_specs
            ],
            "scan": {
                "summary": {
                    "unmatched_input_count": 0,
                },
            },
            "artifacts": {
                "project_registry_portfolio_workspace_json": str(portfolio_workspace),
                "project_registry_index_json": str(tmp_path / "project_registry_index.json"),
            },
        },
    )
    _write_json(
        ops_portfolio,
        {
            "summary": {
                "family_count": family_count,
                "ready_family_count": family_count,
            },
            "summary_line": "Native authoring ops portfolio: PASS | families=8 | ready=8 | runtime_submission=8 | local_variant_trace=8",
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "project_id": str(spec["project_id"]),
                    "project_name": str(spec["project_name"]),
                    "draft_label": str(spec["draft_label"]),
                    "solver_combo_count": int(spec["solver_combo_count"]),
                    "solver_mesh_request_count": int(spec["solver_mesh_request_count"]),
                    "job_count": int(spec["job_count"]),
                    "snapshot_count": int(spec["snapshot_count"]),
                    "member_count": int(spec["member_count"]),
                    "load_pattern_count": int(spec["load_pattern_count"]),
                    "contract_pass": True,
                    "summary_line": (
                        f"Native authoring ops bundle: PASS | family={spec['family_id']} | "
                        f"source=generated | ready=True | solver_combos={spec['solver_combo_count']} | "
                        f"jobs={spec['job_count']} | snapshots={spec['snapshot_count']} | package_artifacts=4"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
            "artifacts": {
                "native_authoring_local_variant_writeback_trace_report_json": str(local_variant_writeback_trace),
            },
            "local_variant_writeback_trace_summary": {
                "family_count": family_count,
                "deep_ready_family_count": family_count,
                "targeted_family_count": 0,
                "workspace_variant_ready_family_count": family_count,
                "solver_variant_ready_family_count": family_count,
                "writeback_trace_ready_family_count": family_count,
                "active_multi_family_count": family_count,
                "combo_multi_family_count": family_count,
                "signed_writeback_family_count": family_count,
                "omitted_library_family_count": 0,
            },
            "local_variant_writeback_trace_summary_line": (
                "Native authoring local variant/writeback trace: PASS | families=8 | deep=8 | targeted=0 | "
                "workspace_variant=8 | solver_variant=8 | writeback_trace=8 | signed=8"
            ),
        },
    )
    _write_json(
        family_corpus_manifest,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring family corpus manifest: PASS | families=8 | ready=8 | internal=32 | "
                "public_refs=24 | authority=5 | benchmark=10 | design=9 | "
                "surfaces=catalog_card=8, guided_demo=8, technical_review=8, benchmark_story=8, regional_design_seed=6"
            ),
            "summary": {
                "family_count": family_count,
                "ready_family_count": family_count,
                "public_reference_count": 24,
                "design_reference_count": 9,
                "benchmark_reference_count": 10,
                "authority_reference_count": 5,
                "surface_count": 5,
                "surface_label": "Catalog Card | Guided Demo | Technical Review | Benchmark Story | Regional Design Seed",
                "unresolved_reference_count": 0,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "contract_pass": True,
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        runtime_submission_lane,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring runtime submission lane: PASS | families=8 | submission_ready=8 | "
                "runtime_ready=8 | writeback_ready=8 | full_ready=8 | approvals=24"
            ),
            "summary": {
                "family_count": family_count,
                "full_ready_count": family_count,
                "submission_ready_count": family_count,
                "runtime_ready_count": family_count,
                "writeback_ready_count": family_count,
                "job_ready_count": family_count,
                "registry_ready_count": family_count,
                "signature_verified_count": family_count,
                "release_ready_count": family_count,
                "queued_submission_count": 0,
                "total_approval_count": 24,
                "total_solver_combo_count": total_combo_count,
                "total_solver_mesh_request_count": total_mesh_request_count,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "authoring_family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "project_id": str(spec["project_id"]),
                    "project_name": str(spec["project_name"]),
                    "draft_label": str(spec["draft_label"]),
                    "member_count": int(spec["member_count"]),
                    "load_pattern_count": int(spec["load_pattern_count"]),
                    "member_type_count": len(str(spec["member_type_label"]).split(",")),
                    "member_type_label": str(spec["member_type_label"]),
                    "solver_combo_count": int(spec["solver_combo_count"]),
                    "solver_mesh_request_count": int(spec["solver_mesh_request_count"]),
                    "solver_mesh_cell_count": int(spec["solver_mesh_cell_count"]),
                    "solver_load_case_count": int(spec["solver_load_case_count"]),
                    "solver_loadcomb_line_count": int(spec["solver_loadcomb_line_count"]),
                    "job_count": int(spec["job_count"]),
                    "snapshot_count": int(spec["snapshot_count"]),
                    "approval_count": int(spec["approval_count"]),
                    "node_count": int(spec["node_count"]),
                    "story_count": int(spec["story_count"]),
                    "palette_family_count": int(spec["palette_family_count"]),
                    "palette_family_label": str(spec["palette_family_label"]),
                    "active_family_count": int(spec["active_family_count"]),
                    "active_family_label": str(spec["active_family_label"]),
                    "contract_pass": True,
                    "ops_ready": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "submission_ready": True,
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "family_track_row_present": True,
                    "source_surface_complete": True,
                    "summary_line": (
                        f"{spec['family_id']}: READY | solver_combos={spec['solver_combo_count']} | "
                        f"mesh_requests={spec['solver_mesh_request_count']} | approvals={spec['approval_count']}"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        runtime_writeback_depth,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring runtime writeback depth: PASS | families=8 | full_depth=8 | targeted=0 | "
                "registry=8 | signature=8 | repro=8 | snapshot=8 | queue_clear=8"
            ),
            "summary": {
                "family_count": family_count,
                "depth_ready_family_count": family_count,
                "targeted_family_count": 0,
                "registry_ready_family_count": family_count,
                "signature_verified_family_count": family_count,
                "package_reproducible_family_count": family_count,
                "snapshot_ready_family_count": family_count,
                "queue_clear_family_count": family_count,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "contract_pass": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "runtime_ready": True,
                    "summary_line": (
                        f"{spec['family_id']}: FULL_DEPTH | registry=yes | signature=yes | "
                        f"snapshot={spec['snapshot_count']}"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        local_runtime_scenario_depth,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring local runtime scenario depth: PASS | families=8 | deep=8 | targeted=0 | "
                "trace_ready=8 | mesh_ready=8 | runtime_ready=8 | omitted=0"
            ),
            "summary": {
                "family_count": family_count,
                "depth_ready_family_count": family_count,
                "targeted_family_count": 0,
                "trace_ready_family_count": family_count,
                "mesh_trace_ready_family_count": family_count,
                "runtime_ready_family_count": family_count,
                "omitted_library_family_count": 0,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "contract_pass": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "summary_line": (
                        f"{spec['family_id']}: LOCAL_DEPTH | trace=yes | mesh=yes | runtime=yes"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        local_variant_writeback_trace,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring local variant/writeback trace: PASS | families=8 | deep=8 | targeted=0 | "
                "workspace_variant=8 | solver_variant=8 | writeback_trace=8 | signed=8"
            ),
            "summary": {
                "family_count": family_count,
                "deep_ready_family_count": family_count,
                "targeted_family_count": 0,
                "workspace_variant_ready_family_count": family_count,
                "solver_variant_ready_family_count": family_count,
                "writeback_trace_ready_family_count": family_count,
                "active_multi_family_count": family_count,
                "combo_multi_family_count": family_count,
                "signed_writeback_family_count": family_count,
                "omitted_library_family_count": 0,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "contract_pass": True,
                    "workspace_variant_ready": True,
                    "solver_variant_ready": True,
                    "signature_verified": True,
                    "summary_line": (
                        f"{spec['family_id']}: LOCAL_VARIANT | workspace=yes | solver=yes | trace=yes"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        multi_project_runtime_writeback,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring multi-project runtime/writeback: PASS | projects=8 | families=8 | "
                "project_families=8 | full_depth=8 | ready_projects=8 | signature=8 | repro=8 | "
                "snapshot=8 | queue_clear=8"
            ),
            "summary": {
                "multi_project_runtime_writeback_ready": True,
                "project_count": family_count,
                "family_count": family_count,
                "project_family_count": family_count,
                "full_depth_project_family_count": family_count,
                "targeted_project_family_count": 0,
                "ready_project_count": family_count,
                "signature_verified_project_count": family_count,
                "package_reproducible_project_count": family_count,
                "snapshot_ready_project_count": family_count,
                "queue_clear_project_count": family_count,
            },
            "project_rows": [
                {"project_id": str(spec["project_id"]), "project_ready": True}
                for spec in family_specs
            ],
            "project_family_rows": [
                {
                    "project_id": str(spec["project_id"]),
                    "family_id": str(spec["family_id"]),
                    "full_depth_ready": True,
                }
                for spec in family_specs
            ],
            "artifacts": {
                "native_authoring_multi_project_runtime_writeback_report_json": str(
                    multi_project_runtime_writeback
                ),
            },
        },
    )
    _write_json(
        solver_family_breadth,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring solver family breadth: PASS | families=8 | broad_ready=8 | full_breadth=8 | "
                "solver_ready=8 | combo_broad=8 | mesh_coverage=8 | mesh_broad=8 | member_multi=8 | queue=0"
            ),
            "summary": {
                "family_count": family_count,
                "broad_ready_family_count": family_count,
                "full_breadth_family_count": family_count,
                "solver_ready_family_count": family_count,
                "runtime_ready_family_count": family_count,
                "release_ready_family_count": family_count,
                "combo_broad_family_count": family_count,
                "mesh_coverage_family_count": family_count,
                "mesh_broad_family_count": family_count,
                "member_multi_family_count": family_count,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "solver_ready": True,
                    "runtime_ready": True,
                    "release_ready": True,
                    "signature_verified": True,
                    "solver_combo_count": int(spec["solver_combo_count"]),
                    "solver_mesh_request_count": int(spec["solver_mesh_request_count"]),
                    "member_type_count": len(str(spec["member_type_label"]).split(",")),
                    "member_type_label": str(spec["member_type_label"]),
                    "palette_family_count": int(spec["palette_family_count"]),
                    "active_family_count": int(spec["active_family_count"]),
                    "summary_line": (
                        f"{spec['family_id']}: BROAD | combo=broad:{spec['solver_combo_count']} | "
                        f"mesh=broad:{spec['solver_mesh_request_count']} | active={spec['active_family_count']}"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        writeback_breadth,
        {
            "contract_pass": True,
            "summary_line": (
                "Native authoring writeback breadth: PASS | families=8 | broad_ready=8 | full_breadth=8 | mesh_broad=8"
            ),
            "summary": {
                "family_count": family_count,
                "broad_ready_family_count": family_count,
                "full_breadth_family_count": family_count,
                "mesh_broad_family_count": family_count,
            },
            "family_rows": [
                {
                    "family_id": str(spec["family_id"]),
                    "family_label": str(spec["family_label"]),
                    "runtime_ready": True,
                    "submission_ready": True,
                    "signature_verified": True,
                    "summary_line": (
                        f"{spec['family_id']}: WRITEBACK_BROAD | combo=broad:{spec['solver_combo_count']} | "
                        f"mesh=broad:{spec['solver_mesh_request_count']} | writeback=yes"
                    ),
                    "artifacts": dict(spec["artifacts"]),
                }
                for spec in family_specs
            ],
        },
    )
    _write_json(
        project_ops_service_snapshot,
        {
            "contract_pass": True,
            "summary_line": "Project ops service snapshot: PASS | projects=8 | families=8 | endpoints=10",
            "health": {
                "status": "ok",
            },
            "summary": {
                "service_ready": True,
                "project_count": family_count,
                "family_count": family_count,
                "portfolio_count": 1,
                "submission_count": family_count,
                "ready_submission_count": family_count,
                "writeback_ready_submission_count": family_count,
                "queued_submission_count": 0,
                "batch_job_count": family_count,
                "batch_snapshot_count": family_count,
                "family_batch_report_count": family_count,
                "endpoint_count": 10,
                "ready_family_count": family_count,
                "release_candidate_pass": True,
                "commercial_grade": "ready",
                "latest_release_snapshot": "2026-04-21T00:00:00Z",
                "latest_release_snapshot_generated_at": "2026-04-21T00:00:00Z",
            },
        },
    )
    _write_json(
        ops_bundle,
        {
            "summary_line": "Native authoring ops bundle: PASS | source=loaded | ready=True | solver_combos=13 | jobs=3 | snapshots=3 | package_artifacts=4",
            "contract_pass": True,
            "summary": {
                "model_id": "authoring-tower-a",
                "solver_combo_count": 13,
                "solver_mesh_request_count": 2,
                "solver_load_case_count": 4,
                "solver_loadcomb_line_count": 37,
                "job_count": 3,
                "snapshot_count": 3,
                "registry_approval_count": 3,
            },
            "checks": {
                "project_registry_pass": True,
                "project_registry_signature_verified_pass": True,
            },
            "project_registry_summary": {
                "approved_count": 3,
                "package_bytes": 12345,
            },
            "artifacts": {
                "workspace_summary_json": str(workspace_summary),
                "solver_session_json": str(solver_session),
                "batch_job_report_json": str(batch_job_report),
                "loadcomb_preview_mgt": str(loadcomb_preview),
                "project_registry_json": str(tmp_path / "native_authoring_project_registry.json"),
                "project_package_zip": str(tmp_path / "native_authoring_project_package.zip"),
                "project_registry_public_key": str(tmp_path / "native_authoring_project_registry_ed25519.pub.pem"),
                "project_registry_signature": str(tmp_path / "native_authoring_project_registry.signature.b64"),
            },
        },
    )

    module.DEFAULT_NATIVE_AUTHORING_WORKSPACE_SUMMARY = workspace_summary
    module.DEFAULT_NATIVE_AUTHORING_SOLVER_SESSION = solver_session
    module.DEFAULT_NATIVE_AUTHORING_OPS_BUNDLE = ops_bundle
    module.DEFAULT_NATIVE_AUTHORING_BATCH_JOB_REPORT = batch_job_report
    module.DEFAULT_NATIVE_AUTHORING_LOADCOMB_PREVIEW = loadcomb_preview
    module.DEFAULT_PROJECT_REGISTRY_PORTFOLIO_WORKSPACE = portfolio_workspace
    module.DEFAULT_NATIVE_AUTHORING_OPS_PORTFOLIO = ops_portfolio
    module.DEFAULT_NATIVE_AUTHORING_FAMILY_CORPUS_MANIFEST = family_corpus_manifest
    module.DEFAULT_NATIVE_AUTHORING_RUNTIME_SUBMISSION_LANE = runtime_submission_lane
    module.DEFAULT_NATIVE_AUTHORING_RUNTIME_WRITEBACK_DEPTH_REPORT = runtime_writeback_depth
    module.DEFAULT_NATIVE_AUTHORING_LOCAL_RUNTIME_SCENARIO_DEPTH_REPORT = local_runtime_scenario_depth
    module.DEFAULT_NATIVE_AUTHORING_LOCAL_VARIANT_WRITEBACK_TRACE_REPORT = local_variant_writeback_trace
    module.DEFAULT_NATIVE_AUTHORING_MULTI_PROJECT_RUNTIME_WRITEBACK_REPORT = (
        multi_project_runtime_writeback
    )
    module.DEFAULT_NATIVE_AUTHORING_SOLVER_FAMILY_BREADTH_REPORT = solver_family_breadth
    module.DEFAULT_NATIVE_AUTHORING_WRITEBACK_BREADTH_REPORT = writeback_breadth
    module.DEFAULT_PROJECT_OPS_SERVICE_SNAPSHOT = project_ops_service_snapshot

    evidence = module._native_authoring_solver_ops_evidence()
    parity = module._commercial_parity_summary([], {})
    authoring_dimension = next(
        row
        for row in parity["dimensions"]
        if row["label"] == "authoring / solver replacement"
    )

    assert evidence["available"] is True
    assert evidence["workspace_ready"] is True
    assert evidence["solver_session_ready"] is True
    assert evidence["ops_bundle_ready"] is True
    assert evidence["signature_verified"] is True
    assert evidence["session_id"] == "authoring-session-01"
    assert evidence["combo_count"] == 13
    assert evidence["mesh_request_count"] == 2
    assert evidence["job_count"] == 3
    assert evidence["approval_count"] == 3
    assert evidence["package_bytes"] == 12345
    assert evidence["palette_family_count"] == 4
    assert evidence["active_family_count"] == 2
    assert evidence["portfolio_project_count"] == 8
    assert evidence["portfolio_unmatched_input_count"] == 0
    assert evidence["family_row_count"] == 8
    assert evidence["ready_family_count"] == 8
    assert evidence["native_authoring_runtime_submission_attached"] is True
    assert evidence["native_authoring_runtime_submission_ready"] is True
    assert evidence["native_authoring_runtime_submission_count"] == 8
    assert evidence["native_authoring_runtime_submission_ready_count"] == 8
    assert evidence["native_authoring_runtime_writeback_ready_count"] == 8
    assert evidence["native_authoring_runtime_writeback_depth_attached"] is True
    assert evidence["native_authoring_runtime_writeback_depth_ready"] is True
    assert evidence["native_authoring_runtime_writeback_depth_family_count"] == 8
    assert evidence["native_authoring_runtime_writeback_depth_ready_count"] == 8
    assert evidence["native_authoring_local_runtime_scenario_depth_attached"] is True
    assert evidence["native_authoring_local_runtime_scenario_depth_ready"] is True
    assert evidence["native_authoring_local_runtime_scenario_depth_family_count"] == 8
    assert evidence["native_authoring_local_runtime_scenario_depth_ready_count"] == 8
    assert evidence["native_authoring_local_variant_writeback_trace_attached"] is True
    assert evidence["native_authoring_local_variant_writeback_trace_ready"] is True
    assert evidence["native_authoring_local_variant_writeback_trace_family_count"] == 8
    assert evidence["native_authoring_local_variant_writeback_trace_ready_count"] == 8
    assert evidence["native_authoring_multi_project_runtime_writeback_attached"] is True
    assert evidence["native_authoring_multi_project_runtime_writeback_ready"] is True
    assert evidence["native_authoring_multi_project_runtime_writeback_project_count"] == 8
    assert evidence["native_authoring_multi_project_runtime_writeback_project_family_count"] == 8
    assert evidence["native_authoring_solver_family_breadth_attached"] is True
    assert evidence["native_authoring_solver_family_breadth_ready"] is True
    assert evidence["native_authoring_solver_family_breadth_family_count"] == 8
    assert evidence["native_authoring_solver_family_breadth_ready_count"] == 8
    assert evidence["native_authoring_writeback_breadth_attached"] is True
    assert evidence["native_authoring_writeback_breadth_ready"] is True
    assert evidence["native_authoring_writeback_breadth_family_count"] == 8
    assert evidence["native_authoring_writeback_breadth_ready_count"] == 8
    assert evidence["family_corpus_attached"] is True
    assert evidence["family_corpus_ready"] is True
    assert evidence["family_corpus_family_count"] == 8
    assert evidence["family_corpus_public_reference_count"] == 24
    assert evidence["project_ops_service_attached"] is True
    assert evidence["project_ops_service_ready"] is True
    assert evidence["project_ops_service_project_count"] == 8
    assert evidence["project_ops_service_family_count"] == 8
    assert evidence["project_ops_service_endpoint_count"] == 10
    family_rows_by_id = {
        str(row["family_id"]): row
        for row in evidence["family_rows"]
    }
    assert family_rows_by_id["rc_wall_core"]["family_label"] == "RC Wall Core"
    assert family_rows_by_id["sample_tower"]["family_label"] == "Sample Tower"
    assert family_rows_by_id["sample_tower"]["ready"] is True
    assert family_rows_by_id["steel_braced_frame"]["ready"] is True
    assert evidence["artifact_paths"]["ops_bundle_json"] == str(ops_bundle)
    assert evidence["artifact_paths"]["solver_session_json"] == str(solver_session)
    assert evidence["artifact_paths"]["loadcomb_preview_mgt"] == str(loadcomb_preview)
    assert evidence["artifact_paths"]["portfolio_workspace_json"] == str(portfolio_workspace)
    assert evidence["artifact_paths"]["ops_portfolio_json"] == str(ops_portfolio)
    assert evidence["artifact_paths"]["native_authoring_family_corpus_manifest_json"].endswith(
        "native_authoring_family_corpus_manifest.json"
    )
    assert evidence["artifact_paths"]["native_authoring_runtime_submission_lane_json"].endswith(
        "native_authoring_runtime_submission_lane.json"
    )
    assert evidence["artifact_paths"]["native_authoring_runtime_writeback_depth_report_json"].endswith(
        "native_authoring_runtime_writeback_depth_report.json"
    )
    assert evidence["artifact_paths"]["native_authoring_local_runtime_scenario_depth_report_json"].endswith(
        "native_authoring_local_runtime_scenario_depth_report.json"
    )
    assert evidence["artifact_paths"]["native_authoring_local_variant_writeback_trace_report_json"].endswith(
        "native_authoring_local_variant_writeback_trace_report.json"
    )
    assert evidence["artifact_paths"]["native_authoring_multi_project_runtime_writeback_report_json"].endswith(
        "native_authoring_multi_project_runtime_writeback_report.json"
    )
    assert evidence["artifact_paths"]["native_authoring_solver_family_breadth_report_json"].endswith(
        "native_authoring_solver_family_breadth_report.json"
    )
    assert evidence["artifact_paths"]["native_authoring_writeback_breadth_report_json"].endswith(
        "native_authoring_writeback_breadth_report.json"
    )
    assert evidence["artifact_paths"]["project_ops_service_snapshot_json"].endswith(
        "project_ops_service_snapshot.json"
    )
    assert evidence["native_authoring_runtime_submission_summary_line"].startswith(
        "Native authoring runtime submission lane: PASS"
    )
    assert "Project ops service snapshot: PASS" in evidence["project_ops_service_summary_line"]
    assert "session=authoring-session-01" in evidence["parity_note"]
    assert "palette_families=4" in evidence["parity_note"]
    assert "family_rows=8" in evidence["parity_note"]
    assert "ready_families=8" in evidence["parity_note"]
    assert "portfolio_projects=8" in evidence["parity_note"]
    assert "family_corpus=PASS" in evidence["parity_note"]
    assert "corpus_refs=24" in evidence["parity_note"]
    assert "runtime_submission=PASS" in evidence["parity_note"]
    assert "runtime_writeback_depth=PASS" in evidence["parity_note"]
    assert "local_runtime_depth=PASS" in evidence["parity_note"]
    assert "local_variant_trace=PASS" in evidence["parity_note"]
    assert "multi_project_runtime=PASS" in evidence["parity_note"]
    assert "solver_family_breadth=PASS" in evidence["parity_note"]
    assert "writeback_breadth=PASS" in evidence["parity_note"]
    assert "ops_service=PASS" in evidence["parity_note"]
    assert parity["native_authoring_evidence"]["session_id"] == "authoring-session-01"
    assert authoring_dimension["score"] > 40
    assert "ops_bundle=PASS" in authoring_dimension["note"]
    assert "ops_service=PASS" in authoring_dimension["note"]
    assert "signed_registry=yes" in authoring_dimension["note"]


def test_native_authoring_server_ops_summary_and_family_track_breadth_reflect_compact_evidence(
    tmp_path: Path,
) -> None:
    module = _load_viewer_module()
    family_specs = _native_authoring_family_specs(tmp_path)
    family_rows = [
        {
            "family_id": str(spec["family_id"]),
            "family_label": str(spec["family_label"]),
            "ready": True,
            "status_label": "ready",
            "readiness_summary": (
                f"combos={spec['solver_combo_count']} | mesh_requests={spec['solver_mesh_request_count']} | "
                "registries=1/1 | signature=1"
            ),
            "scope_summary": (
                f"drafts={spec['draft_label']} | member_types={spec['member_type_label']} | "
                f"members={spec['member_count']} | loads={spec['load_pattern_count']}"
            ),
            "summary_line": (
                f"Native authoring ops bundle: PASS | family={spec['family_id']} | source=generated | ready=True | "
                f"solver_combos={spec['solver_combo_count']} | jobs={spec['job_count']} | "
                f"snapshots={spec['snapshot_count']} | package_artifacts=4"
            ),
            "project_name": str(spec["project_name"]),
            "project_count": 1,
            "draft_labels": [str(spec["draft_label"])],
            "primary_href": f"{spec['family_id']}.json",
            "secondary_href": f"{spec['family_id']}_solver_session.json",
            "tertiary_href": f"{spec['family_id']}_loadcomb_preview.mgt",
        }
        for spec in family_specs
    ]
    evidence = {
        "available": True,
        "workspace_ready": True,
        "solver_session_ready": True,
        "runtime_authoring_ready": True,
        "ops_bundle_ready": True,
        "registry_ready": True,
        "signature_verified": True,
        "session_id": "authoring-session-01",
        "model_id": "authoring-tower-a",
        "family": "KDS-2022",
        "combo_count": 13,
        "mesh_request_count": 2,
        "load_case_count": 4,
        "loadcomb_line_count": 37,
        "job_count": 3,
        "snapshot_count": 3,
        "approval_count": 3,
        "portfolio_attached": True,
        "portfolio_project_count": 8,
        "portfolio_complete_count": 8,
        "portfolio_signature_count": 8,
        "portfolio_repro_count": 8,
        "portfolio_unmatched_input_count": 0,
        "palette_family_count": 4,
        "palette_family_label": "Composite, Steel, RC, CFT",
        "active_family_count": 4,
        "active_family_label": "Beam, Brace, Column, Wall",
        "member_type_count": 4,
        "member_type_label": "Beam, Brace, Column, Wall",
        "family_row_count": 8,
        "ready_family_count": 8,
        "family_rows": family_rows,
        "workspace_summary_line": "Native authoring bundle: PASS | stories=5 | nodes=24 | members=35 | loads=4 | unsupported=0 | unresolved=0 | score=100.0",
        "solver_session_summary_line": "Native authoring solver session: PASS | meshes=2 | cells=588 | combos=13 | family=KDS-2022",
        "runtime_summary_line": "Runtime load-combination authoring: PASS | combos=13 | linear=13 | nested=0 | max_depth=1 | cases=4 | unresolved=0",
        "ops_bundle_summary_line": "Native authoring ops bundle: PASS | source=loaded | ready=True | solver_combos=13 | jobs=3 | snapshots=3 | package_artifacts=4",
        "batch_job_summary_line": "Batch job runner: PASS | jobs=3 | snapshots=3 | reruns=0 | statuses=completed=3",
        "portfolio_summary_line": "Project registry portfolio workspace: PASS | projects=8 | unique=8 | complete=8 | signature=8 | repro=8",
        "artifact_paths": {
            "ops_bundle_json": "native_authoring_ops_bundle.json",
            "solver_session_json": "native_authoring_solver_session.json",
            "batch_job_report_json": "native_authoring_batch_job_report.json",
            "portfolio_workspace_json": "project_registry_portfolio_workspace.json",
            "ops_portfolio_json": "native_authoring_ops_portfolio.json",
        },
        "strongest_local_evidence": [
            "native_authoring_ops_bundle.json",
            "native_authoring_solver_session.json",
            "native_authoring_batch_job_report.json",
        ],
        "parity_note": "Scoped native authoring evidence is now present.",
    }

    server_ops = module._native_authoring_server_ops_summary(evidence)
    family_breadth = module._native_authoring_family_track_commercialization_breadth(evidence)

    assert server_ops["available"] is True
    assert server_ops["label"] == "Server-Style Ops Summary"
    assert server_ops["count"] == 3
    assert server_ops["ready_count"] == 3
    assert server_ops["open_count"] == 0
    assert server_ops["headline"] == "session=authoring-session-01 | model=authoring-tower-a | combos=13 | jobs=3 | families=8/8"
    assert server_ops["rows"][0]["label"] == "Workspace / runtime"
    assert server_ops["rows"][1]["label"] == "Solver session / ops bundle"
    assert server_ops["rows"][2]["label"] == "Family-track breadth"
    assert "workspace=PASS" in server_ops["summary_line"]
    assert "ops_bundle=PASS" in server_ops["summary_line"]
    assert "portfolio=PASS" in server_ops["summary_line"]
    assert server_ops["artifact_paths"]["ops_bundle_json"] == "native_authoring_ops_bundle.json"
    assert server_ops["strongest_local_evidence"][0] == "native_authoring_ops_bundle.json"

    assert family_breadth["available"] is True
    assert family_breadth["label"] == "Family-Track Commercialization Breadth"
    assert family_breadth["count"] == 8
    assert family_breadth["ready_count"] == 8
    assert family_breadth["open_count"] == 0
    assert family_breadth["headline"] == "ready 8/8 | palette 4 | active 4 | portfolio 8/8"
    family_breadth_rows = {str(row["family_id"]): row for row in family_breadth["rows"]}
    assert family_breadth_rows["belt_truss_mega_frame"]["family_label"] == "Belt-Truss Mega Frame"
    assert family_breadth_rows["sample_tower"]["status"] == "READY"
    assert family_breadth_rows["sample_tower"]["project_name"] == "Native Authoring Sample Tower"
    assert "palette=Composite, Steel, RC, CFT" in family_breadth["summary_line"]
    assert "families=8" in family_breadth["summary_line"]
    assert "ready_families=8" in family_breadth["summary_line"]


def test_native_authoring_runtime_submission_lane_surface_renders_when_evidence_fields_are_present() -> None:
    module = _load_viewer_module()
    evidence = {
        "available": True,
        "native_authoring_runtime_submission_attached": False,
        "native_authoring_runtime_submission_ready": False,
        "native_authoring_runtime_submission_summary_line": (
            "Runtime submission lane: CHECK | submissions=8 | ready=6 | writeback=8 | queue=0"
        ),
        "native_authoring_runtime_submission_count": 8,
        "native_authoring_runtime_submission_ready_count": 6,
        "native_authoring_runtime_writeback_ready_count": 8,
        "native_authoring_runtime_submission_queue_count": 0,
        "native_authoring_runtime_submission_status_label": "native_authoring_runtime_submission_lane_partial",
        "native_authoring_runtime_writeback_depth_attached": True,
        "native_authoring_runtime_writeback_depth_ready": False,
        "native_authoring_runtime_writeback_depth_summary_line": (
            "Native authoring runtime writeback depth: CHECK | families=8 | full_depth=6 | targeted=2 | "
            "registry=8 | signature=8 | repro=6 | snapshot=8 | queue_clear=6"
        ),
        "native_authoring_runtime_writeback_depth_family_count": 8,
        "native_authoring_runtime_writeback_depth_ready_count": 6,
        "native_authoring_runtime_writeback_depth_targeted_count": 2,
        "native_authoring_runtime_writeback_depth_signature_count": 8,
        "native_authoring_runtime_writeback_depth_repro_count": 6,
        "native_authoring_runtime_writeback_depth_snapshot_count": 8,
        "native_authoring_runtime_writeback_depth_queue_clear_count": 6,
        "native_authoring_local_runtime_scenario_depth_attached": True,
        "native_authoring_local_runtime_scenario_depth_ready": False,
        "native_authoring_local_runtime_scenario_depth_summary_line": (
            "Native authoring local runtime scenario depth: CHECK | families=8 | deep=6 | targeted=2 | trace_ready=8 | mesh_ready=6 | runtime_ready=8 | omitted=2"
        ),
        "native_authoring_local_runtime_scenario_depth_family_count": 8,
        "native_authoring_local_runtime_scenario_depth_ready_count": 6,
        "native_authoring_local_runtime_scenario_depth_targeted_count": 2,
        "native_authoring_local_runtime_scenario_depth_trace_ready_count": 8,
        "native_authoring_local_runtime_scenario_depth_mesh_ready_count": 6,
        "native_authoring_local_runtime_scenario_depth_runtime_ready_count": 8,
        "native_authoring_local_runtime_scenario_depth_omitted_count": 2,
        "native_authoring_local_variant_writeback_trace_attached": True,
        "native_authoring_local_variant_writeback_trace_ready": False,
        "native_authoring_local_variant_writeback_trace_summary_line": (
            "Native authoring local variant/writeback trace: CHECK | families=8 | deep=6 | targeted=2 | "
            "workspace_variant=8 | solver_variant=6 | writeback_trace=6 | signed=8"
        ),
        "native_authoring_local_variant_writeback_trace_family_count": 8,
        "native_authoring_local_variant_writeback_trace_ready_count": 6,
        "native_authoring_local_variant_writeback_trace_targeted_count": 2,
        "native_authoring_local_variant_workspace_variant_ready_count": 8,
        "native_authoring_local_variant_solver_variant_ready_count": 6,
        "native_authoring_local_variant_writeback_trace_ready_family_trace_count": 6,
        "native_authoring_local_variant_signed_writeback_family_count": 8,
        "native_authoring_multi_project_runtime_writeback_attached": True,
        "native_authoring_multi_project_runtime_writeback_ready": False,
        "native_authoring_multi_project_runtime_writeback_summary_line": (
            "Native authoring multi-project runtime/writeback: CHECK | projects=8 | families=8 | "
            "project_families=8 | full_depth=6 | ready_projects=6 | signature=8 | repro=6 | snapshot=8 | queue_clear=6"
        ),
        "native_authoring_multi_project_runtime_writeback_project_count": 8,
        "native_authoring_multi_project_runtime_writeback_project_family_count": 8,
        "native_authoring_multi_project_runtime_writeback_full_count": 6,
        "native_authoring_multi_project_runtime_writeback_ready_project_count": 6,
        "native_authoring_multi_project_runtime_writeback_signature_project_count": 8,
        "native_authoring_multi_project_runtime_writeback_repro_project_count": 6,
        "native_authoring_multi_project_runtime_writeback_snapshot_project_count": 8,
        "native_authoring_multi_project_runtime_writeback_queue_clear_project_count": 6,
        "native_authoring_solver_family_breadth_attached": True,
        "native_authoring_solver_family_breadth_ready": False,
        "native_authoring_solver_family_breadth_summary_line": (
            "Native authoring solver family breadth: CHECK | families=8 | broad_ready=6 | "
            "full_breadth=4 | solver_ready=8 | combo_broad=8 | mesh_coverage=6 | mesh_broad=6 | "
            "member_multi=8 | queue=0"
        ),
        "native_authoring_solver_family_breadth_family_count": 8,
        "native_authoring_solver_family_breadth_ready_count": 6,
        "native_authoring_solver_family_breadth_full_count": 4,
        "native_authoring_solver_family_breadth_mesh_broad_count": 6,
        "native_authoring_solver_family_breadth_member_multi_count": 8,
        "native_authoring_writeback_breadth_attached": True,
        "native_authoring_writeback_breadth_ready": False,
        "native_authoring_writeback_breadth_summary_line": (
            "Native authoring writeback breadth: CHECK | families=8 | broad_ready=6 | full_breadth=4 | mesh_broad=6"
        ),
        "native_authoring_writeback_breadth_family_count": 8,
        "native_authoring_writeback_breadth_ready_count": 6,
        "native_authoring_writeback_breadth_full_count": 4,
        "native_authoring_writeback_breadth_mesh_broad_count": 6,
        "portfolio_attached": True,
        "portfolio_project_count": 8,
        "portfolio_complete_count": 8,
        "portfolio_signature_count": 8,
        "portfolio_repro_count": 6,
        "portfolio_unmatched_input_count": 0,
        "ready_family_count": 6,
        "family_row_count": 8,
        "portfolio_summary_line": "Project registry portfolio workspace: PASS | projects=8 | unique=8 | complete=8 | signature=8 | repro=6",
        "project_ops_service_attached": False,
        "project_ops_service_ready": False,
        "project_ops_service_summary_line": "Project Ops Service: CHECK | projects=6 | families=8 | endpoints=10",
        "project_ops_service_project_count": 6,
        "project_ops_service_family_count": 8,
        "project_ops_service_endpoint_count": 10,
        "project_ops_service_portfolio_count": 1,
        "project_ops_service_submission_count": 8,
        "project_ops_service_ready_submission_count": 6,
        "project_ops_service_writeback_ready_submission_count": 8,
        "project_ops_service_queued_submission_count": 0,
        "artifact_paths": {
            "native_authoring_runtime_submission_lane_json": "native_authoring_runtime_submission_lane.json",
            "native_authoring_runtime_writeback_depth_report_json": "native_authoring_runtime_writeback_depth_report.json",
            "native_authoring_local_runtime_scenario_depth_report_json": "native_authoring_local_runtime_scenario_depth_report.json",
            "native_authoring_local_variant_writeback_trace_report_json": "native_authoring_local_variant_writeback_trace_report.json",
            "native_authoring_multi_project_runtime_writeback_report_json": "native_authoring_multi_project_runtime_writeback_report.json",
            "native_authoring_solver_family_breadth_report_json": "native_authoring_solver_family_breadth_report.json",
            "native_authoring_writeback_breadth_report_json": "native_authoring_writeback_breadth_report.json",
            "project_ops_service_snapshot_json": "project_ops_service_snapshot.json",
        },
        "strongest_local_evidence": [],
    }

    surface = module._native_authoring_runtime_submission_lane_surface(evidence)

    assert surface["available"] is True
    assert surface["label"] == "Runtime Submission Lane"
    assert surface["count"] == 10
    assert surface["ready_count"] == 1
    assert surface["open_count"] == 9
    assert surface["status_label"] == "native_authoring_runtime_submission_lane_partial"
    assert [row["label"] for row in surface["rows"]] == [
        "Runtime submission lane",
        "Writeback / registry",
        "Project Ops Service",
        "Portfolio / family / runtime / service alignment",
        "Runtime writeback depth",
        "Multi-project runtime/writeback",
        "Solver family breadth",
        "Local runtime scenario depth",
        "Local variant/writeback trace",
        "Broader native writeback coverage",
    ]
    assert surface["rows"][0]["status"] == "CHECK"
    assert surface["rows"][1]["status"] == "PASS"
    assert surface["rows"][2]["status"] == "CHECK"
    assert surface["rows"][3]["status"] == "CHECK"
    assert surface["rows"][4]["status"] == "CHECK"
    assert surface["rows"][5]["status"] == "CHECK"
    assert surface["rows"][6]["status"] == "CHECK"
    assert surface["rows"][7]["status"] == "CHECK"
    assert surface["rows"][8]["status"] == "CHECK"
    assert surface["rows"][9]["status"] == "CHECK"
    assert surface["portfolio_status_label"] == "PASS"
    assert surface["alignment_status_label"] == "CHECK"
    assert surface["summary_line"] == (
        "runtime=CHECK | writeback=PASS | runtime_writeback_depth=CHECK | local_runtime_depth=CHECK | local_variant_trace=CHECK | multi_project_runtime=CHECK | solver_family_breadth=CHECK | writeback_breadth=CHECK | "
        "project_ops_service=CHECK | alignment=CHECK"
    )
    assert surface["alignment_summary_line"] == (
        "alignment=CHECK | portfolio=PASS | families=6/8 | runtime=CHECK | service=CHECK"
    )
    assert surface["runtime_artifact_names"] == (
        "native_authoring_runtime_submission_lane.json, native_authoring_runtime_writeback_depth_report.json, native_authoring_local_runtime_scenario_depth_report.json, native_authoring_local_variant_writeback_trace_report.json, native_authoring_multi_project_runtime_writeback_report.json, native_authoring_solver_family_breadth_report.json, "
        "native_authoring_writeback_breadth_report.json, project_ops_service_snapshot.json"
    )
    assert surface["strongest_local_evidence"] == [
        "native_authoring_runtime_submission_lane.json",
        "native_authoring_runtime_writeback_depth_report.json",
        "native_authoring_local_runtime_scenario_depth_report.json",
        "native_authoring_local_variant_writeback_trace_report.json",
        "native_authoring_multi_project_runtime_writeback_report.json",
        "native_authoring_solver_family_breadth_report.json",
        "native_authoring_writeback_breadth_report.json",
        "project_ops_service_snapshot.json",
    ]


def test_commercialization_depth_surface_tracks_p0_p1_release_gap_summary() -> None:
    module = _load_viewer_module()
    release_gap_payload = {
        "summary": {
            "material_constitutive_summary_line": (
                "Material constitutive gate: PASS | concrete_damage=yes(matrix=48/48,max=1.000) | "
                "cyclic_degradation=yes(matrix=46/46,residual_max=1.914%) | bond_interface=yes(matrix=48/48,bond_max=0.980)"
            ),
            "element_material_breadth_summary_line": (
                "Element/material breadth: PASS | panel_cyclic=yes(sections=2,pinch=0.18,crush=1.00) | "
                "assembled_depth=yes(beam_iter=2,tangent=0.05,panel=2,torsion=1) | materials=2(rc_composite,steel_elastic_plastic)"
            ),
            "load_combination_engine_pass": True,
            "load_combination_engine_summary_line": (
                "Load-combination engine gate: PASS | models=3 | exact_roundtrip=3/3 | "
                "kds_strength_avg=1.000 min=1.000 | cases=4"
            ),
            "midas_loadcomb_roundtrip_summary_line": (
                "MIDAS loadcomb-roundtrip: ok | entry_row_coverage=midas_generator_33.json=1.00 | artifacts=3"
            ),
            "reference_regression_pass": True,
            "reference_regression_summary_line": (
                "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0"
            ),
            "reference_regression_report_path": (
                "implementation/phase1/release/reference_regression/reference_regression_report.json"
            ),
            "advanced_ssi_pass": True,
            "advanced_ssi_summary_line": (
                "Advanced SSI: PASS | layers=3 | groups=2 | peak_transfer=PILE_PERIM@2.49Hz x2.66 | "
                "detune=MAT_CORE:3.18 | group_eff=PILE_PERIM:0.47"
            ),
            "foundation_soil_link_summary_line": (
                "Foundation/soil link: PASS | foundation_members=76 | optimized_groups=2 | "
                "ssi=yes | soil_tunnel=yes | impedance_schema=yes | links=6(...)"
            ),
            "general_fe_contact_matrix_summary_line": (
                "General FE contact matrix: PASS | ready=10/10 | ssi=yes | soil_tunnel=yes | support_depth=21 | coupling_depth=31"
            ),
            "wind_workflow_pass": True,
            "wind_workflow_summary_line": (
                "Wind workflow: PASS | exposure=C | stories=6 | accel=10.3/24.0mg | comfort=acceptable | cases=8"
            ),
            "wind_tunnel_raw_mapping_ready": False,
            "wind_tunnel_mapping_mode": "semantic_pressure_binding_only",
            "wind_tunnel_mapping_reason": "Raw wind-tunnel mapping artifact still needs direct bound rows.",
        }
    }

    surface = module._commercialization_depth_surface(release_gap_payload)
    parity = module._commercial_parity_summary([], {}, release_gap_payload)

    assert surface["available"] is True
    assert surface["count"] == 5
    assert surface["ready_count"] == 5
    assert surface["open_count"] == 0
    assert surface["p0_total_count"] == 3
    assert surface["p0_ready_count"] == 3
    assert surface["p1_total_count"] == 2
    assert surface["p1_ready_count"] == 2
    assert surface["headline"] == "P0 3/3 | P1 2/2 | total 5/5"
    assert [row["id"] for row in surface["rows"]] == [
        "material_depth",
        "load_depth",
        "reference_regression",
        "advanced_ssi_depth",
        "wind_depth",
    ]
    assert surface["rows"][0]["status"] == "PASS"
    assert surface["rows"][1]["status"] == "PASS"
    assert surface["rows"][2]["status"] == "PASS"
    assert surface["rows"][3]["status"] == "PASS"
    assert surface["rows"][4]["status"] == "PASS"
    assert "concrete_damage=yes" in surface["rows"][0]["summary_excerpt"]
    assert "exact_roundtrip=3/3" in surface["rows"][1]["summary_excerpt"]
    assert "cases=8/8" in surface["rows"][2]["summary_excerpt"]
    assert "peak_transfer=PILE_PERIM@2.49Hz x2.66" in surface["rows"][3]["summary_excerpt"]
    assert "comfort=acceptable" in surface["rows"][4]["summary_excerpt"]
    assert parity["commercialization_depth_surface"]["ready_count"] == 5
    assert parity["commercialization_depth_surface"]["rows"][4]["label"] == "Wind / raw mapping depth"


def test_commercial_workflow_breadth_surface_tracks_open_commercialization_areas() -> None:
    module = _load_viewer_module()
    report_payload = {
        "summary_line": (
            "Commercial workflow breadth: CHECK | construction_stage=yes(history_snapshots=7,max_shortening=4.250mm) | "
            "rail_tunnel=yes(serviceability=monitor,maintenance=high,actions=3) | "
            "design_redesign_loop=no(traceability=0.875,ng_members=4,suggestions=5)"
        ),
        "checks": {"pass": False},
        "summary": {
            "construction_stage_ready": True,
            "construction_stage_history_snapshot_count": 7,
            "construction_stage_max_differential_shortening_mm": 4.25,
            "rail_tunnel_ready": True,
            "rail_tunnel_serviceability_status": "monitor",
            "rail_tunnel_maintenance_priority": "high",
            "rail_tunnel_recommended_action_count": 3,
            "design_redesign_loop_ready": False,
            "design_report_traceability_ratio": 0.875,
            "design_report_ng_member_count": 4,
            "section_optimizer_suggestion_count": 5,
            "section_optimizer_strengthen_count": 3,
            "section_optimizer_reduce_count": 2,
            "governing_clause_count": 6,
        },
    }

    surface = module._commercial_workflow_breadth_surface(
        report_payload,
        artifact_href="commercial_workflow_breadth_report.json",
        artifact_path="implementation/phase1/release/commercial_workflow_breadth_report.json",
    )

    assert surface["available"] is True
    assert surface["label"] == "Commercial Workflow Breadth"
    assert surface["ready_count"] == 2
    assert surface["open_count"] == 1
    assert surface["checks_pass"] is False
    assert surface["headline"] == "ready 2/3 | checks=CHECK | clauses=6"
    assert surface["artifact_name"] == "commercial_workflow_breadth_report.json"
    assert surface["traceability_summary_label"] == (
        "checks=CHECK | construction_snapshots=7 | rail_actions=3 | design_traceability=87.5%"
    )
    assert [row["label"] for row in surface["rows"]] == [
        "Construction-stage breadth",
        "Rail / tunnel serviceability",
        "Design redesign loop breadth",
    ]
    assert surface["rows"][0]["summary_excerpt"] == "history snapshots=7 | max shortening=4.250 mm"
    assert surface["rows"][1]["summary_excerpt"] == "serviceability=monitor | maintenance=high"
    assert surface["rows"][2]["status"] == "CHECK"
    assert "strengthen=3" in surface["rows"][2]["evidence_excerpt"]


def test_case_catalog_markup_includes_runtime_submission_lane_surface_when_native_authoring_evidence_is_present() -> None:
    module = _load_viewer_module()
    evidence = {
        "available": True,
        "native_authoring_runtime_submission_attached": False,
        "native_authoring_runtime_submission_ready": False,
        "native_authoring_runtime_submission_summary_line": (
            "Runtime submission lane: CHECK | submissions=2 | ready=1 | writeback=2 | queue=0"
        ),
        "native_authoring_runtime_submission_count": 2,
        "native_authoring_runtime_submission_ready_count": 1,
        "native_authoring_runtime_writeback_ready_count": 2,
        "native_authoring_runtime_submission_queue_count": 0,
        "native_authoring_runtime_submission_status_label": "native_authoring_runtime_submission_lane_partial",
        "portfolio_attached": True,
        "portfolio_project_count": 2,
        "portfolio_complete_count": 1,
        "portfolio_signature_count": 1,
        "portfolio_repro_count": 1,
        "portfolio_unmatched_input_count": 1,
        "ready_family_count": 1,
        "family_row_count": 2,
        "portfolio_summary_line": "Project registry portfolio workspace: PASS | projects=2 | unique=2 | complete=1 | signature=1 | repro=1",
        "project_ops_service_attached": False,
        "project_ops_service_ready": False,
        "project_ops_service_summary_line": "Project Ops Service: CHECK | projects=1 | families=1 | endpoints=2",
        "project_ops_service_project_count": 1,
        "project_ops_service_family_count": 1,
        "project_ops_service_endpoint_count": 2,
        "project_ops_service_portfolio_count": 1,
        "project_ops_service_submission_count": 2,
        "project_ops_service_ready_submission_count": 2,
        "project_ops_service_writeback_ready_submission_count": 2,
        "project_ops_service_queued_submission_count": 0,
        "artifact_paths": {
            "native_authoring_runtime_submission_lane_json": "native_authoring_runtime_submission_lane.json",
            "project_ops_service_snapshot_json": "project_ops_service_snapshot.json",
        },
        "strongest_local_evidence": [],
    }

    module._native_authoring_solver_ops_evidence = lambda: evidence
    case_catalog = [
        {
            "entry_id": "demo_case",
            "title": "Demo Case",
            "href": "demo_case.html",
            "catalog_group": "Demo",
            "catalog_primary": "other",
            "catalog_visibility": "featured",
            "status_label": "demo",
            "is_current": True,
        }
    ]
    summary = {
        "featured_entry_count": 1,
        "secondary_entry_count": 0,
        "deep_artifact_count": 0,
        "viewable_3d_count": 0,
        "verified_preview_count": 0,
        "crosscheck_available_count": 0,
        "upgrade_candidate_count": 0,
        "registered_catalog_count": 1,
    }

    markup = module._case_catalog_markup(case_catalog, summary)

    assert "Runtime Submission Lane" in markup
    assert "Writeback / registry" in markup
    assert "Project Ops Service" in markup
    assert "Portfolio / family / runtime / service alignment" in markup
    assert "native_authoring_runtime_submission_lane.json" in markup
    assert "project_ops_service_snapshot.json" in markup
    assert "runtime=CHECK" in markup
    assert "alignment=CHECK" in markup


def test_generate_structural_optimization_visualization_viewer(tmp_path: Path) -> None:
    release_gap = tmp_path / "release_gap_report.json"
    commercial_workflow_breadth_report = tmp_path / "commercial_workflow_breadth_report.json"
    export_report = tmp_path / "export_report.json"
    change_summary = tmp_path / "change_summary.json"
    execution_manifest = tmp_path / "execution_manifest.json"
    execution_status = tmp_path / "execution_status.json"
    committee_package = tmp_path / "committee_package_report.json"
    changes_report = tmp_path / "changes.json"
    dataset_npz = tmp_path / "dataset.npz"
    model_json = tmp_path / "model.json"
    out_dir = tmp_path / "viewer"
    png = tmp_path / "drift.png"
    hysteresis_png = tmp_path / "core_wall_hysteresis.png"
    pbd_package = tmp_path / "pbd_review_package_report.json"
    png.write_bytes(b"")
    hysteresis_png.write_bytes(b"")

    _write_json(
        commercial_workflow_breadth_report,
        {
            "summary_line": (
                "Commercial workflow breadth: CHECK | construction_stage=yes(history_snapshots=9,max_shortening=3.200mm) | "
                "rail_tunnel=yes(serviceability=monitor,maintenance=planned,actions=4) | "
                "design_redesign_loop=no(traceability=0.875,ng_members=5,suggestions=7)"
            ),
            "checks": {"pass": False},
            "summary": {
                "construction_stage_ready": True,
                "construction_stage_history_snapshot_count": 9,
                "construction_stage_max_differential_shortening_mm": 3.2,
                "rail_tunnel_ready": True,
                "rail_tunnel_serviceability_status": "monitor",
                "rail_tunnel_maintenance_priority": "planned",
                "rail_tunnel_recommended_action_count": 4,
                "design_redesign_loop_ready": False,
                "design_report_traceability_ratio": 0.875,
                "design_report_ng_member_count": 5,
                "section_optimizer_suggestion_count": 7,
                "section_optimizer_strengthen_count": 4,
                "section_optimizer_reduce_count": 3,
                "governing_clause_count": 9,
            },
        },
    )
    _write_json(
        release_gap,
        {
            "summary": {
                "commercial_grade": "Commercial",
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "measured_chain_total_minutes": 5.4,
                "measured_chain_selected_step_count": 19,
                "project_registry_package_bytes": 4096,
                "project_registry_approval_count": 2,
                "project_registry_signature_verified": True,
                "external_benchmark_batch_job_count": 4,
                "external_benchmark_batch_completed_count": 2,
                "external_benchmark_batch_failed_count": 0,
                "external_benchmark_batch_rerun_count": 1,
                "external_benchmark_batch_job_summary_line": "Batch job runner: PASS | jobs=4 | completed=2 | failed=0 | reruns=1 | snapshots=3",
                "mgt_export_delivery_boundary": "direct_patch=beam=1 | sidecar=n/a",
                "solver_breadth_summary_line": "Solver breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=2,cases=14,material=rc_composite) | interface=yes(ssi_nonlinear_boundary) | contact=full_structural_contact | general_fe_contact=yes(10/10)",
                "material_constitutive_summary_line": "Material constitutive gate: PASS | concrete_damage=yes(matrix=48/48,max=1.000) | cyclic_degradation=yes(matrix=46/46,residual_max=1.914%) | bond_interface=yes(matrix=48/48,bond_max=0.980) | wind_dynamic_response=yes(matrix=16/16,topo=4) | raw_pressure_field_mapping=yes(matrix=5/5,mapped=7278)",
                "load_combination_engine_pass": True,
                "load_combination_engine_summary_line": "Load-combination engine gate: PASS | models=3 | family=KDS-2022-steel-gravity | runtime_combo_range=8-8 | exact_roundtrip=3/3 | kds_strength_avg=1.000 min=1.000 | cases=4",
                "reference_regression_pass": True,
                "reference_regression_summary_line": "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0",
                "reference_regression_report_path": "implementation/phase1/release/reference_regression/reference_regression_report.json",
                "structural_contact_summary_line": "Structural contact readiness: PASS | impl=6/6 | validated=6/6 | ready=6/6",
                "general_fe_contact_matrix_summary_line": "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21 | coupling_depth=31",
                "foundation_soil_link_summary_line": "Foundation/soil link: PASS | foundation_members=76 | optimized_groups=2 | ssi=yes | soil_tunnel=yes | impedance_schema=yes | links=6(...)",
                "midas_kds_geometry_bridge_summary_line": "MIDAS kds-geometry-bridge: ok | mapped_review_ids=12/12 | exact=12 | heuristic=0 | rows=1056 | row_provenance=1056/1056",
                "pbd_dynamic_hinge_refresh_ready": True,
                "panel_zone_3d_clash_ready": True,
                "foundation_optimization_ready": True,
                "wind_tunnel_raw_mapping_ready": True,
                "wind_tunnel_mapping_mode": "raw_hffb_node_pressure_mapping",
                "wind_tunnel_mapping_reason": "Raw wind-tunnel HFFB mapping is ready for traceable MIDAS binding.",
                "panel_zone_constructability_mode": "internal_engine_complete",
                "panel_zone_validation_boundary": "external_validation_only",
                "panel_zone_internal_engine_complete": True,
                "panel_zone_external_validation_pending": True,
                "panel_zone_external_validation_advisory_only": True,
                "panel_zone_external_validation_release_blocking": False,
                "panel_zone_external_validation_status_label": "advisory_only_boundary",
            },
            "advanced_holdouts": [
                {
                    "id": "pbd_dynamic_hinge_refresh",
                    "severity": "P0",
                    "title": "Dynamic plastic-hinge refresh",
                    "ready": True,
                    "status": "closed",
                    "mode": "computed_member_local_hinge_refresh",
                    "reason": "Dynamic hinge-refresh artifact is attached.",
                    "evidence": "hinge_proxy_artifacts=2, artifact_present=True, benchmark_gate_pass=True",
                },
                {
                    "id": "wind_tunnel_raw_mapping",
                    "severity": "P1",
                    "title": "Raw wind-tunnel data mapping",
                    "ready": False,
                    "status": "open",
                    "mode": "semantic_pressure_binding_only",
                    "reason": "Raw wind-tunnel mapping artifact still needs direct bound rows.",
                    "evidence": "semantic_pressure_binding=True, bound_pressure_rows=0, unbound_pressure_rows=12",
                },
            ],
        },
    )
    _write_json(
        export_report,
        {
            "summary": {
                "direct_patch_change_count": 25,
                "instruction_sidecar_change_count": 0,
                "instruction_sidecar_audit_only_change_count": 11,
                "audit_review_packet_count": 2,
                "audit_review_queue_pending_count": 2,
                "evidence_model": "direct_patch_plus_audit_review_manifest",
                "direct_patch_action_family_counts": {"beam_section": 1, "rebar": 5},
                "instruction_sidecar_audit_only_action_family_counts": {"connection_detailing": 6},
            }
        },
    )
    _write_json(
        change_summary,
        {
            "change_summary_rows": [
                {
                    "story_band": 4,
                    "zone_label": "perimeter",
                    "member_type": "wall",
                    "changed_group_count": 2,
                    "cost_proxy_delta_sum": -157.3,
                    "constructability_delta_sum": -0.09,
                    "max_dcr_after_max": 0.58,
                },
                {
                    "story_band": 5,
                    "zone_label": "core",
                    "member_type": "beam",
                    "changed_group_count": 1,
                    "cost_proxy_delta_sum": 8.6,
                    "constructability_delta_sum": -0.03,
                    "max_dcr_after_max": 0.41,
                },
            ]
        },
    )
    _write_json(
        changes_report,
        {
            "changes": [
                {
                    "group_id": "S04:perimeter:nogroup:wall:W1",
                    "group_index": 0,
                    "member_type": "wall",
                    "action_name": "wall_thickness",
                    "action_family": "wall_thickness",
                    "before_section": "W300",
                    "after_section": "W250",
                    "before_thickness_scale": 1.00,
                    "after_thickness_scale": 0.92,
                    "before_rebar_ratio": 0.010,
                    "after_rebar_ratio": 0.008,
                    "before_constructability": 0.420,
                    "after_constructability": 0.380,
                    "before_detailing_complexity": 0.610,
                    "after_detailing_complexity": 0.570,
                    "drift_before_pct": 1.200,
                    "drift_after_pct": 1.080,
                    "residual_before_pct": 0.240,
                    "residual_after_pct": 0.210,
                    "cost_proxy_before": 320.5,
                    "cost_proxy_after": 310.0,
                    "cost_proxy_delta": -10.5,
                    "max_dcr_before": 0.920,
                    "max_dcr_after": 0.810,
                    "selection_gate": "hard_gate_pass",
                    "reason_selected": "selected_best_gain_in_batch",
                    "governing_clause": "KDS-WALL-001",
                },
                {
                    "group_id": "S05:core:nogroup:beam:B1",
                    "group_index": 1,
                    "member_type": "beam",
                    "action_name": "rebar_down",
                    "action_family": "rebar",
                    "before_section": "B700x350",
                    "after_section": "B700x350",
                    "before_thickness_scale": 1.00,
                    "after_thickness_scale": 1.00,
                    "before_rebar_ratio": 0.012,
                    "after_rebar_ratio": 0.007,
                    "before_constructability": 0.510,
                    "after_constructability": 0.480,
                    "before_detailing_complexity": 0.720,
                    "after_detailing_complexity": 0.660,
                    "drift_before_pct": 1.020,
                    "drift_after_pct": 1.000,
                    "residual_before_pct": 0.180,
                    "residual_after_pct": 0.175,
                    "cost_proxy_before": 180.1,
                    "cost_proxy_after": 188.7,
                    "cost_proxy_delta": 8.6,
                    "max_dcr_before": 0.670,
                    "max_dcr_after": 0.620,
                    "selection_gate": "hard_gate_pass",
                    "reason_selected": "selected_best_gain_in_batch",
                    "governing_clause": "KDS-BEAM-002",
                },
            ]
        },
    )
    np.savez(
        dataset_npz,
        member_ids=np.array(["101", "202"]),
        group_ids=np.array(["S04:perimeter:nogroup:wall:W1", "S05:core:nogroup:beam:B1"]),
        group_index_per_member=np.array([0, 1], dtype=np.int32),
        member_type_per_group=np.array(["wall", "beam"]),
        story_band_index=np.array([4, 5], dtype=np.int32),
    )
    _write_json(
        model_json,
        {
            "model": {
                "nodes": [
                    {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                    {"id": 2, "x": 10.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 10.0, "y": 10.0, "z": 0.0},
                    {"id": 4, "x": 0.0, "y": 10.0, "z": 0.0},
                    {"id": 5, "x": 2.0, "y": 2.0, "z": 12.0},
                    {"id": 6, "x": 8.0, "y": 2.0, "z": 18.0},
                    {"id": 7, "x": 4.0, "y": 4.0, "z": 0.0},
                    {"id": 8, "x": 4.0, "y": 4.0, "z": 15.0},
                    {"id": 9, "x": 1.0, "y": 1.0, "z": 6.0},
                    {"id": 10, "x": 9.0, "y": 1.0, "z": 6.0},
                    {"id": 11, "x": 9.0, "y": 9.0, "z": 6.0},
                    {"id": 12, "x": 1.0, "y": 9.0, "z": 6.0},
                ],
                "elements": [
                    {"id": 101, "type": "PLATE", "family": "wall", "section_id": 11, "node_ids": [1, 2, 3, 4]},
                    {"id": 202, "type": "BEAM", "family": "beam", "section_id": 12, "node_ids": [5, 6]},
                    {"id": 303, "type": "COLUMN", "family": "column", "section_id": 13, "node_ids": [7, 8]},
                    {"id": 404, "type": "PLATE", "family": "slab", "section_id": 14, "node_ids": [9, 10, 11, 12]},
                ],
                "sections": [
                    {"id": 11, "name": "WALL300X5000", "raw_tokens": ["WALL300X5000", "0.3", "5.0"]},
                    {"id": 12, "name": "SB800X3002.00", "raw_tokens": ["SB800X3002.00", "SB", "2", "0.8", "0.3"]},
                    {"id": 13, "name": "CFT600X600X20", "raw_tokens": ["CFT600X600X20", "0.6", "0.6", "0.02"]},
                    {"id": 14, "name": "SLAB180X3000", "raw_tokens": ["SLAB180X3000", "0.18", "3.0"]},
                ],
                "loads": {
                    "static_load_cases": [
                        {"name": "DEAD", "type": "D"},
                        {"name": "LIVE", "type": "L"},
                        {"name": "WINDX", "type": "WIND"},
                    ],
                    "load_cases": [
                        {"name": "DEAD", "category": "Static"},
                        {"name": "LIVE", "category": "Live"},
                        {"name": "WINDX", "category": "Wind"},
                    ],
                    "load_combinations": [
                        {
                            "name": "ULS1",
                            "limit_state": "strength",
                            "combination_type": "GEN",
                            "referenced_cases": ["DEAD", "LIVE", "WINDX"],
                            "referenced_combinations": [],
                            "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6, "WINDX": 0.7},
                            "expansion_mode": "linear_combination",
                            "expansion_depth": 1,
                            "referenced_leaf_cases": ["DEAD", "LIVE", "WINDX"],
                            "entry_count": 3,
                            "expression": "1.2(D) + 1.6(L) + 0.7(WINDX)",
                        },
                        {
                            "name": "ENV1",
                            "limit_state": "service",
                            "combination_type": "ENV",
                            "referenced_cases": [],
                            "referenced_combinations": ["ULS1"],
                            "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6, "WINDX": 0.7},
                            "expansion_mode": "envelope_union",
                            "expansion_depth": 2,
                            "referenced_leaf_cases": ["DEAD", "LIVE", "WINDX"],
                            "entry_count": 1,
                            "expression": "ENV(ULS1)",
                        },
                    ],
                    "load_combination_graph": {
                        "node_count": 5,
                        "edge_count": 4,
                        "combo_node_count": 2,
                        "case_node_count": 3,
                        "combo_summaries": [
                            {
                                "name": "ULS1",
                                "expansion_mode": "linear_combination",
                                "expansion_depth": 1,
                                "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6, "WINDX": 0.7},
                                "referenced_leaf_cases": ["DEAD", "LIVE", "WINDX"],
                            },
                            {
                                "name": "ENV1",
                                "expansion_mode": "envelope_union",
                                "expansion_depth": 2,
                                "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6, "WINDX": 0.7},
                                "referenced_leaf_cases": ["DEAD", "LIVE", "WINDX"],
                            },
                        ],
                    },
                    "nodal_loads": [
                        {"load_case": "LIVE", "node_ids": [5, 6], "fx": 0.0, "fy": 0.0, "fz": -120.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
                    ],
                    "selfweight": [
                        {"load_case": "DEAD", "gx": 0.0, "gy": 0.0, "gz": -1.0},
                    ],
                    "pressure_loads": [
                        {"load_case": "WINDX", "element_ids": [101, 404], "numeric_values": [2.5, 2.5], "tag_tokens": ["GX"]},
                    ],
                    "semantic_load_summary": {
                        "case_force_summaries": [
                            {"load_case": "DEAD", "semantic_status": "bound"},
                            {"load_case": "LIVE", "semantic_status": "bound"},
                            {"load_case": "WINDX", "semantic_status": "derived"},
                        ],
                    },
                },
                "metadata": {
                    "design_sections": [{"section_id": 11}, {"section_id": 12}],
                    "section_colors": [{"section_id": 11}, {"section_id": 13}],
                    "section_scales": [{"section_id": 12}, {"section_id": 14}],
                    "load_colors": [{"case_name": "DEAD"}, {"case_name": "WINDX"}],
                },
            }
        },
    )
    _write_json(
        execution_manifest,
        {
            "summary": {
                "execution_mode": "limited",
                "review_boundary_resolution_label": "approve_all=PASS_START_NOW_FULL/ready_full=yes; reject_one=ERR_ARCHITECTURE_BLOCKERS/open_revision=1",
                "review_boundary_owner_label": "licensed_engineer=2",
                "review_boundary_assignee_label": "unassigned=2",
                "review_boundary_assignment_status_label": "unassigned=2",
                "review_boundary_priority_label": "high=1, medium=1",
                "review_boundary_family_label": "connection_detailing=1, detailing=1",
                "review_boundary_followup_action_label": "wait_for_review=2",
                "review_boundary_sla_state_label": "within_sla=2",
                "review_boundary_age_bucket_label": "lt_24h=2",
            },
            "blocked_tasks": [
                {
                    "benchmark_family": "connection_detailing",
                    "priority": "high",
                    "owner": "licensed_engineer",
                    "assignee_name": "unassigned",
                    "assignment_status": "unassigned",
                    "followup_action": "wait_for_review",
                    "sla_state": "within_sla",
                    "age_bucket": "lt_24h",
                    "preview_if_all_closed_reason_code": "PASS_START_NOW_FULL",
                    "preview_if_rejected_reason_code": "ERR_ARCHITECTURE_BLOCKERS",
                }
            ],
        },
    )
    _write_json(
        execution_status,
        {
            "summary": {
                "execution_mode": "limited",
                "status_mode": "execution_complete_no_fail",
                "completed_task_count": 10,
                "blocked_task_count": 2,
                "completion_ratio": 1.0,
            }
        },
    )
    _write_json(
        committee_package,
        {
            "artifacts": {
                "committee_dashboard_html": str(tmp_path / "committee_review_dashboard.html"),
                "drift_envelope_png": str(png),
                "core_hysteresis_png": str(hysteresis_png),
                "project_registry_report": str(tmp_path / "project_registry.json"),
                "project_package_zip": str(tmp_path / "project_package.zip"),
                "project_registry_signature": str(tmp_path / "project_registry.signature.b64"),
                "external_benchmark_batch_job_report_json": str(tmp_path / "external_benchmark_batch_job_report.json"),
            }
        },
    )
    _write_json(
        pbd_package,
        {
            "metrics": {
                "core_hysteresis_overflow_regime": True,
                "core_hysteresis_visual_mode": "operational_detail_plus_magnitude_inset",
                "core_hysteresis_solver_instability_suspected": True,
                "core_hysteresis_regime_label": "overflow / unstable regime",
            }
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_structural_optimization_visualization_viewer.py",
            "--release-gap-report",
            str(release_gap),
            "--commercial-workflow-breadth-report",
            str(commercial_workflow_breadth_report),
            "--export-report",
            str(export_report),
            "--change-summary-report",
            str(change_summary),
            "--changes-report",
            str(changes_report),
            "--design-optimization-npz",
            str(dataset_npz),
            "--model-json",
            str(model_json),
            "--execution-manifest",
            str(execution_manifest),
            "--execution-status-manifest",
            str(execution_status),
            "--committee-package-report",
            str(committee_package),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads((out_dir / "structural_optimization_viewer.json").read_text(encoding="utf-8"))
    html = (out_dir / "structural_optimization_viewer.html").read_text(encoding="utf-8")
    assert "structural-viewer-selection-v1" in html
    assert "readSharedSelectionFallback" in html
    assert "row_provenance_shared_selection" in html
    assert "member_set" in html
    assert "memberIds" in html
    assert "selectionSetCount" in html
    assert "resolveSharedViewerMemberIds" in html
    assert "results_series_index" in html
    assert "row_ref" in html
    assert "member_set" in html
    assert "memberIds" in html
    assert "selectionSetCount" in html
    assert "overlay_member_id" in html
    assert "overlay_group_id" in html
    assert "overlay_row_id" in html
    assert "overlay_selected_event_index" in html
    onepage = (out_dir / "analysis_evidence_gallery_onepage.html").read_text(encoding="utf-8")
    beam_viewer_html = (out_dir / "entries" / "beam_archive_rhino_baseline.html").read_text(encoding="utf-8")
    beam_preview_viewer_html = (out_dir / "entries" / "beam_decoded_preview_baseline.html").read_text(encoding="utf-8")
    ramp_preview_viewer_html = (out_dir / "entries" / "ramp_decoded_preview_baseline.html").read_text(encoding="utf-8")
    rc_house_preview_viewer_html = (out_dir / "entries" / "rc_house_decoded_preview_baseline.html").read_text(encoding="utf-8")
    locator_rows = payload["member_overlay"]["member_locator_rows"]
    locator_groups = payload["member_overlay"]["member_locator_groups"]
    assert len(locator_rows) == 2
    assert len(locator_groups) == 2
    assert all(row["overlay_row_id"].startswith("overlay_row::") for row in locator_rows)
    assert {row["change_semantics_label"] for row in locator_rows} == {"같은 자리 / 단면·두께 조정", "같은 자리 / 배근·디테일 조정"}
    assert all(row["optimization_meaning_label"] for row in locator_rows)
    assert all(row["spatial_read_label"] for row in locator_rows)
    assert all(group["member_count"] == 1 for group in locator_groups)
    assert all(group["representative_members"] for group in locator_groups)
    assert any(group["representative_members"][0]["label"] for group in locator_groups)
    assert any("thickness x1.00 -> x0.92" in group["representative_modification_label"] for group in locator_groups)
    assert any("dcr 0.920 -> 0.810" in group["representative_impact_label"] for group in locator_groups)
    after_segments = payload["interactive_3d"]["after_segments"]
    assert any(segment["change_semantics_label"] == "같은 자리 / 단면·두께 조정" for segment in after_segments)
    assert any(segment["optimization_meaning_label"] for segment in after_segments)
    assert any(segment["spatial_read_label"] for segment in after_segments)
    rc_house_source_html = (out_dir / "entries" / "source_midas_support_rc_house_archive.html").read_text(encoding="utf-8")
    ramp_source_html = (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    fcm_source_html = (out_dir / "entries" / "source_midas_support_fcm_bridge_archive.html").read_text(encoding="utf-8")
    opensees_compare_html = (out_dir / "entries" / "opensees_scbf_family_compare.html").read_text(encoding="utf-8")
    opensees_frame_baseline_html = (out_dir / "entries" / "opensees_scbf16b_baseline.html").read_text(encoding="utf-8")
    opensees_shell_baseline_html = (out_dir / "entries" / "opensees_scbf16b_shell_beam_mix_baseline.html").read_text(encoding="utf-8")
    opstool_synthetic_compare_html = (out_dir / "entries" / "opstool_606m_outrigger_ai_compare.html").read_text(encoding="utf-8")
    opstool_5pack_execution_html = (out_dir / "entries" / "ai_opstool_direct_5pack_execution.html").read_text(encoding="utf-8")
    opstool_5pack_case_html = (out_dir / "entries" / "ai_opstool_direct_case_00020.html").read_text(encoding="utf-8")
    source_beam_payload = json.loads((out_dir / "entries" / "source_midas_support_beam_archive.json").read_text(encoding="utf-8"))
    beam_probe_payload = json.loads((out_dir / "entries" / "binary_probe_midas_support_beam_archive.json").read_text(encoding="utf-8"))
    source_fcm_payload = json.loads((out_dir / "entries" / "source_midas_support_fcm_bridge_archive.json").read_text(encoding="utf-8"))
    source_github_payload = json.loads((out_dir / "entries" / "source_midas_generator_33_github.json").read_text(encoding="utf-8"))
    source_ramp_payload = json.loads((out_dir / "entries" / "source_midas_support_ramp_archive.json").read_text(encoding="utf-8"))
    fcm_inventory_payload = json.loads((out_dir / "entries" / "binary_inventory_midas_support_fcm_bridge_archive.json").read_text(encoding="utf-8"))
    source_rc_house_payload = json.loads((out_dir / "entries" / "source_midas_support_rc_house_archive.json").read_text(encoding="utf-8"))
    beam_preview_viewer_payload = json.loads((out_dir / "entries" / "beam_decoded_preview_baseline.json").read_text(encoding="utf-8"))
    ramp_preview_viewer_payload = json.loads((out_dir / "entries" / "ramp_decoded_preview_baseline.json").read_text(encoding="utf-8"))
    fcm_preview_viewer_path = out_dir / "entries" / "fcm_bridge_decoded_preview_baseline.json"
    fcm_preview_viewer_payload = json.loads(fcm_preview_viewer_path.read_text(encoding="utf-8")) if fcm_preview_viewer_path.exists() else None
    rc_house_preview_viewer_payload = json.loads((out_dir / "entries" / "rc_house_decoded_preview_baseline.json").read_text(encoding="utf-8"))
    ramp_inventory_payload = json.loads((out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.json").read_text(encoding="utf-8"))
    rc_house_preview_path = out_dir / "entries" / "binary_preview_midas_support_rc_house_archive.json"
    rc_house_preview_payload = json.loads(rc_house_preview_path.read_text(encoding="utf-8")) if rc_house_preview_path.exists() else None
    ramp_member_json_candidates = sorted((out_dir / "entries").glob("binary_member_midas_support_ramp_archive_*.json"))
    assert ramp_member_json_candidates
    ramp_member_payload = json.loads(ramp_member_json_candidates[0].read_text(encoding="utf-8"))
    beam_archive_member_candidates = sorted((out_dir / "entries").glob("binary_archive_member_midas_support_beam_archive_*.json"))
    assert beam_archive_member_candidates
    beam_archive_member_payload = json.loads(beam_archive_member_candidates[0].read_text(encoding="utf-8"))

    assert payload["viewer_mode"] == "static_release_artifact_viewer"
    assert payload["case_catalog_summary"]["total_entry_count"] >= 4
    assert payload["total_entry_count"] == payload["case_catalog_summary"]["total_entry_count"]
    assert payload["verified_preview_count"] == payload["case_catalog_summary"]["verified_preview_count"]
    assert payload["hint_preview_count"] == payload["case_catalog_summary"]["hint_preview_count"]
    assert payload["raw_preview_count"] == payload["case_catalog_summary"]["raw_preview_count"]
    assert payload["crosscheck_available_count"] == payload["case_catalog_summary"]["crosscheck_available_count"]
    assert payload["upgrade_candidate_count"] == payload["case_catalog_summary"]["upgrade_candidate_count"]
    assert payload["artifact_links"]["optimized_drawing_review_html"].endswith("optimized_drawing_review.html")
    assert payload["artifact_links"]["benchmark_optimization_review_html"].endswith("benchmark_optimization_review.html")
    assert payload["artifact_links"]["benchmark_optimization_review_summary_json"].endswith("benchmark_optimization_review_summary.json")
    assert payload["artifact_links"]["commercial_workflow_breadth_report_json"].endswith(
        "commercial_workflow_breadth_report.json"
    )
    assert payload["artifact_links"]["expert_validation_dashboard_html"] == payload["artifact_links"]["committee_dashboard_html"]
    assert payload["artifact_links"]["validation_boundary_json"] == payload["artifact_links"]["release_gap_report_json"]
    assert payload["artifact_links"]["external_expert_mode_href"].endswith("#viewer-expert-review-route")
    assert payload["artifact_links"]["project_registry_report"].endswith("project_registry.json")
    assert payload["artifact_links"]["project_registry_portfolio_workspace_json"].endswith(
        "project_registry_portfolio_workspace.json"
    )
    assert payload["artifact_links"]["project_package_zip"].endswith("project_package.zip")
    assert payload["artifact_links"]["project_registry_signature"].endswith("project_registry.signature.b64")
    assert payload["artifact_links"]["external_benchmark_batch_job_report_json"].endswith(
        "external_benchmark_batch_job_report.json"
    )
    hero_cards = {card["label"]: card for card in payload["hero_cards"]}
    assert hero_cards["Project Package"]["value"] == "4096 B"
    assert hero_cards["Project Package"]["note"] == "approvals=2 sig=ok"
    assert hero_cards["Batch Runner"]["value"] == "4 jobs"
    assert hero_cards["Batch Runner"]["note"] == "done=2 failed=0 reruns=1"
    assert payload["system_state"]["panel_external_validation_pending"] is True
    assert payload["system_state"]["panel_external_validation_advisory_only"] is True
    assert payload["system_state"]["panel_external_validation_release_blocking"] is False
    assert payload["system_state"]["panel_external_validation_status_label"] == "advisory_only_boundary"
    assert "status=advisory_only_boundary" in payload["detail_context"]["boundary_queue_label"]
    assert "advisory_only=True" in payload["detail_context"]["boundary_queue_label"]
    assert "release_blocking=False" in payload["detail_context"]["boundary_queue_label"]
    assert "status=advisory_only_boundary" in html
    assert payload["commercial_parity_summary"]["label"] == "Heuristic Commercial Parity Estimate"
    assert payload["commercial_parity_summary"]["overall_score"] > 0
    assert len(payload["commercial_parity_summary"]["dimensions"]) == 4
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["available"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["ops_bundle_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["palette_family_count"] >= 4
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["portfolio_project_count"] >= 2
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["family_row_count"] >= 4
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["ready_family_count"] >= 4
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_runtime_submission_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_runtime_submission_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_runtime_writeback_depth_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_runtime_writeback_depth_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_local_runtime_scenario_depth_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_local_runtime_scenario_depth_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_multi_project_runtime_writeback_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_multi_project_runtime_writeback_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_multi_project_runtime_writeback_project_count"] >= 4
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_solver_family_breadth_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_solver_family_breadth_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_writeback_breadth_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["native_authoring_writeback_breadth_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["project_ops_service_attached"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["project_ops_service_ready"] is True
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["project_ops_service_project_count"] >= 4
    assert payload["commercial_parity_summary"]["native_authoring_evidence"]["project_ops_service_family_count"] >= 4
    assert "Project ops service snapshot: PASS" in payload["commercial_parity_summary"]["native_authoring_evidence"]["project_ops_service_summary_line"]
    assert payload["runtime_submission_lane_surface"]["label"] == "Runtime Submission Lane"
    assert payload["runtime_submission_lane_surface"]["count"] >= 5
    assert [row["label"] for row in payload["runtime_submission_lane_surface"]["rows"]] == [
        "Runtime submission lane",
        "Writeback / registry",
        "Project Ops Service",
        "Portfolio / family / runtime / service alignment",
        "Runtime writeback depth",
        "Multi-project runtime/writeback",
        "Solver family breadth",
        "Local runtime scenario depth",
        "Local variant/writeback trace",
        "Broader native writeback coverage",
        "Family corpus",
        "Local evidence",
    ]
    assert payload["runtime_submission_lane_surface"]["rows"][3]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][4]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][5]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][6]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][7]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][8]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][9]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["rows"][10]["status"] == "PASS"
    assert payload["runtime_submission_lane_surface"]["summary_line"] == (
        "runtime=PASS | writeback=PASS | runtime_writeback_depth=PASS | local_runtime_depth=PASS | local_variant_trace=PASS | multi_project_runtime=PASS | solver_family_breadth=PASS | writeback_breadth=PASS | "
        "family_corpus=PASS | local_evidence=PASS | project_ops_service=PASS | alignment=PASS"
    )
    assert payload["runtime_submission_lane_surface"]["alignment_summary_line"] == (
        "alignment=PASS | portfolio=PASS | families=8/8 | runtime=PASS | service=PASS"
    )
    assert payload["commercial_workflow_breadth_surface"]["label"] == "Commercial Workflow Breadth"
    assert payload["commercial_workflow_breadth_surface"]["ready_count"] == 2
    assert payload["commercial_workflow_breadth_surface"]["open_count"] == 1
    assert payload["commercial_workflow_breadth_surface"]["artifact_name"] == "commercial_workflow_breadth_report.json"
    assert payload["commercial_parity_summary"]["commercial_workflow_breadth_surface"]["headline"] == (
        "ready 2/3 | checks=CHECK | clauses=9"
    )
    assert [row["label"] for row in payload["commercial_workflow_breadth_surface"]["rows"]] == [
        "Construction-stage breadth",
        "Rail / tunnel serviceability",
        "Design redesign loop breadth",
    ]
    assert payload["commercial_workflow_breadth_surface"]["rows"][2]["status"] == "CHECK"
    assert payload["commercialization_depth_surface"]["label"] == "P0/P1 Commercialization Depth"
    assert payload["commercialization_depth_surface"]["ready_count"] == 5
    assert payload["commercialization_depth_surface"]["p0_ready_count"] == 3
    assert payload["commercialization_depth_surface"]["p1_ready_count"] == 2
    assert payload["commercial_parity_summary"]["commercialization_depth_surface"]["headline"] == "P0 3/3 | P1 2/2 | total 5/5"
    assert [row["label"] for row in payload["commercialization_depth_surface"]["rows"]] == [
        "Material / constitutive depth",
        "Load / combination depth",
        "Reference regression loop",
        "Advanced SSI / interaction depth",
        "Wind / raw mapping depth",
    ]
    assert payload["commercialization_depth_surface"]["rows"][3]["status"] == "PASS"
    assert payload["commercialization_depth_surface"]["rows"][4]["status"] == "PASS"
    assert "raw_hffb_node_pressure_mapping" in payload["commercialization_depth_surface"]["rows"][4]["summary_excerpt"]
    assert payload["server_ops_summary"]["label"] == "Server-Style Ops Summary"
    assert payload["server_ops_summary"]["ready_count"] == 3
    assert payload["server_ops_summary"]["open_count"] == 0
    assert payload["server_ops_summary"]["rows"][0]["label"] == "Workspace / runtime"
    assert payload["server_ops_summary"]["rows"][1]["label"] == "Solver session / ops bundle"
    assert payload["server_ops_summary"]["rows"][2]["label"] == "Family-track breadth"
    assert "workspace=PASS" in payload["server_ops_summary"]["summary_line"]
    assert payload["family_track_commercialization_breadth"]["label"] == "Family-Track Commercialization Breadth"
    assert payload["family_track_commercialization_breadth"]["count"] >= 4
    assert payload["family_track_commercialization_breadth"]["ready_count"] >= 4
    assert payload["family_track_commercialization_breadth"]["open_count"] == 0
    assert any(row["family_label"] == "Sample Tower" for row in payload["family_track_commercialization_breadth"]["rows"])
    assert any(row["status"] == "READY" for row in payload["family_track_commercialization_breadth"]["rows"])
    assert "palette=" in payload["family_track_commercialization_breadth"]["summary_line"]
    assert payload["advanced_holdout_surface"]["count"] == 2
    assert payload["advanced_holdout_surface"]["ready_count"] == 1
    assert payload["advanced_holdout_surface"]["open_count"] == 1
    assert payload["advanced_holdout_surface"]["rows"][0]["status"] == "closed"
    assert payload["advanced_holdout_surface"]["rows"][1]["status"] == "open"
    assert any(
        row["family_id"] == "sample_tower" and row["family_label"] == "Sample Tower"
        for row in payload["commercial_parity_summary"]["native_authoring_evidence"]["family_rows"]
    )
    assert next(
        row
        for row in payload["commercial_parity_summary"]["dimensions"]
        if row["label"] == "authoring / solver replacement"
    )["score"] > 40
    assert "ops_bundle=PASS" in next(
        row
        for row in payload["commercial_parity_summary"]["dimensions"]
        if row["label"] == "authoring / solver replacement"
    )["note"]
    assert payload["benchmark_expansion_summary"]["label"] == "Megastructure Expansion Board"
    assert payload["benchmark_expansion_summary"]["direct_model_count"] >= 1
    assert payload["benchmark_expansion_summary"]["detailed_geometry_summary"]["viewer_ready_family_count"] >= 3
    assert payload["benchmark_expansion_summary"]["detailed_geometry_summary"]["local_bridge_pending_count"] == 0
    assert len(payload["benchmark_expansion_summary"]["detailed_geometry_tracks"]) >= 2
    assert len(payload["benchmark_expansion_summary"]["lanes"]) >= 3
    assert len(payload["benchmark_expansion_summary"]["rows"]) >= 5
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["available"] is True
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["solver_session_ready"] is True
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["ops_bundle_ready"] is True
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["session_id"] == (
        "native-authoring-sample-tower::solver-session"
    )
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["combo_count"] == 13
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["palette_family_count"] >= 4
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["portfolio_project_count"] >= 2
    assert payload["benchmark_expansion_summary"]["native_authoring_evidence"]["family_row_count"] >= 4
    assert any(
        lane["lane_id"] == "opstool_direct_green_lane"
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "native_authoring_solver_lane"
        and lane["lane_badge"] == "AUTHORING READY"
        and lane["primary_label"] == "ops bundle"
        and lane["primary_href"].endswith("native_authoring_ops_bundle.json")
        and lane["secondary_href"].endswith("native_authoring_solver_session.json")
        and lane["tertiary_href"].endswith("native_authoring_solver_session.loadcomb_preview.mgt")
        and "runtime_authoring=PASS" in lane["execution_summary_line"]
        and "families_ready=" in lane["execution_summary_line"]
        and "Sample Tower" in lane["track_names"]
        and "Steel Braced Frame" in lane["track_names"]
        and any(item["id"] == "native_authoring_family_sample_tower" for item in lane["items"])
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "opstool_direct_green_lane"
        and lane["lane_status"] == "executed"
        and lane["lane_note_short"] == "materialized 5-pack gates passed"
        and lane["execution_summary_line"].startswith("benchmark_kpi=PASS")
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "authority_green_now"
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "authority_yellow_next_ingest"
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "peer_blind_prediction_public_input"
        and lane["lane_badge"] == "INPUT READY"
        and lane["primary_href"].endswith("benchmark_optimization_review.html#peer-benchmark")
        and lane["primary_label"] == "benchmark drawings"
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "peer_blind_prediction_compare_lane"
        and lane["primary_href"].endswith("benchmark_optimization_review.html#peer-benchmark")
        and lane["primary_label"] == "benchmark drawings"
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        row["id"] == "canton_tower_reduced_shm_family"
        and row["secondary_href"].endswith("benchmark_optimization_review.html#canton-review")
        and row["secondary_label"] == "AI optimized drawings"
        for row in payload["benchmark_expansion_summary"]["detailed_geometry_tracks"]
    )
    assert any(
        lane["lane_id"] == "peer_blind_prediction_sample_compare_lane"
        and lane["lane_status"] == "green"
        and lane["lane_badge"] == "SAMPLE READY"
        and any("sample measured-response bundle: PASS" in summary for summary in lane["readiness_summaries"])
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        (
            row["id"] == "opstool_606m_megatall_model"
            or "opstool_606m_megatall_model" in row.get("id", "")
            or "opstool 606m megatall model" in row.get("title", "").lower()
            or "opstool_606m_megatall_model" in row.get("source_name", "")
        )
        and row["direct_model_ready"]
        for row in payload["benchmark_expansion_summary"]["rows"]
    )
    assert any(
        row["id"] in {"tpu_highrise_wind_pressure_and_force", "tpu_wind"}
        or "tpu" in row.get("title", "").lower()
        or "tpu" in row.get("source_name", "").lower()
        for row in payload["benchmark_expansion_summary"]["rows"]
    )
    assert any(
        row["entry_id"] == "midas33_release_compare"
        for row in payload["commercial_parity_summary"]["representative_cases"]
    )
    assert any(
        row["entry_id"] == "beam_decoded_preview_baseline"
        for row in payload["commercial_parity_summary"]["representative_cases"]
    )
    assert any(row["entry_id"] == "midas33_release_compare" for row in payload["case_catalog"])
    assert any(row["entry_id"] == "ai_release_optimization_data" for row in payload["case_catalog"])
    assert any(
        row["entry_id"] == "ai_opstool_direct_5pack_execution"
        and row["status_label"] == "BENCHMARK_PASS_NOISE_PASS"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "ai_opstool_direct_case_00020"
        and row["direct_batch_case_id"] == "opstool_606m_megatall_model-00020"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "ai_opstool_direct_case_00009"
        and row["direct_batch_case_short_id"] == "00009"
        for row in payload["case_catalog"]
    )
    assert payload["benchmark_expansion_summary"]["executed_lane_count"] >= 1
    assert payload["benchmark_expansion_summary"]["executed_case_count"] >= 5
    assert any(row["entry_id"] == "megastructure_tpu_highrise_wind_pressure_and_force" for row in payload["case_catalog"])
    assert any(
        row["entry_id"] == "megastructure_zenodo_atwood_highrise_shm_2025"
        and row["status_label"] == "registered / green benchmark lane"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "megastructure_zenodo_atwood_highrise_shm_2025"
        and row["benchmark_card_title"] == "Atwood High-Rise SHM"
        and row["benchmark_lane_note_short"] == "ready for featured viewer surfacing"
        and row["benchmark_why_now_line"] == "MIDAS building bias를 가장 빨리 줄이는 green measured track."
        and row["benchmark_next_step_line"] == "Refresh Atwood cases and pin KPI stub again."
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "megastructure_zenodo_kw51_railway_bridge_monitoring_2025"
        and row["status_label"] == "registered / yellow next-ingest lane"
        for row in payload["case_catalog"]
    )
    assert any(
        lane["lane_id"] == "authority_green_now"
        and lane["lane_note_short"] == "ready for featured viewer surfacing"
        and "green measured track." in lane["why_now_short"]
        and "tighten viewer wording." in lane["next_step_short"]
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert any(
        lane["lane_id"] == "authority_yellow_next_ingest"
        and lane["lane_note_short"] == "holdout worth surfacing after next ingest"
        and "yellow track." in lane["why_now_short"]
        and "starter case family." in lane["next_step_short"]
        for lane in payload["benchmark_expansion_summary"]["lanes"]
    )
    assert (out_dir / "entries" / "ai_release_optimization_data.html").exists()
    assert (out_dir / "entries" / "megastructure_tpu_highrise_wind_pressure_and_force.html").exists()
    assert payload["artifact_links"]["changes_report_json"].endswith("design_optimization_cost_reduction_changes.json")
    assert payload["artifact_links"]["execution_status_manifest_json"].endswith("external_benchmark_execution_status_manifest.json")
    assert payload["case_context"]["case_family"] == "midas33_release"
    assert payload["case_context"]["evidence_links"]
    assert payload["case_context"]["evidence_links"][0]["key"] == "pbd-review-package"
    assert payload["case_context"]["evidence_links"][0]["corner_label"] == "PACKAGE"
    assert payload["case_context"]["direct_patch_label"] == "25"
    assert payload["case_context"]["audit_packets_label"] == "2"
    assert payload["case_context"]["queue_pending_label"] == "2"
    assert payload["case_context"]["blocked_tasks_label"] == "2"
    assert payload["case_context"]["change_rows_label"] == "2"
    assert payload["case_context"]["measured_chain_label"] == "5.4 min"
    assert payload["case_context"]["section_library_available"] is True
    assert payload["case_context"]["section_library_source_label"] == "viewer fallback derived"
    assert payload["case_context"]["section_row_count_label"] == "4"
    assert payload["case_context"]["used_section_count_label"] == "4"
    assert payload["case_context"]["unused_section_count_label"] == "0"
    assert payload["case_context"]["derived_template_count_label"] == "4"
    assert payload["case_context"]["section_library_usage_coverage_label"] == "4/4 used"
    assert payload["case_context"]["section_focus_coverage_label"] == "4/4 linked"
    assert payload["case_context"]["section_family_mix_label"] == "composite=3, steel=1"
    assert payload["case_context"]["section_shape_mix_label"] == "cft_box=1, h_beam=1, slab_strip=1, wall_strip=1"
    assert payload["case_context"]["section_library_highlights"][0]["name"] == "CFT600X600X20"
    assert payload["case_context"]["section_library_highlights"][0]["same_section_member_count_label"] == "1"
    assert payload["case_context"]["section_library_highlights"][0]["representative_coverage_label"] == "1/1 representative linked"
    assert payload["case_context"]["load_pattern_library_available"] is True
    assert payload["case_context"]["load_pattern_source_label"] == "viewer fallback derived"
    assert payload["case_context"]["load_contract_recovery_available"] is False
    assert payload["case_context"]["load_pattern_count_label"] == "3"
    assert payload["case_context"]["load_pattern_primitive_count_label"] == "3"
    assert payload["case_context"]["load_pattern_combination_count_label"] == "2"
    assert payload["case_context"]["load_pattern_kind_mix_label"] == "point_load=1, self_weight=1, surface_pressure=1"
    assert payload["case_context"]["load_pattern_design_situation_mix_label"] == "lateral_wind=1, permanent_gravity=1, variable_imposed=1"
    assert payload["case_context"]["load_pattern_semantic_status_mix_label"] == "bound=2, derived=1"
    assert payload["case_context"]["load_pattern_highlights"][0]["label"] == "DEAD"
    assert payload["case_context"]["load_pattern_highlights"][0]["direction_preview_label"] == "global_z"
    assert payload["case_context"]["load_pattern_highlights"][0]["focus_available"] is True
    assert payload["case_context"]["load_pattern_highlights"][0]["focus_story_scope_label"] == "all stories (4)"
    assert payload["case_context"]["load_pattern_highlights"][0]["focus_category_scope_label"] == "all categories"
    assert payload["case_context"]["load_pattern_highlights"][0]["focus_target_member_count_label"] == "4"
    assert payload["case_context"]["load_pattern_highlights"][0]["focus_representative_member_id"] == "101"
    assert payload["case_context"]["load_pattern_highlights"][1]["label"] == "LIVE"
    assert payload["case_context"]["load_pattern_highlights"][1]["focus_story_scope_label"] == "S04"
    assert payload["case_context"]["load_pattern_highlights"][1]["focus_category_scope_label"] == "beam"
    assert payload["case_context"]["load_pattern_highlights"][1]["focus_representative_member_id"] == "202"
    assert payload["case_context"]["load_pattern_highlights"][0]["recommended_results_series_label"] == "Final drift"
    assert payload["case_context"]["load_pattern_highlights"][2]["recommended_results_card"] == "time-history"
    assert "lateral wind scope" in payload["case_context"]["load_pattern_highlights"][2]["recommended_results_reason_label"]
    assert payload["case_context"]["load_pattern_highlights"][2]["label"] == "WINDX"
    assert payload["case_context"]["load_pattern_highlights"][2]["focus_story_scope_label"] == "S01, S02"
    assert payload["case_context"]["load_pattern_highlights"][2]["focus_category_scope_label"] == "slab, wall"
    assert payload["case_context"]["load_combination_browser_available"] is True
    assert payload["case_context"]["load_combination_count_label"] == "2"
    assert payload["case_context"]["load_combination_graph_density_label"] == "5 nodes / 4 edges"
    assert payload["case_context"]["load_combination_limit_state_mix_label"] == "service=1, strength=1"
    assert payload["case_context"]["load_combination_expansion_mode_mix_label"] == "envelope_union=1, linear_combination=1"
    assert payload["case_context"]["load_combination_leaf_case_union_label"] == "DEAD, LIVE, WINDX"
    assert payload["case_context"]["load_combination_max_depth_label"] == "2"
    assert payload["case_context"]["load_combination_editor_seed_available"] is True
    assert payload["case_context"]["load_combination_editor_seed_source_label"] == "viewer fallback derived"
    assert payload["case_context"]["load_combination_graph_stage_count_label"] == "3"
    assert payload["case_context"]["load_combination_graph_case_count_label"] == "3"
    assert payload["case_context"]["load_combination_graph_combo_count_label"] == "2"
    assert payload["case_context"]["load_combination_graph_edge_count_label"] == "4"
    assert len(payload["case_context"]["load_combination_graph_node_rows"]) == 5
    assert len(payload["case_context"]["load_combination_graph_edge_rows"]) == 4
    assert payload["case_context"]["load_combination_highlights"][0]["name"] == "ENV1"
    assert payload["case_context"]["load_combination_highlights"][0]["expansion_mode_label"] == "envelope_union"
    assert payload["case_context"]["load_combination_highlights"][0]["leaf_case_scope_label"] == "DEAD, LIVE, WINDX"
    assert payload["case_context"]["load_combination_highlights"][0]["recommended_results_card"] == "time-history"
    assert payload["case_context"]["load_combination_highlights"][0]["recommended_results_series_label"] == "Displacement u"
    assert payload["case_context"]["load_combination_highlights"][1]["name"] == "ULS1"
    assert payload["case_context"]["load_combination_highlights"][1]["focus_story_scope_label"] == "all stories (4)"
    assert payload["results_explorer"]["available"] is True
    assert payload["results_explorer"]["ndtha_response"]["available"] is True
    assert payload["results_explorer"]["ndtha_response"]["response_npz_available"] is True
    assert payload["results_explorer"]["ndtha_response"]["solver_control_available"] is True
    assert payload["results_explorer"]["ndtha_response"]["response_npz_case_count"] == 3
    assert payload["results_explorer"]["ndtha_response"]["solver_control_event_count"] == 7200
    assert payload["results_explorer"]["ndtha_response"]["solver_control_nonconverged_step_count"] == 0
    assert payload["results_explorer"]["ndtha_response"]["solver_control_cutback_step_count"] == 3
    assert payload["results_explorer"]["ndtha_response"]["response_npz_series_case_count"] == 3
    assert payload["results_explorer"]["ndtha_response"]["response_npz_series_contract_pass"] is True
    assert payload["results_explorer"]["ndtha_response"]["step_series_depth_available"] is True
    assert payload["results_explorer"]["ndtha_response"]["step_series_depth_label"] == "2400"
    assert payload["results_explorer"]["geometry_crosswalk"]["available"] is True
    assert payload["results_explorer"]["geometry_crosswalk"]["full_crosswalk_depth_available"] is True
    assert payload["results_explorer"]["geometry_crosswalk"]["full_crosswalk_depth_label"] == "1056"
    assert payload["results_explorer"]["geometry_full_crosswalk_depth_available"] is True
    assert payload["results_explorer"]["geometry_full_crosswalk_depth_label"] == "1056"
    assert payload["results_explorer"]["general_fe_contact_coupling_available"] is True
    assert "support families=" in payload["results_explorer"]["general_fe_contact_coupling_summary_label"]
    assert "coupling depth=" in payload["results_explorer"]["general_fe_contact_coupling_summary_label"]
    assert "assembled depth=" in payload["results_explorer"]["general_fe_contact_coupling_summary_label"]
    assert payload["results_explorer"]["traceability"]["surface_chain_label"] == "time-history -> envelope -> ndtha-response -> mode-shape"
    assert payload["results_explorer"]["traceability"]["source_report_count"] == 4
    assert payload["results_explorer"]["traceability"]["audit_report_count"] == 10
    assert payload["results_explorer"]["traceability"]["commercial_workflow_breadth_traceability_label"] == (
        "checks=CHECK | construction_snapshots=9 | rail_actions=4 | design_traceability=87.5%"
    )
    assert any(
        row["label"] == "Project Registry"
        for row in payload["results_explorer"]["traceability"]["audit_reports"]
    )
    assert any(
        row["label"] == "Commercial Workflow Breadth JSON"
        for row in payload["results_explorer"]["traceability"]["audit_reports"]
    )
    assert any(
        row["label"] == "Batch Job Report"
        for row in payload["results_explorer"]["traceability"]["audit_reports"]
    )
    assert "support families=" in payload["results_explorer"]["traceability"]["general_fe_contact_coupling_summary_label"]
    assert payload["delivery_boundary"]["direct_patch_change_count"] == 25
    assert payload["benchmark_execution"]["review_boundary_assignee_label"] == "unassigned=2"
    assert payload["benchmark_execution"]["batch_job_count"] == 4
    assert payload["benchmark_execution"]["batch_completed_count"] == 2
    assert payload["benchmark_execution"]["batch_failed_count"] == 0
    assert payload["benchmark_execution"]["batch_rerun_count"] == 1
    assert payload["detail_context"]["ready_vector_label"] == "hinge=ready | panel=ready | foundation=ready | wind=ready"
    assert "batch=2/4" in payload["detail_context"]["benchmark_progress_label"]
    assert "batch_failed=0" in payload["detail_context"]["benchmark_progress_label"]
    assert payload["change_overview"]["row_count"] == 2
    assert payload["story_zone_map"]["nonempty_cell_count"] == 2
    assert payload["baseline_structure"]["mode"] == "before_optimization_structural_baseline"
    assert payload["baseline_structure"]["total_element_count"] == 4
    assert payload["baseline_structure"]["story_slice_options"]
    assert payload["baseline_structure"]["story_slice_label"] != "n/a"
    assert payload["interactive_3d"]["mode"] == "interactive_canvas_xyz_structure"
    assert payload["interactive_3d"]["story_slice_options"]
    assert payload["interactive_3d"]["story_slice_label"] != "n/a"
    assert payload["interactive_3d"]["baseline_segment_raw_count"] >= payload["interactive_3d"]["baseline_segment_count"]
    assert payload["interactive_3d"]["baseline_lod_step"] >= 1
    assert payload["interactive_3d"]["baseline_segment_count"] > 0
    assert payload["interactive_3d"]["after_segment_count"] > 0
    assert payload["member_overlay"]["mode"] == "changed_member_overlay"
    assert payload["member_overlay"]["changed_member_count"] == 2
    assert payload["coverage_summary"]["mapped_groups_label"] == "2/2"
    assert payload["coverage_summary"]["live_member_type_label"] == "beam=1, wall=1"
    assert payload["coverage_summary"]["type_alignment_label"] == "2/2 aligned"
    assert payload["coverage_summary"]["type_mismatch_count"] == 0
    assert payload["member_overlay"]["family_options"] == [
        {"label": "rebar", "count": 1},
        {"label": "wall_thickness", "count": 1},
    ]
    assert "viewer-signal-strip" in html
    assert "Current Review Snapshot" in html
    assert "viewer-signal-card" in html
    assert "Core workflow" in html
    assert "data-core-mode='core'" in html
    assert "data-core-mode='review'" in html
    assert "data-core-mode='compare'" in html
    assert "data-core-mode='midas'" in html
    assert "data-core-mode='all'" in html
    assert "viewer-role-presets-data" in html
    assert "Quick Outline" in html
    assert "viewer-quick-outline" in html
    assert "data-outline-target='viewer-interactive-3d'" in html
    assert "data-outline-target='viewer-baseline'" in html
    assert "data-outline-target='viewer-midas-load-combination'" in html
    assert "viewer-command-palette" in html
    assert "viewer-command-palette-data" in html
    assert "data-viewer-command-palette-open='true'" in html
    assert "Ctrl/Cmd+K" in html
    assert "section-heading section-heading--split" in html
    assert "[hidden] { display:none !important; }" in html
    assert "Foundation / Soil Link" in html
    assert "General FE Contact Matrix" in html
    assert "current-selected-member" in html
    assert "current-governing-row" in html
    assert "midas-section-representative" in html
    assert "load-pattern" in html
    assert "load-combination" in html
    assert "codecheck-row" in html
    assert "getViewerCommandPaletteRuntimeEntries" in html
    assert "openCurrentSelectedMemberObject" in html
    assert "openCurrentGoverningCodecheckObject" in html
    assert "openMidasSectionRepresentativeObject" in html
    assert "openMidasLoadPatternObject" in html
    assert "focusBaselineExactCodecheckRow" in html
    assert "viewer-mode-core" in html
    assert "viewer-interactive-3d" in html
    assert "viewer-baseline" in html
    assert "viewer-results-explorer" in html
    assert "Traceability" in html
    assert "general-fe/contact=" in html
    assert "refresh results explorer from already-generated phase1 artifacts" in html
    assert "NDTHA Response NPZ" in html
    assert "Archive and solver-control trace" in html
    assert "already-generated phase1 result reports + NDTHA response archive" in html
    assert "solver-control head unavailable in report" in html
    assert "solver-control history pass" in html
    assert "Open NDTHA Response NPZ" in html
    assert "step-series depth" in html
    assert "Geometry Crosswalk" in html
    assert "Full bridge crosswalk depth and aggregate" in html
    assert "full crosswalk depth" in html
    assert "generate_structural_optimization_visualization_viewer.py" in html
    assert "--committee-package-report" in html
    assert "Execution Manifest" in html
    assert "Release Gap JSON" in html
    assert "Commercial Workflow Breadth" in html
    assert "Workflow Breadth JSON" in html
    assert "Project Registry" in html
    assert "Batch Job Report" in html
    assert "workflow-breadth=checks=CHECK | construction_snapshots=9 | rail_actions=4 | design_traceability=87.5%" in html
    assert "Advanced Holdout Closeout" in html
    assert "Dynamic plastic-hinge refresh" in html
    assert "Raw wind-tunnel data mapping" in html
    assert "data-viewer-preset-key='interactive-3d'" in html
    assert "data-viewer-preset-key='baseline'" in html
    assert "data-viewer-preset-key='results-explorer'" in html
    assert "data-viewer-preset-key='changed-overlay'" in html
    assert "data-viewer-preset-key='story-zone'" in html
    assert "data-viewer-preset-key='midas-section-library'" in html
    assert "data-viewer-preset-key='midas-load-pattern'" in html
    assert "data-viewer-preset-key='midas-load-combination'" in html
    assert "viewer-analysis-gallery" in html
    assert "data-viewer-tier='advanced'" in html
    assert "gallery-preview" in html
    assert "ready_families=" in html
    assert "workspace=PASS" in html
    assert "ops_bundle=PASS" in html
    assert "portfolio=PASS" in html
    assert "Design & AI Case Catalog" in html
    assert "등록된 설계도와 AI 해석·최적화 데이터를 선택해서 봅니다." in html
    assert "기본은 핵심 케이스만 깔끔하게 보여줍니다." in html
    assert "case-catalog-select" in html
    assert "case-catalog-search" in html
    assert "catalog-filter-row" in html
    assert "catalog-filter-summary" in html
    assert "data-catalog-filter='featured'" in html
    assert "data-catalog-filter='secondary'" in html
    assert "data-catalog-filter='all'" in html
    assert "data-catalog-filter='3d'" in html
    assert "data-catalog-filter='midas-33'" in html
    assert "data-catalog-filter='support-source'" in html
    assert "data-catalog-filter='synthetic'" in html
    assert "data-catalog-filter='ai-data'" in html
    assert "data-catalog-filter='registered'" in html
    assert "data-catalog-filter='deep-artifacts'" in html
    assert "data-catalog-filter='verified-preview'" in html
    assert "data-catalog-filter='hint-preview'" in html
    assert "data-catalog-filter='raw-preview'" in html
    assert "data-catalog-filter='heuristic-preview'" in html
    assert "data-catalog-filter='crosscheck'" in html
    assert "data-catalog-filter='no-preview'" in html
    assert "data-catalog-filter='promote-next'" in html
    assert "data-catalog-group=" in html
    assert "data-catalog-visibility=" in html
    assert "data-preview-state=" in html
    assert "data-preview-bucket=" in html
    assert "data-case-family=" in html
    assert "data-has-crosscheck=" in html
    assert "data-upgrade-candidate=" in html
    assert "data-is-current=" in html
    assert "Featured 3D Cases" in html
    assert "MIDAS 33 Family" in html
    assert "OpenSees Detailed 3D" in html
    assert "Support-Source 3D" in html
    assert "OpenSees-derived Synthetic Compare" in html
    assert "data-catalog-filter='opensees'" in html
    assert "OPENSEES" in html
    assert "featured-family-group" in html
    assert "featured-family-summary-toggle" in html
    assert "featured-family-body" in html
    assert "featured-family-summary" in html
    assert "featured-family-pill" in html
    assert "featured-family-state-row" in html
    assert "featured-family-state-pill" in html
    assert "featured-family-open-label" in html
    assert "featured-family-open-icon" in html
    assert "featured-family-open-copy is-closed" in html
    assert "featured-family-open-copy is-open" in html
    assert "featured-family-grid" in html
    assert "catalog-summary-strip" in html
    assert "처음엔 이 3개만 보면 됩니다." in html
    assert "benchmark start" in html
    assert "executed 5-pack is ready" in html
    assert "AI OPSTOOL Direct 5-Pack Execution" in html
    assert "expert review" in html
    assert "external expert handoff is ready" in html
    assert "External Expert Mode" in html
    assert "Sheet-Style Drawing Package" in html
    assert "main gap" in html
    assert "data-featured-family='midas-33'" in html
    assert "data-featured-family='support-source'" in html
    assert "data-featured-family='synthetic'" in html
    assert "data-featured-family='opensees'" in html
    assert "full bridge pair" in html
    assert "synthetic compare" in html
    assert "same frame + shell delta" in html
    assert "cards hidden" in html
    assert "cards open" in html
    assert "summary first" in html
    support_slice = html.split("Support-Source 3D", 1)[1].split("OpenSees-derived Synthetic Compare", 1)[0]
    assert support_slice.index("Fcm Bridge Decoded Preview Baseline") < support_slice.index("Beam Archive Rhino Baseline")
    assert support_slice.index("Beam Archive Rhino Baseline") < support_slice.index("Beam Decoded Preview Baseline")
    assert "Key AI Reports" in html
    assert "Source Landing Pages" in html
    assert "readiness-kicker is-midas" in html
    assert "readiness-kicker is-opensees" in html
    assert "readiness-kicker is-support" in html
    assert "readiness-kicker is-synthetic" in html
    assert "is-recommended-card" in html
    assert "featured-recommended-kicker" in html
    assert "RECOMMENDED" in html
    assert "data-featured-recommended='true'" in html
    assert "featured-state-kicker" in html
    assert "VERIFIED" in html
    assert "EXTERNAL BRIDGE" in html
    assert "HINT-GUIDED" in html
    assert "case-chip-kicker-row" in html
    assert "case-chip-kicker" in html
    assert "MIDAS 33" in html
    assert "SUPPORT SOURCE" in html
    assert "SYNTHETIC" in html
    assert "[MIDAS 33] MIDAS 33 Release Compare" in html
    assert "Binary Readiness Board" in html
    assert "Commercial Parity Board" in html
    assert "Server-Style Ops Summary" in html
    assert "Family-Track Commercialization Breadth" in html
    assert "P0/P1 Commercialization Depth" in html
    assert "Material / constitutive depth" in html
    assert "Load / combination depth" in html
    assert "Advanced SSI / interaction depth" in html
    assert "Wind / raw mapping depth" in html
    assert "p0=3/3 | p1=2/2" in html
    assert "session=native-authoring-sample-tower::solver-session" in html
    assert "Sample Tower" in html
    assert "Steel Braced Frame" in html
    assert "families=" in html
    assert "ready_families=" in html
    assert "portfolio=" in html
    assert "native_authoring_ops_bundle.json" in html
    assert "native_authoring_solver_session.json" in html
    assert "Topology Recovery Ladder" in html
    assert "Megastructure Expansion Board" in html
    assert "Native Authoring / Solver Evidence Lane" in html
    assert "Detailed Megastructure Geometry" in html
    assert (
        f"viewer_ready_family={int((payload['benchmark_expansion_summary']['detailed_geometry_summary'] or {}).get('viewer_ready_family_count', 0) or 0)}"
        in html
    )
    assert "local_bridge_pending=0" in html
    assert "OPSTOOL 606m Detailed Direct Family" in html
    assert "OPSTOOL 606m OpenSees-derived Synthetic Compare" in html
    assert "OpenSees SCBF Detailed Local Family" in html
    assert "OpenSees SCBF Family / Detail Compare Surface" in html
    assert "OpenSees SCBF16B Shell-Beam Mix Baseline" in html
    assert "OpenSees SCBF16B Baseline" in html
    assert "family compare" in html
    assert "main synthetic compare" in html
    assert (
        f"detail_compare={int((payload['benchmark_expansion_summary']['detailed_geometry_summary'] or {}).get('compare_surface_count', 0) or 0)}"
        in html
    )
    assert "recommended next 5 = 1 direct model + 4 authority/measured tracks" in html
    assert "Direct Model Green Lane" in html or "direct model curated lane" in html
    assert "AUTHORING READY" in html
    assert "Authority / Measured Green Now" in html
    assert "Authority / Measured Yellow Next-Ingest" in html
    assert "PEER Blind Prediction Public Input" in html
    assert "public input ready" in html
    assert "PEER Blind Prediction Compare Lane" in html
    assert "benchmark drawings" in html
    assert "PEER Blind Prediction Sample Compare Lane" in html
    assert "synthetic sample landing closes the compare path end-to-end" in html
    assert "Benchmark AI Drawings" in html
    assert "materialized 5-pack gates passed" in html
    assert "EXECUTED 5-PACK" in html
    assert "executed=1" in html
    assert "executed_cases=5" in html
    assert "benchmark_kpi=PASS" in html
    assert "noise_gate=PASS" in html
    assert "featured benchmark lane으로 승격" in html
    assert "AI OPSTOOL Direct 5-Pack Execution" in html
    assert "items=atwood, tpu wind" in html
    assert "items=kw51, usgs nsmp" in html
    assert "BENCHMARK" in html
    assert "GREEN DIRECT" in html
    assert "GREEN NOW" in html
    assert "YELLOW NEXT-INGEST" in html
    assert "ready for featured viewer surfacing" in html
    assert "holdout worth surfacing after next ingest" in html
    assert "Selected 5-Pack Cases" in opstool_5pack_execution_html
    assert "execution_band=benchmark_pass_noise_pass" in opstool_5pack_execution_html
    assert "opstool_606m_megatall_model-00020" in opstool_5pack_execution_html
    assert "ai_opstool_direct_case_00020.html" in opstool_5pack_execution_html
    assert "ai_opstool_direct_case_00009.html" in opstool_5pack_execution_html
    assert "benchmark gate=PASS" in opstool_5pack_execution_html
    assert "noise gate=PASS" in opstool_5pack_execution_html
    assert "support mode=materialized 5-pack gates passed" in opstool_5pack_execution_html
    assert "delivery boundary=direct benchmark materialization / no synthetic compare overlay" in opstool_5pack_execution_html
    assert "evidence model=direct_megastructure_5pack_materialization" in opstool_5pack_execution_html
    assert "reason KPI=benchmark_kpi=PASS | noise_gate=PASS" in opstool_5pack_execution_html
    assert "Family / Detail Compare Reading" in opensees_compare_html
    assert "OpenSees family/detail compare surface" in opensees_compare_html
    assert "optimization compare는 아직 아닙니다" in opensees_compare_html
    assert "Truth Boundary" in opensees_compare_html
    assert "OpenSees-derived synthetic compare surface" in opensees_compare_html
    assert "open OpenSees-derived synthetic compare" in opensees_compare_html
    assert "shared frame 위에 추가된 shell-only slab panel" in opensees_compare_html
    assert "story filter와 shell-only panel 선택을 동기화해 같은 frame 위에 어떤 slab panel이 추가됐는지 읽습니다." in opensees_compare_html
    assert "Shell-Only Panel List" in opensees_compare_html
    assert "Slab Delta by Story" in opensees_compare_html
    assert "story_groups=5" in opensees_compare_html
    assert "story_path=S04 -&gt; S05 -&gt; S09 -&gt; S10 -&gt; S16" in opensees_compare_html
    assert "highlights=S04, S05, S09, S10, S16" in opensees_compare_html
    assert "Read low to high: S04 starts with 1 panel, S05 continues with 1 panel, S09 continues with 1 panel, S10 continues with 1 panel, S16 finishes with 1 panel." in opensees_compare_html
    assert "Orange stack markers show only shell-only slab additions inside this family/detail compare surface. They do not imply optimization ranking or candidate scoring." in opensees_compare_html
    assert "Story mini-highlights show the shell 5 height slots directly" in opensees_compare_html
    assert "story highlights" in opensees_compare_html
    assert "Story mini-highlights" in opensees_compare_html
    assert "shell-story-mini-strip" in opensees_compare_html
    assert "shell-story-mini-chip" in opensees_compare_html
    assert "shell-story-mini-chip-track" in opensees_compare_html
    assert "Each chip marks where a shell slab panel was added by elevation/story. Family/detail compare only, not optimization ranking." in opensees_compare_html
    assert "S04 adds 1 shell panel at this story height" in opensees_compare_html
    assert "S16 adds 1 shell panel at this story height" in opensees_compare_html
    assert "lowest shell delta level | height slot 1 / 5 on the shell-only elevation path" in opensees_compare_html
    assert "highest shell delta level | height slot 5 / 5 on the shell-only elevation path" in opensees_compare_html
    assert "Mini elevation stack" in opensees_compare_html
    assert "Top to bottom: highest shell-only slab story down to entry story." in opensees_compare_html
    assert "shell-story-stack" in opensees_compare_html
    assert "shell-story-floor is-top" in opensees_compare_html
    assert "shell-story-floor is-entry" in opensees_compare_html
    assert "shell-story-marker" in opensees_compare_html
    assert "entry story" in opensees_compare_html
    assert "mid story" in opensees_compare_html
    assert "top shell story" in opensees_compare_html
    assert "1 / 5 shell-only panels" in opensees_compare_html
    assert "20% of shell-only slab delta" in opensees_compare_html
    assert "shell-story-summary-note-highlight" in opensees_compare_html
    assert "shell-story-inline-highlight" in opensees_compare_html
    assert "shell-story-summary-note-height" in opensees_compare_html
    assert "shell-story-inline-height" in opensees_compare_html
    assert "ids=#990001" in opensees_compare_html
    assert "open shell-beam mix baseline next" in opensees_compare_html
    assert "#990001" in opensees_compare_html
    assert "#990005" in opensees_compare_html
    assert "unique_nodes=4 | groups=1" in opensees_compare_html
    assert "S04 | panels=1 | groups=1 | 20% of shell-only slab delta" in opensees_compare_html
    assert "group=S04:intermediate:slab" in opensees_compare_html
    assert "shell-beam mix=5" in opensees_compare_html
    assert "frame_brace" in opensees_compare_html
    assert "diff=+5 shell slab panels" in opensees_compare_html
    assert "surface truth=OpenSees-derived synthetic compare | scope=synthetic optimization compare" in opstool_synthetic_compare_html
    assert "optimization compare wording은 이 opstool 606m synthetic lane에만 씁니다" in opstool_synthetic_compare_html
    assert "OPSTOOL 606m OpenSees-derived Synthetic Compare" in opstool_synthetic_compare_html
    assert "Synthetic Optimization Compare Review" in opstool_synthetic_compare_html
    assert "before truth=OpenSees-derived synthetic baseline" in opstool_synthetic_compare_html
    assert "after truth=AI optimization overlay" in opstool_synthetic_compare_html
    assert "changed rows=24" in opstool_synthetic_compare_html
    assert "direct patch actions=24" in opstool_synthetic_compare_html
    assert "cost proxy delta=-3417.045" in opstool_synthetic_compare_html
    assert "constructability delta=-0.721" in opstool_synthetic_compare_html
    assert "max after D/C=0.965" in opstool_synthetic_compare_html
    assert "patch mix=perimeter_frame=9, beam_section=8, connection_detailing=7" in opstool_synthetic_compare_html
    assert "support mode=synthetic benchmark overlay" in opstool_synthetic_compare_html
    assert "evidence model=synthetic_ndtha_story_family_overlay" in opstool_synthetic_compare_html
    assert "synthetic benchmark overlay / no release patch delivery" in opstool_synthetic_compare_html
    assert "Story-Band Impact Table" in opstool_synthetic_compare_html
    assert "Story-band impact table" in opstool_synthetic_compare_html
    assert "story-band impact=top_story=S24 | costΔ=-152.993 | slots=24" in opstool_synthetic_compare_html
    assert "story path=S01 -&gt; S02 -&gt; S03" in opstool_synthetic_compare_html
    assert "Click a row to jump the interactive 3D viewer to the same story height band." in opstool_synthetic_compare_html
    assert "Row click stays on this page and focuses the 3D viewer instead of navigating away." in opstool_synthetic_compare_html
    assert "data-synthetic-story-band-focus='true'" in opstool_synthetic_compare_html
    assert "data-story-band-label='S24'" in opstool_synthetic_compare_html
    assert "<th>Height slot</th><th>Story</th><th>Rows</th><th>Groups</th><th>Cost delta</th>" in opstool_synthetic_compare_html
    assert "Height slot" in opstool_synthetic_compare_html
    assert "data-story-band-jump='true'" in opstool_synthetic_compare_html
    assert "focusInteractive3DStoryBand" in opstool_synthetic_compare_html
    assert "<td>S24<div class='synthetic-compare-story-band-subnote'>same height jump ready</div><div class='synthetic-compare-story-band-subnote'>interactive 3D focus jump</div></td>" in opstool_synthetic_compare_html
    assert "interactive 3D focus jump" in opstool_synthetic_compare_html
    assert "<td>core</td>" in opstool_synthetic_compare_html
    assert "<td>column</td>" in opstool_synthetic_compare_html
    for baseline_html in (opensees_frame_baseline_html, opensees_shell_baseline_html):
        assert "viewer-page is-opensees-planar-baseline" in baseline_html
        assert "OpenSees Baseline Reading Guide" in baseline_html
        assert "Interactive XZ Frame Viewer" in baseline_html
        assert "baseline-only x/z frame" in baseline_html
        assert "Baseline Elevation XZ" in baseline_html
        assert "Collapsed Plan XY" in baseline_html
        assert "planar_xz=y=0 baseline only" in baseline_html
        assert "planar x/z frame | elevation-first auto camera | y=0 collapsed plan" in baseline_html
        assert "Changed Family Filter" not in baseline_html
        assert "Open baseline+after 3D" not in baseline_html
        assert "baseline-only OpenSees frame viewer" in baseline_html
    assert "Benchmark Role Snapshot" in opstool_5pack_case_html
    assert "before/after compare viewer가 아니라" in opstool_5pack_case_html
    assert "role=outrigger | seismic | test" in opstool_5pack_case_html
    assert "base_shear_hf_kN" in opstool_5pack_case_html
    assert "support mode=materialized 5-pack gates passed" in opstool_5pack_case_html
    assert "delivery boundary=direct benchmark materialization / no synthetic compare overlay" in opstool_5pack_case_html
    assert "evidence model=direct_megastructure_5pack_materialization" in opstool_5pack_case_html
    assert "reason KPI=drift_hf=" in opstool_5pack_case_html
    assert "Batch Story / Height Drilldown" in opstool_5pack_execution_html
    assert "raw batch height payload가 아니라" in opstool_5pack_execution_html
    assert "handoff truth=synthetic compare handoff / no raw batch height payload" in opstool_5pack_execution_html
    assert "compare vocabulary=story band / height slot / handoff truth" in opstool_5pack_execution_html
    assert "open same height in synthetic compare" in opstool_5pack_execution_html
    assert "slot 24/24" in opstool_5pack_execution_html
    assert "data-batch-case-target='row'" in opstool_5pack_execution_html
    assert "data-batch-case-target='pill'" in opstool_5pack_execution_html
    assert "synthetic compare handoff ready" in opstool_5pack_execution_html
    assert "story path=S01 -&gt; S02 -&gt; S03" in opstool_5pack_execution_html
    assert "surface truth=OpenSees-derived synthetic compare" in opstool_5pack_case_html
    assert "opstool_606m_outrigger_ai_compare.html?story=S24&amp;focus=interactive3d&amp;source=direct_5pack_story_handoff" in opstool_5pack_case_html
    assert "same story height band를 직접 검토해야 하면 synthetic compare 3D로 넘기는 것이 맞고" in opstool_5pack_execution_html
    assert "현재 page는 raw case height overlay를 직접 담지 않으므로" in opstool_5pack_case_html
    assert "Story-Band / Height Drilldown" in opstool_5pack_execution_html
    assert "story-band drilldown=synthetic compare linked" in opstool_5pack_case_html
    assert "height drilldown=S01 -&gt; S02 -&gt; S03" in opstool_5pack_case_html
    assert "story-band impact=top_story=S24 | costΔ=-152.993 | slots=24" in opstool_5pack_execution_html
    assert "MIDAS building bias를 가장 빨리 줄이는 green measured track." in html
    assert "Authority lane에서 wind diversity를 바로 늘리는 green track." in html
    assert "Refresh Atwood cases and pin KPI stub again." in html
    assert "Keep execution artifacts and tighten viewer wording." in html
    assert "direct_model=yes | optimization_ready=yes" in html
    assert "changed_rows=24 | changed_groups=24 | costΔ=-3417.045 | max_dcr_after=0.965" in html
    assert "patch mix=perimeter_frame=9, beam_section=8, connection_detailing=7 | support=synthetic benchmark overlay" in html
    assert "boundary=synthetic benchmark overlay / no release patch delivery" in html
    assert "opstool 606m megatall model" in html
    assert "zenodo atwood highrise shm 2025" in html
    assert "zenodo kw51 railway bridge monitoring 2025" in html
    assert "usgs nsmp structural arrays" in html
    assert "tpu highrise wind pressure and force" in html
    assert "registered / green benchmark lane" in html
    assert "registered / yellow next-ingest lane" in html
    assert "megastructure_tpu_highrise_wind_pressure_and_force.html" in html
    assert "Position Snapshot" in html
    assert "progress=3/4 | next_experiment=beam_node_xyz_slot_recovery" in html
    assert "exact decode path" in html
    assert "decode_progress=0/3" in html
    assert "node xyz" in html
    assert "elem connectivity" in html
    assert "gate recheck" in html
    assert "Heuristic Commercial Parity Estimate" in html
    assert "Full Geometry Bridge" in html
    assert "Viewer-Ready Verified Preview" in html
    assert "Hint-Guided Preview" in html
    assert "parity anchor=" in html
    assert "score range=" in html
    assert "current parity" in html
    assert "3D review / inspection" in html
    assert "external expert package=" in html
    assert "optimized_drawing_expert_review.html" in html
    assert "optimized drawing expert review" in html
    assert "optimized drawing review" in html
    assert "permit / committee 제출용 sheet-style drawing package" in html
    assert "permit / committee PDF issue 기준" in html
    assert "Representative Cases" in html
    assert "near commercial review-grade" in html
    assert "diagnostic candidate" in html
    assert "readiness-title-link" in html
    assert "readiness-link-pill" in html
    assert "promote_next=" in html
    assert "current tier" in html
    assert (
        "raw preview + cross-check" in html
        or "hint preview + cross-check" in html
        or "raw preview only" in html
        or "hint preview only" in html
        or "verified preview ready" in html
    )
    assert "gallery-head" in html
    assert "MIDAS 33 Case Switch" in html
    assert "midas 33 family" in html
    assert "여기는 <strong>AI가 실제로 바꾼 부재만</strong> 따로 보는 화면입니다." in html
    assert "overlay-reading-order" in html
    assert "색 선부터 보면 AI가 바꾼 위치가 바로 보입니다." in html
    assert "overlay-mini-guide" in html
    assert "overlay-mini-card" in html
    assert ".overlay-toolbar { display:grid; grid-template-columns:1fr auto; gap:14px; align-items:start; margin-top:14px; position:relative; z-index:4; }" in html
    assert ".filter-chip { appearance:none;" in html
    assert "pointer-events:auto;" in html
    assert "transition:transform .14s ease, box-shadow .18s ease" in html
    assert ".filter-chip.is-feedback { transform:translateY(-1px); box-shadow:0 10px 18px rgba(15,106,115,.14); }" in html
    assert ".overlay-count.is-live-update { animation:overlayCountPulse .52s ease-out 1; }" in html
    assert ".overlay-count.is-delta-down { color:#1f7a4f; }" in html
    assert ".overlay-count.is-delta-up { color:#b76a11; }" in html
    assert "target.closest('[data-filter-group=\"family\"]')" in html
    assert "target.closest('[data-filter-group=\"member-type\"]')" in html
    assert "overlay-filter-feedback" in html
    assert "filters=family:all | type:all | last=ready" in html
    assert "overlay-family-filter-count" in html
    assert "overlay-member-type-filter-count" in html
    assert "0 active" in html
    assert "| delta=0 |" in html
    assert "const reorderFilterChips = (buttons) => {" in html
    assert "button.classList.contains('is-active')" in html
    assert "wall thickness" in html
    assert "Before vs After" in html
    assert "Click To Inspect" in html
    assert "Filters" in html
    assert "NOT TO SCALE" in html
    assert "회색은 원래 위치, 색 선은 AI가 바꾼 뒤 위치를 덧그린 강조선입니다." in html
    assert "여기 선 두께는 실제 부재 두께가 아니라 보기 쉽게 겹쳐 그린 표시" in html
    assert "부재를 클릭하면 아래 `Selected Member` 패널에서 family, 층, 영향이 같이 열립니다." in html
    assert "family로 변경 종류를 좁히고, member type으로 beam/wall/slab/column만 따로 볼 수 있습니다." in html
    assert "변경 종류 색" in html
    assert "부재 종류 quick key" in html
    assert "실제 단면 / 두께 해석" in html
    assert (
        "overlay는 위치 강조용이고 not-to-scale입니다." in html
        or "이 viewer에서 보이는 색 선은 위치 이동이 아니라" in html
    )
    assert "beam은 보통 수평 골조입니다." in html
    assert "wall은 코어·전단벽 계열입니다." in html
    assert "쉽게 보면 `live_types`는 실제 최적화 대상 전체" in html
    assert "가장 먼저 보는 메인 뷰입니다. 위에서 본 변경 위치를 빠르게 읽습니다." in html
    assert "한 장으로 공간감을 보는 정적 3D 요약 뷰입니다." in html
    assert "무엇이 바뀌었는지" in html
    assert "direct patch" in html
    assert "audit packets" in html
    assert "queue pending" in html
    assert "blocked tasks" in html
    assert "measured chain" in html
    assert "delivery boundary=direct_patch=beam=1 | sidecar=n/a" in html
    assert "MIDAS Section Library" in html
    assert "viewer fallback derived" in html
    assert "coverage=4/4 used" in html
    assert "rep links=4/4 linked" in html
    assert "representative links" in html
    assert "section 13 · CFT600X600X20" in html
    assert "same section 1 baseline members" in html
    assert "1/1 representative linked" in html
    assert "open representative member · 1 of 1" in html
    assert "data-midas-section-focus-id='13'" in html
    assert "data-midas-section-member-count='1'" in html
    assert "focusMidasSectionRepresentative" in html
    assert "같은 section ${sectionCountLabel}를 함께 강조합니다." in html
    assert "data-baseline-static-summary-role='metrics'" in html
    assert "midasSectionFocusMemberCount" in html
    assert "same section ${midasSectionFocusMemberCount} baseline members" in html
    assert "const getActiveMidasSectionFocusMetrics = (row) => {" in html
    assert "MIDAS Load Pattern Library" in html
    assert "patterns=3" in html
    assert "primitives=3" in html
    assert "combinations=2" in html
    assert "primitive mix" in html
    assert "design situation mix" in html
    assert "semantic status mix" in html
    assert "DEAD · permanent_gravity" in html
    assert "LIVE · variable_imposed" in html
    assert "WINDX · lateral_wind" in html
    assert "global gravity | rows=1" in html
    assert "nodes=2 | rows=1" in html
    assert "elements=2 | rows=1" in html
    assert "point_load=1, self_weight=1, surface_pressure=1" in html
    assert "MIDAS Load Combination Browser" in html
    assert "Combination graph mini-map" in html
    assert "editor seed=viewer fallback derived" in html
    assert "seed contract=0.1.0" in html
    assert "case nodes=3" in html
    assert "combo nodes=2" in html
    assert "stages=3" in html
    assert "midas-load-graph-card" in html
    assert "midas-load-graph-quick-grid" in html
    assert "midas-load-graph-node-title" in html
    assert "midas-load-graph-edge case_factor" in html
    assert "data-midas-load-combination-focus='true'" in html
    assert "data-midas-load-pattern-focus='true'" in html
    assert "case는 왼쪽, nested combo depth는 오른쪽으로 밀어 두었습니다." in html
    assert "bound=2, derived=1" in html
    assert "focus scope: story=all stories (4) | category=all categories | target members=4 | category mix=beam=1, column=1, slab=1, wall=1" in html
    assert "focus scope: story=S04 | category=beam | target members=1 | category mix=beam=2" in html
    assert "focus scope: story=S01, S02 | category=slab, wall | target members=2 | category mix=slab=1, wall=1" in html
    assert "data-midas-load-pattern-focus='true'" in html
    assert "open load focus · all stories (4) | all categories" in html
    assert "open load focus · S04 | beam" in html
    assert "open load focus · S01, S02 | slab, wall" in html
    assert "results sync: Envelope Explorer · Final drift | serviceability / gravity lens로 final drift를 먼저 맞춥니다." in html
    assert "data-midas-load-pattern-representative-member='202'" in html
    assert "data-midas-load-pattern-results-label='Final drift'" in html
    assert "MIDAS Load Combination Browser" in html
    assert "combos=2" in html
    assert "graph=5 nodes / 4 edges" in html
    assert "max depth=2" in html
    assert "limit state mix" in html
    assert "expansion mode mix" in html
    assert "leaf case union" in html
    assert "ENV1 · service / ENV" in html
    assert "ULS1 · strength / GEN" in html
    assert "expanded factors: DEAD=1.20, LIVE=1.60, WINDX=0.70" in html
    assert "design mix: lateral_wind=1, permanent_gravity=1, variable_imposed=1 | referenced combos: ULS1" in html
    assert "design mix: lateral_wind=1, permanent_gravity=1, variable_imposed=1 | referenced combos: direct cases only" in html
    assert "results sync: Time-History Viewer · Displacement u | lateral wind scope가 포함되어 response trace를 먼저 맞춥니다." in html
    assert "open combination focus · DEAD, LIVE, WINDX" in html
    assert "midas-load-graph-quick-button" in html
    assert "code-check top row:" in html
    assert "Geometry bridge" in html
    assert "Code-Check Drilldown" in html
    assert "midas-load-codecheck-data" in html
    assert "Code-check review table" in html
    assert "Row detail" in html
    assert "Member inventory" in html
    assert "Clause provenance" in html
    assert "Clause drilldown" in html
    assert "data-midas-load-codecheck-role='clause-filter'" in html
    assert "data-midas-load-codecheck-role='reviewer-appendix'" in html
    assert "Reviewer appendix surface" in html
    assert "Hazard filter" in html
    assert "Rule family filter" in html
    assert "Export-aligned subset" in html
    assert "subset key=" in html
    assert "combo subset csv" in html
    assert "hazard subset csv" in html
    assert "rule subset csv" in html
    assert "current slice csv" in html
    assert "hazard/rule family appendix export와 같은 slice를 씁니다." in html
    assert "midas-load-codecheck-clause-chip" in html
    assert "data-midas-load-codecheck-hazard" in html
    assert "data-midas-load-codecheck-rule-family" in html
    assert "getMidasLoadCodecheckSubsetHref" in html
    assert "combinationName: String(initialDeepLinkParams.get('combination') || initialDeepLinkParams.get('combination_name') || '').trim()," in html
    assert "rowIndex: String(initialDeepLinkParams.get('row') || initialDeepLinkParams.get('row_index') || '').trim()," in html
    assert "clauseLabel: String(initialDeepLinkParams.get('clause') || initialDeepLinkParams.get('clause_label') || '').trim()," in html
    assert "hazardLabel: String(initialDeepLinkParams.get('hazard') || initialDeepLinkParams.get('hazard_type') || '').trim()," in html
    assert "ruleFamilyLabel: String(initialDeepLinkParams.get('rule_family') || initialDeepLinkParams.get('ruleFamily') || '').trim()," in html
    assert "rowRef: String(initialDeepLinkParams.get('row_ref') || '').trim()," in html
    assert "memberId: String(initialDeepLinkParams.get('member_id') || '').trim()," in html
    assert "memberIds: parsePipeTokenList(initialDeepLinkParams.get('member_set') || '').map((token) => String(token || '').trim()).filter(Boolean)," in html
    assert "baselineFocusMemberId: String(" in html
    assert "subsetCsv: String(initialDeepLinkParams.get('subset_csv') || '').trim()," in html
    assert "const memberIds = parsePipeTokenList(stored.memberIds || stored.memberSet || stored.member_ids || '').map((value) => String(value || '').trim()).filter(Boolean);" in html
    assert "const deepLinkCombination = String(initialViewerDeepLink.combinationName || '');" in html
    assert "const rawDeepLinkRowIndex = String(initialViewerDeepLink.rowIndex || '').trim();" in html
    assert "const hasDeepLinkRowIndex = rawDeepLinkRowIndex !== '' && Number.isFinite(Number(rawDeepLinkRowIndex));" in html
    assert "const deepLinkRowRef = String(initialViewerDeepLink.rowRef || '');" in html
    assert "setOrDeleteViewerQueryParam(params, 'member_set', memberIds.join('|'));" in html
    assert "memberSet: memberIds," in html
    assert "selectionSetCount: memberIds.length," in html
    assert "preferredMemberIds: deepLinkMemberIds," in html
    assert "restoreMemberContext: isAnyRowProvenanceSource," in html
    assert "panel-zone exact row jump" in html
    assert "row-provenance:panel-zone-context" in html
    assert "midas_kds_row_provenance_subsets" in html
    assert "Clause/member appendix와 같은 provenance rows를 hazard / rule family 기준으로 바로 좁혀서 읽습니다." in html
    assert "data-midas-load-combination-codecheck-rows=" in html
    assert "data-midas-load-combination-recovery-mode=" in html
    assert "Top check는" in html
    assert "data-midas-load-combination-focus='true'" in html
    assert "data-midas-load-combination-results-card='time-history'" in html
    assert "data-midas-load-combination-results-label='Displacement u'" in html
    assert "data-midas-load-combination-codecheck-top='" in html
    assert "updateMidasLoadCodecheckSelection" in html
    assert "setMidasLoadCodecheckClauseFilter" in html
    assert "setMidasLoadCodecheckHazardFilter" in html
    assert "setMidasLoadCodecheckRuleFamilyFilter" in html
    assert "buildMidasLoadCodecheckSubsetSummaryHtml" in html
    assert "buildMidasLoadCodecheckRowRef" in html
    assert "matchMidasLoadCodecheckEntry" in html
    assert "selection set=" in html
    assert "selection-set members" in html
    assert "is-selection-set-match" in html
    assert "selection match=" in html
    assert "Selection-set review surface" in html
    assert "data-midas-load-codecheck-detail-block=\"selection-set\"" in html
    assert "selection-set:row:" in html
    assert "Selection-set compare console" in html
    assert "Selection-set side-by-side matrix" in html
    assert "results-selection-set-compare-shell" in html
    assert "results-selection-set-compare-summary" in html
    assert "results-selection-set-compare-console" in html
    assert "results-selection-set-matrix-wrap" in html
    assert "results-selection-set-matrix-head-member" in html
    assert "results-selection-set-matrix-cell" in html
    assert "results-selection-set-member-matrix" in html
    assert "results-selection-set-member-card" in html
    assert "results-selection-set-member-console" in html
    assert "results-selection-set-member-console-item" in html
    assert "selection-set-compare:member:" in html
    assert "selection-set-compare:matrix-review" in html
    assert "Compare summary" in html
    assert "Member status console" in html
    assert "Per-member detail console" in html
    assert "Missing diagnostics" in html
    assert "Suggested actions" in html
    assert "Missing reason" in html
    assert "Suggested action" in html
    assert "Writeback review" in html
    assert "Writeback action" in html
    assert "Writeback status" in html
    assert "Writeback next step" in html
    assert "Writeback diff row matrix" in html
    assert "open writeback diff row review" in html
    assert "open writeback-linked member review" in html
    assert "Actual regenerated artifact compare" in html
    assert "open regenerated compare review" in html
    assert "open regenerated compare JSON" in html
    assert "before / after review from the same optimized member overlay" in html
    assert "results-benchmark-context-banner" in html
    assert "benchmark optimization review matrix에서 전달된 story / zone focus입니다." in html
    assert "row-provenance:benchmark-context" in html
    assert "Writeback Diff Review" in html
    assert "Open standalone diff review" in html
    assert "Row density" in html
    assert "Governing D/C spread" in html
    assert "Member profile" in html
    assert "Case / bridge state" in html
    assert "selection-set compare console keeps the same result sample and current filtered combo slice aligned per member." in html
    assert "selected members currently missing from this slice" in html
    assert "Bridge / aliases" in html
    assert "Next review step" in html
    assert "member review" in html
    assert "Governing D/C" in html
    assert "open governing row" in html
    assert "selection-set compare" in html
    assert "current slice csv" in html
    assert "Next:" in html
    assert "syncMidasLoadCodecheckFromBaselineSelection" in html
    assert "focusMidasLoadCodecheckSelection" in html
    assert "현재 clause filter는 ${clauseFilterLabel}입니다." in html
    assert "initializeMidasLoadCodecheckDrilldown" in html
    assert "focus exact baseline member" in html or "exact geometry bridge unavailable" in html
    assert "data-midas-load-codecheck-open-row=\"true\"" in html
    assert "jump back to combo/code-check row" in html
    assert "review keys=" in html
    assert "bridge_member_inventory_source_label" in html
    assert "const focusMidasLoadPattern = (button) => {" in html
    assert "const focusMidasLoadCombination = (button) => {" in html
    assert "const applyMidasLoadScopeFocus = ({" in html
    assert "const setResultsExplorerCardSelection = (cardKey = 'envelope', seriesIndex = 0, options = {}) => {" in html
    assert "const focusResultsExplorerCard = (cardKey = 'envelope', seriesIndex = 0, helpText = '') => setResultsExplorerCardSelection(" in html
    assert "Results Explorer는 ${recommendedResultsCard} card · ${recommendedResultsLabel}로 함께 맞췄습니다." in html
    assert "findBaselineNodeByFocusHints" in html
    assert "MIDAS ${scopeLabel} (${contextLabel}) focus를 열었습니다." in html
    assert "Selected Member detail card에 함께 고정됩니다." in html
    assert "같은 section 묶음 강조가 유지되므로 representative 1개만 보지 말고 related member까지 같이 따라가면" in html
    assert "Jump to representative member" in html
    assert "interactive-3d-detail-actions" in html
    assert "interactive-3d-detail-representative-jump" in html
    assert "interactive-3d-detail-codecheck-jump" in html
    assert "Open provenance/code-check row" in html
    assert "interactive-3d-detail-related-prev" in html
    assert "interactive-3d-detail-related-next" in html
    assert "interactive-3d-detail-action-counter" in html
    assert "interactive-3d-detail-action-breadcrumb" in html
    assert "interactive-3d-detail-story-prev" in html
    assert "interactive-3d-detail-story-current" in html
    assert "interactive-3d-detail-story-next" in html
    assert "interactive-3d-detail-action-note" in html
    assert "midasSectionFocusRepresentativeMemberId" in html
    assert "sectionFocusRepresentativeMember: normalizedMemberId" in html
    assert "필요하면 Jump to representative member로 대표 기준 부재로 바로 돌아갈 수 있습니다." in html
    assert "same-section highlight remains active after jump." in html
    assert "대표 부재로 이동해도 ${sectionMetrics.memberCountLabel} 강조가 그대로 유지되며, ${sectionMetrics.relatedLabel}도 함께 따라갑니다. Previous/Next related member와 prev/current/next story chip으로 같은 section 묶음을 연속 탐색할 수 있습니다." in html
    assert "Open provenance/code-check row로 바로 이어서 볼 수 있습니다." in html
    assert "Open provenance/code-check row로 review table과 row detail을 바로 이어서 볼 수 있습니다." in html
    assert "Previous related member" in html
    assert "Next related member" in html
    assert "Related member ${sectionNavState.currentPositionLabel}" in html
    assert "Prev story ${previousStory}" in html
    assert "Current story ${currentStory}" in html
    assert "Next story ${nextStory}" in html
    assert "현재 ${sectionNavState.currentPositionLabel} 위치입니다." in html
    assert "Previous/Next related member와 prev/current/next story chip으로 같은 section 묶음을 연속 탐색할 수 있습니다." in html
    assert "const getSectionFocusNavigationEntries = () => {" in html
    assert "const getSectionFocusNavigationState = (row) => {" in html
    assert "const focusMidasSectionRelatedMember = (direction = 1) => {" in html
    assert "const focusMidasSectionStoryChip = (kind = 'current') => {" in html
    assert "sectionMetrics.sectionLabel" in html
    assert "sectionMetrics.representativeLabel" in html
    assert "before -> after 수치가 아니라 baseline member reference입니다. ${sectionMetrics.memberCountLabel}, ${sectionMetrics.representativeLabel}, ${sectionMetrics.relatedLabel}가 함께 유지됩니다." in html
    assert "family mix" in html
    assert "shape mix" in html
    assert "Overflow / unstable regime" in html
    assert "solver instability suspicion" in html
    assert "viewer-expert-review-route" in html
    assert "External Expert Review Route" in html
    assert "Open External Expert Mode" in html
    assert "Open Sheet-Style Drawing Package" in html
    assert "Expert Validation Dashboard" in html
    assert "Validation Boundary JSON" in html
    assert "recommended route=dashboard -&gt; drawing package -&gt; interactive viewer -&gt; boundary" in html
    assert "validation language=outside review / sign-off / sheet check" in html
    assert "Presentation One-Page" in html
    assert "FigJam Wireframe" in html
    assert "Type Alignment Mismatch Report" in html
    assert payload["member_overlay"]["family_legend_rows"] == [
        {"label": "rebar", "count": 1, "color": "#1f7a4f"},
        {"label": "wall_thickness", "count": 1, "color": "#b35c2e"},
    ]
    assert payload["member_overlay"]["member_type_legend_rows"] == [
        {"label": "beam", "count": 1, "color": "#6f8fb8"},
        {"label": "wall", "count": 1, "color": "#8d7663"},
    ]
    assert payload["topology_recovery_summary"]["label"] == "Topology Recovery Ladder"
    assert payload["topology_recovery_summary"]["tiers"]
    assert payload["topology_recovery_summary"]["tiers"][0]["parity_anchor_label"]
    assert payload["case_catalog_summary"]["featured_entry_count"] > 0
    assert payload["case_catalog_summary"]["secondary_entry_count"] > 0
    assert payload["case_catalog_summary"]["deep_artifact_count"] > 0
    assert "Optimization Change Landscape" in html
    assert "Optimized Member Coverage Truth" in html
    assert "wall/column이 실제 최적화 대상이면 여기서 먼저 드러나고" in html
    assert "type_alignment=2/2 aligned" in html
    assert "type_mismatch=0" in html
    assert "semantic vs geometry member type mismatch detail=none" in html
    assert "mismatch-grid" in html
    assert source_beam_payload["entry"]["metadata"]["local_archive_cached"] is True
    assert source_beam_payload["entry"]["metadata"]["local_archive_member_count"] >= 1
    assert source_beam_payload["entry"]["metadata"]["binary_adapter_manifest_ready"] is True
    assert source_beam_payload["entry"]["metadata"]["binary_decoded_inventory_contract_ready"] is True
    assert source_beam_payload["entry"]["metadata"]["binary_decoded_inventory_ready"] is False
    assert source_beam_payload["entry"]["metadata"]["binary_primary_member_probe"]["magic_ascii"] == "MCVL"
    assert source_beam_payload["entry"]["metadata"]["binary_primary_probe_entry_id"] == "binary_probe_midas_support_beam_archive"
    assert source_beam_payload["entry"]["metadata"]["binary_archive_members"]
    assert source_beam_payload["entry"]["metadata"]["binary_archive_member_entry_ids"]
    assert source_beam_payload["entry"]["metadata"]["binary_preview_note"]
    assert source_beam_payload["entry"]["metadata"]["binary_preview_state_label"] == "unverified hint preview"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_descriptor"] == "hint preview"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_bucket"] == "hint-preview"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_mode"] == "mcvl_node_hint_preview"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_source_table"] == "NODE/ELEM hinted ranges"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_basis"] == "mcvl_node_elem_hint"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_probe_label"] == "mcvl hint probe"
    assert source_beam_payload["entry"]["metadata"]["binary_preview_trust_hints"]
    assert (
        source_beam_payload["entry"]["metadata"]["binary_preview_reading_boundary_label"]
        == "Hint-guided surface only: safe for directional shape reading and silhouette comparison, but not for node identity, member connectivity, or exact topology. "
        f"Cross-check support is limited to {source_beam_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}."
    )
    assert source_beam_payload["entry"]["metadata"]["binary_preview_decode_readiness_label"].startswith(
        "Decode-readiness: NODE packed-pair candidates"
    )
    assert (
        source_beam_payload["entry"]["metadata"]["binary_preview_exact_promotion_gate_label"]
        == "decode NODE/ELEM hinted ranges into node coordinates and member connectivity"
    )
    assert source_beam_payload["entry"]["metadata"]["binary_exact_decode_status_label"] == "exact decode gate blocked"
    assert source_beam_payload["entry"]["metadata"]["binary_exact_decode_basis_label"].startswith(
        "NODE packed-pair candidates"
    )
    assert "constant-filled" in source_beam_payload["entry"]["metadata"]["binary_exact_decode_evidence_label"]
    assert source_beam_payload["entry"]["metadata"]["binary_hint_phase_scoreboard_label"].startswith("p0:")
    assert source_beam_payload["entry"]["metadata"]["binary_hint_record_windows_label"].startswith("[")
    assert source_beam_payload["entry"]["metadata"]["binary_scalar_anchor_slots_label"].startswith("lane 0 -> slot")
    assert source_beam_payload["entry"]["metadata"]["binary_readiness_stage_label"] == "hint preview + cross-check"
    assert source_beam_payload["entry"]["metadata"]["binary_next_step"] == "decode NODE/ELEM hinted ranges into node coordinates and member connectivity"
    assert source_beam_payload["entry"]["metadata"]["binary_upgrade_priority"] > 0
    assert any(
        row["label"] == "hint point source trace" and row["value"] == "NODE/ELEM hinted ranges"
        for row in source_beam_payload["entry"]["metadata"]["binary_preview_trust_hints"]
    )
    assert any(
        row["label"] == "scalar count" and row["value"] == "15"
        for row in source_beam_payload["entry"]["metadata"]["binary_preview_trust_hints"]
    )
    assert any(
        row["label"] == "grouping phase" and row["value"] == "0"
        for row in source_beam_payload["entry"]["metadata"]["binary_preview_trust_hints"]
    )
    assert "<svg" in source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_svg"]
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_note"]
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"] in {
        "strong silhouette match",
        "moderate silhouette match",
        "weak silhouette match",
    }
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_score"] >= 0.0
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_kind"] == "geometry_bridge"
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_basis"] == "shape_normalized_overlay"
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_subject"] == "selected binary preview"
    assert source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_target"] == "geometry bridge model"
    if source_beam_payload["entry"]["metadata"]["binary_preview_svg"]:
        assert "<svg" in source_beam_payload["entry"]["metadata"]["binary_preview_svg"]
    assert source_beam_payload["entry"]["artifact_paths"]["decoded_inventory_catalog_page"].endswith(
        "binary_inventory_midas_support_beam_archive.html"
    )
    assert source_beam_payload["entry"]["metadata"]["adapter_readiness_hint"] in {
        "native model binary candidate detected",
        "cad/parametric geometry candidate detected",
        "archive cached / parser pending",
        "archive cached / unreadable members",
    }
    assert source_github_payload["entry"]["metadata"]["parse_ok"] is True
    assert source_github_payload["entry"]["status_label"] == "registered source / parsed ready / 3d linked"
    assert source_fcm_payload["entry"]["metadata"]["binary_decoded_inventory_contract_ready"] is True
    assert source_fcm_payload["entry"]["metadata"]["binary_decoded_inventory_ready"] is False
    assert source_fcm_payload["entry"]["status_label"] in {
        "registered source / preview 3d linked",
        "registered source / verified preview 3d linked",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_state_label"] in {
        "verified preview",
        "unverified table-local preview",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_bucket"] in {
        "table-local-preview",
        "verified-preview",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_mode"] == "table_local_ascii_preview"
    assert "*POINT/*MEMBER_ADD" in source_fcm_payload["entry"]["metadata"]["binary_preview_source_table"]
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_basis"] == "table_local_payload"
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_anchor_table_names"] == [
        "PONT",
        "CURV",
        "MEMB",
        "*POINT",
        "*MEMBER_ADD",
    ]
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_bridge_summary"]["preview_state_label"] == "unverified table-local preview"
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_surface_status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_readiness_stage_label"] in {
        "verified preview ready",
        "exact recovered topology candidate + cross-check",
        "topology-grounded preview + cross-check",
        "payload-exact member-add preview + cross-check",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_reading_boundary_label"] in {
        "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology.",
        "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim. "
        f"Cross-check support is limited to {source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim. "
        f"Cross-check support is limited to {source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim. "
        f"Cross-check support is limited to {source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_decode_readiness_label"] in {
        "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step.",
        "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains.",
        "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains.",
        "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains.",
        "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
        "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_exact_promotion_gate_label"].startswith(
        (
            "connect exact topology or bridge cross-check for confidence uplift",
            "close the final verified preview gate on top of the exact recovered topology candidate",
            "validate exact member-add topology confidence",
            "close the verified promotion gate on top of the payload-exact member-add topology preview",
        )
    )
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_topology_ready"] is True
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_topology_readiness_label"] in {
        "topology-grounded member-add preview",
        "payload-exact member-add preview",
        "payload-exact member-add topology preview",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_fidelity_label"] in {
        "verified preview",
        "exact recovered topology candidate",
        "topology-grounded preview",
        "payload-exact member-add preview",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_exactness_label"] in {
        "exact topology candidate",
        "topology-grounded member-add preview",
        "payload-exact member-add preview",
        "payload-exact member-add topology preview",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_exactness_signal_source_label"] in {
        "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD",
        "n/a",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_missing_member_path_count"] == 0
    assert source_fcm_payload["entry"]["metadata"]["binary_preview_missing_member_reference_count"] == 0
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_title"] in {
        "Binary Preview Variant Cross-Check",
        "Binary Inventory Variant Cross-Check",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_gap_label"] in {
        "silhouette_gap",
        "token_gap",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"] in {
        "strong token match",
        "moderate token match",
        "weak token match",
        "strong silhouette match",
        "moderate silhouette match",
        "weak silhouette match",
    }
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_score"] >= 0.0
    assert "<svg" in source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_svg"]
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_kind"] in {"archive_variant", "inventory_variant"}
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_basis"] in {"shape_normalized_overlay", "table_token_overlap"}
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_subject"]
    assert source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_target"]
    assert (
        "archive variant overlay" in source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_note"]
        or "inventory variant overlap" in source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_note"]
    )
    assert source_fcm_payload["entry"]["artifact_paths"]["decoded_inventory_catalog_page"].endswith(
        "binary_inventory_midas_support_fcm_bridge_archive.html"
    )
    assert source_fcm_payload["entry"]["artifact_paths"]["decoded_preview_bridge_report"].endswith(
        "midas_support_fcm_bridge_archive_decoded_preview/bridge_report.json"
    )
    assert fcm_inventory_payload["entry"]["status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert fcm_inventory_payload["entry"]["metadata"]["binary_decoded_inventory_contract_ready"] is True
    assert (
        fcm_inventory_payload["entry"]["status_label"]
        == fcm_inventory_payload["entry"]["metadata"]["binary_preview_surface_status_label"]
    )
    assert source_ramp_payload["entry"]["metadata"]["binary_decoded_inventory_contract_ready"] is True
    assert source_ramp_payload["entry"]["metadata"]["binary_decoded_inventory_ready"] is False
    assert source_ramp_payload["entry"]["metadata"]["binary_decoded_inventory_summary"]["layout_family"] == "MBDG_DB_CONTAINER"
    assert source_ramp_payload["entry"]["status_label"] in {
        "registered source / preview 3d linked",
        "registered source / verified preview 3d linked",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_state_label"] in {
        "verified preview",
        "unverified table-local preview",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_bucket"] in {
        "table-local-preview",
        "verified-preview",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_surface_status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_basis"] == "table_local_payload"
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_source_table"] == "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD"
    assert source_ramp_payload["entry"]["metadata"]["binary_readiness_stage_label"] in {
        "verified preview ready",
        "exact recovered topology candidate + cross-check",
        "topology-grounded preview + cross-check",
        "payload-exact member-add preview + cross-check",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_reading_boundary_label"] in {
        "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology.",
        "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim. "
        f"Cross-check support is limited to {source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim. "
        f"Cross-check support is limited to {source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim. "
        f"Cross-check support is limited to {source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_decode_readiness_label"] in {
        "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step.",
        "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains.",
        "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains.",
        "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains.",
        "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
        "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_exact_promotion_gate_label"].startswith(
        (
            "connect exact topology or bridge cross-check for confidence uplift",
            "close the final verified preview gate on top of the exact recovered topology candidate",
            "validate exact member-add topology confidence",
            "close the verified promotion gate on top of the payload-exact member-add topology preview",
        )
    )
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_topology_ready"] is True
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_topology_readiness_label"] in {
        "topology-grounded member-add preview",
        "payload-exact member-add preview",
        "payload-exact member-add topology preview",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_missing_member_path_count"] == 0
    assert source_ramp_payload["entry"]["metadata"]["binary_preview_missing_member_reference_count"] == 0
    assert source_ramp_payload["entry"]["metadata"]["binary_bridge_crosscheck_title"] == "Binary Preview Variant Cross-Check"
    assert source_ramp_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"] in {
        "strong silhouette match",
        "moderate silhouette match",
        "weak silhouette match",
    }
    assert source_ramp_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_score"] >= 0.0
    assert "<svg" in source_ramp_payload["entry"]["metadata"]["binary_bridge_crosscheck_svg"]
    assert "archive variant overlay" in source_ramp_payload["entry"]["metadata"]["binary_bridge_crosscheck_note"]
    assert source_ramp_payload["entry"]["artifact_paths"]["decoded_inventory_catalog_page"].endswith(
        "binary_inventory_midas_support_ramp_archive.html"
    )
    assert "ramp_decoded_preview_baseline" in source_ramp_payload["entry"]["metadata"]["derived_cases"]
    assert source_rc_house_payload["entry"]["metadata"]["binary_decoded_inventory_ready"] is True
    assert source_rc_house_payload["entry"]["metadata"]["binary_decoded_inventory_contract_ready"] is True
    assert source_rc_house_payload["entry"]["status_label"] in {
        "registered source / preview 3d linked",
        "registered source / verified preview 3d linked",
    }
    assert source_rc_house_payload["entry"]["metadata"]["binary_decoded_inventory_summary"]["geometry_preview_ready"] is True
    assert source_rc_house_payload["entry"]["metadata"]["binary_decoded_inventory_source_table"] == "xVPNT"
    assert source_rc_house_payload["entry"]["metadata"]["binary_decoded_inventory_selected_member"].endswith(".meb")
    assert source_rc_house_payload["entry"]["metadata"]["binary_decoded_inventory_reason_code"].startswith("PASS_")
    assert source_rc_house_payload["entry"]["metadata"]["binary_preview_state_label"] == "verified preview"
    assert source_rc_house_payload["entry"]["metadata"]["binary_readiness_stage_label"] == "verified preview ready"
    assert (
        source_rc_house_payload["entry"]["metadata"]["binary_preview_reading_boundary_label"]
        == "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology."
    )
    assert (
        source_rc_house_payload["entry"]["metadata"]["binary_preview_decode_readiness_label"]
        == "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step."
    )
    assert source_rc_house_payload["entry"]["metadata"]["binary_preview_exact_promotion_gate_label"].startswith(
        (
            "inspect exact topology confidence uplift",
            "connect exact topology or bridge cross-check for confidence uplift",
        )
    )
    assert "rc_house_decoded_preview_baseline" in source_rc_house_payload["entry"]["metadata"]["derived_cases"]
    assert rc_house_preview_viewer_payload["case_context"]["status_label"] == "viewer-ready verified preview 3d bridge"
    assert rc_house_preview_viewer_payload["case_context"]["case_family"] == "support_source_preview"
    assert rc_house_preview_viewer_payload["case_context"]["preview_source_table_label"] == "xVPNT"
    assert rc_house_preview_viewer_payload["case_context"]["preview_state_label"] == "verified preview"
    assert rc_house_preview_viewer_payload["case_context"]["preview_surface_status_label"] == "viewer-ready verified preview 3d bridge"
    assert rc_house_preview_viewer_payload["case_context"]["preview_readiness_stage_label"] in {
        "viewer-ready verified preview",
        "verified preview ready",
    }
    assert rc_house_preview_viewer_payload["case_context"]["preview_basis_label"] == "table_directory_heuristic"
    assert rc_house_preview_viewer_payload["case_context"]["source_status_label"] == source_rc_house_payload["entry"]["status_label"]
    assert rc_house_preview_viewer_payload["case_context"]["binary_bridge_crosscheck_quality_label"] == source_rc_house_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"]
    assert rc_house_preview_viewer_payload["case_context"]["binary_readiness_stage_label"] == "verified preview ready"
    assert rc_house_preview_viewer_payload["case_context"]["queue_rank_label"] == "4/4"
    assert rc_house_preview_viewer_payload["case_context"]["queue_next_label"] == "none"
    assert rc_house_preview_viewer_payload["case_context"]["next_unlock_label"].startswith(
        (
            "inspect exact topology confidence uplift",
            "connect exact topology or bridge cross-check for confidence uplift",
        )
    )
    assert (
        rc_house_preview_viewer_payload["case_context"]["preview_reading_boundary_label"]
        == "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology."
    )
    assert (
        rc_house_preview_viewer_payload["case_context"]["preview_decode_readiness_label"]
        == "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step."
    )
    assert rc_house_preview_viewer_payload["case_context"]["preview_fidelity_label"] == "verified preview"
    assert rc_house_preview_viewer_payload["case_context"]["preview_exactness_signal_source_label"] in {
        "geometry_preview_ready",
        "xVPNT",
    }
    assert rc_house_preview_viewer_payload["case_context"]["preview_exact_promotion_gate_label"].startswith(
        (
            "inspect exact topology confidence uplift",
            "connect exact topology or bridge cross-check for confidence uplift",
        )
    )
    assert rc_house_preview_viewer_payload["case_context"]["initial_3d_mode"] == "baseline-only"
    assert rc_house_preview_viewer_payload["case_context"]["evidence_links"][0]["key"] == "source-catalog-page"
    assert "viewer-ready verified preview 3d bridge" in rc_house_preview_viewer_html
    assert "preview segments" in rc_house_preview_viewer_html
    assert "preview points" in rc_house_preview_viewer_html
    assert "context source" in rc_house_preview_viewer_html
    assert "readiness-card is-context-source" in rc_house_preview_viewer_html
    assert "preview source=xVPNT" in rc_house_preview_viewer_html
    assert "basis=table_directory_heuristic" in rc_house_preview_viewer_html
    assert f"source status={source_rc_house_payload['entry']['status_label']}" in rc_house_preview_viewer_html
    assert f"cross-check={source_rc_house_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}" in rc_house_preview_viewer_html
    assert (
        "readiness=viewer-ready verified preview" in rc_house_preview_viewer_html
        or "readiness=verified preview ready" in rc_house_preview_viewer_html
    )
    assert "queue=4/4" in rc_house_preview_viewer_html
    assert "next source=none" in rc_house_preview_viewer_html
    assert (
        "next unlock=inspect exact topology confidence uplift or attach bridge cross-check evidence" in rc_house_preview_viewer_html
        or "next unlock=connect exact topology or bridge cross-check for confidence uplift" in rc_house_preview_viewer_html
    )
    assert "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology." in rc_house_preview_viewer_html
    assert "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step." in rc_house_preview_viewer_html
    assert "Source Lineage Ribbon" in rc_house_preview_viewer_html
    assert "registered source page" in rc_house_preview_viewer_html
    assert "decoded inventory preview" in rc_house_preview_viewer_html
    assert "preview bridge report" in rc_house_preview_viewer_html
    assert "First 3D Promotion Live" in rc_house_source_html
    assert "<svg" in source_rc_house_payload["entry"]["metadata"]["binary_preview_svg"]
    assert "Heuristic XY preview" in source_rc_house_payload["entry"]["metadata"]["binary_preview_svg"]
    assert source_rc_house_payload["entry"]["artifact_paths"]["decoded_inventory_preview_page"].endswith(
        "binary_preview_midas_support_rc_house_archive.html"
    )
    assert "beam_decoded_preview_baseline" in source_beam_payload["entry"]["metadata"]["derived_cases"]
    assert beam_preview_viewer_payload["case_context"]["status_label"] == "hint-guided preview-derived 3d candidate"
    assert beam_preview_viewer_payload["case_context"]["preview_state_label"] == "unverified hint preview"
    assert beam_preview_viewer_payload["case_context"]["preview_surface_status_label"] == "hint-guided preview-derived 3d candidate"
    assert beam_preview_viewer_payload["case_context"]["preview_readiness_stage_label"] in {
        "hint preview candidate",
        "hint preview + cross-check",
    }
    assert beam_preview_viewer_payload["case_context"]["preview_basis_label"] == "mcvl_node_elem_hint"
    assert beam_preview_viewer_payload["case_context"]["preview_fidelity_label"] == "hint-guided preview"
    assert beam_preview_viewer_payload["case_context"]["preview_density_label"] == "sparse preview geometry"
    assert beam_preview_viewer_payload["case_context"]["preview_visibility_label"] == "sparse assist on"
    assert "secondary members" in beam_preview_viewer_payload["case_context"]["preview_hidden_detail_label"]
    assert beam_preview_viewer_payload["case_context"]["preview_recommended_visibility_mode_label"] == "trace"
    assert beam_preview_viewer_payload["case_context"]["source_status_label"] == source_beam_payload["entry"]["status_label"]
    assert beam_preview_viewer_payload["case_context"]["binary_bridge_crosscheck_quality_label"] == source_beam_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"]
    assert beam_preview_viewer_payload["case_context"]["binary_readiness_stage_label"] == "hint preview + cross-check"
    assert beam_preview_viewer_payload["case_context"]["queue_rank_label"] == "1/4"
    assert beam_preview_viewer_payload["case_context"]["queue_next_label"] == "fcm"
    assert beam_preview_viewer_payload["case_context"]["binary_bridge_crosscheck_kind"] == "geometry_bridge"
    assert beam_preview_viewer_payload["case_context"]["next_unlock_label"] == "decode NODE/ELEM hinted ranges into node coordinates and member connectivity"
    assert (
        beam_preview_viewer_payload["case_context"]["preview_reading_boundary_label"]
        == "Hint-guided surface only: safe for directional shape reading and silhouette comparison, but not for node identity, member connectivity, or exact topology. "
        f"Cross-check support is limited to {source_beam_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}."
    )
    assert beam_preview_viewer_payload["case_context"]["preview_decode_readiness_label"].startswith(
        "Decode-readiness: NODE packed-pair candidates"
    )
    assert (
        beam_preview_viewer_payload["case_context"]["preview_exact_promotion_gate_label"]
        == "decode NODE/ELEM hinted ranges into node coordinates and member connectivity"
    )
    assert beam_preview_viewer_payload["case_context"]["preview_exact_decode_status_label"] == "exact decode gate blocked"
    assert beam_preview_viewer_payload["case_context"]["preview_exact_decode_basis_label"].startswith(
        "NODE packed-pair candidates"
    )
    assert "constant-filled" in beam_preview_viewer_payload["case_context"]["preview_exact_decode_evidence_label"]
    assert beam_preview_viewer_payload["case_context"]["preview_exact_decode_recommendation_label"] == "do_not_promote"
    assert "Not enough evidence today" in beam_preview_viewer_payload["case_context"]["preview_exact_decode_recommendation_summary"]
    assert beam_preview_viewer_payload["case_context"]["preview_exact_decode_next_experiment_id"] == "beam_node_xyz_slot_recovery"
    assert "Recover stable record-local NODE xyz semantics" in beam_preview_viewer_payload["case_context"]["preview_exact_decode_next_experiment_goal"]
    assert "beam_node_xyz_slot_recovery" in beam_preview_viewer_payload["case_context"]["preview_exact_decode_recommended_order_label"]
    assert beam_preview_viewer_payload["case_context"]["preview_node_reassembly_best_phase_label"] == "0"
    assert beam_preview_viewer_payload["case_context"]["preview_node_reassembly_triplet_count_label"] == "5"
    assert beam_preview_viewer_payload["case_context"]["preview_node_reassembly_cross_record_count_label"] == "5"
    assert "[951, 953, 953]" in beam_preview_viewer_payload["case_context"]["preview_node_reassembly_best_window_label"]
    assert "[1, 0, 2]" in beam_preview_viewer_payload["case_context"]["preview_node_reassembly_best_lane_sequence_label"]
    assert beam_preview_viewer_payload["case_context"]["preview_hint_phase_scoreboard_label"].startswith("p0:")
    assert beam_preview_viewer_payload["case_context"]["preview_hint_record_windows_label"].startswith("[")
    assert beam_preview_viewer_payload["case_context"]["preview_scalar_anchor_slots_label"].startswith("lane 0 -> slot")
    assert beam_preview_viewer_payload["case_context"]["preview_source_table_label"] == "NODE/ELEM hinted ranges"
    assert beam_preview_viewer_payload["case_context"]["preview_decode_focus_label"].startswith("NODE packed-pair candidates")
    assert "decode" in beam_preview_viewer_payload["case_context"]["preview_decode_blocker_label"] or "constant-filled" in beam_preview_viewer_payload["case_context"]["preview_decode_blocker_label"]
    assert "hint-guided preview-derived 3d candidate" in beam_preview_viewer_html
    assert "Exact Topology Evidence" in beam_preview_viewer_html
    assert "Why This Is Not MIDAS 33 Yet" in beam_preview_viewer_html
    assert "promotion recommendation" in beam_preview_viewer_html
    assert "do_not_promote" in beam_preview_viewer_html
    assert "next experiment" in beam_preview_viewer_html
    assert "beam_node_xyz_slot_recovery" in beam_preview_viewer_html
    assert "reassembly triplets" in beam_preview_viewer_html
    assert "cross-record triplets" in beam_preview_viewer_html
    assert "Topology Recovery Ladder" in beam_preview_viewer_html
    assert "commercial parity" in beam_preview_viewer_html
    assert "diagnostic candidate" in beam_preview_viewer_html
    assert "Source Preview Trust Snapshot" in beam_preview_viewer_html
    assert "Source Handoff" in beam_preview_viewer_html
    assert "context source" in beam_preview_viewer_html
    assert "readiness-card is-context-source" in beam_preview_viewer_html
    assert "preview source=NODE/ELEM hinted ranges" in beam_preview_viewer_html
    assert "basis=mcvl_node_elem_hint" in beam_preview_viewer_html
    assert "fidelity=hint-guided preview" in beam_preview_viewer_html
    assert "density=sparse preview geometry" in beam_preview_viewer_html
    assert "visibility=sparse assist on" in beam_preview_viewer_html
    assert "Preview Visibility" in beam_preview_viewer_html
    assert "data-filter-group='interactive-3d-preview-visibility'" in beam_preview_viewer_html
    assert "data-filter-block='interactive-3d-preview-visibility'" in beam_preview_viewer_html
    assert "adaptive" in beam_preview_viewer_html
    assert "clarify" in beam_preview_viewer_html
    assert "thicker + dots" in beam_preview_viewer_html
    assert "focus" in beam_preview_viewer_html
    assert "labels + assist" in beam_preview_viewer_html
    assert "trace" in beam_preview_viewer_html
    assert "max labels" in beam_preview_viewer_html
    assert "interactive-3d-preview-banner-row" in beam_preview_viewer_html
    assert "why this looks lighter" in beam_preview_viewer_html
    assert "not shown yet" in beam_preview_viewer_html
    assert "MIDAS 33 full bridge와 달리" in beam_preview_viewer_html
    assert "geometry density" in beam_preview_viewer_html
    assert "source-preview-trust-panel" in beam_preview_viewer_html
    assert f"source status={source_beam_payload['entry']['status_label']}" in beam_preview_viewer_html
    assert f"cross-check={source_beam_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}" in beam_preview_viewer_html
    assert (
        "readiness=hint preview candidate" in beam_preview_viewer_html
        or "readiness=hint preview + cross-check" in beam_preview_viewer_html
    )
    assert "queue=1/4" in beam_preview_viewer_html
    assert "next source=fcm" in beam_preview_viewer_html
    assert "next unlock=decode NODE/ELEM hinted ranges into node coordinates and member connectivity" in beam_preview_viewer_html
    assert "decode focus" in beam_preview_viewer_html
    assert "decode blocker" in beam_preview_viewer_html
    assert "NODE packed-pair candidates" in beam_preview_viewer_html
    assert "recommended assist=trace" in beam_preview_viewer_html
    assert "reading boundary" in beam_preview_viewer_html
    assert "decode-readiness" in beam_preview_viewer_html
    assert "exact promotion gate" in beam_preview_viewer_html
    assert "Hint-guided surface only: safe for directional shape reading and silhouette comparison, but not for node identity, member connectivity, or exact topology." in beam_preview_viewer_html
    assert "Decode-readiness: NODE packed-pair candidates" in beam_preview_viewer_html
    assert "Confidence Guardrail" in beam_preview_viewer_html
    assert "hint-guided directional preview" in beam_preview_viewer_html
    assert "Use this for rough spatial orientation, silhouette comparison, and upgrade prioritization." in beam_preview_viewer_html
    assert "Do not read member connectivity, node identity, or exact topology from this hint preview." in beam_preview_viewer_html
    assert "Source Lineage Ribbon" in beam_preview_viewer_html
    assert "registered source page" in beam_preview_viewer_html
    assert "decoded inventory preview" in beam_preview_viewer_html
    assert "preview bridge report" in beam_preview_viewer_html
    assert ramp_preview_viewer_payload["case_context"]["status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_state_label"] in {
        "verified preview",
        "unverified table-local preview",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_surface_status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_readiness_stage_label"] in {
        "verified preview ready",
        "exact recovered topology candidate",
        "topology-grounded preview candidate",
        "payload-exact member-add preview candidate",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_basis_label"] == "table_local_payload"
    assert ramp_preview_viewer_payload["case_context"]["preview_fidelity_label"] in {
        "verified preview",
        "exact recovered topology candidate",
        "topology-grounded preview",
        "payload-exact member-add preview",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_density_label"] in {
        "moderate preview geometry",
        "sparse preview geometry",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_visibility_label"] in {
        "standard preview visibility",
        "sparse assist on",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_recommended_visibility_mode_label"] in {"auto", "trace"}
    assert ramp_preview_viewer_payload["case_context"]["source_status_label"] == source_ramp_payload["entry"]["status_label"]
    assert ramp_preview_viewer_payload["case_context"]["binary_bridge_crosscheck_quality_label"] == source_ramp_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"]
    assert ramp_preview_viewer_payload["case_context"]["binary_readiness_stage_label"] in {
        "verified preview ready",
        "exact recovered topology candidate + cross-check",
        "topology-grounded preview + cross-check",
        "payload-exact member-add preview + cross-check",
    }
    assert ramp_preview_viewer_payload["case_context"]["queue_rank_label"] == "3/4"
    assert ramp_preview_viewer_payload["case_context"]["queue_next_label"] == "rc_house"
    assert ramp_preview_viewer_payload["case_context"]["next_unlock_label"].startswith(
        (
            "connect exact topology or bridge cross-check for confidence uplift",
            "close the final verified preview gate on top of the exact recovered topology candidate",
            "validate exact member-add topology confidence",
            "close the verified promotion gate on top of the payload-exact member-add topology preview",
        )
    )
    assert ramp_preview_viewer_payload["case_context"]["preview_reading_boundary_label"] in {
        "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology.",
        "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim. "
        f"Cross-check support is limited to {source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim. "
        f"Cross-check support is limited to {source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim. "
        f"Cross-check support is limited to {source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_decode_readiness_label"] in {
        "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step.",
        "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains.",
        "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains.",
        "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains.",
        "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
        "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_exact_promotion_gate_label"].startswith(
        (
            "connect exact topology or bridge cross-check for confidence uplift",
            "close the final verified preview gate on top of the exact recovered topology candidate",
            "validate exact member-add topology confidence",
            "close the verified promotion gate on top of the payload-exact member-add topology preview",
        )
    )
    assert ramp_preview_viewer_payload["case_context"]["preview_source_table_label"] == "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD"
    assert ramp_preview_viewer_payload["case_context"]["preview_topology_ready_label"] == "True"
    assert ramp_preview_viewer_payload["case_context"]["preview_topology_readiness_label"] in {
        "topology-grounded member-add preview",
        "payload-exact member-add preview",
        "payload-exact member-add topology preview",
    }
    assert ramp_preview_viewer_payload["case_context"]["preview_missing_member_path_count_label"] == "0"
    assert ramp_preview_viewer_payload["case_context"]["preview_missing_member_reference_count_label"] == "0"
    assert (
        "viewer-ready verified preview 3d bridge" in ramp_preview_viewer_html
        or
        "exact recovered topology-derived 3d candidate" in ramp_preview_viewer_html
        or
        "topology-grounded preview-derived 3d candidate" in ramp_preview_viewer_html
        or "payload-exact member-add preview-derived 3d candidate" in ramp_preview_viewer_html
    )
    assert "Source Preview Trust Snapshot" in ramp_preview_viewer_html
    assert "Source Handoff" in ramp_preview_viewer_html
    assert "context source" in ramp_preview_viewer_html
    assert "readiness-card is-context-source" in ramp_preview_viewer_html
    assert "preview source=ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD" in ramp_preview_viewer_html
    assert "basis=table_local_payload" in ramp_preview_viewer_html
    assert (
        "fidelity=verified preview" in ramp_preview_viewer_html
        or
        "fidelity=exact recovered topology candidate" in ramp_preview_viewer_html
        or "fidelity=topology-grounded preview" in ramp_preview_viewer_html
        or "fidelity=payload-exact member-add preview" in ramp_preview_viewer_html
    )
    assert (
        "density=moderate preview geometry" in ramp_preview_viewer_html
        or "density=sparse preview geometry" in ramp_preview_viewer_html
    )
    assert (
        "visibility=standard preview visibility" in ramp_preview_viewer_html
        or "visibility=sparse assist on" in ramp_preview_viewer_html
    )
    assert f"source status={source_ramp_payload['entry']['status_label']}" in ramp_preview_viewer_html
    assert f"cross-check={source_ramp_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}" in ramp_preview_viewer_html
    assert (
        "readiness=verified preview ready" in ramp_preview_viewer_html
        or
        "readiness=exact recovered topology candidate" in ramp_preview_viewer_html
        or
        "readiness=topology-grounded preview candidate" in ramp_preview_viewer_html
        or "readiness=payload-exact member-add preview candidate" in ramp_preview_viewer_html
    )
    assert "queue=3/4" in ramp_preview_viewer_html
    assert "next source=rc_house" in ramp_preview_viewer_html
    assert (
        "next unlock=connect exact topology or bridge cross-check for confidence uplift" in ramp_preview_viewer_html
        or
        "next unlock=close the final verified preview gate on top of the exact recovered topology candidate" in ramp_preview_viewer_html
        or
        "next unlock=validate exact member-add topology confidence and promote to verified preview" in ramp_preview_viewer_html
        or "next unlock=close the verified promotion gate on top of the payload-exact member-add topology preview" in ramp_preview_viewer_html
    )
    assert (
        "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology." in ramp_preview_viewer_html
        or
        "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim." in ramp_preview_viewer_html
        or
        "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim." in ramp_preview_viewer_html
        or "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim." in ramp_preview_viewer_html
    )
    assert "Exact Topology Evidence" in ramp_preview_viewer_html
    assert "Why This Is Not MIDAS 33 Yet" in ramp_preview_viewer_html
    assert "payload-exact member-add topology preview" in ramp_preview_viewer_html
    assert "Topology Recovery Ladder" in ramp_preview_viewer_html
    assert "commercial parity" in ramp_preview_viewer_html
    assert "review-grade lite" in ramp_preview_viewer_html
    assert (
        "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step." in ramp_preview_viewer_html
        or
        "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains." in ramp_preview_viewer_html
        or "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains." in ramp_preview_viewer_html
        or
        "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains." in ramp_preview_viewer_html
        or "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in ramp_preview_viewer_html
        or "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in ramp_preview_viewer_html
    )
    assert "exact promotion gate" in ramp_preview_viewer_html
    assert "Source Lineage Ribbon" in ramp_preview_viewer_html
    assert "registered source page" in ramp_preview_viewer_html
    assert "decoded inventory preview" in ramp_preview_viewer_html
    assert "preview bridge report" in ramp_preview_viewer_html
    assert any(
        row["entry_id"] == "binary_preview_midas_support_rc_house_archive"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "binary_inventory_midas_support_beam_archive"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "binary_probe_midas_support_beam_archive"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "binary_inventory_midas_support_fcm_bridge_archive"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "fcm_bridge_decoded_preview_baseline"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "binary_inventory_midas_support_ramp_archive"
        for row in payload["case_catalog"]
    )
    assert any(
        row["entry_id"] == "beam_decoded_preview_baseline"
        for row in payload["case_catalog"]
    )
    beam_catalog_row = next(row for row in payload["case_catalog"] if row["entry_id"] == "beam_decoded_preview_baseline")
    assert beam_catalog_row["preview_state_label"] == "unverified hint preview"
    assert beam_catalog_row["preview_surface_bucket"] == "hint-preview"
    assert beam_catalog_row["preview_fidelity_label"] == "hint-guided preview"
    assert beam_catalog_row["preview_density_label"] == "sparse preview geometry"
    assert beam_catalog_row["preview_recommended_visibility_mode_label"] == "trace"
    assert any(
        row["entry_id"] == "ramp_decoded_preview_baseline"
        for row in payload["case_catalog"]
    )
    ramp_catalog_row = next(row for row in payload["case_catalog"] if row["entry_id"] == "ramp_decoded_preview_baseline")
    assert ramp_catalog_row["preview_state_label"] in {"verified preview", "unverified table-local preview"}
    assert ramp_catalog_row["preview_surface_bucket"] in {"verified-preview", "table-local-preview"}
    if any(row["entry_id"] == "fcm_decoded_preview_baseline" for row in payload["case_catalog"]):
        fcm_catalog_row = next(row for row in payload["case_catalog"] if row["entry_id"] == "fcm_decoded_preview_baseline")
        assert fcm_catalog_row["preview_state_label"] in {"verified preview", "unverified table-local preview"}
        assert fcm_catalog_row["preview_surface_bucket"] in {"verified-preview", "table-local-preview"}
    rc_house_catalog_row = next(row for row in payload["case_catalog"] if row["entry_id"] == "rc_house_decoded_preview_baseline")
    assert rc_house_catalog_row["preview_state_label"] == "verified preview"
    assert rc_house_catalog_row["preview_surface_bucket"] == "verified-preview"
    assert any(
        row["entry_id"].startswith("binary_member_midas_support_ramp_archive_")
        for row in payload["case_catalog"]
    )
    assert ramp_inventory_payload["entry"]["status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert ramp_inventory_payload["entry"]["metadata"]["binary_decoded_inventory_ready"] is False
    assert ramp_inventory_payload["entry"]["metadata"]["binary_inventory_excerpt_rows"]
    assert ramp_inventory_payload["entry"]["metadata"]["binary_inventory_refresh_evaluations"]
    assert ramp_inventory_payload["entry"]["metadata"]["binary_preview_state_label"] in {
        "verified preview",
        "unverified table-local preview",
    }
    assert ramp_inventory_payload["entry"]["metadata"]["binary_preview_surface_status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    assert ramp_inventory_payload["entry"]["metadata"]["binary_readiness_stage_label"] in {
        "verified preview ready",
        "exact recovered topology candidate + cross-check",
        "topology-grounded preview + cross-check",
        "payload-exact member-add preview + cross-check",
    }
    assert (
        ramp_inventory_payload["entry"]["status_label"]
        == ramp_inventory_payload["entry"]["metadata"]["binary_preview_surface_status_label"]
    )
    assert ramp_member_payload["entry"]["metadata"]["member_contract_pass"] is True
    assert beam_probe_payload["entry"]["status_label"] == "binary member extracted / table layout still uncertain"
    assert beam_probe_payload["entry"]["metadata"]["probe_magic_ascii"] == "MCVL"
    assert beam_probe_payload["entry"]["metadata"]["probe_table_token_rows"]
    assert beam_archive_member_payload["entry"]["metadata"]["member_extension"] in {".mcb", ".gh", ".3dm"}
    assert "Decoded Inventory | midas_support_beam_archive" in html
    beam_source_html = (out_dir / "entries" / "source_midas_support_beam_archive.html").read_text(encoding="utf-8")
    assert source_beam_payload["entry"]["metadata"]["binary_decoded_inventory_summary"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert source_beam_payload["entry"]["metadata"]["binary_decoded_inventory_summary"]["geometry_preview_mode"] == "mcvl_node_hint_preview"
    assert source_beam_payload["entry"]["metadata"]["binary_node_elem_probe"]["node"]["range_start"] == 951
    assert source_beam_payload["entry"]["metadata"]["binary_node_elem_probe"]["node"]["range_end"] == 1111
    assert source_beam_payload["entry"]["metadata"]["binary_node_elem_probe"]["elem"]["range_start"] == 224
    assert source_beam_payload["entry"]["metadata"]["binary_node_elem_probe"]["elem"]["range_end"] == 379
    assert "exact decode gate" in beam_source_html
    assert "exact decode=exact decode gate blocked" in beam_source_html
    assert "hint phase scoreboard" in beam_source_html
    assert "lane anchor slots" in beam_source_html
    if source_beam_payload["entry"]["metadata"]["binary_preview_svg"]:
        assert "Heuristic Geometry Preview" in beam_source_html
        assert "unverified hint preview" in beam_source_html
    assert "Upgrade Action Pack" in beam_source_html
    assert "Preview Trust Snapshot" in beam_source_html
    assert "Open decoded inventory page" in beam_source_html
    assert "Open primary binary probe" in beam_source_html
    assert "Open geometry bridge report" in beam_source_html
    assert "decode NODE/ELEM hinted ranges into node coordinates and member connectivity" in beam_source_html
    assert (
        "connect exact topology or bridge cross-check for confidence uplift" in ramp_source_html
        or
        "close the final verified preview gate on top of the exact recovered topology candidate" in ramp_source_html
        or
        "validate exact member-add topology confidence and promote to verified preview" in ramp_source_html
        or "close the verified promotion gate on top of the payload-exact member-add topology preview" in ramp_source_html
    )
    assert (
        "connect exact topology or bridge cross-check for confidence uplift" in fcm_source_html
        or
        "close the final verified preview gate on top of the exact recovered topology candidate" in fcm_source_html
        or
        "validate exact member-add topology confidence and promote to verified preview" in fcm_source_html
        or "close the verified promotion gate on top of the payload-exact member-add topology preview" in fcm_source_html
    )
    assert "layout_family" in beam_source_html
    assert "MCVL_TABLE_CONTAINER" in beam_source_html
    assert "MCVL Node/ELEM Probe" in beam_source_html
    assert "MCVL Uint Layout Evidence" in beam_source_html
    assert "951..1111" in beam_source_html
    assert "224..379" in beam_source_html
    assert "node active small uint records" in beam_source_html
    assert "elem active small uint records" in beam_source_html
    assert "node likely packed pairs" in beam_source_html
    assert "node adjacent pair probe" in beam_source_html
    assert "decode focus" in beam_source_html
    assert "decode blocker" in beam_source_html
    assert "NODE packed-pair candidates" in beam_source_html
    assert "small uint slot counts" in beam_source_html
    assert "probe=mcvl hint probe" in beam_source_html
    assert "hint point source trace=NODE/ELEM hinted ranges" in beam_source_html
    assert "scalar count=15" in beam_source_html
    assert "grouping phase=0" in beam_source_html
    assert "Upgrade Guidance" in beam_source_html
    assert "Confidence Guardrail" in beam_source_html
    assert "reading boundary" in beam_source_html
    assert "decode-readiness" in beam_source_html
    assert "exact promotion gate" in beam_source_html
    assert "Hint-guided surface only: safe for directional shape reading and silhouette comparison, but not for node identity, member connectivity, or exact topology." in beam_source_html
    assert "Decode-readiness: NODE packed-pair candidates" in beam_source_html
    assert "hint-guided directional preview" in beam_source_html
    assert "Use this for rough spatial orientation, silhouette comparison, and upgrade prioritization." in beam_source_html
    assert "Do not read member connectivity, node identity, or exact topology from this hint preview." in beam_source_html
    assert "context source" in beam_source_html
    assert "readiness-card is-context-source" in beam_source_html
    assert "hint preview + cross-check" in beam_source_html
    assert "decode NODE/ELEM hinted ranges into node coordinates and member connectivity" in beam_source_html
    beam_inventory_html = (out_dir / "entries" / "binary_inventory_midas_support_beam_archive.html").read_text(encoding="utf-8")
    assert "Heuristic Geometry Preview" in beam_inventory_html
    assert "mode=mcvl_node_hint_preview" in beam_inventory_html
    assert "source=NODE/ELEM hinted ranges" in beam_inventory_html
    assert "MCVL NODE/ELEM hinted" in beam_inventory_html
    assert "Binary vs Geometry Bridge Cross-Check" in beam_inventory_html
    assert "MCVL Node/ELEM Probe" in beam_inventory_html
    assert "cross-check available" in beam_inventory_html
    assert "quality=" in beam_inventory_html
    assert "score=" in beam_inventory_html
    assert "Primary Binary Probe" in (out_dir / "entries" / "binary_inventory_midas_support_beam_archive.html").read_text(encoding="utf-8")
    if rc_house_preview_payload is not None:
        assert rc_house_preview_payload["entry"]["status_label"] == "viewer-ready verified preview 3d bridge"
        assert rc_house_preview_payload["entry"]["metadata"]["binary_decoded_inventory_ready"] is True
        assert rc_house_preview_payload["entry"]["metadata"]["binary_decoded_inventory_source_table"] == "xVPNT"
        assert (
            rc_house_preview_payload["entry"]["status_label"]
            == rc_house_preview_payload["entry"]["metadata"]["binary_preview_surface_status_label"]
        )
    assert "Primary Binary Probe" in (out_dir / "entries" / "source_midas_support_beam_archive.html").read_text(encoding="utf-8")
    assert "Archive Members" in (out_dir / "entries" / "source_midas_support_beam_archive.html").read_text(encoding="utf-8")
    assert "preview 3d=hint-guided preview-derived 3d candidate" in html
    assert (
        "preview 3d=viewer-ready verified preview 3d bridge" in html
        or
        "preview 3d=topology-grounded preview-derived 3d candidate" in html
        or "preview 3d=exact recovered topology-derived 3d candidate" in html
        or "preview 3d=payload-exact member-add preview-derived 3d candidate" in html
    )
    assert "preview 3d=viewer-ready verified preview 3d bridge" in html
    fcm_source_html = (out_dir / "entries" / "source_midas_support_fcm_bridge_archive.html").read_text(encoding="utf-8")
    assert "Preview Trust Snapshot" in fcm_source_html
    assert "Upgrade Guidance" in fcm_source_html
    assert "Confidence Guardrail" in fcm_source_html
    assert ("unverified table-local preview" in fcm_source_html) or ("verified preview" in fcm_source_html)
    assert "table-local preview" in fcm_source_html
    assert (
        "verified preview ready" in fcm_source_html
        or
        "exact recovered topology candidate" in fcm_source_html
        or "topology-grounded preview candidate" in fcm_source_html
        or "payload-exact member-add preview candidate" in fcm_source_html
    )
    assert "reading boundary" in fcm_source_html
    assert "decode-readiness" in fcm_source_html
    assert "exact promotion gate" in fcm_source_html
    assert (
        "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology." in fcm_source_html
        or
        "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim." in fcm_source_html
        or
        "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim." in fcm_source_html
        or "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim." in fcm_source_html
    )
    assert (
        "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step." in fcm_source_html
        or
        "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains." in fcm_source_html
        or "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains." in fcm_source_html
        or
        "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains." in fcm_source_html
        or "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in fcm_source_html
        or "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in fcm_source_html
    )
    assert (
        "Use this for baseline-only 3D navigation, source lineage review, and bridge evidence checks." in fcm_source_html
        or
        "Use this for topology-level reading, member-add lineage review, and final verified-preview gating." in fcm_source_html
        or
        "Use this for table-grounded layout reading, member-add lineage review, and decoded preview triage." in fcm_source_html
        or "Use this for member-add topology reading, table-grounded layout review, and promotion gating." in fcm_source_html
    )
    assert (
        "Do not silently promote it to exact recovered authoring topology without the separate topology uplift evidence." in fcm_source_html
        or
        "Do not call this verified bridge geometry or full authoring topology until the remaining verified gate is closed." in fcm_source_html
        or
        "Do not call this verified or exact recovered topology until the remaining upgrade gate is closed." in fcm_source_html
        or "Do not call this verified or fully recovered authoring topology until the remaining promotion gate is closed." in fcm_source_html
    )
    fcm_inventory_html = (out_dir / "entries" / "binary_inventory_midas_support_fcm_bridge_archive.html").read_text(encoding="utf-8")
    assert "Decoded Inventory Snapshot" in fcm_inventory_html
    assert "*POINT/*MEMBER_ADD" in fcm_inventory_html
    assert "kind=" in fcm_source_html
    assert "basis=" in fcm_source_html
    assert "subject=" in fcm_source_html
    assert "target=" in fcm_source_html
    assert fcm_inventory_payload["entry"]["metadata"]["binary_readiness_stage_label"] in {
        "verified preview ready",
        "exact recovered topology candidate + cross-check",
        "topology-grounded preview + cross-check",
        "payload-exact member-add preview + cross-check",
    }
    assert fcm_inventory_payload["entry"]["metadata"]["binary_preview_surface_status_label"] in {
        "viewer-ready verified preview 3d bridge",
        "exact recovered topology-derived 3d candidate",
        "topology-grounded preview-derived 3d candidate",
        "payload-exact member-add preview-derived 3d candidate",
    }
    if fcm_preview_viewer_payload is not None:
        fcm_preview_viewer_html = (out_dir / "entries" / "fcm_bridge_decoded_preview_baseline.html").read_text(encoding="utf-8")
        assert fcm_preview_viewer_payload["case_context"]["status_label"] in {
            "viewer-ready verified preview 3d bridge",
            "exact recovered topology-derived 3d candidate",
            "topology-grounded preview-derived 3d candidate",
            "payload-exact member-add preview-derived 3d candidate",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_state_label"] in {
            "verified preview",
            "unverified table-local preview",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_surface_status_label"] in {
            "viewer-ready verified preview 3d bridge",
            "exact recovered topology-derived 3d candidate",
            "topology-grounded preview-derived 3d candidate",
            "payload-exact member-add preview-derived 3d candidate",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_readiness_stage_label"] in {
            "verified preview ready",
            "exact recovered topology candidate",
            "topology-grounded preview candidate",
            "payload-exact member-add preview candidate",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_basis_label"] == "table_local_payload"
        assert fcm_preview_viewer_payload["case_context"]["preview_fidelity_label"] in {
            "verified preview",
            "exact recovered topology candidate",
            "topology-grounded preview",
            "payload-exact member-add preview",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_density_label"] in {
            "moderate preview geometry",
            "sparse preview geometry",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_visibility_label"] in {
            "standard preview visibility",
            "sparse assist on",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_recommended_visibility_mode_label"] in {"auto", "trace"}
        assert fcm_preview_viewer_payload["case_context"]["source_status_label"] == source_fcm_payload["entry"]["status_label"]
        assert fcm_preview_viewer_payload["case_context"]["binary_bridge_crosscheck_quality_label"] == source_fcm_payload["entry"]["metadata"]["binary_bridge_crosscheck_quality_label"]
        assert fcm_preview_viewer_payload["case_context"]["preview_anchor_table_names_label"] == "PONT, CURV, MEMB, *POINT, *MEMBER_ADD"
        assert fcm_preview_viewer_payload["case_context"]["binary_readiness_stage_label"] in {
            "verified preview ready",
            "exact recovered topology candidate + cross-check",
            "topology-grounded preview + cross-check",
            "payload-exact member-add preview + cross-check",
        }
        assert fcm_preview_viewer_payload["case_context"]["queue_rank_label"] == "2/4"
        assert fcm_preview_viewer_payload["case_context"]["queue_next_label"] == "ramp"
        assert fcm_preview_viewer_payload["case_context"]["next_unlock_label"].startswith(
            (
                "connect exact topology or bridge cross-check for confidence uplift",
                "close the final verified preview gate on top of the exact recovered topology candidate",
                "validate exact member-add topology confidence",
                "close the verified promotion gate on top of the payload-exact member-add topology preview",
            )
        )
        assert fcm_preview_viewer_payload["case_context"]["preview_reading_boundary_label"] in {
            "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology.",
            "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim. "
            f"Cross-check support is limited to {source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
            "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim. "
            f"Cross-check support is limited to {source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
            "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim. "
            f"Cross-check support is limited to {source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}.",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_decode_readiness_label"] in {
            "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step.",
            "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains.",
            "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains.",
            "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains.",
            "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
            "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains.",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_exact_promotion_gate_label"].startswith(
            (
                "connect exact topology or bridge cross-check for confidence uplift",
                "close the final verified preview gate on top of the exact recovered topology candidate",
                "validate exact member-add topology confidence",
                "close the verified promotion gate on top of the payload-exact member-add topology preview",
            )
        )
        assert "*POINT/*MEMBER_ADD" in fcm_preview_viewer_payload["case_context"]["preview_source_table_label"]
        assert fcm_preview_viewer_payload["case_context"]["preview_topology_ready_label"] == "True"
        assert fcm_preview_viewer_payload["case_context"]["preview_topology_readiness_label"] in {
            "topology-grounded member-add preview",
            "payload-exact member-add preview",
            "payload-exact member-add topology preview",
        }
        assert fcm_preview_viewer_payload["case_context"]["preview_missing_member_path_count_label"] == "0"
        assert fcm_preview_viewer_payload["case_context"]["preview_missing_member_reference_count_label"] == "0"
        assert (
            "viewer-ready verified preview 3d bridge" in fcm_preview_viewer_html
            or
            "exact recovered topology-derived 3d candidate" in fcm_preview_viewer_html
            or
            "topology-grounded preview-derived 3d candidate" in fcm_preview_viewer_html
            or "payload-exact member-add preview-derived 3d candidate" in fcm_preview_viewer_html
        )
        assert "Source Preview Trust Snapshot" in fcm_preview_viewer_html
        assert "Source Handoff" in fcm_preview_viewer_html
        assert "context source" in fcm_preview_viewer_html
        assert "readiness-card is-context-source" in fcm_preview_viewer_html
        assert "*POINT/*MEMBER_ADD" in fcm_preview_viewer_html
        assert "basis=table_local_payload" in fcm_preview_viewer_html
        assert (
            "fidelity=verified preview" in fcm_preview_viewer_html
            or
            "fidelity=exact recovered topology candidate" in fcm_preview_viewer_html
            or "fidelity=topology-grounded preview" in fcm_preview_viewer_html
            or "fidelity=payload-exact member-add preview" in fcm_preview_viewer_html
        )
        assert (
            "density=moderate preview geometry" in fcm_preview_viewer_html
            or "density=sparse preview geometry" in fcm_preview_viewer_html
        )
        assert (
            "visibility=standard preview visibility" in fcm_preview_viewer_html
            or "visibility=sparse assist on" in fcm_preview_viewer_html
        )
        assert "fidelity note=" in fcm_preview_viewer_html
        assert "visibility note=" in fcm_preview_viewer_html
        assert f"source status={source_fcm_payload['entry']['status_label']}" in fcm_preview_viewer_html
        assert f"cross-check={source_fcm_payload['entry']['metadata']['binary_bridge_crosscheck_quality_label']}" in fcm_preview_viewer_html
        assert (
            "readiness=verified preview ready" in fcm_preview_viewer_html
            or
            "readiness=exact recovered topology candidate" in fcm_preview_viewer_html
            or
            "readiness=topology-grounded preview candidate" in fcm_preview_viewer_html
            or "readiness=payload-exact member-add preview candidate" in fcm_preview_viewer_html
        )
        assert "queue=2/4" in fcm_preview_viewer_html
        assert "next source=ramp" in fcm_preview_viewer_html
        assert (
            "next unlock=connect exact topology or bridge cross-check for confidence uplift" in fcm_preview_viewer_html
            or
            "next unlock=close the final verified preview gate on top of the exact recovered topology candidate" in fcm_preview_viewer_html
            or
            "next unlock=validate exact member-add topology confidence and promote to verified preview" in fcm_preview_viewer_html
            or "next unlock=close the verified promotion gate on top of the payload-exact member-add topology preview" in fcm_preview_viewer_html
        )
        assert (
            "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology." in fcm_preview_viewer_html
            or
            "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim." in fcm_preview_viewer_html
            or
            "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim." in fcm_preview_viewer_html
            or "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim." in fcm_preview_viewer_html
        )
        assert "Exact Topology Evidence" in fcm_preview_viewer_html
        assert "Why This Is Not MIDAS 33 Yet" in fcm_preview_viewer_html
        assert "payload-exact member-add topology preview" in fcm_preview_viewer_html
        assert "Topology Recovery Ladder" in fcm_preview_viewer_html
        assert "commercial parity" in fcm_preview_viewer_html
        assert "review-grade lite" in fcm_preview_viewer_html
        assert (
            "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step." in fcm_preview_viewer_html
            or
            "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains." in fcm_preview_viewer_html
            or "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains." in fcm_preview_viewer_html
            or
            "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains." in fcm_preview_viewer_html
            or "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in fcm_preview_viewer_html
            or "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in fcm_preview_viewer_html
        )
        assert "exact promotion gate" in fcm_preview_viewer_html
        assert "Confidence Guardrail" in fcm_preview_viewer_html
        assert (
            "viewer-ready decoded preview" in fcm_preview_viewer_html
            or
            "exact recovered topology candidate" in fcm_preview_viewer_html
            or "topology-grounded preview candidate" in fcm_preview_viewer_html
            or "payload-exact member-add preview candidate" in fcm_preview_viewer_html
        )
        assert (
            "Use this for baseline-only 3D navigation, source lineage review, and bridge evidence checks." in fcm_preview_viewer_html
            or
            "Use this for topology-level reading, member-add lineage review, and final verified-preview gating." in fcm_preview_viewer_html
            or
            "Use this for table-grounded layout reading, member-add lineage review, and decoded preview triage." in fcm_preview_viewer_html
            or "Use this for member-add topology reading, table-grounded layout review, and promotion gating." in fcm_preview_viewer_html
        )
        assert (
            "Do not silently promote it to exact recovered authoring topology without the separate topology uplift evidence." in fcm_preview_viewer_html
            or
            "Do not call this verified bridge geometry or full authoring topology until the remaining verified gate is closed." in fcm_preview_viewer_html
            or
            "Do not call this verified or exact recovered topology until the remaining upgrade gate is closed." in fcm_preview_viewer_html
            or "Do not call this verified or fully recovered authoring topology until the remaining promotion gate is closed." in fcm_preview_viewer_html
        )
        assert "Source Lineage Ribbon" in fcm_preview_viewer_html
        assert "registered source page" in fcm_preview_viewer_html
        assert "decoded inventory preview" in fcm_preview_viewer_html
        assert "preview bridge report" in fcm_preview_viewer_html
    assert "Heuristic Geometry Preview" in (out_dir / "entries" / "binary_preview_midas_support_rc_house_archive.html").read_text(encoding="utf-8")
    assert "Decoded Inventory Snapshot" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert "Decoded Inventory Snapshot" in (out_dir / "entries" / "binary_inventory_midas_support_fcm_bridge_archive.html").read_text(encoding="utf-8")
    assert "Archive Member Evaluations" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert "Derived 3D Cases" in (out_dir / "entries" / "source_midas_generator_33_github.html").read_text(encoding="utf-8")
    assert "Adapter Readiness" in (out_dir / "entries" / "source_midas_support_beam_archive.html").read_text(encoding="utf-8")
    assert "binary adapter scaffold ready" in (out_dir / "entries" / "source_midas_support_beam_archive.html").read_text(encoding="utf-8")
    assert "Heuristic Geometry Preview" in (out_dir / "entries" / "source_midas_support_rc_house_archive.html").read_text(encoding="utf-8")
    assert "Heuristic XY preview" in (out_dir / "entries" / "source_midas_support_rc_house_archive.html").read_text(encoding="utf-8")
    assert "xVPNT" in (out_dir / "entries" / "source_midas_support_rc_house_archive.html").read_text(encoding="utf-8")
    assert "Heuristic Geometry Preview" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert (
        "unverified table-local preview" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
        or "verified preview" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    )
    assert "Binary Preview Variant Cross-Check" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert "archive variant overlay" in (out_dir / "entries" / "binary_inventory_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert (
        "verified preview ready" in (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
        or
        "exact recovered topology candidate + cross-check" in (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
        or
        "topology-grounded preview + cross-check" in (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
        or "payload-exact member-add preview + cross-check" in (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    )
    assert "Upgrade Guidance" in (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert "Preview Trust Snapshot" in (out_dir / "entries" / "source_midas_support_ramp_archive.html").read_text(encoding="utf-8")
    assert "3d fidelity" in beam_preview_viewer_html
    assert "density" in beam_preview_viewer_html
    assert "visibility" in beam_preview_viewer_html
    assert "readiness" in beam_preview_viewer_html
    assert "hidden detail" in beam_preview_viewer_html
    assert "source status" in beam_preview_viewer_html
    assert "cross-check" in beam_preview_viewer_html
    assert "CURRENT_CASE_FAMILY" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_STATE_LABEL" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_DENSITY_TIER" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_DENSITY_LABEL" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_FIDELITY_LABEL" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_VISIBILITY_LABEL" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_READINESS_LABEL" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_HIDDEN_DETAIL_LABEL" in beam_preview_viewer_html
    assert "CURRENT_PREVIEW_RECOMMENDED_VISIBILITY_MODE" in beam_preview_viewer_html
    assert "getSupportPreviewRenderAssist" in beam_preview_viewer_html
    assert "collectSupportPreviewLabelPoints" in beam_preview_viewer_html
    assert "sparse assist on" in beam_preview_viewer_html
    assert "fidelity=hint-guided preview | density=sparse preview geometry" in html
    assert (
        "verified preview ready" in html
        or
        "exact recovered topology candidate + cross-check" in html
        or "payload-exact member-add preview + cross-check" in html
    )
    assert (
        "readiness=hint preview candidate | assist=trace" in html
        or "readiness=hint preview + cross-check | assist=trace" in html
    )
    assert "Why This 3D Looks Lighter" in beam_preview_viewer_html
    assert "featured entries" in html
    assert "verified=" in html
    assert "hint=" in html
    assert "all=" in html
    assert "deep=" in html
    assert "no_preview=" not in html  # runtime summary string uses visible counts, top summary carries counts in JSON
    assert "crosscheck=" in html
    assert "filter=verified preview entries" not in html
    assert "type mismatch rows=none" in html
    assert "Story-Zone Structural Map" in html
    assert "Interactive XYZ Structure Viewer" in html
    assert "Before-Optimization Structural Baseline" in html
    assert "Baseline Story Slice" in html
    assert "Baseline Category Filter" in html
    assert "Baseline Preset" in html
    assert "Baseline Sync" in html
    assert "Baseline Detail Level" in html
    assert "data-filter-group='baseline-story-slice'" in html
    assert "data-filter-block='baseline-story-slice'" in html
    assert "data-filter-group='baseline-category'" in html
    assert "data-filter-group='baseline-preset'" in html
    assert "data-filter-group='baseline-sync'" in html
    assert "data-filter-group='baseline-detail-level'" in html
    assert "baseline-preset-row" in html
    assert "baseline-reading-order" in html
    assert "baseline-reading-chip" in html
    assert "is-preset-card" in html
    assert "preset-mini" in html
    assert "preset-mini-frame" in html
    assert "preset-mini-vertical" in html
    assert "baseline-preset-help" in html
    assert "data-help-text='beam과 column 위주로 골조 흐름을 먼저 읽는 기본 보기입니다." in html
    assert "all categories" in html
    assert "beam+column" in html
    assert "column+wall" in html
    assert "recommended start" in html
    assert "vertical focus" in html
    assert "full overview" in html
    assert "vertical focus" in html
    assert "overlay story" in html
    assert "3d slice" in html
    assert "quiet slab" in html
    assert "balanced" in html
    assert "full" in html
    assert "baseline_visible=" in html
    assert "baseline_summary=beam=" in html
    assert "baseline-summary-row" in html
    assert "baseline-summary-chip" in html
    assert "baseline-summary-swatch.beam" in html
    assert "data-baseline-summary-category" in html
    assert "Baseline in 3D" in html
    assert "baseline-3d-launch" in html
    assert "baseline-open-3d" in html
    assert "baseline-open-3d-compare" in html
    assert "Open baseline only in 3D" in html
    assert "Open baseline+after 3D" in html
    assert "slice=all" in html
    assert "preset=frame-focus" in html
    assert "sync=overlay+3d" in html
    assert "viewer는 frame focus로 시작해 beam/column 골조를 먼저 읽게 합니다." in html
    assert "보조 뷰는 기본 축소 상태로 두고" in html
    assert "정적 `Isometric XYZ`는 방향 미리보기입니다." in html
    assert "Plan XY로 골조 흐름 먼저 확인" in html
    assert "Elevation XZ로 수직 계통 점검" in html
    assert "Isometric XYZ로 공간감 최종 확인" in html
    assert "Changed Member Overlay" in html
    assert "쉽게 보면 `live_types`는 실제 최적화 대상 전체" in html
    assert "overlay-mini-guide" in html
    assert "Click To Inspect" in html
    assert "Action Family Filter" in html
    assert "Change Locator" in html
    assert "groups=2 | members=2" in html
    assert "visible_groups=2 | visible_members=2" in html
    assert "overlay-change-locator-groups" in html
    assert "overlay-change-locator-group" in html
    assert "overlay-change-locator-group-summary" in html
    assert "overlay-change-locator-group-focus" in html
    assert "overlay-change-locator-group-representatives" in html
    assert "overlay-change-locator-representative" in html
    assert "overlay-change-locator-group-impact-pill is-good" in html
    assert "overlay-change-locator-group-summary-line" in html
    assert "기준으로 먼저 묶어 본 그룹입니다." in html
    assert "overlay-group-focus-banner" in html
    assert "현재 그룹 포커스" in html
    assert "overlay-group-focus-metrics" in html
    assert "그룹 포커스 해제" in html
    assert "이 그룹만 보기" in html
    assert "대표 member를 바로 눌러 상세로 이동하거나" in html
    assert "overlay가 그 그룹 기준으로 자동 좁혀집니다" in html
    assert "costΔ total=" in html
    assert "constructabilityΔ total=" in html
    assert "대표 수정:" in html
    assert "overlay-change-locator-row" in html
    assert "같은 자리 / 단면·두께 조정" in html
    assert "같은 자리 / 배근·디테일 조정" in html
    assert "section W300 -> W250" in html
    assert "thickness x1.00 -> x0.92" in html
    assert "rebar 0.012 -> 0.007" in html
    assert "Layer Toggle" in html
    assert "wheel로 확대/축소, drag로 pan" in html
    assert "Zoom In" in html
    assert "Zoom Out" in html
    assert "Fit Frame" in html
    assert "Fit Selected" in html
    assert "id='interactive-3d-fit-selected' disabled aria-disabled='true'" in html
    assert "fitSelectedWasReady = false" in html
    assert "pulseFitSelectedButton" in html
    assert "pulseSelectedStatusPill" in html
    assert ".overlay-view-button.is-ready-pulse" in html
    assert "@keyframes fitSelectedReadyPulse" in html
    assert ".interactive-3d-status-pill.is-ready-pulse" in html
    assert "@keyframes selectedStatusReadyPulse" in html
    assert "Full Screen" in html
    assert "Reset View" in html
    assert "Isometric XYZ" in html
    assert "Interactive 3D XYZ" in html
    assert "Interactive XYZ structure viewer" in html
    assert "interactive-3d-canvas" in html
    assert "width='1360' height='720'" in html
    assert "interactive-3d-data" in html
    assert "interactive-3d-mode-banner" in html
    assert "baseline vs changed compare" in html
    assert "baseline_raw=" in html
    assert "lod_step=" in html
    assert "live_types=" in html
    assert "geometry_mapped_groups=" in html
    assert "unmapped_live_types=" in html
    assert "dataset group mapping이 없으면 `unmapped_live_types`로" in html
    assert "Story Slice Filter" in html
    assert "3D Camera" in html
    assert "Baseline 3D Quick Toggle" in html
    assert "baseline-3d-quick-row" in html
    assert "baseline-3d-quick-chip" in html
    assert "frame lines" in html
    assert "vertical supports" in html
    assert "plates / floor" in html
    assert "core / shear" in html
    assert "data-filter-group='story-3d-slice'" in html
    assert "data-filter-group='interactive-3d-camera'" in html
    assert "data-filter-block='baseline-3d-quick'" in html
    assert "data-filter-block='story-3d-slice'" in html
    assert "data-filter-block='interactive-3d-camera'" in html
    assert "data-filter-block='baseline-3d-category'" in html
    assert "data-filter-block='after-3d-family'" in html
    assert "data-filter-block='interactive-3d-layer'" in html
    assert "camera-mini-auto" in html
    assert "camera-mini-top" in html
    assert "camera-mini-oblique" in html
    assert "camera-mini-frame" in html
    assert "slice-aware" in html
    assert "plan bias" in html
    assert "balanced" in html
    assert "beam/column" in html
    assert "slice=" in html
    assert "interactive-3d-legend" in html
    assert "baseline ghost" in html
    assert "changed overlay" in html
    assert "selected member" in html
    assert "X/Y/Z orientation axis" in html
    assert "data-filter-group='baseline-3d-category'" in html
    assert "data-filter-group='after-3d-family'" in html
    assert "data-filter-group='interactive-3d-layer'" in html
    assert "interactive-3d-status-pill" in html
    assert "interactive-3d-status-help" in html
    assert "data-interactive-3d-pill" in html
    assert "data-help-text=" in html
    assert "interactive-3d-status-pill::after" in html
    assert ".case-drift-pill-action::after" in html
    assert ".case-evidence-link.is-guided" in html
    assert ".case-evidence-link.is-featured" in html
    assert "case-evidence-group-title" in html
    assert "case-evidence-links-featured" in html
    assert "case-evidence-corner-badge" in html
    assert "case-evidence-quick-row" in html
    assert "case-evidence-quick-chip" in html
    assert "case-evidence-quick-chip-kicker" in html
    assert "case-evidence-quick-chip-label" in html
    assert "case-evidence-role-row" in html
    assert "case-evidence-role-badge" in html
    assert "case-evidence-role-badge-priority" in html
    assert "case-evidence-preview" in html
    assert "case-evidence-preview-badge" in html
    assert "case-evidence-preview-meta" in html
    assert "case-evidence-actions" in html
    assert "case-evidence-action-chip" in html
    assert "case-evidence-action-chip-primary" in html
    assert "data-interactive-3d-pill='camera']::after" in html
    assert "data-interactive-3d-pill='zoom']::after" in html
    assert "data-interactive-3d-pill='fidelity']::after" in html
    assert "data-interactive-3d-pill='readiness']::after" in html
    assert "data-interactive-3d-pill='exactness']::after" in html
    assert "data-interactive-3d-pill='density']::after" in html
    assert "data-interactive-3d-pill='assist']::after" in html
    assert "data-interactive-3d-pill='same-family']::after" in html
    assert "interactive3DStatusPill('camera', 'camera'" in html
    assert "interactive3DStatusPill('zoom', 'zoom'" in html
    assert "interactive3DStatusPill('fidelity', 'fidelity'" in html
    assert "interactive3DStatusPill('readiness', 'readiness'" in html
    assert "interactive3DStatusPill('density', 'density'" in html
    assert "interactive3DStatusPill('assist', 'assist'" in html
    assert "interactive3DStatusPill('baseline', 'baseline'" in html
    assert "interactive3DStatusPill('selected', 'selected'" in html
    assert "same group" in html
    assert "same family" in html
    assert "pick member" in html
    assert "focusCaseHotspotStory" in html
    assert "focusCaseEvidenceKey" in html
    assert "pulseZoneCellsForStory" in html
    assert "pulseStoryRowsForStory" in html
    assert "handleInteractive3DStatusPill" in html
    assert "pulseGuidedElement(interactive3DDetailPanel || interactive3DCanvas);" in html
    assert "INTERACTIVE_3D_MAX_ZOOM = 8.5" in html
    assert "adjustInteractive3DZoom" in html
    assert "zoomInteractive3DAtPoint" in html
    assert "toggleInteractive3DFullscreen" in html
    assert "resizeInteractive3DCanvas" in html
    assert "recenterInteractive3DToPoint" in html
    assert "focusInteractive3DRow" in html
    assert "focusInteractive3DSelection" in html
    assert "focusFilterBlock" in html
    assert "cycleInteractive3DCameraPreset" in html
    assert "setInteractive3DStatusHelp" in html
    assert "scrollStoryRowsIntoViewForCategory" in html
    assert "pulseStoryRow" in html
    assert "interactive3DCameraPreset === 'auto' ? 'default' : interactive3DCameraPreset" in html
    assert "wheel은 커서 기준으로 확대/축소됩니다." in html
    assert "Zoom In/Out, Fit Selected, Full Screen도 함께 쓸 수 있습니다." in html
    assert "hover로 inspect, click changed member로 기존 detail panel과 동기화합니다." in html
    assert "더블클릭하면 해당 부재 쪽으로 바로 들어갑니다." in html
    assert "3D Pick Detail" in html
    assert "3D Change Reading" in html
    assert "interactive-3d-change-reading" in html
    assert "interactive-3d-detail-grid" in html
    assert "interactive-3d-detail-layer" in html
    assert "interactive-3d-detail-member" in html
    assert "interactive-3d-detail-group-family" in html
    assert "interactive-3d-detail-type-hint" in html
    assert "interactive-3d-detail-where" in html
    assert "interactive-3d-detail-optimization" in html
    assert "interactive-3d-detail-spatial" in html
    assert "interactive-3d-detail-modification" in html
    assert "interactive-3d-detail-before-after" in html
    assert "interactive3DSelected.afterFamily.clear()" in html
    assert "interactive3DSelected.storyBand.add(storyBandLabel)" in html
    assert "focusInteractive3DSelection();" in html
    assert "clearOverlayGroupFocusState();" in html
    assert "group focus cleared" in html
    assert "overlay-view-focus-badge" in html
    assert "overlay-view-focus-badge-plan" in html
    assert "overlay-view-focus-badge-elevation" in html
    assert "overlay-view-focus-badge-isometric" in html
    assert "현재 그룹 포커스 적용 중:" in html
    assert "focused · ${storyLabel}/${zoneLabel}" in html
    assert "interactive-3d-detail-keychanges" in html
    assert "interactive-3d-detail-keychanges-list" in html
    assert "interactive-3d-detail-comparison" in html
    assert "interactive-3d-detail-comparison-table" in html
    assert "interactive-3d-floating-summary" in html
    assert "interactive-3d-floating-summary-title" in html
    assert "interactive-3d-floating-summary-pills" in html
    assert "interactive-3d-floating-summary-meta" in html
    assert "같은 자리 부재의 단면·두께·배근·디테일 같은 속성을 조정한 최적화" in html
    assert "Baseline Isometric XYZ" in html
    assert "baseline-frame-primary" in html
    assert "baseline-side-stack" in html
    assert "baseline-frame-secondary" in html
    assert "baseline-secondary-header" in html
    assert "baseline-secondary-preview" in html
    assert "baseline-secondary-body" in html
    assert "baseline-secondary-toggle" in html
    assert "data-baseline-secondary-view='elevation'" in html
    assert "data-baseline-secondary-view='isometric'" in html
    assert "data-baseline-secondary-toggle='elevation'" in html
    assert "data-baseline-secondary-toggle='isometric'" in html
    assert "Expand view" in html
    assert "색 vs 회색" in html
    assert "맵 / 표 연동" in html
    assert "Before vs After" in html
    assert "Filters" in html
    assert "Selected Member" in html
    assert "visible_members=2" in html
    assert "story_sync=baseline:auto" in html
    assert "cell_filter=all" in html
    assert "visible_rows=2" in html
    assert "data-filter-group='family'" in html
    assert "data-filter-group='layer'" in html
    assert "data-member-type='wall'" in html
    assert "data-cost-delta='-10.5'" in html
    assert "data-group-member-count='1'" in html
    assert "data-group-index='0'" in html
    assert "data-story-band='4'" in html
    assert "data-zone-label='perimeter'" in html
    assert "overlay-detail-member" in html
    assert "changed-member-overlay-panel" in html
    assert "focusTypeMismatch" in html
    assert "type-mismatch-focus-button" in html
    assert "overlay-detail-group-cluster" in html
    assert "overlay-detail-action-gate" in html
    assert "overlay-detail-family-cluster" in html
    assert "overlay-detail-family-aggregate" in html
    assert "overlay-detail-group-metrics" in html
    assert "overlay-detail-provenance" in html
    assert "overlay-detail-summary" in html
    assert "overlay-detail-summary-copy" in html
    assert "overlay-detail-action-note" in html
    assert "overlay-detail-change-semantics-copy" in html
    assert "overlay-detail-spatial-read-copy" in html
    assert "overlay-detail-metric-notes" in html
    assert "overlay-detail-group-metrics-note" in html
    assert "overlay-detail-family-aggregate-note" in html
    assert "overlay-detail-provenance-note" in html
    assert "overlay-detail-deltas-note" in html
    assert "overlay-detail-summary-reason" in html
    assert "overlay-detail-summary-gate" in html
    assert "overlay-detail-summary-clause" in html
    assert "overlay-detail-summary-cost" in html
    assert "overlay-detail-summary-constructability" in html
    assert "overlay-detail-summary-cost-icon" in html
    assert "overlay-detail-summary-constructability-icon" in html
    assert "overlay-detail-highlight-pills-wrap" in html
    assert "overlay-detail-highlight-pills" in html
    assert "overlay-detail-transition-grid" in html
    assert "overlay-detail-transition-geometry" in html
    assert "overlay-detail-transition-rebar" in html
    assert "overlay-detail-transition-response" in html
    assert "overlay-detail-transition-impact" in html
    assert "overlay-detail-keychanges" in html
    assert "overlay-detail-keychanges-list" in html
    assert "overlay-detail-comparison" in html
    assert "overlay-detail-comparison-table" in html
    assert "수정 방식" in html
    assert "배근 / 디테일" in html
    assert "응답 변화" in html
    assert "영향 요약" in html
    assert "핵심 변화 3줄 요약" in html
    assert "핵심 증감" in html
    assert "정량 변화표" in html
    assert "단면 변경" in html
    assert "두께 절감" in html
    assert "배근 절감" in html
    assert "비용 절감" in html
    assert "overlay-detail-priority-note" in html
    assert "overlay-detail-more" in html
    assert "overlay-detail-grid-secondary" in html
    assert "한 줄 요약" in html
    assert "어떻게 최적화했는지" in html
    assert "위치 해석" in html
    assert "벽 두께 조정" in html
    assert "배근량 감소" in html
    assert "하드 게이트 통과" in html
    assert "배치 내 개선폭 기준 선택" in html
    assert "overlay-selection-callout" in html
    assert "overlay-selection-callout-pills" in html
    assert "overlay-selection-callout-pill" in html
    assert "data-overlay-callout='plan'" in html
    assert "data-overlay-callout='elevation'" in html
    assert "data-overlay-callout='isometric'" in html
    assert "data-overlay-callout-role='pills'" in html
    assert "buildOverlayCalloutMeta" in html
    assert "게이트:" in html
    assert "두께 절감" in html
    assert "DCR 완화" in html
    assert "stroke-dasharray:10 6" in html
    assert "ctx.setLineDash([10, 8]);" in html
    assert "선택 이유" in html
    assert "비용" in html
    assert "시공성" in html
    assert "추가 상세 열기" in html
    assert "핵심 먼저=member | zone | family | action | cost" in html
    assert "추가 상세=group | provenance | runtime" in html
    assert "OK" in html
    assert "buildOverlayActionNote" in html
    assert "buildOverlayChangeSemanticsNote" in html
    assert "buildOverlaySpatialReadNote" in html
    assert "buildGroupMetricsNote" in html
    assert "buildFamilyAggregateNote" in html
    assert "buildProvenanceNote" in html
    assert "buildDeltasNote" in html
    assert "Group Metrics 쉽게 보기" in html
    assert "Family Aggregate 쉽게 보기" in html
    assert "Provenance 쉽게 보기" in html
    assert "Cost / Constructability 쉽게 보기" in html
    assert ".overlay-mini-guide { grid-template-columns:1fr; }" in html
    assert ".overlay-change-locator { grid-template-columns:1fr; }" in html
    assert ".overlay-change-locator-group-head { display:grid; grid-template-columns:1fr; }" in html
    assert ".overlay-detail-empty { font-size:15px; line-height:1.7; }" in html
    assert ".overlay-detail-summary-copy { font-size:15px; line-height:1.72; }" in html
    assert ".overlay-detail-action-note { font-size:14px; line-height:1.72; padding:12px; }" in html
    assert ".overlay-detail-more > summary { font-size:14px; padding:13px 14px; }" in html
    assert ".overlay-detail-grid { grid-template-columns:1fr; }" in html
    assert ".overlay-detail-metric-notes { grid-template-columns:1fr; }" in html
    assert ".overlay-detail-transition-grid { grid-template-columns:1fr; }" in html
    assert ".overlay-detail-value { font-size:15px; line-height:1.55; }" in html
    assert "계열 조정안이며" in html
    assert "setSummaryTagTone" in html
    assert "resolveChangeSemanticsBundle" in html
    assert "focusLocatorMember" in html
    assert "is-ok" in html
    assert "is-warn" in html
    assert "is-neutral" in html
    assert "buildOverlayDetailSummary" in html
    assert "Release / Runtime" in html
    assert "Ready Vector" in html
    assert "Boundary / Queue" in html
    assert "Benchmark / Delivery" in html
    assert "overlay-detail-change-artifact-link" in html
    assert "Open Change Artifact JSON" in html
    assert "analysis evidence one-page" in html
    assert "source model JSON" in html
    assert "External Expert Mode" in html
    assert "Sheet-Style Drawing Package" in html
    assert "Release Gap JSON" in html
    assert "Committee Dashboard" in html
    assert "Benchmark Manifest" in html
    assert "Benchmark Status" in html
    assert "queue_pending=2" in html
    assert "hinge=ready | panel=ready | foundation=ready | wind=ready" in html
    assert "execution_complete_no_fail | completed=10 | failed=0 | not_run=0" in html
    assert "overlay-before" in html
    assert "overlay-after" in html
    assert "baseline-segment" in html
    assert "compare-after-segment" not in html
    assert "overlay-tooltip" in html
    assert "legend-chip" in html
    assert "zone-cell' data-story-band='4' data-zone-label='perimeter'" in html
    assert "data-member-types='wall'" in html
    assert "story-change-row' data-story-band='4' data-zone-label='perimeter' data-member-type='wall'" in html
    assert "is-baseline-story-linked" in html
    assert "is-baseline-category-preview" in html
    assert "is-pulse-focus" in html
    assert ".zone-cell.is-pulse-focus" in html
    assert "@keyframes zoneCellPulse" in html
    assert "data-action-name='wall_thickness'" in html
    assert "data-family-member-count='1'" in html
    assert "data-family-cost-delta-total='8.6'" in html
    assert "data-family-constructability-delta-total='0.0'" in html
    assert "data-family-zone-count='1'" in html
    assert "is-selected-filter" in html
    assert "is-family-linked" in html
    assert "is-family-zone-linked" in html
    assert "is-baseline-story-linked" in html
    assert "is-hover-preview" in html
    assert "cell_filter=preview:" in html
    assert "applyBaselineFilters" in html
    assert "toggleBaselineStorySlice" in html
    assert "toggleBaselineCategory" in html
    assert "setBaselinePreset" in html
    assert "focusBaselineSummaryCategory" in html
    assert "baselineSummaryHoverCategory" in html
    assert "interactive3DSelected.baselineCategory.clear()" in html
    assert "interactive3DSelected.baselineCategory.add(category)" in html
    assert "previewLinked" in html
    assert "pill을 누르면 관련 제어로 바로 이동하거나 카메라 preset을 순환합니다." in html
    assert "toggleBaselineSync" in html
    assert "setBaselineDetailLevel" in html
    assert "toggleBaselineSecondaryView" in html
    assert "baselineSecondaryState" in html
    assert "openBaselineInteractive3D" in html
    assert "setInteractive3DMode(mode);" in html
    assert "INITIAL_INTERACTIVE_3D_MODE" in html
    assert "applyInteractive3DSliceCameraPreset" in html
    assert "getInteractive3DCameraLabel" in html
    assert "baseline-visible-summary" in html
    assert "detail=quiet-slab" in html
    assert "slab/wall은 더 옅은 ghost 수준으로 뒤에 둡니다." in html
    assert "보조 뷰는 기본 축소 상태로 두고" in html
    assert "기본은 접혀 있고" in html
    assert "data-story-band-label='S04'" in html
    assert "setHoverCellFilter(cell, true)" in html
    assert "toggleInteractive3DBaselineCategory" in html
    assert "toggleInteractive3DAfterFamily" in html
    assert "toggleInteractive3DLayer" in html
    assert "resetInteractive3DViewFrame" in html
    assert "findInteractive3DHit" in html
    assert "distancePointToSegment" in html
    assert "drawInteractive3DAxisTriad" in html
    assert "rotate3DVector" in html
    assert "selected member" in html
    assert "interactive3DStatusPill('same-group', 'same group'" in html
    assert "interactive3DStatusPill('same-family', 'same family'" in html
    assert "interactive3DStatusPill('exactness', 'exactness'" in html
    assert "same group cluster" in html
    assert "Presentation One-Page" in onepage
    assert "Featured Evidence" in onepage
    assert "Program Truth" in onepage
    assert "Supporting Evidence" in onepage
    assert "External Expert Mode" in onepage
    assert "Project Registry" in onepage
    assert "Batch Job Report" in onepage
    assert "Workflow Breadth JSON" in onepage
    assert "Expert Validation Dashboard" in onepage
    assert "Sheet-Style Drawing Package" in onepage
    assert "Validation Boundary" in onepage
    assert "geometry handoff and validation route overview" in onepage
    assert "release provenance and sign-off boundary" in onepage
    assert "drawing-first before/after review route" in onepage
    assert "Why The Hysteresis Is Framed This Way" in onepage
    assert "overflow / unstable regime" in onepage
    assert "solver instability suspicion" in onepage
    assert "FigJam Wireframe" in onepage
    assert "same action family" in html
    assert "pulseGuidedElement" in html
    assert "storyBandLabel" in html
    assert "renderInteractive3D" in html
    assert "<svg" in html
    assert "Review Boundary" in html
    assert "assignee=unassigned" in html
    assert "groups=2" in html
    assert "Analysis Evidence Gallery" in html
    assert "accepted objects" in beam_viewer_html
    assert "bridge ready" in beam_viewer_html
    assert "family assumption" in beam_viewer_html
    assert "accepted types=" in beam_viewer_html
    assert "geometry bridge report" in beam_viewer_html
    assert "registered source page" in beam_viewer_html
    assert "status-pills" in rc_house_source_html
    assert "selected member" in rc_house_source_html
    assert "source table" in rc_house_source_html
    assert "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY" in rc_house_source_html
    assert "geometry preview" in rc_house_source_html
    assert "First 3D Promotion Live" in rc_house_source_html
    assert "inspect promoted baseline 3D and tighten exact topology confidence" in rc_house_source_html
    assert "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology." in rc_house_source_html
    assert "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step." in rc_house_source_html
    assert "status-pills" in ramp_source_html
    assert "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD" in ramp_source_html
    assert "PASS_TABLE_DIRECTORY_ONLY" in ramp_source_html
    assert "geometry preview" in ramp_source_html
    assert "Preview Trust Snapshot" in ramp_source_html
    assert "topology readiness" in ramp_source_html
    assert "missing member refs" in ramp_source_html
    assert (
        "Verified preview surface only: safe for baseline-only 3D reading and bridge evidence review, but still not exact recovered authoring topology." in ramp_source_html
        or
        "Exact recovered topology candidate only: safe for topology-level reading, member-add lineage review, and near-final decoded preview comparison, but not yet a verified bridge claim." in ramp_source_html
        or
        "Topology-grounded candidate only: safe for member-add layout and lineage reading, but not yet a verified or exact topology claim." in ramp_source_html
        or "Payload-exact member-add candidate only: safe for member-add topology and lineage reading, but not yet a verified recovered topology or full bridge claim." in ramp_source_html
    )
    assert (
        "Decode-readiness: viewer-ready preview exists. Exact topology uplift remains a separate evidence step." in ramp_source_html
        or
        "Decode-readiness: exact recovered topology candidate is visible, but verified preview confirmation still remains." in ramp_source_html
        or "Decode-readiness: exact recovered topology candidate + cross-check is visible, but verified preview confirmation still remains." in ramp_source_html
        or
        "Decode-readiness: topology-grounded member-add preview is visible with no known missing path/reference counts, but exact topology confirmation still remains." in ramp_source_html
        or "Decode-readiness: payload-exact member-add preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in ramp_source_html
        or "Decode-readiness: payload-exact member-add topology preview is visible with no known missing path/reference counts, but full-file verified topology confirmation still remains." in ramp_source_html
    )


def test_preview_state_generalization_and_trust_hints() -> None:
    viewer = _load_viewer_module()

    trust = viewer._preview_trust_fields(
        {
            "geometry_preview_mode": "mcvl_node_hint_preview",
            "mcvl_hint_preview_probe": {
                "source_table": "NODE/ELEM hinted ranges",
                "candidate_scalar_count": 15,
                "candidate_point_count": 5,
                "projection_label": "XY",
                "hint_grouping_phase": 0,
            },
        },
        {"mode": "mcvl_node_hint_preview"},
        "NODE/ELEM hinted ranges",
    )
    assert trust["probe_label"] == "mcvl hint probe"
    assert trust["rows"][0] == {"label": "grounding tier", "value": "hint-guided preview"}
    assert trust["rows"][1] == {"label": "hint point source trace", "value": "NODE/ELEM hinted ranges"}
    assert {"label": "scalar count", "value": "15"} in trust["rows"]
    assert {"label": "grouping phase", "value": "0"} in trust["rows"]

    assert viewer._preview_mode_default_state("table_local_xyz_preview") == "unverified table-local preview"
    assert viewer._preview_surface_bucket("unverified table-local preview") == "table-local-preview"
    assert viewer._preview_grounding_label("unverified table-local preview", "table_local_ascii_preview") == "source-grounded table-local preview"
    surface = viewer._preview_surface_fields(
        "unverified table-local preview",
        {"topology_preview_ready": True, "topology_readiness_label": "topology-grounded member-add preview"},
    )
    assert surface["preview_surface_status_label"] == "topology-grounded preview-derived 3d candidate"
    assert surface["preview_readiness_stage_label"] == "topology-grounded preview candidate"
    exact_surface = viewer._preview_surface_fields(
        "unverified table-local preview",
        {"exact_topology_candidate": True, "topology_preview_ready": True, "topology_readiness_label": "payload-exact member-add topology preview"},
    )
    assert exact_surface["preview_surface_status_label"] == "exact recovered topology-derived 3d candidate"
    assert exact_surface["preview_readiness_stage_label"] == "exact recovered topology candidate"
    readiness = viewer._binary_readiness_fields(
        {
            "entry_id": "source_future_table_local_case",
            "catalog_group": "Registered Design Sources",
            "metadata": {
                "binary_preview_state_label": "unverified table-local preview",
                "binary_bridge_crosscheck_quality_label": "moderate silhouette match",
                "binary_decoded_inventory_contract_ready": True,
                "binary_decoded_inventory_ready": False,
                "binary_selected_preview_quality": {"label": "topology-grounded preview"},
                "binary_preview_topology_ready": True,
                "binary_preview_topology_readiness_label": "topology-grounded member-add preview",
            },
        }
    )
    assert readiness["binary_readiness_stage_label"] == "topology-grounded preview + cross-check"
    assert readiness["binary_next_step"] == "validate exact member-add topology confidence and promote to verified preview"
    assert readiness["binary_readiness_score"] == 90
    assert readiness["binary_upgrade_priority"] == 86
    exact_readiness = viewer._binary_readiness_fields(
        {
            "entry_id": "source_exact_table_local_case",
            "catalog_group": "Registered Design Sources",
            "metadata": {
                "binary_preview_state_label": "unverified table-local preview",
                "binary_bridge_crosscheck_quality_label": "moderate silhouette match",
                "binary_decoded_inventory_contract_ready": True,
                "binary_decoded_inventory_ready": False,
                "binary_preview_topology_ready": True,
                "binary_preview_topology_readiness_label": "payload-exact member-add topology preview",
                "binary_preview_exact_topology_candidate": True,
            },
        }
    )
    assert exact_readiness["binary_readiness_stage_label"] == "exact recovered topology candidate + cross-check"
    assert exact_readiness["binary_next_step"] == "close the final verified preview gate on top of the exact recovered topology candidate"
    assert exact_readiness["binary_readiness_score"] == 96
    assert exact_readiness["binary_upgrade_priority"] == 58

    beam_readiness = viewer._binary_readiness_fields(
        {
            "entry_id": "source_midas_support_beam_archive",
            "catalog_group": "Registered Design Sources",
            "metadata": {
                "binary_preview_state_label": "unverified hint preview",
                "binary_bridge_crosscheck_quality_label": "weak silhouette match",
                "binary_decoded_inventory_contract_ready": True,
                "binary_decoded_inventory_ready": False,
                "binary_node_elem_probe": {"node": {"range_start": 1}, "elem": {"range_start": 2}},
            },
        }
    )
    ramp_readiness = viewer._binary_readiness_fields(
        {
            "entry_id": "source_midas_support_ramp_archive",
            "catalog_group": "Registered Design Sources",
            "metadata": {
                "binary_preview_state_label": "unverified raw preview",
                "binary_bridge_crosscheck_quality_label": "strong silhouette match",
                "binary_decoded_inventory_contract_ready": True,
                "binary_decoded_inventory_ready": False,
            },
        }
    )
    assert beam_readiness["binary_readiness_score"] > readiness["binary_readiness_score"] > ramp_readiness["binary_readiness_score"]
    assert beam_readiness["binary_upgrade_priority"] > ramp_readiness["binary_upgrade_priority"] > readiness["binary_upgrade_priority"]
    assert beam_readiness["binary_next_step"] == "decode NODE/ELEM hinted ranges into node coordinates and member connectivity"
    assert ramp_readiness["binary_next_step"] == "resolve PONT/CURV/MEMB block-relative mapping into table-grounded preview + connectivity"


def test_panel_zone_external_validation_surface_distinguishes_advisory_boundary() -> None:
    viewer = _load_viewer_module()

    advisory_surface = viewer._panel_zone_external_validation_surface(
        {
            "panel_zone_3d_clash_ready": True,
            "panel_zone_internal_engine_complete": True,
            "panel_zone_external_validation_pending": True,
            "panel_zone_validation_boundary": "external_validation_only",
        }
    )
    assert advisory_surface["advisory_only"] is True
    assert advisory_surface["release_blocking"] is False
    assert advisory_surface["status_label"] == "advisory_only_boundary"

    verified_surface = viewer._panel_zone_external_validation_surface(
        {
            "panel_zone_3d_clash_ready": True,
            "panel_zone_external_validation_pending": False,
        }
    )
    assert verified_surface["advisory_only"] is False
    assert verified_surface["release_blocking"] is False
    assert verified_surface["status_label"] == "solver_verified"
