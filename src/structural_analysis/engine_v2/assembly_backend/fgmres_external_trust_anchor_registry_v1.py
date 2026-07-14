"""Package-owned Ed25519 trust anchors for external gfx1100 evidence.

The checked-in registry is intentionally empty.  A future executor key must be
added by changing the package resource and the code-anchored raw-byte digest;
an evidence envelope can never introduce its own trust root.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
import json
import math
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.evidence.ed25519_v1 import (
    decode_canonical_base64_v1,
)

from .fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    load_hip_fgmres_fixture_registry_v1,
)


HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-trust-anchor-registry.v1"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V1 = (
    "phase0_external_gfx1100_ed25519_trust_anchors"
)
HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V1 = (
    "package_owned_ed25519_verification_keys_non_promoting"
)

_RESOURCE_PACKAGE = (
    "structural_analysis.engine_v2.assembly_backend.fixtures."
    "fgmres_external_trust_anchors_v1"
)
_REGISTRY_RESOURCE = "registry.v1.json"
_SCHEMA_RESOURCE = "hip_fgmres_external_trust_anchor_registry_v1.schema.json"
_SCHEMA_RESOURCE_BYTES_SHA256 = (
    "sha256:d95e060303cb777970c198fd3a5e2aa845e31b7d8d3ea83e83ba8aad70ba7ec9"
)
_REGISTRY_RESOURCE_BYTES_SHA256 = (
    "sha256:f39fc9a2a932b8e92be028ee87d036445cdcb33f244f10af85ee9127290e61c6"
)


class HipFgmresExternalTrustAnchorRegistryV1Error(RuntimeError):
    """Stable fail-closed package trust-registry error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorV1:
    key_id: str
    key_epoch: int
    status: str
    runner_id: str
    public_key_base64: str
    public_key_sha256: str
    allowed_architecture_base: str
    allowed_suite_id: str
    allowed_fixture_registry_bytes_sha256: str
    allowed_fixture_registry_hash: str
    minimum_run_sequence: int
    maximum_run_sequence: int | None
    valid_from_utc: str
    valid_until_utc: str | None
    revoked_at_utc: str | None
    revocation_reason: str | None

    @property
    def public_key_bytes(self) -> bytes:
        return decode_canonical_base64_v1(
            self.public_key_base64,
            expected_byte_count=32,
            path="/keys/public_key_base64",
        )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalTrustAnchorRegistryResultV1:
    registry_bytes_sha256: str
    registry_hash: str
    registry_epoch: int
    keys: tuple[HipFgmresExternalTrustAnchorV1, ...]
    receipt_hash: str

    @property
    def active_key_count(self) -> int:
        return sum(key.status == "active" for key in self.keys)

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_trust_anchor_registry_result_v1(self)
        return _result_payload(self, include_hash=True)


class _DuplicateKeyError(ValueError):
    pass


def load_hip_fgmres_external_trust_anchor_registry_v1() -> (
    HipFgmresExternalTrustAnchorRegistryResultV1
):
    """Load only the immutable package registry; no caller path exists."""

    return _TRUST_REGISTRY_LOADER_AUTHORITY()


def validate_hip_fgmres_external_trust_anchor_registry_result_v1(
    result: HipFgmresExternalTrustAnchorRegistryResultV1,
) -> HipFgmresExternalTrustAnchorRegistryResultV1:
    if type(result) is not HipFgmresExternalTrustAnchorRegistryResultV1:
        _fail("hip_fgmres_external_trust_registry_result_type_invalid", "/")
    if (
        type(result.keys) is not tuple
        or any(type(key) is not HipFgmresExternalTrustAnchorV1 for key in result.keys)
        or result.registry_bytes_sha256 != _REGISTRY_RESOURCE_BYTES_SHA256
    ):
        _fail("hip_fgmres_external_trust_registry_result_invalid", "/")
    for index, key in enumerate(result.keys):
        _validate_key(key, path=f"/keys/{index}")
    expected = _TRUST_REGISTRY_LOADER_AUTHORITY()
    if _result_payload(result, include_hash=False) != _result_payload(
        expected,
        include_hash=False,
    ):
        _fail("hip_fgmres_external_trust_registry_replay_mismatch", "/")
    if result.receipt_hash != canonical_hash(
        _result_payload(result, include_hash=False)
    ):
        _fail(
            "hip_fgmres_external_trust_registry_receipt_hash_invalid", "/receipt_hash"
        )
    return result


