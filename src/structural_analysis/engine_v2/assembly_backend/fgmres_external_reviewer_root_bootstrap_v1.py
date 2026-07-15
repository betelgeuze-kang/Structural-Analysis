"""Detached reviewer-root ceremony and package-pinned pending bootstrap status.

The v2 trust registry has an immutable empty reviewer commitment.  It cannot
cryptographically authorize a non-empty successor.  This module therefore
defines a fresh-genesis ceremony that binds the exact v2 empty lineage and
requires every target reviewer root to endorse one canonical plan.

Detached endorsements verify possession signatures under the listed public
keys over one exact plan only.  They do not activate a registry.  The package-owned public
loader currently returns an exact, code-pinned pending status with no reviewer
material.  No signing or private-key API is provided here.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from importlib import resources
import json
import math
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator, SchemaError

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

from .fgmres_external_trust_anchor_registry_v2 import (
    HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2,
    HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2,
    HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2,
    HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2,
    HipFgmresExternalTrustAnchorRegistryResultV2,
    load_hip_fgmres_external_trust_anchor_registry_v2,
)


HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PLAN_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-reviewer-root-bootstrap-plan.v1"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-reviewer-root-bootstrap-receipt.v1"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_STATUS_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-reviewer-root-bootstrap-status.v1"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1 = (
    "phase0_external_gfx1100_reviewer_root_new_trust_genesis"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PURPOSE_V1 = (
    "hip_fgmres_external_reviewer_root_new_trust_genesis"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_ENDORSEMENT_DOMAIN_V1 = (
    b"structural-analysis/engine-v2/hip-fgmres/"
    b"reviewer-root-bootstrap-endorsement/v1\x00"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_LINEAGE_DOMAIN_V1 = (
    b"structural-analysis/engine-v2/hip-fgmres/reviewer-root-bootstrap-lineage/v1\x00"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_DETACHED_EVIDENCE_SCOPE_V1 = (
    "detached_target_root_possession_signatures_non_authoritative"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PACKAGE_EVIDENCE_SCOPE_V1 = (
    "package_owned_bootstrap_contract_pending_external_roots"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-trust-anchor-registry.v3"
)
HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1 = (
    "structural-analysis-engine-v2-external-trust-registry-reviewer-root-v3"
)

_RESOURCE_PACKAGE_V1 = (
    "structural_analysis.engine_v2.assembly_backend.fixtures."
    "fgmres_external_reviewer_root_bootstrap_v1"
)
_SOURCE_REGISTRY_RESOURCE_PACKAGE_V1 = (
    "structural_analysis.engine_v2.assembly_backend.fixtures."
    "fgmres_external_trust_anchors_v2"
)
_STATUS_RESOURCE_V1 = "status.v1.json"
_SOURCE_REGISTRY_RESOURCE_V1 = "registry.v2.json"
_SCHEMA_RESOURCE_V1 = "hip_fgmres_external_reviewer_root_bootstrap_v1.schema.json"
_SOURCE_REGISTRY_SCHEMA_RESOURCE_V1 = (
    "hip_fgmres_external_trust_anchor_registry_v2.schema.json"
)
_SCHEMA_RESOURCE_BYTES_SHA256_V1 = (
    "sha256:f15ca0fe364706e3d6889ac13e61eb73cd3acbadc169b287f903863434b20fda"
)
_STATUS_RESOURCE_BYTES_SHA256_V1 = (
    "sha256:253945078b9d84d9a816d835978ba033073f94fefe76715f9a7f17bf956bbbaa"
)

_SOURCE_REGISTRY_SCHEMA_BYTES_SHA256_V1 = (
    "sha256:d8ed736d9c98959d18a50467e3e0a919504c538dd44e510ee83b0ff016278c6e"
)
_SOURCE_REGISTRY_BYTES_SHA256_V1 = (
    "sha256:dfa6172c8819f812d9992f64e6e3d5fa0f97e7c2651b49ca7ee47ccc557a2fbc"
)
_SOURCE_REGISTRY_HASH_V1 = (
    "sha256:5dc12aa7bb553f1852eb702f1d0ad6f3b927f193dcd7ce28f85a5c9658d6b1e4"
)
_SOURCE_HEAD_EVENT_HASH_V1 = (
    "sha256:0742df80dcb3c737362fac6c4c409668976b10a030a35f5305e9951f527b1813"
)
_SOURCE_HEAD_OCCURRED_AT_UTC_V1 = "2026-07-15T00:00:00Z"
_SOURCE_REVIEWER_COMMITMENT_HASH_V1 = (
    "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)
_SOURCE_REPLAY_RECEIPT_HASH_V1 = (
    "sha256:3330f6e4ca6738faf02e2244441241cbe0998c1a0a0ce13a1aa85a6826da345f"
)
_SOURCE_AUTHORITY_MODE_V1 = "empty_genesis_no_signing_authority"

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_REVIEWER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_REVIEWER_KEY_ID_RE = re.compile(r"^ed25519-review:[a-z0-9][a-z0-9._-]{2,63}:v1$")
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z$"
)
_TARGET_LINEAGE_GENERATION_V1 = 1
_REVIEWER_COUNT_V1 = 3
_MINIMUM_EVENT_APPROVALS_V1 = 2
_BOOTSTRAP_ENDORSEMENT_COUNT_V1 = 3
_MAX_RESOURCE_BYTES_V1 = 256 * 1024
_MAX_JSON_NODES_V1 = 20_000
_MAX_JSON_DEPTH_V1 = 48
_MAX_ERROR_PATH_CHARS_V1 = 512
_MAX_ERROR_MESSAGE_CHARS_V1 = 240


class HipFgmresExternalReviewerRootBootstrapV1Error(RuntimeError):
    """Stable fail-closed reviewer-root bootstrap error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = _bounded_path_v1(path)
        self.message = (message or code)[:_MAX_ERROR_MESSAGE_CHARS_V1]
        super().__init__(f"{code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerBootstrapSourceRegistryV1:
    """Exact v0.2.37 empty source lineage; it has no signing authority."""

    schema_version: str
    capability_profile: str
    evidence_scope: str
    registry_id: str
    registry_schema_bytes_sha256: str
    registry_bytes_sha256: str
    registry_hash: str
    registry_epoch: int
    predecessor_registry_epoch: int
    predecessor_registry_hash: str | None
    head_event_hash: str
    head_event_occurred_at_utc: str
    event_count: int
    reviewer_authority_count: int
    reviewer_authority_commitment_hash: str
    enrolled_key_count: int
    active_key_count: int
    replay_receipt_hash: str
    source_authority_mode: str
    authority_continuity_available: Literal[False]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerBootstrapPolicyV1:
    """Fixed first-lineage policy: all roots bootstrap, 2-of-3 operate."""

    algorithm: str = ED25519_ALGORITHM_V1
    reviewer_count: int = _REVIEWER_COUNT_V1
    minimum_event_approvals: int = _MINIMUM_EVENT_APPROVALS_V1
    bootstrap_endorsement_count: int = _BOOTSTRAP_ENDORSEMENT_COUNT_V1
    target_genesis_activation_endorsement_count: int = _BOOTSTRAP_ENDORSEMENT_COUNT_V1
    target_genesis_binds_bootstrap_plan_and_receipt_hashes: Literal[True] = True
    lineage_bound_runner_enrollment_required: Literal[True] = True
    reviewer_root_set_immutable: Literal[True] = True
    reviewer_rotation_requires_new_lineage: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootV1:
    """One public reviewer root.  No identity or key-origin claim is encoded."""

    reviewer_id: str
    key_id: str
    key_epoch: int
    public_key_base64: str
    public_key_sha256: str
    valid_from_utc: str
    valid_until_utc: str

    @property
    def public_key_bytes(self) -> bytes:
        return _decode_public_key_v1(
            self.public_key_base64,
            path="/reviewer_root/public_key_base64",
        )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootBootstrapPlanV1:
    """Canonical self-hashed fresh-genesis statement signed by all roots."""

    schema_version: str
    capability_profile: str
    purpose: str
    ceremony_id: str
    nonce_base64: str
    bootstrap_at_utc: str
    source_registry: HipFgmresExternalReviewerBootstrapSourceRegistryV1
    source_lineage_commitment_hash: str
    target_registry_schema_version: str
    target_registry_id: str
    target_lineage_generation: int
    target_lineage_nonce_base64: str
    reviewer_policy: HipFgmresExternalReviewerBootstrapPolicyV1
    reviewer_policy_hash: str
    reviewer_roots: tuple[HipFgmresExternalReviewerRootV1, ...]
    reviewer_root_commitment_hash: str
    target_lineage_id: str
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(self)
        return _plan_payload_v1(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootEndorsementV1:
    """One detached Ed25519 signature over the exact bootstrap plan."""

    reviewer_id: str
    reviewer_key_id: str
    reviewer_key_epoch: int
    plan_hash: str
    algorithm: str
    signature_base64: str
    signature_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootBootstrapClaimsV1:
    """Narrow detached claims; no package or operational authority is minted."""

    exact_empty_source_lineage_bound: Literal[True] = True
    all_target_reviewer_private_key_possession_signatures_verified: Literal[True] = True
    all_target_reviewer_exact_plan_signatures_verified: Literal[True] = True
    package_bootstrap_inclusion_verified: Literal[False] = False
    target_registry_genesis_activated: Literal[False] = False
    predecessor_reviewer_authority_continuity_verified: Literal[False] = False
    reviewer_human_identity_verified: Literal[False] = False
    reviewer_independence_verified: Literal[False] = False
    reviewer_hsm_origin_verified: Literal[False] = False
    reviewer_hsm_non_exportability_verified: Literal[False] = False
    trusted_ceremony_time_verified: Literal[False] = False
    ceremony_nonce_entropy_and_uniqueness_verified: Literal[False] = False
    hostile_same_process_mutation_resistance_verified: Literal[False] = False
    external_monotonic_anchor_verified: Literal[False] = False
    historical_recovery_verified: Literal[False] = False
    runner_key_activation_verified: Literal[False] = False
    hardware_execution_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False
    commercial_ready: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootBootstrapReceiptV1:
    """Revalidatable but non-authoritative all-root endorsement receipt."""

    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1
    endorsements: tuple[HipFgmresExternalReviewerRootEndorsementV1, ...]
    claims: HipFgmresExternalReviewerRootBootstrapClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(self)
        return _receipt_payload_v1(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootBootstrapStatusClaimsV1:
    """Exact package status: the contract exists but reviewer roots do not."""

    package_owned_contract_loaded: Literal[True] = True
    code_anchored_raw_contract_verified: Literal[True] = True
    exact_empty_source_lineage_bound: Literal[True] = True
    source_has_signing_authority: Literal[False] = False
    fresh_genesis_required: Literal[True] = True
    reviewer_root_material_present: Literal[False] = False
    reviewer_root_possession_signatures_verified: Literal[False] = False
    package_bootstrap_inclusion_verified: Literal[False] = False
    target_registry_genesis_activated: Literal[False] = False
    predecessor_reviewer_authority_continuity_verified: Literal[False] = False
    reviewer_human_identity_verified: Literal[False] = False
    reviewer_independence_verified: Literal[False] = False
    reviewer_hsm_verified: Literal[False] = False
    ceremony_nonce_entropy_and_uniqueness_verified: Literal[False] = False
    hostile_same_process_mutation_resistance_verified: Literal[False] = False
    external_monotonic_anchor_verified: Literal[False] = False
    historical_recovery_verified: Literal[False] = False
    runner_key_activation_verified: Literal[False] = False
    hardware_execution_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False
    commercial_ready: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootBootstrapStatusV1:
    """Result of replaying the one code-pinned package pending status."""

    contract_bytes_sha256: str
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    source_registry: HipFgmresExternalReviewerBootstrapSourceRegistryV1
    source_lineage_commitment_hash: str
    target_registry_schema_version: str
    target_registry_id: str
    target_lineage_generation: int
    reviewer_policy: HipFgmresExternalReviewerBootstrapPolicyV1
    reviewer_policy_hash: str
    bootstrap_plan: None
    bootstrap_receipt: None
    claims: HipFgmresExternalReviewerRootBootstrapStatusClaimsV1
    status_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_reviewer_root_bootstrap_status_v1(self)
        payload = _package_status_payload_v1(self, include_hash=True)
        return {"contract_bytes_sha256": self.contract_bytes_sha256, **payload}


def compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
    *,
    ceremony_id: str,
    nonce: bytes,
    bootstrap_at_utc: str,
    target_lineage_nonce: bytes,
    reviewer_roots: tuple[HipFgmresExternalReviewerRootV1, ...],
) -> HipFgmresExternalReviewerRootBootstrapPlanV1:
    """Compile a fresh-genesis plan; the exact current empty v2 source is used."""

    if type(nonce) is not bytes or len(nonce) != 32:
        _fail("hip_fgmres_external_reviewer_bootstrap_nonce_invalid", "/nonce")
    if type(target_lineage_nonce) is not bytes or len(target_lineage_nonce) != 32:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_lineage_nonce_invalid",
            "/target_lineage_nonce",
        )
    if nonce == target_lineage_nonce:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_nonce_reuse",
            "/target_lineage_nonce",
        )
    if (
        type(reviewer_roots) is not tuple
        or len(reviewer_roots) != _REVIEWER_COUNT_V1
        or any(
            type(root) is not HipFgmresExternalReviewerRootV1 for root in reviewer_roots
        )
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_reviewer_roots_invalid",
            "/reviewer_roots",
        )
    if (
        type(ceremony_id) is not str
        or len(ceremony_id) > 128
        or _ID_RE.fullmatch(ceremony_id) is None
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_ceremony_id_invalid",
            "/ceremony_id",
        )
    bootstrap_at = _parse_utc_v1(bootstrap_at_utc, "/bootstrap_at_utc")
    source_head_at = _parse_utc_v1(
        _SOURCE_HEAD_OCCURRED_AT_UTC_V1,
        "/source_registry/head_event_occurred_at_utc",
    )
    if bootstrap_at <= source_head_at:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_time_order_invalid",
            "/bootstrap_at_utc",
        )
    _validate_reviewer_roots_v1(reviewer_roots, bootstrap_at=bootstrap_at)
    source = _load_exact_source_identity_v1()
    policy = HipFgmresExternalReviewerBootstrapPolicyV1()
    source_commitment = canonical_hash(source.to_dict())
    policy_hash = canonical_hash(policy.to_dict())
    roots_payload = [root.to_dict() for root in reviewer_roots]
    roots_commitment = canonical_hash(roots_payload)
    nonce_base64 = base64.b64encode(nonce).decode("ascii")
    lineage_nonce_base64 = base64.b64encode(target_lineage_nonce).decode("ascii")
    target_lineage_id = _target_lineage_id_v1(
        ceremony_id=ceremony_id,
        nonce_base64=nonce_base64,
        bootstrap_at_utc=bootstrap_at_utc,
        source_lineage_commitment_hash=source_commitment,
        target_lineage_nonce_base64=lineage_nonce_base64,
        reviewer_policy_hash=policy_hash,
        reviewer_root_commitment_hash=roots_commitment,
    )
    draft = HipFgmresExternalReviewerRootBootstrapPlanV1(
        schema_version=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PLAN_SCHEMA_VERSION_V1
        ),
        capability_profile=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1
        ),
        purpose=HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PURPOSE_V1,
        ceremony_id=ceremony_id,
        nonce_base64=nonce_base64,
        bootstrap_at_utc=bootstrap_at_utc,
        source_registry=source,
        source_lineage_commitment_hash=source_commitment,
        target_registry_schema_version=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1
        ),
        target_registry_id=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1
        ),
        target_lineage_generation=_TARGET_LINEAGE_GENERATION_V1,
        target_lineage_nonce_base64=lineage_nonce_base64,
        reviewer_policy=policy,
        reviewer_policy_hash=policy_hash,
        reviewer_roots=reviewer_roots,
        reviewer_root_commitment_hash=roots_commitment,
        target_lineage_id=target_lineage_id,
        plan_hash=_ZERO_HASH,
    )
    plan = replace(
        draft,
        plan_hash=canonical_hash(_plan_payload_v1(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(plan)


def compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1(
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1,
) -> bytes:
    """Return the exact domain-separated bytes every target root must sign."""

    validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(plan)
    return _endorsement_message_v1(plan)


def verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1,
    *,
    endorsements: tuple[HipFgmresExternalReviewerRootEndorsementV1, ...],
) -> HipFgmresExternalReviewerRootBootstrapReceiptV1:
    """Verify all three root endorsements and return a detached receipt."""

    validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(plan)
    if (
        type(endorsements) is not tuple
        or len(endorsements) != _BOOTSTRAP_ENDORSEMENT_COUNT_V1
        or any(
            type(item) is not HipFgmresExternalReviewerRootEndorsementV1
            for item in endorsements
        )
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_endorsements_invalid",
            "/endorsements",
        )
    _validate_endorsements_v1(plan, endorsements)
    draft = HipFgmresExternalReviewerRootBootstrapReceiptV1(
        schema_version=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_RECEIPT_SCHEMA_VERSION_V1
        ),
        capability_profile=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1
        ),
        status="detached_all_target_reviewer_root_endorsements_verified",
        evidence_scope=(
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_DETACHED_EVIDENCE_SCOPE_V1
        ),
        plan=plan,
        endorsements=endorsements,
        claims=HipFgmresExternalReviewerRootBootstrapClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload_v1(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(receipt)


def validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1,
) -> HipFgmresExternalReviewerRootBootstrapPlanV1:
    if (
        type(plan) is not HipFgmresExternalReviewerRootBootstrapPlanV1
        or type(plan.source_registry)
        is not HipFgmresExternalReviewerBootstrapSourceRegistryV1
        or type(plan.reviewer_policy) is not HipFgmresExternalReviewerBootstrapPolicyV1
        or type(plan.reviewer_roots) is not tuple
        or len(plan.reviewer_roots) != _REVIEWER_COUNT_V1
        or any(
            type(root) is not HipFgmresExternalReviewerRootV1
            for root in plan.reviewer_roots
        )
    ):
        _fail("hip_fgmres_external_reviewer_bootstrap_plan_type_invalid", "/")
    payload = _plan_payload_v1(plan, include_hash=True)
    _validate_schema_v1(payload, path="/plan")
    exact_source = _load_exact_source_identity_v1()
    exact_policy = HipFgmresExternalReviewerBootstrapPolicyV1()
    bootstrap_at = _parse_utc_v1(plan.bootstrap_at_utc, "/bootstrap_at_utc")
    source_head_at = _parse_utc_v1(
        _SOURCE_HEAD_OCCURRED_AT_UTC_V1,
        "/source_registry/head_event_occurred_at_utc",
    )
    nonce = _decode_base64_v1(
        plan.nonce_base64,
        expected_byte_count=32,
        path="/nonce_base64",
    )
    lineage_nonce = _decode_base64_v1(
        plan.target_lineage_nonce_base64,
        expected_byte_count=32,
        path="/target_lineage_nonce_base64",
    )
    if (
        plan.schema_version
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PLAN_SCHEMA_VERSION_V1
        or plan.capability_profile
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1
        or plan.purpose != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PURPOSE_V1
        or type(plan.ceremony_id) is not str
        or len(plan.ceremony_id) > 128
        or _ID_RE.fullmatch(plan.ceremony_id) is None
        or nonce == lineage_nonce
        or bootstrap_at <= source_head_at
        or not _dataclass_fields_exact_v1(plan.source_registry, exact_source)
        or plan.source_lineage_commitment_hash != canonical_hash(exact_source.to_dict())
        or plan.target_registry_schema_version
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1
        or plan.target_registry_id
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1
        or plan.target_registry_id == plan.source_registry.registry_id
        or type(plan.target_lineage_generation) is not int
        or plan.target_lineage_generation != _TARGET_LINEAGE_GENERATION_V1
        or not _dataclass_fields_exact_v1(plan.reviewer_policy, exact_policy)
        or plan.reviewer_policy_hash != canonical_hash(exact_policy.to_dict())
    ):
        _fail("hip_fgmres_external_reviewer_bootstrap_plan_semantics_invalid", "/plan")
    _validate_reviewer_roots_v1(plan.reviewer_roots, bootstrap_at=bootstrap_at)
    roots_payload = [root.to_dict() for root in plan.reviewer_roots]
    if (
        plan.reviewer_root_commitment_hash != canonical_hash(roots_payload)
        or plan.target_lineage_id
        != _target_lineage_id_v1(
            ceremony_id=plan.ceremony_id,
            nonce_base64=plan.nonce_base64,
            bootstrap_at_utc=plan.bootstrap_at_utc,
            source_lineage_commitment_hash=plan.source_lineage_commitment_hash,
            target_lineage_nonce_base64=plan.target_lineage_nonce_base64,
            reviewer_policy_hash=plan.reviewer_policy_hash,
            reviewer_root_commitment_hash=plan.reviewer_root_commitment_hash,
        )
        or plan.plan_hash != canonical_hash(_plan_payload_v1(plan, include_hash=False))
    ):
        _fail("hip_fgmres_external_reviewer_bootstrap_plan_hash_invalid", "/plan_hash")
    return plan


def validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
    receipt: HipFgmresExternalReviewerRootBootstrapReceiptV1,
) -> HipFgmresExternalReviewerRootBootstrapReceiptV1:
    if (
        type(receipt) is not HipFgmresExternalReviewerRootBootstrapReceiptV1
        or type(receipt.plan) is not HipFgmresExternalReviewerRootBootstrapPlanV1
        or type(receipt.endorsements) is not tuple
        or len(receipt.endorsements) != _BOOTSTRAP_ENDORSEMENT_COUNT_V1
        or any(
            type(item) is not HipFgmresExternalReviewerRootEndorsementV1
            for item in receipt.endorsements
        )
        or type(receipt.claims) is not HipFgmresExternalReviewerRootBootstrapClaimsV1
    ):
        _fail("hip_fgmres_external_reviewer_bootstrap_receipt_type_invalid", "/")
    validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(receipt.plan)
    payload = _receipt_payload_v1(receipt, include_hash=True)
    _validate_schema_v1(payload, path="/receipt")
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_RECEIPT_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1
        or receipt.status != "detached_all_target_reviewer_root_endorsements_verified"
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_DETACHED_EVIDENCE_SCOPE_V1
        or not _dataclass_fields_exact_v1(
            receipt.claims,
            HipFgmresExternalReviewerRootBootstrapClaimsV1(),
        )
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_receipt_semantics_invalid",
            "/receipt",
        )
    _validate_endorsements_v1(receipt.plan, receipt.endorsements)
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload_v1(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_receipt_hash_invalid",
            "/receipt_hash",
        )
    return receipt


