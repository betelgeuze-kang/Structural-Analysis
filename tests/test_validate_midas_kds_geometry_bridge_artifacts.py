from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/validate_midas_kds_geometry_bridge_artifacts.py"
    spec = importlib.util.spec_from_file_location("validate_midas_kds_geometry_bridge_artifacts_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_midas_kds_geometry_bridge_artifacts_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_module()
    artifacts: list[Path] = []
    for index, (exact_ids, heuristic_ids, total_ids, rows, strategies, confidence_counts) in enumerate(
        [
            (0, 0, 12, 1056, {"unmapped": 12}, {"none": 12}),
            (2, 0, 12, 1056, {"element_id_direct": 2, "unmapped": 10}, {"exact_id": 2, "none": 10}),
            (0, 12, 12, 1056, {"heuristic_case_profile_vertical_core_surrogate": 12}, {"heuristic_case_profile": 12}),
        ],
        start=1,
    ):
        model_path = tmp_path / f"model_{index}.json"
        _write_json(
            model_path,
            {
                "model": {
                    "metadata": {
                        "kds_geometry_bridge": {
                            "provenance": "kds_codecheck_bridge_metadata",
                            "registry_source_label": "none",
                            "registry_contract_version": "0.1.0",
                            "summary": {
                                "review_id_count": total_ids,
                                "mapped_review_id_count": exact_ids + heuristic_ids,
                                "exact_mapped_review_id_count": exact_ids,
                                "heuristic_mapped_review_id_count": heuristic_ids,
                            "review_row_count": rows,
                            "mapped_row_provenance_count": exact_ids and rows or heuristic_ids and rows or 0,
                            "exact_mapped_row_provenance_count": exact_ids and rows or 0,
                            "heuristic_mapped_row_provenance_count": heuristic_ids and rows or 0,
                            "strategy_counts": strategies,
                            "confidence_counts": confidence_counts,
                                "external_registry_row_count": 0,
                                "external_registry_usable_row_count": 0,
                                "external_registry_exact_row_count": 0,
                                "external_registry_heuristic_row_count": 0,
                                "external_registry_source_counts": {},
                            },
                        }
                    }
                }
            },
        )
        artifacts.append(model_path)

    monkeypatch.setattr(module, "DEFAULT_TARGETS", tuple(artifacts))

    exit_code = module.main([])
    captured = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 0
    assert len(captured) == 3
    assert captured[0].startswith("MIDAS kds-geometry-bridge: ok")
    assert "mapped_review_ids=0/12" in captured[0]
    assert "exact=0 | heuristic=0" in captured[0]
    assert "row_provenance=0/1056" in captured[0]
    assert "strategies=unmapped:12" in captured[0]
    assert "confidence=none:12" in captured[0]
    assert "registry=none 0/0" in captured[0]
    assert "registry_exact=0" in captured[0]
    assert "registry_heuristic=0" in captured[0]
    assert "registry_sources=none" in captured[0]
    assert "section_parity=0/0 PASS" in captured[0]
    assert "load_crosswalk=0/0 PASS" in captured[0]
    assert "semantic_crosswalk=0/0 PASS" in captured[0]
    assert "full_member_crosswalk=0/0 PASS" in captured[0]
    assert "full_section_crosswalk=0/0 PASS" in captured[0]
    assert "full_load_crosswalk=0/0 PASS" in captured[0]
    assert "geometry_diff=0/0 PASS" in captured[0]
    assert str(artifacts[0]) in captured[0]
    assert "mapped_review_ids=2/12" in captured[1]
    assert "exact=2 | heuristic=0" in captured[1]
    assert "row_provenance=1056/1056" in captured[1]
    assert "element_id_direct:2" in captured[1]
    assert "section_parity=0/0 PASS" in captured[1]
    assert "load_crosswalk=0/0 PASS" in captured[1]
    assert "semantic_crosswalk=0/0 PASS" in captured[1]
    assert "full_member_crosswalk=0/0 PASS" in captured[1]
    assert "full_section_crosswalk=0/0 PASS" in captured[1]
    assert "full_load_crosswalk=0/0 PASS" in captured[1]
    assert "geometry_diff=0/0 PASS" in captured[1]
    assert "mapped_review_ids=12/12" in captured[2]
    assert "exact=0 | heuristic=12" in captured[2]
    assert "row_provenance=1056/1056" in captured[2]
    assert "heuristic_case_profile_vertical_core_surrogate:12" in captured[2]
    assert "confidence=heuristic_case_profile:12" in captured[2]
    assert "section_parity=0/0 PASS" in captured[2]
    assert "load_crosswalk=0/0 PASS" in captured[2]
    assert "semantic_crosswalk=0/0 PASS" in captured[2]
    assert "full_member_crosswalk=0/0 PASS" in captured[2]
    assert "full_section_crosswalk=0/0 PASS" in captured[2]
    assert "full_load_crosswalk=0/0 PASS" in captured[2]
    assert "geometry_diff=0/0 PASS" in captured[2]


def test_validate_midas_kds_geometry_bridge_artifacts_detects_threshold_gap(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_module()
    model_path = tmp_path / "model.json"
    _write_json(
        model_path,
        {
            "model": {
                "elements": [
                    {"id": 202, "type": "BEAM", "family": "beam", "section_id": 11, "material_id": 1, "node_ids": [2, 3]},
                    {"id": 303, "type": "COLUMN", "family": "column", "section_id": 12, "material_id": 2, "node_ids": [3, 4]},
                ],
                "metadata": {
                    "members": [
                        {"id": 9001, "element_seed": 202, "element_ids": [202]},
                        {"id": 9002, "element_seed": 303, "element_ids": [303]},
                    ]
                },
                "nodes": [
                    {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 2.0, "y": 0.0, "z": 0.0},
                    {"id": 4, "x": 2.0, "y": 3.0, "z": 0.0},
                ],
                "metadata": {
                    "members": [
                        {"id": 9001, "element_seed": 202, "element_ids": [202]},
                        {"id": 9002, "element_seed": 303, "element_ids": [303]},
                    ],
                    "kds_geometry_bridge": {
                        "provenance": "kds_codecheck_bridge_metadata",
                        "registry_source_label": "reviewer_verified_registry",
                        "registry_contract_version": "0.2.0",
                        "summary": {
                            "review_id_count": 12,
                            "mapped_review_id_count": 0,
                            "exact_mapped_review_id_count": 0,
                            "heuristic_mapped_review_id_count": 0,
                            "review_row_count": 1056,
                            "mapped_row_provenance_count": 0,
                            "exact_mapped_row_provenance_count": 0,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"unmapped": 12},
                            "confidence_counts": {"none": 12},
                            "external_registry_row_count": 3,
                            "external_registry_usable_row_count": 2,
                            "external_registry_exact_row_count": 1,
                            "external_registry_heuristic_row_count": 1,
                            "external_registry_source_counts": {
                                "heuristic_semantic_case_profile_registry": 1,
                                "reviewer_verified_registry": 1,
                            },
                        },
                    }
                }
            }
        },
    )

    monkeypatch.setattr(module, "DEFAULT_TARGETS", (model_path,))

    exit_code = module.main(["--require", "--min-mapped-review-ids", "1"])
    captured = capsys.readouterr().out.strip()

    assert exit_code == 1
    assert captured.startswith("MIDAS kds-geometry-bridge: missing")
    assert "mapped_review_ids=0/12" in captured
    assert "exact=0 | heuristic=0" in captured
    assert "row_provenance=0/1056" in captured
    assert "registry=reviewer_verified_registry 2/3" in captured
    assert "registry_exact=1" in captured
    assert "registry_heuristic=1" in captured
    assert "registry_sources=heuristic_semantic_case_profile_registry:1, reviewer_verified_registry:1" in captured
    assert str(model_path) in captured


def test_validate_midas_kds_geometry_bridge_artifacts_reports_exact_snapshot_coverage(tmp_path: Path) -> None:
    module = _load_module()
    model_path = tmp_path / "model.json"
    _write_json(
        model_path,
        {
            "model": {
                "elements": [
                    {"id": 202, "type": "BEAM", "family": "beam", "section_id": 11, "material_id": 1, "node_ids": [2, 3]},
                    {"id": 303, "type": "COLUMN", "family": "column", "section_id": 12, "material_id": 2, "node_ids": [3, 4]},
                    {"id": 404, "type": "BEAM", "family": "beam", "section_id": 13, "material_id": 1, "node_ids": [2, 5]},
                ],
                "nodes": [
                    {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 2.0, "y": 0.0, "z": 0.0},
                    {"id": 4, "x": 2.0, "y": 3.0, "z": 0.0},
                    {"id": 5, "x": 1.0, "y": 2.0, "z": 0.0},
                ],
                "metadata": {
                    "members": [
                        {"id": 9001, "element_seed": 202, "element_ids": [202]},
                        {"id": 9002, "element_seed": 303, "element_ids": [303]},
                        {"id": 9003, "element_seed": 404, "element_ids": [404]},
                    ],
                    "kds_geometry_bridge": {
                        "provenance": "kds_codecheck_bridge_metadata",
                        "registry_source_label": "reviewer_verified_exact_registry",
                        "registry_contract_version": "0.2.0",
                        "summary": {
                            "review_id_count": 2,
                            "mapped_review_id_count": 2,
                            "exact_mapped_review_id_count": 2,
                            "heuristic_mapped_review_id_count": 0,
                            "review_row_count": 6,
                            "mapped_row_provenance_count": 6,
                            "exact_mapped_row_provenance_count": 6,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"external_registry_manual": 2},
                            "confidence_counts": {"manual_verified": 2},
                            "external_registry_row_count": 2,
                            "external_registry_usable_row_count": 2,
                            "external_registry_exact_row_count": 2,
                            "external_registry_heuristic_row_count": 0,
                            "external_registry_source_counts": {
                                "reviewer_verified_exact_registry": 2,
                            },
                        },
                        "bridge_rows": [
                            {
                                "review_case_id": "C-EXACT-001",
                                "baseline_focus_member_id": "202",
                                "full_crosswalk_target_member_handle": "9001",
                                "full_crosswalk_target_section_id": "11",
                                "full_crosswalk_member_handles": ["9001", "9003"],
                                "full_crosswalk_section_ids": ["11", "13"],
                                "full_crosswalk_load_combination_names": ["KDS_ULS_1"],
                                "match_confidence": "manual_verified",
                                "source_member_type": "beam",
                                "source_hazard_type": "wind",
                                "source_topology_type": "rahmen",
                                "member_inventory_count": 1,
                                "member_inventory_member_type_names": ["beam"],
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_rule_family_count": 1,
                                "row_provenance_hazard_count": 1,
                                "row_provenance_topology_count": 1,
                                "row_provenance_combination_names": ["KDS_ULS_1"],
                                "row_provenance_clause_names": ["KDS-AXIAL-001"],
                                "row_provenance_component_names": ["axial_force_kN"],
                                "row_provenance_rule_family_names": ["strength"],
                                "row_provenance_hazard_names": ["wind"],
                                "row_provenance_topology_names": ["rahmen"],
                                "row_provenance_rows": [
                                    {
                                        "member_type": "beam",
                                        "hazard_type": "wind",
                                        "topology_type": "rahmen",
                                        "rule_family": "strength",
                                        "combination": "KDS_ULS_1",
                                        "component": "axial_force_kN",
                                        "clause": "KDS-AXIAL-001",
                                        "dcr": 0.422,
                                    }
                                ],
                                "review_geometry_snapshot": {
                                    "element_type": "BEAM",
                                    "family": "beam",
                                    "section_id": "11",
                                    "material_id": "1",
                                    "node_ids": ["2", "3"],
                                    "node_coordinates": [
                                        {"id": "2", "x": 1.0, "y": 0.0, "z": 0.0},
                                        {"id": "3", "x": 2.0, "y": 0.0, "z": 0.0},
                                    ],
                                },
                            },
                            {
                                "review_case_id": "C-EXACT-002",
                                "baseline_focus_member_id": "303",
                                "full_crosswalk_target_member_handle": "9002",
                                "full_crosswalk_target_section_id": "12",
                                "full_crosswalk_load_combination_names": ["KDS_ULS_2"],
                                "match_confidence": "manual_verified",
                                "source_member_type": "column",
                                "source_hazard_type": "seismic",
                                "source_topology_type": "frame",
                                "member_inventory_count": 1,
                                "member_inventory_member_type_names": ["column"],
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_rule_family_count": 1,
                                "row_provenance_hazard_count": 1,
                                "row_provenance_topology_count": 1,
                                "row_provenance_combination_names": ["KDS_ULS_2"],
                                "row_provenance_clause_names": ["KDS-MOMENT-Y-001"],
                                "row_provenance_component_names": ["bending_moment_y_kNm"],
                                "row_provenance_rule_family_names": ["strength"],
                                "row_provenance_hazard_names": ["seismic"],
                                "row_provenance_topology_names": ["frame"],
                                "row_provenance_rows": [
                                    {
                                        "member_type": "column",
                                        "hazard_type": "seismic",
                                        "topology_type": "frame",
                                        "rule_family": "strength",
                                        "combination": "KDS_ULS_2",
                                        "component": "bending_moment_y_kNm",
                                        "clause": "KDS-MOMENT-Y-001",
                                        "dcr": 0.611,
                                    }
                                ],
                                "review_geometry_snapshot": {
                                    "element_type": "COLUMN",
                                    "family": "column",
                                    "section_id": "12",
                                    "material_id": "2",
                                    "node_ids": ["3", "4"],
                                    "node_coordinates": [
                                        {"id": "3", "x": 2.0, "y": 0.0, "z": 0.0},
                                        {"id": "4", "x": 2.0, "y": 3.0, "z": 0.0},
                                    ],
                                },
                            },
                        ],
                    }
                }
            }
        },
    )

    summary = module.summarize_artifact(model_path)

    assert summary["exact_review_geometry_snapshot_count"] == 2
    assert summary["exact_review_geometry_snapshot_expected"] == 2
    assert summary["exact_review_geometry_snapshot_status"] == "PASS"
    assert summary["exact_review_geometry_section_parity_count"] == 2
    assert summary["exact_review_geometry_section_parity_expected"] == 2
    assert summary["exact_review_geometry_section_parity_status"] == "PASS"
    assert summary["exact_review_load_crosswalk_count"] == 2
    assert summary["exact_review_load_crosswalk_expected"] == 2
    assert summary["exact_review_load_crosswalk_status"] == "PASS"
    assert summary["exact_review_semantic_crosswalk_count"] == 2
    assert summary["exact_review_semantic_crosswalk_expected"] == 2
    assert summary["exact_review_semantic_crosswalk_status"] == "PASS"
    assert summary["full_member_crosswalk_count"] == 3
    assert summary["full_member_crosswalk_expected"] == 3
    assert summary["full_member_crosswalk_status"] == "PASS"
    assert summary["full_member_crosswalk_handle_kind"] == "aggregate_member_id"
    assert summary["full_section_crosswalk_count"] == 3
    assert summary["full_section_crosswalk_expected"] == 3
    assert summary["full_section_crosswalk_status"] == "PASS"
    assert summary["full_load_crosswalk_count"] == 2
    assert summary["full_load_crosswalk_expected"] == 2
    assert summary["full_load_crosswalk_status"] == "PASS"
    assert summary["exact_geometry_diff_count"] == 2
    assert summary["exact_geometry_diff_expected"] == 2
    assert summary["exact_geometry_diff_status"] == "PASS"
    assert summary["exact_geometry_diff_max_abs"] == 0.0
    assert "snapshots=2/2 PASS" in summary["summary_line"]
    assert "section_parity=2/2 PASS" in summary["summary_line"]
    assert "load_crosswalk=2/2 PASS" in summary["summary_line"]
    assert "semantic_crosswalk=2/2 PASS" in summary["summary_line"]
    assert "full_member_crosswalk=3/3 PASS" in summary["summary_line"]
    assert "full_section_crosswalk=3/3 PASS" in summary["summary_line"]
    assert "full_load_crosswalk=2/2 PASS" in summary["summary_line"]
    assert "geometry_diff=2/2 PASS max=0" in summary["summary_line"]


