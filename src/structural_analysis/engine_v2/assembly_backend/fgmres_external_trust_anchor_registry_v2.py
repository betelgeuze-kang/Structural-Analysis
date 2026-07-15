"""Event-sourced package trust anchors for external gfx1100 evidence.

The public loader has no caller-controlled path.  It accepts only the exact
package resource whose raw bytes and schema bytes are anchored in this module.
Runner-key state is derived by replaying the append-only event history; no
mutable key-state object is accepted as authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from importlib import import_module, resources
import json
import math
import re
from typing import Any, Callable, Literal, NoReturn

from jsonschema import Draft202012Validator, SchemaError

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)
from structural_analysis.engine_v2.evidence.ed25519_v1 import (
    Ed25519EvidenceV1Error,
    decode_canonical_base64_v1,
    validate_ed25519_public_key_v1,
    verify_ed25519_signature_v1,
)


HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-external-trust-anchor-registry.v2"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2 = (
    "phase0_external_gfx1100_reviewed_ed25519_trust_lifecycle"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2 = (
    "package_owned_event_sourced_trust_lifecycle_non_promoting"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2 = (
    "structural-analysis-engine-v2-external-trust-registry"
)

_EVENT_ACTION_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-trust-registry-event-action.v2"
)
_REVIEW_SIGNATURE_DOMAIN_V2 = (
    b"structural-analysis/hip-fgmres/trust-registry-review/v2\x00"
)
_RESOURCE_PACKAGE_V2 = (
    "structural_analysis.engine_v2.assembly_backend.fixtures."
    "fgmres_external_trust_anchors_v2"
)
_REGISTRY_RESOURCE_V2 = "registry.v2.json"
_SCHEMA_RESOURCE_V2 = "hip_fgmres_external_trust_anchor_registry_v2.schema.json"

_SCHEMA_RESOURCE_BYTES_SHA256_V2 = (
    "sha256:d8ed736d9c98959d18a50467e3e0a919504c538dd44e510ee83b0ff016278c6e"
)
_REGISTRY_RESOURCE_BYTES_SHA256_V2 = (
    "sha256:dfa6172c8819f812d9992f64e6e3d5fa0f97e7c2651b49ca7ee47ccc557a2fbc"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUNNER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_KEY_ID_RE = re.compile(r"^ed25519:[a-z0-9][a-z0-9._-]{2,63}:v[1-9][0-9]*$")
_REVIEWER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_REVIEWER_KEY_ID_RE = re.compile(
    r"^ed25519-review:[a-z0-9][a-z0-9._-]{2,63}:v[1-9][0-9]*$"
)
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z$"
)
_MAX_REGISTRY_BYTES = 4 * 1024 * 1024
_MAX_JSON_NODES = 250_000
_MAX_JSON_DEPTH = 64
_MAX_ERROR_PATH_CHARS = 512
_MAX_ERROR_MESSAGE_CHARS = 240
_MAX_REGISTRY_EPOCH_V2 = 100_000
_MAX_RUN_SEQUENCE_V2 = 9_223_372_036_854_775_807
_MAX_REVIEWER_AUTHORITIES_V2 = 32
_MAX_KEY_ID_CHARS_V2 = 128
_MAX_RUNNER_ID_CHARS_V2 = 64
_MAX_REVIEWER_ID_CHARS_V2 = 128
_MAX_SUITE_ID_CHARS_V2 = 256
_ED25519_PUBLIC_KEY_BASE64_CHARS_V2 = 44


def _is_hash_v2(value: Any) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


class HipFgmresExternalTrustAnchorRegistryV2Error(RuntimeError):
    """Stable fail-closed v2 trust-registry error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = _bounded_path(path)
        self.message = (message or code)[:_MAX_ERROR_MESSAGE_CHARS]
        super().__init__(f"{code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustReviewerAuthorityV2:
    reviewer_id: str
    key_id: str
    key_epoch: int
    public_key_base64: str
    public_key_sha256: str
    valid_from_utc: str
    valid_until_utc: str

    @property
    def public_key_bytes(self) -> bytes:
        if (
            type(self.public_key_base64) is not str
            or len(self.public_key_base64) != _ED25519_PUBLIC_KEY_BASE64_CHARS_V2
        ):
            _fail(
                "hip_fgmres_external_trust_registry_v2_reviewer_key_invalid",
                "/reviewer_authority/public_key_base64",
            )
        try:
            return validate_ed25519_public_key_v1(
                decode_canonical_base64_v1(
                    self.public_key_base64,
                    expected_byte_count=32,
                    path="/reviewer_authority/public_key_base64",
                )
            )
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_trust_registry_v2_reviewer_key_invalid",
                "/reviewer_authority/public_key_base64",
                exc.code,
            )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorV2:
    key_id: str
    key_epoch: int
    status: Literal["enrolled", "active", "retired", "revoked"]
    runner_id: str
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
    enrollment_receipt_hash: str
    enrollment_event_hash: str
    activation_event_hash: str | None
    activated_at_utc: str | None
    terminal_event_hash: str | None
    terminal_at_utc: str | None
    revocation_effect: Literal["prospective", "retroactive"] | None
    terminal_reason: str | None

    @property
    def public_key_bytes(self) -> bytes:
        if (
            type(self.public_key_base64) is not str
            or len(self.public_key_base64) != _ED25519_PUBLIC_KEY_BASE64_CHARS_V2
        ):
            _fail(
                "hip_fgmres_external_trust_registry_v2_runner_key_invalid",
                "/keys/public_key_base64",
            )
        try:
            return validate_ed25519_public_key_v1(
                decode_canonical_base64_v1(
                    self.public_key_base64,
                    expected_byte_count=32,
                    path="/keys/public_key_base64",
                )
            )
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_trust_registry_v2_runner_key_invalid",
                "/keys/public_key_base64",
                exc.code,
            )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorRegistryClaimsV2:
    package_owned_registry_loaded: Literal[True] = True
    code_anchored_raw_registry_verified: Literal[True] = True
    canonical_append_only_event_history_verified: Literal[True] = True
    all_enrolled_key_proof_of_possession_receipts_verified: Literal[True] = True
    all_non_init_package_reviewer_signatures_verified: Literal[True] = True
    key_lifecycle_derived_from_events: Literal[True] = True
    operational_reviewer_bootstrap_verified: Literal[False] = False
    private_keys_packaged: Literal[False] = False
    reviewer_human_identity_verified: Literal[False] = False
    reviewer_hsm_verified: Literal[False] = False
    runner_key_hsm_verified: Literal[False] = False
    vendor_attestation_verified: Literal[False] = False
    hardware_execution_verified: Literal[False] = False
    external_monotonic_anchor_verified: Literal[False] = False
    historical_recovery_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False
    commercial_ready: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _claims_are_exact_v2(value: Any) -> bool:
    if type(value) is not HipFgmresExternalTrustAnchorRegistryClaimsV2:
        return False
    expected = HipFgmresExternalTrustAnchorRegistryClaimsV2()
    return all(
        getattr(value, name) is getattr(expected, name)
        for name in expected.__dataclass_fields__
    )


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorRegistryResultV2:
    registry_bytes_sha256: str
    registry_hash: str
    registry_epoch: int
    predecessor_registry_epoch: int
    predecessor_registry_hash: str | None
    head_event_hash: str
    event_count: int
    reviewer_authorities: tuple[HipFgmresExternalTrustReviewerAuthorityV2, ...]
    keys: tuple[HipFgmresExternalTrustAnchorV2, ...]
    claims: HipFgmresExternalTrustAnchorRegistryClaimsV2
    receipt_hash: str

    @property
    def active_key_count(self) -> int:
        return sum(key.status == "active" for key in self.keys)

    @property
    def enrolled_key_count(self) -> int:
        return len(self.keys)

    def to_dict(self) -> dict[str, Any]:
        _validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(self)
        return _result_payload_v2(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class _EnrollmentViewV2:
    key_id: str
    key_epoch: int
    runner_id: str
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
    predecessor_registry_epoch: int
    predecessor_registry_hash: str
    target_registry_epoch: int
    predecessor_key_id: str | None
    predecessor_key_epoch: int | None
    predecessor_public_key_sha256: str | None
    predecessor_maximum_run_sequence: int | None
    receipt_hash: str


@dataclass(slots=True)
class _MutableKeyV2:
    enrollment: _EnrollmentViewV2
    enrollment_event_hash: str
    status: str = "enrolled"
    activation_event_hash: str | None = None
    activated_at_utc: str | None = None
    terminal_event_hash: str | None = None
    terminal_at_utc: str | None = None
    revocation_effect: str | None = None
    terminal_reason: str | None = None


class _DuplicateKeyError(ValueError):
    pass


EnrollmentReceiptValidatorV2 = Callable[[dict[str, Any]], Any]


def load_hip_fgmres_external_trust_anchor_registry_v2() -> (
    HipFgmresExternalTrustAnchorRegistryResultV2
):
    """Load the one immutable package registry; no caller path is accepted."""

    return _TRUST_REGISTRY_LOADER_AUTHORITY_V2()


def validate_hip_fgmres_external_trust_anchor_registry_result_v2(
    result: HipFgmresExternalTrustAnchorRegistryResultV2,
) -> HipFgmresExternalTrustAnchorRegistryResultV2:
    """Require an exact replay of the current code-anchored package registry."""

    _validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(result)
    expected = _TRUST_REGISTRY_LOADER_AUTHORITY_V2()
    if result != expected:
        _fail("hip_fgmres_external_trust_registry_v2_package_replay_mismatch", "/")
    return result


def _compile_hip_fgmres_external_trust_anchor_registry_snapshot_v2(
    manifest: dict[str, Any],
    *,
    registry_bytes_sha256: str,
    enrollment_receipt_validator: EnrollmentReceiptValidatorV2 | None = None,
) -> HipFgmresExternalTrustAnchorRegistryResultV2:
    """Compile one structural snapshot for focused tests and verifier adapters."""

    if type(manifest) is not dict or not _is_hash_v2(registry_bytes_sha256):
        _fail("hip_fgmres_external_trust_registry_v2_snapshot_invalid", "/")
    _validate_schema_v2(manifest)
    declared_hash = manifest["registry_hash"]
    if (
        manifest["schema_version"]
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2
        or manifest["capability_profile"]
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2
        or manifest["evidence_scope"]
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2
    ):
        _fail("hip_fgmres_external_trust_registry_v2_semantics_invalid", "/")

    reviewers = tuple(
        HipFgmresExternalTrustReviewerAuthorityV2(**row)
        for row in manifest["reviewer_authorities"]
    )
    _validate_reviewer_authorities_v2(reviewers)
    prefix_hashes = _registry_prefix_hashes_v2(
        events=manifest["events"],
        reviewers=reviewers,
    )
    if declared_hash != prefix_hashes[-1]:
        _fail(
            "hip_fgmres_external_trust_registry_v2_content_hash_mismatch",
            "/registry_hash",
        )
    expected_predecessor_hash = None if len(prefix_hashes) == 1 else prefix_hashes[-2]
    if manifest["predecessor_registry_hash"] != expected_predecessor_hash:
        _fail(
            "hip_fgmres_external_trust_registry_v2_registry_lineage_invalid",
            "/predecessor_registry_hash",
        )
    keys, head_hash = _replay_events_v2(
        manifest["events"],
        reviewers=reviewers,
        enrollment_receipt_validator=enrollment_receipt_validator,
        prefix_hashes=prefix_hashes,
    )
    if (
        manifest["registry_epoch"] != len(manifest["events"])
        or (
            manifest["registry_epoch"] == 1
            and (
                manifest["predecessor_registry_epoch"] != 0
                or manifest["predecessor_registry_hash"] is not None
            )
        )
        or (
            manifest["registry_epoch"] > 1
            and (
                manifest["predecessor_registry_epoch"] != manifest["registry_epoch"] - 1
                or type(manifest["predecessor_registry_hash"]) is not str
                or _HASH_RE.fullmatch(manifest["predecessor_registry_hash"]) is None
            )
        )
    ):
        _fail(
            "hip_fgmres_external_trust_registry_v2_epoch_head_mismatch",
            "/registry_epoch",
        )
    draft = HipFgmresExternalTrustAnchorRegistryResultV2(
        registry_bytes_sha256=registry_bytes_sha256,
        registry_hash=declared_hash,
        registry_epoch=manifest["registry_epoch"],
        predecessor_registry_epoch=manifest["predecessor_registry_epoch"],
        predecessor_registry_hash=manifest["predecessor_registry_hash"],
        head_event_hash=head_hash,
        event_count=len(manifest["events"]),
        reviewer_authorities=reviewers,
        keys=keys,
        claims=HipFgmresExternalTrustAnchorRegistryClaimsV2(),
        receipt_hash=_ZERO_HASH,
    )
    result = replace(
        draft,
        receipt_hash=canonical_hash(_result_payload_v2(draft, include_hash=False)),
    )
    return _validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
        result
    )


