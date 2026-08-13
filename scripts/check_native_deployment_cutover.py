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
    Path("scripts/run_native_rootfs_isolation_e2e.sh"),
    Path("scripts/build_onprem_deployment_packaging_manifest.py"),
    Path("native/capabilities.json"),
    Path("docs/native/deployment-cutover-v1.md"),
    Path("docs/native/distribution-lifecycle.md"),
    Path("docs/native/rust-native-workbench-v1.md"),
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
            "model-edit-node",
            "model-edit-nodal-load",
            "model-edit-constraint-value",
            "model-edit-linear-material",
            "model-edit-frame-section",
            "model-edit-frame-element-orientation",
            "model-edit-element-connectivity",
            "model-add-frame3d-member",
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
        "structural-native-distribution-e2e.v23",
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
