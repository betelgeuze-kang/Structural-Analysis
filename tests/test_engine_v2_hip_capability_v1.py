from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.hip import native  # noqa: E402
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    HIP_ERROR_NO_DEVICE,
    discover_hip_runtime_library,
    probe_hip_capability,
)
from structural_analysis.engine_v2.backends.hip.types import (  # noqa: E402
    HIP_CAPABILITY_READY_CODE,
    HipCapabilityReceiptError,
    validate_hip_capability_receipt,
)


class FakeHipRuntime:
    library_name = "fake-libamdhip64.so"
    library_path: str | None = None

    def __init__(
        self,
        *,
        init_status: int = 0,
        count_status: int = 0,
        device_count: int = 2,
        name_status: int = 0,
        device_name: str = "Fake AMD GPU",
        runtime_status: int = 0,
        runtime_version: int = 60400000,
        driver_status: int = 0,
        driver_version: int = 60400001,
    ) -> None:
        self.init_status = init_status
        self.count_status = count_status
        self.device_count = device_count
        self.name_status = name_status
        self.device_name = device_name
        self.runtime_status = runtime_status
        self.runtime_version = runtime_version
        self.driver_status = driver_status
        self.driver_version = driver_version
        self.name_ordinals: list[int] = []

    def hip_init(self) -> int:
        return self.init_status

    def hip_get_device_count(self) -> tuple[int, int]:
        return self.count_status, self.device_count

    def hip_device_get_name(self, ordinal: int) -> tuple[int, str]:
        self.name_ordinals.append(ordinal)
        return self.name_status, self.device_name

    def hip_runtime_get_version(self) -> tuple[int, int]:
        return self.runtime_status, self.runtime_version

    def hip_driver_get_version(self) -> tuple[int, int]:
        return self.driver_status, self.driver_version

    def hip_error_string(self, status: int) -> str:
        return f"fake HIP error {status}"


def _schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "structural_analysis"
        / "schemas"
        / "hip_capability_receipt_v1.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def test_fake_runtime_ready_receipt_is_canonical_strict_and_immutable() -> None:
    runtime = FakeHipRuntime()

    receipt = probe_hip_capability(runtime=runtime, device_ordinal=1)
    repeated = probe_hip_capability(runtime=FakeHipRuntime(), device_ordinal=1)
    manifest = receipt.to_dict()

    Draft202012Validator.check_schema(_schema())
    Draft202012Validator(_schema()).validate(manifest)
    assert receipt.status == "ready"
    assert receipt.status_code == HIP_CAPABILITY_READY_CODE
    assert receipt.receipt_hash == repeated.receipt_hash
    assert receipt.device.name == "Fake AMD GPU"
    assert runtime.name_ordinals == [1]
    assert manifest["fallback_policy"] == "forbidden"
    assert manifest["fallback_used"] is False
    assert manifest["context_created"] is False
    assert manifest["model_residency_proven"] is False
    assert manifest["operator_execution_proven"] is False
    assert manifest["solver_execution_proven"] is False
    assert not ({"pointer", "stream", "handle"} & _all_keys(manifest))

    with pytest.raises(FrozenInstanceError):
        receipt.status = "unavailable"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        receipt.device.name = "mutated"  # type: ignore[misc]


def test_resolved_injected_library_has_exact_content_sha(tmp_path: Path) -> None:
    library = tmp_path / "libamdhip64-fake.so"
    library.write_bytes(b"fake native HIP runtime bytes\0")
    runtime = FakeHipRuntime()
    runtime.library_path = str(library)

    receipt = probe_hip_capability(runtime=runtime)

    assert receipt.library.resolved_path == str(library.resolve())
    expected = "sha256:" + hashlib.sha256(library.read_bytes()).hexdigest()
    assert receipt.library.sha256 == expected


def test_canonical_hash_and_proof_boundary_tampering_fail_closed() -> None:
    receipt = probe_hip_capability(runtime=FakeHipRuntime())

    with pytest.raises(HipCapabilityReceiptError) as hash_error:
        validate_hip_capability_receipt(replace(receipt, message="forged"))
    assert hash_error.value.code == "hip_receipt_hash_mismatch"

    with pytest.raises(HipCapabilityReceiptError) as proof_error:
        validate_hip_capability_receipt(
            replace(receipt, operator_execution_proven=True)
        )
    assert proof_error.value.code == "hip_receipt_schema_invalid"


