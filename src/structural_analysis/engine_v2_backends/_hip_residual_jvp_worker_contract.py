"""Non-promoting pre-execution contract for the dedicated gfx1100 lane.

The historical G1 worker mixed a local Python callback probe with production
hardware claims.  The current-main contract deliberately has no hardware
execution entry point.  It binds only the immutable inputs that a dedicated
runner must consume; hardware, provenance, performance, and release authority
remain external blockers until independently verified receipts are imported.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import re
from typing import Any, Final


PROFILE: Final = "g1_gfx1100_preexecution_worker_contract.v2"
SCHEMA_VERSION: Final = "g1-gfx1100-preexecution-worker-contract.v2"
EXPECTED_ARCHITECTURE: Final = "gfx1100"
EXPECTED_REPOSITORY: Final = "betelgeuze-kang/Structural-Analysis"
EXPECTED_REPOSITORY_ID: Final = 1136685613
EXPECTED_WORKFLOW_PATH: Final = (
    ".github/workflows/g1-production-mgt-gfx1100-hardware.yml"
)
EXPECTED_WORKFLOW_REF: Final = "refs/heads/main"
EXPECTED_SOURCE_REF: Final = "refs/heads/main"
MAX_RETAINED_WHEEL_BYTES: Final = 512 * 1024 * 1024
REQUIRED_RUNNER_LABELS: Final = (
    "self-hosted",
    "linux",
    "x64",
    "amd",
    "rocm",
    "gfx1100",
    "g1-production-gfx1100",
)
BLOCKERS: Final = (
    "actual_gfx1100_hardware_execution_missing",
    "trusted_hardware_identity_attestation_missing",
    "independent_hardware_operator_attestation_missing",
    "signed_retained_bundle_provenance_not_imported",
    "cross_device_gfx1030_gfx1100_pair_missing",
    "independently_attested_cpu_fallback_zero_missing",
    "gfx1030_gfx1100_terminal_resultir_diagnosticir_parity_missing",
    "atomic_wheel_identity_measurement_missing",
    "end_to_end_cross_device_performance_sweep_missing",
    "release_authority_missing",
)
CLAIM_BOUNDARY: Final = (
    "This deterministic receipt binds the exact source commit, a reproducible "
    "repo-local AST import closure seeded by dynamic recurrence/device paths and "
    "explicit Stage 4, gate, contract, schema, test, release-metadata, and "
    "packaging input bytes, target architecture, GitHub "
    "run identity, dedicated runner identity and labels, retained wheel bytes, "
    "and expected Ed25519 signer public-key hash before execution. It contains no "
    "hardware observation or signature. It cannot prove hardware execution, "
    "signed provenance, cross-device parity, performance, production readiness, "
    "release authority, or G1 closure."
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_RUN_ID_RE = re.compile(r"[1-9][0-9]*")


class HIPResidualJVPWorkerContractError(ValueError):
    """Raised when a pre-execution contract is malformed or overclaims."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def source_set_hash(source_files: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_bytes(dict(sorted(source_files.items()))))


def _receipt_hash(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "receipt_hash"}
    return sha256_bytes(canonical_bytes(body))


def _validate_hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise HIPResidualJVPWorkerContractError(f"{field}_invalid")
    return value


