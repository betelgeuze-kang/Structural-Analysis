from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1 import run_korean_medium_large_ingest_pipeline as ingest
from implementation.phase1.open_data.korea import validate_operator_attachment_manifest


def test_ingest_pipeline_detects_manual_mgt_under_artifact_root(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "midas_generator_33.optimized.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")

    source_id = "lh_newtown_highrise_block_competition"
    artifact_dir = tmp_path / "collected" / "artifacts" / source_id
    artifact_dir.mkdir(parents=True)
    artifact_mgt = artifact_dir / f"{source_id}.mgt"
    artifact_mgt.write_bytes(benchmark.read_bytes())

    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": source_id,
                        "storey_band": "10_20",
                        "format": "mgt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", tmp_path / "collected" / "artifacts")
    monkeypatch.setattr(ingest, "CURATED_ROOT", tmp_path / "curated")
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {"records": [{"source_id": source_id, "status": "", "local_path": ""}]},
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
    )

    assert receipt["summary"]["attached_count"] == 1
    assert receipt["summary"]["metadata_only_count"] == 0
    assert receipt["summary"]["mgt_header_ok_count"] == 1
    assert receipt["summary"]["repo_benchmark_bridge_source_ids"] == [source_id]
    assert receipt["summary"]["operator_attach_required_source_ids"] == []
    assert receipt["summary"]["operator_action_queue_source_ids"] == [source_id]
    assert receipt["summary"]["operator_action_type_counts"] == {
        "replace_repo_benchmark_bridge_mgt_with_operator_real_mgt": 1
    }
    assert receipt["operator_action_queue"][0]["target_directory"] == str(artifact_dir)
    action_packet = receipt["operator_action_packet"]
    assert action_packet["schema_version"] == "korean-medium-large-operator-action-packet.v1"
    assert action_packet["status"] == "pending"
    assert action_packet["action_count"] == 1
    assert action_packet["source_ids_by_action_type"] == {
        "replace_repo_benchmark_bridge_mgt_with_operator_real_mgt": [source_id]
    }
    assert (
        "sha256_differs_from_repo_benchmark_bridge"
        in action_packet["acceptance_check_inventory"]
    )
    bridge_matrix = action_packet["candidate_blocker_matrix"][0]
    assert bridge_matrix["source_id"] == source_id
    assert bridge_matrix["repo_candidate_match_count"] == 1
    assert bridge_matrix["candidate_promotion_blocker_counts"] == {
        "repo_benchmark_bridge_mgt": 1
    }
    assert (
        bridge_matrix["next_resolvable_step"]
        == "replace_repo_benchmark_bridge_with_source_native_mgt"
    )
    row = receipt["per_source"][0]
    assert row["mgt_path"] == str(artifact_mgt)
    assert row["attach_provenance"] == "repo_benchmark_bridge"
    assert row["attachment_detection"] == "artifact_root"
    assert row["blockers"] == []


def test_ingest_pipeline_routes_placeholder_mgt_to_source_native_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark = tmp_path / "midas_generator_33.optimized.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")

    source_id = "placeholder_mgt"
    artifact_dir = tmp_path / "collected" / "artifacts" / source_id
    artifact_dir.mkdir(parents=True)
    artifact_mgt = artifact_dir / f"{source_id}.mgt"
    artifact_mgt.write_text("*VERSION\n9.5\n", encoding="utf-8")

    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": source_id,
                        "storey_band": "10_20",
                        "format": "mgt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", tmp_path / "collected" / "artifacts")
    monkeypatch.setattr(ingest, "CURATED_ROOT", tmp_path / "curated")
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {
            "records": [{"source_id": source_id, "status": "", "local_path": ""}]
        },
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
    )

    assert receipt["summary"]["attached_count"] == 1
    assert receipt["summary"]["mgt_header_ok_count"] == 0
    assert receipt["summary"]["placeholder_mgt_count"] == 1
    assert receipt["summary"]["operator_action_type_counts"] == {
        "replace_placeholder_mgt_with_operator_real_mgt": 1
    }
    matrix = receipt["operator_action_packet"]["candidate_blocker_matrix"][0]
    assert matrix["source_id"] == source_id
    assert matrix["next_resolvable_step"] == "replace_placeholder_with_source_native_mgt"
    row = receipt["per_source"][0]
    assert row["mgt_path"] == str(artifact_mgt)
    assert any(str(blocker).startswith("mgt_file_too_small:") for blocker in row["blockers"])


