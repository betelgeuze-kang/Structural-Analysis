from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/build_kds_geometry_bridge_registry.py"
    spec = importlib.util.spec_from_file_location("build_kds_geometry_bridge_registry_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_kds_geometry_bridge_registry_generates_heuristic_case_profile_mappings() -> None:
    module = _load_module()
    model_payload = {
        "model": {
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 10.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 0.0, "y": 10.0, "z": 0.0},
                {"id": 4, "x": 0.0, "y": 0.0, "z": 10.0},
                {"id": 5, "x": 8.0, "y": 8.0, "z": 0.0},
                {"id": 6, "x": 0.0, "y": 12.0, "z": 0.0},
            ],
            "elements": [
                {"id": 101, "family": "beam", "section_id": 11, "node_ids": [1, 2]},
                {"id": 202, "family": "beam", "section_id": 22, "node_ids": [1, 5]},
                {"id": 303, "family": "beam", "section_id": 33, "node_ids": [1, 4]},
                {"id": 404, "family": "beam", "section_id": 44, "node_ids": [1, 6]},
            ],
            "metadata": {
                "members": [
                    {"id": 7, "element_seed": 101, "element_ids": [101]},
                    {"id": 8, "element_seed": 202, "element_ids": [202]},
                    {"id": 9, "element_seed": 303, "element_ids": [303]},
                    {"id": 10, "element_seed": 404, "element_ids": [404]},
                ]
            },
        }
    }
    benchmark_payload = {
        "cases": [
            {"case_id": "C-TRN-001", "source_family": "commercial_export", "topology_type": "rahmen", "hazard_type": "wind", "element_mix": "beam_only"},
            {"case_id": "C-TRN-002", "source_family": "commercial_export", "topology_type": "truss", "hazard_type": "wind", "element_mix": "beam_only"},
            {"case_id": "C-TST-001", "source_family": "commercial_export", "topology_type": "outrigger", "hazard_type": "seismic", "element_mix": "shell_beam_mix"},
        ]
    }
    code_check_report = {
        "member_check_rows": [
            {
                "member_id": "C-TRN-001",
                "case_id": "C-TRN-001",
                "member_type": "beam",
                "hazard_type": "wind",
                "topology_type": "rahmen",
                "rule_family": "strength",
                "combination": "KDS_ULS_1",
                "component": "axial_force_kN",
                "clause": "KDS-AXIAL-001",
                "dcr": 0.42,
            },
            {
                "member_id": "C-TRN-002",
                "case_id": "C-TRN-002",
                "member_type": "brace",
                "hazard_type": "wind",
                "topology_type": "truss",
                "rule_family": "strength",
                "combination": "KDS_ULS_3_WX+",
                "component": "combined_interaction",
                "clause": "KDS-INT-FRAME-001",
                "dcr": 0.51,
            },
            {
                "member_id": "C-TST-001",
                "case_id": "C-TST-001",
                "member_type": "column",
                "hazard_type": "seismic",
                "topology_type": "outrigger",
                "rule_family": "serviceability",
                "combination": "SVC_DRIFT",
                "component": "drift_ratio_pct",
                "clause": "KDS-SVC-DRIFT-001",
                "dcr": 0.61,
            },
        ]
    }

    registry = module.build_registry(
        model_payload=model_payload,
        benchmark_payload=benchmark_payload,
        code_check_report=code_check_report,
    )

    assert registry["source"] == "heuristic_semantic_case_profile_registry"
    assert registry["summary"]["mapping_count"] == 3
    assert registry["summary"]["full_member_crosswalk_count"] == 4
    assert registry["summary"]["full_member_crosswalk_expected"] == 4
    assert registry["summary"]["full_member_crosswalk_status"] == "PASS"
    assert registry["summary"]["full_member_crosswalk_handle_kind"] == "aggregate_member_id"
    assert registry["summary"]["full_member_crosswalk_handles"] == ["10", "7", "8", "9"]
    assert registry["summary"]["full_member_crosswalk_expected_handles"] == ["10", "7", "8", "9"]
    assert registry["summary"]["full_member_crosswalk_missing_handles"] == []
    assert registry["summary"]["full_section_crosswalk_count"] == 4
    assert registry["summary"]["full_section_crosswalk_expected"] == 4
    assert registry["summary"]["full_section_crosswalk_status"] == "PASS"
    assert registry["summary"]["full_section_crosswalk_ids"] == ["11", "22", "33", "44"]
    assert registry["summary"]["full_section_crosswalk_expected_ids"] == ["11", "22", "33", "44"]
    assert registry["summary"]["full_section_crosswalk_missing_ids"] == []
    assert registry["summary"]["full_load_crosswalk_count"] == 3
    assert registry["summary"]["full_load_crosswalk_expected"] == 3
    assert registry["summary"]["full_load_crosswalk_status"] == "PASS"
    assert registry["summary"]["full_load_crosswalk_names"] == ["KDS_ULS_1", "KDS_ULS_3_WX+", "SVC_DRIFT"]
    assert registry["summary"]["full_load_crosswalk_expected_names"] == ["KDS_ULS_1", "KDS_ULS_3_WX+", "SVC_DRIFT"]
    assert registry["summary"]["full_load_crosswalk_missing_names"] == []
    assert registry["summary"]["full_member_crosswalk_handles_by_group"] == {
        "horizontal_beam": ["10", "7"],
        "plan_diagonal": ["8"],
        "vertical": ["9"],
    }
    assert registry["summary"]["full_section_crosswalk_ids_by_group"] == {
        "horizontal_beam": ["11", "44"],
        "plan_diagonal": ["22"],
        "vertical": ["33"],
    }
    assert registry["summary"]["full_crosswalk_summary_label"] == (
        "members=4/4 PASS | sections=4/4 PASS | loads=3/3 PASS"
    )
    rows = {row["review_case_id"]: row for row in registry["mappings"]}
    assert rows["C-TRN-001"]["baseline_focus_member_id"] == "101"
    assert rows["C-TRN-001"]["match_confidence"] == "heuristic_case_profile"
    assert rows["C-TRN-001"]["selector_kind"] == "x_beam_surrogate"
    assert rows["C-TRN-001"]["row_provenance_row_count"] == 1
    assert rows["C-TRN-001"]["row_provenance_combination_names"] == ["KDS_ULS_1"]
    assert rows["C-TRN-001"]["member_inventory_member_type_names"] == ["beam"]
    assert rows["C-TRN-001"]["review_keys_label"] == "C-TRN-001"
    assert rows["C-TRN-001"]["full_crosswalk_target_member_handle"] == "7"
    assert rows["C-TRN-001"]["full_crosswalk_target_section_id"] == "11"
    assert rows["C-TRN-001"]["full_crosswalk_member_groups"] == ["horizontal_beam"]
    assert rows["C-TRN-001"]["full_crosswalk_member_handles"] == ["10", "7"]
    assert rows["C-TRN-001"]["full_crosswalk_member_handle_count"] == 2
    assert rows["C-TRN-001"]["full_crosswalk_section_groups"] == ["horizontal_beam"]
    assert rows["C-TRN-001"]["full_crosswalk_section_ids"] == ["11", "44"]
    assert rows["C-TRN-001"]["full_crosswalk_section_id_count"] == 2
    assert rows["C-TRN-001"]["full_crosswalk_load_combination_names"] == ["KDS_ULS_1"]
    assert rows["C-TRN-001"]["full_crosswalk_load_combination_count"] == 1
    assert rows["C-TRN-001"]["full_crosswalk_global_member_handles"] == ["10", "7", "8", "9"]
    assert rows["C-TRN-001"]["full_crosswalk_global_member_handle_count"] == 4
    assert rows["C-TRN-001"]["full_crosswalk_global_section_ids"] == ["11", "22", "33", "44"]
    assert rows["C-TRN-001"]["full_crosswalk_global_section_id_count"] == 4
    assert rows["C-TRN-001"]["full_crosswalk_global_load_combination_names"] == ["KDS_ULS_1", "KDS_ULS_3_WX+", "SVC_DRIFT"]
    assert rows["C-TRN-001"]["full_crosswalk_global_load_combination_count"] == 3
    assert rows["C-TRN-001"]["full_crosswalk_inventory_scope"] == "selector_group"
    assert rows["C-TRN-001"]["full_crosswalk_global_inventory_scope"] == "model_and_codecheck_expected"
    assert rows["C-TRN-002"]["baseline_focus_member_id"] == "202"
    assert rows["C-TRN-002"]["selector_kind"] == "plan_diagonal_surrogate"
    assert rows["C-TRN-002"]["full_crosswalk_target_member_handle"] == "8"
    assert rows["C-TRN-002"]["full_crosswalk_member_handles"] == ["8"]
    assert rows["C-TST-001"]["baseline_focus_member_id"] == "303"
    assert rows["C-TST-001"]["selector_kind"] == "vertical_core_surrogate"
    assert rows["C-TST-001"]["full_crosswalk_target_member_handle"] == "9"
    assert rows["C-TST-001"]["full_crosswalk_member_handles"] == ["9"]
    assert rows["C-TST-001"]["full_crosswalk_section_ids"] == ["33"]


