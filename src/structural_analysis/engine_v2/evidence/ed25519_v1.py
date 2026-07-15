"""Strict Ed25519 verification helpers.

Only verification is available in the product package.  Private-key loading
and signing deliberately remain runner/deployment concerns.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ED25519_ALGORITHM_V1 = "Ed25519"

_ED25519_FIELD_MODULUS_V1 = 2**255 - 19
_ED25519_SUBGROUP_ORDER_V1 = 2**252 + 27742317777372353535851937790883648493
_ED25519_CURVE_D_V1 = (
    -121665
    * pow(121666, _ED25519_FIELD_MODULUS_V1 - 2, _ED25519_FIELD_MODULUS_V1)
    % _ED25519_FIELD_MODULUS_V1
)
_ED25519_SQRT_MINUS_ONE_V1 = pow(
    2,
    (_ED25519_FIELD_MODULUS_V1 - 1) // 4,
    _ED25519_FIELD_MODULUS_V1,
)
_ED25519_IDENTITY_V1 = (0, 1, 1, 0)


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
    expected_encoded_extent = 4 * ((expected_byte_count + 2) // 3)
    if len(value) != expected_encoded_extent:
        _fail("ed25519_base64_noncanonical", path)
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


def validate_ed25519_public_key_v1(public_key: bytes) -> bytes:
    """Require one canonical, non-identity, prime-order Ed25519 point."""

    if type(public_key) is not bytes or len(public_key) != 32:
        _fail("ed25519_public_key_invalid", "/public_key")
    if not _is_valid_prime_order_ed25519_point_v1(public_key):
        _fail(
            "ed25519_public_key_invalid",
            "/public_key",
            "point_not_in_prime_order_subgroup",
        )
    return public_key


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
        validate_ed25519_public_key_v1(public_key)
    except Ed25519EvidenceV1Error as exc:
        # Preserve the existing verify API's fail-closed signature error for
        # structurally sized but unsafe public keys.
        _fail("ed25519_signature_invalid", "/signature", exc.code)
    if (
        not _is_valid_prime_order_ed25519_point_v1(signature[:32])
        or int.from_bytes(signature[32:], "little") >= _ED25519_SUBGROUP_ORDER_V1
    ):
        _fail("ed25519_signature_invalid", "/signature")
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        _fail("ed25519_signature_invalid", "/signature", type(exc).__name__)


@lru_cache(maxsize=256)
def _is_valid_prime_order_ed25519_point_v1(encoded: bytes) -> bool:
    """Validate RFC 8032 decoding plus membership in the order-L subgroup."""

    point = _decode_ed25519_point_v1(encoded)
    return (
        point is not None
        and not _ed25519_point_is_identity_v1(point)
        and _ed25519_point_is_identity_v1(
            _multiply_ed25519_point_v1(_ED25519_SUBGROUP_ORDER_V1, point)
        )
    )


def _decode_ed25519_point_v1(
    encoded: bytes,
) -> tuple[int, int, int, int] | None:
    """Decode one canonical compressed Edwards point as specified by RFC 8032."""

    if type(encoded) is not bytes or len(encoded) != 32:
        return None
    value = int.from_bytes(encoded, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    modulus = _ED25519_FIELD_MODULUS_V1
    if y >= modulus:
        return None
    y_squared = y * y % modulus
    numerator = (y_squared - 1) % modulus
    denominator = (_ED25519_CURVE_D_V1 * y_squared + 1) % modulus
    if denominator == 0:
        return None
    x_squared = numerator * pow(denominator, modulus - 2, modulus) % modulus
    x = pow(x_squared, (modulus + 3) // 8, modulus)
    if (x * x - x_squared) % modulus != 0:
        x = x * _ED25519_SQRT_MINUS_ONE_V1 % modulus
    if (x * x - x_squared) % modulus != 0 or (x == 0 and sign == 1):
        return None
    if (x & 1) != sign:
        x = modulus - x
    return (x, y, 1, x * y % modulus)


def _add_ed25519_points_v1(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    modulus = _ED25519_FIELD_MODULUS_V1
    a = (left[1] - left[0]) * (right[1] - right[0]) % modulus
    b = (left[1] + left[0]) * (right[1] + right[0]) % modulus
    c = 2 * _ED25519_CURVE_D_V1 * left[3] * right[3] % modulus
    d = 2 * left[2] * right[2] % modulus
    e = (b - a) % modulus
    f = (d - c) % modulus
    g = (d + c) % modulus
    h = (b + a) % modulus
    return (e * f % modulus, g * h % modulus, f * g % modulus, e * h % modulus)


def _multiply_ed25519_point_v1(
    scalar: int,
    point: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    result = _ED25519_IDENTITY_V1
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _add_ed25519_points_v1(result, addend)
        addend = _add_ed25519_points_v1(addend, addend)
        scalar >>= 1
    return result


def _ed25519_point_is_identity_v1(point: tuple[int, int, int, int]) -> bool:
    modulus = _ED25519_FIELD_MODULUS_V1
    return (
        point[2] % modulus != 0
        and point[0] % modulus == 0
        and (point[1] - point[2]) % modulus == 0
    )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise Ed25519EvidenceV1Error(code, path, message)


__all__ = [
    "ED25519_ALGORITHM_V1",
    "Ed25519EvidenceV1Error",
    "decode_canonical_base64_v1",
    "validate_ed25519_public_key_v1",
    "verify_ed25519_signature_v1",
]
