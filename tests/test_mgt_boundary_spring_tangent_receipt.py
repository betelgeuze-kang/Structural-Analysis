#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_mgt_boundary_spring_tangent_receipt import (  # noqa: E402
    build_mgt_boundary_spring_tangent_receipt,
)


def test_mgt_boundary_spring_tangent_receipt_assembles_real_links_and_masks() -> None:
    payload = build_mgt_boundary_spring_tangent_receipt()
    assert payload["schema_version"] == "mgt-boundary-spring-tangent-receipt.v1"
    assert payload["status"] == "ready"
    assert payload["summary"]["support_node_count"] == 2133
    assert payload["summary"]["elastic_link_node_count"] == 3384
    assert payload["summary"]["direct_support_link_node_intersection_count"] == 0
    assert payload["summary"]["finite_spring_component_count"] == 1692 * 6
    assert payload["summary"]["authored_support_restrained_dof_count"] == 7707
    assert payload["summary"]["tangent_nnz"] == 1692 * 6 * 4
    assert payload["support"]["authored_support_mask_application_ready"] is True
    assert payload["support"]["finite_elastic_link_spring_tangent_ready"] is True
    assert payload["support"]["boundary_subsystem_probe_solve_ready"] is True
    assert payload["support"]["solver_uses_authored_support_restraint_masks"] is True
    assert payload["support"]["solver_assembles_finite_elastic_link_springs"] is True
    assert payload["support"]["global_frame_shell_tangent_integration_ready"] is False
    assert payload["probe_solve"]["relative_residual_inf"] <= 1.0e-8


def test_mgt_boundary_spring_tangent_receipt_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_boundary_spring_tangent_receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_boundary_spring_tangent_receipt.py"),
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
    assert payload["summary"]["finite_spring_component_count"] == 10152