def _validate_relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise HIPResidualJVPWorkerContractError(f"{field}_invalid")
    parts = value.split("/")
    if (
        not value
        or value.startswith("/")
        or value.endswith("/")
        or value.startswith("./")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise HIPResidualJVPWorkerContractError(f"{field}_invalid")
    return value


def _validate_run_repository_identity(
    *,
    repository: object,
    repository_id: object,
    workflow_path: object,
    workflow_ref: object,
    source_ref: object,
) -> None:
    if repository != EXPECTED_REPOSITORY:
        raise HIPResidualJVPWorkerContractError("repository_invalid")
    if type(repository_id) is not int or repository_id != EXPECTED_REPOSITORY_ID:
        raise HIPResidualJVPWorkerContractError("repository_id_invalid")
    if workflow_path != EXPECTED_WORKFLOW_PATH:
        raise HIPResidualJVPWorkerContractError("workflow_path_invalid")
    if workflow_ref != EXPECTED_WORKFLOW_REF:
        raise HIPResidualJVPWorkerContractError("workflow_ref_invalid")
    if source_ref != EXPECTED_SOURCE_REF:
        raise HIPResidualJVPWorkerContractError("source_ref_invalid")


def build_preexecution_receipt(
    *,
    source_commit_sha: str,
    source_files: Mapping[str, str],
    wheel_filename: str,
    wheel_sha256: str,
    wheel_size_bytes: int,
    expected_signer_public_key_sha256: str,
    github_run_id: str,
    github_run_attempt: int,
    artifact_prefix: str,
    expected_runner_id: str,
    receipt_runner_id: str,
    repository: str,
    repository_id: int,
    workflow_path: str,
    workflow_ref: str,
    source_ref: str,
    expected_device_architecture: str = EXPECTED_ARCHITECTURE,
    required_runner_labels: Sequence[str] = REQUIRED_RUNNER_LABELS,
) -> dict[str, Any]:
    """Build an immutable contract-only receipt with no promotion surface."""

    if _COMMIT_RE.fullmatch(source_commit_sha) is None:
        raise HIPResidualJVPWorkerContractError("source_commit_sha_invalid")
    if expected_device_architecture != EXPECTED_ARCHITECTURE:
        raise HIPResidualJVPWorkerContractError("expected_device_architecture_invalid")
    if tuple(required_runner_labels) != REQUIRED_RUNNER_LABELS:
        raise HIPResidualJVPWorkerContractError("required_runner_labels_invalid")
    _validate_run_repository_identity(
        repository=repository,
        repository_id=repository_id,
        workflow_path=workflow_path,
        workflow_ref=workflow_ref,
        source_ref=source_ref,
    )
    expected_prefix = f"g1-mgt-gfx1100-{github_run_id}-{github_run_attempt}"
    expected_receipt_runner = (
        f"{expected_runner_id}::github_run_id={github_run_id}::"
        f"run_attempt={github_run_attempt}"
    )
    if (
        not isinstance(github_run_id, str)
        or _RUN_ID_RE.fullmatch(github_run_id) is None
    ):
        raise HIPResidualJVPWorkerContractError("github_run_id_invalid")
    if (
        type(github_run_attempt) is bool
        or not isinstance(github_run_attempt, int)
        or github_run_attempt <= 0
    ):
        raise HIPResidualJVPWorkerContractError("github_run_attempt_invalid")
    if artifact_prefix != expected_prefix:
        raise HIPResidualJVPWorkerContractError("artifact_prefix_invalid")
    if (
        not isinstance(expected_runner_id, str)
        or not expected_runner_id
        or any(character in expected_runner_id for character in "\r\n")
        or "::github_run_id=" in expected_runner_id
        or "::run_attempt=" in expected_runner_id
    ):
        raise HIPResidualJVPWorkerContractError("expected_runner_id_invalid")
    if receipt_runner_id != expected_receipt_runner:
        raise HIPResidualJVPWorkerContractError("receipt_runner_id_invalid")
    if (
        not wheel_filename
        or wheel_filename in {".", ".."}
        or "/" in wheel_filename
        or "\\" in wheel_filename
    ):
        raise HIPResidualJVPWorkerContractError("wheel_filename_invalid")
    _validate_hash(wheel_sha256, field="wheel_sha256")
    _validate_hash(
        expected_signer_public_key_sha256,
        field="expected_signer_public_key_sha256",
    )
    if type(wheel_size_bytes) is bool or not isinstance(wheel_size_bytes, int):
        raise HIPResidualJVPWorkerContractError("wheel_size_bytes_invalid")
    if wheel_size_bytes <= 0 or wheel_size_bytes > MAX_RETAINED_WHEEL_BYTES:
        raise HIPResidualJVPWorkerContractError("wheel_size_bytes_invalid")
    if not source_files:
        raise HIPResidualJVPWorkerContractError("source_files_missing")
    normalized_source_files: dict[str, str] = {}
    for path, digest in sorted(source_files.items()):
        _validate_relative_path(path, field="source_file_path")
        normalized_source_files[path] = _validate_hash(
            digest,
            field="source_file_sha256",
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "receipt_hash": "sha256:" + "0" * 64,
        "source": {
            "repository_commit_sha": source_commit_sha,
            "input_checksums": normalized_source_files,
            "source_set_hash": source_set_hash(normalized_source_files),
        },
        "target": {
            "device_architecture": EXPECTED_ARCHITECTURE,
            "required_runner_labels": list(REQUIRED_RUNNER_LABELS),
        },
        "run_identity": {
            "repository": repository,
            "repository_id": repository_id,
            "workflow_path": workflow_path,
            "workflow_ref": workflow_ref,
            "source_ref": source_ref,
            "github_run_id": github_run_id,
            "github_run_attempt": github_run_attempt,
            "artifact_prefix": artifact_prefix,
            "expected_runner_id": expected_runner_id,
            "receipt_runner_id": receipt_runner_id,
        },
        "retained_wheel": {
            "filename": wheel_filename,
            "sha256": wheel_sha256,
            "size_bytes": wheel_size_bytes,
        },
        "signer_policy": {
            "algorithm": "ed25519",
            "expected_public_key_sha256": expected_signer_public_key_sha256,
            "private_key_in_repository_or_workflow": False,
        },
        "claims": {
            "hardware_execution_proven": False,
            "signed_provenance": False,
            "release": False,
            "performance": False,
            "production_ready": False,
        },
        "blockers_remaining": list(BLOCKERS),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    validate_preexecution_receipt(payload)
    return payload


def validate_preexecution_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate exact shape, hashes, and the permanently non-promoting claims."""

    if not isinstance(payload, Mapping):
        raise HIPResidualJVPWorkerContractError("receipt_object_required")
    expected_top = {
        "schema_version",
        "profile",
        "receipt_hash",
        "source",
        "target",
        "run_identity",
        "retained_wheel",
        "signer_policy",
        "claims",
        "blockers_remaining",
        "claim_boundary",
    }
    if set(payload) != expected_top:
        raise HIPResidualJVPWorkerContractError("receipt_shape_invalid")
    if payload["schema_version"] != SCHEMA_VERSION or payload["profile"] != PROFILE:
        raise HIPResidualJVPWorkerContractError("receipt_version_invalid")
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        raise HIPResidualJVPWorkerContractError("claim_boundary_invalid")
    if payload["blockers_remaining"] != list(BLOCKERS):
        raise HIPResidualJVPWorkerContractError("blockers_invalid")
    if payload["claims"] != {
        "hardware_execution_proven": False,
        "signed_provenance": False,
        "release": False,
        "performance": False,
        "production_ready": False,
    }:
        raise HIPResidualJVPWorkerContractError("claims_invalid")

    source = payload["source"]
    if not isinstance(source, Mapping) or set(source) != {
        "repository_commit_sha",
        "input_checksums",
        "source_set_hash",
    }:
        raise HIPResidualJVPWorkerContractError("source_shape_invalid")
    if _COMMIT_RE.fullmatch(str(source["repository_commit_sha"])) is None:
        raise HIPResidualJVPWorkerContractError("source_commit_sha_invalid")
    checksums = source["input_checksums"]
    if not isinstance(checksums, Mapping) or not checksums:
        raise HIPResidualJVPWorkerContractError("source_files_missing")
    normalized: dict[str, str] = {}
    for path, digest in checksums.items():
        _validate_relative_path(path, field="source_file_path")
        normalized[path] = _validate_hash(digest, field="source_file_sha256")
    if source["source_set_hash"] != source_set_hash(normalized):
        raise HIPResidualJVPWorkerContractError("source_set_hash_mismatch")

    target = payload["target"]
    if target != {
        "device_architecture": EXPECTED_ARCHITECTURE,
        "required_runner_labels": list(REQUIRED_RUNNER_LABELS),
    }:
        raise HIPResidualJVPWorkerContractError("target_contract_invalid")
    run_identity = payload["run_identity"]
    if not isinstance(run_identity, Mapping) or set(run_identity) != {
        "repository",
        "repository_id",
        "workflow_path",
        "workflow_ref",
        "source_ref",
        "github_run_id",
        "github_run_attempt",
        "artifact_prefix",
        "expected_runner_id",
        "receipt_runner_id",
    }:
        raise HIPResidualJVPWorkerContractError("run_identity_shape_invalid")
    _validate_run_repository_identity(
        repository=run_identity["repository"],
        repository_id=run_identity["repository_id"],
        workflow_path=run_identity["workflow_path"],
        workflow_ref=run_identity["workflow_ref"],
        source_ref=run_identity["source_ref"],
    )
    run_id = run_identity["github_run_id"]
    attempt = run_identity["github_run_attempt"]
    expected_runner = run_identity["expected_runner_id"]
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise HIPResidualJVPWorkerContractError("github_run_id_invalid")
    if type(attempt) is bool or not isinstance(attempt, int) or attempt <= 0:
        raise HIPResidualJVPWorkerContractError("github_run_attempt_invalid")
    if (
        not isinstance(expected_runner, str)
        or not expected_runner
        or any(character in expected_runner for character in "\r\n")
        or "::github_run_id=" in expected_runner
        or "::run_attempt=" in expected_runner
    ):
        raise HIPResidualJVPWorkerContractError("expected_runner_id_invalid")
    if run_identity["artifact_prefix"] != f"g1-mgt-gfx1100-{run_id}-{attempt}":
        raise HIPResidualJVPWorkerContractError("artifact_prefix_invalid")
    expected_receipt_runner = (
        f"{expected_runner}::github_run_id={run_id}::run_attempt={attempt}"
    )
    if run_identity["receipt_runner_id"] != expected_receipt_runner:
        raise HIPResidualJVPWorkerContractError("receipt_runner_id_invalid")
    wheel = payload["retained_wheel"]
    if not isinstance(wheel, Mapping) or set(wheel) != {
        "filename",
        "sha256",
        "size_bytes",
    }:
        raise HIPResidualJVPWorkerContractError("retained_wheel_shape_invalid")
    if (
        not isinstance(wheel["filename"], str)
        or not wheel["filename"]
        or wheel["filename"] in {".", ".."}
        or "/" in wheel["filename"]
        or "\\" in wheel["filename"]
    ):
        raise HIPResidualJVPWorkerContractError("wheel_filename_invalid")
    _validate_hash(wheel["sha256"], field="wheel_sha256")
    if (
        type(wheel["size_bytes"]) is bool
        or not isinstance(wheel["size_bytes"], int)
        or wheel["size_bytes"] <= 0
        or wheel["size_bytes"] > MAX_RETAINED_WHEEL_BYTES
    ):
        raise HIPResidualJVPWorkerContractError("wheel_size_bytes_invalid")
    signer = payload["signer_policy"]
    if not isinstance(signer, Mapping) or set(signer) != {
        "algorithm",
        "expected_public_key_sha256",
        "private_key_in_repository_or_workflow",
    }:
        raise HIPResidualJVPWorkerContractError("signer_policy_shape_invalid")
    if signer["algorithm"] != "ed25519":
        raise HIPResidualJVPWorkerContractError("signer_algorithm_invalid")
    _validate_hash(
        signer["expected_public_key_sha256"],
        field="expected_signer_public_key_sha256",
    )
    if signer["private_key_in_repository_or_workflow"] is not False:
        raise HIPResidualJVPWorkerContractError("private_key_boundary_invalid")
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise HIPResidualJVPWorkerContractError("receipt_hash_mismatch")
    return dict(payload)


__all__ = [
    "BLOCKERS",
    "CLAIM_BOUNDARY",
    "EXPECTED_ARCHITECTURE",
    "EXPECTED_REPOSITORY",
    "EXPECTED_REPOSITORY_ID",
    "EXPECTED_SOURCE_REF",
    "EXPECTED_WORKFLOW_PATH",
    "EXPECTED_WORKFLOW_REF",
    "HIPResidualJVPWorkerContractError",
    "MAX_RETAINED_WHEEL_BYTES",
    "PROFILE",
    "REQUIRED_RUNNER_LABELS",
    "SCHEMA_VERSION",
    "build_preexecution_receipt",
    "canonical_bytes",
    "sha256_bytes",
    "source_set_hash",
    "validate_preexecution_receipt",
]
