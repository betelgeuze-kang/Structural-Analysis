from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_key_enrollment_v1 as enrollment,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_external_key_enrollment_v1 import (
    HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PROOF_DOMAIN_V1,
    HipFgmresExternalKeyEnrollmentPredecessorKeyV1,
    HipFgmresExternalKeyEnrollmentV1Error,
    compile_hip_fgmres_external_key_enrollment_challenge_v1,
    compile_hip_fgmres_external_key_enrollment_proof_message_v1,
    validate_hip_fgmres_external_key_enrollment_challenge_v1,
    validate_hip_fgmres_external_key_enrollment_receipt_v1,
    verify_hip_fgmres_external_key_enrollment_proof_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
)
from structural_analysis.engine_v2.contracts._canonical import sha256_prefixed


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_external_key_enrollment_v1.schema.json"
)
FIXTURE_BYTES_HASH = (
    "sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa"
)
FIXTURE_HASH = "sha256:0f9fb841c2ed6bfe2aef43024d5a496485f06d3d00b95892c7304b7e0dab7eb6"
PREDECESSOR_REGISTRY_HASH = (
    "sha256:4154e2e679ce17b986eac4e90735e518ceddda62751625aa6e254742924b1704"
)


@pytest.fixture(scope="module")
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _challenge_kwargs(public_key: bytes) -> dict[str, Any]:
    return {
        "nonce": b"N" * 32,
        "request_id": "request:enrollment-001",
        "runner_id": "external-runner",
        "key_id": "ed25519:external-runner:v1",
        "key_epoch": 1,
        "predecessor_registry_epoch": 1,
        "predecessor_registry_hash": PREDECESSOR_REGISTRY_HASH,
        "target_registry_epoch": 2,
        "predecessor_key": None,
        "public_key": public_key,
        "public_key_sha256": sha256_prefixed(public_key),
        "allowed_architecture_base": "gfx1100",
        "allowed_suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        "allowed_fixture_registry_bytes_sha256": FIXTURE_BYTES_HASH,
        "allowed_fixture_registry_hash": FIXTURE_HASH,
        "minimum_run_sequence": 1,
        "maximum_run_sequence": 100,
        "valid_from_utc": "2026-07-15T00:00:00Z",
        "valid_until_utc": "2026-08-15T00:00:00Z",
        "runner_declared_key_origin": "runner_declared_isolated_hsm",
        "attestation_digest_sha256": sha256_prefixed(b"unverified-attestation"),
    }


def _compile(private_key: Ed25519PrivateKey, **changes: Any) -> Any:
    kwargs = _challenge_kwargs(_public_key(private_key))
    kwargs.update(changes)
    return compile_hip_fgmres_external_key_enrollment_challenge_v1(**kwargs)


def _signature(private_key: Ed25519PrivateKey, challenge: Any) -> str:
    message = compile_hip_fgmres_external_key_enrollment_proof_message_v1(challenge)
    return base64.b64encode(private_key.sign(message)).decode("ascii")


def test_detached_proof_verifies_only_private_key_possession(
    private_key: Ed25519PrivateKey,
) -> None:
    challenge = _compile(private_key)
    signature = _signature(private_key, challenge)
    receipt = verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=signature,
    )

    assert (
        validate_hip_fgmres_external_key_enrollment_challenge_v1(challenge) is challenge
    )
    assert validate_hip_fgmres_external_key_enrollment_receipt_v1(receipt) is receipt
    assert challenge.to_dict()["predecessor_key"] is None
    assert challenge.target_registry_epoch == challenge.predecessor_registry_epoch + 1
    assert receipt.proof_signature_sha256 == sha256_prefixed(
        base64.b64decode(signature)
    )
    assert receipt.claims.private_key_possession_at_enrollment_verified
    false_claims = receipt.claims.to_dict()
    false_claims.pop("private_key_possession_at_enrollment_verified")
    assert set(false_claims.values()) == {False}


def test_contract_objects_are_immutable_and_no_signing_api_is_exported(
    private_key: Ed25519PrivateKey,
) -> None:
    challenge = _compile(private_key)
    receipt = verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=_signature(private_key, challenge),
    )
    with pytest.raises(FrozenInstanceError):
        challenge.request_id = "request:mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        receipt.receipt_hash = PREDECESSOR_REGISTRY_HASH  # type: ignore[misc]
    assert not any(
        "sign" in name or "private_key" in name for name in enrollment.__all__
    )


