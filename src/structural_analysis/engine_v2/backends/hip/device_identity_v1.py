"""Loader-attested, process-local HIP device identity evidence.

This module deliberately accepts only the exact :class:`LoadedHipRuntime`
issued by :func:`load_hip_native_runtime`.  It queries identity metadata only;
it does not create a context or stream, allocate or copy device memory, launch
a kernel, invoke a CPU fallback, or claim multi-architecture promotion.

Serialized receipts are canonical, immutable observations.  They cannot carry
the loader registry witness or the exact runtime object identity, so standalone
receipt validation is structural only.  Authoritative process-local validation
requires :class:`HipDeviceIdentityResultV1` and its retained runtime.
"""

from __future__ import annotations

import _ctypes
import ctypes
from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal
import uuid as uuid_module
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.backends.hip.native import (
    HIP_SUCCESS,
    HipNativeRuntimeError,
    LoadedHipRuntime,
    _PrivateHipCdllFacade,
)
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

HIP_DEVICE_IDENTITY_SCHEMA_VERSION_V1 = "structural-analysis-hip-device-identity.v1"
HIP_DEVICE_IDENTITY_CAPABILITY_PROFILE_V1 = (
    "engine_v2_loader_attested_hip_device_identity_v1"
)
HIP_DEVICE_IDENTITY_EVIDENCE_SCOPE_V1 = (
    "process_local_loader_attested_nonexecuting_hip_device_identity"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_RESOURCE = "hip_device_identity_v1.schema.json"
_GCN_BASE_RE = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")
_GCN_FEATURE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}[+-]$")
_PCI_BDF_RE = re.compile(
    r"^(?P<domain>[0-9a-fA-F]{4}):"
    r"(?P<bus>[0-9a-fA-F]{2}):"
    r"(?P<device>[0-9a-fA-F]{2})\."
    r"(?P<function>[0-7])$"
)
_GCN_ARCH_NAME_BYTES = 256
_PCI_BUS_ID_BYTES = 32
_UUID_BYTES = 16

_DLSYM = _ctypes.dlsym
_CFUNCTYPE = ctypes.CFUNCTYPE
_NATIVE_BINDING_AUTHORITY = (_DLSYM, _CFUNCTYPE)


def _class_member_code(member: Any) -> object | None:
    target = member.fget if type(member) is property else member
    return getattr(target, "__code__", None)


_RUNTIME_CLASS_MEMBER_NAMES = (
    "library_identity",
    "_loader_provenance_witness",
    "bind",
    "hip_init",
    "hip_get_device_count",
    "hip_device_get_name",
    "hip_runtime_get_version",
    "hip_driver_get_version",
)
_LOADED_RUNTIME_CLASS_MEMBERS = tuple(
    (
        name,
        vars(LoadedHipRuntime)[name],
        _class_member_code(vars(LoadedHipRuntime)[name]),
    )
    for name in _RUNTIME_CLASS_MEMBER_NAMES
)
_PRIVATE_FACADE_CLASS_MEMBERS = (
    (
        "symbol_address",
        vars(_PrivateHipCdllFacade)["symbol_address"],
        _class_member_code(vars(_PrivateHipCdllFacade)["symbol_address"]),
    ),
)
_LOADED_RUNTIME_LIBRARY_IDENTITY_PROPERTY = vars(LoadedHipRuntime)["library_identity"]
if (
    type(_LOADED_RUNTIME_LIBRARY_IDENTITY_PROPERTY) is not property
    or _LOADED_RUNTIME_LIBRARY_IDENTITY_PROPERTY.fget is None
):  # pragma: no cover - trusted module import invariant
    raise RuntimeError("LoadedHipRuntime.library_identity authority is invalid.")
_LOADED_RUNTIME_LIBRARY_IDENTITY_GETTER = _LOADED_RUNTIME_LIBRARY_IDENTITY_PROPERTY.fget
_LOADED_RUNTIME_LOADER_WITNESS_METHOD = vars(LoadedHipRuntime)[
    "_loader_provenance_witness"
]


