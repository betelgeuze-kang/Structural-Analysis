"""Detached runner-key enrollment and activation on a registry-v3 lineage.

The registry-v3 genesis contract activates three public reviewer roots but
deliberately leaves runner-key counts at zero.  This module consumes that
detached genesis plus a detached runner proof-of-possession receipt and builds
two reviewed transitions: epoch-2 enrollment and epoch-3 activation.

Every transition is approved by an ordered two-or-three member subset of the
three immutable reviewer roots.  The product module only compiles messages and
verifies signatures; it never loads private keys or signs.  The resulting
receipt is still detached and non-promoting.  In particular, it is not a
package trust-store mutation, an HSM attestation, or external gfx1100 evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, TypeAlias

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

from . import fgmres_external_key_enrollment_v1 as enrollment_v1
from . import fgmres_external_reviewer_root_bootstrap_v1 as bootstrap_v1
from . import fgmres_external_trust_anchor_registry_v3 as registry_v3


HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_SCHEMA_VERSION_V3 = (
    "structural-analysis-hip-fgmres-external-runner-key-lifecycle.v3"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_CAPABILITY_PROFILE_V3 = (
    "phase0_external_gfx1100_runner_key_enrollment_activation_v3"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_EVIDENCE_SCOPE_V3 = (
    "detached_v3_lineage_runner_pop_and_reviewer_quorum_non_authoritative"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_STATUS_V3 = (
    "detached_v3_runner_key_enrollment_activation_verified"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_EVENT_ACTION_SCHEMA_VERSION_V3 = (
    "structural-analysis-hip-fgmres-external-runner-key-event-action.v3"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_ENROLLMENT_PURPOSE_V3 = (
    "hip_fgmres_external_runner_key_v3_enrollment"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_ACTIVATION_PURPOSE_V3 = (
    "hip_fgmres_external_runner_key_v3_activation"
)
HIP_FGMRES_EXTERNAL_RUNNER_KEY_REVIEW_DOMAIN_V3 = (
    b"structural-analysis/engine-v2/hip-fgmres/"
    b"external-runner-key-registry-v3-review/v1\x00"
)

_SCHEMA_RESOURCE = "hip_fgmres_external_runner_key_lifecycle_v3.schema.json"
_REGISTRY_ID = (
    bootstrap_v1.HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1
)
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUNNER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_KEY_ID_RE = re.compile(r"^ed25519:[a-z0-9][a-z0-9._-]{2,63}:v1$")
_REVIEWER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_REVIEWER_KEY_ID_RE = re.compile(r"^ed25519-review:[a-z0-9][a-z0-9._-]{2,63}:v1$")
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z$"
)
_REVIEWER_COUNT = 3
_MINIMUM_REVIEWER_APPROVALS = 2
_SOURCE_REGISTRY_EPOCH = 1
_ENROLLMENT_REGISTRY_EPOCH = 2
_ACTIVATION_REGISTRY_EPOCH = 3
_MAX_ERROR_PATH_CHARS = 512
_MAX_ERROR_MESSAGE_CHARS = 240


class HipFgmresExternalRunnerKeyLifecycleV3Error(RuntimeError):
    """Stable fail-closed runner-key lifecycle-v3 error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path[:_MAX_ERROR_PATH_CHARS] if path.startswith("/") else "/"
        self.message = (message or code)[:_MAX_ERROR_MESSAGE_CHARS]
        super().__init__(f"{self.code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyEnrollmentStatementV3:
    schema_version: str
    purpose: str
    registry_schema_version: str
    registry_id: str
    lineage_generation: int
    lineage_id: str
    sequence: int
    event_type: Literal["runner_key_enrolled"]
    occurred_at_utc: str
    previous_event_hash: str
    predecessor_registry_epoch: int
    predecessor_registry_hash: str
    source_registry_receipt_hash: str
    reviewer_policy_hash: str
    reviewer_roots: tuple[bootstrap_v1.HipFgmresExternalReviewerRootV1, ...]
    reviewer_root_commitment_hash: str
    minimum_reviewer_approvals: int
    enrollment_receipt_schema_version: str
    enrollment_receipt_hash: str
    enrollment_challenge_hash: str
    runner_id: str
    key_id: str
    key_epoch: int
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
    statement_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_runner_key_enrollment_statement_v3(self)
        return _enrollment_statement_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyActivationStatementV3:
    schema_version: str
    purpose: str
    registry_schema_version: str
    registry_id: str
    lineage_generation: int
    lineage_id: str
    sequence: int
    event_type: Literal["runner_key_activated"]
    occurred_at_utc: str
    previous_event_hash: str
    predecessor_registry_epoch: int
    predecessor_registry_hash: str
    source_registry_receipt_hash: str
    reviewer_policy_hash: str
    reviewer_roots: tuple[bootstrap_v1.HipFgmresExternalReviewerRootV1, ...]
    reviewer_root_commitment_hash: str
    minimum_reviewer_approvals: int
    enrollment_event_hash: str
    enrollment_receipt_hash: str
    enrollment_challenge_hash: str
    runner_id: str
    key_id: str
    key_epoch: int
    public_key_sha256: str
    valid_from_utc: str
    valid_until_utc: str
    activated_at_utc: str
    statement_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_runner_key_activation_statement_v3(self)
        return _activation_statement_payload(self, include_hash=True)


RunnerKeyStatementV3: TypeAlias = (
    HipFgmresExternalRunnerKeyEnrollmentStatementV3
    | HipFgmresExternalRunnerKeyActivationStatementV3
)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyReviewerApprovalV3:
    reviewer_id: str
    reviewer_key_id: str
    reviewer_key_epoch: int
    statement_hash: str
    algorithm: str
    signature_base64: str
    signature_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyEnrollmentEventV3:
    statement: HipFgmresExternalRunnerKeyEnrollmentStatementV3
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...]
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_runner_key_enrollment_event_v3(self)
        return _event_payload(self.statement, self.approvals, self.event_hash)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyActivationEventV3:
    statement: HipFgmresExternalRunnerKeyActivationStatementV3
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...]
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_runner_key_activation_event_v3(self)
        return _event_payload(self.statement, self.approvals, self.event_hash)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalActiveRunnerKeyV3:
    status: Literal["active"]
    runner_id: str
    key_id: str
    key_epoch: int
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
    source_registry_receipt_hash: str
    source_registry_hash: str
    lineage_id: str
    enrollment_receipt_hash: str
    enrollment_challenge_hash: str
    enrollment_event_hash: str
    enrolled_at_utc: str
    activation_event_hash: str
    activated_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyLifecycleClaimsV3:
    detached_registry_genesis_signature_chain_verified: Literal[True] = True
    detached_runner_key_possession_verified: Literal[True] = True
    lineage_bound_enrollment_verified: Literal[True] = True
    enrollment_reviewer_quorum_verified: Literal[True] = True
    activation_reviewer_quorum_verified: Literal[True] = True
    detached_active_runner_key_state_verified: Literal[True] = True
    source_bootstrap_replayed_in_detached_receipt: Literal[False] = False
    package_registry_v3_inclusion_verified: Literal[False] = False
    package_runner_key_enrollment_verified: Literal[False] = False
    package_runner_key_activation_verified: Literal[False] = False
    operational_reviewer_authority_verified: Literal[False] = False
    actual_isolated_runner_verified: Literal[False] = False
    runner_hsm_origin_verified: Literal[False] = False
    runner_hsm_non_exportability_verified: Literal[False] = False
    reviewer_human_identity_verified: Literal[False] = False
    reviewer_independence_verified: Literal[False] = False
    reviewer_hsm_verified: Literal[False] = False
    trusted_event_time_verified: Literal[False] = False
    external_monotonic_anchor_verified: Literal[False] = False
    historical_registry_resolution_verified: Literal[False] = False
    signed_trace_binding_verified: Literal[False] = False
    durable_ledger_v3_verified: Literal[False] = False
    actual_external_gfx1100_verified: Literal[False] = False
    same_artifact_two_architecture_verified: Literal[False] = False
    result_ir_verified: Literal[False] = False
    performance_or_speedup_verified: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyLifecycleReceiptV3:
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    promotion_eligible: Literal[False]
    source_registry_receipt: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3
    enrollment_receipt: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1
    enrollment_event: HipFgmresExternalRunnerKeyEnrollmentEventV3
    activation_event: HipFgmresExternalRunnerKeyActivationEventV3
    active_key: HipFgmresExternalActiveRunnerKeyV3
    registry_epoch: Literal[3]
    predecessor_registry_epoch: Literal[2]
    predecessor_registry_hash: str
    source_registry_hash: str
    enrollment_registry_hash: str
    registry_hash: str
    head_event_hash: str
    event_count: Literal[3]
    reviewer_authority_count: Literal[3]
    enrolled_runner_key_count: Literal[1]
    active_runner_key_count: Literal[1]
    claims: HipFgmresExternalRunnerKeyLifecycleClaimsV3
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalRunnerKeyLifecycleResultV3:
    receipt: HipFgmresExternalRunnerKeyLifecycleReceiptV3
    source_registry_result: registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_external_runner_key_lifecycle_result_v3(self)
        return self.receipt.to_dict()


def compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
    source_registry_receipt: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
    enrollment_receipt: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    *,
    enrolled_at_utc: str,
) -> HipFgmresExternalRunnerKeyEnrollmentStatementV3:
    """Compile the exact epoch-2 enrollment statement for reviewer signing."""

    _validate_source_receipt(source_registry_receipt)
    _validate_enrollment_receipt(enrollment_receipt)
    genesis = source_registry_receipt.genesis
    challenge = enrollment_receipt.challenge
    enrolled_at = _parse_utc(enrolled_at_utc, "/enrolled_at_utc")
    genesis_at = _parse_utc(genesis.activated_at_utc, "/source/activated_at_utc")
    if enrolled_at <= genesis_at:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_time_invalid",
            "/enrolled_at_utc",
        )
    _validate_reviewer_roots(genesis.reviewer_roots, observed_at=enrolled_at)
    if (
        challenge.predecessor_registry_epoch != _SOURCE_REGISTRY_EPOCH
        or challenge.predecessor_registry_hash != source_registry_receipt.registry_hash
        or challenge.target_registry_epoch != _ENROLLMENT_REGISTRY_EPOCH
        or challenge.key_epoch != 1
        or challenge.predecessor_key is not None
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_lineage_invalid",
            "/enrollment_receipt/challenge",
        )
    draft = HipFgmresExternalRunnerKeyEnrollmentStatementV3(
        schema_version=HIP_FGMRES_EXTERNAL_RUNNER_KEY_EVENT_ACTION_SCHEMA_VERSION_V3,
        purpose=HIP_FGMRES_EXTERNAL_RUNNER_KEY_ENROLLMENT_PURPOSE_V3,
        registry_schema_version=genesis.registry_schema_version,
        registry_id=genesis.registry_id,
        lineage_generation=genesis.lineage_generation,
        lineage_id=genesis.lineage_id,
        sequence=_ENROLLMENT_REGISTRY_EPOCH,
        event_type="runner_key_enrolled",
        occurred_at_utc=_format_utc(enrolled_at),
        previous_event_hash=genesis.genesis_event_hash,
        predecessor_registry_epoch=_SOURCE_REGISTRY_EPOCH,
        predecessor_registry_hash=source_registry_receipt.registry_hash,
        source_registry_receipt_hash=source_registry_receipt.receipt_hash,
        reviewer_policy_hash=genesis.reviewer_policy_hash,
        reviewer_roots=genesis.reviewer_roots,
        reviewer_root_commitment_hash=genesis.reviewer_root_commitment_hash,
        minimum_reviewer_approvals=_MINIMUM_REVIEWER_APPROVALS,
        enrollment_receipt_schema_version=enrollment_receipt.schema_version,
        enrollment_receipt_hash=enrollment_receipt.receipt_hash,
        enrollment_challenge_hash=challenge.challenge_hash,
        runner_id=challenge.runner_id,
        key_id=challenge.key_id,
        key_epoch=challenge.key_epoch,
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
        runner_declared_key_origin=challenge.runner_declared_key_origin,
        attestation_digest_sha256=challenge.attestation_digest_sha256,
        statement_hash=_ZERO_HASH,
    )
    statement = replace(
        draft,
        statement_hash=canonical_hash(
            _enrollment_statement_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_fgmres_external_runner_key_enrollment_statement_v3(statement)


def compile_hip_fgmres_external_runner_key_activation_statement_v3(
    source_registry_receipt: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
    enrollment_receipt: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    enrollment_event: HipFgmresExternalRunnerKeyEnrollmentEventV3,
    *,
    activated_at_utc: str,
) -> HipFgmresExternalRunnerKeyActivationStatementV3:
    """Compile the exact epoch-3 activation statement for reviewer signing."""

    _validate_source_receipt(source_registry_receipt)
    _validate_enrollment_receipt(enrollment_receipt)
    validate_hip_fgmres_external_runner_key_enrollment_event_v3(enrollment_event)
    _validate_enrollment_binding(
        source_registry_receipt,
        enrollment_receipt,
        enrollment_event.statement,
    )
    activated_at = _parse_utc(activated_at_utc, "/activated_at_utc")
    enrolled_at = _parse_utc(
        enrollment_event.statement.occurred_at_utc,
        "/enrollment_event/occurred_at_utc",
    )
    challenge = enrollment_receipt.challenge
    valid_from = _parse_utc(challenge.valid_from_utc, "/key/valid_from_utc")
    valid_until = _parse_utc(challenge.valid_until_utc, "/key/valid_until_utc")
    if activated_at <= enrolled_at or not valid_from <= activated_at < valid_until:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_activation_time_invalid",
            "/activated_at_utc",
        )
    genesis = source_registry_receipt.genesis
    _validate_reviewer_roots(genesis.reviewer_roots, observed_at=activated_at)
    enrollment_registry_hash = _registry_transition_hash(
        enrollment_event.statement,
        event_hash=enrollment_event.event_hash,
    )
    draft = HipFgmresExternalRunnerKeyActivationStatementV3(
        schema_version=HIP_FGMRES_EXTERNAL_RUNNER_KEY_EVENT_ACTION_SCHEMA_VERSION_V3,
        purpose=HIP_FGMRES_EXTERNAL_RUNNER_KEY_ACTIVATION_PURPOSE_V3,
        registry_schema_version=genesis.registry_schema_version,
        registry_id=genesis.registry_id,
        lineage_generation=genesis.lineage_generation,
        lineage_id=genesis.lineage_id,
        sequence=_ACTIVATION_REGISTRY_EPOCH,
        event_type="runner_key_activated",
        occurred_at_utc=_format_utc(activated_at),
        previous_event_hash=enrollment_event.event_hash,
        predecessor_registry_epoch=_ENROLLMENT_REGISTRY_EPOCH,
        predecessor_registry_hash=enrollment_registry_hash,
        source_registry_receipt_hash=source_registry_receipt.receipt_hash,
        reviewer_policy_hash=genesis.reviewer_policy_hash,
        reviewer_roots=genesis.reviewer_roots,
        reviewer_root_commitment_hash=genesis.reviewer_root_commitment_hash,
        minimum_reviewer_approvals=_MINIMUM_REVIEWER_APPROVALS,
        enrollment_event_hash=enrollment_event.event_hash,
        enrollment_receipt_hash=enrollment_receipt.receipt_hash,
        enrollment_challenge_hash=challenge.challenge_hash,
        runner_id=challenge.runner_id,
        key_id=challenge.key_id,
        key_epoch=challenge.key_epoch,
        public_key_sha256=challenge.public_key_sha256,
        valid_from_utc=challenge.valid_from_utc,
        valid_until_utc=challenge.valid_until_utc,
        activated_at_utc=_format_utc(activated_at),
        statement_hash=_ZERO_HASH,
    )
    statement = replace(
        draft,
        statement_hash=canonical_hash(
            _activation_statement_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_fgmres_external_runner_key_activation_statement_v3(statement)


def compile_hip_fgmres_external_runner_key_review_message_v3(
    statement: RunnerKeyStatementV3,
) -> bytes:
    """Return the domain-separated bytes reviewed roots must sign."""

    if type(statement) is HipFgmresExternalRunnerKeyEnrollmentStatementV3:
        validate_hip_fgmres_external_runner_key_enrollment_statement_v3(statement)
    elif type(statement) is HipFgmresExternalRunnerKeyActivationStatementV3:
        validate_hip_fgmres_external_runner_key_activation_statement_v3(statement)
    else:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_statement_type_invalid",
            "/statement",
        )
    return HIP_FGMRES_EXTERNAL_RUNNER_KEY_REVIEW_DOMAIN_V3 + canonical_json_bytes(
        {"purpose": statement.purpose, "statement": statement.to_dict()}
    )


def finalize_hip_fgmres_external_runner_key_enrollment_event_v3(
    statement: HipFgmresExternalRunnerKeyEnrollmentStatementV3,
    *,
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...],
) -> HipFgmresExternalRunnerKeyEnrollmentEventV3:
    """Verify reviewer quorum and seal one epoch-2 enrollment event."""

    validate_hip_fgmres_external_runner_key_enrollment_statement_v3(statement)
    _validate_approvals(statement, approvals)
    event_hash = canonical_hash(_event_payload(statement, approvals, event_hash=None))
    event = HipFgmresExternalRunnerKeyEnrollmentEventV3(
        statement=statement,
        approvals=approvals,
        event_hash=event_hash,
    )
    return validate_hip_fgmres_external_runner_key_enrollment_event_v3(event)


def finalize_hip_fgmres_external_runner_key_activation_event_v3(
    statement: HipFgmresExternalRunnerKeyActivationStatementV3,
    *,
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...],
) -> HipFgmresExternalRunnerKeyActivationEventV3:
    """Verify reviewer quorum and seal one epoch-3 activation event."""

    validate_hip_fgmres_external_runner_key_activation_statement_v3(statement)
    _validate_approvals(statement, approvals)
    event_hash = canonical_hash(_event_payload(statement, approvals, event_hash=None))
    event = HipFgmresExternalRunnerKeyActivationEventV3(
        statement=statement,
        approvals=approvals,
        event_hash=event_hash,
    )
    return validate_hip_fgmres_external_runner_key_activation_event_v3(event)


