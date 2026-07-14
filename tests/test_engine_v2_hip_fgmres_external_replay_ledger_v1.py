from __future__ import annotations

import base64
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from typing import Any

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_release_identity_v1 as release_identity,
    fgmres_external_replay_ledger_v1 as replay_ledger,
    fgmres_external_signed_evidence_v1 as signed_evidence,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.engine_v2.evidence.durable_replay_ledger_v1 import (
    DurableReplayLedgerV1Error,
    begin_durable_replay_acceptance_v1,
)
from structural_analysis.engine_v2.evidence import (
    durable_replay_ledger_v1 as durable_replay,
)
from tests.test_engine_v2_hip_fgmres_external_release_identity_v1 import (
    _paths,
    _receipt,
)
from tests.test_engine_v2_hip_fgmres_external_signed_evidence_v1 import (
    _build_envelope,
    evidence_material as _source_evidence_material,
)


@pytest.fixture(scope="module")
def evidence_material_fixture() -> dict[str, Any]:
    return _source_evidence_material.__wrapped__()


def _verified_release(
    tmp_path: Path,
    material: dict[str, Any],
) -> release_identity.HipFgmresExternalVerifiedReleaseV1:
    binding = material["release"]
    base = _receipt()
    draft = replace(
        base,
        release_binding_hash=binding.binding_hash,
        wheel_filename=binding.wheel_filename,
        wheel_byte_count=binding.wheel_byte_count,
        wheel_sha256=binding.wheel_sha256,
        wheel_record_sha256=binding.wheel_record_sha256,
        source_commit=binding.source_commit,
        source_tree_sha256=binding.source_tree_sha256,
        source_bundle_sha256=binding.source_bundle_sha256,
        runner_source_sha256=binding.runner_source_sha256,
        build_recipe_sha256=binding.build_recipe_sha256,
        dependency_lock_sha256=binding.dependency_lock_sha256,
        receipt_hash="sha256:" + "0" * 64,
    )
    identity = replace(
        draft,
        receipt_hash=canonical_hash(
            release_identity._receipt_payload(draft, include_hash=False)
        ),
    )
    release_identity.validate_hip_fgmres_external_release_identity_receipt_v1(identity)
    return release_identity.HipFgmresExternalVerifiedReleaseV1(
        paths=_paths(tmp_path),
        release_binding=binding,
        identity_receipt=identity,
        mint=release_identity._VERIFIED_RELEASE_MINT,
    )


def _patch_synthetic_authorities(
    monkeypatch: pytest.MonkeyPatch,
    material: dict[str, Any],
    *,
    release_replays: list[str] | None = None,
) -> None:
    def verify_release(
        value: release_identity.HipFgmresExternalVerifiedReleaseV1,
    ) -> release_identity.HipFgmresExternalVerifiedReleaseV1:
        if release_replays is not None:
            release_replays.append(value.identity_receipt.receipt_hash)
        return value

    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_release_artifacts_v1",
        verify_release,
    )
    monkeypatch.setattr(
        signed_evidence,
        "_TRUST_REGISTRY_LOADER_AUTHORITY",
        lambda: material["trust_registry"],
    )
    monkeypatch.setattr(
        signed_evidence,
        "_FIXTURE_REGISTRY_LOADER_AUTHORITY",
        lambda: material["registry"],
    )
    monkeypatch.setattr(signed_evidence, "_utc_now", lambda: material["now"])
    monkeypatch.setattr(durable_replay, "_utc_now", lambda: material["now"])

    def issue_with_synthetic_registry(
        *,
        verified_release: release_identity.HipFgmresExternalVerifiedReleaseV1,
        key_id: str,
        runner_id: str,
        run_sequence: int,
        request_id: str,
        campaign_id: str,
        ttl_seconds: int = 900,
    ) -> signed_evidence.HipFgmresExternalChallengeV1:
        release_identity.verify_hip_fgmres_external_release_artifacts_v1(
            verified_release
        )
        return signed_evidence._issue_challenge_with_registry(
            release_binding=verified_release.release_binding,
            key_id=key_id,
            runner_id=runner_id,
            run_sequence=run_sequence,
            request_id=request_id,
            campaign_id=campaign_id,
            ttl_seconds=ttl_seconds,
            registry=material["trust_registry"],
            now=material["now"],
        )

    monkeypatch.setattr(
        release_identity,
        "issue_hip_fgmres_external_evidence_challenge_for_verified_release_v1",
        issue_with_synthetic_registry,
    )


