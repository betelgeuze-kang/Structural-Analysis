"""Tests for the load/stage runtime-flow receipt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_stage_runtime_flow_receipt_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "load_stage_runtime_flow_receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_load_stage_runtime_flow_receipt.py"),
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
    assert payload["schema_version"] == "load-stage-runtime-flow-receipt.v1"
    assert payload["status"] == "ready"
    assert payload["typed_load_stage_flow_ready"] is True
    assert payload["solve_flow_ready"] is True
    assert payload["viewer_flow_ready"] is True
    assert payload["export_flow_ready"] is True
    assert payload["audit_flow_ready"] is True
    assert payload["unsupported_hazard_queue_ready"] is True
    assert payload["summary"]["solve_flow_basis"] in {
        "legacy_native_and_condensed",
        "current_full_sparse_line_frame_coupled_evidence",
    }
    solver_evidence = payload["flow_contract"]["solve"]["solver_evidence"]
    assert solver_evidence["ready"] is True
    assert solver_evidence["full_line_sparse_ready"] is True
    assert solver_evidence["full_frame_6dof_sparse_ready"] is True
    assert solver_evidence["coupled_frame_shell_sparse_ready"] is True
    assert payload["load_family_inventory"]["has_dead"] is True
    assert payload["load_family_inventory"]["has_live"] is True
    assert payload["load_family_inventory"]["has_wind"] is True
    assert payload["unsupported_hazard_queue"]
