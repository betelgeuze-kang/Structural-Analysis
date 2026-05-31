#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_midas_same_mesh_proxy_and_comparison() -> None:
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    crossval = REPO_ROOT / "implementation/phase1/release_evidence/productization/commercial_solver_cross_validation.json"
    result_out = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result_test.json"
    compare_out = (
        REPO_ROOT / "implementation/phase1/release_evidence/productization/midas_gen_same_mesh_native_comparison_test.json"
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_midas_gen_same_mesh_result_proxy.py"),
            "--roundtrip-json",
            str(roundtrip),
            "--commercial-crossval-json",
            str(crossval),
            "--output-json",
            str(result_out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    result_payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert result_payload["metrics"]["drift_ratio_pct"] > 0

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_midas_gen_same_mesh_native_comparison.py"),
            "--result-json",
            str(result_out),
            "--roundtrip-json",
            str(roundtrip),
            "--output-json",
            str(compare_out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(compare_out.read_text(encoding="utf-8"))
    assert str(payload.get("comparison_status") or "").startswith("pass")
    assert payload["ingest"]["source"]["kind"] == "midas_gen_export_proxy"