def _validate_hip_fgmres_external_trust_anchor_registry_snapshot_v2(
    manifest: dict[str, Any],
    *,
    registry_bytes_sha256: str,
    enrollment_receipt_validator: EnrollmentReceiptValidatorV2 | None = None,
) -> HipFgmresExternalTrustAnchorRegistryResultV2:
    """Private structural validator used by signed-verifier integration/tests."""

    return _compile_hip_fgmres_external_trust_anchor_registry_snapshot_v2(
        manifest,
        registry_bytes_sha256=registry_bytes_sha256,
        enrollment_receipt_validator=enrollment_receipt_validator,
    )


def _validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
    result: HipFgmresExternalTrustAnchorRegistryResultV2,
) -> HipFgmresExternalTrustAnchorRegistryResultV2:
    if (
        type(result) is not HipFgmresExternalTrustAnchorRegistryResultV2
        or type(result.reviewer_authorities) is not tuple
        or len(result.reviewer_authorities) > _MAX_REVIEWER_AUTHORITIES_V2
        or type(result.keys) is not tuple
        or type(result.claims) is not HipFgmresExternalTrustAnchorRegistryClaimsV2
        or any(
            type(item) is not HipFgmresExternalTrustReviewerAuthorityV2
            for item in result.reviewer_authorities
        )
        or any(type(item) is not HipFgmresExternalTrustAnchorV2 for item in result.keys)
        or any(
            not _is_hash_v2(value)
            for value in (
                result.registry_bytes_sha256,
                result.registry_hash,
                result.head_event_hash,
                result.receipt_hash,
            )
        )
        or type(result.registry_epoch) is not int
        or result.registry_epoch <= 0
        or result.registry_epoch > _MAX_REGISTRY_EPOCH_V2
        or type(result.predecessor_registry_epoch) is not int
        or result.predecessor_registry_epoch != result.registry_epoch - 1
        or (result.registry_epoch == 1 and result.predecessor_registry_hash is not None)
        or (
            result.registry_epoch > 1
            and (not _is_hash_v2(result.predecessor_registry_hash))
        )
        or type(result.event_count) is not int
        or result.event_count != result.registry_epoch
        or len(result.keys) > result.event_count - 1
        or not _claims_are_exact_v2(result.claims)
    ):
        _fail("hip_fgmres_external_trust_registry_v2_result_invalid", "/")
    # Reject hostile detached runner-key extents before decoding any unrelated
    # reviewer key.  This keeps the result boundary fail-closed without letting
    # oversized attacker-controlled fields reach the base64 decoder.
    _validate_derived_keys_v2(result.keys)
    _validate_reviewer_authorities_v2(result.reviewer_authorities)
    if not {
        reviewer.public_key_sha256 for reviewer in result.reviewer_authorities
    }.isdisjoint(key.public_key_sha256 for key in result.keys):
        _fail("hip_fgmres_external_trust_registry_v2_result_invalid", "/")
    if result.receipt_hash != canonical_hash(
        _result_payload_v2(result, include_hash=False)
    ):
        _fail("hip_fgmres_external_trust_registry_v2_result_invalid", "/")
    return result


