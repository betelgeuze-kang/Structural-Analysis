#!/usr/bin/env python3
"""Bounded synthetic fixed-operator CPU/HIP residual timing; no specimen inputs.

Uses the existing frame+CSR shell+spring HIP kernels, not an RC material solver.
All source/binary/input identities and negative/slow results are retained.
"""

from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

if __name__ == "__main__":
    for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[_name] = "1"

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
PHASE_NAMES = (
    "allocation_ms",
    "h2d_ms",
    "kernel_device_ms",
    "kernel_host_ms",
    "d2h_ms",
    "resident_total_ms",
)
CLAIM = (
    "Generated fixed linear 12-DOF frame blocks plus banded shell CSR and diagonal "
    "spring operators only; not experimental data, RC material Newton, complete "
    "structural solves, physical validation, production HIP support or release evidence. "
    "CPU comparison is compiled SciPy CSR application; timing excludes input generation "
    "and parity/hash checks. GPU kernel time alone excludes transfers and setup."
)


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def summarize(values) -> dict:
    values = [float(value) for value in values]
    return {
        "samples": values,
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "population_stdev": statistics.pstdev(values),
    }


def generated_case(dimension: int, batch: int) -> dict:
    if type(dimension) is not int or dimension < 12 or dimension % 6:
        raise ValueError("dimension must be a Python integer multiple of 6 >= 12")
    if type(batch) is not int or not 1 <= batch <= 64:
        raise ValueError("batch must be a Python integer in [1, 64]")
    elements = dimension // 6 - 1
    dofs = np.arange(elements, dtype=np.int64)[:, None] * 6 + np.arange(
        12, dtype=np.int64
    )
    local = np.diag(np.linspace(2.0, 4.0, 12))
    local += np.diag(np.full(11, -0.25), 1) + np.diag(np.full(11, -0.25), -1)
    stiffness = np.broadcast_to(local, (elements, 12, 12)).copy()
    rows = np.broadcast_to(dofs[:, :, None], stiffness.shape).reshape(-1)
    columns = np.broadcast_to(dofs[:, None, :], stiffness.shape).reshape(-1)
    frame = sparse.coo_matrix(
        (stiffness.reshape(-1), (rows, columns)), shape=(dimension, dimension)
    ).tocsr()
    shell = sparse.diags(
        [
            np.full(dimension - 1, -0.125),
            np.full(dimension, 0.5),
            np.full(dimension - 1, -0.125),
        ],
        [-1, 0, 1],
        format="csr",
    )
    spring = sparse.diags(np.linspace(0.05, 0.15, dimension), format="csr")
    operator = (frame + shell + spring).tocsr()
    operator.eliminate_zeros()
    operator.sort_indices()
    states = (
        np.sin(
            np.arange(batch * dimension, dtype=np.float64).reshape(batch, dimension)
            * 0.013
        )
        * 1.0e-3
    )
    external = np.cos(np.arange(dimension, dtype=np.float64) * 0.017) * 0.01
    arrays = {
        "frame_dofs": dofs,
        "frame_stiffness": stiffness,
        "shell_row_ptr": shell.indptr.astype(np.int64),
        "shell_col_idx": shell.indices.astype(np.int64),
        "shell_values": shell.data,
        "spring_row_ptr": spring.indptr.astype(np.int64),
        "spring_col_idx": spring.indices.astype(np.int64),
        "spring_values": spring.data,
        "external": external,
        "free": np.arange(dimension, dtype=np.int64),
        "states": states,
    }
    h = hashlib.sha256()
    for name, array in sorted(arrays.items()):
        h.update(name.encode())
        h.update(array.dtype.str.encode())
        h.update(json.dumps(array.shape).encode())
        h.update(array.tobytes())
    return {
        "dimension": dimension,
        "batch": batch,
        "elements": elements,
        "arrays": arrays,
        "operator": operator,
        "input_hash": "sha256:" + h.hexdigest(),
        "input_bytes": sum(array.nbytes for array in arrays.values()),
    }


def cpu_residual(case: dict) -> np.ndarray:
    a = case["arrays"]
    return np.ascontiguousarray((case["operator"] @ a["states"].T).T - a["external"])


class Status(ct.Structure):
    _fields_ = (
        [("code", ct.c_int)]
        + [
            (name, ct.c_longlong)
            for name in (
                "frame_element_count",
                "n_dof",
                "free_count",
                "shell_nnz",
                "spring_nnz",
                "batch_size",
            )
        ]
        + [
            (name, ct.c_int)
            for name in (
                "reps",
                "device_id",
                "eval_buffers_reused",
                "operator_buffers_device_resident",
            )
        ]
        + [
            (name, ct.c_double)
            for name in (
                "kernel_elapsed_ms_total",
                "kernel_elapsed_ms_mean",
                "output_abs_sum",
                "output_max_abs",
            )
        ]
    )