def _initialize_ledger(root: Path) -> Any:
    root.mkdir(mode=0o700)
    return replay_ledger.initialize_hip_fgmres_external_replay_ledger_v1(str(root))


def test_restart_rehydrates_ledger_challenge_and_durably_accepts_exact_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    release_replays: list[str] = []
    _patch_synthetic_authorities(
        monkeypatch,
        evidence_material,
        release_replays=release_replays,
    )
    ledger_root = tmp_path / "replay-ledger"
    ledger = _initialize_ledger(ledger_root)
    ledger_id = ledger.ledger_id
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:test-001",
        campaign_id="campaign:test-001",
    )
    assert challenge.ledger_id == ledger_id
    assert release_replays == [verified.identity_receipt.receipt_hash]
    assert challenge.reservation_receipt.ledger_id == ledger_id
    assert (
        challenge.reservation_receipt.namespace
        == replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1
    )
    raw, returned = _build_envelope(
        evidence_material,
        challenge_override=challenge,
    )
    assert returned is challenge

    with pytest.raises(DurableReplayLedgerV1Error) as duplicate:
        replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
            verified_release=verified,
            ledger=ledger,
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:test-duplicate",
            campaign_id="campaign:test-001",
        )
    assert duplicate.value.code in {
        "durable_replay_runner_sequence_not_increasing",
        "durable_replay_runner_sequence_duplicate",
    }
    assert len(release_replays) == 2
    ledger.close()

    reopened = replay_ledger.open_hip_fgmres_external_replay_ledger_v1(
        str(ledger_root),
        expected_ledger_id=ledger_id,
    )
    monkeypatch.setattr(
        signed_evidence,
        "_utc_now",
        lambda: evidence_material["now"] + timedelta(seconds=3),
    )
    monkeypatch.setattr(
        durable_replay,
        "_utc_now",
        lambda: evidence_material["now"] + timedelta(seconds=3),
    )
    result = (
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=reopened,
        )
    )
    assert len(release_replays) == 4

    assert result.identity_receipt is verified.identity_receipt
    assert result.signed_receipt.verified_slot_count == 10
    receipt = result.ledger_receipt
    assert receipt.claims.durable_replay_ledger_verified
    assert receipt.claims.runner_sequence_cross_process_uniqueness_enforced
    assert receipt.claims.signed_acceptance_durably_committed
    assert not receipt.claims.signed_envelope_binds_release_identity_receipt
    assert not receipt.claims.exactly_once_delivery_verified
    assert not receipt.claims.coordinated_storage_rollback_resisted
    assert not receipt.claims.hostile_in_process_mint_isolation_verified
    assert not receipt.claims.same_artifact_two_architecture_verified
    assert not receipt.claims.commercial_ready
    assert not receipt.promotion_eligible
    assert not result.signed_receipt.claims.durable_replay_ledger_verified
    assert not result.identity_receipt.claims.durable_replay_ledger_verified

    mismatched_draft = replace(
        receipt,
        runner_id="different-runner",
        receipt_hash="sha256:" + "0" * 64,
    )
    mismatched_receipt = replace(
        mismatched_draft,
        receipt_hash=canonical_hash(
            replay_ledger._receipt_payload(
                mismatched_draft,
                include_hash=False,
            )
        ),
    )
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error) as mismatch:
        replay_ledger.HipFgmresExternalDurablyVerifiedSignedEvidenceV1(
            identity_receipt=result.identity_receipt,
            signed_receipt=result.signed_receipt,
            ledger_receipt=mismatched_receipt,
            mint=replay_ledger._DURABLY_VERIFIED_MINT,
        )
    assert mismatch.value.code.endswith("durable_result_invalid")

    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(reopened)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 1
    assert audit.event_count == 2
    assert audit.last_event_hash == receipt.acceptance_event_hash

    with pytest.raises(DurableReplayLedgerV1Error) as replayed:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=reopened,
        )
    assert replayed.value.code == "durable_replay_challenge_already_accepted"
    assert len(release_replays) == 4

    later = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=reopened,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=2,
        request_id="request:test-002",
        campaign_id="campaign:test-001",
    )
    assert later.challenge_id != challenge.challenge_id
    assert len(release_replays) == 5
    later_audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(reopened)
    assert later_audit.event_count == 3
    assert later_audit.last_event_hash != receipt.acceptance_commit_head_event_hash
    assert (
        receipt.acceptance_commit_head_event_sequence
        == receipt.acceptance_event_sequence
    )

    monkeypatch.setattr(
        signed_evidence,
        "_utc_now",
        lambda: evidence_material["now"] + timedelta(days=1),
    )
    recovered = (
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v1(
            verified_release=verified,
            ledger=reopened,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=result.signed_receipt.envelope_hash,
        )
    )
    assert recovered.ledger_receipt == receipt
    assert recovered.signed_receipt == result.signed_receipt
    assert len(release_replays) == 6

    monkeypatch.setattr(
        signed_evidence,
        "_TRUST_REGISTRY_LOADER_AUTHORITY",
        signed_evidence.load_hip_fgmres_external_trust_anchor_registry_v1,
    )
    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV1Error
    ) as registry_drift:
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v1(
            verified_release=verified,
            ledger=reopened,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=result.signed_receipt.envelope_hash,
        )
    assert registry_drift.value.code == "hip_fgmres_external_trust_anchor_not_found"
    assert len(release_replays) == 7
    reopened.close()


