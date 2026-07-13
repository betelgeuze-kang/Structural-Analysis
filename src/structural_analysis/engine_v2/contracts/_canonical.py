"""Canonical hashing and immutable-array helpers for Engine v2 contracts.

The helpers in this module deliberately have no knowledge of a particular IR.
They define the byte and JSON rules shared by ExecutionPlan, StateIR, and
ResultIR receipts.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from typing import Any

import numpy as np


class CanonicalContractError(ValueError):
    """Raised when a value cannot be represented by the canonical contract."""


def canonical_json_bytes(payload: Any) -> bytes:
    """Return deterministic UTF-8 JSON after rejecting non-finite values."""

    normalized = _normalize_json_value(payload, path="/")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_hash(payload: Any) -> str:
    """Return the prefixed SHA-256 of :func:`canonical_json_bytes`."""

    return sha256_prefixed(canonical_json_bytes(payload))


def sha256_prefixed(data: bytes | bytearray | memoryview) -> str:
    """Hash bytes using the repository-wide ``sha256:<hex>`` spelling."""

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def immutable_array(value: Any, *, dtype: Any) -> np.ndarray:
    """Copy a value into an immutable, C-contiguous, little-endian array.

    The returned array is backed by a ``bytes`` object.  Consequently callers
    cannot re-enable its write flag, unlike an owned array with only
    ``writeable=False`` applied to it.
    """

    target_dtype = np.dtype(dtype)
    if target_dtype.hasobject:
        raise CanonicalContractError("Object arrays are not contract-safe.")
    if target_dtype.itemsize > 1:
        target_dtype = target_dtype.newbyteorder("<")
    try:
        contiguous = np.ascontiguousarray(value, dtype=target_dtype)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalContractError(
            f"Value cannot be represented as {target_dtype.str}."
        ) from exc
    immutable_bytes = contiguous.tobytes(order="C")
    return np.frombuffer(immutable_bytes, dtype=target_dtype).reshape(contiguous.shape)


def array_data_hash(array: np.ndarray) -> str:
    """Hash the exact C-order bytes of an array, excluding metadata."""

    checked = _contract_array(array)
    return sha256_prefixed(memoryview(checked).cast("B"))


def raw_array_hash(array: np.ndarray) -> str:
    """Compatibility alias that makes raw-byte hash intent explicit."""

    return array_data_hash(array)


def array_content_hash(metadata: Any, array: np.ndarray) -> str:
    """Hash canonical metadata and exact array bytes as one artifact."""

    checked = _contract_array(array)
    digest = hashlib.sha256()
    digest.update(canonical_json_bytes(metadata))
    digest.update(b"\0")
    digest.update(memoryview(checked).cast("B"))
    return f"sha256:{digest.hexdigest()}"


def has_immutable_bytes_backing(array: np.ndarray) -> bool:
    """Return whether an array ultimately references immutable ``bytes``."""

    if not isinstance(array, np.ndarray) or array.flags.writeable:
        return False
    base: Any = array
    seen: set[int] = set()
    while isinstance(base, np.ndarray):
        identifier = id(base)
        if identifier in seen:  # pragma: no cover - defensive against exotic views
            return False
        seen.add(identifier)
        base = base.base
    return isinstance(base, bytes)


def _contract_array(array: np.ndarray) -> np.ndarray:
    if not isinstance(array, np.ndarray):
        raise CanonicalContractError("Expected a NumPy array.")
    if array.dtype.hasobject:
        raise CanonicalContractError("Object arrays are not contract-safe.")
    if not array.flags.c_contiguous:
        raise CanonicalContractError("Contract arrays must be C-contiguous.")
    return array


def _normalize_json_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if not math.isfinite(result):
            raise CanonicalContractError(f"Non-finite number at {path}.")
        return 0.0 if result == 0.0 else result
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return _normalize_json_value(value.tolist(), path=path)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        if any(not isinstance(key, str) for key in value):
            raise CanonicalContractError(f"Non-string object key at {path}.")
        for key in sorted(value):
            child_path = f"{path.rstrip('/')}/{key}"
            normalized[key] = _normalize_json_value(value[key], path=child_path)
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json_value(item, path=f"{path.rstrip('/')}/{index}")
            for index, item in enumerate(value)
        ]
    raise CanonicalContractError(
        f"Unsupported canonical JSON value {type(value).__name__} at {path}."
    )