def test_external_hsm_message_is_exactly_domain_separated(
    private_key: Ed25519PrivateKey,
) -> None:
    challenge = _compile(private_key)
    message = compile_hip_fgmres_external_key_enrollment_proof_message_v1(challenge)
    assert message.startswith(HIP_FGMRES_EXTERNAL_KEY_ENROLLMENT_PROOF_DOMAIN_V1)
    assert challenge.challenge_hash.encode("ascii") in message


@pytest.mark.parametrize("failure", ["wrong_key", "wrong_domain"])
def test_wrong_key_or_domain_is_rejected(
    private_key: Ed25519PrivateKey,
    failure: str,
) -> None:
    challenge = _compile(private_key)
    if failure == "wrong_key":
        signature_bytes = Ed25519PrivateKey.generate().sign(
            compile_hip_fgmres_external_key_enrollment_proof_message_v1(challenge)
        )
    else:
        signature_bytes = private_key.sign(
            b"wrong-enrollment-domain\0" + challenge.challenge_hash.encode("ascii")
        )
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        verify_hip_fgmres_external_key_enrollment_proof_v1(
            challenge,
            proof_signature_base64=base64.b64encode(signature_bytes).decode("ascii"),
        )
    assert caught.value.code == (
        "hip_fgmres_external_key_enrollment_proof_signature_invalid"
    )


def test_low_order_public_key_is_rejected_before_pop_challenge_issuance() -> None:
    kwargs = _challenge_kwargs(b"\x00" * 32)
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        compile_hip_fgmres_external_key_enrollment_challenge_v1(**kwargs)
    assert caught.value.code == (
        "hip_fgmres_external_key_enrollment_public_key_invalid"
    )


def test_proof_cannot_be_replayed_into_mutated_request_or_nonce(
    private_key: Ed25519PrivateKey,
) -> None:
    original = _compile(private_key)
    signature = _signature(private_key, original)
    mutated = _compile(
        private_key,
        request_id="request:enrollment-002",
        nonce=b"R" * 32,
    )
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        verify_hip_fgmres_external_key_enrollment_proof_v1(
            mutated,
            proof_signature_base64=signature,
        )
    assert caught.value.code == (
        "hip_fgmres_external_key_enrollment_proof_signature_invalid"
    )


def test_rotation_requires_contiguous_nonoverlapping_range_and_new_key() -> None:
    old_key = Ed25519PrivateKey.generate()
    new_key = Ed25519PrivateKey.generate()
    old_public = _public_key(old_key)
    new_public = _public_key(new_key)
    predecessor = HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        public_key_sha256=sha256_prefixed(old_public),
        maximum_run_sequence=100,
    )
    kwargs = _challenge_kwargs(new_public)
    kwargs.update(
        key_id="ed25519:external-runner:v2",
        key_epoch=2,
        predecessor_registry_epoch=2,
        target_registry_epoch=3,
        predecessor_key=predecessor,
        minimum_run_sequence=101,
        maximum_run_sequence=200,
    )
    challenge = compile_hip_fgmres_external_key_enrollment_challenge_v1(**kwargs)
    assert challenge.predecessor_key is predecessor
    assert challenge.to_dict()["predecessor_key"] == predecessor.to_dict()

    for minimum, public_key in ((100, new_public), (101, old_public)):
        invalid = dict(kwargs)
        invalid.update(
            minimum_run_sequence=minimum,
            public_key=public_key,
            public_key_sha256=sha256_prefixed(public_key),
        )
        with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
            compile_hip_fgmres_external_key_enrollment_challenge_v1(**invalid)
        assert caught.value.code == (
            "hip_fgmres_external_key_enrollment_predecessor_key_invalid"
        )


