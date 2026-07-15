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
    fgmres_external_replay_ledger_v1 as replay_ledger_v1,
    fgmres_external_replay_ledger_v2 as replay_ledger,
    fgmres_external_signed_evidence_v2 as signed_evidence,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.engine_v2.evidence import (
    durable_replay_ledger_v1 as durable_replay,
)
from structural_analysis.engine_v2.evidence.durable_replay_ledger_v1 import (
    DurableReplayLedgerV1Error,
    begin_durable_replay_acceptance_v1,
)
from tests.test_engine_v2_hip_fgmres_external_signed_evidence_v1 import (
    _build_envelope_v2,
    _make_verified_release_v2,
    evidence_material as _source_evidence_material,
)


@pytest.fixture(scope="module")
def evidence_material_fixture() -> dict[str, Any]:
    return _source_evidence_material.__wrapped__()


def _initialize_ledger(root: Path) -> Any:
    root.mkdir(mode=0o700)
    return replay_ledger.initialize_hip_fgmres_external_replay_ledger_v2(str(root))


def _patch_synthetic_authorities(
    monkeypatch: pytest.MonkeyPatch,
    material: dict[str, Any],
    *,
    release_replays: list[str] | None = None,
) -> dict[str, Any]:
    def replay_release(value: Any) -> Any:
        if release_replays is not None:
            release_replays.append(value.identity_receipt.receipt_hash)
        return value

    clock = {
        "signed": material["now"],
        "adapter": material["now"],
        "durable": material["now"],
    }
    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_release_artifacts_v1",
        replay_release,
    )
    monkeypatch.setattr(
        signed_evidence.signed_evidence_v1,
        "_TRUST_REGISTRY_LOADER_AUTHORITY",
        lambda: material["trust_registry"],
    )
    monkeypatch.setattr(
        signed_evidence.signed_evidence_v1,
        "_FIXTURE_REGISTRY_LOADER_AUTHORITY",
        lambda: material["registry"],
    )
    monkeypatch.setattr(
        signed_evidence.signed_evidence_v1,
        "_replay_external_fixed_suite_payload_common_v1",
        lambda **_: material["family"],
    )
    monkeypatch.setattr(
        signed_evidence,
        "_utc_now_v2",
        lambda: clock["signed"],
    )
    monkeypatch.setattr(replay_ledger, "_utc_now", lambda: clock["adapter"])
    monkeypatch.setattr(durable_replay, "_utc_now", lambda: clock["durable"])
    return clock


def _issue(
    *,
    verified: Any,
    ledger: Any,
    run_sequence: int = 1,
    request_id: str = "request:v2-ledger-001",
    campaign_id: str = "campaign:v2-ledger-001",
    ttl_seconds: int = 900,
) -> Any:
    return replay_ledger.issue_hip_fgmres_external_evidence_challenge_with_replay_ledger_v2(
        verified_release=verified,
        ledger=ledger,
        key_id="ed25519:external-runner:v1",
        runner_id="external-runner",
        run_sequence=run_sequence,
        request_id=request_id,
        campaign_id=campaign_id,
        ttl_seconds=ttl_seconds,
    )


def _verification_time(clock: dict[str, Any], material: dict[str, Any]) -> None:
    current = material["now"] + timedelta(seconds=3)
    clock["signed"] = current
    clock["adapter"] = current
    clock["durable"] = current


def _format_utc(value: Any) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _detached_ledger_receipt_v2() -> Any:
    acceptance_hash = canonical_hash({"v2-detached-ledger": "acceptance"})
    draft = replay_ledger.HipFgmresExternalReplayLedgerReceiptV2(
        schema_version=(
            replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_RECEIPT_SCHEMA_VERSION_V2
        ),
        capability_profile=(
            replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_CAPABILITY_PROFILE_V2
        ),
        status="external_signed_release_identity_evidence_durably_recorded",
        evidence_scope=(
            replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_EVIDENCE_SCOPE_V2
        ),
        ledger_id=canonical_hash({"v2-detached-ledger": "id"}),
        ledger_namespace=(replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V2),
        reservation_event_sequence=1,
        reservation_event_hash=canonical_hash({"v2-detached-ledger": "reservation"}),
        acceptance_event_sequence=2,
        acceptance_event_hash=acceptance_hash,
        acceptance_commit_head_event_sequence=2,
        acceptance_commit_head_event_hash=acceptance_hash,
        request_id="request:v2-detached-receipt",
        campaign_id="campaign:v2-detached-receipt",
        challenge_id=canonical_hash({"v2-detached-ledger": "challenge"}),
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        runner_id="external-runner",
        run_sequence=1,
        release_binding_hash=canonical_hash({"v2-detached-ledger": "release"}),
        release_identity_receipt_schema_version=(
            release_identity.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        ),
        release_identity_receipt_hash=canonical_hash(
            {"v2-detached-ledger": "identity"}
        ),
        trust_registry_hash=canonical_hash({"v2-detached-ledger": "trust"}),
        fixture_registry_hash=canonical_hash({"v2-detached-ledger": "fixture"}),
        envelope_hash=canonical_hash({"v2-detached-ledger": "envelope"}),
        signed_payload_sha256=canonical_hash({"v2-detached-ledger": "payload"}),
        signed_evidence_receipt_hash=canonical_hash(
            {"v2-detached-ledger": "signed-receipt"}
        ),
        claims=replay_ledger.HipFgmresExternalReplayLedgerClaimsV2(),
        promotion_eligible=False,
        receipt_hash="sha256:" + "0" * 64,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            replay_ledger._receipt_payload(draft, include_hash=False)
        ),
    )


