#!/usr/bin/env python3
"""Fail closed on the bounded native deployment-authority cutover."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_CONTAINER = Path("deployment/onprem/Containerfile")
ACTIVE_COMPOSE = Path("deployment/onprem/compose.example.yml")
ACTIVE_README = Path("deployment/onprem/README.md")
ACTIVE_LICENSE = Path("deployment/onprem/offline-license.example.json")
ACTIVE_UPDATE = Path("deployment/onprem/signed-update-package.example.json")
CUTOVER_MANIFEST = Path("native/decommission/production-deployment-v1.json")
LEGACY_PAGES_WORKFLOW = Path("deployment/legacy-react-pages/deploy-pages.yml")
LEGACY_PAGES_README = Path("deployment/legacy-react-pages/README.md")
LEGACY_PYTHON_CONTAINER = Path("deployment/legacy-python-onprem/Containerfile")
LEGACY_PYTHON_README = Path("deployment/legacy-python-onprem/README.md")

REQUIRED_FILES = (
    Path(".dockerignore"),
    ACTIVE_CONTAINER,
    ACTIVE_COMPOSE,
    ACTIVE_README,
    ACTIVE_LICENSE,
    ACTIVE_UPDATE,
    CUTOVER_MANIFEST,
    LEGACY_PAGES_WORKFLOW,
    LEGACY_PAGES_README,
    LEGACY_PYTHON_CONTAINER,
    LEGACY_PYTHON_README,
    Path("deployment/legacy-python-onprem/compose.example.yml"),
    Path("deployment/legacy-python-onprem/offline-license.example.json"),
    Path("deployment/legacy-python-onprem/signed-update-package.example.json"),
    Path("scripts/build_native_distribution.sh"),
    Path("scripts/run_native_distribution_e2e.sh"),
    Path("scripts/check_native_distribution_receipt.py"),
    Path("scripts/run_native_rootfs_isolation_e2e.sh"),
    Path("scripts/build_onprem_deployment_packaging_manifest.py"),
    Path("native/capabilities.json"),
    Path("docs/native/deployment-cutover-v1.md"),
    Path("docs/native/distribution-lifecycle.md"),
    Path("docs/native/rust-native-workbench-v1.md"),
    Path("docs/native/modelir-model-identity-edit-v1.md"),
    Path("docs/native/modelir-node-identity-cascade-edit-v2.md"),
    Path("docs/native/modelir-truss3d-editing-v1.md"),
    Path("docs/native/modelir-frame3d-leaf-deletion-v1.md"),
    Path("docs/native/modelir-truss3d-leaf-deletion-v1.md"),
    Path("docs/native/modelir-truss-section-deletion-v1.md"),
    Path("docs/native/modelir-node-add-v1.md"),
    Path("docs/native/modelir-orphan-node-delete-v1.md"),
    Path("docs/native/modelir-linear-load-combination-add-v1.md"),
    Path("docs/native/modelir-linear-load-combination-deletion-v1.md"),
    Path("docs/native/modelir-direct-linear-load-combination-deletion-v1.md"),
    Path("docs/native/modelir-nested-linear-load-combination-deletion-v1.md"),
    Path("docs/native/modelir-nested-linear-load-combination-reference-edit-v1.md"),
    Path("docs/native/modelir-fixed-constraint-deletion-v1.md"),
    Path("docs/native/modelir-nodal-load-deletion-v1.md"),
    Path("docs/native/modelir-nodal-load-target-edit-v1.md"),
    Path("docs/native/modelir-constraint-target-edit-v1.md"),
    Path("docs/native/modelir-fixed-constraint-dof-deletion-v1.md"),
)


def _text(root: Path, relative: Path, blockers: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"deployment_evidence_unreadable:{relative.as_posix()}:{exc}")
        return ""


def _json_object(root: Path, relative: Path, blockers: list[str]) -> dict[str, Any]:
    text = _text(root, relative, blockers)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        blockers.append(f"deployment_json_invalid:{relative.as_posix()}:{exc}")
        return {}
    if not isinstance(payload, dict):
        blockers.append(f"deployment_json_not_object:{relative.as_posix()}")
        return {}
    return payload


def _require_tokens(
    *,
    relative: Path,
    text: str,
    tokens: tuple[str, ...],
    blockers: list[str],
) -> None:
    for token in tokens:
        if token not in text:
            blockers.append(
                f"deployment_token_missing:{relative.as_posix()}:{token}"
            )


def check_native_deployment_cutover(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            blockers.append(f"deployment_evidence_missing:{relative.as_posix()}")

    active_workflow_dir = root / ".github/workflows"
    active_workflows = sorted(
        [*active_workflow_dir.glob("*.yml"), *active_workflow_dir.glob("*.yaml")]
    ) if active_workflow_dir.is_dir() else []
    if (active_workflow_dir / "deploy-pages.yml").exists():
        blockers.append("legacy_pages_workflow_still_active")
    forbidden_pages_tokens = (
        "actions/deploy-pages@",
        "actions/upload-pages-artifact@",
        "pages: write",
    )
    for path in active_workflows:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in forbidden_pages_tokens:
            if token.lower() in text:
                blockers.append(
                    "active_pages_deployment_authority:"
                    f"{path.relative_to(root).as_posix()}:{token}"
                )

    container = _text(root, ACTIVE_CONTAINER, blockers)
    _require_tokens(
        relative=ACTIVE_CONTAINER,
        text=container,
        tokens=(
            "FROM rust:1.77-bookworm AS builder",
            "scripts/build_native_distribution.sh",
            "--backend cpu-only",
            "--linkage static",
            "FROM debian:bookworm-slim AS runtime",
            "COPY --from=builder --chown=65532:65532",
            "USER 65532:65532",
            'ENTRYPOINT ["/opt/structural/bin/structural-workbench"]',
        ),
        blockers=blockers,
    )
    lowered_container = container.lower()
    for token in (
        "from python",
        "from node",
        "npm ",
        "pip ",
        "project_ops_api_service.py",
        "expose ",
        'cmd ["python"',
        'cmd ["node"',
    ):
        if token in lowered_container:
            blockers.append(f"active_container_forbidden_runtime_token:{token}")
    if container.count("FROM ") != 2:
        blockers.append("active_container_stage_count_not_two")

    compose = _text(root, ACTIVE_COMPOSE, blockers)
    _require_tokens(
        relative=ACTIVE_COMPOSE,
        text=compose,
        tokens=(
            "workbench:",
            "network_mode: none",
            "read_only: true",
            "cap_drop:",
            "no-new-privileges:true",
            "/workspace",
            'command: ["--version"]',
        ),
        blockers=blockers,
    )
    lowered_compose = compose.lower()
    for token in ("ports:", "secrets:", "project_ops_", "python", "node", "npm", "pip"):
        if token in lowered_compose:
            blockers.append(f"active_compose_forbidden_runtime_token:{token}")

    readme = _text(root, ACTIVE_README, blockers)
    _require_tokens(
        relative=ACTIVE_README,
        text=readme,
        tokens=(
            "Import -> Validate -> Run -> Resume -> Compare -> Report",
            "Python, Node, React",
            "no listener, exposed port, secret, or network namespace",
            "structural-installer",
            "model-edit-model-identity",
            "model-edit-node",
            "model-add-node",
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
            "model-add-truss-section",
            "model-add-truss3d-member",
            "model-delete-frame3d-leaf-member",
            "model-delete-truss3d-leaf-member",
            "model-delete-fixed-constraint",
            "model-add-nodal-load",
            "model-delete-nodal-load",
            "model-delete-linear-load-pattern",
            "model-add-linear-load-combination",
            "model-add-linear-load-combination-term",
            "model-delete-linear-load-combination-term",
            "model-add-nested-linear-load-combination-term",
            "model-delete-nested-linear-load-combination-term",
            "model-reorder-nested-linear-load-combination-term",
            "model-edit-linear-load-combination-factor",
            "model-edit-linear-load-combination-reference",
            "model-edit-nested-linear-load-combination-factor",
            "model-edit-nested-linear-load-combination-reference",
            "installed v57 E2E",
            "installed v56 E2E",
            "installed v55 E2E",
            "installed v54 E2E",
            "installed v53 E2E",
            "installed v52 E2E",
            "installed v51 E2E",
            "installed v50 E2E",
            "model-add-nested-linear-load-combination",
            "model-delete-linear-load-combination",
            "depth-eight/64-leaf nested root",
            "model-delete-linear-material",
            "model-add-frame-section",
            "model-delete-frame-section",
            "model-delete-truss-section",
            "model-create-linear-analysis-request",
            "customer-approved image build",
            "not final C6",
        ),
        blockers=blockers,
    )

    cutover_doc = _text(root, Path("docs/native/deployment-cutover-v1.md"), blockers)
    _require_tokens(
        relative=Path("docs/native/deployment-cutover-v1.md"),
        text=cutover_doc,
        tokens=(
            "Import -> Validate -> Run -> Resume -> Compare -> Report",
            "Distribution E2E v76",
            "model-edit-node-identity-cascade",
            "N2_LINKED",
            "Distribution E2E v75",
            "model-edit-model-identity",
            "engine-v2-frame-cantilever-renamed",
            "Distribution E2E v74",
            "model-edit-linear-load-combination-identity",
            "COMBO_RENAMED",
            "Distribution E2E v73",
            "model-edit-element-identity",
            "E1_RENAMED",
            "Distribution E2E v72",
            "model-edit-node-identity",
            "N3_RENAMED",
            "Distribution E2E v71",
            "model-edit-truss-section-identity",
            "T2_RENAMED",
            "Distribution E2E v70",
            "model-edit-frame-section-identity",
            "S2_RENAMED",
            "Distribution E2E v69",
            "model-edit-linear-material-identity",
            "M2_RENAMED",
            "Distribution E2E v68",
            "model-edit-linear-load-pattern-identity",
            "LC_WEAK_RENAMED",
            "Distribution E2E v67",
            "model-edit-nodal-load-identity",
            "L_WEAK_N3_RENAMED",
            "Distribution E2E v66",
            "model-edit-fixed-constraint-identity",
            "BC_N3_RENAMED",
            "Distribution E2E v65",
            "model-reorder-fixed-constraint-dof",
            "Distribution E2E v64",
            "model-add-fixed-constraint-dof",
            "Distribution E2E v63",
            "model-delete-fixed-constraint-dof",
            "[11,12,13,14,15,16,17]",
            "[0,0,-1000,0,0,0,0]",
            "Distribution E2E v62",
            "model-edit-constraint-target",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "Distribution E2E v61",
            "model-edit-nodal-load-target",
            "[0,0,0,0,0,0,0,-10000,0,0,0,0]",
            "Distribution E2E v60",
            "model-insert-nested-linear-load-combination-term",
            "[COMBO_SERVICE,LC_STRONG,LC_AXIAL]",
            "Distribution E2E v59",
            "model-insert-linear-load-combination-term",
            "[LC_WEAK,LC_AXIAL,LC_STRONG]",
            "Distribution E2E v58",
            "model-reorder-linear-load-combination-term",
            "Distribution E2E v57",
            "model-reorder-nested-linear-load-combination-term",
            "Distribution E2E v56",
            "model-delete-nested-linear-load-combination-term",
            "[0,-6000,1500,0,0,0]",
            "Distribution E2E v55",
            "model-add-nested-linear-load-combination-term",
            "[25000,-6000,1500,0,0,0]",
            "Distribution E2E v54",
            "model-delete-linear-load-combination-term",
            "[25000,-12000,0,0,0,0]",
            "Distribution E2E v53",
            "model-add-linear-load-combination-term",
            "[25000,-12000,5000,0,0,0]",
            "model-edit-nested-linear-load-combination-reference",
            "[0,-8000,2000,0,0,0]",
            "model-edit-linear-load-combination-reference",
            "[120000,0,5000,0,0,0]",
            "model-edit-linear-load-combination-factor",
            "[25000,-13500,5000,0,0,0]",
            "model-edit-nested-linear-load-combination-factor",
            "[25000,-9000,3750,0,0,0]",
            "model-add-nested-linear-load-combination",
            "last-neutral two-through-64 direct linear-load-combination deletion",
            "last-neutral bounded acyclic nested linear-load-combination deletion",
            "can no longer receive Pages write authority",
            "release-authorized build",
            "legacy release publication and branch-writing workflows are archived",
            "final C6",
        ),
        blockers=blockers,
    )

    dockerignore = _text(root, Path(".dockerignore"), blockers)
    _require_tokens(
        relative=Path(".dockerignore"),
        text=dockerignore,
        tokens=(".git", ".env", "**/target", "node_modules", ".betelgeuze"),
        blockers=blockers,
    )

    license_payload = _json_object(root, ACTIVE_LICENSE, blockers)
    if license_payload.get("schema_version") != "native-offline-license-file.example.v1":
        blockers.append("native_offline_license_schema_invalid")
    features = license_payload.get("features")
    required_features = {
        "native_workbench",
        "native_distribution_lifecycle",
        "native_report",
        "mgt_import_health",
    }
    if not isinstance(features, list) or set(features) != required_features:
        blockers.append("native_offline_license_features_invalid")
    if license_payload.get("signature") != "replace-with-production-signature":
        blockers.append("native_offline_license_placeholder_invalid")

    update_payload = _json_object(root, ACTIVE_UPDATE, blockers)
    if update_payload.get("schema_version") != "native-signed-update-package.example.v1":
        blockers.append("native_signed_update_schema_invalid")
    if update_payload.get("network_policy") != "offline_transfer_only":
        blockers.append("native_signed_update_network_policy_invalid")
    artifacts = update_payload.get("artifacts")
    labels = {
        str(row.get("label", ""))
        for row in artifacts
        if isinstance(row, dict)
    } if isinstance(artifacts, list) else set()
    if labels != {"native_cpu_static_bundle", "native_distribution_e2e_receipt"}:
        blockers.append("native_signed_update_artifacts_invalid")
    rollback = update_payload.get("rollback")
    if not isinstance(rollback, dict) or "structural-installer rollback" not in str(
        rollback.get("policy", "")
    ):
        blockers.append("native_signed_update_rollback_invalid")

    archived_pages = _text(root, LEGACY_PAGES_WORKFLOW, blockers)
    _require_tokens(
        relative=LEGACY_PAGES_WORKFLOW,
        text=archived_pages,
        tokens=("ARCHIVED - Deploy Workbench", "actions/setup-node@", "actions/deploy-pages@"),
        blockers=blockers,
    )
    archived_pages_readme = _text(root, LEGACY_PAGES_README, blockers)
    _require_tokens(
        relative=LEGACY_PAGES_README,
        text=archived_pages_readme,
        tokens=("rollback and deprecation evidence", "cannot dispatch", "Removal remains disallowed"),
        blockers=blockers,
    )
    archived_python = _text(root, LEGACY_PYTHON_CONTAINER, blockers)
    _require_tokens(
        relative=LEGACY_PYTHON_CONTAINER,
        text=archived_python,
        tokens=("rollback-only Python", "FROM python:3.10-slim", "project_ops_api_service.py"),
        blockers=blockers,
    )
    archived_python_readme = _text(root, LEGACY_PYTHON_README, blockers)
    _require_tokens(
        relative=LEGACY_PYTHON_README,
        text=archived_python_readme,
        tokens=("rollback-only compatibility evidence", "deployment/onprem"),
        blockers=blockers,
    )
    legacy_builder = _text(
        root, Path("scripts/build_onprem_deployment_packaging_manifest.py"), blockers
    )
    if 'DEFAULT_PACKAGING_DIR = Path("deployment/legacy-python-onprem")' not in legacy_builder:
        blockers.append("legacy_onprem_manifest_builder_not_archived")

    build_distribution = _text(
        root, Path("scripts/build_native_distribution.sh"), blockers
    )
    distribution_e2e = _text(
        root, Path("scripts/run_native_distribution_e2e.sh"), blockers
    )
    rootfs_e2e = _text(
        root, Path("scripts/run_native_rootfs_isolation_e2e.sh"), blockers
    )
    for token in (
        "structural-workbench",
        "structural-catalog",
        "structural-evidence",
        "structural-installer",
        "cpu-only",
        "static",
        "rocm_runtime_rpath",
        "libamdhip64.so",
        "-DCMAKE_INSTALL_RPATH=$install_rpath",
    ):
        if token not in build_distribution:
            blockers.append(f"native_distribution_build_token_missing:{token}")
    for token in (
        "PATH=\"$empty_path\"",
        "workbench_restart_passed",
        "python_lookup_count",
        "node_lookup_count",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
        "structural-native-distribution-e2e.v45",
        "structural-native-distribution-e2e.v46",
        "structural-native-distribution-e2e.v47",
        "structural-native-distribution-e2e.v48",
        "structural-native-distribution-e2e.v49",
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
        "structural-native-distribution-e2e.v57",
        "exercise_node_add_surface",
        "model-add-node",
        "workbench_node_add_surface_passed",
        "workbench_node_add_model_sha256",
        "workbench_node_add_receipt_sha256",
        "workbench_node_add_composed_model_sha256",
        "workbench_node_add_request_sha256",
        "workbench_node_add_result_ir_sha256",
        "workbench_node_add_recovery_sha256",
        "exercise_orphan_node_delete_surface",
        "model-delete-orphan-node",
        "workbench_orphan_node_delete_surface_passed",
        "workbench_orphan_node_delete_model_sha256",
        "workbench_orphan_node_delete_receipt_sha256",
        "workbench_orphan_node_delete_request_sha256",
        "workbench_orphan_node_delete_result_ir_sha256",
        "workbench_orphan_node_delete_recovery_sha256",
        "exercise_linear_load_combination_add_surface",
        "model-add-linear-load-combination",
        "workbench_linear_load_combination_add_surface_passed",
        "workbench_linear_load_combination_add_model_sha256",
        "workbench_linear_load_combination_add_receipt_sha256",
        "workbench_linear_load_combination_add_validation_sha256",
        "workbench_linear_load_combination_add_view_sha256",
        "workbench_linear_load_combination_add_solver_rejection_sha256",
        "--load-combination COMBO_SERVICE",
        "structural-native-model-linear-combination-request-create-receipt.v1",
        "workbench_linear_load_combination_execution_surface_passed",
        "workbench_linear_load_combination_request_receipt_sha256",
        "workbench_linear_load_combination_request_sha256",
        "workbench_linear_load_combination_assembly_receipt_sha256",
        "workbench_linear_load_combination_checkpoint_sha256",
        "workbench_linear_load_combination_result_ir_sha256",
        "workbench_linear_load_combination_recovery_sha256",
        "workbench_linear_load_combination_report_ir_sha256",
        "workbench_linear_load_combination_restart_passed",
        "exercise_direct_linear_load_combination_surface",
        "structural-native-model-linear-direct-combination-request-create-receipt.v2",
        "workbench_direct_linear_load_combination_surface_passed",
        "workbench_direct_linear_load_combination_model_sha256",
        "workbench_direct_linear_load_combination_edit_receipt_sha256",
        "workbench_direct_linear_load_combination_request_receipt_sha256",
        "workbench_direct_linear_load_combination_request_sha256",
        "workbench_direct_linear_load_combination_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_checkpoint_sha256",
        "workbench_direct_linear_load_combination_result_ir_sha256",
        "workbench_direct_linear_load_combination_recovery_sha256",
        "workbench_direct_linear_load_combination_report_ir_sha256",
        "workbench_direct_linear_load_combination_restart_passed",
        "exercise_direct_linear_load_combination_factor_edit_surface",
        "model-edit-linear-load-combination-factor",
        "structural-native:model-edit-direct-linear-load-combination-factor.v1",
        "workbench_direct_linear_load_combination_factor_edit_surface_passed",
        "workbench_direct_linear_load_combination_factor_edit_model_sha256",
        "workbench_direct_linear_load_combination_factor_edit_receipt_sha256",
        "workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256",
        "workbench_direct_linear_load_combination_factor_edit_request_sha256",
        "workbench_direct_linear_load_combination_factor_edit_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_factor_edit_checkpoint_sha256",
        "workbench_direct_linear_load_combination_factor_edit_result_ir_sha256",
        "workbench_direct_linear_load_combination_factor_edit_recovery_sha256",
        "workbench_direct_linear_load_combination_factor_edit_report_ir_sha256",
        "workbench_direct_linear_load_combination_factor_edit_restart_passed",
        "exercise_nested_linear_load_combination_factor_edit_surface",
        "model-edit-nested-linear-load-combination-factor",
        "structural-native:model-edit-nested-linear-load-combination-factor.v1",
        "workbench_nested_linear_load_combination_factor_edit_surface_passed",
        "workbench_nested_linear_load_combination_factor_edit_model_sha256",
        "workbench_nested_linear_load_combination_factor_edit_receipt_sha256",
        "workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256",
        "workbench_nested_linear_load_combination_factor_edit_request_sha256",
        "workbench_nested_linear_load_combination_factor_edit_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_factor_edit_checkpoint_sha256",
        "workbench_nested_linear_load_combination_factor_edit_result_ir_sha256",
        "workbench_nested_linear_load_combination_factor_edit_recovery_sha256",
        "workbench_nested_linear_load_combination_factor_edit_report_ir_sha256",
        "workbench_nested_linear_load_combination_factor_edit_restart_passed",
        "exercise_direct_linear_load_combination_reference_edit_surface",
        "model-edit-linear-load-combination-reference",
        "structural-native:model-edit-direct-linear-load-combination-reference.v1",
        "workbench_direct_linear_load_combination_reference_edit_surface_passed",
        "workbench_direct_linear_load_combination_reference_edit_model_sha256",
        "workbench_direct_linear_load_combination_reference_edit_receipt_sha256",
        "workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256",
        "workbench_direct_linear_load_combination_reference_edit_request_sha256",
        "workbench_direct_linear_load_combination_reference_edit_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_reference_edit_checkpoint_sha256",
        "workbench_direct_linear_load_combination_reference_edit_result_ir_sha256",
        "workbench_direct_linear_load_combination_reference_edit_recovery_sha256",
        "workbench_direct_linear_load_combination_reference_edit_report_ir_sha256",
        "workbench_direct_linear_load_combination_reference_edit_restart_passed",
        "exercise_nested_linear_load_combination_reference_edit_surface",
        "model-edit-nested-linear-load-combination-reference",
        "structural-native:model-edit-nested-linear-load-combination-reference.v1",
        "workbench_nested_linear_load_combination_reference_edit_surface_passed",
        "workbench_nested_linear_load_combination_reference_edit_model_sha256",
        "workbench_nested_linear_load_combination_reference_edit_receipt_sha256",
        "workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256",
        "workbench_nested_linear_load_combination_reference_edit_request_sha256",
        "workbench_nested_linear_load_combination_reference_edit_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_reference_edit_checkpoint_sha256",
        "workbench_nested_linear_load_combination_reference_edit_result_ir_sha256",
        "workbench_nested_linear_load_combination_reference_edit_recovery_sha256",
        "workbench_nested_linear_load_combination_reference_edit_report_ir_sha256",
        "workbench_nested_linear_load_combination_reference_edit_restart_passed",
        "exercise_direct_linear_load_combination_term_add_surface",
        "model-add-linear-load-combination-term",
        "structural-native:model-add-direct-linear-load-combination-term.v1",
        "workbench_direct_linear_load_combination_term_add_surface_passed",
        "workbench_direct_linear_load_combination_term_add_model_sha256",
        "workbench_direct_linear_load_combination_term_add_receipt_sha256",
        "workbench_direct_linear_load_combination_term_add_request_receipt_sha256",
        "workbench_direct_linear_load_combination_term_add_request_sha256",
        "workbench_direct_linear_load_combination_term_add_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_term_add_checkpoint_sha256",
        "workbench_direct_linear_load_combination_term_add_result_ir_sha256",
        "workbench_direct_linear_load_combination_term_add_recovery_sha256",
        "workbench_direct_linear_load_combination_term_add_report_ir_sha256",
        "workbench_direct_linear_load_combination_term_add_restart_passed",
        "exercise_direct_linear_load_combination_term_delete_surface",
        "model-delete-linear-load-combination-term",
        "structural-native:model-delete-direct-linear-load-combination-term.v1",
        "workbench_direct_linear_load_combination_term_delete_surface_passed",
        "workbench_direct_linear_load_combination_term_delete_model_sha256",
        "workbench_direct_linear_load_combination_term_delete_receipt_sha256",
        "workbench_direct_linear_load_combination_term_delete_request_receipt_sha256",
        "workbench_direct_linear_load_combination_term_delete_request_sha256",
        "workbench_direct_linear_load_combination_term_delete_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_term_delete_checkpoint_sha256",
        "workbench_direct_linear_load_combination_term_delete_result_ir_sha256",
        "workbench_direct_linear_load_combination_term_delete_recovery_sha256",
        "workbench_direct_linear_load_combination_term_delete_report_ir_sha256",
        "workbench_direct_linear_load_combination_term_delete_restart_passed",
        "exercise_direct_linear_load_combination_term_reorder_surface",
        "model-reorder-linear-load-combination-term",
        "structural-native:model-reorder-direct-linear-load-combination-term.v1",
        "workbench_direct_linear_load_combination_term_reorder_surface_passed",
        "workbench_direct_linear_load_combination_term_reorder_model_sha256",
        "workbench_direct_linear_load_combination_term_reorder_receipt_sha256",
        "workbench_direct_linear_load_combination_term_reorder_request_receipt_sha256",
        "workbench_direct_linear_load_combination_term_reorder_request_sha256",
        "workbench_direct_linear_load_combination_term_reorder_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_term_reorder_checkpoint_sha256",
        "workbench_direct_linear_load_combination_term_reorder_result_ir_sha256",
        "workbench_direct_linear_load_combination_term_reorder_recovery_sha256",
        "workbench_direct_linear_load_combination_term_reorder_report_ir_sha256",
        "workbench_direct_linear_load_combination_term_reorder_restart_passed",
        "exercise_direct_linear_load_combination_term_insert_surface",
        "model-insert-linear-load-combination-term",
        "structural-native:model-insert-direct-linear-load-combination-term.v1",
        "workbench_direct_linear_load_combination_term_insert_surface_passed",
        "workbench_direct_linear_load_combination_term_insert_model_sha256",
        "workbench_direct_linear_load_combination_term_insert_receipt_sha256",
        "workbench_direct_linear_load_combination_term_insert_request_receipt_sha256",
        "workbench_direct_linear_load_combination_term_insert_request_sha256",
        "workbench_direct_linear_load_combination_term_insert_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_term_insert_checkpoint_sha256",
        "workbench_direct_linear_load_combination_term_insert_result_ir_sha256",
        "workbench_direct_linear_load_combination_term_insert_recovery_sha256",
        "workbench_direct_linear_load_combination_term_insert_report_ir_sha256",
        "workbench_direct_linear_load_combination_term_insert_restart_passed",
        "exercise_nested_linear_load_combination_term_add_surface",
        "model-add-nested-linear-load-combination-term",
        "structural-native:model-add-nested-linear-load-combination-term.v1",
        "workbench_nested_linear_load_combination_term_add_surface_passed",
        "workbench_nested_linear_load_combination_term_add_model_sha256",
        "workbench_nested_linear_load_combination_term_add_receipt_sha256",
        "workbench_nested_linear_load_combination_term_add_request_receipt_sha256",
        "workbench_nested_linear_load_combination_term_add_request_sha256",
        "workbench_nested_linear_load_combination_term_add_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_term_add_checkpoint_sha256",
        "workbench_nested_linear_load_combination_term_add_result_ir_sha256",
        "workbench_nested_linear_load_combination_term_add_recovery_sha256",
        "workbench_nested_linear_load_combination_term_add_report_ir_sha256",
        "workbench_nested_linear_load_combination_term_add_restart_passed",
        "exercise_nested_linear_load_combination_term_insert_surface",
        "model-insert-nested-linear-load-combination-term",
        "structural-native:model-insert-nested-linear-load-combination-term.v1",
        "workbench_nested_linear_load_combination_term_insert_surface_passed",
        "workbench_nested_linear_load_combination_term_insert_model_sha256",
        "workbench_nested_linear_load_combination_term_insert_receipt_sha256",
        "workbench_nested_linear_load_combination_term_insert_request_receipt_sha256",
        "workbench_nested_linear_load_combination_term_insert_request_sha256",
        "workbench_nested_linear_load_combination_term_insert_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_term_insert_checkpoint_sha256",
        "workbench_nested_linear_load_combination_term_insert_result_ir_sha256",
        "workbench_nested_linear_load_combination_term_insert_recovery_sha256",
        "workbench_nested_linear_load_combination_term_insert_report_ir_sha256",
        "workbench_nested_linear_load_combination_term_insert_restart_passed",
        "exercise_nested_linear_load_combination_term_delete_surface",
        "model-delete-nested-linear-load-combination-term",
        "structural-native:model-delete-nested-linear-load-combination-term.v1",
        "workbench_nested_linear_load_combination_term_delete_surface_passed",
        "workbench_nested_linear_load_combination_term_delete_model_sha256",
        "workbench_nested_linear_load_combination_term_delete_receipt_sha256",
        "workbench_nested_linear_load_combination_term_delete_request_receipt_sha256",
        "workbench_nested_linear_load_combination_term_delete_request_sha256",
        "workbench_nested_linear_load_combination_term_delete_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_term_delete_checkpoint_sha256",
        "workbench_nested_linear_load_combination_term_delete_result_ir_sha256",
        "workbench_nested_linear_load_combination_term_delete_recovery_sha256",
        "workbench_nested_linear_load_combination_term_delete_report_ir_sha256",
        "workbench_nested_linear_load_combination_term_delete_restart_passed",
        "exercise_nested_linear_load_combination_term_reorder_surface",
        "model-reorder-nested-linear-load-combination-term",
        "structural-native:model-reorder-nested-linear-load-combination-term.v1",
        "workbench_nested_linear_load_combination_term_reorder_surface_passed",
        "workbench_nested_linear_load_combination_term_reorder_model_sha256",
        "workbench_nested_linear_load_combination_term_reorder_receipt_sha256",
        "workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256",
        "workbench_nested_linear_load_combination_term_reorder_request_sha256",
        "workbench_nested_linear_load_combination_term_reorder_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_term_reorder_checkpoint_sha256",
        "workbench_nested_linear_load_combination_term_reorder_result_ir_sha256",
        "workbench_nested_linear_load_combination_term_reorder_recovery_sha256",
        "workbench_nested_linear_load_combination_term_reorder_report_ir_sha256",
        "workbench_nested_linear_load_combination_term_reorder_restart_passed",
        "exercise_nested_linear_load_combination_surface",
        "model-add-nested-linear-load-combination",
        "structural-native-model-linear-nested-combination-request-create-receipt.v3",
        "workbench_nested_linear_load_combination_surface_passed",
        "workbench_nested_linear_load_combination_model_sha256",
        "workbench_nested_linear_load_combination_edit_receipt_sha256",
        "workbench_nested_linear_load_combination_request_receipt_sha256",
        "workbench_nested_linear_load_combination_request_sha256",
        "workbench_nested_linear_load_combination_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_checkpoint_sha256",
        "workbench_nested_linear_load_combination_result_ir_sha256",
        "workbench_nested_linear_load_combination_recovery_sha256",
        "workbench_nested_linear_load_combination_report_ir_sha256",
        "workbench_nested_linear_load_combination_restart_passed",
        "exercise_direct_linear_load_combination_delete_surface",
        "structural-native:model-delete-direct-linear-load-combination.v2",
        "workbench_direct_linear_load_combination_delete_surface_passed",
        "workbench_direct_linear_load_combination_delete_model_sha256",
        "workbench_direct_linear_load_combination_delete_receipt_sha256",
        "workbench_direct_linear_load_combination_delete_request_sha256",
        "workbench_direct_linear_load_combination_delete_assembly_receipt_sha256",
        "workbench_direct_linear_load_combination_delete_checkpoint_sha256",
        "workbench_direct_linear_load_combination_delete_result_ir_sha256",
        "workbench_direct_linear_load_combination_delete_recovery_sha256",
        "workbench_direct_linear_load_combination_delete_report_ir_sha256",
        "workbench_direct_linear_load_combination_delete_restart_passed",
        "exercise_nested_linear_load_combination_delete_surface",
        "structural-native:model-delete-nested-linear-load-combination.v3",
        "workbench_nested_linear_load_combination_delete_surface_passed",
        "workbench_nested_linear_load_combination_delete_model_sha256",
        "workbench_nested_linear_load_combination_delete_receipt_sha256",
        "workbench_nested_linear_load_combination_delete_request_receipt_sha256",
        "workbench_nested_linear_load_combination_delete_request_sha256",
        "workbench_nested_linear_load_combination_delete_assembly_receipt_sha256",
        "workbench_nested_linear_load_combination_delete_checkpoint_sha256",
        "workbench_nested_linear_load_combination_delete_result_ir_sha256",
        "workbench_nested_linear_load_combination_delete_recovery_sha256",
        "workbench_nested_linear_load_combination_delete_report_ir_sha256",
        "workbench_nested_linear_load_combination_delete_restart_passed",
        "exercise_linear_load_combination_delete_surface",
        "model-delete-linear-load-combination",
        "workbench_linear_load_combination_delete_surface_passed",
        "workbench_linear_load_combination_delete_model_sha256",
        "workbench_linear_load_combination_delete_receipt_sha256",
        "workbench_linear_load_combination_delete_request_sha256",
        "workbench_linear_load_combination_delete_result_ir_sha256",
        "workbench_linear_load_combination_delete_recovery_sha256",
        "exercise_nodal_load_edit_surface",
        "workbench_nodal_load_edit_surface_passed",
        "workbench_nodal_load_edit_receipt_sha256",
        "exercise_constraint_value_edit_surface",
        "workbench_constraint_value_edit_surface_passed",
        "workbench_constraint_value_edit_receipt_sha256",
        "exercise_linear_material_edit_surface",
        "workbench_linear_material_edit_surface_passed",
        "workbench_linear_material_edit_receipt_sha256",
        "exercise_frame_section_edit_surface",
        "workbench_frame_section_edit_surface_passed",
        "workbench_frame_section_edit_receipt_sha256",
        "exercise_frame_element_orientation_edit_surface",
        "workbench_frame_element_orientation_edit_surface_passed",
        "workbench_frame_element_orientation_edit_receipt_sha256",
        "exercise_element_connectivity_edit_surface",
        "workbench_element_connectivity_edit_surface_passed",
        "workbench_element_connectivity_edit_receipt_sha256",
        "exercise_frame3d_member_add_surface",
        "model-add-frame3d-member",
        "workbench_frame3d_member_add_surface_passed",
        "workbench_frame3d_member_add_model_sha256",
        "workbench_frame3d_member_add_receipt_sha256",
        "workbench_frame3d_member_add_request_sha256",
        "workbench_frame3d_member_add_result_ir_sha256",
        "exercise_nodal_load_target_edit_surface",
        "model-edit-nodal-load-target",
        "structural-native:model-edit-nodal-load-target.v1",
        "workbench_nodal_load_target_edit_surface_passed",
        "workbench_nodal_load_target_edit_model_sha256",
        "workbench_nodal_load_target_edit_receipt_sha256",
        "workbench_nodal_load_target_edit_request_receipt_sha256",
        "workbench_nodal_load_target_edit_request_sha256",
        "workbench_nodal_load_target_edit_assembly_receipt_sha256",
        "workbench_nodal_load_target_edit_checkpoint_sha256",
        "workbench_nodal_load_target_edit_result_ir_sha256",
        "workbench_nodal_load_target_edit_recovery_sha256",
        "workbench_nodal_load_target_edit_report_ir_sha256",
        "workbench_nodal_load_target_edit_restart_passed",
        "exercise_constraint_target_edit_surface",
        "model-edit-constraint-target",
        "structural-native:model-edit-constraint-target.v1",
        "workbench_constraint_target_edit_surface_passed",
        "workbench_constraint_target_edit_model_sha256",
        "workbench_constraint_target_edit_receipt_sha256",
        "workbench_constraint_target_edit_request_receipt_sha256",
        "workbench_constraint_target_edit_request_sha256",
        "workbench_constraint_target_edit_assembly_receipt_sha256",
        "workbench_constraint_target_edit_checkpoint_sha256",
        "workbench_constraint_target_edit_result_ir_sha256",
        "workbench_constraint_target_edit_recovery_sha256",
        "workbench_constraint_target_edit_report_ir_sha256",
        "workbench_constraint_target_edit_restart_passed",
        "exercise_fixed_constraint_dof_delete_surface",
        "model-delete-fixed-constraint-dof",
        "structural-native:model-delete-fixed-constraint-dof.v1",
        "workbench_fixed_constraint_dof_delete_surface_passed",
        "workbench_fixed_constraint_dof_delete_model_sha256",
        "workbench_fixed_constraint_dof_delete_receipt_sha256",
        "workbench_fixed_constraint_dof_delete_request_receipt_sha256",
        "workbench_fixed_constraint_dof_delete_request_sha256",
        "workbench_fixed_constraint_dof_delete_assembly_receipt_sha256",
        "workbench_fixed_constraint_dof_delete_checkpoint_sha256",
        "workbench_fixed_constraint_dof_delete_result_ir_sha256",
        "workbench_fixed_constraint_dof_delete_recovery_sha256",
        "workbench_fixed_constraint_dof_delete_report_ir_sha256",
        "workbench_fixed_constraint_dof_delete_restart_passed",
        "exercise_fixed_constraint_dof_add_surface",
        "model-add-fixed-constraint-dof",
        "structural-native:model-add-fixed-constraint-dof.v1",
        "workbench_fixed_constraint_dof_add_surface_passed",
        "workbench_fixed_constraint_dof_add_model_sha256",
        "workbench_fixed_constraint_dof_add_receipt_sha256",
        "workbench_fixed_constraint_dof_add_request_receipt_sha256",
        "workbench_fixed_constraint_dof_add_request_sha256",
        "workbench_fixed_constraint_dof_add_assembly_receipt_sha256",
        "workbench_fixed_constraint_dof_add_checkpoint_sha256",
        "workbench_fixed_constraint_dof_add_result_ir_sha256",
        "workbench_fixed_constraint_dof_add_recovery_sha256",
        "workbench_fixed_constraint_dof_add_report_ir_sha256",
        "workbench_fixed_constraint_dof_add_restart_passed",
        "exercise_fixed_constraint_dof_reorder_surface",
        "model-reorder-fixed-constraint-dof",
        "structural-native:model-reorder-fixed-constraint-dof.v1",
        "workbench_fixed_constraint_dof_reorder_surface_passed",
        "workbench_fixed_constraint_dof_reorder_model_sha256",
        "workbench_fixed_constraint_dof_reorder_receipt_sha256",
        "workbench_fixed_constraint_dof_reorder_request_receipt_sha256",
        "workbench_fixed_constraint_dof_reorder_request_sha256",
        "workbench_fixed_constraint_dof_reorder_assembly_receipt_sha256",
        "workbench_fixed_constraint_dof_reorder_checkpoint_sha256",
        "workbench_fixed_constraint_dof_reorder_result_ir_sha256",
        "workbench_fixed_constraint_dof_reorder_recovery_sha256",
        "workbench_fixed_constraint_dof_reorder_report_ir_sha256",
        "workbench_fixed_constraint_dof_reorder_restart_passed",
        "exercise_fixed_constraint_identity_edit_surface",
        "model-edit-fixed-constraint-identity",
        "structural-native:model-edit-fixed-constraint-identity.v1",
        "workbench_fixed_constraint_identity_edit_surface_passed",
        "workbench_fixed_constraint_identity_edit_model_sha256",
        "workbench_fixed_constraint_identity_edit_receipt_sha256",
        "workbench_fixed_constraint_identity_edit_request_receipt_sha256",
        "workbench_fixed_constraint_identity_edit_request_sha256",
        "workbench_fixed_constraint_identity_edit_assembly_receipt_sha256",
        "workbench_fixed_constraint_identity_edit_checkpoint_sha256",
        "workbench_fixed_constraint_identity_edit_result_ir_sha256",
        "workbench_fixed_constraint_identity_edit_recovery_sha256",
        "workbench_fixed_constraint_identity_edit_report_ir_sha256",
        "workbench_fixed_constraint_identity_edit_restart_passed",
        "exercise_nodal_load_identity_edit_surface",
        "model-edit-nodal-load-identity",
        "structural-native:model-edit-nodal-load-identity.v1",
        "workbench_nodal_load_identity_edit_surface_passed",
        "workbench_nodal_load_identity_edit_model_sha256",
        "workbench_nodal_load_identity_edit_receipt_sha256",
        "workbench_nodal_load_identity_edit_request_receipt_sha256",
        "workbench_nodal_load_identity_edit_request_sha256",
        "workbench_nodal_load_identity_edit_assembly_receipt_sha256",
        "workbench_nodal_load_identity_edit_checkpoint_sha256",
        "workbench_nodal_load_identity_edit_result_ir_sha256",
        "workbench_nodal_load_identity_edit_recovery_sha256",
        "workbench_nodal_load_identity_edit_report_ir_sha256",
        "workbench_nodal_load_identity_edit_restart_passed",
        "exercise_linear_load_pattern_identity_edit_surface",
        "model-edit-linear-load-pattern-identity",
        "structural-native:model-edit-linear-load-pattern-identity.v1",
        "workbench_linear_load_pattern_identity_edit_surface_passed",
        "workbench_linear_load_pattern_identity_edit_model_sha256",
        "workbench_linear_load_pattern_identity_edit_receipt_sha256",
        "workbench_linear_load_pattern_identity_edit_request_receipt_sha256",
        "workbench_linear_load_pattern_identity_edit_request_sha256",
        "workbench_linear_load_pattern_identity_edit_assembly_receipt_sha256",
        "workbench_linear_load_pattern_identity_edit_checkpoint_sha256",
        "workbench_linear_load_pattern_identity_edit_result_ir_sha256",
        "workbench_linear_load_pattern_identity_edit_recovery_sha256",
        "workbench_linear_load_pattern_identity_edit_report_ir_sha256",
        "workbench_linear_load_pattern_identity_edit_restart_passed",
        "exercise_linear_material_identity_edit_surface",
        "model-edit-linear-material-identity",
        "structural-native:model-edit-linear-material-identity.v1",
        "workbench_linear_material_identity_edit_surface_passed",
        "workbench_linear_material_identity_edit_model_sha256",
        "workbench_linear_material_identity_edit_receipt_sha256",
        "workbench_linear_material_identity_edit_request_receipt_sha256",
        "workbench_linear_material_identity_edit_request_sha256",
        "workbench_linear_material_identity_edit_assembly_receipt_sha256",
        "workbench_linear_material_identity_edit_checkpoint_sha256",
        "workbench_linear_material_identity_edit_result_ir_sha256",
        "workbench_linear_material_identity_edit_recovery_sha256",
        "workbench_linear_material_identity_edit_report_ir_sha256",
        "workbench_linear_material_identity_edit_restart_passed",
        "exercise_frame_section_identity_edit_surface",
        "model-edit-frame-section-identity",
        "structural-native:model-edit-frame-section-identity.v1",
        "workbench_frame_section_identity_edit_surface_passed",
        "workbench_frame_section_identity_edit_model_sha256",
        "workbench_frame_section_identity_edit_receipt_sha256",
        "workbench_frame_section_identity_edit_request_receipt_sha256",
        "workbench_frame_section_identity_edit_request_sha256",
        "workbench_frame_section_identity_edit_assembly_receipt_sha256",
        "workbench_frame_section_identity_edit_checkpoint_sha256",
        "workbench_frame_section_identity_edit_result_ir_sha256",
        "workbench_frame_section_identity_edit_recovery_sha256",
        "workbench_frame_section_identity_edit_report_ir_sha256",
        "workbench_frame_section_identity_edit_restart_passed",
        "exercise_truss_section_identity_edit_surface",
        "model-edit-truss-section-identity",
        "structural-native:model-edit-truss-section-identity.v1",
        "workbench_truss_section_identity_edit_surface_passed",
        "workbench_truss_section_identity_edit_model_sha256",
        "workbench_truss_section_identity_edit_receipt_sha256",
        "workbench_truss_section_identity_edit_request_receipt_sha256",
        "workbench_truss_section_identity_edit_request_sha256",
        "workbench_truss_section_identity_edit_assembly_receipt_sha256",
        "workbench_truss_section_identity_edit_checkpoint_sha256",
        "workbench_truss_section_identity_edit_result_ir_sha256",
        "workbench_truss_section_identity_edit_recovery_sha256",
        "workbench_truss_section_identity_edit_report_ir_sha256",
        "workbench_truss_section_identity_edit_restart_passed",
        "exercise_node_identity_edit_surface",
        "model-edit-node-identity",
        "structural-native:model-edit-node-identity.v1",
        "workbench_node_identity_edit_surface_passed",
        "workbench_node_identity_edit_model_sha256",
        "workbench_node_identity_edit_receipt_sha256",
        "workbench_node_identity_edit_request_receipt_sha256",
        "workbench_node_identity_edit_request_sha256",
        "workbench_node_identity_edit_assembly_receipt_sha256",
        "workbench_node_identity_edit_checkpoint_sha256",
        "workbench_node_identity_edit_result_ir_sha256",
        "workbench_node_identity_edit_recovery_sha256",
        "workbench_node_identity_edit_report_ir_sha256",
        "workbench_node_identity_edit_restart_passed",
        "exercise_element_identity_edit_surface",
        "model-edit-element-identity",
        "structural-native:model-edit-element-identity.v1",
        "workbench_element_identity_edit_surface_passed",
        "workbench_element_identity_edit_model_sha256",
        "workbench_element_identity_edit_receipt_sha256",
        "workbench_element_identity_edit_request_receipt_sha256",
        "workbench_element_identity_edit_request_sha256",
        "workbench_element_identity_edit_assembly_receipt_sha256",
        "workbench_element_identity_edit_checkpoint_sha256",
        "workbench_element_identity_edit_result_ir_sha256",
        "workbench_element_identity_edit_recovery_sha256",
        "workbench_element_identity_edit_report_ir_sha256",
        "workbench_element_identity_edit_restart_passed",
        "exercise_linear_load_combination_identity_edit_surface",
        "model-edit-linear-load-combination-identity",
        "structural-native:model-edit-linear-load-combination-identity.v1",
        "workbench_linear_load_combination_identity_edit_surface_passed",
        "workbench_linear_load_combination_identity_edit_model_sha256",
        "workbench_linear_load_combination_identity_edit_receipt_sha256",
        "workbench_linear_load_combination_identity_edit_request_receipt_sha256",
        "workbench_linear_load_combination_identity_edit_request_sha256",
        "workbench_linear_load_combination_identity_edit_assembly_receipt_sha256",
        "workbench_linear_load_combination_identity_edit_checkpoint_sha256",
        "workbench_linear_load_combination_identity_edit_result_ir_sha256",
        "workbench_linear_load_combination_identity_edit_recovery_sha256",
        "workbench_linear_load_combination_identity_edit_report_ir_sha256",
        "workbench_linear_load_combination_identity_edit_restart_passed",
        "exercise_model_identity_edit_surface",
        "model-edit-model-identity",
        "structural-native:model-edit-model-identity.v1",
        "workbench_model_identity_edit_surface_passed",
        "workbench_model_identity_edit_model_sha256",
        "workbench_model_identity_edit_receipt_sha256",
        "workbench_model_identity_edit_request_receipt_sha256",
        "workbench_model_identity_edit_request_sha256",
        "workbench_model_identity_edit_assembly_receipt_sha256",
        "workbench_model_identity_edit_checkpoint_sha256",
        "workbench_model_identity_edit_result_ir_sha256",
        "workbench_model_identity_edit_recovery_sha256",
        "workbench_model_identity_edit_report_ir_sha256",
        "workbench_model_identity_edit_restart_passed",
        "exercise_node_identity_cascade_edit_surface",
        "model-edit-node-identity-cascade",
        "structural-native:model-edit-node-identity-cascade.v2",
        "workbench_node_identity_cascade_edit_surface_passed",
        "workbench_node_identity_cascade_edit_model_sha256",
        "workbench_node_identity_cascade_edit_receipt_sha256",
        "workbench_node_identity_cascade_edit_request_receipt_sha256",
        "workbench_node_identity_cascade_edit_request_sha256",
        "workbench_node_identity_cascade_edit_assembly_receipt_sha256",
        "workbench_node_identity_cascade_edit_checkpoint_sha256",
        "workbench_node_identity_cascade_edit_result_ir_sha256",
        "workbench_node_identity_cascade_edit_recovery_sha256",
        "workbench_node_identity_cascade_edit_report_ir_sha256",
        "workbench_node_identity_cascade_edit_restart_passed",
        "exercise_nodal_load_add_surface",
        "model-add-nodal-load",
        "workbench_nodal_load_add_surface_passed",
        "workbench_nodal_load_add_model_sha256",
        "workbench_nodal_load_add_receipt_sha256",
        "workbench_nodal_load_add_request_sha256",
        "workbench_nodal_load_add_result_ir_sha256",
        "workbench_nodal_load_add_recovery_sha256",
        "exercise_nodal_load_deletion_surface",
        "model-delete-nodal-load",
        "workbench_nodal_load_delete_surface_passed",
        "workbench_nodal_load_delete_model_sha256",
        "workbench_nodal_load_delete_receipt_sha256",
        "workbench_nodal_load_delete_request_sha256",
        "workbench_nodal_load_delete_result_ir_sha256",
        "workbench_nodal_load_delete_recovery_sha256",
        "exercise_linear_load_pattern_deletion_surface",
        "model-delete-linear-load-pattern",
        "workbench_linear_load_pattern_delete_surface_passed",
        "workbench_linear_load_pattern_delete_model_sha256",
        "workbench_linear_load_pattern_delete_receipt_sha256",
        "workbench_linear_load_pattern_delete_request_sha256",
        "workbench_linear_load_pattern_delete_result_ir_sha256",
        "workbench_linear_load_pattern_delete_recovery_sha256",
        "exercise_linear_material_deletion_surface",
        "model-delete-linear-material",
        "workbench_linear_material_delete_surface_passed",
        "workbench_linear_material_delete_model_sha256",
        "workbench_linear_material_delete_receipt_sha256",
        "workbench_linear_material_delete_request_sha256",
        "workbench_linear_material_delete_result_ir_sha256",
        "workbench_linear_material_delete_recovery_sha256",
        "exercise_frame_section_deletion_surface",
        "model-delete-frame-section",
        "workbench_frame_section_delete_surface_passed",
        "workbench_frame_section_delete_model_sha256",
        "workbench_frame_section_delete_receipt_sha256",
        "workbench_frame_section_delete_request_sha256",
        "workbench_frame_section_delete_result_ir_sha256",
        "workbench_frame_section_delete_recovery_sha256",
        "exercise_truss_section_deletion_surface",
        "model-delete-truss-section",
        "workbench_truss_section_delete_surface_passed",
        "workbench_truss_section_delete_model_sha256",
        "workbench_truss_section_delete_receipt_sha256",
        "workbench_truss_section_delete_request_sha256",
        "workbench_truss_section_delete_result_ir_sha256",
        "workbench_truss_section_delete_recovery_sha256",
        "exercise_fixed_constraint_add_surface",
        "model-add-fixed-constraint",
        "workbench_fixed_constraint_add_surface_passed",
        "workbench_fixed_constraint_add_model_sha256",
        "workbench_fixed_constraint_add_receipt_sha256",
        "workbench_fixed_constraint_add_request_sha256",
        "workbench_fixed_constraint_add_result_ir_sha256",
        "workbench_fixed_constraint_add_recovery_sha256",
        "exercise_fixed_constraint_deletion_surface",
        "model-delete-fixed-constraint",
        "workbench_fixed_constraint_delete_surface_passed",
        "workbench_fixed_constraint_delete_model_sha256",
        "workbench_fixed_constraint_delete_receipt_sha256",
        "workbench_fixed_constraint_delete_request_sha256",
        "workbench_fixed_constraint_delete_result_ir_sha256",
        "workbench_fixed_constraint_delete_recovery_sha256",
        "exercise_linear_load_pattern_add_surface",
        "model-add-linear-load-pattern",
        "workbench_linear_load_pattern_add_surface_passed",
        "workbench_linear_load_pattern_add_model_sha256",
        "workbench_linear_load_pattern_add_receipt_sha256",
        "workbench_linear_load_pattern_add_request_sha256",
        "workbench_linear_load_pattern_add_result_ir_sha256",
        "workbench_linear_load_pattern_add_recovery_sha256",
        "exercise_linear_material_add_surface",
        "model-add-linear-material",
        "workbench_linear_material_add_surface_passed",
        "workbench_linear_material_add_model_sha256",
        "workbench_linear_material_add_receipt_sha256",
        "workbench_linear_material_add_composed_model_sha256",
        "workbench_linear_material_add_request_sha256",
        "workbench_linear_material_add_result_ir_sha256",
        "workbench_linear_material_add_recovery_sha256",
        "exercise_frame_section_add_surface",
        "model-add-frame-section",
        "workbench_frame_section_add_surface_passed",
        "workbench_frame_section_add_model_sha256",
        "workbench_frame_section_add_receipt_sha256",
        "workbench_frame_section_add_composed_model_sha256",
        "workbench_frame_section_add_request_sha256",
        "workbench_frame_section_add_result_ir_sha256",
        "workbench_frame_section_add_recovery_sha256",
        "exercise_frame_element_properties_edit_surface",
        "model-edit-frame-element-properties",
        "workbench_frame_element_properties_edit_surface_passed",
        "workbench_frame_element_properties_edit_model_sha256",
        "workbench_frame_element_properties_edit_receipt_sha256",
        "workbench_frame_element_properties_edit_request_sha256",
        "workbench_frame_element_properties_edit_result_ir_sha256",
        "workbench_frame_element_properties_edit_recovery_sha256",
        "exercise_truss3d_authoring_surface",
        "model-add-truss-section",
        "model-add-truss3d-member",
        "workbench_truss3d_authoring_surface_passed",
        "workbench_truss3d_authoring_section_model_sha256",
        "workbench_truss3d_authoring_section_receipt_sha256",
        "workbench_truss3d_authoring_member_model_sha256",
        "workbench_truss3d_authoring_member_receipt_sha256",
        "workbench_truss3d_authoring_composed_model_sha256",
        "workbench_truss3d_authoring_request_sha256",
        "workbench_truss3d_authoring_result_ir_sha256",
        "workbench_truss3d_authoring_recovery_sha256",
        "exercise_truss3d_editing_surface",
        "model-edit-truss-section",
        "model-edit-truss-element-properties",
        "workbench_truss3d_editing_surface_passed",
        "workbench_truss3d_editing_section_model_sha256",
        "workbench_truss3d_editing_section_receipt_sha256",
        "workbench_truss3d_editing_properties_model_sha256",
        "workbench_truss3d_editing_properties_receipt_sha256",
        "workbench_truss3d_editing_section_result_ir_sha256",
        "workbench_truss3d_editing_request_sha256",
        "workbench_truss3d_editing_result_ir_sha256",
        "workbench_truss3d_editing_recovery_sha256",
        "exercise_truss3d_leaf_deletion_surface",
        "model-delete-truss3d-leaf-member",
        "workbench_truss3d_leaf_deletion_surface_passed",
        "workbench_truss3d_leaf_deletion_model_sha256",
        "workbench_truss3d_leaf_deletion_receipt_sha256",
        "workbench_truss3d_leaf_deletion_request_sha256",
        "workbench_truss3d_leaf_deletion_result_ir_sha256",
        "workbench_truss3d_leaf_deletion_recovery_sha256",
        "exercise_frame3d_leaf_deletion_surface",
        "model-delete-frame3d-leaf-member",
        "workbench_frame3d_leaf_deletion_surface_passed",
        "workbench_frame3d_leaf_deletion_model_sha256",
        "workbench_frame3d_leaf_deletion_receipt_sha256",
        "workbench_frame3d_leaf_deletion_request_sha256",
        "workbench_frame3d_leaf_deletion_result_ir_sha256",
        "workbench_frame3d_leaf_deletion_recovery_sha256",
        "exercise_model_linear_request_create_surface",
        "model-create-linear-analysis-request",
        "workbench_model_linear_request_create_surface_passed",
        "workbench_model_linear_request_create_request_sha256",
        "workbench_model_linear_request_create_receipt_sha256",
        "workflow-model-linear",
        "model_ir_linear_workbench_restart_passed",
        "model_ir_linear_result_recovery_ir_sha256",
        "model_ir_linear_report_pdf_sha256",
        "exercise_model_ir_linear_localized_pdf_surface",
        "model_ir_linear_localized_pdf_surface_passed",
        "workflow-mgt-model-linear",
        "mgt_model_ir_linear_workbench_restart_passed",
        "mgt_model_ir_linear_import_health_sha256",
        "mgt_model_ir_linear_result_recovery_ir_sha256",
        "structural-native-sparse-linear-localized-pdf-report-receipt.v2",
        "workbench_localized_model_view_surface_passed",
        "workbench_model_view_ko_kr_sha256",
        "result-deformed-view",
        "workbench_deformed_view_surface_passed",
        "workbench_localized_result_views_surface_passed",
        "rollback --root",
    ):
        if token not in distribution_e2e:
            blockers.append(f"native_distribution_e2e_token_missing:{token}")
    for token in (
        "unshare -Urn bwrap",
        "--ro-bind / /",
        "--unshare-user",
        "--uid 65532",
        "--gid 65532",
        "--setenv PATH /nonexistent",
        "workflow-mgt",
        "workflow-model-linear",
        "workflow-mgt-model-linear",
        "inspect --workspace",
        "--decision review",
        "review-show --workspace",
        "export --workspace",
        "--workbench-inspect-before-review",
        "--model-ir-linear-workbench-root",
        "--model-ir-linear-workbench-inspect-before-review",
        "--mgt-model-ir-linear-workbench-root",
        "--mgt-model-ir-linear-workbench-inspect-before-review",
        "--model-ir-linear-workbench-session-before-localized-pdf",
        "--model-ir-linear-localized-pdf-en-us-first-root",
        "--model-ir-linear-localized-pdf-ko-kr-second-root",
        "structural-native-benchmark-catalog-view.v1",
        "structural-native-evidence-bundle-view.v1",
        "--workbench-catalog",
        "--workbench-evidence",
        "runtime-probe",
        "runtime-receipt-verify",
    ):
        if token not in rootfs_e2e:
            blockers.append(f"native_rootfs_e2e_token_missing:{token}")

    distribution_receipt_check = _text(
        root, Path("scripts/check_native_distribution_receipt.py"), blockers
    )
    _require_tokens(
        relative=Path("scripts/check_native_distribution_receipt.py"),
        text=distribution_receipt_check,
        tokens=(
            "structural-native-distribution-e2e.v76",
            "V76_NODE_IDENTITY_CASCADE_EDIT_KEYS",
            "workbench_node_identity_cascade_edit_surface_passed",
            "workbench_node_identity_cascade_edit_receipt_sha256",
            "workbench_node_identity_cascade_edit_request_receipt_sha256",
            "workbench_node_identity_cascade_edit_recovery_sha256",
            "workbench_node_identity_cascade_edit_restart_passed",
            "structural-native-distribution-e2e.v75",
            "V75_MODEL_IDENTITY_EDIT_KEYS",
            "workbench_model_identity_edit_surface_passed",
            "workbench_model_identity_edit_receipt_sha256",
            "workbench_model_identity_edit_request_receipt_sha256",
            "workbench_model_identity_edit_recovery_sha256",
            "workbench_model_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v74",
            "V74_LINEAR_LOAD_COMBINATION_IDENTITY_EDIT_KEYS",
            "workbench_linear_load_combination_identity_edit_surface_passed",
            "workbench_linear_load_combination_identity_edit_receipt_sha256",
            "workbench_linear_load_combination_identity_edit_request_receipt_sha256",
            "workbench_linear_load_combination_identity_edit_recovery_sha256",
            "workbench_linear_load_combination_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v73",
            "V73_ELEMENT_IDENTITY_EDIT_KEYS",
            "workbench_element_identity_edit_surface_passed",
            "workbench_element_identity_edit_receipt_sha256",
            "workbench_element_identity_edit_request_receipt_sha256",
            "workbench_element_identity_edit_recovery_sha256",
            "workbench_element_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v72",
            "V72_NODE_IDENTITY_EDIT_KEYS",
            "workbench_node_identity_edit_surface_passed",
            "workbench_node_identity_edit_receipt_sha256",
            "workbench_node_identity_edit_request_receipt_sha256",
            "workbench_node_identity_edit_recovery_sha256",
            "workbench_node_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v71",
            "V71_TRUSS_SECTION_IDENTITY_EDIT_KEYS",
            "workbench_truss_section_identity_edit_surface_passed",
            "workbench_truss_section_identity_edit_receipt_sha256",
            "workbench_truss_section_identity_edit_request_receipt_sha256",
            "workbench_truss_section_identity_edit_recovery_sha256",
            "workbench_truss_section_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v70",
            "V70_FRAME_SECTION_IDENTITY_EDIT_KEYS",
            "workbench_frame_section_identity_edit_surface_passed",
            "workbench_frame_section_identity_edit_receipt_sha256",
            "workbench_frame_section_identity_edit_request_receipt_sha256",
            "workbench_frame_section_identity_edit_recovery_sha256",
            "workbench_frame_section_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v69",
            "V69_LINEAR_MATERIAL_IDENTITY_EDIT_KEYS",
            "workbench_linear_material_identity_edit_surface_passed",
            "workbench_linear_material_identity_edit_receipt_sha256",
            "workbench_linear_material_identity_edit_request_receipt_sha256",
            "workbench_linear_material_identity_edit_recovery_sha256",
            "workbench_linear_material_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v68",
            "V68_LINEAR_LOAD_PATTERN_IDENTITY_EDIT_KEYS",
            "workbench_linear_load_pattern_identity_edit_surface_passed",
            "workbench_linear_load_pattern_identity_edit_receipt_sha256",
            "workbench_linear_load_pattern_identity_edit_request_receipt_sha256",
            "workbench_linear_load_pattern_identity_edit_recovery_sha256",
            "workbench_linear_load_pattern_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v67",
            "V67_NODAL_LOAD_IDENTITY_EDIT_KEYS",
            "workbench_nodal_load_identity_edit_surface_passed",
            "workbench_nodal_load_identity_edit_receipt_sha256",
            "workbench_nodal_load_identity_edit_request_receipt_sha256",
            "workbench_nodal_load_identity_edit_recovery_sha256",
            "workbench_nodal_load_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v66",
            "V66_FIXED_CONSTRAINT_IDENTITY_EDIT_KEYS",
            "workbench_fixed_constraint_identity_edit_surface_passed",
            "workbench_fixed_constraint_identity_edit_receipt_sha256",
            "workbench_fixed_constraint_identity_edit_request_receipt_sha256",
            "workbench_fixed_constraint_identity_edit_recovery_sha256",
            "workbench_fixed_constraint_identity_edit_restart_passed",
            "structural-native-distribution-e2e.v65",
            "V65_FIXED_CONSTRAINT_DOF_REORDER_KEYS",
            "workbench_fixed_constraint_dof_reorder_surface_passed",
            "workbench_fixed_constraint_dof_reorder_receipt_sha256",
            "workbench_fixed_constraint_dof_reorder_request_receipt_sha256",
            "workbench_fixed_constraint_dof_reorder_recovery_sha256",
            "workbench_fixed_constraint_dof_reorder_restart_passed",
            "structural-native-distribution-e2e.v64",
            "V64_FIXED_CONSTRAINT_DOF_ADD_KEYS",
            "workbench_fixed_constraint_dof_add_surface_passed",
            "workbench_fixed_constraint_dof_add_receipt_sha256",
            "workbench_fixed_constraint_dof_add_request_receipt_sha256",
            "workbench_fixed_constraint_dof_add_recovery_sha256",
            "workbench_fixed_constraint_dof_add_restart_passed",
            "structural-native-distribution-e2e.v63",
            "V63_FIXED_CONSTRAINT_DOF_DELETE_KEYS",
            "workbench_fixed_constraint_dof_delete_surface_passed",
            "workbench_fixed_constraint_dof_delete_receipt_sha256",
            "workbench_fixed_constraint_dof_delete_request_receipt_sha256",
            "workbench_fixed_constraint_dof_delete_recovery_sha256",
            "workbench_fixed_constraint_dof_delete_restart_passed",
            "structural-native-distribution-e2e.v62",
            "V62_CONSTRAINT_TARGET_EDIT_KEYS",
            "workbench_constraint_target_edit_surface_passed",
            "workbench_constraint_target_edit_receipt_sha256",
            "workbench_constraint_target_edit_request_receipt_sha256",
            "workbench_constraint_target_edit_recovery_sha256",
            "workbench_constraint_target_edit_restart_passed",
            "structural-native-distribution-e2e.v61",
            "V61_NODAL_LOAD_TARGET_EDIT_KEYS",
            "workbench_nodal_load_target_edit_surface_passed",
            "workbench_nodal_load_target_edit_receipt_sha256",
            "workbench_nodal_load_target_edit_request_receipt_sha256",
            "workbench_nodal_load_target_edit_recovery_sha256",
            "workbench_nodal_load_target_edit_restart_passed",
            "structural-native-distribution-e2e.v60",
            "V60_NESTED_LINEAR_LOAD_COMBINATION_TERM_INSERT_KEYS",
            "workbench_nested_linear_load_combination_term_insert_surface_passed",
            "workbench_nested_linear_load_combination_term_insert_receipt_sha256",
            "workbench_nested_linear_load_combination_term_insert_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_insert_recovery_sha256",
            "workbench_nested_linear_load_combination_term_insert_restart_passed",
            "structural-native-distribution-e2e.v59",
            "V59_DIRECT_LINEAR_LOAD_COMBINATION_TERM_INSERT_KEYS",
            "workbench_direct_linear_load_combination_term_insert_surface_passed",
            "workbench_direct_linear_load_combination_term_insert_receipt_sha256",
            "workbench_direct_linear_load_combination_term_insert_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_insert_recovery_sha256",
            "workbench_direct_linear_load_combination_term_insert_restart_passed",
            "structural-native-distribution-e2e.v57",
            "V57_NESTED_LINEAR_LOAD_COMBINATION_TERM_REORDER_KEYS",
            "workbench_nested_linear_load_combination_term_reorder_surface_passed",
            "workbench_nested_linear_load_combination_term_reorder_receipt_sha256",
            "workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_reorder_recovery_sha256",
            "workbench_nested_linear_load_combination_term_reorder_restart_passed",
            "structural-native-distribution-e2e.v56",
            "V56_NESTED_LINEAR_LOAD_COMBINATION_TERM_DELETE_KEYS",
            "workbench_nested_linear_load_combination_term_delete_surface_passed",
            "workbench_nested_linear_load_combination_term_delete_receipt_sha256",
            "workbench_nested_linear_load_combination_term_delete_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_delete_recovery_sha256",
            "workbench_nested_linear_load_combination_term_delete_restart_passed",
            "structural-native-distribution-e2e.v55",
            "V55_NESTED_LINEAR_LOAD_COMBINATION_TERM_ADD_KEYS",
            "workbench_nested_linear_load_combination_term_add_surface_passed",
            "workbench_nested_linear_load_combination_term_add_receipt_sha256",
            "workbench_nested_linear_load_combination_term_add_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_add_recovery_sha256",
            "workbench_nested_linear_load_combination_term_add_restart_passed",
            "structural-native-distribution-e2e.v54",
            "V54_DIRECT_LINEAR_LOAD_COMBINATION_TERM_DELETE_KEYS",
            "workbench_direct_linear_load_combination_term_delete_surface_passed",
            "workbench_direct_linear_load_combination_term_delete_receipt_sha256",
            "workbench_direct_linear_load_combination_term_delete_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_delete_recovery_sha256",
            "workbench_direct_linear_load_combination_term_delete_restart_passed",
            "structural-native-distribution-e2e.v53",
            "V53_DIRECT_LINEAR_LOAD_COMBINATION_TERM_ADD_KEYS",
            "workbench_direct_linear_load_combination_term_add_surface_passed",
            "workbench_direct_linear_load_combination_term_add_receipt_sha256",
            "workbench_direct_linear_load_combination_term_add_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_add_recovery_sha256",
            "workbench_direct_linear_load_combination_term_add_restart_passed",
            "structural-native-distribution-e2e.v52",
            "V52_NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_KEYS",
            "workbench_nested_linear_load_combination_reference_edit_surface_passed",
            "workbench_nested_linear_load_combination_reference_edit_receipt_sha256",
            "workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256",
            "workbench_nested_linear_load_combination_reference_edit_recovery_sha256",
            "workbench_nested_linear_load_combination_reference_edit_restart_passed",
            "structural-native-distribution-e2e.v51",
            "V51_DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_KEYS",
            "workbench_direct_linear_load_combination_reference_edit_surface_passed",
            "workbench_direct_linear_load_combination_reference_edit_receipt_sha256",
            "workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256",
            "workbench_direct_linear_load_combination_reference_edit_recovery_sha256",
            "workbench_direct_linear_load_combination_reference_edit_restart_passed",
            "structural-native-distribution-e2e.v50",
            "V50_NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_KEYS",
            "workbench_nested_linear_load_combination_factor_edit_surface_passed",
            "workbench_nested_linear_load_combination_factor_edit_receipt_sha256",
            "workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256",
            "workbench_nested_linear_load_combination_factor_edit_recovery_sha256",
            "workbench_nested_linear_load_combination_factor_edit_restart_passed",
            "structural-native-distribution-e2e.v49",
            "V49_DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_KEYS",
            "workbench_direct_linear_load_combination_factor_edit_surface_passed",
            "workbench_direct_linear_load_combination_factor_edit_receipt_sha256",
            "workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256",
            "workbench_direct_linear_load_combination_factor_edit_recovery_sha256",
            "workbench_direct_linear_load_combination_factor_edit_restart_passed",
            "structural-native-distribution-e2e.v48",
            "V48_NESTED_LINEAR_LOAD_COMBINATION_DELETE_KEYS",
            "workbench_nested_linear_load_combination_delete_surface_passed",
            "workbench_nested_linear_load_combination_delete_receipt_sha256",
            "workbench_nested_linear_load_combination_delete_request_receipt_sha256",
            "workbench_nested_linear_load_combination_delete_recovery_sha256",
            "workbench_nested_linear_load_combination_delete_restart_passed",
            "structural-native-distribution-e2e.v47",
            "V47_DIRECT_LINEAR_LOAD_COMBINATION_DELETE_KEYS",
            "workbench_direct_linear_load_combination_delete_surface_passed",
            "workbench_direct_linear_load_combination_delete_receipt_sha256",
            "workbench_direct_linear_load_combination_delete_recovery_sha256",
            "workbench_direct_linear_load_combination_delete_restart_passed",
            "structural-native-distribution-e2e.v46",
            "V46_NESTED_LINEAR_LOAD_COMBINATION_KEYS",
            "workbench_nested_linear_load_combination_surface_passed",
            "workbench_nested_linear_load_combination_edit_receipt_sha256",
            "workbench_nested_linear_load_combination_recovery_sha256",
            "workbench_nested_linear_load_combination_restart_passed",
            "structural-native-distribution-e2e.v45",
            "V45_DIRECT_LINEAR_LOAD_COMBINATION_KEYS",
            "workbench_direct_linear_load_combination_surface_passed",
            "workbench_direct_linear_load_combination_edit_receipt_sha256",
            "workbench_direct_linear_load_combination_recovery_sha256",
            "workbench_direct_linear_load_combination_restart_passed",
            "structural-native-distribution-e2e.v44",
            "V44_LINEAR_LOAD_COMBINATION_EXECUTION_KEYS",
            "workbench_linear_load_combination_execution_surface_passed",
            "workbench_linear_load_combination_request_receipt_sha256",
            "workbench_linear_load_combination_report_ir_sha256",
            "workbench_linear_load_combination_restart_passed",
            "structural-native-distribution-e2e.v43",
            "V43_LINEAR_LOAD_COMBINATION_DELETE_KEYS",
            "workbench_linear_load_combination_delete_surface_passed",
            "workbench_linear_load_combination_delete_recovery_sha256",
            "structural-native-distribution-e2e.v42",
            "V42_LINEAR_LOAD_COMBINATION_ADD_KEYS",
            "workbench_linear_load_combination_add_surface_passed",
            "workbench_linear_load_combination_add_solver_rejection_sha256",
            "structural-native-distribution-e2e.v41",
            "V41_ORPHAN_NODE_DELETE_KEYS",
            "workbench_orphan_node_delete_surface_passed",
            "workbench_orphan_node_delete_recovery_sha256",
            "structural-native-distribution-e2e.v40",
            "V40_NODE_ADD_KEYS",
            "workbench_node_add_surface_passed",
            "workbench_node_add_recovery_sha256",
            "structural-native-distribution-e2e.v39",
            "V39_TRUSS_SECTION_DELETE_KEYS",
            "workbench_truss_section_delete_surface_passed",
            "workbench_truss_section_delete_recovery_sha256",
            "structural-native-distribution-e2e.v38",
            "V38_FRAME_SECTION_DELETE_KEYS",
            "workbench_frame_section_delete_surface_passed",
            "workbench_frame_section_delete_recovery_sha256",
            "structural-native-distribution-e2e.v37",
            "V37_LINEAR_MATERIAL_DELETE_KEYS",
            "workbench_linear_material_delete_surface_passed",
            "workbench_linear_material_delete_recovery_sha256",
            "V36_LINEAR_LOAD_PATTERN_DELETE_KEYS",
            "workbench_linear_load_pattern_delete_surface_passed",
            "workbench_linear_load_pattern_delete_recovery_sha256",
            "V35_NODAL_LOAD_DELETE_KEYS",
            "workbench_nodal_load_delete_surface_passed",
            "workbench_nodal_load_delete_recovery_sha256",
            "V34_FIXED_CONSTRAINT_DELETE_KEYS",
            "workbench_fixed_constraint_delete_surface_passed",
            "workbench_fixed_constraint_delete_recovery_sha256",
            "V33_FRAME3D_LEAF_DELETION_KEYS",
            "workbench_frame3d_leaf_deletion_surface_passed",
            "workbench_frame3d_leaf_deletion_recovery_sha256",
            "V32_TRUSS3D_LEAF_DELETION_KEYS",
            "workbench_truss3d_leaf_deletion_surface_passed",
            "workbench_truss3d_leaf_deletion_recovery_sha256",
        ),
        blockers=blockers,
    )

    distribution_doc = _text(
        root, Path("docs/native/distribution-lifecycle.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/distribution-lifecycle.md"),
        text=distribution_doc,
        tokens=(
            "append-only v57 receipt",
            "frozen v1 through v56 receipts",
            "no pre-v57 receipt",
            "append-only v56 receipt",
            "frozen v1 through v55 receipts",
            "no pre-v56 receipt",
            "append-only v55 receipt",
            "frozen v1 through v54 receipts",
            "no pre-v55 receipt",
            "append-only v54 receipt",
            "frozen v1 through v53 receipts",
            "no pre-v54 receipt",
            "append-only v53 receipt",
            "frozen v1 through v52 receipts",
            "no pre-v53 receipt",
            "append-only v52 receipt",
            "frozen v1 through v51 receipts",
            "no pre-v52 receipt",
            "append-only v51 receipt",
            "no pre-v51 receipt",
            "append-only v50 hash-bound receipt",
            "no pre-v50 receipt",
            "append-only v49 hash-bound receipt",
            "frozen v1 through v48 receipts",
            "no pre-v49 receipt",
            "append-only v48 hash-bound receipt",
            "frozen v1 through v47 receipts",
            "no pre-v48 receipt",
            "append-only v47 hash-bound receipt",
            "frozen v1 through v46 receipts",
            "no pre-v47 receipt",
            "append-only v46 hash-bound receipt",
            "frozen v1 through v45 receipts",
            "no pre-v46 receipt",
            "append-only v45 hash-bound receipt",
            "frozen v1 through v44 receipts",
            "no pre-v45 receipt",
            "append-only v44 hash-bound receipt",
            "frozen v1 through v43 receipts",
            "no pre-v44 receipt",
            "append-only v43 hash-bound receipt",
            "frozen v1 through v42 receipts",
            "no pre-v43 receipt",
            "append-only v42 hash-bound receipt",
            "frozen v1 through v41 receipts",
            "no pre-v42 receipt",
            "append-only v41 hash-bound receipt",
            "frozen v1 through v40 receipts",
            "no pre-v41 receipt",
            "append-only v40 hash-bound receipt",
            "frozen v1 through v39 receipts",
            "no pre-v40 receipt",
            "append-only v39 hash-bound receipt",
            "frozen v1 through v38 receipts",
            "no pre-v39 receipt",
            "append-only v38 hash-bound receipt",
            "no pre-v38 receipt",
            "append-only v37 hash-bound receipt",
            "no pre-v37 receipt",
        ),
        blockers=blockers,
    )

    truss_editing_doc = _text(
        root, Path("docs/native/modelir-truss3d-editing-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-truss3d-editing-v1.md"),
        text=truss_editing_doc,
        tokens=(
            "model-edit-truss-section",
            "model-edit-truss-element-properties",
            "Installed static and shared package E2E v31",
            "Frozen v1 through v30",
            "receipts preserve their narrower authority",
        ),
        blockers=blockers,
    )

    linear_load_combination_deletion_doc = _text(
        root,
        Path("docs/native/modelir-linear-load-combination-deletion-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-load-combination-deletion-v1.md"),
        text=linear_load_combination_deletion_doc,
        tokens=(
            "model-delete-linear-load-combination",
            "Installed CPU static/shared E2E v43",
            "two distinct",
            "checkpoint/restart",
            "fallback 0",
            "C6",
        ),
        blockers=blockers,
    )

    truss_leaf_deletion_doc = _text(
        root, Path("docs/native/modelir-truss3d-leaf-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-truss3d-leaf-deletion-v1.md"),
        text=truss_leaf_deletion_doc,
        tokens=(
            "model-delete-truss3d-leaf-member",
            "Installed static and shared package E2E v32",
            "Frozen v1 through v31",
            "receipts preserve their narrower authority",
        ),
        blockers=blockers,
    )

    frame_leaf_deletion_doc = _text(
        root, Path("docs/native/modelir-frame3d-leaf-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-frame3d-leaf-deletion-v1.md"),
        text=frame_leaf_deletion_doc,
        tokens=(
            "model-delete-frame3d-leaf-member",
            "Installed static and shared package E2E v33",
            "Frozen v1 through v32",
            "receipts keep their narrower authority",
        ),
        blockers=blockers,
    )

    fixed_constraint_deletion_doc = _text(
        root, Path("docs/native/modelir-fixed-constraint-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-fixed-constraint-deletion-v1.md"),
        text=fixed_constraint_deletion_doc,
        tokens=(
            "model-delete-fixed-constraint",
            "Installed static and shared package E2E v34",
            "Frozen v1 through v33",
            "receipts keep their narrower authority",
        ),
        blockers=blockers,
    )

    nodal_load_deletion_doc = _text(
        root, Path("docs/native/modelir-nodal-load-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-nodal-load-deletion-v1.md"),
        text=nodal_load_deletion_doc,
        tokens=(
            "model-delete-nodal-load",
            "Installed static and shared package E2E v35",
            "Frozen v1 through v34",
            "receipts retain their narrower authority",
        ),
        blockers=blockers,
    )

    nodal_load_target_edit_doc = _text(
        root, Path("docs/native/modelir-nodal-load-target-edit-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-nodal-load-target-edit-v1.md"),
        text=nodal_load_target_edit_doc,
        tokens=(
            "model-edit-nodal-load-target",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-nodal-load-target.v1",
            "nodal_load_target",
            "append-only v61",
            "[0,0,0,0,0,0,0,-10000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6 remain open",
        ),
        blockers=blockers,
    )

    constraint_target_edit_doc = _text(
        root, Path("docs/native/modelir-constraint-target-edit-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-constraint-target-edit-v1.md"),
        text=constraint_target_edit_doc,
        tokens=(
            "model-edit-constraint-target",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-constraint-target.v1",
            "constraint_target",
            "append-only v62",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6 remain open",
        ),
        blockers=blockers,
    )

    fixed_constraint_dof_delete_doc = _text(
        root, Path("docs/native/modelir-fixed-constraint-dof-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-fixed-constraint-dof-deletion-v1.md"),
        text=fixed_constraint_dof_delete_doc,
        tokens=(
            "model-delete-fixed-constraint-dof",
            "single C ABI into C++ semantic validation",
            "structural-native:model-delete-fixed-constraint-dof.v1",
            "fixed_constraint_dof_delete",
            "append-only v63",
            "[11,12,13,14,15,16,17]",
            "[0,0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6 remain open",
        ),
        blockers=blockers,
    )

    fixed_constraint_dof_add_doc = _text(
        root, Path("docs/native/modelir-fixed-constraint-dof-addition-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-fixed-constraint-dof-addition-v1.md"),
        text=fixed_constraint_dof_add_doc,
        tokens=(
            "model-add-fixed-constraint-dof",
            "single C ABI into C++ semantic validation",
            "structural-native:model-add-fixed-constraint-dof.v1",
            "fixed_constraint_dof_add",
            "append-only v64",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6 remain open",
        ),
        blockers=blockers,
    )

    fixed_constraint_dof_reorder_doc = _text(
        root, Path("docs/native/modelir-fixed-constraint-dof-reorder-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-fixed-constraint-dof-reorder-v1.md"),
        text=fixed_constraint_dof_reorder_doc,
        tokens=(
            "model-reorder-fixed-constraint-dof",
            "single C ABI into C++ semantic validation",
            "structural-native:model-reorder-fixed-constraint-dof.v1",
            "fixed_constraint_dof_reorder",
            "append-only v65",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6 remain open",
        ),
        blockers=blockers,
    )

    fixed_constraint_identity_edit_doc = _text(
        root, Path("docs/native/modelir-fixed-constraint-identity-edit-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-fixed-constraint-identity-edit-v1.md"),
        text=fixed_constraint_identity_edit_doc,
        tokens=(
            "model-edit-fixed-constraint-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-fixed-constraint-identity.v1",
            "fixed_constraint_identity_edit",
            "append-only v66",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    nodal_load_identity_edit_doc = _text(
        root, Path("docs/native/modelir-nodal-load-identity-edit-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-nodal-load-identity-edit-v1.md"),
        text=nodal_load_identity_edit_doc,
        tokens=(
            "model-edit-nodal-load-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-nodal-load-identity.v1",
            "nodal_load_identity_edit",
            "append-only v67",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    linear_load_pattern_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-linear-load-pattern-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-load-pattern-identity-edit-v1.md"),
        text=linear_load_pattern_identity_edit_doc,
        tokens=(
            "model-edit-linear-load-pattern-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-linear-load-pattern-identity.v1",
            "linear_load_pattern_identity_edit",
            "append-only v68",
            "[12,13,14,15,16,17]",
            "[0,-1000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    linear_material_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-linear-material-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-material-identity-edit-v1.md"),
        text=linear_material_identity_edit_doc,
        tokens=(
            "model-edit-linear-material-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-linear-material-identity.v1",
            "linear_material_identity_edit",
            "append-only v69",
            "[6,7,8,9,10,11]",
            "[0,-10000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    frame_section_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-frame-section-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-frame-section-identity-edit-v1.md"),
        text=frame_section_identity_edit_doc,
        tokens=(
            "model-edit-frame-section-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-frame-section-identity.v1",
            "frame_section_identity_edit",
            "append-only v70",
            "[6,7,8,9,10,11]",
            "[0,-10000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    truss_section_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-truss-section-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-truss-section-identity-edit-v1.md"),
        text=truss_section_identity_edit_doc,
        tokens=(
            "model-edit-truss-section-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-truss-section-identity.v1",
            "truss_section_identity_edit",
            "append-only v71",
            "[1,2]",
            "[0,12,15]",
            "[6,7,8,9,10,11]",
            "[0,-10000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    node_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-node-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-node-identity-edit-v1.md"),
        text=node_identity_edit_doc,
        tokens=(
            "model-edit-node-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-node-identity.v1",
            "node_identity_edit",
            "append-only v72",
            "[1]",
            "[0,12]",
            "[6,7,8,9,10,11]",
            "[0,-10000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    element_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-element-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-element-identity-edit-v1.md"),
        text=element_identity_edit_doc,
        tokens=(
            "model-edit-element-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-element-identity.v1",
            "element_identity_edit",
            "append-only v73",
            "[1]",
            "[0,12]",
            "[6,7,8,9,10,11]",
            "[0,-10000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    model_identity_edit_doc = _text(
        root, Path("docs/native/modelir-model-identity-edit-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-model-identity-edit-v1.md"),
        text=model_identity_edit_doc,
        tokens=(
            "model-edit-model-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-model-identity.v1",
            "model_identity_edit",
            "append-only v75",
            "[1]",
            "[0,12]",
            "[6,7,8,9,10,11]",
            "[25000,-12000,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    node_identity_cascade_doc = _text(
        root, Path("docs/native/modelir-node-identity-cascade-edit-v2.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-node-identity-cascade-edit-v2.md"),
        text=node_identity_cascade_doc,
        tokens=(
            "model-edit-node-identity-cascade",
            "single C ABI into C++ semantic",
            "structural-native:model-edit-node-identity-cascade.v2",
            "node_identity_cascade_edit",
            "append-only v76",
            "[1]",
            "[0,12]",
            "[6,7,8,9,10,11]",
            "[25000,-12000,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    linear_load_combination_identity_edit_doc = _text(
        root,
        Path("docs/native/modelir-linear-load-combination-identity-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-load-combination-identity-edit-v1.md"),
        text=linear_load_combination_identity_edit_doc,
        tokens=(
            "model-edit-linear-load-combination-identity",
            "single C ABI into C++ semantic validation",
            "structural-native:model-edit-linear-load-combination-identity.v1",
            "linear_load_combination_identity_edit",
            "append-only v74",
            "[1]",
            "[0,12]",
            "[6,7,8,9,10,11]",
            "[25000,-12000,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "authorize C6",
        ),
        blockers=blockers,
    )

    linear_load_pattern_deletion_doc = _text(
        root, Path("docs/native/modelir-linear-load-pattern-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-load-pattern-deletion-v1.md"),
        text=linear_load_pattern_deletion_doc,
        tokens=(
            "model-delete-linear-load-pattern",
            "Installed static and shared package E2E v36",
            "Frozen v1 through v35",
            "receipts retain their narrower authority",
        ),
        blockers=blockers,
    )

    linear_material_deletion_doc = _text(
        root, Path("docs/native/modelir-linear-material-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-material-deletion-v1.md"),
        text=linear_material_deletion_doc,
        tokens=(
            "model-delete-linear-material",
            "Installed static and shared package E2E v37",
            "Frozen v1 through v36",
            "receipts retain their narrower authority",
        ),
        blockers=blockers,
    )

    frame_section_deletion_doc = _text(
        root, Path("docs/native/modelir-frame-section-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-frame-section-deletion-v1.md"),
        text=frame_section_deletion_doc,
        tokens=(
            "model-delete-frame-section",
            "Installed static and shared package E2E v38",
            "Frozen v1 through v37",
            "receipts retain their narrower authority",
        ),
        blockers=blockers,
    )

    truss_section_deletion_doc = _text(
        root, Path("docs/native/modelir-truss-section-deletion-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-truss-section-deletion-v1.md"),
        text=truss_section_deletion_doc,
        tokens=(
            "model-delete-truss-section",
            "Installed static and shared package E2E v39",
            "Frozen v1 through v38",
            "receipts retain their narrower authority",
        ),
        blockers=blockers,
    )

    node_add_doc = _text(
        root, Path("docs/native/modelir-node-add-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-node-add-v1.md"),
        text=node_add_doc,
        tokens=(
            "model-add-node",
            "Installed static and shared package E2E v40",
            "Frozen v1 through v39",
            "receipts retain their narrower authority",
            "fallback 0",
        ),
        blockers=blockers,
    )

    orphan_node_delete_doc = _text(
        root, Path("docs/native/modelir-orphan-node-delete-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-orphan-node-delete-v1.md"),
        text=orphan_node_delete_doc,
        tokens=(
            "model-delete-orphan-node",
            "Installed static and shared package E2E v41",
            "Frozen v1 through v40",
            "receipts retain their narrower authority",
            "fallback 0",
        ),
        blockers=blockers,
    )

    linear_load_combination_add_doc = _text(
        root, Path("docs/native/modelir-linear-load-combination-add-v1.md"), blockers
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-load-combination-add-v1.md"),
        text=linear_load_combination_add_doc,
        tokens=(
            "model-add-linear-load-combination",
            "Installed CPU static/shared E2E v44",
            "--load-combination",
            "active external load",
            "fallback 0",
            "C6",
        ),
        blockers=blockers,
    )

    linear_load_combination_execution_doc = _text(
        root,
        Path("docs/native/modelir-linear-load-combination-execution-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-linear-load-combination-execution-v1.md"),
        text=linear_load_combination_execution_doc,
        tokens=(
            "load-case selector",
            "exactly two terms",
            "structural-native-model-linear-combination-request-create-receipt.v1",
            "Installed CPU static/shared distribution E2E v44",
            "fallback is zero",
            "C6",
        ),
        blockers=blockers,
    )

    direct_linear_load_combination_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-v1.md"),
        text=direct_linear_load_combination_doc,
        tokens=(
            "two through 64",
            "structural-native:model-add-direct-linear-load-combination.v2",
            "structural-native-model-linear-direct-combination-request-create-receipt.v2",
            "frozen ABI v1.13",
            "Installed CPU static/shared distribution E2E v45",
            "[25000,-12000,5000,0,0,0]",
            "fallback 0",
            "C6",
        ),
        blockers=blockers,
    )

    direct_linear_load_combination_factor_edit_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md"),
        text=direct_linear_load_combination_factor_edit_doc,
        tokens=(
            "model-edit-linear-load-combination-factor",
            "two through 64 ordered",
            "single C ABI into C++",
            "structural-native:model-edit-direct-linear-load-combination-factor.v1",
            "direct_linear_load_combination_factor_edit",
            "Installed CPU static/shared distribution E2E v49",
            "[25000,-13500,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )

    direct_linear_load_combination_reference_edit_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path(
            "docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md"
        ),
        text=direct_linear_load_combination_reference_edit_doc,
        tokens=(
            "model-edit-linear-load-combination-reference",
            "two through 64 ordered",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-edit-direct-linear-load-combination-reference.v1",
            "direct_linear_load_combination_reference_edit",
            "append-only v51",
            "[120000,0,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )

    direct_linear_load_combination_deletion_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-deletion-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-deletion-v1.md"),
        text=direct_linear_load_combination_deletion_doc,
        tokens=(
            "model-delete-linear-load-combination",
            "two through 64",
            "structural-native:model-delete-direct-linear-load-combination.v2",
            "direct_linear_load_combination_delete",
            "Installed CPU static/shared distribution E2E v47",
            "[0,-10000,0,0,0,0]",
            "fallback 0",
            "C6",
        ),
        blockers=blockers,
    )

    nested_linear_load_combination_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-nested-linear-load-combination-v1.md"),
        text=nested_linear_load_combination_doc,
        tokens=(
            "model-add-nested-linear-load-combination",
            "root-inclusive combination depth is at most eight",
            "structural-native:model-add-nested-linear-load-combination.v3",
            "structural-native-model-linear-nested-combination-request-create-receipt.v3",
            "frozen ABI v1.13",
            "Installed CPU static/shared distribution E2E v46",
            "[25000,-6000,2500,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )

    nested_linear_load_combination_deletion_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-deletion-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-nested-linear-load-combination-deletion-v1.md"),
        text=nested_linear_load_combination_deletion_doc,
        tokens=(
            "model-delete-linear-load-combination",
            "root-inclusive combination depth is at most eight",
            "structural-native:model-delete-nested-linear-load-combination.v3",
            "nested_linear_load_combination_delete",
            "acyclic_nested_linear_static_depth_8_expanded_terms_64",
            "Installed CPU static/shared distribution E2E v48",
            "[0,-12000,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )

    nested_linear_load_combination_factor_edit_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-factor-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-nested-linear-load-combination-factor-edit-v1.md"),
        text=nested_linear_load_combination_factor_edit_doc,
        tokens=(
            "model-edit-nested-linear-load-combination-factor",
            "root-inclusive depth at most eight",
            "single C ABI into C++",
            "structural-native:model-edit-nested-linear-load-combination-factor.v1",
            "nested_linear_load_combination_factor_edit",
            "Installed CPU static/shared distribution E2E v50",
            "[25000,-9000,3750,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    nested_linear_load_combination_reference_edit_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-reference-edit-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path(
            "docs/native/modelir-nested-linear-load-combination-reference-edit-v1.md"
        ),
        text=nested_linear_load_combination_reference_edit_doc,
        tokens=(
            "model-edit-nested-linear-load-combination-reference",
            "root-inclusive depth at most eight",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-edit-nested-linear-load-combination-reference.v1",
            "nested_linear_load_combination_reference_edit",
            "append-only v52",
            "[0,-8000,2000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    direct_linear_load_combination_term_add_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-term-add-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-term-add-v1.md"),
        text=direct_linear_load_combination_term_add_doc,
        tokens=(
            "model-add-linear-load-combination-term",
            "two through 63",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-add-direct-linear-load-combination-term.v1",
            "direct_linear_load_combination_term_add",
            "append-only v53",
            "[25000,-12000,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    direct_linear_load_combination_term_delete_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-term-delete-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-term-delete-v1.md"),
        text=direct_linear_load_combination_term_delete_doc,
        tokens=(
            "model-delete-linear-load-combination-term",
            "three through 64",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-delete-direct-linear-load-combination-term.v1",
            "direct_linear_load_combination_term_delete",
            "append-only v54",
            "[25000,-12000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    direct_linear_load_combination_term_reorder_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-term-reorder-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-term-reorder-v1.md"),
        text=direct_linear_load_combination_term_reorder_doc,
        tokens=(
            "model-reorder-linear-load-combination-term",
            "two through 64",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-reorder-direct-linear-load-combination-term.v1",
            "direct_linear_load_combination_term_reorder",
            "append-only v58",
            "[25000,-12000,0,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    direct_linear_load_combination_term_insert_doc = _text(
        root,
        Path("docs/native/modelir-direct-linear-load-combination-term-insert-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path("docs/native/modelir-direct-linear-load-combination-term-insert-v1.md"),
        text=direct_linear_load_combination_term_insert_doc,
        tokens=(
            "model-insert-linear-load-combination-term",
            "two through 63",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-insert-direct-linear-load-combination-term.v1",
            "direct_linear_load_combination_term_insert",
            "append-only v59",
            "[25000,-12000,5000,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    nested_linear_load_combination_term_add_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-term-add-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path(
            "docs/native/modelir-nested-linear-load-combination-term-add-v1.md"
        ),
        text=nested_linear_load_combination_term_add_doc,
        tokens=(
            "model-add-nested-linear-load-combination-term",
            "two through 63",
            "root-inclusive depth at most eight",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-add-nested-linear-load-combination-term.v1",
            "nested_linear_load_combination_term_add",
            "append-only v55",
            "[25000,-6000,1500,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    nested_linear_load_combination_term_insert_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-term-insert-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path(
            "docs/native/modelir-nested-linear-load-combination-term-insert-v1.md"
        ),
        text=nested_linear_load_combination_term_insert_doc,
        tokens=(
            "model-insert-nested-linear-load-combination-term",
            "two through 63",
            "root-inclusive depth at most eight",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-insert-nested-linear-load-combination-term.v1",
            "nested_linear_load_combination_term_insert",
            "append-only v60",
            "[25000,-6000,1500,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    nested_linear_load_combination_term_delete_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-term-delete-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path(
            "docs/native/modelir-nested-linear-load-combination-term-delete-v1.md"
        ),
        text=nested_linear_load_combination_term_delete_doc,
        tokens=(
            "model-delete-nested-linear-load-combination-term",
            "three through 64",
            "root-inclusive depth at most eight",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-delete-nested-linear-load-combination-term.v1",
            "nested_linear_load_combination_term_delete",
            "append-only v56",
            "[0,-6000,1500,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )
    nested_linear_load_combination_term_reorder_doc = _text(
        root,
        Path("docs/native/modelir-nested-linear-load-combination-term-reorder-v1.md"),
        blockers,
    )
    _require_tokens(
        relative=Path(
            "docs/native/modelir-nested-linear-load-combination-term-reorder-v1.md"
        ),
        text=nested_linear_load_combination_term_reorder_doc,
        tokens=(
            "model-reorder-nested-linear-load-combination-term",
            "two through 64",
            "root-inclusive depth at most eight",
            "single C ABI into C++ semantic, reference and cycle validation",
            "structural-native:model-reorder-nested-linear-load-combination-term.v1",
            "nested_linear_load_combination_term_reorder",
            "append-only v57",
            "[0,-6000,1500,0,0,0]",
            "fallback 0",
            "approved HIP C2",
            "C6",
        ),
        blockers=blockers,
    )

    manifest = _json_object(root, CUTOVER_MANIFEST, blockers)
    expected_manifest = {
        "schema_version": "native-production-deployment-cutover.v1",
        "status": "implemented",
        "cutover_gate": "C5",
        "owner": "structural-workbench",
        "active_entrypoint": ACTIVE_CONTAINER.as_posix(),
        "active_runtime": "rust_cpp_cpu_only",
        "active_network_listener": False,
        "local_rootfs_isolation_harness": True,
        "local_rootfs_receipt_authority": "local_rootfs_diagnostic_c5",
        "customer_image_receipt": False,
        "c6_complete": False,
    }
    for field, expected in expected_manifest.items():
        if manifest.get(field) != expected:
            blockers.append(f"deployment_cutover_manifest_field_invalid:{field}")
    if manifest.get("active_runtime_interpreters") != []:
        blockers.append("deployment_cutover_active_interpreters_not_empty")
    retired = manifest.get("retired_entrypoints")
    retired_index = {
        str(row.get("path", "")): row
        for row in retired
        if isinstance(row, dict)
    } if isinstance(retired, list) else {}
    for path in (LEGACY_PAGES_WORKFLOW, LEGACY_PYTHON_CONTAINER):
        row = retired_index.get(path.as_posix())
        if (
            row is None
            or row.get("rollback_only") is not True
            or row.get("removal_allowed") is not False
        ):
            blockers.append(f"deployment_cutover_retired_entry_invalid:{path.as_posix()}")
    remaining = manifest.get("remaining_c6_blockers")
    if not isinstance(remaining, list) or len(remaining) < 4:
        blockers.append("deployment_cutover_c6_blockers_not_preserved")

    capabilities_payload = _json_object(
        root, Path("native/capabilities.json"), blockers
    )
    capabilities = capabilities_payload.get("capabilities")
    nodal_load_target_edit_capability = (
        capabilities.get("modelir_nodal_load_target_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nodal_load_target_edit_capability, dict):
        blockers.append("modelir_nodal_load_target_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nodal_load_target_edit_capability.get(field) != expected:
                blockers.append(
                    f"modelir_nodal_load_target_edit_capability_field_invalid:{field}"
                )
        nodal_load_target_edit_claim = str(
            nodal_load_target_edit_capability.get("claim", "")
        )
        for token in (
            "changes exactly one existing nodal-load node_id",
            "distinct existing node",
            "preserving load and pattern identity and contiguous indices",
            "all six finite SI components",
            "single C ABI into C++ semantic validation",
            "distribution v61 E2E",
            "exact active load [0,0,0,0,0,0,0,-10000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nodal_load_target_edit_claim:
                blockers.append(
                    "modelir_nodal_load_target_edit_capability_"
                    f"claim_missing:{token}"
                )
    constraint_target_edit_capability = (
        capabilities.get("modelir_fixed_constraint_target_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(constraint_target_edit_capability, dict):
        blockers.append("modelir_fixed_constraint_target_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if constraint_target_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_fixed_constraint_target_edit_capability_"
                    f"field_invalid:{field}"
                )
        constraint_target_edit_claim = str(
            constraint_target_edit_capability.get("claim", "")
        )
        for token in (
            "changes exactly one existing fixed_dofs constraint node_id",
            "distinct existing node",
            "preserving constraint identity and contiguous index",
            "restrained DOF mask",
            "single C ABI into C++ semantic validation",
            "distribution v62 E2E",
            "exact active DOFs [12,13,14,15,16,17]",
            "active load [0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in constraint_target_edit_claim:
                blockers.append(
                    "modelir_fixed_constraint_target_edit_capability_"
                    f"claim_missing:{token}"
                )
    fixed_constraint_dof_delete_capability = (
        capabilities.get("modelir_fixed_constraint_dof_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(fixed_constraint_dof_delete_capability, dict):
        blockers.append("modelir_fixed_constraint_dof_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if fixed_constraint_dof_delete_capability.get(field) != expected:
                blockers.append(
                    "modelir_fixed_constraint_dof_deletion_capability_"
                    f"field_invalid:{field}"
                )
        fixed_constraint_dof_delete_claim = str(
            fixed_constraint_dof_delete_capability.get("claim", "")
        )
        for token in (
            "removes exactly one named restrained DOF",
            "retaining at least one DOF",
            "matching explicit prescribed SI value",
            "single C ABI into C++ semantic validation",
            "distribution v63 E2E",
            "exact active DOFs [11,12,13,14,15,16,17]",
            "active load [0,0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in fixed_constraint_dof_delete_claim:
                blockers.append(
                    "modelir_fixed_constraint_dof_deletion_capability_"
                    f"claim_missing:{token}"
                )
    fixed_constraint_dof_add_capability = (
        capabilities.get("modelir_fixed_constraint_dof_addition")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(fixed_constraint_dof_add_capability, dict):
        blockers.append("modelir_fixed_constraint_dof_addition_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if fixed_constraint_dof_add_capability.get(field) != expected:
                blockers.append(
                    "modelir_fixed_constraint_dof_addition_capability_"
                    f"field_invalid:{field}"
                )
        fixed_constraint_dof_add_claim = str(
            fixed_constraint_dof_add_capability.get("claim", "")
        )
        for token in (
            "appends exactly one named previously unrestrained DOF",
            "explicit finite prescribed SI value",
            "same node fail closed before publication",
            "single C ABI into C++ semantic validation",
            "distribution v64 E2E",
            "exact active DOFs [12,13,14,15,16,17]",
            "active load [0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in fixed_constraint_dof_add_claim:
                blockers.append(
                    "modelir_fixed_constraint_dof_addition_capability_"
                    f"claim_missing:{token}"
                )
    fixed_constraint_dof_reorder_capability = (
        capabilities.get("modelir_fixed_constraint_dof_reorder")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(fixed_constraint_dof_reorder_capability, dict):
        blockers.append("modelir_fixed_constraint_dof_reorder_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if fixed_constraint_dof_reorder_capability.get(field) != expected:
                blockers.append(
                    "modelir_fixed_constraint_dof_reorder_capability_"
                    f"field_invalid:{field}"
                )
        fixed_constraint_dof_reorder_claim = str(
            fixed_constraint_dof_reorder_capability.get("claim", "")
        )
        for token in (
            "moves exactly one named restrained DOF",
            "distinct bounded final index",
            "all prescribed SI values",
            "single C ABI into C++ semantic validation",
            "distribution v65 E2E",
            "exact active DOFs [12,13,14,15,16,17]",
            "active load [0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in fixed_constraint_dof_reorder_claim:
                blockers.append(
                    "modelir_fixed_constraint_dof_reorder_capability_"
                    f"claim_missing:{token}"
                )
    fixed_constraint_identity_edit_capability = (
        capabilities.get("modelir_fixed_constraint_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(fixed_constraint_identity_edit_capability, dict):
        blockers.append("modelir_fixed_constraint_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if fixed_constraint_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_fixed_constraint_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        fixed_constraint_identity_edit_claim = str(
            fixed_constraint_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced fixed_dofs constraint identity",
            "distinct unique ModelIR stable ID",
            "construction-stage, unsupported-feature or round-trip ownership",
            "single C ABI into C++ semantic validation",
            "distribution v66 E2E",
            "exact active DOFs [12,13,14,15,16,17]",
            "active load [0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in fixed_constraint_identity_edit_claim:
                blockers.append(
                    "modelir_fixed_constraint_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    nodal_load_identity_edit_capability = (
        capabilities.get("modelir_nodal_load_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nodal_load_identity_edit_capability, dict):
        blockers.append("modelir_nodal_load_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nodal_load_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_nodal_load_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        nodal_load_identity_edit_claim = str(
            nodal_load_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing nodal-load identity",
            "distinct globally unique ModelIR stable ID",
            "unsupported-feature ownership",
            "containing load-pattern round-trip claim is conservatively degraded",
            "single C ABI into C++ semantic validation",
            "distribution v67 E2E",
            "exact active DOFs [12,13,14,15,16,17]",
            "active load [0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in nodal_load_identity_edit_claim:
                blockers.append(
                    "modelir_nodal_load_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    linear_load_pattern_identity_edit_capability = (
        capabilities.get("modelir_linear_load_pattern_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_load_pattern_identity_edit_capability, dict):
        blockers.append("modelir_linear_load_pattern_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_load_pattern_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_load_pattern_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        linear_load_pattern_identity_edit_claim = str(
            linear_load_pattern_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced linear_static load-pattern identity",
            "distinct unique ModelIR stable ID",
            "load-combination term, construction stage, unsupported-feature row or round-trip mapping",
            "single C ABI into C++ semantic validation",
            "distribution v68 E2E",
            "exact active DOFs [12,13,14,15,16,17]",
            "active load [0,-1000,0,0,0,0]",
            "byte-identical initialized-checkpoint restart",
            "fallback 0",
            "C6 remain separate or open",
        ):
            if token not in linear_load_pattern_identity_edit_claim:
                blockers.append(
                    "modelir_linear_load_pattern_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    linear_material_identity_edit_capability = (
        capabilities.get("modelir_linear_material_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_material_identity_edit_capability, dict):
        blockers.append("modelir_linear_material_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_material_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_material_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        linear_material_identity_edit_claim = str(
            linear_material_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced parameter-set-v1 linear_elastic_isotropic material ID",
            "distinct unique stable ID",
            "element material_id references",
            "section steel_material_id or concrete_material_id references",
            "unsupported-feature ownership and direct round-trip mappings",
            "single C ABI into C++ semantic/reference validation",
            "distribution v69 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "active load [0,-10000,0,0,0,0]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in linear_material_identity_edit_claim:
                blockers.append(
                    "modelir_linear_material_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    frame_section_identity_edit_capability = (
        capabilities.get("modelir_frame_section_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(frame_section_identity_edit_capability, dict):
        blockers.append("modelir_frame_section_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if frame_section_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_frame_section_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        frame_section_identity_edit_claim = str(
            frame_section_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced parameter-set-v1 frame_3d section ID",
            "distinct unique stable ID",
            "element section_id references",
            "unsupported-feature ownership and direct round-trip mappings",
            "single C ABI into C++ semantic/reference validation",
            "distribution v70 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "active load [0,-10000,0,0,0,0]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in frame_section_identity_edit_claim:
                blockers.append(
                    "modelir_frame_section_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    truss_section_identity_edit_capability = (
        capabilities.get("modelir_truss_section_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(truss_section_identity_edit_capability, dict):
        blockers.append("modelir_truss_section_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if truss_section_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_truss_section_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        truss_section_identity_edit_claim = str(
            truss_section_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced parameter-set-v1 truss_3d section ID",
            "distinct unique stable ID",
            "element section_id references",
            "unsupported-feature ownership and direct round-trip mappings",
            "single C ABI into C++ semantic/reference validation",
            "distribution v71 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "active load [0,-10000,0,0,0,0]",
            "typed frame-plus-truss recovery [1,2] with offsets [0,12,15]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in truss_section_identity_edit_claim:
                blockers.append(
                    "modelir_truss_section_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    node_identity_edit_capability = (
        capabilities.get("modelir_node_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(node_identity_edit_capability, dict):
        blockers.append("modelir_node_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if node_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_node_identity_edit_capability_" f"field_invalid:{field}"
                )
        node_identity_edit_claim = str(node_identity_edit_capability.get("claim", ""))
        for token in (
            "replaces exactly one existing unreferenced node ID",
            "distinct unique stable ID",
            "element node_ids references",
            "constraint node_id references",
            "nested nodal-load node_id references",
            "unsupported-feature ownership and direct round-trip mappings",
            "single C ABI into C++ semantic/reference validation",
            "distribution v72 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "active load [0,-10000,0,0,0,0]",
            "typed frame recovery [1] with offsets [0,12]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in node_identity_edit_claim:
                blockers.append(
                    "modelir_node_identity_edit_capability_" f"claim_missing:{token}"
                )
    element_identity_edit_capability = (
        capabilities.get("modelir_element_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(element_identity_edit_capability, dict):
        blockers.append("modelir_element_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if element_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_element_identity_edit_capability_" f"field_invalid:{field}"
                )
        element_identity_edit_claim = str(
            element_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced element ID",
            "distinct unique stable ID",
            "construction-stage active_element_ids references",
            "unsupported-feature source_entity_id ownership",
            "direct round-trip model_ir_entity_id mappings",
            "single C ABI into C++ semantic/reference validation",
            "distribution v73 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "active load [0,-10000,0,0,0,0]",
            "typed frame recovery [1] with offsets [0,12]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in element_identity_edit_claim:
                blockers.append(
                    "modelir_element_identity_edit_capability_" f"claim_missing:{token}"
                )
    model_identity_edit_capability = (
        capabilities.get("modelir_model_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(model_identity_edit_capability, dict):
        blockers.append("modelir_model_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if model_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_model_identity_edit_capability_" f"field_invalid:{field}"
                )
        model_identity_edit_claim = str(model_identity_edit_capability.get("claim", ""))
        for token in (
            "exact expected source model_id",
            "distinct replacement satisfying the stable-ID grammar",
            "C++-canonical source document with model_id removed",
            "every entity family",
            "unsupported-feature source_entity_id ownership of either source or replacement",
            "single C ABI into C++ semantic/reference validation",
            "distribution v75 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "combined active load [25000,-12000,5000,0,0,0]",
            "typed frame recovery [1] with offsets [0,12]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in model_identity_edit_claim:
                blockers.append(
                    "modelir_model_identity_edit_capability_" f"claim_missing:{token}"
                )

    node_identity_cascade_capability = (
        capabilities.get("modelir_node_identity_cascade_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(node_identity_cascade_capability, dict):
        blockers.append("modelir_node_identity_cascade_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if node_identity_cascade_capability.get(field) != expected:
                blockers.append(
                    "modelir_node_identity_cascade_edit_capability_"
                    f"field_invalid:{field}"
                )
        node_identity_cascade_claim = str(node_identity_cascade_capability.get("claim", ""))
        for token in (
            "replaces exactly one existing referenced node ID",
            "atomically updates every typed elements[].node_ids",
            "direct node round-trip model_ir_entity_id",
            "exact or canonicalized direct mappings degrade to approximated",
            "unsupported-feature source_entity_id ownership of either source or replacement",
            "single C ABI into C++ semantic/reference validation",
            "distribution v76 E2E",
            "N2_LINKED",
            "exact active DOFs [6,7,8,9,10,11]",
            "combined active load [25000,-12000,5000,0,0,0]",
            "typed frame recovery [1] with offsets [0,12]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in node_identity_cascade_claim:
                blockers.append(
                    "modelir_node_identity_cascade_edit_capability_"
                    f"claim_missing:{token}"
                )

    linear_load_combination_identity_edit_capability = (
        capabilities.get("modelir_linear_load_combination_identity_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_load_combination_identity_edit_capability, dict):
        blockers.append("modelir_linear_load_combination_identity_edit_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_load_combination_identity_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_load_combination_identity_edit_capability_"
                    f"field_invalid:{field}"
                )
        linear_load_combination_identity_edit_claim = str(
            linear_load_combination_identity_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing unreferenced direct or acyclic nested linear combination ID",
            "distinct unique stable ID",
            "two through 64 unique linear-static pattern terms",
            "depth at most eight and at most 64 expanded terms",
            "load-pattern-ambiguous",
            "downstream load-combination references",
            "unsupported-feature source_entity_id ownership",
            "direct round-trip model_ir_entity_id mappings",
            "single C ABI into C++ semantic/reference validation",
            "distribution v74 E2E",
            "exact active DOFs [6,7,8,9,10,11]",
            "combined active load [25000,-12000,5000,0,0,0]",
            "typed frame recovery [1] with offsets [0,12]",
            "byte-identical initialized restart",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in linear_load_combination_identity_edit_claim:
                blockers.append(
                    "modelir_linear_load_combination_identity_edit_capability_"
                    f"claim_missing:{token}"
                )
    linear_load_combination_deletion_capability = (
        capabilities.get("modelir_linear_load_combination_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_load_combination_deletion_capability, dict):
        blockers.append("modelir_linear_load_combination_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_load_combination_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_load_combination_deletion_capability_"
                    f"field_invalid:{field}"
                )
        linear_load_combination_deletion_claim = str(
            linear_load_combination_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous source-neutral extension-free unreferenced linear combination",
            "exactly two ordered terms",
            "single C ABI into C++",
            "checkpoint/restart parity",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in linear_load_combination_deletion_claim:
                blockers.append(
                    "modelir_linear_load_combination_deletion_capability_"
                    f"claim_missing:{token}"
                )
    linear_load_combination_execution_capability = (
        capabilities.get("modelir_linear_load_combination_execution")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_load_combination_execution_capability, dict):
        blockers.append("modelir_linear_load_combination_execution_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_load_combination_execution_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_load_combination_execution_capability_"
                    f"field_invalid:{field}"
                )
        linear_load_combination_execution_claim = str(
            linear_load_combination_execution_capability.get("claim", "")
        )
        for token in (
            "frozen ABI v1.13 table",
            "unambiguous load-case selector",
            "exactly two distinct direct linear_static patterns",
            "distribution v44 E2E",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in linear_load_combination_execution_claim:
                blockers.append(
                    "modelir_linear_load_combination_execution_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_capability = (
        capabilities.get("modelir_direct_linear_load_combination_authoring_execution")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_authoring_execution_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_authoring_execution_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_claim = str(
            direct_linear_load_combination_capability.get("claim", "")
        )
        for token in (
            "two through 64 ordered terms",
            "exact two-term v1 provenance and request-receipt contract",
            "frozen ABI v1.13 table",
            "distribution v45 E2E",
            "exact three-pattern active external load",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_authoring_execution_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_factor_edit_capability = (
        capabilities.get("modelir_direct_linear_load_combination_factor_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_factor_edit_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_factor_edit_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_factor_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_factor_edit_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_factor_edit_claim = str(
            direct_linear_load_combination_factor_edit_capability.get("claim", "")
        )
        for token in (
            "changes exactly one existing factor",
            "reference kind, reference identity, term order, term count",
            "single C ABI into C++ semantic/reference validation",
            "distribution v49 E2E",
            "exact active load [25000,-13500,5000,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_factor_edit_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_factor_edit_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_reference_edit_capability = (
        capabilities.get("modelir_direct_linear_load_combination_reference_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_reference_edit_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_reference_edit_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if (
                direct_linear_load_combination_reference_edit_capability.get(field)
                != expected
            ):
                blockers.append(
                    "modelir_direct_linear_load_combination_reference_edit_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_reference_edit_claim = str(
            direct_linear_load_combination_reference_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing load_pattern term identity",
            "every factor, term order/count",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v51 E2E",
            "exact active load [120000,0,5000,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_reference_edit_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_reference_edit_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_term_add_capability = (
        capabilities.get("modelir_direct_linear_load_combination_term_add")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_term_add_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_term_add_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_term_add_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_add_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_term_add_claim = str(
            direct_linear_load_combination_term_add_capability.get("claim", "")
        )
        for token in (
            "appends exactly one new load_pattern term",
            "two through 63 ordered unique existing linear_static pattern terms",
            "yielding three through 64 terms",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v53 E2E",
            "exact active load [25000,-12000,5000,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_term_add_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_add_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_term_delete_capability = (
        capabilities.get("modelir_direct_linear_load_combination_term_delete")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_term_delete_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_term_delete_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_term_delete_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_delete_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_term_delete_claim = str(
            direct_linear_load_combination_term_delete_capability.get("claim", "")
        )
        for token in (
            "removes exactly one existing load_pattern term selected by identity",
            "three through 64 ordered unique existing linear_static pattern terms",
            "yielding two through 63 terms",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v54 E2E",
            "exact active load [25000,-12000,0,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_term_delete_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_delete_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_term_reorder_capability = (
        capabilities.get("modelir_direct_linear_load_combination_term_reorder")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_term_reorder_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_term_reorder_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_term_reorder_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_reorder_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_term_reorder_claim = str(
            direct_linear_load_combination_term_reorder_capability.get("claim", "")
        )
        for token in (
            "moves exactly one existing load_pattern term selected by identity",
            "two through 64 ordered unique existing linear_static pattern terms",
            "distinct final zero-based index",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v58 E2E",
            "exact retained active load [25000,-12000,0,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_term_reorder_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_reorder_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_term_insert_capability = (
        capabilities.get("modelir_direct_linear_load_combination_term_insert")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_term_insert_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_term_insert_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_term_insert_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_insert_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_term_insert_claim = str(
            direct_linear_load_combination_term_insert_capability.get("claim", "")
        )
        for token in (
            "inserts exactly one new load_pattern term",
            "two through 63 ordered unique existing linear_static pattern terms",
            "explicit final zero-based index from zero through the source term count",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v59 E2E",
            "exact active load [25000,-12000,5000,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_term_insert_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_term_insert_capability_"
                    f"claim_missing:{token}"
                )
    nested_linear_load_combination_term_add_capability = (
        capabilities.get("modelir_nested_linear_load_combination_term_add")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nested_linear_load_combination_term_add_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_term_add_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_term_add_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_add_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_term_add_claim = str(
            nested_linear_load_combination_term_add_capability.get("claim", "")
        )
        for token in (
            "appends exactly one new explicitly typed load_pattern or load_combination term",
            "two through 63 ordered unique typed terms",
            "yielding three through 64 root terms",
            "root-inclusive depth at most eight",
            "at most 64 expanded leaf contributions",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v55 E2E",
            "exact active load [25000,-6000,1500,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_term_add_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_add_capability_"
                    f"claim_missing:{token}"
                )
    nested_linear_load_combination_term_insert_capability = (
        capabilities.get("modelir_nested_linear_load_combination_term_insert")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nested_linear_load_combination_term_insert_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_term_insert_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_term_insert_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_insert_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_term_insert_claim = str(
            nested_linear_load_combination_term_insert_capability.get("claim", "")
        )
        for token in (
            "inserts exactly one new explicitly typed load_pattern or load_combination term",
            "two through 63 ordered unique typed terms",
            "explicit final zero-based index from zero through the source root-term count",
            "yielding three through 64 root terms",
            "root-inclusive depth at most eight",
            "at most 64 expanded leaf contributions",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v60 E2E",
            "exact active load [25000,-6000,1500,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_term_insert_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_insert_capability_"
                    f"claim_missing:{token}"
                )
    nested_linear_load_combination_term_delete_capability = (
        capabilities.get("modelir_nested_linear_load_combination_term_delete")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nested_linear_load_combination_term_delete_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_term_delete_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_term_delete_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_delete_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_term_delete_claim = str(
            nested_linear_load_combination_term_delete_capability.get("claim", "")
        )
        for token in (
            "removes exactly one existing explicitly typed load_pattern or load_combination root term",
            "three through 64 ordered unique typed terms",
            "yielding two through 63 root terms",
            "edited root must retain at least one load_combination reference",
            "root-inclusive depth at most eight",
            "at most 64 expanded leaf contributions",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v56 E2E",
            "exact active load [0,-6000,1500,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_term_delete_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_delete_capability_"
                    f"claim_missing:{token}"
                )
    nested_linear_load_combination_term_reorder_capability = (
        capabilities.get("modelir_nested_linear_load_combination_term_reorder")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nested_linear_load_combination_term_reorder_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_term_reorder_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_term_reorder_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_reorder_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_term_reorder_claim = str(
            nested_linear_load_combination_term_reorder_capability.get("claim", "")
        )
        for token in (
            "moves exactly one existing explicitly typed load_pattern or load_combination root term",
            "two through 64 ordered unique typed terms",
            "distinct final zero-based index",
            "root-inclusive depth at most eight",
            "at most 64 expanded leaf contributions",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v57 E2E",
            "exact retained active load [0,-6000,1500,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_term_reorder_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_term_reorder_capability_"
                    f"claim_missing:{token}"
                )
    direct_linear_load_combination_deletion_capability = (
        capabilities.get("modelir_direct_linear_load_combination_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(direct_linear_load_combination_deletion_capability, dict):
        blockers.append(
            "modelir_direct_linear_load_combination_deletion_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if direct_linear_load_combination_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_direct_linear_load_combination_deletion_capability_"
                    f"field_invalid:{field}"
                )
        direct_linear_load_combination_deletion_claim = str(
            direct_linear_load_combination_deletion_capability.get("claim", "")
        )
        for token in (
            "two through 64 ordered terms",
            "exact-two v1 provenance/receipt field set",
            "explicit v2 deletion provenance",
            "single C ABI into C++ reference/cycle validation",
            "distribution v47 E2E",
            "exact restored direct-pattern active load",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in direct_linear_load_combination_deletion_claim:
                blockers.append(
                    "modelir_direct_linear_load_combination_deletion_capability_"
                    f"claim_missing:{token}"
                )
    nested_linear_load_combination_capability = (
        capabilities.get("modelir_nested_linear_load_combination_authoring_execution")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nested_linear_load_combination_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_authoring_execution_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_authoring_execution_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_claim = str(
            nested_linear_load_combination_capability.get("claim", "")
        )
        for token in (
            "root-inclusive depth at most eight",
            "at most 64 expanded leaf contributions",
            "repeated-path factor consolidation",
            "frozen ABI v1.13 table",
            "v3 provenance plus a self-hashed v3 request receipt",
            "distribution v46 E2E",
            "exact nested active external load",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_authoring_execution_capability_"
                    f"claim_missing:{token}"
                )
    nested_linear_load_combination_deletion_capability = (
        capabilities.get("modelir_nested_linear_load_combination_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    nested_linear_load_combination_factor_edit_capability = (
        capabilities.get("modelir_nested_linear_load_combination_factor_edit")
        if isinstance(capabilities, dict)
        else None
    )
    nested_linear_load_combination_reference_edit_capability = (
        capabilities.get("modelir_nested_linear_load_combination_reference_edit")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(nested_linear_load_combination_factor_edit_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_factor_edit_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_factor_edit_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_factor_edit_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_factor_edit_claim = str(
            nested_linear_load_combination_factor_edit_capability.get("claim", "")
        )
        for token in (
            "changes exactly one existing root factor",
            "explicit load_pattern or load_combination reference kind and identity",
            "root term order/count",
            "descendant combinations",
            "root-inclusive depth at most eight",
            "both complete expansions",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v50 E2E",
            "exact active load [25000,-9000,3750,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_factor_edit_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_factor_edit_capability_"
                    f"claim_missing:{token}"
                )
    if not isinstance(nested_linear_load_combination_reference_edit_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_reference_edit_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if (
                nested_linear_load_combination_reference_edit_capability.get(field)
                != expected
            ):
                blockers.append(
                    "modelir_nested_linear_load_combination_reference_edit_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_reference_edit_claim = str(
            nested_linear_load_combination_reference_edit_capability.get("claim", "")
        )
        for token in (
            "replaces exactly one existing root load_pattern or load_combination reference",
            "explicit source and replacement kinds and identities",
            "selected factor, root term order/count",
            "descendant combinations",
            "root-inclusive depth at most eight",
            "both complete expansions",
            "single C ABI into C++ semantic/reference/cycle validation",
            "distribution v52 E2E",
            "exact active load [0,-8000,2000,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_reference_edit_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_reference_edit_capability_"
                    f"claim_missing:{token}"
                )
    if not isinstance(nested_linear_load_combination_deletion_capability, dict):
        blockers.append(
            "modelir_nested_linear_load_combination_deletion_capability_missing"
        )
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if nested_linear_load_combination_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_nested_linear_load_combination_deletion_capability_"
                    f"field_invalid:{field}"
                )
        nested_linear_load_combination_deletion_claim = str(
            nested_linear_load_combination_deletion_capability.get("claim", "")
        )
        for token in (
            "two through 64 uniquely typed pattern/combination terms",
            "root-inclusive depth at most eight",
            "at most 64 expanded leaf contributions",
            "single C ABI into C++ reference/cycle validation",
            "direct exact-two v1",
            "explicit v3 root/expanded-term provenance",
            "distribution v48 E2E",
            "retaining and executing the child combination",
            "exact active load [0,-12000,5000,0,0,0]",
            "byte-identical direct/restart output",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in nested_linear_load_combination_deletion_claim:
                blockers.append(
                    "modelir_nested_linear_load_combination_deletion_capability_"
                    f"claim_missing:{token}"
                )
    truss_editing_capability = capabilities.get("modelir_truss3d_editing") if isinstance(
        capabilities, dict
    ) else None
    if not isinstance(truss_editing_capability, dict):
        blockers.append("modelir_truss3d_editing_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if truss_editing_capability.get(field) != expected:
                blockers.append(
                    f"modelir_truss3d_editing_capability_field_invalid:{field}"
                )
        truss_editing_claim = str(truss_editing_capability.get("claim", ""))
        for token in (
            "replaces one finite positive area",
            "atomically reassigns one existing truss_3d element",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in truss_editing_claim:
                blockers.append(
                    f"modelir_truss3d_editing_capability_claim_missing:{token}"
                )
    fixed_constraint_deletion_capability = (
        capabilities.get("modelir_fixed_constraint_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(fixed_constraint_deletion_capability, dict):
        blockers.append("modelir_fixed_constraint_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if fixed_constraint_deletion_capability.get(field) != expected:
                blockers.append(
                    f"modelir_fixed_constraint_deletion_capability_field_invalid:{field}"
                )
        fixed_constraint_deletion_claim = str(
            fixed_constraint_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral homogeneous six-DOF zero fixed_dofs row",
            "construction-stage/unsupported-feature/round-trip reference",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in fixed_constraint_deletion_claim:
                blockers.append(
                    f"modelir_fixed_constraint_deletion_capability_claim_missing:{token}"
                )
    linear_load_pattern_deletion_capability = (
        capabilities.get("modelir_linear_load_pattern_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_load_pattern_deletion_capability, dict):
        blockers.append("modelir_linear_load_pattern_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_load_pattern_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_load_pattern_deletion_capability_"
                    f"field_invalid:{field}"
                )
        linear_load_pattern_deletion_claim = str(
            linear_load_pattern_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral zero-self-weight linear_static pattern",
            "load-combination and construction-stage references",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in linear_load_pattern_deletion_claim:
                blockers.append(
                    "modelir_linear_load_pattern_deletion_capability_"
                    f"claim_missing:{token}"
                )
    linear_material_deletion_capability = (
        capabilities.get("modelir_linear_material_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(linear_material_deletion_capability, dict):
        blockers.append("modelir_linear_material_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if linear_material_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_linear_material_deletion_capability_"
                    f"field_invalid:{field}"
                )
        linear_material_deletion_claim = str(
            linear_material_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral unreferenced parameter-set-v1 linear_elastic_isotropic material",
            "element material_id references",
            "section steel_material_id or concrete_material_id references",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in linear_material_deletion_claim:
                blockers.append(
                    "modelir_linear_material_deletion_capability_"
                    f"claim_missing:{token}"
                )
    frame_section_deletion_capability = (
        capabilities.get("modelir_frame_section_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(frame_section_deletion_capability, dict):
        blockers.append("modelir_frame_section_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if frame_section_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_frame_section_deletion_capability_"
                    f"field_invalid:{field}"
                )
        frame_section_deletion_claim = str(
            frame_section_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral unreferenced parameter-set-v1 frame_3d section",
            "element section_id references",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in frame_section_deletion_claim:
                blockers.append(
                    "modelir_frame_section_deletion_capability_"
                    f"claim_missing:{token}"
                )
    truss_section_deletion_capability = (
        capabilities.get("modelir_truss_section_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(truss_section_deletion_capability, dict):
        blockers.append("modelir_truss_section_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if truss_section_deletion_capability.get(field) != expected:
                blockers.append(
                    "modelir_truss_section_deletion_capability_"
                    f"field_invalid:{field}"
                )
        truss_section_deletion_claim = str(
            truss_section_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral unreferenced parameter-set-v1 truss_3d section",
            "element section_id references",
            "another truss_3d section",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in truss_section_deletion_claim:
                blockers.append(
                    "modelir_truss_section_deletion_capability_"
                    f"claim_missing:{token}"
                )
    frame_leaf_deletion_capability = (
        capabilities.get("modelir_frame3d_leaf_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(frame_leaf_deletion_capability, dict):
        blockers.append("modelir_frame3d_leaf_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if frame_leaf_deletion_capability.get(field) != expected:
                blockers.append(
                    f"modelir_frame3d_leaf_deletion_capability_field_invalid:{field}"
                )
        frame_leaf_deletion_claim = str(
            frame_leaf_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral frame_3d/euler_bernoulli_3d member",
            "last contiguous orphan endpoint node",
            "local rotation, offsets, releases",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in frame_leaf_deletion_claim:
                blockers.append(
                    f"modelir_frame3d_leaf_deletion_capability_claim_missing:{token}"
                )
    truss_leaf_deletion_capability = (
        capabilities.get("modelir_truss3d_leaf_deletion")
        if isinstance(capabilities, dict)
        else None
    )
    if not isinstance(truss_leaf_deletion_capability, dict):
        blockers.append("modelir_truss3d_leaf_deletion_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if truss_leaf_deletion_capability.get(field) != expected:
                blockers.append(
                    f"modelir_truss3d_leaf_deletion_capability_field_invalid:{field}"
                )
        truss_leaf_deletion_claim = str(
            truss_leaf_deletion_capability.get("claim", "")
        )
        for token in (
            "last contiguous neutral truss_3d/linear_truss_3d member",
            "last contiguous orphan endpoint node",
            "installed static/shared E2E",
            "fallback 0",
            "C6 remain open",
        ):
            if token not in truss_leaf_deletion_claim:
                blockers.append(
                    f"modelir_truss3d_leaf_deletion_capability_claim_missing:{token}"
                )
    capability = capabilities.get("native_deployment") if isinstance(
        capabilities, dict
    ) else None
    if not isinstance(capability, dict):
        blockers.append("native_deployment_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-workbench"),
        ):
            if capability.get(field) != expected:
                blockers.append(f"native_deployment_capability_field_invalid:{field}")
        capability_claim = str(capability.get("claim", ""))
        for token in (
            "cpu-only static native distribution",
            "no network namespace, listener, port, secret, Python, Node or React runtime",
            "ModelIR/MGT/ModelIR-linear/normalized-MGT-linear flows",
            "CPU static/shared distribution v50 E2E",
            "standalone neutral-node creation",
            "last-neutral orphan-node deletion",
            "two-pattern linear-load-combination creation",
            "last-neutral exact-two linear-load-combination deletion",
            "bounded two-pattern linear-load-combination CPU execution",
            "bounded two-through-64 direct linear-load-combination authoring and CPU execution",
            "bounded direct linear-load-combination single-factor editing",
            "[25000,-13500,5000,0,0,0]",
            "bounded nested linear-load-combination typed-root-factor editing",
            "[25000,-9000,3750,0,0,0]",
            "bounded two-through-64 direct linear-load-combination deletion",
            "bounded acyclic nested linear-load-combination authoring and CPU execution",
            "bounded acyclic nested linear-load-combination deletion",
            "retained child-combination execution",
            "last-neutral fixed-constraint deletion",
            "last-neutral nodal-load deletion",
            "last-neutral linear-load-pattern deletion",
            "last-neutral linear-material deletion",
            "last-neutral frame-section deletion",
            "last-neutral truss-section deletion",
            "last-neutral-frame-leaf deletion",
            "last-neutral-truss-leaf deletion",
            "removed-frame-field binding",
            "v6 self-hashed local_rootfs_diagnostic_c5 receipt",
            "final C6 remain open",
        ):
            if token not in capability_claim:
                blockers.append(f"native_deployment_capability_claim_missing:{token}")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-deployment-cutover-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": manifest.get("cutover_gate"),
        "active_entrypoint": manifest.get("active_entrypoint"),
        "active_workflow_count": len(active_workflows),
        "active_pages_deployment_authority": False if not blockers else any(
            blocker.startswith("active_pages_deployment_authority")
            or blocker == "legacy_pages_workflow_still_active"
            for blocker in blockers
        ),
        "active_runtime_interpreters": manifest.get("active_runtime_interpreters"),
        "customer_image_receipt": False,
        "local_rootfs_isolation_harness": manifest.get(
            "local_rootfs_isolation_harness"
        ),
        "local_rootfs_receipt_authority": manifest.get(
            "local_rootfs_receipt_authority"
        ),
        "c6_complete": False,
        "blockers": blockers,
        "claim_boundary": (
            "This proves the bounded Pages/Python-on-prem deployment authority cutover and "
            "checked-in CPU image contract. It does not prove an external image build/scan/sign, "
            "global Python/Node removal, general GUI parity, protected HIP C2, or final C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args()
    report = check_native_deployment_cutover(args.repo_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native deployment cutover: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not report["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
