"""Owner-private SQLite replay ledger for externally signed evidence.

The ledger makes challenge reservation and signed-evidence acceptance durable
across interpreter and process restarts.  It is deliberately generic: callers
store canonical challenge, release-binding, release-identity, envelope, and
verification-receipt payloads while the domain verifier remains responsible
for their structural-analysis semantics.

Initialization is explicit.  Every later operation opens the existing database
in ``mode=rw``, pins the original regular-file inode, uses ``BEGIN IMMEDIATE``
for mutations, and audits immutable canonical blobs and an append-only event
hash chain.  This is local POSIX durability, not remote consensus, hostile-root
isolation, hardware attestation, or evidence promotion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib import resources
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
from typing import Any, NoReturn
from urllib.parse import quote

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)


DURABLE_REPLAY_LEDGER_SCHEMA_VERSION_V1 = "structural-analysis-durable-replay-ledger.v1"
DURABLE_REPLAY_RESERVATION_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-durable-replay-reservation-receipt.v1"
)
DURABLE_REPLAY_STORAGE_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-durable-replay-storage-receipt.v1"
)
DURABLE_REPLAY_AUDIT_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-durable-replay-audit-receipt.v1"
)

_DATABASE_FILENAME = "durable-replay-ledger-v1.sqlite3"
_RECEIPT_SCHEMA_RESOURCE = "durable_replay_ledger_receipts_v1.schema.json"
_APPLICATION_ID = 0x53525632
_USER_VERSION = 1
_DEFAULT_BUSY_TIMEOUT_MS = 1000
_MIN_BUSY_TIMEOUT_MS = 1
_MAX_BUSY_TIMEOUT_MS = 5000
_MAX_CAMPAIGNS = 10_000
_MAX_CHALLENGES = 100_000
_MAX_ACCEPTANCES = 100_000
_MAX_EVENTS = 200_000
_MAX_CHALLENGE_BYTES = 64 * 1024
_MAX_RELEASE_BINDING_BYTES = 256 * 1024
_MAX_RELEASE_IDENTITY_BYTES = 512 * 1024
_MAX_ENVELOPE_BYTES = 4 * 1024 * 1024
_MAX_SIGNED_RECEIPT_BYTES = 512 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024
_MAX_EVENT_BYTES = 64 * 1024
_DATABASE_PAGE_SIZE = 4096
_MAX_DATABASE_BYTES = 512 * 1024 * 1024
_MAX_DATABASE_PAGES = _MAX_DATABASE_BYTES // _DATABASE_PAGE_SIZE
_MAX_JSON_NODES = 200_000
_MAX_JSON_DEPTH = 64
_MAX_JSON_KEY_BYTES = 1024
_MAX_JSON_STRING_BYTES = 4 * 1024 * 1024
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
_ZERO_HASH = "sha256:" + "0" * 64

DURABLE_REPLAY_LEDGER_STABLE_ERROR_CODES_V1 = frozenset(
    {
        "durable_replay_acceptance_blob_hash_invalid",
        "durable_replay_acceptance_conflict",
        "durable_replay_acceptance_event_binding_invalid",
        "durable_replay_acceptance_event_cardinality_invalid",
        "durable_replay_acceptance_not_before_not_reached",
        "durable_replay_acceptance_row_binding_invalid",
        "durable_replay_acceptance_sequence_noncontiguous",
        "durable_replay_acceptance_transaction_closed",
        "durable_replay_accepted_evidence_binding_invalid",
        "durable_replay_accepted_evidence_not_found",
        "durable_replay_accepted_evidence_type_invalid",
        "durable_replay_audit_receipt_claim_invalid",
        "durable_replay_audit_receipt_count_invalid",
        "durable_replay_audit_receipt_event_extent_invalid",
        "durable_replay_audit_receipt_event_hash_invalid",
        "durable_replay_audit_receipt_event_sequence_invalid",
        "durable_replay_audit_receipt_type_invalid",
        "durable_replay_blob_extent_invalid",
        "durable_replay_campaign_identity_drift",
        "durable_replay_campaign_orphaned",
        "durable_replay_canonical_blob_bom_forbidden",
        "durable_replay_canonical_blob_duplicate_key",
        "durable_replay_canonical_blob_extent_invalid",
        "durable_replay_canonical_blob_hash_invalid",
        "durable_replay_canonical_blob_json_invalid",
        "durable_replay_canonical_blob_not_canonical",
        "durable_replay_canonical_blob_root_invalid",
        "durable_replay_challenge_already_accepted",
        "durable_replay_challenge_campaign_missing",
        "durable_replay_challenge_expired_at_acceptance",
        "durable_replay_challenge_hash_invalid",
        "durable_replay_challenge_id_reused",
        "durable_replay_challenge_not_reserved",
        "durable_replay_challenge_row_binding_invalid",
        "durable_replay_challenge_time_window_invalid",
        "durable_replay_envelope_bytes_type_invalid",
        "durable_replay_envelope_challenge_type_invalid",
        "durable_replay_envelope_hash_invalid",
        "durable_replay_envelope_hash_reused",
        "durable_replay_envelope_release_type_invalid",
        "durable_replay_envelope_reservation_binding_invalid",
        "durable_replay_envelope_runner_type_invalid",
        "durable_replay_envelope_stored_challenge_mismatch",
        "durable_replay_envelope_stored_release_mismatch",
        "durable_replay_event_blob_hash_invalid",
        "durable_replay_event_cardinality_invalid",
        "durable_replay_event_chain_invalid",
        "durable_replay_event_extent_invalid",
        "durable_replay_event_hash_invalid",
        "durable_replay_event_sequence_noncontiguous",
        "durable_replay_hash_invalid",
        "durable_replay_id_invalid",
        "durable_replay_json_extent_invalid",
        "durable_replay_json_integer_extent_invalid",
        "durable_replay_json_key_extent_invalid",
        "durable_replay_json_key_type_invalid",
        "durable_replay_json_nonfinite",
        "durable_replay_json_string_extent_invalid",
        "durable_replay_json_value_type_invalid",
        "durable_replay_ledger_acceptance_capacity_exceeded",
        "durable_replay_ledger_already_initialized",
        "durable_replay_ledger_busy",
        "durable_replay_ledger_busy_timeout_invalid",
        "durable_replay_ledger_campaign_capacity_exceeded",
        "durable_replay_ledger_challenge_capacity_exceeded",
        "durable_replay_ledger_closed",
        "durable_replay_ledger_commit_ambiguous",
        "durable_replay_ledger_corrupt",
        "durable_replay_ledger_database_create_failed",
        "durable_replay_ledger_database_extent_invalid",
        "durable_replay_ledger_database_file_invalid",
        "durable_replay_ledger_database_missing",
        "durable_replay_ledger_database_open_failed",
        "durable_replay_ledger_directory_inode_replaced",
        "durable_replay_ledger_directory_invalid",
        "durable_replay_ledger_directory_missing",
        "durable_replay_ledger_directory_not_absolute",
        "durable_replay_ledger_directory_not_owner_private",
        "durable_replay_ledger_directory_open_failed",
        "durable_replay_ledger_directory_pin_lost",
        "durable_replay_ledger_directory_type_invalid",
        "durable_replay_ledger_event_capacity_exceeded",
        "durable_replay_ledger_expected_id_required",
        "durable_replay_ledger_expected_namespace_required",
        "durable_replay_ledger_header_blob_hash_invalid",
        "durable_replay_ledger_header_invalid",
        "durable_replay_ledger_header_missing",
        "durable_replay_ledger_header_shape_invalid",
        "durable_replay_ledger_identity_mismatch",
        "durable_replay_ledger_immutable",
        "durable_replay_ledger_inode_pin_lost",
        "durable_replay_ledger_inode_replaced",
        "durable_replay_ledger_internal_error",
        "durable_replay_ledger_journal_mode_invalid",
        "durable_replay_ledger_namespace_mismatch",
        "durable_replay_ledger_posix_required",
        "durable_replay_ledger_pragma_contract_invalid",
        "durable_replay_ledger_quick_check_failed",
        "durable_replay_ledger_row_capacity_exceeded",
        "durable_replay_ledger_schema_creation_mismatch",
        "durable_replay_ledger_schema_manifest_invalid",
        "durable_replay_ledger_schema_object_count_invalid",
        "durable_replay_ledger_schema_object_invalid",
        "durable_replay_ledger_sidecar_invalid",
        "durable_replay_ledger_sqlite_error",
        "durable_replay_ledger_sync_failed",
        "durable_replay_ledger_type_invalid",
        "durable_replay_ledger_wal_sidecar_forbidden",
        "durable_replay_namespace_invalid",
        "durable_replay_nonnegative_integer_invalid",
        "durable_replay_payload_conversion_failed",
        "durable_replay_payload_extent_invalid",
        "durable_replay_payload_not_canonicalizable",
        "durable_replay_payload_root_invalid",
        "durable_replay_payload_type_invalid",
        "durable_replay_positive_integer_invalid",
        "durable_replay_receipt_hash_invalid",
        "durable_replay_receipt_schema_invalid",
        "durable_replay_receipt_schema_validation_failed",
        "durable_replay_receipt_semantics_invalid",
        "durable_replay_release_binding_hash_invalid",
        "durable_replay_release_binding_mismatch",
        "durable_replay_release_identity_binding_mismatch",
        "durable_replay_release_identity_hash_invalid",
        "durable_replay_request_id_reused",
        "durable_replay_required_field_missing",
        "durable_replay_reservation_conflict",
        "durable_replay_reservation_event_binding_invalid",
        "durable_replay_reservation_event_cardinality_invalid",
        "durable_replay_reservation_event_orphan",
        "durable_replay_reservation_receipt_binding_invalid",
        "durable_replay_reservation_receipt_parse_invalid",
        "durable_replay_reservation_receipt_type_invalid",
        "durable_replay_runner_sequence_duplicate",
        "durable_replay_runner_sequence_not_increasing",
        "durable_replay_signed_payload_hash_invalid",
        "durable_replay_signed_payload_hash_reused",
        "durable_replay_signed_payload_type_invalid",
        "durable_replay_signed_receipt_envelope_binding_invalid",
        "durable_replay_signed_receipt_hash_invalid",
        "durable_replay_signed_receipt_hash_reused",
        "durable_replay_signed_receipt_reservation_binding_invalid",
        "durable_replay_storage_receipt_parse_invalid",
        "durable_replay_storage_receipt_type_invalid",
        "durable_replay_text_invalid",
        "durable_replay_timestamp_invalid",
    }
)


class DurableReplayLedgerV1Error(RuntimeError):
    """Stable, bounded, fail-closed durable-ledger error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        if code not in DURABLE_REPLAY_LEDGER_STABLE_ERROR_CODES_V1:
            code = "durable_replay_ledger_internal_error"
        self.code = code
        self.path = path if type(path) is str and path.startswith("/") else "/"
        self.path = _bounded_message(self.path)
        self.message = _bounded_message(message or code)
        super().__init__(f"{code}@{self.path}: {self.message}")


@dataclass(frozen=True, slots=True)
class DurableReplayReservationReceiptV1:
    schema_version: str
    status: str
    ledger_id: str
    namespace: str
    challenge_id: str
    request_id: str
    campaign_id: str
    key_id: str
    key_epoch: int
    runner_id: str
    run_sequence: int
    release_binding_hash: str
    release_identity_receipt_hash: str
    event_sequence: int
    event_hash: str
    reserved_at_utc: str
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_durable_replay_reservation_receipt_v1(self)
        return _dataclass_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class DurableReplayStorageReceiptV1:
    schema_version: str
    status: str
    ledger_id: str
    namespace: str
    challenge_id: str
    campaign_id: str
    runner_id: str
    run_sequence: int
    acceptance_sequence: int
    envelope_hash: str
    signed_payload_sha256: str
    signed_receipt_hash: str
    event_sequence: int
    event_hash: str
    accepted_at_utc: str
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_durable_replay_storage_receipt_v1(self)
        return _dataclass_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class DurableReplayAuditReceiptV1:
    schema_version: str
    status: str
    ledger_id: str
    namespace: str
    schema_manifest_hash: str
    campaign_count: int
    challenge_count: int
    acceptance_count: int
    event_count: int
    last_event_sequence: int
    last_event_hash: str
    quick_check_ok: bool
    canonical_blobs_verified: bool
    event_chain_verified: bool
    audited_at_utc: str
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_durable_replay_audit_receipt_v1(self)
        return _dataclass_payload(self, include_hash=True)


class DurableReplayAcceptedEvidenceV1:
    """Immutable canonical bytes loaded from one committed acceptance."""

    __slots__ = (
        "ledger_id",
        "namespace",
        "_challenge_blob",
        "_release_binding_blob",
        "_release_identity_blob",
        "_reservation_receipt_blob",
        "_envelope_blob",
        "_signed_receipt_blob",
        "storage_receipt",
    )

    def __init__(
        self,
        *,
        ledger_id: str,
        namespace: str,
        challenge_blob: bytes,
        release_binding_blob: bytes,
        release_identity_blob: bytes,
        reservation_receipt_blob: bytes,
        envelope_blob: bytes,
        signed_receipt_blob: bytes,
        storage_receipt: DurableReplayStorageReceiptV1,
    ) -> None:
        self.ledger_id = ledger_id
        self.namespace = namespace
        self._challenge_blob = bytes(challenge_blob)
        self._release_binding_blob = bytes(release_binding_blob)
        self._release_identity_blob = bytes(release_identity_blob)
        self._reservation_receipt_blob = bytes(reservation_receipt_blob)
        self._envelope_blob = bytes(envelope_blob)
        self._signed_receipt_blob = bytes(signed_receipt_blob)
        self.storage_receipt = storage_receipt

    @property
    def challenge_payload(self) -> dict[str, Any]:
        return _decode_known_canonical_blob(
            self._challenge_blob,
            path="/accepted/challenge",
            max_bytes=_MAX_CHALLENGE_BYTES,
        )

    @property
    def release_binding_payload(self) -> dict[str, Any]:
        return _decode_known_canonical_blob(
            self._release_binding_blob,
            path="/accepted/release_binding",
            max_bytes=_MAX_RELEASE_BINDING_BYTES,
        )

    @property
    def release_identity_payload(self) -> dict[str, Any]:
        return _decode_known_canonical_blob(
            self._release_identity_blob,
            path="/accepted/release_identity",
            max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
        )

    @property
    def envelope_bytes(self) -> bytes:
        return self._envelope_blob

    @property
    def reservation_receipt(self) -> DurableReplayReservationReceiptV1:
        payload = _decode_known_canonical_blob(
            self._reservation_receipt_blob,
            path="/accepted/reservation_receipt",
            max_bytes=_MAX_RECEIPT_BYTES,
        )
        return _parse_reservation_receipt(payload)

    @property
    def envelope_payload(self) -> dict[str, Any]:
        return _decode_known_canonical_blob(
            self._envelope_blob,
            path="/accepted/envelope",
            max_bytes=_MAX_ENVELOPE_BYTES,
        )

    @property
    def signed_receipt_payload(self) -> dict[str, Any]:
        return _decode_known_canonical_blob(
            self._signed_receipt_blob,
            path="/accepted/signed_receipt",
            max_bytes=_MAX_SIGNED_RECEIPT_BYTES,
        )