def verify_hip_fgmres_external_runner_key_lifecycle_v3(
    source_registry_result: registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3,
    enrollment_receipt: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    *,
    enrollment_event: HipFgmresExternalRunnerKeyEnrollmentEventV3,
    activation_event: HipFgmresExternalRunnerKeyActivationEventV3,
) -> HipFgmresExternalRunnerKeyLifecycleResultV3:
    """Verify both reviewed transitions and mint an attached replay result."""

    _validate_source_result(source_registry_result)
    _validate_enrollment_receipt(enrollment_receipt)
    validate_hip_fgmres_external_runner_key_enrollment_event_v3(enrollment_event)
    validate_hip_fgmres_external_runner_key_activation_event_v3(activation_event)
    source_receipt = source_registry_result.receipt
    _validate_lifecycle_binding(
        source_receipt,
        enrollment_receipt,
        enrollment_event,
        activation_event,
    )
    enrollment_registry_hash = _registry_transition_hash(
        enrollment_event.statement,
        event_hash=enrollment_event.event_hash,
    )
    activation_registry_hash = _registry_transition_hash(
        activation_event.statement,
        event_hash=activation_event.event_hash,
    )
    active_key = _derive_active_key(
        source_receipt,
        enrollment_receipt,
        enrollment_event,
        activation_event,
    )
    draft = HipFgmresExternalRunnerKeyLifecycleReceiptV3(
        schema_version=HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_SCHEMA_VERSION_V3,
        capability_profile=(
            HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_CAPABILITY_PROFILE_V3
        ),
        status=HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_STATUS_V3,
        evidence_scope=HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_EVIDENCE_SCOPE_V3,
        promotion_eligible=False,
        source_registry_receipt=source_receipt,
        enrollment_receipt=enrollment_receipt,
        enrollment_event=enrollment_event,
        activation_event=activation_event,
        active_key=active_key,
        registry_epoch=_ACTIVATION_REGISTRY_EPOCH,
        predecessor_registry_epoch=_ENROLLMENT_REGISTRY_EPOCH,
        predecessor_registry_hash=enrollment_registry_hash,
        source_registry_hash=source_receipt.registry_hash,
        enrollment_registry_hash=enrollment_registry_hash,
        registry_hash=activation_registry_hash,
        head_event_hash=activation_event.event_hash,
        event_count=_ACTIVATION_REGISTRY_EPOCH,
        reviewer_authority_count=_REVIEWER_COUNT,
        enrolled_runner_key_count=1,
        active_runner_key_count=1,
        claims=HipFgmresExternalRunnerKeyLifecycleClaimsV3(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    result = HipFgmresExternalRunnerKeyLifecycleResultV3(
        receipt=receipt,
        source_registry_result=source_registry_result,
    )
    return validate_hip_fgmres_external_runner_key_lifecycle_result_v3(result)


def validate_hip_fgmres_external_runner_key_enrollment_statement_v3(
    statement: HipFgmresExternalRunnerKeyEnrollmentStatementV3,
) -> HipFgmresExternalRunnerKeyEnrollmentStatementV3:
    if type(statement) is not HipFgmresExternalRunnerKeyEnrollmentStatementV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_statement_type_invalid",
            "/statement",
        )
    _validate_statement_common(
        statement,
        expected_purpose=HIP_FGMRES_EXTERNAL_RUNNER_KEY_ENROLLMENT_PURPOSE_V3,
        expected_sequence=_ENROLLMENT_REGISTRY_EPOCH,
        expected_event_type="runner_key_enrolled",
    )
    hashes = (
        statement.enrollment_receipt_hash,
        statement.enrollment_challenge_hash,
        statement.public_key_sha256,
        statement.allowed_fixture_registry_bytes_sha256,
        statement.allowed_fixture_registry_hash,
    )
    integer_values = (
        statement.key_epoch,
        statement.minimum_run_sequence,
        statement.maximum_run_sequence,
    )
    if (
        statement.enrollment_receipt_schema_version
        != enrollment_v1.HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_RECEIPT_SCHEMA_VERSION_V1
        or any(
            type(value) is not str or _HASH_RE.fullmatch(value) is None
            for value in hashes
        )
        or type(statement.runner_id) is not str
        or _RUNNER_ID_RE.fullmatch(statement.runner_id) is None
        or type(statement.key_id) is not str
        or _KEY_ID_RE.fullmatch(statement.key_id) is None
        or statement.key_id != f"ed25519:{statement.runner_id}:v1"
        or any(type(value) is not int or value <= 0 for value in integer_values)
        or statement.key_epoch != 1
        or statement.maximum_run_sequence < statement.minimum_run_sequence
        or statement.allowed_architecture_base != "gfx1100"
        or type(statement.allowed_suite_id) is not str
        or not statement.allowed_suite_id
        or statement.runner_declared_key_origin
        not in enrollment_v1.HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_ALLOWED_ORIGINS_V1
        or (
            statement.attestation_digest_sha256 is not None
            and (
                type(statement.attestation_digest_sha256) is not str
                or _HASH_RE.fullmatch(statement.attestation_digest_sha256) is None
            )
        )
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_statement_invalid",
            "/statement",
        )
    valid_from = _parse_utc(statement.valid_from_utc, "/statement/valid_from_utc")
    valid_until = _parse_utc(statement.valid_until_utc, "/statement/valid_until_utc")
    if valid_from >= valid_until:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_statement_invalid",
            "/statement",
        )
    expected_hash = canonical_hash(
        _enrollment_statement_payload(statement, include_hash=False)
    )
    if statement.statement_hash != expected_hash:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_statement_hash_invalid",
            "/statement/statement_hash",
        )
    return statement


