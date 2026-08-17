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


def test_c_header_is_consumable_from_c(tmp_path: Path) -> None:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("C compiler is unavailable")
    source = tmp_path / "abi_smoke.c"
    source.write_text(
        "#include \"structural_engine_c_api.h\"\n"
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