class DurableReplayLedgerV1:
    """Pinned handle for an already initialized local ledger."""

    __slots__ = (
        "_busy_timeout_ms",
        "_closed",
        "_database_path",
        "_device",
        "_directory_device",
        "_directory_inode",
        "_directory_path",
        "_directory_pin_fd",
        "_inode",
        "_ledger_id",
        "_namespace",
        "_pin_fd",
    )

    def __init__(
        self,
        *,
        directory_path: Path,
        database_path: Path,
        busy_timeout_ms: int,
        directory_pin_fd: int,
        directory_device: int,
        directory_inode: int,
        pin_fd: int,
        device: int,
        inode: int,
        ledger_id: str,
        namespace: str,
    ) -> None:
        self._directory_path = directory_path
        self._database_path = database_path
        self._busy_timeout_ms = busy_timeout_ms
        self._directory_pin_fd = directory_pin_fd
        self._directory_device = directory_device
        self._directory_inode = directory_inode
        self._pin_fd = pin_fd
        self._device = device
        self._inode = inode
        self._ledger_id = ledger_id
        self._namespace = namespace
        self._closed = False

    @property
    def database_path(self) -> str:
        return os.fspath(self._database_path)

    @property
    def directory_path(self) -> str:
        return os.fspath(self._directory_path)

    @property
    def ledger_id(self) -> str:
        return self._ledger_id

    @property
    def namespace(self) -> str:
        return self._namespace

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                os.close(self._pin_fd)
            except OSError:
                pass
            try:
                os.close(self._directory_pin_fd)
            except OSError:
                pass

    def __enter__(self) -> DurableReplayLedgerV1:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()

    def __del__(self) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            _fail("durable_replay_ledger_closed", "/ledger")

    def _assert_identity(self) -> None:
        self._require_open()
        directory_path_stat = _validate_owner_private_directory(self._directory_path)
        try:
            directory_fd_stat = os.fstat(self._directory_pin_fd)
        except OSError as exc:
            _fail(
                "durable_replay_ledger_directory_pin_lost",
                "/ledger_directory",
                str(exc),
            )
        if (
            directory_path_stat.st_dev != self._directory_device
            or directory_path_stat.st_ino != self._directory_inode
            or directory_fd_stat.st_dev != self._directory_device
            or directory_fd_stat.st_ino != self._directory_inode
        ):
            _fail("durable_replay_ledger_directory_inode_replaced", "/ledger_directory")
        path_stat = _validate_database_path(self._database_path)
        try:
            fd_stat = os.fstat(self._pin_fd)
        except OSError as exc:
            _fail("durable_replay_ledger_inode_pin_lost", "/database", str(exc))
        if (
            path_stat.st_dev != self._device
            or path_stat.st_ino != self._inode
            or fd_stat.st_dev != self._device
            or fd_stat.st_ino != self._inode
        ):
            _fail("durable_replay_ledger_inode_replaced", "/database")


class DurableReplayAcceptanceTransactionV1:
    """One live ``BEGIN IMMEDIATE`` acceptance transaction."""

    __slots__ = (
        "_challenge_blob",
        "_connection",
        "_ledger",
        "_release_binding_blob",
        "_release_identity_blob",
        "_reservation_receipt_blob",
        "_row",
        "_state",
    )

    def __init__(
        self,
        *,
        ledger: DurableReplayLedgerV1,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> None:
        self._ledger = ledger
        self._connection = connection
        self._row = row
        self._challenge_blob = bytes(row["challenge_blob"])
        self._release_binding_blob = bytes(row["release_binding_blob"])
        self._release_identity_blob = bytes(row["release_identity_blob"])
        self._reservation_receipt_blob = bytes(row["reservation_receipt_blob"])
        self._state = "open"

    @property
    def challenge_payload(self) -> dict[str, Any]:
        self._require_open()
        return _decode_known_canonical_blob(
            self._challenge_blob,
            path="/acceptance/challenge",
            max_bytes=_MAX_CHALLENGE_BYTES,
        )

    @property
    def release_binding_payload(self) -> dict[str, Any]:
        self._require_open()
        return _decode_known_canonical_blob(
            self._release_binding_blob,
            path="/acceptance/release_binding",
            max_bytes=_MAX_RELEASE_BINDING_BYTES,
        )

    @property
    def release_identity_payload(self) -> dict[str, Any]:
        self._require_open()
        return _decode_known_canonical_blob(
            self._release_identity_blob,
            path="/acceptance/release_identity",
            max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
        )

    @property
    def challenge_id(self) -> str:
        return str(self._row["challenge_id"])

    @property
    def ledger_id(self) -> str:
        return self._ledger.ledger_id

    @property
    def namespace(self) -> str:
        return self._ledger.namespace

    @property
    def reservation_receipt(self) -> DurableReplayReservationReceiptV1:
        self._require_open()
        payload = _decode_known_canonical_blob(
            self._reservation_receipt_blob,
            path="/acceptance/reservation_receipt",
            max_bytes=_MAX_RECEIPT_BYTES,
        )
        return _parse_reservation_receipt(payload)

    def commit(
        self,
        *,
        envelope_bytes: bytes,
        signed_receipt: object,
        accepted_not_before_utc: str,
    ) -> DurableReplayStorageReceiptV1:
        """Commit after the caller's verifier time floor and SQLite COMMIT."""

        self._require_open()
        try:
            result = _commit_acceptance(
                self,
                envelope_bytes=envelope_bytes,
                signed_receipt=signed_receipt,
                accepted_not_before_utc=accepted_not_before_utc,
            )
            self._ledger._assert_identity()
        except BaseException:
            self._abort_after_error()
            raise
        self._state = "committing"
        try:
            _commit_or_raise_ambiguous(self._connection, path="/acceptance/commit")
        except BaseException:
            self._state = "ambiguous"
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
            raise
        self._state = "committed"
        try:
            self._connection.close()
            self._ledger._assert_identity()
            return result
        except BaseException:
            raise

    def rollback(self) -> None:
        if self._state == "open":
            try:
                self._connection.rollback()
            finally:
                self._state = "rolled_back"
                self._connection.close()

    def close(self) -> None:
        self.rollback()

    def __enter__(self) -> DurableReplayAcceptanceTransactionV1:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.rollback()

    def __del__(self) -> None:
        self.rollback()

    def _require_open(self) -> None:
        if self._state != "open":
            _fail("durable_replay_acceptance_transaction_closed", "/acceptance")

    def _abort_after_error(self) -> None:
        if self._state == "open":
            try:
                self._connection.rollback()
            except sqlite3.Error:
                pass
            self._state = "failed"
            try:
                self._connection.close()
            except sqlite3.Error:
                pass


_TABLE_STATEMENTS = (
    """CREATE TABLE meta (
        meta_key TEXT NOT NULL PRIMARY KEY,
        value_blob BLOB NOT NULL,
        value_sha256 TEXT NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE campaigns (
        campaign_id TEXT NOT NULL PRIMARY KEY,
        runner_id TEXT NOT NULL,
        release_binding_hash TEXT NOT NULL,
        release_binding_blob_sha256 TEXT NOT NULL,
        release_identity_receipt_hash TEXT NOT NULL,
        release_identity_blob_sha256 TEXT NOT NULL,
        trust_registry_hash TEXT NOT NULL,
        fixture_registry_hash TEXT NOT NULL,
        architecture_base TEXT NOT NULL,
        suite_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE challenges (
        challenge_id TEXT NOT NULL PRIMARY KEY,
        request_id TEXT NOT NULL,
        campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
        key_id TEXT NOT NULL,
        key_epoch INTEGER NOT NULL CHECK(key_epoch > 0),
        runner_id TEXT NOT NULL,
        run_sequence INTEGER NOT NULL CHECK(run_sequence > 0),
        release_binding_hash TEXT NOT NULL,
        release_identity_receipt_hash TEXT NOT NULL,
        challenge_blob BLOB NOT NULL,
        challenge_blob_sha256 TEXT NOT NULL,
        release_binding_blob BLOB NOT NULL,
        release_binding_blob_sha256 TEXT NOT NULL,
        release_identity_blob BLOB NOT NULL,
        release_identity_blob_sha256 TEXT NOT NULL,
        reserved_at_utc TEXT NOT NULL,
        reservation_receipt_blob BLOB NOT NULL,
        reservation_receipt_hash TEXT NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE acceptances (
        challenge_id TEXT NOT NULL PRIMARY KEY REFERENCES challenges(challenge_id),
        acceptance_sequence INTEGER NOT NULL,
        envelope_blob BLOB NOT NULL,
        envelope_blob_sha256 TEXT NOT NULL,
        envelope_hash TEXT NOT NULL,
        signed_payload_sha256 TEXT NOT NULL,
        signed_receipt_blob BLOB NOT NULL,
        signed_receipt_blob_sha256 TEXT NOT NULL,
        signed_receipt_hash TEXT NOT NULL,
        accepted_at_utc TEXT NOT NULL,
        event_sequence INTEGER NOT NULL,
        event_hash TEXT NOT NULL,
        storage_receipt_blob BLOB NOT NULL,
        storage_receipt_hash TEXT NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE events (
        event_sequence INTEGER NOT NULL PRIMARY KEY CHECK(event_sequence > 0),
        event_type TEXT NOT NULL,
        object_id TEXT NOT NULL,
        event_blob BLOB NOT NULL,
        event_blob_sha256 TEXT NOT NULL,
        previous_event_hash TEXT NOT NULL,
        event_hash TEXT NOT NULL
    ) WITHOUT ROWID""",
)

_INDEX_STATEMENTS = (
    "CREATE UNIQUE INDEX challenges_request_id_uq ON challenges(request_id)",
    "CREATE UNIQUE INDEX challenges_runner_sequence_uq ON challenges(runner_id, run_sequence)",
    "CREATE INDEX challenges_campaign_idx ON challenges(campaign_id)",
    "CREATE UNIQUE INDEX acceptances_sequence_uq ON acceptances(acceptance_sequence)",
    "CREATE UNIQUE INDEX acceptances_envelope_hash_uq ON acceptances(envelope_hash)",
    "CREATE UNIQUE INDEX acceptances_signed_payload_hash_uq ON acceptances(signed_payload_sha256)",
    "CREATE UNIQUE INDEX acceptances_signed_receipt_hash_uq ON acceptances(signed_receipt_hash)",
    "CREATE UNIQUE INDEX acceptances_event_sequence_uq ON acceptances(event_sequence)",
    "CREATE UNIQUE INDEX acceptances_event_hash_uq ON acceptances(event_hash)",
    "CREATE UNIQUE INDEX events_event_hash_uq ON events(event_hash)",
)

_IMMUTABLE_TABLES = ("meta", "campaigns", "challenges", "acceptances", "events")
_TRIGGER_STATEMENTS = tuple(
    statement
    for table_name in _IMMUTABLE_TABLES
    for statement in (
        f"CREATE TRIGGER {table_name}_reject_update BEFORE UPDATE ON {table_name} "
        "BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END",
        f"CREATE TRIGGER {table_name}_reject_delete BEFORE DELETE ON {table_name} "
        "BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END",
    )
)
_INSERT_GUARD_TRIGGER_STATEMENTS = (
    """CREATE TRIGGER meta_reject_replace BEFORE INSERT ON meta
       WHEN EXISTS (SELECT 1 FROM meta WHERE meta_key = NEW.meta_key)
       BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END""",
    """CREATE TRIGGER campaigns_reject_replace BEFORE INSERT ON campaigns
       WHEN EXISTS (SELECT 1 FROM campaigns WHERE campaign_id = NEW.campaign_id)
       BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END""",
    """CREATE TRIGGER challenges_reject_replace BEFORE INSERT ON challenges
       WHEN EXISTS (
           SELECT 1 FROM challenges
           WHERE challenge_id = NEW.challenge_id
              OR request_id = NEW.request_id
              OR (runner_id = NEW.runner_id AND run_sequence = NEW.run_sequence)
       )
       BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END""",
    """CREATE TRIGGER acceptances_reject_replace BEFORE INSERT ON acceptances
       WHEN EXISTS (
           SELECT 1 FROM acceptances
           WHERE challenge_id = NEW.challenge_id
              OR acceptance_sequence = NEW.acceptance_sequence
              OR envelope_hash = NEW.envelope_hash
              OR signed_payload_sha256 = NEW.signed_payload_sha256
              OR signed_receipt_hash = NEW.signed_receipt_hash
              OR event_sequence = NEW.event_sequence
              OR event_hash = NEW.event_hash
       )
       BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END""",
    """CREATE TRIGGER events_reject_replace BEFORE INSERT ON events
       WHEN EXISTS (
           SELECT 1 FROM events
           WHERE event_sequence = NEW.event_sequence OR event_hash = NEW.event_hash
       )
       BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END""",
)
_SCHEMA_STATEMENTS = (
    _TABLE_STATEMENTS
    + _INDEX_STATEMENTS
    + _TRIGGER_STATEMENTS
    + _INSERT_GUARD_TRIGGER_STATEMENTS
)


def initialize_durable_replay_ledger_v1(
    ledger_directory: str | os.PathLike[str],
    *,
    namespace: str,
    busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
) -> DurableReplayLedgerV1:
    """Explicitly initialize a ledger in an existing owner-private directory."""

    directory = _coerce_directory_path(ledger_directory)
    checked_namespace = _require_namespace(namespace, "/namespace")
    timeout = _validate_busy_timeout(busy_timeout_ms)
    if os.name != "posix":
        _fail("durable_replay_ledger_posix_required", "/ledger_directory")
    directory_stat = _validate_owner_private_directory(directory)
    directory_pin_fd = _open_directory_pin(directory)
    database_path = directory / _DATABASE_FILENAME
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd = -1
    connection: sqlite3.Connection | None = None
    initialized_ledger_id: str | None = None
    commit_started = False
    commit_succeeded = False
    try:
        pinned_directory_stat = os.fstat(directory_pin_fd)
        if (
            pinned_directory_stat.st_dev != directory_stat.st_dev
            or pinned_directory_stat.st_ino != directory_stat.st_ino
        ):
            _fail(
                "durable_replay_ledger_directory_inode_replaced",
                "/ledger_directory",
            )
        try:
            fd = os.open(_DATABASE_FILENAME, flags, 0o600, dir_fd=directory_pin_fd)
        except FileExistsError:
            _fail("durable_replay_ledger_already_initialized", "/database")
        except OSError as exc:
            _fail(
                "durable_replay_ledger_database_create_failed",
                "/database",
                str(exc),
            )
        os.fchmod(fd, 0o600)
        created_stat = os.fstat(fd)
        if (
            not stat.S_ISREG(created_stat.st_mode)
            or created_stat.st_uid != os.geteuid()
            or created_stat.st_nlink != 1
            or stat.S_IMODE(created_stat.st_mode) != 0o600
        ):
            _fail("durable_replay_ledger_database_file_invalid", "/database")
        path_stat = _validate_database_path(database_path, allow_empty=True)
        if (
            path_stat.st_dev != created_stat.st_dev
            or path_stat.st_ino != created_stat.st_ino
        ):
            _fail("durable_replay_ledger_inode_replaced", "/database")
        connection = _connect_database_path(
            database_path,
            timeout,
            initializing=True,
        )
        connection.execute("BEGIN IMMEDIATE")
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)
        manifest_blob = canonical_json_bytes(_actual_schema_manifest(connection))
        expected_manifest = _expected_schema_manifest()
        if manifest_blob != canonical_json_bytes(expected_manifest):
            _fail("durable_replay_ledger_schema_creation_mismatch", "/schema")
        created_at = _format_utc(_utc_now())
        initialized_ledger_id = _new_ledger_id()
        header_without_hash = {
            "schema_version": DURABLE_REPLAY_LEDGER_SCHEMA_VERSION_V1,
            "ledger_id": initialized_ledger_id,
            "namespace": checked_namespace,
            "created_at_utc": created_at,
            "application_id": _APPLICATION_ID,
            "user_version": _USER_VERSION,
            "schema_manifest_hash": sha256_prefixed(manifest_blob),
        }
        header = {
            **header_without_hash,
            "header_hash": canonical_hash(header_without_hash),
        }
        header_blob = canonical_json_bytes(header)
        connection.execute(
            "INSERT INTO meta(meta_key, value_blob, value_sha256) VALUES (?, ?, ?)",
            ("ledger_header", header_blob, sha256_prefixed(header_blob)),
        )
        _fresh_audit_database_state(connection, quick_check=True)
        commit_started = True
        _commit_or_raise_ambiguous(connection, path="/initialize")
        commit_succeeded = True
        connection.close()
        connection = None
        current_path_stat = _validate_database_path(database_path)
        if (
            current_path_stat.st_dev != created_stat.st_dev
            or current_path_stat.st_ino != created_stat.st_ino
        ):
            _fail("durable_replay_ledger_inode_replaced", "/database")
        try:
            os.fsync(fd)
            os.fsync(directory_pin_fd)
        except OSError as exc:
            _fail("durable_replay_ledger_sync_failed", "/database", str(exc))
    except BaseException as exc:
        if connection is not None:
            try:
                if not commit_started:
                    connection.rollback()
            except sqlite3.Error:
                pass
            try:
                connection.close()
            except sqlite3.Error:
                pass
        if fd >= 0 and not commit_started:
            try:
                created_for_cleanup = os.fstat(fd)
            except OSError:
                created_for_cleanup = None
            if created_for_cleanup is not None:
                _unlink_created_database_quiet(
                    directory_pin_fd,
                    database_path,
                    created_for_cleanup,
                )
        if isinstance(exc, DurableReplayLedgerV1Error):
            raise
        if isinstance(exc, sqlite3.Error):
            _raise_sqlite_error(exc, path="/initialize")
        if isinstance(exc, OSError):
            _fail(
                "durable_replay_ledger_database_create_failed",
                "/initialize",
                type(exc).__name__,
            )
        if isinstance(exc, Exception):
            _fail(
                "durable_replay_ledger_internal_error",
                "/initialize",
                type(exc).__name__,
            )
        raise
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.close(directory_pin_fd)
        except OSError:
            pass
    assert commit_succeeded
    assert initialized_ledger_id is not None
    return open_durable_replay_ledger_v1(
        directory,
        expected_ledger_id=initialized_ledger_id,
        expected_namespace=checked_namespace,
        busy_timeout_ms=timeout,
    )


