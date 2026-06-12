"""Tests for MGT native reanalysis pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from verify_delivery_evidence_for_ci import build_gap_status_command  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_pipeline_verifies_sha_and_runs_story_proxy(tmp_path: Path) -> None:
    out = tmp_path / "mgt_native_reanalysis_pipeline_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_reanalysis_pipeline.py"),
            "--output-json",
            str(out),
            "--skip-global-solves",
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
        "mesh_3d_beam_global_wired_with_midas_live_ingest",
        "mesh_3d_beam_global_wired_with_midas_model_derived",
        "mesh_3d_beam_global_wired_with_midas_same_mesh_proxy",
    }
    assert (payload.get("native_fea") or {}).get("global_solves_skipped") is True
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


def test_verify_delivery_evidence_ci_ready(tmp_path: Path) -> None:
    bundle = tmp_path / "delivery_evidence_bundle.json"
    gap = tmp_path / "gap_closure_status.json"
    bundle.write_text(
        json.dumps(
            {"schema_version": "delivery-evidence-bundle.v1", "status": "ready", "blockers": []}
        )
        + "\n",
        encoding="utf-8",
    )
    gap.write_text(
        json.dumps({"schema_version": "gap-closure-status.v1", "delivery_status": "ready"}) + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/verify_delivery_evidence_for_ci.py"),
            "--check-existing",
            "--bundle-json",
            str(bundle),
            "--gap-json",
            str(gap),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_verify_delivery_evidence_ci_gap_command_uses_bundle_productization_dir(tmp_path: Path) -> None:
    bundle = tmp_path / "custom-productization" / "delivery_evidence_bundle.json"
    gap = tmp_path / "gap_closure_status.json"
    cmd = build_gap_status_command(gap_json=gap, productization_dir=bundle.parent)

    assert "--productization-dir" in cmd
    productization_index = cmd.index("--productization-dir") + 1
    output_index = cmd.index("--output-json") + 1
    assert cmd[productization_index] == str(bundle.parent)
    assert cmd[output_index] == str(gap)
