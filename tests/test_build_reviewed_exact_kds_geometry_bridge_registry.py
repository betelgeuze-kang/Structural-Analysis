from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/build_reviewed_exact_kds_geometry_bridge_registry.py"
    )
    spec = importlib.util.spec_from_file_location(
        "build_reviewed_exact_kds_geometry_bridge_registry_for_tests",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_reviewed_exact_registry_includes_row_provenance_crosswalk() -> None:
    module = _load_module()
    model_payload = {
        "model": {
            "nodes": [
                {"id": 7868, "x": 140.073, "y": 209.216, "z": 3.7},
                {"id": 7869, "x": 157.371, "y": 209.216, "z": 3.7},
                {"id": 7870, "x": 140.073, "y": 226.514, "z": 3.7},
            ],
            "elements": [
                {
                    "id": 26878,
                    "type": "BEAM",
                    "family": "beam",
                    "section_id": 343,
                    "material_id": 1,
                    "node_ids": [7868, 7869],
                },
                {
                    "id": 26879,
                    "type": "BEAM",
                    "family": "beam",
                    "section_id": 344,
                    "material_id": 1,
                    "node_ids": [7868, 7870],
                },
            ],
            "metadata": {
                "members": [
                    {"id": 9001, "element_seed": 26878, "element_ids": [26878]},
                    {"id": 9002, "element_seed": 26879, "element_ids": [26879]},
                ]
            },
        }
    }
    benchmark_payload = {
        "cases": [
            {
                "case_id": "C-TRN-001",
                "source_family": "commercial_export",
                "topology_type": "rahmen",
                "hazard_type": "wind",
                "element_mix": "beam_only",
            }
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
                "dcr": 0.422,
            },
            {
                "member_id": "C-TRN-001",
                "case_id": "C-TRN-001",
                "member_type": "beam",
                "hazard_type": "wind",
                "topology_type": "rahmen",
                "rule_family": "serviceability",
                "combination": "SVC_DRIFT",
                "component": "drift_ratio_pct",
                "clause": "KDS-SVC-DRIFT-001",
                "dcr": 0.700,
            },
        ]
    }

    registry = module.build_registry(
        model_payload=model_payload,
        code_check_report=code_check_report,
        benchmark_payload=benchmark_payload,
    )

    assert registry["contract_version"] == "0.6.0"
    assert registry["summary"]["exact_mapping_count"] == 1
    assert registry["summary"]["full_member_crosswalk_count"] == 2
    assert registry["summary"]["full_member_crosswalk_expected"] == 2
    assert registry["summary"]["full_member_crosswalk_status"] == "PASS"
    assert registry["summary"]["full_member_crosswalk_handle_kind"] == "aggregate_member_id"
    assert registry["summary"]["full_member_crosswalk_handles"] == ["9001", "9002"]
    assert registry["summary"]["full_member_crosswalk_expected_handles"] == ["9001", "9002"]
    assert registry["summary"]["full_member_crosswalk_missing_handles"] == []
    assert registry["summary"]["full_section_crosswalk_count"] == 2
    assert registry["summary"]["full_section_crosswalk_expected"] == 2
    assert registry["summary"]["full_section_crosswalk_status"] == "PASS"
    assert registry["summary"]["full_section_crosswalk_ids"] == ["343", "344"]
    assert registry["summary"]["full_section_crosswalk_expected_ids"] == ["343", "344"]
    assert registry["summary"]["full_section_crosswalk_missing_ids"] == []
    assert registry["summary"]["full_load_crosswalk_count"] == 2
    assert registry["summary"]["full_load_crosswalk_expected"] == 2
    assert registry["summary"]["full_load_crosswalk_status"] == "PASS"
    assert registry["summary"]["full_load_crosswalk_names"] == ["KDS_ULS_1", "SVC_DRIFT"]
    assert registry["summary"]["full_load_crosswalk_expected_names"] == ["KDS_ULS_1", "SVC_DRIFT"]
    assert registry["summary"]["full_load_crosswalk_missing_names"] == []
    assert registry["summary"]["full_member_crosswalk_handles_by_group"] == {
        "horizontal_beam": ["9001", "9002"]
    }
    assert registry["summary"]["full_section_crosswalk_ids_by_group"] == {
        "horizontal_beam": ["343", "344"]
    }
    assert registry["summary"]["full_crosswalk_summary_label"] == (
        "members=2/2 PASS | sections=2/2 PASS | loads=2/2 PASS"
    )
    row = registry["mappings"][0]
    assert row["review_keys"] == ["C-TRN-001", "C-TRN-001"]
    assert row["review_keys_label"] == "C-TRN-001, C-TRN-001"
    assert row["mapped"] is True
    assert row["member_inventory_count"] == 1
    assert row["member_inventory_member_type_names"] == ["beam"]
    assert row["row_provenance_row_count"] == 2
    assert row["row_provenance_combination_count"] == 2
    assert row["row_provenance_combination_names"] == ["SVC_DRIFT", "KDS_ULS_1"]
    assert row["row_provenance_clause_names"] == ["KDS-SVC-DRIFT-001", "KDS-AXIAL-001"]
    assert row["row_provenance_rule_family_names"] == ["serviceability", "strength"]
    assert row["row_provenance_hazard_names"] == ["wind"]
    assert row["row_provenance_topology_names"] == ["rahmen"]
    assert row["surrogate_aggregate_member_id"] == "9001"
    assert row["full_crosswalk_target_member_handle"] == "9001"
    assert row["full_crosswalk_target_section_id"] == "343"
    assert row["full_crosswalk_member_groups"] == ["horizontal_beam"]
    assert row["full_crosswalk_member_handles"] == ["9001", "9002"]
    assert row["full_crosswalk_member_handle_count"] == 2
    assert row["full_crosswalk_section_groups"] == ["horizontal_beam"]
    assert row["full_crosswalk_section_ids"] == ["343", "344"]
    assert row["full_crosswalk_section_id_count"] == 2
    assert row["full_crosswalk_load_combination_names"] == ["SVC_DRIFT", "KDS_ULS_1"]
    assert row["full_crosswalk_load_combination_count"] == 2
    assert row["full_crosswalk_global_member_handles"] == ["9001", "9002"]
    assert row["full_crosswalk_global_member_handle_count"] == 2
    assert row["full_crosswalk_global_section_ids"] == ["343", "344"]
    assert row["full_crosswalk_global_section_id_count"] == 2
    assert row["full_crosswalk_global_load_combination_names"] == ["KDS_ULS_1", "SVC_DRIFT"]
    assert row["full_crosswalk_global_load_combination_count"] == 2
    assert row["full_crosswalk_inventory_scope"] == "selector_group"
    assert row["full_crosswalk_global_inventory_scope"] == "model_and_codecheck_expected"
    assert row["full_crosswalk_inventory_summary_label"].startswith(
        "groups=members:1/sections:1 | selector=members:2/sections:2/loads:2 | global=members:2/sections:2/loads:2"
    )
    assert row["row_provenance_top_row_label"] == "SVC_DRIFT | drift_ratio_pct | KDS-SVC-DRIFT-001 | D/C=0.700"
    assert row["row_provenance_summary_label"].startswith("rows=2 | combos=2 | clauses=2 | top=SVC_DRIFT")
    assert row["clause_provenance_summary_label"].startswith("clauses=2 | rules=2 | hazards=1 | top=SVC_DRIFT")
    assert len(row["row_provenance_rows"]) == 2
    assert row["review_geometry_snapshot"]["section_id"] == "343"
