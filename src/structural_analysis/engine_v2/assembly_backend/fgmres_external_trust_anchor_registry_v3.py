"""Detached reviewer-root trust-registry v3 genesis activation.

The reviewer bootstrap v1 contract proves three possession signatures over a
fresh-lineage plan, but deliberately does not activate the target registry.
This module implements the second, separately domain-separated 3-of-3
activation required by that plan.  The resulting receipt is detached and
non-promoting: it carries public roots and verifies signatures, but it is not a
package trust-store update and does not enroll or activate a runner key.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

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

from . import fgmres_external_reviewer_root_bootstrap_v1 as bootstrap_v1


HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3 = bootstrap_v1.HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_SCHEMA_VERSION_V1
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V3 = (
    "phase0_external_gfx1100_reviewer_root_registry_v3_genesis"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V3 = (
    "detached_three_reviewer_root_genesis_activation_non_authoritative"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_STATUS_V3 = (
    "detached_reviewer_root_registry_v3_genesis_verified"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_PURPOSE_V3 = (
    "hip_fgmres_external_reviewer_root_registry_v3_genesis_activation"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_DOMAIN_V3 = (
    b"structural-analysis/engine-v2/hip-fgmres/"
    b"reviewer-root-registry-v3-genesis-activation/v1\x00"
)

_SCHEMA_RESOURCE = "hip_fgmres_external_trust_anchor_registry_v3.schema.json"
_TARGET_REGISTRY_ID = (
    bootstrap_v1.HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_TARGET_REGISTRY_ID_V1
)
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REVIEWER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_REVIEWER_KEY_ID_RE = re.compile(r"^ed25519-review:[a-z0-9][a-z0-9._-]{2,63}:v1$")
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z$"
)
_REVIEWER_COUNT = 3
_REGISTRY_EPOCH = 1
_EVENT_COUNT = 1
_MAX_ERROR_PATH_CHARS = 512
_MAX_ERROR_MESSAGE_CHARS = 240


class HipFgmresExternalTrustAnchorRegistryV3Error(RuntimeError):
    """Stable fail-closed reviewer-root registry-v3 error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path[:_MAX_ERROR_PATH_CHARS] if path.startswith("/") else "/"
        self.message = (message or code)[:_MAX_ERROR_MESSAGE_CHARS]
        super().__init__(f"{self.code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorRegistryGenesisV3:
    purpose: str
    registry_schema_version: str
    registry_id: str
    registry_epoch: int
    event_count: int
    lineage_generation: int
    lineage_id: str
    predecessor_registry_id: None
    predecessor_registry_hash: None
    predecessor_authority_continuity_available: Literal[False]
    source_registry_schema_version: str
    source_registry_id: str
    source_registry_hash: str
    source_lineage_commitment_hash: str
    bootstrap_plan_schema_version: str
    bootstrap_plan_hash: str
    bootstrap_receipt_schema_version: str
    bootstrap_receipt_hash: str
    bootstrap_at_utc: str
    activated_at_utc: str
    reviewer_policy: bootstrap_v1.HipFgmresExternalReviewerBootstrapPolicyV1
    reviewer_policy_hash: str
    reviewer_roots: tuple[bootstrap_v1.HipFgmresExternalReviewerRootV1, ...]
    reviewer_root_commitment_hash: str
    reviewer_authority_count: int
    activation_endorsement_count: int
    enrolled_runner_key_count: Literal[0]
    active_runner_key_count: Literal[0]
    genesis_event_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(self)
        return _genesis_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReviewerRootActivationEndorsementV3:
    reviewer_id: str
    reviewer_key_id: str
    reviewer_key_epoch: int
    genesis_event_hash: str
    bootstrap_receipt_hash: str
    algorithm: str
    signature_base64: str
    signature_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorRegistryClaimsV3:
    detached_registry_genesis_self_consistent: Literal[True] = True
    bootstrap_receipt_hash_committed: Literal[True] = True
    reviewer_root_set_and_policy_committed: Literal[True] = True
    all_three_root_activation_signatures_verified: Literal[True] = True
    reviewer_root_private_key_possession_verified: Literal[True] = True
    runner_key_counts_zero_verified: Literal[True] = True
    source_bootstrap_receipt_replayed_in_detached_receipt: Literal[False] = False
    predecessor_reviewer_authority_continuity_verified: Literal[False] = False
    package_registry_v3_inclusion_verified: Literal[False] = False
    package_registry_v3_activation_verified: Literal[False] = False
    operational_reviewer_authority_activated: Literal[False] = False
    reviewer_human_identity_verified: Literal[False] = False
    reviewer_independence_verified: Literal[False] = False
    reviewer_hsm_origin_verified: Literal[False] = False
    reviewer_hsm_non_exportability_verified: Literal[False] = False
    trusted_activation_time_verified: Literal[False] = False
    external_monotonic_anchor_verified: Literal[False] = False
    historical_registry_resolution_verified: Literal[False] = False
    runner_key_enrollment_verified: Literal[False] = False
    runner_key_activation_verified: Literal[False] = False
    signed_trace_binding_verified: Literal[False] = False
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
class HipFgmresExternalTrustAnchorRegistryReceiptV3:
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    promotion_eligible: Literal[False]
    genesis: HipFgmresExternalTrustAnchorRegistryGenesisV3
    activation_endorsements: tuple[
        HipFgmresExternalReviewerRootActivationEndorsementV3, ...
    ]
    registry_hash: str
    claims: HipFgmresExternalTrustAnchorRegistryClaimsV3
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorRegistryResultV3:
    receipt: HipFgmresExternalTrustAnchorRegistryReceiptV3
    source_bootstrap_receipt: (
        bootstrap_v1.HipFgmresExternalReviewerRootBootstrapReceiptV1
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_external_trust_anchor_registry_result_v3(self)
        return self.receipt.to_dict()


def compile_hip_fgmres_external_trust_anchor_registry_genesis_v3(
    source_bootstrap_receipt: (
        bootstrap_v1.HipFgmresExternalReviewerRootBootstrapReceiptV1
    ),
    *,
    activated_at_utc: str,
) -> HipFgmresExternalTrustAnchorRegistryGenesisV3:
    """Compile the exact target-genesis statement for second-round signing."""

    if (
        type(source_bootstrap_receipt)
        is not bootstrap_v1.HipFgmresExternalReviewerRootBootstrapReceiptV1
    ):
        _fail("hip_fgmres_external_registry_v3_bootstrap_type_invalid", "/source")
    bootstrap_v1.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
        source_bootstrap_receipt
    )
    plan = source_bootstrap_receipt.plan
    activated_at = _parse_utc(activated_at_utc, "/activated_at_utc")
    bootstrap_at = _parse_utc(plan.bootstrap_at_utc, "/bootstrap_at_utc")
    if activated_at <= bootstrap_at:
        _fail(
            "hip_fgmres_external_registry_v3_activation_time_invalid",
            "/activated_at_utc",
        )
    _validate_roots(plan.reviewer_roots, observed_at=activated_at)
    source = plan.source_registry
    draft = HipFgmresExternalTrustAnchorRegistryGenesisV3(
        purpose=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_PURPOSE_V3,
        registry_schema_version=(
            HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3
        ),
        registry_id=_TARGET_REGISTRY_ID,
        registry_epoch=_REGISTRY_EPOCH,
        event_count=_EVENT_COUNT,
        lineage_generation=plan.target_lineage_generation,
        lineage_id=plan.target_lineage_id,
        predecessor_registry_id=None,
        predecessor_registry_hash=None,
        predecessor_authority_continuity_available=False,
        source_registry_schema_version=source.schema_version,
        source_registry_id=source.registry_id,
        source_registry_hash=source.registry_hash,
        source_lineage_commitment_hash=plan.source_lineage_commitment_hash,
        bootstrap_plan_schema_version=plan.schema_version,
        bootstrap_plan_hash=plan.plan_hash,
        bootstrap_receipt_schema_version=source_bootstrap_receipt.schema_version,
        bootstrap_receipt_hash=source_bootstrap_receipt.receipt_hash,
        bootstrap_at_utc=plan.bootstrap_at_utc,
        activated_at_utc=_format_utc(activated_at),
        reviewer_policy=plan.reviewer_policy,
        reviewer_policy_hash=plan.reviewer_policy_hash,
        reviewer_roots=plan.reviewer_roots,
        reviewer_root_commitment_hash=plan.reviewer_root_commitment_hash,
        reviewer_authority_count=_REVIEWER_COUNT,
        activation_endorsement_count=_REVIEWER_COUNT,
        enrolled_runner_key_count=0,
        active_runner_key_count=0,
        genesis_event_hash=_ZERO_HASH,
    )
    genesis = replace(
        draft,
        genesis_event_hash=canonical_hash(_genesis_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(genesis)


def compile_hip_fgmres_external_trust_anchor_registry_activation_message_v3(
    genesis: HipFgmresExternalTrustAnchorRegistryGenesisV3,
) -> bytes:
    """Return the domain-separated exact genesis statement signed by each root."""

    validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(genesis)
    return HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_DOMAIN_V3 + (
        canonical_json_bytes(
            {
                "purpose": (
                    HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_PURPOSE_V3
                ),
                "genesis": genesis.to_dict(),
            }
        )
    )


def verify_hip_fgmres_external_trust_anchor_registry_activation_v3(
    source_bootstrap_receipt: (
        bootstrap_v1.HipFgmresExternalReviewerRootBootstrapReceiptV1
    ),
    *,
    genesis: HipFgmresExternalTrustAnchorRegistryGenesisV3,
    activation_endorsements: tuple[
        HipFgmresExternalReviewerRootActivationEndorsementV3, ...
    ],
) -> HipFgmresExternalTrustAnchorRegistryResultV3:
    """Verify all three second-round signatures and mint an attached result."""

    if (
        type(source_bootstrap_receipt)
        is not bootstrap_v1.HipFgmresExternalReviewerRootBootstrapReceiptV1
    ):
        _fail("hip_fgmres_external_registry_v3_bootstrap_type_invalid", "/source")
    bootstrap_v1.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
        source_bootstrap_receipt
    )
    validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(genesis)
    expected_genesis = compile_hip_fgmres_external_trust_anchor_registry_genesis_v3(
        source_bootstrap_receipt,
        activated_at_utc=genesis.activated_at_utc,
    )
    if genesis != expected_genesis:
        _fail("hip_fgmres_external_registry_v3_bootstrap_binding_invalid", "/genesis")
    _validate_endorsements(genesis, activation_endorsements)
    registry_hash = canonical_hash(
        {
            "genesis": genesis.to_dict(),
            "activation_endorsements": [
                endorsement.to_dict() for endorsement in activation_endorsements
            ],
        }
    )
    draft = HipFgmresExternalTrustAnchorRegistryReceiptV3(
        schema_version=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3,
        capability_profile=(
            HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V3
        ),
        status=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_STATUS_V3,
        evidence_scope=HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V3,
        promotion_eligible=False,
        genesis=genesis,
        activation_endorsements=activation_endorsements,
        registry_hash=registry_hash,
        claims=HipFgmresExternalTrustAnchorRegistryClaimsV3(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    result = HipFgmresExternalTrustAnchorRegistryResultV3(
        receipt=receipt,
        source_bootstrap_receipt=source_bootstrap_receipt,
    )
    return validate_hip_fgmres_external_trust_anchor_registry_result_v3(result)


def validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(
    genesis: HipFgmresExternalTrustAnchorRegistryGenesisV3,
) -> HipFgmresExternalTrustAnchorRegistryGenesisV3:
    """Validate one detached target-genesis statement."""

    if type(genesis) is not HipFgmresExternalTrustAnchorRegistryGenesisV3:
        _fail("hip_fgmres_external_registry_v3_genesis_type_invalid", "/genesis")
    if (
        type(genesis.reviewer_policy)
        is not bootstrap_v1.HipFgmresExternalReviewerBootstrapPolicyV1
        or type(genesis.reviewer_roots) is not tuple
    ):
        _fail("hip_fgmres_external_registry_v3_genesis_nested_type_invalid", "/genesis")
    hashes = (
        genesis.lineage_id,
        genesis.source_registry_hash,
        genesis.source_lineage_commitment_hash,
        genesis.bootstrap_plan_hash,
        genesis.bootstrap_receipt_hash,
        genesis.reviewer_policy_hash,
        genesis.reviewer_root_commitment_hash,
        genesis.genesis_event_hash,
    )
    if (
        genesis.purpose
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_PURPOSE_V3
        or genesis.registry_schema_version
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3
        or genesis.registry_id != _TARGET_REGISTRY_ID
        or type(genesis.registry_epoch) is not int
        or genesis.registry_epoch != _REGISTRY_EPOCH
        or type(genesis.event_count) is not int
        or genesis.event_count != _EVENT_COUNT
        or type(genesis.lineage_generation) is not int
        or genesis.lineage_generation != 1
        or genesis.predecessor_registry_id is not None
        or genesis.predecessor_registry_hash is not None
        or genesis.predecessor_authority_continuity_available is not False
        or genesis.source_registry_schema_version
        != bootstrap_v1.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2
        or genesis.source_registry_id
        != bootstrap_v1.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2
        or genesis.bootstrap_plan_schema_version
        != bootstrap_v1.HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_PLAN_SCHEMA_VERSION_V1
        or genesis.bootstrap_receipt_schema_version
        != bootstrap_v1.HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_RECEIPT_SCHEMA_VERSION_V1
        or any(
            type(value) is not str or _HASH_RE.fullmatch(value) is None
            for value in hashes
        )
        or not _policy_is_exact(genesis.reviewer_policy)
        or genesis.reviewer_policy_hash
        != canonical_hash(genesis.reviewer_policy.to_dict())
        or type(genesis.reviewer_authority_count) is not int
        or genesis.reviewer_authority_count != _REVIEWER_COUNT
        or type(genesis.activation_endorsement_count) is not int
        or genesis.activation_endorsement_count != _REVIEWER_COUNT
        or type(genesis.enrolled_runner_key_count) is not int
        or genesis.enrolled_runner_key_count != 0
        or type(genesis.active_runner_key_count) is not int
        or genesis.active_runner_key_count != 0
    ):
        _fail("hip_fgmres_external_registry_v3_genesis_semantics_invalid", "/genesis")
    bootstrap_at = _parse_utc(genesis.bootstrap_at_utc, "/genesis/bootstrap_at_utc")
    activated_at = _parse_utc(genesis.activated_at_utc, "/genesis/activated_at_utc")
    if activated_at <= bootstrap_at:
        _fail("hip_fgmres_external_registry_v3_activation_time_invalid", "/genesis")
    _validate_roots(genesis.reviewer_roots, observed_at=activated_at)
    if genesis.reviewer_root_commitment_hash != canonical_hash(
        [root.to_dict() for root in genesis.reviewer_roots]
    ):
        _fail("hip_fgmres_external_registry_v3_root_commitment_invalid", "/genesis")
    expected_hash = canonical_hash(_genesis_payload(genesis, include_hash=False))
    if genesis.genesis_event_hash != expected_hash:
        _fail("hip_fgmres_external_registry_v3_genesis_hash_invalid", "/genesis")
    return genesis


def validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(
    receipt: HipFgmresExternalTrustAnchorRegistryReceiptV3,
) -> HipFgmresExternalTrustAnchorRegistryReceiptV3:
    """Validate detached signatures without claiming package source provenance."""

    if type(receipt) is not HipFgmresExternalTrustAnchorRegistryReceiptV3:
        _fail("hip_fgmres_external_registry_v3_receipt_type_invalid", "/")
    if (
        type(receipt.genesis) is not HipFgmresExternalTrustAnchorRegistryGenesisV3
        or type(receipt.activation_endorsements) is not tuple
        or type(receipt.claims) is not HipFgmresExternalTrustAnchorRegistryClaimsV3
    ):
        _fail("hip_fgmres_external_registry_v3_receipt_nested_type_invalid", "/")
    validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(receipt.genesis)
    _validate_endorsements(receipt.genesis, receipt.activation_endorsements)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_external_registry_v3_schema_invalid", path, error.message)
    expected_registry_hash = canonical_hash(
        {
            "genesis": receipt.genesis.to_dict(),
            "activation_endorsements": [
                endorsement.to_dict() for endorsement in receipt.activation_endorsements
            ],
        }
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V3
        or receipt.status != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_STATUS_V3
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V3
        or receipt.promotion_eligible is not False
        or not _claims_are_exact(receipt.claims)
        or type(receipt.registry_hash) is not str
        or receipt.registry_hash != expected_registry_hash
    ):
        _fail("hip_fgmres_external_registry_v3_receipt_semantics_invalid", "/")
    expected_receipt_hash = canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    )
    if receipt.receipt_hash != expected_receipt_hash:
        _fail("hip_fgmres_external_registry_v3_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_fgmres_external_trust_anchor_registry_result_v3(
    result: HipFgmresExternalTrustAnchorRegistryResultV3,
) -> HipFgmresExternalTrustAnchorRegistryResultV3:
    """Replay the source bootstrap and require its exact deterministic genesis."""

    if type(result) is not HipFgmresExternalTrustAnchorRegistryResultV3:
        _fail("hip_fgmres_external_registry_v3_result_type_invalid", "/")
    validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(result.receipt)
    if (
        type(result.source_bootstrap_receipt)
        is not bootstrap_v1.HipFgmresExternalReviewerRootBootstrapReceiptV1
    ):
        _fail("hip_fgmres_external_registry_v3_bootstrap_type_invalid", "/source")
    bootstrap_v1.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
        result.source_bootstrap_receipt
    )
    expected = compile_hip_fgmres_external_trust_anchor_registry_genesis_v3(
        result.source_bootstrap_receipt,
        activated_at_utc=result.receipt.genesis.activated_at_utc,
    )
    if result.receipt.genesis != expected:
        _fail("hip_fgmres_external_registry_v3_bootstrap_binding_invalid", "/source")
    return result


def _validate_roots(
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
    ):
        _fail(
            "hip_fgmres_external_registry_v3_reviewer_roots_invalid",
            "/genesis/reviewer_roots",
        )
    if tuple(
        (root.reviewer_id, root.key_id, root.key_epoch) for root in roots
    ) != tuple(
        sorted((root.reviewer_id, root.key_id, root.key_epoch) for root in roots)
    ):
        _fail(
            "hip_fgmres_external_registry_v3_reviewer_roots_invalid",
            "/genesis/reviewer_roots",
        )
    reviewer_ids: set[str] = set()
    key_ids: set[str] = set()
    key_hashes: set[str] = set()
    for index, root in enumerate(roots):
        path = f"/genesis/reviewer_roots/{index}"
        if (
            type(root.reviewer_id) is not str
            or _REVIEWER_ID_RE.fullmatch(root.reviewer_id) is None
            or type(root.key_id) is not str
            or _REVIEWER_KEY_ID_RE.fullmatch(root.key_id) is None
            or root.key_id != f"ed25519-review:{root.reviewer_id}:v1"
            or type(root.key_epoch) is not int
            or root.key_epoch != 1
            or type(root.public_key_sha256) is not str
            or _HASH_RE.fullmatch(root.public_key_sha256) is None
        ):
            _fail("hip_fgmres_external_registry_v3_reviewer_root_invalid", path)
        try:
            public_key = decode_canonical_base64_v1(
                root.public_key_base64,
                expected_byte_count=32,
                path=f"{path}/public_key_base64",
            )
            validate_ed25519_public_key_v1(public_key)
        except Ed25519EvidenceV1Error as exc:
            _fail(
                "hip_fgmres_external_registry_v3_reviewer_root_invalid", path, exc.code
            )
        valid_from = _parse_utc(root.valid_from_utc, f"{path}/valid_from_utc")
        valid_until = _parse_utc(root.valid_until_utc, f"{path}/valid_until_utc")
        if (
            root.public_key_sha256 != sha256_prefixed(public_key)
            or valid_from >= valid_until
            or observed_at < valid_from
            or observed_at >= valid_until
            or root.reviewer_id in reviewer_ids
            or root.key_id in key_ids
            or root.public_key_sha256 in key_hashes
        ):
            _fail("hip_fgmres_external_registry_v3_reviewer_root_invalid", path)
        reviewer_ids.add(root.reviewer_id)
        key_ids.add(root.key_id)
        key_hashes.add(root.public_key_sha256)


def _policy_is_exact(
    policy: bootstrap_v1.HipFgmresExternalReviewerBootstrapPolicyV1,
) -> bool:
    expected = bootstrap_v1.HipFgmresExternalReviewerBootstrapPolicyV1()
    for name in expected.__dataclass_fields__:
        value = getattr(policy, name)
        expected_value = getattr(expected, name)
        if type(value) is not type(expected_value) or value != expected_value:
            return False
    return True


def _claims_are_exact(claims: HipFgmresExternalTrustAnchorRegistryClaimsV3) -> bool:
    expected = HipFgmresExternalTrustAnchorRegistryClaimsV3()
    return all(
        getattr(claims, name) is getattr(expected, name)
        for name in expected.__dataclass_fields__
    )


def _validate_endorsements(
    genesis: HipFgmresExternalTrustAnchorRegistryGenesisV3,
    endorsements: tuple[HipFgmresExternalReviewerRootActivationEndorsementV3, ...],
) -> None:
    if (
        type(endorsements) is not tuple
        or len(endorsements) != _REVIEWER_COUNT
        or any(
            type(row) is not HipFgmresExternalReviewerRootActivationEndorsementV3
            for row in endorsements
        )
    ):
        _fail(
            "hip_fgmres_external_registry_v3_endorsements_invalid",
            "/activation_endorsements",
        )
    message = compile_hip_fgmres_external_trust_anchor_registry_activation_message_v3(
        genesis
    )
    for index, (root, row) in enumerate(
        zip(genesis.reviewer_roots, endorsements, strict=True)
    ):
        path = f"/activation_endorsements/{index}"
        if (
            row.reviewer_id != root.reviewer_id
            or row.reviewer_key_id != root.key_id
            or type(row.reviewer_key_epoch) is not int
            or row.reviewer_key_epoch != root.key_epoch
            or row.genesis_event_hash != genesis.genesis_event_hash
            or row.bootstrap_receipt_hash != genesis.bootstrap_receipt_hash
            or row.algorithm != ED25519_ALGORITHM_V1
            or type(row.signature_sha256) is not str
            or _HASH_RE.fullmatch(row.signature_sha256) is None
        ):
            _fail("hip_fgmres_external_registry_v3_endorsement_invalid", path)
        try:
            signature = decode_canonical_base64_v1(
                row.signature_base64,
                expected_byte_count=64,
                path=f"{path}/signature_base64",
            )
            if row.signature_sha256 != sha256_prefixed(signature):
                _fail("hip_fgmres_external_registry_v3_endorsement_invalid", path)
            verify_ed25519_signature_v1(
                public_key=decode_canonical_base64_v1(
                    root.public_key_base64,
                    expected_byte_count=32,
                    path=f"{path}/public_key_base64",
                ),
                signature_base64=row.signature_base64,
                message=message,
            )
        except Ed25519EvidenceV1Error as exc:
            _fail("hip_fgmres_external_registry_v3_endorsement_invalid", path, exc.code)


def _genesis_payload(
    genesis: HipFgmresExternalTrustAnchorRegistryGenesisV3,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "purpose": genesis.purpose,
        "registry_schema_version": genesis.registry_schema_version,
        "registry_id": genesis.registry_id,
        "registry_epoch": genesis.registry_epoch,
        "event_count": genesis.event_count,
        "lineage_generation": genesis.lineage_generation,
        "lineage_id": genesis.lineage_id,
        "predecessor_registry_id": genesis.predecessor_registry_id,
        "predecessor_registry_hash": genesis.predecessor_registry_hash,
        "predecessor_authority_continuity_available": (
            genesis.predecessor_authority_continuity_available
        ),
        "source_registry_schema_version": genesis.source_registry_schema_version,
        "source_registry_id": genesis.source_registry_id,
        "source_registry_hash": genesis.source_registry_hash,
        "source_lineage_commitment_hash": genesis.source_lineage_commitment_hash,
        "bootstrap_plan_schema_version": genesis.bootstrap_plan_schema_version,
        "bootstrap_plan_hash": genesis.bootstrap_plan_hash,
        "bootstrap_receipt_schema_version": genesis.bootstrap_receipt_schema_version,
        "bootstrap_receipt_hash": genesis.bootstrap_receipt_hash,
        "bootstrap_at_utc": genesis.bootstrap_at_utc,
        "activated_at_utc": genesis.activated_at_utc,
        "reviewer_policy": genesis.reviewer_policy.to_dict(),
        "reviewer_policy_hash": genesis.reviewer_policy_hash,
        "reviewer_roots": [root.to_dict() for root in genesis.reviewer_roots],
        "reviewer_root_commitment_hash": genesis.reviewer_root_commitment_hash,
        "reviewer_authority_count": genesis.reviewer_authority_count,
        "activation_endorsement_count": genesis.activation_endorsement_count,
        "enrolled_runner_key_count": genesis.enrolled_runner_key_count,
        "active_runner_key_count": genesis.active_runner_key_count,
    }
    if include_hash:
        payload["genesis_event_hash"] = genesis.genesis_event_hash
    return payload


def _receipt_payload(
    receipt: HipFgmresExternalTrustAnchorRegistryReceiptV3,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "genesis": receipt.genesis.to_dict(),
        "activation_endorsements": [
            endorsement.to_dict() for endorsement in receipt.activation_endorsements
        ],
        "registry_hash": receipt.registry_hash,
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
        _fail("hip_fgmres_external_registry_v3_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("hip_fgmres_external_registry_v3_timestamp_invalid", path)
    if parsed.tzinfo != timezone.utc or _format_utc(parsed) != value:
        _fail("hip_fgmres_external_registry_v3_timestamp_invalid", path)
    return parsed


def _format_utc(value: datetime) -> str:
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalTrustAnchorRegistryV3Error(code, path, message)


__all__ = [
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_DOMAIN_V3",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ACTIVATION_PURPOSE_V3",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V3",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V3",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V3",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_STATUS_V3",
    "HipFgmresExternalReviewerRootActivationEndorsementV3",
    "HipFgmresExternalTrustAnchorRegistryClaimsV3",
    "HipFgmresExternalTrustAnchorRegistryGenesisV3",
    "HipFgmresExternalTrustAnchorRegistryReceiptV3",
    "HipFgmresExternalTrustAnchorRegistryResultV3",
    "HipFgmresExternalTrustAnchorRegistryV3Error",
    "compile_hip_fgmres_external_trust_anchor_registry_activation_message_v3",
    "compile_hip_fgmres_external_trust_anchor_registry_genesis_v3",
    "validate_hip_fgmres_external_trust_anchor_registry_genesis_v3",
    "validate_hip_fgmres_external_trust_anchor_registry_receipt_v3",
    "validate_hip_fgmres_external_trust_anchor_registry_result_v3",
    "verify_hip_fgmres_external_trust_anchor_registry_activation_v3",
]