def validate_hip_fgmres_external_runner_key_activation_statement_v3(
    statement: HipFgmresExternalRunnerKeyActivationStatementV3,
) -> HipFgmresExternalRunnerKeyActivationStatementV3:
    if type(statement) is not HipFgmresExternalRunnerKeyActivationStatementV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_statement_type_invalid",
            "/statement",
        )
    _validate_statement_common(
        statement,
        expected_purpose=HIP_FGMRES_EXTERNAL_RUNNER_KEY_ACTIVATION_PURPOSE_V3,
        expected_sequence=_ACTIVATION_REGISTRY_EPOCH,
        expected_event_type="runner_key_activated",
    )
    hashes = (
        statement.enrollment_event_hash,
        statement.enrollment_receipt_hash,
        statement.enrollment_challenge_hash,
        statement.public_key_sha256,
    )
    activated_at = _parse_utc(
        statement.activated_at_utc,
        "/statement/activated_at_utc",
    )
    valid_from = _parse_utc(statement.valid_from_utc, "/statement/valid_from_utc")
    valid_until = _parse_utc(statement.valid_until_utc, "/statement/valid_until_utc")
    if (
        any(
            type(value) is not str or _HASH_RE.fullmatch(value) is None
            for value in hashes
        )
        or statement.previous_event_hash != statement.enrollment_event_hash
        or statement.occurred_at_utc != statement.activated_at_utc
        or type(statement.runner_id) is not str
        or _RUNNER_ID_RE.fullmatch(statement.runner_id) is None
        or type(statement.key_id) is not str
        or _KEY_ID_RE.fullmatch(statement.key_id) is None
        or statement.key_id != f"ed25519:{statement.runner_id}:v1"
        or type(statement.key_epoch) is not int
        or statement.key_epoch != 1
        or valid_from >= valid_until
        or not valid_from <= activated_at < valid_until
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_activation_statement_invalid",
            "/statement",
        )
    expected_hash = canonical_hash(
        _activation_statement_payload(statement, include_hash=False)
    )
    if statement.statement_hash != expected_hash:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_statement_hash_invalid",
            "/statement/statement_hash",
        )
    return statement


def validate_hip_fgmres_external_runner_key_enrollment_event_v3(
    event: HipFgmresExternalRunnerKeyEnrollmentEventV3,
) -> HipFgmresExternalRunnerKeyEnrollmentEventV3:
    if type(event) is not HipFgmresExternalRunnerKeyEnrollmentEventV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_event_type_invalid",
            "/event",
        )
    validate_hip_fgmres_external_runner_key_enrollment_statement_v3(event.statement)
    _validate_approvals(event.statement, event.approvals)
    _validate_event_hash(event.statement, event.approvals, event.event_hash)
    return event


def validate_hip_fgmres_external_runner_key_activation_event_v3(
    event: HipFgmresExternalRunnerKeyActivationEventV3,
) -> HipFgmresExternalRunnerKeyActivationEventV3:
    if type(event) is not HipFgmresExternalRunnerKeyActivationEventV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_event_type_invalid",
            "/event",
        )
    validate_hip_fgmres_external_runner_key_activation_statement_v3(event.statement)
    _validate_approvals(event.statement, event.approvals)
    _validate_event_hash(event.statement, event.approvals, event.event_hash)
    return event


def validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3(
    receipt: HipFgmresExternalRunnerKeyLifecycleReceiptV3,
) -> HipFgmresExternalRunnerKeyLifecycleReceiptV3:
    if type(receipt) is not HipFgmresExternalRunnerKeyLifecycleReceiptV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_receipt_type_invalid",
            "/",
        )
    if (
        type(receipt.source_registry_receipt)
        is not registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3
        or type(receipt.enrollment_receipt)
        is not enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1
        or type(receipt.enrollment_event)
        is not HipFgmresExternalRunnerKeyEnrollmentEventV3
        or type(receipt.activation_event)
        is not HipFgmresExternalRunnerKeyActivationEventV3
        or type(receipt.active_key) is not HipFgmresExternalActiveRunnerKeyV3
        or type(receipt.claims) is not HipFgmresExternalRunnerKeyLifecycleClaimsV3
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_receipt_nested_type_invalid",
            "/",
        )
    _validate_source_receipt(receipt.source_registry_receipt)
    _validate_enrollment_receipt(receipt.enrollment_receipt)
    validate_hip_fgmres_external_runner_key_enrollment_event_v3(
        receipt.enrollment_event
    )
    validate_hip_fgmres_external_runner_key_activation_event_v3(
        receipt.activation_event
    )
    _validate_lifecycle_binding(
        receipt.source_registry_receipt,
        receipt.enrollment_receipt,
        receipt.enrollment_event,
        receipt.activation_event,
    )
    expected_enrollment_registry_hash = _registry_transition_hash(
        receipt.enrollment_event.statement,
        event_hash=receipt.enrollment_event.event_hash,
    )
    expected_registry_hash = _registry_transition_hash(
        receipt.activation_event.statement,
        event_hash=receipt.activation_event.event_hash,
    )
    expected_active_key = _derive_active_key(
        receipt.source_registry_receipt,
        receipt.enrollment_receipt,
        receipt.enrollment_event,
        receipt.activation_event,
    )
    integer_fields = (
        receipt.registry_epoch,
        receipt.predecessor_registry_epoch,
        receipt.event_count,
        receipt.reviewer_authority_count,
        receipt.enrolled_runner_key_count,
        receipt.active_runner_key_count,
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_SCHEMA_VERSION_V3
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_CAPABILITY_PROFILE_V3
        or receipt.status != HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_STATUS_V3
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_EVIDENCE_SCOPE_V3
        or receipt.promotion_eligible is not False
        or receipt.active_key != expected_active_key
        or any(type(value) is not int for value in integer_fields)
        or receipt.registry_epoch != _ACTIVATION_REGISTRY_EPOCH
        or receipt.predecessor_registry_epoch != _ENROLLMENT_REGISTRY_EPOCH
        or receipt.event_count != _ACTIVATION_REGISTRY_EPOCH
        or receipt.reviewer_authority_count != _REVIEWER_COUNT
        or receipt.enrolled_runner_key_count != 1
        or receipt.active_runner_key_count != 1
        or receipt.predecessor_registry_hash != expected_enrollment_registry_hash
        or receipt.source_registry_hash != receipt.source_registry_receipt.registry_hash
        or receipt.enrollment_registry_hash != expected_enrollment_registry_hash
        or receipt.registry_hash != expected_registry_hash
        or receipt.head_event_hash != receipt.activation_event.event_hash
        or not _claims_are_exact(receipt.claims)
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_receipt_semantics_invalid",
            "/",
        )
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_schema_invalid",
            path,
            error.message,
        )
    expected_receipt_hash = canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    )
    if receipt.receipt_hash != expected_receipt_hash:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_receipt_hash_invalid",
            "/receipt_hash",
        )
    return receipt


def validate_hip_fgmres_external_runner_key_lifecycle_result_v3(
    result: HipFgmresExternalRunnerKeyLifecycleResultV3,
) -> HipFgmresExternalRunnerKeyLifecycleResultV3:
    if type(result) is not HipFgmresExternalRunnerKeyLifecycleResultV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_result_type_invalid",
            "/",
        )
    validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3(result.receipt)
    _validate_source_result(result.source_registry_result)
    if result.receipt.source_registry_receipt != result.source_registry_result.receipt:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_binding_invalid",
            "/source_registry_result",
        )
    expected_enrollment = (
        compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
            result.source_registry_result.receipt,
            result.receipt.enrollment_receipt,
            enrolled_at_utc=result.receipt.enrollment_event.statement.occurred_at_utc,
        )
    )
    if result.receipt.enrollment_event.statement != expected_enrollment:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_binding_invalid",
            "/enrollment_event/statement",
        )
    expected_activation = (
        compile_hip_fgmres_external_runner_key_activation_statement_v3(
            result.source_registry_result.receipt,
            result.receipt.enrollment_receipt,
            result.receipt.enrollment_event,
            activated_at_utc=result.receipt.activation_event.statement.activated_at_utc,
        )
    )
    if result.receipt.activation_event.statement != expected_activation:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_binding_invalid",
            "/activation_event/statement",
        )
    return result


def _validate_statement_common(
    statement: RunnerKeyStatementV3,
    *,
    expected_purpose: str,
    expected_sequence: int,
    expected_event_type: str,
) -> None:
    if (
        type(statement.reviewer_roots) is not tuple
        or len(statement.reviewer_roots) != _REVIEWER_COUNT
        or any(
            type(root) is not bootstrap_v1.HipFgmresExternalReviewerRootV1
            for root in statement.reviewer_roots
        )
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_reviewer_roots_invalid",
            "/statement/reviewer_roots",
        )
    hashes = (
        statement.lineage_id,
        statement.previous_event_hash,
        statement.predecessor_registry_hash,
        statement.source_registry_receipt_hash,
        statement.reviewer_policy_hash,
        statement.reviewer_root_commitment_hash,
        statement.statement_hash,
    )
    if (
        statement.schema_version
        != HIP_FGMRES_EXTERNAL_RUNNER_KEY_EVENT_ACTION_SCHEMA_VERSION_V3
        or statement.purpose != expected_purpose
        or statement.registry_schema_version
        != registry_v3.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3
        or statement.registry_id != _REGISTRY_ID
        or type(statement.lineage_generation) is not int
        or statement.lineage_generation != 1
        or type(statement.sequence) is not int
        or statement.sequence != expected_sequence
        or statement.event_type != expected_event_type
        or type(statement.predecessor_registry_epoch) is not int
        or statement.predecessor_registry_epoch != expected_sequence - 1
        or type(statement.minimum_reviewer_approvals) is not int
        or statement.minimum_reviewer_approvals != _MINIMUM_REVIEWER_APPROVALS
        or any(
            type(value) is not str or _HASH_RE.fullmatch(value) is None
            for value in hashes
        )
        or statement.reviewer_root_commitment_hash
        != canonical_hash([root.to_dict() for root in statement.reviewer_roots])
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_statement_semantics_invalid",
            "/statement",
        )
    occurred_at = _parse_utc(statement.occurred_at_utc, "/statement/occurred_at_utc")
    _validate_reviewer_roots(statement.reviewer_roots, observed_at=occurred_at)