class HipDeviceIdentityV1Error(ValueError):
    """Stable fail-closed identity error with a JSON-style path."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


class _HipDevicePropR0000(ctypes.Structure):
    """Exact deprecated R0000 ABI used only for non-allocating identity reads."""

    _fields_ = (
        ("name", ctypes.c_char * 256),
        ("totalGlobalMem", ctypes.c_size_t),
        ("sharedMemPerBlock", ctypes.c_size_t),
        ("regsPerBlock", ctypes.c_int),
        ("warpSize", ctypes.c_int),
        ("maxThreadsPerBlock", ctypes.c_int),
        ("maxThreadsDim", ctypes.c_int * 3),
        ("maxGridSize", ctypes.c_int * 3),
        ("clockRate", ctypes.c_int),
        ("memoryClockRate", ctypes.c_int),
        ("memoryBusWidth", ctypes.c_int),
        ("totalConstMem", ctypes.c_size_t),
        ("major", ctypes.c_int),
        ("minor", ctypes.c_int),
        ("multiProcessorCount", ctypes.c_int),
        ("l2CacheSize", ctypes.c_int),
        ("maxThreadsPerMultiProcessor", ctypes.c_int),
        ("computeMode", ctypes.c_int),
        ("clockInstructionRate", ctypes.c_int),
        # hipDeviceArch_tR0000 is one unsigned 32-bit bit-field container.
        ("arch", ctypes.c_uint),
        ("concurrentKernels", ctypes.c_int),
        ("pciDomainID", ctypes.c_int),
        ("pciBusID", ctypes.c_int),
        ("pciDeviceID", ctypes.c_int),
        ("maxSharedMemoryPerMultiProcessor", ctypes.c_size_t),
        ("isMultiGpuBoard", ctypes.c_int),
        ("canMapHostMemory", ctypes.c_int),
        ("gcnArch", ctypes.c_int),
        ("gcnArchName", ctypes.c_char * _GCN_ARCH_NAME_BYTES),
        ("integrated", ctypes.c_int),
        ("cooperativeLaunch", ctypes.c_int),
        ("cooperativeMultiDeviceLaunch", ctypes.c_int),
        ("maxTexture1DLinear", ctypes.c_int),
        ("maxTexture1D", ctypes.c_int),
        ("maxTexture2D", ctypes.c_int * 2),
        ("maxTexture3D", ctypes.c_int * 3),
        ("hdpMemFlushCntl", ctypes.POINTER(ctypes.c_uint)),
        ("hdpRegFlushCntl", ctypes.POINTER(ctypes.c_uint)),
        ("memPitch", ctypes.c_size_t),
        ("textureAlignment", ctypes.c_size_t),
        ("texturePitchAlignment", ctypes.c_size_t),
        ("kernelExecTimeoutEnabled", ctypes.c_int),
        ("ECCEnabled", ctypes.c_int),
        ("tccDriver", ctypes.c_int),
        ("cooperativeMultiDeviceUnmatchedFunc", ctypes.c_int),
        ("cooperativeMultiDeviceUnmatchedGridDim", ctypes.c_int),
        ("cooperativeMultiDeviceUnmatchedBlockDim", ctypes.c_int),
        ("cooperativeMultiDeviceUnmatchedSharedMem", ctypes.c_int),
        ("isLargeBar", ctypes.c_int),
        ("asicRevision", ctypes.c_int),
        ("managedMemory", ctypes.c_int),
        ("directManagedMemAccessFromHost", ctypes.c_int),
        ("concurrentManagedAccess", ctypes.c_int),
        ("pageableMemoryAccess", ctypes.c_int),
        ("pageableMemoryAccessUsesHostPageTables", ctypes.c_int),
    )


class _HipUuid(ctypes.Structure):
    _fields_ = (("bytes", ctypes.c_ubyte * _UUID_BYTES),)


@dataclass(frozen=True, slots=True)
class HipGcnArchitectureV1:
    raw: str
    base: str
    features: tuple[str, ...]
    normalized: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "base": self.base,
            "features": list(self.features),
            "normalized": self.normalized,
        }


@dataclass(frozen=True, slots=True)
class HipDeviceArchitectureBindingV1:
    runtime: HipGcnArchitectureV1
    expected_compiled: HipGcnArchitectureV1
    base_matches: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime.to_dict(),
            "expected_compiled": self.expected_compiled.to_dict(),
            "base_matches": self.base_matches,
        }


@dataclass(frozen=True, slots=True)
class HipDeviceHardwareIdentityV1:
    selected_ordinal: int
    device_count: int
    name: str
    uuid: str
    uuid_bytes_hex: str
    pci_bus_id_raw: str
    pci_bdf: str
    properties_pci_domain_id: int
    properties_pci_bus_id: int
    properties_pci_device_id: int

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipDeviceIdentityVersionsV1:
    runtime: int
    driver: int

    def to_dict(self) -> dict[str, int]:
        return {"runtime": self.runtime, "driver": self.driver}


@dataclass(frozen=True, slots=True)
class HipDeviceIdentityTelemetryV1:
    loader_provenance_check_count: Literal[3] = 3
    fresh_function_bind_count: Literal[8] = 8
    hip_init_call_count: Literal[1] = 1
    device_count_call_count: Literal[1] = 1
    device_name_call_count: Literal[1] = 1
    runtime_version_call_count: Literal[1] = 1
    driver_version_call_count: Literal[1] = 1
    device_properties_r0000_call_count: Literal[1] = 1
    device_uuid_call_count: Literal[1] = 1
    device_pci_bus_id_call_count: Literal[1] = 1
    device_allocation_count: Literal[0] = 0
    device_copy_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    context_creation_count: Literal[0] = 0
    stream_creation_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipDeviceIdentityClaimsV1:
    exact_loader_issued_runtime_verified: Literal[True] = True
    loader_registry_witness_verified: Literal[True] = True
    runtime_library_path_and_sha256_bound: Literal[True] = True
    fixed_r0000_gcn_arch_name_decoded: Literal[True] = True
    runtime_and_compiled_architecture_base_match: Literal[True] = True
    uuid_16_bytes_observed: Literal[True] = True
    canonical_pci_bdf_observed: Literal[True] = True
    no_device_allocation_copy_or_kernel: Literal[True] = True
    process_local_runtime_identity_verified: Literal[True] = True
    process_local_runtime_identity_serialized: Literal[False] = False
    standalone_serialized_authenticity: Literal[False] = False
    signed_evidence: Literal[False] = False
    multi_architecture_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipDeviceIdentityReceiptV1:
    schema_version: str
    capability_profile: str
    status: Literal["identity_attested"]
    evidence_scope: str
    actual_backend: Literal["hip"]
    library: HipRuntimeLibraryIdentity
    device: HipDeviceHardwareIdentityV1
    versions: HipDeviceIdentityVersionsV1
    architecture: HipDeviceArchitectureBindingV1
    telemetry: HipDeviceIdentityTelemetryV1
    claims: HipDeviceIdentityClaimsV1
    promotion_eligible: Literal[False]
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Return a structural manifest without serializing runtime authority."""

        validate_hip_device_identity_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipDeviceIdentityRuntimeQueryAuthorityV1:
    runtime: LoadedHipRuntime
    witness: object
    library: HipRuntimeLibraryIdentity
    library_snapshot: tuple[Any, ...]
    cdll: ctypes.CDLL
    private_cdll: _PrivateHipCdllFacade
    private_handle: int
    hip_init: Any
    hip_get_device_count: Any
    hip_device_get_name: Any
    hip_runtime_get_version: Any
    hip_driver_get_version: Any
    hip_get_device_properties_r0000: Any
    hip_device_get_uuid: Any
    hip_device_get_pci_bus_id: Any
    callable_authority_snapshot: tuple[Any, ...]
    class_authority_snapshot: tuple[Any, ...]
    private_snapshot: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class _HipDeviceIdentityPublicationRecordV1:
    receipt: HipDeviceIdentityReceiptV1
    runtime: LoadedHipRuntime
    witness: object
    library: HipRuntimeLibraryIdentity
    library_snapshot: tuple[Any, ...]
    query_authority: _HipDeviceIdentityRuntimeQueryAuthorityV1
    private_snapshot: tuple[Any, ...]
    publication_snapshot: tuple[Any, ...]


@dataclass(frozen=True, repr=False, eq=False)
class HipDeviceIdentityResultV1:
    __slots__ = (
        "receipt",
        "_loaded_runtime",
        "_loader_witness",
        "_runtime_library_identity",
        "_runtime_library_snapshot",
        "_runtime_query_authority",
        "_runtime_private_snapshot",
        "_publication_authority_snapshot",
        "__weakref__",
    )

    receipt: HipDeviceIdentityReceiptV1
    _loaded_runtime: LoadedHipRuntime
    _loader_witness: object
    _runtime_library_identity: HipRuntimeLibraryIdentity
    _runtime_library_snapshot: tuple[Any, ...]
    _runtime_query_authority: _HipDeviceIdentityRuntimeQueryAuthorityV1
    _runtime_private_snapshot: tuple[Any, ...]
    _publication_authority_snapshot: tuple[Any, ...]

    @property
    def architecture_base(self) -> str:
        return self.receipt.architecture.runtime.base

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_device_identity_result_v1(self)
        return self.receipt.to_dict()


_HIP_DEVICE_IDENTITY_PUBLICATION_LOCK = threading.RLock()
_HIP_DEVICE_IDENTITY_PUBLICATIONS: weakref.WeakKeyDictionary[
    HipDeviceIdentityResultV1,
    _HipDeviceIdentityPublicationRecordV1,
] = weakref.WeakKeyDictionary()