def test_ingest_pipeline_splits_mgt_provenance_and_curated_ifc(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "midas_generator_33.optimized.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")
    operator_mgt = tmp_path / "operator_real.mgt"
    operator_mgt.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "1" * 800, encoding="utf-8")
    curated_ifc = tmp_path / "curated" / "award.ifc"
    curated_ifc.parent.mkdir(parents=True)
    curated_ifc.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": "bridge_mgt",
                        "storey_band": "20_30",
                        "format": "mgt",
                    },
                    {
                        "source_id": "operator_mgt",
                        "storey_band": "20_30",
                        "format": "mgt",
                    },
                    {
                        "source_id": "curated_ifc",
                        "storey_band": "high_rise",
                        "format": "ifc",
                        "curated_local_ifc_required": True,
                        "curated_local_ifc_status": "attached",
                        "curated_local_ifc_reference": str(curated_ifc),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "collected" / "artifacts"
    bridge_dir = artifact_root / "bridge_mgt"
    bridge_dir.mkdir(parents=True)
    (bridge_dir / "bridge_mgt.mgt").write_bytes(benchmark.read_bytes())

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {
            "records": [
                {"source_id": "bridge_mgt", "status": "", "local_path": ""},
                {"source_id": "operator_mgt", "status": "collected", "local_path": str(operator_mgt)},
                {"source_id": "curated_ifc", "status": "", "local_path": ""},
            ]
        },
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
    )

    summary = receipt["summary"]
    assert summary["attached_count"] == 3
    assert summary["mgt_attached_count"] == 2
    assert summary["mgt_header_ok_count"] == 2
    assert summary["repo_benchmark_bridge_mgt_header_ok_count"] == 1
    assert summary["operator_attached_mgt_header_ok_count"] == 1
    assert summary["operator_attached_real_mgt_header_ok_count"] == 1
    assert summary["ifc_attached_count"] == 1
    assert summary["operator_attached_ifc_count"] == 1
    assert summary["curated_local_ifc_attached_count"] == 1
    assert summary["curated_local_ifc_missing_count"] == 0
    assert summary["operator_attached_real_artifact_count"] == 2
    assert summary["metadata_only_source_ids"] == []
    assert summary["repo_benchmark_bridge_source_ids"] == ["bridge_mgt"]
    assert summary["operator_attach_required_source_ids"] == []
    assert summary["operator_action_queue_source_ids"] == ["bridge_mgt"]
    assert summary["operator_action_queue_count"] == 1
    assert summary["operator_attached_real_mgt_header_ok_target"] == 4
    assert summary["operator_attached_real_mgt_header_ok_remaining"] == 3
    assert summary["operator_action_type_counts"] == {
        "replace_repo_benchmark_bridge_mgt_with_operator_real_mgt": 1
    }
    assert receipt["operator_action_packet"]["action_count"] == 1
    assert (
        receipt["operator_action_packet"][
            "operator_attached_real_mgt_header_ok_remaining"
        ]
        == 3
    )

    rows = {row["source_id"]: row for row in receipt["per_source"]}
    assert rows["bridge_mgt"]["attach_provenance"] == "repo_benchmark_bridge"
    assert rows["operator_mgt"]["attach_provenance"] == "operator_attached"
    assert rows["curated_ifc"]["curated_local_ifc_exists"] is True
    assert rows["curated_ifc"]["attachment_detection"] == "curated_local_ifc_reference"
    assert rows["curated_ifc"]["attach_provenance"] == "operator_attached"


def test_ingest_pipeline_counts_confirmed_operator_attachment_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark = tmp_path / "benchmark.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")
    operator_mgt = tmp_path / "native_source.mgt"
    operator_mgt.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "1" * 800, encoding="utf-8")
    manifest = tmp_path / "operator_attachment_manifest.json"
    source_id = "operator_manifest_mgt"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "korean-medium-large-operator-attachment-manifest.v1",
                "attachments": [
                    {
                        "source_id": source_id,
                        "local_path": str(operator_mgt),
                        "file_type": ".mgt",
                        "rights_confirmed": True,
                        "source_native_artifact": True,
                        "provenance_url": "https://example.test/source",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": source_id,
                        "storey_band": "20_30",
                        "format": "mgt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", tmp_path / "collected" / "artifacts")
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {
            "records": [{"source_id": source_id, "status": "", "local_path": ""}]
        },
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
        operator_attachment_manifest_path=manifest,
    )

    summary = receipt["summary"]
    assert summary["attached_count"] == 1
    assert summary["metadata_only_count"] == 0
    assert summary["mgt_header_ok_count"] == 1
    assert summary["operator_attached_real_mgt_header_ok_count"] == 1
    assert summary["operator_attachment_manifest_present"] is True
    assert summary["operator_attachment_manifest_accepted_count"] == 1
    assert summary["operator_attachment_manifest_rejected_count"] == 0
    assert summary["operator_action_queue_count"] == 0
    row = receipt["per_source"][0]
    assert row["operator_attachment_manifest_overlay"] is True
    assert row["mgt_path"] == str(operator_mgt)
    assert row["attach_provenance"] == "operator_attached"