class DeviceInfo(ct.Structure):
    _fields_ = [
        ("name", ct.c_char * 256),
        ("architecture", ct.c_char * 256),
        ("global_memory_bytes", ct.c_ulonglong),
    ] + [
        (name, ct.c_int)
        for name in (
            "multiprocessors",
            "clock_khz",
            "driver_version",
            "runtime_version",
        )
    ]


class HipResidual:
    def __init__(self, path: Path):
        self.lib = ct.CDLL(str(path))
        pointer = ct.c_void_p
        self.lib.mgt_hip_full_residual_create.argtypes = (
            [ct.POINTER(pointer)]
            + [pointer] * 10
            + [ct.c_longlong] * 5
            + [ct.POINTER(Status)]
        )
        self.lib.mgt_hip_full_residual_create.restype = ct.c_int
        self.lib.structural_hip_residual_timed_eval.argtypes = [
            pointer,
            pointer,
            ct.c_longlong,
            pointer,
            pointer,
        ]
        self.lib.structural_hip_residual_timed_eval.restype = ct.c_int
        self.lib.mgt_hip_full_residual_destroy.argtypes = [pointer]
        self.lib.mgt_hip_full_residual_last_error.restype = ct.c_char_p
        self.lib.structural_hip_residual_device_info.argtypes = [ct.POINTER(DeviceInfo)]

    def checked(self, value):
        if value != 0:
            raise RuntimeError(self.lib.mgt_hip_full_residual_last_error().decode())

    def device(self) -> dict:
        info = DeviceInfo()
        self.checked(self.lib.structural_hip_residual_device_info(ct.byref(info)))
        return {
            name: (value.decode() if isinstance(value, bytes) else value)
            for name, _ in info._fields_
            for value in [getattr(info, name)]
        }

    def create(self, case):
        a = case["arrays"]
        names = (
            "frame_dofs",
            "frame_stiffness",
            "shell_row_ptr",
            "shell_col_idx",
            "shell_values",
            "spring_row_ptr",
            "spring_col_idx",
            "spring_values",
            "external",
            "free",
        )
        handle, status = ct.c_void_p(), Status()
        start = time.perf_counter()
        self.checked(
            self.lib.mgt_hip_full_residual_create(
                ct.byref(handle),
                *[a[name].ctypes.data for name in names],
                case["elements"],
                case["dimension"],
                a["shell_values"].size,
                a["spring_values"].size,
                case["dimension"],
                ct.byref(status),
            )
        )
        return handle, (time.perf_counter() - start) * 1000

    def evaluate(self, handle, case, output):
        phase = np.empty(6, dtype=np.float64)
        start = time.perf_counter()
        self.checked(
            self.lib.structural_hip_residual_timed_eval(
                handle,
                case["arrays"]["states"].ctypes.data,
                case["batch"],
                output.ctypes.data,
                phase.ctypes.data,
            )
        )
        return phase, (time.perf_counter() - start) * 1000


