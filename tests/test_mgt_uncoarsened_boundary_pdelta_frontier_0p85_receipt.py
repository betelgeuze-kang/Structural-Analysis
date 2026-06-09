from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_mgt_uncoarsened_boundary_pdelta_frontier_0p85_receipt.py"
SEGMENT_DIR = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_uncoarsened_boundary_pdelta_checkpoint_segments"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_uncoarsened_boundary_pdelta_frontier_0p85_receipt.json"
)


def test_frontier_0p85_receipt_default_runs() -> None:
    out = DEFAULT_OUT
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-json", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "mgt-uncoarsened-boundary-pdelta-frontier-0p85-receipt.v1"
    assert payload["target_load_scale"] == 0.85
    assert payload["summary"]["segment_count"] >= 50
    assert payload["frontier_load_scale"] >= 0.4
    assert payload["frontier_load_scale"] < 0.85 or payload["frontier_0p85_reached"]
    assert "rule_family_breakdown" in payload["summary"]
    assert "next_action" in payload["frontier_diagnostic"]
    assert "blockers" in payload
    assert "claim_boundary" in payload


def test_frontier_0p85_receipt_segment_dir_uses_real_segments() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-json", str(DEFAULT_OUT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(DEFAULT_OUT.read_text(encoding="utf-8"))
    assert payload["source"]["segment_count"] >= 50
    assert "strength" in payload["summary"]["rule_family_breakdown"]


def test_frontier_0p85_receipt_target_synthetic() -> None:
    """Synthesize a tiny segment directory and verify the receipt aggregates correctly."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        seg_dir = tmp_path / "segments"
        seg_dir.mkdir()
        for idx, (load_scale, ready) in enumerate(
            [(0.5, True), (0.55, True), (0.6, True), (0.7, True), (0.8, True)]
        ):
            seg = {
                "schema_version": "mgt-uncoarsened-boundary-pdelta-probe.v1",
                "status": "partial" if not ready else "partial",
                "max_converged_load_scale": load_scale,
                "first_failed_load_scale": None,
                "step_results": [
                    {
                        "load_scale": load_scale,
                        "ready": ready,
                        "converged": ready,
                        "residual_tolerance_n": 5.0e-4,
                        "relative_increment_tolerance": 1.0e-4,
                        "best_residual_inf_n": 1.0e-4,
                        "best_fixed_point_relative_increment": 5.0e-5,
                    }
                ],
            }
            (seg_dir / f"segment_{idx:03d}.json").write_text(json.dumps(seg), encoding="utf-8")
        out = tmp_path / "receipt.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--segment-dir",
                str(seg_dir),
                "--output-json",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["frontier_load_scale"] == 0.8
        assert payload["summary"]["segment_count"] == 5
        assert payload["summary"]["accepted_step_count"] == 5
        assert payload["frontier_0p85_reached"] is False
        assert payload["blockers"] == ["frontier_below_target:0.800000_of_0.85"]


def test_frontier_0p85_receipt_target_reached() -> None:
    """Synthesize a synthetic run that reaches 0.85."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        seg_dir = tmp_path / "segments"
        seg_dir.mkdir()
        for idx, (load_scale, ready) in enumerate(
            [(0.6, True), (0.7, True), (0.85, True), (0.9, True)]
        ):
            seg = {
                "schema_version": "mgt-uncoarsened-boundary-pdelta-probe.v1",
                "status": "partial",
                "max_converged_load_scale": load_scale,
                "first_failed_load_scale": None,
                "step_results": [
                    {
                        "load_scale": load_scale,
                        "ready": ready,
                        "converged": ready,
                        "residual_tolerance_n": 5.0e-4,
                        "relative_increment_tolerance": 1.0e-4,
                        "best_residual_inf_n": 1.0e-4,
                        "best_fixed_point_relative_increment": 5.0e-5,
                    }
                ],
            }
            (seg_dir / f"segment_{idx:03d}.json").write_text(json.dumps(seg), encoding="utf-8")
        out = tmp_path / "receipt.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--segment-dir",
                str(seg_dir),
                "--target-load-scale",
                "0.85",
                "--output-json",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["frontier_load_scale"] == 0.9
        assert payload["frontier_0p85_reached"] is True
        assert payload["status"] == "ready"
        assert payload["blockers"] == []