def normalize_hip_gcn_architecture_v1(raw: str) -> HipGcnArchitectureV1:
    """Parse one gfx target and canonicalize feature order and case."""

    if type(raw) is not str or not raw:
        _fail(
            "hip_device_identity_gcn_architecture_type_invalid",
            "/architecture",
        )
    if raw != raw.strip() or any(ord(character) < 0x21 for character in raw):
        _fail(
            "hip_device_identity_gcn_architecture_invalid",
            "/architecture",
        )
    lowered = raw.lower()
    parts = lowered.split(":")
    base = parts[0]
    if _GCN_BASE_RE.fullmatch(base) is None or base == "gfx000":
        _fail(
            "hip_device_identity_gcn_architecture_invalid",
            "/architecture/base",
        )
    feature_by_name: dict[str, str] = {}
    for feature in parts[1:]:
        if _GCN_FEATURE_RE.fullmatch(feature) is None:
            _fail(
                "hip_device_identity_gcn_feature_invalid",
                "/architecture/features",
            )
        feature_name = feature[:-1]
        if feature_name in feature_by_name:
            _fail(
                "hip_device_identity_gcn_feature_duplicate",
                "/architecture/features",
            )
        feature_by_name[feature_name] = feature
    features = tuple(feature_by_name[name] for name in sorted(feature_by_name))
    normalized = ":".join((base, *features)) if features else base
    return HipGcnArchitectureV1(
        raw=raw,
        base=base,
        features=features,
        normalized=normalized,
    )


def normalize_hip_pci_bus_id_v1(raw: str) -> str:
    """Return one canonical lower-case PCI domain:bus:device.function BDF."""

    if type(raw) is not str or not raw or raw != raw.strip():
        _fail("hip_device_identity_pci_bus_id_type_invalid", "/device/pci_bus_id")
    matched = _PCI_BDF_RE.fullmatch(raw)
    if matched is None:
        _fail("hip_device_identity_pci_bus_id_invalid", "/device/pci_bus_id")
    domain = int(matched.group("domain"), 16)
    bus = int(matched.group("bus"), 16)
    device = int(matched.group("device"), 16)
    function = int(matched.group("function"), 10)
    if domain > 0xFFFF or bus > 0xFF or device > 0x1F or function > 7:
        _fail("hip_device_identity_pci_bus_id_invalid", "/device/pci_bus_id")
    return f"{domain:04x}:{bus:02x}:{device:02x}.{function}"


def attest_hip_device_identity_v1(
    loaded_runtime: LoadedHipRuntime,
    *,
    device_ordinal: int,
    expected_compiled_architecture: str,
) -> HipDeviceIdentityResultV1:
    """Query one loader-issued runtime without allocating or executing work."""

    if type(loaded_runtime) is not LoadedHipRuntime:
        _fail(
            "hip_device_identity_runtime_type_invalid",
            "/loaded_runtime",
            "Exact loader-issued LoadedHipRuntime required.",
        )
    if type(device_ordinal) is not int or device_ordinal < 0:
        _fail(
            "hip_device_identity_device_ordinal_invalid",
            "/device_ordinal",
        )
    _validate_r0000_abi()
    expected_architecture = normalize_hip_gcn_architecture_v1(
        expected_compiled_architecture
    )
    query_authority = _capture_runtime_query_authority(loaded_runtime)
    first_witness = query_authority.witness
    library = query_authority.library
    initial_library_snapshot = query_authority.library_snapshot
    _validate_runtime_library_identity(library)
    initial_private_snapshot = query_authority.private_snapshot

    _require_zero_status(
        _call_runtime_status(
            query_authority.hip_init,
            ctypes.c_uint(0),
            path="/runtime/hipInit",
        ),
        "hip_device_identity_init_failed",
        "/runtime/hipInit",
    )
    count_status, device_count = _call_runtime_output_int(
        query_authority.hip_get_device_count,
        path="/runtime/hipGetDeviceCount",
    )
    _require_zero_status(
        count_status,
        "hip_device_identity_device_count_failed",
        "/runtime/hipGetDeviceCount",
    )
    if device_count <= 0:
        _fail("hip_device_identity_no_devices", "/device/device_count")
    if device_ordinal >= device_count:
        _fail(
            "hip_device_identity_device_ordinal_unavailable",
            "/device/selected_ordinal",
        )

    name_status, device_name = _call_runtime_device_name(
        query_authority.hip_device_get_name,
        device_ordinal,
        path="/runtime/hipDeviceGetName",
    )
    _require_zero_status(
        name_status,
        "hip_device_identity_device_name_failed",
        "/runtime/hipDeviceGetName",
    )
    _validate_device_name(device_name)

    runtime_status, runtime_version = _call_runtime_output_int(
        query_authority.hip_runtime_get_version,
        path="/runtime/hipRuntimeGetVersion",
    )
    _require_zero_status(
        runtime_status,
        "hip_device_identity_runtime_version_failed",
        "/runtime/hipRuntimeGetVersion",
    )
    driver_status, driver_version = _call_runtime_output_int(
        query_authority.hip_driver_get_version,
        path="/runtime/hipDriverGetVersion",
    )
    _require_zero_status(
        driver_status,
        "hip_device_identity_driver_version_failed",
        "/runtime/hipDriverGetVersion",
    )
    if runtime_version < 0 or driver_version < 0:
        _fail("hip_device_identity_version_invalid", "/versions")

    get_properties = query_authority.hip_get_device_properties_r0000
    get_uuid = query_authority.hip_device_get_uuid
    get_pci_bus_id = query_authority.hip_device_get_pci_bus_id

    properties = _HipDevicePropR0000()
    properties_status = _call_bound_status(
        get_properties,
        ctypes.byref(properties),
        device_ordinal,
        path="/runtime/hipGetDevicePropertiesR0000",
    )
    _require_zero_status(
        properties_status,
        "hip_device_identity_properties_failed",
        "/runtime/hipGetDevicePropertiesR0000",
    )
    raw_gcn = _fixed_ascii_field(
        ctypes.addressof(properties) + _HipDevicePropR0000.gcnArchName.offset,
        _GCN_ARCH_NAME_BYTES,
        code="hip_device_identity_gcn_arch_name_invalid",
        path="/architecture/runtime/raw",
    )
    runtime_architecture = normalize_hip_gcn_architecture_v1(raw_gcn)
    if runtime_architecture.base != expected_architecture.base:
        _fail(
            "hip_device_identity_architecture_base_mismatch",
            "/architecture/base_matches",
            f"Runtime {runtime_architecture.base} != compiled "
            f"{expected_architecture.base}.",
        )

    uuid_value = _HipUuid()
    uuid_status = _call_bound_status(
        get_uuid,
        ctypes.byref(uuid_value),
        device_ordinal,
        path="/runtime/hipDeviceGetUuid",
    )
    _require_zero_status(
        uuid_status,
        "hip_device_identity_uuid_failed",
        "/runtime/hipDeviceGetUuid",
    )
    uuid_bytes = bytes(uuid_value.bytes)
    if len(uuid_bytes) != _UUID_BYTES or uuid_bytes in {
        b"\0" * _UUID_BYTES,
        b"\xff" * _UUID_BYTES,
    }:
        _fail("hip_device_identity_uuid_invalid", "/device/uuid")
    canonical_uuid = str(uuid_module.UUID(bytes=uuid_bytes))

    pci_buffer = ctypes.create_string_buffer(_PCI_BUS_ID_BYTES)
    pci_status = _call_bound_status(
        get_pci_bus_id,
        ctypes.cast(pci_buffer, ctypes.POINTER(ctypes.c_char)),
        _PCI_BUS_ID_BYTES,
        device_ordinal,
        path="/runtime/hipDeviceGetPCIBusId",
    )
    _require_zero_status(
        pci_status,
        "hip_device_identity_pci_bus_id_failed",
        "/runtime/hipDeviceGetPCIBusId",
    )
    raw_pci = _fixed_ascii_field(
        ctypes.addressof(pci_buffer),
        _PCI_BUS_ID_BYTES,
        code="hip_device_identity_pci_bus_id_invalid",
        path="/device/pci_bus_id",
    )
    canonical_pci = normalize_hip_pci_bus_id_v1(raw_pci)
    pci_components = _pci_components(canonical_pci)
    properties_pci = (
        int(properties.pciDomainID),
        int(properties.pciBusID),
        int(properties.pciDeviceID),
    )
    if properties_pci != pci_components[:3]:
        _fail(
            "hip_device_identity_pci_properties_mismatch",
            "/device/pci_bdf",
        )

    (
        second_witness,
        current_library,
        current_library_snapshot,
        current_private_snapshot,
    ) = _validate_runtime_query_authority(query_authority)
    if second_witness is not first_witness:
        _fail(
            "hip_device_identity_runtime_provenance_changed",
            "/loaded_runtime/provenance",
        )
    if current_library is not library:
        _fail(
            "hip_device_identity_runtime_library_changed",
            "/library",
        )
    if current_library_snapshot != initial_library_snapshot:
        _fail(
            "hip_device_identity_runtime_library_changed",
            "/library",
        )
    if current_private_snapshot != initial_private_snapshot:
        _fail(
            "hip_device_identity_runtime_private_identity_changed",
            "/loaded_runtime/private_identity",
        )

    architecture = HipDeviceArchitectureBindingV1(
        runtime=runtime_architecture,
        expected_compiled=expected_architecture,
    )
    device = HipDeviceHardwareIdentityV1(
        selected_ordinal=device_ordinal,
        device_count=device_count,
        name=device_name,
        uuid=canonical_uuid,
        uuid_bytes_hex=uuid_bytes.hex(),
        pci_bus_id_raw=raw_pci,
        pci_bdf=canonical_pci,
        properties_pci_domain_id=properties_pci[0],
        properties_pci_bus_id=properties_pci[1],
        properties_pci_device_id=properties_pci[2],
    )
    versions = HipDeviceIdentityVersionsV1(
        runtime=runtime_version,
        driver=driver_version,
    )
    receipt = _build_receipt(
        library=library,
        device=device,
        versions=versions,
        architecture=architecture,
    )
    authority_snapshot = _publication_authority_snapshot(
        receipt,
        loaded_runtime,
        first_witness,
        library,
        initial_library_snapshot,
        query_authority,
        initial_private_snapshot,
    )
    result = HipDeviceIdentityResultV1(
        receipt=receipt,
        _loaded_runtime=loaded_runtime,
        _loader_witness=first_witness,
        _runtime_library_identity=library,
        _runtime_library_snapshot=initial_library_snapshot,
        _runtime_query_authority=query_authority,
        _runtime_private_snapshot=initial_private_snapshot,
        _publication_authority_snapshot=authority_snapshot,
    )
    with _HIP_DEVICE_IDENTITY_PUBLICATION_LOCK:
        _HIP_DEVICE_IDENTITY_PUBLICATIONS[result] = (
            _HipDeviceIdentityPublicationRecordV1(
                receipt=receipt,
                runtime=loaded_runtime,
                witness=first_witness,
                library=library,
                library_snapshot=initial_library_snapshot,
                query_authority=query_authority,
                private_snapshot=initial_private_snapshot,
                publication_snapshot=authority_snapshot,
            )
        )
    return validate_hip_device_identity_result_v1(
        result,
        expected_loaded_runtime=loaded_runtime,
    )


