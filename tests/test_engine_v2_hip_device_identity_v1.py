from __future__ import annotations

import copy
import ctypes
from dataclasses import FrozenInstanceError, replace
import inspect
import os
from pathlib import Path
import pickle
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.hip import native  # noqa: E402
from structural_analysis.engine_v2.backends.hip import (  # noqa: E402
    device_identity_v1 as identity,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (  # noqa: E402
    HipDeviceIdentityV1Error,
    attest_hip_device_identity_v1,
    normalize_hip_gcn_architecture_v1,
    normalize_hip_pci_bus_id_v1,
    validate_hip_device_identity_receipt_v1,
    validate_hip_device_identity_result_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    HipNativeRuntimeError,
    LoadedHipRuntime,
    load_hip_native_runtime,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)


_FAKE_RUNTIME_SOURCE = r"""
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct FakePropsR0000 {
  char name[256];
  size_t totalGlobalMem;
  size_t sharedMemPerBlock;
  int regsPerBlock;
  int warpSize;
  int maxThreadsPerBlock;
  int maxThreadsDim[3];
  int maxGridSize[3];
  int clockRate;
  int memoryClockRate;
  int memoryBusWidth;
  size_t totalConstMem;
  int major;
  int minor;
  int multiProcessorCount;
  int l2CacheSize;
  int maxThreadsPerMultiProcessor;
  int computeMode;
  int clockInstructionRate;
  unsigned int arch;
  int concurrentKernels;
  int pciDomainID;
  int pciBusID;
  int pciDeviceID;
  size_t maxSharedMemoryPerMultiProcessor;
  int isMultiGpuBoard;
  int canMapHostMemory;
  int gcnArch;
  char gcnArchName[256];
} FakePropsR0000;

static int modes[3] = {0, 0, 0};
static int calls[8] = {0, 0, 0, 0, 0, 0, 0, 0};

int hipInit(unsigned int flags) {
  (void)flags;
  calls[0] += 1;
  return 0;
}

int hipGetDeviceCount(int* count) {
  calls[1] += 1;
  *count = 1;
  return 0;
}

int hipDeviceGetName(void* output, int length, int device) {
  calls[2] += 1;
  if (device != 0 || length <= 0) return 101;
  snprintf((char*)output, (size_t)length, "%s", "Fake Loader AMD GPU");
  return 0;
}

int hipRuntimeGetVersion(int* version) {
  calls[3] += 1;
  *version = 60032831;
  return 0;
}

int hipDriverGetVersion(int* version) {
  calls[4] += 1;
  *version = 60032831;
  return 0;
}

const char* hipGetErrorString(int status) {
  (void)status;
  return "fake HIP error";
}

int hipGetDevicePropertiesR0000(void* raw, int device) {
  FakePropsR0000* props = (FakePropsR0000*)raw;
  calls[5] += 1;
  if (device != 0) return 101;
  memset(props, 0, sizeof(*props));
  props->pciDomainID = 0;
  props->pciBusID = 11;
  props->pciDeviceID = 0;
  if (modes[0] == 1) {
    memset(props->gcnArchName, 'a', sizeof(props->gcnArchName));
  } else if (modes[0] == 2) {
    memcpy(props->gcnArchName, "gfx1030:bad", 12);
  } else if (modes[0] == 3) {
    memcpy(props->gcnArchName, "gfx1100", 8);
  } else {
    memcpy(props->gcnArchName, "gfx1030:xnack+:sramecc-", 24);
  }
  return 0;
}

int hipDeviceGetUuid(void* raw, int device) {
  unsigned char* output = (unsigned char*)raw;
  calls[6] += 1;
  if (device != 0) return 101;
  for (int index = 0; index < 16; ++index) {
    output[index] = modes[1] == 1 ? 0 : (unsigned char)(index + 1);
  }
  return 0;
}

int hipDeviceGetPCIBusId(char* output, int length, int device) {
  calls[7] += 1;
  if (device != 0 || length <= 0) return 101;
  if (modes[2] == 1) {
    snprintf(output, (size_t)length, "%s", "0000:0b:20.0");
  } else if (modes[2] == 2) {
    memset(output, 'a', (size_t)length);
  } else {
    snprintf(output, (size_t)length, "%s", "0000:0B:00.0");
  }
  return 0;
}

void fakeReset(void) {
  memset(modes, 0, sizeof(modes));
  memset(calls, 0, sizeof(calls));
}

void fakeSetMode(int index, int value) {
  if (index >= 0 && index < 3) modes[index] = value;
}

int fakeGetCallCount(int index) {
  if (index < 0 || index >= 8) return -1;
  return calls[index];
}
"""


class _NativeHarness:
    def __init__(self, runtime: LoadedHipRuntime) -> None:
        self.runtime = runtime
        self._reset = runtime.bind("fakeReset", [], None)
        self._set_mode = runtime.bind("fakeSetMode", [ctypes.c_int, ctypes.c_int], None)
        self._get_call_count = runtime.bind(
            "fakeGetCallCount", [ctypes.c_int], ctypes.c_int
        )
        self.reset()

    def reset(self) -> None:
        self._reset()

    def set_mode(self, index: int, value: int) -> None:
        self._set_mode(index, value)

    @property
    def call_counts(self) -> tuple[int, ...]:
        return tuple(int(self._get_call_count(index)) for index in range(8))


def _compile_runtime_library(tmp_path: Path, source_text: str, name: str) -> Path:
    compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if compiler is None:
        pytest.fail("A C compiler is required for loader-issued HIP ABI tests.")
    source = tmp_path / f"{name}.c"
    library = tmp_path / f"{name}.so"
    source.write_text(source_text, encoding="utf-8")
    completed = subprocess.run(
        [compiler, "-shared", "-fPIC", "-O2", "-o", str(library), str(source)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        pytest.fail(f"Could not compile fake HIP runtime: {completed.stderr}")
    return library


@pytest.fixture()
def native_harness(tmp_path: Path) -> _NativeHarness:
    library = _compile_runtime_library(
        tmp_path,
        _FAKE_RUNTIME_SOURCE,
        "libfake_hip_identity_runtime",
    )
    return _NativeHarness(load_hip_native_runtime(library))


def _attest(harness: _NativeHarness) -> Any:
    return attest_hip_device_identity_v1(
        harness.runtime,
        device_ordinal=0,
        expected_compiled_architecture="gfx1030",
    )


def _coherently_rehash(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, **changes, receipt_hash=identity._ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            identity._receipt_payload(draft, include_hash=False)
        ),
    )


def test_r0000_ctypes_layout_matches_rocm6_prefix_abi() -> None:
    props = identity._HipDevicePropR0000

    assert ctypes.sizeof(props) == 792
    assert ctypes.alignment(props) == 8
    assert props.pciDomainID.offset == 364
    assert props.pciBusID.offset == 368
    assert props.pciDeviceID.offset == 372
    assert props.gcnArchName.offset == 396
    gcn_field_type = next(
        field_type
        for field_name, field_type in props._fields_
        if field_name == "gcnArchName"
    )
    assert ctypes.sizeof(gcn_field_type) == 256


def test_loader_issued_identity_receipt_is_exact_canonical_and_nonpromoting(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)
    receipt = result.receipt
    manifest = result.to_manifest()

    assert receipt.actual_backend == "hip"
    assert receipt.architecture.runtime.raw == "gfx1030:xnack+:sramecc-"
    assert receipt.architecture.runtime.base == "gfx1030"
    assert receipt.architecture.runtime.features == ("sramecc-", "xnack+")
    assert receipt.architecture.runtime.normalized == "gfx1030:sramecc-:xnack+"
    assert receipt.architecture.expected_compiled.base == "gfx1030"
    assert receipt.architecture.base_matches
    assert receipt.device.name == "Fake Loader AMD GPU"
    assert receipt.device.uuid_bytes_hex == "0102030405060708090a0b0c0d0e0f10"
    assert receipt.device.uuid == "01020304-0506-0708-090a-0b0c0d0e0f10"
    assert receipt.device.pci_bus_id_raw == "0000:0B:00.0"
    assert receipt.device.pci_bdf == "0000:0b:00.0"
    assert receipt.device.properties_pci_bus_id == 11
    assert receipt.library is native_harness.runtime.library_identity
    assert receipt.library.sha256 is not None
    assert native_harness.call_counts == (1, 1, 1, 1, 1, 1, 1, 1)
    assert receipt.telemetry.loader_provenance_check_count == 3
    assert receipt.telemetry.fresh_function_bind_count == 8
    assert receipt.telemetry.device_allocation_count == 0
    assert receipt.telemetry.device_copy_count == 0
    assert receipt.telemetry.kernel_launch_count == 0
    assert receipt.telemetry.context_creation_count == 0
    assert receipt.telemetry.stream_creation_count == 0
    assert receipt.telemetry.fallback_count == 0
    assert receipt.claims.process_local_runtime_identity_verified
    assert not receipt.claims.process_local_runtime_identity_serialized
    assert not receipt.claims.standalone_serialized_authenticity
    assert not receipt.claims.signed_evidence
    assert not receipt.claims.multi_architecture_verified
    assert not receipt.claims.commercial_ready
    assert not receipt.claims.promotion_eligible
    assert not receipt.promotion_eligible
    assert "_loaded_runtime" not in manifest
    assert "_loader_witness" not in manifest
    assert validate_hip_device_identity_receipt_v1(receipt) is receipt
    assert (
        validate_hip_device_identity_result_v1(
            result,
            expected_loaded_runtime=native_harness.runtime,
        )
        is result
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "discovery_source",
        "requested_name",
        "loaded_name",
        "resolved_path",
        "sha256",
    ),
)
def test_loader_library_identity_value_drift_rejects_before_identity_queries(
    native_harness: _NativeHarness,
    tmp_path: Path,
    field_name: str,
) -> None:
    runtime = native_harness.runtime
    library = runtime.library_identity
    replacement_path = tmp_path / "alternate-runtime.so"
    shutil.copy2(Path(library.resolved_path), replacement_path)
    replacements = {
        "discovery_source": "opt_rocm",
        "requested_name": "libamdhip64-alternate.so",
        "loaded_name": "libamdhip64-alternate.so",
        "resolved_path": str(replacement_path.resolve(strict=True)),
        "sha256": "sha256:" + "f" * 64,
    }
    object.__setattr__(library, field_name, replacements[field_name])

    with pytest.raises(HipNativeRuntimeError) as native_caught:
        runtime._loader_provenance_witness()
    assert native_caught.value.code == "hip_runtime_provenance_invalid"

    with pytest.raises(HipDeviceIdentityV1Error) as identity_caught:
        _attest(native_harness)
    assert (
        identity_caught.value.code == "hip_device_identity_runtime_provenance_invalid"
    )
    assert native_harness.call_counts == (0, 0, 0, 0, 0, 0, 0, 0)


def test_published_result_rejects_coherent_shared_library_identity_forge(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)
    library = result._runtime_library_identity
    object.__setattr__(library, "sha256", "sha256:" + "f" * 64)
    object.__setattr__(
        result.receipt,
        "receipt_hash",
        canonical_hash(identity._receipt_payload(result.receipt, include_hash=False)),
    )
    forged_snapshot = identity._runtime_library_identity_snapshot(library)
    object.__setattr__(
        result._runtime_query_authority,
        "library_snapshot",
        forged_snapshot,
    )
    object.__setattr__(result, "_runtime_library_snapshot", forged_snapshot)
    object.__setattr__(
        result,
        "_publication_authority_snapshot",
        identity._publication_authority_snapshot(
            result.receipt,
            result._loaded_runtime,
            result._loader_witness,
            library,
            forged_snapshot,
            result._runtime_query_authority,
            result._runtime_private_snapshot,
        ),
    )

    assert validate_hip_device_identity_receipt_v1(result.receipt) is result.receipt
    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        validate_hip_device_identity_result_v1(result)
    assert caught.value.code == "hip_device_identity_result_publication_invalid"


def test_loader_rejects_path_swap_between_hash_and_dlopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path = _compile_runtime_library(
        tmp_path,
        _FAKE_RUNTIME_SOURCE,
        "libsnapshot_hip_runtime",
    )
    replacement_path = _compile_runtime_library(
        tmp_path,
        _FAKE_RUNTIME_SOURCE.replace(
            "Fake Loader AMD GPU",
            "Replacement Runtime GPU",
        ),
        "libreplacement_hip_runtime",
    )
    original_digest = native._sha256_file(original_path)
    original_sha256_fd = native._sha256_fd
    hash_calls = 0

    def _hash_then_swap_path(descriptor: int) -> str:
        nonlocal hash_calls
        digest = original_sha256_fd(descriptor)
        hash_calls += 1
        if hash_calls == 1:
            os.replace(replacement_path, original_path)
        return digest

    monkeypatch.setattr(native, "_sha256_fd", _hash_then_swap_path)
    with pytest.raises(HipNativeRuntimeError) as caught:
        load_hip_native_runtime(original_path)

    assert caught.value.code == "hip_runtime_library_changed_during_load"
    assert caught.value.runtime_loaded
    assert hash_calls == 1
    assert native._sha256_file(original_path) != original_digest


def test_loader_rejects_parent_directory_swap_during_snapshot_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_directory = tmp_path / "runtime-current"
    replacement_directory = tmp_path / "runtime-replacement"
    displaced_directory = tmp_path / "runtime-displaced"
    original_directory.mkdir()
    replacement_directory.mkdir()
    original_path = _compile_runtime_library(
        original_directory,
        _FAKE_RUNTIME_SOURCE,
        "libamdhip64",
    )
    replacement_path = _compile_runtime_library(
        replacement_directory,
        _FAKE_RUNTIME_SOURCE.replace(
            "Fake Loader AMD GPU",
            "Replacement Runtime GPU",
        ),
        "libamdhip64",
    )
    original_digest = native._sha256_file(original_path)
    replacement_digest = native._sha256_file(replacement_path)
    original_sha256_fd = native._sha256_fd
    hash_calls = 0

    def _hash_then_swap_parent_directories(descriptor: int) -> str:
        nonlocal hash_calls
        digest = original_sha256_fd(descriptor)
        hash_calls += 1
        if hash_calls == 1:
            os.replace(original_directory, displaced_directory)
            os.replace(replacement_directory, original_directory)
        return digest

    monkeypatch.setattr(native, "_sha256_fd", _hash_then_swap_parent_directories)
    with pytest.raises(HipNativeRuntimeError) as caught:
        load_hip_native_runtime(original_path)

    assert caught.value.code == "hip_runtime_library_changed_during_load"
    assert caught.value.runtime_loaded
    assert hash_calls == 3
    assert native._sha256_file(original_path) == replacement_digest
    assert native._sha256_file(original_path) != original_digest


def test_probe_reports_parent_directory_swap_as_valid_unavailable_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_directory = tmp_path / "probe-current"
    replacement_directory = tmp_path / "probe-replacement"
    displaced_directory = tmp_path / "probe-displaced"
    original_directory.mkdir()
    replacement_directory.mkdir()
    original_path = _compile_runtime_library(
        original_directory,
        _FAKE_RUNTIME_SOURCE,
        "libamdhip64",
    )
    _compile_runtime_library(
        replacement_directory,
        _FAKE_RUNTIME_SOURCE.replace(
            "Fake Loader AMD GPU",
            "Replacement Runtime GPU",
        ),
        "libamdhip64",
    )
    original_digest = native._sha256_file(original_path)
    original_sha256_fd = native._sha256_fd
    hash_calls = 0

    def _hash_then_swap_parent_directories(descriptor: int) -> str:
        nonlocal hash_calls
        digest = original_sha256_fd(descriptor)
        hash_calls += 1
        if hash_calls == 1:
            os.replace(original_directory, displaced_directory)
            os.replace(replacement_directory, original_directory)
        return digest

    monkeypatch.setattr(native, "_sha256_fd", _hash_then_swap_parent_directories)
    receipt = native.probe_hip_capability(runtime_library=original_path)

    assert receipt.status == "unavailable"
    assert receipt.status_code == "hip_runtime_library_changed_during_load"
    assert receipt.capabilities.runtime_loaded
    assert not receipt.capabilities.runtime_initialized
    assert receipt.library.loaded_name == str(original_path.resolve(strict=True))
    assert receipt.library.sha256 == original_digest
    assert hash_calls == 3
    assert receipt.to_dict()["status_code"] == receipt.status_code


def test_missing_mandatory_symbol_preserves_loader_and_probe_failure_contract(
    tmp_path: Path,
) -> None:
    library = _compile_runtime_library(
        tmp_path,
        _FAKE_RUNTIME_SOURCE.replace(
            "int hipGetDeviceCount(",
            "int fakeMissingHipGetDeviceCount(",
        ),
        "libmissing_required_symbol",
    )

    with pytest.raises(HipNativeRuntimeError) as caught:
        load_hip_native_runtime(library)
    assert caught.value.code == "hip_runtime_symbol_missing"
    assert caught.value.runtime_loaded
    assert caught.value.library.resolved_path == str(library.resolve(strict=True))
    assert caught.value.library.sha256 == native._sha256_file(library)

    receipt = native.probe_hip_capability(runtime_library=library)
    assert receipt.status == "unavailable"
    assert receipt.status_code == "hip_runtime_symbol_missing"
    assert receipt.library.resolved_path == str(library.resolve(strict=True))
    assert receipt.library.sha256 == native._sha256_file(library)


def test_receipt_schema_is_strict_draft_2020_12_and_accepts_canonical_payload(
    native_harness: _NativeHarness,
) -> None:
    manifest = _attest(native_harness).to_manifest()
    validator = identity._schema_validator()
    schema = validator.schema

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert not list(validator.iter_errors(manifest))
    for definition in (
        "library",
        "device",
        "versions",
        "gcnArchitecture",
        "architectureBinding",
        "telemetry",
        "claims",
    ):
        assert schema["$defs"][definition]["additionalProperties"] is False


def test_receipt_validator_rejects_additional_properties_at_every_object_boundary(
    native_harness: _NativeHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _attest(native_harness).receipt
    original_payload = identity._receipt_payload
    container_paths = (
        (),
        ("library",),
        ("device",),
        ("versions",),
        ("architecture",),
        ("architecture", "runtime"),
        ("architecture", "expected_compiled"),
        ("telemetry",),
        ("claims",),
    )

    for container_path in container_paths:

        def payload_with_extra_key(
            value: Any,
            *,
            include_hash: bool,
            path: tuple[str, ...] = container_path,
        ) -> dict[str, Any]:
            payload = original_payload(value, include_hash=include_hash)
            target = payload
            for segment in path:
                target = target[segment]
            target["unexpected_key"] = "forbidden"
            return payload

        monkeypatch.setattr(identity, "_receipt_payload", payload_with_extra_key)
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            validate_hip_device_identity_receipt_v1(receipt)
        assert caught.value.code == "hip_device_identity_receipt_schema_invalid"
        assert caught.value.path == (
            "/" if not container_path else "/" + "/".join(container_path)
        )


def test_receipt_validator_schema_rejects_boolean_integer_type_confusion(
    native_harness: _NativeHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _attest(native_harness).receipt
    original_payload = identity._receipt_payload
    confused_values = (
        (("device", "selected_ordinal"), False),
        (("versions", "runtime"), True),
        (("architecture", "base_matches"), 1),
        (("telemetry", "hip_init_call_count"), True),
        (("claims", "signed_evidence"), 0),
        (("promotion_eligible",), 0),
    )

    for field_path, confused_value in confused_values:

        def payload_with_confused_type(
            value: Any,
            *,
            include_hash: bool,
            path: tuple[str, ...] = field_path,
            replacement: Any = confused_value,
        ) -> dict[str, Any]:
            payload = original_payload(value, include_hash=include_hash)
            target = payload
            for segment in path[:-1]:
                target = target[segment]
            target[path[-1]] = replacement
            return payload

        monkeypatch.setattr(identity, "_receipt_payload", payload_with_confused_type)
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            validate_hip_device_identity_receipt_v1(receipt)
        assert caught.value.code == "hip_device_identity_receipt_schema_invalid"
        assert caught.value.path == "/" + "/".join(field_path)


def test_structural_receipt_is_deterministic_but_result_requires_exact_runtime(
    native_harness: _NativeHarness,
    tmp_path: Path,
) -> None:
    first = _attest(native_harness)
    second = _attest(native_harness)
    assert first.receipt.receipt_hash == second.receipt.receipt_hash

    other_library = tmp_path / "libfake_hip_identity_runtime_copy.so"
    other_library.write_bytes(
        Path(native_harness.runtime.library_identity.resolved_path).read_bytes()
    )
    other_runtime = load_hip_native_runtime(other_library)
    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        validate_hip_device_identity_result_v1(
            first,
            expected_loaded_runtime=other_runtime,
        )
    assert caught.value.code == "hip_device_identity_result_runtime_mismatch"


def test_coherently_rehashed_structural_receipt_cannot_replace_local_publication(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)
    forged_device = replace(result.receipt.device, name="Coherently Forged GPU")
    forged_receipt = _coherently_rehash(result.receipt, device=forged_device)

    # Serialized validation is intentionally structural and non-promoting.
    assert validate_hip_device_identity_receipt_v1(forged_receipt) is forged_receipt
    forged_result = replace(result, receipt=forged_receipt)
    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        validate_hip_device_identity_result_v1(forged_result)
    assert caught.value.code == "hip_device_identity_result_publication_invalid"


def test_coherent_receipt_and_rebuilt_publication_snapshot_remain_unpublished(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)
    forged_receipt = _coherently_rehash(
        result.receipt,
        device=replace(result.receipt.device, name="Coherently Forged GPU"),
    )
    rebuilt_snapshot = identity._publication_authority_snapshot(
        forged_receipt,
        result._loaded_runtime,
        result._loader_witness,
        result._runtime_library_identity,
        result._runtime_library_snapshot,
        result._runtime_query_authority,
        result._runtime_private_snapshot,
    )
    forged_result = replace(
        result,
        receipt=forged_receipt,
        _publication_authority_snapshot=rebuilt_snapshot,
    )

    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        validate_hip_device_identity_result_v1(
            forged_result,
            expected_loaded_runtime=native_harness.runtime,
        )
    assert caught.value.code == "hip_device_identity_result_publication_invalid"


def test_result_copy_deepcopy_and_pickle_cannot_clone_publication_authority(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)

    clones = [replace(result)]
    for copier in (copy.copy, copy.deepcopy):
        try:
            clones.append(copier(result))
        except (copy.Error, FrozenInstanceError, TypeError, ValueError):
            pass
    for clone in clones:
        assert clone is not result
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            validate_hip_device_identity_result_v1(clone)
        assert caught.value.code == "hip_device_identity_result_publication_invalid"

    try:
        payload = pickle.dumps(result)
    except (AttributeError, TypeError, ValueError, pickle.PicklingError):
        return
    clone = pickle.loads(payload)
    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        validate_hip_device_identity_result_v1(clone)
    assert caught.value.code == "hip_device_identity_result_publication_invalid"


@pytest.mark.parametrize(
    ("owner", "member_name"),
    (
        (LoadedHipRuntime, "hip_device_get_name"),
        (LoadedHipRuntime, "bind"),
        (native._PrivateHipCdllFacade, "symbol_address"),
    ),
)
def test_runtime_class_callable_authority_patch_fails_before_queries(
    native_harness: _NativeHarness,
    monkeypatch: pytest.MonkeyPatch,
    owner: type[Any],
    member_name: str,
) -> None:
    monkeypatch.setattr(owner, member_name, lambda *_args, **_kwargs: (0, "Forged"))

    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        _attest(native_harness)

    assert caught.value.code == (
        "hip_device_identity_runtime_callable_authority_invalid"
    )
    assert native_harness.call_counts == (0, 0, 0, 0, 0, 0, 0, 0)


def test_result_validation_rejects_post_attestation_class_callable_patch(
    native_harness: _NativeHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _attest(native_harness)
    monkeypatch.setattr(
        LoadedHipRuntime,
        "hip_device_get_name",
        lambda *_args: (0, "Forged"),
    )

    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        validate_hip_device_identity_result_v1(result)
    assert caught.value.code == (
        "hip_device_identity_runtime_callable_authority_invalid"
    )


def test_runtime_class_callable_code_drift_fails_before_queries(
    native_harness: _NativeHarness,
) -> None:
    member = vars(LoadedHipRuntime)["hip_device_get_name"]
    original_code = member.__code__

    def forged(_runtime: Any, _ordinal: int) -> tuple[int, str]:
        return 0, "Forged"

    member.__code__ = forged.__code__
    try:
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            _attest(native_harness)
        assert caught.value.code == (
            "hip_device_identity_runtime_callable_authority_invalid"
        )
        assert native_harness.call_counts == (0, 0, 0, 0, 0, 0, 0, 0)
    finally:
        member.__code__ = original_code


def test_loader_probe_callable_errcheck_drift_fails_before_queries(
    native_harness: _NativeHarness,
) -> None:
    operation = object.__getattribute__(
        native_harness.runtime,
        "_hip_device_get_name",
    )
    original_errcheck = getattr(operation, "errcheck", None)
    operation.errcheck = lambda result, _function, _arguments: result
    try:
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            _attest(native_harness)
        assert caught.value.code == ("hip_device_identity_runtime_provenance_invalid")
        assert native_harness.call_counts == (0, 0, 0, 0, 0, 0, 0, 0)
    finally:
        if original_errcheck is None:
            del operation.errcheck
        else:
            operation.errcheck = original_errcheck


def test_published_fresh_callable_mutation_invalidates_result(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)
    operation = result._runtime_query_authority.hip_device_get_name
    original_errcheck = getattr(operation, "errcheck", None)
    operation.errcheck = lambda value, _function, _arguments: value
    try:
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            validate_hip_device_identity_result_v1(result)
        assert caught.value.code == (
            "hip_device_identity_runtime_callable_authority_invalid"
        )
    finally:
        if original_errcheck is None:
            del operation.errcheck
        else:
            operation.errcheck = original_errcheck


def test_persistent_private_callable_replacement_cannot_publish_forged_name(
    native_harness: _NativeHarness,
) -> None:
    runtime = native_harness.runtime
    original = object.__getattribute__(runtime, "_hip_device_get_name")

    def forged_name(output: Any, length: int, ordinal: int) -> int:
        assert ordinal == 0
        forged = b"Forged Process-Local GPU\0"
        ctypes.memmove(output, forged, min(length, len(forged)))
        object.__setattr__(runtime, "_hip_device_get_name", original)
        return 0

    object.__setattr__(runtime, "_hip_device_get_name", forged_name)
    try:
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            _attest(native_harness)
        assert caught.value.code == ("hip_device_identity_runtime_provenance_invalid")
        assert native_harness.call_counts == (0, 0, 0, 0, 0, 0, 0, 0)
    finally:
        object.__setattr__(runtime, "_hip_device_get_name", original)


def test_loaded_runtime_private_slot_drift_invalidates_result(
    native_harness: _NativeHarness,
) -> None:
    result = _attest(native_harness)
    runtime = native_harness.runtime
    original = object.__getattribute__(runtime, "_hip_init")
    object.__setattr__(runtime, "_hip_init", lambda _flags=0: 0)
    try:
        with pytest.raises(HipDeviceIdentityV1Error) as caught:
            validate_hip_device_identity_result_v1(result)
        assert caught.value.code == ("hip_device_identity_runtime_provenance_invalid")
    finally:
        object.__setattr__(runtime, "_hip_init", original)


def test_forged_or_injected_runtime_is_rejected_before_calls() -> None:
    class ForgedRuntime:
        calls = 0

        def hip_init(self) -> int:
            self.calls += 1
            return 0

    forged = ForgedRuntime()
    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        attest_hip_device_identity_v1(  # type: ignore[arg-type]
            forged,
            device_ordinal=0,
            expected_compiled_architecture="gfx1030",
        )
    assert caught.value.code == "hip_device_identity_runtime_type_invalid"
    assert forged.calls == 0


def test_loader_registry_witness_is_required(
    native_harness: _NativeHarness,
) -> None:
    runtime = native_harness.runtime
    with native._LOADED_HIP_RUNTIME_WITNESS_LOCK:
        del native._LOADED_HIP_RUNTIME_WITNESSES[runtime]

    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        attest_hip_device_identity_v1(
            runtime,
            device_ordinal=0,
            expected_compiled_architecture="gfx1030",
        )
    assert caught.value.code == "hip_device_identity_runtime_provenance_invalid"
    assert native_harness.call_counts == (0, 0, 0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " gfx1030",
        "gfx000",
        "gfx10",
        "gfx1030:bad",
        "gfx1030:xnack+:xnack-",
        "gfx1030:xnack+:",
        "gfx1030:xnack+\n",
    ],
)
def test_invalid_gcn_architectures_fail_closed(raw: str) -> None:
    with pytest.raises(HipDeviceIdentityV1Error):
        normalize_hip_gcn_architecture_v1(raw)


def test_gcn_architecture_normalizes_base_features_and_case() -> None:
    architecture = normalize_hip_gcn_architecture_v1("GFX90A:XNACK-:SRAMECC+")

    assert architecture.raw == "GFX90A:XNACK-:SRAMECC+"
    assert architecture.base == "gfx90a"
    assert architecture.features == ("sramecc+", "xnack-")
    assert architecture.normalized == "gfx90a:sramecc+:xnack-"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "0000:0b:00",
        "0000:0b:20.0",
        "0000:100:00.0",
        "0000:0b:00.8",
        " 0000:0b:00.0",
    ],
)
def test_invalid_pci_bus_ids_fail_closed(raw: str) -> None:
    with pytest.raises(HipDeviceIdentityV1Error):
        normalize_hip_pci_bus_id_v1(raw)


def test_pci_bus_id_normalizes_case() -> None:
    assert normalize_hip_pci_bus_id_v1("0000:0B:1F.7") == "0000:0b:1f.7"


@pytest.mark.parametrize(
    ("mode_index", "mode_value", "expected_code"),
    [
        (0, 1, "hip_device_identity_gcn_arch_name_invalid"),
        (0, 2, "hip_device_identity_gcn_feature_invalid"),
        (0, 3, "hip_device_identity_architecture_base_mismatch"),
        (1, 1, "hip_device_identity_uuid_invalid"),
        (2, 1, "hip_device_identity_pci_bus_id_invalid"),
        (2, 2, "hip_device_identity_pci_bus_id_invalid"),
    ],
)
def test_runtime_identity_payload_failures_do_not_publish(
    native_harness: _NativeHarness,
    mode_index: int,
    mode_value: int,
    expected_code: str,
) -> None:
    native_harness.set_mode(mode_index, mode_value)

    with pytest.raises(HipDeviceIdentityV1Error) as caught:
        _attest(native_harness)

    assert caught.value.code == expected_code


def test_expected_compiled_architecture_type_and_device_ordinal_are_strict(
    native_harness: _NativeHarness,
) -> None:
    class TextSubclass(str):
        pass

    with pytest.raises(HipDeviceIdentityV1Error) as architecture_error:
        attest_hip_device_identity_v1(
            native_harness.runtime,
            device_ordinal=0,
            expected_compiled_architecture=TextSubclass("gfx1030"),
        )
    assert architecture_error.value.code == (
        "hip_device_identity_gcn_architecture_type_invalid"
    )

    with pytest.raises(HipDeviceIdentityV1Error) as ordinal_error:
        attest_hip_device_identity_v1(
            native_harness.runtime,
            device_ordinal=True,  # type: ignore[arg-type]
            expected_compiled_architecture="gfx1030",
        )
    assert ordinal_error.value.code == "hip_device_identity_device_ordinal_invalid"


def test_hash_relabel_library_and_signed_zero_forgery_fail_closed(
    native_harness: _NativeHarness,
) -> None:
    receipt = _attest(native_harness).receipt

    with pytest.raises(HipDeviceIdentityV1Error) as hash_error:
        validate_hip_device_identity_receipt_v1(
            replace(receipt, receipt_hash=identity._ZERO_HASH)
        )
    assert hash_error.value.code == "hip_device_identity_receipt_hash_invalid"

    relabeled = _coherently_rehash(receipt, actual_backend="test_double")
    with pytest.raises(HipDeviceIdentityV1Error) as relabel_error:
        validate_hip_device_identity_receipt_v1(relabeled)
    assert relabel_error.value.code == "hip_device_identity_receipt_semantics_invalid"

    injected_library = replace(receipt.library, discovery_source="injected")
    forged_library = _coherently_rehash(receipt, library=injected_library)
    with pytest.raises(HipDeviceIdentityV1Error) as library_error:
        validate_hip_device_identity_receipt_v1(forged_library)
    assert library_error.value.code == "hip_device_identity_library_source_invalid"

    signed_zero_device = replace(receipt.device, device_count=-0.0)  # type: ignore[arg-type]
    signed_zero = _coherently_rehash(receipt, device=signed_zero_device)
    with pytest.raises(HipDeviceIdentityV1Error) as signed_zero_error:
        validate_hip_device_identity_receipt_v1(signed_zero)
    assert signed_zero_error.value.code == "hip_device_identity_device_scalar_invalid"


def _hardware_required() -> bool:
    return os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE", "0") == "1"


def test_actual_local_gfx1030_uuid_pci_identity_without_device_work() -> None:
    required = _hardware_required()
    try:
        runtime = load_hip_native_runtime()
        result = attest_hip_device_identity_v1(
            runtime,
            device_ordinal=0,
            expected_compiled_architecture="gfx1030",
        )
    except (HipNativeRuntimeError, HipDeviceIdentityV1Error) as exc:
        if required:
            pytest.fail(f"Required local gfx1030 identity failed: {exc}")
        pytest.skip(f"Local gfx1030 identity unavailable without fallback: {exc}")

    receipt = result.receipt
    assert receipt.architecture.runtime.raw == "gfx1030"
    assert receipt.architecture.runtime.base == "gfx1030"
    assert receipt.device.name == "AMD Radeon RX 6900 XT"
    assert re.fullmatch(r"[0-9a-f]{32}", receipt.device.uuid_bytes_hex)
    assert receipt.device.uuid_bytes_hex != "0" * 32
    assert re.fullmatch(
        r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]",
        receipt.device.pci_bdf,
    )
    assert receipt.library.resolved_path
    assert receipt.library.sha256
    assert receipt.telemetry.device_allocation_count == 0
    assert receipt.telemetry.device_copy_count == 0
    assert receipt.telemetry.kernel_launch_count == 0
    assert receipt.telemetry.context_creation_count == 0
    assert receipt.telemetry.stream_creation_count == 0
    assert receipt.telemetry.fallback_count == 0
    source = inspect.getsource(identity)
    assert "hipMalloc" not in source
    assert "hipMemcpy" not in source
    assert "hipLaunchKernel" not in source
