from __future__ import annotations

import json

from implementation.phase1.generate_irregular_benchmark_execution_manifest import (
    attach_irregular_benchmark_receipts,
    build_irregular_benchmark_execution_manifest,
)


def test_build_irregular_benchmark_execution_manifest_promotes_single_local_ready_case() -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "torsion_local",
                    "family_id": "torsionally_eccentric_core_tower",
                    "source_urls": ["https://example.com/local-proxy"],
                },
                {
                    "source_id": "remote_peer",
                    "family_id": "transfer_podium_tower",
                    "source_urls": ["https://peer.berkeley.edu/example"],
                },
            ]
        },
        collection_report={"summary": {"collected_count": 7, "metadata_only_remote_candidate_count": 15}},
        top5_manifest={
            "top5_families": [
                {
                    "family_id": "torsionally_eccentric_core_tower",
                    "execution_mode": "ready_local_now",
                    "source_ids": ["torsion_local"],
                    "local_paths": ["implementation/phase1/open_data/wind/tpu/case.csv"],
                    "irregularity_tags": ["torsion", "core_offset"],
                    "recommended_kpi_or_validation_angle": "torsional irregularity index",
                    "why_it_matters": "offset core",
                },
                {
                    "family_id": "transfer_podium_tower",
                    "execution_mode": "remote_source_hunt_needed",
                    "source_ids": ["remote_peer"],
                    "local_paths": [],
                    "irregularity_tags": ["transfer_story"],
                    "recommended_kpi_or_validation_angle": "transfer demand jump",
                    "why_it_matters": "transfer podium",
                },
            ]
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_EXECUTION_MANIFEST_READY"
    assert payload["summary"]["ready_task_count"] == 1
    assert payload["summary"]["blocked_task_count"] == 1
    assert payload["summary"]["execution_mode"] == "limited"
    assert payload["summary"]["ready_canonical_task_count"] == 0
    assert payload["summary"]["ready_bridged_task_count"] == 0
    assert payload["summary"]["ready_proxy_task_count"] == 1
    ready_task = payload["ready_tasks"][0]
    blocked_task = payload["blocked_tasks"][0]
    assert ready_task["task_id"] == "irregular::torsionally_eccentric_core_tower"
    assert ready_task["execution_status"] == "ready"
    assert ready_task["benchmark_readiness_tier"] == "proxy"
    assert ready_task["input_path"].endswith("case.csv")
    assert blocked_task["task_id"] == "irregular::transfer_podium_tower"
    assert blocked_task["blocker_reason"] == "collect_remote_source"
    assert blocked_task["required_action"] == "collect_remote_source"


def test_build_irregular_benchmark_execution_manifest_accepts_proxy_ready_modes() -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "proxy_local",
                    "family_id": "transfer_podium_tower",
                    "source_urls": ["https://example.com/proxy.json"],
                }
            ]
        },
        collection_report={"summary": {"collected_count": 1, "metadata_only_remote_candidate_count": 0}},
        top5_manifest={
            "summary": {"top5_local_ready_count": 1, "top5_proxy_ready_count": 1},
            "top5_families": [
                {
                    "family_id": "transfer_podium_tower",
                    "execution_mode": "ready_local_proxy_now",
                    "recommended_source_kind": "repo_local_proxy",
                    "recommended_source_format": "json_graph",
                    "source_ids": ["proxy_local"],
                    "local_paths": ["implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/model.json"],
                    "irregularity_tags": ["load_transfer", "transfer_story"],
                    "recommended_kpi_or_validation_angle": "transfer-story demand ratio",
                    "why_it_matters": "transfer podium",
                }
            ],
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )

    assert payload["summary"]["ready_task_count"] == 1
    assert payload["summary"]["top5_proxy_ready_count"] == 1
    assert payload["ready_tasks"][0]["benchmark_readiness_tier"] == "proxy"
    assert payload["ready_tasks"][0]["source_origin_class"] == "repo_local_proxy_irregular"
    assert payload["summary"]["ready_canonical_task_count"] == 0
    assert payload["summary"]["ready_bridged_task_count"] == 0
    assert payload["summary"]["ready_proxy_task_count"] == 1
    assert payload["task_count"] == 1
    assert len(payload["tasks"]) == 1