def test_restart_happy_path_binds_identity_and_later_event_does_not_stale_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    release_replays: list[str] = []
    clock = _patch_synthetic_authorities(
        monkeypatch,
        material,
        release_replays=release_replays,
    )
    root = tmp_path / "v2-ledger"
    ledger = _initialize_ledger(root)
    ledger_id = ledger.ledger_id
    challenge = _issue(verified=verified, ledger=ledger)
    raw, _ = _build_envelope_v2(
        material,
        verified,
        challenge_override=challenge,
    )
    ledger.close()
    ledger = replay_ledger.open_hip_fgmres_external_replay_ledger_v2(
        str(root),
        expected_ledger_id=ledger_id,
    )
    _verification_time(clock, material)

    result = (
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    )
    receipt = result.ledger_receipt
    assert result.signed_receipt.claims.signed_envelope_binds_release_identity_receipt
    assert result.signed_receipt.release_identity_receipt_schema_version == (
        verified.identity_receipt.schema_version
    )
    assert result.signed_receipt.release_identity_receipt_hash == (
        verified.identity_receipt.receipt_hash
    )
    assert receipt.release_identity_receipt_schema_version == (
        verified.identity_receipt.schema_version
    )
    assert (
        receipt.release_identity_receipt_hash == verified.identity_receipt.receipt_hash
    )
    assert receipt.ledger_namespace == (
        replay_ledger.HIP_FGMRES_EXTERNAL_REPLAY_LEDGER_NAMESPACE_V2
    )
    assert receipt.claims.durable_replay_ledger_verified
    assert receipt.claims.signed_envelope_binds_release_identity_receipt
    assert not receipt.claims.exactly_once_delivery_verified
    assert not receipt.claims.cross_host_replay_prevented
    assert not receipt.claims.coordinated_storage_rollback_resisted
    assert not receipt.claims.hostile_in_process_mint_isolation_verified
    assert not receipt.claims.cryptographic_ledger_authenticity_verified
    assert not receipt.claims.hardware_monotonic_anchor_verified
    assert not receipt.claims.promotion_eligible
    assert not receipt.claims.commercial_ready
    assert receipt.acceptance_commit_head_event_sequence == 2
    assert receipt.acceptance_commit_head_event_hash == receipt.acceptance_event_hash
    assert release_replays == [verified.identity_receipt.receipt_hash] * 6

    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV2Error):
        replay_ledger.validate_hip_fgmres_external_replay_ledger_receipt_v2(
            replace(receipt, release_identity_receipt_hash="sha256:" + "f" * 64)
        )

    later = _issue(
        verified=verified,
        ledger=ledger,
        run_sequence=2,
        request_id="request:v2-ledger-002",
        campaign_id="campaign:v2-ledger-001",
    )
    assert later.reservation_receipt.event_sequence == 3
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        2,
        1,
        3,
    )
    assert receipt.acceptance_commit_head_event_sequence == 2

    recovered = (
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v2(
            verified_release=verified,
            ledger=ledger,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=result.signed_receipt.envelope_hash,
        )
    )
    assert recovered.identity_receipt == result.identity_receipt
    assert recovered.signed_receipt == result.signed_receipt
    assert recovered.ledger_receipt == result.ledger_receipt
    ledger.close()


def test_package_zero_key_path_cannot_mutate_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    monkeypatch.setattr(signed_evidence, "_utc_now_v2", lambda: material["now"])
    monkeypatch.setattr(durable_replay, "_utc_now", lambda: material["now"])
    ledger = _initialize_ledger(tmp_path / "zero-key-ledger")

    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        _issue(verified=verified, ledger=ledger)
    assert caught.value.code == "hip_fgmres_external_v2_trust_anchor_not_found"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (audit.campaign_count, audit.challenge_count, audit.acceptance_count) == (
        0,
        0,
        0,
    )
    assert audit.event_count == 0
    ledger.close()