def test_validate_midas_kds_geometry_bridge_artifacts_reports_exact_section_parity_gap(tmp_path: Path) -> None:
    module = _load_module()
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    _write_json(
        model_path,
        {
            "model": {
                "elements": [
                    {"id": 202, "type": "BEAM", "family": "beam", "section_id": 99, "material_id": 1, "node_ids": [2, 3]},
                    {"id": 303, "type": "COLUMN", "family": "column", "section_id": 12, "material_id": 2, "node_ids": [3, 4]},
                ],
                "nodes": [
                    {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 2.0, "y": 0.0, "z": 0.0},
                    {"id": 4, "x": 2.0, "y": 3.0, "z": 0.0},
                ],
                "metadata": {
                    "kds_geometry_bridge": {
                        "provenance": "kds_codecheck_bridge_metadata",
                        "registry_source_label": "reviewer_verified_exact_registry",
                        "registry_contract_version": "0.2.0",
                        "summary": {
                            "review_id_count": 2,
                            "mapped_review_id_count": 2,
                            "exact_mapped_review_id_count": 2,
                            "heuristic_mapped_review_id_count": 0,
                            "review_row_count": 6,
                            "mapped_row_provenance_count": 6,
                            "exact_mapped_row_provenance_count": 6,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"external_registry_manual": 2},
                            "confidence_counts": {"manual_verified": 2},
                            "external_registry_row_count": 2,
                            "external_registry_usable_row_count": 2,
                            "external_registry_exact_row_count": 2,
                            "external_registry_heuristic_row_count": 0,
                            "external_registry_source_counts": {
                                "reviewer_verified_exact_registry": 2,
                            },
                        },
                        "bridge_rows": [
                            {
                                "review_case_id": "C-EXACT-001",
                                "baseline_focus_member_id": "202",
                                "match_confidence": "manual_verified",
                                "review_geometry_snapshot": {
                                    "element_type": "BEAM",
                                    "family": "beam",
                                    "section_id": "11",
                                    "material_id": "1",
                                    "node_ids": ["2", "3"],
                                    "node_coordinates": [
                                        {"id": "2", "x": 1.0, "y": 0.0, "z": 0.0},
                                        {"id": "3", "x": 2.0, "y": 0.0, "z": 0.0},
                                    ],
                                },
                            },
                            {
                                "review_case_id": "C-EXACT-002",
                                "baseline_focus_member_id": "303",
                                "match_confidence": "manual_verified",
                                "review_geometry_snapshot": {
                                    "element_type": "COLUMN",
                                    "family": "column",
                                    "section_id": "12",
                                    "material_id": "2",
                                    "node_ids": ["3", "4"],
                                    "node_coordinates": [
                                        {"id": "3", "x": 2.0, "y": 0.0, "z": 0.0},
                                        {"id": "4", "x": 2.0, "y": 3.0, "z": 0.0},
                                    ],
                                },
                            },
                        ],
                    }
                }
            }
        },
    )

    exit_code = module.main(["--path", str(model_path), "--out", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = module.summarize_artifact(model_path)

    assert exit_code == 0
    assert summary["exact_review_geometry_section_parity_count"] == 1
    assert summary["exact_review_geometry_section_parity_expected"] == 2
    assert summary["exact_review_geometry_section_parity_status"] == "CHECK"
    assert "section_parity=1/2 CHECK" in summary["summary_line"]
    assert report["checks"]["exact_section_parity_pass"] is False
    assert report["checks"]["exact_load_crosswalk_pass"] is True
    assert report["checks"]["exact_semantic_crosswalk_pass"] is True
    assert report["checks"]["full_member_crosswalk_pass"] is True
    assert report["checks"]["full_section_crosswalk_pass"] is False
    assert report["checks"]["full_load_crosswalk_pass"] is True
    assert report["checks"]["exact_geometry_diff_pass"] is False
    assert report["summary"]["exact_review_geometry_section_parity_count_total"] == 1
    assert report["summary"]["exact_review_geometry_section_parity_expected_total"] == 2
    assert report["summary"]["full_member_crosswalk_count_total"] == 2
    assert report["summary"]["full_member_crosswalk_expected_total"] == 2
    assert report["summary"]["full_section_crosswalk_count_total"] == 1
    assert report["summary"]["full_section_crosswalk_expected_total"] == 2
    assert report["summary"]["full_load_crosswalk_count_total"] == 0
    assert report["summary"]["full_load_crosswalk_expected_total"] == 0
    assert report["summary"]["exact_geometry_diff_count_total"] == 1
    assert report["summary"]["exact_geometry_diff_expected_total"] == 2
    assert "section_parity=1/2" in report["summary_line"]
    assert "full_member_crosswalk=2/2 PASS" in report["summary_line"]
    assert "full_section_crosswalk=1/2 CHECK" in report["summary_line"]
    assert "full_load_crosswalk=0/0 PASS" in report["summary_line"]
    assert "geometry_diff=1/2" in report["summary_line"]


def test_validate_midas_kds_geometry_bridge_artifacts_reports_load_crosswalk_gap(tmp_path: Path) -> None:
    module = _load_module()
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    _write_json(
        model_path,
        {
            "model": {
                "elements": [
                    {"id": 202, "type": "BEAM", "family": "beam", "section_id": 11, "material_id": 1, "node_ids": [2, 3]},
                ],
                "nodes": [
                    {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                    {"id": 3, "x": 2.0, "y": 0.0, "z": 0.0},
                ],
                "metadata": {
                    "kds_geometry_bridge": {
                        "provenance": "kds_codecheck_bridge_metadata",
                        "registry_source_label": "reviewer_verified_exact_registry",
                        "registry_contract_version": "0.2.0",
                        "summary": {
                            "review_id_count": 1,
                            "mapped_review_id_count": 1,
                            "exact_mapped_review_id_count": 1,
                            "heuristic_mapped_review_id_count": 0,
                            "review_row_count": 1,
                            "mapped_row_provenance_count": 1,
                            "exact_mapped_row_provenance_count": 1,
                            "heuristic_mapped_row_provenance_count": 0,
                            "strategy_counts": {"external_registry_manual": 1},
                            "confidence_counts": {"manual_verified": 1},
                            "external_registry_row_count": 1,
                            "external_registry_usable_row_count": 1,
                            "external_registry_exact_row_count": 1,
                            "external_registry_heuristic_row_count": 0,
                            "external_registry_source_counts": {
                                "reviewer_verified_exact_registry": 1,
                            },
                        },
                        "bridge_rows": [
                            {
                                "review_case_id": "C-EXACT-001",
                                "baseline_focus_member_id": "202",
                                "match_confidence": "manual_verified",
                                "source_member_type": "beam",
                                "source_hazard_type": "wind",
                                "source_topology_type": "rahmen",
                                "member_inventory_count": 1,
                                "member_inventory_member_type_names": ["beam"],
                                "row_provenance_row_count": 1,
                                "row_provenance_combination_count": 1,
                                "row_provenance_clause_count": 1,
                                "row_provenance_component_count": 1,
                                "row_provenance_rule_family_count": 1,
                                "row_provenance_hazard_count": 1,
                                "row_provenance_topology_count": 1,
                                "row_provenance_combination_names": ["KDS_ULS_BAD"],
                                "row_provenance_clause_names": ["KDS-AXIAL-001"],
                                "row_provenance_component_names": ["axial_force_kN"],
                                "row_provenance_rule_family_names": ["strength"],
                                "row_provenance_hazard_names": ["combined"],
                                "row_provenance_topology_names": ["rahmen"],
                                "row_provenance_rows": [
                                    {
                                        "member_type": "beam",
                                        "hazard_type": "wind",
                                        "topology_type": "rahmen",
                                        "rule_family": "strength",
                                        "combination": "KDS_ULS_1",
                                        "component": "axial_force_kN",
                                        "clause": "KDS-AXIAL-001",
                                        "dcr": 0.422,
                                    }
                                ],
                                "review_geometry_snapshot": {
                                    "element_type": "BEAM",
                                    "family": "beam",
                                    "section_id": "11",
                                    "material_id": "1",
                                    "node_ids": ["2", "3"],
                                    "node_coordinates": [
                                        {"id": "2", "x": 1.0, "y": 0.0, "z": 0.0},
                                        {"id": "3", "x": 2.0, "y": 0.0, "z": 0.0},
                                    ],
                                },
                            }
                        ],
                    }
                }
            }
        },
    )

    exit_code = module.main(["--path", str(model_path), "--out", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = module.summarize_artifact(model_path)

    assert exit_code == 0
    assert summary["exact_review_load_crosswalk_count"] == 0
    assert summary["exact_review_load_crosswalk_expected"] == 1
    assert summary["exact_review_load_crosswalk_status"] == "CHECK"
    assert summary["exact_review_semantic_crosswalk_count"] == 0
    assert summary["exact_review_semantic_crosswalk_expected"] == 1
    assert summary["exact_review_semantic_crosswalk_status"] == "CHECK"
    assert summary["full_member_crosswalk_count"] == 1
    assert summary["full_member_crosswalk_expected"] == 1
    assert summary["full_member_crosswalk_status"] == "PASS"
    assert summary["full_section_crosswalk_count"] == 1
    assert summary["full_section_crosswalk_expected"] == 1
    assert summary["full_section_crosswalk_status"] == "PASS"
    assert summary["full_load_crosswalk_count"] == 0
    assert summary["full_load_crosswalk_expected"] == 1
    assert summary["full_load_crosswalk_status"] == "CHECK"
    assert "load_crosswalk=0/1 CHECK" in summary["summary_line"]
    assert "semantic_crosswalk=0/1 CHECK" in summary["summary_line"]
    assert "full_member_crosswalk=1/1 PASS" in summary["summary_line"]
    assert "full_section_crosswalk=1/1 PASS" in summary["summary_line"]
    assert "full_load_crosswalk=0/1 CHECK" in summary["summary_line"]
    assert report["checks"]["exact_load_crosswalk_pass"] is False
    assert report["checks"]["exact_semantic_crosswalk_pass"] is False
    assert report["checks"]["full_member_crosswalk_pass"] is True
    assert report["checks"]["full_section_crosswalk_pass"] is True
    assert report["checks"]["full_load_crosswalk_pass"] is False
    assert report["summary"]["exact_review_load_crosswalk_count_total"] == 0
    assert report["summary"]["exact_review_load_crosswalk_expected_total"] == 1
    assert report["summary"]["exact_review_semantic_crosswalk_count_total"] == 0
    assert report["summary"]["exact_review_semantic_crosswalk_expected_total"] == 1
    assert report["summary"]["full_member_crosswalk_count_total"] == 1
    assert report["summary"]["full_member_crosswalk_expected_total"] == 1
    assert report["summary"]["full_section_crosswalk_count_total"] == 1
    assert report["summary"]["full_section_crosswalk_expected_total"] == 1
    assert report["summary"]["full_load_crosswalk_count_total"] == 0
    assert report["summary"]["full_load_crosswalk_expected_total"] == 1


def test_validate_midas_kds_geometry_bridge_artifacts_uses_registry_inventory_for_additive_closure(
    tmp_path: Path,
) -> None:
    module = _load_module()
    registry_path = tmp_path / "kds_geometry_bridge_registry.heuristic.json"
    _write_json(
        registry_path,
        {
            "source": "merged_registry",
            "summary": {
                "full_member_crosswalk_count": 4,
                "full_member_crosswalk_expected": 4,
                "full_member_crosswalk_status": "PASS",
                "full_member_crosswalk_handle_kind": "aggregate_member_id",
                "full_member_crosswalk_handles": ["7", "8", "9", "10"],
                "full_section_crosswalk_count": 3,
                "full_section_crosswalk_expected": 3,
                "full_section_crosswalk_status": "PASS",
                "full_section_crosswalk_ids": ["11", "22", "33"],
                "full_load_crosswalk_count": 0,
                "full_load_crosswalk_expected": 0,
                "full_load_crosswalk_status": "PASS",
                "full_load_crosswalk_names": [],
            },
        },
    )

    model_payload = {
        "model": {
            "elements": [
                {"id": 202, "type": "BEAM", "family": "beam", "section_id": 11, "material_id": 1, "node_ids": [1, 2]},
                {"id": 303, "type": "BEAM", "family": "beam", "section_id": 22, "material_id": 1, "node_ids": [2, 3]},
                {"id": 404, "type": "COLUMN", "family": "column", "section_id": 33, "material_id": 2, "node_ids": [3, 4]},
                {"id": 505, "type": "COLUMN", "family": "column", "section_id": 33, "material_id": 2, "node_ids": [4, 5]},
            ],
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 2.0, "y": 0.0, "z": 0.0},
                {"id": 4, "x": 2.0, "y": 3.0, "z": 0.0},
                {"id": 5, "x": 2.0, "y": 6.0, "z": 0.0},
            ],
            "metadata": {
                "members": [
                    {"id": 7, "element_seed": 202, "element_ids": [202]},
                    {"id": 8, "element_seed": 303, "element_ids": [303]},
                    {"id": 9, "element_seed": 404, "element_ids": [404]},
                    {"id": 10, "element_seed": 505, "element_ids": [505]},
                ],
            },
        }
    }

    artifact_a = tmp_path / "artifact_a.json"
    artifact_b = tmp_path / "artifact_b.json"
    for artifact_path, baseline_member_id, member_handle, section_id in (
        (artifact_a, "202", "7", "11"),
        (artifact_b, "303", "8", "22"),
    ):
        payload = json.loads(json.dumps(model_payload))
        payload["model"]["metadata"]["kds_geometry_bridge"] = {
            "provenance": "kds_codecheck_bridge_metadata",
            "registry_source_label": "merged_registry",
            "registry_contract_version": "0.4.0",
            "summary": {
                "review_id_count": 1,
                "mapped_review_id_count": 1,
                "exact_mapped_review_id_count": 1,
                "heuristic_mapped_review_id_count": 0,
                "review_row_count": 1,
                "mapped_row_provenance_count": 1,
                "exact_mapped_row_provenance_count": 1,
                "heuristic_mapped_row_provenance_count": 0,
                "strategy_counts": {"external_registry_manual": 1},
                "confidence_counts": {"manual_verified": 1},
                "external_registry_row_count": 4,
                "external_registry_usable_row_count": 4,
                "external_registry_exact_row_count": 4,
                "external_registry_heuristic_row_count": 0,
                "external_registry_source_counts": {"merged_registry": 4},
            },
            "bridge_rows": [
                {
                    "review_case_id": f"C-{member_handle}",
                    "baseline_focus_member_id": baseline_member_id,
                    "full_crosswalk_target_member_handle": member_handle,
                    "full_crosswalk_target_section_id": section_id,
                    "match_confidence": "manual_verified",
                    "review_geometry_snapshot": {
                        "element_type": "BEAM",
                        "family": "beam",
                        "section_id": section_id,
                        "material_id": "1",
                        "node_ids": ["1", "2"],
                        "node_coordinates": [
                            {"id": "1", "x": 0.0, "y": 0.0, "z": 0.0},
                            {"id": "2", "x": 1.0, "y": 0.0, "z": 0.0},
                        ],
                    },
                }
            ],
        }
        _write_json(artifact_path, payload)

    report_path = tmp_path / "report.json"
    exit_code = module.main(
        ["--path", str(artifact_a), "--path", str(artifact_b), "--out", str(report_path)]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["checks"]["full_member_crosswalk_pass"] is True
    assert report["checks"]["full_section_crosswalk_pass"] is True
    assert report["full_member_crosswalk_count_total"] == 4
    assert report["full_member_crosswalk_expected_total"] == 4
    assert report["full_member_crosswalk_status"] == "PASS"
    assert report["full_member_crosswalk_basis"] == "structured_inventory_union"
    assert report["full_member_crosswalk_handle_kind"] == "aggregate_member_id"
    assert report["full_section_crosswalk_count_total"] == 3
    assert report["full_section_crosswalk_expected_total"] == 3
    assert report["full_section_crosswalk_status"] == "PASS"
    assert report["full_section_crosswalk_basis"] == "structured_inventory_union"
    assert "full_member_crosswalk=4/4 PASS" in report["summary_line"]
    assert "full_section_crosswalk=3/3 PASS" in report["summary_line"]
    assert report["summary"]["artifact_rows"][0]["full_member_crosswalk_status"] == "CHECK"
    assert report["summary"]["artifact_rows"][1]["full_member_crosswalk_status"] == "CHECK"


def test_validate_midas_kds_geometry_bridge_artifacts_keeps_check_when_registry_inventory_is_incomplete(
    tmp_path: Path,
) -> None:
    module = _load_module()
    registry_path = tmp_path / "kds_geometry_bridge_registry.heuristic.json"
    _write_json(
        registry_path,
        {
            "source": "merged_registry",
            "summary": {
                "full_member_crosswalk_count": 2,
                "full_member_crosswalk_expected": 4,
                "full_member_crosswalk_status": "CHECK",
                "full_member_crosswalk_handle_kind": "aggregate_member_id",
                "full_member_crosswalk_handles": ["7", "8"],
                "full_section_crosswalk_count": 1,
                "full_section_crosswalk_expected": 3,
                "full_section_crosswalk_status": "CHECK",
                "full_section_crosswalk_ids": ["11"],
                "full_load_crosswalk_count": 0,
                "full_load_crosswalk_expected": 0,
                "full_load_crosswalk_status": "PASS",
                "full_load_crosswalk_names": [],
            },
        },
    )

    model_payload = {
        "model": {
            "elements": [
                {"id": 202, "type": "BEAM", "family": "beam", "section_id": 11, "material_id": 1, "node_ids": [1, 2]},
                {"id": 303, "type": "BEAM", "family": "beam", "section_id": 22, "material_id": 1, "node_ids": [2, 3]},
                {"id": 404, "type": "COLUMN", "family": "column", "section_id": 33, "material_id": 2, "node_ids": [3, 4]},
                {"id": 505, "type": "COLUMN", "family": "column", "section_id": 33, "material_id": 2, "node_ids": [4, 5]},
            ],
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 2.0, "y": 0.0, "z": 0.0},
                {"id": 4, "x": 2.0, "y": 3.0, "z": 0.0},
                {"id": 5, "x": 2.0, "y": 6.0, "z": 0.0},
            ],
            "metadata": {
                "members": [
                    {"id": 7, "element_seed": 202, "element_ids": [202]},
                    {"id": 8, "element_seed": 303, "element_ids": [303]},
                    {"id": 9, "element_seed": 404, "element_ids": [404]},
                    {"id": 10, "element_seed": 505, "element_ids": [505]},
                ],
            },
        }
    }

    artifact_a = tmp_path / "artifact_a.json"
    artifact_b = tmp_path / "artifact_b.json"
    for artifact_path, baseline_member_id, member_handle, section_id in (
        (artifact_a, "202", "7", "11"),
        (artifact_b, "303", "8", "22"),
    ):
        payload = json.loads(json.dumps(model_payload))
        payload["model"]["metadata"]["kds_geometry_bridge"] = {
            "provenance": "kds_codecheck_bridge_metadata",
            "registry_source_label": "merged_registry",
            "registry_contract_version": "0.4.0",
            "summary": {
                "review_id_count": 1,
                "mapped_review_id_count": 1,
                "exact_mapped_review_id_count": 1,
                "heuristic_mapped_review_id_count": 0,
                "review_row_count": 1,
                "mapped_row_provenance_count": 1,
                "exact_mapped_row_provenance_count": 1,
                "heuristic_mapped_row_provenance_count": 0,
                "strategy_counts": {"external_registry_manual": 1},
                "confidence_counts": {"manual_verified": 1},
                "external_registry_row_count": 2,
                "external_registry_usable_row_count": 2,
                "external_registry_exact_row_count": 2,
                "external_registry_heuristic_row_count": 0,
                "external_registry_source_counts": {"merged_registry": 2},
            },
            "bridge_rows": [
                {
                    "review_case_id": f"C-{member_handle}",
                    "baseline_focus_member_id": baseline_member_id,
                    "full_crosswalk_target_member_handle": member_handle,
                    "full_crosswalk_target_section_id": section_id,
                    "match_confidence": "manual_verified",
                    "review_geometry_snapshot": {
                        "element_type": "BEAM",
                        "family": "beam",
                        "section_id": section_id,
                        "material_id": "1",
                        "node_ids": ["1", "2"],
                        "node_coordinates": [
                            {"id": "1", "x": 0.0, "y": 0.0, "z": 0.0},
                            {"id": "2", "x": 1.0, "y": 0.0, "z": 0.0},
                        ],
                    },
                }
            ],
        }
        _write_json(artifact_path, payload)

    report_path = tmp_path / "report.json"
    exit_code = module.main(
        ["--path", str(artifact_a), "--path", str(artifact_b), "--out", str(report_path)]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["checks"]["full_member_crosswalk_pass"] is False
    assert report["checks"]["full_section_crosswalk_pass"] is False
    assert report["full_member_crosswalk_count_total"] == 2
    assert report["full_member_crosswalk_expected_total"] == 8
    assert report["full_member_crosswalk_status"] == "CHECK"
    assert report["full_member_crosswalk_basis"] == "artifact_sum"
    assert report["full_section_crosswalk_count_total"] == 2
    assert report["full_section_crosswalk_expected_total"] == 6
    assert report["full_section_crosswalk_status"] == "CHECK"
    assert report["full_section_crosswalk_basis"] == "artifact_sum"
    assert "full_member_crosswalk=2/8 CHECK" in report["summary_line"]
    assert "full_section_crosswalk=2/6 CHECK" in report["summary_line"]
