from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/authoring/generate_korean_solver_ready_reconstruction_report.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_korean_solver_ready_reconstruction_report_materializes_artifact(tmp_path: Path) -> None:
    catalog = tmp_path / "korean_source_catalog.json"
    out = tmp_path / "korean_solver_ready_reconstruction_report.json"
    artifact_root = tmp_path / "solver_ready_reconstruction"
    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "buildingSMART Korea IFC 구조 골조 예제",
                    "source_class": "ifc_public",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "structure_type": "public_facility",
                    "structural_system": "steel_frame",
                    "storey_band": "mid_rise",
                    "exact_topology_candidate": True,
                    "native_writeback_candidate": False,
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--korean-source-catalog",
            str(catalog),
            "--artifact-root",
            str(artifact_root),
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
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["prepared_count"] == 1
    assert payload["summary"]["materialized_count"] == 1
    assert len(payload["rows"]) == 1

    row = payload["rows"][0]
    artifact_json = Path(row["artifact_json"])
    artifact_md = Path(row["artifact_markdown"])
    assert artifact_json.exists()
    assert artifact_md.exists()
    assert row["reconstruction_ready"] is True
    assert row["blocker_before"] == "pending_solver_ready_reconstruction"
    assert row["blocker_after"] == "korean_structural_preview_materialization_pending"
    assert "status=materialized" in row["summary_line"]

    artifact_payload = json.loads(artifact_json.read_text(encoding="utf-8"))
    assert artifact_payload["schema_version"] == "korean_solver_ready_reconstruction_artifact.v1"
    assert artifact_payload["source_id"] == "ifc_public_award_structure"
    assert artifact_payload["reconstruction_status"] == "materialized"
    assert artifact_payload["blocker_before"] == "pending_solver_ready_reconstruction"
    assert artifact_payload["blocker_after"] == "korean_structural_preview_materialization_pending"
    assert artifact_payload["truthful_contract"] is True
    assert artifact_payload["local_first"] is True


def test_generate_korean_solver_ready_reconstruction_report_stays_pending_without_candidate(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "korean_source_catalog.json"
    out = tmp_path / "korean_solver_ready_reconstruction_report.json"
    artifact_root = tmp_path / "solver_ready_reconstruction"
    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "buildingSMART Korea IFC 구조 골조 예제",
                    "source_class": "ifc_public",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "structure_type": "public_facility",
                    "structural_system": "steel_frame",
                    "storey_band": "mid_rise",
                    "exact_topology_candidate": False,
                    "native_writeback_candidate": False,
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--korean-source-catalog",
            str(catalog),
            "--artifact-root",
            str(artifact_root),
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
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_PENDING"
    assert payload["summary"]["candidate_count"] == 0
    assert payload["summary"]["prepared_count"] == 0
    assert payload["summary"]["materialized_count"] == 0
    assert payload["rows"] == []
    assert not any(artifact_root.rglob("*.solver_ready_reconstruction_artifact.json"))

