"""Strict immutable types for the Engine v2 native HIP capability probe.

This module describes discovery evidence only.  A capability receipt never
contains a device pointer, stream, context handle, or a claim that an Engine v2
operator has executed on the device.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

HIP_CAPABILITY_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-capability-receipt.v1"
)
HIP_CAPABILITY_PROBE_VERSION = "engine-v2-native-hip-capability-probe.v1"
HIP_CAPABILITY_READY_CODE = "hip_runtime_device_ready"
HIP_CAPABILITY_UNAVAILABLE_CODES = frozenset(
    {
        "hip_runtime_library_not_found",
        "hip_runtime_library_hash_failed",
        "hip_runtime_library_load_failed",
        "hip_runtime_symbol_missing",
        "hip_init_failed",
        "hip_device_count_failed",
        "hip_no_devices",
        "hip_device_ordinal_unavailable",
        "hip_device_name_failed",
        "hip_device_name_invalid",
        "hip_runtime_version_failed",
        "hip_driver_version_failed",
    }
)

HipCapabilityStatus = Literal["ready", "unavailable"]
HipLibraryDiscoverySource = Literal[
    "explicit", "opt_rocm", "system_loader", "injected", "none"
]


class HipCapabilityReceiptError(ValueError):
    """Fail-closed HIP receipt error carrying a stable code and JSON path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class HipRuntimeLibraryIdentity:
    discovery_source: HipLibraryDiscoverySource
    requested_name: str | None
    loaded_name: str | None
    resolved_path: str | None
    sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovery_source": self.discovery_source,
            "requested_name": self.requested_name,
            "loaded_name": self.loaded_name,
            "resolved_path": self.resolved_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class HipDeviceIdentity:
    selected_ordinal: int
    device_count: int | None
    name: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_ordinal": self.selected_ordinal,
            "device_count": self.device_count,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class HipVersionIdentity:
    runtime: int | None
    driver: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"runtime": self.runtime, "driver": self.driver}


@dataclass(frozen=True, slots=True)
class HipCapabilityFacts:
    runtime_loaded: bool
    runtime_initialized: bool
    device_enumeration_succeeded: bool
    selected_device_available: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "runtime_loaded": self.runtime_loaded,
            "runtime_initialized": self.runtime_initialized,
            "device_enumeration_succeeded": self.device_enumeration_succeeded,
            "selected_device_available": self.selected_device_available,
        }