def _load_package_registry_v2() -> HipFgmresExternalTrustAnchorRegistryResultV2:
    raw = _read_fixed_resource_v2()
    if sha256_prefixed(raw) != _REGISTRY_RESOURCE_BYTES_SHA256_V2:
        _fail(
            "hip_fgmres_external_trust_registry_v2_resource_hash_mismatch",
            "/registry",
        )
    manifest = _parse_strict_object_v2(raw, path="/registry")
    return _compile_hip_fgmres_external_trust_anchor_registry_snapshot_v2(
        manifest,
        registry_bytes_sha256=_REGISTRY_RESOURCE_BYTES_SHA256_V2,
    )


def _validate_reviewer_authorities_v2(
    reviewers: tuple[HipFgmresExternalTrustReviewerAuthorityV2, ...],
) -> None:
    if type(reviewers) is not tuple or len(reviewers) > _MAX_REVIEWER_AUTHORITIES_V2:
        _fail(
            "hip_fgmres_external_trust_registry_v2_reviewer_invalid",
            "/reviewer_authorities",
        )
    ids: set[str] = set()
    key_ids: set[str] = set()
    public_hashes: set[str] = set()
    previous_sort_key: tuple[str, int] | None = None
    for index, reviewer in enumerate(reviewers):
        path = f"/reviewer_authorities/{index}"
        if (
            type(reviewer) is not HipFgmresExternalTrustReviewerAuthorityV2
            or type(reviewer.reviewer_id) is not str
            or not 1 <= len(reviewer.reviewer_id) <= _MAX_REVIEWER_ID_CHARS_V2
            or type(reviewer.key_id) is not str
            or not 1 <= len(reviewer.key_id) <= _MAX_KEY_ID_CHARS_V2
            or type(reviewer.key_epoch) is not int
            or not 1 <= reviewer.key_epoch <= _MAX_REGISTRY_EPOCH_V2
            or type(reviewer.public_key_base64) is not str
            or len(reviewer.public_key_base64) != _ED25519_PUBLIC_KEY_BASE64_CHARS_V2
            or not _is_hash_v2(reviewer.public_key_sha256)
            or type(reviewer.valid_from_utc) is not str
            or type(reviewer.valid_until_utc) is not str
        ):
            _fail("hip_fgmres_external_trust_registry_v2_reviewer_invalid", path)
        public_key = reviewer.public_key_bytes
        valid_from = _parse_utc_v2(reviewer.valid_from_utc, f"{path}/valid_from_utc")
        valid_until = _parse_utc_v2(reviewer.valid_until_utc, f"{path}/valid_until_utc")
        sort_key = (reviewer.reviewer_id, reviewer.key_epoch)
        if (
            _REVIEWER_ID_RE.fullmatch(reviewer.reviewer_id) is None
            or _REVIEWER_KEY_ID_RE.fullmatch(reviewer.key_id) is None
            or reviewer.key_id
            != f"ed25519-review:{reviewer.reviewer_id}:v{reviewer.key_epoch}"
            or sha256_prefixed(public_key) != reviewer.public_key_sha256
            or reviewer.reviewer_id in ids
            or reviewer.key_id in key_ids
            or reviewer.public_key_sha256 in public_hashes
            or valid_until <= valid_from
            or (previous_sort_key is not None and sort_key <= previous_sort_key)
        ):
            _fail("hip_fgmres_external_trust_registry_v2_reviewer_invalid", path)
        ids.add(reviewer.reviewer_id)
        key_ids.add(reviewer.key_id)
        public_hashes.add(reviewer.public_key_sha256)
        previous_sort_key = sort_key