def test_public_zero_key_path_records_no_challenge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    ledger = _initialize_ledger(tmp_path / "zero-key-ledger")

    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV1Error
    ) as caught:
        replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
            verified_release=verified,
            ledger=ledger,
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:zero-key",
            campaign_id="campaign:zero-key",
        )
    assert caught.value.code == "hip_fgmres_external_trust_anchor_not_found"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 0
    assert audit.acceptance_count == 0
    assert audit.event_count == 0
    ledger.close()


def test_commit_then_response_failure_recovers_without_second_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "response-failure-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:response-failure",
        campaign_id="campaign:response-failure",
    )
    raw, _ = _build_envelope(evidence_material, challenge_override=challenge)
    verification_time = evidence_material["now"] + timedelta(seconds=3)
    monkeypatch.setattr(signed_evidence, "_utc_now", lambda: verification_time)
    monkeypatch.setattr(durable_replay, "_utc_now", lambda: verification_time)

    class ResponsePublicationFailure(RuntimeError):
        pass

    original_consume = signed_evidence.HipFgmresExternalChallengeV1._consume
    consume_calls: list[str] = []

    def fail_first_consume(
        self: signed_evidence.HipFgmresExternalChallengeV1,
        token: object,
    ) -> None:
        if not consume_calls:
            consume_calls.append("failed_after_commit")
            raise ResponsePublicationFailure("simulated response loss")
        original_consume(self, token)
        consume_calls.append("recovery_consumed")

    monkeypatch.setattr(
        signed_evidence.HipFgmresExternalChallengeV1,
        "_consume",
        fail_first_consume,
    )
    with pytest.raises(ResponsePublicationFailure, match="simulated response loss"):
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )

    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 1
    assert audit.event_count == 2
    with pytest.raises(DurableReplayLedgerV1Error) as retry:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert retry.value.code == "durable_replay_challenge_already_accepted"

    expected_envelope_hash = json.loads(raw)["envelope_hash"]
    recovered = (
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v1(
            verified_release=verified,
            ledger=ledger,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=expected_envelope_hash,
        )
    )
    assert recovered.signed_receipt.verified_slot_count == 10
    assert recovered.ledger_receipt.acceptance_event_sequence == 2
    assert consume_calls == ["failed_after_commit", "recovery_consumed"]
    final_audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert final_audit == audit
    ledger.close()


