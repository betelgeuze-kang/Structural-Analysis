from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_irregular_structure_collection_gate_passes(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    triage = tmp_path / "triage.json"
    collection = tmp_path / "collection.json"
    top5 = tmp_path / "top5.json"
    out = tmp_path / "gate.json"

    _write(catalog, {"summary": {"family_count": 20, "source_record_count": 22, "local_ready_count": 7, "remote_candidate_count": 15, "authority_high_like_count": 21, "ai_high_like_count": 22}})
    _write(triage, {"summary": {"native_roundtrip_candidate_count": 14, "solver_benchmark_candidate_count": 11, "ai_learning_candidate_count": 22, "quick_start_local_source_count": 7}})
    _write(collection, {"contract_pass": True, "summary": {"collected_count": 7, "metadata_only_remote_candidate_count": 15, "rejected_count": 0, "format_counts": {"mgt": 3}}})
    _write(top5, {"contract_pass": True, "summary": {"top5_count": 5}, "top5_families": [{"execution_mode": "ready_local_now"}] * 2 + [{"execution_mode": "remote_source_hunt_needed"}] * 3})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_irregular_structure_collection_gate.py",
            "--source-catalog", str(catalog),
            "--triage-report", str(triage),
            "--collection-report", str(collection),
            "--top5-manifest", str(top5),
            "--out", str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["catalog_present_pass"] is True
    assert report["checks"]["collection_report_present_pass"] is True
    assert report["checks"]["top5_manifest_present_pass"] is True
    assert report["summary"]["top5_local_ready_count"] == 2
    assert report["summary"]["top5_remote_needed_count"] == 3
    assert "families=20" in report["summary_line"]


