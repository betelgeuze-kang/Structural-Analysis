"""Direct ``libamdhip64`` discovery and capability probing for Engine v2.

The probe calls only HIP runtime discovery APIs.  It does not allocate a HIP
context, stream, or device memory and it never invokes the CPU reference
backend.  ``LoadedHipRuntime`` is an in-process handle that a later execution
layer may reuse; no handle from it is serialized into the capability receipt.
"""

from __future__ import annotations

import _ctypes
from collections.abc import Sequence
import ctypes
import ctypes.util
from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
from typing import Any, Protocol, runtime_checkable
import weakref

from .types import (
    HIP_CAPABILITY_READY_CODE,
    HipCapabilityFacts,
    HipCapabilityReceipt,
    HipDeviceIdentity,
    HipRuntimeLibraryIdentity,
    HipVersionIdentity,
    build_hip_capability_receipt,
)

HIP_SUCCESS = 0
HIP_ERROR_NO_DEVICE = 100
_DEVICE_NAME_BUFFER_BYTES = 256


@runtime_checkable
class HipRuntimeProtocol(Protocol):
    """Small injectable ABI used by the hardware-independent probe tests."""

    def hip_init(self) -> int: ...

    def hip_get_device_count(self) -> tuple[int, int]: ...

    def hip_device_get_name(self, ordinal: int) -> tuple[int, str]: ...

    def hip_runtime_get_version(self) -> tuple[int, int]: ...

    def hip_driver_get_version(self) -> tuple[int, int]: ...

    def hip_error_string(self, status: int) -> str: ...


@dataclass(frozen=True, slots=True)
class HipRuntimeLibraryCandidate:
    discovery_source: str
    requested_name: str
    load_name: str
    resolved_path: str | None


