#!/usr/bin/env python3
"""Fingerprint the product artifact DAG and invalidate stale descendants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_DAG = ROOT / "canonical/generated-artifact-dag.v1.json"
LEGACY_STATE_SCHEMA_VERSION = "generated-artifact-dag-state.v1"
STATE_SCHEMA_VERSION = "generated-artifact-dag-state.v2"
REPORT_SCHEMA_VERSION = "generated-artifact-dag-report.v2"
FULL_STATE = "full"
CANDIDATE_STATE = "candidate"
ALLOWED_NODE_KINDS = {"source", "generated", "receipt", "product-state"}
EXPECTED_NODE_KINDS = {
    "capability-registry": "source",
    "generated-capability-surfaces": "generated",
    "verification-receipts": "receipt",
    "product-state": "product-state",
}
EXPECTED_NODE_ORDER = tuple(EXPECTED_NODE_KINDS)
RELEASE_LEAF_INPUTS = [
    "package.json",
    "package-lock.json",
    "scripts/build_runtime_packaging_manifest.py",
    "scripts/build_frontend_dependency_audit_report.py",
    "scripts/report_pm_release_gate.py",
    "scripts/build_pm_release_blocker_action_register.py",
    "scripts/build_pm_release_blocker_closure_board.py",
    "scripts/build_product_readiness_snapshot.py",
    "scripts/build_structural_product_development_roadmap.py",
]
RELEASE_LEAF_OUTPUTS = [
    "implementation/phase1/native_runtime_artifact_manifest.json",
    "implementation/phase1/production_runtime_packaging_manifest.json",
    "implementation/phase1/runtime_sbom.json",
    "implementation/phase1/runtime_version_compatibility_matrix.json",
    "implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json",
    "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json",
    "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
    "implementation/phase1/release_evidence/productization/structural_product_development_roadmap.json",
]
EVIDENCE_OUTPUT_ONLY_PATHS = {
    *RELEASE_LEAF_OUTPUTS,
    "implementation/phase1/release_evidence/productization/"
    "structural_product_development_roadmap.md",
}
TRUSTED_GIT = Path("/usr/bin/git")
EXPECTED_NODE_PATHS = {
    "capability-registry": {
        "inputs": ["artifacts/manifests/capabilities.yaml"],
        "outputs": [],
    },
    "generated-capability-surfaces": {
        "inputs": ["scripts/generate_capability_surfaces.py"],
        "outputs": [
            "README.md",
            "docs/api-capabilities.md",
            "src/structural_analysis/generated_capabilities.py",
            "src/workbench-v2/model/generatedCapabilities.json",
        ],
    },
    "verification-receipts": {
        "inputs": [
            "canonical/verification-environment.v1.json",
            "canonical/requirements-cp312-manylinux2014-x86_64.lock",
            "canonical/canonical-project-wheel-contract.v1.schema.json",
            "canonical/canonical-verification-receipt.v1.schema.json",
            "scripts/build_canonical_project_wheel.py",
            "scripts/build_canonical_verification_receipt.py",
            "scripts/verify_bounded_planar_wheel_smoke.py",
            *RELEASE_LEAF_INPUTS,
        ],
        "outputs": [
            "artifacts/manifests/canonical_verification_environment.current.v1.json",
            ".ci/canonical-project-wheel-contract.json",
            ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl",
            *RELEASE_LEAF_OUTPUTS,
        ],
    },
    "product-state": {
        "inputs": [
            "canonical/product-state.current.v1.schema.json",
            "scripts/build_product_state.py",
        ],
        "outputs": ["artifacts/manifests/product_state.current.v1.json"],
    },
}
LEGACY_EXPECTED_NODE_PATHS = {
    **EXPECTED_NODE_PATHS,
    "verification-receipts": {
        "inputs": [
            "canonical/verification-environment.v1.json",
            "canonical/requirements-cp312-manylinux2014-x86_64.lock",
        ],
        "outputs": [
            "artifacts/manifests/canonical_verification_environment.current.v1.json"
        ],
    },
    "product-state": {
        "inputs": ["scripts/build_product_state.py"],
        "outputs": ["artifacts/manifests/product_state.current.v1.json"],
    },
}
CURRENT_BINDING_VALIDATORS = {
    "capability-registry": "capability-registry-schema-and-evidence.v2",
    "generated-capability-surfaces": "capability-surface-exact-render.v2",
    "verification-receipts": "canonical-wheel-and-release-leaves.v2",
    "product-state": "product-state-exact-producer-rebuild.v1",
}
PRODUCT_STATE_NIGHTLY_SOURCE = "github_api_refs_heads_main_pre_build"
PRODUCT_STATE_EXTERNAL_CODE_RECEIPT = Path(
    ".ci/product-state-inputs/code-to-code-receipt.json"
)
PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT = Path(
    ".ci/product-state-inputs/modal-buckling-receipt.json"
)


class ArtifactDAGError(ValueError):
    """Raised when the artifact DAG contract is malformed."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ArtifactDAGError(f"{path}: root must be an object")
    return payload


def _safe_path(value: Any) -> str:
    text = str(value).strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ArtifactDAGError(f"unsafe repository-relative path: {value!r}")
    return path.as_posix()