def _load_package_registry() -> HipFgmresExternalTrustAnchorRegistryResultV1:
    raw = _read_fixed_resource()
    if sha256_prefixed(raw) != _REGISTRY_RESOURCE_BYTES_SHA256:
        _fail("hip_fgmres_external_trust_registry_resource_hash_mismatch", "/registry")
    manifest = _parse_strict_object(raw, path="/registry")
    _validate_schema(manifest)
    declared_hash = manifest["registry_hash"]
    hash_payload = dict(manifest)
    del hash_payload["registry_hash"]
    if declared_hash != canonical_hash(hash_payload):
        _fail(
            "hip_fgmres_external_trust_registry_content_hash_mismatch", "/registry_hash"
        )
    if (
        manifest["schema_version"]
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V1
        or manifest["capability_profile"]
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V1
        or manifest["evidence_scope"]
        != HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V1
    ):
        _fail("hip_fgmres_external_trust_registry_semantics_invalid", "/")
    keys = tuple(HipFgmresExternalTrustAnchorV1(**row) for row in manifest["keys"])
    if len({key.key_id for key in keys}) != len(keys):
        _fail("hip_fgmres_external_trust_registry_key_id_duplicate", "/keys")
    if len({(key.runner_id, key.key_epoch) for key in keys}) != len(keys):
        _fail("hip_fgmres_external_trust_registry_runner_epoch_duplicate", "/keys")
    if len({key.public_key_sha256 for key in keys}) != len(keys):
        _fail("hip_fgmres_external_trust_registry_public_key_duplicate", "/keys")
    for index, key in enumerate(keys):
        _validate_key(key, path=f"/keys/{index}")
    draft = HipFgmresExternalTrustAnchorRegistryResultV1(
        registry_bytes_sha256=_REGISTRY_RESOURCE_BYTES_SHA256,
        registry_hash=declared_hash,
        registry_epoch=manifest["registry_epoch"],
        keys=keys,
        receipt_hash="sha256:" + "0" * 64,
    )
    return HipFgmresExternalTrustAnchorRegistryResultV1(
        registry_bytes_sha256=draft.registry_bytes_sha256,
        registry_hash=draft.registry_hash,
        registry_epoch=draft.registry_epoch,
        keys=draft.keys,
        receipt_hash=canonical_hash(_result_payload(draft, include_hash=False)),
    )


def _validate_key(key: HipFgmresExternalTrustAnchorV1, *, path: str) -> None:
    public_key = key.public_key_bytes
    fixture_registry = load_hip_fgmres_fixture_registry_v1()
    valid_from = _parse_utc(key.valid_from_utc, path=f"{path}/valid_from_utc")
    valid_until = (
        None
        if key.valid_until_utc is None
        else _parse_utc(key.valid_until_utc, path=f"{path}/valid_until_utc")
    )
    revoked_at = (
        None
        if key.revoked_at_utc is None
        else _parse_utc(key.revoked_at_utc, path=f"{path}/revoked_at_utc")
    )
    if (
        sha256_prefixed(public_key) != key.public_key_sha256
        or key.key_id != f"ed25519:{key.runner_id}:v{key.key_epoch}"
        or key.allowed_architecture_base != "gfx1100"
        or key.allowed_suite_id != HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1
        or key.allowed_fixture_registry_bytes_sha256
        != fixture_registry.registry_bytes_sha256
        or key.allowed_fixture_registry_hash != fixture_registry.registry_hash
        or (
            key.maximum_run_sequence is not None
            and key.maximum_run_sequence < key.minimum_run_sequence
        )
        or (valid_until is not None and valid_until <= valid_from)
        or (
            key.status == "active"
            and (revoked_at is not None or key.revocation_reason is not None)
        )
        or (
            key.status == "revoked"
            and (revoked_at is None or key.revocation_reason is None)
        )
    ):
        _fail("hip_fgmres_external_trust_registry_key_invalid", path)


