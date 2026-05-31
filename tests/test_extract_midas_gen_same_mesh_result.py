#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_extract_model_derived_real_quantities() -> None:
    out = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.model_derived_test.json"
    condensed = REPO_ROOT / "implementation/phase1/release_evidence/productization/mgt_global_fea_condensed_solve.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/extract_midas_gen_same_mesh_result.py"),
            "--condensed-solve-json",
            str(condensed),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"]["kind"] == "model_derived_estimate"
    assert payload["derivation"]["seismic_weight_kN"] > 1000.0
    assert payload["derivation"]["building_height_m"] > 0.0
    assert payload["metrics"]["base_shear_kN"] > 0.0
    assert payload["confidence"]["drift_ratio_pct"] == "medium"
    assert payload["metrics"]["drift_ratio_pct"] > 1.0
    assert "kds_seismic" in payload


def test_extract_validates_as_non_live() -> None:
    result = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.model_derived_test.json"
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
    # status pass (only the live-only soft check fails -> non-zero exit allowed)
    assert "midas-validate: pass" in proc.stdout
    assert "live_ready=False" in proc.stdout