class HipNativeRuntimeError(RuntimeError):
    """Stable load/discovery failure raised before a probe receipt is built."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        library: HipRuntimeLibraryIdentity,
        runtime_loaded: bool = False,
    ) -> None:
        self.code = code
        self.message = message
        self.library = library
        self.runtime_loaded = runtime_loaded
        super().__init__(f"{code}: {message}")


class _PrivateHipCdllFacade:
    """Non-exported symbol-address resolver for one native HIP handle."""

    __slots__ = ("_handle",)

    def __init__(self, cdll: ctypes.CDLL) -> None:
        handle = getattr(cdll, "_handle", None)
        if isinstance(handle, bool) or not isinstance(handle, int) or handle <= 0:
            raise ValueError("native HIP CDLL handle is invalid")
        self._handle = handle

    def symbol_address(self, symbol: str) -> int:
        address = int(_ctypes.dlsym(self._handle, symbol))
        if address <= 0 or ctypes.c_void_p(address).value != address:
            raise OSError(f"native HIP symbol has an invalid address: {symbol}")
        return address


_LOADED_HIP_RUNTIME_MINT = object()
_LOADED_HIP_RUNTIME_WITNESS_LOCK = threading.RLock()
_LOADED_HIP_RUNTIME_WITNESSES: weakref.WeakKeyDictionary[object, object] = (
    weakref.WeakKeyDictionary()
)


class LoadedHipRuntime:
    """A loaded native HIP library with probe functions bound by ``ctypes``.

    ``cdll`` and ``bind`` are intentionally runtime-only APIs.  Receipt types
    have no field that can accept either the library handle or later device
    pointers/streams.
    """

    __slots__ = (
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
        "__weakref__",
    )

    def __init__(
        self,
        cdll: ctypes.CDLL,
        library_identity: HipRuntimeLibraryIdentity,
        *,
        _loader_mint: object | None = None,
    ) -> None:
        if _loader_mint is not _LOADED_HIP_RUNTIME_MINT:
            raise TypeError(
                "LoadedHipRuntime is loader-issued only by load_hip_native_runtime()."
            )
        self._cdll = cdll
        self._library_identity = library_identity
        self._loader_provenance_nonce = object()
        self._private_cdll = (
            _PrivateHipCdllFacade(cdll) if isinstance(cdll, ctypes.CDLL) else None
        )
        self._hip_init = self.bind("hipInit", [ctypes.c_uint], ctypes.c_int)
        self._hip_get_device_count = self.bind(
            "hipGetDeviceCount", [ctypes.POINTER(ctypes.c_int)], ctypes.c_int
        )
        self._hip_device_get_name = self.bind(
            "hipDeviceGetName",
            [ctypes.c_void_p, ctypes.c_int, ctypes.c_int],
            ctypes.c_int,
        )
        self._hip_runtime_get_version = self.bind(
            "hipRuntimeGetVersion", [ctypes.POINTER(ctypes.c_int)], ctypes.c_int
        )
        self._hip_driver_get_version = self.bind(
            "hipDriverGetVersion", [ctypes.POINTER(ctypes.c_int)], ctypes.c_int
        )
        try:
            self._hip_get_error_string = self.bind(
                "hipGetErrorString", [ctypes.c_int], ctypes.c_char_p
            )
        except HipNativeRuntimeError:
            self._hip_get_error_string = None
        with _LOADED_HIP_RUNTIME_WITNESS_LOCK:
            _LOADED_HIP_RUNTIME_WITNESSES[self] = self._loader_provenance_nonce

    @property
    def library_identity(self) -> HipRuntimeLibraryIdentity:
        """Return immutable loader-attested library identity metadata."""

        return self._library_identity

    @property
    def cdll(self) -> ctypes.CDLL:
        """Return a compatibility view that is never used as binding authority."""

        return self._cdll

    def _loader_provenance_witness(self) -> object:
        """Return the process-local loader witness after registry validation."""

        with _LOADED_HIP_RUNTIME_WITNESS_LOCK:
            witness = _LOADED_HIP_RUNTIME_WITNESSES.get(self)
        if witness is not self._loader_provenance_nonce:
            raise HipNativeRuntimeError(
                "hip_runtime_provenance_invalid",
                "LoadedHipRuntime is not backed by the native loader registry.",
                library=self._library_identity,
                runtime_loaded=True,
            )
        return witness

    def bind(
        self,
        symbol: str,
        argtypes: Sequence[Any],
        restype: Any,
    ) -> Any:
        """Return one fresh fixed-prototype HIP callable.

        A public ``ctypes.CDLL`` caches mutable ``_FuncPtr`` objects.  The
        native path resolves only an address through a private facade and
        constructs a new ``CFUNCTYPE`` object for every caller, so mutations
        to the compatibility ``cdll`` view or to another result of ``bind``
        cannot change an in-flight owner.  Non-CDLL injected test doubles keep
        the legacy callable path.
        """

        if self._private_cdll is not None:
            try:
                address = self._private_cdll.symbol_address(symbol)
                prototype = ctypes.CFUNCTYPE(restype, *tuple(argtypes))
                return prototype(address)
            except (AttributeError, OSError, TypeError, ValueError) as exc:
                raise HipNativeRuntimeError(
                    "hip_runtime_symbol_missing",
                    f"Required HIP symbol is missing or invalid: {symbol}.",
                    library=self.library_identity,
                    runtime_loaded=True,
                ) from exc

        try:
            function = getattr(self._cdll, symbol)
        except AttributeError as exc:
            raise HipNativeRuntimeError(
                "hip_runtime_symbol_missing",
                f"Required HIP symbol is missing: {symbol}.",
                library=self.library_identity,
                runtime_loaded=True,
            ) from exc
        try:
            address = ctypes.cast(function, ctypes.c_void_p).value
        except (TypeError, ValueError, ctypes.ArgumentError):
            address = None
        if address:
            prototype = ctypes.CFUNCTYPE(restype, *tuple(argtypes))
            return prototype(address)
        function.argtypes = list(argtypes)
        function.restype = restype
        return function

    def hip_init(self) -> int:
        return int(self._hip_init(0))

    def hip_get_device_count(self) -> tuple[int, int]:
        count = ctypes.c_int(0)
        status = int(self._hip_get_device_count(ctypes.byref(count)))
        return status, int(count.value)

    def hip_device_get_name(self, ordinal: int) -> tuple[int, str]:
        buffer = ctypes.create_string_buffer(_DEVICE_NAME_BUFFER_BYTES)
        status = int(
            self._hip_device_get_name(
                ctypes.cast(buffer, ctypes.c_void_p),
                len(buffer),
                ordinal,
            )
        )
        raw_name = bytes(buffer).split(b"\0", 1)[0]
        return status, raw_name.decode("utf-8", errors="replace").strip()

    def hip_runtime_get_version(self) -> tuple[int, int]:
        version = ctypes.c_int(0)
        status = int(self._hip_runtime_get_version(ctypes.byref(version)))
        return status, int(version.value)

    def hip_driver_get_version(self) -> tuple[int, int]:
        version = ctypes.c_int(0)
        status = int(self._hip_driver_get_version(ctypes.byref(version)))
        return status, int(version.value)

    def hip_error_string(self, status: int) -> str:
        if self._hip_get_error_string is None:
            return "HIP error string unavailable"
        raw = self._hip_get_error_string(status)
        if raw is None:
            return "HIP error string unavailable"
        return raw.decode("utf-8", errors="replace")


def discover_hip_runtime_library(
    runtime_library: str | Path | None = None,
) -> HipRuntimeLibraryCandidate | None:
    """Discover an explicit, ``/opt/rocm``, or system-loader HIP runtime."""

    if runtime_library is not None:
        raw_name = str(runtime_library)
        if not raw_name:
            raise ValueError("runtime_library must not be empty")
        resolved = _resolve_existing_library_path(raw_name)
        load_name = resolved or raw_name
        return HipRuntimeLibraryCandidate(
            discovery_source="explicit",
            requested_name=raw_name,
            load_name=load_name,
            resolved_path=resolved,
        )

    opt_rocm_candidates = (
        Path("/opt/rocm/lib/libamdhip64.so"),
        Path("/opt/rocm/lib/libamdhip64.so.6"),
        Path("/opt/rocm/lib64/libamdhip64.so"),
        Path("/opt/rocm/lib64/libamdhip64.so.6"),
    )
    for path in opt_rocm_candidates:
        resolved = _resolve_existing_library_path(str(path))
        if resolved is not None:
            return HipRuntimeLibraryCandidate(
                discovery_source="opt_rocm",
                requested_name=str(path),
                load_name=resolved,
                resolved_path=resolved,
            )

    for directory in (Path("/opt/rocm/lib"), Path("/opt/rocm/lib64")):
        try:
            versioned_candidates = sorted(directory.glob("libamdhip64.so*"))
        except OSError:
            versioned_candidates = []
        for path in versioned_candidates:
            resolved = _resolve_existing_library_path(str(path))
            if resolved is not None:
                return HipRuntimeLibraryCandidate(
                    discovery_source="opt_rocm",
                    requested_name=str(path),
                    load_name=resolved,
                    resolved_path=resolved,
                )

    loader_name = ctypes.util.find_library("amdhip64")
    if loader_name:
        resolved = _resolve_loader_name(loader_name)
        return HipRuntimeLibraryCandidate(
            discovery_source="system_loader",
            requested_name=loader_name,
            load_name=resolved or loader_name,
            resolved_path=resolved,
        )
    return None


def load_hip_native_runtime(
    runtime_library: str | Path | None = None,
) -> LoadedHipRuntime:
    """Load ``libamdhip64`` and bind only the non-allocating probe surface."""

    candidate = discover_hip_runtime_library(runtime_library)
    if candidate is None:
        identity = HipRuntimeLibraryIdentity(
            discovery_source="none",
            requested_name=None,
            loaded_name=None,
            resolved_path=None,
            sha256=None,
        )
        raise HipNativeRuntimeError(
            "hip_runtime_library_not_found",
            "No explicit, /opt/rocm, or system-loader libamdhip64 was found.",
            library=identity,
        )

    if (
        candidate.discovery_source == "explicit"
        and _looks_like_path(candidate.requested_name)
        and candidate.resolved_path is None
    ):
        identity = _library_identity(candidate, loaded_name=None, sha256=None)
        raise HipNativeRuntimeError(
            "hip_runtime_library_not_found",
            f"Explicit HIP runtime does not exist: {candidate.requested_name}.",
            library=identity,
        )

    sha256: str | None = None
    if candidate.resolved_path is not None:
        try:
            sha256 = _sha256_file(Path(candidate.resolved_path))
        except OSError as exc:
            identity = _library_identity(candidate, loaded_name=None, sha256=None)
            raise HipNativeRuntimeError(
                "hip_runtime_library_hash_failed",
                f"Could not hash resolved HIP runtime: {type(exc).__name__}.",
                library=identity,
            ) from exc

    before_load = _library_identity(candidate, loaded_name=None, sha256=sha256)
    try:
        cdll = ctypes.CDLL(candidate.load_name, mode=getattr(ctypes, "RTLD_LOCAL", 0))
    except OSError as exc:
        raise HipNativeRuntimeError(
            "hip_runtime_library_load_failed",
            f"libamdhip64 could not be loaded: {type(exc).__name__}.",
            library=before_load,
        ) from exc

    loaded_identity = _library_identity(
        candidate,
        loaded_name=candidate.load_name,
        sha256=sha256,
    )
    return LoadedHipRuntime(
        cdll,
        loaded_identity,
        _loader_mint=_LOADED_HIP_RUNTIME_MINT,
    )


def probe_hip_capability(
    *,
    runtime_library: str | Path | None = None,
    device_ordinal: int = 0,
    runtime: HipRuntimeProtocol | None = None,
) -> HipCapabilityReceipt:
    """Probe native HIP readiness without allocating execution resources."""

    if isinstance(device_ordinal, bool) or not isinstance(device_ordinal, int):
        raise TypeError("device_ordinal must be an integer")
    if device_ordinal < 0:
        raise ValueError("device_ordinal must be non-negative")
    if runtime is not None and runtime_library is not None:
        raise ValueError("runtime and runtime_library are mutually exclusive")

    if runtime is None:
        try:
            runtime_api: HipRuntimeProtocol = load_hip_native_runtime(runtime_library)
        except HipNativeRuntimeError as exc:
            return _unavailable_receipt(
                code=exc.code,
                message=exc.message,
                library=exc.library,
                device_ordinal=device_ordinal,
                facts=HipCapabilityFacts(
                    runtime_loaded=exc.runtime_loaded,
                    runtime_initialized=False,
                    device_enumeration_succeeded=False,
                    selected_device_available=False,
                ),
            )
        library = runtime_api.library_identity  # type: ignore[attr-defined]
    else:
        runtime_api = runtime
        library = _injected_library_identity(runtime)

    loaded_only = HipCapabilityFacts(True, False, False, False)
    try:
        init_status = _status_value(runtime_api.hip_init(), "hipInit")
    except Exception as exc:  # fake/runtime ABI boundary
        return _unavailable_receipt(
            code="hip_init_failed",
            message=_exception_message("hipInit", exc),
            library=library,
            device_ordinal=device_ordinal,
            facts=loaded_only,
        )
    if init_status != HIP_SUCCESS:
        return _unavailable_receipt(
            code="hip_init_failed",
            message=_hip_status_message(runtime_api, "hipInit", init_status),
            library=library,
            device_ordinal=device_ordinal,
            facts=loaded_only,
        )

    initialized = HipCapabilityFacts(True, True, False, False)
    try:
        count_status, device_count = _status_and_nonnegative_int(
            runtime_api.hip_get_device_count(), "hipGetDeviceCount"
        )
    except Exception as exc:
        return _unavailable_receipt(
            code="hip_device_count_failed",
            message=_exception_message("hipGetDeviceCount", exc),
            library=library,
            device_ordinal=device_ordinal,
            facts=initialized,
        )
    if count_status == HIP_ERROR_NO_DEVICE:
        return _unavailable_receipt(
            code="hip_no_devices",
            message=_hip_status_message(runtime_api, "hipGetDeviceCount", count_status),
            library=library,
            device_ordinal=device_ordinal,
            facts=initialized,
        )
    if count_status != HIP_SUCCESS:
        return _unavailable_receipt(
            code="hip_device_count_failed",
            message=_hip_status_message(runtime_api, "hipGetDeviceCount", count_status),
            library=library,
            device_ordinal=device_ordinal,
            facts=initialized,
        )

    enumerated = HipCapabilityFacts(True, True, True, False)
    if device_count == 0:
        return _unavailable_receipt(
            code="hip_no_devices",
            message="hipGetDeviceCount returned zero devices.",
            library=library,
            device_ordinal=device_ordinal,
            facts=enumerated,
            device_count=0,
        )
    if device_ordinal >= device_count:
        return _unavailable_receipt(
            code="hip_device_ordinal_unavailable",
            message=(
                f"Selected HIP device ordinal {device_ordinal} is outside "
                f"the enumerated range [0, {device_count})."
            ),
            library=library,
            device_ordinal=device_ordinal,
            facts=enumerated,
            device_count=device_count,
        )

    selected = HipCapabilityFacts(True, True, True, True)
    try:
        name_status, device_name = _status_and_string(
            runtime_api.hip_device_get_name(device_ordinal), "hipDeviceGetName"
        )
    except Exception as exc:
        return _unavailable_receipt(
            code="hip_device_name_failed",
            message=_exception_message("hipDeviceGetName", exc),
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
        )
    if name_status != HIP_SUCCESS:
        return _unavailable_receipt(
            code="hip_device_name_failed",
            message=_hip_status_message(runtime_api, "hipDeviceGetName", name_status),
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
        )
    if not device_name:
        return _unavailable_receipt(
            code="hip_device_name_invalid",
            message="hipDeviceGetName returned an empty device name.",
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
        )

    try:
        runtime_status, runtime_version = _status_and_nonnegative_int(
            runtime_api.hip_runtime_get_version(), "hipRuntimeGetVersion"
        )
    except Exception as exc:
        return _unavailable_receipt(
            code="hip_runtime_version_failed",
            message=_exception_message("hipRuntimeGetVersion", exc),
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
            device_name=device_name,
        )
    if runtime_status != HIP_SUCCESS:
        return _unavailable_receipt(
            code="hip_runtime_version_failed",
            message=_hip_status_message(
                runtime_api, "hipRuntimeGetVersion", runtime_status
            ),
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
            device_name=device_name,
        )

    try:
        driver_status, driver_version = _status_and_nonnegative_int(
            runtime_api.hip_driver_get_version(), "hipDriverGetVersion"
        )
    except Exception as exc:
        return _unavailable_receipt(
            code="hip_driver_version_failed",
            message=_exception_message("hipDriverGetVersion", exc),
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
            device_name=device_name,
            runtime_version=runtime_version,
        )
    if driver_status != HIP_SUCCESS:
        return _unavailable_receipt(
            code="hip_driver_version_failed",
            message=_hip_status_message(
                runtime_api, "hipDriverGetVersion", driver_status
            ),
            library=library,
            device_ordinal=device_ordinal,
            facts=selected,
            device_count=device_count,
            device_name=device_name,
            runtime_version=runtime_version,
        )

    return build_hip_capability_receipt(
        status="ready",
        status_code=HIP_CAPABILITY_READY_CODE,
        message="HIP runtime and selected device were queried successfully.",
        library=library,
        device=HipDeviceIdentity(device_ordinal, device_count, device_name),
        versions=HipVersionIdentity(runtime_version, driver_version),
        capabilities=selected,
    )


def _unavailable_receipt(
    *,
    code: str,
    message: str,
    library: HipRuntimeLibraryIdentity,
    device_ordinal: int,
    facts: HipCapabilityFacts,
    device_count: int | None = None,
    device_name: str | None = None,
    runtime_version: int | None = None,
    driver_version: int | None = None,
) -> HipCapabilityReceipt:
    return build_hip_capability_receipt(
        status="unavailable",
        status_code=code,
        message=_bounded_message(message),
        library=library,
        device=HipDeviceIdentity(device_ordinal, device_count, device_name),
        versions=HipVersionIdentity(runtime_version, driver_version),
        capabilities=facts,
    )


def _injected_library_identity(
    runtime: HipRuntimeProtocol,
) -> HipRuntimeLibraryIdentity:
    identity = getattr(runtime, "library_identity", None)
    if isinstance(identity, HipRuntimeLibraryIdentity):
        return identity
    loaded_name = str(getattr(runtime, "library_name", "injected-runtime"))
    raw_path = getattr(runtime, "library_path", None)
    resolved = _resolve_existing_library_path(str(raw_path)) if raw_path else None
    sha256 = _sha256_file(Path(resolved)) if resolved is not None else None
    return HipRuntimeLibraryIdentity(
        discovery_source="injected",
        requested_name=loaded_name,
        loaded_name=loaded_name,
        resolved_path=resolved,
        sha256=sha256,
    )


def _library_identity(
    candidate: HipRuntimeLibraryCandidate,
    *,
    loaded_name: str | None,
    sha256: str | None,
) -> HipRuntimeLibraryIdentity:
    return HipRuntimeLibraryIdentity(
        discovery_source=candidate.discovery_source,  # type: ignore[arg-type]
        requested_name=candidate.requested_name,
        loaded_name=loaded_name,
        resolved_path=candidate.resolved_path,
        sha256=sha256,
    )


def _resolve_existing_library_path(raw_name: str) -> str | None:
    path = Path(raw_name).expanduser()
    try:
        if not path.is_file():
            return None
        return str(path.resolve(strict=True))
    except OSError:
        return None


def _resolve_loader_name(loader_name: str) -> str | None:
    direct = _resolve_existing_library_path(loader_name)
    if direct is not None:
        return direct
    for directory in (
        "/usr/lib/x86_64-linux-gnu",
        "/usr/lib64",
        "/usr/lib",
        "/lib/x86_64-linux-gnu",
        "/lib64",
        "/lib",
    ):
        resolved = _resolve_existing_library_path(str(Path(directory) / loader_name))
        if resolved is not None:
            return resolved
    return None


def _looks_like_path(name: str) -> bool:
    return "/" in name or "\\" in name or name.startswith(".")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _status_value(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} did not return an integer status")
    return value


def _status_and_nonnegative_int(value: Any, label: str) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError(f"{label} did not return a (status, value) tuple")
    status = _status_value(value[0], label)
    result = value[1]
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise TypeError(f"{label} returned an invalid non-negative integer value")
    return status, result


def _status_and_string(value: Any, label: str) -> tuple[int, str]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError(f"{label} did not return a (status, value) tuple")
    status = _status_value(value[0], label)
    result = value[1]
    if not isinstance(result, str):
        raise TypeError(f"{label} returned a non-string value")
    return status, result.strip()


def _hip_status_message(
    runtime: HipRuntimeProtocol,
    operation: str,
    status: int,
) -> str:
    try:
        detail = runtime.hip_error_string(status).strip()
    except Exception:
        detail = "HIP error string unavailable"
    return _bounded_message(f"{operation} failed with HIP status {status}: {detail}.")


def _exception_message(operation: str, exc: Exception) -> str:
    return _bounded_message(f"{operation} probe call failed: {type(exc).__name__}.")


def _bounded_message(message: str) -> str:
    normalized = " ".join(str(message).split())
    if not normalized:
        normalized = "HIP capability probe failed."
    return normalized[:512]


__all__ = [
    "HIP_ERROR_NO_DEVICE",
    "HIP_SUCCESS",
    "HipNativeRuntimeError",
    "HipRuntimeLibraryCandidate",
    "HipRuntimeProtocol",
    "LoadedHipRuntime",
    "discover_hip_runtime_library",
    "load_hip_native_runtime",
    "probe_hip_capability",
]
