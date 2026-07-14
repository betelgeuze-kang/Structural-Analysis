"""Durable local replay ledger integration for external FGMRES evidence v1.

The storage backend is intentionally separated from signed-evidence semantics.
This module is the only layer allowed to combine a freshly replayed release,
the v1 signed verifier, and a durable local acceptance receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib.resources import files
import json
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.evidence.durable_replay_ledger_v1 import (
    DurableReplayAuditReceiptV1,
    DurableReplayLedgerV1,
    DurableReplayReservationReceiptV1,
    DurableReplayStorageReceiptV1,
    audit_durable_replay_ledger_v1,
    begin_durable_replay_acceptance_v1,
    initialize_durable_replay_ledger_v1,
    load_durable_replay_accepted_evidence_v1,
    open_durable_replay_ledger_v1,
    reserve_durable_replay_challenge_v1,
    validate_durable_replay_reservation_receipt_v1,
    validate_durable_replay_storage_receipt_v1,
)

from . import fgmres_external_release_identity_v1 as release_identity
from . import fgmres_external_signed_evidence_v1 as signed_evidence


HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-replay-ledger-receipt.v1"
)
HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_CAPABILITY_PROFILE_V1 = (
    "phase0_external_signed_evidence_local_durable_replay_ledger"
)
HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_EVIDENCE_SCOPE_V1 = (
    "single_configured_local_posix_sqlite_ledger_cross_process_at_most_once_"
    "acceptance_non_promoting"
)
HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1 = (
    "hip_fgmres_external_signed_evidence_v1"
)

_STATUS = "external_signed_evidence_durably_recorded"
_SCHEMA_RESOURCE = "hip_fgmres_external_replay_ledger_receipt_v1.schema.json"
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_KEY_ID_RE = re.compile(r"^ed25519:[a-z0-9][a-z0-9._-]{2,63}:v[1-9][0-9]*$")
_ZERO_HASH = "sha256:" + "0" * 64
_LEDGERED_CHALLENGE_MINT = object()
_DURABLY_VERIFIED_MINT = object()

HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_STABLE_ERROR_CODES_V1 = frozenset(
    {
        "hip_fgmres_external_replay_ledger_challenge_construction_forbidden",
        "hip_fgmres_external_replay_ledger_challenge_invalid",
        "hip_fgmres_external_replay_ledger_durable_result_construction_forbidden",
        "hip_fgmres_external_replay_ledger_durable_result_invalid",
        "hip_fgmres_external_replay_ledger_receipt_type_invalid",
        "hip_fgmres_external_replay_ledger_receipt_invalid",
        "hip_fgmres_external_replay_ledger_ledger_invalid",
        "hip_fgmres_external_replay_ledger_namespace_mismatch",
        "hip_fgmres_external_replay_ledger_schema_invalid",
        "hip_fgmres_external_replay_ledger_schema_validation_failed",
        "hip_fgmres_external_replay_ledger_release_binding_mismatch",
        "hip_fgmres_external_replay_ledger_identity_mismatch",
        "hip_fgmres_external_replay_ledger_signed_receipt_mismatch",
        "hip_fgmres_external_replay_ledger_envelope_challenge_mismatch",
        "hip_fgmres_external_replay_ledger_acceptance_missing",
        "hip_fgmres_external_replay_ledger_acceptance_time_invalid",
        "hip_fgmres_external_replay_ledger_storage_error",
    }
)


class HipFgmresExternalReplayLedgerV1Error(RuntimeError):
    """Stable fail-closed high-level durable replay error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        if code not in HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_STABLE_ERROR_CODES_V1:
            code = "hip_fgmres_external_replay_ledger_storage_error"
        self.code = code
        self.path = path if type(path) is str and path.startswith("/") else "/"
        text = message if type(message) is str and message else code
        self.message = text[:240]
        super().__init__(f"{self.code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReplayLedgerClaimsV1:
    release_artifacts_freshly_replayed: Literal[True] = True
    ledger_issued_challenge_rehydrated: Literal[True] = True
    signed_evidence_receipt_verified: Literal[True] = True
    release_identity_and_signed_receipts_bound: Literal[True] = True
    challenge_reservation_durably_committed: Literal[True] = True
    signed_acceptance_durably_committed: Literal[True] = True
    runner_sequence_cross_process_uniqueness_enforced: Literal[True] = True
    challenge_and_envelope_uniqueness_enforced: Literal[True] = True
    canonical_ledger_event_chain_replayed: Literal[True] = True
    local_sqlite_extra_synchronous_commit_completed: Literal[True] = True
    durable_replay_ledger_verified: Literal[True] = True
    signed_envelope_binds_release_identity_receipt: Literal[False] = False
    exactly_once_delivery_verified: Literal[False] = False
    cross_host_replay_prevented: Literal[False] = False
    coordinated_storage_rollback_resisted: Literal[False] = False
    hostile_same_uid_storage_writer_resisted: Literal[False] = False
    hostile_in_process_mint_isolation_verified: Literal[False] = False
    cryptographic_ledger_authenticity_verified: Literal[False] = False
    hardware_monotonic_anchor_verified: Literal[False] = False
    runner_honesty_verified: Literal[False] = False
    hardware_root_attested: Literal[False] = False
    external_hardware_independently_observed_by_local_process: Literal[False] = False
    same_artifact_two_architecture_verified: Literal[False] = False
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
class HipFgmresExternalReplayLedgerReceiptV1:
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    ledger_id: str
    ledger_namespace: str
    reservation_event_sequence: int
    reservation_event_hash: str
    acceptance_event_sequence: int
    acceptance_event_hash: str
    acceptance_commit_head_event_sequence: int
    acceptance_commit_head_event_hash: str
    request_id: str
    campaign_id: str
    challenge_id: str
    key_id: str
    key_epoch: int
    runner_id: str
    run_sequence: int
    release_binding_hash: str
    release_identity_receipt_hash: str
    trust_registry_hash: str
    fixture_registry_hash: str
    envelope_hash: str
    signed_payload_sha256: str
    signed_evidence_receipt_hash: str
    claims: HipFgmresExternalReplayLedgerClaimsV1
    promotion_eligible: bool
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_replay_ledger_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


class HipFgmresExternalLedgeredChallengeV1:
    """A challenge exposed only after its durable reservation commits."""

    __slots__ = ("_challenge", "_reservation", "_ledger_id", "_mint")

    def __init__(
        self,
        *,
        challenge: signed_evidence.HipFgmresExternalChallengeV1,
        reservation: Any,
        ledger_id: str,
        mint: object,
    ) -> None:
        if (
            mint is not _LEDGERED_CHALLENGE_MINT
            or type(challenge) is not signed_evidence.HipFgmresExternalChallengeV1
            or type(reservation) is not DurableReplayReservationReceiptV1
            or type(ledger_id) is not str
            or _HASH_RE.fullmatch(ledger_id) is None
        ):
            _fail(
                "hip_fgmres_external_replay_ledger_challenge_construction_forbidden",
                "/challenge",
            )
        validate_durable_replay_reservation_receipt_v1(reservation)
        payload = challenge.to_dict()
        if (
            reservation.ledger_id != ledger_id
            or reservation.namespace != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
            or reservation.challenge_id != payload["challenge_id"]
            or reservation.request_id != payload["request_id"]
            or reservation.campaign_id != payload["campaign_id"]
            or reservation.key_id != payload["expected_key_id"]
            or reservation.key_epoch != payload["expected_key_epoch"]
            or reservation.runner_id != payload["expected_runner_id"]
            or reservation.run_sequence != payload["expected_run_sequence"]
            or reservation.release_binding_hash
            != payload["expected_release_binding_hash"]
        ):
            _fail(
                "hip_fgmres_external_replay_ledger_challenge_invalid",
                "/challenge/reservation",
            )
        self._challenge = challenge
        self._reservation = reservation
        self._ledger_id = ledger_id
        self._mint = mint

    @property
    def challenge_id(self) -> str:
        return self._challenge.challenge_id

    @property
    def ledger_id(self) -> str:
        return self._ledger_id

    @property
    def reservation_receipt(self) -> DurableReplayReservationReceiptV1:
        return self._reservation

    def to_dict(self) -> dict[str, Any]:
        return self._challenge.to_dict()


class HipFgmresExternalDurablyVerifiedSignedEvidenceV1:
    """Process-local wrapper around two receipts and a durable acceptance."""

    __slots__ = ("_identity_receipt", "_signed_receipt", "_ledger_receipt", "_mint")

    def __init__(
        self,
        *,
        identity_receipt: release_identity.HipFgmresExternalReleaseIdentityReceiptV1,
        signed_receipt: signed_evidence.HipFgmresExternalSignedEvidenceReceiptV1,
        ledger_receipt: HipFgmresExternalReplayLedgerReceiptV1,
        mint: object,
    ) -> None:
        if mint is not _DURABLY_VERIFIED_MINT:
            _fail(
                "hip_fgmres_external_replay_ledger_durable_result_construction_forbidden",
                "/result",
            )
        release_identity.validate_hip_fgmres_external_release_identity_receipt_v1(
            identity_receipt
        )
        signed_evidence.validate_hip_fgmres_external_signed_evidence_receipt_v1(
            signed_receipt
        )
        validate_hip_fgmres_external_replay_ledger_receipt_v1(ledger_receipt)
        if (
            identity_receipt.release_binding_hash != signed_receipt.release_binding_hash
            or ledger_receipt.release_binding_hash
            != identity_receipt.release_binding_hash
            or ledger_receipt.release_identity_receipt_hash
            != identity_receipt.receipt_hash
            or ledger_receipt.signed_evidence_receipt_hash
            != signed_receipt.receipt_hash
            or ledger_receipt.challenge_id != signed_receipt.challenge_id
            or ledger_receipt.envelope_hash != signed_receipt.envelope_hash
            or ledger_receipt.signed_payload_sha256
            != signed_receipt.signed_payload_sha256
            or ledger_receipt.key_id != signed_receipt.key_id
            or ledger_receipt.key_epoch != signed_receipt.key_epoch
            or ledger_receipt.runner_id != signed_receipt.runner_id
            or ledger_receipt.run_sequence != signed_receipt.run_sequence
            or ledger_receipt.trust_registry_hash != signed_receipt.trust_registry_hash
            or ledger_receipt.fixture_registry_hash
            != signed_receipt.fixture_registry_hash
        ):
            _fail(
                "hip_fgmres_external_replay_ledger_durable_result_invalid",
                "/result",
            )
        self._identity_receipt = identity_receipt
        self._signed_receipt = signed_receipt
        self._ledger_receipt = ledger_receipt
        self._mint = mint

    @property
    def identity_receipt(
        self,
    ) -> release_identity.HipFgmresExternalReleaseIdentityReceiptV1:
        return self._identity_receipt

    @property
    def signed_receipt(
        self,
    ) -> signed_evidence.HipFgmresExternalSignedEvidenceReceiptV1:
        return self._signed_receipt

    @property
    def ledger_receipt(self) -> HipFgmresExternalReplayLedgerReceiptV1:
        return self._ledger_receipt


def _require_replay_ledger(ledger: Any) -> DurableReplayLedgerV1:
    if type(ledger) is not DurableReplayLedgerV1:
        _fail(
            "hip_fgmres_external_replay_ledger_ledger_invalid",
            "/ledger",
        )
    if ledger.namespace != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1:
        _fail(
            "hip_fgmres_external_replay_ledger_namespace_mismatch",
            "/ledger/namespace",
        )
    return ledger


def initialize_hip_fgmres_external_replay_ledger_v1(
    ledger_directory: str,
    *,
    busy_timeout_ms: int = 1000,
) -> DurableReplayLedgerV1:
    """Explicitly initialize one owner-private local replay ledger."""

    return initialize_durable_replay_ledger_v1(
        ledger_directory,
        namespace=HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1,
        busy_timeout_ms=busy_timeout_ms,
    )


def open_hip_fgmres_external_replay_ledger_v1(
    ledger_directory: str,
    *,
    expected_ledger_id: str,
    busy_timeout_ms: int = 1000,
) -> DurableReplayLedgerV1:
    """Open an existing ledger only when its pinned identity matches."""

    return open_durable_replay_ledger_v1(
        ledger_directory,
        expected_ledger_id=expected_ledger_id,
        expected_namespace=HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1,
        busy_timeout_ms=busy_timeout_ms,
    )


def audit_hip_fgmres_external_replay_ledger_v1(
    ledger: DurableReplayLedgerV1,
) -> DurableReplayAuditReceiptV1:
    """Freshly audit the configured local ledger."""

    return audit_durable_replay_ledger_v1(_require_replay_ledger(ledger))


def issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
    *,
    verified_release: release_identity.HipFgmresExternalVerifiedReleaseV1,
    ledger: DurableReplayLedgerV1,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    request_id: str,
    campaign_id: str,
    ttl_seconds: int = 900,
) -> HipFgmresExternalLedgeredChallengeV1:
    """Freshly replay a release and expose a challenge after durable reserve."""

    ledger = _require_replay_ledger(ledger)
    release_identity._validate_verified_release(verified_release)
    challenge = release_identity.issue_hip_fgmres_external_evidence_challenge_for_verified_release_v1(
        verified_release=verified_release,
        key_id=key_id,
        runner_id=runner_id,
        run_sequence=run_sequence,
        request_id=request_id,
        campaign_id=campaign_id,
        ttl_seconds=ttl_seconds,
    )
    reservation = reserve_durable_replay_challenge_v1(
        ledger,
        challenge=challenge.to_dict(),
        release_binding=verified_release.release_binding.to_dict(),
        release_identity=verified_release.identity_receipt.to_dict(),
    )
    validate_durable_replay_reservation_receipt_v1(reservation)
    challenge_payload = challenge.to_dict()
    if (
        reservation.ledger_id != ledger.ledger_id
        or reservation.namespace != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
        or reservation.challenge_id != challenge.challenge_id
        or reservation.request_id != request_id
        or reservation.campaign_id != campaign_id
        or reservation.key_id != key_id
        or reservation.key_epoch != challenge_payload["expected_key_epoch"]
        or reservation.runner_id != runner_id
        or reservation.run_sequence != run_sequence
        or reservation.release_binding_hash
        != verified_release.release_binding.binding_hash
        or reservation.release_identity_receipt_hash
        != verified_release.identity_receipt.receipt_hash
    ):
        _fail(
            "hip_fgmres_external_replay_ledger_challenge_invalid",
            "/challenge",
        )
    return HipFgmresExternalLedgeredChallengeV1(
        challenge=challenge,
        reservation=reservation,
        ledger_id=ledger.ledger_id,
        mint=_LEDGERED_CHALLENGE_MINT,
    )


def verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
    envelope_bytes: bytes,
    *,
    verified_release: release_identity.HipFgmresExternalVerifiedReleaseV1,
    ledger: DurableReplayLedgerV1,
) -> HipFgmresExternalDurablyVerifiedSignedEvidenceV1:
    """Rehydrate one ledger challenge and durably accept verified evidence."""

    ledger = _require_replay_ledger(ledger)
    release_identity._validate_verified_release(verified_release)
    routing = signed_evidence._extract_hip_fgmres_external_envelope_routing_v1(
        envelope_bytes
    )
    routed_envelope = signed_evidence._parse_canonical_envelope(envelope_bytes)
    runner_completed_at = signed_evidence._parse_utc(
        routed_envelope["signed_payload"]["runner"]["completed_at_utc"],
        "/signed_payload/runner/completed_at_utc",
    )
    challenge_id = routing.get("challenge_id")
    if type(challenge_id) is not str or _HASH_RE.fullmatch(challenge_id) is None:
        _fail(
            "hip_fgmres_external_replay_ledger_envelope_challenge_mismatch",
            "/envelope/challenge_id",
        )
    snapshot_transaction = begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=challenge_id,
    )
    with snapshot_transaction:
        if (
            snapshot_transaction.ledger_id != ledger.ledger_id
            or snapshot_transaction.namespace
            != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
        ):
            _fail(
                "hip_fgmres_external_replay_ledger_namespace_mismatch",
                "/acceptance/snapshot",
            )
        reservation = snapshot_transaction.reservation_receipt
        stored_challenge = snapshot_transaction.challenge_payload
        stored_release_binding = snapshot_transaction.release_binding_payload
        stored_release_identity = snapshot_transaction.release_identity_payload
    if routing != stored_challenge:
        _fail(
            "hip_fgmres_external_replay_ledger_envelope_challenge_mismatch",
            "/envelope/challenge",
        )
    release_identity.verify_hip_fgmres_external_release_artifacts_v1(verified_release)
    _require_stored_release_matches(
        stored_release_binding,
        stored_release_identity,
        verified_release=verified_release,
    )
    challenge = signed_evidence._rehydrate_hip_fgmres_external_challenge_v1(
        stored_challenge
    )
    trust_registry = signed_evidence._TRUST_REGISTRY_LOADER_AUTHORITY()
    fixture_registry = signed_evidence._FIXTURE_REGISTRY_LOADER_AUTHORITY()
    storage_box: list[DurableReplayStorageReceiptV1] = []

    def durable_commit(
        signed_receipt: signed_evidence.HipFgmresExternalSignedEvidenceReceiptV1,
    ) -> None:
        release_identity.verify_hip_fgmres_external_release_artifacts_v1(
            verified_release
        )
        commit_started_at = signed_evidence._utc_now()
        issued_at = signed_evidence._parse_utc(
            stored_challenge["issued_at_utc"],
            "/challenge/issued_at_utc",
        )
        expires_at = signed_evidence._parse_utc(
            stored_challenge["expires_at_utc"],
            "/challenge/expires_at_utc",
        )
        acceptance_not_before = max(commit_started_at, runner_completed_at)
        if not issued_at <= acceptance_not_before <= expires_at:
            _fail(
                "hip_fgmres_external_replay_ledger_acceptance_time_invalid",
                "/acceptance/time",
            )
        commit_transaction = begin_durable_replay_acceptance_v1(
            ledger,
            challenge_id=challenge_id,
        )
        with commit_transaction:
            if (
                commit_transaction.ledger_id != ledger.ledger_id
                or commit_transaction.namespace
                != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
                or commit_transaction.reservation_receipt != reservation
                or commit_transaction.challenge_payload != stored_challenge
                or commit_transaction.release_binding_payload != stored_release_binding
                or commit_transaction.release_identity_payload
                != stored_release_identity
            ):
                _fail(
                    "hip_fgmres_external_replay_ledger_challenge_invalid",
                    "/acceptance/snapshot",
                )
            storage = commit_transaction.commit(
                envelope_bytes=envelope_bytes,
                signed_receipt=signed_receipt.to_dict(),
                accepted_not_before_utc=signed_evidence._format_utc(
                    acceptance_not_before
                ),
            )
        accepted_at = signed_evidence._parse_utc(
            storage.accepted_at_utc,
            "/acceptance/accepted_at_utc",
        )
        if not acceptance_not_before <= accepted_at <= expires_at:
            _fail(
                "hip_fgmres_external_replay_ledger_acceptance_time_invalid",
                "/acceptance/accepted_at_utc",
            )
        storage_box.append(storage)

    signed_receipt = signed_evidence._verify_with_authorities(
        envelope_bytes,
        challenge=challenge,
        release_binding=verified_release.release_binding,
        trust_registry=trust_registry,
        fixture_registry=fixture_registry,
        success_commit_hook=durable_commit,
    )
    if len(storage_box) != 1:
        _fail(
            "hip_fgmres_external_replay_ledger_acceptance_missing",
            "/acceptance",
        )
    ledger_receipt = _compile_replay_ledger_receipt(
        reservation=reservation,
        storage=storage_box[0],
        identity_receipt=verified_release.identity_receipt,
        signed_receipt=signed_receipt,
    )
    return HipFgmresExternalDurablyVerifiedSignedEvidenceV1(
        identity_receipt=verified_release.identity_receipt,
        signed_receipt=signed_receipt,
        ledger_receipt=ledger_receipt,
        mint=_DURABLY_VERIFIED_MINT,
    )


def recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v1(
    *,
    verified_release: release_identity.HipFgmresExternalVerifiedReleaseV1,
    ledger: DurableReplayLedgerV1,
    challenge_id: str,
    expected_envelope_hash: str,
) -> HipFgmresExternalDurablyVerifiedSignedEvidenceV1:
    """Re-verify and recover one already committed durable acceptance."""

    ledger = _require_replay_ledger(ledger)
    if (
        type(challenge_id) is not str
        or _HASH_RE.fullmatch(challenge_id) is None
        or type(expected_envelope_hash) is not str
        or _HASH_RE.fullmatch(expected_envelope_hash) is None
    ):
        _fail(
            "hip_fgmres_external_replay_ledger_durable_result_invalid",
            "/recovery",
        )
    release_identity._validate_verified_release(verified_release)
    release_identity.verify_hip_fgmres_external_release_artifacts_v1(verified_release)
    accepted = load_durable_replay_accepted_evidence_v1(
        ledger,
        challenge_id=challenge_id,
    )
    _require_stored_release_matches(
        accepted.release_binding_payload,
        accepted.release_identity_payload,
        verified_release=verified_release,
    )
    if (
        accepted.ledger_id != ledger.ledger_id
        or accepted.storage_receipt.envelope_hash != expected_envelope_hash
        or accepted.storage_receipt.challenge_id != challenge_id
        or signed_evidence._extract_hip_fgmres_external_envelope_routing_v1(
            accepted.envelope_bytes
        )
        != accepted.challenge_payload
    ):
        _fail(
            "hip_fgmres_external_replay_ledger_durable_result_invalid",
            "/recovery",
        )
    challenge = signed_evidence._rehydrate_hip_fgmres_external_challenge_v1(
        accepted.challenge_payload
    )
    trust_registry = signed_evidence._TRUST_REGISTRY_LOADER_AUTHORITY()
    fixture_registry = signed_evidence._FIXTURE_REGISTRY_LOADER_AUTHORITY()
    accepted_at = signed_evidence._parse_utc(
        accepted.storage_receipt.accepted_at_utc,
        "/acceptance/accepted_at_utc",
    )
    reverified_receipt = signed_evidence._verify_with_authorities(
        accepted.envelope_bytes,
        challenge=challenge,
        release_binding=verified_release.release_binding,
        trust_registry=trust_registry,
        fixture_registry=fixture_registry,
        now=accepted_at,
    )
    stored_receipt = _parse_signed_receipt(accepted.signed_receipt_payload)
    if reverified_receipt != stored_receipt:
        _fail(
            "hip_fgmres_external_replay_ledger_signed_receipt_mismatch",
            "/signed_receipt",
        )
    signed_receipt = reverified_receipt
    ledger_receipt = _compile_replay_ledger_receipt(
        reservation=accepted.reservation_receipt,
        storage=accepted.storage_receipt,
        identity_receipt=verified_release.identity_receipt,
        signed_receipt=signed_receipt,
    )
    return HipFgmresExternalDurablyVerifiedSignedEvidenceV1(
        identity_receipt=verified_release.identity_receipt,
        signed_receipt=signed_receipt,
        ledger_receipt=ledger_receipt,
        mint=_DURABLY_VERIFIED_MINT,
    )