def load_dag(
    path: Path = DEFAULT_DAG,
    *,
    enforce_canonical_paths: bool = True,
) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != "generated-artifact-dag.v1":
        raise ArtifactDAGError("unsupported artifact DAG schema")
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ArtifactDAGError("nodes must be a non-empty list")
    nodes: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ArtifactDAGError("each node must be an object")
        node_id = str(raw_node.get("id", "")).strip()
        if not node_id or node_id in ids:
            raise ArtifactDAGError(f"invalid or duplicate node id: {node_id!r}")
        ids.add(node_id)
        kind = str(raw_node.get("kind", "")).strip()
        if kind not in ALLOWED_NODE_KINDS:
            raise ArtifactDAGError(f"{node_id}: unsupported node kind {kind!r}")
        expected_kind = EXPECTED_NODE_KINDS.get(node_id)
        if expected_kind is not None and kind != expected_kind:
            raise ArtifactDAGError(
                f"{node_id}: kind must be {expected_kind!r}, got {kind!r}"
            )
        dependencies = raw_node.get("dependencies")
        inputs = raw_node.get("inputs")
        outputs = raw_node.get("outputs")
        if not all(
            isinstance(value, list) for value in (dependencies, inputs, outputs)
        ):
            raise ArtifactDAGError(
                f"{node_id}: dependencies, inputs, and outputs must be lists"
            )
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "dependencies": [str(item) for item in dependencies],
                "inputs": [_safe_path(item) for item in inputs],
                "outputs": [_safe_path(item) for item in outputs],
            }
        )
    known: set[str] = set()
    for node in nodes:
        unknown = set(node["dependencies"]) - ids
        if unknown:
            raise ArtifactDAGError(
                f"{node['id']}: unknown dependencies {sorted(unknown)}"
            )
        not_yet_seen = set(node["dependencies"]) - known
        if not_yet_seen:
            raise ArtifactDAGError(
                f"{node['id']}: nodes must be topologically ordered; dependencies follow node {sorted(not_yet_seen)}"
            )
        known.add(node["id"])
    if tuple(node["id"] for node in nodes) != EXPECTED_NODE_ORDER:
        raise ArtifactDAGError(
            "artifact DAG v1 must contain the canonical registry-to-product-state chain"
        )
    for index, node in enumerate(nodes):
        expected_dependencies = [] if index == 0 else [nodes[index - 1]["id"]]
        if node["dependencies"] != expected_dependencies:
            raise ArtifactDAGError(
                "artifact DAG must be one linear authority chain; "
                f"{node['id']} must depend on {expected_dependencies}"
            )
        if enforce_canonical_paths:
            expected_paths = EXPECTED_NODE_PATHS[node["id"]]
            for field in ("inputs", "outputs"):
                if node[field] != expected_paths[field]:
                    raise ArtifactDAGError(
                        "artifact DAG must preserve canonical node paths; "
                        f"{node['id']}.{field} must be {expected_paths[field]}"
                    )
    return nodes