def test_ingest_pipeline_rejects_unconfirmed_operator_attachment_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark = tmp_path / "benchmark.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")
    operator_mgt = tmp_path / "native_source.mgt"
    operator_mgt.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "1" * 800, encoding="utf-8")
    manifest = tmp_path / "operator_attachment_manifest.json"
    source_id = "unconfirmed_manifest_mgt"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "korean-medium-large-operator-attachment-manifest.v1",
                "attachments": [
                    {
                        "source_id": source_id,
                        "local_path": str(operator_mgt),
                        "file_type": ".mgt",
                        "rights_confirmed": False,
                        "source_native_artifact": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": source_id,
                        "storey_band": "20_30",
                        "format": "mgt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", tmp_path / "collected" / "artifacts")
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {
            "records": [{"source_id": source_id, "status": "", "local_path": ""}]
        },
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
        operator_attachment_manifest_path=manifest,
    )

    summary = receipt["summary"]
    assert summary["attached_count"] == 0
    assert summary["metadata_only_count"] == 1
    assert summary["operator_attachment_manifest_accepted_count"] == 0
    assert summary["operator_attachment_manifest_rejected_count"] == 1
    assert summary["operator_attachment_manifest_rejection_counts"] == {
        "rights_not_confirmed": 1
    }
    assert receipt["operator_attachment_manifest_candidates"][0][
        "accepted_for_collection_overlay"
    ] is False
    assert receipt["operator_action_queue"][0]["action_type"] == "attach_operator_real_mgt"