def test_rehydrated_durable_challenge_rechecks_release_allowlist_before_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    clock = _patch_synthetic_authorities(monkeypatch, material)
    ledger = _initialize_ledger(tmp_path / "allowlist-recheck-ledger")
    challenge = _issue(verified=verified, ledger=ledger)
    raw, _ = _build_envelope_v2(
        material,
        verified,
        challenge_override=challenge,
    )
    blocked_key = replace(
        material["trust_registry"].keys[0],
        allowed_fixture_registry_bytes_sha256=canonical_hash(
            {"forged_allowlist": "bytes"}
        ),
        allowed_fixture_registry_hash=canonical_hash({"forged_allowlist": "semantic"}),
    )
    blocked_registry = replace(
        material["trust_registry"],
        keys=(blocked_key,),
    )
    monkeypatch.setattr(
        signed_evidence.signed_evidence_v1,
        "_TRUST_REGISTRY_LOADER_AUTHORITY",
        lambda: blocked_registry,
    )
    _verification_time(clock, material)

    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            raw,
            verified_release=verified,
            ledger=ledger,
        )

    assert caught.value.code == "hip_fgmres_external_v2_challenge_release_not_allowed"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        0,
        1,
    )
    ledger.close()


def test_response_failure_recovers_without_second_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    clock = _patch_synthetic_authorities(monkeypatch, material)
    ledger = _initialize_ledger(tmp_path / "response-failure-ledger")
    challenge = _issue(verified=verified, ledger=ledger)
    raw, _ = _build_envelope_v2(
        material,
        verified,
        challenge_override=challenge,
    )
    _verification_time(clock, material)
    original_consume = signed_evidence.HipFgmresExternalChallengeV2._consume

    def fail_response(self: Any, token: object) -> None:
        del self, token
        raise RuntimeError("simulated response loss after durable commit")

    monkeypatch.setattr(
        signed_evidence.HipFgmresExternalChallengeV2,
        "_consume",
        fail_response,
    )
    with pytest.raises(RuntimeError, match="simulated response loss"):
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    monkeypatch.setattr(
        signed_evidence.HipFgmresExternalChallengeV2,
        "_consume",
        original_consume,
    )

    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        1,
        2,
    )
    with pytest.raises(DurableReplayLedgerV1Error) as second:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert second.value.code == "durable_replay_challenge_already_accepted"

    envelope_hash = json.loads(raw)["envelope_hash"]
    recovered = (
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v2(
            verified_release=verified,
            ledger=ledger,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=envelope_hash,
        )
    )
    assert recovered.signed_receipt.envelope_hash == envelope_hash
    after = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (after.acceptance_count, after.event_count) == (1, 2)
    ledger.close()


def test_v1_and_v2_ledger_namespaces_fail_closed(tmp_path: Path) -> None:
    v1_root = tmp_path / "v1-ledger"
    v1_root.mkdir(mode=0o700)
    v1_ledger = replay_ledger_v1.initialize_hip_fgmres_external_replay_ledger_v1(
        str(v1_root)
    )
    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV2Error) as v2:
        replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(v1_ledger)
    assert v2.value.code.endswith("namespace_mismatch")
    v1_ledger.close()

    v2_ledger = _initialize_ledger(tmp_path / "v2-ledger")
    with pytest.raises(replay_ledger_v1.HipFgmresExternalReplayLedgerV1Error) as v1:
        replay_ledger_v1.audit_hip_fgmres_external_replay_ledger_v1(v2_ledger)
    assert v1.value.code.endswith("namespace_mismatch")
    v2_ledger.close()


def test_release_identity_substitution_and_payload_hash_drift_do_not_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    substituted = _make_verified_release_v2(material, identity_label="substituted")
    clock = _patch_synthetic_authorities(monkeypatch, material)
    substitution_ledger = _initialize_ledger(tmp_path / "substitution-ledger")
    challenge = _issue(verified=verified, ledger=substitution_ledger)
    raw, _ = _build_envelope_v2(
        material,
        verified,
        challenge_override=challenge,
    )
    _verification_time(clock, material)

    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV2Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            raw,
            verified_release=substituted,
            ledger=substitution_ledger,
        )
    assert caught.value.code.endswith("identity_mismatch")
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(
        substitution_ledger
    )
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        0,
        1,
    )
    substitution_ledger.close()

    clock["signed"] = material["now"]
    clock["adapter"] = material["now"]
    clock["durable"] = material["now"]
    drift_ledger = _initialize_ledger(tmp_path / "hash-drift-ledger")
    drift_challenge = _issue(
        verified=verified,
        ledger=drift_ledger,
        request_id="request:v2-hash-drift",
        campaign_id="campaign:v2-hash-drift",
    )

    def drift_identity_hash(payload: dict[str, Any]) -> None:
        payload["release_identity_receipt_hash"] = "sha256:" + "f" * 64

    drifted_raw, _ = _build_envelope_v2(
        material,
        verified,
        mutate=drift_identity_hash,
        challenge_override=drift_challenge,
    )
    _verification_time(clock, material)
    with pytest.raises(signed_evidence.HipFgmresExternalSignedEvidenceV2Error) as drift:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            drifted_raw,
            verified_release=verified,
            ledger=drift_ledger,
        )
    assert drift.value.code == "hip_fgmres_external_v2_release_identity_mismatch"
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(drift_ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        0,
        1,
    )
    drift_ledger.close()


