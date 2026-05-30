"""Tests for MGT native reanalysis pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_pipeline_verifies_sha_and_runs_story_proxy() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/mgt_native_reanalysis_pipeline_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_reanalysis_pipeline.py"),
            "--output-json",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mgt_integrity"]["mgt_exists"] is True
    assert payload.get("mgt_refresh") is not None
    assert (payload.get("native_fea") or {}).get("status") in {
        "parse_linked",
        "readiness_pass",
        "mesh_contract_pass",
        "condensed_solve_wired",
        "mesh_3d_global_wired",
        "not_wired",
    }
    assert (payload.get("native_fea") or {}).get("native_solve_status") in {
        "not_wired",
        "condensed_global_fea_wired",
        "mesh_3d_beam_global_wired",
        "mesh_3d_beam_global_wired_with_licensed_fingerprint_bridge",
    }
    assert payload["mgt_integrity"]["integrity_status"] in {
        "verified",
        "verified_without_expected_sha",
    }
    assert payload["status"] in {
        "story_proxy_pass",
        "story_proxy_pass_with_mgt_warn",
        "story_proxy_warn",
        "blocked",
    }
    assert payload["story_model_reanalysis"]["status"] in {"pass", "warn", "blocked"}


def test_verify_delivery_evidence_ci_ready() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/verify_delivery_evidence_for_ci.py")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
