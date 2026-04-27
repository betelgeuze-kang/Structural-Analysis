from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/generate_real_project_parser_coverage_matrix.py"
SEED_MANIFEST = REPO_ROOT / "implementation/phase1/real_project_corpus_seed_manifest.json"


def test_generate_real_project_parser_coverage_matrix_cli(tmp_path: Path) -> None:
    out = tmp_path / "real_project_parser_coverage_matrix.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(SEED_MANIFEST),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert set(payload) >= {"summary", "source_rows", "p1_gate_rows"}
    assert payload["summary"]["source_family_count"] == 2
    assert payload["summary"]["p0_provenance_required_count"] == 2
    assert payload["summary"]["raw_redistribution_auto_allowed_after_p0"] is False

    rows_by_id = {row["source_id"]: row for row in payload["source_rows"]}
    koneps = rows_by_id["koneps_turnkey_design_docs"]
    assert koneps["priority_phase"] == "P0"
    assert koneps["p0_provenance_required"] is True
    assert koneps["redistribution_allowed"] is False
    assert koneps["manual_review_required"] is True
    assert [target["file_type"] for target in koneps["parser_coverage_targets"]] == [
        ".mgt",
        ".ifc",
        ".dwg",
        ".dxf",
        ".pdf",
        ".xlsx",
        ".zip",
    ]
    assert {target["coverage_status"] for target in koneps["parser_coverage_targets"]} == {"planned"}

    peer_tbi = rows_by_id["peer_tbi_tall_buildings"]
    assert peer_tbi["priority_phase"] == "P0"
    assert peer_tbi["p0_provenance_required"] is True
    assert peer_tbi["redistribution_allowed"] is False
    assert peer_tbi["manual_review_required"] is True
    assert [target["metric"] for target in peer_tbi["benchmark_metric_targets"]] == [
        "period",
        "base_shear",
        "story_drift",
        "nonlinear_response",
        "citation",
    ]

    gate_rows_by_id = {row["gate_id"]: row for row in payload["p1_gate_rows"]}
    assert gate_rows_by_id["P1_RAW_REDISTRIBUTION_SAFETY"]["raw_redistribution_auto_allowed_after_p0"] is False
    assert gate_rows_by_id["P1_RAW_REDISTRIBUTION_SAFETY"]["coverage_status"] == "planned"


def test_generate_real_project_parser_coverage_matrix_is_deterministic(tmp_path: Path) -> None:
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--manifest",
        str(SEED_MANIFEST),
    ]

    proc_a = subprocess.run(cmd + ["--out", str(out_a)], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    proc_b = subprocess.run(cmd + ["--out", str(out_b)], cwd=REPO_ROOT, capture_output=True, text=True, check=False)

    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")