def test_foreign_namespace_ledger_is_rejected_before_any_event(
    tmp_path: Path,
    evidence_material_fixture: dict[str, Any],
) -> None:
    verified = _verified_release(tmp_path, evidence_material_fixture)
    foreign_root = tmp_path / "foreign-namespace-ledger"
    foreign_root.mkdir(mode=0o700)
    foreign = durable_replay.initialize_durable_replay_ledger_v1(
        str(foreign_root),
        namespace="other_solver_evidence_v1",
    )

    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error) as caught:
        replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
            verified_release=verified,
            ledger=foreign,
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:foreign-ledger",
            campaign_id="campaign:foreign-ledger",
        )
    assert caught.value.code == "hip_fgmres_external_replay_ledger_namespace_mismatch"
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error):
        replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(foreign)
    audit = durable_replay.audit_durable_replay_ledger_v1(foreign)
    assert audit.event_count == 0
    assert audit.challenge_count == 0
    assert audit.acceptance_count == 0
    foreign.close()


@pytest.mark.parametrize(
    "depth",
    [
        signed_evidence._ENVELOPE_MAX_JSON_DEPTH + 1,
        1_100,
    ],
)
def test_excessive_envelope_nesting_fails_before_any_ledger_event(
    tmp_path: Path,
    evidence_material_fixture: dict[str, Any],
    depth: int,
) -> None:
    verified = _verified_release(tmp_path, evidence_material_fixture)
    ledger = _initialize_ledger(tmp_path / f"nested-envelope-ledger-{depth}")
    raw = b"[" * depth + b"0" + b"]" * depth

    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV1Error
    ) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert caught.value.code == "hip_fgmres_external_envelope_extent_invalid"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.event_count == 0
    assert audit.challenge_count == 0
    assert audit.acceptance_count == 0
    ledger.close()


def test_full_verifier_runs_without_holding_sqlite_writer_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "optimistic-two-phase-ledger")
    first = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:optimistic-001",
        campaign_id="campaign:optimistic",
    )
    raw, _ = _build_envelope(evidence_material, challenge_override=first)

    class VerificationPaused(RuntimeError):
        pass

    nested_challenges: list[replay_ledger.HipFgmresExternalLedgeredChallengeV1] = []

    def verifier_probe(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        nested_challenges.append(
            replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
                verified_release=verified,
                ledger=ledger,
                key_id="ed25519:external-runner:v1",
                runner_id="external-runner",
                run_sequence=2,
                request_id="request:optimistic-002",
                campaign_id="campaign:optimistic",
            )
        )
        raise VerificationPaused

    monkeypatch.setattr(signed_evidence, "_verify_with_authorities", verifier_probe)
    with pytest.raises(VerificationPaused):
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert nested_challenges[0].challenge_id != first.challenge_id
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 2
    assert audit.acceptance_count == 0
    ledger.close()


def test_acceptance_expiry_after_numerical_verification_stays_uncommitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "expiry-at-commit-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:expiry-at-commit",
        campaign_id="campaign:expiry-at-commit",
        ttl_seconds=60,
    )
    raw, _ = _build_envelope(evidence_material, challenge_override=challenge)

    def verifier_after_expiry(*args: Any, **kwargs: Any) -> None:
        del args
        kwargs["success_commit_hook"](object())

    monkeypatch.setattr(
        signed_evidence,
        "_utc_now",
        lambda: evidence_material["now"] + timedelta(seconds=61),
    )
    monkeypatch.setattr(
        signed_evidence,
        "_verify_with_authorities",
        verifier_after_expiry,
    )
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert caught.value.code.endswith("acceptance_time_invalid")
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 0
    ledger.close()


def test_recovery_reverifies_signature_before_minting_authoritative_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "forged-recovery-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:forged-recovery",
        campaign_id="campaign:forged-recovery",
    )
    raw, _ = _build_envelope(evidence_material, challenge_override=challenge)
    envelope = json.loads(raw)
    signature = bytearray(base64.b64decode(envelope["signature_base64"]))
    signature[0] ^= 1
    envelope["signature_base64"] = base64.b64encode(signature).decode("ascii")
    envelope["envelope_hash"] = canonical_hash(
        {key: value for key, value in envelope.items() if key != "envelope_hash"}
    )
    tampered_raw = canonical_json_bytes(envelope)
    fake_receipt = {
        "challenge_id": challenge.challenge_id,
        "release_binding_hash": verified.release_binding.binding_hash,
        "key_id": "ed25519:external-runner:v1",
        "key_epoch": 1,
        "runner_id": "external-runner",
        "run_sequence": 1,
        "envelope_hash": envelope["envelope_hash"],
        "signed_payload_sha256": envelope["signed_payload_sha256"],
    }
    fake_receipt["receipt_hash"] = canonical_hash(fake_receipt)
    monkeypatch.setattr(
        durable_replay,
        "_utc_now",
        lambda: evidence_material["now"] + timedelta(seconds=3),
    )
    with begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=challenge.challenge_id,
    ) as transaction:
        storage = transaction.commit(
            envelope_bytes=tampered_raw,
            signed_receipt=fake_receipt,
            accepted_not_before_utc=signed_evidence._format_utc(
                evidence_material["now"] + timedelta(seconds=3)
            ),
        )

    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV1Error
    ) as caught:
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v1(
            verified_release=verified,
            ledger=ledger,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=storage.envelope_hash,
        )
    assert caught.value.code == "hip_fgmres_external_signature_invalid"
    ledger.close()