def test_forged_low_level_receipt_cannot_mint_recovery_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    clock = _patch_synthetic_authorities(monkeypatch, material)
    ledger = _initialize_ledger(tmp_path / "forged-row-ledger")
    challenge = _issue(verified=verified, ledger=ledger)
    raw, _ = _build_envelope_v2(
        material,
        verified,
        challenge_override=challenge,
    )
    envelope = json.loads(raw)
    envelope["signature_base64"] = base64.b64encode(bytes(64)).decode("ascii")
    envelope["envelope_hash"] = canonical_hash(
        {key: value for key, value in envelope.items() if key != "envelope_hash"}
    )
    forged_raw = canonical_json_bytes(envelope)
    _verification_time(clock, material)
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
    transaction = begin_durable_replay_acceptance_v1(
        ledger,
        challenge_id=challenge.challenge_id,
    )
    with transaction:
        transaction.commit(
            envelope_bytes=forged_raw,
            signed_receipt=fake_receipt,
            accepted_not_before_utc=_format_utc(clock["adapter"]),
        )
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        1,
        2,
    )

    with pytest.raises(
        signed_evidence.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        replay_ledger.recover_hip_fgmres_external_signed_evidence_from_replay_ledger_v2(
            verified_release=verified,
            ledger=ledger,
            challenge_id=challenge.challenge_id,
            expected_envelope_hash=envelope["envelope_hash"],
        )
    assert caught.value.code == "hip_fgmres_external_v2_signature_invalid"
    ledger.close()


@pytest.mark.parametrize(
    ("runner_id", "key_id"),
    [
        ("external:runner", "ed25519:external-runner:v1"),
        ("alternate-runner", "ed25519:external-runner:v1"),
    ],
)
def test_detached_ledger_receipt_rejects_runner_or_key_relation_forgery(
    runner_id: str,
    key_id: str,
) -> None:
    valid = _detached_ledger_receipt_v2()
    assert (
        replay_ledger.validate_hip_fgmres_external_replay_ledger_receipt_v2(valid)
        is valid
    )
    receipt = replace(
        valid,
        runner_id=runner_id,
        key_id=key_id,
    )
    forged = replace(
        receipt,
        receipt_hash=canonical_hash(
            replay_ledger._receipt_payload(receipt, include_hash=False)
        ),
    )

    with pytest.raises(replay_ledger.HipFgmresExternalReplayLedgerV2Error):
        replay_ledger.validate_hip_fgmres_external_replay_ledger_receipt_v2(forged)


@pytest.mark.parametrize(
    ("durable_seconds", "expected_code"),
    [
        (61, "durable_replay_challenge_expired_at_acceptance"),
        (2, "durable_replay_acceptance_not_before_not_reached"),
    ],
)
def test_storage_time_failure_rolls_back_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_material_fixture: dict[str, Any],
    durable_seconds: int,
    expected_code: str,
) -> None:
    material = evidence_material_fixture
    verified = _make_verified_release_v2(material)
    clock = _patch_synthetic_authorities(monkeypatch, material)
    ledger = _initialize_ledger(tmp_path / f"storage-time-{durable_seconds}")
    challenge = _issue(
        verified=verified,
        ledger=ledger,
        request_id=f"request:v2-storage-{durable_seconds}",
        campaign_id=f"campaign:v2-storage-{durable_seconds}",
        ttl_seconds=60,
    )
    raw, _ = _build_envelope_v2(
        material,
        verified,
        challenge_override=challenge,
    )
    clock["signed"] = material["now"] + timedelta(seconds=3)
    clock["adapter"] = material["now"] + timedelta(seconds=3)
    clock["durable"] = material["now"] + timedelta(seconds=durable_seconds)

    with pytest.raises(DurableReplayLedgerV1Error) as caught:
        replay_ledger.verify_hip_fgmres_external_signed_evidence_with_replay_ledger_v2(
            raw,
            verified_release=verified,
            ledger=ledger,
        )
    assert caught.value.code == expected_code
    audit = replay_ledger.audit_hip_fgmres_external_replay_ledger_v2(ledger)
    assert (audit.challenge_count, audit.acceptance_count, audit.event_count) == (
        1,
        0,
        1,
    )
    ledger.close()
