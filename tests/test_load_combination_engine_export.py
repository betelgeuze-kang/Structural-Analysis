from __future__ import annotations

from implementation.phase1.load_combination_engine import (
    export_midas_loadcomb_from_editor_seed,
    export_midas_loadcomb_from_model_payload,
    load_combinations_from_midas_model,
    summarize_runtime_combination_model,
)
from implementation.phase1.parse_midas_mgt_to_json_npz import derive_minimal_structured_loads_from_raw_combination_payload


def test_export_midas_loadcomb_from_editor_seed_renders_direct_and_nested_rows() -> None:
    editor_seed = {
        "combination_nodes": [
            {
                "name": "ULS1",
                "editor_stage": 1,
                "combination_type": "GEN",
                "limit_state": "STRENGTH",
                "expression": "1.2(D) + 1.6(L)",
                "entry_rows": [
                    {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.2},
                    {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.6},
                ],
                "factor_map": {"DEAD": 1.2, "LIVE": 1.6},
                "referenced_combinations": [],
            },
            {
                "name": "ENV1",
                "editor_stage": 2,
                "combination_type": "GEN",
                "limit_state": "SERVICE",
                "expression": "expression n/a",
                "entry_rows": [
                    {"reference_kind": "CB", "reference_name": "ULS1", "factor": 1.0},
                ],
                "factor_map": {"DEAD": 1.2, "LIVE": 1.6},
                "referenced_combinations": ["ULS1"],
            },
        ]
    }

    block = export_midas_loadcomb_from_editor_seed(editor_seed)

    assert block.startswith("*LOADCOMB\n")
    assert "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0" in block
    assert "ST, DEAD, 1.2, ST, LIVE, 1.6" in block
    assert "NAME=ENV1, GEN, SERVICE, 0, 1, Envelope refs ULS1, 0, 0, 0" in block
    assert "CB, ULS1, 1" in block


def test_export_midas_loadcomb_from_model_payload_uses_embedded_seed() -> None:
    model_payload = {
        "model": {
            "metadata": {
                "load_combination_editor_seed": {
                    "combination_nodes": [
                        {
                            "name": "SLS1",
                            "editor_stage": 1,
                            "combination_type": "GEN",
                            "limit_state": "SERVICE",
                            "expression": "D + L",
                            "entry_rows": [
                                {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.0},
                                {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.0},
                            ],
                        }
                    ]
                }
            }
        }
    }

    block = export_midas_loadcomb_from_model_payload(model_payload, include_comments=False)

    assert block.startswith("*LOADCOMB\n")
    assert "; NAME=NAME" not in block
    assert "NAME=SLS1, GEN, SERVICE, 0, 0, D + L, 0, 0, 0" in block
    assert "ST, DEAD, 1, ST, LIVE, 1" in block


def test_derive_minimal_structured_loads_from_raw_combination_payload_builds_loads_contract() -> None:
    model_payload = {
        "model": {
            "load_combinations_raw": [
                "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0",
                "ST, DEAD, 1.2, ST, LIVE, 1.6",
                "NAME=ENV1, GEN, SERVICE, 0, 1, expression n/a, 0, 0, 0",
                "CB, ULS1, 1.0",
            ]
        }
    }

    loads = derive_minimal_structured_loads_from_raw_combination_payload(model_payload)

    assert [row["name"] for row in loads["static_load_cases"]] == ["DEAD", "LIVE"]
    assert loads["active_static_case_sequence"] == ["DEAD", "LIVE"]
    assert [row["name"] for row in loads["load_cases"]] == ["DEAD", "LIVE"]
    assert [row["name"] for row in loads["load_combinations"]] == ["ULS1", "ENV1"]
    assert loads["semantic_load_summary"]["case_count"] == 2
    assert loads["semantic_load_summary"]["combination_count"] == 2
    assert all(row["semantic_status"] == "combination_only_raw_recovery" for row in loads["semantic_load_summary"]["case_force_summaries"])
    assert loads["nodal_loads"] == []
    assert loads["selfweight"] == []
    assert loads["pressure_loads"] == []
    assert loads["recovery_contract"]["mode"] == "combination_only_raw_recovery"


def test_export_midas_loadcomb_from_model_payload_uses_helper_generated_minimal_loads() -> None:
    model_payload = {
        "model": {
            "load_combinations_raw": [
                "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0",
                "ST, DEAD, 1.2, ST, LIVE, 1.6",
                "NAME=ENV1, GEN, SERVICE, 0, 1, expression n/a, 0, 0, 0",
                "CB, ULS1, 1.0",
            ]
        }
    }
    model_payload["model"]["loads"] = derive_minimal_structured_loads_from_raw_combination_payload(model_payload)

    combos = load_combinations_from_midas_model(model_payload)
    block = export_midas_loadcomb_from_model_payload(model_payload, include_comments=False)

    assert [combo.name for combo in combos] == ["ULS1", "ENV1"]
    assert combos[0].factors == {"D": 1.2, "L": 1.6}
    assert block.startswith("*LOADCOMB\n")
    assert "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0" in block
    assert "ST, DEAD, 1.2, ST, LIVE, 1.6" in block
    assert "NAME=ENV1, GEN, SERVICE, 0, 1, Envelope refs ULS1, 0, 0, 0" in block
    assert "CB, ULS1, 1" in block


def test_summarize_runtime_combination_model_surfaces_nested_depth_and_unresolved_refs() -> None:
    model_payload = {
        "model": {
            "loads": {
                "load_combinations": [
                    {
                        "name": "ULS1",
                        "combination_type": "GEN",
                        "limit_state": "ULS",
                        "entry_rows": [
                            {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.2},
                            {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.6},
                        ],
                    },
                    {
                        "name": "ENV1",
                        "combination_type": "GEN",
                        "limit_state": "ULS",
                        "entry_rows": [
                            {"reference_kind": "CB", "reference_name": "ULS1", "factor": 1.0},
                        ],
                    },
                    {
                        "name": "ENV2",
                        "combination_type": "GEN",
                        "limit_state": "SERVICE",
                        "entry_rows": [
                            {"reference_kind": "CB", "reference_name": "ENV1", "factor": 1.0},
                            {"reference_kind": "CB", "reference_name": "MISSING", "factor": 0.7},
                        ],
                    },
                ]
            }
        }
    }

    summary = summarize_runtime_combination_model(model_payload)

    assert summary["combo_count"] == 3
    assert summary["linear_combo_count"] == 1
    assert summary["nested_combo_count"] == 2
    assert summary["max_nested_depth"] == 3
    assert summary["runtime_case_names"] == ["D", "L"]
    assert summary["unresolved_reference_names"] == ["MISSING"]
    assert summary["authoring_ready"] is False
    assert "max_depth=3" in summary["summary_line"]