def test_envelope_routing_must_equal_full_stored_challenge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "routing-drift-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:routing-original",
        campaign_id="campaign:routing",
    )

    def mutate(payload: dict[str, Any]) -> None:
        payload["challenge"]["request_id"] = "request:routing-forged"
        payload["challenge"]["challenge_id"] = canonical_hash(
            {
                key: value
                for key, value in payload["challenge"].items()
                if key != "challenge_id"
            }
        )

    raw, _ = _build_envelope(
        evidence_material,
        challenge_override=challenge,
        mutate=mutate,
    )
    with pytest.raises(DurableReplayLedgerV1Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert caught.value.code == "durable_replay_challenge_not_reserved"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 0
    assert audit.event_count == 1
    ledger.close()


def test_storage_clock_past_expiry_rolls_back_before_acceptance_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "expiry-boundary-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:expiry-boundary",
        campaign_id="campaign:expiry-boundary",
    )
    raw, _ = _build_envelope(evidence_material, challenge_override=challenge)
    expires_at = signed_evidence._parse_utc(
        challenge.to_dict()["expires_at_utc"],
        "/challenge/expires_at_utc",
    )
    monkeypatch.setattr(
        signed_evidence,
        "_utc_now",
        lambda: expires_at - timedelta(microseconds=1),
    )
    monkeypatch.setattr(
        durable_replay,
        "_utc_now",
        lambda: expires_at + timedelta(microseconds=1),
    )
    monkeypatch.setattr(
        signed_evidence,
        "_validate_cases",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(DurableReplayLedgerV1Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert caught.value.code == "durable_replay_challenge_expired_at_acceptance"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 0
    assert audit.event_count == 1
    ledger.close()


def test_storage_clock_rollback_before_verified_time_cannot_poison_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "clock-rollback-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:clock-rollback",
        campaign_id="campaign:clock-rollback",
    )
    raw, _ = _build_envelope(evidence_material, challenge_override=challenge)
    signed_clock = iter(
        (
            evidence_material["now"] + timedelta(seconds=3),
            evidence_material["now"] + timedelta(seconds=1),
        )
    )
    monkeypatch.setattr(signed_evidence, "_utc_now", lambda: next(signed_clock))
    monkeypatch.setattr(
        durable_replay,
        "_utc_now",
        lambda: evidence_material["now"] + timedelta(seconds=1),
    )
    monkeypatch.setattr(
        signed_evidence,
        "_validate_cases",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(DurableReplayLedgerV1Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert caught.value.code == "durable_replay_acceptance_not_before_not_reached"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 0
    assert audit.event_count == 1
    ledger.close()


def test_acceptance_rejects_valid_but_different_stored_release_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    _patch_synthetic_authorities(monkeypatch, evidence_material)
    ledger = _initialize_ledger(tmp_path / "identity-drift-ledger")
    challenge = replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v1(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:identity-drift",
        campaign_id="campaign:identity-drift",
    )
    raw, _ = _build_envelope(
        evidence_material,
        challenge_override=challenge,
    )
    identity_draft = replace(
        verified.identity_receipt,
        source_tracked_file_count=(
            verified.identity_receipt.source_tracked_file_count + 1
        ),
        receipt_hash="sha256:" + "0" * 64,
    )
    different_identity = replace(
        identity_draft,
        receipt_hash=canonical_hash(
            release_identity._receipt_payload(identity_draft, include_hash=False)
        ),
    )
    release_identity.validate_hip_fgmres_external_release_identity_receipt_v1(
        different_identity
    )
    drifted_release = release_identity.HipFgmresExternalVerifiedReleaseV1(
        paths=verified._paths,
        release_binding=verified.release_binding,
        identity_receipt=different_identity,
        mint=release_identity._VERIFIED_RELEASE_MINT,
    )

    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v1(
            raw,
            verified_release=drifted_release,
            ledger=ledger,
        )
    assert caught.value.code.endswith("identity_mismatch")
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v1(ledger)
    assert audit.challenge_count == 1
    assert audit.acceptance_count == 0
    assert audit.event_count == 1
    ledger.close()


def test_durable_wrappers_reject_direct_construction(
    tmp_path: Path,
    evidence_material_fixture: dict[str, Any],
) -> None:
    evidence_material = evidence_material_fixture
    verified = _verified_release(tmp_path, evidence_material)
    challenge = signed_evidence._issue_challenge_with_registry(
        release_binding=verified.release_binding,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=1,
        request_id="request:constructor",
        campaign_id="campaign:constructor",
        ttl_seconds=900,
        registry=evidence_material["trust_registry"],
        now=evidence_material["now"],
    )
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error) as caught:
        replay_ledger.HipFgmresExternalLedgeredChallengeV1(
            challenge=challenge,
            reservation=object(),
            ledger_id="sha256:" + "1" * 64,
            mint=object(),
        )
    assert caught.value.code.endswith("challenge_construction_forbidden")
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error) as result:
        replay_ledger.HipFgmresExternalDurablyVerifiedSignedEvidenceV1(
            identity_receipt=object(),
            signed_receipt=object(),
            ledger_receipt=object(),
            mint=object(),
        )
    assert result.value.code.endswith("durable_result_construction_forbidden")


def test_receipt_schema_rejects_claim_or_hash_tamper() -> None:
    claims = replay_ledger.HipFgmresExternalReplayLedgerClaimsV1()
    draft = replay_ledger.HipFgmresExternalReplayLedgerReceiptV1(
        schema_version=(
            replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_RECEIPT_SCHEMA_VERSION_V1
        ),
        capability_profile=(
            replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_CAPABILITY_PROFILE_V1
        ),
        status="external_signed_evidence_durably_recorded",
        evidence_scope=(
            replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_EVIDENCE_SCOPE_V1
        ),
        ledger_id="sha256:" + "1" * 64,
        ledger_namespace=(replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V1),
        reservation_event_sequence=1,
        reservation_event_hash="sha256:" + "2" * 64,
        acceptance_event_sequence=2,
        acceptance_event_hash="sha256:" + "3" * 64,
        acceptance_commit_head_event_sequence=2,
        acceptance_commit_head_event_hash="sha256:" + "3" * 64,
        request_id="request:schema",
        campaign_id="campaign:schema",
        challenge_id="sha256:" + "4" * 64,
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        runner_id="external-runner",
        run_sequence=1,
        release_binding_hash="sha256:" + "5" * 64,
        release_identity_receipt_hash="sha256:" + "6" * 64,
        trust_registry_hash="sha256:" + "7" * 64,
        fixture_registry_hash="sha256:" + "8" * 64,
        envelope_hash="sha256:" + "9" * 64,
        signed_payload_sha256="sha256:" + "a" * 64,
        signed_evidence_receipt_hash="sha256:" + "b" * 64,
        claims=claims,
        promotion_eligible=False,
        receipt_hash="sha256:" + "0" * 64,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(
            replay_ledger._receipt_payload(draft, include_hash=False)
        ),
    )
    assert (
        replay_ledger.validate_hip_fgmres_external_replay_ledger_receipt_v1(receipt)
        is receipt
    )
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error):
        replay_ledger.validate_hip_fgmres_external_replay_ledger_receipt_v1(
            replace(
                receipt,
                acceptance_commit_head_event_hash="sha256:" + "c" * 64,
            )
        )

    payload = receipt.to_dict()
    payload["claims"]["commercial_ready"] = True
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV1Error):
        replay_ledger._validate_schema(payload)