def test_build_irregular_benchmark_execution_manifest_tracks_bridged_and_canonical_tiers() -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "bridged_local",
                    "family_id": "setback_tower",
                    "source_urls": ["https://example.com/bridged.ifc"],
                },
                {
                    "source_id": "canonical_local",
                    "family_id": "bridge_section_frame",
                    "source_urls": ["https://example.com/frame.mgt"],
                },
            ]
        },
        collection_report={"summary": {"collected_count": 2, "metadata_only_remote_candidate_count": 0}},
        top5_manifest={
            "summary": {
                "top5_local_ready_count": 2,
                "top5_proxy_ready_count": 0,
                "top5_bridged_ready_count": 1,
                "top5_canonical_ready_count": 1,
            },
            "top5_families": [
                {
                    "family_id": "setback_tower",
                    "execution_mode": "ready_local_bridged_now",
                    "recommended_source_kind": "repo_local_bridged",
                    "recommended_source_format": "ifc",
                    "source_ids": ["bridged_local"],
                    "local_paths": ["implementation/phase1/open_data/irregular/collected/artifacts/tower.ifc"],
                    "irregularity_tags": ["setback"],
                    "recommended_kpi_or_validation_angle": "setback demand jump",
                    "why_it_matters": "setback tower",
                },
                {
                    "family_id": "bridge_section_frame",
                    "execution_mode": "ready_local_canonical_now",
                    "recommended_source_kind": "public_native_source",
                    "recommended_source_format": "mgt",
                    "source_ids": ["canonical_local"],
                    "local_paths": ["implementation/phase1/open_data/midas/public/frame.mgt"],
                    "irregularity_tags": ["bridge_section"],
                    "recommended_kpi_or_validation_angle": "native roundtrip",
                    "why_it_matters": "native frame",
                },
            ],
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )

    tiers = {row["case_id"]: row["benchmark_readiness_tier"] for row in payload["ready_tasks"]}
    assert tiers["setback_tower"] == "bridged"
    assert tiers["bridge_section_frame"] == "canonical"
    assert payload["summary"]["top5_bridged_ready_count"] == 1
    assert payload["summary"]["top5_canonical_ready_count"] == 1
    assert payload["summary"]["task_count"] == 2
    assert len(payload["tasks"]) == 2


def test_build_irregular_benchmark_execution_manifest_promotes_bridge_report_backed_proxy_rows() -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "bridged_local",
                    "family_id": "transfer_podium_tower",
                    "source_urls": ["https://example.com/bridged.json"],
                    "companion_paths": [
                        "implementation/phase1/open_data/midas/quality_corpus/bridged/example_case/bridge_report.json"
                    ],
                }
            ]
        },
        collection_report={"summary": {"collected_count": 1, "metadata_only_remote_candidate_count": 0}},
        top5_manifest={
            "summary": {
                "top5_local_ready_count": 1,
                "top5_proxy_ready_count": 0,
                "top5_bridged_ready_count": 1,
                "top5_canonical_ready_count": 0,
            },
            "top5_families": [
                {
                    "family_id": "transfer_podium_tower",
                    "execution_mode": "ready_local_now",
                    "recommended_source_kind": "repo_local_proxy",
                    "recommended_evidence_class": "repo_local_proxy",
                    "recommended_source_format": "json_graph",
                    "source_ids": ["bridged_local"],
                    "local_paths": [
                        "implementation/phase1/open_data/midas/quality_corpus/bridged/example_case/model.json"
                    ],
                    "irregularity_tags": ["load_transfer"],
                    "recommended_kpi_or_validation_angle": "transfer demand",
                    "why_it_matters": "bridged transfer podium",
                }
            ],
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )

    ready_task = payload["ready_tasks"][0]
    assert ready_task["benchmark_readiness_tier"] == "bridged"
    assert ready_task["source_origin_class"] == "repo_local_bridged_irregular"
    assert payload["summary"]["ready_bridged_task_count"] == 1
    assert payload["summary"]["ready_proxy_task_count"] == 0