def validate_hip_device_identity_receipt_v1(
    receipt: HipDeviceIdentityReceiptV1,
) -> HipDeviceIdentityReceiptV1:
    """Validate serialized structure without reasserting loader authenticity."""

    if type(receipt) is not HipDeviceIdentityReceiptV1:
        _fail("hip_device_identity_receipt_type_invalid", "/")
    nested_types = (
        (receipt.library, HipRuntimeLibraryIdentity, "/library"),
        (receipt.device, HipDeviceHardwareIdentityV1, "/device"),
        (receipt.versions, HipDeviceIdentityVersionsV1, "/versions"),
        (receipt.architecture, HipDeviceArchitectureBindingV1, "/architecture"),
        (receipt.telemetry, HipDeviceIdentityTelemetryV1, "/telemetry"),
        (receipt.claims, HipDeviceIdentityClaimsV1, "/claims"),
    )
    for value, expected, path in nested_types:
        if type(value) is not expected:
            _fail("hip_device_identity_nested_type_invalid", path)

    for name in (
        "schema_version",
        "capability_profile",
        "status",
        "evidence_scope",
        "actual_backend",
        "receipt_hash",
    ):
        if type(getattr(receipt, name)) is not str:
            _fail("hip_device_identity_scalar_type_invalid", f"/{name}")
    if type(receipt.promotion_eligible) is not bool:
        _fail("hip_device_identity_scalar_type_invalid", "/promotion_eligible")

    _validate_runtime_library_identity(receipt.library)
    _validate_device_identity(receipt.device)
    _validate_versions(receipt.versions)
    _validate_architecture_binding(receipt.architecture)
    _validate_telemetry(receipt.telemetry)
    _validate_claims(receipt.claims)
    if (
        receipt.schema_version != HIP_DEVICE_IDENTITY_SCHEMA_VERSION_V1
        or receipt.capability_profile != HIP_DEVICE_IDENTITY_CAPABILITY_PROFILE_V1
        or receipt.status != "identity_attested"
        or receipt.evidence_scope != HIP_DEVICE_IDENTITY_EVIDENCE_SCOPE_V1
        or receipt.actual_backend != "hip"
        or receipt.promotion_eligible is not False
    ):
        _fail("hip_device_identity_receipt_semantics_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_device_identity_receipt_schema_invalid", path, error.message)
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if (
        _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != expected_hash
    ):
        _fail("hip_device_identity_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_device_identity_result_v1(
    result: HipDeviceIdentityResultV1,
    *,
    expected_loaded_runtime: LoadedHipRuntime | None = None,
) -> HipDeviceIdentityResultV1:
    """Validate exact process-local loader and receipt identity provenance."""

    if type(result) is not HipDeviceIdentityResultV1:
        _fail("hip_device_identity_result_type_invalid", "/")
    with _HIP_DEVICE_IDENTITY_PUBLICATION_LOCK:
        publication = _HIP_DEVICE_IDENTITY_PUBLICATIONS.get(result)
    if (
        type(publication) is not _HipDeviceIdentityPublicationRecordV1
        or publication.receipt is not result.receipt
        or publication.runtime is not result._loaded_runtime
        or publication.witness is not result._loader_witness
        or publication.library is not result._runtime_library_identity
        or publication.library_snapshot is not result._runtime_library_snapshot
        or type(publication.library_snapshot) is not tuple
        or publication.library_snapshot
        != _runtime_library_identity_snapshot(publication.library)
        or result.receipt.library is not publication.library
        or publication.query_authority is not result._runtime_query_authority
        or publication.query_authority.library is not publication.library
        or publication.query_authority.library_snapshot != publication.library_snapshot
        or publication.private_snapshot is not result._runtime_private_snapshot
        or publication.publication_snapshot
        is not result._publication_authority_snapshot
    ):
        _fail("hip_device_identity_result_publication_invalid", "/publication")
    validate_hip_device_identity_receipt_v1(result.receipt)
    runtime = result._loaded_runtime
    if type(runtime) is not LoadedHipRuntime:
        _fail("hip_device_identity_result_runtime_invalid", "/runtime")
    if expected_loaded_runtime is not None:
        if type(expected_loaded_runtime) is not LoadedHipRuntime:
            _fail(
                "hip_device_identity_expected_runtime_invalid",
                "/expected_loaded_runtime",
            )
        if runtime is not expected_loaded_runtime:
            _fail("hip_device_identity_result_runtime_mismatch", "/runtime")
    query_authority = result._runtime_query_authority
    witness, library, library_snapshot, private_snapshot = (
        _validate_runtime_query_authority(query_authority)
    )
    if (
        witness is not result._loader_witness
        or library is not result._runtime_library_identity
        or result.receipt.library is not result._runtime_library_identity
        or type(result._runtime_library_snapshot) is not tuple
        or library_snapshot != result._runtime_library_snapshot
        or query_authority.library_snapshot is not result._runtime_library_snapshot
        or query_authority.runtime is not runtime
        or query_authority.witness is not witness
        or query_authority.library is not library
        or type(result._runtime_private_snapshot) is not tuple
        or private_snapshot != result._runtime_private_snapshot
        or type(result._publication_authority_snapshot) is not tuple
        or result._publication_authority_snapshot
        != _publication_authority_snapshot(
            result.receipt,
            runtime,
            witness,
            library,
            library_snapshot,
            query_authority,
            private_snapshot,
        )
    ):
        _fail("hip_device_identity_result_provenance_invalid", "/provenance")
    return result