def _path_identity(
    repo_root: Path, relative_path: str, *, available_in_scope: bool = True
) -> dict[str, Any]:
    if not available_in_scope:
        return {"path": relative_path, "status": "unavailable", "sha256": None}
    path = repo_root / relative_path
    if not path.is_file():
        return {"path": relative_path, "status": "missing", "sha256": None}
    return {
        "path": relative_path,
        "status": "available",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _current_binding(
    node_id: str,
    *,
    violations: list[str] | tuple[str, ...] = (),
    out_of_scope: bool = False,
) -> dict[str, Any]:
    unique_violations = list(dict.fromkeys(str(item) for item in violations))
    if out_of_scope:
        status = "out_of_scope"
        contract_pass = False
    elif unique_violations:
        status = "stale"
        contract_pass = False
    else:
        status = "current"
        contract_pass = True
    return {
        "validator": CURRENT_BINDING_VALIDATORS[node_id],
        "status": status,
        "contract_pass": contract_pass,
        "violations": unique_violations,
    }


def _git_run(
    repo_root: Path, *args: str, text: bool = True
) -> subprocess.CompletedProcess[Any]:
    if (
        not TRUSTED_GIT.is_file()
        or TRUSTED_GIT.is_symlink()
        or TRUSTED_GIT.resolve() != TRUSTED_GIT
    ):
        raise ArtifactDAGError("trusted /usr/bin/git is unavailable")
    return subprocess.run(
        [str(TRUSTED_GIT), *args],
        cwd=repo_root,
        env={
            "HOME": "/nonexistent",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
        },
        check=False,
        capture_output=True,
        text=text,
    )


def _git_head(repo_root: Path) -> str:
    result = _git_run(repo_root, "rev-parse", "HEAD")
    value = result.stdout.strip()
    if (
        result.returncode != 0
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ArtifactDAGError("exact repository HEAD is unavailable")
    return value


def _validate_frontend_report_git_binding(
    repo_root: Path,
    payload: Mapping[str, Any],
    *,
    report_path: Path | None = None,
) -> list[str]:
    """Bind the current report to its historical output-only evidence commit.

    The evidence commit need not be ``HEAD``: GitHub normally adds a two-parent
    merge commit after the reviewed evidence commit.  The last commit that
    modified the tracked report is the evidence commit, and its single parent
    is the source commit recorded by the report.
    """

    violations: list[str] = []
    report = report_path or repo_root / RELEASE_LEAF_OUTPUTS[4]
    try:
        report_relative = report.resolve(strict=True).relative_to(
            repo_root.resolve(strict=True)
        ).as_posix()
    except (FileNotFoundError, RuntimeError, ValueError):
        return ["frontend_audit_report_path_invalid"]
    if not report.is_file() or report.is_symlink():
        return ["frontend_audit_report_path_invalid"]

    source = payload.get("source")
    source_sha = source.get("commit_sha") if isinstance(source, dict) else None
    source_tree = source.get("tree_sha") if isinstance(source, dict) else None
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(character not in "0123456789abcdef" for character in source_sha)
    ):
        return ["frontend_audit_source_commit_invalid"]
    exists = _git_run(repo_root, "cat-file", "-e", f"{source_sha}^{{commit}}")
    if exists.returncode != 0:
        return ["frontend_audit_source_commit_object_missing"]
    tree = _git_run(repo_root, "rev-parse", f"{source_sha}^{{tree}}")
    if tree.returncode != 0 or tree.stdout.strip() != source_tree:
        violations.append("frontend_audit_source_tree_mismatch")

    head = _git_head(repo_root)
    evidence = _git_run(
        repo_root,
        "log",
        "-1",
        "--format=%H",
        "--",
        report_relative,
    )
    evidence_sha = evidence.stdout.strip()
    if (
        evidence.returncode != 0
        or len(evidence_sha) != 40
        or any(character not in "0123456789abcdef" for character in evidence_sha)
    ):
        violations.append("frontend_audit_evidence_commit_missing")
        return violations
    evidence_object = _git_run(
        repo_root, "cat-file", "-e", f"{evidence_sha}^{{commit}}"
    )
    if evidence_object.returncode != 0:
        violations.append("frontend_audit_evidence_commit_object_missing")
        return violations
    parents = _git_run(repo_root, "rev-list", "--parents", "-n", "1", evidence_sha)
    parent_tokens = parents.stdout.strip().split()
    if (
        parents.returncode != 0
        or len(parent_tokens) != 2
        or parent_tokens[0] != evidence_sha
    ):
        violations.append("frontend_audit_evidence_commit_not_single_parent")
    elif parent_tokens[1] != source_sha:
        violations.append("frontend_audit_source_not_evidence_commit_parent")
    ancestry = _git_run(repo_root, "merge-base", "--is-ancestor", evidence_sha, head)
    if ancestry.returncode != 0:
        violations.append("frontend_audit_evidence_commit_not_head_ancestor")

    changed = _git_run(
        repo_root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        evidence_sha,
    )
    changed_paths = (
        set(changed.stdout.splitlines()) if changed.returncode == 0 else set()
    )
    if changed.returncode != 0 or changed_paths != EVIDENCE_OUTPUT_ONLY_PATHS:
        violations.append("frontend_audit_evidence_commit_not_output_only")

    evidence_report = _git_run(
        repo_root, "show", f"{evidence_sha}:{report_relative}", text=False
    )
    if evidence_report.returncode != 0 or evidence_report.stdout != report.read_bytes():
        violations.append("frontend_audit_report_differs_from_evidence_commit")

    inputs = payload.get("inputs")
    for relative, binding_name in (
        ("package.json", "package_json"),
        ("package-lock.json", "package_lock"),
    ):
        result = _git_run(repo_root, "show", f"{source_sha}:{relative}", text=False)
        current_path = repo_root / relative
        binding = inputs.get(binding_name) if isinstance(inputs, dict) else None
        if (
            result.returncode != 0
            or not current_path.is_file()
            or current_path.is_symlink()
            or result.stdout != current_path.read_bytes()
            or not isinstance(binding, dict)
            or binding.get("bytes") != len(result.stdout)
            or binding.get("sha256")
            != "sha256:" + hashlib.sha256(result.stdout).hexdigest()
        ):
            violations.append(f"frontend_audit_source_blob_mismatch:{relative}")
    return violations


def _validate_capability_registry_binding(repo_root: Path) -> list[str]:
    from scripts.generate_capability_surfaces import load_registry

    load_registry(repo_root)
    return []


def _validate_capability_surfaces_binding(repo_root: Path) -> list[str]:
    from scripts.generate_capability_surfaces import check_outputs

    return [f"stale_or_missing:{path}" for path in check_outputs(repo_root)]


def _validate_canonical_artifacts_binding(repo_root: Path) -> list[str]:
    from scripts.build_canonical_verification_receipt import (
        validate_persisted_canonical_bundle,
    )

    outputs = EXPECTED_NODE_PATHS["verification-receipts"]["outputs"]
    canonical_violations = validate_persisted_canonical_bundle(
        repo_root=repo_root,
        receipt_path=Path(outputs[0]),
        project_wheel_contract_path=Path(outputs[1]),
        project_wheel_path=Path(outputs[2]),
    )
    return [*canonical_violations, *_validate_release_artifact_bindings(repo_root)]


def _sha256_prefixed(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_report_input_hashes(
    *,
    repo_root: Path,
    report_relative: str,
    schema_version: str,
    required_inputs: tuple[str, ...],
) -> list[str]:
    report_path = repo_root / report_relative
    if not report_path.is_file() or report_path.is_symlink():
        return [f"release_leaf_missing_or_unsafe:{report_relative}"]
    try:
        payload = _load_json_object(report_path)
    except (OSError, json.JSONDecodeError, ArtifactDAGError):
        return [f"release_leaf_json_invalid:{report_relative}"]
    violations: list[str] = []
    if payload.get("schema_version") != schema_version:
        violations.append(f"release_leaf_schema_invalid:{report_relative}")
    checksums = payload.get("input_checksums")
    if not isinstance(checksums, dict):
        return [*violations, f"release_leaf_input_checksums_invalid:{report_relative}"]
    provenance = payload.get("source_input_provenance")
    provenance_rows = provenance.get("inputs") if isinstance(provenance, dict) else None
    for dependency in required_inputs:
        dependency_path = repo_root / dependency
        if not dependency_path.is_file() or dependency_path.is_symlink():
            violations.append(f"release_leaf_dependency_missing:{dependency}")
            continue
        actual_checksum = _sha256_prefixed(dependency_path)
        source_checksum = checksums.get(dependency)
        if source_checksum == actual_checksum:
            continue
        matching_rows = (
            [
                row
                for row in provenance_rows
                if isinstance(row, dict) and row.get("path") == dependency
            ]
            if isinstance(provenance_rows, list)
            else []
        )
        expected_blocker = f"input_differs_from_source_commit:{dependency}"
        transparent_workspace_delta = bool(
            len(matching_rows) == 1
            and matching_rows[0].get("source_checksum") == source_checksum
            and matching_rows[0].get("workspace_checksum") == actual_checksum
            and matching_rows[0].get("workspace_matches_source") is False
            and matching_rows[0].get("blocker") == expected_blocker
            and isinstance(provenance, dict)
            and provenance.get("contract_pass") is False
            and expected_blocker in provenance.get("blockers", [])
        )
        if not transparent_workspace_delta:
            violations.append(
                f"release_leaf_input_hash_mismatch:{report_relative}->{dependency}"
            )
    return violations


def _validate_release_artifact_bindings(repo_root: Path) -> list[str]:
    from scripts import build_frontend_dependency_audit_report as frontend_audit
    from scripts.build_runtime_packaging_manifest import (
        validate_runtime_packaging_artifacts,
    )

    violations = validate_runtime_packaging_artifacts(repo_root)
    frontend_relative = RELEASE_LEAF_OUTPUTS[4]
    frontend_path = repo_root / frontend_relative
    if not frontend_path.is_file() or frontend_path.is_symlink():
        violations.append(f"release_leaf_missing_or_unsafe:{frontend_relative}")
    else:
        try:
            frontend_payload = frontend_audit._load_json_text(
                frontend_path.read_text(encoding="utf-8")
            )
            source = frontend_payload.get("source")
            source_sha = source.get("commit_sha") if isinstance(source, dict) else ""
            frontend_audit.verify_report(
                frontend_payload,
                source_identity=source if isinstance(source, dict) else {},
                expected_source_sha=source_sha if isinstance(source_sha, str) else "",
                package_json=repo_root / "package.json",
                package_lock=repo_root / "package-lock.json",
            )
            violations.extend(
                _validate_frontend_report_git_binding(repo_root, frontend_payload)
            )
        except (
            OSError,
            ArtifactDAGError,
            frontend_audit.FrontendDependencyAuditError,
        ):
            violations.append(
                f"release_leaf_frontend_audit_invalid:{frontend_relative}"
            )

    runtime_manifest = RELEASE_LEAF_OUTPUTS[1]
    runtime_sbom = RELEASE_LEAF_OUTPUTS[2]
    pm_report = RELEASE_LEAF_OUTPUTS[5]
    action_register = RELEASE_LEAF_OUTPUTS[6]
    closure_board = RELEASE_LEAF_OUTPUTS[7]
    readiness_snapshot = RELEASE_LEAF_OUTPUTS[8]
    roadmap = RELEASE_LEAF_OUTPUTS[9]
    report_contracts = (
        (
            pm_report,
            "pm-release-gate-report.v1",
            (runtime_manifest, runtime_sbom, frontend_relative),
        ),
        (
            action_register,
            "pm-release-blocker-action-register.v1",
            (pm_report,),
        ),
        (
            closure_board,
            "pm-release-blocker-closure-board.v1",
            (pm_report, action_register),
        ),
        (
            readiness_snapshot,
            "product-readiness-snapshot.v1",
            (pm_report, action_register),
        ),
        (
            roadmap,
            "structural-product-development-roadmap.v1",
            (pm_report, readiness_snapshot),
        ),
    )
    for report_relative, schema_version, required_inputs in report_contracts:
        violations.extend(
            _validate_report_input_hashes(
                repo_root=repo_root,
                report_relative=report_relative,
                schema_version=schema_version,
                required_inputs=required_inputs,
            )
        )
    return violations


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ArtifactDAGError(f"{path}: JSON object required")
    return payload


def _validate_product_state_binding(
    repo_root: Path,
    *,
    nightly_workflow_run_event: Path | None,
) -> list[str]:
    from scripts.build_product_state import build_product_state

    if nightly_workflow_run_event is None:
        return ["product_state_nightly_event_missing"]
    event_path = (
        nightly_workflow_run_event
        if nightly_workflow_run_event.is_absolute()
        else repo_root / nightly_workflow_run_event
    )
    if not event_path.is_file():
        return ["product_state_nightly_event_missing"]
    external_code_receipt = repo_root / PRODUCT_STATE_EXTERNAL_CODE_RECEIPT
    external_modal_receipt = repo_root / PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT
    missing_inputs = [
        relative.as_posix()
        for relative, path in (
            (PRODUCT_STATE_EXTERNAL_CODE_RECEIPT, external_code_receipt),
            (PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT, external_modal_receipt),
        )
        if not path.is_file()
    ]
    if missing_inputs:
        return [
            f"product_state_rebuild_input_missing:{path}" for path in missing_inputs
        ]
    output_path = repo_root / EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    if not output_path.is_file():
        return ["product_state_output_missing"]
    try:
        nightly_event = _load_json_object(event_path)
    except (OSError, json.JSONDecodeError, ArtifactDAGError):
        return ["product_state_nightly_event_invalid"]
    current, _ = build_product_state(
        repo_root,
        observed_main_sha=_git_head(repo_root),
        observed_main_source=PRODUCT_STATE_NIGHTLY_SOURCE,
        verify_legacy_git_objects=True,
        nightly_workflow_run_event=nightly_event,
        # Match the producer invocation exactly. The license due-diligence receipt
        # treats repository-relative evidence paths as part of its identity, so
        # passing equivalent absolute paths would create a different rebuild.
        external_vv_code_receipt=PRODUCT_STATE_EXTERNAL_CODE_RECEIPT,
        external_vv_modal_receipt=PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT,
    )
    expected = (
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if output_path.read_bytes() != expected:
        return ["product_state_exact_rebuild_mismatch"]
    return []


def validate_current_bindings(
    *,
    repo_root: Path,
    candidate: bool,
    product_state_nightly_event: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Run producer-specific validators for every node in the evaluated scope."""

    bindings: dict[str, dict[str, Any]] = {}
    validators = {
        "capability-registry": lambda: _validate_capability_registry_binding(repo_root),
        "generated-capability-surfaces": (
            lambda: _validate_capability_surfaces_binding(repo_root)
        ),
        "verification-receipts": lambda: _validate_canonical_artifacts_binding(
            repo_root
        ),
        "product-state": lambda: _validate_product_state_binding(
            repo_root,
            nightly_workflow_run_event=product_state_nightly_event,
        ),
    }
    for node_id in EXPECTED_NODE_ORDER:
        if candidate and node_id == "product-state":
            bindings[node_id] = _current_binding(
                node_id,
                violations=["candidate_scope_excludes_product_state"],
                out_of_scope=True,
            )
            continue
        try:
            violations = validators[node_id]()
        except Exception:  # producer exceptions must fail closed with stable output
            violations = ["producer_validator_error"]
        bindings[node_id] = _current_binding(node_id, violations=violations)
    return bindings


def build_snapshot(
    nodes: list[dict[str, Any]],
    *,
    repo_root: Path,
    candidate: bool = False,
) -> dict[str, Any]:
    snapshots: dict[str, dict[str, Any]] = {}
    evaluated_through = nodes[-1]["id"]
    for node in nodes:
        available_in_scope = not (candidate and node["id"] == nodes[-1]["id"])
        if candidate and available_in_scope:
            evaluated_through = node["id"]
        inputs = [
            _path_identity(repo_root, path, available_in_scope=available_in_scope)
            for path in node["inputs"]
        ]
        outputs = [
            _path_identity(repo_root, path, available_in_scope=available_in_scope)
            for path in node["outputs"]
        ]
        identity = {
            "id": node["id"],
            "kind": node["kind"],
            "dependencies": {
                dependency: snapshots[dependency]["fingerprint"]
                for dependency in node["dependencies"]
            },
            "inputs": inputs,
            "outputs": outputs,
        }
        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshots[node["id"]] = {**identity, "fingerprint": fingerprint}
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_kind": CANDIDATE_STATE if candidate else FULL_STATE,
        "evaluated_through": evaluated_through,
        "nodes": snapshots,
    }


def _state_dependencies(node_id: str, node: dict[str, Any]) -> set[str]:
    dependencies = node.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ArtifactDAGError(f"{node_id}: state dependencies must be an object")
    return set(dependencies)


def _topological_state_node_ids(nodes: dict[str, Any]) -> list[str]:
    remaining = list(nodes)
    ordered: list[str] = []
    known = set(nodes)
    while remaining:
        ready = [
            node_id
            for node_id in remaining
            if _state_dependencies(node_id, nodes[node_id]) <= set(ordered)
        ]
        if not ready:
            unknown = {
                dependency
                for node_id in remaining
                for dependency in _state_dependencies(node_id, nodes[node_id])
                if dependency not in known
            }
            reason = f"unknown dependencies {sorted(unknown)}" if unknown else "cycle"
            raise ArtifactDAGError(f"artifact DAG state is not topological: {reason}")
        for node_id in ready:
            remaining.remove(node_id)
            ordered.append(node_id)
    return ordered


def _state_ancestors(nodes: dict[str, Any], node_id: str) -> set[str]:
    ancestors = {node_id}
    pending = [node_id]
    while pending:
        current = pending.pop()
        for dependency in _state_dependencies(current, nodes[current]):
            if dependency not in ancestors:
                ancestors.add(dependency)
                pending.append(dependency)
    return ancestors


def validate_state(payload: dict[str, Any]) -> None:
    """Validate state metadata while accepting pre-metadata v1 snapshots."""

    schema_version = payload.get("schema_version")
    if schema_version not in {LEGACY_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION}:
        raise ArtifactDAGError("unsupported artifact DAG state schema")
    if not isinstance(payload.get("nodes"), dict):
        raise ArtifactDAGError("artifact DAG state nodes must be an object")
    legacy = schema_version == LEGACY_STATE_SCHEMA_VERSION
    if legacy:
        if "state_kind" in payload or "evaluated_through" in payload:
            raise ArtifactDAGError("legacy v1 state cannot contain v2 scope metadata")
        state_kind = FULL_STATE
        evaluated_through = "product-state"
    else:
        state_kind = payload.get("state_kind")
        if state_kind not in {FULL_STATE, CANDIDATE_STATE}:
            raise ArtifactDAGError(
                f"unsupported artifact DAG state kind: {state_kind!r}"
            )
        evaluated_through = str(payload.get("evaluated_through", "")).strip()
    nodes = payload["nodes"]
    if set(nodes) != set(EXPECTED_NODE_ORDER):
        raise ArtifactDAGError(
            "artifact DAG state must contain the canonical registry-to-product-state chain"
        )
    if not evaluated_through or evaluated_through not in nodes:
        raise ArtifactDAGError(
            "artifact DAG state evaluated_through must identify a state node"
        )
    terminal = nodes.get("product-state")
    if not isinstance(terminal, dict) or terminal.get("kind") != "product-state":
        raise ArtifactDAGError("artifact DAG state must end at product-state")
    dependencies = terminal.get("dependencies")
    if not isinstance(dependencies, dict) or len(dependencies) != 1:
        raise ArtifactDAGError("product-state must have exactly one dependency")
    terminal_dependency = next(iter(dependencies))
    unavailable_nodes: set[str] = set()
    for node_id, node in nodes.items():
        if not isinstance(node, dict) or node.get("id") != node_id:
            raise ArtifactDAGError(f"invalid artifact DAG state node: {node_id}")
        required_node_fields = {
            "id",
            "kind",
            "dependencies",
            "inputs",
            "outputs",
            "fingerprint",
        }
        if set(node) != required_node_fields:
            raise ArtifactDAGError(f"{node_id}: state node fields are invalid")
        if node.get("kind") not in ALLOWED_NODE_KINDS:
            raise ArtifactDAGError(f"{node_id}: invalid artifact DAG state kind")
        expected_kind = EXPECTED_NODE_KINDS.get(node_id)
        if expected_kind is not None and node.get("kind") != expected_kind:
            raise ArtifactDAGError(f"{node_id}: state kind must be {expected_kind!r}")
        if node.get("kind") == "product-state" and node_id != "product-state":
            raise ArtifactDAGError(
                f"{node_id}: only the terminal node can be product-state"
            )
        inputs = node.get("inputs")
        outputs = node.get("outputs")
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            raise ArtifactDAGError(f"{node_id}: state paths must be lists")
        identities = [*inputs, *outputs]
        if not all(isinstance(row, dict) for row in identities):
            raise ArtifactDAGError(f"{node_id}: state path identity must be an object")
        expected_paths = (
            LEGACY_EXPECTED_NODE_PATHS[node_id]
            if legacy
            else EXPECTED_NODE_PATHS[node_id]
        )
        for field, rows in (("inputs", inputs), ("outputs", outputs)):
            actual_paths = [row.get("path") for row in rows]
            if actual_paths != expected_paths[field]:
                raise ArtifactDAGError(
                    "artifact DAG state must preserve canonical node paths; "
                    f"{node_id}.{field} must be {expected_paths[field]}"
                )
        allowed_statuses = {"available", "missing"}
        if not legacy:
            allowed_statuses.add("unavailable")
        for row in identities:
            if set(row) != {"path", "status", "sha256"}:
                raise ArtifactDAGError(
                    f"{node_id}: state path identity fields are invalid"
                )
            path = row.get("path")
            if not isinstance(path, str) or _safe_path(path) != path:
                raise ArtifactDAGError(f"{node_id}: state path is invalid")
            status = row.get("status")
            if status not in allowed_statuses:
                raise ArtifactDAGError(f"{node_id}: state path status is invalid")
            digest = row.get("sha256")
            if status == "available":
                if not (
                    isinstance(digest, str)
                    and len(digest) == 64
                    and all(character in "0123456789abcdef" for character in digest)
                ):
                    raise ArtifactDAGError(
                        f"{node_id}: available state path hash is invalid"
                    )
            elif digest is not None:
                raise ArtifactDAGError(
                    f"{node_id}: unavailable state path hash must be null"
                )
        fingerprint = node.get("fingerprint")
        identity = {
            "id": node["id"],
            "kind": node["kind"],
            "dependencies": node["dependencies"],
            "inputs": inputs,
            "outputs": outputs,
        }
        expected_fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if fingerprint != expected_fingerprint:
            raise ArtifactDAGError(f"{node_id}: state fingerprint is invalid")
        if any(row.get("status") == "unavailable" for row in identities):
            unavailable_nodes.add(node_id)
    ordered_node_ids = _topological_state_node_ids(nodes)
    if tuple(ordered_node_ids) != EXPECTED_NODE_ORDER:
        raise ArtifactDAGError(
            "artifact DAG state must preserve the canonical authority order"
        )
    for index, node_id in enumerate(ordered_node_ids):
        expected_dependencies = set() if index == 0 else {ordered_node_ids[index - 1]}
        actual_dependencies = _state_dependencies(node_id, nodes[node_id])
        if actual_dependencies != expected_dependencies:
            raise ArtifactDAGError(
                "artifact DAG state must preserve the canonical linear dependency "
                f"chain; {node_id} must depend on {sorted(expected_dependencies)}"
            )
        for dependency, fingerprint in nodes[node_id]["dependencies"].items():
            if nodes[dependency].get("fingerprint") != fingerprint:
                raise ArtifactDAGError(
                    f"{node_id}: dependency fingerprint does not match {dependency}"
                )
    if _state_ancestors(nodes, "product-state") != set(nodes):
        raise ArtifactDAGError("every state node must feed product-state")
    if state_kind == CANDIDATE_STATE:
        if evaluated_through != terminal_dependency:
            raise ArtifactDAGError(
                "candidate state must evaluate through the product-state dependency"
            )
        if unavailable_nodes != {"product-state"}:
            raise ArtifactDAGError(
                "candidate state must mark only product-state unavailable"
            )
        terminal_identities = [
            *terminal.get("inputs", []),
            *terminal.get("outputs", []),
        ]
        if not terminal_identities or any(
            row.get("status") != "unavailable" for row in terminal_identities
        ):
            raise ArtifactDAGError(
                "candidate state must mark every product-state path unavailable"
            )
    else:
        if evaluated_through != "product-state":
            raise ArtifactDAGError("full state must evaluate through product-state")
        if unavailable_nodes:
            raise ArtifactDAGError("full state cannot contain unavailable nodes")


def load_baseline(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    validate_state(payload)
    if payload.get("state_kind", FULL_STATE) == CANDIDATE_STATE:
        raise ArtifactDAGError(
            "candidate state cannot be used as a trusted artifact DAG baseline"
        )
    return payload


def _normalized_current_bindings(
    candidate: dict[str, Any],
    current_bindings: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    bindings = current_bindings if isinstance(current_bindings, Mapping) else {}
    normalized: dict[str, dict[str, Any]] = {}
    candidate_mode = candidate.get("state_kind", FULL_STATE) == CANDIDATE_STATE
    for node_id in EXPECTED_NODE_ORDER:
        raw = bindings.get(node_id)
        if not isinstance(raw, Mapping):
            normalized[node_id] = _current_binding(
                node_id, violations=["current_binding_result_missing"]
            )
            continue
        expected_fields = {"validator", "status", "contract_pass", "violations"}
        violations = raw.get("violations")
        structurally_valid = (
            set(raw) == expected_fields
            and raw.get("validator") == CURRENT_BINDING_VALIDATORS[node_id]
            and raw.get("status") in {"current", "stale", "out_of_scope"}
            and type(raw.get("contract_pass")) is bool
            and isinstance(violations, list)
            and all(isinstance(item, str) and item for item in violations)
            and len(violations) == len(set(violations))
        )
        status = raw.get("status")
        if status == "current":
            structurally_valid = (
                structurally_valid
                and raw.get("contract_pass") is True
                and violations == []
            )
        elif status == "stale":
            structurally_valid = (
                structurally_valid
                and raw.get("contract_pass") is False
                and bool(violations)
            )
        elif status == "out_of_scope":
            structurally_valid = (
                structurally_valid
                and candidate_mode
                and node_id == "product-state"
                and raw.get("contract_pass") is False
                and violations == ["candidate_scope_excludes_product_state"]
            )
        if not structurally_valid:
            normalized[node_id] = _current_binding(
                node_id, violations=["current_binding_result_invalid"]
            )
            continue
        normalized[node_id] = dict(raw)
    if set(bindings) != set(EXPECTED_NODE_ORDER):
        for node_id in EXPECTED_NODE_ORDER:
            if node_id not in bindings:
                continue
            normalized[node_id] = _current_binding(
                node_id, violations=["current_binding_result_set_invalid"]
            )
    return normalized


def evaluate_snapshot(
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    current_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_state(candidate)
    if baseline is not None:
        validate_state(baseline)
    bindings = _normalized_current_bindings(candidate, current_bindings)
    baseline_nodes = baseline.get("nodes", {}) if isinstance(baseline, dict) else {}
    report_nodes: dict[str, dict[str, Any]] = {}
    ordered_node_ids = _topological_state_node_ids(candidate["nodes"])
    for node_id in ordered_node_ids:
        node = candidate["nodes"][node_id]
        reasons: list[str] = []
        missing = [
            row["path"]
            for row in [*node["inputs"], *node["outputs"]]
            if row["status"] == "missing"
        ]
        if missing:
            reasons.extend(f"missing:{path}" for path in missing)
        unavailable = [
            row["path"]
            for row in [*node["inputs"], *node["outputs"]]
            if row["status"] == "unavailable"
        ]
        if unavailable:
            reasons.extend(f"candidate_unavailable:{path}" for path in unavailable)
        current_binding = bindings[node_id]
        if current_binding["status"] == "stale":
            reasons.extend(
                f"current_binding:{violation}"
                for violation in current_binding["violations"]
            )
        previous = (
            baseline_nodes.get(node_id) if isinstance(baseline_nodes, dict) else None
        )
        if not isinstance(previous, dict):
            reasons.append("baseline_missing")
        elif previous.get("fingerprint") != node["fingerprint"]:
            reasons.append("fingerprint_changed")
        stale_dependencies = [
            dependency
            for dependency in node["dependencies"]
            if report_nodes[dependency]["status"] != "fresh"
        ]
        reasons.extend(
            f"upstream_stale:{dependency}" for dependency in stale_dependencies
        )
        report_nodes[node_id] = {
            "status": "stale" if reasons else "fresh",
            "fingerprint": node["fingerprint"],
            "reasons": reasons,
            "current_binding": current_binding,
        }
    stale = [
        node_id for node_id, node in report_nodes.items() if node["status"] == "stale"
    ]
    evaluated_through = str(
        candidate.get("evaluated_through")
        or (
            "product-state"
            if "product-state" in candidate["nodes"]
            else next(reversed(candidate["nodes"]), "")
        )
    )
    scope = _state_ancestors(candidate["nodes"], evaluated_through)
    scoped_node_ids = [node_id for node_id in ordered_node_ids if node_id in scope]
    scope_stale = [node_id for node_id in scoped_node_ids if node_id in stale]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluation_mode": candidate.get("state_kind", FULL_STATE),
        "evaluated_through": evaluated_through,
        "contract_pass": not stale,
        "scope_pass": not scope_stale,
        "stale_nodes": stale,
        "nodes": report_nodes,
        "claim_boundary": (
            "scope_pass requires artifact availability, DAG fingerprint consistency, "
            "and producer-specific current binding through evaluated_through. A "
            "self-baselined hash cannot override a failed or missing producer "
            "validator. contract_pass requires every DAG node; neither field grants "
            "product or release authority."
        ),
    }


def _serialized(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dag", type=Path, default=DEFAULT_DAG)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    state_mode = parser.add_mutually_exclusive_group()
    state_mode.add_argument("--state", type=Path)
    state_mode.add_argument("--write-state", type=Path)
    state_mode.add_argument("--write-candidate-state", type=Path)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--product-state-nightly-event", type=Path)
    args = parser.parse_args(argv)

    nodes = load_dag(args.dag)
    if args.allow_missing and not args.write_state:
        parser.error("--allow-missing is valid only with --write-state")
    if args.write_candidate_state and args.report is None:
        parser.error("--write-candidate-state requires --report")
    if args.write_state and args.report is None:
        parser.error("--write-state requires --report")
    snapshot = build_snapshot(
        nodes,
        repo_root=args.repo_root,
        candidate=bool(args.write_candidate_state),
    )
    missing = [
        row["path"]
        for node in snapshot["nodes"].values()
        for row in [*node["inputs"], *node["outputs"]]
        if row["status"] == "missing"
    ]
    if args.write_state:
        if missing and not args.allow_missing:
            print(
                "refusing to bless missing DAG artifacts: " + ", ".join(missing),
                file=sys.stderr,
            )
            return 1
        current_bindings = validate_current_bindings(
            repo_root=args.repo_root,
            candidate=False,
            product_state_nightly_event=args.product_state_nightly_event,
        )
        report = evaluate_snapshot(
            snapshot,
            snapshot,
            current_bindings=current_bindings,
        )
        _atomic_write(args.write_state, snapshot)
        _atomic_write(args.report, report)
        print(_serialized(snapshot), end="")
        return 0 if report["contract_pass"] else 1

    if args.write_candidate_state:
        current_bindings = validate_current_bindings(
            repo_root=args.repo_root,
            candidate=True,
        )
        report = evaluate_snapshot(
            snapshot,
            snapshot,
            current_bindings=current_bindings,
        )
        _atomic_write(args.write_candidate_state, snapshot)
        _atomic_write(args.report, report)
        print(_serialized(report), end="")
        return 0 if report["scope_pass"] else 1

    baseline = (
        load_baseline(args.state) if args.state and args.state.is_file() else None
    )
    current_bindings = validate_current_bindings(
        repo_root=args.repo_root,
        candidate=False,
        product_state_nightly_event=args.product_state_nightly_event,
    )
    report = evaluate_snapshot(
        snapshot,
        baseline,
        current_bindings=current_bindings,
    )
    if args.report:
        _atomic_write(args.report, report)
    print(_serialized(report), end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