def load_hip_fgmres_external_reviewer_root_bootstrap_status_v1() -> (
    HipFgmresExternalReviewerRootBootstrapStatusV1
):
    """Load the one package-owned pending contract; no caller path is accepted."""

    return _BOOTSTRAP_STATUS_LOADER_AUTHORITY_V1()


def validate_hip_fgmres_external_reviewer_root_bootstrap_status_v1(
    status: HipFgmresExternalReviewerRootBootstrapStatusV1,
) -> HipFgmresExternalReviewerRootBootstrapStatusV1:
    """Require an exact replay of the current code-pinned package status."""

    _validate_package_status_result_v1(status)
    expected = _BOOTSTRAP_STATUS_LOADER_AUTHORITY_V1()
    if status != expected:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_package_replay_mismatch",
            "/",
        )
    return status


def _compile_package_status_v1(
    manifest: dict[str, Any],
    *,
    contract_bytes_sha256: str,
) -> HipFgmresExternalReviewerRootBootstrapStatusV1:
    if type(manifest) is not dict or not _is_hash_v1(contract_bytes_sha256):
        _fail("hip_fgmres_external_reviewer_bootstrap_status_invalid", "/")
    _validate_schema_v1(manifest, path="/status")
    try:
        source = HipFgmresExternalReviewerBootstrapSourceRegistryV1(
            **manifest["source_registry"]
        )
        policy = HipFgmresExternalReviewerBootstrapPolicyV1(
            **manifest["reviewer_policy"]
        )
        claims = HipFgmresExternalReviewerRootBootstrapStatusClaimsV1(
            **manifest["claims"]
        )
    except (KeyError, TypeError) as exc:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_status_invalid",
            "/status",
            type(exc).__name__,
        )
    result = HipFgmresExternalReviewerRootBootstrapStatusV1(
        contract_bytes_sha256=contract_bytes_sha256,
        schema_version=manifest["schema_version"],
        capability_profile=manifest["capability_profile"],
        status=manifest["status"],
        evidence_scope=manifest["evidence_scope"],
        source_registry=source,
        source_lineage_commitment_hash=manifest["source_lineage_commitment_hash"],
        target_registry_schema_version=manifest["target_registry_schema_version"],
        target_registry_id=manifest["target_registry_id"],
        target_lineage_generation=manifest["target_lineage_generation"],
        reviewer_policy=policy,
        reviewer_policy_hash=manifest["reviewer_policy_hash"],
        bootstrap_plan=manifest["bootstrap_plan"],
        bootstrap_receipt=manifest["bootstrap_receipt"],
        claims=claims,
        status_hash=manifest["status_hash"],
    )
    return _validate_package_status_result_v1(result)


