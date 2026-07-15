"""Bind external FGMRES evidence to a freshly replayed release receipt.

Version 2 is an additive, domain-separated envelope.  Unlike v1, both the
verifier challenge and the signed payload carry the exact schema version and
hash of the independently replayed release-identity receipt.  The public API
accepts only the mint-guarded ``HipFgmresExternalVerifiedReleaseV1`` authority;
callers cannot supply either the release binding or identity hash directly.

This remains a non-promoting verifier contract.  It does not add a package
trust key, observe an external GPU, provide a durable ledger, or attest runner
honesty, hardware roots, performance, or commercial readiness.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib import resources
import json
import math
import re
import secrets
from threading import Lock
from typing import Any, Callable, Literal, NoReturn

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
    verify_ed25519_signature_v1,
)

from . import fgmres_external_release_identity_v1 as release_identity_v1
from . import fgmres_external_signed_evidence_v1 as signed_evidence_v1
from .fgmres_external_signed_evidence_v1 import HipFgmresExternalReleaseBindingV1
from .fgmres_external_trust_anchor_registry_v1 import (
    HipFgmresExternalTrustAnchorRegistryResultV1,
    HipFgmresExternalTrustAnchorV1,
)
from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresFixtureRegistryResultV1,
)


HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-external-signed-evidence.v2"
)
HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-external-signed-payload.v2"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-external-signed-evidence-receipt.v2"
)
HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-external-challenge.v2"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2 = (
    "phase0_external_gfx1100_release_identity_ed25519_verification"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCOPE_V2 = (
    "trusted_runner_signed_release_identity_serialized_lane_non_promoting"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V2 = (
    "trusted_runner_signed_release_identity_hash_raw_numerics_replayed_non_promoting"
)

_PURPOSE_V2 = "hip_fgmres_external_gfx1100_release_identity_attestation"
_AUDIENCE_V2 = "structural-analysis-engine-v2-verifier"
_ENVELOPE_SCHEMA_RESOURCE_V2 = "hip_fgmres_external_signed_evidence_v2.schema.json"
_RECEIPT_SCHEMA_RESOURCE_V2 = (
    "hip_fgmres_external_signed_evidence_receipt_v2.schema.json"
)
_ENVELOPE_MAX_BYTES_V2 = 4 * 1024 * 1024
_ENVELOPE_MAX_JSON_NODES_V2 = 200_000
_ENVELOPE_MAX_JSON_DEPTH_V2 = 64
_ENVELOPE_MAX_ERROR_PATH_CHARS_V2 = 512
_SIGNATURE_DOMAIN_V2 = (
    b"structural-analysis\0hip-fgmres-external-gfx1100-evidence\0v2\0"
)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_KEY_ID_RE = re.compile(r"^ed25519:[a-z0-9][a-z0-9._-]{2,63}:v[1-9][0-9]*$")
_RUNNER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
_ZERO_HASH = "sha256:" + "0" * 64
_CHALLENGE_MINT_V2 = object()
_VERIFIED_SIGNED_EVIDENCE_MINT_V2 = object()


class HipFgmresExternalSignedEvidenceV2Error(RuntimeError):
    """Stable fail-closed v2 signed-evidence error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path if type(path) is str and path.startswith("/") else "/"
        self.message = (message or code)[:240]
        super().__init__(f"{self.code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class _EnvelopeJsonPathV2:
    parent: _EnvelopeJsonPathV2 | None
    segment: str


@dataclass(frozen=True, slots=True)
class _ChallengePayloadV2:
    schema_version: str
    challenge_id: str
    request_id: str
    audience: str
    campaign_id: str
    nonce_base64: str
    issued_at_utc: str
    expires_at_utc: str
    expected_key_id: str
    expected_key_epoch: int
    expected_runner_id: str
    expected_run_sequence: int
    expected_release_binding_hash: str
    expected_release_identity_receipt_schema_version: str
    expected_release_identity_receipt_hash: str
    expected_trust_registry_hash: str
    expected_architecture_base: str
    expected_suite_id: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class HipFgmresExternalChallengeV2:
    """Verifier-owned, process-local, single-use v2 challenge authority."""

    __slots__ = ("_payload", "_lock", "_state", "_reservation")

    def __init__(self, payload: _ChallengePayloadV2, *, mint: object) -> None:
        if mint is not _CHALLENGE_MINT_V2 or type(payload) is not _ChallengePayloadV2:
            _fail(
                "hip_fgmres_external_v2_challenge_construction_forbidden", "/challenge"
            )
        self._payload = payload
        self._lock = Lock()
        self._state = "fresh"
        self._reservation: object | None = None

    @property
    def challenge_id(self) -> str:
        return self._payload.challenge_id

    @property
    def consumed(self) -> bool:
        with self._lock:
            return self._state == "consumed"

    def to_dict(self) -> dict[str, Any]:
        return self._payload.to_dict()

    def _reserve(self) -> object:
        with self._lock:
            if self._state != "fresh":
                _fail("hip_fgmres_external_v2_challenge_replayed", "/challenge")
            token = object()
            self._state = "reserved"
            self._reservation = token
            return token

    def _release(self, token: object) -> None:
        with self._lock:
            if self._state == "reserved" and self._reservation is token:
                self._state = "fresh"
                self._reservation = None

    def _consume(self, token: object) -> None:
        with self._lock:
            if self._state != "reserved" or self._reservation is not token:
                _fail(
                    "hip_fgmres_external_v2_challenge_reservation_lost",
                    "/challenge",
                )
            self._state = "consumed"
            self._reservation = None


@dataclass(frozen=True, slots=True)
class HipFgmresExternalSignedEvidenceClaimsV2:
    canonical_envelope_verified: Literal[True] = True
    package_trust_anchor_matched: Literal[True] = True
    ed25519_signature_verified: Literal[True] = True
    verifier_challenge_single_use_reserved: Literal[True] = True
    release_artifacts_freshly_replayed: Literal[True] = True
    expected_release_binding_matched: Literal[True] = True
    release_identity_receipt_schema_matched: Literal[True] = True
    release_identity_receipt_hash_matched: Literal[True] = True
    signed_envelope_binds_release_identity_receipt: Literal[True] = True
    current_schema_manifest_matched: Literal[True] = True
    current_fixture_registry_bound: Literal[True] = True
    external_gfx1100_fixed_suite_signed: Literal[True] = True
    raw_completion_payload_integrity_verified: Literal[True] = True
    raw_numerical_parity_replayed: Literal[True] = True
    solve_record_semantics_replayed: Literal[True] = True
    durable_replay_ledger_verified: Literal[False] = False
    local_gfx1030_signed: Literal[False] = False
    external_evidence_counted_in_family_v2: Literal[False] = False
    same_artifact_two_architecture_verified: Literal[False] = False
    external_hardware_independently_observed_by_local_process: Literal[False] = False
    hardware_root_attested: Literal[False] = False
    runner_honesty_verified: Literal[False] = False
    full_model_family_parity_verified: Literal[False] = False
    multiarchitecture_promotion_verified: Literal[False] = False
    result_ir_verified: Literal[False] = False
    iteration_host_copy_zero_verified: Literal[False] = False
    speedup_verified: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalSignedEvidenceReceiptV2:
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    envelope_hash: str
    signed_payload_sha256: str
    key_id: str
    key_epoch: int
    runner_id: str
    run_sequence: int
    challenge_id: str
    release_binding_hash: str
    release_identity_receipt_schema_version: str
    release_identity_receipt_hash: str
    trust_registry_hash: str
    fixture_registry_hash: str
    family_receipt_hash: str
    common_runtime_binding_hash: str
    ordered_case_aggregate_hash: str
    verified_slot_count: int
    verified_slot_ids: tuple[str, ...]
    claims: HipFgmresExternalSignedEvidenceClaimsV2
    promotion_eligible: bool
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_signed_evidence_receipt_v2(self)
        return _verification_receipt_payload_v2(self, include_hash=True)


class HipFgmresExternalVerifiedSignedEvidenceV2:
    """Process-local authority for a freshly replayed, verified v2 envelope."""

    __slots__ = ("_identity_receipt", "_signed_receipt", "_mint")

    def __init__(
        self,
        *,
        identity_receipt: release_identity_v1.HipFgmresExternalReleaseIdentityReceiptV1,
        signed_receipt: HipFgmresExternalSignedEvidenceReceiptV2,
        mint: object,
    ) -> None:
        if mint is not _VERIFIED_SIGNED_EVIDENCE_MINT_V2:
            _fail(
                "hip_fgmres_external_v2_verified_signed_evidence_construction_forbidden",
                "/result",
            )
        release_identity_v1.validate_hip_fgmres_external_release_identity_receipt_v1(
            identity_receipt
        )
        validate_hip_fgmres_external_signed_evidence_receipt_v2(signed_receipt)
        if (
            signed_receipt.release_binding_hash != identity_receipt.release_binding_hash
            or signed_receipt.release_identity_receipt_schema_version
            != identity_receipt.schema_version
            or signed_receipt.release_identity_receipt_hash
            != identity_receipt.receipt_hash
        ):
            _fail(
                "hip_fgmres_external_v2_verified_signed_evidence_binding_mismatch",
                "/result",
            )
        self._identity_receipt = identity_receipt
        self._signed_receipt = signed_receipt
        self._mint = mint

    @property
    def identity_receipt(
        self,
    ) -> release_identity_v1.HipFgmresExternalReleaseIdentityReceiptV1:
        return self._identity_receipt

    @property
    def signed_receipt(self) -> HipFgmresExternalSignedEvidenceReceiptV2:
        return self._signed_receipt


class _DuplicateKeyError(ValueError):
    pass


def issue_hip_fgmres_external_evidence_challenge_for_verified_release_v2(
    *,
    verified_release: release_identity_v1.HipFgmresExternalVerifiedReleaseV1,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    request_id: str,
    campaign_id: str,
    ttl_seconds: int = 900,
) -> HipFgmresExternalChallengeV2:
    """Freshly replay a mint-guarded release and issue a v2 challenge."""

    registry = signed_evidence_v1._TRUST_REGISTRY_LOADER_AUTHORITY()
    return _issue_challenge_with_registry_v2(
        verified_release=verified_release,
        key_id=key_id,
        runner_id=runner_id,
        run_sequence=run_sequence,
        request_id=request_id,
        campaign_id=campaign_id,
        ttl_seconds=ttl_seconds,
        registry=registry,
    )


def verify_hip_fgmres_external_signed_evidence_for_verified_release_v2(
    envelope_bytes: bytes,
    *,
    challenge: HipFgmresExternalChallengeV2,
    verified_release: release_identity_v1.HipFgmresExternalVerifiedReleaseV1,
) -> HipFgmresExternalVerifiedSignedEvidenceV2:
    """Return process-local authority after final replay and challenge consumption."""

    trust_registry = signed_evidence_v1._TRUST_REGISTRY_LOADER_AUTHORITY()
    fixture_registry = signed_evidence_v1._FIXTURE_REGISTRY_LOADER_AUTHORITY()
    signed_receipt = _verify_with_authorities_v2(
        envelope_bytes,
        challenge=challenge,
        verified_release=verified_release,
        trust_registry=trust_registry,
        fixture_registry=fixture_registry,
    )
    return HipFgmresExternalVerifiedSignedEvidenceV2(
        identity_receipt=verified_release.identity_receipt,
        signed_receipt=signed_receipt,
        mint=_VERIFIED_SIGNED_EVIDENCE_MINT_V2,
    )


def validate_hip_fgmres_external_signed_evidence_receipt_v2(
    receipt: HipFgmresExternalSignedEvidenceReceiptV2,
) -> HipFgmresExternalSignedEvidenceReceiptV2:
    """Validate detached structure only; this does not mint verification authority."""

    if (
        type(receipt) is not HipFgmresExternalSignedEvidenceReceiptV2
        or type(receipt.verified_slot_ids) is not tuple
        or type(receipt.claims) is not HipFgmresExternalSignedEvidenceClaimsV2
    ):
        _fail("hip_fgmres_external_v2_signed_receipt_type_invalid", "/")
    payload = _verification_receipt_payload_v2(receipt, include_hash=True)
    _validate_json_schema_v2(payload, _RECEIPT_SCHEMA_RESOURCE_V2, path="/receipt")
    hashes = (
        receipt.envelope_hash,
        receipt.signed_payload_sha256,
        receipt.challenge_id,
        receipt.release_binding_hash,
        receipt.release_identity_receipt_hash,
        receipt.trust_registry_hash,
        receipt.fixture_registry_hash,
        receipt.family_receipt_hash,
        receipt.common_runtime_binding_hash,
        receipt.ordered_case_aggregate_hash,
        receipt.receipt_hash,
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V2
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2
        or receipt.status
        != "external_gfx1100_release_identity_signed_evidence_verified"
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V2
        or receipt.release_identity_receipt_schema_version
        != release_identity_v1.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        or any(_HASH_RE.fullmatch(value) is None for value in hashes)
        or _RUNNER_ID_RE.fullmatch(receipt.runner_id) is None
        or receipt.key_id != f"ed25519:{receipt.runner_id}:v{receipt.key_epoch}"
        or receipt.verified_slot_ids != HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        or receipt.verified_slot_count != len(receipt.verified_slot_ids)
        or receipt.claims != HipFgmresExternalSignedEvidenceClaimsV2()
        or receipt.promotion_eligible is not False
        or receipt.receipt_hash
        != canonical_hash(_verification_receipt_payload_v2(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_external_v2_signed_receipt_semantics_invalid", "/")
    return receipt


def _issue_challenge_with_registry_v2(
    *,
    verified_release: release_identity_v1.HipFgmresExternalVerifiedReleaseV1,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    request_id: str,
    campaign_id: str,
    ttl_seconds: int,
    registry: HipFgmresExternalTrustAnchorRegistryResultV1,
    now: datetime | None = None,
) -> HipFgmresExternalChallengeV2:
    binding, identity = _fresh_verified_release_snapshot_v2(verified_release)
    if (
        type(registry) is not HipFgmresExternalTrustAnchorRegistryResultV1
        or type(key_id) is not str
        or type(runner_id) is not str
        or type(run_sequence) is not int
        or run_sequence <= 0
        or type(request_id) is not str
        or _ID_RE.fullmatch(request_id) is None
        or type(campaign_id) is not str
        or _ID_RE.fullmatch(campaign_id) is None
        or type(ttl_seconds) is not int
        or not 60 <= ttl_seconds <= 3600
    ):
        _fail("hip_fgmres_external_v2_challenge_request_invalid", "/challenge")
    current = _utc_now_v2() if now is None else _validated_utc_datetime_v2(now, "/now")
    key = _resolve_active_key_v2(
        registry,
        key_id=key_id,
        runner_id=runner_id,
        run_sequence=run_sequence,
        observed_at=current,
    )
    if (
        key.allowed_fixture_registry_bytes_sha256
        != binding.fixture_registry_bytes_sha256
        or key.allowed_fixture_registry_hash != binding.fixture_registry_hash
    ):
        _fail(
            "hip_fgmres_external_v2_challenge_release_not_allowed",
            "/release_binding",
        )
    expires_at = current + timedelta(seconds=ttl_seconds)
    if key.valid_until_utc is not None and expires_at > _parse_trust_anchor_utc_v2(
        key.valid_until_utc,
        "/trust_anchor/valid_until_utc",
    ):
        _fail("hip_fgmres_external_v2_trust_anchor_not_active", "/key_id")
    unsigned = {
        "schema_version": HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V2,
        "request_id": request_id,
        "audience": _AUDIENCE_V2,
        "campaign_id": campaign_id,
        "nonce_base64": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        "issued_at_utc": _format_utc_v2(current),
        "expires_at_utc": _format_utc_v2(expires_at),
        "expected_key_id": key.key_id,
        "expected_key_epoch": key.key_epoch,
        "expected_runner_id": key.runner_id,
        "expected_run_sequence": run_sequence,
        "expected_release_binding_hash": binding.binding_hash,
        "expected_release_identity_receipt_schema_version": identity.schema_version,
        "expected_release_identity_receipt_hash": identity.receipt_hash,
        "expected_trust_registry_hash": registry.registry_hash,
        "expected_architecture_base": "gfx1100",
        "expected_suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    }
    payload = _ChallengePayloadV2(
        challenge_id=canonical_hash(unsigned),
        **unsigned,
    )
    return HipFgmresExternalChallengeV2(payload, mint=_CHALLENGE_MINT_V2)


def _rehydrate_hip_fgmres_external_challenge_v2(
    payload: dict[str, Any],
) -> HipFgmresExternalChallengeV2:
    """Rehydrate an exact durable-authorized v2 challenge payload."""

    restored = _validate_stored_challenge_payload_v2(payload)
    return HipFgmresExternalChallengeV2(restored, mint=_CHALLENGE_MINT_V2)


def _validate_stored_challenge_payload_v2(
    payload: dict[str, Any],
) -> _ChallengePayloadV2:
    if type(payload) is not dict:
        _fail("hip_fgmres_external_v2_stored_challenge_type_invalid", "/challenge")
    expected_fields = frozenset(_ChallengePayloadV2.__dataclass_fields__)
    if frozenset(payload) != expected_fields:
        _fail("hip_fgmres_external_v2_stored_challenge_fields_invalid", "/challenge")
    string_fields = tuple(
        name
        for name in _ChallengePayloadV2.__dataclass_fields__
        if name not in ("expected_key_epoch", "expected_run_sequence")
    )
    for field in string_fields:
        if type(payload[field]) is not str:
            _fail(
                "hip_fgmres_external_v2_stored_challenge_field_invalid",
                f"/challenge/{field}",
            )
    for field in ("expected_key_epoch", "expected_run_sequence"):
        if type(payload[field]) is not int or payload[field] <= 0:
            _fail(
                "hip_fgmres_external_v2_stored_challenge_field_invalid",
                f"/challenge/{field}",
            )
    if (
        payload["schema_version"] != HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V2
        or _HASH_RE.fullmatch(payload["challenge_id"]) is None
        or _ID_RE.fullmatch(payload["request_id"]) is None
        or payload["audience"] != _AUDIENCE_V2
        or _ID_RE.fullmatch(payload["campaign_id"]) is None
        or _KEY_ID_RE.fullmatch(payload["expected_key_id"]) is None
        or _RUNNER_ID_RE.fullmatch(payload["expected_runner_id"]) is None
        or _HASH_RE.fullmatch(payload["expected_release_binding_hash"]) is None
        or payload["expected_release_identity_receipt_schema_version"]
        != release_identity_v1.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        or _HASH_RE.fullmatch(payload["expected_release_identity_receipt_hash"]) is None
        or _HASH_RE.fullmatch(payload["expected_trust_registry_hash"]) is None
        or payload["expected_architecture_base"] != "gfx1100"
        or payload["expected_suite_id"] != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or payload["expected_key_id"]
        != f"ed25519:{payload['expected_runner_id']}:v{payload['expected_key_epoch']}"
    ):
        _fail("hip_fgmres_external_v2_stored_challenge_semantics_invalid", "/challenge")
    try:
        decode_canonical_base64_v1(
            payload["nonce_base64"],
            expected_byte_count=32,
            path="/challenge/nonce_base64",
        )
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_v2_stored_challenge_nonce_invalid",
            "/challenge/nonce_base64",
            exc.code,
        )
    if (
        _UTC_RE.fullmatch(payload["issued_at_utc"]) is None
        or _UTC_RE.fullmatch(payload["expires_at_utc"]) is None
    ):
        _fail("hip_fgmres_external_v2_stored_challenge_timestamp_invalid", "/challenge")
    issued = _parse_utc_v2(payload["issued_at_utc"], "/challenge/issued_at_utc")
    expires = _parse_utc_v2(payload["expires_at_utc"], "/challenge/expires_at_utc")
    lifetime = expires - issued
    if (
        lifetime < timedelta(seconds=60)
        or lifetime > timedelta(seconds=3600)
        or lifetime.microseconds != 0
    ):
        _fail("hip_fgmres_external_v2_stored_challenge_timestamp_invalid", "/challenge")
    unsigned = {
        field: payload[field]
        for field in _ChallengePayloadV2.__dataclass_fields__
        if field != "challenge_id"
    }
    if payload["challenge_id"] != canonical_hash(unsigned):
        _fail("hip_fgmres_external_v2_stored_challenge_hash_invalid", "/challenge")
    return _ChallengePayloadV2(**payload)


def _extract_hip_fgmres_external_envelope_routing_v2(
    envelope_bytes: bytes,
) -> dict[str, Any]:
    """Extract strict v2 challenge routing without asserting signature authority."""

    envelope = _parse_canonical_envelope_v2(envelope_bytes)
    _validate_json_schema_v2(
        envelope,
        _ENVELOPE_SCHEMA_RESOURCE_V2,
        path="/envelope",
    )
    signed_payload = _validate_envelope_integrity_v2(envelope)
    challenge = _validate_stored_challenge_payload_v2(signed_payload["challenge"])
    _require_payload_identity_matches_challenge_v2(signed_payload, challenge)
    return challenge.to_dict()


def _parse_runner_completed_at_utc_v2(envelope_bytes: bytes) -> datetime:
    """Parse a bounded canonical v2 envelope and return its runner completion UTC."""

    envelope = _parse_canonical_envelope_v2(envelope_bytes)
    _validate_json_schema_v2(
        envelope,
        _ENVELOPE_SCHEMA_RESOURCE_V2,
        path="/envelope",
    )
    signed_payload = _validate_envelope_integrity_v2(envelope)
    return _parse_utc_v2(
        signed_payload["runner"]["completed_at_utc"],
        "/signed_payload/runner/completed_at_utc",
    )


def _verify_with_authorities_v2(
    envelope_bytes: bytes,
    *,
    challenge: HipFgmresExternalChallengeV2,
    verified_release: release_identity_v1.HipFgmresExternalVerifiedReleaseV1,
    trust_registry: HipFgmresExternalTrustAnchorRegistryResultV1,
    fixture_registry: HipFgmresFixtureRegistryResultV1,
    now: datetime | None = None,
    success_commit_hook: (
        Callable[[HipFgmresExternalSignedEvidenceReceiptV2], None] | None
    ) = None,
) -> HipFgmresExternalSignedEvidenceReceiptV2:
    """Verify one v2 envelope without falling back to the v1 verifier."""

    if type(challenge) is not HipFgmresExternalChallengeV2:
        _fail("hip_fgmres_external_v2_challenge_type_invalid", "/challenge")
    if type(trust_registry) is not HipFgmresExternalTrustAnchorRegistryResultV1:
        _fail("hip_fgmres_external_v2_trust_registry_type_invalid", "/trust_registry")
    if type(fixture_registry) is not HipFgmresFixtureRegistryResultV1:
        _fail(
            "hip_fgmres_external_v2_fixture_registry_type_invalid", "/fixture_registry"
        )
    if success_commit_hook is not None and not callable(success_commit_hook):
        _fail("hip_fgmres_external_v2_success_commit_hook_invalid", "/commit_hook")

    envelope = _parse_canonical_envelope_v2(envelope_bytes)
    _validate_json_schema_v2(
        envelope,
        _ENVELOPE_SCHEMA_RESOURCE_V2,
        path="/envelope",
    )
    signed_payload = _validate_envelope_integrity_v2(envelope)
    binding, identity = _fresh_verified_release_snapshot_v2(verified_release)
    if signed_payload["challenge"] != challenge.to_dict():
        _fail(
            "hip_fgmres_external_v2_challenge_mismatch",
            "/signed_payload/challenge",
        )
    if signed_payload["release_binding"] != binding.to_dict():
        _fail(
            "hip_fgmres_external_v2_release_binding_mismatch",
            "/signed_payload/release_binding",
        )
    challenge_payload = challenge._payload
    _require_payload_identity_matches_challenge_v2(signed_payload, challenge_payload)
    if (
        identity.release_binding_hash != binding.binding_hash
        or challenge_payload.expected_release_binding_hash != binding.binding_hash
        or challenge_payload.expected_release_identity_receipt_schema_version
        != identity.schema_version
        or challenge_payload.expected_release_identity_receipt_hash
        != identity.receipt_hash
        or signed_payload["release_identity_receipt_schema_version"]
        != identity.schema_version
        or signed_payload["release_identity_receipt_hash"] != identity.receipt_hash
    ):
        _fail(
            "hip_fgmres_external_v2_release_identity_mismatch",
            "/signed_payload/release_identity_receipt_hash",
        )
    runner = signed_payload["runner"]
    if not any(key.key_id == envelope["key_id"] for key in trust_registry.keys):
        _fail("hip_fgmres_external_v2_trust_anchor_not_found", "/key_id")
    if (
        challenge_payload.expected_trust_registry_hash != trust_registry.registry_hash
        or challenge_payload.expected_key_id != envelope["key_id"]
        or challenge_payload.expected_runner_id != runner["runner_id"]
        or challenge_payload.expected_run_sequence != runner["run_sequence"]
        or challenge_payload.expected_architecture_base != runner["architecture_base"]
        or challenge_payload.expected_suite_id
        != signed_payload["fixture_registry"]["suite_id"]
    ):
        _fail("hip_fgmres_external_v2_challenge_binding_invalid", "/challenge")
    current = _utc_now_v2() if now is None else _validated_utc_datetime_v2(now, "/now")
    issued = _parse_utc_v2(challenge_payload.issued_at_utc, "/challenge/issued_at_utc")
    expires = _parse_utc_v2(
        challenge_payload.expires_at_utc, "/challenge/expires_at_utc"
    )
    started = _parse_utc_v2(runner["started_at_utc"], "/runner/started_at_utc")
    completed = _parse_utc_v2(runner["completed_at_utc"], "/runner/completed_at_utc")
    if not (issued <= started <= completed <= current <= expires):
        _fail(
            "hip_fgmres_external_v2_challenge_expired_or_time_invalid",
            "/challenge",
        )
    key = _resolve_active_key_v2(
        trust_registry,
        key_id=envelope["key_id"],
        runner_id=runner["runner_id"],
        run_sequence=runner["run_sequence"],
        observed_at=completed,
    )
    if (
        key.allowed_fixture_registry_bytes_sha256
        != binding.fixture_registry_bytes_sha256
        or key.allowed_fixture_registry_hash != binding.fixture_registry_hash
    ):
        _fail(
            "hip_fgmres_external_v2_challenge_release_not_allowed",
            "/release_binding",
        )
    if key.key_epoch != challenge_payload.expected_key_epoch:
        _fail("hip_fgmres_external_v2_key_epoch_mismatch", "/key_id")

    reservation = challenge._reserve()
    try:
        message = _SIGNATURE_DOMAIN_V2 + canonical_json_bytes(
            _signed_content_v2(envelope)
        )
        try:
            verify_ed25519_signature_v1(
                public_key=key.public_key_bytes,
                signature_base64=envelope["signature_base64"],
                message=message,
            )
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_v2_signature_invalid",
                "/signature_base64",
                exc.code,
            )
        try:
            family_receipt = (
                signed_evidence_v1._replay_external_fixed_suite_payload_common_v1(
                    signed_payload=signed_payload,
                    release_binding=binding,
                    fixture_registry=fixture_registry,
                )
            )
        except signed_evidence_v1.HipFgmresExternalSignedEvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_v2_fixed_suite_replay_invalid",
                exc.path,
                exc.code,
            )
        _validate_payload_claims_v2(signed_payload["claims"])
        final_binding, final_identity = _fresh_verified_release_snapshot_v2(
            verified_release
        )
        if final_binding != binding or final_identity != identity:
            _fail(
                "hip_fgmres_external_v2_release_artifact_replay_failed",
                "/release",
            )
        draft = HipFgmresExternalSignedEvidenceReceiptV2(
            schema_version=(
                HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V2
            ),
            capability_profile=HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2,
            status="external_gfx1100_release_identity_signed_evidence_verified",
            evidence_scope=HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V2,
            envelope_hash=envelope["envelope_hash"],
            signed_payload_sha256=envelope["signed_payload_sha256"],
            key_id=key.key_id,
            key_epoch=key.key_epoch,
            runner_id=key.runner_id,
            run_sequence=runner["run_sequence"],
            challenge_id=challenge.challenge_id,
            release_binding_hash=binding.binding_hash,
            release_identity_receipt_schema_version=identity.schema_version,
            release_identity_receipt_hash=identity.receipt_hash,
            trust_registry_hash=trust_registry.registry_hash,
            fixture_registry_hash=fixture_registry.registry_hash,
            family_receipt_hash=family_receipt.receipt_hash,
            common_runtime_binding_hash=signed_payload["common_runtime_binding_hash"],
            ordered_case_aggregate_hash=signed_payload["ordered_case_aggregate_hash"],
            verified_slot_count=len(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
            verified_slot_ids=HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
            claims=HipFgmresExternalSignedEvidenceClaimsV2(),
            promotion_eligible=False,
            receipt_hash=_ZERO_HASH,
        )
        receipt = replace(
            draft,
            receipt_hash=canonical_hash(
                _verification_receipt_payload_v2(draft, include_hash=False)
            ),
        )
        receipt = validate_hip_fgmres_external_signed_evidence_receipt_v2(receipt)
        if success_commit_hook is not None:
            success_commit_hook(receipt)
        challenge._consume(reservation)
    except BaseException:
        challenge._release(reservation)
        raise
    return receipt


def _fresh_verified_release_snapshot_v2(
    verified_release: release_identity_v1.HipFgmresExternalVerifiedReleaseV1,
) -> tuple[
    HipFgmresExternalReleaseBindingV1,
    release_identity_v1.HipFgmresExternalReleaseIdentityReceiptV1,
]:
    try:
        release_identity_v1._validate_verified_release(verified_release)
        replayed = release_identity_v1.verify_hip_fgmres_external_release_artifacts_v1(
            verified_release
        )
        if replayed is not verified_release:
            _fail("hip_fgmres_external_v2_verified_release_identity_lost", "/release")
        binding = verified_release.release_binding
        identity = verified_release.identity_receipt
        release_identity_v1.validate_hip_fgmres_external_release_identity_receipt_v1(
            identity
        )
    except HipFgmresExternalSignedEvidenceV2Error:
        raise
    except release_identity_v1.HipFgmresExternalReleaseIdentityV1Error as exc:
        _fail(
            "hip_fgmres_external_v2_release_artifact_replay_failed",
            exc.path,
            exc.code,
        )
    if (
        identity.schema_version
        != release_identity_v1.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        or identity.release_binding_hash != binding.binding_hash
    ):
        _fail("hip_fgmres_external_v2_release_identity_mismatch", "/release")
    return binding, identity


def _require_payload_identity_matches_challenge_v2(
    signed_payload: dict[str, Any],
    challenge: _ChallengePayloadV2,
) -> None:
    if (
        signed_payload["release_identity_receipt_schema_version"]
        != challenge.expected_release_identity_receipt_schema_version
        or signed_payload["release_identity_receipt_hash"]
        != challenge.expected_release_identity_receipt_hash
    ):
        _fail(
            "hip_fgmres_external_v2_release_identity_mismatch",
            "/signed_payload/release_identity_receipt_hash",
        )


def _validate_envelope_integrity_v2(envelope: dict[str, Any]) -> dict[str, Any]:
    signed_payload = envelope["signed_payload"]
    if (
        envelope["schema_version"]
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V2
        or envelope["capability_profile"]
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2
        or envelope["algorithm"] != ED25519_ALGORITHM_V1
        or envelope["envelope_hash"]
        != canonical_hash(
            {key: value for key, value in envelope.items() if key != "envelope_hash"}
        )
        or envelope["signed_payload_sha256"]
        != sha256_prefixed(canonical_json_bytes(signed_payload))
        or signed_payload["payload_schema_version"]
        != HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V2
        or signed_payload["purpose"] != _PURPOSE_V2
        or signed_payload["evidence_scope"]
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCOPE_V2
    ):
        _fail("hip_fgmres_external_v2_envelope_semantics_invalid", "/envelope")
    return signed_payload


def _validate_payload_claims_v2(claims: dict[str, Any]) -> None:
    expected = {
        "runner_attests_actual_native_hip_execution": True,
        "runner_attests_external_gfx1100_fixed_suite": True,
        "runner_attests_release_identity_receipt_hash": True,
        "raw_completion_payloads_included": True,
        "full_model_family_parity_verified": False,
        "multiarchitecture_promotion_verified": False,
        "result_ir_verified": False,
        "iteration_host_copy_zero_verified": False,
        "speedup_verified": False,
        "end_to_end_o_n_verified": False,
        "commercial_ready": False,
        "promotion_eligible": False,
    }
    if claims != expected:
        _fail(
            "hip_fgmres_external_v2_payload_claims_invalid",
            "/signed_payload/claims",
        )


def _resolve_active_key_v2(
    registry: HipFgmresExternalTrustAnchorRegistryResultV1,
    *,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    observed_at: datetime,
) -> HipFgmresExternalTrustAnchorV1:
    matches = tuple(key for key in registry.keys if key.key_id == key_id)
    if len(matches) != 1:
        _fail("hip_fgmres_external_v2_trust_anchor_not_found", "/key_id")
    key = matches[0]
    valid_from = _parse_trust_anchor_utc_v2(
        key.valid_from_utc,
        "/trust_anchor/valid_from_utc",
    )
    valid_until = (
        None
        if key.valid_until_utc is None
        else _parse_trust_anchor_utc_v2(
            key.valid_until_utc,
            "/trust_anchor/valid_until_utc",
        )
    )
    if (
        key.status != "active"
        or key.runner_id != runner_id
        or key.allowed_architecture_base != "gfx1100"
        or key.allowed_suite_id != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or run_sequence < key.minimum_run_sequence
        or (
            key.maximum_run_sequence is not None
            and run_sequence > key.maximum_run_sequence
        )
        or observed_at < valid_from
        or (valid_until is not None and observed_at > valid_until)
    ):
        _fail("hip_fgmres_external_v2_trust_anchor_not_active", "/key_id")
    return key


def _signed_content_v2(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": envelope["schema_version"],
        "capability_profile": envelope["capability_profile"],
        "algorithm": envelope["algorithm"],
        "key_id": envelope["key_id"],
        "signed_payload_sha256": envelope["signed_payload_sha256"],
        "signed_payload": envelope["signed_payload"],
    }


def _verification_receipt_payload_v2(
    receipt: HipFgmresExternalSignedEvidenceReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "envelope_hash": receipt.envelope_hash,
        "signed_payload_sha256": receipt.signed_payload_sha256,
        "key_id": receipt.key_id,
        "key_epoch": receipt.key_epoch,
        "runner_id": receipt.runner_id,
        "run_sequence": receipt.run_sequence,
        "challenge_id": receipt.challenge_id,
        "release_binding_hash": receipt.release_binding_hash,
        "release_identity_receipt_schema_version": (
            receipt.release_identity_receipt_schema_version
        ),
        "release_identity_receipt_hash": receipt.release_identity_receipt_hash,
        "trust_registry_hash": receipt.trust_registry_hash,
        "fixture_registry_hash": receipt.fixture_registry_hash,
        "family_receipt_hash": receipt.family_receipt_hash,
        "common_runtime_binding_hash": receipt.common_runtime_binding_hash,
        "ordered_case_aggregate_hash": receipt.ordered_case_aggregate_hash,
        "verified_slot_count": receipt.verified_slot_count,
        "verified_slot_ids": list(receipt.verified_slot_ids),
        "claims": receipt.claims.to_dict(),
        "promotion_eligible": receipt.promotion_eligible,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _parse_canonical_envelope_v2(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _ENVELOPE_MAX_BYTES_V2:
        _fail("hip_fgmres_external_v2_envelope_extent_invalid", "/envelope")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_external_v2_envelope_bom_forbidden", "/envelope")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKeyError(key)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
        _reject_nonfinite_v2(payload, path="/envelope")
        canonical = canonical_json_bytes(payload)
    except _DuplicateKeyError as exc:
        _fail(
            "hip_fgmres_external_v2_envelope_duplicate_key",
            "/envelope",
            str(exc)[:128],
        )
    except RecursionError:
        _fail("hip_fgmres_external_v2_envelope_extent_invalid", "/envelope")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        _fail(
            "hip_fgmres_external_v2_envelope_json_invalid",
            "/envelope",
            type(exc).__name__,
        )
    if type(payload) is not dict:
        _fail("hip_fgmres_external_v2_envelope_root_invalid", "/envelope")
    if raw != canonical:
        _fail("hip_fgmres_external_v2_envelope_not_canonical", "/envelope")
    return payload


def _reject_nonfinite_v2(value: Any, *, path: str) -> None:
    stack: list[tuple[Any, _EnvelopeJsonPathV2 | None, int]] = [(value, None, 0)]
    node_count = 0
    while stack:
        item, item_path, depth = stack.pop()
        node_count += 1
        if (
            node_count > _ENVELOPE_MAX_JSON_NODES_V2
            or depth > _ENVELOPE_MAX_JSON_DEPTH_V2
            or (type(item) in (dict, list) and depth >= _ENVELOPE_MAX_JSON_DEPTH_V2)
        ):
            _fail(
                "hip_fgmres_external_v2_envelope_extent_invalid",
                _format_envelope_json_path_v2(path, item_path),
            )
        if type(item) is float and not math.isfinite(item):
            _fail(
                "hip_fgmres_external_v2_envelope_nonfinite",
                _format_envelope_json_path_v2(path, item_path),
            )
        if type(item) in (dict, list) and (
            node_count + len(stack) + len(item) > _ENVELOPE_MAX_JSON_NODES_V2
        ):
            _fail(
                "hip_fgmres_external_v2_envelope_extent_invalid",
                _format_envelope_json_path_v2(path, item_path),
            )
        if type(item) is dict:
            for key, child in item.items():
                stack.append((child, _EnvelopeJsonPathV2(item_path, key), depth + 1))
        elif type(item) is list:
            for index, child in enumerate(item):
                stack.append(
                    (child, _EnvelopeJsonPathV2(item_path, str(index)), depth + 1)
                )


def _format_envelope_json_path_v2(
    root: str,
    leaf: _EnvelopeJsonPathV2 | None,
) -> str:
    segments: list[str] = []
    current = leaf
    while current is not None:
        segments.append(current.segment)
        current = current.parent
    result = root[:_ENVELOPE_MAX_ERROR_PATH_CHARS_V2]
    for segment in reversed(segments):
        if len(result) >= _ENVELOPE_MAX_ERROR_PATH_CHARS_V2:
            break
        addition = "/" + segment
        remaining = _ENVELOPE_MAX_ERROR_PATH_CHARS_V2 - len(result)
        if len(addition) <= remaining:
            result += addition
            continue
        if remaining > 3:
            result += addition[: remaining - 3] + "..."
        break
    return result


def _validate_json_schema_v2(
    payload: dict[str, Any],
    resource_name: str,
    *,
    path: str,
) -> None:
    try:
        raw = (
            resources.files("structural_analysis.schemas")
            .joinpath(resource_name)
            .read_bytes()
        )
        schema = json.loads(raw.decode("utf-8"))
        Draft202012Validator.check_schema(schema)
        error = next(Draft202012Validator(schema).iter_errors(payload), None)
    except RecursionError:
        _fail("hip_fgmres_external_v2_envelope_extent_invalid", path)
    except Exception as exc:
        _fail("hip_fgmres_external_v2_schema_invalid", path, type(exc).__name__)
    if error is not None:
        location = (
            path.rstrip("/") + "/" + "/".join(str(part) for part in error.absolute_path)
        )
        if len(location) > _ENVELOPE_MAX_ERROR_PATH_CHARS_V2:
            location = location[: _ENVELOPE_MAX_ERROR_PATH_CHARS_V2 - 3] + "..."
        keyword = str(error.validator)[:64]
        _fail(
            "hip_fgmres_external_v2_schema_validation_failed",
            location,
            f"schema keyword {keyword} rejected value",
        )


def _parse_utc_v2(value: str, path: str) -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        _fail("hip_fgmres_external_v2_timestamp_invalid", path)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail("hip_fgmres_external_v2_timestamp_invalid", path)
    return parsed


def _parse_trust_anchor_utc_v2(value: str, path: str) -> datetime:
    """Parse the existing registry's canonical seconds-or-microseconds UTC."""

    if type(value) is not str:
        _fail("hip_fgmres_external_v2_timestamp_invalid", path)
    format_string = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
    try:
        parsed = datetime.strptime(value, format_string).replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("hip_fgmres_external_v2_timestamp_invalid", path)
    if _format_trust_anchor_utc_v2(parsed, fractional="." in value) != value:
        _fail("hip_fgmres_external_v2_timestamp_invalid", path)
    return parsed


def _format_trust_anchor_utc_v2(value: datetime, *, fractional: bool) -> str:
    format_string = "%Y-%m-%dT%H:%M:%S.%fZ" if fractional else "%Y-%m-%dT%H:%M:%SZ"
    return value.astimezone(timezone.utc).strftime(format_string)


def _validated_utc_datetime_v2(value: datetime, path: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail("hip_fgmres_external_v2_timestamp_invalid", path)
    return value.astimezone(timezone.utc)


def _format_utc_v2(value: datetime) -> str:
    return _validated_utc_datetime_v2(value, "/time").strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _utc_now_v2() -> datetime:
    return datetime.now(timezone.utc)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalSignedEvidenceV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V2",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V2",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V2",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V2",
    "HipFgmresExternalChallengeV2",
    "HipFgmresExternalSignedEvidenceClaimsV2",
    "HipFgmresExternalSignedEvidenceReceiptV2",
    "HipFgmresExternalSignedEvidenceV2Error",
    "HipFgmresExternalVerifiedSignedEvidenceV2",
    "issue_hip_fgmres_external_evidence_challenge_for_verified_release_v2",
    "validate_hip_fgmres_external_signed_evidence_receipt_v2",
    "verify_hip_fgmres_external_signed_evidence_for_verified_release_v2",
]
