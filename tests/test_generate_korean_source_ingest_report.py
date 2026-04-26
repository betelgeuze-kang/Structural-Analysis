from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.open_data.korea.generate_korean_source_ingest_report import (
    build_korean_source_ingest_report,
)


SCRIPT = Path("implementation/phase1/open_data/korea/generate_korean_source_ingest_report.py")


def test_build_korean_source_ingest_report_tracks_sha_and_duplicates() -> None:
    catalog = {
        "schema_version": "korean_source_catalog.v1",
        "source_records": [
            {
                "source_id": "a",
                "title": "KONEPS A",
                "source_class": "koneps",
                "origin_type": "public_notice_attachment",
                "origin_org": "조달청",
                "format": "mgt",
                "content_kind": "native_text_model",
                "structure_type": "building",
                "structural_system": "rc_frame",
                "storey_band": "20_40",
                "seed_basis": "local test seed",
                "seed_priority": "P0",
                "promotion_hint": "native_writeback_candidate",
                "collection_policy": "static_seed_only",
                "provenance_url": "https://example/a.mgt",
                "download_url": "https://example/a.mgt",
                "license_hint": "public",
                "exact_topology_candidate": True,
                "native_writeback_candidate": True,
                "notes": "seed one",
            },
            {
                "source_id": "b",
                "title": "LH B",
                "source_class": "lh_sh",
                "origin_type": "competition_base_material",
                "origin_org": "LH",
                "format": "zip",
                "content_kind": "archive_bundle",
                "structure_type": "housing",
                "structural_system": "wall_frame_hybrid",
                "storey_band": "20_30",
                "seed_basis": "local test seed",
                "seed_priority": "P0",
                "promotion_hint": "preview_roundtrip_candidate",
                "collection_policy": "static_seed_only",
                "provenance_url": "https://example/b.zip",
                "download_url": "https://example/b.zip",
                "license_hint": "competition",
                "notes": "seed two",
            },
            {
                "source_id": "c",
                "title": "AIK C",
                "source_class": "aik_kci",
                "origin_type": "society_example_appendix",
                "origin_org": "AIK/KCI",
                "format": "pdf",
                "content_kind": "structural_report",
                "structure_type": "building",
                "structural_system": "rc_frame",
                "storey_band": "10_20",
                "seed_basis": "local test seed",
                "seed_priority": "P1",
                "promotion_hint": "white_box_calibration_candidate",
                "collection_policy": "static_seed_only",
                "provenance_url": "https://example/c.pdf",
                "download_url": "https://example/c.pdf",
                "license_hint": "society",
                "notes": "seed three",
            },
        ],
    }
    collection_report = {
        "records": [
            {
                "source_id": "a",
                "sha256": "same",
                "local_path": "/tmp/a.mgt",
                "retrieved_at_utc": "2026-04-07T00:00:00Z",
                "reference_scheme": "local_path",
                "status": "collected",
                "ingest_status": "fingerprinted",
                "byte_count": 12,
            },
            {
                "source_id": "b",
                "sha256": "same",
                "local_path": "/tmp/b.zip",
                "retrieved_at_utc": "2026-04-07T00:00:01Z",
                "reference_scheme": "file_url",
                "status": "collected",
                "ingest_status": "fingerprinted",
                "byte_count": 34,
            },
            {
                "source_id": "c",
                "reference_scheme": "remote_reference",
                "status": "metadata_only_remote_candidate",
                "ingest_status": "discovered",
                "byte_count": 0,
            },
        ]
    }

    report = build_korean_source_ingest_report(catalog, collection_report)

    assert report["summary"]["source_count"] == 3
    assert report["summary"]["fingerprinted_count"] == 2
    assert report["summary"]["metadata_only_count"] == 1
    assert report["summary"]["duplicate_sha_group_count"] == 1
    assert report["summary"]["exact_topology_candidate_count"] == 1
    assert report["summary"]["native_writeback_candidate_count"] == 1
    assert report["summary"]["seed_priority_counts"] == {"P0": 2, "P1": 1}
    assert report["summary"]["promotion_hint_counts"] == {
        "native_writeback_candidate": 1,
        "preview_roundtrip_candidate": 1,
        "white_box_calibration_candidate": 1,
    }
    assert report["summary"]["collection_policy_counts"] == {"static_seed_only": 3}
    assert report["summary"]["seed_metadata_complete_count"] == 3
    assert report["duplicate_sha_groups"][0]["source_ids"] == ["a", "b"]
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert "duplicate_sha_groups=1" in report["summary_line"]
    assert "seed_complete=3" in report["summary_line"]
    assert "exact_topology=1" in report["summary_line"]
    assert "native_writeback=1" in report["summary_line"]
    assert "p0_focus=2" in report["summary_line"]

    row_a = next(row for row in report["records"] if row["source_id"] == "a")
    assert row_a["title"] == "KONEPS A"
    assert row_a["origin_type"] == "public_notice_attachment"
    assert row_a["origin_org"] == "조달청"
    assert row_a["structure_type"] == "building"
    assert row_a["structural_system"] == "rc_frame"
    assert row_a["storey_band"] == "20_40"
    assert row_a["seed_basis"] == "local test seed"
    assert row_a["seed_priority"] == "P0"
    assert row_a["promotion_hint"] == "native_writeback_candidate"
    assert row_a["collection_policy"] == "static_seed_only"
    assert row_a["download_url"] == "https://example/a.mgt"
    assert row_a["exact_topology_candidate"] is True
    assert row_a["native_writeback_candidate"] is True
    assert row_a["notes"] == "seed one"


def test_generate_korean_source_ingest_report_cli_writes_output(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    collection_path = tmp_path / "collection.json"
    out_path = tmp_path / "ingest_report.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": "korean_source_catalog.v1",
                "source_records": [
                {
                    "source_id": "a",
                    "title": "KONEPS A",
                    "source_class": "koneps",
                    "origin_type": "public_notice_attachment",
                    "origin_org": "조달청",
                    "format": "mgt",
                    "content_kind": "native_text_model",
                    "structure_type": "building",
                    "structural_system": "rc_frame",
                    "storey_band": "20_40",
                    "seed_basis": "local test seed",
                    "seed_priority": "P0",
                    "promotion_hint": "native_writeback_candidate",
                    "collection_policy": "static_seed_only",
                    "provenance_url": "https://example/a.mgt",
                    "download_url": "https://example/a.mgt",
                    "license_hint": "public",
                }
            ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    collection_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_id": "a",
                        "sha256": "abc",
                        "local_path": "/tmp/a.mgt",
                        "retrieved_at_utc": "2026-04-07T00:00:00Z",
                        "reference_scheme": "local_path",
                        "status": "collected",
                        "ingest_status": "fingerprinted",
                        "byte_count": 12,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--catalog", str(catalog_path), "--collection-report", str(collection_path), "--out", str(out_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert f"Wrote Korean source ingest report: {out_path}" in proc.stdout
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["summary"]["fingerprinted_count"] == 1
    assert payload["summary"]["seed_metadata_complete_count"] == 1
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["records"][0]["title"] == "KONEPS A"
