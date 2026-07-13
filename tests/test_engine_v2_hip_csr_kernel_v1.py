from __future__ import annotations

import ctypes
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any

from jsonschema import Draft202012Validator
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.hip import kernel_artifact as artifact  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_ambient_hip_toolchain_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in artifact.HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES:
        monkeypatch.delenv(name, raising=False)


class FakeFunction:
    def __init__(self, callback: Any) -> None:
        self.callback = callback
        self.argtypes: list[Any] | None = None
        self.restype: Any = None

    def __call__(self, *args: Any) -> Any:
        return self.callback(*args)


class FakeKernelCdll:
    def __init__(
        self,
        *,
        targets: str = "gfx1030",
        abi_version: int = 1,
        block_size: int = 256,
        launch_status: int = 0,
    ) -> None:
        self.last_request: artifact._ResidualJvpRequestV1 | None = None
        self.engine_v2_hip_csr_abi_version = FakeFunction(
            lambda: abi_version
        )
        self.engine_v2_hip_csr_block_size = FakeFunction(lambda: block_size)
        self.engine_v2_hip_csr_targets = FakeFunction(
            lambda: targets.encode("ascii")
        )
        self.engine_v2_hip_csr_buffer_view_size = FakeFunction(
            lambda: ctypes.sizeof(artifact._BufferViewV1)
        )
        self.engine_v2_hip_csr_canonical_csr_size = FakeFunction(
            lambda: ctypes.sizeof(artifact._CanonicalCsrV1)
        )
        self.engine_v2_hip_csr_residual_jvp_request_size = FakeFunction(
            lambda: ctypes.sizeof(artifact._ResidualJvpRequestV1)
        )

        def launch(request_pointer: Any) -> int:
            pointer = ctypes.cast(
                request_pointer,
                ctypes.POINTER(artifact._ResidualJvpRequestV1),
            )
            self.last_request = artifact._ResidualJvpRequestV1.from_buffer_copy(
                ctypes.string_at(
                    pointer, ctypes.sizeof(artifact._ResidualJvpRequestV1)
                )
            )
            return launch_status

        def last_error(output: Any, capacity: int) -> int:
            message = b"fake bounded launch error\0"
            length = min(len(message), int(capacity))
            ctypes.memmove(output, message, length)
            return max(0, length - 1)

        self.engine_v2_hip_csr_launch = FakeFunction(launch)
        self.engine_v2_hip_csr_last_error = FakeFunction(last_error)


class FakeCdllLoader:
    def __init__(self, cdll: FakeKernelCdll) -> None:
        self.cdll = cdll
        self.calls: list[tuple[str, int]] = []

    def __call__(self, path: str, *, mode: int) -> FakeKernelCdll:
        self.calls.append((path, mode))
        return self.cdll


class FakeHipccRunner:
    def __init__(
        self,
        *,
        version_output: str = "HIP version: 6.0.32831\nAMD clang 17.0.0",
        build_returncode: int = 0,
    ) -> None:
        self.version_output = version_output
        self.build_returncode = build_returncode
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: Any) -> Any:
        self.calls.append(list(command))
        if command[-1] == "--version":
            return subprocess.CompletedProcess(
                command, 0, stdout=self.version_output, stderr=""
            )
        if self.build_returncode == 0:
            output = Path(command[command.index("-o") + 1])
            output.write_bytes(b"fake HIP CSR shared artifact\0")
        return subprocess.CompletedProcess(
            command,
            self.build_returncode,
            stdout="",
            stderr="fake compiler failure" if self.build_returncode else "",
        )


