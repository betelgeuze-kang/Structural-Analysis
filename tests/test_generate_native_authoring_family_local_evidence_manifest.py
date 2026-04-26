from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.generate_native_authoring_family_local_evidence_manifest import (
    build_native_authoring_family_local_evidence_manifest,
)


def _build_default_manifest(tmp_path: Path) -> dict:
    out = tmp_path / "native_authoring_family_local_evidence_manifest.json"
    return build_native_authoring_family_local_evidence_manifest(
        family_corpus_manifest_path=Path(
            "implementation/phase1/release/authoring/portfolio/native_authoring_family_corpus_manifest.json"
        ),
        portfolio_json_path=Path("implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json"),
        release_root=Path("implementation/phase1/release/authoring/portfolio"),
        korean_source_catalog_path=Path("implementation/phase1/open_data/korea/korean_source_catalog.json"),
        korean_source_ingest_report_path=Path("implementation/phase1/open_data/korea/korean_source_ingest_report.json"),
        korean_collection_report_path=Path(
            "implementation/phase1/open_data/korea/korean_public_structure_collection_report.json"
        ),
        benchmark_diversification_catalog_path=Path(
            "implementation/phase1/open_data/benchmark_diversification_catalog.json"
        ),
        benchmark_catalog_path=Path("implementation/phase1/open_data/megastructure/mega_structure_catalog.json"),
        authority_source_catalog_path=Path("implementation/phase1/open_data/global_authority/authority_source_catalog.json"),
        midas_native_corpus_manifest_path=Path("implementation/phase1/open_data/midas/midas_native_corpus_manifest.json"),
        out=out,
        generated_at="2026-04-21T15:00:00+09:00",
    )


def test_build_native_authoring_family_local_evidence_manifest_default_release_portfolio(tmp_path: Path) -> None:
    payload = _build_default_manifest(tmp_path)

    expected_family_ids = [
        "sample_tower",
        "steel_braced_frame",
        "rc_wall_core",
        "composite_podium",
        "outrigger_transfer_tower",
        "dual_system_hospital",
        "belt_truss_mega_frame",
        "deep_transfer_basement",
    ]

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 8
    assert payload["summary"]["concrete_local_corpus_family_count"] == 8
    assert payload["summary"]["roundtrip_concrete_family_count"] == 8
    assert payload["summary"]["benchmark_linked_family_count"] == 8
    assert payload["summary"]["benchmark_concrete_family_count"] == 6
    assert payload["summary"]["review_concrete_family_count"] == 8
    assert payload["summary"]["reference_registered_only_family_count"] == 2
    assert payload["checks"]["all_families_have_concrete_local_corpus"] is True
    assert payload["checks"]["all_families_have_roundtrip_linkage"] is True
    assert payload["checks"]["all_families_have_benchmark_linkage"] is True
    assert payload["checks"]["all_families_have_review_linkage"] is True
    assert payload["checks"]["all_families_have_test_fixture_rows"] is True
    assert [row["family_id"] for row in payload["family_rows"]] == expected_family_ids

    persisted = json.loads(
        (tmp_path / "native_authoring_family_local_evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert persisted["summary"]["benchmark_concrete_family_count"] == 6
    assert persisted["family_rows"][0]["test_fixture_count"] >= 1


def test_native_authoring_family_local_evidence_manifest_surfaces_registered_only_reference_gaps(
    tmp_path: Path,
) -> None:
    payload = _build_default_manifest(tmp_path)

    composite_row = next(row for row in payload["family_rows"] if row["family_id"] == "composite_podium")
    assert composite_row["benchmark_linkage_status"] == "linked"
    assert composite_row["registered_only_reference_count"] == 1
    peer_joint = next(
        row for row in composite_row["reference_evidence_rows"] if row["reference_id"] == "peer_rc_beam_column_joint_2003_10"
    )
    assert peer_joint["availability_status"] == "registered_only"
    assert peer_joint["benchmark_linkage_status"] == "linked"
    assert peer_joint["concrete_local_artifact_count"] == 0

    basement_row = next(row for row in payload["family_rows"] if row["family_id"] == "deep_transfer_basement")
    assert basement_row["benchmark_linkage_status"] == "linked"
    assert basement_row["registered_only_reference_count"] == 2
    basement_refs = {
        row["reference_id"]: row["availability_status"] for row in basement_row["reference_evidence_rows"]
    }
    assert basement_refs["designsafe_liquefaction_pile_foundations"] == "registered_only"
    assert basement_refs["kci_strut_tie_model_design_examples"] == "registered_only"
    assert basement_refs["koneps_goyang_changneung_powerplant_design_service"] == "concrete"

    rc_row = next(row for row in payload["family_rows"] if row["family_id"] == "rc_wall_core")
    assert rc_row["benchmark_linkage_status"] == "concrete"
    assert rc_row["review_linkage_status"] == "concrete"
    peer_spd = next(row for row in rc_row["reference_evidence_rows"] if row["reference_id"] == "peer_spd_rc_columns")
    assert peer_spd["availability_status"] == "concrete"
    assert peer_spd["benchmark_linkage_status"] == "concrete"

    sample_row = next(row for row in payload["family_rows"] if row["family_id"] == "sample_tower")
    assert sample_row["roundtrip_linkage_status"] == "concrete"
    assert sample_row["review_linkage_status"] == "concrete"
    assert sample_row["test_fixture_count"] == 2
