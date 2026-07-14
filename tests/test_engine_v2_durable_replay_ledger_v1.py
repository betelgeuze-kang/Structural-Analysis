from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)
from structural_analysis.engine_v2.evidence import (
    durable_replay_ledger_v1 as ledger_module,
)
from structural_analysis.engine_v2.evidence.durable_replay_ledger_v1 import (
    DURABLE_REPLAY_LEDGER_STABLE_ERROR_CODES_V1,
    DurableReplayLedgerV1Error,
    audit_durable_replay_ledger_v1,
    begin_durable_replay_acceptance_v1,
    initialize_durable_replay_ledger_v1,
    load_durable_replay_accepted_evidence_v1,
    open_durable_replay_ledger_v1,
    reserve_durable_replay_challenge_v1,
    validate_durable_replay_accepted_evidence_v1,
    validate_durable_replay_audit_receipt_v1,
    validate_durable_replay_reservation_receipt_v1,
    validate_durable_replay_storage_receipt_v1,
)


_HASH_A = "sha256:" + "1" * 64
_HASH_B = "sha256:" + "2" * 64
_DATABASE_FILENAME = "durable-replay-ledger-v1.sqlite3"
_NAMESPACE = "test.durable-replay"


def _artifacts(
    *,
    sequence: int = 1,
    request_id: str | None = None,
    campaign_id: str = "campaign.one",
    runner_id: str = "runner.one",
    key_id: str = "ed25519:test-runner:v1",
    key_epoch: int = 1,
    binding_marker: str = "release-a",
    issued_at_utc: str | None = None,
    expires_at_utc: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    issued_at = (
        issued_at_utc
        if issued_at_utc is not None
        else (
            (now - timedelta(hours=1))
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    )
    expires_at = (
        expires_at_utc
        if expires_at_utc is not None
        else (
            (now + timedelta(hours=1))
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    )
    binding: dict[str, Any] = {
        "schema_version": "test-release-binding.v1",
        "artifact_hash": canonical_hash({"marker": binding_marker}),
        "comparison_marker": 1,
        "fixture_registry_hash": _HASH_B,
    }
    binding["binding_hash"] = canonical_hash(binding)
    identity: dict[str, Any] = {
        "schema_version": "test-release-identity.v1",
        "release_binding_hash": binding["binding_hash"],
        "artifact_marker": binding_marker,
        "claims": {"independently_replayed": True, "promotion_eligible": False},
    }
    identity["receipt_hash"] = canonical_hash(identity)
    challenge: dict[str, Any] = {
        "schema_version": "test-challenge.v1",
        "request_id": request_id or f"request.{sequence}",
        "campaign_id": campaign_id,
        "comparison_marker": 1,
        "nonce_base64": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "issued_at_utc": issued_at,
        "expires_at_utc": expires_at,
        "expected_key_id": key_id,
        "expected_key_epoch": key_epoch,
        "expected_runner_id": runner_id,
        "expected_run_sequence": sequence,
        "expected_release_binding_hash": binding["binding_hash"],
        "expected_trust_registry_hash": _HASH_A,
        "expected_architecture_base": "gfx1100",
        "expected_suite_id": "fixed-suite.one",
    }
    challenge["challenge_id"] = canonical_hash(challenge)
    signed_payload = {
        "challenge": challenge,
        "release_binding": binding,
        "runner": {"runner_id": runner_id, "run_sequence": sequence},
        "payload": {"synthetic": True},
    }
    envelope: dict[str, Any] = {
        "schema_version": "test-envelope.v1",
        "key_id": key_id,
        "signed_payload_sha256": sha256_prefixed(canonical_json_bytes(signed_payload)),
        "signed_payload": signed_payload,
        "signature_base64": "synthetic",
    }
    envelope["envelope_hash"] = canonical_hash(envelope)
    signed_receipt: dict[str, Any] = {
        "schema_version": "test-signed-receipt.v1",
        "envelope_hash": envelope["envelope_hash"],
        "signed_payload_sha256": envelope["signed_payload_sha256"],
        "key_id": key_id,
        "key_epoch": key_epoch,
        "runner_id": runner_id,
        "run_sequence": sequence,
        "challenge_id": challenge["challenge_id"],
        "release_binding_hash": binding["binding_hash"],
        "claims": {"verified": True, "promotion_eligible": False},
    }
    signed_receipt["receipt_hash"] = canonical_hash(signed_receipt)
    return challenge, binding, identity, canonical_json_bytes(envelope), signed_receipt


def _mutate_embedded_acceptance_payload(
    artifacts: tuple[Any, ...],
    *,
    section: str,
    updates: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    envelope = json.loads(artifacts[3])
    embedded = dict(envelope["signed_payload"][section])
    embedded.update(updates)
    envelope["signed_payload"][section] = embedded
    envelope["signed_payload_sha256"] = sha256_prefixed(
        canonical_json_bytes(envelope["signed_payload"])
    )
    envelope["envelope_hash"] = canonical_hash(
        {key: value for key, value in envelope.items() if key != "envelope_hash"}
    )
    signed_receipt = dict(artifacts[4])
    signed_receipt["envelope_hash"] = envelope["envelope_hash"]
    signed_receipt["signed_payload_sha256"] = envelope["signed_payload_sha256"]
    signed_receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in signed_receipt.items() if key != "receipt_hash"}
    )
    return canonical_json_bytes(envelope), signed_receipt


def _initialize(tmp_path: Path, **kwargs: Any):
    directory = tmp_path / "ledger"
    directory.mkdir(mode=0o700)
    return initialize_durable_replay_ledger_v1(
        directory,
        namespace=_NAMESPACE,
        **kwargs,
    )


def _reserve(ledger: Any, artifacts: tuple[Any, ...]):
    challenge, binding, identity, _, _ = artifacts
    return reserve_durable_replay_challenge_v1(
        ledger,
        challenge=challenge,
        release_binding=binding,
        release_identity=identity,
    )


def _accept(ledger: Any, artifacts: tuple[Any, ...]):
    challenge, _, _, envelope, signed_receipt = artifacts
    with begin_durable_replay_acceptance_v1(
        ledger, challenge_id=challenge["challenge_id"]
    ) as transaction:
        return transaction.commit(
            envelope_bytes=envelope,
            signed_receipt=signed_receipt,
            accepted_not_before_utc=challenge["issued_at_utc"],
        )


def _reservation_worker(
    directory: str,
    ledger_id: str,
    artifacts: tuple[Any, ...],
    start: Any,
    output: Any,
) -> None:
    start.wait(10)
    try:
        ledger = open_durable_replay_ledger_v1(
            directory,
            expected_ledger_id=ledger_id,
            expected_namespace=_NAMESPACE,
            busy_timeout_ms=2000,
        )
        try:
            _reserve(ledger, artifacts)
            output.put(("ok", ""))
        finally:
            ledger.close()
    except DurableReplayLedgerV1Error as exc:
        output.put(("error", exc.code))


def _acceptance_worker(
    directory: str,
    ledger_id: str,
    artifacts: tuple[Any, ...],
    start: Any,
    output: Any,
) -> None:
    start.wait(10)
    for _ in range(5):
        try:
            ledger = open_durable_replay_ledger_v1(
                directory,
                expected_ledger_id=ledger_id,
                expected_namespace=_NAMESPACE,
                busy_timeout_ms=500,
            )
            try:
                _accept(ledger, artifacts)
                output.put(("ok", ""))
                return
            finally:
                ledger.close()
        except DurableReplayLedgerV1Error as exc:
            if exc.code == "durable_replay_ledger_busy":
                time.sleep(0.05)
                continue
            output.put(("error", exc.code))
            return
    output.put(("error", "durable_replay_ledger_busy"))


def test_initialize_reserve_accept_reopen_load_and_audit(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    reservation = _reserve(ledger, artifacts)
    challenge = artifacts[0]
    with begin_durable_replay_acceptance_v1(
        ledger, challenge_id=challenge["challenge_id"]
    ) as transaction:
        assert transaction.challenge_payload == challenge
        assert transaction.release_binding_payload == artifacts[1]
        assert transaction.release_identity_payload == artifacts[2]
        assert transaction.reservation_receipt == reservation
        storage = transaction.commit(
            envelope_bytes=artifacts[3],
            signed_receipt=artifacts[4],
            accepted_not_before_utc=challenge["issued_at_utc"],
        )
    assert storage.event_sequence == reservation.event_sequence + 1
    assert reservation.namespace == storage.namespace == _NAMESPACE
    validate_durable_replay_reservation_receipt_v1(reservation)
    validate_durable_replay_storage_receipt_v1(storage)
    identity = ledger.ledger_id
    database_path = Path(ledger.database_path)
    ledger.close()

    reopened = open_durable_replay_ledger_v1(
        tmp_path / "ledger",
        expected_ledger_id=identity,
        expected_namespace=_NAMESPACE,
    )
    loaded = load_durable_replay_accepted_evidence_v1(
        reopened, challenge_id=challenge["challenge_id"]
    )
    assert loaded.reservation_receipt == reservation
    assert loaded.storage_receipt == storage
    assert loaded.envelope_bytes == artifacts[3]
    validate_durable_replay_accepted_evidence_v1(loaded)
    audit = audit_durable_replay_ledger_v1(reopened)
    validate_durable_replay_audit_receipt_v1(audit)
    assert (audit.campaign_count, audit.challenge_count, audit.acceptance_count) == (
        1,
        1,
        1,
    )
    assert audit.event_count == 2
    assert audit.last_event_hash == storage.event_hash
    assert stat.S_IMODE((tmp_path / "ledger").stat().st_mode) == 0o700
    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600
    reopened.close()


def test_open_requires_and_pins_expected_ledger_identity(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    identity = ledger.ledger_id
    ledger.close()
    with pytest.raises(DurableReplayLedgerV1Error) as missing:
        open_durable_replay_ledger_v1(tmp_path / "ledger")
    assert missing.value.code == "durable_replay_ledger_expected_id_required"
    with pytest.raises(DurableReplayLedgerV1Error) as missing_namespace:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id=identity,
        )
    assert (
        missing_namespace.value.code
        == "durable_replay_ledger_expected_namespace_required"
    )
    with pytest.raises(DurableReplayLedgerV1Error) as wrong:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id="sha256:" + "f" * 64,
            expected_namespace=_NAMESPACE,
        )
    assert wrong.value.code == "durable_replay_ledger_identity_mismatch"
    with pytest.raises(DurableReplayLedgerV1Error) as wrong_namespace:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id=identity,
            expected_namespace="test.other-domain",
        )
    assert wrong_namespace.value.code == "durable_replay_ledger_namespace_mismatch"
    reopened = open_durable_replay_ledger_v1(
        tmp_path / "ledger",
        expected_ledger_id=identity,
        expected_namespace=_NAMESPACE,
    )
    assert reopened.ledger_id == identity
    assert reopened.namespace == _NAMESPACE
    with pytest.raises(AttributeError):
        reopened.ledger_id = _HASH_A  # type: ignore[misc]
    with pytest.raises(AttributeError):
        reopened.namespace = "test.other-domain"  # type: ignore[misc]
    reopened.close()


def test_initialization_is_explicit_and_mutations_never_recreate_database(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(DurableReplayLedgerV1Error) as initialize_error:
        initialize_durable_replay_ledger_v1(missing, namespace=_NAMESPACE)
    assert initialize_error.value.code == "durable_replay_ledger_directory_missing"
    assert not missing.exists()
    with pytest.raises(DurableReplayLedgerV1Error) as open_error:
        open_durable_replay_ledger_v1(
            missing,
            expected_ledger_id=_HASH_A,
            expected_namespace=_NAMESPACE,
        )
    assert open_error.value.code == "durable_replay_ledger_directory_missing"
    assert not missing.exists()
    ledger = _initialize(tmp_path)
    with pytest.raises(DurableReplayLedgerV1Error) as duplicate_initialize:
        initialize_durable_replay_ledger_v1(
            tmp_path / "ledger",
            namespace=_NAMESPACE,
        )
    assert (
        duplicate_initialize.value.code == "durable_replay_ledger_already_initialized"
    )
    database = Path(ledger.database_path)
    database.unlink()
    with pytest.raises(DurableReplayLedgerV1Error) as reserve_error:
        _reserve(ledger, _artifacts())
    assert reserve_error.value.code == "durable_replay_ledger_database_missing"
    assert not database.exists()
    ledger.close()


def test_initialization_fsyncs_database_and_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "ledger"
    directory.mkdir(mode=0o700)
    observed_modes: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd: int) -> None:
        observed_modes.append(os.fstat(fd).st_mode)
        real_fsync(fd)

    monkeypatch.setattr(ledger_module.os, "fsync", tracking_fsync)
    ledger = initialize_durable_replay_ledger_v1(
        directory,
        namespace=_NAMESPACE,
    )
    assert any(stat.S_ISREG(mode) for mode in observed_modes)
    assert any(stat.S_ISDIR(mode) for mode in observed_modes)
    ledger.close()


def test_campaign_identity_is_pinned_and_runner_sequence_strictly_increases(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    _reserve(ledger, _artifacts(sequence=1))
    with pytest.raises(DurableReplayLedgerV1Error) as drift:
        _reserve(ledger, _artifacts(sequence=2, binding_marker="release-b"))
    assert drift.value.code == "durable_replay_campaign_identity_drift"
    with pytest.raises(DurableReplayLedgerV1Error) as runner_drift:
        _reserve(
            ledger,
            _artifacts(
                sequence=1,
                request_id="request.other-runner",
                runner_id="runner.two",
            ),
        )
    assert runner_drift.value.code == "durable_replay_campaign_identity_drift"
    second = _artifacts(sequence=2)
    _reserve(ledger, second)
    with pytest.raises(DurableReplayLedgerV1Error) as decreasing:
        _reserve(ledger, _artifacts(sequence=1, request_id="request.lower"))
    assert decreasing.value.code in {
        "durable_replay_runner_sequence_duplicate",
        "durable_replay_runner_sequence_not_increasing",
    }
    ledger.close()


def test_ids_and_runner_sequence_are_unique_across_key_epochs(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    first = _artifacts(sequence=1)
    _reserve(ledger, first)
    with pytest.raises(DurableReplayLedgerV1Error) as challenge_reuse:
        _reserve(ledger, first)
    assert challenge_reuse.value.code == "durable_replay_challenge_id_reused"
    with pytest.raises(DurableReplayLedgerV1Error) as request_reuse:
        _reserve(ledger, _artifacts(sequence=2, request_id="request.1"))
    assert request_reuse.value.code == "durable_replay_request_id_reused"
    cross_epoch = _artifacts(
        sequence=1,
        request_id="request.cross-epoch",
        key_id="ed25519:test-runner:v2",
        key_epoch=2,
    )
    with pytest.raises(DurableReplayLedgerV1Error) as sequence_reuse:
        _reserve(ledger, cross_epoch)
    assert sequence_reuse.value.code == "durable_replay_runner_sequence_duplicate"
    ledger.close()


def test_reservation_rejects_non_increasing_challenge_window(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts(
        issued_at_utc="2026-01-01T00:01:00.000000Z",
        expires_at_utc="2026-01-01T00:01:00.000000Z",
    )
    with pytest.raises(DurableReplayLedgerV1Error) as invalid:
        _reserve(ledger, artifacts)
    assert invalid.value.code == "durable_replay_challenge_time_window_invalid"
    assert audit_durable_replay_ledger_v1(ledger).challenge_count == 0
    ledger.close()


def test_acceptance_is_single_use_and_rollback_preserves_pending_challenge(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    challenge_id = artifacts[0]["challenge_id"]
    with begin_durable_replay_acceptance_v1(
        ledger, challenge_id=challenge_id
    ) as transaction:
        assert transaction.challenge_id == challenge_id
    storage = _accept(ledger, artifacts)
    assert storage.challenge_id == challenge_id
    with pytest.raises(DurableReplayLedgerV1Error) as duplicate:
        begin_durable_replay_acceptance_v1(ledger, challenge_id=challenge_id)
    assert duplicate.value.code == "durable_replay_challenge_already_accepted"
    ledger.close()


def test_invalid_acceptance_rolls_back_and_does_not_consume(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    bad_receipt = dict(artifacts[4])
    bad_receipt["run_sequence"] = True
    bad_receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in bad_receipt.items() if key != "receipt_hash"}
    )
    transaction = begin_durable_replay_acceptance_v1(
        ledger, challenge_id=artifacts[0]["challenge_id"]
    )
    with pytest.raises(DurableReplayLedgerV1Error):
        transaction.commit(
            envelope_bytes=artifacts[3],
            signed_receipt=bad_receipt,
            accepted_not_before_utc=artifacts[0]["issued_at_utc"],
        )
    storage = _accept(ledger, artifacts)
    assert storage.acceptance_sequence == 1
    ledger.close()


def test_accepted_evidence_validator_binds_every_reservation_field(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    _accept(ledger, artifacts)
    loaded = load_durable_replay_accepted_evidence_v1(
        ledger,
        challenge_id=artifacts[0]["challenge_id"],
    )
    reservation = loaded.reservation_receipt.to_dict()
    reservation["request_id"] = "request.foreign"
    reservation["receipt_hash"] = canonical_hash(
        {key: value for key, value in reservation.items() if key != "receipt_hash"}
    )
    tampered = ledger_module.DurableReplayAcceptedEvidenceV1(
        ledger_id=loaded.ledger_id,
        namespace=loaded.namespace,
        challenge_blob=canonical_json_bytes(loaded.challenge_payload),
        release_binding_blob=canonical_json_bytes(loaded.release_binding_payload),
        release_identity_blob=canonical_json_bytes(loaded.release_identity_payload),
        reservation_receipt_blob=canonical_json_bytes(reservation),
        envelope_blob=loaded.envelope_bytes,
        signed_receipt_blob=canonical_json_bytes(loaded.signed_receipt_payload),
        storage_receipt=loaded.storage_receipt,
    )
    with pytest.raises(DurableReplayLedgerV1Error) as mismatch:
        validate_durable_replay_accepted_evidence_v1(tampered)
    assert mismatch.value.code == "durable_replay_accepted_evidence_binding_invalid"
    ledger.close()


def test_expired_acceptance_fails_without_consuming_reservation(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts(
        issued_at_utc="2000-01-01T00:00:00.000000Z",
        expires_at_utc="2000-01-01T00:01:00.000000Z",
    )
    _reserve(ledger, artifacts)
    with pytest.raises(DurableReplayLedgerV1Error) as expired:
        _accept(ledger, artifacts)
    assert expired.value.code == "durable_replay_challenge_expired_at_acceptance"
    audit = audit_durable_replay_ledger_v1(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        0,
        1,
    )
    ledger.close()


@pytest.mark.parametrize(
    ("section", "updates", "expected_code"),
    [
        (
            "challenge",
            {"campaign_id": "campaign.embedded-tamper"},
            "durable_replay_envelope_stored_challenge_mismatch",
        ),
        (
            "release_binding",
            {"artifact_hash": "sha256:" + "2" * 64},
            "durable_replay_envelope_stored_release_mismatch",
        ),
    ],
)
def test_acceptance_requires_exact_stored_challenge_and_release_binding(
    tmp_path: Path,
    section: str,
    updates: dict[str, Any],
    expected_code: str,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    envelope, signed_receipt = _mutate_embedded_acceptance_payload(
        artifacts,
        section=section,
        updates=updates,
    )
    transaction = begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=artifacts[0]["challenge_id"],
    )
    with pytest.raises(DurableReplayLedgerV1Error) as mismatch:
        transaction.commit(
            envelope_bytes=envelope,
            signed_receipt=signed_receipt,
            accepted_not_before_utc=artifacts[0]["issued_at_utc"],
        )
    assert mismatch.value.code == expected_code
    pending = audit_durable_replay_ledger_v1(ledger)
    assert (pending.acceptance_count, pending.event_count) == (0, 1)
    assert _accept(ledger, artifacts).acceptance_sequence == 1
    ledger.close()


@pytest.mark.parametrize(
    ("section", "replacement", "expected_code"),
    [
        (
            "challenge",
            True,
            "durable_replay_envelope_stored_challenge_mismatch",
        ),
        (
            "challenge",
            1.0,
            "durable_replay_envelope_stored_challenge_mismatch",
        ),
        (
            "release_binding",
            True,
            "durable_replay_envelope_stored_release_mismatch",
        ),
        (
            "release_binding",
            1.0,
            "durable_replay_envelope_stored_release_mismatch",
        ),
    ],
)
def test_acceptance_rejects_json_numeric_type_confusion(
    tmp_path: Path,
    section: str,
    replacement: bool | float,
    expected_code: str,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    stored = artifacts[0] if section == "challenge" else artifacts[1]
    confused = {**stored, "comparison_marker": replacement}
    assert confused == stored
    assert canonical_json_bytes(confused) != canonical_json_bytes(stored)
    envelope, signed_receipt = _mutate_embedded_acceptance_payload(
        artifacts,
        section=section,
        updates={"comparison_marker": replacement},
    )
    transaction = begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=artifacts[0]["challenge_id"],
    )
    with pytest.raises(DurableReplayLedgerV1Error) as mismatch:
        transaction.commit(
            envelope_bytes=envelope,
            signed_receipt=signed_receipt,
            accepted_not_before_utc=artifacts[0]["issued_at_utc"],
        )
    assert mismatch.value.code == expected_code
    audit = audit_durable_replay_ledger_v1(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        0,
        1,
    )
    ledger.close()


def test_acceptance_rejects_commit_outside_stored_challenge_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    expires_at = datetime.fromisoformat(artifacts[0]["expires_at_utc"][:-1] + "+00:00")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            ledger_module,
            "_utc_now",
            lambda: expires_at + timedelta(microseconds=1),
        )
        transaction = begin_durable_replay_acceptance_v1(
            ledger,
            challenge_id=artifacts[0]["challenge_id"],
        )
        with pytest.raises(DurableReplayLedgerV1Error) as expired:
            transaction.commit(
                envelope_bytes=artifacts[3],
                signed_receipt=artifacts[4],
                accepted_not_before_utc=artifacts[0]["issued_at_utc"],
            )
    assert expired.value.code == "durable_replay_challenge_expired_at_acceptance"
    pending = audit_durable_replay_ledger_v1(ledger)
    assert (pending.acceptance_count, pending.event_count) == (0, 1)
    assert _accept(ledger, artifacts).acceptance_sequence == 1
    ledger.close()


def test_acceptance_not_before_prevents_unrecoverable_early_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    issued_at = datetime.fromisoformat(artifacts[0]["issued_at_utc"][:-1] + "+00:00")
    accepted_not_before = (
        (issued_at + timedelta(seconds=3))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(
            ledger_module,
            "_utc_now",
            lambda: issued_at + timedelta(seconds=1),
        )
        transaction = begin_durable_replay_acceptance_v1(
            ledger,
            challenge_id=artifacts[0]["challenge_id"],
        )
        with pytest.raises(DurableReplayLedgerV1Error) as too_early:
            transaction.commit(
                envelope_bytes=artifacts[3],
                signed_receipt=artifacts[4],
                accepted_not_before_utc=accepted_not_before,
            )
    assert too_early.value.code == "durable_replay_acceptance_not_before_not_reached"
    assert too_early.value.path == "/accepted_not_before_utc"
    pending = audit_durable_replay_ledger_v1(ledger)
    assert (pending.acceptance_count, pending.event_count) == (0, 1)
    assert _accept(ledger, artifacts).acceptance_sequence == 1
    ledger.close()


@pytest.mark.parametrize(
    "invalid_not_before",
    [True, "2026-01-01T00:00:00Z"],
)
def test_acceptance_not_before_requires_strict_canonical_timestamp(
    tmp_path: Path,
    invalid_not_before: Any,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    transaction = begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=artifacts[0]["challenge_id"],
    )
    with pytest.raises(DurableReplayLedgerV1Error) as invalid:
        transaction.commit(
            envelope_bytes=artifacts[3],
            signed_receipt=artifacts[4],
            accepted_not_before_utc=invalid_not_before,
        )
    assert invalid.value.code == "durable_replay_timestamp_invalid"
    assert invalid.value.path == "/accepted_not_before_utc"
    pending = audit_durable_replay_ledger_v1(ledger)
    assert (pending.acceptance_count, pending.event_count) == (0, 1)
    ledger.close()


def test_post_commit_ambiguity_fails_closed_and_can_be_recovered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    reservation = _reserve(ledger, artifacts)

    def commit_then_report_ambiguous(
        connection: sqlite3.Connection,
        *,
        path: str,
    ) -> None:
        connection.commit()
        raise DurableReplayLedgerV1Error(
            "durable_replay_ledger_commit_ambiguous",
            path,
        )

    monkeypatch.setattr(
        ledger_module,
        "_commit_or_raise_ambiguous",
        commit_then_report_ambiguous,
    )
    transaction = begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=artifacts[0]["challenge_id"],
    )
    with pytest.raises(DurableReplayLedgerV1Error) as ambiguous:
        transaction.commit(
            envelope_bytes=artifacts[3],
            signed_receipt=artifacts[4],
            accepted_not_before_utc=artifacts[0]["issued_at_utc"],
        )
    assert ambiguous.value.code == "durable_replay_ledger_commit_ambiguous"
    recovered = load_durable_replay_accepted_evidence_v1(
        ledger,
        challenge_id=artifacts[0]["challenge_id"],
    )
    assert recovered.reservation_receipt == reservation
    assert recovered.storage_receipt.acceptance_sequence == 1
    ledger.close()


def test_commit_exception_maps_to_stable_ambiguous_error() -> None:
    class BrokenCommit:
        def commit(self) -> None:
            raise sqlite3.OperationalError("synthetic post-commit I/O failure")

    with pytest.raises(DurableReplayLedgerV1Error) as error:
        ledger_module._commit_or_raise_ambiguous(  # type: ignore[arg-type]
            BrokenCommit(),
            path="/test",
        )
    assert error.value.code == "durable_replay_ledger_commit_ambiguous"
    assert error.value.code in DURABLE_REPLAY_LEDGER_STABLE_ERROR_CODES_V1
    unknown = DurableReplayLedgerV1Error("not_registered", "not/a/path")
    assert unknown.code == "durable_replay_ledger_internal_error"
    assert unknown.path == "/"


def test_begin_immediate_has_bounded_busy_failure(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path, busy_timeout_ms=50)
    first = _artifacts(sequence=1)
    _reserve(ledger, first)
    other = open_durable_replay_ledger_v1(
        tmp_path / "ledger",
        expected_ledger_id=ledger.ledger_id,
        expected_namespace=_NAMESPACE,
        busy_timeout_ms=20,
    )
    transaction = begin_durable_replay_acceptance_v1(
        ledger, challenge_id=first[0]["challenge_id"]
    )
    try:
        with pytest.raises(DurableReplayLedgerV1Error) as busy:
            _reserve(other, _artifacts(sequence=2))
        assert busy.value.code == "durable_replay_ledger_busy"
        assert len(str(busy.value)) < 400
    finally:
        transaction.rollback()
        other.close()
        ledger.close()


def test_multiprocess_reservation_is_exactly_once(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    identity = ledger.ledger_id
    directory = ledger.directory_path
    ledger.close()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    output = context.Queue()
    artifacts = _artifacts()
    processes = [
        context.Process(
            target=_reservation_worker,
            args=(directory, identity, artifacts, start, output),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    results = [output.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert [status for status, _ in results].count("ok") == 1
    assert {code for status, code in results if status == "error"} == {
        "durable_replay_challenge_id_reused"
    }
    reopened = open_durable_replay_ledger_v1(
        directory,
        expected_ledger_id=identity,
        expected_namespace=_NAMESPACE,
    )
    assert audit_durable_replay_ledger_v1(reopened).challenge_count == 1
    reopened.close()


def test_multiprocess_acceptance_is_exactly_once(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    identity = ledger.ledger_id
    directory = ledger.directory_path
    ledger.close()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    output = context.Queue()
    processes = [
        context.Process(
            target=_acceptance_worker,
            args=(directory, identity, artifacts, start, output),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    results = [output.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert [status for status, _ in results].count("ok") == 1
    assert {code for status, code in results if status == "error"} <= {
        "durable_replay_challenge_already_accepted",
        "durable_replay_ledger_busy",
    }
    reopened = open_durable_replay_ledger_v1(
        directory,
        expected_ledger_id=identity,
        expected_namespace=_NAMESPACE,
    )
    audit = audit_durable_replay_ledger_v1(reopened)
    assert (audit.acceptance_count, audit.event_count) == (1, 2)
    reopened.close()


@pytest.mark.parametrize("kind", ["fifo", "symlink", "hardlink"])
def test_special_database_files_fail_without_opening(tmp_path: Path, kind: str) -> None:
    if kind == "fifo":
        directory = tmp_path / "ledger"
        directory.mkdir(mode=0o700)
        database = directory / _DATABASE_FILENAME
        os.mkfifo(database, mode=0o600)
        started = time.monotonic()
        with pytest.raises(DurableReplayLedgerV1Error) as error:
            open_durable_replay_ledger_v1(
                directory,
                expected_ledger_id=_HASH_A,
                expected_namespace=_NAMESPACE,
            )
        assert time.monotonic() - started < 2.0
        assert error.value.code == "durable_replay_ledger_database_file_invalid"
        return
    ledger = _initialize(tmp_path)
    identity = ledger.ledger_id
    database = Path(ledger.database_path)
    ledger.close()
    if kind == "symlink":
        original = database.with_suffix(".original")
        database.rename(original)
        database.symlink_to(original.name)
    else:
        os.link(database, database.with_suffix(".hardlink"))
    with pytest.raises(DurableReplayLedgerV1Error) as error:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id=identity,
            expected_namespace=_NAMESPACE,
        )
    assert error.value.code == "durable_replay_ledger_database_file_invalid"


def test_owner_private_directory_and_inode_replacement_are_enforced(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    directory = tmp_path / "ledger"
    directory.chmod(0o750)
    with pytest.raises(DurableReplayLedgerV1Error) as mode_error:
        audit_durable_replay_ledger_v1(ledger)
    assert mode_error.value.code == "durable_replay_ledger_directory_not_owner_private"
    directory.chmod(0o700)
    database = Path(ledger.database_path)
    replacement = database.with_suffix(".replacement")
    shutil.copyfile(database, replacement)
    replacement.chmod(0o600)
    database.unlink()
    replacement.rename(database)
    with pytest.raises(DurableReplayLedgerV1Error) as inode_error:
        audit_durable_replay_ledger_v1(ledger)
    assert inode_error.value.code == "durable_replay_ledger_inode_replaced"
    ledger.close()


def test_directory_inode_replacement_is_detected(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    directory.mkdir(mode=0o700)
    ledger = initialize_durable_replay_ledger_v1(
        directory,
        namespace=_NAMESPACE,
    )
    moved = tmp_path / "ledger.original"
    directory.rename(moved)
    directory.mkdir(mode=0o700)
    with pytest.raises(DurableReplayLedgerV1Error) as error:
        audit_durable_replay_ledger_v1(ledger)
    assert error.value.code == "durable_replay_ledger_directory_inode_replaced"
    ledger.close()


def test_tables_are_immutable_and_event_chain_tamper_is_detected(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    database = ledger.database_path
    identity = ledger.ledger_id
    connection = sqlite3.connect(database)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE challenges SET request_id = 'request.tampered'")
        connection.rollback()
        connection.execute("DROP TRIGGER events_reject_update")
        connection.execute(
            "UPDATE events SET event_hash = ? WHERE event_sequence = 1",
            ("sha256:" + "e" * 64,),
        )
        connection.execute(
            """CREATE TRIGGER events_reject_update BEFORE UPDATE ON events
               BEGIN SELECT RAISE(ABORT, 'durable_replay_immutable_table'); END"""
        )
        connection.commit()
    finally:
        connection.close()
    ledger.close()
    with pytest.raises(DurableReplayLedgerV1Error) as tamper:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id=identity,
            expected_namespace=_NAMESPACE,
        )
    assert tamper.value.code in {
        "durable_replay_event_chain_invalid",
        "durable_replay_event_hash_invalid",
    }


def test_insert_or_replace_cannot_bypass_immutable_table_guards(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    artifacts = _artifacts()
    _reserve(ledger, artifacts)
    _accept(ledger, artifacts)
    connection = sqlite3.connect(ledger.database_path)
    try:
        connection.execute("PRAGMA recursive_triggers = OFF")
        for table_name in (
            "meta",
            "campaigns",
            "challenges",
            "acceptances",
            "events",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(
                    f"INSERT OR REPLACE INTO {table_name} "
                    f"SELECT * FROM {table_name} LIMIT 1"
                )
            connection.rollback()
    finally:
        connection.close()
    audit = audit_durable_replay_ledger_v1(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        1,
        2,
    )
    ledger.close()


@pytest.mark.parametrize("column", ["trust_registry_hash", "fixture_registry_hash"])
def test_campaign_registry_binding_tamper_is_detected_after_schema_restore(
    tmp_path: Path,
    column: str,
) -> None:
    ledger = _initialize(tmp_path)
    _reserve(ledger, _artifacts())
    connection = sqlite3.connect(ledger.database_path)
    try:
        connection.execute("DROP TRIGGER campaigns_reject_update")
        connection.execute(
            f"UPDATE campaigns SET {column} = ?",
            ("sha256:" + "3" * 64,),
        )
        connection.execute(
            next(
                statement
                for statement in ledger_module._TRIGGER_STATEMENTS
                if statement.startswith("CREATE TRIGGER campaigns_reject_update ")
            )
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DurableReplayLedgerV1Error) as tamper:
        audit_durable_replay_ledger_v1(ledger)
    assert tamper.value.code == "durable_replay_campaign_identity_drift"
    ledger.close()


def test_reservation_receipt_cannot_claim_a_foreign_ledger(
    tmp_path: Path,
) -> None:
    ledger = _initialize(tmp_path)
    _reserve(ledger, _artifacts())
    connection = sqlite3.connect(ledger.database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT challenge_id, reservation_receipt_blob FROM challenges"
        ).fetchone()
        assert row is not None
        payload = json.loads(bytes(row["reservation_receipt_blob"]))
        payload["ledger_id"] = "sha256:" + "4" * 64
        payload["receipt_hash"] = canonical_hash(
            {key: value for key, value in payload.items() if key != "receipt_hash"}
        )
        blob = canonical_json_bytes(payload)
        connection.execute("DROP TRIGGER challenges_reject_update")
        connection.execute(
            """UPDATE challenges
               SET reservation_receipt_blob = ?, reservation_receipt_hash = ?
               WHERE challenge_id = ?""",
            (blob, payload["receipt_hash"], row["challenge_id"]),
        )
        connection.execute(
            next(
                statement
                for statement in ledger_module._TRIGGER_STATEMENTS
                if statement.startswith("CREATE TRIGGER challenges_reject_update ")
            )
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DurableReplayLedgerV1Error) as tamper:
        audit_durable_replay_ledger_v1(ledger)
    assert tamper.value.code == "durable_replay_reservation_receipt_binding_invalid"
    ledger.close()


def test_deep_canonical_json_recursion_maps_to_bounded_extent_error() -> None:
    depth = 2_000
    raw = b'{"value":' + (b"[" * depth) + b"0" + (b"]" * depth) + b"}"
    with pytest.raises(DurableReplayLedgerV1Error) as recursion:
        ledger_module._decode_canonical_json_bytes(
            raw,
            path="/deep_json",
            max_bytes=len(raw),
        )
    assert recursion.value.code == "durable_replay_json_extent_invalid"
    assert recursion.value.path == "/deep_json"
    assert len(str(recursion.value)) < 400


def test_database_corruption_fails_closed_with_bounded_error(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    identity = ledger.ledger_id
    database = Path(ledger.database_path)
    ledger.close()
    with database.open("r+b", buffering=0) as stream:
        stream.seek(0)
        stream.write(b"not-a-sqlite-ledger" + b"\0" * 256)
    with pytest.raises(DurableReplayLedgerV1Error) as corruption:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id=identity,
            expected_namespace=_NAMESPACE,
        )
    assert corruption.value.code in {
        "durable_replay_ledger_corrupt",
        "durable_replay_ledger_sqlite_error",
    }
    assert len(str(corruption.value)) < 400


def test_truncated_database_fails_closed_on_reopen(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    identity = ledger.ledger_id
    database = Path(ledger.database_path)
    ledger.close()
    os.truncate(database, 128)
    with pytest.raises(DurableReplayLedgerV1Error) as truncated:
        open_durable_replay_ledger_v1(
            tmp_path / "ledger",
            expected_ledger_id=identity,
            expected_namespace=_NAMESPACE,
        )
    assert truncated.value.code in {
        "durable_replay_ledger_corrupt",
        "durable_replay_ledger_sqlite_error",
        "durable_replay_ledger_pragma_contract_invalid",
    }


def test_pragma_and_schema_manifest_contract_is_fixed(tmp_path: Path) -> None:
    ledger = _initialize(tmp_path)
    connection = sqlite3.connect(ledger.database_path)
    try:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == 0x53525632
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        trigger_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'trigger'"
        ).fetchone()[0]
        assert trigger_count == 15
    finally:
        connection.close()
    internal = ledger_module._connect(ledger)
    try:
        assert internal.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert internal.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        assert internal.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert internal.execute("PRAGMA synchronous").fetchone()[0] == 3
        assert (
            internal.execute("PRAGMA max_page_count").fetchone()[0]
            == ledger_module._MAX_DATABASE_PAGES
        )
    finally:
        internal.close()
    ledger.close()


def test_receipt_schema_is_valid_draft_2020_12() -> None:
    schema_path = (
        Path(__file__).parents[1]
        / "src"
        / "structural_analysis"
        / "schemas"
        / "durable_replay_ledger_receipts_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    reservation = schema["$defs"]["reservation"]["properties"]
    storage = schema["$defs"]["storage"]["properties"]
    audit = schema["$defs"]["audit"]["properties"]
    assert reservation["key_epoch"]["maximum"] == 2**63 - 1
    assert reservation["run_sequence"]["maximum"] == 2**63 - 1
    assert reservation["event_sequence"]["maximum"] == 200_000
    assert storage["run_sequence"]["maximum"] == 2**63 - 1
    assert storage["acceptance_sequence"]["maximum"] == 100_000
    assert storage["event_sequence"]["maximum"] == 200_000
    assert audit["last_event_sequence"]["maximum"] == 200_000
    bounded_integer_fields = (
        reservation["key_epoch"],
        reservation["run_sequence"],
        reservation["event_sequence"],
        storage["run_sequence"],
        storage["acceptance_sequence"],
        storage["event_sequence"],
        audit["last_event_sequence"],
    )
    for field_schema in bounded_integer_fields:
        rejected = list(
            Draft202012Validator(field_schema).iter_errors(field_schema["maximum"] + 1)
        )
        assert len(rejected) == 1
        assert rejected[0].validator == "maximum"