def _schema() -> dict[str, Any]:
    path = (
        REPO_ROOT
        / "src"
        / "structural_analysis"
        / "schemas"
        / "hip_csr_kernel_artifact_v1.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_toolchain(tmp_path: Path, version: str = "6.0") -> tuple[Path, Path]:
    root = tmp_path / f"rocm-{version}"
    hipcc = root / "bin" / "hipcc"
    hipcc.parent.mkdir(parents=True)
    hipcc.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hipcc.chmod(hipcc.stat().st_mode | stat.S_IXUSR)
    libraries = root / "amdgcn" / "bitcode"
    libraries.mkdir(parents=True)
    (libraries / "ocml.bc").write_bytes(f"ocml-{version}".encode())
    (libraries / "ockl.bc").write_bytes(f"ockl-{version}".encode())
    return hipcc, libraries


def _build_fixture(
    tmp_path: Path,
    *,
    targets: tuple[str, ...] = ("gfx1030",),
    cdll: FakeKernelCdll | None = None,
) -> tuple[
    artifact.HipCsrKernelArtifactReceipt,
    Path,
    FakeHipccRunner,
    FakeCdllLoader,
]:
    hipcc, libraries = _fake_toolchain(tmp_path)
    runner = FakeHipccRunner()
    loader = FakeCdllLoader(
        cdll or FakeKernelCdll(targets=",".join(sorted(targets)))
    )
    output = tmp_path / "engine-v2-csr.so"
    receipt = artifact.build_hip_csr_kernel_artifact(
        output,
        targets=targets,
        hipcc_path=hipcc,
        device_libraries_path=libraries,
        runner=runner,
        cdll_loader=loader,
    )
    return receipt, output, runner, loader


def test_build_receipt_is_strict_hashed_immutable_and_non_promoting(
    tmp_path: Path,
) -> None:
    receipt, output, runner, loader = _build_fixture(
        tmp_path, targets=("gfx1100", "gfx1030")
    )
    manifest = receipt.to_dict()

    Draft202012Validator.check_schema(_schema())
    Draft202012Validator(_schema()).validate(manifest)
    assert receipt.schema_version == (
        "structural-analysis-hip-csr-kernel-artifact.v1"
    )
    assert receipt.entrypoint == "engine_v2_hip_csr_launch"
    assert receipt.abi_version == 1
    assert receipt.block_size == 256
    assert receipt.targets == ("gfx1030", "gfx1100")
    assert receipt.artifact_hash == receipt.library_hash
    assert receipt.library_hash == (
        "sha256:" + hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert receipt.source_hash.startswith("sha256:")
    assert receipt.abi_hash.startswith("sha256:")
    assert receipt.build_target_hash.startswith("sha256:")
    assert receipt.device_libraries.matching_compiler_root_asserted is True
    assert receipt.device_libraries.matching_hip_version_asserted is True
    assert receipt.compiler.ambient_override_policy == "reject_if_present"
    assert receipt.compiler.ambient_overrides_absent is True
    assert receipt.compiler.rejected_environment_override_names == (
        artifact.HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES
    )
    assert receipt.fallback_policy == "forbidden"
    assert receipt.fallback_used is False
    assert receipt.operator_execution_proven is False
    assert receipt.numerical_parity_proven is False
    assert receipt.speedup_proven is False
    assert loader.calls[0][1] == getattr(ctypes, "RTLD_LOCAL", 0)

    build_command = runner.calls[-1]
    for flag in artifact.HIP_CSR_KERNEL_REQUIRED_FLAGS:
        assert flag in build_command
    assert "--offload-arch=gfx1030" in build_command
    assert "--offload-arch=gfx1100" in build_command
    assert any(row.startswith("--rocm-device-lib-path=") for row in build_command)
    assert '-DENGINE_V2_HIP_CSR_TARGETS="gfx1030,gfx1100"' in build_command

    with pytest.raises(FrozenInstanceError):
        receipt.abi_version = 2  # type: ignore[misc]


def test_runtime_loader_verifies_hash_abi_targets_and_builds_descriptor(
    tmp_path: Path,
) -> None:
    cdll = FakeKernelCdll()
    receipt, output, _, _ = _build_fixture(tmp_path, cdll=cdll)
    loader = FakeCdllLoader(cdll)

    kernel = artifact.load_hip_csr_kernel_artifact(
        output,
        expected_sha256=receipt.library_hash,
        artifact_receipt=receipt,
        cdll_loader=loader,
    )
    kernel.launch_residual_jvp(
        row_count=6,
        nnz_count=12,
        row_ptr=0x1000,
        column_indices=0x2000,
        values=0x3000,
        load=0x4000,
        state=0x5000,
        direction=0x6000,
        residual_out=0x7000,
        jvp_out=0x8000,
        stream=0x9000,
    )

    assert kernel.artifact_receipt is receipt
    assert loader.calls == [
        (str(output.resolve()), getattr(ctypes, "RTLD_LOCAL", 0))
    ]
    request = cdll.last_request
    assert request is not None
    assert request.abi_version == 1
    assert request.struct_size == ctypes.sizeof(artifact._ResidualJvpRequestV1)
    assert request.csr.dof_count == 6
    assert request.csr.nnz_count == 12
    assert request.csr.row_ptr.dtype == 1
    assert request.csr.row_ptr.shape[0] == 7
    assert request.csr.row_ptr.byte_length == 28
    assert request.csr.values.dtype == 2
    assert request.csr.values.shape[0] == 12
    assert request.csr.values.byte_length == 96
    assert request.load.shape[0] == 6
    assert request.load.strides[0] == 8
    assert request.residual_out.pointer == 0x7000
    assert request.jvp_out.pointer == 0x8000
    assert request.stream == 0x9000


def test_launch_failure_uses_stable_code_and_bounded_native_error(
    tmp_path: Path,
) -> None:
    build_cdll = FakeKernelCdll()
    receipt, output, _, _ = _build_fixture(tmp_path, cdll=build_cdll)
    failing_cdll = FakeKernelCdll(launch_status=-2007)
    kernel = artifact.load_hip_csr_kernel_artifact(
        output,
        expected_sha256=receipt.library_hash,
        artifact_receipt=receipt,
        cdll_loader=FakeCdllLoader(failing_cdll),
    )

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        kernel.launch_residual_jvp(
            row_count=1,
            nnz_count=1,
            row_ptr=1,
            column_indices=2,
            values=3,
            load=4,
            state=5,
            direction=6,
            residual_out=7,
            jvp_out=8,
            stream=9,
        )

    assert caught.value.code == "hip_csr_kernel_launch_failed"
    assert "fake bounded launch error" in caught.value.message
    assert len(caught.value.message) <= 512


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("row_count", 0),
        ("nnz_count", 0),
        ("stream", 0),
        ("values", None),
    ],
)
def test_friendly_launch_rejects_invalid_counts_and_null_pointers(
    tmp_path: Path, field: str, value: Any
) -> None:
    cdll = FakeKernelCdll()
    receipt, output, _, _ = _build_fixture(tmp_path, cdll=cdll)
    kernel = artifact.load_hip_csr_kernel_artifact(
        output,
        expected_sha256=receipt.library_hash,
        artifact_receipt=receipt,
        cdll_loader=FakeCdllLoader(cdll),
    )
    arguments: dict[str, Any] = {
        "row_count": 1,
        "nnz_count": 1,
        "row_ptr": 1,
        "column_indices": 2,
        "values": 3,
        "load": 4,
        "state": 5,
        "direction": 6,
        "residual_out": 7,
        "jvp_out": 8,
        "stream": 9,
    }
    arguments[field] = value

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        kernel.launch_residual_jvp(**arguments)
    assert caught.value.code == "hip_csr_launch_argument_invalid"
    assert cdll.last_request is None


