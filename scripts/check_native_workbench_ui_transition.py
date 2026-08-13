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
    Path("native/crates/structural-workbench/tests/native_workbench_e2e.rs"),
    Path("native/crates/structural-catalog/src/lib.rs"),
    Path("native/crates/structural-catalog/tests/catalog_builder_product.rs"),
    Path("native/crates/structural-frontend-contract/src/lib.rs"),
    Path("native/crates/structural-frontend-contract/tests/frontend_contract_product.rs"),
    Path("native/crates/structural-evidence/src/lib.rs"),
    Path("native/crates/structural-evidence/tests/evidence_bundle_product.rs"),
    Path("native/catalog/benchmark-catalog-v2.json"),
    Path("native/catalog/benchmark-catalog-sources-v1.json"),
    Path("native/decommission/legacy-frontend-build-contract-v1.json"),
    Path("native/evidence/workbench-evidence-sources-v1.json"),
    Path("native/tests/fixtures/workbench_evidence/manifest.json"),
    Path("docs/native/benchmark-catalog-v1.md"),
    Path("docs/native/rust-native-workbench-v1.md"),
    Path("docs/native/workbench-ui-transition-v1.md"),
    Path("package.json"),
    Path("vite.config.ts"),
    Path("src/main.tsx"),
)
NODE_WORKFLOW_TOKENS = ("actions/setup-node@", "npm ci", "npm run")
EXPECTED_FEATURES = {
    "import_validate_run_resume_compare_report": ("c5_implemented", False),
    "deterministic_result_inspect_human_review_export": ("c5_implemented", False),
    "general_visual_model_editing_and_3d_result_exploration": ("open", True),
    "arbitrary_modelir_topology_and_solver_selection": ("open", True),
    "benchmark_and_evidence_catalog_browsing": ("c5_implemented", False),
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
    if native.get("operator_flow") != ["inspect", "review", "export"]:
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
        "structural-frontend-contract check"
    ]:
        blockers.append("workbench_ui_native_frontend_contract_flow_invalid")
    for field in (
        "runtime_python_required",
        "runtime_node_required",
        "runtime_browser_required",
        "human_review_inferred",
    ):
        if native.get(field) is not False:
            blockers.append(f"workbench_ui_native_false_boundary_invalid:{field}")

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
            "pub fn publish_review",
            "pub fn export_json",
            "automatically_inferred",
            "browse_embedded_benchmark_catalog",
            "browse_evidence_bundle",
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
            "pub fn check_frontend_contract",
            "decode_json_strict",
            "frontend_forbidden_path_present",
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
            'Some("review")',
            'Some("export")',
            'Some("catalog")',
            'Some("catalog-show")',
            'Some("evidence")',
            'Some("evidence-show")',
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
    transition_doc = _text(
        root, Path("docs/native/workbench-ui-transition-v1.md"), blockers
    )
    _require_tokens(
        Path("docs/native/workbench-ui-transition-v1.md"),
        transition_doc,
        (
            "not a C6 removal receipt",
            "never infers this decision",
            "seven active workflows",
            "catalog and copied-evidence browsing",
            "Rust-native evidence-bundle builder",
            "Rust-native benchmark-catalog builder",
            "Rust-native frontend build-contract checker",
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

    claim = str(manifest.get("claim_boundary", ""))
    for token in (
        "active React/TypeScript/JavaScript and Node verification dependency visible",
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