@pytest.mark.parametrize(
    "predecessor",
    [
        HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
            key_id="ed25519:external-runner:v100001",
            key_epoch=100_001,
            public_key_sha256=sha256_prefixed(b"predecessor-key"),
            maximum_run_sequence=100,
        ),
        HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
            key_id="ed25519:external-runner:v1",
            key_epoch=1,
            public_key_sha256=sha256_prefixed(b"predecessor-key"),
            maximum_run_sequence=2**63,
        ),
        HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
            key_id="ed25519:external-runner:v" + "9" * 100_001,
            key_epoch=1,
            public_key_sha256=sha256_prefixed(b"predecessor-key"),
            maximum_run_sequence=100,
        ),
    ],
)
def test_exported_predecessor_rejects_out_of_schema_extents(
    predecessor: HipFgmresExternalKeyEnrollmentPredecessorKeyV1,
) -> None:
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        predecessor.to_dict()
    assert caught.value.code == (
        "hip_fgmres_external_key_enrollment_predecessor_key_invalid"
    )
    assert len(str(caught.value)) <= 512


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"nonce": b"short"}, "hip_fgmres_external_key_enrollment_nonce_invalid"),
        (
            {"key_epoch": True},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"runner_id": "external:runner"},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"target_registry_epoch": 4},
            "hip_fgmres_external_key_enrollment_challenge_semantics_invalid",
        ),
        (
            {"minimum_run_sequence": 2},
            "hip_fgmres_external_key_enrollment_predecessor_key_invalid",
        ),
        (
            {"maximum_run_sequence": 0},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"maximum_run_sequence": 2**63},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"key_epoch": float("inf")},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"valid_until_utc": "2026-07-14T00:00:00Z"},
            "hip_fgmres_external_key_enrollment_challenge_semantics_invalid",
        ),
        (
            {"valid_until_utc": "2026-08-15T00:00:00.1Z"},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"runner_declared_key_origin": "verified_hsm"},
            "hip_fgmres_external_key_enrollment_schema_validation_failed",
        ),
        (
            {"allowed_fixture_registry_hash": PREDECESSOR_REGISTRY_HASH},
            "hip_fgmres_external_key_enrollment_challenge_semantics_invalid",
        ),
    ],
)
def test_compile_challenge_rejects_invalid_semantics(
    private_key: Ed25519PrivateKey,
    changes: dict[str, Any],
    code: str,
) -> None:
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        _compile(private_key, **changes)
    assert caught.value.code == code


def test_challenge_and_receipt_self_hashes_fail_closed(
    private_key: Ed25519PrivateKey,
) -> None:
    challenge = _compile(private_key)
    forged_challenge = replace(
        challenge,
        challenge_hash=PREDECESSOR_REGISTRY_HASH,
    )
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught_challenge:
        validate_hip_fgmres_external_key_enrollment_challenge_v1(forged_challenge)
    assert caught_challenge.value.code == (
        "hip_fgmres_external_key_enrollment_challenge_hash_invalid"
    )

    receipt = verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=_signature(private_key, challenge),
    )
    forged_receipt = replace(receipt, receipt_hash=PREDECESSOR_REGISTRY_HASH)
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught_receipt:
        validate_hip_fgmres_external_key_enrollment_receipt_v1(forged_receipt)
    assert caught_receipt.value.code == (
        "hip_fgmres_external_key_enrollment_receipt_semantics_invalid"
    )


def test_schema_accepts_exact_objects_and_rejects_extra_fields(
    private_key: Ed25519PrivateKey,
) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    challenge = _compile(private_key)
    receipt = verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=_signature(private_key, challenge),
    )
    assert not list(validator.iter_errors(challenge.to_dict()))
    assert not list(validator.iter_errors(receipt.to_dict()))
    forged = receipt.to_dict()
    forged["unexpected"] = True
    assert list(validator.iter_errors(forged))


def test_noncanonical_signature_base64_is_rejected(
    private_key: Ed25519PrivateKey,
) -> None:
    challenge = _compile(private_key)
    signature = _signature(private_key, challenge)
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        verify_hip_fgmres_external_key_enrollment_proof_v1(
            challenge,
            proof_signature_base64=signature.rstrip("="),
        )
    assert caught.value.code == "hip_fgmres_external_key_enrollment_base64_invalid"


def test_schema_failure_message_does_not_amplify_hostile_input(
    private_key: Ed25519PrivateKey,
) -> None:
    hostile_request_id = "r" * 100_000
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        _compile(private_key, request_id=hostile_request_id)
    assert caught.value.code == (
        "hip_fgmres_external_key_enrollment_schema_validation_failed"
    )
    assert hostile_request_id not in str(caught.value)
    assert len(caught.value.message) <= 240
    assert len(str(caught.value)) <= 512


def test_signature_base64_extent_is_rejected_before_decode(
    private_key: Ed25519PrivateKey,
) -> None:
    challenge = _compile(private_key)
    with pytest.raises(HipFgmresExternalKeyEnrollmentV1Error) as caught:
        verify_hip_fgmres_external_key_enrollment_proof_v1(
            challenge,
            proof_signature_base64="A" * 1_000_000,
        )
    assert caught.value.code == "hip_fgmres_external_key_enrollment_base64_invalid"
    assert len(str(caught.value)) <= 512