def _replay_events_v2(
    events: list[dict[str, Any]],
    *,
    reviewers: tuple[HipFgmresExternalTrustReviewerAuthorityV2, ...],
    enrollment_receipt_validator: EnrollmentReceiptValidatorV2 | None,
    prefix_hashes: tuple[str, ...],
) -> tuple[tuple[HipFgmresExternalTrustAnchorV2, ...], str]:
    if type(events) is not list or not events:
        _fail("hip_fgmres_external_trust_registry_v2_event_history_invalid", "/events")
    by_reviewer = {reviewer.reviewer_id: reviewer for reviewer in reviewers}
    keys: dict[str, _MutableKeyV2] = {}
    runner_predecessors: dict[str, _EnrollmentViewV2] = {}
    active_key_by_runner: dict[str, str] = {}
    public_hashes = {reviewer.public_key_sha256 for reviewer in reviewers}
    previous_hash: str | None = None
    previous_occurred_at: datetime | None = None
    registry_id: str | None = None
    minimum_approvals = 2

    for index, event in enumerate(events):
        path = f"/events/{index}"
        if type(event) is not dict or event["sequence"] != index + 1:
            _fail("hip_fgmres_external_trust_registry_v2_event_sequence_invalid", path)
        if event["previous_event_hash"] != previous_hash:
            _fail(
                "hip_fgmres_external_trust_registry_v2_event_predecessor_invalid",
                f"{path}/previous_event_hash",
            )
        expected_event_hash = canonical_hash(
            {name: value for name, value in event.items() if name != "event_hash"}
        )
        if event["event_hash"] != expected_event_hash:
            _fail(
                "hip_fgmres_external_trust_registry_v2_event_hash_invalid",
                f"{path}/event_hash",
            )
        occurred_at = _parse_utc_v2(event["occurred_at_utc"], f"{path}/occurred_at_utc")
        if previous_occurred_at is not None and occurred_at <= previous_occurred_at:
            _fail(
                "hip_fgmres_external_trust_registry_v2_event_time_invalid",
                f"{path}/occurred_at_utc",
            )
        event_type = event["event_type"]
        if index == 0:
            if (
                event_type != "registry_initialized"
                or event["approvals"] != []
                or event["action"]["registry_id"]
                != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2
                or event["action"]["reviewer_authority_count"] != len(reviewers)
                or event["action"]["reviewer_authority_commitment_hash"]
                != canonical_hash([item.to_dict() for item in reviewers])
            ):
                _fail(
                    "hip_fgmres_external_trust_registry_v2_initial_event_invalid", path
                )
            registry_id = event["action"]["registry_id"]
            minimum_approvals = event["action"]["minimum_reviewer_approvals"]
        else:
            if event_type == "registry_initialized" or registry_id is None:
                _fail(
                    "hip_fgmres_external_trust_registry_v2_event_history_invalid", path
                )
            _verify_event_approvals_v2(
                event,
                registry_id=registry_id,
                occurred_at=occurred_at,
                minimum_approvals=minimum_approvals,
                reviewers=by_reviewer,
                path=path,
            )
            if event_type == "key_enrolled":
                enrollment = _validated_enrollment_view_v2(
                    event["action"]["enrollment_receipt"],
                    validator=enrollment_receipt_validator,
                    path=f"{path}/action/enrollment_receipt",
                )
                _apply_enrollment_v2(
                    enrollment,
                    event=event,
                    expected_predecessor_registry_hash=prefix_hashes[index - 1],
                    keys=keys,
                    runner_predecessors=runner_predecessors,
                    public_hashes=public_hashes,
                    path=path,
                )
            elif event_type == "key_activated":
                _apply_activation_v2(
                    event,
                    keys=keys,
                    active_key_by_runner=active_key_by_runner,
                    path=path,
                )
            elif event_type == "key_rotated":
                _apply_rotation_v2(
                    event,
                    keys=keys,
                    active_key_by_runner=active_key_by_runner,
                    path=path,
                )
            elif event_type == "key_retired":
                _apply_retirement_v2(
                    event,
                    keys=keys,
                    active_key_by_runner=active_key_by_runner,
                    path=path,
                )
            elif event_type == "key_revoked":
                _apply_revocation_v2(
                    event,
                    keys=keys,
                    active_key_by_runner=active_key_by_runner,
                    path=path,
                )
            else:
                _fail(
                    "hip_fgmres_external_trust_registry_v2_event_type_invalid",
                    f"{path}/event_type",
                )
        previous_hash = event["event_hash"]
        previous_occurred_at = occurred_at

    # Dict insertion order is the validated key_enrolled event order, so the
    # deterministic result needs one O(K) materialization and no final sort.
    anchors = tuple(_freeze_key_v2(value) for value in keys.values())
    _validate_derived_keys_v2(anchors)
    return anchors, previous_hash or _ZERO_HASH


def _verify_event_approvals_v2(
    event: dict[str, Any],
    *,
    registry_id: str,
    occurred_at: datetime,
    minimum_approvals: int,
    reviewers: dict[str, HipFgmresExternalTrustReviewerAuthorityV2],
    path: str,
) -> None:
    approvals = event["approvals"]
    if len(approvals) < minimum_approvals:
        _fail(
            "hip_fgmres_external_trust_registry_v2_approval_insufficient",
            f"{path}/approvals",
        )
    message = _review_approval_message_v2(event, registry_id=registry_id)
    seen_reviewers: set[str] = set()
    seen_keys: set[str] = set()
    previous_approval_key: tuple[str, str] | None = None
    for index, approval in enumerate(approvals):
        approval_path = f"{path}/approvals/{index}"
        reviewer_id = approval["reviewer_id"]
        authority = reviewers.get(reviewer_id)
        approval_key = (reviewer_id, approval["reviewer_key_id"])
        if (
            authority is None
            or reviewer_id in seen_reviewers
            or approval["reviewer_key_id"] in seen_keys
            or approval["reviewer_key_id"] != authority.key_id
            or (
                previous_approval_key is not None
                and approval_key <= previous_approval_key
            )
        ):
            _fail(
                "hip_fgmres_external_trust_registry_v2_approval_authority_invalid",
                approval_path,
            )
        valid_from = _parse_utc_v2(
            authority.valid_from_utc, f"{approval_path}/authority/valid_from_utc"
        )
        valid_until = _parse_utc_v2(
            authority.valid_until_utc,
            f"{approval_path}/authority/valid_until_utc",
        )
        if not valid_from <= occurred_at < valid_until:
            _fail(
                "hip_fgmres_external_trust_registry_v2_approval_authority_inactive",
                approval_path,
            )
        try:
            verify_ed25519_signature_v1(
                public_key=authority.public_key_bytes,
                signature_base64=approval["signature_base64"],
                message=message,
            )
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_trust_registry_v2_approval_signature_invalid",
                f"{approval_path}/signature_base64",
                exc.code,
            )
        seen_reviewers.add(reviewer_id)
        seen_keys.add(approval["reviewer_key_id"])
        previous_approval_key = approval_key


def _review_approval_message_v2(
    event: dict[str, Any],
    *,
    registry_id: str = HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2,
) -> bytes:
    action = {
        "schema_version": _EVENT_ACTION_SCHEMA_VERSION_V2,
        "registry_id": registry_id,
        "sequence": event["sequence"],
        "event_type": event["event_type"],
        "occurred_at_utc": event["occurred_at_utc"],
        "previous_event_hash": event["previous_event_hash"],
        "action": event["action"],
    }
    return _REVIEW_SIGNATURE_DOMAIN_V2 + canonical_json_bytes(action)


def _validated_enrollment_view_v2(
    payload: dict[str, Any],
    *,
    validator: EnrollmentReceiptValidatorV2 | None,
    path: str,
) -> _EnrollmentViewV2:
    if type(payload) is not dict:
        _fail("hip_fgmres_external_trust_registry_v2_enrollment_invalid", path)
    selected_validator = validator or _default_enrollment_receipt_validator_v2
    try:
        receipt = selected_validator(payload)
    except HipFgmresExternalTrustAnchorRegistryV2Error:
        raise
    except Exception as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_enrollment_invalid",
            path,
            type(exc).__name__,
        )
    to_dict = getattr(receipt, "to_dict", None)
    if not callable(to_dict) or to_dict() != payload:
        _fail("hip_fgmres_external_trust_registry_v2_enrollment_invalid", path)
    challenge = getattr(receipt, "challenge", None)
    predecessor = getattr(challenge, "predecessor_key", None)
    try:
        view = _EnrollmentViewV2(
            key_id=challenge.key_id,
            key_epoch=challenge.key_epoch,
            runner_id=challenge.runner_id,
            public_key_base64=challenge.public_key_base64,
            public_key_sha256=challenge.public_key_sha256,
            allowed_architecture_base=challenge.allowed_architecture_base,
            allowed_suite_id=challenge.allowed_suite_id,
            allowed_fixture_registry_bytes_sha256=(
                challenge.allowed_fixture_registry_bytes_sha256
            ),
            allowed_fixture_registry_hash=challenge.allowed_fixture_registry_hash,
            minimum_run_sequence=challenge.minimum_run_sequence,
            maximum_run_sequence=challenge.maximum_run_sequence,
            valid_from_utc=challenge.valid_from_utc,
            valid_until_utc=challenge.valid_until_utc,
            predecessor_registry_epoch=challenge.predecessor_registry_epoch,
            predecessor_registry_hash=challenge.predecessor_registry_hash,
            target_registry_epoch=challenge.target_registry_epoch,
            predecessor_key_id=(None if predecessor is None else predecessor.key_id),
            predecessor_key_epoch=(
                None if predecessor is None else predecessor.key_epoch
            ),
            predecessor_public_key_sha256=(
                None if predecessor is None else predecessor.public_key_sha256
            ),
            predecessor_maximum_run_sequence=(
                None if predecessor is None else predecessor.maximum_run_sequence
            ),
            receipt_hash=receipt.receipt_hash,
        )
    except (AttributeError, TypeError) as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_enrollment_invalid",
            path,
            f"{type(exc).__name__}: {exc}",
        )
    _validate_enrollment_view_v2(view, path=path)
    return view