def open_durable_replay_ledger_v1(
    ledger_directory: str | os.PathLike[str],
    *,
    expected_ledger_id: str | None = None,
    expected_namespace: str | None = None,
    busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
) -> DurableReplayLedgerV1:
    """Open an existing ledger without creating a directory or database."""

    directory = _coerce_directory_path(ledger_directory)
    timeout = _validate_busy_timeout(busy_timeout_ms)
    if expected_ledger_id is None:
        _fail("durable_replay_ledger_expected_id_required", "/expected_ledger_id")
    expected_id = _require_hash(expected_ledger_id, "/expected_ledger_id")
    if expected_namespace is None:
        _fail(
            "durable_replay_ledger_expected_namespace_required",
            "/expected_namespace",
        )
    checked_namespace = _require_namespace(
        expected_namespace,
        "/expected_namespace",
    )
    if os.name != "posix":
        _fail("durable_replay_ledger_posix_required", "/ledger_directory")
    directory_path_stat = _validate_owner_private_directory(directory)
    directory_pin_fd = _open_directory_pin(directory)
    database_path = directory / _DATABASE_FILENAME
    pin_fd = -1
    try:
        directory_pin_stat = os.fstat(directory_pin_fd)
        if (
            directory_pin_stat.st_dev != directory_path_stat.st_dev
            or directory_pin_stat.st_ino != directory_path_stat.st_ino
        ):
            _fail(
                "durable_replay_ledger_directory_inode_replaced",
                "/ledger_directory",
            )
        path_stat = _validate_database_path(database_path)
        pin_fd = _open_database_pin(database_path)
        pin_stat = os.fstat(pin_fd)
        if pin_stat.st_dev != path_stat.st_dev or pin_stat.st_ino != path_stat.st_ino:
            _fail("durable_replay_ledger_inode_replaced", "/database")
        connection = _connect_database_path(database_path, timeout, initializing=False)
        try:
            connection.execute("BEGIN")
            header, _, _, _ = _fresh_audit_database_state(
                connection,
                quick_check=True,
            )
            connection.rollback()
        finally:
            connection.close()
        if header["ledger_id"] != expected_id:
            _fail("durable_replay_ledger_identity_mismatch", "/expected_ledger_id")
        if header["namespace"] != checked_namespace:
            _fail(
                "durable_replay_ledger_namespace_mismatch",
                "/expected_namespace",
            )
        ledger = DurableReplayLedgerV1(
            directory_path=directory,
            database_path=database_path,
            busy_timeout_ms=timeout,
            directory_pin_fd=directory_pin_fd,
            directory_device=directory_pin_stat.st_dev,
            directory_inode=directory_pin_stat.st_ino,
            pin_fd=pin_fd,
            device=pin_stat.st_dev,
            inode=pin_stat.st_ino,
            ledger_id=expected_id,
            namespace=checked_namespace,
        )
        directory_pin_fd = -1
        pin_fd = -1
        ledger._assert_identity()
        return ledger
    except BaseException as exc:
        if pin_fd >= 0:
            try:
                os.close(pin_fd)
            except OSError:
                pass
        if directory_pin_fd >= 0:
            try:
                os.close(directory_pin_fd)
            except OSError:
                pass
        if isinstance(exc, DurableReplayLedgerV1Error):
            raise
        if isinstance(exc, sqlite3.Error):
            _raise_sqlite_error(exc, path="/open")
        if isinstance(exc, OSError):
            _fail(
                "durable_replay_ledger_database_open_failed",
                "/open",
                type(exc).__name__,
            )
        if isinstance(exc, Exception):
            _fail(
                "durable_replay_ledger_internal_error",
                "/open",
                type(exc).__name__,
            )
        raise


