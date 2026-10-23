"""Canonical hashing and immutable-array helpers for Engine v2 contracts.

The helpers in this module deliberately have no knowledge of a particular IR.
They define the byte and JSON rules shared by the core ExecutionPlan and
StateIR contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import hashlib
import json
import math
from typing import Any

import numpy as np


class CanonicalContractError(ValueError):
    """Raised when a value cannot be represented by the canonical contract."""


def canonical_json_bytes(payload: Any) -> bytes:
    """Return deterministic UTF-8 JSON after rejecting non-finite values."""

    normalized = _USE_LEGACY_NORMALIZATION
    if (
        _normalize_json_value is _NORMALIZER_REFERENCE
        and _normalize_json_value.__code__ is _NORMALIZER_CODE
        and math.isfinite is _ISFINITE_REFERENCE
    ):
        try:
            normalized = _normalize_plain_json_value(payload, depth=0)
        except (_PlainNormalizationFallback, RecursionError):
            pass
    # Keep the reference call outside the except block so its exceptions do
    # not acquire an internal speculative-traversal exception as context.
    if normalized is _USE_LEGACY_NORMALIZATION:
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
    """Losslessly copy a value into a canonical immutable numeric array.

    The returned array is backed by a ``bytes`` object.  Consequently callers
    cannot re-enable its write flag, unlike an owned array with only
    ``writeable=False`` applied to it.  Boolean/numeric kind changes and
    value-losing narrowing conversions fail closed.
    """

    target_dtype = np.dtype(dtype)
    if target_dtype.hasobject or target_dtype.kind not in "biufc":
        raise CanonicalContractError(
            "Only boolean and real/complex numeric arrays are contract-safe."
        )
    if target_dtype.itemsize > 1:
        target_dtype = target_dtype.newbyteorder("<")
    try:
        source = np.asarray(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalContractError(
            f"Value cannot be represented as {target_dtype.str}."
        ) from exc
    if source.dtype.hasobject or source.dtype.kind not in "biufc":
        raise CanonicalContractError(
            "Only boolean and real/complex numeric values are contract-safe."
        )
    _validate_lossless_array_cast(source, target_dtype)
    try:
        contiguous = np.ascontiguousarray(source, dtype=target_dtype)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalContractError(
            f"Value cannot be represented as {target_dtype.str}."
        ) from exc
    if contiguous.dtype.kind in "fc":
        if not np.all(np.isfinite(contiguous)):
            raise CanonicalContractError("Contract arrays must contain finite values.")
        if source.size:
            with np.errstate(invalid="ignore", over="ignore"):
                roundtrip = contiguous.astype(source.dtype)
            if not np.array_equal(roundtrip, source):
                raise CanonicalContractError(
                    f"Conversion from {source.dtype.str} to {target_dtype.str} "
                    "would change a value."
                )
        contiguous = contiguous.copy(order="C")
        if contiguous.dtype.kind == "c":
            contiguous.real[contiguous.real == 0] = 0
            contiguous.imag[contiguous.imag == 0] = 0
        else:
            contiguous[contiguous == 0] = 0
    immutable_bytes = contiguous.tobytes(order="C")
    return np.frombuffer(immutable_bytes, dtype=target_dtype).reshape(contiguous.shape)


def _validate_lossless_array_cast(source: np.ndarray, target: np.dtype[Any]) -> None:
    if source.size == 0:
        return
    source_kind = source.dtype.kind
    target_kind = target.kind
    if target_kind == "b":
        if source_kind != "b":
            raise CanonicalContractError(
                "Boolean arrays cannot be created from non-boolean values."
            )
        return
    if target_kind in "iu":
        if source_kind not in "iu":
            raise CanonicalContractError(
                "Integer arrays require integer, non-boolean source values."
            )
        limits = np.iinfo(target)
        if int(source.min()) < int(limits.min) or int(source.max()) > int(limits.max):
            raise CanonicalContractError(
                f"Integer values do not fit canonical dtype {target.str}."
            )
        return
    if target_kind == "f" and source_kind not in "iuf":
        raise CanonicalContractError(
            "Real arrays require integer or real floating-point source values."
        )
    if target_kind == "c" and source_kind not in "iufc":
        raise CanonicalContractError(
            "Complex arrays require integer, real, or complex source values."
        )


def array_data_hash(array: np.ndarray) -> str:
    """Hash the exact C-order bytes of an array, excluding metadata."""

    checked = _contract_array(array)
    raw_bytes: bytes | memoryview = (
        b"" if checked.nbytes == 0 else memoryview(checked).cast("B")
    )
    return sha256_prefixed(raw_bytes)


def raw_array_hash(array: np.ndarray) -> str:
    """Compatibility alias that makes raw-byte hash intent explicit."""

    return array_data_hash(array)


def array_content_hash(metadata: Any, array: np.ndarray) -> str:
    """Hash canonical metadata and exact array bytes as one artifact."""

    checked = _contract_array(array)
    digest = hashlib.sha256()
    digest.update(_array_metadata_bytes(metadata))
    digest.update(b"\0")
    raw_bytes: bytes | memoryview = (
        b"" if checked.nbytes == 0 else memoryview(checked).cast("B")
    )
    digest.update(raw_bytes)
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


class _PlainNormalizationFallback(Exception):
    """Abort speculative traversal without invoking custom value behavior."""


_PLAIN_NORMALIZATION_MAX_DEPTH = 64
_USE_LEGACY_NORMALIZATION = object()
_NORMALIZER_REFERENCE = _normalize_json_value
_NORMALIZER_CODE = _normalize_json_value.__code__
_ISFINITE_REFERENCE = math.isfinite


def _normalize_plain_json_value(value: Any, depth: int) -> Any:
    """Copy exact builtins, otherwise request a complete legacy traversal."""

    value_type = type(value)
    if value is None or value_type is str or value_type is bool or value_type is int:
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise _PlainNormalizationFallback
        return 0.0 if value == 0.0 else value
    if depth >= _PLAIN_NORMALIZATION_MAX_DEPTH:
        raise _PlainNormalizationFallback
    if value_type is dict:
        if any(type(key) is not str for key in value):
            raise _PlainNormalizationFallback
        return {
            key: _normalize_plain_json_value(value[key], depth + 1)
            for key in sorted(value)
        }
    if value_type is list or value_type is tuple:
        return [_normalize_plain_json_value(item, depth + 1) for item in value]
    raise _PlainNormalizationFallback


def _serialization_implementation(function: Any) -> tuple[Any, ...]:
    """Freeze the small, explicit serializer call graph, without model state."""
    return (
        function,
        getattr(function, "__code__", None),
        getattr(function, "__defaults__", None),
        (getattr(function, "__kwdefaults__", None) or {}).copy() or None,
        tuple(
            id(cell.cell_contents)
            for cell in (getattr(function, "__closure__", None) or ())
        ),
    )


def _serialization_bindings(
    namespace: Mapping[str, Any], names: tuple[str, ...]
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (namespace, name, *_serialization_implementation(namespace.get(name)))
        for name in names
    )


def _serialization_bindings_unchanged(bindings: tuple[tuple[Any, ...], ...]) -> bool:
    # Flatten once at import. On each use, compare the live binding and Python
    # function attributes directly instead of rebuilding per-function tokens.
    for namespace, name, expected, code, defaults, kwdefaults, closure in bindings:
        function = namespace.get(name)
        if function is None or function is not expected:
            return False
        if code is not None:
            if (
                function.__code__ is not code
                or function.__defaults__ is not defaults
                or (function.__kwdefaults__ or None) != kwdefaults
            ):
                return False
            if (
                closure
                and tuple(id(cell.cell_contents) for cell in function.__closure__)
                != closure
            ):
                return False
    return True


# These are import-time immutable implementation descriptions. The value cache
# below changes no module-level registry, including the Jacobian source guard.
_JSON_MODULE = json
_JSON_ENCODER_MODULE = json.encoder
_HASHLIB_MODULE = hashlib
_CANONICAL_CACHE_BINDINGS = _serialization_bindings(
    globals(),
    (
        "canonical_json_bytes",
        "canonical_hash",
        "sha256_prefixed",
        "_normalize_json_value",
        "_normalize_plain_json_value",
    ),
) + tuple(
    binding
    for owner, names in (
        (json, ("dumps", "JSONEncoder")),
        (json.JSONEncoder, ("__init__", "encode", "iterencode", "default")),
        (
            json.encoder,
            (
                "c_make_encoder",
                "_make_iterencode",
                "encode_basestring",
                "encode_basestring_ascii",
            ),
        ),
        (hashlib, ("sha256",)),
    )
    for binding in _serialization_bindings(vars(owner), names)
)


def _canonical_cache_eligible() -> bool:
    """Do not reuse old bytes/digests after explicit serializer changes."""
    if (
        json is not _JSON_MODULE
        or getattr(json, "encoder", None) is not _JSON_ENCODER_MODULE
        or hashlib is not _HASHLIB_MODULE
        or math.isfinite is not _ISFINITE_REFERENCE
    ):
        return False
    return _serialization_bindings_unchanged(_CANONICAL_CACHE_BINDINGS)


_ARRAY_METADATA_STRING_FIELDS = frozenset(
    (
        "name",
        "dtype",
        "layout",
        "byte_order",
        "storage_profile",
        "unit_profile",
        "artifact_uri",
        "state_hash",
        "equation_order_hash",
        "equation_scope",
        "owner_kind",
        "owner_hash",
        "engineering_result_id",
        "source_numerical_result_hash",
        "recovery_operator_hash",
    )
)


def _array_metadata_snapshot(metadata: Any) -> tuple[tuple[str, Any], ...] | None:
    """Copy only bounded, known descriptor fields; all other JSON stays legacy.

    Types are fixed by each field, so True/1/1.0 cannot share a cache key.
    Shape list/tuple spelling may share one key: both canonically encode a list.
    """
    if type(metadata) is not dict or not 3 <= len(metadata) <= 20:
        return None
    if any(type(key) is not str for key in metadata):
        return None
    if len(metadata) == 5:
        name, dtype, shape_value, layout, length = (
            metadata.get("name"),
            metadata.get("dtype"),
            metadata.get("shape"),
            metadata.get("layout"),
            metadata.get("byte_length"),
        )
        shape: Any = shape_value
        if (
            type(name) is str
            and type(dtype) is str
            and type(layout) is str
            and type(length) is int
            and length.bit_length() <= 64
            and type(shape) in (list, tuple)
            and len(shape) <= 32
            and len(name) + len(dtype) + len(layout) <= 4096
            and all(type(item) is int and item.bit_length() <= 64 for item in shape)
        ):
            # The common descriptor has a fixed canonical key order and no
            # recursive object walk, generic field dispatch, or sorting.
            return (
                ("byte_length", length),
                ("dtype", dtype),
                ("layout", layout),
                ("name", name),
                ("shape", tuple(shape)),
            )
    if not {"name", "dtype", "shape"}.issubset(metadata):
        return None
    result: list[tuple[str, Any]] = []
    characters = 0
    for key in sorted(metadata):
        value = metadata[key]
        if key in _ARRAY_METADATA_STRING_FIELDS:
            if type(value) is not str:
                return None
            characters += len(value)
            if characters > 4096:
                return None
        elif key == "byte_length":
            if type(value) is not int or value.bit_length() > 64:
                return None
        elif key == "shape":
            if type(value) not in (list, tuple) or len(value) > 32:
                return None
            if any(type(item) is not int or item.bit_length() > 64 for item in value):
                return None
            value = tuple(value)
        else:
            return None
        result.append((key, value))
    return tuple(result)


@lru_cache(maxsize=128)
def _cached_array_metadata_bytes(snapshot: tuple[tuple[str, Any], ...]) -> bytes:
    return canonical_json_bytes(dict(snapshot))


def _array_metadata_bytes(metadata: Any) -> bytes:
    snapshot = _array_metadata_snapshot(metadata)
    if snapshot is not None and _canonical_cache_eligible():
        return _cached_array_metadata_bytes(snapshot)
    return canonical_json_bytes(metadata)
