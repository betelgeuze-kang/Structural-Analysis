"""Detached Ed25519 proof-of-possession for an external runner key.

This module verifies that one public key controlled the private key needed to
sign an exact enrollment challenge.  It deliberately does not enroll or
activate the key, mutate a trust registry, load a private key, or sign data.
Runner-declared key origin and optional attestation digests remain unverified
metadata in the resulting non-authoritative receipt.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from importlib import resources
import json
import re
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)
from structural_analysis.engine_v2.evidence.ed25519_v1 import (
    ED25519_ALGORITHM_V1,
    Ed25519EvidenceV1Error,
    decode_canonical_base64_v1,
    validate_ed25519_public_key_v1,
    verify_ed25519_signature_v1,
)

from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
)


HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CHALLENGE_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-key-enrollment-challenge.v1"
)
HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-key-enrollment-receipt.v1"
)
HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CAPABILITY_PROFILE_V1 = (
    "phase0_external_gfx1100_detached_key_enrollment_pop"
)
HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PURPOSE_V1 = (
    "hip_fgmres_external_gfx1100_runner_key_proof_of_possession"
)
HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_EVIDENCE_SCOPE_V1 = (
    "detached_ed25519_possession_only_non_authoritative"
)
HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PROOF_DOMAIN_V1 = (
    b"structural-analysis/engine-v2/hip-fgmres/external-key-enrollment-proof/v1\0"
)
HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_ALLOWED_ORIGINS_V1 = (
    "runner_declared_isolated_hsm",
    "runner_declared_hardware_token",
    "runner_declared_software_keystore",
    "runner_declared_unknown",
)

_SCHEMA_RESOURCE = "hip_fgmres_external_key_enrollment_v1.schema.json"
_SCHEMA_RESOURCE_BYTES_SHA256 = (
    "sha256:25efb0862eefbee44f9b88dff48b8ee831ae5ea0d79bcba31a3f6d1b8e7ae614"
)
_ZERO_HASH = "sha256:" + "0" * 64
_ALLOWED_FIXTURE_REGISTRY_BYTES_SHA256 = (
    "sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa"
)
_ALLOWED_FIXTURE_REGISTRY_HASH = (
    "sha256:0f9fb841c2ed6bfe2aef43024d5a496485f06d3d00b95892c7304b7e0dab7eb6"
)
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_REQUEST_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{2,127}")
_RUNNER_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
_KEY_ID_RE = re.compile(r"ed25519:([a-z0-9][a-z0-9._-]{2,63}):v([1-9][0-9]*)")
_MAX_KEY_ID_CHARS = 128
_MAX_KEY_EPOCH = 100_000
_MAX_RUN_SEQUENCE = 9_223_372_036_854_775_807
_UTC_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)


class HipFgmresExternalKeyEnrollmentV1Error(ValueError):
    """Stable fail-closed detached enrollment error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = (message or code)[:240]
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalKeyEnrollmentPredecessorKeyV1:
    """Finite terminal range of the key immediately preceding a rotation."""

    key_id: str
    key_epoch: int
    public_key_sha256: str
    maximum_run_sequence: int

    def to_dict(self) -> dict[str, Any]:
        _validate_predecessor_key(self, runner_id=None, path="/predecessor_key")
        return _predecessor_payload(self)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalKeyEnrollmentChallengeV1:
    """Canonical, self-hashed message description for detached HSM signing."""

    schema_version: str
    capability_profile: str
    purpose: str
    request_id: str
    nonce_base64: str
    runner_id: str
    key_id: str
    key_epoch: int
    predecessor_registry_epoch: int
    predecessor_registry_hash: str
    target_registry_epoch: int
    predecessor_key: HipFgmresExternalKeyEnrollmentPredecessorKeyV1 | None
    public_key_base64: str
    public_key_sha256: str
    allowed_architecture_base: str
    allowed_suite_id: str
    allowed_fixture_registry_bytes_sha256: str
    allowed_fixture_registry_hash: str
    minimum_run_sequence: int
    maximum_run_sequence: int
    valid_from_utc: str
    valid_until_utc: str
    runner_declared_key_origin: str
    attestation_digest_sha256: str | None
    challenge_hash: str

    @property
    def public_key_bytes(self) -> bytes:
        return _decode_base64(
            self.public_key_base64,
            expected_byte_count=32,
            path="/challenge/public_key_base64",
        )

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_key_enrollment_challenge_v1(self)
        return _challenge_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalKeyEnrollmentClaimsV1:
    """Narrow claim projection: only possession is true."""

    private_key_possession_at_enrollment_verified: bool = True
    package_registry_inclusion_verified: bool = False
    key_activation_verified: bool = False
    hsm_origin_verified: bool = False
    hsm_non_exportability_verified: bool = False
    reviewer_identity_verified: bool = False
    hardware_execution_verified: bool = False
    promotion_eligible: bool = False
    commercial_ready: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalKeyEnrollmentReceiptV1:
    """Cryptographically revalidatable detached PoP receipt."""

    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    challenge: HipFgmresExternalKeyEnrollmentChallengeV1
    proof_algorithm: str
    proof_signature_base64: str
    proof_signature_sha256: str
    claims: HipFgmresExternalKeyEnrollmentClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_key_enrollment_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