def benchmark_case(backend, dimension, batch, warmups, samples):
    case = generated_case(dimension, batch)
    expected = cpu_residual(case)
    output = np.empty_like(expected)
    handle, setup = backend.create(case)
    try:
        cold_phase, cold_wall = backend.evaluate(handle, case, output)
        for _ in range(warmups):
            cpu_residual(case)
            backend.evaluate(handle, case, output)
        cpu_times, gpu_times, phases = [], [], []
        for index in range(samples):
            # Alternate order to reduce systematic heating/order bias.
            def cpu():
                start = time.perf_counter()
                actual = cpu_residual(case)
                cpu_times.append((time.perf_counter() - start) * 1000)
                if not np.array_equal(actual, expected):
                    raise RuntimeError("CPU reference changed")

            def gpu():
                phase, wall = backend.evaluate(handle, case, output)
                phases.append(phase)
                gpu_times.append(wall)
                if not np.allclose(output, expected, rtol=1e-11, atol=1e-12):
                    raise RuntimeError("HIP FP64 parity failed")

            if index % 2:
                gpu()
                cpu()
            else:
                cpu()
                gpu()
        error = np.abs(output - expected)
        return {
            "dimension": dimension,
            "batch": batch,
            "elements": case["elements"],
            "operator_nnz": case["operator"].nnz,
            "input_hash": case["input_hash"],
            "input_bytes": case["input_bytes"],
            "setup_operator_allocation_and_h2d_ms": setup,
            "cold_evaluation_phases_ms": dict(zip(PHASE_NAMES, cold_phase.tolist())),
            "cold_evaluation_wall_ms": cold_wall,
            "cpu_total_ms": summarize(cpu_times),
            "gpu_total_ms": summarize(gpu_times),
            "gpu_phases_ms": {
                name: summarize([row[index] for row in phases])
                for index, name in enumerate(PHASE_NAMES)
            },
            "resident_end_to_end_speedup": statistics.median(cpu_times)
            / statistics.median(gpu_times),
            "parity": {
                "pass": True,
                "rtol": 1e-11,
                "atol": 1e-12,
                "maximum_absolute_error": float(error.max()),
                "relative_l2_error": float(
                    np.linalg.norm(error)
                    / max(np.linalg.norm(expected), np.finfo(float).tiny)
                ),
                "cpu_output_hash": digest(expected.tobytes()),
                "last_gpu_output_hash": digest(output.tobytes()),
            },
        }
    finally:
        backend.checked(backend.lib.mgt_hip_full_residual_destroy(handle))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--hipcc", type=Path, default=Path("/opt/rocm/bin/hipcc"))
    parser.add_argument("--architecture", default="gfx1030")
    parser.add_argument(
        "--dimensions", type=int, nargs="+", default=[1536, 12288, 49152]
    )
    parser.add_argument("--batches", type=int, nargs="+", default=[1, 8, 32])
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--reuse-library", action="store_true")
    args = parser.parse_args(argv)
    if not 3 <= args.samples <= 31 or not 0 <= args.warmups <= 5:
        parser.error("samples must be in [3,31], warmups in [0,5]")
    if (
        any(value < 12 or value > 196608 or value % 6 for value in args.dimensions)
        or any(value < 1 or value > 64 for value in args.batches)
        or len(args.dimensions) * len(args.batches) > 20
    ):
        parser.error("bounded sweep exceeded")
    args.out.mkdir(parents=True, exist_ok=True)
    library = args.out / "libstructural_hip_residual_timing.so"
    source = ROOT / "native/hip/hip_residual_timing.cpp"
    parents = [
        source,
        ROOT / "implementation/phase1/hip_full_residual_ffi.cpp",
        Path(__file__).resolve(),
    ]
    command = [
        str(args.hipcc),
        "-O3",
        "-std=c++17",
        f"--offload-arch={args.architecture}",
        "-shared",
        "-fPIC",
        str(source),
        "-o",
        str(library),
    ]
    device_libraries = (
        ROOT
        / "implementation/phase1/third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
    )
    if device_libraries.is_dir():
        command.insert(4, f"--rocm-device-lib-path={device_libraries}")
    receipt = {
        "schema_version": "structural-synthetic-hip-residual-performance.v1",
        "claim_boundary": CLAIM,
        "source_files": {
            str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in parents
        },
        "cpu_thread_environment": {
            name: os.environ[name]
            for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "cpu_baseline": "scipy.sparse.csr_matrix @ batched_states.T minus external loads",
        "runtime_versions": {
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
        },
        "process_cpu_affinity": sorted(os.sched_getaffinity(0)),
        "status": "started",
        "cases": [],
    }
    build_manifest_path = args.out / "build-manifest.json"
    compiled_sources = {
        str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in parents[:2]
    }
    try:
        if not args.reuse_library:
            start = time.perf_counter()
            build = subprocess.run(command, capture_output=True, text=True, timeout=240)
            (args.out / "build.log").write_text(build.stdout + build.stderr)
            receipt["build"] = {
                "command": command,
                "returncode": build.returncode,
                "seconds": time.perf_counter() - start,
            }
            if build.returncode:
                raise RuntimeError("HIP compilation failed; see build.log")
            build_manifest_path.write_text(
                json.dumps(
                    {
                        "build": receipt["build"],
                        "source_files": compiled_sources,
                        "binary_hash": digest(library.read_bytes()),
                    },
                    indent=2,
                )
            )
        else:
            previous = json.loads(build_manifest_path.read_text())
            if previous["source_files"] != compiled_sources or previous[
                "binary_hash"
            ] != digest(library.read_bytes()):
                raise RuntimeError(
                    "reuse library does not match its bound source/binary manifest"
                )
            receipt["build"] = previous["build"]
            receipt["reused_verified_build"] = True
        receipt["binary_hash"] = digest(library.read_bytes())
        if args.compile_only:
            receipt["status"] = "compiled_not_executed"
        else:
            backend = HipResidual(library)
            receipt["device"] = backend.device()
            if receipt["device"]["architecture"].split(":")[0] != args.architecture:
                raise RuntimeError(
                    "actual GPU architecture differs from compiled target"
                )
            receipt["device_properties_hash"] = digest(
                json.dumps(receipt["device"], sort_keys=True).encode()
            )
            for dimension in args.dimensions:
                for batch in args.batches:
                    row = benchmark_case(
                        backend, dimension, batch, args.warmups, args.samples
                    )
                    receipt["cases"].append(row)
                    (args.out / "performance.json").write_text(
                        json.dumps(receipt, indent=2)
                    )
            receipt["status"] = "passed"
    except Exception as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
    (args.out / "performance.json").write_text(json.dumps(receipt, indent=2))
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "cases": len(receipt["cases"]),
                "receipt": str(args.out / "performance.json"),
                "error": receipt.get("error"),
            }
        )
    )
    return 0 if receipt["status"] in ("passed", "compiled_not_executed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