def _default_enrollment_receipt_validator_v2(payload: dict[str, Any]) -> Any:
    try:
        module = import_module(
            ".fgmres_external_key_enrollment_v1", package=__package__
        )
    except ImportError as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_enrollment_validator_unavailable",
            "/enrollment_receipt",
            str(exc),
        )
    try:
        challenge_payload = dict(payload["challenge"])
        predecessor_payload = challenge_payload["predecessor_key"]
        predecessor = (
            None
            if predecessor_payload is None
            else module.HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
                **predecessor_payload
            )
        )
        challenge_payload["predecessor_key"] = predecessor
        challenge = module.HipFgmresExternalKeyEnrollmentChallengeV1(
            **challenge_payload
        )
        values = dict(payload)
        values["challenge"] = challenge
        values["claims"] = module.HipFgmresExternalKeyEnrollmentClaimsV1(
            **values["claims"]
        )
        receipt = module.HipFgmresExternalKeyEnrollmentReceiptV1(**values)
        return module.validate_hip_fgmres_external_key_enrollment_receipt_v1(receipt)
    except (KeyError, TypeError, AttributeError) as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_enrollment_invalid",
            "/enrollment_receipt",
            type(exc).__name__,
        )


def _validate_enrollment_view_v2(view: _EnrollmentViewV2, *, path: str) -> None:
    if (
        type(view) is not _EnrollmentViewV2
        or type(view.key_id) is not str
        or not 1 <= len(view.key_id) <= _MAX_KEY_ID_CHARS_V2
        or type(view.runner_id) is not str
        or not 1 <= len(view.runner_id) <= _MAX_RUNNER_ID_CHARS_V2
        or type(view.public_key_base64) is not str
        or len(view.public_key_base64) != _ED25519_PUBLIC_KEY_BASE64_CHARS_V2
        or type(view.allowed_architecture_base) is not str
        or type(view.allowed_suite_id) is not str
        or not 1 <= len(view.allowed_suite_id) <= _MAX_SUITE_ID_CHARS_V2
        or type(view.valid_from_utc) is not str
        or type(view.valid_until_utc) is not str
        or not _is_hash_v2(view.public_key_sha256)
        or not _is_hash_v2(view.allowed_fixture_registry_bytes_sha256)
        or not _is_hash_v2(view.allowed_fixture_registry_hash)
        or not _is_hash_v2(view.predecessor_registry_hash)
        or not _is_hash_v2(view.receipt_hash)
        or (
            view.predecessor_key_id is not None
            and type(view.predecessor_key_id) is not str
        )
        or (
            view.predecessor_key_epoch is not None
            and (
                type(view.predecessor_key_epoch) is not int
                or not 1 <= view.predecessor_key_epoch <= _MAX_REGISTRY_EPOCH_V2
            )
        )
        or (
            view.predecessor_public_key_sha256 is not None
            and not _is_hash_v2(view.predecessor_public_key_sha256)
        )
        or (
            view.predecessor_maximum_run_sequence is not None
            and (
                type(view.predecessor_maximum_run_sequence) is not int
                or not 1
                <= view.predecessor_maximum_run_sequence
                <= _MAX_RUN_SEQUENCE_V2
            )
        )
    ):
        _fail("hip_fgmres_external_trust_registry_v2_enrollment_invalid", path)
    try:
        public_key = decode_canonical_base64_v1(
            view.public_key_base64,
            expected_byte_count=32,
            path=f"{path}/public_key_base64",
        )
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_enrollment_invalid",
            path,
            exc.code,
        )
    valid_from = _parse_utc_v2(view.valid_from_utc, f"{path}/valid_from_utc")
    valid_until = _parse_utc_v2(view.valid_until_utc, f"{path}/valid_until_utc")
    if (
        _KEY_ID_RE.fullmatch(view.key_id) is None
        or _RUNNER_ID_RE.fullmatch(view.runner_id) is None
        or type(view.key_epoch) is not int
        or not 1 <= view.key_epoch <= _MAX_REGISTRY_EPOCH_V2
        or view.key_id != f"ed25519:{view.runner_id}:v{view.key_epoch}"
        or sha256_prefixed(public_key) != view.public_key_sha256
        or view.allowed_architecture_base != "gfx1100"
        or not _is_hash_v2(view.allowed_fixture_registry_bytes_sha256)
        or not _is_hash_v2(view.allowed_fixture_registry_hash)
        or type(view.minimum_run_sequence) is not int
        or not 1 <= view.minimum_run_sequence <= _MAX_RUN_SEQUENCE_V2
        or type(view.maximum_run_sequence) is not int
        or not view.minimum_run_sequence
        <= view.maximum_run_sequence
        <= _MAX_RUN_SEQUENCE_V2
        or valid_until <= valid_from
        or type(view.predecessor_registry_epoch) is not int
        or not 1 <= view.predecessor_registry_epoch < _MAX_REGISTRY_EPOCH_V2
        or not _is_hash_v2(view.predecessor_registry_hash)
        or type(view.target_registry_epoch) is not int
        or not 2 <= view.target_registry_epoch <= _MAX_REGISTRY_EPOCH_V2
        or not _is_hash_v2(view.receipt_hash)
    ):
        _fail("hip_fgmres_external_trust_registry_v2_enrollment_invalid", path)


