#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_mgt_story_eccentricity_load_receipt import (  # noqa: E402
    build_mgt_story_eccentricity_load_receipt,
)


def test_mgt_story_eccentricity_load_receipt_generates_enabled_cases() -> None:
    payload = build_mgt_story_eccentricity_load_receipt()
    assert payload["schema_version"] == "mgt-story-eccentricity-load-receipt.v1"
    assert payload["status"] == "ready"
    assert payload["story_eccentricity"]["include_seismic_eccentricity"] is True
    assert payload["story_eccentricity"]["include_wind_eccentricity"] is False
    assert payload["summary"]["story_count"] >= 20
    assert payload["summary"]["generated_case_count"] == 4
    assert payload["summary"]["generated_seismic_case_count"] == 4
    assert payload["summary"]["generated_wind_case_count"] == 0
    assert payload["summary"]["max_abs_torsional_moment_nm"] > 0.0
    assert payload["summary"]["nodal_equivalent_entry_count"] > 0
    assert payload["support"]["typed_mgt_story_eccentricity_parser_ready"] is True
    assert payload["support"]["story_eccentricity_load_generation_ready"] is True
    assert payload["support"]["seismic_story_eccentricity_load_generation_ready"] is True
    assert payload["support"]["wind_story_eccentricity_disabled_by_source"] is True
    assert payload["support"]["global_solver_consumes_story_eccentricity_loads"] is False
    assert payload["generated_load_cases"][0]["family"] == "seismic_accidental_eccentricity"
    assert payload["generated_load_cases"][0]["total_abs_torsional_moment_nm"] > 0.0


def test_mgt_story_eccentricity_load_receipt_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_story_eccentricity_load_receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_story_eccentricity_load_receipt.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"]["provenance"] == "repo_benchmark_bridge"
    assert payload["summary"]["generated_case_count"] == 4