def test_operator_attachment_manifest_validator_reports_overlay_readiness(
    tmp_path: Path,
) -> None:
    operator_mgt = tmp_path / "native_source.mgt"
    operator_mgt.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "1" * 800, encoding="utf-8")
    manifest = tmp_path / "operator_attachment_manifest.json"
    catalog = tmp_path / "korean_source_catalog.json"
    source_id = "validated_manifest_mgt"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": source_id,
                        "storey_band": "20_30",
                        "format": "mgt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "korean-medium-large-operator-attachment-manifest.v1",
                "attachments": [
                    {
                        "source_id": source_id,
                        "local_path": str(operator_mgt),
                        "file_type": ".mgt",
                        "rights_confirmed": True,
                        "source_native_artifact": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_operator_attachment_manifest.validate_operator_attachment_manifest(
        manifest_path=manifest,
        catalog_path=catalog,
    )

    assert report["ready_for_collection_overlay"] is True
    assert report["accepted_source_count"] == 1
    assert report["rejected_source_count"] == 0
    assert report["rows"][0]["accepted_for_collection_overlay"] is True


def test_ingest_pipeline_reports_local_private_candidates_without_counting_them(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark = tmp_path / "benchmark.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")
    private_mgt = tmp_path / "private_real.mgt"
    private_mgt.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "1" * 800, encoding="utf-8")
    private_pdf = tmp_path / "private_real.pdf"
    private_pdf.write_bytes(b"%PDF-1.6\n" + b"0" * 1200)
    private_manifest = tmp_path / "private_manifest.json"
    private_manifest.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": "kr_private_seed",
                        "jurisdiction": "KR",
                        "source_family": "public_institution_bid_drawing_docs",
                        "files": [
                            {
                                "file_name": private_pdf.name,
                                "file_type": ".pdf",
                                "bytes": private_pdf.stat().st_size,
                                "role": "architectural_drawing_pdf",
                                "private_path": str(private_pdf),
                                "raw_redistribution_allowed": False,
                                "drawing_review_candidate": True,
                            }
                        ],
                    },
                    {
                        "project_id": "global_mgt_seed",
                        "jurisdiction": "GLOBAL",
                        "source_family": "public_midas_mgt_model",
                        "files": [
                            {
                                "file_name": private_mgt.name,
                                "file_type": ".mgt",
                                "bytes": private_mgt.stat().st_size,
                                "role": "midas_mgt_model",
                                "private_path": str(private_mgt),
                                "raw_redistribution_allowed": False,
                                "model_optimization_candidate": True,
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": "awaiting_real_mgt",
                        "storey_band": "20_30",
                        "format": "mgt",
                    },
                    {
                        "source_id": "awaiting_real_pdf",
                        "storey_band": "20_30",
                        "format": "pdf",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", tmp_path / "collected" / "artifacts")
    monkeypatch.setattr(ingest, "CURATED_ROOT", tmp_path / "curated")
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "PRIVATE_REAL_DRAWING_MANIFEST", private_manifest)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {
            "records": [
                {"source_id": "awaiting_real_mgt", "status": "", "local_path": ""},
                {"source_id": "awaiting_real_pdf", "status": "", "local_path": ""},
            ]
        },
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
    )

    summary = receipt["summary"]
    assert summary["attached_count"] == 0
    assert summary["local_private_candidate_count"] == 2
    assert summary["existing_local_private_candidate_count"] == 2
    assert summary["kr_local_private_candidate_count"] == 1
    assert summary["mgt_local_private_candidate_count"] == 1
    assert summary["mgt_header_ok_local_private_candidate_count"] == 1
    assert summary["g7_counted_local_private_candidate_count"] == 0
    assert summary["catalog_source_unmatched_candidate_count"] == 2
    assert summary["operator_action_private_candidate_match_count"] == 1
    assert summary["operator_action_private_candidate_source_count"] == 1
    assert summary["operator_action_private_candidate_file_count"] == 1
    candidates = receipt["local_private_candidate_artifacts"]
    assert all(row["counted_in_g7"] is False for row in candidates)
    assert "not_catalog_source_matched" in candidates[0]["promotion_blockers"]
    assert "raw_redistribution_not_allowed" in candidates[0]["promotion_blockers"]
    candidate_matches = receipt["operator_action_private_candidate_matches"]
    assert candidate_matches[0]["source_id"] == "awaiting_real_pdf"
    assert candidate_matches[0]["candidate_file_name"] == private_pdf.name
    assert candidate_matches[0]["requires_rights_confirmation"] is True
    assert candidate_matches[0]["counted_in_g7"] is False
    candidate_matrix = {
        row["source_id"]: row
        for row in receipt["operator_action_packet"]["candidate_blocker_matrix"]
    }
    assert receipt["operator_action_packet"]["candidate_matrix_summary"] == {
        "candidate_action_count": 2,
        "candidate_match_count": 1,
        "exact_clean_repo_candidate_count": 0,
        "actions_with_candidate_blockers_count": 1,
    }
    pdf_matrix = candidate_matrix["awaiting_real_pdf"]
    assert pdf_matrix["private_candidate_match_count"] == 1
    assert pdf_matrix["candidate_promotion_blocker_counts"] == {
        "not_catalog_source_matched": 1,
        "raw_redistribution_not_allowed": 1,
    }
    assert (
        pdf_matrix["next_resolvable_step"]
        == "confirm_rights_and_map_private_candidate_to_catalog_source"
    )
    assert candidate_matrix["awaiting_real_mgt"]["candidate_match_count"] == 0


def test_ingest_pipeline_reports_repo_public_candidates_without_counting_them(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark = tmp_path / "benchmark.mgt"
    benchmark.write_text("*VERSION\n9.5\n*UNIT\nKN, M\n" + "0" * 800, encoding="utf-8")
    artifact_root = tmp_path / "collected" / "artifacts"
    bridge_dir = artifact_root / "bridge_mgt"
    bridge_dir.mkdir(parents=True)
    bridge_mgt = bridge_dir / "bridge_mgt.mgt"
    bridge_mgt.write_bytes(benchmark.read_bytes())
    curated_root = tmp_path / "curated"
    curated_root.mkdir()
    curated_ifc = curated_root / "award_reference.ifc"
    curated_ifc.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    private_manifest = tmp_path / "missing_private_manifest.json"

    catalog = tmp_path / "korean_source_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                    {
                        "source_id": "bridge_mgt",
                        "storey_band": "20_30",
                        "format": "mgt",
                    },
                    {
                        "source_id": "missing_ifc",
                        "storey_band": "high_rise",
                        "format": "ifc",
                        "curated_local_ifc_required": True,
                        "curated_local_ifc_status": "required_missing",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(ingest, "CURATED_ROOT", curated_root)
    monkeypatch.setattr(ingest, "BENCHMARK_MGT", benchmark)
    monkeypatch.setattr(ingest, "PRIVATE_REAL_DRAWING_MANIFEST", private_manifest)
    monkeypatch.setattr(ingest, "_regenerate_catalog", lambda *, skip_regenerate: None)
    monkeypatch.setattr(
        ingest,
        "_run_collector",
        lambda *, catalog_path, skip_collect: {
            "records": [
                {"source_id": "bridge_mgt", "status": "", "local_path": ""},
                {"source_id": "missing_ifc", "status": "", "local_path": ""},
            ]
        },
    )

    receipt = ingest.run_korean_medium_large_ingest_pipeline(
        catalog_path=catalog,
        collection_report_path=tmp_path / "collection.json",
        receipt_path=tmp_path / "receipt.json",
    )

    summary = receipt["summary"]
    assert summary["repo_public_candidate_count"] == 2
    assert summary["repo_public_candidate_mgt_count"] == 1
    assert summary["repo_public_candidate_ifc_count"] == 1
    assert summary["repo_public_candidate_benchmark_bridge_count"] == 1
    assert summary["g7_counted_repo_public_candidate_count"] == 0
    assert summary["operator_action_repo_candidate_match_count"] == 2
    assert summary["operator_action_repo_candidate_source_count"] == 2
    assert summary["operator_action_repo_candidate_file_count"] == 2
    assert summary["operator_action_repo_candidate_exact_source_match_count"] == 1
    assert summary["operator_action_repo_candidate_exact_clean_count"] == 0
    assert summary["operator_action_repo_candidate_exact_blocker_counts"] == {
        "repo_benchmark_bridge_mgt": 1
    }
    assert summary["operator_action_repo_candidate_requires_source_mapping_count"] == 1
    assert summary["operator_action_repo_candidate_ifc_source_mapping_candidate_count"] == 1
    assert (
        summary[
            "operator_action_repo_candidate_ifc_source_mapping_candidate_source_count"
        ]
        == 1
    )
    assert (
        summary[
            "operator_action_repo_candidate_ifc_source_mapping_candidate_file_count"
        ]
        == 1
    )
    assert summary["operator_action_repo_candidate_benchmark_bridge_count"] == 1

    repo_matches = receipt["operator_action_repo_candidate_matches"]
    assert all(row["counted_in_g7"] is False for row in repo_matches)
    bridge_match = next(row for row in repo_matches if row["source_id"] == "bridge_mgt")
    assert bridge_match["candidate_mgt_provenance"] == "repo_benchmark_bridge"
    assert "repo_benchmark_bridge_mgt" in bridge_match["promotion_blockers"]
    ifc_match = next(row for row in repo_matches if row["source_id"] == "missing_ifc")
    assert ifc_match["candidate_file_name"] == curated_ifc.name
    assert ifc_match["requires_operator_source_mapping"] is True
    assert "catalog_source_unmatched_candidate" in ifc_match["promotion_blockers"]
    candidate_matrix = {
        row["source_id"]: row
        for row in receipt["operator_action_packet"]["candidate_blocker_matrix"]
    }
    assert receipt["operator_action_packet"]["candidate_matrix_summary"] == {
        "candidate_action_count": 2,
        "candidate_match_count": 2,
        "exact_clean_repo_candidate_count": 0,
        "actions_with_candidate_blockers_count": 2,
    }
    resolution_plan = receipt["operator_action_packet"]["operator_resolution_plan"]
    assert (
        resolution_plan["schema_version"]
        == "korean-medium-large-operator-resolution-plan.v1"
    )
    assert resolution_plan["auto_promotable_repo_candidate_count"] == 0
    assert resolution_plan["source_mapping_blocked_action_count"] == 1
    assert resolution_plan["priority_batches"][0]["batch_id"] == (
        "replace_benchmark_bridge_mgt"
    )
    assert resolution_plan["priority_batches"][0]["source_ids"] == ["bridge_mgt"]
    assert candidate_matrix["bridge_mgt"]["candidate_promotion_blocker_counts"] == {
        "repo_benchmark_bridge_mgt": 1
    }
    assert candidate_matrix["bridge_mgt"]["exact_clean_repo_candidate_count"] == 0
    assert candidate_matrix["missing_ifc"]["candidate_promotion_blocker_counts"] == {
        "catalog_source_unmatched_candidate": 1
    }
    assert (
        candidate_matrix["missing_ifc"]["next_resolvable_step"]
        == "map_repo_candidate_to_catalog_source_or_attach_native_artifact"
    )
    assert receipt["operator_action_repo_candidate_ifc_source_mapping_candidates"] == [
        ifc_match
    ]