def test_explicit_content_hash_mismatch_fails_before_cdll_load(
    tmp_path: Path,
) -> None:
    receipt, output, _, _ = _build_fixture(tmp_path)
    output.write_bytes(output.read_bytes() + b"tampered")
    loader = FakeCdllLoader(FakeKernelCdll())

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.load_hip_csr_kernel_artifact(
            output,
            expected_sha256=receipt.library_hash,
            artifact_receipt=receipt,
            cdll_loader=loader,
        )

    assert caught.value.code == "hip_csr_artifact_hash_mismatch"
    assert loader.calls == []


def test_artifact_read_error_is_wrapped_before_cdll_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, output, _, _ = _build_fixture(tmp_path)
    loader = FakeCdllLoader(FakeKernelCdll())

    def denied(_: Path) -> str:
        raise PermissionError("artifact read denied")

    monkeypatch.setattr(artifact, "_sha256_file", denied)
    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.load_hip_csr_kernel_artifact(
            output,
            expected_sha256=receipt.library_hash,
            artifact_receipt=receipt,
            cdll_loader=loader,
        )

    assert caught.value.code == "hip_csr_artifact_hash_failed"
    assert caught.value.path == "/library_hash"
    assert "PermissionError" in caught.value.message
    assert loader.calls == []


@pytest.mark.parametrize(
    ("cdll", "expected_code"),
    [
        (FakeKernelCdll(abi_version=2), "hip_csr_artifact_abi_mismatch"),
        (FakeKernelCdll(block_size=128), "hip_csr_artifact_abi_mismatch"),
        (FakeKernelCdll(targets="gfx1100"), "hip_csr_artifact_target_mismatch"),
    ],
)
def test_loader_rejects_native_metadata_mismatch(
    tmp_path: Path, cdll: FakeKernelCdll, expected_code: str
) -> None:
    receipt, output, _, _ = _build_fixture(tmp_path)

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.load_hip_csr_kernel_artifact(
            output,
            expected_sha256=receipt.library_hash,
            artifact_receipt=receipt,
            cdll_loader=FakeCdllLoader(cdll),
        )
    assert caught.value.code == expected_code