def _build_receipt(
    *,
    library: HipRuntimeLibraryIdentity,
    device: HipDeviceHardwareIdentityV1,
    versions: HipDeviceIdentityVersionsV1,
    architecture: HipDeviceArchitectureBindingV1,
) -> HipDeviceIdentityReceiptV1:
    draft = HipDeviceIdentityReceiptV1(
        schema_version=HIP_DEVICE_IDENTITY_SCHEMA_VERSION_V1,
        capability_profile=HIP_DEVICE_IDENTITY_CAPABILITY_PROFILE_V1,
        status="identity_attested",
        evidence_scope=HIP_DEVICE_IDENTITY_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        library=library,
        device=device,
        versions=versions,
        architecture=architecture,
        telemetry=HipDeviceIdentityTelemetryV1(),
        claims=HipDeviceIdentityClaimsV1(),
        promotion_eligible=False,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_device_identity_receipt_v1(receipt)


def _receipt_payload(
    receipt: HipDeviceIdentityReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "library": receipt.library.to_dict(),
        "device": receipt.device.to_dict(),
        "versions": receipt.versions.to_dict(),
        "architecture": receipt.architecture.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "promotion_eligible": receipt.promotion_eligible,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_runtime_library_identity(identity: HipRuntimeLibraryIdentity) -> None:
    if type(identity) is not HipRuntimeLibraryIdentity:
        _fail("hip_device_identity_library_type_invalid", "/library")
    if identity.discovery_source not in {"explicit", "opt_rocm", "system_loader"}:
        _fail("hip_device_identity_library_source_invalid", "/library/discovery_source")
    for name in ("requested_name", "loaded_name", "resolved_path", "sha256"):
        value = getattr(identity, name)
        if type(value) is not str or not value:
            _fail("hip_device_identity_library_field_invalid", f"/library/{name}")
    assert identity.resolved_path is not None
    assert identity.sha256 is not None
    path = Path(identity.resolved_path)
    try:
        resolved = str(path.resolve(strict=True))
    except OSError as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_library_path_invalid",
            "/library/resolved_path",
            type(exc).__name__,
        ) from exc
    if (
        not path.is_absolute()
        or not path.is_file()
        or resolved != identity.resolved_path
    ):
        _fail(
            "hip_device_identity_library_path_invalid",
            "/library/resolved_path",
        )
    if _HASH_RE.fullmatch(identity.sha256) is None:
        _fail("hip_device_identity_library_hash_invalid", "/library/sha256")


def _validate_r0000_abi() -> None:
    expected_offsets = {
        "arch": 356,
        "pciDomainID": 364,
        "pciBusID": 368,
        "pciDeviceID": 372,
        "gcnArchName": 396,
        "hdpMemFlushCntl": 696,
        "hdpRegFlushCntl": 704,
    }
    if (
        ctypes.sizeof(ctypes.c_int) != 4
        or ctypes.sizeof(ctypes.c_uint) != 4
        or ctypes.sizeof(ctypes.c_size_t) != 8
        or ctypes.sizeof(ctypes.c_void_p) != 8
        or ctypes.sizeof(_HipDevicePropR0000) != 792
        or ctypes.alignment(_HipDevicePropR0000) != 8
        or any(
            getattr(_HipDevicePropR0000, name).offset != offset
            for name, offset in expected_offsets.items()
        )
    ):
        _fail(
            "hip_device_identity_r0000_abi_unsupported",
            "/runtime/hipGetDevicePropertiesR0000/abi",
        )


def _validate_device_identity(device: HipDeviceHardwareIdentityV1) -> None:
    for name in (
        "selected_ordinal",
        "device_count",
        "properties_pci_domain_id",
        "properties_pci_bus_id",
        "properties_pci_device_id",
    ):
        if type(getattr(device, name)) is not int:
            _fail("hip_device_identity_device_scalar_invalid", f"/device/{name}")
    if (
        device.selected_ordinal < 0
        or device.device_count <= 0
        or device.selected_ordinal >= device.device_count
    ):
        _fail("hip_device_identity_device_extent_invalid", "/device")
    _validate_device_name(device.name)
    for name in ("uuid", "uuid_bytes_hex", "pci_bus_id_raw", "pci_bdf"):
        if type(getattr(device, name)) is not str:
            _fail("hip_device_identity_device_scalar_invalid", f"/device/{name}")
    if re.fullmatch(r"[0-9a-f]{32}", device.uuid_bytes_hex) is None:
        _fail("hip_device_identity_uuid_invalid", "/device/uuid_bytes_hex")
    uuid_bytes = bytes.fromhex(device.uuid_bytes_hex)
    if uuid_bytes in {b"\0" * _UUID_BYTES, b"\xff" * _UUID_BYTES}:
        _fail("hip_device_identity_uuid_invalid", "/device/uuid_bytes_hex")
    try:
        expected_uuid = str(uuid_module.UUID(bytes=uuid_bytes))
    except ValueError as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_uuid_invalid",
            "/device/uuid",
            type(exc).__name__,
        ) from exc
    if device.uuid != expected_uuid:
        _fail("hip_device_identity_uuid_invalid", "/device/uuid")
    if normalize_hip_pci_bus_id_v1(device.pci_bus_id_raw) != device.pci_bdf:
        _fail("hip_device_identity_pci_bus_id_invalid", "/device/pci_bdf")
    pci_components = _pci_components(device.pci_bdf)
    if (
        device.properties_pci_domain_id,
        device.properties_pci_bus_id,
        device.properties_pci_device_id,
    ) != pci_components[:3]:
        _fail("hip_device_identity_pci_properties_mismatch", "/device/pci_bdf")


