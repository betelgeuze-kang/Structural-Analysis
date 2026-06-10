"""Tests for material/element tangent support matrix evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_material_element_tangent_support_matrix_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "material_element_tangent_support_matrix.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_material_element_tangent_support_matrix.py"),
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
    assert payload["schema_version"] == "material-element-tangent-support-matrix.v1"
    assert payload["status"] == "ready"
    assert payload["line_beam_tangent_ready"] is True
    assert payload["unsupported_queue_ready"] is True
    support_rows = {row["family"]: row for row in payload["support_matrix"]}
    assert support_rows["line_beam_column_code1"]["status"] == "tangent_coupled"
    assert support_rows["line_beam_column_code1"]["section_material_coverage_pct"] >= 95.0
    assert support_rows["line_beam_column_code1"]["frame_local_axis_roll_transform_ready"] is True
    assert support_rows["line_beam_column_code1"]["frame_local_axis_nonzero_angle_count"] == 150
    assert support_rows["plate_shell_surface_code2"]["status"] in {
        "parsed_exported_not_tangent_coupled",
        "membrane_tangent_smoke_solved_bending_drilling_unsupported",
        "membrane_bending_drilling_smoke_solved_source_thickness_unsupported",
        "membrane_bending_drilling_smoke_solved_source_thickness_promoted_full_benchmark_unsupported",
        "membrane_bending_drilling_calibrated_benchmark_ready_opening_local_axis_unsupported",
    }
    if support_rows["plate_shell_surface_code2"]["status"] != "parsed_exported_not_tangent_coupled":
        assert support_rows["plate_shell_surface_code2"]["surface_membrane_tangent_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["surface_shell_full_bending_tangent_ready"] is False
    if support_rows["plate_shell_surface_code2"]["status"] in {
        "membrane_bending_drilling_smoke_solved_source_thickness_unsupported",
        "membrane_bending_drilling_smoke_solved_source_thickness_promoted_full_benchmark_unsupported",
        "membrane_bending_drilling_calibrated_benchmark_ready_opening_local_axis_unsupported",
    }:
        assert support_rows["plate_shell_surface_code2"]["surface_shell_bending_drilling_smoke_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["surface_shell_transverse_pressure_smoke_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["surface_shell_coupled_sparse_equilibrium_ready"] is True
    if (
        support_rows["plate_shell_surface_code2"]["status"]
        == "membrane_bending_drilling_smoke_solved_source_thickness_promoted_full_benchmark_unsupported"
        or support_rows["plate_shell_surface_code2"]["status"]
        == "membrane_bending_drilling_calibrated_benchmark_ready_opening_local_axis_unsupported"
    ):
        assert support_rows["plate_shell_surface_code2"]["section_law"] == "source_mgt_thickness_rows_by_plate_section_id"
        assert support_rows["plate_shell_surface_code2"]["source_plate_thickness_coverage_pct"] == 100.0
    if (
        support_rows["plate_shell_surface_code2"]["status"]
        == "membrane_bending_drilling_calibrated_benchmark_ready_opening_local_axis_unsupported"
    ):
        assert support_rows["plate_shell_surface_code2"]["surface_shell_calibration_benchmarks_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["shell_calibration_ready_case_count"] >= 5
        assert support_rows["plate_shell_surface_code2"]["surface_lcaxis_parser_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["surface_lcaxis_source_all_default"] is True
        assert support_rows["plate_shell_surface_code2"]["opening_runtime_semantics_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["current_source_opening_noop_runtime_ready"] is True
        assert support_rows["plate_shell_surface_code2"]["generic_opening_cutout_runtime_semantics_ready"] is False
    nonlinear = support_rows["nonlinear_rc_steel_composite_material_laws"]
    assert nonlinear["status"] == "bounded_frame_material_nonlinear_tangent_smoke_ready_full_newton_unsupported"
    assert nonlinear["frame_material_nonlinear_tangent_ready"] is True
    assert nonlinear["bounded_material_tangent_global_smoke_ready"] is True
    assert nonlinear["controlled_probe_material_state_summary"]["nonlinear_tangent_element_count"] > 0
    assert payload["unsupported_element_material_queue"]
