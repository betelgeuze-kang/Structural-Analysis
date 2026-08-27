#!/usr/bin/env python3
"""Build one deterministic integrity bundle for exact-SHA product-state evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_generated_artifact_dag import (  # noqa: E402
    ArtifactDAGError,
    build_snapshot,
    evaluate_snapshot,
    load_dag,
    validate_current_bindings,
)
from build_canonical_verification_receipt import (  # noqa: E402
    validate_project_wheel_contract,
)


SCHEMA_VERSION = "product-state-provenance-bundle.v1"
SCHEMA_PATH = ROOT / "canonical/product-state-provenance-bundle.v1.schema.json"
PRODUCT_PROFILE = "repository_integrity_developer_preview"
CANONICAL_PROFILE = "p0-canonical-installed-wheel.v1"
PRODUCT_STATE_WORKFLOW_NAME = "Product State Current"
PRODUCT_STATE_WORKFLOW_PATH = ".github/workflows/product-state-current.yml"
PRODUCT_STATE_WORKFLOW_REF_RE = re.compile(
    r"^(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"(?P<path>\.github/workflows/product-state-current\.yml)@"
    r"(?P<ref>refs/heads/main)$"
)
CLAIM_BOUNDARY = (
    "Integrity-only exact-SHA provenance: this bundle binds the listed bytes and "
    "validates their bounded developer-preview contracts. It preserves, but does "
    "not promote, the product-state readiness outcome and does not grant release, "
    "design, commercial, or independent-verification authority."
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NIGHTLY_TERMINAL_CONCLUSIONS = frozenset(
    {
        "action_required",
        "cancelled",
        "failure",
        "neutral",
        "skipped",
        "stale",
        "success",
        "timed_out",
    }
)
EXPECTED_DAG_OUTPUTS = {
    "canonical_receipt": (
        "verification-receipts",
        "artifacts/manifests/canonical_verification_environment.current.v1.json",
    ),
    "canonical_project_wheel_contract": (
        "verification-receipts",
        ".ci/canonical-project-wheel-contract.json",
    ),
    "canonical_project_wheel": (
        "verification-receipts",
        ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl",
    ),
    "product_state": (
        "product-state",
        "artifacts/manifests/product_state.current.v1.json",
    ),
}


class ProductStateProvenanceError(ValueError):
    """Raised when exact-SHA provenance cannot be established."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProductStateProvenanceError(reason)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductStateProvenanceError(f"{label}_json_invalid:{exc}") from exc
    if not isinstance(payload, dict):
        raise ProductStateProvenanceError(f"{label}_object_required")
    return payload


def _repo_file(repo_root: Path, path: Path, label: str) -> tuple[Path, str]:
    root = repo_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (FileNotFoundError, ValueError) as exc:
        raise ProductStateProvenanceError(
            f"{label}_must_be_repository_file:{path}"
        ) from exc
    if not resolved.is_file():
        raise ProductStateProvenanceError(f"{label}_file_required:{path}")
    return resolved, relative


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact(path: Path, relative_path: str) -> dict[str, Any]:
    return {
        "path": relative_path,
        "sha256": _sha256(path),
        "byte_length": path.stat().st_size,
    }