def validate_hip_fgmres_external_replay_ledger_receipt_v1(
    receipt: HipFgmresExternalReplayLedgerReceiptV1,
) -> HipFgmresExternalReplayLedgerReceiptV1:
    """Validate detached receipt structure without re-opening its ledger."""

    if (
        type(receipt) is not HipFgmresExternalReplayLedgerReceiptV1
        or type(receipt.claims) is not HipFgmresExternalReplayLedgerClaimsV1
    ):
        _fail("hip_fgmres_external_replay_ledger_receipt_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    _validate_schema(payload)
    hashes = (
        receipt.ledger_id,
        receipt.reservation_event_hash,
        receipt.acceptance_event_hash,
        receipt.acceptance_commit_head_event_hash,
        receipt.challenge_id,
        receipt.release_binding_hash,
        receipt.release_identity_receipt_hash,
        receipt.trust_registry_hash,
        receipt.fixture_registry_hash,
        receipt.envelope_hash,
        receipt.signed_payload_sha256,
        receipt.signed_evidence_receipt_hash,
        receipt.receipt_hash,
    )
    integers = (
        receipt.reservation_event_sequence,
        receipt.acceptance_event_sequence,
        receipt.acceptance_commit_head_event_sequence,
        receipt.key_epoch,
        receipt.run_sequence,
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_RECEIPT_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_CAPABILITY_PROFILE_V1
        or receipt.status != _STATUS
        or receipt.evidence_scope != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_EVIDENCE_SCOPE_V1
        or receipt.ledger_namespace != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
        or any(_HASH_RE.fullmatch(value) is None for value in hashes)
        or any(type(value) is not int or value <= 0 for value in integers)
        or receipt.acceptance_event_sequence <= receipt.reservation_event_sequence
        or receipt.acceptance_commit_head_event_sequence
        != receipt.acceptance_event_sequence
        or receipt.acceptance_commit_head_event_hash != receipt.acceptance_event_hash
        or _ID_RE.fullmatch(receipt.request_id) is None
        or _ID_RE.fullmatch(receipt.campaign_id) is None
        or _ID_RE.fullmatch(receipt.runner_id) is None
        or _KEY_ID_RE.fullmatch(receipt.key_id) is None
        or receipt.claims != HipFgmresExternalReplayLedgerClaimsV1()
        or receipt.promotion_eligible is not False
        or receipt.receipt_hash
        != canonical_hash(_receipt_payload(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_external_replay_ledger_receipt_invalid", "/")
    return receipt


def _compile_replay_ledger_receipt(
    *,
    reservation: DurableReplayReservationReceiptV1,
    storage: DurableReplayStorageReceiptV1,
    identity_receipt: release_identity.HipFgmresExternalReleaseIdentityReceiptV1,
    signed_receipt: signed_evidence.HipFgmresExternalSignedEvidenceReceiptV1,
) -> HipFgmresExternalReplayLedgerReceiptV1:
    validate_durable_replay_reservation_receipt_v1(reservation)
    validate_durable_replay_storage_receipt_v1(storage)
    release_identity.validate_hip_fgmres_external_release_identity_receipt_v1(
        identity_receipt
    )
    signed_evidence.validate_hip_fgmres_external_signed_evidence_receipt_v1(
        signed_receipt
    )
    if (
        reservation.ledger_id != storage.ledger_id
        or reservation.namespace != storage.namespace
        or storage.namespace != HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
        or reservation.challenge_id != storage.challenge_id
        or reservation.campaign_id != storage.campaign_id
        or reservation.runner_id != storage.runner_id
        or reservation.run_sequence != storage.run_sequence
        or reservation.challenge_id != signed_receipt.challenge_id
        or reservation.key_id != signed_receipt.key_id
        or reservation.key_epoch != signed_receipt.key_epoch
        or reservation.runner_id != signed_receipt.runner_id
        or reservation.run_sequence != signed_receipt.run_sequence
        or reservation.release_binding_hash != signed_receipt.release_binding_hash
        or reservation.release_binding_hash != identity_receipt.release_binding_hash
        or reservation.release_identity_receipt_hash != identity_receipt.receipt_hash
        or storage.envelope_hash != signed_receipt.envelope_hash
        or storage.signed_payload_sha256 != signed_receipt.signed_payload_sha256
        or storage.signed_receipt_hash != signed_receipt.receipt_hash
        or storage.event_sequence <= reservation.event_sequence
    ):
        _fail(
            "hip_fgmres_external_replay_ledger_signed_receipt_mismatch",
            "/acceptance",
        )
    draft = HipFgmresExternalReplayLedgerReceiptV1(
        schema_version=HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_RECEIPT_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_CAPABILITY_PROFILE_V1,
        status=_STATUS,
        evidence_scope=HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_EVIDENCE_SCOPE_V1,
        ledger_id=storage.ledger_id,
        ledger_namespace=storage.namespace,
        reservation_event_sequence=reservation.event_sequence,
        reservation_event_hash=reservation.event_hash,
        acceptance_event_sequence=storage.event_sequence,
        acceptance_event_hash=storage.event_hash,
        acceptance_commit_head_event_sequence=storage.event_sequence,
        acceptance_commit_head_event_hash=storage.event_hash,
        request_id=reservation.request_id,
        campaign_id=reservation.campaign_id,
        challenge_id=reservation.challenge_id,
        key_id=reservation.key_id,
        key_epoch=reservation.key_epoch,
        runner_id=reservation.runner_id,
        run_sequence=reservation.run_sequence,
        release_binding_hash=reservation.release_binding_hash,
        release_identity_receipt_hash=reservation.release_identity_receipt_hash,
        trust_registry_hash=signed_receipt.trust_registry_hash,
        fixture_registry_hash=signed_receipt.fixture_registry_hash,
        envelope_hash=storage.envelope_hash,
        signed_payload_sha256=storage.signed_payload_sha256,
        signed_evidence_receipt_hash=storage.signed_receipt_hash,
        claims=HipFgmresExternalReplayLedgerClaimsV1(),
        promotion_eligible=False,
        receipt_hash=_ZERO_HASH,
    )
    result = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_external_replay_ledger_receipt_v1(result)


def _require_stored_release_matches(
    stored_binding: dict[str, Any],
    stored_identity: dict[str, Any],
    *,
    verified_release: release_identity.HipFgmresExternalVerifiedReleaseV1,
) -> None:
    if stored_binding != verified_release.release_binding.to_dict():
        _fail(
            "hip_fgmres_external_replay_ledger_release_binding_mismatch",
            "/release_binding",
        )
    if stored_identity != verified_release.identity_receipt.to_dict():
        _fail(
            "hip_fgmres_external_replay_ledger_identity_mismatch",
            "/release_identity",
        )


def _parse_signed_receipt(
    payload: dict[str, Any],
) -> signed_evidence.HipFgmresExternalSignedEvidenceReceiptV1:
    try:
        values = dict(payload)
        values["verified_slot_ids"] = tuple(values["verified_slot_ids"])
        values["claims"] = signed_evidence.HipFgmresExternalSignedEvidenceClaimsV1(
            **values["claims"]
        )
        receipt = signed_evidence.HipFgmresExternalSignedEvidenceReceiptV1(**values)
        return signed_evidence.validate_hip_fgmres_external_signed_evidence_receipt_v1(
            receipt
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_external_replay_ledger_signed_receipt_mismatch",
            "/signed_receipt",
            f"{type(exc).__name__}: {exc}",
        )


def _receipt_payload(
    receipt: HipFgmresExternalReplayLedgerReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "ledger_id": receipt.ledger_id,
        "ledger_namespace": receipt.ledger_namespace,
        "reservation_event_sequence": receipt.reservation_event_sequence,
        "reservation_event_hash": receipt.reservation_event_hash,
        "acceptance_event_sequence": receipt.acceptance_event_sequence,
        "acceptance_event_hash": receipt.acceptance_event_hash,
        "acceptance_commit_head_event_sequence": (
            receipt.acceptance_commit_head_event_sequence
        ),
        "acceptance_commit_head_event_hash": receipt.acceptance_commit_head_event_hash,
        "request_id": receipt.request_id,
        "campaign_id": receipt.campaign_id,
        "challenge_id": receipt.challenge_id,
        "key_id": receipt.key_id,
        "key_epoch": receipt.key_epoch,
        "runner_id": receipt.runner_id,
        "run_sequence": receipt.run_sequence,
        "release_binding_hash": receipt.release_binding_hash,
        "release_identity_receipt_hash": receipt.release_identity_receipt_hash,
        "trust_registry_hash": receipt.trust_registry_hash,
        "fixture_registry_hash": receipt.fixture_registry_hash,
        "envelope_hash": receipt.envelope_hash,
        "signed_payload_sha256": receipt.signed_payload_sha256,
        "signed_evidence_receipt_hash": receipt.signed_evidence_receipt_hash,
        "claims": receipt.claims.to_dict(),
        "promotion_eligible": receipt.promotion_eligible,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _validate_schema(payload: dict[str, Any]) -> None:
    try:
        schema = json.loads(
            files("structural_analysis.schemas")
            .joinpath(_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except SchemaError as exc:
        _fail(
            "hip_fgmres_external_replay_ledger_schema_invalid",
            "/schema",
            exc.message,
        )
    except ValidationError as exc:
        pointer = "/" + "/".join(str(part) for part in exc.absolute_path)
        _fail(
            "hip_fgmres_external_replay_ledger_schema_validation_failed",
            pointer,
            exc.message,
        )
    except (OSError, ValueError, TypeError) as exc:
        _fail(
            "hip_fgmres_external_replay_ledger_schema_invalid",
            "/schema",
            f"{type(exc).__name__}: {exc}",
        )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalReplayLedgerV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1",
    "HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_RECEIPT_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_STABLE_ERROR_CODES_V1",
    "HipFgmresExternalDurablyVerifiedSignedEvidenceV1",
    "HipFgmresExternalLedgeredChallengeV1",
    "HipFgmresExternalReplayLedgerClaimsV1",
    "HipFgmresExternalReplayLedgerReceiptV1",
    "HipFgmresExternalReplayLedgerV1Error",
    "audit_hip_fgmres_external_replay_ledger_v1",
    "initialize_hip_fgmres_external_replay_ledger_v1",
    "issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1",
    "open_hip_fgmres_external_replay_ledger_v1",
    "recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v1",
    "validate_hip_fgmres_external_replay_ledger_receipt_v1",
    "verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1",
]