def _parse_utc(value: str, *, path: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail("hip_fgmres_external_trust_registry_timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        _fail("hip_fgmres_external_trust_registry_timestamp_invalid", path, str(exc))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("hip_fgmres_external_trust_registry_timestamp_invalid", path)
    return parsed


def _result_payload(
    result: HipFgmresExternalTrustAnchorRegistryResultV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V1,
        "evidence_scope": HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V1,
        "registry_bytes_sha256": result.registry_bytes_sha256,
        "registry_hash": result.registry_hash,
        "registry_epoch": result.registry_epoch,
        "keys": [key.to_dict() for key in result.keys],
        "key_count": len(result.keys),
        "active_key_count": result.active_key_count,
        "claims": {
            "package_owned_trust_anchors_loaded": True,
            "envelope_supplied_public_keys_trusted": False,
            "private_keys_packaged": False,
            "external_gfx1100_signed_cells": 0,
            "durable_replay_protection": False,
            "promotion_eligible": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["receipt_hash"] = result.receipt_hash
    return payload


def _read_fixed_resource() -> bytes:
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(_REGISTRY_RESOURCE)
    if not resource.is_file():
        _fail("hip_fgmres_external_trust_registry_resource_missing", "/registry")
    try:
        return resource.read_bytes()
    except OSError as exc:
        _fail(
            "hip_fgmres_external_trust_registry_resource_read_failed",
            "/registry",
            str(exc),
        )


def _parse_strict_object(raw: bytes, *, path: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_external_trust_registry_json_bom_forbidden", path)

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKeyError(key)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
        _reject_nonfinite(payload, path=path)
    except _DuplicateKeyError as exc:
        _fail("hip_fgmres_external_trust_registry_json_duplicate_key", path, str(exc))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail("hip_fgmres_external_trust_registry_json_invalid", path, str(exc))
    if type(payload) is not dict:
        _fail("hip_fgmres_external_trust_registry_json_root_invalid", path)
    return payload


def _reject_nonfinite(value: Any, *, path: str) -> None:
    if type(value) is float and not math.isfinite(value):
        _fail("hip_fgmres_external_trust_registry_json_nonfinite", path)
    if type(value) is dict:
        for key, item in value.items():
            _reject_nonfinite(item, path=f"{path}/{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_nonfinite(item, path=f"{path}/{index}")


def _validate_schema(manifest: dict[str, Any]) -> None:
    schema_raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_bytes()
    )
    if sha256_prefixed(schema_raw) != _SCHEMA_RESOURCE_BYTES_SHA256:
        _fail("hip_fgmres_external_trust_registry_schema_hash_mismatch", "/schema")
    schema = _parse_strict_object(schema_raw, path="/schema")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        _fail("hip_fgmres_external_trust_registry_schema_invalid", "/schema", str(exc))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(
            "hip_fgmres_external_trust_registry_schema_validation_failed",
            location,
            error.message,
        )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalTrustAnchorRegistryV1Error(code, path, message)


def _make_authoritative_loader(
    loader: Any = _load_package_registry,
) -> Any:
    """Capture the fixed loader so public-name rebinding cannot add trust."""

    return loader


_TRUST_REGISTRY_LOADER_AUTHORITY = _make_authoritative_loader()
del _make_authoritative_loader


__all__ = [
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V1",
    "HipFgmresExternalTrustAnchorRegistryResultV1",
    "HipFgmresExternalTrustAnchorRegistryV1Error",
    "HipFgmresExternalTrustAnchorV1",
    "load_hip_fgmres_external_trust_anchor_registry_v1",
    "validate_hip_fgmres_external_trust_anchor_registry_result_v1",
]
