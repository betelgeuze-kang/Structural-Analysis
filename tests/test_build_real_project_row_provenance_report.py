from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/build_real_project_row_provenance_report.py"
SEED_MANIFEST = REPO_ROOT / "implementation/phase1/real_project_corpus_seed_manifest.json"
COVERAGE_MATRIX = REPO_ROOT / "implementation/phase1/real_project_parser_coverage_matrix.json"
PEER_METRIC_RECORDS = REPO_ROOT / "implementation/phase1/peer_tbi_benchmark_metric_records.json"

REQUIRED_ROW_FIELDS = {
    "row_id",
    "source_id",
    "source_label",
    "source_kind",
    "jurisdiction",
    "official_url",
    "p0_upstream_hard_gate",
    "access_policy",
    "artifact_status",
    "checksum_status_or_withheld_reason",
    "file_inventory_status",
    "parser_contract",
    "row_pointer",
    "release_surface_allowed",
    "blocked_reason",
}


def _run_cli(out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(SEED_MANIFEST),
            "--coverage-matrix",
            str(COVERAGE_MATRIX),
            "--peer-metric-records",
            str(PEER_METRIC_RECORDS),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_real_project_row_provenance_report_cli_contract(tmp_path: Path) -> None:
    out = tmp_path / "real_project_row_provenance_report.json"

    proc = _run_cli(out)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "real_project_row_provenance_report.v1"
    assert payload["run_id"] == "phase1-real-project-row-provenance-report"
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["p0_upstream_hard_gate"] is True
    assert payload["row_provenance_coverage"] == 1.0
    assert payload["raw_redistribution_default_blocked"] is True
    assert payload["summary"]["required_source_families_present"] is True
    assert payload["summary"]["p0_hard_gate_represented"] is True
    assert payload["summary"]["row_provenance_coverage"] == 1.0
    assert payload["summary"]["row_count"] == 2
    assert payload["summary"]["release_surface_allowed_count"] == 0
    assert payload["summary"]["peer_tbi_metric_group_count"] == 5
    assert payload["summary"]["all_rows_have_required_fields"] is True
    assert payload["promoted_row_provenance_rows"] == []

    rows_by_id = {row["source_id"]: row for row in payload["source_provenance_rows"]}
    assert {"koneps_turnkey_design_docs", "peer_tbi_tall_buildings"} <= set(rows_by_id)

    for row in rows_by_id.values():
        assert REQUIRED_ROW_FIELDS <= set(row)
        assert row["p0_upstream_hard_gate"] is True
        assert row["release_surface_allowed"] is False
        assert row["blocked_reason"]
        assert row["access_policy"]["redistribution_allowed"] is False
        assert row["access_policy"]["requires_manual_review"] is True
        assert {"source_file", "json_path"} <= set(row["row_pointer"])

    koneps = rows_by_id["koneps_turnkey_design_docs"]
    assert koneps["artifact_status"] == "metadata_only_candidate_pending_artifact_review"
    assert koneps["checksum_status_or_withheld_reason"] == "withheld_until_artifact_level_review"
    assert koneps["file_inventory_status"] == "not_collected_metadata_seed_only"
    assert koneps["parser_contract"]["coverage_status"] == "planned"
    assert koneps["parser_contract"]["required_target_count"] == 7
    assert koneps["parser_contract"]["source_file"] == "real_project_parser_coverage_matrix.json"

    peer = rows_by_id["peer_tbi_tall_buildings"]
    assert peer["artifact_status"] == "citation_metric_records_seeded_no_raw_models"
    assert peer["checksum_status_or_withheld_reason"] == "raw_model_files_not_redistributed"
    assert peer["file_inventory_status"] == "peer_tbi_benchmark_metric_records.json"
    assert peer["parser_contract"]["metric_group_count"] == 5
    assert peer["parser_contract"]["source_file"] == "peer_tbi_benchmark_metric_records.json"
    assert peer["row_pointer"]["source_file"] == "peer_tbi_benchmark_metric_records.json"


def test_build_real_project_row_provenance_report_is_deterministic(tmp_path: Path) -> None:
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"

    proc_a = _run_cli(out_a)
    proc_b = _run_cli(out_b)

    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")
