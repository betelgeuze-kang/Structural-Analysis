"""Shared Phase 3 benchmark reproduction contract paths."""

from __future__ import annotations

from pathlib import Path


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")

GIT_CLEAN_CLONE_REQUIRED_INPUTS = [
    Path("package.json"),
    Path("pyproject.toml"),
    Path("pytest.ini"),
    Path("setup.cfg"),
    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl"),
    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl"),
    Path("implementation/phase1/opensees_topology_report.json"),
    Path("implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"),
    Path("implementation/phase1/report_commercial_solver_cross_validation.py"),
    PRODUCTIZATION / "commercial_solver_cross_validation.json",
    Path("src/structural_analysis"),
    Path("scripts/build_phase3_benchmark_acquisition_artifacts.py"),
    Path("scripts/build_phase3_benchmark_factory_artifacts.py"),
    Path("scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
    Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
    Path("scripts/build_phase3_ifc_source_license_receipt.py"),
    Path("scripts/build_phase3_ifc_import_health_execution_receipt.py"),
    Path("scripts/build_phase3_ifc_query_gui_readiness_receipt.py"),
    Path("scripts/build_phase3_medium_model_scorecard_readiness_receipt.py"),
    Path("scripts/build_phase3_large_model_runner_readiness_receipt.py"),
    Path("scripts/build_phase3_opensees_source_license_receipt.py"),
    Path("scripts/build_phase4_commercial_comparison_import_template.py"),
    Path("scripts/build_phase4_commercial_cross_solver_readiness_receipt.py"),
    Path("scripts/build_phase4_analytic_physical_fallback_scorecard.py"),
    Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
    Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
    Path("scripts/phase3_benchmark_reproduction_contract.py"),
    Path("scripts/release_evidence_metadata.py"),
    Path("scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py"),
    Path("scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py"),
    Path("src/structure-viewer/viewer-commercial-tool-crosswalk-model.js"),
    Path("src/structure-viewer/viewer-report-export.js"),
    Path("tests/test_build_phase3_benchmark_factory_artifacts.py"),
    Path("tests/test_build_phase3_benchmark_acquisition_artifacts.py"),
    Path("tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
    Path("tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
    Path("tests/test_build_phase3_ifc_source_license_receipt.py"),
    Path("tests/test_build_phase3_ifc_import_health_execution_receipt.py"),
    Path("tests/test_build_phase3_opensees_source_license_receipt.py"),
    Path("tests/test_build_phase4_commercial_comparison_import_template.py"),
    Path("tests/test_build_phase4_analytic_physical_fallback_scorecard.py"),
    Path("tests/test_build_phase4_commercial_operator_reference_contract.py"),
    Path("tests/test_build_phase4_commercial_operator_reference_ingest_validator.py"),
    Path("tests/test_structure_viewer_commercial_tool_crosswalk_model_contract.py"),
    Path("tests/test_structure_viewer_explainability_report_contract.py"),
    Path("tests/test_structural_analysis_benchmark_cli.py"),
    Path("tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py"),
    Path("tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py"),
    PRODUCTIZATION / "phase3_benchmark_factory_seed_manifest.json",
    PRODUCTIZATION / "phase3_benchmark_factory_seed_scorecard.json",
    PRODUCTIZATION / "phase3_benchmark_factory_seed_summary.json",
    PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json",
    PRODUCTIZATION / "phase3_benchmark_factory_seed_clean_checkout_reproduction.json",
    PRODUCTIZATION / "phase3_benchmark_acquisition_plan.json",
    PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json",
    PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json",
    PRODUCTIZATION / "phase3_ifc_source_license_receipt.json",
    PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json",
    PRODUCTIZATION / "phase3_opensees_medium_source_license_receipt.json",
    PRODUCTIZATION / "phase4_commercial_comparison_import_template.json",
    PRODUCTIZATION / "phase4_analytic_physical_fallback_scorecard.json",
    PRODUCTIZATION / "phase4_commercial_operator_reference_contract.json",
    PRODUCTIZATION / "phase4_commercial_operator_reference_ingest_validator.json",
]


def path_strings(paths: list[Path]) -> list[str]:
    return [path.as_posix() for path in sorted(paths, key=lambda item: item.as_posix())]
