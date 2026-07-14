"""Strict Ed25519 verification helpers.

Only verification is available in the product package.  Private-key loading
and signing deliberately remain runner/deployment concerns.
"""

from __future__ import annotations

import base64
import binascii
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ED25519_ALGORITHM_V1 = "Ed25519"


class Ed25519EvidenceV1Error(ValueError):
    """Stable fail-closed Ed25519/base64 verification error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


def decode_canonical_base64_v1(
    value: str,
    *,
    expected_byte_count: int,
    path: str,
) -> bytes:
    """Decode standard padded base64 and reject alternate encodings."""

    if (
        type(value) is not str
        or type(expected_byte_count) is not int
        or expected_byte_count < 0
        or type(path) is not str
        or not path.startswith("/")
    ):
        _fail("ed25519_base64_argument_invalid", path if type(path) is str else "/")
    try:
        encoded = value.encode("ascii", errors="strict")
        decoded = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        _fail("ed25519_base64_invalid", path, type(exc).__name__)
    if (
        len(decoded) != expected_byte_count
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        _fail("ed25519_base64_noncanonical", path)
    return decoded


def verify_ed25519_signature_v1(
    *,
    public_key: bytes,
    signature_base64: str,
    message: bytes,
) -> None:
    """Verify one exact 32-byte-key/64-byte-signature Ed25519 message."""

    if type(public_key) is not bytes or len(public_key) != 32:
        _fail("ed25519_public_key_invalid", "/public_key")
    if type(message) is not bytes or not message:
        _fail("ed25519_message_invalid", "/message")
    signature = decode_canonical_base64_v1(
        signature_base64,
        expected_byte_count=64,
        path="/signature",
    )
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        _fail("ed25519_signature_invalid", "/signature", type(exc).__name__)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise Ed25519EvidenceV1Error(code, path, message)


__all__ = [
    "ED25519_ALGORITHM_V1",
    "Ed25519EvidenceV1Error",
    "decode_canonical_base64_v1",
    "verify_ed25519_signature_v1",
]
