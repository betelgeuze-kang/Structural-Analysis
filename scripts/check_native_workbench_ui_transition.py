#!/usr/bin/env python3
"""Fail closed on React/TypeScript Workbench inventory and C6 removal readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("native/decommission/workbench-ui-transition-v1.json")
REQUIRED_PATHS = (
    MANIFEST,
    Path("native/capabilities.json"),
    Path("native/crates/structural-workbench/src/lib.rs"),
    Path("native/crates/structural-workbench/src/main.rs"),
    Path("native/crates/structural-workbench/src/analysis_request.rs"),
    Path("native/crates/structural-workbench/src/model_edit.rs"),
    Path("native/crates/structural-workbench/src/deformed_view.rs"),
    Path("native/crates/structural-workbench/src/model_view.rs"),
    Path("native/crates/structural-workbench/src/report_view.rs"),
    Path("native/crates/structural-workbench/src/result_view.rs"),
    Path("native/crates/structural-workbench/tests/native_workbench_e2e.rs"),
    Path("native/crates/structural-catalog/src/lib.rs"),
    Path("native/crates/structural-catalog/tests/catalog_builder_product.rs"),
    Path("native/crates/structural-frontend-contract/src/lib.rs"),
    Path("native/crates/structural-frontend-contract/src/browser_smoke.rs"),
    Path("native/crates/structural-frontend-contract/src/frontend_audit.rs"),
    Path("native/crates/structural-frontend-contract/src/frontend_audit_report.rs"),
    Path("native/crates/structural-frontend-contract/src/frontend_build.rs"),
    Path("native/crates/structural-frontend-contract/src/frontend_dev.rs"),
    Path("native/crates/structural-frontend-contract/src/frontend_install.rs"),
    Path("native/crates/structural-frontend-contract/src/frontend_preview.rs"),
    Path("native/crates/structural-frontend-contract/src/phase5_task_browser_smoke.rs"),
    Path("native/crates/structural-frontend-contract/src/playwright.rs"),
    Path("native/crates/structural-frontend-contract/src/playwright_install.rs"),
    Path("native/crates/structural-frontend-contract/src/prototype.rs"),
    Path("native/crates/structural-frontend-contract/src/prototype_browser_smoke.rs"),
    Path("native/crates/structural-frontend-contract/src/smoke.rs"),
    Path("native/crates/structural-frontend-contract/src/verified_publication.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_js_syntax.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_manifest.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_performance_probe.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_readme_capture.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_report_pdf_export.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_report_pdf_smoke.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_sample_workflow.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_server.rs"),
    Path("native/crates/structural-frontend-contract/src/viewer_visual_regression.rs"),
    Path("native/crates/structural-frontend-contract/src/workbench_v2_browser_smoke.rs"),
    Path("native/crates/structural-frontend-contract/tests/frontend_contract_product.rs"),
    Path("native/crates/structural-evidence/src/lib.rs"),
    Path("native/crates/structural-evidence/tests/evidence_bundle_product.rs"),
    Path("native/catalog/benchmark-catalog-v2.json"),
    Path("native/catalog/benchmark-catalog-sources-v1.json"),
    Path("native/decommission/legacy-frontend-build-contract-v1.json"),
    Path("src/structure-viewer/viewer-project-manifest.v1.json"),
    Path("src/structure-viewer/viewer-project-manifest-data.js"),
    Path("prototype/structural-workbench/app.js"),
    Path("prototype/structural-workbench/demo-case.json"),
    Path("prototype/structural-workbench/index.html"),
    Path("scripts/export-structure-viewer-report-pdf.mjs"),
    Path("scripts/measure-structure-viewer-visual-regression.mjs"),
    Path("scripts/run_phase5_task_based_ux_browser_smoke.py"),
    Path("scripts/build_frontend_dependency_audit_report.py"),
    Path("scripts/verify-structure-viewer-sample-workflow.mjs"),
    Path("scripts/verify_quality_gate.py"),
    Path("implementation/phase1/structure_viewer_visual_regression_baseline.json"),
    Path("scripts/json-module-loader.mjs"),
    Path("tests/frontend/workbench-prototype-smoke.spec.ts"),
    Path("tests/frontend/workbench-v2-e2e.spec.ts"),
    Path("tests/frontend/workbench-v2-unit-coordinate-guard.spec.ts"),
    Path("tests/frontend/workbench-v2-live-provider-guard.spec.ts"),
    Path("tests/frontend/workbench-v2-job-contract.spec.ts"),
    Path("tests/frontend/workbench-v2-engineering-value-state.spec.ts"),
    Path("tests/frontend/workbench-v2-status-taxonomy.spec.ts"),
    Path("tests/frontend/developer-preview-workflow.spec.ts"),
    Path("native/evidence/workbench-evidence-sources-v1.json"),
    Path("native/tests/fixtures/workbench_evidence/manifest.json"),
    Path("docs/native/benchmark-catalog-v1.md"),
    Path("docs/native/rust-native-workbench-v1.md"),
    Path("docs/native/localized-modelir-topology-view-v1.md"),
    Path("docs/native/localized-terminal-result-views-v1.md"),
    Path("docs/native/modelir-constraint-value-edit-v1.md"),
    Path("docs/native/modelir-linear-material-edit-v1.md"),
    Path("docs/native/modelir-frame-section-edit-v1.md"),
    Path("docs/native/modelir-frame-element-orientation-edit-v1.md"),
    Path("docs/native/modelir-frame-element-properties-edit-v1.md"),
    Path("docs/native/modelir-element-connectivity-edit-v1.md"),
    Path("docs/native/modelir-frame3d-member-add-v1.md"),
    Path("docs/native/modelir-nodal-load-add-v1.md"),
    Path("docs/native/modelir-fixed-constraint-add-v1.md"),
    Path("docs/native/modelir-linear-load-pattern-add-v1.md"),
    Path("docs/native/modelir-linear-material-add-v1.md"),
    Path("docs/native/modelir-frame-section-add-v1.md"),
    Path("docs/native/modelir-truss3d-authoring-v1.md"),
    Path("docs/native/modelir-truss3d-editing-v1.md"),
    Path("docs/native/modelir-truss3d-leaf-deletion-v1.md"),
    Path("docs/native/modelir-linear-analysis-request-create-v1.md"),
    Path("docs/native/modelir-nodal-load-edit-v1.md"),
    Path("docs/native/workbench-ui-transition-v1.md"),
    Path("package.json"),
    Path("vite.config.ts"),
    Path("src/main.tsx"),
)
NODE_WORKFLOW_TOKENS = ("actions/setup-node@", "npm ci", "npm run")
FRONTEND_INSTALL_WORKFLOW_COMMAND = (
    "cargo run --quiet --locked --manifest-path native/Cargo.toml "
    "-p structural-frontend-contract -- frontend-install --root ."
)
FRONTEND_AUDIT_WORKFLOW_COMMAND = (
    "cargo run --quiet --locked --manifest-path native/Cargo.toml "
    "-p structural-frontend-contract -- frontend-audit --root ."
)
PLAYWRIGHT_INSTALL_WORKFLOW_COMMAND = (
    "cargo run --quiet --locked --manifest-path native/Cargo.toml "
    "-p structural-frontend-contract -- playwright-install --root ."
)
FRONTEND_CONTRACT_WORKFLOW_PREFIX = (
    "cargo run --quiet --locked --manifest-path native/Cargo.toml "
    "-p structural-frontend-contract -- "
)
DIRECT_FRONTEND_WORKFLOW_COMMANDS = {
    "frontend-web-ci.yml": (
        "frontend-audit --root .",
        "frontend-build --root .",
        "check --root .",
        "prototype --root .",
        "prototype-browser-smoke --root .",
        "workbench-v2-browser-smoke --root .",
    ),
    "nightly-full-quality.yml": (
        "workbench-v2-browser-smoke --root .",
        "viewer-sample-workflow --root .",
        "viewer-report-pdf-smoke --root .",
        "viewer-performance-probe --root .",
        "viewer-visual-regression --root .",
    ),
    "runtime-input-viewer-ci.yml": (
        "viewer-js-syntax --root .",
        "frontend-build --root .",
        "workbench-v2-browser-smoke --root .",
    ),
    "viewer-browser-ci.yml": (
        "viewer-manifest --root .",
        "browser-smoke --root . --mode minimal",
    ),
}
EXPECTED_FEATURES = {
    "import_validate_run_resume_compare_report": ("c5_implemented", False),
    "deterministic_result_inspect_human_review_export": ("c5_implemented", False),
    "bounded_general_modelir_terminal_topology_view": ("c5_implemented", False),
    "bounded_terminal_utf8_modelir_topology_view_en_us_ko_kr": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_modelir_node_coordinate_edit": ("c5_implemented", False),
    "bounded_cpp_revalidated_existing_modelir_nodal_load_component_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_modelir_constraint_prescribed_value_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_linear_elastic_material_parameter_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_frame3d_section_parameter_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_frame3d_element_orientation_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_frame3d_element_material_section_reference_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_truss3d_section_area_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_truss3d_element_material_section_reference_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_existing_two_node_element_connectivity_edit": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_linear_frame3d_member_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_linear_static_nodal_load_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_homogeneous_fixed_constraint_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_linear_static_load_pattern_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_linear_elastic_isotropic_material_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_frame3d_section_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_truss3d_section_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_linear_truss3d_member_add": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_revalidated_last_neutral_truss3d_leaf_member_delete": (
        "c5_implemented",
        False,
    ),
    "bounded_cpp_assembly_preflighted_modelir_linear_cpu_request_creation": (
        "c5_implemented",
        False,
    ),
    "bounded_ndtha_terminal_response_history_view": ("c5_implemented", False),
    "bounded_fixed_guided_ndtha_deformed_shape_view": ("c5_implemented", False),
    "bounded_terminal_utf8_ndtha_result_views_en_us_ko_kr": (
        "c5_implemented",
        False,
    ),
    "general_visual_model_editing_and_3d_result_exploration": ("open", True),
    "arbitrary_modelir_topology_and_solver_selection": ("open", True),
    "benchmark_and_evidence_catalog_browsing": ("c5_implemented", False),
    "bounded_terminal_utf8_linear_report_view_en_us_ko_kr": (
        "c5_implemented",
        False,
    ),
    "bounded_embedded_font_pdf_en_us_ko_kr": ("c5_implemented", False),
    "accessibility_localization_and_unicode_report_ui": ("open", True),
}
EXPECTED_PREREQUISITES = {
    "native_feature_parity_complete",
    "active_node_verification_authority_zero",
    "language_neutral_golden_ownership_complete",
    "approved_hip_c2_receipts_complete",
    "deprecation_window_complete",
    "rollback_package_complete",
    "clean_machine_product_e2e_complete",
    "native_result_error_checksum_parity_complete",
}


def _text(root: Path, relative: Path, blockers: list[str]) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"workbench_ui_file_unreadable:{relative.as_posix()}:{exc}")
        return ""


def _json(root: Path, relative: Path, blockers: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(_text(root, relative, blockers))
    except json.JSONDecodeError as exc:
        blockers.append(f"workbench_ui_json_invalid:{relative.as_posix()}:{exc}")
        return {}
    if not isinstance(value, dict):
        blockers.append(f"workbench_ui_json_not_object:{relative.as_posix()}")
        return {}
    return value


def _files(root: Path, directory: str, suffixes: tuple[str, ...]) -> list[Path]:
    base = root / directory
    if not base.is_dir():
        return []
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file() and path.suffix in suffixes
    )


def _active_node_workflows(root: Path) -> list[str]:
    directory = root / ".github/workflows"
    if not directory.is_dir():
        return []
    active: list[str] = []
    for path in sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if any(token in text for token in NODE_WORKFLOW_TOKENS):
            active.append(path.relative_to(root).as_posix())
    return active


def _require_tokens(
    relative: Path,
    text: str,
    tokens: tuple[str, ...],
    blockers: list[str],
) -> None:
    for token in tokens:
        if token not in text:
            blockers.append(
                f"workbench_ui_token_missing:{relative.as_posix()}:{token}"
            )


def check_native_workbench_ui_transition(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            blockers.append(f"workbench_ui_file_missing:{relative.as_posix()}")
    removed_prototype_wrapper = Path(
        "scripts/verify-workbench-prototype-browser-smoke.mjs"
    )
    if (root / removed_prototype_wrapper).exists():
        blockers.append("workbench_ui_removed_prototype_browser_wrapper_present")
    removed_workbench_v2_wrapper = Path("scripts/verify-workbench-v2-e2e.mjs")
    if (root / removed_workbench_v2_wrapper).exists():
        blockers.append("workbench_ui_removed_workbench_v2_browser_wrapper_present")
    removed_viewer_pdf_wrapper = Path("scripts/verify-structure-viewer-report-pdf.mjs")
    if (root / removed_viewer_pdf_wrapper).exists():
        blockers.append("workbench_ui_removed_viewer_pdf_wrapper_present")

    manifest = _json(root, MANIFEST, blockers)
    for field, expected in (
        ("schema_version", "native-workbench-ui-transition.v1"),
        ("status", "transition_active"),
        ("current_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if manifest.get(field) != expected:
            blockers.append(f"workbench_ui_manifest_field_invalid:{field}")

    native = manifest.get("native_surface")
    if not isinstance(native, dict):
        blockers.append("workbench_ui_native_surface_invalid")
        native = {}
    if native.get("binary") != "structural-workbench":
        blockers.append("workbench_ui_native_binary_invalid")
    if native.get("core_flow") != [
        "import",
        "validate",
        "run",
        "resume",
        "compare",
        "report",
    ]:
        blockers.append("workbench_ui_native_core_flow_invalid")
    if native.get("model_flow") != [
        "model-view",
        "model-edit-node",
        "model-edit-nodal-load",
        "model-edit-constraint-value",
        "model-edit-linear-material",
        "model-edit-frame-section",
        "model-edit-frame-element-orientation",
        "model-edit-frame-element-properties",
        "model-edit-truss-section",
        "model-edit-truss-element-properties",
        "model-edit-element-connectivity",
        "model-add-frame3d-member",
        "model-add-nodal-load",
        "model-add-fixed-constraint",
        "model-add-linear-load-pattern",
        "model-add-linear-material",
        "model-add-frame-section",
        "model-add-truss-section",
        "model-add-truss3d-member",
        "model-delete-truss3d-leaf-member",
        "model-create-linear-analysis-request",
    ]:
        blockers.append("workbench_ui_native_model_flow_invalid")
    if native.get("operator_flow") != [
        "inspect",
        "report-view",
        "result-view",
        "result-deformed-view",
        "report-export-pdf",
        "review",
        "export",
    ]:
        blockers.append("workbench_ui_native_operator_flow_invalid")
    if native.get("catalog_flow") != [
        "catalog",
        "catalog-show",
        "evidence",
        "evidence-show",
    ]:
        blockers.append("workbench_ui_native_catalog_flow_invalid")
    if native.get("evidence_bundle_flow") != [
        "structural-evidence check",
        "structural-evidence build",
    ]:
        blockers.append("workbench_ui_native_evidence_bundle_flow_invalid")
    if native.get("benchmark_catalog_flow") != [
        "structural-catalog check",
        "structural-catalog build",
    ]:
        blockers.append("workbench_ui_native_benchmark_catalog_flow_invalid")
    if native.get("legacy_frontend_contract_flow") != [
        "structural-frontend-contract check",
        "structural-frontend-contract smoke",
        "structural-frontend-contract delivery",
        "structural-frontend-contract frontend-audit",
        "structural-frontend-contract frontend-audit-report",
        "structural-frontend-contract frontend-build",
        "structural-frontend-contract frontend-dev",
        "structural-frontend-contract frontend-install",
        "structural-frontend-contract frontend-preview",
        "structural-frontend-contract phase5-task-browser-smoke",
        "structural-frontend-contract playwright-install",
        "structural-frontend-contract prototype",
        "structural-frontend-contract prototype-browser-smoke",
        "structural-frontend-contract workbench-v2-browser-smoke",
        "structural-frontend-contract browser-smoke",
        "structural-frontend-contract viewer-js-syntax",
        "structural-frontend-contract viewer-sample-workflow",
        "structural-frontend-contract viewer-performance-probe",
        "structural-frontend-contract viewer-visual-regression",
        "structural-frontend-contract viewer-readme-capture",
        "structural-frontend-contract viewer-report-pdf-export",
        "structural-frontend-contract viewer-report-pdf-smoke",
        "structural-frontend-contract serve",
        "structural-frontend-contract viewer-manifest",
    ]:
        blockers.append("workbench_ui_native_frontend_contract_flow_invalid")
    if native.get("legacy_frontend_runtime") != {
        "build_smoke_node_required": True,
        "frontend_build_node_required": True,
        "frontend_build_typescript_required": True,
        "frontend_build_vite_required": True,
        "frontend_build_browser_required": False,
        "frontend_build_listener_required": False,
        "frontend_dev_node_required": True,
        "frontend_dev_vite_required": True,
        "frontend_dev_browser_required": False,
        "frontend_dev_retained_vite_listener": True,
        "frontend_install_node_required": True,
        "frontend_install_npm_required": True,
        "frontend_install_browser_required": False,
        "frontend_install_network_uninstrumented": True,
        "frontend_install_node_modules_mutation_expected": True,
        "frontend_audit_node_required": True,
        "frontend_audit_npm_required": True,
        "frontend_audit_browser_required": False,
        "frontend_audit_numeric_nonzero_non_blocking": True,
        "frontend_audit_findings_not_independently_classified": True,
        "frontend_audit_network_uninstrumented": True,
        "frontend_audit_report_node_required": True,
        "frontend_audit_report_npm_required": True,
        "frontend_audit_report_browser_required": False,
        "frontend_audit_report_python_direct_npm_entrypoints": 0,
        "frontend_audit_report_python_wrapper_retained": True,
        "frontend_audit_report_strict_json_owned_by_rust": True,
        "frontend_audit_report_verified_publication_owned_by_rust": True,
        "frontend_audit_report_network_uninstrumented": True,
        "quality_gate_frontend_npm_entrypoints": 0,
        "quality_gate_frontend_direct_rust_entrypoints": True,
        "quality_gate_frontend_strict_audit_policy": True,
        "hosted_frontend_workflow_npm_script_entrypoints": 0,
        "hosted_frontend_workflow_direct_rust_entrypoints": True,
        "hosted_frontend_workflow_native_bash_wrappers_retained": True,
        "frontend_preview_node_required": False,
        "frontend_preview_browser_required": False,
        "frontend_preview_loopback_required": True,
        "playwright_install_node_required": True,
        "playwright_install_playwright_required": True,
        "playwright_install_browser_process_required": False,
        "playwright_install_external_network_uninstrumented": True,
        "playwright_install_host_mutation_possible": True,
        "browser_smoke_node_required": True,
        "browser_smoke_playwright_required": True,
        "browser_smoke_browser_required": True,
        "prototype_browser_smoke_node_required": True,
        "prototype_browser_smoke_playwright_required": True,
        "prototype_browser_smoke_browser_required": True,
        "workbench_v2_browser_smoke_build_node_required": True,
        "workbench_v2_browser_smoke_node_required": True,
        "workbench_v2_browser_smoke_playwright_required": True,
        "workbench_v2_browser_smoke_browser_required": True,
        "phase5_task_browser_smoke_python_npm_entrypoints": 0,
        "phase5_task_browser_smoke_python_npx_entrypoints": 0,
        "phase5_task_browser_smoke_direct_rust_entrypoint": True,
        "phase5_task_browser_smoke_python_wrapper_retained": True,
        "phase5_task_browser_smoke_build_node_required": True,
        "phase5_task_browser_smoke_node_required": True,
        "phase5_task_browser_smoke_playwright_required": True,
        "phase5_task_browser_smoke_browser_required": True,
        "phase5_task_browser_smoke_fixed_loopback_required": True,
        "viewer_js_syntax_node_required": True,
        "viewer_js_syntax_browser_required": False,
        "viewer_js_syntax_listener_required": False,
        "viewer_js_syntax_network_required": False,
        "viewer_readme_capture_node_required": True,
        "viewer_readme_capture_playwright_required": True,
        "viewer_readme_capture_browser_required": True,
        "viewer_readme_capture_internal_loopback_required": True,
        "viewer_report_pdf_export_node_required": True,
        "viewer_report_pdf_export_playwright_required": True,
        "viewer_report_pdf_export_browser_required": True,
        "viewer_report_pdf_export_pdftotext_optional": True,
        "viewer_report_pdf_smoke_node_required": True,
        "viewer_report_pdf_smoke_playwright_required": True,
        "viewer_report_pdf_smoke_browser_required": True,
        "viewer_report_pdf_smoke_pdftotext_optional": True,
        "viewer_performance_probe_node_required": True,
        "viewer_performance_probe_playwright_required": True,
        "viewer_performance_probe_browser_required": True,
        "viewer_performance_probe_internal_loopback_required": True,
        "viewer_sample_workflow_node_required": True,
        "viewer_sample_workflow_playwright_required": True,
        "viewer_sample_workflow_browser_required": True,
        "viewer_sample_workflow_internal_loopback_required": True,
        "viewer_visual_regression_node_required": True,
        "viewer_visual_regression_playwright_required": True,
        "viewer_visual_regression_browser_required": True,
        "viewer_visual_regression_internal_loopback_required": True,
    }:
        blockers.append("workbench_ui_native_frontend_runtime_boundary_invalid")
    for field in (
        "runtime_python_required",
        "runtime_node_required",
        "runtime_browser_required",
        "human_review_inferred",
    ):
        if native.get(field) is not False:
            blockers.append(f"workbench_ui_native_false_boundary_invalid:{field}")
    if native.get("linear_report_locales") != ["en-US", "ko-KR"]:
        blockers.append("workbench_ui_native_linear_report_locales_invalid")
    if native.get("localized_pdf_locales") != ["en-US", "ko-KR"]:
        blockers.append("workbench_ui_native_localized_pdf_locales_invalid")
    if native.get("localized_result_view_locales") != ["en-US", "ko-KR"]:
        blockers.append("workbench_ui_native_localized_result_view_locales_invalid")
    if native.get("localized_model_view_locales") != ["en-US", "ko-KR"]:
        blockers.append("workbench_ui_native_localized_model_view_locales_invalid")

    legacy = manifest.get("legacy_surface")
    if not isinstance(legacy, dict):
        blockers.append("workbench_ui_legacy_surface_invalid")
        legacy = {}
    for field, expected in (
        ("product_entrypoint", "src/main.tsx"),
        ("package_manifest", "package.json"),
        ("build_config", "vite.config.ts"),
        ("production_deployment_authority", False),
        ("verification_authority_active", True),
        ("rollback_archive_complete", False),
        ("removal_allowed", False),
    ):
        if legacy.get(field) != expected:
            blockers.append(f"workbench_ui_legacy_field_invalid:{field}")
    for source_root in legacy.get("source_roots", []):
        if not isinstance(source_root, str) or not (root / source_root).is_dir():
            blockers.append(f"workbench_ui_legacy_source_root_invalid:{source_root}")

    actual_inventory = {
        "src_ts_tsx_files": len(_files(root, "src", (".ts", ".tsx"))),
        "src_js_mjs_files": len(_files(root, "src", (".js", ".mjs"))),
        "frontend_ts_tsx_test_files": len(
            _files(root, "tests/frontend", (".ts", ".tsx"))
        ),
        "node_js_mjs_script_files": len(_files(root, "scripts", (".js", ".mjs"))),
        "js_mjs_test_files": len(_files(root, "tests", (".js", ".mjs"))),
    }
    if legacy.get("source_inventory") != actual_inventory:
        blockers.append("workbench_ui_legacy_source_inventory_drift")

    active_node_workflows = _active_node_workflows(root)
    if legacy.get("active_node_workflows") != active_node_workflows:
        blockers.append("workbench_ui_active_node_workflow_inventory_drift")

    entrypoint = _text(root, Path("src/main.tsx"), blockers)
    _require_tokens(
        Path("src/main.tsx"),
        entrypoint,
        ("from 'react'", "react-dom/client", "WorkbenchPage", "ReactDOM.createRoot"),
        blockers,
    )
    package = _json(root, Path("package.json"), blockers)
    dependencies = package.get("dependencies")
    dev_dependencies = package.get("devDependencies")
    scripts = package.get("scripts")
    if not isinstance(dependencies, dict) or not {"react", "react-dom"}.issubset(
        dependencies
    ):
        blockers.append("workbench_ui_react_dependency_inventory_invalid")
    if not isinstance(dev_dependencies, dict) or not {
        "typescript",
        "vite",
        "@vitejs/plugin-react",
    }.issubset(dev_dependencies):
        blockers.append("workbench_ui_typescript_dependency_inventory_invalid")
    if not isinstance(scripts, dict) or not {
        "build",
        "build:evidence-bundle",
        "verify:evidence-bundle-contract",
        "verify:workbench-v2-e2e",
    }.issubset(scripts):
        blockers.append("workbench_ui_node_script_inventory_invalid")
    elif not isinstance(scripts["build:evidence-bundle"], str) or (
        "structural-evidence" not in scripts["build:evidence-bundle"]
        and "build_native_workbench_evidence_bundle.sh"
        not in scripts["build:evidence-bundle"]
    ):
        blockers.append("workbench_ui_evidence_builder_authority_invalid")
    if not isinstance(scripts, dict) or not {
        "build:benchmark-catalog",
        "verify:benchmark-catalog-contract",
    }.issubset(scripts):
        blockers.append("workbench_ui_catalog_script_inventory_invalid")
    elif not isinstance(scripts["build:benchmark-catalog"], str) or (
        "structural-catalog" not in scripts["build:benchmark-catalog"]
        and "build_native_benchmark_catalog.sh"
        not in scripts["build:benchmark-catalog"]
    ):
        blockers.append("workbench_ui_catalog_builder_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("verify:frontend-contract") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- check --root ."
    ):
        blockers.append("workbench_ui_frontend_contract_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("build") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- frontend-build --root ."
    ):
        blockers.append("workbench_ui_frontend_build_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("dev") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- frontend-dev --root ."
    ):
        blockers.append("workbench_ui_frontend_dev_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("install:dependencies") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- frontend-install --root ."
    ):
        blockers.append("workbench_ui_frontend_install_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("preview") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- frontend-preview --root ."
    ):
        blockers.append("workbench_ui_frontend_preview_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("install:browser-runtime") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- playwright-install --root ."
    ):
        blockers.append("workbench_ui_playwright_install_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("verify:frontend-smoke") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- smoke --root ."
    ):
        blockers.append("workbench_ui_frontend_smoke_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:workbench-viewer-delivery"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- delivery --root ."
    ):
        blockers.append("workbench_ui_frontend_delivery_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("verify:viewer-manifest") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-manifest --root ."
    ):
        blockers.append("workbench_ui_viewer_manifest_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:workbench-prototype-dom-contract"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- prototype --root ."
    ):
        blockers.append("workbench_ui_prototype_contract_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("serve:viewer") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- serve --root ."
    ):
        blockers.append("workbench_ui_viewer_server_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:frontend-browser-smoke"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- browser-smoke --root ."
    ):
        blockers.append("workbench_ui_viewer_browser_smoke_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:workbench-prototype-browser-smoke"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- prototype-browser-smoke --root ."
    ):
        blockers.append("workbench_ui_prototype_browser_smoke_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("verify:workbench-v2-e2e") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- workbench-v2-browser-smoke --root ."
    ):
        blockers.append("workbench_ui_workbench_v2_browser_smoke_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("verify:viewer-js-syntax") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-js-syntax --root ."
    ):
        blockers.append("workbench_ui_viewer_js_syntax_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("verify:viewer-report-pdf") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-report-pdf-smoke --root ."
    ):
        blockers.append("workbench_ui_viewer_report_pdf_smoke_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("export:viewer-report-pdf") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-report-pdf-export --root ."
    ):
        blockers.append("workbench_ui_viewer_report_pdf_export_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get("capture:readme-viewer-image") != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-readme-capture --root ."
    ):
        blockers.append("workbench_ui_viewer_readme_capture_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:viewer-performance-probe"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-performance-probe --root ."
    ):
        blockers.append("workbench_ui_viewer_performance_probe_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:viewer-sample-workflow"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-sample-workflow --root ."
    ):
        blockers.append("workbench_ui_viewer_sample_workflow_authority_invalid")
    if not isinstance(scripts, dict) or scripts.get(
        "verify:viewer-visual-regression"
    ) != (
        "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-visual-regression --root ."
    ):
        blockers.append("workbench_ui_viewer_visual_regression_authority_invalid")

    runtime_input_ci = _text(
        root, Path(".github/workflows/runtime-input-viewer-ci.yml"), blockers
    )
    if (
        "Rust-orchestrated Viewer JavaScript syntax gate" not in runtime_input_ci
        or (
            f"{FRONTEND_CONTRACT_WORKFLOW_PREFIX}viewer-js-syntax --root ."
            not in runtime_input_ci
        )
        or "npm run verify:viewer-js-syntax" in runtime_input_ci
        or "node --check" in runtime_input_ci
    ):
        blockers.append("workbench_ui_viewer_js_syntax_ci_authority_invalid")

    for workflow_name in (
        "ci.yml",
        "frontend-web-ci.yml",
        "nightly-full-quality.yml",
        "runtime-input-viewer-ci.yml",
        "viewer-browser-ci.yml",
    ):
        workflow_path = Path(".github/workflows") / workflow_name
        workflow = _text(root, workflow_path, blockers)
        if (
            workflow.count(FRONTEND_INSTALL_WORKFLOW_COMMAND) != 1
            or "Rust-orchestrated frontend dependency install" not in workflow
            or "run: npm ci" in workflow
            or "npm run install:dependencies" in workflow
        ):
            blockers.append(
                f"workbench_ui_frontend_install_ci_authority_invalid:{workflow_name}"
            )
        if (
            workflow.count(PLAYWRIGHT_INSTALL_WORKFLOW_COMMAND) != 1
            or "Rust-orchestrated Playwright browser install" not in workflow
            or "npx playwright install" in workflow
            or "npm run install:browser-runtime" in workflow
        ):
            blockers.append(
                f"workbench_ui_playwright_install_ci_authority_invalid:{workflow_name}"
            )

    for workflow_name, commands in DIRECT_FRONTEND_WORKFLOW_COMMANDS.items():
        workflow_path = Path(".github/workflows") / workflow_name
        workflow = _text(root, workflow_path, blockers)
        if "npm run " in workflow or "npx " in workflow or "run: node " in workflow:
            blockers.append(
                f"workbench_ui_frontend_workflow_launcher_invalid:{workflow_name}"
            )
        for command in commands:
            expected = f"{FRONTEND_CONTRACT_WORKFLOW_PREFIX}{command}"
            if workflow.count(expected) != 1:
                blockers.append(
                    f"workbench_ui_frontend_workflow_command_invalid:{workflow_name}:{command}"
                )
    frontend_web_ci = _text(
        root, Path(".github/workflows/frontend-web-ci.yml"), blockers
    )
    if (
        frontend_web_ci.count(FRONTEND_AUDIT_WORKFLOW_COMMAND) != 1
        or "Rust-orchestrated non-blocking dependency audit" not in frontend_web_ci
        or "run: npm audit" in frontend_web_ci
    ):
        blockers.append("workbench_ui_frontend_audit_ci_authority_invalid")
    quality_gate = _text(root, Path("scripts/verify_quality_gate.py"), blockers)
    _require_tokens(
        Path("scripts/verify_quality_gate.py"),
        quality_gate,
        (
            "def _frontend_contract",
            '_frontend_contract("frontend-install")',
            '_frontend_contract("frontend-audit", "--fail-on-nonzero")',
            '_frontend_contract("check")',
            '_frontend_contract("frontend-build")',
            '_frontend_contract("viewer-manifest")',
            '_frontend_contract("browser-smoke", "--mode", "minimal")',
            '_frontend_contract("browser-smoke")',
            '_frontend_contract("viewer-sample-workflow")',
            '_frontend_contract("viewer-report-pdf-smoke")',
            '_frontend_contract("viewer-performance-probe")',
            '_frontend_contract("viewer-visual-regression")',
        ),
        blockers,
    )
    if "def _npm" in quality_gate or "_npm()" in quality_gate or '["npm"' in quality_gate:
        blockers.append("workbench_ui_quality_gate_frontend_launcher_invalid")
    for wrapper in (
        "bash ./scripts/build_native_benchmark_catalog.sh --check",
        "bash ./scripts/build_native_workbench_evidence_bundle.sh",
    ):
        if frontend_web_ci.count(wrapper) != 1:
            blockers.append(
                f"workbench_ui_frontend_native_wrapper_invalid:{wrapper}"
            )

    native_lib = _text(
        root, Path("native/crates/structural-workbench/src/lib.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/lib.rs"),
        native_lib,
        (
            "structural-native-workbench-view.v1",
            "structural-native-workbench-review.v1",
            "structural-native-workbench-export.v1",
            "pub fn inspect_json",
            "pub fn linear_report_text",
            "pub fn ndtha_response_view_text",
            "pub fn ndtha_response_view_text_localized",
            "pub fn fixed_guided_deformed_shape_view_text",
            "pub fn fixed_guided_deformed_shape_view_text_localized",
            "render_model_topology_view_file_localized",
            "render_model_topology_view_localized",
            "pub fn publish_review",
            "pub fn export_json",
            "automatically_inferred",
            "browse_embedded_benchmark_catalog",
            "browse_evidence_bundle",
        ),
        blockers,
    )
    native_report_view = _text(
        root, Path("native/crates/structural-workbench/src/report_view.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/report_view.rs"),
        native_report_view,
        (
            "structural-native-workbench-linear-report.v1",
            "WorkbenchReportLocaleV1",
            '"en-US"',
            '"ko-KR"',
            "safe_terminal_text",
            "not WCAG, PDF/UA",
        ),
        blockers,
    )
    native_result_view = _text(
        root, Path("native/crates/structural-workbench/src/result_view.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/result_view.rs"),
        native_result_view,
        (
            "structural-native-workbench-ndtha-response-view.v1",
            "WorkbenchResultChannelV1",
            "WORKBENCH_RESULT_VIEW_MAX_COUNT_V1",
            "ResultIR v1 does not carry dt_s",
            "not a time reconstruction, 3D/deformed/modal/contour view",
            "시간값을 추론하지 않습니다",
        ),
        blockers,
    )
    native_deformed_view = _text(
        root, Path("native/crates/structural-workbench/src/deformed_view.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/deformed_view.rs"),
        native_deformed_view,
        (
            "structural-native-workbench-fixed-guided-deformed-view.v1",
            "fixed_guided_frame3d_x",
            "validate_model_bytes",
            "Top displacement global X (m)",
            "C++ fixed-guided adapter execution",
            "C++ 고정-가이드 어댑터 실행",
            'semantic_snapshot_value: "verified"',
            "not_general_nodal_displacement_3d_modal_contour",
        ),
        blockers,
    )
    native_model_view = _text(
        root, Path("native/crates/structural-workbench/src/model_view.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/model_view.rs"),
        native_model_view,
        (
            "structural-native-model-topology-view.v1",
            "render_model_topology_view_file_localized",
            "render_model_topology_view_localized",
            "WorkbenchReportLocaleV1::EnUs",
            "WorkbenchReportLocaleV1::KoKr",
            "Structural Native Workbench - 모델 위상 뷰",
            "C++ 의미 스냅샷",
            "보기 해시",
        ),
        blockers,
    )
    native_model_edit = _text(
        root, Path("native/crates/structural-workbench/src/model_edit.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/model_edit.rs"),
        native_model_edit,
        (
            "structural-native:model-edit-linear-material.v1",
            "structural-native:model-edit-frame-section.v1",
            "structural-native:model-edit-frame-element-orientation.v1",
            "structural-native:model-edit-frame-element-properties.v1",
            "structural-native:model-edit-element-connectivity.v1",
            "structural-native:model-add-frame3d-member.v1",
            "structural-native:model-add-nodal-load.v1",
            "structural-native:model-add-fixed-constraint.v1",
            "structural-native:model-add-linear-load-pattern.v1",
            "structural-native:model-add-linear-material.v1",
            "structural-native:model-add-frame-section.v1",
            "pub fn edit_model_linear_material",
            "pub fn edit_model_frame_section",
            "pub fn edit_model_frame_element_orientation",
            "pub fn edit_model_frame_element_properties",
            "pub fn edit_model_element_connectivity",
            "pub fn add_model_frame3d_member",
            "pub fn add_model_nodal_load",
            "pub fn add_model_fixed_constraint",
            "pub fn add_model_linear_load_pattern",
            "pub fn add_model_linear_material",
            "pub fn add_model_frame_section",
            'mark_roundtrip_entity_approximated(&mut edited, "material", material_id)',
            'mark_roundtrip_entity_approximated(&mut edited, "section", section_id)',
            'mark_roundtrip_entity_approximated(&mut edited, "element", element_id)',
        ),
        blockers,
    )
    native_analysis_request = _text(
        root, Path("native/crates/structural-workbench/src/analysis_request.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/analysis_request.rs"),
        native_analysis_request,
        (
            "structural-native-model-linear-request-create-receipt.v1",
            "pub fn create_model_linear_analysis_request",
            "build_model_ir_linear_analysis_request_v1",
            "validate_model_ir_linear_analysis_compatibility",
            "cpp_linear_assembly_preflight_verified",
            "execution_started",
            "bounded_cpp_assembly_preflighted_modelir_linear_cpu_request_creation",
        ),
        blockers,
    )
    viewer_report_pdf_export = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/viewer_report_pdf_export.rs"
        ),
        blockers,
    )
    verified_publication = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/verified_publication.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/verified_publication.rs"),
        verified_publication,
        (
            "pub(crate) fn prepare_verified_publication_target",
            "pub(crate) fn publish_verified_outputs",
            "VERIFIED_PUBLICATION_STRATEGY",
            "create_new",
            "require_unchanged",
            "rollback_publication",
        ),
        blockers,
    )
    viewer_js_syntax = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/viewer_js_syntax.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/viewer_js_syntax.rs"),
        viewer_js_syntax,
        (
            "pub fn run_viewer_js_syntax",
            "structural-native-viewer-js-syntax-receipt.v1",
            "viewer_js_syntax_contract_changed",
            "Command::new(node_launcher())",
            '.arg("--check")',
            "verify_execution_inputs_unchanged",
            "direct_processes_spawned",
            "browser_runtime_required",
        ),
        blockers,
    )
    viewer_readme_capture = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/viewer_readme_capture.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/viewer_readme_capture.rs"),
        viewer_readme_capture,
        (
            "pub fn run_viewer_readme_capture",
            "scripts/capture-readme-viewer-image.mjs",
            "viewer_readme_capture_contract_changed",
            "viewer_readme_capture_png_invalid",
            "png_crc32",
            "README_CAPTURE_VIEW_PRESET",
            "publish_verified_outputs",
            "direct_processes_spawned",
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/viewer_report_pdf_export.rs"
        ),
        viewer_report_pdf_export,
        (
            "pub fn run_viewer_report_pdf_export",
            "run_viewer_report_pdf_smoke",
            "viewer_report_pdf_export_output_changed",
            "viewer_report_pdf_export_publish_failed",
            "publish_verified_outputs",
            "VERIFIED_PUBLICATION_STRATEGY",
            "direct_processes_spawned",
            "retained Node exporter",
        ),
        blockers,
    )
    frontend_contract = _text(
        root, Path("native/crates/structural-frontend-contract/src/lib.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/lib.rs"),
        frontend_contract,
        (
            "structural-native-frontend-contract-receipt.v1",
            "structural-native-frontend-delivery-receipt.v1",
            "pub fn check_frontend_contract",
            "pub fn check_frontend_delivery",
            "decode_json_strict",
            "frontend_forbidden_path_present",
            "commands_executed",
            "network_access_count",
        ),
        blockers,
    )
    viewer_manifest = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/viewer_manifest.rs"),
        blockers,
    )
    frontend_build = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/frontend_build.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/frontend_build.rs"),
        frontend_build,
        (
            "pub fn run_frontend_build",
            "structural-native-frontend-build-receipt.v1",
            "node_modules/typescript/bin/tsc",
            "node_modules/vite/bin/vite.js",
            "frontend_build_source_changed",
            "frontend_build_runtime_changed",
            '.env_remove("NODE_OPTIONS")',
            "check_frontend_delivery",
            "direct_processes_spawned",
            "delivery_receipt_hash",
        ),
        blockers,
    )
    frontend_dev = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/frontend_dev.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/frontend_dev.rs"),
        frontend_dev,
        (
            "pub fn run_frontend_dev",
            "structural-native-frontend-dev-receipt.v1",
            "node_modules/vite/bin/vite.js",
            "frontend_dev_host_forbidden",
            "frontend_dev_runtime_changed",
            '.env_remove("NODE_OPTIONS")',
            "--strictPort",
            "source_mutation_policy",
            "direct_processes_spawned",
        ),
        blockers,
    )
    frontend_install = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/frontend_install.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/frontend_install.rs"),
        frontend_install,
        (
            "pub fn run_frontend_install",
            "structural-native-frontend-install-receipt.v1",
            '"npm"',
            '"ci"',
            "frontend_install_contract_changed",
            '.env_remove("NODE_OPTIONS")',
            "direct_processes_spawned",
            "network_access_accounting",
            "filesystem_mutation_accounting",
            "environment_accounting",
        ),
        blockers,
    )
    frontend_audit = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/frontend_audit.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/frontend_audit.rs"),
        frontend_audit,
        (
            "pub fn run_frontend_audit",
            "structural-native-frontend-audit-receipt.v1",
            '"audit"',
            '"--audit-level"',
            '"high"',
            "frontend_audit_contract_changed",
            '.env_remove("NODE_OPTIONS")',
            "observed_exit_code",
            "record_numeric_nonzero_without_failing_workflow",
            "fail_command_after_recording_numeric_nonzero",
            "nonzero_not_classified_as_vulnerability_network_or_tool_failure",
            "network_access_accounting",
            "filesystem_mutation_accounting",
            "environment_accounting",
        ),
        blockers,
    )
    frontend_audit_report = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/frontend_audit_report.rs"
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/frontend_audit_report.rs"
        ),
        frontend_audit_report,
        (
            "pub fn run_frontend_audit_report",
            "structural-native-frontend-audit-report-receipt.v1",
            '"audit", "--json"',
            "decode_json_strict",
            "frontend_audit_report_contract_changed",
            '.env_remove("NODE_OPTIONS")',
            "VERIFIED_PUBLICATION_STRATEGY",
            "npm_audit_json_unavailable",
            "frontend_dependency_high_or_critical_vulnerabilities_present",
            "network_access_accounting",
            "filesystem_mutation_accounting",
            "environment_accounting",
        ),
        blockers,
    )
    frontend_audit_report_wrapper = _text(
        root, Path("scripts/build_frontend_dependency_audit_report.py"), blockers
    )
    _require_tokens(
        Path("scripts/build_frontend_dependency_audit_report.py"),
        frontend_audit_report_wrapper,
        (
            '"frontend-audit-report"',
            "NATIVE_COMMAND",
            "_receipt_from_stdout",
            "_load_published_report",
        ),
        blockers,
    )
    if (
        "subprocess.run" not in frontend_audit_report_wrapper
        or "npm audit" in frontend_audit_report_wrapper
        or "[_npm()" in frontend_audit_report_wrapper
        or 'subprocess.run(["npm"' in frontend_audit_report_wrapper
    ):
        blockers.append("workbench_ui_frontend_audit_report_authority_invalid")
    frontend_preview = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/frontend_preview.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/frontend_preview.rs"),
        frontend_preview,
        (
            "pub fn plan_frontend_preview",
            "pub fn serve_frontend_preview",
            "structural-native-frontend-preview-receipt.v1",
            "frontend_preview_host_forbidden",
            "check_frontend_delivery",
            "handle_spa_stream",
            "direct_processes_spawned",
            "delivery_receipt_hash",
        ),
        blockers,
    )
    playwright_install = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/playwright_install.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/playwright_install.rs"),
        playwright_install,
        (
            "pub fn run_playwright_install",
            "structural-native-playwright-install-receipt.v1",
            "node_modules/@playwright/test/cli.js",
            '"--with-deps"',
            '"chromium"',
            "playwright_install_contract_changed",
            "playwright_install_runtime_changed",
            '.env_remove("NODE_OPTIONS")',
            "direct_processes_spawned",
            "external_network_access_accounting",
            "system_mutation_accounting",
        ),
        blockers,
    )
    frontend_smoke = _text(
        root, Path("native/crates/structural-frontend-contract/src/smoke.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/smoke.rs"),
        frontend_smoke,
        (
            "pub fn run_frontend_smoke",
            "frontend_smoke_command_failed",
            "frontend_smoke_contract_changed",
            "not_instrumented_npm_ci_may_access_registry",
            "direct_processes_spawned",
            "delivery_receipt_hash",
        ),
        blockers,
    )
    workbench_prototype = _text(
        root, Path("native/crates/structural-frontend-contract/src/prototype.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/prototype.rs"),
        workbench_prototype,
        (
            "pub fn check_workbench_prototype",
            "workbench_prototype_demo_json_invalid",
            "workbench_prototype_source_drift",
            "commands_executed",
            "network_access_count",
            "browser_executed",
        ),
        blockers,
    )
    viewer_server = _text(
        root, Path("native/crates/structural-frontend-contract/src/viewer_server.rs"), blockers
    )
    viewer_browser_smoke = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/browser_smoke.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/browser_smoke.rs"),
        viewer_browser_smoke,
        (
            "pub fn run_viewer_browser_smoke",
            "node_modules/@playwright/test/cli.js",
            "not_instrumented_browser_page_requests",
            "loopback_listener_count",
            "direct_processes_spawned",
            "frontend_contract_receipt_hash",
            "playwright_cli_sha256",
            "execute_playwright",
        ),
        blockers,
    )
    playwright = _text(
        root,
        Path("native/crates/structural-frontend-contract/src/playwright.rs"),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/playwright.rs"),
        playwright,
        (
            "pub(crate) fn execute_playwright",
            "pub(crate) fn validate_playwright_plan",
            "TcpListener::bind",
            "Command::new",
            "playwright_failed",
            "viewer_browser_smoke_failed",
            "workbench_prototype_browser_smoke_failed",
            "workbench_v2_browser_smoke_failed",
            "validate_scoped_policy",
            "validate_spa_policy",
        ),
        blockers,
    )
    prototype_browser_smoke = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/prototype_browser_smoke.rs"
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/prototype_browser_smoke.rs"
        ),
        prototype_browser_smoke,
        (
            "pub fn run_workbench_prototype_browser_smoke",
            "prototype/structural-workbench/",
            "WORKBENCH_PROTOTYPE_BASE_URL",
            "prototype_contract_receipt_hash",
            "loopback_listener_count",
            "direct_processes_spawned",
            "playwright_cli_sha256",
            "not_instrumented_browser_page_requests",
        ),
        blockers,
    )
    workbench_v2_browser_smoke = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/workbench_v2_browser_smoke.rs"
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/workbench_v2_browser_smoke.rs"
        ),
        workbench_v2_browser_smoke,
        (
            "pub fn run_workbench_v2_browser_smoke",
            "npm",
            "VITE_BASE_PATH",
            "WORKBENCH_V2_BASE_URL",
            "NODE_OPTIONS",
            "PlaywrightServerRoute::Spa",
            "workbench_v2_browser_smoke_build_failed",
            "delivery_receipt_hash",
            "loopback_listener_count",
            "direct_processes_spawned",
            "not_instrumented_npm_build_and_browser_page_requests",
        ),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/viewer_server.rs"),
        viewer_server,
        (
            "pub fn plan_viewer_server",
            "pub fn serve_viewer",
            "viewer_server_host_forbidden",
            "allowed_path_prefixes",
            "loopback_only",
            "external_network_access_count",
            "validate_scoped_policy",
        ),
        blockers,
    )
    viewer_report_pdf_smoke = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/viewer_report_pdf_smoke.rs"
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/viewer_report_pdf_smoke.rs"
        ),
        viewer_report_pdf_smoke,
        (
            "pub fn run_viewer_report_pdf_smoke",
            "scripts/export-structure-viewer-report-pdf.mjs",
            "viewer_report_pdf_smoke_export_failed",
            "viewer_report_pdf_smoke_contract_changed",
            "viewer_report_pdf_smoke_pdf_invalid",
            "viewer_report_pdf_smoke_html_invalid",
            "pdftotext",
            "temporary_removed_after_verification",
            "direct_processes_spawned",
            "not_instrumented_exporter_loopback_and_browser_page_requests",
        ),
        blockers,
    )
    viewer_performance_probe = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/viewer_performance_probe.rs"
        ),
        blockers,
    )
    viewer_sample_workflow = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/viewer_sample_workflow.rs"
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/viewer_sample_workflow.rs"
        ),
        viewer_sample_workflow,
        (
            "pub fn run_viewer_sample_workflow",
            "scripts/verify-structure-viewer-sample-workflow.mjs",
            "decode_json_strict",
            "viewer_sample_workflow_failed",
            "viewer_sample_workflow_contract_changed",
            "viewer_sample_workflow_aggregate_mismatch",
            "viewer_sample_workflow_step_failed",
            "temporary_removed_after_verification",
            "direct_processes_spawned",
            "not_instrumented_probe_loopback_and_browser_page_requests",
            "not human new-user observation",
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/viewer_performance_probe.rs"
        ),
        viewer_performance_probe,
        (
            "pub fn run_viewer_performance_probe",
            "scripts/measure-structure-viewer-performance.mjs",
            "decode_json_strict",
            "viewer_performance_probe_failed",
            "viewer_performance_probe_contract_changed",
            "viewer_performance_probe_source_identity_mismatch",
            "viewer_performance_probe_measurement_failed",
            "temporary_removed_after_verification",
            "direct_processes_spawned",
            "not_instrumented_probe_loopback_and_browser_page_requests",
        ),
        blockers,
    )
    viewer_visual_regression = _text(
        root,
        Path(
            "native/crates/structural-frontend-contract/src/viewer_visual_regression.rs"
        ),
        blockers,
    )
    _require_tokens(
        Path(
            "native/crates/structural-frontend-contract/src/viewer_visual_regression.rs"
        ),
        viewer_visual_regression,
        (
            "pub fn run_viewer_visual_regression",
            "scripts/measure-structure-viewer-visual-regression.mjs",
            "structure_viewer_visual_regression_baseline.json",
            "decode_json_strict",
            "viewer_visual_regression_failed",
            "viewer_visual_regression_contract_changed",
            "viewer_visual_regression_source_identity_mismatch",
            "viewer_visual_regression_measurement_failed",
            "temporary_removed_after_verification",
            "direct_processes_spawned",
            "not_instrumented_probe_loopback_and_browser_page_requests",
        ),
        blockers,
    )
    _require_tokens(
        Path("native/crates/structural-frontend-contract/src/viewer_manifest.rs"),
        viewer_manifest,
        (
            "pub fn check_viewer_manifest",
            "viewer_manifest_javascript_projection_drift",
            "viewer_manifest_path_invalid",
            "commands_executed",
            "network_access_count",
        ),
        blockers,
    )
    native_main = _text(
        root, Path("native/crates/structural-workbench/src/main.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-workbench/src/main.rs"),
        native_main,
        (
            'Some("inspect")',
            'Some("report-view")',
            'Some("result-view")',
            'Some("result-deformed-view")',
            'Some("report-export-pdf")',
            'Some("review")',
            'Some("export")',
            'Some("catalog")',
            'Some("catalog-show")',
            'Some("evidence")',
            'Some("evidence-show")',
            'Some("model-edit-linear-material")',
            'Some("model-edit-frame-section")',
            'Some("model-edit-frame-element-orientation")',
            'Some("model-edit-frame-element-properties")',
            'Some("model-edit-element-connectivity")',
            'Some("model-add-frame3d-member")',
            'Some("model-add-nodal-load")',
            'Some("model-add-fixed-constraint")',
            'Some("model-add-linear-load-pattern")',
            'Some("model-add-linear-material")',
            'Some("model-add-frame-section")',
            'Some("model-create-linear-analysis-request")',
        ),
        blockers,
    )
    evidence_builder = _text(
        root, Path("native/crates/structural-evidence/src/lib.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-evidence/src/lib.rs"),
        evidence_builder,
        (
            "structural-native-evidence-bundle-build-receipt.v1",
            "pub fn check_evidence_sources",
            "pub fn build_evidence_bundle",
            "evidence_sensitive_data_detected",
            "evidence_source_commit_mismatch",
            "evidence_output_exists",
        ),
        blockers,
    )
    catalog_builder = _text(
        root, Path("native/crates/structural-catalog/src/lib.rs"), blockers
    )
    _require_tokens(
        Path("native/crates/structural-catalog/src/lib.rs"),
        catalog_builder,
        (
            "structural-native-benchmark-catalog-build-receipt.v1",
            "pub fn check_benchmark_catalog",
            "pub fn build_benchmark_catalog",
            "catalog_duplicate_case_id",
            "catalog_source_checksum_invalid",
            "commands_executed",
            "network_access_count",
        ),
        blockers,
    )
    member_add_doc = _text(
        root, Path("docs/native/modelir-frame3d-member-add-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-frame3d-member-add-v1.md"),
        member_add_doc,
        (
            "model-add-frame3d-member",
            "Rust -> C ABI -> C++",
            "structural-native:model-add-frame3d-member.v1",
            "euler_bernoulli_3d",
            "typed ResultIR",
            "recovery in the product E2E",
            "C6",
        ),
        blockers,
    )
    nodal_load_add_doc = _text(
        root, Path("docs/native/modelir-nodal-load-add-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-nodal-load-add-v1.md"),
        nodal_load_add_doc,
        (
            "model-add-nodal-load",
            "Rust -> C ABI -> C++",
            "structural-native:model-add-nodal-load.v1",
            "linear_static",
            "Typed recovery",
            "fallback 0",
            "C6",
        ),
        blockers,
    )
    fixed_constraint_add_doc = _text(
        root, Path("docs/native/modelir-fixed-constraint-add-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-fixed-constraint-add-v1.md"),
        fixed_constraint_add_doc,
        (
            "model-add-fixed-constraint",
            "Rust -> C ABI -> C++",
            "structural-native:model-add-fixed-constraint.v1",
            "fixed_dofs",
            "active_dof_indices",
            "fallback 0",
            "C6",
        ),
        blockers,
    )
    linear_load_pattern_add_doc = _text(
        root, Path("docs/native/modelir-linear-load-pattern-add-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-linear-load-pattern-add-v1.md"),
        linear_load_pattern_add_doc,
        (
            "model-add-linear-load-pattern",
            "Rust -> C ABI -> C++",
            "structural-native:model-add-linear-load-pattern.v1",
            "linear_static",
            "active_external_load",
            "fallback 0",
            "C6",
        ),
        blockers,
    )
    linear_material_add_doc = _text(
        root, Path("docs/native/modelir-linear-material-add-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-linear-material-add-v1.md"),
        linear_material_add_doc,
        (
            "model-add-linear-material",
            "Rust -> C ABI -> C++",
            "structural-native:model-add-linear-material.v1",
            "linear_elastic_isotropic",
            "state_update_epoch",
            "fallback 0",
            "C6",
        ),
        blockers,
    )
    frame_section_add_doc = _text(
        root, Path("docs/native/modelir-frame-section-add-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-frame-section-add-v1.md"),
        frame_section_add_doc,
        (
            "model-add-frame-section",
            "Rust -> C ABI -> C++",
            "structural-native:model-add-frame-section.v1",
            "frame_3d",
            "active external load",
            "fallback 0",
            "C6",
        ),
        blockers,
    )
    frame_element_properties_doc = _text(
        root, Path("docs/native/modelir-frame-element-properties-edit-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/modelir-frame-element-properties-edit-v1.md"),
        frame_element_properties_doc,
        (
            "model-edit-frame-element-properties",
            "Rust -> C ABI -> C++",
            "structural-native:model-edit-frame-element-properties.v1",
            "active external load",
            "fallback 0",
            "C6",
        ),
        blockers,
    )
    transition_doc = _text(
        root, Path("docs/native/workbench-ui-transition-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/workbench-ui-transition-v1.md"),
        transition_doc,
        (
            "not a C6 removal receipt",
            "bounded terminal UTF-8 linear report view is C5-implemented",
            "bounded embedded-font PDF export is C5-implemented",
            "bounded NDTHA response-history view is C5-implemented",
            "fixed-guided deformed-shape view is C5-implemented",
            "localized NDTHA result views are C5-implemented",
            "model-edit-nodal-load",
            "model-edit-constraint-value",
            "model-edit-linear-material",
            "model-edit-frame-section",
            "model-edit-frame-element-orientation",
            "model-edit-frame-element-properties",
            "model-edit-element-connectivity",
            "model-add-frame3d-member",
            "model-add-nodal-load",
            "model-add-fixed-constraint",
            "model-add-linear-load-pattern",
            "model-add-linear-material",
            "model-add-frame-section",
            "model-create-linear-analysis-request",
            "never infers this decision",
            "seven active workflows",
            "catalog and copied-evidence browsing",
            "Rust-native evidence-bundle builder",
            "Rust-native benchmark-catalog builder",
            "structural-frontend-contract check/smoke/delivery/frontend-audit/frontend-audit-report/frontend-build/frontend-dev/frontend-install/frontend-preview/phase5-task-browser-smoke/playwright-install/prototype/prototype-browser-smoke/workbench-v2-browser-smoke/browser-smoke/viewer-js-syntax/viewer-sample-workflow/viewer-performance-probe/viewer-visual-regression/viewer-readme-capture/viewer-report-pdf-export/viewer-report-pdf-smoke/serve/viewer-manifest",
            "frontend clean-build orchestration, static contract",
            "Frontend TypeScript/Vite build orchestration is Rust-native",
            "Frontend dependency-install orchestration is Rust-native",
            "Frontend dependency-audit orchestration is Rust-native",
            "Frontend dependency-audit evidence projection and publication are Rust-native",
            "Quality-gate frontend entrypoints are Rust-native",
            "Hosted frontend/browser workflow product entrypoints are Rust-native",
            "Frontend development-server orchestration is Rust-native",
            "Frontend production-delivery preview serving is Rust-native",
            "Playwright browser-install orchestration is Rust-native",
            "Phase 5 task-based browser-smoke orchestration is Rust-native",
            "Viewer, prototype, and Workbench v2 browser-smoke orchestration are Rust-native",
            "Viewer JavaScript syntax gate orchestration is Rust-native",
            "Viewer report PDF verification wrapper is Rust-native",
            "Viewer performance verifier is Rust-native",
            "Viewer visual-regression verifier is Rust-native",
            "removal remains forbidden",
            "`removal_allowed` and `c6_complete` stay false",
        ),
        blockers,
    )

    feature_rows = manifest.get("feature_matrix")
    feature_index = {
        row.get("feature"): row
        for row in feature_rows
        if isinstance(row, dict) and isinstance(row.get("feature"), str)
    } if isinstance(feature_rows, list) else {}
    if (
        not isinstance(feature_rows, list)
        or len(feature_index) != len(feature_rows)
        or set(feature_index) != set(EXPECTED_FEATURES)
    ):
        blockers.append("workbench_ui_feature_matrix_inventory_invalid")
    for feature, (native_status, removal_blocker) in EXPECTED_FEATURES.items():
        row = feature_index.get(feature)
        if (
            not isinstance(row, dict)
            or row.get("native_status") != native_status
            or row.get("removal_blocker") is not removal_blocker
        ):
            blockers.append(f"workbench_ui_feature_matrix_invalid:{feature}")

    prerequisites = manifest.get("c6_prerequisites")
    if not isinstance(prerequisites, dict) or set(prerequisites) != EXPECTED_PREREQUISITES:
        blockers.append("workbench_ui_c6_prerequisite_inventory_invalid")
        prerequisites = {}
    elif not all(isinstance(value, bool) for value in prerequisites.values()):
        blockers.append("workbench_ui_c6_prerequisite_type_invalid")
    c6_ready = (
        bool(prerequisites)
        and all(prerequisites.values())
        and not active_node_workflows
        and legacy.get("verification_authority_active") is False
        and legacy.get("rollback_archive_complete") is True
        and legacy.get("removal_allowed") is True
        and not any(
            isinstance(row, dict) and row.get("removal_blocker") is True
            for row in feature_index.values()
        )
    )
    if manifest.get("c6_complete") is not c6_ready:
        blockers.append("workbench_ui_c6_claim_not_derived_from_prerequisites")

    extension_claim = manifest.get("native_surface_extension_claim")
    expected_extension_claim = (
        "compatible frame3d element and truss3d material/section edits, truss3d "
        "section/member authoring, and one last-neutral-truss3d-leaf deletion"
    )
    if extension_claim != expected_extension_claim:
        blockers.append("workbench_ui_native_surface_extension_claim_invalid")
    claim = f"{manifest.get('claim_boundary', '')} {extension_claim or ''}"
    for token in (
        "direct Cargo entrypoints for hosted frontend/browser product commands with npm package-script entrypoints 0",
        "existing-linear-elastic-material parameter, existing-frame3d-section parameter, existing-frame3d-element orientation and existing-two-node-element connectivity edits, one connected linear frame3d node/member addition, one existing-pattern/existing-node linear-static nodal-load addition, and one homogeneous six-DOF fixed-constraint addition, one atomic zero-self-weight linear-static pattern with its first nonzero nodal load, one stateless linear-elastic-material addition composed into a referencing member, and one frame3d-section addition composed into a referencing member, all with native linear execution, plus C++-assembly-preflighted bounded ModelIR linear CPU request creation",
        "compatible frame3d element and truss3d material/section edits, truss3d section/member authoring, and one last-neutral-truss3d-leaf deletion",
        "active React/TypeScript/JavaScript, npm plus retained Node/TypeScript/Vite install, audit, build, development, syntax, browser installer, exporter, probe, and capture runtimes, npm registry/advisory/cache/lifecycle/configuration and node_modules or external-cache mutation, Playwright-owned downloads, caches, elevation and host-package mutation, Chromium/browser, optional pdftotext, the Python quality-gate sequence, and the native catalog/evidence Bash launcher conveniences visible",
        "does not authorize source deletion",
        "approved HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"workbench_ui_claim_boundary_missing:{token}")

    transition_blockers = [
        f"c6_prerequisite_open:{field}"
        for field, complete in sorted(prerequisites.items())
        if complete is False
    ]
    transition_blockers.extend(
        f"native_feature_open:{feature}"
        for feature, row in sorted(feature_index.items())
        if isinstance(row, dict) and row.get("removal_blocker") is True
    )
    if active_node_workflows:
        transition_blockers.append("active_node_verification_workflows_present")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-workbench-ui-transition-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "c6_ready": c6_ready,
        "removal_allowed": legacy.get("removal_allowed"),
        "source_inventory": actual_inventory,
        "active_node_workflows": active_node_workflows,
        "transition_blockers": sorted(set(transition_blockers)),
        "blockers": blockers,
        "claim_boundary": (
            "Contract pass means the active legacy authority and native replacement inventory are "
            "honest. It is not C6 readiness or permission to delete the legacy surface."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--require-c6", action="store_true")
    args = parser.parse_args()
    report = check_native_workbench_ui_transition(args.repo_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native Workbench UI transition contract: {report['status']}")
        print(f"C6 ready: {str(report['c6_ready']).lower()}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    if args.fail_blocked and not report["contract_pass"]:
        return 1
    return 2 if args.require_c6 and not report["c6_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