def test_missing_explicit_runtime_returns_stable_unavailable_receipt(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing" / "libamdhip64.so"

    receipt = probe_hip_capability(runtime_library=missing)

    assert receipt.status == "unavailable"
    assert receipt.status_code == "hip_runtime_library_not_found"
    assert receipt.library.discovery_source == "explicit"
    assert receipt.library.requested_name == str(missing)
    assert receipt.library.loaded_name is None
    assert receipt.capabilities.runtime_loaded is False
    Draft202012Validator(_schema()).validate(receipt.to_dict())


@pytest.mark.parametrize(
    ("runtime", "ordinal", "expected_code"),
    [
        (FakeHipRuntime(init_status=7), 0, "hip_init_failed"),
        (FakeHipRuntime(count_status=8), 0, "hip_device_count_failed"),
        (
            FakeHipRuntime(count_status=HIP_ERROR_NO_DEVICE, device_count=0),
            0,
            "hip_no_devices",
        ),
        (FakeHipRuntime(device_count=0), 0, "hip_no_devices"),
        (FakeHipRuntime(device_count=1), 1, "hip_device_ordinal_unavailable"),
        (FakeHipRuntime(name_status=9), 0, "hip_device_name_failed"),
        (FakeHipRuntime(device_name=""), 0, "hip_device_name_invalid"),
        (
            FakeHipRuntime(runtime_status=10),
            0,
            "hip_runtime_version_failed",
        ),
        (FakeHipRuntime(driver_status=11), 0, "hip_driver_version_failed"),
    ],
)
def test_fake_runtime_failures_have_stable_unavailable_codes(
    runtime: FakeHipRuntime,
    ordinal: int,
    expected_code: str,
) -> None:
    receipt = probe_hip_capability(runtime=runtime, device_ordinal=ordinal)

    assert receipt.status == "unavailable"
    assert receipt.status_code == expected_code
    assert receipt.fallback_policy == "forbidden"
    assert receipt.fallback_used is False
    validate_hip_capability_receipt(receipt)


def test_unavailable_code_cannot_be_reused_with_ready_capability_facts() -> None:
    ready = probe_hip_capability(runtime=FakeHipRuntime())

    with pytest.raises(HipCapabilityReceiptError) as error:
        validate_hip_capability_receipt(
            replace(
                ready,
                status="unavailable",
                status_code="hip_init_failed",
            )
        )

    assert error.value.code in {
        "hip_receipt_semantics_invalid",
        "hip_receipt_hash_mismatch",
    }


def test_explicit_candidate_is_resolved_without_loading(tmp_path: Path) -> None:
    library = tmp_path / "libamdhip64.so"
    library.write_bytes(b"not an ELF, discovery only")

    candidate = discover_hip_runtime_library(library)

    assert candidate is not None
    assert candidate.discovery_source == "explicit"
    assert candidate.resolved_path == str(library.resolve())
    assert candidate.load_name == str(library.resolve())


def test_probe_arguments_are_strict() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        probe_hip_capability(runtime=FakeHipRuntime(), device_ordinal=-1)
    with pytest.raises(TypeError, match="integer"):
        probe_hip_capability(runtime=FakeHipRuntime(), device_ordinal=True)
    with pytest.raises(ValueError, match="mutually exclusive"):
        probe_hip_capability(
            runtime=FakeHipRuntime(), runtime_library="libamdhip64.so"
        )


def test_actual_host_probe_is_ready_or_explicitly_unavailable() -> None:
    receipt = probe_hip_capability()

    assert receipt.status in {"ready", "unavailable"}
    if receipt.status == "ready":
        assert receipt.status_code == HIP_CAPABILITY_READY_CODE
        assert receipt.library.sha256 is not None or receipt.library.resolved_path is None
        assert receipt.device.device_count is not None
        assert receipt.device.name
    else:
        assert receipt.status_code != HIP_CAPABILITY_READY_CODE
    Draft202012Validator(_schema()).validate(receipt.to_dict())


def test_native_probe_has_no_cpu_solver_dependency() -> None:
    source = inspect.getsource(native)

    assert "cpu_reference" not in source
    assert "solve_linear_static" not in source