def _validate_package_status_result_v1(
    status: HipFgmresExternalReviewerRootBootstrapStatusV1,
) -> HipFgmresExternalReviewerRootBootstrapStatusV1:
    if (
        type(status) is not HipFgmresExternalReviewerRootBootstrapStatusV1
        or type(status.source_registry)
        is not HipFgmresExternalReviewerBootstrapSourceRegistryV1
        or type(status.reviewer_policy)
        is not HipFgmresExternalReviewerBootstrapPolicyV1
        or type(status.claims)
        is not HipFgmresExternalReviewerRootBootstrapStatusClaimsV1
    ):
        _fail("hip_fgmres_external_reviewer_bootstrap_status_type_invalid", "/")
    exact_source = _load_exact_source_identity_v1()
    exact_policy = HipFgmresExternalReviewerBootstrapPolicyV1()
    manifest = _package_status_payload_v1(status, include_hash=True)
    _validate_schema_v1(manifest, path="/status")
    if (
        status.contract_bytes_sha256 != _STATUS_RESOURCE_BYTES_SHA256_V1
        or status.schema_version
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_STATUS_SCHEMA_VERSION_V1
        or status.capability_profile
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1
        or status.status != "pending_independent_reviewer_root_material"
        or status.evidence_scope
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PACKAGE_EVIDENCE_SCOPE_V1
        or not _dataclass_fields_exact_v1(status.source_registry, exact_source)
        or status.source_lineage_commitment_hash
        != canonical_hash(exact_source.to_dict())
        or status.target_registry_schema_version
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1
        or status.target_registry_id
        != HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1
        or status.target_registry_id == status.source_registry.registry_id
        or type(status.target_lineage_generation) is not int
        or status.target_lineage_generation != _TARGET_LINEAGE_GENERATION_V1
        or not _dataclass_fields_exact_v1(status.reviewer_policy, exact_policy)
        or status.reviewer_policy_hash != canonical_hash(exact_policy.to_dict())
        or status.bootstrap_plan is not None
        or status.bootstrap_receipt is not None
        or not _dataclass_fields_exact_v1(
            status.claims,
            HipFgmresExternalReviewerRootBootstrapStatusClaimsV1(),
        )
        or status.status_hash
        != canonical_hash(_package_status_payload_v1(status, include_hash=False))
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_status_semantics_invalid",
            "/status",
        )
    return status