def _apply_enrollment_v2(
    enrollment: _EnrollmentViewV2,
    *,
    event: dict[str, Any],
    expected_predecessor_registry_hash: str,
    keys: dict[str, _MutableKeyV2],
    runner_predecessors: dict[str, _EnrollmentViewV2],
    public_hashes: set[str],
    path: str,
) -> None:
    immediate_predecessor = runner_predecessors.get(enrollment.runner_id)
    expected_epoch = (
        1 if immediate_predecessor is None else immediate_predecessor.key_epoch + 1
    )
    if (
        enrollment.target_registry_epoch != event["sequence"]
        or enrollment.predecessor_registry_epoch != event["sequence"] - 1
        or enrollment.key_id in keys
        or enrollment.public_key_sha256 in public_hashes
        or enrollment.key_epoch != expected_epoch
        or enrollment.predecessor_registry_hash != expected_predecessor_registry_hash
    ):
        _fail("hip_fgmres_external_trust_registry_v2_enrollment_binding_invalid", path)
    if immediate_predecessor is None:
        if any(
            value is not None
            for value in (
                enrollment.predecessor_key_id,
                enrollment.predecessor_key_epoch,
                enrollment.predecessor_public_key_sha256,
                enrollment.predecessor_maximum_run_sequence,
            )
        ):
            _fail(
                "hip_fgmres_external_trust_registry_v2_enrollment_predecessor_invalid",
                path,
            )
    elif (
        enrollment.predecessor_key_id != immediate_predecessor.key_id
        or enrollment.predecessor_key_epoch != immediate_predecessor.key_epoch
        or enrollment.predecessor_public_key_sha256
        != immediate_predecessor.public_key_sha256
        or enrollment.predecessor_maximum_run_sequence
        != immediate_predecessor.maximum_run_sequence
    ):
        _fail(
            "hip_fgmres_external_trust_registry_v2_enrollment_predecessor_invalid",
            path,
        )
    if immediate_predecessor is not None:
        if (
            enrollment.minimum_run_sequence
            != immediate_predecessor.maximum_run_sequence + 1
        ):
            _fail(
                "hip_fgmres_external_trust_registry_v2_key_sequence_not_contiguous",
                path,
            )
        predecessor_valid_until = _parse_utc_v2(
            immediate_predecessor.valid_until_utc,
            f"{path}/predecessor/valid_until_utc",
        )
        enrollment_valid_from = _parse_utc_v2(
            enrollment.valid_from_utc,
            f"{path}/enrollment/valid_from_utc",
        )
        if enrollment_valid_from < predecessor_valid_until:
            _fail("hip_fgmres_external_trust_registry_v2_key_range_overlap", path)
    keys[enrollment.key_id] = _MutableKeyV2(
        enrollment=enrollment,
        enrollment_event_hash=event["event_hash"],
    )
    runner_predecessors[enrollment.runner_id] = enrollment
    public_hashes.add(enrollment.public_key_sha256)


def _registry_prefix_hashes_v2(
    *,
    events: list[dict[str, Any]],
    reviewers: tuple[HipFgmresExternalTrustReviewerAuthorityV2, ...],
) -> tuple[str, ...]:
    """Build an O(E) chain whose per-epoch canonical payload has fixed shape."""

    reviewer_commitment_hash = canonical_hash([item.to_dict() for item in reviewers])
    hashes: list[str] = []
    predecessor_registry_hash: str | None = None
    for count, event in enumerate(events, start=1):
        payload = {
            "schema_version": (
                HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2
            ),
            "capability_profile": (
                HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2
            ),
            "evidence_scope": (
                HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2
            ),
            "registry_epoch": count,
            "predecessor_registry_hash": predecessor_registry_hash,
            "reviewer_authority_commitment_hash": reviewer_commitment_hash,
            "head_event_hash": event["event_hash"],
        }
        predecessor_registry_hash = canonical_hash(payload)
        hashes.append(predecessor_registry_hash)
    return tuple(hashes)


def _apply_activation_v2(
    event: dict[str, Any],
    *,
    keys: dict[str, _MutableKeyV2],
    active_key_by_runner: dict[str, str],
    path: str,
) -> None:
    action = event["action"]
    key = keys.get(action["key_id"])
    if key is None:
        _fail("hip_fgmres_external_trust_registry_v2_key_not_found", path)
    activated_at = _parse_utc_v2(action["activated_at_utc"], f"{path}/action")
    occurred_at = _parse_utc_v2(event["occurred_at_utc"], f"{path}/occurred_at_utc")
    if (
        key.status != "enrolled"
        or key.enrollment.key_epoch != 1
        or key.enrollment.runner_id in active_key_by_runner
        or activated_at != occurred_at
        or not _time_in_key_window_v2(activated_at, key.enrollment)
    ):
        _fail("hip_fgmres_external_trust_registry_v2_activation_invalid", path)
    key.status = "active"
    key.activation_event_hash = event["event_hash"]
    key.activated_at_utc = action["activated_at_utc"]
    active_key_by_runner[key.enrollment.runner_id] = key.enrollment.key_id


def _apply_rotation_v2(
    event: dict[str, Any],
    *,
    keys: dict[str, _MutableKeyV2],
    active_key_by_runner: dict[str, str],
    path: str,
) -> None:
    action = event["action"]
    old = keys.get(action["retired_key_id"])
    new = keys.get(action["successor_key_id"])
    if old is None or new is None or old is new:
        _fail("hip_fgmres_external_trust_registry_v2_rotation_invalid", path)
    rotated_at = _parse_utc_v2(action["rotated_at_utc"], f"{path}/action")
    occurred_at = _parse_utc_v2(event["occurred_at_utc"], f"{path}/occurred_at_utc")
    old_end = _parse_utc_v2(old.enrollment.valid_until_utc, f"{path}/old/valid_until")
    new_start = _parse_utc_v2(new.enrollment.valid_from_utc, f"{path}/new/valid_from")
    if (
        old.status != "active"
        or new.status != "enrolled"
        or old.enrollment.runner_id != new.enrollment.runner_id
        or active_key_by_runner.get(old.enrollment.runner_id) != old.enrollment.key_id
        or new.enrollment.key_epoch != old.enrollment.key_epoch + 1
        or old.enrollment.maximum_run_sequence + 1
        != new.enrollment.minimum_run_sequence
        or old_end > new_start
        or rotated_at != occurred_at
        or rotated_at != new_start
    ):
        _fail("hip_fgmres_external_trust_registry_v2_rotation_invalid", path)
    old.status = "retired"
    old.terminal_event_hash = event["event_hash"]
    old.terminal_at_utc = action["rotated_at_utc"]
    old.terminal_reason = "rotated"
    new.status = "active"
    new.activation_event_hash = event["event_hash"]
    new.activated_at_utc = action["rotated_at_utc"]
    active_key_by_runner[old.enrollment.runner_id] = new.enrollment.key_id


def _apply_retirement_v2(
    event: dict[str, Any],
    *,
    keys: dict[str, _MutableKeyV2],
    active_key_by_runner: dict[str, str],
    path: str,
) -> None:
    action = event["action"]
    key = keys.get(action["key_id"])
    retired_at = _parse_utc_v2(action["retired_at_utc"], f"{path}/action")
    occurred_at = _parse_utc_v2(event["occurred_at_utc"], f"{path}/occurred_at_utc")
    if (
        key is None
        or key.status != "active"
        or active_key_by_runner.get(key.enrollment.runner_id) != key.enrollment.key_id
        or retired_at != occurred_at
    ):
        _fail("hip_fgmres_external_trust_registry_v2_retirement_invalid", path)
    key.status = "retired"
    key.terminal_event_hash = event["event_hash"]
    key.terminal_at_utc = action["retired_at_utc"]
    key.terminal_reason = action["reason"]
    del active_key_by_runner[key.enrollment.runner_id]