def test_prebuilt_loader_fails_closed_when_artifact_is_unavailable(
    tmp_path: Path,
) -> None:
    receipt, output, _, _ = _build_fixture(tmp_path)
    output.unlink()

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.load_hip_csr_kernel_artifact(
            output,
            expected_sha256=receipt.library_hash,
            artifact_receipt=receipt,
            cdll_loader=FakeCdllLoader(FakeKernelCdll()),
        )
    assert caught.value.code == "hip_csr_prebuilt_artifact_unavailable"


def test_receipt_validation_is_offline_but_loader_still_checks_artifact(
    tmp_path: Path,
) -> None:
    receipt, output, _, _ = _build_fixture(tmp_path)
    shutil.rmtree(tmp_path / "rocm-6.0")

    assert artifact.validate_hip_csr_kernel_artifact_receipt(receipt) is receipt
    loaded = artifact.load_hip_csr_kernel_artifact(
        output,
        expected_sha256=receipt.library_hash,
        artifact_receipt=receipt,
        cdll_loader=FakeCdllLoader(FakeKernelCdll()),
    )
    assert loaded.artifact_receipt.receipt_hash == receipt.receipt_hash


def test_json_manifest_parse_and_prebuilt_load_roundtrip_is_offline(
    tmp_path: Path,
) -> None:
    receipt, output, _, _ = _build_fixture(tmp_path)
    serialized = json.dumps(
        receipt.to_manifest(), sort_keys=True, separators=(",", ":")
    )
    shutil.rmtree(tmp_path / "rocm-6.0")

    parsed = artifact.parse_hip_csr_kernel_artifact_receipt(
        json.loads(serialized)
    )
    loaded = artifact.load_hip_csr_kernel_artifact(
        output,
        expected_sha256=parsed.library_hash,
        artifact_receipt=parsed,
        cdll_loader=FakeCdllLoader(FakeKernelCdll()),
    )

    assert isinstance(parsed, artifact.HipCsrKernelArtifactReceipt)
    assert isinstance(parsed.descriptor_layout, artifact.HipCsrDescriptorLayout)
    assert isinstance(parsed.compiler, artifact.HipCsrCompilerIdentity)
    assert isinstance(
        parsed.device_libraries, artifact.HipCsrDeviceLibrariesIdentity
    )
    assert parsed.to_manifest() == receipt.to_manifest()
    assert loaded.artifact_receipt.receipt_hash == receipt.receipt_hash


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        (lambda manifest: manifest.__setitem__("abi_version", "1"), "/abi_version"),
        (
            lambda manifest: manifest.__setitem__("unexpected", True),
            "/",
        ),
        (
            lambda manifest: manifest["compiler"].__setitem__(
                "unexpected", "value"
            ),
            "/compiler",
        ),
    ],
)
def test_manifest_parser_rejects_wrong_types_and_extra_keys(
    tmp_path: Path, mutation: Any, expected_path: str
) -> None:
    receipt, _, _, _ = _build_fixture(tmp_path)
    manifest = json.loads(json.dumps(receipt.to_manifest()))
    mutation(manifest)

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.parse_hip_csr_kernel_artifact_receipt(manifest)

    assert caught.value.code == "hip_csr_artifact_receipt_schema_invalid"
    assert caught.value.path == expected_path