def _validate_approvals(
    statement: RunnerKeyStatementV3,
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...],
) -> None:
    if (
        type(approvals) is not tuple
        or not _MINIMUM_REVIEWER_APPROVALS <= len(approvals) <= _REVIEWER_COUNT
        or any(
            type(row) is not HipFgmresExternalRunnerKeyReviewerApprovalV3
            for row in approvals
        )
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_approvals_invalid",
            "/approvals",
        )
    roots = {root.reviewer_id: root for root in statement.reviewer_roots}
    previous_key: tuple[str, str] | None = None
    seen_reviewers: set[str] = set()
    seen_keys: set[str] = set()
    message = compile_hip_fgmres_external_runner_key_review_message_v3(statement)
    for index, row in enumerate(approvals):
        path = f"/approvals/{index}"
        root = roots.get(row.reviewer_id)
        order_key = (row.reviewer_id, row.reviewer_key_id)
        if (
            root is None
            or row.reviewer_id in seen_reviewers
            or row.reviewer_key_id in seen_keys
            or previous_key is not None
            and order_key <= previous_key
            or row.reviewer_key_id != root.key_id
            or type(row.reviewer_key_epoch) is not int
            or row.reviewer_key_epoch != root.key_epoch
            or row.statement_hash != statement.statement_hash
            or row.algorithm != ED25519_ALGORITHM_V1
            or type(row.signature_sha256) is not str
            or _HASH_RE.fullmatch(row.signature_sha256) is None
        ):
            _fail(
                "hip_fgmres_external_runner_key_lifecycle_v3_approval_invalid",
                path,
            )
        try:
            signature = decode_canonical_base64_v1(
                row.signature_base64,
                expected_byte_count=64,
                path=f"{path}/signature_base64",
            )
            if row.signature_sha256 != sha256_prefixed(signature):
                _fail(
                    "hip_fgmres_external_runner_key_lifecycle_v3_approval_invalid",
                    path,
                )
            verify_ed25519_signature_v1(
                public_key=root.public_key_bytes,
                signature_base64=row.signature_base64,
                message=message,
            )
        except (
            Ed25519EvidenceV1Error,
            bootstrap_v1.HipFgmresExternalReviewerRootBootstrapV1Error,
        ) as exc:
            _fail(
                "hip_fgmres_external_runner_key_lifecycle_v3_approval_invalid",
                path,
                getattr(exc, "code", type(exc).__name__),
            )
        seen_reviewers.add(row.reviewer_id)
        seen_keys.add(row.reviewer_key_id)
        previous_key = order_key


def _validate_event_hash(
    statement: RunnerKeyStatementV3,
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...],
    event_hash: str,
) -> None:
    expected_hash = canonical_hash(
        _event_payload(statement, approvals, event_hash=None)
    )
    if type(event_hash) is not str or event_hash != expected_hash:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_event_hash_invalid",
            "/event/event_hash",
        )


def _validate_enrollment_binding(
    source: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
    enrollment: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    statement: HipFgmresExternalRunnerKeyEnrollmentStatementV3,
) -> None:
    challenge = enrollment.challenge
    genesis = source.genesis
    if (
        statement.registry_schema_version != genesis.registry_schema_version
        or statement.registry_id != genesis.registry_id
        or statement.lineage_generation != genesis.lineage_generation
        or statement.lineage_id != genesis.lineage_id
        or statement.previous_event_hash != genesis.genesis_event_hash
        or statement.predecessor_registry_hash != source.registry_hash
        or statement.source_registry_receipt_hash != source.receipt_hash
        or statement.reviewer_policy_hash != genesis.reviewer_policy_hash
        or statement.reviewer_roots != genesis.reviewer_roots
        or statement.reviewer_root_commitment_hash
        != genesis.reviewer_root_commitment_hash
        or statement.enrollment_receipt_hash != enrollment.receipt_hash
        or statement.enrollment_challenge_hash != challenge.challenge_hash
        or statement.runner_id != challenge.runner_id
        or statement.key_id != challenge.key_id
        or statement.key_epoch != challenge.key_epoch
        or statement.public_key_sha256 != challenge.public_key_sha256
        or statement.allowed_architecture_base != challenge.allowed_architecture_base
        or statement.allowed_suite_id != challenge.allowed_suite_id
        or statement.allowed_fixture_registry_bytes_sha256
        != challenge.allowed_fixture_registry_bytes_sha256
        or statement.allowed_fixture_registry_hash
        != challenge.allowed_fixture_registry_hash
        or statement.minimum_run_sequence != challenge.minimum_run_sequence
        or statement.maximum_run_sequence != challenge.maximum_run_sequence
        or statement.valid_from_utc != challenge.valid_from_utc
        or statement.valid_until_utc != challenge.valid_until_utc
        or statement.runner_declared_key_origin != challenge.runner_declared_key_origin
        or statement.attestation_digest_sha256 != challenge.attestation_digest_sha256
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_binding_invalid",
            "/enrollment_event/statement",
        )


def _validate_lifecycle_binding(
    source: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
    enrollment: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    enrollment_event: HipFgmresExternalRunnerKeyEnrollmentEventV3,
    activation_event: HipFgmresExternalRunnerKeyActivationEventV3,
) -> None:
    _validate_enrollment_binding(source, enrollment, enrollment_event.statement)
    activation = activation_event.statement
    challenge = enrollment.challenge
    expected_enrollment_registry_hash = _registry_transition_hash(
        enrollment_event.statement,
        event_hash=enrollment_event.event_hash,
    )
    enrolled_at = _parse_utc(
        enrollment_event.statement.occurred_at_utc,
        "/enrollment_event/statement/occurred_at_utc",
    )
    activated_at = _parse_utc(
        activation.activated_at_utc,
        "/activation_event/statement/activated_at_utc",
    )
    valid_from = _parse_utc(challenge.valid_from_utc, "/key/valid_from_utc")
    valid_until = _parse_utc(challenge.valid_until_utc, "/key/valid_until_utc")
    if (
        activation.registry_schema_version != source.genesis.registry_schema_version
        or activation.registry_id != source.genesis.registry_id
        or activation.lineage_generation != source.genesis.lineage_generation
        or activation.lineage_id != source.genesis.lineage_id
        or activation.previous_event_hash != enrollment_event.event_hash
        or activation.predecessor_registry_hash != expected_enrollment_registry_hash
        or activation.source_registry_receipt_hash != source.receipt_hash
        or activation.reviewer_policy_hash != source.genesis.reviewer_policy_hash
        or activation.reviewer_roots != source.genesis.reviewer_roots
        or activation.reviewer_root_commitment_hash
        != source.genesis.reviewer_root_commitment_hash
        or activation.enrollment_event_hash != enrollment_event.event_hash
        or activation.enrollment_receipt_hash != enrollment.receipt_hash
        or activation.enrollment_challenge_hash != challenge.challenge_hash
        or activation.runner_id != challenge.runner_id
        or activation.key_id != challenge.key_id
        or activation.key_epoch != challenge.key_epoch
        or activation.public_key_sha256 != challenge.public_key_sha256
        or activation.valid_from_utc != challenge.valid_from_utc
        or activation.valid_until_utc != challenge.valid_until_utc
        or activated_at <= enrolled_at
        or not valid_from <= activated_at < valid_until
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_activation_binding_invalid",
            "/activation_event/statement",
        )