def _apply_revocation_v2(
    event: dict[str, Any],
    *,
    keys: dict[str, _MutableKeyV2],
    active_key_by_runner: dict[str, str],
    path: str,
) -> None:
    action = event["action"]
    key = keys.get(action["key_id"])
    revoked_at = _parse_utc_v2(action["revoked_at_utc"], f"{path}/action")
    occurred_at = _parse_utc_v2(event["occurred_at_utc"], f"{path}/occurred_at_utc")
    if (
        key is None
        or key.status == "revoked"
        or (
            key.status == "active"
            and active_key_by_runner.get(key.enrollment.runner_id)
            != key.enrollment.key_id
        )
        or revoked_at != occurred_at
    ):
        _fail("hip_fgmres_external_trust_registry_v2_revocation_invalid", path)
    if key.status == "active":
        del active_key_by_runner[key.enrollment.runner_id]
    key.status = "revoked"
    key.terminal_event_hash = event["event_hash"]
    key.terminal_at_utc = action["revoked_at_utc"]
    key.revocation_effect = action["revocation_effect"]
    key.terminal_reason = action["reason"]


def _time_in_key_window_v2(value: datetime, key: _EnrollmentViewV2) -> bool:
    start = _parse_utc_v2(key.valid_from_utc, "/keys/valid_from_utc")
    end = _parse_utc_v2(key.valid_until_utc, "/keys/valid_until_utc")
    return start <= value < end


def _freeze_key_v2(value: _MutableKeyV2) -> HipFgmresExternalTrustAnchorV2:
    enrollment = value.enrollment
    return HipFgmresExternalTrustAnchorV2(
        key_id=enrollment.key_id,
        key_epoch=enrollment.key_epoch,
        status=value.status,  # type: ignore[arg-type]
        runner_id=enrollment.runner_id,
        public_key_base64=enrollment.public_key_base64,
        public_key_sha256=enrollment.public_key_sha256,
        allowed_architecture_base=enrollment.allowed_architecture_base,
        allowed_suite_id=enrollment.allowed_suite_id,
        allowed_fixture_registry_bytes_sha256=(
            enrollment.allowed_fixture_registry_bytes_sha256
        ),
        allowed_fixture_registry_hash=enrollment.allowed_fixture_registry_hash,
        minimum_run_sequence=enrollment.minimum_run_sequence,
        maximum_run_sequence=enrollment.maximum_run_sequence,
        valid_from_utc=enrollment.valid_from_utc,
        valid_until_utc=enrollment.valid_until_utc,
        enrollment_receipt_hash=enrollment.receipt_hash,
        enrollment_event_hash=value.enrollment_event_hash,
        activation_event_hash=value.activation_event_hash,
        activated_at_utc=value.activated_at_utc,
        terminal_event_hash=value.terminal_event_hash,
        terminal_at_utc=value.terminal_at_utc,
        revocation_effect=value.revocation_effect,  # type: ignore[arg-type]
        terminal_reason=value.terminal_reason,
    )


def _validate_derived_keys_v2(keys: tuple[HipFgmresExternalTrustAnchorV2, ...]) -> None:
    ids: set[str] = set()
    runner_predecessors: dict[str, HipFgmresExternalTrustAnchorV2] = {}
    public_hashes: set[str] = set()
    active_runners: set[str] = set()
    for index, key in enumerate(keys):
        path = f"/keys/{index}"
        if (
            type(key) is not HipFgmresExternalTrustAnchorV2
            or type(key.key_id) is not str
            or not 1 <= len(key.key_id) <= _MAX_KEY_ID_CHARS_V2
            or type(key.key_epoch) is not int
            or not 1 <= key.key_epoch <= _MAX_REGISTRY_EPOCH_V2
            or type(key.status) is not str
            or type(key.runner_id) is not str
            or not 1 <= len(key.runner_id) <= _MAX_RUNNER_ID_CHARS_V2
            or type(key.public_key_base64) is not str
            or len(key.public_key_base64) != _ED25519_PUBLIC_KEY_BASE64_CHARS_V2
            or type(key.allowed_architecture_base) is not str
            or type(key.allowed_suite_id) is not str
            or not 1 <= len(key.allowed_suite_id) <= _MAX_SUITE_ID_CHARS_V2
            or type(key.minimum_run_sequence) is not int
            or not 1 <= key.minimum_run_sequence <= _MAX_RUN_SEQUENCE_V2
            or type(key.maximum_run_sequence) is not int
            or not key.minimum_run_sequence
            <= key.maximum_run_sequence
            <= _MAX_RUN_SEQUENCE_V2
            or type(key.valid_from_utc) is not str
            or type(key.valid_until_utc) is not str
            or (
                key.activated_at_utc is not None
                and type(key.activated_at_utc) is not str
            )
        ):
            _fail("hip_fgmres_external_trust_registry_v2_derived_key_invalid", path)
        public_key = key.public_key_bytes
        valid_from = _parse_utc_v2(key.valid_from_utc, f"{path}/valid_from_utc")
        valid_until = _parse_utc_v2(key.valid_until_utc, f"{path}/valid_until_utc")
        activated_at = (
            None
            if key.activated_at_utc is None
            else _parse_utc_v2(key.activated_at_utc, f"{path}/activated_at_utc")
        )
        predecessor = runner_predecessors.get(key.runner_id)
        expected_epoch = 1 if predecessor is None else predecessor.key_epoch + 1
        if predecessor is not None:
            predecessor_valid_until = _parse_utc_v2(
                predecessor.valid_until_utc,
                f"{path}/predecessor/valid_until_utc",
            )
            if (
                key.minimum_run_sequence != predecessor.maximum_run_sequence + 1
                or valid_from < predecessor_valid_until
            ):
                _fail(
                    "hip_fgmres_external_trust_registry_v2_derived_key_invalid",
                    path,
                )
        if (
            key.key_id in ids
            or key.key_epoch != expected_epoch
            or key.public_key_sha256 in public_hashes
            or _KEY_ID_RE.fullmatch(key.key_id) is None
            or _RUNNER_ID_RE.fullmatch(key.runner_id) is None
            or key.key_id != f"ed25519:{key.runner_id}:v{key.key_epoch}"
            or key.status not in {"enrolled", "active", "retired", "revoked"}
            or any(
                not _is_hash_v2(value)
                for value in (
                    key.public_key_sha256,
                    key.allowed_fixture_registry_bytes_sha256,
                    key.allowed_fixture_registry_hash,
                    key.enrollment_receipt_hash,
                    key.enrollment_event_hash,
                )
            )
            or sha256_prefixed(public_key) != key.public_key_sha256
            or key.allowed_architecture_base != "gfx1100"
            or not key.allowed_suite_id
            or valid_until <= valid_from
            or (
                key.status == "enrolled"
                and (
                    key.activation_event_hash is not None
                    or key.activated_at_utc is not None
                )
            )
            or (
                key.status in {"active", "retired"}
                and (key.activation_event_hash is None or key.activated_at_utc is None)
            )
            or ((key.activation_event_hash is None) != (activated_at is None))
            or (
                key.activation_event_hash is not None
                and not _is_hash_v2(key.activation_event_hash)
            )
            or (
                activated_at is not None
                and not valid_from <= activated_at < valid_until
            )
            or (
                key.status in {"retired", "revoked"}
                and (
                    not _is_hash_v2(key.terminal_event_hash)
                    or type(key.terminal_at_utc) is not str
                    or type(key.terminal_reason) is not str
                    or not key.terminal_reason
                    or len(key.terminal_reason) > 256
                )
            )
            or (
                key.status in {"enrolled", "active"}
                and (
                    key.terminal_event_hash is not None
                    or key.terminal_at_utc is not None
                    or key.terminal_reason is not None
                )
            )
            or (key.status != "revoked" and key.revocation_effect is not None)
            or (
                key.status == "revoked"
                and key.revocation_effect not in {"prospective", "retroactive"}
            )
        ):
            _fail("hip_fgmres_external_trust_registry_v2_derived_key_invalid", path)
        if key.terminal_at_utc is not None:
            terminal_at = _parse_utc_v2(
                key.terminal_at_utc,
                f"{path}/terminal_at_utc",
            )
            if activated_at is not None and terminal_at <= activated_at:
                _fail(
                    "hip_fgmres_external_trust_registry_v2_derived_key_invalid",
                    path,
                )
        if key.status == "active":
            if key.runner_id in active_runners:
                _fail(
                    "hip_fgmres_external_trust_registry_v2_multiple_active_keys", path
                )
            active_runners.add(key.runner_id)
        ids.add(key.key_id)
        runner_predecessors[key.runner_id] = key
        public_hashes.add(key.public_key_sha256)