def test_manifest_parser_rejects_hash_tampering_and_non_mapping(
    tmp_path: Path,
) -> None:
    receipt, _, _, _ = _build_fixture(tmp_path)
    manifest = json.loads(json.dumps(receipt.to_manifest()))
    manifest["source_hash"] = "sha256:" + ("1" * 64)

    with pytest.raises(artifact.HipCsrKernelArtifactError) as tamper_error:
        artifact.parse_hip_csr_kernel_artifact_receipt(manifest)
    assert tamper_error.value.code == (
        "hip_csr_artifact_receipt_hash_mismatch"
    )
    assert tamper_error.value.path == "/receipt_hash"

    with pytest.raises(artifact.HipCsrKernelArtifactError) as type_error:
        artifact.parse_hip_csr_kernel_artifact_receipt([])  # type: ignore[arg-type]
    assert type_error.value.code == "hip_csr_artifact_receipt_type_invalid"
    assert type_error.value.path == "/"


def test_receipt_claim_or_hash_tampering_fails_closed(tmp_path: Path) -> None:
    receipt, _, _, _ = _build_fixture(tmp_path)

    with pytest.raises(artifact.HipCsrKernelArtifactError) as claim_error:
        artifact.validate_hip_csr_kernel_artifact_receipt(
            replace(receipt, speedup_proven=True)
        )
    assert claim_error.value.code == "hip_csr_artifact_receipt_schema_invalid"

    with pytest.raises(artifact.HipCsrKernelArtifactError) as hash_error:
        artifact.validate_hip_csr_kernel_artifact_receipt(
            replace(receipt, source_hash="sha256:" + ("1" * 64))
        )
    assert hash_error.value.code == "hip_csr_artifact_receipt_hash_mismatch"


def test_probe_rejects_cross_version_or_external_device_libraries(
    tmp_path: Path,
) -> None:
    hipcc, _ = _fake_toolchain(tmp_path / "compiler", "6.0")
    _, old_libraries = _fake_toolchain(tmp_path / "repository", "5.7.1")

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.probe_hip_csr_kernel_toolchain(
            hipcc_path=hipcc,
            device_libraries_path=old_libraries,
            runner=FakeHipccRunner(),
        )
    assert caught.value.code == "hip_csr_device_libraries_mismatch"


def test_probe_requires_parseable_compiler_identity_and_required_bitcode(
    tmp_path: Path,
) -> None:
    hipcc, libraries = _fake_toolchain(tmp_path)

    with pytest.raises(artifact.HipCsrKernelArtifactError) as identity_error:
        artifact.probe_hip_csr_kernel_toolchain(
            hipcc_path=hipcc,
            device_libraries_path=libraries,
            runner=FakeHipccRunner(version_output="AMD clang without HIP release"),
        )
    assert identity_error.value.code == "hip_csr_compiler_identity_invalid"

    (libraries / "ockl.bc").unlink()
    with pytest.raises(artifact.HipCsrKernelArtifactError) as library_error:
        artifact.probe_hip_csr_kernel_toolchain(
            hipcc_path=hipcc,
            device_libraries_path=libraries,
            runner=FakeHipccRunner(),
        )
    assert library_error.value.code == "hip_csr_device_libraries_unavailable"