def _validate_reviewer_roots_v1(
    roots: tuple[HipFgmresExternalReviewerRootV1, ...],
    *,
    bootstrap_at: datetime,
) -> None:
    if len(roots) != _REVIEWER_COUNT_V1:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_reviewer_count_invalid",
            "/reviewer_roots",
        )
    for index, root in enumerate(roots):
        path = f"/reviewer_roots/{index}"
        if (
            type(root) is not HipFgmresExternalReviewerRootV1
            or type(root.reviewer_id) is not str
            or not 3 <= len(root.reviewer_id) <= 64
            or _REVIEWER_ID_RE.fullmatch(root.reviewer_id) is None
            or type(root.key_id) is not str
            or not 1 <= len(root.key_id) <= 128
            or _REVIEWER_KEY_ID_RE.fullmatch(root.key_id) is None
            or root.key_id != f"ed25519-review:{root.reviewer_id}:v1"
            or type(root.key_epoch) is not int
            or root.key_epoch != 1
            or type(root.public_key_base64) is not str
            or len(root.public_key_base64) != 44
            or not _is_hash_v1(root.public_key_sha256)
            or type(root.valid_from_utc) is not str
            or type(root.valid_until_utc) is not str
        ):
            _fail(
                "hip_fgmres_external_reviewer_bootstrap_reviewer_root_invalid",
                path,
            )
    expected_order = tuple(
        sorted(roots, key=lambda root: (root.reviewer_id, root.key_id, root.key_epoch))
    )
    if roots != expected_order:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_reviewer_order_invalid",
            "/reviewer_roots",
        )
    reviewer_ids: set[str] = set()
    key_ids: set[str] = set()
    public_hashes: set[str] = set()
    for index, root in enumerate(roots):
        path = f"/reviewer_roots/{index}"
        public_key = root.public_key_bytes
        valid_from = _parse_utc_v1(root.valid_from_utc, f"{path}/valid_from_utc")
        valid_until = _parse_utc_v1(root.valid_until_utc, f"{path}/valid_until_utc")
        if (
            root.reviewer_id in reviewer_ids
            or root.key_id in key_ids
            or root.public_key_sha256 in public_hashes
            or root.public_key_sha256 != sha256_prefixed(public_key)
            or valid_until <= valid_from
            or not valid_from <= bootstrap_at < valid_until
        ):
            _fail(
                "hip_fgmres_external_reviewer_bootstrap_reviewer_root_invalid",
                path,
            )
        reviewer_ids.add(root.reviewer_id)
        key_ids.add(root.key_id)
        public_hashes.add(root.public_key_sha256)


