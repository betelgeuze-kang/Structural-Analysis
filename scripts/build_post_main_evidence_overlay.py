#!/usr/bin/env python3
"""Build and validate the exact-main post-main release-evidence overlay.

The overlay is produced after Nightly Full Quality reaches its terminal
outcome. It keeps fresh generated release leaves outside Git, binds them to the
exact source tree and workflow blob, and preserves technical-only/non-promotion
boundaries. It never grants release, legal, independent-operator, or scientific
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.strict_json import StrictJSONError, strict_json_load_path  # noqa: E402
from scripts.nonpromotion_authority_policy import (  # noqa: E402
    AuthorityPolicy,
    AuthorityPolicyError,
    POLICY_PATH as AUTHORITY_POLICY_PATH,
    load_authority_policy,
    promoted_authority_violations,
)


SCHEMA_VERSION = "post-main-evidence-overlay.v1"
MANIFEST_NAME = "post-main-evidence-overlay.seal.json"
SCHEMA_PATH = Path("canonical/post-main-evidence-overlay.v1.schema.json")
TRUSTED_GIT = Path("/usr/bin/git")
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_FILE_BYTES = 100_000_000
MAX_TOTAL_BYTES = 300_000_000

PORTABLE_RELEASE_REPLAY_INPUTS = (
    "implementation/phase1/release_evidence/productization/"
    "developer_preview_readiness.json",
    "implementation/phase1/release_evidence/productization/"
    "developer_preview_rc_status.json",
    "implementation/phase1/release_evidence/productization/"
    "release_evidence_freshness_report.json",
)

RELEASE_FILES = (
    "implementation/phase1/native_runtime_artifact_manifest.json",
    "implementation/phase1/production_runtime_packaging_manifest.json",
    "implementation/phase1/runtime_sbom.json",
    "implementation/phase1/runtime_version_compatibility_matrix.json",
    "implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json",
    *PORTABLE_RELEASE_REPLAY_INPUTS,
    "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json",
    "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
    "implementation/phase1/release_evidence/productization/structural_product_development_roadmap.json",
    "implementation/phase1/release_evidence/productization/structural_product_development_roadmap.md",
)

PAIR_SCHEMA = "canonical/technical-evidence-handoff-pair.v1.schema.json"
PAIR_VERIFIER = "scripts/verify_technical_evidence_handoff_pair.py"
TECHNICAL_LANES = {
    "medium": ".github/workflows/medium-scale-current-source.yml",
    "ifc": ".github/workflows/ifc-import-health-current-source.yml",
    "mgt9": ".github/workflows/mgt-import-health-current-source.yml",
    "mgt10": ".github/workflows/mgt-import-health-tenth-source.yml",
    "native": ".github/workflows/native-frame-alpha-clean-install.yml",
}

EXTERNAL_RECEIPT_CONTRACTS = {
    (
        "implementation/phase1/release_evidence/productization/"
        "external_code_to_code_technical_execution_receipt.json"
    ): {
        "product_state_input_path": ".ci/product-state-inputs/code-to-code-receipt.json",
        "schema_path": (
            "src/structural_analysis/schemas/"
            "external_code_to_code_technical_receipt_v1.schema.json"
        ),
        "schema_version": "external-code-to-code-technical-execution.v1",
        "truth_class": "external_code_to_code_technical_execution",
        "claim_boundary_sha256": (
            "sha256:2c3877649b94ddd250ec2f5d4690f18c13b126db274c31c43b0232763fb0fd7a"
        ),
    },
    (
        "implementation/phase1/release_evidence/productization/"
        "external_modal_buckling_technical_execution_receipt.json"
    ): {
        "product_state_input_path": ".ci/product-state-inputs/modal-buckling-receipt.json",
        "schema_path": (
            "src/structural_analysis/schemas/"
            "external_modal_buckling_technical_receipt_v1.schema.json"
        ),
        "schema_version": "external-modal-buckling-technical-execution.v1",
        "truth_class": "external_code_to_code_modal_buckling_technical_execution",
        "claim_boundary_sha256": (
            "sha256:46381abd9eee13c5b02986f21f49251f47c856c711e23581b9b57032e0457f31"
        ),
    },
}
EXTERNAL_RECEIPTS = tuple(
    (source_path, str(contract["product_state_input_path"]))
    for source_path, contract in EXTERNAL_RECEIPT_CONTRACTS.items()
)

NONPROMOTING_CLAIMS = (
    "commercial_equivalence",
    "commercial_redistribution_approved",
    "design_authority",
    "external_runtime_redistribution_approval",
    "product_legal_license_approval",
    "product_legal_approval",
    "release_readiness",
    "release_authority",
    "verification_level_2",
    "formal_verification_level_2",
    "independent_operator_attested",
)
NONPROMOTING_EFFECTIVE_CLAIMS = (
    "independent_operator_attested",
    "verification_hierarchy_operator_manifest_attached",
    "verification_hierarchy_credit",
    "product_legal_license_approval",
    "external_runtime_redistribution_approval",
    "commercial_redistribution_approved",
    "formal_verification_level_2",
    "commercial_equivalence",
    "design_authority",
    "release_readiness",
    "release_authority",
)
CLAIM_BOUNDARY = (
    "This exact-main overlay closes only generated-release-leaf freshness and "
    "byte provenance. Technical handoff lanes and same-operator external V&V "
    "remain non-promoting; legal, redistribution, independent-operator, formal "
    "Level 2, commercial equivalence, design, signing, and release authority "
    "remain unavailable without their separate authoritative receipts."
)


class OverlayContractError(ValueError):
    """Raised when overlay bytes, identity, or authority boundaries are invalid."""


def _require(condition: object, reason: str) -> None:
    if not condition:
        raise OverlayContractError(reason)


def _safe_path(value: Any, label: str) -> str:
    _require(type(value) is str and 0 < len(value) <= 2048, f"{label}_invalid")
    _require(
        "\\" not in value and "\x00" not in value and ":" not in value,
        f"{label}_encoding_invalid",
    )
    _require(
        unicodedata.normalize("NFC", value) == value
        and not any(
            unicodedata.category(character) in {"Cc", "Cf"} for character in value
        ),
        f"{label}_unicode_invalid",
    )
    path = PurePosixPath(value)
    _require(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"{label}_unsafe",
    )
    return value


def _safe_integer(value: Any, label: str) -> int:
    _require(type(value) is int and 1 <= value <= MAX_SAFE_INTEGER, f"{label}_invalid")
    return value


def _safe_regular_file(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise OverlayContractError(f"{label}_unreadable:{current}") from exc
        _require(
            not stat.S_ISLNK(metadata.st_mode), f"{label}_symlink_forbidden:{current}"
        )
    _require(absolute.is_file(), f"{label}_regular_file_required")
    return absolute


def _safe_directory(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise OverlayContractError(f"{label}_unreadable:{current}") from exc
        _require(
            not stat.S_ISLNK(metadata.st_mode), f"{label}_symlink_forbidden:{current}"
        )
    _require(absolute.is_dir(), f"{label}_directory_required")
    return absolute


def _prepare_materialize_target(repo_root: Path, relative: str, label: str) -> Path:
    root = _safe_directory(repo_root, "materialize_repo_root")
    safe_relative = _safe_path(relative, label)
    parts = PurePosixPath(safe_relative).parts
    current = root
    for part in parts[:-1]:
        candidate = current / part
        try:
            metadata = os.lstat(candidate)
        except FileNotFoundError:
            try:
                os.mkdir(candidate, mode=0o755)
            except OSError as exc:
                raise OverlayContractError(
                    f"{label}_parent_create_failed:{candidate}"
                ) from exc
            metadata = os.lstat(candidate)
        except OSError as exc:
            raise OverlayContractError(
                f"{label}_parent_unreadable:{candidate}"
            ) from exc
        _require(
            not stat.S_ISLNK(metadata.st_mode), f"{label}_parent_symlink:{candidate}"
        )
        _require(
            stat.S_ISDIR(metadata.st_mode), f"{label}_parent_not_directory:{candidate}"
        )
        current = candidate
    target = current / parts[-1]
    try:
        metadata = os.lstat(target)
    except FileNotFoundError:
        return target
    except OSError as exc:
        raise OverlayContractError(f"{label}_target_unreadable:{target}") from exc
    _require(not stat.S_ISLNK(metadata.st_mode), f"{label}_target_symlink:{target}")
    _require(stat.S_ISREG(metadata.st_mode), f"{label}_target_not_regular:{target}")
    return target


def _replace_regular_file(target: Path, raw: bytes, label: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644, follow_symlinks=False)
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise OverlayContractError(f"{label}_write_failed:{target}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _read(path: Path, label: str, *, maximum: int = MAX_FILE_BYTES) -> bytes:
    safe = _safe_regular_file(path, label)
    size = safe.stat().st_size
    _require(0 < size <= maximum, f"{label}_size_invalid")
    raw = safe.read_bytes()
    _require(len(raw) == size, f"{label}_size_changed")
    return raw


def _strict_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = strict_json_load_path(_safe_regular_file(path, label))
    except StrictJSONError as exc:
        raise OverlayContractError(f"{label}_strict_json_invalid") from exc
    _require(type(value) is dict, f"{label}_object_required")
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git(repo_root: Path, *args: str, text: bool = False) -> bytes | str:
    _require(
        TRUSTED_GIT.is_file()
        and not TRUSTED_GIT.is_symlink()
        and TRUSTED_GIT.resolve() == TRUSTED_GIT,
        "trusted_git_unavailable",
    )
    result = subprocess.run(
        [str(TRUSTED_GIT), "-c", f"safe.directory={repo_root.resolve()}", *args],
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
    _require(result.returncode == 0, f"git_command_failed:{args[0]}")
    return result.stdout


def _git_text(repo_root: Path, *args: str) -> str:
    value = _git(repo_root, *args, text=True)
    assert isinstance(value, str)
    return value.strip()


def _source_file_identity(
    repo_root: Path, source_sha: str, relative: str
) -> dict[str, Any]:
    relative = _safe_path(relative, "source_path")
    raw = _git(repo_root, "show", f"{source_sha}:{relative}")
    assert isinstance(raw, bytes)
    _require(0 < len(raw) <= MAX_FILE_BYTES, f"source_file_size_invalid:{relative}")
    blob_sha = _git_text(repo_root, "rev-parse", f"{source_sha}:{relative}")
    _require(SHA.fullmatch(blob_sha) is not None, f"source_blob_sha_invalid:{relative}")
    return {
        "path": relative,
        "blob_sha": blob_sha,
        "bytes": len(raw),
        "sha256": _sha256(raw),
    }


def _copy_identity(
    *, source: Path, overlay_root: Path, overlay_relative: str, path: str
) -> dict[str, Any]:
    raw = _read(source, f"release_file:{path}")
    if path.endswith(".json"):
        _strict_object(source, f"release_json:{path}")
    target = overlay_root / _safe_path(overlay_relative, "overlay_path")
    target.parent.mkdir(parents=True, exist_ok=True)
    _require(not target.exists(), f"overlay_target_already_exists:{overlay_relative}")
    target.write_bytes(raw)
    return {
        "path": path,
        "overlay_path": overlay_relative,
        "bytes": len(raw),
        "sha256": _sha256(raw),
    }


def _canonical_object_hash(
    payload: dict[str, Any], *, excluded: set[str] | None = None
) -> str:
    material = {
        key: value for key, value in payload.items() if key not in (excluded or set())
    }
    raw = json.dumps(
        material,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256(raw)


def _source_authority_policy(repo_root: Path, source_sha: str) -> AuthorityPolicy:
    relative = AUTHORITY_POLICY_PATH.as_posix()
    identity = _source_file_identity(repo_root, source_sha, relative)
    path = repo_root / AUTHORITY_POLICY_PATH
    raw = _read(path, "authority_policy")
    _require(
        len(raw) == identity["bytes"] and _sha256(raw) == identity["sha256"],
        "authority_policy_source_mismatch",
    )
    try:
        return load_authority_policy(path)
    except AuthorityPolicyError as exc:
        raise OverlayContractError(f"authority_policy_invalid:{exc}") from exc


def _assert_no_promoted_authority(
    value: Any, label: str, policy: AuthorityPolicy
) -> None:
    violations = promoted_authority_violations(value, policy)
    _require(
        not violations,
        f"{label}_promotion_claim_true:{violations[0] if violations else ''}",
    )


def _external_receipt_contract(source_path: str) -> dict[str, str]:
    contract = EXTERNAL_RECEIPT_CONTRACTS.get(source_path)
    _require(type(contract) is dict, f"external_receipt_contract_missing:{source_path}")
    return {str(key): str(value) for key, value in contract.items()}


def _validate_external_receipt_schema(
    *,
    repo_root: Path,
    payload: dict[str, Any],
    contract: dict[str, str],
    label: str,
) -> dict[str, Any]:
    try:
        import jsonschema
    except ImportError as exc:
        raise OverlayContractError("jsonschema_unavailable") from exc
    schema_path = repo_root / _safe_path(
        contract["schema_path"], f"{label}_schema_path"
    )
    schema_identity = _source_file_identity(
        repo_root, payload["source_commit_sha"], contract["schema_path"]
    )
    schema_raw = _read(schema_path, f"{label}_schema")
    _require(
        len(schema_raw) == schema_identity["bytes"]
        and _sha256(schema_raw) == schema_identity["sha256"],
        f"{label}_schema_source_mismatch",
    )
    schema = _strict_object(schema_path, f"{label}_schema")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as exc:
        raise OverlayContractError(f"{label}_schema_invalid:{exc.json_path}") from exc
    return schema_identity


def _assert_nonpromoting_receipt(
    payload: dict[str, Any],
    label: str,
    *,
    expected_source_sha: str,
    contract: dict[str, str],
    authority_policy: AuthorityPolicy,
) -> None:
    _require(
        payload.get("schema_version") == contract["schema_version"],
        f"{label}_schema_version_invalid",
    )
    _require(
        payload.get("truth_class") == contract["truth_class"],
        f"{label}_truth_class_invalid",
    )
    _require(
        payload.get("source_commit_sha") == expected_source_sha,
        f"{label}_source_commit_mismatch",
    )
    _require(
        payload.get("artifact_hash")
        == _canonical_object_hash(payload, excluded={"artifact_hash"}),
        f"{label}_artifact_hash_invalid",
    )
    claims = payload.get("claims")
    _require(type(claims) is dict, f"{label}_claims_invalid")
    for key in NONPROMOTING_CLAIMS:
        if key in payload:
            _require(payload[key] is False, f"{label}_promotion_claim_true:{key}")
        if key in claims:
            _require(claims[key] is False, f"{label}_promotion_claim_true:{key}")
    _require(payload.get("status") != "ready", f"{label}_status_unbounded")
    _require(
        payload.get("verification_hierarchy_operator_manifest_attached") is False,
        f"{label}_operator_manifest_promoted",
    )
    _require(
        payload.get("verification_hierarchy_credit") is False,
        f"{label}_verification_hierarchy_promoted",
    )
    runtimes = payload.get("runtimes")
    _require(
        type(runtimes) is dict and set(runtimes) == {"opensees", "calculix"},
        f"{label}_runtimes_invalid",
    )
    for runtime_id, runtime in runtimes.items():
        _require(type(runtime) is dict, f"{label}_{runtime_id}_runtime_invalid")
        license_row = runtime.get("license")
        _require(type(license_row) is dict, f"{label}_{runtime_id}_license_invalid")
        _require(
            license_row.get("product_legal_approval") is False,
            f"{label}_{runtime_id}_product_legal_approval_promoted",
        )
        _require(
            license_row.get("commercial_redistribution_approved") is False,
            f"{label}_{runtime_id}_commercial_redistribution_promoted",
        )
    replay = payload.get("replay_provenance")
    _require(type(replay) is dict, f"{label}_replay_provenance_invalid")
    _require(
        replay.get("external_runtime_executed_in_this_generation") is False,
        f"{label}_external_runtime_freshness_promoted",
    )
    _require(
        replay.get("external_execution_reused") is True,
        f"{label}_external_execution_reuse_invalid",
    )
    _require(
        type(payload.get("technical_contract_pass")) is bool
        and replay.get("current_product_replay_pass")
        is payload["technical_contract_pass"],
        f"{label}_current_product_replay_invalid",
    )
    _require(
        type(replay.get("reuse_reason")) is str
        and bool(replay["reuse_reason"].strip()),
        f"{label}_reuse_reason_invalid",
    )
    expected_status = "partial" if payload["technical_contract_pass"] else "blocked"
    _require(payload.get("status") == expected_status, f"{label}_status_invalid")
    claim_boundary = payload.get("claim_boundary")
    _require(type(claim_boundary) is str, f"{label}_claim_boundary_invalid")
    _require(
        _sha256(claim_boundary.encode("utf-8")) == contract["claim_boundary_sha256"],
        f"{label}_claim_boundary_invalid",
    )
    _assert_no_promoted_authority(payload, label, authority_policy)


def _technical_contracts(repo_root: Path, source_sha: str) -> dict[str, Any]:
    rows = []
    for lane, workflow in TECHNICAL_LANES.items():
        template = f"{lane}-technical-handoff-{{run_id}}-{{run_attempt}}-{{source_sha}}"
        rows.append(
            {
                "lane": lane,
                "workflow": _source_file_identity(repo_root, source_sha, workflow),
                "handoff_artifact_name_template": template,
                "attestation_artifact_name_template": template + "-attestation",
                "authority": "technical_only",
                "promotion_eligible": False,
            }
        )
    return {
        "pair_schema": _source_file_identity(repo_root, source_sha, PAIR_SCHEMA),
        "pair_verifier": _source_file_identity(repo_root, source_sha, PAIR_VERIFIER),
        "lanes": rows,
        "promotion_eligible": False,
    }


def _validate_schema(repo_root: Path, payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise OverlayContractError("jsonschema_unavailable") from exc
    source_sha = payload.get("source", {}).get("commit_sha")
    _require(type(source_sha) is str, "overlay_schema_source_invalid")
    schema_identity = _source_file_identity(
        repo_root, source_sha, SCHEMA_PATH.as_posix()
    )
    schema_path = repo_root / SCHEMA_PATH
    schema_raw = _read(schema_path, "overlay_schema")
    _require(
        len(schema_raw) == schema_identity["bytes"]
        and _sha256(schema_raw) == schema_identity["sha256"],
        "overlay_schema_source_mismatch",
    )
    schema = _strict_object(schema_path, "overlay_schema")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as exc:
        raise OverlayContractError(f"overlay_schema_invalid:{exc.json_path}") from exc


def build_overlay(
    *,
    repo_root: Path,
    out_dir: Path,
    repository: str,
    source_sha: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    event: str,
) -> dict[str, Any]:
    repo_root = _safe_directory(repo_root, "repo_root")
    _require(REPOSITORY.fullmatch(repository) is not None, "repository_invalid")
    _require(
        SHA.fullmatch(source_sha) is not None and source_sha != "0" * 40,
        "source_sha_invalid",
    )
    _safe_integer(workflow_run_id, "workflow_run_id")
    _safe_integer(workflow_run_attempt, "workflow_run_attempt")
    _require(event in {"schedule", "workflow_dispatch"}, "workflow_event_invalid")
    head = _git_text(repo_root, "rev-parse", "HEAD")
    _require(head == source_sha, "source_sha_not_head")
    tree_sha = _git_text(repo_root, "rev-parse", f"{source_sha}^{{tree}}")
    _require(SHA.fullmatch(tree_sha) is not None, "source_tree_sha_invalid")
    _require(not out_dir.exists(), "overlay_output_already_exists")
    out_dir.mkdir(parents=True)
    out_dir = _safe_directory(out_dir, "overlay_output")
    authority_policy = _source_authority_policy(repo_root, source_sha)

    release_rows: list[dict[str, Any]] = []
    for relative in RELEASE_FILES:
        release_rows.append(
            _copy_identity(
                source=repo_root / relative,
                overlay_root=out_dir,
                overlay_relative=f"release-files/{relative}",
                path=relative,
            )
        )

    external_rows: list[dict[str, Any]] = []
    for index, (source_path, product_state_input_path) in enumerate(EXTERNAL_RECEIPTS):
        source = repo_root / source_path
        contract = _external_receipt_contract(source_path)
        _require(
            product_state_input_path == contract["product_state_input_path"],
            f"external_receipt_route_contract_mismatch:{index}",
        )
        payload = _strict_object(source, f"external_receipt:{index}")
        _assert_nonpromoting_receipt(
            payload,
            f"external_receipt:{index}",
            expected_source_sha=source_sha,
            contract=contract,
            authority_policy=authority_policy,
        )
        schema_identity = _validate_external_receipt_schema(
            repo_root=repo_root,
            payload=payload,
            contract=contract,
            label=f"external_receipt:{index}",
        )
        overlay_path = f"external-vv-nonpromoting/{Path(source_path).name}"
        identity = _copy_identity(
            source=source,
            overlay_root=out_dir,
            overlay_relative=overlay_path,
            path=source_path,
        )
        external_rows.append(
            {
                "source_path": source_path,
                "overlay_path": overlay_path,
                "product_state_input_path": product_state_input_path,
                "schema_version": str(payload.get("schema_version", "")),
                "schema_path": schema_identity["path"],
                "schema_blob_sha": schema_identity["blob_sha"],
                "schema_sha256": schema_identity["sha256"],
                "bytes": identity["bytes"],
                "sha256": identity["sha256"],
                "technical_contract_pass": payload.get("technical_contract_pass")
                is True,
                "promotion_eligible": False,
            }
        )

    from scripts import check_generated_artifact_dag

    violations = check_generated_artifact_dag.validate_post_main_overlay_outputs(
        repo_root=repo_root,
        expected_source_sha=source_sha,
    )
    _require(not violations, "post_main_release_leaf_invalid:" + ",".join(violations))
    workflow = _source_file_identity(
        repo_root, source_sha, ".github/workflows/nightly-full-quality.yml"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "source": {
            "commit_sha": source_sha,
            "tree_sha": tree_sha,
            "ref": "refs/heads/main",
        },
        "producer": {
            "workflow_name": "Nightly Full Quality",
            "workflow_path": workflow["path"],
            "workflow_blob_sha": workflow["blob_sha"],
            "workflow_sha256": workflow["sha256"],
            "event": event,
            "run_id": workflow_run_id,
            "run_attempt": workflow_run_attempt,
        },
        "authority_flow": {
            "producer": "Nightly Full Quality",
            "consumer": "Product State Current",
            "cycle_free": True,
        },
        "generated_artifact_dag": {
            "validator_path": "scripts/check_generated_artifact_dag.py",
            "release_leaf_contract_pass": True,
            "violations": [],
        },
        "release_files": release_rows,
        "technical_handoff_contracts": _technical_contracts(repo_root, source_sha),
        "external_vv_nonpromotion": {
            "receipts": external_rows,
            "effective_claims": {key: False for key in NONPROMOTING_EFFECTIVE_CLAIMS},
            "promotion_eligible": False,
        },
        "contract_pass": True,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    _validate_schema(repo_root, payload)
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _validate_source_identity(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    repository: str | None,
    source_sha: str | None,
    workflow_run_id: int | None,
    workflow_run_attempt: int | None,
) -> None:
    source = payload["source"]
    producer = payload["producer"]
    effective_sha = source_sha or source["commit_sha"]
    _require(source["commit_sha"] == effective_sha, "overlay_source_sha_mismatch")
    _require(
        _git_text(repo_root, "rev-parse", "HEAD") == effective_sha,
        "overlay_source_not_head",
    )
    _require(
        _git_text(repo_root, "rev-parse", f"{effective_sha}^{{tree}}")
        == source["tree_sha"],
        "overlay_source_tree_mismatch",
    )
    if repository is not None:
        _require(payload["repository"] == repository, "overlay_repository_mismatch")
    if workflow_run_id is not None:
        _require(producer["run_id"] == workflow_run_id, "overlay_run_id_mismatch")
    if workflow_run_attempt is not None:
        _require(
            producer["run_attempt"] == workflow_run_attempt,
            "overlay_run_attempt_mismatch",
        )
    workflow = _source_file_identity(
        repo_root, effective_sha, producer["workflow_path"]
    )
    _require(
        workflow["blob_sha"] == producer["workflow_blob_sha"],
        "overlay_workflow_blob_mismatch",
    )
    _require(
        workflow["sha256"] == producer["workflow_sha256"],
        "overlay_workflow_sha256_mismatch",
    )


def _validate_file_rows(
    *,
    overlay_root: Path,
    rows: Iterable[dict[str, Any]],
    expected_paths: set[str],
    path_key: str,
) -> None:
    observed: set[str] = set()
    total = 0
    for index, row in enumerate(rows):
        path = _safe_path(row[path_key], f"file_path:{index}")
        overlay_path = _safe_path(row["overlay_path"], f"overlay_path:{index}")
        _require(path not in observed, f"duplicate_file_path:{path}")
        observed.add(path)
        raw = _read(overlay_root / overlay_path, f"overlay_file:{overlay_path}")
        total += len(raw)
        _require(total <= MAX_TOTAL_BYTES, "overlay_total_size_exceeded")
        _require(row["bytes"] == len(raw), f"overlay_file_size_mismatch:{path}")
        _require(row["sha256"] == _sha256(raw), f"overlay_file_digest_mismatch:{path}")
        if path.endswith(".json"):
            _strict_object(overlay_root / overlay_path, f"overlay_json:{path}")
    _require(observed == expected_paths, "overlay_file_set_mismatch")


def _validate_external_receipt_routes(rows: Iterable[dict[str, Any]]) -> None:
    expected = {
        source_path: {
            "overlay_path": f"external-vv-nonpromoting/{Path(source_path).name}",
            "product_state_input_path": product_state_input_path,
            "schema_path": _external_receipt_contract(source_path)["schema_path"],
        }
        for source_path, product_state_input_path in EXTERNAL_RECEIPTS
    }
    observed: set[str] = set()
    for index, row in enumerate(rows):
        source_path = _safe_path(row["source_path"], f"external_source_path:{index}")
        overlay_path = _safe_path(row["overlay_path"], f"external_overlay_path:{index}")
        product_state_input_path = _safe_path(
            row["product_state_input_path"],
            f"external_product_state_input_path:{index}",
        )
        _require(source_path not in observed, f"external_route_duplicate:{source_path}")
        observed.add(source_path)
        route = expected.get(source_path)
        _require(route is not None, f"external_route_unknown:{source_path}")
        _require(
            overlay_path == route["overlay_path"]
            and product_state_input_path == route["product_state_input_path"]
            and row.get("schema_path") == route["schema_path"],
            f"external_route_mismatch:{source_path}",
        )
    _require(observed == set(expected), "external_route_set_mismatch")


def _validate_release_routes(rows: Iterable[dict[str, Any]]) -> None:
    expected = {path: f"release-files/{path}" for path in RELEASE_FILES}
    observed: set[str] = set()
    for index, row in enumerate(rows):
        path = _safe_path(row["path"], f"release_path:{index}")
        overlay_path = _safe_path(row["overlay_path"], f"release_overlay_path:{index}")
        _require(path not in observed, f"release_route_duplicate:{path}")
        observed.add(path)
        _require(expected.get(path) == overlay_path, f"release_route_mismatch:{path}")
    _require(observed == set(expected), "release_route_set_mismatch")


def validate_overlay(
    *,
    repo_root: Path,
    overlay_root: Path,
    repository: str | None = None,
    source_sha: str | None = None,
    workflow_run_id: int | None = None,
    workflow_run_attempt: int | None = None,
) -> dict[str, Any]:
    repo_root = _safe_directory(repo_root, "repo_root")
    overlay_root = _safe_directory(overlay_root, "overlay_root")
    payload = _strict_object(overlay_root / MANIFEST_NAME, "overlay_manifest")
    _validate_schema(repo_root, payload)
    _validate_source_identity(
        payload,
        repo_root=repo_root,
        repository=repository,
        source_sha=source_sha,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    authority_policy = _source_authority_policy(
        repo_root, payload["source"]["commit_sha"]
    )
    _validate_release_routes(payload["release_files"])
    _validate_file_rows(
        overlay_root=overlay_root,
        rows=payload["release_files"],
        expected_paths=set(RELEASE_FILES),
        path_key="path",
    )
    external_rows = payload["external_vv_nonpromotion"]["receipts"]
    _require(
        payload["external_vv_nonpromotion"]["effective_claims"]
        == {key: False for key in NONPROMOTING_EFFECTIVE_CLAIMS},
        "external_effective_claims_invalid",
    )
    _validate_external_receipt_routes(external_rows)
    _validate_file_rows(
        overlay_root=overlay_root,
        rows=external_rows,
        expected_paths={path for path, _ in EXTERNAL_RECEIPTS},
        path_key="source_path",
    )
    for row in external_rows:
        contract = _external_receipt_contract(row["source_path"])
        receipt = _strict_object(
            overlay_root / row["overlay_path"],
            f"external_receipt:{row['source_path']}",
        )
        label = f"external_receipt:{row['source_path']}"
        _assert_nonpromoting_receipt(
            receipt,
            label,
            expected_source_sha=payload["source"]["commit_sha"],
            contract=contract,
            authority_policy=authority_policy,
        )
        schema_identity = _validate_external_receipt_schema(
            repo_root=repo_root,
            payload=receipt,
            contract=contract,
            label=label,
        )
        _require(
            row["schema_path"] == schema_identity["path"]
            and row["schema_blob_sha"] == schema_identity["blob_sha"]
            and row["schema_sha256"] == schema_identity["sha256"],
            "external_receipt_schema_identity_mismatch",
        )
        _require(
            receipt.get("schema_version") == row["schema_version"],
            "external_receipt_schema_mismatch",
        )
        _require(
            (receipt.get("technical_contract_pass") is True)
            == row["technical_contract_pass"],
            "external_receipt_contract_mismatch",
        )
    contracts = payload["technical_handoff_contracts"]
    expected_contracts = _technical_contracts(
        repo_root, payload["source"]["commit_sha"]
    )
    _require(contracts == expected_contracts, "technical_handoff_contract_mismatch")
    _require(payload["contract_pass"] is True, "overlay_contract_not_passed")
    _require(
        payload["claim_boundary"] == CLAIM_BOUNDARY, "overlay_claim_boundary_invalid"
    )
    return payload


def materialize_overlay(
    *,
    repo_root: Path,
    overlay_root: Path,
    repository: str | None = None,
    source_sha: str | None = None,
    workflow_run_id: int | None = None,
    workflow_run_attempt: int | None = None,
) -> dict[str, Any]:
    payload = validate_overlay(
        repo_root=repo_root,
        overlay_root=overlay_root,
        repository=repository,
        source_sha=source_sha,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    writes: list[tuple[Path, bytes, str]] = []
    for row in payload["release_files"]:
        relative = row["path"]
        source = overlay_root / row["overlay_path"]
        target = _prepare_materialize_target(
            repo_root,
            relative,
            f"materialize_release:{relative}",
        )
        writes.append(
            (target, _read(source, f"materialize_source:{relative}"), relative)
        )
    for row in payload["external_vv_nonpromotion"]["receipts"]:
        source = overlay_root / row["overlay_path"]
        target_relative = _safe_path(
            row["product_state_input_path"],
            "materialize_product_state_input_path",
        )
        target = _prepare_materialize_target(
            repo_root,
            target_relative,
            f"materialize_external:{target_relative}",
        )
        writes.append(
            (
                target,
                _read(source, f"materialize_source:{target_relative}"),
                target_relative,
            )
        )
    for target, raw, relative in writes:
        _replace_regular_file(target, raw, f"materialize:{relative}")
    violations = __import__(
        "scripts.check_generated_artifact_dag",
        fromlist=["validate_post_main_overlay_outputs"],
    ).validate_post_main_overlay_outputs(
        repo_root=repo_root,
        expected_source_sha=payload["source"]["commit_sha"],
    )
    _require(
        not violations, "materialized_release_leaf_invalid:" + ",".join(violations)
    )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "check", "materialize"))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--repository")
    parser.add_argument("--source-sha")
    parser.add_argument("--workflow-run-id", type=int)
    parser.add_argument("--workflow-run-attempt", type=int)
    parser.add_argument("--event", choices=("schedule", "workflow_dispatch"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.mode == "build":
            _require(args.repository is not None, "repository_required")
            _require(args.source_sha is not None, "source_sha_required")
            _require(args.workflow_run_id is not None, "workflow_run_id_required")
            _require(
                args.workflow_run_attempt is not None, "workflow_run_attempt_required"
            )
            _require(args.event is not None, "event_required")
            payload = build_overlay(
                repo_root=args.repo_root,
                out_dir=args.overlay_root,
                repository=args.repository,
                source_sha=args.source_sha,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
                event=args.event,
            )
        elif args.mode == "check":
            payload = validate_overlay(
                repo_root=args.repo_root,
                overlay_root=args.overlay_root,
                repository=args.repository,
                source_sha=args.source_sha,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
            )
        else:
            payload = materialize_overlay(
                repo_root=args.repo_root,
                overlay_root=args.overlay_root,
                repository=args.repository,
                source_sha=args.source_sha,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
            )
    except OverlayContractError as exc:
        print(f"post-main overlay contract failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