def _validate_schema(payload: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = _read_json(schema_path, f"{label}_schema")
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise ProductStateProvenanceError(
            f"{label}_schema_invalid:{exc.message}"
        ) from exc


def _mapping(payload: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ProductStateProvenanceError(f"{label}_{key}_object_required")
    return value


def _positive_integer(value: Any, reason: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProductStateProvenanceError(reason)
    return value


def _validate_product_state(payload: dict[str, Any], source_sha: str) -> dict[str, Any]:
    _require(
        payload.get("schema_version") == "product-state.current.v1",
        "product_state_schema_version_invalid",
    )
    _require(
        payload.get("source_commit_sha") == source_sha,
        "product_state_source_commit_mismatch",
    )
    _require(
        payload.get("observed_github_main_sha") == source_sha,
        "product_state_observed_main_mismatch",
    )
    _require(
        payload.get("observed_github_main_source")
        == "github_api_refs_heads_main_pre_build",
        "product_state_observation_source_invalid",
    )
    _require(
        payload.get("source_matches_observed_github_main") is True,
        "product_state_main_binding_invalid",
    )
    _require(
        payload.get("product_profile") == PRODUCT_PROFILE,
        "product_state_profile_invalid",
    )
    _require(
        payload.get("release_authority") is False,
        "product_state_release_authority_must_be_false",
    )
    _require(
        payload.get("release_eligible") is False,
        "product_state_release_eligible_must_be_false",
    )
    contract_pass = payload.get("contract_pass")
    _require(type(contract_pass) is bool, "product_state_contract_pass_invalid")
    blockers = payload.get("blockers")
    _require(isinstance(blockers, list), "product_state_blockers_list_required")
    _require(
        all(isinstance(blocker, str) and bool(blocker) for blocker in blockers),
        "product_state_blockers_nonempty_strings_required",
    )
    _require(
        len(blockers) == len(set(blockers)),
        "product_state_blockers_must_be_unique",
    )
    _require(
        contract_pass is (not blockers),
        "product_state_contract_pass_blockers_mismatch",
    )
    candidate_dirty = payload.get("candidate_worktree_dirty")
    _require(
        type(candidate_dirty) is bool,
        "product_state_candidate_worktree_dirty_invalid",
    )
    candidate_change_count = payload.get("candidate_worktree_change_count")
    _require(
        isinstance(candidate_change_count, int)
        and not isinstance(candidate_change_count, bool)
        and candidate_change_count >= 0,
        "product_state_candidate_worktree_change_count_invalid",
    )
    _require(
        candidate_dirty is (candidate_change_count > 0),
        "product_state_candidate_worktree_state_mismatch",
    )
    if contract_pass:
        _require(
            candidate_dirty is False and candidate_change_count == 0,
            "passing_product_state_requires_clean_worktree",
        )
    expected_status = "ready" if contract_pass else "blocked"
    _require(
        payload.get("status") == expected_status,
        "product_state_status_contract_mismatch",
    )
    quality_evidence = _mapping(payload, "quality_evidence", "product_state")
    _require(
        quality_evidence.get("status") == "available",
        "product_state_quality_evidence_unavailable",
    )
    _require(
        quality_evidence.get("head_sha") == source_sha,
        "product_state_quality_source_mismatch",
    )
    return {
        "schema_version": payload["schema_version"],
        "product_profile": payload["product_profile"],
        "status": payload["status"],
        "contract_pass": contract_pass,
    }


def _validate_canonical_contracts(
    receipt: dict[str, Any],
    wheel_contract: dict[str, Any],
    *,
    source_sha: str,
    wheel_path: Path,
) -> dict[str, Any]:
    _validate_schema(
        receipt,
        ROOT / "canonical/canonical-verification-receipt.v1.schema.json",
        "canonical_receipt",
    )
    _validate_schema(
        wheel_contract,
        ROOT / "canonical/canonical-project-wheel-contract.v1.schema.json",
        "canonical_project_wheel_contract",
    )
    _require(
        receipt.get("contract_profile") == CANONICAL_PROFILE,
        "canonical_receipt_profile_invalid",
    )
    _require(
        receipt.get("source_commit_sha") == source_sha
        and receipt.get("source_checkout_head_sha") == source_sha,
        "canonical_receipt_source_mismatch",
    )
    _require(
        receipt.get("contract_pass") is True and receipt.get("violations") == [],
        "canonical_receipt_contract_failed",
    )
    _require(
        wheel_contract.get("source_commit_sha") == source_sha,
        "canonical_project_wheel_source_mismatch",
    )
    _require(
        wheel_contract.get("contract_pass") is True
        and wheel_contract.get("violations") == [],
        "canonical_project_wheel_contract_failed",
    )
    _require(
        receipt.get("source_date_epoch") == wheel_contract.get("source_date_epoch"),
        "canonical_source_date_epoch_mismatch",
    )
    _require(
        receipt.get("project_wheel") == wheel_contract,
        "canonical_receipt_project_wheel_mismatch",
    )
    shared_violations = validate_project_wheel_contract(
        wheel_contract,
        wheel_path=wheel_path,
        source_sha=source_sha,
        source_date_epoch=receipt["source_date_epoch"],
    )
    _require(
        not shared_violations,
        "canonical_project_wheel_shared_validation_failed:"
        + ",".join(shared_violations),
    )

    wheel = _mapping(wheel_contract, "wheel", "canonical_project_wheel_contract")
    wheel_sha256 = _sha256(wheel_path)
    _require(
        wheel.get("filename") == wheel_path.name,
        "canonical_project_wheel_filename_mismatch",
    )
    _require(
        wheel.get("byte_length") == wheel_path.stat().st_size,
        "canonical_project_wheel_length_mismatch",
    )
    _require(
        wheel.get("sha256") == wheel_sha256
        and wheel.get("repeat_sha256") == wheel_sha256,
        "canonical_project_wheel_hash_mismatch",
    )
    installed = _mapping(
        wheel_contract, "installed_replay", "canonical_project_wheel_contract"
    )
    _require(
        installed.get("installed_source_commit_sha") == source_sha,
        "canonical_installed_replay_source_mismatch",
    )
    _require(
        installed.get("installed_source_date_epoch")
        == wheel_contract.get("source_date_epoch"),
        "canonical_installed_replay_epoch_mismatch",
    )
    _require(
        installed.get("wheel_filename") == wheel_path.name
        and installed.get("wheel_sha256") == wheel_sha256,
        "canonical_installed_replay_wheel_mismatch",
    )
    return {
        "receipt_schema_version": receipt["schema_version"],
        "contract_profile": receipt["contract_profile"],
        "project_wheel_schema_version": wheel_contract["schema_version"],
        "contract_pass": True,
    }


def _workflow_identity(
    run: dict[str, Any],
    *,
    authority: str,
    expected_name: str,
    expected_path: str,
    source_sha: str,
    allowed_events: set[str],
    require_success: bool,
) -> dict[str, Any]:
    _require(run.get("name") == expected_name, f"{authority}_workflow_name_invalid")
    _require(run.get("path") == expected_path, f"{authority}_workflow_path_invalid")
    _require(run.get("head_branch") == "main", f"{authority}_head_branch_invalid")
    _require(run.get("head_sha") == source_sha, f"{authority}_head_sha_mismatch")
    trigger_event = run.get("event")
    _require(trigger_event in allowed_events, f"{authority}_trigger_event_invalid")
    conclusion = run.get("conclusion")
    _require(
        isinstance(conclusion, str) and bool(conclusion),
        f"{authority}_conclusion_invalid",
    )
    if require_success:
        _require(conclusion == "success", f"{authority}_conclusion_not_success")
    return {
        "authority": authority,
        "workflow_name": expected_name,
        "workflow_path": expected_path,
        "run_id": _positive_integer(run.get("id"), f"{authority}_run_id_invalid"),
        "run_number": _positive_integer(
            run.get("run_number"), f"{authority}_run_number_invalid"
        ),
        "run_attempt": _positive_integer(
            run.get("run_attempt"), f"{authority}_run_attempt_invalid"
        ),
        "trigger_event": trigger_event,
        "conclusion": conclusion,
        "head_branch": "main",
        "head_sha": source_sha,
    }


def _validate_workflow_runs(
    canonical_run: dict[str, Any],
    nightly_event: dict[str, Any],
    product_state: dict[str, Any],
    source_sha: str,
) -> dict[str, Any]:
    canonical_identity = _workflow_identity(
        canonical_run,
        authority="github_actions_workflow_run_api",
        expected_name="P0 Canonical Verification Contract",
        expected_path=".github/workflows/p0-canonical-contract.yml",
        source_sha=source_sha,
        allowed_events={"push", "workflow_dispatch"},
        require_success=True,
    )
    nightly_run = nightly_event.get("workflow_run")
    if not isinstance(nightly_run, dict):
        raise ProductStateProvenanceError("nightly_workflow_run_event_invalid")
    nightly_identity = _workflow_identity(
        nightly_run,
        authority="github_actions_workflow_run_event",
        expected_name="Nightly Full Quality",
        expected_path=".github/workflows/nightly-full-quality.yml",
        source_sha=source_sha,
        allowed_events={"schedule", "workflow_dispatch"},
        require_success=False,
    )
    _require(
        nightly_identity["conclusion"] in NIGHTLY_TERMINAL_CONCLUSIONS,
        "github_actions_workflow_run_event_conclusion_not_terminal",
    )
    if nightly_identity["conclusion"] != "success":
        _require(
            product_state.get("contract_pass") is False
            and product_state.get("status") == "blocked",
            "nightly_non_success_product_state_must_be_blocked",
        )
    quality_evidence = _mapping(product_state, "quality_evidence", "product_state")
    for identity_key, evidence_key in (
        ("workflow_name", "workflow_name"),
        ("run_id", "run_id"),
        ("run_number", "run_number"),
        ("run_attempt", "run_attempt"),
        ("trigger_event", "trigger_event"),
        ("conclusion", "conclusion"),
        ("head_branch", "head_branch"),
        ("head_sha", "head_sha"),
    ):
        _require(
            nightly_identity[identity_key] == quality_evidence.get(evidence_key),
            f"nightly_product_state_evidence_mismatch:{identity_key}",
        )
    return {
        "canonical_verification": canonical_identity,
        "nightly_full_quality": nightly_identity,
    }


def _git_stdout(repo_root: Path, arguments: list[str], reason: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ProductStateProvenanceError(reason) from exc
    if result.returncode != 0:
        raise ProductStateProvenanceError(reason)
    return result.stdout


def _validate_product_state_workflow(
    *,
    repo_root: Path,
    source_sha: str,
    workflow_sha: str,
    workflow_ref: str,
    workflow_name: str,
    trigger_event: str,
    run_id: int,
    run_number: int,
    run_attempt: int,
    workflow_definition_path: Path,
    workflow_definition_artifact: dict[str, Any],
) -> dict[str, Any]:
    _require(
        workflow_name == PRODUCT_STATE_WORKFLOW_NAME,
        "product_state_workflow_name_invalid",
    )
    _require(trigger_event == "workflow_run", "product_state_workflow_event_invalid")
    _require(
        bool(SHA_RE.fullmatch(workflow_sha)),
        "product_state_workflow_sha_invalid",
    )
    _require(
        workflow_sha == source_sha,
        "product_state_workflow_sha_source_mismatch",
    )
    reference = PRODUCT_STATE_WORKFLOW_REF_RE.fullmatch(workflow_ref)
    _require(reference is not None, "product_state_workflow_ref_invalid")
    assert reference is not None
    _require(
        reference.group("path") == PRODUCT_STATE_WORKFLOW_PATH,
        "product_state_workflow_ref_path_invalid",
    )
    _require(
        workflow_definition_artifact["path"] == PRODUCT_STATE_WORKFLOW_PATH,
        "product_state_workflow_definition_path_invalid",
    )

    head_sha = (
        _git_stdout(
            repo_root,
            ["rev-parse", "--verify", "HEAD^{commit}"],
            "product_state_git_head_unavailable",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    _require(head_sha == source_sha, "product_state_git_head_source_mismatch")
    committed_workflow = _git_stdout(
        repo_root,
        ["show", f"{workflow_sha}:{PRODUCT_STATE_WORKFLOW_PATH}"],
        "product_state_workflow_definition_unavailable_at_source",
    )
    try:
        working_workflow = workflow_definition_path.read_bytes()
    except OSError as exc:
        raise ProductStateProvenanceError(
            "product_state_workflow_definition_unreadable"
        ) from exc
    _require(
        working_workflow == committed_workflow,
        "product_state_workflow_definition_source_mismatch",
    )

    validated_run_id = _positive_integer(
        run_id, "product_state_workflow_run_id_invalid"
    )
    validated_run_number = _positive_integer(
        run_number, "product_state_workflow_run_number_invalid"
    )
    validated_run_attempt = _positive_integer(
        run_attempt, "product_state_workflow_run_attempt_invalid"
    )
    if os.environ.get("GITHUB_ACTIONS") == "true":
        expected_context = {
            "GITHUB_REPOSITORY": reference.group("repository"),
            "GITHUB_WORKFLOW": workflow_name,
            "GITHUB_WORKFLOW_REF": workflow_ref,
            "GITHUB_WORKFLOW_SHA": workflow_sha,
            "GITHUB_EVENT_NAME": trigger_event,
            "GITHUB_RUN_ID": str(validated_run_id),
            "GITHUB_RUN_NUMBER": str(validated_run_number),
            "GITHUB_RUN_ATTEMPT": str(validated_run_attempt),
        }
        for variable, expected in expected_context.items():
            _require(
                os.environ.get(variable) == expected,
                f"product_state_workflow_context_mismatch:{variable}",
            )

    return {
        "authority": "github_actions_workflow_context",
        "repository": reference.group("repository"),
        "workflow_name": PRODUCT_STATE_WORKFLOW_NAME,
        "workflow_path": PRODUCT_STATE_WORKFLOW_PATH,
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "run_id": validated_run_id,
        "run_number": validated_run_number,
        "run_attempt": validated_run_attempt,
        "trigger_event": "workflow_run",
        "workflow_definition": workflow_definition_artifact,
    }


def _dag_output_identity(
    state: dict[str, Any], node_id: str, expected_path: str
) -> dict[str, Any]:
    nodes = _mapping(state, "nodes", "dag_state")
    node = nodes.get(node_id)
    if not isinstance(node, dict):
        raise ProductStateProvenanceError(f"dag_state_node_missing:{node_id}")
    outputs = node.get("outputs")
    if not isinstance(outputs, list):
        raise ProductStateProvenanceError(f"dag_state_outputs_invalid:{node_id}")
    matches = [row for row in outputs if row.get("path") == expected_path]
    _require(
        len(matches) == 1,
        f"dag_state_output_path_mismatch:{node_id}:{expected_path}",
    )
    row = matches[0]
    _require(
        row.get("status") == "available",
        f"dag_state_output_unavailable:{node_id}:{expected_path}",
    )
    return row


def _validate_dag(
    state: dict[str, Any],
    report: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    *,
    repo_root: Path,
    product_state_nightly_event: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_schema(
        state,
        ROOT / "canonical/generated-artifact-dag-state.v2.schema.json",
        "generated_artifact_dag_state",
    )
    _validate_schema(
        report,
        ROOT / "canonical/generated-artifact-dag-report.v2.schema.json",
        "generated_artifact_dag_report",
    )
    _require(
        state.get("state_kind") == "full"
        and state.get("evaluated_through") == "product-state",
        "generated_artifact_dag_state_not_full",
    )

    bindings: dict[str, Any] = {}
    for artifact_key, (node_id, expected_path) in EXPECTED_DAG_OUTPUTS.items():
        artifact = artifacts[artifact_key]
        _require(
            artifact["path"] == expected_path,
            f"dag_artifact_path_mismatch:{artifact_key}",
        )
        identity = _dag_output_identity(state, node_id, expected_path)
        dag_sha256 = identity.get("sha256")
        actual_sha256 = artifact["sha256"].removeprefix("sha256:")
        _require(
            dag_sha256 == actual_sha256,
            f"dag_artifact_hash_mismatch:{artifact_key}",
        )
        bindings[artifact_key] = {
            "artifact": artifact_key,
            "node_id": node_id,
            "path": expected_path,
            "sha256": artifact["sha256"],
        }

    try:
        current_nodes = load_dag(repo_root / "canonical/generated-artifact-dag.v1.json")
        current_state = build_snapshot(current_nodes, repo_root=repo_root)
        current_bindings = validate_current_bindings(
            repo_root=repo_root,
            candidate=False,
            product_state_nightly_event=product_state_nightly_event,
        )
        expected_report = evaluate_snapshot(
            current_state,
            current_state,
            current_bindings=current_bindings,
        )
    except ArtifactDAGError as exc:
        raise ProductStateProvenanceError(
            f"generated_artifact_dag_current_snapshot_invalid:{exc}"
        ) from exc
    _require(
        state == current_state,
        "generated_artifact_dag_state_current_snapshot_mismatch",
    )
    _require(
        report == expected_report,
        "generated_artifact_dag_report_state_mismatch",
    )
    _require(
        report.get("scope_pass") is True
        and report.get("contract_pass") is True
        and report.get("stale_nodes") == [],
        "generated_artifact_dag_contract_failed",
    )
    contract = {
        "state_schema_version": state["schema_version"],
        "report_schema_version": report["schema_version"],
        "state_kind": state["state_kind"],
        "evaluated_through": state["evaluated_through"],
        "contract_pass": True,
    }
    return contract, bindings


def _serialized(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    temporary.replace(path)


def _repo_file_for_output(repo_root: Path, path: Path) -> Path:
    root = repo_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProductStateProvenanceError(
            f"output_must_be_repository_relative:{path}"
        ) from exc
    return resolved


def build_bundle(
    *,
    repo_root: Path,
    source_sha: str,
    product_state_path: Path,
    canonical_receipt_path: Path,
    canonical_wheel_contract_path: Path,
    canonical_wheel_path: Path,
    dag_state_path: Path,
    dag_report_path: Path,
    canonical_workflow_run_path: Path,
    nightly_workflow_run_event_path: Path,
    product_state_workflow_sha: str,
    product_state_workflow_ref: str,
    product_state_workflow_name: str,
    product_state_workflow_event: str,
    product_state_workflow_run_id: int,
    product_state_workflow_run_number: int,
    product_state_workflow_run_attempt: int,
) -> dict[str, Any]:
    _require(bool(SHA_RE.fullmatch(source_sha)), "source_commit_sha_invalid")
    paths: dict[str, tuple[Path, str]] = {}
    for key, path in {
        "product_state": product_state_path,
        "canonical_receipt": canonical_receipt_path,
        "canonical_project_wheel_contract": canonical_wheel_contract_path,
        "canonical_project_wheel": canonical_wheel_path,
        "generated_artifact_dag_state": dag_state_path,
        "generated_artifact_dag_report": dag_report_path,
        "product_state_workflow_definition": Path(PRODUCT_STATE_WORKFLOW_PATH),
    }.items():
        paths[key] = _repo_file(repo_root, path, key)

    product_state = _read_json(paths["product_state"][0], "product_state")
    canonical_receipt = _read_json(paths["canonical_receipt"][0], "canonical_receipt")
    wheel_contract = _read_json(
        paths["canonical_project_wheel_contract"][0],
        "canonical_project_wheel_contract",
    )
    dag_state = _read_json(
        paths["generated_artifact_dag_state"][0], "generated_artifact_dag_state"
    )
    dag_report = _read_json(
        paths["generated_artifact_dag_report"][0], "generated_artifact_dag_report"
    )
    canonical_workflow_run = _read_json(
        canonical_workflow_run_path, "canonical_workflow_run"
    )
    nightly_workflow_run_event = _read_json(
        nightly_workflow_run_event_path, "nightly_workflow_run_event"
    )
    artifacts = {
        key: _artifact(path, relative) for key, (path, relative) in paths.items()
    }
    product_state_contract = _validate_product_state(product_state, source_sha)
    canonical_contract = _validate_canonical_contracts(
        canonical_receipt,
        wheel_contract,
        source_sha=source_sha,
        wheel_path=paths["canonical_project_wheel"][0],
    )
    dag_contract, dag_bindings = _validate_dag(
        dag_state,
        dag_report,
        artifacts,
        repo_root=repo_root.resolve(strict=True),
        product_state_nightly_event=nightly_workflow_run_event_path,
    )
    workflow_runs = _validate_workflow_runs(
        canonical_workflow_run,
        nightly_workflow_run_event,
        product_state,
        source_sha,
    )
    workflow_runs["product_state_current"] = _validate_product_state_workflow(
        repo_root=repo_root.resolve(strict=True),
        source_sha=source_sha,
        workflow_sha=product_state_workflow_sha,
        workflow_ref=product_state_workflow_ref,
        workflow_name=product_state_workflow_name,
        trigger_event=product_state_workflow_event,
        run_id=product_state_workflow_run_id,
        run_number=product_state_workflow_run_number,
        run_attempt=product_state_workflow_run_attempt,
        workflow_definition_path=paths["product_state_workflow_definition"][0],
        workflow_definition_artifact=artifacts["product_state_workflow_definition"],
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_sha,
        "contracts": {
            "product_state": product_state_contract,
            "canonical_verification": canonical_contract,
            "generated_artifact_dag": dag_contract,
        },
        "artifacts": artifacts,
        "dag_artifact_bindings": dag_bindings,
        "workflow_runs": workflow_runs,
        "bundle_integrity_pass": True,
        "release_authority": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    _validate_schema(payload, SCHEMA_PATH, "product_state_provenance_bundle")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--product-state", type=Path, required=True)
    parser.add_argument("--canonical-receipt", type=Path, required=True)
    parser.add_argument("--canonical-wheel-contract", type=Path, required=True)
    parser.add_argument("--canonical-wheel", type=Path, required=True)
    parser.add_argument("--dag-state", type=Path, required=True)
    parser.add_argument("--dag-report", type=Path, required=True)
    parser.add_argument("--canonical-workflow-run", type=Path, required=True)
    parser.add_argument("--nightly-workflow-run-event", type=Path, required=True)
    parser.add_argument("--product-state-workflow-sha", required=True)
    parser.add_argument("--product-state-workflow-ref", required=True)
    parser.add_argument("--product-state-workflow-name", required=True)
    parser.add_argument("--product-state-workflow-event", required=True)
    parser.add_argument("--product-state-workflow-run-id", type=int, required=True)
    parser.add_argument("--product-state-workflow-run-number", type=int, required=True)
    parser.add_argument("--product-state-workflow-run-attempt", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build_bundle(
            repo_root=args.repo_root,
            source_sha=args.source_sha,
            product_state_path=args.product_state,
            canonical_receipt_path=args.canonical_receipt,
            canonical_wheel_contract_path=args.canonical_wheel_contract,
            canonical_wheel_path=args.canonical_wheel,
            dag_state_path=args.dag_state,
            dag_report_path=args.dag_report,
            canonical_workflow_run_path=args.canonical_workflow_run,
            nightly_workflow_run_event_path=args.nightly_workflow_run_event,
            product_state_workflow_sha=args.product_state_workflow_sha,
            product_state_workflow_ref=args.product_state_workflow_ref,
            product_state_workflow_name=args.product_state_workflow_name,
            product_state_workflow_event=args.product_state_workflow_event,
            product_state_workflow_run_id=args.product_state_workflow_run_id,
            product_state_workflow_run_number=args.product_state_workflow_run_number,
            product_state_workflow_run_attempt=args.product_state_workflow_run_attempt,
        )
        output = _repo_file_for_output(args.repo_root, args.out)
        _write_atomic(output, _serialized(payload))
    except ProductStateProvenanceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