def _validate_endorsements_v1(
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1,
    endorsements: tuple[HipFgmresExternalReviewerRootEndorsementV1, ...],
) -> None:
    if len(endorsements) != _BOOTSTRAP_ENDORSEMENT_COUNT_V1:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_endorsement_count_invalid",
            "/endorsements",
        )
    for index, endorsement in enumerate(endorsements):
        path = f"/endorsements/{index}"
        if (
            type(endorsement) is not HipFgmresExternalReviewerRootEndorsementV1
            or type(endorsement.reviewer_id) is not str
            or not 3 <= len(endorsement.reviewer_id) <= 64
            or _REVIEWER_ID_RE.fullmatch(endorsement.reviewer_id) is None
            or type(endorsement.reviewer_key_id) is not str
            or not 1 <= len(endorsement.reviewer_key_id) <= 128
            or _REVIEWER_KEY_ID_RE.fullmatch(endorsement.reviewer_key_id) is None
            or type(endorsement.reviewer_key_epoch) is not int
            or endorsement.reviewer_key_epoch != 1
            or not _is_hash_v1(endorsement.plan_hash)
            or type(endorsement.algorithm) is not str
            or endorsement.algorithm != ED25519_ALGORITHM_V1
            or type(endorsement.signature_base64) is not str
            or len(endorsement.signature_base64) != 88
            or not _is_hash_v1(endorsement.signature_sha256)
        ):
            _fail(
                "hip_fgmres_external_reviewer_bootstrap_endorsement_invalid",
                path,
            )
    expected_order = tuple(
        sorted(
            endorsements,
            key=lambda item: (
                item.reviewer_id,
                item.reviewer_key_id,
                item.reviewer_key_epoch,
            ),
        )
    )
    if endorsements != expected_order:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_endorsement_order_invalid",
            "/endorsements",
        )
    roots = {root.reviewer_id: root for root in plan.reviewer_roots}
    seen_reviewers: set[str] = set()
    seen_keys: set[str] = set()
    message = _endorsement_message_v1(plan)
    for index, endorsement in enumerate(endorsements):
        path = f"/endorsements/{index}"
        root = roots.get(endorsement.reviewer_id)
        signature = _decode_base64_v1(
            endorsement.signature_base64,
            expected_byte_count=64,
            path=f"{path}/signature_base64",
        )
        if (
            root is None
            or endorsement.reviewer_id in seen_reviewers
            or endorsement.reviewer_key_id in seen_keys
            or endorsement.reviewer_key_id != root.key_id
            or endorsement.reviewer_key_epoch != root.key_epoch
            or endorsement.plan_hash != plan.plan_hash
            or endorsement.algorithm != ED25519_ALGORITHM_V1
            or endorsement.signature_sha256 != sha256_prefixed(signature)
        ):
            _fail(
                "hip_fgmres_external_reviewer_bootstrap_endorsement_invalid",
                path,
            )
        try:
            verify_ed25519_signature_v1(
                public_key=root.public_key_bytes,
                signature_base64=endorsement.signature_base64,
                message=message,
            )
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_reviewer_bootstrap_signature_invalid",
                f"{path}/signature_base64",
                exc.code,
            )
        seen_reviewers.add(endorsement.reviewer_id)
        seen_keys.add(endorsement.reviewer_key_id)
    if seen_reviewers != set(roots):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_endorsement_coverage_invalid",
            "/endorsements",
        )


