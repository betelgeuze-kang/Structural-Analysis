from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_module(path: Path, name: str):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        if sys.path and sys.path[0] == str(path.parent):
            sys.path.pop(0)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_backfill_midas_load_productization_metadata_writes_embedded_payload(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_load_productization_metadata.py",
        "backfill_midas_load_productization_metadata_test",
    )
    artifact = tmp_path / "model.json"
    _write_json(
        artifact,
        {
            "model": {
                "sections": [
                    {"id": 10, "name": "H-400x200", "raw_tokens": ["H-400x200"]},
                    {"id": 11, "name": "SLAB-200", "raw_tokens": ["SLAB-200"]},
                ],
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 10, "node_ids": [1, 2]},
                    {"id": 202, "family": "slab", "section_id": 11, "node_ids": [1, 2, 3, 4]},
                ],
                "loads": {
                    "static_load_cases": [
                        {"name": "DEAD", "type": "D"},
                        {"name": "LIVE", "type": "L"},
                    ],
                    "load_cases": [
                        {"name": "DEAD", "category": "Static"},
                        {"name": "LIVE", "category": "Live"},
                    ],
                    "load_combinations": [
                        {
                            "name": "ULS1",
                            "limit_state": "strength",
                            "combination_type": "GEN",
                            "referenced_cases": ["DEAD", "LIVE"],
                            "referenced_combinations": [],
                            "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6},
                            "factor_map": {"DEAD": 1.2, "LIVE": 1.6},
                            "expansion_mode": "linear_combination",
                            "expansion_depth": 1,
                            "referenced_leaf_cases": ["DEAD", "LIVE"],
                            "expression": "1.2(D) + 1.6(L)",
                        }
                    ],
                    "load_combination_graph": {
                        "node_count": 3,
                        "edge_count": 2,
                        "combo_node_count": 1,
                        "case_node_count": 2,
                        "nodes": [
                            {"id": "COMBO:ULS1", "kind": "combo", "name": "ULS1"},
                            {"id": "CASE:DEAD", "kind": "case", "name": "DEAD"},
                            {"id": "CASE:LIVE", "kind": "case", "name": "LIVE"},
                        ],
                        "edges": [
                            {"src": "COMBO:ULS1", "dst": "CASE:DEAD", "kind": "case_factor", "factor": 1.2},
                            {"src": "COMBO:ULS1", "dst": "CASE:LIVE", "kind": "case_factor", "factor": 1.6},
                        ],
                    },
                    "nodal_loads": [
                        {"load_case": "LIVE", "node_ids": [1, 2], "fx": 0.0, "fy": 0.0, "fz": -12.0, "mx": 0.0, "my": 0.0, "mz": 0.0}
                    ],
                    "selfweight": [
                        {"load_case": "DEAD", "gx": 0.0, "gy": 0.0, "gz": -1.0}
                    ],
                    "pressure_loads": [],
                    "semantic_load_summary": {
                        "case_force_summaries": [
                            {"load_case": "DEAD", "semantic_status": "bound"},
                            {"load_case": "LIVE", "semantic_status": "bound"},
                        ]
                    },
                },
                "metadata": {"load_colors": [{"case_name": "DEAD"}]},
            }
        },
    )

    summary = module.backfill_artifact(artifact, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    metadata = ((updated.get("model") or {}).get("metadata") or {})

    assert summary["written"] is True
    assert summary["patterns"] == 2
    assert summary["combos"] == 1
    assert summary["editor_combo_nodes"] == 1
    assert summary["editor_case_nodes"] == 2
    assert summary["editor_edges"] == 2
    assert isinstance(metadata.get("load_pattern_library"), dict)
    assert isinstance(metadata.get("load_combination_editor_seed"), dict)
    assert metadata["load_combination_editor_seed"]["summary"]["graph_edge_count"] == 2


def test_backfill_midas_load_productization_metadata_recovers_raw_combinations(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_load_productization_metadata.py",
        "backfill_midas_load_productization_metadata_test_raw_recovery",
    )
    artifact = tmp_path / "model.json"
    _write_json(
        artifact,
        {
            "model": {
                "metadata": {},
                "load_combinations_raw": [
                    "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0",
                    "ST, DEAD, 1.2, ST, LIVE, 1.6",
                    "NAME=ENV1, GEN, ACTIVE, 0, 0, ENV(ULS1), 0, 0, 0",
                    "CB, ULS1, 1",
                ],
            }
        },
    )

    summary = module.backfill_artifact(artifact, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    loads = ((updated.get("model") or {}).get("loads") or {})
    metadata = ((updated.get("model") or {}).get("metadata") or {})

    assert summary["supported"] is True
    assert summary["recovery_mode"] == "combination_only_raw_recovery"
    assert summary["patterns"] == 2
    assert summary["combos"] == 2
    assert summary["editor_combo_nodes"] == 2
    assert summary["editor_case_nodes"] == 2
    assert loads["provenance"] == "combination_only_raw_recovery"
    assert [row["name"] for row in loads["static_load_cases"]] == ["DEAD", "LIVE"]
    assert [row["name"] for row in loads["load_cases"]] == ["DEAD", "LIVE"]
    assert loads["load_combination_graph"]["combo_node_count"] == 2
    assert loads["load_combination_graph"]["case_node_count"] == 2
    assert loads["semantic_load_summary"]["case_count"] == 2
    assert loads["load_combinations"][0]["name"] == "ENV1"
    assert loads["load_combinations"][1]["name"] == "ULS1"
    assert loads["load_combinations"][1]["entries"][0]["reference_kind"] == "ST"
    assert metadata["load_pattern_library"]["provenance"] == "combination_only_raw_recovery"
    assert metadata["load_combination_editor_seed"]["provenance"] == "combination_only_raw_recovery"
    assert metadata["load_contract_recovery"]["mode"] == "combination_only_raw_recovery"
    assert metadata["load_pattern_library"]["pattern_summary"]["primitive_count"] == 0
    assert metadata["load_combination_editor_seed"]["combination_nodes"][1]["name"] == "ULS1"

    second_summary = module.backfill_artifact(artifact, write=False)

    assert second_summary["supported"] is True
    assert second_summary["recovery_mode"] == "combination_only_raw_recovery"
    assert second_summary["patterns"] == 2
    assert second_summary["combos"] == 2
    assert second_summary["changed"] is False


def test_backfill_midas_load_productization_metadata_skips_unsupported_artifact(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_load_productization_metadata.py",
        "backfill_midas_load_productization_metadata_test_unsupported",
    )
    artifact = tmp_path / "model.json"
    _write_json(artifact, {"model": {"metadata": {"section_library": {"summary": {"used_section_count": 1}}}}})

    summary = module.backfill_artifact(artifact, write=True)

    assert summary["supported"] is False
    assert summary["missing_load_contract"] is True
    assert summary["written"] is False


def test_enrich_kds_geometry_bridge_full_crosswalk_metadata_merges_exact_registry_inventory(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "parse_midas_mgt_to_json_npz_test_exact_inventory",
    )
    monkeypatch.setattr(
        module,
        "_build_exact_kds_geometry_bridge_mapping_index",
        lambda: {
            ("pair", "C-EX-001", "C-EX-001"): {
                "review_member_id": "C-EX-001",
                "review_case_id": "C-EX-001",
                "full_crosswalk_member_groups": ["horizontal_beam"],
                "full_crosswalk_member_handles": ["1", "2", "3"],
                "full_crosswalk_section_groups": ["horizontal_beam"],
                "full_crosswalk_section_ids": ["11", "22", "33"],
                "full_crosswalk_load_combination_names": ["ULS1"],
            }
        },
    )

    payload = {
        "model": {
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 10.0, "y": 0.0, "z": 0.0},
                {"id": 4, "x": 15.0, "y": 0.0, "z": 0.0},
            ],
            "sections": [
                {"id": 11, "name": "B1"},
                {"id": 22, "name": "B2"},
                {"id": 33, "name": "B3"},
            ],
            "elements": [
                {"id": 101, "family": "beam", "section_id": 11, "node_ids": [1, 2]},
                {"id": 102, "family": "beam", "section_id": 22, "node_ids": [2, 3]},
                {"id": 103, "family": "beam", "section_id": 33, "node_ids": [3, 4]},
            ],
            "loads": {"load_combinations": [{"name": "ULS1"}]},
            "metadata": {
                "members": [
                    {"id": "1", "element_seed": "101", "element_ids": ["101"]},
                    {"id": "2", "element_seed": "102", "element_ids": ["102"]},
                    {"id": "3", "element_seed": "103", "element_ids": ["103"]},
                ]
            },
        }
    }
    bridge = {
        "bridge_rows": [
            {
                "review_member_id": "C-EX-001",
                "review_case_id": "C-EX-001",
                "review_keys": ["C-EX-001"],
                "baseline_focus_member_id": "101",
                "source_member_type": "beam",
                "source_topology_type": "rahmen",
                "source_element_mix": "beam_only",
                "source_hazard_type": "wind",
                "review_geometry_snapshot": {"section_id": "11"},
            }
        ]
    }

    enriched = module.enrich_kds_geometry_bridge_full_crosswalk_metadata(payload, bridge)
    row = enriched["bridge_rows"][0]
    summary = enriched["summary"]

    assert row["full_crosswalk_member_groups"] == ["horizontal_beam"]
    assert row["full_crosswalk_member_handles"] == ["1", "2", "3"]
    assert row["full_crosswalk_section_groups"] == ["horizontal_beam"]
    assert row["full_crosswalk_section_ids"] == ["11", "22", "33"]
    assert row["full_crosswalk_load_combination_names"] == ["ULS1"]
    assert summary["full_member_crosswalk_count"] == 3
    assert summary["full_member_crosswalk_expected"] == 3
    assert summary["full_member_crosswalk_status"] == "PASS"
    assert summary["full_section_crosswalk_count"] == 3
    assert summary["full_section_crosswalk_expected"] == 3
    assert summary["full_section_crosswalk_status"] == "PASS"
    assert summary["full_load_crosswalk_count"] == 1
    assert summary["full_load_crosswalk_expected"] == 1
    assert summary["full_load_crosswalk_status"] == "PASS"