def test_merge_registry_payloads_prefers_reviewer_verified_exact_rows() -> None:
    module = _load_module()
    heuristic_registry = {
        "contract_version": "0.3.0",
        "source": "heuristic_semantic_case_profile_registry",
        "summary": {
            "full_member_crosswalk_expected": 2,
            "full_section_crosswalk_expected": 2,
            "full_load_crosswalk_expected": 2,
            "full_member_crosswalk_handle_kind": "aggregate_member_id",
        },
        "mappings": [
            {
                "review_member_id": "C-TRN-001",
                "review_case_id": "C-TRN-001",
                "review_keys": ["C-TRN-001"],
                "baseline_focus_member_id": "101",
                "surrogate_aggregate_member_id": "7",
                "full_crosswalk_target_member_handle": "7",
                "full_crosswalk_target_section_id": "11",
                "full_crosswalk_load_combination_names": ["KDS_ULS_1"],
                "match_strategy": "heuristic_case_profile_x_beam_surrogate",
                "match_confidence": "heuristic_case_profile",
            },
            {
                "review_member_id": "C-TST-001",
                "review_case_id": "C-TST-001",
                "review_keys": ["C-TST-001"],
                "baseline_focus_member_id": "303",
                "surrogate_aggregate_member_id": "9",
                "full_crosswalk_target_member_handle": "9",
                "full_crosswalk_target_section_id": "33",
                "full_crosswalk_load_combination_names": ["SVC_DRIFT"],
                "match_strategy": "heuristic_case_profile_vertical_core_surrogate",
                "match_confidence": "heuristic_case_profile",
            },
        ],
    }
    explicit_registry = {
        "contract_version": "0.2.0",
        "source": "reviewer_verified_registry",
        "mappings": [
            {
                "review_member_id": "C-TRN-001",
                "review_case_id": "C-TRN-001",
                "review_keys": ["C-TRN-001"],
                "baseline_focus_member_id": "202",
                "match_strategy": "external_registry_manual",
                "match_confidence": "manual_verified",
                "reviewer_verified": True,
                "surrogate_aggregate_member_id": "8",
                "full_crosswalk_target_member_handle": "8",
                "full_crosswalk_target_section_id": "22",
                "full_crosswalk_load_combination_names": ["KDS_ULS_1"],
                "row_provenance_combination_names": ["KDS_ULS_1"],
                "row_provenance_row_count": 3,
                "review_geometry_snapshot": {
                    "section_id": "22",
                    "node_ids": ["1", "5"],
                },
            }
        ],
    }

    merged = module.merge_registry_payloads(heuristic_registry, explicit_registry)

    assert merged["source"] == "merged_registry"
    assert merged["merge_strategy"] == "reviewer_verified_exact_overrides_heuristic_by_review_key"
    assert merged["summary"]["mapping_count"] == 2
    assert merged["summary"]["exact_mapping_count"] == 1
    assert merged["summary"]["heuristic_mapping_count"] == 1
    assert merged["summary"]["reviewer_verified_mapping_count"] == 1
    assert merged["summary"]["full_member_crosswalk_count"] == 2
    assert merged["summary"]["full_member_crosswalk_expected"] == 2
    assert merged["summary"]["full_member_crosswalk_status"] == "PASS"
    assert merged["summary"]["full_member_crosswalk_expected_handles"] == ["8", "9"]
    assert merged["summary"]["full_member_crosswalk_missing_handles"] == []
    assert merged["summary"]["full_section_crosswalk_count"] == 2
    assert merged["summary"]["full_section_crosswalk_expected"] == 2
    assert merged["summary"]["full_section_crosswalk_status"] == "PASS"
    assert merged["summary"]["full_section_crosswalk_expected_ids"] == ["22", "33"]
    assert merged["summary"]["full_section_crosswalk_missing_ids"] == []
    assert merged["summary"]["full_load_crosswalk_count"] == 2
    assert merged["summary"]["full_load_crosswalk_expected"] == 2
    assert merged["summary"]["full_load_crosswalk_status"] == "PASS"
    assert merged["summary"]["full_load_crosswalk_expected_names"] == ["KDS_ULS_1", "SVC_DRIFT"]
    assert merged["summary"]["full_load_crosswalk_missing_names"] == []
    assert merged["summary"]["full_crosswalk_summary_label"] == (
        "members=2/2 PASS | sections=2/2 PASS | loads=2/2 PASS"
    )
    assert merged["summary"]["source_counts"] == {
        "heuristic_semantic_case_profile_registry": 1,
        "reviewer_verified_registry": 1,
    }
    rows = {row["review_case_id"]: row for row in merged["mappings"]}
    assert rows["C-TRN-001"]["baseline_focus_member_id"] == "202"
    assert rows["C-TRN-001"]["match_confidence"] == "manual_verified"
    assert rows["C-TRN-001"]["registry_source_label"] == "reviewer_verified_registry"
    assert rows["C-TRN-001"]["review_geometry_snapshot"]["section_id"] == "22"
    assert rows["C-TRN-001"]["row_provenance_combination_names"] == ["KDS_ULS_1"]
    assert rows["C-TRN-001"]["row_provenance_row_count"] == 3
    assert rows["C-TRN-001"]["full_crosswalk_target_member_handle"] == "8"
    assert rows["C-TRN-001"]["full_crosswalk_target_section_id"] == "22"
    assert rows["C-TST-001"]["baseline_focus_member_id"] == "303"
    assert rows["C-TST-001"]["match_confidence"] == "heuristic_case_profile"
    assert rows["C-TST-001"]["registry_source_label"] == "heuristic_semantic_case_profile_registry"