def _load_exact_source_identity_v1() -> (
    HipFgmresExternalReviewerBootstrapSourceRegistryV1
):
    source_schema_hash, source_head_occurred_at = _read_exact_source_material_v1()
    result = _SOURCE_REGISTRY_LOADER_V1()
    if type(result) is not HipFgmresExternalTrustAnchorRegistryResultV2:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_source_type_invalid",
            "/source_registry",
        )
    source = HipFgmresExternalReviewerBootstrapSourceRegistryV1(
        schema_version=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2,
        capability_profile=(
            HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2
        ),
        evidence_scope=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2,
        registry_id=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2,
        registry_schema_bytes_sha256=source_schema_hash,
        registry_bytes_sha256=result.registry_bytes_sha256,
        registry_hash=result.registry_hash,
        registry_epoch=result.registry_epoch,
        predecessor_registry_epoch=result.predecessor_registry_epoch,
        predecessor_registry_hash=result.predecessor_registry_hash,
        head_event_hash=result.head_event_hash,
        head_event_occurred_at_utc=source_head_occurred_at,
        event_count=result.event_count,
        reviewer_authority_count=len(result.reviewer_authorities),
        reviewer_authority_commitment_hash=canonical_hash(
            [reviewer.to_dict() for reviewer in result.reviewer_authorities]
        ),
        enrolled_key_count=result.enrolled_key_count,
        active_key_count=result.active_key_count,
        replay_receipt_hash=result.receipt_hash,
        source_authority_mode=_SOURCE_AUTHORITY_MODE_V1,
        authority_continuity_available=False,
    )
    expected = HipFgmresExternalReviewerBootstrapSourceRegistryV1(
        schema_version=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2,
        capability_profile=(
            HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2
        ),
        evidence_scope=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2,
        registry_id=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2,
        registry_schema_bytes_sha256=_SOURCE_REGISTRY_SCHEMA_BYTES_SHA256_V1,
        registry_bytes_sha256=_SOURCE_REGISTRY_BYTES_SHA256_V1,
        registry_hash=_SOURCE_REGISTRY_HASH_V1,
        registry_epoch=1,
        predecessor_registry_epoch=0,
        predecessor_registry_hash=None,
        head_event_hash=_SOURCE_HEAD_EVENT_HASH_V1,
        head_event_occurred_at_utc=_SOURCE_HEAD_OCCURRED_AT_UTC_V1,
        event_count=1,
        reviewer_authority_count=0,
        reviewer_authority_commitment_hash=(_SOURCE_REVIEWER_COMMITMENT_HASH_V1),
        enrolled_key_count=0,
        active_key_count=0,
        replay_receipt_hash=_SOURCE_REPLAY_RECEIPT_HASH_V1,
        source_authority_mode=_SOURCE_AUTHORITY_MODE_V1,
        authority_continuity_available=False,
    )
    if not _dataclass_fields_exact_v1(source, expected):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_source_identity_mismatch",
            "/source_registry",
        )
    return source


def _read_exact_source_material_v1() -> tuple[str, str]:
    schema_resource = resources.files("structural_analysis.schemas").joinpath(
        _SOURCE_REGISTRY_SCHEMA_RESOURCE_V1
    )
    schema_raw = _read_bounded_resource_v1(
        schema_resource,
        path="/source_registry/schema",
        missing_code="hip_fgmres_external_reviewer_bootstrap_source_schema_missing",
        read_code="hip_fgmres_external_reviewer_bootstrap_source_schema_read_failed",
    )
    schema_hash = sha256_prefixed(schema_raw)
    if schema_hash != _SOURCE_REGISTRY_SCHEMA_BYTES_SHA256_V1:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_source_schema_hash_mismatch",
            "/source_registry/schema",
        )

    registry_resource = resources.files(_SOURCE_REGISTRY_RESOURCE_PACKAGE_V1).joinpath(
        _SOURCE_REGISTRY_RESOURCE_V1
    )
    registry_raw = _read_bounded_resource_v1(
        registry_resource,
        path="/source_registry",
        missing_code="hip_fgmres_external_reviewer_bootstrap_source_resource_missing",
        read_code="hip_fgmres_external_reviewer_bootstrap_source_resource_read_failed",
    )
    if sha256_prefixed(registry_raw) != _SOURCE_REGISTRY_BYTES_SHA256_V1:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_source_resource_hash_mismatch",
            "/source_registry",
        )
    manifest = _parse_strict_object_v1(registry_raw, path="/source_registry")
    events = manifest.get("events")
    if (
        type(events) is not list
        or len(events) != 1
        or type(events[0]) is not dict
        or events[0].get("event_hash") != _SOURCE_HEAD_EVENT_HASH_V1
        or events[0].get("occurred_at_utc") != _SOURCE_HEAD_OCCURRED_AT_UTC_V1
        or manifest.get("registry_hash") != _SOURCE_REGISTRY_HASH_V1
    ):
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_source_head_mismatch",
            "/source_registry/events/0",
        )
    _parse_utc_v1(
        events[0]["occurred_at_utc"],
        "/source_registry/events/0/occurred_at_utc",
    )
    return schema_hash, events[0]["occurred_at_utc"]