@dataclass(frozen=True, slots=True)
class HipCapabilityReceipt:
    """Immutable evidence that a HIP runtime/device can or cannot be queried."""

    schema_version: str
    probe_version: str
    status: HipCapabilityStatus
    status_code: str
    message: str
    backend: Literal["hip_native"]
    library: HipRuntimeLibraryIdentity
    device: HipDeviceIdentity
    versions: HipVersionIdentity
    capabilities: HipCapabilityFacts
    fallback_policy: Literal["forbidden"]
    fallback_used: Literal[False]
    context_created: Literal[False]
    model_residency_proven: Literal[False]
    operator_execution_proven: Literal[False]
    solver_execution_proven: Literal[False]
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_capability_receipt(self)
        return _receipt_payload(self, include_receipt_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def build_hip_capability_receipt(
    *,
    status: HipCapabilityStatus,
    status_code: str,
    message: str,
    library: HipRuntimeLibraryIdentity,
    device: HipDeviceIdentity,
    versions: HipVersionIdentity,
    capabilities: HipCapabilityFacts,
) -> HipCapabilityReceipt:
    """Build, hash, schema-check, and semantically validate one receipt."""

    receipt = HipCapabilityReceipt(
        schema_version=HIP_CAPABILITY_RECEIPT_SCHEMA_VERSION,
        probe_version=HIP_CAPABILITY_PROBE_VERSION,
        status=status,
        status_code=status_code,
        message=message,
        backend="hip_native",
        library=library,
        device=device,
        versions=versions,
        capabilities=capabilities,
        fallback_policy="forbidden",
        fallback_used=False,
        context_created=False,
        model_residency_proven=False,
        operator_execution_proven=False,
        solver_execution_proven=False,
        receipt_hash="sha256:" + ("0" * 64),
    )
    receipt = replace(
        receipt,
        receipt_hash=canonical_hash(
            _receipt_payload(receipt, include_receipt_hash=False)
        ),
    )
    return validate_hip_capability_receipt(receipt)


def validate_hip_capability_receipt(
    receipt: HipCapabilityReceipt,
) -> HipCapabilityReceipt:
    """Reject malformed, internally inconsistent, or rehashed receipts."""

    if not isinstance(receipt, HipCapabilityReceipt):
        raise HipCapabilityReceiptError(
            "hip_receipt_type_invalid", "/", "Expected HipCapabilityReceipt."
        )
    nested_types = (
        (receipt.library, HipRuntimeLibraryIdentity, "/library"),
        (receipt.device, HipDeviceIdentity, "/device"),
        (receipt.versions, HipVersionIdentity, "/versions"),
        (receipt.capabilities, HipCapabilityFacts, "/capabilities"),
    )
    for value, expected_type, path in nested_types:
        if not isinstance(value, expected_type):
            raise HipCapabilityReceiptError(
                "hip_receipt_type_invalid",
                path,
                f"Expected {expected_type.__name__}.",
            )

    payload = _receipt_payload(receipt, include_receipt_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipCapabilityReceiptError(
            "hip_receipt_schema_invalid", path, error.message
        )

    _validate_semantics(receipt)
    expected_hash = canonical_hash(
        _receipt_payload(receipt, include_receipt_hash=False)
    )
    if receipt.receipt_hash != expected_hash:
        raise HipCapabilityReceiptError(
            "hip_receipt_hash_mismatch",
            "/receipt_hash",
            "Receipt hash does not match its canonical payload.",
        )
    return receipt


def _validate_semantics(receipt: HipCapabilityReceipt) -> None:
    facts = receipt.capabilities
    library = receipt.library
    device = receipt.device

    if receipt.status == "ready":
        if receipt.status_code != HIP_CAPABILITY_READY_CODE:
            raise HipCapabilityReceiptError(
                "hip_receipt_status_code_invalid",
                "/status_code",
                "Ready receipts require the canonical ready code.",
            )
        if not all(
            (
                facts.runtime_loaded,
                facts.runtime_initialized,
                facts.device_enumeration_succeeded,
                facts.selected_device_available,
            )
        ):
            raise HipCapabilityReceiptError(
                "hip_receipt_ready_facts_invalid",
                "/capabilities",
                "Ready receipts require all discovery facts to be true.",
            )
    elif receipt.status_code not in HIP_CAPABILITY_UNAVAILABLE_CODES:
        raise HipCapabilityReceiptError(
            "hip_receipt_status_code_invalid",
            "/status_code",
            "Unavailable receipt uses an unknown stable status code.",
        )

    if facts.runtime_initialized and not facts.runtime_loaded:
        _semantic_error(
            "/capabilities/runtime_initialized",
            "Runtime initialization cannot precede library loading.",
        )
    if facts.device_enumeration_succeeded and not facts.runtime_initialized:
        _semantic_error(
            "/capabilities/device_enumeration_succeeded",
            "Device enumeration cannot precede runtime initialization.",
        )
    if facts.selected_device_available and not facts.device_enumeration_succeeded:
        _semantic_error(
            "/capabilities/selected_device_available",
            "Device availability requires successful enumeration.",
        )
    if facts.runtime_loaded and library.loaded_name is None:
        _semantic_error(
            "/library/loaded_name", "A loaded runtime requires a loaded name."
        )
    if library.loaded_name is not None and not facts.runtime_loaded:
        _semantic_error(
            "/library/loaded_name",
            "A loaded library name requires proven runtime loading.",
        )
    if (
        library.resolved_path is not None
        and library.sha256 is None
        and receipt.status_code != "hip_runtime_library_hash_failed"
    ):
        _semantic_error(
            "/library/sha256",
            "A resolved runtime library must carry its content SHA-256.",
        )
    if library.sha256 is not None and library.resolved_path is None:
        _semantic_error(
            "/library/resolved_path",
            "A library SHA-256 requires a resolved filesystem path.",
        )
    if device.device_count is not None and not facts.device_enumeration_succeeded:
        _semantic_error(
            "/device/device_count",
            "A device count requires successful enumeration.",
        )
    if facts.selected_device_available:
        if device.device_count is None or device.selected_ordinal >= device.device_count:
            _semantic_error(
                "/device/selected_ordinal",
                "Selected ordinal is outside the enumerated device range.",
            )
    if device.name is not None and not facts.selected_device_available:
        _semantic_error(
            "/device/name", "A device name requires a proven available ordinal."
        )
    if receipt.status == "ready":
        if (
            device.name is None
            or receipt.versions.runtime is None
            or receipt.versions.driver is None
        ):
            _semantic_error(
                "/",
                "Ready receipts require a device name and runtime/driver versions.",
            )

    expected_facts: dict[str, tuple[bool, bool, bool, bool] | None] = {
        "hip_runtime_library_not_found": (False, False, False, False),
        "hip_runtime_library_hash_failed": (False, False, False, False),
        "hip_runtime_library_load_failed": (False, False, False, False),
        "hip_runtime_symbol_missing": (True, False, False, False),
        "hip_init_failed": (True, False, False, False),
        "hip_device_count_failed": (True, True, False, False),
        "hip_no_devices": None,
        "hip_device_ordinal_unavailable": (True, True, True, False),
        "hip_device_name_failed": (True, True, True, True),
        "hip_device_name_invalid": (True, True, True, True),
        "hip_runtime_version_failed": (True, True, True, True),
        "hip_driver_version_failed": (True, True, True, True),
    }
    expected = expected_facts.get(receipt.status_code)
    actual = (
        facts.runtime_loaded,
        facts.runtime_initialized,
        facts.device_enumeration_succeeded,
        facts.selected_device_available,
    )
    if expected is not None and actual != expected:
        _semantic_error(
            "/capabilities",
            f"Capability facts do not match status code {receipt.status_code}.",
        )
    if receipt.status_code == "hip_no_devices" and actual not in {
        (True, True, False, False),
        (True, True, True, False),
    }:
        _semantic_error(
            "/capabilities",
            "No-device facts must stop at enumeration or a proven zero count.",
        )
    if receipt.status_code == "hip_device_ordinal_unavailable" and (
        device.device_count is None
        or device.device_count <= 0
        or device.selected_ordinal < device.device_count
    ):
        _semantic_error(
            "/device/selected_ordinal",
            "Unavailable ordinal must be outside a non-empty enumerated range.",
        )
    if receipt.status_code in {
        "hip_device_name_failed",
        "hip_device_name_invalid",
    } and device.name is not None:
        _semantic_error(
            "/device/name", "A failed device-name query cannot carry a name."
        )
    if receipt.status_code == "hip_runtime_version_failed" and (
        receipt.versions.runtime is not None or receipt.versions.driver is not None
    ):
        _semantic_error(
            "/versions", "A failed runtime-version query cannot carry versions."
        )
    if receipt.status_code == "hip_driver_version_failed" and (
        receipt.versions.runtime is None or receipt.versions.driver is not None
    ):
        _semantic_error(
            "/versions",
            "A failed driver-version query requires only the runtime version.",
        )


def _semantic_error(path: str, message: str) -> None:
    raise HipCapabilityReceiptError("hip_receipt_semantics_invalid", path, message)


def _receipt_payload(
    receipt: HipCapabilityReceipt, *, include_receipt_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "probe_version": receipt.probe_version,
        "status": receipt.status,
        "status_code": receipt.status_code,
        "message": receipt.message,
        "backend": receipt.backend,
        "library": receipt.library.to_dict(),
        "device": receipt.device.to_dict(),
        "versions": receipt.versions.to_dict(),
        "capabilities": receipt.capabilities.to_dict(),
        "fallback_policy": receipt.fallback_policy,
        "fallback_used": receipt.fallback_used,
        "context_created": receipt.context_created,
        "model_residency_proven": receipt.model_residency_proven,
        "operator_execution_proven": receipt.operator_execution_proven,
        "solver_execution_proven": receipt.solver_execution_proven,
    }
    if include_receipt_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "hip_capability_receipt_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "HIP_CAPABILITY_PROBE_VERSION",
    "HIP_CAPABILITY_READY_CODE",
    "HIP_CAPABILITY_RECEIPT_SCHEMA_VERSION",
    "HIP_CAPABILITY_UNAVAILABLE_CODES",
    "HipCapabilityFacts",
    "HipCapabilityReceipt",
    "HipCapabilityReceiptError",
    "HipDeviceIdentity",
    "HipRuntimeLibraryIdentity",
    "HipVersionIdentity",
    "build_hip_capability_receipt",
    "validate_hip_capability_receipt",
]
