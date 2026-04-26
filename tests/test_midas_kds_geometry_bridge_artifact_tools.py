from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_backfill_midas_kds_geometry_bridge_metadata_writes_embedded_payload(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_kds_geometry_bridge_metadata.py",
        "backfill_midas_kds_geometry_bridge_metadata_test",
    )
    monkeypatch.setattr(module, "DEFAULT_HEURISTIC_REGISTRY", tmp_path / "missing_heuristic_registry.json")
    monkeypatch.setattr(module, "DEFAULT_EXACT_REGISTRY", tmp_path / "missing_exact_registry.json")
    artifact = tmp_path / "model.json"
    report = tmp_path / "code_check_report.json"
    _write_json(
        artifact,
        {
            "model": {
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 10, "node_ids": [1, 2]},
                    {"id": 202, "family": "column", "section_id": 11, "node_ids": [2, 3]},
                ],
                "metadata": {
                    "members": [
                        {"id": 7, "element_seed": 101, "element_ids": [101]},
                    ]
                },
            }
        },
    )
    _write_json(
        report,
        {
            "member_check_rows": [
                {
                    "combination": "KDS_ULS_2",
                    "member_id": "7",
                    "case_id": "7",
                    "member_type": "beam",
                    "component": "bending_moment_y_kNm",
                    "demand": 120.0,
                    "capacity": 100.0,
                    "dcr": 1.2,
                    "clause": "KDS-MOMENT-Y-001",
                },
                {
                    "combination": "KDS_ULS_2",
                    "member_id": "C-UNMAPPED-001",
                    "case_id": "C-UNMAPPED-001",
                    "member_type": "column",
                    "component": "axial_force_kN",
                    "demand": 80.0,
                    "capacity": 100.0,
                    "dcr": 0.8,
                    "clause": "KDS-AXIAL-001",
                },
            ]
        },
    )

    summary = module.backfill_artifact(artifact, report_path=report, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    metadata = ((updated.get("model") or {}).get("metadata") or {})
    bridge = metadata.get("kds_geometry_bridge") or {}
    bridge_rows = bridge.get("bridge_rows") or []

    assert summary["supported"] is True
    assert summary["written"] is True
    assert summary["review_ids"] == 2
    assert summary["mapped_review_ids"] == 1
    assert summary["exact_mapped_review_ids"] == 1
    assert summary["heuristic_mapped_review_ids"] == 0
    assert summary["unmapped_review_ids"] == 1
    assert bridge["summary"]["mapped_review_id_count"] == 1
    assert bridge["summary"]["exact_mapped_review_id_count"] == 1
    assert bridge["summary"]["heuristic_mapped_review_id_count"] == 0
    assert bridge["summary"]["unmapped_review_id_count"] == 1
    assert bridge_rows[0]["baseline_focus_member_id"] == "101"
    assert bridge_rows[0]["match_strategy"] == "member_aggregate_seed"
    assert bridge_rows[1]["baseline_focus_member_id"] == ""
    assert bridge_rows[1]["match_strategy"] == "unmapped"


def test_backfill_midas_kds_geometry_bridge_metadata_applies_external_registry(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_kds_geometry_bridge_metadata.py",
        "backfill_midas_kds_geometry_bridge_metadata_registry_test",
    )
    artifact = tmp_path / "model.json"
    report = tmp_path / "code_check_report.json"
    heuristic_registry = tmp_path / "kds_geometry_bridge_registry.heuristic.json"
    registry = tmp_path / "kds_geometry_bridge_registry.json"
    monkeypatch.setattr(module, "DEFAULT_HEURISTIC_REGISTRY", heuristic_registry)
    monkeypatch.setattr(module, "DEFAULT_EXACT_REGISTRY", tmp_path / "missing_exact_registry.json")
    _write_json(
        artifact,
        {
            "model": {
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 10, "node_ids": [1, 2]},
                    {"id": 202, "family": "column", "section_id": 11, "node_ids": [2, 3]},
                    {"id": 303, "family": "beam", "section_id": 12, "node_ids": [3, 4]},
                ],
                "metadata": {
                    "members": [
                        {"id": 7, "element_seed": 101, "element_ids": [101]},
                    ]
                },
            }
        },
    )
    _write_json(
        report,
        {
            "member_check_rows": [
                {"combination": "KDS_ULS_2", "member_id": "7", "case_id": "7"},
                {"combination": "KDS_ULS_2", "member_id": "C-UNMAPPED-001", "case_id": "C-UNMAPPED-001"},
                {"combination": "KDS_ULS_2", "member_id": "C-HEURISTIC-001", "case_id": "C-HEURISTIC-001"},
            ]
        },
    )
    _write_json(
        heuristic_registry,
        {
            "contract_version": "0.3.0",
            "source": "heuristic_semantic_case_profile_registry",
            "mappings": [
                {
                    "review_member_id": "C-HEURISTIC-001",
                    "review_case_id": "C-HEURISTIC-001",
                    "baseline_focus_member_id": "303",
                    "match_strategy": "heuristic_case_profile_x_beam_surrogate",
                    "match_confidence": "heuristic_case_profile",
                }
            ],
        },
    )
    _write_json(
        registry,
        {
            "contract_version": "0.2.0",
            "source": "reviewer_verified_registry",
            "mappings": [
                {
                    "review_member_id": "C-UNMAPPED-001",
                    "baseline_focus_member_id": "202",
                    "match_strategy": "external_registry_manual",
                    "match_confidence": "manual_verified",
                    "note": "verified by external reviewer registry",
                }
            ],
        },
    )

    summary = module.backfill_artifact(artifact, report_path=report, registry_path=registry, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    metadata = ((updated.get("model") or {}).get("metadata") or {})
    bridge = metadata.get("kds_geometry_bridge") or {}
    bridge_rows = bridge.get("bridge_rows") or []

    assert summary["supported"] is True
    assert summary["written"] is True
    assert summary["review_ids"] == 3
    assert summary["mapped_review_ids"] == 3
    assert summary["exact_mapped_review_ids"] == 2
    assert summary["heuristic_mapped_review_ids"] == 1
    assert summary["registry_source_label"] == "merged_registry"
    assert summary["registry_contract_version"] == "0.4.0"
    assert summary["external_registry_row_count"] == 2
    assert summary["external_registry_usable_row_count"] == 2
    assert summary["external_registry_exact_row_count"] == 1
    assert summary["external_registry_heuristic_row_count"] == 1
    assert summary["external_registry_source_counts"] == {
        "heuristic_semantic_case_profile_registry": 1,
        "reviewer_verified_registry": 1,
    }
    assert bridge["registry_source_label"] == "merged_registry"
    assert bridge["registry_contract_version"] == "0.4.0"
    assert bridge["summary"]["mapped_review_id_count"] == 3
    assert bridge["summary"]["exact_mapped_review_id_count"] == 2
    assert bridge["summary"]["heuristic_mapped_review_id_count"] == 1
    assert bridge["summary"]["external_registry_row_count"] == 2
    assert bridge["summary"]["external_registry_usable_row_count"] == 2
    assert bridge["summary"]["external_registry_exact_row_count"] == 1
    assert bridge["summary"]["external_registry_heuristic_row_count"] == 1
    assert bridge["summary"]["external_registry_source_counts"] == {
        "heuristic_semantic_case_profile_registry": 1,
        "reviewer_verified_registry": 1,
    }
    rows = {row["review_case_id"]: row for row in bridge_rows}
    assert rows["C-UNMAPPED-001"]["baseline_focus_member_id"] == "202"
    assert rows["C-UNMAPPED-001"]["match_strategy"] == "external_registry_manual"
    assert rows["C-UNMAPPED-001"]["registry_source_label"] == "reviewer_verified_registry"
    assert rows["C-HEURISTIC-001"]["baseline_focus_member_id"] == "303"
    assert rows["C-HEURISTIC-001"]["match_confidence"] == "heuristic_case_profile"
    assert rows["C-HEURISTIC-001"]["registry_source_label"] == "heuristic_semantic_case_profile_registry"


def test_backfill_midas_kds_geometry_bridge_metadata_merges_default_exact_registry_when_available(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_kds_geometry_bridge_metadata.py",
        "backfill_midas_kds_geometry_bridge_metadata_default_exact_registry_test",
    )
    artifact = tmp_path / "model.json"
    report = tmp_path / "code_check_report.json"
    heuristic_registry = tmp_path / "kds_geometry_bridge_registry.heuristic.json"
    exact_registry = tmp_path / "kds_geometry_bridge_registry.exact.json"
    monkeypatch.setattr(module, "DEFAULT_HEURISTIC_REGISTRY", heuristic_registry)
    monkeypatch.setattr(module, "DEFAULT_EXACT_REGISTRY", exact_registry)
    _write_json(
        artifact,
        {
            "model": {
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 10, "node_ids": [1, 2]},
                    {"id": 202, "family": "column", "section_id": 11, "node_ids": [2, 3]},
                    {"id": 303, "family": "beam", "section_id": 12, "node_ids": [3, 4]},
                ],
                "metadata": {
                    "members": [
                        {"id": 7, "element_seed": 101, "element_ids": [101]},
                    ]
                },
            }
        },
    )
    _write_json(
        report,
        {
            "member_check_rows": [
                {"combination": "KDS_ULS_2", "member_id": "7", "case_id": "7"},
                {"combination": "KDS_ULS_2", "member_id": "C-EXACT-001", "case_id": "C-EXACT-001"},
                {"combination": "KDS_ULS_2", "member_id": "C-HEURISTIC-001", "case_id": "C-HEURISTIC-001"},
            ]
        },
    )
    _write_json(
        heuristic_registry,
        {
            "contract_version": "0.3.0",
            "source": "heuristic_semantic_case_profile_registry",
            "mappings": [
                {
                    "review_member_id": "C-HEURISTIC-001",
                    "review_case_id": "C-HEURISTIC-001",
                    "baseline_focus_member_id": "303",
                    "match_strategy": "heuristic_case_profile_x_beam_surrogate",
                    "match_confidence": "heuristic_case_profile",
                }
            ],
        },
    )
    _write_json(
        exact_registry,
        {
            "contract_version": "0.2.0",
            "source": "reviewer_verified_exact_registry",
            "mappings": [
                {
                    "review_member_id": "C-EXACT-001",
                    "review_case_id": "C-EXACT-001",
                    "baseline_focus_member_id": "202",
                    "match_strategy": "external_registry_manual",
                    "match_confidence": "manual_verified",
                    "reviewer_verified": True,
                    "note": "verified reviewer mapping",
                    "review_geometry_snapshot": {
                        "section_id": "11",
                        "node_ids": ["2", "3"],
                    },
                }
            ],
        },
    )

    summary = module.backfill_artifact(artifact, report_path=report, write=False)

    bridge = module.derive_kds_geometry_bridge_for_model_payload(
        json.loads(artifact.read_text(encoding="utf-8")),
        code_check_report=json.loads(report.read_text(encoding="utf-8")),
        bridge_registry=module._effective_registry_payload(None),
    )
    rows = {row["review_case_id"]: row for row in (bridge.get("bridge_rows") or [])}

    assert summary["supported"] is True
    assert summary["written"] is False
    assert summary["review_ids"] == 3
    assert summary["mapped_review_ids"] == 3
    assert summary["exact_mapped_review_ids"] == 2
    assert summary["heuristic_mapped_review_ids"] == 1
    assert summary["registry_source_label"] == "merged_registry"
    assert summary["registry_contract_version"] == "0.4.0"
    assert summary["external_registry_row_count"] == 2
    assert summary["external_registry_usable_row_count"] == 2
    assert summary["external_registry_exact_row_count"] == 1
    assert summary["external_registry_heuristic_row_count"] == 1
    assert summary["external_registry_source_counts"] == {
        "heuristic_semantic_case_profile_registry": 1,
        "reviewer_verified_exact_registry": 1,
    }
    assert rows["C-EXACT-001"]["review_geometry_snapshot"]["section_id"] == "11"
    assert rows["C-EXACT-001"]["review_geometry_snapshot"]["node_ids"] == ["2", "3"]