def _target_lineage_id_v1(
    *,
    ceremony_id: str,
    nonce_base64: str,
    bootstrap_at_utc: str,
    source_lineage_commitment_hash: str,
    target_lineage_nonce_base64: str,
    reviewer_policy_hash: str,
    reviewer_root_commitment_hash: str,
) -> str:
    payload = {
        "ceremony_id": ceremony_id,
        "nonce_base64": nonce_base64,
        "bootstrap_at_utc": bootstrap_at_utc,
        "source_lineage_commitment_hash": source_lineage_commitment_hash,
        "target_registry_schema_version": (
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1
        ),
        "target_registry_id": (
            HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1
        ),
        "target_lineage_generation": _TARGET_LINEAGE_GENERATION_V1,
        "target_lineage_nonce_base64": target_lineage_nonce_base64,
        "reviewer_policy_hash": reviewer_policy_hash,
        "reviewer_root_commitment_hash": reviewer_root_commitment_hash,
    }
    return sha256_prefixed(
        HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_LINEAGE_DOMAIN_V1
        + canonical_json_bytes(payload)
    )


def _endorsement_message_v1(
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1,
) -> bytes:
    return (
        HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_ENDORSEMENT_DOMAIN_V1
        + canonical_json_bytes(_plan_payload_v1(plan, include_hash=True))
    )


def _plan_payload_v1(
    plan: HipFgmresExternalReviewerRootBootstrapPlanV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": plan.schema_version,
        "capability_profile": plan.capability_profile,
        "purpose": plan.purpose,
        "ceremony_id": plan.ceremony_id,
        "nonce_base64": plan.nonce_base64,
        "bootstrap_at_utc": plan.bootstrap_at_utc,
        "source_registry": plan.source_registry.to_dict(),
        "source_lineage_commitment_hash": plan.source_lineage_commitment_hash,
        "target_registry_schema_version": plan.target_registry_schema_version,
        "target_registry_id": plan.target_registry_id,
        "target_lineage_generation": plan.target_lineage_generation,
        "target_lineage_nonce_base64": plan.target_lineage_nonce_base64,
        "reviewer_policy": plan.reviewer_policy.to_dict(),
        "reviewer_policy_hash": plan.reviewer_policy_hash,
        "reviewer_roots": [root.to_dict() for root in plan.reviewer_roots],
        "reviewer_root_commitment_hash": plan.reviewer_root_commitment_hash,
        "target_lineage_id": plan.target_lineage_id,
    }
    if include_hash:
        payload["plan_hash"] = plan.plan_hash
    return payload


def _receipt_payload_v1(
    receipt: HipFgmresExternalReviewerRootBootstrapReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "plan": _plan_payload_v1(receipt.plan, include_hash=True),
        "endorsements": [item.to_dict() for item in receipt.endorsements],
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _package_status_payload_v1(
    status: HipFgmresExternalReviewerRootBootstrapStatusV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": status.schema_version,
        "capability_profile": status.capability_profile,
        "status": status.status,
        "evidence_scope": status.evidence_scope,
        "source_registry": status.source_registry.to_dict(),
        "source_lineage_commitment_hash": status.source_lineage_commitment_hash,
        "target_registry_schema_version": status.target_registry_schema_version,
        "target_registry_id": status.target_registry_id,
        "target_lineage_generation": status.target_lineage_generation,
        "reviewer_policy": status.reviewer_policy.to_dict(),
        "reviewer_policy_hash": status.reviewer_policy_hash,
        "bootstrap_plan": status.bootstrap_plan,
        "bootstrap_receipt": status.bootstrap_receipt,
        "claims": status.claims.to_dict(),
    }
    if include_hash:
        payload["status_hash"] = status.status_hash
    return payload


def _load_package_status_v1() -> HipFgmresExternalReviewerRootBootstrapStatusV1:
    raw = _read_fixed_resource_v1()
    raw_hash = sha256_prefixed(raw)
    if raw_hash != _STATUS_RESOURCE_BYTES_SHA256_V1:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_resource_hash_mismatch",
            "/status",
        )
    manifest = _parse_strict_object_v1(raw, path="/status")
    return _compile_package_status_v1(
        manifest,
        contract_bytes_sha256=raw_hash,
    )


def _read_fixed_resource_v1() -> bytes:
    resource = resources.files(_RESOURCE_PACKAGE_V1).joinpath(_STATUS_RESOURCE_V1)
    return _read_bounded_resource_v1(
        resource,
        path="/status",
        missing_code="hip_fgmres_external_reviewer_bootstrap_resource_missing",
        read_code="hip_fgmres_external_reviewer_bootstrap_resource_read_failed",
    )


def _read_bounded_resource_v1(
    resource: Any,
    *,
    path: str,
    missing_code: str,
    read_code: str,
) -> bytes:
    try:
        if not resource.is_file():
            _fail(missing_code, path)
        with resource.open("rb") as stream:
            raw = stream.read(_MAX_RESOURCE_BYTES_V1 + 1)
    except HipFgmresExternalReviewerRootBootstrapV1Error:
        raise
    except OSError as exc:
        _fail(read_code, path, type(exc).__name__)
    if not raw or len(raw) > _MAX_RESOURCE_BYTES_V1:
        _fail("hip_fgmres_external_reviewer_bootstrap_extent_invalid", path)
    return raw


class _DuplicateKeyError(ValueError):
    pass