def test_merge_registry_payloads_ignores_empty_exact_payload() -> None:
    module = _load_module()
    heuristic_registry = {
        "contract_version": "0.3.0",
        "source": "heuristic_semantic_case_profile_registry",
        "summary": {
            "mapping_count": 1,
            "selector_counts": {"x_beam_surrogate": 1},
            "surrogate_geometry_counts": {"x_beam": 1},
            "full_member_crosswalk_expected": 1,
            "full_section_crosswalk_expected": 1,
            "full_load_crosswalk_expected": 1,
            "full_member_crosswalk_handle_kind": "aggregate_member_id",
        },
        "mappings": [
            {
                "review_member_id": "C-TRN-001",
                "review_case_id": "C-TRN-001",
                "review_keys": ["C-TRN-001"],
                "baseline_focus_member_id": "101",
                "surrogate_aggregate_member_id": "7",
                "full_crosswalk_target_member_handle": "7",
                "full_crosswalk_target_section_id": "11",
                "full_crosswalk_load_combination_names": ["KDS_ULS_1"],
                "match_strategy": "heuristic_case_profile_x_beam_surrogate",
                "match_confidence": "heuristic_case_profile",
            }
        ],
    }
    empty_exact_registry = {
        "contract_version": "0.2.0",
        "source": "reviewer_verified_exact_registry",
        "summary": {
            "mapping_count": 0,
            "exact_mapping_count": 0,
            "heuristic_mapping_count": 0,
            "reviewer_verified_mapping_count": 0,
            "source_counts": {},
            "confidence_counts": {},
            "full_member_crosswalk_expected": 1,
            "full_section_crosswalk_expected": 1,
            "full_load_crosswalk_expected": 1,
            "full_member_crosswalk_handle_kind": "aggregate_member_id",
        },
        "mappings": [],
    }

    merged = module.merge_registry_payloads(heuristic_registry, empty_exact_registry)

    assert merged["source"] == "heuristic_semantic_case_profile_registry"
    assert merged["summary"]["mapping_count"] == 1
    assert merged["summary"]["full_member_crosswalk_count"] == 1
    assert merged["summary"]["full_member_crosswalk_expected"] == 1
    assert merged["summary"]["full_member_crosswalk_expected_handles"] == ["7"]
    assert merged["summary"]["full_section_crosswalk_count"] == 1
    assert merged["summary"]["full_section_crosswalk_expected"] == 1
    assert merged["summary"]["full_section_crosswalk_expected_ids"] == ["11"]
    assert merged["summary"]["full_load_crosswalk_count"] == 1
    assert merged["summary"]["full_load_crosswalk_expected"] == 1
    assert merged["summary"]["full_load_crosswalk_expected_names"] == ["KDS_ULS_1"]
    assert merged["mappings"][0]["review_case_id"] == "C-TRN-001"
