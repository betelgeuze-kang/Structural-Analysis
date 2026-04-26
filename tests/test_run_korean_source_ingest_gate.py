from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/run_korean_source_ingest_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_korean_source_ingest_gate_passes_with_full_class_coverage(tmp_path: Path) -> None:
    catalog = tmp_path / "korean_source_catalog.json"
    collection = tmp_path / "korean_public_structure_collection_report.json"
    ingest = tmp_path / "korean_source_ingest_report.json"
    out = tmp_path / "korean_source_ingest_gate_report.json"

    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "summary": {
                "record_count": 4,
                "source_class_counts": {"koneps": 1, "lh_sh": 1, "aik_kci": 1, "ifc_public": 1},
            },
            "source_records": [{"source_id": f"s{i}"} for i in range(4)],
        },
    )
    _write_json(
        collection,
        {
            "contract_pass": True,
            "summary": {
                "source_count": 4,
                "collected_count": 1,
                "metadata_only_remote_candidate_count": 3,
                "rejected_count": 0,
            },
            "summary_line": "Korean source collect: PASS | sources=4 | collected=1 | metadata_only=3 | rejected=0 | bytes=12",
        },
    )
    _write_json(
        ingest,
        {
            "contract_pass": True,
            "summary": {
                "source_count": 4,
                "fingerprinted_count": 1,
                "metadata_only_count": 3,
                "rejected_count": 0,
                "duplicate_sha_group_count": 0,
            },
            "summary_line": "Korean source ingest: PASS | sources=4 | fingerprinted=1 | metadata_only=3 | rejected=0 | duplicate_sha_groups=0",
            "records": [{"source_id": f"s{i}"} for i in range(4)],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--catalog",
            str(catalog),
            "--collection-report",
            str(collection),
            "--ingest-report",
            str(ingest),
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
    assert payload["summary"]["source_count"] == 4
    assert payload["summary"]["source_class_count"] == 4
    assert payload["checks"]["collection_accounting_pass"] is True
    assert payload["checks"]["ingest_accounting_pass"] is True
    assert payload["summary_line"].startswith("Korean source ingest gate: PASS")


def test_run_korean_source_ingest_gate_fails_when_class_coverage_is_thin(tmp_path: Path) -> None:
    catalog = tmp_path / "korean_source_catalog.json"
    collection = tmp_path / "korean_public_structure_collection_report.json"
    ingest = tmp_path / "korean_source_ingest_report.json"
    out = tmp_path / "korean_source_ingest_gate_report.json"

    _write_json(
        catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "summary": {"record_count": 2, "source_class_counts": {"koneps": 2}},
            "source_records": [{"source_id": "a"}, {"source_id": "b"}],
        },
    )
    _write_json(
        collection,
        {
            "contract_pass": True,
            "summary": {
                "source_count": 2,
                "collected_count": 1,
                "metadata_only_remote_candidate_count": 1,
                "rejected_count": 0,
            },
        },
    )
    _write_json(
        ingest,
        {
            "contract_pass": True,
            "summary": {
                "source_count": 2,
                "fingerprinted_count": 1,
                "metadata_only_count": 1,
                "rejected_count": 0,
                "duplicate_sha_group_count": 0,
            },
            "records": [{"source_id": "a"}, {"source_id": "b"}],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--catalog",
            str(catalog),
            "--collection-report",
            str(collection),
            "--ingest-report",
            str(ingest),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CATALOG"
    assert payload["checks"]["source_class_coverage_pass"] is False