def _parse_strict_object_v1(raw: bytes, *, path: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_RESOURCE_BYTES_V1:
        _fail("hip_fgmres_external_reviewer_bootstrap_extent_invalid", path)
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_external_reviewer_bootstrap_json_bom_forbidden", path)

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
            "hip_fgmres_external_reviewer_bootstrap_extent_invalid",
            path,
            "JSON nesting exceeds parser limit",
        )
    except _DuplicateKeyError:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_json_duplicate_key",
            path,
            "duplicate object member",
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_json_invalid",
            path,
            type(exc).__name__,
        )
    if type(payload) is not dict:
        _fail("hip_fgmres_external_reviewer_bootstrap_json_root_invalid", path)
    _enforce_json_bounds_v1(payload, path=path)
    return payload


def _enforce_json_bounds_v1(value: Any, *, path: str) -> None:
    nodes = 0
    stack: list[tuple[Any, int, str]] = [(value, 1, path)]
    while stack:
        item, depth, item_path = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES_V1 or depth > _MAX_JSON_DEPTH_V1:
            _fail("hip_fgmres_external_reviewer_bootstrap_extent_invalid", item_path)
        if type(item) is float and not math.isfinite(item):
            _fail("hip_fgmres_external_reviewer_bootstrap_json_nonfinite", item_path)
        if type(item) is dict:
            for key, child in item.items():
                stack.append((child, depth + 1, f"{item_path}/{key}"))
        elif type(item) is list:
            for index, child in enumerate(item):
                stack.append((child, depth + 1, f"{item_path}/{index}"))


def _validate_schema_v1(payload: dict[str, Any], *, path: str) -> None:
    resource = resources.files("structural_analysis.schemas").joinpath(
        _SCHEMA_RESOURCE_V1
    )
    raw = _read_bounded_resource_v1(
        resource,
        path="/schema",
        missing_code="hip_fgmres_external_reviewer_bootstrap_schema_read_failed",
        read_code="hip_fgmres_external_reviewer_bootstrap_schema_read_failed",
    )
    if sha256_prefixed(raw) != _SCHEMA_RESOURCE_BYTES_SHA256_V1:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_schema_hash_mismatch",
            "/schema",
        )
    schema = _parse_strict_object_v1(raw, path="/schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_schema_invalid",
            "/schema",
            type(exc).__name__,
        )
    errors = Draft202012Validator(schema).iter_errors(payload)
    first = next(errors, None)
    if first is not None:
        pointer = "/" + "/".join(str(part) for part in first.absolute_path)
        keyword = str(first.validator)[:64]
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_schema_validation_failed",
            pointer if pointer != "/" else path,
            f"schema keyword {keyword} rejected value",
        )


def _parse_utc_v1(value: str, path: str) -> datetime:
    if (
        type(value) is not str
        or len(value) not in {20, 27}
        or _UTC_RE.fullmatch(value) is None
    ):
        _fail("hip_fgmres_external_reviewer_bootstrap_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_timestamp_invalid",
            path,
            type(exc).__name__,
        )
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("hip_fgmres_external_reviewer_bootstrap_timestamp_invalid", path)
    canonical = parsed.isoformat(
        timespec="microseconds" if "." in value else "seconds"
    ).replace("+00:00", "Z")
    if canonical != value:
        _fail("hip_fgmres_external_reviewer_bootstrap_timestamp_invalid", path)
    return parsed


def _decode_public_key_v1(value: str, *, path: str) -> bytes:
    raw = _decode_base64_v1(value, expected_byte_count=32, path=path)
    try:
        return validate_ed25519_public_key_v1(raw)
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_public_key_invalid",
            path,
            exc.code,
        )


def _decode_base64_v1(
    value: str,
    *,
    expected_byte_count: int,
    path: str,
) -> bytes:
    expected_length = 4 * ((expected_byte_count + 2) // 3)
    if type(value) is not str or len(value) != expected_length:
        _fail("hip_fgmres_external_reviewer_bootstrap_base64_invalid", path)
    try:
        return decode_canonical_base64_v1(
            value,
            expected_byte_count=expected_byte_count,
            path=path,
        )
    except Ed25519EvidenceV1Error as exc:
        _fail(
            "hip_fgmres_external_reviewer_bootstrap_base64_invalid",
            path,
            exc.code,
        )


def _is_hash_v1(value: Any) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


def _dataclass_fields_exact_v1(value: Any, expected: Any) -> bool:
    if type(value) is not type(expected):
        return False
    return all(
        type(getattr(value, name)) is type(getattr(expected, name))
        and getattr(value, name) == getattr(expected, name)
        for name in expected.__dataclass_fields__
    )


def _bounded_path_v1(path: str) -> str:
    value = path if type(path) is str and path.startswith("/") else "/"
    if len(value) <= _MAX_ERROR_PATH_CHARS_V1:
        return value
    return value[: _MAX_ERROR_PATH_CHARS_V1 - 3] + "..."


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalReviewerRootBootstrapV1Error(code, path, message)


def _make_source_registry_loader_v1(
    loader: Any = load_hip_fgmres_external_trust_anchor_registry_v2,
) -> Any:
    return loader


_SOURCE_REGISTRY_LOADER_V1 = _make_source_registry_loader_v1()
del _make_source_registry_loader_v1


def _make_bootstrap_status_loader_v1(loader: Any = _load_package_status_v1) -> Any:
    return loader


_BOOTSTRAP_STATUS_LOADER_AUTHORITY_V1 = _make_bootstrap_status_loader_v1()
del _make_bootstrap_status_loader_v1


__all__ = [
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_DETACHED_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_ENDORSEMENT_DOMAIN_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_LINEAGE_DOMAIN_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PACKAGE_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PLAN_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PURPOSE_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_RECEIPT_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_STATUS_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1",
    "HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1",
    "HipFgmresExternalReviewerBootstrapPolicyV1",
    "HipFgmresExternalReviewerBootstrapSourceRegistryV1",
    "HipFgmresExternalReviewerRootBootstrapClaimsV1",
    "HipFgmresExternalReviewerRootBootstrapPlanV1",
    "HipFgmresExternalReviewerRootBootstrapReceiptV1",
    "HipFgmresExternalReviewerRootBootstrapStatusClaimsV1",
    "HipFgmresExternalReviewerRootBootstrapStatusV1",
    "HipFgmresExternalReviewerRootBootstrapV1Error",
    "HipFgmresExternalReviewerRootEndorsementV1",
    "HipFgmresExternalReviewerRootV1",
    "compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1",
    "compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1",
    "load_hip_fgmres_external_reviewer_root_bootstrap_status_v1",
    "validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1",
    "validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1",
    "validate_hip_fgmres_external_reviewer_root_bootstrap_status_v1",
    "verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1",
]