def reserve_durable_replay_challenge_v1(
    ledger: DurableReplayLedgerV1,
    *,
    challenge: object,
    release_binding: object,
    release_identity: object,
) -> DurableReplayReservationReceiptV1:
    """Atomically reserve one challenge and its full release identity."""

    checked_ledger = _require_ledger(ledger)
    challenge_payload, challenge_blob = _canonical_input_object(
        challenge,
        path="/challenge",
        max_bytes=_MAX_CHALLENGE_BYTES,
    )
    binding_payload, binding_blob = _canonical_input_object(
        release_binding,
        path="/release_binding",
        max_bytes=_MAX_RELEASE_BINDING_BYTES,
    )
    identity_payload, identity_blob = _canonical_input_object(
        release_identity,
        path="/release_identity",
        max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
    )
    fields = _validate_reservation_inputs(
        challenge_payload,
        binding_payload,
        identity_payload,
    )
    connection = _connect(checked_ledger)
    commit_started = False
    try:
        _begin_immediate(connection)
        header, counts, _, _ = _fresh_audit_database_state(
            connection,
            quick_check=True,
        )
        _require_header_matches_ledger(header, checked_ledger)
        if counts["challenge_count"] >= _MAX_CHALLENGES:
            _fail("durable_replay_ledger_challenge_capacity_exceeded", "/challenge")
        if counts["event_count"] >= _MAX_EVENTS:
            _fail("durable_replay_ledger_event_capacity_exceeded", "/events")
        if (
            connection.execute(
                "SELECT 1 FROM challenges WHERE challenge_id = ?",
                (fields["challenge_id"],),
            ).fetchone()
            is not None
        ):
            _fail("durable_replay_challenge_id_reused", "/challenge/challenge_id")
        if (
            connection.execute(
                "SELECT 1 FROM challenges WHERE request_id = ?",
                (fields["request_id"],),
            ).fetchone()
            is not None
        ):
            _fail("durable_replay_request_id_reused", "/challenge/request_id")
        if (
            connection.execute(
                "SELECT 1 FROM challenges WHERE runner_id = ? AND run_sequence = ?",
                (fields["runner_id"], fields["run_sequence"]),
            ).fetchone()
            is not None
        ):
            _fail(
                "durable_replay_runner_sequence_duplicate",
                "/challenge/run_sequence",
            )
        campaign_row = connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?",
            (fields["campaign_id"],),
        ).fetchone()
        binding_blob_hash = sha256_prefixed(binding_blob)
        identity_blob_hash = sha256_prefixed(identity_blob)
        now = _format_utc(_utc_now())
        if campaign_row is None:
            if counts["campaign_count"] >= _MAX_CAMPAIGNS:
                _fail("durable_replay_ledger_campaign_capacity_exceeded", "/campaign")
            connection.execute(
                """INSERT INTO campaigns(
                    campaign_id, runner_id, release_binding_hash,
                    release_binding_blob_sha256,
                    release_identity_receipt_hash,
                    release_identity_blob_sha256, trust_registry_hash,
                    fixture_registry_hash, architecture_base, suite_id,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fields["campaign_id"],
                    fields["runner_id"],
                    fields["release_binding_hash"],
                    binding_blob_hash,
                    fields["release_identity_receipt_hash"],
                    identity_blob_hash,
                    fields["trust_registry_hash"],
                    fields["fixture_registry_hash"],
                    fields["architecture_base"],
                    fields["suite_id"],
                    now,
                ),
            )
        else:
            expected_campaign = (
                fields["runner_id"],
                fields["release_binding_hash"],
                binding_blob_hash,
                fields["release_identity_receipt_hash"],
                identity_blob_hash,
                fields["trust_registry_hash"],
                fields["fixture_registry_hash"],
                fields["architecture_base"],
                fields["suite_id"],
            )
            actual_campaign = tuple(
                campaign_row[name]
                for name in (
                    "runner_id",
                    "release_binding_hash",
                    "release_binding_blob_sha256",
                    "release_identity_receipt_hash",
                    "release_identity_blob_sha256",
                    "trust_registry_hash",
                    "fixture_registry_hash",
                    "architecture_base",
                    "suite_id",
                )
            )
            if actual_campaign != expected_campaign:
                _fail("durable_replay_campaign_identity_drift", "/campaign")
        maximum_sequence = connection.execute(
            "SELECT MAX(run_sequence) FROM challenges WHERE runner_id = ?",
            (fields["runner_id"],),
        ).fetchone()[0]
        if maximum_sequence is not None and fields["run_sequence"] <= maximum_sequence:
            _fail(
                "durable_replay_runner_sequence_not_increasing",
                "/challenge/run_sequence",
            )
        event_sequence, previous_hash = _next_event(connection)
        event_blob, event_hash = _compile_event(
            event_sequence=event_sequence,
            event_type="challenge_reserved",
            object_id=fields["challenge_id"],
            occurred_at_utc=now,
            details={
                "campaign_id": fields["campaign_id"],
                "request_id": fields["request_id"],
                "runner_id": fields["runner_id"],
                "run_sequence": fields["run_sequence"],
                "key_id": fields["key_id"],
                "key_epoch": fields["key_epoch"],
                "challenge_blob_sha256": sha256_prefixed(challenge_blob),
                "release_binding_hash": fields["release_binding_hash"],
                "release_identity_receipt_hash": fields[
                    "release_identity_receipt_hash"
                ],
            },
            previous_event_hash=previous_hash,
        )
        draft = DurableReplayReservationReceiptV1(
            schema_version=DURABLE_REPLAY_RESERVATION_RECEIPT_SCHEMA_VERSION_V1,
            status="durable_replay_challenge_reserved",
            ledger_id=header["ledger_id"],
            namespace=header["namespace"],
            challenge_id=fields["challenge_id"],
            request_id=fields["request_id"],
            campaign_id=fields["campaign_id"],
            key_id=fields["key_id"],
            key_epoch=fields["key_epoch"],
            runner_id=fields["runner_id"],
            run_sequence=fields["run_sequence"],
            release_binding_hash=fields["release_binding_hash"],
            release_identity_receipt_hash=fields["release_identity_receipt_hash"],
            event_sequence=event_sequence,
            event_hash=event_hash,
            reserved_at_utc=now,
            receipt_hash=_ZERO_HASH,
        )
        receipt = replace(
            draft,
            receipt_hash=canonical_hash(_dataclass_payload(draft, include_hash=False)),
        )
        validate_durable_replay_reservation_receipt_v1(receipt)
        receipt_blob = canonical_json_bytes(
            _dataclass_payload(receipt, include_hash=True)
        )
        connection.execute(
            """INSERT INTO challenges(
                challenge_id, request_id, campaign_id, key_id, key_epoch,
                runner_id, run_sequence, release_binding_hash,
                release_identity_receipt_hash, challenge_blob,
                challenge_blob_sha256, release_binding_blob,
                release_binding_blob_sha256, release_identity_blob,
                release_identity_blob_sha256, reserved_at_utc,
                reservation_receipt_blob, reservation_receipt_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fields["challenge_id"],
                fields["request_id"],
                fields["campaign_id"],
                fields["key_id"],
                fields["key_epoch"],
                fields["runner_id"],
                fields["run_sequence"],
                fields["release_binding_hash"],
                fields["release_identity_receipt_hash"],
                challenge_blob,
                sha256_prefixed(challenge_blob),
                binding_blob,
                binding_blob_hash,
                identity_blob,
                identity_blob_hash,
                now,
                receipt_blob,
                receipt.receipt_hash,
            ),
        )
        _insert_event(
            connection,
            event_sequence=event_sequence,
            event_type="challenge_reserved",
            object_id=fields["challenge_id"],
            event_blob=event_blob,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        final_header, _, _, _ = _fresh_audit_database_state(
            connection,
            quick_check=True,
        )
        _require_header_matches_ledger(final_header, checked_ledger)
        checked_ledger._assert_identity()
        commit_started = True
        _commit_or_raise_ambiguous(connection, path="/reserve")
    except sqlite3.IntegrityError as exc:
        _rollback_quiet(connection)
        _raise_reservation_integrity_error(exc)
    except sqlite3.Error as exc:
        _rollback_quiet(connection)
        _raise_sqlite_error(exc, path="/reserve")
    except DurableReplayLedgerV1Error as exc:
        if exc.code != "durable_replay_ledger_commit_ambiguous":
            _rollback_quiet(connection)
        raise
    except BaseException:
        if not commit_started:
            _rollback_quiet(connection)
        raise
    finally:
        connection.close()
    checked_ledger._assert_identity()
    return receipt


def begin_durable_replay_acceptance_v1(
    ledger: DurableReplayLedgerV1,
    *,
    challenge_id: str,
) -> DurableReplayAcceptanceTransactionV1:
    """Hold a write reservation and return the ledger-stored verifier inputs."""

    checked_ledger = _require_ledger(ledger)
    challenge_key = _require_hash(challenge_id, "/challenge_id")
    connection = _connect(checked_ledger)
    try:
        _begin_immediate(connection)
        header, _, _, _ = _fresh_audit_database_state(
            connection,
            quick_check=True,
        )
        _require_header_matches_ledger(header, checked_ledger)
        row = connection.execute(
            "SELECT * FROM challenges WHERE challenge_id = ?",
            (challenge_key,),
        ).fetchone()
        if row is None:
            _fail("durable_replay_challenge_not_reserved", "/challenge_id")
        accepted = connection.execute(
            "SELECT 1 FROM acceptances WHERE challenge_id = ?",
            (challenge_key,),
        ).fetchone()
        if accepted is not None:
            _fail("durable_replay_challenge_already_accepted", "/challenge_id")
        _audit_challenge_row(row, header=header)
        checked_ledger._assert_identity()
        return DurableReplayAcceptanceTransactionV1(
            ledger=checked_ledger,
            connection=connection,
            row=row,
        )
    except sqlite3.Error as exc:
        _rollback_quiet(connection)
        connection.close()
        _raise_sqlite_error(exc, path="/acceptance")
    except BaseException:
        _rollback_quiet(connection)
        connection.close()
        raise


def load_durable_replay_accepted_evidence_v1(
    ledger: DurableReplayLedgerV1,
    *,
    challenge_id: str,
) -> DurableReplayAcceptedEvidenceV1:
    """Load and revalidate all canonical blobs for one accepted challenge."""

    checked_ledger = _require_ledger(ledger)
    challenge_key = _require_hash(challenge_id, "/challenge_id")
    connection = _connect(checked_ledger)
    result: DurableReplayAcceptedEvidenceV1 | None = None
    try:
        connection.execute("BEGIN")
        header, _, _, _ = _fresh_audit_database_state(
            connection,
            quick_check=True,
        )
        _require_header_matches_ledger(header, checked_ledger)
        row = connection.execute(
            """SELECT c.*, a.*
               FROM challenges AS c
               JOIN acceptances AS a ON a.challenge_id = c.challenge_id
               WHERE c.challenge_id = ?""",
            (challenge_key,),
        ).fetchone()
        if row is None:
            _fail("durable_replay_accepted_evidence_not_found", "/challenge_id")
        _audit_joined_acceptance_row(row, header=header)
        storage_payload = _decode_known_canonical_blob(
            bytes(row["storage_receipt_blob"]),
            path="/accepted/storage_receipt",
            max_bytes=_MAX_RECEIPT_BYTES,
        )
        storage_receipt = _parse_storage_receipt(storage_payload)
        result = DurableReplayAcceptedEvidenceV1(
            ledger_id=header["ledger_id"],
            namespace=header["namespace"],
            challenge_blob=bytes(row["challenge_blob"]),
            release_binding_blob=bytes(row["release_binding_blob"]),
            release_identity_blob=bytes(row["release_identity_blob"]),
            reservation_receipt_blob=bytes(row["reservation_receipt_blob"]),
            envelope_blob=bytes(row["envelope_blob"]),
            signed_receipt_blob=bytes(row["signed_receipt_blob"]),
            storage_receipt=storage_receipt,
        )
    except sqlite3.Error as exc:
        _raise_sqlite_error(exc, path="/accepted")
    finally:
        connection.close()
    checked_ledger._assert_identity()
    assert result is not None
    return validate_durable_replay_accepted_evidence_v1(result)


def audit_durable_replay_ledger_v1(
    ledger: DurableReplayLedgerV1,
) -> DurableReplayAuditReceiptV1:
    """Run quick-check, schema, canonical-row, relational, and chain audits."""

    checked_ledger = _require_ledger(ledger)
    connection = _connect(checked_ledger)
    result: DurableReplayAuditReceiptV1 | None = None
    try:
        connection.execute("BEGIN")
        header, counts, last_sequence, last_hash = _fresh_audit_database_state(
            connection,
            quick_check=True,
        )
        _require_header_matches_ledger(header, checked_ledger)
        audited_at = _format_utc(_utc_now())
        draft = DurableReplayAuditReceiptV1(
            schema_version=DURABLE_REPLAY_AUDIT_RECEIPT_SCHEMA_VERSION_V1,
            status="durable_replay_ledger_audited",
            ledger_id=header["ledger_id"],
            namespace=header["namespace"],
            schema_manifest_hash=header["schema_manifest_hash"],
            campaign_count=counts["campaign_count"],
            challenge_count=counts["challenge_count"],
            acceptance_count=counts["acceptance_count"],
            event_count=counts["event_count"],
            last_event_sequence=last_sequence,
            last_event_hash=last_hash,
            quick_check_ok=True,
            canonical_blobs_verified=True,
            event_chain_verified=True,
            audited_at_utc=audited_at,
            receipt_hash=_ZERO_HASH,
        )
        result = replace(
            draft,
            receipt_hash=canonical_hash(_dataclass_payload(draft, include_hash=False)),
        )
        validate_durable_replay_audit_receipt_v1(result)
        connection.rollback()
    except sqlite3.Error as exc:
        _rollback_quiet(connection)
        _raise_sqlite_error(exc, path="/audit")
    except BaseException:
        _rollback_quiet(connection)
        raise
    finally:
        connection.close()
    checked_ledger._assert_identity()
    assert result is not None
    return result


def validate_durable_replay_reservation_receipt_v1(
    receipt: DurableReplayReservationReceiptV1,
) -> DurableReplayReservationReceiptV1:
    if type(receipt) is not DurableReplayReservationReceiptV1:
        _fail("durable_replay_reservation_receipt_type_invalid", "/receipt")
    payload = _dataclass_payload(receipt, include_hash=True)
    _validate_receipt_schema(payload, path="/receipt")
    _require_receipt_common(
        payload,
        schema_version=DURABLE_REPLAY_RESERVATION_RECEIPT_SCHEMA_VERSION_V1,
        status="durable_replay_challenge_reserved",
    )
    for name in (
        "key_epoch",
        "run_sequence",
        "event_sequence",
    ):
        _require_positive_int(payload[name], f"/receipt/{name}")
    for name in (
        "ledger_id",
        "challenge_id",
        "release_binding_hash",
        "release_identity_receipt_hash",
        "event_hash",
    ):
        _require_hash(payload[name], f"/receipt/{name}")
    for name in ("request_id", "campaign_id", "runner_id"):
        _require_id(payload[name], f"/receipt/{name}")
    _require_namespace(payload["namespace"], "/receipt/namespace")
    _require_bounded_text(payload["key_id"], "/receipt/key_id", minimum=3, maximum=128)
    _require_timestamp(payload["reserved_at_utc"], "/receipt/reserved_at_utc")
    _require_receipt_hash(payload)
    return receipt


def validate_durable_replay_storage_receipt_v1(
    receipt: DurableReplayStorageReceiptV1,
) -> DurableReplayStorageReceiptV1:
    if type(receipt) is not DurableReplayStorageReceiptV1:
        _fail("durable_replay_storage_receipt_type_invalid", "/receipt")
    payload = _dataclass_payload(receipt, include_hash=True)
    _validate_receipt_schema(payload, path="/receipt")
    _require_receipt_common(
        payload,
        schema_version=DURABLE_REPLAY_STORAGE_RECEIPT_SCHEMA_VERSION_V1,
        status="durable_replay_evidence_committed",
    )
    for name in (
        "run_sequence",
        "acceptance_sequence",
        "event_sequence",
    ):
        _require_positive_int(payload[name], f"/receipt/{name}")
    for name in (
        "ledger_id",
        "challenge_id",
        "envelope_hash",
        "signed_payload_sha256",
        "signed_receipt_hash",
        "event_hash",
    ):
        _require_hash(payload[name], f"/receipt/{name}")
    for name in ("campaign_id", "runner_id"):
        _require_id(payload[name], f"/receipt/{name}")
    _require_namespace(payload["namespace"], "/receipt/namespace")
    _require_timestamp(payload["accepted_at_utc"], "/receipt/accepted_at_utc")
    _require_receipt_hash(payload)
    return receipt


def validate_durable_replay_audit_receipt_v1(
    receipt: DurableReplayAuditReceiptV1,
) -> DurableReplayAuditReceiptV1:
    if type(receipt) is not DurableReplayAuditReceiptV1:
        _fail("durable_replay_audit_receipt_type_invalid", "/receipt")
    payload = _dataclass_payload(receipt, include_hash=True)
    _validate_receipt_schema(payload, path="/receipt")
    _require_receipt_common(
        payload,
        schema_version=DURABLE_REPLAY_AUDIT_RECEIPT_SCHEMA_VERSION_V1,
        status="durable_replay_ledger_audited",
    )
    for name, maximum in (
        ("campaign_count", _MAX_CAMPAIGNS),
        ("challenge_count", _MAX_CHALLENGES),
        ("acceptance_count", _MAX_ACCEPTANCES),
        ("event_count", _MAX_EVENTS),
    ):
        value = _require_nonnegative_int(payload[name], f"/receipt/{name}")
        if value > maximum:
            _fail("durable_replay_audit_receipt_count_invalid", f"/receipt/{name}")
    _require_nonnegative_int(
        payload["last_event_sequence"], "/receipt/last_event_sequence"
    )
    for name in ("ledger_id", "schema_manifest_hash", "last_event_hash"):
        _require_hash(payload[name], f"/receipt/{name}")
    _require_namespace(payload["namespace"], "/receipt/namespace")
    for name in ("quick_check_ok", "canonical_blobs_verified", "event_chain_verified"):
        if payload[name] is not True:
            _fail("durable_replay_audit_receipt_claim_invalid", f"/receipt/{name}")
    if (payload["event_count"] == 0) != (payload["last_event_sequence"] == 0):
        _fail("durable_replay_audit_receipt_event_extent_invalid", "/receipt")
    if payload["event_count"] == 0 and payload["last_event_hash"] != _ZERO_HASH:
        _fail("durable_replay_audit_receipt_event_hash_invalid", "/receipt")
    if payload["event_count"] != payload["last_event_sequence"]:
        _fail("durable_replay_audit_receipt_event_sequence_invalid", "/receipt")
    _require_timestamp(payload["audited_at_utc"], "/receipt/audited_at_utc")
    _require_receipt_hash(payload)
    return receipt


def validate_durable_replay_accepted_evidence_v1(
    evidence: DurableReplayAcceptedEvidenceV1,
) -> DurableReplayAcceptedEvidenceV1:
    if type(evidence) is not DurableReplayAcceptedEvidenceV1:
        _fail("durable_replay_accepted_evidence_type_invalid", "/accepted")
    _require_hash(evidence.ledger_id, "/accepted/ledger_id")
    _require_namespace(evidence.namespace, "/accepted/namespace")
    challenge = evidence.challenge_payload
    binding = evidence.release_binding_payload
    identity = evidence.release_identity_payload
    envelope = evidence.envelope_payload
    signed_receipt = evidence.signed_receipt_payload
    fields = _validate_reservation_inputs(challenge, binding, identity)
    envelope_hash, payload_hash = _validate_envelope_payload(envelope)
    signed_hash = _validate_signed_receipt_payload(signed_receipt)
    storage = validate_durable_replay_storage_receipt_v1(evidence.storage_receipt)
    reservation = evidence.reservation_receipt
    if (
        storage.ledger_id != evidence.ledger_id
        or reservation.ledger_id != evidence.ledger_id
        or storage.namespace != evidence.namespace
        or reservation.namespace != evidence.namespace
        or reservation.challenge_id != fields["challenge_id"]
        or reservation.request_id != fields["request_id"]
        or reservation.campaign_id != fields["campaign_id"]
        or reservation.key_id != fields["key_id"]
        or reservation.key_epoch != fields["key_epoch"]
        or reservation.runner_id != fields["runner_id"]
        or reservation.run_sequence != fields["run_sequence"]
        or reservation.release_binding_hash != fields["release_binding_hash"]
        or reservation.release_identity_receipt_hash
        != fields["release_identity_receipt_hash"]
        or storage.challenge_id != fields["challenge_id"]
        or storage.campaign_id != fields["campaign_id"]
        or storage.runner_id != fields["runner_id"]
        or storage.run_sequence != fields["run_sequence"]
        or storage.envelope_hash != envelope_hash
        or storage.signed_payload_sha256 != payload_hash
        or storage.signed_receipt_hash != signed_hash
    ):
        _fail("durable_replay_accepted_evidence_binding_invalid", "/accepted")
    _validate_acceptance_bindings(
        challenge_fields=fields,
        stored_challenge=challenge,
        stored_release_binding=binding,
        envelope=envelope,
        signed_receipt=signed_receipt,
    )
    return evidence


def _commit_acceptance(
    transaction: DurableReplayAcceptanceTransactionV1,
    *,
    envelope_bytes: bytes,
    signed_receipt: object,
    accepted_not_before_utc: str,
) -> DurableReplayStorageReceiptV1:
    connection = transaction._connection
    ledger = transaction._ledger
    ledger._assert_identity()
    accepted_not_before = _timestamp_datetime(
        accepted_not_before_utc,
        "/accepted_not_before_utc",
    )
    if type(envelope_bytes) is not bytes:
        _fail("durable_replay_envelope_bytes_type_invalid", "/envelope")
    envelope = _decode_canonical_json_bytes(
        envelope_bytes,
        path="/envelope",
        max_bytes=_MAX_ENVELOPE_BYTES,
    )
    receipt_payload, receipt_blob = _canonical_input_object(
        signed_receipt,
        path="/signed_receipt",
        max_bytes=_MAX_SIGNED_RECEIPT_BYTES,
    )
    challenge_payload = _decode_known_canonical_blob(
        transaction._challenge_blob,
        path="/challenge",
        max_bytes=_MAX_CHALLENGE_BYTES,
    )
    binding_payload = _decode_known_canonical_blob(
        transaction._release_binding_blob,
        path="/release_binding",
        max_bytes=_MAX_RELEASE_BINDING_BYTES,
    )
    identity_payload = _decode_known_canonical_blob(
        transaction._release_identity_blob,
        path="/release_identity",
        max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
    )
    challenge_fields = _validate_reservation_inputs(
        challenge_payload,
        binding_payload,
        identity_payload,
    )
    envelope_hash, signed_payload_hash = _validate_envelope_payload(envelope)
    signed_receipt_hash = _validate_signed_receipt_payload(receipt_payload)
    _validate_acceptance_bindings(
        challenge_fields=challenge_fields,
        stored_challenge=challenge_payload,
        stored_release_binding=binding_payload,
        envelope=envelope,
        signed_receipt=receipt_payload,
    )
    if (
        connection.execute(
            "SELECT 1 FROM acceptances WHERE challenge_id = ?",
            (challenge_fields["challenge_id"],),
        ).fetchone()
        is not None
    ):
        _fail("durable_replay_challenge_already_accepted", "/challenge_id")
    counts = _bounded_counts(connection)
    if counts["acceptance_count"] >= _MAX_ACCEPTANCES:
        _fail("durable_replay_ledger_acceptance_capacity_exceeded", "/acceptance")
    if counts["event_count"] >= _MAX_EVENTS:
        _fail("durable_replay_ledger_event_capacity_exceeded", "/events")
    acceptance_sequence = counts["acceptance_count"] + 1
    event_sequence, previous_hash = _next_event(connection)
    accepted_at = _format_utc(_utc_now())
    issued_at = _timestamp_datetime(
        challenge_payload["issued_at_utc"],
        "/challenge/issued_at_utc",
    )
    expires_at = _timestamp_datetime(
        challenge_payload["expires_at_utc"],
        "/challenge/expires_at_utc",
    )
    accepted_datetime = _timestamp_datetime(accepted_at, "/accepted_at_utc")
    if not issued_at <= accepted_datetime <= expires_at:
        _fail(
            "durable_replay_challenge_expired_at_acceptance",
            "/challenge/expires_at_utc",
        )
    if accepted_datetime < accepted_not_before:
        _fail(
            "durable_replay_acceptance_not_before_not_reached",
            "/accepted_not_before_utc",
        )
    event_blob, event_hash = _compile_event(
        event_sequence=event_sequence,
        event_type="evidence_accepted",
        object_id=challenge_fields["challenge_id"],
        occurred_at_utc=accepted_at,
        details={
            "acceptance_sequence": acceptance_sequence,
            "campaign_id": challenge_fields["campaign_id"],
            "runner_id": challenge_fields["runner_id"],
            "run_sequence": challenge_fields["run_sequence"],
            "envelope_hash": envelope_hash,
            "signed_payload_sha256": signed_payload_hash,
            "signed_receipt_hash": signed_receipt_hash,
        },
        previous_event_hash=previous_hash,
    )
    header = _load_header(connection)
    _require_header_matches_ledger(header, ledger)
    draft = DurableReplayStorageReceiptV1(
        schema_version=DURABLE_REPLAY_STORAGE_RECEIPT_SCHEMA_VERSION_V1,
        status="durable_replay_evidence_committed",
        ledger_id=header["ledger_id"],
        namespace=header["namespace"],
        challenge_id=challenge_fields["challenge_id"],
        campaign_id=challenge_fields["campaign_id"],
        runner_id=challenge_fields["runner_id"],
        run_sequence=challenge_fields["run_sequence"],
        acceptance_sequence=acceptance_sequence,
        envelope_hash=envelope_hash,
        signed_payload_sha256=signed_payload_hash,
        signed_receipt_hash=signed_receipt_hash,
        event_sequence=event_sequence,
        event_hash=event_hash,
        accepted_at_utc=accepted_at,
        receipt_hash=_ZERO_HASH,
    )
    result = replace(
        draft,
        receipt_hash=canonical_hash(_dataclass_payload(draft, include_hash=False)),
    )
    validate_durable_replay_storage_receipt_v1(result)
    storage_blob = canonical_json_bytes(_dataclass_payload(result, include_hash=True))
    try:
        connection.execute(
            """INSERT INTO acceptances(
                challenge_id, acceptance_sequence, envelope_blob,
                envelope_blob_sha256, envelope_hash, signed_payload_sha256,
                signed_receipt_blob, signed_receipt_blob_sha256,
                signed_receipt_hash, accepted_at_utc, event_sequence,
                event_hash, storage_receipt_blob, storage_receipt_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                challenge_fields["challenge_id"],
                acceptance_sequence,
                envelope_bytes,
                sha256_prefixed(envelope_bytes),
                envelope_hash,
                signed_payload_hash,
                receipt_blob,
                sha256_prefixed(receipt_blob),
                signed_receipt_hash,
                accepted_at,
                event_sequence,
                event_hash,
                storage_blob,
                result.receipt_hash,
            ),
        )
        _insert_event(
            connection,
            event_sequence=event_sequence,
            event_type="evidence_accepted",
            object_id=challenge_fields["challenge_id"],
            event_blob=event_blob,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        final_header, _, _, _ = _fresh_audit_database_state(
            connection,
            quick_check=True,
        )
        _require_header_matches_ledger(final_header, ledger)
    except sqlite3.IntegrityError as exc:
        _raise_acceptance_integrity_error(exc)
    except sqlite3.Error as exc:
        _raise_sqlite_error(exc, path="/acceptance/commit")
    return result


def _validate_reservation_inputs(
    challenge: dict[str, Any],
    release_binding: dict[str, Any],
    release_identity: dict[str, Any],
) -> dict[str, Any]:
    challenge_id = _require_hash(
        _field(challenge, "challenge_id", "/challenge"),
        "/challenge/challenge_id",
    )
    challenge_without_id = {
        key: value for key, value in challenge.items() if key != "challenge_id"
    }
    if challenge_id != canonical_hash(challenge_without_id):
        _fail("durable_replay_challenge_hash_invalid", "/challenge/challenge_id")
    request_id = _require_id(
        _field(challenge, "request_id", "/challenge"),
        "/challenge/request_id",
    )
    campaign_id = _require_id(
        _field(challenge, "campaign_id", "/challenge"),
        "/challenge/campaign_id",
    )
    key_id = _require_bounded_text(
        _field(challenge, "expected_key_id", "/challenge"),
        "/challenge/expected_key_id",
        minimum=3,
        maximum=128,
    )
    key_epoch = _require_positive_int(
        _field(challenge, "expected_key_epoch", "/challenge"),
        "/challenge/expected_key_epoch",
    )
    runner_id = _require_id(
        _field(challenge, "expected_runner_id", "/challenge"),
        "/challenge/expected_runner_id",
    )
    run_sequence = _require_positive_int(
        _field(challenge, "expected_run_sequence", "/challenge"),
        "/challenge/expected_run_sequence",
    )
    release_binding_hash = _require_hash(
        _field(release_binding, "binding_hash", "/release_binding"),
        "/release_binding/binding_hash",
    )
    if release_binding_hash != canonical_hash(
        {key: value for key, value in release_binding.items() if key != "binding_hash"}
    ):
        _fail(
            "durable_replay_release_binding_hash_invalid",
            "/release_binding/binding_hash",
        )
    expected_binding = _require_hash(
        _field(challenge, "expected_release_binding_hash", "/challenge"),
        "/challenge/expected_release_binding_hash",
    )
    if expected_binding != release_binding_hash:
        _fail("durable_replay_release_binding_mismatch", "/challenge")
    release_identity_receipt_hash = _require_hash(
        _field(release_identity, "receipt_hash", "/release_identity"),
        "/release_identity/receipt_hash",
    )
    if release_identity_receipt_hash != canonical_hash(
        {key: value for key, value in release_identity.items() if key != "receipt_hash"}
    ):
        _fail(
            "durable_replay_release_identity_hash_invalid",
            "/release_identity/receipt_hash",
        )
    identity_binding = _require_hash(
        _field(release_identity, "release_binding_hash", "/release_identity"),
        "/release_identity/release_binding_hash",
    )
    if identity_binding != release_binding_hash:
        _fail("durable_replay_release_identity_binding_mismatch", "/release_identity")
    trust_registry_hash = _require_hash(
        _field(challenge, "expected_trust_registry_hash", "/challenge"),
        "/challenge/expected_trust_registry_hash",
    )
    fixture_registry_hash = _require_hash(
        _field(release_binding, "fixture_registry_hash", "/release_binding"),
        "/release_binding/fixture_registry_hash",
    )
    architecture_base = _require_bounded_text(
        _field(challenge, "expected_architecture_base", "/challenge"),
        "/challenge/expected_architecture_base",
        minimum=3,
        maximum=64,
    )
    suite_id = _require_id(
        _field(challenge, "expected_suite_id", "/challenge"),
        "/challenge/expected_suite_id",
    )
    issued_at_utc = _require_timestamp(
        _field(challenge, "issued_at_utc", "/challenge"),
        "/challenge/issued_at_utc",
    )
    expires_at_utc = _require_timestamp(
        _field(challenge, "expires_at_utc", "/challenge"),
        "/challenge/expires_at_utc",
    )
    if _timestamp_datetime(
        issued_at_utc,
        "/challenge/issued_at_utc",
    ) >= _timestamp_datetime(
        expires_at_utc,
        "/challenge/expires_at_utc",
    ):
        _fail(
            "durable_replay_challenge_time_window_invalid",
            "/challenge/expires_at_utc",
        )
    return {
        "challenge_id": challenge_id,
        "request_id": request_id,
        "campaign_id": campaign_id,
        "key_id": key_id,
        "key_epoch": key_epoch,
        "runner_id": runner_id,
        "run_sequence": run_sequence,
        "release_binding_hash": release_binding_hash,
        "release_identity_receipt_hash": release_identity_receipt_hash,
        "trust_registry_hash": trust_registry_hash,
        "fixture_registry_hash": fixture_registry_hash,
        "architecture_base": architecture_base,
        "suite_id": suite_id,
    }


def _validate_envelope_payload(payload: dict[str, Any]) -> tuple[str, str]:
    envelope_hash = _require_hash(
        _field(payload, "envelope_hash", "/envelope"),
        "/envelope/envelope_hash",
    )
    signed_payload = _field(payload, "signed_payload", "/envelope")
    if type(signed_payload) is not dict:
        _fail("durable_replay_signed_payload_type_invalid", "/envelope/signed_payload")
    signed_payload_hash = _require_hash(
        _field(payload, "signed_payload_sha256", "/envelope"),
        "/envelope/signed_payload_sha256",
    )
    if signed_payload_hash != sha256_prefixed(canonical_json_bytes(signed_payload)):
        _fail(
            "durable_replay_signed_payload_hash_invalid",
            "/envelope/signed_payload_sha256",
        )
    if envelope_hash != canonical_hash(
        {key: value for key, value in payload.items() if key != "envelope_hash"}
    ):
        _fail("durable_replay_envelope_hash_invalid", "/envelope/envelope_hash")
    return envelope_hash, signed_payload_hash


def _validate_signed_receipt_payload(payload: dict[str, Any]) -> str:
    receipt_hash = _require_hash(
        _field(payload, "receipt_hash", "/signed_receipt"),
        "/signed_receipt/receipt_hash",
    )
    if receipt_hash != canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    ):
        _fail(
            "durable_replay_signed_receipt_hash_invalid",
            "/signed_receipt/receipt_hash",
        )
    return receipt_hash


def _validate_acceptance_bindings(
    *,
    challenge_fields: dict[str, Any],
    stored_challenge: dict[str, Any],
    stored_release_binding: dict[str, Any],
    envelope: dict[str, Any],
    signed_receipt: dict[str, Any],
) -> None:
    signed_payload = envelope["signed_payload"]
    envelope_challenge = _field(signed_payload, "challenge", "/envelope/signed_payload")
    if type(envelope_challenge) is not dict:
        _fail(
            "durable_replay_envelope_challenge_type_invalid",
            "/envelope/signed_payload/challenge",
        )
    envelope_release = _field(
        signed_payload,
        "release_binding",
        "/envelope/signed_payload",
    )
    if type(envelope_release) is not dict:
        _fail(
            "durable_replay_envelope_release_type_invalid",
            "/envelope/signed_payload/release_binding",
        )
    if canonical_json_bytes(envelope_challenge) != canonical_json_bytes(
        stored_challenge
    ):
        _fail(
            "durable_replay_envelope_stored_challenge_mismatch",
            "/envelope/signed_payload/challenge",
        )
    if canonical_json_bytes(envelope_release) != canonical_json_bytes(
        stored_release_binding
    ):
        _fail(
            "durable_replay_envelope_stored_release_mismatch",
            "/envelope/signed_payload/release_binding",
        )
    bindings = {
        "challenge_id": challenge_fields["challenge_id"],
        "release_binding_hash": challenge_fields["release_binding_hash"],
        "key_id": challenge_fields["key_id"],
        "key_epoch": challenge_fields["key_epoch"],
        "runner_id": challenge_fields["runner_id"],
        "run_sequence": challenge_fields["run_sequence"],
    }
    envelope_key_id = _require_bounded_text(
        _field(envelope, "key_id", "/envelope"),
        "/envelope/key_id",
        minimum=3,
        maximum=128,
    )
    runner = _field(signed_payload, "runner", "/envelope/signed_payload")
    if type(runner) is not dict:
        _fail(
            "durable_replay_envelope_runner_type_invalid",
            "/envelope/signed_payload/runner",
        )
    actual = {
        "challenge_id": _require_hash(
            _field(
                envelope_challenge, "challenge_id", "/envelope/signed_payload/challenge"
            ),
            "/envelope/signed_payload/challenge/challenge_id",
        ),
        "release_binding_hash": _require_hash(
            _field(
                envelope_release,
                "binding_hash",
                "/envelope/signed_payload/release_binding",
            ),
            "/envelope/signed_payload/release_binding/binding_hash",
        ),
        "key_id": envelope_key_id,
        "key_epoch": _require_positive_int(
            _field(
                envelope_challenge,
                "expected_key_epoch",
                "/envelope/signed_payload/challenge",
            ),
            "/envelope/signed_payload/challenge/expected_key_epoch",
        ),
        "runner_id": _require_id(
            _field(runner, "runner_id", "/envelope/signed_payload/runner"),
            "/envelope/signed_payload/runner/runner_id",
        ),
        "run_sequence": _require_positive_int(
            _field(runner, "run_sequence", "/envelope/signed_payload/runner"),
            "/envelope/signed_payload/runner/run_sequence",
        ),
    }
    if actual != bindings:
        _fail("durable_replay_envelope_reservation_binding_invalid", "/envelope")
    receipt_actual = {
        "challenge_id": _require_hash(
            _field(signed_receipt, "challenge_id", "/signed_receipt"),
            "/signed_receipt/challenge_id",
        ),
        "release_binding_hash": _require_hash(
            _field(signed_receipt, "release_binding_hash", "/signed_receipt"),
            "/signed_receipt/release_binding_hash",
        ),
        "key_id": _require_bounded_text(
            _field(signed_receipt, "key_id", "/signed_receipt"),
            "/signed_receipt/key_id",
            minimum=3,
            maximum=128,
        ),
        "key_epoch": _require_positive_int(
            _field(signed_receipt, "key_epoch", "/signed_receipt"),
            "/signed_receipt/key_epoch",
        ),
        "runner_id": _require_id(
            _field(signed_receipt, "runner_id", "/signed_receipt"),
            "/signed_receipt/runner_id",
        ),
        "run_sequence": _require_positive_int(
            _field(signed_receipt, "run_sequence", "/signed_receipt"),
            "/signed_receipt/run_sequence",
        ),
    }
    if receipt_actual != bindings:
        _fail(
            "durable_replay_signed_receipt_reservation_binding_invalid",
            "/signed_receipt",
        )
    envelope_hash, payload_hash = _validate_envelope_payload(envelope)
    if (
        _field(signed_receipt, "envelope_hash", "/signed_receipt") != envelope_hash
        or _field(signed_receipt, "signed_payload_sha256", "/signed_receipt")
        != payload_hash
    ):
        _fail(
            "durable_replay_signed_receipt_envelope_binding_invalid", "/signed_receipt"
        )


def _compile_event(
    *,
    event_sequence: int,
    event_type: str,
    object_id: str,
    occurred_at_utc: str,
    details: dict[str, Any],
    previous_event_hash: str,
) -> tuple[bytes, str]:
    payload_without_hash = {
        "schema_version": "structural-analysis-durable-replay-event.v1",
        "event_sequence": event_sequence,
        "event_type": event_type,
        "object_id": object_id,
        "occurred_at_utc": occurred_at_utc,
        "details": details,
        "previous_event_hash": previous_event_hash,
    }
    payload = {
        **payload_without_hash,
        "event_hash": canonical_hash(payload_without_hash),
    }
    blob = canonical_json_bytes(payload)
    if len(blob) > _MAX_EVENT_BYTES:
        _fail("durable_replay_event_extent_invalid", "/events")
    return blob, payload["event_hash"]


def _insert_event(
    connection: sqlite3.Connection,
    *,
    event_sequence: int,
    event_type: str,
    object_id: str,
    event_blob: bytes,
    previous_hash: str,
    event_hash: str,
) -> None:
    connection.execute(
        """INSERT INTO events(
            event_sequence, event_type, object_id, event_blob,
            event_blob_sha256, previous_event_hash, event_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            event_sequence,
            event_type,
            object_id,
            event_blob,
            sha256_prefixed(event_blob),
            previous_hash,
            event_hash,
        ),
    )


def _next_event(connection: sqlite3.Connection) -> tuple[int, str]:
    row = connection.execute(
        "SELECT event_sequence, event_hash FROM events ORDER BY event_sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return 1, _ZERO_HASH
    sequence = _require_positive_int(row["event_sequence"], "/events/event_sequence")
    if sequence >= _MAX_EVENTS:
        _fail("durable_replay_ledger_event_capacity_exceeded", "/events")
    return sequence + 1, _require_hash(row["event_hash"], "/events/event_hash")


def _audit_campaigns(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT * FROM campaigns ORDER BY campaign_id")
    for index, row in enumerate(rows):
        path = f"/campaigns/{index}"
        _require_id(row["campaign_id"], f"{path}/campaign_id")
        _require_id(row["runner_id"], f"{path}/runner_id")
        for name in (
            "release_binding_hash",
            "release_binding_blob_sha256",
            "release_identity_receipt_hash",
            "release_identity_blob_sha256",
            "trust_registry_hash",
            "fixture_registry_hash",
        ):
            _require_hash(row[name], f"{path}/{name}")
        _require_bounded_text(
            row["architecture_base"], f"{path}/architecture_base", minimum=3, maximum=64
        )
        _require_id(row["suite_id"], f"{path}/suite_id")
        _require_timestamp(row["created_at_utc"], f"{path}/created_at_utc")
        challenge_count = connection.execute(
            "SELECT COUNT(*) FROM challenges WHERE campaign_id = ?",
            (row["campaign_id"],),
        ).fetchone()[0]
        if type(challenge_count) is not int or challenge_count <= 0:
            _fail("durable_replay_campaign_orphaned", path)
        challenge_row = connection.execute(
            """SELECT challenge_blob, release_binding_blob,
                      release_identity_blob
               FROM challenges
               WHERE campaign_id = ?
               ORDER BY run_sequence
               LIMIT 1""",
            (row["campaign_id"],),
        ).fetchone()
        if challenge_row is None:
            _fail("durable_replay_campaign_orphaned", path)
        challenge = _decode_known_canonical_blob(
            bytes(challenge_row["challenge_blob"]),
            path=f"{path}/challenge_blob",
            max_bytes=_MAX_CHALLENGE_BYTES,
        )
        binding = _decode_known_canonical_blob(
            bytes(challenge_row["release_binding_blob"]),
            path=f"{path}/release_binding_blob",
            max_bytes=_MAX_RELEASE_BINDING_BYTES,
        )
        identity = _decode_known_canonical_blob(
            bytes(challenge_row["release_identity_blob"]),
            path=f"{path}/release_identity_blob",
            max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
        )
        fields = _validate_reservation_inputs(challenge, binding, identity)
        campaign_values = (
            row["campaign_id"],
            row["runner_id"],
            row["release_binding_hash"],
            row["release_binding_blob_sha256"],
            row["release_identity_receipt_hash"],
            row["release_identity_blob_sha256"],
            row["trust_registry_hash"],
            row["fixture_registry_hash"],
            row["architecture_base"],
            row["suite_id"],
        )
        expected_values = (
            fields["campaign_id"],
            fields["runner_id"],
            fields["release_binding_hash"],
            sha256_prefixed(canonical_json_bytes(binding)),
            fields["release_identity_receipt_hash"],
            sha256_prefixed(canonical_json_bytes(identity)),
            fields["trust_registry_hash"],
            fields["fixture_registry_hash"],
            fields["architecture_base"],
            fields["suite_id"],
        )
        if campaign_values != expected_values:
            _fail("durable_replay_campaign_identity_drift", path)


def _audit_challenges(
    connection: sqlite3.Connection,
    *,
    header: dict[str, Any],
) -> None:
    rows = connection.execute(
        "SELECT * FROM challenges ORDER BY runner_id, run_sequence"
    )
    previous_runner: str | None = None
    previous_sequence: int | None = None
    for index, row in enumerate(rows):
        _audit_challenge_row(row, path=f"/challenges/{index}", header=header)
        runner_id = str(row["runner_id"])
        sequence = _require_positive_int(
            row["run_sequence"], f"/challenges/{index}/run_sequence"
        )
        if (
            previous_runner == runner_id
            and previous_sequence is not None
            and sequence <= previous_sequence
        ):
            _fail(
                "durable_replay_runner_sequence_not_increasing", f"/challenges/{index}"
            )
        previous_runner = runner_id
        previous_sequence = sequence
        campaign = connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?",
            (row["campaign_id"],),
        ).fetchone()
        if campaign is None:
            _fail("durable_replay_challenge_campaign_missing", f"/challenges/{index}")
        challenge_payload = _decode_known_canonical_blob(
            bytes(row["challenge_blob"]),
            path=f"/challenges/{index}/challenge_blob",
            max_bytes=_MAX_CHALLENGE_BYTES,
        )
        if (
            campaign["runner_id"] != row["runner_id"]
            or campaign["release_binding_hash"] != row["release_binding_hash"]
            or campaign["release_binding_blob_sha256"]
            != row["release_binding_blob_sha256"]
            or campaign["release_identity_receipt_hash"]
            != row["release_identity_receipt_hash"]
            or campaign["release_identity_blob_sha256"]
            != row["release_identity_blob_sha256"]
            or campaign["trust_registry_hash"]
            != challenge_payload["expected_trust_registry_hash"]
            or campaign["fixture_registry_hash"]
            != _decode_known_canonical_blob(
                bytes(row["release_binding_blob"]),
                path=f"/challenges/{index}/release_binding_blob",
                max_bytes=_MAX_RELEASE_BINDING_BYTES,
            )["fixture_registry_hash"]
            or campaign["architecture_base"]
            != challenge_payload["expected_architecture_base"]
            or campaign["suite_id"] != challenge_payload["expected_suite_id"]
        ):
            _fail("durable_replay_campaign_identity_drift", f"/challenges/{index}")


def _audit_challenge_row(
    row: sqlite3.Row,
    *,
    path: str = "/challenge",
    header: dict[str, Any] | None = None,
) -> None:
    challenge_blob = _require_blob(
        row["challenge_blob"], f"{path}/challenge_blob", _MAX_CHALLENGE_BYTES
    )
    binding_blob = _require_blob(
        row["release_binding_blob"],
        f"{path}/release_binding_blob",
        _MAX_RELEASE_BINDING_BYTES,
    )
    identity_blob = _require_blob(
        row["release_identity_blob"],
        f"{path}/release_identity_blob",
        _MAX_RELEASE_IDENTITY_BYTES,
    )
    reservation_blob = _require_blob(
        row["reservation_receipt_blob"],
        f"{path}/reservation_receipt_blob",
        _MAX_RECEIPT_BYTES,
    )
    for blob, hash_name in (
        (challenge_blob, "challenge_blob_sha256"),
        (binding_blob, "release_binding_blob_sha256"),
        (identity_blob, "release_identity_blob_sha256"),
    ):
        if sha256_prefixed(blob) != row[hash_name]:
            _fail("durable_replay_canonical_blob_hash_invalid", f"{path}/{hash_name}")
    challenge = _decode_known_canonical_blob(
        challenge_blob, path=f"{path}/challenge_blob", max_bytes=_MAX_CHALLENGE_BYTES
    )
    binding = _decode_known_canonical_blob(
        binding_blob,
        path=f"{path}/release_binding_blob",
        max_bytes=_MAX_RELEASE_BINDING_BYTES,
    )
    identity = _decode_known_canonical_blob(
        identity_blob,
        path=f"{path}/release_identity_blob",
        max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
    )
    fields = _validate_reservation_inputs(challenge, binding, identity)
    scalar_names = (
        "challenge_id",
        "request_id",
        "campaign_id",
        "key_id",
        "key_epoch",
        "runner_id",
        "run_sequence",
        "release_binding_hash",
        "release_identity_receipt_hash",
    )
    if any(row[name] != fields[name] for name in scalar_names):
        _fail("durable_replay_challenge_row_binding_invalid", path)
    _require_timestamp(row["reserved_at_utc"], f"{path}/reserved_at_utc")
    reservation = _parse_reservation_receipt(
        _decode_known_canonical_blob(
            reservation_blob,
            path=f"{path}/reservation_receipt_blob",
            max_bytes=_MAX_RECEIPT_BYTES,
        )
    )
    if (
        sha256_prefixed(reservation_blob)
        != sha256_prefixed(canonical_json_bytes(reservation.to_dict()))
        or reservation.receipt_hash != row["reservation_receipt_hash"]
        or reservation.challenge_id != fields["challenge_id"]
        or reservation.request_id != fields["request_id"]
        or reservation.campaign_id != fields["campaign_id"]
        or reservation.key_id != fields["key_id"]
        or reservation.key_epoch != fields["key_epoch"]
        or reservation.runner_id != fields["runner_id"]
        or reservation.run_sequence != fields["run_sequence"]
        or reservation.release_binding_hash != fields["release_binding_hash"]
        or reservation.release_identity_receipt_hash
        != fields["release_identity_receipt_hash"]
        or reservation.reserved_at_utc != row["reserved_at_utc"]
        or (
            header is not None
            and (
                reservation.ledger_id != header["ledger_id"]
                or reservation.namespace != header["namespace"]
            )
        )
    ):
        _fail("durable_replay_reservation_receipt_binding_invalid", path)


def _audit_acceptances(
    connection: sqlite3.Connection,
    *,
    header: dict[str, Any],
) -> None:
    rows = connection.execute(
        """SELECT c.*, a.*
           FROM challenges AS c
           JOIN acceptances AS a ON a.challenge_id = c.challenge_id
           ORDER BY a.acceptance_sequence"""
    )
    for index, row in enumerate(rows):
        if row["acceptance_sequence"] != index + 1:
            _fail(
                "durable_replay_acceptance_sequence_noncontiguous",
                f"/acceptances/{index}/acceptance_sequence",
            )
        _audit_joined_acceptance_row(
            row,
            path=f"/acceptances/{index}",
            header=header,
        )


def _audit_joined_acceptance_row(
    row: sqlite3.Row,
    *,
    path: str = "/accepted",
    header: dict[str, Any] | None = None,
) -> None:
    _audit_challenge_row(row, path=f"{path}/challenge", header=header)
    envelope_blob = _require_blob(
        row["envelope_blob"], f"{path}/envelope_blob", _MAX_ENVELOPE_BYTES
    )
    receipt_blob = _require_blob(
        row["signed_receipt_blob"],
        f"{path}/signed_receipt_blob",
        _MAX_SIGNED_RECEIPT_BYTES,
    )
    storage_blob = _require_blob(
        row["storage_receipt_blob"],
        f"{path}/storage_receipt_blob",
        _MAX_RECEIPT_BYTES,
    )
    if (
        sha256_prefixed(envelope_blob) != row["envelope_blob_sha256"]
        or sha256_prefixed(receipt_blob) != row["signed_receipt_blob_sha256"]
    ):
        _fail("durable_replay_acceptance_blob_hash_invalid", path)
    envelope = _decode_known_canonical_blob(
        envelope_blob, path=f"{path}/envelope_blob", max_bytes=_MAX_ENVELOPE_BYTES
    )
    receipt = _decode_known_canonical_blob(
        receipt_blob,
        path=f"{path}/signed_receipt_blob",
        max_bytes=_MAX_SIGNED_RECEIPT_BYTES,
    )
    challenge = _decode_known_canonical_blob(
        bytes(row["challenge_blob"]),
        path=f"{path}/challenge_blob",
        max_bytes=_MAX_CHALLENGE_BYTES,
    )
    binding = _decode_known_canonical_blob(
        bytes(row["release_binding_blob"]),
        path=f"{path}/release_binding_blob",
        max_bytes=_MAX_RELEASE_BINDING_BYTES,
    )
    identity = _decode_known_canonical_blob(
        bytes(row["release_identity_blob"]),
        path=f"{path}/release_identity_blob",
        max_bytes=_MAX_RELEASE_IDENTITY_BYTES,
    )
    fields = _validate_reservation_inputs(challenge, binding, identity)
    envelope_hash, payload_hash = _validate_envelope_payload(envelope)
    signed_receipt_hash = _validate_signed_receipt_payload(receipt)
    _validate_acceptance_bindings(
        challenge_fields=fields,
        stored_challenge=challenge,
        stored_release_binding=binding,
        envelope=envelope,
        signed_receipt=receipt,
    )
    storage = _parse_storage_receipt(
        _decode_known_canonical_blob(
            storage_blob,
            path=f"{path}/storage_receipt_blob",
            max_bytes=_MAX_RECEIPT_BYTES,
        )
    )
    scalar_checks = (
        (row["envelope_hash"], envelope_hash),
        (row["signed_payload_sha256"], payload_hash),
        (row["signed_receipt_hash"], signed_receipt_hash),
        (row["storage_receipt_hash"], storage.receipt_hash),
        (row["event_sequence"], storage.event_sequence),
        (row["event_hash"], storage.event_hash),
        (row["accepted_at_utc"], storage.accepted_at_utc),
        (row["acceptance_sequence"], storage.acceptance_sequence),
        (fields["challenge_id"], storage.challenge_id),
        (fields["campaign_id"], storage.campaign_id),
        (fields["runner_id"], storage.runner_id),
        (fields["run_sequence"], storage.run_sequence),
        (envelope_hash, storage.envelope_hash),
        (payload_hash, storage.signed_payload_sha256),
        (signed_receipt_hash, storage.signed_receipt_hash),
    )
    accepted_datetime = _timestamp_datetime(
        row["accepted_at_utc"], f"{path}/accepted_at_utc"
    )
    issued_datetime = _timestamp_datetime(
        challenge["issued_at_utc"], f"{path}/challenge/issued_at_utc"
    )
    expires_datetime = _timestamp_datetime(
        challenge["expires_at_utc"], f"{path}/challenge/expires_at_utc"
    )
    if (
        any(actual != expected for actual, expected in scalar_checks)
        or (
            header is not None
            and (
                storage.ledger_id != header["ledger_id"]
                or storage.namespace != header["namespace"]
            )
        )
        or not issued_datetime <= accepted_datetime <= expires_datetime
    ):
        _fail("durable_replay_acceptance_row_binding_invalid", path)


def _audit_events(connection: sqlite3.Connection) -> tuple[int, str]:
    rows = connection.execute("SELECT * FROM events ORDER BY event_sequence")
    previous_hash = _ZERO_HASH
    event_count = 0
    for index, row in enumerate(rows):
        event_count = index + 1
        path = f"/events/{index}"
        expected_sequence = index + 1
        if row["event_sequence"] != expected_sequence:
            _fail(
                "durable_replay_event_sequence_noncontiguous", f"{path}/event_sequence"
            )
        blob = _require_blob(row["event_blob"], f"{path}/event_blob", _MAX_EVENT_BYTES)
        if sha256_prefixed(blob) != row["event_blob_sha256"]:
            _fail("durable_replay_event_blob_hash_invalid", f"{path}/event_blob")
        payload = _decode_known_canonical_blob(
            blob, path=f"{path}/event_blob", max_bytes=_MAX_EVENT_BYTES
        )
        event_hash = _require_hash(
            _field(payload, "event_hash", f"{path}/event_blob"),
            f"{path}/event_hash",
        )
        if event_hash != canonical_hash(
            {key: value for key, value in payload.items() if key != "event_hash"}
        ):
            _fail("durable_replay_event_hash_invalid", f"{path}/event_hash")
        if (
            payload.get("schema_version")
            != "structural-analysis-durable-replay-event.v1"
            or payload.get("event_sequence") != expected_sequence
            or payload.get("event_type") != row["event_type"]
            or payload.get("object_id") != row["object_id"]
            or payload.get("previous_event_hash") != previous_hash
            or row["previous_event_hash"] != previous_hash
            or row["event_hash"] != event_hash
            or type(payload.get("details")) is not dict
        ):
            _fail("durable_replay_event_chain_invalid", path)
        _require_timestamp(payload.get("occurred_at_utc"), f"{path}/occurred_at_utc")
        previous_hash = event_hash
    return event_count, previous_hash


def _audit_event_relations(
    connection: sqlite3.Connection,
    counts: dict[str, int],
    *,
    header: dict[str, Any],
) -> None:
    expected_event_count = counts["challenge_count"] + counts["acceptance_count"]
    if counts["event_count"] != expected_event_count:
        _fail("durable_replay_event_cardinality_invalid", "/events")
    reservation_events = connection.execute(
        "SELECT object_id, event_sequence, event_hash FROM events WHERE event_type = 'challenge_reserved'"
    )
    reservation_event_count = 0
    for row in reservation_events:
        reservation_event_count += 1
        challenge = connection.execute(
            "SELECT reservation_receipt_blob FROM challenges WHERE challenge_id = ?",
            (row["object_id"],),
        ).fetchone()
        if challenge is None:
            _fail("durable_replay_reservation_event_orphan", "/events")
        receipt = _parse_reservation_receipt(
            _decode_known_canonical_blob(
                bytes(challenge["reservation_receipt_blob"]),
                path="/events/reservation_receipt",
                max_bytes=_MAX_RECEIPT_BYTES,
            )
        )
        if (
            receipt.event_sequence != row["event_sequence"]
            or receipt.event_hash != row["event_hash"]
            or receipt.ledger_id != header["ledger_id"]
            or receipt.namespace != header["namespace"]
        ):
            _fail("durable_replay_reservation_event_binding_invalid", "/events")
    if reservation_event_count != counts["challenge_count"]:
        _fail("durable_replay_reservation_event_cardinality_invalid", "/events")
    acceptance_events = connection.execute(
        "SELECT object_id, event_sequence, event_hash FROM events WHERE event_type = 'evidence_accepted'"
    )
    acceptance_event_count = 0
    for row in acceptance_events:
        acceptance_event_count += 1
        acceptance = connection.execute(
            "SELECT event_sequence, event_hash FROM acceptances WHERE challenge_id = ?",
            (row["object_id"],),
        ).fetchone()
        if acceptance is None or (
            acceptance["event_sequence"] != row["event_sequence"]
            or acceptance["event_hash"] != row["event_hash"]
        ):
            _fail("durable_replay_acceptance_event_binding_invalid", "/events")
    if acceptance_event_count != counts["acceptance_count"]:
        _fail("durable_replay_acceptance_event_cardinality_invalid", "/events")


def _fresh_audit_database_state(
    connection: sqlite3.Connection,
    *,
    quick_check: bool,
) -> tuple[dict[str, Any], dict[str, int], int, str]:
    """Audit all durable state in the caller's current SQLite snapshot."""

    _validate_database_contract(connection)
    if quick_check:
        quick_rows = connection.execute("PRAGMA quick_check(1)").fetchall()
        if len(quick_rows) != 1 or quick_rows[0][0] != "ok":
            _fail("durable_replay_ledger_quick_check_failed", "/database")
    header = _load_header(connection)
    counts = _bounded_counts(connection)
    _audit_campaigns(connection)
    _audit_challenges(connection, header=header)
    _audit_acceptances(connection, header=header)
    last_sequence, last_hash = _audit_events(connection)
    _audit_event_relations(connection, counts, header=header)
    return header, counts, last_sequence, last_hash


def _require_header_matches_ledger(
    header: dict[str, Any],
    ledger: DurableReplayLedgerV1,
) -> None:
    if header["ledger_id"] != ledger.ledger_id:
        _fail("durable_replay_ledger_identity_mismatch", "/ledger")
    if header["namespace"] != ledger.namespace:
        _fail("durable_replay_ledger_namespace_mismatch", "/ledger")


def _connect(ledger: DurableReplayLedgerV1) -> sqlite3.Connection:
    ledger._assert_identity()
    connection = _connect_database_path(
        ledger._database_path,
        ledger._busy_timeout_ms,
        initializing=False,
    )
    try:
        ledger._assert_identity()
        return connection
    except BaseException:
        connection.close()
        raise


def _connect_database_path(
    database_path: Path,
    busy_timeout_ms: int,
    *,
    initializing: bool,
) -> sqlite3.Connection:
    uri_path = quote(os.fspath(database_path), safe="/")
    uri = f"file:{uri_path}?mode=rw"
    try:
        connection = sqlite3.connect(
            uri,
            timeout=busy_timeout_ms / 1000.0,
            isolation_level=None,
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA recursive_triggers = ON")
        if initializing:
            connection.execute(f"PRAGMA page_size = {_DATABASE_PAGE_SIZE}")
            mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            if str(mode).lower() != "delete":
                _fail("durable_replay_ledger_journal_mode_invalid", "/database")
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_USER_VERSION}")
        maximum_pages = connection.execute(
            f"PRAGMA max_page_count = {_MAX_DATABASE_PAGES}"
        ).fetchone()[0]
        if maximum_pages != _MAX_DATABASE_PAGES:
            _fail("durable_replay_ledger_database_extent_invalid", "/database")
        connection.execute("PRAGMA synchronous = EXTRA")
        connection.execute("PRAGMA cell_size_check = ON")
        try:
            connection.enable_load_extension(False)
        except (AttributeError, sqlite3.Error):
            pass
        return connection
    except DurableReplayLedgerV1Error:
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass
        raise
    except sqlite3.Error as exc:
        _raise_sqlite_error(exc, path="/database")


def _begin_immediate(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlite3.Error as exc:
        _raise_sqlite_error(exc, path="/transaction")


def _validate_database_contract(connection: sqlite3.Connection) -> None:
    pragma_values = {
        "application_id": connection.execute("PRAGMA application_id").fetchone()[0],
        "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
        "foreign_keys": connection.execute("PRAGMA foreign_keys").fetchone()[0],
        "trusted_schema": connection.execute("PRAGMA trusted_schema").fetchone()[0],
        "recursive_triggers": connection.execute(
            "PRAGMA recursive_triggers"
        ).fetchone()[0],
        "journal_mode": str(
            connection.execute("PRAGMA journal_mode").fetchone()[0]
        ).lower(),
        "synchronous": connection.execute("PRAGMA synchronous").fetchone()[0],
        "page_size": connection.execute("PRAGMA page_size").fetchone()[0],
        "max_page_count": connection.execute("PRAGMA max_page_count").fetchone()[0],
    }
    expected = {
        "application_id": _APPLICATION_ID,
        "user_version": _USER_VERSION,
        "foreign_keys": 1,
        "trusted_schema": 0,
        "recursive_triggers": 1,
        "journal_mode": "delete",
        "synchronous": 3,
        "page_size": _DATABASE_PAGE_SIZE,
        "max_page_count": _MAX_DATABASE_PAGES,
    }
    if pragma_values != expected:
        _fail("durable_replay_ledger_pragma_contract_invalid", "/database")
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    if (
        type(page_count) is not int
        or page_count <= 0
        or page_count > _MAX_DATABASE_PAGES
    ):
        _fail("durable_replay_ledger_database_extent_invalid", "/database")
    actual = _actual_schema_manifest(connection)
    expected_schema = _expected_schema_manifest()
    if actual != expected_schema:
        _fail("durable_replay_ledger_schema_manifest_invalid", "/schema")


def _actual_schema_manifest(connection: sqlite3.Connection) -> list[dict[str, str]]:
    object_count = connection.execute(
        "SELECT COUNT(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    if type(object_count) is not int or object_count != len(_SCHEMA_STATEMENTS):
        _fail("durable_replay_ledger_schema_object_count_invalid", "/schema")
    rows = connection.execute(
        """SELECT type, name, tbl_name, sql
           FROM sqlite_schema
           WHERE name NOT LIKE 'sqlite_%'
           ORDER BY type, name"""
    )
    result: list[dict[str, str]] = []
    for row in rows:
        if type(row["sql"]) is not str:
            _fail("durable_replay_ledger_schema_object_invalid", "/schema")
        result.append(
            {
                "type": str(row["type"]),
                "name": str(row["name"]),
                "table_name": str(row["tbl_name"]),
                "sql": _normalize_sql(row["sql"]),
            }
        )
    return result


def _expected_schema_manifest() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for statement in _TABLE_STATEMENTS:
        match = re.match(r"CREATE TABLE ([a-z_]+)", _normalize_sql(statement))
        assert match is not None
        name = match.group(1)
        rows.append(
            {
                "type": "table",
                "name": name,
                "table_name": name,
                "sql": _normalize_sql(statement),
            }
        )
    for statement in _INDEX_STATEMENTS:
        match = re.match(
            r"CREATE (?:UNIQUE )?INDEX ([a-z_]+) ON ([a-z_]+)",
            _normalize_sql(statement),
        )
        assert match is not None
        rows.append(
            {
                "type": "index",
                "name": match.group(1),
                "table_name": match.group(2),
                "sql": _normalize_sql(statement),
            }
        )
    for statement in _TRIGGER_STATEMENTS + _INSERT_GUARD_TRIGGER_STATEMENTS:
        match = re.match(
            r"CREATE TRIGGER ([a-z_]+) .* ON ([a-z_]+)",
            _normalize_sql(statement),
        )
        assert match is not None
        rows.append(
            {
                "type": "trigger",
                "name": match.group(1),
                "table_name": match.group(2),
                "sql": _normalize_sql(statement),
            }
        )
    return sorted(rows, key=lambda row: (row["type"], row["name"]))


def _normalize_sql(value: str) -> str:
    return " ".join(value.strip().rstrip(";").split())


def _load_header(connection: sqlite3.Connection) -> dict[str, Any]:
    meta_count = connection.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    if type(meta_count) is not int or meta_count != 1:
        _fail("durable_replay_ledger_header_missing", "/meta")
    row = connection.execute(
        "SELECT * FROM meta WHERE meta_key = 'ledger_header'"
    ).fetchone()
    if row is None:
        _fail("durable_replay_ledger_header_missing", "/meta")
    blob = _require_blob(row["value_blob"], "/meta/ledger_header", _MAX_RECEIPT_BYTES)
    if sha256_prefixed(blob) != row["value_sha256"]:
        _fail("durable_replay_ledger_header_blob_hash_invalid", "/meta")
    payload = _decode_known_canonical_blob(
        blob, path="/meta/ledger_header", max_bytes=_MAX_RECEIPT_BYTES
    )
    required = {
        "schema_version",
        "ledger_id",
        "namespace",
        "created_at_utc",
        "application_id",
        "user_version",
        "schema_manifest_hash",
        "header_hash",
    }
    if set(payload) != required:
        _fail("durable_replay_ledger_header_shape_invalid", "/meta")
    if (
        payload["schema_version"] != DURABLE_REPLAY_LEDGER_SCHEMA_VERSION_V1
        or payload["application_id"] != _APPLICATION_ID
        or type(payload["application_id"]) is not int
        or payload["user_version"] != _USER_VERSION
        or type(payload["user_version"]) is not int
        or payload["schema_manifest_hash"]
        != sha256_prefixed(canonical_json_bytes(_expected_schema_manifest()))
        or payload["header_hash"]
        != canonical_hash(
            {key: value for key, value in payload.items() if key != "header_hash"}
        )
    ):
        _fail("durable_replay_ledger_header_invalid", "/meta")
    _require_hash(payload["ledger_id"], "/meta/ledger_id")
    _require_namespace(payload["namespace"], "/meta/namespace")
    _require_hash(payload["schema_manifest_hash"], "/meta/schema_manifest_hash")
    _require_hash(payload["header_hash"], "/meta/header_hash")
    _require_timestamp(payload["created_at_utc"], "/meta/created_at_utc")
    return payload


def _bounded_counts(connection: sqlite3.Connection) -> dict[str, int]:
    result: dict[str, int] = {}
    for table_name, maximum, output_name in (
        ("campaigns", _MAX_CAMPAIGNS, "campaign_count"),
        ("challenges", _MAX_CHALLENGES, "challenge_count"),
        ("acceptances", _MAX_ACCEPTANCES, "acceptance_count"),
        ("events", _MAX_EVENTS, "event_count"),
    ):
        value = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        count = _require_nonnegative_int(value, f"/{table_name}/count")
        if count > maximum:
            _fail("durable_replay_ledger_row_capacity_exceeded", f"/{table_name}")
        result[output_name] = count
    return result


def _canonical_input_object(
    value: object,
    *,
    path: str,
    max_bytes: int,
) -> tuple[dict[str, Any], bytes]:
    if type(value) is dict:
        payload = value
    else:
        to_dict = getattr(value, "to_dict", None)
        if not callable(to_dict):
            _fail("durable_replay_payload_type_invalid", path)
        try:
            payload = to_dict()
        except DurableReplayLedgerV1Error:
            raise
        except Exception as exc:
            _fail("durable_replay_payload_conversion_failed", path, type(exc).__name__)
    if type(payload) is not dict:
        _fail("durable_replay_payload_root_invalid", path)
    _validate_json_extent(payload, path=path)
    try:
        blob = canonical_json_bytes(payload)
    except Exception as exc:
        _fail("durable_replay_payload_not_canonicalizable", path, type(exc).__name__)
    if not blob or len(blob) > max_bytes:
        _fail("durable_replay_payload_extent_invalid", path)
    decoded = _decode_canonical_json_bytes(blob, path=path, max_bytes=max_bytes)
    return decoded, blob


def _decode_canonical_json_bytes(
    raw: bytes,
    *,
    path: str,
    max_bytes: int,
) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > max_bytes:
        _fail("durable_replay_canonical_blob_extent_invalid", path)
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("durable_replay_canonical_blob_bom_forbidden", path)

    class _DuplicateKey(ValueError):
        pass

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKey(key)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(value)

    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
        if type(payload) is not dict:
            _fail("durable_replay_canonical_blob_root_invalid", path)
        _validate_json_extent(payload, path=path)
        canonical = canonical_json_bytes(payload)
    except DurableReplayLedgerV1Error:
        raise
    except _DuplicateKey as exc:
        _fail("durable_replay_canonical_blob_duplicate_key", path, str(exc))
    except RecursionError:
        _fail("durable_replay_json_extent_invalid", path)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        _fail("durable_replay_canonical_blob_json_invalid", path, type(exc).__name__)
    if raw != canonical:
        _fail("durable_replay_canonical_blob_not_canonical", path)
    return payload


def _decode_known_canonical_blob(
    raw: bytes,
    *,
    path: str,
    max_bytes: int,
) -> dict[str, Any]:
    return _decode_canonical_json_bytes(raw, path=path, max_bytes=max_bytes)


def _validate_json_extent(value: Any, *, path: str) -> None:
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    node_count = 0
    while stack:
        item, item_path, depth = stack.pop()
        node_count += 1
        if node_count > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _fail("durable_replay_json_extent_invalid", item_path)
        if item is None or type(item) is bool:
            continue
        if type(item) is int:
            if not -(2**63) <= item <= 2**63 - 1:
                _fail("durable_replay_json_integer_extent_invalid", item_path)
            continue
        if type(item) is float:
            if not math.isfinite(item):
                _fail("durable_replay_json_nonfinite", item_path)
            continue
        if type(item) is str:
            if len(item.encode("utf-8")) > _MAX_JSON_STRING_BYTES:
                _fail("durable_replay_json_string_extent_invalid", item_path)
            continue
        if type(item) is list:
            for index, child in enumerate(item):
                stack.append((child, f"{item_path}/{index}", depth + 1))
            continue
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    _fail("durable_replay_json_key_type_invalid", item_path)
                if len(key.encode("utf-8")) > _MAX_JSON_KEY_BYTES:
                    _fail("durable_replay_json_key_extent_invalid", item_path)
                stack.append((child, f"{item_path}/{key}", depth + 1))
            continue
        _fail("durable_replay_json_value_type_invalid", item_path)


def _coerce_directory_path(value: str | os.PathLike[str]) -> Path:
    if isinstance(value, bytes):
        _fail("durable_replay_ledger_directory_type_invalid", "/ledger_directory")
    try:
        path = Path(value)
    except (TypeError, ValueError) as exc:
        _fail(
            "durable_replay_ledger_directory_type_invalid",
            "/ledger_directory",
            str(exc),
        )
    if not path.is_absolute():
        _fail("durable_replay_ledger_directory_not_absolute", "/ledger_directory")
    if "\x00" in os.fspath(path):
        _fail("durable_replay_ledger_directory_invalid", "/ledger_directory")
    return path


def _validate_owner_private_directory(directory: Path) -> os.stat_result:
    try:
        result = os.lstat(directory)
    except FileNotFoundError:
        _fail("durable_replay_ledger_directory_missing", "/ledger_directory")
    except OSError as exc:
        _fail("durable_replay_ledger_directory_invalid", "/ledger_directory", str(exc))
    if (
        not stat.S_ISDIR(result.st_mode)
        or stat.S_ISLNK(result.st_mode)
        or result.st_uid != os.geteuid()
        or stat.S_IMODE(result.st_mode) != 0o700
    ):
        _fail("durable_replay_ledger_directory_not_owner_private", "/ledger_directory")
    return result


def _open_directory_pin(directory: Path) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(directory, flags)
    except OSError as exc:
        _fail(
            "durable_replay_ledger_directory_open_failed",
            "/ledger_directory",
            str(exc),
        )
    try:
        result = os.fstat(fd)
        if (
            not stat.S_ISDIR(result.st_mode)
            or result.st_uid != os.geteuid()
            or stat.S_IMODE(result.st_mode) != 0o700
        ):
            _fail(
                "durable_replay_ledger_directory_not_owner_private",
                "/ledger_directory",
            )
        return fd
    except BaseException:
        os.close(fd)
        raise


def _validate_database_path(
    database_path: Path,
    *,
    allow_empty: bool = False,
) -> os.stat_result:
    try:
        result = os.lstat(database_path)
    except FileNotFoundError:
        _fail("durable_replay_ledger_database_missing", "/database")
    except OSError as exc:
        _fail("durable_replay_ledger_database_file_invalid", "/database", str(exc))
    if (
        not stat.S_ISREG(result.st_mode)
        or stat.S_ISLNK(result.st_mode)
        or result.st_uid != os.geteuid()
        or result.st_nlink != 1
        or stat.S_IMODE(result.st_mode) != 0o600
        or (result.st_size <= 0 and not allow_empty)
        or result.st_size > _MAX_DATABASE_BYTES
    ):
        _fail("durable_replay_ledger_database_file_invalid", "/database")
    _validate_sidecars(database_path)
    return result


def _validate_sidecars(database_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        path = Path(os.fspath(database_path) + suffix)
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            _fail("durable_replay_ledger_sidecar_invalid", "/database", str(exc))
        _fail("durable_replay_ledger_wal_sidecar_forbidden", "/database")
    journal = Path(os.fspath(database_path) + "-journal")
    try:
        result = os.lstat(journal)
    except FileNotFoundError:
        return
    except OSError as exc:
        _fail("durable_replay_ledger_sidecar_invalid", "/database", str(exc))
    if (
        not stat.S_ISREG(result.st_mode)
        or stat.S_ISLNK(result.st_mode)
        or result.st_uid != os.geteuid()
        or result.st_nlink != 1
        or stat.S_IMODE(result.st_mode) & 0o077
        or result.st_size > _MAX_DATABASE_BYTES
    ):
        _fail("durable_replay_ledger_sidecar_invalid", "/database")


def _open_database_pin(database_path: Path) -> int:
    flags = os.O_RDWR
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(database_path, flags)
    except OSError as exc:
        _fail("durable_replay_ledger_database_open_failed", "/database", str(exc))
    try:
        result = os.fstat(fd)
        if (
            not stat.S_ISREG(result.st_mode)
            or result.st_uid != os.geteuid()
            or result.st_nlink != 1
            or stat.S_IMODE(result.st_mode) != 0o600
            or result.st_size <= 0
            or result.st_size > _MAX_DATABASE_BYTES
        ):
            _fail("durable_replay_ledger_database_file_invalid", "/database")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _unlink_created_database_quiet(
    directory_pin_fd: int,
    database_path: Path,
    created_stat: os.stat_result,
) -> None:
    try:
        current = os.lstat(database_path)
        if (
            current.st_dev != created_stat.st_dev
            or current.st_ino != created_stat.st_ino
        ):
            return
        os.unlink(_DATABASE_FILENAME, dir_fd=directory_pin_fd)
        os.fsync(directory_pin_fd)
    except OSError:
        pass


def _validate_busy_timeout(value: int) -> int:
    if (
        type(value) is not int
        or not _MIN_BUSY_TIMEOUT_MS <= value <= _MAX_BUSY_TIMEOUT_MS
    ):
        _fail("durable_replay_ledger_busy_timeout_invalid", "/busy_timeout_ms")
    return value


def _require_ledger(value: DurableReplayLedgerV1) -> DurableReplayLedgerV1:
    if type(value) is not DurableReplayLedgerV1:
        _fail("durable_replay_ledger_type_invalid", "/ledger")
    value._assert_identity()
    return value


def _parse_reservation_receipt(
    payload: dict[str, Any],
) -> DurableReplayReservationReceiptV1:
    try:
        receipt = DurableReplayReservationReceiptV1(**payload)
    except (TypeError, KeyError) as exc:
        _fail("durable_replay_reservation_receipt_parse_invalid", "/receipt", str(exc))
    return validate_durable_replay_reservation_receipt_v1(receipt)


def _parse_storage_receipt(payload: dict[str, Any]) -> DurableReplayStorageReceiptV1:
    try:
        receipt = DurableReplayStorageReceiptV1(**payload)
    except (TypeError, KeyError) as exc:
        _fail("durable_replay_storage_receipt_parse_invalid", "/receipt", str(exc))
    return validate_durable_replay_storage_receipt_v1(receipt)


def _dataclass_payload(receipt: Any, *, include_hash: bool) -> dict[str, Any]:
    payload = {
        name: getattr(receipt, name)
        for name in receipt.__dataclass_fields__
        if name != "receipt_hash"
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _validate_receipt_schema(payload: dict[str, Any], *, path: str) -> None:
    try:
        raw = (
            resources.files("structural_analysis.schemas")
            .joinpath(_RECEIPT_SCHEMA_RESOURCE)
            .read_bytes()
        )
        schema = json.loads(raw.decode("utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(payload),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        )
    except Exception as exc:
        _fail("durable_replay_receipt_schema_invalid", path, type(exc).__name__)
    if errors:
        error = errors[0]
        location = (
            path.rstrip("/") + "/" + "/".join(str(item) for item in error.absolute_path)
        )
        _fail("durable_replay_receipt_schema_validation_failed", location)


def _require_receipt_common(
    payload: dict[str, Any],
    *,
    schema_version: str,
    status: str,
) -> None:
    if (
        payload.get("schema_version") != schema_version
        or payload.get("status") != status
    ):
        _fail("durable_replay_receipt_semantics_invalid", "/receipt")


def _require_receipt_hash(payload: dict[str, Any]) -> None:
    receipt_hash = _require_hash(payload.get("receipt_hash"), "/receipt/receipt_hash")
    if receipt_hash != canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    ):
        _fail("durable_replay_receipt_hash_invalid", "/receipt/receipt_hash")


def _field(payload: dict[str, Any], name: str, path: str) -> Any:
    if name not in payload:
        _fail("durable_replay_required_field_missing", f"{path}/{name}")
    return payload[name]


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        _fail("durable_replay_hash_invalid", path)
    return value


def _require_id(value: Any, path: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        _fail("durable_replay_id_invalid", path)
    return value


def _require_namespace(value: Any, path: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        _fail("durable_replay_namespace_invalid", path)
    return value


def _require_bounded_text(
    value: Any,
    path: str,
    *,
    minimum: int,
    maximum: int,
) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        _fail("durable_replay_text_invalid", path)
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        _fail("durable_replay_text_invalid", path)
    return value


def _require_positive_int(value: Any, path: str) -> int:
    if type(value) is not int or value <= 0 or value > 2**63 - 1:
        _fail("durable_replay_positive_integer_invalid", path)
    return value


def _require_nonnegative_int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > 2**63 - 1:
        _fail("durable_replay_nonnegative_integer_invalid", path)
    return value


def _require_timestamp(value: Any, path: str) -> str:
    if type(value) is not str or _TIMESTAMP_RE.fullmatch(value) is None:
        _fail("durable_replay_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        _fail("durable_replay_timestamp_invalid", path, str(exc))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail("durable_replay_timestamp_invalid", path)
    return value


def _timestamp_datetime(value: Any, path: str) -> datetime:
    checked = _require_timestamp(value, path)
    try:
        return datetime.fromisoformat(checked[:-1] + "+00:00")
    except ValueError as exc:  # pragma: no cover - guarded by _require_timestamp
        _fail("durable_replay_timestamp_invalid", path, str(exc))


def _require_blob(value: Any, path: str, maximum: int) -> bytes:
    if type(value) is not bytes or not value or len(value) > maximum:
        _fail("durable_replay_blob_extent_invalid", path)
    return value


def _new_ledger_id() -> str:
    return sha256_prefixed(
        b"structural-analysis-durable-replay-ledger-v1\0" + secrets.token_bytes(32)
    )


def _format_utc(value: datetime) -> str:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail("durable_replay_timestamp_invalid", "/time")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _rollback_quiet(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.Error:
        pass


def _commit_or_raise_ambiguous(
    connection: sqlite3.Connection,
    *,
    path: str,
) -> None:
    try:
        connection.commit()
    except Exception as exc:
        _fail(
            "durable_replay_ledger_commit_ambiguous",
            path,
            type(exc).__name__,
        )


def _raise_reservation_integrity_error(exc: sqlite3.IntegrityError) -> NoReturn:
    message = str(exc).lower()
    if "challenges.challenge_id" in message:
        code = "durable_replay_challenge_id_reused"
        path = "/challenge/challenge_id"
    elif "challenges.request_id" in message:
        code = "durable_replay_request_id_reused"
        path = "/challenge/request_id"
    elif "challenges.runner_id, challenges.run_sequence" in message:
        code = "durable_replay_runner_sequence_duplicate"
        path = "/challenge/run_sequence"
    else:
        code = "durable_replay_reservation_conflict"
        path = "/challenge"
    _fail(code, path)


def _raise_acceptance_integrity_error(exc: sqlite3.IntegrityError) -> NoReturn:
    message = str(exc).lower()
    if "acceptances.challenge_id" in message:
        code = "durable_replay_challenge_already_accepted"
        path = "/challenge_id"
    elif "acceptances.envelope_hash" in message:
        code = "durable_replay_envelope_hash_reused"
        path = "/envelope/envelope_hash"
    elif "acceptances.signed_payload_sha256" in message:
        code = "durable_replay_signed_payload_hash_reused"
        path = "/envelope/signed_payload_sha256"
    elif "acceptances.signed_receipt_hash" in message:
        code = "durable_replay_signed_receipt_hash_reused"
        path = "/signed_receipt/receipt_hash"
    else:
        code = "durable_replay_acceptance_conflict"
        path = "/acceptance"
    _fail(code, path)


def _raise_sqlite_error(exc: sqlite3.Error, *, path: str) -> NoReturn:
    message = str(exc).lower()
    if "locked" in message or "busy" in message:
        code = "durable_replay_ledger_busy"
    elif (
        "malformed" in message
        or "not a database" in message
        or "database disk image" in message
    ):
        code = "durable_replay_ledger_corrupt"
    elif "durable_replay_immutable_table" in message:
        code = "durable_replay_ledger_immutable"
    else:
        code = "durable_replay_ledger_sqlite_error"
    _fail(code, path)


def _bounded_message(value: str) -> str:
    text = "".join(
        character if 0x20 <= ord(character) < 0x7F else "?" for character in str(value)
    )
    return text[:256]


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise DurableReplayLedgerV1Error(code, path, message)


__all__ = [
    "DURABLE_REPLAY_AUDIT_RECEIPT_SCHEMA_VERSION_V1",
    "DURABLE_REPLAY_LEDGER_STABLE_ERROR_CODES_V1",
    "DURABLE_REPLAY_LEDGER_SCHEMA_VERSION_V1",
    "DURABLE_REPLAY_RESERVATION_RECEIPT_SCHEMA_VERSION_V1",
    "DURABLE_REPLAY_STORAGE_RECEIPT_SCHEMA_VERSION_V1",
    "DurableReplayAcceptedEvidenceV1",
    "DurableReplayAcceptanceTransactionV1",
    "DurableReplayAuditReceiptV1",
    "DurableReplayLedgerV1",
    "DurableReplayLedgerV1Error",
    "DurableReplayReservationReceiptV1",
    "DurableReplayStorageReceiptV1",
    "audit_durable_replay_ledger_v1",
    "begin_durable_replay_acceptance_v1",
    "initialize_durable_replay_ledger_v1",
    "load_durable_replay_accepted_evidence_v1",
    "open_durable_replay_ledger_v1",
    "reserve_durable_replay_challenge_v1",
    "validate_durable_replay_accepted_evidence_v1",
    "validate_durable_replay_audit_receipt_v1",
    "validate_durable_replay_reservation_receipt_v1",
    "validate_durable_replay_storage_receipt_v1",
]