def _derive_active_key(
    source: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
    enrollment: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    enrollment_event: HipFgmresExternalRunnerKeyEnrollmentEventV3,
    activation_event: HipFgmresExternalRunnerKeyActivationEventV3,
) -> HipFgmresExternalActiveRunnerKeyV3:
    challenge = enrollment.challenge
    return HipFgmresExternalActiveRunnerKeyV3(
        status="active",
        runner_id=challenge.runner_id,
        key_id=challenge.key_id,
        key_epoch=challenge.key_epoch,
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
        runner_declared_key_origin=challenge.runner_declared_key_origin,
        attestation_digest_sha256=challenge.attestation_digest_sha256,
        source_registry_receipt_hash=source.receipt_hash,
        source_registry_hash=source.registry_hash,
        lineage_id=source.genesis.lineage_id,
        enrollment_receipt_hash=enrollment.receipt_hash,
        enrollment_challenge_hash=challenge.challenge_hash,
        enrollment_event_hash=enrollment_event.event_hash,
        enrolled_at_utc=enrollment_event.statement.occurred_at_utc,
        activation_event_hash=activation_event.event_hash,
        activated_at_utc=activation_event.statement.activated_at_utc,
    )


def _registry_transition_hash(
    statement: RunnerKeyStatementV3,
    *,
    event_hash: str,
) -> str:
    return canonical_hash(
        {
            "registry_schema_version": statement.registry_schema_version,
            "registry_id": statement.registry_id,
            "lineage_generation": statement.lineage_generation,
            "lineage_id": statement.lineage_id,
            "registry_epoch": statement.sequence,
            "predecessor_registry_hash": statement.predecessor_registry_hash,
            "head_event_hash": event_hash,
            "reviewer_root_commitment_hash": (statement.reviewer_root_commitment_hash),
        }
    )


def _validate_reviewer_roots(
    roots: tuple[bootstrap_v1.HipFgmresExternalReviewerRootV1, ...],
    *,
    observed_at: datetime,
) -> None:
    if (
        type(roots) is not tuple
        or len(roots) != _REVIEWER_COUNT
        or any(
            type(root) is not bootstrap_v1.HipFgmresExternalReviewerRootV1
            for root in roots
        )
        or tuple((root.reviewer_id, root.key_id) for root in roots)
        != tuple(sorted((root.reviewer_id, root.key_id) for root in roots))
    ):
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_reviewer_roots_invalid",
            "/statement/reviewer_roots",
        )
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    seen_hashes: set[str] = set()
    for index, root in enumerate(roots):
        path = f"/statement/reviewer_roots/{index}"
        try:
            public_key = validate_ed25519_public_key_v1(root.public_key_bytes)
        except (
            Ed25519EvidenceV1Error,
            bootstrap_v1.HipFgmresExternalReviewerRootBootstrapV1Error,
        ) as exc:
            _fail(
                "hip_fgmres_external_runner_key_lifecycle_v3_reviewer_root_invalid",
                path,
                getattr(exc, "code", type(exc).__name__),
            )
        valid_from = _parse_utc(root.valid_from_utc, f"{path}/valid_from_utc")
        valid_until = _parse_utc(root.valid_until_utc, f"{path}/valid_until_utc")
        if (
            type(root.reviewer_id) is not str
            or _REVIEWER_ID_RE.fullmatch(root.reviewer_id) is None
            or type(root.key_id) is not str
            or _REVIEWER_KEY_ID_RE.fullmatch(root.key_id) is None
            or root.key_id != f"ed25519-review:{root.reviewer_id}:v1"
            or type(root.key_epoch) is not int
            or root.key_epoch != 1
            or root.public_key_sha256 != sha256_prefixed(public_key)
            or valid_from >= valid_until
            or not valid_from <= observed_at < valid_until
            or root.reviewer_id in seen_ids
            or root.key_id in seen_keys
            or root.public_key_sha256 in seen_hashes
        ):
            _fail(
                "hip_fgmres_external_runner_key_lifecycle_v3_reviewer_root_invalid",
                path,
            )
        seen_ids.add(root.reviewer_id)
        seen_keys.add(root.key_id)
        seen_hashes.add(root.public_key_sha256)


def _validate_source_receipt(
    receipt: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
) -> None:
    if type(receipt) is not registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_type_invalid",
            "/source_registry_receipt",
        )
    try:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(
            receipt
        )
    except registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error as exc:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_invalid",
            "/source_registry_receipt",
            exc.code,
        )


def _validate_source_result(
    result: registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3,
) -> None:
    if type(result) is not registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_type_invalid",
            "/source_registry_result",
        )
    try:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_result_v3(result)
    except registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error as exc:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_source_invalid",
            "/source_registry_result",
            exc.code,
        )


def _validate_enrollment_receipt(
    receipt: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
) -> None:
    if type(receipt) is not enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_type_invalid",
            "/enrollment_receipt",
        )
    try:
        enrollment_v1.validate_hip_fgmres_external_key_enrollment_receipt_v1(receipt)
    except enrollment_v1.HipFgmresExternalKeyEnrollmentV1Error as exc:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_invalid",
            "/enrollment_receipt",
            exc.code,
        )


def _claims_are_exact(claims: HipFgmresExternalRunnerKeyLifecycleClaimsV3) -> bool:
    expected = HipFgmresExternalRunnerKeyLifecycleClaimsV3()
    return all(
        getattr(claims, name) is getattr(expected, name)
        for name in expected.__dataclass_fields__
    )


