"""Tests for GPU Newton certification honesty checklist."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_state_npz(tmp_path: Path) -> Path:
    state_npz = tmp_path / "solver_state.npz"
    np.savez_compressed(
        state_npz,
        group_ids=np.asarray(["G0"], dtype="<U8"),
        rebar_ratio=np.asarray([0.012], dtype=np.float64),
        thickness_scale=np.asarray([1.0], dtype=np.float64),
        detailing_quality=np.asarray([0.88], dtype=np.float64),
        max_dcr=np.asarray([0.98], dtype=np.float64),
        congestion=np.asarray([0.20], dtype=np.float64),
        lap_splice=np.asarray([0.10], dtype=np.float64),
        anchorage=np.asarray([0.25], dtype=np.float64),
        detailing=np.asarray([0.30], dtype=np.float64),
        robustness_margin=np.asarray([0.22], dtype=np.float64),
        multi_hazard_margin=np.asarray([0.24], dtype=np.float64),
        group_cost_proxy=np.asarray([1200.0], dtype=np.float64),
        member_type=np.asarray(["column"], dtype="<U16"),
        zone_label=np.asarray(["transfer"], dtype="<U16"),
        semantic_group=np.asarray(["G-T1"], dtype="<U16"),
        story_band=np.asarray([0], dtype=np.int32),
        repair_influence=np.asarray([1.35], dtype=np.float64),
        combination_match_score=np.asarray([0.82], dtype=np.float64),
        combination_risk=np.asarray([1.18], dtype=np.float64),
        global_drift_pct=np.asarray([1.0], dtype=np.float64),
        global_residual_drift_pct=np.asarray([0.1], dtype=np.float64),
        action_mask=np.asarray([[True, True]], dtype=np.bool_),
    )
    return state_npz


def test_gpu_newton_checklist_without_terminal_artifact(tmp_path: Path) -> None:
    out = tmp_path / "gpu_newton_certification_checklist.json"
    missing_cert = tmp_path / "gpu_newton_terminal_certification_missing.json"
    state_npz = _write_state_npz(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"),
            "--state-npz",
            str(state_npz),
            "--output-json",
            str(out),
            "--terminal-certification-json",
            str(missing_cert),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "not_certified"
    assert payload["gpu_newton_terminal_proven"] is False
    assert "gpu_newton_terminal_not_proven" in (payload.get("certification_blockers") or [])
    assert len(payload["required_evidence_before_terminal_claim"]) >= 3


def test_gpu_newton_checklist_with_terminal_artifact_when_present(
    tmp_path: Path,
) -> None:
    cert = REPO_ROOT / "implementation/phase1/release_evidence/productization/gpu_newton_terminal_certification.json"
    if not cert.is_file():
        return
    out = tmp_path / "gpu_newton_certification_checklist_from_cert.json"
    state_npz = _write_state_npz(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"),
            "--state-npz",
            str(state_npz),
            "--output-json",
            str(out),
            "--terminal-certification-json",
            str(cert),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    cert_payload = json.loads(cert.read_text(encoding="utf-8"))
    if cert_payload.get("gpu_newton_terminal_proven"):
        assert payload["status"] == "certified"
        assert payload["gpu_newton_terminal_proven"] is True
    else:
        assert payload["status"] == "not_certified"
