from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import pytest

from implementation.phase1.open_data.korea.collect_korean_public_structures import (
    collect_korean_public_structures,
)


SCRIPT = Path("implementation/phase1/open_data/korea/collect_korean_public_structures.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_collect_korean_public_structures_mixed_local_and_remote(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    mgt_path = source_dir / "public_building.mgt"
    mgt_path.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    ifc_path = source_dir / "award.ifc"
    ifc_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    catalog = tmp_path / "korean_source_catalog.json"
    out_dir = tmp_path / "out"
    report_out = tmp_path / "korean_public_structure_collection_report.json"
    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "koneps_case",
                    "title": "KONEPS case",
                    "source_class": "koneps",
                    "origin_type": "public_notice_attachment",
                    "format": "mgt",
                    "content_kind": "native_text_model",
                    "seed_basis": "local test seed",
                    "seed_priority": "P0",
                    "promotion_hint": "native_writeback_candidate",
                    "collection_policy": "static_seed_only",
                    "provenance_url": "https://example.go.kr/public_building.mgt",
                    "local_path": str(mgt_path),
                    "native_writeback_candidate": True,
                },
                {
                    "source_id": "ifc_case",
                    "title": "IFC case",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "seed_basis": "local test seed",
                    "seed_priority": "P0",
                    "promotion_hint": "exact_topology_candidate",
                    "collection_policy": "local_first_manual_attach",
                    "provenance_url": "https://event.buildingsmart.or.kr/Awards/2023",
                    "download_url": "https://event.buildingsmart.or.kr/Awards/2023",
                    "exact_topology_candidate": True,
                    "curated_local_ifc_required": True,
                    "curated_local_ifc_status": "attached",
                    "curated_local_ifc_reference": str(ifc_path),
                },
                {
                    "source_id": "remote_case",
                    "title": "Remote case",
                    "source_class": "lh_sh",
                    "origin_type": "competition_base_material",
                    "format": "zip",
                    "content_kind": "archive_bundle",
                    "seed_basis": "local test seed",
                    "seed_priority": "P0",
                    "promotion_hint": "preview_roundtrip_candidate",
                    "collection_policy": "static_seed_only",
                    "provenance_url": "https://example.lh.or.kr/base.zip",
                    "download_url": "https://example.lh.or.kr/base.zip",
                },
            ],
        },
    )

    report = collect_korean_public_structures(catalog, out_dir, report_out)

    assert report["contract_pass"] is True
    assert report["summary"]["source_count"] == 3
    assert report["summary"]["collected_count"] == 2
    assert report["summary"]["metadata_only_remote_candidate_count"] == 1
    assert report["summary"]["rejected_count"] == 0
    assert report["summary"]["local_path_count"] == 2
    assert report["summary"]["file_url_count"] == 0
    assert report["summary"]["remote_reference_count"] == 1
    assert report["summary"]["exact_topology_candidate_count"] == 1
    assert report["summary"]["native_writeback_candidate_count"] == 1
    assert report["summary"]["seed_priority_counts"] == {"P0": 3}
    assert report["summary"]["promotion_hint_counts"] == {
        "exact_topology_candidate": 1,
        "native_writeback_candidate": 1,
        "preview_roundtrip_candidate": 1,
    }
    assert report["summary"]["collection_policy_counts"] == {
        "local_first_manual_attach": 1,
        "static_seed_only": 2,
    }
    assert report["summary"]["seed_metadata_complete_count"] == 3
    assert report["summary"]["curated_local_ifc_required_count"] == 1
    assert report["summary"]["curated_local_ifc_attached_count"] == 1
    assert report["summary"]["p0_focus_candidate_count"] == 3
    assert "seed_complete=3" in report["summary_line"]
    assert "curated_local_ifc=1/1" in report["summary_line"]
    assert "p0_focus=3" in report["summary_line"]

    rows = {row["source_id"]: row for row in report["records"]}
    assert rows["koneps_case"]["status"] == "collected"
    assert rows["ifc_case"]["status"] == "collected"
    assert rows["remote_case"]["status"] == "metadata_only_remote_candidate"
    assert rows["ifc_case"]["curated_local_ifc_required"] is True
    assert rows["ifc_case"]["curated_local_ifc_status"] == "attached"
    assert rows["koneps_case"]["seed_priority"] == "P0"
    assert rows["ifc_case"]["promotion_hint"] == "exact_topology_candidate"
    assert Path(rows["koneps_case"]["artifacts"]["copied_source_path"]).exists()
    assert Path(rows["ifc_case"]["artifacts"]["source_metadata_path"]).exists()
    metadata = json.loads(Path(rows["ifc_case"]["artifacts"]["source_metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["seed_basis"] == "local test seed"
    assert metadata["seed_priority"] == "P0"
    assert metadata["promotion_hint"] == "exact_topology_candidate"
    assert metadata["collection_policy"] == "local_first_manual_attach"
    assert metadata["curated_local_ifc_required"] is True
    assert metadata["curated_local_ifc_status"] == "attached"


def test_collect_korean_public_structures_cli_writes_output(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = source_dir / "example.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    catalog = tmp_path / "korean_source_catalog.json"
    report_out = tmp_path / "report.json"
    out_dir = tmp_path / "out"
    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "aik_case",
                    "title": "AIK case",
                    "source_class": "aik_kci",
                    "origin_type": "society_example_appendix",
                    "format": "pdf",
                    "content_kind": "structural_report",
                    "seed_basis": "local test seed",
                    "seed_priority": "P1",
                    "promotion_hint": "white_box_calibration_candidate",
                    "collection_policy": "static_seed_only",
                    "provenance_url": "file://" + str(pdf_path),
                }
            ],
        },
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--catalog", str(catalog), "--out-dir", str(out_dir), "--report-out", str(report_out)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert f"Wrote Korean public structure collection report: {report_out}" in proc.stdout
    payload = json.loads(report_out.read_text(encoding="utf-8"))
    assert payload["summary"]["collected_count"] == 1
    assert payload["summary"]["seed_metadata_complete_count"] == 1


def test_collect_korean_public_structures_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    mgt_path = source_dir / "a.mgt"
    mgt_path.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    catalog = tmp_path / "korean_source_catalog.json"
    report_out = tmp_path / "report.json"
    out_dir = tmp_path / "out"
    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "dup",
                    "title": "Case A",
                    "source_class": "koneps",
                    "origin_type": "public_notice_attachment",
                    "format": "mgt",
                    "content_kind": "native_text_model",
                    "provenance_url": "https://example/a.mgt",
                    "local_path": str(mgt_path),
                },
                {
                    "source_id": "dup",
                    "title": "Case B",
                    "source_class": "lh_sh",
                    "origin_type": "competition_base_material",
                    "format": "zip",
                    "content_kind": "archive_bundle",
                    "provenance_url": "https://example/b.zip",
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="duplicate source_id"):
        collect_korean_public_structures(catalog, out_dir, report_out)
