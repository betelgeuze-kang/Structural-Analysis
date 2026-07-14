"""Verify Ed25519-signed external gfx1100 FGMRES fixed-suite evidence.

This authority is deliberately separate from the process-local model-family
v2 result.  A successful verification proves a package-trusted runner signed
the exact canonical payload and that the included raw numerics replay against
the current package registry.  It does not establish hardware-root
attestation, local observation, two-architecture promotion, ResultIR,
host-copy-zero, performance, O(N), or commercial readiness.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib import metadata, resources
import json
import math
import re
import secrets
from threading import Lock
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    normalize_hip_gcn_architecture_v1,
)
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

from .fgmres_completion_export_v1 import _bundle_hash
from .fgmres_external_trust_anchor_registry_v1 import (
    HipFgmresExternalTrustAnchorRegistryResultV1,
    HipFgmresExternalTrustAnchorV1,
    load_hip_fgmres_external_trust_anchor_registry_v1,
    validate_hip_fgmres_external_trust_anchor_registry_result_v1,
)
from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    HipFgmresFixtureRegistryResultV1,
    HipFgmresFixtureReplayV1,
    load_hip_fgmres_fixture_registry_v1,
    validate_hip_fgmres_fixture_registry_result_v1,
)
from .fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityBindingsV1,
    HipFgmresModelCaseParityClaimsV1,
    HipFgmresModelCaseParityDimensionsV1,
    HipFgmresModelCaseParityDiscreteComparisonV1,
    HipFgmresModelCaseParityReceiptV1,
    HipFgmresModelCaseParityTelemetryV1,
    HipFgmresModelCaseParityToleranceV1,
    HipFgmresModelCaseParityVectorComparisonV1,
    replay_hip_fgmres_detached_model_case_numerics_v1,
    validate_hip_fgmres_model_case_parity_receipt_v1,
)
from .fgmres_model_family_parity_v2 import (
    HipFgmresModelFamilyClaimsV2,
    HipFgmresModelFamilyCoverageV2,
    HipFgmresModelFamilyObservedCellV2,
    HipFgmresModelFamilyParityReceiptV2,
    validate_hip_fgmres_model_family_parity_receipt_v2,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomePolicySnapshotV1,
    decode_hip_fgmres_detached_completion_payload_v1,
)


HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-signed-evidence.v1"
)
HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-signed-payload.v1"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-signed-evidence-receipt.v1"
)
HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-challenge.v1"
)
HIP_FGMRES_EXTERNAL_RELEASE_BINDING_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-release-binding.v1"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1 = (
    "phase0_external_gfx1100_fixed_suite_ed25519_verification"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCOPE_V1 = (
    "trusted_runner_signed_serialized_lane_non_promoting"
)
HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V1 = (
    "trusted_runner_signed_raw_numerics_replayed_non_promoting"
)

_PURPOSE = "hip_fgmres_external_gfx1100_fixed_suite_attestation"
_AUDIENCE = "structural-analysis-engine-v2-verifier"
_DISTRIBUTION_NAME = "structural-optimization-workbench"
_ENVELOPE_SCHEMA_RESOURCE = "hip_fgmres_external_signed_evidence_v1.schema.json"
_RECEIPT_SCHEMA_RESOURCE = "hip_fgmres_external_signed_evidence_receipt_v1.schema.json"
_ENVELOPE_MAX_BYTES = 4 * 1024 * 1024
_ENVELOPE_MAX_JSON_NODES = 200_000
_ENVELOPE_MAX_JSON_DEPTH = 64
_SIGNATURE_DOMAIN = b"structural-analysis\0hip-fgmres-external-gfx1100-evidence\0v1\0"
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_KEY_ID_RE = re.compile(r"^ed25519:[a-z0-9][a-z0-9._-]{2,63}:v[1-9][0-9]*$")
_RUNNER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
_ZERO_HASH = "sha256:" + "0" * 64
_CHALLENGE_MINT = object()


class HipFgmresExternalSignedEvidenceV1Error(RuntimeError):
    """Stable fail-closed external signed-evidence error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReleaseBindingV1:
    schema_version: str
    distribution_name: str
    distribution_version: str
    wheel_filename: str
    wheel_byte_count: int
    wheel_sha256: str
    wheel_record_sha256: str
    source_commit: str
    source_tree_sha256: str
    source_bundle_sha256: str
    runner_source_sha256: str
    build_recipe_sha256: str
    dependency_lock_sha256: str
    schema_manifest_count: int
    schema_manifest_hash: str
    fixture_registry_bytes_sha256: str
    fixture_registry_hash: str
    fixture_registry_receipt_hash: str
    binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_release_binding_v1(self)
        return _release_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class _ChallengePayloadV1:
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
    expected_trust_registry_hash: str
    expected_architecture_base: str
    expected_suite_id: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class HipFgmresExternalChallengeV1:
    """Verifier-owned, process-local, single-use challenge authority."""

    __slots__ = ("_payload", "_lock", "_state", "_reservation")

    def __init__(self, payload: _ChallengePayloadV1, *, mint: object) -> None:
        if mint is not _CHALLENGE_MINT or type(payload) is not _ChallengePayloadV1:
            _fail("hip_fgmres_external_challenge_construction_forbidden", "/challenge")
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
                _fail("hip_fgmres_external_challenge_replayed", "/challenge")
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
                _fail("hip_fgmres_external_challenge_reservation_lost", "/challenge")
            self._state = "consumed"
            self._reservation = None


@dataclass(frozen=True, slots=True)
class HipFgmresExternalSignedEvidenceClaimsV1:
    canonical_envelope_verified: bool = True
    package_trust_anchor_matched: bool = True
    ed25519_signature_verified: bool = True
    verifier_challenge_consumed: bool = True
    expected_release_binding_matched: bool = True
    current_schema_manifest_matched: bool = True
    current_fixture_registry_bound: bool = True
    external_gfx1100_fixed_suite_signed: bool = True
    raw_completion_payload_integrity_verified: bool = True
    raw_numerical_parity_replayed: bool = True
    solve_record_semantics_replayed: bool = True
    durable_replay_ledger_verified: bool = False
    local_gfx1030_signed: bool = False
    external_evidence_counted_in_family_v2: bool = False
    same_artifact_two_architecture_verified: bool = False
    external_hardware_independently_observed_by_local_process: bool = False
    hardware_root_attested: bool = False
    full_model_family_parity_verified: bool = False
    multiarchitecture_promotion_verified: bool = False
    result_ir_verified: bool = False
    iteration_host_copy_zero_verified: bool = False
    speedup_verified: bool = False
    end_to_end_o_n_verified: bool = False
    commercial_ready: bool = False
    promotion_eligible: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalSignedEvidenceReceiptV1:
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
    trust_registry_hash: str
    fixture_registry_hash: str
    family_receipt_hash: str
    common_runtime_binding_hash: str
    ordered_case_aggregate_hash: str
    verified_slot_count: int
    verified_slot_ids: tuple[str, ...]
    claims: HipFgmresExternalSignedEvidenceClaimsV1
    promotion_eligible: bool
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_signed_evidence_receipt_v1(self)
        return _verification_receipt_payload(self, include_hash=True)