def compile_hip_fgmres_external_key_enrollment_challenge_v1(
    *,
    nonce: bytes,
    request_id: str,
    runner_id: str,
    key_id: str,
    key_epoch: int,
    predecessor_registry_epoch: int,
    predecessor_registry_hash: str,
    target_registry_epoch: int,
    predecessor_key: HipFgmresExternalKeyEnrollmentPredecessorKeyV1 | None,
    public_key: bytes,
    public_key_sha256: str,
    allowed_architecture_base: str,
    allowed_suite_id: str,
    allowed_fixture_registry_bytes_sha256: str,
    allowed_fixture_registry_hash: str,
    minimum_run_sequence: int,
    maximum_run_sequence: int,
    valid_from_utc: str,
    valid_until_utc: str,
    runner_declared_key_origin: str,
    attestation_digest_sha256: str | None,
) -> HipFgmresExternalKeyEnrollmentChallengeV1:
    """Compile exact public enrollment material; never enroll or sign the key."""

    if type(nonce) is not bytes or len(nonce) != 32:
        _fail("hip_fgmres_external_key_enrollment_nonce_invalid", "/nonce")
    if type(public_key) is not bytes or len(public_key) != 32:
        _fail(
            "hip_fgmres_external_key_enrollment_public_key_invalid",
            "/public_key",
        )
    try:
        validate_ed25519_public_key_v1(public_key)
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_public_key_invalid",
            "/public_key",
            exc.code,
        )
    if public_key_sha256 != sha256_prefixed(public_key):
        _fail(
            "hip_fgmres_external_key_enrollment_public_key_hash_invalid",
            "/public_key_sha256",
        )
    draft = HipFgmresExternalKeyEnrollmentChallengeV1(
        schema_version=(HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CHALLENGE_SCHEMA_VERSION_V1),
        capability_profile=HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CAPABILITY_PROFILE_V1,
        purpose=HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PURPOSE_V1,
        request_id=request_id,
        nonce_base64=base64.b64encode(nonce).decode("ascii"),
        runner_id=runner_id,
        key_id=key_id,
        key_epoch=key_epoch,
        predecessor_registry_epoch=predecessor_registry_epoch,
        predecessor_registry_hash=predecessor_registry_hash,
        target_registry_epoch=target_registry_epoch,
        predecessor_key=predecessor_key,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
        public_key_sha256=public_key_sha256,
        allowed_architecture_base=allowed_architecture_base,
        allowed_suite_id=allowed_suite_id,
        allowed_fixture_registry_bytes_sha256=(allowed_fixture_registry_bytes_sha256),
        allowed_fixture_registry_hash=allowed_fixture_registry_hash,
        minimum_run_sequence=minimum_run_sequence,
        maximum_run_sequence=maximum_run_sequence,
        valid_from_utc=valid_from_utc,
        valid_until_utc=valid_until_utc,
        runner_declared_key_origin=runner_declared_key_origin,
        attestation_digest_sha256=attestation_digest_sha256,
        challenge_hash=_ZERO_HASH,
    )
    if (
        predecessor_key is not None
        and type(predecessor_key) is not HipFgmresExternalKeyEnrollmentPredecessorKeyV1
    ):
        _fail(
            "hip_fgmres_external_key_enrollment_predecessor_key_invalid",
            "/predecessor_key",
        )
    # Validate the bounded wire shape before canonical serialization.  This
    # keeps hostile non-finite or oversized integer inputs on the stable
    # contract error path instead of leaking JSON encoder exceptions.
    _validate_json_schema(
        _challenge_payload(draft, include_hash=True),
        path="/challenge",
    )
    challenge = replace(
        draft,
        challenge_hash=canonical_hash(_challenge_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_key_enrollment_challenge_v1(challenge)


def compile_hip_fgmres_external_key_enrollment_proof_message_v1(
    challenge: HipFgmresExternalKeyEnrollmentChallengeV1,
) -> bytes:
    """Return the exact domain-separated bytes an external HSM must sign."""

    validate_hip_fgmres_external_key_enrollment_challenge_v1(challenge)
    return _proof_message(challenge)


def verify_hip_fgmres_external_key_enrollment_proof_v1(
    challenge: HipFgmresExternalKeyEnrollmentChallengeV1,
    *,
    proof_signature_base64: str,
) -> HipFgmresExternalKeyEnrollmentReceiptV1:
    """Verify detached PoP and return a non-authoritative, self-hashed receipt."""

    validate_hip_fgmres_external_key_enrollment_challenge_v1(challenge)
    signature = _decode_base64(
        proof_signature_base64,
        expected_byte_count=64,
        path="/proof_signature_base64",
    )
    _verify_proof_signature(challenge, proof_signature_base64)
    draft = HipFgmresExternalKeyEnrollmentReceiptV1(
        schema_version=HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_RECEIPT_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CAPABILITY_PROFILE_V1,
        status="detached_runner_key_proof_of_possession_verified",
        evidence_scope=HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_EVIDENCE_SCOPE_V1,
        challenge=challenge,
        proof_algorithm=ED25519_ALGORITHM_V1,
        proof_signature_base64=proof_signature_base64,
        proof_signature_sha256=sha256_prefixed(signature),
        claims=HipFgmresExternalKeyEnrollmentClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_key_enrollment_receipt_v1(receipt)


def validate_hip_fgmres_external_key_enrollment_challenge_v1(
    challenge: HipFgmresExternalKeyEnrollmentChallengeV1,
) -> HipFgmresExternalKeyEnrollmentChallengeV1:
    if type(challenge) is not HipFgmresExternalKeyEnrollmentChallengeV1:
        _fail("hip_fgmres_external_key_enrollment_challenge_type_invalid", "/")
    if (
        challenge.predecessor_key is not None
        and type(challenge.predecessor_key)
        is not HipFgmresExternalKeyEnrollmentPredecessorKeyV1
    ):
        _fail(
            "hip_fgmres_external_key_enrollment_predecessor_key_invalid",
            "/predecessor_key",
        )
    payload = _challenge_payload(challenge, include_hash=True)
    _validate_json_schema(payload, path="/challenge")
    public_key = challenge.public_key_bytes
    try:
        validate_ed25519_public_key_v1(public_key)
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_public_key_invalid",
            "/challenge/public_key_base64",
            exc.code,
        )
    valid_from = _parse_utc(challenge.valid_from_utc, "/valid_from_utc")
    valid_until = _parse_utc(challenge.valid_until_utc, "/valid_until_utc")
    integer_values = (
        challenge.key_epoch,
        challenge.predecessor_registry_epoch,
        challenge.target_registry_epoch,
        challenge.minimum_run_sequence,
        challenge.maximum_run_sequence,
    )
    if (
        challenge.schema_version
        != HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CHALLENGE_SCHEMA_VERSION_V1
        or challenge.capability_profile
        != HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CAPABILITY_PROFILE_V1
        or challenge.purpose != HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PURPOSE_V1
        or type(challenge.request_id) is not str
        or _REQUEST_ID_RE.fullmatch(challenge.request_id) is None
        or type(challenge.runner_id) is not str
        or _RUNNER_ID_RE.fullmatch(challenge.runner_id) is None
        or any(type(value) is not int or value <= 0 for value in integer_values)
        or challenge.key_id != f"ed25519:{challenge.runner_id}:v{challenge.key_epoch}"
        or challenge.target_registry_epoch != challenge.predecessor_registry_epoch + 1
        or _HASH_RE.fullmatch(challenge.predecessor_registry_hash) is None
        or sha256_prefixed(public_key) != challenge.public_key_sha256
        or challenge.allowed_architecture_base != "gfx1100"
        or challenge.allowed_suite_id != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or challenge.allowed_fixture_registry_bytes_sha256
        != _ALLOWED_FIXTURE_REGISTRY_BYTES_SHA256
        or challenge.allowed_fixture_registry_hash != _ALLOWED_FIXTURE_REGISTRY_HASH
        or challenge.maximum_run_sequence < challenge.minimum_run_sequence
        or valid_until <= valid_from
        or challenge.runner_declared_key_origin
        not in HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_ALLOWED_ORIGINS_V1
        or (
            challenge.attestation_digest_sha256 is not None
            and (
                type(challenge.attestation_digest_sha256) is not str
                or _HASH_RE.fullmatch(challenge.attestation_digest_sha256) is None
            )
        )
    ):
        _fail(
            "hip_fgmres_external_key_enrollment_challenge_semantics_invalid",
            "/challenge",
        )
    _decode_base64(
        challenge.nonce_base64,
        expected_byte_count=32,
        path="/nonce_base64",
    )
    predecessor = challenge.predecessor_key
    if predecessor is None:
        if challenge.key_epoch != 1 or challenge.minimum_run_sequence != 1:
            _fail(
                "hip_fgmres_external_key_enrollment_predecessor_key_invalid",
                "/predecessor_key",
            )
    else:
        _validate_predecessor_key(
            predecessor,
            runner_id=challenge.runner_id,
            path="/predecessor_key",
        )
        if (
            challenge.key_epoch != predecessor.key_epoch + 1
            or challenge.minimum_run_sequence != predecessor.maximum_run_sequence + 1
            or challenge.public_key_sha256 == predecessor.public_key_sha256
        ):
            _fail(
                "hip_fgmres_external_key_enrollment_predecessor_key_invalid",
                "/predecessor_key",
            )
    expected_hash = canonical_hash(_challenge_payload(challenge, include_hash=False))
    if challenge.challenge_hash != expected_hash:
        _fail(
            "hip_fgmres_external_key_enrollment_challenge_hash_invalid",
            "/challenge_hash",
        )
    return challenge


def validate_hip_fgmres_external_key_enrollment_receipt_v1(
    receipt: HipFgmresExternalKeyEnrollmentReceiptV1,
) -> HipFgmresExternalKeyEnrollmentReceiptV1:
    if (
        type(receipt) is not HipFgmresExternalKeyEnrollmentReceiptV1
        or type(receipt.challenge) is not HipFgmresExternalKeyEnrollmentChallengeV1
        or type(receipt.claims) is not HipFgmresExternalKeyEnrollmentClaimsV1
    ):
        _fail("hip_fgmres_external_key_enrollment_receipt_type_invalid", "/")
    validate_hip_fgmres_external_key_enrollment_challenge_v1(receipt.challenge)
    payload = _receipt_payload(receipt, include_hash=True)
    _validate_json_schema(payload, path="/receipt")
    signature = _decode_base64(
        receipt.proof_signature_base64,
        expected_byte_count=64,
        path="/proof_signature_base64",
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_RECEIPT_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CAPABILITY_PROFILE_V1
        or receipt.status != "detached_runner_key_proof_of_possession_verified"
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_EVIDENCE_SCOPE_V1
        or receipt.proof_algorithm != ED25519_ALGORITHM_V1
        or receipt.proof_signature_sha256 != sha256_prefixed(signature)
        or receipt.claims != HipFgmresExternalKeyEnrollmentClaimsV1()
        or receipt.receipt_hash
        != canonical_hash(_receipt_payload(receipt, include_hash=False))
    ):
        _fail(
            "hip_fgmres_external_key_enrollment_receipt_semantics_invalid",
            "/receipt",
        )
    _verify_proof_signature(receipt.challenge, receipt.proof_signature_base64)
    return receipt


def _validate_predecessor_key(
    predecessor: HipFgmresExternalKeyEnrollmentPredecessorKeyV1,
    *,
    runner_id: str | None,
    path: str,
) -> None:
    key_id_is_bounded = (
        type(predecessor) is HipFgmresExternalKeyEnrollmentPredecessorKeyV1
        and type(predecessor.key_id) is str
        and len(predecessor.key_id) <= _MAX_KEY_ID_CHARS
    )
    key_match = (
        None if not key_id_is_bounded else _KEY_ID_RE.fullmatch(predecessor.key_id)
    )
    if (
        type(predecessor) is not HipFgmresExternalKeyEnrollmentPredecessorKeyV1
        or type(predecessor.key_id) is not str
        or not key_id_is_bounded
        or key_match is None
        or type(predecessor.key_epoch) is not int
        or not 1 <= predecessor.key_epoch <= _MAX_KEY_EPOCH
        or key_match.group(2) != str(predecessor.key_epoch)
        or type(predecessor.maximum_run_sequence) is not int
        or not 1 <= predecessor.maximum_run_sequence <= _MAX_RUN_SEQUENCE
        or type(predecessor.public_key_sha256) is not str
        or _HASH_RE.fullmatch(predecessor.public_key_sha256) is None
        or (runner_id is not None and key_match.group(1) != runner_id)
    ):
        _fail("hip_fgmres_external_key_enrollment_predecessor_key_invalid", path)


def _verify_proof_signature(
    challenge: HipFgmresExternalKeyEnrollmentChallengeV1,
    signature_base64: str,
) -> None:
    try:
        verify_ed25519_signature_v1(
            public_key=challenge.public_key_bytes,
            signature_base64=signature_base64,
            message=_proof_message(challenge),
        )
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_proof_signature_invalid",
            "/proof_signature_base64",
            exc.code,
        )


def _proof_message(challenge: HipFgmresExternalKeyEnrollmentChallengeV1) -> bytes:
    return HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PROOF_DOMAIN_V1 + canonical_json_bytes(
        _challenge_payload(challenge, include_hash=True)
    )


def _challenge_payload(
    challenge: HipFgmresExternalKeyEnrollmentChallengeV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": challenge.schema_version,
        "capability_profile": challenge.capability_profile,
        "purpose": challenge.purpose,
        "request_id": challenge.request_id,
        "nonce_base64": challenge.nonce_base64,
        "runner_id": challenge.runner_id,
        "key_id": challenge.key_id,
        "key_epoch": challenge.key_epoch,
        "predecessor_registry_epoch": challenge.predecessor_registry_epoch,
        "predecessor_registry_hash": challenge.predecessor_registry_hash,
        "target_registry_epoch": challenge.target_registry_epoch,
        "predecessor_key": (
            None
            if challenge.predecessor_key is None
            else _predecessor_payload(challenge.predecessor_key)
        ),
        "public_key_base64": challenge.public_key_base64,
        "public_key_sha256": challenge.public_key_sha256,
        "allowed_architecture_base": challenge.allowed_architecture_base,
        "allowed_suite_id": challenge.allowed_suite_id,
        "allowed_fixture_registry_bytes_sha256": (
            challenge.allowed_fixture_registry_bytes_sha256
        ),
        "allowed_fixture_registry_hash": challenge.allowed_fixture_registry_hash,
        "minimum_run_sequence": challenge.minimum_run_sequence,
        "maximum_run_sequence": challenge.maximum_run_sequence,
        "valid_from_utc": challenge.valid_from_utc,
        "valid_until_utc": challenge.valid_until_utc,
        "runner_declared_key_origin": challenge.runner_declared_key_origin,
        "attestation_digest_sha256": challenge.attestation_digest_sha256,
    }
    if include_hash:
        payload["challenge_hash"] = challenge.challenge_hash
    return payload


def _predecessor_payload(
    predecessor: HipFgmresExternalKeyEnrollmentPredecessorKeyV1,
) -> dict[str, Any]:
    return {
        "key_id": predecessor.key_id,
        "key_epoch": predecessor.key_epoch,
        "public_key_sha256": predecessor.public_key_sha256,
        "maximum_run_sequence": predecessor.maximum_run_sequence,
    }


def _receipt_payload(
    receipt: HipFgmresExternalKeyEnrollmentReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "challenge": _challenge_payload(receipt.challenge, include_hash=True),
        "proof_algorithm": receipt.proof_algorithm,
        "proof_signature_base64": receipt.proof_signature_base64,
        "proof_signature_sha256": receipt.proof_signature_sha256,
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _parse_utc(value: str, path: str) -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        _fail("hip_fgmres_external_key_enrollment_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_timestamp_invalid",
            path,
            type(exc).__name__,
        )
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("hip_fgmres_external_key_enrollment_timestamp_invalid", path)
    return parsed


def _decode_base64(value: str, *, expected_byte_count: int, path: str) -> bytes:
    expected_encoded_length = 4 * ((expected_byte_count + 2) // 3)
    if type(value) is not str or len(value) != expected_encoded_length:
        _fail(
            "hip_fgmres_external_key_enrollment_base64_invalid",
            path,
            "encoded length rejected",
        )
    try:
        return decode_canonical_base64_v1(
            value,
            expected_byte_count=expected_byte_count,
            path=path,
        )
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_base64_invalid",
            path,
            exc.code,
        )


def _validate_json_schema(payload: dict[str, Any], *, path: str) -> None:
    try:
        raw = (
            resources.files("structural_analysis.schemas")
            .joinpath(_SCHEMA_RESOURCE)
            .read_bytes()
        )
    except OSError as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_schema_read_failed",
            "/schema",
            type(exc).__name__,
        )
    if sha256_prefixed(raw) != _SCHEMA_RESOURCE_BYTES_SHA256:
        _fail(
            "hip_fgmres_external_key_enrollment_schema_hash_mismatch",
            "/schema",
        )
    try:
        schema = json.loads(raw.decode("utf-8", errors="strict"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        _fail(
            "hip_fgmres_external_key_enrollment_schema_invalid",
            "/schema",
            type(exc).__name__,
        )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        keyword = str(error.validator)[:64]
        _fail(
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
            location if location != "/" else path,
            f"schema keyword {keyword} rejected value",
        )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalKeyEnrollmentV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_ALLOWED_ORIGINS_V1",
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_CHALLENGE_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PROOF_DOMAIN_V1",
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PURPOSE_V1",
    "HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_RECEIPT_SCHEMA_VERSION_V1",
    "HipFgmresExternalKeyEnrollmentChallengeV1",
    "HipFgmresExternalKeyEnrollmentClaimsV1",
    "HipFgmresExternalKeyEnrollmentPredecessorKeyV1",
    "HipFgmresExternalKeyEnrollmentReceiptV1",
    "HipFgmresExternalKeyEnrollmentV1Error",
    "compile_hip_fgmres_external_key_enrollment_challenge_v1",
    "compile_hip_fgmres_external_key_enrollment_proof_message_v1",
    "validate_hip_fgmres_external_key_enrollment_challenge_v1",
    "validate_hip_fgmres_external_key_enrollment_receipt_v1",
    "verify_hip_fgmres_external_key_enrollment_proof_v1",
]
