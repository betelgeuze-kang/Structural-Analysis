#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_mgt_boundary_entity_support_receipt import (  # noqa: E402
    build_mgt_boundary_entity_support_receipt,
)


def test_mgt_boundary_entity_receipt_is_honest_about_parser_and_solver_boundary() -> None:
    payload = build_mgt_boundary_entity_support_receipt()
    assert payload["schema_version"] == "mgt-boundary-entity-support-receipt.v1"
    assert payload["status"] == "partial"
    assert payload["summary"]["support_constraint_row_count"] == 8
    assert payload["summary"]["distinct_support_constraint_node_count"] == 2133
    assert payload["summary"]["unmatched_support_constraint_node_count"] == 0
    assert payload["summary"]["restraint_code_counts"]["111000"] == 1
    assert payload["summary"]["restraint_code_counts"]["111111"] == 7
    assert payload["summary"]["elastic_link_row_count"] == 1692
    assert payload["summary"]["elastic_link_type_counts"]["GEN"] == 1692
    assert payload["summary"]["unmatched_elastic_link_node_count"] == 0
    assert payload["summary"]["story_eccentricity_present"] is True
    assert payload["support"]["canonical_support_constraint_entity_ready"] is True
    assert payload["support"]["canonical_elastic_link_entity_ready"] is True
    assert payload["support"]["roundtrip_constraint_summary_ready"] is True
    assert payload["support"]["roundtrip_rigid_like_elastic_link_coarsening_ready"] is True
    assert payload["support"]["solver_uses_authored_support_restraint_masks"] is False
    assert payload["support"]["solver_assembles_finite_elastic_link_springs"] is False
    assert payload["support"]["solver_applies_story_eccentricity_load_generation"] is False


def test_mgt_boundary_entity_receipt_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_boundary_entity_support_receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_boundary_entity_support_receipt.py"),
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
    assert payload["summary"]["elastic_link_row_count"] == 1692