class _DuplicateKeyError(ValueError):
    pass


def compile_hip_fgmres_external_release_binding_v1(
    *,
    wheel_filename: str,
    wheel_byte_count: int,
    wheel_sha256: str,
    wheel_record_sha256: str,
    source_commit: str,
    source_tree_sha256: str,
    source_bundle_sha256: str,
    runner_source_sha256: str,
    build_recipe_sha256: str,
    dependency_lock_sha256: str,
) -> HipFgmresExternalReleaseBindingV1:
    """Bind caller-supplied expected release identities to current package data.

    This compiler validates the shape of wheel/source/runner hashes but does not
    open or independently hash those artifacts.  It does independently bind the
    installed distribution version, schema manifest, and fixture-registry replay.
    """

    registry = _FIXTURE_REGISTRY_LOADER_AUTHORITY()
    validate_hip_fgmres_fixture_registry_result_v1(registry)
    schema_count, schema_hash = _schema_manifest_identity()
    try:
        distribution_version = metadata.version(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError as exc:
        _fail(
            "hip_fgmres_external_release_distribution_missing",
            "/distribution",
            str(exc),
        )
    draft = HipFgmresExternalReleaseBindingV1(
        schema_version=HIP_FGMRES_EXTERNAL_RELEASE_BINDING_SCHEMA_VERSION_V1,
        distribution_name=_DISTRIBUTION_NAME,
        distribution_version=distribution_version,
        wheel_filename=wheel_filename,
        wheel_byte_count=wheel_byte_count,
        wheel_sha256=wheel_sha256,
        wheel_record_sha256=wheel_record_sha256,
        source_commit=source_commit,
        source_tree_sha256=source_tree_sha256,
        source_bundle_sha256=source_bundle_sha256,
        runner_source_sha256=runner_source_sha256,
        build_recipe_sha256=build_recipe_sha256,
        dependency_lock_sha256=dependency_lock_sha256,
        schema_manifest_count=schema_count,
        schema_manifest_hash=schema_hash,
        fixture_registry_bytes_sha256=registry.registry_bytes_sha256,
        fixture_registry_hash=registry.registry_hash,
        fixture_registry_receipt_hash=registry.receipt_hash,
        binding_hash=_ZERO_HASH,
    )
    result = replace(
        draft,
        binding_hash=canonical_hash(_release_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_release_binding_v1(result)


def validate_hip_fgmres_external_release_binding_v1(
    binding: HipFgmresExternalReleaseBindingV1,
) -> HipFgmresExternalReleaseBindingV1:
    if type(binding) is not HipFgmresExternalReleaseBindingV1:
        _fail("hip_fgmres_external_release_binding_type_invalid", "/release_binding")
    values = _release_payload(binding, include_hash=True)
    if (
        binding.schema_version != HIP_FGMRES_EXTERNAL_RELEASE_BINDING_SCHEMA_VERSION_V1
        or binding.distribution_name != _DISTRIBUTION_NAME
        or type(binding.distribution_version) is not str
        or not binding.distribution_version
        or type(binding.wheel_filename) is not str
        or "/" in binding.wheel_filename
        or "\\" in binding.wheel_filename
        or not binding.wheel_filename.endswith(".whl")
        or type(binding.wheel_byte_count) is not int
        or binding.wheel_byte_count <= 0
        or _SOURCE_COMMIT_RE.fullmatch(binding.source_commit) is None
        or any(
            _HASH_RE.fullmatch(value) is None
            for name, value in values.items()
            if name.endswith("_sha256") or name.endswith("_hash")
        )
        or type(binding.schema_manifest_count) is not int
        or binding.schema_manifest_count <= 0
        or binding.binding_hash
        != canonical_hash(_release_payload(binding, include_hash=False))
    ):
        _fail("hip_fgmres_external_release_binding_invalid", "/release_binding")
    return binding


def issue_hip_fgmres_external_evidence_challenge_v1(
    *,
    release_binding: HipFgmresExternalReleaseBindingV1,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    request_id: str,
    campaign_id: str,
    ttl_seconds: int = 900,
) -> HipFgmresExternalChallengeV1:
    """Issue an unpredictable single-use challenge for a package-trusted key."""

    registry = _TRUST_REGISTRY_LOADER_AUTHORITY()
    validate_hip_fgmres_external_trust_anchor_registry_result_v1(registry)
    return _issue_challenge_with_registry(
        release_binding=release_binding,
        key_id=key_id,
        runner_id=runner_id,
        run_sequence=run_sequence,
        request_id=request_id,
        campaign_id=campaign_id,
        ttl_seconds=ttl_seconds,
        registry=registry,
    )


def verify_hip_fgmres_external_signed_evidence_v1(
    envelope_bytes: bytes,
    *,
    challenge: HipFgmresExternalChallengeV1,
    release_binding: HipFgmresExternalReleaseBindingV1,
) -> HipFgmresExternalSignedEvidenceReceiptV1:
    """Verify one envelope against immutable package-owned trust authorities."""

    trust_registry = _TRUST_REGISTRY_LOADER_AUTHORITY()
    validate_hip_fgmres_external_trust_anchor_registry_result_v1(trust_registry)
    fixture_registry = _FIXTURE_REGISTRY_LOADER_AUTHORITY()
    validate_hip_fgmres_fixture_registry_result_v1(fixture_registry)
    return _verify_with_authorities(
        envelope_bytes,
        challenge=challenge,
        release_binding=release_binding,
        trust_registry=trust_registry,
        fixture_registry=fixture_registry,
    )


def validate_hip_fgmres_external_signed_evidence_receipt_v1(
    receipt: HipFgmresExternalSignedEvidenceReceiptV1,
) -> HipFgmresExternalSignedEvidenceReceiptV1:
    """Validate receipt structure without re-creating a consumed challenge."""

    if (
        type(receipt) is not HipFgmresExternalSignedEvidenceReceiptV1
        or type(receipt.verified_slot_ids) is not tuple
        or type(receipt.claims) is not HipFgmresExternalSignedEvidenceClaimsV1
    ):
        _fail("hip_fgmres_external_signed_receipt_type_invalid", "/")
    payload = _verification_receipt_payload(receipt, include_hash=True)
    _validate_json_schema(payload, _RECEIPT_SCHEMA_RESOURCE, path="/receipt")
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1
        or receipt.status != "external_gfx1100_fixed_suite_signed_evidence_verified"
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V1
        or receipt.verified_slot_ids != HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        or receipt.verified_slot_count != len(receipt.verified_slot_ids)
        or receipt.claims != HipFgmresExternalSignedEvidenceClaimsV1()
        or receipt.promotion_eligible is not False
        or receipt.receipt_hash
        != canonical_hash(_verification_receipt_payload(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_external_signed_receipt_semantics_invalid", "/")
    return receipt


def _issue_challenge_with_registry(
    *,
    release_binding: HipFgmresExternalReleaseBindingV1,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    request_id: str,
    campaign_id: str,
    ttl_seconds: int,
    registry: HipFgmresExternalTrustAnchorRegistryResultV1,
    now: datetime | None = None,
) -> HipFgmresExternalChallengeV1:
    validate_hip_fgmres_external_release_binding_v1(release_binding)
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
        _fail("hip_fgmres_external_challenge_request_invalid", "/challenge")
    current = _utc_now() if now is None else _validated_utc_datetime(now, "/now")
    key = _resolve_active_key(
        registry,
        key_id=key_id,
        runner_id=runner_id,
        run_sequence=run_sequence,
        observed_at=current,
    )
    if (
        key.allowed_fixture_registry_bytes_sha256
        != release_binding.fixture_registry_bytes_sha256
        or key.allowed_fixture_registry_hash != release_binding.fixture_registry_hash
    ):
        _fail("hip_fgmres_external_challenge_release_not_allowed", "/release_binding")
    expires_at = current + timedelta(seconds=ttl_seconds)
    if key.valid_until_utc is not None and expires_at > _parse_utc(
        key.valid_until_utc, "/trust_anchor/valid_until_utc"
    ):
        _fail("hip_fgmres_external_trust_anchor_not_active", "/key_id")
    issued = _format_utc(current)
    expires = _format_utc(expires_at)
    nonce = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    unsigned = {
        "schema_version": HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V1,
        "request_id": request_id,
        "audience": _AUDIENCE,
        "campaign_id": campaign_id,
        "nonce_base64": nonce,
        "issued_at_utc": issued,
        "expires_at_utc": expires,
        "expected_key_id": key.key_id,
        "expected_key_epoch": key.key_epoch,
        "expected_runner_id": key.runner_id,
        "expected_run_sequence": run_sequence,
        "expected_release_binding_hash": release_binding.binding_hash,
        "expected_trust_registry_hash": registry.registry_hash,
        "expected_architecture_base": "gfx1100",
        "expected_suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    }
    payload = _ChallengePayloadV1(
        challenge_id=canonical_hash(unsigned),
        **unsigned,
    )
    return HipFgmresExternalChallengeV1(payload, mint=_CHALLENGE_MINT)


def _rehydrate_hip_fgmres_external_challenge_v1(
    payload: dict[str, Any],
) -> HipFgmresExternalChallengeV1:
    """Rehydrate an exact ledger-authorized challenge payload.

    This helper validates serialized structure and issuer invariants only.  Its
    package-private caller remains responsible for establishing that the bytes
    came from an authoritative durable issuance record.
    """

    restored = _validate_stored_challenge_payload_v1(payload)
    return HipFgmresExternalChallengeV1(restored, mint=_CHALLENGE_MINT)


def _validate_stored_challenge_payload_v1(
    payload: dict[str, Any],
) -> _ChallengePayloadV1:
    if type(payload) is not dict:
        _fail("hip_fgmres_external_stored_challenge_type_invalid", "/challenge")
    expected_fields = frozenset(_ChallengePayloadV1.__dataclass_fields__)
    if frozenset(payload) != expected_fields:
        _fail("hip_fgmres_external_stored_challenge_fields_invalid", "/challenge")

    string_fields = (
        "schema_version",
        "challenge_id",
        "request_id",
        "audience",
        "campaign_id",
        "nonce_base64",
        "issued_at_utc",
        "expires_at_utc",
        "expected_key_id",
        "expected_runner_id",
        "expected_release_binding_hash",
        "expected_trust_registry_hash",
        "expected_architecture_base",
        "expected_suite_id",
    )
    for field in string_fields:
        if type(payload[field]) is not str:
            _fail(
                "hip_fgmres_external_stored_challenge_field_invalid",
                f"/challenge/{field}",
            )
    integer_fields = ("expected_key_epoch", "expected_run_sequence")
    for field in integer_fields:
        if type(payload[field]) is not int or payload[field] <= 0:
            _fail(
                "hip_fgmres_external_stored_challenge_field_invalid",
                f"/challenge/{field}",
            )

    if (
        payload["schema_version"] != HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V1
        or _HASH_RE.fullmatch(payload["challenge_id"]) is None
        or _ID_RE.fullmatch(payload["request_id"]) is None
        or payload["audience"] != _AUDIENCE
        or _ID_RE.fullmatch(payload["campaign_id"]) is None
        or _KEY_ID_RE.fullmatch(payload["expected_key_id"]) is None
        or _RUNNER_ID_RE.fullmatch(payload["expected_runner_id"]) is None
        or _HASH_RE.fullmatch(payload["expected_release_binding_hash"]) is None
        or _HASH_RE.fullmatch(payload["expected_trust_registry_hash"]) is None
        or payload["expected_architecture_base"] != "gfx1100"
        or payload["expected_suite_id"] != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or payload["expected_key_id"]
        != (f"ed25519:{payload['expected_runner_id']}:v{payload['expected_key_epoch']}")
    ):
        _fail("hip_fgmres_external_stored_challenge_semantics_invalid", "/challenge")

    try:
        decode_canonical_base64_v1(
            payload["nonce_base64"],
            expected_byte_count=32,
            path="/challenge/nonce_base64",
        )
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_stored_challenge_nonce_invalid",
            "/challenge/nonce_base64",
            exc.code,
        )

    if (
        _UTC_RE.fullmatch(payload["issued_at_utc"]) is None
        or _UTC_RE.fullmatch(payload["expires_at_utc"]) is None
    ):
        _fail("hip_fgmres_external_stored_challenge_timestamp_invalid", "/challenge")
    try:
        issued = _parse_utc(payload["issued_at_utc"], "/challenge/issued_at_utc")
        expires = _parse_utc(payload["expires_at_utc"], "/challenge/expires_at_utc")
    except HipFgmresExternalSignedEvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_stored_challenge_timestamp_invalid",
            exc.path,
            exc.code,
        )
    lifetime = expires - issued
    if (
        lifetime < timedelta(seconds=60)
        or lifetime > timedelta(seconds=3600)
        or lifetime.microseconds != 0
    ):
        _fail("hip_fgmres_external_stored_challenge_timestamp_invalid", "/challenge")

    unsigned = {
        field: payload[field]
        for field in _ChallengePayloadV1.__dataclass_fields__
        if field != "challenge_id"
    }
    if payload["challenge_id"] != canonical_hash(unsigned):
        _fail("hip_fgmres_external_stored_challenge_hash_invalid", "/challenge")

    return _ChallengePayloadV1(**payload)


def _extract_hip_fgmres_external_envelope_routing_v1(
    envelope_bytes: bytes,
) -> dict[str, Any]:
    """Extract strict routing data without asserting signature authority.

    The full returned challenge payload includes ``challenge_id``.  Envelope
    identity hashes and the challenge's own identity are checked, but the
    Ed25519 signature is deliberately not verified at this routing boundary.
    """

    envelope = _parse_canonical_envelope(envelope_bytes)
    _validate_json_schema(envelope, _ENVELOPE_SCHEMA_RESOURCE, path="/envelope")
    signed_payload = _validate_envelope_integrity_v1(envelope)
    challenge_payload = _validate_stored_challenge_payload_v1(
        signed_payload["challenge"]
    )
    return challenge_payload.to_dict()


def _validate_envelope_integrity_v1(
    envelope: dict[str, Any],
) -> dict[str, Any]:
    expected_envelope_hash = canonical_hash(
        {key: value for key, value in envelope.items() if key != "envelope_hash"}
    )
    signed_payload = envelope["signed_payload"]
    if (
        envelope["schema_version"]
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V1
        or envelope["capability_profile"]
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1
        or envelope["algorithm"] != ED25519_ALGORITHM_V1
        or envelope["envelope_hash"] != expected_envelope_hash
        or envelope["signed_payload_sha256"]
        != sha256_prefixed(canonical_json_bytes(signed_payload))
        or signed_payload["payload_schema_version"]
        != HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V1
        or signed_payload["purpose"] != _PURPOSE
        or signed_payload["evidence_scope"]
        != HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCOPE_V1
    ):
        _fail("hip_fgmres_external_envelope_semantics_invalid", "/envelope")
    return signed_payload


def _verify_with_authorities(
    envelope_bytes: bytes,
    *,
    challenge: HipFgmresExternalChallengeV1,
    release_binding: HipFgmresExternalReleaseBindingV1,
    trust_registry: HipFgmresExternalTrustAnchorRegistryResultV1,
    fixture_registry: HipFgmresFixtureRegistryResultV1,
    now: datetime | None = None,
    success_commit_hook: (
        Callable[[HipFgmresExternalSignedEvidenceReceiptV1], None] | None
    ) = None,
) -> HipFgmresExternalSignedEvidenceReceiptV1:
    if type(challenge) is not HipFgmresExternalChallengeV1:
        _fail("hip_fgmres_external_challenge_type_invalid", "/challenge")
    validate_hip_fgmres_external_release_binding_v1(release_binding)
    if type(trust_registry) is not HipFgmresExternalTrustAnchorRegistryResultV1:
        _fail("hip_fgmres_external_trust_registry_type_invalid", "/trust_registry")
    if type(fixture_registry) is not HipFgmresFixtureRegistryResultV1:
        _fail("hip_fgmres_external_fixture_registry_type_invalid", "/fixture_registry")
    if success_commit_hook is not None and not callable(success_commit_hook):
        _fail("hip_fgmres_external_success_commit_hook_invalid", "/commit_hook")
    envelope = _parse_canonical_envelope(envelope_bytes)
    _validate_json_schema(envelope, _ENVELOPE_SCHEMA_RESOURCE, path="/envelope")
    signed_payload = _validate_envelope_integrity_v1(envelope)
    if signed_payload["challenge"] != challenge.to_dict():
        _fail("hip_fgmres_external_challenge_mismatch", "/signed_payload/challenge")
    if signed_payload["release_binding"] != release_binding.to_dict():
        _fail(
            "hip_fgmres_external_release_binding_mismatch",
            "/signed_payload/release_binding",
        )
    challenge_payload = challenge._payload
    runner = signed_payload["runner"]
    if not any(key.key_id == envelope["key_id"] for key in trust_registry.keys):
        _fail("hip_fgmres_external_trust_anchor_not_found", "/key_id")
    if (
        challenge_payload.expected_release_binding_hash != release_binding.binding_hash
        or challenge_payload.expected_trust_registry_hash
        != trust_registry.registry_hash
        or challenge_payload.expected_key_id != envelope["key_id"]
        or challenge_payload.expected_runner_id != runner["runner_id"]
        or challenge_payload.expected_run_sequence != runner["run_sequence"]
        or challenge_payload.expected_architecture_base != runner["architecture_base"]
        or challenge_payload.expected_suite_id
        != signed_payload["fixture_registry"]["suite_id"]
    ):
        _fail("hip_fgmres_external_challenge_binding_invalid", "/challenge")
    current = _utc_now() if now is None else _validated_utc_datetime(now, "/now")
    issued = _parse_utc(challenge_payload.issued_at_utc, "/challenge/issued_at_utc")
    expires = _parse_utc(challenge_payload.expires_at_utc, "/challenge/expires_at_utc")
    started = _parse_utc(runner["started_at_utc"], "/runner/started_at_utc")
    completed = _parse_utc(runner["completed_at_utc"], "/runner/completed_at_utc")
    if not (issued <= started <= completed <= current <= expires):
        _fail("hip_fgmres_external_challenge_expired_or_time_invalid", "/challenge")
    key = _resolve_active_key(
        trust_registry,
        key_id=envelope["key_id"],
        runner_id=runner["runner_id"],
        run_sequence=runner["run_sequence"],
        observed_at=completed,
    )
    if key.key_epoch != challenge_payload.expected_key_epoch:
        _fail("hip_fgmres_external_key_epoch_mismatch", "/key_id")
    reservation = challenge._reserve()
    try:
        signed_content = _signed_content(envelope)
        message = _SIGNATURE_DOMAIN + canonical_json_bytes(signed_content)
        try:
            verify_ed25519_signature_v1(
                public_key=key.public_key_bytes,
                signature_base64=envelope["signature_base64"],
                message=message,
            )
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_signature_invalid", "/signature_base64", exc.code
            )
        _validate_release_against_current_package(release_binding, fixture_registry)
        family_receipt = _parse_family_receipt(signed_payload["family_receipt_v2"])
        _validate_external_family_lane(family_receipt)
        _validate_fixture_registry_block(
            signed_payload["fixture_registry"], fixture_registry
        )
        _validate_runner_binding(runner, family_receipt)
        _validate_cases(
            signed_payload["cases"],
            family_receipt=family_receipt,
            fixture_registry=fixture_registry,
            runner=runner,
            common_runtime_binding_hash=signed_payload["common_runtime_binding_hash"],
            ordered_case_aggregate_hash=signed_payload["ordered_case_aggregate_hash"],
        )
        _validate_payload_claims(signed_payload["claims"])
        draft = HipFgmresExternalSignedEvidenceReceiptV1(
            schema_version=(
                HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V1
            ),
            capability_profile=(
                HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1
            ),
            status="external_gfx1100_fixed_suite_signed_evidence_verified",
            evidence_scope=HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V1,
            envelope_hash=envelope["envelope_hash"],
            signed_payload_sha256=envelope["signed_payload_sha256"],
            key_id=key.key_id,
            key_epoch=key.key_epoch,
            runner_id=key.runner_id,
            run_sequence=runner["run_sequence"],
            challenge_id=challenge.challenge_id,
            release_binding_hash=release_binding.binding_hash,
            trust_registry_hash=trust_registry.registry_hash,
            fixture_registry_hash=fixture_registry.registry_hash,
            family_receipt_hash=family_receipt.receipt_hash,
            common_runtime_binding_hash=signed_payload["common_runtime_binding_hash"],
            ordered_case_aggregate_hash=signed_payload["ordered_case_aggregate_hash"],
            verified_slot_count=len(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
            verified_slot_ids=HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
            claims=HipFgmresExternalSignedEvidenceClaimsV1(),
            promotion_eligible=False,
            receipt_hash=_ZERO_HASH,
        )
        receipt = replace(
            draft,
            receipt_hash=canonical_hash(
                _verification_receipt_payload(draft, include_hash=False)
            ),
        )
        receipt = validate_hip_fgmres_external_signed_evidence_receipt_v1(receipt)
        if success_commit_hook is not None:
            success_commit_hook(receipt)
        challenge._consume(reservation)
    except BaseException:
        challenge._release(reservation)
        raise
    return receipt


def _parse_model_case_receipt(
    payload: dict[str, Any],
) -> HipFgmresModelCaseParityReceiptV1:
    try:
        receipt = HipFgmresModelCaseParityReceiptV1(
            schema_version=payload["schema_version"],
            capability_profile=payload["capability_profile"],
            status=payload["status"],
            evidence_scope=payload["evidence_scope"],
            actual_backend=payload["actual_backend"],
            promotion_eligible=payload["promotion_eligible"],
            case_id=payload["case_id"],
            bindings=HipFgmresModelCaseParityBindingsV1(**payload["bindings"]),
            dimensions=HipFgmresModelCaseParityDimensionsV1(**payload["dimensions"]),
            tolerance=HipFgmresModelCaseParityToleranceV1(**payload["tolerance"]),
            discrete=HipFgmresModelCaseParityDiscreteComparisonV1(
                **payload["discrete"]
            ),
            vectors=tuple(
                HipFgmresModelCaseParityVectorComparisonV1(**row)
                for row in payload["vectors"]
            ),
            telemetry=HipFgmresModelCaseParityTelemetryV1(**payload["telemetry"]),
            claims=HipFgmresModelCaseParityClaimsV1(**payload["claims"]),
            receipt_hash=payload["receipt_hash"],
        )
        return validate_hip_fgmres_model_case_parity_receipt_v1(receipt)
    except Exception as exc:
        _fail(
            "hip_fgmres_external_model_case_receipt_invalid",
            "/cases/model_case_receipt_v1",
            f"{type(exc).__name__}: {exc}",
        )


def _parse_family_receipt(
    payload: dict[str, Any],
) -> HipFgmresModelFamilyParityReceiptV2:
    try:
        coverage_payload = payload["coverage"]
        receipt = HipFgmresModelFamilyParityReceiptV2(
            schema_version=payload["schema_version"],
            capability_profile=payload["capability_profile"],
            status=payload["status"],
            evidence_scope=payload["evidence_scope"],
            registry_bytes_sha256=payload["registry_bytes_sha256"],
            registry_hash=payload["registry_hash"],
            required_architecture_bases=tuple(payload["required_architecture_bases"]),
            required_slot_ids=tuple(payload["required_slot_ids"]),
            observations=tuple(
                HipFgmresModelFamilyObservedCellV2(**row)
                for row in payload["observations"]
            ),
            coverage=HipFgmresModelFamilyCoverageV2(
                required_slot_count=coverage_payload["required_slot_count"],
                required_architecture_count=coverage_payload[
                    "required_architecture_count"
                ],
                expected_matrix_cell_count=coverage_payload[
                    "expected_matrix_cell_count"
                ],
                validated_input_case_count=coverage_payload[
                    "validated_input_case_count"
                ],
                covered_matrix_cell_count=coverage_payload["covered_matrix_cell_count"],
                missing_matrix_cell_count=coverage_payload["missing_matrix_cell_count"],
                covered_cells=tuple(coverage_payload["covered_cells"]),
                missing_cells=tuple(coverage_payload["missing_cells"]),
                observed_architecture_bases=tuple(
                    coverage_payload["observed_architecture_bases"]
                ),
                completed_architecture_bases=tuple(
                    coverage_payload["completed_architecture_bases"]
                ),
                incomplete_architecture_bases=tuple(
                    coverage_payload["incomplete_architecture_bases"]
                ),
            ),
            claims=HipFgmresModelFamilyClaimsV2(**payload["claims"]),
            promotion_eligible=payload["promotion_eligible"],
            receipt_hash=payload["receipt_hash"],
        )
        return validate_hip_fgmres_model_family_parity_receipt_v2(receipt)
    except Exception as exc:
        _fail(
            "hip_fgmres_external_family_receipt_invalid",
            "/signed_payload/family_receipt_v2",
            f"{type(exc).__name__}: {exc}",
        )


def _validate_external_family_lane(
    receipt: HipFgmresModelFamilyParityReceiptV2,
) -> None:
    expected_cells = tuple(
        f"gfx1100:{slot_id}"
        for slot_id in HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    expected_missing = tuple(
        f"gfx1030:{slot_id}"
        for slot_id in HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    if (
        receipt.status != "partial_fixed_suite_hardware_observation"
        or len(receipt.observations) != 10
        or tuple(row.slot_id for row in receipt.observations)
        != HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        or any(
            row.runtime_architecture_base != "gfx1100" for row in receipt.observations
        )
        or receipt.coverage.validated_input_case_count != 10
        or receipt.coverage.covered_matrix_cell_count != 10
        or receipt.coverage.missing_matrix_cell_count != 10
        or receipt.coverage.covered_cells != expected_cells
        or receipt.coverage.missing_cells != expected_missing
        or receipt.coverage.observed_architecture_bases != ("gfx1100",)
        or receipt.coverage.completed_architecture_bases != ("gfx1100",)
        or receipt.coverage.incomplete_architecture_bases != ("gfx1030",)
        or receipt.claims.primary_gfx1030_fixed_suite_complete
        or receipt.claims.unsigned_fixed_suite_two_architecture_matrix_observed
        or receipt.claims.signed_evidence
        or receipt.claims.serialized_external_evidence_counted
        or receipt.promotion_eligible
    ):
        _fail(
            "hip_fgmres_external_family_lane_not_exact_gfx1100_ten",
            "/signed_payload/family_receipt_v2",
        )


def _validate_fixture_registry_block(
    payload: dict[str, Any],
    registry: HipFgmresFixtureRegistryResultV1,
) -> None:
    expected = {
        "suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        "registry_bytes_sha256": registry.registry_bytes_sha256,
        "registry_hash": registry.registry_hash,
        "registry_receipt_hash": registry.receipt_hash,
        "ordered_slot_ids": list(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
    }
    if payload != expected:
        _fail(
            "hip_fgmres_external_fixture_registry_binding_mismatch",
            "/signed_payload/fixture_registry",
        )


def _validate_runner_binding(
    runner: dict[str, Any],
    family_receipt: HipFgmresModelFamilyParityReceiptV2,
) -> None:
    try:
        architecture = normalize_hip_gcn_architecture_v1(
            runner["compiled_architecture"]
        )
        decode_canonical_base64_v1(
            runner["runner_nonce_base64"],
            expected_byte_count=32,
            path="/signed_payload/runner/runner_nonce_base64",
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_external_runner_binding_invalid",
            "/signed_payload/runner",
            f"{type(exc).__name__}: {exc}",
        )
    if architecture.base != "gfx1100" or runner["architecture_base"] != "gfx1100":
        _fail(
            "hip_fgmres_external_runner_architecture_invalid",
            "/signed_payload/runner/compiled_architecture",
        )
    for index, observation in enumerate(family_receipt.observations):
        if (
            observation.runtime_architecture_base != runner["architecture_base"]
            or observation.compiled_architecture != runner["compiled_architecture"]
            or observation.device_ordinal != runner["device_ordinal"]
            or observation.device_uuid_bytes_hex != runner["device_uuid_bytes_hex"]
            or observation.device_pci_bdf != runner["device_pci_bdf"]
            or observation.runtime_library_sha256 != runner["runtime_library_sha256"]
            or observation.kernel_identity_hash != runner["kernel_identity_hash"]
            or observation.kernel_source_sha256 != runner["kernel_source_sha256"]
        ):
            _fail(
                "hip_fgmres_external_runner_family_binding_mismatch",
                f"/signed_payload/family_receipt_v2/observations/{index}",
            )


def _validate_cases(
    case_payloads: list[dict[str, Any]],
    *,
    family_receipt: HipFgmresModelFamilyParityReceiptV2,
    fixture_registry: HipFgmresFixtureRegistryResultV1,
    runner: dict[str, Any],
    common_runtime_binding_hash: str,
    ordered_case_aggregate_hash: str,
) -> None:
    if (
        type(case_payloads) is not list
        or len(case_payloads) != 10
        or tuple(row.get("slot_id") for row in case_payloads)
        != HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
        or len({row.get("slot_id") for row in case_payloads}) != 10
    ):
        _fail("hip_fgmres_external_case_order_invalid", "/signed_payload/cases")
    expected_common = canonical_hash(_runtime_binding_payload(runner))
    if common_runtime_binding_hash != expected_common:
        _fail(
            "hip_fgmres_external_common_runtime_binding_hash_invalid",
            "/signed_payload/common_runtime_binding_hash",
        )
    aggregate_rows: list[dict[str, Any]] = []
    for index, case_payload in enumerate(case_payloads):
        slot = fixture_registry.slot(case_payload["slot_id"])
        observation = family_receipt.observations[index]
        expected_case_hash = canonical_hash(
            {
                key: value
                for key, value in case_payload.items()
                if key != "case_evidence_hash"
            }
        )
        if case_payload["case_evidence_hash"] != expected_case_hash:
            _fail(
                "hip_fgmres_external_case_evidence_hash_invalid",
                f"/signed_payload/cases/{index}/case_evidence_hash",
            )
        receipt = _parse_model_case_receipt(case_payload["model_case_receipt_v1"])
        _validate_one_case(
            case_payload,
            receipt=receipt,
            slot=slot,
            observation=observation,
            runner=runner,
            path=f"/signed_payload/cases/{index}",
        )
        aggregate_rows.append(
            {
                "slot_id": slot.slot_id,
                "slot_registration_hash": slot.slot_registration_hash,
                "case_receipt_hash": receipt.receipt_hash,
                "completion_payload_hash": case_payload["completion_payload_hash"],
                "case_evidence_hash": case_payload["case_evidence_hash"],
            }
        )
    if ordered_case_aggregate_hash != canonical_hash(aggregate_rows):
        _fail(
            "hip_fgmres_external_ordered_case_aggregate_hash_invalid",
            "/signed_payload/ordered_case_aggregate_hash",
        )


def _validate_one_case(
    payload: dict[str, Any],
    *,
    receipt: HipFgmresModelCaseParityReceiptV1,
    slot: HipFgmresFixtureReplayV1,
    observation: HipFgmresModelFamilyObservedCellV2,
    runner: dict[str, Any],
    path: str,
) -> None:
    bindings = receipt.bindings
    plan = slot.execution_plan
    cpu = slot.cpu_result
    policy = slot.policy
    dimensions = receipt.dimensions
    free_dof_count = int(plan.array("free_dofs").size)
    expected_maximum_restarts = slot.recurrence_plan.maximum_restart_count
    if (
        payload["slot_registration_hash"] != slot.slot_registration_hash
        or observation.slot_id != slot.slot_id
        or observation.case_receipt_hash != receipt.receipt_hash
        or observation.case_id != receipt.case_id
        or bindings.model_ir_content_hash != slot.model.content_hash
        or bindings.execution_plan_id != plan.plan_id
        or bindings.execution_plan_hash != plan.plan_hash
        or bindings.operator_hash != plan.operator_hash
        or bindings.numeric_snapshot_hash != plan.numeric_snapshot_hash
        or bindings.symbolic_reuse_hash != plan.symbolic_reuse_hash
        or bindings.partition_hash != plan.partition_hash
        or bindings.load_pattern_id != plan.load_pattern_id
        or bindings.fgmres_plan_id != slot.fgmres_plan.plan_id
        or bindings.fgmres_plan_hash != slot.fgmres_plan.plan_hash
        or bindings.recurrence_plan_id != slot.recurrence_plan.plan_id
        or bindings.recurrence_plan_hash != slot.recurrence_plan.plan_hash
        or bindings.policy_hash != policy.policy_hash
        or bindings.cpu_result_hash != cpu.result_hash
        or bindings.runtime_architecture_base != "gfx1100"
        or bindings.compiled_architecture != runner["compiled_architecture"]
        or bindings.device_ordinal != runner["device_ordinal"]
        or bindings.device_uuid_bytes_hex != runner["device_uuid_bytes_hex"]
        or bindings.device_pci_bdf != runner["device_pci_bdf"]
        or bindings.runtime_library_sha256 != runner["runtime_library_sha256"]
        or bindings.kernel_identity_hash != runner["kernel_identity_hash"]
        or bindings.kernel_source_sha256 != runner["kernel_source_sha256"]
        or dimensions.global_dof_count != plan.dof_count
        or dimensions.free_dof_count != free_dof_count
        or dimensions.reduced_csr_nnz != plan.reduced_nnz
        or dimensions.restart_dimension != policy.restart_dimension
        or dimensions.max_iterations != policy.max_iterations
        or dimensions.maximum_restart_count != expected_maximum_restarts
        or dimensions.populated_restart_row_count != len(cpu.history)
    ):
        _fail("hip_fgmres_external_case_registry_binding_invalid", path)
    observation_fields = {
        "model_ir_content_hash": bindings.model_ir_content_hash,
        "execution_plan_hash": bindings.execution_plan_hash,
        "fgmres_plan_hash": bindings.fgmres_plan_hash,
        "recurrence_plan_hash": bindings.recurrence_plan_hash,
        "policy_hash": bindings.policy_hash,
        "cpu_result_hash": bindings.cpu_result_hash,
        "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
    }
    if any(
        getattr(observation, name) != value
        for name, value in observation_fields.items()
    ):
        _fail("hip_fgmres_external_case_family_binding_invalid", path)
    solution_x = _decode_case_base64(
        payload["solution_x_base64"], 8 * free_dof_count, f"{path}/solution_x_base64"
    )
    true_residual = _decode_case_base64(
        payload["true_residual_base64"],
        8 * free_dof_count,
        f"{path}/true_residual_base64",
    )
    solve_record = _decode_case_base64(
        payload["solve_record_base64"],
        192 + 72 * expected_maximum_restarts,
        f"{path}/solve_record_base64",
    )
    completion_hash = _bundle_hash((solution_x, true_residual, solve_record))
    if (
        payload["completion_payload_hash"] != completion_hash
        or bindings.completion_export_payload_hash != completion_hash
    ):
        _fail("hip_fgmres_external_completion_payload_hash_invalid", path)
    policy_snapshot = HipFgmresTerminalOutcomePolicySnapshotV1(
        restart_dimension=policy.restart_dimension,
        max_iterations=policy.max_iterations,
        maximum_restart_count=expected_maximum_restarts,
        stagnation_checkpoint_limit=policy.stagnation_checkpoint_limit,
        absolute_tolerance=policy.absolute_tolerance,
        relative_tolerance=policy.relative_tolerance,
        authoritative_tolerance=plan.residual_tolerance,
        stagnation_relative_tolerance=policy.stagnation_relative_tolerance,
        divergence_factor=policy.divergence_factor,
    )
    try:
        outcome = decode_hip_fgmres_detached_completion_payload_v1(
            solution_x=solution_x,
            true_residual=true_residual,
            solve_record=solve_record,
            free_dof_count=free_dof_count,
            maximum_restart_count=expected_maximum_restarts,
            policy=policy_snapshot,
        )
        vectors = replay_hip_fgmres_detached_model_case_numerics_v1(
            execution_plan=plan,
            cpu_result=cpu,
            solution_x=solution_x,
            true_residual=true_residual,
            outcome=outcome,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_external_detached_numerical_replay_failed",
            path,
            f"{type(exc).__name__}: {exc}",
        )
    if receipt.vectors != vectors:
        _fail(
            "hip_fgmres_external_case_vector_receipt_mismatch",
            f"{path}/model_case_receipt_v1/vectors",
        )


def _validate_release_against_current_package(
    binding: HipFgmresExternalReleaseBindingV1,
    registry: HipFgmresFixtureRegistryResultV1,
) -> None:
    count, manifest_hash = _schema_manifest_identity()
    try:
        current_version = metadata.version(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError as exc:
        _fail(
            "hip_fgmres_external_release_distribution_missing",
            "/distribution",
            str(exc),
        )
    if (
        binding.distribution_version != current_version
        or binding.schema_manifest_count != count
        or binding.schema_manifest_hash != manifest_hash
        or binding.fixture_registry_bytes_sha256 != registry.registry_bytes_sha256
        or binding.fixture_registry_hash != registry.registry_hash
        or binding.fixture_registry_receipt_hash != registry.receipt_hash
    ):
        _fail(
            "hip_fgmres_external_release_current_package_mismatch", "/release_binding"
        )


def _validate_payload_claims(claims: dict[str, Any]) -> None:
    expected = {
        "runner_attests_actual_native_hip_execution": True,
        "runner_attests_external_gfx1100_fixed_suite": True,
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
        _fail("hip_fgmres_external_payload_claims_invalid", "/signed_payload/claims")


def _resolve_active_key(
    registry: HipFgmresExternalTrustAnchorRegistryResultV1,
    *,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    observed_at: datetime,
) -> HipFgmresExternalTrustAnchorV1:
    matches = tuple(key for key in registry.keys if key.key_id == key_id)
    if len(matches) != 1:
        _fail("hip_fgmres_external_trust_anchor_not_found", "/key_id")
    key = matches[0]
    valid_from = _parse_utc(key.valid_from_utc, "/trust_anchor/valid_from_utc")
    valid_until = (
        None
        if key.valid_until_utc is None
        else _parse_utc(key.valid_until_utc, "/trust_anchor/valid_until_utc")
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
        _fail("hip_fgmres_external_trust_anchor_not_active", "/key_id")
    return key


def _signed_content(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": envelope["schema_version"],
        "capability_profile": envelope["capability_profile"],
        "algorithm": envelope["algorithm"],
        "key_id": envelope["key_id"],
        "signed_payload_sha256": envelope["signed_payload_sha256"],
        "signed_payload": envelope["signed_payload"],
    }


def _runtime_binding_payload(runner: dict[str, Any]) -> dict[str, Any]:
    names = (
        "runner_id",
        "architecture_base",
        "compiled_architecture",
        "device_ordinal",
        "device_uuid_bytes_hex",
        "device_pci_bdf",
        "device_name",
        "rocm_version",
        "driver_version",
        "hiprtc_version",
        "runtime_library_sha256",
        "runtime_dependency_manifest_hash",
        "kernel_identity_hash",
        "kernel_source_sha256",
        "kernel_code_object_sha256",
    )
    return {name: runner[name] for name in names}


def _release_payload(
    binding: HipFgmresExternalReleaseBindingV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        name: getattr(binding, name)
        for name in binding.__dataclass_fields__
        if name != "binding_hash"
    }
    if include_hash:
        payload["binding_hash"] = binding.binding_hash
    return payload


def _verification_receipt_payload(
    receipt: HipFgmresExternalSignedEvidenceReceiptV1,
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


def _schema_manifest_identity() -> tuple[int, str]:
    schema_root = resources.files("structural_analysis.schemas")
    rows = []
    for resource in sorted(schema_root.iterdir(), key=lambda item: item.name):
        if resource.is_file() and resource.name.endswith(".json"):
            raw = resource.read_bytes()
            rows.append(
                {
                    "resource_name": resource.name,
                    "byte_count": len(raw),
                    "bytes_sha256": sha256_prefixed(raw),
                }
            )
    if not rows:
        _fail("hip_fgmres_external_schema_manifest_empty", "/schemas")
    return len(rows), canonical_hash(rows)


def _parse_canonical_envelope(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _ENVELOPE_MAX_BYTES:
        _fail("hip_fgmres_external_envelope_extent_invalid", "/envelope")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_external_envelope_bom_forbidden", "/envelope")

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
        _reject_nonfinite(payload, path="/envelope")
        canonical = canonical_json_bytes(payload)
    except _DuplicateKeyError as exc:
        _fail(
            "hip_fgmres_external_envelope_duplicate_key",
            "/envelope",
            str(exc)[:256],
        )
    except RecursionError:
        _fail("hip_fgmres_external_envelope_extent_invalid", "/envelope")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        _fail("hip_fgmres_external_envelope_json_invalid", "/envelope", str(exc))
    if type(payload) is not dict:
        _fail("hip_fgmres_external_envelope_root_invalid", "/envelope")
    if raw != canonical:
        _fail("hip_fgmres_external_envelope_not_canonical", "/envelope")
    return payload


def _reject_nonfinite(value: Any, *, path: str) -> None:
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    node_count = 0
    while stack:
        item, item_path, depth = stack.pop()
        node_count += 1
        if node_count > _ENVELOPE_MAX_JSON_NODES or depth > _ENVELOPE_MAX_JSON_DEPTH:
            _fail("hip_fgmres_external_envelope_extent_invalid", item_path)
        if type(item) is float and not math.isfinite(item):
            _fail("hip_fgmres_external_envelope_nonfinite", item_path)
        if type(item) is dict:
            for key, child in item.items():
                stack.append((child, f"{item_path}/{key}", depth + 1))
        elif type(item) is list:
            for index, child in enumerate(item):
                stack.append((child, f"{item_path}/{index}", depth + 1))


def _validate_json_schema(
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
    except Exception as exc:
        _fail(
            "hip_fgmres_external_schema_invalid", path, f"{type(exc).__name__}: {exc}"
        )
    error = next(Draft202012Validator(schema).iter_errors(payload), None)
    if error is not None:
        location = (
            path.rstrip("/") + "/" + "/".join(str(part) for part in error.absolute_path)
        )
        keyword = str(error.validator)
        if len(keyword) > 64:
            keyword = keyword[:64]
        _fail(
            "hip_fgmres_external_schema_validation_failed",
            location,
            f"schema keyword {keyword} rejected value",
        )


def _decode_case_base64(value: str, byte_count: int, path: str) -> bytes:
    try:
        return decode_canonical_base64_v1(
            value,
            expected_byte_count=byte_count,
            path=path,
        )
    except Ed25519EvidenceV1Error as exc:
        _fail("hip_fgmres_external_case_base64_invalid", path, exc.code)


def _parse_utc(value: str, path: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail("hip_fgmres_external_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        _fail("hip_fgmres_external_timestamp_invalid", path, str(exc))
    return _validated_utc_datetime(parsed, path)


def _validated_utc_datetime(value: datetime, path: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail("hip_fgmres_external_timestamp_invalid", path)
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    checked = _validated_utc_datetime(value, "/time")
    return checked.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalSignedEvidenceV1Error(code, path, message)


# Capture the package loaders before public names can be rebound.  The trusted
# installed package/interpreter remains an explicit boundary; arbitrary code
# execution inside the same process is outside this pure-Python contract.
_TRUST_REGISTRY_LOADER_AUTHORITY = load_hip_fgmres_external_trust_anchor_registry_v1
_FIXTURE_REGISTRY_LOADER_AUTHORITY = load_hip_fgmres_fixture_registry_v1


__all__ = [
    "HIP_FGMRES_EXTERNAL_CHALLENGE_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_RELEASE_BINDING_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V1",
    "HipFgmresExternalChallengeV1",
    "HipFgmresExternalReleaseBindingV1",
    "HipFgmresExternalSignedEvidenceClaimsV1",
    "HipFgmresExternalSignedEvidenceReceiptV1",
    "HipFgmresExternalSignedEvidenceV1Error",
    "compile_hip_fgmres_external_release_binding_v1",
    "issue_hip_fgmres_external_evidence_challenge_v1",
    "validate_hip_fgmres_external_release_binding_v1",
    "validate_hip_fgmres_external_signed_evidence_receipt_v1",
    "verify_hip_fgmres_external_signed_evidence_v1",
]
