from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from implementation.phase1.open_data.korea.generate_korean_source_catalog import (
    DEFAULT_SOURCE_ROWS,
    MEDIUM_LARGE_SEED_PATH,
    build_korean_source_catalog,
    load_merged_korean_seed_rows,
)
from implementation.phase1.open_data.korea.korean_source_schema import SCHEMA_VERSION
import pytest


SCRIPT = Path("implementation/phase1/open_data/korea/generate_korean_source_catalog.py")


def test_generate_korean_source_catalog_normalizes_default_seed_inventory() -> None:
    catalog = build_korean_source_catalog(DEFAULT_SOURCE_ROWS, generated_at_utc="2026-04-07T00:00:00Z")

    assert catalog["schema_version"] == SCHEMA_VERSION
    assert catalog["generated_at_utc"] == "2026-04-07T00:00:00Z"
    assert catalog["summary"]["record_count"] == 15
    assert catalog["summary"]["source_class_counts"] == {
        "aik_kci": 3,
        "ifc_public": 5,
        "koneps": 3,
        "lh_sh": 4,
    }
    assert catalog["summary"]["seed_priority_counts"] == {"P0": 11, "P1": 4}
    assert catalog["summary"]["promotion_hint_counts"] == {
        "exact_topology_candidate": 5,
        "native_writeback_candidate": 5,
        "preview_roundtrip_candidate": 3,
        "white_box_calibration_candidate": 2,
    }
    assert catalog["summary"]["collection_policy_counts"] == {
        "local_first_manual_attach": 10,
        "static_seed_only": 5,
    }
    assert catalog["summary"]["seed_metadata_complete_count"] == 15
    assert catalog["summary"]["exact_topology_candidate_count"] == 5
    assert catalog["summary"]["native_writeback_candidate_count"] == 5
    assert catalog["summary"]["curated_local_ifc_required_count"] == 5
    assert catalog["summary"]["curated_local_ifc_attached_count"] == 5
    assert catalog["summary"]["p0_focus_candidate_count"] == 11
    assert "seed_complete=15" in catalog["summary_line"]
    assert "p0_focus=11" in catalog["summary_line"]
    assert [row["source_id"] for row in catalog["source_records"]] == [
        "koneps_hangang_park_gwangnaru2_design_service",
        "koneps_goyang_changneung_powerplant_design_service",
        "koneps_hangang_park_gwangnaru2_native_baseline",
        "lh_bucheon_yeokgok_a1_housing_competition",
        "lh_happy_city_5_1_design_competition",
        "lh_bucheon_yeokgok_a1_housing_native_baseline",
        "lh_happy_city_5_1_native_baseline",
        "kci_concrete_building_design_examples_2e",
        "kci_strut_tie_model_design_examples",
        "kci_concrete_building_design_examples_2e_native_baseline",
        "ifc_public_award_structure",
        "ifc_public_award_reference_2022",
        "ifc_public_award_reference_2021",
        "ifc_public_award_reference_2024",
        "ifc_public_award_reference_2020",
    ]

    assert catalog["source_records"][0]["seed_basis"] == "official g2b attachment seed for public building design-service package"
    assert catalog["source_records"][0]["seed_priority"] == "P0"
    assert catalog["source_records"][0]["promotion_hint"] == "preview_roundtrip_candidate"
    assert catalog["source_records"][1]["promotion_hint"] == "native_writeback_candidate"
    assert catalog["source_records"][10]["seed_priority"] == "P0"
    assert catalog["source_records"][10]["promotion_hint"] == "exact_topology_candidate"
    assert catalog["source_records"][10]["collection_policy"] == "local_first_manual_attach"
    assert catalog["source_records"][10]["curated_local_ifc_required"] is True
    assert catalog["source_records"][10]["curated_local_ifc_status"] == "attached"
    assert catalog["source_records"][10]["curated_local_ifc_reference"] == "implementation/phase1/open_data/korea/curated/ifc_public_award_structure.ifc"

    for row in catalog["source_records"]:
        assert row["ingest_status"] == "discovered"
        assert row["source_id"]
        assert "sha256" in row
        assert "local_path" in row
        assert "retrieved_at_utc" in row
        assert "seed_basis" in row
        assert "seed_priority" in row
        assert "promotion_hint" in row
        assert "collection_policy" in row
        assert "curated_local_ifc_required" in row
        assert "curated_local_ifc_status" in row
        assert "curated_local_ifc_reference" in row


def test_generate_korean_source_catalog_cli_writes_output(tmp_path: Path) -> None:
    out_path = tmp_path / "korean_source_catalog.json"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_path), "--no-medium-large-seed"],
        cwd=Path(__file__).resolve().parents[1],
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert f"Wrote Korean source catalog: {out_path}" in proc.stdout

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["summary"]["record_count"] == 15
    assert payload["summary"]["seed_priority_counts"] == {"P0": 11, "P1": 4}
    assert payload["summary"]["seed_metadata_complete_count"] == 15
    assert payload["summary"]["curated_local_ifc_required_count"] == 5
    assert payload["summary"]["curated_local_ifc_attached_count"] == 5


def test_load_merged_korean_seed_rows_includes_medium_large_extension() -> None:
    if not MEDIUM_LARGE_SEED_PATH.is_file():
        return
    merged = load_merged_korean_seed_rows()
    assert len(merged) > len(DEFAULT_SOURCE_ROWS)
    catalog = build_korean_source_catalog(merged, generated_at_utc="2026-05-31T00:00:00Z")
    assert catalog["summary"]["record_count"] == len(merged)


def test_generate_korean_source_catalog_cli_writes_merged_output(tmp_path: Path) -> None:
    if not MEDIUM_LARGE_SEED_PATH.is_file():
        return
    out_path = tmp_path / "korean_source_catalog_merged.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["summary"]["record_count"] > 15


def test_build_korean_source_catalog_rejects_inconsistent_promotion_hint_flags() -> None:
    broken = [dict(DEFAULT_SOURCE_ROWS[1], native_writeback_candidate=False)]

    with pytest.raises(ValueError, match="promotion_hint=native_writeback_candidate requires native_writeback_candidate=true"):
        build_korean_source_catalog(broken, generated_at_utc="2026-04-07T00:00:00Z")
