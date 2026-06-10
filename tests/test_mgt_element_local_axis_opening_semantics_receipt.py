"""Tests for MGT element local-axis/opening semantics receipt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_element_local_axis_opening_receipt_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_element_local_axis_opening_semantics_receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_element_local_axis_opening_semantics_receipt.py"),
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
    assert payload["schema_version"] == "mgt-element-local-axis-opening-semantics-receipt.v1"
    assert payload["status"] == "ready"
    assert payload["source"]["provenance"] == "repo_benchmark_bridge"
    assert payload["summary"]["line_local_axis_row_count"] >= 5500
    assert payload["summary"]["line_nonzero_angle_row_count"] == 150
    assert payload["summary"]["surface_lcaxis_row_count"] == 7152
    assert payload["support"]["frame_angle_parser_ready"] is True
    assert payload["support"]["frame_angle_source_has_nonzero_rows"] is True
    assert payload["support"]["frame_angle_solver_consumption_ready"] is True
    assert payload["support"]["surface_lcaxis_parser_ready"] is True
    assert payload["support"]["surface_lcaxis_source_all_default"] is True
    assert payload["support"]["opening_source_inventory_ready"] is True
    assert payload["support"]["opening_source_rows_present"] is False
    assert payload["support"]["current_source_opening_absence_policy_ready"] is True
    assert payload["support"]["current_source_opening_noop_runtime_ready"] is True
    assert payload["support"]["opening_runtime_semantics_ready"] is True
    assert payload["support"]["generic_opening_cutout_runtime_semantics_ready"] is False
