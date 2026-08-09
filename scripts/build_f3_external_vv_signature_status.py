#!/usr/bin/env python3
"""Build and verify independent signatures for all F3 external-V&V surfaces."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Final, Mapping, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    F3_REQUIRED_SURFACES,
    F3_STAGE_ORDER,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "f3_external_vv_signature_status.json"
DEFAULT_SIGNATURE_DIR = PRODUCTIZATION / "f3_external_vv_signatures"
SCHEMA = Path(
    "src/structural_analysis/schemas/f3_external_vv_signature_status_v1.schema.json"
)
BUILDER = Path("scripts/build_f3_external_vv_signature_status.py")
VERSION = "f3-external-vv-signature-status.v1"
ENVELOPE_VERSION = "f3-external-vv-signature-envelope.v1"
STAGE_RECEIPTS: dict[str, Path] = {
    "frame3d_linear": PRODUCTIZATION / "f3_frame3d_linear_vertical_evidence.json",
    "frame3d_load_control": PRODUCTIZATION
    / "f3_frame3d_load_control_vertical_evidence.json",
    "frame3d_direct_control": PRODUCTIZATION
    / "f3_frame3d_direct_control_vertical_evidence.json",
    "frame3d_stateful_material": PRODUCTIZATION
    / "f3_frame3d_stateful_material_vertical_evidence.json",
    "modal_buckling": PRODUCTIZATION / "f3_modal_buckling_vertical_evidence.json",
    "sdof_authenticated_transient": PRODUCTIZATION
    / "f3_sdof_authenticated_transient_vertical_evidence.json",
    "mdof_linear_transient": PRODUCTIZATION
    / "f3_mdof_linear_transient_vertical_evidence.json",
    "nonlinear_mdof": PRODUCTIZATION / "f3_nonlinear_mdof_vertical_evidence.json",
    "shell": PRODUCTIZATION / "f3_shell_vertical_evidence.json",
    "contact": PRODUCTIZATION / "f3_contact_vertical_evidence.json",
}
CLAIM_BOUNDARY = (
    "This fail-closed v1 status replays every canonical F3 stage receipt, its "
    "source ancestry and input checksums, all nine required surface bindings, "
    "and optional detached Ed25519 signatures. Cryptographic consistency is "
    "reported separately from independently trusted identity. The production "
    "trust-anchor set is empty, so v1 remains partial and never promotes F3."
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_TREE_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True)
class TrustedSignerAnchor:
    """Repository-owned identity policy; envelope claims cannot create trust."""

    organization_id: str
    signer_id: str
    public_key_sha256: str
    independence_authority_receipt_sha256: str


# Intentionally empty for v1. Adding an anchor is a separately reviewed authority
# change; no CLI or envelope field can extend this set.
TRUSTED_SIGNER_ANCHORS: Final[tuple[TrustedSignerAnchor, ...]] = ()


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("f3_signature_json_object_required")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"f3_{label}_fields_invalid")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_commit_sha(value: Any) -> bool:
    return isinstance(value, str) and _COMMIT_RE.fullmatch(value) is not None


def _canonical_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise ValueError("f3_repository_path_not_canonical")
    if path.as_posix() != str(value).replace("\\", "/"):
        raise ValueError("f3_repository_path_not_canonical")
    return path


def _git(
    root: Path,
    *args: str,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", str(root.resolve()), *args]
    completed = subprocess.run(
        command,
        shell=False,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0 and not allow_failure:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"f3_git_command_failed:{args[0]}:{detail}")
    return completed


def _git_text(root: Path, *args: str) -> str:
    return _git(root, *args).stdout.decode("utf-8").strip()


def _git_commit(root: Path, revision: str = "HEAD") -> str:
    commit = _git_text(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if not _is_commit_sha(commit):
        raise ValueError("f3_git_commit_sha_invalid")
    return commit


def _git_tree_oid(root: Path, commit: str) -> str:
    if not _is_commit_sha(commit):
        raise ValueError("f3_git_commit_sha_invalid")
    tree_oid = _git_text(root, "rev-parse", "--verify", f"{commit}^{{tree}}")
    if _TREE_OID_RE.fullmatch(tree_oid) is None:
        raise ValueError("f3_git_tree_oid_invalid")
    return tree_oid


def _git_blob(root: Path, commit: str, path: Path) -> bytes | None:
    if not _is_commit_sha(commit):
        raise ValueError("f3_git_commit_sha_invalid")
    canonical = _canonical_repo_path(path)
    completed = _git(
        root,
        "show",
        f"{commit}:{canonical.as_posix()}",
        allow_failure=True,
    )
    return completed.stdout if completed.returncode == 0 else None


def _git_blob_sha256(root: Path, commit: str, path: Path) -> str | None:
    blob = _git_blob(root, commit, path)
    return None if blob is None else _sha_bytes(blob)


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    if not _is_commit_sha(ancestor) or not _is_commit_sha(descendant):
        raise ValueError("f3_git_commit_sha_invalid")
    completed = _git(
        root,
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
        allow_failure=True,
    )
    if completed.returncode not in (0, 1):
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"f3_git_ancestry_check_failed:{detail}")
    return completed.returncode == 0


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _receipt_hash(payload: dict[str, Any]) -> str:
    return _sha_bytes(
        canonical_bytes(
            {key: value for key, value in payload.items() if key != "receipt_hash"}
        )
    )


def _repository_target(root: Path, path: Path) -> Path:
    canonical = _canonical_repo_path(path)
    resolved_root = root.resolve()
    target = resolved_root
    for component in canonical.parts:
        target /= component
        if target.is_symlink():
            raise ValueError("f3_repository_path_symlink_component")
    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise ValueError("f3_repository_path_escape")
    return target


def _aggregate_source_binding(
    *, root: Path, source_commit_sha: str | None = None
) -> dict[str, Any]:
    source_commit = _git_commit(root, source_commit_sha or "HEAD")
    head_commit = _git_commit(root)
    source_tree_oid = _git_tree_oid(root, source_commit)
    source_is_ancestor = _git_is_ancestor(root, source_commit, head_commit)
    rows: dict[str, dict[str, Any]] = {}
    for label, path in (("builder", BUILDER), ("schema", SCHEMA)):
        target = _repository_target(root, path)
        worktree_sha = _sha_bytes(target.read_bytes()) if target.is_file() else None
        committed_sha = _git_blob_sha256(root, source_commit, path)
        rows[label] = {
            "path": path.as_posix(),
            "committed_sha256": committed_sha,
            "worktree_sha256": worktree_sha,
            "worktree_matches_committed_blob": bool(
                committed_sha is not None and committed_sha == worktree_sha
            ),
        }
    return {
        "source_commit_sha": source_commit,
        "source_tree_oid": source_tree_oid,
        "source_commit_is_ancestor_of_head": source_is_ancestor,
        "builder": rows["builder"],
        "schema": rows["schema"],
        "exact_source_binding": bool(
            source_is_ancestor
            and all(row["worktree_matches_committed_blob"] for row in rows.values())
        ),
    }


def _source_input_binding(
    *,
    root: Path,
    source_commit_sha: str,
    aggregate_source_commit_sha: str,
    checksums: Any,
) -> dict[str, Any]:
    if not isinstance(checksums, dict) or not checksums:
        raise ValueError("f3_source_input_checksums_invalid")
    source_mismatches: list[str] = []
    aggregate_mismatches: list[str] = []
    for raw_path, expected in sorted(checksums.items()):
        if not isinstance(raw_path, str) or not _is_sha256(expected):
            raise ValueError("f3_source_input_checksum_invalid")
        path = _canonical_repo_path(raw_path)
        if _git_blob_sha256(root, source_commit_sha, path) != expected:
            source_mismatches.append(path.as_posix())
        if _git_blob_sha256(root, aggregate_source_commit_sha, path) != expected:
            aggregate_mismatches.append(path.as_posix())
    return {
        "source_input_count": len(checksums),
        "recorded_source_mismatch_paths": source_mismatches,
        "aggregate_source_mismatch_paths": aggregate_mismatches,
        "recorded_source_inputs_match": not source_mismatches,
        "aggregate_source_inputs_match": not aggregate_mismatches,
    }


def _predecessor_binding(
    *,
    stage: str,
    receipt: Mapping[str, Any],
    root: Path,
    aggregate_source_commit_sha: str,
) -> dict[str, Any]:
    index = F3_STAGE_ORDER.index(stage)
    gate = receipt["stage_gate"]
    replay = receipt.get("predecessor_replay")
    if index == 0:
        if (
            gate.get("predecessor_stage") is not None
            or gate.get("predecessor_receipt_sha256") is not None
            or replay is not None
        ):
            raise ValueError("f3_unexpected_predecessor_binding")
        return {
            "required": False,
            "predecessor_stage": None,
            "predecessor_receipt_path": None,
            "predecessor_receipt_sha256": None,
            "canonical_replay_sha256": None,
            "semantic_replay_hash_recomputed": None,
            "semantic_replay_hash_matches": None,
            "binding_pass": True,
        }

    predecessor_stage = F3_STAGE_ORDER[index - 1]
    predecessor_path = STAGE_RECEIPTS[predecessor_stage]
    if gate.get("predecessor_stage") != predecessor_stage:
        raise ValueError("f3_predecessor_stage_mismatch")
    if not isinstance(replay, dict):
        raise ValueError("f3_predecessor_replay_missing")
    if replay.get("source_receipt_path") != predecessor_path.as_posix():
        raise ValueError("f3_predecessor_path_not_canonical")
    predecessor_target = _repository_target(root, predecessor_path)
    predecessor_sha = _sha_bytes(predecessor_target.read_bytes())
    aggregate_predecessor_sha = _git_blob_sha256(
        root, aggregate_source_commit_sha, predecessor_path
    )
    if replay.get("source_receipt_sha256") != predecessor_sha:
        raise ValueError("f3_predecessor_receipt_hash_mismatch")
    predecessor_gate_replay_sha = gate.get("predecessor_receipt_sha256")
    if not _is_sha256(predecessor_gate_replay_sha):
        raise ValueError("f3_predecessor_replay_hash_invalid")
    semantic_replay_hash_recomputed = index == 1
    canonical_replay_sha = (
        _sha_bytes(canonical_bytes(replay)) if semantic_replay_hash_recomputed else None
    )
    semantic_replay_hash_matches = bool(
        semantic_replay_hash_recomputed
        and predecessor_gate_replay_sha == canonical_replay_sha
    )
    if semantic_replay_hash_recomputed and not semantic_replay_hash_matches:
        raise ValueError("f3_predecessor_replay_hash_mismatch")
    if replay.get("current_source_replay_executed") is not True:
        raise ValueError("f3_predecessor_replay_not_executed")
    if replay.get("public_product_promotion_passed") is not True:
        raise ValueError("f3_predecessor_replay_not_passing")
    if replay.get("replayed_source_commit_sha") != receipt.get("source_commit_sha"):
        raise ValueError("f3_predecessor_replayed_source_mismatch")
    predecessor_receipt = _read(predecessor_target)
    persisted_source = replay.get("persisted_source_commit_sha")
    if persisted_source is not None and persisted_source != predecessor_receipt.get(
        "source_commit_sha"
    ):
        raise ValueError("f3_predecessor_persisted_source_mismatch")
    if replay.get("input_checksums_unchanged") not in (None, True):
        raise ValueError("f3_predecessor_input_checksum_mismatch")
    return {
        "required": True,
        "predecessor_stage": predecessor_stage,
        "predecessor_receipt_path": predecessor_path.as_posix(),
        "predecessor_receipt_sha256": predecessor_sha,
        "predecessor_gate_replay_sha256": predecessor_gate_replay_sha,
        "canonical_replay_sha256": canonical_replay_sha,
        "semantic_replay_hash_recomputed": semantic_replay_hash_recomputed,
        "semantic_replay_hash_matches": semantic_replay_hash_matches,
        "aggregate_tree_receipt_sha256": aggregate_predecessor_sha,
        "binding_pass": bool(
            aggregate_predecessor_sha == predecessor_sha
            and semantic_replay_hash_matches
        ),
    }


def stage_evidence_payload(
    stage: str,
    *,
    root: Path = ROOT,
    aggregate_source_commit_sha: str | None = None,
    _aggregate_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in F3_STAGE_ORDER:
        raise ValueError(f"unknown_f3_stage:{stage}")
    path = STAGE_RECEIPTS[stage]
    target = _repository_target(root, path)
    receipt = _read(target)
    gate = receipt.get("stage_gate")
    surfaces = receipt.get("surface_artifacts")
    if not isinstance(gate, dict) or not isinstance(surfaces, dict):
        raise ValueError("f3_stage_receipt_shape_invalid")
    if receipt.get("contract_pass") is not True or receipt.get("status") != "ready":
        raise ValueError("f3_stage_receipt_not_ready")
    if gate.get("stage") != stage or gate.get("stage_index") != F3_STAGE_ORDER.index(
        stage
    ):
        raise ValueError("f3_stage_identity_invalid")
    if tuple(gate.get("required_surfaces", ())) != F3_REQUIRED_SURFACES:
        raise ValueError("f3_required_surface_order_invalid")
    if tuple(gate.get("verified_surfaces", ())) != F3_REQUIRED_SURFACES:
        raise ValueError("f3_verified_surface_order_invalid")
    if set(surfaces) != set(F3_REQUIRED_SURFACES):
        raise ValueError("f3_surface_artifact_set_invalid")
    bindings = gate.get("evidence_artifact_sha256")
    if not isinstance(bindings, dict) or set(bindings) != set(F3_REQUIRED_SURFACES):
        raise ValueError("f3_surface_binding_set_invalid")
    for surface in F3_REQUIRED_SURFACES:
        if bindings[surface] != _sha_bytes(canonical_bytes(surfaces[surface])):
            raise ValueError(f"f3_surface_binding_mismatch:{surface}")
    source_commit = receipt.get("source_commit_sha")
    if not _is_commit_sha(source_commit):
        raise ValueError("f3_source_commit_invalid")
    if gate.get("source_commit_sha") != source_commit:
        raise ValueError("f3_stage_gate_source_commit_mismatch")
    aggregate_source = dict(
        _aggregate_source
        or _aggregate_source_binding(
            root=root, source_commit_sha=aggregate_source_commit_sha
        )
    )
    aggregate_commit = aggregate_source["source_commit_sha"]
    stage_tree_oid = _git_tree_oid(root, source_commit)
    stage_receipt_sha = _sha_bytes(target.read_bytes())
    aggregate_receipt_sha = _git_blob_sha256(root, aggregate_commit, path)
    source_inputs = _source_input_binding(
        root=root,
        source_commit_sha=source_commit,
        aggregate_source_commit_sha=aggregate_commit,
        checksums=receipt.get("source_input_checksums"),
    )
    predecessor = _predecessor_binding(
        stage=stage,
        receipt=receipt,
        root=root,
        aggregate_source_commit_sha=aggregate_commit,
    )
    source_is_ancestor = _git_is_ancestor(root, source_commit, aggregate_commit)
    canonical_receipt_bound = aggregate_receipt_sha == stage_receipt_sha
    source_binding_pass = bool(
        source_is_ancestor
        and canonical_receipt_bound
        and source_inputs["recorded_source_inputs_match"]
        and source_inputs["aggregate_source_inputs_match"]
        and predecessor["binding_pass"]
    )
    external = surfaces["external_vv"]
    return {
        "stage": stage,
        "stage_index": F3_STAGE_ORDER.index(stage),
        "source_commit_sha": source_commit,
        "source_tree_oid": stage_tree_oid,
        "aggregate_source_commit_sha": aggregate_commit,
        "aggregate_source_tree_oid": aggregate_source["source_tree_oid"],
        "stage_receipt_path": path.as_posix(),
        "stage_receipt_sha256": stage_receipt_sha,
        "aggregate_tree_stage_receipt_sha256": aggregate_receipt_sha,
        "external_vv_artifact_sha256": bindings["external_vv"],
        "external_vv_reference_profile": external.get("reference_profile"),
        "required_surface_count": len(F3_REQUIRED_SURFACES),
        "all_nine_surfaces_verified": True,
        "recorded_signature_status": gate.get("external_vv_signature_status"),
        "source_commit_is_ancestor_of_aggregate": source_is_ancestor,
        "canonical_stage_receipt_bound": canonical_receipt_bound,
        "source_input_binding": source_inputs,
        "predecessor_binding": predecessor,
        "current_source_binding_pass": source_binding_pass,
    }


def create_unsigned_envelope(
    *,
    stage: str,
    organization_id: str,
    signer_id: str,
    independent_from_repository_operator: bool,
    independence_authority_receipt_sha256: str | None = None,
    root: Path = ROOT,
    aggregate_source_commit_sha: str | None = None,
) -> dict[str, Any]:
    if not organization_id.strip() or not signer_id.strip():
        raise ValueError("f3_signature_identity_required")
    if independence_authority_receipt_sha256 is not None and not _is_sha256(
        independence_authority_receipt_sha256
    ):
        raise ValueError("f3_independence_authority_receipt_hash_invalid")
    evidence = stage_evidence_payload(
        stage,
        root=root,
        aggregate_source_commit_sha=aggregate_source_commit_sha,
    )
    evidence["signer_attestation"] = {
        "organization_id": organization_id.strip(),
        "signer_id": signer_id.strip(),
        "independent_from_repository_operator": independent_from_repository_operator,
        "independence_authority_receipt_sha256": (
            independence_authority_receipt_sha256
        ),
    }
    payload: dict[str, Any] = {
        "schema_version": ENVELOPE_VERSION,
        "receipt_hash": "",
        "evidence_payload": evidence,
        "signature": {
            "state": "unsigned",
            "algorithm": None,
            "public_key_spki_base64": None,
            "public_key_sha256": None,
            "signature_base64": None,
            "signed_payload_hash": _sha_bytes(canonical_bytes(evidence)),
        },
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return payload


def envelope_evidence_bytes(payload: dict[str, Any]) -> bytes:
    return canonical_bytes(payload["evidence_payload"])


def _load_ed25519_public_key(public_key_pem: bytes) -> Any:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("f3_signature_public_key_not_ed25519")
    return key


def attach_signature(
    payload: dict[str, Any], *, signature_bytes: bytes, public_key_pem: bytes
) -> dict[str, Any]:
    updated = deepcopy(payload)
    if updated["signature"]["state"] != "unsigned":
        raise ValueError("f3_signature_envelope_not_unsigned")
    key = _load_ed25519_public_key(public_key_pem)
    key.verify(signature_bytes, envelope_evidence_bytes(updated))
    from cryptography.hazmat.primitives import serialization

    spki = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    updated["signature"] = {
        "state": "verified",
        "algorithm": "Ed25519",
        "public_key_spki_base64": base64.b64encode(spki).decode("ascii"),
        "public_key_sha256": _sha_bytes(spki),
        "signature_base64": base64.b64encode(signature_bytes).decode("ascii"),
        "signed_payload_hash": _sha_bytes(envelope_evidence_bytes(updated)),
    }
    updated["receipt_hash"] = _receipt_hash(updated)
    return updated


def validate_envelope(payload: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _require_exact_keys(
        payload,
        {"schema_version", "receipt_hash", "evidence_payload", "signature"},
        label="signature_envelope",
    )
    if payload.get("schema_version") != ENVELOPE_VERSION:
        raise ValueError("f3_signature_envelope_schema_invalid")
    if payload.get("receipt_hash") != _receipt_hash(payload):
        raise ValueError("f3_signature_envelope_receipt_hash_mismatch")
    evidence = payload.get("evidence_payload")
    if not isinstance(evidence, dict):
        raise ValueError("f3_signature_evidence_payload_invalid")
    aggregate_source_commit = evidence.get("aggregate_source_commit_sha")
    if not _is_commit_sha(aggregate_source_commit):
        raise ValueError("f3_signature_aggregate_source_invalid")
    expected = stage_evidence_payload(
        str(evidence.get("stage")),
        root=root,
        aggregate_source_commit_sha=aggregate_source_commit,
    )
    attestation = evidence.get("signer_attestation")
    if not isinstance(attestation, dict):
        raise ValueError("f3_signature_attestation_missing")
    _require_exact_keys(
        attestation,
        {
            "organization_id",
            "signer_id",
            "independent_from_repository_operator",
            "independence_authority_receipt_sha256",
        },
        label="signature_attestation",
    )
    if not attestation.get("organization_id") or not attestation.get("signer_id"):
        raise ValueError("f3_signature_attestation_identity_missing")
    if attestation.get("independent_from_repository_operator") is not True:
        raise ValueError("f3_signature_independence_not_attested")
    authority_receipt = attestation.get("independence_authority_receipt_sha256")
    if authority_receipt is not None and not _is_sha256(authority_receipt):
        raise ValueError("f3_signature_independence_authority_hash_invalid")
    if {**expected, "signer_attestation": attestation} != evidence:
        raise ValueError("f3_signature_stage_evidence_replay_mismatch")
    signature = payload.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("f3_signature_block_invalid")
    _require_exact_keys(
        signature,
        {
            "state",
            "algorithm",
            "public_key_spki_base64",
            "public_key_sha256",
            "signature_base64",
            "signed_payload_hash",
        },
        label="signature_block",
    )
    if signature.get("signed_payload_hash") != _sha_bytes(
        envelope_evidence_bytes(payload)
    ):
        raise ValueError("f3_signature_signed_payload_hash_mismatch")
    if signature.get("state") == "verified":
        if signature.get("algorithm") != "Ed25519":
            raise ValueError("f3_signature_algorithm_invalid")
        spki = base64.b64decode(signature["public_key_spki_base64"], validate=True)
        if signature.get("public_key_sha256") != _sha_bytes(spki):
            raise ValueError("f3_signature_public_key_hash_mismatch")
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = serialization.load_der_public_key(spki)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("f3_signature_public_key_not_ed25519")
        key.verify(
            base64.b64decode(signature["signature_base64"], validate=True),
            envelope_evidence_bytes(payload),
        )
    elif signature.get("state") == "unsigned":
        if any(
            signature.get(name) is not None
            for name in (
                "algorithm",
                "public_key_spki_base64",
                "public_key_sha256",
                "signature_base64",
            )
        ):
            raise ValueError("f3_signature_unsigned_fields_invalid")
    else:
        raise ValueError("f3_signature_state_invalid")
    return payload


def classify_envelope_trust(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    trusted_signer_anchors: Sequence[TrustedSignerAnchor] = TRUSTED_SIGNER_ANCHORS,
) -> dict[str, Any]:
    validated = validate_envelope(payload, root=root)
    signature = validated["signature"]
    attestation = validated["evidence_payload"]["signer_attestation"]
    cryptographic_signature_valid = signature["state"] == "verified"
    matching_anchor = next(
        (
            anchor
            for anchor in trusted_signer_anchors
            if anchor.organization_id == attestation["organization_id"]
            and anchor.signer_id == attestation["signer_id"]
            and anchor.public_key_sha256 == signature["public_key_sha256"]
        ),
        None,
    )
    trusted_signer_allowlisted = matching_anchor is not None
    authority_bound = bool(
        matching_anchor is not None
        and _is_sha256(matching_anchor.independence_authority_receipt_sha256)
        and matching_anchor.independence_authority_receipt_sha256
        == attestation["independence_authority_receipt_sha256"]
    )
    independently_trusted = bool(
        cryptographic_signature_valid
        and trusted_signer_allowlisted
        and authority_bound
        and attestation["independent_from_repository_operator"] is True
    )
    return {
        "cryptographic_signature_valid": cryptographic_signature_valid,
        "public_key_sha256": signature["public_key_sha256"],
        "trusted_signer_allowlisted": trusted_signer_allowlisted,
        "independence_authority_bound": authority_bound,
        "independently_trusted": independently_trusted,
    }


def build_status(
    *,
    root: Path = ROOT,
    generated_at: str | None = None,
    aggregate_source_commit_sha: str | None = None,
    _signature_dir_override: Path | None = None,
    _trusted_signer_anchors: Sequence[TrustedSignerAnchor] = TRUSTED_SIGNER_ANCHORS,
) -> dict[str, Any]:
    root = root.resolve()
    aggregate_source = _aggregate_source_binding(
        root=root, source_commit_sha=aggregate_source_commit_sha
    )
    rows: list[dict[str, Any]] = []
    for stage in F3_STAGE_ORDER:
        evidence = stage_evidence_payload(
            stage,
            root=root,
            _aggregate_source=aggregate_source,
        )
        envelope_path = DEFAULT_SIGNATURE_DIR / f"{stage}.json"
        target = (
            _signature_dir_override / f"{stage}.json"
            if _signature_dir_override is not None
            else _repository_target(root, envelope_path)
        )
        crypto_valid = False
        signer_allowlisted = False
        authority_bound = False
        trusted = False
        envelope_source_matches = False
        envelope_hash: str | None = None
        organization_id: str | None = None
        signer_id: str | None = None
        public_key_sha256: str | None = None
        authority_receipt_sha256: str | None = None
        if target.is_file():
            envelope = validate_envelope(_read(target), root=root)
            if envelope["evidence_payload"]["stage"] != stage:
                raise ValueError("f3_signature_envelope_stage_mismatch")
            trust = classify_envelope_trust(
                envelope,
                root=root,
                trusted_signer_anchors=_trusted_signer_anchors,
            )
            envelope_source_matches = (
                envelope["evidence_payload"]["aggregate_source_commit_sha"]
                == aggregate_source["source_commit_sha"]
                and envelope["evidence_payload"]["aggregate_source_tree_oid"]
                == aggregate_source["source_tree_oid"]
            )
            crypto_valid = trust["cryptographic_signature_valid"]
            signer_allowlisted = trust["trusted_signer_allowlisted"]
            authority_bound = trust["independence_authority_bound"]
            trusted = bool(
                trust["independently_trusted"]
                and envelope_source_matches
                and evidence["current_source_binding_pass"]
            )
            envelope_hash = envelope["receipt_hash"]
            attestation = envelope["evidence_payload"]["signer_attestation"]
            organization_id = attestation["organization_id"]
            signer_id = attestation["signer_id"]
            public_key_sha256 = trust["public_key_sha256"]
            authority_receipt_sha256 = attestation[
                "independence_authority_receipt_sha256"
            ]
        rows.append(
            {
                "stage": stage,
                "stage_index": evidence["stage_index"],
                "stage_source_commit_sha": evidence["source_commit_sha"],
                "stage_source_tree_oid": evidence["source_tree_oid"],
                "stage_receipt_path": evidence["stage_receipt_path"],
                "stage_receipt_sha256": evidence["stage_receipt_sha256"],
                "aggregate_tree_stage_receipt_sha256": evidence[
                    "aggregate_tree_stage_receipt_sha256"
                ],
                "external_vv_artifact_sha256": evidence["external_vv_artifact_sha256"],
                "recorded_signature_status": evidence["recorded_signature_status"],
                "signature_envelope_path": envelope_path.as_posix(),
                "signature_envelope_receipt_hash": envelope_hash,
                "organization_id": organization_id,
                "signer_id": signer_id,
                "public_key_sha256": public_key_sha256,
                "independence_authority_receipt_sha256": (authority_receipt_sha256),
                "cryptographic_signature_valid": crypto_valid,
                "trusted_signer_allowlisted": signer_allowlisted,
                "independence_authority_bound": authority_bound,
                "signature_source_matches_aggregate": envelope_source_matches,
                "stage_source_is_ancestor": evidence[
                    "source_commit_is_ancestor_of_aggregate"
                ],
                "canonical_stage_receipt_bound": evidence[
                    "canonical_stage_receipt_bound"
                ],
                "recorded_source_inputs_match": evidence["source_input_binding"][
                    "recorded_source_inputs_match"
                ],
                "aggregate_source_inputs_match": evidence["source_input_binding"][
                    "aggregate_source_inputs_match"
                ],
                "recorded_source_mismatch_paths": evidence["source_input_binding"][
                    "recorded_source_mismatch_paths"
                ],
                "aggregate_source_mismatch_paths": evidence["source_input_binding"][
                    "aggregate_source_mismatch_paths"
                ],
                "predecessor_binding_pass": evidence["predecessor_binding"][
                    "binding_pass"
                ],
                "predecessor_semantic_hash_recomputed": evidence["predecessor_binding"][
                    "semantic_replay_hash_recomputed"
                ],
                "predecessor_semantic_hash_matches": evidence["predecessor_binding"][
                    "semantic_replay_hash_matches"
                ],
                "current_source_binding_pass": evidence["current_source_binding_pass"],
                "independent_signature_verified": trusted,
            }
        )
    crypto_count = sum(int(row["cryptographic_signature_valid"]) for row in rows)
    signed = sum(int(row["independent_signature_verified"]) for row in rows)
    current_bound = sum(int(row["current_source_binding_pass"]) for row in rows)
    blockers: list[str] = []
    if not aggregate_source["exact_source_binding"]:
        blockers.append("aggregate_source_builder_schema_not_commit_bound")
    for row in rows:
        stage = row["stage"]
        if not row["current_source_binding_pass"]:
            blockers.append(f"current_source_binding_incomplete:{stage}")
        if row["predecessor_semantic_hash_recomputed"] is False:
            blockers.append(f"predecessor_semantic_hash_unverified:{stage}")
        elif row["predecessor_semantic_hash_matches"] is False:
            blockers.append(f"predecessor_semantic_hash_mismatch:{stage}")
        if row["signature_envelope_receipt_hash"] is None:
            blockers.append(f"trusted_independent_signature_missing:{stage}")
        elif not row["cryptographic_signature_valid"]:
            blockers.append(f"cryptographic_signature_not_verified:{stage}")
        elif not row["trusted_signer_allowlisted"]:
            blockers.append(f"trusted_signer_not_allowlisted:{stage}")
        elif not row["independence_authority_bound"]:
            blockers.append(f"independence_authority_not_bound:{stage}")
        elif not row["signature_source_matches_aggregate"]:
            blockers.append(f"signature_source_epoch_mismatch:{stage}")
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "partial",
        "contract_pass": True,
        "aggregate_source": aggregate_source,
        "trusted_signer_policy_anchor_count": len(TRUSTED_SIGNER_ANCHORS),
        "stage_count": len(rows),
        "required_surface_count_per_stage": len(F3_REQUIRED_SURFACES),
        "self_verified_stage_count": len(rows),
        "current_source_bound_stage_count": current_bound,
        "cryptographically_verified_stage_count": crypto_count,
        "independently_signed_stage_count": signed,
        "stage_rows": rows,
        "claims": {
            "ten_stage_nine_surface_self_verification": len(rows) == 10,
            "signature_verification_adapter_available": True,
            "all_canonical_stage_receipts_bound": all(
                row["canonical_stage_receipt_bound"] for row in rows
            ),
            "all_stage_sources_ancestral": all(
                row["stage_source_is_ancestor"] for row in rows
            ),
            "all_stage_inputs_match_recorded_sources": all(
                row["recorded_source_inputs_match"] for row in rows
            ),
            "all_stage_inputs_match_aggregate_source": all(
                row["aggregate_source_inputs_match"] for row in rows
            ),
            "trusted_signer_policy_configured": False,
            "all_independent_external_vv_signatures_verified": False,
            "f3_signed_promotion_closure": False,
        },
        "blockers_remaining": blockers,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return payload


def validate_status(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    _signature_dir_override: Path | None = None,
) -> dict[str, Any]:
    schema = _read(_repository_target(root, SCHEMA))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("f3_signature_status_receipt_hash_mismatch")
    expected = build_status(
        root=root,
        generated_at=payload["generated_at"],
        aggregate_source_commit_sha=payload["aggregate_source"]["source_commit_sha"],
        _signature_dir_override=_signature_dir_override,
    )
    if payload != expected:
        raise ValueError("f3_signature_status_replay_mismatch")
    return payload


def write_status(
    *,
    root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    aggregate_source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_status(
        root=root,
        aggregate_source_commit_sha=aggregate_source_commit_sha,
    )
    target = _repository_target(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate_status(payload, root=root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stage", choices=F3_STAGE_ORDER)
    parser.add_argument("--envelope", type=Path)
    parser.add_argument("--create-envelope", action="store_true")
    parser.add_argument("--organization-id")
    parser.add_argument("--signer-id")
    parser.add_argument("--independent-from-repository-operator", action="store_true")
    parser.add_argument("--independence-authority-receipt-sha256")
    parser.add_argument("--export-evidence", type=Path)
    parser.add_argument("--attach-signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--check-envelope", action="store_true")
    args = parser.parse_args(argv)
    if args.create_envelope:
        if not all((args.stage, args.envelope, args.organization_id, args.signer_id)):
            raise ValueError("f3_create_envelope_arguments_required")
        payload = create_unsigned_envelope(
            stage=args.stage,
            organization_id=args.organization_id,
            signer_id=args.signer_id,
            independent_from_repository_operator=(
                args.independent_from_repository_operator
            ),
            independence_authority_receipt_sha256=(
                args.independence_authority_receipt_sha256
            ),
            aggregate_source_commit_sha=args.source_commit,
        )
        validate_envelope(payload, root=ROOT)
        target = _resolve(ROOT, args.envelope)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"unsigned | stage={args.stage} | envelope={args.envelope}")
        return 0
    if args.export_evidence is not None:
        if args.envelope is None:
            raise ValueError("f3_export_envelope_required")
        payload = validate_envelope(_read(_resolve(ROOT, args.envelope)), root=ROOT)
        target = _resolve(ROOT, args.export_evidence)
        target.write_bytes(envelope_evidence_bytes(payload))
        print(f"exported | stage={payload['evidence_payload']['stage']}")
        return 0
    if args.attach_signature is not None:
        if args.envelope is None or args.public_key is None:
            raise ValueError("f3_attach_signature_arguments_required")
        envelope_target = _resolve(ROOT, args.envelope)
        payload = validate_envelope(_read(envelope_target), root=ROOT)
        signed = attach_signature(
            payload,
            signature_bytes=_resolve(ROOT, args.attach_signature).read_bytes(),
            public_key_pem=_resolve(ROOT, args.public_key).read_bytes(),
        )
        validate_envelope(signed, root=ROOT)
        envelope_target.write_text(
            json.dumps(signed, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"verified | stage={signed['evidence_payload']['stage']}")
        return 0
    if args.check_envelope:
        if args.envelope is None:
            raise ValueError("f3_check_envelope_required")
        payload = validate_envelope(_read(_resolve(ROOT, args.envelope)), root=ROOT)
        trust = classify_envelope_trust(payload, root=ROOT)
        print(
            f"f3_external_vv_signature_envelope_consistent | "
            f"stage={payload['evidence_payload']['stage']} | "
            f"state={payload['signature']['state']} | "
            f"trusted={str(trust['independently_trusted']).lower()}"
        )
        return 0
    if args.check:
        validate_status(_read(_resolve(ROOT, args.out)), root=ROOT)
        print("f3_external_vv_signature_status_consistent")
        return 0
    payload = write_status(
        out=args.out,
        aggregate_source_commit_sha=args.source_commit,
    )
    print(
        f"{payload['status']} | cryptographic="
        f"{payload['cryptographically_verified_stage_count']}/"
        f"{payload['stage_count']} | trusted="
        f"{payload['independently_signed_stage_count']}/{payload['stage_count']} | "
        "f3_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
