from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/build_g1_mgt_state_updated_frame_axial_geometry_preflight.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_state_updated_frame_axial_geometry_preflight",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_actual_mgt_preflight_records_exact_fail_closed_blocker() -> None:
    payload = module.build_preflight(repo_root=ROOT)

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["readiness_pass"] is False
    assert payload["diagnostic_execution_ready"] is True
    assert payload["engineer_review_required"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["inputs"]["node_count"] == 13_047
    assert payload["inputs"]["element_count"] == 12_728
    assert payload["inputs"]["analysis_material_table_ids"] == [
        1,
        2,
        3,
        4,
        5,
        7,
    ]
    assert payload["inputs"]["dgn_alias_frame_element_count"] == 79
    assert payload["inputs"]["dgn_alias_frame_material_id_counts"] == [
        {"material_id": 16, "element_count": 5},
        {"material_id": 26, "element_count": 9},
        {"material_id": 27, "element_count": 9},
        {"material_id": 28, "element_count": 14},
        {"material_id": 29, "element_count": 17},
        {"material_id": 30, "element_count": 15},
        {"material_id": 31, "element_count": 10},
    ]
    connectivity = payload["frame_connectivity_audit"]
    assert connectivity["frame_connectivity_source"] == (
        "elem_conn_ptr/elem_conn_idx"
    )
    assert connectivity["edge_index_used_for_element_binding"] is False
    assert connectivity["line_elements_solved"] == 5_572
    assert connectivity["line_element_row_accounting_exact"] is True

    coverage = payload["source_property_coverage_audit"]
    assert coverage["frame_element_count"] == 5_572
    assert coverage["source_section_property_count"] == 183
    assert coverage["source_material_property_count"] == 6
    assert coverage["section_property_resolved_element_count"] == 5_572
    assert coverage["material_property_resolved_element_count"] == 5_493
    assert coverage["resolved_source_property_element_count"] == 5_493
    assert coverage["unresolved_source_property_element_count"] == 79
    assert coverage["source_property_coverage_ratio"] == pytest.approx(
        5_493 / 5_572
    )
    assert coverage["exact_source_property_coverage"] is False
    assert coverage["missing_section_id_counts"] == []
    assert coverage["missing_material_id_counts"] == [
        {"material_id": 16, "element_count": 5},
        {"material_id": 26, "element_count": 9},
        {"material_id": 27, "element_count": 9},
        {"material_id": 28, "element_count": 14},
        {"material_id": 29, "element_count": 17},
        {"material_id": 30, "element_count": 15},
        {"material_id": 31, "element_count": 10},
    ]
    assert coverage["unresolved_element_head"][0] == {
        "element_id": 1261,
        "section_id": 307,
        "material_id": 27,
        "missing_section_property": False,
        "missing_material_property": True,
    }

    alias_audit = payload["dgn_material_property_alias_audit"]
    assert alias_audit["source_material_count"] == 6
    assert alias_audit["dgn_material_row_count"] == 29
    assert alias_audit["existing_source_id_row_count"] == 5
    assert alias_audit["exact_unique_identity_match_row_count"] == 29
    assert alias_audit["alias_material_count"] == 24
    assert alias_audit["unresolved_identity_rows"] == []
    assert alias_audit["ambiguous_identity_rows"] == []
    assert alias_audit["dgn_numeric_elastic_override_consumed_count"] == 0
    assert alias_audit["fuzzy_name_match_count"] == 0
    assert alias_audit["contract_pass"] is True
    assert alias_audit["engineer_review_required"] is True
    resolved_coverage = payload[
        "resolved_source_property_coverage_audit"
    ]
    assert resolved_coverage["source_material_property_count"] == 30
    assert resolved_coverage[
        "resolved_source_property_element_count"
    ] == 5_572
    assert resolved_coverage[
        "unresolved_source_property_element_count"
    ] == 0
    assert resolved_coverage["exact_source_property_coverage"] is True
    assert resolved_coverage["missing_material_id_counts"] == []

    probe = payload["prepack_probe"]
    assert probe["attempted"] is True
    assert probe["succeeded"] is False
    assert probe["expected_fail_closed"] is True
    assert probe["failure_type"] == "ValueError"
    assert probe["failure_reason_code"] == (
        "INCOMPLETE_FRAME_SOURCE_PROPERTY_BINDING"
    )
    assert "unresolved_element_count=79" in probe["failure_message"]
    assert probe["property_fallback_attempted"] is False
    assert probe["property_fallback_count"] == 0
    resolved_probe = payload["resolved_prepack_probe"]
    assert resolved_probe["attempted"] is True
    assert resolved_probe["succeeded"] is True
    assert resolved_probe["expected_fail_closed"] is False
    assert resolved_probe["failure_type"] is None
    assert resolved_probe["failure_reason_code"] is None
    assert resolved_probe["failure_message"] is None
    assert resolved_probe["property_fallback_attempted"] is False
    assert resolved_probe["property_fallback_count"] == 0
    assert payload["claims"][
        "missing_property_prepack_failed_closed"
    ] is True
    assert payload["claims"]["synthetic_property_fallback_used"] is False
    assert payload["claims"][
        "design_material_rows_promoted_to_analysis_properties"
    ] is False
    assert payload["claims"][
        "exact_raw_material_table_frame_property_coverage"
    ] is False
    assert payload["claims"][
        "exact_source_derived_alias_frame_property_coverage"
    ] is True
    assert payload["claims"][
        "dgn_exact_type_name_alias_contract_pass"
    ] is True
    assert payload["claims"][
        "dgn_numeric_elastic_override_consumed"
    ] is False
    assert payload["claims"][
        "dgn_alias_engineer_review_required"
    ] is True
    assert payload["claims"][
        "actual_mgt_state_updated_axial_geometry_prepacked"
    ] is True
    assert payload["claims"]["full_nonlinear_continuation"] is False
    assert payload["claims"]["g1_full_building_closure"] is False
    assert (
        "dgn_exact_type_name_material_inheritance_engineer_review_required"
        in payload["blockers_remaining"]
    )

    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_committed_preflight_is_reproducible() -> None:
    passed, reason = module.check_preflight(repo_root=ROOT)

    assert passed is True, reason
    assert reason == "g1_mgt_state_updated_frame_axial_preflight_consistent"