def _validate_versions(versions: HipDeviceIdentityVersionsV1) -> None:
    if (
        type(versions.runtime) is not int
        or type(versions.driver) is not int
        or versions.runtime < 0
        or versions.driver < 0
    ):
        _fail("hip_device_identity_version_invalid", "/versions")


def _validate_architecture_binding(
    binding: HipDeviceArchitectureBindingV1,
) -> None:
    if (
        type(binding.runtime) is not HipGcnArchitectureV1
        or type(binding.expected_compiled) is not HipGcnArchitectureV1
        or type(binding.base_matches) is not bool
    ):
        _fail("hip_device_identity_architecture_type_invalid", "/architecture")
    runtime = normalize_hip_gcn_architecture_v1(binding.runtime.raw)
    expected = normalize_hip_gcn_architecture_v1(binding.expected_compiled.raw)
    if runtime != binding.runtime or expected != binding.expected_compiled:
        _fail("hip_device_identity_architecture_normalization_invalid", "/architecture")
    if binding.base_matches is not True or runtime.base != expected.base:
        _fail("hip_device_identity_architecture_base_mismatch", "/architecture")


def _validate_telemetry(telemetry: HipDeviceIdentityTelemetryV1) -> None:
    for name in telemetry.__dataclass_fields__:
        if type(getattr(telemetry, name)) is not int:
            _fail("hip_device_identity_telemetry_type_invalid", f"/telemetry/{name}")
    if telemetry != HipDeviceIdentityTelemetryV1():
        _fail("hip_device_identity_telemetry_invalid", "/telemetry")


def _validate_claims(claims: HipDeviceIdentityClaimsV1) -> None:
    for name in claims.__dataclass_fields__:
        if type(getattr(claims, name)) is not bool:
            _fail("hip_device_identity_claim_type_invalid", f"/claims/{name}")
    if claims != HipDeviceIdentityClaimsV1():
        _fail("hip_device_identity_claim_invalid", "/claims")


def _loader_witness(runtime: LoadedHipRuntime) -> object:
    try:
        return _LOADED_RUNTIME_LOADER_WITNESS_METHOD(runtime)
    except HipNativeRuntimeError as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_runtime_provenance_invalid",
            "/loaded_runtime/provenance",
            exc.code,
        ) from exc


def _runtime_library_identity(runtime: LoadedHipRuntime) -> HipRuntimeLibraryIdentity:
    identity = _LOADED_RUNTIME_LIBRARY_IDENTITY_GETTER(runtime)
    if type(identity) is not HipRuntimeLibraryIdentity:
        _fail("hip_device_identity_library_type_invalid", "/library")
    return identity


def _runtime_library_identity_snapshot(
    identity: HipRuntimeLibraryIdentity,
) -> tuple[Any, ...]:
    """Return exact immutable field values for one loader identity object."""

    if type(identity) is not HipRuntimeLibraryIdentity:
        _fail("hip_device_identity_library_type_invalid", "/library")
    return (
        type(identity),
        type(object.__getattribute__(identity, "discovery_source")),
        object.__getattribute__(identity, "discovery_source"),
        type(object.__getattribute__(identity, "requested_name")),
        object.__getattribute__(identity, "requested_name"),
        type(object.__getattribute__(identity, "loaded_name")),
        object.__getattribute__(identity, "loaded_name"),
        type(object.__getattribute__(identity, "resolved_path")),
        object.__getattribute__(identity, "resolved_path"),
        type(object.__getattribute__(identity, "sha256")),
        object.__getattribute__(identity, "sha256"),
    )


def _runtime_class_authority_snapshot() -> tuple[Any, ...]:
    rows: list[tuple[Any, ...]] = []
    expected_dlsym, expected_cfunctype = _NATIVE_BINDING_AUTHORITY
    if (
        _DLSYM is not expected_dlsym
        or _ctypes.dlsym is not expected_dlsym
        or _CFUNCTYPE is not expected_cfunctype
        or ctypes.CFUNCTYPE is not expected_cfunctype
    ):
        _fail(
            "hip_device_identity_runtime_callable_authority_invalid",
            "/loaded_runtime/class_authority/native_binding",
        )
    rows.append(
        (
            "native_binding",
            type(expected_dlsym),
            id(expected_dlsym),
            type(expected_cfunctype),
            id(expected_cfunctype),
        )
    )
    for owner, members in (
        (LoadedHipRuntime, _LOADED_RUNTIME_CLASS_MEMBERS),
        (_PrivateHipCdllFacade, _PRIVATE_FACADE_CLASS_MEMBERS),
    ):
        current_members = vars(owner)
        for name, expected, expected_code in members:
            current = current_members.get(name)
            current_code = _class_member_code(current)
            if current is not expected or current_code is not expected_code:
                _fail(
                    "hip_device_identity_runtime_callable_authority_invalid",
                    f"/loaded_runtime/class_authority/{owner.__name__}/{name}",
                )
            rows.append(
                (
                    owner.__module__,
                    owner.__qualname__,
                    name,
                    type(current),
                    id(current),
                    id(current_code) if current_code is not None else None,
                )
            )
    return tuple(rows)