def _common_statement_payload(statement: RunnerKeyStatementV3) -> dict[str, Any]:
    return {
        "schema_version": statement.schema_version,
        "purpose": statement.purpose,
        "registry_schema_version": statement.registry_schema_version,
        "registry_id": statement.registry_id,
        "lineage_generation": statement.lineage_generation,
        "lineage_id": statement.lineage_id,
        "sequence": statement.sequence,
        "event_type": statement.event_type,
        "occurred_at_utc": statement.occurred_at_utc,
        "previous_event_hash": statement.previous_event_hash,
        "predecessor_registry_epoch": statement.predecessor_registry_epoch,
        "predecessor_registry_hash": statement.predecessor_registry_hash,
        "source_registry_receipt_hash": statement.source_registry_receipt_hash,
        "reviewer_policy_hash": statement.reviewer_policy_hash,
        "reviewer_roots": [root.to_dict() for root in statement.reviewer_roots],
        "reviewer_root_commitment_hash": statement.reviewer_root_commitment_hash,
        "minimum_reviewer_approvals": statement.minimum_reviewer_approvals,
    }


def _enrollment_statement_payload(
    statement: HipFgmresExternalRunnerKeyEnrollmentStatementV3,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = _common_statement_payload(statement)
    payload.update(
        {
            "enrollment_receipt_schema_version": (
                statement.enrollment_receipt_schema_version
            ),
            "enrollment_receipt_hash": statement.enrollment_receipt_hash,
            "enrollment_challenge_hash": statement.enrollment_challenge_hash,
            "runner_id": statement.runner_id,
            "key_id": statement.key_id,
            "key_epoch": statement.key_epoch,
            "public_key_sha256": statement.public_key_sha256,
            "allowed_architecture_base": statement.allowed_architecture_base,
            "allowed_suite_id": statement.allowed_suite_id,
            "allowed_fixture_registry_bytes_sha256": (
                statement.allowed_fixture_registry_bytes_sha256
            ),
            "allowed_fixture_registry_hash": (statement.allowed_fixture_registry_hash),
            "minimum_run_sequence": statement.minimum_run_sequence,
            "maximum_run_sequence": statement.maximum_run_sequence,
            "valid_from_utc": statement.valid_from_utc,
            "valid_until_utc": statement.valid_until_utc,
            "runner_declared_key_origin": statement.runner_declared_key_origin,
            "attestation_digest_sha256": statement.attestation_digest_sha256,
        }
    )
    if include_hash:
        payload["statement_hash"] = statement.statement_hash
    return payload


def _activation_statement_payload(
    statement: HipFgmresExternalRunnerKeyActivationStatementV3,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = _common_statement_payload(statement)
    payload.update(
        {
            "enrollment_event_hash": statement.enrollment_event_hash,
            "enrollment_receipt_hash": statement.enrollment_receipt_hash,
            "enrollment_challenge_hash": statement.enrollment_challenge_hash,
            "runner_id": statement.runner_id,
            "key_id": statement.key_id,
            "key_epoch": statement.key_epoch,
            "public_key_sha256": statement.public_key_sha256,
            "valid_from_utc": statement.valid_from_utc,
            "valid_until_utc": statement.valid_until_utc,
            "activated_at_utc": statement.activated_at_utc,
        }
    )
    if include_hash:
        payload["statement_hash"] = statement.statement_hash
    return payload


def _event_payload(
    statement: RunnerKeyStatementV3,
    approvals: tuple[HipFgmresExternalRunnerKeyReviewerApprovalV3, ...],
    event_hash: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "statement": statement.to_dict(),
        "approvals": [row.to_dict() for row in approvals],
    }
    if event_hash is not None:
        payload["event_hash"] = event_hash
    return payload


def _receipt_payload(
    receipt: HipFgmresExternalRunnerKeyLifecycleReceiptV3,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "source_registry_receipt": receipt.source_registry_receipt.to_dict(),
        "enrollment_receipt": receipt.enrollment_receipt.to_dict(),
        "enrollment_event": receipt.enrollment_event.to_dict(),
        "activation_event": receipt.activation_event.to_dict(),
        "active_key": receipt.active_key.to_dict(),
        "registry_epoch": receipt.registry_epoch,
        "predecessor_registry_epoch": receipt.predecessor_registry_epoch,
        "predecessor_registry_hash": receipt.predecessor_registry_hash,
        "source_registry_hash": receipt.source_registry_hash,
        "enrollment_registry_hash": receipt.enrollment_registry_hash,
        "registry_hash": receipt.registry_hash,
        "head_event_hash": receipt.head_event_hash,
        "event_count": receipt.event_count,
        "reviewer_authority_count": receipt.reviewer_authority_count,
        "enrolled_runner_key_count": receipt.enrolled_runner_key_count,
        "active_runner_key_count": receipt.active_runner_key_count,
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _parse_utc(value: str, path: str) -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_timestamp_invalid",
            path,
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_timestamp_invalid",
            path,
        )
    if parsed.tzinfo != timezone.utc or _format_utc(parsed) != value:
        _fail(
            "hip_fgmres_external_runner_key_lifecycle_v3_timestamp_invalid",
            path,
        )
    return parsed


def _format_utc(value: datetime) -> str:
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalRunnerKeyLifecycleV3Error(code, path, message)


__all__ = [
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_ACTIVATION_PURPOSE_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_ENROLLMENT_PURPOSE_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_EVENT_ACTION_SCHEMA_VERSION_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_CAPABILITY_PROFILE_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_EVIDENCE_SCOPE_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_SCHEMA_VERSION_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_LIFECYCLE_STATUS_V3",
    "HIP_FGMRES_EXTERNAL_RUNNER_KEY_REVIEW_DOMAIN_V3",
    "HipFgmresExternalActiveRunnerKeyV3",
    "HipFgmresExternalRunnerKeyActivationEventV3",
    "HipFgmresExternalRunnerKeyActivationStatementV3",
    "HipFgmresExternalRunnerKeyEnrollmentEventV3",
    "HipFgmresExternalRunnerKeyEnrollmentStatementV3",
    "HipFgmresExternalRunnerKeyLifecycleClaimsV3",
    "HipFgmresExternalRunnerKeyLifecycleReceiptV3",
    "HipFgmresExternalRunnerKeyLifecycleResultV3",
    "HipFgmresExternalRunnerKeyLifecycleV3Error",
    "HipFgmresExternalRunnerKeyReviewerApprovalV3",
    "compile_hip_fgmres_external_runner_key_activation_statement_v3",
    "compile_hip_fgmres_external_runner_key_enrollment_statement_v3",
    "compile_hip_fgmres_external_runner_key_review_message_v3",
    "finalize_hip_fgmres_external_runner_key_activation_event_v3",
    "finalize_hip_fgmres_external_runner_key_enrollment_event_v3",
    "validate_hip_fgmres_external_runner_key_activation_event_v3",
    "validate_hip_fgmres_external_runner_key_activation_statement_v3",
    "validate_hip_fgmres_external_runner_key_enrollment_event_v3",
    "validate_hip_fgmres_external_runner_key_enrollment_statement_v3",
    "validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3",
    "validate_hip_fgmres_external_runner_key_lifecycle_result_v3",
    "verify_hip_fgmres_external_runner_key_lifecycle_v3",
]
