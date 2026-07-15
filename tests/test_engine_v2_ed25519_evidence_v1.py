from __future__ import annotations

import base64

import pytest

from structural_analysis.engine_v2.evidence.ed25519_v1 import (
    Ed25519EvidenceV1Error,
    decode_canonical_base64_v1,
    validate_ed25519_public_key_v1,
    verify_ed25519_signature_v1,
)


def test_rfc8032_vector_two_verifies_exact_message() -> None:
    public_key = bytes.fromhex(
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
    )
    signature = bytes.fromhex(
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
    )
    verify_ed25519_signature_v1(
        public_key=public_key,
        signature_base64=base64.b64encode(signature).decode("ascii"),
        message=b"\x72",
    )


@pytest.mark.parametrize(
    ("value", "expected_byte_count"),
    [
        ("AQ", 1),
        ("AQ==\n", 1),
        ("-Q==", 1),
        ("AQ==", 2),
    ],
)
def test_base64_rejects_noncanonical_or_wrong_extent(
    value: str,
    expected_byte_count: int,
) -> None:
    with pytest.raises(Ed25519EvidenceV1Error):
        decode_canonical_base64_v1(
            value,
            expected_byte_count=expected_byte_count,
            path="/test",
        )


def test_base64_extent_is_rejected_before_decoder_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_decode(*_: object, **__: object) -> bytes:
        raise AssertionError("decoder must not receive an impossible extent")

    monkeypatch.setattr(base64, "b64decode", forbidden_decode)
    with pytest.raises(Ed25519EvidenceV1Error) as caught:
        decode_canonical_base64_v1(
            "A" * 1_000_000,
            expected_byte_count=32,
            path="/test",
        )
    assert caught.value.code == "ed25519_base64_noncanonical"


def test_signature_tamper_and_wrong_key_fail_closed() -> None:
    signature = base64.b64encode(b"\x00" * 64).decode("ascii")
    with pytest.raises(Ed25519EvidenceV1Error) as caught:
        verify_ed25519_signature_v1(
            public_key=b"\x00" * 32,
            signature_base64=signature,
            message=b"domain-separated-message",
        )
    assert caught.value.code == "ed25519_signature_invalid"


@pytest.mark.parametrize(
    "public_key",
    [
        b"\x00" * 32,
        b"\x01" + b"\x00" * 31,
        (2**255 - 19).to_bytes(32, "little"),
        # RFC 8032 vector-two public point plus the order-two torsion point.
        bytes.fromhex(
            "b0bfe83c17bc76a56d48f558b2e481436367d330d13b69733f32aa0ed50b99f3"
        ),
    ],
)
def test_low_order_identity_and_noncanonical_public_keys_are_rejected(
    public_key: bytes,
) -> None:
    with pytest.raises(Ed25519EvidenceV1Error) as caught:
        validate_ed25519_public_key_v1(public_key)
    assert caught.value.code == "ed25519_public_key_invalid"