def _result_payload_v2(
    result: HipFgmresExternalTrustAnchorRegistryResultV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2,
        "capability_profile": (
            HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2
        ),
        "evidence_scope": HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2,
        "registry_bytes_sha256": result.registry_bytes_sha256,
        "registry_hash": result.registry_hash,
        "registry_epoch": result.registry_epoch,
        "predecessor_registry_epoch": result.predecessor_registry_epoch,
        "predecessor_registry_hash": result.predecessor_registry_hash,
        "head_event_hash": result.head_event_hash,
        "event_count": result.event_count,
        "reviewer_authority_count": len(result.reviewer_authorities),
        "reviewer_authorities": [
            item.to_dict() for item in result.reviewer_authorities
        ],
        "enrolled_key_count": result.enrolled_key_count,
        "active_key_count": result.active_key_count,
        "keys": [item.to_dict() for item in result.keys],
        "claims": result.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = result.receipt_hash
    return payload


def _read_fixed_resource_v2() -> bytes:
    resource = resources.files(_RESOURCE_PACKAGE_V2).joinpath(_REGISTRY_RESOURCE_V2)
    if not resource.is_file():
        _fail("hip_fgmres_external_trust_registry_v2_resource_missing", "/registry")
    try:
        raw = resource.read_bytes()
    except OSError as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_resource_read_failed",
            "/registry",
            str(exc),
        )
    if len(raw) > _MAX_REGISTRY_BYTES:
        _fail("hip_fgmres_external_trust_registry_v2_extent_invalid", "/registry")
    return raw


def _parse_strict_object_v2(raw: bytes, *, path: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_REGISTRY_BYTES:
        _fail("hip_fgmres_external_trust_registry_v2_extent_invalid", path)
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_external_trust_registry_v2_json_bom_forbidden", path)

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
    except RecursionError:
        _fail(
            "hip_fgmres_external_trust_registry_v2_extent_invalid",
            path,
            "JSON nesting exceeds parser limit",
        )
    except _DuplicateKeyError:
        _fail(
            "hip_fgmres_external_trust_registry_v2_json_duplicate_key",
            path,
            "duplicate object member",
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_json_invalid",
            path,
            str(exc),
        )
    if type(payload) is not dict:
        _fail("hip_fgmres_external_trust_registry_v2_json_root_invalid", path)
    _enforce_json_bounds_v2(payload, path=path)
    return payload


def _enforce_json_bounds_v2(value: Any, *, path: str) -> None:
    nodes = 0
    stack: list[tuple[Any, int, str]] = [(value, 1, path)]
    while stack:
        item, depth, item_path = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _fail("hip_fgmres_external_trust_registry_v2_extent_invalid", item_path)
        if type(item) is float and not math.isfinite(item):
            _fail("hip_fgmres_external_trust_registry_v2_json_nonfinite", item_path)
        if type(item) is dict:
            for key, child in item.items():
                stack.append((child, depth + 1, f"{item_path}/{key}"))
        elif type(item) is list:
            for index, child in enumerate(item):
                stack.append((child, depth + 1, f"{item_path}/{index}"))


def _validate_schema_v2(manifest: dict[str, Any]) -> None:
    try:
        schema_raw = (
            resources.files("structural_analysis.schemas")
            .joinpath(_SCHEMA_RESOURCE_V2)
            .read_bytes()
        )
    except OSError as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_schema_invalid",
            "/schema",
            str(exc),
        )
    if sha256_prefixed(schema_raw) != _SCHEMA_RESOURCE_BYTES_SHA256_V2:
        _fail("hip_fgmres_external_trust_registry_v2_schema_hash_mismatch", "/schema")
    schema = _parse_strict_object_v2(schema_raw, path="/schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_schema_invalid",
            "/schema",
            type(exc).__name__,
        )
    errors = Draft202012Validator(schema).iter_errors(manifest)
    first = next(errors, None)
    if first is not None:
        pointer = "/" + "/".join(str(part) for part in first.absolute_path)
        keyword = str(first.validator)[:64]
        _fail(
            "hip_fgmres_external_trust_registry_v2_schema_validation_failed",
            pointer,
            f"schema keyword {keyword} rejected value",
        )


def _parse_utc_v2(value: str, path: str) -> datetime:
    if (
        type(value) is not str
        or len(value) not in {20, 27}
        or _UTC_RE.fullmatch(value) is None
    ):
        _fail("hip_fgmres_external_trust_registry_v2_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        _fail(
            "hip_fgmres_external_trust_registry_v2_timestamp_invalid",
            path,
            type(exc).__name__,
        )
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("hip_fgmres_external_trust_registry_v2_timestamp_invalid", path)
    canonical = parsed.isoformat(
        timespec="microseconds" if "." in value else "seconds"
    ).replace("+00:00", "Z")
    if canonical != value:
        _fail("hip_fgmres_external_trust_registry_v2_timestamp_invalid", path)
    return parsed


def _bounded_path(path: str) -> str:
    value = path if type(path) is str and path.startswith("/") else "/"
    if len(value) <= _MAX_ERROR_PATH_CHARS:
        return value
    return value[: _MAX_ERROR_PATH_CHARS - 3] + "..."


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalTrustAnchorRegistryV2Error(code, path, message)


def _make_authoritative_loader_v2(
    loader: Any = _load_package_registry_v2,
) -> Any:
    return loader


_TRUST_REGISTRY_LOADER_AUTHORITY_V2 = _make_authoritative_loader_v2()
del _make_authoritative_loader_v2


__all__ = [
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2",
    "HipFgmresExternalTrustAnchorRegistryClaimsV2",
    "HipFgmresExternalTrustAnchorRegistryResultV2",
    "HipFgmresExternalTrustAnchorRegistryV2Error",
    "HipFgmresExternalTrustAnchorV2",
    "HipFgmresExternalTrustReviewerAuthorityV2",
    "load_hip_fgmres_external_trust_anchor_registry_v2",
    "validate_hip_fgmres_external_trust_anchor_registry_result_v2",
]
