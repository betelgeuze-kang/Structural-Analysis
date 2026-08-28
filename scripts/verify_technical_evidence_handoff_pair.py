#!/usr/bin/env python3
"""Verify a source-bound technical handoff/attestation artifact pair.

The caller authenticates GitHub API metadata and performs Sigstore verification.
This verifier has no network access or authority-bearing side effects: it recombines
those normalized identities with the exact downloaded bytes and fails closed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any
import zipfile


PAIR_VERSION = "technical-evidence-handoff-pair.v1"
SEAL_VERSION = "technical-evidence-handoff-seal.v1"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_ARCHIVE_BYTES = 300_000_000
MAX_TOTAL_UNCOMPRESSED_BYTES = 300_000_000
MAX_FILE_BYTES = 100_000_000
MAX_ARCHIVE_ENTRIES = 192
MAX_DSSE_PAYLOAD_BYTES = 16 * 1024 * 1024
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
ATTESTOR_WORKFLOW = ".github/workflows/_technical-evidence-attest.yml"
ATTESTATION_BUNDLE_PATH = "attestation.json"
SIGSTORE_BUNDLE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
IN_TOTO_PAYLOAD_TYPE = "application/vnd.in-toto+json"
IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
SLSA_PROVENANCE_V1 = "https://slsa.dev/provenance/v1"

LANES = {
    "medium": {
        "workflow": ".github/workflows/medium-scale-current-source.yml",
        "subject": "artifacts/medium-scale/current-source/medium-scale-execution.v1.json",
        "version": "medium-scale-current-source-execution.v1",
        "source_key": "source_commit_sha",
    },
    "ifc": {
        "workflow": ".github/workflows/ifc-import-health-current-source.yml",
        "subject": ".ci/ifc-import-health-current-source/technical-receipt.json",
        "version": "ifc-import-health-current-source-technical-receipt.v1",
        "source_key": "source_commit_sha",
    },
    "mgt9": {
        "workflow": ".github/workflows/mgt-import-health-current-source.yml",
        "subject": ".ci/mgt-import-health-current-source/technical-receipt.json",
        "version": "mgt-import-health-current-source-technical-receipt.v1",
        "source_key": "source_commit_sha",
    },
    "mgt10": {
        "workflow": ".github/workflows/mgt-import-health-tenth-source.yml",
        "subject": ".ci/mgt-import-health-tenth-source/technical-receipt.json",
        "version": "mgt-import-health-tenth-source-technical-receipt.v1",
        "source_key": "source_commit_sha",
    },
    "native": {
        "workflow": ".github/workflows/native-frame-alpha-clean-install.yml",
        "subject": "native-clean-install-summary.json",
        "version": "technical-native-clean-install-handoff.v1",
        "source_key": "source_sha",
    },
}


class PairContractError(ValueError):
    """Raised when any identity or byte-level binding is invalid."""


def _fail(reason: str) -> None:
    raise PairContractError(reason)


def _require(condition: object, reason: str) -> None:
    if not condition:
        _fail(reason)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"json_duplicate_key:{key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    _fail(f"json_nonfinite_number:{token}")


def _require_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _fail(f"json_nonfinite_number:{path}")
    if isinstance(value, dict):
        for key, nested in value.items():
            _require_finite(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _require_finite(nested, f"{path}[{index}]")


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PairContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PairContractError(f"{label}_strict_json_invalid") from exc
    _require_finite(value)
    return value


def _strict_object(raw: bytes, label: str) -> dict[str, Any]:
    value = _strict_json(raw, label)
    _require(type(value) is dict, f"{label}_object_required")
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    _require(type(value) is dict, f"{label}_object_required")
    _require(set(value) == expected, f"{label}_keys_invalid")
    return value


def _safe_positive_integer(value: Any, label: str) -> int:
    _require(
        type(value) is int and 1 <= value <= MAX_SAFE_INTEGER,
        f"{label}_safe_positive_integer_required",
    )
    return value


def _safe_path(value: Any, label: str) -> str:
    _require(type(value) is str and 0 < len(value) <= 2048, f"{label}_invalid")
    _require(
        "\\" not in value and "\x00" not in value and ":" not in value,
        f"{label}_encoding_invalid",
    )
    path = PurePosixPath(value)
    _require(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"{label}_unsafe",
    )
    return value


def _symlink_free_file(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise PairContractError(f"{label}_unreadable:{current}") from exc
        _require(not stat.S_ISLNK(metadata.st_mode), f"{label}_symlink_forbidden:{current}")
    _require(absolute.is_file(), f"{label}_regular_file_required")
    return absolute


def _read_file(path: Path, label: str, *, maximum: int = MAX_ARCHIVE_BYTES) -> bytes:
    safe = _symlink_free_file(path, label)
    size = safe.stat().st_size
    _require(0 < size <= maximum, f"{label}_size_invalid")
    raw = safe.read_bytes()
    _require(len(raw) == size, f"{label}_size_changed")
    return raw


def _safe_zip(path: Path, label: str) -> tuple[bytes, dict[str, bytes]]:
    archive = _read_file(path, label)
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    canonical_seen: set[str] = set()
    directory_paths: set[str] = set()
    file_paths: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            infos = zipped.infolist()
            _require(0 < len(infos) <= MAX_ARCHIVE_ENTRIES, f"{label}_entry_count_invalid")
            for info in infos:
                name = info.filename
                _require(name not in seen, f"{label}_duplicate_path:{name}")
                seen.add(name)
                _require("\\" not in name and "\x00" not in name, f"{label}_path_encoding_invalid")
                normalized = name[:-1] if info.is_dir() and name.endswith("/") else name
                safe_name = _safe_path(normalized, f"{label}_path")
                folded_name = safe_name.casefold()
                _require(folded_name not in canonical_seen, f"{label}_canonical_path_collision:{name}")
                canonical_seen.add(folded_name)
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                _require(file_type != stat.S_IFLNK, f"{label}_symlink_forbidden:{name}")
                _require(not (info.flag_bits & 0x1), f"{label}_encrypted_entry:{name}")
                if info.is_dir():
                    _require(file_type in {0, stat.S_IFDIR}, f"{label}_directory_type_invalid:{name}")
                    directory_paths.add(safe_name)
                    continue
                _require(file_type in {0, stat.S_IFREG}, f"{label}_nonregular_entry:{name}")
                _require(
                    info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
                    f"{label}_compression_type_invalid:{name}",
                )
                _require(0 <= info.file_size <= MAX_FILE_BYTES, f"{label}_file_size_invalid:{name}")
                total += info.file_size
                _require(total <= MAX_TOTAL_UNCOMPRESSED_BYTES, f"{label}_expansion_limit_exceeded")
                file_paths.add(safe_name)
            _require(file_paths.isdisjoint(directory_paths), f"{label}_file_directory_collision")
            for name in directory_paths:
                parent = PurePosixPath(name)
                while parent != PurePosixPath("."):
                    _require(parent.as_posix() not in file_paths, f"{label}_path_prefix_conflict:{name}")
                    parent = parent.parent
            for name in file_paths:
                parent = PurePosixPath(name).parent
                while parent != PurePosixPath("."):
                    _require(parent.as_posix() not in file_paths, f"{label}_path_prefix_conflict:{name}")
                    parent = parent.parent
            for info in infos:
                if info.is_dir():
                    continue
                raw = zipped.read(info)
                _require(len(raw) == info.file_size, f"{label}_member_size_changed:{info.filename}")
                files[info.filename] = raw
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise PairContractError(f"{label}_zip_invalid") from exc
    return archive, files


def _sigstore_bundle_statement(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the exact DSSE statement embedded in a v0.3 Sigstore bundle."""

    bundle = _strict_object(raw, "sigstore_bundle")
    _exact_keys(
        bundle,
        {"mediaType", "verificationMaterial", "dsseEnvelope"},
        "sigstore_bundle",
    )
    _require(bundle["mediaType"] == SIGSTORE_BUNDLE_MEDIA_TYPE, "sigstore_bundle_media_type_invalid")
    _require(
        type(bundle["verificationMaterial"]) is dict
        and bool(bundle["verificationMaterial"]),
        "sigstore_bundle_verification_material_invalid",
    )
    envelope = _exact_keys(
        bundle["dsseEnvelope"],
        {"payload", "payloadType", "signatures"},
        "sigstore_dsse_envelope",
    )
    _require(envelope["payloadType"] == IN_TOTO_PAYLOAD_TYPE, "sigstore_dsse_payload_type_invalid")
    payload = envelope["payload"]
    _require(
        type(payload) is str
        and 0 < len(payload) <= ((MAX_DSSE_PAYLOAD_BYTES + 2) // 3) * 4,
        "sigstore_dsse_payload_size_invalid",
    )
    try:
        statement_raw = base64.b64decode(payload.encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error, ValueError) as exc:
        raise PairContractError("sigstore_dsse_payload_base64_invalid") from exc
    _require(
        0 < len(statement_raw) <= MAX_DSSE_PAYLOAD_BYTES,
        "sigstore_dsse_payload_size_invalid",
    )
    signatures = envelope["signatures"]
    _require(type(signatures) is list and len(signatures) == 1, "sigstore_dsse_signatures_invalid")
    signature = signatures[0]
    _require(
        type(signature) is dict
        and set(signature).issubset({"keyid", "sig"})
        and type(signature.get("sig")) is str
        and bool(signature["sig"]),
        "sigstore_dsse_signature_invalid",
    )
    try:
        base64.b64decode(signature["sig"].encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error, ValueError) as exc:
        raise PairContractError("sigstore_dsse_signature_base64_invalid") from exc
    statement = _strict_object(statement_raw, "sigstore_dsse_statement")
    _exact_keys(
        statement,
        {"_type", "subject", "predicateType", "predicate"},
        "sigstore_dsse_statement",
    )
    _require(statement["_type"] == IN_TOTO_STATEMENT_TYPE, "sigstore_statement_type_invalid")
    _require(statement["predicateType"] == SLSA_PROVENANCE_V1, "sigstore_statement_predicate_type_invalid")
    _require(type(statement["predicate"]) is dict, "sigstore_statement_predicate_invalid")
    return bundle, statement


def _validate_pair_shape(pair: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    _exact_keys(
        pair,
        {
            "schema_version", "lane", "github_api", "handoff_artifact",
            "handoff_seal", "technical_subject", "attestation_artifact",
            "sigstore_verification",
        },
        "pair",
    )
    _require(pair["schema_version"] == PAIR_VERSION, "pair_schema_version_invalid")
    lane = pair["lane"]
    _require(type(lane) is str and lane in LANES, "pair_lane_invalid")
    config = LANES[lane]

    api = _exact_keys(
        pair["github_api"],
        {
            "repository", "source_commit_sha", "source_tree_sha", "source_ref",
            "workflow_path", "workflow_blob_sha", "attestor_workflow_path",
            "attestor_workflow_blob_sha", "run_id", "run_attempt",
        },
        "github_api",
    )
    _require(type(api["repository"]) is str and REPOSITORY.fullmatch(api["repository"]), "repository_invalid")
    for key in (
        "source_commit_sha", "source_tree_sha", "workflow_blob_sha",
        "attestor_workflow_blob_sha",
    ):
        _require(type(api[key]) is str and SHA1.fullmatch(api[key]), f"github_api_{key}_invalid")
    _require(api["source_ref"] == "refs/heads/main", "source_ref_invalid")
    _require(api["workflow_path"] == config["workflow"], "workflow_path_lane_mismatch")
    _require(api["attestor_workflow_path"] == ATTESTOR_WORKFLOW, "attestor_workflow_path_invalid")
    run_id = _safe_positive_integer(api["run_id"], "run_id")
    run_attempt = _safe_positive_integer(api["run_attempt"], "run_attempt")

    artifact_identity_keys = {
        "id", "name", "api_digest", "workflow_run_id", "workflow_run_attempt",
        "source_sha",
    }
    handoff = _exact_keys(pair["handoff_artifact"], artifact_identity_keys, "handoff_artifact")
    attestation = _exact_keys(
        pair["attestation_artifact"],
        artifact_identity_keys | {"bundle_path", "bundle_sha256"},
        "attestation_artifact",
    )
    for label, artifact in (("handoff", handoff), ("attestation", attestation)):
        _safe_positive_integer(artifact["id"], f"{label}_artifact_id")
        artifact_run_id = _safe_positive_integer(
            artifact["workflow_run_id"], f"{label}_artifact_run_id"
        )
        artifact_run_attempt = _safe_positive_integer(
            artifact["workflow_run_attempt"], f"{label}_artifact_run_attempt"
        )
        _require(artifact_run_id == run_id, f"{label}_artifact_run_id_mismatch")
        _require(
            artifact_run_attempt == run_attempt,
            f"{label}_artifact_run_attempt_mismatch",
        )
        _require(artifact["source_sha"] == api["source_commit_sha"], f"{label}_artifact_source_mismatch")
        _require(type(artifact["name"]) is str and 0 < len(artifact["name"]) <= 512, f"{label}_artifact_name_invalid")
        _require(type(artifact["api_digest"]) is str and SHA256.fullmatch(artifact["api_digest"]), f"{label}_artifact_digest_invalid")
    expected_name = f"{lane}-technical-handoff-{run_id}-{run_attempt}-{api['source_commit_sha']}"
    _require(handoff["name"] == expected_name, "handoff_artifact_name_invalid")
    _require(attestation["name"] == expected_name + "-attestation", "attestation_artifact_name_invalid")
    _require(handoff["id"] != attestation["id"], "artifact_id_not_unique")
    _require(handoff["name"] != attestation["name"], "artifact_name_not_unique")

    seal = _exact_keys(pair["handoff_seal"], {"path", "sha256"}, "handoff_seal")
    _require(seal["path"] == "handoff-seal.json", "handoff_seal_path_invalid")
    _require(type(seal["sha256"]) is str and SHA256.fullmatch(seal["sha256"]), "handoff_seal_digest_invalid")

    subject = _exact_keys(pair["technical_subject"], {"path", "sha256", "schema_version"}, "technical_subject")
    _require(subject["path"] == config["subject"], "technical_subject_path_lane_mismatch")
    _require(subject["schema_version"] == config["version"], "technical_subject_version_lane_mismatch")
    _require(type(subject["sha256"]) is str and SHA256.fullmatch(subject["sha256"]), "technical_subject_digest_invalid")
    _require(
        attestation["bundle_path"] == ATTESTATION_BUNDLE_PATH,
        "attestation_bundle_path_invalid",
    )
    _require(type(attestation["bundle_sha256"]) is str and SHA256.fullmatch(attestation["bundle_sha256"]), "attestation_bundle_digest_invalid")

    verification = _exact_keys(
        pair["sigstore_verification"],
        {
            "verified", "report_sha256", "bundle_sha256", "subject_name",
            "subject_sha256", "repository", "signer_workflow", "signer_digest",
            "source_digest", "source_ref", "deny_self_hosted_runners",
        },
        "sigstore_verification",
    )
    _require(verification["verified"] is True, "sigstore_not_verified")
    _require(verification["deny_self_hosted_runners"] is True, "sigstore_self_hosted_not_denied")
    for key in ("report_sha256", "bundle_sha256", "subject_sha256"):
        _require(type(verification[key]) is str and SHA256.fullmatch(verification[key]), f"sigstore_{key}_invalid")
    _require(verification["bundle_sha256"] == attestation["bundle_sha256"], "sigstore_bundle_digest_mismatch")
    _require(verification["subject_sha256"] == subject["sha256"], "sigstore_subject_digest_mismatch")
    _require(type(verification["subject_name"]) is str and 0 < len(verification["subject_name"]) <= 1024, "sigstore_subject_name_invalid")
    _require(
        verification["subject_name"] == PurePosixPath(subject["path"]).name,
        "sigstore_subject_name_path_mismatch",
    )
    _require(verification["repository"] == api["repository"], "sigstore_repository_mismatch")
    _require(
        verification["signer_workflow"] == f"{api['repository']}/{ATTESTOR_WORKFLOW}",
        "sigstore_signer_workflow_mismatch",
    )
    _require(verification["signer_digest"] == api["source_commit_sha"], "sigstore_signer_digest_mismatch")
    _require(verification["source_digest"] == api["source_commit_sha"], "sigstore_source_digest_mismatch")
    _require(verification["source_ref"] == api["source_ref"], "sigstore_source_ref_mismatch")
    return api, config


def verify_pair(
    *,
    pair_path: Path,
    handoff_archive_path: Path,
    attestation_archive_path: Path,
    sigstore_report_path: Path,
) -> dict[str, Any]:
    pair_raw = _read_file(pair_path, "pair", maximum=4 * 1024 * 1024)
    pair = _strict_object(pair_raw, "pair")
    api, config = _validate_pair_shape(pair)

    handoff_archive, handoff_files = _safe_zip(handoff_archive_path, "handoff_archive")
    _require(_sha256(handoff_archive) == pair["handoff_artifact"]["api_digest"], "handoff_artifact_api_digest_mismatch")
    seal_path = pair["handoff_seal"]["path"]
    _require(seal_path in handoff_files, "handoff_seal_missing")
    _require(_sha256(handoff_files[seal_path]) == pair["handoff_seal"]["sha256"], "handoff_seal_digest_mismatch")
    strict_documents = {
        name: _strict_object(raw, f"handoff_json:{name}")
        for name, raw in handoff_files.items()
        if name.endswith(".json")
    }
    seal = strict_documents[seal_path]
    _exact_keys(
        seal,
        {
            "artifact_files", "lane", "run_attempt", "run_id", "schema_version",
            "source_sha", "source_workflow_path", "source_workflow_sha",
        },
        "handoff_seal",
    )
    _require(
        seal["schema_version"] == SEAL_VERSION
        and seal["lane"] == pair["lane"]
        and seal["source_sha"] == api["source_commit_sha"]
        and seal["source_workflow_sha"] == api["source_commit_sha"]
        and seal["source_workflow_path"] == api["workflow_path"]
        and seal["run_id"] == api["run_id"]
        and seal["run_attempt"] == api["run_attempt"],
        "handoff_seal_identity_mismatch",
    )
    sealed_files = seal["artifact_files"]
    _require(type(sealed_files) is dict, "handoff_seal_inventory_invalid")
    _require(set(sealed_files) == set(handoff_files) - {seal_path}, "handoff_seal_file_set_mismatch")
    for name, digest in sealed_files.items():
        _safe_path(name, "handoff_seal_member_path")
        _require(type(digest) is str and SHA256.fullmatch(digest), "handoff_seal_member_digest_invalid")
        _require(_sha256(handoff_files[name]) == digest, f"handoff_seal_member_digest_mismatch:{name}")

    subject = pair["technical_subject"]
    subject_path = subject["path"]
    _require(subject_path in handoff_files, "technical_subject_missing")
    _require(_sha256(handoff_files[subject_path]) == subject["sha256"], "technical_subject_digest_mismatch")
    subject_document = strict_documents[subject_path]
    _require(subject_document.get("schema_version") == subject["schema_version"], "technical_subject_schema_version_mismatch")
    _require(subject_document.get(config["source_key"]) == api["source_commit_sha"], "technical_subject_source_mismatch")

    attestation_archive, attestation_files = _safe_zip(attestation_archive_path, "attestation_archive")
    _require(_sha256(attestation_archive) == pair["attestation_artifact"]["api_digest"], "attestation_artifact_api_digest_mismatch")
    bundle_path = pair["attestation_artifact"]["bundle_path"]
    _require(set(attestation_files) == {bundle_path}, "attestation_artifact_file_set_invalid")
    bundle_raw = attestation_files[bundle_path]
    _require(_sha256(bundle_raw) == pair["attestation_artifact"]["bundle_sha256"], "attestation_bundle_digest_mismatch")
    bundle, bundle_statement = _sigstore_bundle_statement(bundle_raw)

    report_raw = _read_file(sigstore_report_path, "sigstore_report", maximum=16 * 1024 * 1024)
    verification = pair["sigstore_verification"]
    _require(_sha256(report_raw) == verification["report_sha256"], "sigstore_report_digest_mismatch")
    report = _strict_json(report_raw, "sigstore_report")
    _require(type(report) is list and len(report) == 1, "sigstore_report_shape_invalid")
    row = report[0]
    _require(type(row) is dict and set(row) == {"attestation", "verificationResult"}, "sigstore_report_row_invalid")
    report_attestation = _exact_keys(
        row["attestation"],
        {"bundle", "bundle_url", "initiator"},
        "sigstore_report_attestation",
    )
    _require(
        report_attestation["bundle"] == bundle
        and report_attestation["bundle_url"] == ""
        and report_attestation["initiator"] == "",
        "sigstore_report_bundle_mismatch",
    )
    result = row["verificationResult"]
    _require(type(result) is dict, "sigstore_verification_result_invalid")
    signature = result.get("signature")
    timestamps = result.get("verifiedTimestamps")
    statement = result.get("statement")
    _require(
        type(signature) is dict
        and type(signature.get("certificate")) is dict
        and bool(signature["certificate"])
        and type(timestamps) is list
        and bool(timestamps)
        and all(type(item) is dict and bool(item) for item in timestamps)
        and type(statement) is dict,
        "sigstore_verification_result_shape_invalid",
    )
    _exact_keys(
        statement,
        {"_type", "subject", "predicateType", "predicate"},
        "sigstore_report_statement",
    )
    _require(statement == bundle_statement, "sigstore_report_statement_mismatch")
    subjects = statement["subject"]
    _require(
        statement["_type"] == IN_TOTO_STATEMENT_TYPE
        and statement["predicateType"] == SLSA_PROVENANCE_V1
        and type(statement["predicate"]) is dict
        and type(subjects) is list
        and len(subjects) == 1
        and type(subjects[0]) is dict,
        "sigstore_statement_shape_invalid",
    )
    signed_subject = subjects[0]
    _require(
        type(signed_subject.get("name")) is str
        and signed_subject["name"] == verification["subject_name"]
        and type(signed_subject.get("digest")) is dict
        and set(signed_subject["digest"]) == {"sha256"}
        and "sha256:" + str(signed_subject["digest"]["sha256"])
        == verification["subject_sha256"],
        "sigstore_statement_subject_mismatch",
    )
    return {
        "schema_version": PAIR_VERSION,
        "lane": pair["lane"],
        "repository": api["repository"],
        "source_commit_sha": api["source_commit_sha"],
        "source_tree_sha": api["source_tree_sha"],
        "workflow_path": api["workflow_path"],
        "workflow_blob_sha": api["workflow_blob_sha"],
        "attestor_workflow_path": api["attestor_workflow_path"],
        "attestor_workflow_blob_sha": api["attestor_workflow_blob_sha"],
        "run_id": api["run_id"],
        "run_attempt": api["run_attempt"],
        "handoff_artifact_id": pair["handoff_artifact"]["id"],
        "handoff_artifact_digest": pair["handoff_artifact"]["api_digest"],
        "attestation_artifact_id": pair["attestation_artifact"]["id"],
        "attestation_artifact_digest": pair["attestation_artifact"]["api_digest"],
        "technical_subject_path": pair["technical_subject"]["path"],
        "subject_sha256": pair["technical_subject"]["sha256"],
        "sigstore_report_sha256": pair["sigstore_verification"]["report_sha256"],
        "valid": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--handoff-archive", type=Path, required=True)
    parser.add_argument("--attestation-archive", type=Path, required=True)
    parser.add_argument("--sigstore-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_pair(
            pair_path=args.pair,
            handoff_archive_path=args.handoff_archive,
            attestation_archive_path=args.attestation_archive,
            sigstore_report_path=args.sigstore_report,
        )
    except PairContractError as exc:
        print(str(exc))
        return 1
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
