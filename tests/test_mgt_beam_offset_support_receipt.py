#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_mgt_beam_offset_support_receipt import build_mgt_beam_offset_support_receipt  # noqa: E402


def test_mgt_beam_offset_receipt_is_honest_about_parser_and_solver_boundary() -> None:
    payload = build_mgt_beam_offset_support_receipt()
    assert payload["schema_version"] == "mgt-beam-offset-support-receipt.v1"
    assert payload["status"] == "partial"
    assert payload["summary"]["offset_row_count"] >= 700
    assert payload["summary"]["distinct_offset_element_count"] == payload["summary"]["offset_element_ref_count"]
    assert payload["summary"]["unmatched_offset_element_count"] == 0
    assert payload["summary"]["coordinate_system_counts"]["GLOBAL"] >= 700
    assert payload["summary"]["max_abs_offset_m"] >= 0.5
    assert payload["support"]["typed_mgt_offset_parser_ready"] is True
    assert payload["support"]["canonical_runtime_entity_ready"] is True
    assert payload["support"]["solver_rigid_end_offset_tangent_ready"] is True
    assert payload["support"]["solver_geometric_stiffness_offset_ready"] is True
    assert payload["support"]["frame_offset_applied_element_count"] >= 700
    assert payload["support"]["roundtrip_preserves_offset_metadata"] is False


def test_mgt_beam_offset_receipt_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_beam_offset_support_receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_beam_offset_support_receipt.py"),
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
    assert payload["summary"]["offset_row_count"] >= 700
    assert payload["source"]["provenance"] == "repo_benchmark_bridge"
