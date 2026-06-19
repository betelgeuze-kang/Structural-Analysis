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
    "stable_row_pointer",
    "manual_review_status",
    "release_eligibility",
    "release_surface_allowed",
    "blocked_reason",
}


def _run_cli(out: Path, midas_kds_validation_report: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
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
    ]
    if midas_kds_validation_report is not None:
        cmd.extend(["--midas-kds-validation-report", str(midas_kds_validation_report)])
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _midas_kds_validation_report(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "run_id": "phase1-validate-midas-kds-geometry-bridge-artifacts",
                "contract_pass": True,
                "summary": {
                    "artifact_count": 3,
                    "exact_geometry_bridge_pass_count": 3,
                    "review_row_count_total": 3168,
                    "exact_mapped_row_provenance_count_total": 3168,
                    "full_member_crosswalk_count_total": 242,
                    "full_section_crosswalk_count_total": 200,
                    "full_load_crosswalk_count_total": 51,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_real_project_row_provenance_report_cli_contract(tmp_path: Path) -> None:
    out = tmp_path / "real_project_row_provenance_report.json"
    validation_report = _midas_kds_validation_report(tmp_path / "midas_kds_geometry_bridge_validation_report.json")

    proc = _run_cli(out, validation_report)

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
    assert payload["summary"]["row_count"] == 13
    assert payload["summary"]["measured_artifact_row_count"] == 10
    assert payload["summary"]["measured_file_format_count"] == 2
    assert payload["summary"]["measured_file_formats"] == ["ifc", "mgt"]
    assert payload["summary"]["release_surface_allowed_count"] == 0
    assert payload["summary"]["checksum_or_withheld_count"] == 13
    assert payload["summary"]["stable_row_pointer_count"] == 13
    assert payload["summary"]["manual_review_status_count"] == 13
    assert payload["summary"]["release_eligibility_count"] == 13
    assert payload["summary"]["peer_tbi_metric_group_count"] == 5
    assert payload["summary"]["all_rows_have_required_fields"] is True
    assert payload["summary"]["midas_kds_validation_present"] is True
    assert payload["summary"]["midas_kds_validation_artifact_count"] == 3
    assert payload["summary"]["midas_kds_exact_row_provenance_count"] == 3168
    assert payload["summary"]["midas_kds_review_row_count"] == 3168
    assert payload["promoted_row_provenance_rows"] == []

    rows_by_id = {row["source_id"]: row for row in payload["source_provenance_rows"]}
    assert {"koneps_turnkey_design_docs", "peer_tbi_tall_buildings", "midas_kds_geometry_bridge_validation"} <= set(rows_by_id)

    for row in rows_by_id.values():
        assert REQUIRED_ROW_FIELDS <= set(row)
        assert row["p0_upstream_hard_gate"] is True
        assert row["release_surface_allowed"] is False
        assert row["blocked_reason"]
        assert row["access_policy"]["redistribution_allowed"] is False
        assert row["access_policy"]["requires_manual_review"] is True
        assert {"source_file", "json_path"} <= set(row["row_pointer"])
        assert row["stable_row_pointer"]
        assert row["manual_review_status"]
        assert row["release_eligibility"]

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

    validation = rows_by_id["midas_kds_geometry_bridge_validation"]
    assert validation["official_url"] == "midas_kds_geometry_bridge_validation_report.json"
    assert validation["artifact_status"] == "exact_geometry_bridge_row_provenance_validation_evidence"
    assert validation["checksum_status_or_withheld_reason"] == "validation_report_only_no_raw_redistribution"
    assert validation["file_inventory_status"] == "midas_kds_geometry_bridge_validation_report.json"
    assert validation["parser_contract"]["source_file"] == "midas_kds_geometry_bridge_validation_report.json"
    assert validation["parser_contract"]["run_id"] == "phase1-validate-midas-kds-geometry-bridge-artifacts"
    assert validation["parser_contract"]["contract_pass"] is True
    assert validation["parser_contract"]["artifact_count"] == 3
    assert validation["parser_contract"]["exact_geometry_bridge_pass_count"] == 3
    assert validation["parser_contract"]["review_row_count_total"] == 3168
    assert validation["parser_contract"]["exact_mapped_row_provenance_count_total"] == 3168
    assert validation["parser_contract"]["full_member_crosswalk_count_total"] == 242
    assert validation["parser_contract"]["full_section_crosswalk_count_total"] == 200
    assert validation["parser_contract"]["full_load_crosswalk_count_total"] == 51
    assert validation["row_pointer"]["source_file"] == "midas_kds_geometry_bridge_validation_report.json"
    assert validation["stable_row_pointer"] == "midas_kds_geometry_bridge_validation_report.json:$.summary"

    measured_rows = [
        row for row in payload["source_provenance_rows"] if row["artifact_status"] == "measured_local_artifact_attached"
    ]
    assert len(measured_rows) == 10
    assert {row["parser_contract"]["format"] for row in measured_rows} == {"ifc", "mgt"}
    assert all(row["manual_review_status"] == "pending_artifact_level_review" for row in measured_rows)
    assert all(row["release_eligibility"] == "blocked_pending_artifact_review" for row in measured_rows)
    assert all(row["release_surface_allowed"] is False for row in measured_rows)
    assert all(row["checksum_status_or_withheld_reason"] for row in measured_rows)


def test_build_real_project_row_provenance_report_cli_falls_back_when_validation_report_missing(
    tmp_path: Path,
) -> None:
    out = tmp_path / "real_project_row_provenance_report.json"
    missing_validation_report = tmp_path / "missing_midas_kds_geometry_bridge_validation_report.json"

    proc = _run_cli(out, midas_kds_validation_report=missing_validation_report)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["row_count"] == 12
    assert payload["summary"]["measured_artifact_row_count"] == 10
    assert payload["summary"]["midas_kds_validation_present"] is False
    assert payload["summary"]["midas_kds_validation_artifact_count"] == 0
    assert payload["summary"]["midas_kds_exact_row_provenance_count"] == 0
    assert payload["summary"]["midas_kds_review_row_count"] == 0
    assert {"koneps_turnkey_design_docs", "peer_tbi_tall_buildings"} <= {
        row["source_id"] for row in payload["source_provenance_rows"]
    }


def test_build_real_project_row_provenance_report_is_deterministic(tmp_path: Path) -> None:
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    validation_report = _midas_kds_validation_report(tmp_path / "midas_kds_geometry_bridge_validation_report.json")

    proc_a = _run_cli(out_a, validation_report)
    proc_b = _run_cli(out_b, validation_report)

    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")
