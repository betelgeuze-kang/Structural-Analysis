from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STRUCTURE_VIEWER_CONTRACT_TESTS = [
    "tests/test_structure_viewer_instancing_contract.py",
    "tests/test_structure_viewer_data_loader_contract.py",
    "tests/test_structure_viewer_model_normalizer_contract.py",
    "tests/test_structure_viewer_direct_model_normalizer_contract.py",
    "tests/test_structure_viewer_contour_materials_contract.py",
    "tests/test_structure_viewer_render_mesh_builders_contract.py",
    "tests/test_structure_viewer_render_picking_geometry_contract.py",
    "tests/test_structure_viewer_large_model_picking_contract.py",
    "tests/test_structure_viewer_pick_broadphase_contract.py",
    "tests/test_build_structure_viewer_performance_budget_manifest.py",
    "tests/test_structure_viewer_browser_performance_probe_contract.py",
    "tests/test_structure_viewer_visual_regression_contract.py",
    "tests/test_structure_viewer_deformed_rendering_contract.py",
    "tests/test_structure_viewer_offline_vendor_contract.py",
    "tests/test_structure_viewer_local_vendor_contract.py",
    "tests/test_structure_viewer_suite_shell_contract.py",
    "tests/test_structure_viewer_real_drawing_browser_state_contract.py",
    "tests/test_structure_viewer_real_drawing_panel_events_contract.py",
    "tests/test_structure_viewer_real_drawing_panel_model_contract.py",
    "tests/test_structure_viewer_real_drawing_panel_renderer_contract.py",
    "tests/test_structure_viewer_real_drawing_quality_contract.py",
    "tests/test_structure_viewer_real_drawing_selection_contract.py",
    "tests/test_structure_viewer_real_drawing_tree_model_contract.py",
    "tests/test_structure_viewer_search_results_model_contract.py",
    "tests/test_structure_viewer_selection_summary_model_contract.py",
    "tests/test_structure_viewer_provenance_model_contract.py",
    "tests/test_structure_viewer_side_panel_model_contract.py",
    "tests/test_structure_viewer_shared_selection_state_contract.py",
    "tests/test_structure_viewer_stats_summary_contract.py",
    "tests/test_structure_viewer_analysis_cockpit_model_contract.py",
    "tests/test_structure_viewer_project_workspace_contract.py",
    "tests/test_structure_viewer_project_manifest_verifier.py",
    "tests/test_structure_viewer_optimization_comparison_model_contract.py",
    "tests/test_structure_viewer_member_comparison_model_contract.py",
    "tests/test_structure_viewer_commercial_tool_crosswalk_model_contract.py",
    "tests/test_structure_viewer_review_task_model_contract.py",
    "tests/test_structure_viewer_solver_receipt_model_contract.py",
    "tests/test_structure_viewer_evidence_ingest_model_contract.py",
    "tests/test_structure_viewer_lineage_drilldown_model_contract.py",
    "tests/test_structure_viewer_drawing_sheet_package_contract.py",
    "tests/test_structure_viewer_explainability_report_contract.py",
    "tests/test_structure_viewer_pdf_export_contract.py",
    "tests/test_structure_viewer_local_ops_state_contract.py",
    "tests/test_viewer_shared_selection_contract.py",
    "tests/test_generate_selfcontained_viewer.py",
    "tests/test_structure_viewer_singlefile_offline_contract.py",
]


def build_pytest_command(extra_pytest_args: list[str] | None = None) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *STRUCTURE_VIEWER_CONTRACT_TESTS,
        *(extra_pytest_args or []),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the structure viewer contract suite.")
    parser.add_argument("--dry-run", action="store_true", help="Print the pytest command without executing it.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Optional arguments passed through after `--`.")
    args = parser.parse_args(argv)

    passthrough_args = args.pytest_args
    if passthrough_args and passthrough_args[0] == "--":
        passthrough_args = passthrough_args[1:]

    command = build_pytest_command(passthrough_args)
    print(" ".join(command))
    if args.dry_run:
        return 0
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