def _runtime_private_snapshot(runtime: LoadedHipRuntime) -> tuple[Any, ...]:
    names = (
        "_cdll",
        "_private_cdll",
        "_library_identity",
        "_loader_provenance_nonce",
        "_hip_init",
        "_hip_get_device_count",
        "_hip_device_get_name",
        "_hip_runtime_get_version",
        "_hip_driver_get_version",
        "_hip_get_error_string",
    )
    try:
        private_cdll = object.__getattribute__(runtime, "_private_cdll")
        if type(private_cdll) is not _PrivateHipCdllFacade:
            _fail(
                "hip_device_identity_runtime_private_identity_invalid",
                "/loaded_runtime/private_identity/_private_cdll",
            )
        private_handle = object.__getattribute__(private_cdll, "_handle")
        if type(private_handle) is not int or private_handle <= 0:
            _fail(
                "hip_device_identity_runtime_private_identity_invalid",
                "/loaded_runtime/private_identity/_private_cdll/_handle",
            )
        instance_rows = tuple(
            (name, type(value), id(value))
            for name in names
            for value in (object.__getattribute__(runtime, name),)
        )
        return (
            *instance_rows,
            ("_private_cdll._handle", type(private_handle), private_handle),
            (
                "_library_identity.values",
                _runtime_library_identity_snapshot(
                    object.__getattribute__(runtime, "_library_identity")
                ),
            ),
            ("class_authority", _runtime_class_authority_snapshot()),
        )
    except AttributeError as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_runtime_private_identity_invalid",
            "/loaded_runtime/private_identity",
            type(exc).__name__,
        ) from exc


def _capture_runtime_query_authority(
    runtime: LoadedHipRuntime,
) -> _HipDeviceIdentityRuntimeQueryAuthorityV1:
    class_snapshot = _runtime_class_authority_snapshot()
    witness = _loader_witness(runtime)
    library = _runtime_library_identity(runtime)
    library_snapshot = _runtime_library_identity_snapshot(library)
    try:
        cdll = object.__getattribute__(runtime, "_cdll")
        private_cdll = object.__getattribute__(runtime, "_private_cdll")
        private_handle = object.__getattribute__(private_cdll, "_handle")
    except AttributeError as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_runtime_query_authority_invalid",
            "/loaded_runtime/query_authority",
            type(exc).__name__,
        ) from exc
    if (
        type(cdll) is not ctypes.CDLL
        or type(private_cdll) is not _PrivateHipCdllFacade
        or type(private_handle) is not int
        or private_handle <= 0
        or object.__getattribute__(cdll, "_handle") != private_handle
    ):
        _fail(
            "hip_device_identity_runtime_query_authority_invalid",
            "/loaded_runtime/query_authority",
        )
    hip_init = _bind_identity_function(
        private_handle,
        "hipInit",
        [ctypes.c_uint],
    )
    hip_get_device_count = _bind_identity_function(
        private_handle,
        "hipGetDeviceCount",
        [ctypes.POINTER(ctypes.c_int)],
    )
    hip_device_get_name = _bind_identity_function(
        private_handle,
        "hipDeviceGetName",
        [ctypes.c_void_p, ctypes.c_int, ctypes.c_int],
    )
    hip_runtime_get_version = _bind_identity_function(
        private_handle,
        "hipRuntimeGetVersion",
        [ctypes.POINTER(ctypes.c_int)],
    )
    hip_driver_get_version = _bind_identity_function(
        private_handle,
        "hipDriverGetVersion",
        [ctypes.POINTER(ctypes.c_int)],
    )
    hip_get_device_properties_r0000 = _bind_identity_function(
        private_handle,
        "hipGetDevicePropertiesR0000",
        [ctypes.POINTER(_HipDevicePropR0000), ctypes.c_int],
    )
    hip_device_get_uuid = _bind_identity_function(
        private_handle,
        "hipDeviceGetUuid",
        [ctypes.POINTER(_HipUuid), ctypes.c_int],
    )
    hip_device_get_pci_bus_id = _bind_identity_function(
        private_handle,
        "hipDeviceGetPCIBusId",
        [ctypes.POINTER(ctypes.c_char), ctypes.c_int, ctypes.c_int],
    )
    callable_snapshot = _identity_callable_authority_snapshot(
        (
            ("hipInit", hip_init),
            ("hipGetDeviceCount", hip_get_device_count),
            ("hipDeviceGetName", hip_device_get_name),
            ("hipRuntimeGetVersion", hip_runtime_get_version),
            ("hipDriverGetVersion", hip_driver_get_version),
            ("hipGetDevicePropertiesR0000", hip_get_device_properties_r0000),
            ("hipDeviceGetUuid", hip_device_get_uuid),
            ("hipDeviceGetPCIBusId", hip_device_get_pci_bus_id),
        )
    )
    private_snapshot = _runtime_private_snapshot(runtime)
    authority = _HipDeviceIdentityRuntimeQueryAuthorityV1(
        runtime=runtime,
        witness=witness,
        library=library,
        library_snapshot=library_snapshot,
        cdll=cdll,
        private_cdll=private_cdll,
        private_handle=private_handle,
        hip_init=hip_init,
        hip_get_device_count=hip_get_device_count,
        hip_device_get_name=hip_device_get_name,
        hip_runtime_get_version=hip_runtime_get_version,
        hip_driver_get_version=hip_driver_get_version,
        hip_get_device_properties_r0000=hip_get_device_properties_r0000,
        hip_device_get_uuid=hip_device_get_uuid,
        hip_device_get_pci_bus_id=hip_device_get_pci_bus_id,
        callable_authority_snapshot=callable_snapshot,
        class_authority_snapshot=class_snapshot,
        private_snapshot=private_snapshot,
    )
    return authority


def _validate_runtime_query_authority(
    authority: _HipDeviceIdentityRuntimeQueryAuthorityV1,
) -> tuple[object, HipRuntimeLibraryIdentity, tuple[Any, ...], tuple[Any, ...]]:
    if type(authority) is not _HipDeviceIdentityRuntimeQueryAuthorityV1:
        _fail(
            "hip_device_identity_runtime_query_authority_invalid",
            "/loaded_runtime/query_authority",
        )
    runtime = authority.runtime
    if type(runtime) is not LoadedHipRuntime:
        _fail(
            "hip_device_identity_runtime_query_authority_invalid",
            "/loaded_runtime/query_authority/runtime",
        )
    current_class_snapshot = _runtime_class_authority_snapshot()
    current_witness = _loader_witness(runtime)
    current_library = _runtime_library_identity(runtime)
    current_library_snapshot = _runtime_library_identity_snapshot(current_library)
    current_private_snapshot = _runtime_private_snapshot(runtime)
    current_callable_snapshot = _identity_callable_authority_snapshot(
        (
            ("hipInit", authority.hip_init),
            ("hipGetDeviceCount", authority.hip_get_device_count),
            ("hipDeviceGetName", authority.hip_device_get_name),
            ("hipRuntimeGetVersion", authority.hip_runtime_get_version),
            ("hipDriverGetVersion", authority.hip_driver_get_version),
            (
                "hipGetDevicePropertiesR0000",
                authority.hip_get_device_properties_r0000,
            ),
            ("hipDeviceGetUuid", authority.hip_device_get_uuid),
            ("hipDeviceGetPCIBusId", authority.hip_device_get_pci_bus_id),
        )
    )
    if (
        authority.witness is not current_witness
        or authority.library is not current_library
        or authority.library_snapshot != current_library_snapshot
        or authority.class_authority_snapshot != current_class_snapshot
        or object.__getattribute__(runtime, "_cdll") is not authority.cdll
        or object.__getattribute__(runtime, "_private_cdll")
        is not authority.private_cdll
        or object.__getattribute__(authority.private_cdll, "_handle")
        != authority.private_handle
        or object.__getattribute__(authority.cdll, "_handle")
        != authority.private_handle
        or current_callable_snapshot != authority.callable_authority_snapshot
        or current_private_snapshot != authority.private_snapshot
    ):
        _fail(
            "hip_device_identity_runtime_query_authority_invalid",
            "/loaded_runtime/query_authority",
        )
    return (
        current_witness,
        current_library,
        current_library_snapshot,
        current_private_snapshot,
    )