def test_build_irregular_benchmark_execution_manifest_marks_reference_only_assets_as_materialize_needed() -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "soft_story_reference",
                    "family_id": "soft_story_podium_tower",
                    "source_urls": ["https://example.com/reference"],
                }
            ]
        },
        collection_report={
            "summary": {"collected_count": 1, "metadata_only_remote_candidate_count": 0},
            "records": [
                {
                    "source_id": "soft_story_reference",
                    "status": "collected",
                    "artifacts": {
                        "copied_source_path": "implementation/phase1/open_data/irregular/collected/artifacts/soft_story/reference.pdf"
                    },
                }
            ],
        },
        top5_manifest={
            "top5_families": [
                {
                    "family_id": "soft_story_podium_tower",
                    "execution_mode": "reference_collected_only",
                    "source_ids": ["soft_story_reference"],
                    "local_paths": [],
                    "reference_paths": ["implementation/phase1/open_data/irregular/collected/artifacts/soft_story/reference.pdf"],
                    "recommended_source_format": "model_text",
                    "irregularity_tags": ["soft_story", "vertical_irregularity"],
                    "recommended_kpi_or_validation_angle": "story stiffness ratio",
                    "why_it_matters": "soft story podium",
                }
            ]
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_EXECUTION_START_BLOCKED"
    assert payload["summary"]["ready_task_count"] == 0
    assert payload["summary"]["blocked_task_count"] == 1
    blocked_task = payload["blocked_tasks"][0]
    assert blocked_task["blocker_reason"] == "materialize_executable_model"
    assert blocked_task["required_action"] == "materialize_executable_model"


def test_attach_irregular_benchmark_receipts_materializes_proxy_receipts(tmp_path) -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "proxy_local",
                    "family_id": "transfer_podium_tower",
                    "source_urls": ["https://example.com/proxy.json"],
                    "companion_paths": [str(tmp_path / "bridge_report.json")],
                }
            ]
        },
        collection_report={"summary": {"collected_count": 1, "metadata_only_remote_candidate_count": 0}},
        top5_manifest={
            "summary": {"top5_local_ready_count": 1, "top5_proxy_ready_count": 1},
            "top5_families": [
                {
                    "family_id": "transfer_podium_tower",
                    "execution_mode": "ready_local_proxy_now",
                    "recommended_source_kind": "repo_local_proxy",
                    "recommended_evidence_class": "repo_local_proxy",
                    "recommended_source_format": "json_graph",
                    "source_ids": ["proxy_local"],
                    "local_paths": [str(tmp_path / "model.json")],
                    "irregularity_tags": ["load_transfer", "transfer_story"],
                    "recommended_kpi_or_validation_angle": "transfer-story demand ratio",
                    "why_it_matters": "transfer podium",
                }
            ],
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )
    (tmp_path / "model.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "bridge_report.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    payload = attach_irregular_benchmark_receipts(payload, receipt_root=tmp_path / "receipts")

    ready_task = payload["ready_tasks"][0]
    assert ready_task["benchmark_readiness_tier"] == "proxy"
    assert ready_task["benchmark_receipt_json"].endswith("transfer_podium_tower.benchmark_receipt.json")
    assert ready_task["benchmark_receipt_md"].endswith("transfer_podium_tower.benchmark_receipt.md")
    assert (tmp_path / "receipts" / "transfer_podium_tower.benchmark_receipt.json").exists()
    assert (tmp_path / "receipts" / "transfer_podium_tower.benchmark_receipt.md").exists()
    assert payload["summary"]["receipt_count"] == 1


def test_attach_irregular_benchmark_receipts_includes_structured_transfer_hunt_summary(tmp_path) -> None:
    payload = build_irregular_benchmark_execution_manifest(
        source_catalog={
            "source_records": [
                {
                    "source_id": "peer_transfer_podium_tower_remote",
                    "family_id": "transfer_podium_tower",
                    "source_urls": ["https://peer.berkeley.edu/example.pdf"],
                }
            ]
        },
        collection_report={"summary": {"collected_count": 1, "metadata_only_remote_candidate_count": 0}},
        top5_manifest={
            "summary": {"top5_local_ready_count": 1, "top5_proxy_ready_count": 0, "top5_bridged_ready_count": 1},
            "top5_families": [
                {
                    "family_id": "transfer_podium_tower",
                    "execution_mode": "ready_local_bridged_now",
                    "recommended_source_kind": "repo_local_bridged",
                    "recommended_evidence_class": "repo_local_bridged_graph",
                    "recommended_source_format": "json_graph",
                    "source_ids": ["peer_transfer_podium_tower_remote"],
                    "local_paths": [str(tmp_path / "model.json")],
                    "companion_paths": [str(tmp_path / "bridge_report.json")],
                    "irregularity_tags": ["transfer_story"],
                    "recommended_kpi_or_validation_angle": "transfer-story demand ratio",
                    "why_it_matters": "transfer podium",
                }
            ],
        },
        source_catalog_path="catalog.json",
        collection_report_path="collection.json",
        top5_manifest_path="top5.json",
    )
    (tmp_path / "model.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    (tmp_path / "bridge_report.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    payload = attach_irregular_benchmark_receipts(payload, receipt_root=tmp_path / "receipts")

    receipt_path = tmp_path / "receipts" / "transfer_podium_tower.benchmark_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    why = receipt["why_still_bridged"]
    assert why["audit_note"].startswith("official benchmark documentation checked, native package not found as of ")
    assert why["canonical_upgrade_path"] == "collect official benchmark-native package"
    assert "next_source_url" not in why
    assert "source_hunt_summary_structured" not in why
    md_path = tmp_path / "receipts" / "transfer_podium_tower.benchmark_receipt.md"
    md_text = md_path.read_text(encoding="utf-8")
    assert "## Why Still Bridged" in md_text
    assert "canonical_upgrade_path" in md_text
    assert "## Transfer Hunt Summary" not in md_text
    assert "## Reference PDF Hunt" not in md_text
    assert "## Author Whitelist Scan" not in md_text
    assert "source_hunt_summary_structured" not in md_text
    assert payload["summary"]["receipt_count"] == 1