def test_oversize_parseable_hip_version_never_compiles_or_promotes(
    tmp_path: Path,
) -> None:
    hipcc, libraries = _fake_toolchain(tmp_path)
    output = tmp_path / "must-not-promote.so"
    hip_version = ("1" * 31) + ".0"
    assert len(hip_version) == 33
    runner = FakeHipccRunner(version_output=f"HIP version: {hip_version}")

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            output,
            targets=("gfx1030",),
            hipcc_path=hipcc,
            device_libraries_path=libraries,
            runner=runner,
            cdll_loader=FakeCdllLoader(FakeKernelCdll()),
        )

    assert caught.value.code == "hip_csr_compiler_identity_invalid"
    assert caught.value.path == "/compiler/hip_version"
    assert runner.calls == [[str(hipcc.resolve()), "--version"]]
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.building"))


@pytest.mark.parametrize(
    "override_name",
    artifact.HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES,
)
def test_each_ambient_toolchain_override_blocks_build_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override_name: str,
) -> None:
    output = tmp_path / "must-not-promote.so"
    runner = FakeHipccRunner()
    secret_value = "override-value-must-not-be-reported"
    monkeypatch.setenv(override_name, secret_value)

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            output,
            targets=("gfx1030",),
            hipcc_path=tmp_path / "must-not-be-probed" / "hipcc",
            runner=runner,
        )

    assert caught.value.code == "hip_csr_toolchain_environment_override"
    assert caught.value.path == "/compiler/environment"
    assert override_name in caught.value.message
    assert secret_value not in caught.value.message
    assert runner.calls == []
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.building"))


def test_ambient_override_blocks_direct_version_probe_before_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeHipccRunner()
    monkeypatch.setenv("HIPCC_COMPILE_FLAGS_APPEND", "-ffast-math")

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.probe_hip_csr_kernel_toolchain(
            hipcc_path="/path/must/not/be/queried",
            runner=runner,
        )

    assert caught.value.code == "hip_csr_toolchain_environment_override"
    assert caught.value.path == "/compiler/environment"
    assert runner.calls == []


def test_build_failure_leaves_no_partial_or_promoted_artifact(
    tmp_path: Path,
) -> None:
    hipcc, libraries = _fake_toolchain(tmp_path)
    output = tmp_path / "failed.so"

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            output,
            targets=("gfx1030",),
            hipcc_path=hipcc,
            device_libraries_path=libraries,
            runner=FakeHipccRunner(build_returncode=1),
            cdll_loader=FakeCdllLoader(FakeKernelCdll()),
        )
    assert caught.value.code == "hip_csr_compile_failed"
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.building"))


def test_full_receipt_validation_precedes_atomic_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hipcc, libraries = _fake_toolchain(tmp_path)
    output = tmp_path / "must-not-promote.so"

    def reject_receipt(_: Any) -> Any:
        raise artifact.HipCsrKernelArtifactError(
            "hip_csr_artifact_receipt_schema_invalid",
            "/compiler/hip_version",
            "injected receipt schema rejection",
        )

    monkeypatch.setattr(
        artifact, "validate_hip_csr_kernel_artifact_receipt", reject_receipt
    )
    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            output,
            targets=("gfx1030",),
            hipcc_path=hipcc,
            device_libraries_path=libraries,
            runner=FakeHipccRunner(),
            cdll_loader=FakeCdllLoader(FakeKernelCdll()),
        )

    assert caught.value.code == "hip_csr_artifact_receipt_schema_invalid"
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.building"))


@pytest.mark.parametrize(
    "targets",
    [
        tuple(f"gfx1030:feature{index}" for index in range(33)),
        ("gfx1030:" + ("x" * 57),),
    ],
)
def test_schema_bounded_targets_fail_before_toolchain_and_leave_no_output(
    tmp_path: Path, targets: tuple[str, ...]
) -> None:
    output = tmp_path / "must-not-exist.so"
    runner = FakeHipccRunner()

    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            output,
            targets=targets,
            hipcc_path=tmp_path / "must-not-be-probed" / "hipcc",
            runner=runner,
        )

    assert caught.value.code == "hip_csr_target_invalid"
    assert caught.value.path == "/targets"
    assert runner.calls == []
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.building"))