def test_backfill_artifact_embeds_exact_geometry_inventory(monkeypatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parse_module = _load_module(
        repo_root / "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "parse_midas_mgt_to_json_npz_test_backfill_exact_inventory",
    )
    monkeypatch.setattr(
        parse_module,
        "_build_exact_kds_geometry_bridge_mapping_index",
        lambda: {
            ("pair", "C-EX-002", "C-EX-002"): {
                "review_member_id": "C-EX-002",
                "review_case_id": "C-EX-002",
                "full_crosswalk_member_groups": ["horizontal_beam"],
                "full_crosswalk_member_handles": ["1", "2", "3"],
                "full_crosswalk_section_groups": ["horizontal_beam"],
                "full_crosswalk_section_ids": ["11", "22", "33"],
                "full_crosswalk_load_combination_names": ["ULS1"],
            }
        },
    )
    monkeypatch.setitem(sys.modules, "parse_midas_mgt_to_json_npz", parse_module)

    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_load_productization_metadata.py",
        "backfill_midas_load_productization_metadata_test_exact_inventory",
    )
    artifact = tmp_path / "model.json"
    _write_json(
        artifact,
        {
            "model": {
                "nodes": [
                    {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                    {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 10.0, "y": 0.0, "z": 0.0},
                    {"id": 4, "x": 15.0, "y": 0.0, "z": 0.0},
                ],
                "sections": [
                    {"id": 11, "name": "B1", "raw_tokens": ["B1"]},
                    {"id": 22, "name": "B2", "raw_tokens": ["B2"]},
                    {"id": 33, "name": "B3", "raw_tokens": ["B3"]},
                ],
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 11, "node_ids": [1, 2]},
                    {"id": 102, "family": "beam", "section_id": 22, "node_ids": [2, 3]},
                    {"id": 103, "family": "beam", "section_id": 33, "node_ids": [3, 4]},
                ],
                "loads": {
                    "static_load_cases": [{"name": "DEAD", "type": "D"}],
                    "load_cases": [{"name": "DEAD", "category": "Dead"}],
                    "load_combinations": [
                        {
                            "name": "ULS1",
                            "limit_state": "strength",
                            "combination_type": "GEN",
                            "referenced_cases": ["DEAD"],
                            "referenced_combinations": [],
                            "expanded_factor_map": {"DEAD": 1.2},
                            "factor_map": {"DEAD": 1.2},
                            "expansion_mode": "linear_combination",
                            "expansion_depth": 1,
                            "referenced_leaf_cases": ["DEAD"],
                            "expression": "1.2(D)",
                        }
                    ],
                    "load_combination_graph": {
                        "node_count": 2,
                        "edge_count": 1,
                        "combo_node_count": 1,
                        "case_node_count": 1,
                        "nodes": [
                            {"id": "COMBO:ULS1", "kind": "combo", "name": "ULS1"},
                            {"id": "CASE:DEAD", "kind": "case", "name": "DEAD"},
                        ],
                        "edges": [
                            {"src": "COMBO:ULS1", "dst": "CASE:DEAD", "kind": "case_factor", "factor": 1.2}
                        ],
                    },
                    "nodal_loads": [],
                    "selfweight": [{"load_case": "DEAD", "gx": 0.0, "gy": 0.0, "gz": -1.0}],
                    "pressure_loads": [],
                    "semantic_load_summary": {"case_force_summaries": [{"load_case": "DEAD", "semantic_status": "bound"}]},
                },
                "metadata": {
                    "members": [
                        {"id": "1", "element_seed": "101", "element_ids": ["101"]},
                        {"id": "2", "element_seed": "102", "element_ids": ["102"]},
                        {"id": "3", "element_seed": "103", "element_ids": ["103"]},
                    ],
                    "kds_geometry_bridge": {
                        "bridge_rows": [
                            {
                                "review_member_id": "C-EX-002",
                                "review_case_id": "C-EX-002",
                                "review_keys": ["C-EX-002"],
                                "baseline_focus_member_id": "101",
                                "source_member_type": "beam",
                                "source_topology_type": "rahmen",
                                "source_element_mix": "beam_only",
                                "source_hazard_type": "wind",
                                "review_geometry_snapshot": {"section_id": "11"},
                            }
                        ]
                    },
                },
            }
        },
    )

    summary = module.backfill_artifact(artifact, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    metadata = ((updated.get("model") or {}).get("metadata") or {})
    bridge = metadata["kds_geometry_bridge"]
    row = bridge["bridge_rows"][0]

    assert summary["supported"] is True
    assert summary["geometry_full_member_crosswalk_count"] == 3
    assert summary["geometry_full_member_crosswalk_expected"] == 3
    assert summary["geometry_full_member_crosswalk_status"] == "PASS"
    assert summary["geometry_full_section_crosswalk_count"] == 3
    assert summary["geometry_full_section_crosswalk_expected"] == 3
    assert summary["geometry_full_section_crosswalk_status"] == "PASS"
    assert row["full_crosswalk_member_handles"] == ["1", "2", "3"]
    assert row["full_crosswalk_section_ids"] == ["11", "22", "33"]
    assert row["full_crosswalk_load_combination_names"] == ["ULS1"]


def test_backfill_midas_load_productization_metadata_embeds_full_crosswalk_inventory(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_load_productization_metadata.py",
        "backfill_midas_load_productization_metadata_test_geometry_crosswalk",
    )
    artifact = tmp_path / "model.json"
    _write_json(
        artifact,
        {
            "model": {
                "nodes": [
                    {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                    {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 5.0, "y": 4.0, "z": 0.0},
                ],
                "sections": [
                    {"id": 10, "name": "B1"},
                    {"id": 20, "name": "B2"},
                    {"id": 30, "name": "BR1"},
                ],
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 10, "node_ids": [1, 2]},
                    {"id": 102, "family": "beam", "section_id": 20, "node_ids": [2, 3]},
                    {"id": 103, "family": "brace", "section_id": 30, "node_ids": [1, 3]},
                ],
                "loads": {
                    "static_load_cases": [
                        {"name": "DEAD", "type": "D"},
                        {"name": "LIVE", "type": "L"},
                    ],
                    "load_cases": [
                        {"name": "DEAD", "category": "Static"},
                        {"name": "LIVE", "category": "Live"},
                    ],
                    "load_combinations": [
                        {
                            "name": "ULS1",
                            "limit_state": "strength",
                            "combination_type": "GEN",
                            "referenced_cases": ["DEAD"],
                            "referenced_combinations": [],
                            "expanded_factor_map": {"DEAD": 1.2},
                            "factor_map": {"DEAD": 1.2},
                            "expansion_mode": "linear_combination",
                            "expansion_depth": 1,
                            "referenced_leaf_cases": ["DEAD"],
                            "expression": "1.2(D)",
                        },
                        {
                            "name": "SVC1",
                            "limit_state": "service",
                            "combination_type": "GEN",
                            "referenced_cases": ["LIVE"],
                            "referenced_combinations": [],
                            "expanded_factor_map": {"LIVE": 1.0},
                            "factor_map": {"LIVE": 1.0},
                            "expansion_mode": "linear_combination",
                            "expansion_depth": 1,
                            "referenced_leaf_cases": ["LIVE"],
                            "expression": "1.0(L)",
                        },
                    ],
                    "load_combination_graph": {"node_count": 0, "edge_count": 0, "combo_node_count": 0, "case_node_count": 0},
                    "nodal_loads": [],
                    "selfweight": [],
                    "pressure_loads": [],
                    "semantic_load_summary": {"case_force_summaries": []},
                },
                "metadata": {
                    "members": [
                        {"id": "M1", "element_seed": "101", "element_ids": ["101"]},
                        {"id": "M2", "element_seed": "102", "element_ids": ["102"]},
                        {"id": "M3", "element_seed": "103", "element_ids": ["103"]},
                    ],
                    "kds_geometry_bridge": {
                        "summary": {},
                        "bridge_rows": [
                            {
                                "review_member_id": "C-TRN-001",
                                "review_case_id": "C-TRN-001",
                                "baseline_focus_member_id": "101",
                                "source_member_type": "beam",
                                "source_topology_type": "rahmen",
                                "source_element_mix": "beam_only",
                                "review_geometry_snapshot": {"section_id": "10"},
                                "row_provenance_combination_names": ["ULS1"],
                            },
                            {
                                "review_member_id": "C-BRC-001",
                                "review_case_id": "C-BRC-001",
                                "baseline_focus_member_id": "103",
                                "source_member_type": "brace",
                                "source_topology_type": "truss",
                                "source_element_mix": "beam_only",
                                "review_geometry_snapshot": {"section_id": "30"},
                                "row_provenance_combination_names": ["SVC1"],
                            },
                        ],
                    },
                },
            }
        },
    )

    summary = module.backfill_artifact(artifact, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    bridge = ((((updated.get("model") or {}).get("metadata") or {}).get("kds_geometry_bridge")) or {})
    rows = bridge.get("bridge_rows") or []

    assert summary["supported"] is True
    assert summary["geometry_full_member_crosswalk_count"] == 3
    assert summary["geometry_full_member_crosswalk_expected"] == 3
    assert summary["geometry_full_member_crosswalk_status"] == "PASS"
    assert summary["geometry_full_section_crosswalk_count"] == 3
    assert summary["geometry_full_section_crosswalk_expected"] == 3
    assert summary["geometry_full_section_crosswalk_status"] == "PASS"
    assert summary["geometry_full_load_crosswalk_count"] == 2
    assert summary["geometry_full_load_crosswalk_expected"] == 2
    assert summary["geometry_full_load_crosswalk_status"] == "PASS"
    assert bridge["summary"]["full_member_crosswalk_handles"] == ["M1", "M2", "M3"]
    assert bridge["summary"]["full_section_crosswalk_ids"] == ["10", "20", "30"]
    assert bridge["summary"]["full_load_crosswalk_names"] == ["SVC1", "ULS1"]
    assert rows[0]["baseline_focus_member_id"] == "101"
    assert rows[0]["full_crosswalk_member_groups"] == ["horizontal_beam"]
    assert rows[0]["full_crosswalk_member_handles"] == ["M1", "M2"]
    assert rows[0]["full_crosswalk_section_groups"] == ["horizontal_beam"]
    assert rows[0]["full_crosswalk_section_ids"] == ["10", "20"]
    assert rows[1]["full_crosswalk_member_groups"] == ["plan_diagonal"]
    assert rows[1]["full_crosswalk_member_handles"] == ["M3"]
    assert rows[1]["full_crosswalk_section_ids"] == ["30"]
