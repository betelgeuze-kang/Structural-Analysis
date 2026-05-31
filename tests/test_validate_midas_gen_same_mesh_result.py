#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_validate_live_example_fixture() -> None:
    result = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.live.example.json"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_midas_gen_same_mesh_result.py"),
            "--result-json",
            str(result),
            "--roundtrip-json",
            str(roundtrip),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "live_ready=True" in proc.stdout


def test_csv_convert_to_live_result() -> None:
    csv_path = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_summary.example.csv"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    out = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result_converted_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/convert_midas_gen_table_export_to_result.py"),
            "--csv",
            str(csv_path),
            "--roundtrip-json",
            str(roundtrip),
            "--output-json",
            str(out),
            "--kind",
            "midas_gen_live_export",
            "--load-case",
            "COMB1",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"]["kind"] == "midas_gen_live_export"
    assert payload["metrics"]["drift_ratio_pct"] == 1.92


def test_live_example_comparison_status() -> None:
    result = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.live.example.json"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/midas_gen_same_mesh_native_comparison_live_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_midas_gen_same_mesh_native_comparison.py"),
            "--result-json",
            str(result),
            "--roundtrip-json",
            str(roundtrip),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["comparison_status"] == "pass_live_ingest_native_metrics_diverge"
    assert payload["ingest"]["source"]["live_midas_gen_export"] is True