def test_build_artifact_hash_io_error_is_wrapped_and_not_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hipcc, libraries = _fake_toolchain(tmp_path)
    output = tmp_path / "must-not-promote.so"
    original_hash = artifact._sha256_file

    def fail_compiler_output_hash(path: Path) -> str:
        if path.name.endswith(".building"):
            raise PermissionError("compiler output read denied")
        return original_hash(path)

    monkeypatch.setattr(artifact, "_sha256_file", fail_compiler_output_hash)
    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            output,
            targets=("gfx1030",),
            hipcc_path=hipcc,
            device_libraries_path=libraries,
            runner=FakeHipccRunner(),
            cdll_loader=FakeCdllLoader(FakeKernelCdll()),
        )

    assert caught.value.code == "hip_csr_artifact_hash_failed"
    assert caught.value.path == "/library_hash"
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.building"))


@pytest.mark.parametrize(
    "targets",
    [(), ("native",), ("gfx1030", "gfx1030"), ("gfx 1030",)],
)
def test_build_requires_explicit_unique_gfx_targets(
    tmp_path: Path, targets: tuple[str, ...]
) -> None:
    with pytest.raises(artifact.HipCsrKernelArtifactError) as caught:
        artifact.build_hip_csr_kernel_artifact(
            tmp_path / "never.so",
            targets=targets,
            hipcc_path=tmp_path / "never-queried",
        )
    assert caught.value.code == "hip_csr_target_invalid"


def test_native_source_is_one_row_per_thread_fused_and_resource_free() -> None:
    source_path = (
        REPO_ROOT
        / "src"
        / "structural_analysis"
        / "engine_v2"
        / "backends"
        / "hip"
        / "kernels"
        / "engine_v2_csr_residual_jvp.hip.cpp"
    )
    source = source_path.read_text(encoding="utf-8")

    assert "EngineV2BufferViewV1" in source
    assert "EngineV2CanonicalCsrV1" in source
    assert "EngineV2ResidualJvpRequestV1" in source
    assert "blockIdx.x * blockDim.x + threadIdx.x" in source
    assert "state_product += coefficient * state[column]" in source
    assert "direction_product += coefficient * direction[column]" in source
    assert "residual_out[row] = state_product - load[row]" in source
    assert "jvp_out[row] = direction_product" in source
    assert "hipGetLastError" in source
    assert "kLastErrorBytes = 256U" in source
    for forbidden in (
        "hipMalloc",
        "hipFree",
        "hipMemcpy",
        "hipDeviceSynchronize",
        "hipStreamSynchronize",
        "hipSetDevice",
        "atomicAdd",
        "atomicCAS",
    ):
        assert forbidden not in source

    kernel_sources = sorted(source_path.parent.glob("*.hip.cpp"))
    assert kernel_sources == [source_path]
    hip_backend_root = source_path.parent.parent
    obsolete_paths = (
        hip_backend_root / "rtc.py",
        hip_backend_root / "rtc_kernels",
        hip_backend_root.parent / "hip_rtc",
    )
    assert not any(
        path.is_file()
        or (
            path.is_dir()
            and any(
                item.is_file()
                and (item.suffix == ".py" or item.name.endswith(".hip.cpp"))
                for item in path.rglob("*")
            )
        )
        for path in obsolete_paths
    )


def test_python_artifact_layer_has_no_cpu_solver_or_fallback_execution() -> None:
    source = Path(artifact.__file__).read_text(encoding="utf-8")

    assert "cpu_reference" not in source
    assert "solve_linear_static" not in source
    assert "fallback_used=False" in source
    assert "ctypes.RTLD_LOCAL" in source
    assert "expected_sha256" in source


def test_public_hip_package_reexports_aot_artifact_contract() -> None:
    import structural_analysis.engine_v2.backends.hip as hip

    assert hip.build_hip_csr_kernel_artifact is artifact.build_hip_csr_kernel_artifact
    assert hip.load_hip_csr_kernel_artifact is artifact.load_hip_csr_kernel_artifact
    assert (
        hip.parse_hip_csr_kernel_artifact_receipt
        is artifact.parse_hip_csr_kernel_artifact_receipt
    )
    assert (
        hip.validate_hip_csr_kernel_artifact_receipt
        is artifact.validate_hip_csr_kernel_artifact_receipt
    )
