#!/usr/bin/env python3
"""Reusable native HIP full-residual batch backend for G1 probes."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

PHASE1 = Path(__file__).resolve().parent
REPO_ROOT = PHASE1.parents[1]
NATIVE_WORKSPACE = REPO_ROOT / "native"
NATIVE_CPP = NATIVE_WORKSPACE / "cpp"
PRODUCTIZATION = PHASE1 / "release_evidence" / "productization"
HIP_SOURCE = PHASE1 / "hip_full_residual_batch_replay.cpp"
HIP_BINARY = PRODUCTIZATION / "bin/hip_full_residual_batch_replay"
HIP_WORKER_SOURCE = PHASE1 / "hip_full_residual_resident_worker.cpp"
HIP_WORKER_BINARY = PRODUCTIZATION / "bin/hip_full_residual_resident_worker"
PRODUCT_REPLAY_HEADER = PHASE1 / "product_full_residual_replay.hpp"
HIP_FFI_LIBRARY = PRODUCTIZATION / "bin/libstructural_c_abi_v1.so"
HIP_FFI_BUILD = PHASE1 / "build/native-full-residual-product"
RUST_HIP_FFI_CRATE = PHASE1 / "mgt_hip_full_residual_ffi"
RUST_HIP_FFI_LIBRARY = PRODUCTIZATION / "bin/libmgt_hip_full_residual_rust_ffi.so"
ROCM_DEVICE_LIB_PATH = (
    PHASE1 / "third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
)


def build_product_replay_binary(
    *,
    source: Path,
    binary: Path,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    product_build = build_hip_full_residual_ffi_library(
        hipcc=hipcc,
        force_rebuild=force_rebuild,
    )
    binary.parent.mkdir(parents=True, exist_ok=True)
    compiler = os.environ.get("CXX", "c++")
    command = [
        compiler,
        "-O3",
        "-std=c++20",
        "-I",
        str(NATIVE_CPP / "include"),
        "-I",
        str(PHASE1),
        str(source),
        "-L",
        str(HIP_FFI_LIBRARY.parent),
        "-lstructural_c_abi_v1",
        "-Wl,-z,defs",
        "-Wl,-rpath,$ORIGIN",
        "-o",
        str(binary),
    ]
    if not bool(product_build.get("ok")):
        return {
            "attempted": False,
            "ok": False,
            "binary": str(binary),
            "source": str(source),
            "command": command,
            "product_library_build": product_build,
            "reason": "product_library_build_failed",
        }
    tracked_sources = (source, PRODUCT_REPLAY_HEADER, NATIVE_CPP / "include/structural/abi_v1.h")
    needs_build = bool(force_rebuild) or not binary.exists()
    if binary.exists():
        needs_build = needs_build or any(
            path.exists() and path.stat().st_mtime > binary.stat().st_mtime
            for path in tracked_sources
        )
        needs_build = needs_build or HIP_FFI_LIBRARY.stat().st_mtime > binary.stat().st_mtime
    if not needs_build:
        return {
            "attempted": False,
            "ok": True,
            "binary": str(binary),
            "source": str(source),
            "command": command,
            "product_library": str(HIP_FFI_LIBRARY),
            "product_library_build": product_build,
            "single_entry_symbol": "sa_get_api_v1",
            "reason": "binary_current",
        }
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "binary": str(binary),
        "source": str(source),
        "command": command,
        "product_library": str(HIP_FFI_LIBRARY),
        "product_library_build": product_build,
        "single_entry_symbol": "sa_get_api_v1",
        "returncode": int(proc.returncode),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "seconds": float(time.perf_counter() - started),
    }


def build_hip_full_residual_binary(
    *,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    return build_product_replay_binary(
        source=HIP_SOURCE,
        binary=HIP_BINARY,
        hipcc=hipcc,
        force_rebuild=force_rebuild,
    )


def build_hip_full_residual_worker_binary(
    *,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    return build_product_replay_binary(
        source=HIP_WORKER_SOURCE,
        binary=HIP_WORKER_BINARY,
        hipcc=hipcc,
        force_rebuild=force_rebuild,
    )


def build_hip_full_residual_ffi_library(
    *,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    HIP_FFI_LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    rocm_root = hipcc.parent.parent
    hip_compiler = rocm_root / "llvm/bin/clang++"
    architecture = os.environ.get("STRUCTURAL_HIP_ARCHITECTURE", "gfx1030")
    configured_library = HIP_FFI_BUILD / "lib/libstructural_c_abi_v1.so"
    configure_command = [
        "cmake",
        "-S",
        str(NATIVE_CPP),
        "-B",
        str(HIP_FFI_BUILD),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_HIP_COMPILER={hip_compiler}",
        f"-DCMAKE_HIP_ARCHITECTURES={architecture}",
        f"-DSTRUCTURAL_ROCM_ROOT={rocm_root}",
        f"-DSTRUCTURAL_HIP_DEVICE_LIB_PATH={ROCM_DEVICE_LIB_PATH}",
        "-DSTRUCTURAL_ENABLE_HIP=ON",
        "-DSTRUCTURAL_BUILD_TESTS=OFF",
        "-DSTRUCTURAL_WARNINGS_AS_ERRORS=ON",
        "-DBUILD_SHARED_LIBS=ON",
    ]
    build_command = [
        "cmake",
        "--build",
        str(HIP_FFI_BUILD),
        "--target",
        "structural_c_abi_v1",
        "--parallel",
        "2",
    ]
    source_paths = [
        NATIVE_CPP / "CMakeLists.txt",
        NATIVE_CPP / "include/structural/abi_v1.h",
        NATIVE_CPP / "src/abi/abi_v1.cpp",
        NATIVE_CPP / "src/hip/full_residual_hip.hpp",
        NATIVE_CPP / "src/hip/full_residual_hip.hip.cpp",
        NATIVE_CPP / "src/solver_cpu/full_residual.hpp",
        NATIVE_CPP / "src/solver_cpu/full_residual.cpp",
    ]
    needs_build = (
        bool(force_rebuild)
        or not HIP_FFI_LIBRARY.exists()
        or not configured_library.exists()
        or any(
            source.exists()
            and HIP_FFI_LIBRARY.exists()
            and source.stat().st_mtime > HIP_FFI_LIBRARY.stat().st_mtime
            for source in source_paths
        )
    )
    if not needs_build:
        return {
            "attempted": False,
            "ok": True,
            "library": str(HIP_FFI_LIBRARY),
            "source": str(NATIVE_CPP),
            "configure_command": configure_command,
            "build_command": build_command,
            "reason": "library_current",
        }
    started = time.perf_counter()
    configure = subprocess.run(
        configure_command, capture_output=True, text=True, check=False
    )
    build = None
    copied = False
    if configure.returncode == 0:
        build = subprocess.run(
            build_command, capture_output=True, text=True, check=False
        )
        if build.returncode == 0 and configured_library.exists():
            shutil.copy2(configured_library, HIP_FFI_LIBRARY)
            copied = True
    return {
        "attempted": True,
        "ok": bool(
            configure.returncode == 0
            and build is not None
            and build.returncode == 0
            and copied
            and HIP_FFI_LIBRARY.exists()
        ),
        "library": str(HIP_FFI_LIBRARY),
        "source": str(NATIVE_CPP),
        "configured_library": str(configured_library),
        "configure_command": configure_command,
        "build_command": build_command,
        "configure_returncode": int(configure.returncode),
        "build_returncode": int(build.returncode) if build is not None else None,
        "copied": copied,
        "stdout": ((configure.stdout if configure else "") + (build.stdout if build else ""))[-4000:],
        "stderr": ((configure.stderr if configure else "") + (build.stderr if build else ""))[-4000:],
        "seconds": float(time.perf_counter() - started),
    }


def build_rust_hip_full_residual_ffi_library(*, force_rebuild: bool = False) -> dict[str, Any]:
    RUST_HIP_FFI_LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    manifest = RUST_HIP_FFI_CRATE / "Cargo.toml"
    rust_src = RUST_HIP_FFI_CRATE / "src/lib.rs"
    built_library = NATIVE_WORKSPACE / "target/release/libmgt_hip_full_residual_rust_ffi.so"
    needs_build = bool(force_rebuild) or not RUST_HIP_FFI_LIBRARY.exists() or not built_library.exists()
    for source in (manifest, rust_src):
        if source.exists() and RUST_HIP_FFI_LIBRARY.exists():
            needs_build = needs_build or source.stat().st_mtime > RUST_HIP_FFI_LIBRARY.stat().st_mtime
    command = [
        "cargo",
        "build",
        "--release",
        "--offline",
        "--manifest-path",
        str(NATIVE_WORKSPACE / "Cargo.toml"),
        "--package",
        "mgt_hip_full_residual_rust_ffi",
    ]
    if not needs_build:
        return {
            "attempted": False,
            "ok": True,
            "library": str(RUST_HIP_FFI_LIBRARY),
            "crate": str(RUST_HIP_FFI_CRATE),
            "command": command,
            "reason": "library_current",
        }
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    copied = False
    if proc.returncode == 0 and built_library.exists():
        shutil.copy2(built_library, RUST_HIP_FFI_LIBRARY)
        copied = True
    return {
        "attempted": True,
        "ok": proc.returncode == 0 and copied and RUST_HIP_FFI_LIBRARY.exists(),
        "library": str(RUST_HIP_FFI_LIBRARY),
        "crate": str(RUST_HIP_FFI_CRATE),
        "built_library": str(built_library),
        "copied": copied,
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "seconds": float(time.perf_counter() - started),
    }


class _RustHipFullResidualStatus(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_int),
        ("frame_element_count", ctypes.c_longlong),
        ("n_dof", ctypes.c_longlong),
        ("free_count", ctypes.c_longlong),
        ("shell_nnz", ctypes.c_longlong),
        ("spring_nnz", ctypes.c_longlong),
        ("batch_size", ctypes.c_longlong),
        ("reps", ctypes.c_int),
        ("device_id", ctypes.c_int),
        ("eval_buffers_reused", ctypes.c_int),
        ("operator_buffers_device_resident", ctypes.c_int),
        ("kernel_elapsed_ms_total", ctypes.c_double),
        ("kernel_elapsed_ms_mean", ctypes.c_double),
        ("output_abs_sum", ctypes.c_double),
        ("output_max_abs", ctypes.c_double),
    ]


def _as_void_p(array: np.ndarray) -> ctypes.c_void_p:
    return ctypes.c_void_p(int(array.ctypes.data))


def _load_rust_hip_full_residual_library() -> ctypes.CDLL:
    lib = ctypes.CDLL(str(RUST_HIP_FFI_LIBRARY))
    lib.mgt_rust_hip_full_residual_ffi_version.argtypes = []
    lib.mgt_rust_hip_full_residual_ffi_version.restype = ctypes.c_uint
    lib.mgt_rust_hip_full_residual_load_library.argtypes = [ctypes.c_char_p]
    lib.mgt_rust_hip_full_residual_load_library.restype = ctypes.c_int
    lib.mgt_rust_hip_full_residual_create.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_longlong,
        ctypes.c_longlong,
        ctypes.c_longlong,
        ctypes.c_longlong,
        ctypes.c_longlong,
        ctypes.POINTER(_RustHipFullResidualStatus),
    ]
    lib.mgt_rust_hip_full_residual_create.restype = ctypes.c_int
    lib.mgt_rust_hip_full_residual_eval.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_longlong,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.POINTER(_RustHipFullResidualStatus),
    ]
    lib.mgt_rust_hip_full_residual_eval.restype = ctypes.c_int
    lib.mgt_rust_hip_full_residual_destroy.argtypes = [ctypes.c_void_p]
    lib.mgt_rust_hip_full_residual_destroy.restype = ctypes.c_int
    lib.mgt_rust_hip_full_residual_device_name.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    lib.mgt_rust_hip_full_residual_device_name.restype = ctypes.c_int
    lib.mgt_rust_hip_full_residual_last_error.argtypes = []
    lib.mgt_rust_hip_full_residual_last_error.restype = ctypes.c_char_p
    rc = int(lib.mgt_rust_hip_full_residual_load_library(str(HIP_FFI_LIBRARY).encode("utf-8")))
    if rc != 0:
        raise RuntimeError(f"rust HIP full residual FFI library load failed: rc={rc}")
    return lib


def _run_hip_full_residual_bridge(
    *,
    frame_dofs_path: Path,
    frame_stiffness_path: Path,
    shell_row_ptr_path: Path,
    shell_col_idx_path: Path,
    shell_values_path: Path,
    spring_row_ptr_path: Path,
    spring_col_idx_path: Path,
    spring_values_path: Path,
    states_path: Path,
    f_ext_path: Path,
    free_path: Path,
    output_path: Path,
    frame_element_count: int,
    n_dof: int,
    shell_nnz: int,
    spring_nnz: int,
    free_count: int,
    batch_size: int,
    reps: int,
) -> tuple[dict[str, Any], float]:
    command = [
        str(HIP_BINARY),
        "--frame-dofs",
        str(frame_dofs_path),
        "--frame-stiffness",
        str(frame_stiffness_path),
        "--shell-row-ptr",
        str(shell_row_ptr_path),
        "--shell-col-idx",
        str(shell_col_idx_path),
        "--shell-values",
        str(shell_values_path),
        "--spring-row-ptr",
        str(spring_row_ptr_path),
        "--spring-col-idx",
        str(spring_col_idx_path),
        "--spring-values",
        str(spring_values_path),
        "--states",
        str(states_path),
        "--f-ext",
        str(f_ext_path),
        "--free",
        str(free_path),
        "--output",
        str(output_path),
        "--frame-element-count",
        str(frame_element_count),
        "--n-dof",
        str(n_dof),
        "--shell-nnz",
        str(shell_nnz),
        "--spring-nnz",
        str(spring_nnz),
        "--free-count",
        str(free_count),
        "--batch-size",
        str(batch_size),
        "--reps",
        str(reps),
    ]
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    elapsed = float(time.perf_counter() - started)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    payload.update(
        {
            "command": command,
            "returncode": int(proc.returncode),
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "subprocess_seconds": elapsed,
        }
    )
    return payload, elapsed


@dataclass
class HipFullResidualBatchBackend:
    """Prepared file-backed HIP residual evaluator with reusable operator buffers."""

    temp_dir: tempfile.TemporaryDirectory[str]
    frame_dofs_path: Path
    frame_stiffness_path: Path
    shell_row_ptr_path: Path
    shell_col_idx_path: Path
    shell_values_path: Path
    spring_row_ptr_path: Path
    spring_col_idx_path: Path
    spring_values_path: Path
    f_ext_path: Path
    free_path: Path
    frame_element_count: int
    n_dof: int
    shell_nnz: int
    spring_nnz: int
    free_count: int
    build: dict[str, Any]
    operator_write_seconds: float

    @classmethod
    def prepare(
        cls,
        *,
        frame_dofs: np.ndarray,
        frame_stiffness: np.ndarray,
        shell_csr: Any,
        spring_csr: Any,
        f_ext: np.ndarray,
        free: np.ndarray,
        hipcc: Path = Path("/opt/rocm/bin/hipcc"),
        force_rebuild: bool = False,
    ) -> "HipFullResidualBatchBackend":
        build = build_hip_full_residual_binary(hipcc=hipcc, force_rebuild=force_rebuild)
        if not bool(build.get("ok")):
            raise RuntimeError("hip full residual binary build failed")
        temp_dir = tempfile.TemporaryDirectory(prefix="mgt_hip_full_residual_backend_")
        root = Path(temp_dir.name)
        started = time.perf_counter()
        frame_dofs_path = root / "frame_dofs.i64"
        frame_stiffness_path = root / "frame_stiffness.f64"
        shell_row_ptr_path = root / "shell_row_ptr.i64"
        shell_col_idx_path = root / "shell_col_idx.i64"
        shell_values_path = root / "shell_values.f64"
        spring_row_ptr_path = root / "spring_row_ptr.i64"
        spring_col_idx_path = root / "spring_col_idx.i64"
        spring_values_path = root / "spring_values.f64"
        f_ext_path = root / "f_ext.f64"
        free_path = root / "free.i64"
        np.asarray(frame_dofs, dtype=np.int64).tofile(frame_dofs_path)
        np.asarray(frame_stiffness, dtype=np.float64).tofile(frame_stiffness_path)
        np.asarray(shell_csr.indptr, dtype=np.int64).tofile(shell_row_ptr_path)
        np.asarray(shell_csr.indices, dtype=np.int64).tofile(shell_col_idx_path)
        np.asarray(shell_csr.data, dtype=np.float64).tofile(shell_values_path)
        np.asarray(spring_csr.indptr, dtype=np.int64).tofile(spring_row_ptr_path)
        np.asarray(spring_csr.indices, dtype=np.int64).tofile(spring_col_idx_path)
        np.asarray(spring_csr.data, dtype=np.float64).tofile(spring_values_path)
        np.asarray(f_ext, dtype=np.float64).tofile(f_ext_path)
        np.asarray(free, dtype=np.int64).tofile(free_path)
        return cls(
            temp_dir=temp_dir,
            frame_dofs_path=frame_dofs_path,
            frame_stiffness_path=frame_stiffness_path,
            shell_row_ptr_path=shell_row_ptr_path,
            shell_col_idx_path=shell_col_idx_path,
            shell_values_path=shell_values_path,
            spring_row_ptr_path=spring_row_ptr_path,
            spring_col_idx_path=spring_col_idx_path,
            spring_values_path=spring_values_path,
            f_ext_path=f_ext_path,
            free_path=free_path,
            frame_element_count=int(np.asarray(frame_dofs).shape[0]),
            n_dof=int(np.asarray(f_ext).size),
            shell_nnz=int(shell_csr.nnz),
            spring_nnz=int(spring_csr.nnz),
            free_count=int(np.asarray(free).size),
            build=build,
            operator_write_seconds=float(time.perf_counter() - started),
        )

    def evaluate(self, states: np.ndarray, *, reps: int = 1) -> tuple[np.ndarray, dict[str, Any]]:
        state_batch = np.asarray(states, dtype=np.float64)
        if state_batch.ndim != 2:
            raise ValueError("states must be a 2D array shaped (batch, n_dof)")
        if int(state_batch.shape[1]) != int(self.n_dof):
            raise ValueError(f"state n_dof {state_batch.shape[1]} does not match backend n_dof {self.n_dof}")
        root = Path(self.temp_dir.name)
        states_path = root / "states.f64"
        output_path = root / "hip_full_residual.f64"
        np.asarray(state_batch, dtype=np.float64).tofile(states_path)
        hip_payload, subprocess_seconds = _run_hip_full_residual_bridge(
            frame_dofs_path=self.frame_dofs_path,
            frame_stiffness_path=self.frame_stiffness_path,
            shell_row_ptr_path=self.shell_row_ptr_path,
            shell_col_idx_path=self.shell_col_idx_path,
            shell_values_path=self.shell_values_path,
            spring_row_ptr_path=self.spring_row_ptr_path,
            spring_col_idx_path=self.spring_col_idx_path,
            spring_values_path=self.spring_values_path,
            states_path=states_path,
            f_ext_path=self.f_ext_path,
            free_path=self.free_path,
            output_path=output_path,
            frame_element_count=self.frame_element_count,
            n_dof=self.n_dof,
            shell_nnz=self.shell_nnz,
            spring_nnz=self.spring_nnz,
            free_count=self.free_count,
            batch_size=int(state_batch.shape[0]),
            reps=max(int(reps), 1),
        )
        if not output_path.exists():
            raise RuntimeError(f"hip full residual output missing: {hip_payload}")
        residual = np.fromfile(output_path, dtype=np.float64).reshape(
            (int(state_batch.shape[0]), int(self.free_count))
        )
        meta = {
            "backend": "native_hip_full_residual_batch",
            "single_entry_symbol": hip_payload.get("single_entry_symbol"),
            "product_library_linked": bool(hip_payload.get("product_library_linked")),
            "kernel_owner": hip_payload.get("kernel_owner"),
            "replay_executable_owns_kernels": False,
            "single_subprocess_boundary": True,
            "persistent_in_process_worker": False,
            "batch_size": int(state_batch.shape[0]),
            "free_dof_count": int(self.free_count),
            "operator_write_seconds": float(self.operator_write_seconds),
            "hip_subprocess_seconds": float(subprocess_seconds),
            "hip_kernel_mean_seconds": float(hip_payload.get("kernel_elapsed_ms_mean") or 0.0) / 1000.0,
            "build": self.build,
            "hip": hip_payload,
            "operator_sizes": {
                "frame_element_count": int(self.frame_element_count),
                "shell_nnz": int(self.shell_nnz),
                "spring_nnz": int(self.spring_nnz),
            },
        }
        return np.asarray(residual, dtype=np.float64), meta


@dataclass
class HipFullResidualResidentWorkerBackend:
    """Long-lived native HIP worker that keeps operator buffers resident."""

    temp_dir: tempfile.TemporaryDirectory[str]
    process: subprocess.Popen[str]
    startup: dict[str, Any]
    frame_dofs_path: Path
    frame_stiffness_path: Path
    shell_row_ptr_path: Path
    shell_col_idx_path: Path
    shell_values_path: Path
    spring_row_ptr_path: Path
    spring_col_idx_path: Path
    spring_values_path: Path
    f_ext_path: Path
    free_path: Path
    frame_element_count: int
    n_dof: int
    shell_nnz: int
    spring_nnz: int
    free_count: int
    build: dict[str, Any]
    operator_write_seconds: float
    worker_start_seconds: float
    evaluation_count: int = 0

    @classmethod
    def prepare(
        cls,
        *,
        frame_dofs: np.ndarray,
        frame_stiffness: np.ndarray,
        shell_csr: Any,
        spring_csr: Any,
        f_ext: np.ndarray,
        free: np.ndarray,
        hipcc: Path = Path("/opt/rocm/bin/hipcc"),
        force_rebuild: bool = False,
    ) -> "HipFullResidualResidentWorkerBackend":
        build = build_hip_full_residual_worker_binary(hipcc=hipcc, force_rebuild=force_rebuild)
        if not bool(build.get("ok")):
            raise RuntimeError("hip full residual resident worker build failed")
        temp_dir = tempfile.TemporaryDirectory(prefix="mgt_hip_full_residual_worker_")
        root = Path(temp_dir.name)
        started = time.perf_counter()
        frame_dofs_path = root / "frame_dofs.i64"
        frame_stiffness_path = root / "frame_stiffness.f64"
        shell_row_ptr_path = root / "shell_row_ptr.i64"
        shell_col_idx_path = root / "shell_col_idx.i64"
        shell_values_path = root / "shell_values.f64"
        spring_row_ptr_path = root / "spring_row_ptr.i64"
        spring_col_idx_path = root / "spring_col_idx.i64"
        spring_values_path = root / "spring_values.f64"
        f_ext_path = root / "f_ext.f64"
        free_path = root / "free.i64"
        np.asarray(frame_dofs, dtype=np.int64).tofile(frame_dofs_path)
        np.asarray(frame_stiffness, dtype=np.float64).tofile(frame_stiffness_path)
        np.asarray(shell_csr.indptr, dtype=np.int64).tofile(shell_row_ptr_path)
        np.asarray(shell_csr.indices, dtype=np.int64).tofile(shell_col_idx_path)
        np.asarray(shell_csr.data, dtype=np.float64).tofile(shell_values_path)
        np.asarray(spring_csr.indptr, dtype=np.int64).tofile(spring_row_ptr_path)
        np.asarray(spring_csr.indices, dtype=np.int64).tofile(spring_col_idx_path)
        np.asarray(spring_csr.data, dtype=np.float64).tofile(spring_values_path)
        np.asarray(f_ext, dtype=np.float64).tofile(f_ext_path)
        np.asarray(free, dtype=np.int64).tofile(free_path)
        operator_write_seconds = float(time.perf_counter() - started)
        frame_element_count = int(np.asarray(frame_dofs).shape[0])
        n_dof = int(np.asarray(f_ext).size)
        shell_nnz = int(shell_csr.nnz)
        spring_nnz = int(spring_csr.nnz)
        free_count = int(np.asarray(free).size)
        command = [
            str(HIP_WORKER_BINARY),
            "--frame-dofs",
            str(frame_dofs_path),
            "--frame-stiffness",
            str(frame_stiffness_path),
            "--shell-row-ptr",
            str(shell_row_ptr_path),
            "--shell-col-idx",
            str(shell_col_idx_path),
            "--shell-values",
            str(shell_values_path),
            "--spring-row-ptr",
            str(spring_row_ptr_path),
            "--spring-col-idx",
            str(spring_col_idx_path),
            "--spring-values",
            str(spring_values_path),
            "--f-ext",
            str(f_ext_path),
            "--free",
            str(free_path),
            "--frame-element-count",
            str(frame_element_count),
            "--n-dof",
            str(n_dof),
            "--shell-nnz",
            str(shell_nnz),
            "--spring-nnz",
            str(spring_nnz),
            "--free-count",
            str(free_count),
        ]
        worker_started = time.perf_counter()
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        ready_line = process.stdout.readline() if process.stdout is not None else ""
        worker_start_seconds = float(time.perf_counter() - worker_started)
        try:
            startup = json.loads(ready_line.strip()) if ready_line.strip() else {}
        except json.JSONDecodeError:
            startup = {}
        if not bool(startup.get("ok")):
            stderr = ""
            if process.poll() is not None and process.stderr is not None:
                stderr = process.stderr.read()[-4000:]
            process.terminate()
            raise RuntimeError(
                f"hip full residual resident worker startup failed: {startup or ready_line!r} {stderr}"
            )
        startup = {
            **startup,
            "command": command,
            "worker_start_seconds": worker_start_seconds,
        }
        return cls(
            temp_dir=temp_dir,
            process=process,
            startup=startup,
            frame_dofs_path=frame_dofs_path,
            frame_stiffness_path=frame_stiffness_path,
            shell_row_ptr_path=shell_row_ptr_path,
            shell_col_idx_path=shell_col_idx_path,
            shell_values_path=shell_values_path,
            spring_row_ptr_path=spring_row_ptr_path,
            spring_col_idx_path=spring_col_idx_path,
            spring_values_path=spring_values_path,
            f_ext_path=f_ext_path,
            free_path=free_path,
            frame_element_count=frame_element_count,
            n_dof=n_dof,
            shell_nnz=shell_nnz,
            spring_nnz=spring_nnz,
            free_count=free_count,
            build=build,
            operator_write_seconds=operator_write_seconds,
            worker_start_seconds=worker_start_seconds,
        )

    def evaluate(self, states: np.ndarray, *, reps: int = 1) -> tuple[np.ndarray, dict[str, Any]]:
        if self.process.poll() is not None:
            raise RuntimeError(f"hip resident worker exited with {self.process.returncode}")
        state_batch = np.asarray(states, dtype=np.float64)
        if state_batch.ndim != 2:
            raise ValueError("states must be a 2D array shaped (batch, n_dof)")
        if int(state_batch.shape[1]) != int(self.n_dof):
            raise ValueError(f"state n_dof {state_batch.shape[1]} does not match backend n_dof {self.n_dof}")
        self.evaluation_count += 1
        root = Path(self.temp_dir.name)
        states_path = root / f"states_{self.evaluation_count:06d}.f64"
        output_path = root / f"hip_full_residual_{self.evaluation_count:06d}.f64"
        np.asarray(state_batch, dtype=np.float64).tofile(states_path)
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("hip resident worker stdio is not available")
        command = (
            f"EVAL {states_path} {output_path} "
            f"{int(state_batch.shape[0])} {max(int(reps), 1)}\n"
        )
        started = time.perf_counter()
        self.process.stdin.write(command)
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        elapsed = float(time.perf_counter() - started)
        try:
            hip_payload = json.loads(line.strip()) if line.strip() else {}
        except json.JSONDecodeError:
            hip_payload = {}
        if not bool(hip_payload.get("ok")):
            raise RuntimeError(f"hip resident worker evaluation failed: {hip_payload or line!r}")
        if not output_path.exists():
            raise RuntimeError(f"hip resident worker output missing: {hip_payload}")
        residual = np.fromfile(output_path, dtype=np.float64).reshape(
            (int(state_batch.shape[0]), int(self.free_count))
        )
        meta = {
            "backend": "native_hip_full_residual_resident_worker",
            "single_entry_symbol": hip_payload.get("single_entry_symbol"),
            "product_library_linked": bool(
                self.startup.get("product_library_linked")
                and hip_payload.get("product_library_linked")
            ),
            "kernel_owner": hip_payload.get("kernel_owner"),
            "replay_executable_owns_kernels": False,
            "single_subprocess_boundary": False,
            "persistent_process_worker": True,
            "persistent_in_process_worker": False,
            "rust_ffi_worker": False,
            "operator_buffers_device_resident": bool(
                self.startup.get("operator_buffers_device_resident")
                and hip_payload.get("operator_buffers_device_resident")
            ),
            "worker_evaluation_count": int(self.evaluation_count),
            "worker_pid": int(self.process.pid),
            "batch_size": int(state_batch.shape[0]),
            "free_dof_count": int(self.free_count),
            "operator_write_seconds": float(self.operator_write_seconds),
            "worker_start_seconds": float(self.worker_start_seconds),
            "worker_roundtrip_seconds": elapsed,
            "hip_kernel_mean_seconds": float(hip_payload.get("kernel_elapsed_ms_mean") or 0.0) / 1000.0,
            "build": self.build,
            "startup": self.startup,
            "hip": hip_payload,
            "operator_sizes": {
                "frame_element_count": int(self.frame_element_count),
                "shell_nnz": int(self.shell_nnz),
                "spring_nnz": int(self.spring_nnz),
            },
        }
        return np.asarray(residual, dtype=np.float64), meta

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        if self.process.stdin is not None:
            try:
                self.process.stdin.write("QUIT\n")
                self.process.stdin.flush()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def __enter__(self) -> "HipFullResidualResidentWorkerBackend":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


@dataclass
class HipFullResidualRustFfiBackend:
    """In-process Rust FFI wrapper over the native HIP full-residual C ABI."""

    library: ctypes.CDLL
    handle: ctypes.c_void_p
    frame_element_count: int
    n_dof: int
    shell_nnz: int
    spring_nnz: int
    free_count: int
    build: dict[str, Any]
    operator_create_seconds: float
    evaluation_count: int = 0

    @classmethod
    def prepare(
        cls,
        *,
        frame_dofs: np.ndarray,
        frame_stiffness: np.ndarray,
        shell_csr: Any,
        spring_csr: Any,
        f_ext: np.ndarray,
        free: np.ndarray,
        hipcc: Path = Path("/opt/rocm/bin/hipcc"),
        force_rebuild: bool = False,
    ) -> "HipFullResidualRustFfiBackend":
        hip_build = build_hip_full_residual_ffi_library(hipcc=hipcc, force_rebuild=force_rebuild)
        if not bool(hip_build.get("ok")):
            raise RuntimeError(f"hip full residual FFI library build failed: {hip_build}")
        rust_build = build_rust_hip_full_residual_ffi_library(force_rebuild=force_rebuild)
        if not bool(rust_build.get("ok")):
            raise RuntimeError(f"rust HIP full residual FFI library build failed: {rust_build}")
        lib = _load_rust_hip_full_residual_library()
        frame_dofs_c = np.ascontiguousarray(frame_dofs, dtype=np.int64)
        frame_stiffness_c = np.ascontiguousarray(frame_stiffness, dtype=np.float64)
        shell_row_ptr_c = np.ascontiguousarray(shell_csr.indptr, dtype=np.int64)
        shell_col_idx_c = np.ascontiguousarray(shell_csr.indices, dtype=np.int64)
        shell_values_c = np.ascontiguousarray(shell_csr.data, dtype=np.float64)
        spring_row_ptr_c = np.ascontiguousarray(spring_csr.indptr, dtype=np.int64)
        spring_col_idx_c = np.ascontiguousarray(spring_csr.indices, dtype=np.int64)
        spring_values_c = np.ascontiguousarray(spring_csr.data, dtype=np.float64)
        f_ext_c = np.ascontiguousarray(f_ext, dtype=np.float64)
        free_c = np.ascontiguousarray(free, dtype=np.int64)
        handle = ctypes.c_void_p()
        status = _RustHipFullResidualStatus()
        started = time.perf_counter()
        rc = int(
            lib.mgt_rust_hip_full_residual_create(
                ctypes.byref(handle),
                _as_void_p(frame_dofs_c),
                _as_void_p(frame_stiffness_c),
                _as_void_p(shell_row_ptr_c),
                _as_void_p(shell_col_idx_c),
                _as_void_p(shell_values_c),
                _as_void_p(spring_row_ptr_c),
                _as_void_p(spring_col_idx_c),
                _as_void_p(spring_values_c),
                _as_void_p(f_ext_c),
                _as_void_p(free_c),
                ctypes.c_longlong(int(frame_dofs_c.shape[0])),
                ctypes.c_longlong(int(f_ext_c.size)),
                ctypes.c_longlong(int(shell_csr.nnz)),
                ctypes.c_longlong(int(spring_csr.nnz)),
                ctypes.c_longlong(int(free_c.size)),
                ctypes.byref(status),
            )
        )
        operator_create_seconds = float(time.perf_counter() - started)
        if rc != 0 or not bool(handle.value):
            last_error = lib.mgt_rust_hip_full_residual_last_error()
            message = last_error.decode("utf-8", errors="replace") if last_error else ""
            raise RuntimeError(f"rust HIP full residual FFI create failed: rc={rc} {message}")
        return cls(
            library=lib,
            handle=handle,
            frame_element_count=int(frame_dofs_c.shape[0]),
            n_dof=int(f_ext_c.size),
            shell_nnz=int(shell_csr.nnz),
            spring_nnz=int(spring_csr.nnz),
            free_count=int(free_c.size),
            build={
                "hip_ffi": hip_build,
                "rust_ffi": rust_build,
                "rust_ffi_version": int(lib.mgt_rust_hip_full_residual_ffi_version()),
            },
            operator_create_seconds=operator_create_seconds,
        )

    def _device_name(self) -> str:
        buffer = ctypes.create_string_buffer(256)
        rc = int(
            self.library.mgt_rust_hip_full_residual_device_name(
                self.handle,
                buffer,
                ctypes.c_size_t(len(buffer)),
            )
        )
        if rc != 0:
            return ""
        return buffer.value.decode("utf-8", errors="replace")

    def evaluate(self, states: np.ndarray, *, reps: int = 1) -> tuple[np.ndarray, dict[str, Any]]:
        if not bool(self.handle.value):
            raise RuntimeError("rust HIP full residual FFI handle is closed")
        state_batch = np.ascontiguousarray(states, dtype=np.float64)
        if state_batch.ndim != 2:
            raise ValueError("states must be a 2D array shaped (batch, n_dof)")
        if int(state_batch.shape[1]) != int(self.n_dof):
            raise ValueError(f"state n_dof {state_batch.shape[1]} does not match backend n_dof {self.n_dof}")
        self.evaluation_count += 1
        residual = np.empty((int(state_batch.shape[0]), int(self.free_count)), dtype=np.float64)
        status = _RustHipFullResidualStatus()
        started = time.perf_counter()
        rc = int(
            self.library.mgt_rust_hip_full_residual_eval(
                self.handle,
                _as_void_p(state_batch),
                ctypes.c_longlong(int(state_batch.shape[0])),
                ctypes.c_int(max(int(reps), 1)),
                _as_void_p(residual),
                ctypes.byref(status),
            )
        )
        elapsed = float(time.perf_counter() - started)
        if rc != 0:
            last_error = self.library.mgt_rust_hip_full_residual_last_error()
            message = last_error.decode("utf-8", errors="replace") if last_error else ""
            raise RuntimeError(f"rust HIP full residual FFI evaluation failed: rc={rc} {message}")
        meta = {
            "backend": "rust_hip_full_residual_ffi",
            "single_subprocess_boundary": False,
            "persistent_process_worker": False,
            "persistent_in_process_worker": True,
            "rust_ffi_worker": True,
            "native_hip_c_abi": True,
            "operator_buffers_device_resident": bool(status.operator_buffers_device_resident),
            "worker_evaluation_count": int(self.evaluation_count),
            "worker_pid": int(os.getpid()),
            "batch_size": int(state_batch.shape[0]),
            "free_dof_count": int(self.free_count),
            "operator_create_seconds": float(self.operator_create_seconds),
            "ffi_call_seconds": elapsed,
            "hip_kernel_mean_seconds": float(status.kernel_elapsed_ms_mean) / 1000.0,
            "hip_kernel_total_seconds": float(status.kernel_elapsed_ms_total) / 1000.0,
            "eval_buffers_reused": bool(status.eval_buffers_reused),
            "device_name": self._device_name(),
            "build": self.build,
            "hip": {
                "code": int(status.code),
                "frame_element_count": int(status.frame_element_count),
                "n_dof": int(status.n_dof),
                "free_count": int(status.free_count),
                "shell_nnz": int(status.shell_nnz),
                "spring_nnz": int(status.spring_nnz),
                "batch_size": int(status.batch_size),
                "reps": int(status.reps),
                "device_id": int(status.device_id),
                "eval_buffers_reused": bool(status.eval_buffers_reused),
                "operator_buffers_device_resident": bool(status.operator_buffers_device_resident),
                "kernel_elapsed_ms_total": float(status.kernel_elapsed_ms_total),
                "kernel_elapsed_ms_mean": float(status.kernel_elapsed_ms_mean),
                "output_abs_sum": float(status.output_abs_sum),
                "output_max_abs": float(status.output_max_abs),
            },
            "operator_sizes": {
                "frame_element_count": int(self.frame_element_count),
                "shell_nnz": int(self.shell_nnz),
                "spring_nnz": int(self.spring_nnz),
            },
        }
        return residual, meta

    def close(self) -> None:
        if bool(self.handle.value):
            self.library.mgt_rust_hip_full_residual_destroy(self.handle)
            self.handle = ctypes.c_void_p()

    def __enter__(self) -> "HipFullResidualRustFfiBackend":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
