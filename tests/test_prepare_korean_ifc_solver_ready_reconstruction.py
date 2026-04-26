from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/authoring/prepare_korean_ifc_solver_ready_reconstruction.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_prepare_korean_ifc_solver_ready_reconstruction_marks_missing_local_reference(tmp_path: Path) -> None:
    catalog = tmp_path / "korean_source_catalog.json"
    collection = tmp_path / "korean_public_structure_collection_report.json"
    out_dir = tmp_path / "solver_ready_reconstruction"
    out = tmp_path / "korean_solver_ready_reconstruction_report.json"

    _write_json(
        catalog,
        {
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                    "exact_topology_candidate": True,
                    "collection_policy": "local_first_manual_attach",
                    "curated_local_ifc_required": True,
                    "curated_local_ifc_status": "required_missing",
                }
            ]
        },
    )
    _write_json(collection, {"records": []})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--korean-source-catalog",
            str(catalog),
            "--korean-collection-report",
            str(collection),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["prepared_count"] == 0
    assert payload["summary"]["missing_local_reference_count"] == 1
    assert payload["summary"]["missing_curated_local_ifc_reference_count"] == 1
    assert payload["rows"][0]["source_id"] == "ifc_public_award_structure"
    assert payload["rows"][0]["status"] == "missing_curated_local_ifc_reference"


def test_prepare_korean_ifc_solver_ready_reconstruction_prepares_local_ifc(tmp_path: Path) -> None:
    catalog = tmp_path / "korean_source_catalog.json"
    collection = tmp_path / "korean_public_structure_collection_report.json"
    out_dir = tmp_path / "solver_ready_reconstruction"
    out = tmp_path / "korean_solver_ready_reconstruction_report.json"
    local_ifc = tmp_path / "award.ifc"
    local_ifc.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "HEADER;",
                "ENDSEC;",
                "DATA;",
                "#1=IFCBUILDINGSTOREY('a',$,'L1',$,$,$,$,$);",
                "#2=IFCCOLUMN('b',$,'C1',$,$,$,$);",
                "#3=IFCBEAM('c',$,'B1',$,$,$,$);",
                "#4=IFCSLAB('d',$,'S1',$,$,$,$,.FLOOR.);",
                "ENDSEC;",
                "END-ISO-10303-21;",
            ]
        ),
        encoding="utf-8",
    )

    _write_json(
        catalog,
        {
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                    "exact_topology_candidate": True,
                    "collection_policy": "local_first_manual_attach",
                    "curated_local_ifc_required": True,
                    "curated_local_ifc_status": "attached",
                    "curated_local_ifc_reference": str(local_ifc),
                }
            ]
        },
    )
    _write_json(
        collection,
        {
            "records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "local_path": str(local_ifc),
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--korean-source-catalog",
            str(catalog),
            "--korean-collection-report",
            str(collection),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["prepared_count"] == 1
    assert payload["rows"][0]["status"] == "prepared"
    assert payload["rows"][0]["reconstruction_ready"] is True
    assert payload["rows"][0]["structural_preview_case_id"] == "ifc_public_award_structure__structural_preview_candidate"
    artifact_json = Path(payload["rows"][0]["artifact_json"])
    assert artifact_json.exists()
    artifact = json.loads(artifact_json.read_text(encoding="utf-8"))
    assert artifact["contract_pass"] is True
    assert artifact["metrics"]["ifc_storey_count"] == 1
    assert artifact["metrics"]["ifc_structural_entity_total"] == 3