def test_backfill_midas_kds_geometry_bridge_metadata_persists_exact_snapshot_on_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_kds_geometry_bridge_metadata.py",
        "backfill_midas_kds_geometry_bridge_metadata_snapshot_write_test",
    )
    artifact = tmp_path / "model.json"
    report = tmp_path / "code_check_report.json"
    heuristic_registry = tmp_path / "kds_geometry_bridge_registry.heuristic.json"
    exact_registry = tmp_path / "kds_geometry_bridge_registry.exact.json"
    monkeypatch.setattr(module, "DEFAULT_HEURISTIC_REGISTRY", heuristic_registry)
    monkeypatch.setattr(module, "DEFAULT_EXACT_REGISTRY", exact_registry)
    _write_json(
        artifact,
        {
            "model": {
                "elements": [
                    {"id": 101, "family": "beam", "section_id": 10, "node_ids": [1, 2]},
                    {"id": 202, "family": "column", "section_id": 11, "node_ids": [2, 3]},
                ],
                "metadata": {
                    "members": [
                        {"id": 7, "element_seed": 101, "element_ids": [101]},
                    ]
                },
            }
        },
    )
    _write_json(
        report,
        {
            "member_check_rows": [
                {"combination": "KDS_ULS_2", "member_id": "7", "case_id": "7"},
                {"combination": "KDS_ULS_2", "member_id": "C-EXACT-001", "case_id": "C-EXACT-001"},
            ]
        },
    )
    _write_json(
        heuristic_registry,
        {
            "contract_version": "0.3.0",
            "source": "heuristic_semantic_case_profile_registry",
            "mappings": [],
        },
    )
    _write_json(
        exact_registry,
        {
            "contract_version": "0.2.0",
            "source": "reviewer_verified_exact_registry",
            "mappings": [
                {
                    "review_member_id": "C-EXACT-001",
                    "review_case_id": "C-EXACT-001",
                    "baseline_focus_member_id": "202",
                    "match_strategy": "external_registry_manual",
                    "match_confidence": "manual_verified",
                    "reviewer_verified": True,
                    "review_geometry_snapshot": {
                        "element_type": "BEAM",
                        "family": "beam",
                        "section_id": "11",
                        "material_id": "1",
                        "node_ids": ["2", "3"],
                        "node_coordinates": [
                            {"id": "2", "x": 0.0, "y": 0.0, "z": 3.0},
                            {"id": "3", "x": 5.0, "y": 0.0, "z": 3.0},
                        ],
                    },
                }
            ],
        },
    )

    summary = module.backfill_artifact(artifact, report_path=report, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    bridge_rows = ((((updated.get("model") or {}).get("metadata") or {}).get("kds_geometry_bridge") or {}).get("bridge_rows") or [])
    rows = {row["review_case_id"]: row for row in bridge_rows}

    assert summary["supported"] is True
    assert summary["written"] is True
    assert summary["exact_mapped_review_ids"] == 2
    assert rows["C-EXACT-001"]["review_geometry_snapshot"] == {
        "element_type": "BEAM",
        "family": "beam",
        "section_id": "11",
        "material_id": "1",
        "node_ids": ["2", "3"],
        "node_coordinates": [
            {"id": "2", "x": 0.0, "y": 0.0, "z": 3.0},
            {"id": "3", "x": 5.0, "y": 0.0, "z": 3.0},
        ],
    }
