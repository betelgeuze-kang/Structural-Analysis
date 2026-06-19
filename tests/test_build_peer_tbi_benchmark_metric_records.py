from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/build_peer_tbi_benchmark_metric_records.py"
SEED_MANIFEST = REPO_ROOT / "implementation/phase1/real_project_corpus_seed_manifest.json"
COVERAGE_MATRIX = REPO_ROOT / "implementation/phase1/real_project_parser_coverage_matrix.json"
REQUIRED_GROUPS = {"period", "base_shear", "story_drift", "nonlinear_response", "citation"}
REQUIRED_RECORD_FIELDS = {
    "source_id",
    "official_url",
    "citation",
    "report_id",
    "metric_group",
    "metric_name",
    "value",
    "status",
    "unit",
    "locator",
    "benchmark_status",
    "reference_truth_status",
    "redistribution_allowed",
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
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_peer_tbi_benchmark_metric_records_cli_contract(tmp_path: Path) -> None:
    out = tmp_path / "peer_tbi_benchmark_metric_records.json"

    proc = _run_cli(out)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert {
        "schema_version",
        "run_id",
        "source_manifest_schema_version",
        "source_id",
        "contract_pass",
        "reason_code",
        "raw_redistribution_default",
        "p0_upstream_hard_gate",
        "required_metric_groups",
        "summary",
        "metric_records",
        "p1_gate_rows",
    } <= set(payload)
    assert payload["schema_version"] == "peer_tbi_benchmark_metric_records.v1"
    assert payload["run_id"] == "phase1-peer-tbi-benchmark-metric-records"
    assert payload["source_id"] == "peer_tbi_tall_buildings"
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["raw_redistribution_default"] is False
    assert payload["p0_upstream_hard_gate"] is True
    assert set(payload["required_metric_groups"]) == REQUIRED_GROUPS
    assert payload["summary"]["required_metric_groups"] == sorted(REQUIRED_GROUPS)
    assert payload["summary"]["represented_metric_groups"] == sorted(REQUIRED_GROUPS)
    assert payload["summary"]["raw_redistribution_auto_allowed"] is False
    assert payload["summary"]["metric_record_count"] == len(REQUIRED_GROUPS)
    assert payload["summary"]["required_metric_group_count"] == len(REQUIRED_GROUPS)
    assert payload["summary"]["recorded_metric_group_count"] == len(REQUIRED_GROUPS)
    assert payload["summary"]["metric_groups_with_value"] == sorted(REQUIRED_GROUPS)
    assert payload["summary"]["metric_groups_with_value_count"] == len(REQUIRED_GROUPS)
    assert payload["summary"]["metric_groups_missing_value"] == []
    assert payload["summary"]["official_reference_truth_metric_groups"] == ["period"]
    assert payload["summary"]["measured_run_kpi_bridge_metric_groups"] == [
        "base_shear",
        "nonlinear_response",
        "story_drift",
    ]
    assert payload["summary"]["redistribution_allowed_record_count"] == 0
    assert payload["source_documents"]["peer_task12_report"]["sha256"]
    assert payload["source_documents"]["kpi_receipt"]["exists"] is True
    assert payload["source_documents"]["ndtha_stress_report"]["exists"] is True
    assert "third-party reference truth" in payload["claim_boundary"]

    records_by_group = {record["metric_group"]: record for record in payload["metric_records"]}
    assert set(records_by_group) == REQUIRED_GROUPS
    for group, record in records_by_group.items():
        assert REQUIRED_RECORD_FIELDS <= set(record)
        assert record["source_id"] == "peer_tbi_tall_buildings"
        assert record["official_url"] == "https://peer.berkeley.edu/research/building-systems/tall-buildings-initiative"
        assert record["citation"]
        assert record["report_id"] == "peer_tbi_tall_buildings_citation_seed"
        assert record["metric_name"]
        assert record["redistribution_allowed"] is False
        assert record["raw_model_redistribution_review_required"] is True
        assert record["value"] is not None
        assert {"page", "table", "figure", "note"} <= set(record["locator"])
        if group == "citation":
            assert record["status"] == "recorded"
            assert record["value"] == record["citation"]
            assert record["benchmark_status"] == "citation_metric_recorded"
            assert record["reference_truth_status"] == "citation_only_not_metric_truth"
            assert record["locator"]["note"] == "citation_seed:citation"
        elif group == "period":
            assert record["status"] == "official_report_value_recorded"
            assert record["value"] == 4.456
            assert record["benchmark_status"] == "official_public_report_metric_recorded"
            assert record["reference_truth_status"] == "official_public_report_metric"
            assert record["locator"]["table"] == "Table 4.1 Period and mass participation summary"
        else:
            assert record["benchmark_status"] == "measured_run_kpi_bridge_attached"
            assert record["reference_truth_status"] == "measured_run_kpi_bridge_not_external_reference_truth"
            assert isinstance(record["unit"], str)

    gates_by_id = {row["gate_id"]: row for row in payload["p1_gate_rows"]}
    assert gates_by_id["P1_PEER_TBI_BENCHMARK_METRICS"]["contract_pass"] is True
    assert gates_by_id["P1_RAW_REDISTRIBUTION_SAFETY"]["raw_redistribution_auto_allowed"] is False


def test_build_peer_tbi_benchmark_metric_records_is_deterministic(tmp_path: Path) -> None:
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"

    proc_a = _run_cli(out_a)
    proc_b = _run_cli(out_b)

    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")