def _publication_authority_snapshot(
    receipt: HipDeviceIdentityReceiptV1,
    runtime: LoadedHipRuntime,
    witness: object,
    library: HipRuntimeLibraryIdentity,
    library_snapshot: tuple[Any, ...],
    query_authority: _HipDeviceIdentityRuntimeQueryAuthorityV1,
    private_snapshot: tuple[Any, ...],
) -> tuple[Any, ...]:
    return (
        type(receipt),
        id(receipt),
        receipt.receipt_hash,
        type(runtime),
        id(runtime),
        id(witness),
        type(library),
        id(library),
        library_snapshot,
        type(query_authority),
        id(query_authority),
        private_snapshot,
    )


def _call_runtime_status(operation: Any, *arguments: Any, path: str) -> int:
    if not callable(operation):
        _fail("hip_device_identity_runtime_method_invalid", path)
    try:
        result = operation(*arguments)
    except Exception as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_runtime_call_failed",
            path,
            type(exc).__name__,
        ) from exc
    if type(result) is not int:
        _fail("hip_device_identity_runtime_result_invalid", path)
    return result


def _call_runtime_output_int(
    operation: Any,
    path: str,
) -> tuple[int, int]:
    output = ctypes.c_int(0)
    status = _call_runtime_status(operation, ctypes.byref(output), path=path)
    return status, int(output.value)


def _call_runtime_device_name(
    operation: Any,
    device_ordinal: int,
    *,
    path: str,
) -> tuple[int, str]:
    buffer = ctypes.create_string_buffer(_GCN_ARCH_NAME_BYTES)
    status = _call_runtime_status(
        operation,
        ctypes.cast(buffer, ctypes.c_void_p),
        len(buffer),
        device_ordinal,
        path=path,
    )
    raw_name = bytes(buffer).split(b"\0", 1)[0]
    return status, raw_name.decode("utf-8", errors="replace").strip()


def _identity_callable_authority_snapshot(
    operations: tuple[tuple[str, Any], ...],
) -> tuple[Any, ...]:
    rows: list[tuple[Any, ...]] = []
    for name, operation in operations:
        argtypes = getattr(operation, "argtypes", None)
        restype = getattr(operation, "restype", None)
        errcheck = getattr(operation, "errcheck", None)
        if (
            not callable(operation)
            or type(argtypes) not in {list, tuple}
            or not argtypes
            or restype is not ctypes.c_int
            or errcheck is not None
        ):
            _fail(
                "hip_device_identity_runtime_callable_authority_invalid",
                f"/runtime/{name}",
            )
        rows.append(
            (
                name,
                type(operation),
                id(operation),
                tuple((type(value), id(value)) for value in tuple(argtypes)),
                type(restype),
                id(restype),
                type(errcheck),
                id(errcheck),
            )
        )
    return tuple(rows)


def _bind_identity_function(
    private_handle: int,
    symbol: str,
    argtypes: list[Any],
) -> Any:
    dlsym, cfunctype = _NATIVE_BINDING_AUTHORITY
    try:
        address = int(dlsym(private_handle, symbol))
        if address <= 0 or ctypes.c_void_p(address).value != address:
            raise OSError(f"native HIP symbol has an invalid address: {symbol}")
        function = cfunctype(ctypes.c_int, *tuple(argtypes))(address)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_runtime_symbol_invalid",
            f"/runtime/{symbol}",
            type(exc).__name__,
        ) from exc
    if not callable(function):
        _fail("hip_device_identity_runtime_symbol_invalid", f"/runtime/{symbol}")
    return function


def _call_bound_status(function: Any, *arguments: Any, path: str) -> int:
    try:
        status = function(*arguments)
    except Exception as exc:
        raise HipDeviceIdentityV1Error(
            "hip_device_identity_runtime_call_failed",
            path,
            type(exc).__name__,
        ) from exc
    if type(status) is not int:
        _fail("hip_device_identity_runtime_result_invalid", path)
    return status


def _require_zero_status(status: int, code: str, path: str) -> None:
    if type(status) is not int or status != HIP_SUCCESS:
        _fail(code, path, f"HIP status {status!r}.")


def _fixed_ascii_field(address: int, size: int, *, code: str, path: str) -> str:
    raw = ctypes.string_at(address, size)
    terminator = raw.find(b"\0")
    if terminator <= 0:
        _fail(code, path, "Fixed field is empty or lacks NUL termination.")
    try:
        value = raw[:terminator].decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise HipDeviceIdentityV1Error(code, path, "Non-ASCII fixed field.") from exc
    if not value:
        _fail(code, path)
    return value


def _pci_components(canonical_bdf: str) -> tuple[int, int, int, int]:
    matched = _PCI_BDF_RE.fullmatch(canonical_bdf)
    if matched is None:  # pragma: no cover - caller normalizes first
        _fail("hip_device_identity_pci_bus_id_invalid", "/device/pci_bdf")
    return (
        int(matched.group("domain"), 16),
        int(matched.group("bus"), 16),
        int(matched.group("device"), 16),
        int(matched.group("function"), 10),
    )


def _validate_device_name(name: str) -> None:
    if (
        type(name) is not str
        or not name
        or name != name.strip()
        or "\ufffd" in name
        or any(not character.isprintable() for character in name)
    ):
        _fail("hip_device_identity_device_name_invalid", "/device/name")


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipDeviceIdentityV1Error(code, path, message)


__all__ = [
    "HIP_DEVICE_IDENTITY_CAPABILITY_PROFILE_V1",
    "HIP_DEVICE_IDENTITY_EVIDENCE_SCOPE_V1",
    "HIP_DEVICE_IDENTITY_SCHEMA_VERSION_V1",
    "HipDeviceArchitectureBindingV1",
    "HipDeviceHardwareIdentityV1",
    "HipDeviceIdentityClaimsV1",
    "HipDeviceIdentityReceiptV1",
    "HipDeviceIdentityResultV1",
    "HipDeviceIdentityTelemetryV1",
    "HipDeviceIdentityV1Error",
    "HipDeviceIdentityVersionsV1",
    "HipGcnArchitectureV1",
    "attest_hip_device_identity_v1",
    "normalize_hip_gcn_architecture_v1",
    "normalize_hip_pci_bus_id_v1",
    "validate_hip_device_identity_receipt_v1",
    "validate_hip_device_identity_result_v1",
]
