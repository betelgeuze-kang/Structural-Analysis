from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"


def test_native_abi_surface_is_versioned_and_language_neutral() -> None:
    header = (NATIVE / "include/structural_engine_c_api.h").read_text(
        encoding="utf-8"
    )
    assert "SA_ABI_VERSION_MAJOR" in header
    assert "SA_ABI_VERSION_MINOR" in header
    assert "struct_size" in header
    assert "typedef int32_t sa_status;" in header
    assert "typedef uint32_t sa_execution_mode;" in header
    assert "typedef enum sa_status" not in header
    assert "typedef struct sa_engine sa_engine;" in header
    assert "sa_engine_create" in header
    assert "sa_engine_destroy" in header
    assert "std::" not in header
    assert "Vec<" not in header


def test_native_claim_boundary_remains_bounded() -> None:
    readme = (NATIVE / "README.md").read_text(encoding="utf-8")
    assert "does **not** provide a production structural solver" in readme
    assert "does not grant numerical or release authority" in readme
    assert "Python remains the reference oracle" in readme


def test_cpp_reference_lifecycle_compiles_with_strict_warnings(tmp_path: Path) -> None:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.skip("C++ compiler is unavailable")
    subprocess.run(
        [
            compiler,
            "-std=c++20",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-Werror",
            "-I",
            str(NATIVE / "include"),
            "-c",
            str(NATIVE / "cpp/structural_engine_c_api.cpp"),
            "-o",
            str(tmp_path / "structural_engine_c_api.o"),
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
    )


def test_cpp_reference_lifecycle_runtime_contract(tmp_path: Path) -> None:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.skip("C++ compiler is unavailable")
    source = tmp_path / "abi_runtime.cpp"
    source.write_text(
        r'''
#include "structural_engine_c_api.h"

#include <cstdint>
#include <cstring>

static_assert(sizeof(sa_status) == sizeof(int32_t));
static_assert(sizeof(sa_execution_mode) == sizeof(uint32_t));

int main() {
    sa_engine_config config{};
    config.struct_size = sizeof(config);
    config.abi_version_major = SA_ABI_VERSION_MAJOR;
    config.abi_version_minor = SA_ABI_VERSION_MINOR;
    config.execution_mode = SA_EXECUTION_MODE_AUDITED;
    config.requested_device_index = -1;

    sa_engine *engine = reinterpret_cast<sa_engine *>(uintptr_t{1});
    config.reserved_u32[0] = 1;
    if (sa_engine_create(&config, &engine) != SA_STATUS_INVALID_ARGUMENT) return 1;
    if (engine != nullptr) return 2;

    config.reserved_u32[0] = 0;
    if (sa_engine_create(&config, &engine) != SA_STATUS_OK) return 3;
    if (engine == nullptr) return 4;

    uint64_t capabilities = UINT64_MAX;
    if (sa_engine_capabilities(nullptr, &capabilities) != SA_STATUS_INVALID_ARGUMENT) return 5;
    if (capabilities != 0) return 6;

    capabilities = UINT64_MAX;
    if (sa_engine_capabilities(engine, &capabilities) != SA_STATUS_OK) return 7;
    if (capabilities != SA_CAPABILITY_CPU_REFERENCE) return 8;

    size_t required = 0;
    if (sa_engine_last_error(engine, nullptr, 0, &required) != SA_STATUS_BUFFER_TOO_SMALL) return 9;
    if (required != 1) return 10;
    char empty[1] = {'x'};
    if (sa_engine_last_error(engine, empty, sizeof(empty), &required) != SA_STATUS_OK) return 11;
    if (empty[0] != '\0' || required != 1) return 12;

    sa_engine_destroy(engine);
    return 0;
}
''',
        encoding="utf-8",
    )
    executable = tmp_path / "abi_runtime"
    subprocess.run(
        [
            compiler,
            "-std=c++20",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-Werror",
            "-I",
            str(NATIVE / "include"),
            str(source),
            str(NATIVE / "cpp/structural_engine_c_api.cpp"),
            "-o",
            str(executable),
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
    )
    subprocess.run([str(executable)], cwd=ROOT, check=True, timeout=120)


def test_c_header_is_consumable_from_c(tmp_path: Path) -> None:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("C compiler is unavailable")
    source = tmp_path / "abi_smoke.c"
    source.write_text(
        "#include \"structural_engine_c_api.h\"\n"
        "_Static_assert(sizeof(sa_status) == sizeof(int32_t), \"sa_status width\");\n"
        "_Static_assert(sizeof(sa_execution_mode) == sizeof(uint32_t), \"mode width\");\n"
        "int main(void) { sa_engine_config c = {0}; "
        "c.struct_size = sizeof(c); return c.struct_size == 0; }\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-Werror",
            "-I",
            str(NATIVE / "include"),
            "-c",
            str(source),
            "-o",
            str(tmp_path / "abi_smoke.o"),
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
    )


def test_rust_workspace_mock_contracts(tmp_path: Path) -> None:
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip("Cargo is unavailable")
    env = {**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "cargo-target")}
    subprocess.run(
        [
            cargo,
            "test",
            "--manifest-path",
            str(NATIVE / "rust/Cargo.toml"),
            "--workspace",
            "--all-targets",
            "--offline",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=180,
    )
